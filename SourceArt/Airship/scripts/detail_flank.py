"""Hull flank layout for the detail pass (round 3): the chart-based plate layout of zone 1, shared by every flank zone.

Moved here unchanged from detail_zone1.py on 2026-11-28 (zone 1 = the approved sample; its geometry is proven identical
after the move, see Docs/Airship/round3/ZONES.md). New parameters, all defaulting to zone 1's behaviour:
  Flank(ship, K, side=+1)       side -1 = starboard (FlankChart(side=-1)); the masks then keep off the FR / RR pockets
  K['regions']                  arc-length bands that find the gunwale ('up'), middle strip ('mid') and lower ('low')
                                runs of a chart column (zone 1's values are the default)
  K['mask_pods']                pods whose pockets the masks keep off (default FL, RL on port, FR, RR on starboard)
  build_flank(...) also writes log['continuity']: the reference lines and runs other zones continue (no randomness used)

Do not edit this module from a zone: pass knobs in K, or copy a function into your zone script and change the copy.
"""
import bpy, sys, os, math, random, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from mathutils import Vector as V
from mathutils.bvhtree import BVHTree
import rig_common as C
import detail_common as D
import detail_ship as S


def wchoice(rng, items):
    t = rng.random() * sum(w for _, w in items)
    for k, w in items:
        t -= w
        if t <= 0:
            return k
    return items[-1][0]


# ================================================================== hull flank
# arc-length bands (m from the deck edge) of the free runs in a chart column: gunwale rows, middle strip, lower flank
REGIONS = dict(up=(None, 1.1, 0.6), mid=(1.8, 3.0, 0.25), low=(3.0, 5.0, 0.5))      # (s0 >, s0 <, min length)


class Flank:
    def __init__(self, ship, K, side=1, obst_mask=None):
        """side +1 port, -1 starboard. obst_mask: SM_Airship polygons that count as covering geometry (default every
        polygon that is not the skin; pass ~deleted to ignore faces a base edit removes)"""
        self.K = K
        self.side = side
        self.ship = ship
        self.skin = ship.surface(ship.p_island == S.SKIN)
        self.obst = ship.bvh((ship.p_island != S.SKIN) if obst_mask is None else obst_mask)
        x0, x1, dx = K['chart_x']
        p0, p1, dp = K['chart_phi']
        self.chart = S.FlankChart(self.skin, self.obst, np.arange(x0, x1 + 1e-9, dx), np.arange(p0, p1 - 1e-9, dp),
                                  side=side, clear=K['chart_clear'])
        ch = self.chart
        jb = int(np.argmin(np.abs(np.degrees(ch.ph) - K['bilge_phi'])))
        self.s_lim = ch.s[:, jb]
        self.runs = [ch.runs(i, 0.2) for i in range(len(ch.xs))]
        self.reg = dict(REGIONS, **K.get('regions', {}))

    def region(self, x, name):
        i = self.chart.col(x)
        R = self.runs[i]
        if name == 'up':
            a, b, m = self.reg['up']
            r = next(((s0, s1) for (_, _, s0, s1) in R if (a is None or a < s0) and s0 < b and s1 - s0 > m), None)
        elif name == 'mid':
            a, b, m = self.reg['mid']
            r = next(((s0, s1) for (_, _, s0, s1) in R if a < s0 < b and s1 - s0 > m), None)
        else:
            a, b, m = self.reg['low']
            r = next(((s0, s1) for (_, _, s0, s1) in R if a <= s0 < b and s1 - s0 > m), None)
            if r is not None:
                lim = self.s_lim[i]
                if np.isnan(lim):
                    return None
                r = (r[0], min(r[1], float(lim)))
                if r[1] - r[0] < 0.5:
                    return None
        return r

    def fn(self, x0, a0, a1, W):
        """surface function of a sheared rectangle: u in [0, W] along x from x0, v down the section from the line
        s = a0 + (a1 - a0) u / W"""
        ch = self.chart

        def f(u, v):
            x = x0 + u
            s = a0 + (a1 - a0) * (u / W if W > 0 else 0) + v
            return ch.surf(x, s)
        return f


def rect_ok(fl, x0, W, a0, a1, H, pad=0.03):
    """chart test: the sheared rectangle (s from a0 + (a1 - a0) u / W, height H) lies on free skin"""
    ch = fl.chart
    for u in np.linspace(0, W, max(3, int(W / 0.05) + 1)):
        x = x0 + u
        s0 = a0 + (a1 - a0) * u / W
        if not ch.rect_free(x, x, s0, s0 + H, pad=pad, step=0.05):
            return False
    return True


# ------------------------------------------------------------------ row-aligned coverage masks
def smooth_ref(xs, raw, win=0.6):
    """fill the gaps of a per-x curve by interpolation and smooth it (moving average over +-win metres)"""
    raw = np.array(raw, float)
    ok = ~np.isnan(raw)
    if ok.sum() == 0:
        return np.full_like(raw, np.nan)
    filled = np.interp(xs, xs[ok], raw[ok])
    k = max(1, int(round(win / (xs[1] - xs[0]))))
    return np.array([filled[max(0, i - k):i + k + 1].mean() for i in range(len(xs))])


def median_ref(xs, raw, win=0.3):
    """fill gaps by interpolation, then a moving median (steps of the chart's arc length survive)"""
    raw = np.array(raw, float)
    ok = ~np.isnan(raw)
    if ok.sum() == 0:
        return np.full_like(raw, np.nan)
    filled = np.interp(xs, xs[ok], raw[ok])
    k = max(1, int(round(win / (xs[1] - xs[0]))))
    return np.array([np.median(filled[max(0, i - k):i + k + 1]) for i in range(len(xs))])


