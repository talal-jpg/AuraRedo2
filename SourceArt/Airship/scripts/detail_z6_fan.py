"""Zone 6: the two big side fans (Turbine_L / Turbine_R), round 3.

Talal's answer 4 (2026-11-28): "remove the back of the fans so that they are visible from back". The base edit
base_edits/z6.json deletes the duct back wall and the big tail cone of each fan (whole islands). This module builds
what a real ducted fan has at its exhaust, plus the plating of the housing, all as detail objects:
  * housing (bone Turbine_X): riveted front rim band, plate rows with the approved layers (raised rust armour, picture
    frames, patches, slotted plates, rust frame ribs over seams, ~30 % calm), a dark gimbal track band under the gimbal
    ring, a rear band, two machinery bays (housing with hinged lid, gas bottle, pipe into a gland; two small housings
    with a valve), rust rim segments on the duct's rear face, a dark exhaust liner inside the duct behind the blades
    with stiffener ribs, a 5-strut stator spider (rust struts on riveted feet) holding a small bearing housing with a
    short tail cone, rivets on the gimbal ring's aft face, support blocks under the top platform
  * rotor (bone Turbine_X_Rotor): a riveted tail cap on the hub's flat rear face; since Talal's answer of 2026-11-28
    also a riveted blade-root collar ring with a clamp cuff per slat and a steel tip cap on every slat end
    (build_rotor_blades; the slats themselves are the base model's, unchanged)
  * hanging rod (bone Turbine_X_Rod): a riveted collar and a plumb weight at the lower end
Every housing piece is tested before it is kept: not into the housing's own fittings (gimbal ring, beams, knobs,
platform, lip), not into the hull, the fan mounts or the zone's hull details at any yaw (-12 .. 12 deg), not into the
hanging rod at any swing (+-20), not into the rotor's swept volume, not above a PA_Airship box top.
"""
import math
import numpy as np
from mathutils import Vector as V
import detail_common as D
from detail_flank import wchoice
import detail_z6_lib as L

R0 = 3.6                    # nominal outer radius for arc lengths on the shell (shell r 3.53 .. 3.65)
R_IN = 2.788                # duct inner wall radius
ROWS = dict(FB=(-16.235, -16.035), P1=(-17.20, -16.265), GB=(-17.62, -17.26), P2=(-18.20, -17.65),
            RB=(-18.47, -18.23))


class Fan:
    def __init__(self, ship, s):
        self.s = s
        self.side = 1 if s == 'L' else -1
        self.cy, self.cz = self.side * 7.6, 1.4
        self.bone, self.rotor, self.rod = 'Turbine_' + s, 'Turbine_%s_Rotor' % s, 'Turbine_%s_Rod' % s
        part = 'FanHousing_' + s
        self.isl = {}
        for i, r in ship.islands.items():
            if r['part'] == part:
                self.isl.setdefault(r.get('piece', ''), []).append(i)
        self.shell = ship.surface(np.isin(ship.p_island, self.isl['shell']))
        self.ring = ship.surface(np.isin(ship.p_island, self.isl['gimbal_ring']))
        self.hub_isl = [i for i, r in ship.islands.items() if r['part'] == 'FanRotor_' + s and r.get('piece') == 'hub_spinner']

    def d(self, th):
        a = math.radians(th)
        return np.array([0.0, self.side * math.cos(a), math.sin(a)])

    def pt(self, x, th, r):
        return np.array([x, self.cy, self.cz]) + self.d(th) * r

    def rad(self, P):
        P = np.asarray(P, float)
        return np.hypot(P[..., 1] - self.cy, P[..., 2] - self.cz)

    def out(self, x, th):
        r = self.shell.ray(self.pt(x, th, 5.5), -self.d(th), 4.0)
        return None if r is None else (r[0], r[1])

    def inn(self, x, th):
        r = self.shell.ray(self.pt(x, th, 0.4), self.d(th), 3.0)
        if r is None or r[1] @ self.d(th) > 0:
            return None
        return r[0], r[1]

    def rear(self, rho, th):
        r = self.shell.ray(self.pt(-21.0, th, rho), np.array([1.0, 0.0, 0.0]), 4.0)
        if r is None or r[1][0] > -0.3:
            return None
        return r[0], r[1]

    def out_fn(self, th0, x0):
        return lambda u, v: self.out(x0 - v, th0 + math.degrees(u / R0))

    def inn_fn(self, th0, x0):
        return lambda u, v: self.inn(x0 - v, th0 + math.degrees(u / R_IN))

    def rear_fn(self, th0, rho0, rho_m=3.2):
        return lambda u, v: self.rear(rho0 + v, th0 + math.degrees(u / rho_m))

    def rotor_zone(self, P):
        """vertices inside the rotor's swept volume (blades r 0.79 .. 2.75 at x -17.415 .. -16.90, hub r 0.82 at
        x -17.774 .. -16.05, the rotor tail cap to x -17.87), with a 3-4 cm margin"""
        P = np.asarray(P, float)
        r = self.rad(P)
        x = P[:, 0]
        return ((r < 2.775) & (x > -17.47) & (x < -16.85)) | ((r < 0.86) & (x > -17.92) & (x < -16.0))


# ------------------------------------------------------------------ the free map on the outer shell
class FanMap:
    """highest free height level over the outer shell per (x, theta) cell: a point at the level height above the shell
    must keep 3 cm from the housing's own fittings, 3 cm from the hull (+ zone hull details) at every yaw pose, 4 cm
    from the hanging rod at every swing pose and stay below the PA_Airship box tops"""
    HS = (0.035, 0.075, 0.125, 0.215)

    def __init__(self, fan, obst, hull_bvh, yaw_mats, rod_bvhs, boxes):
        self.fan = fan
        self.xs = np.arange(-18.52, -15.97, 0.05)
        self.ths = np.arange(0.0, 360.0, 2.0)
        self.level = np.full((len(self.xs), len(self.ths)), -1, int)
        Ms = [np.asarray(M) for M in yaw_mats]
        for i, x in enumerate(self.xs):
            for j, th in enumerate(self.ths):
                h = fan.out(x, th)
                if h is None:
                    continue
                p, n = h
                for k, hh in enumerate(self.HS):
                    q = p + n * hh
                    if obst.find_nearest(V(q), 0.03)[0] is not None:
                        break
                    bad = False
                    for M in Ms:
                        if hull_bvh.find_nearest(V(M[:3, :3] @ q + M[:3, 3]), 0.03)[0] is not None:
                            bad = True
                            break
                    if not bad:
                        for rb in rod_bvhs:
                            if rb.find_nearest(V(q), 0.04)[0] is not None:
                                bad = True
                                break
                    if bad or L.pa_bad(q[None], boxes)[0]:
                        break
                    self.level[i, j] = k

    def ok(self, th0, th1, xa, xb, lev, pad_th=2.0, pad_x=0.03):
        """is every cell of the patch theta [th0, th1] x x [xa, xb] (xa < xb) free up to level `lev`?"""
        im = (self.xs >= xa - pad_x) & (self.xs <= xb + pad_x)
        if not im.any():
            return False
        a0, a1 = th0 - pad_th, th1 + pad_th
        rel = (self.ths - a0) % 360.0
        jm = rel <= (a1 - a0) + 1e-6
        return bool((self.level[np.ix_(im, jm)] >= lev).all())


