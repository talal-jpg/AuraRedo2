"""Zone 3 of the airship detail pass (round 3, 2026-11-28): the AFT FLANKS of both sides and the REAR PODS.

Z3 (detail_zones.py) = both hull flanks aft of x -11.55 (zone 1 / zone 2's aft edge, the aft cannon station) to the
stern, deck edge to the bilge line; the rear thruster pods Thruster_RL / Thruster_RR (drum, nozzle, petals) and their
hull pockets (walls and roof). Zone 1's approved language and density (detail_zone1.K), continued across the seam.

  blender_capped.sh --python detail_z3.py [-- --no-save] [--blend-out FILE] [--report FILE]

Opens rig/AirshipRig.blend READ ONLY, builds collection Detail_Z3 and saves rig/detail/zones/AirshipRig_detail_z3.blend
(detail_common.safe_save). Report: Docs/Airship/round3/z3_report.json (+ z3_continuity.json).

Objects (parent Armature, Armature modifier, every vertex 100 % on one bone):
  SM_AirshipDetail_Z3_Hull         Hull                     aft flanks (port + starboard), RL / RR pocket lips + stiffeners
  SM_AirshipDetail_Z3_Pod_RL       Thruster_RL              and _Nozzle_RL (Thruster_RL_Nozzle), _Petals_RL (PetalNN)
  SM_AirshipDetail_Z3_Pod_RR       Thruster_RR              and _Nozzle_RR, _Petals_RR
Modules: detail_z3_flank.py (aft flank layout, a modified copy of zone 1's), detail_z3_pod.py (hug pipes, actuators,
pocket lip). Shared modules are only imported.
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
import detail_zone1 as Z1
from detail_pod import build_pod
from detail_z3_flank import AftFlank, build_aft_flank
from detail_z3_pod import hug_pipes_and_actuators, pocket, motion_filter

ZONE = 'Z3'
DOCS = '/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/round3'

# ------------------------------------------------------------------ knobs: zone 1's (approved density) + what Z3 needs
K = copy.deepcopy(Z1.K)
K.update(
    seed=1303,
    seed_side={1: 1325, -1: 1311},           # one layout seed per side (picked by a seed scan: calm ~30 %, 1 armour)
    chart_x=(-16.4, -11.0, 0.05),
    x_aft_end=-15.30,                        # aft-most mask column (the stern corner beyond belongs to Z6 / Z5)
    x_mask_fwd=-11.60,                       # last mask column: plates end at -11.587, zone 1's start at -11.563
    gusset_grid_x0=-11.20,                   # zone 1's gusset grid x = -11.20 + 0.51 k
    seam_gland_x=-11.70,                     # channel pipes and conduits come out of glands here at the seam
    end_rib=dict(w=0.18, t=0.11),            # riveted rust rib the runs end on (top 12.5 cm off the skin, like ribs / teeth)
    z3_bay_w=(1.15, 2.0),                    # one lower machinery bay per side (zone 1: 2.1 / 1.6 m) ...
    z3_bay_v1=(2.78, 2.66, 2.54, 2.42),      # ... zone 1's height where it fits, else shorter (a step in the skin)
    zone_margin={'Z6': 0.12, 'none': 0.10, 'Z7': 0.10, 'Z4': 0.10, 'Z5': 0.03},
    seam_fallback={                          # used when the neighbour's continuity file is missing
        1: dict(ref_up=0.9281, ref_low=3.3742, ref_strake=3.3555, source='zone 1 z1_continuity.json'),
        -1: dict(ref_up=0.9327, ref_low=3.3902, ref_strake=3.3696,
                 source='zone 1 code on starboard (detail_selftest, the same deterministic lines Z2 builds on)')},
    pocket_z3=dict(lip_w=0.15, lip_t=0.04, pod_clear=0.05, stiff_step=15.0, zone='Z3'),
    pod_z3={
        # hugs: (h along the pod axis, pipe radius, material); prefer: angle windows (pod frame, mirrored on
        # starboard) of the sides seen from aft and from below; act_pref: preferred actuator angle
        # Both rear pods show the same kit on their AFT side (the side you see from the stern quarters): the hull
        # clearance leaves the front-outboard gap (where zone 1 put it on FL) almost closed on RL and closed on RR.
        'RL': dict(hugs=[(1.84, 0.06, 'copper'), (2.05, 0.05, 'brass')], prefer=[(130.0, 180.0), (-180.0, -170.0)],
                   hug_min_n=6, act_pref=158.0, act_gaps=(14, 10, 8), act_window=30, hug_max_deg=60.0),
        'RR': dict(hugs=[(1.84, 0.06, 'copper'), (2.05, 0.05, 'brass')], prefer=[(130.0, 180.0), (-180.0, -170.0)],
                   hug_min_n=6, act_pref=158.0, act_gaps=(14, 10, 8), act_window=30, hug_max_deg=60.0),
    },
)
K['slots'] = dict(K['slots'], low=1)
K['calm_target'] = 0.30
K['fill'] = dict(K['fill'], min_w=0.36, min_h=0.28)      # fewer tiny fill plates on the ragged stern masks
K['ubay'] = dict(K['ubay'], x_pref=(-12.9,), w=(1.6,))
K['pod'] = dict(K['pod'], hug_th=(0.0, 0.0), act_th=())     # built by detail_z3_pod instead (free angles per pod)
K['conduit'] = dict(K['conduit'], fittings_z3=1)


def opts():
    a = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    o = {}
    for i, k in enumerate(a):
        if k.startswith('--'):
            o[k[2:]] = a[i + 1] if i + 1 < len(a) and not a[i + 1].startswith('--') else True
    return o


def seam_targets(side):
    """the neighbour's reference lines at x -11.55: zone 1 (port), zone 2 (starboard) when its file exists"""
    f = DOCS + ('/z1_continuity.json' if side > 0 else '/z2_continuity.json')
    if os.path.exists(f):
        c = C.load_json(f)
        xs = c['xs']
        i = int(np.argmin([abs(x - (-11.55)) for x in xs]))
        return dict(ref_up=c['ref_up'][i], ref_low=c['ref_low'][i], ref_strake=c['ref_strake'][i], source=f)
    return dict(K['seam_fallback'][side])