class RowMask:
    """Free hull skin in row-aligned chart coordinates (x, v) with s = ref(x) + v, so plate rows follow the band
    above them. Free = no other geometry within the chart clearance in front of the skin, away from breaks and
    creases, above the bilge limit, outside both pod pockets and the FL rim band, v <= v_hi(x)."""

    def __init__(self, fl, ship, xs, ref, v_hi, K, dv=0.04, rim_pts=(), name=''):
        ch = fl.chart
        self.fl, self.xs, self.ref, self.name = fl, np.asarray(xs), np.asarray(ref), name
        self.dx = float(xs[1] - xs[0])
        self.dv = dv
        vmax = float(np.nanmax(v_hi)) if np.isfinite(np.nanmax(v_hi)) else 0.0
        self.vs = np.arange(0.0, vmax + dv, dv)
        nx, nv = len(self.xs), len(self.vs)
        F = np.zeros((nx, nv), bool)
        free = ch.free()
        bad = ch.brk.copy()
        bad[:, :-1] |= ch.brk[:, 1:]
        pods = K.get('mask_pods') or (('FL', 'RL') if fl.side > 0 else ('FR', 'RR'))
        pockets = [ship.pod_frame(p) for p in pods]
        R = K['pocket']['r']
        for i, x in enumerate(self.xs):
            if np.isnan(self.ref[i]) or np.isnan(v_hi[i]):
                continue
            ci = ch.col(x)
            col = ch.s[ci]
            js = np.nonzero(~np.isnan(col))[0]
            lim = fl.s_lim[ci]
            if len(js) < 2 or np.isnan(lim):
                continue
            sv = col[js]
            ok = free[ci][js] & ~bad[ci][js]
            P = ch.P[ci][js]
            for (O, T0, A, NP) in pockets:
                rel = P - T0
                h = rel @ A
                d = np.linalg.norm(rel - np.outer(h, A), axis=1)
                ok &= ~((d < R + np.where(h < 0.5, 0.06, 0.16)) & (h > K['pocket']['roof_h'] - 0.06) & (h < 4.6))
            ss = self.ref[i] + self.vs
            k = np.clip(np.searchsorted(sv, ss), 1, len(sv) - 1)
            near = np.where(np.abs(sv[k - 1] - ss) < np.abs(sv[k] - ss), k - 1, k)
            F[i] = ok[near] & (np.abs(sv[near] - ss) < 0.06) & (ss <= lim) & (self.vs <= v_hi[i])
        for (x, s_) in rim_pts:
            i0 = int(round((x - self.xs[0]) / self.dx))
            for i in range(max(0, i0 - 3), min(nx, i0 + 4)):
                if np.isnan(self.ref[i]):
                    continue
                dd = np.hypot(self.xs[i] - x, self.vs - (s_ - self.ref[i]))
                F[i, dd < 0.09] = False
        E = F.copy()
        E[1:] &= F[:-1]; E[:-1] &= F[1:]; E[:, 1:] &= F[:, :-1]; E[:, :-1] &= F[:, 1:]
        self.free = E
        self.used = np.zeros_like(E)

    def ix(self, x):
        return int(round((x - self.xs[0]) / self.dx))

    def iv(self, v):
        return int(round(v / self.dv))

    def maxrect(self, x0, x1, v0, v1):
        """largest available rectangle inside the candidate, edges on cell borders (metres), or None"""
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
        self.used[i0:i1 + 1, m0:m1 + 1] = True

    def covered(self, x0, x1, v0, v1):
        i0, i1 = max(0, self.ix(x0)), min(len(self.xs) - 1, self.ix(x1))
        m0, m1 = max(0, self.iv(v0)), min(len(self.vs) - 1, self.iv(v1))
        return bool(self.used[i0:i1 + 1, m0:m1 + 1].all())

    def s_of(self, x, v):
        return float(np.interp(x, self.xs, self.ref)) + v

    def fn(self, x0, v0):
        ch = self.fl.chart

        def f(u, v):
            x = x0 + u
            return ch.surf(x, self.s_of(x, v0 + v))
        return f


def tile_rows(M, rng, cfg, K, kind='plate'):
    """staggered rows of plates over the mask; each candidate is clipped to the largest free rectangle inside it"""
    out = []
    seam = K['seam']
    v = 0.0
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


def overlaps(a, b, m=0.0):
    return not (a[1] + m <= b[0] or b[1] + m <= a[0] or a[3] + m <= b[2] or b[3] + m <= a[2])


def x_runs(ok_fn, xs, min_len, join=0.11):
    """[x0, x1] runs of consecutive x where ok_fn(i) holds, at least min_len long"""
    out = []
    for i, x in enumerate(xs):
        if not ok_fn(i):
            continue
        if out and x - out[-1][1] < join:
            out[-1][1] = x
        else:
            out.append([x, x])
    return [r for r in out if r[1] - r[0] >= min_len]


def on_step(f, W, H, tol):
    """does the patch [0, W] x [0, H] of f straddle a step in the skin? Fits a quadratic surface (along the mean normal)
    to a 6 x 5 sample of points; a residual over `tol` means a step / shelf, which would crumple a conforming plate."""
    P, N = [], []
    UV = []
    for u in np.linspace(0.0, W, 6):
        for v in np.linspace(0.0, H, 5):
            r = f(u, v)
            if r is None:
                return True
            P.append(r[0]); N.append(r[1]); UV.append((u, v))
    P = np.array(P); n = D.unit(np.mean(N, axis=0)); UV = np.array(UV)
    z = (P - P.mean(0)) @ n
    u, v = UV[:, 0], UV[:, 1]
    Amat = np.stack([np.ones_like(u), u, v, u * u, u * v, v * v], 1)
    c, *_ = np.linalg.lstsq(Amat, z, rcond=None)
    return float(np.abs(Amat @ c - z).max()) > tol


def plate_rivets(mesh, top_fn, us, vs, R, p, keep_fn, extra=()):
    """corner rivets (+ extra (u, v) points) on a plate, skipping points under a later layer"""
    pts = D.corner_pts(us, vs, R['inset'], p.get('cut_used', 0.0), p.get('corners_used', (0, 0, 0, 0))) + list(extra)
    pts = [(u, v) for (u, v) in pts if keep_fn(p['x0'] + u, p['v0'] + v)]
    return D.rivet_row(mesh, top_fn, pts, r=R['r'], h=R['h'])


def build_plate(mesh, p, K, gap, t, bevel, log):
    """p: dict(M, x0, W, v0, H, mat, corners, cut, kind) in the mask's (x, v) coordinates; returns top_fn or None.
    Plates that straddle a step in the skin are skipped (they would crumple)."""
    M = p['M']
    f = M.fn(p['x0'], p['v0'])
    if on_step(f, p['W'], p['H'], K['step_tol']):
        log['skipped_on_step'] = log.get('skipped_on_step', 0) + 1
        p['top_fn'] = None
        return None
    cuts = p.get('corners', (0, 0, 0, 0))
    cut = min(p.get('cut', 0.0), 0.3 * min(p['W'], p['H'])) if any(cuts) else 0.0
    us = D.grid_coords(0.0, p['W'], K['plate']['cell_u'], cut)
    vs = D.grid_coords(0.0, p['H'], K['plate']['cell_v'], cut)
    top_fn, ok = D.solid_plate(mesh, f, us, vs, gap, t, bevel, p['mat'], corners=cuts if cut > 0 else (0, 0, 0, 0),
                               kind=p.get('kind', 'plate'))
    p['top_fn'] = top_fn if ok else None
    p['us'], p['vs'], p['cut_used'], p['corners_used'] = us, vs, cut, (cuts if cut > 0 else (0, 0, 0, 0))
    p['top'] = gap + t
    return p['top_fn']


