"""Detail generators for the airship detail pass (round 3). Reusable for every zone.

New detail geometry goes ON TOP of the unchanged ship (SM_Airship and the props stay as they are). Every generator
appends loose parts to a `Mesh` builder; `Mesh.to_object()` turns one builder into one skinned object (every vertex
100 % on one bone, like the rig's props). Seeded randomness only (random.Random(seed)), so a rerun gives the same
geometry.

Blender world metres: +X bow, +Y port, +Z up. Rig contract: Docs/Airship/RIG_CONTRACT.md.

Generators (all sizes in metres):
  solid_plate      patch plate with thickness, chamfered top edge and optional cut corners, conforming to any surface
                   given as a function (u, v) -> (point, normal)
  solid_quad       the same for any four-sided outline (slanted bars, trapezoids)
  picture_frame    raised rim of four strips round a panel (the panel's centre stays lower, so it reads recessed)
  slotted_plate    armour plate with 3-4 slanted slots cut through it, a flush dark backing behind the slots
  rivet / rivet_row  low domed round rivet heads (8 sides, closed, 14 triangles); not inked in the previews
  bolt / bolt_row  hex bolt heads (6 sides, closed); kept for the few places that want a real bolt
  tube / pipe_run  swept pipes with rounded elbows, flanges, clamps (band + one foot), end caps
  gland            square bolted plate with a collar where a pipe or conduit enters the hull
  valve_body       valve block without a hand wheel (Talal had the valve wheels removed on 2026-10-31)
  housing          chunky machinery housing: bolted base flange, a lid with two hinges and two dog latches, pipe stubs
  pump_body        horizontal pump / pressure body on two saddles, flanged ends
  louver_vent      framed vent box with slanted louvres (not used on the hull flank any more: read as windows)
  grille_round     round grille: ring + bars (not used on the hull flank any more: read as portholes)
  machinery_box    chamfered box with cooling ribs (first pass; replaced on the flank by `housing`)
  gusset           triangular bracket with a foot plate
  tank             small gas bottle with domed ends and two straps
  cable / chain    sagging cable with ferrules / draped chain (first pass; not used on the flank any more)
  piston           hydraulic actuator: cylinder, rod, two end eyes
  drop_floating    removes every loose piece that touches nothing (ship or other detail) within 2 cm
"""
import bpy, bmesh, math, random, os
import numpy as np
from mathutils import Vector as V, Matrix
from mathutils.bvhtree import BVHTree

# ------------------------------------------------------------------ where detail builds may write (round 3, 2026-11-28)
# Every zone builds into its own file under rig/detail/zones/. Talal's files, the rig and the approved zone 1 sample
# (rig/detail/AirshipRig_detail.blend, which Talal may have open) are never written: safe_save() refuses them.
BLENDER_ROOT = '/mnt/new_partition/BlenderProjects/StylizedAirship'
RIG_DIR = BLENDER_ROOT + '/rig'
ZONES_DIR = RIG_DIR + '/detail/zones'
TMP_DIR = RIG_DIR + '/tmp'
APPROVED_Z1_BLEND = RIG_DIR + '/detail/AirshipRig_detail.blend'      # read only (approved zone 1, pass 2)
PROTECTED_BLENDS = (BLENDER_ROOT + '/StylizedAirship.blend', RIG_DIR + '/AirshipRig.blend',
                    RIG_DIR + '/AirshipRig_src.blend', APPROVED_Z1_BLEND, RIG_DIR + '/props/AirshipProps.blend',
                    RIG_DIR + '/props/Turret.blend')
WRITABLE_DIRS = (ZONES_DIR, TMP_DIR)


def zone_blend(zone):
    """the output .blend of a zone: zone 1 or 'z1' or 'Z1' -> rig/detail/zones/AirshipRig_detail_z1.blend"""
    z = str(zone).lower().lstrip('z')
    return '%s/AirshipRig_detail_z%s.blend' % (ZONES_DIR, z)


def check_writable(path):
    p = os.path.realpath(path)
    if any(p == os.path.realpath(q) for q in PROTECTED_BLENDS):
        raise RuntimeError('refusing to write a protected file: ' + p)
    if not any(p.startswith(os.path.realpath(d) + os.sep) for d in WRITABLE_DIRS):
        raise RuntimeError('detail builds write only under %s: %s' % (' or '.join(WRITABLE_DIRS), p))
    return p


def safe_save(path):
    """the only way a detail script saves a .blend (zones/ or tmp/ only, never a protected file)"""
    p = check_writable(path)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=p, relative_remap=True, compress=False)
    return p

# ------------------------------------------------------------------ role materials (the final colours are by ROLE)
# Every detail face carries one ROLE material. Talal approved reference 1's yellow and rust palette as the FINAL look on
# 2026-11-28 (the 'toon' preview), and the Unreal stage bakes the colours by role, so the material name says the role.
# The key is what the code uses (mat='rust_red' ...); the material name is what Unreal sees. Keep this order (material
# index = position) and only ever append new roles at the end.
ROLES = [
    # key            material name     colour (linear)       what it is for
    ('paint_yellow', 'DM_Yellow',     (0.95, 0.68, 0.21), 'base plates, one value step lighter than the hull paint (0.90, 0.60, 0.17)'),
    ('paint_ochre',  'DM_Ochre',      (0.83, 0.54, 0.15), 'base plates one step darker; picture-frame rims on yellow plates'),
    ('paint_orange', 'DM_Orange',     (0.85, 0.38, 0.12), 'reserved: the turbine housings\' own orange (fan zone only, if it must match them)'),
    ('rust_red',     'DM_Rust',       (0.50, 0.20, 0.12), 'strakes, teeth, frame ribs, straps, bay frames, rim straps, heavy armour (<= ~15 % of plates), patches, pods'),
    ('rust_dark',    'DM_RustDark',   (0.34, 0.14, 0.09), 'pod plates and lips, second rust tone'),
    ('dark_metal',   'DM_Dark',       (0.17, 0.16, 0.16), 'recesses, bay floors, backings, clamps, glands, lids, hinges, conduits'),
    ('machinery',    'DM_Machinery',  (0.28, 0.29, 0.31), 'machinery bodies: housings, pump bodies, cavity ribs'),
    ('steel',        'DM_Steel',      (0.50, 0.52, 0.55), 'bright steel: nozzle hoops and fins, latches'),
    ('copper',       'DM_Copper',     (0.70, 0.36, 0.17), 'big pipes, housing pipe stubs'),
    ('brass',        'DM_Brass',      (0.76, 0.58, 0.24), 'second pipe, flanges, valves, collars'),
    ('bolt',         'DM_Rivet',      (0.33, 0.30, 0.27), 'rivet heads (not inked; the bake draws rivet rows as dots)'),
    ('wood',         'DM_Wood',       (0.45, 0.30, 0.18), 'wooden treads / hand rails (stairs), only where wood makes sense'),
]
PALETTE = {k: c for k, _, c, _ in ROLES}
ROLE_MATERIAL = {k: n for k, n, _, _ in ROLES}
NO_INK_KINDS = ('rivet', 'bolt')            # faces of these kinds get a Freestyle face mark: the previews skip them
MAT_KEYS = [k for k, _, _, _ in ROLES]
MAT_PREFIX = 'DM_'                          # until 2026-11-28 the materials were M_Detail_<Key> (same keys, same order)


def mat_name(key):
    return ROLE_MATERIAL[key]


def ensure_materials():
    """one material per role, in ROLES order (viewport colour = the role colour, custom property palette_key = the role
    key; the render scripts swap them for their looks by palette_key)"""
    mats = []
    for k in MAT_KEYS:
        n = mat_name(k)
        m = bpy.data.materials.get(n) or bpy.data.materials.new(n)
        m.diffuse_color = PALETTE[k] + (1.0,)
        m['palette_key'] = k
        m['role'] = k
        mats.append(m)
    return mats


# ------------------------------------------------------------------ zone .blends: load another zone's details
def zone_collection_name(zone):
    return 'Detail_Z' + str(zone).upper().lstrip('Z')


