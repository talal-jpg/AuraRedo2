"""Zone 6: the stern (round 3): transom, the ship's own raised transom panels, the fan mounts (pylons, struts) and the
rudder. Bone Hull for the transom and the mounts, bone Rudder for the rudder.

Transom: a 4 cm chart of the flat aft face (x -16.18) seen from straight behind; a cell is free when the first thing a
ray from behind meets is that flat face (not the raised panels, the rudder, the fans or the pipes) and it keeps clear of
the rudder's swing (|y| >= 0.85) and of the PA_Airship stern box tops (|y| > 3.15 above z 1.95). Plates are laid in
rows like zone 1 (largest free rectangle per candidate, then a gap fill), with the approved layers; one upper machinery
bay each side (two housings, a valve, a riser into a gland). The raised panels get a riveted rust strap and corner
rivets (they read as armour blocks, not as hatches).
Rudder: on both flat faces, a riveted dark edge band along the aft edges, horizontal frame ribs, plates between them
(rust family), layers; the tiller bar gets two clamp bands. Details keep to x < -16.75, so they never swing into the
transom (rudder +-30 deg).
Mounts: riveted rust straps along the top and bottom of the pylons' long faces, frame ribs between them, a patch;
clamp bands on the struts. Kept below the PA box tops on the pylon (walkable) and off the fans' yaw sweep.
"""
import math, random
import numpy as np
from mathutils import Vector as V
import detail_common as D
from detail_flank import wchoice
import detail_z6_lib as L

X_FLAT = (-16.21, -16.15)


# ================================================================== transom
class Transom:
    X_PA = -16.192
    def __init__(self, ship, geo, step=0.04):
        self.skin = ship.surface(ship.p_island == 392)
        allb = geo.bvh(geo.keep)
        self.ys = np.arange(-4.5, 4.5001, step)
        self.zs = np.arange(-3.1, 2.9501, step)
        self.step = step
        ny, nz = len(self.ys), len(self.zs)
        self.cls = np.full((nz, ny), ' ', dtype='<U1')
        self.x = np.full((nz, ny), np.nan)
        for i, z in enumerate(self.zs):
            for j, y in enumerate(self.ys):
                r = self.skin.ray((-30.0, y, z), (1.0, 0.0, 0.0), 40.0)
                if r is None:
                    continue
                h = allb.ray_cast(V((-30.0, y, z)), V((1.0, 0.0, 0.0)), 40.0)
                x = r[0][0]
                self.x[i, j] = x
                if h[0] is not None and h[3] < r[3] - 0.003:
                    c = '#'
                elif r[4][0] > -0.97:
                    c = '/'
                elif x < -16.35:
                    c = 'c'
                elif x < -16.25:
                    c = 'b'
                elif X_FLAT[0] <= x <= X_FLAT[1]:
                    c = '.'
                else:
                    c = 'r'
                self.cls[i, j] = c
        Y, Zg = np.meshgrid(self.ys, self.zs)
        flat = self.cls == '.'
        ok = flat & (np.abs(Y) >= 0.62) & ~((np.abs(Y) > 3.15) & (Zg > 1.95)) & (Zg <= 2.78)
        er = ok.copy()                                  # keep one cell (4 cm) from anything that is not the flat face
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                er &= np.roll(np.roll(flat, di, 0), dj, 1)
        er[0, :] = er[-1, :] = er[:, 0] = er[:, -1] = False
        self.free = er

    def fn(self, y0, z0):
        def f(u, v):
            r = self.skin.ray((-30.0, y0 + u, z0 + v), (1.0, 0.0, 0.0), 40.0)
            if r is None or r[4][0] > -0.97:
                return None
            # PA_Airship's stern boxes start at x -16.20 (1.6 cm behind the flat transom at -16.184): keep every detail
            # vertex aft of that plane, so nothing stands 'above a box top' inside a box footprint
            p = r[0].copy()
            p[0] = min(p[0], self.X_PA)
            return p, r[4]
        return f

    def rect_m(self, rc):
        i0, i1, j0, j1 = rc
        return self.ys[j0], self.ys[j1 - 1], self.zs[i0], self.zs[i1 - 1]

    def take(self, y0, y1, z0, z1, pad):
        jm = (self.ys >= y0 - pad) & (self.ys <= y1 + pad)
        im = (self.zs >= z0 - pad) & (self.zs <= z1 + pad)
        self.free[np.ix_(im, jm)] = False

    def window(self, y0, y1, z0, z1):
        j0 = int(np.searchsorted(self.ys, y0 - 1e-6)); j1 = int(np.searchsorted(self.ys, y1 + 1e-6))
        i0 = int(np.searchsorted(self.zs, z0 - 1e-6)); i1 = int(np.searchsorted(self.zs, z1 + 1e-6))
        return i0, i1, j0, j1

    def panels(self, code):
        """bounding boxes (y0, y1, z0, z1) of the raised panels of one class, per side"""
        out = []
        Y, Zg = np.meshgrid(self.ys, self.zs)
        m = self.cls == code
        for sgn in (-1, 1):
            mm = m & (np.sign(Y) == sgn) & (np.abs(Y) > 0.8)
            if mm.sum() < 20:
                continue
            out.append((float(Y[mm].min()), float(Y[mm].max()), float(Zg[mm].min()), float(Zg[mm].max())))
        return out


