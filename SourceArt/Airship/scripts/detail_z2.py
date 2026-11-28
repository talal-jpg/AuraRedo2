"""Zone 2 of the airship detail pass (round 3, 2026-11-28): the STARBOARD hull flank and the front-right pod.

Z2 = the starboard mirror of zone 1 (approved 2026-11-28, "keep it as it is"): the flank between the starboard cannon
stations (x -11.55 .. 6.95), deck edge to the bilge line, carried forward over pod FR's pocket (plates end at its fore
rim strap), + pod Thruster_FR (drum, nozzle, 12 petals) + the FR pocket rim and cavity. Same kinds, same density, same
layout code as zone 1 (detail_flank / detail_pod with zone 1's knobs), its own seed and a few knobs tuned for the
starboard hull, which is not a mirror of the port one (ZONE_2.md):
  * the RR pocket cuts much higher into the starboard flank (RR sits 0.64 m further out than a mirror of RL): there is
    only a 0.45-0.7 m strip under the gunwale band from x -9 to -5.6, so zone 1's first upper bay (x -7.4) has no room
    and the aft upper rows are 0.7-0.9 m tall (a bay needs 0.9): both upper bays go into the free run x -5.55 .. 1.45,
    staggered with the lower bays (K['ubay']['x_pref'])
  * the aft channel run is 1.25 m long on starboard (port 1.40, zone 1's minimum): the minimum is 1.20 here, so the
    pipe channel starts at the Z3 seam on both sides (K['chan_min_len'])
  * pod FR: the shared hull-clearance test (detail_pod.HullClear) decides inside / outside by the normal of the nearest
    skin point; 2-3 m from the hull (the outboard lower drum of FR) that sign flips at random, so the lower hug pipe,
    both actuators and some drum plates were dropped. Zone 2 replaces it at run time with a ray-parity test
    (HullClearParity, same margins); the rig check (243 poses) proves the result.
  * the FR pocket rim: detail_z2_rim.pocket_rim_z2, zone 1's rim code with robust edge fits, 3D-smoothed straps, a
    zone-2 / smooth-skin filter and a 0.6 m minimum piece (the shared one made a wavy top strap and broken bits past
    the fore edge on this side)

  blender_capped.sh --python detail_z2.py [-- --no-save] [--seed N] [--sweep a,b,c] [--report FILE] [--blend-out FILE]

Opens rig/AirshipRig.blend READ ONLY, builds collection Detail_Z2 and saves rig/detail/zones/AirshipRig_detail_z2.blend
(D.safe_save). Writes Docs/Airship/round3/z2_report.json and z2_continuity.json (+ a copy of the continuity file in
rig/detail/zones/). Objects (parent Armature, Armature modifier, every vertex 100 % on one bone):
  SM_AirshipDetail_Z2_Hull        -> Hull
  SM_AirshipDetail_Z2_Pod_FR      -> Thruster_FR
  SM_AirshipDetail_Z2_Nozzle_FR   -> Thruster_FR_Nozzle
  SM_AirshipDetail_Z2_Petals_FR   -> Thruster_FR_Petal00 .. 11
"""
import bpy, sys, os, math, random, json, time, copy
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from mathutils import Vector as V
import rig_common as C
import detail_common as D
import detail_ship as S
import detail_zones as Z
import detail_checks as CK
import detail_base_edits as BE
import detail_flank as FLK
import detail_pod as POD
import detail_zone1 as Z1
import detail_z2_rim as RIM

ZONE = 'Z2'
DOCS = '/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/round3'
POD_ID = 'FR'

# ------------------------------------------------------------------ knobs: zone 1's (the approved density) + Z2 changes
K = copy.deepcopy(Z1.K)
K.update(seed=2341)                       # own seed (sweep: calm area, armour, ribs, frames closest to zone 1)
K['ubay']['x_pref'] = (-5.0, 0.6)          # upper bays: the RR pocket leaves no room aft (zone 1: -7.4, -2.3); both go
                                          # into the free run x -5.55 .. 1.45, staggered with the lower bays
