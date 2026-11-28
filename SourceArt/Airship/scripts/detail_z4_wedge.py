"""Zone 4 (bow): the bow wedge (BowWedge, island 3 + its raised panels 4-10) and the keel block under the bow
(Underside_Front), plus the ship's own belly tabs forward of x 6.95.

Bow wedge (reference 1 / crop_bow.png: heavy rust armour plates, a riveted strake, big bolted blocks):
  * every big face is a Panel (detail_z4_lib): both vertical sides, the three lower chamfer facets per side, the
    bottom, the front face, the aft face below the keel line. The upper chamfer stays plain (narrow, carries the
    ship's own strip, and PA walkable boxes reach over it). The aft face above the main deck stays plain: PA boxes
    Hull_MainFwd_02 / 03 run under it (walkable tops, nothing may stand above them).
  * riveted dark angle irons over every crease of the sides (the top strake line at z 3.7, the side / chamfer and
    chamfer / bottom creases), bent riveted straps over the facet creases, a riveted keel strap down the bottom
  * plates in the wedge's own rust, one value step either way (rust_red / rust_dark), raised heavy armour in dark rust
    with a rivet row, dark frame ribs, patches in the other rust tone, slotted armour plates; no picture frames (on
    rust they read as windows, zone 6 found the same on the rudder)
  * big bolted blocks (machinery grey body, dark riveted base, dark rust cap) on the sides, the bottom and the front
  * two machinery bays on the bottom (zone 1's bay: riveted rust frame, dark floor, housing, pump, bottle, valve)
Keel block (Underside_Front, a lumpy sculpted V keel, grey): plates on fitted patches (lifted over the bumps,
refused where the surface departs more than 6 cm, e.g. the oval dent), in machinery grey / dark metal with rust
straps across both halves and a riveted rust keel angle along the V; raised armour and patches in rust.
Belly tabs (8 rust tabs on the bow flanks): corner rivets on their outer faces.
"""
import math
import numpy as np
from mathutils import Vector as V
import detail_common as D
import detail_zones as Z
from detail_flank import tile_rows, fill_gaps
from detail_z4_lib import (Panel, layer_plates, edge_angle, plane_meet, bolted_block, strap, bay, surf_of, lift_fn,
                           pipe_channel, conduit_pair)

WEDGE = 3


def face_info(ship):
    me = ship.ob.data
    n = len(me.polygons)
    nrm = np.empty(n * 3); me.polygons.foreach_get('normal', nrm); nrm = nrm.reshape(-1, 3)
    cen = np.empty(n * 3); me.polygons.foreach_get('center', cen); cen = cen.reshape(-1, 3)
    area = np.empty(n); me.polygons.foreach_get('area', area)
    return nrm, cen, area


def plane_of(ship, faces, nrm, area):
    w = area[faces]
    N = D.unit((nrm[faces] * w[:, None]).sum(0))
    pts = np.concatenate([ship.co[list(ship.polys[k])] for k in faces])
    return N, pts


def frame_for(N, pts, u_hint, v_hint):
    """plane frame: U = u_hint projected, Vd = N x U turned toward v_hint; origin + extents over pts"""
    U, _, _ = D.ortho_frame(N, u_hint)
    Vd = D.unit(np.cross(N, U))
    if np.dot(Vd, v_hint) < 0:
        Vd = -Vd
    c = pts.mean(0)
    u = (pts - c) @ U; v = (pts - c) @ Vd; h = (pts - c) @ N
    o = c + U * u.min() + Vd * v.min() + N * h.max()
    return o, U, Vd, float(u.max() - u.min()), float(v.max() - v.min())


class Keep:
    """global keep-outs of the zone: PA walkable tops (nothing may stand above a box top in its footprint), the
    ChainFwd swing (its links + a margin, starboard side of the wedge), the turret and cannon keep-clear volumes"""

    def __init__(self, K, near=()):
        """near: [(BVH, margin)]: keep `margin` away from that geometry (ChainFwd: it swings beside the wedge)"""
        self.boxes = Z.pa_boxes_blender(K['pa_boxes'])
        self.boxes = [(mn, mx) for (mn, mx) in self.boxes if mx[0] > 5.0]
        self.out = K['z4']['keepout_boxes']
        self.near = list(near)

    def __call__(self, p, margin=0.25):
        x, y, z = float(p[0]), float(p[1]), float(p[2])
        for mn, mx in self.boxes:
            if mn[0] - 0.02 <= x <= mx[0] + 0.02 and mn[1] - 0.02 <= y <= mx[1] + 0.02 and z > mx[2] - margin:
                return False
        for (x0, x1, y0, y1, z0, z1) in self.out:
            if x0 <= x <= x1 and y0 <= y <= y1 and z0 <= z <= z1:
                return False
        if Z.keep_clear_hits([p]):
            return False
        for b, m in self.near:
            if b.find_nearest(V(p), m)[0] is not None:
                return False
        return True

    def pa_bad(self, p):
        x, y, z = float(p[0]), float(p[1]), float(p[2])
        for mn, mx in self.boxes:
            if mn[0] <= x <= mx[0] and mn[1] <= y <= mx[1] and z > mx[2] - 0.005:
                return True
        return False


