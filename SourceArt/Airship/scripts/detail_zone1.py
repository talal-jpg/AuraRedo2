"""Zone 1 of the airship detail pass (round 3, 2026-11-28): a style and density sample for Talal.

Zone 1 = the PORT hull flank between the aft and the forward cannon stations (x -11.47 .. -0.46), from the deck edge
down to the turn of the bilge, carried on forward over the front-left pod's hull pocket (plates end at the pocket's fore
rim strap, x ~6.9), plus the front-left thruster pod Thruster_FL (pod, nozzle, the 12 petals) and the cavity of its hull
pocket.

  blender -b --factory-startup --python detail_zone1.py [-- --no-save]

Opens rig/AirshipRig.blend (never saved), adds the zone's detail objects to collection Detail_Z1 and saves the copy
rig/detail/AirshipRig_detail.blend. SM_Airship (Talal's mesh), its UVs and the props are untouched.

Objects (all parented to the Armature, Armature modifier, every vertex 100 % on one bone):
  SM_AirshipDetail_Z1_Hull            -> Hull
  SM_AirshipDetail_Z1_Pod_FL          -> Thruster_FL
  SM_AirshipDetail_Z1_Nozzle_FL       -> Thruster_FL_Nozzle
  SM_AirshipDetail_Z1_Petals_FL       -> Thruster_FL_Petal00 .. 11 (one vertex group per petal)
Report: rig/detail/zone1_report.json (parameters, triangles per object / kind, checks, extrapolation).

Pass 2 (after review): colour by role, three depth levels (base plates 4.5 cm, layers / ribs / teeth 10-13 cm,
machinery bays and pipe channel 18-20 cm), picture-frame and slotted plates, a riveted strake with big rectangular teeth on
a dark backing, a pipe channel with two big pipes, machinery bays with housings / pump / bottle, conduits ending in
glands, low domed rivets only on straps / ribs / corners, floating-piece check. No round grilles, louvre boxes, exhaust
stubs, cable loops, chain or junction boxes on the flank any more.
"""
import bpy, sys, os, math, random, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from mathutils import Vector as V
from mathutils.bvhtree import BVHTree
import rig_common as C
import detail_common as D
import detail_ship as S

DETAIL_DIR = C.RIG + '/detail'
OUT_BLEND = DETAIL_DIR + '/AirshipRig_detail.blend'
REPORT = DETAIL_DIR + '/zone1_report.json'
COLL = 'Detail_Z1'
PREFIX = 'SM_AirshipDetail_Z1_'
YELLOWS = (('paint_yellow', 0.5), ('paint_ochre', 0.5))

# ------------------------------------------------------------------ knobs (all metres / degrees)
K = dict(
    seed=1301,
    x_aft=-11.55, x_fwd=8.6,                 # aft cannon station .. forward end of the FL pocket
    x_fwd_plates=6.95,                       # plates end at the pocket's fore rim strap (a clean zone edge)
    chart_x=(-12.0, 9.0, 0.05), chart_phi=(30.0, -80.0, -0.5), chart_clear=0.30,
    bilge_phi=-56.0,                         # lower limit of the zone (turn of the bilge) as a chart angle
    touch_tol=0.02,                          # every loose piece touches the ship or another piece within this
    step_tol=0.012,                          # a plate whose skin patch departs from a smooth fit by more is skipped
    plate=dict(gap=0.015, t=0.045, bevel=0.014, cell_u=0.6, cell_v=0.25, cut=(0.07, 0.17), cut_p=0.3),
    layer=0.006,                             # clearance between stacked layers
    seam=0.024,
    rivet=dict(r=0.022, h=0.012, inset=0.07, spacing=0.28),
    upper=dict(w=(0.8, 1.7), row_h=(0.55, 0.95), top_off=0.27, min_w=0.35, min_h=0.22, keep=0.25, mats=YELLOWS),
    lower=dict(w=(0.8, 1.6), row_h=(0.7, 1.1), top_off=0.04, min_w=0.35, min_h=0.22, keep=0.25, mats=YELLOWS),
    fill=dict(w=(0.35, 0.8), h=(0.3, 0.6), min_w=0.3, min_h=0.24, mats=YELLOWS),
    shingle=dict(p=0.3, overlap=0.08, t=0.04, armour=0.5),
    frame=dict(p=0.65, rim=0.075, t=0.035, inset_p=0.0, min_w=0.6, min_h=0.45, edge=0.09),
    patch=dict(p=0.7, t=0.04, w=(0.4, 0.8), h=(0.3, 0.55), mats=(('rust_red', 0.7), ('paint_ochre', 0.3))),
    batten=dict(p=0.75, w=0.12, t=0.05, mat='rust_red'),
    slots=dict(up=3, mid=2, w=(0.55, 0.8), h=(0.32, 0.45), n=(3, 4), slot_w=0.05, ang=58.0),
    strake=dict(h=0.2, t=0.085, back_h=0.6, back_t=0.02, smooth=0.9),
    teeth=dict(w=(0.7, 0.9), h=(0.62, 0.78), gap=(0.14, 0.2), t=0.09, chamfer=0.07),
    channel=dict(v=(1.02, 1.52), r=(0.07, 0.058), clamp_step=1.0),
    bay=dict(v=(1.62, 2.78), w=(2.1, 1.6), rim=0.1, rim_t=0.05, depth=0.11, pump_r=0.068),
    ubay=dict(v=(0.1, 0.86), w=(1.8, 1.6), x_pref=(-7.4, -2.3), rim=0.08, depth=0.1),
    conduit=dict(r_up=(0.03, 0.026), clamp_step=0.7, fittings=3, smooth=0.75),
    gusset=dict(step=0.51, depth=0.10, height=0.22, t=0.025),
    pocket=dict(r=2.85, rim_w=(0.03, 0.19), rim_t=0.05, cavity_bottom_h=-1.84, roof_h=-2.8),
    pod=dict(gap=0.012, t=0.035, bevel=0.01, rib_rivet_step=20.0, hull_clear=0.05, bundle_r=0.05, hug_r=(0.06, 0.05),
             act_r=2.04, hoops=(3.25, 3.6), mats=(('rust_red', 0.45), ('rust_dark', 0.35), ('dark_metal', 0.2))),
    pa_boxes='/mnt/new_partition/UnrealProjects/_AirshipWork/Saved/Airship/pa_hull_boxes.json',
)


def wchoice(rng, items):
    t = rng.random() * sum(w for _, w in items)
    for k, w in items:
        t -= w
        if t <= 0:
            return k
    return items[-1][0]


