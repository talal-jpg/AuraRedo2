"""Round 3 export: offline check of every FBX in rig/detail/r3export/fbx/ with Blender's low-level FBX parser
(verify_fbxlib: no importer logic, none of the rig_* / r3_prep code paths that wrote the files).

  BL_MEM_MAX=6G blender_capped.sh --python SourceArt/Airship/scripts/r3_fbx_check.py -- [--r2-repro FBX]

Opens rig/detail/r3export/AirshipR3_export.blend read-only (the source objects: positions, UVs, normals are compared
corner by corner) and reads manifest.json / manifest_arrays.npz (per-vertex bone, per-face palette index).
Checks, per file:
  skeleton (SK_Airship*.fbx): every LimbNode / the Armature node against today's SK_Airship (round 2,
    rig/export/SK_Airship.fbx): names in file order, parents, local transform properties, global matrices, BindPose
    matrices and cluster TransformLinks (identical within 1e-4 cm), GlobalSettings;
  meshes: names and order (= Unreal's material slot order), one material each and the global slot order M_Airship,
    M_AirshipProps, M_AirshipR3_Detail; vertices / polygons / triangles; UV layers (names, count); UV1 = an integer
    palette index, the same on every corner of a face, equal to the manifest; skin: every vertex in exactly one cluster
    with weight 1, on the manifest's bone; positions, polygon corners, UV layers and corner normals against the export
    blend object; LOD files: everything but the Moving object identical to LOD0;
  static meshes: no armature / skin / pose, one material, two UV layers, identity node after the axis conversion,
    positions / UVs / normals against the source; the turrets also against round 2's turret FBX (same frame, same UV0);
  Unreal build risks: half-float UVs (Unreal's default for skeletal and non-Nanite static meshes: the texel error per
    channel on its page), corners Unreal's builders would weld (same vertex and normal, every UV channel within
    1/1024 but not equal: the static mesh builder's fixed UVsEqual threshold, the skeletal default ThresholdUV),
    estimated render vertices;
  bounds in UE cm against round 2's SK and the manifest; triangle counts per LOD against the manifest.
--r2-repro FBX: a fresh round-2 export (rig_export.py without flags, --out elsewhere) compared element by element with
rig/export/SK_Airship.fbx (header and creation time skipped): round 2 stays reproducible.
Writes r3export/checks/fbx_check.json and Docs/Airship/round3/export_fbx_check.json.
"""
import bpy, sys, os, json, math, time, hashlib
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np
from mathutils import Matrix
import verify_fbxlib as F
import r3_common as RC
from io_scene_fbx.fbx_utils import RIGHT_HAND_AXES
from bpy_extras.io_utils import axis_conversion

A = RC.argv()
FBX_DIR = RC.OUT + '/fbx'
R2_SK = RC.RIG_DIR + '/export/SK_Airship.fbx'
R2_TURRET = {n: RC.RIG_DIR + '/export/%s.fbx' % n for n in RC.TURRETS.values()}
R2_REPRO = RC.arg(A, '--r2-repro', '')
TOL_CM = 1e-4 * 100          # 1e-4 m in file cm
log = RC.Log('r3_fbx_check')
rep = dict(started=time.strftime('%Y-%m-%d %H:%M:%S'), protected_start=RC.protected_state(), defects=[], notes=[],
           files={})


def defect(m):
    rep['defects'].append(m); log('[DEFECT]', m)


def note(m):
    rep['notes'].append(m); log('[note]', m)


MAN = RC.load_json(RC.MANIFEST)
ARR = np.load(RC.ARRAYS)
BONES = [str(b) for b in ARR['bone_names']]


def arr_key(name):
    return name.replace('SM_Airship', '').strip('_') or 'Hull'


# ------------------------------------------------------------------ the source objects (export blend, read only)
bpy.ops.wm.open_mainfile(filepath=RC.EXPORT_BLEND)
rep['export_blend_md5'] = RC.md5_file(RC.EXPORT_BLEND)
arm = bpy.data.objects['Armature']
for pb in arm.pose.bones:
    pb.matrix_basis = Matrix.Identity(4)
SRC = {}


def src_arrays(o, local=False):
    me = o.data
    d = RC.mesh_np(me)
    M = np.eye(4) if local else np.array(o.matrix_world)
    co = d['co'] @ M[:3, :3].T + M[:3, 3]
    try:
        cn = np.empty(len(me.loops) * 3); me.corner_normals.foreach_get('vector', cn); cn = cn.reshape(-1, 3)
    except AttributeError:
        me.calc_normals_split(); cn = np.array([tuple(l.normal) for l in me.loops])
    cn = cn @ M[:3, :3].T
    cn /= np.linalg.norm(cn, axis=1, keepdims=True) + 1e-12
    uv = {u.name: RC.uv_get(me, u.name) for u in me.uv_layers}
    return dict(co=co, lv=d['lv'], ls=d['ls'], lt=d['lt'], cn=cn, uv=uv, nP=len(me.polygons), fa=d['fa'], lp=d['lp'])


