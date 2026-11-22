"""Independent check of rig/export/SK_Airship.fbx with Blender's low-level FBX parser (no rig_* code).

  blender -b --factory-startup rig/checks/verify/Talal_copy.blend --python rig/scripts/verify_fbx.py -- \
      [--fbx rig/export/SK_Airship.fbx] [--out rig/checks/verify/fbx_verify.json]

Talal_copy.blend is a byte copy of StylizedAirship.blend (never saved). Checks: units/axes, node names, bone set and
parents against RIG_CONTRACT.md, rest positions (contract + geometry-derived pivots), rest orientations (all equal,
world-aligned, identity after the Y-up -> Z-up conversion UE applies), weights (one bone, weight 1 per vertex, the
expected bone from the research island map), SM_Airship positions / face corners / UVs / normals vs Talal's mesh,
materials, UCX, prop UV channels.
"""
import bpy, sys, os, json, math
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_fbxlib as F
from io_scene_fbx.fbx_utils import RIGHT_HAND_AXES
from bpy_extras.io_utils import axis_conversion

RIG = '/mnt/new_partition/BlenderProjects/StylizedAirship/rig'
RES = '/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/research'
argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
def arg(k, d):
    return argv[argv.index(k) + 1] if k in argv else d
FBX = arg('--fbx', RIG + '/export/SK_Airship.fbx')
OUT = arg('--out', RIG + '/checks/verify/fbx_verify.json')

rep = {'fbx': FBX, 'defects': [], 'notes': []}
def defect(msg):
    rep['defects'].append(msg); print('[DEFECT]', msg)
def note(msg):
    rep['notes'].append(msg); print('[note]', msg)

sc = F.load(FBX)
gs = sc.global_settings
rep['global_settings'] = {k: gs.get(k) for k in ['UpAxis', 'UpAxisSign', 'FrontAxis', 'FrontAxisSign', 'CoordAxis',
                                                  'CoordAxisSign', 'UnitScaleFactor', 'OriginalUnitScaleFactor']}
usf = float(gs.get('UnitScaleFactor', 1.0))
if abs(usf - 1.0) > 1e-5:
    defect('UnitScaleFactor %r != 1' % usf)
axis_key = ((int(gs['UpAxis']), int(gs['UpAxisSign'])), (int(gs['FrontAxis']), int(gs['FrontAxisSign'])),
            (int(gs['CoordAxis']), int(gs['CoordAxisSign'])))
inv = {v: k for k, v in RIGHT_HAND_AXES.items()}
ax_up, ax_fwd = inv[axis_key]
CV = axis_conversion(from_forward=ax_fwd, from_up=ax_up).to_4x4()   # file axes -> Blender/UE Z-up axes
TOM = usf * 0.01                                                     # file units -> metres
rep['axes'] = {'file_up': ax_up, 'file_forward': ax_fwd, 'conversion_to_zup': [list(r) for r in CV.to_3x3()]}
# what UE's FbxAxisSystem::ConvertScene does for (Y up, +Z front parity odd, RH) -> (Z up, -Y front, RH): X->X, Y->Z, Z->-Y
UE_CONV = Matrix(((1, 0, 0), (0, 0, -1), (0, 1, 0)))
if (CV.to_3x3() - UE_CONV).to_quaternion().angle > 1e-6 and max(abs(a - b) for r1, r2 in zip(CV.to_3x3(), UE_CONV) for a, b in zip(r1, r2)) > 1e-6:
    note('file axis conversion differs from the Y-up->Z-up rotation assumed for UE: %s' % rep['axes'])

# ---------------------------------------------------------------- nodes
by_name = {}
for uid, m in sc.models.items():
    by_name.setdefault(m['name'], []).append(uid)
dups = [n for n, l in by_name.items() if len(l) > 1]
if dups:
    defect('duplicate node names: %s' % dups)
nulls = [m for m in sc.models.values() if m['type'] == 'Null']
limbs = {m['name']: uid for uid, m in sc.models.items() if m['type'] == 'LimbNode'}
meshes = {m['name']: uid for uid, m in sc.models.items() if m['type'] == 'Mesh'}
rep['node_counts'] = {'Null': len(nulls), 'LimbNode': len(limbs), 'Mesh': len(meshes),
                      'other': sorted({m['type'] for m in sc.models.values()} - {'Null', 'LimbNode', 'Mesh'})}
if [n['name'] for n in nulls] != ['Armature']:
    defect('Null nodes: %s (expected exactly one named Armature)' % [n['name'] for n in nulls])
arm_uid = by_name['Armature'][0]
if sc.parent.get(arm_uid, 0) != 0:
    defect('Armature node is not at the scene root')
def pname(uid):
    p = sc.parent.get(uid, 0)
    return sc.models[p]['name'] if p in sc.models else None

# expected skeleton (RIG_CONTRACT.md section 3)
exp_parent = {'root': 'Armature', 'Hull': 'root'}
for t in ['FL', 'FR', 'RL', 'RR']:
    exp_parent['Thruster_' + t] = 'Hull'
    exp_parent['Thruster_%s_Nozzle' % t] = 'Thruster_' + t
    for i in range(12):
        exp_parent['Thruster_%s_Petal%02d' % (t, i)] = 'Thruster_%s_Nozzle' % t
    exp_parent['Thruster_%s_Flame' % t] = 'Thruster_%s_Nozzle' % t
