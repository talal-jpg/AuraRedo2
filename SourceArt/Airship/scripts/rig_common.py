"""Shared helpers for the SK_Airship rig scripts (rig_place, rig_build, rig_export, rig_render, ...).

Blender world metres: +X bow, +Y port (L), +Z up. Unreal component space = (100x, -100y, 100z) cm.
Contract: /mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/RIG_CONTRACT.md
"""
import json, math, os
import numpy as np
from mathutils import Vector as V, Matrix

RIG = '/mnt/new_partition/BlenderProjects/StylizedAirship/rig'
TALAL_BLEND = '/mnt/new_partition/BlenderProjects/StylizedAirship/StylizedAirship.blend'   # never opened for writing
SRC_BLEND = RIG + '/AirshipRig_src.blend'      # byte copy (cp) of Talal's file, the pristine input of rig_build
RIG_BLEND = RIG + '/AirshipRig.blend'          # the rigged copy (written by rig_build.py)
PROPS_BLEND = RIG + '/props/AirshipProps.blend'
TURRET_BLEND = RIG + '/props/Turret.blend'     # model_turret.py (geometry); its atlas UVs live in AirshipProps.blend
SCRIPTS = os.path.dirname(os.path.abspath(__file__))
SOURCE_ART = '/mnt/new_partition/UnrealProjects/_AirshipWork/SourceArt/Airship'
RESEARCH = '/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/research'
CHECKS = RIG + '/checks/rig'
RENDERS = RIG + '/renders/rig'
EXPORT = RIG + '/export'
PLACEMENT_JSON = CHECKS + '/placement.json'

SHELL_ISLAND = 392          # the closed hull skin (deck surface is part of it)
PODS = ('FL', 'FR', 'RL', 'RR')
POD_OBJ = {'FL': 'Thruster_Front_L', 'FR': 'Thruster_Front_R', 'RL': 'Thruster_Rear_L', 'RR': 'Thruster_Rear_R'}
CANNONS = ('L1', 'L2', 'R1', 'R2')       # L1 fwd port, L2 aft port, R1 fwd stbd, R2 aft stbd
CANNON_SIDE = {'L1': 1, 'L2': 1, 'R1': -1, 'R2': -1}
# Station targets = Talal's marks in talal_sketches/3_cannon_spots.png, read through the solved sketch camera
# (checks/verify/sketch_camera.json, 6 landmarks within 1.4 px; verify_station_fit.py -> checks/verify/station_fit.json).
# Fore mark: a cannon at the rail gap x -0.463 sits in the middle of it on Talal's screen (silhouette centroid 4 px
# from the mark's, 72 % inside; the gap at -1.387 is 21 px off, 45 % inside); the mark's ray hits have their median at
# x -0.65. Aft mark: ray-hit median x -11.33 -> gap -11.472 (the view is too foreshortened there to do better).
# Until 2026-11-22 the fore pair used -5.3, an eyeballed estimate that put it between the two marks; set 'L1'/'R1' to
# -1.3 for the next gap aft (the verifier's suggestion) or -5.3 for the old station.
CANNON_TARGET_X = {'L1': -0.46, 'L2': -11.3, 'R1': -0.46, 'R2': -11.3}
CANNON_PARTS = ('Carriage', 'Barrel', 'Quoin', 'Wheel_FL', 'Wheel_FR', 'Wheel_BL', 'Wheel_BR')
# cannon model (AirshipProps.blend, carriage space, metres)
C_TRUNNION = V((0.30, 0.0, 0.80))
C_MUZZLE = V((1.86, 0.0, 0.80))
C_QUOIN = V((-0.80, 0.0, 0.33))
C_WHEELS = {'FL': V((0.50, 0.525, 0.22)), 'FR': V((0.50, -0.525, 0.22)),
            'BL': V((-0.53, 0.525, 0.22)), 'BR': V((-0.53, -0.525, 0.22))}
