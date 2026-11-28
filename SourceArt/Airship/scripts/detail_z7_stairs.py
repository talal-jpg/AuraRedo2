"""Zone 7 stairs (round 3, Talal 2026-11-28 point 3: "stairs, where looks better"): from the main deck up to the
forward turret deck (the gantry platform, 4.17 m higher).

Shared by detail_z7.py (the build) and detail_z7_mocks.py (the placement options). Plain numbers here, Blender world
metres (+X bow, +Y port, +Z up); UE cm = (100 x, -100 y, 100 z).

  plan(option, z_deck, z_top, ...)   -> dict: flights (start, direction, risers, riser, going, base z) + landings
  build_mock(mesh, plan)             -> simple boxes (placement study only)
  build_stairs(mesh, plan, rng)      -> the detailed stairs (rust steel channel stringers, riveted plank treads in steel
                                        frames, hand rails on steel posts (plan['rail']: steel tube since Talal's
                                        answer of 2026-11-28, wood before), a riveted landing on four columns)
  collision(plan)                    -> walkable ramps / landing / blocking boxes for PA_Airship (UE cm, ship space)
  usability(plan)                    -> riser, going, slope, widths (the checks of ZONE_7.md)
"""
import math
import numpy as np
import detail_common as D

# usability limits (UE CharacterMovement defaults: MaxStepHeight 45 cm, walkable floor 44.76 deg; mech capsule 141.6 cm)
MAX_RISER, MIN_GOING, MAX_SLOPE, MIN_WIDTH, MIN_HEAD = 0.22, 0.28, 38.0, 1.4, 2.2

ST_T = 0.08          # stringer (channel web) thickness
ST_UP, ST_DN = 0.10, 0.27     # stringer top edge above / bottom edge below the nosing line
RAIL_H = 0.95        # hand rail top above the nosing line
POST_STEP = 1.05     # hand rail posts, along the slope (horizontal)
# top rail of the hand rails: plan['rail'] (detail_z7.K['stairs']['rail']); without it the old wooden rail is built.
# Talal 2026-11-28, "make them steel": a steel tube on a small dark saddle at every post (detail_z7.py's default).
RAIL_WOOD = dict(mat='wood', r=0.034, sides=8, saddle=False)


def unit2(d):
    d = np.asarray(d, float)
    return d / np.linalg.norm(d)


def plan(option, z_deck, z_top, x_top=10.5, w=1.5, going=0.30, landing=1.5):
    """placement options (all clear width w between the stringers' inner faces):
    'central'  two straight flights on the deck's centre corridor between the crates (y 0.63), rising to the bow, a
               landing half way; arrives at the middle of the platform's open aft edge
    'port'     one straight flight along the port side outboard of the crates, a top landing that turns inboard to the
               platform's aft edge (inboard of the AftL search light post)
    'across'   one flight across the ship against the gantry's aft face, rising from port to starboard, a top landing
               at the platform's starboard aft corner"""
    H = z_top - z_deck
    n = int(math.ceil(H / MAX_RISER - 1e-9))
    r = H / n
    g = going
    W = w + 2 * ST_T
    P = dict(option=option, z_deck=z_deck, z_top=z_top, rise=H, risers=n, riser=r, going=g, w=w, W=W,
             slope_deg=math.degrees(math.atan2(r, g)), flights=[], landings=[], x_top=x_top)
    if option == 'central':
        yc = 0.63
        n1 = (n + 1) // 2                       # 10 risers up to the landing, 9 to the platform
        n2 = n - n1
        x0 = x_top - (n1 - 1) * g - landing - (n2 - 1) * g
        P['flights'].append(dict(p0=(x0, yc), d=(1.0, 0.0), n=n1, zb=z_deck))
        xl0 = x0 + (n1 - 1) * g
        P['landings'].append(dict(x=(xl0, xl0 + landing), y=(yc - W / 2, yc + W / 2), z=z_deck + n1 * r,
                                  posts=True, open_sides=('aft', 'fwd')))
        P['flights'].append(dict(p0=(xl0 + landing, yc), d=(1.0, 0.0), n=n2, zb=z_deck + n1 * r))
        P['top_opening'] = dict(x=x_top, y=(yc - W / 2, yc + W / 2))
    elif option == 'port':
        yc = 3.97
        x_end = 8.0
        x0 = x_end - (n - 1) * g
        P['flights'].append(dict(p0=(x0, yc), d=(1.0, 0.0), n=n, zb=z_deck))
        P['landings'].append(dict(x=(x_end, x_top + 0.05), y=(1.45, yc + W / 2 - 0.30), z=z_top, posts=True,
                                  open_sides=('aft_part', 'fwd_part')))
        P['top_opening'] = dict(x=x_top, y=(1.45, 3.2))
    elif option == 'across':
        xc = 9.6
        y0 = 3.55
        P['flights'].append(dict(p0=(xc, y0), d=(0.0, -1.0), n=n, zb=z_deck))
        y_end = y0 - (n - 1) * g
        P['landings'].append(dict(x=(xc - W / 2, x_top + 0.05), y=(-3.2, y_end), z=z_top, posts=True,
                                  open_sides=('port_part', 'fwd_part')))
        P['top_opening'] = dict(x=x_top, y=(-3.2, y_end))
    else:
        raise KeyError(option)
    for f in P['flights']:
        f['r'], f['g'], f['w'] = r, g, w
    return P


