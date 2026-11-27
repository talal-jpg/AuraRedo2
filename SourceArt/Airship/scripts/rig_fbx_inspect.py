"""Step 6a: read an FBX file's raw node tree (Blender's low-level FBX parser, no importer logic) and report what Unreal's
FBX importer will see. Adapted from the Burrower's fbx_inspect.py.

  blender -b --factory-startup --python rig/scripts/rig_fbx_inspect.py -- FILE.fbx --json OUT.json [--csv BONES.csv]

Checks: FBX version, GlobalSettings axes + units, Model nodes by type and their parent tree, one Skin deformer per mesh,
clusters linked to bones, every vertex weighted exactly once with sum 1, BindPose covering all bones, cluster
TransformLink = bind pose matrix, node-chain globals = bind pose, material order, animation stacks.
Bone table in Unreal component space: file (Y-up, cm) -> Z-up by the importer's scene conversion Rx(+90) -> UE (x, -y, z)
with quaternion (x, -y, z, -w) as FFbxDataConverter does.
"""
import sys, os, json, math, csv
import numpy as np
import bpy
import addon_utils
for p in addon_utils.paths():
    if os.path.isdir(os.path.join(p, 'io_scene_fbx')):
        sys.path.insert(0, p)
        break
from io_scene_fbx import parse_fbx
from mathutils import Matrix, Euler, Quaternion

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
path = argv[0]
out_json = argv[argv.index('--json') + 1] if '--json' in argv else ''
out_csv = argv[argv.index('--csv') + 1] if '--csv' in argv else ''
root, version = parse_fbx.parse(path)


def child(el, name):
    for e in el.elems:
        if e.id == name.encode():
            return e
    return None


def children(el, name):
    return [e for e in el.elems if e.id == name.encode()]


def props70(el):
    p = child(el, 'Properties70'); d = {}
    if p is None:
        return d
    for e in p.elems:
        k = e.props[0].decode(); d[k] = e.props[4:] if len(e.props) > 4 else []
    return d


def name_of(el):
    return el.props[1].split(b'\x00\x01')[0].decode()


R = {'file': os.path.basename(path), 'fbx_version': version, 'size_mb': round(os.path.getsize(path) / 1e6, 2)}
gs = props70(child(root, 'GlobalSettings'))
R['global'] = {k: (gs[k][0] if gs.get(k) else None) for k in
               ('UpAxis', 'UpAxisSign', 'FrontAxis', 'FrontAxisSign', 'CoordAxis', 'CoordAxisSign',
                'UnitScaleFactor', 'OriginalUnitScaleFactor', 'TimeMode', 'CustomFrameRate')}
creator = child(root, 'Creator'); R['creator'] = creator.props[0].decode() if creator is not None else ''

objs = child(root, 'Objects')
byid = {e.props[0]: e for e in objs.elems}
models = {i: e for i, e in byid.items() if e.id == b'Model'}
geoms = {i: e for i, e in byid.items() if e.id == b'Geometry'}
deformers = {i: e for i, e in byid.items() if e.id == b'Deformer'}
nodeattrs = {i: e for i, e in byid.items() if e.id == b'NodeAttribute'}
materials = [e for e in objs.elems if e.id == b'Material']
poses = [e for e in objs.elems if e.id == b'Pose']
stacks = [e for e in objs.elems if e.id == b'AnimationStack']
curves = [e for e in objs.elems if e.id == b'AnimationCurve']
conns = [(c.props[1], c.props[2], c.props[0].decode()) for c in child(root, 'Connections').elems]
parent = {}
for src, dst, kind in conns:
    if src in models and (dst in models or dst == 0):
        parent[src] = dst
mtype = {i: e.props[2].decode() for i, e in models.items()}
R['model_counts'] = {t: sum(1 for v in mtype.values() if v == t) for t in sorted(set(mtype.values()))}
R['materials_in_file_order'] = [name_of(m) for m in materials]


def path_of(i):
    p = []
    while i in models:
        p.append(name_of(models[i])); i = parent.get(i, 0)
    return '/'.join(reversed(p))


