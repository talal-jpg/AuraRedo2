"""Round 3 export, step 2: bake the ink textures (Docs/Airship/round3/EXPORT_R3.md section 3).

  BL_MEM_MAX=6G blender_capped.sh --python SourceArt/Airship/scripts/r3_bake.py -- [--cpu] [--pages hull,H,M,P]
      [--dmax 0.12] [--dot-r 0.018] [--out DIR] [--compare REPORT.json]
  --out: texture folder (default rig/detail/r3export/textures); --compare: an earlier r3_bake_report.json, prints
  SAME / DIFF per texture md5 (the determinism check: run again with --out .../textures_det --compare ...).

Opens rig/detail/r3export/AirshipR3_export.blend (r3_prep.py; never saved). Per page:
  hull  T_AirshipR3_HullInk.png      4096, SM_Airship's own atlas in UV2 'R3Ink' (r3_prep --hull-uv atlas)
  H     T_AirshipR3_DetailInk_H.png  4096, SM_AirshipR3_HullDetail's atlas
  M     T_AirshipR3_DetailInk_M.png  4096, SM_AirshipR3Detail_Moving's atlas
  P     T_AirshipR3_PropsInk.png     2048, the props atlas (one cannon, the helm, the turret base and gun: the four
                                     cannons share one set of UVs; the turrets use the same atlas)
 1. r3_raster.py rasterises the page's atlas faces (numpy, deterministic, no GPU): owner triangle, 3D position (on
    the triangle's plane, extrapolated up to --margin-px 8 texels past it) and nearest edge of every texel. Rivet,
    hidden, thin and plate-side faces have their UVs in the reserved blocks. (bake_pos_fid below is the spike's Cycles
    route, kept for reference and not used.)
 2. Feature edges on the page's mesh (r3_sdf.feature_segments): creases over --crease (hull 35, details 60, props 45
    degrees), palette-class boundaries, open borders, front contours (face attribute r3_cap from r3_prep).
 3. R = signed distance: (d + dneg) / (dmax + dneg), 0..1 = -2..12 cm. d = distance to the nearest feature edge of the
    texel's own piece within dmax of its face (r3_sdf.face_lists_piece / distance_map_n, with a behind-the-face test);
    in the margin beyond a feature edge at an island border d is negative, so lines there stay crisp at any width.
 4. G = rivet dots: every rivet head (r3_kind 1, one loose piece) is projected along its axis onto the surface under
    it; the texels of that page within --dot-r of the foot point get a dot (anti-aliased by half a texel).
 5. B = 0. Talal's comic mask (round 2's T_AirshipDrivable_ComicMask.png) is its own texture on SM_Airship's UV0
    (only when --hull-uv talal was used in r3_prep does it go into the hull page's B).
 6. Reserved blocks (detail pages and the hull's R3Ink atlas): BLANK top right (d = dmax), plate sides top left
    (d = --side-d 1.5 cm: colour up close, ink once a line is wider).
 7. 8-bit RGB PNGs (linear) + rig/detail/r3export/checks/r3_bake_report.json (densities, coverage, features, dots,
    seam continuity, md5s, protected md5 at start and end).
Seam check: for every UV seam edge between two textured faces, R is sampled (bilinear) at 3 points of the edge in
both faces' UVs; the same 3D point should give the same distance on both sides. Reported as |difference| in cm and
as the share of samples where one side draws ink and the other does not (line half widths 0.5 / 2 / 6 cm).
"""
import bpy, sys, os, json, math, time
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np
from mathutils import Vector as V, Matrix
from mathutils.bvhtree import BVHTree
import r3_common as RC
import r3_sdf as S
import r3_raster as RR

A = RC.argv()
CPU = '--cpu' in A
PAGES = RC.arg(A, '--pages', 'hull,H,M,P').split(',')
DMAX = RC.arg(A, '--dmax', 0.12, float)
DOT_R = RC.arg(A, '--dot-r', 0.018, float)
DOT_R_HULL = RC.arg(A, '--dot-r-hull', 0.012, float)   # review fix (EXPORT_R3 15): the hull page (36 texels/m) blurred a
                                                       # 1.8 cm dot into a halo wider than the head; 0.018 = pass 1
