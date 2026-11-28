"""Thruster pod, pod pocket rim and cavity details (round 3), shared by the zones that own a pod.

Moved here from detail_zone1.py on 2026-11-28 (zone 1's geometry proven identical after the move). Every function takes
the pod id ('FL', 'FR', 'RL', 'RR'); default 'FL' = zone 1. The four pods are the same model: the starboard pods FR / RR
are mirror images (plate and side-box angles negated), so the angle basis is mirrored with the side (e90 -> side * e90)
and the same angle constants land on the mirrored places. Island ids come from the research classifier per pod
(pod_islands()). Pod-specific angle constants are knobs in K['pod'] (zone 1's values are the defaults).

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
from detail_flank import wchoice
from detail_checks import pod_frame_coords


def pod_side(pod):
    """+1 for the port pods (FL, RL), -1 for the starboard pods (FR, RR)"""
    return -1 if pod in ('FR', 'RR') else 1


def pod_islands(ship, pod):
    """research island ids of one pod: the three big plates (12 vertices each, checked) and the two side boxes, sorted
    by id. FL: plates (720, 721, 727), boxes (733, 739); FR = FL + 78, RL = FL + 156, RR = FL + 234 (same order, the
    starboard ones mirrored)"""
    part = 'Pod_' + pod
    plates = sorted(i for i, r in ship.islands.items() if r['part'] == part and r.get('piece') == 'plate')
    boxes = sorted(i for i, r in ship.islands.items() if r['part'] == part and r.get('piece') == 'side_box')
    assert len(plates) == 3 and len(boxes) == 2, (pod, plates, boxes)
    for i in plates:
        assert int((ship.v_island == i).sum()) == 12, (pod, i, int((ship.v_island == i).sum()))
    return plates, boxes


def pod_basis_mirrored(A, pod):
    """(e0, e90 for angles, e90 for full rings): angles are mirrored on the starboard pods, so one set of angle
    constants lands on the mirrored places; full rings keep the unmirrored basis (their winding stays outward)"""
    e0, e90 = S.pod_basis(A)
    return e0, (-e90 if pod_side(pod) < 0 else e90), e90


# ================================================================== FL pocket (hull bone): rim strap and cavity
def pocket_rim(mesh, fl, ship, K, rng, log, pod='FL'):
    """riveted strap round the pod's pocket opening on the outer skin: the top edge (where the pocket roof meets the
    flank) and the aft / fore edges (where the pocket cylinder meets it), found in the chart as outer-skin cells
    next to pocket-wall cells. Returns chart points over the strap (plates keep off them)."""
    O, T0, A, NP = ship.pod_frame(pod)
    ch = fl.chart
    R = K['pocket']['r']
    cx0, cx1 = K['pocket'].get('cols') or (O[0] - 4.33, O[0] + 5.67)      # zone 1 passes (-0.5, 9.5)
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
    log['rim_edge_points'] = dict(top=len(top), aft=len(aft), fore=len(fore))
    pod_bvh = ship.bvh(np.char.startswith(ship.p_bone.astype(str), 'Thruster_' + pod))

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


def cavity(hull, ship, fl, K, rng, log, pod='FL'):
    """pod pocket cavity above the pod, kept simple (the pod top and the steam pipe hide most of it): vertical wall
    stiffeners and one ring rib along the lower edge of the cavity wall, where it shows through the opening"""
    O, T0, A, NP = ship.pod_frame(pod)
    e0, e90, _ = pod_basis_mirrored(A, pod)
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


def build_pod(pod, noz, pet, ship, K, rng, log, skin=None, which='FL'):
    """pod (bone Thruster_<which>), nozzle (Thruster_<which>_Nozzle) and petal (Thruster_<which>_PetalNN) details
    into the three Mesh builders pod, noz, pet"""
    O, T0, A, NP = ship.pod_frame(which)
    PL3, BOX2 = pod_islands(ship, which)
    hc0 = HullClear(skin) if skin is not None else (lambda p, m: True)

    def hc_ok(p, m):
        # the pod tilts +-3 deg about its origin: a point L metres from it moves up to L sin(3 deg)
        L = np.linalg.norm(np.asarray(p) - O)
        return hc0(p, m + L * math.sin(math.radians(3.0)))
    CLR = K['pod']['hull_clear']
    e0, e90, e90r = pod_basis_mirrored(A, which)
    PK = K['pod']
    RV = K['rivet']
    blk_mask = np.isin(ship.p_island, [i for i, r in ship.islands.items() if r['part'] == 'Pod_' + which and r['piece'] != 'drum'])
    blk = ship.bvh(blk_mask)
    plates_surf = ship.surface(np.isin(ship.p_island, PL3))
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
    bands = PK.get('bands', [(-1.52, -1.12), (-0.21, 0.26), (0.44, 0.91), (1.09, 1.56)])
    jg0, jg1 = PK.get('junction_gap', (-13.0, 5.0))      # no drum plate where the junction housing (g) sits
    nplates = 0
    nr = 0
    for (h0, h1) in bands:
        th = -178.0
        while th < 178.0:
            span = rng.uniform(28.0, 50.0)
            th1 = min(th + span, 178.0)
            if h0 < 0.0 < h1 and th1 > jg0 and th < jg1:        # the junction housing (g) sits here
                if th < jg0:
                    th1 = jg0
                else:
                    th = jg1
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
        rings.append(D.ring_pts(T0 + A * h, e0, e90r, r, k))
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
    FAC = {isl: plate_facets(isl) for isl in PL3}
    # (plate, facet, u0, u1, v0, v1 as fractions of the facet; material, thickness, rivets 'row' | 'corners' | 'strap')
    # plate ids by role: P0 = outboard (FL 720, at 90 deg), P1 = front-outboard (721, 36 deg), P2 = front (727, 0 deg)
    P0, P1, P2 = PL3
    BIG = [(P1, 0, 0.03, 0.97, 'lip'), (P1, 1, 0.03, 0.97, 'lip'), (P2, 0, 0.03, 0.97, 'lip'),
           (P2, 1, 0.03, 0.97, 'lip'),
           (P0, 0, 0.18, 0.78, (0.12, 0.42)), (P2, 0, 0.2, 0.85, (0.3, 0.62)), (P1, 1, 0.12, 0.7, (0.08, 0.5)),
           (P0, 0, 0.96, 1.0, 'strap'), (P0, 1, 0.0, 0.04, 'strap'), (P2, 0, 0.965, 1.0, 'strap'),
           (P2, 1, 0.0, 0.035, 'strap')]
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
    for bid in BOX2:
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
    for k_, th in enumerate(PK.get('bundle_th', (-38.0, -46.0, -54.0))):
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
        p0, d0 = S.cyl_point(T0, A, e0, e90, hc, PK.get('bundle_bar_th', (-62.0, -30.0))[0], 1.95 + 0.012 + 2 * rp + 0.014)
        p1, d1 = S.cyl_point(T0, A, e0, e90, hc, PK.get('bundle_bar_th', (-62.0, -30.0))[1], 1.95 + 0.012 + 2 * rp + 0.014)
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
        for th in np.arange(PK.get('hug_th', (-76.0, 70.0))[0], PK.get('hug_th', (-76.0, 70.0))[1], 4.0):
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
        vis = [r_ for r_ in runs_ if np.mean(r_) > PK.get('hug_vis_min', -20.0) and len(r_) >= 6]
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
    for th in PK.get('act_th', (32.0, 46.0)):
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
    jt = PK.get('junction_th', -4.0)
    p, d = S.cyl_point(T0, A, e0, e90, 0.02, jt, RD)
    tang = np.cross(A, d)
    D.housing(pod, p - d * 0.012, d, tang, 0.42, 0.3, 0.09)
    tsg = tang if pod_side(which) > 0 else -tang      # mirrored pods: the conduit leaves from the mirrored side
    q0 = p + d * 0.06 + tsg * (-0.27)
    pts = [q0] + [S.cyl_point(T0, A, e0, e90, 0.02 + 0.05 * k_, jt - 8.0 * (k_ + 1), RD + 0.07)[0] for k_ in range(3)]
    pts.append(S.cyl_point(T0, A, e0, e90, 0.2, jt - 32.0, RD + 0.02)[0])
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
            rings.append(D.ring_pts(T0 + A * h, e0, e90r, shell_r(h) + dr, kq))
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
        isl = [i for i, r in ship.islands.items() if r['part'] == 'Nozzle_' + which and r.get('piece') == 'petal' and r.get('index') == k_]
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
        pet.cur_group = 'Thruster_%s_Petal%02d' % (which, k_)
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
