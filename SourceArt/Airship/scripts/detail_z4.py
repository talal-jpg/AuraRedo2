"""Zone 4 of the airship detail pass (round 3, 2026-11-28): the BOW.

Z4 (detail_zones.py) = everything forward of x 6.95 below the gantry: both hull flanks forward of the FL / FR pocket
rims, the bow wedge (BowWedge), the keel block under the bow (Underside_Front) and the belly tabs there. Zone 1's
approved language and density (detail_zone1.K), continued forward; reference 1's bow (crop_bow.png): heavy rust
armour plates, a riveted strake, big bolted blocks, the teeth line continuing from zone 1.

  blender_capped.sh --python detail_z4.py [-- --no-save] [--blend-out FILE] [--report FILE]

Opens rig/AirshipRig.blend READ ONLY, builds collection Detail_Z4 and saves rig/detail/zones/AirshipRig_detail_z4.blend
(detail_common.safe_save). The finished zones' details (1, 2, 3, 6, 7) are appended only to be obstacles and are
removed again before the save; Z5 (built after Z4, and it loads Z4) is only cross-checked, report only. Report: Docs/Airship/round3/z4_report.json (+ z4_continuity.json).

Objects (parent Armature, Armature modifier, every vertex 100 % on the Hull bone):
  SM_AirshipDetail_Z4_Hull     bow flanks (port + starboard): upper rows, gussets, strake + teeth, lower rows,
                               conduits; rivets on the ship's own belly tabs
  SM_AirshipDetail_Z4_Wedge    the bow wedge: plates in two rust tones, angle irons over the creases, straps,
                               bolted blocks, two machinery bays on the bottom
  SM_AirshipDetail_Z4_Keel     the keel block under the bow: grey plates on fitted patches, rust straps, keel angle
Modules: detail_z4_lib.py (masks on faces, zone 1's layering as a function, angle irons, blocks, bays),
detail_z4_flank.py (bow flank), detail_z4_wedge.py (wedge, keel block, tabs). Shared modules are only imported.
"""
import bpy, sys, os, math, random, json, time, copy
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from mathutils import Vector as V
from mathutils.bvhtree import BVHTree
import rig_common as C
import detail_common as D
import detail_ship as S
import detail_zones as Z
import detail_checks as CK
import detail_base_edits as BE
import detail_zone1 as Z1
from detail_z4_flank import BowFlank, build_bow_flank
from detail_z4_wedge import build_wedge, build_keel, tab_rivets, Keep
from detail_z4_lib import drop_intersecting

ZONE = 'Z4'
DOCS = '/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/round3'
# finished zones only: Z5 is built after Z4 and itself loads Z4 as an obstacle, so Z4 must not depend on Z5's file
# (that would make the two builds circular and Z4's hash change with every Z5 rebuild). The Z5 seam is checked after
# the fact (z4_report.json -> log.z5_crosscheck).
OTHER_ZONES = ('1', '2', '3', '6', '7')
CROSSCHECK_ZONES = ('5',)

