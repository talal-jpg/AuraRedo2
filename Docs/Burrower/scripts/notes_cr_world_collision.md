# Burrower corpse vs the hex tiles: why it falls through, and what to change (UE 5.8)

Read-only research, 2026-11-22. Nothing was run. The engine source is the 5.8 build at `/mnt/new_partition/5.8/Engine/`.
Project facts come from the work clone `/mnt/new_partition/UnrealProjects/_BurrowerWork` (HEAD bcaf45d plus the
uncommitted bw_04 edits). Asset values were decoded offline with a copy of the uasset parser, kept in the scratchpad.

| Tag | Path under `/mnt/new_partition/5.8/Engine/` |
|---|---|
| `CRP` | `Plugins/Experimental/ControlRigPhysics/Source/ControlRigPhysics` |
| `PC`  | `Plugins/Animation/PhysicsControl/Source/PhysicsControl` |
| `EN`  | `Source/Runtime/Engine` |
| `IP`  | `Source/Runtime/Engine/Private/PhysicsEngine/ImmediatePhysics` |
| `CH`  | `Source/Runtime/Experimental/Chaos` |

## 0. Short answer

**1. Why corpses fall through intact tiles.** They do fall through. Both ragdoll modes have the same cause: an
**object-type mismatch**. Tunnelling is not the cause.

* **The tiles are `WorldDynamic`.**
  * `AMyHexPlatform` creates `HexPillarsISM` with `CreateDefaultSubobject<UInstancedStaticMeshComponent>`, which gets
    the `UStaticMeshComponent` default profile `BlockAllDynamic` (`EN/Private/Components/StaticMeshComponent.cpp:206`).
    That profile is ObjectType `WorldDynamic` (`Engine/Config/BaseEngine.ini:3106`).
  * The constructor only sets QueryAndPhysics and Block on every channel (`Source/Aura/Private/Actors/MyHexPlatform.cpp:74-80`).
  * Neither BP_MyHexPlatform nor BP_MyHexPlatformBottom overrides the BodyInstance. Their name tables have no
    `BodyInstance`, `ObjectType` or `CollisionProfileName`.
* **The CR ragdoll** has `WorldCollisionType = Static`, which gathers **object type `WorldStatic` only**, whatever the
  mobility. So the tiles are never added to the simulation.
* **The mesh fallback** body (object type Pawn) has `WorldDynamic = Overlap` (`BurrowerCharacter.cpp:103`). The base
  death only adds `WorldStatic = Block` (`MyCharBase.cpp:141`). Chaos needs both sides to block, so there is no contact.
* **Why only "sometimes".** Most tile props are `WorldStatic`: PCG descriptors with profile `BlockAll` for rocks,
  cliffs, ice, the paving `SM_PathFloor` and the bridges. Both modes collide with those, so a corpse sometimes catches
  on a prop or a bridge, and otherwise drops through the bare tiles.

**2. What to change.**
* **bw_04**, `RAGDOLL_SOLVER_PINS` (node `RagdollSolver`, struct `RigUnit_SpawnPhysicsSolver`):
  * `SolverSettings.WorldCollisionType`: `'Static'` -> **`'All'`**.
  * `SolverSettings.WorldCollisionBoundsExpansion`: `1.1` -> **`2.5`**.
  * Keep `bWorldCollisionIncludePhysics True` and `bWorldCollisionIncludeQuery False`.
  * Leave `bAllowCCD` False and the iterations as they are.
* **C++** (`ABurrowerCharacter::HandleBurrowerDeath`, the `bUseMeshRagdollFallback` branch):
  * Add `GetMesh()->SetCollisionResponseToChannel(ECC_WorldDynamic, ECR_Block);`.
  * Put it after the existing `SetCollisionEnabled(PhysicsOnly)` and before `Super::MulticastHandleDeath_Implementation()`.
  * CCD is not needed in either mode at 14-30 m/s (section 4).