def reserve_line(M, a, b, half):
    """mark the cells of mask M within `half` of the world segment a-b as used (an angle iron / strap lies there)"""
    N = M.N
    a, b = D.vec(a), D.vec(b)
    a, b = a - N * float(a @ N), b - N * float(b @ N)          # measured in the panel's plane (lumpy panels too)
    ab = b - a
    L2 = max(float(ab @ ab), 1e-9)
    for i, u in enumerate(M.xs):
        P = M.o[None, :] + M.U[None, :] * u + M.Vd[None, :] * M.vs[:, None]
        P = P - np.outer(P @ N, N)
        t = np.clip(((P - a) @ ab) / L2, 0.0, 1.0)
        d = np.linalg.norm(P - (a + np.outer(t, ab)), axis=1)
        M.used[i, d < half] = True


def reserve_rect(M, u0, u1, v0, v1, pad=0.05):
    M.used[max(0, M.ix(u0 - pad)):M.ix(u1 + pad) + 1, max(0, M.iv(v0 - pad)):M.iv(v1 + pad) + 1] = True


def find_spot(M, cands, w, h, pad=0.06):
    """first (u, v) centre in cands where a w x h rectangle (+ pad) is free"""
    for (u, v) in cands:
        if M.all_free(u - w / 2 - pad, u + w / 2 + pad, v - h / 2 - pad, v + h / 2 + pad):
            return u, v
    return None


def slide_rect(M, u0, v0, W, H, du=1.6, dv=0.6, step=0.05, pad=0.04):
    """top-left (u, v) of a free W x H rectangle nearest the preferred top-left (u0, v0) within +-du / +-dv"""
    best = None
    for a in np.arange(-du, du + 1e-9, step):
        for b in np.arange(-dv, dv + 1e-9, step):
            d = a * a + 2.0 * b * b
            if best is not None and d >= best[0]:
                continue
            u, v = u0 + a, v0 + b
            if u < 0 or v < 0 or u + W > M.Lu or v + H > M.Lv:
                continue
            if M.all_free(u - pad, u + W + pad, v - pad, v + H + pad):
                best = (d, (u, v))
    return None if best is None else best[1]


def angle_runs(c_at, x0, x1, n1, n2, leg, t, gap, obst, keep, step=0.05, min_len=0.6):
    """x runs along a crease where an angle iron fits: its section clear of obstacles and of the keep-outs"""
    xs = np.arange(x0, x1 + 1e-9, step)
    ok = []
    for x in xs:
        c = c_at(x)
        if c is None:
            ok.append(False)
            continue
        e = np.array([1.0, 0.0, 0.0])
        n1_ = D.unit(n1 - e * n1[0]) if abs(n1[0]) < 0.9 else n1
        good = True
        for n_, other in ((n1, n2), (n2, n1)):
            d_ = D.unit(np.cross(np.cross(n_, other), n_))       # in-plane, away from the other face
            if np.dot(d_, other) > 0:
                d_ = -d_
            for s in (0.0, 0.5, 1.0):
                p = c + n_ * (gap + t * 0.5) + d_ * leg * s
                if any(b.find_nearest(V(p), t * 0.5 + 0.012)[0] is not None for b in obst) or not keep(p, margin=0.06):
                    good = False
                    break
            if not good:
                break
        ok.append(good)
    runs, cur = [], None
    for x, g in zip(xs, ok):
        if g:
            cur = [x, x] if cur is None else [cur[0], x]
        else:
            if cur and cur[1] - cur[0] >= min_len:
                runs.append(cur)
            cur = None
    if cur and cur[1] - cur[0] >= min_len:
        runs.append(cur)
    return [(a + 0.02, b - 0.02) for a, b in runs]


