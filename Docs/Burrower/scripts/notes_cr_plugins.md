# ControlRigPhysics / ControlRigDynamics / PhysicsControl audit of control_rig_recipe.md (UE 5.8)

Audit of recipe Steps 3, 4.1-4.4, 5.3, 5.5, 5.6 and 9 against the 5.8 source build at `/mnt/new_partition/5.8`.
Read-only audit (2026-11-21). No editor was run.

Source roots used in the citations below (all under `/mnt/new_partition/5.8/Engine/`):

| Tag | Path |
|---|---|
| `CRP` | `Plugins/Experimental/ControlRigPhysics/Source/ControlRigPhysics` |
| `CRD` | `Plugins/Experimental/ControlRigDynamics/Source/ControlRigDynamics` |
| `PC`  | `Plugins/Animation/PhysicsControl/Source/PhysicsControl` |
| `CR`  | `Plugins/Animation/ControlRig/Source/ControlRig` |
| `RVM` | `Plugins/Runtime/RigVM/Source` |
| `ENG` | `Source/Runtime/Engine` |

Binary check: `Plugins/Experimental/ControlRigPhysics/Binaries/Linux/libUnrealEditor-ControlRigPhysics.so` and
`.../ControlRigDynamics/Binaries/Linux/libUnrealEditor-ControlRigDynamics.so` exist (built 2026-08-07, BuildId
55116800). `grep -a` finds the reflected names `RigUnit_StepPhysicsSolver1`, `bTrackVelocitiesDuringPassThrough`,
`InertialForces`, `TeleportDetection`, `RigUnit_SpawnDynamicsSolver1`, `NumConstraintSubIterations`, `ChainCurves`
etc. in them, so the binaries match this source.

## 0. Verdict in short

* All 21 struct names in the recipe exist exactly as spelled. Every one lives in a **runtime** module:
  `/Script/ControlRigPhysics.<Name>` or `/Script/ControlRigDynamics.<Name>`. There is no `...Developer` module
  for either plugin; the `...Editor` modules hold no rig units.
* The deprecated/current pairs in Step 3 are right. Three more Physics nodes are deprecated in 5.8 (table row 2).
* Every pin path the recipe sets exists with that exact name and nesting. The few wrong statements are about
  behaviour, not names: see section 1.
* No extra "register" node is needed: physics bodies join a solver at Instantiate time by key match
  (`CRP/Private/RigPhysicsSolver.cpp:84-126`), joints are found by scanning all joint components
  (`:242-298`), and Dynamics particles/colliders are appended to the solver's arrays by the spawn nodes
  themselves, provided the solver already exists (`CRD/Private/RigDynamicsExecutionHelpers.cpp:156,243-246`,
  `CRD/Private/RigDynamicsColliderExecution.cpp:42-45`).

## 1. Corrections table: recipe -> 5.8 actual