# ================================================================== hull flank
class Flank:
    def __init__(self, ship, K):
        self.K = K
        self.skin = ship.surface(ship.p_island == S.SKIN)
        self.obst = ship.bvh(ship.p_island != S.SKIN)
        x0, x1, dx = K['chart_x']
        p0, p1, dp = K['chart_phi']
        self.chart = S.FlankChart(self.skin, self.obst, np.arange(x0, x1 + 1e-9, dx), np.arange(p0, p1 - 1e-9, dp),
                                  side=1, clear=K['chart_clear'])
        ch = self.chart
        jb = int(np.argmin(np.abs(np.degrees(ch.ph) - K['bilge_phi'])))
        self.s_lim = ch.s[:, jb]
        self.runs = [ch.runs(i, 0.2) for i in range(len(ch.xs))]

    def region(self, x, name):
        i = self.chart.col(x)
        R = self.runs[i]
        if name == 'up':
            r = next(((s0, s1) for (_, _, s0, s1) in R if s0 < 1.1 and s1 - s0 > 0.6), None)
        elif name == 'mid':
            r = next(((s0, s1) for (_, _, s0, s1) in R if 1.8 < s0 < 3.0 and s1 - s0 > 0.25), None)
        else:
            r = next(((s0, s1) for (_, _, s0, s1) in R if 3.0 <= s0 < 5.0 and s1 - s0 > 0.5), None)
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
        pockets = [ship.pod_frame(p) for p in ('FL', 'RL')]
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
    log['gussets'] = ng

    def surf_below(pt):
        r = fl.skin.nearest(pt, 1.0)
        return (r[0], r[1]) if r is not None else None

    # ---------------------------------------------------------------- pipe channel: dark backing, two big pipes, valve
    npipe = 0
    chan = {}
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
    return dict(MU=MU, ML=ML)


# ================================================================== FL pocket (hull bone): rim strap and cavity
def pocket_rim(mesh, fl, ship, K, rng, log):
    """riveted strap round the FL pocket opening on the outer skin: the top edge (where the pocket roof meets the
    flank) and the aft / fore edges (where the pocket cylinder meets it), found in the chart as outer-skin cells
    next to pocket-wall cells. Returns chart points over the strap (plates keep off them)."""
    O, T0, A, NP = ship.pod_frame('FL')
    ch = fl.chart
    R = K['pocket']['r']
    RV = K['rivet']
    nx, nph = ch.hit.shape
    wall = np.zeros((nx, nph), bool)
    outer = np.zeros((nx, nph), bool)
    cols = [i for i in range(nx) if -0.5 <= ch.xs[i] <= 9.5]
    for i in cols:
        for j in range(nph):
            if not ch.hit[i, j] or np.isnan(ch.s[i, j]):
                continue
            rel = ch.P[i, j] - T0
            h = rel @ A
            rv = rel - A * h
            d = np.linalg.norm(rv)
            nr = ch.N[i, j] @ (rv / max(d, 1e-9))
            if abs(d - R) < 0.08 and nr < -0.5:
                wall[i, j] = True
            elif ch.N[i, j][1] > 0.2 and (d > R - 0.02 or h < K['pocket']['roof_h'] + 0.02):
                outer[i, j] = True
    top, aft, fore = [], [], []
    for i in cols:
        js = np.nonzero(wall[i])[0]
        if len(js) and js[0] > 0 and outer[i, js[0] - 1]:
            top.append((ch.xs[i], ch.s[i, js[0] - 1]))
    for j in range(nph):
        for k in range(len(cols) - 1):
            i, i2 = cols[k], cols[k + 1]
            if outer[i, j] and wall[i2, j] and ch.s[i, j] <= fl.s_lim[i]:
                aft.append((ch.xs[i], ch.s[i, j]))
            if wall[i, j] and outer[i2, j] and ch.s[i2, j] <= fl.s_lim[i2]:
                fore.append((ch.xs[i2], ch.s[i2, j]))
    rim_pts = []
    rw0, rw1 = K['pocket']['rim_w']
    log['rim_edge_points'] = dict(top=len(top), aft=len(aft), fore=len(fore))
    pod_bvh = ship.bvh(np.char.startswith(ship.p_bone.astype(str), 'Thruster_FL'))

    def pod_far(q, d=0.2):
        if q is None:
            return False
        r = pod_bvh.find_nearest(V(q[0]), d)
        return r[0] is None

    def smooth_line(pts, key):
        pts = np.array(sorted(pts, key=lambda q: q[key]))
        if len(pts) < 8:
            return None
        t = pts[:, key]
        o = 1 - key
        deg = 3 if (t[-1] - t[0]) > 1.5 else 1
        c = np.polyfit(t, pts[:, o], deg)
        tt = np.linspace(t[0], t[-1], max(8, int((t[-1] - t[0]) / 0.05)))
        out = np.zeros((len(tt), 2))
        out[:, key] = tt
        out[:, o] = np.polyval(c, tt)
        return out

    def strap(f, L, name):
        us_all = np.arange(0.0, L + 1e-9, 0.08)
        okm = [f(u, (rw0 + rw1) / 2) is not None and fl.chart.free_at(*f.xs(u, rw0 + 0.02), 0.0) and
               fl.chart.free_at(*f.xs(u, rw1 - 0.02), 0.0) and pod_far(f(u, rw0)) and pod_far(f(u, rw1))
               for u in us_all]
        n = 0
        m = 0
        while m < len(us_all):
            if not okm[m]:
                m += 1
                continue
            e = m
            while e + 1 < len(us_all) and okm[e + 1]:
                e += 1
            if e - m >= 3:
                u0, u1 = us_all[m], us_all[e]
                g = lambda u, v, u0=u0: f(u0 + u, v)
                top_fn, ok = D.solid_plate(mesh, g, D.grid_coords(0, u1 - u0, 0.16), np.array([rw0, rw1]), 0.012,
                                           K['pocket']['rim_t'], 0.014, 'rust_red', kind='rim')
                if ok:
                    n += 1
                    kb = max(1, int((u1 - u0) / RV['spacing']))
                    D.rivet_row(mesh, top_fn, [((u1 - u0) * (i + 0.5) / kb, (rw0 + rw1) / 2) for i in range(kb)],
                                r=RV['r'], h=RV['h'])
                for u in np.arange(u0, u1 + 1e-9, 0.04):
                    for vv in np.linspace(0.0, rw1 + 0.03, 5):
                        rim_pts.append(f.xs(u, vv))
            m = e + 1
        return n

    nrim = 0
    st = smooth_line(top, 0)
    if st is not None:
        x0, x1 = st[0, 0], st[-1, 0]

        def ft(u, v):
            x = x0 + u
            return ch.surf(x, float(np.interp(x, st[:, 0], st[:, 1])) - v)
        ft.xs = lambda u, v: (x0 + u, float(np.interp(x0 + u, st[:, 0], st[:, 1])) - v)
        nrim += strap(ft, x1 - x0, 'top')
    for pts, sgn, name in ((aft, -1.0, 'aft'), (fore, 1.0, 'fore')):
        sl = smooth_line(pts, 1)
        if sl is None:
            continue
        s_top_here = float(np.interp(sl[0, 0], st[:, 0], st[:, 1])) if st is not None else sl[0, 1]
        keep = sl[:, 1] > s_top_here + 0.05
        sl = sl[keep]
        if len(sl) < 4:
            continue
        s0, s1 = sl[0, 1] - (0.05 if st is not None else 0.0), sl[-1, 1]

        def fs(u, v, sl=sl, s0=s0, sgn=sgn):
            s_ = s0 + u
            return ch.surf(float(np.interp(s_, sl[:, 1], sl[:, 0])) + sgn * v, s_)
        fs.xs = lambda u, v, sl=sl, s0=s0, sgn=sgn: (float(np.interp(s0 + u, sl[:, 1], sl[:, 0])) + sgn * v, s0 + u)
        nrim += strap(fs, s1 - s0, name)
    log['rim_pieces'] = nrim
    return rim_pts


