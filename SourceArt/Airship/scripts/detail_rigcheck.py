"""Rig check for the detail pass: pose the detailed pod / nozzle / petal bones through their contract limits and look
for new intersections between parts that move against each other; report the per-bone skin assignment.

  blender -b --factory-startup --python detail_rigcheck.py -- --pod FL [--render DIR]

Opens rig/detail/AirshipRig_detail.blend (never saved). Limits (RIG_CONTRACT.md + research_blender.md 3.1/3.2): pod
+-3 deg pitch and roll (spring jiggle), nozzle +-5 deg pitch and roll (thrust vectoring), petals -10 .. +35 deg flare.
Every combination of pod {-3, 0, 3}^2 x nozzle {-5, 0, 5}^2 x flare {-10, 0, 35} is tested.

For each pose, triangle overlaps (BVH) are counted between groups that move against each other:
  details on the pod     vs the static hull (ship + hull details)
  details on the nozzle  vs the pod (ship + pod details) and the static hull
  details on the petals  vs the nozzle (ship + nozzle details), the pod, the static hull
  hull details           vs the pod, nozzle and petals (ship geometry)
The same counts for the ship's own geometry (pod vs hull, nozzle vs pod, ...) are the baseline the details are judged
against (research: the FL pod already touches its pocket at 1-3 deg).
Writes rig/detail/zone1_rigcheck.json.
"""
import bpy, sys, os, json, math, itertools, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from mathutils.bvhtree import BVHTree
import rig_common as C

DETAIL_BLEND = C.RIG + '/detail/AirshipRig_detail.blend'


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
    me = ob.data
    me.calc_loop_triangles()
    t = np.empty(len(me.loop_triangles) * 3, np.int64)
    me.loop_triangles.foreach_get('vertices', t)
    return t.reshape(-1, 3)


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