def build_transom(tr, part, K, rng, log, CH):
    PL, RV, TK = K['plate'], K['rivet'], K['transom']
    G2 = PL['gap'] + PL['t'] + K['layer']
    lg = log.setdefault('transom', {})
    lg['free_cells'] = int(tr.free.sum())
    lg['free_area_m2'] = round(float(tr.free.sum()) * tr.step ** 2, 1)
    seam = K['seam']
    # ---- review fix 2026-11-28: no dark bays with square lids on the transom (from the chase camera the pair read as
    #      a face's eyes / cabin windows). One side gets a proud horizontal pipe header under the deck edge, the other a
    #      vertical riser pair down its outboard column: different content per side. Their strips stay plate-free.
    bays = []
    pipes = []
    for pk, spec in sorted(TK.get('pipes', {}).items()):
        y0, y1, z0, z1 = spec['strip']
        rc = tr.window(y0, y1, z0, z1)
        if not tr.free[rc[0]:rc[1], rc[2]:rc[3]].any():
            lg.setdefault('pipes_skipped', []).append(pk)
            continue
        pipes.append((pk, spec))
        tr.take(y0, y1, z0, z1, 0.0)
    # ---- plates: greedy largest free rectangle, one side at a time with its own random stream (so the two sides do
    #      not mirror), split into plates of zone 1's sizes (rows of 0.8 .. 1.5 m, plates 0.7 .. 1.3 m wide, seams
    #      staggered row to row). Narrow columns (beside the rudder and the raised panels) get one or two tall calm
    #      plates with a riveted rust rib between them, not a stack of small tiles; leftovers under min_w x min_h stay
    #      bare (zone 4's filler rule: at least 0.5 x 0.38 m)
    plates = []
    jmid = int(np.searchsorted(tr.ys, 0.0))
    min_w, min_h = TK.get('min_w', 0.3), TK.get('min_h', 0.24)
    for sgn in (1, -1):
        rs = random.Random(K['seed'] + (31 if sgn > 0 else 57))
        ja, jb = (jmid, tr.free.shape[1]) if sgn > 0 else (0, jmid)
        for _ in range(200):
            rc = L.maxrect(tr.free, 0, tr.free.shape[0], ja, jb)
            if rc is None:
                break
            a, b, c, d = tr.rect_m(rc)
            W, H = b - a, d - c
            if W < min_w or H < min_h:
                tr.free[rc[0]:rc[1], rc[2]:rc[3]] = False
                continue
            column = W < TK.get('col_w', 0.0)
            if column:
                nh = 1 if H < TK['col_split'] else 2
                cut = c + H * rs.uniform(0.38, 0.62)
                hs = [c, d + seam] if nh == 1 else [c, cut + seam / 2, d + seam]
                ws_all = [[a, b + seam]]
            else:
                nh = max(1, int(math.ceil(H / rs.uniform(*TK['row_h']))))
                hs = list(np.linspace(c, d + seam, nh + 1))
                ws_all = []
                for r_ in range(nh):
                    nw = max(1, int(math.ceil(W / rs.uniform(*TK['w']))))
                    if nw == 1:
                        ws = [a, b + seam]
                    else:
                        ws = list(np.linspace(a, b + seam, nw + 1))
                        jit = (W / nw) * 0.25
                        for q in range(1, nw):
                            ws[q] += rs.uniform(-jit, jit)
                    ws_all.append(ws)
            for r_ in range(nh):
                z0, z1 = hs[r_], hs[r_ + 1] - seam
                ws = ws_all[0] if column else ws_all[r_]
                for q in range(len(ws) - 1):
                    y0, y1 = ws[q], ws[q + 1] - seam
                    if y1 - y0 >= min_w and z1 - z0 >= min_h:
                        plates.append(dict(y0=y0, y1=y1, z0=z0, z1=z1, kind='plate', column=column, side=sgn))
            tr.take(a, b, c, d, seam)
    for p in plates:
        p['W'], p['H'] = p['y1'] - p['y0'], p['z1'] - p['z0']
        p['mat'] = wchoice(rng, K['yellows'])
        cut = rng.uniform(*PL['cut'])
        p['corners'] = tuple(int(rng.random() < PL['cut_p']) for _ in range(4))
        p['cut'] = min(cut, 0.3 * min(p['W'], p['H'])) if any(p['corners']) else 0.0
    # layers: heavy rust armour on about 12 % of the plates, then slotted plates, picture frames, patches; the rest calm
    order = list(plates)
    rng.shuffle(order)
    n_arm = max(1, int(round(TK['armour_p'] * len(plates))))
    nslot = 0
    for p in order:
        if p.get('column'):
            continue
        if n_arm and p['W'] >= 0.5 and p['H'] >= 0.36:
            p['armour'] = True
            n_arm -= 1
        elif nslot < TK['slots'] and p['W'] >= 0.5 and p['H'] >= 0.5:
            p['slot'] = True
            nslot += 1
        elif p['W'] >= TK.get('frame_min_w', 0.5) and p['H'] >= 0.6 and rng.random() < TK['frame_p']:
            p['frame'] = 'paint_ochre' if p['mat'] == 'paint_yellow' else 'paint_yellow'
        elif p['W'] >= TK.get('patch_min_w', 0.42) and p['H'] >= 0.4 and rng.random() < TK['patch_p']:
            p['patch'] = True
    built = dict(base=0, armour=0, frames=0, patches=0, slotted=0)
    for p in plates:
        tmp = part.new()
        f = tr.fn(p['y0'], p['z0'])
        us = D.grid_coords(0.0, p['W'], 0.6, p['cut'])
        vs = D.grid_coords(0.0, p['H'], 0.4, p['cut'])
        arm = p.get('armour')
        corners = p['corners'] if p['cut'] > 0 else (0, 0, 0, 0)
        top_fn, ok = D.solid_plate(tmp, f, us, vs, PL['gap'], 0.065 if arm else PL['t'], PL['bevel'],
                                   'rust_red' if arm else p['mat'], corners=corners, kind='plate_armour' if arm else 'plate')
        if not ok:
            continue
        pts = D.corner_pts(us, vs, RV['inset'], p['cut'], corners)
        if arm:
            k = max(1, int(round((p['W'] - 2 * RV['inset']) / RV['spacing'])))
            pts += [(RV['inset'] + (p['W'] - 2 * RV['inset']) * i / k, p['H'] - RV['inset']) for i in range(1, k)]
        if p['W'] * p['H'] >= 0.12:
            D.rivet_row(tmp, top_fn, pts, r=RV['r'], h=RV['h'])
        if not part.accept(tmp, CH, 'transom_plate'):
            continue
        built['armour' if arm else 'base'] += 1
        p['ok'] = True
        if p.get('frame'):
            e = 0.09
            Wf, Hf = p['W'] - 2 * e, p['H'] - 2 * e
            tmp = part.new()
            fr = lambda u, v, f=f: f(u + e, v + e)
            D.picture_frame(tmp, fr, Wf, Hf, 0.075, G2, 0.035, 0.012, p['frame'], kind='frame')
            top = lambda u, v, fr=fr: (lambda r: None if r is None else (r[0] + r[1] * (G2 + 0.035), r[1]))(fr(u, v))
            D.rivet_row(tmp, top, D.corner_pts(np.array([0.0, Wf]), np.array([0.0, Hf]), 0.0375), r=RV['r'], h=RV['h'])
            built['frames'] += int(part.accept(tmp, CH, 'transom_frame'))
        elif p.get('patch'):
            w = min(rng.uniform(0.4, 0.7), p['W'] - 0.12)
            h = min(rng.uniform(0.3, 0.6), p['H'] - 0.14)
            if TK.get('patch_low'):
                h = min(h, 0.34)                     # low and wide, on the plate's bottom edge at one end (off centre)
            if w >= 0.3 and h >= 0.22:
                u0, v0 = rng.uniform(0.06, max(0.061, p['W'] - w - 0.06)), rng.uniform(0.07, p['H'] - h - 0.07)
                if TK.get('patch_low'):
                    u0, v0 = (0.06 if u0 < (p['W'] - w) / 2 else p['W'] - w - 0.06), 0.07
                tmp = part.new()
                fp = lambda u, v, f=f, u0=u0, v0=v0: f(u0 + u, v0 + v)
                us2, vs2 = D.grid_coords(0.0, w, 0.6), D.grid_coords(0.0, h, 0.4)
                t2, ok2 = D.solid_plate(tmp, fp, us2, vs2, G2, 0.04, 0.012, wchoice(rng, (('rust_red', 0.7), ('paint_ochre', 0.3))),
                                        kind='patch')
                if ok2:
                    D.rivet_row(tmp, t2, D.corner_pts(us2, vs2, 0.05), r=RV['r'], h=RV['h'])
                    built['patches'] += int(part.accept(tmp, CH, 'transom_patch'))
        elif p.get('slot'):
            sw, sh = min(rng.uniform(0.45, 0.8), p['W'] - 0.12), min(rng.uniform(0.32, 0.42), p['H'] - 0.12)
            u0, v0 = (p['W'] - sw) / 2, (p['H'] - sh) / 2
            tmp = part.new()
            fs = lambda u, v, f=f, u0=u0, v0=v0: f(u0 + u, v0 + v)
            if D.slotted_plate(tmp, fs, sw, sh, G2, 0.035, 0.01, p['mat'], n_slots=2 if sw < 0.6 else 3, slot_w=0.05, ang=58.0):
                top = lambda u, v, fs=fs: (lambda r: None if r is None else (r[0] + r[1] * (G2 + 0.048), r[1]))(fs(u, v))
                D.rivet_row(tmp, top, [(0.045, 0.037), (sw - 0.045, 0.037), (0.045, sh - 0.037), (sw - 0.045, sh - 0.037)],
                            r=0.018, h=0.01)
                built['slotted'] += int(part.accept(tmp, CH, 'transom_slotted'))
    calm = [p for p in plates if p.get('ok') and not (p.get('armour') or p.get('frame') or p.get('patch') or p.get('slot'))]
    area = sum(p['W'] * p['H'] for p in plates if p.get('ok'))
    lg['plate_dims'] = [(round(p['y0'], 2), round(p['z0'], 2), round(p['W'], 2), round(p['H'], 2)) for p in plates]
    lg['plates'] = dict(built, planned=len(plates), plate_area_m2=round(area, 1),
                        calm_share_of_area=round(sum(p['W'] * p['H'] for p in calm) / max(area, 1e-6), 2))
    # frame ribs over the seams between neighbouring plates (side by side: vertical rib; stacked: horizontal rib)
    nb = 0
    ok_p = [p for p in plates if p.get('ok') and not p.get('armour')]
    for a_ in ok_p:
        for b_ in ok_p:
            gy = b_['y0'] - a_['y1']
            gz = b_['z0'] - a_['z1']
            if 0 < gy < 0.08:
                z0, z1 = max(a_['z0'], b_['z0']) - 0.02, min(a_['z1'], b_['z1']) + 0.02
                if z1 - z0 < 0.35 or rng.random() > TK['batten_p']:
                    continue
                w = 0.12
                f, us, vs = tr.fn(a_['y1'] + gy / 2 - w / 2, z0), np.array([0.0, w]), D.grid_coords(0.0, z1 - z0, 0.4)
                L_, along_u = z1 - z0, False
            elif 0 < gz < 0.08:
                y0, y1 = max(a_['y0'], b_['y0']) - 0.02, min(a_['y1'], b_['y1']) + 0.02
                force = a_.get('column') and b_.get('column')
                if y1 - y0 < (0.3 if force else 0.35) or (rng.random() > TK['batten_p'] and not force):
                    continue
                w = 0.12
                f, us, vs = tr.fn(y0, a_['z1'] + gz / 2 - w / 2), D.grid_coords(0.0, y1 - y0, 0.4), np.array([0.0, w])
                L_, along_u = y1 - y0, True
            else:
                continue
            tmp = part.new()
            top_fn, ok = D.solid_plate(tmp, f, us, vs, G2, 0.05, 0.012, 'rust_red', kind='batten')
            if ok:
                k = max(1, int(round((L_ - 0.12) / RV['spacing'])))
                pts = [(0.06 + (L_ - 0.12) * i / k, w / 2) if along_u else (w / 2, 0.06 + (L_ - 0.12) * i / k) for i in range(k + 1)]
                D.rivet_row(tmp, top_fn, pts, r=RV['r'], h=RV['h'])
                nb += int(part.accept(tmp, CH, 'transom_batten'))
    lg['battens'] = nb
    # ---- the upper bays: riveted rust frame, dark floor, two housings joined by a valve pipe, a riser into a gland
    nbay = 0
    for (y0, y1, z0, z1) in bays:
        W, H = y1 - y0, z1 - z0
        f = tr.fn(y0, z0)
        tmp = part.new()
        rim = 0.08
        D.picture_frame(tmp, f, W, H, rim, PL['gap'], 0.05, 0.014, 'rust_red', kind='bay')
        D.solid_plate(tmp, f, D.grid_coords(rim + 0.008, W - rim - 0.008, 0.6), D.grid_coords(rim + 0.008, H - rim - 0.008, 0.4),
                      PL['gap'], 0.012, 0.003, 'dark_metal', kind='bay')
        top = lambda u, v, f=f: (lambda r: None if r is None else (r[0] + r[1] * (PL['gap'] + 0.05), r[1]))(f(u, v))
        D.rivet_row(tmp, top, D.corner_pts(np.array([0.0, W]), np.array([0.0, H]), rim / 2) + [(W / 2, rim / 2), (W / 2, H - rim / 2)],
                    r=RV['r'], h=RV['h'])
        floor = PL['gap'] + 0.014
        iu0, iu1 = rim + 0.05, W - rim - 0.05
        iv0, iv1 = rim + 0.05, H - rim - 0.05
        hw = min(0.5, (iu1 - iu0 - 0.3) / 2)
        hh = min(0.38, iv1 - iv0 - 0.06)
        c1 = (iu0 + 0.05 + hw / 2, (iv0 + iv1) / 2 - 0.02)
        c2 = (iu1 - 0.05 - hw / 2, (iv0 + iv1) / 2 + 0.01)
        q1, q2 = f(*c1), f(*c2)
        if q1 is None or q2 is None or hw < 0.25:
            continue
        uh = np.array([0.0, 1.0, 0.0])
        e1 = D.housing(tmp, q1[0] + q1[1] * floor, q1[1], uh, hw, hh, 0.1, stubs=((1, -0.3),), r_stub=0.035)
        e2 = D.housing(tmp, q2[0] + q2[1] * floor, q2[1], uh, hw * 0.85, hh * 0.9, 0.1, stubs=((-1, 0.2),), r_stub=0.035)
        (a_, da), (b_, db) = e1[0], e2[0]
        P_, _ = D.pipe_run(tmp, [a_ - da * 0.01, a_ + da * 0.05, b_ + db * 0.05, b_ - db * 0.01], 0.035, 0.06, sides=8,
                           mat='brass', flange_at=(0.5,), kind='bay')
        mi = len(P_) // 2
        D.valve_body(tmp, P_[mi], D.unit(P_[mi + 1] - P_[mi - 1]), q1[1], 0.035)
        # riser from the first housing down through the lower frame into a gland below the bay
        ut = c1[0] - hw * 0.25
        qs = [f(ut, c1[1] - hh / 2 + 0.04), f(ut, rim * 0.5), f(ut, -0.12)]
        if all(q is not None for q in qs):
            dep = floor + 0.05
            path = [qs[0][0] + qs[0][1] * dep, qs[1][0] + qs[1][1] * (PL['gap'] + 0.05 + 0.04), qs[2][0] - qs[2][1] * 0.02]
            D.pipe_run(tmp, path, 0.03, 0.08, sides=8, mat='copper', kind='bay')
            D.gland(tmp, qs[2][0], qs[2][1], (0.0, 1.0, 0.0), 0.03, size=0.06)
        nbay += int(part.accept(tmp, CH, 'transom_bay'))
    lg['bays'] = dict(planned=len(bays), built=nbay)
    # ---- the pipe header (one side) and the riser pair (the other side), on bare skin in their reserved strips
    npipe = {}
    for pk, spec in pipes:
        tmp = part.new()
        okk = True
        for k_, (c_, r_, mat_) in enumerate(spec['runs']):
            if spec['kind'] == 'header':
                a_, b_ = (spec['span'][0], c_), (spec['span'][1], c_)
            else:
                a_, b_ = (c_, spec['span'][0]), (c_, spec['span'][1])
            last = k_ == len(spec['runs']) - 1
            okk &= transom_pipe(tr, tmp, a_, b_, r_, mat_, off=r_ + 0.045,
                                flange_at=() if last else (0.33, 0.68),
                                valve_at=0.5 if last else None, bonnet=np.array(spec['bonnet'], float))
        if okk:
            npipe[pk] = int(part.accept(tmp, CH, 'transom_pipes'))
        else:
            npipe[pk] = 'no surface'
    lg['pipes'] = npipe
    # ---- the ship's own raised panels: a riveted rust strap across, corner rivets (armour blocks, not hatches)
    npn = 0
    for code, x_top in (('b', -16.334), ('c', -16.36)):
        for (y0, y1, z0, z1) in tr.panels(code):
            if min(abs(y0), abs(y1)) < 0.85 and code == 'b':
                continue
            if code == 'c' and z1 - z0 > 1.2:
                continue                                    # the narrow uprights next to the rudder: rudder swing
            sk = 0.05
            y0, y1, z0, z1 = y0 + sk, y1 - sk, z0 + sk, z1 - sk
            if code == 'c':                                  # the long low panel: keep off the rudder strip
                y0, y1 = (max(y0, 0.95), y1) if y1 > 0 else (y0, min(y1, -0.95))
            W, H = y1 - y0, z1 - z0
            if W < 0.3 or H < 0.3:
                continue

            def fpan(u, v, y0=y0, z0=z0):
                r = tr.skin.ray((-30.0, y0 + u, z0 + v), (1.0, 0.0, 0.0), 40.0)
                if r is None or r[4][0] > -0.97 or r[0][0] > -16.25:
                    return None
                return r[0], r[4]
            tmp = part.new()
            if code == 'b':
                pass                                         # Talal's raised panels: corner rivets only
            elif TK.get('low_panel_strap', True):
                # review fix 2026-11-28: one horizontal riveted strap along the long low panel (the 2 + 2 vertical
                # straps read as teeth under the 'face')
                hs_ = 0.18
                fs = lambda u, v: fpan(u, (H - hs_) / 2 + v)
                top_fn, ok = D.solid_plate(tmp, fs, D.grid_coords(0.0, W, 0.4), np.array([0.0, hs_]), 0.012, 0.045, 0.012,
                                           'rust_red', kind='strap')
                if ok:
                    k = max(1, int(round((W - 0.12) / RV['spacing'])))
                    D.rivet_row(tmp, top_fn, [(0.06 + (W - 0.12) * i / k, hs_ / 2) for i in range(k + 1)], r=RV['r'], h=RV['h'])
            top0 = lambda u, v: (lambda r: None if r is None else (r[0] + r[1] * 0.0, r[1]))(fpan(u, v))
            D.rivet_row(tmp, top0, D.corner_pts(np.array([0.0, W]), np.array([0.0, H]), 0.06),
                        r=RV['r'], h=RV['h'])
            npn += int(part.accept(tmp, CH, 'panel_strap'))
    lg['panel_straps'] = npn


