# SK_Airship rig contract (shared by Blender, C++ and the Control Rig)

Decided 2026-11-22 from `research_blender.md`, `research_control_rig.md`, `research_cpp.md`, `research_flight.md` and
Talal's sketches (`/mnt/new_partition/UnrealProjects/_AirshipWork_logs/talal_sketches/`). Change it only together with
every consumer.

Coordinates: Blender world metres (+X bow, +Y port = left, +Z up). Unreal component space = (100x, -100y, 100z) cm.
Names use physical sides: L = port, R = starboard (port is Blender +Y, Unreal -Y).

## 1. Files

| What | Where |
|---|---|
| Rig .blend (copy, Talal's StylizedAirship.blend is never saved) | `/mnt/new_partition/BlenderProjects/StylizedAirship/rig/AirshipRig.blend` |
| Prop models | `.../rig/props/Helm.blend`, `Cannon.blend`, `AirshipProps.blend` (atlas) |
| Prop atlas textures (2048) | `.../rig/props/textures/T_AirshipProps_ComicLines.png` (sRGB), `T_AirshipProps_ComicMask.png` (linear) |
| Export for Unreal | `.../rig/export/SK_Airship.fbx` (cm, UnitScaleFactor 1, armature node `Armature` so UE drops it, root bone `root`, X forward, Z up, no leaf bones, no animation) |
| Checks | `.../rig/checks/` (FBX structure JSON, bone table, weight report), renders `.../rig/renders/` |
| Unreal assets | `/Game/Assets/MyShip/Drivable/` (SK_Airship, SKEL_Airship, PA_Airship, A_Airship_TestSweep, CR_Airship, ABP_Airship, BP_AirshipPawn, BP_AirshipCannonball; `Materials/` M_AirshipProps, M_AirshipCannonball; `Textures/` T_AirshipProps_*; `FX/` NS_Airship*; `Input/` IMC_Airship, IMC_AirshipBoard, IA_Airship*; `Physics/` PM_AirshipHull; `Maps/` L_AirshipTest). The existing `/Game/Assets/MyShip/SM_Airship` (8 UCX hulls) is reused as the pawn's physics body. |

## 2. Meshes and materials

* `SM_Airship` geometry and UVs are used **unchanged** (Talal hand-edited the bow underside). Skin weights are 100 %
  per loose island from `Docs/Airship/research/sm_airship_vertex_parts.json` (rigid parts, like the Burrower's hard
  pieces). Material slot 0 = `M_Airship` (existing comic-lines texture).
* New props (helm + 4 cannons) use material slot 1 = `M_AirshipProps` with the prop atlas. The 4 cannons are identical
  copies and share the same atlas region (same baked ink); everything else is overlap-free.
* All meshes skinned to one armature, exported as one FBX -> one skeletal mesh with 2 material slots.

## 3. Bones

Every bone's rest orientation is **world-aligned, no exceptions** (in Blender: head at the pivot, tail = head +
(0, 0, 0.5 m), roll 0), so in Unreal every bone has the same rest rotation as `root` and local axes = component axes.
The Control Rig still never assumes local axes: it bakes axes from the rest pose at build time (cannon aim = Muzzle -
Barrel rest positions; petal hinge axis = A x d from the petal's rest position around its nozzle axis). Rest scale 1.
`(skin)` = has vertex weights; others are sockets/markers only. Every part root is a direct child of `Hull`.

| Bone | Parent | Pivot (Blender m) | Skin | Motion (rig) |
|---|---|---|---|---|
| root | - | (0, 0, 0) | - | actor origin |
| Hull | root | (0, 0, 0) | Hull islands, FanMount_L/R, HangStrip_1..4, ChainAft, all hull geometry | kinematic body |
| Thruster_FL / FR / RL / RR | Hull | pod object origins: FL (3.833, 4.656, -0.934), FR (3.833, -4.918, -1.130), RL (-7.167, 5.130, -1.204), RR (-7.167, -5.768, -1.239) | Pod_* islands | physics jiggle only, +-3 deg (tight hull pockets) |
| Thruster_*_Nozzle | Thruster_* | nozzle joints: FL (3.499, 4.656, -3.711), FR (3.499, -4.918, -3.907), RL (-7.501, 5.130, -3.980), RR (-7.501, -5.768, -4.016) | Nozzle_* islands except petals | thrust vectoring pitch/roll +-5 deg |
| Thruster_*_Petal00..11 | Thruster_*_Nozzle | petal hinge = T0 + 3.9 A + 1.45 d (T0 = pod origin + (0,0,-0.4), A = (-0.139, 0, -0.990), d = petal radial unit); hinge axis = A x d (computed by the rig, + flares out) | one petal each (index from the island classifier) | flare with throttle (-10 .. +35 deg) |
| Thruster_*_Flame | Thruster_*_Nozzle | nozzle exit centre (along A below the petal tips) | - | Niagara socket; exhaust direction = A (rest) |
| Turbine_L / R | Hull | yaw pivot (-17.2, +-5.35, 1.4) | FanHousing_* islands (+ hanging rod if no own bone) | steering yaw, clamp +-12 deg |
| Turbine_*_Rotor | Turbine_* | (-17.2, +-7.6, 1.4) | FanRotor_* islands | spin about the duct axis (+X at rest) |
| Turbine_*_Rod | Turbine_* | rod top (-17.2, +-7.6, -2.126) | the hanging rod island | small pendulum |
| Turbine_*_Exhaust | Turbine_* | duct rear exit centre (about -18.8, +-7.6, 1.4) | - | wind/exhaust FX socket, blows toward -X |
| Rudder | Hull | hinge x -16.364, y 0, z 0.7 (vertical line) | Rudder islands | follows steering, +-30 deg |
| SearchLight_AftL / MidL / MidR / FwdC | Hull | AftL (11.2, 2.8, 6.55), MidL (24.6, 2.4, 7.35), MidR (24.6, -2.4, 7.35), FwdC (30.4, 0.9, 7.35) | posts | spring wobble +-4 deg |
| SearchLight_*_Head | SearchLight_* | same x, y at head height: AftL z 9.70, MidL/MidR z 9.70, FwdC z 10.50 (refine to the head's real pivot) | head + lens | slow pan |
| ChainFwd | Hull | chain end A (26.545, -2.946, 4.320) | ChainFwd links | pendulum about the A->B line |
| ChainFwd_End | ChainFwd | chain end B (21.464, -3.353, 2.961) | - | marker for the swing axis |
| Winch_Fwd / Winch_Aft | Hull | (30.4, 0, 5.0) / (28.3, 0, 5.0) | drum + flanges | optional idle spin about Y |
| Helm | Hull | pedestal base on the deck centreline at x -6.5 (z = deck height there, ~2.60) | Helm_Pedestal | static |
| Helm_Wheel | Helm | wheel axle centre (pedestal + the Helm.blend wheel origin offset) | Helm_Wheel | spin about the axle (X), multi-turn |
| PilotSeat | Hull | where the pilot stands: 1.3 m aft of the wheel axle on the centreline, z = deck | - | C++ attach point for the pilot (marker) |
| Cannon_L1 / L2 / R1 / R2 | Hull | carriage origin on the deck (see 4); cannon frame below = X firing direction (outboard), Z up (bone itself world-aligned) | Cannon_Carriage copy | yaw about Z, recoil slide along -X (cannon frame) |
| Cannon_*_Barrel | Cannon_* | trunnion axis centre (carriage + (0.30, 0, 0.80) in the cannon frame) | Cannon_Barrel copy | elevation about the trunnion axis |
| Cannon_*_Muzzle | Cannon_*_Barrel | muzzle face centre (carriage + (1.86, 0, 0.80)) | - | muzzle flash / projectile socket, +X out |
| Cannon_*_Quoin | Cannon_* | quoin origin (if the cannon model has a separate `Cannon_Quoin`) | quoin | slides back with elevation |
| Cannon_*_Wheel_FL / FR / BL / BR | Cannon_* | truck axle centres (carriage + (0.50, +-0.525, 0.22) and (-0.53, +-0.525, 0.22) in the cannon frame) | wheels | spin with recoil |

Cannon names: L1 = forward port, L2 = aft port, R1 = forward starboard, R2 = aft starboard.

## 4. Placement (Talal's sketches + deck survey)

* Helm: deck centreline at x -6.5 (between the two hatches, just forward of the aft hatch, which starts at x -8.9),
  wheel axle along X facing the bow; the pilot stands aft of it.
* Cannons, broadside, pointing outboard (+Y for L, -Y for R), 2 per side: forward pair near **x -0.46**, aft pair near
  **x -11.3** (Talal's marks). Snap each to the middle of the nearest rail-post gap (fore x -0.463, aft x -11.472).
  Changed 2026-11-22: the fore pair said "x -5.3" before, an eyeballed reading of `3_cannon_spots.png` that put the guns
  between his two marks. With the sketch camera solved from 6 landmarks (within 1.4 px; `rig/checks/verify/
  sketch_camera.json`) the cannon was projected at every rail gap (`rig/checks/verify/station_fit.json`): at x -0.463 it
  sits in the middle of the fore mark on Talal's screen (gap -1.387: at the mark's aft end; -5.344: outside it). The aft
  mark (ray hits median x -11.33) matched and did not move. Consumers: the FBX bones `Cannon_L1/R1*` moved about +488 cm
  in UE X; `AirshipPawn.h` `CannonMuzzleFallback` (used only without muzzle bones) follows the new
  `Cannon_*_Muzzle` sockets (listed in `rig/export/README_rig.md`). Carriage origin on the deck so that
  the **muzzle face stays about 0.12 m inside the rail** (the 0.56 m muzzle can't pass between the rail bars; the ball
  flies through the 0.48 m gap between the mid bar and the top bar). Barrel axis height = carriage + 0.80 m.
  Check yaw (+-20 deg target) and elevation (-10..+9 deg) clearance against the rail and deck props; report the safe
  ranges.

## 5. Control Rig variables (C++ UAirshipAnimInstance writes these names into the rig instance)

All `float` unless stated; created as public rig variables.

| Variable | Unit / range | Meaning |
|---|---|---|
| NozzlePitchDeg_FL, _FR, _RL, _RR | deg, +-5 | nozzle about hull +Y (UE): + swings the nozzle exit aft (thrust pushes forward) |
| NozzleRollDeg_FL, _FR, _RL, _RR | deg, +-5 | nozzle about hull +X (UE): + swings the exit toward UE +Y |
| NozzleFlareDeg_FL, _FR, _RL, _RR | deg, -10..+35 | petal flare, + = open |
| ThrustAlpha_FL, _FR, _RL, _RR | 0..1.5 | thrust level (for FX/scale; the rig may ignore it) |
| TurbineYawDeg_L, _R | deg, +-12 | about hull +Z: + turns the fan axis from +X toward UE +Y |
| RotorAngleDeg_L, _R | deg, [0, 360) | rotor spin angle |
| RudderDeg | deg, +-30 | about the hinge, hull +Z (UE), standard rotation like TurbineYawDeg: + swings the trailing edge toward UE -Y (port), so a right turn (D) is negative (sign pinned 2026-11-22) |
| WheelAngleDeg | deg, unbounded | helm wheel angle about the axle, hull +X (UE), standard rotation: a right turn (D, clockwise as the pilot sees it) is negative (sign pinned 2026-11-22) |
| CannonYawDeg_L1, _L2, _R1, _R2 | deg, +-20 | about hull +Z |
| CannonElevDeg_L1.._R2 | deg, -10..+8.75 | + raises the muzzle (8.75: the barrel meets its carriage; the C++ sends at most 8.5, eased in, since fix round 2 on 2026-11-22; 9 before session 3) |
| CannonRecoilCm_L1.._R2 | cm, 0..60 | slide back along -aim |
| SearchLightPanDeg | deg | shared slow pan of the 4 heads (each head may add its own offset) |
| bIsDead | bool | death switch (Fx solver Alpha 1 -> 0, Wreck solver Alpha 0 -> 1) |
| DeathTime | s since death, 0 alive | timed break-offs |