| # | Recipe (step) | 5.8 actual | Source (file:line) |
|---|---|---|---|
| 1 | Step 1/9: ControlRigPhysics' .uplugin "not staged", "treat it as experimental" | `IsBetaVersion: true`, `IsExperimentalVersion: false`, `EnabledByDefault: true`; depends on `ControlRig` + `PhysicsControl`. ControlRigDynamics: `IsExperimentalVersion: true`, same two deps. The clone's `Aura.uproject` already has both `"Enabled": true` | `Plugins/Experimental/ControlRigPhysics/ControlRigPhysics.uplugin:15-28`, `.../ControlRigDynamics/ControlRigDynamics.uplugin:15-26`, `_BurrowerWork/Aura.uproject` |
| 2 | Step 3 deprecated table (4 pairs + TrackInputPose) | Also deprecated 5.8: `RigUnit_SetPhysicsSolverSimulationSpaceSettings`, `RigUnit_GetPhysicsSolverSimulationSpaceSettings`. Their replacements are `RigUnit_SetPhysicsSolverSpaceMotion` / `RigUnit_SetPhysicsSolverTeleportDetection` (+ Get variants). The recipe uses none of the deprecated ones | `CRP/Public/RigPhysicsSolverExecution.h:260,292,322,371,395` |
| 3 | Step 3: "All Dynamics nodes default their solver key to bone Root" | True for Dynamics. **Physics** nodes default to an **empty** bone name (`ElementKey.Name = None`, Name `PhysicsSolver`/`PhysicsBody`), an invalid key, so the key must always be set (recipe does). Only `RigUnit_GetPhysicsSolverExists` defaults to `Root`. FName compare ignores case, so `Root` would match `root` anyway | `CRP/Public/RigPhysicsSolverExecution.h:121-122,140-141,205-206`; `CRP/Public/RigPhysicsBodyExecution.h:353-354`; `CRD/Public/RigDynamicsSolverExecution.h:76,158-159` |
| 4 | C1 RagdollSolver `TeleportDetection.PositionChangeThreshold 500` (and `SpaceMotion` "not used") | In **World** simulation space the solver returns before teleport detection and all SpaceMotion conditioning; only `SpaceMotion.Drag.ExternalLinear/AngularVelocity` are read. The 500 has no effect (harmless) | `CRP/Private/RigPhysicsSolver_Space.cpp:139-145` |
| 5 | C1 why World: "once dead ... the body should keep its world momentum" | Not what happens. During Alpha-0 tracking the dynamic bodies are snapped to the input pose each frame with the **component-space** bone velocity, rotated into world. The actor's own world velocity is never added. At death the corpse starts with the wave motion only (the actor stops anyway). If flight momentum is wanted, queue `Add Force` with `Type = VelocityChange`, `Linear = actor velocity` on the first dead frame (needs a rig variable from C++) | `CRP/Private/RigPhysicsSolver.cpp:1096-1131,2025-2045`, `CRP/Private/RigPhysicsSolver_Space.inl:63-74` |
| 6 | C1: `bWorldCollisionIncludeQuery False` "excludes the Burrower's own QueryOnly mesh bodies and RotorBox"; Step 7: "otherwise the rig's world collision gathers the Burrower's own capsule" | Components owned by the rig's owning actor are **always skipped**. The AnimBP Control Rig node registers the owning mesh component, so the owner is known. Keep the capsule NoCollision on death for the other reasons, not this one | `CRP/Private/RigPhysicsSolver_WorldObjects.cpp:243`; `CR/Private/AnimNode_ControlRigBase.cpp:73`; `CR/Private/ControlRig.cpp:3937-3956` |
| 7 | Step 9 "World collision unknowns" (ISM instances? owner excluded?) | Resolved. ISM overlaps are taken **per instance** (`Overlap.ItemIndex`, per-instance body). `Static` = object type `ECC_WorldStatic` (plus custom channels flagged static); the hex tiles are WorldStatic (hex_api.md:106-108), so they are found. Only bodies whose collision has physics are added when `bWorldCollisionIncludePhysics`. The overlap box is built from **non-kinematic** bodies only, and the step returns early at Alpha 0, so nothing is gathered while alive. Objects are gathered **after** each step, so the first dead frame has no ground (one frame) | `CRP/Private/RigPhysicsSolver_WorldObjects.cpp:24-31,132-149,173-183,226-255`; `CRP/Private/RigPhysicsSolver.cpp:2023-2059,2130,2157`; `ENG/Public/CollisionQueryParams.h:362` |
| 8 | C2 `PhysicsAsset` "if the text default is refused, pick it in the details panel" | It is a `TObjectPtr<UPhysicsAsset>` input pin and **does** take the object path as text, but RigVM only finds it if the asset is **already loaded** (FindPackage + FindObject, no load). Call `unreal.load_asset('/Game/Assets/Enemies/Burrower/PA_Burrower')` first, then set `'/Game/Assets/Enemies/Burrower/PA_Burrower.PA_Burrower'`. `''` or `None` clears it | `CRP/Public/RigPhysicsExecution.h:197-198`; `RVM/RigVM/Private/RigVMTypeUtils.cpp:553-595`; `RVM/RigVMDeveloper/Private/RigVMModel/RigVMPin.cpp:1234-1262`; `.../RigVMController.cpp:10331,10438-10441` |
| 9 | C2 "copies box, sphere, sphyl and convex shapes" | Correct, and **only** those: tapered capsules and level sets in the asset are dropped. A body made only of a tapered capsule gets no shape, so its computed mass is 0 and `MassOverride` is then ignored (it only rescales a positive computed mass), which gives a zero-mass dynamic body. PA_Burrower must use plain capsules (Sphyl) | `CRP/Private/RigPhysicsExecution.cpp:304-331`; `CRP/Private/RigPhysicsSolver.cpp:597-614` |
| 10 | C2 `bMakeHelperBodies False` | Correct; note its default is **True**, so this pin must be set | `CRP/Public/RigPhysicsExecution.h:234-235` |
| 11 | C3 movement type in the Construction Event | Allowed: `Set Physics Body Movement Mode` has no event check. The value is also re-applied to the Chaos actor **every step**, so the Step 9 fallback (switching it in Forwards Solve) works too. `Static` behaves like `Kinematic` here (anything not Simulated is kinematic) | `CRP/Private/RigPhysicsBodyExecution.cpp:242-253`; `CRP/Private/RigPhysicsSolver.cpp:1160`; `PC/Private/RigidBodyWithControl.cpp:143-149` |
| 12 | 4.1 fallback: `Calculate Physics Collision` `MinSize` "for capsules is the minimum radius" | The header says radius but the code does `Radius = 0.5 * max(MinSize, Length * MinAspectRatio)`, so MinSize acts as a minimum **diameter**: pass twice the radius. Also J1_Forequarters has 9 children (J2 + 8 pipe roots), so its auto shape is a **box** around them, and the leaf J4_Tail gets a shape built from its parent offset in its own frame, not along the tail. The fallback is rough; prefer the PA | `CRP/Public/RigPhysicsBodyExecution.h:94-102`; `CRP/Private/RigPhysicsBodyComponent.cpp:118,134-164,166-185,186-202` |
| 13 | C6 "leave Collision empty, the node auto-calculates a capsule from the bone to its child" | Correct for the hose bones: each has exactly one child (rig_info: 71 bones = 7 body/rotor + 64 chain bones, no extra children). With the defaults (MinAspectRatio 0.25, MinSize 0) the capsule runs from the bone to its child: radius = segment/8, core = 0.75 x segment (about r 3.6-4.1 cm for 29-33 cm segments) | `CRP/Private/RigPhysicsBodyExecution.cpp:46-49`; `CRP/Private/RigPhysicsBodyComponent.cpp:166-185`; `SourceArt/Burrower/Burrower_rig_info.json` |
| 14 | C6 optional `Set Physics Body Update Kinematic From Simulation` True on `_end` "so the kinematic anchor is written back after its simulated parent moves it" | Redundant, and the reason is wrong. `FPhysicsControlModifierData.bUpdateKinematicFromSimulation` already defaults to **true** (constructor), a kinematic body is never moved by its joints, and every body with a target bone is written back after the step anyway. Drop it | `PC/Public/PhysicsControlData.h:243-260,296-297`; `CRP/Private/RigPhysicsSolver.cpp:578-585,1898-1955` |
| 15 | C9 "pin both ends" (12 nodes) | Only the 6 `_end` nodes do anything. The root-most particle of each chain (no ancestor particle) is forced Kinematic at instantiate, so the `_01` nodes are redundant (harmless) | `CRD/Private/RigDynamicsSolver.cpp:293-307` |
| 16 | 4.3/9: Dynamics movement type treated like Physics | A Dynamics particle's MovementType is read **only at Instantiate**; changing it later (e.g. in Forwards Solve) has no effect in 5.8. It must stay in Construction, before `Instantiate dynamics` (the recipe already does this). Physics bodies differ (row 11) | `CRD/Private/RigDynamicsSolver.cpp:248-257`; `CRD/Public/RigParticleSimulation.h:608-627` |
| 17 | 4.4 "otherwise ... for the ragdoll, possibly the death frame"; "if one of them warns in the Construction Event, delete it" | With `bTrackVelocitiesDuringPassThrough = true` the first Alpha-0 frame already instantiates, so allocation happens on the first alive frame, not at death. Neither Instantiate node checks the event, so neither warns in Construction | `CRP/Private/RigPhysicsSolver.cpp:2025-2035`; `CRP/Private/RigPhysicsSolverExecution.cpp:147-166`; `CRD/Private/RigDynamicsSolverExecution.cpp:205-225`; `CRD/Private/RigDynamicsSolver.cpp:1205-1219` |
| 18 | 5.3 optional death kick with `Add Force` "on the first dead frame" | Forces queued on a frame where the step has Alpha <= 0 are **discarded**. The node must run on a frame with Alpha > 0 and before `StepRagdoll`. With `ForceAndTorqueSpace = World` the vector is world space (converted through the component transform) | `CRP/Private/RigPhysicsSolver.cpp:2055-2057,1251-1318` |
| 19 | 5.3 `WorldCollisionType` "has no runtime setter ...; it is fixed at construction" | No node sets it (true), but the solver reads `SolverSettings` from the component every step, so it is not frozen in the solver; it just cannot be reached from the graph | `CRP/Private/RigPhysicsSolver.cpp:2075-2130`; `CRP/Public/RigPhysicsSolverExecution.h` (no setter) |
| 20 | 5.6 "a negative DeltaTimeOverride freezes the solver" | No stepping, but the read-back still writes the bones every frame (pipes hold their last pose in sim space). Also true for Physics | `CRD/Private/RigDynamicsSolver.cpp:1185-1188,1331-1337`; `CRP/Private/RigPhysicsSolver.cpp:1984-1987,2138-2150` |
| 21 | Step 9 "Events" bullet | Construction-only (errors "... can only be used during Setup"): Spawn Physics Solver/Body/Joint/Components, Instantiate From Physics Asset, Import Collision From Physics Asset, Calculate Physics Collision, Set Physics Body Solver Settings / Dynamics Properties / Collision Properties / Target Bone / Material, Disable Collision Between, all Dynamics Spawn nodes, Import Dynamics Colliders, Set Dynamics Collider Shapes. **No** check (run in any event): Set Physics Body Source Bone, Movement Mode, Collision Mode, Damping, Gravity Multiplier, Blend Weight, Update Kinematic From Simulation, Add Force, Instantiate*, Step*, all Dynamics Set-particle nodes | `CRP/Private/RigPhysicsBodyExecution.cpp:26,74,93,113,132,151,164-175,185,305`; `CRP/Private/RigPhysicsJointExecution.cpp:30`; `CRP/Private/RigPhysicsExecution.cpp:29,178,579`; `CRD/Private/*Execution*.cpp` |
| 22 | Step 9 "Defaults that bite" (additions) | `FRigPhysicsDynamics.MassOverride` default **1 kg** (every Spawn Physics Body is 1 kg unless set). `Set Physics Body Damping` pins default 0/0. Physics `EvaluationIntervalThresholdForReset` default **0** (if `bResetFromEvaluationInterval` is ticked with no threshold, any frame-time jitter above dt+0.01 s resets; Dynamics default is 0.1). `Make Articulation Joint Data` `AngularLimit` default (-1,-1,-1) = free. Physics `VelocityIterations` default 4 | `CRP/Public/RigPhysicsData.h:726,835,854`; `CRP/Public/RigPhysicsBodyExecution.h:547-552`; `CRP/Public/RigPhysicsJointExecution.h:308-309`; `CRD/Public/RigDynamicsData.h:211` |
| 23 | Open question 4 (PhysicsControl types "[unverified]") | Verified: `EPhysicsMovementType` = `Static, Kinematic, Simulated, Default`; `EAngularDriveMode` = `SLERP, TwistAndSwing`; `ECollisionEnabled` = `NoCollision, QueryOnly, PhysicsOnly, QueryAndPhysics, ProbeOnly, QueryAndProbe`; `FPhysicsControlModifierData` defaults: MovementType Simulated, CollisionType QueryAndPhysics, KinematicTargetSpace OffsetInBoneSpace, GravityMultiplier 1, PhysicsBlendWeight 1, bUpdateKinematicFromSimulation true, bEnableCCD false | `PC/Public/PhysicsControlData.h:19-32,240-303`; `ENG/Classes/PhysicsEngine/ConstraintDrives.h:9-19`; `ENG/Classes/Engine/EngineTypes.h:1804-1826` |
| 24 | Step 3 "Text formats" | Confirmed with two strictness rules: bool sub-pins accept exactly `True`/`False` (Python `str(True)` is fine), and **int32 pins reject `8.0`** (pass Python ints; the recipe does). Enums take the short value name for both `enum class` and namespaced `TEnumAsByte` enums (`World`, `NoCollision`, `SLERP`, `Kinematic`). Validation is on by default | `RVM/RigVMDeveloper/Private/RigVMModel/RigVMPin.cpp:1300-1341`; `.../RigVMController.cpp:97,122,10329-10334` |
| 25 | C1 `MaxDepenetrationVelocity` "default 0" | Correct; 0 = no clamp (instant push-out), so 300 is a real limit | `CRP/Public/RigPhysicsData.h:760`; `ENG/Private/PhysicsEngine/ImmediatePhysics/ImmediatePhysicsChaos/ImmediatePhysicsSimulation_Chaos.cpp:820-822`; `Source/Runtime/Experimental/Chaos/Private/Chaos/Collision/PBDCollisionContainerSolver.cpp:285` |

