"""Independent low-level FBX reader for the SK_Airship verification (uses Blender's io_scene_fbx.parse_fbx only,
none of the rig_* scripts). Import from a script run inside Blender:

    sys.path.insert(0, <this dir>); import verify_fbxlib as F; scene = F.load(path)
"""
import math
from io_scene_fbx import parse_fbx
from mathutils import Matrix, Euler, Vector


def sname(b):
    return b.split(b'\x00\x01')[0].decode('utf-8', 'replace')


def child(e, id_):
    for c in e.elems:
        if c.id == id_:
            return c
    return None


def children(e, id_):
    return [c for c in e.elems if c.id == id_]


def props70(e):
    p = child(e, b'Properties70')
    out = {}
    if p is None:
        return out
    for c in p.elems:
        name = c.props[0].decode()
        vals = list(c.props[4:])
        vals = [v.decode('utf-8', 'replace') if isinstance(v, bytes) else v for v in vals]
        out[name] = vals[0] if len(vals) == 1 else vals
    return out


def arr(e, id_):
    c = child(e, id_)
    if c is None:
        return None
    return list(c.props[0]) if c.props else []


def m4(a):
    """FBX matrix (16 doubles, column-major) -> mathutils Matrix (same as Blender's importer)."""
    return Matrix(tuple(zip(*[iter(a)] * 4))).transposed()


def model_local(p):
    """FBX local transform: T * Roff * Rp * Rpre * R * Rpost^-1 * Rp^-1 * Soff * Sp * S * Sp^-1."""
    def v3(name, d=(0.0, 0.0, 0.0)):
        v = p.get(name, d)
        return Vector(v if isinstance(v, (list, tuple)) else d)
    order = ['XYZ', 'XZY', 'YZX', 'YXZ', 'ZXY', 'ZYX'][int(p.get('RotationOrder', 0))]
    def rot(v):
        return Euler([math.radians(c) for c in v], order).to_matrix().to_4x4()
    T = Matrix.Translation(v3('Lcl Translation'))
    R = rot(v3('Lcl Rotation'))
    pre = rot(v3('PreRotation')); post = rot(v3('PostRotation'))
    if not int(p.get('RotationActive', 0)):
        pre_used = pre; post_used = post   # Blender writes RotationActive 1 when it uses them; keep both, report
    else:
        pre_used = pre; post_used = post
    Roff = Matrix.Translation(v3('RotationOffset')); Rp = Matrix.Translation(v3('RotationPivot'))
    Soff = Matrix.Translation(v3('ScalingOffset')); Sp = Matrix.Translation(v3('ScalingPivot'))
    s = v3('Lcl Scaling', (1.0, 1.0, 1.0))
    S = Matrix.Diagonal((s.x, s.y, s.z, 1.0))
    return T @ Roff @ Rp @ pre_used @ R @ post_used.inverted() @ Rp.inverted() @ Soff @ Sp @ S @ Sp.inverted()


class Scene:
    pass


def load(path):
    root, version = parse_fbx.parse(path)
    sc = Scene()
    sc.version = version
    gs = child(root, b'GlobalSettings')
    sc.global_settings = props70(gs) if gs is not None else {}
    objs = child(root, b'Objects')
    conns = child(root, b'Connections')
    sc.models = {}; sc.geoms = {}; sc.deformers = {}; sc.materials = {}; sc.poses = {}; sc.attrs = {}; sc.other = {}
    for e in objs.elems:
        uid = e.props[0]
        name = sname(e.props[1]) if len(e.props) > 1 else ''
        typ = e.props[2].decode() if len(e.props) > 2 and isinstance(e.props[2], bytes) else ''
        rec = {'uid': uid, 'name': name, 'type': typ, 'elem': e}
        if e.id == b'Model':
            rec['p'] = props70(e)
            sc.models[uid] = rec
        elif e.id == b'Geometry':
            sc.geoms[uid] = rec
        elif e.id == b'Deformer':
            sc.deformers[uid] = rec
        elif e.id == b'Material':
            sc.materials[uid] = rec
        elif e.id == b'Pose':
            sc.poses[uid] = rec
        elif e.id == b'NodeAttribute':
            sc.attrs[uid] = rec
        else:
            sc.other.setdefault(e.id.decode(), []).append(rec)
    sc.conns = []
    for c in conns.elems:
        if c.id != b'C':
            continue
        kind = c.props[0].decode()
        sc.conns.append((kind, c.props[1], c.props[2], c.props[3].decode() if len(c.props) > 3 else None))
    # parent links for models
    sc.parent = {}
    sc.children_of = {}
    for kind, ch, pa, pn in sc.conns:
        if ch in sc.models and (pa in sc.models or pa == 0):
            sc.parent[ch] = pa
            sc.children_of.setdefault(pa, []).append(ch)
    sc._glob = {}
    return sc


def global_matrix(sc, uid):
    if uid in sc._glob:
        return sc._glob[uid]
    M = model_local(sc.models[uid]['p'])
    pa = sc.parent.get(uid, 0)
    if pa and pa in sc.models:
        M = global_matrix(sc, pa) @ M
    sc._glob[uid] = M
    return M


def connected(sc, uid, table, as_parent=True):
    """Objects in `table` connected to uid. as_parent=True: things whose parent is uid."""
    out = []
    for kind, ch, pa, pn in sc.conns:
        if as_parent and pa == uid and ch in table:
            out.append(ch)
        if not as_parent and ch == uid and pa in table:
            out.append(pa)
    return out


def geometry_data(g):
    e = g['elem']
    d = {}
    d['vertices'] = arr(e, b'Vertices')
    d['pvi'] = arr(e, b'PolygonVertexIndex')
    d['uv'] = []
    for le in children(e, b'LayerElementUV'):
        nm = child(le, b'Name').props[0].decode() if child(le, b'Name') is not None else ''
        mapping = child(le, b'MappingInformationType').props[0].decode()
        ref = child(le, b'ReferenceInformationType').props[0].decode()
        idx_layer = int(le.props[0]) if le.props else 0
        d['uv'].append({'layer': idx_layer, 'name': nm, 'mapping': mapping, 'ref': ref,
                        'UV': arr(le, b'UV'), 'UVIndex': arr(le, b'UVIndex')})
    d['normals'] = []
    for le in children(e, b'LayerElementNormal'):
        mapping = child(le, b'MappingInformationType').props[0].decode()
        ref = child(le, b'ReferenceInformationType').props[0].decode()
        d['normals'].append({'mapping': mapping, 'ref': ref, 'N': arr(le, b'Normals'),
                             'NIndex': arr(le, b'NormalsIndex')})
    d['materials'] = []
    for le in children(e, b'LayerElementMaterial'):
        mapping = child(le, b'MappingInformationType').props[0].decode()
        d['materials'].append({'mapping': mapping, 'M': arr(le, b'Materials')})
    d['smoothing'] = []
    for le in children(e, b'LayerElementSmoothing'):
        mapping = child(le, b'MappingInformationType').props[0].decode()
        d['smoothing'].append({'mapping': mapping, 'S': arr(le, b'Smoothing')})
    return d


def per_corner_uv(uvl):
    uv = uvl['UV']; idx = uvl['UVIndex']
    if uvl['ref'] == 'IndexToDirect':
        return [(uv[2 * i], uv[2 * i + 1]) for i in idx]
    return [(uv[2 * i], uv[2 * i + 1]) for i in range(len(uv) // 2)]