def src_of(name):
    if name not in SRC:
        o = bpy.data.objects[name]
        SRC[name] = src_arrays(o, local=name in RC.TURRETS.values())
    return SRC[name]


# ------------------------------------------------------------------ FBX helpers
def fbx_axes(sc):
    gs = sc.global_settings
    key = ((int(gs['UpAxis']), int(gs['UpAxisSign'])), (int(gs['FrontAxis']), int(gs['FrontAxisSign'])),
           (int(gs['CoordAxis']), int(gs['CoordAxisSign'])))
    inv = {v: k for k, v in RIGHT_HAND_AXES.items()}
    up, fwd = inv[key]
    return axis_conversion(from_forward=fwd, from_up=up).to_4x4(), float(gs.get('UnitScaleFactor', 1.0)) * 0.01


def npa(e, id_):
    c = F.child(e, id_)
    return None if c is None else np.asarray(c.props[0])


def mesh_records(sc):
    """per Mesh model in file order: name, geometry arrays, materials, skin (vertex -> [(bone, w)])"""
    CV, TOM = fbx_axes(sc)
    geom_of, mats_of = {}, {}
    for kind, ch, pa, pn in sc.conns:
        if ch in sc.geoms and pa in sc.models:
            geom_of[pa] = ch
        if ch in sc.materials and pa in sc.models:
            mats_of.setdefault(pa, []).append(sc.materials[ch]['name'])
    skin_of, clusters, cbone = {}, {}, {}
    for kind, ch, pa, pn in sc.conns:
        if ch in sc.deformers and pa in sc.geoms and sc.deformers[ch]['type'] == 'Skin':
            skin_of[pa] = ch
        if ch in sc.deformers and sc.deformers[ch]['type'] == 'Cluster' and pa in sc.deformers:
            clusters.setdefault(pa, []).append(ch)
        if ch in sc.models and pa in sc.deformers and sc.deformers[pa]['type'] == 'Cluster':
            cbone[pa] = sc.models[ch]['name']
    out = []
    for uid, m in sc.models.items():
        if m['type'] != 'Mesh':
            continue
        g = sc.geoms[geom_of[uid]]
        e = g['elem']
        V = npa(e, b'Vertices').reshape(-1, 3)
        pvi = npa(e, b'PolygonVertexIndex').astype(np.int64)
        cv = np.where(pvi < 0, ~pvi, pvi)
        ends = np.nonzero(pvi < 0)[0]
        sizes = np.diff(np.concatenate([[-1], ends]))
        G = F.global_matrix(sc, uid)
        W = np.array(CV @ G)
        Vw = (V @ W[:3, :3].T + W[:3, 3]) * TOM
        uvs = []
        for le in F.children(e, b'LayerElementUV'):
            nm = F.child(le, b'Name').props[0].decode()
            ref = F.child(le, b'ReferenceInformationType').props[0].decode()
            UV = npa(le, b'UV').reshape(-1, 2)
            if ref == 'IndexToDirect':
                UV = UV[npa(le, b'UVIndex').astype(np.int64)]
            uvs.append((nm, UV))
        N = None
        for le in F.children(e, b'LayerElementNormal'):
            ref = F.child(le, b'ReferenceInformationType').props[0].decode()
            N = npa(le, b'Normals').reshape(-1, 3)
            if ref == 'IndexToDirect':
                N = N[npa(le, b'NormalsIndex').astype(np.int64)]
        Rn = np.array((CV.to_3x3() @ G.to_3x3()).normalized())
        Nw = N @ Rn.T if N is not None else None
        if Nw is not None:
            Nw /= np.linalg.norm(Nw, axis=1, keepdims=True) + 1e-12
        mat_layers = [(F.child(le, b'MappingInformationType').props[0].decode(), npa(le, b'Materials'))
                      for le in F.children(e, b'LayerElementMaterial')]
        sk = skin_of.get(geom_of[uid])
        vb = [[] for _ in range(len(V))]
        for cu in clusters.get(sk, []):
            ce = sc.deformers[cu]['elem']
            idx = npa(ce, b'Indexes'); wts = npa(ce, b'Weights')
            if idx is None:
                continue
            for i, w in zip(idx.tolist(), wts.tolist()):
                vb[i].append((cbone[cu], w))
        out.append(dict(name=m['name'], uid=uid, V=V, Vw=Vw, pvi=pvi, cv=cv, sizes=sizes, uvs=uvs, N=N, Nw=Nw,
                        mats=mats_of.get(uid, []), mat_layers=mat_layers, skin=sk is not None, vb=vb,
                        node_identity=float(np.abs(np.array(G) - np.eye(4)).max())))
    return out


def tri_count(rec):
    return int((rec['sizes'] - 2).sum())


def h(a):
    return hashlib.md5(np.ascontiguousarray(a).tobytes()).hexdigest()