Confirmed as written in the recipe (no change needed): all struct paths; FRigComponentKey text
`(ElementKey=(Type=Bone,Name="x"),Name="Comp")` (members `ElementKey`, `Name`; no custom ImportText,
`CR/Public/Rigs/RigHierarchyDefines.h:1770-1774,1927-1931`); default component names `PhysicsSolver`,
`PhysicsBody`, `PhysicsJoint`, `DynamicsSolver`, `DynamicsParticle`, `DynamicsCollider`; Physics clamps in rad/s and
rad/s^2 (`CRP/Private/RigPhysicsSolver_Space.cpp:266,276`; header `RigPhysicsData.h:589-610`), Dynamics clamps in deg/s
and deg/s^2 (`CRD/Private/RigDynamicsSimulationSpace.cpp:232-242`; `RigDynamicsData.h:327-355`);
`Spawn Dynamics Chains` sets `ParticleProperties.GravityMultiplier = 0` in its constructor
(`CRD/Public/RigDynamicsExecutionHelpers.h:148-151`) and follows all descendants of each root
(`CRD/Private/RigDynamicsExecutionHelpers.cpp:169-182`); Instantiate From Physics Asset maps only
`PhysType_Simulated` to Simulated (Default -> Kinematic), CollisionResponse Enabled -> `PhysicsOnly` else
`NoCollision`, names bodies `PhysicsBody` and joints `PhysicsJoint` (`CRP/Private/RigPhysicsExecution.cpp:352-357,369-370,551-552`);
`FRigPhysicsDriveData.bUseSkeletalAnimation` defaults to true (`CRP/Public/RigPhysicsData.h:917`) and Make
Articulation Drive Data leaves it true; Instantiate From PA sets it **false** when `bEnableDrives` is on
(`RigPhysicsExecution.cpp:542-548`); SourceBone/TargetBone default to the owning bone
(`RigPhysicsSolver.cpp:795-799,816-820,1037-1041`); damping re-read every step
(`RigPhysicsSolver.cpp:1240-1246`); effective blend = Alpha x PhysicsBlendWeight (`:1935`); construction event name
`Construction` (`CR/Public/Units/Execution/RigUnit_PrepareForExecution.h:29`); Make Articulation Joint Data leaves the
linear constraint at its default, which is locked on X/Y/Z (`ENG/Private/PhysicsEngine/ConstraintTypes.cpp:43-52`);
Dynamics capsule main axis +Z, `Length` = core (`CRD/Public/RigDynamicsData.h:59-69`); Dynamics colliders follow the
hierarchy pose at step time (`CRD/Private/RigDynamicsSolver.cpp:712-726`).

## 2. Per-node pin reference (only the pins the recipe uses)

Common facts:
* "Mutable" = derives from `FRigUnit_PhysicsBaseMutable` / `FRigUnit_DynamicsBaseMutable` -> `FRigUnitMutable`, which
  has one IO execute pin named **`ExecutePin`** (display "Execute") (`CR/Public/Units/RigUnit.h:121-122`). The
  recipe's `exec_pin()` finds it with `URigVMPin.is_execute_context()` (`RVM/RigVMDeveloper/Public/RigVMModel/RigVMPin.h:301-302`).
  The events' output pin is also `ExecutePin` (`CR/Public/Units/Execution/RigUnit_BeginExecution.h:26-27`).