def cavity(hull, ship, fl, K, rng, log):
    """FL pocket cavity above the pod, kept simple (the pod top and the steam pipe hide most of it): vertical wall
    stiffeners and one ring rib along the lower edge of the cavity wall, where it shows through the opening"""
    O, T0, A, NP = ship.pod_frame('FL')
    e0, e90 = S.pod_basis(A)
    R = K['pocket']['r']
    hb, hr = K['pocket']['cavity_bottom_h'], K['pocket']['roof_h']
    skin = fl.skin
    wall = {}
    for th in range(-180, 180, 5):
        cnt = 0
        for h in np.arange(hr + 0.08, hb + 0.001, 0.1):
            c = T0 + A * h
            d = S.cyl_point(T0, A, e0, e90, h, th, 1.0)[1]
            r = skin.ray(c, d, 3.5)
            if r is not None and abs(r[3] - R) < 0.05:
                cnt += 1
        wall[th] = cnt
    nh = len(np.arange(hr + 0.08, hb + 0.001, 0.1))
    ths = sorted(wall)
    ok = [wall[t] == nh for t in ths]
    if all(ok) or not any(ok):
        log['cavity_wall_deg'] = None
        return
    n = len(ths)
    start = next(i for i in range(n) if ok[i] and not ok[i - 1])
    best, cur = (0, 0), None
    for k in range(n):
        i = (start + k) % n
        if ok[i]:
            cur = (cur[0], k) if cur else (k, k)
            if cur[1] - cur[0] > best[1] - best[0]:
                best = cur
        else:
            cur = None
    a0 = ths[(start + best[0]) % n]
    a1 = a0 + 5 * (best[1] - best[0])
    full = [a0, a1]

    def wall_fn(th0):
        def f(u, v):
            th = th0 + math.degrees(u / R)
            tk = int(5 * round(((th + 180.0) % 360.0 - 180.0) / 5))
            if wall.get(tk if tk < 180 else -180, 0) < nh:
                return None
            p, d = S.cyl_point(T0, A, e0, e90, v, th, R)
            return p, -d
        return f
    nst = 0
    for th in np.arange(full[0] + 6, full[-1] - 5, 15.0):
        f = wall_fn(th)
        w = 0.09
        top_fn, ok_ = D.solid_plate(hull, lambda u, v, f=f: f(u - w / 2, v), np.array([0.0, w]),
                                    D.grid_coords(hr + 0.05, hb, 0.3), 0.01, 0.045, 0.01, 'dark_metal', kind='cavity')
        if ok_:
            nst += 1
            D.rivet_row(hull, top_fn, [(w / 2, h) for h in np.arange(hb - 0.1, hr + 0.1, -0.3)], r=0.018, h=0.01)
    L = math.radians(full[-1] - full[0] - 4) * R
    f = wall_fn(full[0] + 2)
    D.solid_plate(hull, lambda u, v, f=f: f(u, hb - 0.04 + v), D.grid_coords(0, L, 0.3), np.array([-0.05, 0.05]),
                  0.06, 0.03, 0.008, 'machinery', kind='cavity')
    log['cavity'] = dict(stiffeners=nst, wall_sector=[full[0], full[-1]])


# ================================================================== the pod, nozzle and petals
class HullClear:
    """is a point outside the hull solid and at least `margin` from the skin? (the hull floor runs through the lower
    drum of the pod: details there would be buried in the hull and collide when the pod tilts)"""

    def __init__(self, skin):
        self.skin = skin

    def __call__(self, p, margin):
        r = self.skin.nearest(p, 5.0)
        if r is None:
            return True
        q, n, fi, dist = r
        return (np.asarray(p) - q) @ n > 0 and dist >= margin