OUTD = RC.arg(A, '--out', RC.TEX_DIR)
COMPARE = RC.arg(A, '--compare', '')
DNEG = RC.arg(A, '--dneg', 0.02, float)                 # stored range below 0 (signed margins beyond feature edges)
MPX = RC.arg(A, '--margin-px', 8, int)                  # texels of extrapolated margin round every island
LISTS = RC.arg(A, '--lists', 'piece')                   # piece (production) | ring (the spike's 1-ring rule)
BEHIND = RC.arg(A, '--behind', 0.7, float)
SIDE_D = RC.arg(A, '--side-d', 0.015, float)           # thin plate sides (INK block): ink once a line is wider than this
CREASE = {'hull': RC.arg(A, '--crease-deg', 42.0, float), 'H': RC.arg(A, '--box-deg', 60.0, float),
          'M': RC.arg(A, '--box-deg', 60.0, float), 'P': RC.arg(A, '--prop-deg', 45.0, float)}
MARGIN = 12
SENT = 1.0e6
log = RC.Log('r3_bake')
RC.check_out_path(OUTD + '/x')
os.makedirs(OUTD, exist_ok=True)
os.makedirs(RC.CHECK_DIR, exist_ok=True)
rep = dict(started=time.strftime('%Y-%m-%d %H:%M:%S'), protected_start=RC.protected_state(),
           export_blend=RC.EXPORT_BLEND, export_blend_md5=RC.md5_file(RC.EXPORT_BLEND),
           knobs=dict(dmax=DMAX, dneg=DNEG, side_d=SIDE_D, dot_r=DOT_R, dot_r_hull=DOT_R_HULL, crease=CREASE, margin_px=MPX, lists=LISTS, behind=BEHIND,
                      encoding='R = (d + dneg) / (dmax + dneg), d in metres (negative beyond a feature edge)'), pages={})

bpy.ops.wm.open_mainfile(filepath=RC.EXPORT_BLEND)
sc = bpy.context.scene
arm = bpy.data.objects['Armature']
for pb in arm.pose.bones:
    pb.matrix_basis = Matrix.Identity(4)
bpy.context.view_layer.update()
bcoll = bpy.data.collections.new('R3_Bake')
sc.collection.children.link(bcoll)
PROP_SET = ['SM_AirshipProp_Cannon_L1_' + p for p in ('Barrel', 'Carriage', 'Quoin', 'Wheel_BL', 'Wheel_BR',
                                                     'Wheel_FL', 'Wheel_FR')] + \
           ['SM_AirshipProp_Helm_Pedestal', 'SM_AirshipProp_Helm_Wheel'] + list(RC.TURRETS.values())


def page_objects(pg):
    return [bpy.data.objects[n] for n in (RC.PAGES[pg]['objects'] or PROP_SET)]


def bake_copy(objs, name):
    """one mesh in world space (rest pose, no modifiers) from the page's objects, face attributes kept"""
    import bmesh
    bm = bmesh.new()
    for o in objs:
        m = o.data.copy()
        m.transform(o.matrix_world)
        bm.from_mesh(m)
        bpy.data.meshes.remove(m)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bcoll.objects.link(ob)
    return ob


# ------------------------------------------------------------------ Cycles
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
sc.cycles.samples = 1
sc.cycles.use_denoising = False
sc.cycles.seed = 0
sc.render.bake.margin = MARGIN
sc.render.bake.margin_type = 'EXTEND'
rep['device'] = dev
log('cycles device', dev)


def emit_mat(name, kind, img):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    em = nt.nodes.new('ShaderNodeEmission'); out = nt.nodes.new('ShaderNodeOutputMaterial')
    if kind == 'pos':
        src = nt.nodes.new('ShaderNodeNewGeometry').outputs['Position']
    else:
        at = nt.nodes.new('ShaderNodeAttribute'); at.attribute_type = 'GEOMETRY'; at.attribute_name = 'r3_fid'
        src = at.outputs['Fac']
    nt.links.new(src, em.inputs['Color']); nt.links.new(em.outputs[0], out.inputs['Surface'])
    tx = nt.nodes.new('ShaderNodeTexImage'); tx.image = img
    nt.nodes.active = tx
    return m