for s in ['L', 'R']:
    exp_parent['Turbine_' + s] = 'Hull'
    for c in ['Rotor', 'Rod', 'Exhaust']:
        exp_parent['Turbine_%s_%s' % (s, c)] = 'Turbine_' + s
exp_parent['Rudder'] = 'Hull'
for s in ['AftL', 'MidL', 'MidR', 'FwdC']:
    exp_parent['SearchLight_' + s] = 'Hull'; exp_parent['SearchLight_%s_Head' % s] = 'SearchLight_' + s
exp_parent.update({'ChainFwd': 'Hull', 'ChainFwd_End': 'ChainFwd', 'Winch_Fwd': 'Hull', 'Winch_Aft': 'Hull',
                   'Helm': 'Hull', 'Helm_Wheel': 'Helm', 'PilotSeat': 'Hull'})
for c in ['L1', 'L2', 'R1', 'R2']:
    exp_parent['Cannon_' + c] = 'Hull'
    for s in ['Barrel', 'Quoin', 'Wheel_FL', 'Wheel_FR', 'Wheel_BL', 'Wheel_BR']:
        exp_parent['Cannon_%s_%s' % (c, s)] = 'Cannon_' + c
    exp_parent['Cannon_%s_Muzzle' % c] = 'Cannon_%s_Barrel' % c
SOCKETS = {'root', 'PilotSeat', 'ChainFwd_End'} | {'Thruster_%s_Flame' % t for t in ['FL', 'FR', 'RL', 'RR']} | \
          {'Turbine_%s_Exhaust' % s for s in 'LR'} | {'Cannon_%s_Muzzle' % c for c in ['L1', 'L2', 'R1', 'R2']}
rep['bones_expected'] = len(exp_parent)
missing = sorted(set(exp_parent) - set(limbs)); extra = sorted(set(limbs) - set(exp_parent))
if missing: defect('bones missing: %s' % missing)
if extra: defect('extra bones: %s' % extra)
wrong_parent = {b: (pname(limbs[b]), p) for b, p in exp_parent.items() if b in limbs and pname(limbs[b]) != p}
if wrong_parent: defect('wrong parents (found, expected): %s' % wrong_parent)
rep['bones_found'] = len(limbs)

# ---------------------------------------------------------------- bone rest transforms
def to_world(G):
    """file-space global matrix -> (position in Blender metres, 3x3 rotation in Z-up axes)."""
    W = CV @ G
    return Vector(W.translation) * TOM, (CV.to_3x3() @ G.to_3x3() @ CV.to_3x3().inverted())

bone_pos = {}; bone_rot_dev = {}; bone_scale = {}
for b, uid in limbs.items():
    G = F.global_matrix(sc, uid)
    p, R = to_world(G)
    # rotation of the bone frame in Z-up world: CV @ Grot (frame axes expressed in world)
    Rw = CV.to_3x3() @ G.to_3x3()
    sc_ = Rw.to_scale()
    Rn = Rw.normalized()
    dev = max(abs(Rn[i][j] - (1.0 if i == j else 0.0)) for i in range(3) for j in range(3))
    bone_pos[b] = p; bone_rot_dev[b] = dev; bone_scale[b] = tuple(sc_)
maxdev = max(bone_rot_dev.values())
rep['bone_rotation_max_dev_from_identity_in_zup_world'] = maxdev
rep['bone_rotation_max_dev_deg'] = math.degrees(math.asin(min(1.0, maxdev)))
if maxdev > 1e-4:
    defect('bones not world-aligned / identity in the Z-up (UE) frame: %s' %
           {b: round(d, 5) for b, d in bone_rot_dev.items() if d > 1e-4})
# all bones identical orientation in the file itself
Rroot = F.global_matrix(sc, limbs['root']).to_3x3().normalized()
rel = max(max(abs(a - c) for r1, r2 in zip(F.global_matrix(sc, u).to_3x3().normalized(), Rroot) for a, c in zip(r1, r2))
          for u in limbs.values())
rep['bone_rotation_max_dev_from_root_in_file'] = rel
# local rotations of non-root bones
loc_rot = {b: sc.models[u]['p'].get('Lcl Rotation', [0, 0, 0]) for b, u in limbs.items()}
nz = {b: r for b, r in loc_rot.items() if b != 'root' and max(abs(x) for x in r) > 1e-4}
rep['nonroot_local_rotation_nonzero'] = nz
rep['root_local_rotation'] = loc_rot.get('root')
rep['armature_local_rotation'] = sc.models[arm_uid]['p'].get('Lcl Rotation')
if nz: defect('non-root bones with local rotation: %s' % nz)
badscale = {b: s for b, s in bone_scale.items() if max(abs(x - 1) for x in s) > 1e-4}
if badscale: defect('bone global scale != 1 (in cm units): %s' % badscale)
pre = {b: sc.models[u]['p'].get('PreRotation') for b, u in limbs.items() if sc.models[u]['p'].get('PreRotation')}
if pre: note('PreRotation present on %d bones' % len(pre))

