"""Zone 6 of the airship detail pass (round 3, 2026-11-28): the stern and the two big side fans, with the OPEN FAN
BACKS (Talal's answer 4: "remove the back of the fans so that they are visible from back").

  blender_capped.sh --python detail_z6.py [-- --no-save] [--blend-out FILE] [--report FILE]      (about 1 min)

Opens rig/AirshipRig.blend READ ONLY (never saved), treats the faces of base_edits/z6.json (the duct back wall and the
big tail cone of each fan, whole islands) as gone, builds the zone's details and saves
rig/detail/zones/AirshipRig_detail_z6.blend (collection Detail_Z6) through detail_common.safe_save.

Objects (parent 'Armature', Armature modifier, every vertex 100 % on one bone):
  SM_AirshipDetail_Z6_Hull        Hull               transom, the transom's raised panels, fan mount pylons and struts
  SM_AirshipDetail_Z6_Turbine_L   Turbine_L          port fan housing: plating, bays, exhaust rim, liner, stator spider
  SM_AirshipDetail_Z6_Turbine_R   Turbine_R          starboard fan housing (same, own seed)
  SM_AirshipDetail_Z6_Rotor_L/_R  Turbine_X_Rotor    riveted tail cap on the hub; blade-root collar ring, a cuff per
                                                     slat, a steel tip cap per slat end (Talal 2026-11-28, K['rotor'])
  SM_AirshipDetail_Z6_Rod_L/_R    Turbine_X_Rod      collar and plumb weight on the hanging rod
  SM_AirshipDetail_Z6_Rudder      Rudder             edge band, frame ribs, plates, layers, tiller clamps
Modules: detail_z6_fan.py (fans), detail_z6_stern.py (transom, mounts, rudder), detail_z6_lib.py (poses, tests).
Every piece is checked against the moving parts it can meet before it is kept (fan yaw +-12, rotor spin, rod swing
+-20, rudder +-30, the PA_Airship walkable box tops); detail_rigcheck.py then checks the result independently.
"""
import bpy, sys, os, math, random, json, time, copy
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np
from mathutils import Vector as V
import rig_common as C
import detail_common as D
import detail_ship as S
import detail_zones as Z
import detail_checks as CK
import detail_base_edits as BE
import detail_z6_lib as L
import detail_z6_fan as F
import detail_z6_stern as ST

ZONE = 'Z6'
DOCS = '/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/round3'
COLL, PREFIX = 'Detail_Z6', 'SM_AirshipDetail_Z6_'

