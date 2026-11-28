"""Round 3 export spike: does the planned Unreal look (palette colour per face + baked ink + rivet dots) hold up
against the approved zone 1 toon renders? (Docs/Airship/round3/EXPORT_R3.md section 7)

  BL_MEM_MAX=6G blender_capped.sh --python SourceArt/Airship/scripts/r3_spike.py -- --tag I --ink sdf --hull-ink sdf \
      --cap-deg 30 --cap-deg-tube 30 --shots-file Docs/Airship/round3/media/export/spike_shots.json \
      --shots close_flank,q34,side,chase65            (the chosen variant; ~50 s on the GPU, --cpu works)
  other knobs: --tex 2048 --density 80 --min-w 0.025 --pack-px 4 --cull 0.02 --dot-r 0.018 --dmax 0.08 --ink-px 2.2
      --wmin 0.002 --crease-deg 35 --box-deg 60 --no-ink-sides --no-hull-contour; --ink comic (his shader, knobs
      --bevel --crease --spot --hatch --panel --hatch-freq --edge-thr) and --hull-ink his|rebake|sdf
      (+ --hull-bevel --hull-crease --hull-spot --hull-hatch --hull-panel --hull-tex)

Never saves a .blend. Talal's files are only read (comic_lines.py source, his round 2 drivable hull mask).
 1. Opens the zone 1 file (SM_Airship as the rig has it, the 4 zone 1 detail objects) in the rest pose.
 2. Joins the 4 detail objects and sorts their faces: rivets (Freestyle mark) -> a blank texel block; hidden faces
    (plate bottoms sunk into or pressed on the hull, faces touching another piece) and thin faces (short side under
    --min-w) -> no atlas space; thin SIDES and chamfers of pieces with atlas fronts -> a solid ink block (the plates'
    outline band); the rest is unwrapped (smart project 60 deg, uniform scale = --density texels per metre, packed
    with --pack-px margins on a --tex page).
 3. Ink. sdf (chosen): position + face id bakes (Cycles, 1 sample), then for every texel the distance to the nearest
    feature edge of its face's 1-ring (r3_sdf: hard creases, class boundaries, borders and the pieces' front contours),
    stored as distance / --dmax in R. The material draws the line at --ink-px pixels (view distance x pixel angle,
    what Unreal gets from PixelDepth or fwidth). comic: his shader (r3_ink) baked as an emission mask, his post-process.
    The hull gets the same treatment on its own UVs (--hull-ink sdf) or keeps his round 2 mask (his) or his shader
    re-baked with the details present (rebake).
 4. Rivet dots in G: every texel within --dot-r of a rivet's foot point (the plate under the head) gets a dot.
 5. Renders (EEVEE): 'lit' = Unreal-like (Principled, roughness 0.9, sun + sky ambient, Standard view), base colour =
    mix(mix(palette[role], rivet, G), ink, line); the hull's palette by part class (detail_render.ship_face_classes);
    props keep their in-game paper texture. Variants lit (LOD0), lit_lod1 (no rivet geometry, the dots alone), flat.
Outputs: rig/detail/r3export/spike/<tag>/ (ink PNGs, renders, spike_report.json); sheets: r3_spike_sheet.py.
"""
import bpy, bmesh, sys, os, json, math, time
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np
from mathutils import Vector as V, Matrix
from mathutils.bvhtree import BVHTree
import rig_common as C
import detail_common as D
import detail_render as R
import r3_ink as K
import r3_sdf as S

A = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []


def arg(k, d, f=str):
    return f(A[A.index(k) + 1]) if k in A else d


BLEND = arg('--blend', D.zone_blend(1))
TEX = arg('--tex', 2048, int)
DENSITY = arg('--density', 80.0, float)
KN = dict(bevel=arg('--bevel', 0.025, float), crease=arg('--crease', 0.05, float), spot=arg('--spot', 0.4, float),
          hatch=arg('--hatch', 1.0, float), panel=arg('--panel', 1.0, float), hatch_freq=arg('--hatch-freq', 2.4, float),
          edge_thr=arg('--edge-thr', 0.26, float))
DOT_R = arg('--dot-r', 0.018, float)
MIN_W = arg('--min-w', 0.025, float)
PACK_PX = arg('--pack-px', 4, int)
CULL_D = arg('--cull', 0.02, float)                     # faces whose normal ray hits the ship within this: hidden
HULL_INK = arg('--hull-ink', 'his')                     # his = his round 2 mask | rebake = his shader | sdf = lines
HKN = dict(bevel=arg('--hull-bevel', 0.08, float), crease=arg('--hull-crease', 0.15, float),
           spot=arg('--hull-spot', 1.2, float), hatch=arg('--hull-hatch', 1.0, float),
           panel=arg('--hull-panel', 1.0, float), hatch_freq=2.4, edge_thr=0.26)
TEXH = arg('--hull-tex', 4096, int)
INK_MODE = arg('--ink', 'sdf')                          # sdf = geometric lines as a distance field | comic = his shader
CREASE = arg('--crease-deg', 35.0, float)               # sdf: hard edges whose faces turn more than this are lines
DMAX = arg('--dmax', 0.08, float)                       # sdf: distance range stored in the texture (m)
INK_PX = arg('--ink-px', 2.2, float)                    # sdf: line width in pixels (the material)
WMIN = arg('--wmin', 0.002, float)                      # sdf: smallest half width (m)
CAP_DEG = arg('--cap-deg', 50.0, float)                 # sdf: faces within this of a piece's front draw its outline
CAP_DEG_TUBE = arg('--cap-deg-tube', 70.0, float)       # sdf: the same for closed pieces (tubes): lines near their outline
HULL_CONTOUR = '--no-hull-contour' not in A            # sdf: the hull's own pieces (not its skin) get front contours too
INK_SIDES = '--no-ink-sides' not in A                  # thin sides / chamfers of plates: solid ink (outline band)
BOX_DEG = arg('--box-deg', 60.0, float)                 # sdf: creases on details (boxes' corners), hull uses --crease-deg
SAMPLES = arg('--samples', 64, int)
SHOTS = arg('--shots', 'close_flank,q34,side').split(',')
if '--shots-file' in A:                                 # extra cameras {name: {loc, tgt, lens | ortho, res}}
    for k_, v_ in json.load(open(arg('--shots-file', ''))).items():
        R.SHOTS[k_] = (tuple(v_['loc']), tuple(v_['tgt']), ('ortho', float(v_['ortho'])) if 'ortho' in v_ else
                       float(v_.get('lens', 35.0)), tuple(v_.get('res', (1920, 1080))))
