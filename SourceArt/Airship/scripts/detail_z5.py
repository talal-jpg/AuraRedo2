"""Zone 5 of the airship detail pass (round 3, 2026-11-28): the BELLY and KEEL.

Z5 (detail_zones.py) = the belly below the bilge line (chart angle -56 deg) on both sides, from the transom to x 6.95,
around (not on) the four pods and their pockets (each pod's zone owns the belly within 3.1 m of its axis), plus the
ship's own belly tabs aft of x 6.95. Zone 1's approved language and density (detail_zone1.K); reference 1's underside
(crop_hull_bottom.png): heavy rust keel strakes, big bolted plates, machinery under the hull, heavy hoses and chains
hanging in long sags. The belly is seen from below when the ship flies over the players: the big shapes (the keel
girder and its pipe mains, the rust frames, the dark bays, the hanging chains and hoses) carry it at 25-40 m.

  blender_capped.sh --python detail_z5.py [-- --no-save] [--blend-out FILE] [--report FILE]

Opens rig/AirshipRig.blend READ ONLY, builds collection Detail_Z5 and saves rig/detail/zones/AirshipRig_detail_z5.blend
(detail_common.safe_save). The other zones' details (1, 2, 3, 4, 6, 7 when their files exist) are appended only to be
obstacles and are removed again before the save. Report: Docs/Airship/round3/z5_report.json.

Object (parent Armature, Armature modifier, every vertex 100 % on the Hull bone):
  SM_AirshipDetail_Z5_Belly   keel girder (dark backing + riveted rust strake), two pipe mains beside it (copper and
                              brass on a dark backing, flanges, clamps on the frames, a valve, glands), rust belly frames
                              every 2.4 m, four machinery bays, zone 1's plate rows and layers, corner rivets on the
                              ship's belly tabs, two heavy chains on padeyes under the keel, two heavy hoses between the
                              bays
Module: detail_z5_lib.py (belly chart + mask, zone 1's layering copied from zone 4's module). Shared modules are only
imported.
"""
import bpy, sys, os, math, random, json, time, copy
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from mathutils import Vector as V
from mathutils.bvhtree import BVHTree
import rig_common as C
import detail_common as D
import detail_ship as S
import detail_zones as Z
import detail_checks as CK
import detail_base_edits as BE
import detail_zone1 as Z1
from detail_flank import x_runs
from detail_z5_lib import (BellyChart, BellyMask, tile_rows, fill_gaps, layer_plates, bay, lift_fn, drop_intersecting,
                           ZONE1_STYLE, valve_body5)

ZONE = 'Z5'
DOCS = '/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/round3'
OTHER_ZONES = ('1', '2', '3', '4', '6', '7')

# ------------------------------------------------------------------ knobs: zone 1's (approved density) + the belly's
K = copy.deepcopy(Z1.K)
K.update(seed=1315)                                # seed search 2026-11-28: calm plate area 31 % / 36 %
K['z5'] = dict(
    chart_x=(-16.5, 7.1, 0.05), chart_psi=(-70.0, 70.0, 0.25), AZ=0.3, clear=0.30, dv=0.04, vmax=5.4,
    margin=0.12,                                   # free cells keep 12 cm from every other zone (seam rule 10 cm)
    other_r=0.17,                                  # ... and 17 cm in 3D from any face another zone owns (struts, tabs)
    rudder=dict(c=(-16.364, 0.0), r=1.05),         # rudder pivot; its forward 0.76 m swings +-30 deg under the stern
    girder=dict(back=0.40, strake=0.23, back_t=0.02, t=0.085, seg=2.25, joint=0.008, piece=3.0, min_len=3.0,
                rivet_in=0.06, back_rivet_step=0.56),
    channel=dict(v=(0.47, 0.97), pipes=((0.07, 0.15, 'copper'), (0.058, 0.38, 'brass')), min_len=2.5,
                 flange_step=4.0, clamp_step=1.2, back_t=0.015),
    ribs=dict(xs=(-14.0, -11.6, -9.2, -6.8, -4.4, -2.0, 0.4, 2.8, 5.2), w=0.16, t=0.10, min_len=0.5, gap=0.02),
    # machinery bays: (side, x0, W, v0, H, pump, tank)
    bays=[(1, -13.86, 1.70, 1.10, 1.16, True, True), (-1, -13.86, 1.70, 1.10, 1.16, True, False),
          (1, -3.86, 1.70, 1.10, 1.16, False, True), (-1, -3.86, 1.70, 1.10, 1.16, True, True)],
    # heavy hoses from the aft bay to the mid bay on each side: (side, x_a, x_b, v, sag)
    # review fix 2026-11-28: the hoses hung 0.55 m and read as thin dark necklaces under the hull line: thicker, with
    # a short sag (was r 7.5 cm, sag 0.55)
    hoses=[(1, -11.93, -4.07, 1.68, 0.26), (-1, -11.93, -4.07, 1.68, 0.26)],
    hose=dict(r=0.09, sides=12, band_step=0.75, fitting=0.26, rise=0.16),
    # heavy chains on padeyes on the keel strake: (x_a, x_b, sag). Review fix 2026-11-28: the two keel swags had no
    # load and no purpose and read as beaded necklaces from the side: dropped (was (-14.45, -9.25, 0.62),
    # (-1.35, 4.05, 0.62))
    chains=[],
    chain=dict(link=0.30, wire=0.032),
    # review fix 2026-11-28: the belly frames ended in the middle of the skin under raised rust plates ('signs on
    # posts' from the side). A riveted rust bilge stringer per side, as far out as it runs freely, takes the frame
    # ends; frames that cannot reach it end in a sniped knee (tapering 0.3 m end); no raised rust armour within
    # 0.5 m of a frame end
    stringer=dict(v=(2.2, 3.7), w=0.16, t=0.10, pad=0.02, min_len=2.0, x=(-14.3, 5.5), seg=2.4, joint=0.008),
    knee=dict(L=0.30, w_end=0.06, t=0.06, keep_armour_off=0.5),
    rows=dict(w=(0.8, 1.6), row_h=(0.7, 1.1), min_w=0.35, min_h=0.22, keep=0.25, mats=Z1.YELLOWS),
    style_slots=3,
    # look-and-fix pass (2026-11-28): the first build had 19-22 % calm plate area, 29 picture frames on 129 plates and
    # 11 raised armour plates (zone 1: 30 % calm, 3 frames on 49 plates, 2 armour). The belly's plates are bigger than
    # the flank's, so more of them qualify for a frame: lower the shares to land on zone 1's numbers.
    frame_p=0.4, patch_p=0.65, armour_p=0.3,
    bay_depth=0.095,                               # zone 1's 0.11: the belly curves away under a flat housing
    rows_v0=1.01,                                  # plate rows start at the outer edge of the pipe main
)