* "Pure" = derives from `FRigUnit_PhysicsBase` / `FRigUnit_DynamicsBase` -> `FRigUnit`: no execute pin.
* "Construction only" = the Execute body returns with `UE_CONTROLRIG_RIGUNIT_REPORT_ERROR("... can only be used during
  Setup")` when `GetEventName() != "Construction"`. It logs, never asserts.
* Pin paths are `<NodeName>.<Pin>[.<SubPin>...]`. A `DisplayName` (e.g. "Bone Mask", "Auto Find Solver",
  "Solver Component Key") changes only the label, never the pin name.
* Component keys: `K(b,c) = (ElementKey=(Type=Bone,Name="b"),Name="c")`; bone keys `(Type=Bone,Name="b")`;
  key arrays `((Type=Bone,Name="a"),(Type=Bone,Name="b"))`.

### 2.1 ControlRigPhysics

**RigUnit_SpawnPhysicsSolver** - `/Script/ControlRigPhysics.RigUnit_SpawnPhysicsSolver` - current (replaces deprecated
`RigUnit_AddPhysicsSolver`) - mutable - Construction only (`CRP/Private/RigPhysicsSolverExecution.cpp:103-133`, check at
:110). Header `CRP/Public/RigPhysicsSolverExecution.h:69-108`. Creates component named **`PhysicsSolver`** on Owner
(hard-coded, no name pin, :120-121); a clash would get a unique suffix.

| Pin path | Type | Default | Recipe |
|---|---|---|---|
| `Owner` | FRigElementKey | Type Bone, Name None | `(Type=Bone,Name="root")` / `J1_Forequarters` |
| `SolverSettings.bAutomaticallyAddPhysicsBodyComponents` | bool | True | False |
| `SolverSettings.SimulationSpace` | ERigPhysicsSimulationSpace `World / Component / SpaceBone` | Component | World (ragdoll), Component (hoses) |
| `SolverSettings.CollisionSpace` | same enum | Component | World / Component |
| `SolverSettings.WorldCollisionType` | ERigPhysicsWorldCollisionType `None / Static / Dynamic / All` | None | Static / None |
| `SolverSettings.bWorldCollisionIncludePhysics` | bool | True | (default) |
| `SolverSettings.bWorldCollisionIncludeQuery` | bool | False | (default) |
| `SolverSettings.WorldCollisionBoundsExpansion` | float | 1.1 | (default) |
| `SolverSettings.PositionIterations` | int32 | 8 | 8 / 12 |
| `SolverSettings.VelocityIterations` | int32 | 4 | 2 / 1 |
| `SolverSettings.ProjectionIterations` | int32 | 1 | (default) |
| `SolverSettings.FixedTimeStep` | float | 0.02 | 0.0 |
| `SolverSettings.MaxDeltaTime` | float | 1.0 | 0.0334 |
| `SolverSettings.MaxTimeSteps` | int32 | 10 | 4 |
| `SolverSettings.MaxDepenetrationVelocity` | float | 0 (no clamp) | 300 (ragdoll) |
| `SolverSettings.Gravity` | FVector | (0,0,-981) | (default) |
| `SolverSettings.bResetFromEvaluationInterval` | bool | False | True (hoses) |
| `SolverSettings.EvaluationIntervalThresholdForReset` | float (s) | 0.0 | 0.25 |
| `SolverSettings.Collision` | FRigPhysicsCollision | empty | test ground box only (Step 8.4) |
| `TeleportDetection.PositionChangeThreshold` | float (cm per update) | 100 | 500 (no effect in World space, row 4) |
| `TeleportDetection.OrientationChangeThreshold` | float (deg per update) | 30 | 45 |
| `SpaceMotion.InertialForces.Amount` | float 0..1 | 1.0 | 0.5 |
| `SpaceMotion.bClampLinearAcceleration` / `SpaceMotion.MaxLinearAcceleration` | bool / float | False / 10000 | True / 3000 |
| `SpaceMotion.bClampAngularVelocity` / `SpaceMotion.MaxAngularVelocity` | bool / float **rad/s** | False / 10000 | True / 3.0 |
| `SpaceMotion.bClampAngularAcceleration` / `SpaceMotion.MaxAngularAcceleration` | bool / float **rad/s^2** | False / 10000 | True / 20.0 |
| `SpaceMotion.Drag.LinearDragMultiplier` / `SpaceMotion.Drag.AngularDragMultiplier` | float 0..1 | 1.0 / 1.0 | 0.1 / 0.3 |
| output `PhysicsSolverComponentKey` | FRigComponentKey | | = K(owner, PhysicsSolver) |

Field lines: `CRP/Public/RigPhysicsData.h` SolverSettings 666-836, TeleportDetection 626-662, SpaceMotion 564-620,
InertialForces 476-506, Drag 513-558. The nested sub-pin paths `SpaceMotion.InertialForces.Amount` and
`SpaceMotion.Drag.LinearDragMultiplier` are the exact paths Epic's own upgrade remap uses
(`CRP/Private/RigPhysicsSolverExecution.cpp:78,88`). Note the Physics drag multipliers act through body damping
(Chaos ether drag = `Dynamics.LinearDamping/AngularDamping`, `ENG/Private/PhysicsEngine/ImmediatePhysics/ImmediatePhysicsChaos/ImmediatePhysicsActorHandle_Chaos.cpp:127-128`).

**RigUnit_HierarchyInstantiateFromPhysicsAsset** - `/Script/ControlRigPhysics.RigUnit_HierarchyInstantiateFromPhysicsAsset`
- current - mutable - Construction only (`CRP/Private/RigPhysicsExecution.cpp:171-569`, check :178; null asset logs
"needs a valid physics asset" :191-195). Header `CRP/Public/RigPhysicsExecution.h:171-260`.

| Pin path | Type | Default | Recipe |
|---|---|---|---|
| `PhysicsSolverComponentKey` | FRigComponentKey | (Bone None, PhysicsSolver) | K(root, PhysicsSolver) |
| `bUseAutomaticSolver` | bool | True | False |
| `PhysicsAsset` | TObjectPtr<UPhysicsAsset> | null | `/Game/Assets/Enemies/Burrower/PA_Burrower.PA_Burrower` (asset must be loaded first, row 8) |
| `ConstraintProfileName` | FName | None (= default profile) | (leave) |
| `BonesToUse` (label "Bone Mask") | TArray<FRigElementKey> | empty = all | J0..J4 bone keys |
| `bEnableJoints` | bool | True | True |
| `bEnableDrives` | bool | True | False |
| `bAddSimSpaceControl` / `bAddParentSpaceControl` | bool | False / False | False / False |
| `bMakeHelperBodies` | bool | **True** | False |
| outputs `PhysicsBodyComponentKeys`, `PhysicsJointComponentKeys`, `SimSpaceControlComponentKeys`, `ParentSpaceControlComponentKeys` | TArray<FRigComponentKey> | | bodies K(Jn, PhysicsBody); joints on the child bone, K(child, PhysicsJoint) |