# cluster TransformLink + BindPose vs hierarchy
link_dev = 0.0; link_missing = set(limbs)
skin_of_geom = {}
cluster_bone = {}
for kind, ch, pa, pn in sc.conns:
    if ch in sc.deformers and pa in sc.geoms and sc.deformers[ch]['type'] == 'Skin':
        skin_of_geom[pa] = ch
    if ch in sc.models and pa in sc.deformers and sc.deformers[pa]['type'] == 'Cluster':
        cluster_bone[pa] = ch
clusters_of_skin = {}
for kind, ch, pa, pn in sc.conns:
    if ch in sc.deformers and sc.deformers[ch]['type'] == 'Cluster' and pa in sc.deformers:
        clusters_of_skin.setdefault(pa, []).append(ch)
for cu, bu in cluster_bone.items():
    e = sc.deformers[cu]['elem']
    TL = F.m4(F.arr(e, b'TransformLink'))
    G = F.global_matrix(sc, bu)
    d = max(abs(a - c) for r1, r2 in zip(TL, G) for a, c in zip(r1, r2))
    link_dev = max(link_dev, d)
    link_missing.discard(sc.models[bu]['name'])
rep['cluster_transformlink_max_dev_vs_hierarchy'] = link_dev
if link_dev > 1e-3: defect('cluster TransformLink differs from the node hierarchy by %g' % link_dev)
pose_dev = 0.0; pose_nodes = set()
for pu, p in sc.poses.items():
    for pn in F.children(p['elem'], b'PoseNode'):
        nu = F.child(pn, b'Node').props[0]
        M = F.m4(F.arr(pn, b'Matrix'))
        if nu in sc.models:
            G = F.global_matrix(sc, nu)
            pose_dev = max(pose_dev, max(abs(a - c) for r1, r2 in zip(M, G) for a, c in zip(r1, r2)))
            pose_nodes.add(sc.models[nu]['name'])
rep['bindpose_max_dev_vs_hierarchy'] = pose_dev
rep['bindpose_bones_missing'] = sorted(set(limbs) - pose_nodes)
if pose_dev > 1e-3: defect('BindPose matrices differ from the node hierarchy by %g' % pose_dev)

# ---------------------------------------------------------------- meshes, weights, materials
islands = json.load(open(RES + '/sm_airship_islands.json'))
vparts = json.load(open(RES + '/sm_airship_vertex_parts.json'))
isl = {i['id']: i for i in islands['islands']}
part_names = vparts['parts']
def expected_bone_sm(vi):
    part = part_names[vparts['vertex_part'][vi]]
    i = isl[vparts['vertex_island'][vi]]
    piece = i['piece']
    if part.startswith('Pod_'):
        return 'Thruster_' + part[4:]
    if part.startswith('Nozzle_'):
        t = part[7:]
        return 'Thruster_%s_Petal%02d' % (t, i['index']) if piece == 'petal' else 'Thruster_%s_Nozzle' % t
    if part.startswith('FanHousing_'):
        s = part[-1]
        return 'Turbine_%s_Rod' % s if piece == 'hanging_rod' else 'Turbine_' + s
    if part.startswith('FanRotor_'):
        return 'Turbine_%s_Rotor' % part[-1]
    if part.startswith('FanMount_') or part.startswith('HangStrip_') or part == 'ChainAft' or part == 'Hull':
        return 'Hull'
    if part.startswith('SearchLight_'):
        return part if piece == 'post' else part + '_Head'
    return part   # Rudder, ChainFwd, Winch_Fwd, Winch_Aft

def prop_bone(mname):
    n = mname.replace('SM_AirshipProp_', '')
    if n == 'Helm_Pedestal': return 'Helm'
    if n == 'Helm_Wheel': return 'Helm_Wheel'
    c, part = n.split('_')[1], '_'.join(n.split('_')[2:])
    return 'Cannon_' + c if part == 'Carriage' else 'Cannon_%s_%s' % (c, part)

mesh_info = {}; total_v = 0; total_t = 0
geom_of_model = {}
mat_of_model = {}
for kind, ch, pa, pn in sc.conns:
    if ch in sc.geoms and pa in sc.models: geom_of_model[pa] = ch
    if ch in sc.materials and pa in sc.models: mat_of_model.setdefault(pa, []).append(sc.materials[ch]['name'])