def compare_to_source(rec, src, pages):
    """FBX mesh vs the export blend object: positions (m), polygon corners, UVs per layer, corner normals"""
    r = {}
    nv = len(src['co'])
    r['verts'] = [len(rec['Vw']), nv]
    if len(rec['Vw']) != nv:
        defect('%s: %d vertices in the FBX, %d in the source' % (rec['name'], len(rec['Vw']), nv))
        return r
    d = np.linalg.norm(rec['Vw'] - src['co'], axis=1)
    r['pos_max_m'] = float(d.max())
    if d.max() > 1e-5:
        defect('%s: positions differ from the source by up to %.6f m' % (rec['name'], d.max()))
    same = len(rec['cv']) == len(src['lv']) and np.array_equal(rec['cv'], src['lv']) and \
        np.array_equal(np.nonzero(rec['pvi'] < 0)[0], src['ls'] + src['lt'] - 1)
    r['corners_identical'] = bool(same)
    if not same:
        defect('%s: polygon corners / order differ from the source' % rec['name'])
        return r
    names = [n for n, _ in rec['uvs']]
    r['uv_layers'] = names
    if names != list(src['uv']):
        defect('%s: UV layers %s, source %s' % (rec['name'], names, list(src['uv'])))
    r['uv_max_delta'] = {}
    for n, uv in rec['uvs']:
        if n in src['uv']:
            dd = float(np.abs(uv - src['uv'][n]).max())
            r['uv_max_delta'][n] = dd
            if dd > 1e-6:
                defect('%s: UV layer %s differs from the source by %.2e' % (rec['name'], n, dd))
    if rec['Nw'] is not None:
        dots = np.clip((rec['Nw'] * src['cn']).sum(1), -1, 1)
        ang = np.degrees(np.arccos(dots))
        r['normal_max_deg'] = float(ang.max())
        r['normal_corners_over_0p5deg'] = int((ang > 0.5).sum())
        # Blender's Mesh.transform (the export's metres -> cm, Z-up -> Y-up) re-encodes custom normals; on faces of a
        # few mm^2 that moves them by up to a few degrees (seen: 11 faces of 1.4-2.5 mm^2, 2.3 deg). Faces under 1 cm^2
        # are reported, larger ones are a defect.
        big = src['fa'][src['lp']] >= 1e-4
        r['normal_corners_over_0p5deg_faces_ge_1cm2'] = int(((ang > 0.5) & big).sum())
        if ((ang > 0.5) & big).sum():
            defect('%s: %d corner normals on faces of 1 cm^2 or more differ from the source by > 0.5 deg (max %.2f)'
                   % (rec['name'], ((ang > 0.5) & big).sum(), ang[big].max()))
        elif (ang > 0.5).sum():
            sm = (ang > 0.5) & ~big
            note('%s: %d corner normals on %d faces under 1 cm^2 (largest %.1f mm^2) differ by up to %.2f deg (Mesh.transform '
                 're-encoding custom normals of tiny faces; invisible)' % (rec['name'], sm.sum(), len(np.unique(src['lp'][sm])),
                                                                          src['fa'][src['lp'][sm]].max() * 1e6, ang[sm].max()))
    else:
        defect('%s: no normals layer' % rec['name'])
    return r


def palette_check(rec, want):
    """UV1 'R3Palette': integer x, y 0, constant per polygon, = the manifest"""
    uvd = dict(rec['uvs'])
    if RC.UV_PAL not in uvd:
        defect('%s: no %s layer' % (rec['name'], RC.UV_PAL))
        return {}
    u = uvd[RC.UV_PAL]
    integral = float(np.abs(u[:, 0] - np.round(u[:, 0])).max())
    yzero = float(np.abs(u[:, 1]).max())
    lp = np.repeat(np.arange(len(rec['sizes'])), rec['sizes'])
    first = np.round(u[np.concatenate([[0], np.cumsum(rec['sizes'])[:-1]]), 0]).astype(np.int64)
    const = bool(np.array_equal(np.round(u[:, 0]).astype(np.int64), first[lp]))
    r = dict(integral_err=integral, y_max=yzero, constant_per_face=const, range=[int(first.min()), int(first.max())])
    if integral > 1e-6 or yzero > 1e-6 or not const or first.min() < 0 or first.max() > 23:
        defect('%s: R3Palette not an integer per face in 0..23: %s' % (rec['name'], r))
    if want is not None:
        eq = bool(len(want) == len(first) and np.array_equal(first, want))
        r['equals_manifest'] = eq
        if not eq:
            defect('%s: palette index per face differs from the manifest' % rec['name'])
        r['slots'] = {RC.PALETTE_SLOTS[i][0]: int((first == i).sum()) for i in np.unique(first)}
    return r


