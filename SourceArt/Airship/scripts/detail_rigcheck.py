"""Rig check for the detail pass (round 3): pose every moving part near the details through its contract range and
count NEW intersections caused by detail geometry; sweep the cannons and the front turrets past the details.

  blender_capped.sh --python detail_rigcheck.py -- --sets pod:FL,cannons [--blend FILE] [--zones 1,2] \
      [--only Detail_Z2] [--base-edits all|none|z6] [--out FILE.json]

Opens --blend (default zone 1's file; never saved), appends --zones (their Detail_ZN collections), applies the base
edits (deleted SM_Airship faces leave the test). "Test" details = the --only collections (default: every Detail_*
collection); other loaded Detail_* collections count like the ship ("context").
Sets (comma list):
  pod:FL|FR|RL|RR   pod pitch / roll {-3, 0, 3}, nozzle pitch / roll {-5, 0, 5}, petal flare {-10, 0, 35}: 243 poses
                    bodies hull / pod / nozzle / petals (RIG_CONTRACT; research_blender.md 3.1/3.2)
  turbine:L|R       yaw {-12, 0, 12} x rotor 0..345 every 15 deg (72 poses) + yaw x rod swing X / Y {-20, 0, 20}
                    (27 poses); bodies hull / housing / rotor / rod
  rudder            RudderDeg -30..30 every 5 (13 poses)
  searchlights      lamp wobble X / Y {-4, 0, 4} x pan 0..345 every 15 (216 poses); bodies hull / posts / heads
  chain             ChainSwingDeg {-1, 0, 3} (its contact limits) x winch spin 0..330 every 30 (36 poses)
  cannons[:L1+L2]   each cannon: yaw {-20, 0, 20} x elevation {-10, 0, 8.75} x recoil {0, 60 cm}: overlaps with the
                    test details and their smallest distance to the swept cannon
  turrets           both front turrets (not rigged: placed like detail_render does) through their yaw range every 10
                    deg x pitch {-20, 0, 40}: overlaps and smallest distance to the test details
For a moving set, overlaps between rigid bodies are counted per pose: NEW = (test details of A vs everything of B) +
(ship / context of A vs test details of B); BASELINE = ship / context vs ship / context (the original model's own
contacts, which the details are judged against). A set passes when no pose has more NEW pairs than the rest pose.
Also reports every test object's skin (each vertex 100 % on one bone), parent and modifiers.
"""
import bpy, sys, os, json, math, itertools, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from mathutils import Vector as V, Matrix
from mathutils.bvhtree import BVHTree
import rig_common as C
import detail_common as D

DETAIL_BLEND = D.zone_blend(1)          # read only; never saved


def opts():
    a = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    o = {}
    for i, k in enumerate(a):
        if k.startswith('--'):
            o[k[2:]] = a[i + 1] if i + 1 < len(a) and not a[i + 1].startswith('--') else True
    return o


def eval_co(ob, dg):
    oe = ob.evaluated_get(dg)
    me = oe.to_mesh()
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get('co', co)
    oe.to_mesh_clear()
    M = np.array(ob.matrix_world)
    return co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3]


def tris_of(ob):
    """(triangles (n, 3) vertex ids, polygon index per triangle)"""
    me = ob.data
    me.calc_loop_triangles()
    t = np.empty(len(me.loop_triangles) * 3, np.int64)
    me.loop_triangles.foreach_get('vertices', t)
    p = np.empty(len(me.loop_triangles), np.int64)
    me.loop_triangles.foreach_get('polygon_index', p)
    return t.reshape(-1, 3), p


def vgroup_names(ob):
    """per-vertex bone name (rigid skin: exactly one group, weight 1.0, checked)"""
    names = {g.index: g.name for g in ob.vertex_groups}
    out = []
    bad = 0
    for v in ob.data.vertices:
        if len(v.groups) != 1 or abs(v.groups[0].weight - 1.0) > 1e-6:
            bad += 1
            out.append(None)
        else:
            out.append(names[v.groups[0].group])
    return np.array(out, dtype=object), bad