def main():
    o = opts()
    pod = o.get('pod', 'FL')
    bpy.ops.wm.open_mainfile(filepath=DETAIL_BLEND)
    arm = bpy.data.objects['Armature']
    spec = C.load_json(C.CHECKS + '/bones_spec.json')
    ship = bpy.data.objects[C.HULL_OBJ]
    dets = [ob for ob in bpy.data.objects if ob.name.startswith('SM_AirshipDetail_') and ob.type == 'MESH']
    B = 'Thruster_' + pod
    moving = lambda n: n == B or n.startswith(B + '_')

    def role(bone):
        if bone == B:
            return 'pod'
        if bone == B + '_Nozzle':
            return 'nozzle'
        if bone.startswith(B + '_Petal'):
            return 'petal'
        return 'hull' if bone == 'Hull' else 'other'

    # ---- per-bone assignment report
    assign = {}
    bad_total = 0
    for ob in dets:
        names, bad = vgroup_names(ob)
        bad_total += bad
        u, c = np.unique(names.astype(str), return_counts=True)
        mods = [m.type for m in ob.modifiers]
        assign[ob.name] = dict(parent=ob.parent.name if ob.parent else None, modifiers=mods,
                               bones={k: int(v) for k, v in zip(u, c)}, verts=len(names), not_rigid=bad,
                               tris=int(sum(len(p.vertices) - 2 for p in ob.data.polygons)))
    # ---- triangle groups: (source object, triangle index arrays per role)
    pod_origin = np.array(spec['bones'][B]['head'])
    groups = {}          # name -> list of (object, tri array)

    def add(name, ob, tri):
        if len(tri):
            groups.setdefault(name, []).append((ob, tri))
    s_names, _ = vgroup_names(ship)
    s_tri = tris_of(ship)
    s_co0 = np.array([v.co[:] for v in ship.data.vertices])
    near = np.linalg.norm(s_co0[s_tri].mean(1) - pod_origin, axis=1) < 6.5
    tb = s_names[s_tri[:, 0]]
    for r_ in ('pod', 'nozzle', 'petal'):
        add('ship_' + r_, ship, s_tri[np.array([role(str(b)) == r_ for b in tb]) & near])
    add('ship_hull', ship, s_tri[np.array([str(b) == 'Hull' for b in tb]) & near])
    for ob in dets:
        names, _ = vgroup_names(ob)
        t = tris_of(ob)
        if not len(t):
            continue
        c0 = np.array([v.co[:] for v in ob.data.vertices])
        nr = np.linalg.norm(c0[t].mean(1) - pod_origin, axis=1) < 6.5
        tbd = names[t[:, 0]]
        for r_ in ('pod', 'nozzle', 'petal', 'hull'):
            add('det_' + r_, ob, t[np.array([role(str(b)) == r_ for b in tbd]) & nr])
    log = {k: sum(len(t) for _, t in v) for k, v in groups.items()}
    print('[rigcheck] triangles near the pod', log)

    PAIRS = [  # (label, group a, group b, new?)  new = involves detail geometry
        ('pod details vs static hull', 'det_pod', ('ship_hull', 'det_hull'), True),
        ('nozzle details vs pod', 'det_nozzle', ('ship_pod', 'det_pod'), True),
        ('nozzle details vs static hull', 'det_nozzle', ('ship_hull', 'det_hull'), True),
        ('petal details vs nozzle', 'det_petal', ('ship_nozzle', 'det_nozzle'), True),
        ('petal details vs pod + hull', 'det_petal', ('ship_pod', 'det_pod', 'ship_hull', 'det_hull'), True),
        ('hull details vs pod + nozzle + petals', 'det_hull', ('ship_pod', 'ship_nozzle', 'ship_petal'), True),
        ('nozzle (ship) vs pod details', 'ship_nozzle', ('det_pod',), True),
        ('petals (ship) vs nozzle + pod details', 'ship_petal', ('det_nozzle', 'det_pod'), True),
        ('baseline: pod (ship) vs static hull (ship)', 'ship_pod', ('ship_hull',), False),
        ('baseline: nozzle (ship) vs pod (ship)', 'ship_nozzle', ('ship_pod',), False),
    ]

    def bvh_of(names, cache):
        co_all, tri_all, off = [], [], 0
        for n in names:
            for ob, tri in groups.get(n, []):
                co = cache[ob.name]
                co_all.append(co)
                tri_all.append(tri + off)
                off += len(co)
        if not co_all:
            return None
        return BVHTree.FromPolygons(np.concatenate(co_all).tolist(), np.concatenate(tri_all).tolist(), all_triangles=True)

    def check(ctrl):
        C.apply_pose(arm, spec, ctrl)
        dg = bpy.context.evaluated_depsgraph_get()
        dg.update()
        cache = {ob.name: eval_co(ob, dg) for ob in [ship] + dets}
        res = {}
        for (label, a, bs, new) in PAIRS:
            ba = bvh_of([a], cache)
            bb = bvh_of(list(bs), cache)
            res[label] = 0 if (ba is None or bb is None) else len(ba.overlap(bb))
        return res

    P = [-3.0, 0.0, 3.0]
    N = [-5.0, 0.0, 5.0]
    F = [-10.0, 0.0, 35.0]
    t0 = time.time()
    rest = check({})
    rows = []
    worst = {}
    for pp, pr, npi, nro, fl in itertools.product(P, P, N, N, F):
        ctrl = {'PodPitchDeg_' + pod: pp, 'PodRollDeg_' + pod: pr, 'NozzlePitchDeg_' + pod: npi,
                'NozzleRollDeg_' + pod: nro, 'NozzleFlareDeg_' + pod: fl}
        r = check(ctrl)
        rows.append(dict(ctrl=[pp, pr, npi, nro, fl], res=r))
        for k, v in r.items():
            if v > worst.get(k, (-1,))[0]:
                worst[k] = (v, [pp, pr, npi, nro, fl])
    C.apply_pose(arm, spec, {})
    new_bad = {k: v for k, v in worst.items() if v[0] > rest[k] and not k.startswith('baseline')}

    # ---- port cannons (yaw +-20, elevation -10 .. +8.75, recoil 0 .. 60 cm) against the hull details: overlaps and
    #      the smallest distance between the swept cannon and any hull detail
    hull_dets = [ob for ob in dets if all(n == 'Hull' for n in vgroup_names(ob)[0].astype(str))]
    cannons = {}
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    det_cache = {ob.name: eval_co(ob, dg) for ob in hull_dets}
    det_tris = {ob.name: tris_of(ob) for ob in hull_dets}
    det_bvh = BVHTree.FromPolygons(np.concatenate([det_cache[o.name] for o in hull_dets]).tolist(),
                                   np.concatenate([det_tris[o.name] + off for o, off in
                                                   zip(hull_dets, np.cumsum([0] + [len(det_cache[o.name]) for o in hull_dets[:-1]]))]).tolist(),
                                   all_triangles=True) if hull_dets else None
    det_co = np.concatenate([det_cache[o.name] for o in hull_dets]) if hull_dets else np.zeros((0, 3))
    for cn in ('L1', 'L2'):
        cobs = [ob for ob in bpy.data.objects if ob.type == 'MESH' and ob.name.startswith('SM_AirshipProp_Cannon_' + cn)]
        if not cobs or det_bvh is None:
            continue
        best = (9.0, None)
        over = 0
        for yaw, el, rc in itertools.product((-20.0, 0.0, 20.0), (-10.0, 0.0, 8.75), (0.0, 60.0)):
            C.apply_pose(arm, spec, {'CannonYawDeg_' + cn: yaw, 'CannonElevDeg_' + cn: el, 'CannonRecoilCm_' + cn: rc})
            dg = bpy.context.evaluated_depsgraph_get()
            dg.update()
            co_all, tri_all, o_ = [], [], 0
            for ob in cobs:
                c_ = eval_co(ob, dg)
                co_all.append(c_); tri_all.append(tris_of(ob) + o_); o_ += len(c_)
            cco = np.concatenate(co_all)
            cb = BVHTree.FromPolygons(cco.tolist(), np.concatenate(tri_all).tolist(), all_triangles=True)
            over = max(over, len(cb.overlap(det_bvh)))
            centre = cco.mean(0)
            near = det_co[np.linalg.norm(det_co - centre, axis=1) < 4.0]
            for p in near:
                hit = cb.find_nearest(p, best[0])
                if hit[0] is not None and hit[3] < best[0]:
                    best = (hit[3], [yaw, el, rc])
        cannons[cn] = dict(poses=18, overlap_pairs_max=over, min_distance_m=round(best[0], 3), at_pose_yaw_elev_recoil=best[1],
                           detail_vertices_within_4m=int(len(near)))
    C.apply_pose(arm, spec, {})
    print('[rigcheck] cannons', json.dumps(cannons))
    rep = dict(pod=pod, poses=len(rows), seconds=round(time.time() - t0, 1),
               limits=dict(pod_pitch_roll_deg=P, nozzle_pitch_roll_deg=N, petal_flare_deg=F),
               rest=rest, worst={k: dict(overlap_pairs=v[0], pose=v[1]) for k, v in worst.items()},
               new_contacts_from_details=new_bad, not_rigid_vertices=bad_total, assignment=assign, cannons=cannons,
               triangles_tested=log, pose_order='[pod pitch, pod roll, nozzle pitch, nozzle roll, petal flare] deg')
    out = C.RIG + '/detail/zone1_rigcheck.json'
    C.dump_json(dict(rep, rows=rows), out)
    print('[rigcheck] rest', rest)
    print('[rigcheck] worst', json.dumps(rep['worst']))
    print('[rigcheck] new contacts from details', new_bad)
    print('[rigcheck] not rigid vertices', bad_total)
    print('[rigcheck] assignment', json.dumps({k: v['bones'] for k, v in assign.items()}))
    print('[rigcheck] wrote', out, rep['seconds'], 's')


if __name__ == '__main__':
    main()