K['chan_min_len'] = 1.20                  # pipe channel minimum run (zone 1: 1.40; the starboard aft run is 1.25 m)
K['pod'].update(hug_th=(-76.0, 70.0), act_th=(32.0, 46.0))   # zone 1's angles (they fit once the clearance test is sound)
K['hullclear'] = dict(dirs=5, near=0.0)    # HullClearParity: rays per test (majority vote)


# ------------------------------------------------------------------ run-time replacements (shared modules unchanged)
class HullClearParity:
    """is a point outside the hull solid and at least `margin` from the skin? Inside / outside by ray parity (majority
    of several directions) instead of the sign of the nearest skin normal (detail_pod.HullClear), which flips at random
    when the nearest skin point is metres away on an edge of the pocket opening."""
    DIRS = [D.unit(np.array(d, float)) for d in ((0.13, 0.21, 1.0), (0.11, -0.17, -1.0), (0.97, 0.05, 0.23),
                                                  (-0.95, 0.12, -0.27), (0.07, 1.0, 0.19))]

    def __init__(self, skin):
        self.skin = skin
        self.bvh = skin.bvh
        self.cache = {}

    def inside(self, p):
        key = tuple(np.round(np.asarray(p, float), 4))
        if key in self.cache:
            return self.cache[key]
        votes = 0
        for d in self.DIRS[:K['hullclear']['dirs']]:
            o, n = V(p), 0
            dv = V(d)
            for _ in range(60):
                hit = self.bvh.ray_cast(o, dv, 200.0)
                if hit[0] is None:
                    break
                n += 1
                o = hit[0] + dv * 1e-4
            votes += n % 2
        r = votes * 2 > K['hullclear']['dirs']
        self.cache[key] = r
        return r

    def __call__(self, p, margin):
        r = self.skin.nearest(p, 5.0)
        if r is not None and r[3] < margin:
            return False
        return not self.inside(p)


_x_runs_orig = FLK.x_runs


def x_runs_z2(ok_fn, xs, min_len, join=0.11):
    """detail_flank.x_runs with the pipe channel's minimum run (1.4, used only by the channel call) from K"""
    if abs(min_len - 1.4) < 1e-9:
        min_len = K['chan_min_len']
    return _x_runs_orig(ok_fn, xs, min_len, join)


def install_overrides():
    POD.HullClear = HullClearParity          # build_pod looks HullClear up in its module at call time
    FLK.x_runs = x_runs_z2                   # build_flank looks x_runs up in its module at call time


def opts():
    a = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    o = {}
    for i, k in enumerate(a):
        if k.startswith('--'):
            o[k[2:]] = a[i + 1] if i + 1 < len(a) and not a[i + 1].startswith('--') else True
    return o


# ------------------------------------------------------------------ build
def build(ship, zi, deleted, K, log, flank_only=False):
    """{part: (Mesh, bone or None)}; the hull flank, FR pocket rim and cavity on the Hull bone, the FR pod parts"""
    seed = K['seed']
    fl = Flank(ship, K, deleted)
    log['_fl'] = fl
    hull = D.Mesh('hull'); hull.cur_group = 'Hull'
    rim_pts = RIM.pocket_rim_z2(hull, fl, ship, K, random.Random(seed + 2), log, pod=POD_ID, zone=ZONE, zi=zi)
    FLK.build_flank(hull, fl, ship, K, random.Random(seed + 1), log, rim_pts)
    if flank_only:
        return {'Hull': (hull, 'Hull')}
    POD.cavity(hull, ship, fl, K, random.Random(seed + 3), log, pod=POD_ID)
    pod = D.Mesh('pod'); pod.cur_group = 'Thruster_' + POD_ID
    noz = D.Mesh('noz'); noz.cur_group = 'Thruster_%s_Nozzle' % POD_ID
    pet = D.Mesh('pet'); pet.cur_group = None
    POD.build_pod(pod, noz, pet, ship, K, random.Random(seed + 4), log, skin=fl.skin, which=POD_ID)
    log['pocket_rim_points'] = len(rim_pts)
    return {'Hull': (hull, 'Hull'), 'Pod_' + POD_ID: (pod, 'Thruster_' + POD_ID),
            'Nozzle_' + POD_ID: (noz, 'Thruster_%s_Nozzle' % POD_ID), 'Petals_' + POD_ID: (pet, None)}