def float_img(name, size, fill):
    im = bpy.data.images.new(name, size, size, alpha=True, float_buffer=True)
    im.colorspace_settings.name = 'Non-Color'
    im.pixels.foreach_set(np.full(size * size * 4, fill, np.float32))
    return im


def read_img(im, ch):
    s_ = im.size[0]
    a_ = np.empty(s_ * s_ * 4, np.float32); im.pixels.foreach_get(a_)
    return a_.reshape(s_, s_, 4)[:, :, :ch].copy()


def bake_pos_fid(ob, target_faces, size):
    """(pos (H,W,3), fid (H,W) int, covered (H,W) bool) of the target faces' texels"""
    me = ob.data
    RC.face_attr_set(me, 'r3_fid', np.arange(len(me.polygons)), kind='FLOAT')
    dummy = bpy.data.images.new('_r3_dummy', 8, 8, float_buffer=True); dummy.colorspace_settings.name = 'Non-Color'
    out = {}
    for kind, fill in (('pos', SENT), ('fid', -1.0)):
        img = float_img('_r3_' + kind, size, fill)
        me.materials.clear()
        me.materials.append(emit_mat('_r3_t_' + kind, kind, img))
        me.materials.append(emit_mat('_r3_d_' + kind, kind, dummy))
        me.polygons.foreach_set('material_index', np.where(target_faces, 0, 1).astype(np.int32))
        for o in sc.objects:
            o.hide_render = o is not ob
        for o in bpy.context.view_layer.objects:
            o.select_set(o is ob)
        bpy.context.view_layer.objects.active = ob
        t = time.time()
        bpy.ops.object.bake(type='EMIT', margin=MARGIN, margin_type='EXTEND', use_clear=False)
        out[kind] = read_img(img, 3 if kind == 'pos' else 1)
        out[kind + '_s'] = round(time.time() - t, 1)
        bpy.data.images.remove(img)
    bpy.data.images.remove(dummy)
    pos = out['pos']
    fid = np.round(out['fid'][:, :, 0]).astype(np.int64)
    cov = (pos[:, :, 0] < SENT * 0.5) & (fid >= 0)
    return pos, fid, cov, (out['pos_s'], out['fid_s'])


def bilinear(img, uv):
    """bilinear sample of img (H,W) at uv (N,2) in 0..1 (texel centres at (i + .5) / res), clamped"""
    H, W = img.shape
    x = np.clip(uv[:, 0] * W - 0.5, 0, W - 1.001); y = np.clip(uv[:, 1] * H - 0.5, 0, H - 1.001)
    x0 = np.floor(x).astype(np.int64); y0 = np.floor(y).astype(np.int64)
    fx = x - x0; fy = y - y0
    a = img[y0, x0] * (1 - fx) + img[y0, x0 + 1] * fx
    b = img[y0 + 1, x0] * (1 - fx) + img[y0 + 1, x0 + 1] * fx
    return a * (1 - fy) + b * fy