def build_pod(pod, noz, pet, ship, K, rng, log, skin=None):
    O, T0, A, NP = ship.pod_frame('FL')
    hc0 = HullClear(skin) if skin is not None else (lambda p, m: True)

    def hc_ok(p, m):
        # the pod tilts +-3 deg about its origin: a point L metres from it moves up to L sin(3 deg)
        L = np.linalg.norm(np.asarray(p) - O)
        return hc0(p, m + L * math.sin(math.radians(3.0)))
    CLR = K['pod']['hull_clear']
    e0, e90 = S.pod_basis(A)
    PK = K['pod']
    RV = K['rivet']
    blk_mask = np.isin(ship.p_island, [i for i, r in ship.islands.items() if r['part'] == 'Pod_FL' and r['piece'] != 'drum'])
    blk = ship.bvh(blk_mask)
    plates_surf = ship.surface(np.isin(ship.p_island, [720, 721, 727]))
    RD = 1.85                                        # drum radius

    def radial_free(h, th, r_in=RD + 0.07, r_out=3.2):
        p, d = S.cyl_point(T0, A, e0, e90, h, th, r_out)
        hit = blk.ray_cast(V(p), V(-d), r_out - r_in)
        return hit[0] is None

    def drum_fn(th0, r=RD):
        def f(u, v):
            th = th0 + math.degrees(u / RD)
            p, d = S.cyl_point(T0, A, e0, e90, v, th, r)
            return p, d
        return f

    def free_patch(th0, th1, h0, h1):
        for th in np.arange(th0, th1 + 0.01, 3.0):
            for h in np.arange(h0, h1 + 0.001, 0.06):
                if not radial_free(h, th) or not hc_ok(S.cyl_point(T0, A, e0, e90, h, th, RD + 0.04)[0], CLR):
                    return False
        return True

    # (a) drum plates in the bands between the ribs (rust family and dark metal; never hull yellow). The band below the
    #     last-but-one rib (h 1.74 .. 2.16) carries the pipe pair (e) instead.
    bands = [(-1.52, -1.12), (-0.21, 0.26), (0.44, 0.91), (1.09, 1.56)]
    nplates = 0
    nr = 0
    for (h0, h1) in bands:
        th = -178.0
        while th < 178.0:
            span = rng.uniform(28.0, 50.0)
            th1 = min(th + span, 178.0)
            if h0 < 0.0 < h1 and th1 > -13.0 and th < 5.0:      # the junction housing (g) sits here
                if th < -13.0:
                    th1 = -13.0
                else:
                    th = 5.0
                    continue
            ok = False
            t1 = th1
            while t1 - th >= 16.0:
                if free_patch(th, t1, h0, h1):
                    ok = True
                    break
                t1 -= 4.0
            if not ok:
                th += 4.0
                continue
            W = math.radians(t1 - th) * RD
            f = drum_fn(th)
            cut = rng.uniform(0.04, 0.08)
            corners = tuple(int(rng.random() < 0.3) for _ in range(4))
            us = D.grid_coords(0.0, W, 0.22, cut if any(corners) else 0)
            vs = D.grid_coords(h0, h1, 0.25, cut if any(corners) else 0)
            mat = wchoice(rng, PK['mats'])
            top_fn, okp = D.solid_plate(pod, f, us, vs, PK['gap'], PK['t'], PK['bevel'], mat,
                                        corners=corners if any(corners) else (0, 0, 0, 0), kind='pod_plate')
            if okp:
                nplates += 1
                nr += D.rivet_row(pod, top_fn, D.corner_pts(us, vs, 0.05, cut, corners if any(corners) else (0, 0, 0, 0)),
                                  r=0.02, h=0.011)
                if W > 0.6 and rng.random() < 0.3:
                    pw = rng.uniform(0.25, min(0.5, W - 0.25)); u0p = rng.uniform(0.12, W - pw - 0.12)
                    hv0, hv1 = h0 + 0.1, h1 - 0.1
                    f2 = lambda u, v, f=f, u0p=u0p: f(u0p + u, v)
                    us2 = D.grid_coords(0.0, pw, 0.22); vs2 = D.grid_coords(hv0, hv1, 0.25)
                    t2, ok2 = D.solid_plate(pod, f2, us2, vs2, PK['gap'] + PK['t'] + 0.006, 0.025, 0.008, 'rust_dark',
                                            kind='pod_plate')
                    if ok2:
                        nr += D.rivet_row(pod, t2, D.corner_pts(us2, vs2, 0.04), r=0.016, h=0.009)
            th = t1 + rng.uniform(2.0, 6.0)
    # (b) rivets on the upper face of each rib (diamond section: crest r 1.95 at the rib centre, 1.87 at +-0.08)
    for hc in (-0.3, 0.35, 1.0, 1.65, 2.25):
        for th in np.arange(-180.0, 180.0, PK['rib_rivet_step']):
            if not radial_free(hc - 0.04, th, r_in=1.96) or not hc_ok(S.cyl_point(T0, A, e0, e90, hc - 0.04, th, 1.93)[0], CLR):
                continue
            p, d = S.cyl_point(T0, A, e0, e90, hc - 0.04, th, 1.912)
            D.rivet(pod, p, D.unit(d - A), r=0.02, h=0.011, sink=0.008)
            nr += 1
    # (c) riveted ring band on the drum just above the collar
    k = 36
    rings = []
    for (h, r) in ((-1.08, RD - 0.01), (-1.08, RD + 0.045), (-0.94, RD + 0.045), (-0.94, RD - 0.01)):
        rings.append(D.ring_pts(T0 + A * h, e0, e90, r, k))
    idx = []
    for rg in rings:
        b = pod.verts(rg)
        idx.append(list(range(b, b + k)))
    for i in range(4):
        pod.bridge(idx[i], idx[(i + 1) % 4], 'dark_metal', False, 'pod_band')
    for th in np.arange(-180.0, 180.0, 24.0):
        p, d = S.cyl_point(T0, A, e0, e90, -1.01, th, RD + 0.045)
        D.rivet(pod, p, d, r=0.018, h=0.01)
        nr += 1

    # (d) the three big pod plates stay the main shapes: a thick riveted lip along the lower edges of 721 and 727, two
    #     straps bent over the folds of 720 and 727, three large rust patches, all on the plates' outer facets
    nover = 0

    def plate_facets(isl):
        """the outer face of a big pod plate (12 vertices: an outer and an inner sheet, three columns each, folded at
        the middle column) as two flat facets [(top, bottom) column pairs, left to right]"""
        v = ship.island_verts([isl])
        h, th, rr = pod_frame_coords(v, T0, A, e0, e90)
        cols = {}
        for k in range(len(v)):
            cols.setdefault(round(float(th[k])), []).append(k)
        out = []
        for t_ in sorted(cols):
            ks = sorted(cols[t_], key=lambda k: h[k])
            top = max(ks[:2], key=lambda k: rr[k])                  # outer vertex of the top pair
            bot = max(ks[-2:], key=lambda k: rr[k])                 # outer vertex of the bottom pair
            out.append((v[top], v[bot]))
        return out

    def facet_fn(c0, c1):
        """surface (u, v) in metres over one facet: u along the top edge, v down the side; flat facet normal"""
        (at, ab), (bt, bb) = c0, c1
        Lu, Lv = float(np.linalg.norm(bt - at)), float(np.linalg.norm(ab - at))
        n = D.unit(np.cross(bt - at, ab - at))
        rad = (at - T0) - A * ((at - T0) @ A)
        if n @ rad < 0:
            n = -n

        def f(u, v):
            s_, w_ = u / Lu, v / Lv
            return (1 - s_) * (1 - w_) * at + s_ * (1 - w_) * bt + s_ * w_ * bb + (1 - s_) * w_ * ab, n
        return f, Lu, Lv
    FAC = {isl: plate_facets(isl) for isl in (720, 721, 727)}
    # (plate, facet, u0, u1, v0, v1 as fractions of the facet; material, thickness, rivets 'row' | 'corners' | 'strap')
    BIG = [(721, 0, 0.03, 0.97, 'lip'), (721, 1, 0.03, 0.97, 'lip'), (727, 0, 0.03, 0.97, 'lip'),
           (727, 1, 0.03, 0.97, 'lip'),
           (720, 0, 0.18, 0.78, (0.12, 0.42)), (727, 0, 0.2, 0.85, (0.3, 0.62)), (721, 1, 0.12, 0.7, (0.08, 0.5)),
           (720, 0, 0.96, 1.0, 'strap'), (720, 1, 0.0, 0.04, 'strap'), (727, 0, 0.965, 1.0, 'strap'),
           (727, 1, 0.0, 0.035, 'strap')]
    for (isl, fi, u0, u1, kind_) in BIG:
        cs = FAC[isl]
        if fi + 1 >= len(cs):
            continue
        f, Lu, Lv = facet_fn(cs[fi], cs[fi + 1])
        U0, U1 = u0 * Lu, u1 * Lu
        if kind_ == 'lip':                     # thick riveted lip along the lower edge
            V0, V1, mat, t_ = Lv - 0.16, Lv - 0.02, 'rust_dark', 0.05
        elif kind_ == 'strap':                 # a strap bent over the plate's fold (two halves, one per facet)
            V0, V1, mat, t_ = 0.05, Lv - 0.2, 'rust_dark', 0.04
        else:                                  # one large rust patch
            V0, V1, mat, t_ = kind_[0] * Lv, kind_[1] * Lv, 'rust_red', 0.032
        us = D.grid_coords(U0, U1, 0.2); vs = D.grid_coords(V0, V1, 0.2)
        g = lambda u, v, f=f, U0=U0, V0=V0: f(U0 + u, V0 + v)
        top_fn, ok = D.solid_plate(pod, g, us - U0, vs - V0, 0.012, t_, 0.012, mat, kind='pod_patch')
        if not ok:
            log.setdefault('pod_skipped', []).append('big plate piece %d/%d' % (isl, fi))
            continue
        nover += 1
        W, H = U1 - U0, V1 - V0
        if kind_ == 'lip':
            kk = max(1, int(round((W - 0.1) / RV['spacing'])))
            pts = [(0.05 + (W - 0.1) * i / kk, H / 2) for i in range(kk + 1)]
        elif kind_ == 'strap':
            kk = max(1, int(round((H - 0.1) / RV['spacing'])))
            pts = [(W / 2, 0.05 + (H - 0.1) * i / kk) for i in range(kk + 1)]
        else:
            pts = D.corner_pts(np.array([0.0, W]), np.array([0.0, H]), 0.05)
        nr += D.rivet_row(pod, top_fn, pts, r=0.02, h=0.011)
    # lids on the two side boxes: inset plate, rivets, two hinges and two dog latches (no handle)
    for bid in (733, 739):
        bv = ship.island_verts([bid])
        rel = bv - T0
        hb_ = rel @ A
        rr = np.linalg.norm(rel - np.outer(hb_, A), axis=1)
        face = bv[np.argsort(-rr)[:4]]
        c = face.mean(0)
        n = D.unit(np.cross(face[1] - face[0], face[2] - face[0]))
        if n @ (c - (T0 + A * (c - T0) @ A)) < 0:
            n = -n
        ax_v = D.unit(A - n * (A @ n)); ax_u = np.cross(n, ax_v)
        ext_u = max(abs((face - c) @ ax_u)); ext_v = max(abs((face - c) @ ax_v))
        lu, lv = ext_u - 0.05, ext_v - 0.05
        D.chamfer_box(pod, D.frame_matrix(c + n * 0.012, ax_u, ax_v, n), lu, lv, 0.012, 0.006, 'dark_metal', 'pod_box')
        for su in (-1, 1):
            for sv in (-1, 1):
                D.rivet(pod, c + n * 0.024 + ax_u * su * (lu - 0.04) + ax_v * sv * (lv - 0.04), n, r=0.017, h=0.009)
        for s in (-0.55, 0.55):                       # hinges along the upper edge (-v), latches on the lower edge
            p = c + n * 0.026 - ax_v * (lv + 0.004) + ax_u * s * lu
            D.cylinder(pod, p - ax_u * 0.05, p + ax_u * 0.05, 0.016, 6, 'dark_metal', 'pod_box', smooth=True)
            q = c + n * 0.03 + ax_v * (lv - 0.03) + ax_u * s * lu
            D.chamfer_box(pod, D.frame_matrix(q, ax_u, ax_v, n), 0.012, 0.045, 0.008, 0.002, 'steel', 'pod_box')
            D.chamfer_box(pod, D.frame_matrix(q + ax_v * 0.06 - n * 0.006, ax_u, ax_v, n), 0.024, 0.014, 0.012, 0.003,
                          'steel', 'pod_box')
    # (e) thick pipe bundle down the front-inboard side (over the rib crests), clamps on the ribs, ends into the drum
    rp = PK['bundle_r']
    pipe_end_h = 9.0
    for k_, th in enumerate((-38.0, -46.0, -54.0)):
        rr = 1.95 + 0.012 + rp
        pts = [S.cyl_point(T0, A, e0, e90, -1.5, th, RD - 0.02)[0],
               S.cyl_point(T0, A, e0, e90, -1.38, th, rr)[0]]
        h_end = -1.15
        for h in np.arange(-1.15, 2.31, 0.05):
            if not hc_ok(S.cyl_point(T0, A, e0, e90, h + 0.15, th, rr + rp)[0], CLR):
                break
            h_end = h
        pts += [S.cyl_point(T0, A, e0, e90, h, th, rr)[0] for h in np.arange(-1.15, h_end - 0.05, 0.35)]
        pts += [S.cyl_point(T0, A, e0, e90, h_end, th, rr)[0], S.cyl_point(T0, A, e0, e90, h_end + 0.14, th + 4, RD - 0.03)[0]]
        pipe_end_h = min(pipe_end_h, h_end) if k_ else h_end
        D.pipe_run(pod, pts, rp, 0.12, sides=10, mat='copper' if k_ != 1 else 'brass', flange_at=(0.35, 0.7), flange_k=1.25,
                   kind='pod_pipe')
    for hc in [h_ for h_ in (-0.3, 0.35, 1.0, 1.65) if h_ < pipe_end_h - 0.1]:
        p0, d0 = S.cyl_point(T0, A, e0, e90, hc, -62.0, 1.95 + 0.012 + 2 * rp + 0.014)
        p1, d1 = S.cyl_point(T0, A, e0, e90, hc, -30.0, 1.95 + 0.012 + 2 * rp + 0.014)
        mid_d = D.unit(d0 + d1)
        c = (p0 + p1) / 2
        t = D.unit(p1 - p0)
        D.chamfer_box(pod, D.frame_matrix(c - mid_d * 0.02, t, A, mid_d), np.linalg.norm(p1 - p0) / 2, 0.03, 0.014, 0.004,
                      'dark_metal', 'pod_pipe')
        for pp in (p0, p1):
            D.rivet(pod, pp - mid_d * 0.006, mid_d, r=0.018, h=0.01)
    # (f) the gap below the big plates: two thick pipes hugging the drum in the lowest band (instead of plates there),
    #     clamped at the ribs' faces, ends bent into the drum; two actuators across them on the front-outboard side
    npp = 0
    for k_, (hh, rpp) in enumerate(((1.84, PK['hug_r'][0]), (2.05, PK['hug_r'][1]))):
        rr = RD + 0.012 + rpp
        runs_, cur = [], []
        for th in np.arange(-76.0, 70.0, 4.0):
            p = S.cyl_point(T0, A, e0, e90, hh, th, rr + rpp)[0]
            ok = radial_free(hh, th, r_in=rr + rpp + 0.01) and hc_ok(p, CLR) and \
                hc_ok(S.cyl_point(T0, A, e0, e90, hh, th, RD + 0.02)[0], CLR)
            if ok:
                cur.append(th)
            else:
                if cur:
                    runs_.append(cur)
                cur = []
        if cur:
            runs_.append(cur)
        # the longest run on the front / outboard side (the side players see), else the longest
        vis = [r_ for r_ in runs_ if np.mean(r_) > -20.0 and len(r_) >= 6]
        ths = max(vis or runs_ or [[]], key=len)
        if len(ths) < 6:
            log.setdefault('pod_skipped', []).append('hug pipe %d' % k_)
            continue
        ta, tb = ths[0], ths[-1]
        pts = [S.cyl_point(T0, A, e0, e90, hh, ta - 3.0, RD - 0.02)[0]]
        pts += [S.cyl_point(T0, A, e0, e90, hh, th, rr)[0] for th in np.arange(ta + 2.0, tb - 1.9, 4.0)]
        pts += [S.cyl_point(T0, A, e0, e90, hh, tb + 3.0, RD - 0.02)[0]]
        ncl = max(2, int((tb - ta) / 30.0))
        def pod_surf_fn(pt):
            rel = np.asarray(pt) - T0
            hq = rel @ A
            dq = D.unit(rel - A * hq)
            return T0 + A * hq + dq * RD, dq
        D.pipe_run(pod, pts, rpp, 0.1, sides=10, mat='copper' if k_ == 0 else 'brass', flange_at=(0.3, 0.7),
                   clamp_at=[(i + 0.5) / ncl for i in range(ncl)], surf_fn=pod_surf_fn, kind='pod_pipe')
        npp += 1
    for th in (32.0, 46.0):
        a = S.cyl_point(T0, A, e0, e90, 1.12, th, PK['act_r'])[0]
        b = S.cyl_point(T0, A, e0, e90, 2.15, th, PK['act_r'])[0]
        if not (hc_ok(a, CLR) and hc_ok(b, CLR)):
            log.setdefault('pod_skipped', []).append('piston %d' % th)
            continue
        d = S.cyl_point(T0, A, e0, e90, 0, th, 1)[1]
        D.piston(pod, a, b, r=0.04, eye_axis=np.cross(A, d))
        for (hh, pp) in ((1.12, a), (2.15, b)):
            q, dd = S.cyl_point(T0, A, e0, e90, hh, th, RD + 0.02)
            D.chamfer_box(pod, D.frame_matrix(q + dd * (PK['act_r'] - RD) * 0.5, np.cross(A, dd), A, dd), 0.012, 0.05,
                          (PK['act_r'] - RD) * 0.5 + 0.01, 0.004, 'dark_metal', 'piston')
    # (g) junction box on the front band (above plate 727) with a conduit to the pipe bundle
    p, d = S.cyl_point(T0, A, e0, e90, 0.02, -4.0, RD)
    tang = np.cross(A, d)
    D.housing(pod, p - d * 0.012, d, tang, 0.42, 0.3, 0.09)
    q0 = p + d * 0.06 + tang * (-0.27)
    pts = [q0] + [S.cyl_point(T0, A, e0, e90, 0.02 + 0.05 * k_, -4.0 - 8.0 * (k_ + 1), RD + 0.07)[0] for k_ in range(3)]
    pts.append(S.cyl_point(T0, A, e0, e90, 0.2, -36.0, RD + 0.02)[0])
    D.tube(pod, D.fillet_path(pts, 0.08, 3), 0.03, 8, 'dark_metal', 'pod_pipe')
    log['pod'] = dict(drum_plates=nplates, big_plate_pieces=nover, hug_pipes=npp, rivets=nr)

    # ---- nozzle: rivet ring above the band, two riveted hoops round the bell, fins between them (lighter steel)
    nn = 0
    for th in np.arange(0.0, 360.0, 15.0):
        h = 2.78
        r = float(np.interp(h, [2.4, 3.0], [1.6, 1.5]))
        p, d = S.cyl_point(T0, A, e0, e90, h, th, r)
        D.rivet(noz, p, D.unit(d + A * (0.1 / 0.6)), r=0.022, h=0.012)
        nn += 1

    def shell_r(h):
        return float(np.interp(h, [2.4, 3.0, 3.001, 3.35, 4.05], [1.6, 1.5, 1.45, 1.2, 1.5]))
    HOOPS = PK['hoops']
    kq = 48
    for hc_ in HOOPS:
        rings = []
        for (h, dr) in ((hc_ - 0.035, -0.012), (hc_ - 0.035, 0.05), (hc_ + 0.035, 0.05), (hc_ + 0.035, -0.012)):
            rings.append(D.ring_pts(T0 + A * h, e0, e90, shell_r(h) + dr, kq))
        idx = []
        for rg in rings:
            b = noz.verts(rg)
            idx.append(list(range(b, b + kq)))
        for i in range(4):
            noz.bridge(idx[i], idx[(i + 1) % 4], 'steel', False, 'hoop')
        for th in np.arange(0.0, 360.0, 30.0):
            p, d = S.cyl_point(T0, A, e0, e90, hc_, th, shell_r(hc_) + 0.05)
            D.rivet(noz, p, d, r=0.018, h=0.01)
            nn += 1
    segs = []
    lo = 3.07
    for hc_ in HOOPS:
        segs.append((lo, hc_ - 0.045))
        lo = hc_ + 0.045
    segs.append((lo, 3.86))
    tf = 0.03
    nf = 0
    for th in np.arange(15.0, 360.0, 30.0):
        d = S.cyl_point(T0, A, e0, e90, 0, th, 1)[1]
        tng = np.cross(A, d)
        for (ha, hb2) in segs:
            if hb2 - ha < 0.08:
                continue
            hs = np.linspace(ha, hb2, 3)
            inner = [T0 + A * h + d * (shell_r(h) - 0.012) for h in hs]
            outer = [T0 + A * h + d * float(np.interp(h, [3.07, 3.86], [1.555, 1.49])) for h in hs]
            rings = []
            for s_ in (-1, 1):
                rings.append([q + tng * s_ * tf / 2 for q in inner])
                rings.append([q + tng * s_ * tf / 2 for q in outer])
            I0 = noz.verts(rings[0]); O0 = noz.verts(rings[1]); I1 = noz.verts(rings[2]); O1 = noz.verts(rings[3])
            n_ = len(hs)
            for i in range(n_ - 1):
                noz.face((I0 + i, I0 + i + 1, O0 + i + 1, O0 + i), 'steel', False, 'fin')
                noz.face((I1 + i, O1 + i, O1 + i + 1, I1 + i + 1), 'steel', False, 'fin')
                noz.face((O0 + i, O0 + i + 1, O1 + i + 1, O1 + i), 'steel', False, 'fin')
                noz.face((I0 + i, I1 + i, I1 + i + 1, I0 + i + 1), 'steel', False, 'fin')
            noz.face((I0, O0, O1, I1), 'steel', False, 'fin')
            noz.face((I0 + n_ - 1, I1 + n_ - 1, O1 + n_ - 1, O0 + n_ - 1), 'steel', False, 'fin')
            nf += 1
    log['nozzle'] = dict(rivets=nn, hoops=len(HOOPS), fin_pieces=nf)

    # ---- petals: a hinge knuckle under the lip ring and a short actuator rod down the petal, each petal on its own bone
    npet = 0
    for k_ in range(12):
        isl = [i for i, r in ship.islands.items() if r['part'] == 'Nozzle_FL' and r.get('piece') == 'petal' and r.get('index') == k_]
        assert len(isl) == 1
        pv = ship.island_verts(isl)
        rel = pv - T0
        h = rel @ A
        rad = rel - np.outer(h, A)
        rr = np.linalg.norm(rad, axis=1)
        d = D.unit(rad.mean(0))
        tng = np.cross(A, d)
        top = h < h.mean()
        outer_pts = [pv[i] for i in range(8) if rr[i] >= np.median(rr[top == top[i]])]
        if len(outer_pts) != 4:
            outer_pts = [pv[i] for i in np.argsort(-rr)[:4]]
        op = np.array(outer_pts)
        oh = (op - T0) @ A
        tmid = op[oh < oh.mean()].mean(0)
        bmid = op[oh >= oh.mean()].mean(0)
        Ld = D.unit(bmid - tmid)
        n = D.unit(np.cross(Ld, tng))
        if n @ d < 0:
            n = -n
        Lh = np.linalg.norm(bmid - tmid)
        pet.cur_group = 'Thruster_FL_Petal%02d' % k_
        kn = tmid + Ld * 0.6 * Lh + n * 0.024           # hinge barrel just below the lip ring's lower edge
        D.cylinder(pet, kn - tng * 0.15, kn + tng * 0.15, 0.026, 8, 'dark_metal', 'petal', smooth=True)
        D.chamfer_box(pet, D.frame_matrix(kn - n * 0.012, tng, Ld, n), 0.13, 0.035, 0.01, 0.003, 'dark_metal', 'petal')
        a_ = kn + Ld * 0.04 + n * 0.002
        b_ = tmid + Ld * 0.93 * Lh + n * 0.026
        D.piston(pet, a_, b_, r=0.02, eye_axis=tng)      # a short actuator down the petal
        D.chamfer_box(pet, D.frame_matrix(b_ - n * 0.012, tng, Ld, n), 0.03, 0.025, 0.008, 0.003, 'dark_metal', 'petal')
        for s_ in (-1, 1):
            D.rivet(pet, tmid + Ld * 0.82 * Lh + tng * s_ * 0.11, n, r=0.016, h=0.009)
        npet += 1
    log['petals'] = npet