def transom_pipe(tr, tmp, yz_a, yz_b, r, mat, off, clamp_step=0.55, flange_at=(), valve_at=None, bonnet=None):
    """a pipe on the flat transom from (y, z) a to b, `off` (centre) off the skin, diving into a gland at each end,
    clamps every ~0.55 m, flanges at `flange_at`, an inline valve at `valve_at` with its bonnet toward `bonnet`.
    Everything stays aft of the PA stern boxes' aft face (x -16.200): tr.fn gives surface points at x -16.192, so the
    glands' backs and the clamp feet stop 0.9 cm further aft (1.7 cm off the flat transom at -16.184)"""
    f = tr.fn(0.0, 0.0)

    def at(s_):
        y = yz_a[0] + (yz_b[0] - yz_a[0]) * s_
        z = yz_a[1] + (yz_b[1] - yz_a[1]) * s_
        q = f(y, z)
        return None if q is None else (np.asarray(q[0], float), D.unit(np.asarray(q[1], float)))
    qa, qb = at(0.0), at(1.0)
    if qa is None or qb is None:
        return False
    L_ = float(np.hypot(yz_b[0] - yz_a[0], yz_b[1] - yz_a[1]))
    k = max(2, int(L_ / 0.3))
    mids = []
    for i in range(k + 1):
        q = at(i / k)
        if q is None:
            return False
        mids.append(q[0] + q[1] * off)
    n = qa[1]
    path = [qa[0] + n * 0.014] + mids + [qb[0] + qb[1] * 0.014]
    D.pipe_run(tmp, path, r, 0.07, sides=8, mat=mat, flange_at=flange_at, kind='pipe')
    for q in (qa, qb):
        D.gland(tmp, q[0] + q[1] * 0.009, q[1], (0.0, 0.0, 1.0) if abs(yz_b[1] - yz_a[1]) < 1e-6 else (0.0, 1.0, 0.0), r,
                size=max(0.07, r * 2.4))
    t = D.unit(mids[-1] - mids[0])
    nc = max(2, int(round((L_ - 0.3) / clamp_step)))
    for i in range(1, nc):
        q = at(0.15 / L_ + (1 - 0.3 / L_) * i / nc)
        if q is not None:
            D.clamp(tmp, q[0] + q[1] * off, t, r, q[0] + q[1] * 0.019, q[1])
    if valve_at is not None:
        q = at(valve_at)
        if q is not None:
            tv = t if bonnet is None or np.dot(np.cross(t, q[1]), bonnet) > 0 else -t
            D.valve_body(tmp, q[0] + q[1] * off, tv, q[1], r)
    return True


