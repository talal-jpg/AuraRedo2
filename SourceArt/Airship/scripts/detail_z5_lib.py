"""Zone 5 (belly and keel) helpers for the round 3 detail pass: the belly chart and its free-area mask.

Zone 5's own module (detail_z5.py imports it). Nothing here edits a shared module.

BellyChart: section rays in the (y, z) plane of each station x, from far below toward the axis point (x, 0, AZ), at the
angle psi (0 = straight down, + toward port). Every cell keeps the skin hit (point, smooth normal), whether other
geometry lies in front of it (covered: belly tabs, pods, struts ...), breaks / creases between neighbours, and the
signed arc length v across the belly from the keel line (v = 0 under the keel, + port, - starboard).

BellyMask: the free skin of zone 5 in (x, v) cells (the RowMask interface of detail_flank, so detail_flank.tile_rows /
fill_gaps tile it): hit, not covered, not next to a break, owned by Z5 by the zone map's rules (detail_zones:
position_owner per point and the nearest face's owner), at least `margin` from any other zone, and outside the extra
keep-outs (the rudder sweep).
"""
import math
import numpy as np
from mathutils import Vector as V
import detail_common as D
import detail_zones as Z


class BellyChart:
    def __init__(self, skin, obst, xs, psis_deg, AZ=0.3, clear=0.30):
        self.skin, self.obst, self.AZ = skin, obst, AZ
        self.xs = np.asarray(xs, float)
        self.ps = np.radians(np.asarray(psis_deg, float))
        nx, npsi = len(self.xs), len(self.ps)
        self.P = np.full((nx, npsi, 3), np.nan)
        self.N = np.full((nx, npsi, 3), np.nan)
        self.cov = np.zeros((nx, npsi), bool)
        self.hit = np.zeros((nx, npsi), bool)
        self.fi = np.full((nx, npsi), -1, np.int64)
        self.FN = np.full((nx, npsi, 3), np.nan)        # flat (face) normals: the belly's chine creases
        for i, x in enumerate(self.xs):
            ax = np.array([x, 0.0, AZ])
            for j, p in enumerate(self.ps):
                d = np.array([0.0, math.sin(p), -math.cos(p)])
                o = ax + 20.0 * d
                r = skin.ray(o, -d, 30.0)
                if r is None:
                    continue
                self.hit[i, j] = True
                self.P[i, j], self.N[i, j] = r[0], r[1]
                self.fi[i, j] = r[2]
                self.FN[i, j] = r[4]
                ro = obst.ray_cast(V(o), V(-d), 30.0)
                if ro[0] is not None and ro[3] < r[3] + 0.002 and r[3] - ro[3] < clear + 1.0:
                    self.cov[i, j] = True
        self.brk = np.zeros((nx, npsi), bool)
        dp = np.linalg.norm(self.P[:, 1:] - self.P[:, :-1], axis=2)
        dn = np.einsum('ijk,ijk->ij', self.N[:, 1:], self.N[:, :-1])
        self.brk[:, 1:] = ~(dp < 0.2) | ~(dn > math.cos(math.radians(22)))
        # signed arc length from the keel ray (psi = 0)
        j0 = int(np.argmin(np.abs(self.ps)))
        self.j0 = j0
        self.v = np.full((nx, npsi), np.nan)
        for i in range(nx):
            if not self.hit[i, j0]:
                continue
            self.v[i, j0] = 0.0
            for rng_, sgn in ((range(j0 + 1, npsi), 1), (range(j0 - 1, -1, -1), -1)):
                acc, prev = 0.0, j0
                for j in rng_:
                    if not self.hit[i, j]:
                        break
                    acc += float(np.linalg.norm(self.P[i, j] - self.P[i, prev]))
                    self.v[i, j] = sgn * acc
                    prev = j

    def col(self, x):
        return int(np.clip(np.round((x - self.xs[0]) / (self.xs[1] - self.xs[0])), 0, len(self.xs) - 1))

    def psi_at(self, x, v):
        i = self.col(x)
        vv = self.v[i]
        ok = ~np.isnan(vv)
        if ok.sum() < 2:
            return None
        js = np.nonzero(ok)[0]
        sv = vv[js]
        if v < sv[0] - 1e-6 or v > sv[-1] + 1e-6:
            return None
        return float(np.interp(v, sv, self.ps[js]))

    def surf(self, x, v):
        """exact skin point + smooth normal at (x, v): a ray at the interpolated angle"""
        p = self.psi_at(x, v)
        if p is None:
            return None
        d = np.array([0.0, math.sin(p), -math.cos(p)])
        ax = np.array([x, 0.0, self.AZ])
        r = self.skin.ray(ax + 20.0 * d, -d, 30.0)
        if r is None:
            return None
        return r[0], r[1]


    def crease(self, side, v_rng=(1.3, 2.9), k=3, min_deg=8.0):
        """|v| of the chine crease (the 15-28 deg fold between the flat keel bottom and the belly side) per column on
        one side (NaN where none is found)"""
        out = np.full(len(self.xs), np.nan)
        for i in range(len(self.xs)):
            vv = self.v[i] * side
            js = np.nonzero(~np.isnan(vv) & (vv >= v_rng[0]) & (vv <= v_rng[1]))[0]
            best, bj = 0.0, None
            for j in js:
                a, b = j - k * side, j + k * side
                if a < 0 or b < 0 or a >= len(self.ps) or b >= len(self.ps):
                    continue
                if np.isnan(self.FN[i, a][0]) or np.isnan(self.FN[i, b][0]):
                    continue
                ang = math.degrees(math.acos(max(-1.0, min(1.0, float(np.dot(self.FN[i, a], self.FN[i, b]))))))
                if ang > best:
                    best, bj = ang, j
            if bj is not None and best >= min_deg:
                out[i] = float(vv[bj])
        return out


