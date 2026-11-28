"""Zone 4 (bow) helpers for the round 3 detail pass: plate masks on flat or lumpy faces (Panel), zone 1's plate
layering as a reusable function (layer_plates), edge angles over creases, bolted blocks, straps, machinery bays.

Zone 4's own module (detail_z4.py imports it). Nothing here edits a shared module: the plate tiling (tile_rows,
fill_gaps) and the skin-step test (on_step) are imported from detail_flank unchanged; the layering below is a copy of
the 'plates and their layers' part of detail_flank.build_flank with the colours passed in (a style dict), so the same
approved language works on the rust bow wedge and the grey keel block.
"""
import math
import numpy as np
from mathutils import Vector as V
from mathutils.bvhtree import BVHTree
import detail_common as D
from detail_flank import wchoice, on_step, overlaps


# ================================================================== masks on faces
class Panel:
    """Free area of one face (or face group) of the ship in plane coordinates (u along U, v down the face along Vd),
    the same interface as detail_flank.RowMask (xs, vs, dx, dv, free, used, maxrect, take, fn), so detail_flank's
    tile_rows / fill_gaps tile it. A cell is free when a ray along -N hits the target faces there (normal within ntol
    of N), no other geometry lies within `clear` in front of it, keep(point) holds and (inside: a BVH of a closed
    shell) the point is not enclosed by that shell. lumpy=True: plates are built
    on a quadratic fit of their own patch, lifted so every sample of the real surface stays under the plate
    (fn_patch); a patch whose surface departs from the fit by more than max_res is refused."""

    def __init__(self, name, o, U, Vd, N, Lu, Lv, target, obst, clear=0.25, du=0.05, dv=0.04, ntol=20.0, erode=1,
                 keep=None, lumpy=False, max_res=0.06, rb=0.8, flat=True, inside=None):
        self.name = name
        self.o, self.U, self.Vd, self.N = D.vec(o), D.unit(U), D.unit(Vd), D.unit(N)
        self.Lu, self.Lv = float(Lu), float(Lv)
        self.target, self.obst = target, list(obst)
        self.lumpy, self.max_res, self.rb, self.flat = lumpy, max_res, rb, flat
        self.xs = np.arange(0.0, self.Lu + 1e-9, du)
        self.vs = np.arange(0.0, self.Lv + 1e-9, dv)
        self.dx, self.dv = du, dv
        nx, nv = len(self.xs), len(self.vs)
        F = np.zeros((nx, nv), bool)
        cos_t = math.cos(math.radians(ntol))
        self.hits = 0
        for i, u in enumerate(self.xs):
            for m, v in enumerate(self.vs):
                p0 = self.o + self.U * u + self.Vd * v + self.N * rb
                r = target.ray(p0, -self.N, rb + 1.2)
                if r is None:
                    continue
                n_ = r[4] if flat else r[1]
                if np.dot(n_, self.N) < cos_t:
                    continue
                d = r[3]
                bad = False
                for b in self.obst:
                    loc, _, _, do = b.ray_cast(V(p0), V(-self.N), d + 0.005)
                    if loc is not None and do < d - 1e-4 and d - do < clear:
                        bad = True
                        break
                    q = b.find_nearest(V(r[0]), 0.03)        # something touching the surface right there
                    if q[0] is not None:
                        bad = True
                        break
                if bad:
                    continue
                if keep is not None and not keep(r[0]):
                    continue
                if inside is not None:                    # enclosed by the hull skin (a face inside the hull volume)
                    loc, nn, _, _ = inside.ray_cast(V(r[0] + self.N * 0.01), V(self.N), 60.0)
                    if loc is not None and np.dot(np.array(nn), self.N) > 0:
                        continue
                F[i, m] = True
                self.hits += 1
        E = F.copy()
        for _ in range(erode):
            G = E.copy()
            G[1:] &= E[:-1]; G[:-1] &= E[1:]; G[:, 1:] &= E[:, :-1]; G[:, :-1] &= E[:, 1:]
            E = G
        self.free = E
        self.used = np.zeros_like(E)

    # ---- RowMask interface
    def ix(self, x):
        return int(round((x - self.xs[0]) / self.dx))

    def iv(self, v):
        return int(round(v / self.dv))

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
        self.used[i0:i1 + 1, m0:m1 + 1] = True

    def all_free(self, x0, x1, v0, v1):
        i0, i1 = max(0, self.ix(x0)), min(len(self.xs) - 1, self.ix(x1))
        m0, m1 = max(0, self.iv(v0)), min(len(self.vs) - 1, self.iv(v1))
        if i1 < i0 or m1 < m0 or x0 < self.xs[0] - 1e-6 or v0 < -1e-6 or x1 > self.xs[-1] + self.dx or v1 > self.vs[-1] + self.dv:
            return False
        return bool((self.free & ~self.used)[i0:i1 + 1, m0:m1 + 1].all())

    def area_free(self):
        return float(self.free.sum() * self.dx * self.dv)

    # ---- surface functions
    def at(self, u, v):
        p0 = self.o + self.U * u + self.Vd * v + self.N * self.rb
        r = self.target.ray(p0, -self.N, self.rb + 1.2)
        if r is None:
            return None
        n_ = r[4] if self.flat else r[1]
        if np.dot(n_, self.N) < 0:
            n_ = -n_
        return r[0], D.unit(n_)

    def fn(self, x0, v0):
        def f(u, v):
            return self.at(x0 + u, v0 + v)
        return f

    def world(self, u, v):
        return self.o + self.U * u + self.Vd * v

    def fn_patch(self, x0, v0, W, H, nu=7, nv=6):
        """smooth surface function over the patch [0, W] x [0, H] (from (x0, v0)): a quadratic fit of the ray distance,
        lifted so the real surface stays under it everywhere sampled; None when the residual exceeds max_res"""
        us, vs = np.linspace(0.0, W, max(3, nu)), np.linspace(0.0, H, max(3, nv))
        A, T = [], []
        for u in us:
            for v in vs:
                p0 = self.o + self.U * (x0 + u) + self.Vd * (v0 + v) + self.N * self.rb
                r = self.target.ray(p0, -self.N, self.rb + 1.2)
                if r is None:
                    return None
                A.append((1.0, u, v, u * u, u * v, v * v)); T.append(r[3])
        A = np.array(A); T = np.array(T)
        c, *_ = np.linalg.lstsq(A, T, rcond=None)
        res = A @ c - T                     # > 0: the real surface is nearer the plane (above the fit)
        if res.max() - res.min() > self.max_res:
            return None
        lift = float(res.max())
        U, Vd, N, o, rb = self.U, self.Vd, self.N, self.o, self.rb

        def f(u, v):
            t = c[0] + c[1] * u + c[2] * v + c[3] * u * u + c[4] * u * v + c[5] * v * v - lift
            dtu = c[1] + 2 * c[3] * u + c[4] * v
            dtv = c[2] + c[4] * u + 2 * c[5] * v
            p = o + U * (x0 + u) + Vd * (v0 + v) + N * (rb - t)
            su, sv = U - N * dtu, Vd - N * dtv
            n = D.unit(np.cross(su, sv))
            if np.dot(n, N) < 0:
                n = -n
            return p, n
        f.res = float(res.max() - res.min())
        return f