# ================================================================== bow wedge
def build_wedge(mesh, ship, K, rng, log, obst_all, deleted, keep):
    """mesh: SM_AirshipDetail_Z4_Wedge (Hull bone). obst_all: BVHs of other zones' details."""
    W4 = K['z4']
    R = K['rivet']
    PL = K['plate']
    nrm, cen, area = face_info(ship)
    isl = ship.p_island
    wf = np.nonzero(isl == WEDGE)[0]
    big = [k for k in wf if area[k] > 1.0]
    sel = lambda cond: [k for k in big if cond(nrm[k], cen[k])]
    groups = {}
    for side, sg in (('P', 1), ('S', -1)):
        groups['side_' + side] = sel(lambda n, c: n[1] * sg > 0.99)
        groups['upch_' + side] = sel(lambda n, c: n[1] * sg > 0.85 and n[2] > 0.3)
        low = sorted(sel(lambda n, c: n[1] * sg > 0.8 and n[2] < -0.2), key=lambda k: cen[k][0])
        for i, k in enumerate(low):
            groups['lowch%d_%s' % (i, side)] = [k]
    groups['bottom'] = sel(lambda n, c: n[2] < -0.9)
    groups['front'] = sel(lambda n, c: n[0] > 0.99)
    groups['aft'] = sel(lambda n, c: n[0] < -0.99)
    log['wedge_groups'] = {k: [int(x) for x in v] for k, v in groups.items()}
    planes = {k: plane_of(ship, v, nrm, area) for k, v in groups.items() if v}

    def obst_for(faces):
        m = np.ones(len(ship.polys), bool)
        m[faces] = False
        m &= ~deleted
        return [ship.bvh(m)] + obst_all

    panels = {}
    skin_bvh = ship.bvh(isl == 392)
    hints = dict(side=((1, 0, 0), (0, 0, -1)), lowch=((1, 0, 0), (0, 0, -1)), bottom=((1, 0, 0), (0, -1, 0)),
                 front=((0, -1, 0), (0, 0, -1)), aft=((0, 1, 0), (0, 0, -1)))
    for name in [k for k in groups if not k.startswith('upch') and groups[k]]:
        kind = name.split('_')[0].rstrip('0123456789')
        N, pts = planes[name]
        o, U, Vd, Lu, Lv = frame_for(N, pts, *hints[kind])
        tsurf = ship.surface(np.isin(np.arange(len(ship.polys)), groups[name]))
        # the aft face: most of it lies inside the hull (the hull runs on inside the wedge), so anything at all in
        # front of it blocks a cell (clear 40 m); elsewhere only what stands within 0.3 m of the face
        panels[name] = Panel('wedge_' + name, o, U, Vd, N, Lu, Lv, tsurf, obst_for(groups[name]),
                             clear=40.0 if kind == 'aft' else 0.3, du=0.05, dv=0.04, ntol=8.0, erode=1, keep=keep,
                             inside=skin_bvh if kind == 'aft' else None)
    log['wedge_free_m2'] = {k: round(p.area_free(), 1) for k, p in panels.items()}

    # ---------------------------------------------------------------- creases: angle irons and bent straps
    AN = W4['angle']
    nang = 0
    ang_log = []
    obst_ang = obst_for(wf) if False else [ship.bvh(~np.isin(isl, [WEDGE]) & ~deleted)] + obst_all

    def crease(gA, gB, x0, x1, tag, leg=AN['leg'], mat=AN['mat'], panels_touch=()):
        nonlocal nang
        if gA not in planes or gB not in planes:
            return
        nA, pA = planes[gA]; nB, pB = planes[gB]
        aA, aB = pA.mean(0), pB.mean(0)
        c_at = lambda x: plane_meet(nA, aA, nB, aB, x)
        for (xa, xb) in angle_runs(c_at, x0, x1, nA, nB, leg, AN['t'], PL['gap'], obst_ang, keep):
            c0, c1 = c_at(xa), c_at(xb)
            nang += edge_angle(mesh, c0, c1, nA, nB, leg=leg, t=AN['t'], gap=PL['gap'], mat=mat, R=R, kind='angle')
            ang_log.append(dict(tag=tag, x=[round(float(xa), 2), round(float(xb), 2)]))
            for pn in panels_touch:
                if pn in panels:
                    reserve_line(panels[pn], c0, c1, leg + 0.05)

    for side in ('P', 'S'):
        lows = sorted([k for k in groups if k.startswith('lowch') and k.endswith(side)])
        xr = lambda g: (float(min(ship.co[list(ship.polys[k])][:, 0].min() for k in groups[g])),
                        float(max(ship.co[list(ship.polys[k])][:, 0].max() for k in groups[g])))
        if 'upch_' + side in planes:
            x0, x1 = xr('side_' + side)
            crease('side_' + side, 'upch_' + side, x0 + 0.06, x1 - 0.06, 'top_' + side, panels_touch=('side_' + side,))
        for lg in lows:
            x0, x1 = xr(lg)
            crease('side_' + side, lg, x0 + 0.06, x1 - 0.06, 'side_low_' + lg, panels_touch=('side_' + side, lg))
            crease(lg, 'bottom', x0 + 0.06, x1 - 0.06, 'low_bottom_' + lg, panels_touch=(lg, 'bottom'))
        # bent straps over the creases between the chamfer facets (nearly vertical lines)
        for la, lb in zip(lows, lows[1:]):
            nA, pA = planes[la]; nB, pB = planes[lb]
            e = D.unit(np.cross(nA, nB))
            shared = [p for p in pA if np.min(np.linalg.norm(pB - p, axis=1)) < 1e-3]
            if len(shared) < 2:
                continue
            shared = sorted(shared, key=lambda p: p[2])
            c0, c1 = D.vec(shared[0]), D.vec(shared[-1])
            dl = D.unit(c1 - c0)
            c0, c1 = c0 + dl * 0.12, c1 - dl * 0.12
            if all(keep(c, 0.06) for c in (c0, c1)):
                nang += edge_angle(mesh, c0, c1, nA, nB, leg=W4['strap_w'] / 2, t=0.03, gap=PL['gap'], mat=AN['mat'],
                                   R=R, kind='strap')
                for pn in (la, lb):
                    reserve_line(panels[pn], c0, c1, W4['strap_w'] / 2 + 0.05)
                ang_log.append(dict(tag='facet_strap_' + la, z=[round(float(c0[2]), 2), round(float(c1[2]), 2)]))
    # bottom: bent straps over the two facet creases (x 19, x 23) and the keel strap down the middle
    bot = groups['bottom']
    bfaces = sorted(bot, key=lambda k: cen[k][0])
    Mb = panels.get('bottom')
    for fa, fb in zip(bfaces, bfaces[1:]):
        pa_ = ship.co[list(ship.polys[fa])]; pb_ = ship.co[list(ship.polys[fb])]
        shared = [p for p in pa_ if np.min(np.linalg.norm(pb_ - p, axis=1)) < 1e-3]
        if len(shared) < 2:
            continue
        shared = sorted(shared, key=lambda p: p[1])
        c0, c1 = D.vec(shared[0]), D.vec(shared[-1])
        dl = D.unit(c1 - c0)
        c0, c1 = c0 + dl * 0.2, c1 - dl * 0.2
        nang += edge_angle(mesh, c0, c1, nrm[fa], nrm[fb], leg=W4['strap_w'] / 2, t=0.03, gap=PL['gap'],
                           mat='rust_red', R=R, kind='strap')
        if Mb is not None:
            reserve_line(Mb, c0, c1, W4['strap_w'] / 2 + 0.05)
        ang_log.append(dict(tag='bottom_crease', x=round(float(c0[0]), 2)))
    if Mb is not None:
        # keel strap: a riveted rust strap down the bottom's centre line, one piece per facet
        for k in bfaces:
            P = ship.co[list(ship.polys[k])]
            xa, xb = P[:, 0].min() + 0.2, P[:, 0].max() - 0.2
            qa, qb = np.array([xa, 0.0, 0.0]), np.array([xb, 0.0, 0.0])
            # (u, v) of the centre line on the bottom panel
            ua, va = (qa - Mb.o) @ Mb.U, (qa - Mb.o) @ Mb.Vd
            ub, vb = (qb - Mb.o) @ Mb.U, (qb - Mb.o) @ Mb.Vd
            w = W4['keel_w']
            f = Mb.fn(ua, va - w / 2)
            n_, ok = strap(mesh, f, ub - ua, w, PL['gap'], 0.04, 'rust_red', R, along='u', kind='strap')
            nang += n_
            if ok:
                reserve_rect(Mb, ua, ub, va - w / 2, va + w / 2, pad=0.05)
        log['bottom_keel_strap'] = True
    log['wedge_angles'] = ang_log

    # ---------------------------------------------------------------- pipes: channels down the bottom, conduits on the sides
    npipe = 0
    if Mb is not None:
        for (cu0, cu1, cv0) in W4['bottom_channels']:
            H = 0.5
            u0, u1, v0 = Mb.Lu * cu0, Mb.Lu * cu1, Mb.Lv * cv0
            # the pipes pass over the crease straps (their top 5 cm off the bottom)
            npipe += pipe_channel(mesh, Mb, u0, u1, v0, K, rng, log, H=H, over=0.016, tag='bottom')
            reserve_rect(Mb, u0, u1, v0, v0 + H, pad=0.05)
    SC = W4['side_conduit']
    for side in ('P', 'S'):
        M = panels.get('side_' + side)
        if M is None:
            continue
        v, dv = SC['v'], 0.095
        band = (v - 0.03, v + dv + 0.01)
        u0 = 0.2
        while u0 < 3.0 and not M.all_free(u0, u0 + 0.6, *band):
            u0 += 0.05
        u1 = u0
        while u1 + 0.05 < M.Lu - 0.2 and M.all_free(u1, u1 + 0.05, *band):
            u1 += 0.05
        u1 -= 0.12
        if u1 - u0 > 2.0:
            npipe += conduit_pair(mesh, M, u0 + 0.1, u1, v, K, log, off0=SC['off'], tag='side_' + side)
            reserve_rect(M, u0, u1 + 0.05, v - 0.05, v + dv + 0.05, pad=0.02)
    log['wedge_pipes'] = npipe

    # ---------------------------------------------------------------- gussets under the top angle (zone 1's grid)
    G = K['gusset']
    ngus = 0
    for side in ('P', 'S'):
        M = panels.get('side_' + side)
        if M is None:
            continue
        x0w = float((M.o + M.U * 0.0)[0])
        for x in W4['gusset_x0'] + G['step'] * np.arange(math.ceil((x0w + 0.15 - W4['gusset_x0']) / G['step']), 80):
            u = (x - x0w) / max(1e-6, M.U[0])
            if u > M.Lu - 0.15:
                break
            vt = W4['angle']['leg'] + 0.035
            i0, i1 = M.ix(u - 0.03), M.ix(u + 0.03)
            m0, m1 = M.iv(vt), M.iv(vt + G['height'] + 0.02)
            if i0 < 0 or i1 >= len(M.xs) or not M.free[i0:i1 + 1, m0:m1 + 1].all():
                continue
            q, q2 = M.at(u, vt), M.at(u, vt + 0.08)
            if q is None or q2 is None:
                continue
            D.gusset(mesh, q[0] + q[1] * 0.004, q[1], D.unit(q[0] - q2[0]), G['depth'], G['height'], G['t'])
            M.used[max(0, M.ix(u - 0.06)):M.ix(u + 0.06) + 1, m0:m1 + 1] = True
            ngus += 1
    log['wedge_gussets'] = ngus

    # ---------------------------------------------------------------- machinery bays (bottom, sides, chamfers)
    nbay = 0
    for (pname, fu, fv, W, H) in W4['wedge_bays']:
        M = panels.get(pname)
        if M is None:
            continue
        spot = slide_rect(M, M.Lu * fu, M.Lv * fv, W, H, du=2.0, dv=0.6)
        if spot is None:
            log.setdefault('bays_skipped', []).append([pname, fu, fv])
            continue
        u0, v0 = spot
        nang += bay(mesh, M, u0, v0, W, H, K, rng, log, rim=0.1, rim_t=0.05, depth=0.11, tag='wedge_' + pname)
        reserve_rect(M, u0, u0 + W, v0, v0 + H, pad=0.06)
        nbay += 1
    log['wedge_bays'] = nbay

    # ---------------------------------------------------------------- big bolted blocks
    nb = 0
    blocks_log = []
    for pname, (fu, fv), (w, h, d) in W4['blocks']:
        M = panels.get(pname)
        if M is None:
            continue
        s = slide_rect(M, M.Lu * fu - w / 2, M.Lv * fv - h / 2, w + 0.14, h + 0.14, du=1.2, dv=0.5)
        if s is None:
            blocks_log.append(dict(panel=pname, built=False))
            continue
        u, v = s[0] + w / 2 + 0.07, s[1] + h / 2 + 0.07
        q = M.at(u, v)
        if q is None:
            continue
        BM = W4.get('block_mats', dict(body='machinery', base='dark_metal', cap=None))
        nang += bolted_block(mesh, q[0], q[1], M.U, w, h, d, mat=BM['body'], base_mat=BM['base'], cap_mat=BM['cap'], R=R)
        reserve_rect(M, u - w / 2 - 0.07, u + w / 2 + 0.07, v - h / 2 - 0.07, v + h / 2 + 0.07, pad=0.05)
        nb += 1
        blocks_log.append(dict(panel=pname, u=round(u, 2), v=round(v, 2), size=[w, h, d]))
    log['wedge_blocks'] = blocks_log

    # ---------------------------------------------------------------- plates + layers on every panel
    style = dict(armour='rust_dark', armour_p=0.5, batten='dark_metal', frames=False, frame_mat=lambda m: m,
                 patch_mats=lambda m: (('rust_dark', 1.0),) if m == 'rust_red' else (('rust_red', 1.0),),
                 slots=1, slot_pair=False, patch_p=0.55, rivet_min_area=W4['rivet_min_area'])
    cfg_row = dict(W4['wedge_rows'], mats=W4['wedge_mats'])
    cfg_fill = dict(W4['wedge_fill'], mats=W4['wedge_mats'])
    stats = {}
    for name in sorted(panels):
        M = panels[name]
        rows = tile_rows(M, rng, cfg_row, K)
        fills = fill_gaps(M, rng, cfg_fill, K)
        st = dict(style, slots=W4['wedge_slots'].get(name.split('_')[0].rstrip('0123456789'), 0))
        stats[name] = layer_plates(mesh, rows, fills, K, rng, log, style=st, tag='wedge_' + name)
        nang += stats[name]['rivets']
    log['wedge_rivets_struct'] = nang
    return panels