# ------------------------------------------------------------------ knobs: zone 1's (approved density) + the bow's
K = copy.deepcopy(Z1.K)
K.update(
    seed=1304,
    x_aft=7.05, x_fwd_plates=15.45,          # 10 cm from the Z1 / Z2 seam (x 6.95) to the wedge's aft face (x 15.5)
    chart_x=(6.8, 15.7, 0.05), chart_phi=(60.0, -85.0, -0.5),  # up to 60 deg: the deck edge where the hull narrows
    bilge_phi=-84.0,                          # Z4 owns the bow down to the keel block (no bilge line forward of 6.95)
)
K['z4'] = dict(
    gusset_x0=-11.20,                         # zone 1's gusset grid x = -11.20 + 0.51 k (7.16, 7.67, ...)
    flank_slots=2,
    flank_frame_min=(0.75, 0.5),              # picture frames only on the bigger flank plates (small ones read as hatches)
    conduit_min_strip=0.42,                   # the conduit pair only where the strip under the gunwale band is this tall
    end_rib=dict(w=0.18, t=0.11),             # riveted rust rib each strake run ends on (12.5 cm off the skin)
    seam_clear=0.10,                          # flank cells within this of zone 1 / 2 / 5 details stay free (seam rule)
    teeth_min=0.36,                           # shortest tooth where the strip under the band narrows (zone 1: 0.62-0.78)
    seam=dict(port=dict(file=DOCS + '/z1_continuity.json', fallback=1.0562),
              stbd=dict(file=DOCS + '/z2_continuity.json', fallback=1.0165)),
    angle=dict(leg=0.13, t=0.032, mat='dark_metal'),   # angle irons over the wedge's creases
    strap_w=0.2, keel_w=0.3,
    wedge_rows=dict(w=(1.2, 2.4), row_h=(0.75, 1.1), min_w=0.5, min_h=0.34, keep=0.3),
    wedge_fill=dict(w=(0.6, 1.1), h=(0.45, 0.75), min_w=0.5, min_h=0.4),
    wedge_mats=(('rust_red', 0.55), ('rust_dark', 0.45)),
    wedge_slots=dict(side=1, lowch=0, bottom=1, front=2, aft=0),
    # big bolted blocks: (panel, preferred centre as fractions of (Lu, Lv), (w, h, d)); the nearest free place is used
    blocks=[('lowch0_P', (0.2, 0.5), (0.5, 0.42, 0.17)), ('lowch2_P', (0.6, 0.5), (0.42, 0.36, 0.16)),
            ('lowch0_S', (0.2, 0.5), (0.5, 0.42, 0.17)), ('lowch2_S', (0.6, 0.5), (0.42, 0.36, 0.16)),
            ('side_P', (0.97, 0.22), (0.4, 0.34, 0.15)), ('side_S', (0.97, 0.22), (0.4, 0.34, 0.15)),
            ('front', (0.14, 0.8), (0.46, 0.4, 0.16)), ('front', (0.88, 0.22), (0.36, 0.32, 0.14)),
            ('bottom', (0.05, 0.12), (0.5, 0.42, 0.17)), ('bottom', (0.05, 0.88), (0.5, 0.42, 0.17)),
            ('bottom', (0.95, 0.25), (0.42, 0.36, 0.15)), ('bottom', (0.95, 0.75), (0.42, 0.36, 0.15))],
    # machinery bays: (panel, preferred top-left as fractions of (Lu, Lv), W, H)
    wedge_bays=[('bottom', 0.37, 0.07, 1.9, 1.3), ('bottom', 0.12, 0.68, 1.8, 1.25), ('bottom', 0.7, 0.64, 1.8, 1.2),
                ('side_P', 0.08, 0.45, 1.9, 1.0), ('side_S', 0.08, 0.45, 1.9, 1.0)],
    bottom_channels=[(0.035, 0.965, 0.355)],  # (u0, u1, v0) fractions of the wedge bottom: one channel, port of the keel strap
    side_conduit=dict(v=0.23, off=0.106),     # conduit pair under the wedge's top angle, riding over the gussets
    keepout_boxes=[],
    chain_margin=0.22,                        # ChainFwd (swing -1 .. +3 deg) beside the starboard side: keep 22 cm off its links
    keel_rows=dict(w=(0.9, 1.7), row_h=(0.6, 0.95), min_w=0.45, min_h=0.3, keep=0.3),
    keel_fill=dict(w=(0.5, 0.9), h=(0.4, 0.65), min_w=0.45, min_h=0.36),
    keel_mats=(('machinery', 0.65), ('dark_metal', 0.35)),
    keel_max_res=0.06,
    rivet_min_area=0.25,                      # wedge / keel: corner rivets on plates of 0.25 m2 and up (zone 1: 0.12)
    keel_strap_u=(0.2, 0.45, 0.7),
    keel_block_at=[(0.08, 0.55), (0.1, 0.4), (0.12, 0.7)],
    keel_pipe=dict(v=0.62, r=0.055, u=(0.5, 0.7), off=0.07,   # copper pipe 0.62 m out from the keel angle, over the straps
                   x_max=dict(P=10.75, S=99.0)),               # port: ends before the oval dent (x 11 .. 13.4)
    keel_bay=None,                            # (no bay on the lumpy keel block: no patch calm enough for one)
    # ---- look-and-fix pass (2026-11-28, after the first renders)
    # bow flank: the gaps round the ship's own rust plates filled with many small yellow scraps (a mosaic); fillers
    # now at least 0.5 x 0.38 m, the rest stays calm
    flank_fill=dict(w=(0.5, 0.9), h=(0.38, 0.6), min_w=0.5, min_h=0.38, mats=(('paint_yellow', 0.5), ('paint_ochre', 0.5))),
    # bolted blocks: one solid stepped rust lump. A dark cap in a grey body read as a framed window, and a grey cap
    # on a dark flange read as a screen (tried both): dark rust body and cap on a flange in the wedge's own rust; rust
    # on the grey keel
    block_mats=dict(body='rust_dark', base='rust_red', cap='rust_dark'),
    keel_block_mats=dict(body='rust_red', base='rust_red', cap='rust_red'),
)
# keel plates: mostly the keel's own grey (machinery), fewer dark ones (dark rectangles on the grey keel read as
# hatches from below)
K['z4']['keel_mats'] = (('machinery', 0.75), ('dark_metal', 0.25))
# review fix 2026-11-28: the keel block read as a grey sticker collage with short rust straps that start and end
# nowhere. More rust armour like the wedge, few dark plates; three wrap bands at even spacing that each run on from the
# keel angle as one band (joints only, no stray pieces)
K['z4']['keel_mats'] = (('rust_dark', 0.4), ('rust_red', 0.2), ('machinery', 0.32), ('dark_metal', 0.08))
K['z4']['keel_strap_u'] = (0.22, 0.5, 0.78)
K['z4']['keel_strap_continuous'] = True
K['slots'] = dict(K['slots'])


