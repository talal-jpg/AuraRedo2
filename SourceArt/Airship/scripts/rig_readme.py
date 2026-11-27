"""Step 7: write export/README_rig.md from the check files (plain python3, no Blender needed).

  python3 rig/scripts/rig_readme.py
"""
import json, os

RIG = '/mnt/new_partition/BlenderProjects/StylizedAirship/rig'
CH = RIG + '/checks/rig'


def J(n):
    with open(os.path.join(CH, n)) as f:
        return json.load(f)


spec, skin, place, motion, rt, fbx = (J('bones_spec.json'), J('skin_report.json'), J('placement.json'),
                                      J('motion_ranges.json'), J('roundtrip.json'), J('fbx_SK_Airship.json'))
B = spec['bones']; ORDER = spec['order']; PV = skin['per_bone_verts']
kids = {}
for n in ORDER:
    kids.setdefault(B[n]['parent'], []).append(n)


def ue(n):
    x, y, z = B[n]['head']
    return '(%.1f, %.1f, %.1f)' % (100 * x, -100 * y + 0.0, 100 * z)


NOTE = {
    'root': 'actor origin', 'Hull': 'hull, deck, rails, gantry, pipes, fan pylons, hang strips, aft chain',
    'Thruster_FL': 'pod (drum, plates, pipes)', 'Thruster_FR': 'pod', 'Thruster_RL': 'pod', 'Thruster_RR': 'pod',
    'Turbine_L': 'fan nacelle: shell, ring, top deck + rail (yaw pivot 2.25 m inboard)', 'Turbine_R': 'fan nacelle',
    'Rudder': 'blade + tiller bar, vertical hinge', 'ChainFwd': 'end A, 6 links', 'ChainFwd_End': 'end B, swing axis marker',
    'Winch_Fwd': 'drum + 2 flanges', 'Winch_Aft': 'drum + 2 flanges', 'Helm': 'pedestal base on the deck',
    'Helm_Wheel': 'wheel axle centre', 'PilotSeat': 'pilot stands here (marker)',
}


def label(n):
    if n.endswith('_Flame'):
        return 'socket: nozzle exit, exhaust along A'
    if n.endswith('_Exhaust'):
        return 'socket: duct rear exit, blows toward -X'
    if n.endswith('_Muzzle'):
        return 'socket: muzzle face'
    if n.endswith('_Rotor'):
        return 'rotor hub + 28 blades, spins about +X'
    if n.endswith('_Rod'):
        return 'hanging rod (top)'
    if n.endswith('_Nozzle'):
        return 'nozzle shell, band, throat, lip (petals are children)'
    if n.startswith('SearchLight_'):
        return 'head + lens' if n.endswith('_Head') else 'post'
    if n.startswith('Cannon_'):
        p = n.split('_')[2:] or ['Carriage']
        return {'Carriage': 'carriage', 'Barrel': 'barrel (trunnion axis)', 'Quoin': 'quoin wedge'}.get(p[0], 'truck wheel ' + '_'.join(p[1:]))
    return NOTE.get(n, '')


lines = []


def walk(n, pre='', last=True, top=True):
    conn = '' if top else ('└─ ' if last else '├─ ')
    v = PV.get(n, 0)
    vs = ('%6d v' % v) if v else '-'
    lines.append('%-46s %-26s %8s  %s' % (pre + conn + n, ue(n), vs, label(n)))
    ch = kids.get(n, [])
    petals = [c for c in ch if '_Petal' in c]
    rest = [c for c in ch if '_Petal' not in c]
    sub = pre + ('' if top else ('   ' if last else '│  '))
    if petals:
        p0 = petals[0]
        lines.append('%-46s %-26s %8s  %s' % (sub + ('├─ ' if rest else '└─ ') + p0.replace('00', '00..11'), 'ring, see the CSV', '8 v each',
                                             '12 petals, hinge at the top edge'))
    for i, c in enumerate(rest):
        walk(c, sub, i == len(rest) - 1, False)


walk('root')
TREE = '\n'.join(lines)

C = place['cannons']; H = place['helm']; BV = place['cannon_barrel_vs_carriage']
mr = {c['label']: c for c in motion['checks']}


def T(v):
    return '(%.1f, %.1f, %.1f)' % tuple(float(x) + 0.0 for x in v)


def hard(lbl):
    return mr[lbl]['hard_limit']


pods = []
for p in ('FL', 'FR', 'RL', 'RR'):
    pods.append('%s pitch %+.1f / %+.1f, roll %+.1f / %+.1f' % (p, hard('PodPitchDeg_%s +6' % p), hard('PodPitchDeg_%s -6' % p),
                                                              hard('PodRollDeg_%s +6' % p), hard('PodRollDeg_%s -6' % p)))
noz = []
for p in ('FL', 'FR', 'RL', 'RR'):
    noz.append('%s %+.1f / %+.1f, %+.1f / %+.1f' % (p, hard('NozzlePitchDeg_%s +12' % p), hard('NozzlePitchDeg_%s -12' % p),
                                                   hard('NozzleRollDeg_%s +12' % p), hard('NozzleRollDeg_%s -12' % p)))