# ================================================================== fan mounts (bone Hull)
def build_mounts(ship, geo, part, K, rng, log, CH):
    RV = K['rivet']
    lg = log.setdefault('mounts', {})
    allb = geo.bvh(geo.keep)
    for s in ('L', 'R'):
        for i, r in ship.islands.items():
            if r['part'] != 'FanMount_' + s:
                continue
            P = ship.island_verts([i])
            if r['piece'] == 'pylon':
                lg.setdefault('pylon_faces', 0)
                lg['pylon_faces'] += pylon_details(P, i, part, allb, K, rng, lg, CH)
            else:
                lg.setdefault('strut_bands', 0)
                lg['strut_bands'] += strut_details(P, part, K, CH)


def pylon_details(P, isl, part, allb, K, rng, lg, CH):
    """the pylon is a box beam (2.4 x 2.8 m plan, 1.6 m tall): riveted straps along the top and bottom of its two long
    vertical faces where they are in the open (not inside the hull or the fan), frame ribs between, one patch"""
    RV = K['rivet']
    P = np.asarray(P)
    bot = P[np.argsort(P[:, 2])[:4]]
    top = P[np.argsort(P[:, 2])[4:]]
    cen = P.mean(0)
    n_built = 0
    # the four vertical faces: pairs of bottom corners; keep the two longest that are not at the ends
    bc = bot[np.argsort(np.arctan2(bot[:, 1] - cen[1], bot[:, 0] - cen[0]))]
    faces = []
    for k in range(4):
        a, b = bc[k], bc[(k + 1) % 4]
        faces.append((np.linalg.norm(b[:2] - a[:2]), a, b))
    faces.sort(key=lambda q: -q[0])
    for Lf, a, b in faces[:2]:
        ta = top[np.argmin(np.linalg.norm(top[:, :2] - a[:2], axis=1))]
        tb = top[np.argmin(np.linalg.norm(top[:, :2] - b[:2], axis=1))]
        t = D.unit(b - a)
        n = D.unit(np.cross(t, ta - a))
        if n @ (a - cen) < 0:
            n = -n
        Hf = float(np.linalg.norm(ta - a))

        def fface(u, v, a=a, b=b, ta=ta, tb=tb, Lf=Lf, Hf=Hf, n=n):
            s, w = u / Lf, v / Hf
            return (1 - s) * (1 - w) * a + s * (1 - w) * b + s * w * tb + (1 - s) * w * ta, n
        # free run along the face (mid height and near top / bottom): nothing in front within 0.3 m
        us = np.arange(0.05, Lf - 0.05, 0.05)
        okv = []
        for u in us:
            good = True
            for v in (0.15, Hf / 2, Hf - 0.25):
                p, _ = fface(u, v)
                o = p + n * 0.3
                h = allb.ray_cast(V(o), V(-n), 0.4)
                if h[0] is None or abs(h[3] - 0.3) > 0.01:
                    good = False
                    break
            okv.append(good)
        okv = np.array(okv)
        if not okv.any():
            continue
        best, cur = None, None
        for k, g in enumerate(okv):
            if g:
                cur = (cur[0], k) if cur else (k, k)
                if best is None or cur[1] - cur[0] > best[1] - best[0]:
                    best = cur
            else:
                cur = None
        u0, u1 = us[best[0]] + 0.04, us[best[1]] - 0.04
        if u1 - u0 < 0.6:
            continue
        W = u1 - u0
        f = lambda u, v, u0=u0: fface(u0 + u, v)
        tmp = part.new()
        for (v0, v1) in ((0.07, 0.25), (Hf - 0.36, Hf - 0.18)):
            fs = lambda u, v, v0=v0: f(u, v0 + v)
            top_fn, ok = D.solid_plate(tmp, fs, D.grid_coords(0.0, W, 0.6), np.array([0.0, v1 - v0]), 0.012, 0.045, 0.012,
                                       'rust_red', kind='strap')
            if ok:
                k = max(1, int(round((W - 0.1) / RV['spacing'])))
                D.rivet_row(tmp, top_fn, [(0.05 + (W - 0.1) * i / k, (v1 - v0) / 2) for i in range(k + 1)], r=RV['r'], h=RV['h'])
        nseg = max(1, int(round(W / 0.9)))
        for k in range(1, nseg):
            uc = W * k / nseg
            fs = lambda u, v, uc=uc: f(uc - 0.06 + u, 0.25 + 0.008 + v)
            Hr = Hf - 0.36 - 0.25 - 0.016
            top_fn, ok = D.solid_plate(tmp, fs, np.array([0.0, 0.12]), D.grid_coords(0.0, Hr, 0.4), 0.012, 0.045, 0.012,
                                       'rust_red', kind='rib')
            if ok:
                D.rivet_row(tmp, top_fn, [(0.06, 0.08), (0.06, Hr / 2), (0.06, Hr - 0.08)], r=RV['r'], h=RV['h'])
        if nseg >= 2:
            k = rng.randrange(nseg)
            pw = W / nseg - 0.36
            if pw > 0.3:
                fs = lambda u, v, k=k: f(W * k / nseg + 0.18 + u, 0.25 + 0.2 + v)
                ph = Hf - 0.36 - 0.25 - 0.4
                if ph > 0.25:
                    top_fn, ok = D.solid_plate(tmp, fs, D.grid_coords(0.0, pw, 0.6), D.grid_coords(0.0, ph, 0.4), 0.012, 0.04,
                                               0.012, 'machinery', kind='patch')
                    if ok:
                        D.rivet_row(tmp, top_fn, D.corner_pts(np.array([0.0, pw]), np.array([0.0, ph]), 0.05), r=RV['r'],
                                    h=RV['h'])
        n_built += int(part.accept(tmp, CH, 'pylon'))
    return n_built