def flight_frame(f):
    d = np.array([f['d'][0], f['d'][1], 0.0])
    l = np.array([-f['d'][1], f['d'][0], 0.0])
    z = np.array([0.0, 0.0, 1.0])
    p0 = np.array([f['p0'][0], f['p0'][1], f['zb']])
    return p0, d, l, z


def nose_z(f, s):
    """nosing line height at s (metres along the flight from its first riser)"""
    return f['zb'] + f['r'] + s * f['r'] / f['g']


def flight_end_s(f):
    return (f['n'] - 1) * f['g']


def usability(P):
    out = dict(risers=P['risers'], riser_m=round(P['riser'], 4), going_m=P['going'],
               slope_deg=round(P['slope_deg'], 2), clear_width_m=P['w'],
               flights=[dict(risers=f['n'], run_m=round(flight_end_s(f), 2)) for f in P['flights']],
               rise_m=round(P['rise'], 3))
    out['ok'] = (P['riser'] <= MAX_RISER + 1e-9 and P['going'] >= MIN_GOING and P['slope_deg'] <= MAX_SLOPE
                 and P['w'] >= MIN_WIDTH)
    return out


# ------------------------------------------------------------------ small geometry helpers
def obox(mesh, c, ax, ay, az, hx, hy, hz, mat, kind, bevel=0.0):
    """box centred at c with half sizes along the (right-handed) unit axes ax, ay, az"""
    D.chamfer_box(mesh, D.frame_matrix(np.asarray(c, float), ax, ay, az), hx, hy, hz, c=bevel, mat=mat, kind=kind)


def seg_box(mesh, a, b, side, hw, hh, mat, kind, bevel=0.0, ext=0.0):
    """box from point a to point b (centre line), half width hw along `side` (unit, normal to b - a), half height hh
    along the third axis"""
    a, b = np.asarray(a, float), np.asarray(b, float)
    t = D.unit(b - a)
    s = D.unit(np.asarray(side, float) - t * np.dot(side, t))
    u = np.cross(t, s)
    L = np.linalg.norm(b - a) / 2 + ext
    obox(mesh, (a + b) / 2, t, s, u, L, hw, hh, mat, kind, bevel)


def extrude_poly(mesh, pts, O, U, Vv, N, t, mat, kind, smooth=False):
    """convex polygon pts [(u, v)] in the plane O + U u + Vv v, extruded from -t/2 to +t/2 along N (closed prism)"""
    P = [np.asarray(O) + U * u + Vv * v for (u, v) in pts]
    if np.dot(np.cross(P[1] - P[0], P[2] - P[0]), N) < 0:
        P = P[::-1]
    bot = [p - N * t / 2 for p in P]
    top = [p + N * t / 2 for p in P]
    mesh.prism(bot, top, mat, smooth, kind)