def build(ship, zi, deleted, K, log):
    skin = ship.surface(ship.p_island == S.SKIN)
    hull = D.Mesh('hull'); hull.cur_group = 'Hull'
    parts = {'Hull': (hull, 'Hull')}
    # ---- aft flanks, port then starboard
    for side, name in ((1, 'port'), (-1, 'stbd')):
        t0 = time.time()
        lg = {}
        fl = AftFlank(ship, K, side=side)
        cont = seam_targets(side)
        build_aft_flank(hull, fl, ship, K, random.Random(K['seed_side'][side]), lg, zi, cont)
        lg['seam_source'] = cont.get('source')
        lg['seconds'] = round(time.time() - t0, 1)
        log['flank_' + name] = lg
    # ---- pockets of RL / RR (hull bone) and the two pods
    for i, which in enumerate(('RL', 'RR')):
        pocket(hull, ship, skin, which, K, random.Random(K['seed'] + 10 + i), log, zi)
        pod = D.Mesh('pod'); pod.cur_group = 'Thruster_' + which
        noz = D.Mesh('noz'); noz.cur_group = 'Thruster_%s_Nozzle' % which
        pet = D.Mesh('pet'); pet.cur_group = None
        lg = {}
        build_pod(pod, noz, pet, ship, K, random.Random(K['seed'] + 20 + i), lg, skin=skin, which=which)
        hug_pipes_and_actuators(pod, ship, which, K, lg, skin)
        log['pod_' + which] = lg
        parts['Pod_' + which] = (pod, 'Thruster_' + which)
        parts['Nozzle_' + which] = (noz, 'Thruster_%s_Nozzle' % which)
        parts['Petals_' + which] = (pet, None)
    # the pods' whole motion range against the hull (after both pockets exist: the lips are hull details)
    if K.get('debug_dir'):
        log['debug_dir'] = K['debug_dir']
    for which in ('RL', 'RR'):
        motion_filter(ship, deleted, which, parts['Pod_' + which][0], parts['Nozzle_' + which][0], hull, log)
    log.pop('debug_dir', None)
    return parts