class BellyMask:
    """free zone 5 skin in (x, v) cells; the RowMask / Panel interface (xs, vs, dx, dv, free, used, maxrect, take, fn)"""

    def __init__(self, ch, zi, xs, vs, margin=0.12, keep=None, name='belly', extra_bad=None, side=1, ref=None,
                 v_hi=None):
        """side +1: chart v = +(ref(x) + v) (port half), -1: chart v = -(ref(x) + v) (starboard half), so both halves
        grow away from the keel line with v >= 0. ref: per-column offset (row-aligned bands along the chine crease);
        v_hi: per-column upper limit of v (NaN: no cell free in that column)"""
        self.ch, self.name, self.side = ch, name, side
        self.ref = np.zeros(len(xs)) if ref is None else np.asarray(ref, float)
        self.v_hi = None if v_hi is None else np.asarray(v_hi, float)
        self.xs, self.vs = np.asarray(xs, float), np.asarray(vs, float)
        self.dx, self.dv = float(self.xs[1] - self.xs[0]), float(self.vs[1] - self.vs[0])
        nx, nv = len(self.xs), len(self.vs)
        F = np.zeros((nx, nv), bool)
        self.P = np.full((nx, nv, 3), np.nan)
        self.N = np.full((nx, nv, 3), np.nan)
        self.owner = np.full((nx, nv), '', dtype=object)
        bad = ch.brk.copy()
        bad[:, :-1] |= ch.brk[:, 1:]
        own_face = None
        if zi is not None:
            own_face = zi.zone
        for i, x in enumerate(self.xs):
            ci = ch.col(x)
            col = ch.v[ci]
            js = np.nonzero(~np.isnan(col))[0]
            if len(js) < 2:
                continue
            sv = col[js]
            if np.isnan(self.ref[i]):
                continue
            vq = (self.ref[i] + self.vs) * side
            k = np.clip(np.searchsorted(sv, vq), 1, len(sv) - 1)
            near = np.where(np.abs(sv[k - 1] - vq) < np.abs(sv[k] - vq), k - 1, k)
            close = np.abs(sv[near] - vq) < 0.05
            for m in np.nonzero(close)[0]:
                j = js[near[m]]
                p, n = ch.P[ci, j], ch.N[ci, j]
                self.P[i, m], self.N[i, m] = p, n
                ow = Z.position_owner(p, n)
                if ow == 'Z5' and own_face is not None:
                    fo = zi.zone_at(p, 0.2)
                    if fo != 'Z5':
                        ow = str(fo)
                self.owner[i, m] = ow
                if ow != 'Z5' or ch.cov[ci, j] or bad[ci, j]:
                    continue
                if keep is not None and not keep(p):
                    continue
                if self.v_hi is not None and not (self.vs[m] <= self.v_hi[i]):
                    continue
                F[i, m] = True
        if extra_bad is not None:
            F &= ~extra_bad
        # margin: every free cell at least `margin` from a non-free-by-zone cell (other zones, keep-outs) and a
        # one-cell erosion everywhere else (breaks, covered cells)
        Zm = np.array([[o == 'Z5' for o in row] for row in self.owner], bool)
        kx, kv = int(math.ceil(margin / self.dx)), int(math.ceil(margin / self.dv))
        # v = 0 (the keel line) is not an edge of the zone: the other half continues there
        Ze = np.concatenate([np.repeat(Zm[:, :1], kv, axis=1), Zm], axis=1)
        Zr = Ze.copy()
        for a in range(-kx, kx + 1):
            for b in range(-kv, kv + 1):
                if (a * self.dx) ** 2 + (b * self.dv) ** 2 > margin ** 2 + 1e-9:
                    continue
                Zr &= _shift(Ze, a, b, False)
        Zr = Zr[:, kv:]
        E = F & Zr
        G = E.copy()
        G[1:] &= E[:-1]; G[:-1] &= E[1:]; G[:, 1:] &= E[:, :-1]; G[:, :-1] &= E[:, 1:]
        self.zone_ok = Zr
        self.free = G
        self.used = np.zeros_like(G)

    # ---- RowMask interface
    def ix(self, x):
        return int(round((x - self.xs[0]) / self.dx))

    def iv(self, v):
        return int(round((v - self.vs[0]) / self.dv))

    def maxrect(self, x0, x1, v0, v1):
        i0, i1 = max(0, self.ix(x0)), min(len(self.xs) - 1, self.ix(x1))
        m0, m1 = max(0, self.iv(v0)), min(len(self.vs) - 1, self.iv(v1))
        if i1 <= i0 or m1 <= m0:
            return None
        B = (self.free & ~self.used)[i0:i1 + 1, m0:m1 + 1]
        best = (0.0, None)
        hgt = np.zeros(B.shape[1], int)
        for i in range(B.shape[0]):
            hgt = np.where(B[i], hgt + 1, 0)
            st = []
            for m in range(len(hgt) + 1):
                hm = int(hgt[m]) if m < len(hgt) else 0
                start = m
                while st and st[-1][1] >= hm:
                    s0, hh = st.pop()
                    a = (hh * self.dx) * ((m - s0) * self.dv)
                    if a > best[0]:
                        best = (a, (i - hh + 1, i, s0, m - 1))
                    start = s0
                st.append((start, hm))
        if best[1] is None:
            return None
        ia, ib, ma, mb = best[1]
        return (self.xs[i0 + ia] - self.dx / 2, self.xs[i0 + ib] + self.dx / 2,
                self.vs[m0 + ma] - self.dv / 2, self.vs[m0 + mb] + self.dv / 2)

    def take(self, x0, x1, v0, v1):
        i0, i1 = max(0, self.ix(x0 + self.dx / 2)), min(len(self.xs) - 1, self.ix(x1 - self.dx / 2))
        m0, m1 = max(0, self.iv(v0 + self.dv / 2)), min(len(self.vs) - 1, self.iv(v1 - self.dv / 2))
        if i1 >= i0 and m1 >= m0:
            self.used[i0:i1 + 1, m0:m1 + 1] = True

    def all_free(self, x0, x1, v0, v1, pad=0.0):
        i0, i1 = self.ix(x0 - pad), self.ix(x1 + pad)
        m0, m1 = self.iv(v0 - pad), self.iv(v1 + pad)
        if i0 < 0 or m0 < 0 or i1 >= len(self.xs) or m1 >= len(self.vs):
            return False
        return bool((self.free & ~self.used)[i0:i1 + 1, m0:m1 + 1].all())

    def area_free(self):
        return float(self.free.sum() * self.dx * self.dv)

    # ---- surface functions (u along +x from x0, v across from v0, in this half's v)
    def ref_at(self, x):
        return float(np.interp(x, self.xs, self.ref))

    def at(self, x, v):
        return self.ch.surf(x, self.side * (self.ref_at(x) + v))

    def fn(self, x0, v0):
        ch, sd = self.ch, self.side

        def f(u, v):
            x = x0 + u
            return ch.surf(x, sd * (self.ref_at(x) + v0 + v))
        return f

    # ---- absolute keel-distance helpers (|chart v|), for pieces that cross the bands
    def take_abs(self, x0, x1, va, vb):
        i0, i1 = max(0, self.ix(x0 + self.dx / 2)), min(len(self.xs) - 1, self.ix(x1 - self.dx / 2))
        for i in range(i0, i1 + 1):
            m0 = max(0, self.iv(va - self.ref[i] + self.dv / 2))
            m1 = min(len(self.vs) - 1, self.iv(vb - self.ref[i] - self.dv / 2))
            if m1 >= m0:
                self.used[i, m0:m1 + 1] = True

    def free_abs(self, i, va):
        """is the cell of column i at |chart v| = va free and unused? None when va is outside this band"""
        m = self.iv(va - self.ref[i])
        if m < 0 or m >= len(self.vs) or (self.v_hi is not None and not (self.vs[m] <= self.v_hi[i] + 1e-9)):
            return None
        return bool(self.free[i, m] and not self.used[i, m])

    def world_dir_u(self, x, v):
        """unit tangent along +x at (x, v)"""
        a, b = self.at(x - 0.05, v), self.at(x + 0.05, v)
        if a is None or b is None:
            return np.array([1.0, 0.0, 0.0])
        return D.unit(b[0] - a[0])