**3. ISM tiles do work with the CR ragdoll in 5.8.** The gather is per instance:
* `Overlap.ItemIndex` goes to `GetBodyInstance(NAME_None, false, ItemIndex)`, with one world object per (component,
  instance) (`CRP/Private/RigPhysicsSolver_WorldObjects.cpp:226-252`).
* The ISM sets `bMultiBodyOverlap = true` (`EN/Private/InstancedStaticMesh.cpp:2368`).

So keep the CR ragdoll (`bUseMeshRagdollFallback = false`). Switching to the mesh fallback would not help on its own,
because it is broken the same way until the C++ line above goes in.

## 1. How ControlRigPhysics gathers world collision (5.8)

### 1.1 The setting does reach the solver

* bw_04 sets `SolverSettings.WorldCollisionType`, `.bWorldCollisionIncludePhysics`, `.bWorldCollisionIncludeQuery`
  and `.WorldCollisionBoundsExpansion` on the `RagdollSolver` node (`bw_04_control_rig.py:237-240`).
* On the struct side, these are pins of `FRigUnit_SpawnPhysicsSolver::SolverSettings`
  (`CRP/Public/RigPhysicsSolverExecution.h:98-99`), of type `FRigPhysicsSolverSettings`:
  * `WorldCollisionType`, default **None** (`CRP/Public/RigPhysicsData.h:697`);
  * the three include flags (`:702`, `:707`, `:712`);
  * `WorldCollisionBoundsExpansion`, default 1.1, ClampMin 1 (`:715-716`).
* The Construction execute copies the whole struct into the solver component (`CRP/Private/RigPhysicsSolverExecution.cpp:127`).
  `StepSimulation` reads it from there (`CRP/Private/RigPhysicsSolver.cpp:2075`). It serializes all four fields
  (`CRP/Private/RigPhysicsData.cpp:568-587`).
* The build proves the value got in:
  * `bw_cr_helpers.RigGraph.setp` raises when a default is refused (`bw_cr_helpers.py:678-688`);
  * the probe passed (`Saved/Burrower/04_cr.out:138`, "all 29 pin paths ... exist") and the build passed (`:207`);
  * the saved `CR_Burrower.uasset` holds a SpawnPhysicsSolver pin block with `Static` and `1.1`, next to the hose
    solver's `None`.
* So nothing is lost on the way. The problem is what `Static` means.

### 1.2 The query (`UpdateWorldObjectsPostPhysics`, `CRP/Private/RigPhysicsSolver_WorldObjects.cpp:112-329`)

**The box.**
* It is the union AABB of every **dynamic** body's `LocalBounds`, at its post-step transform (`:127-149`).
* Kinematic bodies are skipped (`:134`). If no body is dynamic, there is no query (`:151-154`).
* The box keeps its centre and its **half extent is multiplied** by `WorldCollisionBoundsExpansion` (`:163-166`).
* There is one box for the whole ragdoll. It has no velocity term.

**The query call.**
* `World->OverlapMultiByObjectType(Overlaps, Centre, Identity, ObjectQueryParams, Box, QueryParams)` (`:213-215`).
* `bTraceComplex = false`. `QueryParams.MobilityType = EQueryMobilityType::Any` (`:168-170`), so **mobility is
  never filtered**.

**Which object types each enum value queries** (`:173-183`):

| `WorldCollisionType` | `FCollisionObjectQueryParams` | Object types |
|---|---|---|
| None | (no query; existing world objects destroyed, `:41-55`) | - |
| **Static** | `AllStaticObjects` | `ECC_WorldStatic` only (`EN/Public/CollisionQueryParams.h:362`), plus custom object channels flagged `bStaticObject` (`EN/Private/Collision/CollisionProfile.cpp:460-464`). The project defines none (`Config/DefaultEngine.ini` has no channels). |
| Dynamic | `AllDynamicObjects` | every object channel except the static set (`CollisionQueryParams.h:397-400`): WorldDynamic, Pawn, PhysicsBody, Vehicle, Destructible, ... |
| All | `AllObjects` | both of the above (trace channels like Visibility and Camera are not object types) |