def checks(ship, parts, objs, zi, K, log):
    """zone 3's own checks on top of detail_checks.zone_checks: silhouette (hull details vs skin, outside the
    pockets), pod outline growth (zone 1's envelope_report), density numbers"""
    out = {}
    skin = ship.surface(ship.p_island == S.SKIN)
    hull = parts['Hull'][0]
    hv = np.array(hull.v)
    in_cav = np.zeros(len(hv), bool)
    R = K['pocket']['r']
    for which in ('RL', 'RR'):
        O, T0, A, NP = ship.pod_frame(which)
        e0, e90 = S.pod_basis(A)
        h_, th_, r_ = CK.pod_frame_coords(hv, T0, A, e0, e90)
        in_cav |= (r_ < R + 0.1) & (h_ > K['pocket']['roof_h'] - 0.1) & (h_ < 2.6)
    vk = CK.vertex_kinds(hull)
    out['hull_flank_vs_skin'] = CK.dist_report(hv[~in_cav], skin, 'aft flank details vs hull skin', 0.20,
                                               vkind=[k for k, c in zip(vk, ~in_cav) if c])
    out['pocket_vs_skin'] = CK.dist_report(hv[in_cav], skin, 'RL / RR pocket details vs hull skin', 0.20)
    for which in ('RL', 'RR'):
        pod, noz, pet = parts['Pod_' + which][0], parts['Nozzle_' + which][0], parts['Petals_' + which][0]
        O, T0, A, NP = ship.pod_frame(which)
        e0, e90 = S.pod_basis(A)
        pod_mask = np.char.startswith(ship.p_bone.astype(str), 'Thruster_' + which)
        pod_surf = ship.surface(pod_mask)
        pod_co = ship.co[np.char.startswith(ship.v_bone.astype(str), 'Thruster_' + which)]
        sil = CK.silhouette_table(pod_surf.bvh, T0, A, e0, e90, pod_co=pod_co)
        out['pod_envelope_' + which] = CK.envelope_report(np.array(pod.v), pod_surf.bvh, T0, A, e0, e90,
                                                          'pod %s details outside the pod radial envelope' % which,
                                                          sil=sil, vkind=CK.vertex_kinds(pod))
        out['nozzle_envelope_' + which] = CK.envelope_report(np.array(noz.v), pod_surf.bvh, T0, A, e0, e90,
                                                             'nozzle %s details' % which, sil=sil, vkind=CK.vertex_kinds(noz))
        out['petal_envelope_' + which] = CK.envelope_report(np.array(pet.v), pod_surf.bvh, T0, A, e0, e90,
                                                            'petal %s details' % which, sil=sil, vkind=CK.vertex_kinds(pet))
    # ownership per kind of piece (which pieces lie on / over a seam), every vertex of every part
    co_all, vk_all = [], []
    for name, (m, _) in parts.items():
        co_all += list(m.v)
        vk_all += ['%s:%s' % (name, k) for k in CK.vertex_kinds(m)]
    own = Z.ownership_report(zi, np.array(co_all), 'Z3', kinds=vk_all, sample=1)
    out['ownership_by_kind'] = dict(outside_zone=own['outside_zone'], outside_by_kind=own['outside_by_kind'],
                                    on_seam_with=own['on_seam_with'], within_margin_of=own['within_margin_of'],
                                    keep_clear=own['keep_clear'], verts_tested=own['verts_tested'])
    kinds = {}
    for name, (m, _) in parts.items():
        for k, v in m.tris_by_kind().items():
            kinds[k] = kinds.get(k, 0) + v
    out['tris_by_kind'] = kinds
    tot = sum(kinds.values())
    out['rivet_share'] = round(kinds.get('rivet', 0) / max(1, tot), 3)
    hk = hull.tris_by_kind()
    out['hull_tris_by_kind'] = hk
    out['hull_rivet_share'] = round(hk.get('rivet', 0) / max(1, sum(hk.values())), 3)
    return out


