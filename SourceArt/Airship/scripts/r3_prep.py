"""Round 3 export, step 1: the export .blend with atlas UVs, palette UVs, face kinds and LOD variants
(Docs/Airship/round3/EXPORT_R3.md sections 1, 2, 4, 5).

  BL_MEM_MAX=6G blender_capped.sh --python SourceArt/Airship/scripts/r3_prep.py -- [knobs]
  knobs: --tex-h 4096 --tex-m 4096 --pack-px 4 --shape CONCAVE|CONVEX|AABB --min-w 0.025 --cull 0.02
         --cap-deg 30 --cap-deg-tube 30 --z7-scale 1.5 --angle 60 --lod1 0.15 --lod2 0.6 --props-palette on|off
         --density N (exact texels/m instead of filling the page)

Reads (never saves) rig/AirshipRig.blend (SM_Airship's part classes, the base edits' and recolours' face masks) and
rig/detail/zones/AirshipRig_detail_full.blend (checked against full_hash.json and the rig), appends the two turret
meshes from rig/props/AirshipProps.blend (read only). Writes rig/detail/r3export/:
  AirshipR3_export.blend   Armature + SM_Airship (base edits applied) + 30 props + SM_AirshipR3Detail_Moving (22 moving
                           detail objects merged, rigid skin kept) + SM_AirshipR3_HullDetail (12 Hull-bone objects
                           merged) + _LOD1 / _LOD2 of both + SM_AirshipTurret_Base / _Gun (collection R3_Turrets).
                           Every mesh: UV0 'UVMap' (SM_Airship: Talal's; props / turrets: the props atlas; details: the
                           new page atlas), UV1 'R3Palette' (x = palette index 0..23, y = 0, the same on all corners of a
                           face), one material (M_Airship / M_AirshipProps / M_AirshipR3_Detail), face attributes r3_pal
                           (palette index), r3_kind (details: 0 atlas, 1 rivet, 2 hidden, 3 thin, 4 ink side), r3_cap
                           (front contour: -1 off, 0 side, 1 front), r3_src (source object, details).
  manifest.json            palette table, objects (counts, bones, bounds in UE cm, palette use), page densities, LODs
  manifest_arrays.npz      per vertex bone, per face palette index of every export mesh (for verify_fbx / verify_import)
  checks/prep_report.json  face kinds, packing, UV checks (overlap texels between islands, out-of-range / reserved-band
                           loops per source object), texel density per source object, protected md5 at start and end
Faces with no atlas space (rivets, hidden, thin) map to the BLANK block (top right, no ink, no dot), thin sides of
plates to the side block (top left; r3_bake gives it d = 1.5 cm): both 32 texels, above / right of the 40-texel band
the packed islands leave free. Every ink feature edge is also an island border (--seams features). SM_Airship gets
its own ink atlas in UV2 'R3Ink' (--hull-uv atlas; thin = narrower than --min-w-hull 4.5 cm with a feature edge
along it); its UV0 stays Talal's.
"""
import bpy, bmesh, sys, os, json, math, time
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np
from mathutils import Vector as V, Matrix
from mathutils.bvhtree import BVHTree
import r3_common as RC
import r3_sdf as S

A = RC.argv()
TEX = {'H': RC.arg(A, '--tex-h', 4096, int), 'M': RC.arg(A, '--tex-m', 4096, int)}
PACK_PX = RC.arg(A, '--pack-px', 4, float)
SHAPE = RC.arg(A, '--shape', 'CONCAVE')
MIN_W = RC.arg(A, '--min-w', 0.025, float)
CULL_D = RC.arg(A, '--cull', 0.02, float)
CAP_DEG = RC.arg(A, '--cap-deg', 30.0, float)
CAP_DEG_TUBE = RC.arg(A, '--cap-deg-tube', 30.0, float)
Z7_SCALE = RC.arg(A, '--z7-scale', 1.5, float)
ANGLE = RC.arg(A, '--angle', 60.0, float)
LOD1_CUT = RC.arg(A, '--lod1', 0.15, float)
LOD2_CUT = RC.arg(A, '--lod2', 0.6, float)
PROPS_PAL = RC.arg(A, '--props-palette', 'on') != 'off'
DENSITY = RC.arg(A, '--density', 0.0, float)
NO_SAVE = '--no-save' in A
SEAMS = RC.arg(A, '--seams', 'features')               # features: every ink feature edge is an island border too
BOX_DEG = RC.arg(A, '--box-deg', 60.0, float)          # the bake's crease angle on details (r3_bake --box-deg)
HULL_CREASE = RC.arg(A, '--crease-deg', 42.0, float)   # the bake's crease angle on SM_Airship (r3_bake --crease-deg)
HULL_UV = RC.arg(A, '--hull-uv', 'atlas')              # atlas: SM_Airship gets its own ink atlas in UV2 'R3Ink' |
                                                       # talal: the ink texture on Talal's UVs (UV0), as the plan had it
TEX['hull'] = RC.arg(A, '--tex-hull', 4096, int)
MIN_W_HULL = RC.arg(A, '--min-w-hull', 0.045, float)   # SM_Airship: ~1.5 texels at its ~35 texels/m (a strip narrower
                                                       # than that cannot hold a value of its own on the page)
log = RC.Log('r3_prep')
rep = dict(started=time.strftime('%Y-%m-%d %H:%M:%S'), protected_start=RC.protected_state(),
           knobs=dict(tex=TEX, pack_px=PACK_PX, shape=SHAPE, min_w=MIN_W, cull=CULL_D, cap_deg=CAP_DEG,
                      cap_deg_tube=CAP_DEG_TUBE, z7_scale=Z7_SCALE, angle=ANGLE, lod1=LOD1_CUT, lod2=LOD2_CUT,
                      props_palette=PROPS_PAL, density=DENSITY, block=RC.BLOCK, band=RC.BAND, seams=SEAMS,
                      box_deg=BOX_DEG, hull_crease=HULL_CREASE, hull_uv=HULL_UV, min_w_hull=MIN_W_HULL))