The header comment ("static (or kinematic, since they may move) objects", `RigPhysicsData.h:142-144`) is misleading.
"Static" means **object type WorldStatic**. It is not about mobility.

**Filters applied to each overlap** (`:217-309`):
* **ISM**: `IsA<UInstancedStaticMeshComponent>()` means `InstanceIndex = Overlap.ItemIndex`, and the key is
  `(Component UniqueID, InstanceIndex)` (`:226-238`). HISM is a subclass, so it is covered too.
  * `ItemIndex` is the body's `InstanceBodyIndex` when the component is multi-body (`EN/Private/Collision/CollisionConversions.cpp:726-738`).
  * The ISM constructor sets `bMultiBodyOverlap = true` and `Mobility = Movable` (`EN/Private/InstancedStaticMesh.cpp:2360,2368`).
  * `UInstancedStaticMeshComponent::GetBodyInstance(.., Index)` returns `InstancePhysicsBodies->GetBodyInstance(Index)`
    (`InstancedStaticMesh.cpp:2583-2586`). That is the per-instance body, or the component body for an invalid index,
    which fails `IsValidBodyInstance` (`EN/Private/InstancedMeshComponentBodies.cpp:276-283`).
  * Movable ISMs init one body per instance (`InstancedMeshComponentBodies.cpp:98-111`).
* **Owner excluded**: a new entry is skipped if `!OverlapComp->GetOwner() || GetOwner() == OwningActor` (`:243-246`).
  * `OwningActor` is the owner of the rig's owning scene component (the Burrower mesh)
    (`RigPhysicsSolverExecution.cpp:295-296`).
  * The check runs for new entries only. Owner-less components are skipped too.
* **Body must be valid** (`:248-252`). Then `IsBodyDesiredInSim` (`:24-31`):
  * the body's CollisionEnabled must have Physics if `bWorldCollisionIncludePhysics`;
  * or Query if `IncludeQuery`;
  * or Probe if `IncludeProbe`.
  * With the bw_04 values that means QueryAndPhysics or PhysicsOnly bodies.
* **New object**: it gets a **kinematic** immediate actor from the body
  (`ImmediatePhysics::MakeKinematicActorSetup(Body, WorldTM with Scale3D)`, `:257-273`).
  * Its geometry is the body setup's simple shapes, scaled (`IP/ImmediatePhysicsAdapters.cpp:107-150, 212-258`).
  * The friction and restitution come from the body's simple physical material, read on the game thread
    (`ImmediatePhysicsAdapters.cpp:250-256`).
  * It is added with `AddToCollidingPairs` (`:280`), which pairs it with every actor that could be dynamic
    (`IP/ImmediatePhysicsChaos/ImmediatePhysicsSimulation_Chaos.cpp:615-628`).
* **Existing object**: its transform is refreshed and its last-seen counter updated (`:289-308`).
* **Filter flags inside the immediate sim**:
  * Every shape is set to block everything (`IP/ImmediatePhysicsChaos/ImmediatePhysicsActorHandle_Chaos.cpp:88-99`).
  * Filtering is disabled (`ImmediatePhysicsSimulation_Chaos.cpp:382`).
  * So the world component's **channel responses do not matter**, only its object type (for the query) and its
    CollisionEnabled.

### 1.3 When it runs: latency

* The overlap is an `AsyncTask(ENamedThreads::GameThread, ...)`.
  * In editor builds it runs inline if the rig already evaluates on the game thread (`:316-327`).
  * It is queued **after** the step (`RigPhysicsSolver.cpp:2157`).
* Results are consumed at the **next** step's `UpdateWorldObjectsPrePhysics` (`:2130`):
  * new objects get `InitWorldTransform`;
  * known ones get `SetKinematicTarget` (`RigPhysicsSolver_WorldObjects.cpp:81-106`).