K = dict(
    seed=1306, touch_tol=0.02, layer=0.006, seam=0.024,
    plate=dict(gap=0.015, t=0.045, bevel=0.014, cut=(0.07, 0.15), cut_p=0.3),     # zone 1's base plate
    rivet=dict(r=0.022, h=0.012, inset=0.07, spacing=0.28),                         # zone 1's low domed rivets
    yellows=(('paint_yellow', 0.5), ('paint_ochre', 0.5)),
    poses=dict(yaw=(-12.0, -8.0, -4.0, 0.0, 4.0, 8.0, 12.0), rudder=tuple(float(a) for a in range(-30, 31, 5)),
               rod=(-20.0, 0.0, 20.0), spin=tuple(float(a) for a in range(0, 360, 15))),
    fan=dict(w=(0.8, 1.5), min_w=0.45, mats=(('paint_orange', 0.7), ('paint_ochre', 0.3)), armour_p=0.14, overlap=0.08,
             batten_p=0.55, batten_w=0.12, frame_p=0.42, frame_edge=0.09, patch_p=0.5,
             patch_mats=(('rust_red', 0.7), ('rust_dark', 0.3)), slots=2, band_seg=1.7,
             bays=((-38.0, 1.45, 'pump'), (46.0, 1.3, 'pair')),
             rim_n=16, rim_rho=(2.95, 3.45), liner_n=10, ring_rivet_step=0.6,
             # review fix 2026-11-28: the two bays per fan read as windows on a tower in the side view (dark floor,
             # dark square lids): ochre floor and machinery-grey lids, so no dark square faces out
             bay_floor='paint_ochre', bay_lid='machinery'),
    stator=dict(n=5, phase=91.0, x=(-18.36, -18.10), t=0.09, collar_r=0.65, hub_r=0.6, hub_x=(-18.56, -17.93),
                tail_x=-18.98, tail_r=0.28),
    transom=dict(w=(1.0, 1.6), row_h=(0.8, 1.5), armour_p=0.12, slots=1, frame_p=0.3, patch_p=0.5, batten_p=0.6,
                 # review fix 2026-11-28: no machinery bays on the transom (two dark square-lidded recesses under the
                 # deck edge read as a face's eyes from the chase camera); a pipe header on the port side and a riser
                 # pair down the starboard outboard column instead (different content per side); narrow columns get
                 # one or two tall plates with a rust rib; nothing smaller than 0.5 x 0.38 m
                 min_w=0.5, min_h=0.38, col_w=0.75, col_split=2.0,
                 # picture frames and slotted plates side by side under the deck edge read as small windows: fewer
                 # of them, frames only on big plates; the long low panel stays plain like the raised panels (the
                 # rudder's swing splits any strap across it into a pair of bars)
                 frame_min_w=1.1, low_panel_strap=False, patch_min_w=0.9, patch_low=True,
                 pipes=dict(port_header=dict(kind='header', strip=(0.95, 2.95, 2.24, 2.76), span=(1.02, 2.86),
                                             runs=((2.60, 0.055, 'copper'), (2.41, 0.045, 'brass')), bonnet=(0, 0, -1)),
                            stbd_riser=dict(kind='riser', strip=(-2.97, -2.56, -1.1, 2.76), span=(-0.95, 2.62),
                                            runs=((-2.84, 0.05, 'copper'), (-2.69, 0.04, 'brass')), bonnet=(0, 1, 0)))),
    # review fix 2026-11-28: 26 similar plates in a grid with 4 ribs read as a panelled cabinet door: fewer, bigger
    # plates, a heavier riveted edge band, 2 ribs, one diagonal brace per face, the slotted plate kept
    rudder=dict(x_cut=-16.75, band=(0.05, 0.25), ribs=(2.75, -1.6), tiller=(1.21, 1.59),
                w=(1.5, 2.3), mats=(('rust_dark', 0.6), ('rust_red', 0.4)), frame_p=0.25, patch_p=0.3,
                tiller_clamps=(-17.6, -19.1), brace=(-1.45, 1.06), force_slot=True),
    # Talal 2026-11-28 ("yes" to a blade-root collar ring and tip caps; the slats stay the base model's). On the rotor
    # bone. Base blades: root face 0.779, tip face 2.747 from the axis (corners 0.79-0.80 / 2.75), hub r 0.82 to
    # x -16.954, blade chord x -17.415 .. -16.90. Duct inner wall: 32-gon, inscribed r 2.7747.
    rotor=dict(blades=True,
               collar=dict(x=(-17.34, -16.88), r_in=0.79, r_out=0.95, ch=0.025, seg=56, mat='rust_red', rivets=28,
                           rivet_r=0.885),
               # machinery grey: a dark cuff on the dark slat only read by its outline (comparison render)
               cuffs=dict(rho=(0.90, 1.04), m_chord=0.02, m_thick=0.015, ch=0.008, mat='machinery'),
               # 'caps' (one per slat end) was chosen over 'shroud' (one band joining the tips): from behind the caps
               # read as a ring of bright tips round the blade disc at 40-75 m and as finished slat ends close up; the
               # thin shroud merged with the duct wall (rig/tmp/r3ans/cmp, FULL.md section 5)
               tips='caps',
               # skip_fwd: the cap starts this far behind the slat's forward edge. The base model's fan-mount pylon
               # passes 2.7 mm (swept) in front of the slat tips at yaw +-12, so a cap round the whole tip would hit
               # it; every rotor piece keeps swept_margin (x, r) from the hull through the yaw range (SweptHull)
               caps=dict(len=0.14, skip_fwd=0.08, m_chord=0.012, m_thick=0.014, ch=0.006, ext=0.012, mat='steel',
                         rivet=True),
               shroud=dict(x=(-17.44, -17.21), r=(2.70, 2.755), ch=0.01, seg=112, mat='steel', rivets=28),
               r_max=2.756, duct_r_min=2.7747, swept_margin=0.01, swept_yaw_step=0.25),
)


