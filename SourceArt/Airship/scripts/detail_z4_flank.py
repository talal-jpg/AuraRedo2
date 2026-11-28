"""Zone 4 (bow) hull flanks: zone 1's chart-based flank layout carried forward of the FL / FR pocket rims (x 6.95) to
the bow wedge's aft face (x 15.5), both sides.

A modified copy of detail_flank.build_flank (the shared module is only imported):
  * BowFlank finds the bands by island: the gunwale band (414 / 415) and the bow's own lower band (416 / 418, which
    starts at x 6.84 just forward of the pocket); the upper rows hang under the gunwale band, the strake and teeth
    under the lower band, the lower rows go down to the keel block (Underside_Front) around the ship's belly tabs
  * the chart reaches up to 60 deg, so the deck edge (s = 0) is found where the hull narrows
  * gussets on zone 1's grid x = -11.20 + 0.51 k; ref_up blends into zone 1's / zone 2's value over the first metre
  * strake runs end on a riveted rust end rib; no middle strip; continuity export for the record
"""
import math
import numpy as np
from mathutils import Vector as V
import detail_common as D
import detail_ship as S
from detail_flank import Flank, RowMask, smooth_ref, median_ref, x_runs, tile_rows, fill_gaps, on_step
from detail_z4_lib import layer_plates, ZONE1_STYLE


class BowFlank(Flank):
    """zone 1's Flank with the bow's bands: region('up') = the free run under the gunwale band, region('low') = the
    free run under the bow's lower band; no middle strip"""

    def __init__(self, ship, K, side, obst_mask, band_up, band_low):
        super().__init__(ship, K, side=side, obst_mask=obst_mask)
        ch = self.chart
        bu = ship.bvh(np.isin(ship.p_island, band_up))
        bl = ship.bvh(np.isin(ship.p_island, band_low))
        nx, nphi = len(ch.xs), len(ch.ph)
        self.j_up = np.full(nx, -1)          # last cell (from the top) covered by the gunwale band
        self.j_low = np.full(nx, -1)         # last cell covered by the lower band
        self.j_low0 = np.full(nx, nphi)      # first cell covered by the lower band
        for i, x in enumerate(ch.xs):
            ax = np.array([x, side * ch.AY, ch.AZ])
            for j, p in enumerate(ch.ph):
                if not ch.hit[i, j]:
                    continue
                d = np.array([0.0, side * math.cos(p), math.sin(p)])
                o = ax + 20.0 * d
                dist_skin = float(np.linalg.norm(o - ch.P[i, j]))
                for bv, which in ((bu, 'u'), (bl, 'l')):
                    r = bv.ray_cast(V(o), V(-d), dist_skin + 0.01)
                    if r[0] is not None and r[3] < dist_skin + 0.002:
                        if which == 'u':
                            self.j_up[i] = j
                        else:
                            self.j_low[i] = j
                            self.j_low0[i] = min(self.j_low0[i], j)

    def region(self, x, name):
        i = self.chart.col(x)
        R = self.runs[i]
        if name == 'up':
            ju, jl = self.j_up[i], self.j_low0[i]
            if ju < 0:
                return None
            return next(((s0, s1) for (j0, j1, s0, s1) in R if j0 > ju and j0 < jl and s1 - s0 > 0.12), None)
        if name == 'low':
            jl = self.j_low[i]
            if jl < 0:
                return None
            r = next(((s0, s1) for (j0, j1, s0, s1) in R if j0 > jl and s1 - s0 > 0.3), None)
            if r is None:
                return None
            lim = self.s_lim[i]
            if np.isnan(lim):
                return None
            r = (r[0], min(r[1], float(lim)))
            return r if r[1] - r[0] >= 0.3 else None
        return None


def blend_seam(xs, ref, x_seam, target, width=1.0):
    """move ref toward `target` near x_seam (weight 1 at the seam, 0 at x_seam + width)"""
    if target is None:
        return ref
    w = np.clip(1.0 - (xs - x_seam) / width, 0.0, 1.0)
    w = w * w * (3 - 2 * w)
    return np.where(np.isnan(ref), ref, ref * (1 - w) + target * w)


