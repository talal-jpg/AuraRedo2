# CR_Burrower ragdoll: why the death velocity is lost, and how to give it back (UE 5.8)

Read-only research, 2026-11-22. Nothing was run. The source is the 5.8 build at `/mnt/new_partition/5.8/Engine/`.
Every name below was also checked against the clone's Python stub `Intermediate/PythonStub/unreal.py`, where each
struct exists as `class <Name>(`.

| Tag | Path under `/mnt/new_partition/5.8/Engine/` |
|---|---|
| `CRP` | `Plugins/Experimental/ControlRigPhysics/Source/ControlRigPhysics` |
| `PC`  | `Plugins/Animation/PhysicsControl/Source/PhysicsControl` |
| `CR`  | `Plugins/Animation/ControlRig/Source/ControlRig` |
| `RVM` | `Plugins/Runtime/RigVM/Source/RigVM` |
| `IP`  | `Source/Runtime/Engine/Private/PhysicsEngine/ImmediatePhysics/ImmediatePhysicsChaos` |
| `CH`  | `Source/Runtime/Experimental/Chaos` |

## 0. Short answer

* **Why.** With `SimulationSpace = World`, the alive frames (Alpha 0, `bTrackVelocitiesDuringPassThrough` true) give
  every dynamic body the bone's **component-space** velocity each frame, only rotated into world. The component's
  own world velocity, and its turn (omega x r), are never computed or added anywhere in World space. On the first
  dead frame nothing resets or re-snaps the bodies. They step from last frame's world pose with only the small
  body-wave velocity, so gravity wins and they drop straight down. `StopMovementImmediately` is not the cause: the
  travel velocity was never in the simulation to begin with.
* **No solver setting fixes it.** World space ignores all component motion; the only extra input is the wind
  "External" drag. Component space plus inertial forces could fake it on the server, but it depends on frame order,
  hits teleport detection above about 1700 cm/s, and fails on clients (section 4).
* **Fix.** On the first dead frame, run one `Add Force` per body (J0..J4) right before `StepRagdoll`:
  `Type = VelocityChange`, `ForceAndTorqueSpace = World`, `LocationSpace = Body`, `Location = 0`.
  * `Linear` = `DeathVelocity + Rad(DeathAngularVelocity) x (c_k - c_0)`, with both centres in **world** space.
  * `Angular` = `Rad(DeathAngularVelocity)`.
  * Latch it with a private bool `bDeathKickDone`, and guard on `bIsDead` and DeltaTime > 0.
  * The C++ passes **world** vectors (section 3.5).

## 1. Why the CR ragdoll loses the travel velocity

### 1.1 Execute path of `StepRagdoll` (`RigUnit_StepPhysicsSolver1`)

* `FRigUnit_StepPhysicsSolver1_Execute` (`CRP/Private/RigPhysicsSolverExecution.cpp:266-313`) finds the solver
  component and calls `FRigPhysicsSolver::StepSimulation(World, OwningActor, ExecuteContext, Hierarchy, SolverComponent,
  DeltaTimeOverride, SimulationSpaceDeltaTimeOverride, Alpha, bTrackVelocitiesDuringPassThrough)`.
* `StepSimulation` (`CRP/Private/RigPhysicsSolver.cpp:1962-2163`):
  1. `PhysicsDeltaTime = ExecuteContext.GetDeltaTime()`, or the override. A negative override gives 0 (`:1978-1986`).
  2. If `bResetFromEvaluationInterval` is on and the gap since the last evaluation is too long,
     `TrackInputCounter = 3` (`:2004-2016`). This is off on RagdollSolver (default False, `CRP/Public/RigPhysicsData.h:827`;
     not set in `bw_04_control_rig.py` `RAGDOLL_SOLVER_PINS`).
  3. **Alpha <= 0 (alive)** (`:2023-2058`): with tracking on and dt > 0, the frame runs these steps.
     1. `UpdateSimulationSpaceStateAndCalculateData`.
     2. `Instantiate`. This returns early once done.
     3. `UpdateBodyRecordsPrePhysics`.
     4. `ResetPoseFromAnimation(SolverComponent, bUseSourceVelocity=true)`.
     5. `PreviousUpdateCounter = UpdateCounter`, which keeps the velocity history "consecutive".
     6. `ClearBodyForceAndTorques`: **any queued Add Force is discarded** (`:2057`).
     7. Return.
  4. **Alpha > 0 (dead)**: the frame runs these steps.
     1. Sim-space update (`:2062`), then Instantiate.
     2. Push the solver settings.
     3. `UpdatePrePhysics` (`:2140`). This does: the body records, then `CheckForResetsPrePhysics`, then
        `UpdateBodyPrePhysics` per body (movement type, damping), joints, controls, and **`ApplyForcesPrePhysics`**
        (`:1636-1648`).
     4. `Simulation->Simulate` (`:2142`).
     5. `UpdatePostPhysics`, which writes the bones back and **empties every body's ForceAndTorques** (`:1844`).
     6. World objects are gathered **after** the step (`:2157`).
     7. Steps 3 and 4 run only `if (PhysicsDeltaTime > 0)` (`:2138`). With Alpha > 0 and dt = 0, queued forces are
        still emptied in step 5 without being applied.