def surf_of(M, x0, v0, W, H):
    """surface function for a rectangle of a mask: a fitted patch on lumpy panels, the plain one elsewhere"""
    if getattr(M, 'lumpy', False):
        return M.fn_patch(x0, v0, W, H)
    return M.fn(x0, v0)


def lift_fn(f, d):
    """surface function moved out by d along its normal"""
    def g(u, v):
        r = f(u, v)
        return None if r is None else (r[0] + r[1] * d, r[1])
    return g


# ================================================================== plates and their layers (zone 1's language)
ZONE1_STYLE = dict(
    armour='rust_red', armour_p=0.5, batten='rust_red', frames=True,
    frame_mat=lambda m: 'paint_ochre' if m == 'paint_yellow' else 'paint_yellow',
    patch_mats=lambda m: (('rust_red', 0.7), ('paint_ochre', 0.3)),
    slots=3)


def build_plate4(mesh, p, K, gap, t, bevel, log):
    """detail_flank.build_plate for any mask (lumpy panels use a fitted patch); returns top_fn or None"""
    M = p['M']
    if getattr(M, 'lumpy', False):
        f = M.fn_patch(p['x0'], p['v0'], p['W'], p['H'])
        if f is None:
            log['skipped_lumpy'] = log.get('skipped_lumpy', 0) + 1
            p['top_fn'] = None
            return None
    else:
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
    p['f'] = f
    p['us'], p['vs'], p['cut_used'], p['corners_used'] = us, vs, cut, (cuts if cut > 0 else (0, 0, 0, 0))
    p['top'] = gap + t
    return p['top_fn']