def keep_off(M, fl, bvhs, dist, x_max):
    """mark mask cells (columns with x < x_max) within `dist` of a neighbour zone's details as not free (the seam
    rule: 10 cm from another zone; zone 1's / zone 2's pocket rim straps reach forward to x 7.28 low on the flank)"""
    n = 0
    for i, x in enumerate(M.xs):
        if x > x_max:
            break
        for m in range(len(M.vs)):
            if not M.free[i, m]:
                continue
            q = fl.chart.surf(x, M.s_of(x, M.vs[m]))
            if q is None:
                continue
            if any(b.find_nearest(V(q[0]), dist)[0] is not None for b in bvhs):
                M.free[i, m] = False
                n += 1
    return n


def build_bow_flank(mesh, fl, ship, K, rng, log, seam, nbvh=()):
    """seam: dict(ref_up=..., source=...) from the neighbour's continuity file (zone 1 port, zone 2 starboard);
    nbvh: the neighbour zones' detail BVHs (cells near them are kept free)"""
    XA, XB = K['x_aft'], K['x_fwd_plates']
    ch = fl.chart
    PL, R, LAY = K['plate'], K['rivet'], K['layer']
    TOP0 = PL['gap'] + PL['t']
    G2 = TOP0 + LAY
    xs = np.arange(XA, XB + 1e-9, 0.05)
    up_raw = [(fl.region(x, 'up') or (np.nan,))[0] for x in xs]
    low_raw = [(fl.region(x, 'low') or (np.nan,))[0] for x in xs]
    lim = np.array([fl.s_lim[ch.col(x)] for x in xs])
    ref_up = smooth_ref(xs, up_raw, win=0.4) + K['upper']['top_off']
    ref_up = blend_seam(xs, ref_up, XA - 0.1, seam.get('ref_up'), 1.0)
    up_ok = ~np.isnan(np.array(up_raw))
    low_s = median_ref(xs, low_raw, win=0.3)
    ref_low = low_s + K['lower']['top_off']
    up_end = np.array([(fl.region(x, 'up') or (np.nan, np.nan))[1] for x in xs])
    v_hi_up = np.where(up_ok, up_end - 0.02 - ref_up, np.nan)
    v_hi_low = lim - ref_low
    MU = RowMask(fl, ship, xs, ref_up, np.where(np.isnan(v_hi_up), -1.0, v_hi_up), K, name='up')
    ML = RowMask(fl, ship, xs, ref_low, v_hi_low, K, name='low')
    for i in range(len(xs)):
        for m in range(len(ML.vs)):
            s_ = ML.ref[i] + ML.vs[m]
            if np.isnan(s_) or np.isnan(MU.ref[i]):
                continue
            mu = MU.iv(s_ - MU.ref[i])
            if 0 <= mu < len(MU.vs) and MU.free[i, mu]:
                ML.free[i, m] = False
    # keep the zone's 10 cm margin to the aft seam and stop short of the wedge's aft face
    for M in (MU, ML):
        M.free[xs < XA + 0.0] = False
        M.free[xs > XB - 0.03] = False
    log['cells_kept_off_neighbours'] = sum(keep_off(M, fl, nbvh, K['z4']['seam_clear'], XA + 0.9) for M in (MU, ML))
    log['flank_free_m2'] = dict(up=round(float(MU.free.sum() * MU.dx * MU.dv), 1),
                                low=round(float(ML.free.sum() * ML.dx * ML.dv), 1))

    # ---------------------------------------------------------------- lower flank plan: strake + teeth strip
    ST, TE, CH = K['strake'], K['teeth'], K['channel']
    # the strip under the band is shorter at the bow (the belly tabs sit close under it forward of x 10.5): the run
    # continues where a strake + short teeth fit, the backing and the teeth shortened to the free height there
    TZ = K['z4']['teeth_min']
    avail = np.zeros(len(xs))
    for i in range(len(xs)):
        col = ML.free[i]
        k = 0
        while k < len(col) and col[k]:
            k += 1
        avail[i] = k * ML.dv
    v_min = ST['h'] + 0.008 + TZ + 0.06
    strake_runs = x_runs(lambda i: avail[i] >= v_min, xs, 0.8)
    log['strake_runs'] = [[round(a_, 2), round(b_, 2)] for a_, b_ in strake_runs]
    for (xa, xb) in strake_runs:
        for i in range(ML.ix(xa), ML.ix(xb) + 1):
            ML.used[i, :ML.iv(min(avail[i], ST['h'] + max(ST['back_h'], TE['h'][1]) + 0.03)) + 1] = True
    mc0, mc1 = ML.iv(CH['v'][0]), ML.iv(CH['v'][1])
    spans = x_runs(lambda i: mc1 < len(ML.vs) and bool(ML.free[i, mc0:mc1 + 1].all()) and
                   not ML.used[i, mc0:mc1 + 1].any(), xs, 1.4)
    log['pipe_spans'] = [[round(a_, 2), round(b_, 2)] for a_, b_ in spans]
    for (xa, xb) in spans:
        ML.used[ML.ix(xa):ML.ix(xb) + 1, ML.iv(CH['v'][0] - 0.02):ML.iv(CH['v'][1] + 0.04) + 1] = True

    # ---------------------------------------------------------------- plates + zone 1's layers
    up_rows = tile_rows(MU, rng, K['upper'], K)
    low_rows = tile_rows(ML, rng, K['lower'], K)
    FF = K['z4'].get('flank_fill', K['fill'])   # bigger gap fillers on the bow flank (look-and-fix pass)
    fills = fill_gaps(MU, rng, FF, K) + fill_gaps(ML, rng, FF, K)
    st = layer_plates(mesh, up_rows + low_rows, fills, K, rng, log, style=dict(ZONE1_STYLE, slots=K['z4']['flank_slots'],
                                                                          frame_min=K['z4']['flank_frame_min']),
                      tag='flank_%s' % ('port' if fl.side > 0 else 'stbd'))
    nr = st['rivets']
    base = up_rows + low_rows + fills

    def plate_at(M, x, v):
        for q in base:
            if q['M'] is M and q['x0'] - 0.012 <= x <= q['x0'] + q['W'] + 0.012 and q['v0'] - 0.012 <= v <= q['v0'] + q['H'] + 0.012:
                return q
        return None

    # ---------------------------------------------------------------- strake, dark backing and teeth
    nteeth = 0
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

    def seg_free(x0, L, depth=0.75):
        for xq in np.linspace(x0, x0 + L, 7):
            r0 = float(np.interp(xq, xs, ref_st))
            for vq in np.linspace(0.0, depth, 6):
                if not ch.free_at(xq, r0 + vq, 0.0):
                    return False
        return True

    def av_at(x0, L):
        i0, i1 = max(0, ML.ix(x0)), min(len(xs) - 1, ML.ix(x0 + L))
        return float(avail[i0:i1 + 1].min()) if i1 >= i0 else 0.0

    def fn_st(x0, v0):
        def f(u, v):
            x = x0 + u
            return ch.surf(x, float(np.interp(x, xs, ref_st)) + v0 + v)
        return f
    gT = PL['gap'] + ST['back_t'] + LAY
    nseg = nskip = 0
    cont_seg = []
    ER = K['z4']['end_rib']
    for (xa, xb) in strake_runs:
        x = xa + 0.02
        first = None
        last = None
        while x < xb - 0.5:
            w = rng.uniform(*TE['w'])
            g = rng.uniform(*TE['gap'])
            L = min(w + g, xb - x)
            f = fn_st(x, 0.0)
            av = av_at(x, L)
            th_max = min(TE['h'][1], av - ST['h'] - 0.06)          # tallest tooth that fits here
            bh = min(ST['back_h'], th_max - 0.04)                   # backing a little shorter than the teeth
            if bh < 0.2 or not seg_free(x, L, ST['h'] + bh) or on_step(f, L, ST['h'] + bh, K['step_tol']):
                x += 0.1
                nskip += 1
                continue
            D.solid_plate(mesh, f, D.grid_coords(0.0, L - 0.008, 0.5), D.grid_coords(0.0, ST['h'], 0.25), PL['gap'],
                          ST['t'], 0.016, 'rust_red', kind='strake')
            top = lambda u, v, f=f: (lambda r: None if r is None else (r[0] + r[1] * (PL['gap'] + ST['t']), r[1]))(f(u, v))
            nr += D.rivet_row(mesh, top, [(0.08, ST['h'] / 2), ((L - 0.008) / 2, ST['h'] / 2), (L - 0.088, ST['h'] / 2)],
                              r=R['r'], h=R['h'])
            fb = fn_st(x, ST['h'] + 0.004)
            D.solid_plate(mesh, fb, D.grid_coords(0.0, L - 0.008, 0.5), D.grid_coords(0.0, bh, 0.3), PL['gap'],
                          ST['back_t'], 0.004, 'dark_metal', kind='strake')
            nseg += 1
            first = x if first is None else first
            last = x + L - 0.008
            cont_seg.append(dict(x0=round(float(x), 4), L=round(float(L), 4), top0=f(0.0, 0.0), bot0=fb(0.0, bh)))
            if L >= w + 0.06 and th_max >= TZ:
                h = min(rng.uniform(*TE['h']), th_max)
                v0 = ST['h'] + 0.008
                xt = x + g / 2
                ft = fn_st(xt, v0)
                cut = TE['chamfer']
                us = D.grid_coords(0.0, w, 0.45, cut); vs = D.grid_coords(0.0, h, 0.3, cut)
                if not on_step(ft, w, h, K['step_tol']) and seg_free(xt, w, ST['h'] + h):
                    top_fn, ok = D.solid_plate(mesh, ft, us, vs, gT, TE['t'], 0.014, 'rust_red', corners=(0, 0, 1, 0),
                                               kind='tooth')
                    if ok:
                        nteeth += 1
                        nr += D.rivet_row(mesh, top_fn, [(0.1, 0.07), (w - 0.1, 0.07)], r=R['r'], h=R['h'])
            x += L
        # the run ends on riveted rust end ribs over the strake + backing (a clean end, no cut-off plate)
        for xe, s_ in ((first, 1), (last, -1)):
            if xe is None:
                continue
            x0 = xe - ER['w'] / 2 if s_ > 0 else xe - ER['w'] / 2
            f = fn_st(x0, -0.02)
            Hh = ST['h'] + min(ST['back_h'], av_at(x0, ER['w']) - ST['h'] - 0.1) + 0.04
            if f(0.0, 0.0) is None or f(ER['w'], Hh) is None:
                continue
            top_fn, ok = D.solid_plate(mesh, f, np.array([0.0, ER['w']]), D.grid_coords(0.0, Hh, 0.25), PL['gap'],
                                       ER['t'], 0.014, 'rust_red', kind='strake')
            if ok:
                nr += D.rivet_row(mesh, top_fn, [(ER['w'] / 2, 0.07 + (Hh - 0.14) * k / 3) for k in range(4)],
                                  r=R['r'], h=R['h'])
    log['strake'] = dict(segments=nseg, shifted_for_a_shelf=nskip)
    log['teeth'] = nteeth

    # ---------------------------------------------------------------- gussets under the gunwale band (zone 1's grid)
    G = K['gusset']
    ng = 0
    cont_gus = []
    k0 = math.ceil((XA + 0.05 - K['z4']['gusset_x0']) / G['step'])
    for x in K['z4']['gusset_x0'] + G['step'] * np.arange(k0, k0 + 60):
        if x > XB - 0.1:
            break
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

    # ---------------------------------------------------------------- pipe channel (only where a 1.4 m span fits)
    npipe = 0
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
                D.valve_body(mesh, pts[i], D.unit(pts[i + 1] - pts[i - 1]), q0[1], rp * 0.88)
            npipe += 1
    log['pipes'] = npipe

    # ---------------------------------------------------------------- conduit pair under the upper rows (zone 1's)
    CD = K['conduit']
    SH, BT = K['shingle'], K['batten']
    top_all_c = G2 + max(SH['t'], BT['t'], 0.048) + 0.008

    def base_top(x, s):
        q = plate_at(MU, x, s - float(np.interp(x, MU.xs, MU.ref)))
        if q is None or not q.get('top_fn'):
            return 0.0
        return q.get('top', TOP0)

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
    ncond = 0
    cont_cond = []
    fun = lambda x: (lambda r: r[1] - 0.06 if r and r[1] - r[0] > K['z4']['conduit_min_strip'] else None)(fl.region(x, 'up'))
    for run in runs_of(fun):
        run = run[1:-1]
        if len(run) < 5:
            continue
        rx = np.array([x for (x, _) in run])
        rs = smooth_ref(rx, [fun(x) for x in rx], win=CD['smooth'])
        for k, rr in enumerate(CD['r_up']):
            pts, xs_r = [], []
            for x, s0 in zip(rx, rs):
                sv = s0 - k * 0.095
                qq = ch.surf(x, sv)
                if qq is None:
                    continue
                pts.append(qq[0] + qq[1] * (top_all_c + rr)); xs_r.append((x, sv))
            if len(pts) < 5:
                continue
            (xa_, sa_), (xb_, sb_) = xs_r[0], xs_r[-1]
            qa, qb = ch.surf(xa_, sa_), ch.surf(xb_, sb_)
            path = [qa[0] - qa[1] * 0.02] + pts + [qb[0] - qb[1] * 0.02]
            n_cl = max(2, int(len(pts) * 0.25 / CD['clamp_step']))
            D.pipe_run(mesh, path, rr, 0.08, sides=8, mat='dark_metal' if k == 0 else 'brass', flange_at=(),
                       clamp_at=[(i + 0.5) / n_cl for i in range(n_cl)], surf_fn=surf_below, kind='conduit')
            for (xx, ss), q in (((xa_, sa_), qa), ((xb_, sb_), qb)):
                D.gland(mesh, q[0], q[1], (1, 0, 0), rr, size=0.065, back=base_top(xx, ss))
            ncond += 1
            cont_cond.append(dict(pipe=k, r=rr, x=[round(float(xa_), 3), round(float(xb_), 3)], end_aft=path[1],
                                  end_fwd=path[-2]))
    log['conduits'] = ncond
    log['hull_rivets'] = log.get('hull_rivets', 0) + nr
    rr4 = lambda a: [None if (v is None or not np.isfinite(v)) else round(float(v), 4) for v in a]
    log.setdefault('continuity', {})['port' if fl.side > 0 else 'stbd'] = dict(
        side=fl.side, x_range=[XA, XB], seam_from=seam.get('source'), xs=rr4(xs[::4]), ref_up=rr4(MU.ref[::4]),
        ref_low=rr4(ML.ref[::4]), ref_strake=rr4(ref_st[::4]),
        about='Z4 bow flank: ref_up = top of the upper rows (gunwale band + top_off, blended into the neighbour over '
              'the first metre); ref_low = top of the strake under the bow\'s lower band (islands 416 / 418, which '
              'start at x 6.84: a new band, so the strake line is new at the bow); s = arc length from the deck edge',
        strake_runs=strake_runs, strake_segments=cont_seg[:3] + cont_seg[-2:], gussets=cont_gus, conduits=cont_cond)
    return dict(MU=MU, ML=ML, plates=base)
