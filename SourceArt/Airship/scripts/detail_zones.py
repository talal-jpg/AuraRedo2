"""Zone map of the round 3 detail pass: which zone owns which part of the ship (exact rules, as code).

Blender world metres (+X bow, +Y port, +Z up); UE cm = (100 x, -100 y, 100 z). Numbers come from detail_survey.py
(rig/detail/zones/ship_survey.json) and from zone 1's build (z1_continuity.json). ZONES.md explains them in words.

Every SM_Airship polygon gets one owner (face_zones), by the FIRST rule that matches:
  1. parts with a fixed owner (PART_OWNER): the four pods + nozzles -> the pod's zone, turbines / fan mounts / rudder
     -> Z6, gantry (+ search lights, winches, chains, hang strips) and the deck rails -> Z7, bow wedge and the front
     underside block -> Z4, deck props -> none; the belly tabs (the small 'Hull' islands 393-411) -> Z5 (Z4 forward of
     X_FWD), each island whole
  2. walkable faces (the tops of PA_Airship's hull boxes, the deck) -> none: the deck planks and every walkable top stay
     plain
  3. a pod's pocket (walls + roof: within CAVITY = 4 cm of the pocket cylinder) -> the pod's zone (FL Z1, FR Z2,
     RL Z3, RR Z3); its rim band (up to SURROUND = 0.25 m outside the cylinder) -> the pod's zone too, except where the
     band lies in the Z1 / Z2 flank of the other pod's zone (round RL / RR: zone 1's plates come to 9 cm of the RL
     opening, so Z3 keeps to the lip there)
  4. the transom (x < TRANSOM_X and the face looks aft) -> Z6
  5. forward of X_FWD (6.95, zone 1's fore edge: the FL pocket's fore rim strap) -> Z4
  6. below the bilge line (chart angle < BILGE_PHI, -56 deg, zone 1's lower edge) -> Z5
  7. aft of X_AFT (-11.55, zone 1's aft edge: the aft cannon station) -> Z3
  8. otherwise the flank between the cannon stations: port (y > 0) Z1, starboard Z2
Two volumes in open space belong to a zone as well (VOLUMES): the stairs box (Z7) and the open fan backs (Z6).
KEEP_CLEAR volumes belong to nobody (helm, turret sweeps, cannon sweeps): nothing may be built in them.

Helpers (point tests work without Blender; face_zones needs a detail_ship.Ship):
  zone_of_point(p, ship_zones=None)   owner of a point (volumes first, then the nearest face's owner)
  keep_clear_hits(points)              how many points sit in a KEEP_CLEAR volume, per volume
  chart_phi(p)                         the flank chart angle of a point (FlankChart convention, deg)
  pod_coords(p, pod)                   (h along the pod axis, distance from it) in the pod's frame
  ZoneIndex(ship)                      per-face owners + a BVH: .zone_at(p), .near_other(p, zone, margin)
"""
import math, json, os
try:
    import numpy as np
except ImportError:          # plain python3 (the sheet script) only needs the tables
    np = None

ZONE_IDS = ('Z1', 'Z2', 'Z3', 'Z4', 'Z5', 'Z6', 'Z7')
NONE = 'none'
ZONES = {
    'Z1': 'port flank between the cannon stations (x -11.55 .. 6.95), deck edge to the bilge line, + pod FL, its pocket',
    'Z2': 'starboard flank between the cannon stations (mirror of Z1) + pod FR, its pocket',
    'Z3': 'aft flanks of both sides (aft of x -11.55 to the transom), above the bilge line + pods RL, RR, their pockets',
    'Z4': 'bow: everything forward of x 6.95 below the gantry (both flanks, belly, keel), bow wedge, front underside',
    'Z5': 'belly and keel below the bilge line, both sides, x -16.36 .. 6.95, around (not on) the pods and pockets',
    'Z6': 'stern: transom, rudder, both turbines (housing, rotor, rods, mounts), the OPEN FAN BACKS',
    'Z7': 'gantry / forward superstructure (not its walkable tops), search lights, winches, chains, hang strips, '
          'the deck rails, and the STAIRS from the main deck up to the forward turret deck',
}
STATUS = {'Z1': 'done, approved 2026-11-28 (pass 2)'}