os.makedirs(RC.CHECK_DIR, exist_ok=True)

# ------------------------------------------------------------------ 1. SM_Airship classes on the rig (read only)
bpy.ops.wm.open_mainfile(filepath=RC.RIG_BLEND)
import detail_render as R
import detail_base_edits as BE
import r3_base_recolor as BR
ship, keys_after = R.ship_face_classes('all')            # part classes + the registered overrides (keel_block)
be_rep = {}
deleted = BE.deleted_mask(ship, 'all', be_rep)
rme = ship.ob.data
rcen = np.empty(len(rme.polygons) * 3); rme.polygons.foreach_get('center', rcen); rcen = rcen.reshape(-1, 3)
keys_kept = [k for k, d in zip(keys_after, deleted) if not d]
_rt = RC.tri_arrays(rme)
_rco = RC.mesh_np(rme)['co']
DELETED_TRIS = _rco[_rt[1][deleted[_rt[2]]]]                     # (N, 3, 3) world triangles the base edits removed
_edit_of_face = np.full(len(rme.polygons), -1)
for _k, (_f, _e) in enumerate(BE.load_entries('all')):
    _edit_of_face[BE.edit_mask(ship, _e)] = _k
DELETED_EDIT = _edit_of_face[_rt[2][deleted[_rt[2]]]]
DELETED_IDS = [e['id'] for _, e in BE.load_entries('all')]
cen_kept = rcen[~deleted]
rep['sm_airship_rig'] = dict(faces=len(rme.polygons), deleted=int(deleted.sum()), kept=len(keys_kept), base_edits=be_rep,
                             classes={k: keys_kept.count(k) for k in sorted(set(keys_kept))})
log('rig SM_Airship: %d faces, %d deleted by the base edits, classes %s' % (len(rme.polygons), deleted.sum(),
                                                                           rep['sm_airship_rig']['classes']))

# ------------------------------------------------------------------ 2. the full file, checked
FULL_MD5 = RC.md5_file(RC.FULL_BLEND)
bpy.ops.wm.open_mainfile(filepath=RC.FULL_BLEND)
import detail_hash as DH
sc = bpy.context.scene
arm = bpy.data.objects['Armature']
for pb in arm.pose.bones:
    pb.matrix_basis = Matrix.Identity(4)
bpy.context.view_layer.update()
fh = RC.load_json(RC.FULL_HASH)['objects']
dets = sorted([o for o in bpy.data.objects if o.type == 'MESH' and o.name.startswith('SM_AirshipDetail_')],
              key=lambda o: o.name)
assert len(dets) == 34, len(dets)
hash_diff = []
for o in dets:
    fp = DH.fingerprint(o)
    for k in ('verts', 'faces', 'tris', 'co_0p1mm_md5', 'faces_md5', 'roles_md5', 'bones_md5'):
        if fh[o.name][k] != fp[k]:
            hash_diff.append((o.name, k))
assert not hash_diff, hash_diff
sob = bpy.data.objects[RC.HULL_OBJ]
sme = sob.data
assert np.allclose(np.array(sob.matrix_world), np.eye(4))
assert len(sme.polygons) == len(keys_kept), (len(sme.polygons), len(keys_kept))
fcen = np.empty(len(sme.polygons) * 3); sme.polygons.foreach_get('center', fcen); fcen = fcen.reshape(-1, 3)
cen_err = float(np.abs(fcen - cen_kept).max())
assert cen_err < 1e-5, cen_err
full_slots, full_entries = BR.read_from_object(sob)
kb_rig = np.array([k == 'keel_block' for k in keys_kept])
kb_full = np.array([s == 'keel_block' for s in full_slots])
assert (kb_rig == kb_full).all() and kb_rig.sum() == 8381, (kb_rig.sum(), kb_full.sum())
rep['input'] = dict(full_blend=RC.FULL_BLEND, full_md5=FULL_MD5, fingerprint='34 objects identical to full_hash.json',
                    sm_airship_faces=len(sme.polygons), sm_airship_face_centres_vs_rig_max_err=cen_err,
                    keel_block_faces=int(kb_full.sum()), recolor_entries=full_entries)
log('full file ok: md5 %s, 34 detail objects = full_hash.json, SM_Airship = rig minus base edits (%.1e m), '
    'keel block %d faces' % (FULL_MD5, cen_err, kb_full.sum()))
for o in dets + [sob]:
    assert np.allclose(np.array(o.matrix_world), np.eye(4)), o.name

# ------------------------------------------------------------------ 3. SM_Airship: palette + contour flags
hp = np.array([RC.SLOT[k] for k in keys_kept], np.int32)
RC.face_attr_set(sme, 'r3_pal', hp)
H_ = RC.mesh_np(sme)
hpiece = S.pieces(len(H_['co']), H_['ls'], H_['lt'], H_['lv'])
ua_, inv_ = np.unique(hpiece, return_inverse=True)
parea = np.zeros(len(ua_)); np.add.at(parea, inv_, H_['fa'])
skin = ua_[np.argmax(parea)]
hcap, _ = S.cap_faces(hpiece, H_['fn'], H_['fa'], np.ones(len(hpiece)), lambda f: np.array((0.0, 0.0, 1.0)),
                      cap_deg=CAP_DEG, cap_deg_weak=CAP_DEG_TUBE)
hcap = np.where(hpiece == skin, -1, hcap)
RC.face_attr_set(sme, 'r3_cap', hcap)
rep['sm_airship'] = dict(pieces=int(len(ua_)), skin_area_m2=round(float(parea.max()), 1),
                         palette={RC.PALETTE_SLOTS[i][0]: int((hp == i).sum()) for i in np.unique(hp)})


