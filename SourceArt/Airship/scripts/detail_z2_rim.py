"""Zone 2 helper: the riveted rim strap round the FR pocket opening.

A copy of detail_pod.pocket_rim (zone 1's code, unchanged there) with four changes, because on the starboard hull the
shared version made a wavy top strap and broken pieces past the fore edge (ZONE_2.md):
  1. the edge lines are fitted robustly (outliers out, like the strake line), so a few stray edge cells no longer bend
     the cubic out to x 7.9 (forward of the zone, into Z4)
  2. each strap is smoothed in 3D (its centre line and its across direction, moving average over +-0.3 m) and laid
     back on the skin by nearest point: the chart's arc length jumps a few cm from column to column there (the deck
     edge it is measured from is not straight), which made a long strap wobble
  3. a strap sample must lie in zone 2 (detail_zones: the FR pocket / rim band or the Z2 flank) and on smooth skin
     (no normal jump over 25 degrees and no gap to the next sample): no pieces on the belly, forward of the zone, or
     wrapped over the jagged lower corner of the opening
  4. pieces shorter than K['rim2']['min_len'] (0.6 m) are left out (short bits read as debris)
Everything else (where the edges are, strap width, thickness, rivets, the chart points the plates keep off) is zone 1's.
"""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from mathutils import Vector as V
import detail_common as D
import detail_zones as Z

RIM2 = dict(min_len=0.6, smooth=0.3, max_turn=25.0, fit_tol=0.03)


def robust_line(pts, key, tol=0.03):
    """pts (n, 2) of (x, s); key 0: s as a function of x (top edge), key 1: x as a function of s (side edges).
    Cubic (linear when short) fitted with outliers removed; sampled every 5 cm inside the kept data range only."""
    pts = np.array(sorted(pts, key=lambda q: q[key]))
    if len(pts) < 8:
        return None
    t, y = pts[:, key], pts[:, 1 - key]
    deg = 3 if (t[-1] - t[0]) > 1.5 else 1
    keep = np.ones(len(t), bool)
    for _ in range(5):
        c = np.polyfit(t[keep], y[keep], deg)
        res = np.abs(np.polyval(c, t) - y)
        keep = res < max(tol, np.percentile(res, 75))
        if keep.sum() < 8:
            return None
    tk = t[keep]
    tt = np.linspace(tk[0], tk[-1], max(8, int((tk[-1] - tk[0]) / 0.05)))
    out = np.zeros((len(tt), 2))
    out[:, key] = tt
    out[:, 1 - key] = np.polyval(c, tt)
    return out


