"""Round 3: geometric ink as a distance field (the bakeable part of the approved toon renders' Freestyle lines).

The approved zone 1 renders draw crease and material-boundary lines (Freestyle, constant pixel width) and no ink on
rivets. A baked line has a world width, so the texture stores the DISTANCE (metres) from each texel to the nearest
feature edge, and the material draws the line at a width that follows the pixel size (fwidth of the world position in
Unreal, the camera's view distance in the Blender preview): thin and crisp up close, still one or two pixels at the
chase camera.

Feature edges (per mesh, from its own topology):
  * hard creases: the two faces' normals differ by more than `crease_deg` AND the edge is shaded hard (their corner
    normals at the edge differ by more than `hard_deg`; smooth tubes and domes are never lined along their facets);
  * class boundaries: the faces' class (role / palette slot) differs, at any angle;
  * open borders and non-manifold edges.
A texel's distance is measured to the feature edges that touch its own face's vertices (the face's 1-ring), so lines
continue across UV seams and across the faces of one plate.

  segs, incid = feature_segments(co, ls, lt, lv, cn, fnrm, cls)
  dist = distance_map(fid, pos, covered, face_lists(ls, lt, lv, incid), segs, dmax)
"""
import numpy as np


def feature_segments(co, ls, lt, lv, cn, fnrm, cls, crease_deg=35.0, hard_deg=None, faces_ok=None, cap=None):
    """feature edges of a polygon mesh (numpy arrays: co (V,3), loop_start/total (P), loop vertex (L), corner normals
    (L,3), face normals (P,3), face class (P)). crease_deg: a number or a per-face array (an edge is a crease when its
    faces turn more than the larger of their two thresholds); hard_deg: also require hard shading across the edge
    (None = angle only); cap (P int, -1 = not used): 1 = the face looks out of its piece's front (the piece's outward
    direction), 0 = it does not; an edge between a cap and a non-cap face of the same piece is a contour line (the
    outline a view from the front sees). faces_ok (P bool): faces that take part (others are ignored, as if
    absent). Returns (segments (S,2,3), segment vertex ids (S,2), counts dict)"""
    nP = len(ls)
    lp = np.repeat(np.arange(nP), lt)
    nxt = np.arange(len(lv)) + 1
    nxt[ls + lt - 1] = ls
    if faces_ok is not None:
        keep = faces_ok[lp]
    else:
        keep = np.ones(len(lv), bool)
    L = np.nonzero(keep)[0]
    a, b = lv[L], lv[nxt[L]]
    key = np.minimum(a, b).astype(np.int64) * (len(co) + 1) + np.maximum(a, b)
    o = np.argsort(key, kind='stable')
    ks, Ls = key[o], L[o]
    cut = np.nonzero(np.diff(ks))[0] + 1
    starts = np.concatenate([[0], cut]); ends = np.concatenate([cut, [len(ks)]])
    cnt = ends - starts
    feat = []
    n_border = n_nonman = n_class = n_crease = 0
    cdeg = np.broadcast_to(np.asarray(crease_deg, np.float64), (nP,))
    # border / non-manifold
    for s, e in zip(starts[cnt != 2], ends[cnt != 2]):
        i = Ls[s]
        feat.append((lv[i], lv[nxt[i]]))
        if e - s == 1:
            n_border += 1
        else:
            n_nonman += 1
    s2 = starts[cnt == 2]
    i, j = Ls[s2], Ls[s2 + 1]
    fi, fj = lp[i], lp[j]
    clsd = cls[fi] != cls[fj]
    ang = (fnrm[fi] * fnrm[fj]).sum(1) < np.cos(np.radians(np.maximum(cdeg[fi], cdeg[fj])))
    if hard_deg is not None:
        # corner normals at the two shared vertices: loop i runs v -> w; loop j runs w -> v (consistent winding)
        cos_h = np.cos(np.radians(hard_deg))
        same_dir = lv[i] == lv[j]
        jv = np.where(same_dir, j, nxt[j])          # loop of face j at vertex lv[i]
        jw = np.where(same_dir, nxt[j], j)          # loop of face j at vertex lv[nxt[i]]
        ang &= ((cn[i] * cn[jv]).sum(1) < cos_h) | ((cn[nxt[i]] * cn[jw]).sum(1) < cos_h)
    cont = np.zeros(len(i), bool)
    if cap is not None:
        cont = (cap[fi] >= 0) & (cap[fj] >= 0) & (cap[fi] != cap[fj])
    f = clsd | ang | cont
    n_class = int(clsd.sum()); n_crease = int((ang & ~clsd).sum())
    n_cont = int((cont & ~ang & ~clsd).sum())
    for ii in i[f]:
        feat.append((lv[ii], lv[nxt[ii]]))
    sv = np.array(feat, np.int64).reshape(-1, 2)
    segs = co[sv]
    return segs, sv, dict(border=n_border, nonmanifold=n_nonman, class_boundary=n_class, crease=n_crease,
                          contour=n_cont, segments=int(len(sv)))