def skin_check(rec, want_bone):
    bad = [i for i, l in enumerate(rec['vb']) if len(l) != 1 or abs(l[0][1] - 1.0) > 1e-6]
    r = dict(verts=len(rec['vb']), not_rigid=len(bad))
    if bad:
        defect('%s: %d vertices not 100 %% on one bone (first %s)' % (rec['name'], len(bad), [(i, rec['vb'][i]) for i in bad[:3]]))
        return r
    got = np.array([BONES.index(l[0][0]) for l in rec['vb']])
    if want_bone is not None:
        wrong = int((got != want_bone).sum()) if len(got) == len(want_bone) else -1
        r['wrong_bone'] = wrong
        if wrong:
            defect('%s: %d vertices on another bone than the manifest' % (rec['name'], wrong))
    r['bones'] = len(np.unique(got))
    return r


UVPAGE = {'SM_Airship': {RC.UV_INK: 4096, RC.UV_HULL_INK: 4096}, 'prop': {RC.UV_INK: 2048},
          RC.MOVING: {RC.UV_INK: 4096}, RC.HULLDET: {RC.UV_INK: 4096}}


def page_sizes(name):
    if name == RC.HULL_OBJ:
        return UVPAGE['SM_Airship']
    if name.startswith(RC.PROP_PREFIX) or name in RC.TURRETS.values():
        return UVPAGE['prop']
    if name.startswith(RC.MOVING):
        return UVPAGE[RC.MOVING]
    return UVPAGE[RC.HULLDET]


def ue_risks(rec):
    """half-float UV error (texels on the page) and the corners Unreal's builders would weld"""
    pages = page_sizes(rec['name'])
    r = dict(half_float_texel_err={}, weld={})
    for n, uv in rec['uvs']:
        hf = uv.astype(np.float16).astype(np.float64)
        e = np.abs(hf - uv).max(1)
        res = pages.get(n, 0)
        if n == RC.UV_PAL:
            r['half_float_texel_err'][n] = dict(max_abs=float(e.max()), note='integer index: exact in half float')
        elif res:
            r['half_float_texel_err'][n] = dict(page=res, max=round(float(e.max() * res), 3),
                                                p99=round(float(np.percentile(e, 99) * res), 3))
    # weld: corners of one vertex, normals within 2e-5 per component, every UV channel within 1/1024 but not identical
    cv = rec['cv']
    U = np.concatenate([uv for _, uv in rec['uvs']], 1)
    key = np.concatenate([cv[:, None], np.round(rec['N'] * 1e6).astype(np.int64) if rec['N'] is not None else
                          np.zeros((len(cv), 3), np.int64), np.round(U * 2 ** 24).astype(np.int64)], 1)
    uk, inv = np.unique(key, axis=0, return_inverse=True)
    r['render_vertices_est'] = int(len(uk))
    # candidate groups: same vertex with more than one distinct key
    vfirst = uk[:, 0]
    cnt = np.bincount(vfirst, minlength=len(rec['V']))
    multi = np.nonzero(cnt > 1)[0]
    starts = np.concatenate([[0], np.cumsum(np.bincount(vfirst, minlength=len(rec['V'])))])
    nrm = uk[:, 1:4] / 1e6
    uvk = uk[:, 4:] / 2 ** 24
    pairs, worst = 0, 0.0
    deltas = []
    T = 1.0 / 1024
    for v in multi.tolist():
        a, b = starts[v], starts[v + 1]
        if b - a < 2:
            continue
        nn = nrm[a:b]; uu = uvk[a:b]
        for i in range(b - a):
            dn = np.abs(nn[i + 1:] - nn[i]).max(1) <= 2e-5
            du = np.abs(uu[i + 1:] - uu[i]).max(1)
            hit = dn & (du <= T) & (du > 0)
            if hit.any():
                pairs += int(hit.sum())
                worst = max(worst, float(du[hit].max()))
                deltas += du[hit].tolist()
    dl = np.array(deltas)
    r['weld'] = dict(pairs=pairs, worst_uv_delta=worst, worst_texels_4096=round(worst * 4096, 3),
                     pairs_over_1_65536=int((dl > 1.0 / 65536).sum()), pairs_over_quarter_texel_4096=int((dl > 0.25 / 4096).sum()),
                     pairs_over_1_texel_4096=int((dl > 1.0 / 4096).sum()),
                     rule='same vertex + normal, all UV channels within 1/1024 but not equal: Unreal\'s builders weld these '
                          '(static: fixed 1/1024; skeletal: the LOD build settings\' ThresholdUV, default 1/1024)')
    return r


def bounds_ue(Vw):
    u = Vw * np.array((100.0, -100.0, 100.0))
    return dict(min_cm=np.round(u.min(0), 2).tolist(), max_cm=np.round(u.max(0), 2).tolist())