# ================================================================== keel block (Underside_Front)
def keel_panels(ship, K, obst_all, deleted, keep):
    """two lumpy panels over the V bottom of the keel block (port / starboard halves), v = 0 on the keel line"""
    W4 = K['z4']
    src = ship.p_src == 'Underside_Front'
    tsurf = ship.surface(src)
    m = ~src & ~deleted
    obst = [ship.bvh(m)] + obst_all
    out = {}
    for side, sg in (('P', 1), ('S', -1)):
        pts, nrs = [], []
        for x in np.arange(6.9, 14.0, 0.25):
            for y in np.arange(0.15, 2.65, 0.25):
                r = tsurf.ray((x, sg * y, -8.0), (0, 0, 1), 10.0)
                if r is not None and r[0][2] < 0.0:
                    pts.append(r[0]); nrs.append(r[1])
        pts = np.array(pts); N = D.unit(np.mean(nrs, axis=0))
        U, _, _ = D.ortho_frame(N, (1.0, 0.0, 0.0))
        Vd = D.unit(np.cross(N, U))
        if Vd[1] * sg < 0:
            Vd = -Vd
        c = pts.mean(0)
        # keel line (y = 0) at v = 0
        kp = np.array([[x, 0.0, 0.0] for x in np.arange(6.9, 14.0, 0.5)])
        u_all = (pts - c) @ U
        v_keel = float(np.median(((kp - c) @ Vd)))
        h = (pts - c) @ N
        o = c + U * (u_all.min() - 0.1) + Vd * v_keel + N * (h.max() + 0.1)
        Lu = float(u_all.max() - u_all.min() + 0.2)
        Lv = float(((pts - c) @ Vd).max() - v_keel + 0.1)
        out[side] = Panel('keel_' + side, o, U, Vd, N, Lu, Lv, tsurf, obst, clear=0.25, du=0.05, dv=0.04, ntol=35.0,
                          erode=1, keep=keep, lumpy=True, max_res=W4['keel_max_res'], rb=1.2, flat=False)
    return out, tsurf