### 1.2 What "track velocities during pass-through" records

* `UpdateBodyRecordPrePhysics` (`:1019-1060`) reads `Hierarchy.GetGlobalTransform(SourceBone)`. That is **rig
  global = component space**.
  * It differentiates the transform against last frame:
    `SourceComponentSpaceVelocity = (P_now - P_prev)/dt`, plus the same for the angular velocity (`:1047-1053`).
  * The result is zero if the update counter was not consecutive (`:1054-1059`).
* `ResetPoseFromAnimation` (`:1096-1131`) teleports each **dynamic** body (kinematic ones are skipped, `:1105`).
  * Position: `SetWorldTransform(ConvertComponentSpaceTransformToSimSpace(SourceCS))`, which in World space is
    `SourceCS * ComponentTM` (`CRP/Private/RigPhysicsSolver_Space.inl:43`).
  * Velocity: `SetLinearVelocity(ComponentTM.TransformVectorNoScale(SourceComponentSpaceVelocity))`, and the same for
    the angular velocity (`:1116-1123`, `.inl:69`).
  * So the velocity is the component-space velocity **rotated** into world. The component's translation rate and
    turn rate are not part of it.
  * Chaos side: `FActorHandle::SetWorldTransform` sets X, P and PrevX/PrevR, and `SetLinearVelocity` sets V
    (`IP/ImmediatePhysicsActorHandle_Chaos.cpp:222-237, 370-393`). Nothing derives V from the teleport.
* Side note: the CS velocity is the **bone origin's** velocity, applied as the COM velocity. That is a small
  inconsistency in the wave motion only.

### 1.3 The first Alpha > 0 frame (no reset, no switch)

* In tracking mode, `bNeedToResetPose` stays false (`:2044`). So `UpdatePrePhysics` does not call
  `ResetPoseFromAnimation` (`:1572-1580`) and does not bump `TrackInputCounter`.
* The bodies start the step with exactly what the last alive frame set: that frame's pose in world, and that frame's
  rotated CS velocity.
* **No kinematic -> simulated switch happens.**
  * `CreateBody` makes every body a `DynamicActor` (`:567-571`).
  * Pass-through never calls `UpdateBodyPrePhysics`.
  * `UpdateBodyFromModifierData` with `MovementType Simulated` is then a no-op (`PC/Private/RigidBodyWithControl.cpp:143-149`).
  * The bodies were dynamic, and teleported, the whole time.
* `CheckForResetsPrePhysics` (`:1487-1546`) looks only at kinematic bodies, and only if `bResetFromKinematicSpeed` or
  `bResetFromKinematicAcceleration` is on. Both are off by default (`RigPhysicsData.h:808,817`).
* `bResetFromPosition` (off) measures `|SimSpaceTM.Translation|` (`:1828-1834`). **In World space that is the
  distance from the world origin**: never turn it on for this solver.
* Teleport detection: World space returns before any teleport detection or SpaceMotion conditioning
  (`CRP/Private/RigPhysicsSolver_Space.cpp:138-145`). There, `SimulationSpaceData.LinearVelocity` is just
  `SpaceMotion.Drag.ExternalLinearVelocity`, which is 0.

### 1.4 How World space uses the component transform