# ------------------------------------------------------------------ skeleton vs round 2
def skeleton(sc):
    limbs = [(uid, m) for uid, m in sc.models.items() if m['type'] in ('LimbNode', 'Null')]
    out = []
    for uid, m in limbs:
        p = m['p']
        pa = sc.parent.get(uid, 0)
        out.append(dict(name=m['name'], type=m['type'], parent=sc.models[pa]['name'] if pa in sc.models else None,
                        T=list(p.get('Lcl Translation', [0, 0, 0])), R=list(p.get('Lcl Rotation', [0, 0, 0])),
                        S=list(p.get('Lcl Scaling', [1, 1, 1])), pre=list(p.get('PreRotation', [0, 0, 0])),
                        post=list(p.get('PostRotation', [0, 0, 0])), ra=p.get('RotationActive'),
                        G=np.array(F.global_matrix(sc, uid))))
    bind = {}
    for pu, pz in sc.poses.items():
        for pn in F.children(pz['elem'], b'PoseNode'):
            nu = F.child(pn, b'Node').props[0]
            if nu in sc.models:
                bind[sc.models[nu]['name']] = np.array(F.m4(F.arr(pn, b'Matrix')))
    links = {}
    for kind, ch, pa, pn in sc.conns:
        if ch in sc.models and pa in sc.deformers and sc.deformers[pa]['type'] == 'Cluster':
            links.setdefault(sc.models[ch]['name'], []).append(np.array(F.m4(F.arr(sc.deformers[pa]['elem'], b'TransformLink'))))
    return out, bind, links


def compare_skeleton(sc, ref, name):
    a, ab, al = skeleton(sc)
    b, bb, bl = ref
    r = dict(nodes=len(a), nodes_ref=len(b))
    if [x['name'] for x in a] != [x['name'] for x in b]:
        defect('%s: skeleton node names / order differ from round 2 (%d vs %d)' % (name, len(a), len(b)))
        return r
    dpar = [x['name'] for x, y in zip(a, b) if x['parent'] != y['parent'] or x['type'] != y['type']]
    dloc = max(max(np.abs(np.array(x[k], float) - np.array(y[k], float)).max() for k in ('T', 'R', 'S', 'pre', 'post'))
               for x, y in zip(a, b))
    dglob = max(float(np.abs(x['G'] - y['G']).max()) for x, y in zip(a, b))
    dra = [x['name'] for x, y in zip(a, b) if x['ra'] != y['ra']]
    dbind = max((float(np.abs(ab[k] - bb[k]).max()) for k in bb if k in ab), default=0.0)
    miss_bind = sorted(set(bb) - set(ab))
    dlink = 0.0
    for k, ms in al.items():
        refm = bl.get(k, [None])[0]
        if refm is None:
            refm = next(x['G'] for x in a if x['name'] == k)
        for M in ms:
            dlink = max(dlink, float(np.abs(M - refm).max()))
    r.update(parent_or_type_diff=dpar, local_props_max_diff=float(dloc), global_max_diff_cm=dglob,
             rotation_active_diff=dra, bindpose_max_diff=dbind, bindpose_missing=miss_bind,
             cluster_transformlink_max_diff=dlink, bones=[x['name'] for x in a if x['type'] == 'LimbNode'])
    if dpar or dloc > 1e-6 or dglob > TOL_CM or dra or dbind > TOL_CM or miss_bind or dlink > TOL_CM:
        defect('%s: skeleton differs from round 2: %s' % (name, {k: v for k, v in r.items() if k != 'bones'}))
    r['bones'] = len(r['bones'])
    return r


# ------------------------------------------------------------------ run
ref_sc = F.load(R2_SK)
REF_SKEL = skeleton(ref_sc)
ref_meshes = {m['name']: m for m in mesh_records(ref_sc)}
r2_gs = {k: ref_sc.global_settings.get(k) for k in ('UpAxis', 'UpAxisSign', 'FrontAxis', 'FrontAxisSign', 'CoordAxis',
                                                   'CoordAxisSign', 'UnitScaleFactor')}
r2_bounds = bounds_ue(np.concatenate([m['Vw'] for m in ref_meshes.values()]))
rep['round2'] = dict(fbx=R2_SK, md5=RC.md5_file(R2_SK), tris=sum(tri_count(m) for m in ref_meshes.values()),
                     meshes=len(ref_meshes), bounds_ue=r2_bounds, bones=sum(1 for x in REF_SKEL[0] if x['type'] == 'LimbNode'))
log('round 2 SK: %d meshes, %d tris, %d bones, bounds %s' % (len(ref_meshes), rep['round2']['tris'], rep['round2']['bones'], r2_bounds))