def arc_runs(fm, xa, xb, lev, step=2.0):
    """free arcs (theta0, theta1) at a level over the x range, theta in degrees, wrapping round"""
    ths = np.arange(0.0, 360.0, step)
    ok = np.array([fm.ok(t, t + step, xa, xb, lev, pad_th=0.5, pad_x=0.0) for t in ths])
    if ok.all():
        return [(0.0, 360.0)]
    if not ok.any():
        return []
    n = len(ths)
    start = next(i for i in range(n) if ok[i] and not ok[i - 1])
    runs, cur = [], None
    for k in range(n):
        i = (start + k) % n
        if ok[i]:
            cur = [start + k, start + k] if cur is None else [cur[0], start + k]
        elif cur is not None:
            runs.append(cur)
            cur = None
    if cur is not None:
        runs.append(cur)
    return [(ths[0] + a * step, ths[0] + (b + 1) * step) for a, b in runs]


def in_arcs(th0, th1, arcs):
    for a0, a1 in arcs:
        if (th0 - a0) % 360.0 < (a1 - a0) or (a0 - th0) % 360.0 < (th1 - th0):
            return True
    return False


# ------------------------------------------------------------------ builder
def build_fan(fan, housing, K, rng, log, checks):
    """housing details of one fan. checks: dict 'housing' -> check list for detail_z6_lib.Part.accept, 'map' -> FanMap"""
    FK = K['fan']
    PL, RV = K['plate'], K['rivet']
    G2 = PL['gap'] + PL['t'] + K['layer']
    fm = checks['map']
    CH = checks['housing']
    lg = log.setdefault('fan_' + fan.s, {})
    deg = lambda w, r=R0: math.degrees(w / r)
    seam_deg = deg(K['seam'])

    def rivets_on(tmp, top_fn, pts, r=RV['r'], h=RV['h']):
        return D.rivet_row(tmp, top_fn, pts, r=r, h=h)

    # ---- bands (front rim band, gimbal track, rear band): free arcs split into riveted segments
    def band(name, xr, t, mat, rstep, lev=1):
        xa, xb = xr
        H = xb - xa
        n = 0
        for (a0, a1) in arc_runs(fm, xa, xb, lev):
            Larc = math.radians(a1 - a0) * R0
            full = (a1 - a0) >= 359.0
            if Larc < 0.25:
                continue
            k = max(1, int(math.ceil(Larc / FK['band_seg'])))
            Ls = Larc / k
            for i in range(k):
                th0 = a0 + deg(i * Ls) + (seam_deg / 2 if (i or full) else 0.0)
                W = Ls - (K['seam'] / 2 if (i or full) else 0.0) - (K['seam'] / 2 if (i < k - 1 or full) else 0.0)
                tmp = housing.new()
                top_fn, ok = D.solid_plate(tmp, fan.out_fn(th0, xb), D.grid_coords(0.0, W, 0.3), np.array([0.0, H]),
                                           PL['gap'], t, 0.012, mat, kind='band_' + name)
                if not ok:
                    continue
                if rstep:
                    m = max(1, int(round((W - 0.1) / rstep)))
                    rivets_on(tmp, top_fn, [(0.05 + (W - 0.1) * (j + 0.5) / m, H / 2) for j in range(m)])
                n += int(housing.accept(tmp, CH, 'band_' + name))
        lg['band_' + name] = n

    band('front', ROWS['FB'], 0.05, 'rust_red', 0.35)
    band('gimbal', ROWS['GB'], 0.04, 'dark_metal', 0.7)
    band('rear', ROWS['RB'], 0.045, 'rust_red', 0.0)

    # ---- machinery bays in row P1 (hero clusters): reserved first
    xa1, xb1 = ROWS['P1']
    bays = []
    for (thc, Wb, kind_) in FK['bays']:
        dth = deg(Wb)
        placed = None
        for sh in (0, 4, -4, 8, -8, 12, -12, 16, -16):
            t0 = thc + sh - dth / 2
            if fm.ok(t0, t0 + dth, xa1 + 0.05, xb1 - 0.05, 3):
                placed = t0
                break
        if placed is None:
            lg.setdefault('bays_skipped', []).append(thc)
            continue
        bays.append(dict(th0=placed, th1=placed + dth, W=Wb, kind=kind_))
    reserved = [(b['th0'] - seam_deg, b['th1'] + seam_deg) for b in bays]

    # ---- plate rows
    plates = []
    for row in ('P1', 'P2'):
        xa, xb = ROWS[row]
        H = xb - xa
        th = rng.uniform(0.0, 360.0)
        end = th + 360.0
        prow = []
        while th < end - deg(FK['min_w']):
            if in_arcs(th, th + 0.5, reserved if row == 'P1' else []):
                th += 2.0
                continue
            W = rng.uniform(*FK['w'])
            th1 = min(th + deg(W), end - seam_deg)
            if row == 'P1':
                for (a0, a1) in reserved:                  # stop before a bay
                    rel = (a0 - th) % 360.0
                    if rel < th1 - th:
                        th1 = th + rel
            t1, ok = th1, False
            while math.radians(t1 - th) * R0 >= FK['min_w']:
                if fm.ok(th, t1, xa, xb, 1):
                    ok = True
                    break
                t1 -= 2.0
            if not ok:
                th += 2.0
                continue
            Wp = math.radians(t1 - th) * R0
            cut = rng.uniform(*PL['cut'])
            corners = tuple(int(rng.random() < PL['cut_p']) for _ in range(4))
            prow.append(dict(row=row, th0=th, th1=t1, W=Wp, x0=xb, H=H, mat=wchoice(rng, FK['mats']), corners=corners,
                             cut=cut if any(corners) else 0.0))
            th = t1 + seam_deg
        plates += prow
    # layers: raised rust armour (never two neighbours), frame ribs over seams, slotted plates, picture frames, patches
    for row in ('P1', 'P2'):
        ps = [p for p in plates if p['row'] == row]
        for i, p in enumerate(ps):
            p['raised'] = (rng.random() < FK['armour_p'] and not (i and ps[i - 1].get('raised')) and p['W'] >= 0.6)
        for i, p in enumerate(ps):
            if not p['raised']:
                continue
            ov = deg(FK['overlap'])
            a0, a1 = p['th0'] - ov, p['th1'] + ov
            if fm.ok(a0, a1, ROWS[row][0], ROWS[row][1], 2):
                p['th0'], p['th1'], p['W'] = a0, a1, math.radians(a1 - a0) * R0
                p['mat'] = 'rust_red'
                p['corners'] = (0, 0, 0, 0)
                p['cut'] = 0.0
            else:
                p['raised'] = False
    battens = []
    for row in ('P1', 'P2'):
        p_sorted = sorted([p for p in plates if p['row'] == row], key=lambda q: q['th0'])
        for a_, b_ in zip(p_sorted, p_sorted[1:] + p_sorted[:1]):
            if a_['raised'] or b_['raised']:
                continue
            gap = (b_['th0'] - a_['th1']) % 360.0
            if gap > 3 * seam_deg or rng.random() > FK['batten_p']:
                continue
            battens.append((row, a_['th1'] + gap / 2))
    raised_arcs = [(p['row'], p['th0'], p['th1']) for p in plates if p['raised']]

    def under_raised(row, th):
        return any(r_ == row and (th - a0 + deg(0.04)) % 360.0 < (a1 - a0) + 2 * deg(0.04) for r_, a0, a1 in raised_arcs)
    flat = [p for p in plates if not p['raised']]
    rng.shuffle(flat)
    nslot = 0
    for p in flat:
        if nslot < FK['slots'] and p['row'] == 'P1' and p['W'] >= 0.95 and fm.ok(p['th0'], p['th1'], *ROWS['P1'], 2):
            p['slot'] = dict(W=rng.uniform(0.55, min(0.8, p['W'] - 0.25)), H=rng.uniform(0.32, 0.45),
                             n=rng.choice((3, 4)))
            nslot += 1
            continue
        if not fm.ok(p['th0'], p['th1'], ROWS[p['row']][0], ROWS[p['row']][1], 2):
            continue
        if p['W'] >= 0.6 and p['H'] >= 0.45 and rng.random() < FK['frame_p']:
            p['frame'] = 'paint_ochre' if p['mat'] == 'paint_orange' else 'paint_orange'
            continue
        if rng.random() < FK['patch_p']:
            w = min(rng.uniform(0.4, 0.75), p['W'] - 0.18)
            h = min(rng.uniform(0.28, 0.5), p['H'] - 0.14)
            if w >= 0.3 and h >= 0.22:
                p['patch'] = dict(u0=rng.uniform(0.09, p['W'] - w - 0.09), v0=rng.uniform(0.07, p['H'] - h - 0.07), W=w,
                                  H=h, mat=wchoice(rng, FK['patch_mats']))
    nrv = 0
    bat_ths = [(r_, t_) for r_, t_ in battens]

    def near_batten(row, th):
        return any(r_ == row and abs(((th - t_ + 180.0) % 360.0) - 180.0) < deg(0.085) for r_, t_ in bat_ths)
    built = dict(base=0, raised=0, frames=0, patches=0, slotted=0, battens=0)
    for p in plates:
        tmp = housing.new()
        gap, t = (G2, 0.04) if p['raised'] else (PL['gap'], PL['t'])
        cut = min(p['cut'], 0.3 * min(p['W'], p['H']))
        us = D.grid_coords(0.0, p['W'], 0.3, cut)
        vs = D.grid_coords(0.0, p['H'], 0.5, cut)
        f = fan.out_fn(p['th0'], p['x0'])
        top_fn, ok = D.solid_plate(tmp, f, us, vs, gap, t, PL['bevel'], p['mat'],
                                   corners=p['corners'] if cut > 0 else (0, 0, 0, 0),
                                   kind='plate_raised' if p['raised'] else 'plate')
        if not ok:
            continue
        pts = D.corner_pts(us, vs, RV['inset'], cut, p['corners'] if cut > 0 else (0, 0, 0, 0))
        pts = [(u, v) for (u, v) in pts if not near_batten(p['row'], p['th0'] + deg(u)) and
               (p['raised'] or not under_raised(p['row'], p['th0'] + deg(u)))]
        if p['raised']:
            k = max(1, int(round((p['W'] - 2 * RV['inset']) / RV['spacing'])))
            pts += [(RV['inset'] + (p['W'] - 2 * RV['inset']) * i / k, RV['inset']) for i in range(1, k)]
        if p['W'] * p['H'] >= 0.12:
            nrv += rivets_on(tmp, top_fn, pts)
        if not housing.accept(tmp, CH, 'plate'):
            continue
        p['ok'] = True
        built['raised' if p['raised'] else 'base'] += 1
        # layers on this plate
        if p.get('frame'):
            tmp = housing.new()
            e = FK['frame_edge']
            Wf, Hf = p['W'] - 2 * e, p['H'] - 2 * e
            fr = lambda u, v, f=f: f(u + e, v + e)
            if Wf > 0.35 and Hf > 0.25:
                D.picture_frame(tmp, fr, Wf, Hf, 0.075, G2, 0.035, 0.012, p['frame'], kind='frame', cell=0.3)
                top = lambda u, v, fr=fr: (lambda r: None if r is None else (r[0] + r[1] * (G2 + 0.035), r[1]))(fr(u, v))
                nrv += rivets_on(tmp, top, D.corner_pts(np.array([0.0, Wf]), np.array([0.0, Hf]), 0.0375))
                built['frames'] += int(housing.accept(tmp, CH, 'frame'))
        if p.get('patch'):
            pa = p['patch']
            tmp = housing.new()
            fp = lambda u, v, f=f, pa=pa: f(pa['u0'] + u, pa['v0'] + v)
            us2, vs2 = D.grid_coords(0.0, pa['W'], 0.3), D.grid_coords(0.0, pa['H'], 0.5)
            t2, ok2 = D.solid_plate(tmp, fp, us2, vs2, G2, 0.04, 0.012, pa['mat'], kind='patch')
            if ok2:
                nrv += rivets_on(tmp, t2, D.corner_pts(us2, vs2, 0.05))
                built['patches'] += int(housing.accept(tmp, CH, 'patch'))
        if p.get('slot'):
            sl = p['slot']
            tmp = housing.new()
            u0 = rng.uniform(0.1, p['W'] - sl['W'] - 0.1)
            v0 = (p['H'] - sl['H']) / 2
            fs = lambda u, v, f=f, u0=u0, v0=v0: f(u0 + u, v0 + v)
            if D.slotted_plate(tmp, fs, sl['W'], sl['H'], G2, 0.035, 0.01, p['mat'], n_slots=sl['n'], slot_w=0.05, ang=58.0):
                top = lambda u, v, fs=fs: (lambda r: None if r is None else (r[0] + r[1] * (G2 + 0.048), r[1]))(fs(u, v))
                nrv += rivets_on(tmp, top, [(0.045, 0.037), (sl['W'] - 0.045, 0.037), (0.045, sl['H'] - 0.037),
                                            (sl['W'] - 0.045, sl['H'] - 0.037)], r=0.018, h=0.01)
                built['slotted'] += int(housing.accept(tmp, CH, 'slotted'))
    for (row, thc) in battens:
        xa, xb = ROWS[row]
        H = xb - xa + 0.02
        w = FK['batten_w']
        tmp = housing.new()
        top_fn, ok = D.solid_plate(tmp, fan.out_fn(thc - deg(w / 2), xb + 0.01), np.array([0.0, w]), D.grid_coords(0.0, H, 0.5),
                                   G2, 0.05, 0.012, 'rust_red', kind='batten')
        if ok:
            k = max(1, int(round((H - 0.12) / RV['spacing'])))
            nrv += rivets_on(tmp, top_fn, [(w / 2, 0.06 + (H - 0.12) * i / k) for i in range(k + 1)])
            built['battens'] += int(housing.accept(tmp, CH, 'batten'))
    calm = [p for p in plates if p.get('ok') and not p['raised'] and not (p.get('frame') or p.get('patch') or p.get('slot'))]
    area = sum(p['W'] * p['H'] for p in plates if p.get('ok'))
    lg['plates'] = dict(built, planned=len(plates), calm_plates=len(calm),
                        calm_share_of_area=round(sum(p['W'] * p['H'] for p in calm) / max(area, 1e-6), 2),
                        armour_share=round(built['raised'] / max(1, built['raised'] + built['base']), 2),
                        plate_area_m2=round(area, 1))

    # ---- machinery bays
    def bay_shell(tmp, f, W, H, rim=0.09, rim_t=0.05):
        D.picture_frame(tmp, f, W, H, rim, PL['gap'], rim_t, 0.014, 'rust_red', kind='bay')
        D.solid_plate(tmp, f, D.grid_coords(rim + 0.008, W - rim - 0.008, 0.22), D.grid_coords(rim + 0.008, H - rim - 0.008, 0.3),
                      PL['gap'], 0.012, 0.003, FK.get('bay_floor', 'dark_metal'), kind='bay')
        top = lambda u, v: (lambda r: None if r is None else (r[0] + r[1] * (PL['gap'] + rim_t), r[1]))(f(u, v))
        rivets_on(tmp, top, D.corner_pts(np.array([0.0, W]), np.array([0.0, H]), rim / 2) +
                  [(W / 2, rim / 2), (W / 2, H - rim / 2)])
        return PL['gap'] + 0.012 + 0.002

    def frame_at(f, u, v):
        q = f(u, v)
        q2 = f(u + 0.1, v)
        if q is None or q2 is None:
            return None
        return q[0], q[1], D.unit(q2[0] - q[0])
    nb = 0
    for b in bays:
        tmp = housing.new()
        W = b['W']
        v0, v1 = 0.05, (xb1 - xa1) - 0.05
        H = v1 - v0
        f = (lambda f0, v0: (lambda u, v: f0(u, v0 + v)))(fan.out_fn(b['th0'], xb1), v0)
        floor = bay_shell(tmp, f, W, H)
        iu0, iu1, iv0, iv1 = 0.15, W - 0.15, 0.15, H - 0.15
        if b['kind'] == 'pump':
            hw, hh = min(0.5, 0.45 * (iu1 - iu0)), min(0.46, iv1 - iv0 - 0.04)
            c = (iu0 + 0.14 + hw / 2, (iv0 + iv1) / 2)
            fr = frame_at(f, *c)
            if fr is None:
                continue
            ends = D.housing(tmp, fr[0] + fr[1] * floor, fr[1], fr[2], hw, hh, 0.1, stubs=((1, -0.5), (-1, 0.45)),
                             lid_mat=FK.get('bay_lid', 'dark_metal'))
            ua, ub = c[0] + hw / 2 + 0.16, iu1 - 0.02
            if ub - ua > 0.3:
                a_ = f(ua, iv0 + 0.1)
                b_ = f(ub, iv0 + 0.1)
                if a_ is not None and b_ is not None:
                    off = floor + 0.012 + 0.06
                    D.tank(tmp, a_[0] + a_[1] * off, b_[0] + b_[1] * off, 0.06, a_[1], mat='rust_red')
            st, sd = ends[0]
            qg = f(min(ub, c[0] + hw / 2 + 0.3), iv1 - 0.04)
            if qg is not None:
                gp = qg[0] + qg[1] * floor
                D.pipe_run(tmp, [st - sd * 0.01, st + sd * 0.07, gp + qg[1] * 0.09, gp - qg[1] * 0.02], 0.04, 0.06, sides=8,
                           mat='copper', kind='bay')
                D.gland(tmp, gp, qg[1], fr[2], 0.04, size=0.07)
            st2, sd2 = ends[1]
            g2 = st2 + sd2 * 0.1 - fr[1] * 0.062                  # the bay floor under the bend
            D.pipe_run(tmp, [st2 - sd2 * 0.01, st2 + sd2 * 0.1, g2 - fr[1] * 0.02], 0.04, 0.05, sides=8, mat='copper',
                       kind='bay')
            D.gland(tmp, g2, fr[1], sd2, 0.04, size=0.07)
        else:
            hw = min(0.42, (iu1 - iu0 - 0.25) / 2)
            hh = min(0.38, iv1 - iv0 - 0.04)
            c1 = (iu0 + 0.02 + hw / 2, (iv0 + iv1) / 2 + 0.02)
            c2 = (iu1 - 0.02 - hw / 2, (iv0 + iv1) / 2 - 0.02)
            f1, f2 = frame_at(f, *c1), frame_at(f, *c2)
            if f1 is None or f2 is None:
                continue
            e1 = D.housing(tmp, f1[0] + f1[1] * floor, f1[1], f1[2], hw, hh, 0.09, stubs=((1, -0.3),), r_stub=0.035,
                           lid_mat=FK.get('bay_lid', 'dark_metal'))
            e2 = D.housing(tmp, f2[0] + f2[1] * floor, f2[1], f2[2], hw * 0.85, hh * 0.9, 0.09, stubs=((-1, 0.2),),
                           r_stub=0.035, lid_mat=FK.get('bay_lid', 'dark_metal'))
            (a_, da), (b_, db) = e1[0], e2[0]
            P_, _ = D.pipe_run(tmp, [a_ - da * 0.01, a_ + da * 0.05, b_ + db * 0.05, b_ - db * 0.01], 0.035, 0.06, sides=8,
                               mat='brass', flange_at=(0.5,), kind='bay')
            mi = len(P_) // 2
            D.valve_body(tmp, P_[mi], D.unit(P_[mi + 1] - P_[mi - 1]), f1[1], 0.035)
        nb += int(housing.accept(tmp, CH, 'bay_' + b['kind']))
    lg['bays'] = dict(planned=[(round(b['th0'], 1), b['kind']) for b in bays], built=nb)

    # ---- rust rim segments on the duct's rear face (the heavy riveted exhaust rim)
    nrim = 0
    ph = rng.uniform(0.0, 360.0 / FK['rim_n'])
    rho0, rho1 = FK['rim_rho']
    for k in range(FK['rim_n']):
        a0 = ph + k * 360.0 / FK['rim_n'] + 0.45
        a1 = ph + (k + 1) * 360.0 / FK['rim_n'] - 0.45
        W = math.radians(a1 - a0) * 3.2
        tmp = housing.new()
        f = fan.rear_fn(a0, rho0)
        H = rho1 - rho0
        top_fn, ok = D.solid_plate(tmp, f, D.grid_coords(0.0, W, 0.32), np.array([0.0, H]), PL['gap'], 0.045,
                                   0.012, 'rust_red', kind='rim')
        if not ok:
            continue
        rivets_on(tmp, top_fn, [(0.08, H / 2), (W - 0.08, H / 2)])
        nrim += int(housing.accept(tmp, CH, 'rear_rim'))
    lg['rear_rim_segments'] = nrim

    # ---- exhaust liner inside the duct behind the blades, stiffener ribs over its joints, stator feet
    SK = K['stator']
    x_l0, x_l1 = -17.56, -18.585
    nl = FK['liner_n']
    th_l = SK['phase'] + 180.0 / SK['n'] + 0.0
    lin_t = 0.02
    nli = 0
    for k in range(nl):
        a0 = th_l + k * 360.0 / nl + deg(0.006, R_IN)
        a1 = th_l + (k + 1) * 360.0 / nl - deg(0.006, R_IN)
        W = math.radians(a1 - a0) * R_IN
        tmp = housing.new()
        top_fn, ok = D.solid_plate(tmp, fan.inn_fn(a0, x_l0), D.grid_coords(0.0, W, 0.3), np.array([0.0, x_l0 - x_l1]),
                                   0.012, lin_t, 0.005, 'dark_metal', kind='liner')
        if ok:
            nli += int(housing.accept(tmp, CH, 'liner'))
    g_l = 0.012 + lin_t + K['layer']
    nrib = 0
    for k in range(nl):
        thc = th_l + k * 360.0 / nl
        w = 0.08
        tmp = housing.new()
        top_fn, ok = D.solid_plate(tmp, fan.inn_fn(thc - deg(w / 2, R_IN), x_l0 + 0.02), np.array([0.0, w]),
                                   np.array([0.0, 0.98]), g_l, 0.03, 0.008, 'machinery', kind='liner_rib')
        if ok:
            nrib += int(housing.accept(tmp, CH, 'liner_rib'))
    lg['liner'] = dict(segments=nli, ribs=nrib)

    # ---- stator spider: struts from the liner (riveted feet) to a small bearing housing with a short tail cone
    r_foot = R_IN - g_l - 0.03                      # top of the feet (towards the axis)
    xs0, xs1 = SK['x']                              # strut chord (aft, fore)
    nst = 0
    for k in range(SK['n']):
        th = SK['phase'] + k * 360.0 / SK['n']
        tmp = housing.new()
        fw, fl = 0.26, 0.3
        top_fn, ok = D.solid_plate(tmp, fan.inn_fn(th - deg(fw / 2, R_IN), xs1 + 0.03), D.grid_coords(0.0, fw, 0.15),
                                   D.grid_coords(0.0, fl, 0.15), g_l, 0.03, 0.008, 'rust_red', kind='stator_foot')
        if not ok:
            lg.setdefault('stator_foot_failed', []).append(round(th, 1))
            continue
        rivets_on(tmp, top_fn, D.corner_pts(np.array([0.0, fw]), np.array([0.0, fl]), 0.045), r=0.02, h=0.011)
        d = fan.d(th)
        tng = np.cross(np.array([1.0, 0.0, 0.0]), d)
        r_in, r_out = SK['collar_r'] - 0.02, r_foot - 0.003
        c = np.array([(xs0 + xs1) / 2, fan.cy, fan.cz]) + d * (r_in + r_out) / 2
        D.chamfer_box(tmp, D.frame_matrix(c, tng, np.array([1.0, 0.0, 0.0]), d), SK['t'] / 2, (xs1 - xs0) / 2,
                      (r_out - r_in) / 2, 0.014, 'rust_red', 'stator')
        # small gusset plates either side at the foot
        for sg in (-1, 1):
            gc = np.array([(xs0 + xs1) / 2, fan.cy, fan.cz]) + d * (r_out - 0.09) + tng * sg * (SK['t'] / 2 + 0.03)
            D.chamfer_box(tmp, D.frame_matrix(gc, tng, np.array([1.0, 0.0, 0.0]), d), 0.03, (xs1 - xs0) / 2 - 0.02, 0.09,
                          0.006, 'rust_red', 'stator')
        nst += int(housing.accept(tmp, CH, 'stator_strut'))
    tmp = housing.new()
    ax = np.array([1.0, 0.0, 0.0])
    cxyz = lambda x: np.array([x, fan.cy, fan.cz])
    hr = SK['hub_r']
    D.cylinder(tmp, cxyz(SK['hub_x'][1]), cxyz(SK['hub_x'][0]), hr, 16, 'machinery', 'stator_hub', smooth=True)
    D.cylinder(tmp, cxyz(SK['hub_x'][1] + 0.002), cxyz(SK['hub_x'][1] - 0.035), hr + 0.07, 16, 'dark_metal', 'stator_hub',
               smooth=False)
    D.cylinder(tmp, cxyz(xs1 + 0.03), cxyz(xs0 - 0.03), SK['collar_r'], 16, 'dark_metal', 'stator_hub', smooth=False)
    xr = SK['hub_x'][0]
    D.cylinder(tmp, cxyz(xr + 0.035), cxyz(xr), hr + 0.07, 16, 'dark_metal', 'stator_hub', smooth=False)
    e90 = np.array([0.0, 0.0, 1.0])
    e0 = np.array([0.0, 1.0, 0.0])
    for q in D.ring_pts(cxyz(xr), e0, e90, hr + 0.035, 10, 0.2):
        D.rivet(tmp, q, -ax, r=0.016, h=0.009, sink=0.004)
    xt0, xt1 = xr - 0.002, SK['tail_x']
    D.cylinder(tmp, cxyz(xt0), cxyz(xt1), hr - 0.03, 16, 'machinery', 'stator_hub', smooth=True, r1=SK['tail_r'])
    D.cylinder(tmp, cxyz(xt1 + 0.004), cxyz(xt1 - 0.06), SK['tail_r'] * 0.7, 12, 'dark_metal', 'stator_hub', smooth=False)
    nh = int(housing.accept(tmp, CH, 'stator_hub'))
    lg['stator'] = dict(struts=nst, hub=nh)

    # ---- rivets on the gimbal ring's aft face, support blocks under the top platform
    ngr = 0
    obst_ray = checks['obst_bvh']
    rr = 4.14
    for th in np.arange(0.0, 360.0, deg(FK['ring_rivet_step'], rr)):
        o = fan.pt(-19.6, th, rr)
        hit = fan.ring.ray(o, np.array([1.0, 0.0, 0.0]), 3.0)
        if hit is None or not (-17.66 < hit[0][0] < -17.61):
            continue
        h2 = obst_ray.ray_cast(V(o), V((1.0, 0.0, 0.0)), 3.0)
        if h2[0] is not None and h2[3] < hit[3] - 0.003:
            continue
        tmp = housing.new()
        D.rivet(tmp, hit[0], hit[4], r=0.024, h=0.013)
        ngr += int(housing.accept(tmp, checks['housing_on_ring'], 'ring_rivet'))
    lg['ring_rivets'] = ngr
    npb = 0
    z_pl = checks['platform_z']
    for x in (np.mean(ROWS['FB']), np.mean(ROWS['RB'])):
        for sy in (-1, 1):
            th = math.degrees(math.acos(sy * 0.8 / 3.64))
            h = fan.out(x, th)
            if h is None:
                continue
            p, n = h
            zb = p[2] + 0.05
            zt = z_pl - 0.004
            if zt - zb < 0.03:
                continue
            tmp = housing.new()
            c = np.array([x, p[1], (zb + zt) / 2])
            D.chamfer_box(tmp, D.frame_matrix(c, np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, 1.0])), 0.08,
                          0.07, (zt - zb) / 2, 0.008, 'dark_metal', 'platform_block')
            npb += int(housing.accept(tmp, CH, 'platform_block'))
    lg['platform_blocks'] = npb

    lg['rivets_on_plates_and_layers'] = nrv