* `SimulationSpaceState.ComponentTM = ExecuteContext.GetToWorldSpaceTransform()`
  (`CRP/Private/RigPhysicsSolver_Space.cpp:111`).
  * It is set at the start of each rig execute from `OwningComponent->GetComponentToWorld()`
    (`RVM/Private/RigVMCore/RigVMExecuteContext.cpp:34-46`, `CR/Private/ControlRig.cpp:1138-1141`).
  * That is the Burrower **mesh** component, including client mesh smoothing.
* It is used only as a coordinate change:
  * bone CS -> world for the teleports (`.inl:43,56,69`);
  * world -> CS for the write-back (`ConvertSimSpaceTransformToComponentSpace`, `.inl:83`; `RigPhysicsSolver.cpp:1838`);
  * Add Force vectors (section 2);
  * the world-collision box.
* `GetSimulationSpaceTransform` is Identity for World (`.inl:29`). No component velocity or acceleration is ever
  computed in World space (`Space.cpp:138-145`). Chaos sim-space settings are enabled (`InertialForces.Amount` 1 > 0,
  `RigPhysicsSolver.cpp:2114`), but they get zero space velocity and acceleration (`:2123-2128`).

### 1.5 What the component stopping on the death frame does

* `HandleBurrowerDeath` (`Source/Aura/Private/Burrower/BurrowerCharacter.cpp:283-294` at HEAD 96ce1fe) calls
  `StopMovementImmediately()` and `DisableMovement()`. The actor, and so the mesh `ComponentTM`, is fixed from then on.
* In World space this changes nothing in the bodies' velocities, because they never had the travel velocity.
* It does keep the write-back sane. The corpse lives in world, and the bones are written relative to a stationary
  component.
* If the component kept moving, the corpse would still fall in world, while the capsule flew on and the bones were
  written further and further behind it. So keep the stop, and keep World space. World space is also immune to
  client mesh smoothing after death.