weight_bad = []; wrong_bone = {}; bone_vcount = {}
mesh_world = {}
for mname, mu in sorted(meshes.items()):
    gu = geom_of_model[mu]
    gd = F.geometry_data(sc.geoms[gu])
    V = np.array(gd['vertices']).reshape(-1, 3)
    nv = len(V)
    pvi = np.array(gd['pvi'])
    npoly = int((pvi < 0).sum())
    # triangles: each polygon of k corners -> k-2 tris
    ends = np.where(pvi < 0)[0]
    sizes = np.diff(np.concatenate([[-1], ends]))
    ntri = int((sizes - 2).sum())
    total_v += nv; total_t += ntri
    G = F.global_matrix(sc, mu)
    W = CV @ G
    Vw = (np.array(W.to_3x3()) @ V.T).T + np.array(W.translation)
    Vw *= TOM
    mesh_world[mname] = Vw
    # weights
    sku = skin_of_geom.get(gu)
    vb = [[] for _ in range(nv)]
    for cu in clusters_of_skin.get(sku, []):
        e = sc.deformers[cu]['elem']
        idx = F.arr(e, b'Indexes') or []; wts = F.arr(e, b'Weights') or []
        bname = sc.models[cluster_bone[cu]]['name']
        for i, w in zip(idx, wts):
            vb[i].append((bname, w))
    nbad = 0; counts = {}
    for vi, l in enumerate(vb):
        if len(l) != 1 or abs(l[0][1] - 1.0) > 1e-6:
            nbad += 1
            if len(weight_bad) < 20: weight_bad.append((mname, vi, l))
            continue
        b = l[0][0]
        counts[b] = counts.get(b, 0) + 1
        bone_vcount[b] = bone_vcount.get(b, 0) + 1
        exp = expected_bone_sm(vi) if mname == 'SM_Airship' else prop_bone(mname)
        if b != exp:
            key = '%s: %s -> %s' % (mname, exp, b)
            wrong_bone[key] = wrong_bone.get(key, 0) + 1
    mats = mat_of_model.get(mu, [])
    lm = gd['materials'][0] if gd['materials'] else None
    mesh_info[mname] = {'verts': nv, 'polys': npoly, 'tris': ntri, 'bad_weight_verts': nbad, 'bones': counts,
                        'materials': mats, 'mat_layer': (lm['mapping'], sorted(set(lm['M']))) if lm else None,
                        'uv_layers': [(u['layer'], u['name']) for u in gd['uv']],
                        'normals_layers': [(n['mapping'], n['ref']) for n in gd['normals']],
                        'smoothing_layers': [s['mapping'] for s in gd['smoothing']],
                        'model_global_is_identity_after_conv': max(abs(a - c) for r1, r2 in zip(G, Matrix.Identity(4)) for a, c in zip(r1, r2)),
                        'bbox_min_m': V.min(0).tolist() and Vw.min(0).round(4).tolist(),
                        'bbox_max_m': Vw.max(0).round(4).tolist()}
    mesh_info[mname]['_gd'] = gd
rep['total_verts'] = total_v; rep['total_tris'] = total_t
rep['bone_vertex_counts'] = bone_vcount
if weight_bad: defect('vertices not weighted 100%% to one bone (first ones): %s' % weight_bad[:5])
if wrong_bone: defect('vertices on an unexpected bone (expected -> found: count): %s' % wrong_bone)
skinned = set(bone_vcount)
if skinned & SOCKETS: defect('socket bones carry vertices: %s' % sorted(skinned & SOCKETS))
unskinned = set(exp_parent) - SOCKETS - skinned
if unskinned: defect('bones that should carry vertices have none: %s' % sorted(unskinned))
ucx = [m for m in meshes if m.upper().startswith('UCX')]
if ucx: defect('UCX meshes in the SK: %s' % ucx)
all_mats = sorted({m for l in mat_of_model.values() for m in l})
rep['materials'] = all_mats
if all_mats != ['M_Airship', 'M_AirshipProps']: defect('materials %s' % all_mats)
if mesh_info['SM_Airship']['materials'] != ['M_Airship']: defect('SM_Airship materials %s' % mesh_info['SM_Airship']['materials'])
for mname, mi in mesh_info.items():
    if mname != 'SM_Airship' and mi['materials'] != ['M_AirshipProps']:
        defect('%s materials %s' % (mname, mi['materials']))
    if len(mi['uv_layers']) != 1:
        defect('%s has %d UV layers %s' % (mname, len(mi['uv_layers']), mi['uv_layers']))
# order of mesh models in the file (UE builds material slots in import order)
rep['mesh_order_in_file'] = [sc.models[u]['name'] for u in sc.models if sc.models[u]['type'] == 'Mesh']
rep['textures'] = [(t['name'], F.props70(t['elem']).get('RelativeFilename') or F.arr(t['elem'], b'RelativeFilename'))
                   for t in sc.other.get('Texture', [])]
rep['textures'] = [(t['name'], (F.child(t['elem'], b'RelativeFilename').props[0].decode() if F.child(t['elem'], b'RelativeFilename') is not None else None))
                   for t in sc.other.get('Texture', [])]

# ---------------------------------------------------------------- SM_Airship vs Talal's mesh
tal = bpy.data.objects['SM_Airship']
dg = bpy.context.evaluated_depsgraph_get()
tme = tal.data
TW = tal.matrix_world
tV = np.array([tuple(TW @ v.co) for v in tme.vertices])
fV = mesh_world['SM_Airship']
sm = {'talal_verts': len(tV), 'fbx_verts': len(fV), 'talal_modifiers': [m.type for m in tal.modifiers],
      'talal_matrix_world_identity': TW == Matrix.Identity(4)}
if len(tV) != len(fV) or len(tV) != 36908:
    defect('SM_Airship vertex count FBX %d vs Talal %d (expected 36908)' % (len(fV), len(tV)))
else:
    d = np.linalg.norm(tV - fV, axis=1)
    sm['pos_max_delta_m'] = float(d.max()); sm['pos_mean_delta_m'] = float(d.mean())
    if d.max() > 1e-4: defect('SM_Airship positions differ from Talal\'s, max %.6f m' % d.max())