def build_rotor_and_rod(fan, rotor, rod, log, checks):
    """rotor (riveted tail cap on the hub's flat rear face) and hanging rod (collar, plumb weight); tested against the
    housing (+ its details) through the rotor spin and the rod swing"""
    lg = log.setdefault('fan_' + fan.s, {})
    ax = np.array([1.0, 0.0, 0.0])
    e0, e90 = np.array([0.0, 1.0, 0.0]), np.array([0.0, 0.0, 1.0])
    cxyz = lambda x: np.array([x, fan.cy, fan.cz])
    # ---- rotor: riveted tail cap on the hub's flat rear face
    tmp = rotor.new()
    x0, x1 = -17.777, -17.87
    D.cylinder(tmp, cxyz(x0), cxyz(x1), 0.79, 16, 'dark_metal', 'rotor_tail', smooth=False, r1=0.68)
    D.cylinder(tmp, cxyz(x1 + 0.002), cxyz(x1 - 0.02), 0.36, 12, 'machinery', 'rotor_tail', smooth=False)
    for q in D.ring_pts(cxyz(-17.823), e0, e90, 0.735, 8, 0.1):
        rad = D.unit(q - cxyz(-17.823))
        D.rivet(tmp, q, D.unit(rad * 0.76 - ax * 0.65), r=0.02, h=0.011, sink=0.006)
    lg['rotor_tail'] = int(rotor.accept(tmp, checks['rotor'], 'rotor_tail'))

    # ---- hanging rod: riveted collar and a plumb weight at the lower end
    rc = checks['rod_centre']
    tmp = rod.new()
    I3 = np.eye(3)
    D.chamfer_box(tmp, D.frame_matrix(np.array([rc[0], rc[1], -3.17]), I3[0], I3[1], I3[2]), 0.215, 0.215, 0.045, 0.008,
                  'dark_metal', 'rod')
    D.cylinder(tmp, np.array([rc[0], rc[1], -3.21]), np.array([rc[0], rc[1], -3.46]), 0.17, 12, 'rust_red', 'rod',
               smooth=True)
    D.cylinder(tmp, np.array([rc[0], rc[1], -3.459]), np.array([rc[0], rc[1], -3.6]), 0.17, 12, 'rust_red', 'rod',
               smooth=True, r1=0.05)
    D.cylinder(tmp, np.array([rc[0], rc[1], -3.30]), np.array([rc[0], rc[1], -3.35]), 0.185, 12, 'dark_metal', 'rod',
               smooth=False)
    lg['rod_details'] = int(rod.accept(tmp, checks['rod'], 'rod'))