LOD0_HASH = {}
WANT_MATS = [RC.MAT_HULL, RC.MAT_PROPS, RC.MAT_DETAIL]
for lod in (0, 1, 2):
    name = 'SK_Airship.fbx' if lod == 0 else 'SK_Airship_LOD%d.fbx' % lod
    path = os.path.join(FBX_DIR, name)
    fr = dict(path=path, bytes=os.path.getsize(path), md5=RC.md5_file(path), lod=lod)
    rep['files'][name] = fr
    sc = F.load(path)
    gs = {k: sc.global_settings.get(k) for k in r2_gs}
    fr['global_settings_same_as_round2'] = gs == r2_gs
    if gs != r2_gs:
        defect('%s: GlobalSettings %s, round 2 %s' % (name, gs, r2_gs))
    fr['skeleton'] = compare_skeleton(sc, REF_SKEL, name)
    recs = mesh_records(sc)
    moving = RC.MOVING + ('_LOD%d' % lod if lod else '')
    want_names = sorted([n for n in MAN['objects'] if n == RC.HULL_OBJ or n.startswith(RC.PROP_PREFIX)]) + [moving]
    fr['mesh_order'] = [m['name'] for m in recs]
    if fr['mesh_order'] != want_names:
        defect('%s: meshes in the file %s, want %s' % (name, fr['mesh_order'][:5], want_names[:5]))
    slot_order = []
    for m in recs:
        for mt in m['mats']:
            if mt not in slot_order:
                slot_order.append(mt)
    fr['material_slot_order'] = slot_order
    if slot_order != WANT_MATS:
        defect('%s: material order %s (want %s)' % (name, slot_order, WANT_MATS))
    per = {}
    tris = 0
    allV = []
    for m in recs:
        n = m['name']
        pm = dict(verts=len(m['V']), polys=len(m['sizes']), tris=tri_count(m), materials=m['mats'],
                  uv_layers=[u for u, _ in m['uvs']], node_identity_dev=m['node_identity'])
        tris += pm['tris']
        allV.append(m['Vw'])
        want_m = [RC.MAT_HULL] if n == RC.HULL_OBJ else ([RC.MAT_DETAIL] if n.startswith(RC.MOVING) else [RC.MAT_PROPS])
        if m['mats'] != want_m:
            defect('%s %s: materials %s want %s' % (name, n, m['mats'], want_m))
        want_uv = [RC.UV_INK, RC.UV_PAL, RC.UV_HULL_INK] if n == RC.HULL_OBJ else [RC.UV_INK, RC.UV_PAL]
        if pm['uv_layers'] != want_uv:
            defect('%s %s: UV layers %s want %s' % (name, n, pm['uv_layers'], want_uv))
        mobj = MAN['objects'].get(n, {})
        if mobj and (mobj['tris'] != pm['tris'] or mobj['verts'] != pm['verts']):
            defect('%s %s: %d tris / %d verts, manifest %s / %s' % (name, n, pm['tris'], pm['verts'], mobj['tris'], mobj['verts']))
        key = arr_key(n)
        pm['palette'] = palette_check(m, ARR[key + '__face_pal'] if key + '__face_pal' in ARR.files else None)
        pm['skin'] = skin_check(m, ARR[key + '__vert_bone'] if key + '__vert_bone' in ARR.files else None)
        if lod == 0 or n.startswith(RC.MOVING):
            pm['vs_source'] = compare_to_source(m, src_of(n), page_sizes(n))
            pm['ue'] = ue_risks(m)
        hsh = h(m['V']) + h(m['pvi']) + ''.join(h(u) for _, u in m['uvs']) + h(m['N'])
        if lod == 0:
            LOD0_HASH[n] = hsh
            if n in ref_meshes and n != RC.HULL_OBJ:
                rm = ref_meshes[n]
                same = len(rm['V']) == len(m['V']) and np.abs(rm['Vw'] - m['Vw']).max() < 1e-6 and \
                    np.array_equal(rm['pvi'], m['pvi']) and np.abs(rm['uvs'][0][1] - m['uvs'][0][1]).max() < 1e-7
                pm['same_as_round2_except_uv1'] = bool(same)
                if not same:
                    defect('%s %s: differs from the round 2 prop (positions / corners / UV0)' % (name, n))
        elif not n.startswith(RC.MOVING):
            pm['same_as_lod0'] = LOD0_HASH.get(n) == hsh
            if not pm['same_as_lod0']:
                defect('%s %s: differs from LOD0' % (name, n))
        per[n] = pm
    fr['meshes'] = {k: v for k, v in per.items() if k == RC.HULL_OBJ or k.startswith(RC.MOVING)}
    fr['props'] = dict(count=sum(1 for k in per if k.startswith(RC.PROP_PREFIX)),
                       all_same_as_round2_except_uv1=all(v.get('same_as_round2_except_uv1', v.get('same_as_lod0', False))
                                                         for k, v in per.items() if k.startswith(RC.PROP_PREFIX)),
                       tris=sum(v['tris'] for k, v in per.items() if k.startswith(RC.PROP_PREFIX)),
                       palette_slots={k: v['palette'].get('slots') for k, v in per.items() if k.startswith(RC.PROP_PREFIX + 'Helm')})
    if lod == 0:
        fr['props']['ue'] = {k: v['ue'] for k, v in per.items() if k.startswith(RC.PROP_PREFIX + 'Cannon_L1')}
    fr['tris'] = tris
    want_t = MAN['lods']['sk_tris'][str(lod)]
    if tris != want_t:
        defect('%s: %d triangles, manifest %d' % (name, tris, want_t))
    fr['bounds_ue'] = bounds_ue(np.concatenate(allV))
    fr['bounds_vs_round2_cm'] = dict(min=np.round(np.array(fr['bounds_ue']['min_cm']) - r2_bounds['min_cm'], 2).tolist(),
                                     max=np.round(np.array(fr['bounds_ue']['max_cm']) - r2_bounds['max_cm'], 2).tolist())
    sz = np.array(fr['bounds_ue']['max_cm']) - np.array(fr['bounds_ue']['min_cm'])
    fr['bounds_size_cm'] = np.round(sz, 1).tolist()
    if abs(sz[0] - 5190) >= 150 or abs(sz[1] - 2390) >= 150 or abs(sz[2] - 1700) >= 150:
        defect('%s: bounds %s outside as_10\'s check (5190 x 2390 x 1700 +-150)' % (name, fr['bounds_size_cm']))
    log('%s: %d meshes, %d tris (manifest %d), slots %s, skeleton %s, bounds %s (vs round 2 %s)' % (
        name, len(recs), tris, want_t, slot_order, 'same' if not [d for d in rep['defects'] if name in d and 'skeleton' in d]
        else 'DIFFERS', fr['bounds_size_cm'], fr['bounds_vs_round2_cm']))