What it copies (`RigPhysicsExecution.cpp:299-364`): Box/Sphere/Sphyl/Convex only; material friction = max(Friction,
StaticFriction), restitution, combine modes; `MassOverride = CalculateMass()`; LinearDamping, AngularDamping, COMNudge;
MovementType Simulated only for `PhysType_Simulated`; CollisionType PhysicsOnly/NoCollision; bEnableCCD = bUseCCD;
collision-disable table -> NoCollisionBodies (:440-501); joints from Frame1/Frame2 + AngularRotationOffset + the
profile's Linear/Cone/Twist limits and projection (:119-139, :504-567). Bodies on bones missing from the hierarchy are
skipped silently (:222-225).

**RigUnit_HierarchySetPhysicsBodyMovementType** ("Set Physics Body Movement Mode") -
`/Script/ControlRigPhysics.RigUnit_HierarchySetPhysicsBodyMovementType` - current - mutable - any event
(`CRP/Private/RigPhysicsBodyExecution.cpp:242-253`). Header `CRP/Public/RigPhysicsBodyExecution.h:346-367`.

| Pin | Type | Default | Recipe |
|---|---|---|---|
| `PhysicsBodyComponentKey` | FRigComponentKey | (Bone None, PhysicsBody) | K(Jn, PhysicsBody) |
| `MovementType` | EPhysicsMovementType `Static / Kinematic / Simulated / Default` | Simulated | Simulated |

**RigUnit_HierarchySetPhysicsBodyDamping** ("Set Physics Body Damping") -
`/Script/ControlRigPhysics.RigUnit_HierarchySetPhysicsBodyDamping` - current - mutable - any event
(`CRP/Private/RigPhysicsBodyExecution.cpp:360-372`). Header `CRP/Public/RigPhysicsBodyExecution.h:528-553`.
Pins: `PhysicsBodyComponentKey` (as above), `LinearDamping` float 1/s default **0**, `AngularDamping` float 1/s
default **0**. Recipe 0.1 / 1.0. Writes `Dynamics.LinearDamping/AngularDamping`; re-applied each step
(`RigPhysicsSolver.cpp:1240-1246`).

**RigUnit_AddPhysicsBody** ("Spawn Physics Body") - `/Script/ControlRigPhysics.RigUnit_AddPhysicsBody` - current -
mutable - Construction only (`CRP/Private/RigPhysicsBodyExecution.cpp:20-53`, check :26). Header
`CRP/Public/RigPhysicsBodyExecution.h:14-52`. Component name **`PhysicsBody`** (hard-coded, :36-37). Empty
`Collision` -> `AutoCalculateCollision()` with defaults (:46-49).

| Pin path | Type | Default | Recipe |
|---|---|---|---|
| `Owner` | FRigElementKey | Bone None | hose bone b |
| `Solver` (whole struct) or `Solver.PhysicsSolverComponentKey` | FRigComponentKey | (Bone None, PhysicsSolver) | K(J1_Forequarters, PhysicsSolver) |
| `Solver.bUseAutomaticSolver` (label "Auto Find Solver") | bool | True | False |
| `Solver.SourceBone` / `Solver.TargetBone` | FRigElementKey | unset = owning bone | b / b (redundant) |
| `Solver.bIncludeInChecksForReset` | bool | True | True |
| `Dynamics.MassOverride` | float kg | **1.0** | 20 (only applied if the shapes give mass > 0) |
| `Dynamics.LinearDamping` / `Dynamics.AngularDamping` | float 1/s | 0 / 0 | 0.5 / 2.0 |
| `BodyData.MovementType` | EPhysicsMovementType | Simulated | Kinematic (`_01`, `_end`) / Simulated |
| `BodyData.CollisionType` | TEnumAsByte<ECollisionEnabled::Type> | QueryAndPhysics | NoCollision |
| `Collision.Spheres` | TArray<FRigPhysicsCollisionSphere> (`TM`, `Radius`, `Name`, `RestOffset`, `bContributeToMass`) | empty | `((Radius=6.0))` on `_end` |
| output `PhysicsBodyComponentKey` | FRigComponentKey | | K(b, PhysicsBody) |

Struct lines: FRigPhysicsBodySolverSettings `CRP/Public/RigPhysicsData.h:1022-1059`, FRigPhysicsDynamics :840-897,
FRigPhysicsCollision :309-332, shapes :166-268, FPhysicsControlModifierData `PC/Public/PhysicsControlData.h:240-303`.

**RigUnit_AddPhysicsJoint** ("Spawn Physics Joint") - `/Script/ControlRigPhysics.RigUnit_AddPhysicsJoint` - current -
mutable - Construction only (`CRP/Private/RigPhysicsJointExecution.cpp:24-55`, check :30). Header
`CRP/Public/RigPhysicsJointExecution.h:15-58`. Component name **`PhysicsJoint`** (:40-41).

| Pin | Type | Default | Recipe |
|---|---|---|---|
| `Owner` | FRigElementKey | Bone None | b (child) |
| `ParentBodyComponentKey` | FRigComponentKey | (Bone None, PhysicsBody) = auto-find | K(prev, PhysicsBody) |
| `ChildBodyComponentKey` | FRigComponentKey | (Bone None, PhysicsBody) = auto-find | K(b, PhysicsBody) |
| `JointData` | FRigPhysicsJointData | bEnabled, auto offsets, linear locked, cone/twist free, bDisableCollision True | linked from HoseJointData.JointData |
| `DriveData` | FRigPhysicsDriveData | drives off, bUseSkeletalAnimation True | linked from HoseDriveData.DriveData |
| output `PhysicsJointComponentKey` | FRigComponentKey | | K(b, PhysicsJoint) |

With `bAutoCalculateParentOffset` the parent frame = the child bone's initial local transform
(`RigPhysicsSolver.cpp:904-910`), which assumes the parent body sits on the child's hierarchy parent: true for the hose
chains.

**RigUnit_MakeArticulationJointData** - `/Script/ControlRigPhysics.RigUnit_MakeArticulationJointData` - current -
**pure** - any event (`CRP/Private/RigPhysicsJointExecution.cpp:202-296`). Header `CRP/Public/RigPhysicsJointExecution.h:298-325`.
Pins: `AngularLimit` FVector deg (X twist, Y swing1, Z swing2; <0 free, 0 locked, >0 limited) default (-1,-1,-1),
recipe (12,12,12); `SoftStrength` FVector (Hz-like strength; <0 hard) default (-1,-1,-1), recipe (2,2,2);
`SoftDampingRatio` FVector default (1,1,1); output **`JointData`**. Swing1/Swing2 share one cone stiffness/damping
(the Z values win, :256-257,283-284). Linear motion stays at the locked default.

**RigUnit_MakeArticulationDriveData** - `/Script/ControlRigPhysics.RigUnit_MakeArticulationDriveData` - current -
**pure** - any event (`CRP/Private/RigPhysicsJointExecution.cpp:299-337`). Header `CRP/Public/RigPhysicsJointExecution.h:329-368`.
Pins: `bEnableAngularDrive` bool default True; `AngularDriveMode` TEnumAsByte<EAngularDriveMode::Type> `SLERP` /
`TwistAndSwing`, default SLERP (SLERP fails only if an angular axis is Locked; the hose limits are Limited);
`AngularStrength` float default 10 (recipe 6); `AngularDampingRatio` default 1 (recipe 0.8); `AngularExtraDamping`
default 0; `SkeletalAnimationVelocityMultiplier` default 1; output **`DriveData`** (bUseSkeletalAnimation stays True,
acceleration mode on).