# ------------------------------------------------------------------ blade root collar and tip caps (Talal 2026-11-28)
# Talal answered "yes" to "the fan blades are still the base model's 28 flat slats: a blade-root collar ring and tip
# caps?" (FULL.md section 5). The slats themselves stay as they are (base geometry, no twist / spinner pass). Added on
# the rotor bone, in SM_AirshipDetail_Z6_Rotor_X:
#   * a riveted rust collar ring round the hub where the slats start (rivets on its aft face, seen from behind)
#   * a dark clamp cuff on every slat where it leaves the collar
#   * a steel tip cap on every slat end (K['rotor']['tips'] = 'caps'), or a steel tip shroud band ('shroud', the other
#     option; the caps were chosen, see ZONE_6.md)
# Clearance: the duct's inner wall is a 32-sided polygon, inscribed radius 2.7747 (vertices 2.788) over the blade x
# range. Every new vertex stays at a radius <= K['rotor']['r_max'] from the fan axis, so the gap to the wall holds at
# every rotor angle, not only at the 15-degree steps the piece test samples (the rotor spins inside its own housing:
# the fan yaw and the rod swing do not change it).
def blade_sections(ship, fan):
    """the base blades of this fan (one 8-vertex box each: a flat slat, twisted and swept): per blade the root and tip
    corner rings (same cyclic order; root corner k joined to tip corner k by a long edge), the radial unit d and the
    distances of the root and tip faces from the axis along d (both faces are planes normal to d)"""
    ids = sorted([i for i, r in ship.islands.items() if r['part'] == 'FanRotor_' + fan.s and r.get('piece') == 'blade'],
                 key=lambda i: ship.islands[i].get('index', 0))
    C0 = np.array([0.0, fan.cy, fan.cz])
    out = []
    for i in ids:
        polys = [ship.polys[k] for k in np.nonzero(ship.p_island == i)[0]]
        vs = sorted({int(v) for p in polys for v in p})
        P = {v: np.asarray(ship.co[v], float) for v in vs}
        rad = {v: float(fan.rad(P[v])) for v in vs}
        r_mid = 0.5 * (min(rad.values()) + max(rad.values()))
        root_v = {v for v in vs if rad[v] < r_mid}
        if len(root_v) != 4 or len(vs) != 8:
            continue
        rf = [p for p in polys if {int(v) for v in p} == root_v]
        if not rf:
            continue
        order = [int(v) for v in rf[0]]
        pair = {}
        for p in polys:
            n = len(p)
            for k in range(n):
                a, b = int(p[k]), int(p[(k + 1) % n])
                if (a in root_v) != (b in root_v):
                    ra, tb = (a, b) if a in root_v else (b, a)
                    pair[ra] = tb
        root = np.array([P[v] for v in order])
        tip = np.array([P[pair[v]] for v in order])
        c = tip.mean(0) - C0
        d = D.unit(np.array([0.0, c[1], c[2]]))
        rr, rt = (root - C0) @ d, (tip - C0) @ d
        out.append(dict(island=int(i), index=ship.islands[i].get('index'), root=root, tip=tip, d=d,
                        rho_root=float(rr.mean()), rho_tip=float(rt.mean()),
                        flat_err=float(max(np.ptp(rr), np.ptp(rt)))))
    return out