# static meshes
for lod in (0, 1, 2):
    n = RC.HULLDET + ('_LOD%d' % lod if lod else '')
    name = n + '.fbx'
    path = os.path.join(FBX_DIR, name)
    fr = dict(path=path, bytes=os.path.getsize(path), md5=RC.md5_file(path), lod=lod)
    rep['files'][name] = fr
    sc = F.load(path)
    types = sorted({m['type'] for m in sc.models.values()})
    fr['model_types'] = types
    if types != ['Mesh'] or sc.deformers or sc.poses:
        defect('%s: model types %s, %d deformers, %d poses (want one Mesh, no skin)' % (name, types, len(sc.deformers), len(sc.poses)))
    recs = mesh_records(sc)
    if [m['name'] for m in recs] != [n]:
        defect('%s: meshes %s' % (name, [m['name'] for m in recs]))
    m = recs[0]
    fr.update(verts=len(m['V']), tris=tri_count(m), materials=m['mats'], uv_layers=[u for u, _ in m['uvs']],
              node_global_identity_dev=m['node_identity'])
    if m['mats'] != [RC.MAT_DETAIL] or fr['uv_layers'] != [RC.UV_INK, RC.UV_PAL]:
        defect('%s: materials %s, UV layers %s' % (name, m['mats'], fr['uv_layers']))
    want_t = MAN['lods']['hull_detail_tris'][str(lod)]
    if fr['tris'] != want_t:
        defect('%s: %d triangles, manifest %d' % (name, fr['tris'], want_t))
    fr['palette'] = palette_check(m, ARR[arr_key(n) + '__face_pal'])
    fr['vs_source'] = compare_to_source(m, src_of(n), page_sizes(n))
    fr['ue'] = ue_risks(m)
    fr['bounds_ue'] = bounds_ue(m['Vw'])
    mb = MAN['objects'][n]['bounds']
    fr['bounds_vs_manifest_cm'] = float(max(np.abs(np.array(fr['bounds_ue']['min_cm']) - mb['min_cm']).max(),
                                            np.abs(np.array(fr['bounds_ue']['max_cm']) - mb['max_cm']).max()))
    if fr['bounds_vs_manifest_cm'] > 0.02:
        defect('%s: bounds %s vs manifest %s' % (name, fr['bounds_ue'], mb))
    log('%s: %d tris (manifest %d), slots %s, UV %s, bounds %s' % (name, fr['tris'], want_t, m['mats'], fr['uv_layers'], fr['bounds_ue']))

for base, n in RC.TURRETS.items():
    name = n + '.fbx'
    path = os.path.join(FBX_DIR, name)
    fr = dict(path=path, bytes=os.path.getsize(path), md5=RC.md5_file(path))
    rep['files'][name] = fr
    sc = F.load(path)
    recs = mesh_records(sc)
    m = recs[0]
    fr.update(meshes=[r['name'] for r in recs], verts=len(m['V']), tris=tri_count(m), materials=m['mats'],
              uv_layers=[u for u, _ in m['uvs']], skin=m['skin'])
    if len(recs) != 1 or m['skin'] or m['mats'] != [RC.MAT_PROPS] or fr['uv_layers'] != [RC.UV_INK, RC.UV_PAL]:
        defect('%s: %s' % (name, {k: fr[k] for k in ('meshes', 'materials', 'uv_layers', 'skin')}))
    fr['palette'] = palette_check(m, ARR[arr_key(base) + '__face_pal'])
    fr['vs_source'] = compare_to_source(m, src_of(n), page_sizes(n))
    fr['ue'] = ue_risks(m)
    r2 = mesh_records(F.load(R2_TURRET[n]))[0]
    same = len(r2['V']) == len(m['V']) and float(np.abs(r2['Vw'] - m['Vw']).max()) < 1e-6 and \
        np.array_equal(r2['pvi'], m['pvi']) and float(np.abs(r2['uvs'][0][1] - m['uvs'][0][1]).max()) < 1e-7
    fr['same_frame_and_uv0_as_round2'] = bool(same)
    if not same:
        defect('%s: differs from round 2 %s (positions / corners / UV0)' % (name, R2_TURRET[n]))
    fr['bounds_ue'] = bounds_ue(m['Vw'])
    log('%s: %d tris, slots %s, UV %s, palette %s, same frame and UV0 as round 2: %s' % (
        name, fr['tris'], m['mats'], fr['uv_layers'], fr['palette'].get('slots'), same))