def local_matrix(e):
    p = props70(e)
    t = [float(x) for x in p.get('Lcl Translation', [0, 0, 0])]
    r = [math.radians(float(x)) for x in p.get('Lcl Rotation', [0, 0, 0])]
    s = [float(x) for x in p.get('Lcl Scaling', [1, 1, 1])]
    M = Matrix.Translation(t) @ Euler(r, 'XYZ').to_matrix().to_4x4() @ Matrix.Diagonal((*s, 1.0))
    if 'PreRotation' in p:
        pr = [math.radians(float(x)) for x in p['PreRotation']]
        M = Matrix.Translation(t) @ Euler(pr, 'XYZ').to_matrix().to_4x4() @ Euler(r, 'XYZ').to_matrix().to_4x4() @ Matrix.Diagonal((*s, 1.0))
    return M


def global_matrix(i):
    M = Matrix.Identity(4)
    chain = []
    while i in models:
        chain.append(i); i = parent.get(i, 0)
    for j in reversed(chain):
        M = M @ local_matrix(models[j])
    return M


tree = []
for i, e in models.items():
    if mtype[i] == 'Mesh':
        continue
    p = props70(e)
    tree.append({'name': name_of(e), 'type': mtype[i], 'path': path_of(i),
                 'parent': name_of(models[parent[i]]) if parent.get(i, 0) in models else '<scene root>',
                 'T': [round(float(x), 4) for x in p.get('Lcl Translation', [0, 0, 0])],
                 'R': [round(float(x), 3) for x in p.get('Lcl Rotation', [0, 0, 0])],
                 'S': [round(float(x), 4) for x in p.get('Lcl Scaling', [1, 1, 1])],
                 'PreRotation': [round(float(x), 3) for x in p['PreRotation']] if 'PreRotation' in p else None})
R['skeleton_nodes'] = sorted(tree, key=lambda t: t['path'])
mesh_nodes = {}
for i, t in mtype.items():
    if t == 'Mesh':
        pp = parent.get(i, 0)
        mesh_nodes[name_of(models[i])] = dict(parent=name_of(models[pp]) if pp in models else '<scene root>',
                                              T=[round(float(x), 4) for x in props70(models[i]).get('Lcl Translation', [0, 0, 0])],
                                              R=[round(float(x), 3) for x in props70(models[i]).get('Lcl Rotation', [0, 0, 0])],
                                              S=[round(float(x), 4) for x in props70(models[i]).get('Lcl Scaling', [1, 1, 1])])
R['limbnode_attributes'] = sum(1 for e in nodeattrs.values() if e.props[2] == b'LimbNode')

# ---- skins
geom_of_model = {}
mats_of_model = {}
for src, dst, kind in conns:
    if src in geoms and dst in models:
        geom_of_model[dst] = src
    if dst in models and byid.get(src) is not None and byid[src].id == b'Material':
        mats_of_model.setdefault(dst, []).append(name_of(byid[src]))
skin_of_geom, bone_of_cluster, clusters_of_skin = {}, {}, {}
for src, dst, kind in conns:
    if src in deformers and dst in geoms and deformers[src].props[2] == b'Skin':
        skin_of_geom.setdefault(dst, []).append(src)
    if src in models and dst in deformers and deformers[dst].props[2] == b'Cluster':
        bone_of_cluster[dst] = src
    if src in deformers and dst in deformers and deformers[src].props[2] == b'Cluster':
        clusters_of_skin.setdefault(dst, []).append(src)


def mat(el, name):
    c = child(el, name)
    return np.array(c.props[0], float).reshape(4, 4).T if c is not None else None   # FBX stores column-major


