"""Round 3 assembler: the whole detailed ship in one file, checked as one (2026-11-28).

  blender_capped.sh --python detail_assemble.py                       # build + checks -> zones/AirshipRig_detail_full.blend
  blender_capped.sh --python detail_assemble.py -- --no-save          # checks only
  blender_capped.sh --python detail_assemble.py -- --tool rigcheck <detail_rigcheck.py args>
  blender_capped.sh --python detail_assemble.py -- --tool render <detail_render.py args>   # env DETAIL_ASSEMBLE_CPU=1:
                                                                      # clay (Cycles) on the CPU when the GPU is full
  blender_capped.sh --python detail_assemble.py -- --verify           # reopen the saved file and check it
  blender_capped.sh --python detail_assemble.py -- --test-talal-z1 --no-save --out FILE   # exercise the 'Talal
                                                                      # edited zone 1' path (writes rig/tmp only)

Build:
 1. Zone 1 source. If rig/detail/AirshipRig_detail.blend (Talal's approved zone 1 file) still has the approved md5
    31317912621726b5e647c78bfc0cf948, zone 1 comes from the generated zones/AirshipRig_detail_z1.blend (identical
    geometry, z1_approved_hash.json). If the md5 changed, Talal edited it: every object in that file that is not in
    rig/AirshipRig.blend (zone 1's objects and anything he added) is taken from it, read only, into
    zones/AirshipRig_detail_z1_talal.blend, and the report lists exactly what differs from the generated zone 1.
 2. Opens rig/AirshipRig.blend read only, appends Detail_Z1 .. Detail_Z7 (each object's fingerprint is compared with
    the zone's own hash file), appends the two front turrets for the checks only (they are not part of SK_Airship).
 3. Global checks on the assembly (base edits applied, i.e. the deleted faces are not there): object checklist,
    floating pieces, overlaps between details (cross-zone seams), keep-clear volumes (helm, turrets, cannons),
    PA_Airship walkable tops, the deck, silhouette (per object and the outline seen from the side / top / front),
    ownership per zone, the stairs (geometry against stairs_collision.json, head room, clear width, nothing in the
    walking corridor), triangle totals per zone / object / bone / kind and for the whole SK.
 4. Integration fixes in the output file only: zone 1's inside-out pieces are flipped (winding and custom normals;
    vertex positions unchanged; ZONES.md: "flip them at export"), the registered base edits (base_edits/z*.json) are
    applied to SM_Airship for real (bmesh, whole islands; kept vertices / UVs / corners / weights hashed before and
    after, like rig_build.py did for round 2), then the registered base colour overrides (base_recolor/z*.json,
    r3_base_recolor.py; since 2026-11-28 the keel block is rust) are written onto it: FACE attribute 'r3_recolor' and
    SM_Airship['round3_base_recolor'] (no geometry, UV or material slot change).
 5. Saves zones/AirshipRig_detail_full.blend (D.safe_save: zones/ only) and Docs/Airship/round3/full_report.json.
The md5 and dates of the protected .blend files are recorded at the start and at the end of every run.

--tool rigcheck / render run detail_rigcheck.main / detail_render.main with zone 1 taken from the same source as the
build (they open rig/AirshipRig.blend and append the zones, with the base edits in memory: the same content as the
full file, and the "before" state of the renders still has the unedited ship).
"""
import bpy, bmesh, sys, os, json, math, time, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from mathutils import Vector as V, Matrix
from mathutils.bvhtree import BVHTree
import rig_common as C
import detail_common as D

FULL_BLEND = D.ZONES_DIR + '/AirshipRig_detail_full.blend'
Z1_TALAL_BLEND = D.ZONES_DIR + '/AirshipRig_detail_z1_talal.blend'
APPROVED_MD5 = '31317912621726b5e647c78bfc0cf948'
DOCS = '/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/round3'
REPORT = DOCS + '/full_report.json'
PA_JSON = '/mnt/new_partition/UnrealProjects/_AirshipWork/Saved/Airship/pa_hull_boxes.json'
STAIRS_JSON = DOCS + '/stairs_collision.json'
ZONE_NUMS = (1, 2, 3, 4, 5, 6, 7)
HASH_FILES = {1: D.ZONES_DIR + '/z1_approved_hash.json'}
HASH_FILES.update({z: D.ZONES_DIR + '/z%d_hash.json' % z for z in ZONE_NUMS[1:]})
TOL, TOL_RIVET = 0.02, 0.01          # floating-piece tolerances (zone builds: drop_floating)
WALK_LAYER, WALK_FREE, WALK_OVERHEAD = 2.2, 0.20, 1.75     # zone 7's walk check numbers
STAIRS_OBJ = 'SM_AirshipDetail_Z7_Stairs'


def opts():
    a = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    o = {}
    for i, k in enumerate(a):
        if k.startswith('--'):
            o[k[2:]] = a[i + 1] if i + 1 < len(a) and not a[i + 1].startswith('--') else True
    return o, a


def md5_file(p):
    h = hashlib.md5()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 22), b''):
            h.update(b)
    return h.hexdigest()


def protected_state():
    out = {}
    for p in D.PROTECTED_BLENDS:
        if os.path.exists(p):
            st = os.stat(p)
            out[p] = dict(md5=md5_file(p), mtime=time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(st.st_mtime)),
                          size=st.st_size)
    return out


def talal_z1_changed():
    if os.environ.get('DETAIL_ASSEMBLE_FORCE_TALAL_Z1'):
        return True
    return md5_file(D.APPROVED_Z1_BLEND) != APPROVED_MD5


def z1_source():
    """the .blend zone 1 is appended from: the generated file, or the normalised copy of Talal's edited file"""
    if not talal_z1_changed():
        return D.zone_blend(1)
    if not os.path.exists(Z1_TALAL_BLEND):
        raise RuntimeError('Talal changed %s: run the build first (it writes %s)' % (D.APPROVED_Z1_BLEND, Z1_TALAL_BLEND))
    return Z1_TALAL_BLEND


def r(v, n=3):
    return round(float(v), n)


# ================================================================== zone 1 from Talal's file (only if he edited it)
def normalise_talal_z1(out_path):
    """every object of Talal's file that is not in rig/AirshipRig.blend -> collection Detail_Z1 of a copy of the rig,
    parented to its Armature, role materials by palette_key; then a diff against the generated zone 1"""
    import detail_hash as H
    bpy.ops.wm.open_mainfile(filepath=C.RIG_BLEND)
    base = {o.name for o in bpy.data.objects}
    with bpy.data.libraries.load(D.APPROVED_Z1_BLEND, link=False) as (src, dst):
        names = [n for n in src.objects if n not in base]
        dst.objects = list(names)
    arm = bpy.data.objects['Armature']
    coll = bpy.data.collections.new('Detail_Z1')
    bpy.context.scene.collection.children.link(coll)
    mats = {m['palette_key']: m for m in D.ensure_materials()}
    got, no_role = [], {}
    for ob in [o for o in dst.objects if o is not None]:
        for c in list(ob.users_collection):
            c.objects.unlink(ob)
        coll.objects.link(ob)
        got.append(ob.name)
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
                else:
                    no_role[ob.name] = no_role.get(ob.name, []) + [m.name if m else None]
    for o in [o for o in bpy.data.objects if o.type == 'ARMATURE' and o != arm]:
        bpy.data.objects.remove(o)
    bpy.context.view_layer.update()
    talal_fp = {o.name: H.fingerprint(o) for o in coll.all_objects if o.type == 'MESH'}
    # the generated zone 1 for the diff (appended under .001 names, removed again)
    before = set(bpy.data.objects)
    with bpy.data.libraries.load(D.zone_blend(1), link=False) as (src, dst):
        dst.objects = [n for n in src.objects if n.startswith('SM_AirshipDetail_Z1_')]
    gen = {}
    for ob in [o for o in dst.objects if o is not None]:
        bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.update()
    for ob in [o for o in dst.objects if o is not None]:
        gen[ob.name.rsplit('.', 1)[0]] = (H.fingerprint(ob), CK_world_co(ob))
    diff = dict(objects_only_in_talal=sorted(set(talal_fp) - set(gen)),
                objects_only_in_generated=sorted(set(gen) - set(talal_fp)), objects={})
    import re

    def norm(fp):
        # the appended copies hang on their own duplicate armature ('Armature.001'): compare names without the suffix
        fp = dict(fp)
        st = lambda n: re.sub(r'\.\d{3}$', '', n) if isinstance(n, str) else n
        fp['parent'] = st(fp.get('parent'))
        fp['modifiers'] = [[t, st(n)] for t, n in fp.get('modifiers', [])]
        return fp
    talal_fp = {k: norm(v) for k, v in talal_fp.items()}
    gen = {k: (norm(v[0]), v[1]) for k, v in gen.items()}
    for k in sorted(set(talal_fp) & set(gen)):
        a, (b, bco) = talal_fp[k], gen[k]
        d = {f: (b.get(f), a.get(f)) for f in ('verts', 'faces', 'tris', 'co_0p1mm_md5', 'faces_md5', 'roles_md5',
                                                'bones_md5', 'parent', 'modifiers') if a.get(f) != b.get(f)}
        if 'co_0p1mm_md5' in d and a['verts'] == b['verts']:
            tco = CK_world_co(bpy.data.objects[k])
            mv = np.linalg.norm(tco - bco, axis=1)
            m = mv > 1e-4
            d['moved_vertices'] = int(m.sum())
            d['max_move_m'] = r(mv.max(), 4)
            if m.any():
                d['moved_bbox'] = [[r(v) for v in tco[m].min(0)], [r(v) for v in tco[m].max(0)]]
        diff['objects'][k] = d or 'identical'
    for k in diff['objects_only_in_talal']:
        ob = bpy.data.objects[k]
        diff.setdefault('added', {})[k] = dict(type=ob.type, tris=talal_fp.get(k, {}).get('tris'),
                                               bbox=None if ob.type != 'MESH' else
                                               [[r(v) for v in CK_world_co(ob).min(0)], [r(v) for v in CK_world_co(ob).max(0)]])
    diff['materials_without_role'] = no_role
    for o in [o for o in bpy.data.objects if o not in before]:
        bpy.data.objects.remove(o)
    # SM_Airship in Talal's file (the zones never change it: say so if he did)
    before = set(bpy.data.objects)
    with bpy.data.libraries.load(D.APPROVED_Z1_BLEND, link=False) as (src, dst):
        dst.objects = ['SM_Airship']
    ts = dst.objects[0]
    bpy.context.scene.collection.objects.link(ts)
    bpy.context.view_layer.update()
    fa, fb = H.fingerprint(ts), H.fingerprint(bpy.data.objects['SM_Airship'])
    diff['SM_Airship'] = 'identical' if all(fa[f] == fb[f] for f in H.GEOM_FIELDS) else \
        {f: (fb[f], fa[f]) for f in H.GEOM_FIELDS if fa[f] != fb[f]}
    for o in [o for o in bpy.data.objects if o not in before]:
        bpy.data.objects.remove(o)
    D.safe_save(out_path)
    return dict(talal_objects=got, diff=diff, saved=out_path)