# ------------------------------------------------------------------ the moving sets
def pod_set(p, spec):
    B = 'Thruster_' + p
    bodies = {'hull': ['Hull'], 'pod': [B], 'nozzle': [B + '_Nozzle'], 'petals': ['%s_Petal%02d' % (B, k) for k in range(12)]}
    pairs = [('pod', 'hull'), ('nozzle', 'pod'), ('nozzle', 'hull'), ('petals', 'nozzle'), ('petals', 'pod'),
             ('petals', 'hull')]
    P, N, F = (-3.0, 0.0, 3.0), (-5.0, 0.0, 5.0), (-10.0, 0.0, 35.0)
    poses = [{'PodPitchDeg_' + p: a, 'PodRollDeg_' + p: b, 'NozzlePitchDeg_' + p: c, 'NozzleRollDeg_' + p: d,
              'NozzleFlareDeg_' + p: e} for a, b, c, d, e in itertools.product(P, P, N, N, F)]
    return bodies, pairs, poses, [(spec['bones'][B]['head'], 6.5)]


def turbine_set(s, spec):
    B = 'Turbine_' + s
    bodies = {'hull': ['Hull'], 'housing': [B], 'rotor': [B + '_Rotor'], 'rod': [B + '_Rod']}
    pairs = [('housing', 'hull'), ('rotor', 'housing'), ('rotor', 'hull'), ('rod', 'hull'), ('rod', 'rotor')]
    Y = (-12.0, 0.0, 12.0)
    poses = [{'TurbineYawDeg_' + s: y, 'RotorAngleDeg_' + s: float(r)} for y in Y for r in range(0, 360, 15)]
    poses += [{'TurbineYawDeg_' + s: y, 'RodSwingXDeg_' + s: a, 'RodSwingYDeg_' + s: b}
              for y in Y for a in (-20.0, 0.0, 20.0) for b in (-20.0, 0.0, 20.0)]
    return bodies, pairs, poses, [(spec['bones'][B + '_Rotor']['head'], 6.0)]


def rudder_set(spec):
    bodies = {'hull': ['Hull'], 'rudder': ['Rudder']}
    poses = [{'RudderDeg': float(a)} for a in range(-30, 31, 5)]
    return bodies, [('rudder', 'hull')], poses, [(spec['bones']['Rudder']['head'], 7.0)]


def searchlight_set(spec):
    L = ('AftL', 'MidL', 'MidR', 'FwdC')
    bodies = {'hull': ['Hull'], 'posts': ['SearchLight_' + l for l in L], 'heads': ['SearchLight_%s_Head' % l for l in L]}
    pairs = [('heads', 'posts'), ('heads', 'hull'), ('posts', 'hull')]
    poses = [{'LampWobbleXDeg': a, 'LampWobbleYDeg': b, 'SearchLightPanDeg': float(p)}
             for a in (-4.0, 0.0, 4.0) for b in (-4.0, 0.0, 4.0) for p in range(0, 360, 15)]
    near = [(spec['bones']['SearchLight_%s_Head' % l]['head'], 2.5) for l in L] + \
           [(spec['bones']['SearchLight_' + l]['head'], 2.0) for l in L]
    return bodies, pairs, poses, near


def chain_set(spec):
    bodies = {'hull': ['Hull'], 'chain': ['ChainFwd'], 'winches': ['Winch_Fwd', 'Winch_Aft']}
    pairs = [('chain', 'hull'), ('winches', 'hull'), ('chain', 'winches')]
    poses = [{'ChainSwingDeg': c, 'WinchSpinDeg': float(w)} for c in (-1.0, 0.0, 3.0) for w in range(0, 360, 30)]
    return bodies, pairs, poses, [(spec['bones']['ChainFwd']['head'], 6.5), (spec['bones']['Winch_Aft']['head'], 3.5)]