def add_palette_uv(me, pal):
    """UV1 'R3Palette': x = palette index (the same on all corners of the face), y = 0"""
    assert me.uv_layers[0].name == RC.UV_INK, [u.name for u in me.uv_layers]
    while len(me.uv_layers) > 1:
        me.uv_layers.remove(me.uv_layers[-1])
    me.uv_layers.new(name=RC.UV_PAL, do_init=False)
    lt = np.empty(len(me.polygons), np.int64); me.polygons.foreach_get('loop_total', lt)
    uv = np.zeros((len(me.loops), 2)); uv[:, 0] = np.repeat(np.asarray(pal, np.float64), lt)
    RC.uv_set(me, RC.UV_PAL, uv)
    me.uv_layers.active = me.uv_layers[RC.UV_INK]
    me.uv_layers[RC.UV_INK].active_render = True


add_palette_uv(sme, hp)

# ------------------------------------------------------------------ 4. props + turrets: palette by object
props = sorted([o for o in bpy.data.objects if o.type == 'MESH' and o.name.startswith(RC.PROP_PREFIX)],
               key=lambda o: o.name)
assert len(props) == 30, len(props)
with bpy.data.libraries.load(RC.PROPS_BLEND, link=False) as (src, dst):
    dst.objects = list(RC.TURRETS)
tcoll = bpy.data.collections.new('R3_Turrets')
sc.collection.children.link(tcoll)
mat_props = bpy.data.materials[RC.MAT_PROPS]
turrets = []
for o in dst.objects:
    base_name = o.name.split('.')[0]
    o.name = RC.TURRETS[base_name]
    o.data.name = o.name
    tcoll.objects.link(o)
    assert [u.name for u in o.data.uv_layers] == [RC.UV_INK], [u.name for u in o.data.uv_layers]
    assert [m.name.split('.')[0] for m in o.data.materials] == [RC.MAT_PROPS]
    o.data.materials[0] = mat_props
    turrets.append(o)
for m in list(bpy.data.materials):
    if m.name.startswith(RC.MAT_PROPS + '.') and m.users == 0:
        bpy.data.materials.remove(m)
prop_rep = {}
for o in props + turrets:
    k = RC.prop_key(o.name)
    pal = np.full(len(o.data.polygons), RC.SLOT[RC.PROP_KEY_TO_SLOT[k]], np.int32)
    RC.face_attr_set(o.data, 'r3_pal', pal)
    RC.face_attr_set(o.data, 'r3_cap', np.full(len(pal), -1))
    add_palette_uv(o.data, pal)
    prop_rep[o.name] = dict(key=k, slot=RC.PROP_KEY_TO_SLOT[k], faces=len(pal))
# the four cannons share one set of atlas UVs (the props page bakes one of each part)
uv_same = {}
for part in ('Barrel', 'Carriage', 'Quoin', 'Wheel_BL', 'Wheel_BR', 'Wheel_FL', 'Wheel_FR'):
    ref = RC.uv_get(bpy.data.objects['SM_AirshipProp_Cannon_L1_' + part].data, RC.UV_INK)
    for c in ('L2', 'R1', 'R2'):
        u = RC.uv_get(bpy.data.objects['SM_AirshipProp_Cannon_%s_%s' % (c, part)].data, RC.UV_INK)
        uv_same['%s_%s' % (c, part)] = bool(u.shape == ref.shape and np.abs(u - ref).max() < 1e-7)
rep['props'] = dict(palette_on=PROPS_PAL, objects=prop_rep, cannon_uvs_same_as_L1=uv_same)
log('props + turrets: palette slots set (%d objects); cannon UVs = L1: %s' % (len(prop_rep), all(uv_same.values())))

# ------------------------------------------------------------------ 5. merge the detail objects
src_names = [o.name for o in dets]
GROUPS = {}
for i, o in enumerate(dets):
    RC.face_attr_set(o.data, 'r3_src', np.full(len(o.data.polygons), i))
    vg = sorted({g.name for g in o.vertex_groups})
    GROUPS.setdefault('H' if vg == ['Hull'] else 'M', []).append(o)
assert len(GROUPS['H']) == 12 and len(GROUPS['M']) == 22, {k: len(v) for k, v in GROUPS.items()}
DM = [m.name for m in dets[0].data.materials]
for o in dets:
    assert [m.name for m in o.data.materials] == DM, o.name
for c in bpy.data.collections:
    if c.name.startswith('Detail_'):
        c.hide_viewport = False
_stack = [bpy.context.view_layer.layer_collection]
while _stack:
    _l = _stack.pop()
    if _l.collection.name.startswith('Detail_') or _l.collection.name in ('SK_Airship', 'Airship_Export'):
        _l.exclude = False; _l.hide_viewport = False
    _stack += list(_l.children)


def join(objs, name):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.hide_set(False); o.hide_viewport = False; o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    o = bpy.context.view_layer.objects.active
    o.name = name; o.data.name = name
    assert [m.name for m in o.data.materials] == DM, [m.name for m in o.data.materials]
    return o


tris_before = {g: sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in v) for g, v in GROUPS.items()}
OBJ = {'H': join(GROUPS['H'], RC.HULLDET), 'M': join(GROUPS['M'], RC.MOVING)}
dcoll = bpy.data.collections.new('R3_Details')
sc.collection.children.link(dcoll)
for o in OBJ.values():
    for c in list(o.users_collection):
        c.objects.unlink(o)
    dcoll.objects.link(o)
    assert np.allclose(np.array(o.matrix_world), np.eye(4))
for g, o in OBJ.items():
    t = sum(len(p.vertices) - 2 for p in o.data.polygons)
    assert t == tris_before[g], (g, t, tris_before[g])
log('merged: %s %d tris, %s %d tris' % (RC.HULLDET, tris_before['H'], RC.MOVING, tris_before['M']))

# ------------------------------------------------------------------ 6. face kinds
D_ = {g: RC.mesh_np(o.data) for g, o in OBJ.items()}
mark = {}
for g, o in OBJ.items():
    m = np.zeros(len(o.data.polygons), bool); o.data.polygons.foreach_get('use_freestyle_mark', m)
    mark[g] = m