def pocket_rim_z2(mesh, fl, ship, K, rng, log, pod='FR', zone='Z2', zi=None):
    O, T0, A, NP = ship.pod_frame(pod)
    ch = fl.chart
    R = K['pocket']['r']
    R2 = dict(RIM2, **K.get('rim2', {}))
    cx0, cx1 = K['pocket'].get('cols') or (O[0] - 4.33, O[0] + 5.67)
    RV = K['rivet']
    nx, nph = ch.hit.shape
    wall = np.zeros((nx, nph), bool)
    outer = np.zeros((nx, nph), bool)
    cols = [i for i in range(nx) if cx0 <= ch.xs[i] <= cx1]
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
            elif fl.side * ch.N[i, j][1] > 0.2 and (d > R - 0.02 or h < K['pocket']['roof_h'] + 0.02):
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
    vm = (rw0 + rw1) / 2
    log['rim_edge_points'] = dict(top=len(top), aft=len(aft), fore=len(fore))
    pod_bvh = ship.bvh(np.char.startswith(ship.p_bone.astype(str), 'Thruster_' + pod))
    skin = fl.skin
    why = {}

    def pod_far(q, d=0.2):
        if q is None:
            return False
        return pod_bvh.find_nearest(V(q[0]), d)[0] is None

    def mine(p):
        po, _ = Z.pocket_owner(p)
        if po == zone:
            return True
        return zi is not None and zi.zone_at(p) == zone

    def smooth(a, k):
        a = np.asarray(a, float)
        out = np.empty_like(a)
        for i in range(len(a)):
            out[i] = a[max(0, i - k):i + k + 1].mean(0)
        return out

    def strap(f, L, name):
        step = 0.08
        us_all = np.arange(0.0, L + 1e-9, step)
        q0 = [f(u, rw0) for u in us_all]
        q1 = [f(u, rw1) for u in us_all]
        qm = [f(u, vm) for u in us_all]
        okm = []
        for m_, u in enumerate(us_all):
            ok = (q0[m_] is not None and q1[m_] is not None and qm[m_] is not None and
                  fl.chart.free_at(*f.xs(u, rw0 + 0.02), 0.0) and fl.chart.free_at(*f.xs(u, rw1 - 0.02), 0.0) and
                  pod_far(q0[m_]) and pod_far(q1[m_]))
            if ok and not (mine(q0[m_][0]) and mine(q1[m_][0])):
                why['not_in_zone'] = why.get('not_in_zone', 0) + 1
                ok = False
            okm.append(ok)
        # smooth skin: no normal jump and no gap between neighbouring samples
        for m_ in range(1, len(us_all)):
            if okm[m_] and okm[m_ - 1]:
                ang = math.degrees(math.acos(float(np.clip(qm[m_][1] @ qm[m_ - 1][1], -1, 1))))
                gap = float(np.linalg.norm(qm[m_][0] - qm[m_ - 1][0]))
                if ang > R2['max_turn'] or gap > 2.5 * step:
                    why['skin_break'] = why.get('skin_break', 0) + 1
                    okm[m_] = False
        n = 0
        m = 0
        while m < len(us_all):
            if not okm[m]:
                m += 1
                continue
            e = m
            while e + 1 < len(us_all) and okm[e + 1]:
                e += 1
            if (e - m) * step < R2['min_len']:
                why['too_short'] = why.get('too_short', 0) + 1
                m = e + 1
                continue
            # 3D-smoothed centre line and across direction, laid back on the skin by nearest point
            kk = max(1, int(round(R2['smooth'] / step)))
            C_ = smooth([qm[i][0] for i in range(m, e + 1)], kk)
            T_ = smooth([D.unit(q1[i][0] - q0[i][0]) for i in range(m, e + 1)], kk)
            T_ = np.array([D.unit(t_) for t_ in T_])
            cum = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(C_, axis=0), axis=1))])
            Lr = float(cum[-1])

            def g(u, v, C_=C_, T_=T_, cum=cum):
                c = np.array([np.interp(u, cum, C_[:, a]) for a in range(3)])
                t_ = D.unit(np.array([np.interp(u, cum, T_[:, a]) for a in range(3)]))
                r = skin.nearest(c + t_ * (v - vm), 0.5)
                return None if r is None else (r[0], r[1])
            top_fn, ok = D.solid_plate(mesh, g, D.grid_coords(0, Lr, 0.16), np.array([rw0, rw1]), 0.012,
                                       K['pocket']['rim_t'], 0.014, 'rust_red', kind='rim')
            if ok:
                n += 1
                kb = max(1, int(Lr / RV['spacing']))
                D.rivet_row(mesh, top_fn, [(Lr * (i + 0.5) / kb, vm) for i in range(kb)], r=RV['r'], h=RV['h'])
                for u in np.arange(us_all[m], us_all[e] + 1e-9, 0.04):
                    for vv in np.linspace(0.0, rw1 + 0.03, 5):
                        rim_pts.append(f.xs(u, vv))
            m = e + 1
        return n

    nrim = 0
    st = robust_line(top, 0, R2['fit_tol'])
    if st is not None:
        x0, x1 = st[0, 0], st[-1, 0]

        def ft(u, v):
            x = x0 + u
            return ch.surf(x, float(np.interp(x, st[:, 0], st[:, 1])) - v)
        ft.xs = lambda u, v: (x0 + u, float(np.interp(x0 + u, st[:, 0], st[:, 1])) - v)
        nrim += strap(ft, x1 - x0, 'top')
    for pts, sgn, name in ((aft, -1.0, 'aft'), (fore, 1.0, 'fore')):
        sl = robust_line(pts, 1, R2['fit_tol'])
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
    log['rim_samples_left_out'] = why
    return rim_pts
