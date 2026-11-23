# CR_Airship: Control Rig design for the rigged airship (UE 5.8)

Read-only research, 2026-11-22. No editor or commandlet was run. Every engine claim cites the 5.8 source at
`/mnt/new_partition/5.8/Engine`. "Verified in editor" means the Burrower build proved it in this engine
build (bw_04 built CR_Burrower: 209 nodes, compile clean; bw_04b 124/124 numeric checks; PIE all PASS, commits
a52a516 / 9727f1d, logs in `_BurrowerWork/Saved/Burrower/04_cr.out`, `04b_cr.out`, `bw_04_control_rig.json`).
"Source" means it was read in the C++ and has not been run. Anything not checked is marked [unverified].

Source tags (all under `/mnt/new_partition/5.8/Engine/`):

| Tag | Path |
|---|---|
| CRP | `Plugins/Experimental/ControlRigPhysics/Source/ControlRigPhysics` |
| CRD | `Plugins/Experimental/ControlRigDynamics/Source/ControlRigDynamics` |
| PC | `Plugins/Animation/PhysicsControl/Source/PhysicsControl` |
| CR | `Plugins/Animation/ControlRig/Source/ControlRig` |
| CRDev | `Plugins/Animation/ControlRig/Source/ControlRigDeveloper` |
| RVM | `Plugins/Runtime/RigVM/Source/RigVM` |
| ENG | `Source/Runtime/Engine` |
| CHAOS | `Source/Runtime/Experimental/Chaos` |
| BW | `/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Burrower/scripts` (notes_cr_core.md, notes_cr_plugins.md, bw_cr_helpers.py, bw_04_control_rig.py) |

---

## 0. Verdict

* **Two ControlRigPhysics solvers, both in Component space**, plus plain control math on the hierarchy:
  * **FxSolver** (owner `root`): alive secondary motion. A kinematic Hull body; every moving part is a simulated
    body jointed to its hierarchy parent, with an angular drive that targets the control pose. Inertial forces from
    the ship's motion make the parts lag, wobble and overshoot. No world collision. `Alpha = 1 - bIsDead`.
  * **WreckSolver** (owner `Hull`): death. The same parts again as separate bodies. Break-off parts have no joint,
    the cannons are jointed limp (soft limits, no drive). Static world collision. `Alpha = bIsDead`, tracking during
    pass-through. This is the Burrower ragdoll switch (Alpha 0 -> 1), which is verified in editor and PIE.
* Component space is required for death, not only for the wobble. A World-space solver starts the bodies
  without the actor's velocity (BW notes_cr_plugins row 5; CRP/Private/RigPhysicsSolver.cpp:1096-1131), so debris
  from a ship flying at 30 m/s would stop in mid-air. In Component space the inertial pseudo-forces keep the
  ship's momentum and turn rate (CRP/Private/RigPhysicsSolver.cpp:2108-2128).
* There are runtime setters for drive strength, limits, joint on/off, movement type, blend weight, gravity
  multiplier, collision mode and space motion. All are source-verified (section 7a), none has been run. Keep them for
  v2 effects (timed break-offs). The death switch itself uses only the verified Alpha pattern.
* Feed the rig from C++: the anim instance writes the 32 public rig variables straight into the Control Rig
  instance of the AnimBP node, in `NativeThreadSafeUpdateAnimation`. No "Use Pin" clicks are needed, and a
  rebuilt rig keeps working. This is source-checked only. The Burrower "Use Pin" path (SlateInspector, verified)
  is the fallback (section 7d).
* The rig needs no physics asset. Give the SK a simple kinematic PA anyway: without one the mesh bounds stay fixed
  and falling debris is culled (ENG/Private/Components/SkinnedMeshComponent.cpp:2269-2291). Section 7e.

---

## 1. What the rig does each frame

```
Forwards Solve
 1. controls  : gimbal, nozzle scale, turbine yaw, rotor spin, rudder, wheel, cannon yaw + recoil + elevation
                (Set Rotation / Set Scale / Offset Transform on the hierarchy, from rig variables)
 2. StepFx    : Alpha = 1 - Dead, bodies drive toward the pose from step 1, write back with the wobble
 3. death kick: Branch(bIsDead) -> Run Once -> Add Force (VelocityChange) on Wreck break-off bodies   [optional]
 4. StepWreck : Alpha = Dead. Alive: pass-through that snaps its bodies to the pose after step 2 (with velocity).
                Dead: simulates (limp cannons, falling parts, Static world collision), writes back
 5. StepChains: ControlRigDynamics wire solver for ChainAft/ChainFwd                                  [optional]
```

Why this order is right:
* Every body reads its target and source pose from the **current hierarchy at the moment its Step node runs**, not
  from the AnimBP input or the initial pose. Joint drive target: `Hierarchy.GetGlobalTransform(ChildSourceKey/
  ParentSourceKey)` (CRP/Private/RigPhysicsSolver.cpp:1418-1426). Kinematic source: `Record.SourceComponentSpaceTM
  = Hierarchy.GetGlobalTransform(SourceKey)` (:1044, target set :1166-1236). So step 1 must come before step 2.
* The Wreck pass-through snaps dynamic bodies to that same hierarchy pose, with velocity, every frame
  (:2023-2059, `ResetPoseFromAnimation(..., true)` :2039). Running it after StepFx means death starts from the
  wobbling pose and its velocities, so there is no pop.
* Write-back uses `SetGlobalTransform(..., bAffectChildren = true)`, root to leaf (:1897-1955, calls at :1938/1951). Bones without a
  body (nozzle, rotor, muzzle, wheel) keep the local transform step 1 gave them and ride on their simulated parent.

---

## 2. Bones and per-part plan

Assumed UE bone names, matching the task list. Every part root must be a **direct child of `Hull`**, the barrel
of its carriage, the nozzle of its thruster, the rotor of its turbine, the wheel of `Helm`. The joint's
auto parent frame is the child's *initial local* transform (CRP/Private/RigPhysicsSolver.cpp:904-911), which
is only right when the parent body sits on the child's hierarchy parent. Keep every bone's rest scale at 1:
write-back sets unit-scale transforms.

| Bone(s) | Control (rig variable) | FxSolver body | WreckSolver |
|---|---|---|---|
| `Hull` | none | Kinematic, NoCollision | Kinematic, deck box PhysicsOnly |
| `Thruster_FL/FR/RL/RR` | gimbal: ThrusterPitchDeg_*, ThrusterRollDeg_* | Simulated, SLERP drive, soft limits (pocket clearance) | Break (no joint) + kick |
| `Thruster_*_Nozzle` | NozzleScale_* (Set Scale) | none | none (rides on the thruster) |
| `Turbine_L/R` | TurbineYawDeg_* | Simulated, SLERP drive | Break + kick |
| `Turbine_*_Rotor` | RotorAngleDeg_* | none (spin is kinematic) | none |
| `Rudder` | RudderDeg | Simulated, SLERP drive | Break |
| `Helm` | none | none | none |
| `Helm_Wheel` | WheelAngleDeg (multi-turn) | none: a SLERP drive takes the short arc past 180 deg | none (C++ free-spins it after death) |
| `Cannon_L1/L2/R1/R2` (carriage) | CannonYawDeg_*, CannonRecoilCm_* | Simulated, linear+angular drive, linear sphere limit | Limp joint to Hull |
| `Cannon_*_Barrel` | CannonElevDeg_* | Simulated, SLERP drive | Limp joint to carriage |
| `Cannon_*_Muzzle` | socket only | none | none |
| `SearchLight_*` posts (the "lamp posts") | none | Simulated, stiff wobble, soft limits | Break |
| `ChainAft_*`, `ChainFwd_*` (if bone chains) | none | ControlRigDynamics chains, both ends kinematic | same (stays) |