# everything that can hide a face: SM_Airship + the non-rivet faces of both detail meshes (BVHs from loop triangles:
# polygon input runs Blender's polyfill, which crashed on some of the merged n-gons)
_, htv, htp = RC.tri_arrays(sme)
allco, alltri, off = [H_['co']], [htv], len(H_['co'])
for g in ('H', 'M'):
    _, tv_, tp_ = RC.tri_arrays(OBJ[g].data)
    allco.append(D_[g]['co'])
    alltri.append(tv_[~mark[g][tp_]] + off)
    off += len(D_[g]['co'])
cbvh = BVHTree.FromPolygons(np.vstack(allco).tolist(), np.vstack(alltri).tolist(), all_triangles=True)
hbvh = BVHTree.FromPolygons(H_['co'].tolist(), htv.tolist(), all_triangles=True)
del alltri
KIND, CAP = {}, {}
for g, o in OBJ.items():
    d = D_[g]
    nP = len(d['ls'])
    nxt = np.arange(len(d['lv'])) + 1
    nxt[d['ls'] + d['lt'] - 1] = d['ls']
    elen = np.linalg.norm(d['co'][d['lv']] - d['co'][d['lv'][nxt]], axis=1)
    width = d['fa'] / np.maximum(np.maximum.reduceat(elen, d['ls']), 1e-9)
    thin = width < MIN_W
    hidden = np.zeros(nP, bool)
    t = time.time()
    for q in np.nonzero(~mark[g] & ~thin)[0].tolist():
        pc, pn = d['fc'][q], d['fn'][q]
        if cbvh.ray_cast(V(pc + pn * 0.002), V(pn), CULL_D)[0] is not None:
            hidden[q] = True
            continue
        hp_, hn_, _, _ = hbvh.find_nearest(V(pc), 0.25)
        if hp_ is not None and np.dot(pn, hn_) < -0.5 and np.dot(pc - np.array(hp_), hn_) < 0.005:
            hidden[q] = True
    log('%s: hidden-face test %.1fs' % (g, time.time() - t))
    blank = mark[g] | thin | hidden

    def hull_out(fi, d=d):
        hit = hbvh.find_nearest(V(d['fc'][fi]))
        return np.array(hit[1]) if hit[0] is not None else np.array((0.0, 0.0, 1.0))
    piece = S.pieces(len(d['co']), d['ls'], d['lt'], d['lv'])
    cap, n_weak = S.cap_faces(piece, d['fn'], d['fa'], (~blank).astype(np.float64), hull_out, cap_deg=CAP_DEG,
                              cap_deg_weak=CAP_DEG_TUBE)
    pairs = S.edge_pairs(d['ls'], d['lt'], d['lv'])
    inks = S.grow(~blank & (cap == 1), blank & ~mark[g] & ~hidden & (cap == 0), pairs, 2)
    kind = np.full(nP, RC.K_ATLAS, np.int32)
    kind[thin] = RC.K_THIN
    kind[hidden] = RC.K_HIDDEN
    kind[inks] = RC.K_INKSIDE
    kind[mark[g]] = RC.K_RIVET
    KIND[g], CAP[g] = kind, cap
    src = RC.face_attr_get(o.data, 'r3_src')
    RC.face_attr_set(o.data, 'r3_kind', kind)
    RC.face_attr_set(o.data, 'r3_cap', np.where(kind == RC.K_RIVET, -1, cap))
    RC.face_attr_set(o.data, 'r3_pal', d['mi'])
    rep.setdefault('faces', {})[g] = dict(
        total=int(nP), pieces=int(len(np.unique(piece))), front_from_hull_normal=n_weak,
        **{KIND_N: int((kind == k).sum()) for k, KIND_N in RC.KIND_NAMES.items()},
        **{'area_' + KIND_N: round(float(d['fa'][kind == k].sum()), 2) for k, KIND_N in RC.KIND_NAMES.items()},
        by_source={src_names[s]: {RC.KIND_NAMES[k]: int(((src == s) & (kind == k)).sum()) for k in RC.KIND_NAMES}
                   for s in np.unique(src)})
    log('%s kinds: %s' % (g, {n: int((kind == k).sum()) for k, n in RC.KIND_NAMES.items()}))

# SM_Airship's own ink atlas (UV2): Talal's UVs give 2.6 cm texels and put his 2 cm bevel strips between texel
# centres (dashed crate edges at deck range); his UV0 stays for his comic mask and the fallback material
PAL_OF = {'H': D_['H']['mi'], 'M': D_['M']['mi'], 'hull': hp}
CREASE_OF = {'H': BOX_DEG, 'M': BOX_DEG, 'hull': HULL_CREASE}
PAGES_UV = {'H': OBJ['H'], 'M': OBJ['M']}
if HULL_UV == 'atlas':
    d = H_
    nxt = np.arange(len(d['lv'])) + 1
    nxt[d['ls'] + d['lt'] - 1] = d['ls']
    elen = np.linalg.norm(d['co'][d['lv']] - d['co'][d['lv'][nxt]], axis=1)
    width = d['fa'] / np.maximum(np.maximum.reduceat(elen, d['ls']), 1e-9)
    # thin = narrow AND one of its long edges is a feature edge (bevel strips between two creases). Narrow faces whose
    # long edges are smooth (the copper pipes' facets, 8.9k faces) keep atlas space: their ring lines need it
    _, hsv, _ = S.feature_segments(d['co'], d['ls'], d['lt'], d['lv'], None, d['fn'], hp.astype(np.int64),
                                   crease_deg=HULL_CREASE, cap=hcap.astype(np.int64))
    nv_ = len(d['co']) + 1
    fk_ = np.unique(np.minimum(hsv[:, 0], hsv[:, 1]) * nv_ + np.maximum(hsv[:, 0], hsv[:, 1]))
    lk_ = np.minimum(d['lv'], d['lv'][nxt]) * nv_ + np.maximum(d['lv'], d['lv'][nxt])
    jf = np.clip(np.searchsorted(fk_, lk_), 0, len(fk_) - 1)
    feat_len = np.where(fk_[jf] == lk_, elen, 0.0)
    long_feat = np.maximum.reduceat(feat_len, d['ls']) > 2.0 * width
    narrow = width < MIN_W_HULL
    thin = narrow & long_feat
    pairs = S.edge_pairs(d['ls'], d['lt'], d['lv'])
    inks = S.grow(~thin & (hcap == 1), thin & (hcap == 0), pairs, 2)
    kind = np.full(len(d['ls']), RC.K_ATLAS, np.int32)
    kind[thin] = RC.K_THIN
    kind[inks] = RC.K_INKSIDE
    KIND['hull'], CAP['hull'], D_['hull'] = kind, hcap, H_
    RC.face_attr_set(sme, 'r3_kind', kind)
    PAGES_UV['hull'] = sob
    rep['faces']['hull'] = dict(total=int(len(kind)), **{n: int((kind == k).sum()) for k, n in RC.KIND_NAMES.items()},
                                **{'area_' + n: round(float(d['fa'][kind == k].sum()), 2) for k, n in RC.KIND_NAMES.items()},
                                thin_by_class={RC.PALETTE_SLOTS[i][0]: int((thin & (hp == i)).sum()) for i in np.unique(hp[thin])},
                                narrow_kept_in_atlas_by_class={RC.PALETTE_SLOTS[i][0]: int((narrow & ~thin & (hp == i)).sum())
                                                               for i in np.unique(hp[narrow & ~thin])})
    log('hull kinds: %s' % {n: int((kind == k).sum()) for k, n in RC.KIND_NAMES.items()})

