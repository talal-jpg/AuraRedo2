"""TEMPLATE for one zone of the airship detail pass (round 3). Copy it to detail_zN.py, set ZONE, replace build().

  blender_capped.sh --python detail_zN.py [-- --no-save] [--blend-out FILE]      (about 10-60 s)

The minimal flow every zone follows (ZONES.md, section 'Per-zone checklist'):
  1. open rig/AirshipRig.blend READ ONLY (never saved), detail_ship.Ship, the zone map (detail_zones.ZoneIndex) and the
     faces the registered base edits remove (detail_base_edits.deleted_mask: treat them as absent, never edit them)
  2. build(): fill one detail_common.Mesh per bone (seeded rng only). Flank zones call detail_flank.Flank(side) +
     build_flank(); pod zones call detail_pod.pocket_rim / cavity / build_pod(which=...); everything else uses the
     generators of detail_common on a target surface. Start the knobs from zone 1's (approved density):
     K = copy.deepcopy(detail_zone1.K), then change what the zone needs.
  3. drop_floating (every piece touches the ship or another piece) and orient_outward (no inside-out pieces)
  4. objects SM_AirshipDetail_ZN_<Part> in collection Detail_ZN, parented to 'Armature' with an Armature modifier,
     every vertex 100 % on one bone, every face a role material (DM_*)
  5. checks -> Docs/Airship/round3/zN_report.json (+ zN_continuity.json when build_flank ran)
  6. D.safe_save(rig/detail/zones/AirshipRig_detail_zN.blend) (refuses any other place)
Then, by hand (commands in ZONES.md): detail_rigcheck.py (--only Detail_ZN, the moving sets near the zone), renders
with detail_render.py (--blend your file --zones 1,<done zones>, toon = final look, before / after) into
Docs/Airship/round3/media/zN/, look at every render, write Docs/Airship/round3/ZONE_N.md.

The demo build() below puts one riveted plate on the ship at the zone's ANCHOR, to prove the flow end to end:
  blender_capped.sh --python detail_zone_template.py -- --zone Z2 --no-save
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

ZONE = 'Z0'                                  # set: 'Z2' .. 'Z7'
DOCS = '/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/round3'
K = dict(seed=1300, touch_tol=0.02,
         plate=dict(gap=0.015, t=0.045, bevel=0.014),            # zone 1's base plate (1.5 cm skin gap, 4.5 cm thick)
         rivet=dict(r=0.022, h=0.012, inset=0.07, spacing=0.28))  # zone 1's low domed rivets
# demo anchors: a ray (origin, direction) that hits the ship inside each zone
ANCHOR = {'Z0': ((-4.0, -20.0, 0.5), (0, 1, 0)), 'Z2': ((-4.0, -20.0, 0.5), (0, 1, 0)),
          'Z3': ((-13.5, 20.0, 0.8), (0, -1, 0)), 'Z4': ((11.0, 20.0, 0.6), (0, -1, 0)),
          'Z5': ((-3.0, 2.0, -20.0), (0, 0, 1)), 'Z6': ((-40.0, 1.6, 0.0), (1, 0, 0)),
          'Z7': ((18.0, 20.0, 6.1), (0, -1, 0))}


def opts():
    a = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    o = {}
    for i, k in enumerate(a):
        if k.startswith('--'):
            o[k[2:]] = a[i + 1] if i + 1 < len(a) and not a[i + 1].startswith('--') else True
    return o


def surface_fn_at(surf, p, n, u_hint=(1.0, 0.0, 0.0)):
    """(u, v) -> (point, smooth normal) on `surf` (detail_common.Surface) round the point p: rays along -n from a
    plane 0.5 m above p (u, v in metres in that plane)"""
    u, v, n = D.ortho_frame(n, u_hint)
    o = np.asarray(p) + n * 0.5

    def f(a, b):
        r = surf.ray(o + u * a + v * b, -n, 1.5)
        return None if r is None else (r[0], r[1])
    return f


def build(ship, zi, deleted, K, rng, log):
    """REPLACE in a real zone. Returns {part name: (Mesh, bone name or None = per-vertex groups in mesh.g)}"""
    surf = ship.surface(~deleted)
    o, d = ANCHOR.get(ZONE, ANCHOR['Z0'])
    hit = surf.ray(o, d, 60.0)
    hull = D.Mesh('hull'); hull.cur_group = 'Hull'
    if hit is None:
        log['demo'] = 'anchor ray missed'
        return {'Hull': (hull, 'Hull')}
    p, n = hit[0], hit[1]
    log['demo_anchor'] = dict(point=[round(float(x), 3) for x in p], owner=zi.zone_at(p))
    f = surface_fn_at(surf, p, n)
    PL, R = K['plate'], K['rivet']
    W, H = 0.6, 0.4
    g = lambda u, v: f(u - W / 2, v - H / 2)
    us, vs = D.grid_coords(0.0, W, 0.3), D.grid_coords(0.0, H, 0.2)
    top, ok = D.solid_plate(hull, g, us, vs, PL['gap'], PL['t'], PL['bevel'], 'paint_yellow', kind='plate')
    if ok:
        D.rivet_row(hull, top, D.corner_pts(us, vs, R['inset']), r=R['r'], h=R['h'])
    log['demo_plate'] = bool(ok)
    return {'Hull': (hull, 'Hull')}


def main():
    o = opts()
    global ZONE
    ZONE = o.get('zone', ZONE)
    zn = ZONE.upper().lstrip('Z')
    coll_name, prefix = 'Detail_Z' + zn, 'SM_AirshipDetail_Z%s_' % zn
    report_path = o.get('report') or (DOCS + '/z%s_report.json' % zn)
    out_blend = o.get('blend-out') or D.zone_blend(zn)
    t0 = time.time()
    bpy.ops.wm.open_mainfile(filepath=C.RIG_BLEND)                 # read only: never saved under this name
    ship = S.Ship(bpy)
    mats = D.ensure_materials()
    zi = Z.ZoneIndex(ship)
    be_rep = {}
    deleted = BE.deleted_mask(ship, 'all', be_rep)
    log = {}
    parts = build(ship, zi, deleted, K, random.Random(K['seed']), log)
    # every loose piece touches the ship (minus deleted faces) or another piece; no piece inside out
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
    cont = log.pop('continuity', None)
    if cont is not None:
        C.dump_json(cont, DOCS + '/z%s_continuity.json' % zn)
    rep = dict(zone=ZONE, knobs=K, log=log, base_edits=be_rep,
               tris={ob.name: int(sum(len(p.vertices) - 2 for p in ob.data.polygons)) for ob in objs},
               objects=[CK.object_report(ob, ZONE) for ob in objs],
               zone_checks=CK.zone_checks(objs, ZONE, ship, zi) if objs else None,
               seconds=round(time.time() - t0, 1))
    rep['tris_total'] = sum(rep['tris'].values())
    rep['all_objects_ok'] = all(r['ok'] for r in rep['objects'])
    C.dump_json(rep, report_path)
    print('[%s] tris' % ZONE, rep['tris'], 'total', rep['tris_total'])
    print('[%s] objects ok' % ZONE, rep['all_objects_ok'], json.dumps([{k: r[k] for k in ('object', 'ok', 'inside_out_pieces',
          'nonmanifold_edges', 'not_rigid_vertices', 'faces_without_role')} for r in rep['objects']]))
    print('[%s] zone checks' % ZONE, json.dumps(rep['zone_checks'])[:1500])
    print('[%s] log' % ZONE, json.dumps(log)[:1500])
    print('[%s] report' % ZONE, report_path)
    if not o.get('no-save'):
        print('[%s] saved' % ZONE, D.safe_save(out_blend))
    print('[%s] done %.1f s' % (ZONE, time.time() - t0))
    sys.stdout.flush()


if __name__ == '__main__':
    main()