# ------------------------------------------------------------------ boundary numbers (metres, degrees)
X_AFT = -11.55          # Z1 / Z2 aft edge (zone 1's x_aft; rail gap of the aft cannons at -11.47) = Z3 fore edge
X_FWD = 6.95            # Z1 / Z2 fore edge (FL pocket fore rim strap; zone 1's x_fwd_plates) = Z4 aft edge
BILGE_PHI = -56.0       # flank / belly line as a chart angle (zone 1's bilge_phi), z about -3.7 amidships
CHART_AY, CHART_AZ = 1.5, 0.3       # chart axis (x, side * 1.5, 0.3): detail_ship.FlankChart
TRANSOM_X, TRANSOM_NX = -15.0, -0.6  # transom faces: aft of x -15 and face normal x < -0.6 (skin ends at x -16.364)
DECK_NZ, DECK_Z = 0.75, 1.5          # deck faces: normal z > 0.75 above z 1.5 (FlankChart's deck edge rule)
POCKET_R = 2.85                       # pod pocket radius about the pod axis (Boolean cutters Cut_Thruster_*)
CAVITY = 0.04                         # the pocket itself: walls and roof, d < POCKET_R + 0.04 (always the pod's zone)
SURROUND = 0.25                       # the rim band round the opening: d < POCKET_R + 0.25 (zone 1's rim strap is
                                      # 0.03 .. 0.19 m from the edge); the pod's zone owns it unless it lies in Z1 / Z2's
                                      # flank (zone 1's plates come to 0.09 m of the RL opening: Z3 keeps to the lip) ...
POCKET_H = (-2.9, 4.6)                # ... in the pod frame's height band h (roof at h -2.8; zone 1's mask band)
MARGIN = 0.10                         # seam rule: 10 cm from a boundary unless continuing a run across it
POD_ZONE = {'FL': 'Z1', 'FR': 'Z2', 'RL': 'Z3', 'RR': 'Z3'}

# pod frames (research classifier, sm_airship_islands.json 'frames'); T0 = drum axis point at h 0, A = axis (nozzle
# direction, down and slightly aft). FR is 0.196 m lower and 0.262 m further out than a mirror of FL; RR is 0.035 m
# lower and 0.637 m further out than a mirror of RL (the pods are not placed symmetrically; the hull is).
POD_T0 = {'FL': (3.83303, 4.65572, -1.33381), 'FR': (3.83303, -4.91791, -1.52989),
          'RL': (-7.16697, 5.13032, -1.60362), 'RR': (-7.16697, -5.76756, -1.63902)}
POD_AXIS = (-0.139173, 0.0, -0.990268)

# parts with a fixed owner: (src, part prefix) -> zone ('*' = any part). Checked in order.
PART_OWNER = [
    ('Thruster_Front_L', '*', 'Z1'), ('Thruster_Front_R', '*', 'Z2'),
    ('Thruster_Rear_L', '*', 'Z3'), ('Thruster_Rear_R', '*', 'Z3'),
    ('Turbines', '*', 'Z6'), ('Rudder', '*', 'Z6'),
    ('Gantry', '*', 'Z7'),             # includes SearchLight_*, ChainFwd, ChainAft, HangStrip_*, Winch_Fwd, Winch_Aft
    ('DeckRails', '*', 'Z7'),
    ('BowWedge', '*', 'Z4'), ('Underside_Front', '*', 'Z4'),
    ('DeckProps', '*', NONE), ('BowFin', '*', NONE),   # BowFin was deleted in round 2 (deck_removals.json)
]

