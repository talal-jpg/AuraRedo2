"""Zone 3 (round 3): the AFT hull flanks, both sides, from zone 1 / zone 2's aft edge (x -11.55) to the stern.

A modified copy of zone 1's flank layout (detail_flank.build_flank; ZONES.md section 6 allows copying a shared function
into a zone module). The kinds, sizes, depths, colours and rivet rules are zone 1's (knobs from detail_zone1.K). What
changes for the aft flank:
  * AftFlank: the chart regions follow the ship's own bands (gunwale band, steam pipes, lower band) instead of fixed
    arc-length windows. Aft of the cannon station the bands climb (the lower band's lower edge goes from s 3.35 at
    x -11.55 to s 2.4 at -15.3), so zone 1's fixed windows lose the lower region there.
  * The masks keep 10-12 cm off every face owned by Z6 (fan mounts, transom), the deck ('none') and Z7 (rails); they
    may run to the bilge line (Z5) and to the zone 1 / zone 2 seam, where the plate rows continue.
  * Continuity at the seam (ZONES.md section 3): reference lines blended into zone 1's (port) / zone 2's (starboard)
    numbers over the last metre; the strake is laid from the seam AFT, its last segment ending at x -11.538 (8 mm
    joint to zone 1's first segment at -11.53); the channel's dark backing ends at -11.56 and its two pipes come out of
    glands at x -11.70; gussets on zone 1's grid x = -11.20 + 0.51 k; the conduit pair ends in glands at -11.70.
  * Clean ends: the lower runs (strake, teeth, channel) end on a riveted rust END RIB near the stern; the upper rows
    end on a riveted rust rib just forward of the fan mount pylon.
"""
import bpy, sys, os, math, random, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from mathutils import Vector as V
from mathutils.bvhtree import BVHTree
import rig_common as C
import detail_common as D
import detail_ship as S
from detail_flank import (Flank, RowMask, tile_rows, fill_gaps, overlaps, x_runs, on_step, plate_rivets, build_plate,
                          smooth_ref, median_ref, wchoice)

SEAM_X = -11.55


# ================================================================== chart with band-aware regions
class AftFlank(Flank):
    """Flank (zone 1's chart) whose regions are found from what covers the skin above / below each free run:
    G = gunwale band (SteamBands above z 1.2), P = steam pipes, L = lower band (SteamBands below z 1.2), T = turbines
    (fan mount pylon / struts), H = hull tabs, O = anything else."""

    def __init__(self, ship, K, side=1):
        mask = ship.p_island != S.SKIN
        super().__init__(ship, K, side=side, obst_mask=mask)
        pidx = np.nonzero(mask)[0]
        ch = self.chart
        nx, nph = ch.hit.shape
        self.lab = np.full((nx, nph), '', dtype=object)
        for i in range(nx):
            ax = np.array([ch.xs[i], side * ch.AY, ch.AZ])
            for j in range(nph):
                if not ch.cov[i, j]:
                    continue
                ph = ch.ph[j]
                d = np.array([0.0, side * math.cos(ph), math.sin(ph)])
                o = ax + 20.0 * d
                ro = self.obst.ray_cast(V(o), V(-d), 30.0)
                if ro[0] is None:
                    self.lab[i, j] = 'O'
                    continue
                isl = int(ship.p_island[pidx[ro[2]]])
                src = ship.islands[isl]['src']
                if src == 'SteamBands':
                    self.lab[i, j] = 'G' if ro[0].z > 1.2 else 'L'
                elif src == 'SteamPipes':
                    self.lab[i, j] = 'P'
                elif src == 'Turbines':
                    self.lab[i, j] = 'T'
                elif src == 'Hull':
                    self.lab[i, j] = 'H'
                else:
                    self.lab[i, j] = 'O'
        self._reg = {}

    def _classify(self, i):
        if i in self._reg:
            return self._reg[i]
        ch = self.chart
        out = {}
        for (j0, j1, s0, s1) in self.runs[i]:
            above = next((self.lab[i, j] for j in range(j0 - 1, -1, -1) if self.lab[i, j]), 'top')
            below = next((self.lab[i, j] for j in range(j1 + 1, len(ch.ph)) if self.lab[i, j]), 'end')
            if above == 'G' and 'up' not in out and s1 - s0 > 0.45:
                out['up'] = (s0, s1)
            elif above == 'P' and below == 'L' and 'mid' not in out and s1 - s0 > 0.25:
                out['mid'] = (s0, s1)
            elif above == 'L' and 'low' not in out and s1 - s0 > 0.5:
                out['low'] = (s0, s1)
        self._reg[i] = out
        return out

    def region(self, x, name):
        i = self.chart.col(x)
        r = self._classify(i).get(name)
        if r is None:
            return None
        if name == 'low':
            lim = self.s_lim[i]
            if np.isnan(lim):
                return None
            r = (r[0], min(r[1], float(lim)))
            if r[1] - r[0] < 0.5:
                return None
        return r