def append_zone(zone, arm=None, path=None):
    """append collection Detail_ZN of zone N's .blend into the open file (the zone file is only read), parented to this
    file's Armature (Armature modifier retargeted, the appended duplicate armature removed) and with this file's role
    materials. Returns the collection, or None when the zone has no .blend / collection yet. A collection already in
    the file is returned as it is."""
    cname = zone_collection_name(zone)
    if cname in bpy.data.collections:
        return bpy.data.collections[cname]
    path = path or zone_blend(zone)
    if not os.path.exists(path):
        return None
    before = set(bpy.data.objects)
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        dst.collections = [cname] if cname in src.collections else []
    if not dst.collections or dst.collections[0] is None:
        return None
    coll = dst.collections[0]
    bpy.context.scene.collection.children.link(coll)
    arm = arm or bpy.data.objects['Armature']
    mats = {m['palette_key']: m for m in ensure_materials()}
    for ob in coll.all_objects:
        if ob.parent is not None and ob.parent.type == 'ARMATURE' and ob.parent != arm:
            mw = ob.matrix_world.copy()
            ob.parent = arm
            ob.matrix_parent_inverse = arm.matrix_world.inverted()
            ob.matrix_world = mw
        for md in ob.modifiers:
            if md.type == 'ARMATURE':
                md.object = arm
        if ob.type == 'MESH':
            for i, m in enumerate(ob.data.materials):
                k = m.get('palette_key') if m else None
                if k in mats:
                    ob.data.materials[i] = mats[k]
    for o in [o for o in bpy.data.objects if o not in before]:
        if o.type == 'ARMATURE' and o != arm:
            bpy.data.objects.remove(o)
    return coll


def detail_objects(collections=None):
    """mesh objects of the Detail_* collections (all, or the named ones)"""
    out = []
    for c in bpy.data.collections:
        if c.name.startswith('Detail_') and (collections is None or c.name in collections):
            out += [o for o in c.all_objects if o.type == 'MESH']
    return out


# ------------------------------------------------------------------ small vector helpers
def vec(a):
    return np.asarray(a, dtype=float)


def unit(a):
    a = vec(a)
    n = np.linalg.norm(a)
    return a / n if n > 1e-12 else a


def ortho_frame(n, hint=(1.0, 0.0, 0.0)):
    """(u, v, n): u = hint projected onto the plane of n, v = n x u"""
    n = unit(n)
    h = vec(hint)
    u = h - n * h.dot(n)
    if np.linalg.norm(u) < 1e-6:
        h = np.array([0.0, 0.0, 1.0]) if abs(n[2]) < 0.9 else np.array([0.0, 1.0, 0.0])
        u = h - n * h.dot(n)
    u = unit(u)
    return u, np.cross(n, u), n


def frame_matrix(origin, x, y, z):
    M = np.eye(4)
    M[:3, 0], M[:3, 1], M[:3, 2], M[:3, 3] = x, y, z, origin
    return M


def ring_pts(c, a, b, r, k, phase=0.0):
    """k points on a circle (centre c, radius r) in the plane spanned by the unit vectors a, b"""
    t = phase + np.arange(k) * 2 * math.pi / k
    return vec(c) + r * (np.outer(np.cos(t), a) + np.outer(np.sin(t), b))


# ------------------------------------------------------------------ mesh builder
class Mesh:
    """loose parts accumulated as numpy-friendly lists; every face has a material key, a smooth flag and a kind tag"""

    def __init__(self, name):
        self.name = name
        self.v = []
        self.f = []
        self.m = []
        self.s = []
        self.k = []
        self.g = []                 # per-vertex bone name (for objects whose parts sit on several bones)
        self.cur_group = None

    def verts(self, pts):
        b = len(self.v)
        pts = [tuple(map(float, p)) for p in np.asarray(pts, dtype=float).reshape(-1, 3)]
        self.v.extend(pts)
        self.g.extend([self.cur_group] * len(pts))
        return b

    def face(self, idx, mat, smooth=False, kind='misc'):
        self.f.append(tuple(int(i) for i in idx))
        self.m.append(mat)
        self.s.append(bool(smooth))
        self.k.append(kind)

    def tris(self):
        return sum(len(f) - 2 for f in self.f)

    def tris_by_kind(self):
        d = {}
        for f, k in zip(self.f, self.k):
            d[k] = d.get(k, 0) + len(f) - 2
        return d

    def extend(self, other):
        b = len(self.v)
        self.v.extend(other.v)
        self.g.extend(other.g)
        for f, m, s, k in zip(other.f, other.m, other.s, other.k):
            self.f.append(tuple(i + b for i in f)); self.m.append(m); self.s.append(s); self.k.append(k)

    def components(self):
        """connected pieces: (face -> piece id, vertex -> piece id), union-find over the faces' vertices"""
        par = list(range(len(self.v)))

        def find(i):
            while par[i] != i:
                par[i] = par[par[i]]
                i = par[i]
            return i
        for f in self.f:
            a = find(f[0])
            for j in f[1:]:
                b = find(j)
                if a != b:
                    par[b] = a
        vc = np.array([find(i) for i in range(len(self.v))], np.int64)
        fc = np.array([vc[f[0]] for f in self.f], np.int64)
        return fc, vc

    def drop_faces(self, drop):
        """remove the faces whose index is in `drop` and every vertex no face uses any more"""
        drop = set(int(i) for i in drop)
        keep_f = [i for i in range(len(self.f)) if i not in drop]
        used = sorted({j for i in keep_f for j in self.f[i]})
        remap = {o: n for n, o in enumerate(used)}
        self.v = [self.v[i] for i in used]
        self.g = [self.g[i] for i in used]
        self.f = [tuple(remap[j] for j in self.f[i]) for i in keep_f]
        self.m = [self.m[i] for i in keep_f]
        self.s = [self.s[i] for i in keep_f]
        self.k = [self.k[i] for i in keep_f]

    def piece_volumes(self):
        """signed volume of every loose piece (closed pieces: < 0 = inside out, e.g. a box built in a left-handed
        frame). Returns (face -> piece id, {piece id: volume})"""
        fc, _ = self.components()
        P = np.asarray(self.v, float)
        vol = {}
        for f, c in zip(self.f, fc):
            a = P[f[0]]
            for i in range(1, len(f) - 1):
                vol[int(c)] = vol.get(int(c), 0.0) + float(np.dot(a, np.cross(P[f[i]], P[f[i + 1]]))) / 6.0
        return fc, vol

    def orient_outward(self, min_vol=1e-9):
        """flip every closed loose piece whose signed volume is negative (inside out). New zones call this before
        to_object(); zone 1 (approved, frozen) does not, its few inside-out pieces are listed in ZONES.md. Returns the
        number of pieces flipped."""
        fc, vol = self.piece_volumes()
        bad = {c for c, v in vol.items() if v < -min_vol}
        for i, c in enumerate(fc):
            if int(c) in bad:
                self.f[i] = tuple(reversed(self.f[i]))
        return len(bad)

    # ---- low level shape helpers
    def bridge(self, a, b, mat, smooth, kind, closed=True, flip=False):
        """quads between two index rings of equal length"""
        n = len(a)
        rng = range(n) if closed else range(n - 1)
        for i in rng:
            j = (i + 1) % n
            q = (a[i], a[j], b[j], b[i])
            self.face(q[::-1] if flip else q, mat, smooth, kind)

    def cap(self, ring, mat, kind, flip=False):
        r = list(ring)
        self.face(r[::-1] if flip else r, mat, False, kind)

    def prism(self, bottom, top, mat, smooth=False, kind='misc', caps=True):
        """connect two point rings (k, 3) with quads; caps as n-gons. Ring order counter-clockwise seen from the top
        (outside of the bottom cap = -direction)."""
        bi = self.verts(bottom)
        ti = self.verts(top)
        k = len(bottom)
        a = list(range(bi, bi + k))
        b = list(range(ti, ti + k))
        self.bridge(a, b, mat, smooth, kind)
        if caps:
            self.cap(a, mat, kind, flip=True)
            self.cap(b, mat, kind)
        return a, b

    def from_bmesh(self, bm, M, mat, kind, smooth=False):
        M = np.asarray(M)
        pts = np.array([v.co[:] for v in bm.verts])
        pts = pts @ M[:3, :3].T + M[:3, 3]
        b = self.verts(pts)
        bm.verts.index_update()
        for f in bm.faces:
            self.face([b + v.index for v in f.verts], mat, smooth, kind)

    # ---- to a Blender object
    def to_object(self, name, coll, mats, arm=None, groups=None, smooth_angle=35.0, weighted=True):
        """mats: list of materials in MAT_KEYS order. groups: per-vertex bone names (or one name for all)"""
        me = bpy.data.meshes.new(name)
        me.from_pydata(self.v, [], self.f)
        me.update()
        for m in mats:
            me.materials.append(m)
        mi = np.array([MAT_KEYS.index(m) for m in self.m], dtype=np.int32)
        me.polygons.foreach_set('material_index', mi)
        me.polygons.foreach_set('use_smooth', np.array(self.s, dtype=bool))
        me.set_sharp_from_angle(angle=math.radians(smooth_angle))
        ob = bpy.data.objects.new(name, me)
        coll.objects.link(ob)
        if weighted:
            md = ob.modifiers.new('WN', 'WEIGHTED_NORMAL')
            md.keep_sharp = True
            md.mode = 'FACE_AREA'
            md.weight = 50
            dg = bpy.context.evaluated_depsgraph_get()
            dg.update()
            oe = ob.evaluated_get(dg)
            nm = bpy.data.meshes.new_from_object(oe, preserve_all_data_layers=True, depsgraph=dg)
            ob.modifiers.remove(md)
            old = ob.data
            ob.data = nm
            bpy.data.meshes.remove(old)
            nm.name = name
        # Freestyle face marks on rivets / bolts: the preview line sets exclude marked faces (comic artists draw rivet
        # rows as dots, not as outlined glyphs). The mark is preview data only; the face order is unchanged above.
        marks = np.array([k in NO_INK_KINDS for k in self.k], dtype=bool)
        ob.data.polygons.foreach_set('use_freestyle_mark', marks)
        if arm is not None:
            skin_rigid(ob, arm, groups)
        return ob