def pieces(nv, ls, lt, lv):
    """connected pieces: piece id per face (union-find over the faces' vertices)"""
    par = np.arange(nv)

    def find(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a
    for s, t in zip(ls.tolist(), lt.tolist()):
        vs = lv[s:s + t].tolist()
        r0 = find(vs[0])
        for q in vs[1:]:
            rq = find(q)
            if rq != r0:
                par[rq] = r0
    root = np.array([find(i) for i in range(nv)])
    return root[lv[ls]]


def edge_pairs(ls, lt, lv):
    """(fi, fj) for every edge shared by exactly two faces"""
    nP = len(ls)
    lp = np.repeat(np.arange(nP), lt)
    nxt = np.arange(len(lv)) + 1
    nxt[ls + lt - 1] = ls
    a, b = lv, lv[nxt]
    key = np.minimum(a, b).astype(np.int64) * (int(lv.max()) + 2) + np.maximum(a, b)
    o = np.argsort(key, kind='stable')
    ks = key[o]
    same = np.nonzero(ks[1:] == ks[:-1])[0]
    single = np.ones(len(same), bool)
    single[1:] &= same[1:] != same[:-1] + 1
    single[:-1] &= same[:-1] + 1 != same[1:]
    same = same[single]
    return lp[o[same]], lp[o[same + 1]]


def grow(seed, allowed, pairs, rings):
    """faces in `allowed` reachable from `seed` through shared edges in up to `rings` steps (seed excluded)"""
    fi, fj = pairs
    got = np.zeros(len(seed), bool)
    front = seed.copy()
    for _ in range(rings):
        nb = np.zeros(len(seed), bool)
        nb[fj[front[fi]]] = True
        nb[fi[front[fj]]] = True
        nb &= allowed & ~got & ~seed
        if not nb.any():
            break
        got |= nb
        front = nb
    return got


def cap_faces(piece, fnrm, farea, visible, fallback_dir, cap_deg=50.0, min_ratio=0.3, cap_deg_weak=None):
    """1 where a face looks out of its piece's front, else 0. The front = the area-weighted normal of the piece's
    visible faces; when those nearly cancel (closed tubes, domes: |sum| < min_ratio * area) the front is
    fallback_dir(piece_face_index) (the hull's outward normal near the piece)."""
    nP = len(piece)
    w = (fnrm * (farea * visible)[:, None])
    _, inv = np.unique(piece, return_inverse=True)
    S = np.zeros((inv.max() + 1, 3)); np.add.at(S, inv, w)
    A = np.zeros(inv.max() + 1); np.add.at(A, inv, farea * visible)
    N = S / np.maximum(np.linalg.norm(S, axis=1, keepdims=True), 1e-12)
    weak = np.linalg.norm(S, axis=1) < min_ratio * np.maximum(A, 1e-12)
    if weak.any():
        first = np.zeros(inv.max() + 1, np.int64); first[inv[::-1]] = np.arange(nP)[::-1]
        for k in np.nonzero(weak)[0]:
            N[k] = fallback_dir(int(first[k]))
    cdeg = np.where(weak[inv], cap_deg if cap_deg_weak is None else cap_deg_weak, cap_deg)
    return ((fnrm * N[inv]).sum(1) > np.cos(np.radians(cdeg))).astype(np.int64), int(weak.sum())


def face_lists(ls, lt, lv, seg_verts, nverts):
    """per face: the feature segments touching any of its vertices (CSR: offsets, ids)"""
    inc = [[] for _ in range(nverts)]
    for k, (a, b) in enumerate(seg_verts.tolist()):
        inc[a].append(k)
        inc[b].append(k)
    out, off = [], [0]
    for s, t in zip(ls.tolist(), lt.tolist()):
        ids = set()
        for v in lv[s:s + t].tolist():
            ids.update(inc[v])
        out.extend(sorted(ids))
        off.append(len(out))
    return np.array(off, np.int64), np.array(out, np.int64)


def point_seg_dist(P, A, B):
    """distances (n, m) from points P (n,3) to segments A->B (m,3)"""
    AB = B - A
    L2 = np.maximum((AB * AB).sum(1), 1e-18)
    AP = P[:, None, :] - A[None, :, :]
    t = np.clip((AP * AB[None]).sum(2) / L2[None], 0.0, 1.0)
    Q = A[None] + t[..., None] * AB[None]
    return np.linalg.norm(P[:, None, :] - Q, axis=2)


def distance_map(fid, pos, covered, csr, segs, dmax, faces_ok=None):
    """fid (H,W) int face id per texel (-1 = none), pos (H,W,3) world position, covered (H,W) bool. Returns (H,W)
    float32 distance in metres, clipped to dmax (dmax where a face has no feature edge near it)."""
    off, ids = csr
    H, W = fid.shape
    out = np.full(H * W, dmax, np.float32)
    f = fid.ravel()
    P = pos.reshape(-1, 3)
    sel = np.nonzero(covered.ravel() & (f >= 0))[0]
    if faces_ok is not None:
        sel = sel[faces_ok[f[sel]]]
    o = np.argsort(f[sel], kind='stable')
    sel = sel[o]
    fs = f[sel]
    cut = np.nonzero(np.diff(fs))[0] + 1
    for grp in np.split(sel, cut):
        if not len(grp):
            continue
        face = f[grp[0]]
        sid = ids[off[face]:off[face + 1]]
        if not len(sid):
            continue
        S = segs[sid]
        for c0 in range(0, len(grp), 20000):
            g = grp[c0:c0 + 20000]
            d = point_seg_dist(P[g], S[:, 0], S[:, 1]).min(1)
            out[g] = np.minimum(d, dmax)
    return out.reshape(H, W)


# ------------------------------------------------------------------ round 3 production (r3_bake.py, 2026-11-28)
# The 1-ring rule above (a texel sees only the feature edges touching its own face's vertices) gives different
# distances on the two sides of a UV seam whenever one of the faces is narrow: on the whole ship 11-18 % of the hull's
# seam samples flipped between ink and no ink. The production rule: a face sees every feature edge of ITS OWN PIECE
# (connected part) within dmax of its bounding box, so two faces that share an edge see the same edges at that edge
# (exact continuity across seams and face borders); a texel ignores an edge whose nearest point lies behind its face
# (more than `behind` x the distance below the face's plane: the far side of a plate, a wall seen through itself).

def face_lists_piece(co, ls, lt, lv, seg_verts, piece, dmax, faces_ok=None, chunk=4_000_000):
    """per face: the feature segments of its own piece whose bounding box comes within dmax of the face's (CSR)"""
    nP = len(ls)
    lp = np.repeat(np.arange(nP), lt)
    flo = np.full((nP, 3), np.inf); fhi = np.full((nP, 3), -np.inf)
    np.minimum.at(flo, lp, co[lv]); np.maximum.at(fhi, lp, co[lv])
    vpiece = np.zeros(len(co), np.int64); vpiece[lv] = piece[lp]
    sp = vpiece[seg_verts[:, 0]]
    slo = np.minimum(co[seg_verts[:, 0]], co[seg_verts[:, 1]]); shi = np.maximum(co[seg_verts[:, 0]], co[seg_verts[:, 1]])
    fsel = np.arange(nP) if faces_ok is None else np.nonzero(faces_ok)[0]
    so = np.argsort(sp, kind='stable'); sps = sp[so]
    fo = fsel[np.argsort(piece[fsel], kind='stable')]; fps = piece[fo]
    rows, cols = [], []
    for p in np.unique(fps):
        F = fo[np.searchsorted(fps, p):np.searchsorted(fps, p, side='right')]
        Sg = so[np.searchsorted(sps, p):np.searchsorted(sps, p, side='right')]
        if not len(Sg):
            continue
        step = max(1, chunk // len(Sg))
        for c0 in range(0, len(F), step):
            f = F[c0:c0 + step]
            gap = np.maximum(0.0, np.maximum(flo[f][:, None, :] - shi[Sg][None], slo[Sg][None] - fhi[f][:, None, :]))
            r, c = np.nonzero((gap * gap).sum(2) < dmax * dmax)
            rows.append(f[r]); cols.append(Sg[c])
    rows = np.concatenate(rows) if rows else np.zeros(0, np.int64)
    cols = np.concatenate(cols) if cols else np.zeros(0, np.int64)
    o = np.lexsort((cols, rows))
    rows, cols = rows[o], cols[o]
    off = np.zeros(nP + 1, np.int64)
    np.add.at(off, rows + 1, 1)
    return np.cumsum(off), cols


def distance_map_n(fid, pos, covered, csr, segs, dmax, fnrm, faces_ok=None, behind=0.7, slack=0.002, block=4_000_000):
    """distance_map with the behind-the-face test: a segment counts for a texel only where its nearest point Q has
    (Q - P) . n >= -(behind |Q - P| + slack), n = the texel's face normal"""
    off, ids = csr
    H, W = fid.shape
    out = np.full(H * W, dmax, np.float32)
    f = fid.ravel()
    P = pos.reshape(-1, 3)
    sel = np.nonzero(covered.ravel() & (f >= 0))[0]
    if faces_ok is not None:
        sel = sel[faces_ok[f[sel]]]
    o = np.argsort(f[sel], kind='stable')
    sel = sel[o]
    fs = f[sel]
    cut = np.nonzero(np.diff(fs))[0] + 1
    for grp in np.split(sel, cut):
        if not len(grp):
            continue
        face = f[grp[0]]
        sid = ids[off[face]:off[face + 1]]
        if not len(sid):
            continue
        A_ = segs[sid, 0]; B_ = segs[sid, 1]
        AB = B_ - A_
        L2 = np.maximum((AB * AB).sum(1), 1e-18)
        n = fnrm[face]
        step = max(1, block // len(sid))
        for c0 in range(0, len(grp), step):
            g = grp[c0:c0 + step]
            AP = P[g][:, None, :] - A_[None]
            t = np.clip((AP * AB[None]).sum(2) / L2[None], 0.0, 1.0)
            Q = A_[None] + t[..., None] * AB[None]
            D = Q - P[g][:, None, :]
            dist = np.sqrt((D * D).sum(2))
            ok = (D @ n) >= -(behind * dist + slack)
            d = np.where(ok, dist, dmax).min(1)
            out[g] = np.minimum(d, dmax)
    return out.reshape(H, W)