TAG = arg('--tag', 'A')
CPU = '--cpu' in A
RES_SCALE = arg('--res-scale', 100, int)
OUT = '/mnt/new_partition/BlenderProjects/StylizedAirship/rig/detail/r3export/spike/' + TAG
HULL_MASK = C.RIG + '/checks/hull_ink/T_AirshipDrivable_ComicMask.png'      # round 2: his mask + the deck-piece fix
PROPS_TEX = C.RIG + '/props/textures/T_AirshipProps_ComicLines.png'
MARGIN = 12
RESERVED = 16                     # texels: two blocks in the top-right corner: blank (rivets) and solid ink
T0 = time.time()
rep = dict(blend=BLEND, tex=TEX, density_target=DENSITY, knobs=KN, dot_r=DOT_R, samples=SAMPLES)


def log(*a):
    print('[r3_spike %5.0fs]' % (time.time() - T0), *a, flush=True)


os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=BLEND)
sc, cam = R.base_scene()
arm = bpy.data.objects['Armature']
for pb in arm.pose.bones:
    pb.matrix_basis = Matrix.Identity(4)
bpy.context.view_layer.update()
ship = bpy.data.objects[C.HULL_OBJ]
dets = sorted([o for o in bpy.data.objects if o.type == 'MESH' and o.name.startswith('SM_AirshipDetail_Z1_')],
              key=lambda o: o.name)
assert len(dets) == 4, [o.name for o in dets]
coll = bpy.data.collections.new('R3_Spike')
sc.collection.children.link(coll)


def copy_obj(ob, name, keep_mods=False):
    o = bpy.data.objects.new(name, ob.data.copy())
    o.matrix_world = ob.matrix_world.copy()
    coll.objects.link(o)
    return o


def join(objs, name):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    o = bpy.context.view_layer.objects.active
    o.name = name
    return o


def apply_world(o):
    o.data.transform(o.matrix_world)
    o.matrix_world = Matrix.Identity(4)


# ------------------------------------------------------------------ 1-2. joined details + atlas
cps = [copy_obj(o, 'tmp_' + o.name) for o in dets]
for o in cps:
    apply_world(o)
det = join(cps, 'R3_Z1_Details')
me = det.data
nP = len(me.polygons)
mark = np.zeros(nP, bool); me.polygons.foreach_get('use_freestyle_mark', mark)
ls = np.empty(nP, np.int64); me.polygons.foreach_get('loop_start', ls)
lt = np.empty(nP, np.int64); me.polygons.foreach_get('loop_total', lt)
lp = np.repeat(np.arange(nP), lt)                       # polygon of every loop
co = np.empty(len(me.vertices) * 3); me.vertices.foreach_get('co', co); co = co.reshape(-1, 3)
lv = np.empty(len(me.loops), np.int64); me.loops.foreach_get('vertex_index', lv)
fa = np.empty(nP); me.polygons.foreach_get('area', fa)
nxt = np.arange(len(lv)) + 1
nxt[ls + lt - 1] = ls                                   # next loop in the same polygon
elen = np.linalg.norm(co[lv] - co[lv[nxt]], axis=1)
maxe = np.maximum.reduceat(elen, ls)
width = fa / np.maximum(maxe, 1e-9)                     # ~ the face's short side
blank = mark | (width < MIN_W)                          # rivets and thin faces: colour only, no atlas space
# hidden faces (plate bottoms on the hull, faces pressed against another piece): no atlas space either
hidden = np.zeros(nP, bool)
if CULL_D > 0:
    sco = np.empty(len(ship.data.vertices) * 3); ship.data.vertices.foreach_get('co', sco); sco = sco.reshape(-1, 3)
    spolys = [list(q.vertices) for q in ship.data.polygons]
    dpolys = [list(lv[ls[q]:ls[q] + lt[q]] + len(sco)) for q in range(nP) if not mark[q]]
    cbvh = BVHTree.FromPolygons(np.vstack([sco, co]).tolist(), spolys + dpolys)
    pn_ = np.empty(nP * 3); me.polygons.foreach_get('normal', pn_); pn_ = pn_.reshape(-1, 3)
    pc_ = np.empty(nP * 3); me.polygons.foreach_get('center', pc_); pc_ = pc_.reshape(-1, 3)
    hb_ = BVHTree.FromPolygons(sco.tolist(), spolys)
    for q in np.nonzero(~blank)[0]:
        if cbvh.ray_cast(V(pc_[q] + pn_[q] * 0.002), V(pn_[q]), CULL_D)[0] is not None:
            hidden[q] = True
            continue
        # faces sunk into the hull (plate bottoms below its skin) and facing into it
        hp_, hn_, _, hd_ = hb_.find_nearest(V(pc_[q]), 0.25)
        if hp_ is not None and np.dot(pn_[q], hn_) < -0.5 and np.dot(pc_[q] - np.array(hp_), hn_) < 0.005:
            hidden[q] = True
    blank |= hidden
