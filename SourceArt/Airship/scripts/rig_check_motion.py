"""Step 6d: sweep every hull-part control of the rig through (and past) its range and look for collisions.

  blender -b --factory-startup --python rig/scripts/rig_check_motion.py -- [--json checks/rig/motion_ranges.json]

Uses the real rig (AirshipRig.blend, Armature modifier evaluated), so it checks the bones' pivots as built.
For each control and direction: walk from 0 in steps; at each step the moved SM_Airship faces are tested against the
faces that did not move (BVH triangle overlap). A contact counts when it touches an island that the moving part did
not already touch at rest ("new contact"; the 10 steam-pipe ends per side plugged into the fan intake are allowed to
clip, research_blender.md 3.3). For closed islands touched at rest and the closed hull skin, moved vertices that were
outside at rest and are now inside by more than 2 cm (ray parity) count too (e.g. the chain lying on the bow wedge).
hard = last value with no counted contact. Cannons and helm are covered by rig_place.py.
Never saves the .blend.
"""
import bpy, sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from mathutils import Vector as V
from mathutils.bvhtree import BVHTree
import rig_common as C

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
OUT = argv[argv.index('--json') + 1] if '--json' in argv else C.CHECKS + '/motion_ranges.json'
DEPTH_TOL = 0.02

bpy.ops.wm.open_mainfile(filepath=C.RIG_BLEND)
arm = bpy.data.objects['Armature']
spec = C.load_json(C.CHECKS + '/bones_spec.json')
ship = bpy.data.objects[C.HULL_OBJ]
co0, polys = C.mesh_arrays(ship.data)
VP = C.load_json(C.RESEARCH + '/sm_airship_vertex_parts.json')
visl = np.array(VP['vertex_island'])
fisl = np.array([visl[p[0]] for p in polys])
pv0 = np.array([p[0] for p in polys])


def posed_co(ctrl):
    C.apply_pose(arm, spec, ctrl)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    oe = ship.evaluated_get(dg); me = oe.to_mesh()
    co = np.empty(len(me.vertices) * 3); me.vertices.foreach_get('co', co)
    oe.to_mesh_clear()
    return co.reshape(-1, 3)


# pipe ends plugged into the fan intake lips: research_blender.md 3.3 lets them clip (they stay 18-34 cm inside the
# nacelle shell over +-20 deg), so they do not count as contacts for the fan yaw
ALLOWED = {466, 467, 512, 513, 558, 559, 560, 565, 566, 567, 612, 613, 658, 659, 704, 705, 706, 710, 711, 712}

# closed islands (every edge shared by exactly 2 faces) -> robust inside test by ray parity
from collections import Counter
ec = Counter()
for f in polys:
    for a, b in zip(f, f[1:] + f[:1]):
        ec[(min(a, b), max(a, b))] += 1
open_isl = {int(visl[a]) for (a, b), n in ec.items() if n != 2}
CLOSED = set(int(i) for i in np.unique(fisl)) - open_isl
DIRS = (V((0.3127, 0.2219, 0.9236)).normalized(), V((-0.5410, 0.7321, -0.4139)).normalized())
ISL_SRC = {r['id']: r['src'] for r in C.load_json(C.RESEARCH + '/sm_airship_islands.json')['islands']}


def inside(tree, p):
    """2-ray parity: inside only when both rays agree"""
    res = []
    for d in DIRS:
        n, o = 0, V(p)
        for _ in range(64):
            h = tree.ray_cast(o, d, 200.0)
            if h[0] is None:
                break
            n += 1
            o = h[0] + d * 1e-5
        res.append(n % 2 == 1)
    return all(res)


ISL_PIECE = {r['id']: (r['part'], r.get('piece', '')) for r in C.load_json(C.RESEARCH + '/sm_airship_islands.json')['islands']}


def penetration(points, tree, was_inside, vids):
    """depth of points that were outside the closed surface at rest and are inside now; + the deepest pieces"""
    worst, per = 0.0, {}
    for p, w, vi in zip(points, was_inside, vids):
        if w:
            continue
        if inside(tree, p):
            h = tree.find_nearest(V(p), 5.0)
            d = h[3] if h[0] is not None else 0.0
            worst = max(worst, d)
            k = int(visl[vi])
            per[k] = max(per.get(k, 0.0), d)
    top = sorted(per.items(), key=lambda kv: -kv[1])[:3]
    return worst, [dict(island=k, part=ISL_PIECE[k][0], piece=ISL_PIECE[k][1], depth_m=round(d, 3)) for k, d in top]