class Scene:
    """the objects under test: ship (minus deleted faces), context details, test details; per triangle: bone, rest
    centre"""

    def __init__(self, ship, deleted, test, context):
        self.items = []                      # (object, kind 'base' | 'test', tris, bone per tri, rest centres)
        for ob, kind in [(ship, 'base')] + [(o, 'base') for o in context] + [(o, 'test') for o in test]:
            names, _ = vgroup_names(ob)
            t, p = tris_of(ob)
            if ob is ship and deleted is not None:
                t = t[~deleted[p]]
            if not len(t):
                continue
            c0 = np.array([v.co[:] for v in ob.data.vertices])
            M = np.array(ob.matrix_world)
            c0 = c0 @ M[:3, :3].T + M[:3, 3]
            self.items.append((ob, kind, t, names[t[:, 0]].astype(str), c0[t].mean(1)))

    def groups(self, bodies, near):
        """{(body, kind): [(object, tris)]} for triangles near the moving set"""
        g = {}
        for ob, kind, t, tb, cen in self.items:
            nm = np.zeros(len(t), bool)
            for (c, r) in near:
                nm |= np.linalg.norm(cen - np.asarray(c), axis=1) < r
            for b, bones in bodies.items():
                m = nm & np.isin(tb, bones)
                if m.any():
                    g.setdefault((b, kind), []).append((ob, t[m]))
        return g


def bvh_of(entries, cache):
    co_all, tri_all, off = [], [], 0
    for ob, tri in entries:
        co = cache[ob.name]
        co_all.append(co)
        tri_all.append(tri + off)
        off += len(co)
    if not co_all:
        return None
    return BVHTree.FromPolygons(np.concatenate(co_all).tolist(), np.concatenate(tri_all).tolist(), all_triangles=True)


def ov(a, b):
    return 0 if (a is None or b is None) else len(a.overlap(b))


def run_set(name, bodies, pairs, poses, near, scn, arm, spec):
    g = scn.groups(bodies, near)
    objs = sorted({ob.name: ob for v in g.values() for ob, _ in v}.values(), key=lambda o: o.name)
    tested = {'%s/%s' % k: int(sum(len(t) for _, t in v)) for k, v in g.items()}

    def check(ctrl):
        C.apply_pose(arm, spec, ctrl)
        dg = bpy.context.evaluated_depsgraph_get()
        dg.update()
        cache = {ob.name: eval_co(ob, dg) for ob in objs}
        bv = {k: bvh_of(v, cache) for k, v in g.items()}
        res = {}
        for a, b in pairs:
            ta, ba = bv.get((a, 'test')), bv.get((a, 'base'))
            tb_, bb = bv.get((b, 'test')), bv.get((b, 'base'))
            res['%s vs %s' % (a, b)] = dict(new=ov(ta, bb) + ov(ta, tb_) + ov(ba, tb_), baseline=ov(ba, bb))
        return res
    t0 = time.time()
    rest = check({})
    worst = {k: dict(new=-1, baseline=-1) for k in rest}
    bad_poses = []
    for ctrl in poses:
        r = check(ctrl)
        for k, v in r.items():
            if v['new'] > worst[k]['new']:
                worst[k]['new'], worst[k]['new_pose'] = v['new'], ctrl
            if v['baseline'] > worst[k]['baseline']:
                worst[k]['baseline'], worst[k]['baseline_pose'] = v['baseline'], ctrl
            if v['new'] > rest[k]['new']:
                bad_poses.append(dict(pair=k, new=v['new'], rest=rest[k]['new'], pose=ctrl))
    C.apply_pose(arm, spec, {})
    return dict(set=name, poses=len(poses), seconds=round(time.time() - t0, 1), triangles_tested=tested, rest=rest,
                worst=worst, new_contacts=len(bad_poses), new_contact_examples=bad_poses[:12],
                passed=len(bad_poses) == 0)