def build_keel(mesh, ship, K, rng, log, obst_all, deleted, keep):
    W4 = K['z4']
    R = K['rivet']
    PL = K['plate']
    panels, tsurf = keel_panels(ship, K, obst_all, deleted, keep)
    log['keel_free_m2'] = {k: round(p.area_free(), 1) for k, p in panels.items()}
    nr = 0
    # keel angle along the V: per 1.2 m segment, planes fitted to each half next to the keel (lifted over the bumps)
    segs = []
    for xa in np.arange(7.05, 13.7, 1.25):
        xb = min(xa + 1.2, 13.75)
        fits = []
        for sg in (1, -1):
            P = []
            for x in np.linspace(xa, xb, 6):
                for y in np.linspace(0.06, 0.32, 5):
                    r = tsurf.ray((x, sg * y, -8.0), (0, 0, 1), 10.0)
                    if r is not None:
                        P.append(r[0])
            if len(P) < 20:
                fits = None
                break
            P = np.array(P); c = P.mean(0)
            _, _, vt = np.linalg.svd(P - c)
            n = vt[2]
            if n[2] > 0:
                n = -n
            lift = float(((P - c) @ n).max())
            fits.append((n, c + n * lift))
        if not fits:
            continue
        (n1, a1), (n2, a2) = fits
        c0, c1 = plane_meet(n1, a1, n2, a2, xa), plane_meet(n1, a1, n2, a2, xb)
        if c0 is None or c1 is None or not keep(c0, 0.06) or not keep(c1, 0.06):
            continue
        nr += edge_angle(mesh, c0, c1, n1, n2, leg=W4['keel_w'] / 2 + 0.04, t=0.04, gap=PL['gap'], mat='rust_red', R=R,
                         kind='strap')
        segs.append([round(float(xa), 2), round(float(xb), 2)])
        for M in panels.values():
            reserve_line(M, c0, c1, W4['keel_w'] / 2 + 0.1)
    log['keel_angle_segments'] = segs
    # rust straps across both halves (every ~1.6 m), split where the surface is too lumpy for one piece
    nstr = 0
    for side, M in panels.items():
        for fu in W4['keel_strap_u']:
            u0 = M.Lu * fu
            v = 0.2
            while v < M.Lv - 0.3:
                done = False
                for Lseg in (M.Lv - v - 0.05, 1.4, 1.0, 0.7):
                    if Lseg < 0.5:
                        continue
                    cells = M.free[max(0, M.ix(u0)):M.ix(u0 + W4['strap_w']) + 1, M.iv(v):M.iv(v + Lseg) + 1]
                    if cells.size == 0 or cells.mean() < 0.85:
                        continue
                    f = M.fn_patch(u0, v, W4['strap_w'], Lseg, nu=3, nv=8)
                    if f is None:
                        continue
                    n_, ok = strap(mesh, f, Lseg, W4['strap_w'], PL['gap'], 0.04, 'rust_red', R, along='v', kind='strap')
                    if ok:
                        nr += n_
                        nstr += 1
                        reserve_rect(M, u0, u0 + W4['strap_w'], v, v + Lseg, pad=0.05)
                        v += Lseg + 0.02
                        done = True
                        break
                if not done:
                    if W4.get('keel_strap_continuous'):
                        break                  # review fix 2026-11-28: a band runs on from the keel angle, no stray bits
                    v += 0.2
    log['keel_straps'] = nstr
    # a pipe along each half next to the keel angle (pushed clear of the bumps, smoothed), ends in glands
    KP = W4['keel_pipe']
    npk = 0
    for side, M in panels.items():
        pts = []
        for u in np.arange(KP['u'][0], M.Lu - KP['u'][1], 0.3):
            q = M.at(u, KP['v'])
            if q is None:
                continue
            if q[0][0] > KP['x_max'][side]:          # the port pipe stops short of the oval dent in the keel block
                break
            pts.append(q[0] + q[1] * (KP['r'] + KP['off']))
        if len(pts) < 6:
            continue
        P = np.array(pts)
        for _ in range(3):
            for i in range(len(P)):                    # push clear of the lumpy surface (r + 1.5 cm)
                q = tsurf.nearest(P[i], 1.0)
                if q is not None and q[3] < KP['r'] + KP['off'] - 0.01:
                    P[i] = P[i] + q[1] * (KP['r'] + KP['off'] - 0.01 - q[3])
            P[1:-1] = (P[:-2] + 2 * P[1:-1] + P[2:]) / 4.0
        for _ in range(2):                             # keep every point in a band off the surface (no dips, no hops)
            for i in range(len(P)):
                q = tsurf.nearest(P[i], 1.0)
                if q is None:
                    continue
                d0 = KP['r'] + KP['off']
                if q[3] < d0 - 0.012 or q[3] > d0 + 0.015:
                    P[i] = q[0] + D.unit(P[i] - q[0]) * min(max(q[3], d0 - 0.008), d0 + 0.01)
        ends = [tsurf.nearest(P[0], 1.0), tsurf.nearest(P[-1], 1.0)]
        if any(e is None for e in ends):
            continue
        path = [ends[0][0] - ends[0][1] * 0.02] + list(P) + [ends[1][0] - ends[1][1] * 0.02]
        surf_n = lambda pt: (lambda r: None if r is None else (r[0], r[1]))(tsurf.nearest(pt, 1.0))
        ncl = max(2, int(len(P) * 0.3 / 1.0))
        D.pipe_run(mesh, path, KP['r'], 0.14, sides=10, mat='copper', flange_at=(0.3, 0.7), flange_k=1.2,
                   clamp_at=[(i + 0.5) / ncl for i in range(ncl)], surf_fn=surf_n, kind='pipe')
        for e in ends:
            D.gland(mesh, e[0], e[1], M.U, KP['r'], size=KP['r'] * 2.0, back=0.0)
        reserve_line(M, P[0], P[-1], KP['r'] + 0.12)
        npk += 1
    log['keel_pipes'] = npk
    # one machinery bay per half (on a fitted patch; slides to where the surface is calm enough)
    nkb = 0
    for side, M in (panels.items() if W4.get('keel_bay') else ()):
        fu, fv, W, H, res = W4['keel_bay']
        res0, M.max_res = M.max_res, res
        best = None
        for a in np.arange(-2.0, 2.01, 0.1):
            u0, v0 = M.Lu * fu + a, M.Lv * fv
            if u0 < 0 or u0 + W > M.Lu or not M.all_free(u0 - 0.04, u0 + W + 0.04, v0 - 0.04, v0 + H + 0.04):
                continue
            if M.fn_patch(u0, v0, W, H) is None:
                continue
            if best is None or abs(a) < abs(best[0]):
                best = (a, u0, v0)
        if best is None:
            M.max_res = res0
            log.setdefault('keel_bays_skipped', []).append(side)
            continue
        nr += bay(mesh, M, best[1], best[2], W, H, K, rng, log, rim=0.09, rim_t=0.05, depth=0.1, tag='keel_' + side)
        M.max_res = res0
        reserve_rect(M, best[1], best[1] + W, best[2], best[2] + H, pad=0.06)
        nkb += 1
    log['keel_bays'] = nkb
    # big bolted blocks near the keel's lower end (aft) on each half
    for side, M in panels.items():
        s = find_spot(M, [(M.Lu * a, M.Lv * b) for (a, b) in W4['keel_block_at']], 0.5, 0.42)
        if s is None:
            continue
        f = M.fn_patch(s[0] - 0.35, s[1] - 0.3, 0.7, 0.6)
        if f is None:
            continue
        q = f(0.35, 0.3)
        BM = W4.get('keel_block_mats', dict(body='machinery', base='rust_dark', cap=None))
        nr += bolted_block(mesh, q[0], q[1], M.U, 0.5, 0.42, 0.17, mat=BM['body'], base_mat=BM['base'], cap_mat=BM['cap'],
                           R=R)
        reserve_rect(M, s[0] - 0.33, s[0] + 0.33, s[1] - 0.3, s[1] + 0.3, pad=0.04)
    style = dict(armour='rust_red', armour_p=0.6, batten='rust_red', frames=False, frame_mat=lambda m: m,
                 patch_mats=lambda m: (('rust_red', 0.6), ('rust_dark', 0.4)), slots=1, slot_pair=False, patch_p=0.6,
                 rivet_min_area=W4['rivet_min_area'])
    cfg_row = dict(W4['keel_rows'], mats=W4['keel_mats'])
    cfg_fill = dict(W4['keel_fill'], mats=W4['keel_mats'])
    for side, M in panels.items():
        rows = tile_rows(M, rng, cfg_row, K)
        fills = fill_gaps(M, rng, cfg_fill, K)
        st = layer_plates(mesh, rows, fills, K, rng, log, style=style, tag='keel_' + side)
        nr += st['rivets']
    log['keel_rivets'] = nr
    return panels


# ================================================================== the ship's own belly tabs forward of x 6.95
def tab_rivets(mesh, ship, K, log, extra=(4, 5, 7, 8)):
    """corner rivets on the outer face of each Z4 belly tab (islands 393-411 with centre forward of x 6.95) and of the
    bow wedge's own raised side panels (islands 4, 5, 7, 8)"""
    R = K['rivet']
    nrm, cen, area = face_info(ship)
    n = 0
    tabs = []
    for isl in list(range(393, 412)) + list(extra):
        vm = ship.v_island == isl
        if not vm.any():
            continue
        cc = ship.co[vm].mean(0)
        if cc[0] <= Z.X_FWD:
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