# ------------------------------------------------------------------ 7. atlas UVs per page
sc.tool_settings.mesh_select_mode = (False, False, True)
PACK = {}
for g, o in PAGES_UV.items():
    me = o.data
    d = D_[g]
    tex = TEX[g]
    kind = KIND[g]
    atlas = kind == RC.K_ATLAS
    src = RC.face_attr_get(me, 'r3_src')
    z7 = np.array(['_Z7_' in src_names[s] for s in src]) if src is not None else np.zeros(len(kind), bool)
    UVX = RC.UV_HULL_INK if g == 'hull' else RC.UV_INK
    if g == 'hull':
        assert [u.name for u in me.uv_layers] == [RC.UV_INK, RC.UV_PAL]
        me.uv_layers.new(name=UVX, do_init=False)
    else:
        for u in list(me.uv_layers):
            me.uv_layers.remove(u)
        me.uv_layers.new(name=UVX, do_init=False)
    RC.uv_set(me, UVX, np.zeros((len(me.loops), 2)))
    me.uv_layers.active = me.uv_layers[UVX]
    for ob_ in bpy.context.view_layer.objects:
        ob_.select_set(ob_ is o)
    bpy.context.view_layer.objects.active = o
    me.polygons.foreach_set('select', atlas)
    vsel = np.zeros(len(me.vertices), bool); vsel[d['lv'][atlas[d['lp']]]] = True
    me.vertices.foreach_set('select', vsel)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.hide(unselected=True)
    t = time.time()
    bpy.ops.uv.smart_project(angle_limit=math.radians(ANGLE), island_margin=0.0, area_weight=0.0, correct_aspect=True,
                             scale_to_bounds=False)
    n_feat_cut = 0
    if SEAMS == 'features':
        # every edge the bake draws a line on becomes an island border as well (r3_bake's signed margins then keep
        # those lines crisp at any width; a line inside an island can only be as thin as about a texel): seams =
        # smart-project island borders + feature edges, then an angle-based unwrap of the atlas faces
        bpy.ops.object.mode_set(mode='OBJECT')
        uvs = RC.uv_get(me, UVX)
        _, fsv, _ = S.feature_segments(d['co'], d['ls'], d['lt'], d['lv'], None, d['fn'], PAL_OF[g].astype(np.int64),
                                       crease_deg=CREASE_OF[g], cap=CAP[g].astype(np.int64), faces_ok=kind != RC.K_RIVET)
        nv = len(d['co']) + 1
        ev = np.empty(len(me.edges) * 2, np.int64); me.edges.foreach_get('vertices', ev); ev = ev.reshape(-1, 2)
        ekey = np.minimum(ev[:, 0], ev[:, 1]) * nv + np.maximum(ev[:, 0], ev[:, 1])
        fk = np.minimum(fsv[:, 0], fsv[:, 1]) * nv + np.maximum(fsv[:, 0], fsv[:, 1])
        seam = np.isin(ekey, fk)
        n_feat = int(seam.sum())
        # smart-project borders: edges whose two atlas faces disagree on the UVs (or that border a non-atlas face)
        nxt = np.arange(len(d['lv'])) + 1
        nxt[d['ls'] + d['lt'] - 1] = d['ls']
        lk = np.minimum(d['lv'], d['lv'][nxt]) * nv + np.maximum(d['lv'], d['lv'][nxt])
        la = atlas[d['lp']]
        o = np.argsort(lk, kind='stable'); ks = lk[o]
        st = np.nonzero(np.r_[True, ks[1:] != ks[:-1]])[0]
        cnt = np.diff(np.r_[st, len(ks)])
        two = st[cnt == 2]
        i_, j_ = o[two], o[two + 1]
        same_dir = d['lv'][i_] == d['lv'][j_]
        uj0 = np.where(same_dir[:, None], uvs[j_], uvs[nxt[j_]]); uj1 = np.where(same_dir[:, None], uvs[nxt[j_]], uvs[j_])
        cutb = (np.abs(uvs[i_] - uj0).max(1) > 1e-6) | (np.abs(uvs[nxt[i_]] - uj1).max(1) > 1e-6) | (la[i_] != la[j_])
        seam |= np.isin(ekey, lk[i_[cutb]])
        n_feat_cut = int((np.isin(ekey, fk) & ~np.isin(ekey, lk[i_[cutb]])).sum())
        me.edges.foreach_set('use_seam', seam)
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.uv.select_all(action='SELECT')
        bpy.ops.uv.unwrap(method='ANGLE_BASED', fill_holes=False, correct_aspect=True, margin=0.0)
        log('%s: seams = %d feature edges (%d of them inside smart-project islands) + island borders' % (g, n_feat, n_feat_cut))
    bpy.ops.uv.select_all(action='SELECT')
    bpy.ops.uv.average_islands_scale()
    bpy.ops.object.mode_set(mode='OBJECT')
    t_sp = time.time() - t
    uv = RC.uv_get(me, UVX)
    lp = d['lp']
    tl, tv, tp = RC.tri_arrays(me)
    dens, a3 = RC.texel_density(uv, d['co'], tl, tv, atlas[tp], 1.0)
    d0 = float(np.median(dens))
    uv[atlas[lp]] /= d0                       # 1 UV unit = 1 m
    uv[(atlas & z7)[lp]] *= Z7_SCALE          # stairs, rails, gantry: the deck view (EXPORT_R3 section 2.3)
    if DENSITY > 0:
        uv[atlas[lp]] *= DENSITY / tex
    RC.uv_set(me, UVX, uv)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.uv.select_all(action='SELECT')
    t = time.time()
    usable = (tex - RC.BAND) / tex
    bpy.ops.uv.pack_islands(rotate=True, scale=DENSITY <= 0, margin_method='FRACTION',
                            margin=PACK_PX / (tex - RC.BAND), shape_method=SHAPE)
    t_pack = time.time() - t
    bpy.ops.mesh.reveal(select=False)
    bpy.ops.object.mode_set(mode='OBJECT')
    uv = RC.uv_get(me, UVX)
    ua = uv[atlas[lp]]
    if DENSITY <= 0:
        uv[atlas[lp]] *= usable               # free the band along the top and the right edge
    ua = uv[atlas[lp]]
    blank_c = (1.0 - RC.BLOCK * 0.5 / tex, 1.0 - RC.BLOCK * 0.5 / tex)
    ink_c = (RC.BLOCK * 0.5 / tex, 1.0 - RC.BLOCK * 0.5 / tex)
    uv[np.isin(kind, (RC.K_RIVET, RC.K_HIDDEN, RC.K_THIN))[lp]] = blank_c
    uv[(kind == RC.K_INKSIDE)[lp]] = ink_c
    RC.uv_set(me, UVX, uv)
    dens, a3 = RC.texel_density(uv, d['co'], tl, tv, atlas[tp], tex)
    dz7, az7 = RC.texel_density(uv, d['co'], tl, tv, (atlas & z7)[tp], tex)
    dno, ano = RC.texel_density(uv, d['co'], tl, tv, (atlas & ~z7)[tp], tex)
    used = float(np.sum(0.5 * np.abs(np.cross(uv[tl[:, 1]] - uv[tl[:, 0]], uv[tl[:, 2]] - uv[tl[:, 0]]))[atlas[tp]]))
    PACK[g] = dict(tex=tex, shape=SHAPE, margin_px=PACK_PX, unwrap_s=round(t_sp, 1), pack_s=round(t_pack, 1),
                   seams=SEAMS, feature_edges_cut_inside_smart_islands=n_feat_cut,
                   density_all=RC.weighted_pct(dens, a3), density_z7=RC.weighted_pct(dz7, az7),
                   density_other=RC.weighted_pct(dno, ano), uv_area_used=round(used, 4),
                   packing_efficiency=round(used / usable ** 2, 3), extent=np.round(ua.max(0), 4).tolist(),
                   area_atlas_m2=round(float(a3.sum()), 1))
    log('%s packed: %s' % (g, PACK[g]))
    if g == 'hull':
        me.uv_layers.active = me.uv_layers[RC.UV_INK]
        me.uv_layers[RC.UV_INK].active_render = True
        continue
    add_palette_uv(me, d['mi'])
    me.materials.clear()
    dm = bpy.data.materials.get(RC.MAT_DETAIL) or bpy.data.materials.new(RC.MAT_DETAIL)
    me.materials.append(dm)
    me.polygons.foreach_set('material_index', np.zeros(len(me.polygons), np.int32))
    me.update()