def seam_check(me, faces_ok, R, density, uvname):
    """distance continuity across UV seams between textured faces (metres)"""
    d = RC.mesh_np(me)
    uv = RC.uv_get(me, uvname)
    nxt = np.arange(len(d['lv'])) + 1
    nxt[d['ls'] + d['lt'] - 1] = d['ls']
    L = np.nonzero(faces_ok[d['lp']])[0]
    a, b = d['lv'][L], d['lv'][nxt[L]]
    key = np.minimum(a, b) * (len(d['co']) + 1) + np.maximum(a, b)
    o = np.argsort(key, kind='stable'); ks = key[o]
    same = np.nonzero(ks[1:] == ks[:-1])[0]
    i, j = L[o[same]], L[o[same + 1]]
    # loop i: v -> w; loop j: w -> v (consistent winding) or v -> w
    vi, wi = d['lv'][i], d['lv'][nxt[i]]
    sj = d['lv'][j] == vi
    uj_v = np.where(sj[:, None], uv[j], uv[nxt[j]]); uj_w = np.where(sj[:, None], uv[nxt[j]], uv[j])
    ui_v, ui_w = uv[i], uv[nxt[i]]
    seam = (np.abs(ui_v - uj_v).max(1) > 1e-6) | (np.abs(ui_w - uj_w).max(1) > 1e-6)
    out = dict(seam_edges=int(seam.sum()))
    if not seam.any():
        return out
    dif = []
    for t in (0.25, 0.5, 0.75):
        pa = ui_v[seam] * (1 - t) + ui_w[seam] * t
        pb = uj_v[seam] * (1 - t) + uj_w[seam] * t
        da = bilinear(R, pa); db = bilinear(R, pb)
        dif.append(np.stack([da, db], 1))
    dd = np.concatenate(dif)
    ad = np.abs(dd[:, 0] - dd[:, 1]) * 100.0
    out.update(samples=int(len(dd)), abs_diff_cm={str(p): round(float(np.percentile(ad, p)), 3) for p in (50, 95, 99, 99.9)},
               max_cm=round(float(ad.max()), 2), over_1cm=int((ad > 1.0).sum()), over_2cm=int((ad > 2.0).sum()))
    tol = max(0.01, 1.5 / max(density, 1.0))        # 1 cm, or 1.5 texels (sampling at the island edge)
    out['tolerance_cm'] = round(tol * 100, 2)
    for w in (0.005, 0.02, 0.06):
        ink_a, ink_b = dd[:, 0] < w, dd[:, 1] < w
        # a real mismatch: one side inked, the other clearly not (more than the tolerance past the line edge)
        mis = (ink_a & (dd[:, 1] > w + tol)) | (ink_b & (dd[:, 0] > w + tol))
        out['ink_mismatch_halfwidth_%gcm' % (w * 100)] = dict(samples=int(mis.sum()), share=round(float(mis.mean()), 5))
    return out


# ------------------------------------------------------------------ rivets: foot points and the page under them
t0 = time.time()
own_co, own_tri, own_page, own_face = [], [], [], []
off = 0
for pg, name in (('hull', RC.HULL_OBJ), ('H', RC.HULLDET), ('M', RC.MOVING)):
    me = bpy.data.objects[name].data
    d = RC.mesh_np(me)
    kind = RC.face_attr_get(me, 'r3_kind')
    ok = np.ones(len(d['ls']), bool) if kind is None else kind != RC.K_RIVET
    _, tv_, tp_ = RC.tri_arrays(me)
    k_ = ok[tp_]
    own_co.append(d['co'])
    own_tri.append(tv_[k_] + off)
    own_page += [pg] * int(k_.sum()); own_face.append(tp_[k_])
    off += len(d['co'])
own_face = np.concatenate(own_face)
obvh = BVHTree.FromPolygons(np.vstack(own_co).tolist(), np.vstack(own_tri).tolist(), all_triangles=True)
del own_tri
RIVETS = {'hull': [], 'H': [], 'M': [], 'P': []}
rv_stat = dict(pieces=0, no_hit=0, on_textured_face=0, on_blank_face=0, by_page={})
kinds_of = {pg: RC.face_attr_get(bpy.data.objects[n].data, 'r3_kind') for pg, n in (('H', RC.HULLDET), ('M', RC.MOVING),
                                                                                    ('hull', RC.HULL_OBJ))}