def _shift(A, a, b, fill):
    """A shifted by (a, b) cells: out[i, m] = A[i + a, m + b] (fill outside)"""
    out = np.full_like(A, fill)
    nx, nv = A.shape
    i0, i1 = max(0, -a), min(nx, nx - a)
    m0, m1 = max(0, -b), min(nv, nv - b)
    if i1 > i0 and m1 > m0:
        out[i0:i1, m0:m1] = A[i0 + a:i1 + a, m0 + b:m1 + b]
    return out


# ================================================================== zone 1's plate language on any mask
# Copied on 2026-11-28 from detail_z4_lib.py (zone 4's own module: build_plate4, plate_rivets4, layer_plates, bay,
# strap, drop_intersecting, lift_fn), unchanged apart from the names, so zone 4's later edits never change zone 5.
from detail_flank import wchoice, on_step, overlaps
from mathutils.bvhtree import BVHTree

ZONE1_STYLE = dict(
    armour='rust_red', armour_p=0.5, batten='rust_red', frames=True,
    frame_mat=lambda m: 'paint_ochre' if m == 'paint_yellow' else 'paint_yellow',
    patch_mats=lambda m: (('rust_red', 0.7), ('paint_ochre', 0.3)),
    slots=3)


def lift_fn(f, d):
    """surface function moved out by d along its normal"""
    def g(u, v):
        r = f(u, v)
        return None if r is None else (r[0] + r[1] * d, r[1])
    return g