rep['pack'] = PACK


# ------------------------------------------------------------------ 8. LOD variants
def lod_copy(o, cut, suffix):
    me = o.data
    d = RC.mesh_np(me)
    kind = RC.face_attr_get(me, 'r3_kind')
    piece = S.pieces(len(d['co']), d['ls'], d['lt'], d['lv'])
    vpiece = np.zeros(len(d['co']), np.int64); vpiece[d['lv']] = piece[d['lp']]
    _, inv = np.unique(vpiece, return_inverse=True)
    lo = np.full((inv.max() + 1, 3), np.inf); hi = np.full((inv.max() + 1, 3), -np.inf)
    np.minimum.at(lo, inv, d['co']); np.maximum.at(hi, inv, d['co'])
    diag = np.linalg.norm(hi - lo, axis=1)
    fdiag = diag[inv[d['lv'][d['ls']]]]
    kill = (kind == RC.K_RIVET) | (fdiag < cut)
    n = o.copy()
    n.data = me.copy()
    n.name = o.name + suffix; n.data.name = n.name
    for c in o.users_collection:
        c.objects.link(n)
    bm = bmesh.new(); bm.from_mesh(n.data)
    bm.faces.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[bm.faces[i] for i in np.nonzero(kill)[0].tolist()], context='FACES_ONLY')
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
    bmesh.ops.delete(bm, geom=[e for e in bm.edges if not e.link_faces], context='EDGES')
    bm.to_mesh(n.data); bm.free()
    tri = lambda m: int(sum(len(p.vertices) - 2 for p in m.polygons))
    return n, dict(tris=tri(n.data), faces=len(n.data.polygons), rivet_tris_dropped=int(np.sum((d['lt'] - 2)[kind == RC.K_RIVET])),
                   small_tris_dropped=int(np.sum((d['lt'] - 2)[(kind != RC.K_RIVET) & (fdiag < cut)])), cut_m=cut)


LODS = {}
for g, o in OBJ.items():
    LODS[g] = {'0': dict(tris=int(sum(len(p.vertices) - 2 for p in o.data.polygons)))}
    for lvl, cut in (('1', LOD1_CUT), ('2', LOD2_CUT)):
        n, r = lod_copy(o, cut, '_LOD' + lvl)
        LODS[g][lvl] = r