# volumes in open space: (zone, kind, params). box: (x0, x1, y0, y1, z0, z1); cyl_x: (x0, x1, cy, cz, r)
VOLUMES = [
    ('Z7', 'box', (2.5, 10.65, -4.6, 4.6, 2.35, 6.65), 'stairs: main deck aft of the forward turret deck (deck top '
     'about 2.39 there, turret deck top 6.53 from x 10.55); Z7 picks the place inside it'),
    ('Z6', 'cyl_x', (-20.0, -16.85, 7.6, 1.4, 2.95), 'open back of the port fan (behind the rotor, x -17.4 .. -16.9)'),
    ('Z6', 'cyl_x', (-20.0, -16.85, -7.6, 1.4, 2.95), 'open back of the starboard fan'),
]
# nothing may be built here (open-space keep-outs; the rig check sweeps the moving ones exactly)
KEEP_CLEAR = [
    ('helm', 'cyl_z', (-6.5, 0.0, 1.5, 2.3, 5.5), 'helm: 1.5 m round the pedestal axis (bone Helm (-6.5, 0, 2.605))'),
    ('turret_L', 'cyl_z', (21.0, 2.45, 1.95, 6.5, 9.7), 'port turret: yaw axis on the deck top (6.55); base r 0.44, '
     'gun 1.80 ahead / 0.44 behind the trunnion 1.50 above the deck, yaw -30..+110 deg (Blender, + toward port), pitch '
     '-20..40: everything it can reach is inside r 1.95, up to 3.15 above the deck'),
    ('turret_R', 'cyl_z', (21.0, -2.45, 1.95, 6.5, 9.7), 'starboard turret (yaw -110..+30 deg Blender)'),
    ('cannon_L1', 'sph_up', (-0.463, 5.985, 2.437, 2.3), 'cannon L1 sweep (yaw +-20, elevation -10..8.75, recoil 0.6)'),
    ('cannon_L2', 'sph_up', (-11.472, 3.927, 2.836, 2.3), 'cannon L2 sweep'),
    ('cannon_R1', 'sph_up', (-0.463, -5.985, 2.437, 2.3), 'cannon R1 sweep'),
    ('cannon_R2', 'sph_up', (-11.472, -3.927, 2.836, 2.3), 'cannon R2 sweep'),
]
TURRET_MOUNTS = {'L': (21.0, 2.45, 6.55), 'R': (21.0, -2.45, 6.55)}
TURRET_YAW_BLENDER = {'L': (-30.0, 110.0), 'R': (-110.0, 30.0)}      # UE yaw limits (-110, 30) / (-30, 110), negated
TURRET_PITCH = (-20.0, 40.0)
TURRET_PIVOT_H, TURRET_MUZZLE, TURRET_REAR, TURRET_BASE_R, TURRET_BASE_H = 1.50, 1.80, 0.444, 0.436, 1.877


# ------------------------------------------------------------------ point helpers (no Blender needed)
def chart_phi(p):
    """flank chart angle (deg) of a point: 0 = horizontal outboard from (x, side * 1.5, 0.3), + up"""
    y, z = abs(float(p[1])), float(p[2])
    return math.degrees(math.atan2(z - CHART_AZ, y - CHART_AY))


def pod_coords(p, pod):
    rel = [float(p[i]) - POD_T0[pod][i] for i in range(3)]
    h = sum(rel[i] * POD_AXIS[i] for i in range(3))
    return h, math.sqrt(sum((rel[i] - POD_AXIS[i] * h) ** 2 for i in range(3)))


def pocket_owner(p):
    """(zone, 'cavity' | 'rim') of the pod pocket that contains p, else (None, None)"""
    for pod, z in POD_ZONE.items():
        if (pod in ('FL', 'RL')) != (p[1] > 0):
            continue
        h, d = pod_coords(p, pod)
        if POCKET_H[0] < h < POCKET_H[1] and d < POCKET_R + SURROUND:
            return z, ('cavity' if d < POCKET_R + CAVITY else 'rim')
    return None, None


def in_volume(p, kind, prm):
    x, y, z = (float(v) for v in p)
    if kind == 'box':
        x0, x1, y0, y1, z0, z1 = prm
        return x0 <= x <= x1 and y0 <= y <= y1 and z0 <= z <= z1
    if kind == 'cyl_x':
        x0, x1, cy, cz, r = prm
        return x0 <= x <= x1 and math.hypot(y - cy, z - cz) <= r
    if kind == 'cyl_z':
        cx, cy, r, z0, z1 = prm
        return z0 <= z <= z1 and math.hypot(x - cx, y - cy) <= r
    if kind == 'sph_up':                # upper half ball (above the deck point) round a mount
        cx, cy, cz, r = prm
        return z >= cz - 0.05 and math.dist((x, y, z), (cx, cy, cz)) <= r
    raise KeyError(kind)