def opts():
    a = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    o = {}
    for i, k in enumerate(a):
        if k.startswith('--'):
            o[k[2:]] = a[i + 1] if i + 1 < len(a) and not a[i + 1].startswith('--') else True
    return o


def build(ship, zi, deleted, K, log, t0):
    spec = C.load_json(C.CHECKS + '/bones_spec.json')
    geo = L.ShipGeo(ship, ~deleted)
    boxes = Z.pa_boxes_blender()
    PZ = K['poses']
    pa_fn = ('fn', lambda P: L.pa_bad(P, boxes), 'pa_walkable_top')
    fans = {s: F.Fan(ship, s) for s in ('L', 'R')}
    mount_isl = [i for i, r in ship.islands.items() if r['part'].startswith('FanMount_')]
    # ---- the moving ship parts in their poses (targets for the hull details)
    housing_posed = []
    for s in ('L', 'R'):
        fb = ['Turbine_' + s, 'Turbine_%s_Rotor' % s, 'Turbine_%s_Rod' % s]
        for y in PZ['yaw']:
            housing_posed.append(geo.bvh(geo.mask(bones=fb), L.yaw_M(spec, s, y)))
    rudder_posed = [geo.bvh(geo.mask(bones=['Rudder']), L.rudder_M(spec, a)) for a in PZ['rudder']]
    log['t_posed'] = round(time.time() - t0, 1)

    # ---- hull details first (transom, panels, mounts): they must clear the fans' yaw and the rudder's swing
    hull = L.Part('Hull', 'Hull')
    st_transom = geo.bvh(geo.mask(bones=['Hull'], islands_ex=[S.SKIN]))
    st_mount = geo.bvh(geo.mask(bones=['Hull'], islands_ex=mount_isl))
    CH_T = [('static', st_transom, 'hull_fittings'), ('targets', housing_posed, 'fan_yaw'),
            ('targets', rudder_posed, 'rudder_swing'), pa_fn]
    CH_M = [('static', st_mount, 'hull_or_fittings'), ('targets', housing_posed, 'fan_yaw'),
            ('targets', rudder_posed, 'rudder_swing'), pa_fn]
    tr = ST.Transom(ship, geo)
    log['transom_map'] = [''.join(r) for r in tr.cls[::-3, ::3]]
    ST.build_transom(tr, hull, K, random.Random(K['seed'] + 1), log, CH_T)
    ST.build_mounts(ship, geo, hull, K, random.Random(K['seed'] + 2), log, CH_M)
    log['t_hull'] = round(time.time() - t0, 1)

    # ---- fans: the free map and every piece against the hull (+ the hull details) at every yaw
    hull_all = geo.bvh(geo.mask(bones=['Hull']), extra=[hull.mesh])
    parts = {'Hull': hull}
    for k, s in enumerate(('L', 'R')):
        fan = fans[s]
        hb = 'Turbine_' + s
        obst_mask = geo.mask(bones=[hb], islands_ex=fan.isl['shell'])
        obst = geo.bvh(obst_mask)
        yaw_moves = [(L.yaw_M(spec, s, y), hull_all) for y in PZ['yaw']]
        rod_mask = geo.mask(bones=['Turbine_%s_Rod' % s])
        rod_posed = [geo.bvh(rod_mask, L.rod_M(spec, s, a, b)) for a in PZ['rod'] for b in PZ['rod']]
        fm = F.FanMap(fan, obst, hull_all, [m for m, _ in yaw_moves], rod_posed, boxes)
        log.setdefault('fan_map', {})[s] = dict(cells=int(fm.level.size), free_by_level=[int((fm.level >= i).sum())
                                                                                      for i in range(4)])
        housing = L.Part('Turbine_' + s, hb)
        rotor = L.Part('Rotor_' + s, 'Turbine_%s_Rotor' % s)
        rod = L.Part('Rod_' + s, 'Turbine_%s_Rod' % s)
        CH_H = [('static', obst, 'housing_fittings'), ('moved', yaw_moves, 'hull_at_yaw'),
                ('targets', rod_posed, 'rod_swing'), ('fn', fan.rotor_zone, 'rotor_sweep'), pa_fn]
        obst_nr = geo.bvh(geo.mask(bones=[hb], islands_ex=fan.isl['shell'] + fan.isl['gimbal_ring']))
        CH_HR = [('static', obst_nr, 'housing_fittings')] + CH_H[1:]
        checks = dict(map=fm, housing=CH_H, housing_on_ring=CH_HR, obst_bvh=obst,
                      platform_z=float(ship.island_verts(fan.isl['top_platform'])[:, 2].min()),
                      rod_centre=ship.island_verts(fan.isl['hanging_rod']).mean(0))
        # the housing first; the rotor and rod details are tested once it exists (they move against it)
        F.build_fan(fan, housing, K, random.Random(K['seed'] + 10 + 10 * k), log, checks)
        hous_all = geo.bvh(geo.mask(bones=[hb]), extra=[housing.mesh])
        checks['rotor'] = [('moved', [(L.spin_M(spec, s, a), hous_all) for a in PZ['spin']], 'housing_at_spin')]
        checks['rod'] = [('moved', [(L.rod_M(spec, s, a, b), hous_all) for a in PZ['rod'] for b in PZ['rod']],
                          'housing_at_rod_swing'),
                         ('moved', [(L.yaw_M(spec, s, y) @ L.rod_M(spec, s, a, b), hull_all) for y in PZ['yaw']
                                    for a in PZ['rod'] for b in PZ['rod']], 'hull_at_yaw_and_swing')]
        F.build_rotor_and_rod(fan, rotor, rod, log, checks)
        if K['rotor'].get('blades'):
            r_max = K['rotor']['r_max']
            clear_fn = (lambda fan_, r_max_: (lambda P: (fan_.rad(P) > r_max_ + 1e-6) & (P[:, 0] > -17.9) &
                                                         (P[:, 0] < -16.2)))(fan, r_max)
            checks['rotor_blades'] = checks['rotor'] + [('fn', clear_fn, 'duct_clearance')]
            # the hull side (Hull bone: ship + this zone's hull details) swept through the fan yaw range
            hmask = geo.mask(bones=['Hull'])
            htris = [(p_[0], p_[i], p_[i + 1]) for k_ in np.nonzero(hmask)[0] for p_ in [ship.polys[k_]]
                     for i in range(1, len(p_) - 1)]
            hco = np.asarray(ship.co, float)
            hv = np.asarray(hull.mesh.v, float)
            htris += [(f_[0] + len(hco), f_[i] + len(hco), f_[i + 1] + len(hco)) for f_ in hull.mesh.f
                      for i in range(1, len(f_) - 1)]
            ys_ = np.arange(-12.0, 12.0 + 1e-6, K['rotor']['swept_yaw_step'])
            checks['swept_hull'] = F.SweptHull(fan, np.concatenate([hco, hv]), np.array(htris),
                                               [L.yaw_M(spec, s, y) for y in ys_], margin=K['rotor']['swept_margin'],
                                               pivot=spec['bones']['Turbine_' + s]['head'][:2],
                                               max_yaw=float(np.abs(ys_).max()))
            checks['swept_yaws'] = [float(ys_[0]), float(ys_[-1]), float(K['rotor']['swept_yaw_step'])]
            F.build_rotor_blades(fan, rotor, ship, K, log, checks)
        parts.update({'Turbine_' + s: housing, 'Rotor_' + s: rotor, 'Rod_' + s: rod})
        log['t_fan_' + s] = round(time.time() - t0, 1)

    # ---- rudder: every piece against the hull (+ hull details) at every rudder angle, not into the tiller bar
    rud = L.Part('Rudder', 'Rudder')
    tiller = geo.bvh(geo.mask(islands=[i for i, r in ship.islands.items() if r['part'] == 'Rudder' and r.get('piece') == 'tiller_bar']))
    CH_R = [('moved', [(L.rudder_M(spec, a), hull_all) for a in PZ['rudder']], 'hull_at_rudder_angle'),
            ('static', tiller, 'tiller_bar'), pa_fn]
    CH_RC = [('moved', [(L.rudder_M(spec, a), hull_all) for a in PZ['rudder']], 'hull_at_rudder_angle'), pa_fn]
    ST.build_rudder(ship, rud, K, random.Random(K['seed'] + 40), log, CH_R, CH_RC)
    parts['Rudder'] = rud
    log['t_rudder'] = round(time.time() - t0, 1)
    log['pieces'] = {n: p.stats for n, p in parts.items()}
    return {n: (p.mesh, p.bone) for n, p in parts.items()}