skins = []
worst_sum = 0.0; tot_v = 0; unweighted = 0; max_inf = 0; multi = 0
transform_links = {}
per_bone = {}
for mi, t in mtype.items():
    if t != 'Mesh':
        continue
    g = geoms[geom_of_model[mi]]
    nv = len(child(g, 'Vertices').props[0]) // 3
    sk = skin_of_geom.get(geom_of_model[mi], [])
    ent = {'mesh': name_of(models[mi]), 'verts': nv, 'skins': len(sk), 'materials': mats_of_model.get(mi, []), 'clusters': {}}
    pvi = np.array(child(g, 'PolygonVertexIndex').props[0], int)     # polygon ends are stored as ~index
    sizes = np.diff(np.concatenate([[-1], np.where(pvi < 0)[0]]))
    ent['polys'] = int(len(sizes)); ent['tris'] = int((sizes - 2).sum())
    if len(sk) == 1:
        wsum = np.zeros(nv); ninf = np.zeros(nv, int)
        for c in clusters_of_skin.get(sk[0], []):
            ce = deformers[c]; bone = name_of(models[bone_of_cluster[c]])
            idx = child(ce, 'Indexes'); w = child(ce, 'Weights')
            idx = np.array(idx.props[0], int) if idx is not None else np.zeros(0, int)
            w = np.array(w.props[0], float) if w is not None else np.zeros(0)
            np.add.at(wsum, idx, w); np.add.at(ninf, idx, 1)
            if len(idx):
                ent['clusters'][bone] = int(len(idx))
                per_bone[bone] = per_bone.get(bone, 0) + int(len(idx))
            tl = mat(ce, 'TransformLink')
            if tl is not None:
                transform_links.setdefault(bone, []).append(tl)
        worst_sum = max(worst_sum, float(np.abs(wsum - 1).max()))
        unweighted += int((ninf == 0).sum()); max_inf = max(max_inf, int(ninf.max())); multi += int((ninf > 1).sum())
    tot_v += nv
    skins.append(ent)
R['meshes'] = len(skins)
R['meshes_with_one_skin'] = sum(1 for s in skins if s['skins'] == 1)
R['total_vertices'] = tot_v
R['total_triangles'] = int(sum(e['tris'] for e in skins))
R['weights'] = {'worst_abs(sum-1)': worst_sum, 'unweighted_vertices': unweighted, 'vertices_with_more_than_one_bone': multi,
                'max_influences': max_inf}
R['clusters_total'] = sum(len(s['clusters']) for s in skins)
R['per_bone_vertices'] = per_bone
R['bind_matrix_spread'] = {b: float(max(np.abs(m - ms[0]).max() for m in ms)) for b, ms in transform_links.items()}
R['mesh_list'] = skins
R['mesh_nodes'] = mesh_nodes

# ---- bind pose
lim_ids = {i for i, t in mtype.items() if t == 'LimbNode'}
bp = []
pose_mats = {}
for p in poses:
    typ = child(p, 'Type'); typ = typ.props[0].decode() if typ is not None else ''
    nodes = children(p, 'PoseNode')
    names = []
    for n in nodes:
        nid = child(n, 'Node').props[0]
        if nid in models:
            nm = name_of(models[nid]); names.append(nm)
            m = np.array(child(n, 'Matrix').props[0], float).reshape(4, 4).T
            if nid in lim_ids:
                pose_mats.setdefault(nm, m)
    bones_in = [n for n in names if n in {name_of(models[i]) for i in lim_ids}]
    agree = {b: float(np.abs(pose_mats[b] - transform_links[b][0]).max()) for b in transform_links if b in pose_mats}
    bp.append({'name': name_of(p), 'type': typ, 'nodes': len(nodes), 'bones_in_pose': len(bones_in),
               'max_diff_pose_vs_cluster_TransformLink': max(agree.values()) if agree else None})
R['poses'] = {'count': len(bp), 'bones_in_poses_union': len(pose_mats), 'all': bp[:3],
              'max_diff_pose_vs_cluster': max((b['max_diff_pose_vs_cluster_TransformLink'] or 0) for b in bp) if bp else None}