def volume_owner(p):
    for z, kind, prm, _ in VOLUMES:
        if in_volume(p, kind, prm):
            return z
    return None


def keep_clear_hits(points):
    out = {}
    for name, kind, prm, _ in KEEP_CLEAR:
        n = sum(1 for p in points if in_volume(p, kind, prm))
        if n:
            out[name] = n
    return out


def position_owner(c, n):
    """rules 3-8 for a skin / band / pipe / tab face with centre c and face normal n"""
    po, kind = pocket_owner(c)
    if kind == 'cavity':
        return po
    if c[0] < TRANSOM_X and n[0] < TRANSOM_NX:
        pz = 'Z6'
    elif c[0] > X_FWD:
        pz = 'Z4'
    elif chart_phi(c) < BILGE_PHI:
        pz = 'Z5'
    elif c[0] < X_AFT:
        pz = 'Z3'
    else:
        pz = 'Z1' if c[1] > 0 else 'Z2'
    if kind == 'rim' and (pz not in ('Z1', 'Z2') or pz == po):
        return po
    return pz


def part_owner(src, part):
    for s, p, z in PART_OWNER:
        if s == src and (p == '*' or part.startswith(p)):
            return z
    return None


def pa_walkable(c, n, boxes):
    """is a face with centre c (Blender m) and normal n one of PA_Airship's walkable tops? boxes: (min, max) Blender m"""
    if n[2] < 0.7:
        return False
    for mn, mx in boxes:
        if mn[0] <= c[0] <= mx[0] and mn[1] <= c[1] <= mx[1] and mx[2] - 0.3 <= c[2] <= mx[2] + 0.08:
            return True
    return False


def pa_boxes_blender(path='/mnt/new_partition/UnrealProjects/_AirshipWork/Saved/Airship/pa_hull_boxes.json'):
    """PA_Airship hull boxes in Blender metres: [(min, max)] (UE (x, y, z) cm -> (x, -y, z) / 100)"""
    B = json.load(open(path))['hull_boxes']
    out = []
    for b in B:
        a = np.array(b['min']) / 100.0; c = np.array(b['max']) / 100.0
        out.append((np.array([a[0], -c[1], a[2]]), np.array([c[0], -a[1], c[2]])))
    return out


# ------------------------------------------------------------------ per-face owners (needs Blender + detail_ship.Ship)
def face_zones(ship, boxes=None):
    """owner per SM_Airship polygon (array of str) and the rule that decided it (array of str)"""
    me = ship.ob.data
    nP = len(me.polygons)
    cen = np.empty(nP * 3); me.polygons.foreach_get('center', cen); cen = cen.reshape(-1, 3)
    nrm = np.empty(nP * 3); me.polygons.foreach_get('normal', nrm); nrm = nrm.reshape(-1, 3)
    boxes = pa_boxes_blender() if boxes is None else boxes
    zone = np.empty(nP, dtype=object)
    why = np.empty(nP, dtype=object)
    import detail_ship as S
    for k in range(nP):
        isl = int(ship.p_island[k])
        rec = ship.islands[isl]
        c, n = cen[k], nrm[k]
        z = part_owner(rec['src'], rec['part'])
        if z is None and rec['src'] == 'Hull' and isl != S.SKIN:
            # the belly tabs (islands 393-411, one row per side along the bilge) and the small fittings at x 6.7:
            # whole islands, by centre (Z1 / Z2 stop just above the tabs)
            cc = ship.co[ship.v_island == isl].mean(0)
            z = 'Z4' if cc[0] > X_FWD else 'Z5'
        if z is not None:
            if z != NONE and pa_walkable(c, n, boxes):
                zone[k], why[k] = NONE, 'walkable top of a part'
            else:
                zone[k], why[k] = z, 'part ' + rec['src']
            continue
        if pa_walkable(c, n, boxes) or (isl == S.SKIN and n[2] > DECK_NZ and c[2] > DECK_Z):
            zone[k], why[k] = NONE, 'deck / walkable'
            continue
        zone[k] = position_owner(c, n)
        why[k] = 'position'
    return zone, why