# each piece's front (its visible faces' mean normal, else the hull's outward normal there); faces that turn more than
# CAP_DEG from it are its sides. Thin sides and chamfers of a piece that has atlas faces get SOLID INK (the plate's
# outline band, like the previews' contour lines); other thin faces only their colour.
_hco = np.empty(len(ship.data.vertices) * 3); ship.data.vertices.foreach_get('co', _hco)
hbvh = BVHTree.FromPolygons(_hco.reshape(-1, 3).tolist(), [list(q.vertices) for q in ship.data.polygons])
dfn = np.empty(nP * 3); me.polygons.foreach_get('normal', dfn); dfn = dfn.reshape(-1, 3)
dfc = np.empty(nP * 3); me.polygons.foreach_get('center', dfc); dfc = dfc.reshape(-1, 3)


def hull_out(fi_):
    hit_ = hbvh.find_nearest(V(dfc[fi_]))
    return np.array(hit_[1]) if hit_[0] is not None else np.array((0.0, 0.0, 1.0))


dpiece = S.pieces(len(co), ls, lt, lv)
dcap, n_weak = S.cap_faces(dpiece, dfn, fa, (~hidden & ~mark & (width >= MIN_W)).astype(np.float64), hull_out,
                           cap_deg=CAP_DEG, cap_deg_weak=CAP_DEG_TUBE)
# the outline band: thin side faces reached from an atlas front face in up to two steps (chamfer, then side)
dpairs = S.edge_pairs(ls, lt, lv)
inkf = S.grow(~blank & (dcap == 1), blank & ~mark & ~hidden & (dcap == 0), dpairs, 2) & INK_SIDES
rep['front'] = dict(pieces=int(len(np.unique(dpiece))), front_from_hull_normal=n_weak, ink_side_faces=int(inkf.sum()),
                    ink_side_area=round(float(fa[inkf].sum()), 2))
for u in list(me.uv_layers):
    me.uv_layers.remove(u)
uvl = me.uv_layers.new(name='R3Atlas')
uvl.data.foreach_set('uv', np.zeros(len(me.loops) * 2))
me.uv_layers.active = uvl
uvl.active_render = True
rep['faces'] = dict(total=int(nP), rivet=int(mark.sum()), hidden=int(hidden.sum()), area_hidden=round(float(fa[hidden].sum()), 2),
                    thin=int((blank & ~mark & ~hidden).sum()), atlas=int((~blank).sum()),
                    area_m2=round(float(fa.sum()), 1), area_rivet=round(float(fa[mark].sum()), 2),
                    area_thin=round(float(fa[blank & ~mark].sum()), 2), area_atlas=round(float(fa[~blank].sum()), 1))
log('details joined', rep['faces'], [m.name for m in me.materials])

me.calc_loop_triangles()
tl = np.empty(len(me.loop_triangles) * 3, np.int64); me.loop_triangles.foreach_get('loops', tl); tl = tl.reshape(-1, 3)
tp = np.empty(len(me.loop_triangles), np.int64); me.loop_triangles.foreach_get('polygon_index', tp)


def density(uvs):
    tu = uvs[tl]; tc = co[lv[tl]]
    a2 = 0.5 * np.abs((tu[:, 1, 0] - tu[:, 0, 0]) * (tu[:, 2, 1] - tu[:, 0, 1]) - (tu[:, 2, 0] - tu[:, 0, 0]) * (tu[:, 1, 1] - tu[:, 0, 1]))
    a3 = 0.5 * np.linalg.norm(np.cross(tc[:, 1] - tc[:, 0], tc[:, 2] - tc[:, 0]), axis=1)
    k = (~blank[tp]) & (a3 > 1e-9)
    d = np.sqrt(a2[k] * TEX * TEX / a3[k])
    o = np.argsort(d); cw = np.cumsum(a3[k][o]) / a3[k].sum()
    return float(np.interp(0.5, cw, d[o])), float(a2[k].sum()), float(a3[k].sum())


def get_uv():
    u = me.uv_layers['R3Atlas']                         # layer references go stale across edit mode
    a = np.empty(len(me.loops) * 2); u.data.foreach_get('uv', a)
    return a.reshape(-1, 2)


def set_uv(a):
    me.uv_layers['R3Atlas'].data.foreach_set('uv', a.ravel())


bpy.context.view_layer.objects.active = det
for o in bpy.context.view_layer.objects:
    o.select_set(o is det)
sc.tool_settings.mesh_select_mode = (False, False, True)
me.polygons.foreach_set('select', ~blank)
vsel = np.zeros(len(me.vertices), bool); vsel[lv[~blank[lp]]] = True
me.vertices.foreach_set('select', vsel)
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.hide(unselected=True)                      # UV operators must not see the blank faces
t = time.time()
bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.0, area_weight=0.0, correct_aspect=True,
                         scale_to_bounds=False)
bpy.ops.uv.select_all(action='SELECT')
bpy.ops.uv.average_islands_scale()
bpy.ops.object.mode_set(mode='OBJECT')
log('smart project + average scale %.1fs' % (time.time() - t))
uv = get_uv()
d0, _, _ = density(uv)
pack_scale = DENSITY > 0
if pack_scale:
    uv[~blank[lp]] *= DENSITY / d0                      # exact density, then pack without scaling
    set_uv(uv)
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.uv.select_all(action='SELECT')
t = time.time()
bpy.ops.uv.pack_islands(rotate=True, scale=not pack_scale, margin_method='ADD', margin=PACK_PX / TEX,
                        shape_method='CONVEX')