* Expiry: an object not seen by the latest query is dropped one step later. `GetExpired` is
  `UpdateCounter > LastSeen + 1` (`CRP/Private/RigPhysicsSolver.h:555-566`).
* While alive (`Alpha <= 0`), `StepSimulation` returns at `RigPhysicsSolver.cpp:2058`, **before** the gather. So:
  * **dead frame 1**: the death-kick frame steps with **no** world objects;
  * **dead frame 2**: it gets the objects from frame 1's post-step box (if the game-thread task has run by then);
  * from then on, the objects always lag one frame behind the body positions.

### 1.4 Tunnelling and CCD inside the immediate sim

**Settings.**
* `SolverSettings.bAllowCCD` defaults to False (`RigPhysicsData.h:797`) and is pushed every step
  (`RigPhysicsSolver.cpp:2102`). The immediate sim's own default is off (`ImmediatePhysicsSimulation_Chaos.cpp:385`).
* Per-body CCD:
  * comes from the physics asset's `DefaultInstance.bUseCCD` (`CRP/Private/RigPhysicsExecution.cpp:358`);
  * or from the node `RigUnit_HierarchySetPhysicsBodyEnableCCD` (`CRP/Public/RigPhysicsBodyExecution.h:557-578`,
    pin `bEnableCCD`);
  * and is applied with `SetCCDEnabled` (`PC/Private/RigidBodyWithControl.cpp:151`).
  * PA_Burrower stores no `DefaultInstance`, so `bUseCCD` is false.

**Swept bounds.** Without CCD, dynamic bodies still get **swept** bounds (X to P) every integrate
(`CH/Private/Chaos/Evolution/PBDMinEvolution.cpp:293-296`). So a world object that is **in the sim** is always found
by the broad phase.

**When a body can still pass through.** The narrow phase works on the end pose. A body only gets through a slab if, in
one substep, it moves more than about `r + t/2`. After that the shortest push-out points downward:

| Quantity | Value |
|---|---|
| Body capsule radii r (PA_Burrower `SkeletalBodySetup_0..4`, decoded) | 160 / 185 / 175 / 125 / **85** (J4_Tail) cm |
| Rim top tile t | 80 cm (section 3) |
| Limit for the tail at `MaxDeltaTime` 0.0334 s (bw_04) | 85 + 40 = 125 cm per substep, about **37 m/s** |
| Corpse speed | 14-30 m/s |

So **CCD is not needed** once the tile is in the simulation.

**What does let a fast corpse through is the gather latency (1.3).**
* The tile below must already be inside the expanded box one frame ahead.
* With expansion 1.1 the vertical margin is only 0.1 x the half height, about 0.1 x 185 = **18 cm**.
* A body falling v x dt further than that reaches the tile before the tile exists in the sim.
* At 30 m/s and 12 fps (PIE on this PC runs at 9-13 fps) that is 250 cm per frame. That is enough to pass a whole
  80 cm rim tile: 170 cm tail diameter plus 80 cm.
* CCD cannot help here, because the object is missing, not too thin. Only `WorldCollisionBoundsExpansion` helps
  (section 2.1).

**MaxDepenetrationVelocity 300 (bw_04).**
* It goes to `Collisions.SetMaxPushOutVelocity` (`ImmediatePhysicsSimulation_Chaos.cpp:820-822`).
* In 5.8 it clamps the accumulated correction term of a contact (`CH/Public/Chaos/Collision/PBDCollisionSolver.h:896-900`).
  It does not clamp the contact's initial error.
* So it does not stop a landing. Leave it as it is.

## 2. Settings to change

### 2.1 bw_04 (`RAGDOLL_SOLVER_PINS`, node `RagdollSolver`, `/Script/ControlRigPhysics.RigUnit_SpawnPhysicsSolver`)