def plate_rivets4(mesh, top_fn, us, vs, R, p, keep_fn, extra=()):
    pts = D.corner_pts(us, vs, R['inset'], p.get('cut_used', 0.0), p.get('corners_used', (0, 0, 0, 0))) + list(extra)
    pts = [(u, v) for (u, v) in pts if keep_fn(p['x0'] + u, p['v0'] + v)]
    return D.rivet_row(mesh, top_fn, pts, r=R['r'], h=R['h'])


def layer_plates(mesh, rows, fills, K, rng, log, style=ZONE1_STYLE, tag=''):
    """zone 1's layers on tiled plates (rows: tile_rows output, fills: fill_gaps output, any masks): raised plates
    overlapping both row neighbours (some heavy armour), riveted frame ribs over plain seams, slotted armour plates,
    picture frames, patches, ~30 % calm; then the geometry with rivets on corners / ribs / armour edges only.
    Returns the stats dict (also merged into log['layers'][tag])."""
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
            p['mat'] = style['armour'] if rng.random() < style.get('armour_p', SH['armour']) else p['mat']
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

    # slotted armour plates
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

    # picture frames and patches
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

    # ---- geometry
    nr = 0
    built = dict(base=0, raised=0, battens=0, frames=0, patches=0, slotted=0)
    for p in flat:
        top_fn = build_plate4(mesh, p, K, PL['gap'], PL['t'], PL['bevel'], log)
        if top_fn:
            built['base'] += 1
            if p['W'] * p['H'] >= style.get('rivet_min_area', 0.12):
                nr += plate_rivets4(mesh, top_fn, p['us'], p['vs'], R, p, lambda x, v, M=p['M']: free_of_keepout(M, x, v))
    for p in raised:
        top_fn = build_plate4(mesh, p, K, G2, SH['t'], PL['bevel'], log)
        if top_fn:
            built['raised'] += 1
            extra = []
            if p.get('armour'):
                k = max(1, int(round((p['W'] - 2 * R['inset']) / R['spacing'])))
                extra = [(R['inset'] + (p['W'] - 2 * R['inset']) * i / k, R['inset']) for i in range(1, k)]
            nr += plate_rivets4(mesh, top_fn, p['us'], p['vs'], R, p, lambda x, v: True, extra)
    for b in battens:
        f = surf_of(b['M'], b['x0'], b['v0'], b['W'], b['H'])
        if f is None:
            continue
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
        f = surf_of(p['M'], p['x0'] + fr['edge'], p['v0'] + fr['edge'], W, H)
        if f is None:
            continue
        D.picture_frame(mesh, f, W, H, FR['rim'], G2, FR['t'], 0.012, fr['mat'], kind='frame')
        built['frames'] += 1
        top = lift_fn(f, G2 + FR['t'])
        nr += D.rivet_row(mesh, top, D.corner_pts(np.array([0.0, W]), np.array([0.0, H]), FR['rim'] / 2), r=R['r'], h=R['h'])
    for pa in patches:
        if not pa['plate'].get('top_fn'):
            continue
        top_fn = build_plate4(mesh, pa, K, G2, PA['t'], 0.012, log)
        if top_fn:
            built['patches'] += 1
            nr += plate_rivets4(mesh, top_fn, pa['us'], pa['vs'], dict(R, inset=0.05), pa, lambda x, v: True)
    for sl in slotted:
        p = sl['plate']
        if not p.get('top_fn'):
            continue
        f = surf_of(p['M'], p['x0'] + sl['u0'], p['v0'] + sl['v0'], sl['W'], sl['H'])
        if f is None:
            continue
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