def sweep_props(label, prop_obs, set_pose, poses, test_items, centre, radius=4.0):
    """overlaps and smallest distance between swept prop objects and the test details near them"""
    co_all, tri_all, off = [], [], 0
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    for ob, kind, t, tb, cen in test_items:
        m = np.linalg.norm(cen - np.asarray(centre), axis=1) < radius + 3.0
        if not m.any():
            continue
        co = eval_co(ob, dg)
        co_all.append(co); tri_all.append(t[m] + off); off += len(co)
    if not co_all:
        return dict(label=label, detail_tris_near=0, passed=True)
    dco = np.concatenate(co_all)
    tri = np.concatenate(tri_all)
    dbvh = BVHTree.FromPolygons(dco.tolist(), tri.tolist(), all_triangles=True)
    dpts = dco[np.unique(tri)]
    dpts = dpts[np.linalg.norm(dpts - np.asarray(centre), axis=1) < radius + 1.0]
    best, over, at = 9.0, 0, None
    for ps in poses:
        set_pose(ps)
        dg = bpy.context.evaluated_depsgraph_get()
        dg.update()
        pc, pt, o_ = [], [], 0
        for ob in prop_obs:
            c_ = eval_co(ob, dg)
            pc.append(c_); pt.append(tris_of(ob)[0] + o_); o_ += len(c_)
        pco = np.concatenate(pc)
        pb = BVHTree.FromPolygons(pco.tolist(), np.concatenate(pt).tolist(), all_triangles=True)
        over = max(over, len(pb.overlap(dbvh)))
        for p in dpts:
            h = pb.find_nearest(V(p), best)
            if h[0] is not None and h[3] < best:
                best, at = h[3], ps
    return dict(label=label, poses=len(poses), detail_tris_near=int(len(tri)), overlap_pairs_max=over,
                min_distance_m=round(best, 3), at_pose=at, passed=over == 0)