def build_flank(mesh, fl, ship, K, rng, log, rim_pts):
    XA, XB = K['x_aft'], K['x_fwd_plates']
    ch = fl.chart
    PL = K['plate']
    R = K['rivet']
    LAY = K['layer']
    TOP0 = PL['gap'] + PL['t']                       # base plate top above the skin
    G2 = TOP0 + LAY                                  # gap of anything resting on a base plate
    xs = np.arange(XA, XB + 1e-9, 0.05)
    up_raw = [(fl.region(x, 'up') or (np.nan,))[0] for x in xs]
    low_raw = [(fl.region(x, 'low') or (np.nan,))[0] for x in xs]
    lim = np.array([fl.s_lim[ch.col(x)] for x in xs])
    ref_up = smooth_ref(xs, up_raw) + K['upper']['top_off']
    low_s = median_ref(xs, low_raw, win=0.3)
    ref_low = low_s + K['lower']['top_off']
    v_hi_up = np.where(np.isnan(np.array(low_raw)), lim, np.array(low_raw) - 0.02) - ref_up
    v_hi_low = lim - ref_low
    MU = RowMask(fl, ship, xs, ref_up, v_hi_up, K, rim_pts=rim_pts, name='up')
    ML = RowMask(fl, ship, xs, ref_low, v_hi_low, K, rim_pts=rim_pts, name='low')
    for i in range(len(xs)):                         # the lower mask must not hand out what the upper one covers
        for m in range(len(ML.vs)):
            s_ = ML.ref[i] + ML.vs[m]
            if np.isnan(s_) or np.isnan(MU.ref[i]):
                continue
            mu = MU.iv(s_ - MU.ref[i])
            if 0 <= mu < len(MU.vs) and MU.free[i, mu]:
                ML.free[i, m] = False

    # ---------------------------------------------------------------- lower flank plan (before any plate is tiled)
    ST, TE, CH, BY = K['strake'], K['teeth'], K['channel'], K['bay']
    v_strip = ST['h'] + ST['back_h'] + 0.2            # strake + teeth strip (reserved over the whole length)
    m_strip = ML.iv(v_strip)
    strake_runs = x_runs(lambda i: m_strip < len(ML.vs) and bool(ML.free[i, 0:m_strip + 1].all()), xs, 0.8)
    mc0, mc1 = ML.iv(CH['v'][0]), ML.iv(CH['v'][1])
    spans = x_runs(lambda i: mc1 < len(ML.vs) and bool(ML.free[i, mc0:mc1 + 1].all()), xs, 1.4)
    log['strake_runs'] = [[round(a_, 2), round(b_, 2)] for a_, b_ in strake_runs]
    log['pipe_spans'] = [[round(a_, 2), round(b_, 2)] for a_, b_ in spans]
    ML.used[:, :ML.iv(CH['v'][0] - 0.02)] = True
    for (xa, xb) in spans:
        ML.used[ML.ix(xa):ML.ix(xb) + 1, ML.iv(CH['v'][0] - 0.02):ML.iv(CH['v'][1] + 0.04) + 1] = True
    bays = []
    m0, m1 = ML.iv(BY['v'][0] - 0.04), ML.iv(BY['v'][1] + 0.04)
    bay_runs = x_runs(lambda i: m1 < len(ML.vs) and bool(ML.free[i, m0:m1 + 1].all()) and not ML.used[i, m0:m1 + 1].any(),
                      xs, 1.5)
    log['bay_runs'] = [[round(a_, 2), round(b_, 2)] for a_, b_ in bay_runs]
    for (xa, xb) in bay_runs:
        L = xb - xa
        cand = [(xa + 0.08, xa + 0.08 + BY['w'][0]), (xb - 0.08 - BY['w'][1], xb - 0.08)] if L >= sum(BY['w']) + 0.45 else \
               [(xa + 0.08, xa + 0.08 + min(BY['w'][0], L - 0.16))]
        for (ba, bb) in cand:
            ML.used[ML.ix(ba - 0.05):ML.ix(bb + 0.05) + 1, m0:m1 + 1] = True
            bays.append((ba, bb))
    log['bays'] = [[round(a_, 2), round(b_, 2)] for a_, b_ in bays]
    UB = K['ubay']
    mu0, mu1 = MU.iv(UB['v'][0] - 0.04), MU.iv(UB['v'][1] + 0.04)
    ub_runs = x_runs(lambda i: mu1 < len(MU.vs) and bool(MU.free[i, mu0:mu1 + 1].all()), xs, 1.5)
    ubays = []
    for xp, w in zip(UB['x_pref'], UB['w']):
        for (xa, xb) in ub_runs:
            if xb - xa >= w + 0.1 and xa - 1.0 <= xp <= xb + 1.0:
                c = min(max(xp, xa + w / 2 + 0.05), xb - w / 2 - 0.05)
                if any(abs(c - (u0 + u1) / 2) < w for (u0, u1) in ubays):
                    continue
                ubays.append((c - w / 2, c + w / 2))
                MU.used[MU.ix(c - w / 2 - 0.05):MU.ix(c + w / 2 + 0.05) + 1, mu0:mu1 + 1] = True
                break
    log['upper_bays'] = [[round(a_, 2), round(b_, 2)] for a_, b_ in ubays]

    # ---------------------------------------------------------------- plates
    up_rows = tile_rows(MU, rng, K['upper'], K)
    low_rows = tile_rows(ML, rng, K['lower'], K)
    fills = fill_gaps(MU, rng, K['fill'], K) + fill_gaps(ML, rng, K['fill'], K)
    cov_u = MU.used[MU.free].mean() if MU.free.any() else 0
    log['plates'] = dict(up_rows=len(up_rows), low_rows=len(low_rows), fill=len(fills),
                         coverage_up=round(float(cov_u), 3),
                         free_m2_up=round(float(MU.free.sum() * MU.dx * MU.dv), 1),
                         free_m2_low=round(float(ML.free.sum() * ML.dx * ML.dv), 1))
    base = up_rows + low_rows + fills
    keepout = []                                      # (mask, x0, x1, v0, v1): later layers sit here

    def plate_at(M, x, v):
        for q in base:
            if q['M'] is M and q['x0'] - 0.012 <= x <= q['x0'] + q['W'] + 0.012 and q['v0'] - 0.012 <= v <= q['v0'] + q['H'] + 0.012:
                return q
        return None

    def free_of_keepout(M, x, v, m=0.035):
        return not any(k[0] is M and k[1] - m <= x <= k[2] + m and k[3] - m <= v <= k[4] + m for k in keepout)

    def in_mid(p):
        xm = p['x0'] + p['W'] / 2
        r_ = fl.region(xm, 'mid')
        return r_ is not None and r_[0] - 0.05 <= MU.s_of(xm, p['v0'])

    # ---- shingles (raised plates overlapping both row neighbours; some of them heavy rust armour) and frame ribs
    SH, BT = K['shingle'], K['batten']
    battens = []
    byrow = {}
    for p in up_rows + low_rows:
        byrow.setdefault((p['M'].name, p['row']), []).append(p)
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
            p['mat'] = 'rust_red' if rng.random() < SH['armour'] else p['mat']
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
    raised = [p for p in up_rows + low_rows if p.get('raised')]
    flat = [p for p in base if not p.get('raised')]

    # ---- slotted armour plates (reference 1): a few, at irregular places on the upper rows and the middle strip
    SL = K['slots']
    slotted = []
    up_c = [p for p in up_rows if not p.get('raised') and p['W'] >= 0.95 and p['H'] >= 0.5 and not in_mid(p)]
    mid_c = [p for p in up_rows + fills if p['M'] is MU and not p.get('raised') and p['W'] >= 0.7 and p['H'] >= 0.36
             and in_mid(p)]
    rng.shuffle(up_c); rng.shuffle(mid_c)

    def add_slot(p, w, h, u0=None, v0=None):
        u0 = rng.uniform(0.08, p['W'] - w - 0.08) if u0 is None else u0
        v0 = rng.uniform(0.07, max(0.071, p['H'] - h - 0.07)) if v0 is None else v0
        r_ = (p['x0'] + u0, p['x0'] + u0 + w, p['v0'] + v0, p['v0'] + v0 + h)
        if any(k[0] is p['M'] and overlaps(r_, k[1:], 0.03) for k in keepout):
            return False
        slotted.append(dict(plate=p, u0=u0, v0=v0, W=w, H=h, n=rng.choice(SL['n']), mat=p['mat']))
        keepout.append((p['M'],) + r_)
        p['busy'] = True
        return True
    n_up = 0
    for k_, p in enumerate(up_c):
        if n_up >= SL['up']:
            break
        w = rng.uniform(*SL['w']); h = min(rng.uniform(*SL['h']), p['H'] - 0.14)
        if w > p['W'] - 0.16 or h < 0.26:
            continue
        if n_up == 0 and p['W'] >= 2 * w + 0.35:
            # two different slotted plates side by side on one wide plate (breaks the one-item-per-panel rhythm)
            w2 = w * 0.7
            if add_slot(p, w, h, u0=0.1) and add_slot(p, w2, h * 0.8, u0=p['W'] - w2 - 0.12, v0=p['H'] - h * 0.8 - 0.09):
                n_up += 2
                continue
        n_up += int(add_slot(p, w, h))
    n_mid = 0
    for p in mid_c:
        if n_mid >= SL['mid']:
            break
        w = min(0.5, p['W'] - 0.2); h = min(0.3, p['H'] - 0.1)
        if w < 0.4 or h < 0.24:
            continue
        if add_slot(p, w, h, u0=(p['W'] - w) * rng.uniform(0.2, 0.8), v0=(p['H'] - h) / 2):
            slotted[-1]['n'] = 2
            n_mid += 1

    # ---- picture-frame plates (raised rim, lower centre; some with a dark inset = recessed panel) and rust patches
    FR, PA = K['frame'], K['patch']
    frames, patches = [], []
    why = {}
    for p in flat:
        if p.get('busy') or p['kind'] == 'fill' and (p['W'] < 0.55 or p['H'] < 0.4):
            why['busy_or_small_fill'] = why.get('busy_or_small_fill', 0) + 1
            continue
        why['eligible'] = why.get('eligible', 0) + 1
        done = False
        if p['W'] >= FR['min_w'] and p['H'] >= FR['min_h'] and rng.random() < FR['p']:
            for e_ in (FR['edge'], 0.16):
                r_ = (p['x0'] + e_, p['x0'] + p['W'] - e_, p['v0'] + e_, p['v0'] + p['H'] - e_)
                if r_[1] - r_[0] < 0.4 or r_[3] - r_[2] < 0.3:
                    break
                if any(k[0] is p['M'] and overlaps(r_, k[1:], 0.0) for k in keepout):
                    continue
                frames.append(dict(plate=p, edge=e_, inset=rng.random() < FR['inset_p'],
                                   mat='paint_ochre' if p['mat'] == 'paint_yellow' else 'paint_yellow'))
                keepout.append((p['M'],) + r_)
                p['busy'] = done = True
                break
        if done:
            continue
        if rng.random() < PA['p']:
            w = min(rng.uniform(*PA['w']), p['W'] - 0.18); h = min(rng.uniform(*PA['h']), p['H'] - 0.14)
            if w < 0.3 or h < 0.24:
                why['patch_too_small'] = why.get('patch_too_small', 0) + 1
                continue
            x0 = p['x0'] + rng.uniform(0.09, p['W'] - w - 0.09)
            v0 = p['v0'] + rng.uniform(0.07, max(0.071, p['H'] - h - 0.07))
            r_ = (x0, x0 + w, v0, v0 + h)
            if any(k[0] is p['M'] and overlaps(r_, k[1:], 0.03) for k in keepout):
                why['patch_keepout'] = why.get('patch_keepout', 0) + 1
                continue
            patches.append(dict(plate=p, M=p['M'], x0=x0, W=w, v0=v0, H=h, mat=wchoice(rng, PA['mats']),
                                corners=tuple(int(rng.random() < 0.25) for _ in range(4)), cut=rng.uniform(0.04, 0.09),
                                kind='patch'))
            keepout.append((p['M'],) + r_)
            p['busy'] = True
    calm = [p for p in flat if not p.get('busy')]
    log['frame_patch_reasons'] = why
    log['layers'] = dict(raised=len(raised), armour=sum(p['mat'] == 'rust_red' for p in raised), battens=len(battens),
                         slotted=len(slotted), frames=len(frames), patches=len(patches),
                         calm_plates=len(calm), calm_share_of_area=round(sum(p['W'] * p['H'] for p in calm) /
                                                                      max(1e-6, sum(p['W'] * p['H'] for p in base)), 2))

    # ---------------------------------------------------------------- geometry: plates and their layers
    nr = 0
    for p in flat:
        top_fn = build_plate(mesh, p, K, PL['gap'], PL['t'], PL['bevel'], log)
        if top_fn and p['W'] * p['H'] >= 0.12:
            nr += plate_rivets(mesh, top_fn, p['us'], p['vs'], R, p,
                               lambda x, v, M=p['M']: free_of_keepout(M, x, v))
    for p in raised:
        gapR = G2
        top_fn = build_plate(mesh, p, K, gapR, SH['t'], PL['bevel'], log)
        if top_fn:
            extra = []
            if p['mat'] == 'rust_red':                  # heavy armour: a rivet row along the top edge
                k = max(1, int(round((p['W'] - 2 * R['inset']) / R['spacing'])))
                extra = [(R['inset'] + (p['W'] - 2 * R['inset']) * i / k, R['inset']) for i in range(1, k)]
            nr += plate_rivets(mesh, top_fn, p['us'], p['vs'], R, p, lambda x, v: True, extra)
    for b in battens:
        f = b['M'].fn(b['x0'], b['v0'])
        top_fn, ok = D.solid_plate(mesh, f, np.array([0.0, b['W']]), D.grid_coords(0.0, b['H'], 0.3), G2, BT['t'], 0.012,
                                   BT['mat'], kind='batten')
        if ok:
            k = max(1, int(round((b['H'] - 0.12) / R['spacing'])))
            nr += D.rivet_row(mesh, top_fn, [(b['W'] / 2, 0.06 + (b['H'] - 0.12) * i / k) for i in range(k + 1)],
                              r=R['r'], h=R['h'])
    for fr in frames:
        p = fr['plate']
        if not p.get('top_fn'):
            continue
        f = p['M'].fn(p['x0'] + fr['edge'], p['v0'] + fr['edge'])
        W, H = p['W'] - 2 * fr['edge'], p['H'] - 2 * fr['edge']
        D.picture_frame(mesh, f, W, H, FR['rim'], G2, FR['t'], 0.012, fr['mat'], kind='frame')
        if fr['inset']:
            D.solid_plate(mesh, f, D.grid_coords(FR['rim'] + 0.02, W - FR['rim'] - 0.02, 0.4),
                          D.grid_coords(FR['rim'] + 0.02, H - FR['rim'] - 0.02, 0.3), G2, 0.008, 0.002, 'dark_metal',
                          kind='frame')
        top = lambda u, v, f=f: (lambda r: None if r is None else (r[0] + r[1] * (G2 + FR['t']), r[1]))(f(u, v))
        nr += D.rivet_row(mesh, top, D.corner_pts(np.array([0.0, W]), np.array([0.0, H]), FR['rim'] / 2), r=R['r'], h=R['h'])
    for pa in patches:
        if not pa['plate'].get('top_fn'):
            continue
        top_fn = build_plate(mesh, pa, K, G2, PA['t'], 0.012, log)
        if top_fn:
            nr += plate_rivets(mesh, top_fn, pa['us'], pa['vs'], dict(R, inset=0.05), pa, lambda x, v: True)
    for sl in slotted:
        p = sl['plate']
        if not p.get('top_fn'):
            continue
        f = p['M'].fn(p['x0'] + sl['u0'], p['v0'] + sl['v0'])
        if D.slotted_plate(mesh, f, sl['W'], sl['H'], G2, 0.035, 0.01, sl['mat'], n_slots=sl['n'], slot_w=SL['slot_w'],
                           ang=SL['ang']):
            top = lambda u, v, f=f: (lambda r: None if r is None else (r[0] + r[1] * (G2 + 0.013 + 0.035), r[1]))(f(u, v))
            nr += D.rivet_row(mesh, top, [(0.045, 0.037), (sl['W'] - 0.045, 0.037), (0.045, sl['H'] - 0.037),
                                          (sl['W'] - 0.045, sl['H'] - 0.037)], r=0.018, h=0.01)

    # ---------------------------------------------------------------- strake, dark backing and teeth (reference 1)
    nteeth = 0
    # the strake runs on a smoothed reference line (no wobble) in segments of one tooth pitch each (seams like a real
    # strake's plate joins); a segment whose skin patch has a shelf in it is shifted or left out, so nothing bends
    # robust line: a cubic per strake run fitted to the lower rows' reference with outliers (the reference dips under
    # the ship's own hardware below the band) removed; segments that would cover that hardware are left out
    ref_st = smooth_ref(xs, ML.ref, win=ST['smooth'])
    for (xa, xb) in strake_runs:
        m_ = (xs >= xa - 1e-6) & (xs <= xb + 1e-6) & ~np.isnan(ML.ref)
        xx, yy = xs[m_], ML.ref[m_]
        keep = np.ones(len(xx), bool)
        for _ in range(4):
            c_ = np.polyfit(xx[keep], yy[keep], 3 if xb - xa > 3.0 else 1)
            res = np.abs(np.polyval(c_, xx) - yy)
            keep = res < max(0.03, np.percentile(res, 70))
        ref_st[m_] = np.polyval(c_, xx)

    def seg_free(x0, L):
        for xq in np.linspace(x0, x0 + L, 7):
            r0 = float(np.interp(xq, xs, ref_st))
            for vq in (0.0, 0.1, 0.2, 0.4, 0.6, 0.8):
                if not ch.free_at(xq, r0 + vq, 0.0):
                    return False
        return True

    def fn_st(x0, v0):
        def f(u, v):
            x = x0 + u
            return ch.surf(x, float(np.interp(x, xs, ref_st)) + v0 + v)
        return f
    gT = PL['gap'] + ST['back_t'] + LAY
    nseg = nskip = 0
    cont_seg = []                                    # continuity export only (no effect on the geometry)
    for (xa, xb) in strake_runs:
        x = xa + 0.02
        while x < xb - 0.5:
            w = rng.uniform(*TE['w'])
            g = rng.uniform(*TE['gap'])
            L = min(w + g, xb - x)
            f = fn_st(x, 0.0)
            if not seg_free(x, L) or on_step(f, L, ST['h'] + ST['back_h'], K['step_tol']):
                x += 0.1
                nskip += 1
                continue
            D.solid_plate(mesh, f, D.grid_coords(0.0, L - 0.008, 0.5), D.grid_coords(0.0, ST['h'], 0.25), PL['gap'],
                          ST['t'], 0.016, 'rust_red', kind='strake')
            top = lambda u, v, f=f: (lambda r: None if r is None else (r[0] + r[1] * (PL['gap'] + ST['t']), r[1]))(f(u, v))
            nr += D.rivet_row(mesh, top, [(0.08, ST['h'] / 2), ((L - 0.008) / 2, ST['h'] / 2), (L - 0.088, ST['h'] / 2)],
                              r=R['r'], h=R['h'])
            fb = fn_st(x, ST['h'] + 0.004)
            D.solid_plate(mesh, fb, D.grid_coords(0.0, L - 0.008, 0.5), D.grid_coords(0.0, ST['back_h'], 0.3), PL['gap'],
                          ST['back_t'], 0.004, 'dark_metal', kind='strake')
            nseg += 1
            cont_seg.append(dict(x0=round(float(x), 4), L=round(float(L), 4),
                                 top0=f(0.0, 0.0), top1=f(L - 0.008, 0.0), bot0=fb(0.0, ST['back_h']),
                                 bot1=fb(L - 0.008, ST['back_h'])))
            if L >= w + 0.06:
                h = rng.uniform(*TE['h'])
                v0 = ST['h'] + 0.008
                xt = x + g / 2
                ft = fn_st(xt, v0)
                cut = TE['chamfer']
                us = D.grid_coords(0.0, w, 0.45, cut); vs = D.grid_coords(0.0, h, 0.3, cut)
                if not on_step(ft, w, h, K['step_tol']):
                    top_fn, ok = D.solid_plate(mesh, ft, us, vs, gT, TE['t'], 0.014, 'rust_red', corners=(0, 0, 1, 0),
                                               kind='tooth')
                    if ok:
                        nteeth += 1
                        nr += D.rivet_row(mesh, top_fn, [(0.1, 0.07), (w - 0.1, 0.07)], r=R['r'], h=R['h'])
            x += L
    log['strake'] = dict(segments=nseg, shifted_for_a_shelf=nskip)
    log['teeth'] = nteeth

    # ---------------------------------------------------------------- gussets under the gunwale band
    G = K['gusset']
    ng = 0
    cont_gus = []
    for x in np.arange(XA + 0.35, XB - 0.1, G['step']):
        r = fl.region(x, 'up')
        if r is None:
            continue
        s = r[0] + 0.012
        a = ch.surf(x, s); b = ch.surf(x, s + 0.08)
        if a is None or b is None or not ch.free_at(x, s + G['height'] / 2, G['height'] / 2):
            continue
        D.gusset(mesh, a[0] + a[1] * 0.004, a[1], D.unit(a[0] - b[0]), G['depth'], G['height'], G['t'])
        ng += 1
        cont_gus.append(dict(x=round(float(x), 4), s=round(float(s), 4), p=a[0]))
    log['gussets'] = ng

    def surf_below(pt):
        r = fl.skin.nearest(pt, 1.0)
        return (r[0], r[1]) if r is not None else None

    # ---------------------------------------------------------------- pipe channel: dark backing, two big pipes, valve
    npipe = 0
    chan = {}
    cont_chan = []
    for (xa, xb) in spans:
        f = ML.fn(xa + 0.05, CH['v'][0])
        L = xb - xa - 0.1
        D.solid_plate(mesh, f, D.grid_coords(0.0, L, 0.5), D.grid_coords(0.0, CH['v'][1] - CH['v'][0], 0.25), PL['gap'],
                      0.015, 0.004, 'dark_metal', kind='channel')
        base_off = PL['gap'] + 0.015
        vv = (CH['v'][0] + 0.13, CH['v'][0] + 0.37)
        for k, (rp, v_) in enumerate(zip(CH['r'], vv)):
            off = base_off + 0.006 + rp
            pts = []
            for x in np.linspace(xa + 0.32, xb - 0.32, max(4, int((xb - xa) / 0.35))):
                q = ch.surf(x, ML.s_of(x, v_))
                if q is None:
                    pts = None
                    break
                pts.append(q[0] + q[1] * off)
            q0 = ch.surf(xa + 0.14, ML.s_of(xa + 0.14, v_)); q1 = ch.surf(xb - 0.14, ML.s_of(xb - 0.14, v_))
            if not pts or q0 is None or q1 is None:
                continue
            path = [q0[0] - q0[1] * 0.02] + pts + [q1[0] - q1[1] * 0.02]
            ncl = max(1, int((xb - xa) / CH['clamp_step']))
            D.pipe_run(mesh, path, rp, 0.16, sides=12, mat='copper' if k == 0 else 'brass', flange_at=(0.2, 0.5, 0.8),
                       flange_k=1.25, clamp_at=[(i + 0.5) / ncl for i in range(ncl)], surf_fn=surf_below, kind='pipe')
            for q in (q0, q1):
                D.gland(mesh, q[0], q[1], (1, 0, 0), rp, size=rp * 1.9, back=base_off)
            if k == 0 and len(pts) > 4:
                i = len(pts) // 3
                xv = xa + 0.32 + (xb - xa - 0.64) * i / (len(pts) - 1)
                nq = ch.surf(xv, ML.s_of(xv, v_))
                if nq is not None:
                    D.valve_body(mesh, pts[i], D.unit(pts[i + 1] - pts[i - 1]), nq[1], rp * 0.88)
            chan[(xa, xb, k)] = (v_, off, rp)
            cont_chan.append(dict(span=[round(float(xa), 3), round(float(xb), 3)], pipe=k, v=v_, centre_off=off, r=rp,
                                  end_aft=path[0], first=path[1], last=path[-2], end_fwd=path[-1]))
            npipe += 1
    log['pipes'] = npipe

    # ---------------------------------------------------------------- machinery bays (hero clusters)
    def bay_shell(f, W, H, rim, rim_t):
        """a riveted rust frame round a dark floor (the recess the machinery sits in); returns the floor height"""
        D.picture_frame(mesh, f, W, H, rim, PL['gap'], rim_t, 0.014, 'rust_red', kind='bay')
        D.solid_plate(mesh, f, D.grid_coords(rim + 0.008, W - rim - 0.008, 0.4),
                      D.grid_coords(rim + 0.008, H - rim - 0.008, 0.3), PL['gap'], 0.012, 0.003, 'dark_metal', kind='bay')
        top = lambda u, v: (lambda r: None if r is None else (r[0] + r[1] * (PL['gap'] + rim_t), r[1]))(f(u, v))
        n_ = D.rivet_row(mesh, top, D.corner_pts(np.array([0.0, W]), np.array([0.0, H]), rim / 2) +
                         [(W / 2, rim / 2), (W / 2, H - rim / 2)], r=R['r'], h=R['h'])
        return PL['gap'] + 0.012 + 0.002, n_

    def frame_at(f, u, v):
        q = f(u, v); q2 = f(u + 0.1, v)
        if q is None or q2 is None:
            return None
        return q[0], q[1], D.unit(q2[0] - q[0])

    nb_ = 0
    for bi, (ba, bb) in enumerate(bays):
        W = bb - ba
        v0, v1 = BY['v']
        H = v1 - v0
        f = ML.fn(ba, v0)
        floor, n_ = bay_shell(f, W, H, BY['rim'], BY['rim_t'])
        nr += n_
        iu0, iu1 = BY['rim'] + 0.06, W - BY['rim'] - 0.06
        iv0, iv1 = BY['rim'] + 0.06, H - BY['rim'] - 0.06
        hw = min(0.92, 0.45 * (iu1 - iu0))
        hh = min(0.62, iv1 - iv0 - 0.12)
        hc_u, hc_v = iu0 + 0.04 + hw / 2, (iv0 + iv1) / 2
        fr = frame_at(f, hc_u, hc_v)
        if fr is None:
            continue
        ends = D.housing(mesh, fr[0] + fr[1] * floor, fr[1], fr[2], hw, hh, BY['depth'], stubs=((1, -0.55), (-1, 0.5)))
        nb_ += 1
        rest_u0 = hc_u + hw / 2 + 0.2
        Lp = iu1 - 0.05 - rest_u0
        pump_v = hc_v - hh * 0.22
        if Lp >= 0.42:
            a_ = f(rest_u0, pump_v); b_ = f(rest_u0 + Lp, pump_v)
            if a_ is not None and b_ is not None:
                rpump = BY['pump_r']
                off = floor + 0.022 + rpump
                pa_ = a_[0] + a_[1] * off; pb_ = b_[0] + b_[1] * off
                tp = D.unit(pb_ - pa_)
                D.pump_body(mesh, pa_ + tp * 0.03, pb_, rpump, a_[1])
                st, sd = ends[0]                       # housing stub (+u side, upper) -> pump cover
                D.pipe_run(mesh, [st - sd * 0.01, st + sd * 0.06, pa_ - tp * 0.07, pa_ + tp * 0.045],
                           0.04, 0.06, sides=8, mat='copper', flange_at=(), kind='bay')
            a2 = f(rest_u0 + 0.05, hc_v + hh * 0.3); b2 = f(rest_u0 + 0.05 + max(0.36, Lp - 0.12), hc_v + hh * 0.3)
            if a2 is not None and b2 is not None:
                off2 = floor + 0.012 + 0.062
                D.tank(mesh, a2[0] + a2[1] * off2, b2[0] + b2[1] * off2, 0.062, a2[1], mat='rust_red')
        # branch from the housing's other stub (-u side, lower) up to the channel's lower pipe (a tee), with a valve
        key = next((kk for kk in chan if kk[2] == 1 and kk[0] - 0.01 <= ba and bb <= kk[1] + 0.01), None)
        if key is not None and len(ends) > 1:
            v_, offc, rpc = chan[key]
            st, sd = ends[1]
            xb_ = ba + hc_u - hw / 2 - 0.16
            qa = ch.surf(xb_, ML.s_of(xb_, v0 + hc_v + hh * 0.25))
            qt = ch.surf(xb_, ML.s_of(xb_, v_))
            if qa is not None and qt is not None:
                pmid = qa[0] + qa[1] * (np.dot(st - qa[0], qa[1]))
                ptee = qt[0] + qt[1] * offc
                P_, _ = D.pipe_run(mesh, [st - sd * 0.01, st + sd * 0.06, pmid, ptee], 0.04, 0.09, sides=8, mat='copper',
                                   flange_at=(0.55,), kind='bay')
                mid_i = len(P_) // 2
                D.valve_body(mesh, P_[mid_i], D.unit(P_[mid_i + 1] - P_[mid_i - 1]), qa[1], 0.04)
    # upper bays: two smaller housings joined by a flanged pipe with a valve, a riser into the hull through a gland
    for (ba, bb) in ubays:
        W = bb - ba
        v0, v1 = UB['v']
        H = v1 - v0
        f = MU.fn(ba, v0)
        floor, n_ = bay_shell(f, W, H, UB['rim'], BY['rim_t'])
        nr += n_
        iu0, iu1 = UB['rim'] + 0.05, W - UB['rim'] - 0.05
        iv0, iv1 = UB['rim'] + 0.05, H - UB['rim'] - 0.05
        hw = min(0.56, (iu1 - iu0 - 0.3) / 2)
        hh = min(0.42, iv1 - iv0 - 0.1)
        c1 = (iu0 + 0.05 + hw / 2, (iv0 + iv1) / 2 + 0.02)
        c2 = (iu1 - 0.05 - hw / 2, (iv0 + iv1) / 2 - 0.03)
        f1, f2 = frame_at(f, *c1), frame_at(f, *c2)
        if f1 is None or f2 is None:
            continue
        e1 = D.housing(mesh, f1[0] + f1[1] * floor, f1[1], f1[2], hw, hh, UB['depth'], stubs=((1, -0.3),), r_stub=0.035)
        e2 = D.housing(mesh, f2[0] + f2[1] * floor, f2[1], f2[2], hw * 0.85, hh * 0.9, UB['depth'], stubs=((-1, 0.2),),
                       r_stub=0.035)
        nb_ += 2
        (a_, da), (b_, db) = e1[0], e2[0]
        P_, _ = D.pipe_run(mesh, [a_ - da * 0.01, a_ + da * 0.05, b_ + db * 0.05, b_ - db * 0.01], 0.035, 0.06, sides=8,
                           mat='brass', flange_at=(0.5,), kind='bay')
        mid_i = len(P_) // 2
        D.valve_body(mesh, P_[mid_i], D.unit(P_[mid_i + 1] - P_[mid_i - 1]), f1[1], 0.035)
        # riser from the first housing's top edge up through the bay frame into the hull
        ut = c1[0] - hw * 0.25
        qs = [f(ut, c1[1] - hh / 2 + 0.04), f(ut, UB['rim'] * 0.5 - 0.1), f(ut, UB['rim'] * 0.5 - 0.22)]
        if all(q is not None for q in qs):
            dep = floor + UB['depth'] * 0.5
            path = [qs[0][0] + qs[0][1] * dep, qs[1][0] + qs[1][1] * (PL['gap'] + BY['rim_t'] + 0.04),
                    qs[2][0] - qs[2][1] * 0.02]
            D.pipe_run(mesh, path, 0.03, 0.08, sides=8, mat='copper', flange_at=(), kind='bay')
            xg = ba + ut
            D.gland(mesh, qs[2][0], qs[2][1], (1, 0, 0), 0.03, size=0.06,
                    back=(lambda q: q.get('top', TOP0) if q and q.get('top_fn') else 0.0)(
                        plate_at(MU, xg, v0 + UB['rim'] * 0.5 - 0.22)))
    log['bays_built'] = nb_

    # ---------------------------------------------------------------- conduits: a pair along the bottom of the upper rows,
    #      one along the middle strip; over every plate layer, clamped, every end in a gland; through-hull fittings
    CD = K['conduit']
    top_all_c = G2 + max(SH['t'], BT['t'], 0.048) + 0.008

    def runs_of(fun):
        out, cur = [], []
        for x in np.arange(XA + 0.15, XB - 0.1, 0.25):
            sv = fun(x)
            q = ch.surf(x, sv) if sv is not None else None
            if q is None or not ch.free_at(x, sv, 0.05):
                if len(cur) >= 5:
                    out.append(cur)
                cur = []
                continue
            cur.append((x, q))
        if len(cur) >= 5:
            out.append(cur)
        return out

    def base_top(x, s):
        """height of the plate layer under (x, s) on the upper mask (0 on bare skin)"""
        q = plate_at(MU, x, s - float(np.interp(x, MU.xs, MU.ref)))
        if q is None or not q.get('top_fn'):
            return 0.0
        return q.get('top', TOP0)
    ncond = 0
    nfit = 0
    cont_cond = []
    # (the middle strip under the big steam pipe is a row of stepped blocks: a conduit there wobbles over the steps, so
    #  it only gets plates and small slotted plates)
    for fun, radii, dv, name in ((lambda x: (lambda r: r[1] - 0.06 if r else None)(fl.region(x, 'up')), CD['r_up'], 0.095, 'up'),):
        for run in runs_of(fun):
            run = run[1:-1]                              # ends well inside the free skin
            if len(run) < 5:
                continue
            rx = np.array([x for (x, _) in run])
            rs = smooth_ref(rx, [fun(x) for x in rx], win=CD['smooth'])   # no wobble: a smooth line along the run
            for k, rr in enumerate(radii):
                pts, xs_r = [], []
                for x, s0 in zip(rx, rs):
                    sv = s0 - k * dv
                    qq = ch.surf(x, sv)
                    if qq is None:
                        continue
                    pts.append(qq[0] + qq[1] * (top_all_c + rr)); xs_r.append((x, sv))
                if len(pts) < 5:
                    continue
                (xa_, sa_), (xb_, sb_) = xs_r[0], xs_r[-1]
                qa, qb = ch.surf(xa_, sa_), ch.surf(xb_, sb_)
                # each end drops straight into a gland
                path = [qa[0] - qa[1] * 0.02] + pts + [qb[0] - qb[1] * 0.02]
                n_cl = max(2, int(len(pts) * 0.25 / CD['clamp_step']))
                D.pipe_run(mesh, path, rr, 0.08, sides=8, mat='dark_metal' if k == 0 else 'brass', flange_at=(),
                           clamp_at=[(i + 0.5) / n_cl for i in range(n_cl)], surf_fn=surf_below, kind='conduit')
                for (xx, ss), q in (((xa_, sa_), qa), ((xb_, sb_), qb)):
                    D.gland(mesh, q[0], q[1], (1, 0, 0), rr, size=0.065, back=base_top(xx, ss))
                ncond += 1
                cont_cond.append(dict(pipe=k, r=rr, x=[round(float(xa_), 3), round(float(xb_), 3)],
                                      s=[round(float(sa_), 4), round(float(sb_), 4)], centre_off=top_all_c + rr,
                                      end_aft=path[1], end_fwd=path[-2]))
                if name == 'up' and k == 0:
                    # through-hull fittings: a branch rises from the conduit and enters the hull through a gland
                    L = xs_r[-1][0] - xs_r[0][0]
                    cands = sorted(rng.sample(list(np.arange(xs_r[0][0] + 0.7, xs_r[-1][0] - 0.7, 0.25)),
                                              k=min(8, max(0, int((L - 1.4) / 0.25)))))
                    last = -99.0
                    for xf in cands:
                        if nfit >= CD['fittings'] or xf - last < 1.6:
                            continue
                        sv = float(np.interp(xf, rx, rs))
                        q0 = ch.surf(xf, sv); q1 = ch.surf(xf, sv - 0.2); q2 = ch.surf(xf, sv - 0.3)
                        if q0 is None or q1 is None or q2 is None or not free_of_keepout(MU, xf, sv - 0.3 - float(np.interp(xf, MU.xs, MU.ref)), 0.08):
                            continue
                        off = top_all_c + rr
                        D.pipe_run(mesh, [q0[0] + q0[1] * off, q1[0] + q1[1] * off, q2[0] - q2[1] * 0.02], 0.028, 0.07,
                                   sides=8, mat='brass', flange_at=(0.35,), kind='conduit')
                        D.gland(mesh, q2[0], q2[1], (1, 0, 0), 0.028, size=0.06, back=base_top(xf, sv - 0.3))
                        nfit += 1
                        last = xf
    log['conduits'] = ncond
    log['through_hull_fittings'] = nfit
    log['hull_rivets'] = nr
    # ---- continuity export (read by the neighbouring zones; detail_zones.py / ZONES.md explain the fields)
    rr4 = lambda a: [None if (v is None or not np.isfinite(v)) else round(float(v), 4) for v in a]
    log['continuity'] = dict(
        side=fl.side, x_range=[XA, XB], xs=rr4(xs),
        ref_up=rr4(MU.ref), ref_low=rr4(ML.ref), ref_strake=rr4(ref_st), s_bilge=rr4(lim),
        about='s = arc length down the chart section from the deck edge (FlankChart). ref_up: top of the upper plate '
              'rows (gunwale band + top_off); ref_low: top of the lower mask = top edge of the strake (lower band + '
              'top_off); ref_strake: the fitted strake line; s_bilge: the bilge line (chart angle bilge_phi)',
        bands=dict(strake_h=ST['h'], strake_t=ST['t'], backing_h=ST['back_h'], teeth_h=TE['h'], teeth_w=TE['w'],
                   channel_v=CH['v'], channel_r=CH['r'], bay_v=BY['v'], upper_bay_v=UB['v'], gusset_step=G['step'],
                   gusset_x0=XA + 0.35, conduit_r=CD['r_up'], conduit_v_below_up_run_end=0.06, conduit_dv=0.095),
        strake_runs=strake_runs, strake_segments=cont_seg, channel_spans=spans, channel_pipes=cont_chan,
        lower_bays=bays, upper_bays=ubays, gussets=cont_gus, conduits=cont_cond)
    return dict(MU=MU, ML=ML)
