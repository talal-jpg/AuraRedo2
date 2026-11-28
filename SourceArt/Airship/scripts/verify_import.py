"""Second reader for rig/export/SK_Airship.fbx: fresh import into a clean factory scene (no rig_* code), then
* skeleton: names, parents, rest heads vs the low-level reader, tails = head + Z, roll 0 (bones world-aligned);
* skin: every vertex in exactly one group with weight 1, the expected bone (research island map / prop names);
* deformation: each of the 105 skinned bones is rotated alone; the set of vertices that move must be exactly the
  vertices of that bone and its descendants (checked per vertex, all 31 meshes);
* prop atlas: UV channel 0, overlap raster test (4 cannon copies may share their region with each other only), with the
  two turret static meshes (export/SM_AirshipTurret_*.fbx) on the same atlas.
Round 2: SM_Airship is Talal's mesh minus the islands in scripts/deck_removals.json (vertex i = his kept vertex i).

  blender -b --factory-startup --python rig/scripts/verify_import.py -- [--fbx F] [--out rig/checks/verify/import_verify.json]
Round 3 (2026-11-28), only with --r3: --fbx default rig/detail/r3export/fbx/SK_Airship.fbx (or an _LOD1 / _LOD2 file),
the low-level reader's report is rig/detail/r3export/checks/fbx_verify.json (verify_fbx.py --r3, which also resolves
the round 3 base edits: SM_Airship = Talal's mesh minus deck_removals.json minus those islands), the Moving detail
object's expected bone per vertex comes from rig/detail/r3export/manifest_arrays.npz, so the deformation test covers
every detail vertex too; the prop atlas test leaves the Moving object out (its UV0 is the detail page) and expects two UV
layers (UVMap, R3Palette) on the props and on the turret meshes next to the FBX. Without --r3 nothing changes.
"""
import bpy, sys, os, json, math
import numpy as np
from mathutils import Matrix, Vector, Quaternion

RIG = '/mnt/new_partition/BlenderProjects/StylizedAirship/rig'
RES = '/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/research'
argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
def arg(k, d):
    return argv[argv.index(k) + 1] if k in argv else d
R3 = '--r3' in argv or '--round3' in argv
R3X = RIG + '/detail/r3export'
FBX = arg('--fbx', R3X + '/fbx/SK_Airship.fbx' if R3 else RIG + '/export/SK_Airship.fbx')
OUT = arg('--out', R3X + '/checks/import_verify.json' if R3 else RIG + '/checks/verify/import_verify.json')
LOW = arg('--low', R3X + '/checks/fbx_verify.json' if R3 else RIG + '/checks/verify/fbx_verify.json')

rep = {'fbx': FBX, 'defects': [], 'notes': []}
def defect(m):
    rep['defects'].append(m); print('[DEFECT]', m)
def note(m):
    rep['notes'].append(m); print('[note]', m)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=FBX, automatic_bone_orientation=False, primary_bone_axis='Z',
                         secondary_bone_axis='X', ignore_leaf_bones=False, use_anim=False)
arms = [o for o in bpy.data.objects if o.type == 'ARMATURE']
meshes = sorted([o for o in bpy.data.objects if o.type == 'MESH'], key=lambda o: o.name)
rep['objects'] = {'armatures': [a.name for a in arms], 'meshes': len(meshes), 'other': sorted({o.type for o in bpy.data.objects} - {'ARMATURE', 'MESH'})}
if len(arms) != 1 or arms[0].name != 'Armature':
    defect('imported armatures: %s' % [a.name for a in arms])
arm = arms[0]
bones = arm.data.bones
rep['bone_count'] = len(bones)
roots = [b.name for b in bones if b.parent is None]
rep['root_bones'] = roots
if roots != ['root']:
    defect('root bones: %s' % roots)
low = json.load(open(LOW))
lowpos = low['positions_ue_cm']
AW = arm.matrix_world
head = {}; maxd = 0.0; dir_dev = 0.0; roll_dev = 0.0
for b in bones:
    M = AW @ b.matrix_local
    h = M.translation
    head[b.name] = np.array(h)
    ue = lowpos.get(b.name)
    if ue is None:
        defect('bone %s not in the low-level reader' % b.name); continue
    p = np.array((ue[0] / 100, -ue[1] / 100, ue[2] / 100))
    maxd = max(maxd, float(np.linalg.norm(p - head[b.name])))
    R = M.to_3x3().normalized()
    y = R.col[1]; x = R.col[0]
    dir_dev = max(dir_dev, (y - Vector((0, 0, 1))).length)
    roll_dev = max(roll_dev, (x - Vector((1, 0, 0))).length)