def main():
    o = opts()
    t0 = time.time()
    bpy.ops.wm.open_mainfile(filepath=o.get('blend', DETAIL_BLEND))
    arm = bpy.data.objects['Armature']
    spec = C.load_json(C.CHECKS + '/bones_spec.json')
    for z in [z for z in str(o.get('zones', '')).split(',') if z.strip()]:
        D.append_zone(z.strip(), arm)
    import detail_ship as S
    import detail_base_edits as BE
    ship_s = S.Ship(bpy)
    be_rep = {}
    deleted = BE.deleted_mask(ship_s, o.get('base-edits', 'all'), be_rep)
    ship = ship_s.ob
    only = [c.strip() for c in str(o.get('only', '')).split(',') if c.strip()] or None
    test = D.detail_objects(only)
    context = [ob for ob in D.detail_objects() if ob not in test]
    # ---- skin / parent / modifier report of the test objects
    assign, bad_total = {}, 0
    for ob in test:
        names, bad = vgroup_names(ob)
        bad_total += bad
        u, c = np.unique(names.astype(str), return_counts=True)
        assign[ob.name] = dict(parent=ob.parent.name if ob.parent else None,
                               modifiers=[[m.type, getattr(m, 'object', None) and m.object.name] for m in ob.modifiers],
                               bones={k: int(v) for k, v in zip(u, c)}, verts=len(names), not_rigid=bad,
                               tris=int(sum(len(p.vertices) - 2 for p in ob.data.polygons)))
    scn = Scene(ship, deleted, test, context)
    results = []
    sets = [s.strip() for s in str(o.get('sets', 'pod:FL,cannons')).split(',') if s.strip()]
    for s in sets:
        kind, _, arg = s.partition(':')
        if kind == 'pod':
            results.append(run_set(s, *pod_set(arg, spec), scn, arm, spec))
        elif kind == 'turbine':
            results.append(run_set(s, *turbine_set(arg, spec), scn, arm, spec))
        elif kind == 'rudder':
            results.append(run_set(s, *rudder_set(spec), scn, arm, spec))
        elif kind == 'searchlights':
            results.append(run_set(s, *searchlight_set(spec), scn, arm, spec))
        elif kind == 'chain':
            results.append(run_set(s, *chain_set(spec), scn, arm, spec))
        elif kind == 'cannons':
            test_items = [it for it in scn.items if it[1] == 'test']
            for cn in (arg.split('+') if arg else C.CANNONS):
                cobs = [ob for ob in bpy.data.objects if ob.type == 'MESH' and ob.name.startswith('SM_AirshipProp_Cannon_' + cn)]
                poses = [{'CannonYawDeg_' + cn: y, 'CannonElevDeg_' + cn: e, 'CannonRecoilCm_' + cn: r}
                         for y, e, r in itertools.product((-20.0, 0.0, 20.0), (-10.0, 0.0, 8.75), (0.0, 60.0))]
                results.append(sweep_props('cannon ' + cn, cobs, lambda ps: C.apply_pose(arm, spec, ps), poses, test_items,
                                           spec['bones']['Cannon_' + cn]['head']))
            C.apply_pose(arm, spec, {})
        elif kind == 'turrets':
            import detail_render as R
            import detail_zones as Z
            R.add_turrets()
            test_items = [it for it in scn.items if it[1] == 'test']
            for s_ in ('L', 'R'):
                b = bpy.data.objects['SM_AirshipProp_Turret_%s_Base' % s_]
                gn = bpy.data.objects['SM_AirshipProp_Turret_%s_Gun' % s_]
                mount = V(Z.TURRET_MOUNTS[s_])
                piv = V((0, 0, Z.TURRET_PIVOT_H))
                y0, y1 = Z.TURRET_YAW_BLENDER[s_]

                def setp(ps, b=b, gn=gn, mount=mount, piv=piv):
                    Mb = Matrix.Translation(mount) @ Matrix.Rotation(math.radians(ps['yaw']), 4, 'Z')
                    b.matrix_world = Mb
                    gn.matrix_world = Mb @ Matrix.Translation(piv) @ Matrix.Rotation(math.radians(-ps['pitch']), 4, 'Y')
                poses = [dict(yaw=float(y), pitch=p) for y in range(int(y0), int(y1) + 1, 10)
                         for p in Z.TURRET_PITCH + (0.0,)]
                results.append(sweep_props('turret ' + s_, [b, gn], setp, poses, test_items, tuple(mount), radius=3.2))
        else:
            raise KeyError(s)
    rep = dict(blend=o.get('blend', DETAIL_BLEND), zones=o.get('zones'), only=only, base_edits=be_rep,
               test_objects=[ob.name for ob in test], context_objects=[ob.name for ob in context],
               not_rigid_vertices=bad_total, assignment=assign, results=results,
               passed=all(r.get('passed', True) for r in results) and bad_total == 0,
               seconds=round(time.time() - t0, 1))
    out = o.get('out', D.TMP_DIR + '/rigcheck.json')
    C.dump_json(rep, out)
    for r in results:
        print('[rigcheck]', r.get('set') or r.get('label'), 'PASS' if r.get('passed', True) else 'FAIL',
              json.dumps({k: r[k] for k in r if k in ('poses', 'new_contacts', 'overlap_pairs_max', 'min_distance_m',
                                                       'seconds', 'detail_tris_near')}))
        if 'worst' in r:
            print('[rigcheck]    worst', json.dumps(r['worst']))
    print('[rigcheck] not rigid vertices', bad_total, '; test objects', len(test), '; context', len(context))
    print('[rigcheck] RESULT', 'PASS' if rep['passed'] else 'FAIL', 'wrote', out, rep['seconds'], 's')
    sys.stdout.flush()


if __name__ == '__main__':
    main()