# ================================================================== structural pieces
def edge_angle(mesh, c0, c1, n1, n2, leg=0.13, t=0.032, gap=0.015, mat='dark_metal', rivet_step=0.28, R=None,
               kind='angle', rivets=True, stagger=True):
    """riveted angle iron over a convex crease between two plane faces (outward normals n1, n2) from c0 to c1 (points
    on the crease line): an L section whose legs lie `gap` off each face, `leg` wide, `t` thick; rivets along both
    legs (staggered: every rivet_step along the crease, the legs take turns). Also works as a bent strap over a
    shallow crease. Returns the number of rivets."""
    c0, c1 = D.vec(c0), D.vec(c1)
    e = D.unit(c1 - c0)
    n1 = D.unit(np.asarray(n1) - e * np.dot(n1, e)); n2 = D.unit(np.asarray(n2) - e * np.dot(n2, e))
    d1 = D.unit(np.cross(e, n1)); d2 = D.unit(np.cross(e, n2))
    if np.dot(d1, n2) > 0:            # d1 must point away from face 2 (into face 1)
        d1 = -d1
    if np.dot(d2, n1) > 0:
        d2 = -d2
    k = 1.0 + float(np.dot(n1, n2))

    def section(c):
        lo = c + (n1 + n2) * (gap / k)
        hi = c + (n1 + n2) * ((gap + t) / k)
        return [lo, c + n1 * gap + d1 * leg, c + n1 * (gap + t) + d1 * leg, hi,
                c + n2 * (gap + t) + d2 * leg, c + n2 * gap + d2 * leg]
    mesh.prism(section(c0), section(c1), mat, False, kind)
    nr = 0
    if rivets:
        R = R or dict(r=0.022, h=0.012)
        L = float(np.linalg.norm(c1 - c0))
        m = max(1, int(round((L - 0.16) / rivet_step)))
        for i in range(m + 1):                    # staggered: one rivet every rivet_step along the crease, legs taking turns
            c = c0 + e * (0.08 + (L - 0.16) * i / m)
            n_, d_ = ((n1, d1), (n2, d2))[i % 2] if stagger else (n1, d1)
            D.rivet(mesh, c + n_ * (gap + t) + d_ * leg * 0.58, n_, r=R['r'], h=R['h'])
            nr += 1
    return nr


def plane_meet(n1, a1, n2, a2, x):
    """point at coordinate x (world X) on the line where planes (n1, a1) and (n2, a2) meet (None if parallel to X)"""
    e = np.cross(n1, n2)
    if np.linalg.norm(e) < 1e-6:
        return None
    # solve n1.p = n1.a1, n2.p = n2.a2, p.x = x
    A = np.array([n1, n2, [1.0, 0.0, 0.0]])
    b = np.array([np.dot(n1, a1), np.dot(n2, a2), x])
    try:
        return np.linalg.solve(A, b)
    except np.linalg.LinAlgError:
        return None


def bolted_block(mesh, origin, n, u_hint, w, h, d, mat='machinery', base_mat='dark_metal', kind='block', R=None,
                 cap_mat=None):
    """big bolted block (reference 1's bow): a chamfered body on a riveted base plate, a thick cap plate on top with
    a rivet in each corner. origin on the surface, n out. Height d above the surface (keep <= 0.19).
    cap_mat: the cap's colour (default: the base's). Same as the body = one solid stepped block (look-and-fix pass
    2026-11-28: a dark cap inside a lighter body read as a small framed window from 25 m)."""
    u, v, n = D.ortho_frame(n, u_hint)
    o = D.vec(origin)
    R = R or dict(r=0.022, h=0.012)
    bt = 0.022
    D.chamfer_box(mesh, D.frame_matrix(o + n * (0.012 + bt / 2), u, v, n), w / 2 + 0.07, h / 2 + 0.07, bt / 2, 0.006,
                  base_mat, kind)
    body = d - bt - 0.035 - 0.012
    D.chamfer_box(mesh, D.frame_matrix(o + n * (0.012 + bt + body / 2 - 0.002), u, v, n), w / 2, h / 2, body / 2,
                  min(0.025, body * 0.25), mat, kind)
    top = o + n * (0.012 + bt + body - 0.004)
    D.chamfer_box(mesh, D.frame_matrix(top + n * 0.0175, u, v, n), w / 2 - 0.035, h / 2 - 0.035, 0.0175, 0.008,
                  cap_mat or (base_mat if mat != base_mat else 'rust_dark'), kind)
    nr = 0
    for su in (-1, 1):
        for sv in (-1, 1):
            D.rivet(mesh, o + n * (0.012 + bt) + u * su * (w / 2 + 0.035) + v * sv * (h / 2 + 0.035), n, r=R['r'], h=R['h'])
            nr += 1
    for su in (-1, 1):
        for sv in (-1, 1):
            D.rivet(mesh, top + n * 0.035 + u * su * (w / 2 - 0.075) + v * sv * (h / 2 - 0.075), n, r=R['r'], h=R['h'])
            nr += 1
    return nr