gd = mesh_info['SM_Airship']['_gd']
pvi = np.array(gd['pvi'])
corner_v = np.where(pvi < 0, ~pvi, pvi)
tl = np.array([l.vertex_index for l in tme.loops])
sm['corners_fbx'] = len(corner_v); sm['corners_talal'] = len(tl)
sm['polys_fbx'] = int((pvi < 0).sum()); sm['polys_talal'] = len(tme.polygons)
tstarts = np.array([p.loop_start for p in tme.polygons]); tsz = np.array([p.loop_total for p in tme.polygons])
fends = np.where(pvi < 0)[0]
same_topo = len(corner_v) == len(tl) and np.array_equal(corner_v, tl) and len(fends) == len(tstarts) and \
            np.array_equal(fends, tstarts + tsz - 1)
sm['face_corners_identical'] = bool(same_topo)
if not same_topo: defect('SM_Airship face corners / polygon order differ from Talal\'s mesh')
sm['talal_uv_layers'] = [u.name for u in tme.uv_layers]
uvres = []
for k, u in enumerate(tme.uv_layers):
    tuv = np.array([tuple(d.uv) for d in u.data])
    if k < len(gd['uv']):
        fuv = np.array(F.per_corner_uv(gd['uv'][k]))
        if len(fuv) == len(tuv):
            dd = np.abs(fuv - tuv).max()
            uvres.append({'layer': k, 'name': u.name, 'fbx_name': gd['uv'][k]['name'], 'max_delta': float(dd)})
            if dd > 1e-5: defect('SM_Airship UV layer %s differs from Talal\'s, max %.6f' % (u.name, dd))
        else:
            defect('SM_Airship UV layer %d corner count mismatch' % k)
    else:
        defect('SM_Airship UV layer %s missing in FBX' % u.name)
sm['uv'] = uvres
# normals (shading): FBX corner normals vs Talal's corner normals
try:
    tn = np.array([tuple(n.vector) for n in tme.corner_normals])
except AttributeError:
    tme.calc_normals_split(); tn = np.array([tuple(l.normal) for l in tme.loops])
nl = gd['normals'][0] if gd['normals'] else None
if nl is not None:
    N = np.array(nl['N']).reshape(-1, 3)
    if nl['ref'] == 'IndexToDirect' and nl['NIndex']:
        N = N[np.array(nl['NIndex'])]
    if nl['mapping'] == 'ByPolygonVertex' and len(N) == len(tn):
        G = F.global_matrix(sc, meshes['SM_Airship'])
        Rn = np.array((CV.to_3x3() @ G.to_3x3()).normalized())
        Nw = (Rn @ N.T).T
        Nw /= np.linalg.norm(Nw, axis=1, keepdims=True) + 1e-12
        dots = np.clip((Nw * tn).sum(1), -1, 1)
        ang = np.degrees(np.arccos(dots))
        sm['normals_max_angle_deg'] = float(ang.max()); sm['normals_p99_angle_deg'] = float(np.percentile(ang, 99))
        sm['normals_corners_over_1deg'] = int((ang > 1).sum())
        if (ang > 1).sum() > 0:
            note('SM_Airship corner normals differ from Talal\'s mesh on %d corners (max %.2f deg)' % ((ang > 1).sum(), ang.max()))
    else:
        sm['normals'] = 'mapping %s, %d vs %d' % (nl['mapping'], len(N), len(tn))
rep['sm_airship'] = sm

# ---------------------------------------------------------------- props UVs
cannons = ['L1', 'L2', 'R1', 'R2']
parts_c = ['Carriage', 'Barrel', 'Quoin', 'Wheel_FL', 'Wheel_FR', 'Wheel_BL', 'Wheel_BR']
cuv = {}
for c in cannons:
    for p in parts_c:
        n = 'SM_AirshipProp_Cannon_%s_%s' % (c, p)
        cuv[(c, p)] = np.array(F.per_corner_uv(mesh_info[n]['_gd']['uv'][0]))
copy_dev = max(float(np.abs(cuv[(c, p)] - cuv[('L1', p)]).max()) for c in cannons for p in parts_c)
rep['cannon_copies_uv_max_dev'] = copy_dev
if copy_dev > 1e-6: defect('the 4 cannon copies do not share identical UVs (max dev %g)' % copy_dev)
allp = np.concatenate([np.array(F.per_corner_uv(mi['_gd']['uv'][0])) for n, mi in mesh_info.items() if n != 'SM_Airship'])
rep['props_uv_range'] = [allp.min(0).tolist(), allp.max(0).tolist()]
if allp.min() < -1e-6 or allp.max() > 1 + 1e-6: defect('prop UVs outside 0..1: %s' % rep['props_uv_range'])

# ---------------------------------------------------------------- rest positions
BP = {b: np.array(p) for b, p in bone_pos.items()}
pos = {}
def chk(b, exp, tol=0.02, label='contract'):
    d = float(np.linalg.norm(BP[b] - np.array(exp)))
    pos[b] = {'found': BP[b].round(4).tolist(), 'expected': [round(x, 4) for x in exp], 'delta_m': round(d, 4), 'ref': label}
    if d > tol:
        pos[b]['FAIL'] = True
    return d