def tile_rows(M, rng, cfg, K, kind='plate', v_start=0.0):
    """detail_flank.tile_rows with the first row starting at v_start (the edge of the reserved keel strip)"""
    out = []
    seam = K['seam']
    v = v_start
    row = 0
    while v < M.vs[-1] - 0.15:
        h = rng.uniform(*cfg['row_h'])
        x = M.xs[0] - rng.uniform(0.0, cfg['w'][1] * 0.8)
        while x < M.xs[-1]:
            w = rng.uniform(*cfg['w'])
            cx0, cx1 = max(x, M.xs[0]), min(x + w, M.xs[-1])
            x += w
            if cx1 - cx0 < cfg['min_w']:
                continue
            r = M.maxrect(cx0, cx1, v, v + h)
            if r is None:
                continue
            W, H = r[1] - r[0], r[3] - r[2]
            if W < cfg['min_w'] or H < cfg['min_h'] or W * H < cfg['keep'] * (cx1 - cx0) * h:
                continue
            M.take(*r)
            out.append(dict(M=M, x0=r[0] + seam / 2, W=W - seam, v0=r[2] + seam / 2, H=H - seam, row=row,
                            mat=wchoice(rng, cfg['mats']), kind=kind,
                            corners=tuple(int(rng.random() < K['plate']['cut_p']) for _ in range(4)),
                            cut=rng.uniform(*K['plate']['cut'])))
        v += h
        row += 1
    return out


def fill_gaps(M, rng, cfg, K):
    """detail_flank.fill_gaps (the same small-plate pass)"""
    out = []
    seam = K['seam']
    for v in np.arange(0.0, M.vs[-1], 0.12):
        for x in np.arange(M.xs[0], M.xs[-1], 0.12):
            i, m = M.ix(x), M.iv(v)
            if not (M.free[i, m] and not M.used[i, m]):
                continue
            w, h = rng.uniform(*cfg['w']), rng.uniform(*cfg['h'])
            r = M.maxrect(x - w / 2, x + w / 2, v - h / 2, v + h / 2)
            if r is None or r[1] - r[0] < cfg['min_w'] or r[3] - r[2] < cfg['min_h']:
                continue
            M.take(*r)
            out.append(dict(M=M, x0=r[0] + seam / 2, W=r[1] - r[0] - seam, v0=r[2] + seam / 2, H=r[3] - r[2] - seam,
                            row=-1, mat=wchoice(rng, cfg['mats']), kind='fill',
                            corners=tuple(int(rng.random() < 0.2) for _ in range(4)), cut=rng.uniform(0.04, 0.08),
                            edges=wchoice(rng, (((('v0', 'v1')), 0.5), ((), 0.3), (('u0', 'u1'), 0.2)))))
    return out


def build_plate5(mesh, p, K, gap, t, bevel, log):
    M = p['M']
    f = M.fn(p['x0'], p['v0'])
    if on_step(f, p['W'], p['H'], K['step_tol']):
        log['skipped_on_step'] = log.get('skipped_on_step', 0) + 1
        log.setdefault('skipped_on_step_at', []).append([M.name, round(p['x0'], 2), round(p['v0'], 2), round(p['W'], 2),
                                                          round(p['H'], 2), p.get('kind')])
        p['top_fn'] = None
        return None
    cuts = p.get('corners', (0, 0, 0, 0))
    cut = min(p.get('cut', 0.0), 0.3 * min(p['W'], p['H'])) if any(cuts) else 0.0
    us = D.grid_coords(0.0, p['W'], K['plate']['cell_u'], cut)
    vs = D.grid_coords(0.0, p['H'], K['plate']['cell_v'], cut)
    top_fn, ok = D.solid_plate(mesh, f, us, vs, gap, t, bevel, p['mat'], corners=cuts if cut > 0 else (0, 0, 0, 0),
                               kind=p.get('kind', 'plate'))
    p['top_fn'] = top_fn if ok else None
    p['f'] = f
    p['us'], p['vs'], p['cut_used'], p['corners_used'] = us, vs, cut, (cuts if cut > 0 else (0, 0, 0, 0))
    p['top'] = gap + t
    return p['top_fn']