**RigUnit_InstantiatePhysics** ("Instantiate physics") - `/Script/ControlRigPhysics.RigUnit_InstantiatePhysics` -
current - mutable - any event (no check, `CRP/Private/RigPhysicsSolverExecution.cpp:147-166`). Header
`CRP/Public/RigPhysicsSolverExecution.h:133-150`. Pin: `PhysicsSolverComponentKey` (default Bone None, PhysicsSolver).
Early-outs after the first call (`RigPhysicsSolver.cpp:687-690`).

**RigUnit_StepPhysicsSolver1** ("Step Physics Solver") - `/Script/ControlRigPhysics.RigUnit_StepPhysicsSolver1` -
current (deprecated twin `RigUnit_StepPhysicsSolver`) - mutable - any event (meant for Forwards Solve)
(`CRP/Private/RigPhysicsSolverExecution.cpp:266-313`). Header `CRP/Public/RigPhysicsSolverExecution.h:198-251`.

| Pin | Type | Default | Recipe |
|---|---|---|---|
| `PhysicsSolverComponentKey` | FRigComponentKey | (Bone None, PhysicsSolver) | RAGDOLL / HOSE_SOLVER |
| `DeltaTimeOverride` | float | 0 (>0 override, <0 no step) | 0 |
| `SimulationSpaceDeltaTimeOverride` | float | 0 | 0 |
| `Alpha` | float 0..1 | 1 | `DeadAlpha` link / 1 |
| `bTrackVelocitiesDuringPassThrough` | bool | True | True |
| `VisualizationSettings.bShowBodies` / `bShowCentreOfMass` / `bShowJoints` / `bShowControls` / `bShowWorldObjects` / `bShowWorldOverlapBox` / `bShowActiveContacts` / `bShowInactiveContacts` | bool (FRigPhysicsVisualizationSettings1) | all False | debug only |

Drawing happens only when Alpha > 0 and CVar `ControlRig.Physics.AllowVisualization` != 0 (:302-309; CVar :16-25).
CVar `ControlRig.Physics.EnableStepSolver 0` disables all physics stepping (:27-29, :275-278).

**RigUnit_HierarchyAddPhysicsBodyForce** ("Add Force") - `/Script/ControlRigPhysics.RigUnit_HierarchyAddPhysicsBodyForce`
- current - mutable - any event (`CRP/Private/RigPhysicsBodyExecution.cpp:375-386`). Header
`CRP/Public/RigPhysicsBodyExecution.h:585-611`. Pins: `PhysicsBodyComponentKey`; `ForceAndTorque.Type`
EPhysicsControlForceType `Force / Acceleration / Impulse / VelocityChange` (default Force);
`ForceAndTorque.ForceAndTorqueSpace` EPhysicsControlSpace `World / Component / Body` (default World);
`ForceAndTorque.LocationSpace` (default Body); `ForceAndTorque.Linear`, `ForceAndTorque.Angular`,
`ForceAndTorque.Location` FVector; `Name` FName. Struct `PC/Public/PhysicsControlData.h:1061-1097`. Applied at the next
step with Alpha > 0, then cleared; dropped if the next step is a pass-through (row 18).

**RigUnit_HierarchySetPhysicsBodyUpdateKinematicFromSimulation** ("Set Physics Body Update Kinematic From Simulation")
- `/Script/ControlRigPhysics.RigUnit_HierarchySetPhysicsBodyUpdateKinematicFromSimulation` - current - mutable - any
event (`CRP/Private/RigPhysicsBodyExecution.cpp:346-357`). Header `CRP/Public/RigPhysicsBodyExecution.h:499-522`. Pins
`PhysicsBodyComponentKey`, `bUpdateKinematicFromSimulation` (default True). Not needed (row 14).

**RigUnit_HierarchyAutoCalculateCollision** ("Calculate Physics Collision", fallback only) -
`/Script/ControlRigPhysics.RigUnit_HierarchyAutoCalculateCollision` - mutable - Construction only
(`CRP/Private/RigPhysicsBodyExecution.cpp:67-83`). Pins `PhysicsBodyComponentKey`, `MinAspectRatio` (0.25), `MinSize`
(0; acts as minimum diameter for capsules, row 12).

**RigUnit_GetPhysicsSolverSpaceData** (Step 3 list) - `/Script/ControlRigPhysics.RigUnit_GetPhysicsSolverSpaceData` -
pure. Pin `PhysicsSolverComponentKey`; outputs `LinearVelocity`, `AngularVelocity` (rad/s), `LinearAcceleration`,
`AngularAcceleration`, `Gravity` (`CRP/Public/RigPhysicsSolverExecution.h:499-536`).

### 2.2 ControlRigDynamics

**RigUnit_SpawnDynamicsSolver1** ("Spawn Dynamics Solver") - `/Script/ControlRigDynamics.RigUnit_SpawnDynamicsSolver1` -
current (deprecated twin `RigUnit_SpawnDynamicsSolver`) - mutable - Construction only
(`CRD/Private/RigDynamicsSolverExecution.cpp:163-192`, check :169). Header `CRD/Public/RigDynamicsSolverExecution.h:66-104`.

| Pin path | Type | Default | Recipe |
|---|---|---|---|
| `Owner` | FRigElementKey | (Bone, "Root") | root |
| `SolverComponentName` | FName | DynamicsSolver | DynamicsSolver |
| `Settings.SimulationSpace` | ERigDynamicsSimulationSpace `World / Component / SpaceBone` | Component | Component |
| `Settings.Gravity` | FVector (world) | (0,0,-981) | (default) |
| `Settings.MaxTimeStep` | float s | 1.0 | 0.0167 |
| `Settings.MaxNumSteps` | int32 | 4 | 4 |
| `Settings.NumIterations` | int32 | 1 | 1 |
| `Settings.NumConstraintSubIterations` | int32 | 1 | 4 |
| `Settings.bReadBoneOrientations` / `Settings.bReadBonePositions` | bool | True / False | (defaults) |
| `Settings.bResetFromPosition` / `Settings.PositionThresholdForReset` | bool / float cm | False / 10000 | True / 2000 |
| `Settings.bResetFromEvaluationInterval` / `Settings.EvaluationIntervalThresholdForReset` | bool / float s | False / 0.1 | True / 0.25 |
| `TeleportDetection.PositionChangeThreshold` / `TeleportDetection.OrientationChangeThreshold` | float cm / deg | 100 / 30 | 500 / 45 |
| `SpaceMotion.bClampLinearAcceleration` / `SpaceMotion.MaxLinearAcceleration` | bool / float | False / 10000 | True / 4000 |
| `SpaceMotion.bClampAngularVelocity` / `SpaceMotion.MaxAngularVelocity` | bool / float **deg/s** | False / 720 | True / 180 |
| `SpaceMotion.bClampAngularAcceleration` / `SpaceMotion.MaxAngularAcceleration` | bool / float **deg/s^2** | False / 7200 | True / 1440 |
| `SpaceMotion.InertialForces.Amount` | float 0..1 | 1.0 | 0.6 |
| `SpaceMotion.Drag.LinearDragMultiplier` / `SpaceMotion.Drag.AngularDragMultiplier` | float 0..1 | 1.0 / 1.0 | 0.15 / 0.3 |
| output `DynamicsSolverComponentKey` (label "Solver Component Key") | FRigComponentKey | | K(root, DynamicsSolver) |