sk_base = sum(len(p.vertices) - 2 for o in [sob] + props for p in o.data.polygons)
rep['lods'] = dict(details=LODS, sk_base_tris=int(sk_base),
                   sk_tris={lvl: int(sk_base + LODS['M'][lvl]['tris']) for lvl in ('0', '1', '2')},
                   hull_detail_tris={lvl: LODS['H'][lvl]['tris'] for lvl in ('0', '1', '2')})
log('LODs: SK %s, HullDetail %s' % (rep['lods']['sk_tris'], rep['lods']['hull_detail_tris']))

# ------------------------------------------------------------------ 9. UV checks (overlaps, range, density)
UVC = {}


def check_page(name, objs, res, atlas_only, band, uvname=RC.UV_INK):
    """overlap texels between UV islands (rasterised at res), loops out of 0..1 / in the reserved band, per source"""
    tris_uv, tris_isl, tris_src, isl_off = [], [], [], 0
    out_rng, in_band, per_src_loops = {}, {}, {}
    for o in objs:
        me = o.data
        d = RC.mesh_np(me)
        uv = RC.uv_get(me, uvname)
        kind = RC.face_attr_get(me, 'r3_kind')
        src = RC.face_attr_get(me, 'r3_src')
        use = (kind == RC.K_ATLAS) if (atlas_only and kind is not None) else np.ones(len(d['ls']), bool)
        isl = RC.uv_islands(d['ls'], d['lt'], d['lv'], uv, use)
        tl, tv, tp = RC.tri_arrays(me)
        k = use[tp]
        tris_uv.append(uv[tl[k]]); tris_isl.append(isl[tp[k]] + isl_off); isl_off += len(d['ls'])
        sname = (lambda f: src_names[src[f]]) if src is not None else (lambda f, n=o.name: n)
        tris_src.append(np.array([sname(f) for f in tp[k]], object) if src is not None else np.full(int(k.sum()), o.name, object))
        lp = d['lp']
        bad = ((uv < 0) | (uv > 1)).any(1) & use[lp]
        if band:
            inb = ((uv[:, 0] > 1 - band / res) | (uv[:, 1] > 1 - band / res)) & use[lp]
        else:
            inb = np.zeros(len(lp), bool)
        srcs = np.array([sname(f) for f in lp]) if src is not None else np.full(len(lp), o.name)
        for s in np.unique(srcs):
            m = srcs == s
            out_rng[s] = out_rng.get(s, 0) + int((bad & m).sum())
            in_band[s] = in_band.get(s, 0) + int((inb & m).sum())
            per_src_loops[s] = per_src_loops.get(s, 0) + int((m & use[lp]).sum())
    T = np.concatenate(tris_uv); I = np.concatenate(tris_isl); Sx = np.concatenate(tris_src)
    t = time.time()
    lo, hi, cnt = RC.raster_owner(T, I, res)
    ov = (hi >= 0) & (lo != hi)
    # which sources own the overlapping texels: re-raster only the triangles touching them
    per_src_ov = {}
    if ov.any():
        ovi = np.unique(np.concatenate([lo[ov], hi[ov]]))
        sel = np.isin(I, ovi)
        for s in np.unique(Sx[sel]):
            per_src_ov[s] = int(np.isin(I[sel & (Sx == s)], ovi).sum())
    r = dict(res=res, triangles=int(len(T)), covered_texels=int((hi >= 0).sum()), coverage=round(float((hi >= 0).mean()), 4),
             overlap_texels=int(ov.sum()), overlap_triangles_by_source=per_src_ov,
             loops_out_of_range=out_rng, loops_in_reserved_band=in_band, atlas_loops=per_src_loops,
             raster_s=round(time.time() - t, 1))
    log('uv check %s: %s' % (name, {k: v for k, v in r.items() if not isinstance(v, dict)}))
    return r, (hi >= 0)


if HULL_UV == 'atlas':
    UVC['hull'], _ = check_page('hull', [sob], TEX['hull'], True, RC.BAND, RC.UV_HULL_INK)
    UVC['hull_talal_uv0'], _ = check_page('hull_talal_uv0', [sob], 4096, False, 0)
else:
    UVC['hull'], _ = check_page('hull', [sob], 4096, False, 0)
UVC['H'], _ = check_page('H', [OBJ['H']], TEX['H'], True, RC.BAND)
UVC['M'], _ = check_page('M', [OBJ['M']], TEX['M'], True, RC.BAND)
pset = [bpy.data.objects['SM_AirshipProp_Cannon_L1_' + p] for p in
        ('Barrel', 'Carriage', 'Quoin', 'Wheel_BL', 'Wheel_BR', 'Wheel_FL', 'Wheel_FR')] + \
       [bpy.data.objects['SM_AirshipProp_Helm_Pedestal'], bpy.data.objects['SM_AirshipProp_Helm_Wheel']] + turrets
UVC['P'], _ = check_page('P', pset, 2048, False, 0)
rep['uv_checks'] = UVC


# texel density per source object (details) and per page
def dens_by_source(o, res):
    me = o.data
    d = RC.mesh_np(me)
    uv = RC.uv_get(me, RC.UV_INK)
    kind = RC.face_attr_get(me, 'r3_kind')
    src = RC.face_attr_get(me, 'r3_src')
    tl, tv, tp = RC.tri_arrays(me)
    out = {}
    for s in np.unique(src):
        dd, aa = RC.texel_density(uv, d['co'], tl, tv, ((kind == RC.K_ATLAS) & (src == s))[tp], res)
        out[src_names[s]] = dict(area_m2=round(float(aa.sum()), 2), **RC.weighted_pct(dd, aa))
    return out


rep['density_by_source'] = {g: dens_by_source(OBJ[g], TEX[g]) for g in ('H', 'M')}
_htl, _htv, _htp = RC.tri_arrays(sme)
if HULL_UV == 'atlas':
    dd, aa = RC.texel_density(RC.uv_get(sme, RC.UV_HULL_INK), H_['co'], _htl, _htv, (KIND['hull'] == RC.K_ATLAS)[_htp], TEX['hull'])