log('pack %.1fs' % (time.time() - t))
bpy.ops.mesh.reveal(select=False)
bpy.ops.object.mode_set(mode='OBJECT')
uv = get_uv()
ua = uv[~blank[lp]]
hi = 1.0 - (RESERVED + 2.0) / TEX
in_res = np.all(ua > hi, axis=1).sum()
overflow = int(((ua < 0) | (ua > 1)).any(axis=1).sum())
uv[blank[lp]] = 1.0 - (RESERVED * 0.5) / TEX            # rivets and thin faces: the blank block (no ink, no dots)
uv[inkf[lp]] = (1.0 - (RESERVED * 1.5) / TEX, 1.0 - (RESERVED * 0.5) / TEX)    # thin sides: the solid ink block
set_uv(uv)
d_fin, used, area3 = density(uv)
rep['atlas'] = dict(density=round(d_fin, 1), uv_used=round(used, 4), packing_efficiency=round(used / max(
    float(ua[:, 0].max() * ua[:, 1].max()), 1e-9), 3), extent=np.round(ua.max(0), 4).tolist(), overflow_loops=overflow,
    loops_in_reserved_block=int(in_res), area_atlas_m2=round(area3, 1), margin_px=PACK_PX, bake_margin_px=MARGIN)
log('atlas', rep['atlas'])

# ------------------------------------------------------------------ 3. bake mesh: details without rivets + the hull
_, hull_keys = R.ship_face_classes()                    # palette class per SM_Airship face (the toon previews' map)
hull_order = sorted(set(hull_keys))
hull_cls = np.array([hull_order.index(k_) for k_ in hull_keys], np.int32)


def face_attr(m_, name, vals):
    a_ = m_.attributes.get(name) or m_.attributes.new(name, 'FLOAT', 'FACE')
    a_.data.foreach_set('value', np.asarray(vals, np.float32))


def plain_mat(name):
    m_ = bpy.data.materials.new(name); m_.use_nodes = True
    return m_


det_mi = np.empty(nP, np.int64); me.polygons.foreach_get('material_index', det_mi)
if INK_MODE == 'comic':
    mat_det = K.comic_material('R3_BakeDet', **KN)
    mat_hull = K.comic_material('R3_BakeHull', **(HKN if HULL_INK == 'rebake' else KN))
else:
    mat_det, mat_hull = plain_mat('R3_BakeDet'), plain_mat('R3_BakeHull')
mat_blank = plain_mat('R3_BakeBlank')
bk_det = copy_obj(det, 'tmp_bake_det')
face_attr(bk_det.data, 'r3_cls', 100 + det_mi)
bk_det.data.materials.clear()
for m_ in (mat_det, mat_hull, mat_blank):
    bk_det.data.materials.append(m_)
bk_det.data.polygons.foreach_set('material_index', np.where(blank, 2, 0).astype(np.int32))  # thin / hidden: dummy
bmd = bmesh.new(); bmd.from_mesh(bk_det.data)
bmd.faces.ensure_lookup_table()
bmesh.ops.delete(bmd, geom=[f for f in bmd.faces if mark[f.index]], context='FACES')
bmd.to_mesh(bk_det.data); bmd.free()
bk_hull = copy_obj(ship, 'tmp_bake_hull')
apply_world(bk_hull)
bk_hull.data.uv_layers.new(name='R3Atlas')              # = the hull's own UVs (its faces bake into the hull image)
_hu = np.empty(len(bk_hull.data.loops) * 2); bk_hull.data.uv_layers['UVMap'].data.foreach_get('uv', _hu)
bk_hull.data.uv_layers['R3Atlas'].data.foreach_set('uv', _hu)
face_attr(bk_hull.data, 'r3_cls', hull_cls)
bk_hull.data.materials.clear(); bk_hull.data.materials.append(mat_hull)
bk_hull.data.polygons.foreach_set('material_index', np.zeros(len(bk_hull.data.polygons), np.int32))
bake = join([bk_det, bk_hull], 'R3_Bake')
bme = bake.data
bme.uv_layers.active = bme.uv_layers['R3Atlas']
bme.uv_layers['R3Atlas'].active_render = True
bnP = len(bme.polygons)
face_attr(bme, 'r3_fid', np.arange(bnP))
bmi = np.empty(bnP, np.int64); bme.polygons.foreach_get('material_index', bmi)
log('bake mesh: %d faces (%d detail atlas, %d hull, %d blank)' % (bnP, (bmi == 0).sum(), (bmi == 1).sum(), (bmi == 2).sum()))

sc.render.engine = 'CYCLES'
dev = 'CPU'
if not CPU:
    prefs = bpy.context.preferences.addons['cycles'].preferences
    for dt in ('OPTIX', 'CUDA'):
        try:
            prefs.compute_device_type = dt
            prefs.get_devices()
            if any(d_.type == dt for d_ in prefs.devices):
                break
        except TypeError:
            continue
    for d_ in prefs.devices:
        d_.use = d_.type != 'CPU'
    dev = 'GPU' if any(d_.use for d_ in prefs.devices) else 'CPU'
sc.cycles.device = dev
sc.render.bake.margin = MARGIN
sc.render.bake.margin_type = 'EXTEND'
for o in sc.objects:
    o.hide_render = o is not bake
for o in bpy.context.view_layer.objects:
    o.select_set(o is bake)
bpy.context.view_layer.objects.active = bake


def target(m_, img):
    nt = m_.node_tree
    n_ = nt.nodes.get('_R3Target') or nt.nodes.new('ShaderNodeTexImage')
    n_.name = '_R3Target'
    n_.image = img
    nt.nodes.active = n_