for name in (RC.HULLDET, RC.MOVING):
    me = bpy.data.objects[name].data
    d = RC.mesh_np(me)
    kind = RC.face_attr_get(me, 'r3_kind')
    rf = np.nonzero(kind == RC.K_RIVET)[0]
    piece = S.pieces(len(d['co']), d['ls'], d['lt'], d['lv'])
    order = np.argsort(piece[rf], kind='stable')
    rfs = rf[order]; pcs = piece[rfs]
    cut = np.nonzero(np.diff(pcs))[0] + 1
    for faces in np.split(rfs, cut):
        rv_stat['pieces'] += 1
        vs = np.unique(np.concatenate([d['lv'][d['ls'][p]:d['ls'][p] + d['lt'][p]] for p in faces]))
        c = d['co'][vs].mean(0)
        n = d['fn'][faces[np.argmax(d['fa'][faces])]]
        best = None
        for s in (1.0, -1.0):
            hit, nrm, idx, dist_ = obvh.ray_cast(V(c), V(n * s), 0.08)
            if hit is not None and (best is None or dist_ < best[3]):
                best = (hit, nrm, idx, dist_)
        if best is None:
            rv_stat['no_hit'] += 1
            continue
        pg, fq = own_page[best[2]], own_face[best[2]]
        textured = kinds_of[pg] is None or kinds_of[pg][fq] == RC.K_ATLAS
        rv_stat['on_textured_face' if textured else 'on_blank_face'] += 1
        rv_stat['by_page'][pg] = rv_stat['by_page'].get(pg, 0) + 1
        if textured:
            RIVETS[pg].append((np.array(best[0]), np.array(best[1])))
rv_stat['seconds'] = round(time.time() - t0, 1)
rep['rivets'] = rv_stat
log('rivets', rv_stat)
del obvh


def stamp_dots(pos, cov, size, density, rivets, dot_r=None):
    dot_r = DOT_R if dot_r is None else dot_r
    dots = np.zeros(size * size, np.float32)
    if not rivets:
        return dots.reshape(size, size), 0
    P = pos[cov]
    idx = np.nonzero(cov.ravel())[0]
    CELL = 0.05
    key = np.floor(P / CELL).astype(np.int64)
    h = (key[:, 0] * 73856093) ^ (key[:, 1] * 19349663) ^ (key[:, 2] * 83492791)
    order = np.argsort(h, kind='stable'); hs = h[order]
    aa = 0.5 / max(density, 1.0)
    n_ok = 0
    for foot, n in rivets:
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
            continue
        cand = np.concatenate(cand)
        rel = P[cand] - foot
        along = rel @ n
        inpl = np.linalg.norm(rel - np.outer(along, n), axis=1)
        v = np.clip((dot_r + aa - inpl) / (2 * aa), 0, 1) * (np.abs(along) < 0.03)
        if v.max() > 0:
            n_ok += 1
        ii = idx[cand]
        dots[ii] = np.maximum(dots[ii], v)
    return dots.reshape(size, size), n_ok


def save_png(path, rgb):
    size = rgb.shape[0]
    img = bpy.data.images.new(os.path.basename(path)[:-4], size, size)
    img.colorspace_settings.name = 'Non-Color'
    px = np.ones((size, size, 4), np.float32); px[:, :, :3] = rgb
    img.pixels.foreach_set(px.ravel())
    sc.render.image_settings.file_format = 'PNG'
    sc.render.image_settings.color_mode = 'RGB'
    sc.render.image_settings.color_depth = '8'
    sc.render.image_settings.compression = 90
    img.save_render(RC.check_out_path(path), scene=sc)
    bpy.data.images.remove(img)