Clearance data from the parallel Blender analysis (`Docs/Airship/research/rig_clearance.json`, Blender metres and
axes, work in progress) puts hard numbers on the limits:
* Thruster pods: rest clearance 1 mm, gimbal cone 0-2 deg minimum (RR 0, FR 1), 4-10 deg in the best directions.
  The physics limit and the C++ gimbal range must stay inside this, or the pockets must be widened in Blender.
* Fans: the pylon struts are embedded for yaw -35..+35 and the blades touch the pylon at rest (48 samples). This is a
  model issue to settle before the yaw range is fixed.
* Rudder: leading-edge hinge, axis (-0.0547, 0, -0.9985), +/-24 deg; or vertical aft-face hinge +/-54 deg.
* Searchlight posts: 3 m post, head 0.9 m clear, tilt limit 0 deg toward the rail, up to 30 deg the other way.
* Axis conversion: UE = (100 x, -100 y, 100 z) cm from Blender (x, y, z) m. Blender +Y (port) is UE -Y.

---

## 3. Variables

All are created with `rig.add_member_variable(name, cpp, True, False, default)` (BW notes_cr_core section 2). Use
`'float'`, which gives an FFloatProperty, and `'bool'`. 32 public variables, no private ones. Axes are baked into
pin defaults at build time (section 6.1).

| Variable | Type | Unit / range | Meaning (sign) |
|---|---|---|---|
| ThrusterPitchDeg_FL, _FR, _RL, _RR | float | deg, inside the pod clearance | about hull +Y (UE): + moves the nozzle exit aft, so the thrust pushes forward |
| ThrusterRollDeg_FL, _FR, _RL, _RR | float | deg | about hull +X: + moves the nozzle exit toward +Y (UE right), so the thrust pushes left |
| NozzleScale_FL, _FR, _RL, _RR | float | 1.0 = rest, about 1.0-1.35 | nozzle bone local scale (thrust dilation) |
| TurbineYawDeg_L, _R | float | deg | about hull +Z: + turns the fan axis from +X toward +Y |
| RotorAngleDeg_L, _R | float | deg, wrapped [0, 360) | about the rotor spin axis at rest |
| RudderDeg | float | deg, +/-24 (leading-edge hinge) | about the hinge axis |
| WheelAngleDeg | float | deg, unbounded | about the wheel axle |
| CannonYawDeg_L1, _L2, _R1, _R2 | float | deg | about hull +Z |
| CannonElevDeg_L1.._R2 | float | deg | about e = aim x Z (algebraic cross product, component space): + raises the muzzle |
| CannonRecoilCm_L1.._R2 | float | cm, 0..60 | slide back along -aim in the yawed carriage frame |
| bIsDead | bool | | death switch for both solvers |
| DeathTime | float | s since death, 0 alive | only for v2 timed breaks |

The fun is in C++ (anim instance, every machine): critically damped or underdamped springs on the control targets
(wheel overshoot about 10 %, a recoil curve with a fast attack of about 0.06 s and an eased return of about 0.5 s,
gimbal slew-limited), and after death a free-spin decay of the wheel and a spin-down of the rotors. The rig adds
the physical lag and overshoot on top.

---

## 4. Construction Event (in this order)

Event node `/Script/ControlRig.RigUnit_PrepareForExecution` (event name `Construction`). A new rig has **no**
event nodes, so add both (BW notes_cr_core section 1; RigUnit_PrepareForExecution.h:14-29). Pin text formats are
the BW ones: key `(Type=Bone,Name="x")`, component `(ElementKey=(Type=Bone,Name="x"),Name="PhysicsBody")`, bool
`True`/`False`, int without `.0`, enum short names (`Component`, `Static`, `SLERP`, `Kinematic`, `NoCollision`,
`LCM_Limited`), vectors `(X=..,Y=..,Z=..)`, arrays `(a,b)`. Physics node keys default to an **empty bone**, so always
set them (notes_cr_plugins row 3).

**Wreck first, then Fx.** A second body on the same bone gets the name `PhysicsBody_2`
(CR/Private/Rigs/RigHierarchy.cpp:8599-8618, `FName(Name, 3)`), and joints get `PhysicsJoint_2`. Forwards Solve only
refers to Wreck bodies (the kick), so spawning them first keeps them at the default `PhysicsBody`. All Fx keys are
used inside Construction only: **link** each Spawn Body output `PhysicsBodyComponentKey` into the joints'
`ParentBodyComponentKey` / `ChildBodyComponentKey` instead of typing them. After the build, run Construction on a
test instance and list `inst.get_hierarchy().get_all_component_keys()` (stub unreal.py:251460) to confirm the names.

### 4.1 WreckSolver

`/Script/ControlRigPhysics.RigUnit_SpawnPhysicsSolver`, node `C_WreckSolver` (Construction only,
CRP/Private/RigPhysicsSolverExecution.cpp:103-133; pins CRP/Public/RigPhysicsSolverExecution.h:69-108):

| Pin | Value | Why |
|---|---|---|
| Owner | `(Type=Bone,Name="Hull")` | component -> K(Hull, PhysicsSolver) |
| SolverSettings.bAutomaticallyAddPhysicsBodyComponents | False | default True (RigPhysicsData.h:675) |
| SolverSettings.SimulationSpace / CollisionSpace | Component / Component | momentum via inertial forces |
| SolverSettings.WorldCollisionType | Static | no runtime setter; gathered only while Alpha > 0 (BW row 7) |
| SolverSettings.bWorldCollisionIncludePhysics / IncludeQuery | True / False | |
| SolverSettings.WorldCollisionBoundsExpansion | 1.2 | |
| SolverSettings.PositionIterations / VelocityIterations / ProjectionIterations | 8 / 2 / 1 | ints |
| SolverSettings.FixedTimeStep / MaxDeltaTime / MaxTimeSteps | 0.0 / 0.0334 / 4 | as the Burrower |
| SolverSettings.MaxDepenetrationVelocity | 500.0 | default 0 = unclamped |
| SolverSettings.bResetFromPosition | False (default) | **keep it False**: it measures distance from the component origin (RigPhysicsSolver.cpp:1816-1833), and debris falls far |
| SolverSettings.bResetFromEvaluationInterval | False (default) | an off-screen gap must not snap the wreck back |
| TeleportDetection.PositionChangeThreshold / OrientationChangeThreshold | 3000.0 / 90.0 | cm, deg per update |
| TeleportDetection.LinearAccelerationThreshold / AngularAccelerationThreshold | 1000000.0 / 1000000.0 | cm/s2, deg/s2: let the crash jolt through |
| SpaceMotion.bClamp* | all False (default) | the wreck should obey free-body physics |
| SpaceMotion.InertialForces.Amount | 1.0 | per-term amounts stay 1 (RigPhysicsData.h:484-505) |
| SpaceMotion.Drag.LinearDragMultiplier / AngularDragMultiplier | 1.0 / 1.0 | body damping acts against the air (world) |