c1, c2 = C['L1'], C['L2']
cl1, cl2 = c1['clearance'], c2['clearance']
import math as _m
YAWK = ('yaw_limit_pos_deg', 'yaw_limit_neg_deg', 'yaw_limit_pos_at_elev+9', 'yaw_limit_neg_at_elev+9',
        'yaw_limit_pos_at_elev-10', 'yaw_limit_neg_at_elev-10', 'yaw_limit_pos_at_recoil0.6', 'yaw_limit_neg_at_recoil0.6')
FREE1 = all(abs(cl1[k]) >= 45.0 for k in YAWK)
YAW1_NOTE = ('free to the 45 deg test limit, also at elevation +9 / -10 and at 60 cm recoil' if FREE1 else
             'limits: ' + ', '.join('%s %+.1f' % (k, cl1[k]) for k in YAWK))
RECOIL_MIN = min(C[c]['clearance']['recoil_limit_m'] for c in C)
WHEEL_MAX = max(abs(x) for c in C for x in C[c]['clearance']['contract_grid_wheel_sink_float_m'])
ELEV_FREE = min(min(C[c]['clearance']['elev_limit_up_deg_vs_ship'], -C[c]['clearance']['elev_limit_down_deg_vs_ship']) for c in C)
ROLL1, ROLL2 = abs(c1['roll_deg']), abs(c2['roll_deg'])
SINK1, SINK2 = 105 * _m.tan(_m.radians(ROLL1)), 105 * _m.tan(_m.radians(ROLL2))     # Z up: uphill wheels sink by the track x slope
SHIFT1, SHIFT2 = 80 * _m.sin(_m.radians(ROLL1)), 80 * _m.sin(_m.radians(ROLL2))     # barrel axis 0.80 m above the origin
UE_L1 = '(%d, %d, %d)' % tuple(round(v) for v in c1['origin_ue_cm'])
_sf = os.path.join(RIG, 'checks/verify/station_fit.json')
SF1 = dict(best=c1['gap_x'], dx=float('nan'), inside=float('nan'), dx_1387=float('nan'), in_1387=float('nan'),
           dx_5344=float('nan'), in_5344=float('nan'), rail=['?', '?', '?'])
if os.path.exists(_sf):
    with open(_sf) as _f:
        _m1 = json.load(_f)['marks'][0]
    _c = {round(r['gap_x'], 1): r for r in _m1['candidates']}
    _g = lambda x: _c.get(round(x, 1), dict(centroid_dx_px=float('nan'), inside_mark=float('nan')))
    SF1.update(dx=_g(c1['gap_x'])['centroid_dx_px'], inside=_g(c1['gap_x'])['inside_mark'],
               dx_1387=_g(-1.387)['centroid_dx_px'], in_1387=_g(-1.387)['inside_mark'],
               dx_5344=_g(-5.344)['centroid_dx_px'], in_5344=_g(-5.344)['inside_mark'],
               rail=_m1['on_rail_plane']['filled_x_p5_p50_p95'])
OLD_L1 = (-5.3437, 5.9086, 2.5638)        # fore station before 2026-11-22 (rail gap x -5.344), Blender m
MOVE_UE = (100 * (c1['origin'][0] - OLD_L1[0]), -100 * (c1['origin'][1] - OLD_L1[1]), 100 * (c1['origin'][2] - OLD_L1[2]))
# totals from the exported file (rig_fbx_inspect.py), not typed in: they change when a prop or the hull changes
MESH = {m['mesh']: m for m in fbx['mesh_list']}
tris = fbx['total_triangles']
HULL_V, HULL_T = MESH['SM_Airship']['verts'], MESH['SM_Airship']['tris']
DR = skin['deck_removal']
WHEEL_OFS = [round(100 * (a - b)) for a, b in zip(H['wheel_axle'], H['pedestal'])]
PILOT_BEHIND = H['wheel_axle'][0] - H['pilot'][0]
_td = os.path.join(CH, 'turret_dims.json')
TD = json.load(open(_td)) if os.path.exists(_td) else None
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'deck_removals.json')) as _f:
    DRJ = json.load(_f)
REMOVED_ROWS = '\n'.join('  | %d | %s | %s | %s | %d |' % (
    p['arrow'], p['name'], ', '.join(str(i) for i in p['islands']),
    '(%.0f..%.0f, %.0f..%.0f, %.0f..%.0f)' % (100 * p['bbox_min'][0], 100 * p['bbox_max'][0], -100 * p['bbox_max'][1],
                                           -100 * p['bbox_min'][1], 100 * p['bbox_min'][2], 100 * p['bbox_max'][2]),
    q['verts']) for p, q in zip(DRJ['pieces'], DR['pieces']))