# ------------------------------------------------------------------ mock (placement study)
def build_mock(mesh, P):
    for f in P['flights']:
        p0, d, l, z = flight_frame(f)
        w, g, r, n = f['w'], f['g'], f['r'], f['n']
        for k in range(1, n):
            sc = (k - 1) * g + g / 2 - 0.0125
            c = p0 + d * sc + z * (k * r - 0.0225)
            obox(mesh, c, d, l, z, (g + 0.025) / 2, w / 2, 0.0225, 'wood', 'tread')
        se = flight_end_s(f)
        for side in (-1, 1):
            off = l * side * (w / 2 + ST_T / 2)
            a = p0 + off + d * (-0.25) + z * (nose_z(f, -0.25) - f['zb'] - 0.08)
            b = p0 + off + d * se + z * (nose_z(f, se) - f['zb'] - 0.08)
            seg_box(mesh, a, b, l, ST_T / 2, 0.17, 'rust_red', 'stringer')
            a2 = a + z * (RAIL_H + 0.08)
            b2 = b + z * (RAIL_H + 0.08)
            seg_box(mesh, a2, b2, l, 0.03, 0.03, 'wood', 'rail')
            for s in np.arange(0.2, se + 0.01, POST_STEP):
                q = p0 + off + d * s + z * (nose_z(f, s) - f['zb'])
                obox(mesh, q + z * (RAIL_H / 2), d, l, z, 0.025, 0.025, RAIL_H / 2, 'dark_metal', 'post')
    for L in P['landings']:
        (x0, x1), (y0, y1), zl = L['x'], L['y'], L['z']
        ex, ey, ez = np.eye(3)
        obox(mesh, ((x0 + x1) / 2, (y0 + y1) / 2, zl - 0.06), ex, ey, ez, (x1 - x0) / 2, (y1 - y0) / 2, 0.06,
             'rust_red', 'landing')
        for (px, py) in ((x0 + 0.1, y0 + 0.1), (x1 - 0.1, y0 + 0.1), (x0 + 0.1, y1 - 0.1), (x1 - 0.1, y1 - 0.1)):
            if px > P['x_top'] - 0.05:
                continue
            obox(mesh, (px, py, (P['z_deck'] + zl - 0.12) / 2), ex, ey, ez, 0.06, 0.06,
                 (zl - 0.12 - P['z_deck']) / 2, 'dark_metal', 'post')
    return mesh


# ------------------------------------------------------------------ the detailed stairs
FL_W = 0.10          # stringer flange width (the channel: web + top and bottom flanges pointing outward)
WEB_T = 0.05         # stringer web thickness
FL_T = 0.022         # flange thickness
RIV = dict(r=0.022, h=0.012)


def pt(f, s, t, h):
    """point of flight f: s along the flight from its first riser, t lateral (+ = left of the walking direction),
    h absolute height"""
    p0, d, l, z = flight_frame(f)
    return np.array([p0[0], p0[1], 0.0]) + d * s + l * t + z * h