rep['heads_vs_lowlevel_max_m'] = maxd
rep['bone_dir_dev_from_+Z'] = dir_dev
rep['bone_x_axis_dev_from_+X'] = roll_dev
if maxd > 1e-4: defect('imported bone heads differ from the low-level reader by %g m' % maxd)
if dir_dev > 1e-4 or roll_dev > 1e-4: defect('imported bones not world-aligned (dir %g, roll %g)' % (dir_dev, roll_dev))
lens = [(AW @ b.tail_local - AW @ b.head_local).length for b in bones]
rep['bone_length_m_range'] = [min(lens), max(lens)]

# ---------------------------------------------------------------- expected bone per vertex
islands = json.load(open(RES + '/sm_airship_islands.json'))
vparts = json.load(open(RES + '/sm_airship_vertex_parts.json'))
isl = {i['id']: i for i in islands['islands']}
pn = vparts['parts']
DR = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'deck_removals.json')))
REMOVED = sorted(i for p in DR['pieces'] for i in p['islands'])
if R3:
    # round 3: the base-edit islands as the low-level reader resolved them (their guards are checked there)
    REMOVED = sorted(set(REMOVED) | {i for e in low.get('r3_base_edits', []) for i in e['islands']})
    rep['r3_removed_islands'] = REMOVED
    if not low.get('r3_base_edits'):
        defect('%s has no r3_base_edits: run verify_fbx.py --r3 on this FBX first' % LOW)
    R3_ARR = np.load(R3X + '/manifest_arrays.npz')
    R3_BONES = [str(b) for b in R3_ARR['bone_names']]
KEEP = np.nonzero(~np.isin(np.array(vparts['vertex_island']), REMOVED))[0]
rep['sm_airship_expected_verts'] = int(len(KEEP))
def exp_sm(vi):
    vi = int(KEEP[vi])
    part = pn[vparts['vertex_part'][vi]]; i = isl[vparts['vertex_island'][vi]]; piece = i['piece']
    if part.startswith('Pod_'): return 'Thruster_' + part[4:]
    if part.startswith('Nozzle_'):
        t = part[7:]
        return 'Thruster_%s_Petal%02d' % (t, i['index']) if piece == 'petal' else 'Thruster_%s_Nozzle' % t
    if part.startswith('FanHousing_'): return 'Turbine_%s_Rod' % part[-1] if piece == 'hanging_rod' else 'Turbine_' + part[-1]
    if part.startswith('FanRotor_'): return 'Turbine_%s_Rotor' % part[-1]
    if part.startswith(('FanMount_', 'HangStrip_')) or part in ('ChainAft', 'Hull'): return 'Hull'
    if part.startswith('SearchLight_'): return part if piece == 'post' else part + '_Head'
    return part
def exp_prop(n):
    n = n.replace('SM_AirshipProp_', '')
    if n == 'Helm_Pedestal': return 'Helm'
    if n == 'Helm_Wheel': return 'Helm_Wheel'
    c, part = n.split('_')[1], '_'.join(n.split('_')[2:])
    return 'Cannon_' + c if part == 'Carriage' else 'Cannon_%s_%s' % (c, part)
expected = {}
for o in meshes:
    nv = len(o.data.vertices)
    if o.name == 'SM_Airship' and nv != len(KEEP):
        defect('imported SM_Airship has %d vertices, expected %d (Talal\'s minus the removed deck pieces)' % (nv, len(KEEP)))
        nv = min(nv, len(KEEP))
    if R3 and o.name.startswith('SM_AirshipR3Detail_Moving'):
        _vb = R3_ARR[o.name.replace('SM_Airship', '').strip('_') + '__vert_bone']
        if len(_vb) != nv:
            defect('%s has %d vertices, the manifest %d' % (o.name, nv, len(_vb)))
        expected[o.name] = [R3_BONES[int(_vb[i])] if i < len(_vb) else None for i in range(nv)]
        continue
    expected[o.name] = [exp_sm(i) for i in range(nv)] if o.name == 'SM_Airship' else [exp_prop(o.name)] * nv