| Pin path (relative to the node) | Now | New | Why |
|---|---|---|---|
| `SolverSettings.WorldCollisionType` | `'Static'` | **`'All'`** | Tiles are WorldDynamic; props, paving and bridges are WorldStatic, so both are needed. `Dynamic` would drop the WorldStatic props. CR_Mech already uses `All` (`Content/Assets/Characters/Mech/CR_Mech.uasset` pin text `ERigPhysicsWorldCollisionType::All`). |
| `SolverSettings.WorldCollisionBoundsExpansion` | `1.1` | **`2.5`** | Margin = (E-1) x half extent. Level corpse: half height about 185, so the Z margin is about 278 cm. That covers 30 m/s down to about 11 fps. 2.0 (185 cm) is enough at 30 fps or more. |
| `SolverSettings.bWorldCollisionIncludePhysics` | True | True | Tiles and props are QueryAndPhysics. |
| `SolverSettings.bWorldCollisionIncludeQuery` | False | False | Skips QueryOnly things (player meshes, triggers, live Burrowers). |
| `SolverSettings.bWorldCollisionIncludeProbe` | (default False) | optional explicit False | - |
| `SolverSettings.bAllowCCD` | (default False) | False | Section 1.4. |
| `SolverSettings.PositionIterations` / `VelocityIterations` / `ProjectionIterations` | 8 / 2 / 1 | unchanged | Enough for 5 bodies resting on boxes. |
| `SolverSettings.MaxDepenetrationVelocity` | 300 | unchanged | Section 1.4. |

**Pin probe.** `PINS_USED` comes from the dict, so the pre-build probe covers the two changed pins without edits.

**Check to add to bw_04b.** The `_pin_default` paths are:
* `RagdollSolver.SolverSettings.WorldCollisionType` == `All`
* `float(RagdollSolver.SolverSettings.WorldCollisionBoundsExpansion)` >= 2.0

**Deviation block.**
* Add item 29.
* Replace the "kept on purpose ... WorldCollisionBoundsExpansion 1.1 (raise to ~2.0 ...)" sentence
  (`bw_04_control_rig.py:117-118`).

**Optional CCD, only if `DeathVelocityScale` ever pushes corpses past about 35 m/s.**
* `SolverSettings.bAllowCCD = True`.
* In Construction, after the RagMove nodes, add one
  `/Script/ControlRigPhysics.RigUnit_HierarchySetPhysicsBodyEnableCCD` for J4_Tail, with
  `PhysicsBodyComponentKey = (ElementKey=(Type=Bone,Name="J4_Tail"),Name="PhysicsBody")` and `bEnableCCD = True`.
  Both nodes are in the stub (`unreal.py:235966`, `:236442`).
* Not recommended now.

**Cost with `All` + 2.5.**
* The query box is about 51 m long for a level corpse. It is much larger when the corpse lies diagonally, because it is
  an AABB.
* Expect a few dozen to a little over a hundred instances: tiles of about 10.4 m^2 each at HexRadius 200, plus props.
* Each one becomes a kinematic box or convex actor paired with 5 bodies (only 5: RagdollSolver has J0..J4 only).
* That is one box overlap per dead Burrower per frame on the game thread, plus actor churn as the box moves. That is
  fine for a few corpses for 10 s (LifeSpan). Check `stat` in PIE if many die at once.

### 2.2 C++ (mesh fallback), `Source/Aura/Private/Burrower/BurrowerCharacter.cpp:326-337`

```cpp
if (bUseMeshRagdollFallback)
{
    GetMesh()->SetCollisionEnabled(ECollisionEnabled::PhysicsOnly);
    // The hex tiles (AMyHexPlatform::HexPillarsISM) are WorldDynamic (BlockAllDynamic); the alive mesh only overlaps
    // WorldDynamic (constructor), and the base death adds WorldStatic only, so without this the corpse falls through
    GetMesh()->SetCollisionResponseToChannel(ECC_WorldDynamic, ECR_Block);
    Super::MulticastHandleDeath_Implementation();
    ApplyDeathMotionToMeshBodies();
}
```