def emit_source(m_, kind):
    """emission of the world position ('pos') or of the face id attribute ('fid')"""
    nt = m_.node_tree
    for n_ in list(nt.nodes):
        if n_.name != '_R3Target':
            nt.nodes.remove(n_)
    em_ = nt.nodes.new('ShaderNodeEmission'); out_ = nt.nodes.new('ShaderNodeOutputMaterial')
    if kind == 'pos':
        src = nt.nodes.new('ShaderNodeNewGeometry').outputs['Position']
    else:
        at = nt.nodes.new('ShaderNodeAttribute'); at.attribute_type = 'GEOMETRY'; at.attribute_name = 'r3_fid'
        src = at.outputs['Fac']
    nt.links.new(src, em_.inputs['Color']); nt.links.new(em_.outputs[0], out_.inputs['Surface'])


def float_img(name, size, fill):
    im = bpy.data.images.new(name, size, size, alpha=True, float_buffer=True)
    im.colorspace_settings.name = 'Non-Color'
    im.pixels.foreach_set(np.full(size * size * 4, fill, np.float32))
    return im


def read_img(im, ch=3):
    s_ = im.size[0]
    a_ = np.empty(s_ * s_ * 4, np.float32); im.pixels.foreach_get(a_)
    return a_.reshape(s_, s_, 4)[:, :, :ch]


dummy = bpy.data.images.new('_r3_dummy', 8, 8)
dummy.colorspace_settings.name = 'Non-Color'
HULL_PAGE = HULL_INK in ('rebake', 'sdf')
lines = None
hull_lines = None
t_bake = time.time()
if INK_MODE == 'comic':
    ink_img = bpy.data.images.new('_r3_ink', TEX, TEX); ink_img.colorspace_settings.name = 'Non-Color'
    hull_img = bpy.data.images.new('_r3_hull', TEXH, TEXH) if HULL_INK == 'rebake' else None
    if hull_img:
        hull_img.colorspace_settings.name = 'Non-Color'
    for m_ in (mat_det, mat_hull):
        K.link_mask_output(m_)
    target(mat_det, ink_img); target(mat_hull, hull_img or dummy); target(mat_blank, dummy)
    sc.cycles.samples = SAMPLES
    bpy.ops.object.bake(type='EMIT', margin=MARGIN, use_clear=True)
    lines = K.post_process(read_img(ink_img, 1)[:, :, 0])
    if hull_img:
        hull_lines = K.post_process(read_img(hull_img, 1)[:, :, 0])
# position + face id (1 sample: one face per texel, exact values)
SENT = 1.0e6
pos_img = float_img('_r3_pos', TEX, SENT)
fid_img = float_img('_r3_fid', TEX, -1.0)
hpos_img = float_img('_r3_hpos', TEXH, SENT) if HULL_PAGE else None
hfid_img = float_img('_r3_hfid', TEXH, -1.0) if HULL_PAGE else None
keep_mats = [mat_det, mat_hull, mat_blank]
pms = [plain_mat('_r3_e%d' % i) for i in range(3)]
for i in range(3):
    bme.materials[i] = pms[i]
sc.cycles.samples = 1
for kind, imgs in (('pos', (pos_img, hpos_img)), ('fid', (fid_img, hfid_img))):
    if INK_MODE == 'comic' and kind == 'fid' and HULL_INK != 'sdf':
        continue
    for i, m_ in enumerate(pms):
        emit_source(m_, kind)
        target(m_, [imgs[0], imgs[1] or dummy, dummy][i] or dummy)
    bpy.ops.object.bake(type='EMIT', margin=MARGIN, use_clear=False)
for i in range(3):
    bme.materials[i] = keep_mats[i]
rep['bake_s'] = round(time.time() - t_bake, 1)
pos = read_img(pos_img)
cov = pos[:, :, 0] < SENT * 0.5
log('bakes done in %.1fs (%s): %d covered detail texels' % (rep['bake_s'], dev, cov.sum()))

if INK_MODE == 'sdf' or HULL_INK == 'sdf':
    t = time.time()
    bco = np.empty(len(bme.vertices) * 3); bme.vertices.foreach_get('co', bco); bco = bco.reshape(-1, 3)
    bls = np.empty(bnP, np.int64); bme.polygons.foreach_get('loop_start', bls)
    blt = np.empty(bnP, np.int64); bme.polygons.foreach_get('loop_total', blt)
    blv = np.empty(len(bme.loops), np.int64); bme.loops.foreach_get('vertex_index', blv)
    bcn = np.empty(len(bme.loops) * 3); bme.corner_normals.foreach_get('vector', bcn); bcn = bcn.reshape(-1, 3)
    bfn = np.empty(bnP * 3); bme.polygons.foreach_get('normal', bfn); bfn = bfn.reshape(-1, 3)
    bcl = np.empty(bnP, np.float32); bme.attributes['r3_cls'].data.foreach_get('value', bcl)
    bfa = np.empty(bnP); bme.polygons.foreach_get('area', bfa)
    bcen = np.empty(bnP * 3); bme.polygons.foreach_get('center', bcen); bcen = bcen.reshape(-1, 3)
    is_det = bmi != 1
    piece = S.pieces(len(bco), bls, blt, blv)
    det_keep = np.nonzero(~mark)[0]                     # bake face k < len(det_keep) = joined detail face det_keep[k]
    cap = np.full(bnP, -1, np.int64); cap[:len(det_keep)] = dcap[det_keep]
    if HULL_CONTOUR:
        hsel = np.nonzero(bmi == 1)[0]
        hp_ = piece[hsel]
        ua, inv_ = np.unique(hp_, return_inverse=True)
        parea = np.zeros(len(ua)); np.add.at(parea, inv_, bfa[hsel])
        skin = ua[np.argmax(parea)]
        hc, _ = S.cap_faces(hp_, bfn[hsel], bfa[hsel], np.ones(len(hsel)), lambda f_: np.array((0.0, 0.0, 1.0)),
                            cap_deg=CAP_DEG, cap_deg_weak=CAP_DEG_TUBE)
        cap[hsel] = np.where(hp_ == skin, -1, hc)
    cdeg = np.where(is_det, BOX_DEG, CREASE)
    segs, sv, fcount = S.feature_segments(bco, bls, blt, blv, bcn, bfn, bcl.astype(np.int64), crease_deg=cdeg,
                                          cap=cap)

    csr = S.face_lists(bls, blt, blv, sv, len(bco))
    rep['features'] = fcount
    log('feature edges', fcount, '%.1fs' % (time.time() - t))
    if INK_MODE == 'sdf':
        fid = np.round(read_img(fid_img, 1)[:, :, 0]).astype(np.int64)
        dist = S.distance_map(fid, pos, cov & (fid >= 0), csr, segs, DMAX, faces_ok=(bmi == 0))
        lines = dist / DMAX                              # stored distance (0..1 = 0..DMAX metres)
        log('detail distance field %.1fs' % (time.time() - t))
    if HULL_INK == 'sdf':
        hpos = read_img(hpos_img)
        hfid = np.round(read_img(hfid_img, 1)[:, :, 0]).astype(np.int64)
        hcov = (hpos[:, :, 0] < SENT * 0.5) & (hfid >= 0)
        hull_lines = S.distance_map(hfid, hpos, hcov, csr, segs, DMAX, faces_ok=(bmi == 1)) / DMAX
        del hpos, hfid
        log('hull distance field %.1fs' % (time.time() - t))
