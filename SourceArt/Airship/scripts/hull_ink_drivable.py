"""Round 2 hull ink fix: T_AirshipDrivable_ComicLines.png, the hull's comic texture for the drivable ship.

Talal's T_Airship_ComicLines (StylizedAirship/textures = export/, baked by StylizedAirship/scripts/comic_lines.py on
2026-10-31) was baked with the five deck pieces that round 2 deleted from the rig copy (deck_removals.json). The deck
under each piece came out solid ink (AO ~0 under a box = comic_lines' "spotted black"), with contact lines round it, so
the drivable ship showed black rectangles and a bar where the pieces used to stand. This script re-bakes the same ink
with and without the pieces and takes only what the removal changes:

  blender -b --factory-startup --python SourceArt/Airship/scripts/hull_ink_drivable.py -- [--cpu] [--radius 1.5]
  (about 2 min on the GPU; --dump DIR also writes the arrays as .npy for debugging)

 1. Opens rig/AirshipRig.blend (SM_Airship = Talal's mesh minus the 21 removed islands; positions and UVs checked
    against his mesh, appended from the byte copy rig/AirshipRig_src.blend). Nothing is ever saved; Talal's files are
    only read.
 2. Bakes the ink twice exactly as comic_lines.py did (the M_ComicLines node tree stored in the file = the shader that
    baked the original, emission bake of its ComicMask output into an 8-bit Non-Color 4096 image, Cycles 64 samples,
    seed 0, margin 12 EXTEND, only the baked object rendering, then comic_lines' post-process: 2 passes of a [1,2,1]
    blur, smoothstep 0.38..0.52, paper #F3EEE4 / ink #1C2230 mix):
      A = the drivable SM_Airship (armature modifier off: the rest-pose mesh = Talal's positions),
      B = Talal's SM_Airship with the pieces in place (reproduces his texture: 99.99 % of the texels within 3 m of the
          pieces are byte-identical, the rest within 13 / 255 up to 1.2 m from them; see the report).
 3. Bakes the world position of every texel of A (float, same margin) and measures each texel's distance to the
    removed geometry (BVH nearest point on the islands of deck_removals.json).
 4. Output = Talal's texel everywhere, except where A != B (the removal's effect) on the drivable mesh's texels (and
    their bake padding) closer than RADIUS (1.5 m; the shader's longest reach is the 1.2 m AO, + the blur) to a
    removed piece: those take A. Texels inside the removed islands' own UV triangles (unused by the drivable ship) are
    kept. A != B also happens far from the pieces (Cycles picks bevel/local hits in BVH order, so a different mesh
    gives different but equally valid strokes in ~0.2 % of the texels): the radius keeps all of that out.
 5. Writes SourceArt/Airship/textures/T_AirshipDrivable_ComicLines.png (4096, 8-bit RGB, like the original) and
    rig/checks/hull_ink/: hull_ink_report.json (changed texels per piece and per connected group with PNG boxes and 3D
    centres, the removal effect and the B-vs-original agreement by distance), T_AirshipDrivable_ComicMask.png (the same
    fix on the mask; not used by the material), zone_preview.png (1024, PNG orientation: grey = drivable texels,
    blue = zone, red = changed).

Look check: hull_ink_render.py (top + perspective views, old vs new texture on the drivable rig).
"""
import sys, os, json, time, hashlib
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
import numpy as np
from mathutils import Vector as V, Matrix
from mathutils.bvhtree import BVHTree
import rig_common as C

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
CPU = '--cpu' in argv
RADIUS = float(argv[argv.index('--radius') + 1]) if '--radius' in argv else 1.5
DUMP = argv[argv.index('--dump') + 1] if '--dump' in argv else None    # debug: .npy arrays (re-bake, positions, distances)
STATS_R = 3.0                      # distances are measured out to here (agreement rings outside the zone)
TALAL = '/mnt/new_partition/BlenderProjects/StylizedAirship'
ORIG_LINES = TALAL + '/textures/T_Airship_ComicLines.png'      # = export/T_Airship_ComicLines.png (what Unreal has)
ORIG_MASK = TALAL + '/textures/T_Airship_ComicMask.png'
COMIC_SCRIPT = TALAL + '/scripts/comic_lines.py'
OUT_LINES = C.SOURCE_ART + '/textures/T_AirshipDrivable_ComicLines.png'
CHECK = C.RIG + '/checks/hull_ink'
TEX, SAMPLES, MARGIN = 4096, 64, 12                            # comic_lines.py defaults (COMIC_TEX, COMIC_SAMPLES)
SMOOTH, INK_CUT = 2, (0.38, 0.52)                              # comic_lines.py COMIC_SMOOTH, COMIC_INK_CUT
PAPER_HEX, INK_HEX = 'F3EEE4', '1C2230'
SENTINEL = 1.0e9
T0 = time.time()