C_WHEEL_R = 0.22
MUZZLE_INSIDE_RAIL = 0.12
QUOIN_K, QUOIN_CAP = 0.024, 0.15          # quoin slide (m) = clamp(0.024 * elev_deg, 0, 0.15) back along cannon -X
HELM_X = -6.5
# Helm_Wheel origin relative to the pedestal origin (Helm.blend: WHEEL_X, 0, AXLE_H). Round 2 (2026-11-24): the wheel was
# scaled to the 141.6 cm mech (140 cm across the handle tips, hub at chest height); it was (-0.63, 0, 1.65), 3.1 m across.
HELM_WHEEL_OFS = V((-0.35, 0.0, 1.00))
# pilot capsule axis behind the wheel plane: capsule radius 0.34 + 0.21 m of room for the arms (was 1.3 m)
PILOT_BEHIND_AXLE = 0.55
BONE_TAIL = V((0, 0, 0.5))

# front machine-gun turrets (round 2): yaw axis on the narrow forward deck, Blender metres (UE (2100, -/+245)). The
# turret actors are spawned by the pawn in Unreal; they are not part of SK_Airship. TURRET_SEAT_BEHIND = the gunner's
# capsule axis behind the yaw axis (UAirshipSettings TurretSeatOffset (-100, 0, 0)).
TURRET_MOUNTS = {'L': (21.0, 2.45), 'R': (21.0, -2.45)}
TURRET_SEAT_BEHIND = 1.0
MECH_CAPSULE_RADIUS, MECH_CAPSULE_HALF_HEIGHT = 0.34, 0.708     # the player mech's capsule (141.6 cm tall)

# object names in the rig .blend / FBX (sorted by name in the FBX, so SM_Airship comes first -> material slot 0)
HULL_OBJ = 'SM_Airship'
PROP_PREFIX = 'SM_AirshipProp_'


def prop_obj_name(kind, part):
    """kind 'Helm' or a cannon id; part = 'Pedestal'/'Wheel' or a CANNON_PARTS entry"""
    return PROP_PREFIX + ('Helm_' + part if kind == 'Helm' else 'Cannon_%s_%s' % (kind, part))


def deck_removals():
    """the deck pieces the rig build deletes from SM_Airship (scripts/deck_removals.json)"""
    return load_json(os.path.join(SCRIPTS, 'deck_removals.json'))


def removed_islands():
    return sorted(i for p in deck_removals()['pieces'] for i in p['islands'])


def kept_vertex_index(visl=None):
    """indices (into Talal's 36908 SM_Airship vertices) of the vertices the rig keeps, in their original order. Deleting
    whole islands keeps the order of the remaining vertices, so kept_vertex_index()[i] is the source vertex of rig vertex i
    (rig_build.py checks this)."""
    if visl is None:
        visl = np.array(load_json(RESEARCH + '/sm_airship_vertex_parts.json')['vertex_island'])
    return np.nonzero(~np.isin(np.asarray(visl), removed_islands()))[0]


def load_json(p):
    with open(p) as f:
        return json.load(f)


def dump_json(obj, p):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w') as f:
        json.dump(obj, f, indent=1, default=lambda o: o.tolist() if hasattr(o, 'tolist') else (list(o) if hasattr(o, '__iter__') else str(o)))


def r3(v, n=4):
    return [round(float(x), n) for x in v]


def ue_cm(v):
    """Blender world metres -> Unreal component cm"""
    return [round(100.0 * v[0], 2) + 0.0, round(-100.0 * v[1], 2) + 0.0, round(100.0 * v[2], 2) + 0.0]


# ------------------------------------------------------------------ island -> bone map
def bone_of_island(r):
    p, piece = r['part'], r.get('piece', '')
    if p == 'Hull' or p.startswith('FanMount_') or p.startswith('HangStrip_') or p == 'ChainAft':
        return 'Hull'
    if p.startswith('Pod_'):
        return 'Thruster_' + p[4:]
    if p.startswith('Nozzle_'):
        return 'Thruster_%s_Petal%02d' % (p[7:], r['index']) if piece == 'petal' else 'Thruster_%s_Nozzle' % p[7:]
    if p.startswith('FanHousing_'):
        return 'Turbine_%s_Rod' % p[-1] if piece == 'hanging_rod' else 'Turbine_' + p[-1]
    if p.startswith('FanRotor_'):
        return 'Turbine_%s_Rotor' % p[-1]
    if p == 'Rudder':
        return 'Rudder'
    if p.startswith('SearchLight_'):
        return p if piece == 'post' else p + '_Head'
    if p == 'ChainFwd':
        return 'ChainFwd'
    if p.startswith('Winch_'):
        return p
    raise KeyError(p)