**Why it is needed.**
* Chaos sim contacts need `(ChannelMask0 & BlockMask1) && (ChannelMask1 & BlockMask0)`
  (`CH/Private/Chaos/CollisionFilterData.cpp:263-272`).
* The mesh is ObjectType Pawn, with every channel Ignore except Visibility Block, WorldDynamic Overlap and PhysicsBody
  Overlap (`BurrowerCharacter.cpp:99-104`).
* The base death adds WorldStatic Block (`MyCharBase.cpp:141`).
* The tiles block Pawn, but the mesh does not block WorldDynamic.

**What to keep as it is.**
* Keep `PhysicsBody` at Overlap, so the corpse does not hit the bridge planks (PhysicsActor profile, `MyHexBridge.cpp:727`)
  or the debris.
* Keep `Pawn` at Ignore, so players do not hit it.

**Timing.** `SetCollisionResponseToChannel` before `SetSimulatePhysics` updates the body filter data, so the first
simulated step already blocks.

**CCD.** Not needed: the main scene caps physics dt at 1/30 s (`EN/Private/PhysicsEngine/PhysicsSettings.cpp:22`,
and the project does not override it), and the radii are at least 85 cm. If ever needed, call
`FBodyInstance::SetUseCCD(true)` (`EN/Classes/PhysicsEngine/BodyInstance.h:1072`) on the bodies in the
`ApplyDeathMotionToMeshBodies` loop.

### 2.3 Alternative not recommended: make the tiles WorldStatic

* The change: one line, `HexPillarsISM->SetCollisionObjectType(ECC_WorldStatic)`, in the `AMyHexPlatform` constructor.
* What it would do: it fixes both ragdolls without any Burrower change.
* Why not:
  * It is outside the Burrower files.
  * It changes other systems. For example, the Mech Sentinel wreck query is `FCollisionObjectQueryParams(ECC_WorldStatic)`
    (`MechSentinelCombatProcessors.cpp:245`), so wrecks would start landing on tiles.
  * Object-type queries elsewhere would change too.
* Leave it for Talal to decide.

## 3. Project facts: the hex tiles

**Component.** `HexPillarsISM` is the root and the only tile component:
* `SetRemoveSwap()`;
* `NumCustomDataFloats 5`;
* `QueryAndPhysics`;
* Block on all channels;
* profile BlockAllDynamic, so **WorldDynamic**;
* **Movable** (the ISM default; the BP does not override it).

Sources: `MyHexPlatform.cpp:65-80`. The BP's HexPillarsISM export only overrides the RVTs.

**Spawning.** The platforms are spawned at runtime by PCG on the server and replicated. Each machine builds its own
grid in BeginPlay. Mobility does not matter to the CR query (MobilityType Any).

**Collision shapes.** They are simple boxes, `CTF_UseSimpleAsComplex` (decoded BodySetup):

| Mesh | Box size | Box Z range (mesh space) | Scale | Height in game |
|---|---|---|---|---|
| `geo/SM/HexPillar` (top platforms) | 167 x 189 x 200 | -200 to 0 (top face at the instance origin) | X/Y `HexRadius/100`; Z = `Lerp(GridSize*VerticalScaling*Noise, 0.4, Distance01)` (`MyHexPlatform.cpp:1309-1313, 1342-1348`) | **80 cm** at the rim (scale 0.4), more inside |
| `geo/SM/HexPillarBottom` (bottom platforms) | 173 x 191 x 370 | centre -185 | Z = `HexRadius/100 * HexPillarBottomScaleZ` (`:1201`) | 741 cm at HexRadius 200 |

The meshes' `DefaultInstance` says BlockAll/WorldStatic, but a static mesh component ignores that unless
`bUseDefaultCollision` is set, and it is not set here.