* Frame timing:
  * the bodies are one frame behind (last alive frame's world pose);
  * if the CMC moved this frame before the death, the component is `V*dt` ahead;
  * with the kick, the first step carries the bodies to about `P_prev + V*dt`, so there is no visible jump.

## 2. Candidate ways to give the bodies a velocity

| Candidate | Struct path | Verdict |
|---|---|---|
| **Add Force, `Type = VelocityChange`** | `/Script/ControlRigPhysics.RigUnit_HierarchyAddPhysicsBodyForce` | **Use.** Exact, mass independent, applied once in the same frame's step. |
| Add Force, `Impulse` | same | Needs each body's mass (`Linear * InvM`, `IP/...ActorHandle_Chaos.cpp:434-436`). The graph has no mass getter. No. |
| Add Force, `Acceleration` / `Force` | same | Applied in **every** substep (Acceleration is cleared only after `Advance`, `CH/Private/Chaos/Evolution/PBDMinEvolution.cpp:111-118`), so the result depends on dt. No. |
| Set Physics Solver External Velocity | `/Script/ControlRigPhysics.RigUnit_SetPhysicsSolverExternalVelocity` | A wind field. In World space it only moves the drag target (`TargetV = -LinearDragMultiplier * Ext`, damped by body damping 0.1/s, `PBDMinEvolution.cpp:244-275`). It is not an initial velocity. No. |
| Set Physics Body Kinematic Target | `/Script/ControlRigPhysics.RigUnit_HierarchySetPhysicsBodyKinematicTarget` | Pose only, and only for kinematic bodies. CRP has **no** node that sets body velocity. No. |
| Kinematic while alive (Alpha 1 always) + Movement Mode Simulated at death | `RigUnit_HierarchySetPhysicsBodyMovementType` | The kinematic V would hold the world velocity. But it costs a full step every alive frame, and gets ~0 on a client whose actor was already stopped by replication. No. |
| Component sim space + inertial forces | solver settings | See section 4. No. |
| Get Physics Body Linear/Angular/Point Velocity | `RigUnit_HierarchyGetPhysicsBody*Velocity` | Read-only, component space (`RigPhysicsSolver.cpp:836-841`). For debugging. |

### Facts for `Add Force` (`CRP/Public/RigPhysicsBodyExecution.h:585-611`, `.cpp:375-386`)

**Basics.**
* It is mutable (`ExecutePin`, IO) and has no event check, so it is legal in Forwards Solve.
* It only appends a record to `FRigPhysicsBodyComponent::ForceAndTorques` (`RigPhysicsBodyComponent.h:71-77`).

**Pins.**
* `PhysicsBodyComponentKey`: `FRigComponentKey`, default `(Bone None, PhysicsBody)`, so it must be set.
* `ForceAndTorque` is `FPhysicsControlForceAndTorqueData` (`PC/Public/PhysicsControlData.h:1072-1097`). Its sub-pins:
  * `ForceAndTorque.LocationSpace`: `EPhysicsControlSpace` `World / Component / Body`, default **Body**.
  * `ForceAndTorque.ForceAndTorqueSpace`: same enum, default **World**.
  * `ForceAndTorque.Type`: `EPhysicsControlForceType` `Force / Acceleration / Impulse / VelocityChange`, default
    Force (`:1059-1067`).
  * `ForceAndTorque.Linear`, `ForceAndTorque.Angular`, `ForceAndTorque.Location`: FVector, default 0.
* `Name`: FName, optional.

**When it applies.**
* It applies at the **next** `StepPhysicsSolver1` of the solver that owns the body, inside `UpdatePrePhysics`,
  **before** `Simulate` in the same frame (`RigPhysicsSolver.cpp:1636-1648, 2140-2144`).
* It is consumed in the first substep's `Integrate`: `DV += LinearImpulseVelocity`, `DW += AngularImpulseVelocity`,
  then both are zeroed (`PBDMinEvolution.cpp:228-229, 290-291`). So it applies exactly once.

**Requirements.** If any of these fails, the record is dropped silently:
* that step has Alpha > 0 (`:2057`);
* that step has dt > 0 (`:2138`, else emptied at `:1844`);
* the body is dynamic at that moment (`:1257`). This means `BodyData.MovementType = Simulated` and
  `TrackInputCounter == 0`; otherwise it is forced kinematic (`:1149-1157`).

**Space.**
* For both `World` **and** `Component`, 5.8 does `ConvertComponentSpaceVectorToSimSpace(ComponentTM.InverseTransformVector(v))`
  (`:1277-1283`). So in World sim space the input is a **real world** vector: `TransformVectorNoScale(InverseTransformVector(v))`
  = v for a unit-scale mesh.
* So `Component` is also read as world, whatever the enum comment says.
* Mesh scale s != 1 would divide the kick by s.

**Location `Body`, `(0,0,0)`.**
* The point is the body COM (`:1306-1311`).
* `AddForceAtLocation(VelocityChange)` with R = 0 gives `LinearImpulseVelocity += Linear` and no angular change
  (`IP/...ActorHandle_Chaos.cpp:448-467, 500-507`; CoM and actor transform use the same accessor,
  `CH/Public/Chaos/Particle/ParticleUtilities.h:61-64,140-143`).
* `AddTorque(VelocityChange)` gives `AngularImpulseVelocity += Angular` (`:514-538`).

**Units.**
* Linear: cm/s.
* Angular: **rad/s**, world vector. Chaos integrates `R1 = R0 + 0.5 dt (W,0) R0` (`CH/../ChaosCore/Private/Rotation.cpp:158-162`):
  a world-frame angular velocity with UE's `FQuat(axis, angle)` sign, so `v = W x r`. RigVM `Cross` is `A ^ B`
  (`RVM/Private/RigVMFunctions/Math/RigVMFunction_MathVector.cpp:276-279`).

## 3. Recommended Forwards Solve graph

### 3.1 Placement and per-life latch

* Exec order: `... wave (5.1) -> [DeathKick block] -> StepRagdoll -> rotor -> ...`.
* The kick sits **after the wave**, so the poses are this frame's input pose. It sits **right before StepRagdoll**,
  so the records are used in this frame's first simulated step.
* `StepRagdoll.Alpha = BoolToFloat(bIsDead)` is already 1 on that same frame.
* Do not leave `StepRagdoll.DeltaTimeOverride` negative, and do not enable any reset on RagdollSolver.

**Latch.**
* New **private** rig variable `bDeathKickDone` (bool, default False):
  `H.ensure_variable(rig, 'bDeathKickDone', H.CPP_BOOL, False, False, False)`.
* Fire condition: `bIsDead AND NOT bDeathKickDone AND DeltaTime > 0`.
* Inside the True branch, after the five Add Force nodes, add `Set bDeathKickDone = True`.
* RigVM variables persist across evaluations. A private variable is not driven by the AnimBP.
* A re-init of the rig recreates both the solver and the variable, so a second kick then is correct.
* No reset is needed, since there is one life per actor (death -> LifeSpan -> destroy).
* Why the dt guard: a first dead frame with dt 0 would empty the records unused (section 2). With the guard it waits
  for the next frame instead of setting the latch.
* A client's first dead frame may come late. The latch fires on whichever frame bIsDead first reaches the rig.
  `DeathVelocity` (the client's last nonzero alive velocity) and `bIsDead` arrive in the same
  `NativeUpdateAnimation` copy.
* `DeathTime` is not needed.

### 3.2 Pivot and body centres (which points)

* The rigid-body velocity of a point p is `V_actor + Omega x (p - ActorLocation)`. `V` = `GetVelocity()` is the
  velocity of the **actor origin**.
* Chaos's `V` is the **COM** velocity, so each body needs `c_k` = its COM, not the bone origin.
* In this asset the actor origin **is** J0's body COM:
  * the mesh relative location is `(-830,0,-187)` with rotation 0 (`BurrowerCharacter.cpp:84` at HEAD 96ce1fe, constructor `SetRelativeLocationAndRotation`), so the actor origin
    in mesh CS is `(830,0,187)`;
  * PA_Burrower's J0_Head capsule centre is CS `(830,0,187)` (`bw_03_physics_asset.py:72`).
* So use `p_pivot = c_0` (J0's COM), **not** the J0_Head bone `(1000,0,180)`. The bone is 170 cm ahead and would add a
  uniform error `Omega x (170,0,-7)`, about 119 cm/s at 40 deg/s.
* COM vs bone origin per body (CS rest): J0 -170, J1 -200, J2 -260, J3 -150, J4 -225 cm along X. Using bone origins
  would be wrong by up to about 180 cm/s per body mid-turn.
* Exact COM in the current pose:
  * `LocalCoM_k = MakeRelative(Global = GetPhysicsBodyCoMTransform.CoMTransform, Parent = GetPhysicsBodyTransform.Transform).Local.Translation`.
    Both getters return the pair written together by `SetPhysicsBodyComponentState` (`RigPhysicsSolver.cpp:831-842`).
    At the first dead frame, before StepRagdoll, both are still the Instantiate values (InstRagdoll in Construction):
    stale, but a consistent pair.
  * Before any instantiate both are identity, which degrades gracefully to the bone origin.
  * Then `c_k(CS) = TransformLocation(GetTransform(Jk, GlobalSpace).Transform, LocalCoM_k)`.
  * Do **not** use `CoMTransform.Translation` directly as the position: before the first step it is the spawn pose,
    not the current one.
* World lever arm: `r_k = ToWorld(c_k) - ToWorld(c_0)` with `RigUnit_ToWorldSpace_Location`. It uses the same
  `ExecuteContext.ToWorldSpaceTransform` that the solver uses as ComponentTM
  (`CR/Private/Units/Hierarchy/RigUnit_WorldSpace.cpp:20-24`), so scale is handled too.

### 3.3 Nodes (names suggested; `K(b) = (ElementKey=(Type=Bone,Name="b"),Name="PhysicsBody")`)

**New public rig variables** (the AnimBP pins): `DeathVelocity` and `DeathAngularVelocity`, cpp type
`/Script/CoreUObject.Vector` (`H.CPP_VECTOR`), default `(X=0.000000,Y=0.000000,Z=0.000000)`.

**Shared nodes**

| Node | Struct path | Pins |
|---|---|---|
| `Kick_Get_bIsDead` | variable getter `bIsDead` | out `Kick_Get_bIsDead.Value` |
| `Kick_Get_Done` | variable getter `bDeathKickDone` | out `.Value` |
| `Kick_NotDone` | `/Script/RigVM.RigVMFunction_MathBoolNot` | `Value` <- `Kick_Get_Done.Value`; out `Result` |
| `Kick_DT` | `/Script/RigVM.RigVMFunction_GetDeltaTime` | out `Result` (= `ExecuteContext.GetDeltaTime()`, the same dt the step uses) |
| `Kick_DTPos` | `/Script/RigVM.RigVMFunction_MathFloatGreater` | `A` <- `Kick_DT.Result`, `B` = `0.0`; out `Result` |
| `Kick_And1` | `/Script/RigVM.RigVMFunction_MathBoolAnd` | `A` <- `Kick_Get_bIsDead.Value`, `B` <- `Kick_NotDone.Result`; out `Result` |
| `Kick_Fire` | `/Script/RigVM.RigVMFunction_MathBoolAnd` | `A` <- `Kick_And1.Result`, `B` <- `Kick_DTPos.Result`; out `Result` |
| `Kick_Branch` | `/Script/RigVM.RigVMFunction_ControlFlowBranch` | exec in `ExecuteContext`; `Condition` <- `Kick_Fire.Result`; exec out `True`, `False`, `Completed` |
| `Kick_Get_V` | variable getter `DeathVelocity` | out `.Value` (world cm/s) |
| `Kick_Get_W` | variable getter `DeathAngularVelocity` | out `.Value` (world deg/s) |
| `Kick_WRad` | `/Script/RigVM.RigVMFunction_MathVectorRad` | `Value` <- `Kick_Get_W.Value`; out `Result` (world rad/s) |
| `Kick_SetDone` | variable setter `bDeathKickDone` | exec `ExecuteContext` (IO); `Value` = `True` |

**Per body, k = 0..4** (bone `Jk` in `J0_Head, J1_Forequarters, J2_Midbody, J3_Hindbody, J4_Tail`)

| Node | Struct path | Pins |
|---|---|---|
| `Kick_k_BodyTM` | `/Script/ControlRigPhysics.RigUnit_HierarchyGetPhysicsBodyTransform` (pure) | `PhysicsBodyComponentKey` = `K(Jk)`; out `Transform` |
| `Kick_k_CoMTM` | `/Script/ControlRigPhysics.RigUnit_HierarchyGetPhysicsBodyCoMTransform` (pure) | `PhysicsBodyComponentKey` = `K(Jk)`; out `CoMTransform` |
| `Kick_k_LocalCoM` | `/Script/RigVM.RigVMFunction_MathTransformMakeRelative` | `Global` <- `Kick_k_CoMTM.CoMTransform`, `Parent` <- `Kick_k_BodyTM.Transform`; out `Local` (use sub-pin `Local.Translation`) |
| `Kick_k_Bone` | `/Script/ControlRig.RigUnit_GetTransform` | `Item` = `(Type=Bone,Name="Jk")`, `Space` = `GlobalSpace`, `bInitial` = `False`; out `Transform` |
| `Kick_k_ComCS` | `/Script/RigVM.RigVMFunction_MathTransformTransformVector` ("Transform Location") | `Transform` <- `Kick_k_Bone.Transform`, `Location` <- `Kick_k_LocalCoM.Local.Translation`; out `Result` |
| `Kick_k_ComWS` | `/Script/ControlRig.RigUnit_ToWorldSpace_Location` ("To World", template) | `Value` <- `Kick_k_ComCS.Result`; out `World` |
| `Kick_k_Arm` (k>=1) | `/Script/RigVM.RigVMFunction_MathVectorSub` | `A` <- `Kick_k_ComWS.World`, `B` <- `Kick_0_ComWS.World`; out `Result` |
| `Kick_k_WxR` (k>=1) | `/Script/RigVM.RigVMFunction_MathVectorCross` | `A` <- `Kick_WRad.Result`, `B` <- `Kick_k_Arm.Result`; out `Result` |
| `Kick_k_Lin` (k>=1) | `/Script/RigVM.RigVMFunction_MathVectorAdd` | `A` <- `Kick_Get_V.Value`, `B` <- `Kick_k_WxR.Result`; out `Result` |
| `Kick_k_Force` | `/Script/ControlRigPhysics.RigUnit_HierarchyAddPhysicsBodyForce` (mutable) | `PhysicsBodyComponentKey` = `K(Jk)`; `ForceAndTorque.Type` = `VelocityChange`; `ForceAndTorque.ForceAndTorqueSpace` = `World`; `ForceAndTorque.LocationSpace` = `Body`; `ForceAndTorque.Location` = `(X=0.000000,Y=0.000000,Z=0.000000)`; `ForceAndTorque.Linear` <- `Kick_k_Lin.Result` (for k = 0: <- `Kick_Get_V.Value`, the lever arm is 0); `ForceAndTorque.Angular` <- `Kick_WRad.Result`; `Name` = `DeathKick` |

J0 needs only BodyTM, CoMTM, LocalCoM, Bone, ComCS and ComWS (for the pivot) plus its Force node. That is about
50 nodes in total, nearly all pure.

Sub-pin links: the wave stage already links **from** `<GetTransform>.Transform.Rotation`, and the rotor stage
(`ROTOR_MODE 'subpin'`) links **into** `Rotor_M1.A.Rotation`. So output and input sub-pin links work in this build.
If `ForceAndTorque.Linear` refuses a link, the fallback is the same as the rotor's: use a separate Add Force per term.

### 3.4 Exec wiring (bw_04 helpers)

```
b.f.add(branch)                    # chain: (wave) -> Kick_Branch; exec_out() then prefers 'Completed'
t = b.g.chain(branch, 'True')      # sub-chain from Kick_Branch.True
for k in 0..4: t.add(Kick_k_Force) # ExecutePin chain
t.add(Kick_SetDone)                # ExecuteContext; Value True
b.f.add(StepRagdoll)               # Kick_Branch.Completed -> StepRagdoll.ExecutePin (existing node)
```

In `_bw04_f_ragdoll`, build the kick block before `rs = b.f.add(...StepRagdoll...)`. Add the new structs to
`PINS_USED`, so the pin probe checks `ForceAndTorque.Type`, `.ForceAndTorqueSpace`, `.LocationSpace`, `.Location`,
`.Linear`, `.Angular`, `Name` and `PhysicsBodyComponentKey`.

### 3.5 Spaces: pass world vectors from C++ (recommended)

* Add Force reads `Linear`/`Angular` as **real world** vectors under both `World` and `Component`
  (`RigPhysicsSolver.cpp:1277-1283`).
* The ragdoll simulates in world. Bodies' velocities are world.
* So `DeathVelocity` (cm/s) and `DeathAngularVelocity` (deg/s) should stay **world** vectors, as the interface
  defines them. The rig converts only the lever arm, with `To World` (`RigUnit_ToWorldSpace_Location`; its inverse is
  `RigUnit_ToRigSpace_Location`, "From World").
* Component-space vectors from C++ would be wrong under either enum unless the rig rotated them back.

**C++ sign trap for `DeathAngularVelocity`.**
* UE's `FRotator` pitch-up is a **negative** rotation about +Y: pure pitch gives `Q.Y = -sin(P/2)`
  (`Source/Runtime/Core/Private/Math/UnrealMath.cpp:463`).
* So the world angular velocity is `Omega = (0,0,dYaw/dt) - (dPitch/dt) * GetActorRightVector()` (deg/s, roll 0),
  **not** `+ Right * dPitch/dt`.
* Safest: take it from the quaternions, as `PC/Public/PhysicsControlHelpers.h:44-48` does:
  `RadiansToDegrees((CurQ * PrevQ.Inverse()).GetShortestArcWith(FQuat::Identity).ToRotationVector() / Dt)`.
  That is the convention Chaos integrates.

### 3.6 Expected motion

* Each body gets `V + Omega x (c_k - c_0)` and spin `Omega`. That is the exact rigid motion of the flying worm, so the
  joints see no violation.
* The existing wave velocity stays on top, because VelocityChange **adds** to it.
* The corpse's COM then flies ballistically (straight plus gravity). The body keeps rotating, which is how "it keeps
  curving" shows.
* `RagDamp_*` `AngularDamping 1.0` /s removes about 63 % of the spin per second (Chaos ether drag,
  `PBDMinEvolution.cpp:272-275`). Lower it (0.2-0.3) if the turn should carry on longer. `LinearDamping 0.1` costs
  about 10 %/s of the travel speed.

## 4. Would a solver setting alone fix it?

* **World space: no.** Nothing in World space adds the component's motion (`Space.cpp:138-145`). External velocity is
  a wind or drag target, not an initial velocity (section 2).
* **Component space + `InertialForces.Amount 1`: partially, and fragile.**
  * When the frame stops, the fictitious forces would give `-LinearAcc*dt = +V` and the Euler term `+Omega x r`
    (`PBDMinEvolution.cpp:244-261`). That only works if the stop lands on a **stepped** (Alpha > 0) frame. If the
    actor stopped during a pass-through frame, the spike is computed and thrown away. That depends on the order of
    CMC, damage and anim on the server.
  * Teleport detection would zero it at speed. Default `LinearAccelerationThreshold 100000` cm/s^2
    (`RigPhysicsData.h:649-653`), while 3200 cm/s stopped in 1/60 s is 192000 cm/s^2.
  * On clients, the replicated stop and smoothing usually decelerate the mesh before the death RPC/OnRep is handled,
    so it gives nothing there.
  * It also changes the collision and reset semantics.
* **Kinematic while alive:** see the table in section 2.
* **Robustness verdict:** the explicit VelocityChange kick from C++-captured values is deterministic.
  * It applies in exactly one known step.
  * It is the same on server and clients.
  * It does not depend on frame ordering or on smoothing.
  * It is independent of the PA masses.
  * It has its own on/off switches (`bInheritVelocityOnDeath`, `bInheritTurnOnDeath` give zero vectors) and scale.

## 5. Risks and side effects of the kick (check in PIE)

1. **Wires (Dynamics, Component space) reset at 20 m.**
   * WireSolver has `Settings.bResetFromPosition True, PositionThresholdForReset 2000` (`bw_04_control_rig.py`
     `WIRE_SOLVER_PINS`).
   * The check is the distance from the **sim origin** (`ControlRigDynamics/Private/RigDynamicsSolver.cpp:1318-1326`).
   * The component stays at the death spot while the corpse flies away at 14-32 m/s. After about 1 s the wire
     particles pass 20 m and snap to the animated pose every frame, so the wires go rigid.
   * Raise the threshold (e.g. 1e6) or switch it off. A vertical fall already crosses 20 m after about 2 s.
2. **Hoses (Physics, Component space, owner J1).**
   * After death the corpse moves fast in component space. The hose chains are dragged at that speed (their kinematic
     roots follow J1), so expect strong trailing.
   * There are no position resets on that solver.
3. **World collision gathered late.**
   * The overlap box is the union of the dynamic bodies' AABBs x `WorldCollisionBoundsExpansion` 1.1
     (`CRP/Private/RigPhysicsSolver_WorldObjects.cpp:124-169`).
   * It is queried on the game thread **after** each step (`RigPhysicsSolver.cpp:2157`).
   * Across the worm's thin axes the 10 % margin is only about 18 cm, while 3200 cm/s is 53 cm per frame at 60 fps.
     So a pillar approached sideways or from below can be gathered a frame late. The first dead frame has no world
     objects at all.
   * If tunnelling shows, raise `SolverSettings.WorldCollisionBoundsExpansion` on RagdollSolver (e.g. 2.0).
4. **Forces dropped silently.** This happens if, on the firing frame, the step has Alpha <= 0 or dt = 0, or the
   bodies are kinematic (`TrackInputCounter > 0`).
   * Never enable `bResetFromEvaluationInterval` or `bResetFromKinematicSpeed/Acceleration` on RagdollSolver.
   * Never enable `bResetFromPosition` on it either: in World space that reset measures from the world origin.
   * The dt guard covers dt = 0.
5. **Mesh scale.** Add Force divides by the component scale (`InverseTransformVector` then `TransformVectorNoScale`).
   Keep the Burrower mesh and actor at scale 1, or pre-multiply.
6. **Actor left behind.** The capsule, and so the net relevancy and culling location, stays at the death point while
   the corpse flies on. Skeletal bounds follow the bones (PA-based), so rendering is fine. Only a very long flight
   would matter.
7. **Pitch sign** of `DeathAngularVelocity` in C++ (section 3.5).

## 6. Not verified here (needs the editor or PIE)

* That RigVM accepts a link into `ForceAndTorque.Linear` / `.Angular`. This is inferred from the working
  `Rotor_M1.A.Rotation` sub-pin link and from the struct reflection.
* That `To World` resolves to the `_Location` permutation when added by struct path. The template auto-resolves; the
  bw_04 resolved-struct check would catch a mismatch.
* That each PA_Burrower body's Chaos COM equals its capsule centre (single capsule, no COM nudge). The getter method
  does not depend on it; only the "pivot = actor origin" equality does.
* Runtime frame ordering of death vs anim update on server and client. The latch makes it irrelevant for
  correctness.
* How often `ExecuteContext.GetDeltaTime()` is 0 in practice (the guard handles it).