# ---- node chain vs bind pose, and the Unreal view of every bone
RCONV = Matrix.Rotation(math.radians(90), 4, 'X')        # UE's FbxAxisSystem conversion Y-up -> Z-up (right-handed)
bones_ue = []
node_vs_pose = 0.0
for i in lim_ids:
    nm = name_of(models[i])
    G = global_matrix(i)
    if nm in pose_mats:
        node_vs_pose = max(node_vs_pose, float(np.abs(np.array(G) - pose_mats[nm]).max()))
    Gz = RCONV @ G
    t = Gz.to_translation(); q = Gz.to_quaternion()
    qu = Quaternion((-q.w, q.x, -q.y, q.z))                # FFbxDataConverter::ConvertRotToQuat (x, -y, z, -w)
    ang = math.degrees(qu.angle) if qu.angle <= math.pi else 360 - math.degrees(qu.angle)
    pp = parent.get(i, 0)
    bones_ue.append(dict(bone=nm, parent=name_of(models[pp]) if pp in lim_ids else None,
                         ue_cm=[round(t.x, 3) + 0.0, round(-t.y, 3) + 0.0, round(t.z, 3) + 0.0],
                         ue_rest_rotation_deg=round(abs(min(ang, 360 - ang)), 5), scale=[round(x, 5) for x in Gz.to_scale()]))
order = {t['name']: k for k, t in enumerate(R['skeleton_nodes'])}
bones_ue.sort(key=lambda b: order.get(b['bone'], 0))
R['node_chain_vs_bindpose_max_diff'] = node_vs_pose
R['bones_ue'] = bones_ue
R['ue_max_rest_rotation_deg'] = max(b['ue_rest_rotation_deg'] for b in bones_ue)

# ---- animation
R['anim_stacks'] = []
for s in stacks:
    p = props70(s)
    ls = p.get('LocalStop', [0]); ktime = 46186158000
    R['anim_stacks'].append({'name': name_of(s), 'seconds': round(float(ls[0]) / ktime, 3) if ls else None})
R['anim_curves'] = len(curves)

# ---- verdict
lim = [t for t in R['skeleton_nodes'] if t['type'] == 'LimbNode']
problems = []
if R['global']['UpAxis'] != 1:
    problems.append('not Y-up')
if abs((R['global']['UnitScaleFactor'] or 0) - 1.0) > 1e-6:
    problems.append('UnitScaleFactor != 1')
if R['meshes_with_one_skin'] != R['meshes']:
    problems.append('mesh without exactly one skin')
if worst_sum > 1e-6 or unweighted or multi:
    problems.append('weights not exactly one bone at 1.0 per vertex')
if R['poses']['bones_in_poses_union'] < len(per_bone):
    problems.append('bind pose misses skinned bones')
if any(v > 1e-4 for v in R['bind_matrix_spread'].values()):
    problems.append('clusters disagree on bind matrices')
if node_vs_pose > 1e-3:
    problems.append('node transforms differ from the bind pose')
arm_nodes = [t for t in R['skeleton_nodes'] if t['type'] == 'Null']
if not arm_nodes or arm_nodes[0]['name'] != 'Armature' or arm_nodes[0]['T'] != [0, 0, 0] or arm_nodes[0]['R'] != [0, 0, 0]:
    problems.append('Armature node missing or not identity')
roots = [t for t in lim if t['parent'] == 'Armature']
if [t['name'] for t in roots] != ['root']:
    problems.append('root bone is not the only child of Armature: %s' % [t['name'] for t in roots])
if any(m['T'] != [0, 0, 0] or m['R'] != [0, 0, 0] or m['S'] != [1, 1, 1] for m in mesh_nodes.values()):
    problems.append('a mesh node has a non-identity transform')
R['problems'] = problems
summary = {k: v for k, v in R.items() if k not in ('skeleton_nodes', 'bones_ue', 'mesh_list', 'mesh_nodes', 'per_bone_vertices', 'bind_matrix_spread')}
print(json.dumps(summary, indent=1, default=str))
if out_json:
    with open(out_json, 'w') as f:
        json.dump(R, f, indent=1, default=str)
if out_csv:
    with open(out_csv, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['bone', 'parent', 'ue_x_cm', 'ue_y_cm', 'ue_z_cm', 'ue_rest_rotation_deg', 'skinned_vertices'])
        for b in bones_ue:
            w.writerow([b['bone'], b['parent'] or '', *b['ue_cm'], b['ue_rest_rotation_deg'], per_bone.get(b['bone'], 0)])
print('[inspect] problems:', problems)