def skin_rigid(ob, arm, groups):
    """every vertex 100 % on one bone (groups: a bone name for all vertices, or a per-vertex list of bone names)"""
    ob.vertex_groups.clear()
    n = len(ob.data.vertices)
    if isinstance(groups, str):
        groups = [groups] * n
    assert len(groups) == n, (len(groups), n)
    by = {}
    for i, g in enumerate(groups):
        by.setdefault(g, []).append(i)
    for g in sorted(by):
        assert g in arm.data.bones, g
        vg = ob.vertex_groups.new(name=g)
        vg.add(by[g], 1.0, 'REPLACE')
    md = ob.modifiers.new('Armature', 'ARMATURE')
    md.object = arm
    md.use_vertex_groups = True
    md.use_bone_envelopes = False
    mw = ob.matrix_world.copy()
    ob.parent = arm
    ob.parent_type = 'OBJECT'
    ob.matrix_parent_inverse = arm.matrix_world.inverted()
    ob.matrix_world = mw


# ------------------------------------------------------------------ target surfaces
class Surface:
    """triangulated part of a mesh with its render (corner) normals: ray casts and nearest points return the smooth
    normal interpolated inside the hit triangle, so offsets follow the shading of the curved hull."""

    def __init__(self, co, tri, tnrm):
        self.co = np.asarray(co, dtype=float)
        self.tri = np.asarray(tri, dtype=np.int64)
        self.tn = np.asarray(tnrm, dtype=float)
        self.bvh = BVHTree.FromPolygons(self.co.tolist(), self.tri.tolist(), all_triangles=True)

    @classmethod
    def from_mesh(cls, me, poly_mask=None, M=None):
        me.calc_loop_triangles()
        lt = me.loop_triangles
        n = len(lt)
        tv = np.empty(n * 3, np.int64); lt.foreach_get('vertices', tv)
        tl = np.empty(n * 3, np.int64); lt.foreach_get('loops', tl)
        tp = np.empty(n, np.int64); lt.foreach_get('polygon_index', tp)
        cn = np.empty(len(me.loops) * 3); me.corner_normals.foreach_get('vector', cn)
        cn = cn.reshape(-1, 3)
        co = np.empty(len(me.vertices) * 3); me.vertices.foreach_get('co', co)
        co = co.reshape(-1, 3)
        if M is not None:
            M = np.asarray(M)
            co = co @ M[:3, :3].T + M[:3, 3]
            cn = cn @ M[:3, :3].T
        tv = tv.reshape(-1, 3); tl = tl.reshape(-1, 3)
        keep = np.ones(n, bool) if poly_mask is None else np.asarray(poly_mask)[tp]
        return cls(co, tv[keep], cn[tl[keep]])

    def _normal(self, fi, p):
        a, b, c = self.co[self.tri[fi]]
        v0, v1, v2 = b - a, c - a, vec(p) - a
        d00, d01, d11 = v0.dot(v0), v0.dot(v1), v1.dot(v1)
        d20, d21 = v2.dot(v0), v2.dot(v1)
        den = d00 * d11 - d01 * d01
        if abs(den) < 1e-18:
            w = np.array([1 / 3, 1 / 3, 1 / 3])
        else:
            wb = (d11 * d20 - d01 * d21) / den
            wc = (d00 * d21 - d01 * d20) / den
            w = np.clip(np.array([1 - wb - wc, wb, wc]), 0, 1)
        return unit(w @ self.tn[fi])

    def ray(self, o, d, maxd=50.0):
        loc, nrm, fi, dist = self.bvh.ray_cast(V(o), V(d), maxd)
        if loc is None:
            return None
        p = vec(loc)
        return p, self._normal(fi, p), fi, dist, vec(nrm)

    def nearest(self, p, maxd=5.0):
        loc, nrm, fi, dist = self.bvh.find_nearest(V(p), maxd)
        if loc is None:
            return None
        q = vec(loc)
        return q, self._normal(fi, q), fi, dist


def bvh_from_objects(objs, depsgraph=None):
    """one BVH over the evaluated world-space triangles of several mesh objects (for clearance tests)"""
    co_all, tri_all, off = [], [], 0
    for ob in objs:
        if depsgraph is not None:
            oe = ob.evaluated_get(depsgraph)
            me = oe.to_mesh()
        else:
            me = ob.data
        me.calc_loop_triangles()
        n = len(me.loop_triangles)
        tv = np.empty(n * 3, np.int64); me.loop_triangles.foreach_get('vertices', tv)
        co = np.empty(len(me.vertices) * 3); me.vertices.foreach_get('co', co)
        M = np.array(ob.matrix_world)
        co = co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3]
        co_all.append(co); tri_all.append(tv.reshape(-1, 3) + off); off += len(co)
        if depsgraph is not None:
            oe.to_mesh_clear()
    co = np.concatenate(co_all) if co_all else np.zeros((0, 3))
    tri = np.concatenate(tri_all) if tri_all else np.zeros((0, 3), np.int64)
    return BVHTree.FromPolygons(co.tolist(), tri.tolist(), all_triangles=True), co, tri


# ------------------------------------------------------------------ plates
def shrink_coords(c, e):
    """move the outermost coordinates of a sorted 1D grid inward by e (for the chamfered top face)"""
    c = np.array(c, dtype=float)
    lo, hi = c[0], c[-1]
    s = (hi - lo - 2 * e) / (hi - lo)
    return lo + e + (c - lo) * s


def grid_coords(lo, hi, cell, cut=0.0):
    """1D grid from lo to hi with cells <= cell; if cut > 0 the second and the second-last lines sit at lo+cut /
    hi-cut (so a chamfered corner is a clean 45-degree cut)"""
    L = hi - lo
    if cut > 0 and L > 3 * cut:
        inner = max(1, int(math.ceil((L - 2 * cut) / cell)))
        return np.concatenate([[lo], np.linspace(lo + cut, hi - cut, inner + 1), [hi]])
    n = max(1, int(math.ceil(L / cell)))
    return np.linspace(lo, hi, n + 1)