# ================================================================== checks
def dist_report(co, surf, name, limit, vkind=None):
    """max distance of detail vertices from the target surface (the silhouette rule)"""
    co = np.asarray(co)
    if len(co) == 0:
        return dict(name=name, verts=0)
    d = np.array([(lambda r: r[3] if r[0] is not None else 9.0)(surf.bvh.find_nearest(V(c), 9.0)) for c in co])
    w = int(np.argmax(d))
    kinds = {}
    if vkind is not None:
        for k in np.nonzero(d > limit)[0]:
            kinds[vkind[k]] = kinds.get(vkind[k], 0) + 1
    return dict(name=name, max_dist_m=round(float(d[w]), 3), worst=[round(float(x), 3) for x in co[w]],
                verts_over_limit=int((d > limit).sum()), over_limit_by_kind=kinds, verts=len(co), limit_m=limit,
                p99_m=round(float(np.percentile(d, 99)), 3))


def pod_frame_coords(co, T0, A, e0, e90):
    rel = np.asarray(co) - T0
    h = rel @ A
    x, y = rel @ e0, rel @ e90
    return h, np.degrees(np.arctan2(y, x)), np.hypot(x, y)


def silhouette_table(pod_bvh, T0, A, e0, e90, r_out=4.0, h_rng=(-1.75, 4.2), pod_co=None):
    """the pod's largest existing radius per 0.5 degree of angle over its whole height (ray casts toward the axis, and
    the pod's own vertices: some outer faces of the big plates are not found by the ray casts)"""
    ths = np.arange(-180.0, 180.0, 0.5)
    out = np.zeros(len(ths))
    for k, th in enumerate(ths):
        a = math.radians(th + 0.13)
        d = e0 * math.cos(a) + e90 * math.sin(a)
        best = 0.0
        for h in np.arange(h_rng[0], h_rng[1], 0.06):
            hit = pod_bvh.ray_cast(V(T0 + A * h + d * r_out), V(-d), r_out)
            if hit[0] is not None:
                best = max(best, r_out - hit[3])
        out[k] = best
    if pod_co is not None:
        _, pth, pr = pod_frame_coords(pod_co, T0, A, e0, e90)
        for k, th in enumerate(ths):
            m = np.abs((pth - th + 180.0) % 360.0 - 180.0) <= 0.5
            if m.any():
                out[k] = max(out[k], float(pr[m].max()))
    return ths, out