def blade_section(b, rho):
    """the blade's 4 corners at distance rho from the axis (along its radial unit)"""
    t = (rho - b['rho_root']) / (b['rho_tip'] - b['rho_root'])
    return b['root'] + t * (b['tip'] - b['root'])


def inflate(Q, m_chord, m_thick):
    """grow a rectangular section (4 corners, cyclic) by m_chord along its long side and m_thick along its short side,
    on each side; returns (corners, chord unit, thickness unit, half chord, half thickness) of the grown section"""
    Q = np.asarray(Q, float)
    c = Q.mean(0)
    a, b = Q[1] - Q[0], Q[3] - Q[0]
    la, lb = np.linalg.norm(a), np.linalg.norm(b)
    a, b = a / la, b / lb
    ma, mb = (m_chord, m_thick) if la >= lb else (m_thick, m_chord)
    out = np.array([q + np.sign((q - c) @ a) * ma * a + np.sign((q - c) @ b) * mb * b for q in Q])
    if la >= lb:
        return out, a, b, la / 2 + ma, lb / 2 + mb
    return out, b, a, lb / 2 + mb, la / 2 + ma


def cap_section(Q, skip_fwd, m_aft, m_thick):
    """a tip-cap section on a rectangular blade section Q (4 corners, cyclic): the chord from skip_fwd behind the
    forward chord end (the end with the larger x) to m_aft past the aft end, the thickness grown by m_thick each side.
    Returns (corners, chord unit pointing aft, thickness unit, centre)"""
    Q = np.asarray(Q, float)
    c = Q.mean(0)
    a, b = Q[1] - Q[0], Q[3] - Q[0]
    la, lb = np.linalg.norm(a), np.linalg.norm(b)
    a, b = a / la, b / lb
    if la < lb:
        a, b, la, lb = b, a, lb, la
    if a[0] > 0:
        a = -a                                   # chord unit pointing aft: u = -la/2 is the forward end
    u0, u1 = -la / 2 + skip_fwd, la / 2 + m_aft
    w = lb / 2 + m_thick
    out = np.array([c + a * u0 - b * w, c + a * u1 - b * w, c + a * u1 + b * w, c + a * u0 + b * w])
    return out, a, b, c + a * 0.5 * (u0 + u1)