def opts():
    a = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    o = {}
    for i, k in enumerate(a):
        if k.startswith('--'):
            o[k[2:]] = a[i + 1] if i + 1 < len(a) and not a[i + 1].startswith('--') else True
    return o


# ================================================================== keel girder
def girder(mesh, ch, masks, K, rng, log):
    """dark backing (0.8 m) + riveted rust keel strake (0.46 m, top 12.6 cm off the skin) along the keel line, in
    segments one strake length long with 8 mm joints; reserves |v| < back + 4 cm in both halves"""
    G, R, PL = K['z5']['girder'], K['rivet'], K['plate']
    mp, ms = masks
    hb, hs = G['back'], G['strake']
    lim = hb + 0.04

    def ok(i):
        a = mp.free[i, :mp.iv(lim) + 1].all() and ms.free[i, :ms.iv(lim) + 1].all()
        return bool(a)
    runs = x_runs(ok, mp.xs, G['min_len'], join=0.11)
    out = []
    nr = 0
    for (x0, x1) in runs:
        x0 += 0.02; x1 -= 0.02
        L = x1 - x0
        for m in (mp, ms):
            m.take(x0 - 0.03, x1 + 0.03, 0.0, lim)

        def fb(xa):
            return lambda u, v: ch.surf(xa + u, v - hb)
        # dark backing in pieces
        n_b = max(1, int(math.ceil(L / G['piece'])))
        lb = (L - 0.006 * (n_b - 1)) / n_b
        for k in range(n_b):
            xa = x0 + k * (lb + 0.006)
            top, okp = D.solid_plate(mesh, fb(xa), D.grid_coords(0.0, lb, 0.5), D.grid_coords(0.0, 2 * hb, 0.2),
                                     PL['gap'], G['back_t'], 0.006, 'dark_metal', kind='girder')
            if okp:
                st = G['back_rivet_step']
                m_ = max(1, int(round((lb - 0.2) / st)))
                pts = []
                for i in range(m_ + 1):
                    u = 0.1 + (lb - 0.2) * i / m_
                    pts += [(u, (hb - hs) / 2), (u, 2 * hb - (hb - hs) / 2)]
                nr += D.rivet_row(mesh, top, pts, r=R['r'], h=R['h'])
        # rust strake segments
        n_s = max(1, int(round(L / G['seg'])))
        ls = (L - G['joint'] * (n_s - 1)) / n_s
        g2 = PL['gap'] + G['back_t'] + K['layer']
        for k in range(n_s):
            xa = x0 + k * (ls + G['joint'])
            f = lambda u, v, xa=xa: ch.surf(xa + u, v - hs)
            top, okp = D.solid_plate(mesh, f, D.grid_coords(0.0, ls, 0.5), D.grid_coords(0.0, 2 * hs, 0.23),
                                     g2, G['t'], 0.014, 'rust_red', kind='keel')
            if okp:
                m_ = max(1, int(round((ls - 0.2) / R['spacing'])))
                pts = []
                for i in range(m_ + 1):
                    u = 0.1 + (ls - 0.2) * i / m_
                    pts += [(u, G['rivet_in']), (u, 2 * hs - G['rivet_in'])]
                nr += D.rivet_row(mesh, top, pts, r=R['r'], h=R['h'])
        out.append((x0, x1))
    log['girder'] = dict(runs=[[round(a, 2), round(b, 2)] for a, b in out], rivets=nr,
                         top_off=round(PL['gap'] + G['back_t'] + K['layer'] + G['t'], 3))
    return out


# ================================================================== pipe mains beside the keel
def _surf_near(skin):
    def f(pt):
        r = skin.nearest(pt, 1.0)
        return None if r is None else (r[0], r[1])
    return f