def log(*a):
    print('[hull_ink %5.0fs]' % (time.time() - T0), *a, flush=True)


def md5(p):
    with open(p, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()


def to_bytes(f):
    """Blender's float -> byte for byte images (unit_float_to_uchar_clamp: round half up, clamped)"""
    return np.clip(np.floor(f * 255.0 + 0.5), 0, 255).astype(np.uint8)


def load_png_bytes(path, nonc):
    img = bpy.data.images.load(path, check_existing=False)
    img.colorspace_settings.name = 'Non-Color' if nonc else 'sRGB'
    assert tuple(img.size) == (TEX, TEX) and not img.is_float, (path, tuple(img.size), img.is_float)
    px = np.empty(TEX * TEX * 4, np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return to_bytes(px.reshape(TEX, TEX, 4)[:, :, :3])           # rows bottom-up (Blender order)


def save_png_bytes(path, rgb, nonc):
    img = bpy.data.images.new(os.path.splitext(os.path.basename(path))[0], rgb.shape[1], rgb.shape[0])  # byte, no alpha
    img.colorspace_settings.name = 'Non-Color' if nonc else 'sRGB'
    px = np.ones((rgb.shape[0], rgb.shape[1], 4), np.float32)
    px[:, :, :3] = rgb.astype(np.float32) / 255.0
    img.pixels.foreach_set(px.ravel())
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()
    bpy.data.images.remove(img)
    log('wrote', path)


# ------------------------------------------------------------------ inputs
for p in (ORIG_LINES, ORIG_MASK, C.RIG_BLEND, C.SRC_BLEND):
    assert os.path.isfile(p), p
INPUT_MD5 = {p: md5(p) for p in (ORIG_LINES, ORIG_MASK, C.RIG_BLEND, C.SRC_BLEND, COMIC_SCRIPT)}
# the ink settings below are comic_lines.py's; stop if that script no longer has them
_src = open(COMIC_SCRIPT).read()
for frag in ('globals().get("COMIC_TEX", 4096)', 'globals().get("COMIC_SAMPLES", 64)', 'scene.render.bake.margin = 12',
             'globals().get("COMIC_SMOOTH", 2)', 'globals().get("COMIC_INK_CUT", (0.38, 0.52))', '"F3", "EE", "E4"',
             '"1C", "22", "30"', 'margin_type = "EXTEND"'):
    assert frag in _src, 'comic_lines.py changed: ' + frag

bpy.ops.wm.open_mainfile(filepath=C.RIG_BLEND)
sc = bpy.context.scene
ob = bpy.data.objects[C.HULL_OBJ]
me = ob.data
assert ob.matrix_world == Matrix.Identity(4)
mc = bpy.data.materials['M_ComicLines']
nt = mc.node_tree
for n in ('ComicMask', 'BakeMask', 'BakeEmit', 'Out'):
    assert n in nt.nodes, 'M_ComicLines has no node ' + n

# the source mesh (Talal's SM_Airship, 36908 vertices) for the removed geometry; appended into memory only
with bpy.data.libraries.load(C.SRC_BLEND, link=False) as (src, dst):
    dst.objects = [C.HULL_OBJ]
src_ob = dst.objects[0]
assert src_ob is not None and src_ob.matrix_world == ob.matrix_world
sme = src_ob.data
visl = np.array(C.load_json(C.RESEARCH + '/sm_airship_vertex_parts.json')['vertex_island'])
assert len(visl) == len(sme.vertices) == C.deck_removals()['source_vertex_count']
KEEP = C.kept_vertex_index(visl)


def co_of(m):
    a = np.empty(len(m.vertices) * 3, np.float64); m.vertices.foreach_get('co', a)
    return a.reshape(-1, 3)


def uv_of(m):
    a = np.empty(len(m.loops) * 2, np.float64); m.uv_layers['UVMap'].data.foreach_get('uv', a)
    return a.reshape(-1, 2)


# the drivable mesh must be the source minus the removed islands, with the same UVs (what rig_build guarantees)
co_s, co_r = co_of(sme), co_of(me)
assert len(co_r) == len(KEEP), (len(co_r), len(KEEP))
assert np.abs(co_s[KEEP] - co_r).max() < 1e-6, 'rig SM_Airship positions differ from the source'
lv_s = np.empty(len(sme.loops), np.int64); sme.loops.foreach_get('vertex_index', lv_s)
kl = np.isin(lv_s, KEEP)
uv_s, uv_r = uv_of(sme), uv_of(me)
assert kl.sum() == len(uv_r) and np.abs(uv_s[kl] - uv_r).max() < 1e-7, 'rig SM_Airship UVs differ from the source'
log('drivable SM_Airship = source minus %d vertices, UVs identical' % (len(co_s) - len(co_r)))

# removed triangles (3D for the distance, UV for the texels we keep)
sme.calc_loop_triangles()
lt_v = np.empty(len(sme.loop_triangles) * 3, np.int64); sme.loop_triangles.foreach_get('vertices', lt_v)
lt_l = np.empty(len(sme.loop_triangles) * 3, np.int64); sme.loop_triangles.foreach_get('loops', lt_l)
lt_v, lt_l = lt_v.reshape(-1, 3), lt_l.reshape(-1, 3)
PIECES = C.deck_removals()['pieces']
piece_of_island = {i: k for k, p in enumerate(PIECES) for i in p['islands']}
tri_piece = np.array([piece_of_island.get(int(visl[t[0]]), -1) for t in lt_v])
REM_TRIS = np.nonzero(tri_piece >= 0)[0]
assert all(np.isin(visl[lt_v[REM_TRIS]], C.removed_islands()).ravel())
bvh_piece, box_piece = [], []
for k, p in enumerate(PIECES):
    tk = lt_v[tri_piece == k]
    used = np.unique(tk)
    remap = {int(v): i for i, v in enumerate(used)}
    bvh_piece.append(BVHTree.FromPolygons([V(c) for c in co_s[used]], [[remap[int(v)] for v in t] for t in tk],
                                          all_triangles=True))
    box_piece.append((co_s[used].min(0), co_s[used].max(0)))
    log('piece %d %-48s %4d tris, box %s..%s' % (p['arrow'], p['name'][:48], len(tk), np.round(box_piece[-1][0], 2),
                                                np.round(box_piece[-1][1], 2)))


def raster_uv_tris(tris_uv, res):
    """texels (row = v, bottom-up like Blender pixels) whose centre lies inside any of the UV triangles"""
    out = np.zeros((res, res), bool)
    for t in tris_uv * res - 0.5:          # texel (i, j) centre at ((j + .5) / res, (i + .5) / res)
        x0, y0 = np.floor(t.min(0)).astype(int); x1, y1 = np.ceil(t.max(0)).astype(int)
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, res - 1), min(y1, res - 1)
        if x1 < x0 or y1 < y0:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
        (ax, ay), (bx, by), (cx, cy) = t
        d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(d) < 1e-12:
            continue
        l1 = ((by - cy) * (gx - cx) + (cx - bx) * (gy - cy)) / d
        l2 = ((cy - ay) * (gx - cx) + (ax - cx) * (gy - cy)) / d
        ins = (l1 >= -1e-6) & (l2 >= -1e-6) & (1 - l1 - l2 >= -1e-6)
        out[y0:y1 + 1, x0:x1 + 1] |= ins
    return out


removed_uv = raster_uv_tris(uv_s[lt_l[REM_TRIS]], TEX)
log('removed islands cover %d texels in UV (kept as they are)' % removed_uv.sum())

# ------------------------------------------------------------------ bake setup (as comic_lines.py)
sc.render.engine = 'CYCLES'
dev = 'CPU'
if not CPU:
    prefs = bpy.context.preferences.addons['cycles'].preferences
    for dev_type in ('OPTIX', 'CUDA'):
        try:
            prefs.compute_device_type = dev_type
            prefs.get_devices()
            if any(d.type == dev_type for d in prefs.devices):
                break
        except TypeError:
            continue
    for d in prefs.devices:
        d.use = d.type != 'CPU'
    dev = 'GPU' if any(d.use for d in prefs.devices) else 'CPU'
sc.cycles.device = dev
sc.render.bake.margin = MARGIN
sc.render.bake.margin_type = 'EXTEND'
for c in bpy.data.collections:
    c.hide_render = False
stack = [bpy.context.view_layer.layer_collection]
while stack:                         # make sure SM_Airship's layer collections are on
    l = stack.pop()
    if ob.name in l.collection.objects:
        l.exclude = False; l.hide_viewport = False; l.collection.hide_viewport = False
    stack += list(l.children)
for m in ob.modifiers:               # the armature: bake the rest-pose mesh (= the source positions, checked above)
    m.show_render = False; m.show_viewport = False
sc.collection.objects.link(src_ob)   # Talal's mesh with the pieces, for the A/B bake (memory only)
log('cycles device', dev, '| seed', sc.cycles.seed, '| drivable', len(me.polygons), 'faces | source', len(sme.polygons), 'faces')


def only(target):
    """only target renders and is selected + active (comic_lines hid every other collection)"""
    for o in sc.objects:
        o.hide_render = o is not target
        try:
            o.select_set(o is target)
        except RuntimeError:         # not in the view layer
            pass
    target.hide_set(False); target.hide_viewport = False
    target.select_set(True)
    bpy.context.view_layer.objects.active = target


tex = nt.nodes.new('ShaderNodeTexImage'); tex.name = '_R2_BakeTarget'


def bake_mask(target):
    """comic_lines.py's bake + post-process on target -> (mask 0..1 float32, raw bake bytes, seconds)"""
    tm = target.data
    keep = tm.materials[0]
    tm.materials[0] = mc
    img = bpy.data.images.new('_r2_mask_raw', TEX, TEX)          # byte + Non-Color, like comic_lines' mask image
    img.colorspace_settings.name = 'Non-Color'
    try:
        only(target)
        tex.image = img
        nt.nodes.active = tex
        nt.links.new(nt.nodes['BakeMask'].outputs[0], nt.nodes['Out'].inputs['Surface'])
        sc.cycles.samples = SAMPLES
        t = time.time()
        bpy.ops.object.bake(type='EMIT', margin=MARGIN, use_clear=True)
        sec = round(time.time() - t, 1)
        px = np.empty(TEX * TEX * 4, np.float32)
        img.pixels.foreach_get(px)
    finally:
        tm.materials[0] = keep
        tex.image = None
        bpy.data.images.remove(img)
    # comic_lines.py post-process, verbatim
    m = px.reshape(TEX, TEX, 4)[:, :, 0].copy()
    raw = to_bytes(m)
    for _ in range(SMOOTH):
        for ax in (0, 1):
            m = (np.roll(m, 1, ax) + 2 * m + np.roll(m, -1, ax)) * 0.25
    lo, hi = INK_CUT
    t_ = np.clip((m - lo) / (hi - lo), 0.0, 1.0)
    m = t_ * t_ * (3 - 2 * t_)
    return m, raw, sec


paper = np.array([int(h, 16) / 255 for h in ('F3', 'EE', 'E4')], dtype=np.float32)
ink = np.array([int(h, 16) / 255 for h in ('1C', '22', '30')], dtype=np.float32)
mA, rawA, BAKE_S = bake_mask(ob)            # A: the drivable mesh (pieces removed)
log('A (drivable) mask baked (%d spp, %s) in %.1fs' % (SAMPLES, dev, BAKE_S))
new_lines = to_bytes(paper + (ink - paper) * mA[:, :, None])
new_mask = to_bytes(np.repeat(mA[:, :, None], 3, axis=2))
del mA
mB, rawB, BAKE_SB = bake_mask(src_ob)       # B: Talal's mesh as it is (pieces in place), same setup
log('B (source, pieces in place) mask baked in %.1fs' % BAKE_SB)
src_mask = to_bytes(mB)
del mB
effect = new_mask[:, :, 0] != src_mask      # what removing the pieces changes in the re-bake
only(ob)

# ------------------------------------------------------------------ position bake -> distance to the removed pieces
pm = bpy.data.materials.new('_R2_Position')
pm.use_nodes = True
pn = pm.node_tree
pn.nodes.clear()
geo = pn.nodes.new('ShaderNodeNewGeometry')
em = pn.nodes.new('ShaderNodeEmission')
po = pn.nodes.new('ShaderNodeOutputMaterial')
pn.links.new(geo.outputs['Position'], em.inputs['Color'])
pn.links.new(em.outputs[0], po.inputs['Surface'])
ptex = pn.nodes.new('ShaderNodeTexImage')
pos_img = bpy.data.images.new('_r2_pos', TEX, TEX, alpha=True, float_buffer=True)
pos_img.colorspace_settings.name = 'Non-Color'
pos_img.pixels.foreach_set(np.full(TEX * TEX * 4, SENTINEL, np.float32))   # untouched texels keep the sentinel
ptex.image = pos_img
pn.nodes.active = ptex
me.materials[0] = pm
sc.cycles.samples = 1
t = time.time()
bpy.ops.object.bake(type='EMIT', margin=MARGIN, use_clear=False)
log('position baked in %.1fs' % (time.time() - t))
pos = np.empty(TEX * TEX * 4, np.float32)
pos_img.pixels.foreach_get(pos)
pos = pos.reshape(TEX, TEX, 4)[:, :, :3]
covered = pos[:, :, 0] < SENTINEL * 0.5
me.materials[0] = bpy.data.materials['M_Airship']                    # (memory only; never saved)

dist = np.full((TEX, TEX), np.inf, np.float32)
dist_k = np.full((TEX, TEX), -1, np.int8)
for k, (bmin, bmax) in enumerate(box_piece):
    near = covered & np.all(pos > (bmin - STATS_R), axis=2) & np.all(pos < (bmax + STATS_R), axis=2)
    ii, jj = np.nonzero(near)
    tree = bvh_piece[k]
    d = np.array([np.inf if r is None else r for r in (tree.find_nearest(V(p), STATS_R)[3] for p in pos[ii, jj].tolist())],
                 np.float32)
    better = d < dist[ii, jj]
    dist[ii[better], jj[better]] = d[better]
    dist_k[ii[better], jj[better]] = k
    log('piece %d: %d texels within its box + %.1f m, %d within %.2f m' % (PIECES[k]['arrow'], len(ii), STATS_R,
                                                                           int((d < RADIUS).sum()), RADIUS))
zone = covered & (dist < RADIUS) & ~removed_uv
change = zone & effect                      # the texels the output takes from the re-bake
if DUMP:
    os.makedirs(DUMP, exist_ok=True)
    for nm, a in (('new_mask', new_mask[:, :, 0]), ('src_mask', src_mask), ('rawA', rawA), ('rawB', rawB), ('pos', pos),
                  ('dist', dist), ('dist_k', dist_k), ('covered', covered), ('removed_uv', removed_uv)):
        np.save(os.path.join(DUMP, nm + '.npy'), a)
    log('dumped arrays to', DUMP)

# ------------------------------------------------------------------ composite
old_lines = load_png_bytes(ORIG_LINES, False)
old_mask = load_png_bytes(ORIG_MASK, True)
out_lines = np.where(change[:, :, None], new_lines, old_lines)
out_mask = np.where(change[:, :, None], new_mask, old_mask)
changed = np.any(out_lines != old_lines, axis=2)
assert not np.any(changed & ~zone)


# ------------------------------------------------------------------ report
def diffstats(a, b, sel):
    n = int(sel.sum())
    if not n:
        return dict(texels=0)
    d = np.abs(a[sel].astype(np.int16) - b[sel].astype(np.int16))
    return dict(texels=n, identical=round(float((d == 0).mean()), 5), mean_abs=round(float(d.mean()), 3),
                over_32=int((d > 32).sum()), over_128=int((d > 128).sum()), max=int(d.max()))


def png_box(sel):
    """texel box in PNG coordinates (x right, y down from the top row)"""
    r, c = np.nonzero(sel)
    if not len(r):
        return None
    return [int(c.min()), int(TEX - 1 - r.max()), int(c.max()), int(TEX - 1 - r.min())]


def components(sel):
    """8-connected groups of texels: list of (rows, cols)"""
    r, c = np.nonzero(sel)
    r, c = r.tolist(), c.tolist()
    idx = {(a, b): i for i, (a, b) in enumerate(zip(r, c))}
    lab = [-1] * len(r)
    out = []
    for s0 in range(len(r)):
        if lab[s0] >= 0:
            continue
        lab[s0] = len(out)
        stack, mem = [s0], []
        while stack:
            i = stack.pop()
            mem.append(i)
            for da in (-1, 0, 1):
                for db in (-1, 0, 1):
                    j = idx.get((r[i] + da, c[i] + db))
                    if j is not None and lab[j] < 0:
                        lab[j] = lab[s0]
                        stack.append(j)
        out.append((np.array([r[i] for i in mem]), np.array([c[i] for i in mem])))
    return out


old_m, new_m, src_m, out_m = old_mask[:, :, 0], new_mask[:, :, 0], src_mask, out_mask[:, :, 0]
used = covered & ~removed_uv
rings = [(0.0, 0.25), (0.25, 0.5), (0.5, 1.0), (1.0, 1.2), (1.2, RADIUS), (RADIUS, 2.0), (2.0, STATS_R)]
inring = lambda r: used & (dist >= r[0]) & (dist < r[1])
groups = []
for rr, cc in components(changed):
    ks = dist_k[rr, cc]
    k = int(np.bincount(ks[ks >= 0], minlength=len(PIECES)).argmax()) if (ks >= 0).any() else -1
    sel = np.zeros((TEX, TEX), bool); sel[rr, cc] = True
    groups.append(dict(piece=PIECES[k]['arrow'] if k >= 0 else None, texels=int(len(rr)), png_box=png_box(sel),
                       centre_m=[round(float(v), 2) for v in pos[rr, cc].mean(0)],
                       dist_m=[round(float(dist[rr, cc].min()), 2), round(float(dist[rr, cc].max()), 2)],
                       ink_to_paper=int((out_m[rr, cc] < old_m[rr, cc]).sum()),
                       paper_to_ink=int((out_m[rr, cc] > old_m[rr, cc]).sum())))
groups.sort(key=lambda g: -g['texels'])
report = dict(
    about='T_AirshipDrivable_ComicLines = Talal\'s T_Airship_ComicLines with the re-baked ink on the texels where '
          'removing the five deck pieces changes the bake (A/B re-bake: drivable mesh vs his mesh, same setup), '
          'limited to the drivable mesh\'s texels closer than radius_m to a removed piece. Every other texel is the '
          'original byte for byte.',
    inputs=INPUT_MD5, output=OUT_LINES, size=[TEX, TEX], format='PNG 8-bit RGB (as the original)',
    radius_m=RADIUS, bake=dict(samples=SAMPLES, margin_px=MARGIN, device=dev, seed=sc.cycles.seed,
                               seconds_drivable=BAKE_S, seconds_source=BAKE_SB),
    texels_total=TEX * TEX, texels_drivable_incl_padding=int(covered.sum()),
    texels_removed_islands_kept=int(removed_uv.sum()), texels_zone=int(zone.sum()),
    texels_changed=int(changed.sum()), texels_changed_by_more_than_32=int((np.abs(out_m.astype(np.int16) - old_m) > 32).sum()),
    texels_changed_ink_to_paper=int((changed & (out_m < old_m)).sum()),
    texels_changed_paper_to_ink=int((changed & (out_m > old_m)).sum()),
    changed_png_box=png_box(changed),
    removal_effect_outside_zone=int((effect & used & ~zone).sum()),
    removal_effect_by_distance={'%.2f-%.2f m' % r: int((effect & inring(r)).sum()) for r in rings},
    rebake_vs_original_by_distance={'%.2f-%.2f m' % r: diffstats(src_m, old_m, inring(r)) for r in rings},
    rebake_vs_original_all=diffstats(src_m, old_m, covered & ~removed_uv),
    zone_texels_kept_although_rebake_differs=int((zone & ~effect & (new_m != old_m)).sum()),
    notes=['rebake_vs_original: B (Talal\'s mesh, pieces in place, this setup) vs his T_Airship_ComicMask, mask 0-255: '
           'how exactly the re-bake reproduces his bake. The differences away from the pieces (bow underside etc.) are '
           'edits to SM_Airship after his 2026-10-31 14:04 bake; they are not touched here.',
           'removal_effect: texels where A (drivable) != B (source); beyond the shader\'s 1.2 m AO reach it must be ~0.',
           'png_box = [x0, y0, x1, y1] in the PNG (y down from the top row); centre_m = Blender metres (+X bow, +Y port).'],
    pieces=[], groups=[g for g in groups if g['texels'] >= 20],
    groups_small=dict(count=sum(1 for g in groups if g['texels'] < 20),
                      texels=sum(g['texels'] for g in groups if g['texels'] < 20)))
for k, p in enumerate(PIECES):
    sel_z = zone & (dist_k == k)
    sel_c = changed & (dist_k == k)
    under = sel_z & (dist < 0.05)
    report['pieces'].append(dict(
        arrow=p['arrow'], name=p['name'], texels_zone=int(sel_z.sum()), texels_changed=int(sel_c.sum()),
        groups=sum(1 for g in groups if g['piece'] == p['arrow']),
        lum_under_before=round(float(old_lines[under].mean() / 255.0), 3) if under.any() else None,
        lum_under_after=round(float(out_lines[under].mean() / 255.0), 3) if under.any() else None,
        ink_share_in_zone_before=round(float((old_m[sel_z] > 127).mean()), 4) if sel_z.any() else None,
        ink_share_in_zone_after=round(float((out_m[sel_z] > 127).mean()), 4) if sel_z.any() else None))
os.makedirs(CHECK, exist_ok=True)
save_png_bytes(OUT_LINES, out_lines, False)
save_png_bytes(CHECK + '/T_AirshipDrivable_ComicMask.png', out_mask, True)
# where: grey = drivable texels, blue = zone, red = changed (1024, max over 4 x 4 blocks; PNG orientation)
s = TEX // 1024
blk = lambda a: a.reshape(1024, s, 1024, s).max(axis=(1, 3))
pv = np.full((1024, 1024, 3), 255, np.uint8)
pv[blk(covered)] = (205, 205, 205)
pv[blk(zone)] = (70, 120, 230)
pv[blk(changed)] = (230, 30, 30)
save_png_bytes(CHECK + '/zone_preview.png', pv, False)
report['output_md5'] = md5(OUT_LINES)
report['seconds'] = round(time.time() - T0, 1)
with open(CHECK + '/hull_ink_report.json', 'w') as f:
    json.dump(report, f, indent=1)
log('zone %d texels, changed %d (%.3f%% of the texture; %d ink->paper, %d paper->ink); removal effect outside the zone %d'
    % (report['texels_zone'], report['texels_changed'], 100.0 * report['texels_changed'] / TEX / TEX,
       report['texels_changed_ink_to_paper'], report['texels_changed_paper_to_ink'], report['removal_effect_outside_zone']))
for p in report['pieces']:
    log('PIECE %d changed %6d in %d groups | deck under it lum %s -> %s | ink share in zone %s -> %s' % (
        p['arrow'], p['texels_changed'], p['groups'], p['lum_under_before'], p['lum_under_after'],
        p['ink_share_in_zone_before'], p['ink_share_in_zone_after']))
for g in report['groups'][:25]:
    log('GROUP', g)
log('small groups', report['groups_small'])
for r in report['removal_effect_by_distance']:
    log('RING %-12s removal effect %7d | rebake vs original %s' % (r, report['removal_effect_by_distance'][r],
                                                                   report['rebake_vs_original_by_distance'][r]))
log('rebake vs original, all drivable texels', report['rebake_vs_original_all'])
log('report', CHECK + '/hull_ink_report.json')