class ZoneIndex:
    """owners of the SM_Airship faces with a BVH, for point tests inside Blender"""

    def __init__(self, ship, boxes=None):
        from mathutils.bvhtree import BVHTree
        self.ship = ship
        self.zone, self.why = face_zones(ship, boxes)
        tri, own = [], []
        for k, p in enumerate(ship.polys):
            for i in range(1, len(p) - 1):
                tri.append((p[0], p[i], p[i + 1]))
                own.append(k)
        self.tri_face = np.array(own)
        self.bvh = BVHTree.FromPolygons(ship.co.tolist(), tri, all_triangles=True)

    def zone_at(self, p, maxd=1.0):
        """owner of a detail point: a volume, else the nearest SM_Airship face's owner (None: nothing within maxd)"""
        from mathutils import Vector as V
        vz = volume_owner(p)
        if vz:
            return vz
        loc, _, fi, _ = self.bvh.find_nearest(V(p), maxd)
        return None if loc is None else self.zone[self.tri_face[fi]]

    def zones_within(self, p, r):
        from mathutils import Vector as V
        return {self.zone[self.tri_face[fi]] for (_, _, fi, _) in self.bvh.find_nearest_range(V(p), r)}

    def near_other(self, p, zone, margin=MARGIN):
        """the other zones whose faces lie within `margin` of p (the seam rule)"""
        from mathutils import Vector as V
        out = set()
        for (_, _, fi, _) in self.bvh.find_nearest_range(V(p), margin):
            z = self.zone[self.tri_face[fi]]
            if z not in (zone, NONE):
                out.add(z)
        return out

    def summary(self):
        me = self.ship.ob.data
        area = np.empty(len(me.polygons)); me.polygons.foreach_get('area', area)
        out = {}
        for z in ZONE_IDS + (NONE,):
            m = self.zone == z
            out[z] = dict(faces=int(m.sum()), area_m2=round(float(area[m].sum()), 1))
        return out


def ownership_report(index, co, zone, margin=MARGIN, kinds=None, sample=4):
    """per-zone check: detail vertices whose owner is another zone, none of them (walkable / plain) or no face near,
    vertices in a KEEP_CLEAR volume, and vertices within `margin` of another zone (allowed only for runs continued
    across a seam: list them in the zone doc). kinds: per-vertex kind tags for the breakdown. Every `sample`-th vertex
    is tested (all of them with sample=1)."""
    co = np.asarray(co)
    idx = np.arange(0, len(co), sample)
    wrong, near, by_k, seam = {}, {}, {}, {}
    for i in idx:
        z = index.zone_at(co[i])
        if z != zone:
            key = str(z)
            if volume_owner(co[i]) is None and zone in index.zones_within(co[i], margin + 0.2):
                seam[key] = seam.get(key, 0) + 1         # its own zone's skin is right there: a part lying on the seam
                continue
            wrong[key] = wrong.get(key, 0) + 1
            if kinds is not None:
                by_k[kinds[i]] = by_k.get(kinds[i], 0) + 1
            continue
        for o in index.near_other(co[i], zone, margin):
            near[o] = near.get(o, 0) + 1
    return dict(zone=zone, verts_tested=int(len(idx)), sample_every=sample, outside_zone=wrong,
                outside_by_kind=by_k, on_seam_with=seam, within_margin_of=near, keep_clear=keep_clear_hits(co[idx]),
                about='outside_zone: nearest SM_Airship face belongs to another zone and no face of this zone lies '
                      'within margin + 0.2 m (must be 0, or explained in the zone doc); on_seam_with: nearest face is '
                      'the neighbour\'s but this zone\'s skin is within margin + 0.2 m (a part ending on the seam, '
                      'or standing 0.2 m off the skin there); within_margin_of: inside the zone but within the 10 cm '
                      'margin of a neighbour (only for runs continued across the seam)')