def stringer(mesh, f, side, foot_z, rng=None):
    """rust channel stringer on one side of flight f (side +1 left, -1 right): a web plate cut level at the foot and
    plumb at the top, top and bottom flanges pointing outward, two rows of rivets on the web's outer face"""
    p0, d, l, z = flight_frame(f)
    g, r, n, w = f['g'], f['r'], f['n'], f['w']
    se = flight_end_s(f)
    k = r / g
    s_t0 = (foot_z - (f['zb'] + r) - ST_UP) / k
    s_b0 = (foot_z - (f['zb'] + r) + ST_DN) / k
    tc = side * (w / 2 + WEB_T / 2)
    O = np.array([p0[0], p0[1], 0.0]) + l * tc
    poly = [(s_t0, foot_z), (s_b0, foot_z), (se, nose_z(f, se) - ST_DN), (se, nose_z(f, se) + ST_UP)]
    extrude_poly(mesh, poly, O, d, z, l, WEB_T, 'rust_red', 'stringer')
    # flanges (outward): top along the top line, bottom along the bottom line
    tf = side * (w / 2 + FL_W / 2)
    sa = s_t0 + 0.06
    for (s0, off) in ((sa, ST_UP - FL_T / 2), (s_b0 + 0.03, -ST_DN + FL_T / 2)):
        a = pt(f, s0, tf, nose_z(f, s0) + off)
        b = pt(f, se, tf, nose_z(f, se) + off)
        seg_box(mesh, a, b, l, FL_W / 2, FL_T / 2, 'rust_red', 'stringer')
    # rivets on the web's outer face, two rows, every 0.28 m
    n_out = l * side
    to = side * (w / 2 + WEB_T + 0.002)
    nr = 0
    for s in np.arange(max(0.12, s_b0 + 0.15), se - 0.05, 0.28):
        D.rivet(mesh, pt(f, s, to, nose_z(f, s) - 0.07), n_out, **RIV)
        nr += 1
    return dict(s_top0=s_t0, s_bot0=s_b0, rivets=nr)


def treads(mesh, f):
    """open-riser treads: a dark steel tray, three wooden planks across the flight, a rust nosing angle with two rivets"""
    p0, d, l, z = flight_frame(f)
    g, r, n, w = f['g'], f['r'], f['n'], f['w']
    for kk in range(1, n):
        s0 = (kk - 1) * g
        zt = f['zb'] + kk * r
        # tray under the planks (between the stringer webs, 3 mm clear of them)
        c = pt(f, s0 + (g - 0.03) / 2, 0.0, zt - 0.0585)
        obox(mesh, c, d, l, z, (g + 0.02) / 2, w / 2 - 0.003, 0.0165, 'dark_metal', 'tread', bevel=0.004)
        # planks (run across the flight), 8 mm gaps
        a, b = s0 + 0.031, s0 + g - 0.006
        pw = (b - a - 2 * 0.008) / 3
        for i in range(3):
            sa = a + i * (pw + 0.008)
            c = pt(f, sa + pw / 2, 0.0, zt - 0.021)
            obox(mesh, c, d, l, z, pw / 2, w / 2 - 0.012, 0.021, 'wood', 'tread')
        # nosing angle (3 mm proud of the planks)
        c = pt(f, s0 + 0.0, 0.0, zt - 0.036)
        obox(mesh, c, d, l, z, 0.025, w / 2 - 0.003, 0.039, 'rust_red', 'tread')
        for tt in (-1, 1):
            D.rivet(mesh, pt(f, s0, tt * (w / 2 - 0.09), zt + 0.003), z, r=0.016, h=0.008)


def rail_saddle(mesh, c, d, l, z, rail):
    """small dark saddle on a post top (c = the post's top centre) that the steel top rail sits in"""
    if rail.get('saddle'):
        hs = 0.015
        obox(mesh, np.asarray(c, float) + z * hs, d, l, z, 0.032, 0.03, hs, 'dark_metal', 'rail', bevel=0.004)