def strap(mesh, f, L, w, gap, t, mat, R, along='u', kind='strap', rivet_step=0.28, seg=0.5):
    """riveted strap on surface function f: [0, L] along u (or v) and w across; rivets along its centre line"""
    if along == 'u':
        us, vs = D.grid_coords(0.0, L, seg), np.array([0.0, w])
        pts = lambda k, m: [(0.08 + (L - 0.16) * i / m, w / 2) for i in range(m + 1)]
    else:
        us, vs = np.array([0.0, w]), D.grid_coords(0.0, L, seg)
        pts = lambda k, m: [(w / 2, 0.08 + (L - 0.16) * i / m) for i in range(m + 1)]
    top_fn, ok = D.solid_plate(mesh, f, us, vs, gap, t, min(0.012, t * 0.3), mat, kind=kind)
    if not ok:
        return 0, False
    m = max(1, int(round((L - 0.16) / rivet_step)))
    return D.rivet_row(mesh, top_fn, pts(0, m), r=R['r'], h=R['h']), True


def bay(mesh, M, ba, va, W, H, K, rng, log, rim=0.09, rim_t=0.05, depth=0.11, pump=True, tank=True, tag='bay',
        housing_dir=None, pump_r=0.062):
    """zone 1's machinery bay on any mask rectangle [ba, ba+W] x [va, va+H]: riveted rust frame round a dark floor,
    a housing (hinged + latched lid) with flanged stubs, a pump body fed by a copper pipe, a gas bottle, a valve on
    the branch. Returns the number of rivets (0 when the surface is not there)."""
    R = K['rivet']
    PL = K['plate']
    f = surf_of(M, ba, va, W, H)
    if f is None:
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
            rp = pump_r                         # zone 1: 0.068; 0.062 keeps the pump's bands inside 20 cm
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
    # the housing's other stub: a short riser with a valve that goes into the hull through a gland in the frame
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
            D.valve_body(mesh, P_[mid_i], D.unit(P_[mid_i + 1] - P_[mid_i - 1]), qa[1], 0.035)
            D.gland(mesh, qg[0], qg[1], D.unit(q2[0] - q[0]), 0.035, size=0.07, back=PL['gap'] + rim_t)
    log.setdefault('bays', []).append(dict(tag=tag, u=[round(ba, 2), round(ba + W, 2)], v=[round(va, 2), round(va + H, 2)]))
    return nr


def drop_intersecting(mesh, bvhs, kinds_keep=(), where=None):
    """remove every loose piece of `mesh` whose faces intersect any of `bvhs` ({name: BVH}: other zones' objects,
    moving parts at rest). Returns {kind: pieces removed}; where (list): filled with (zone, kind, centre)"""
    if not mesh.f or not bvhs:
        return {}
    fc, _ = mesh.components()
    det = BVHTree.FromPolygons(mesh.v, [list(f) for f in mesh.f])
    bad = set()
    for name, b in bvhs.items():
        for (i, _) in det.overlap(b):
            if int(fc[i]) not in bad and where is not None:
                where.append((name, mesh.k[i], [round(float(c), 2) for c in np.mean([mesh.v[j] for j in mesh.f[i]], 0)]))
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


# ================================================================== pipes on panels
def _surf_near(M):
    def f(pt):
        r = M.target.nearest(pt, 1.0)
        return None if r is None else (r[0], r[1])
    return f


