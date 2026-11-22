"""Step 1: place the helm + 4 cannons on SM_Airship (RIG_CONTRACT.md section 4) and sweep their motions for clearance.

  blender -b --factory-startup rig/AirshipRig_src.blend --python rig/scripts/rig_place.py -- [--out checks/rig/placement.json]

Read-only: never saves a .blend. AirshipRig_src.blend is a byte copy (cp) of Talal's StylizedAirship.blend.
Writes the placement (used by rig_build.py) and the clearance report into checks/rig/.

Placement rules:
  * helm pedestal origin on the centreline at x -6.5, z = lowest deck point under the base plate (nothing floats);
    wheel axle = pedestal + Helm.blend wheel origin offset (-0.63, 0, 1.65); pilot 1.3 m aft of the axle on the deck.
  * cannons broadside (X_cannon = +Y for L, -Y for R), x snapped to the middle of the rail-post gap nearest to the
    target (C.CANNON_TARGET_X: -0.46 fwd, -11.3 aft), y so the muzzle face centre is 0.12 m inside the rail centre line, z = lowest deck
    point under the 4 wheels (no wheel floats). If the motion sweep finds a rail contact inside the target ranges the
    cannon is moved inboard in 1 cm steps (reported as a nudge).
Clearance method: BVH triangle overlap of the moved cannon parts against SM_Airship (the wheels are tested against
everything except the hull skin, whose deck they stand on; their sink/float is measured separately), against the helm
and the other cannons at rest. A contact counts only if the static island was not already touched at rest.
"""
import bpy, sys, os, math, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from mathutils import Vector as V, Matrix
from mathutils.bvhtree import BVHTree
import rig_common as C

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
OUT = argv[argv.index('--out') + 1] if '--out' in argv else C.PLACEMENT_JSON
ROLL = (argv[argv.index('--cannon-roll') + 1] if '--cannon-roll' in argv else 'on') == 'on'
MIN_RAIL_CLEAR = float(argv[argv.index('--min-rail-clear') + 1]) if '--min-rail-clear' in argv else 0.02
T0 = time.time()

# ------------------------------------------------------------------ ship
ship = bpy.data.objects['SM_Airship']
assert ship.matrix_world == Matrix.Identity(4)
co, polys = C.mesh_arrays(ship.data)
VP = C.load_json(C.RESEARCH + '/sm_airship_vertex_parts.json')
ISL = C.load_json(C.RESEARCH + '/sm_airship_islands.json')
assert len(co) == VP['n_verts'] == 36908
visl = np.array(VP['vertex_island'])
fisl = np.array([visl[p[0]] for p in polys])
IS = {r['id']: r for r in ISL['islands']}
tolist = co.tolist()


def bvh_faces(mask):
    idx = np.nonzero(mask)[0]
    return BVHTree.FromPolygons(tolist, [polys[i] for i in idx]), idx


ALL, ALL_IDX = bvh_faces(np.ones(len(polys), bool))
SHELL, SHELL_IDX = bvh_faces(fisl == C.SHELL_ISLAND)
NOSHELL, NOSHELL_IDX = bvh_faces(fisl != C.SHELL_ISLAND)
src = np.array([IS[int(i)]['src'] for i in fisl])
RAILS, RAILS_IDX = bvh_faces(src == 'DeckRails')


def deck_at(x, y):
    """first hit straight down: (z, normal_z, island, is_open_deck)"""
    h = ALL.ray_cast(V((x, y, 12.0)), V((0, 0, -1)), 30.0)
    if h[0] is None:
        return None
    isl = int(fisl[ALL_IDX[h[2]]])
    return dict(z=h[0].z, nz=h[1].z, island=isl, src=IS[isl]['src'], deck=(isl == C.SHELL_ISLAND and h[1].z > 0.9))


def shell_z(x, y):
    h = SHELL.ray_cast(V((x, y, 12.0)), V((0, 0, -1)), 30.0)
    return None if h[0] is None else h[0].z