Wreck bodies, `/Script/ControlRigPhysics.RigUnit_AddPhysicsBody`, node `C_WBody_<bone>` (Construction only,
RigPhysicsBodyExecution.cpp:20-53; pins RigPhysicsBodyExecution.h:14-52). Common pins: `Owner` = bone,
`Solver.PhysicsSolverComponentKey` = `(ElementKey=(Type=Bone,Name="Hull"),Name="PhysicsSolver")`,
`Solver.bUseAutomaticSolver` = False, `BodyData.CollisionType` = PhysicsOnly, `BodyData.GravityMultiplier` = 1.0.
`Collision` = one box per part: `((TM=<bone-local OBB centre/rotation>,Extents=(X=..,Y=..,Z=..)))`. Extents are
**full** extents (RigPhysicsData.h:200-202). The OBBs come from the export's rig-info JSON (Burrower_rig_info
pattern). A body needs a shape with mass, otherwise `MassOverride` is ignored and the body has zero mass
(RigPhysicsSolver.cpp:610; BW row 9).

| Body | MovementType | Dynamics.MassOverride | LinearDamping / AngularDamping | Collision |
|---|---|---|---|---|
| Hull | Kinematic | 1 | 0 / 0 | thin deck box (top 40 cm of the deck only, so nothing under the hull starts inside it) |
| Thruster_* | Simulated | 4.0 | 0.05 / 0.3 | pod OBB |
| Turbine_* | Simulated | 6.0 | 0.05 / 0.3 | fan + housing OBB |
| Rudder | Simulated | 3.0 | 0.05 / 0.3 | blade OBB |
| Cannon_* | Simulated | 3.0 | 0.1 / 0.5 | carriage OBB |
| Cannon_*_Barrel | Simulated | 2.0 | 0.1 / 0.5 | barrel capsule (main axis = TM local +Z, FKSphylElem; RigPhysicsSolver.cpp:457-463) |
| SearchLight_* | Simulated | 1.0 | 0.05 / 0.3 | post + head OBB |

Wreck joints (`/Script/ControlRigPhysics.RigUnit_AddPhysicsJoint`, node `C_WJoint_<bone>`; Construction only,
RigPhysicsJointExecution.cpp:24-55; pins RigPhysicsJointExecution.h:15-58). Only the cannons have joints:

| Joint (Owner) | Parent <- link | Child <- link | JointData <- | DriveData <- |
|---|---|---|---|---|
| Cannon_* | C_WBody_Hull.PhysicsBodyComponentKey | C_WBody_Cannon_*.PhysicsBodyComponentKey | C_WLimpCarriage.JointData | C_WNoDrive.DriveData |
| Cannon_*_Barrel | C_WBody_Cannon_*.PhysicsBodyComponentKey | C_WBody_Cannon_*_Barrel.PhysicsBodyComponentKey | C_WLimpBarrel.JointData | C_WNoDrive.DriveData |

Pure makers (any event, RigPhysicsJointExecution.cpp:202-337):
* `C_WLimpCarriage` = `/Script/ControlRigPhysics.RigUnit_MakeArticulationJointData`: AngularLimit
  (X=30,Y=20,Z=20) deg (X twist, Y swing1, Z swing2; <0 free, 0 locked), SoftStrength (3,3,3) Hz, SoftDampingRatio
  (0.8,0.8,0.8). Linear stays locked.
* `C_WLimpBarrel`: AngularLimit (30,30,30), SoftStrength (3,3,3), SoftDampingRatio (0.8,0.8,0.8).
* `C_WNoDrive` = `/Script/ControlRigPhysics.RigUnit_MakeArticulationDriveData`: bEnableAngularDrive False.

`bDisableCollision` stays True (the default). It is applied once, at instantiate, as an ignore pair
(RigPhysicsSolver.cpp:920, 935-941). The carriage never touches the deck box, the barrel does. Break-off parts that
touch the deck box at rest: `/Script/ControlRigPhysics.RigUnit_HierarchyDisableCollisionBetween`
(PhysicsBodyComponentKey1 = the part, PhysicsBodyComponentKey2 = the Hull Wreck body; Construction only,
RigPhysicsBodyExecution.cpp:144-162).

### 4.2 FxSolver

`RigUnit_SpawnPhysicsSolver`, node `C_FxSolver`:

| Pin | Value | Why |
|---|---|---|
| Owner | `(Type=Bone,Name="root")` | -> K(root, PhysicsSolver) |
| SolverSettings.bAutomaticallyAddPhysicsBodyComponents | False | |
| SolverSettings.SimulationSpace / CollisionSpace | Component / Component | |
| SolverSettings.WorldCollisionType | None | no overlap queries while flying over the tiles |
| SolverSettings.PositionIterations / VelocityIterations | 8 / 1 | Burrower hoses used 12 / 1 |
| SolverSettings.FixedTimeStep / MaxDeltaTime / MaxTimeSteps | 0.0 / 0.0334 / 4 | |
| SolverSettings.bResetFromEvaluationInterval / EvaluationIntervalThresholdForReset | True / 0.25 | default threshold 0 resets on frame jitter (BW row 22) |
| TeleportDetection.PositionChangeThreshold | **2000.0** | cm per update. The default 100 is 30 m/s at 30 fps: a fast ship would trip "teleport" every frame and lose all inertia (RigPhysicsSolver_Space.cpp:205-207, 243-254) |
| TeleportDetection.OrientationChangeThreshold | 45.0 | deg per update |
| SpaceMotion.VerticalMotionScale | 1.0 | |
| SpaceMotion.bClampLinearVelocity / MaxLinearVelocity | True / 4000.0 | cm/s, caps the wind drag |
| SpaceMotion.bClampLinearAcceleration / MaxLinearAcceleration | True / 4000.0 | cm/s2, stops collision jolts from throwing parts |
| SpaceMotion.bClampAngularVelocity / MaxAngularVelocity | True / 2.5 | **rad/s** |
| SpaceMotion.bClampAngularAcceleration / MaxAngularAcceleration | True / 15.0 | **rad/s2** |
| SpaceMotion.InertialForces.Amount | 1.0 | tune 0.5-1.0 for how much lag you want |
| SpaceMotion.Drag.LinearDragMultiplier | 1.0 | with body LinearDamping 0 the rigid parts feel no wind; give a little to the searchlights |
| SpaceMotion.Drag.AngularDragMultiplier | 0.0 | angular damping acts relative to the ship (settling only) |

Fx bodies, node `C_FBody_<bone>`. Common pins: `Solver.PhysicsSolverComponentKey` =
`(ElementKey=(Type=Bone,Name="root"),Name="PhysicsSolver")`, `Solver.bUseAutomaticSolver` False,
`BodyData.CollisionType` NoCollision, `BodyData.GravityMultiplier` 1.0. Shapes only set the mass distribution here
(no collision), but that matters. The lever arm (COM to pivot) turns ship acceleration into torque, and the inertia
divides it. Use the same OBBs as Wreck, or empty `Collision` (auto capsule bone -> child,
CRP/Private/RigPhysicsBodyExecution.cpp:46-49 + RigPhysicsBodyComponent.cpp:166-185), plus `Dynamics.bOverrideCentreOfMass` True and `Dynamics.CentreOfMassOverride`
= part centroid in bone space (RigPhysicsSolver.cpp:619-621).