def Flank(ship, K, deleted):
    # obstacles = every SM_Airship face that is not the skin and not removed by a registered base edit
    return FLK.Flank(ship, K, side=-1, obst_mask=(ship.p_island != S.SKIN) & ~deleted)


def flank_stats(log, hull):
    L = log['layers']
    return dict(calm=L['calm_share_of_area'], raised=L['raised'], armour=L['armour'], battens=L['battens'],
                slotted=L['slotted'], frames=L['frames'], patches=L['patches'], plates=log['plates'],
                bays=len(log['bays']), ubays=len(log['upper_bays']), spans=log['pipe_spans'], teeth=log['teeth'],
                strake=log['strake'], fittings=log['through_hull_fittings'], tris=hull.tris(),
                skipped=log.get('skipped_on_step', 0))


def area_by_zone(ship, zi):
    """SM_Airship face area per owner, split in pod parts (Thruster_*) and the rest (hull-like)"""
    me = ship.ob.data
    area = np.empty(len(me.polygons)); me.polygons.foreach_get('area', area)
    pod = np.char.startswith(ship.p_src.astype(str), 'Thruster_')
    out = {}
    for z in ('Z1', 'Z2'):
        m = zi.zone == z
        out[z] = dict(total_m2=round(float(area[m].sum()), 1), pod_m2=round(float(area[m & pod].sum()), 1),
                      hull_m2=round(float(area[m & ~pod].sum()), 1))
    return out


def pod_checks(ship, fl, parts):
    """zone 1's silhouette / pod outline checks, for pod FR"""
    hull, pod, noz, pet = (parts[k][0] for k in ('Hull', 'Pod_FR', 'Nozzle_FR', 'Petals_FR'))
    pod_mask = np.char.startswith(ship.p_bone.astype(str), 'Thruster_' + POD_ID)
    pod_surf = ship.surface(pod_mask)
    O, T0, A, NP = ship.pod_frame(POD_ID)
    e0, e90 = S.pod_basis(A)
    R = K['pocket']['r']
    hv = np.array(hull.v)
    h_, th_, r_ = CK.pod_frame_coords(hv, T0, A, e0, e90)
    in_cav = (r_ < R + 0.1) & (h_ > K['pocket']['roof_h'] - 0.1) & (h_ < 1.3)
    pod_co = ship.co[np.char.startswith(ship.v_bone.astype(str), 'Thruster_' + POD_ID)]
    pv = np.array(pod.v)
    sil = CK.silhouette_table(pod_surf.bvh, T0, A, e0, e90, pod_co=pod_co)
    vk = CK.vertex_kinds(hull)
    return dict(
        hull_flank_vs_skin=CK.dist_report(hv[~in_cav], fl.skin, 'hull details outside the FR pocket vs hull skin', 0.20,
                                          vkind=[k_ for k_, c_ in zip(vk, ~in_cav) if c_]),
        hull_cavity_vs_skin=CK.dist_report(hv[in_cav], fl.skin, 'FR pocket cavity details vs hull skin', 0.20),
        pod_vs_pod=CK.dist_report(pv, pod_surf, 'pod details vs pod surface', 0.15, vkind=CK.vertex_kinds(pod)),
        nozzle_vs_pod=CK.dist_report(noz.v, pod_surf, 'nozzle details vs pod surface', 0.15),
        petals_vs_pod=CK.dist_report(pet.v, pod_surf, 'petal details vs pod surface', 0.15),
        pod_envelope=CK.envelope_report(pv, pod_surf.bvh, T0, A, e0, e90, 'pod details outside the pod radial envelope',
                                        sil=sil, vkind=CK.vertex_kinds(pod)),
        nozzle_envelope=CK.envelope_report(noz.v, pod_surf.bvh, T0, A, e0, e90,
                                           'nozzle details outside the pod radial envelope', sil=sil,
                                           vkind=CK.vertex_kinds(noz)),
        petal_envelope=CK.envelope_report(pet.v, pod_surf.bvh, T0, A, e0, e90,
                                          'petal details outside the pod radial envelope', sil=sil,
                                          vkind=CK.vertex_kinds(pet)),
        pa_boxes=CK.pa_report(np.concatenate([hv, pv]) if len(pv) else hv, K['pa_boxes']),
        hull_details_max_z=round(float(hv[:, 2].max()), 3) if len(hv) else None)