if 'SM_Airship' not in expected:
    defect('imported SM_Airship missing')

# ---------------------------------------------------------------- weights (second reader)
bad_w = 0; wrong = {}; nverts = 0
for o in meshes:
    gname = {g.index: g.name for g in o.vertex_groups}
    mods = [m for m in o.modifiers if m.type == 'ARMATURE']
    if len(mods) != 1 or mods[0].object != arm:
        defect('%s armature modifier: %s' % (o.name, [(m.type, m.object.name if m.object else None) for m in o.modifiers]))
    for v in o.data.vertices:
        nverts += 1
        gs = [(gname[g.group], g.weight) for g in v.groups if g.weight > 0]
        if len(gs) != 1 or abs(gs[0][1] - 1) > 1e-6:
            bad_w += 1; continue
        if gs[0][0] != expected[o.name][v.index]:
            k = '%s: %s -> %s' % (o.name, expected[o.name][v.index], gs[0][0]); wrong[k] = wrong.get(k, 0) + 1
rep['verts'] = nverts; rep['verts_bad_weight'] = bad_w; rep['verts_wrong_bone'] = wrong
if bad_w: defect('%d vertices not 100%% on one bone' % bad_w)
if wrong: defect('wrong bone assignments: %s' % wrong)

# ---------------------------------------------------------------- deformation test, bone by bone
def descendants(name):
    out = {name}
    for c in bones[name].children_recursive:
        out.add(c.name)
    return out
dg = bpy.context.evaluated_depsgraph_get()
def eval_positions():
    dg.update()
    res = {}
    for o in meshes:
        oe = o.evaluated_get(dg)
        me = oe.to_mesh()
        a = np.empty(len(me.vertices) * 3); me.vertices.foreach_get('co', a)
        res[o.name] = a.reshape(-1, 3).copy()
        oe.to_mesh_clear()
    return res
for pb in arm.pose.bones:
    pb.rotation_mode = 'QUATERNION'; pb.rotation_quaternion = (1, 0, 0, 0); pb.location = (0, 0, 0)
rest = eval_positions()
# rest pose must equal the bind (no offset from the armature modifier)
rest_dev = max(float(np.abs(rest[o.name] - np.array([tuple(v.co) for v in o.data.vertices])).max()) * o.matrix_world.to_scale()[0] for o in meshes)   # metres
rep['rest_eval_vs_base_max'] = rest_dev
if rest_dev > 1e-5: defect('rest-pose deformation moves vertices by %g' % rest_dev)
skinned = sorted({b for l in expected.values() for b in l})
q = Quaternion(Vector((0.3, 0.5, 0.81)).normalized(), math.radians(20))
per_bone = {}; mism_total = 0
vbone = {n: np.array(l) for n, l in expected.items()}
for bname in skinned:
    pb = arm.pose.bones[bname]
    pb.rotation_quaternion = q; pb.location = (1.0, 2.0, 3.0)     # rotation + offset: vertices at the pivot move too
    pos = eval_positions()
    pb.rotation_quaternion = (1, 0, 0, 0); pb.location = (0, 0, 0)
    D = descendants(bname)
    moved = 0; mism = 0; ex_n = 0
    for o in meshes:
        d = np.linalg.norm(pos[o.name] - rest[o.name], axis=1) * o.matrix_world.to_scale()[0]
        mv = d > 1e-4
        ex = np.isin(vbone[o.name], list(D))
        moved += int(mv.sum()); ex_n += int(ex.sum()); mism += int((mv != ex).sum())
    per_bone[bname] = {'moved': moved, 'expected': ex_n, 'mismatch': mism}
    mism_total += mism
rep['deform_test'] = per_bone
rep['deform_mismatch_total'] = mism_total
if mism_total:
    defect('deformation test mismatches: %s' % {b: v for b, v in per_bone.items() if v['mismatch']})
print('[verify_import] deform test: %d bones, %d mismatching vertices' % (len(per_bone), mism_total))