| Body | Type | Mass | LinDamp / AngDamp | Drive maker | Joint data |
|---|---|---|---|---|---|
| Hull | Kinematic | 1 | 0/0 | | (sphere r 50) |
| Thruster_* | Simulated | 4.0 | 0 / 0.5 | C_FDrvThruster | C_FJThruster |
| Turbine_* | Simulated | 6.0 | 0 / 0.5 | C_FDrvTurbine | default (angular free) |
| Rudder | Simulated | 3.0 | 0 / 0.5 | C_FDrvRudder | default |
| Cannon_* | Simulated | 5.0 | 0 / 0.5 | C_FDrvCarriage (Make Drive Data) | default + linear sphere limit (below) |
| Cannon_*_Barrel | Simulated | 3.0 | 0 / 0.3 | C_FDrvBarrel | default |
| SearchLight_* | Simulated | 1.0 | 0.1 / 0.3 | C_FDrvPost | C_FJPost |

Drive makers (pure, any event). Strength is the natural frequency in Hz: omega = 2*pi*Strength, stiffness =
omega^2 (PC/Public/PhysicsControlHelpers.h:58-68). The drives work in acceleration mode, so the response does not
depend on mass (ENG/Private/PhysicsEngine/ImmediatePhysics/ImmediatePhysicsAdapters.cpp:499).

| Node | Struct | Pins |
|---|---|---|
| C_FDrvThruster | RigUnit_MakeArticulationDriveData | bEnableAngularDrive True, AngularDriveMode SLERP, AngularStrength 3.0, AngularDampingRatio 0.35, AngularExtraDamping 0, SkeletalAnimationVelocityMultiplier 0.5 |
| C_FDrvTurbine | same | 2.0 / 0.4 / 0 / 0.5 |
| C_FDrvRudder | same | 3.0 / 0.5 / 0 / 0.7 |
| C_FDrvBarrel | same | 3.0 / 0.3 / 0 / 0.5 |
| C_FDrvPost | same | 2.5 / 0.2 / 0 / 1.0 |
| C_FDrvCarriage | `/Script/ControlRigPhysics.RigUnit_MakeDriveData` (RigPhysicsJointExecution.h:371-428) | bEnableLinearDrive True, LinearStrength 9.0, LinearDampingRatio 0.55, LinearExtraDamping 0, bEnableAngularDrive True, AngularDriveMode SLERP, AngularStrength 4.0, AngularDampingRatio 0.5, AngularExtraDamping 0, SkeletalAnimationVelocityMultiplier 1.0 |

SkeletalAnimationVelocityMultiplier scales the velocity target taken from the frame-to-frame target change
(RigPhysicsSolver.cpp:1437-1461). 1.0 tracks fast control changes tightly. Lower values give more lag and overshoot
when the pilot snaps a control.

Joint data:
* Default `FRigPhysicsJointData` = angular **free** on all 3 axes, linear **locked**, auto offsets,
  bDisableCollision True (ConstraintTypes.cpp:43-70; BW row "JointData"). With a SLERP drive this is fine for every
  controlled part, and it does not depend on how the bones are oriented.
* `C_FJThruster` = Make Articulation Joint Data, AngularLimit (X=3,Y=3,Z=3) deg, SoftStrength (6,6,6),
  SoftDampingRatio (1,1,1). It is a near-isotropic soft cone inside the pod clearance. Raise it once the pockets
  are widened.
* `C_FJPost` = Make Articulation Joint Data, AngularLimit (3,3,3), SoftStrength (6,6,6), SoftDampingRatio (1,1,1).
* Carriage: leave JointData unlinked and set its sub-pins: `JointData.LinearConstraint.XMotion` /
  `YMotion` / `ZMotion` = `LCM_Limited`, `JointData.LinearConstraint.Limit` = 80.0 (cm; Limited on 3 axes =
  sphere, ConstraintTypes.h comment on Limit; enum PhysicsCore/Public/Chaos/ChaosEngineInterface.h:186-196). The
  linear drive then follows the recoil translation that the rig puts on the carriage bone.

**SLERP rule (new, source):** if any angular axis is `Locked`, a SLERP drive is dropped **and** the twist/swing
drives are off too, so there is no drive at all. SLERP mode zeroes the twist/swing enables
(ImmediatePhysicsAdapters.cpp:505-518), and Chaos skips SLERP when an axis is locked
(CHAOS/Private/Chaos/Joint/PBDJointCachedSolverGaussSeidel.cpp:2495-2512). Use Limited (small angle) instead of
Locked, or `TwistAndSwing` mode.

Fx joints, node `C_FJoint_<bone>`: Owner = child bone, Parent/Child keys linked from the `C_FBody_*` outputs
(Hull -> part, carriage -> barrel), DriveData linked from the maker in the table, JointData as above.

### 4.3 Chains (optional, ControlRigDynamics, verified Burrower wire pattern)

Only if ChainAft/ChainFwd are exported as bone chains. `/Script/ControlRigDynamics.RigUnit_SpawnDynamicsSolver1`
(Owner root, Settings.SimulationSpace Component, MaxTimeStep 0.0167, NumConstraintSubIterations 4,
TeleportDetection.PositionChangeThreshold 2000, SpaceMotion clamps in **deg/s** and deg/s2: MaxAngularVelocity 180,
MaxAngularAcceleration 1440, InertialForces.Amount 0.6), then `RigUnit_SpawnDynamicsChains` (RootBones = chain
`_01`, ParticleProperties.GravityMultiplier **1.0**, since the node defaults it to 0) and
`RigUnit_HierarchySetDynamicsParticleMovementType` `Kinematic` on each `_end`. Set movement type only in
Construction: it is read only at instantiate (BW rows 15-16). Pins and values as BW bw_04_control_rig.py:248-279.

### 4.4 Instantiate

`/Script/ControlRigPhysics.RigUnit_InstantiatePhysics` x2 (keys K(Hull,PhysicsSolver), K(root,PhysicsSolver)), and
`RigUnit_InstantiateDynamics` if 4.3 exists. These go at the end of Construction, so allocation happens at spawn
(no event check, RigPhysicsSolverExecution.cpp:147-166; BW row 17).

---

## 5. Forwards Solve

Event `/Script/ControlRig.RigUnit_BeginExecution` (`Forwards Solve`). All execute pins are `ExecutePin`, variable
setters use `ExecuteContext`, and control flow uses `ExecuteContext` in and `True`/`False`/`Completed`/`Once` out
(BW notes_cr_core section 3).

### 5.1 One rotation control (pattern R, verified: Burrower wave and rotor, bw_04:843-877, 896-963)