def opts():
    a = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    o = {}
    for i, k in enumerate(a):
        if k.startswith('--'):
            o[k[2:]] = a[i + 1] if i + 1 < len(a) and not a[i + 1].startswith('--') else True
    return o


def other_zone_bvhs(arm, zones=OTHER_ZONES):
    """append the other zones' details, one BVH per zone (rest pose world space), then remove them from this file"""
    out, info = {}, {}
    for z in zones:
        coll = D.append_zone(z, arm)
        if coll is None:
            info['Z' + z] = 'not built yet'
            continue
        objs = [o for o in coll.all_objects if o.type == 'MESH']
        bvh, co, tri = D.bvh_from_objects(objs)
        out['Z' + z] = bvh
        info['Z' + z] = dict(objects=len(objs), tris=int(len(tri)))
        meshes = [o.data for o in objs]
        for o in list(coll.all_objects):
            bpy.data.objects.remove(o, do_unlink=True)
        for m in meshes:
            if m.users == 0:
                bpy.data.meshes.remove(m)
        bpy.data.collections.remove(coll)
    return out, info


def seam_ref(cfg):
    try:
        d = json.load(open(cfg['file']))
        v = [x for x in d['ref_up'] if x is not None][-1]
        return dict(ref_up=float(v), source=os.path.basename(cfg['file']) + ' ref_up at x %.2f' % d['xs'][-1])
    except Exception as e:
        return dict(ref_up=cfg['fallback'], source='fallback (%s)' % e)


def drop_pa(mesh, keep):
    """remove every loose piece with a vertex above a PA_Airship box top inside its footprint (walkable rule)"""
    if not mesh.f:
        return {}
    fc, vc = mesh.components()
    bad = {int(vc[i]) for i, p in enumerate(mesh.v) if keep.pa_bad(p)}
    drop = [i for i in range(len(mesh.f)) if int(fc[i]) in bad]
    kinds = {}
    for c in bad:
        k = next((mesh.k[i] for i in range(len(mesh.f)) if int(fc[i]) == c), '?')
        kinds[k] = kinds.get(k, 0) + 1
    if drop:
        mesh.drop_faces(drop)
    return kinds