manifest = RC.load_json(RC.MANIFEST)
# ------------------------------------------------------------------ pages
for pg in PAGES:
    t_page = time.time()
    cfg = RC.PAGES[pg]
    size = cfg['size']
    objs = page_objects(pg)
    ob = bake_copy(objs, '_r3_bake_' + pg)
    me = ob.data
    d = RC.mesh_np(me)
    nP = len(d['ls'])
    kind = RC.face_attr_get(me, 'r3_kind')
    if kind is None or pg == 'P':
        kind = np.zeros(nP, np.int32)
    pal = RC.face_attr_get(me, 'r3_pal')
    cap = RC.face_attr_get(me, 'r3_cap')
    atlas = kind == RC.K_ATLAS
    t = time.time()
    tl, tv, tp = RC.tri_arrays(me)
    uvname = RC.page_uv(me, pg)
    uvl = RC.uv_get(me, uvname)
    kt = atlas[tp]
    t_uv, t_co, t_face, t_vv = uvl[tl[kt]], d['co'][tv[kt]], tp[kt], tv[kt]
    owner, inside, nedge = RR.raster(t_uv, size, MPX)
    cov = owner >= 0
    pos = RR.positions(t_uv, t_co, owner, size)
    fid = np.where(cov, t_face[np.maximum(owner, 0)], -1)
    bake_s = round(time.time() - t, 1)
    log('%s: rasterised %d triangles (%s s), %d texels inside, %d in the margin' % (pg, kt.sum(), bake_s, inside.sum(),
                                                                                   (cov & ~inside).sum()))
    # feature edges (rivets take no part)
    t = time.time()
    segs, sv, fcount = S.feature_segments(d['co'], d['ls'], d['lt'], d['lv'], None, d['fn'], pal.astype(np.int64),
                                          crease_deg=CREASE[pg], cap=cap.astype(np.int64),
                                          faces_ok=kind != RC.K_RIVET)
    if LISTS == 'ring':
        csr = S.face_lists(d['ls'], d['lt'], d['lv'], sv, len(d['co']))
        dist = S.distance_map(fid, pos, cov, csr, segs, DMAX, faces_ok=atlas)
    else:
        piece = S.pieces(len(d['co']), d['ls'], d['lt'], d['lv'])
        csr = S.face_lists_piece(d['co'], d['ls'], d['lt'], d['lv'], sv, piece, DMAX, faces_ok=atlas)
        dist = S.distance_map_n(fid, pos, cov, csr, segs, DMAX, d['fn'], faces_ok=atlas, behind=BEHIND)
    # signed margins: an outside texel whose nearest triangle edge is a feature edge lies beyond the line
    nv = len(d['co']) + 1
    fkey = np.sort(np.minimum(sv[:, 0], sv[:, 1]) * nv + np.maximum(sv[:, 0], sv[:, 1]))
    oi = np.nonzero((cov & ~inside).ravel())[0]
    ot = owner.ravel()[oi]; oe = nedge.ravel()[oi].astype(np.int64)
    va = t_vv[ot, oe]; vb = t_vv[ot, (oe + 1) % 3]
    ek = np.minimum(va, vb) * nv + np.maximum(va, vb)
    j = np.clip(np.searchsorted(fkey, ek), 0, max(len(fkey) - 1, 0))
    isf = (fkey[j] == ek) if len(fkey) else np.zeros(len(ek), bool)
    Pp = pos.reshape(-1, 3)[oi[isf]]
    A_, B_ = d['co'][va[isf]], d['co'][vb[isf]]
    AB = B_ - A_
    tt = np.clip(((Pp - A_) * AB).sum(1) / np.maximum((AB * AB).sum(1), 1e-18), 0, 1)
    dneg = np.linalg.norm(Pp - (A_ + tt[:, None] * AB), axis=1)
    dist = dist.ravel()
    dist[oi[isf]] = -np.minimum(dneg, DNEG)
    dist = dist.reshape(size, size)
    t_sdf = round(time.time() - t, 1)
    # density of this page (median over atlas faces)
    dens, a3 = RC.texel_density(uvl, d['co'], tl, tv, atlas[tp], size)
    dmed = float(np.interp(0.5, np.cumsum(a3[np.argsort(dens)]) / a3.sum(), np.sort(dens))) if len(dens) else 0.0
    dots, n_dot = stamp_dots(pos, cov, size, dmed, RIVETS.get(pg, []), DOT_R_HULL if pg == 'hull' else DOT_R)
    R = (np.clip(dist, -DNEG, DMAX) + DNEG) / (DMAX + DNEG)
    G = dots
    B = np.zeros((size, size), np.float32)
    comic = None
    if pg == 'hull' and uvname != RC.UV_INK:
        comic = dict(source=RC.HULL_MASK_R2, uv=RC.UV_INK, note='own texture on UV0 (Talal\'s UVs); B of this page is 0')
    elif pg == 'hull' and os.path.isfile(RC.HULL_MASK_R2):
        mi = bpy.data.images.load(RC.HULL_MASK_R2, check_existing=False)
        mi.colorspace_settings.name = 'Non-Color'
        assert tuple(mi.size) == (size, size)
        B = read_img(mi, 1)[:, :, 0]
        bpy.data.images.remove(mi)
        comic = dict(source=RC.HULL_MASK_R2, md5=RC.md5_file(RC.HULL_MASK_R2), ink_share=round(float((B > 0.5).mean()), 4))
    if pg in ('H', 'M') or (pg == 'hull' and uvname != RC.UV_INK):
        bl = RC.BLOCK
        R[size - bl:, size - bl:] = 1.0; G[size - bl:, size - bl:] = 0.0          # BLANK (top right): d = dmax
        R[size - bl:, :bl] = (SIDE_D + DNEG) / (DMAX + DNEG); G[size - bl:, :bl] = 0.0   # INK sides (top left): d = side_d
    rgb = np.stack([R, G, B], 2).astype(np.float32)
    path = os.path.join(OUTD, cfg['tex'])
    save_png(path, rgb)
    seam = seam_check(me, atlas, dist, dmed, uvname)
    near = inside & (dist < 0.01)
    rep['pages'][pg] = dict(
        texture=path, md5=RC.md5_file(path), size=size, uv=uvname, objects=[o.name for o in objs], faces=nP,
        atlas_faces=int(atlas.sum()), inside_texels=int(inside.sum()), margin_texels=int((cov & ~inside).sum()),
        signed_margin_texels=int(isf.sum()), coverage=round(float(inside.mean()), 4),
        density_median=round(dmed, 1), density=RC.weighted_pct(dens, a3), features=fcount,
        ink_texels_lt_1cm=int(near.sum()), ink_share_of_inside=round(float(near.sum() / max(inside.sum(), 1)), 4),
        rivets_dotted=n_dot, rivets_assigned=len(RIVETS.get(pg, [])), dot_texels=int((G > 0.5).sum()),
        comic_B=comic, seams=seam, seconds=dict(bake=bake_s, sdf=t_sdf, total=round(time.time() - t_page, 1)))
    log('%s: %s' % (pg, json.dumps({k: rep['pages'][pg][k] for k in ('density_median', 'features', 'rivets_dotted',
                                                                       'ink_share_of_inside', 'seams')})))
    del pos, fid, cov, dist, R, G, B, rgb, owner, inside, nedge
    bpy.data.objects.remove(ob)