def handrail(mesh, f, side, s_from, s_to, extra_end=None, rail=None):
    """posts on the top flange (every POST_STEP), a top rail RAIL_H above the nosing line (rail: material, radius,
    sides, saddles; default the old wooden rail), a steel mid rail outside the posts. extra_end: (point) the rail
    continues level to this point (joins a guard post)"""
    rail = rail or RAIL_WOOD
    p0, d, l, z = flight_frame(f)
    w = f['w']
    tc = side * (w / 2 + FL_W / 2)
    ss = list(np.arange(s_from, s_to - 0.2, POST_STEP)) + [s_to]
    posts = []
    for s in ss:
        zb_ = nose_z(f, s) + ST_UP
        top = nose_z(f, s) + RAIL_H - 0.03
        c = pt(f, s, tc, (zb_ + top) / 2)
        obox(mesh, c, d, l, z, 0.025, 0.025, (top - zb_) / 2, 'dark_metal', 'rail')
        obox(mesh, pt(f, s, tc, zb_ + 0.006), d, l, z, 0.05, 0.045, 0.006, 'dark_metal', 'rail')
        rail_saddle(mesh, pt(f, s, tc, top), d, l, z, rail)
        posts.append(s)
    # top rail (tube), from the first to the last post
    path = [pt(f, s_from - 0.04, tc, nose_z(f, s_from - 0.04) + RAIL_H), pt(f, s_to, tc, nose_z(f, s_to) + RAIL_H)]
    if extra_end is not None:
        path.append(np.asarray(extra_end, float))
    D.tube(mesh, D.fillet_path(path, 0.06, seg=3, min_turn=5.0), rail['r'], sides=rail['sides'], mat=rail['mat'],
           kind='rail')
    # steel mid rail (flat bar outside the posts)
    tm = side * (w / 2 + FL_W / 2 + 0.025 + 0.009)
    a = pt(f, s_from, tm, nose_z(f, s_from) + 0.50)
    b = pt(f, s_to, tm, nose_z(f, s_to) + 0.50)
    seg_box(mesh, a, b, l, 0.009, 0.022, 'dark_metal', 'rail', ext=0.03)
    return posts