class SweptHull:
    """where the hull-side geometry (static, Hull bone) reaches round the rotor of one fan through the whole fan yaw
    range: an occupancy grid in the rotor's (x, r) half plane (r = distance from the fan axis), dilated by `margin`.
    A rotor piece swept through a full turn occupies exactly its own (x, r) set, so a piece whose (x, r) samples stay
    out of the dilated grid clears the hull at every rotor angle and every yaw step (0.25 deg here; the rig check
    samples 15 deg x 3 yaws). The base model's fan-mount pylon reaches into the duct in front of the blade disc and
    comes within 2.7 mm (swept) of the slat tips' forward corners at yaw +-12."""

    def __init__(self, fan, co, tris, yaw_mats, xw=(-17.75, -16.55), rw=(0.55, 2.90), cell=0.002, margin=0.01,
                 step=0.003, pivot=None, max_yaw=12.0):
        self.fan, self.cell, self.margin, self.x0, self.r0 = fan, cell, margin, xw[0], rw[0]
        nx, nr = int(round((xw[1] - xw[0]) / cell)) + 1, int(round((rw[1] - rw[0]) / cell)) + 1
        occ = np.zeros((nx, nr), bool)
        co = np.asarray(co, float)
        tris = np.asarray(tris, np.int64)
        # triangles near the duct interior at rest (their bounding box within 1.2 m of the rotor's window)
        T = co[tris]
        lo, hi = T.min(1), T.max(1)
        keep = (hi[:, 0] > xw[0] - 1.2) & (lo[:, 0] < xw[1] + 1.2) & \
               (hi[:, 1] > fan.cy - rw[1] - 1.2) & (lo[:, 1] < fan.cy + rw[1] + 1.2) & \
               (hi[:, 2] > fan.cz - rw[1] - 1.2) & (lo[:, 2] < fan.cz + rw[1] + 1.2)
        T = T[keep]
        # coarse pass (5 cm samples, labelled by triangle): which triangles come near the window at any yaw
        Pc, lab = tri_samples(T, 0.05, labels=True)
        near = np.zeros(len(T), bool)
        for M in yaw_mats:
            Mi = np.linalg.inv(np.asarray(M))
            Q = Pc @ Mi[:3, :3].T + Mi[:3, 3]
            x, r = Q[:, 0], fan.rad(Q)
            m = (x >= xw[0] - 0.1) & (x <= xw[1] + 0.1) & (r <= rw[1] + 0.1)
            near[np.unique(lab[m])] = True
        P = tri_samples(T[near], step)
        # keep the samples that can reach the window: a yaw of 12 deg moves a point at most 0.21 x its distance from
        # the yaw axis (a vertical line through the Turbine bone head, about 2.3 m from the fan axis)
        if pivot is not None:
            x, r = P[:, 0], fan.rad(P)
            reach = 2.0 * math.sin(math.radians(max_yaw) / 2.0) * np.hypot(P[:, 0] - pivot[0], P[:, 1] - pivot[1]) + 0.02
            P = P[(x >= xw[0] - reach) & (x <= xw[1] + reach) & (r <= rw[1] + reach)]
        self.n_tris, self.n_samples = int(near.sum()), int(len(P))
        rmin = 9.0
        for M in yaw_mats:
            Mi = np.linalg.inv(np.asarray(M))
            Q = P @ Mi[:3, :3].T + Mi[:3, 3]
            x, r = Q[:, 0], fan.rad(Q)
            m = (x >= xw[0]) & (x <= xw[1]) & (r >= rw[0]) & (r <= rw[1])
            if m.any():
                occ[((x[m] - xw[0]) / cell).astype(int), ((r[m] - rw[0]) / cell).astype(int)] = True
                rmin = min(rmin, float(r[m].min()))
        self.occ = occ
        self.r_min = rmin
        k = int(math.ceil(margin / cell))
        pad = np.pad(occ, k)
        dil = np.zeros_like(occ)
        for dx in range(-k, k + 1):
            for dr in range(-k, k + 1):
                if dx * dx + dr * dr <= k * k:
                    dil |= pad[k + dx:k + dx + nx, k + dr:k + dr + nr]
        self.dil = dil
        self.occ_pts = np.argwhere(occ) * cell + np.array([xw[0], rw[0]])

    def xr(self, mesh):
        P = tri_samples(np.asarray(mesh.v, float)[np.array([list(f[:3]) for f in fan_tris(mesh)])], 0.003) \
            if mesh.f else np.zeros((0, 3))
        return np.c_[P[:, 0], self.fan.rad(P)] if len(P) else np.zeros((0, 2))

    def bad(self, mesh):
        V_ = np.asarray(mesh.v, float)
        if not len(V_) or float(self.fan.rad(V_).max()) < self.r_min - self.margin - 0.01:
            return False
        q = self.xr(mesh)
        ix = np.floor((q[:, 0] - self.x0) / self.cell).astype(int)
        ir = np.floor((q[:, 1] - self.r0) / self.cell).astype(int)
        m = (ix >= 0) & (ix < self.dil.shape[0]) & (ir >= 0) & (ir < self.dil.shape[1])
        return bool(self.dil[ix[m], ir[m]].any())

    def clearance(self, mesh, near=0.06):
        """smallest (x, r) distance from the mesh's samples to the hull's swept occupancy (cell accuracy)"""
        q = self.xr(mesh)
        if not len(q) or not len(self.occ_pts):
            return None
        lo, hi = self.occ_pts.min(0) - near, self.occ_pts.max(0) + near
        q = q[np.all((q >= lo) & (q <= hi), axis=1)]
        if not len(q):
            return round(near, 4)
        o = self.occ_pts[np.all((self.occ_pts >= q.min(0) - near) & (self.occ_pts <= q.max(0) + near), axis=1)]
        if not len(o):
            return round(near, 4)
        best = 9.0
        for k in range(0, len(q), 2000):
            d = np.sqrt(((q[k:k + 2000, None, :] - o[None, ::3, :]) ** 2).sum(-1)).min()
            best = min(best, float(d))
        return round(best, 4)