def build(ship, deleted, K, log, zbvh, keep):
    parts = {}
    hull = D.Mesh('hull'); hull.cur_group = 'Hull'
    t0 = time.time()
    for side, sname, bu, bl in ((1, 'port', [414], [416]), (-1, 'stbd', [415], [418])):
        fl = BowFlank(ship, K, side, (ship.p_island != S.SKIN) & ~deleted, bu, bl)
        seam = seam_ref(K['z4']['seam'][sname])
        build_bow_flank(hull, fl, ship, K, random.Random(K['seed'] + (11 if side > 0 else 21)), log.setdefault(
            'flank_' + sname, {}), seam, nbvh=[zbvh[z] for z in ('Z1', 'Z2', 'Z5') if z in zbvh])
    tab_rivets(hull, ship, K, log)
    log['t_flank'] = round(time.time() - t0, 1)
    parts['Hull'] = (hull, 'Hull')
    wedge = D.Mesh('wedge'); wedge.cur_group = 'Hull'
    obst_all = list(zbvh.values())
    build_wedge(wedge, ship, K, random.Random(K['seed'] + 31), log.setdefault('wedge', {}), obst_all, deleted, keep)
    log['t_wedge'] = round(time.time() - t0, 1)
    parts['Wedge'] = (wedge, 'Hull')
    keel = D.Mesh('keel'); keel.cur_group = 'Hull'
    build_keel(keel, ship, K, random.Random(K['seed'] + 41), log.setdefault('keel', {}), obst_all, deleted, keep)
    log['t_keel'] = round(time.time() - t0, 1)
    parts['Keel'] = (keel, 'Hull')
    return parts


def silhouette_by_kind(parts, surf, limit=0.20):
    """per part and kind: the largest distance of a detail vertex from the ship (any SM_Airship face) and how many
    vertices lie over the 20 cm silhouette limit"""
    out = {}
    for name, (m, _) in parts.items():
        if not m.v:
            continue
        vk = [''] * len(m.v)
        for f, k in zip(m.f, m.k):
            for i in f:
                vk[i] = k
        P = np.asarray(m.v)
        d = np.array([(lambda r: 99.0 if r is None else r[3])(surf.nearest(p, 1.0)) for p in P])
        rec = {}
        for k in sorted(set(vk)):
            sel = np.array([x == k for x in vk])
            rec[k] = dict(max_m=round(float(d[sel].max()), 3), over=int((d[sel] > limit).sum()))
        out[name] = dict(p99_m=round(float(np.percentile(d, 99)), 3), max_m=round(float(d.max()), 3),
                         over=int((d > limit).sum()), by_kind={k: v for k, v in rec.items() if v['max_m'] > 0.17})
    return out