lines[TEX - RESERVED:, TEX - RESERVED:] = 1.0 if INK_MODE == 'sdf' else 0.0      # the blank block: no ink
lines[TEX - RESERVED:, TEX - 2 * RESERVED:TEX - RESERVED] = 0.0 if INK_MODE == 'sdf' else 1.0   # the ink block
rep['ink_mode'] = INK_MODE
if hull_lines is not None:
    hq = np.ones((TEXH, TEXH, 4), np.float32)
    hq[:, :, 0] = hull_lines; hq[:, :, 1] = hull_lines; hq[:, :, 2] = hull_lines
    hull_out = bpy.data.images.new('T_R3Spike_HullInk', TEXH, TEXH); hull_out.colorspace_settings.name = 'Non-Color'
    hull_out.pixels.foreach_set(hq.ravel())
    hull_out.filepath_raw = OUT + '/T_R3Spike_HullInk.png'; hull_out.file_format = 'PNG'; hull_out.save(); hull_out.pack()
    rep['hull_ink'] = dict(mode=HULL_INK, knobs=HKN if HULL_INK == 'rebake' else dict(dmax=DMAX, crease=CREASE),
                           texture=hull_out.filepath_raw)
    del hq
else:
    rep['hull_ink'] = dict(mode='his round 2 mask', texture=HULL_MASK)

# ------------------------------------------------------------------ 4. rivet dots
bme.calc_loop_triangles()
bco = np.empty(len(bme.vertices) * 3); bme.vertices.foreach_get('co', bco); bco = bco.reshape(-1, 3)
btri = np.empty(len(bme.loop_triangles) * 3, np.int64); bme.loop_triangles.foreach_get('vertices', btri)
btp = np.empty(len(bme.loop_triangles), np.int64); bme.loop_triangles.foreach_get('polygon_index', btp)
bvh = BVHTree.FromPolygons(bco.tolist(), btri.reshape(-1, 3).tolist(), all_triangles=True)
tri_is_det = bmi[btp] == 0
par = {}


def find(a):
    while par.setdefault(a, a) != a:
        par[a] = par[par[a]]
        a = par[a]
    return a


fn = np.empty(nP * 3); me.polygons.foreach_get('normal', fn); fn = fn.reshape(-1, 3)
for p in np.nonzero(mark)[0]:
    vs = lv[ls[p]:ls[p] + lt[p]]
    r0 = find(int(vs[0]))
    for q in vs[1:]:
        rq = find(int(q))
        if rq != r0:
            par[rq] = r0
groups = {}
for p in np.nonzero(mark)[0]:
    groups.setdefault(find(int(lv[ls[p]])), []).append(p)
P = pos[cov]
idx = np.nonzero(cov.ravel())[0]
CELL = 0.05
key = np.floor(P / CELL).astype(np.int64)
h = (key[:, 0] * 73856093) ^ (key[:, 1] * 19349663) ^ (key[:, 2] * 83492791)
order = np.argsort(h); hs = h[order]
dots = np.zeros(TEX * TEX, np.float32)
aa = 0.5 / max(d_fin, 1.0)
n_hull = n_none = n_ok = 0
for g, faces in groups.items():
    faces = np.array(faces)
    vs = np.unique(np.concatenate([lv[ls[p]:ls[p] + lt[p]] for p in faces]))
    c = co[vs].mean(0)
    # axis = normal of the head's largest face (a closed head's area-weighted normals sum to zero); the plate is the
    # nearer hit of the two rays along it (the head is sunk a few mm into the plate)
    n = fn[faces[np.argmax(fa[faces])]]
    best = None
    for s in (1.0, -1.0):
        hit, nrm, ti, dist_ = bvh.ray_cast(V(c), V(n * s), 0.08)
        if hit is not None and (best is None or dist_ < best[3]):
            best = (hit, nrm, ti, dist_)
    if best is None:
        n_none += 1
        continue
    hit, nrm, ti, dist_ = best
    if not tri_is_det[ti]:
        n_hull += 1
        continue
    foot = np.array(hit)
    n = np.array(nrm)
    kk = np.floor(foot / CELL).astype(np.int64)
    cand = []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                hh = ((kk[0] + dx) * 73856093) ^ ((kk[1] + dy) * 19349663) ^ ((kk[2] + dz) * 83492791)
                a0, a1 = np.searchsorted(hs, hh), np.searchsorted(hs, hh, side='right')
                if a1 > a0:
                    cand.append(order[a0:a1])
    if not cand:
        n_none += 1
        continue
    cand = np.concatenate(cand)
    rel = P[cand] - foot
    along = rel @ n
    inpl = np.linalg.norm(rel - np.outer(along, n), axis=1)
    v = np.clip((DOT_R + aa - inpl) / (2 * aa), 0, 1) * (np.abs(along) < 0.03)
    ii = idx[cand]
    dots[ii] = np.maximum(dots[ii], v)
    n_ok += 1