**Collapse.**
* `ActivateHexLocal` -> `RemoveHexInstance` -> `HexPillarsISM->RemoveInstance(i)` with **RemoveAtSwap**
  (`MyHexPlatform.cpp:1909, 2183`).
* `FInstancedMeshComponentBodies::RemoveAtSwap` moves the last instance's body into index i
  (`InstancedMeshComponentBodies.cpp:200-217`).
* The broken tile then becomes a Geometry Collection or a falling skeletal mesh.
* A GC's component-level body is not a valid body instance, so the CR skips GC debris.

**Props are WorldStatic.** Decoded `UPCGMeshSelectorWeighted` descriptors:
* **`BlockAll`, `ECC_WorldStatic`, `QueryAndPhysics`**:
  * `PCG_HexTileProps`: cliffs, boulders, rocks, ruined pillar;
  * `PCG_HexTileProps2`: `SM_PathFloor`, ice cliffs, debris, rocks, mountains;
  * `PCG_HexTileProps3`: path floor, ice shards;
  * one descriptor each in `PCG_Bridge` and `PCG_Bridge2`.
* **`NoCollision`**: rock patches, flakes, snow mounds, most PCG_Bridge2 meshes, the atmosphere graphs.
* If a descriptor had no override, the PCG default would come from the HISM CDO (BlockAllDynamic,
  `EN/Private/ISMPartition/ISMComponentDescriptor.cpp:24-27`).

## 4. Evidence from the existing PIE runs

**The corpses died over intact tiles.**
* `Saved/Burrower/pie_result_pie_cr_ragdoll_20261122T064438.json` `e_tiles`: the Burrowers cut
  `BP_MyHexPlatformBottom_C_0`, with tile tops at z = 128.8. 286 of its 297 tiles were still standing.
* `h_death`: `mean_bone_z_drop_cm` was 9398-10221 over the 30 x 0.2 s window. The 01:22 run had 7289-12504.
* That fits an unobstructed fall with LinearDamping 0.1, and with some sim time lost at 9-13 fps
  (MaxDeltaTime 0.0334 x 4 substeps per frame).
* The mesh-fallback runs (`pie_main`, `pie_gun`) dropped 3790-7293 cm in 4 s, which also fits a fall.

**The PIE logs show the corpse's first gather finding only non-tile objects.**
* `Saved/Logs/Aura.log`: `KillAll` is at frame 66 (line 3577). At frame 68, exactly one frame of latency later, there
  are **62 + 62** `LogRigPhysics: Adding object BP_MyHexPlatformBottom0/17`. Those are the same platform under its
  server and client labels.
* Then they expire 1-4 per frame over the next 2-3 s, as the box falls away.
* The three 11-21 backup logs show the same pattern at kill + 2 frames (54/54, 49/49, 14/14).
* Under `Static` these can only be that platform's WorldStatic PCG props. They cannot be its tiles.
* The label is the owner actor, so the log itself cannot tell tiles from props.
* The `BP_MyCharMech*` and other platform adds before the kill come from **CR_Mech** (WorldCollisionType All), not from
  the Burrower.

**How to verify after the fix.** In PIE, after a kill:
* `mean_bone_z_drop_cm` should be a few metres at most over a standing platform;
* the `Adding object <platform>` burst should grow (tiles plus props) and should **not** expire while the corpse lies there;
* optional: `ControlRig.Physics.ShowWorldOverlapBoxOverride 1` and `ControlRig.Physics.ShowWorldObjectsOverride 1`
  (`CRP/Private/RigPhysicsSolver_Visualization.cpp:48-52`). They draw through the rig's draw interface; whether that
  is visible in a PIE viewport is not verified.

## 5. Risks after the change