def main():
    o = opts()
    zn = '3'
    coll_name, prefix = 'Detail_Z3', 'SM_AirshipDetail_Z3_'
    report_path = o.get('report') or (DOCS + '/z3_report.json')
    out_blend = o.get('blend-out') or D.zone_blend(zn)
    if o.get('debug'):
        K['debug_dir'] = o['debug']                  # mask dumps and test logs (development only)
    t0 = time.time()
    bpy.ops.wm.open_mainfile(filepath=C.RIG_BLEND)                 # read only: never saved under this name
    ship = S.Ship(bpy)
    mats = D.ensure_materials()
    zi = Z.ZoneIndex(ship)
    be_rep = {}
    deleted = BE.deleted_mask(ship, 'all', be_rep)
    log = {}
    parts = build(ship, zi, deleted, K, log)
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
    coll = bpy.data.collections.get(coll_name) or bpy.data.collections.new(coll_name)
    if coll.name not in [c.name for c in bpy.context.scene.collection.children]:
        bpy.context.scene.collection.children.link(coll)
    objs = []
    for name, (m, bone) in parts.items():
        if not m.f:
            continue
        objs.append(m.to_object(prefix + name, coll, mats, arm=ship.arm, groups=bone if bone else list(m.g)))
    cont = {k[6:]: v.pop('continuity', None) for k, v in log.items() if k.startswith('flank_')}
    C.dump_json(cont, DOCS + '/z3_continuity.json')
    rep = dict(zone=ZONE, knobs=K, log=log, base_edits=be_rep,
               tris={ob.name: int(sum(len(p.vertices) - 2 for p in ob.data.polygons)) for ob in objs},
               objects=[CK.object_report(ob, ZONE) for ob in objs],
               zone_checks=CK.zone_checks(objs, ZONE, ship, zi, sample=2) if objs else None,
               checks=checks(ship, parts, objs, zi, K, log),
               seconds=round(time.time() - t0, 1))
    rep['tris_total'] = sum(rep['tris'].values())
    rep['all_objects_ok'] = all(r['ok'] for r in rep['objects'])
    C.dump_json(rep, report_path)
    print('[Z3] tris', rep['tris'], 'total', rep['tris_total'])
    print('[Z3] objects ok', rep['all_objects_ok'], json.dumps([{k: r[k] for k in ('object', 'ok', 'inside_out_pieces',
          'nonmanifold_edges', 'not_rigid_vertices', 'faces_without_role')} for r in rep['objects']]))
    print('[Z3] zone checks', json.dumps(rep['zone_checks'])[:2500])
    for side in ('port', 'stbd'):
        lg = log['flank_' + side]
        print('[Z3] flank', side, json.dumps({k: lg.get(k) for k in ('ref_at_seam', 'end_rib', 'upper_end_rib', 'strake_runs',
              'pipe_spans', 'bays', 'upper_bays', 'plates', 'layers', 'strake', 'teeth', 'gussets', 'pipes', 'bays_built',
              'conduits', 'through_hull_fittings', 'mask_filtered_up', 'mask_filtered_low', 'skipped_on_step',
              'end_rib_v', 'upper_end_rib_v', 'end_rib_failed')}))
    for which in ('RL', 'RR'):
        print('[Z3] pod', which, json.dumps(log['pod_' + which])[:800])
        print('[Z3] pocket', which, json.dumps(log.get('pocket_' + which)), json.dumps(log.get('pocket_%s_wall' % which)))
    print('[Z3] floating', dropped, 'flipped', flipped)
    print('[Z3] checks', json.dumps({k: v for k, v in rep['checks'].items() if 'tris_by_kind' not in k})[:3000])
    print('[Z3] report', report_path)
    if not o.get('no-save'):
        print('[Z3] saved', D.safe_save(out_blend))
    print('[Z3] done %.1f s' % (time.time() - t0))
    sys.stdout.flush()


if __name__ == '__main__':
    main()