# round 2 reproducible
def uid_keys(root):
    """object uid -> (element id, name): Blender's exporter draws the uids from Python hashes (they change from run to
    run), so the comparison maps them to what they name"""
    keys = {}
    for top in root.elems:
        for e in top.elems:
            if e.props and isinstance(e.props[0], int) and len(e.props) > 1 and isinstance(e.props[1], (bytes, bytearray)):
                keys[e.props[0]] = (e.id, bytes(e.props[1]))
    return keys


def norm_props(e, keys, outdir=b''):
    out = []
    for x in e.props:
        if isinstance(x, (bytes, bytearray)):
            out.append(bytes(x).replace(outdir, b'<fbx dir>/') if outdir else bytes(x))   # path_mode STRIP writes it
        elif hasattr(x, 'typecode'):
            out.append(list(x))
        elif isinstance(x, int) and x in keys:
            out.append(keys[x])
        else:
            out.append(x)
    return out


def elem_eq(a, b, ka, kb, path, diffs, da=b'', db=b''):
    if a.id != b.id:
        diffs.append('%s: id %s vs %s' % (path, a.id, b.id)); return
    if norm_props(a, ka, da) != norm_props(b, kb, db):
        diffs.append('%s: props differ' % path)
    if len(a.elems) != len(b.elems):
        diffs.append('%s: %d vs %d children' % (path, len(a.elems), len(b.elems))); return
    for i, (x, y) in enumerate(zip(a.elems, b.elems)):
        if len(diffs) > 20:
            return
        elem_eq(x, y, ka, kb, path + '/' + x.id.decode('ascii', 'replace') + '[%d]' % i, diffs, da, db)


if R2_REPRO:
    from io_scene_fbx import parse_fbx
    ra, _ = parse_fbx.parse(R2_SK)
    rb, _ = parse_fbx.parse(R2_REPRO)
    ka, kb = uid_keys(ra), uid_keys(rb)
    diffs = []
    tops = {}
    for x in ra.elems:
        tops.setdefault(x.id, []).append(x)
    SKIP = (b'FileId', b'CreationTime', b'Creator', b'FBXHeaderExtension')
    for y in rb.elems:
        if y.id in SKIP:
            continue
        xs = tops.get(y.id)
        if not xs:
            diffs.append('top %s missing in round 2' % y.id); continue
        elem_eq(xs[0], y, ka, kb, y.id.decode(), diffs, (os.path.dirname(R2_SK) + '/').encode(),
                (os.path.dirname(os.path.abspath(R2_REPRO)) + '/').encode())
    rep['round2_reproducible'] = dict(fresh=R2_REPRO, reference=R2_SK, element_diffs=diffs[:20], same=not diffs,
                                      skipped=[x.decode() for x in SKIP],
                                      uids='mapped to (element, name): the exporter draws them from Python hashes',
                                      paths='the texture paths name the output folder (path_mode STRIP): compared without it')
    if diffs:
        defect('round 2 export without --round3 differs from rig/export/SK_Airship.fbx: %s' % diffs[:5])
    log('round 2 fresh export vs rig/export/SK_Airship.fbx: %s' % ('identical (header, creation time and uids aside)'
                                                                     if not diffs else diffs[:5]))

rep['summary'] = dict(
    sk_tris={k: v['tris'] for k, v in rep['files'].items() if k.startswith('SK_')},
    hull_detail_tris={k: v['tris'] for k, v in rep['files'].items() if k.startswith(RC.HULLDET)},
    turret_tris={k: v['tris'] for k, v in rep['files'].items() if k.startswith('SM_AirshipTurret')},
    skeleton_same_as_round2=not [d for d in rep['defects'] if 'skeleton' in d],
    defects=len(rep['defects']))
rep['protected_end'] = RC.protected_state()
rep['protected_unchanged'] = all(rep['protected_start'][k]['md5'] == v['md5'] for k, v in rep['protected_end'].items())
rep['export_blend_md5_end'] = RC.md5_file(RC.EXPORT_BLEND)
rep['seconds'] = round(time.time() - log.t0, 1)
RC.dump_json(rep, RC.CHECK_DIR + '/fbx_check.json')
RC.dump_json(rep, RC.DOCS + '/export_fbx_check.json')
log('defects %d, notes %d -> %s' % (len(rep['defects']), len(rep['notes']), RC.CHECK_DIR + '/fbx_check.json'))
sys.stdout.flush()
os._exit(0)
