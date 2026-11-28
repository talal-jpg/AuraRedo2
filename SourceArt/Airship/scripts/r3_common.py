"""Round 3 export: shared constants and helpers for r3_prep.py, r3_bake.py, r3_preview.py, r3_checks.py
(Docs/Airship/round3/EXPORT_R3.md sections 2-5).

Blender world metres: +X bow, +Y port, +Z up (rig_common). Everything written goes under rig/detail/r3export/ (Blender
side) or Docs/Airship/round3/ (reports, media). Talal's files are only read.
"""
import os, json, hashlib, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
BLENDER_ROOT = '/mnt/new_partition/BlenderProjects/StylizedAirship'
RIG_DIR = BLENDER_ROOT + '/rig'
RIG_BLEND = RIG_DIR + '/AirshipRig.blend'                      # read only (the rig: SM_Airship part classes)
FULL_BLEND = RIG_DIR + '/detail/zones/AirshipRig_detail_full.blend'   # read only (the assembled detail pass)
FULL_HASH = RIG_DIR + '/detail/zones/full_hash.json'
PROPS_BLEND = RIG_DIR + '/props/AirshipProps.blend'            # read only (props atlas, turret meshes)
HULL_MASK_R2 = RIG_DIR + '/checks/hull_ink/T_AirshipDrivable_ComicMask.png'   # round 2: his mask without the deck pieces
OUT = RIG_DIR + '/detail/r3export'
EXPORT_BLEND = OUT + '/AirshipR3_export.blend'
MANIFEST = OUT + '/manifest.json'
ARRAYS = OUT + '/manifest_arrays.npz'
TEX_DIR = OUT + '/textures'
CHECK_DIR = OUT + '/checks'
DOCS = '/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/round3'
MEDIA = DOCS + '/media/export'
MEDIA_FULL = DOCS + '/media/full'
PROTECTED = (BLENDER_ROOT + '/StylizedAirship.blend', RIG_DIR + '/AirshipRig.blend', RIG_DIR + '/AirshipRig_src.blend',
             RIG_DIR + '/detail/AirshipRig_detail.blend', RIG_DIR + '/props/AirshipProps.blend')

# export objects (EXPORT_R3.md section 1)
HULL_OBJ = 'SM_Airship'
PROP_PREFIX = 'SM_AirshipProp_'
MOVING = 'SM_AirshipR3Detail_Moving'          # in SK_Airship (sorts after SM_AirshipProp_*: material slot 2)
HULLDET = 'SM_AirshipR3_HullDetail'           # the static mesh (component on Mesh, socket Hull)
TURRETS = {'Turret_Base': 'SM_AirshipTurret_Base', 'Turret_Gun': 'SM_AirshipTurret_Gun'}
MAT_HULL, MAT_PROPS, MAT_DETAIL = 'M_Airship', 'M_AirshipProps', 'M_AirshipR3_Detail'
UV_INK, UV_PAL = 'UVMap', 'R3Palette'         # UV0 = ink texture, UV1 = palette index (x), y = 0
UV_HULL_INK = 'R3Ink'                         # SM_Airship only: UV2 = its own ink atlas (UV0 stays Talal's UVs, which
                                              # his comic mask uses)

# face kinds on the detail pages (face attribute r3_kind)
K_ATLAS, K_RIVET, K_HIDDEN, K_THIN, K_INKSIDE = 0, 1, 2, 3, 4
KIND_NAMES = {K_ATLAS: 'atlas', K_RIVET: 'rivet', K_HIDDEN: 'hidden', K_THIN: 'thin', K_INKSIDE: 'ink_side'}

# reserved blocks on the detail pages (texels): BLANK (no ink, no dot) top-right, INK (distance 0) top-left; the packed
# islands stay below / left of a band of BAND texels along the top and the right edge
BLOCK = 32
BAND = 40

# ------------------------------------------------------------------ the palette (EXPORT_R3.md section 2.1)
ROLE_SLOTS = [                       # detail_common.ROLES order: index = role material index
    ('paint_yellow', (0.95, 0.68, 0.21)), ('paint_ochre', (0.83, 0.54, 0.15)), ('paint_orange', (0.85, 0.38, 0.12)),
    ('rust_red', (0.50, 0.20, 0.12)), ('rust_dark', (0.34, 0.14, 0.09)), ('dark_metal', (0.17, 0.16, 0.16)),
    ('machinery', (0.28, 0.29, 0.31)), ('steel', (0.50, 0.52, 0.55)), ('copper', (0.70, 0.36, 0.17)),
    ('brass', (0.76, 0.58, 0.24)), ('bolt', (0.33, 0.30, 0.27)), ('wood', (0.45, 0.30, 0.18))]