# ------------------------------------------------------------------ props (geometry only, appended from AirshipProps.blend)
with bpy.data.libraries.load(C.PROPS_BLEND, link=False) as (src_d, dst_d):
    dst_d.objects = [n for n in src_d.objects if n.startswith('Cannon_') or n.startswith('Helm_')]
PO = {o.name: o for o in dst_d.objects if o is not None}
PART = {}   # name -> (carriage/pedestal-space coords, polys, shells)
for n, o in PO.items():
    if o.type != 'MESH':
        continue
    c, p = C.mesh_arrays(o.data)
    PART[n] = (C.xform(c, o.matrix_basis), p, C.loose_parts(len(c), p))
print('[place] props', sorted(PART))
for n in ('Cannon_Barrel', 'Cannon_Quoin', 'Helm_Wheel'):
    print('[place] origin', n, C.r3(PO[n].location))
assert (PO['Helm_Wheel'].location - C.HELM_WHEEL_OFS).length < 1e-6
assert (PO['Cannon_Barrel'].location - C.C_TRUNNION).length < 1e-6
assert (PO['Cannon_Quoin'].location - C.C_QUOIN).length < 1e-6
assert (PO['Cannon_Muzzle'].matrix_world.translation - C.C_MUZZLE).length < 1e-6 if PO['Cannon_Muzzle'].parent is None else True


def part_bvh(name, M):
    c, p, _ = PART[name]
    return BVHTree.FromPolygons(C.xform(c, M).tolist(), p)


def contacts(bvh, static, idx):
    """set of static islands touched"""
    return {int(fisl[idx[j]]) for _, j in bvh.overlap(static)}


R = {'method': __doc__.split('Clearance method:')[1].strip(), 'deck_props': [], 'cannons': {}, 'helm': {}}

# ------------------------------------------------------------------ rails
rails = [r for r in ISL['islands'] if r['src'] == 'DeckRails']
posts = [r for r in rails if r['bbmax'][2] - r['bbmin'][2] > 0.9]


def side_posts(s):
    return sorted([r for r in posts if np.sign(r['c'][1]) == s], key=lambda r: r['c'][0])


def gap_for(target_x, s):
    P = side_posts(s)
    gaps = []
    for a, b in zip(P[:-1], P[1:]):
        mx = (a['c'][0] + b['c'][0]) / 2
        gaps.append((abs(mx - target_x), mx, a, b))
    gaps.sort(key=lambda g: g[0])
    return gaps


def rail_line(a, b, x):
    t = (x - a['c'][0]) / (b['c'][0] - a['c'][0])
    return dict(y=a['c'][1] + t * (b['c'][1] - a['c'][1]), foot_z=a['bbmin'][2] + t * (b['bbmin'][2] - a['bbmin'][2]),
                slope_deg=math.degrees(math.atan2(b['c'][1] - a['c'][1], b['c'][0] - a['c'][0])),
                post_a=C.r3(a['c'][:2], 3), post_b=C.r3(b['c'][:2], 3),
                gap=math.hypot(b['c'][0] - a['c'][0], b['c'][1] - a['c'][1]))


# ------------------------------------------------------------------ helm
def place_helm():
    ped = PART['Helm_Pedestal'][0]
    lo, hi = ped.min(0), ped.max(0)
    pts = [(HX + dx, dy) for HX in (C.HELM_X,) for dx in np.linspace(lo[0], hi[0], 5) for dy in np.linspace(lo[1], hi[1], 5)]
    dz = [deck_at(x, y) for x, y in pts]
    assert all(d and d['deck'] for d in dz), [d for d in dz if not (d and d['deck'])]
    zs = [d['z'] for d in dz]
    z = deck_at(C.HELM_X, 0.0)['z']      # contract: deck height at the pedestal origin
    plate_bottom = float(ped[:, 2].min())   # the base plate reaches below its origin (-0.05)
    assert z + plate_bottom <= min(zs) + 1e-6, 'helm plate would float'
    base = V((C.HELM_X, 0.0, z))
    wheel = base + C.HELM_WHEEL_OFS
    px = wheel.x - C.PILOT_BEHIND_AXLE
    pd = deck_at(px, 0.0)
    return dict(pedestal=C.r3(base), wheel_axle=C.r3(wheel), pilot=C.r3((px, 0.0, pd['z'])), pilot_on_deck=pd['deck'],
                deck_z_under_plate=[round(min(zs), 4), round(max(zs), 4)], plate_z_local=[plate_bottom, 0.06],
                plate_sunk_m=[round(min(zs) - (z + plate_bottom), 4), round(max(zs) - (z + plate_bottom), 4)],
                plate_top_above_deck_m=[round(z + 0.06 - max(zs), 4), round(z + 0.06 - min(zs), 4)],
                origin_ue_cm=C.ue_cm(base), wheel_axle_ue_cm=C.ue_cm(wheel), pilot_ue_cm=C.ue_cm((px, 0.0, pd['z'])))