def pipe_channel(mesh, M, u0, u1, v0, K, rng, log, r=(0.06, 0.05), dv=(0.13, 0.37), H=0.5, over=0.0, tag='channel'):
    """zone 1's pipe channel on a panel from u0 to u1 at v0 .. v0 + H: dark backing pieces on the free cells, two big
    pipes (copper, brass) with flanges, clamps every metre and a valve, each end diving into a riveted gland.
    `over`: extra height so the pipes pass over straps that cross the channel. Returns the number of pipes."""
    PL = K['plate']
    base_off = PL['gap'] + 0.015
    # backing: one piece per run of free cells along the strip
    i0, i1 = M.ix(u0), M.ix(u1)
    m0, m1 = M.iv(v0), M.iv(v0 + H)
    ok = [bool(M.free[i, m0:m1 + 1].all() and not M.used[i, m0:m1 + 1].any()) for i in range(i0, i1 + 1)]
    runs, cur = [], None
    for k, g in enumerate(ok):
        u = M.xs[i0 + k]
        if g:
            cur = [u, u] if cur is None else [cur[0], u]
        else:
            if cur and cur[1] - cur[0] > 0.3:
                runs.append(cur)
            cur = None
    if cur and cur[1] - cur[0] > 0.3:
        runs.append(cur)
    for (a, b) in runs:
        f = M.fn(a, v0)
        D.solid_plate(mesh, f, D.grid_coords(0.0, b - a, 0.5), D.grid_coords(0.0, H, 0.25), PL['gap'], 0.015, 0.004,
                      'dark_metal', kind='channel')
    n = 0
    for k, (rp, v_) in enumerate(zip(r, dv)):
        off = base_off + 0.006 + rp + over
        pts = []
        for u in np.linspace(u0 + 0.32, u1 - 0.32, max(4, int((u1 - u0) / 0.35))):
            q = M.at(u, v0 + v_)
            if q is None:
                pts = None
                break
            pts.append(q[0] + q[1] * off)
        q0, q1 = M.at(u0 + 0.14, v0 + v_), M.at(u1 - 0.14, v0 + v_)
        if not pts or q0 is None or q1 is None:
            continue
        path = [q0[0] - q0[1] * 0.02] + pts + [q1[0] - q1[1] * 0.02]
        ncl = max(1, int((u1 - u0) / K['channel']['clamp_step']))
        D.pipe_run(mesh, path, rp, 0.16, sides=12, mat='copper' if k == 0 else 'brass', flange_at=(0.2, 0.5, 0.8),
                   flange_k=1.25, clamp_at=[(i + 0.5) / ncl for i in range(ncl)], surf_fn=_surf_near(M), kind='pipe')
        for q in (q0, q1):
            D.gland(mesh, q[0], q[1], M.U, rp, size=rp * 1.9, back=base_off)
        if k == 0 and len(pts) > 4:
            i = len(pts) // 3
            D.valve_body(mesh, pts[i], D.unit(pts[i + 1] - pts[i - 1]), q0[1], rp * 0.88)
        n += 1
    log.setdefault('channels', []).append(dict(tag=tag, u=[round(u0, 2), round(u1, 2)], v=round(v0, 2), pipes=n,
                                               backing_runs=len(runs)))
    return n


def conduit_pair(mesh, M, u0, u1, v, K, log, r=(0.03, 0.026), dv=0.095, off0=0.02, tag='conduit'):
    """zone 1's conduit pair on a panel (dark r 3 cm + brass r 2.6 cm), clamped, both ends dropping into glands"""
    n = 0
    for k, rr in enumerate(r):
        vv = v + k * dv
        pts = []
        for u in np.arange(u0, u1 + 1e-9, 0.25):
            q = M.at(u, vv)
            if q is None:
                pts = None
                break
            pts.append(q[0] + q[1] * (off0 + rr))
        if not pts or len(pts) < 5:
            continue
        qa, qb = M.at(u0, vv), M.at(u1, vv)
        path = [qa[0] - qa[1] * 0.02] + pts[1:-1] + [qb[0] - qb[1] * 0.02]
        n_cl = max(2, int((u1 - u0) / K['conduit']['clamp_step']))
        D.pipe_run(mesh, path, rr, 0.08, sides=8, mat='dark_metal' if k == 0 else 'brass', flange_at=(),
                   clamp_at=[(i + 0.5) / n_cl for i in range(n_cl)], surf_fn=_surf_near(M), kind='conduit')
        for q in (qa, qb):
            D.gland(mesh, q[0], q[1], M.U, rr, size=0.065, back=0.0)
        n += 1
    log.setdefault('conduits', []).append(dict(tag=tag, u=[round(u0, 2), round(u1, 2)], v=round(v, 2), pipes=n))
    return n