Field lines `CRD/Public/RigDynamicsData.h`: SolverSettings 136-212, Drag 219-258, InertialForces 265-297, SpaceMotion
304-365, TeleportDetection 373-404. Upgrade remap confirming nested paths: `CRD/Private/RigDynamicsSolverExecution.cpp:133-157`.

**RigUnit_SpawnDynamicsChains** ("Spawn Dynamics Chains") - `/Script/ControlRigDynamics.RigUnit_SpawnDynamicsChains` -
current - mutable - Construction only (`CRD/Private/RigDynamicsExecutionHelpers.cpp:125-275`, check :127). Header
`CRD/Public/RigDynamicsExecutionHelpers.h:140-217`. Particles are named `ParticleComponentName` (default
**`DynamicsParticle`**) on every bone; they are added to the solver only if `DynamicsSolverComponentKey` resolves at
that moment (:156,243-246).

| Pin path | Type | Default | Recipe |
|---|---|---|---|
| `DynamicsSolverComponentKey` (label "Solver Component Key") | FRigComponentKey | (Root, DynamicsSolver) | WIRE |
| `RootBones` | TArray<FRigElementKey> | empty | `_01` keys |
| `ParticleProperties.Radius` | float cm | 5 | 3.6 / 3.2 |
| `ParticleProperties.Mass` | float kg | 1 | 1 / 0.5 |
| `ParticleProperties.MovementType` | ERigParticleSimulationMovementType `Kinematic / Simulated` | Simulated | Simulated |
| `ParticleProperties.GravityMultiplier` | float | **0 on this node** (1 in the struct) | 1 |
| `ParticleProperties.Strength` | float Hz | 2 | 1.5 / 3.0 |
| `ParticleProperties.DampingRatio` | float | 0.5 | 0.6 / 0.7 |
| `ParticleProperties.TargetMode` | float 0..1 (0 sim space, 1 directional) | 0.5 | 0.7 |
| `ParticleProperties.AngleLimit` | float deg | 0 | 40 / 25 |
| `ParticleProperties.AngleLimitStrength` | float Hz (0 = off) | 0 | 6 / 10 |
| `ParticleProperties.Damping` (label "Damping/Drag") | float Hz | 0 | 1.5 / 2.0 |
| `ParticleProperties.bCollideWithColliders` | bool | True | True / False |
| `ChainCurves` | FParticleChainCurves (flat 1.0) | flat | (leave) |
| outputs `ParticleComponentKeys`, `ColliderComponentKeys` | TArray<FRigComponentKey> | | K(bone, DynamicsParticle) |

Particle property lines `CRD/Public/RigDynamicsData.h:560-651`; enum `CRD/Public/RigParticleSimulation.h:24-31`
(only two values, no Static/Default).

**RigUnit_SpawnDynamicsCollider** ("Spawn Dynamics Collider") - `/Script/ControlRigDynamics.RigUnit_SpawnDynamicsCollider`
- current - mutable - Construction only (`CRD/Private/RigDynamicsColliderExecution.cpp:14-47`, check :20). Header
`CRD/Public/RigDynamicsColliderExecution.h:18-47`.

| Pin | Type | Default | Recipe |
|---|---|---|---|
| `Owner` | FRigElementKey | (Bone, "") | J1_Forequarters |
| `DynamicsSolverComponentKey` | FRigComponentKey | (Root, DynamicsSolver) | WIRE |
| `ColliderComponentName` | FName | DynamicsCollider | (default) |
| `Shapes` / `Shapes.Capsules` | FRigDynamicsShapeCollection: `Boxes`, `Capsules`, `Planes`; capsule members `Name`, `TM` (owner-bone local, main axis +Z), `Radius` (default 10), `Length` (core, default 10) | empty | one capsule `Flank` |
| output `DynamicsColliderComponentKey` (label "Collider Component Key") | FRigComponentKey | | K(J1_Forequarters, DynamicsCollider) |

Shape lines `CRD/Public/RigDynamicsData.h:45-113`.