def fan_envelope(objs, ship):
    """how far the housing details stand out of the fan: radial distance from the fan axis vs the shell's own
    largest radius (3.649) and the gimbal ring's (4.361), and the extent behind the duct"""
    out = {}
    for s, side in (('L', 1), ('R', -1)):
        ob = objs.get('Turbine_' + s)
        if ob is None:
            continue
        P = CK.world_co(ob)
        r = np.hypot(P[:, 1] - side * 7.6, P[:, 2] - 1.4)
        shell_part = (P[:, 0] > -18.52) & (P[:, 0] < -15.95) & (r > 3.0)
        out[s] = dict(max_r_on_shell=round(float(r[shell_part].max()), 3) if shell_part.any() else None,
                      shell_r_max=3.649, gimbal_ring_r=4.361,
                      p99_r_on_shell=round(float(np.percentile(r[shell_part], 99)), 3) if shell_part.any() else None,
                      aft_most_x=round(float(P[:, 0].min()), 3), duct_exit_x=-18.758, old_tail_cone_tip_x=-19.906)
    return out


def main():
    o = opts()
    zn = '6'
    if o.get('tips'):                       # comparison builds only (into rig/tmp): --tips shroud
        K['rotor']['tips'] = o['tips']
    report_path = o.get('report') or (DOCS + '/z6_report.json')
    out_blend = o.get('blend-out') or D.zone_blend(zn)
    t0 = time.time()
    bpy.ops.wm.open_mainfile(filepath=C.RIG_BLEND)                 # read only: never saved under this name
    ship = S.Ship(bpy)
    mats = D.ensure_materials()
    zi = Z.ZoneIndex(ship)
    be_rep = {}
    deleted = BE.deleted_mask(ship, 'all', be_rep)
    log = {}
    parts = build(ship, zi, deleted, K, log, t0)
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
    coll = bpy.data.collections.get(COLL) or bpy.data.collections.new(COLL)
    if coll.name not in [c.name for c in bpy.context.scene.collection.children]:
        bpy.context.scene.collection.children.link(coll)
    objs = {}
    kinds = {}
    for name, (m, bone) in parts.items():
        if not m.f:
            continue
        objs[name] = m.to_object(PREFIX + name, coll, mats, arm=ship.arm, groups=bone)
        kinds[name] = m.tris_by_kind()
    olist = list(objs.values())
    tris = {ob.name: int(sum(len(p.vertices) - 2 for p in ob.data.polygons)) for ob in olist}
    rivet_tris = sum(v.get('rivet', 0) for v in kinds.values())
    rep = dict(zone=ZONE, knobs=K, log=log, base_edits=be_rep, tris=tris, tris_total=sum(tris.values()),
               tris_by_kind=kinds, rivet_share=round(rivet_tris / max(1, sum(tris.values())), 3),
               objects=[CK.object_report(ob, ZONE) for ob in olist],
               zone_checks=CK.zone_checks(olist, ZONE, ship, zi) if olist else None,
               fan_envelope=fan_envelope(objs, ship),
               seconds=round(time.time() - t0, 1))
    rep['all_objects_ok'] = all(r['ok'] for r in rep['objects'])
    C.dump_json(rep, report_path)
    print('[Z6] tris', tris, 'total', rep['tris_total'], 'rivet share', rep['rivet_share'])
    print('[Z6] objects ok', rep['all_objects_ok'], json.dumps([{k: r[k] for k in ('object', 'ok', 'inside_out_pieces',
          'nonmanifold_edges', 'not_rigid_vertices', 'faces_without_role')} for r in rep['objects']]))
    print('[Z6] zone checks', json.dumps(rep['zone_checks'])[:2500])
    print('[Z6] envelope', json.dumps(rep['fan_envelope']))
    print('[Z6] blades', json.dumps({s_: log.get('fan_' + s_, {}).get('blades') for s_ in ('L', 'R')}))
    print('[Z6] log', json.dumps({k: v for k, v in log.items() if k != 'transom_map'})[:6000])
    print('[Z6] report', report_path)
    if not o.get('no-save'):
        print('[Z6] saved', D.safe_save(out_blend))
    print('[Z6] done %.1f s' % (time.time() - t0))
    sys.stdout.flush()


if __name__ == '__main__':
    main()