dots = dots.reshape(TEX, TEX)
dots[TEX - RESERVED:, TEX - RESERVED:] = 0.0
rep['rivets'] = dict(pieces=len(groups), dotted=n_ok, on_hull_not_dotted=n_hull, no_hit=n_none)
log('rivet dots', rep['rivets'])

out_img = bpy.data.images.new('T_R3Spike_Ink', TEX, TEX)
out_img.colorspace_settings.name = 'Non-Color'
rgba = np.zeros((TEX, TEX, 4), np.float32)
rgba[:, :, 0] = lines; rgba[:, :, 1] = dots; rgba[:, :, 3] = 1.0
out_img.pixels.foreach_set(rgba.ravel())
out_img.filepath_raw = OUT + '/T_R3Spike_Ink.png'; out_img.file_format = 'PNG'; out_img.save()
out_img.pack()
rep['ink_texture'] = out_img.filepath_raw

# ------------------------------------------------------------------ 5. render materials
bpy.data.objects.remove(bake)
INK = K.srgb_to_linear(K.hex_rgb(K.INK_HEX))
pal = dict(D.PALETTE); pal.update(R.EXTRA)
if hull_lines is not None:
    hull_tex = bpy.data.images['T_R3Spike_HullInk']
else:
    hull_tex = bpy.data.images.load(HULL_MASK); hull_tex.colorspace_settings.name = 'Non-Color'
HULL_SDF = HULL_INK == 'sdf'
props_img = bpy.data.images.load(PROPS_TEX)

# the line width group: ink = 1 - smoothstep(w - px/2, w + px/2, d), w = clamp(INK_PX * px / 2, WMIN, 0.95 DMAX),
# px = world size of a pixel = view distance * KPX + KC (set per shot) -- what fwidth(world position) gives in Unreal
ng = bpy.data.node_groups.new('R3InkWidth', 'ShaderNodeTree')
ng.interface.new_socket(name='Dist01', in_out='INPUT', socket_type='NodeSocketFloat')
ng.interface.new_socket(name='Ink', in_out='OUTPUT', socket_type='NodeSocketFloat')
gi = ng.nodes.new('NodeGroupInput'); go = ng.nodes.new('NodeGroupOutput')


def gval(name, v):
    n_ = ng.nodes.new('ShaderNodeValue'); n_.name = name; n_.outputs[0].default_value = v
    return n_.outputs[0]


def gmath(op, a_, b_):
    n_ = ng.nodes.new('ShaderNodeMath'); n_.operation = op
    for k_, x in enumerate((a_, b_)):
        if isinstance(x, (int, float)):
            n_.inputs[k_].default_value = x
        else:
            ng.links.new(x, n_.inputs[k_])
    return n_.outputs[0]


camd = ng.nodes.new('ShaderNodeCameraData')
px = gmath('ADD', gmath('MULTIPLY', camd.outputs['View Distance'], gval('KPX', 0.001)), gval('KC', 0.0))
w = gmath('MINIMUM', gmath('MAXIMUM', gmath('MULTIPLY', px, gval('INKPX', INK_PX * 0.5)), WMIN), 0.95 * DMAX)
d = gmath('MULTIPLY', gi.outputs['Dist01'], DMAX)
mr = ng.nodes.new('ShaderNodeMapRange'); mr.interpolation_type = 'SMOOTHSTEP'; mr.clamp = True
ng.links.new(d, mr.inputs['Value'])
ng.links.new(gmath('SUBTRACT', w, gmath('MULTIPLY', px, 0.5)), mr.inputs['From Min'])
ng.links.new(gmath('ADD', w, gmath('MULTIPLY', px, 0.5)), mr.inputs['From Max'])
mr.inputs['To Min'].default_value = 1.0; mr.inputs['To Max'].default_value = 0.0
ng.links.new(mr.outputs['Result'], go.inputs['Ink'])


def set_shot_ink(cam_, res_x):
    if cam_.data.type == 'ORTHO':
        ng.nodes['KPX'].outputs[0].default_value = 0.0
        ng.nodes['KC'].outputs[0].default_value = cam_.data.ortho_scale / res_x
    else:
        ng.nodes['KPX'].outputs[0].default_value = cam_.data.sensor_width / cam_.data.lens / res_x
        ng.nodes['KC'].outputs[0].default_value = 0.0