def ownership_detail(parts, zi, margin=Z.MARGIN):
    """every detail vertex (not sampled) whose owner is another zone: grouped by object, kind and owner, with the
    bounding box, so each group can be explained (a pod part over the belly, a strap ending on the seam ...)"""
    out = {}
    for name, (m, _) in parts.items():
        vk = CK.vertex_kinds(m)
        for i, p in enumerate(m.v):
            z = zi.zone_at(p)
            if z == ZONE:
                continue
            seam = Z.volume_owner(p) is None and ZONE in zi.zones_within(p, margin + 0.2)
            key = '%s|%s|%s|%s' % (name, vk[i], z, 'seam' if seam else 'OUTSIDE')
            r = out.setdefault(key, dict(n=0, lo=[9e9] * 3, hi=[-9e9] * 3))
            r['n'] += 1
            r['lo'] = [round(min(a, b), 3) for a, b in zip(r['lo'], p)]
            r['hi'] = [round(max(a, b), 3) for a, b in zip(r['hi'], p)]
    return out


def main():
    o = opts()
    install_overrides()
    if o.get('seed'):
        K['seed'] = int(o['seed'])
    zn = '2'
    coll_name, prefix = 'Detail_Z2', 'SM_AirshipDetail_Z2_'
    report_path = o.get('report') or (DOCS + '/z2_report.json')
    out_blend = o.get('blend-out') or D.zone_blend(zn)
    t0 = time.time()
    bpy.ops.wm.open_mainfile(filepath=C.RIG_BLEND)                 # read only: never saved under this name
    ship = S.Ship(bpy)
    mats = D.ensure_materials()
    zi = Z.ZoneIndex(ship)
    be_rep = {}
    deleted = BE.deleted_mask(ship, 'all', be_rep)
    if o.get('sweep'):
        # flank only, several seeds: the layer statistics to compare with zone 1's (no save, no report)
        z1 = dict(calm=0.30, raised=6, armour=2, battens=6, slotted=5, frames=3, patches=6)
        print('[Z2] sweep zone 1:', json.dumps(z1))
        fl = None
        for sd in [int(s) for s in str(o['sweep']).split(',')]:
            lg = {}
            if fl is None:
                fl = Flank(ship, K, deleted)
                rim = RIM.pocket_rim_z2(D.Mesh('r'), fl, ship, K, random.Random(sd + 2), lg, pod=POD_ID, zone=ZONE,
                                        zi=zi)
            h = D.Mesh('hull'); h.cur_group = 'Hull'
            FLK.build_flank(h, fl, ship, K, random.Random(sd + 1), lg, rim)
            st = flank_stats(lg, h)
            print('[Z2] sweep', sd, json.dumps(st))
            sys.stdout.flush()
        os._exit(0)
    log = {}
    parts = build(ship, zi, deleted, K, log)
    fl = log.pop('_fl')
    ship_bvh = ship.bvh(~deleted)
    dropped, flipped = {}, {}
    for name, (m, _) in parts.items():
        for _ in range(3):
            dd = D.drop_floating(m, [ship_bvh], tol=K['touch_tol'])
            if not dd:
                break
            for k_, v_ in dd.items():
                dropped.setdefault(name, {})[k_] = dropped.get(name, {}).get(k_, 0) + v_
        flipped[name] = m.orient_outward()
    log['floating_pieces_removed'] = dropped
    log['inside_out_pieces_flipped'] = flipped
    log['stats'] = flank_stats(log, parts['Hull'][0])
    coll = bpy.data.collections.get(coll_name) or bpy.data.collections.new(coll_name)
    if coll.name not in [c.name for c in bpy.context.scene.collection.children]:
        bpy.context.scene.collection.children.link(coll)
    objs = []
    for name, (m, bone) in parts.items():
        if not m.f:
            continue
        objs.append(m.to_object(prefix + name, coll, mats, arm=ship.arm, groups=bone if bone else list(m.g)))
    cont = log.pop('continuity', None)
    if cont is not None:
        C.dump_json(cont, DOCS + '/z2_continuity.json')
        C.dump_json(cont, D.ZONES_DIR + '/z2_continuity.json')
    kinds = {}
    for name, (m, _) in parts.items():
        for k, v in m.tris_by_kind().items():
            kinds[k] = kinds.get(k, 0) + v
    tris = {ob.name: int(sum(len(p.vertices) - 2 for p in ob.data.polygons)) for ob in objs}
    areas = area_by_zone(ship, zi)
    z1rep = C.load_json(D.ZONES_DIR + '/z1_report.json')
    hull_tris = tris.get(prefix + 'Hull', 0)
    dens = dict(z2_hull_tris_per_m2=round(hull_tris / max(1e-6, areas['Z2']['hull_m2']), 1),
                z1_hull_tris_per_m2=round(z1rep['tris']['Hull'] / max(1e-6, areas['Z1']['hull_m2']), 1),
                z2_rivet_share=round(kinds.get('rivet', 0) / max(1, sum(kinds.values())), 3),
                z1_rivet_share=round(z1rep['tris_by_kind'].get('rivet', 0) / max(1, z1rep['tris_total']), 3),
                z2_pod_total=sum(v for k, v in tris.items() if not k.endswith('_Hull')),
                z1_pod_total=sum(v for k, v in z1rep['tris'].items() if k != 'Hull'),
                areas=areas)
    rep = dict(zone=ZONE, knobs=K, log=log, base_edits=be_rep, tris=tris, tris_by_kind=kinds, density=dens,
               objects=[CK.object_report(ob, ZONE) for ob in objs],
               checks=pod_checks(ship, fl, parts), ownership_detail=ownership_detail(parts, zi),
               zone_checks=CK.zone_checks(objs, ZONE, ship, zi) if objs else None,
               seconds=round(time.time() - t0, 1))
    rep['tris_total'] = sum(rep['tris'].values())
    rep['all_objects_ok'] = all(r['ok'] for r in rep['objects'])
    C.dump_json(rep, report_path)
    print('[Z2] tris', rep['tris'], 'total', rep['tris_total'])
    print('[Z2] density', json.dumps({k: v for k, v in dens.items() if k != 'areas'}), json.dumps(areas))
    print('[Z2] stats', json.dumps(log['stats']))
    print('[Z2] objects ok', rep['all_objects_ok'], json.dumps([{k: r[k] for k in ('object', 'ok', 'inside_out_pieces',
          'nonmanifold_edges', 'not_rigid_vertices', 'faces_without_role')} for r in rep['objects']]))
    print('[Z2] checks', json.dumps(rep['checks'])[:3000])
    print('[Z2] zone checks', json.dumps(rep['zone_checks'])[:2000])
    print('[Z2] log', json.dumps({k: v for k, v in log.items() if k != 'stats'})[:2500])
    print('[Z2] report', report_path)
    if not o.get('no-save'):
        print('[Z2] saved', D.safe_save(out_blend))
    print('[Z2] done %.1f s' % (time.time() - t0))
    sys.stdout.flush()


if __name__ == '__main__':
    main()