def hull_vertex_bones():
    """per-vertex bone name for SM_Airship from the research classifier (checked for consistency)"""
    VP = load_json(RESEARCH + '/sm_airship_vertex_parts.json')
    ISL = load_json(RESEARCH + '/sm_airship_islands.json')
    isl = {r['id']: r for r in ISL['islands']}
    parts = VP['parts']
    vb = []
    for i, (pi, ii) in enumerate(zip(VP['vertex_part'], VP['vertex_island'])):
        r = isl[ii]
        assert parts[pi] == r['part'], (i, parts[pi], r['part'])
        vb.append(bone_of_island(r))
    return vb, VP, ISL


# ------------------------------------------------------------------ cannon frame
def cannon_frame(origin, side, yaw_deg=0.0, roll_deg=0.0):
    """world matrix of a cannon: X = firing direction (outboard), Z up; side +1 port (+Y), -1 starboard (-Y).
    roll_deg tilts the cannon about its own firing axis so all 4 wheels sit on the sloped deck (the deck's sheer
    runs along the cannon's axles); the firing direction stays exactly +-Y."""
    return Matrix.Translation(V(origin)) @ Matrix.Rotation(math.radians(90.0 * side + yaw_deg), 4, 'Z') @ \
        Matrix.Rotation(math.radians(roll_deg), 4, 'X')


def quoin_slide(elev_deg):
    return min(max(QUOIN_K * elev_deg, 0.0), QUOIN_CAP)


# ------------------------------------------------------------------ mesh helpers (numpy)
def mesh_arrays(me):
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get('co', co)
    co = co.reshape(-1, 3)
    loops = np.empty(len(me.loops), dtype=np.int64)
    me.loops.foreach_get('vertex_index', loops)
    ls = np.empty(len(me.polygons), dtype=np.int64)
    lt = np.empty(len(me.polygons), dtype=np.int64)
    me.polygons.foreach_get('loop_start', ls)
    me.polygons.foreach_get('loop_total', lt)
    polys = [loops[s:s + t].tolist() for s, t in zip(ls, lt)]
    return co, polys


def xform(co, M):
    M = np.array(M)
    return co @ M[:3, :3].T + M[:3, 3]


