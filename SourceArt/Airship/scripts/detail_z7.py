"""Zone 7 of the airship detail pass (round 3, 2026-11-28): the gantry / forward turret deck and the STAIRS.

  blender_capped.sh --python detail_z7.py [-- --no-save] [--blend-out FILE]

Talal's point 3 (2026-11-28): "stairs, where looks better" from the main deck up to the forward turret deck (the gantry
platform, 4.16 m higher). Three placements were mocked (detail_z7_mocks.py, media/z7/stairs_options/); the chosen one
is 'central': two straight flights on the deck's centre corridor between the crates, a landing half way, arriving at the
middle of the platform's open aft edge. The rest of the zone follows zone 1's approved language (colour by role, three
depth levels, rivets only on straps / ribs / corners / flanges, ~30 % calm, machinery with hinged lids, pipes with
flanges and clamps).

Objects (collection Detail_Z7, parent Armature + Armature modifier, every vertex 100 % on one bone):
  SM_AirshipDetail_Z7_Stairs        Hull         the stairs (one object: the Unreal stage gives it walkable collision,
                                                 Docs/Airship/round3/stairs_collision.json)
  SM_AirshipDetail_Z7_Gantry        Hull         truss gussets and rivets, fascia plates on the platform edge beams and
                                                 the raised fore deck, underside joists / pipes / turret drive housings,
                                                 legs (bands, knees, pump housings), hang strip bands, chain brackets,
                                                 winch bearings
  SM_AirshipDetail_Z7_Rails         Hull         rail collars along the whole ship + the platform's new aft guard rails
  SM_AirshipDetail_Z7_LightPosts    SearchLight_AftL / MidL / MidR / FwdC          sleeves, junction boxes, conduits
  SM_AirshipDetail_Z7_LightHeads    SearchLight_*_Head                             bezels, hoods, fins, yokes, handles
  SM_AirshipDetail_Z7_Winches       Winch_Fwd / Winch_Aft                          rope layers, flange bolt circles
Report: Docs/Airship/round3/z7_report.json; collision: Docs/Airship/round3/stairs_collision.json.
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
import detail_z7_stairs as ST

ZONE = 'Z7'
K_PA = '/mnt/new_partition/UnrealProjects/_AirshipWork/Saved/Airship/pa_hull_boxes.json'
DOCS = '/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/round3'
YELLOWS = (('paint_yellow', 0.5), ('paint_ochre', 0.5))
K = dict(
    seed=1307, touch_tol=0.02,
    plate=dict(gap=0.015, t=0.045, bevel=0.014),             # zone 1's base plate (1.5 cm gap, 4.5 cm thick)
    layer=0.006, seam=0.024,
    rivet=dict(r=0.022, h=0.012, inset=0.07, spacing=0.28),  # zone 1's low domed rivets
    # Talal 2026-11-28 "make them steel": the stair hand rails are a steel tube (was wood r 0.034, 8 sides) on a small
    # dark saddle at every post; treads stay wood. mat 'steel' (DM_Steel) or 'dark_metal' (DM_Dark): both were rendered
    # (rig/tmp/r3ans), see ZONE_7.md. The collision boxes do not change (the rail stays 0.95 m above the nosings).
    stairs=dict(option='central', w=1.5, going=0.30, landing=1.5,
                rail=dict(mat='steel', r=0.026, sides=10, saddle=True)),
    fascia=dict(w=(0.9, 1.6), rib_p=0.75, rib_w=0.12, rib_t=0.05, frame_p=0.25, patch_p=0.25, armour_p=0.10,
                slotted=(1, 0), mats=YELLOWS),         # review fix 2026-11-28: no slotted plates on the 0.8 m walls
    #   of the raised fore deck (the slots merged into a slanted bar and read as the letter Z next to centred patches)
    chain=dict(link=0.55, wire=0.045, sides=6),     # review fix: ChainAft as a heavy chain (was link 0.30, wire 3.2 cm)
    truss=dict(gusset_t=0.02, gusset_w=0.34, gusset_h=0.58, rivet_step=0.40),
    under=dict(joist_d=0.12, pipe_r=(0.065, 0.05), pipe_y=(1.05, 1.30), drive_r=0.34, drive_xy=(21.1, 2.0)),
    lights=dict(sleeve_r=0.11, collar_r=0.10),
    winch=dict(rope_r=(0.735, 0.755), rope_step=0.10, keep_y=0.30, bolt_r=0.84, bolts=12),
    rails=dict(collar_len=0.10, mat='rust_red'),
    guard=dict(x=10.6, top=7.65, mid=7.10, post=0.045, step=1.0),
    walk=dict(layer=2.2, free=0.20, overhead=1.75),
)


def opts():
    a = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    o = {}
    for i, k in enumerate(a):
        if k.startswith('--'):
            o[k[2:]] = a[i + 1] if i + 1 < len(a) and not a[i + 1].startswith('--') else True
    return o


obox, seg_box, extrude_poly = ST.obox, ST.seg_box, ST.extrude_poly
EX, EY, EZ = np.eye(3)


def isl_verts(ship, i):
    return ship.co[ship.v_island == i]


def isl_surface(ship, ids):
    return D.Surface.from_mesh(ship.ob.data, poly_mask=np.isin(ship.p_island, list(ids)))


def pick(rng, choices):
    r = rng.random() * sum(w for _, w in choices)
    for k, w in choices:
        r -= w
        if r <= 0:
            return k
    return choices[-1][0]


# ================================================================== the platform's edge: fascia plates
def wall_fn(surf, A, B, z0, nout):
    """(u, v) -> (point, normal) on a vertical wall between plan points A and B (u along A->B, v up from z0)"""
    A, B = np.asarray(A, float), np.asarray(B, float)
    L = float(np.linalg.norm(B - A))
    t = (B - A) / L
    no = np.array([nout[0], nout[1], 0.0])

    def f(u, v):
        q = A + t * u
        o = np.array([q[0], q[1], z0 + v]) + no * 0.4
        r = surf.ray(o, -no, 1.0)
        return None if r is None else (r[0], r[1])
    return f, L


def shifted(f, du, dv):
    return lambda u, v: f(u + du, v + dv)


def plate_row(m, f, L, H, rng, K, log, u0=0.02, u1=None, slotted=0, gaps=()):
    """one row of base plates along a wall strip [u0, u1] x [0, H] (zone 1's language): yellow / ochre base plates with
    rivets at the corners; rust frame ribs over most seams; on some plates a picture frame, a rust patch, a rust armour
    plate or a slotted plate; the rest calm"""
    P, R, F = K['plate'], K['rivet'], K['fascia']
    u1 = L - 0.02 if u1 is None else u1
    seam = K['seam']
    v0, v1 = 0.015, H - 0.015
    spans, u = [], u0
    while u1 - u > 0.3:
        w = rng.uniform(*F['w'])
        if u1 - u - w < 0.6:
            w = u1 - u
        hit = [g_ for g_ in gaps if u < g_[1] and u + w > g_[0]]
        if hit:
            ga, gb = min(hit)
            if ga - u >= 0.3:
                spans.append((u, ga))
            u = gb
            continue
        spans.append((u, u + w))
        u += w + seam
    g2 = P['gap'] + P['t'] + K['layer']                       # second layer (6.6 cm off the wall)
    slot_at = set(rng.sample(range(len(spans)), min(slotted, len(spans)))) if spans else set()
    n_kind = {}
    for i, (a, b) in enumerate(spans):
        mat = pick(rng, F['mats'])
        g = shifted(f, a, v0)
        W, Hh = b - a, v1 - v0
        us, vs = D.grid_coords(0.0, W, 0.4), D.grid_coords(0.0, Hh, 0.25)
        top, ok = D.solid_plate(m, g, us, vs, P['gap'], P['t'], P['bevel'], mat, kind='plate')
        if not ok:
            n_kind['skipped'] = n_kind.get('skipped', 0) + 1
            continue
        D.rivet_row(m, top, D.corner_pts(us, vs, R['inset']), r=R['r'], h=R['h'])
        r_ = rng.random()
        other = 'paint_ochre' if mat == 'paint_yellow' else 'paint_yellow'
        if i in slot_at and W > 0.7 and Hh > 0.3:
            sw = min(0.8, W - 0.2)
            gs = shifted(g, (W - sw) / 2, 0.05)
            ok2 = D.slotted_plate(m, gs, sw, Hh - 0.1, g2, 0.035, 0.01, mat, n_slots=3 if sw > 0.6 else 2,
                                  slot_w=0.05, ang=58.0)
            kind = 'slotted' if ok2 else 'calm'
        elif r_ < F['armour_p']:
            # heavy rust armour over most of the plate, rivet row along its top edge
            gs = shifted(g, 0.05, 0.03)
            aw, ah = W - 0.10, Hh - 0.06
            ua, va = D.grid_coords(0.0, aw, 0.4), D.grid_coords(0.0, ah, 0.25)
            ta, ok2 = D.solid_plate(m, gs, ua, va, g2, 0.04, 0.012, 'rust_red', kind='armour')
            if ok2:
                D.rivet_row(m, ta, [(x, ah - 0.06) for x in np.arange(0.07, aw - 0.06, R['spacing'])], r=R['r'], h=R['h'])
            kind = 'armour'
        elif r_ < F['armour_p'] + F['frame_p'] and W > 0.6 and Hh > 0.4:
            rim = 0.075
            gs = shifted(g, 0.09, 0.07)
            D.picture_frame(m, gs, W - 0.18, Hh - 0.14, rim, g2, 0.035, 0.01, other, kind='frame')
            kind = 'frame'
        elif r_ < F['armour_p'] + F['frame_p'] + F['patch_p'] and W > 0.55:
            # review fix 2026-11-28: a low, wide patch on the plate's bottom edge at one end (off centre); a small
            # square in the middle of a plate read as a letter / a window
            pw = min(W - 0.2, rng.uniform(0.45, 0.7))
            ph = min(Hh - 0.1, rng.uniform(0.22, 0.32))
            pu = 0.08 if rng.random() < 0.5 else W - pw - 0.08
            rng.uniform(0.0, 1.0)
            pv = 0.04
            gs = shifted(g, pu, pv)
            up, vp = D.grid_coords(0.0, pw, 0.4), D.grid_coords(0.0, ph, 0.25)
            tp, ok2 = D.solid_plate(m, gs, up, vp, g2, 0.04, 0.012, pick(rng, (('rust_red', 0.7), ('paint_ochre', 0.3))),
                                    kind='patch')
            if ok2:
                D.rivet_row(m, tp, D.corner_pts(up, vp, 0.05), r=R['r'], h=R['h'])
            kind = 'patch'
        else:
            kind = 'calm'
        n_kind[kind] = n_kind.get(kind, 0) + 1
    # frame ribs over the seams (rust, 11.6 cm off the wall), rivets every 28 cm
    ribs = 0
    for (a, b), (c, d) in zip(spans[:-1], spans[1:]):
        if rng.random() > F['rib_p']:
            continue
        su = (b + c) / 2
        g = shifted(f, su - F['rib_w'] / 2, 0.0)
        g = shifted(f, su - F['rib_w'] / 2, 0.012)
        ur, vr = D.grid_coords(0.0, F['rib_w'], 0.2), D.grid_coords(0.0, H - 0.024, 0.25)
        tr, ok = D.solid_plate(m, g, ur, vr, g2, F['rib_t'], 0.012, 'rust_red', kind='rib')
        if ok:
            ribs += 1
            nr = max(2, int(round((H - 0.12) / R['spacing'])) + 1)
            D.rivet_row(m, tr, [(F['rib_w'] / 2, v) for v in np.linspace(0.05, H - 0.074, nr)], r=R['r'], h=R['h'])
    for k_, v_ in n_kind.items():
        log[k_] = log.get(k_, 0) + v_
    log['plates'] = log.get('plates', 0) + len(spans)
    log['ribs'] = log.get('ribs', 0) + ribs
    return spans


def fascia(ship, m, rng, K, log):
    """the platform's edge beams (islands 238 / 239) and the raised fore deck's walls (233): one row of plates each"""
    lg = log.setdefault('fascia', {})
    for side, isl in ((1, 238), (-1, 239)):
        surf = isl_surface(ship, [isl])
        A, B = (10.501, side * 3.31), (27.501, side * 3.01)
        t = np.array(B) - np.array(A)
        nout = np.array([-t[1], t[0]]) / np.linalg.norm(t) * side
        if nout[1] * side < 0:
            nout = -nout
        f, L = wall_fn(surf, A, B, 5.85, nout)
        plate_row(m, f, L, 0.50, rng, K, lg, u0=0.03, u1=L - 0.03, slotted=K['fascia']['slotted'][0])
    surf = isl_surface(ship, [233])
    walls = []
    for side in (1, -1):
        walls.append(((23.8, side * 2.5), (27.5, side * 2.4), side))
        walls.append(((27.5, side * 2.4), (31.2, side * 1.25), side))
    walls.append(((31.2, 1.25), (31.2, -1.25), 0))
    for A, B, side in walls:
        t = np.array(B, float) - np.array(A, float)
        nout = np.array([t[1], -t[0]]) / np.linalg.norm(t)
        mid = (np.array(A) + np.array(B)) / 2
        if np.dot(nout, mid - np.array([27.0, 0.0])) < 0:
            nout = -nout
        f, L = wall_fn(surf, A, B, 6.55, nout)
        # the MidL / MidR posts run down through this deck just inside its side walls and wobble +-4 deg about the
        # deck top: leave the wall bare 0.28 m either side of them
        gaps = []
        for (px, py) in ((24.6, 2.4), (24.6, -2.4)):
            tA = np.array(B, float) - np.array(A, float)
            uu = float(np.dot(np.array([px, py]) - np.array(A), tA / np.linalg.norm(tA)))
            dd = abs(float(np.cross(tA / np.linalg.norm(tA), np.array([px, py]) - np.array(A))))
            if dd < 0.4 and -0.3 < uu < L + 0.3:
                gaps.append((uu - 0.28, uu + 0.28))
        # keep 8 cm from the wall corners, plates 0.76 tall
        plate_row(m, f, L, 0.80, rng, K, lg, u0=0.08, u1=L - 0.08, slotted=K['fascia']['slotted'][1] if side else 0,
                  gaps=gaps)
    # the slab's own tapered bow edge (x 27.5 .. 31.5, 0.35 tall): a riveted rust strap
    surf = isl_surface(ship, [232])
    for A, B in (((27.5, 2.9), (31.5, 1.5)), ((31.5, 1.5), (31.5, -1.5)), ((31.5, -1.5), (27.5, -2.9))):
        t = np.array(B, float) - np.array(A, float)
        nout = np.array([t[1], -t[0]]) / np.linalg.norm(t)
        if np.dot(nout, (np.array(A) + np.array(B)) / 2 - np.array([27.0, 0.0])) < 0:
            nout = -nout
        f, L = wall_fn(surf, A, B, 6.2, nout)
        g = shifted(f, 0.06, 0.06)
        us, vs = D.grid_coords(0.0, L - 0.12, 0.4), D.grid_coords(0.0, 0.23, 0.25)
        top, ok = D.solid_plate(m, g, us, vs, K['plate']['gap'], 0.04, 0.012, 'rust_red', kind='strap')
        if ok:
            D.rivet_row(m, top, [(u, 0.115) for u in np.arange(0.07, L - 0.18, K['rivet']['spacing'])],
                        r=K['rivet']['r'], h=K['rivet']['h'])
            lg['straps'] = lg.get('straps', 0) + 1


# ================================================================== the truss: gussets at the joints, rivet rows
def truss(ship, m, K, log):
    T = K['truss']
    R = K['rivet']
    n_g, n_r = 0, 0
    xs = [10.6 + 2.0 * k for k in range(11)]
    for side in (1, -1):
        yf = side * (2.70 + 0.004 + T['gusset_t'] / 2)
        n = np.array([0.0, side, 0.0])
        for j, xj in enumerate(xs):
            lo, hi = max(10.53, xj - T['gusset_w']), min(30.67, xj + T['gusset_w'])
            for top in (True, False):
                zc = 6.10 if top else 4.35
                sgn = -1 if top else 1                 # the plate grows down from the top chord, up from the bottom
                z_edge = zc + (-sgn) * 0.10 if False else (6.20 if top else 4.25)
                z_mid = zc + sgn * 0.18
                z_tip = z_edge + sgn * T['gusset_h']
                poly = [(lo, z_edge), (hi, z_edge), (hi, z_mid), (min(hi, xj + 0.13), z_tip), (max(lo, xj - 0.13), z_tip),
                        (lo, z_mid)]
                extrude_poly(m, poly, np.array([0.0, yf, 0.0]), EX, EZ, n, T['gusset_t'], 'rust_red', 'gusset')
                n_g += 1
                yr = yf + side * (T['gusset_t'] / 2)
                pts = [(x, zc) for x in (lo + 0.07, xj, hi - 0.07) if lo + 0.05 <= x <= hi - 0.05] + \
                      [(xj, z_tip - sgn * 0.10)]
                for (x, z) in pts:
                    D.rivet(m, (x, yr, z), n, r=R['r'], h=R['h'])
                    n_r += 1
        # rivet rows along the bottom chord's outer face between the gussets (the top chord is under the fascia's
        # shadow and seen less: its gussets carry its rivets)
        for zc in (4.35,):
            for xa, xb in zip(xs[:-1], xs[1:]):
                for x in np.arange(xa + T['gusset_w'] + 0.14, xb - T['gusset_w'] - 0.06, T['rivet_step']):
                    D.rivet(m, (x, side * 2.704, zc), n, r=R['r'], h=R['h'])
                    n_r += 1
    log['truss'] = dict(gussets=n_g, rivets=n_r)


# ================================================================== under the platform: joists, pipes, drives
def slab_half_width(x):
    if x <= 27.5:
        return 3.2 + (2.9 - 3.2) * (x - 10.5) / 17.0
    return 2.9 + (1.5 - 2.9) * (x - 27.5) / 4.0


def leg_info(ship, isl):
    P = isl_verts(ship, isl)
    c = P.mean(0)
    U, s, Vt = np.linalg.svd(P - c)
    ax = Vt[0] if Vt[0][2] > 0 else -Vt[0]
    lo = P[np.argsort(P[:, 2])[:4]]
    cl = lo.mean(0)
    # cross-section axes (horizontal edges of the bottom square)
    e = [D.unit(lo[i] - lo[0]) for i in (1, 2, 3)]
    d_ = [np.linalg.norm(lo[i] - lo[0]) for i in (1, 2, 3)]
    order = np.argsort(d_)
    e1, e2 = e[order[0]], e[order[1]]
    half = 0.5 * d_[order[0]]
    t = (P - c) @ ax
    return dict(c=c, ax=ax, bot=c + ax * t.min(), top=c + ax * t.max(), e1=e1, e2=e2, half=half)


def leg_at(L, z):
    a, b = L['bot'], L['top']
    k = (z - a[2]) / (b[2] - a[2])
    return a + (b - a) * k


def underside(ship, m, rng, K, log):
    """joists between the cross beams, two pipe pairs (from the pump housings on the aft legs to the turret drive
    housing / the winch motor box), the two turret drive housings"""
    U = K['under']
    lg = log.setdefault('underside', {})
    zs = 6.195
    jd = U['joist_d']
    nj = 0
    joists = []
    for k in range(5):
        for j in (1.0, 2.0, 3.0):
            x = 10.6 + 4 * k + j
            hw = min(2.47, slab_half_width(x) - 0.06)
            if hw < 1.0:
                continue
            # I-beam: two flanges + web, riveted to the top chords' inner faces
            obox(m, (x, 0.0, zs - 0.0075), EX, EY, EZ, 0.045, hw, 0.0075, 'dark_metal', 'joist')
            obox(m, (x, 0.0, zs - jd + 0.0075), EX, EY, EZ, 0.045, hw, 0.0075, 'dark_metal', 'joist')
            obox(m, (x, 0.0, zs - jd / 2), EX, EY, EZ, 0.011, hw, jd / 2 - 0.015, 'dark_metal', 'joist')
            for sy in (-1, 1):
                D.rivet(m, (x, sy * (hw - 0.06), zs - jd), (0, 0, -1), r=0.016, h=0.009)
            joists.append((x, hw))
            nj += 1
    lg['joists'] = nj
    # cable tray along the centre line under the joists, cables in it, hangers up to the joists
    tz0, tz1 = 5.90, 5.98
    x0t, x1t = 11.0, 27.3
    obox(m, ((x0t + x1t) / 2, 0.0, tz0 + 0.006), EX, EY, EZ, (x1t - x0t) / 2, 0.14, 0.006, 'dark_metal', 'tray')
    for sy in (-1, 1):
        obox(m, ((x0t + x1t) / 2, sy * 0.134, (tz0 + tz1) / 2), EX, EY, EZ, (x1t - x0t) / 2, 0.006, (tz1 - tz0) / 2,
             'dark_metal', 'tray')
    for k_, (yy, rr, mat) in enumerate(((-0.07, 0.024, 'dark_metal'), (0.0, 0.02, 'copper'), (0.07, 0.024, 'dark_metal'))):
        D.tube(m, [np.array([x0t - 0.25, yy, tz0 + 0.013 + rr]), np.array([x1t, yy, tz0 + 0.013 + rr])], rr, sides=6,
               mat=mat, kind='tray')
    for (xj, hw) in joists:
        if x0t < xj < x1t:
            for sy in (-1, 1):
                obox(m, (xj, sy * 0.15, (tz0 + zs - jd) / 2), EX, EY, EZ, 0.02, 0.01, (zs - jd - tz0) / 2 + 0.003,
                     'dark_metal', 'tray')
    # junction housings over the tray (between joists), lids facing down, cables rising into them
    for xh in (13.1, 17.1, 25.1):
        D.housing(m, (xh, 0.0, zs + 0.004), (0, 0, -1), (1, 0, 0), 0.46, 0.34, 0.15)
        for yy in (-0.07, 0.07):
            D.cylinder(m, (xh + 0.20, yy, tz0 + 0.04), (xh + 0.20, yy, zs - 0.10), 0.022, 6, 'brass', 'tray',
                       smooth=False)
    lg['junction_housings'] = 3
    # the slab's aft face (x 10.5, 0.35 tall): a riveted rust strap, split where the stairs arrive
    surf = isl_surface(ship, [232])
    for (ya, yb) in ((-3.12, -0.40), (1.66, 3.12)):
        f, L = wall_fn(surf, (10.5, ya), (10.5, yb), 6.2, (-1.0, 0.0))
        g = shifted(f, 0.0, 0.06)
        us, vs = D.grid_coords(0.0, L, 0.4), D.grid_coords(0.0, 0.23, 0.25)
        top, ok = D.solid_plate(m, g, us, vs, K['plate']['gap'], 0.04, 0.012, 'rust_red', kind='strap')
        if ok:
            D.rivet_row(m, top, [(u, 0.115) for u in np.arange(0.07, L - 0.05, K['rivet']['spacing'])],
                        r=K['rivet']['r'], h=K['rivet']['h'])
    # turret drive housings (under the two turret mounts, inboard of the top chords)
    dx_, dy_ = U['drive_xy']
    R = U['drive_r']
    drives = []
    for side in (1, -1):
        c = np.array([dx_, side * dy_, 0.0])
        D.cylinder(m, (c[0], c[1], zs - 0.31), (c[0], c[1], zs - 0.03), R, 16, 'machinery', 'drive', smooth=True)
        D.cylinder(m, (c[0], c[1], zs - 0.03), (c[0], c[1], zs - 0.002), R + 0.06, 16, 'dark_metal', 'drive', smooth=False)
        for q in D.ring_pts((c[0], c[1], zs - 0.03), EX, EY, R + 0.035, 10, 0.2):
            D.rivet(m, q, (0, 0, -1), r=0.016, h=0.009)
        D.cylinder(m, (c[0], c[1], zs - 0.335), (c[0], c[1], zs - 0.31), R * 0.7, 12, 'dark_metal', 'drive', smooth=False)
        D.cylinder(m, (c[0], c[1], zs - 0.20), (c[0], c[1], zs - 0.16), R + 0.012, 16, 'rust_red', 'drive', smooth=False)
        drives.append(c)
    # leg pump housings (aft legs, on the face toward the ship's centre and the bow)
    legs = {1: leg_info(ship, 262), -1: leg_info(ship, 286)}
    pipes = 0
    for side in (1, -1):
        L = legs[side]
        want = D.unit(np.array([1.0, -side * 1.0, 0.0]))
        cand = [L['e1'], -L['e1'], L['e2'], -L['e2']]
        nf = max(cand, key=lambda e: np.dot(e, want))
        nf = D.unit(np.array([nf[0], nf[1], 0.0]))
        uh = np.cross(EZ, nf)
        zh = 3.15
        o = leg_at(L, zh) + nf * (L['half'] + 0.006)
        D.housing(m, o, nf, uh, 0.36, 0.46, 0.13)
        lg['leg_housings'] = lg.get('leg_housings', 0) + 1
        # the pipe pair: up from the housing's top along the leg face, inboard under the slab, forward
        r_c, r_b = U['pipe_r']
        y_c, y_b = (side * U['pipe_y'][0], side * U['pipe_y'][1])
        z_c, z_b = 5.92, 5.935
        for k_, (rr, yy, zz, mat, du) in enumerate(((r_c, y_c, z_c, 'copper', -0.07), (r_b, y_b, z_b, 'brass', 0.07))):
            base = o + nf * (0.13 + 0.012 + 0.0) + uh * du
            p_start = leg_at(L, zh + 0.23 + 0.03)
            p_start = p_start + nf * (L['half'] + 0.006 + 0.075) + uh * du
            p_up = leg_at(L, 4.05) + nf * (L['half'] + 0.006 + 0.075) + uh * du
            p_v = np.array([p_up[0], p_up[1], 5.45 + 0.04 * k_])
            path = [p_start, p_up, p_v, np.array([p_up[0] + 0.40, yy, zz])]
            if side == 1:
                # port pair: forward to the winch motor box (x 28.65 .. 30.15, y 1.4 .. 2.4, top 5.8)
                xe = 29.05 + 0.25 * k_
                path += [np.array([xe - 0.4, yy, zz]), np.array([xe, 1.75 + 0.0 * k_, zz]),
                         np.array([xe, 1.75, 5.80 + 0.04])]
            else:
                # starboard pair: forward to the starboard turret drive housing (enters its aft side)
                xe = dx_ - R + 0.03
                path += [np.array([xe - 0.6, yy, zz]), np.array([xe, side * (dy_ - 0.10 + 0.17 * k_), zs - 0.17])]
            fl = [0.04, 0.5] + ([0.97] if side == -1 else [])
            # clamps hang from the joists the pipe passes under
            cl = []
            Pf = D.fillet_path(path, 0.25, seg=4)
            Lc = np.concatenate([[0], np.cumsum([np.linalg.norm(Pf[i + 1] - Pf[i]) for i in range(len(Pf) - 1)])])
            for (xj, hw) in joists:
                for i in range(len(Pf) - 1):
                    a, b = Pf[i], Pf[i + 1]
                    if (a[0] - xj) * (b[0] - xj) < 0 and abs(a[2] - b[2]) < 0.01:
                        fr = (Lc[i] + (xj - a[0]) / (b[0] - a[0]) * (Lc[i + 1] - Lc[i])) / Lc[-1]
                        cl.append(fr)
            sf = (lambda p, zj=zs - jd: (np.array([p[0], p[1], zj]), np.array([0.0, 0.0, -1.0])))
            D.pipe_run(m, path, rr, 0.25, sides=12, mat=mat, flange_at=fl, clamp_at=cl, surf_fn=sf)
            pipes += 1
            if side == 1:
                D.gland(m, path[-1] - np.array([0, 0, 0.04]), (0, 0, 1), (1, 0, 0), rr)
    lg['pipes'] = pipes
    return drives


# ================================================================== legs, hang strips, chain brackets
def legs(ship, m, K, log):
    """sleeve bands on the four legs, knee gussets at their tops (in the truss plane)"""
    lg = log.setdefault('legs', {})
    for isl in (262, 263, 286, 287):
        L = leg_info(ship, isl)
        ax, e1, e2, h = L['ax'], L['e1'], L['e2'], L['half']
        e2o = D.unit(e2 - e1 * np.dot(e1, e2))
        a3 = np.cross(e1, e2o)
        if np.dot(a3, ax) < 0:
            e2o = -e2o
            a3 = -a3
        for z in (2.62, 3.95):
            c = leg_at(L, z)
            obox(m, c, e1, e2o, a3, h + 0.018, h + 0.018, 0.035, 'rust_red', 'band', bevel=0.006)
            for s1 in (-1, 1):
                D.rivet(m, c + e1 * s1 * (h + 0.018 + 0.002), e1 * s1, r=0.016, h=0.009)
                D.rivet(m, c + e2o * s1 * (h + 0.018 + 0.002), e2o * s1, r=0.016, h=0.009)
        # knee gusset: triangle from the leg top along the bottom chord (in the truss plane, y = chord centre)
        side = 1 if L['top'][1] > 0 else -1
        yk = side * 2.6
        xt = L['top'][0]
        for dirx in (-1, 1):
            p_leg = leg_at(L, 4.0)
            tri = [(xt + dirx * 0.12, 4.24), (xt + dirx * 0.55, 4.24), (p_leg[0] + dirx * 0.12, 4.0)]
            if dirx < 0 and xt - 0.55 < 10.55:
                continue
            extrude_poly(m, tri, np.array([0.0, yk, 0.0]), EX, EZ, EY, 0.025, 'rust_red', 'knee')
        lg['legs'] = lg.get('legs', 0) + 1


def hang_strips(ship, m, K, log):
    """rust bands at the visible joints of the four hang strips (above the deck), a riveted cleat at their tops"""
    n = 0
    for part in ('HangStrip_1', 'HangStrip_2', 'HangStrip_3', 'HangStrip_4'):
        ids = sorted(i for i, r in ship.islands.items() if r['part'] == part)
        segs = []
        for i in ids:
            P = isl_verts(ship, i)
            c = P.mean(0)
            U_, s_, Vt = np.linalg.svd(P - c)
            ax = Vt[0]
            t = (P - c) @ ax
            a, b = c + ax * t.min(), c + ax * t.max()
            if a[2] < b[2]:
                a, b = b, a
            segs.append((a, b))
        segs.sort(key=lambda s: -s[0][2])
        joints = [s[1] for s in segs[:-1]]
        yc = segs[0][0][1]
        for j, q in enumerate(joints):
            if q[2] < 2.75:
                continue
            d1 = D.unit(segs[j][1] - segs[j][0])
            d2 = D.unit(segs[j + 1][1] - segs[j + 1][0])
            t = D.unit(d1 + d2)
            nrm = D.unit(np.cross(t, EY))
            obox(m, np.array([q[0], yc, q[2]]), t, EY, np.cross(t, EY), 0.05, 0.218, 0.038, 'rust_red', 'band',
                 bevel=0.005)
            for sy in (-1, 1):
                for sn in (-1, 1):
                    D.rivet(m, np.array([q[0], yc + sy * 0.12, q[2]]) + nrm * sn * 0.039, nrm * sn, r=0.016, h=0.009)
            n += 1
        # cleat at the top, against the bottom chord; strips inboard of the truss get a short beam out to the chord
        a = segs[0][0]
        obox(m, np.array([a[0], yc, a[2] - 0.13]), EX, EY, EZ, 0.07, 0.218, 0.11, 'rust_red', 'cleat', bevel=0.006)
        if abs(yc) < 2.45:
            sg = 1 if yc > 0 else -1
            y0, y1 = yc + sg * 0.2, sg * 2.5
            obox(m, (a[0], (y0 + y1) / 2, 4.35), EX, EY, EZ, 0.075, abs(y1 - y0) / 2 + 0.005, 0.09, 'dark_metal',
                 'cleat')
            for dx in (-0.04, 0.04):
                D.rivet(m, (a[0] + dx, (y0 + y1) / 2, 4.26), (0, 0, -1), r=0.016, h=0.009)
        n += 1
    log['hang_strip_bands'] = n


def chain_brackets(ship, m, K, log):
    """riveted brackets from the bottom chord out to the chain ends that hang beside it (ChainAft both ends: Hull bone;
    ChainFwd's upper end: the chain swings about the line through it)"""
    pts = [((12.2, 3.10, 4.35), 1), ((16.2, 3.40, 4.00), 1)]   # ChainFwd hangs inside the bow wedge: no bracket
    n = 0
    for (p, side) in pts:
        p = np.asarray(p, float)
        y0 = side * 2.70
        top = 4.47 if p[2] > 4.2 else 4.30
        z_b = max(p[2] + 0.06, 4.30)
        y1 = p[1] + side * 0.06
        # horizontal arm under the chord's level, from the chord face out past the chain end
        obox(m, (p[0], (y0 + y1) / 2, z_b + 0.03), EX, EY, EZ, 0.07, abs(y1 - y0) / 2, 0.03, 'rust_red', 'bracket',
             bevel=0.005)
        # triangular web under it against the chord
        tri = [(y0, z_b), (y1 - side * 0.02, z_b), (y0, z_b - 0.22)]
        extrude_poly(m, [(abs(a), b) for a, b in tri], np.array([p[0], 0.0, 0.0]), EY * side, EZ, EX, 0.022,
                     'rust_red', 'bracket')
        # lug plate down to the chain end
        if p[2] < 4.2:
            obox(m, (p[0], p[1], (p[2] + z_b) / 2 + 0.03), EX, EY, EZ, 0.05, 0.012, (z_b - p[2]) / 2 + 0.02,
                 'dark_metal', 'bracket')
        for dx in (-0.04, 0.04):
            D.rivet(m, (p[0] + dx, (y0 + y1) / 2, z_b + 0.06), (0, 0, 1), r=0.016, h=0.009)
        n += 1
    log['chain_brackets'] = n


# ================================================================== the heavy link chain (replaces the ChainAft bars)
def chain_line(ship, part):
    """the chain's centre line from its bar islands (ordered along x), smoothed"""
    segs = []
    for i, r in ship.islands.items():
        if r['src'] == 'Gantry' and r['part'] == part and r.get('piece') == 'link':
            P = isl_verts(ship, i)
            c = P.mean(0)
            U_, s_, Vt = np.linalg.svd(P - c)
            t = (P - c) @ Vt[0]
            a, b = c + Vt[0] * t.min(), c + Vt[0] * t.max()
            if a[0] > b[0]:
                a, b = b, a
            segs.append((a, b))
    segs.sort(key=lambda s: s[0][0])
    pts = [segs[0][0]] + [(segs[i][1] + segs[i + 1][0]) / 2 for i in range(len(segs) - 1)] + [segs[-1][1]]
    return D.fillet_path(pts, 0.45, seg=5, min_turn=3.0)


def link_chain(m, pts, link=0.30, wire=0.032, mat='dark_metal', kind='chain', sides=4):
    """links along a polyline (D.chain's link: a 6 x `sides` swept stadium loop, consecutive links turned 90 degrees)"""
    P = [np.asarray(p, float) for p in pts]
    Lc = np.concatenate([[0], np.cumsum([np.linalg.norm(P[i + 1] - P[i]) for i in range(len(P) - 1)])])
    step = link * 0.78
    k = int(Lc[-1] // step)
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
            b = m.verts(D.ring_pts(loop[q], pn, rad, wire, sides, math.pi / sides))
            idx.append(list(range(b, b + sides)))
        for q in range(6):
            m.bridge(idx[q], idx[(q + 1) % 6], mat, False, kind)
    return k


# ================================================================== winches: bearings (Hull), rope layers + bolts (Winch_*)
def ring_solid(m, c, ax, r_in, r_out, a0, a1, sides, mat, kind, smooth=False):
    """annulus prism round the axis ax through c, from a0 to a1 along ax"""
    ax = D.unit(ax)
    u, v, _ = D.ortho_frame(ax, (0.0, 0.0, 1.0)) if abs(ax[2]) < 0.9 else D.ortho_frame(ax, (1.0, 0.0, 0.0))
    c = np.asarray(c, float)
    rings = [D.ring_pts(c + ax * a, u, v, r, sides) for (a, r) in ((a0, r_out), (a1, r_out), (a1, r_in), (a0, r_in))]
    idx = []
    for rg in rings:
        b = m.verts(rg)
        idx.append(list(range(b, b + sides)))
    for i in range(4):
        m.bridge(idx[i], idx[(i + 1) % 4], mat, smooth, kind)


def arc_shell(m, c, ax, up, r_in, r_out, a0, a1, ang0, ang1, k, mat, kind):
    """part of a tube wall (angles ang0..ang1 measured from `up` round ax), closed solid"""
    ax = D.unit(ax)
    up = D.unit(np.asarray(up, float) - ax * np.dot(up, ax))
    sd = np.cross(ax, up)
    c = np.asarray(c, float)
    angs = np.radians(np.linspace(ang0, ang1, k + 1))
    def ring(a, r):
        return [c + ax * a + r * (math.cos(t) * up + math.sin(t) * sd) for t in angs]
    L = [ring(a0, r_out), ring(a1, r_out), ring(a1, r_in), ring(a0, r_in)]
    idx = []
    for rg in L:
        b = m.verts(rg)
        idx.append(list(range(b, b + len(rg))))
    for i in range(4):
        m.bridge(idx[i], idx[(i + 1) % 4], mat, False, kind, closed=False)
    # the two end caps wind opposite ways (review fix 2026-11-28: both had the same winding, so one cap of each hood
    # faced inward and showed as a backface)
    m.face([idx[0][0], idx[1][0], idx[2][0], idx[3][0]], mat, False, kind)
    m.face([idx[3][-1], idx[2][-1], idx[1][-1], idx[0][-1]], mat, False, kind)


def winches(ship, hull_m, w_m, K, log):
    W = K['winch']
    n = 0
    for name, xw in (('Winch_Aft', 28.3), ('Winch_Fwd', 30.4)):
        w_m.cur_group = name
        c = np.array([xw, 0.0, 5.0])
        # rope layer: a ridged sleeve on each half of the drum, clear of the middle hanger. Winch_Fwd has none: its
        # drum already runs through the bottom cross beam at x 30.6 (base model), a spinning rope would rub it
        for s in ((1, -1) if name == 'Winch_Aft' else ()):
            prof = []
            ys = np.arange(W['keep_y'], 1.36 + 1e-6, W['rope_step'] / 2)     # 4 cm clear of the motor box (y 1.4)
            for i, y in enumerate(ys):
                prof.append((y, W['rope_r'][i % 2]))
            idx = []
            for (y, r) in [(ys[0], 0.70)] + prof + [(ys[-1], 0.70)]:
                b = w_m.verts(D.ring_pts(c + EY * (s * y), EX, EZ, r, 14, 0.11))
                idx.append(list(range(b, b + 14)))
            for i in range(len(idx) - 1):
                w_m.bridge(idx[i], idx[i + 1], 'steel', False, 'rope', flip=(s < 0))
            w_m.cap(idx[0], 'steel', 'rope', flip=(s > 0))
            w_m.cap(idx[-1], 'steel', 'rope', flip=(s < 0))
        # bolt circle on the starboard flange's outer face (the port flanges face the motor box)
        for q in D.ring_pts(c + EY * (-1.632), EX, EZ, W['bolt_r'], W['bolts'], 0.13):
            D.rivet(w_m, q, (0, -1, 0), r=0.022, h=0.012)
        n += 1
        # bearings on the Hull: axle stub, bearing block, hanger plate up to the slab
        for s in (1, -1):
            D.cylinder(hull_m, c + EY * s * 1.665, c + EY * s * 1.85, 0.17, 14, 'machinery', 'bearing', smooth=True)
            D.cylinder(hull_m, c + EY * s * 1.848, c + EY * s * 1.875, 0.11, 12, 'dark_metal', 'bearing', smooth=False)
            for q in D.ring_pts(c + EY * s * 1.85, EX, EZ, 0.14, 6, 0.26):
                D.rivet(hull_m, q, (0, s, 0), r=0.014, h=0.008)
            obox(hull_m, (xw, s * 1.76, (5.14 + 6.195) / 2), EX, EY, EZ, 0.08, 0.022, (6.195 - 5.14) / 2 + 0.002,
                 'rust_red', 'bearing')
            for zz in (5.55, 5.95):
                D.rivet(hull_m, (xw, s * (1.76 + 0.024), zz), (0, s, 0), r=0.016, h=0.009)
    log['winches'] = n


# ================================================================== search lights: posts and heads
def lights(ship, post_m, head_m, K, log):
    spec = C.load_json(C.CHECKS + '/bones_spec.json')['bones']
    n = 0
    for L in ('AftL', 'MidL', 'MidR', 'FwdC'):
        post_ids = [i for i, r in ship.islands.items() if r['part'] == 'SearchLight_' + L and r.get('piece') == 'post']
        P = isl_verts(ship, post_ids[0])
        x, y = P[:, 0].mean(), P[:, 1].mean()
        zt = P[:, 2].max()
        zb = spec['SearchLight_' + L]['head'][2]
        piv = np.array(spec['SearchLight_%s_Head' % L]['head'])
        # ---- post (moves with the post bone)
        post_m.cur_group = 'SearchLight_' + L
        a = np.array([x, y, 0.0])
        D.cylinder(post_m, a + EZ * (zb + 0.10), a + EZ * (zb + 0.42), K['lights']['sleeve_r'], 10, 'dark_metal', 'sleeve',
                   smooth=True)
        D.cylinder(post_m, a + EZ * (zb + 0.38), a + EZ * (zb + 0.44), 0.125, 10, 'rust_red', 'sleeve', smooth=False)
        for q in D.ring_pts(a + EZ * (zb + 0.41), EX, EY, 0.126, 4, 0.4):
            D.rivet(post_m, q, D.unit(q - (a + EZ * (zb + 0.41))), r=0.014, h=0.008)
        # junction box: on the side away from the rails that pass the post, at a height clear of their bars (the
        # posts wobble +-4 deg, so 10 cm clear in z): MidL / MidR above the fore deck's top rail, AftL between its rails
        near = []
        for i_, P_ in rail_islands(ship)[1]:
            c_ = P_.mean(0)
            dxy = np.linalg.norm(P_[:, :2] - np.array([x, y]), axis=1).min()
            if dxy < 0.6:
                near.append((P_[:, 2].min(), P_[:, 2].max(), c_))
        zbx = zb + 1.18
        for zc_ in np.arange(zb + 0.75, zb + 1.8, 0.05):
            if all(zc_ - 0.14 > hi + 0.10 or zc_ + 0.14 < lo - 0.10 for lo, hi, _ in near):
                zbx = zc_
                break
        away = np.zeros(3)
        for lo, hi, c_ in near:
            dd = np.array([x - c_[0], y - c_[1], 0.0])
            away += dd / max(np.linalg.norm(dd), 1e-6)
        if np.linalg.norm(away) < 1e-6:
            away = np.array([-1.0, -np.sign(y), 0.0])
        nb = D.unit(np.array([-1.0, 0.0, 0.0]) + 1.2 * D.unit(np.array([0.0, away[1], 0.0]) if abs(away[1]) > 1e-6 else np.zeros(3)))
        ub = np.cross(EZ, nb)
        log.setdefault('light_boxes', {})[L] = dict(z=round(float(zbx), 2), rails_near=len(near),
                                                    dir=[round(float(v), 2) for v in nb])
        cbx = a + EZ * zbx + nb * (0.07 + 0.006 + 0.06)
        obox(post_m, cbx, ub, EZ, nb, 0.075, 0.12, 0.06, 'machinery', 'jbox', bevel=0.01)
        obox(post_m, cbx + nb * 0.066, ub, EZ, nb, 0.058, 0.095, 0.007, 'dark_metal', 'jbox', bevel=0.003)
        for su in (-1, 1):
            obox(post_m, cbx + nb * 0.075 + ub * su * 0.04 + EZ * 0.10, ub, EZ, nb, 0.008, 0.022, 0.006, 'steel', 'jbox')
        for dz in (-0.09, 0.09):
            D.cylinder(post_m, a + EZ * (zbx + dz - 0.015), a + EZ * (zbx + dz + 0.015), 0.085, 8, 'dark_metal', 'jbox',
                       smooth=False)
        # top collar under the head's turntable
        D.cylinder(post_m, a + EZ * (zt - 0.40), a + EZ * (zt - 0.25), K['lights']['collar_r'], 10, 'dark_metal',
                   'collar', smooth=True)
        for q in D.ring_pts(a + EZ * (zt - 0.25), EX, EY, 0.082, 6, 0.3):
            D.rivet(post_m, q, EZ, r=0.012, h=0.007)
        # conduit from the box up the post into the collar, three clips
        o_c = nb * 0.098
        path = [cbx + EZ * 0.12 - nb * 0.035, a + o_c + EZ * (zbx + 0.30), a + o_c + EZ * (zt - 0.48),
                a + nb * 0.06 + EZ * (zt - 0.36)]
        D.tube(post_m, D.fillet_path(path, 0.06, seg=3), 0.016, sides=6, mat='brass', kind='conduit')
        for zc in np.linspace(zbx + 0.45, zt - 0.6, 3):
            obox(post_m, a + nb * 0.088 + EZ * zc, ub, EZ, nb, 0.026, 0.012, 0.022, 'dark_metal', 'conduit')
        # ---- head (pans with the head bone)
        head_m.cur_group = 'SearchLight_%s_Head' % L
        px, py, pz = piv
        hc = np.array([px, py, pz])
        ring_solid(head_m, hc, EX, 0.262, 0.338, 0.22, 0.31, 16, 'brass', 'bezel')
        arc_shell(head_m, hc, EX, EZ, 0.345, 0.372, 0.05, 0.42, -65.0, 65.0, 8, 'dark_metal', 'hood')
        for xf in (-0.27, -0.17):
            ring_solid(head_m, hc, EX, 0.296, 0.356, xf - 0.0125, xf + 0.0125, 12, 'dark_metal', 'fins')
        D.cylinder(head_m, hc + EX * (-0.375), hc + EX * (-0.345), 0.24, 12, 'dark_metal', 'cap', smooth=False)
        D.cylinder(head_m, hc + EX * (-0.43), hc + EX * (-0.37), 0.04, 8, 'brass', 'cap', smooth=False)
        for s in (1, -1):
            D.cylinder(head_m, hc + EY * s * 0.295, hc + EY * s * 0.385, 0.055, 10, 'dark_metal', 'yoke', smooth=False)
            seg_box(head_m, hc + EY * s * 0.365, hc + EY * s * 0.365 - EZ * 0.385, EX, 0.026, 0.0125, 'rust_red', 'yoke')
            seg_box(head_m, hc + EY * s * 0.378 - EZ * 0.37, hc + EY * s * 0.125 - EZ * 0.37, EX, 0.026, 0.0125,
                    'rust_red', 'yoke')
        ring_solid(head_m, hc - EZ * 0.39, EZ, 0.10, 0.145, 0.0, 0.04, 12, 'rust_dark', 'yoke')
        hp = [hc + np.array([-0.17, 0, 0.29]), hc + np.array([-0.17, 0, 0.39]), hc + np.array([0.02, 0, 0.39]),
              hc + np.array([0.02, 0, 0.29])]
        D.tube(head_m, D.fillet_path(hp, 0.04, seg=2), 0.016, sides=6, mat='steel', kind='handle')
        n += 1
    log['lights'] = n


# ================================================================== rails: collars along the whole ship
def rail_islands(ship):
    posts, rails = [], []
    for i, r in ship.islands.items():
        if r['src'] not in ('DeckRails', 'Gantry') or r['part'] != 'Hull':
            continue
        P = isl_verts(ship, i)
        if len(P) != 8:
            continue
        mn, mx = P.min(0), P.max(0)
        d = mx - mn
        if d[2] > 0.9 and d[0] < 0.15 and d[1] < 0.15:
            posts.append((i, P))
        elif d[2] < 0.12 and max(d[0], d[1]) > 0.4:
            rails.append((i, P))
    return posts, rails


def rail_collars(ship, m, K, log, extra_posts=(), extra_rails=()):
    posts, rails = rail_islands(ship)
    n_base_posts = len(posts)
    posts = list(posts) + list(extra_posts)
    rails = list(rails) + list(extra_rails)
    rinfo = []
    for i, P in rails:
        c = P.mean(0)
        d2 = P[:, :2] - c[:2]
        U_, s_, Vt = np.linalg.svd(d2)
        ax = np.array([Vt[0][0], Vt[0][1], 0.0])
        sd = np.array([-ax[1], ax[0], 0.0])
        rel = P - c
        rinfo.append(dict(i=i, c=c, ax=ax, sd=sd, mn=P.min(0), mx=P.max(0),
                          hw=0.5 * float(np.ptp(rel @ sd)), hh=0.5 * float(np.ptp(P[:, 2])),
                          t0=float((rel @ ax).min()), t1=float((rel @ ax).max())))
    n, skipped = 0, 0
    L = K['rails']['collar_len']
    for ip, (i, P) in enumerate(posts):
        kind = 'collar' if ip < n_base_posts else 'guard'
        c = P.mean(0)
        z0, z1 = P[:, 2].min(), P[:, 2].max()
        for r in rinfo:
            if not (r['c'][2] > z0 + 0.3 and r['c'][2] < z1 + 0.08):
                continue
            t = float(np.dot(c - r['c'], r['ax']))
            dside = abs(float(np.dot(c - r['c'], r['sd'])))
            if t < r['t0'] - 0.06 or t > r['t1'] + 0.06 or dside > 0.08:
                continue
            q = np.array([c[0], c[1], r['c'][2]])
            hw = max(r['hw'], 0.045) + 0.014
            corners = [q + sa * r['ax'] * L / 2 + sb * r['sd'] * hw + sc * EZ * (r['hh'] + 0.014) for sa in (-1, 1)
                       for sb in (-1, 1) for sc in (-1, 1)]
            if Z.keep_clear_hits(corners):
                skipped += 1
                continue
            obox(m, q, r['ax'], r['sd'], EZ, L / 2, hw, r['hh'] + 0.014, K['rails']['mat'], kind)
            n += 1
    log['rail_collars'] = dict(collars=n, skipped_keep_clear=skipped, posts=len(posts), rails=len(rails))


def guard_rails(m, P, K, log):
    """new guard rails along the platform's open aft edge (x 10.6), from the stairs' hand rails to the side rails'
    corner posts (y +-3.05); same section and heights as the platform's own rails. Returns their extents (for the
    collision boxes) and the new posts / rails (for collars)"""
    G = K['guard']
    f = P['flights'][-1]
    yc = f['p0'][1]
    yl = yc + (f['w'] / 2 + ST.FL_W / 2)
    yr = yc - (f['w'] / 2 + ST.FL_W / 2)
    out, posts, rails = [], [], []
    for (ya, yb, nm) in ((yr, -3.05, 'Guard_Stbd'), (yl, 3.05, 'Guard_Port')):
        s = 1 if yb > ya else -1
        span = abs(yb - ya) - 0.045
        k = max(1, int(math.ceil(span / G['step'])))
        ys = [ya + s * span * j / k for j in range(k)]
        for y in ys:
            obox(m, (G['x'], y, (6.55 + G['top'] - 0.03) / 2), EX, EY, EZ, G['post'], G['post'],
                 (G['top'] - 0.03 - 6.55) / 2 + 0.001, 'dark_metal', 'guard')
            Pp = np.array([[G['x'] + sx * G['post'], y + sy * G['post'], z] for sx in (-1, 1) for sy in (-1, 1)
                           for z in (6.55, G['top'] - 0.03)])
            posts.append((-1, Pp))
        y_end = yb - s * 0.045
        for zr in (G['top'], G['mid']):
            yc_ = (ya + y_end) / 2
            hl = abs(y_end - ya) / 2
            obox(m, (G['x'], yc_, zr - 0.03), EX, EY, EZ, 0.03, hl, 0.03, 'dark_metal', 'guard')
            Pr = np.array([[G['x'] + sx * 0.03, yc_ + sy * hl, zr - 0.03 + sz * 0.03] for sx in (-1, 1)
                           for sy in (-1, 1) for sz in (-1, 1)])
            rails.append((-1, Pr))
        out.append(dict(name='Stairs_' + nm, x=(G['x'] - 0.06, G['x'] + 0.06), y=tuple(sorted((ya, yb))),
                        z=(6.55, G['top'] + 0.03), why='new guard rail on the platform\'s open aft edge'))
    log['guard_rails'] = dict(sections=len(out), posts=len(posts))
    return out, posts, rails


# ================================================================== checks particular to this zone
def walk_check(meshes, ship, zi, K):
    """detail vertices standing free on a walkable top: inside a PA box footprint, within K['walk']['layer'] above its
    top, and more than K['walk']['free'] from any existing non-walkable SM_Airship geometry (posts, legs, walls). The
    stairs object and the new guard rails carry their own collision (stairs_collision.json) and are left out."""
    B = json.load(open(K_PA))['hull_boxes']
    boxes = []
    for b in B:
        a_ = np.array(b['min']) / 100.0; c_ = np.array(b['max']) / 100.0
        boxes.append((np.array([a_[0], -c_[1], a_[2]]), np.array([c_[0], -a_[1], c_[2]]), b['name']))
    obst = np.array([w not in ('deck / walkable', 'walkable top of a part') for w in zi.why])
    bvh = ship.bvh(obst)
    free, attached, tested, truss_in = {}, 0, 0, {}
    worst = None
    for name, m in meshes.items():
        if name == 'Stairs' or not m.v:
            continue
        vk = CK.vertex_kinds(m)
        co = np.asarray(m.v)
        for k in range(len(co)):
            if vk[k] == 'guard':
                continue
            p = co[k]
            for mn, mx, bn in boxes:
                if mn[0] <= p[0] <= mx[0] and mn[1] <= p[1] <= mx[1] and mx[2] - 0.01 <= p[2] <= mx[2] + K['walk']['layer']:
                    tested += 1
                    h = bvh.find_nearest(V(p), K['walk']['free'])
                    if h[0] is not None:
                        attached += 1
                    elif bn.startswith(('Hull_Well', 'Hull_Bow')):
                        # the bow wedge's top (z 4.28) runs inside the truss under the slab: the underside pieces
                        # hang 1.6+ m above it, inside the truss, where nobody walks
                        truss_in[name + '/' + vk[k]] = truss_in.get(name + '/' + vk[k], 0) + 1
                    elif p[2] - mx[2] > K['walk']['overhead']:
                        truss_in['overhead/' + name + '/' + vk[k]] = truss_in.get('overhead/' + name + '/' + vk[k], 0) + 1
                    else:
                        free[name + '/' + vk[k]] = free.get(name + '/' + vk[k], 0) + 1
                        worst = [round(float(v), 3) for v in p] + [bn]
                    break
    return dict(verts_in_walk_layer=tested, attached_to_existing_obstacles=attached, free_standing=free,
                inside_truss_or_overhead=truss_in,
                free_standing_total=int(sum(free.values())), example=worst, layer_m=K['walk']['layer'],
                free_m=K['walk']['free'])


def stairs_probe(P, stairs_mesh, ship, others):
    """head room above the walking line (vertical rays from 5 cm above the nosing line) and clear width (horizontal
    rays left / right from the flight's centre line, 0.3 .. 1.8 m above the nosing line), against the ship, the other
    detail objects and the stairs themselves"""
    co = [np.asarray(ship.co)]
    tri = []
    off = len(ship.co)
    for p in ship.polys:
        for i in range(1, len(p) - 1):
            tri.append((p[0], p[i], p[i + 1]))
    for m in list(others) + [stairs_mesh]:
        if not m.v:
            continue
        co.append(np.asarray(m.v))
        for f in m.f:
            for i in range(1, len(f) - 1):
                tri.append((f[0] + off, f[i] + off, f[i + 1] + off))
        off += len(m.v)
    allco = np.concatenate(co)
    bvh = BVHTree.FromPolygons(allco.tolist(), tri, all_triangles=True)
    head, width = 9.0, 9.0
    hw_at = None
    for f in P['flights']:
        p0, d, l, z = ST.flight_frame(f)
        se = ST.flight_end_s(f)
        for s in np.arange(-0.25, se + 0.001, 0.1):
            q = ST.pt(f, s, 0.0, ST.nose_z(f, s) + 0.05)
            h = bvh.ray_cast(V(q), V((0, 0, 1)), 9.0)
            hd = 9.0 if h[0] is None else h[3] + 0.05
            head = min(head, hd)
            for hh in (0.3, 0.8, 1.3, 1.8):
                q = ST.pt(f, s, 0.0, ST.nose_z(f, s) + hh)
                ws = []
                for sg in (-1, 1):
                    h = bvh.ray_cast(V(q), V(l * sg), 3.0)
                    ws.append(3.0 if h[0] is None else h[3])
                if sum(ws) < width:
                    width, hw_at = sum(ws), [round(float(v), 2) for v in q]
    return dict(min_head_room_m=round(head, 3), min_clear_width_m=round(width, 3), narrowest_at=hw_at,
                ok=bool(head >= ST.MIN_HEAD and width >= ST.MIN_WIDTH))


# ================================================================== build
def build(ship, zi, deleted, K, rng, log):
    meshes = {}
    for name, grp in (('Stairs', 'Hull'), ('Gantry', 'Hull'), ('Rails', 'Hull'), ('LightPosts', None),
                      ('LightHeads', None), ('Winches', None)):
        meshes[name] = D.Mesh(name)
        meshes[name].cur_group = grp
    # ---- stairs (Talal's point 3)
    noprops = (ship.p_src != 'DeckProps') & ~deleted
    bvh = ship.bvh(noprops)

    def deck_z(x, y):
        h = bvh.ray_cast(V((x, y, 5.0)), V((0, 0, -1)), 6.0)
        return float(h[0][2])
    SK = K['stairs']
    probe = ST.plan(SK['option'], 2.39, 6.55, w=SK['w'], going=SK['going'], landing=SK['landing'])
    f0 = probe['flights'][0]
    z_deck = deck_z(f0['p0'][0] - 0.3, f0['p0'][1])
    h = bvh.ray_cast(V((10.8, f0['p0'][1], 12.0)), V((0, 0, -1)), 20.0)
    z_top = float(h[0][2])
    P = ST.plan(SK['option'], z_deck, z_top, w=SK['w'], going=SK['going'], landing=SK['landing'])
    P['deck_fn'] = deck_z
    if SK.get('rail'):
        P['rail'] = dict(SK['rail'])
    log['stairs'] = dict(plan={k: v for k, v in P.items() if k != 'deck_fn'}, usability=ST.usability(P))
    log['stairs'].update(ST.build_stairs(meshes['Stairs'], P, rng))
    guard, gposts, grails = guard_rails(meshes['Rails'], P, K, log)
    # ---- gantry structure
    g = meshes['Gantry']
    truss(ship, g, K, log)
    fascia(ship, g, rng, K, log)
    underside(ship, g, rng, K, log)
    legs(ship, g, K, log)
    hang_strips(ship, g, K, log)
    chain_brackets(ship, g, K, log)
    if any(e.get('id') == 'z7_chain_aft_bars' for _, e in BE.load_entries('z7')):
        meshes['Chains'] = D.Mesh('Chains')
        meshes['Chains'].cur_group = 'Hull'
        CK_ = K['chain']
        log['chain_links'] = link_chain(meshes['Chains'], chain_line(ship, 'ChainAft'), CK_['link'], CK_['wire'],
                                        sides=CK_['sides'])
    winches(ship, g, meshes['Winches'], K, log)
    lights(ship, meshes['LightPosts'], meshes['LightHeads'], K, log)
    rail_collars(ship, meshes['Rails'], K, log, extra_posts=gposts, extra_rails=grails)
    log['_plan'] = P
    log['_guard'] = guard
    return {k: (v, 'Hull' if k in ('Stairs', 'Gantry', 'Rails', 'Chains') else None) for k, v in meshes.items()}


def main():
    o = opts()
    zn = '7'
    if o.get('rail-mat'):                   # comparison builds only (into rig/tmp): --rail-mat dark_metal
        K['stairs']['rail']['mat'] = o['rail-mat']
    coll_name, prefix = 'Detail_Z7', 'SM_AirshipDetail_Z7_'
    report_path = o.get('report') or (DOCS + '/z7_report.json')
    out_blend = o.get('blend-out') or D.zone_blend(zn)
    t0 = time.time()
    bpy.ops.wm.open_mainfile(filepath=C.RIG_BLEND)                 # read only: never saved under this name
    ship = S.Ship(bpy)
    mats = D.ensure_materials()
    zi = Z.ZoneIndex(ship)
    be_rep = {}
    deleted = BE.deleted_mask(ship, 'all', be_rep)
    log = {}
    rng = random.Random(K['seed'])
    parts = build(ship, zi, deleted, K, rng, log)
    P = log.pop('_plan')
    guard = log.pop('_guard')
    ship_bvh = ship.bvh(~deleted)
    dropped, flipped = {}, {}
    # pieces of different objects touch each other too (a conduit entering a post collar ...): test against all
    for name, (m, _) in parts.items():
        others = [BVHTree.FromPolygons(mm.v, [list(f) for f in mm.f]) for nn, (mm, _) in parts.items()
                  if nn != name and mm.f]
        for _ in range(3):
            dd = D.drop_floating(m, [ship_bvh] + others, tol=K['touch_tol'])
            if not dd:
                break
            for k_, v_ in dd.items():
                dropped.setdefault(name, {})[k_] = dropped.get(name, {}).get(k_, 0) + v_
        flipped[name] = m.orient_outward()
    log['floating_pieces_removed'] = dropped
    log['inside_out_pieces_flipped'] = flipped
    log['tris_by_kind'] = {n: m.tris_by_kind() for n, (m, _) in parts.items()}
    meshes = {n: m for n, (m, _) in parts.items()}
    log['walkable'] = walk_check(meshes, ship, zi, K)
    log['stairs_probe'] = stairs_probe(P, meshes['Stairs'], ship, [m for n, m in meshes.items() if n != 'Stairs'])
    coll = bpy.data.collections.get(coll_name) or bpy.data.collections.new(coll_name)
    if coll.name not in [c.name for c in bpy.context.scene.collection.children]:
        bpy.context.scene.collection.children.link(coll)
    objs = []
    for name, (m, bone) in parts.items():
        if not m.f:
            continue
        objs.append(m.to_object(prefix + name, coll, mats, arm=ship.arm, groups=bone if bone else list(m.g)))
    # collision boxes for the Unreal stage (UE cm, ship component space, like pa_hull_boxes.json)
    col = dict(about='Z7 stairs collision for PA_Airship (round 3, 2026-11-28). UE cm in the ship component space, the '
                     'pa_hull_boxes.json convention (UE = (100 x, -100 y, 100 z) of Blender metres). Each box: centre, '
                     'full size along its own X / Y / Z, rotation (pitch, yaw, roll deg), and its 8 corners. '
                     'walkable_ramp: top face through the tread nosings (36 deg, under the 44.76 deg walkable limit); '
                     'walkable: landing / top step; blocking: hand rails, landing columns, the new aft guard rails.',
               object='SM_AirshipDetail_Z7_Stairs (Hull bone); guard rails are in SM_AirshipDetail_Z7_Rails',
               rail_pieces_removed=[], base_edits_for_the_stairs=None,
               note='No rail or other base piece is removed for the stairs: the platform\'s aft edge (x 1050) has no '
                    'rail where they arrive, and the main-deck rails are not in the way. The deck crates (Hull_Props_02 '
                    '.. 06) stay. (Zone 7\'s only base edit, z7_chain_aft_bars, swaps the ChainAft bars for a link '
                    'chain; PA_Airship has no box for that chain.)',
               usability=ST.usability(P), boxes=ST.collision(P, guard))
    C.dump_json(col, DOCS + '/stairs_collision.json')
    rep = dict(zone=ZONE, knobs=K, log=log, base_edits=be_rep,
               tris={ob.name: int(sum(len(p.vertices) - 2 for p in ob.data.polygons)) for ob in objs},
               objects=[CK.object_report(ob, ZONE) for ob in objs],
               zone_checks=CK.zone_checks(objs, ZONE, ship, zi) if objs else None,
               seconds=round(time.time() - t0, 1))
    rep['tris_total'] = sum(rep['tris'].values())
    # per object: which zone owns the nearest SM_Airship face (volumes first), and how far from the ship it builds out
    surf_all = ship.surface(~deleted)
    per = {}
    for ob in objs:
        co = CK.world_co(ob)[::3]
        own, dist = {}, []
        for p in co:
            z_ = zi.zone_at(p)
            own[str(z_)] = own.get(str(z_), 0) + 1
            h = surf_all.bvh.find_nearest(V(p), 9.0)
            dist.append(9.0 if h[0] is None else h[3])
        dist = np.array(dist)
        per[ob.name] = dict(sampled=len(co), owner_of_nearest=own, max_dist_to_ship_m=round(float(dist.max()), 3),
                            p99_dist_to_ship_m=round(float(np.percentile(dist, 99)), 3),
                            p50_dist_to_ship_m=round(float(np.percentile(dist, 50)), 3))
    rep['per_object'] = per
    rep['all_objects_ok'] = all(r['ok'] for r in rep['objects'])
    C.dump_json(rep, report_path)
    print('[Z7] tris', rep['tris'], 'total', rep['tris_total'])
    print('[Z7] objects ok', rep['all_objects_ok'], json.dumps([{k: r[k] for k in ('object', 'ok', 'inside_out_pieces',
          'nonmanifold_edges', 'not_rigid_vertices', 'faces_without_role')} for r in rep['objects']]))
    print('[Z7] zone checks', json.dumps(rep['zone_checks'])[:2500])
    print('[Z7] walk', json.dumps(log['walkable']))
    print('[Z7] per object', json.dumps(rep['per_object']))
    print('[Z7] probe', json.dumps(log['stairs_probe']), json.dumps(log['stairs']['usability']))
    print('[Z7] dropped', json.dumps(dropped), 'flipped', json.dumps(flipped))
    print('[Z7] log', json.dumps({k: v for k, v in log.items() if k not in ('tris_by_kind', 'stairs')})[:2500])
    if not o.get('no-save'):
        print('[Z7] saved', D.safe_save(out_blend))
    print('[Z7] done %.1f s' % (time.time() - t0))
    sys.stdout.flush()


if __name__ == '__main__':
    main()