fixed = {'root': (0, 0, 0), 'Hull': (0, 0, 0),
         'Thruster_FL': (3.833, 4.656, -0.934), 'Thruster_FR': (3.833, -4.918, -1.130),
         'Thruster_RL': (-7.167, 5.130, -1.204), 'Thruster_RR': (-7.167, -5.768, -1.239),
         'Thruster_FL_Nozzle': (3.499, 4.656, -3.711), 'Thruster_FR_Nozzle': (3.499, -4.918, -3.907),
         'Thruster_RL_Nozzle': (-7.501, 5.130, -3.980), 'Thruster_RR_Nozzle': (-7.501, -5.768, -4.016),
         'Turbine_L': (-17.2, 5.35, 1.4), 'Turbine_R': (-17.2, -5.35, 1.4),
         'Turbine_L_Rotor': (-17.2, 7.6, 1.4), 'Turbine_R_Rotor': (-17.2, -7.6, 1.4),
         'Turbine_L_Rod': (-17.2, 7.6, -2.126), 'Turbine_R_Rod': (-17.2, -7.6, -2.126),
         'Rudder': (-16.364, 0, 0.7),
         'SearchLight_AftL': (11.2, 2.8, 6.55), 'SearchLight_MidL': (24.6, 2.4, 7.35),
         'SearchLight_MidR': (24.6, -2.4, 7.35), 'SearchLight_FwdC': (30.4, 0.9, 7.35),
         'SearchLight_AftL_Head': (11.2, 2.8, 9.70), 'SearchLight_MidL_Head': (24.6, 2.4, 9.70),
         'SearchLight_MidR_Head': (24.6, -2.4, 9.70), 'SearchLight_FwdC_Head': (30.4, 0.9, 10.50),
         'ChainFwd': (26.545, -2.946, 4.320), 'ChainFwd_End': (21.464, -3.353, 2.961),
         'Winch_Fwd': (30.4, 0, 5.0), 'Winch_Aft': (28.3, 0, 5.0)}
for b, e in fixed.items():
    chk(b, e)
chk('Turbine_L_Exhaust', (-18.758, 7.6, 1.4), 0.06, 'contract ~(-18.8): duct shell rear x -18.758')
chk('Turbine_R_Exhaust', (-18.758, -7.6, 1.4), 0.06, 'contract ~(-18.8): duct shell rear x -18.758')

# deck height from Talal's hull (ray down; SM_Airship only)
bm_bvh = BVHTree.FromPolygons([tuple(v) for v in tV], [tuple(p.vertices) for p in tme.polygons])
def deck_z(x, y, top=20.0):
    hit = bm_bvh.ray_cast(Vector((x, y, top)), Vector((0, 0, -1)))
    return hit[0].z if hit[0] is not None else None
geo = {}
# helm
hz = deck_z(-6.5, 0.0)
chk('Helm', (-6.5, 0.0, hz), 0.02, 'contract x -6.5 centreline, z = deck (ray) %.4f' % hz)
whl = mesh_world['SM_AirshipProp_Helm_Wheel']
wc = (whl.min(0) + whl.max(0)) / 2
geo['helm_wheel_bbox_centre'] = wc.round(4).tolist()
chk('Helm_Wheel', (BP['Helm'][0] - 0.63, 0.0, BP['Helm'][2] + 1.65), 0.02, 'Helm + Helm.blend wheel origin (-0.63, 0, 1.65)')
geo['helm_wheel_bone_minus_bbox_centre_yz'] = (BP['Helm_Wheel'] - wc)[1:].round(4).tolist()
pz = deck_z(BP['Helm_Wheel'][0] - 1.3, 0.0)
chk('PilotSeat', (BP['Helm_Wheel'][0] - 1.3, 0.0, pz), 0.02, 'wheel axle - 1.3 m, z = deck (ray)')
ped = mesh_world['SM_AirshipProp_Helm_Pedestal']
geo['helm_pedestal_min_z_minus_deck'] = float(ped[:, 2].min() - hz)
# thruster petals / flames from geometry
A = Vector((-0.13917303085327148, 0.0, -0.9902680516242981)).normalized()
SMV = mesh_world['SM_Airship']
vpart = np.array(vparts['vertex_part']); visl = np.array(vparts['vertex_island'])
petal_geo = {}
for t in ['FL', 'FR', 'RL', 'RR']:
    T0 = np.array(fixed['Thruster_' + t]) + np.array((0, 0, -0.4))
    petal_tip_h = []
    for i in islands['islands']:
        if i['part'] == 'Nozzle_' + t and i['piece'] == 'petal':
            k = i['index']
            P = SMV[visl == i['id']]
            rel = P - T0
            h = rel @ np.array(A)
            radial = rel - np.outer(h, np.array(A))
            r = np.linalg.norm(radial, axis=1)
            top = h < h.min() + 0.03
            dirp = radial.mean(0); dirp /= np.linalg.norm(dirp)
            rd = radial @ dirp            # distance along the petal's own radial direction (hinge line is tangent)
            ht, rt = float(h[top].mean()), float((rd[top].min() + rd[top].max()) / 2)   # mid-thickness of the top edge
            b = 'Thruster_%s_Petal%02d' % (t, k)
            relb = BP[b] - T0
            hb = float(relb @ np.array(A)); radb = relb - hb * np.array(A); rb = float(np.linalg.norm(radb))
            angle = math.degrees(math.acos(max(-1, min(1, float(radb @ dirp / max(rb, 1e-9))))))
            formula = T0 + 3.9 * np.array(A) + 1.45 * dirp
            d_formula = float(np.linalg.norm(BP[b] - formula))
            d_geo = float(np.linalg.norm(BP[b] - (T0 + ht * np.array(A) + rt * dirp)))
            petal_geo[b] = {'bone_h': round(hb, 4), 'bone_r': round(rb, 4), 'top_edge_h': round(ht, 4),
                            'top_edge_r': round(rt, 4), 'top_edge_r_range': [round(float(rd[top].min()), 4), round(float(rd[top].max()), 4)], 'angle_to_petal_dir_deg': round(angle, 3),
                            'd_formula_1.45': round(d_formula, 4), 'd_top_edge': round(d_geo, 4)}
            pos[b] = {'found': BP[b].round(4).tolist(), 'delta_m': round(d_geo, 4),
                      'ref': 'geometry: petal top edge (contract formula 1.45 r: %.4f m off)' % d_formula}
            if d_geo > 0.02 or angle > 1.0: pos[b]['FAIL'] = True
            petal_tip_h.append(float(h.max()))
    # flame: on the axis at the petal tips
    relf = BP['Thruster_%s_Flame' % t] - T0
    hf = float(relf @ np.array(A)); rf = float(np.linalg.norm(relf - hf * np.array(A)))
    pos['Thruster_%s_Flame' % t] = {'found': BP['Thruster_%s_Flame' % t].round(4).tolist(), 'h': round(hf, 4),
                                    'r_off_axis': round(rf, 4), 'petal_tip_h_max': round(max(petal_tip_h), 4),
                                    'delta_m': round(abs(hf - max(petal_tip_h)) + rf, 4),
                                    'ref': 'geometry: nozzle axis at the petal tips'}
    if rf > 0.01 or abs(hf - max(petal_tip_h)) > 0.05: pos['Thruster_%s_Flame' % t]['FAIL'] = True