# ---------------------------------------------------------------- prop atlas UV overlap (raster)
RESN = 4096
cover = np.zeros((RESN, RESN), np.int32)
owner = np.full((RESN, RESN), -1, np.int32)
pairs = {}
props = [o for o in meshes if o.name != 'SM_Airship' and not (R3 and o.name.startswith('SM_AirshipR3Detail_Moving'))]
# round 2: the turret static meshes share the prop atlas (separate FBX files next to the SK)
before = set(bpy.data.objects)
for n in ('SM_AirshipTurret_Base', 'SM_AirshipTurret_Gun'):
    f = os.path.join(os.path.dirname(FBX), n + '.fbx')
    if os.path.exists(f):
        bpy.ops.import_scene.fbx(filepath=f)
    else:
        defect('missing %s' % f)
turret_objs = sorted([o for o in bpy.data.objects if o not in before and o.type == 'MESH'], key=lambda o: o.name)
rep['turret_meshes'] = [o.name for o in turret_objs]
props += turret_objs
uvinfo = {}
oid = 0
names = {}
for o in props:
    me = o.data
    uvinfo[o.name] = [u.name for u in me.uv_layers]
    if o.name.startswith('SM_AirshipProp_Cannon_') and '_L1_' not in o.name:
        continue                    # identical copies of L1 (checked bit-equal by verify_fbx.py) share its region
    me.calc_loop_triangles()
    uv = me.uv_layers[0].data
    for t in me.loop_triangles:
        P = np.array([tuple(uv[l].uv) for l in t.loops]) * RESN - 0.5
        # shrink by 0.35 texel toward the centroid so shared edges do not count as overlap
        c = P.mean(0); Pn = c + (P - c) * np.maximum(0.0, 1 - 0.35 / np.maximum(np.linalg.norm(P - c, axis=1, keepdims=True), 1e-9))
        x0, y0 = np.floor(Pn.min(0)).astype(int); x1, y1 = np.ceil(Pn.max(0)).astype(int)
        x0 = max(x0, 0); y0 = max(y0, 0); x1 = min(x1, RESN - 1); y1 = min(y1, RESN - 1)
        if x1 < x0 or y1 < y0:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
        def edge(a, b):
            return (b[0] - a[0]) * (ys - a[1]) - (b[1] - a[1]) * (xs - a[0])
        e0, e1, e2 = edge(Pn[0], Pn[1]), edge(Pn[1], Pn[2]), edge(Pn[2], Pn[0])
        inside = ((e0 >= 0) & (e1 >= 0) & (e2 >= 0)) | ((e0 <= 0) & (e1 <= 0) & (e2 <= 0))
        if not inside.any():
            continue
        yy, xx = ys[inside], xs[inside]
        prev = owner[yy, xx]
        hit = prev >= 0
        for pid in np.unique(prev[hit]):
            key = (names[pid], o.name)
            pairs[key] = pairs.get(key, 0) + int((prev[hit] == pid).sum())
        cover[yy, xx] += 1
        owner[yy, xx] = oid
    names[oid] = o.name; oid += 1
over = int((cover > 1).sum()); used = int((cover > 0).sum())
rep['prop_uv'] = {'layers': uvinfo, 'raster': RESN, 'texels_used': used, 'coverage': used / RESN ** 2,
                  'texels_overlapping': over, 'overlap_pairs': {'%s | %s' % k: v for k, v in sorted(pairs.items(), key=lambda kv: -kv[1])[:20]}}
# same object overlapping itself counts too (pairs with equal names)
if over > 50:
    defect('prop atlas UV overlap: %d texels at %d^2 (pairs: %s)' % (over, RESN, rep['prop_uv']['overlap_pairs']))
elif over:
    note('prop atlas: %d texels touch (raster tolerance)' % over)
bad_layers = {n: l for n, l in uvinfo.items() if (l != ['UVMap', 'R3Palette'] if R3 else len(l) != 1)}
if bad_layers: defect('prop UV layer counts: %s' % bad_layers)
# SM_Airship vs props overlap is irrelevant (different materials / textures)

json.dump(rep, open(OUT, 'w'), indent=1, default=str)
print('[verify_import] defects:', len(rep['defects']), 'notes:', len(rep['notes']), '->', OUT)