def envelope_report(co, pod_bvh, T0, A, e0, e90, name, r_out=4.0, sil=None, vkind=None):
    """how far detail vertices stick out of the pod's existing radial envelope.
    local: a ray from r_out toward the axis at the vertex's own height and angle finds the outermost existing pod
    surface there (strict: a pipe over the ribs counts from the drum between them).
    silhouette: the pod's largest existing radius at that angle (+-3 deg) over its whole height, i.e. growth of the
    pod's outline seen from that side (silhouette_table)."""
    co = np.asarray(co)
    if len(co) == 0:
        return dict(name=name, verts=0)
    h, th, r = pod_frame_coords(co, T0, A, e0, e90)
    ex = np.zeros(len(co))
    for k in range(len(co)):
        a = math.radians(th[k] + 0.31)
        d = e0 * math.cos(a) + e90 * math.sin(a)
        o = T0 + A * (h[k] + 0.011) + d * r_out
        hit = pod_bvh.ray_cast(V(o), V(-d), r_out)
        r_env = (r_out - hit[3]) if hit[0] is not None else 0.0
        ex[k] = r[k] - r_env
    kinds = {}
    if vkind is not None:
        for k in np.nonzero(ex > 0.15)[0]:
            kinds[vkind[k]] = kinds.get(vkind[k], 0) + 1
    out = dict(name=name, local_max_excess_m=round(float(ex.max()), 3), local_p99_m=round(float(np.percentile(ex, 99)), 3),
               local_verts_over_0_15=int((ex > 0.15).sum()), local_over_0_15_by_kind=kinds, verts=len(ex))
    if sil is not None:
        ths, rmax = sil
        se = np.zeros(len(co))
        for k in range(len(co)):
            dd = np.abs((ths - th[k] + 180.0) % 360.0 - 180.0)
            se[k] = r[k] - rmax[dd <= 3.0].max()
        w = int(np.argmax(se))
        sk = {}
        if vkind is not None:
            for k in np.nonzero(se > 0.0)[0]:
                sk[vkind[k]] = sk.get(vkind[k], 0) + 1
        out.update(silhouette_max_excess_m=round(float(se[w]), 3), silhouette_verts_over_0=int((se > 0.0).sum()),
                   silhouette_over_0_by_kind=sk, silhouette_verts_over_0_05=int((se > 0.05).sum()),
                   silhouette_worst=dict(h=round(float(h[w]), 2), deg=round(float(th[w]), 1), r=round(float(r[w]), 3),
                                         kind=None if vkind is None else vkind[w]))
    return out