H = place_helm()
R['helm'].update(H)
print('[place] helm', H)
HELM_M = Matrix.Translation(V(H['pedestal']))
helm_static = [part_bvh('Helm_Pedestal', HELM_M), part_bvh('Helm_Wheel', HELM_M)]


# ------------------------------------------------------------------ cannon geometry under motion
def cannon_mats(origin, side, yaw=0.0, elev=0.0, recoil=0.0, roll=None):
    """world matrices for each cannon part (carriage-space coords -> world)"""
    Mc = C.cannon_frame(origin, side, roll_deg=ROLLS.get(tuple(origin), 0.0) if roll is None else roll)
    aim = (Mc.to_3x3() @ V((1, 0, 0))).normalized()
    Dc = C.rot_about(origin, (0, 0, 1), yaw) @ Matrix.Translation(-aim * recoil)
    base = Dc @ Mc
    out = {'Carriage': base,
           'Barrel': base @ C.rot_about(C.C_TRUNNION, (0, 1, 0), -elev),
           'Quoin': base @ Matrix.Translation(V((-C.quoin_slide(elev), 0, 0)))}
    for w, wc in C.C_WHEELS.items():
        out['Wheel_' + w] = base @ C.rot_about(wc, (0, 1, 0), -math.degrees(recoil / C.C_WHEEL_R))
    return out


def cannon_bvhs(origin, side, **kw):
    M = cannon_mats(origin, side, **kw)
    return {p: part_bvh('Cannon_' + p, M[p]) for p in C.CANNON_PARTS}, M


def wheel_state(M):
    """per wheel: (lowest wheel point - deck under its axle centre); + = floating, - = sunk; and deck under it open?"""
    out = {}
    for w, wc in C.C_WHEELS.items():
        c = C.xform(PART['Cannon_Wheel_' + w][0], M['Wheel_' + w])
        ctr = M['Carriage'] @ wc
        d = deck_at(ctr.x, ctr.y)
        out[w] = (float(c[:, 2].min() - d['z']) if d else None, bool(d and d['deck']))
    return out


def muzzle_rail_clearance(M, n=400):
    """smallest distance from the barrel's muzzle half (x > 1.0 in carriage space) and the carriage to the rails"""
    best = 9.0
    c, _, _ = PART['Cannon_Barrel']
    sel = c[:, 0] > 1.0
    for q in C.xform(c[sel], M['Barrel']):
        hit = RAILS.find_nearest(V(q), 1.0)
        if hit[0] is not None:
            best = min(best, hit[3])
    return best


def evaluate_pose(origin, side, rest_cont, others, **kw):
    B, M = cannon_bvhs(origin, side, **kw)
    new = {}
    for p, b in B.items():
        static, idx = (NOSHELL, NOSHELL_IDX) if p.startswith('Wheel') else (ALL, ALL_IDX)
        cs = contacts(b, static, idx) - rest_cont[p]
        if cs:
            new[p] = sorted(cs)
        if any(b.overlap(o) for o in others):
            new.setdefault(p, []).append('prop')
    return new, M