**RigUnit_HierarchySetDynamicsParticleMovementType** ("Set Dynamics Particle Movement Type") -
`/Script/ControlRigDynamics.RigUnit_HierarchySetDynamicsParticleMovementType` - current - mutable - any event, but only
effective before Instantiate (row 16) (`CRD/Private/RigDynamicsParticleExecution.cpp:19-28,278`). Header
`CRD/Public/RigDynamicsParticleExecution.h:333-349`. Pins `DynamicsParticleComponentKey` (label "Particle Component
Key", default (Bone "", DynamicsParticle)), `MovementType` (`Kinematic` / `Simulated`, default Simulated). Recipe:
K(b, DynamicsParticle), `Kinematic`.

**RigUnit_InstantiateDynamics** ("Instantiate dynamics") - `/Script/ControlRigDynamics.RigUnit_InstantiateDynamics` -
current - mutable - any event (`CRD/Private/RigDynamicsSolverExecution.cpp:205-225`). Header
`CRD/Public/RigDynamicsSolverExecution.h:131-143`. Pin `DynamicsSolverComponentKey` (default (Root, DynamicsSolver)).

**RigUnit_StepDynamicsSolver** ("Step Dynamics Solver") - `/Script/ControlRigDynamics.RigUnit_StepDynamicsSolver` -
current (the only one) - mutable - any event (`CRD/Private/RigDynamicsSolverExecution.cpp:228-279`). Header
`CRD/Public/RigDynamicsSolverExecution.h:148-193`. Pins `DynamicsSolverComponentKey` (default (Root, DynamicsSolver)),
`DeltaTimeOverride` (0; <0 no step), `SimulationSpaceDeltaTimeOverride` (0), `Alpha` (1), `bTrackVelocitiesDuringPassThrough`
(True), `VisualizationSettings.bShowParticles` / `bShowColliders` / `bShowConfiners` / `bShowSkeletalConstraints` /
`bShowHardConstraints` / `bShowSoftConstraints` / `bShowAngleLimits` / `bShowConeLimits` (all False),
`VisualizationSettings.ParticleValueDisplay` (None). Draws only when Alpha > 0 and `ControlRig.Dynamics.AllowVisualization`
!= 0 (:15-24, :268-275). `ControlRig.Dynamics.EnableStepSolver 0` disables stepping.

**RigUnit_HierarchyImportDynamicsCollidersFromPhysicsAsset1** - `/Script/ControlRigDynamics.RigUnit_HierarchyImportDynamicsCollidersFromPhysicsAsset1`
- current (deprecated twin without the `1`) - mutable - Construction only
(`CRD/Private/RigDynamicsExecutionHelpers.cpp:396-503`, check :398). Header `CRD/Public/RigDynamicsExecutionHelpers.h:259-300`.
Pins `DynamicsSolverComponentKey`, `ColliderComponentName` (DynamicsCollider), `PhysicsAsset` (TObjectPtr, same
loaded-asset rule as row 8), `ElementIncludeMask` / `ElementExcludeMask` (TArray<FRigElementKey>),
`bExcludeElementsWithParticles` (True); output `DynamicsColliderComponentKeys`. Spheres become zero-length capsules;
no convex support.

**RigUnit_GetDynamicsSolverData** - `/Script/ControlRigDynamics.RigUnit_GetDynamicsSolverData` - current - **pure**
(`CRD/Private/RigDynamicsSolverExecution.cpp:282-306`). Header `CRD/Public/RigDynamicsSolverExecution.h:519-566`.
Pin `DynamicsSolverComponentKey`; outputs `SimulationSpaceLinearVelocity` (cm/s), `SimulationSpaceAngularVelocity`
(deg/s), `SimulationSpaceLinearAcceleration`, `SimulationSpaceAngularAcceleration` (deg/s^2), `bTeleportDetected`,
`bKinematicSpeedResetTriggered`, `bPositionResetTriggered`, `bEvaluationIntervalResetTriggered`.

### 2.3 RigVMController calls used with these nodes (signatures checked)

`add_unit_node_from_struct_path(script_struct_path, method_name='Execute', position=Vector2D, node_name='', setup_undo_redo=True, print_python_command=False)`,
`set_pin_default_value(pin_path, default_value, resize_arrays=True, setup_undo_redo=True, merge_undo_action=False, print_python_command=False, set_value_on_linked_pins=True)`,
`add_link(output_pin_path, input_pin_path, ...)`,
`add_variable_node(variable_name, cpp_type, cpp_type_object, is_getter, default_value, position, node_name, ...)`
(`RVM/RigVMDeveloper/Public/RigVMModel/RigVMController.h:363-364,399-400,919-920,1041-1042`);
`URigVMPin.get_pin_path()`, `URigVMPin.is_execute_context()` (`.../RigVMPin.h:171-172,301-302`).

## 3. Risks (asserts, silent failures, editor traps)

Hard asserts (`check`) reachable from these nodes:
* `FRigPhysicsSolverComponent::GetPhysicsSolver` checks that the solver's stored key equals the component key
  (`CRP/Private/RigPhysicsSolverComponent.cpp:73`); `ShouldComponentBeInSimulation` has the same check
  (`CRP/Private/RigPhysicsSolver.cpp:97`). If a solver component's key changes while its solver exists (renaming or
  reparenting the owner bone in the rig editor while the preview simulates), this can assert. Do not rename/reparent
  `root` or `J1_Forequarters` with the preview running; recompile instead.
* `check(Alpha > 0)` in UpdatePostPhysics (`RigPhysicsSolver.cpp:1811`) is guarded by the early return at
  `:2023`; a NaN Alpha clamps to 1 (`:2150`). Safe.
* Dynamics `check(Particle.InvMass ...)` (`CRD/Private/RigParticleSimulation.cpp:33,125,177`) and
  `check(DeltaTime > 0)` (`CRD/Private/RigDynamicsSolver.cpp:570`) are internally consistent. `check(TopoOrder.Num() ==
  NumBones)` in Spawn Dynamics Chains (`CRD/Private/RigDynamicsExecutionHelpers.cpp:90`) holds even with duplicate or
  invalid root bones.

Ensures (non-fatal, log a callstack once):
* `ensure(WorldObject.ActorHandle != nullptr)` (`CRP/Private/RigPhysicsSolver_WorldObjects.cpp:86`) fires if Chaos
  could not build a kinematic copy of an overlapped world body (it is added to the map before CreateActor is checked,
  :261-286). Watch the log on the first dead frame near unusual geometry.
* Dynamics collider shape ensures (`CRD/Private/RigDynamicsSolver.cpp:734,743,753`) if a collider's shape count
  changes after instantiate. Set shapes only in Construction.

Silent failures (no error, the node just does nothing):
* Hard-coded component keys (`comp(b, 'PhysicsBody')` etc.) miss if the hierarchy appended a suffix on a name clash
  (`CR/Private/Rigs/RigHierarchy.cpp:2927-2948`). After the first build, list the components (or read the spawn nodes'
  output pins) once to confirm the names.
* A Dynamics spawn node placed before Spawn Dynamics Solver creates particles/colliders that never join the solver.
* `Set Dynamics Particle Movement Type` after Instantiate is ignored (row 16).
* Physics nodes left at the default solver/body key (empty bone name) never find anything (row 3).
* Instantiate From Physics Asset skips PA bodies whose bone is not in the rig hierarchy, and `BonesToUse` entries
  without a PA body; it only logs when the asset is null.
* `set_pin_default_value` on `PhysicsAsset` returns False if PA_Burrower is not loaded (row 8); the recipe's `setp`
  raises, which is the right behaviour.

Physics behaviour to watch:
* Zero-mass dynamic body if a simulated body ends up with no mass-carrying shape (tapered capsules in the PA, all
  shapes `bContributeToMass = false`, or explicit shapes of zero size). `MassOverride` cannot rescue it
  (`RigPhysicsSolver.cpp:610`).
* First dead frame has no world collision (objects are gathered after the step); Geometry-Collection tiles
  (WorldDynamic) are not collided with `Static` (row 7).
* The corpse does not inherit the flight velocity (row 5).
* Physics body MovementType is re-applied every step, Dynamics particle MovementType is not; do not port the Step 9
  "switch at death" idea to the Dynamics wires.
* `bResetFromEvaluationInterval` with the Physics default threshold 0 resets on ordinary frame-time jitter; always
  set the threshold (recipe sets 0.25 on HoseSolver).
* Rig editor preview: drawing happens only when Alpha > 0, so the ragdoll shows nothing unless `bIsDead` defaults to
  true. World collision in the preview may pick up the Persona preview floor if it is WorldStatic (not verified).

## 4. Not verified here

* Runtime behaviour in the editor (pin creation for every nested member is inferred from the struct reflection and
  Epic's own remap paths `SpaceMotion.InertialForces.Amount` / `SpaceMotion.Drag.*`, not observed).
* Whether the Persona/Control Rig preview scene floor is gathered as a world object.
* That `unreal.Transform.export_text()` output (recipe C10) imports cleanly into `FRigDynamicsShapeCapsule.TM` (it is
  standard FTransform text, so it should).
* Core Control Rig / RigVM math nodes in Steps 5.1/5.4 (outside this audit).