def CK_world_co(ob):
    me = ob.data
    co = np.empty(len(me.vertices) * 3); me.vertices.foreach_get('co', co)
    M = np.array(ob.matrix_world)
    return co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3]


# ================================================================== mesh data of the assembly
class ObData:
    """world vertices, polygons, triangles, loose pieces, rivet marks and a BVH of one mesh object"""

    def __init__(self, ob, poly_mask=None):
        me = ob.data
        self.ob, self.name = ob, ob.name
        self.co = CK_world_co(ob)
        nP = len(me.polygons)
        self.lt = np.empty(nP, np.int64); me.polygons.foreach_get('loop_total', self.lt)
        self.ls = np.empty(nP, np.int64); me.polygons.foreach_get('loop_start', self.ls)
        self.lv = np.empty(len(me.loops), np.int64); me.loops.foreach_get('vertex_index', self.lv)
        self.mark = np.zeros(nP, bool)
        if nP:
            me.polygons.foreach_get('use_freestyle_mark', self.mark)
        me.calc_loop_triangles()
        t = np.empty(len(me.loop_triangles) * 3, np.int64); me.loop_triangles.foreach_get('vertices', t)
        tp = np.empty(len(me.loop_triangles), np.int64); me.loop_triangles.foreach_get('polygon_index', tp)
        self.tri, self.tri_poly = t.reshape(-1, 3), tp
        if poly_mask is not None:
            k = poly_mask[self.tri_poly]
            self.tri, self.tri_poly = self.tri[k], self.tri_poly[k]
        self.bvh = BVHTree.FromPolygons(self.co.tolist(), self.tri.tolist(), all_triangles=True) if len(self.tri) else None
        used = np.unique(self.tri) if len(self.tri) else np.zeros(0, np.int64)
        self.bbox = (self.co[used].min(0), self.co[used].max(0)) if len(used) else (np.zeros(3), np.zeros(3))
        self._pid = None

    def pieces(self):
        """piece id per polygon (union-find over the polygons' vertices) and the vertex list of every piece"""
        if self._pid is None:
            nV = len(self.co)
            par = np.arange(nV)

            def find(a):
                while par[a] != a:
                    par[a] = par[par[a]]
                    a = par[a]
                return a
            for s, t in zip(self.ls.tolist(), self.lt.tolist()):
                vs = self.lv[s:s + t]
                r0 = find(int(vs[0]))
                for q in vs[1:]:
                    rq = find(int(q))
                    if rq != r0:
                        par[rq] = r0
            root = np.array([find(i) for i in range(nV)])
            self._pid = root[self.lv[self.ls]]
            pl = np.repeat(self._pid, self.lt)
            key = np.unique(pl * (nV + 1) + self.lv)
            pv, vv = key // (nV + 1), key % (nV + 1)
            cut = np.nonzero(np.diff(pv))[0] + 1
            self._pverts = {int(g[0]): vs for g, vs in zip(np.split(pv, cut), np.split(vv, cut))}
        return self._pid, self._pverts

    def tri_bones(self):
        names = {g.index: g.name for g in self.ob.vertex_groups}
        vb = np.array([names[v.groups[0].group] if len(v.groups) else '?' for v in self.ob.data.vertices], dtype=object)
        return vb[self.tri[:, 0]] if len(self.tri) else np.zeros(0, dtype=object)


def zone_of(ob):
    for c in ob.users_collection:
        if c.name.startswith('Detail_Z'):
            return 'Z' + c.name[len('Detail_Z'):]
    return None


# ================================================================== checks
def floating_check(dets, others):
    """every loose piece of every detail object must touch something (the ship without the deleted faces, a prop, or
    another piece of any detail object) within 2 cm (rivets: 1 cm), like the zone builds' drop_floating. Fallback for
    a piece with no vertex near anything: does one of its triangles pass through something else?"""
    allx = list(others) + list(dets)
    co, tri, t_obj, t_pc, off = [], [], [], [], 0
    for k, x in enumerate(allx):
        co.append(x.co); tri.append(x.tri + off); off += len(x.co)
        t_obj.append(np.full(len(x.tri), k))
        t_pc.append(x.pieces()[0][x.tri_poly] if k >= len(others) else np.full(len(x.tri), -1))
    tri = np.concatenate(tri)
    t_obj, t_pc = np.concatenate(t_obj), np.concatenate(t_pc)
    co = np.concatenate(co)
    big = BVHTree.FromPolygons(co.tolist(), tri.tolist(), all_triangles=True)
    out = dict(pieces=0, floating=[], by_object={})
    for k0, d in enumerate(dets):
        k = k0 + len(others)
        pid, pverts = d.pieces()
        tri_pid = pid[d.tri_poly]
        poly_of_piece = {}
        for i, c in enumerate(pid.tolist()):
            poly_of_piece.setdefault(c, []).append(i)
        nfl = 0
        for c, vs in pverts.items():
            out['pieces'] += 1
            tol = TOL_RIVET if d.mark[poly_of_piece[c]].all() else TOL
            if len(vs) > 600:
                vs = vs[::int(math.ceil(len(vs) / 600))]
            touch = False
            for vi in vs.tolist():
                for (_, _, fi, _) in big.find_nearest_range(V(d.co[vi]), tol):
                    if t_obj[fi] != k or t_pc[fi] != c:
                        touch = True
                        break
                if touch:
                    break
            if not touch:
                own_t = d.tri[tri_pid == c]
                if len(own_t):
                    own = BVHTree.FromPolygons(d.co.tolist(), own_t.tolist(), all_triangles=True)
                    touch = any(t_obj[j] != k or t_pc[j] != c for (_, j) in own.overlap(big))
            if not touch:
                nfl += 1
                pc = d.co[pverts[c]]
                out['floating'].append(dict(object=d.name, centre=[r(v) for v in pc.mean(0)], verts=int(len(pc)),
                                            rivet=bool(tol == TOL_RIVET)))
        out['by_object'][d.name] = dict(pieces=len(pverts), floating=nfl)
    out['floating_total'] = len(out['floating'])
    out['floating'] = out['floating'][:40]
    return out


