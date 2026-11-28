"""Round 3 export: UV rasteriser for the ink bake (numpy only, deterministic; replaces the Cycles position / face-id
bake of the spike). For every texel within `margin` texels of a UV triangle it returns the owning triangle (inside
texels win; outside texels take the nearest triangle), the 3D position on that triangle's plane (EXTRAPOLATED for
texels outside it, so the distance field continues past the island edge instead of repeating the border texel) and,
for outside texels, which edge of the triangle is the nearest one. r3_bake.py stores a SIGNED distance there: beyond
a feature edge the value goes negative, so bilinear filtering puts the zero crossing exactly on the edge and lines at
island borders stay crisp at any width.

  tri, inside, edge = raster(tri_uv (T,3,2 in 0..1), res, margin)
  pos = positions(tri_uv, tri_co (T,3,3), tri, res)
"""
import numpy as np


def _cands(P, sel, s, M, res):
    """candidate texels of the triangles `sel` (bbox + margin fits in s x s): (row index into sel, pixel, key, edge)"""
    x0 = np.floor(P[sel, :, 0].min(1)).astype(np.int64) - M
    y0 = np.floor(P[sel, :, 1].min(1)).astype(np.int64) - M
    gy, gx = np.mgrid[0:s, 0:s]
    gx = gx.ravel()[None, :] + x0[:, None]; gy = gy.ravel()[None, :] + y0[:, None]
    a, b, c = P[sel, 0], P[sel, 1], P[sel, 2]
    px = gx.astype(np.float64); py = gy.astype(np.float64)

    def edge_d(p0, p1):
        ex = (p1[:, 0] - p0[:, 0])[:, None]; ey = (p1[:, 1] - p0[:, 1])[:, None]
        L2 = np.maximum(ex * ex + ey * ey, 1e-18)
        t = np.clip(((px - p0[:, 0, None]) * ex + (py - p0[:, 1, None]) * ey) / L2, 0, 1)
        dx = px - p0[:, 0, None] - t * ex; dy = py - p0[:, 1, None] - t * ey
        return np.sqrt(dx * dx + dy * dy)
    d0, d1, d2 = edge_d(a, b), edge_d(b, c), edge_d(c, a)
    det = (b[:, 1] - c[:, 1]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 1] - c[:, 1])
    det = np.where(np.abs(det) < 1e-12, 1e-12, det)[:, None]
    l1 = ((b[:, 1, None] - c[:, 1, None]) * (px - c[:, 0, None]) + (c[:, 0, None] - b[:, 0, None]) * (py - c[:, 1, None])) / det
    l2 = ((c[:, 1, None] - a[:, 1, None]) * (px - c[:, 0, None]) + (a[:, 0, None] - c[:, 0, None]) * (py - c[:, 1, None])) / det
    l3 = 1 - l1 - l2
    inside = (l1 >= -1e-9) & (l2 >= -1e-9) & (l3 >= -1e-9)
    dmin = np.minimum(np.minimum(d0, d1), d2)
    edge = np.where(d0 <= np.minimum(d1, d2), 0, np.where(d1 <= d2, 1, 2))
    key = np.where(inside, -1.0, dmin)
    ok = (key <= M) & (gx >= 0) & (gy >= 0) & (gx < res) & (gy < res)
    r, k = np.nonzero(ok)
    return r, gy[r, k] * res + gx[r, k], key[r, k], edge[r, k]


def raster(tri_uv, res, margin=8, chunk=3_000_000):
    """per texel: owning triangle (-1 = none), inside flag, nearest edge (0: v0-v1, 1: v1-v2, 2: v2-v0) of the owner
    for outside texels. Texel (i, j) = row i (v, bottom-up like Blender pixels), column j; centre ((j+.5)/res, (i+.5)/res)."""
    P = tri_uv * res - 0.5
    T = len(P)
    w = np.ceil(P[:, :, 0].max(1)) - np.floor(P[:, :, 0].min(1)) + 1
    h = np.ceil(P[:, :, 1].max(1)) - np.floor(P[:, :, 1].min(1)) + 1
    ext = (np.maximum(w, h) + 2 * margin + 1).astype(np.int64)
    a2 = np.abs((P[:, 1, 0] - P[:, 0, 0]) * (P[:, 2, 1] - P[:, 0, 1]) - (P[:, 2, 0] - P[:, 0, 0]) * (P[:, 1, 1] - P[:, 0, 1]))
    ext[a2 < 1e-6] = 1 << 30                    # collapsed UV triangles own no texel
    best_key = np.full(res * res, np.inf)
    best_tri = np.full(res * res, -1, np.int64)
    best_edge = np.zeros(res * res, np.int8)
    order = np.arange(T)

    def merge(r, pix, key, edge, sel):
        tri = sel[r]
        o = np.lexsort((tri, key, pix))
        pix, key, tri, edge = pix[o], key[o], tri[o], edge[o]
        first = np.ones(len(pix), bool); first[1:] = pix[1:] != pix[:-1]
        pix, key, tri, edge = pix[first], key[first], tri[first], edge[first]
        better = (key < best_key[pix]) | ((key == best_key[pix]) & (tri < best_tri[pix]))
        p = pix[better]
        best_key[p] = key[better]; best_tri[p] = tri[better]; best_edge[p] = edge[better]

    prev = 0
    for s in (8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192):
        sel_all = order[(ext <= s) & (ext > prev)]
        prev = s
        if not len(sel_all):
            continue
        step = max(1, chunk // (s * s))
        for c0 in range(0, len(sel_all), step):
            sel = sel_all[c0:c0 + step]
            r, pix, key, edge = _cands(P, sel, s, margin, res)
            if len(pix):
                merge(r, pix, key, edge, sel)
    inside = best_key < 0
    return best_tri.reshape(res, res), inside.reshape(res, res), best_edge.reshape(res, res)


def positions(tri_uv, tri_co, tri, res):
    """3D position of every owned texel on its triangle's plane (barycentric, extrapolated outside the triangle)"""
    out = np.full((res * res, 3), np.nan)
    t = tri.ravel()
    idx = np.nonzero(t >= 0)[0]
    P = tri_uv[t[idx]] * res - 0.5
    px = (idx % res).astype(np.float64); py = (idx // res).astype(np.float64)
    a, b, c = P[:, 0], P[:, 1], P[:, 2]
    det = (b[:, 1] - c[:, 1]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 1] - c[:, 1])
    det = np.where(np.abs(det) < 1e-12, 1e-12, det)
    l1 = ((b[:, 1] - c[:, 1]) * (px - c[:, 0]) + (c[:, 0] - b[:, 0]) * (py - c[:, 1])) / det
    l2 = ((c[:, 1] - a[:, 1]) * (px - c[:, 0]) + (a[:, 0] - c[:, 0]) * (py - c[:, 1])) / det
    l3 = 1 - l1 - l2
    C = tri_co[t[idx]]
    out[idx] = l1[:, None] * C[:, 0] + l2[:, None] * C[:, 1] + l3[:, None] * C[:, 2]
    return out.reshape(res, res, 3)