def fan_tris(mesh):
    out = []
    for f in mesh.f:
        for i in range(1, len(f) - 1):
            out.append((f[0], f[i], f[i + 1]))
    return out


def tri_samples(T, step, labels=False):
    """points on triangles T (n, 3, 3) no more than about `step` apart (labels: also the triangle index per point)"""
    out, lab = [], []
    for k, (a, b, c) in enumerate(T):
        n = max(1, int(math.ceil(max(np.linalg.norm(b - a), np.linalg.norm(c - a), np.linalg.norm(c - b)) / step)))
        i, j = np.meshgrid(np.arange(n + 1), np.arange(n + 1), indexing='ij')
        m = (i + j) <= n
        i, j = i[m] / n, j[m] / n
        out.append(a + i[:, None] * (b - a) + j[:, None] * (c - a))
        if labels:
            lab.append(np.full(len(i), k))
    P = np.concatenate(out) if out else np.zeros((0, 3))
    if labels:
        return P, (np.concatenate(lab) if lab else np.zeros(0, int))
    return P


def chamfer_prism(mesh, A, B, c, mat, kind):
    """closed prism between two 4-corner rings A and B (same cyclic order), every edge chamfered by c"""
    import bmesh
    bm = bmesh.new()
    va = [bm.verts.new(tuple(map(float, p))) for p in A]
    vb = [bm.verts.new(tuple(map(float, p))) for p in B]
    bm.faces.new(va)
    bm.faces.new(vb)
    for k in range(4):
        bm.faces.new((va[k], va[(k + 1) % 4], vb[(k + 1) % 4], vb[k]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    if c > 0:
        bmesh.ops.bevel(bm, geom=list(bm.edges), offset=c, segments=1, affect='EDGES', profile=0.5)
    mesh.from_bmesh(bm, np.eye(4), mat, kind)
    bm.free()


def revolve(mesh, fan, prof, nseg, mat, kind, phase=0.0, smooth=True):
    """closed ring solid round the fan axis: prof = closed (x, r) loop; nseg segments"""
    rings = []
    for (x, r) in prof:
        b = mesh.verts([fan.pt(x, phase + 360.0 * k / nseg, r) for k in range(nseg)])
        rings.append(list(range(b, b + nseg)))
    for k in range(len(rings)):
        mesh.bridge(rings[k], rings[(k + 1) % len(rings)], mat, smooth, kind)


def build_rotor_blades(fan, rotor, ship, K, log, checks):
    """blade-root collar ring + cuffs and the tip caps (or a tip shroud) on the rotor of one fan. checks: the rotor's
    piece tests (the housing at every spin angle + the duct clearance)"""
    RK = K['rotor']
    lg = log.setdefault('fan_' + fan.s, {}).setdefault('blades', {})
    bl = blade_sections(ship, fan)
    lg['base_blades'] = len(bl)
    lg['blade_face_flatness_max_mm'] = round(1000.0 * max(b['flat_err'] for b in bl), 3) if bl else None
    lg['blade_rho_root_tip'] = [round(bl[0]['rho_root'], 4), round(bl[0]['rho_tip'], 4)] if bl else None
    ax = np.array([1.0, 0.0, 0.0])
    CH = checks['rotor_blades']
    n0 = rotor.mesh.tris()
    # ---- collar ring round the hub (rust), rivets on its aft face
    CK_ = RK['collar']
    xa, xb = CK_['x']
    ri, ro, ch = CK_['r_in'], CK_['r_out'], CK_['ch']
    th_bl = [math.degrees(math.atan2(b['d'][2], fan.side * b['d'][1])) for b in bl]
    ph = th_bl[0] if th_bl else 0.0
    tmp = rotor.new()
    revolve(tmp, fan, [(xa, ri), (xa, ro - ch), (xa + ch, ro), (xb - ch, ro), (xb, ro - ch), (xb, ri)],
            CK_['seg'], CK_['mat'], 'blade_collar', phase=ph)
    nr = CK_['rivets']
    for k in range(nr):
        th = ph + (k + 0.5) * 360.0 / nr
        D.rivet(tmp, fan.pt(xa, th, CK_['rivet_r']), -ax, r=0.02, h=0.011)
    sw = checks.get('swept_hull')
    lg['collar'] = 0 if (sw is not None and sw.bad(tmp)) else int(rotor.accept(tmp, CH, 'blade_collar'))
    # ---- a clamp cuff on every slat where it leaves the collar
    CU = RK['cuffs']
    ncu = 0
    cuff_trees = []
    for b in bl:
        A, _, _, _, _ = inflate(blade_section(b, CU['rho'][0]), CU['m_chord'], CU['m_thick'])
        B, _, _, _, _ = inflate(blade_section(b, CU['rho'][1]), CU['m_chord'], CU['m_thick'])
        tmp = rotor.new()
        chamfer_prism(tmp, A, B, CU['ch'], CU['mat'], 'blade_cuff')
        ok = (sw is None or not sw.bad(tmp)) and rotor.accept(tmp, CH, 'blade_cuff')
        ncu += int(ok)
        if ok:
            cuff_trees.append(L.piece_tree(tmp))
    lg['cuffs'] = ncu
    lg['cuff_pairs_touching'] = sum(1 for i in range(len(cuff_trees)) for j in range(i + 1, len(cuff_trees))
                                    if cuff_trees[i].overlap(cuff_trees[j]))
    # ---- tips: a steel cap on every slat end (or one shroud band)
    r_max = RK['r_max']
    if RK['tips'] == 'shroud':
        SH = RK['shroud']
        (sxa, sxb), (sri, sro), sch = SH['x'], SH['r'], SH['ch']
        tmp = rotor.new()
        revolve(tmp, fan, [(sxa, sri), (sxa, sro - sch), (sxa + sch, sro), (sxb - sch, sro), (sxb, sro - sch), (sxb, sri)],
                SH['seg'], SH['mat'], 'blade_shroud', phase=ph)
        for k in range(SH['rivets']):
            D.rivet(tmp, fan.pt(sxa, ph + (k + 0.5) * 360.0 / SH['rivets'], 0.5 * (sri + sro)), -ax, r=0.016, h=0.009)
        sw = checks.get('swept_hull')
        lg['shroud'] = 0 if (sw is not None and sw.bad(tmp)) else int(rotor.accept(tmp, CH, 'blade_shroud'))
    else:
        CP = RK['caps']
        ncap, nriv, e_used = 0, 0, []
        cap_trees = []
        sw = checks.get('swept_hull')
        for b in bl:
            rho_a = b['rho_tip'] - CP['len']
            # the cap wraps the slat's end from skip_fwd behind its forward edge to past its aft edge (the forward
            # part stays bare: the fan-mount pylon passes 2.7 mm in front of it at full yaw)
            A, _, _, _ = cap_section(blade_section(b, rho_a), CP['skip_fwd'], CP['m_chord'], CP['m_thick'])
            Bt, cu, tu, cc = cap_section(b['tip'], CP['skip_fwd'], CP['m_chord'], CP['m_thick'])
            # the cap reaches past the slat's end face as far as the clearance allows (corners <= r_max)
            e = CP['ext']
            while e > 0.0 and float(fan.rad(Bt + b['d'] * e).max()) > r_max:
                e -= 0.0005
            e = max(e, 0.0)
            B = Bt + b['d'] * e
            e_used.append(e)
            tmp = rotor.new()
            chamfer_prism(tmp, A, B, CP['ch'], CP['mat'], 'blade_tip_cap')
            if CP.get('rivet'):
                n_aft = tu if tu[0] < 0 else -tu
                ht = 0.5 * float(np.linalg.norm(Bt[3] - Bt[0]))
                cm = cap_section(blade_section(b, 0.5 * (rho_a + b['rho_tip'])), CP['skip_fwd'], CP['m_chord'],
                                 CP['m_thick'])[3]
                D.rivet(tmp, cm + n_aft * ht, n_aft, r=0.016, h=0.009)
                nriv += 1
            if sw is not None and sw.bad(tmp):
                st = rotor.stats.setdefault('blade_tip_cap', {'built': 0})
                st['hull_swept_at_yaw'] = st.get('hull_swept_at_yaw', 0) + 1
                continue
            ok = rotor.accept(tmp, CH, 'blade_tip_cap')
            ncap += int(ok)
            if ok:
                cap_trees.append(L.piece_tree(tmp))
        lg['tip_caps'] = ncap
        lg['tip_cap_rivets'] = nriv
        lg['tip_cap_end_past_slat_mm'] = [round(1000 * min(e_used), 1), round(1000 * max(e_used), 1)] if e_used else None
        lg['cap_pairs_touching'] = sum(1 for i in range(len(cap_trees)) for j in range(i + 1, len(cap_trees))
                                       if cap_trees[i].overlap(cap_trees[j]))
    # ---- clearance to the duct wall (radius of every new vertex; the wall's inscribed radius over the blade x range)
    P = np.asarray(rotor.mesh.v, float)
    rr = fan.rad(P)
    inside = (P[:, 0] > -17.9) & (P[:, 0] < -16.2)
    lg['max_vertex_radius_m'] = round(float(rr[inside].max()), 4) if inside.any() else None
    lg['duct_wall_inscribed_r_m'] = RK['duct_r_min']
    lg['min_clearance_to_duct_m'] = round(RK['duct_r_min'] - float(rr[inside].max()), 4) if inside.any() else None
    sw = checks.get('swept_hull')
    if sw is not None:
        lg['hull_swept'] = dict(yaw_steps=checks.get('swept_yaws'), tris=sw.n_tris, samples=sw.n_samples,
                                r_min_reached=round(sw.r_min, 4), margin_m=sw.margin,
                                min_clearance_rotor_details_m=sw.clearance(rotor.mesh))
    lg['tris_added'] = rotor.mesh.tris() - n0
    lg['stats'] = {k: v for k, v in rotor.stats.items() if k.startswith('blade_')}