def kinds_summary(parts):
    out = {}
    for name, (m, _) in parts.items():
        for k, v in m.tris_by_kind().items():
            out[k] = out.get(k, 0) + v
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def main():
    o = opts()
    zn = '4'
    coll_name, prefix = 'Detail_Z4', 'SM_AirshipDetail_Z4_'
    report_path = o.get('report') or (DOCS + '/z4_report.json')
    out_blend = o.get('blend-out') or D.zone_blend(zn)
    t0 = time.time()
    bpy.ops.wm.open_mainfile(filepath=C.RIG_BLEND)                 # read only: never saved under this name
    ship = S.Ship(bpy)
    mats = D.ensure_materials()
    zbvh, zinfo = other_zone_bvhs(ship.arm)
    zi = Z.ZoneIndex(ship)
    be_rep = {}
    deleted = BE.deleted_mask(ship, 'all', be_rep)
    keep = Keep(K, near=[(ship.bvh(ship.p_bone == 'ChainFwd'), K['z4']['chain_margin'])])
    log = dict(other_zones=zinfo)
    parts = build(ship, deleted, K, log, zbvh, keep)
    # nothing of ours may cut into another zone's details; nothing above a walkable top; every loose piece touches
    # the ship or another piece; no piece inside out
    ship_bvh = ship.bvh(~deleted)
    dropped, crossed, pa_dropped, flipped = {}, {}, {}, {}
    for name, (m, _) in parts.items():
        crossed[name] = drop_intersecting(m, zbvh, where=log.setdefault('crossed_where', []))
        pa_dropped[name] = drop_pa(m, keep)
        for _ in range(4):
            dd = D.drop_floating(m, [ship_bvh], tol=K['touch_tol'])
            if not dd:
                break
            for k_, v_ in dd.items():
                dropped.setdefault(name, {})[k_] = dropped.get(name, {}).get(k_, 0) + v_
        flipped[name] = m.orient_outward()
    log['pieces_removed_crossing_other_zones'] = crossed
    log['pieces_removed_above_pa_tops'] = pa_dropped
    log['floating_pieces_removed'] = dropped
    log['inside_out_pieces_flipped'] = flipped
    # report only: zones still in progress (Z5) -- pieces of ours that would intersect their current file
    xb, xinfo = other_zone_bvhs(ship.arm, CROSSCHECK_ZONES)
    xc = dict(zones=xinfo, intersecting_pieces={})
    for name, (m, _) in parts.items():
        if not m.f or not xb:
            continue
        fc, _ = m.components()
        det = BVHTree.FromPolygons(m.v, [list(f) for f in m.f])
        for zn_, b in xb.items():
            hit = {}
            for (i, _) in det.overlap(b):
                hit.setdefault(int(fc[i]), (m.k[i], [round(float(c), 2) for c in np.mean([m.v[j] for j in m.f[i]], 0)]))
            if hit:
                xc['intersecting_pieces'].setdefault(zn_, {})[name] = sorted(hit.values())[:20]
    log['z5_crosscheck'] = xc
    kinds = kinds_summary(parts)
    log['silhouette_by_kind'] = silhouette_by_kind(parts, ship.surface(np.ones(len(ship.polys), bool)))
    coll = bpy.data.collections.get(coll_name) or bpy.data.collections.new(coll_name)
    if coll.name not in [c.name for c in bpy.context.scene.collection.children]:
        bpy.context.scene.collection.children.link(coll)
    objs = []
    for name, (m, bone) in parts.items():
        if not m.f:
            continue
        objs.append(m.to_object(prefix + name, coll, mats, arm=ship.arm, groups=bone if bone else list(m.g)))
    cont = {}
    for sname in ('flank_port', 'flank_stbd'):
        c = log.get(sname, {}).pop('continuity', None)
        if c:
            cont.update(c)
    if cont:
        C.dump_json(cont, DOCS + '/z4_continuity.json')
    tris = {ob.name: int(sum(len(p.vertices) - 2 for p in ob.data.polygons)) for ob in objs}
    rep = dict(zone=ZONE, knobs=K, log=log, base_edits=be_rep, tris=tris, tris_by_kind=kinds,
               objects=[CK.object_report(ob, ZONE) for ob in objs],
               zone_checks=CK.zone_checks(objs, ZONE, ship, zi, sample=2) if objs else None,
               seconds=round(time.time() - t0, 1))
    rep['tris_total'] = sum(tris.values())
    rep['rivet_share'] = round(kinds.get('rivet', 0) / max(1, rep['tris_total']), 3)
    rep['all_objects_ok'] = all(r['ok'] for r in rep['objects'])
    C.dump_json(rep, report_path)
    print('[Z4] tris', tris, 'total', rep['tris_total'], 'rivet share', rep['rivet_share'])
    print('[Z4] kinds', kinds)
    print('[Z4] objects ok', rep['all_objects_ok'], json.dumps([{k: r[k] for k in ('object', 'ok', 'inside_out_pieces',
          'nonmanifold_edges', 'not_rigid_vertices', 'faces_without_role')} for r in rep['objects']]))
    print('[Z4] zone checks', json.dumps(rep['zone_checks'])[:2500])
    print('[Z4] silhouette', json.dumps(log['silhouette_by_kind']))
    print('[Z4] removed', json.dumps(dict(crossed=crossed, pa=pa_dropped, floating=dropped, flipped=flipped)))
    lay = {}
    for sec in ('flank_port', 'flank_stbd', 'wedge', 'keel'):
        lay.update(log.get(sec, {}).get('layers', {}))
    print('[Z4] layers', json.dumps(lay))
    for sec in ('flank_port', 'flank_stbd'):
        s = log.get(sec, {})
        print('[Z4] %s' % sec, json.dumps({k: s.get(k) for k in ('flank_free_m2', 'strake_runs', 'strake', 'teeth',
                                                                   'gussets', 'conduits', 'pipe_spans', 'skipped_on_step')}))
    w = log.get('wedge', {})
    print('[Z4] wedge', json.dumps({k: w.get(k) for k in ('wedge_free_m2', 'wedge_bays', 'bays_skipped', 'wedge_blocks',
                                                          'skipped_on_step')})[:2500])
    kl = log.get('keel', {})
    print('[Z4] keel', json.dumps({k: kl.get(k) for k in ('keel_free_m2', 'keel_angle_segments', 'keel_straps',
                                                          'skipped_lumpy')}))
    print('[Z4] report', report_path)
    if not o.get('no-save'):
        print('[Z4] saved', D.safe_save(out_blend))
    print('[Z4] done %.1f s' % (time.time() - t0))
    sys.stdout.flush()


if __name__ == '__main__':
    main()