1. **Dying inside the cut.**
   * While cutting, the body bottoms sit below the tile tops. In the harness `e_tiles` data the rotor centre is at
     `rotor_z` 212-300, 0.8-1.7 m above tile tops at 128.8. The body capsules are at about the same height with radii
     up to 185 cm, so their bottoms are up to about 1 m below the tile tops.
   * Frame 2 then adds tiles that already overlap the bodies.
   * Chaos pushes them out along the shortest direction: up when a body's centre is above the tile top, which is the
     normal case.
   * Watch for a visible pop. If it is too strong, lower `MaxDepenetrationVelocity` (more gradual).
2. **First dead frame has no world collision** (1.3).
   * A corpse that dies within v x dt of a surface moves one frame unblocked.
   * This is unavoidable in 5.8, because alive frames return before the gather.
3. **Players' capsules become obstacles.**
   * `All` includes Pawn. An ACharacter capsule uses the `Pawn` profile (`EN/Private/Character.cpp:79`), which is
     QueryAndPhysics (`BaseEngine.ini:3110`), so it is added as a kinematic world object. CR_Mech's log shows the mechs
     being added the same way.
   * A player walking into a corpse shoves it, with infinite mass.
   * The player is not blocked, because the corpse mesh is NoCollision in CR mode.
4. **RemoveAtSwap next to a corpse.**
   * If a tile collapses near a resting corpse while the swapped-in last instance is also inside the box, the existing
     `(component, i)` entry is refreshed with the other tile's transform (`RigPhysicsSolver_WorldObjects.cpp:289-307`).
   * `SetKinematicTarget` then sweeps that kinematic box across in one step, and can launch the corpse.
   * This is rare. A fix would need non-swap removal in AMyHexPlatform, which also changes its index bookkeeping, or
     simply accepting it.
5. **Dissolve and LifeSpan.** The corpse rests for at most 10 s, so the box stays small and the cost is bounded.
6. **Docs to correct.**
   * `control_rig_recipe.md:298` ("Static ... hex tiles: ISM") is wrong.
   * Answer the open questions in `control_rig_recipe.md:681-683` and `:858-861`: ISM instances are supported, and the
     owner is excluded.

## 6. What the mesh fallback would lose (if Talal still wants it)

**Pose.**
* The rig keeps running: `bIsDead` still drives `StepRagdoll`, so the CPU pays for two ragdolls.
* J0..J4 come from the main-scene bodies. The rig's corpse pose is thrown away.
* The hose and wire bones keep their rig-local transforms on top of the physics bones. They stay attached, but their
  wobble is computed against the discarded rig pose.
* The CR death kick block is unused. `ApplyDeathMotionToMeshBodies` does the same job.
* To use the fallback cleanly, the anim instance should feed `bIsDead = false` to the rig when `bUseMeshRagdollFallback`
  is on. That is a C++ change in `UBurrowerAnimInstance`.

**Gains.**
* Native scene collision with no gather box and no latency. It handles ISM per-instance bodies natively, and CCD is
  available.
* It only collides with what its responses block: WorldStatic plus WorldDynamic after 2.2. Players and debris are not
  included.

**Both modes are cosmetic and per machine.** According to the project comment at `BurrowerCharacter.cpp:442`, the
mesh does not simulate on a dedicated server. This was not re-checked in the engine.

## 7. Not verified here (needs the editor or PIE)

* That `All` + 2.5 actually leaves corpses on the tiles at PIE frame rates, and how big the pop is when dying inside
  the cut.
* Which exact objects the 62-object burst was: props by code. The log does not tell, and a tile was impossible under
  `Static`.
* The PCG descriptor collision of every spawner node. Only the decoded selector instances are listed in section 3, and
  one nameless descriptor each in PCG_Bridge and PCG_Bridge2.
* Whether the rig visualization CVars draw in a PIE viewport.
* Whether the game-thread overlap task always runs before the next rig evaluation under parallel animation evaluation.
  If it lags a frame, objects can expire and re-add (flicker). Section 1.3 assumes it runs within the frame.