# ================================================================== zone filter for the masks
class ZoneKeep:
    """is a skin point far enough from the faces of the zones we must not touch? (margins per zone)"""

    def __init__(self, ship, zi, margins):
        self.trees = []
        for z, m in margins.items():
            idx = [k for k in range(len(ship.polys)) if zi.zone[k] == z]
            if idx:
                self.trees.append((z, m, BVHTree.FromPolygons(ship.co.tolist(), [ship.polys[k] for k in idx])))

    def ok(self, p):
        for z, m, t in self.trees:
            if t.find_nearest(V(p), m)[0] is not None:
                return False
        return True


def filter_mask(M, fl, keep, log, name):
    """clear the free cells of a RowMask whose skin point is too near a forbidden zone"""
    ch = fl.chart
    n0 = int(M.free.sum())
    for i, x in enumerate(M.xs):
        if np.isnan(M.ref[i]):
            continue
        ci = ch.col(x)
        col = ch.s[ci]
        js = np.nonzero(~np.isnan(col))[0]
        if len(js) < 2:
            continue
        sv = col[js]
        for m in np.nonzero(M.free[i])[0]:
            s_ = M.ref[i] + M.vs[m]
            k = js[int(np.argmin(np.abs(sv - s_)))]
            if not keep.ok(ch.P[ci, k]):
                M.free[i, m] = False
    log['mask_filtered_' + name] = n0 - int(M.free.sum())


def tile_rows_from(M, rng, cfg, K, v_start=0.0, kind='plate'):
    """zone 1's tile_rows (detail_flank) with the first row starting at v_start: on the lower aft flank the strake,
    teeth and pipe channel take the top 1.56 m, so the plate rows start under them instead of straddling them"""
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


# ================================================================== the aft flank build
def blend_to(xs, ref, x_seam, target, width=1.0):
    """add a ramp so that ref(x_seam) == target, fading out over `width` metres aft of the seam"""
    ref = np.array(ref, float)
    if target is None or np.isnan(ref[-1]):
        return ref
    w = np.clip((xs - (x_seam - width)) / width, 0.0, 1.0)
    return ref + w * (target - ref[-1])