if TD:
    TM = TD['mounts']
    TURRET_TXT = f"""* **Front machine-gun turrets** (new, not part of SK_Airship: the pawn spawns two `AAirshipTurret` actors):
  `scripts/props/model_turret.py` -> `rig/props/Turret.blend`, on the shared prop atlas, exported by
  `scripts/export_turret.py` as two static meshes (cm, X forward, Z up, one UV channel, slot `M_AirshipProps`, no UCX):

  | File | Pivot (object origin) | Size (cm) | Triangles |
  |---|---|---|---:|
  | `SM_AirshipTurret_Base.fbx` | yaw axis on the deck (z 0 = deck top) | radius {TD['base_radius_cm']:.1f}, height {TD['base_height_cm']:.1f} | {TD['files']['SM_AirshipTurret_Base']['tris']:,} |
  | `SM_AirshipTurret_Gun.fbx` | trunnion (pitch) axis, fires +X | {TD['gun_length_cm']:.1f} long ({TD['gun_rear_extent_cm']:.1f} behind the pivot) | {TD['files']['SM_AirshipTurret_Gun']['tris']:,} |

  `PivotHeight` {TD['pivot_height_cm']:.0f} cm (GunMesh on BaseMesh), `MuzzleForward` {TD['muzzle_forward_cm']:.0f} cm (between the two
  barrels, which end at Y -10 / +10), pitch -20..+40 checked clear of the base. Mounts (hull cm): port
  {T(TM['L']['location_cm'])}, starboard {T(TM['R']['location_cm'])}: deck top {TD['deck_top_cm_at_mounts']['L']:.1f}, the gantry
  rail's inner face at |Y| {TD['rail_inner_y_cm']} and its top at Z {TD['rail_top_cm']}; the yaw part is
  {TM['L']['base_to_rail_gap_cm']} cm clear of the rail; swept through yaw {TM['L']['yaw_limits_deg']} (port) /
  {TM['R']['yaw_limits_deg']} (starboard) x pitch -20..+40 against the ship: {len(TM['L']['sweep_contacts']) + len(TM['R']['sweep_contacts'])}
  contacts. Gunner seat (1.0 m behind the axis): {T(TM['L']['gunner_seat_cm'])} / {T(TM['R']['gunner_seat_cm'])}. All numbers:
  `turret_dims.json`."""
else:
    TURRET_TXT = '* Front turrets: run `export_turret.py` (turret_dims.json missing).'

CSV_ROWS = []
with open(os.path.join(CH, 'bones_ue.csv')) as f:
    hdr = f.readline()
    for line in f:
        CSV_ROWS.append(line.strip().split(','))