def sweep(origin, side, rest_cont, others, key, lim, step, fixed):
    """walk from 0 toward lim; return last clear value (refined to step/4)"""
    def blocked(v):
        kw = dict(fixed); kw[key] = v
        return evaluate_pose(origin, side, rest_cont, others, **kw)[0]
    v, last = 0.0, 0.0
    sgn = 1 if lim > 0 else -1
    hit = None
    while abs(v) < abs(lim) - 1e-9:
        v = round(v + sgn * step, 6)
        h = blocked(v)
        if h:
            hit = h
            lo, hi = last, v
            for _ in range(3):
                m = (lo + hi) / 2
                if blocked(m):
                    hi = m
                else:
                    lo = m
            return round(lo, 3), hit
        last = v
    return round(lim, 3), None


ROLLS = {}


def place_cannon(c, others, nudge=0.0, gap_rank=0):
    s = C.CANNON_SIDE[c]
    g = gap_for(C.CANNON_TARGET_X[c], s)[gap_rank]
    x = g[1]
    rl = rail_line(g[2], g[3], x)
    y = rl['y'] - s * (C.C_MUZZLE.x + C.MUZZLE_INSIDE_RAIL + nudge)
    Mc0 = C.cannon_frame((x, y, 0.0), s)
    dz = {w: deck_at(*(Mc0 @ V((wc.x, wc.y, 0)))[:2]) for w, wc in C.C_WHEELS.items()}
    assert all(d and d['deck'] for d in dz.values()), (c, dz)
    if ROLL:
        # seat all 4 wheels: deck height at the carriage origin + roll about the firing axis by the deck's slope
        # along the axles (cannon +Y side minus -Y side over the 1.05 m track)
        zl = (dz['FL']['z'] + dz['BL']['z']) / 2; zr = (dz['FR']['z'] + dz['BR']['z']) / 2
        roll = math.degrees(math.atan2(zl - zr, 2 * C.C_WHEELS['FL'].y))
        z = deck_at(x, y)['z']
    else:
        roll = 0.0
        z = min(d['z'] for d in dz.values())
    origin = V((x, y, z))
    ROLLS[tuple(origin)] = roll
    # footprint on open deck (carriage + wheels), nothing else on top
    fp = []
    for fx in np.linspace(-0.88, 0.83, 6):
        for fy in np.linspace(-0.6, 0.6, 5):
            q = Mc0 @ V((fx, fy, 0))
            d = deck_at(q.x, q.y)
            fp.append(bool(d and d['deck']))
    # rest contacts (things already touching at rest, e.g. nothing expected)
    B, M = cannon_bvhs(origin, s)
    rest_cont = {}
    for p, b in B.items():
        static, idx = (NOSHELL, NOSHELL_IDX) if p.startswith('Wheel') else (ALL, ALL_IDX)
        rest_cont[p] = contacts(b, static, idx)
    res = dict(target_x=C.CANNON_TARGET_X[c], gap_x=round(x, 4), gap_rank=gap_rank, nudge_inboard_m=nudge, roll_deg=round(roll, 4), rail=dict((k, (round(v, 4) if isinstance(v, float) else v)) for k, v in rl.items()),
               origin=C.r3(origin), origin_ue_cm=C.ue_cm(origin), deck_z_wheels={w: round(d['z'], 4) for w, d in dz.items()},
               wheel_sink_float_rest_m={w: round(v[0], 4) for w, v in wheel_state(M).items()},
               footprint_open_deck=all(fp), rest_contacts={p: sorted(v) for p, v in rest_cont.items() if v},
               muzzle_face_inside_rail_m=round(s * (rl['y'] - (M['Barrel'] @ C.C_MUZZLE).y), 4),
               trunnion_world=C.r3(M['Barrel'] @ C.C_TRUNNION), muzzle_world=C.r3(M['Barrel'] @ C.C_MUZZLE),
               muzzle_rail_clearance_rest_m=round(muzzle_rail_clearance(M), 4),
               barrel_axis_z=round(z + C.C_TRUNNION.z, 4), rail_top_bar_z=round(rl['foot_z'] + 1.10, 4),
               rail_mid_bar_z=round(rl['foot_z'] + 0.55, 4))
    return res, origin, rest_cont