def look_mat(name, col, img=None, uvname=None, rivet=None, flat=False, sdf=False):
    m_ = bpy.data.materials.new(name); m_.use_nodes = True
    nt = m_.node_tree; nt.nodes.clear()
    out_ = nt.nodes.new('ShaderNodeOutputMaterial')
    base = nt.nodes.new('ShaderNodeRGB'); base.outputs[0].default_value = tuple(col) + (1.0,)
    cur = base.outputs[0]
    if img is not None:
        tx = nt.nodes.new('ShaderNodeTexImage'); tx.image = img; tx.interpolation = 'Linear'
        if uvname:
            uvn = nt.nodes.new('ShaderNodeUVMap'); uvn.uv_map = uvname; nt.links.new(uvn.outputs[0], tx.inputs['Vector'])
        sep = nt.nodes.new('ShaderNodeSeparateColor'); nt.links.new(tx.outputs['Color'], sep.inputs[0])
        if rivet is not None:
            rv = nt.nodes.new('ShaderNodeRGB'); rv.outputs[0].default_value = tuple(rivet) + (1.0,)
            mx = nt.nodes.new('ShaderNodeMix'); mx.data_type = 'RGBA'
            nt.links.new(sep.outputs[1], mx.inputs['Factor']); nt.links.new(cur, mx.inputs[6]); nt.links.new(rv.outputs[0], mx.inputs[7])
            cur = mx.outputs[2]
        inkf = sep.outputs[0]
        if sdf:
            gn = nt.nodes.new('ShaderNodeGroup'); gn.node_tree = ng
            nt.links.new(sep.outputs[0], gn.inputs['Dist01'])
            inkf = gn.outputs['Ink']
        ik = nt.nodes.new('ShaderNodeRGB'); ik.outputs[0].default_value = tuple(INK) + (1.0,)
        mx2 = nt.nodes.new('ShaderNodeMix'); mx2.data_type = 'RGBA'
        nt.links.new(inkf, mx2.inputs['Factor']); nt.links.new(cur, mx2.inputs[6]); nt.links.new(ik.outputs[0], mx2.inputs[7])
        cur = mx2.outputs[2]
    if flat:
        sh_ = nt.nodes.new('ShaderNodeEmission'); nt.links.new(cur, sh_.inputs['Color'])
    else:
        sh_ = nt.nodes.new('ShaderNodeBsdfPrincipled')
        sh_.inputs['Roughness'].default_value = 0.9
        nt.links.new(cur, sh_.inputs['Base Color'])
    nt.links.new(sh_.outputs[0], out_.inputs['Surface'])
    return m_


RIV = pal['bolt']
det_keys = [m_.get('palette_key') if m_ else 'paint_yellow' for m_ in me.materials]


def assign(flat):
    sme = ship.data
    sme.materials.clear()
    for kk in hull_order:
        sme.materials.append(look_mat('R3H_%s_%d' % (kk, flat), pal[kk], hull_tex, 'UVMap', flat=flat, sdf=HULL_SDF))
    sme.polygons.foreach_set('material_index', hull_cls)
    sme.update()
    for i, kk in enumerate(det_keys):
        me.materials[i] = look_mat('R3D_%s_%d' % (kk, flat), pal[kk], out_img, 'R3Atlas', rivet=RIV, flat=flat,
                                   sdf=INK_MODE == 'sdf')
    for ob in bpy.data.objects:
        if ob.type == 'MESH' and ob.name.startswith(C.PROP_PREFIX):
            ob.data.materials.clear()
            ob.data.materials.append(look_mat('R3P_%d_%s' % (flat, ob.name), (1, 1, 1), None, flat=flat))
            mm = ob.data.materials[0]; nt = mm.node_tree
            tx = nt.nodes.new('ShaderNodeTexImage'); tx.image = props_img
            sh_ = next(n_ for n_ in nt.nodes if n_.type in ('BSDF_PRINCIPLED', 'EMISSION'))
            nt.links.new(tx.outputs['Color'], sh_.inputs['Base Color' if sh_.type == 'BSDF_PRINCIPLED' else 'Color'])


lod1 = copy_obj(det, 'R3_Z1_Details_LOD1')              # LOD1: no rivet geometry (the dots alone)
bml = bmesh.new(); bml.from_mesh(lod1.data)
bml.faces.ensure_lookup_table()
bmesh.ops.delete(bml, geom=[f for f in bml.faces if mark[f.index]], context='FACES')
bml.to_mesh(lod1.data); bml.free()
for c_ in bpy.data.collections:
    if c_.name.startswith('Detail_'):
        c_.hide_render = True
for o in dets:
    o.hide_render = True
R.toon_world(sc)                                        # sun direction of the toon previews, sky ambient
sun = bpy.data.objects['PreviewSunToon']; sun.data.energy = 3.2
for n_ in sc.world.node_tree.nodes:
    if n_.type == 'BACKGROUND':
        n_.inputs['Strength'].default_value = 0.55 if n_.inputs['Strength'].default_value < 0.5 else 1.0
try:
    sc.eevee.taa_render_samples = 32
except Exception:
    pass
sc.render.use_freestyle = False
sc.render.resolution_percentage = RES_SCALE
for o in sc.objects:
    if o.type == 'MESH':
        o.hide_render = not (o is ship or o is det or o.name.startswith(C.PROP_PREFIX))
renders = []
for variant in ('lit', 'lit_lod1', 'flat'):
    assign(variant == 'flat')
    for i in range(len(lod1.data.materials)):
        lod1.data.materials[i] = me.materials[i]
    det.hide_render = variant == 'lit_lod1'
    lod1.hide_render = variant != 'lit_lod1'
    for sh in SHOTS:
        R.set_shot(sc, cam, sh)
        set_shot_ink(cam, sc.render.resolution_x * RES_SCALE / 100.0)
        sc.render.filepath = '%s/%s_%s.jpg' % (OUT, sh, variant)
        t = time.time()
        bpy.ops.render.render(write_still=True)
        renders.append(sc.render.filepath)
        log('render', sc.render.filepath, '%.1fs' % (time.time() - t))
rep['renders'] = renders
rep['seconds'] = round(time.time() - T0, 1)
with open(OUT + '/spike_report.json', 'w') as f:
    json.dump(rep, f, indent=1)
log('done', json.dumps({k_: rep.get(k_) for k_ in ('faces', 'atlas', 'rivets', 'bake_s', 'features')}))