def check(ctrl_fn, values, label, ref=None, spin=False):
    """ctrl_fn(v) -> control dict; ref = control dict of the reference state (default rest).
    spin=True: a part turning about its own symmetry axis (no penetration test, only new contacts)."""
    ref_co = posed_co(ref or {})
    moved_v = np.zeros(len(co0), bool)
    for v in (values[-1], values[len(values) // 2], values[len(values) // 4]):
        moved_v |= np.linalg.norm(posed_co(ctrl_fn(v)) - ref_co, axis=1) > 1e-6
    mf = np.nonzero(moved_v[pv0])[0]
    sf = np.nonzero(~moved_v[pv0])[0]
    static = BVHTree.FromPolygons(ref_co.tolist(), [polys[i] for i in sf])
    mpolys = [polys[i] for i in mf]
    mverts = np.nonzero(moved_v)[0]

    def contacts(co):
        b = BVHTree.FromPolygons(co.tolist(), mpolys)
        return {int(fisl[sf[j]]) for _, j in b.overlap(static)}
    rest_touch = contacts(ref_co)
    # the closed hull skin, plus the closed bow-wedge blocks a part lies on (the chain): watch for points pushed inside
    watch = sorted({C.SHELL_ISLAND} | {i for i in rest_touch & CLOSED if ISL_SRC[i] == 'BowWedge'}) if not spin else []
    wf = [i for i in sf if int(fisl[i]) in watch]
    wtree = BVHTree.FromPolygons(ref_co.tolist(), [polys[i] for i in wf]) if wf else None
    was_in = [inside(wtree, p) for p in ref_co[mverts]] if wtree else None
    first, last_ok, rows = None, 0.0, []
    for v in values:
        co = posed_co(ctrl_fn(v))
        new = sorted(contacts(co) - rest_touch - ALLOWED)
        pen, deep = penetration(co[mverts], wtree, was_in, mverts) if wtree else (0.0, [])
        bad = bool(new) or pen > DEPTH_TOL
        rows.append(dict(value=v, new_islands=new[:8], penetration_m=round(pen, 3), deepest=deep))
        if bad and first is None:
            first = rows[-1]
        if not bad and first is None:
            last_ok = v
    return dict(label=label, moving_vertices=int(moved_v.sum()), rest_touch=sorted(rest_touch)[:12],
                watched_closed_islands=watch[:12], hard_limit=last_ok if first else values[-1], first_contact=first, rows=rows)


def steps(lim, n):
    return [round(lim * (i + 1) / n, 4) for i in range(n)]


R = {'method': __doc__.split('Uses the real rig')[1].split('Never saves')[0].strip(), 'checks': []}
JOBS = []
for p in C.PODS:
    for key, lim in (('NozzlePitchDeg_', 12), ('NozzlePitchDeg_', -12), ('NozzleRollDeg_', 12), ('NozzleRollDeg_', -12),
                     ('NozzleFlareDeg_', 45), ('NozzleFlareDeg_', -20), ('PodPitchDeg_', 6), ('PodPitchDeg_', -6),
                     ('PodRollDeg_', 6), ('PodRollDeg_', -6)):
        JOBS.append(('%s%s %+d' % (key, p, lim), (lambda k: (lambda v: {k: v}))(key + p), steps(lim, abs(lim) * 2 if abs(lim) <= 12 else abs(lim))))
for s in ('L', 'R'):
    for lim in (40, -40):
        JOBS.append(('TurbineYawDeg_%s %+d' % (s, lim), (lambda k: (lambda v: {k: v}))('TurbineYawDeg_' + s), steps(lim, 40)))
    for yaw in (-12, 0, 12):
        JOBS.append(('RotorAngleDeg_%s 0..360 at yaw %+d' % (s, yaw),
                     (lambda k, kk, y: (lambda v: {k: v, kk: y}))('RotorAngleDeg_' + s, 'TurbineYawDeg_' + s, yaw), steps(360, 72),
                     {'TurbineYawDeg_' + s: yaw}, True))
    for ax in ('X', 'Y'):
        for lim in (20, -20):
            JOBS.append(('RodSwing%sDeg_%s %+d' % (ax, s, lim), (lambda k: (lambda v: {k: v}))('RodSwing%sDeg_%s' % (ax, s)), steps(lim, 20)))
for lim in (60, -60):
    JOBS.append(('RudderDeg %+d' % lim, lambda v: {'RudderDeg': v}, steps(lim, 30)))
for ax in ('X', 'Y'):
    for lim in (15, -15):
        JOBS.append(('LampWobble%sDeg %+d (all 4 posts)' % (ax, lim), (lambda k: (lambda v: {k: v}))('LampWobble%sDeg' % ax), steps(lim, 15)))
JOBS.append(('SearchLightPanDeg 0..360', lambda v: {'SearchLightPanDeg': v}, steps(360, 36), None, True))
for lim in (45, -45):
    JOBS.append(('ChainSwingDeg %+d' % lim, lambda v: {'ChainSwingDeg': v}, steps(lim, 45)))
JOBS.append(('WinchSpinDeg 0..360', lambda v: {'WinchSpinDeg': v}, steps(360, 24), None, True))

for job in JOBS:
    label, fn, vals = job[:3]
    r = check(fn, vals, label, *job[3:])
    R['checks'].append(r)
    print('[motion] %-40s hard %7.2f  first %s  watch %s' % (label, r['hard_limit'], {k: r['first_contact'][k] for k in ('value', 'new_islands', 'penetration_m')} if r['first_contact'] else None, r['watched_closed_islands']))
for r in R['checks']:
    r['rows'] = [x for x in r['rows'] if x['new_islands'] or x['penetration_m'] > 0.005][:6]
C.dump_json(R, OUT)
print('[motion] wrote', OUT)