SPARE = (1.0, 0.0, 1.0)              # magenta: a face that points at a spare slot shows at once
PALETTE_SLOTS = ROLE_SLOTS + [
    ('hull_paint', (0.90, 0.60, 0.17)), ('deck', (0.52, 0.46, 0.38)), ('recess', (0.20, 0.17, 0.16)),
    ('glass', (0.85, 0.85, 0.70)),
    ('keel_block', (0.50, 0.20, 0.12)),          # Talal 2026-11-28: rust (rust_red's colour); a live knob in Unreal
    ('prop_wood', (0.45, 0.30, 0.18)), ('prop_metal', (0.17, 0.16, 0.16)), ('prop_gun', (0.28, 0.29, 0.31)),
    ('spare_20', SPARE), ('spare_21', SPARE), ('spare_22', SPARE), ('spare_23', SPARE)]
assert len(PALETTE_SLOTS) == 24
SLOT = {k: i for i, (k, _) in enumerate(PALETTE_SLOTS)}
PAL = np.array([c for _, c in PALETTE_SLOTS], np.float64)
# props by object (the approved toon previews' rule, detail_render.apply_toon): wheels and carriages wood, the
# turret gun machinery grey, everything else dark metal
PROP_KEY_TO_SLOT = {'wood': 'prop_wood', 'dark_metal': 'prop_metal', 'machinery': 'prop_gun'}
INK_HEX = '1C2230'


def prop_key(name):
    return 'wood' if ('Wheel' in name or 'Carriage' in name) else ('machinery' if name.endswith('_Gun') else 'dark_metal')