def channel(mesh, M, skin, K, rng, log, rib_xs):
    """zone 1's pipe channel along the keel on one half: dark backing on the free run, two big pipes (copper r 7 cm,
    brass r 5.8 cm) with flanges, clamps on the belly frames, a valve, both ends diving into riveted glands"""
    CH, PL = K['z5']['channel'], K['plate']
    v0, v1 = CH['v']
    m0, m1 = M.iv(v0), M.iv(v1)
    ok = lambda i: bool(M.free[i, m0:m1 + 1].all() and not M.used[i, m0:m1 + 1].any())
    runs = x_runs(ok, M.xs, CH['min_len'], join=0.11)
    res = []
    for (a, b) in runs:
        a += 0.02; b -= 0.02
        M.take(a - 0.02, b + 0.02, v0 - 0.02, v1 + 0.02)
        L = b - a
        n_b = max(1, int(math.ceil(L / 3.0)))
        lb = (L - 0.006 * (n_b - 1)) / n_b
        for k in range(n_b):
            xa = a + k * (lb + 0.006)
            D.solid_plate(mesh, M.fn(xa, v0), D.grid_coords(0.0, lb, 0.5), D.grid_coords(0.0, v1 - v0, 0.25),
                          PL['gap'], CH['back_t'], 0.004, 'dark_metal', kind='channel')
        base_off = PL['gap'] + CH['back_t']
        n = 0
        for k, (rp, dv, mat) in enumerate(CH['pipes']):
            vv = v0 + dv
            off = base_off + 0.006 + rp
            us = np.linspace(a + 0.32, b - 0.32, max(4, int((b - a) / 0.35)))
            pts = []
            for u in us:
                q = M.at(u, vv)
                if q is None:
                    pts = None
                    break
                pts.append(q[0] + q[1] * off)
            q0, q1 = M.at(a + 0.14, vv), M.at(b - 0.14, vv)
            if not pts or q0 is None or q1 is None:
                continue
            path = [q0[0] - q0[1] * 0.02] + pts + [q1[0] - q1[1] * 0.02]
            # flanges every ~4 m, clamps on the belly frames that cross the channel's line, else every 1.2 m
            Lp = sum(np.linalg.norm(np.asarray(path[i + 1]) - path[i]) for i in range(len(path) - 1))
            nf = max(1, int(round(Lp / CH['flange_step'])))
            fl = [(i + 0.5) / nf for i in range(nf)]
            cl = [(xr - (a + 0.14)) / max(1e-6, (b - a - 0.28)) for xr in rib_xs if a + 0.5 < xr < b - 0.5]
            cl = sorted(set(round(c, 4) for c in cl))
            extra = []
            prev = 0.0
            for c in cl + [1.0]:
                gapc = (c - prev) * Lp
                k_ = int(gapc // CH['clamp_step'])
                for j in range(1, k_ + 1):
                    extra.append(prev + (c - prev) * j / (k_ + 1))
                prev = c
            cl_all = sorted([c for c in cl if 0.02 < c < 0.98] + [c for c in extra if 0.03 < c < 0.97])
            cl_all = [c for c in cl_all if all(abs(c - f_) * Lp > 0.18 for f_ in fl)]
            D.pipe_run(mesh, path, rp, 0.16, sides=12, mat=mat, flange_at=fl, flange_k=1.25, clamp_at=cl_all,
                       surf_fn=_surf_near(skin), kind='pipe')
            for q in (q0, q1):
                D.gland(mesh, q[0], q[1], M.world_dir_u(a, vv), rp, size=rp * 1.9, back=base_off)
            if k == 0 and len(pts) > 6:
                i = len(pts) // 3
                valve_body5(mesh, pts[i], D.unit(pts[i + 1] - pts[i - 1]), q0[1], rp * 0.88)
            n += 1
        res.append(dict(x=[round(a, 2), round(b, 2)], pipes=n))
    log.setdefault('channels', {})[M.name] = res
    return res


# ================================================================== belly frames
def stringer(mesh, M, K, log):
    """riveted rust bilge stringer along x at one v per half: the v (in K['z5']['stringer']['v']) where the free runs
    cross the most frame stations, then the longest, then the furthest out. Segments one strake length long with 8 mm
    joints. Returns [(x0, x1)], v"""
    ST, R, PL = K['z5']['stringer'], K['rivet'], K['plate']
    xs_r = K['z5']['ribs']['xs']
    best = None
    for v in np.arange(ST['v'][0], ST['v'][1] + 1e-9, 0.04):
        m0, m1 = M.iv(v - ST['pad']), M.iv(v + ST['w'] + ST['pad'])
        if m0 < 0 or m1 >= len(M.vs):
            continue
        ok = lambda i, m0=m0, m1=m1: bool((M.free[i, m0:m1 + 1] & ~M.used[i, m0:m1 + 1]).all())
        runs = x_runs(ok, M.xs, ST['min_len'], join=0.11)
        runs = [(max(a, ST['x'][0]), min(b, ST['x'][1])) for a, b in runs]
        runs = [(a, b) for a, b in runs if b - a >= ST['min_len']]
        nfr = sum(1 for xr in xs_r for a, b in runs if a + 0.15 < xr < b - 0.15)
        if nfr == 0:
            continue
        score = nfr * 100.0 + sum(b - a for a, b in runs) * 2.0 + v * 10.0
        if best is None or score > best[0]:
            best = (score, float(v), runs)
    out = dict(v=None, runs=[], segments=0, rivets=0)
    if best is None:
        log.setdefault('stringer', {})[M.name] = out
        return [], None
    _, v, runs = best
    nseg = nr = 0
    for (a, b) in runs:
        a += 0.02; b -= 0.02
        M.take(a - 0.03, b + 0.03, v - 0.03, v + ST['w'] + 0.03)
        L_ = b - a
        n_s = max(1, int(round(L_ / ST['seg'])))
        ls = (L_ - ST['joint'] * (n_s - 1)) / n_s
        for k in range(n_s):
            xa = a + k * (ls + ST['joint'])
            f = M.fn(xa, v)
            top, ok = D.solid_plate(mesh, f, D.grid_coords(0.0, ls, 0.4), np.array([0.0, ST['w']]), PL['gap'], ST['t'],
                                    0.014, 'rust_red', kind='stringer')
            if not ok:
                continue
            nseg += 1
            m_ = max(1, int(round((ls - 0.12) / R['spacing'])))
            nr += D.rivet_row(mesh, top, [(0.06 + (ls - 0.12) * i / m_, ST['w'] / 2) for i in range(m_ + 1)],
                              r=R['r'], h=R['h'])
    out.update(v=round(v, 2), runs=[[round(a, 2), round(b, 2)] for a, b in runs], segments=nseg, rivets=nr)
    log.setdefault('stringer', {})[M.name] = out
    return runs, v


def ribs(mesh, M, K, log, st_runs=(), st_v=None, frame_ends=None):
    """riveted rust belly frames across one half at fixed stations: from the edge of the keel strip (channel or
    girder) out to the end of the free skin; plates are tiled after them, so they end on the frames"""
    RB, R, PL = K['z5']['ribs'], K['rivet'], K['plate']
    hw = RB['w'] / 2
    out = []
    nr = 0
    for xr in RB['xs']:
        i0, i1 = M.ix(xr - hw - RB['gap']), M.ix(xr + hw + RB['gap'])
        if i0 < 0 or i1 >= len(M.xs):
            continue
        col_ok = (M.free[i0:i1 + 1] & ~M.used[i0:i1 + 1]).all(0)
        nv = len(M.vs)
        # first free run outside the keel strip that is long enough
        m, run = 0, None
        while m < nv:
            if M.vs[m] < 0.4 or not col_ok[m]:
                m += 1
                continue
            ma = m
            while m + 1 < nv and col_ok[m + 1]:
                m += 1
            if M.vs[m] - M.vs[ma] - 0.04 >= RB['min_len']:
                run = (ma, m)
                break
            m += 1
        if run is None:
            continue
        va, vb = M.vs[run[0]] + 0.02, M.vs[run[1]] - 0.02
        # ends on the bilge stringer when the stringer crosses this station right where the free run stops
        on_st = st_v is not None and any(a + 0.1 < xr < b - 0.1 for a, b in st_runs) and \
            abs((M.vs[run[1]] + M.dv) - (st_v - 0.03)) < 0.12
        if on_st:
            vb = st_v - 0.004
        M.take(xr - hw - RB['gap'], xr + hw + RB['gap'], va - 0.03, vb + 0.03)
        KN = K['z5']['knee']
        vf = vb if on_st else vb - KN['L']                 # the full-section frame; the sniped knee after it
        f = M.fn(xr - hw, va)
        top, ok = D.solid_plate(mesh, f, np.array([0.0, RB['w']]), D.grid_coords(0.0, vf - va, 0.3), PL['gap'], RB['t'],
                                0.014, 'rust_red', kind='rib')
        if not ok:
            continue
        k = max(1, int(round((vf - va - 0.12) / R['spacing'])))
        nr += D.rivet_row(mesh, top, [(RB['w'] / 2, 0.06 + (vf - va - 0.12) * i / k) for i in range(k + 1)],
                          r=R['r'], h=R['h'])
        if not on_st:
            # sniped knee: lower, tapering from the frame's width to w_end over KN['L'], one rivet; butts the frame
            we = KN['w_end']
            q = [(0.0, vf - va + 0.004), (RB['w'], vf - va + 0.004), (RB['w'] / 2 + we / 2, vb - va),
                 (RB['w'] / 2 - we / 2, vb - va)]
            tk, okk = D.solid_quad(mesh, f, q, PL['gap'], KN['t'], 0.012, 'rust_red', kind='rib', cell=0.2)
            if okk:
                r_ = f(RB['w'] / 2, vf - va + KN['L'] * 0.4)
                if r_ is not None:
                    D.rivet(mesh, r_[0] + r_[1] * (PL['gap'] + KN['t']), r_[1], r=R['r'], h=R['h'])
                    nr += 1
        if frame_ends is not None:
            frame_ends.append((M, xr, vb))
        out.append(dict(x=xr, v=[round(va, 2), round(vb, 2)], end='stringer' if on_st else 'knee'))
    log.setdefault('ribs', {})[M.name] = dict(ribs=out, rivets=nr)
    return out


# ================================================================== heavy hoses and chains
def hose_fitting(mesh, p, n, u_hint, r, size):
    """riveted square base plate with a brass collar and a flange where a heavy hose leaves the belly"""
    D.gland(mesh, p, n, u_hint, r, size=size, back=0.0)
    t = D.unit(n)
    D.flange(mesh, p + t * 0.05, t, r * 1.75, thick=0.03, sides=12, mat='brass', kind='hose', bolts=6, bolt_r=0.012)


def hose(mesh, A, nA, B, nB, sag, HS):
    """heavy hose: up out of a fitting along its normal, then a long sag under gravity (a parabola, world -z), back up
    into the other fitting; steel bands every ~0.75 m, brass ferrules at the ends"""
    r, rise = HS['r'], HS['rise']
    A1, B1 = A + nA * rise, B + nB * rise
    pts = [A + nA * 0.03, A + nA * 0.10, A1]
    k = 28
    for i in range(1, k):
        t = i / k
        pts.append(A1 + (B1 - A1) * t + np.array([0.0, 0.0, -1.0]) * sag * 4 * t * (1 - t))
    pts += [B1, B + nB * 0.10, B + nB * 0.03]
    P = D.fillet_path(pts, 0.18, seg=4, min_turn=6.0)
    D.tube(mesh, P, r, HS['sides'], 'dark_metal', 'hose', caps=True)
    Lc = np.concatenate([[0], np.cumsum([np.linalg.norm(P[i + 1] - P[i]) for i in range(len(P) - 1)])])

    def at(s):
        i = int(np.clip(np.searchsorted(Lc, s) - 1, 0, len(P) - 2))
        a = (s - Lc[i]) / max(Lc[i + 1] - Lc[i], 1e-9)
        return P[i] + (P[i + 1] - P[i]) * a, D.unit(P[i + 1] - P[i])
    for s in (0.10, Lc[-1] - 0.10):
        c, t = at(s)
        D.cylinder(mesh, c - t * 0.07, c + t * 0.07, r * 1.32, 12, 'brass', 'hose', smooth=False)
    nb = max(1, int((Lc[-1] - 0.6) / HS['band_step']))
    for j in range(1, nb):
        c, t = at(0.3 + (Lc[-1] - 0.6) * j / nb)
        D.cylinder(mesh, c - t * 0.025, c + t * 0.025, r + 0.012, 12, 'steel', 'hose', smooth=False)
    return P


def padeye(mesh, p, n, tdir, R):
    """riveted padeye on the keel strake: base plate, a lug along the keel with a thick ring through it. Returns the
    point the chain hangs from (bottom of the ring)"""
    n = D.unit(n)
    t = D.unit(tdir - n * np.dot(tdir, n))
    s = np.cross(n, t)
    D.chamfer_box(mesh, D.frame_matrix(p + n * 0.014, t, s, n), 0.16, 0.12, 0.012, 0.004, 'dark_metal', 'padeye')
    for a in (-1, 1):
        for b in (-1, 1):
            D.rivet(mesh, p + n * 0.026 + t * a * 0.12 + s * b * 0.08, n, r=R['r'], h=R['h'])
    D.chamfer_box(mesh, D.frame_matrix(p + n * (0.026 + 0.075), t, s, n), 0.09, 0.025, 0.075, 0.012, 'rust_red', 'padeye')
    # ring through the lug: a torus in the (t, n) plane round the axis s, 0.16 below the lug's foot
    c = p + n * (0.026 + 0.15)
    rr, wire = 0.085, 0.028
    loop = [c + rr * (math.cos(a) * t + math.sin(a) * n) for a in np.linspace(0, 2 * math.pi, 13)[:-1]]
    idx = []
    for q in range(12):
        tn = D.unit(loop[(q + 1) % 12] - loop[q - 1])
        rad = D.unit(np.cross(tn, s))
        b = mesh.verts(D.ring_pts(loop[q], s, rad, wire, 6))
        idx.append(list(range(b, b + 6)))
    for q in range(12):
        mesh.bridge(idx[q], idx[(q + 1) % 12], 'steel', True, 'padeye')
    return c + n * (rr + wire * 0.2)


def link_chain(m, pts, link=0.30, wire=0.032, mat='dark_metal', kind='chain'):
    """links along a polyline (D.chain's link: a 6 x 4 swept stadium loop, consecutive links turned 90 degrees); the
    same heavy chain as zone 7's (link 0.30, wire 3.2 cm)"""
    P = [np.asarray(p, float) for p in pts]
    Lc = np.concatenate([[0], np.cumsum([np.linalg.norm(P[i + 1] - P[i]) for i in range(len(P) - 1)])])
    step = link * 0.78
    k = int(Lc[-1] // step)
    EZ = np.array([0.0, 0.0, 1.0])
    side0 = D.unit(np.cross(D.unit(P[-1] - P[0]), EZ))
    for i in range(k):
        s = (i + 0.5) * step + (Lc[-1] - k * step) / 2
        j = int(np.clip(np.searchsorted(Lc, s) - 1, 0, len(P) - 2))
        c = P[j] + (P[j + 1] - P[j]) * ((s - Lc[j]) / max(Lc[j + 1] - Lc[j], 1e-9))
        t = D.unit(P[j + 1] - P[j])
        sd = D.unit(side0 - t * np.dot(side0, t))
        w = sd if i % 2 == 0 else D.unit(np.cross(t, sd))
        pn = D.unit(np.cross(t, w))
        hl, hr = link * 0.5 - wire, link * 0.28 - wire
        loop = [c + t * hl * math.cos(q * math.pi / 3) + w * hr * math.sin(q * math.pi / 3) for q in range(6)]
        idx = []
        for q in range(6):
            tn = D.unit(loop[(q + 1) % 6] - loop[q - 1])
            rad = D.unit(np.cross(tn, pn))
            b = m.verts(D.ring_pts(loop[q], pn, rad, wire, 4, math.pi / 4))
            idx.append(list(range(b, b + 4)))
        for q in range(6):
            m.bridge(idx[q], idx[(q + 1) % 6], mat, False, kind)
    return k


def chains(mesh, ch, K, log, girder_runs):
    """two heavy chains hanging in long sags under the keel between riveted padeyes on the strake"""
    G, CN, R = K['z5']['girder'], K['z5']['chain'], K['rivet']
    top_off = K['plate']['gap'] + G['back_t'] + K['layer'] + G['t']
    out = []
    for (xa, xb, sag) in K['z5']['chains']:
        if not any(a + 0.3 < xa < b - 0.3 and a + 0.3 < xb < b - 0.3 for a, b in girder_runs):
            out.append(dict(x=[xa, xb], built=False, why='not on the girder'))
            continue
        ends = []
        for x in (xa, xb):
            q = ch.surf(x, 0.0)
            ends.append(padeye(mesh, q[0] + q[1] * top_off, q[1], np.array([1.0, 0.0, 0.0]), R))
        a, b = ends
        k = 40
        pts = [a + (b - a) * (i / k) + np.array([0.0, 0.0, -1.0]) * sag * 4 * (i / k) * (1 - i / k) for i in range(k + 1)]
        nl = link_chain(mesh, pts, CN['link'], CN['wire'])
        out.append(dict(x=[xa, xb], sag=sag, links=nl, low_z=round(float(min(p[2] for p in pts)), 3), built=True))
    log['chains'] = out


def hoses(mesh, masks, skin, K, log):
    HS = K['z5']['hose']
    out = []
    for (side, xa, xb, v, sag) in K['z5']['hoses']:
        M = masks[0] if side > 0 else masks[1]
        ends = []
        for x in (xa, xb):
            q = M.at(x, v)
            if q is None:
                break
            ends.append(q)
        if len(ends) < 2:
            out.append(dict(side=side, built=False))
            continue
        (pa, na), (pb, nb_) = ends
        for (p, n_), x in zip(ends, (xa, xb)):
            hose_fitting(mesh, p, n_, M.world_dir_u(x, v), HS['r'], HS['fitting'])
        P = hose(mesh, pa + na * 0.0, na, pb, nb_, sag, HS)
        out.append(dict(side=side, x=[xa, xb], v=v, sag=sag, low_z=round(float(min(p[2] for p in P)), 3), built=True))
    log['hoses'] = out


def reserve_fittings(masks, K):
    HS = K['z5']['hose']
    s = HS['fitting'] / 2 + 0.05
    for (side, xa, xb, v, sag) in K['z5']['hoses']:
        M = masks[0] if side > 0 else masks[1]
        for x in (xa, xb):
            M.take(x - s, x + s, v - s, v + s)


# ================================================================== the ship's belly tabs (zone 5's own islands)
def tab_rivets(mesh, ship, K, log):
    """corner rivets on the outer face of each zone 5 belly tab (islands 394-411 with the centre aft of x 6.95), like
    zone 4's tabs"""
    R = K['rivet']
    me = ship.ob.data
    nP = len(me.polygons)
    nrm = np.empty(nP * 3); me.polygons.foreach_get('normal', nrm); nrm = nrm.reshape(-1, 3)
    cen = np.empty(nP * 3); me.polygons.foreach_get('center', cen); cen = cen.reshape(-1, 3)
    area = np.empty(nP); me.polygons.foreach_get('area', area)
    n = 0
    tabs = []
    for isl in range(393, 412):
        vm = ship.v_island == isl
        if not vm.any():
            continue
        cc = ship.co[vm].mean(0)
        if cc[0] > Z.X_FWD:
            continue
        fk = np.nonzero(ship.p_island == isl)[0]
        out_dir = lambda j: float(np.dot(nrm[j], D.unit(cen[j] - np.array([cen[j][0], 0.0, 0.3]))))
        big2 = sorted(fk, key=lambda j: -area[j])[:2]
        k = max(big2, key=out_dir)
        if area[k] < 0.25 or out_dir(k) < 0.3:
            continue
        P = ship.co[list(ship.polys[k])]
        N = nrm[k]
        c = P.mean(0)
        U, Vv, _ = D.ortho_frame(N, (1.0, 0.0, 0.0))
        u = (P - c) @ U; v = (P - c) @ Vv
        for su, sv in ((u.min(), v.min()), (u.max(), v.min()), (u.max(), v.max()), (u.min(), v.max())):
            inset = 0.08
            q = c + U * (su - np.sign(su) * inset) + Vv * (sv - np.sign(sv) * inset)
            D.rivet(mesh, q, N, r=R['r'], h=R['h'])
            n += 1
        tabs.append(int(isl))
    log['tab_rivets'] = dict(tabs=tabs, rivets=n)
    return n


# ================================================================== other zones (obstacles only, never saved here)
def other_zone_bvhs(arm):
    got, objs = [], []
    for z in OTHER_ZONES:
        c = D.append_zone(z, arm)
        if c is None:
            continue
        got.append('Z' + z)
        objs += [o for o in c.all_objects if o.type == 'MESH']
    if not objs:
        return None, got, []
    bvh, _, _ = D.bvh_from_objects(objs)
    return bvh, got, objs


def remove_appended(objs):
    colls = set()
    for o in objs:
        for c in o.users_collection:
            colls.add(c)
        me = o.data
        bpy.data.objects.remove(o)
        if me and me.users == 0:
            bpy.data.meshes.remove(me)
    for c in colls:
        if c.name.startswith('Detail_Z') and c.name != 'Detail_Z5':
            bpy.data.collections.remove(c)


# ================================================================== build
def build(ship, zi, deleted, K, log, zbvh):
    t0 = time.time()
    Z5 = K['z5']
    skin = ship.surface((ship.p_island == S.SKIN) & ~deleted)
    obst = ship.bvh((ship.p_island != S.SKIN) & ~deleted)
    ch = BellyChart(skin, obst, np.arange(Z5['chart_x'][0], Z5['chart_x'][1] + 1e-9, Z5['chart_x'][2]),
                    np.arange(Z5['chart_psi'][0], Z5['chart_psi'][1] + 1e-9, Z5['chart_psi'][2]), AZ=Z5['AZ'],
                    clear=Z5['clear'])
    rc, rr = Z5['rudder']['c'], Z5['rudder']['r']
    # free cells keep `other_r` (3D) from every face another zone owns: the skin seams (also kept by `margin`) and the
    # parts that stand on zone 5's skin, like the turbine struts' feet (Z6) and the hull islands next to the bow seam
    keep = lambda p: math.hypot(p[0] - rc[0], p[1] - rc[1]) > rr and not zi.near_other(p, ZONE, Z5['other_r'])
    vs = np.arange(0.0, Z5['vmax'] + 1e-9, Z5['dv'])
    mp = BellyMask(ch, zi, ch.xs, vs, margin=Z5['margin'], keep=keep, name='port', side=1)
    ms = BellyMask(ch, zi, ch.xs, vs, margin=Z5['margin'], keep=keep, name='stbd', side=-1)
    masks = (mp, ms)
    log['free_m2'] = dict(port=round(mp.area_free(), 1), stbd=round(ms.area_free(), 1))
    log['t_mask'] = round(time.time() - t0, 1)
    m = D.Mesh('belly'); m.cur_group = 'Hull'
    rng = random.Random(K['seed'])
    gr = girder(m, ch, masks, K, rng, log)
    rib_xs = Z5['ribs']['xs']
    for M in masks:
        channel(m, M, skin, K, rng, log, rib_xs)
    frame_ends = []
    for M in masks:
        st_runs, st_v = stringer(m, M, K, log)
        ribs(m, M, K, log, st_runs, st_v, frame_ends)
    reserve_fittings(masks, K)
    # machinery bays
    for (side, x0, W, v0, H, pump, tank) in Z5['bays']:
        M = mp if side > 0 else ms
        Hb = H
        while Hb >= 0.8 and not M.all_free(x0, x0 + W, v0, v0 + Hb, pad=0.02):
            Hb -= 0.04
        if Hb < 0.8:
            log.setdefault('bays_skipped', []).append([side, x0])
            continue
        M.take(x0 - 0.03, x0 + W + 0.03, v0 - 0.03, v0 + Hb + 0.03)
        bay(m, M, x0, v0, W, Hb, K, rng, log, rim=K['bay']['rim'], rim_t=K['bay']['rim_t'], depth=Z5['bay_depth'],
            pump=pump, tank=tank, tag='%s %.1f' % (M.name, x0))
    # plates and zone 1's layers
    style = dict(ZONE1_STYLE, slots=Z5['style_slots'], patch_p=Z5['patch_p'], armour_p=Z5['armour_p'],
                 no_armour_near=[(M_, x_, v_, Z5['knee']['keep_armour_off']) for (M_, x_, v_) in frame_ends])
    K['frame'] = dict(K['frame'], p=Z5['frame_p'])
    for M in masks:
        rows = tile_rows(M, rng, Z5['rows'], K, v_start=Z5['rows_v0'])
        fills = fill_gaps(M, rng, K['fill'], K)
        layer_plates(m, rows, fills, K, rng, log, style=style, tag=M.name)
    tab_rivets(m, ship, K, log)
    chains(m, ch, K, log, gr)
    hoses(m, masks, skin, K, log)
    log['t_build'] = round(time.time() - t0, 1)
    # pieces that cut into the ship's own parts (tabs, struts, pods at rest) or another zone's details go
    drops = {}
    d1 = drop_intersecting(m, [obst])
    if d1:
        drops['ship_parts'] = d1
    if zbvh is not None:
        d2 = drop_intersecting(m, [zbvh])
        if d2:
            drops['other_zones'] = d2
    log['dropped_intersecting'] = drops
    return {'Belly': (m, 'Hull')}, (ch, masks)


def kinds_summary(m):
    by = m.tris_by_kind()
    tot = max(1, sum(by.values()))
    return {k: dict(tris=v, share=round(v / tot, 3)) for k, v in sorted(by.items(), key=lambda kv: -kv[1])}


HANGING = ('chain', 'hose', 'padeye')


def main():
    o = opts()
    zn = '5'
    coll_name, prefix = 'Detail_Z5', 'SM_AirshipDetail_Z5_'
    report_path = o.get('report') or (DOCS + '/z5_report.json')
    out_blend = o.get('blend-out') or D.zone_blend(zn)
    if o.get('seed'):                                              # seed search only (the saved build uses K['seed'])
        K['seed'] = int(o['seed'])
    t0 = time.time()
    bpy.ops.wm.open_mainfile(filepath=C.RIG_BLEND)                 # read only: never saved under this name
    ship = S.Ship(bpy)
    mats = D.ensure_materials()
    zi = Z.ZoneIndex(ship)
    be_rep = {}
    deleted = BE.deleted_mask(ship, 'all', be_rep)
    zbvh, got, zobjs = other_zone_bvhs(ship.arm)
    log = dict(other_zones_as_obstacles=got)
    parts, _ = build(ship, zi, deleted, K, log, zbvh)
    remove_appended(zobjs)
    ship_bvh = ship.bvh(~deleted)
    dropped, flipped = {}, {}
    for name, (m, _) in parts.items():
        for _ in range(3):
            dd = D.drop_floating(m, [ship_bvh], tol=K['touch_tol'])
            if not dd:
                break
            for k_, v_ in dd.items():
                dropped.setdefault(name, {})[k_] = dropped.get(name, {}).get(k_, 0) + v_
        flipped[name] = m.orient_outward()
    log['floating_pieces_removed'] = dropped
    log['inside_out_pieces_flipped'] = flipped
    kinds = {name: kinds_summary(m) for name, (m, _) in parts.items()}
    # vertex kinds (for the silhouette split: hanging chains / hoses are allowed below the 20 cm rule)
    vk = {name: CK.vertex_kinds(m) for name, (m, _) in parts.items()}
    coll = bpy.data.collections.get(coll_name) or bpy.data.collections.new(coll_name)
    if coll.name not in [c.name for c in bpy.context.scene.collection.children]:
        bpy.context.scene.collection.children.link(coll)
    objs = []
    for name, (m, bone) in parts.items():
        if not m.f:
            continue
        objs.append(m.to_object(prefix + name, coll, mats, arm=ship.arm, groups=bone if bone else list(m.g)))
    # ---- checks
    zc = CK.zone_checks(objs, ZONE, ship, zi, sample=2) if objs else None
    m = parts['Belly'][0]
    co = np.array(m.v)
    kk = np.array(vk['Belly'])
    hang = np.isin(kk, HANGING)
    ship_surf = ship.surface(np.ones(len(ship.polys), bool))
    sil = dict(fixed=CK.dist_report(co[~hang], ship_surf, 'belly details except the hanging chains and hoses', 0.20,
                                    vkind=list(kk[~hang])),
               hanging=CK.dist_report(co[hang], ship_surf, 'hanging chains, hoses, padeyes', 0.20, vkind=list(kk[hang])),
               lowest_z=round(float(co[:, 2].min()), 3),
               lowest_nozzle_petal_z=round(float(ship.co[np.char.find(ship.v_bone.astype(str), 'Petal') >= 0][:, 2].min()), 3))
    tris = {ob.name: int(sum(len(p.vertices) - 2 for p in ob.data.polygons)) for ob in objs}
    # every vertex within the seam margin of another zone, by kind and where (the checklist lists them in the doc)
    near = {}
    for i in range(len(co)):
        for oz in zi.near_other(co[i], ZONE):
            e = near.setdefault(oz, {})
            k_ = str(kk[i])
            if k_ not in e:
                e[k_] = dict(verts=0, x=[999.0, -999.0])
            e[k_]['verts'] += 1
            e[k_]['x'] = [round(min(e[k_]['x'][0], float(co[i][0])), 2), round(max(e[k_]['x'][1], float(co[i][0])), 2)]
    # density against zone 1 (ZONES.md checklist 11)
    zsum = zi.summary()
    area_z5 = zsum['Z5']['area_m2']
    free = log['free_m2']['port'] + log['free_m2']['stbd']
    tk = kinds['Belly']
    t_all = sum(v['tris'] for v in tk.values())
    t_hang = sum(tk.get(k_, {}).get('tris', 0) for k_ in HANGING)
    lay = log.get('layers', {})
    pa_ = sum(v['plate_area_m2'] for v in lay.values())
    density = dict(
        z5_faces_m2=area_z5, z5_free_skin_m2=round(free, 1),
        tris_per_m2_of_z5_faces=round(t_all / area_z5, 1),
        tris_per_m2_of_free_skin=round(t_all / free, 1),
        tris_per_m2_of_free_skin_without_hanging=round((t_all - t_hang) / free, 1),
        rivet_share=round(tk.get('rivet', {}).get('tris', 0) / t_all, 3),
        calm_share_of_plate_area=round(sum(v['calm_share_of_area'] * v['plate_area_m2'] for v in lay.values()) / max(pa_, 1e-6), 2),
        armour_plates=sum(v['armour'] for v in lay.values()), plates=sum(v['plates'] for v in lay.values()),
        zone1=dict(hull_tris_per_m2_of_faces=128.3, free_skin_tris_per_m2=611, rivet_share=0.241, calm_share=0.30,
                   armour_plates='2 of 49', source='z2_report.json density, ZONE_2.md section 3, zone1_report.json'),
        about='Z5 faces are nearly all free skin; zone 1 face area includes the ship\'s own bands, steam pipes and '
              'pocket, so compare the free-skin numbers')
    rep = dict(zone=ZONE, knobs=K, log=log, base_edits=be_rep, tris=tris, tris_total=sum(tris.values()),
               tris_by_kind=kinds, objects=[CK.object_report(ob, ZONE) for ob in objs], zone_checks=zc,
               silhouette=sil, seam_margin_detail=near, density=density, seconds=round(time.time() - t0, 1))
    rep['all_objects_ok'] = all(r['ok'] for r in rep['objects'])
    C.dump_json(rep, report_path)
    print('[Z5] tris', tris, 'total', rep['tris_total'])
    print('[Z5] objects ok', rep['all_objects_ok'], json.dumps([{k: r[k] for k in ('object', 'ok', 'pieces', 'inside_out_pieces',
          'nonmanifold_edges', 'not_rigid_vertices', 'faces_without_role')} for r in rep['objects']]))
    print('[Z5] kinds', json.dumps({k: v['tris'] for k, v in kinds['Belly'].items()}))
    print('[Z5] zone checks', json.dumps(zc)[:2000])
    print('[Z5] silhouette', json.dumps(sil))
    print('[Z5] seam margin', json.dumps(near))
    print('[Z5] density', json.dumps(density))
    print('[Z5] log', json.dumps({k: v for k, v in log.items() if k not in ('bays',)})[:4000])
    print('[Z5] report', report_path)
    if not o.get('no-save'):
        print('[Z5] saved', D.safe_save(out_blend))
    print('[Z5] done %.1f s' % (time.time() - t0))
    sys.stdout.flush()


if __name__ == '__main__':
    main()