def landing(mesh, P, L, rng=None):
    """riveted landing on four round columns: rust channel frame (sides in line with the stringers), wooden planks
    across, a dark middle joist, X braces on the two outer sides, foot and cap plates"""
    (x0, x1), zl = L['x'], L['z']
    f = P['flights'][0]
    yc = f['p0'][1]
    w = f['w']
    ex, ey, ez = np.eye(3)
    dfn = P.get('deck_fn') or (lambda x, y: P['z_deck'])
    # side channels: web + flanges, top flush with the planks
    for side in (-1, 1):
        yw = yc + side * (w / 2 + WEB_T / 2)
        obox(mesh, ((x0 + x1) / 2, yw, zl - ST_DN / 2 - 0.001), ex, ey, ez, (x1 - x0) / 2, WEB_T / 2,
             ST_DN / 2 - 0.001, 'rust_red', 'landing')
        yf = yc + side * (w / 2 + FL_W / 2)
        for zf in (zl - FL_T / 2, zl - ST_DN + FL_T / 2):
            obox(mesh, ((x0 + x1) / 2, yf, zf), ex, ey, ez, (x1 - x0) / 2, FL_W / 2, FL_T / 2, 'rust_red', 'landing')
        for xx in np.arange(x0 + 0.14, x1 - 0.05, 0.28):
            for dz in (-0.06, -0.20):
                D.rivet(mesh, (xx, yc + side * (w / 2 + WEB_T + 0.002), zl + dz), (0, side, 0), **RIV)
    # end channels under the planks (aft and fore), middle joist
    for xe in (x0 + 0.03, x1 - 0.03):
        obox(mesh, (xe, yc, zl - 0.042 - 0.11), ex, ey, ez, 0.03, w / 2 - 0.003, 0.11, 'rust_red', 'landing')
    obox(mesh, ((x0 + x1) / 2, yc, zl - 0.042 - 0.08), ex, ey, ez, 0.04, w / 2 - 0.003, 0.08, 'dark_metal', 'landing')
    # planks across (along y)
    n_p = int((x1 - x0 - 0.01) // 0.148)
    pw = (x1 - x0 - 0.01 - (n_p - 1) * 0.008) / n_p
    for i in range(n_p):
        xa = x0 + 0.005 + i * (pw + 0.008)
        obox(mesh, (xa + pw / 2, yc, zl - 0.021), ex, ey, ez, pw / 2, w / 2 - 0.003, 0.021, 'wood', 'landing')
    # columns + plates + braces
    zc_top = zl - ST_DN
    cols = []
    for side in (-1, 1):
        yy = yc + side * (w / 2 + WEB_T / 2)
        for xx in (x0 + 0.09, x1 - 0.09):
            zd = dfn(xx, yy)
            D.cylinder(mesh, (xx, yy, zd + 0.012), (xx, yy, zc_top - 0.012), 0.052, 10, 'dark_metal', 'column',
                       smooth=True)
            obox(mesh, (xx, yy, zc_top - 0.007), ex, ey, ez, 0.075, 0.06, 0.007, 'rust_red', 'column')
            obox(mesh, (xx, yy, zd + 0.008), ex, ey, ez, 0.10, 0.10, 0.008, 'dark_metal', 'column')
            for sx in (-1, 1):
                for sy in (-1, 1):
                    D.rivet(mesh, (xx + sx * 0.07, yy + sy * 0.07, zd + 0.016), (0, 0, 1), r=0.014, h=0.008)
            # riveted band a third of the way up
            D.cylinder(mesh, (xx, yy, zd + 0.62), (xx, yy, zd + 0.68), 0.064, 10, 'rust_red', 'column', smooth=False)
            cols.append((xx, yy))
        # X braces between the two columns of this side, on its outer face
        yo = yy + side * (0.052 + 0.016)
        za, zb2 = dfn(x0, yy) + 0.35, zc_top - 0.10
        xa, xb = x0 + 0.09, x1 - 0.09
        for k_, (pa, pb) in enumerate((((xa, za), (xb, zb2)), ((xb, za), (xa, zb2)))):
            off = side * (0.0 if k_ == 0 else 0.026)
            seg_box(mesh, (pa[0], yo + off, pa[1]), (pb[0], yo + off, pb[1]), (0, 1, 0), 0.0125, 0.035,
                    'rust_red', 'brace')
        D.rivet(mesh, ((xa + xb) / 2, yo + side * 0.040, (za + zb2) / 2), (0, side, 0), **RIV)
    return cols


def build_stairs(mesh, P, rng=None):
    """the stairs of plan P (option 'central'): two flights, a landing, hand rails, cleats at the platform"""
    log = dict(rivets=0, rail=dict(P.get('rail') or RAIL_WOOD))
    rail = P.get('rail') or RAIL_WOOD
    fs = P['flights']
    zd = P['z_deck']
    for i, f in enumerate(fs):
        foot = f['zb']
        treads(mesh, f)
        p0, d, l, z = flight_frame(f)
        se = flight_end_s(f)
        for side in (-1, 1):
            st = stringer(mesh, f, side, foot)
            log['rivets'] += st['rivets']
            if i == 0:
                # foot plate under the stringer foot on the deck
                sa, sb = st['s_top0'], st['s_bot0']
                c = pt(f, (sa + sb) / 2, side * (w_half(f) + WEB_T / 2), zd + 0.008)
                obox(mesh, c, d, l, z, (sb - sa) / 2 + 0.06, 0.075, 0.008, 'dark_metal', 'foot')
                for ss in (sa - 0.02, sb + 0.02):
                    for tt in (-1, 1):
                        D.rivet(mesh, pt(f, ss, side * (w_half(f) + WEB_T / 2) + tt * 0.05, zd + 0.016), z,
                                r=0.014, h=0.008)
            # hand rail: flight 1 from its foot to the landing; flight 2 from the landing to the platform edge
            if i == 0:
                handrail(mesh, f, side, 0.10, se, rail=rail)
            else:
                end = pt(f, se + (P['x_top'] + 0.10 - (p0[0] + se)), side * (w_half(f) + FL_W / 2),
                         nose_z(f, se) + RAIL_H)
                handrail(mesh, f, side, -f['g'] + 0.06, se - 0.03, extra_end=end, rail=rail)
                # cleat angle bolted to the platform's aft face, beside the stringer's top end
                tcl = side * (w_half(f) + FL_W + 0.05)
                c = pt(f, se - 0.06, tcl, nose_z(f, se) - 0.18)
                obox(mesh, c, d, l, z, 0.06, 0.05, 0.15, 'rust_dark', 'cleat', bevel=0.006)
                for dz in (-0.27, -0.09):
                    D.rivet(mesh, pt(f, se - 0.06, tcl + side * 0.052, nose_z(f, se) + dz), l * side, **RIV)
    for L in P['landings']:
        landing(mesh, P, L, rng)
        landing_rails(mesh, P, L, rail)
    return log


def landing_rails(mesh, P, L, rail=None):
    """the hand rails along the landing's two sides: they join flight 1's rail (at the landing's aft edge) to flight
    2's (which starts one going before its first riser); one post in the middle, a steel mid rail"""
    rail = rail or RAIL_WOOD
    (x0, x1), zl = L['x'], L['z']
    f1, f2 = P['flights'][0], P['flights'][1]
    yc = f1['p0'][1]
    ex, ey, ez = np.eye(3)
    xe = x1 - f2['g'] + 0.06 - 0.04
    for side in (-1, 1):
        yy = yc + side * (f1['w'] / 2 + FL_W / 2)
        zr0 = zl + RAIL_H
        zr1 = nose_z(f2, xe - f2['p0'][0]) + RAIL_H
        xm = (x0 + xe) / 2
        obox(mesh, (xm, yy, (zl + zl + RAIL_H - 0.03) / 2), ex, ey, ez, 0.025, 0.025, (RAIL_H - 0.03) / 2, 'dark_metal',
             'rail')
        obox(mesh, (xm, yy, zl + 0.006), ex, ey, ez, 0.05, 0.045, 0.006, 'dark_metal', 'rail')
        rail_saddle(mesh, (xm, yy, zl + RAIL_H - 0.03), ex, ey, ez, rail)
        D.tube(mesh, [np.array([x0 - 0.02, yy, zr0]), np.array([xe + 0.02, yy, zr1])], rail['r'], sides=rail['sides'],
               mat=rail['mat'], kind='rail')
        ym = yc + side * (f1['w'] / 2 + FL_W / 2 + 0.025 + 0.009)
        seg_box(mesh, (x0, ym, zl + 0.50), (xe + 0.04, ym, zl + 0.50 + (zr1 - zr0)), ey, 0.009, 0.022, 'dark_metal',
                'rail')


def w_half(f):
    return f['w'] / 2


# ------------------------------------------------------------------ collision for PA_Airship (UE cm, ship space)
def ue(p):
    return [round(100.0 * float(p[0]), 1), round(-100.0 * float(p[1]), 1), round(100.0 * float(p[2]), 1)]


def ue_box(name, kind, c, ax, ay, az, hx, hy, hz, why):
    """an oriented box (Blender centre, unit axes, half sizes in metres) in the pa_hull_boxes.json convention: UE cm,
    ship component space. rotation: UE (pitch, yaw, roll) degrees of the box's local axes; corners for checking."""
    c = np.asarray(c, float)
    ax, ay, az = (np.asarray(v, float) for v in (ax, ay, az))
    corners = [ue(c + sx * hx * ax + sy * hy * ay + sz * hz * az) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    # UE axes: X = (x, -y, z) of Blender; pitch from the local X axis (yaw 0 boxes only here)
    axu = np.array([ax[0], -ax[1], ax[2]])
    pitch = math.degrees(math.asin(max(-1.0, min(1.0, axu[2]))))
    yaw = math.degrees(math.atan2(axu[1], axu[0]))
    return dict(name=name, kind=kind, center=ue(c), size=[round(200 * hx, 1), round(200 * hy, 1), round(200 * hz, 1)],
                rotation=dict(pitch=round(pitch, 3), yaw=round(yaw, 3), roll=0.0),
                min=[min(q[i] for q in corners) for i in range(3)], max=[max(q[i] for q in corners) for i in range(3)],
                corners=corners, why=why)


def collision(P, guard=None):
    """walkable ramps (top face through the tread nosings), the landing, a top step that overlaps the platform box,
    hand rail blocking boxes, the landing columns and the platform's new aft guard rails"""
    out = []
    ex, ey, ez = np.eye(3)
    T = 0.20
    fs = P['flights']
    for i, f in enumerate(fs):
        p0, d, l, z = flight_frame(f)
        se = flight_end_s(f)
        s0 = -f['g'] - 0.05
        a = pt(f, s0, 0.0, nose_z(f, s0))
        b = pt(f, se, 0.0, nose_z(f, se))
        t = D.unit(b - a)
        nrm = np.cross(t, l)
        if nrm[2] < 0:
            nrm = -nrm
        c = (a + b) / 2 - nrm * T / 2
        L = np.linalg.norm(b - a)
        out.append(ue_box('Stairs_Ramp%d' % (i + 1), 'walkable_ramp', c, t, np.cross(nrm, t), nrm, L / 2,
                          f['w'] / 2 + 0.05, T / 2, 'flight %d: top face through the tread nosings, %.1f deg' %
                          (i + 1, math.degrees(math.atan2(f['r'], f['g'])))))
        Hh = 1.0
        for side in (-1, 1):
            tcen = side * (f['w'] / 2 + FL_W / 2)
            a2 = pt(f, s0 + 0.15, tcen, nose_z(f, s0 + 0.15) + Hh / 2)
            b2 = pt(f, se, tcen, nose_z(f, se) + Hh / 2)
            out.append(ue_box('Stairs_Rail%d%s' % (i + 1, 'L' if side > 0 else 'R'), 'blocking',
                              (a2 + b2) / 2, t, np.cross(nrm, t), nrm, np.linalg.norm(b2 - a2) / 2, 0.06, Hh / 2,
                              'hand rail of flight %d (keeps players on the treads)' % (i + 1)))
    for k, L_ in enumerate(P['landings']):
        (x0, x1), (y0, y1), zl = L_['x'], L_['y'], L_['z']
        out.append(ue_box('Stairs_Landing', 'walkable', ((x0 + x1) / 2, (y0 + y1) / 2, zl - T / 2), ex, ey, ez,
                          (x1 - x0) / 2 + 0.05, (y1 - y0) / 2, T / 2, 'landing half way up'))
        f = fs[0]
        yc = f['p0'][1]
        for side in (-1, 1):
            yy = yc + side * (f['w'] / 2 + FL_W / 2)
            out.append(ue_box('Stairs_LandingRail%s' % ('L' if side > 0 else 'R'), 'blocking',
                              ((x0 + x1) / 2, yy, zl + 0.5), ex, ey, ez, (x1 - x0) / 2, 0.06, 0.5, 'landing hand rail'))
            for xx in (x0 + 0.09, x1 - 0.09):
                yw = yc + side * (f['w'] / 2 + WEB_T / 2)
                zc0, zc1 = P['z_deck'], zl - ST_DN
                out.append(ue_box('Stairs_Column', 'blocking', (xx, yw, (zc0 + zc1) / 2), ex, ey, ez, 0.06, 0.06,
                                  (zc1 - zc0) / 2, 'landing column'))
    f = fs[-1]
    xt = P['x_top']
    out.append(ue_box('Stairs_TopStep', 'walkable', (xt, f['p0'][1], P['z_top'] - T / 2), ex, ey, ez, 0.15,
                      f['w'] / 2 + 0.05, T / 2, 'bridges the stairs to the platform box (Hull_Platform_00_0 starts at '
                      'UE x 1055, the slab edge is at 1050)'))
    for g_ in (guard or []):
        (gx0, gx1), (gy0, gy1), (gz0, gz1) = g_['x'], g_['y'], g_['z']
        out.append(ue_box(g_['name'], 'blocking', ((gx0 + gx1) / 2, (gy0 + gy1) / 2, (gz0 + gz1) / 2), ex, ey, ez,
                          (gx1 - gx0) / 2, (gy1 - gy0) / 2, (gz1 - gz0) / 2, g_['why']))
    return out