if COMPARE:
    old = RC.load_json(COMPARE)
    cmp_ = {pg: ('SAME' if old['pages'].get(pg, {}).get('md5') == v['md5'] else 'DIFF') for pg, v in rep['pages'].items()}
    rep['compare'] = dict(against=COMPARE, result=cmp_)
    log('compare', cmp_)
if OUTD == RC.TEX_DIR and set(PAGES) != set(RC.PAGES) and os.path.isfile(RC.CHECK_DIR + '/r3_bake_report.json'):
    # a partial re-bake (--pages): keep the other pages' entries of the last full report, so the report stays whole
    _old = RC.load_json(RC.CHECK_DIR + '/r3_bake_report.json')
    for _pg, _v in _old.get('pages', {}).items():
        if _pg not in rep['pages']:
            _v = dict(_v); _v['from_previous_run'] = _old.get('started', True)
            rep['pages'][_pg] = _v
    rep['partial_rebake'] = dict(pages=PAGES, kept_from_previous=[p_ for p_ in _old.get('pages', {}) if p_ not in PAGES])
    for _k in ('rivets',):
        rep.setdefault(_k, _old.get(_k))
rep['protected_end'] = RC.protected_state()
rep['protected_unchanged'] = all(rep['protected_start'][k]['md5'] == v['md5'] for k, v in rep['protected_end'].items())
rep['seconds'] = round(time.time() - log.t0, 1)
rname = 'r3_bake_report.json' if OUTD == RC.TEX_DIR else 'r3_bake_report_%s.json' % os.path.basename(OUTD.rstrip('/'))
RC.dump_json(rep, RC.CHECK_DIR + '/' + rname)
log('done; protected unchanged:', rep['protected_unchanged'])
sys.stdout.flush()
os._exit(0)