def full_check(c, origin, rest_cont, others):
    s = C.CANNON_SIDE[c]
    out = {}
    out['yaw_limit_pos_deg'], h1 = sweep(origin, s, rest_cont, others, 'yaw', 45.0, 1.0, {})
    out['yaw_limit_neg_deg'], h2 = sweep(origin, s, rest_cont, others, 'yaw', -45.0, 1.0, {})
    out['elev_limit_up_deg_vs_ship'], h3 = sweep(origin, s, rest_cont, others, 'elev', 20.0, 0.5, {})
    out['elev_limit_down_deg_vs_ship'], h4 = sweep(origin, s, rest_cont, others, 'elev', -20.0, 0.5, {})
    out['recoil_limit_m'], h5 = sweep(origin, s, rest_cont, others, 'recoil', 1.2, 0.05, {})
    out['first_contacts'] = {'yaw+': h1, 'yaw-': h2, 'elev+': h3, 'elev-': h4, 'recoil': h5}
    # yaw limits with the barrel at the elevation extremes (+9 / -10) and with full recoil
    for el in (9.0, -10.0):
        out['yaw_limit_pos_at_elev%+d' % el], _ = sweep(origin, s, rest_cont, others, 'yaw', 45.0, 1.0, {'elev': el})
        out['yaw_limit_neg_at_elev%+d' % el], _ = sweep(origin, s, rest_cont, others, 'yaw', -45.0, 1.0, {'elev': el})
    out['yaw_limit_pos_at_recoil0.6'], _ = sweep(origin, s, rest_cont, others, 'yaw', 45.0, 1.0, {'recoil': 0.6})
    out['yaw_limit_neg_at_recoil0.6'], _ = sweep(origin, s, rest_cont, others, 'yaw', -45.0, 1.0, {'recoil': 0.6})
    out.update(grid_check(c, origin, rest_cont, others))
    return out


def grid_check(c, origin, rest_cont, others):
    """contract corner grid: yaw -20..20 x elevation -10/0/+9 x recoil 0/0.3/0.6"""
    s = C.CANNON_SIDE[c]
    out = {}
    grid, worst_clear, wheel_rng, deck_ok = [], 9.0, [9.0, -9.0], True
    for yaw in (-20.0, -10.0, 0.0, 10.0, 20.0):
        for el in (-10.0, 0.0, 9.0):
            for rc in (0.0, 0.3, 0.6):
                new, M = evaluate_pose(origin, s, rest_cont, others, yaw=yaw, elev=el, recoil=rc)
                cl = muzzle_rail_clearance(M)
                worst_clear = min(worst_clear, cl)
                ws = wheel_state(M)
                for v, ok in ws.values():
                    wheel_rng[0] = min(wheel_rng[0], v); wheel_rng[1] = max(wheel_rng[1], v); deck_ok &= ok
                if new:
                    grid.append(dict(yaw=yaw, elev=el, recoil=rc, contacts=new))
    out['contract_grid_contacts'] = grid
    out['contract_grid_min_muzzle_to_rail_m'] = round(worst_clear, 4)
    out['contract_grid_wheel_sink_float_m'] = [round(v, 4) for v in wheel_rng]
    out['contract_grid_wheels_on_open_deck'] = deck_ok
    return out


# rest BVHs of all props, for prop-vs-prop checks
REST = {}
PLACED = {}
for c in C.CANNONS:
    res, origin, rest_cont = place_cannon(c, [])
    PLACED[c] = (res, origin, rest_cont)

for c in C.CANNONS:
    s = C.CANNON_SIDE[c]
    others = list(helm_static) + [b for c2 in C.CANNONS if c2 != c for b in cannon_bvhs(PLACED[c2][1], C.CANNON_SIDE[c2])[0].values()]
    res, origin, rest_cont = PLACED[c]
    g = grid_check(c, origin, rest_cont, others)
    nudge = 0.0
    # target: yaw +-20 clean at every contract corner; nudge inboard if the rail blocks it
    while (g['contract_grid_contacts'] or g['contract_grid_min_muzzle_to_rail_m'] < MIN_RAIL_CLEAR) and nudge < 0.4:
        print('[place]  ', c, 'nudge', nudge, g['contract_grid_contacts'][:3])
        nudge = round(nudge + 0.01, 3)
        res, origin, rest_cont = place_cannon(c, others, nudge=nudge)
        g = grid_check(c, origin, rest_cont, others)
    chk = full_check(c, origin, rest_cont, others)
    res['clearance'] = chk
    PLACED[c] = (res, origin, rest_cont)
    R['cannons'][c] = res
    print('[place] cannon', c, {k: res[k] for k in ('gap_x', 'origin', 'nudge_inboard_m', 'muzzle_face_inside_rail_m', 'muzzle_rail_clearance_rest_m', 'rest_contacts')})
    print('[place]   clearance', {k: v for k, v in chk.items() if k != 'first_contacts'})
    print('[place]   first contacts', chk['first_contacts'])