def plate_rivets5(mesh, top_fn, us, vs, R, p, keep_fn, extra=()):
    pts = D.corner_pts(us, vs, R['inset'], p.get('cut_used', 0.0), p.get('corners_used', (0, 0, 0, 0))) + list(extra)
    pts = [(u, v) for (u, v) in pts if keep_fn(p['x0'] + u, p['v0'] + v)]
    return D.rivet_row(mesh, top_fn, pts, r=R['r'], h=R['h'])


def layer_plates(mesh, rows, fills, K, rng, log, style=ZONE1_STYLE, tag=''):
    """zone 1's layers on tiled plates: raised plates overlapping both row neighbours (some heavy armour), riveted frame
    ribs over plain seams, slotted armour plates, picture frames, patches, ~30 % calm; rivets on corners / ribs /
    armour edges only. Returns the stats dict (also log['layers'][tag])."""
    PL, R, LAY = K['plate'], K['rivet'], K['layer']
    TOP0 = PL['gap'] + PL['t']
    G2 = TOP0 + LAY
    base = rows + fills
    keepout = []

    def free_of_keepout(M, x, v, m=0.035):
        return not any(k[0] is M and k[1] - m <= x <= k[2] + m and k[3] - m <= v <= k[4] + m for k in keepout)

    SH, BT = K['shingle'], K['batten']
    battens = []
    byrow = {}
    for p in rows:
        byrow.setdefault((id(p['M']), p['row']), []).append(p)
    for key, ps in byrow.items():
        ps.sort(key=lambda p: p['x0'])
        for p in ps:
            p['raised'] = False
        for i, p in enumerate(ps):
            if i > 0 and ps[i - 1]['raised']:
                continue
            if rng.random() < SH['p']:
                p['raised'] = True
        for i, p in enumerate(ps):
            if not p['raised']:
                continue
            for j, side in ((i - 1, -1), (i + 1, 1)):
                if j < 0 or j >= len(ps):
                    continue
                q = ps[j]
                gx = (p['x0'] - (q['x0'] + q['W'])) if side < 0 else (q['x0'] - (p['x0'] + p['W']))
                v0 = max(p['v0'], q['v0']); v1 = min(p['v0'] + p['H'], q['v0'] + q['H'])
                if gx > 0.06 or v1 - v0 < 0.25:
                    continue
                ov = SH['overlap']
                if side < 0:
                    p['x0'] -= gx + ov; p['W'] += gx + ov
                    keepout.append((p['M'], p['x0'], p['x0'] + ov, p['v0'], p['v0'] + p['H']))
                else:
                    p['W'] += gx + ov
                    keepout.append((p['M'], p['x0'] + p['W'] - ov, p['x0'] + p['W'], p['v0'], p['v0'] + p['H']))
            p['kind'] = 'plate_raised'
            m0_ = p['mat']
            p['mat'] = style['armour'] if rng.random() < style.get('armour_p', SH['armour']) else p['mat']
            # zone 5 review fix 2026-11-28: no raised rust armour right at a belly frame's end ('sign on a post')
            if p['mat'] != m0_ and any(e[0] is p['M'] and p['x0'] - e[3] <= e[1] <= p['x0'] + p['W'] + e[3] and
                                       p['v0'] - e[3] <= e[2] <= p['v0'] + p['H'] + e[3]
                                       for e in style.get('no_armour_near', ())):
                p['mat'] = m0_
            p['armour'] = p['mat'] == style['armour']
        for a_, b_ in zip(ps, ps[1:]):
            if a_['raised'] or b_['raised']:
                continue
            gx = b_['x0'] - (a_['x0'] + a_['W'])
            v0 = max(a_['v0'], b_['v0']) - 0.02
            v1 = min(a_['v0'] + a_['H'], b_['v0'] + b_['H']) + 0.02
            if gx > 0.06 or v1 - v0 < 0.35 or rng.random() > BT['p']:
                continue
            xs_ = a_['x0'] + a_['W'] + gx / 2
            w = BT['w']
            battens.append(dict(M=a_['M'], x0=xs_ - w / 2, W=w, v0=v0, H=v1 - v0))
            keepout.append((a_['M'], xs_ - w / 2 - 0.02, xs_ + w / 2 + 0.02, v0, v1))
    raised = [p for p in rows if p.get('raised')]
    flat = [p for p in base if not p.get('raised')]

    SL = K['slots']
    slotted = []
    cand = [p for p in rows + fills if not p.get('raised') and p['W'] >= 0.75 and p['H'] >= 0.42]
    rng.shuffle(cand)

    def add_slot(p, w, h, u0=None, v0=None, n=None):
        u0 = rng.uniform(0.08, p['W'] - w - 0.08) if u0 is None else u0
        v0 = rng.uniform(0.07, max(0.071, p['H'] - h - 0.07)) if v0 is None else v0
        r_ = (p['x0'] + u0, p['x0'] + u0 + w, p['v0'] + v0, p['v0'] + v0 + h)
        if any(k[0] is p['M'] and overlaps(r_, k[1:], 0.03) for k in keepout):
            return False
        slotted.append(dict(plate=p, u0=u0, v0=v0, W=w, H=h, n=n or rng.choice(SL['n']), mat=p['mat']))
        keepout.append((p['M'],) + r_)
        p['busy'] = True
        return True
    n_sl = 0
    for p in cand:
        if n_sl >= style.get('slots', 3):
            break
        w = min(rng.uniform(*SL['w']), p['W'] - 0.16); h = min(rng.uniform(*SL['h']), p['H'] - 0.14)
        if w < 0.45 or h < 0.26:
            continue
        if n_sl == 0 and p['W'] >= 2 * w + 0.35 and style.get('slot_pair', True):
            w2 = w * 0.7
            if add_slot(p, w, h, u0=0.1) and add_slot(p, w2, h * 0.8, u0=p['W'] - w2 - 0.12, v0=p['H'] - h * 0.8 - 0.09,
                                                     n=2):
                n_sl += 2
                continue
        n_sl += int(add_slot(p, w, h))

    FR, PA = K['frame'], K['patch']
    frames, patches = [], []
    for p in flat:
        if p.get('busy') or p['kind'] == 'fill' and (p['W'] < 0.55 or p['H'] < 0.4):
            continue
        done = False
        fmin = style.get('frame_min', (FR['min_w'], FR['min_h']))
        if style.get('frames') and p['W'] >= fmin[0] and p['H'] >= fmin[1] and rng.random() < FR['p']:
            for e_ in (FR['edge'], 0.16):
                r_ = (p['x0'] + e_, p['x0'] + p['W'] - e_, p['v0'] + e_, p['v0'] + p['H'] - e_)
                if r_[1] - r_[0] < 0.4 or r_[3] - r_[2] < 0.3:
                    break
                if any(k[0] is p['M'] and overlaps(r_, k[1:], 0.0) for k in keepout):
                    continue
                frames.append(dict(plate=p, edge=e_, mat=style['frame_mat'](p['mat'])))
                keepout.append((p['M'],) + r_)
                p['busy'] = done = True
                break
        if done:
            continue
        if rng.random() < style.get('patch_p', PA['p']):
            w = min(rng.uniform(*PA['w']), p['W'] - 0.18); h = min(rng.uniform(*PA['h']), p['H'] - 0.14)
            if w < 0.3 or h < 0.24:
                continue
            x0 = p['x0'] + rng.uniform(0.09, p['W'] - w - 0.09)
            v0 = p['v0'] + rng.uniform(0.07, max(0.071, p['H'] - h - 0.07))
            r_ = (x0, x0 + w, v0, v0 + h)
            if any(k[0] is p['M'] and overlaps(r_, k[1:], 0.03) for k in keepout):
                continue
            patches.append(dict(plate=p, M=p['M'], x0=x0, W=w, v0=v0, H=h, mat=wchoice(rng, style['patch_mats'](p['mat'])),
                                corners=tuple(int(rng.random() < 0.25) for _ in range(4)), cut=rng.uniform(0.04, 0.09),
                                kind='patch'))
            keepout.append((p['M'],) + r_)
            p['busy'] = True
    calm = [p for p in flat if not p.get('busy')]

    nr = 0
    built = dict(base=0, raised=0, battens=0, frames=0, patches=0, slotted=0)
    for p in flat:
        top_fn = build_plate5(mesh, p, K, PL['gap'], PL['t'], PL['bevel'], log)
        if top_fn:
            built['base'] += 1
            if p['W'] * p['H'] >= 0.12:
                nr += plate_rivets5(mesh, top_fn, p['us'], p['vs'], R, p, lambda x, v, M=p['M']: free_of_keepout(M, x, v))
    for p in raised:
        top_fn = build_plate5(mesh, p, K, G2, SH['t'], PL['bevel'], log)
        if top_fn:
            built['raised'] += 1
            extra = []
            if p.get('armour'):
                k = max(1, int(round((p['W'] - 2 * R['inset']) / R['spacing'])))
                extra = [(R['inset'] + (p['W'] - 2 * R['inset']) * i / k, R['inset']) for i in range(1, k)]
            nr += plate_rivets5(mesh, top_fn, p['us'], p['vs'], R, p, lambda x, v: True, extra)
    for b in battens:
        f = b['M'].fn(b['x0'], b['v0'])
        top_fn, ok = D.solid_plate(mesh, f, np.array([0.0, b['W']]), D.grid_coords(0.0, b['H'], 0.3), G2, BT['t'], 0.012,
                                   style['batten'], kind='batten')
        if ok:
            built['battens'] += 1
            k = max(1, int(round((b['H'] - 0.12) / R['spacing'])))
            nr += D.rivet_row(mesh, top_fn, [(b['W'] / 2, 0.06 + (b['H'] - 0.12) * i / k) for i in range(k + 1)],
                              r=R['r'], h=R['h'])
    for fr in frames:
        p = fr['plate']
        if not p.get('top_fn'):
            continue
        W, H = p['W'] - 2 * fr['edge'], p['H'] - 2 * fr['edge']
        f = p['M'].fn(p['x0'] + fr['edge'], p['v0'] + fr['edge'])
        D.picture_frame(mesh, f, W, H, FR['rim'], G2, FR['t'], 0.012, fr['mat'], kind='frame')
        built['frames'] += 1
        top = lift_fn(f, G2 + FR['t'])
        nr += D.rivet_row(mesh, top, D.corner_pts(np.array([0.0, W]), np.array([0.0, H]), FR['rim'] / 2), r=R['r'], h=R['h'])
    for pa in patches:
        if not pa['plate'].get('top_fn'):
            continue
        top_fn = build_plate5(mesh, pa, K, G2, PA['t'], 0.012, log)
        if top_fn:
            built['patches'] += 1
            nr += plate_rivets5(mesh, top_fn, pa['us'], pa['vs'], dict(R, inset=0.05), pa, lambda x, v: True)
    for sl in slotted:
        p = sl['plate']
        if not p.get('top_fn'):
            continue
        f = p['M'].fn(p['x0'] + sl['u0'], p['v0'] + sl['v0'])
        if D.slotted_plate(mesh, f, sl['W'], sl['H'], G2, 0.035, 0.01, sl['mat'], n_slots=sl['n'], slot_w=SL['slot_w'],
                           ang=SL['ang']):
            built['slotted'] += 1
            top = lift_fn(f, G2 + 0.013 + 0.035)
            nr += D.rivet_row(mesh, top, [(0.045, 0.037), (sl['W'] - 0.045, 0.037), (0.045, sl['H'] - 0.037),
                                          (sl['W'] - 0.045, sl['H'] - 0.037)], r=0.018, h=0.01)
    area = lambda ps: sum(p['W'] * p['H'] for p in ps)
    st = dict(plates=len(base), raised=len(raised), armour=sum(1 for p in raised if p.get('armour')),
              battens=len(battens), slotted=len(slotted), frames=len(frames), patches=len(patches),
              calm_plates=len(calm), calm_share_of_area=round(area(calm) / max(1e-6, area(base)), 2),
              plate_area_m2=round(area(base), 1), built=built, rivets=nr)
    log.setdefault('layers', {})[tag or 'all'] = st
    return st