| Node | Struct | Pins |
|---|---|---|
| `F_Get_<var>` | variable getter (`add_variable_node`) | output `.Value` |
| `F_Rad_<id>` | `/Script/RigVM.RigVMFunction_MathFloatRad` | Value <- getter; Result (rad) |
| `F_Q_<id>` | `/Script/RigVM.RigVMFunction_MathQuaternionFromAxisAndAngle` | Axis = baked bone-local axis (6.1), Angle <- Rad.Result |
| `F_Init_<bone>` | `/Script/ControlRig.RigUnit_GetTransform` | Item bone, Space `LocalSpace`, bInitial True |
| `F_QNew_<bone>` | `/Script/RigVM.RigVMFunction_MathQuaternionMul` | A <- Init.Transform.Rotation, B <- Q.Result (Result = A*B: the turn is applied in the bone's own rest frame) |
| `F_Set_<bone>` | `/Script/ControlRig.RigUnit_SetRotation` | ExecutePin chained; Item bone, Space `LocalSpace`, bInitial False, Weight 1.0, bPropagateToChildren True, Value <- QNew.Result |

* Two-axis gimbal: `F_Qp`, `F_Qr`, then `F_QComb` = QuaternionMul(A = Qp, B = Qr), and B of QNew <- QComb.Result.
  That is 10 nodes per thruster.
* Users: Thruster_* (gimbal), Turbine_* (yaw), Turbine_*_Rotor (spin), Rudder, Helm_Wheel, Cannon_* (yaw),
  Cannon_*_Barrel (elevation).
* Node-saving variant [unverified node]: `/Script/ControlRig.RigUnit_OffsetTransformForItem` (Item, OffsetTransform,
  Weight, bPropagateToChildren) does `New = Offset * Current` in the bone's own frame
  (CR/Private/Units/Hierarchy/RigUnit_OffsetTransform.cpp:41-43). Link Q.Result -> `OffsetTransform.Rotation`. That
  replaces Init, QNew and Set.

### 5.2 Cannon recoil (after the yaw Set)

| Node | Struct | Pins |
|---|---|---|
| `F_RecoilVec_<c>` | `/Script/RigVM.RigVMFunction_MathVectorScale` (template "Scale") | Value = baked bone-local -aim axis, Factor <- CannonRecoilCm getter |
| `F_Recoil_<c>` | `/Script/ControlRig.RigUnit_OffsetTransformForItem` | Item Cannon_*, OffsetTransform.Translation <- RecoilVec.Result, Weight 1.0, bPropagateToChildren True |

The offset is applied in the already-yawed carriage frame (Offset * Current), so the slide follows the aim. If the
-aim axis is a principal bone axis, skip the Scale template: link the float (times -1 from MathFloatMul) straight
into `OffsetTransform.Translation.X` (or .Y/.Z). Fallback with verified nodes only: QuaternionRotateVector(QNew,
axis*Recoil) + Init.Translation -> `RigUnit_SetTranslation` (LocalSpace).

### 5.3 Nozzle scale

`F_Nozzle_<t>` = `/Script/ControlRig.RigUnit_SetScale` (pins Item, Space, bInitial, **Scale**, Weight,
bPropagateToChildren; not a template; CR/Public/Units/Hierarchy/RigUnit_SetTransform.h:212-275): Item
Thruster_*_Nozzle, Space LocalSpace, bInitial False. Link the NozzleScale getter into `Scale.X`, `Scale.Y`, `Scale.Z`.
Leave the axial component at 1 if the thrust axis is a principal bone axis. This is a float -> double sub-pin link:
CanLink allows float/double casts (BW notes_cr_core section 3; RVD RigVMPin.cpp:2499-2506) [unverified for this
pin]. Fallback: `RigVMFunction_MathVectorFromFloat` (template "Cast"). Model rule: the nozzle mesh is 100 % on the
Nozzle bone, with the pivot at the throat. If the 12 petal hinges in rig_clearance.json become bones instead,
that is 12 x pattern R per thruster (about 290 nodes). Prefer one scale bone.

### 5.4 Death switch and steps

| Node | Struct | Pins |
|---|---|---|
| `F_Get_bIsDead` | getter | `.Value` |
| `F_DeadAlpha` | `/Script/RigVM.RigVMFunction_MathBoolToFloat` | Value <- getter; Result 0/1 |
| `F_AliveAlpha` | `/Script/RigVM.RigVMFunction_MathFloatSub` | A 1.0, B <- DeadAlpha.Result |
| `F_StepFx` | `/Script/ControlRigPhysics.RigUnit_StepPhysicsSolver1` (not the deprecated `RigUnit_StepPhysicsSolver`) | PhysicsSolverComponentKey K(root,PhysicsSolver), Alpha <- AliveAlpha.Result, bTrackVelocitiesDuringPassThrough **False** (never resumed), DeltaTimeOverride 0.0 |
| `F_DeathBranch` | `/Script/RigVM.RigVMFunction_ControlFlowBranch` | ExecuteContext <- StepFx; Condition <- bIsDead getter |
| `F_DeathOnce` | `/Script/RigVM.RigVMFunction_ControlFlowRunOnce` | ExecuteContext <- Branch.True (RVM/Public/RigVMFunctions/RigVMFunction_ControlFlow.h:74-110; Once only on the first run, .cpp:29-42) |
| `F_Kick_<bone>` x N | `/Script/ControlRigPhysics.RigUnit_HierarchyAddPhysicsBodyForce` | chained from Once; PhysicsBodyComponentKey K(bone, PhysicsBody) (Wreck); ForceAndTorque.Type `VelocityChange`, ForceAndTorqueSpace `World`, LocationSpace `Body`, Linear e.g. (X=0,Y=0,Z=350), Angular e.g. (X=2,Y=-1.5,Z=0.5) |
| `F_StepWreck` | `RigUnit_StepPhysicsSolver1` | ExecuteContext <- Branch.Completed; key K(Hull,PhysicsSolver), Alpha <- DeadAlpha.Result, bTrackVelocitiesDuringPassThrough **True** |
| `F_StepChains` | `/Script/ControlRigDynamics.RigUnit_StepDynamicsSolver` | optional, Alpha 1 |

Kick facts (source): forces are applied at the next step with Alpha > 0 and dropped on pass-through frames
(RigPhysicsSolver.cpp:2055-2057). `World` and `Component` both read the vector as **world** space
(RigPhysicsSolver.cpp:1277-1289). Kinematic bodies ignore forces (:1256). On the first dead frame the Wreck Alpha is
1 and the kick runs before StepWreck, so it lands.

Rough node count: Forwards about 160 (thrusters 48, turbines and rotors 24, rudder and wheel 12, cannons 60, death
and steps 15). Construction about 75. CR_Burrower had 209.

---

## 6. Build script notes (reuse BW bw_cr_helpers.py)

1. Axes are baked at build time from the rest pose. `q = H.global_tf(rig, bone, True).rotation` and
   `axis_bone = q.unrotate_vector(axis_cs)` (`Quat.unrotate_vector`, stub unreal.py:69299). Component axes:
   * gimbal: pitch +Y, roll +X
   * turbine and cannon yaw: +Z
   * rotor spin: the rotor's rest axis (fan +X)
   * rudder and wheel: hinge and axle from the rig info
   * cannons: aim = normalize(Muzzle_rest - Barrel_rest), elevation e = aim x Z, recoil = -aim
   * Write each axis as `(X=..,Y=..,Z=..)`.
2. `rig.set_auto_vm_recompile(False)` while building, then `H.compile_rig()` (recompile_vm + compile_blueprint +
   status) and `H.save_rig(path)` by explicit path, not during PIE (BW notes_cr_core section 6).
3. After the build, run `verify_struct` on every unit node: templates re-resolve (Multiply, Scale, Cast, Set
   Transform family).
4. Test without PIE (BW notes_cr_core section 7): `inst = rig.create_control_rig()`, `set_variable_from_string`,
   `execute('Construction')`, then per frame `reset_pose_to_initial(BONE)`, `set_absolute_and_delta_time`,
   `execute('Forwards Solve')`. Checks:
   * each control moves its bone by the requested angle about the baked axis (with InertialForces 0 or the
     instance still)
   * bIsDead False: Wreck bodies do not change the pose
   * bIsDead True for 30 frames: break-off parts fall, about 0.5 * 981 * t^2 cm in component Z with no world
   * component key names as expected (section 4)
   * World collision and inertial forces need PIE: a test instance has no world and a fixed component
     (BW notes_cr_core section 7.7).
5. PIE checks: wobble amplitude vs thrust and turn input, recoil spring, death (parts leave, cannons go limp,
   debris collides with platform tiles, nothing is culled), server and client.

---

## 7. Answers a-f

### a. Construction-only vs any event; runtime switches; death switch

| Node (struct under /Script/ControlRigPhysics.) | Event rule | Evidence |
|---|---|---|
| RigUnit_SpawnPhysicsSolver, RigUnit_AddPhysicsBody, RigUnit_AddPhysicsJoint, RigUnit_AddPhysicsControl, RigUnit_HierarchyInstantiateFromPhysicsAsset, RigUnit_HierarchyImportCollisionFromPhysicsAsset, RigUnit_HierarchyAutoCalculateCollision, RigUnit_HierarchySetBodySolverSettings, RigUnit_HierarchySetDynamics, RigUnit_HierarchySetCollision, RigUnit_HierarchyDisableCollisionBetween, RigUnit_HierarchySetPhysicsBodyTargetBone, RigUnit_HierarchySetPhysicsBodyMaterial | **Construction only** (logs "... can only be used during Setup", no assert) | SolverExecution.cpp:110-112; BodyExecution.cpp:26,74-76,93-95,113-115,132-134,151-153,185-187,305-307; JointExecution.cpp:30-34; ControlExecution.cpp:29; PhysicsExecution.cpp:178,579-583 |
| RigUnit_InstantiatePhysics, RigUnit_StepPhysicsSolver1, RigUnit_HierarchyAddPhysicsBodyForce / RemovePhysicsBodyForce | any event | SolverExecution.cpp:147-166, 266-313; BodyExecution.cpp:375-403 |
| Body: RigUnit_HierarchySetPhysicsBodyMovementType, ...CollisionType, ...GravityMultiplier, ...PhysicsBlendWeight, ...Damping, ...KinematicTarget, ...KinematicTargetSpace, ...SourceBone, ...SparseData, ...EnableCCD, ...UpdateKinematicFromSimulation, ...IncludeInChecksForReset | any event; re-applied **every step** | BodyExecution.cpp:164-372; applied in RigPhysicsSolver.cpp:1160 (movement, CCD, collision, gravity via anti-gravity force PC/Private/RigidBodyWithControl.cpp:137-171), :1240-1246 (damping), :1845 + :1935 (blend = Alpha x PhysicsBlendWeight) |
| Joint: RigUnit_HierarchySetJointData ("Set Physics Joint Properties"), ...SetJointLinearLimit, ...SetJointConeLimit, ...SetJointTwistLimit, ...SetJointEnabled, ...SetJointDriveData, ...SetJointDriveUseSkeletalAnimation | any event; sets a dirty flag, applied at the next step | JointExecution.cpp:69-199; RigPhysicsSolver.cpp:1341-1365 |
| Solver: RigUnit_SetPhysicsSolverSpaceMotion, RigUnit_SetPhysicsSolverTeleportDetection, RigUnit_SetPhysicsSolverExternalVelocity, RigUnit_HierarchySetPhysicsSolverAllowCCD | any event; read every step | SolverExecution.cpp:362-480; RigPhysicsSolver.cpp:2079-2128 |
| Controls: RigUnit_HierarchySetControlEnabled / ...AngularStrength / ...Multiplier / ...Target ... | any event; bEnabled checked every step | ControlExecution.cpp:69-260; RigPhysicsSolver.cpp:1671-1677 |
| Makers: RigUnit_MakeArticulationJointData, RigUnit_MakeArticulationDriveData, RigUnit_MakeDriveData | pure | JointExecution.cpp:202-395 |
| Not reachable at runtime: SolverSettings.WorldCollisionType, SimulationSpace, Gravity (no setter); body mass, shapes, material, TargetBone; Dynamics particle movement type | | SolverExecution.h (no setter); BW rows 16, 19 |
| Deprecated 5.8 twins, do not use: RigUnit_AddPhysicsSolver, RigUnit_StepPhysicsSolver, RigUnit_SetPhysicsSolverSimulationSpaceSettings / Get..., RigUnit_TrackInputPose | | SolverExecution.h:20,153,260,292,464 |

Enum text values: ERigPhysicsSimulationSpace `World / Component / SpaceBone`; ERigPhysicsWorldCollisionType
`None / Static / Dynamic / All` (RigPhysicsData.h:137-163); EPhysicsMovementType `Static / Kinematic / Simulated /
Default`; ECollisionEnabled `NoCollision / QueryOnly / PhysicsOnly / QueryAndPhysics`; EAngularDriveMode
`SLERP / TwistAndSwing`; EPhysicsControlForceType `Force / Acceleration / Impulse / VelocityChange`;
EPhysicsControlSpace `World / Component / Body`; ELinearConstraintMotion `LCM_Free / LCM_Limited / LCM_Locked`;
EAngularConstraintMotion `ACM_Free / ACM_Limited / ACM_Locked` (PhysicsCore/Public/Chaos/ChaosEngineInterface.h:113-123,
186-196); ERigVMTransformSpace `LocalSpace / GlobalSpace`.

Death switch: **WreckSolver Alpha 0 -> 1** (Burrower-verified pattern). Alpha <= 0 is a true pass-through: no
simulation, no world gathering, no write-back (RigPhysicsSolver.cpp:2023-2059). PhysicsBlendWeight 0 still
simulates (StepPhysicsSolver1 comment, RigPhysicsSolverExecution.h:230-237). Runtime-setter recipe for a v2 timed break of a
jointed Wreck part [unverified]: in one frame, `Set Physics Joint Enabled` False **and** `Set Physics Joint Drive
Properties` (drive off) **and** `Set Physics Joint Properties` with linear and angular all Free. Disabling alone can
be undone. `SetPhysicsJointEnabled(false)` zeroes the drive params as a UE-204006 workaround
(PC/Private/RigidBodyWithControl.cpp:40-55), but the solver then writes back the settings copy it took
*before* that call (RigPhysicsSolver.cpp:1343-1362), and per that comment a dirty actor re-enables the constraint.

### b. Drive targets, kinematic Hull, jointing

* Drive target with `bUseSkeletalAnimation` True (the default, RigPhysicsData.h:917; Make* leave it True). Target =
  (ChildConnector * child source bone global) relative to (ParentConnector * parent source bone global), both read
  from the **current hierarchy at Step time** (RigPhysicsSolver.cpp:1395-1427). Then the `OrientationTarget` /
  `PositionTarget` offset from DriveData is applied on top (:1430-1435). So any Set Rotation, Translation or Offset
  before the Step node becomes the target. Rest (connectors coincide) means the target is the initial pose. False
  means only the DriveData offsets are targeted.
* A target is set only if the joint is enabled and has drive stiffness or damping (:1368-1373). The velocity target
  comes from the target change times SkeletalAnimationVelocityMultiplier (:1437-1461).
* Kinematic Hull: Spawn Physics Body with BodyData.MovementType `Kinematic`. The defaults KinematicTargetSpace
  `OffsetInBoneSpace` (PC/Public/PhysicsControlData.h:248-257) and KinematicTarget identity give target = source
  bone pose every step (RigPhysicsSolver.cpp:1166-1197, 1234-1236). Verified in editor: the Burrower `_01` and `_end`
  hose anchors held at 0.0 cm drift (bw_04b_cr_check.json d01 / dend). Every body is created dynamic and turned
  kinematic at its first real step (:568-571, 1160).
* Jointing: Spawn Physics Joint (Owner = child bone, explicit Parent and Child keys). Child connector = identity in
  the child body frame. Parent connector = the child's initial local transform (RigPhysicsSolver.cpp:893-911), so
  twist = the child bone's local X. `ExtraChildOffset` / `ExtraParentOffset` (same rotation R on both) re-orient the
  joint frame [unverified]. The design avoids needing that: SLERP plus free or isotropic limits.
* Joint records scan **all** joint components and keep those whose resolved child and parent bodies are both in
  this solver (RigPhysicsSolver.cpp:242-298). Explicit keys therefore keep the Fx and Wreck joints apart.

### c. Simulation space, SpaceMotion, guards, units

* Component space for both solvers. Space TM = owning SK component world transform
  (`ExecuteContext.GetToWorldSpaceTransform()`, RigPhysicsSolver_Space.cpp:111, set from GetComponentToWorld in
  RVM/Private/RigVMCore/RigVMExecuteContext.cpp:34-45 via CR/Private/ControlRig.cpp:1140). Velocity and acceleration
  are finite differences of that TM (:167-193). Then come the VerticalMotionScale (:196-197), the teleport tests
  (:199-255) and the clamps (:258-278). World space skips all of this and only uses ExternalVelocity (:138-145).
* The SK rides on a physics-simulated root. A jittery root transform (substepping, async) becomes acceleration
  noise. The clamps in 4.2 bound it; lower InertialForces.Amount if wobble looks noisy [unverified].
* Guards: Fx teleport 2000 cm / 45 deg per update, then frame motion is zeroed with no pose change (:241-254).
  Fx evaluation-interval reset 0.25 s gives 3 frames of kinematic tracking (TrackInputCounter set at
  RigPhysicsSolver.cpp:2005-2014; bodies forced kinematic while it is > 0, :1149-1157). Wreck: no resets. A teleported or respawned ship is a new actor, so the rig re-constructs anyway.
* Units:

| Quantity | Unit | Evidence |
|---|---|---|
| Physics SpaceMotion.MaxAngularVelocity / MaxAngularAcceleration | rad/s, rad/s2 | RigPhysicsData.h:589-610; compared raw in RigPhysicsSolver_Space.cpp:263-277 |
| TeleportDetection.OrientationChangeThreshold / AngularAccelerationThreshold | deg per update, deg/s2 | RigPhysicsSolver_Space.cpp:202-211 (DegreesToRadians) |
| Drag.ExternalAngularVelocity | deg/s | RigPhysicsSolver_Space.cpp:143, 281 |
| Joint AngularLimit; cone/twist limits | deg | RigPhysicsJointExecution.cpp:216-294; ImmediatePhysicsAdapters.cpp:344-345 |
| AngularStrength / LinearStrength / SoftStrength | Hz (omega = 2 pi f) | PhysicsControlHelpers.h:58-68 |
| MathQuaternionFromAxisAndAngle.Angle | rad | BW notes_cr_core section 4 |
| Dynamics SpaceMotion clamps | deg/s, deg/s2 | BW notes_cr_plugins section 1 |
| Distances, velocities | cm, cm/s | |

* Deflection rule of thumb: theta ~= a / (r * (2 pi f)^2) for a point mass at lever r. A thruster with r 120 cm and
  f 3 Hz at a = 1 g gives 1.3 deg, about 1.7 deg peak with zeta 0.35. Big inertia (the fan disc) cuts it a lot, so
  use real shapes.

### d. Feeding the rig from the anim instance

* Burrower path (verified): AnimGraph Control Rig node -> Output Pose, rig variables exposed with "Use Pin", Get
  nodes wired. The flag `CustomPinProperties[i].bShowPin` has no CPF_Edit (CRDev/Private/AnimGraphNode_ControlRig.cpp:136-140),
  so only the Details checkbox writes it. BW bw_05b drove it with SlateInspector Click/Type, one inbox call per
  action. That is 32 ticks here, and they are lost if the rig asset is recreated.
* Not alternatives:
  * `InputMapping` / `OutputMapping` are `UPROPERTY()` with no Edit, and they map anim **curves** to rig variables
    (CR/Public/AnimNode_ControlRig.h:115-119; AnimNode_ControlRig.cpp:255, 264).
  * `PropagateInputProperties` copies only the exposed pins (SourcePropertyNames / DestPropertyNames,
    AnimNode_ControlRig.cpp:502-528).
  * `UAnimNodeControlRigLibrary` can convert a node reference and set the class, but cannot return the rig instance
    (CR/Public/AnimNode_ControlRig_Library.h:29-43).
  * `UControlRigComponent` runs a rig without the AnimBP and has SetBoneTransform / SetControl* but no variable
    setters (CR/Public/ControlRigComponent.h:236-604). It would also replace the verified AnimBP path.
* **Recommended: C++ direct write.** Source-checked, not yet run.
  * Order: `NativeThreadSafeUpdateAnimation` runs before the graph's node update
    (ENG/Private/Animation/AnimInstanceProxy.cpp:1350 then :1395), and the rig executes later in Evaluate
    (CR/Private/AnimNode_ControlRigBase.cpp:172-201).
  * `FAnimNode_ControlRig::GetControlRig()` is public inline (AnimNode_ControlRig.h:30).
  * `StaticStruct()` is inline over the exported `Z_Construct_UScriptStruct_FAnimNode_ControlRig`
    (`Plugins/Animation/ControlRig/Intermediate/Build/Linux/UnrealGame/Inc/ControlRig/UHT/AnimNode_ControlRig.generated.h:22-26`),
    so it links.
  * `SetPublicVariableValue<T>` is an unchecked typed write to public variables (RVM/Public/RigVMHost.h:162, 191-199;
    RigVMExternalVariable.h:593-597). The C++ type must match exactly: float, not double. Check
    `GetVariableType(Name)` once (RigVMHost.h:170).

```cpp
// Aura.Build.cs: PrivateDependencyModuleNames.AddRange(new[] { "ControlRig", "RigVM" });
#include "AnimNode_ControlRig.h"
#include "Animation/AnimClassInterface.h"

UControlRig* UAirshipAnimInstance::FindRig()   // call from NativeThreadSafeUpdateAnimation
{
    if (const IAnimClassInterface* AC = IAnimClassInterface::GetFromClass(GetClass()))  // AnimClassInterface.h:283
        for (const FStructProperty* P : AC->GetAnimNodeProperties())                    // :188
            if (P && P->Struct && P->Struct->IsChildOf(FAnimNode_ControlRig::StaticStruct()))
                return P->ContainerPtrToValuePtr<FAnimNode_ControlRig>(this)->GetControlRig();
    return nullptr;
}
// then, every update (names as static const FName):
// if (UControlRig* CR = FindRig()) { CR->SetPublicVariableValue<float>(N_ThrusterPitchDeg_FL, PitchFL); ...
//                                    CR->SetPublicVariableValue<bool>(N_bIsDead, bDead); }
```

* Keep the AnimBP minimal: parent UAirshipAnimInstance, Control Rig node (asset reference set with
  ToolsetLibrary.set_object_properties as in bw_05), Alpha 1, LOD threshold -1, bTransferInputPose on, multi-threaded
  update on. No pins.
* The node feeds the ref pose each frame (Source unlinked), so control rotations never accumulate.
* If the C++ write fails in PIE (variables don't move the bones), fall back to bw_05 + bw_05b.

### e. Physics asset

* The rig does not need one. Explicit Spawn Physics Body shapes. Instantiate From PA also drops tapered capsules and
  level sets (BW row 9).
* Damage can use the actor's convex-hull static mesh root, which is already the collision body.
* Give SK_Airship a small PA_Airship anyway, built like bw_03:
  * one simple body per Hull and Wreck part, every body PhysType Kinematic
  * SK collision QueryOnly (or NoCollision if part hits are not wanted)
  * never call SetSimulatePhysics on the SK
* Reason: with a PA the SK bounds follow the bones (`PhysicsAsset->CalcAABB`, SkinnedMeshComponent.cpp:2269-2277).
  Without one they are the fixed mesh bounds (:2284-2291), and debris that falls away gets culled with the hull.
  The PA also gives per-part hit queries on machines that refresh bones. On a server that doesn't render, the bones
  only update with `VisibilityBasedAnimTickOption = AlwaysTickPoseAndRefreshBones` (BW cpp_notes bRefreshBonesOnServer).
* The rig's world collision always skips the owning actor's components, so the SK's own PA bodies and the hull mesh
  are never gathered (CRP/Private/RigPhysicsSolver_WorldObjects.cpp:243; owner registered at
  AnimNode_ControlRigBase.cpp:73).

### f. 5.8 gotchas from the Burrower that apply here

1. Create a **legacy UControlRigBlueprint**: `unreal.ControlRigBlueprintFactory.create_new_control_rig_asset(path,
   False)`, then `get_hierarchy_controller().import_bones_from_skeletal_mesh(skm, '', True, True, False, False, False)`
   and `set_preview_mesh`. The content browser default is UControlRigRuntimeAsset (BW notes_cr_core section 1).
2. A new rig has no events: add PrepareForExecution and BeginExecution. Duplicates raise.
3. Template math: `add_unit_node_from_struct_path` resolved **MathFloatSin/Cos to MathDouble*** in this build. The
   fix is unresolve + resolve to 'float' (bw_cr_helpers.py:612-635; 04_cr.out lines 112-184). Mul, Sub, Rad and
   BoolToFloat stayed float. Run verify_struct on everything, especially the new templates here (MathVectorScale,
   MathVectorFromFloat).
4. Renamed or deprecated: MathQuat* is MathQuaternion*. MathTransformMake and MathVectorMake are deprecated 5.7
   (RigVMFunction_MathVector.h:95). Physics: use Spawn / Step ...1 (7a). Dynamics: SpawnDynamicsSolver1 and
   ImportDynamicsColliders...1.
5. RigVM errors raise RuntimeError. `set_pin_default_value` returns False also when the value is unchanged (BW
   helpers setp). Bools are `True`/`False`. Int pins reject `8.0`. Enums use short names. Arrays need
   `resize_arrays=True`. Object pins need the asset loaded first (only relevant if a PA pin is ever used).
6. Variable types: `'float'` (FFloatProperty) and `'bool'`; `'/Script/CoreUObject.Transform'`, not 'FTransform'.
   `add_member_variable` compiles on every call and returns a suffixed name on a clash.
7. Linking into **input sub-pins** works (Rotor_M1.A.Rotation, 04_cr.out:187). Used here for
   OffsetTransform.Rotation/Translation and Scale.X/Y/Z.
8. Physics defaults that bite: empty-bone default keys; bAutomaticallyAddPhysicsBodyComponents True; MassOverride
   1 kg only applies to a shape with mass; damping 0; EvaluationIntervalThresholdForReset 0; drawing only when
   Alpha > 0 and `ControlRig.Physics.AllowVisualization` (BW rows 3, 22, 25; RigPhysicsSolverExecution.cpp:302-309). In the rig
   editor preview the Wreck shows nothing unless bIsDead defaults to True.
9. Do not rename or reparent `root` / `Hull` while the rig preview simulates: check(solver key) assert
   (CRP/Private/RigPhysicsSolverComponent.cpp:73).
10. Compile = `recompile_vm()` + `compile_blueprint()` + `status` check. Save by explicit path, never during PIE.
    Quitting with the ABP editor open crashed UE: `close_all_editors_for_asset` first.
11. A reuse vs recreate decision protects AnimBP references (bw_04 MODE). With the C++ feed there are no pin ticks
    to lose.
12. World collision with ISM tiles: per-instance and WorldStatic, so tiles are found (BW row 7). The Burrower corpse
    still fell through tiles after death (open issue, memory note). The first dead frame has no ground (objects
    are gathered after the step). Geometry-collection tiles (WorldDynamic) are not hit with `Static`.
13. New for this rig: the SLERP + Locked rule (4.2). Add Force World and Component both mean world (5.4). Joint
    disable can be undone (7a). Second bodies get `_2` names (4). Default teleport threshold 100 cm per update
    kills a fast flyer's inertia (4.2).
14. LOD: the anim node re-runs Construction when the required-bone serial changes (LOD switch), which re-creates
    the physics components (AnimNode_ControlRigBase.cpp:439-447). Use one LOD for SK_Airship, or LODs that keep
    every bone, and check for a pop [unverified].

---

## 8. Still unverified

* Nothing here ran in an editor or PIE. The pieces the Burrower proved are marked as such. New and unproven:
  * Component-space solver **with** Static world collision (source: world objects are converted to sim space each
    frame, RigPhysicsSolver_WorldObjects.cpp:85-100)
  * debris momentum via inertial forces
  * the deck box, Disable Collision Between
  * Make Drive Data linear drive with a Limited linear joint (recoil spring)
  * Offset Transform node; MathVectorScale and SetScale sub-pin links
  * RunOnce + Add Force kick
  * two solvers sharing bones (`PhysicsBody_2` naming)
  * runtime joint setters
* The C++ rig-variable write (FindRig + SetPublicVariableValue) and its threading.
* Whether the SK on a physics root gives smooth enough component accelerations, and the best SK tick group.
* Construction re-run on LOD change for this mesh; SK URO / visibility tick settings for a 52 m ship.
* All tuning numbers (Hz, zeta, masses, limits): starting values only. Pod, fan and rudder limits depend on the
  Blender clearance work (`rig_clearance.json`, in progress), which currently reports near-zero gimbal clearance
  and fan pylon contact.
* Bone orientations and the exact bone list: axes are baked from the rest pose, so they are free, but the parenting
  rules in section 2 are required.