geo['petals'] = petal_geo
# rotors / rods / searchlights / winches / chain from islands
def isl_pts(part, piece=None):
    ids = [i['id'] for i in islands['islands'] if i['part'] == part and (piece is None or i['piece'] == piece)]
    return SMV[np.isin(visl, ids)]
for s, sg in [('L', 1), ('R', -1)]:
    P = isl_pts('FanRotor_' + s)
    geo['rotor_%s_centre_yz' % s] = ((P.min(0) + P.max(0)) / 2).round(4).tolist()
    P = isl_pts('FanHousing_' + s, 'hanging_rod')
    geo['rod_%s_top' % s] = [round(float((P[:, 0].min() + P[:, 0].max()) / 2), 4), round(float((P[:, 1].min() + P[:, 1].max()) / 2), 4), round(float(P[:, 2].max()), 4)]
    P = isl_pts('FanHousing_' + s, 'shell')
    geo['duct_shell_%s_xrange' % s] = [round(float(P[:, 0].min()), 4), round(float(P[:, 0].max()), 4)]
for s in ['AftL', 'MidL', 'MidR', 'FwdC']:
    P = isl_pts('SearchLight_' + s, 'post'); H = isl_pts('SearchLight_' + s, 'head')
    geo['searchlight_%s' % s] = {'post_xy': ((P.min(0) + P.max(0)) / 2)[:2].round(4).tolist(),
                                 'post_z': [round(float(P[:, 2].min()), 3), round(float(P[:, 2].max()), 3)],
                                 'head_z': [round(float(H[:, 2].min()), 3), round(float(H[:, 2].max()), 3)],
                                 'head_xy_centre': ((H.min(0) + H.max(0)) / 2)[:2].round(4).tolist()}
for w in ['Winch_Fwd', 'Winch_Aft']:
    P = isl_pts(w, 'drum'); geo[w + '_drum_centre'] = ((P.min(0) + P.max(0)) / 2).round(4).tolist()
P = isl_pts('ChainFwd'); geo['chainfwd_bbox'] = [P.min(0).round(3).tolist(), P.max(0).round(3).tolist()]
# rudder
P = isl_pts('Rudder'); geo['rudder_bbox'] = [P.min(0).round(3).tolist(), P.max(0).round(3).tolist()]