# ------------------------------------------------------------------ barrel vs its own carriage (same for all 4 copies)
I4 = Matrix.Identity(4)
frame = [part_bvh('Cannon_Carriage', I4)] + [part_bvh('Cannon_Wheel_' + w, I4) for w in C.C_WHEELS]


def barrel_blocked(el):
    b = part_bvh('Cannon_Barrel', C.rot_about(C.C_TRUNNION, (0, 1, 0), -el))
    q = part_bvh('Cannon_Quoin', Matrix.Translation(V((-C.quoin_slide(el), 0, 0))))
    return any(b.overlap(f) for f in frame) or bool(b.overlap(q))


def own_limit(sgn):
    a = 0.0
    while abs(a) < 30 and not barrel_blocked(a + sgn * 0.05):
        a = round(a + sgn * 0.05, 3)
    return a


R['cannon_barrel_vs_carriage'] = dict(rule='quoin slide = clamp(0.024 m/deg * elev, 0, 0.15 m)', up_limit_deg=own_limit(1),
                                      down_limit_deg=own_limit(-1), blocked_at_plus9=barrel_blocked(9.0),
                                      blocked_at_minus10=barrel_blocked(-10.0))
print('[place] barrel vs carriage', R['cannon_barrel_vs_carriage'])

# ------------------------------------------------------------------ helm wheel spin
wv, wp, wsh = PART['Helm_Wheel']
pv, pp, psh = PART['Helm_Pedestal']
WAX = V(H['wheel_axle'])
ped_tree = BVHTree.FromPolygons(C.xform(pv, HELM_M).tolist(), pp)
ped_face_shell = np.array([psh[f[0]] for f in pp])
rest_w = part_bvh('Helm_Wheel', HELM_M)
rest_ped_shells = {int(ped_face_shell[j]) for _, j in rest_w.overlap(ped_tree)}
rest_ship = contacts(rest_w, ALL, ALL_IDX)
rest_ped_ship = contacts(ped_tree, ALL, ALL_IDX)
bad = []
min_deck = 9.0
for a in range(0, 360, 5):
    M = C.rot_about(WAX, (1, 0, 0), a) @ HELM_M
    b = part_bvh('Helm_Wheel', M)
    ns = {int(ped_face_shell[j]) for _, j in b.overlap(ped_tree)} - rest_ped_shells
    nship = contacts(b, ALL, ALL_IDX) - rest_ship
    low = C.xform(wv, M)
    i = int(np.argmin(low[:, 2]))
    d = deck_at(low[i, 0], low[i, 1])
    min_deck = min(min_deck, low[i, 2] - d['z'])
    if ns or nship:
        bad.append(dict(angle=a, pedestal_shells=sorted(ns), ship_islands=sorted(nship)))
R['helm']['wheel_spin'] = dict(step_deg=5, new_contacts=bad, rest_pedestal_shells_touched=sorted(rest_ped_shells),
                               rest_ship_islands_touched_by_wheel=sorted(rest_ship),
                               rest_ship_islands_touched_by_pedestal=sorted(rest_ped_ship),
                               min_wheel_to_deck_m=round(float(min_deck), 4))
# helm clearance to the cannons' recoil paths is covered by the cannon prop-vs-prop checks
print('[place] helm wheel spin', R['helm']['wheel_spin'])
R['seconds'] = round(time.time() - T0, 1)
C.dump_json(R, OUT)
print('[place] wrote', OUT, R['seconds'], 's')