def strut_details(P, part, K, CH):
    """clamp bands round the strut beam (8 vertices: two end quads) at 30 % and 62 % of its length, two rivets per side"""
    P = np.asarray(P)
    c = P.mean(0)
    # split the 8 vertices into the two end quads along the longest axis
    u, s_, vt = np.linalg.svd(P - c)
    ax = vt[0]
    proj = (P - c) @ ax
    A, B = P[proj < 0], P[proj >= 0]
    if len(A) != 4:
        return 0
    ca, cb = A.mean(0), B.mean(0)
    t = D.unit(cb - ca)
    e1 = D.unit((A[1] - A[0]) - t * ((A[1] - A[0]) @ t))
    e2 = np.cross(t, e1)
    h1 = max(abs((A - ca) @ e1)) + 0.025
    h2 = max(abs((A - ca) @ e2)) + 0.025
    n = 0
    for fr in (0.3, 0.62):
        q = ca + (cb - ca) * fr
        tmp = part.new()
        D.chamfer_box(tmp, D.frame_matrix(q, e1, e2, t), h1, h2, 0.05, 0.01, 'dark_metal', 'strut_band')
        for sg in (-1, 1):
            for k in (-1, 1):
                D.rivet(tmp, q + e1 * sg * h1 + e2 * k * h2 * 0.5, e1 * sg, r=0.018, h=0.01)
        n += int(part.accept(tmp, CH, 'strut_band'))
    return n