def bay(mesh, M, ba, va, W, H, K, rng, log, rim=0.09, rim_t=0.05, depth=0.11, pump=True, tank=True, tag='bay'):
    """zone 1's machinery bay on a mask rectangle [ba, ba+W] x [va, va+H]: riveted rust frame round a dark floor, a
    housing (hinged + latched lid) with flanged stubs, a pump body fed by a copper pipe, a gas bottle, a valve on the
    branch into a gland. Returns the number of rivets (0 when the surface is not there)."""
    R = K['rivet']
    PL = K['plate']
    f = M.fn(ba, va)
    if f(0.0, 0.0) is None or f(W, H) is None:
        return 0
    D.picture_frame(mesh, f, W, H, rim, PL['gap'], rim_t, 0.014, 'rust_red', kind='bay')
    D.solid_plate(mesh, f, D.grid_coords(rim + 0.008, W - rim - 0.008, 0.4), D.grid_coords(rim + 0.008, H - rim - 0.008, 0.3),
                  PL['gap'], 0.012, 0.003, 'dark_metal', kind='bay')
    top = lift_fn(f, PL['gap'] + rim_t)
    nr = D.rivet_row(mesh, top, D.corner_pts(np.array([0.0, W]), np.array([0.0, H]), rim / 2) +
                     [(W / 2, rim / 2), (W / 2, H - rim / 2)], r=R['r'], h=R['h'])
    floor = PL['gap'] + 0.012 + 0.002
    iu0, iu1 = rim + 0.06, W - rim - 0.06
    iv0, iv1 = rim + 0.06, H - rim - 0.06
    hw = min(0.8, 0.45 * (iu1 - iu0))
    hh = min(0.6, iv1 - iv0 - 0.1)
    hc_u, hc_v = iu0 + 0.04 + hw / 2, (iv0 + iv1) / 2
    q, q2 = f(hc_u, hc_v), f(hc_u + 0.1, hc_v)
    if q is None or q2 is None:
        return nr
    ends = D.housing(mesh, q[0] + q[1] * floor, q[1], D.unit(q2[0] - q[0]), hw, hh, depth, stubs=((1, -0.55), (-1, 0.5)))
    rest_u0 = hc_u + hw / 2 + 0.2
    Lp = iu1 - 0.05 - rest_u0
    if pump and Lp >= 0.42:
        pv = hc_v - hh * 0.22
        a_, b_ = f(rest_u0, pv), f(rest_u0 + Lp, pv)
        if a_ is not None and b_ is not None:
            rp = 0.068
            off = floor + 0.022 + rp
            pa_, pb_ = a_[0] + a_[1] * off, b_[0] + b_[1] * off
            tp = D.unit(pb_ - pa_)
            D.pump_body(mesh, pa_ + tp * 0.03, pb_, rp, a_[1])
            st, sd = ends[0]
            D.pipe_run(mesh, [st - sd * 0.01, st + sd * 0.06, pa_ - tp * 0.07, pa_ + tp * 0.045], 0.04, 0.06, sides=8,
                       mat='copper', flange_at=(), kind='bay')
        if tank:
            a2, b2 = f(rest_u0 + 0.05, hc_v + hh * 0.3), f(rest_u0 + 0.05 + max(0.36, Lp - 0.12), hc_v + hh * 0.3)
            if a2 is not None and b2 is not None:
                off2 = floor + 0.012 + 0.062
                D.tank(mesh, a2[0] + a2[1] * off2, b2[0] + b2[1] * off2, 0.062, a2[1], mat='rust_red')
    if len(ends) > 1:
        st, sd = ends[1]
        ug = max(rim * 0.5, hc_u - hw / 2 - 0.16)
        qa, qg = f(ug, hc_v + hh * 0.25), f(ug, rim * 0.5 - 0.0)
        if qa is not None and qg is not None:
            pmid = qa[0] + qa[1] * float(np.dot(st - qa[0], qa[1]))
            pg = qg[0] + qg[1] * (PL['gap'] + rim_t + 0.045)
            P_, _ = D.pipe_run(mesh, [st - sd * 0.01, st + sd * 0.06, pmid, pg, qg[0] + qg[1] * (PL['gap'] + rim_t - 0.01)],
                               0.035, 0.08, sides=8, mat='copper', flange_at=(0.5,), kind='bay')
            mid_i = len(P_) // 3
            valve_body5(mesh, P_[mid_i], D.unit(P_[mid_i + 1] - P_[mid_i - 1]), qa[1], 0.035)
            D.gland(mesh, qg[0], qg[1], D.unit(q2[0] - q[0]), 0.035, size=0.07, back=PL['gap'] + rim_t)
    log.setdefault('bays', []).append(dict(tag=tag, x=[round(ba, 2), round(ba + W, 2)], v=[round(va, 2), round(va + H, 2)]))
    return nr