# cannons
can = {}
for c in cannons:
    side = 1 if c[0] == 'L' else -1
    C0 = BP['Cannon_' + c]
    X = np.array((0, side, 0.0)); Z = np.array((0, 0, 1.0)); Y = np.cross(Z, X)
    # actual (possibly rolled) cannon frame from the bones: X from Muzzle - Barrel, Z from wheel plane
    aim = BP['Cannon_%s_Muzzle' % c] - BP['Cannon_%s_Barrel' % c]; aim /= np.linalg.norm(aim)
    lat = (BP['Cannon_%s_Wheel_FL' % c] - BP['Cannon_%s_Wheel_FR' % c]); lat /= np.linalg.norm(lat)
    Zr = np.cross(aim, lat); Zr /= np.linalg.norm(Zr)
    roll = math.degrees(math.atan2(float(Zr @ Y), float(Zr @ Z)))
    aim_dev = math.degrees(math.acos(min(1, abs(float(aim @ X)))))
    dz = deck_z(C0[0], C0[1], 6.0)
    info = {'origin': C0.round(4).tolist(), 'deck_z_under_origin': round(dz, 4), 'origin_minus_deck_z': round(float(C0[2] - dz), 4),
            'aim': aim.round(5).tolist(), 'aim_dev_from_pmY_deg': round(aim_dev, 4), 'roll_about_aim_deg': round(roll, 3)}
    offs = {'Barrel': (0.30, 0, 0.80), 'Muzzle': (1.86, 0, 0.80), 'Wheel_FL': (0.50, 0.525, 0.22),
            'Wheel_FR': (0.50, -0.525, 0.22), 'Wheel_BL': (-0.53, 0.525, 0.22), 'Wheel_BR': (-0.53, -0.525, 0.22),
            'Quoin': (-0.8, 0, 0.33)}
    Yr = np.cross(Zr, aim)
    for k, o in offs.items():
        b = 'Cannon_%s_%s' % (c, k)
        e_flat = C0 + o[0] * X + o[1] * Y + o[2] * Z
        e_roll = C0 + o[0] * aim + o[1] * Yr + o[2] * Zr
        d_flat = float(np.linalg.norm(BP[b] - e_flat)); d_roll = float(np.linalg.norm(BP[b] - e_roll))
        pos[b] = {'found': BP[b].round(4).tolist(), 'delta_m': round(d_roll, 4),
                  'delta_vs_unrolled_contract_frame_m': round(d_flat, 4),
                  'ref': 'contract cannon-frame offset %s in the rolled frame (deviation 1)' % (o,)}
        if d_roll > 0.02: pos[b]['FAIL'] = True
    # geometry: wheel mesh centres, barrel tip, quoin bbox
    for k in ['Wheel_FL', 'Wheel_FR', 'Wheel_BL', 'Wheel_BR']:
        Pm = mesh_world['SM_AirshipProp_Cannon_%s_%s' % (c, k)]
        info[k + '_bone_minus_mesh_bbox_centre_m'] = round(float(np.linalg.norm(BP['Cannon_%s_%s' % (c, k)] - (Pm.min(0) + Pm.max(0)) / 2)), 4)
        lowest = Pm[Pm[:, 2].argmin()]
        dzw = deck_z(lowest[0], lowest[1], lowest[2] + 0.3)
        info[k + '_lowest_minus_deck_m'] = round(float(lowest[2] - dzw), 4) if dzw is not None else None
    Pb = mesh_world['SM_AirshipProp_Cannon_%s_Barrel' % c]
    along = (Pb - BP['Cannon_%s_Barrel' % c]) @ aim
    info['barrel_tip_along_aim_minus_muzzle_bone_m'] = round(float(along.max() - (BP['Cannon_%s_Muzzle' % c] - BP['Cannon_%s_Barrel' % c]) @ aim), 4)
    tipP = Pb[along > along.max() - 0.01]
    info['muzzle_face_centre_minus_bone_m'] = round(float(np.linalg.norm(tipP.mean(0) - BP['Cannon_%s_Muzzle' % c])), 4)
    # trunnion: barrel verts farthest sideways
    lat_d = (Pb - BP['Cannon_%s_Barrel' % c]) @ Yr
    tr = Pb[np.abs(lat_d) > np.abs(lat_d).max() - 0.02]
    info['trunnion_pin_centre_minus_barrel_bone_m'] = round(float(np.linalg.norm(((tr - BP['Cannon_%s_Barrel' % c]) @ np.stack([aim, Zr]).T).mean(0))), 4)
    Pq = mesh_world['SM_AirshipProp_Cannon_%s_Quoin' % c]
    info['quoin_bone_inside_bbox'] = bool(np.all(BP['Cannon_%s_Quoin' % c] >= Pq.min(0) - 0.02) and np.all(BP['Cannon_%s_Quoin' % c] <= Pq.max(0) + 0.02))
    # muzzle clearance to Talal's hull (nearest surface)
    loc, nrm, fi, dist = bm_bvh.find_nearest(Vector(BP['Cannon_%s_Muzzle' % c].tolist()))
    info['muzzle_bone_nearest_hull_m'] = round(dist, 4)
    # carriage vs hull nearest at rest
    Pc = np.concatenate([mesh_world['SM_AirshipProp_Cannon_%s_%s' % (c, p)] for p in parts_c])
    dmin = min(bm_bvh.find_nearest(Vector(p.tolist()))[3] for p in Pc[::7])
    info['cannon_verts_min_dist_to_hull_m(sampled)'] = round(dmin, 4)
    can[c] = info
geo['cannons'] = can
rep['geometry'] = geo
rep['positions'] = pos
fails = {b: v for b, v in pos.items() if v.get('FAIL')}
if fails: defect('bone rest positions off by > 2 cm (or off-geometry): %s' % {b: (v['found'], v.get('expected'), v['delta_m'], v['ref']) for b, v in fails.items()})
unchecked = sorted(set(limbs) - set(pos))
rep['positions_unchecked'] = unchecked
rep['positions_ue_cm'] = {b: [round(p[0] * 100, 2), round(-p[1] * 100, 2), round(p[2] * 100, 2)] for b, p in BP.items()}

for mi in mesh_info.values():
    mi.pop('_gd', None)
rep['meshes'] = mesh_info
os.makedirs(os.path.dirname(OUT), exist_ok=True)
json.dump(rep, open(OUT, 'w'), indent=1, default=lambda o: o.tolist() if hasattr(o, 'tolist') else str(o))
print('[verify_fbx] defects:', len(rep['defects']), 'notes:', len(rep['notes']), '->', OUT)