def vertex_kinds(mesh):
    vk = ['?'] * len(mesh.v)
    for f, k in zip(mesh.f, mesh.k):
        for i in f:
            vk[i] = k
    return vk


def pa_report(co, path):
    """detail vertices against PA_Airship's hull boxes (UE cm: x*100, -y*100, z*100): inside any box, and standing above
    a box's top inside its footprint (the box tops are the walkable deck)"""
    if not os.path.exists(path):
        return dict(missing=path)
    B = C.load_json(path)['hull_boxes']
    mn = np.array([b['min'] for b in B]); mx = np.array([b['max'] for b in B])
    P = np.asarray(co) * np.array([100.0, -100.0, 100.0])
    inside, above, worst_above = 0, 0, None
    for p in P:
        foot = (p[0] >= mn[:, 0]) & (p[0] <= mx[:, 0]) & (p[1] >= mn[:, 1]) & (p[1] <= mx[:, 1])
        if not foot.any():
            continue
        inb = foot & (p[2] >= mn[:, 2]) & (p[2] <= mx[:, 2])
        inside += int(inb.any())
        up = foot & (p[2] > mx[:, 2])
        if up.any():
            above += 1
            dz = float((p[2] - mx[up, 2]).max())
            worst_above = dz if worst_above is None else max(worst_above, dz)
    return dict(boxes=len(B), verts=len(P), verts_inside_a_box=inside, verts_above_a_box_top=above,
                worst_cm_above_a_top=None if worst_above is None else round(worst_above, 1))