def hex_lin(h):
    c = np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)])
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def lin_to_srgb(c):
    c = np.clip(np.asarray(c, np.float64), 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def srgb_to_lin(c):
    c = np.asarray(c, np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


# ------------------------------------------------------------------ pages (EXPORT_R3.md section 2.3)
PAGES = {
    # page: texture file, size, objects (in the export blend), crease angle (deg), notes
    'hull': dict(tex='T_AirshipR3_HullInk.png', size=4096, objects=[HULL_OBJ], crease=42.0, uv=UV_HULL_INK),
    'H': dict(tex='T_AirshipR3_DetailInk_H.png', size=4096, objects=[HULLDET], crease=60.0),
    'M': dict(tex='T_AirshipR3_DetailInk_M.png', size=4096, objects=[MOVING], crease=60.0),
    'P': dict(tex='T_AirshipR3_PropsInk.png', size=2048, objects=None, crease=45.0),     # props atlas (one of each)
}


# ------------------------------------------------------------------ misc
def md5_file(p, chunk=1 << 22):
    h = hashlib.md5()
    with open(p, 'rb') as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def protected_state():
    return {p: dict(md5=md5_file(p), mtime=time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(os.path.getmtime(p))))
            for p in PROTECTED if os.path.isfile(p)}


def check_out_path(p):
    rp = os.path.realpath(p)
    ok = any(rp.startswith(os.path.realpath(d) + os.sep) for d in (OUT, DOCS))
    if not ok or any(rp == os.path.realpath(q) for q in PROTECTED + (FULL_BLEND,)):
        raise RuntimeError('r3 scripts write only under %s or %s: %s' % (OUT, DOCS, p))
    return rp


def dump_json(obj, p):
    check_out_path(p)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w') as f:
        json.dump(obj, f, indent=1, default=lambda o: o.tolist() if hasattr(o, 'tolist') else str(o))


def load_json(p):
    with open(p) as f:
        return json.load(f)


class Log:
    def __init__(self, tag):
        self.t0 = time.time()
        self.tag = tag

    def __call__(self, *a):
        print('[%s %6.1fs]' % (self.tag, time.time() - self.t0), *a, flush=True)


def argv():
    import sys
    return sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []


def arg(A, k, d, f=str):
    return f(A[A.index(k) + 1]) if k in A else d


# ------------------------------------------------------------------ mesh arrays (bpy mesh -> numpy)
def mesh_np(me):
    nP = len(me.polygons)
    co = np.empty(len(me.vertices) * 3); me.vertices.foreach_get('co', co)
    ls = np.empty(nP, np.int64); me.polygons.foreach_get('loop_start', ls)
    lt = np.empty(nP, np.int64); me.polygons.foreach_get('loop_total', lt)
    lv = np.empty(len(me.loops), np.int64); me.loops.foreach_get('vertex_index', lv)
    fn = np.empty(nP * 3); me.polygons.foreach_get('normal', fn)
    fc = np.empty(nP * 3); me.polygons.foreach_get('center', fc)
    fa = np.empty(nP); me.polygons.foreach_get('area', fa)
    mi = np.empty(nP, np.int64); me.polygons.foreach_get('material_index', mi)
    return dict(co=co.reshape(-1, 3), ls=ls, lt=lt, lv=lv, fn=fn.reshape(-1, 3), fc=fc.reshape(-1, 3), fa=fa, mi=mi,
                lp=np.repeat(np.arange(nP), lt))


def face_attr_get(me, name, dtype=np.int32):
    a = me.attributes.get(name)
    if a is None:
        return None
    out = np.empty(len(me.polygons), dtype)
    a.data.foreach_get('value', out)
    return out


def face_attr_set(me, name, vals, kind='INT'):
    a = me.attributes.get(name)
    if a is not None:
        me.attributes.remove(a)
    a = me.attributes.new(name, kind, 'FACE')
    a.data.foreach_set('value', np.asarray(vals, np.int32 if kind == 'INT' else np.float32))


def uv_get(me, name):
    a = np.empty(len(me.loops) * 2); me.uv_layers[name].data.foreach_get('uv', a)
    return a.reshape(-1, 2)


def uv_set(me, name, uv):
    me.uv_layers[name].data.foreach_set('uv', np.ascontiguousarray(uv, np.float64).ravel())


def tri_arrays(me):
    """loop triangles: (T,3) loop ids, (T,3) vertex ids, (T,) polygon ids"""
    me.calc_loop_triangles()
    nT = len(me.loop_triangles)
    tl = np.empty(nT * 3, np.int64); me.loop_triangles.foreach_get('loops', tl)
    tv = np.empty(nT * 3, np.int64); me.loop_triangles.foreach_get('vertices', tv)
    tp = np.empty(nT, np.int64); me.loop_triangles.foreach_get('polygon_index', tp)
    return tl.reshape(-1, 3), tv.reshape(-1, 3), tp


def texel_density(uv, co, tl, tv, keep, res):
    """area-weighted texel density per metre: (per-triangle density, 3D area) of the kept triangles"""
    tu = uv[tl]; tc = co[tv]
    a2 = 0.5 * np.abs((tu[:, 1, 0] - tu[:, 0, 0]) * (tu[:, 2, 1] - tu[:, 0, 1]) -
                      (tu[:, 2, 0] - tu[:, 0, 0]) * (tu[:, 1, 1] - tu[:, 0, 1]))
    a3 = 0.5 * np.linalg.norm(np.cross(tc[:, 1] - tc[:, 0], tc[:, 2] - tc[:, 0]), axis=1)
    k = keep & (a3 > 1e-10)
    return np.sqrt(a2[k] * res * res / a3[k]), a3[k]


def weighted_pct(vals, w, ps=(5, 25, 50, 75, 95)):
    if not len(vals):
        return {}
    o = np.argsort(vals); cw = np.cumsum(w[o]) / w.sum()
    return {str(p): round(float(np.interp(p / 100.0, cw, vals[o])), 2) for p in ps}


# ------------------------------------------------------------------ UV raster (overlap / coverage checks)
def page_uv(me, pg):
    """the UV layer a page's ink texture uses on this mesh"""
    u = PAGES[pg].get('uv', UV_INK)
    return u if u in me.uv_layers else UV_INK


def raster_owner(tri_uv, tri_island, res, eps=1e-6):
    """rasterise UV triangles (T,3,2 in 0..1) at res: per texel the lowest and highest island id whose triangles
    cover the texel centre (-1 / -1 = uncovered) and the coverage count. A texel with lo != hi is an overlap between
    two islands (shared edges inside one island never count)."""
    P = tri_uv * res - 0.5
    x0 = np.ceil(P[:, :, 0].min(1) - eps).astype(np.int64); x1 = np.floor(P[:, :, 0].max(1) + eps).astype(np.int64)
    y0 = np.ceil(P[:, :, 1].min(1) - eps).astype(np.int64); y1 = np.floor(P[:, :, 1].max(1) + eps).astype(np.int64)
    x0 = np.clip(x0, 0, res - 1); y0 = np.clip(y0, 0, res - 1)
    x1 = np.clip(x1, -1, res - 1); y1 = np.clip(y1, -1, res - 1)
    w = x1 - x0 + 1; h = y1 - y0 + 1
    lo = np.full(res * res, np.iinfo(np.int64).max, np.int64)
    hi = np.full(res * res, -1, np.int64)
    cnt = np.zeros(res * res, np.int32)
    (ax, ay), (bx, by), (cx, cy) = P[:, 0].T, P[:, 1].T, P[:, 2].T
    d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
    ok = (w > 0) & (h > 0) & (np.abs(d) > 1e-12)
    s_prev = 0
    for s in (1, 2, 4, 8, 16, 32, 64):
        sel = np.nonzero(ok & (np.maximum(w, h) <= s) & (np.maximum(w, h) > s_prev))[0]
        s_prev = s
        if not len(sel):
            continue
        gy, gx = np.mgrid[0:s, 0:s]
        gx = gx.ravel()[None, :] + x0[sel, None]; gy = gy.ravel()[None, :] + y0[sel, None]
        inb = (gx <= x1[sel, None]) & (gy <= y1[sel, None])
        dd = d[sel, None]
        l1 = ((by[sel, None] - cy[sel, None]) * (gx - cx[sel, None]) + (cx[sel, None] - bx[sel, None]) * (gy - cy[sel, None])) / dd
        l2 = ((cy[sel, None] - ay[sel, None]) * (gx - cx[sel, None]) + (ax[sel, None] - cx[sel, None]) * (gy - cy[sel, None])) / dd
        ins = inb & (l1 > eps) & (l2 > eps) & (1 - l1 - l2 > eps)
        r, c = np.nonzero(ins)
        pix = gy[r, c] * res + gx[r, c]
        isl = tri_island[sel][r]
        np.minimum.at(lo, pix, isl); np.maximum.at(hi, pix, isl); np.add.at(cnt, pix, 1)
    for t in np.nonzero(ok & (np.maximum(w, h) > 64))[0]:
        gy, gx = np.mgrid[y0[t]:y1[t] + 1, x0[t]:x1[t] + 1]
        l1 = ((by[t] - cy[t]) * (gx - cx[t]) + (cx[t] - bx[t]) * (gy - cy[t])) / d[t]
        l2 = ((cy[t] - ay[t]) * (gx - cx[t]) + (ax[t] - cx[t]) * (gy - cy[t])) / d[t]
        ins = (l1 > eps) & (l2 > eps) & (1 - l1 - l2 > eps)
        pix = (gy[ins] * res + gx[ins]).ravel()
        np.minimum.at(lo, pix, tri_island[t]); np.maximum.at(hi, pix, tri_island[t]); np.add.at(cnt, pix, 1)
    lo[hi < 0] = -1
    return lo.reshape(res, res), hi.reshape(res, res), cnt.reshape(res, res)


def uv_islands(ls, lt, lv, uv, faces=None):
    """UV island id per face: faces joined by an edge whose two corners have the same UVs on both sides"""
    nP = len(ls)
    lp = np.repeat(np.arange(nP), lt)
    nxt = np.arange(len(lv)) + 1
    nxt[ls + lt - 1] = ls
    L = np.arange(len(lv)) if faces is None else np.nonzero(faces[lp])[0]
    a, b = lv[L], lv[nxt[L]]
    q = np.round(uv * 1e6).astype(np.int64)
    ua, ub = q[L], q[nxt[L]]
    swap = a > b
    va = np.where(swap, b, a); vb = np.where(swap, a, b)
    uA = np.where(swap[:, None], ub, ua); uB = np.where(swap[:, None], ua, ub)
    key = np.stack([va, vb, uA[:, 0], uA[:, 1], uB[:, 0], uB[:, 1]], 1)
    o = np.lexsort(key.T[::-1])
    ks = key[o]
    same = np.nonzero(np.all(ks[1:] == ks[:-1], axis=1))[0]
    par = np.arange(nP)

    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x
    for i in same.tolist():
        fa, fb = find(lp[L[o[i]]]), find(lp[L[o[i + 1]]])
        if fa != fb:
            par[max(fa, fb)] = min(fa, fb)
    return np.array([find(i) for i in range(nP)])