def overlap_check(dets, zone, props):
    """triangle overlaps between detail objects (at rest), split into cross-zone pairs (the seams) and same-zone pairs,
    and between detail objects and the props (cannons at rest, helm) and the turrets"""
    def bb_hit(a, b, m=0.01):
        return np.all(a.bbox[0] - m <= b.bbox[1]) and np.all(b.bbox[0] - m <= a.bbox[1])

    def ex(a, b, pairs):
        pts = []
        for ia, ib in pairs[:2000:max(1, len(pairs) // 6)]:
            pts.append([r(v) for v in (a.co[a.tri[ia]].mean(0) + b.co[b.tri[ib]].mean(0)) / 2])
        return pts[:6]
    cross, same, prop = [], [], []
    for i, a in enumerate(dets):
        for b in dets[i + 1:]:
            if a.bvh is None or b.bvh is None or not bb_hit(a, b):
                continue
            pr = a.bvh.overlap(b.bvh)
            if pr:
                rec = dict(a=a.name, b=b.name, tri_pairs=len(pr), examples=ex(a, b, pr))
                (cross if zone[a.name] != zone[b.name] else same).append(rec)
        for p in props:
            if a.bvh is None or p.bvh is None or not bb_hit(a, p):
                continue
            pr = a.bvh.overlap(p.bvh)
            if pr:
                prop.append(dict(detail=a.name, prop=p.name, tri_pairs=len(pr), examples=ex(a, p, pr)))
    return dict(cross_zone=cross, cross_zone_pairs=int(sum(x['tri_pairs'] for x in cross)),
                same_zone=same, same_zone_pairs=int(sum(x['tri_pairs'] for x in same)),
                with_props_or_turrets=prop, with_props_pairs=int(sum(x['tri_pairs'] for x in prop)))


def in_volume_np(P, kind, prm):
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    if kind == 'box':
        x0, x1, y0, y1, z0, z1 = prm
        return (x >= x0) & (x <= x1) & (y >= y0) & (y <= y1) & (z >= z0) & (z <= z1)
    if kind == 'cyl_x':
        x0, x1, cy, cz, rr = prm
        return (x >= x0) & (x <= x1) & (np.hypot(y - cy, z - cz) <= rr)
    if kind == 'cyl_z':
        cx, cy, rr, z0, z1 = prm
        return (z >= z0) & (z <= z1) & (np.hypot(x - cx, y - cy) <= rr)
    if kind == 'sph_up':
        cx, cy, cz, rr = prm
        return (z >= cz - 0.05) & (np.linalg.norm(P - np.array([cx, cy, cz]), axis=1) <= rr)
    raise KeyError(kind)


def keep_clear_check(dets):
    import detail_zones as ZN
    out = {}
    for d in dets:
        for name, kind, prm, _ in ZN.KEEP_CLEAR:
            n = int(in_volume_np(d.co, kind, prm).sum())
            if n:
                out.setdefault(name, {})[d.name] = n
    return dict(hits=out, total=int(sum(sum(v.values()) for v in out.values())),
                volumes=[dict(name=n, kind=k, params=list(p)) for n, k, p, _ in ZN.KEEP_CLEAR])


def obb_list_blender(stairs):
    """stairs_collision.json boxes as (centre, axes (3x3 rows), half sizes) in Blender metres"""
    out = []
    for b in stairs['boxes']:
        cs = np.array(b['corners'], float) * np.array([0.01, -0.01, 0.01])
        c = cs.mean(0)
        # corners are ordered sx, sy, sz in (-1, 1): index = 4 * (sx > 0) + 2 * (sy > 0) + (sz > 0)
        ax = (cs[4] - cs[0]) / 2.0
        ay = (cs[2] - cs[0]) / 2.0
        az = (cs[1] - cs[0]) / 2.0
        hs = np.array([np.linalg.norm(ax), np.linalg.norm(ay), np.linalg.norm(az)])
        A = np.array([ax / hs[0], ay / hs[1], az / hs[2]])
        out.append(dict(name=b['name'], kind=b['kind'], c=c, A=A, h=hs, corners=cs))
    return out


def in_obb(P, b, pad=0.0):
    q = (np.asarray(P) - b['c']) @ b['A'].T
    return np.all(np.abs(q) <= b['h'] + pad, axis=1)


def walkable_check(dets, boxes, obst_bvh, deck_bvh, deck_is_walk, stairs_obbs):
    """nothing standing free on a walkable top. A detail vertex is a candidate when it lies inside a PA_Airship box
    footprint, above that box's top by at most 2.2 m, and inside no box (a vertex inside any box is inside collision:
    nobody can touch it; this also handles stacked boxes, the flaw of the shared pa_report). A candidate is fine when
    it is within 0.20 m of existing non-walkable geometry (a post, a leg, a wall, a rail), inside the truss (over the
    bow wedge's top under the slab) or above head height (1.75 m), or covered by the new stairs collision boxes; else
    it stands free on a walkable top (must be 0). Second test, the deck itself: a vertex above z 1.5 whose ray down
    hits a walkable face of SM_Airship within 2.2 m, and nothing non-walkable within 0.20 m."""
    mn = np.array([b[0] for b in boxes]); mx = np.array([b[1] for b in boxes]); nm = [b[2] for b in boxes]
    res = dict(per_object={}, free_total=0, free_examples=[], deck_free_total=0, deck_free_examples=[],
               deck_no_collision_examples=[], stairs_object_skipped=True)
    for d in dets:
        if d.name == STAIRS_OBJ:
            continue
        P = d.co
        n = len(P)
        inside = np.zeros(n, bool)
        layer_box = np.full(n, -1)
        layer_dz = np.full(n, 99.0)
        for k in range(len(boxes)):
            foot = (P[:, 0] >= mn[k, 0]) & (P[:, 0] <= mx[k, 0]) & (P[:, 1] >= mn[k, 1]) & (P[:, 1] <= mx[k, 1])
            if not foot.any():
                continue
            inside |= foot & (P[:, 2] >= mn[k, 2] - 0.01) & (P[:, 2] <= mx[k, 2] + 0.01)
            dz = P[:, 2] - mx[k, 2]
            m = foot & (dz > 0.01) & (dz <= WALK_LAYER) & (dz < layer_dz)
            layer_box[m] = k
            layer_dz[m] = dz[m]
        cand = (layer_box >= 0) & ~inside
        st = np.zeros(n, bool)
        for b in stairs_obbs:
            st |= in_obb(P, b, 0.03)
        cand &= ~st
        rec = dict(in_walk_layer=int((layer_box >= 0).sum()), inside_a_box=int(inside.sum()),
                   covered_by_stairs_collision=int(st.sum()), attached=0, truss=0, overhead=0, free=0)
        for i in np.nonzero(cand)[0].tolist():
            p = V(P[i])
            if obst_bvh.find_nearest(p, WALK_FREE)[0] is not None:
                rec['attached'] += 1
            elif nm[layer_box[i]].startswith(('Hull_Well', 'Hull_Bow')):
                rec['truss'] += 1
            elif layer_dz[i] > WALK_OVERHEAD:
                rec['overhead'] += 1
            else:
                rec['free'] += 1
                if sum(1 for e in res['free_examples'] if e['object'] == d.name) < 6:
                    res['free_examples'].append(dict(object=d.name, p=[r(v) for v in P[i]], box=nm[layer_box[i]],
                                                     above_top_m=r(layer_dz[i])))
        # the deck (SM_Airship's walkable faces), whether or not a PA box covers it
        dk, dtruss, dnone = 0, 0, 0
        for i in np.nonzero((P[:, 2] > 1.5) & ~st & ~inside)[0].tolist():
            p = V(P[i])
            h = deck_bvh.ray_cast(p, V((0, 0, -1)), WALK_LAYER)
            if h[0] is None or not deck_is_walk[h[2]] or h[3] < 0.005:
                continue
            if obst_bvh.find_nearest(p, WALK_FREE)[0] is not None or h[3] > WALK_OVERHEAD:
                continue
            hp = np.array(h[0])
            kb = [k for k in range(len(boxes)) if mn[k, 0] <= hp[0] <= mx[k, 0] and mn[k, 1] <= hp[1] <= mx[k, 1] and
                  abs(mx[k, 2] - hp[2]) < 0.3]
            if not kb:
                dnone += 1           # deck-like skin with no PA box over it: no collision, nobody can stand there
                if sum(1 for e in res['deck_no_collision_examples'] if e['object'] == d.name) < 3:
                    res['deck_no_collision_examples'].append(dict(object=d.name, p=[r(v) for v in P[i]],
                                                                  above_face_m=r(h[3])))
                continue
            if any(nm[k].startswith(('Hull_Well', 'Hull_Bow')) for k in kb):
                dtruss += 1          # the bow wedge's top inside the truss, under the slab: nobody walks there
                continue
            dk += 1
            if sum(1 for e in res['deck_free_examples'] if e['object'] == d.name) < 6:
                res['deck_free_examples'].append(dict(object=d.name, p=[r(v) for v in P[i]], above_deck_m=r(h[3]),
                                                      boxes=[nm[k] for k in kb]))
        rec['deck_free'] = dk
        rec['deck_truss'] = dtruss
        rec['deck_no_collision'] = dnone
        res['per_object'][d.name] = rec
        res['free_total'] += rec['free']
        res['deck_free_total'] += dk
    return res


def silhouette_check(dets, ship_surf_bvh, sample=2):
    """distance of detail vertices to the nearest SM_Airship face (minus the deleted ones), per object"""
    out = {}
    for d in dets:
        P = d.co[::sample]
        dist = np.array([(lambda h: h[3] if h[0] is not None else 9.0)(ship_surf_bvh.find_nearest(V(p), 9.0)) for p in P])
        out[d.name] = dict(max_m=r(dist.max()), p99_m=r(np.percentile(dist, 99)), over_0_20=int((dist > 0.20).sum()),
                           verts_tested=int(len(P)), worst=[r(v) for v in P[int(np.argmax(dist))]])
    return out


def outline_check(before, after, owner_names, cell=0.10):
    """the ship's outline seen from the side (+Y), top (+Z) and front (+X): orthographic ray grids, 10 cm. before =
    the ship as it is + props + turrets, after = the edited ship + props + turrets + details. Reports the area that is
    new (and how far it is from the old outline: within 10 / 20 cm, or more, with the objects that make it), and the
    area that went (the deleted faces)."""
    bvh_b, bvh_a, tri_owner = before, after[0], after[1]
    views = {'side': (1, (0, 2), (-23.0, 33.0), (-7.5, 11.5)), 'top': (2, (0, 1), (-23.0, 33.0), (-12.0, 12.0)),
             'front': (0, (1, 2), (-12.0, 12.0), (-7.5, 11.5))}
    out = {}
    for name, (ax, (ia, ib), ra, rb) in views.items():
        us = np.arange(ra[0], ra[1], cell) + cell / 2
        vs = np.arange(rb[0], rb[1], cell) + cell / 2
        B = np.zeros((len(us), len(vs)), bool)
        A = np.zeros_like(B)
        own = np.full(B.shape, -1)
        d = [0.0, 0.0, 0.0]; d[ax] = -1.0
        dv = V(d)
        for i, u in enumerate(us):
            for j, v in enumerate(vs):
                o = [0.0, 0.0, 0.0]; o[ax] = 60.0; o[ia] = u; o[ib] = v
                ov = V(o)
                B[i, j] = bvh_b.ray_cast(ov, dv, 120.0)[0] is not None
                h = bvh_a.ray_cast(ov, dv, 120.0)
                if h[0] is not None:
                    A[i, j] = True
                    own[i, j] = tri_owner[h[2]]
        new = A & ~B
        gone = B & ~A
        Bd = B.copy()
        ring = []
        for k in range(1, 4):
            Bn = Bd.copy()
            Bn[1:] |= Bd[:-1]; Bn[:-1] |= Bd[1:]; Bn[:, 1:] |= Bd[:, :-1]; Bn[:, :-1] |= Bd[:, 1:]
            Bd = Bn
            ring.append(int((new & Bd).sum()))
        far = new & ~Bd
        by_obj = {}
        for (i, j) in zip(*np.nonzero(far)):
            k = owner_names[own[i, j]] if own[i, j] >= 0 else '?'
            by_obj[k] = by_obj.get(k, 0) + 1
        a2 = cell * cell
        out[name] = dict(before_m2=r(B.sum() * a2, 1), after_m2=r(A.sum() * a2, 1), new_m2=r(new.sum() * a2, 2),
                         new_within_10cm_m2=r(ring[0] * a2, 2), new_within_20cm_m2=r(ring[1] * a2, 2),
                         new_beyond_30cm_m2=r(far.sum() * a2, 2), new_beyond_30cm_by_object_m2={
                             k: r(v * a2, 2) for k, v in sorted(by_obj.items(), key=lambda x: -x[1])},
                         gone_m2=r(gone.sum() * a2, 2),
                         gone_bbox=None if not gone.any() else [[r(us[np.nonzero(gone)[0].min()]), r(vs[np.nonzero(gone)[1].min()])],
                                                                [r(us[np.nonzero(gone)[0].max()]), r(vs[np.nonzero(gone)[1].max()])]])
    return out


def stairs_check(stairs_d, scene_bvh, scene_co_sets, stairs_json):
    """the stairs geometry against stairs_collision.json: tread levels (risers), going, slope, landing and top step
    heights, the ramp boxes' top faces through the nosings; head room and clear width probed against everything;
    nothing of the ship, the props, the turrets or another detail inside the walking corridor"""
    S = json.load(open(stairs_json))
    U = S['usability']
    me = stairs_d.ob.data
    nP = len(me.polygons)
    cen = np.empty(nP * 3); me.polygons.foreach_get('center', cen); cen = cen.reshape(-1, 3)
    nrm = np.empty(nP * 3); me.polygons.foreach_get('normal', nrm); nrm = nrm.reshape(-1, 3)
    M = np.array(stairs_d.ob.matrix_world)
    cen = cen @ M[:3, :3].T + M[:3, 3]
    obbs = {b['name']: b for b in obb_list_blender(S)}
    r1, r2 = obbs['Stairs_Ramp1'], obbs['Stairs_Ramp2']
    yc = float((r1['c'][1] + r2['c'][1]) / 2)
    hw = U['clear_width_m'] / 2
    up = (nrm[:, 2] > 0.97) & (np.abs(cen[:, 1] - yc) < hw - 0.02) & ~stairs_d.mark
    # top z of every up face (its highest vertex) and its x range
    tops = []
    for k in np.nonzero(up)[0].tolist():
        s, t = stairs_d.ls[k], stairs_d.lt[k]
        pts = stairs_d.co[stairs_d.lv[s:s + t]]
        tops.append((float(pts[:, 2].max()), float(pts[:, 0].min()), float(pts[:, 0].max())))
    tops.sort()
    levels = []
    for z, x0, x1 in tops:
        if levels and z - levels[-1]['z_lo'] < 0.06:
            L = levels[-1]
            L['z'] = max(L['z'], z); L['x0'] = min(L['x0'], x0); L['x1'] = max(L['x1'], x1)
        else:
            levels.append(dict(z_lo=z, z=z, x0=x0, x1=x1))
    # deck at the foot and platform at the top (SM_Airship / gantry deck under the first / last level)
    x_first = min(L['x0'] for L in levels)
    h0 = scene_bvh.ray_cast(V((x_first - 0.45, yc, 4.0)), V((0, 0, -1)), 4.0)
    h1 = scene_bvh.ray_cast(V((S_TOP_X(S) + 0.40, yc, 9.0)), V((0, 0, -1)), 4.0)
    z_deck = float(h0[0][2]) if h0[0] is not None else None
    z_top = float(h1[0][2]) if h1[0] is not None else None
    zs = [z_deck] + [L['z'] for L in levels] + [z_top]
    risers = np.diff(np.array(zs))
    treads = [L for L in levels if L['x1'] - L['x0'] < 0.6]
    landing = [L for L in levels if L['x1'] - L['x0'] >= 0.6]
    # going: front edge (nosing, the aft edge of each tread: the stairs rise toward +x) to the next one
    noses = sorted(L['x0'] for L in treads)
    gaps = np.diff(np.array(noses))
    goings = gaps[gaps < 0.6]
    # the ramp boxes' top faces must pass through the nosings
    def ramp_dev(b, Ls):
        n = b['A'][2] * (1 if b['A'][2][2] > 0 else -1)
        top_c = b['c'] + n * b['h'][2]
        return [r(float(np.dot(np.array([L['x0'], yc, L['z']]) - top_c, n)), 4) for L in Ls]
    zl = landing[0]['z'] if landing else 99.0
    t1 = [L for L in treads if L['z'] < zl]
    t2 = [L for L in treads if L['z'] > zl]
    dev = ramp_dev(r1, t1) + ramp_dev(r2, t2)
    land_box = obbs.get('Stairs_Landing')
    top_box = obbs.get('Stairs_TopStep')
    out = dict(levels=len(levels), treads=len(treads), landing_levels=len(landing),
               risers_measured=int(len(risers)), riser_min_m=r(risers.min(), 4), riser_max_m=r(risers.max(), 4),
               riser_json_m=U['riser_m'], risers_json=U['risers'],
               going_min_m=r(goings.min(), 4) if len(goings) else None,
               going_max_m=r(goings.max(), 4) if len(goings) else None, going_json_m=U['going_m'],
               slope_deg=r(math.degrees(math.atan2(float(np.mean(risers)), float(np.mean(goings)))), 2) if len(goings) else None,
               slope_json_deg=U['slope_deg'], z_deck=r(z_deck), z_top=r(z_top), rise_m=r(z_top - z_deck),
               rise_json_m=U['rise_m'],
               ramp_top_vs_nosings_m=dict(max_abs=r(max(abs(v) for v in dev), 4) if dev else None, n=len(dev)),
               landing_z=r(landing[0]['z']) if landing else None,
               landing_box_top_z=r((land_box['c'] + land_box['A'][2] * np.sign(land_box['A'][2][2]) * land_box['h'][2])[2]) if land_box else None,
               top_step_box_top_z=r((top_box['c'] + top_box['A'][2] * np.sign(top_box['A'][2][2]) * top_box['h'][2])[2]) if top_box else None)
    # probes along both flights (the nosing line through the levels)
    head, width, w_at, h_at = 9.0, 9.0, None, None
    lev = sorted(treads, key=lambda L: L['x0'])
    for L in lev + landing:
        for x in np.arange(L['x0'] + 0.03, L['x1'] - 0.02, 0.1):
            q = V((float(x), yc, L['z'] + 0.05))
            h = scene_bvh.ray_cast(q, V((0, 0, 1)), 9.0)
            hd = 9.0 if h[0] is None else h[3] + 0.05
            if hd < head:
                head, h_at = hd, [r(v) for v in q]
            for hh in (0.3, 0.8, 1.3, 1.8):
                q2 = V((float(x), yc, L['z'] + hh))
                ws = []
                for sg in (-1, 1):
                    h = scene_bvh.ray_cast(q2, V((0, sg, 0)), 3.0)
                    ws.append(3.0 if h[0] is None else h[3])
                if sum(ws) < width:
                    width, w_at = sum(ws), [r(v) for v in q2]
    # walking corridor: between the stringers, from 3 cm above the nosing line to 2.2 m above it
    xs = np.array([L['x0'] for L in lev] + [landing[0]['x0'], landing[0]['x1']] if landing else [L['x0'] for L in lev])
    zs_ = np.array([L['z'] for L in lev] + [landing[0]['z'], landing[0]['z']] if landing else [L['z'] for L in lev])
    order = np.argsort(xs)
    xs, zs_ = xs[order], zs_[order]
    intr = {}
    for name, P in scene_co_sets.items():
        m = (np.abs(P[:, 1] - yc) < hw - 0.03) & (P[:, 0] > xs[0]) & (P[:, 0] < S_TOP_X(S))
        if not m.any():
            continue
        Q = P[m]
        zf = np.interp(Q[:, 0], xs, zs_)
        k = int(((Q[:, 2] > zf + 0.03) & (Q[:, 2] < zf + 2.2)).sum())
        if k:
            intr[name] = k
    out.update(min_head_room_m=r(head), head_room_at=h_at, min_clear_width_m=r(width), narrowest_at=w_at,
               corridor_intrusions=intr)
    out['risers_list_m'] = [r(v, 4) for v in risers]
    out['ok_note'] = ('risers <= 0.22 m with 5 mm measuring tolerance (the deck is not flat: 2.39 at x 5, 2.36 at x '
                      '10); going >= 0.28; head room >= 2.2; clear width >= 1.4; nothing in the corridor; total rise '
                      'within 2 cm of the json; ramp tops within 3 cm of the nosings')
    out['ok'] = bool(out['riser_max_m'] <= 0.22 + 0.005 and (out['going_min_m'] or 0) >= 0.28 - 1e-3 and
                     head >= 2.2 and width >= 1.4 and not intr and
                     abs(out['rise_m'] - U['rise_m']) < 0.02 and out['ramp_top_vs_nosings_m']['max_abs'] < 0.03)
    return out


def S_TOP_X(S):
    b = [x for x in S['boxes'] if x['name'] == 'Stairs_TopStep'][0]
    return b['center'][0] / 100.0


# ================================================================== integration fixes
def flip_inside_out(ob):
    """flip every closed loose piece with a negative volume (winding reversed, custom normals negated for those
    corners, kept for all others). Vertex positions are unchanged. Returns the number of pieces flipped."""
    import detail_checks as CK
    vol, pid = CK.loose_piece_volumes(ob)
    bad = {c for c, v in vol.items() if v < -1e-9}
    if not bad:
        return dict(flipped=0)
    me = ob.data
    nP = len(me.polygons)
    cn = np.empty(len(me.loops) * 3); me.corner_normals.foreach_get('vector', cn); cn = cn.reshape(-1, 3)
    lt = np.empty(nP, np.int64); me.polygons.foreach_get('loop_total', lt)
    ls = np.empty(nP, np.int64); me.polygons.foreach_get('loop_start', ls)
    lv = np.empty(len(me.loops), np.int64); me.loops.foreach_get('vertex_index', lv)
    marks0 = np.zeros(nP, bool); me.polygons.foreach_get('use_freestyle_mark', marks0)
    mat0 = np.empty(nP, np.int64); me.polygons.foreach_get('material_index', mat0)
    flip = np.array([int(c) in bad for c in pid])
    old = {}
    for p in range(nP):
        s, t = ls[p], lt[p]
        old[p] = {int(lv[s + i]): cn[s + i] for i in range(t)}
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    bmesh.ops.reverse_faces(bm, faces=[bm.faces[i] for i in np.nonzero(flip)[0].tolist()])
    bm.to_mesh(me)
    bm.free()
    lt2 = np.empty(nP, np.int64); me.polygons.foreach_get('loop_total', lt2)
    ls2 = np.empty(nP, np.int64); me.polygons.foreach_get('loop_start', ls2)
    lv2 = np.empty(len(me.loops), np.int64); me.loops.foreach_get('vertex_index', lv2)
    new = np.zeros((len(me.loops), 3))
    for p in range(nP):
        sg = -1.0 if flip[p] else 1.0
        for i in range(lt2[p]):
            new[ls2[p] + i] = sg * old[p][int(lv2[ls2[p] + i])]
    me.normals_split_custom_set([tuple(v) for v in new])
    me.update()
    vol2, _ = CK.loose_piece_volumes(ob)
    cn2 = np.empty(len(me.loops) * 3); me.corner_normals.foreach_get('vector', cn2); cn2 = cn2.reshape(-1, 3)
    fn = np.empty(nP * 3); me.polygons.foreach_get('normal', fn); fn = fn.reshape(-1, 3)
    pl = np.repeat(np.arange(nP), lt2)
    agree = np.einsum('ij,ij->i', cn2, fn[pl]) > 0.0
    marks1 = np.zeros(nP, bool); me.polygons.foreach_get('use_freestyle_mark', marks1)
    mat1 = np.empty(nP, np.int64); me.polygons.foreach_get('material_index', mat1)
    return dict(flipped=len(bad), polygons_flipped=int(flip.sum()),
                inside_out_after=int(sum(1 for v in vol2.values() if v < -1e-9)),
                corner_normal_angle_change_max_deg=r(np.degrees(np.arccos(np.clip(
                    np.einsum('ij,ij->i', cn2, new / np.maximum(np.linalg.norm(new, axis=1)[:, None], 1e-12)), -1, 1))).max(), 3),
                corners_disagreeing_with_face=int((~agree).sum()), corners=int(len(agree)),
                marks_unchanged=bool((marks0 == marks1).all()), materials_unchanged=bool((mat0 == mat1).all()))


def mesh_hash(me, keep_verts=None):
    """rig_build.py's hash: vertex positions, corner UVs (every UV map) and corner vertex indices of the part made of
    keep_verts (renumbered in order), + the vertex group weights of those vertices"""
    co = np.empty(len(me.vertices) * 3, np.float32); me.vertices.foreach_get('co', co)
    lv = np.empty(len(me.loops), np.int32); me.loops.foreach_get('vertex_index', lv)
    uvs = []
    for L in me.uv_layers:
        uv = np.empty(len(me.loops) * 2, np.float32); L.data.foreach_get('uv', uv)
        uvs.append(uv)
    w = [tuple((g.group, round(g.weight, 5)) for g in v.groups) for v in me.vertices]
    if keep_verts is not None:
        new = np.full(len(me.vertices), -1, np.int64); new[keep_verts] = np.arange(len(keep_verts))
        co = co.reshape(-1, 3)[keep_verts].ravel()
        kl = new[lv] >= 0
        uvs = [u.reshape(-1, 2)[kl].ravel() for u in uvs]
        lv = new[lv[kl]].astype(np.int32)
        w = [w[i] for i in keep_verts.tolist()]
    h = hashlib.md5()
    for a in [co, lv] + uvs:
        h.update(a.tobytes())
    h.update(repr(w).encode())
    return h.hexdigest()


def apply_base_edits(ship_ob, mask, rep):
    """delete the masked SM_Airship faces for real (whole islands), keep everything else bit for bit"""
    me = ship_ob.data
    nP0, nV0 = len(me.polygons), len(me.vertices)
    tris0 = sum(len(p.vertices) - 2 for p in me.polygons)
    lt = np.empty(nP0, np.int64); me.polygons.foreach_get('loop_total', lt)
    ls = np.empty(nP0, np.int64); me.polygons.foreach_get('loop_start', ls)
    lv = np.empty(len(me.loops), np.int64); me.loops.foreach_get('vertex_index', lv)
    keep_loops = np.repeat(~mask, lt)
    keep_verts = np.unique(lv[keep_loops])
    kill_verts = np.setdiff1d(np.arange(nV0), keep_verts)
    partial = np.intersect1d(np.unique(lv[~keep_loops]), keep_verts)      # vertices shared with kept faces
    h0 = mesh_hash(me, keep_verts)
    had_custom = me.has_custom_normals
    cn0 = None
    if had_custom:
        cn0 = np.empty(len(me.loops) * 3); me.corner_normals.foreach_get('vector', cn0)
        cn0 = cn0.reshape(-1, 3)[keep_loops]
    bm = bmesh.new()
    bm.from_mesh(me)
    open0 = sum(1 for e in bm.edges if e.is_boundary)
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[bm.faces[i] for i in np.nonzero(mask)[0].tolist()], context='FACES_ONLY')
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
    bmesh.ops.delete(bm, geom=[e for e in bm.edges if not e.link_faces], context='EDGES')
    open1 = sum(1 for e in bm.edges if e.is_boundary)
    bm.to_mesh(me)
    bm.free()
    me.update()
    if had_custom:
        me.normals_split_custom_set([tuple(v) for v in cn0])
        me.update()
    h1 = mesh_hash(me)
    out = dict(faces_before=nP0, faces_after=len(me.polygons), faces_deleted=int(mask.sum()),
               verts_before=nV0, verts_after=len(me.vertices), verts_deleted=int(len(kill_verts)),
               shared_verts_with_kept_faces=int(len(partial)),
               tris_before=int(tris0), tris_after=int(sum(len(p.vertices) - 2 for p in me.polygons)),
               open_border_edges_before=open0, open_border_edges_after=open1,
               kept_hash_before=h0, kept_hash_after=h1, kept_part_unchanged=h0 == h1,
               custom_normals=bool(had_custom), edits=rep)
    ship_ob['round3_base_edits'] = json.dumps({k: dict(faces=v['faces'], tris=v['tris']) for k, v in rep.items()})
    return out


# ================================================================== triangles
def tri_tables(dets, zone):
    per_obj, per_zone, per_bone = {}, {}, {}
    for d in dets:
        tb = d.tri_bones()
        rv = int(d.mark[d.tri_poly].sum())
        u, c = np.unique(tb.astype(str), return_counts=True)
        bones = {k: int(v) for k, v in zip(u, c)}
        per_obj[d.name] = dict(zone=zone[d.name], tris=int(len(d.tri)), verts=int(len(d.co)), rivet_tris=rv,
                               rivet_share=r(rv / max(1, len(d.tri))), bones=bones)
        z = per_zone.setdefault(zone[d.name], dict(objects=0, tris=0, rivet_tris=0))
        z['objects'] += 1; z['tris'] += int(len(d.tri)); z['rivet_tris'] += rv
        for k, v in bones.items():
            key = k
            if '_Petal' in k:
                key = k.split('_Petal')[0] + '_PetalNN'
            per_bone[key] = per_bone.get(key, 0) + v
    for z in per_zone.values():
        z['rivet_share'] = r(z['rivet_tris'] / max(1, z['tris']))
    return per_obj, dict(sorted(per_zone.items())), dict(sorted(per_bone.items(), key=lambda x: -x[1]))


def lod_estimate(dets):
    """triangles a LOD would keep: LOD1 = without rivets (Freestyle-marked faces) and loose pieces under 15 cm;
    LOD2 = only pieces of 0.6 m and more (plates, big pipes, housings), no rivets"""
    lod = dict(lod0=0, lod1=0, lod2=0, rivets=0, small_pieces_under_15cm=0)
    for d in dets:
        pid, pv = d.pieces()
        tri_pid = pid[d.tri_poly]
        diag = {c: float(np.linalg.norm(d.co[v].max(0) - d.co[v].min(0))) for c, v in pv.items()}
        dg = np.array([diag[c] for c in tri_pid.tolist()]) if len(tri_pid) else np.zeros(0)
        rv = d.mark[d.tri_poly]
        lod['lod0'] += int(len(d.tri))
        lod['rivets'] += int(rv.sum())
        lod['small_pieces_under_15cm'] += int((~rv & (dg < 0.15)).sum())
        lod['lod1'] += int((~rv & (dg >= 0.15)).sum())
        lod['lod2'] += int((~rv & (dg >= 0.60)).sum())
    return lod


# ================================================================== build
def build(o):
    t0 = time.time()
    log = dict(started=time.strftime('%Y-%m-%d %H:%M:%S'), protected_start=protected_state(), steps={})

    def step(name):
        log['steps'][name] = round(time.time() - t0, 1)
        print('[assemble] %6.1f s  %s' % (time.time() - t0, name))
        sys.stdout.flush()
    test_talal = bool(o.get('test-talal-z1'))
    changed = talal_z1_changed() or test_talal
    log['approved_z1_md5'] = md5_file(D.APPROVED_Z1_BLEND)
    log['approved_z1_md5_expected'] = APPROVED_MD5
    if changed:
        out = (D.TMP_DIR + '/z1_talal_test.blend') if test_talal else Z1_TALAL_BLEND
        log['z1'] = dict(source='talal' if not test_talal else 'talal (test run: md5 unchanged, path exercised)',
                         **normalise_talal_z1(out))
        z1_path = out
        step('zone 1 taken from Talal\'s file')
    else:
        z1_path = D.zone_blend(1)
        log['z1'] = dict(source='generated (Talal\'s file unchanged: md5 %s)' % APPROVED_MD5, blend=z1_path)
    import detail_hash as H
    bpy.ops.wm.open_mainfile(filepath=C.RIG_BLEND)
    arm = bpy.data.objects['Armature']
    zone, colls = {}, {}
    ident = {}
    for z in ZONE_NUMS:
        path = z1_path if z == 1 else D.zone_blend(z)
        c = D.append_zone(z, arm, path=path)
        if c is None:
            raise RuntimeError('zone %d: no Detail_Z%d in %s' % (z, z, path))
        colls[z] = c
    bpy.context.view_layer.update()
    for z in ZONE_NUMS:
        ref = json.load(open(HASH_FILES[z]))['objects'] if os.path.exists(HASH_FILES[z]) else {}
        for ob in sorted(colls[z].all_objects, key=lambda x: x.name):
            if ob.type != 'MESH':
                continue
            zone[ob.name] = 'Z%d' % z
            fp = H.fingerprint(ob)
            if z == 1 and changed:
                ident[ob.name] = 'from Talal\'s file (see z1.diff)'
                continue
            rf = ref.get(ob.name)
            if rf is None:
                ident[ob.name] = 'no reference hash'
                continue
            bad = [f for f in H.GEOM_FIELDS + ('roles_md5', 'bones_md5') if rf.get(f) != fp.get(f)]
            ident[ob.name] = 'identical' if not bad else 'DIFF ' + ','.join(bad)
    log['identity_vs_zone_hash'] = ident
    log['zone_blends'] = {('Z%d' % z): (z1_path if z == 1 else D.zone_blend(z)) for z in ZONE_NUMS}
    step('zones appended')
    import detail_render as R
    turrets = R.add_turrets()
    bpy.context.view_layer.update()
    import detail_ship as S
    import detail_base_edits as BE
    import detail_checks as CK
    import detail_zones as ZN
    ship = S.Ship(bpy)
    be_rep = {}
    deleted = BE.deleted_mask(ship, 'all', be_rep)
    log['base_edits'] = be_rep
    import r3_base_recolor as BR
    rc_rep = {}
    rc_slots = BR.face_slots(ship, 'all', rc_rep, deleted)
    log['base_recolor'] = rc_rep
    dets = [ObData(ob) for ob in sorted(D.detail_objects(), key=lambda x: x.name)]
    props = [ObData(ob) for ob in sorted(bpy.data.objects, key=lambda x: x.name)
             if ob.type == 'MESH' and ob.name.startswith(C.PROP_PREFIX) and ob.parent == arm]
    tur = [ObData(ob) for ob in turrets if ob.type == 'MESH']
    shipd = ObData(ship.ob, poly_mask=~deleted)
    ship_full = ObData(ship.ob)
    step('mesh data (%d detail objects, %d props, %d turret parts)' % (len(dets), len(props), len(tur)))
    # ---- object checklist
    log['objects'] = {d.name: CK.object_report(d.ob, zone[d.name]) for d in dets}
    log['objects_ok'] = all(v['ok'] for v in log['objects'].values())
    log['inside_out_before_fix'] = {k: v['inside_out_pieces'] for k, v in log['objects'].items() if v['inside_out_pieces']}
    step('object reports')
    # ---- triangles
    per_obj, per_zone, per_bone = tri_tables(dets, zone)
    rig_meshes = sorted([o for o in bpy.data.objects if o.type == 'MESH' and o.parent == arm and
                         any(m.type == 'ARMATURE' and m.object == arm for m in o.modifiers)], key=lambda x: x.name)
    base_rig = [o for o in rig_meshes if not o.name.startswith('SM_AirshipDetail_')]
    ship_tris0 = int(len(ship_full.tri))
    ship_tris1 = int(len(shipd.tri))
    prop_tris = int(sum(len(p.tri) for p in props))
    det_tris = int(sum(len(d.tri) for d in dets))
    log['tris'] = dict(per_zone=per_zone, per_object=per_obj, per_bone=per_bone,
                       sm_airship_before=ship_tris0, sm_airship_after_base_edits=ship_tris1,
                       props=prop_tris, props_objects=len(props), details=det_tris, details_objects=len(dets),
                       sk_before=ship_tris0 + prop_tris, sk_after=ship_tris1 + prop_tris + det_tris,
                       turrets_each=int(sum(len(t.tri) for t in tur) // 2), turrets_note='separate static meshes '
                       '(BP_AirshipTurret), not in SK_Airship', rig_meshes_before=len(base_rig),
                       rig_meshes_after=len(rig_meshes), lod=lod_estimate(dets))
    step('triangles')
    # ---- floating pieces, overlaps, keep-clear
    log['floating'] = floating_check(dets, [shipd] + props)
    step('floating')
    log['overlaps'] = overlap_check(dets, zone, props + tur)
    step('overlaps')
    log['keep_clear'] = keep_clear_check(dets)
    # ---- PA walkable and the deck
    zi = ZN.ZoneIndex(ship)
    walk_face = np.array([w in ('deck / walkable', 'walkable top of a part') for w in zi.why])
    obst_mask = ~walk_face & ~deleted
    obst_bvh = BVHTree.FromPolygons(
        np.concatenate([ship.co] + [p.co for p in props]).tolist(),
        [list(ship.polys[i]) for i in np.nonzero(obst_mask)[0]] +
        sum([(p.tri + len(ship.co) + sum(len(q.co) for q in props[:k])).tolist() for k, p in enumerate(props)], []))
    deck_tris = shipd.tri
    deck_bvh = BVHTree.FromPolygons(shipd.co.tolist(), deck_tris.tolist(), all_triangles=True)
    deck_is_walk = walk_face[shipd.tri_poly]
    S_ = json.load(open(STAIRS_JSON))
    stairs_obbs = obb_list_blender(S_)
    log['walkable'] = walkable_check(dets, [(a, b, n) for (a, b), n in
                                            zip(ZN.pa_boxes_blender(PA_JSON),
                                                [b['name'] for b in json.load(open(PA_JSON))['hull_boxes']])],
                                     obst_bvh, deck_bvh, deck_is_walk, stairs_obbs)
    ca = ship.island_verts([i for i, rr in ship.islands.items() if rr['src'] == 'Gantry' and rr['part'] == 'ChainAft'
                            and rr.get('piece') == 'link'])
    ch = [d for d in dets if d.name == 'SM_AirshipDetail_Z7_Chains'][0]
    log['walkable']['chain_aft'] = dict(
        note='ChainAft hangs beside the bow over the main deck forward of the stairs; zone 7 swapped its six bars '
             '(base edit z7_chain_aft_bars) for a link chain on the same line. No PA box, no physics, as before.',
        old_bars_bbox=[[r(v) for v in ca.min(0)], [r(v) for v in ca.max(0)]] if len(ca) else None,
        new_chain_bbox=[[r(v) for v in ch.co.min(0)], [r(v) for v in ch.co.max(0)]])
    step('walkable')
    # ---- silhouette
    log['silhouette'] = silhouette_check(dets, shipd.bvh, sample=int(o.get('sample', 2)))
    allb = [ship_full] + props + tur
    co_b = np.concatenate([x.co for x in allb])
    off, tri_b = 0, []
    for x in allb:
        tri_b.append(x.tri + off); off += len(x.co)
    bvh_b = BVHTree.FromPolygons(co_b.tolist(), np.concatenate(tri_b).tolist(), all_triangles=True)
    alla = [shipd] + props + tur + dets
    co_a = np.concatenate([x.co for x in alla])
    off, tri_a, owner = 0, [], []
    for k, x in enumerate(alla):
        tri_a.append(x.tri + off); off += len(x.co); owner.append(np.full(len(x.tri), k))
    bvh_a = BVHTree.FromPolygons(co_a.tolist(), np.concatenate(tri_a).tolist(), all_triangles=True)
    log['outline'] = outline_check(bvh_b, (bvh_a, np.concatenate(owner)), [x.name for x in alla])
    lo = co_b[np.unique(np.concatenate(tri_b))]
    la = co_a[np.unique(np.concatenate(tri_a))]
    log['bbox'] = dict(before=[[r(v) for v in lo.min(0)], [r(v) for v in lo.max(0)]],
                       after=[[r(v) for v in la.min(0)], [r(v) for v in la.max(0)]],
                       lowest_detail=dict(z=r(min(d.co[:, 2].min() for d in dets)),
                                          object=min(dets, key=lambda d: d.co[:, 2].min()).name))
    step('silhouette + outline')
    # ---- ownership per zone (the shared zone check, every 4th vertex)
    own = {}
    for z in ZONE_NUMS:
        zn = 'Z%d' % z
        co = np.concatenate([d.co for d in dets if zone[d.name] == zn])
        rep = ZN.ownership_report(zi, co, zn, sample=int(o.get('own-sample', 4)))
        own[zn] = {k: rep[k] for k in ('verts_tested', 'outside_zone', 'on_seam_with', 'within_margin_of', 'keep_clear')}
    log['ownership'] = own
    step('ownership')
    # ---- stairs
    st = [d for d in dets if d.name == STAIRS_OBJ][0]
    others = [shipd] + props + tur + [d for d in dets if d is not st]
    co_s = np.concatenate([x.co for x in others + [st]])
    off, tri_s = 0, []
    for x in others + [st]:
        tri_s.append(x.tri + off); off += len(x.co)
    scene_bvh = BVHTree.FromPolygons(co_s.tolist(), np.concatenate(tri_s).tolist(), all_triangles=True)
    sets = {x.name: x.co[np.unique(x.tri)] for x in others if len(x.tri)}
    log['stairs'] = stairs_check(st, scene_bvh, sets, STAIRS_JSON)
    # the stairs collision boxes against the PA boxes (AABB overlap, UE cm)
    pa = json.load(open(PA_JSON))['hull_boxes']
    ov = []
    for b in S_['boxes']:
        for p in pa:
            if all(b['min'][i] < p['max'][i] - 0.5 and p['min'][i] < b['max'][i] - 0.5 for i in range(3)):
                ov.append([b['name'], p['name']])
    log['stairs']['collision_aabb_overlaps_with_pa_boxes'] = ov
    log['stairs']['collision_boxes'] = {k: sum(1 for b in S_['boxes'] if b['kind'] == k) for k in
                                        sorted({b['kind'] for b in S_['boxes']})}
    log['stairs']['rail_pieces_removed'] = S_.get('rail_pieces_removed')
    step('stairs')
    # ---- integration fixes, in the output file only
    for t in turrets:
        bpy.data.objects.remove(t)
    c = bpy.data.collections.get('Preview_Turrets')
    if c:
        bpy.data.collections.remove(c)
    fixes = {}
    if not o.get('no-flip-z1'):
        for d in dets:
            if zone[d.name] == 'Z1' and log['objects'][d.name]['inside_out_pieces']:
                fixes[d.name] = flip_inside_out(d.ob)
        for k in fixes:
            log['objects'][k] = CK.object_report(bpy.data.objects[k], 'Z1')
            log['objects'][k]['fixed_in_full_file'] = 'inside-out pieces flipped (winding + custom normals)'
    log['z1_inside_out_fix'] = fixes
    log['objects_ok_after_fix'] = all(v['ok'] for v in log['objects'].values())
    log['apply_base_edits'] = apply_base_edits(ship.ob, deleted, be_rep)
    h_before_rc = mesh_hash(ship.ob.data)
    log['apply_base_recolor'] = BR.apply_to_object(ship.ob, rc_slots[~deleted], rc_rep)
    log['apply_base_recolor']['geometry_uv_weights_unchanged'] = mesh_hash(ship.ob.data) == h_before_rc
    log['apply_base_recolor']['material_slots'] = [m.name if m else None for m in ship.ob.data.materials]
    log['rig_meshes_in_full_file'] = len(rig_meshes)
    step('fixes + base edits applied')
    log['seconds'] = round(time.time() - t0, 1)
    if not o.get('no-save'):
        bpy.context.scene['round3_assembly'] = json.dumps(dict(zones=log['zone_blends'], z1=log['z1']['source'],
                                                               base_edits=list(be_rep), base_recolor=list(rc_rep),
                                                               when=log['started']))
        log['saved'] = D.safe_save(FULL_BLEND)
        log['saved_md5'] = md5_file(FULL_BLEND)
        step('saved')
    log['protected_end'] = protected_state()
    log['protected_unchanged'] = all(log['protected_start'][k]['md5'] == v['md5'] for k, v in log['protected_end'].items())
    out = o.get('out', REPORT)
    C.dump_json(log, out)
    summary(log)
    print('[assemble] wrote', out, log['seconds'], 's')
    sys.stdout.flush()


def summary(log):
    t = log['tris']
    print('[assemble] z1:', log['z1']['source'])
    print('[assemble] identity vs zone hashes:', {k: v for k, v in log['identity_vs_zone_hash'].items() if v != 'identical'} or 'all identical')
    print('[assemble] tris per zone', {k: v['tris'] for k, v in t['per_zone'].items()}, 'details', t['details'],
          'SK before', t['sk_before'], 'after', t['sk_after'])
    print('[assemble] objects ok', log['objects_ok'], 'after fix', log.get('objects_ok_after_fix'),
          'inside-out before fix', log['inside_out_before_fix'])
    print('[assemble] floating', log['floating']['floating_total'], 'of', log['floating']['pieces'], 'pieces')
    print('[assemble] overlaps cross-zone', log['overlaps']['cross_zone_pairs'], [(x['a'], x['b'], x['tri_pairs']) for x in log['overlaps']['cross_zone']])
    print('[assemble] overlaps same-zone', log['overlaps']['same_zone_pairs'], 'props/turrets', log['overlaps']['with_props_pairs'])
    print('[assemble] keep clear', log['keep_clear']['total'], log['keep_clear']['hits'])
    print('[assemble] walkable free', log['walkable']['free_total'], 'deck free', log['walkable']['deck_free_total'])
    print('[assemble] stairs', json.dumps({k: v for k, v in log['stairs'].items() if k not in ('collision_boxes',)}))
    print('[assemble] outline', json.dumps(log['outline']))
    print('[assemble] base edits', json.dumps({k: v for k, v in log.get('apply_base_edits', {}).items() if k != 'edits'}))
    print('[assemble] base recolour', json.dumps(log.get('apply_base_recolor')))
    print('[assemble] protected unchanged', log.get('protected_unchanged'))


# ================================================================== verify the saved file (opens it read only)
def verify(o):
    """reopen zones/AirshipRig_detail_full.blend: the meshes rig_export.py would pick, the object checklist of every
    detail object, SM_Airship's triangles and the base edits it carries, the fingerprints against the zone hashes"""
    import detail_checks as CK
    import detail_hash as H
    t0 = time.time()
    md5_0 = md5_file(FULL_BLEND)
    bpy.ops.wm.open_mainfile(filepath=FULL_BLEND)
    arm = bpy.data.objects['Armature']
    meshes = sorted([ob for ob in bpy.data.objects if ob.type == 'MESH' and ob.parent == arm and
                     any(m.type == 'ARMATURE' and m.object == arm for m in ob.modifiers)], key=lambda x: x.name)
    det = [ob for ob in meshes if ob.name.startswith('SM_AirshipDetail_')]
    rep = dict(blend=FULL_BLEND, md5=md5_0, rig_meshes=len(meshes), first_mesh=meshes[0].name,
               detail_objects=len(det), props=sum(1 for ob in meshes if ob.name.startswith(C.PROP_PREFIX)),
               sm_airship_tris=sum(len(p.vertices) - 2 for p in bpy.data.objects[C.HULL_OBJ].data.polygons),
               sm_airship_base_edits=json.loads(bpy.data.objects[C.HULL_OBJ].get('round3_base_edits', '{}')),
               sm_airship_base_recolor=None,
               details_tris=sum(sum(len(p.vertices) - 2 for p in ob.data.polygons) for ob in det),
               collections=sorted(c.name for c in bpy.data.collections if c.name.startswith('Detail_')),
               materials=sorted({m.name for ob in det for m in ob.data.materials if m}))
    rep['sk_tris'] = sum(sum(len(p.vertices) - 2 for p in ob.data.polygons) for ob in meshes)
    import r3_base_recolor as BR
    sl, ent = BR.read_from_object(bpy.data.objects[C.HULL_OBJ])
    rep['sm_airship_base_recolor'] = dict(entries=ent, faces_by_slot={str(k): int(sum(1 for x in sl if x == k))
                                                                       for k in sorted({x for x in sl if x})})
    rep['sm_airship_materials'] = [m.name if m else None for m in bpy.data.objects[C.HULL_OBJ].data.materials]
    rep['objects'] = {}
    for ob in det:
        zn = ob.name.split('_')[2]
        rr = CK.object_report(ob, zn)
        rep['objects'][ob.name] = {k: rr[k] for k in ('ok', 'tris', 'inside_out_pieces', 'nonmanifold_edges',
                                                      'not_rigid_vertices', 'faces_without_role', 'bones')}
        rep['objects'][ob.name]['uv_maps'] = [u.name for u in ob.data.uv_layers]
        rep['objects'][ob.name]['materials'] = len(ob.data.materials)
    rep['all_ok'] = all(v['ok'] for v in rep['objects'].values())
    fp = {}
    for z in ZONE_NUMS:
        ref = json.load(open(HASH_FILES[z]))['objects']
        for ob in det:
            if ob.name in ref:
                a, b = H.fingerprint(ob), ref[ob.name]
                fp[ob.name] = [f for f in H.GEOM_FIELDS + ('roles_md5', 'bones_md5') if a[f] != b[f]] or 'identical'
    rep['vs_zone_hashes'] = fp
    rep['md5_after_open'] = md5_file(FULL_BLEND)
    rep['seconds'] = round(time.time() - t0, 1)
    C.dump_json(rep, o.get('out', DOCS + '/full_verify.json'))
    print('[verify]', json.dumps({k: v for k, v in rep.items() if k not in ('objects',)}))


# ================================================================== tool wrappers (zone 1 from the build's source)
def add_deck_ink_mask(scene, erode_px=3):
    """toon renders: Freestyle as its own render pass, composited over the image except on deck pixels. Deck pixels =
    the toon deck material (an AOV 'DeckMask' = 1 on fully covered pixels), eroded by `erode_px`, so the outlines of
    things standing on the deck (crates, rails, the helm, the stairs) keep their full width. Stray hidden-line dashes
    in the middle of the plain deck are dropped. Preview only: no geometry changes."""
    vl = scene.view_layers[0]
    vl.freestyle_settings.as_render_pass = True
    aov = next((a for a in vl.aovs if a.name == 'DeckMask'), None) or vl.aovs.add()
    aov.name, aov.type = 'DeckMask', 'VALUE'
    for k in ('MT_deck', 'MP_deck'):
        m = bpy.data.materials.get(k)
        if m is None or not m.use_nodes:
            continue
        if not any(n.type == 'OUTPUT_AOV' for n in m.node_tree.nodes):
            n = m.node_tree.nodes.new('ShaderNodeOutputAOV')
            n.aov_name = 'DeckMask'
            n.inputs['Value'].default_value = 1.0
    scene.use_nodes = True
    tr = scene.node_tree
    tr.nodes.clear()
    rl = tr.nodes.new('CompositorNodeRLayers')
    gt = tr.nodes.new('CompositorNodeMath'); gt.operation = 'GREATER_THAN'; gt.inputs[1].default_value = 0.98
    er = tr.nodes.new('CompositorNodeDilateErode'); er.mode = 'STEP'; er.distance = -abs(int(erode_px))
    inv = tr.nodes.new('CompositorNodeMath'); inv.operation = 'SUBTRACT'; inv.inputs[0].default_value = 1.0
    ao = tr.nodes.new('CompositorNodeAlphaOver')
    comp = tr.nodes.new('CompositorNodeComposite')
    tr.links.new(rl.outputs['DeckMask'], gt.inputs[0])
    tr.links.new(gt.outputs[0], er.inputs['Mask'])
    tr.links.new(er.outputs['Mask'], inv.inputs[1])
    tr.links.new(inv.outputs[0], ao.inputs[0])
    tr.links.new(rl.outputs['Image'], ao.inputs[1])
    tr.links.new(rl.outputs['Freestyle'], ao.inputs[2])
    tr.links.new(ao.outputs['Image'], comp.inputs['Image'])
    print('[assemble] deck ink mask on (erode %d px)' % erode_px)


def run_tool(tool, rest):
    src = z1_source()
    orig = D.append_zone

    def append_zone(zone, arm=None, path=None):
        if path is None and str(zone).lower().lstrip('z') == '1':
            path = src
        return orig(zone, arm, path)
    D.append_zone = append_zone
    sys.argv = [sys.argv[0], '--'] + rest
    print('[assemble] tool', tool, 'zone 1 from', src)
    if tool == 'rigcheck':
        import detail_rigcheck as RC
        RC.D.append_zone = append_zone
        RC.main()
    elif tool == 'render':
        import detail_render as R
        R.D.append_zone = append_zone
        o_r = R.argv_opts()
        if str(o_r.get('deck-ink', 'mask')) != 'raw':
            # review fix 2026-11-28: Freestyle leaks a few hidden-line dashes from the details under the deck onto the
            # plain deck planks. Draw the ink as its own pass and keep it off deck pixels (not within a few pixels
            # of anything that is not deck, so outlines of things standing on the deck stay whole). --deck-ink raw
            # renders the old way.
            orig_toon = R.apply_toon

            def apply_toon(scene, look='toon'):
                ship = orig_toon(scene, look)
                add_deck_ink_mask(scene, int(o_r.get('deck-ink-erode', 3)))
                return ship
            R.apply_toon = apply_toon
        if os.environ.get('DETAIL_ASSEMBLE_CPU'):
            # Cycles on the CPU (the GPU may be full, e.g. while the Unreal editor runs): same look, slower
            orig_clay = R.apply_clay

            def apply_clay(scene, samples):
                orig_clay(scene, samples)
                scene.cycles.device = 'CPU'
                # no CUDA / OptiX context at all (the OptiX denoiser would still open one on a full GPU)
                try:
                    prefs = bpy.context.preferences.addons['cycles'].preferences
                    prefs.compute_device_type = 'NONE'
                    scene.cycles.denoiser = 'OPENIMAGEDENOISE'
                except Exception as e:
                    print('[assemble] cpu-only setup:', e)
                print('[assemble] clay on the CPU')
                return 'CPU'
            R.apply_clay = apply_clay
        R.main()
    else:
        raise KeyError(tool)
    sys.stdout.flush()


if __name__ == '__main__':
    o, a = opts()
    if o.get('tool'):
        i = a.index('--tool')
        run_tool(a[i + 1], a[:i] + a[i + 2:])
    elif o.get('verify'):
        verify(o)
    else:
        build(o)
    sys.stdout.flush()
    os._exit(0)