# ================================================================== main
def main(save=True):
    t0 = time.time()
    bpy.ops.wm.open_mainfile(filepath=C.RIG_BLEND)
    ship = S.Ship(bpy)
    mats = D.ensure_materials()
    log = {}
    fl = Flank(ship, K)
    log['chart_s'] = round(time.time() - t0, 1)
    hull = D.Mesh('hull'); hull.cur_group = 'Hull'
    pod = D.Mesh('pod'); pod.cur_group = 'Thruster_FL'
    noz = D.Mesh('noz'); noz.cur_group = 'Thruster_FL_Nozzle'
    pet = D.Mesh('pet'); pet.cur_group = None
    rim_pts = pocket_rim(hull, fl, ship, K, random.Random(K['seed'] + 2), log)
    build_flank(hull, fl, ship, K, random.Random(K['seed'] + 1), log, rim_pts)
    cavity(hull, ship, fl, K, random.Random(K['seed'] + 3), log)
    build_pod(pod, noz, pet, ship, K, random.Random(K['seed'] + 4), log, skin=fl.skin)
    # every loose piece must touch the ship or another piece within 2 cm (repeat: removing one can strand another)
    ship_bvh = ship.bvh(np.ones(len(ship.polys), bool))
    dropped = {}
    for name, m in (('hull', hull), ('pod', pod), ('noz', noz), ('pet', pet)):
        for _ in range(3):
            d = D.drop_floating(m, [ship_bvh], tol=K['touch_tol'])
            if not d:
                break
            for k_, v_ in d.items():
                dropped.setdefault(name, {})[k_] = dropped.get(name, {}).get(k_, 0) + v_
    log['floating_pieces_removed'] = dropped
    log['build_s'] = round(time.time() - t0, 1)

    # ---- objects
    coll = bpy.data.collections.get(COLL) or bpy.data.collections.new(COLL)
    if coll.name not in [c.name for c in bpy.context.scene.collection.children]:
        bpy.context.scene.collection.children.link(coll)
    arm = ship.arm
    objs = {}
    for m, name, bone in ((hull, 'Hull', 'Hull'), (pod, 'Pod_FL', 'Thruster_FL'), (noz, 'Nozzle_FL', 'Thruster_FL_Nozzle'),
                          (pet, 'Petals_FL', None)):
        groups = bone if bone else list(m.g)
        ob = m.to_object(PREFIX + name, coll, mats, arm=arm, groups=groups)
        objs[name] = ob
    # ---- checks
    pod_mask = np.char.startswith(ship.p_bone.astype(str), 'Thruster_FL')
    pod_surf = ship.surface(pod_mask)
    O, T0, A, NP = ship.pod_frame('FL')
    e0, e90 = S.pod_basis(A)
    R = K['pocket']['r']
    hv = np.array(hull.v)
    h_, th_, r_ = pod_frame_coords(hv, T0, A, e0, e90)
    in_cav = (r_ < R + 0.1) & (h_ > K['pocket']['roof_h'] - 0.1) & (h_ < 1.3)
    pod_co = ship.co[np.char.startswith(ship.v_bone.astype(str), 'Thruster_FL')]
    pv = np.array(pod.v)
    sil = silhouette_table(pod_surf.bvh, T0, A, e0, e90, pod_co=pod_co)
    checks = dict(
        hull_flank_vs_skin=dist_report(hv[~in_cav], fl.skin, 'hull details outside the FL pocket vs hull skin', 0.20,
                                       vkind=[k_ for k_, c_ in zip(vertex_kinds(hull), ~in_cav) if c_]),
        hull_cavity_vs_skin=dist_report(hv[in_cav], fl.skin, 'FL pocket cavity details vs hull skin (inside the cavity, no silhouette)', 0.20),
        pod_vs_pod=dist_report(pv, pod_surf, 'pod details vs pod surface', 0.15, vkind=vertex_kinds(pod)),
        nozzle_vs_pod=dist_report(noz.v, pod_surf, 'nozzle details vs pod surface', 0.15),
        petals_vs_pod=dist_report(pet.v, pod_surf, 'petal details vs pod surface', 0.15),
        pod_envelope=envelope_report(pv, pod_surf.bvh, T0, A, e0, e90, 'pod details outside the pod radial envelope',
                                     sil=sil, vkind=vertex_kinds(pod)),
        nozzle_envelope=envelope_report(noz.v, pod_surf.bvh, T0, A, e0, e90, 'nozzle details outside the pod radial envelope',
                                        sil=sil, vkind=vertex_kinds(noz)),
        petal_envelope=envelope_report(pet.v, pod_surf.bvh, T0, A, e0, e90, 'petal details outside the pod radial envelope',
                                       sil=sil, vkind=vertex_kinds(pet)),
        pa_boxes=pa_report(np.concatenate([hv, pv]) if len(pv) else hv, K['pa_boxes']),
        hull_details_max_z=round(float(hv[:, 2].max()), 3) if len(hv) else None,
    )
    nm = {n: D.nonmanifold_edges(o) for n, o in objs.items()}
    tri = {n: sum(len(p.vertices) - 2 for p in o.data.polygons) for n, o in objs.items()}
    kinds = {}
    for m in (hull, pod, noz, pet):
        for k, v in m.tris_by_kind().items():
            kinds[k] = kinds.get(k, 0) + v
    bones = {n: sorted({g.name for g in o.vertex_groups}) for n, o in objs.items()}
    rep = dict(knobs=K, log=log, tris=tri, tris_total=sum(tri.values()), tris_by_kind=kinds, nonmanifold_edges=nm,
               bones=bones, checks=checks, ship_tris_before=sum(len(p.vertices) - 2 for p in ship.ob.data.polygons),
               seconds=round(time.time() - t0, 1))
    os.makedirs(DETAIL_DIR, exist_ok=True)
    C.dump_json(rep, REPORT)
    print('[zone1] tris', tri, 'total', rep['tris_total'])
    print('[zone1] kinds', kinds)
    print('[zone1] checks', json.dumps(checks))
    print('[zone1] log', json.dumps(log))
    print('[zone1] nonmanifold', nm)
    if save:
        bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND, relative_remap=True, compress=False)
        print('[zone1] saved', OUT_BLEND)
    print('[zone1] done %.1f s' % (time.time() - t0))


if __name__ == '__main__':
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    main(save='--no-save' not in argv)