def solid_plate(mesh, surf_fn, us, vs, gap, t, bevel, mat, corners=(0, 0, 0, 0), kind='plate', smooth=True):
    """Solid plate over a surface patch.

    surf_fn(u, v) -> (point, normal) or None; us, vs: sorted grid lines (metres in the patch's own coordinates).
    gap: clearance between the surface and the plate underside (z-fighting margin); t: thickness; bevel: chamfer of
    the top edge. corners: (u0v0, u1v0, u1v1, u0v1) flags: 1 = cut that corner (needs the cut grid lines from
    grid_coords(cut=...)). Returns (top_fn, ok) where top_fn(u, v) gives the top surface point + normal for bolts.
    Returns (None, False) when the surface function fails anywhere (the caller skips the plate)."""
    nu, nv = len(us), len(vs)
    base = np.zeros((nu, nv, 3)); nb = np.zeros((nu, nv, 3))
    for i, u in enumerate(us):
        for j, v in enumerate(vs):
            r = surf_fn(u, v)
            if r is None:
                return None, False
            base[i, j], nb[i, j] = r
    ut, vt = shrink_coords(us, bevel), shrink_coords(vs, bevel)
    top = np.zeros((nu, nv, 3))
    for i, u in enumerate(ut):
        for j, v in enumerate(vt):
            r = surf_fn(u, v)
            if r is None:
                return None, False
            top[i, j] = r[0] + r[1] * (gap + t)
    cut = {(0, 0): corners[0], (nu - 1, 0): corners[1], (nu - 1, nv - 1): corners[2], (0, nv - 1): corners[3]}
    # boundary loop (counter-clockwise in u, v), skipping cut corner vertices
    loop = [(i, 0) for i in range(nu)] + [(nu - 1, j) for j in range(1, nv)] + \
           [(i, nv - 1) for i in range(nu - 2, -1, -1)] + [(0, j) for j in range(nv - 2, 0, -1)]
    loop = [q for q in loop if not cut.get(q, 0)]
    # orientation: the top face normal must point along the surface normal
    du = base[-1, 0] - base[0, 0]; dv = base[0, -1] - base[0, 0]
    flip = np.cross(du, dv).dot(nb[nu // 2, nv // 2]) < 0
    ti = {}
    for i in range(nu):
        for j in range(nv):
            if not cut.get((i, j), 0):
                ti[(i, j)] = mesh.verts([top[i, j]])
    bot = {}
    for i in range(nu):
        for j in range(nv):
            if not cut.get((i, j), 0):
                bot[(i, j)] = mesh.verts([base[i, j] + nb[i, j] * gap])

    def quad_cells(idx, flipf, mat_, sm):
        for i in range(nu - 1):
            for j in range(nv - 1):
                c = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
                c = [q for q in c if q in idx]
                if len(c) < 3:
                    continue
                f = [idx[q] for q in c]
                mesh.face(f[::-1] if flipf else f, mat_, sm, kind)
    quad_cells(ti, flip, mat, smooth)
    quad_cells(bot, not flip, mat, smooth)
    # rim: top boundary (inset) -> outer edge at gap + t - bevel -> bottom edge at gap
    rim = [mesh.verts([base[i, j] + nb[i, j] * (gap + t - bevel)]) for (i, j) in loop]
    topl = [ti[q] for q in loop]
    botl = [bot[q] for q in loop]
    mesh.bridge(topl, rim, mat, False, kind, flip=not flip)
    mesh.bridge(rim, botl, mat, False, kind, flip=not flip)

    def top_fn(u, v):
        r = surf_fn(u, v)
        if r is None:
            return None
        return r[0] + r[1] * (gap + t), r[1]
    return top_fn, True


def solid_quad(mesh, surf_fn, q, gap, t, bevel, mat, kind='plate', cell=0.2, smooth=True):
    """solid plate over any four-sided outline q = ((u, v) x 4: q00, q10, q11, q01, counter-clockwise) of the surface
    function's (u, v) space (bilinear map, so slanted bars and trapezoids conform to the surface too)"""
    q = np.asarray(q, float)
    Lu = max(np.linalg.norm(q[1] - q[0]), np.linalg.norm(q[2] - q[3]))
    Lv = max(np.linalg.norm(q[3] - q[0]), np.linalg.norm(q[2] - q[1]))
    if Lu < 1e-3 or Lv < 1e-3:
        return None, False

    def g(a, b):
        s, w = a / Lu, b / Lv
        uv = (1 - s) * (1 - w) * q[0] + s * (1 - w) * q[1] + s * w * q[2] + (1 - s) * w * q[3]
        return surf_fn(float(uv[0]), float(uv[1]))
    return solid_plate(mesh, g, grid_coords(0.0, Lu, cell), grid_coords(0.0, Lv, cell), gap, t,
                       min(bevel, 0.3 * min(Lu, Lv)), mat, kind=kind, smooth=smooth)


def picture_frame(mesh, surf_fn, W, H, rim, gap, t, bevel, mat, kind='frame', cell=0.3, sep=0.004):
    """raised rim of four strips round the panel [0, W] x [0, H] of surf_fn (top / bottom strips full width, the side
    strips between them, `sep` apart so no faces coincide). The centre stays lower, so ambient occlusion and ink form
    inside it. Returns the number of strips built."""
    pieces = (((0.0, W), (0.0, rim)), ((0.0, W), (H - rim, H)),
              ((0.0, rim), (rim + sep, H - rim - sep)), ((W - rim, W), (rim + sep, H - rim - sep)))
    n = 0
    for (u0, u1), (v0, v1) in pieces:
        if u1 - u0 < 0.02 or v1 - v0 < 0.02:
            continue
        _, ok = solid_plate(mesh, surf_fn, grid_coords(u0, u1, cell), grid_coords(v0, v1, cell), gap, t,
                            min(bevel, 0.3 * min(u1 - u0, v1 - v0)), mat, kind=kind)
        n += int(ok)
    return n


def slotted_plate(mesh, surf_fn, W, H, gap, t, bevel, mat, n_slots=3, slot_w=0.05, ang=58.0, margin=0.075,
                  back_mat='dark_metal', kind='slotted', end=0.09):
    """armour plate [0, W] x [0, H] with n_slots narrow slanted slots cut through it (reference 1: the slotted plates on
    the bow and the flank). A thin flush dark backing fills the slots; the plate itself is a top bar, a bottom bar and
    n_slots + 1 slanted pieces between the slots. Slots lean by `ang` degrees from the horizontal."""
    vb, vt = margin + 0.004, H - margin - 0.004
    dx = (vt - vb) / math.tan(math.radians(ang))
    span = W - 2 * end - dx - slot_w
    if vt - vb < 0.08 or span <= 1.6 * slot_w * n_slots:
        return False                                 # too small for these slots: build nothing
    _, ok = solid_plate(mesh, surf_fn, grid_coords(0.0, W, 0.3), grid_coords(0.0, H, 0.3), gap, 0.01, 0.003, back_mat,
                        kind=kind)
    if not ok:
        return False
    g2 = gap + 0.01 + 0.003
    for (v0, v1) in ((0.0, margin), (H - margin, H)):
        solid_plate(mesh, surf_fn, grid_coords(0.0, W, 0.3), np.array([v0, v1]), g2, t, min(bevel, 0.25 * margin), mat,
                    kind=kind)
    cs = [end + span * (i + 0.5) / n_slots for i in range(n_slots)]
    for i in range(n_slots + 1):
        lb = 0.0 if i == 0 else cs[i - 1] + slot_w
        rb = W if i == n_slots else cs[i]
        lt = 0.0 if i == 0 else lb + dx
        rt = W if i == n_slots else rb + dx
        solid_quad(mesh, surf_fn, ((lb, vb), (rb, vb), (rt, vt), (lt, vt)), g2, t, bevel * 0.6, mat, kind=kind,
                   cell=0.15)
    return True


# ------------------------------------------------------------------ bolts
def bolt(mesh, p, n, r=0.03, h=0.022, sink=0.006, sides=6, mat='bolt', kind='bolt', phase=None, rng=None):
    """hex bolt head: a closed frustum, base ring (r) sunk `sink` below p, top ring (0.72 r) h above p (20 triangles)"""
    u, v, n = ortho_frame(n)
    ph = phase if phase is not None else (rng.random() * math.pi / 3 if rng else 0.0)
    b = ring_pts(vec(p) - n * sink, u, v, r, sides, ph)
    tp = ring_pts(vec(p) + n * h, u, v, r * 0.72, sides, ph)
    mesh.prism(b, tp, mat, False, kind)


def bolt_row(mesh, top_fn, pts_uv, r=0.03, h=0.022, mat='bolt', rng=None):
    n = 0
    for (u, v) in pts_uv:
        q = top_fn(u, v)
        if q is None:
            continue
        bolt(mesh, q[0], q[1], r=r, h=h, mat=mat, rng=rng)
        n += 1
    return n


def rivet(mesh, p, n, r=0.022, h=0.012, sink=0.004, sides=8, mat='bolt', kind='rivet'):
    """low domed round rivet head: a ring of `sides` (sunk `sink` below p) and a smooth cone to an apex h above p, closed
    by a flat bottom (8 sides: 14 triangles). Smooth shading makes the low cone read as a dome."""
    u, v, n = ortho_frame(n)
    b = mesh.verts(ring_pts(vec(p) - n * sink, u, v, r, sides))
    a = mesh.verts([vec(p) + n * h])
    ring = list(range(b, b + sides))
    mesh.cap(ring, mat, kind, flip=True)
    for i in range(sides):
        mesh.face((ring[i], ring[(i + 1) % sides], a), mat, True, kind)


def rivet_row(mesh, top_fn, pts_uv, r=0.022, h=0.012, mat='bolt'):
    n = 0
    for (u, v) in pts_uv:
        q = top_fn(u, v)
        if q is None:
            continue
        rivet(mesh, q[0], q[1], r=r, h=h, mat=mat)
        n += 1
    return n


def corner_pts(us, vs, inset, cut=0.0, corners=(0, 0, 0, 0)):
    """one rivet position per plate corner (u0v0, u1v0, u1v1, u0v1), moved in along the diagonal past a cut corner"""
    u0, u1, v0, v1 = us[0], us[-1], vs[0], vs[-1]
    out = []
    for k, (a, b, su, sv) in enumerate(((u0, v0, 1, 1), (u1, v0, -1, 1), (u1, v1, -1, -1), (u0, v1, 1, -1))):
        e = inset + (cut * 0.5 if corners[k] else 0.0)
        out.append((a + su * e, b + sv * e))
    return out


def edge_bolts(us, vs, edges, inset, spacing, cut=0.0):
    """bolt positions (u, v) along the chosen plate edges ('u0', 'u1', 'v0', 'v1'), inset from the edge, evenly
    spaced, keeping clear of the corners by inset + cut"""
    u0, u1, v0, v1 = us[0], us[-1], vs[0], vs[-1]
    out = []
    c = inset + cut * 0.7

    def line(a, b, fixed, along_u):
        L = b - a
        if L <= 0:
            return
        k = max(1, int(round(L / spacing)))
        for i in range(k + 1):
            x = a + L * i / k
            out.append((x, fixed) if along_u else (fixed, x))
    if 'v0' in edges:
        line(u0 + c, u1 - c, v0 + inset, True)
    if 'v1' in edges:
        line(u0 + c, u1 - c, v1 - inset, True)
    if 'u0' in edges:
        line(v0 + c + (spacing if 'v0' in edges else 0), v1 - c - (spacing if 'v1' in edges else 0), u0 + inset, False)
    if 'u1' in edges:
        line(v0 + c + (spacing if 'v0' in edges else 0), v1 - c - (spacing if 'v1' in edges else 0), u1 - inset, False)
    return out


# ------------------------------------------------------------------ tubes and pipes
def fillet_path(pts, radius, seg=4, min_turn=12.0):
    """polyline with every inner corner replaced by a circular-ish arc (quadratic Bezier, seg segments)"""
    pts = [vec(p) for p in pts]
    if len(pts) < 3 or radius <= 0:
        return pts
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        a, b, c = pts[i - 1], pts[i], pts[i + 1]
        la, lc = np.linalg.norm(b - a), np.linalg.norm(c - b)
        if np.dot(unit(b - a), unit(c - b)) > math.cos(math.radians(min_turn)):
            out.append(b)                       # nearly straight: no fillet (keeps long pipes light)
            continue
        rr = min(radius, la * 0.45, lc * 0.45)
        p0 = b + unit(a - b) * rr
        p2 = b + unit(c - b) * rr
        for s in range(seg + 1):
            t = s / seg
            out.append((1 - t) ** 2 * p0 + 2 * (1 - t) * t * b + t ** 2 * p2)
    out.append(pts[-1])
    # drop near duplicates
    clean = [out[0]]
    for p in out[1:]:
        if np.linalg.norm(p - clean[-1]) > 1e-4:
            clean.append(p)
    return clean


def tube(mesh, path, r, sides=8, mat='copper', kind='pipe', caps=True, smooth=True, radii=None):
    """sweep a circle along a polyline (parallel transport frames); radii: optional per-point radius"""
    P = [vec(p) for p in path]
    n = len(P)
    T = []
    for i in range(n):
        if i == 0:
            t = P[1] - P[0]
        elif i == n - 1:
            t = P[-1] - P[-2]
        else:
            t = unit(P[i + 1] - P[i]) + unit(P[i] - P[i - 1])
        T.append(unit(t))
    u, _, _ = ortho_frame(T[0], (0.0, 0.0, 1.0))
    rings = []
    prev_t = T[0]
    for i in range(n):
        t = T[i]
        # parallel transport of u
        ax = np.cross(prev_t, t)
        s = np.linalg.norm(ax)
        if s > 1e-8:
            ang = math.atan2(s, prev_t.dot(t))
            R = np.array(Matrix.Rotation(ang, 3, V(ax / s)))
            u = R @ u
        u = unit(u - t * u.dot(t))
        w = np.cross(t, u)
        rr = r if radii is None else radii[i]
        # mitre: scale the ring in the bend plane so the wall keeps its thickness
        rings.append(ring_pts(P[i], u, w, rr, sides))
        prev_t = t
    idx = []
    for rg in rings:
        b = mesh.verts(rg)
        idx.append(list(range(b, b + sides)))
    for i in range(n - 1):
        mesh.bridge(idx[i], idx[i + 1], mat, smooth, kind)
    if caps:
        mesh.cap(idx[0], mat, kind, flip=True)
        mesh.cap(idx[-1], mat, kind)
    return T


def cylinder(mesh, p0, p1, r, sides=8, mat='machinery', kind='misc', smooth=True, caps=True, r1=None):
    a = vec(p0); b = vec(p1)
    t = unit(b - a)
    u, w, _ = ortho_frame(t, (0.0, 0.0, 1.0)) if abs(t[2]) < 0.95 else ortho_frame(t, (1.0, 0.0, 0.0))
    ra = ring_pts(a, u, w, r, sides)
    rb = ring_pts(b, u, w, r if r1 is None else r1, sides)
    ia, ib = mesh.prism(ra, rb, mat, smooth, kind, caps=False)
    if caps:
        mesh.cap(ia, mat, kind, flip=True)
        mesh.cap(ib, mat, kind)
    return ia, ib


def flange(mesh, p, t, r, thick=0.035, sides=10, mat='brass', kind='pipe', bolts=0, bolt_r=0.012):
    """flange disc on a pipe; `bolts` rivet heads on its +t face only"""
    t = unit(t)
    cylinder(mesh, vec(p) - t * thick / 2, vec(p) + t * thick / 2, r, sides, mat, kind, smooth=False)
    if bolts:
        u, w, _ = ortho_frame(t, (0.0, 0.0, 1.0)) if abs(t[2]) < 0.95 else ortho_frame(t, (1.0, 0.0, 0.0))
        for q in ring_pts(vec(p) + t * thick / 2, u, w, r * 0.74, bolts, 0.3):
            rivet(mesh, q, t, r=bolt_r, h=bolt_r * 0.6, sink=0.003)


def clamp(mesh, p, t, r, surf_p, surf_n, w=0.045, mat='dark_metal', kind='clamp'):
    """pipe clamp: a band round the pipe (6-sided, r + 1 cm) and one foot block down to the surface point"""
    t = unit(t)
    cylinder(mesh, vec(p) - t * w / 2, vec(p) + t * w / 2, r + 0.01, 6, mat, kind, smooth=False)
    n = unit(surf_n)
    top = vec(p) - n * (r * 0.5)
    bot = vec(surf_p) - n * 0.01
    if n.dot(top - bot) > 0.01:
        u, v, _ = ortho_frame(n, t)
        s = 0.5 * max(w, 0.04)
        sq = lambda c, k: np.array([c + k * (-s * u - s * v), c + k * (s * u - s * v), c + k * (s * u + s * v), c + k * (-s * u + s * v)])
        mesh.prism(sq(bot, 1.6), sq(top, 1.0), mat, False, kind)


def pipe_run(mesh, path, r, bend_r, sides=8, mat='copper', flange_at=(), clamp_at=(), surf_fn=None, kind='pipe',
             caps=True, flange_mat='brass', flange_k=1.4):
    """pipe along a polyline with rounded elbows. flange_at: fractions (0..1) of the length; clamp_at: fractions where
    a clamp foot goes down to the surface (surf_fn(point) -> (p, n) gives the surface below the pipe)"""
    P = fillet_path(path, bend_r, seg=4)
    tube(mesh, P, r, sides, mat, kind, caps=caps)
    L = np.concatenate([[0], np.cumsum([np.linalg.norm(P[i + 1] - P[i]) for i in range(len(P) - 1)])])

    def at(frac):
        s = frac * L[-1]
        i = int(np.clip(np.searchsorted(L, s) - 1, 0, len(P) - 2))
        a = (s - L[i]) / max(L[i + 1] - L[i], 1e-9)
        return P[i] + (P[i + 1] - P[i]) * a, unit(P[i + 1] - P[i])
    for fr in flange_at:
        p, t = at(fr)
        flange(mesh, p, t, r * flange_k, thick=max(0.025, r * 0.6), sides=max(8, sides), mat=flange_mat, kind=kind,
               bolts=6 if r >= 0.03 else 0)
    for fr in clamp_at:
        p, t = at(fr)
        if surf_fn is None:
            continue
        q = surf_fn(p)
        if q is None:
            continue
        clamp(mesh, p, t, r, q[0], q[1])
    return P, L[-1]


def gland(mesh, p, n, u_hint, r_pipe, size=None, back=0.0, mat='dark_metal', kind='gland'):
    """where a pipe or conduit enters the hull: a square bolted plate (its back `back` above p along n) with a brass
    collar round the pipe and a rivet in each corner"""
    u, v, n = ortho_frame(n, u_hint)
    s = size or max(0.06, r_pipe * 2.2)
    o = vec(p) + n * back
    chamfer_box(mesh, frame_matrix(o + n * 0.01, u, v, n), s, s, 0.01, 0.003, mat, kind)
    cylinder(mesh, o + n * 0.012, o + n * 0.045, r_pipe * 1.45, 8, 'brass', kind, smooth=False)
    for su in (-1, 1):
        for sv in (-1, 1):
            rivet(mesh, o + n * 0.02 + u * su * (s - 0.022) + v * sv * (s - 0.022), n, r=0.012, h=0.007, sink=0.003)


def housing(mesh, origin, n, u_hint, w, h, d, mat='machinery', lid_mat='dark_metal', kind='housing', stubs=(),
            r_stub=0.045):
    """chunky machinery housing standing on a surface (origin on the surface, n out): chamfered body, bolted base
    flange, a lid on the front face with two hinges (lower edge) and two dog latches (upper edge, +v side), rivets.
    stubs: (side along u (+-1), position along v in -1..1) of flanged pipe stubs on the side faces. Returns the stub
    ends [(point, direction)] for joining pipes."""
    u, v, n = ortho_frame(n, u_hint)
    o = vec(origin)
    chamfer_box(mesh, frame_matrix(o + n * (d / 2 + 0.012), u, v, n), w / 2, h / 2, d / 2, min(0.03, d * 0.2), mat, kind)
    chamfer_box(mesh, frame_matrix(o + n * 0.008, u, v, n), w / 2 + 0.04, h / 2 + 0.04, 0.008, 0.003, lid_mat, kind)
    for su in (-1, 1):
        for sv in (-1, 1):
            rivet(mesh, o + n * 0.016 + u * su * (w / 2 + 0.02) + v * sv * (h / 2 + 0.02), n, r=0.014, h=0.008)
    top = o + n * (d + 0.012)
    lw, lh = w / 2 - 0.06, h / 2 - 0.07
    chamfer_box(mesh, frame_matrix(top + n * 0.008, u, v, n), lw, lh, 0.01, 0.004, lid_mat, kind)
    for su in (-1, 1):
        for sv in (-1, 1):
            rivet(mesh, top + n * 0.018 + u * su * (lw - 0.03) + v * sv * (lh - 0.03), n, r=0.014, h=0.008)
    for s in (-0.6, 0.6):                               # hinges on the lower edge
        p = top + n * 0.012 + v * (-lh - 0.012) + u * s * lw
        cylinder(mesh, p - u * 0.055, p + u * 0.055, 0.017, 6, lid_mat, kind, smooth=True)
    for s in (-0.55, 0.55):                             # dog latches on the upper edge: a lug on the body + a lever
        p = top + v * (lh + 0.03) + u * s * lw
        chamfer_box(mesh, frame_matrix(p + n * 0.012, u, v, n), 0.022, 0.014, 0.012, 0.003, 'steel', kind)
        chamfer_box(mesh, frame_matrix(p + n * 0.028 - v * 0.022, u, v, n), 0.009, 0.032, 0.006, 0.002, 'steel', kind)
    ends = []
    for (side, vv) in stubs:
        a = o + n * (d / 2 + 0.012) + u * side * (w / 2) + v * vv * (h / 2 - 0.08)
        b = a + u * side * 0.07
        cylinder(mesh, a - u * side * 0.01, b, r_stub, 8, 'copper', kind, smooth=True)
        flange(mesh, b - u * side * 0.012, u * side, r_stub * 1.55, thick=0.024, sides=8, mat='brass', kind=kind, bolts=4,
               bolt_r=0.009)
        ends.append((b, u * side))
    return ends


def pump_body(mesh, p0, p1, r, n, mat='machinery', kind='pump', inlet_dir=None):
    """horizontal pump / pressure body from p0 to p1 (centre line), radius r, resting on two saddles down to the
    surface along -n: domed end at p1, a flanged flat cover at p0, two flanged bands, an inlet stub on the top"""
    a, b = vec(p0), vec(p1)
    t = unit(b - a)
    n = unit(vec(n) - t * t.dot(n))
    u, w, _ = ortho_frame(t, n)
    L = np.linalg.norm(b - a)
    k = 12
    prof = [(0.0, 1.0), (L - 0.14, 1.0), (L - 0.06, 0.85), (L, 0.45)]
    idx = []
    for s, f in prof:
        bi = mesh.verts(ring_pts(a + t * s, u, w, r * f, k))
        idx.append(list(range(bi, bi + k)))
    for i in range(len(idx) - 1):
        mesh.bridge(idx[i], idx[i + 1], mat, True, kind)
    mesh.cap(idx[0], mat, kind, flip=True)
    mesh.cap(idx[-1], mat, kind)
    flange(mesh, a - t * 0.012, -t, r * 1.12, thick=0.03, sides=12, mat='dark_metal', kind=kind, bolts=6, bolt_r=0.011)
    for s in (0.3, 0.62):
        c = a + t * L * s
        cylinder(mesh, c - t * 0.022, c + t * 0.022, r + 0.014, 12, 'dark_metal', kind, smooth=False)
    for s in (0.22, 0.78):                              # saddles
        c = a + t * L * s - n * (r * 0.55)
        foot = c - n * (r * 0.45 + 0.03)
        chamfer_box(mesh, frame_matrix((c + foot) / 2, t, np.cross(n, t), n), 0.03, r * 0.8,
                    np.linalg.norm(c - foot) / 2 + 0.005, 0.004, 'dark_metal', kind)
    up = unit(np.cross(t, n)) if inlet_dir is None else unit(vec(inlet_dir) - t * t.dot(inlet_dir))
    c = a + t * L * 0.46 + up * r * 0.85              # inlet stub sideways along the surface (keeps the pump low)
    cylinder(mesh, c - up * 0.02, c + up * 0.05, r * 0.32, 8, 'brass', kind, smooth=False)


def valve_body(mesh, p, t, n, r, mat='brass', kind='valve'):
    """inline valve block without a hand wheel: a hex body round the pipe, a bonnet sideways along the surface
    (keeps it close to the hull), a gauge disc on the bonnet"""
    t = unit(t); n = unit(n - t * t.dot(n))
    w = np.cross(t, n)
    L = r * 3.2
    cylinder(mesh, vec(p) - t * L / 2, vec(p) + t * L / 2, r * 1.6, 6, mat, kind, smooth=False)
    b0 = vec(p) + w * r * 1.2
    cylinder(mesh, b0, b0 + w * r * 1.5, r * 0.85, 8, mat, kind, smooth=False)
    g0 = b0 + w * r * 1.5
    cylinder(mesh, g0, g0 + w * r * 0.35, r * 1.3, 12, 'dark_metal', kind, smooth=False)


# ------------------------------------------------------------------ boxes, vents, brackets, tanks
def chamfer_box(mesh, M, sx, sy, sz, c=0.01, mat='machinery', kind='box'):
    """box centred on M's origin with half sizes (sx, sy, sz) in M's axes, edges chamfered by c"""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= 2 * sx; v.co.y *= 2 * sy; v.co.z *= 2 * sz
    if c > 0:
        bmesh.ops.bevel(bm, geom=list(bm.edges), offset=c, segments=1, affect='EDGES', profile=0.5)
    mesh.from_bmesh(bm, M, mat, kind)
    bm.free()


def louver_vent(mesh, origin, n, u_hint, w, h, depth=0.08, louvres=5, mat='dark_metal', frame_mat='machinery',
                kind='vent'):
    """framed vent box on a surface (origin on the surface, n outward): frame walls, a back plate, slanted louvres"""
    u, v, n = ortho_frame(n, u_hint)
    o = vec(origin)
    fw = 0.035                     # frame wall
    M = frame_matrix(o + n * (depth / 2), u, v, n)
    # back plate
    chamfer_box(mesh, frame_matrix(o + n * 0.012, u, v, n), w / 2, h / 2, 0.012, 0.004, frame_mat, kind)
    # four frame walls
    for su, sv, hx, hy in ((0, 1, w / 2, fw / 2), (0, -1, w / 2, fw / 2), (1, 0, fw / 2, h / 2 - fw), (-1, 0, fw / 2, h / 2 - fw)):
        c = o + n * (depth / 2) + u * su * (w / 2 - fw / 2) + v * sv * (h / 2 - fw / 2)
        chamfer_box(mesh, frame_matrix(c, u, v, n), hx, hy, depth / 2, 0.006, frame_mat, kind)
    # louvres: slats along u, tilted 35 degrees (top edge out), inside the frame
    inner_h = h - 2 * fw
    for k in range(louvres):
        cv = -inner_h / 2 + inner_h * (k + 0.5) / louvres
        c = o + n * (depth * 0.5) + v * cv
        ang = math.radians(35)
        vv = v * math.cos(ang) + n * math.sin(ang)
        nn = np.cross(u, vv)
        chamfer_box(mesh, frame_matrix(c, u, vv, nn), w / 2 - fw, inner_h / louvres * 0.62, 0.007, 0.0, mat, kind)


def grille_round(mesh, origin, n, r, bars=5, depth=0.05, mat='dark_metal', kind='vent'):
    u, v, n = ortho_frame(n)
    o = vec(origin)
    cylinder(mesh, o - n * 0.005, o + n * 0.012, r * 0.98, 16, 'machinery', kind, smooth=False)
    # ring: 16-sided annulus prism
    k = 16
    outer_b = ring_pts(o, u, v, r, k); outer_t = ring_pts(o + n * depth, u, v, r, k)
    inner_b = ring_pts(o, u, v, r - 0.04, k); inner_t = ring_pts(o + n * depth, u, v, r - 0.04, k)
    ob_i = mesh.verts(outer_b); ot_i = mesh.verts(outer_t); ib_i = mesh.verts(inner_b); it_i = mesh.verts(inner_t)
    OB = list(range(ob_i, ob_i + k)); OT = list(range(ot_i, ot_i + k))
    IB = list(range(ib_i, ib_i + k)); IT = list(range(it_i, it_i + k))
    mesh.bridge(OB, OT, mat, False, kind)
    mesh.bridge(OT, IT, mat, False, kind)
    mesh.bridge(IT, IB, mat, False, kind)
    mesh.bridge(IB, OB, mat, False, kind)
    for i in range(bars):
        y = -r + 2 * r * (i + 1) / (bars + 1)
        half = math.sqrt(max(r * r - y * y, 0.0)) - 0.03
        c = o + n * (depth * 0.55) + v * y
        chamfer_box(mesh, frame_matrix(c, u, v, n), half, 0.012, depth * 0.4, 0.0, mat, kind)


def gusset(mesh, origin, n, up, depth, height, t=0.025, mat='dark_metal', kind='bracket'):
    """triangular bracket: right angle at the top on the surface, sticking out `depth` along n, `height` down the
    surface (up = the surface direction toward the right angle); plus a foot plate along the surface"""
    o = vec(origin); n = unit(n)
    up = unit(vec(up) - n * vec(up).dot(n))
    s = np.cross(up, n)
    tri = [o, o + n * depth, o - up * height]
    b = [p - s * t / 2 for p in tri]
    tp = [p + s * t / 2 for p in tri]
    mesh.prism(b, tp, mat, False, kind)
    # foot plate on the surface
    fp = frame_matrix(o - up * height / 2 + n * 0.008, s, up, n)
    chamfer_box(mesh, fp, t * 2.2, height / 2 + 0.02, 0.008, 0.0, mat, kind)


def tank(mesh, p0, p1, r, n, mat='rust_red', strap_mat='dark_metal', kind='tank'):
    """gas bottle from p0 to p1 (centre line), radius r, domed ends; two straps that wrap round it and down to the
    surface along -n"""
    a, b = vec(p0), vec(p1)
    t = unit(b - a)
    u, w, _ = ortho_frame(t, n)
    k = 12
    L = np.linalg.norm(b - a)
    rings = []
    prof = [(0.0, 0.35), (0.04, 0.8), (0.12, 1.0), (L - 0.12, 1.0), (L - 0.04, 0.8), (L, 0.35)]
    for s, f in prof:
        rings.append(ring_pts(a + t * s, u, w, r * f, k))
    idx = []
    for rg in rings:
        bi = mesh.verts(rg)
        idx.append(list(range(bi, bi + k)))
    for i in range(len(idx) - 1):
        mesh.bridge(idx[i], idx[i + 1], mat, True, kind)
    mesh.cap(idx[0], mat, kind, flip=True)
    mesh.cap(idx[-1], mat, kind)
    # valve stub at the b end
    cylinder(mesh, b - t * 0.01, b + t * 0.07, r * 0.25, 8, 'brass', kind, smooth=False)
    for s in (0.25, 0.75):
        c = a + t * L * s
        cylinder(mesh, c - t * 0.025, c + t * 0.025, r + 0.012, 12, strap_mat, kind, smooth=False)


def machinery_box(mesh, origin, n, u_hint, w, h, d, ribs=5, mat='machinery', rib_mat='dark_metal', kind='machinery',
                  rng=None, gland=True):
    """box standing on a surface (origin on the surface, n out): chamfered body, cooling ribs on the face, a base
    flange with bolts, a cable gland on one side. Returns the gland's outer point and direction."""
    u, v, n = ortho_frame(n, u_hint)
    o = vec(origin)
    chamfer_box(mesh, frame_matrix(o + n * (d / 2 + 0.01), u, v, n), w / 2, h / 2, d / 2, min(0.02, d * 0.15), mat, kind)
    # base flange
    chamfer_box(mesh, frame_matrix(o + n * 0.012, u, v, n), w / 2 + 0.035, h / 2 + 0.035, 0.012, 0.004, rib_mat, kind)
    for sx in (-1, 1):
        for sy in (-1, 1):
            bolt(mesh, o + n * 0.024 + u * sx * (w / 2 + 0.018) + v * sy * (h / 2 + 0.018), n, r=0.012, h=0.01, sink=0.003)
    # ribs on the face (along v)
    for i in range(ribs):
        cu = -w / 2 + w * (i + 1) / (ribs + 1)
        c = o + n * (d + 0.01 + 0.012) + u * cu
        chamfer_box(mesh, frame_matrix(c, u, v, n), 0.008, h / 2 * 0.85, 0.014, 0.0, rib_mat, kind)
    out = None
    if gland:
        c = o + n * (d * 0.5 + 0.01) + v * (-h / 2)
        cylinder(mesh, c + v * 0.0, c - v * 0.05, 0.03, 8, 'brass', kind, smooth=False)
        out = (c - v * 0.05, -v)
    return out


def cable(mesh, p0, p1, sag, r=0.022, sides=6, seg=10, mat='dark_metal', kind='cable', down=(0, 0, -1), ferrule=True):
    a, b = vec(p0), vec(p1)
    dn = unit(down)
    pts = []
    for i in range(seg + 1):
        t = i / seg
        pts.append(a + (b - a) * t + dn * sag * 4 * t * (1 - t))
    tube(mesh, pts, r, sides, mat, kind, caps=True)
    if ferrule:
        for p, q in ((pts[0], pts[1]), (pts[-1], pts[-2])):
            cylinder(mesh, p, p + unit(q - p) * 0.05, r * 1.6, 8, 'brass', kind, smooth=False)
    return pts


def chain(mesh, p0, p1, sag, link=0.09, wire=0.011, mat='dark_metal', kind='chain', down=(0, 0, -1)):
    """links along a sagging curve; consecutive links turned 90 degrees; each link a 6 x 4 swept loop"""
    a, b = vec(p0), vec(p1)
    dn = unit(down)
    N = 64
    curve = [a + (b - a) * (i / N) + dn * sag * 4 * (i / N) * (1 - i / N) for i in range(N + 1)]
    L = np.concatenate([[0], np.cumsum([np.linalg.norm(curve[i + 1] - curve[i]) for i in range(N)])])
    step = link * 0.78
    k = int(L[-1] // step)
    side = unit(np.cross(unit(b - a), dn))
    for i in range(k):
        s = (i + 0.5) * step
        j = int(np.clip(np.searchsorted(L, s) - 1, 0, N - 1))
        c = curve[j] + (curve[j + 1] - curve[j]) * ((s - L[j]) / max(L[j + 1] - L[j], 1e-9))
        t = unit(curve[j + 1] - curve[j])
        w = side if i % 2 == 0 else unit(np.cross(t, side))
        # stadium loop in the (t, w) plane, a 4-sided wire section
        pn = unit(np.cross(t, w))
        hl, hr = link * 0.5 - wire, link * 0.28 - wire
        pts = [c + t * hl * math.cos(q * math.pi / 3) + w * hr * math.sin(q * math.pi / 3) for q in range(6)]
        idx = []
        for q in range(6):
            tn = unit(pts[(q + 1) % 6] - pts[q - 1])
            rad = unit(np.cross(tn, pn))
            bi = mesh.verts(ring_pts(pts[q], pn, rad, wire, 4, math.pi / 4))
            idx.append(list(range(bi, bi + 4)))
        for q in range(6):
            mesh.bridge(idx[q], idx[(q + 1) % 6], mat, False, kind)


def piston(mesh, p0, p1, r=0.06, mat='dark_metal', rod_mat='brass', kind='piston', eye_axis=None):
    """hydraulic actuator from p0 (cylinder end) to p1 (rod end): eyes at both ends, cylinder 60 % of the length"""
    a, b = vec(p0), vec(p1)
    t = unit(b - a)
    L = np.linalg.norm(b - a)
    e = r * 1.1
    ax = unit(eye_axis) if eye_axis is not None else ortho_frame(t)[0]
    for p in (a, b):
        cylinder(mesh, p - ax * r * 0.6, p + ax * r * 0.6, e, 8, 'machinery', kind, smooth=False)
    c0 = a + t * e
    c1 = a + t * (L * 0.6)
    cylinder(mesh, c0, c1, r, 10, mat, kind, smooth=True)
    cylinder(mesh, c1 - t * 0.02, c1 + t * 0.03, r * 1.15, 10, mat, kind, smooth=False)
    cylinder(mesh, c1, b - t * e, r * 0.45, 8, rod_mat, kind, smooth=True)
    cylinder(mesh, c0 - t * 0.01, c0 + t * 0.04, r * 1.15, 10, mat, kind, smooth=False)


# ------------------------------------------------------------------ geometry checks
def mesh_overlap_pairs(bvh_a, bvh_b):
    return len(bvh_a.overlap(bvh_b))


def nonmanifold_edges(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    n = sum(1 for e in bm.edges if not e.is_manifold)
    bm.free()
    return n


def drop_floating(mesh, others, tol=0.02, sample=600, tol_kind=(('rivet', 0.01),)):
    """Every loose piece must touch something: the ship (`others`: BVH trees) or another piece of this builder, within
    `tol`. Pieces that touch nothing (a bolt over a hull gap, a cable end in open air ...) are removed. Returns
    {kind: pieces removed}."""
    if not mesh.f:
        return {}
    fc, vc = mesh.components()
    det = BVHTree.FromPolygons(mesh.v, [list(f) for f in mesh.f])
    by = {}
    for i, c in enumerate(vc):
        by.setdefault(int(c), []).append(i)
    ckind = {}
    for i, c in enumerate(fc):
        ckind.setdefault(int(c), mesh.k[i])
    tk = dict(tol_kind)
    bad = set()
    for c, vs in by.items():
        tol_c = tk.get(ckind.get(c), tol)          # a rivet must sit on its plate, not merely near another one
        if len(vs) > sample:
            vs = vs[::int(math.ceil(len(vs) / sample))]
        touch = False
        for vi in vs:
            p = V(mesh.v[vi])
            if any(b.find_nearest(p, tol_c)[0] is not None for b in others):
                touch = True
                break
            for (_, _, fi, _) in det.find_nearest_range(p, tol_c):
                if fc[fi] != c:
                    touch = True
                    break
            if touch:
                break
        if not touch:
            # no vertex near anything: does a face of the piece pass through another piece or the ship?
            fl_ = [i for i in range(len(mesh.f)) if fc[i] == c] if len(by[c]) < 5000 else []
            if fl_:
                own = BVHTree.FromPolygons(mesh.v, [list(mesh.f[i]) for i in fl_])
                touch = any(fc[j] != c for (_, j) in own.overlap(det)) or any(own.overlap(b) for b in others)
        if not touch:
            bad.add(c)
    drop = [i for i in range(len(mesh.f)) if int(fc[i]) in bad]
    kinds = {}
    seen = set()
    for i in drop:
        c = int(fc[i])
        if c not in seen:
            seen.add(c)
            kinds[mesh.k[i]] = kinds.get(mesh.k[i], 0) + 1
    if drop:
        mesh.drop_faces(drop)
    return kinds