md = f"""# SK_Airship rig: 118 bones, rigid skin, FBX for Unreal

Rig of the stylized airship (Talal's `SM_Airship`, geometry and UVs unchanged except five deck pieces removed in round 2)
plus the helm and four cannons, made to
`/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/RIG_CONTRACT.md`. Every part is a rigid piece: each vertex
belongs 100 % to one bone. Built headless in Blender 4.5.3 from the scripts in `scripts/` (nothing done by hand).

## Files

Blender side: `/mnt/new_partition/BlenderProjects/StylizedAirship/rig/` (called `rig/` below). Repo copy:
`_AirshipWork/SourceArt/Airship/` (the two FBX files, `textures/`, `scripts/`, this README).

| File | What it is |
|---|---|
| `SK_Airship.fbx` (rig/export, SourceArt/Airship) | Skeleton (118 bones) + 31 skinned meshes in rest pose, no animation. Import this as the skeletal mesh. |
| `SM_AirshipTurret_Base.fbx`, `SM_AirshipTurret_Gun.fbx` (rig/export, SourceArt/Airship) | Round 2: the front machine-gun turret, two static meshes on the prop atlas (see Round 2). `turret_dims.json` (rig/checks/rig, SourceArt/Airship): its pivots, mounts, rail clearance, helm and pilot seat numbers for Unreal. |
| `SK_Airship_testanim.fbx` | Same skeleton and meshes + a 32 s test sweep (frames 1-961 at 30 fps, take `SK_Airship_TestSweep`): every control swept through its range, one group every 2 s (`checks/rig/testanim_segments.json`). Import as an animation on SKEL_Airship. |
| `rig/AirshipRig.blend` | Blender source: armature `Armature`, the meshes in collection `SK_Airship` (vertex groups + Armature modifier), action `SK_Airship_TestSweep` (not assigned). Made from `rig/AirshipRig_src.blend`, a byte copy of Talal's StylizedAirship.blend (md5 4cb832deaa0fa005bf6a9359e34692bb, never written). |
| `SourceArt/Airship/textures/` (= `rig/props/textures/`) | The prop atlas `T_AirshipProps_ComicLines.png` (sRGB) and `T_AirshipProps_ComicMask.png` (linear), 2048. The hull keeps the existing `T_Airship_ComicLines` / `T_Airship_ComicMask` (4096) already in `/Game/Assets/MyShip`. |
| `rig/checks/rig/` | `placement.json` (helm + cannon spots, cannon/helm clearance sweeps), `motion_ranges.json` (every other control swept), `bones_spec.json` / `bones_blender.json` (bones in Blender metres), `bones_ue.csv` (bones in UE cm), `skin_report.json` (vertex counts per bone and mesh), `fbx_SK_Airship*.json` (raw FBX structure), `roundtrip.json`. |
| `rig/renders/rig/` | `rest_*` colour per bone (side, top, two 3/4 views, close-ups), `A_*` every control at its + limit, `B_*` at its - limit. |

Scripts (`rig/scripts/`, copied to `SourceArt/Airship/scripts/`; run all with `bash rig/scripts/rig_all.sh`, about 2 min):
`rig_common.py` (paths, bone map, pose maths), `rig_place.py` (step 1: placement + clearance), `rig_build.py` (steps 2-4:
armature, skin, props, materials, test action), `rig_export.py` (step 5, `-- --anim` for the test file),
`rig_fbx_inspect.py`, `rig_roundtrip.py`, `rig_check_motion.py`, `rig_render.py` (step 6), `rig_readme.py` (this file),
`rig_inspect.py` (lists what a .blend holds). Round 2: `deck_removals.json` (the deck pieces `rig_build.py` deletes),
`export_turret.py` (turret static meshes + `turret_dims.json`), `round2_render.py` (review renders),
`props_all.sh` (rebuilds `props/model_*.py` + `bake_props_comic.py`; run it before `rig_all.sh` when a prop changes).

## Mesh and materials

* {fbx['total_vertices']:,} vertices, {tris:,} triangles, 31 mesh nodes; Unreal merges them into one skeletal mesh.
* Material slot 0 `M_Airship` (SM_Airship, {HULL_V:,} vertices: Talal's {DR['source_verts']:,} minus the {DR['removed_verts']} of the five
  deck pieces removed in round 2; everything else, UVs included, untouched). Slot 1 `M_AirshipProps` (helm + 4 cannons,
  the shared 2048 atlas; the four cannon copies use the same atlas region, everything else is overlap-free). The prop
  meshes are named `SM_AirshipProp_*` so that `SM_Airship` comes first in the FBX (Blender writes objects by name), which
  puts M_Airship first in the file's material list.
* Smoothing by face (as the existing SM_Airship.fbx), normals written per corner, no tangents (Unreal computes them).
* No UCX hulls in this FBX: the pawn uses the existing `/Game/Assets/MyShip/SM_Airship` (8 UCX) as its physics body.

## Skeleton

All positions are Unreal component space in cm (`X = 100x`, `Y = -100y`, `Z = 100z` from Blender metres); port (L) is UE -Y.
Every bone is world-aligned (Blender: head at the pivot, tail = head + (0, 0, 50 cm), roll 0), so in Unreal every bone has
the identity rest rotation, the same as `root`, and its local axes are the component axes. Part roots are direct children
of `Hull`. `v` = vertices skinned to the bone; sockets have no vertices and are not deforming.

```
{TREE}
```

Cannon wheel letters are the cannon's own: F = toward the muzzle (outboard), L = the cannon's left (+Y in its frame), so
on the port guns `Wheel_FL` is the outboard-aft wheel and on the starboard guns the outboard-forward one.
Every bone with its exact position is in `checks/rig/bones_ue.csv`.

## How the weights work

* Every vertex is in exactly one vertex group with weight 1.0 (checked in Blender and again in the FBX: 0 vertices with
  two bones, 0 unweighted, weight sums exactly 1). One group per deforming bone, 105 deforming bones, 13 sockets.
* SM_Airship: weights per loose island from the island classifier (`Docs/Airship/research/sm_airship_vertex_parts.json`).
  The classifier's 1150 islands were checked to still be exactly the mesh's loose parts (same centroids within 2 mm).
  Research part -> bone: Hull, FanMount_L/R, HangStrip_1..4, ChainAft -> `Hull`; Pod_X -> `Thruster_X`; Nozzle_X petal k ->
  `Thruster_X_Petalkk`, the other nozzle islands -> `Thruster_X_Nozzle`; FanHousing_L/R -> `Turbine_L/R` except the
  hanging rod -> `Turbine_*_Rod`; FanRotor -> `Turbine_*_Rotor`; Rudder; SearchLight post -> `SearchLight_*`, head + lens ->
  `SearchLight_*_Head`; ChainFwd; Winch_Fwd/Aft.
* Props: each prop object is 100 % on its bone (pedestal `Helm`, wheel `Helm_Wheel`, carriage `Cannon_X`, barrel
  `Cannon_X_Barrel`, quoin `Cannon_X_Quoin`, wheels `Cannon_X_Wheel_*`).
* Rigid pieces never bend, so a joint shows only where two pieces meet (nozzle in drum, fan nacelle around the pylon, etc.);
  the ranges below say how far each joint can go before that shows.

## Placement (contract section 4)

| Prop | Bone position (UE cm) | How it was placed |
|---|---|---|
| Helm | {T(H['origin_ue_cm'])} | centreline x -6.5 m, z = deck at that point; the base plate reaches 5 cm below its origin, so nothing floats (its aft edge sits 3.8 cm proud of the sloping deck) |
| Helm_Wheel | {T(H['wheel_axle_ue_cm'])} | Helm.blend wheel origin offset ({WHEEL_OFS[0]}, 0, {WHEEL_OFS[2]}) cm; axle along X, the helmsman's side faces aft |
| PilotSeat | {T(H['pilot_ue_cm'])} | {PILOT_BEHIND:.2f} m aft of the axle on the deck (the 141.6 cm mech's capsule: radius 34 cm + 21 cm for the arms) |
| Cannon_L1 / R1 | {T(c1['origin_ue_cm'])} / Y mirrored | rail-post gap middle nearest x {c1['target_x']} = Talal's fore mark (see the change log) (gap {c1['rail']['gap']:.2f} m, rail at {abs(c1['rail']['slope_deg']):.1f} deg to the ship's axis), muzzle face {c1['muzzle_face_inside_rail_m']:.2f} m inside the rail centre line, barrel axis {100 * (c1['barrel_axis_z'] - c1['rail']['foot_z']):.0f} cm above the rail foot (mid bar 55, top bar 110) |
| Cannon_L2 / R2 | {T(c2['origin_ue_cm'])} / Y mirrored | gap middle nearest x {c2['target_x']} = Talal's aft mark (gap {c2['rail']['gap']:.2f} m), moved {c2['nudge_inboard_m']:.2f} m inboard: muzzle face {c2['muzzle_face_inside_rail_m']:.2f} m inside the rail (see deviations) |

The cannons sit on the deck with all four wheels touching (within 1 mm): the deck rises toward the stern
({abs(C['L1']['roll_deg']):.2f} deg at the fore pair, {abs(C['L2']['roll_deg']):.2f} deg at the aft pair), and that slope runs along the
cannon's axles, so each cannon is rolled by it about its own firing axis. The firing direction (Muzzle - Barrel) is still
exactly +-Y.

## Ranges found

"hard" = last value with no collision (cannons, helm: no triangle contact with anything new; hull parts: no new contact and
nothing pushed more than 2 cm into the closed hull skin or the bow wedge). Directions use the contract's signs.

| Control (contract range) | Safe range found | Notes |
|---|---|---|
| CannonYawDeg L1/R1 (+-20) | {cl1['yaw_limit_neg_deg']:+.0f} .. {cl1['yaw_limit_pos_deg']:+.0f} | {YAW1_NOTE}; smallest muzzle-to-rail gap over yaw +-20 x elevation -10/0/+9 x recoil 0/30/60: {100 * cl1['contract_grid_min_muzzle_to_rail_m']:.1f} cm |
| CannonYawDeg L2 (+-20) | {cl2['yaw_limit_neg_deg']:+.0f} .. {cl2['yaw_limit_pos_deg']:+.1f} | + swings the muzzle aft, toward the rail that closes in there; {cl2['yaw_limit_pos_at_elev-10']:+.1f} at elevation -10, {cl2['yaw_limit_pos_at_elev+9']:+.1f} at +9, free with 60 cm recoil; smallest gap at the +-20 corners {100 * cl2['contract_grid_min_muzzle_to_rail_m']:.1f} cm |
| CannonYawDeg R2 (+-20) | {C['R2']['clearance']['yaw_limit_neg_deg']:+.1f} .. {C['R2']['clearance']['yaw_limit_pos_deg']:+.0f} | mirror of L2 (- swings it aft) |
| CannonElevDeg (-10..+9) | {BV['down_limit_deg']:+.2f} .. {BV['up_limit_deg']:+.2f} | limited by the cannon itself (the barrel meets its carriage at +{BV['up_limit_deg']}; the chase meets the transom at {BV['down_limit_deg']}), not by the ship (free +-{ELEV_FREE:.0f} against the rail and deck); +9 overshoots by 0.25 deg (a few mm), clamp at +8.75. The quoin must slide back with elevation: slide = clamp(2.4 cm/deg x elev, 0, 15 cm) along -aim |
| CannonRecoilCm (0..60) | 0 .. {100 * RECOIL_MIN:.0f}{'+' if RECOIL_MIN >= 1.2 else ''} | nothing behind any gun within {RECOIL_MIN:.1f} m (hatches, helm, fan struts, the other guns); wheels stay on open deck. Wheel spin for rolling: recoil / 22 cm rad, backward |
| Cannon wheels vs deck | +-{100 * WHEEL_MAX:.1f} cm | at yaw +-20 the deck slope under the turned carriage lifts/sinks a wheel by up to this much (0 at yaw 0) |
| WheelAngleDeg (unbounded) | free | 5 deg steps all round: no new contact with the pedestal; handle tips clear the deck by {100 * H['wheel_spin']['min_wheel_to_deck_m']:.1f} cm |
| NozzlePitchDeg / NozzleRollDeg (+-5) | {'; '.join(noz)} | pitch + / -, roll + / -; free to the 12 deg test limit except where shown. The joint is flat: the nozzle top drops 14 cm below the drum on one side at 5 deg (research_blender.md 3.2) |
| NozzleFlareDeg (-10..+35) | {hard('NozzleFlareDeg_FL -20'):+.0f} .. {hard('NozzleFlareDeg_FL +45'):+.0f} | all four; closing past -16 hits the throat recess |
| Pods (physics jiggle +-3) | {'; '.join(pods)} | pitch +/-, roll +/- (same axes as the nozzle). The pods sit in tight pockets: +-0.5 is clean everywhere, +-1 pushes a rib up to 4 cm into the pocket wall on the tight side, +-3 the ribs and drum up to 15 cm (inside the pocket, so it only shows at close range) |
| TurbineYawDeg (+-12) | L {hard('TurbineYawDeg_L -40'):+.0f} .. {hard('TurbineYawDeg_L +40'):+.0f}, R {hard('TurbineYawDeg_R -40'):+.0f} .. {hard('TurbineYawDeg_R +40'):+.0f} | the inboard turn stops at 12 on the steam band, the outboard one at 33 on the hull skin. The 10 steam-pipe ends per side plugged into the intake lip stay on Hull and clip inside the nacelle (allowed, research 3.3) |
| RotorAngleDeg | free | full turn at yaw -12, 0 and +12, clear of the pylon slab |
| RudderDeg (+-30) | +-60 | free to the test limit (hinge part buried in the stern) |
| Turbine rods (small pendulum) | +-20 | both axes, free (not swept in the research) |
| Search light posts (wobble +-4) | +-15 fore/aft; -6 .. +15 sideways | tilting the posts toward port, the AftL post meets the gantry rail at 7 deg; the heads pan freely all round |
| ChainFwd swing | 0 .. +25 (outward only) | + = right-handed about ChainFwd -> ChainFwd_End (Blender), swings the sag out to starboard. Inward the links go into the bow wedge at once (-10 deg: 30 cm). At rest the chain already dips up to 12 cm into the wedge and 5-7 cm into the side panels; swinging out lifts it clear except the last link at end B (in its panel, up to 8 cm at +25). The research's "free to 45 both ways" missed this because the chain touches the wedge at rest |
| Winch spin | free | |

## What to know in Unreal

* Import `SK_Airship.fbx` as a Skeletal Mesh with a new skeleton `SKEL_Airship`: Convert Scene on (default), Force Front X
  Axis off, no unit tricks (the file is cm, UnitScaleFactor 1), Normals: Import, Use T0 As Ref Pose off, no animation,
  materials not created (assign `M_Airship` to slot 0 and `M_AirshipProps` to slot 1). The legacy FBX importer
  (`Interchange.FeatureFlags.Import.FBX false`, as used for SM_Airship) skips a Blender node named `Armature`
  (FbxMainImport.cpp, GetRootSkeleton), so the root bone is `root`, as with the Burrower FBX made the same way.
* Expected after import: 118 bones, root `root` with one child `Hull`; ship about 52 m long, bow +X, Z up; `Cannon_L1` at
  about {UE_L1}, `Thruster_FL` at (383, -466, -93). Every bone's reference rotation should be the identity
  (in the file the root LimbNode carries Lcl Rotation (-90, 0, 0), which Unreal's Y-up -> Z-up scene conversion turns into
  the identity; every other node is identity). If an importer shows a different but common rotation on all bones, the rig
  still works: the Control Rig bakes its axes from the rest pose.
* Sockets for C++/Niagara: `Thruster_*_Flame` (exhaust along A = (-0.139, 0, -0.990) in Blender, UE (-0.139, 0, -0.990)),
  `Turbine_*_Exhaust` (blows toward -X), `Cannon_*_Muzzle` (fire along Muzzle - Barrel: +Y Blender = UE -Y for L guns,
  UE +Y for R guns), `PilotSeat`, `ChainFwd_End` (chain swing axis with `ChainFwd`).
* Axes for the Control Rig (from the rest pose, so no local axis is assumed): petal hinge axis = A x d (d = the petal's
  radial unit; the bone sits on the hinge at the top edge, h = 3.90 m along A, r = 1.42 m); fan rotor spins about +X;
  cannon elevation about the true trunnion axis = the cannon's own Y, which is horizontal up to the {max(ROLL1, ROLL2):.1f} deg deck roll
  (using Z x aim instead moves the trunnion ends by about 2 mm, invisible); cannon wheels spin about the same axis.
* Clamp the controls to the safe ranges above: elevation +8.75, aft yaw of L2/R2 21 deg, chain outward only, pods +-0.5..1
  if close-ups matter. `SK_Airship_testanim.fbx` stays inside those ranges (elevation +8.75 max, chain 0..+25) except the
  pods (+-3, the contract's value) and the extra helper sweeps (rods +-8, posts +-4).
* Triangle count {tris:,} (hull {HULL_T:,}); bounds about 51.9 x 23.9 x 17 m like SM_Airship plus the props.

## Deviations from the contract

1. **Cannons are rolled to the deck** ({ROLL1:.2f} / {ROLL2:.2f} deg about the firing axis) instead of "Z up". With Z up the
   uphill wheels sank {SINK1:.1f} cm (fore pair) and {SINK2:.1f} cm (aft pair) into the deck. The aim (Muzzle - Barrel) is unchanged; the
   Barrel/Muzzle/Quoin/wheel bones move up to {SHIFT1:.1f} cm (fore) / {SHIFT2:.1f} cm (aft) along X compared with the unrolled frame. `rig_place.py -- --cannon-roll off`
   restores Z up.
2. **Aft guns {c2['nudge_inboard_m']:.2f} m further inboard** (muzzle face {c2['muzzle_face_inside_rail_m']:.2f} m inside the rail centre line, not 0.12). The rail
   there runs at {abs(c2['rail']['slope_deg']):.1f} deg to the ship's axis, so with 0.12 m the muzzle hits it before the gun has yawed 10 deg aft.
   The script moves the gun inboard in 1 cm steps until yaw +-20 at elevation -10/0/+9 and recoil 0/30/60 is clear by 2 cm.
   The ball path is unchanged: through the gap between mid and top bar.
3. **Elevation +9** is 0.25 deg past what the cannon model allows (+8.75, the barrel meets its carriage); the test animation uses +8.75.
4. **Export bone axes**: `primary_bone_axis='Z'`, `secondary_bone_axis='X'` instead of the Burrower's Y/X. Everything else
   is the Burrower export (cm, `Armature` node, root `root`, Y-up file with pre-rotated data, no leaf bones, smoothing by face).
   With Y/X our up-pointing Blender bones would arrive in Unreal rotated 90 deg about X; with Z/X they arrive as identity.
5. Petal hinges are taken from the geometry (centre of each petal's top edge): h = 3.90 m along A as in the contract, radius
   1.42 m instead of the formula's 1.45 (the formula's radius is the petal's outer face; the bone sits mid-thickness).
6. The contract's ChainFwd end labels are swapped relative to research end_a/end_b; the contract's coordinates are used
   (`ChainFwd` at (26.545, -2.946, 4.320) m, `ChainFwd_End` at (21.464, -3.353, 2.961) m).
7. Exact socket spots where the contract says "about": `Thruster_*_Flame` on the nozzle axis at the petal tips (h = 4.35 m
   along A); `Turbine_*_Exhaust` at the duct shell's rear rim, x = -18.758 m.

## Round 2 (2026-11-24)

Talal's asks for the ship model: "ship wheel smaller to the size of the character", "pointed items to be removed" (5
arrows on a top view), "bigger canon balls", "machine gun turrets (2) in front". Specification:
`Docs/Airship/round2/SPEC_A.md` D7; notes: `Docs/Airship/round2/NOTES_blender.md`.

* **Deck pieces removed** from the rig's SM_Airship (`scripts/deck_removals.json`, deleted in `rig_build.py` after the
  source checks; Talal's StylizedAirship.blend and the Unreal `/Game/Assets/MyShip/SM_Airship` physics body with its UCX
  are not changed): {len(DR['removed_islands'])} islands, {DR['removed_verts']} vertices, {DR['removed_tris']} triangles; all were on the `Hull` bone, so the
  skeleton is the same (118 bones, same names).

  | Arrow | Piece | Islands | Box (UE cm, X / Y / Z) | Vertices |
  |---:|---|---|---|---:|
{REMOVED_ROWS}

* **Wheel at character size** (`scripts/props/model_helm.py` v3): {TD['helm_wheel_size_cm'][1] if TD else '?'} cm across the handle tips (was 310), axle
  {WHEEL_OFS[2]} cm above the deck (was 165), wheel centre {-WHEEL_OFS[0]} cm aft of the pedestal origin (was 63), pedestal scaled
  by 1.00 / 1.65. `Helm_Wheel` is now at {T(H['wheel_axle_ue_cm'])}, `PilotSeat` at {T(H['pilot_ue_cm'])} (was (-713, 0, 425) and
  (-843, 0, 269)). Unreal: `AirshipPawn.h` `PilotSeatFallback` = the new PilotSeat; the PA_Airship helm boxes (not rebuilt in
  PR A) are larger than the new wheel.
* **Cannon bore** (`scripts/props/model_cannon.py` v3): bore radius 22 cm (was 13), muzzle face from radius 25 to the 28 cm
  lip, for the 1 m cannonball. Sockets and the barrel length are unchanged.
{TURRET_TXT}
* **Prop atlas** (`scripts/props/bake_props_comic.py`): the turret joins the helm and cannon on the 2048 atlas (all islands
  repacked: the helm, cannon and turret UVs all moved, so `T_AirshipProps_ComicLines` / `ComicMask` must be re-imported
  together with the meshes); the helm's ink lengths are scaled with it (wheel 0.45, pedestal 0.6: `INK_SCALE`).
* Rebuild: `bash rig/scripts/props_all.sh` (models + atlas + bake), `bash rig/scripts/rig_all.sh`, then
  `bash rig/scripts/verify_all.sh`; copy `export/SK_Airship*.fbx`, `export/SM_AirshipTurret_*.fbx`,
  `checks/rig/turret_dims.json`, `props/textures/T_AirshipProps_Comic*.png` and this README to `SourceArt/Airship`.
  Review renders: `rig/renders/round2/` (before / after, helm and turret close-ups with the mech capsule).

## Change log

* **2026-11-22, fore cannon pair moved forward to Talal's mark.** `Cannon_L1` / `Cannon_R1` (and all their sub-bones
  and sockets) moved from the rail-post gap at x -5.344 m to the gap at x {c1['gap_x']} m: UE ({MOVE_UE[0]:+.1f}, {MOVE_UE[1]:+.1f}, {MOVE_UE[2]:+.1f}) cm for
  L1, Y mirrored for R1. Why: the contract read Talal's fore mark in `talal_sketches/3_cannon_spots.png` as "about x -5.3",
  which put the guns between his two marks. With the sketch camera solved from 6 landmarks (within 1.4 px,
  `checks/verify/sketch_camera.json`) the rigged cannon was projected at every port rail gap
  (`scripts/verify_station_fit.py` -> `checks/verify/station_fit.json`): at {SF1['best']} its silhouette centre is {SF1['dx']:+.0f} px from the
  mark's centre and {100 * SF1['inside']:.0f} % of it lies inside the mark (gap -1.387: {SF1['dx_1387']:+.0f} px, {100 * SF1['in_1387']:.0f} %; old gap -5.344: {SF1['dx_5344']:+.0f} px, {100 * SF1['in_5344']:.0f} %). Other readings of
  the same mark: ray hits on the ship median x -0.65; the mark cast onto the rail's vertical surface spans x
  {SF1['rail'][0]} .. {SF1['rail'][2]} (median {SF1['rail'][1]}). The aft pair stays at gap -11.472 (ray-hit median -11.33; that mark is seen too
  edge-on to pin it closer than a few metres). `RIG_CONTRACT.md` section 4 was updated. The new muzzle sockets are at UE
  {ue('Cannon_L1_Muzzle')} (L1) and {ue('Cannon_R1_Muzzle')} (R1); `AirshipPawn.h` `CannonMuzzleFallback` (only used when the
  mesh has no muzzle bones) holds these positions too. Other stations: set `CANNON_TARGET_X` L1/R1 in `rig_common.py`
  (-1.3 = the next gap aft, -5.3 = the old station) and run `rig_all.sh`.

## How it was checked

* Blender side (`rig_build.py`): every bone world-aligned (rest matrix = 90 deg about X, head at the pivot), deform flag
  exactly on the bones that have vertices, every vertex one group at 1.0, SM_Airship positions + UVs + face corners of
  the kept part hashed before the deck pieces are deleted and again after skinning (unchanged), prop pivots on the
  placed objects' origins.
* FBX (`rig_fbx_inspect.py`, Blender's raw FBX parser, no importer logic): FBX 7.4, Y-up, UnitScaleFactor 1; 1 Null
  `Armature` (identity) -> 118 LimbNodes, 31 meshes each with one Skin, 105 clusters, every vertex weighted once with sum 1,
  bind poses cover all 118 bones and agree with every cluster's TransformLink, node transforms agree with the bind pose
  (max {fbx['node_chain_vs_bindpose_max_diff']:.4f} cm); materials in file order {fbx['materials_in_file_order']}; Unreal view of every bone
  (Y-up -> Z-up, handedness flip): max rest rotation {fbx['ue_max_rest_rotation_deg']} deg.
* Round trip (`rig_roundtrip.py`): both FBX files re-imported into an empty scene: same 118 bones and parents
  (position error {1000 * rt['rest']['bone_max_pos_err_m']:.4f} mm, rotation error {rt['rest']['bone_max_rot_err_deg']} deg), same {rt['rest']['vertices']:,} vertices
  ({1000 * rt['rest']['vertex_max_pos_err_m']:.4f} mm) and weights (0 differences); the test animation deforms the re-imported meshes like the
  original rig at 16 frames across all segments (max {1000 * rt['testanim']['deformed_max_err_m']:.3f} mm, while the parts move up to 5.5 m).
* Clearance: `rig_place.py` (cannons and helm, numbers above), `rig_check_motion.py` (every other control).
* Independent verification (not using the rig_* code): `bash rig/scripts/verify_all.sh` (`verify_*.py`, about 1 min) writes
  `checks/verify/` (FBX structure, import + per-bone deform test, prop atlas, sketch camera fits + mark positions) and
  `renders/verify/` (rest/posed colour per bone, Talal's sketch views with his marks laid over, textured props).
* Renders (`renders/rig/`), looked at: colour per bone at rest (side, top, 3/4 above, 3/4 below, close-ups) and both limit
  poses; no tearing (every piece rigid), nothing floating, the only overlaps are the ones listed in the ranges.

## Appendix: all bones (UE cm)

| Bone | Parent | X | Y | Z | Vertices |
|---|---|---:|---:|---:|---:|
""" + '\n'.join('| %s | %s | %s | %s | %s | %s |' % (r[0], r[1] or '-', r[2], r[3], r[4], r[6]) for r in CSV_ROWS) + '\n'

out = RIG + '/export/README_rig.md'
with open(out, 'w') as f:
    f.write(md)
print('[readme]', out, len(md), 'chars')