def valve_body5(mesh, p, t, n, r, mat='brass', kind='valve'):
    """detail_common.valve_body (inline valve, no hand wheel) with the gauge disc sunk 6 mm into the bonnet: on the big
    channel pipe (r 6 cm) the shared one leaves the disc 2.8 cm off the bonnet's rim, so drop_floating removed it"""
    t = D.unit(t); n = D.unit(n - t * t.dot(n))
    w = np.cross(t, n)
    L = r * 3.2
    D.cylinder(mesh, D.vec(p) - t * L / 2, D.vec(p) + t * L / 2, r * 1.6, 6, mat, kind, smooth=False)
    b0 = D.vec(p) + w * r * 1.2
    D.cylinder(mesh, b0, b0 + w * r * 1.5, r * 0.85, 8, mat, kind, smooth=False)
    g0 = b0 + w * (r * 1.5 - 0.006)
    D.cylinder(mesh, g0, g0 + w * r * 0.35, r * 1.3, 12, 'dark_metal', kind, smooth=False)


def drop_intersecting(mesh, bvhs, kinds_keep=()):
    """remove every loose piece of `mesh` whose faces intersect any of `bvhs` (other zones' objects, moving parts at
    rest). Returns {kind: pieces removed}"""
    if not mesh.f or not bvhs:
        return {}
    fc, _ = mesh.components()
    det = BVHTree.FromPolygons(mesh.v, [list(f) for f in mesh.f])
    bad = set()
    for b in bvhs:
        for (i, _) in det.overlap(b):
            bad.add(int(fc[i]))
    drop = [i for i in range(len(mesh.f)) if int(fc[i]) in bad and mesh.k[i] not in kinds_keep]
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