# ================================================================== rudder (bone Rudder)
def build_rudder(ship, part, K, rng, log, CH, CH_clamp):
    RV, RK, PL = K['rivet'], K['rudder'], K['plate']
    G2 = PL['gap'] + PL['t'] + K['layer']
    lg = log.setdefault('rudder', {})
    isl = [i for i, r in ship.islands.items() if r['part'] == 'Rudder' and r.get('piece') == 'blade']
    surf = ship.surface(np.isin(ship.p_island, isl))
    bv = ship.island_verts(isl)
    xc = RK['x_cut']
    slotted_done = {1: False, -1: False}
    for sgn in (1, -1):
        face = bv[np.abs(bv[:, 1] - sgn * bv[:, 1].max()) < 0.005]
        poly = face[:, [0, 2]]
        c = poly.mean(0)
        poly = poly[np.argsort(np.arctan2(poly[:, 1] - c[1], poly[:, 0] - c[0]))]
        yface = float(face[:, 1].mean())

        def g(a, b, sgn=sgn):
            """surface (a, b) = (-x, z) on this face"""
            r = surf.ray((-a, sgn * 2.0, b), (0.0, -sgn, 0.0), 3.0)
            if r is None or abs(r[4][1]) < 0.97:
                return None
            return r[0], r[4]
        keep = lambda q: xc - q[0]                         # x <= x_cut
        outer = L.clip_half(L.inset_poly(poly, RK['band'][0]), keep)
        inner = L.clip_half(L.inset_poly(poly, RK['band'][1]), keep)
        # edge band: one strip per polygon edge that is not on the cut line
        nband = 0
        if len(outer) == len(inner):
            for k in range(len(outer)):
                o0, o1 = outer[k - 1], outer[k]
                i0, i1 = inner[k - 1], inner[k]
                if abs(o0[0] - xc) < 1e-3 and abs(o1[0] - xc) < 1e-3:
                    continue
                td = D.unit(np.array([o1[0] - o0[0], o1[1] - o0[1], 0.0]))[:2]
                sh = 0.004
                Q = np.array([o0 + td * sh, o1 - td * sh, i1 - td * sh, i0 + td * sh])
                t0_, t1_ = RK['tiller']
                if Q[:, 1].min() < t1_ and Q[:, 1].max() > t0_:          # the tiller bar crosses this strip: split it
                    pieces = [L.clip_half(Q, lambda q: t0_ - q[1]), L.clip_half(Q, lambda q: q[1] - t1_)]
                else:
                    pieces = [Q]
                Lb = float(np.linalg.norm(o1 - o0))
                kk = max(1, int(round((Lb - 0.2) / 0.7)))
                mid0 = (np.asarray(o0) + np.asarray(i0)) / 2
                mid1 = (np.asarray(o1) + np.asarray(i1)) / 2
                rv = [mid0 + (mid1 - mid0) * (0.1 / Lb + (1 - 0.2 / Lb) * j / kk) for j in range(kk + 1)]
                for Qp in pieces:
                    if len(Qp) != 4:
                        continue
                    tmp = part.new()
                    q = [(-v_[0], v_[1]) for v_ in Qp]
                    top_fn, ok = D.solid_quad(tmp, g, q, PL['gap'], 0.045, 0.012, 'dark_metal', kind='rudder_band', cell=0.4)
                    if not ok:
                        continue
                    zlo, zhi = Qp[:, 1].min() + 0.06, Qp[:, 1].max() - 0.06
                    for m in rv:
                        if not (zlo <= m[1] <= zhi) or (t0_ - 0.06 < m[1] < t1_ + 0.06):
                            continue
                        r_ = g(-m[0], m[1])
                        if r_ is not None:
                            D.rivet(tmp, r_[0] + r_[1] * (PL['gap'] + 0.045), r_[1], r=RV['r'], h=RV['h'])
                    nband += int(part.accept(tmp, CH, 'rudder_band'))
        # review fix 2026-11-28: one diagonal riveted rust brace across the slab under the tiller bar (with fewer,
        # bigger plates and two ribs, so the faces stop reading as a panelled cabinet door). Layers keep off it.
        brace = None
        if RK.get('brace'):
            za_, zb_ = RK['brace']
            spa_, spb_ = L.x_span_at(inner, za_), L.x_span_at(inner, zb_)
            if spa_ is not None and spb_ is not None:
                A_ = np.array([-(min(spa_[1], xc - 0.02) - 0.16), za_])
                B_ = np.array([-(spb_[0] + 0.16), zb_])
                brace = (A_, B_)

        def near_brace(xlo, xhi, zlo, zhi, m=0.12):
            if brace is None:
                return False
            for t_ in np.linspace(0.0, 1.0, 25):
                c_ = brace[0] + (brace[1] - brace[0]) * t_
                if xlo - m <= -c_[0] <= xhi + m and zlo - m <= c_[1] <= zhi + m:
                    return True
            return False
        # horizontal frame ribs and the plates between them (the tiller bar is a rib of its own)
        zl = list(RK['ribs'])
        cuts = sorted(zl + [RK['tiller'][0], RK['tiller'][1]])
        zmin, zmax = inner[:, 1].min(), inner[:, 1].max()
        nrib = 0
        for z in zl:
            sp = L.x_span_at(inner, z)
            if sp is None:
                continue
            x0, x1 = sp[0], min(sp[1], xc - 0.02)
            if x1 - x0 < 0.3:
                continue
            tmp = part.new()
            w = 0.12
            q = [(-x1, z - w / 2), (-x0, z - w / 2), (-x0, z + w / 2), (-x1, z + w / 2)]
            top_fn, ok = D.solid_quad(tmp, g, q, G2, 0.05, 0.012, 'dark_metal', kind='rudder_rib', cell=0.4)
            if ok:
                kk = max(1, int(round((x1 - x0 - 0.12) / (2 * RV['spacing']))))
                for j in range(kk + 1):
                    r_ = g(-(x1 - 0.06 - (x1 - x0 - 0.12) * j / kk), z)
                    if r_ is not None:
                        D.rivet(tmp, r_[0] + r_[1] * (G2 + 0.05), r_[1], r=RV['r'], h=RV['h'])
                nrib += int(part.accept(tmp, CH, 'rudder_rib'))
        # cells between the ribs: horizontal slabs of the inner polygon, split into plates along x
        edges = [zmin] + [z for z in cuts if zmin < z < zmax] + [zmax]
        nplate = 0
        nlay = 0
        for za, zb in zip(edges[:-1], edges[1:]):
            if RK['tiller'][0] - 0.01 <= za and zb <= RK['tiller'][1] + 0.01:
                continue                                         # the tiller bar band
            z0, z1 = za + K['seam'] / 2, zb - K['seam'] / 2
            if z1 - z0 < 0.25:
                continue
            slab = L.clip_half(L.clip_half(inner, lambda q, z0=z0: q[1] - z0), lambda q, z1=z1: z1 - q[1])
            if len(slab) < 3:
                continue
            # split the slab at its own vertices' heights into trapezoids
            zs_ = sorted(set([z0, z1] + [float(v[1]) for v in slab if z0 + 0.02 < v[1] < z1 - 0.02]))
            for ta, tb in zip(zs_[:-1], zs_[1:]):
                if tb - ta < 0.2:
                    continue
                spa, spb = L.x_span_at(slab, ta + 1e-4), L.x_span_at(slab, tb - 1e-4)
                if spa is None or spb is None:
                    continue
                spa = (spa[0], min(spa[1], xc - K['seam']))
                spb = (spb[0], min(spb[1], xc - K['seam']))
                span = min(spa[1] - spa[0], spb[1] - spb[0])
                if span < 0.3:
                    continue
                npl = max(1, int(round(span / rng.uniform(*RK['w']))))
                for k in range(npl):
                    s0 = k / npl + (K['seam'] / 2 / span if k else 0.0)
                    s1 = (k + 1) / npl - (K['seam'] / 2 / span if k < npl - 1 else 0.0)
                    xa0, xa1 = spa[0] + (spa[1] - spa[0]) * s0, spa[0] + (spa[1] - spa[0]) * s1
                    xb0, xb1 = spb[0] + (spb[1] - spb[0]) * s0, spb[0] + (spb[1] - spb[0]) * s1
                    q = [(-xa1, ta), (-xa0, ta), (-xb0, tb), (-xb1, tb)]
                    mat = wchoice(rng, RK['mats'])
                    tmp = part.new()
                    top_fn, ok = D.solid_quad(tmp, g, q, PL['gap'], PL['t'], PL['bevel'], mat, kind='rudder_plate', cell=0.45)
                    if not ok:
                        continue
                    # corner rivets 7 cm in (bigger plates only)
                    for (qa, qb) in ([] if span * (tb - ta) / npl < 0.6 else ((q[0], q[2]), (q[1], q[3]), (q[2], q[0]), (q[3], q[1]))):
                        d_ = D.unit(np.array([qb[0] - qa[0], qb[1] - qa[1], 0.0]))[:2]
                        pp = (qa[0] + d_[0] * 0.1, qa[1] + d_[1] * 0.1)
                        r_ = g(*pp)
                        if r_ is not None:
                            D.rivet(tmp, r_[0] + r_[1] * (PL['gap'] + PL['t']), r_[1], r=RV['r'], h=RV['h'])
                    if not part.accept(tmp, CH, 'rudder_plate'):
                        continue
                    nplate += 1
                    # a layer on some: picture frame (rust rim) or a rust patch, in the rectangle common to top and bottom
                    xlo, xhi = max(xa0, xb0) + 0.09, min(xa1, xb1) - 0.09
                    Wl, Hl = xhi - xlo, (tb - ta) - 0.18
                    roll = rng.random()
                    if Wl < 0.35 or Hl < 0.3 or roll > RK['frame_p'] + RK['patch_p']:
                        continue
                    if near_brace(xlo, xhi, ta + 0.09, tb - 0.09):
                        continue
                    fl = lambda u, v, xhi=xhi, ta=ta: g(-xhi + u, ta + 0.09 + v)
                    tmp = part.new()
                    if (roll < RK['frame_p'] or RK.get('force_slot')) and Wl >= 0.6 and Hl >= 0.4 and not slotted_done[sgn]:
                        sw, sh = min(Wl, rng.uniform(0.6, 0.8)), min(Hl, rng.uniform(0.34, 0.42))
                        u0, v0 = (Wl - sw) / 2, (Hl - sh) / 2
                        fs = lambda u, v, u0=u0, v0=v0: fl(u0 + u, v0 + v)
                        if D.slotted_plate(tmp, fs, sw, sh, G2, 0.035, 0.01, mat, n_slots=3, slot_w=0.05, ang=58.0):
                            slotted_done[sgn] = True
                            top = lambda u, v, fs=fs: (lambda r: None if r is None else (r[0] + r[1] * (G2 + 0.048), r[1]))(fs(u, v))
                            D.rivet_row(tmp, top, [(0.045, 0.037), (sw - 0.045, 0.037), (0.045, sh - 0.037), (sw - 0.045, sh - 0.037)],
                                        r=0.018, h=0.01)
                    else:
                        w = min(Wl, rng.uniform(0.6, 1.0)); h = min(Hl, rng.uniform(0.45, 0.75))
                        if w < 0.5 or h < 0.36:
                            continue
                        u0, v0 = rng.uniform(0.0, Wl - w), rng.uniform(0.0, Hl - h)
                        fp = lambda u, v, u0=u0, v0=v0: fl(u0 + u, v0 + v)
                        us2, vs2 = D.grid_coords(0.0, w, 0.45), D.grid_coords(0.0, h, 0.45)
                        t2, ok2 = D.solid_plate(tmp, fp, us2, vs2, G2, 0.04, 0.012,
                                                'rust_red' if mat == 'rust_dark' else 'rust_dark', kind='patch')
                        if ok2:
                            D.rivet_row(tmp, t2, D.corner_pts(us2, vs2, 0.05), r=RV['r'], h=RV['h'])
                    nlay += int(part.accept(tmp, CH, 'rudder_layer'))
        nbr = 0
        if brace is not None:
            A_, B_ = brace
            d_ = D.unit(np.array([B_[0] - A_[0], B_[1] - A_[1], 0.0]))[:2]
            pv = np.array([-d_[1], d_[0]]) * 0.09
            q = [A_ - pv, B_ - pv, B_ + pv, A_ + pv]
            if L.poly_area(np.array(q)) < 0:
                q = q[::-1]
            tmp = part.new()
            top_fn, ok = D.solid_quad(tmp, g, [tuple(x_) for x_ in q], G2, 0.05, 0.012, 'rust_red', kind='rudder_brace',
                                      cell=0.3)
            if ok:
                Lb = float(np.linalg.norm(B_ - A_))
                kk = max(1, int(round((Lb - 0.16) / RV['spacing'])))
                for j in range(kk + 1):
                    c_ = A_ + (B_ - A_) * ((0.08 + (Lb - 0.16) * j / kk) / Lb)
                    r_ = g(c_[0], c_[1])
                    if r_ is not None:
                        D.rivet(tmp, r_[0] + r_[1] * (G2 + 0.05), r_[1], r=RV['r'], h=RV['h'])
                nbr = int(part.accept(tmp, CH, 'rudder_brace'))
        lg['face_%+d' % sgn] = dict(band_strips=nband, ribs=nrib, plates=nplate, layers=nlay, brace=nbr, y=round(yface, 3))
    # tiller clamps (round the bar, both sides of the blade)
    tl = [i for i, r in ship.islands.items() if r['part'] == 'Rudder' and r.get('piece') == 'tiller_bar']
    tv = ship.island_verts(tl)
    zc = float(tv[:, 2].mean())
    hy, hz = float(np.abs(tv[:, 1]).max()) + 0.025, float(tv[:, 2].max() - tv[:, 2].min()) / 2 + 0.025
    nt = 0
    I3 = np.eye(3)
    for x in RK['tiller_clamps']:
        tmp = part.new()
        for sg in (-1, 1):
            yc = sg * (0.22 + (hy - 0.22) / 2 + 0.0)
            D.chamfer_box(tmp, D.frame_matrix(np.array([x, yc, zc]), I3[0], I3[1], I3[2]), 0.05, (hy - 0.22) / 2 + 0.0,
                          hz, 0.008, 'dark_metal', 'tiller_clamp')
            for sz in (-1, 1):
                D.rivet(tmp, np.array([x, sg * hy, zc + sz * hz * 0.55]), np.array([0.0, sg, 0.0]), r=0.018, h=0.01)
        nt += int(part.accept(tmp, CH_clamp, 'tiller_clamp'))
    lg['tiller_clamps'] = nt