def build_aft_flank(mesh, fl, ship, K, rng, log, zi, cont):
    """cont: the neighbour's numbers at the seam (dict ref_up, ref_low, ref_strake) or None"""
    XA, XB = K['x_aft_end'], K['x_mask_fwd']          # mask columns (the plate rows end one seam short of zone 1's)
    ch = fl.chart
    PL = K['plate']
    R = K['rivet']
    LAY = K['layer']
    TOP0 = PL['gap'] + PL['t']
    G2 = TOP0 + LAY
    xs = np.arange(XA, XB + 1e-9, 0.05)
    up_raw = [(fl.region(x, 'up') or (np.nan,))[0] for x in xs]
    low_raw = [(fl.region(x, 'low') or (np.nan,))[0] for x in xs]
    lim = np.array([fl.s_lim[ch.col(x)] for x in xs])
    ref_up = smooth_ref(xs, up_raw) + K['upper']['top_off']
    low_s = median_ref(xs, low_raw, win=0.3)
    ref_low = low_s + K['lower']['top_off']
    seam = cont or {}
    ref_up = blend_to(xs, ref_up, xs[-1], seam.get('ref_up'))
    ref_low = blend_to(xs, ref_low, xs[-1], seam.get('ref_low'))
    v_hi_up = np.where(np.isnan(np.array(low_raw)), lim, np.array(low_raw) - 0.02) - ref_up
    v_hi_low = lim - ref_low
    MU = RowMask(fl, ship, xs, ref_up, v_hi_up, K, rim_pts=(), name='up')
    ML = RowMask(fl, ship, xs, ref_low, v_hi_low, K, rim_pts=(), name='low')
    for i in range(len(xs)):
        for m in range(len(ML.vs)):
            s_ = ML.ref[i] + ML.vs[m]
            if np.isnan(s_) or np.isnan(MU.ref[i]):
                continue
            mu = MU.iv(s_ - MU.ref[i])
            if 0 <= mu < len(MU.vs) and MU.free[i, mu]:
                ML.free[i, m] = False
    keep = ZoneKeep(ship, zi, K['zone_margin'])
    filter_mask(MU, fl, keep, log, 'up')
    filter_mask(ML, fl, keep, log, 'low')
    log['ref_at_seam'] = dict(ref_up=round(float(ref_up[-1]), 4), ref_low=round(float(ref_low[-1]), 4),
                              target=seam)

    # ---------------------------------------------------------------- lower flank plan
    ST, TE, CH, BY = K['strake'], K['teeth'], K['channel'], K['bay']
    v_strip = ST['h'] + ST['back_h'] + 0.2
    m_strip = ML.iv(v_strip)
    strake_runs = x_runs(lambda i: m_strip < len(ML.vs) and bool(ML.free[i, 0:m_strip + 1].all()), xs, 0.8)
    # the END RIB: at the aft end of the strake run that reaches the seam (the runs end on it)
    ER = K['end_rib']
    rib = None
    seam_run = next((r for r in strake_runs if r[1] >= xs[-1] - 0.06), None)
    if seam_run is not None:
        rib = (seam_run[0], seam_run[0] + ER['w'])
        ML.used[ML.ix(rib[0] - 0.03):ML.ix(rib[1] + 0.03) + 1, :] = True
        strake_runs = [[max(a_, rib[1] + 0.03), b_] for a_, b_ in strake_runs if b_ > rib[1] + 0.8]
    log['end_rib'] = None if rib is None else [round(rib[0], 3), round(rib[1], 3)]
    mc0, mc1 = ML.iv(CH['v'][0]), ML.iv(CH['v'][1])
    spans = x_runs(lambda i: mc1 < len(ML.vs) and bool(ML.free[i, mc0:mc1 + 1].all()) and
                   not (rib is not None and xs[i] < rib[1] + 0.03), xs, 1.4)
    log['strake_runs'] = [[round(a_, 2), round(b_, 2)] for a_, b_ in strake_runs]
    log['pipe_spans'] = [[round(a_, 2), round(b_, 2)] for a_, b_ in spans]
    # the strake strip is reserved forward of the end rib only: aft of the rib the skin takes plates again
    i_rib = ML.ix(rib[0] - 0.03) if rib is not None else 0
    ML.used[i_rib:, :ML.iv(CH['v'][0] - 0.02)] = True
    for (xa, xb) in spans:
        ML.used[ML.ix(xa):ML.ix(xb) + 1, ML.iv(CH['v'][0] - 0.02):ML.iv(CH['v'][1] + 0.04) + 1] = True
    bays = []
    BW = K['z3_bay_w']
    # one lower bay per side; where the stern narrows the bay may be shorter than zone 1's (v1 2.78 -> 2.54)
    for v1b in K['z3_bay_v1']:
        m0, m1 = ML.iv(BY['v'][0] - 0.04), ML.iv(v1b + 0.04)
        bay_runs = x_runs(lambda i: m1 < len(ML.vs) and bool(ML.free[i, m0:m1 + 1].all()) and
                          not ML.used[i, m0:m1 + 1].any(), xs, BW[0] + 0.16)
        log['bay_runs'] = [[round(a_, 2), round(b_, 2)] for a_, b_ in bay_runs]
        for (xa, xb) in bay_runs:
            L = xb - xa
            w = min(BW[1], L - 0.16)
            bb = xb - 0.08 - rng.uniform(0.0, max(0.0, L - 0.16 - w))
            ba = bb - w
            ML.used[ML.ix(ba - 0.05):ML.ix(bb + 0.05) + 1, m0:m1 + 1] = True
            bays.append((ba, bb, v1b))
            break
        if bays:
            break
    log['bays'] = [[round(a_, 2), round(b_, 2), v_] for a_, b_, v_ in bays]
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
    # the upper END RIB: at the aft end of the upper rows (just forward of the fan mount pylon)
    urib = None
    up_runs = x_runs(lambda i: bool(MU.free[i, :MU.iv(0.5)].any()), xs, 1.0)
    useam = next((r for r in up_runs if r[1] >= xs[-1] - 0.06), None)
    if useam is not None and useam[0] > xs[0] + 0.1:
        best = None
        for dx_ in np.arange(0.0, 0.45, 0.05):          # the rib where the free height is largest, near the aft end
            xr = (useam[0] + dx_, useam[0] + dx_ + ER['w'])
            i0_, i1_ = MU.ix(xr[0]), MU.ix(xr[1])
            ok_ = MU.free[i0_:i1_ + 1].all(axis=0)
            m_ = 0
            while m_ < len(ok_) and ok_[m_]:
                m_ += 1
            if best is None or m_ > best[1] + 2:
                best = (xr, m_)
        if best is not None and best[1] * MU.dv >= 0.3:
            urib = best[0]
            MU.used[MU.ix(urib[0] - 0.03):MU.ix(urib[1] + 0.03) + 1, :] = True
    log['upper_end_rib'] = None if urib is None else [round(urib[0], 3), round(urib[1], 3)]

    # ---------------------------------------------------------------- plates
    up_rows = tile_rows(MU, rng, K['upper'], K)
    low_rows = tile_rows_from(ML, rng, K['lower'], K, v_start=CH['v'][1] + 0.05)
    fills = fill_gaps(MU, rng, K['fill'], K) + fill_gaps(ML, rng, K['fill'], K)
    if K.get('debug_dir'):
        np.savez(os.path.join(K['debug_dir'], 'mask_%s.npz' % ('port' if fl.side > 0 else 'stbd')),
                 xs=xs, MU_free=MU.free, MU_used=MU.used, ML_free=ML.free, ML_used=ML.used, MU_vs=MU.vs, ML_vs=ML.vs,
                 ref_up=MU.ref, ref_low=ML.ref, lim=lim)
    cov_u = MU.used[MU.free].mean() if MU.free.any() else 0
    log['plates'] = dict(up_rows=len(up_rows), low_rows=len(low_rows), fill=len(fills),
                         coverage_up=round(float(cov_u), 3),
                         free_m2_up=round(float(MU.free.sum() * MU.dx * MU.dv), 1),
                         free_m2_low=round(float(ML.free.sum() * ML.dx * ML.dv), 1))
    base = up_rows + low_rows + fills
    keepout = []

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
    # zone 3: slotted armour on the lower rows too (reference 1's lower flank), K['slots']['low'] of them
    n_low = 0
    low_c = [p for p in low_rows if not p.get('raised') and not p.get('busy') and p['W'] >= 0.85 and p['H'] >= 0.5]
    rng.shuffle(low_c)
    for p in low_c:
        if n_low >= SL.get('low', 0):
            break
        w = min(rng.uniform(*SL['w']), p['W'] - 0.18); h = min(rng.uniform(*SL['h']), p['H'] - 0.14)
        if w < 0.5 or h < 0.28:
            continue
        n_low += int(add_slot(p, w, h))

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
    # zone 1's balance on a small flank: about 30 % calm plate area (K['calm_target']); the largest calm plates get a
    # patch or a frame (deterministic order) until the share is down to it. At least one heavy rust armour plate per
    # side when a raised plate exists (at most ~15 % of the plates).
    area = lambda ps: sum(p['W'] * p['H'] for p in ps)
    tot_a = max(1e-6, area(base))
    nbal = 0
    for p in sorted([p for p in flat if not p.get('busy')], key=lambda p: -p['W'] * p['H']):
        if area([q for q in flat if not q.get('busy')]) / tot_a <= K.get('calm_target', 0.3):
            break
        if p['W'] < 0.5 or p['H'] < 0.34:
            continue
        if p['W'] >= FR['min_w'] and p['H'] >= FR['min_h'] and nbal % 2 == 1:
            e_ = FR['edge']
            r_ = (p['x0'] + e_, p['x0'] + p['W'] - e_, p['v0'] + e_, p['v0'] + p['H'] - e_)
            if not any(k[0] is p['M'] and overlaps(r_, k[1:], 0.0) for k in keepout):
                frames.append(dict(plate=p, edge=e_, inset=False,
                                   mat='paint_ochre' if p['mat'] == 'paint_yellow' else 'paint_yellow'))
                keepout.append((p['M'],) + r_)
                p['busy'] = True
                nbal += 1
                continue
        w = min(max(PA['w'][0], 0.55 * p['W']), p['W'] - 0.16); h = min(max(PA['h'][0], 0.6 * p['H']), p['H'] - 0.12)
        if w < 0.28 or h < 0.2:
            continue
        x0 = p['x0'] + (p['W'] - w) * rng.uniform(0.25, 0.75)
        v0 = p['v0'] + (p['H'] - h) * rng.uniform(0.3, 0.7)
        r_ = (x0, x0 + w, v0, v0 + h)
        if any(k[0] is p['M'] and overlaps(r_, k[1:], 0.03) for k in keepout):
            continue
        patches.append(dict(plate=p, M=p['M'], x0=x0, W=w, v0=v0, H=h, mat=wchoice(rng, PA['mats']),
                            corners=tuple(int(rng.random() < 0.25) for _ in range(4)), cut=rng.uniform(0.04, 0.09),
                            kind='patch'))
        keepout.append((p['M'],) + r_)
        p['busy'] = True
        nbal += 1
    why['balanced_for_calm_share'] = nbal
    if raised and not any(p['mat'] == 'rust_red' for p in raised) and len(base) >= 7:
        max(raised, key=lambda p: p['W'] * p['H'])['mat'] = 'rust_red'
    calm = [p for p in flat if not p.get('busy')]
    log['frame_patch_reasons'] = why
    area = lambda ps: sum(p['W'] * p['H'] for p in ps)
    log['layers'] = dict(raised=len(raised), armour=sum(p['mat'] == 'rust_red' for p in raised), battens=len(battens),
                         slotted=len(slotted), frames=len(frames), patches=len(patches), plates=len(base),
                         calm_plates=len(calm), calm_share_of_area=round(area(calm) / max(1e-6, area(base)), 2),
                         armour_share_of_plates=round(sum(p['mat'] == 'rust_red' for p in raised) / max(1, len(base)), 3))

    # ---------------------------------------------------------------- geometry: plates and their layers
    nr = 0
    for p in flat:
        top_fn = build_plate(mesh, p, K, PL['gap'], PL['t'], PL['bevel'], log)
        if top_fn and p['W'] * p['H'] >= 0.12:
            nr += plate_rivets(mesh, top_fn, p['us'], p['vs'], R, p,
                               lambda x, v, M=p['M']: free_of_keepout(M, x, v))
    for p in raised:
        top_fn = build_plate(mesh, p, K, G2, SH['t'], PL['bevel'], log)
        if top_fn:
            extra = []
            if p['mat'] == 'rust_red':
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

    # ---------------------------------------------------------------- end ribs (the runs end on them)
    def end_rib(M, xr, v0, v1, name):
        f = M.fn(xr[0], v0)
        W, H = xr[1] - xr[0], v1 - v0
        if H < 0.3:
            return 0
        top_fn, ok = D.solid_plate(mesh, f, np.array([0.0, W / 2, W]), D.grid_coords(0.0, H, 0.2), PL['gap'], ER['t'],
                                   0.016, 'rust_red', kind='end_rib')
        if not ok:
            log.setdefault('end_rib_failed', []).append(name)
            return 0
        k = max(1, int(round((H - 0.14) / R['spacing'])))
        return D.rivet_row(mesh, top_fn, [(W / 2, 0.07 + (H - 0.14) * i / k) for i in range(k + 1)], r=R['r'], h=R['h'])

    def free_v_span(M, x0, x1):
        """v range covered by free cells in every column of [x0, x1] (the rib spans the whole free height there)"""
        i0, i1 = M.ix(x0), M.ix(x1)
        ok = M.free[i0:i1 + 1].all(axis=0)
        ms = np.nonzero(ok)[0]
        if len(ms) == 0:
            return None
        # the longest contiguous run from the top
        m_a = ms[0]; m_b = m_a
        while m_b + 1 < len(ok) and ok[m_b + 1]:
            m_b += 1
        return M.vs[m_a] - M.dv / 2, M.vs[m_b] + M.dv / 2
    if rib is not None:
        vr = free_v_span(ML, *rib)
        if vr is not None:
            nr += end_rib(ML, rib, max(vr[0], -0.02), vr[1] - 0.02, 'low')
            log['end_rib_v'] = [round(float(vr[0]), 3), round(float(vr[1]), 3)]
    if urib is not None:
        vr = free_v_span(MU, *urib)
        if vr is not None:
            # from just under the gunwale band (the gussets' strip, above the mask) down to the free end
            xm_ = (urib[0] + urib[1]) / 2
            r_up = fl.region(xm_, 'up')
            v_top = (r_up[0] + 0.03 - MU.s_of(xm_, 0.0)) if r_up else vr[0]
            nr += end_rib(MU, urib, v_top, vr[1] - 0.02, 'up')
            log['upper_end_rib_v'] = [round(float(v_top), 3), round(float(vr[1]), 3)]

    # ---------------------------------------------------------------- strake, backing and teeth: laid from the seam aft
    nteeth = 0
    ref_st = smooth_ref(xs, ML.ref, win=ST['smooth'])
    for (xa, xb) in strake_runs:
        m_ = (xs >= xa - 1e-6) & (xs <= xb + 1e-6) & ~np.isnan(ML.ref)
        xx, yy = xs[m_], ML.ref[m_]
        keep_ = np.ones(len(xx), bool)
        for _ in range(4):
            c_ = np.polyfit(xx[keep_], yy[keep_], 3 if xb - xa > 3.0 else 1)
            res = np.abs(np.polyval(c_, xx) - yy)
            keep_ = res < max(0.03, np.percentile(res, 70))
        ref_st[m_] = np.polyval(c_, xx)
    # never into the lower band: the band's lower edge is wavy (low-poly), so the line keeps 3 cm below the edge's
    # upper envelope (max over +-0.35 m), and stays a smooth cubic (lifted by its largest shortfall)
    lr = np.array(low_raw, float)
    k_ = int(round(0.35 / 0.05))
    env = np.array([np.nanmax(lr[max(0, i - k_):i + k_ + 1]) if np.isfinite(lr[max(0, i - k_):i + k_ + 1]).any()
                    else np.nan for i in range(len(xs))])
    floor_ = env + 0.03
    for (xa, xb) in strake_runs:
        m_ = (xs >= xa - 1e-6) & (xs <= xb + 1e-6) & ~np.isnan(floor_)
        if m_.sum() < 4:
            continue
        lift = float(np.max(floor_[m_] - ref_st[m_]))
        if lift > 0:
            c_ = np.polyfit(xs[m_], floor_[m_], 3 if xb - xa > 3.0 else 1)
            fit2 = np.polyval(c_, xs[m_])
            fit2 += max(0.0, float(np.max(floor_[m_] - fit2)))
            ref_st[m_] = np.maximum(ref_st[m_], fit2)
    ref_st = blend_to(xs, ref_st, xs[-1], seam.get('ref_strake'), width=1.2)
    log['strake_line'] = dict(at_seam=round(float(ref_st[-1]), 4), aft=round(float(ref_st[0]), 4))
    xs_ext = np.append(xs, SEAM_X + 0.03)
    ref_st_ext = np.append(ref_st, ref_st[-1])

    def st_line(x):
        return float(np.interp(x, xs_ext, ref_st_ext))

    def seg_free(x0, L, why=None):
        for xq in np.linspace(x0, x0 + L, 7):
            r0 = st_line(xq)
            for vq in (0.03, 0.1, 0.2, 0.4, 0.6, 0.8):
                if not ch.free_at(xq, r0 + vq, 0.0):
                    if why is not None:
                        why.append((round(float(xq), 2), vq, round(r0 + vq, 3)))
                    return False
        return True

    def fn_st(x0, v0):
        def f(u, v):
            x = x0 + u
            return ch.surf(x, st_line(x) + v0 + v)
        return f
    gT = PL['gap'] + ST['back_t'] + LAY
    nseg = nskip = 0
    cont_seg = []

    def segment(x, L, w, g):
        nonlocal nr, nteeth
        f = fn_st(x, 0.0)
        D.solid_plate(mesh, f, D.grid_coords(0.0, L - 0.008, 0.5), D.grid_coords(0.0, ST['h'], 0.25), PL['gap'],
                      ST['t'], 0.016, 'rust_red', kind='strake')
        top = lambda u, v, f=f: (lambda r: None if r is None else (r[0] + r[1] * (PL['gap'] + ST['t']), r[1]))(f(u, v))
        nr += D.rivet_row(mesh, top, [(0.08, ST['h'] / 2), ((L - 0.008) / 2, ST['h'] / 2), (L - 0.088, ST['h'] / 2)],
                          r=R['r'], h=R['h'])
        fb = fn_st(x, ST['h'] + 0.004)
        D.solid_plate(mesh, fb, D.grid_coords(0.0, L - 0.008, 0.5), D.grid_coords(0.0, ST['back_h'], 0.3), PL['gap'],
                      ST['back_t'], 0.004, 'dark_metal', kind='strake')
        cont_seg.append(dict(x0=round(float(x), 4), L=round(float(L), 4), top0=f(0.0, 0.0), top1=f(L - 0.008, 0.0)))
        if L >= w + 0.06:
            h = rng.uniform(*TE['h'])
            v0 = ST['h'] + 0.008
            ft = fn_st(x + g / 2, v0)
            cut = TE['chamfer']
            us = D.grid_coords(0.0, w, 0.45, cut); vs = D.grid_coords(0.0, h, 0.3, cut)
            if not on_step(ft, w, h, K['step_tol']):
                top_fn, ok = D.solid_plate(mesh, ft, us, vs, gT, TE['t'], 0.014, 'rust_red', corners=(0, 0, 1, 0),
                                           kind='tooth')
                if ok:
                    nteeth += 1
                    nr += D.rivet_row(mesh, top_fn, [(0.1, 0.07), (w - 0.1, 0.07)], r=R['r'], h=R['h'])
    if K.get('debug_dir'):
        dbg = []
        for xq in np.arange(xs[0], SEAM_X, 0.1):
            fq = fn_st(xq, 0.0)
            why = []
            dbg.append((round(float(xq), 2), seg_free(xq, 0.9, why), on_step(fq, 0.9, ST['h'] + ST['back_h'], K['step_tol']), why))
        log['debug_strake_tests'] = dbg
    for (xa, xb) in strake_runs:
        at_seam = xb >= xs[-1] - 0.06
        if at_seam:
            xe = SEAM_X + 0.02                          # = -11.53: zone 1's first segment starts here; ours ends 8 mm short
            while xe - (xa + 0.02) >= 0.5:
                w = rng.uniform(*TE['w']); g = rng.uniform(*TE['gap'])
                L = min(w + g, xe - (xa + 0.02))
                placed = False
                for L_ in (L, L - 0.15, L - 0.3):        # a shorter segment (and tooth) before giving up the joint
                    if L_ < 0.5:
                        break
                    x = xe - L_
                    f = fn_st(x, 0.0)
                    if seg_free(x, L_) and not on_step(f, L_, ST['h'] + ST['back_h'], K['step_tol']):
                        segment(x, L_, min(w, L_ - g), g)
                        nseg += 1
                        xe = x
                        placed = True
                        break
                if not placed:
                    xe -= 0.1
                    nskip += 1
        else:
            x = xa + 0.02
            while x < xb - 0.5:
                w = rng.uniform(*TE['w']); g = rng.uniform(*TE['gap'])
                L = min(w + g, xb - x)
                f = fn_st(x, 0.0)
                if not seg_free(x, L) or on_step(f, L, ST['h'] + ST['back_h'], K['step_tol']):
                    x += 0.1
                    nskip += 1
                    continue
                segment(x, L, w, g)
                nseg += 1
                x += L
    log['strake'] = dict(segments=nseg, shifted_for_a_shelf=nskip)
    log['teeth'] = nteeth

    # ---------------------------------------------------------------- gussets under the gunwale band (zone 1's grid)
    G = K['gusset']
    ng = 0
    cont_gus = []
    gx0 = K['gusset_grid_x0']
    kmax = int(math.floor((gx0 - XA) / G['step']))
    for kk in range(1, kmax + 1):
        x = gx0 - G['step'] * kk
        if x > XB + 0.02:
            continue
        r = fl.region(x, 'up')
        if r is None:
            continue
        s = r[0] + 0.012
        a = ch.surf(x, s); b = ch.surf(x, s + 0.08)
        if a is None or b is None or not ch.free_at(x, s + G['height'] / 2, G['height'] / 2):
            continue
        if not keep.ok(a[0]):
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
        at_seam = xb >= xs[-1] - 0.06
        xb_back = SEAM_X - 0.01 if at_seam else xb - 0.05     # backing to -11.56 at the seam
        xb_gl = K['seam_gland_x'] if at_seam else xb - 0.14   # pipes come out of glands at -11.70 at the seam
        xb_pts = xb_gl - 0.18
        f = ML.fn(xa + 0.05, CH['v'][0])
        L = xb_back - (xa + 0.05)
        D.solid_plate(mesh, f, D.grid_coords(0.0, L, 0.5), D.grid_coords(0.0, CH['v'][1] - CH['v'][0], 0.25), PL['gap'],
                      0.015, 0.004, 'dark_metal', kind='channel')
        base_off = PL['gap'] + 0.015
        vv = (CH['v'][0] + 0.13, CH['v'][0] + 0.37)
        for k, (rp, v_) in enumerate(zip(CH['r'], vv)):
            off = base_off + 0.006 + rp
            pts = []
            for x in np.linspace(xa + 0.32, xb_pts, max(4, int((xb_pts - xa - 0.32) / 0.35))):
                q = ch.surf(x, ML.s_of(x, v_))
                if q is None:
                    pts = None
                    break
                pts.append(q[0] + q[1] * off)
            q0 = ch.surf(xa + 0.14, ML.s_of(xa + 0.14, v_)); q1 = ch.surf(xb_gl, ML.s_of(xb_gl, v_))
            if not pts or q0 is None or q1 is None:
                continue
            path = [q0[0] - q0[1] * 0.02] + pts + [q1[0] - q1[1] * 0.02]
            ncl = max(1, int((xb_gl - xa) / CH['clamp_step']))
            D.pipe_run(mesh, path, rp, 0.16, sides=12, mat='copper' if k == 0 else 'brass', flange_at=(0.25, 0.7),
                       flange_k=1.25, clamp_at=[(i + 0.5) / ncl for i in range(ncl)], surf_fn=surf_below, kind='pipe')
            for q in (q0, q1):
                D.gland(mesh, q[0], q[1], (1, 0, 0), rp, size=rp * 1.9, back=base_off)
            if k == 0 and len(pts) > 4:
                i = len(pts) // 3
                xv = xa + 0.32 + (xb_pts - xa - 0.32) * i / (len(pts) - 1)
                nq = ch.surf(xv, ML.s_of(xv, v_))
                if nq is not None:
                    D.valve_body(mesh, pts[i], D.unit(pts[i + 1] - pts[i - 1]), nq[1], rp * 0.88)
            chan[(xa, xb, k)] = (v_, off, rp)
            cont_chan.append(dict(span=[round(float(xa), 3), round(float(xb), 3)], pipe=k, v=v_, centre_off=off, r=rp,
                                  end_aft=path[0], first=path[1], last=path[-2], end_fwd=path[-1]))
            npipe += 1
    log['pipes'] = npipe

    # ---------------------------------------------------------------- machinery bays (zone 1's bay code)
    def bay_shell(f, W, H, rim, rim_t):
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
    for bi, (ba, bb, v1b) in enumerate(bays):
        W = bb - ba
        v0, v1 = BY['v'][0], v1b
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
                st, sd = ends[0]
                D.pipe_run(mesh, [st - sd * 0.01, st + sd * 0.06, pa_ - tp * 0.07, pa_ + tp * 0.045],
                           0.04, 0.06, sides=8, mat='copper', flange_at=(), kind='bay')
            a2 = f(rest_u0 + 0.05, hc_v + hh * 0.3); b2 = f(rest_u0 + 0.05 + max(0.36, Lp - 0.12), hc_v + hh * 0.3)
            if a2 is not None and b2 is not None:
                off2 = floor + 0.012 + 0.062
                D.tank(mesh, a2[0] + a2[1] * off2, b2[0] + b2[1] * off2, 0.062, a2[1], mat='rust_red')
        elif Lp >= 0.2:
            # zone 3: a narrow bay (the stern tapers) has no room for the pump: an upright gas bottle in its place,
            # valve end up, fed from the housing's upper stub
            ub = rest_u0 + Lp / 2
            a2 = f(ub, iv1 - 0.06); b2 = f(ub, iv0 + 0.1)
            if a2 is not None and b2 is not None:
                off2 = floor + 0.012 + 0.062
                pa2, pb2 = a2[0] + a2[1] * off2, b2[0] + b2[1] * off2
                D.tank(mesh, pa2, pb2, 0.062, a2[1], mat='rust_red')
                st, sd = ends[0]
                tb = D.unit(pb2 - pa2)
                top_ = pb2 + tb * 0.07
                D.pipe_run(mesh, [st - sd * 0.01, st + sd * 0.05, top_ + tb * 0.06 - sd * 0.0, top_ - tb * 0.005],
                           0.022, 0.04, sides=8, mat='copper', flange_at=(), kind='bay')
                log['bay_bottle'] = log.get('bay_bottle', 0) + 1
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

    # ---------------------------------------------------------------- conduit pair along the bottom of the upper rows
    CD = K['conduit']
    top_all_c = G2 + max(SH['t'], BT['t'], 0.048) + 0.008

    def base_top(x, s):
        q = plate_at(MU, x, s - float(np.interp(x, MU.xs, MU.ref)))
        if q is None or not q.get('top_fn'):
            return 0.0
        return q.get('top', TOP0)
    fun = lambda x: (lambda r: r[1] - 0.06 if r else None)(fl.region(x, 'up'))
    ncond = 0
    nfit = 0
    cont_cond = []
    # one run: from the seam gland (x -11.70) aft while the upper run lasts (it ends at the pylon's rib)
    x_end_c = K['seam_gland_x']
    run = []
    for x in np.arange(x_end_c, XA, -0.25):
        sv = fun(x)
        q = ch.surf(x, sv) if sv is not None else None
        if q is None or not ch.free_at(x, sv, 0.05) or (urib is not None and x < urib[1] + 0.12):
            break
        run.append((x, q))
    run = run[::-1]
    if len(run) >= 5:
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
            path = [qa[0] - qa[1] * 0.02] + pts + [qb[0] - qb[1] * 0.02]     # each end drops into a gland
            n_cl = max(2, int(len(pts) * 0.25 / CD['clamp_step']))
            D.pipe_run(mesh, path, rr, 0.08, sides=8, mat='dark_metal' if k == 0 else 'brass', flange_at=(),
                       clamp_at=[(i + 0.5) / n_cl for i in range(n_cl)], surf_fn=surf_below, kind='conduit')
            for (xx, ss), q in (((xa_, sa_), qa), ((xb_, sb_), qb)):
                D.gland(mesh, q[0], q[1], (1, 0, 0), rr, size=0.065, back=base_top(xx, ss))
            ncond += 1
            cont_cond.append(dict(pipe=k, r=rr, x=[round(float(xa_), 3), round(float(xb_), 3)],
                                  s=[round(float(sa_), 4), round(float(sb_), 4)], centre_off=top_all_c + rr))
            if k == 0 and CD.get('fittings_z3', 0) > 0:
                Lr = xs_r[-1][0] - xs_r[0][0]
                cands = [xs_r[0][0] + Lr * f_ for f_ in (0.45, 0.6, 0.35)]
                for xf in cands:
                    if nfit >= CD['fittings_z3']:
                        break
                    sv = float(np.interp(xf, rx, rs))
                    q0 = ch.surf(xf, sv); q1 = ch.surf(xf, sv - 0.2); q2 = ch.surf(xf, sv - 0.3)
                    if q0 is None or q1 is None or q2 is None or \
                            not free_of_keepout(MU, xf, sv - 0.3 - float(np.interp(xf, MU.xs, MU.ref)), 0.08):
                        continue
                    off = top_all_c + rr
                    D.pipe_run(mesh, [q0[0] + q0[1] * off, q1[0] + q1[1] * off, q2[0] - q2[1] * 0.02], 0.028, 0.07,
                               sides=8, mat='brass', flange_at=(0.35,), kind='conduit')
                    D.gland(mesh, q2[0], q2[1], (1, 0, 0), 0.028, size=0.06, back=base_top(xf, sv - 0.3))
                    nfit += 1
    log['conduits'] = ncond
    log['through_hull_fittings'] = nfit
    log['hull_rivets'] = nr
    rr4 = lambda a: [None if (v is None or not np.isfinite(v)) else round(float(v), 4) for v in a]
    log['continuity'] = dict(
        side=fl.side, x_range=[XA, XB], xs=rr4(xs), ref_up=rr4(MU.ref), ref_low=rr4(ML.ref), ref_strake=rr4(ref_st),
        s_bilge=rr4(lim), end_rib=log['end_rib'], upper_end_rib=log['upper_end_rib'],
        strake_runs=strake_runs, strake_segments=cont_seg, channel_spans=spans, channel_pipes=cont_chan,
        lower_bays=bays, upper_bays=ubays, gussets=cont_gus, conduits=cont_cond)
    return dict(MU=MU, ML=ML, base=base)