def loose_parts(nv, polys):
    """union-find shells -> array shell id per vertex"""
    par = np.arange(nv)

    def find(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a
    for p in polys:
        r0 = find(p[0])
        for q in p[1:]:
            rq = find(q)
            if rq != r0:
                par[rq] = r0
    return np.array([find(i) for i in range(nv)])


# ------------------------------------------------------------------ pose math
def rest_matrix(head):
    """world-aligned bone rest matrix as Blender stores it for a bone pointing +Z with roll 0"""
    return Matrix.Translation(V(head)) @ Matrix.Rotation(math.radians(90.0), 4, 'X')


def rot_about(pivot, axis, deg):
    p = V(pivot)
    return Matrix.Translation(p) @ Matrix.Rotation(math.radians(deg), 4, V(axis).normalized()) @ Matrix.Translation(-p)


def controls_to_deltas(ctrl, spec):
    """ctrl: dict of contract-style control values (deg / m); spec: bone spec dict (name -> {head, parent, ...} plus
    'meta' with axes). Returns {bone: D} where D is the bone's own motion in rest-world coordinates
    (applied in the parent's moving frame)."""
    D = {}
    meta = spec['meta']
    for p in PODS:
        b = 'Thruster_' + p
        hp = V(spec['bones'][b]['head'])
        D[b] = rot_about(hp, (0, 1, 0), ctrl.get('PodPitchDeg_' + p, 0.0)) @ rot_about(hp, (-1, 0, 0), ctrl.get('PodRollDeg_' + p, 0.0))
        hn = V(spec['bones'][b + '_Nozzle']['head'])
        # + pitch swings the nozzle exit aft (about Blender +Y); + roll swings the exit toward UE +Y = Blender -Y
        D[b + '_Nozzle'] = rot_about(hn, (0, 1, 0), ctrl.get('NozzlePitchDeg_' + p, 0.0)) @ \
            rot_about(hn, (-1, 0, 0), ctrl.get('NozzleRollDeg_' + p, 0.0))
        fl = ctrl.get('NozzleFlareDeg_' + p, 0.0)
        for k in range(12):
            pb = '%s_Petal%02d' % (b, k)
            D[pb] = rot_about(spec['bones'][pb]['head'], meta['petal_axis'][pb], fl)
    for s in ('L', 'R'):
        b = 'Turbine_' + s
        D[b] = rot_about(spec['bones'][b]['head'], (0, 0, -1), ctrl.get('TurbineYawDeg_' + s, 0.0))
        D[b + '_Rotor'] = rot_about(spec['bones'][b + '_Rotor']['head'], (1, 0, 0), ctrl.get('RotorAngleDeg_' + s, 0.0))
        hr = spec['bones'][b + '_Rod']['head']
        D[b + '_Rod'] = rot_about(hr, (0, 1, 0), ctrl.get('RodSwingXDeg_' + s, 0.0)) @ rot_about(hr, (1, 0, 0), ctrl.get('RodSwingYDeg_' + s, 0.0))
    D['Rudder'] = rot_about(spec['bones']['Rudder']['head'], (0, 0, 1), ctrl.get('RudderDeg', 0.0))
    for L in ('AftL', 'MidL', 'MidR', 'FwdC'):
        b = 'SearchLight_' + L
        h = spec['bones'][b]['head']
        D[b] = rot_about(h, (0, 1, 0), ctrl.get('LampWobbleXDeg', 0.0)) @ rot_about(h, (1, 0, 0), ctrl.get('LampWobbleYDeg', 0.0))
        D[b + '_Head'] = rot_about(spec['bones'][b + '_Head']['head'], (0, 0, 1), ctrl.get('SearchLightPanDeg', 0.0))
    a, bb = V(spec['bones']['ChainFwd']['head']), V(spec['bones']['ChainFwd_End']['head'])
    D['ChainFwd'] = rot_about(a, bb - a, ctrl.get('ChainSwingDeg', 0.0))
    for w in ('Winch_Fwd', 'Winch_Aft'):
        D[w] = rot_about(spec['bones'][w]['head'], (0, 1, 0), ctrl.get('WinchSpinDeg', 0.0))
    D['Helm_Wheel'] = rot_about(spec['bones']['Helm_Wheel']['head'], (1, 0, 0), ctrl.get('WheelAngleDeg', 0.0))
    for c in CANNONS:
        b = 'Cannon_' + c
        side = CANNON_SIDE[c]
        aim = V(meta['cannon_aim'][c])                       # rest firing direction (world, Muzzle - Barrel)
        up = V((0, 0, 1))
        # true trunnion / axle axis = cannon +Y in world (tilted by the deck roll); falls back to up x aim
        lat = V(meta['cannon_axle'][c]).normalized() if 'cannon_axle' in meta else up.cross(aim).normalized()
        rec = ctrl.get('CannonRecoilCm_' + c, 0.0) / 100.0
        D[b] = rot_about(spec['bones'][b]['head'], up, ctrl.get('CannonYawDeg_' + c, 0.0)) @ Matrix.Translation(-aim * rec)
        el = ctrl.get('CannonElevDeg_' + c, 0.0)
        D[b + '_Barrel'] = rot_about(spec['bones'][b + '_Barrel']['head'], -lat, el)      # + raises the muzzle
        D[b + '_Quoin'] = Matrix.Translation(-aim * quoin_slide(el))
        # rolling backward (centre moves along -aim): omega = up x (-aim) = -lat, angle = recoil / radius
        roll = -math.degrees(rec / C_WHEEL_R)
        for w in ('FL', 'FR', 'BL', 'BR'):
            D['%s_Wheel_%s' % (b, w)] = rot_about(spec['bones']['%s_Wheel_%s' % (b, w)]['head'], lat, roll)
    return D


def apply_pose(arm, spec, ctrl):
    """set pose_bone.matrix_basis = Rest^-1 @ D @ Rest for every bone (world-aligned rests, armature at identity)"""
    D = controls_to_deltas(ctrl, spec)
    for pb in arm.pose.bones:
        pb.rotation_mode = 'QUATERNION'
        R = arm.data.bones[pb.name].matrix_local
        M = R.inverted() @ D.get(pb.name, Matrix.Identity(4)) @ R
        pb.matrix_basis = M
    return D