else:
    dd, aa = RC.texel_density(RC.uv_get(sme, RC.UV_INK), H_['co'], _htl, _htv, np.ones(len(_htp), bool), 4096)
rep['density_hull'] = dict(area_m2=round(float(aa.sum()), 1), **RC.weighted_pct(dd, aa))

# ------------------------------------------------------------------ 10. manifest
bone_names = [b.name for b in arm.data.bones]


def vbone(o):
    gname = {g.index: g.name for g in o.vertex_groups}
    out = np.empty(len(o.data.vertices), np.int32)
    for v in o.data.vertices:
        gs = [g for g in v.groups if g.weight > 0]
        assert len(gs) == 1 and abs(gs[0].weight - 1) < 1e-6, (o.name, v.index)
        out[v.index] = bone_names.index(gname[gs[0].group])
    return out


def bounds_ue(o):
    co = RC.mesh_np(o.data)['co']
    lo, hi = co.min(0), co.max(0)
    return dict(min_cm=[round(100 * lo[0], 2), round(-100 * hi[1], 2), round(100 * lo[2], 2)],
                max_cm=[round(100 * hi[0], 2), round(-100 * lo[1], 2), round(100 * hi[2], 2)])


export_objs = [sob] + props + [OBJ['M'], bpy.data.objects[RC.MOVING + '_LOD1'], bpy.data.objects[RC.MOVING + '_LOD2'],
                              OBJ['H'], bpy.data.objects[RC.HULLDET + '_LOD1'], bpy.data.objects[RC.HULLDET + '_LOD2']] + turrets
arrays = dict(bone_names=np.array(bone_names), palette=RC.PAL, deleted_tris=DELETED_TRIS, deleted_edit=DELETED_EDIT,
              deleted_ids=np.array(DELETED_IDS))
objects = {}
for o in export_objs:
    me = o.data
    pal = RC.face_attr_get(me, 'r3_pal')
    objects[o.name] = dict(faces=len(me.polygons), tris=int(sum(len(p.vertices) - 2 for p in me.polygons)),
                           verts=len(me.vertices), uv_layers=[u.name for u in me.uv_layers],
                           materials=[m.name for m in me.materials], bounds=bounds_ue(o),
                           palette_use={RC.PALETTE_SLOTS[i][0]: int((pal == i).sum()) for i in np.unique(pal)})
    import hashlib
    objects[o.name]['uv_md5'] = {u.name: hashlib.md5(np.round(RC.uv_get(me, u.name) * 2 ** 20).astype(np.int64).tobytes()).hexdigest()
                                 for u in me.uv_layers}
    key = o.name.replace('SM_Airship', '').strip('_') or 'Hull'
    arrays[key + '__face_pal'] = pal
    if o.vertex_groups and o.name not in [t.name for t in turrets]:
        vb = vbone(o)
        arrays[key + '__vert_bone'] = vb
        objects[o.name]['bones'] = sorted({bone_names[i] for i in np.unique(vb)})
manifest = dict(
    about='Round 3 export manifest (r3_prep.py). Palette index = UV1.x = face attribute r3_pal. Bounds in Unreal '
          'component cm (100x, -100y, 100z). Per vertex bones and per face palette: manifest_arrays.npz.',
    export_blend=RC.EXPORT_BLEND, input=dict(full_blend=RC.FULL_BLEND, full_md5=FULL_MD5, rig_blend=RC.RIG_BLEND),
    palette=[dict(index=i, slot=k, linear=list(c)) for i, (k, c) in enumerate(RC.PALETTE_SLOTS)],
    pages={g: dict(tex=RC.PAGES[g]['tex'], size=TEX[g], **{k: PACK[g][k] for k in ('density_all', 'density_z7', 'uv_area_used')})
           for g in ('H', 'M')} | {'hull': dict(tex=RC.PAGES['hull']['tex'], size=TEX['hull'], density=rep['density_hull'],
                                      uv=RC.UV_HULL_INK if HULL_UV == 'atlas' else RC.UV_INK,
                                      comic_mask=dict(texture=RC.HULL_MASK_R2, uv=RC.UV_INK)),
                                   'P': dict(tex=RC.PAGES['P']['tex'], size=2048)},
    reserved_blocks=dict(block_texels=RC.BLOCK, band_texels=RC.BAND, blank='top right', ink='top left'),
    objects=objects, sources=src_names, lods=rep['lods'],
    sk_fbx_order=sorted([sob.name] + [p.name for p in props] + [RC.MOVING]),
    props_palette=PROPS_PAL)
RC.dump_json(manifest, RC.MANIFEST)
np.savez_compressed(RC.check_out_path(RC.ARRAYS), **arrays)

# ------------------------------------------------------------------ 11. save the export blend
if not NO_SAVE:
    p = RC.check_out_path(RC.EXPORT_BLEND)
    for o in bpy.data.objects:
        if o.type == 'MESH' and o.name.startswith('SM_AirshipDetail_'):
            bpy.data.objects.remove(o)
    bpy.ops.wm.save_as_mainfile(filepath=p, relative_remap=False, compress=False, copy=True)
    rep['export_blend'] = dict(path=p, md5=RC.md5_file(p), bytes=os.path.getsize(p))
    log('saved', p)
rep['protected_end'] = RC.protected_state()
rep['protected_unchanged'] = all(rep['protected_start'][k]['md5'] == v['md5'] for k, v in rep['protected_end'].items())
rep['full_blend_md5_end'] = RC.md5_file(RC.FULL_BLEND)
rep['seconds'] = round(time.time() - log.t0, 1)
RC.dump_json(rep, RC.CHECK_DIR + '/prep_report.json')
log('done; protected unchanged:', rep['protected_unchanged'], '| full blend unchanged:', rep['full_blend_md5_end'] == FULL_MD5)
sys.stdout.flush()
os._exit(0)
