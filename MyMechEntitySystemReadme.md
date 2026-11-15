# Mech Sentinel Swarm (Mass Entity + GAS + MassReplication)

A Matrix-style swarm of squid-like "sentinels" built on **Mass Entity**. Thousands of flyers avoid each other,
pick targets from a **shared fragment** (a targeting board), switch to an **attack state** in range, are drawn with
**instanced static meshes**, take hits through **simple collision capsules**, and resolve health / armor / buffs /
stuns with the **Gameplay Ability System**, while all the data lives in Mass. It is **server authoritative** and
replicated with the engine's **MassReplication**.

All code is in `Source/Aura/Public/MechSwarm` and `Source/Aura/Private/MechSwarm`.

---

## Contents

1. [Quick setup in the editor](#1-quick-setup-in-the-editor)
2. [Architecture at a glance](#2-architecture-at-a-glance)
3. [Folder and file map](#3-folder-and-file-map)
4. [Structural dependencies](#4-structural-dependencies)
5. [What a sentinel entity is made of](#5-what-a-sentinel-entity-is-made-of)
6. [One frame, step by step](#6-one-frame-step-by-step)
7. [Targeting through the shared fragment](#7-targeting-through-the-shared-fragment)
8. [Combat data flow (GAS logic, Mass storage)](#8-combat-data-flow-gas-logic-mass-storage)
9. [Replication data flow](#9-replication-data-flow)
10. [Waves](#10-waves)
11. [Hitting sentinels from actors (the capsule function)](#11-hitting-sentinels-from-actors-the-capsule-function)
12. [ISM representation and the material](#12-ism-representation-and-the-material)
13. [_Copy classes and their engine counterparts](#13-_copy-classes-and-their-engine-counterparts)
14. [Design choices, deviations and limitations](#14-design-choices-deviations-and-limitations)
15. [Sentinel model and Niagara ribbon tentacles](#15-sentinel-model-and-niagara-ribbon-tentacles)

---

## 1. Quick setup in the editor

The `MassGameplay` plugin is enabled in `Aura.uproject`, and the Mass modules are added in `Aura.Build.cs`.

1. **Gameplay effects** (Blueprint `GameplayEffect` assets):
   | Asset (suggested name) | Duration | What to put in it |
   |---|---|---|
   | `GE_SentinelDamage` | Instant | Executions: `ExecCalc_SentinelDamage`. No modifiers are needed. |
   | `GE_SentinelAttack` (sentinel hits a player) | Instant | Either a modifier on `MyAttributeSet.IncomingDamage`, Add, magnitude **Set by Caller** tag `SetDamageByCaller`, or Executions: the project's `ExecCalc_Damage`. |
   | `GE_SentinelStun` (optional) | Has Duration, e.g. 2 s | Component "Grant Tags to Target Actor": `State.Sentinel.Stunned` |
   | `GE_SentinelShield` (optional) | Has Duration | Grant `State.Sentinel.Shielded` (damage x `ShieldedDamageMultiplier`) |
   | Buffs / debuffs (optional) | Duration / Infinite | Modifiers on `MechSentinelAttributeSet.Armor`, `AttackDamage`, `AttackSpeed`, `MoveSpeedMultiplier` |
2. **Rules asset**: create a `MechSentinelSwarmRules` data asset. Set `DefaultSentinelDamageEffect = GE_SentinelDamage`,
   `SentinelAttackEffect = GE_SentinelAttack`, and tune the caps. Assign it on your GameMode Blueprint
   (`BP_MyGameMode` > **Mech Sentinels** > **Sentinel Swarm Rules**).
3. **Mesh / material**: run `SourceArt/MechSentinel/ue_import_mech_sentinel.py` in the editor. It imports the low-poly
   sentinel (`SM_MechSentinel_Head`, `SM_MechSentinel_Far` with baked tentacles, the tentacle and claw tip) and creates the
   tentacle ribbon material. Give the head a material that reads `PerInstanceCustomData` 0..3
   (see [section 12](#12-ism-representation-and-the-material)). For the Niagara tentacles, build
   `NS_MechSentinelTentacles` with the recipe in [section 15](#15-sentinel-model-and-niagara-ribbon-tentacles).
4. **Entity config**: create a `MassEntityConfigAsset` (for example `DA_SentinelConfig`) with these traits:
   | Trait | Settings |
   |---|---|
   | **Mech Sentinel** | `SwarmGroup`, attribute defaults, shared `MovementSpeed`, `Parameters` (attack range, orbit, capsule size, death fall) |
   | **Movement (Copy)** | max speed / acceleration |
   | **Avoidance (Copy)** | separation distance / strength, prediction time |
   | **Smooth Orientation (Copy)** | turn speed, max pitch, banking |
   | **Visualization ISM (Copy)** | Mesh `SM_MechSentinel_Head`, LowLODMesh `SM_MechSentinel_Far`, materials, `NumCustomDataFloats = 4`, LOD distances |
   | **Mech Sentinel Tentacles (Niagara)** (optional) | Niagara System `NS_MechSentinelTentacles`, budget (`MaxRiggedSentinels`, `MaxDistance`), sway / stiffness |
   | **Replication** (engine trait) | **Bubble Info Class = `MechSentinelClientBubbleInfo`**, **Replicator Class = `MechSentinelReplicator`**. Suggested LOD distances 0 / 2500 / 7000 / 20000, max count per viewer 150 / 300 / 1000, update interval 0.1 / 0.2 / 0.4 / 0.5 |
   If the Replication trait points at other classes, the swarm subsystem logs an error and ignores the config (instead of the engine asserting).
5. **Spawner**: place a `MechSentinelWaveSpawner` in the level (it must be **level-placed**, so clients build the same
   entity template before replicated sentinels arrive). Assign `EntityConfig`, edit `Waves`, `CountMultiplier`, caps
   and `FallbackTargets`.
6. **Weapons**: add a `MechSentinelHitCapsuleComponent` to projectiles, or call
   `ApplyDamageToSentinelsInCapsule` from abilities / melee (server).
7. Play as **listen server + clients** (or a dedicated server). Standalone works too.

---

## 2. Architecture at a glance

```
                         +-----------------------------------------------+
                         |  AMyGameMode (server only)                    |
                         |   SentinelSwarmRules  (UMechSentinelSwarmRules)|  <- global data (no DeveloperSettings)
                         +-----------------------+-----------------------+
                                                 | read on BeginPlay
                                                 v
+----------------------------+   registers   +-----------------------------------------------+
| AMechSentinelWaveSpawner   |-------------->|  UMechSentinelSwarmSubsystem (UWorldSubsystem) |
|  (level placed, replicated)|  config,      |   - rules, player targets, fallback points     |
|  waves, counts, caps       |  fallbacks    |   - template bootstrap + config validation      |
+-------------+--------------+               |   - GAS bridge  ----------------------------+  |
              | SpawnEntities                |   - capsule collision hash + queries        |  |
              v                              +---------------^--------------------+--------+--+
+-------------------------------------------------------+    | hits / effects     | Load/Apply/
|                MASS ENTITY  (all sentinel data)        |    |                    | ReadBack
|  fragments: transform, velocity, attributes, state,    |    |                    v
|             target, attack, GAS (tags + effects)       |  +-+-----------------------------+
|  shared:    targeting board, movement speed            |  | AMechSentinelGASProxy (server) |
|  processors: effects, targeting, steering, avoidance,  |  |  ASC + MechSentinelAttributeSet|
|              forces, movement, orientation, attack,    |  |  ExecCalc_SentinelDamage       |
|              death, collision hash, visuals, smoothing |  |  (combat math only, no storage)|
+---------+-----------------------------+---------------+  +--------------------------------+
          |                             |
          | UMassReplicationProcessor   | UMassUpdateISMProcessor_Copy
          | + UMechSentinelReplicator   | (where frames are rendered)
          v                             v
+----------------------------+   +-----------------------------------------+
| AMechSentinelClientBubble- |   | AMassVisualizer_Copy                     |
| Info (one per client)      |   |  UMassVisualizationComponent_Copy        |
|  fast array of agents      |   |   UInstancedStaticMeshComponent per mesh |
+-------------+--------------+   +-----------------------------------------+
              | network
              v
   client: bubble spawns / updates / destroys client entities -> smoothing -> ISM
```

**Who owns what**

| Concern | Owner |
|---|---|
| Health, MaxHealth, Armor, AttackDamage, AttackSpeed, MoveSpeedMultiplier (per entity) | Mass `FMechSentinelAttributesFragment` |
| MovementSpeed (shared by the whole swarm group) | Mass shared fragment `FMechSentinelSharedAttributesFragment` |
| Active buffs / debuffs / stun / shield, owned gameplay tags | Mass `FMechSentinelGASFragment` (stored), GAS (evaluated) |
| Damage math, armor mitigation, Shielded / Dead rules, modifiers, tag requirements | GAS (`AMechSentinelGASProxy`, `ExecCalc_SentinelDamage`, `UMechSentinelAttributeSet`) |
| Movement, avoidance, LOD, representation, collision queries, scale | Mass |
| Stunned / Dead / Attacking | Gameplay tags in GAS, mirrored as Mass tags for queries |

---

## 3. Folder and file map

```
Source/Aura/{Public,Private}/MechSwarm/
|
+-- Core/
|   MechSwarmProcessorGroups.h      processor group names (Combat, LODCollector, Representation)
|   MechSentinelSwarmRules.h        UMechSentinelSwarmRules: global rules (data asset, referenced by AMyGameMode)
|   MechSentinelSwarmSubsystem.h/.cpp  the hub: rules, targets, templates, GAS bridge, collision hash
|
+-- Sentinel/
|   MechSentinelFragments.h         every sentinel fragment, tag and shared fragment
|   MechSentinelTrait.h/.cpp        "Mech Sentinel" trait
|   MechSentinelProcessors.h        declarations of the sentinel processors
|   MechSentinelBehaviorProcessors.cpp   effects, target selection, steering
|   MechSentinelCombatProcessors.cpp     attack, death, collision hash
|   MechSentinelClientProcessors.cpp     visual data (ISM custom data), net smoothing
|
+-- GAS/
|   MechSentinelTags.h/.cpp         State.Sentinel.{Stunned,Shielded,Dead,Attacking}, Unit.Sentinel
|   MechSentinelAttributeSet.h/.cpp attributes + IncomingDamage meta attribute
|   ExecCalc_SentinelDamage.h/.cpp  armor mitigation
|   MechSentinelGASProxy.h/.cpp     flyweight ASC actor (server)
|
+-- Replication/
|   MechSentinelReplicatedAgent.h/.cpp   compact snapshot + fast array item
|   MechSentinelClientBubble.h/.cpp      bubble handler, serializer, bubble info actor
|   MechSentinelReplicator.h/.cpp        server: fragments -> bubbles
|
+-- Spawning/
|   MechSentinelWaveSpawner.h/.cpp  replicated wave spawner
|
+-- Combat/
|   MechSentinelCombatLibrary.h/.cpp        capsule / sweep queries and hit functions (BP + C++)
|   MechSentinelHitCapsuleComponent.h/.cpp  drop-in hit capsule for projectiles / melee
|
+-- Tentacles/                      Niagara ribbon tentacles (client / standalone visuals only)
|   MechSentinelTentacleTypes.h     FMechSentinelTentacleDesc, tentacle fragment, set index, Niagara parameter names
|   MechSentinelTentacleTrait.h/.cpp      "Mech Sentinel Tentacles (Niagara)" trait
|   MechSentinelTentacleSubsystem.h/.cpp  rig pool per set, socket layout, Niagara component + array upload
|   MechSentinelTentacleProcessor.h/.cpp  budget, verlet chains, far-mesh fallback flag
|
+-- MassCopies/                     project-owned versions of engine Mass classes (*_Copy)
    MassMovementFragments_Copy.h, MassMovementProcessors_Copy.h/.cpp, MassMovementTrait_Copy.h/.cpp
    MassAvoidanceFragments_Copy.h, MassAvoidanceProcessors_Copy.h/.cpp, MassAvoidanceTrait_Copy.h/.cpp
    MassSmoothOrientation_Copy.h/.cpp
    MassLODFragments_Copy.h/.cpp
    MassRepresentationFragments_Copy.h, MassRepresentationProcessors_Copy.h/.cpp
    MassRepresentationSubsystem_Copy.h/.cpp, MassVisualizationComponent_Copy.h/.cpp
    MassVisualizer_Copy.h/.cpp, MassVisualizationTrait_Copy.h/.cpp

Also touched: Public/MyGameMode.h (SentinelSwarmRules), Aura.Build.cs (Mass modules), Aura.uproject (MassGameplay).

SourceArt/MechSentinel/            low-poly model source (Blender 5.x, procedural, see section 15)
    build_mech_sentinel.py         entry point: build, export FBX, verify, save .blend, render previews
    mech_sentinel_{common,head,tentacle}.py
    ue_import_mech_sentinel.py     editor script: import the FBX files, create the tentacle material
    Export/*.fbx, Previews/*.png, MechSentinel.blend
```

---

## 4. Structural dependencies

Arrows read "uses / depends on". Engine pieces are in `[brackets]`.

```
                               [MassEntity / MassCore / MassCommon / MassSpawner / MassLOD / MassReplication]
                                                        ^
        +-----------------------------------------------+-----------------------------------------+
        |                        |                      |                     |                   |
  MassCopies/*_Copy        Sentinel/*            Replication/*           Spawning/*          Combat/*
  (movement, avoidance,    fragments, trait,     agent, bubble,          wave spawner        library,
   orientation, LOD,       processors            replicator                                  hit component
   representation)              |                      |                     |                   |
        ^                       |                      |                     |                   |
        +--- velocity / desired movement / custom movement tag / custom data used by Sentinel ---+
                                |                      |                     |                   |
                                v                      v                     v                   v
                        Core/MechSentinelSwarmSubsystem  <----------------------------------------+
                          |            |           |
                          |            |           +--> Replication/MechSentinelClientBubble (registers bubble class)
                          |            +--> GAS/MechSentinelGASProxy --> GAS/MechSentinelAttributeSet
                          |                                     \------> GAS/ExecCalc_SentinelDamage --> Core/Rules
                          +--> Core/MechSentinelSwarmRules  <-- AMyGameMode (owns the asset reference)
                          +--> [GameplayAbilities], Interfaces/MyCombatInterface (skip dead players)

  GAS/* --> AbilitySystem/Data/MyGameplayTags (MyTags::SetDamageByCaller), AbilitySystem/MyAttributeSet (proxy source set)
```

Include rules that keep it acyclic:
* Fragments (`MechSentinelFragments.h`) depend on nothing but Mass and GameplayTags.
* Processors talk to the world only through `UMechSentinelSwarmSubsystem`.
* The subsystem knows the proxy, the bubble class and the spawner type; none of them include each other's headers
  except where they call into the subsystem.

---

## 5. What a sentinel entity is made of

```
 Trait                      Adds (per entity)                         Adds (shared / const shared)            Tags
 -------------------------  ----------------------------------------  --------------------------------------  ---------------------------
 Mech Sentinel              FTransformFragment                        FMechSentinelParameters (const)         FMechSentinelTag
                            FMechSentinelAttributesFragment           FMechSentinelSharedAttributesFragment   (runtime: Attacking,
                            FMechSentinelGASFragment                  FMechSentinelTargetingSharedFragment     Stunned, Dead)
                            FMechSentinelStateFragment                  (= the shared target board)
                            FMechSentinelTargetFragment
                            FMechSentinelAttackFragment
                            FMechSentinelNetSmoothingFragment (clients only)
 Movement (Copy)            FMassVelocityFragment_Copy                FMassMovementParameters_Copy (const)    FMassCodeDrivenMovementTag_Copy
                            FMassForceFragment_Copy                                                           (runtime: CustomMovement_Copy
                            FMassDesiredMovementFragment_Copy                                                  when dead)
 Avoidance (Copy)           -                                         FMassMovingAvoidanceParameters_Copy
 Smooth Orientation (Copy)  -                                         FMassSmoothOrientationParameters_Copy
 Visualization ISM (Copy)   FMassViewerInfoFragment_Copy              FMassVisualizationLODParameters_Copy    FMassVisualizationTag_Copy
  (not on dedicated server) FMassRepresentationLODFragment_Copy       FMassRepresentationParameters_Copy
                            FMassRepresentationCustomDataFragment_Copy
 Replication (engine)       NetworkID, ReplicatedAgent, viewer info,  FMassReplicationParameters (const)
  (not in standalone)       replication LOD, grid cell, template ID   FMassReplicationSharedFragment
```

Shared fragments are unique per value of their `UPROPERTY` fields. `SwarmGroup` is such a field, so every swarm group
gets its **own** targeting board and its own movement speed. Two spawners whose configs share a group share a board.

---

## 6. One frame, step by step

### Server / standalone (authority)

```
 PrePhysics phase
 ----------------
 [Behavior]   UMechSentinelEffectsProcessor          tick effect durations; expired -> RecomputeSentinel (GAS)
      |       UMechSentinelTargetSelectionProcessor  refresh boards (players, fallbacks) -> count claims -> assign
      v
 [Tasks]      UMechSentinelSteeringProcessor         target -> desired velocity / facing (orbit, arrive, wobble, sink if stunned)
      v
 [Avoidance]  UMassMovingAvoidanceProcessor_Copy     spatial hash (cells sized to the prediction reach) -> force
      v
 [ApplyForces] UMassApplyForceProcessor_Copy         clamp desired velocity (speed / vertical); drop force if not code driven
      v
 [Movement]   UMassApplyMovementProcessor_Copy       velocity -> desired (accel limited), velocity += force * dt,
                                                     force reset, speed clamp, location += v * dt
              UMassSmoothOrientationProcessor_Copy   slerp to facing / velocity, pitch clamp, banking
      v
 [MechSwarm.Combat]
              UMechSentinelAttackProcessor           enter / leave attack state, cooldown, apply attack GE to player
              UMechSentinelDeathProcessor            wreck falls (gravity, ground trace, tumble), destroy at timeout
              UMechSentinelCollisionHashProcessor    rebuild capsule hash for hit queries

 PostPhysics phase
 -----------------
 [engine]     UMassReplicationProcessor (+ UMechSentinelReplicator)   server with clients only
 [MechSwarm.LODCollector]   UMassLODCollectorProcessor_Copy           standalone / listen server (Client flag)
 [MechSwarm.Representation] UMassVisualizationLODProcessor_Copy
                            UMechSentinelVisualDataProcessor          state / health / flash / glow -> custom data
                            UMechSentinelTentacleProcessor            ribbon budget, verlet chains -> Niagara arrays
                            UMassUpdateISMProcessor_Copy              transforms + custom data -> ISM
 [Niagara, ForceTickLast]   NS_MechSentinelTentacles                  one ribbon per chain, built from this frame's arrays
```

### Network client

```
 network receive  -> FMechSentinelClientBubbleHandler: spawn / update / destroy client entities, store net samples
 PrePhysics       -> UMechSentinelNetSmoothingProcessor: ease toward sample + velocity * (time since sample)
 PostPhysics      -> LODCollector_Copy -> VisualizationLOD_Copy -> VisualData -> Tentacles -> UpdateISM_Copy
```

Clients never run behaviour, movement or combat (those processors are `Standalone | Server`); the smoothing fragment
only exists on `NM_Client`, so a listen server renders its own simulation directly.

---

## 7. Targeting through the shared fragment

```
             UMechSentinelSwarmSubsystem                    per swarm group: FMechSentinelTargetingSharedFragment
   +-------------------------------------------+          +---------------------------------------------------+
   | GatherPlayerTargets(): alive player pawns  |  ----->  | PlayerSlots[]   {actor, location, claims, capacity}|
   | GetFallbackTargets(group): spawner points  |  ----->  | FallbackSlots[] {actor/location, claims, capacity} |
   +-------------------------------------------+          | BoardSerial (bumped when the slot set changes)     |
                                                           +-------------------------+-------------------------+
                                                                                     | shared by every sentinel
                                                                                     v
   each sentinel (FMechSentinelTargetFragment): PlayerSlot | FallbackSlot, TargetLocation, OrbitDirection, RetargetTimer

   assignment, when the timer runs out / the board changed / the player is over capacity:
     1. nearest player with room (capacity = rules MaxAttackersPerPlayer; current target gets a stickiness bonus)
     2. otherwise nearest fallback point with room (per point Capacity, 0 = unlimited)
     3. otherwise the least crowded player within range (never idle while players are reachable)
```

A player only counts as "over capacity" when another player or fallback point actually has room, so sentinels do not
bounce between equally crowded players. Fallback points that follow an actor are held weakly: when the actor is
destroyed the point is dropped from the board (the board serial changes and its claimers retarget).

Claims are recounted from scratch every frame (pass 2) before anyone is reassigned (pass 3), so the counts are exact
even when sentinels die, players leave or the board changes.

---

## 8. Combat data flow (GAS logic, Mass storage)

### A hit on a sentinel

```
 projectile / ability / melee                         (server)
        |
        | UMechSentinelHitCapsuleComponent  or  UMechSentinelCombatLibrary::ApplyDamageToSentinelsInCapsule
        v
 QueryCapsule(segment, radius) on the subsystem's spatial hash   --> FMechSentinelHit[] (handle, impact point, distance)
        |
        | MakeSentinelDamageSpec: GE (or rules default), SetByCaller SetDamageByCaller = damage, instigator's ASC as source
        v
 UMechSentinelSwarmSubsystem::ApplyGameplayEffectSpecToSentinel(entity, spec)
        |
        |  pass 1  Proxy.LoadEntity  : Mass attributes -> attribute BASE values, re-apply stored duration effects
        |          Proxy.ApplySpec   : GAS runs the effect
        |                                ExecCalc_SentinelDamage: Armor (captured), Shielded, Dead -> IncomingDamage
        |                                UMechSentinelAttributeSet::PostGameplayEffectExecute: IncomingDamage -> Health
        |          Proxy.ReadBack    : bases + currents + owned tags -> Mass
        |          Proxy.Unload      : remove every temporary effect / loose tag (proxy is blank again)
        |  pass 2  (only if a duration effect was stored) Load / ReadBack / Unload to re-evaluate currents
        v
 Mass: FMechSentinelAttributesFragment, FMechSentinelGASFragment updated
        | HitFlash = 1, ++HitSerial, OnSentinelDamaged
        v
 SyncStateFromGAS: Health <= 0 -> Dead (state, gameplay tag, Mass tags Dead + CustomMovement_Copy), OnSentinelKilled
                   Stunned tag -> Stunned state + Mass tag
        |
        v
 replication: HitSerial / HealthByte / State changes are sent immediately -> clients flash
```

Armor formula (all in `ExecCalc_SentinelDamage`, constants in the rules):

```
 mitigation = k * Armor / (1 + k * |Armor|)        k = ArmorMitigationPerPoint (0.06)
 damage     = raw * (1 - mitigation)               armor 10 -> 37.5% less, armor 50 -> 75% less, negative armor amplifies
 Shielded   : damage *= ShieldedDamageMultiplier (0.25)
 Dead       : damage  = 0
```

### A sentinel attacking a player

```
 UMechSentinelAttackProcessor (in range, cooldown <= 0)
   -> ++AttackSerial, AttackGlow = 1
   -> after the chunk loop: spec of rules SentinelAttackEffect from the proxy ASC,
      SetByCaller SetDamageByCaller = the sentinel's AttackDamage (buffs included), context with origin + hit result
   -> ApplyGameplayEffectSpecToTarget(player ASC)   (the project's normal player damage pipeline takes over)
```

---

## 9. Replication data flow

```
 SERVER                                                                   CLIENT
 ------                                                                   ------
 UMassReplicationProcessor (engine, PostPhysics)
   per client: replication LOD (distance / counts from the Replication trait)
     |
     v
 UMechSentinelReplicator::ProcessClientReplication
   AddEntity    : FMechSentinelReplicatedData::FromEntity -> bubble.AddAgent
   ModifyEntity : movement throttled by UpdateInterval[LOD];
                  state / health / hit / attack changes sent at once      FMechSentinelClientBubbleHandler
   RemoveEntity : bubble.RemoveAgentChecked                                PostReplicatedAdd   : make sure the template
 UMechSentinelReplicationDestroyObserver                                                 exists, spawn entities,
   entity destroyed -> bubble.RemoveAgent for every client that had it                   apply snapshot (snap)
     |
     v
 AMechSentinelClientBubbleInfo (owned by the PlayerController)            PostReplicatedChange: apply snapshot
   FMechSentinelClientBubbleSerializer : fast array of           ----->   PreReplicatedRemove : destroy entities
   FMechSentinelFastArrayItem { NetID, TemplateID, Data }
                                                                          UMechSentinelNetSmoothingProcessor
 Data (~22 bytes): Position (0.1 cm), Velocity (1 cm/s),                    -> transform eases toward the samples
   Yaw/Pitch/Roll (16 bit), State, HealthByte, HitSerial, AttackSerial     UMechSentinelVisualDataProcessor
                                                                            -> flashes on serial changes
 AMechSentinelWaveSpawner: CurrentWaveNumber (RepNotify), WaveState, AliveCount, RemainingToSpawn (always relevant)
```

Why it works on clients:
* Entities destroyed on the server are removed from every client bubble by `UMechSentinelReplicationDestroyObserver`
  in the same frame. The engine only removes agents of entities it still finds in a client's range; when a whole wave
  in range dies in one frame it would otherwise leave stale agents and hit its cleanup assert.
* The bubble info class is registered in `UMechSentinelSwarmSubsystem::Initialize`, before any template is built and
  before any client connects (the engine asserts otherwise).
* The entity template ID depends only on the config asset, so server and client agree. Clients build it from the
  level-placed spawner (`PostInitializeComponents`). If an agent still arrives first, the bubble builds missing templates;
  agents whose template is unknown are postponed instead of asserting, and spawned on their next update.
* `NM_ListenServer` counts as both Client and Server for processors: the host simulates, replicates and renders.

---

## 10. Waves

```
  Idle --StartWaves--> Countdown(DelayBefore) --> Spawning (SpawnDuration, SpawnBatchSize per frame, caps)
                            ^                          |
                            |                          v
                            +--- advance <------- Fighting --(last wave cleared, no repeat)--> Finished
                    WhenCleared | OnTimer(TimeLimit) | ClearedOrTimer
```

Amount control:
* `Waves[i].Count` per wave, `SetWaveCount(i, n)` at runtime.
* `CountMultiplier` scales every wave (`SetCountMultiplier`, also re-plans the wave being spawned).
* Endless mode: `bRepeatLastWave`, `+ExtraCountPerRepeat` sentinels and `x StatScalePerRepeat` health / armor / damage per repeat.
* Caps: `MaxAlive` per spawner, `MaxAliveSentinels` in the rules (soft global cap).
* Pacing: `SpawnDuration`, `SpawnBatchSize`, `DelayBefore`, `TimeLimit`.
* Per-wave stat multipliers scale the trait's attribute defaults at spawn.
* `SpawnSentinelsNow(n)`, `StartNextWave()`, `StopWaves()`, `DespawnAll(bKill)`.
* Events: `OnWaveStarted(wave, count)` (server + clients), `OnWaveCleared(wave)` (server).

The spawner also registers its `FallbackTargets` (and itself, when `bSpawnerIsFallbackTarget`) for its swarm group.

---

## 11. Hitting sentinels from actors (the capsule function)

Sentinels are Mass entities, not physics bodies, so engine traces do not hit them. Each sentinel has a simple capsule
(`CapsuleRadius`, `CapsuleHalfHeight` in the trait parameters) along its forward axis, stored every frame in a spatial
hash by `UMechSentinelCollisionHashProcessor`. Queries are segment-to-segment distance tests (`FMath::SegmentDistToSegmentSafe`).

```cpp
// Server. Damages every sentinel whose capsule touches this capsule (UE convention: axis = Rotation's up vector).
TArray<FMechSentinelHit> Hits;
float TotalDamage = 0.f;
UMechSentinelCombatLibrary::ApplyDamageToSentinelsInCapsule(this, InstigatorPawn,
    Center, Rotation, /*Radius*/ 40.f, /*HalfHeight*/ 90.f, /*Damage*/ 30.f,
    /*DamageEffect (null = rules default)*/ nullptr, /*MaxTargets (0 = all)*/ 0, Hits, TotalDamage);
```

Also available (all Blueprint callable): `FindSentinelsInCapsule`, `SweepSentinels`, `ApplyDamageToSentinelsInSweep`,
`ApplyEffectToSentinelsInCapsule` (stun, shield, slow...), `ApplyDamageToSentinel`, `ApplyGameplayEffectSpecToSentinel`,
`GetSentinelInfo`, `IsSentinelAlive`. Subsystem events: `OnSentinelDamaged`, `OnSentinelKilled`.

`UMechSentinelHitCapsuleComponent` wraps this for projectiles: every server tick it tests its capsule plus the path
since last frame (no tunnelling), hits each sentinel once, supports piercing (`MaxSentinelsHit`), extra effects,
and destroys its owner when spent.

---

## 12. ISM representation and the material

`UMassUpdateISMProcessor_Copy` feeds one `UInstancedStaticMeshComponent` per mesh (high and low LOD) owned by
`AMassVisualizer_Copy` at the world origin. Instances are tracked per entity id: entities that stop being submitted
(destroyed, LOD Off) lose their instance automatically. Dedicated servers create no visuals.

Per-instance custom data written by `UMechSentinelVisualDataProcessor`:

| Index | Value | Material idea |
|---|---|---|
| 0 | state: 0 Seeking, 1 Attacking, 2 Stunned, 3 Dead | eye colour (red when attacking, flicker when stunned, off when dead) |
| 1 | health fraction 0..1 | damage tint / sparks |
| 2 | hit flash 1 -> 0 in ~0.25 s | white additive flash |
| 3 | attack glow 1 -> 0 in ~0.4 s | emissive pulse / beam |

Read them with `PerInstanceCustomData` (index 0..3) in the material and enable "Used with Instanced Static Meshes".
For the reference image's mood: dark metal, emissive red eyes (material slot 1 of the head, `MI_MechSentinel_Eyes`),
Niagara ribbon tentacles near the camera ([section 15](#15-sentinel-model-and-niagara-ribbon-tentacles)), plus a light
cone in the level.

`FMassRepresentationLODFragment_Copy::bForceLowLODMesh` (a project addition) makes the ISM use the low mesh even at
High / Medium LOD. The tentacle processor sets it on every sentinel that has no ribbons, so those are drawn with the
far mesh, which has the tentacles baked in.

---

## 13. _Copy classes and their engine counterparts

The task asked to use the default Mass fragments / processors but copy them under `originalName_Copy`. The engine
code is not pasted (the repository is public and engine code falls under the Unreal Engine EULA); each `_Copy` is a
project-owned implementation with the same role and data, written for this swarm.

| Project class (`MechSwarm/MassCopies`) | Engine counterpart (role) |
|---|---|
| `FMassVelocityFragment_Copy` | `FMassVelocityFragment` (MassMovement) |
| `FMassForceFragment_Copy` | `FMassForceFragment` |
| `FMassDesiredMovementFragment_Copy` | `FMassDesiredMovementFragment` |
| `FMassCodeDrivenMovementTag_Copy` | `FMassCodeDrivenMovementTag` |
| `FMassCustomMovementTag_Copy` | project helper: "someone else owns the position" (death fall) |
| `FMassMovementParameters_Copy` | `FMassMovementParameters` |
| `UMassApplyForceProcessor_Copy` | `UMassApplyForceProcessor` |
| `UMassApplyMovementProcessor_Copy` | `UMassApplyMovementProcessor` |
| `UMassMovementTrait_Copy` | `UMassMovementTrait` |
| `FMassMovingAvoidanceParameters_Copy` | `FMassMovingAvoidanceParameters` (MassNavigation) |
| `UMassMovingAvoidanceProcessor_Copy` | `UMassMovingAvoidanceProcessor` (3D, no navmesh / zone graph) |
| `UMassObstacleAvoidanceTrait_Copy` | `UMassObstacleAvoidanceTrait` |
| `FMassSmoothOrientationParameters_Copy`, `UMassSmoothOrientationProcessor_Copy`, `UMassSmoothOrientationTrait_Copy` | smooth orientation parameters / processor / trait (with pitch and banking for flyers) |
| `FMassViewerInfoFragment_Copy`, `UMassLODCollectorProcessor_Copy` | `FMassViewerInfoFragment`, `UMassLODCollectorProcessor` (MassLOD) |
| `FMassRepresentationLODFragment_Copy`, `FMassVisualizationLODParameters_Copy`, `UMassVisualizationLODProcessor_Copy` | representation LOD fragment / parameters / processor |
| `FStaticMeshInstanceVisualizationDesc_Copy`, `FMassRepresentationParameters_Copy` | `FStaticMeshInstanceVisualizationDesc`, `FMassRepresentationParameters` |
| `FMassRepresentationCustomDataFragment_Copy` | per-instance custom data floats |
| `FMassVisualizationTag_Copy` | marks visualized entities |
| `UMassRepresentationSubsystem_Copy`, `AMassVisualizer_Copy`, `UMassVisualizationComponent_Copy` | `UMassRepresentationSubsystem`, `AMassVisualizer`, `UMassVisualizationComponent` |
| `UMassUpdateISMProcessor_Copy`, `UMassVisualizationTrait_Copy` | `UMassUpdateISMProcessor`, `UMassVisualizationTrait` |

Used from the engine as-is (no copy needed): `FTransformFragment`, the trait / processor / query framework,
`UMassEntityConfigAsset`, `UMassSpawnerSubsystem`, and the whole MassReplication framework (`UMassReplicationProcessor`,
the Replication trait, client bubble base classes), which the custom agent / bubble / replicator plug into.

---

## 14. Design choices, deviations and limitations

* **One GAS proxy instead of one ASC per entity.** Thousands of ASCs would defeat Mass. The proxy loads one sentinel,
  runs real GAS (execs, modifiers, tag requirements, immunity, stacking), writes the result back to Mass and unloads.
  Cost is paid only on combat events, not per frame.
* **Duration / infinite effects** are stored on the entity (`FMechSentinelGASFragment::ActiveEffects`: class, level,
  remaining time, SetByCaller values) and re-applied on the proxy when the entity is evaluated. Re-applying the same
  class refreshes it. Limitations: periodic effects are not persisted (a warning is logged; apply an instant effect
  repeatedly for damage over time), MaxHealth is base-only, and GE "application" side effects (cues, ability grants,
  execution of on-application components) of stored effects re-run each time the proxy reloads them. Cues are suppressed
  on the proxy; sentinel visuals come from Mass.
* **Players as source of sentinel attacks**: the proxy ASC is the source. It carries a default `UMyAttributeSet` so the
  project's `ExecCalc_Damage` can capture source attributes (CritChance = 0).
* **Targeting is server side**; clients only see positions and states.
* **Replication**: positions are throttled by replication LOD, discrete events are immediate. Bandwidth grows with the
  number of relevant sentinels per client: tune the Replication trait LOD distances / max counts and `MaxAliveSentinels`
  for your player count. Clients have no hit queries (the collision hash is built on the server only).
* **The global alive cap is soft**: it uses the alive count of the last collision-hash rebuild plus what a spawner created
  this frame, so several spawners in the same frame can overshoot by a batch.
* **Wrecks**: dead sentinels fall with gravity, stop on WorldStatic geometry (one line trace per falling wreck per frame),
  tumble and are destroyed after `DeathFallDuration`.
* **Avoidance** is entity-entity only (3D separation with prediction, applied as an acceleration on the velocity after the
  steering approach, so it is not cancelled by the acceleration limit). There is no level-geometry avoidance for live
  sentinels; keep the play space open or add fallback points away from walls.
* **Movement speed** is a shared fragment per swarm group (change it with `SetSwarmMovementSpeed`), scaled per entity by
  the `MoveSpeedMultiplier` attribute (slows / hastes through GAS).
* **No DeveloperSettings**: global data is the rules asset referenced by the GameMode, runtime state is in the world subsystem.

---

## 15. Sentinel model and Niagara ribbon tentacles

### The model (SourceArt/MechSentinel)

![hero](SourceArt/MechSentinel/Previews/hero.png)

The low-poly sentinel is built procedurally in Blender (no hand edits, so it can be tweaked and rebuilt):

```
<python with bpy> SourceArt/MechSentinel/build_mech_sentinel.py --out SourceArt/MechSentinel [--no-render] [--quick]
blender -b -P SourceArt/MechSentinel/build_mech_sentinel.py -- --out SourceArt/MechSentinel
```

| Asset | Triangles | What it is |
|---|---|---|
| `SM_MechSentinel_Head` | 1212 | 2.36 m long armoured head: overlapping carapace plates, 8 red eye lenses (slot 1), mandibles, ribbed rear collar with 8 tentacle ports and sockets `Tentacle_00..07`. No tentacles. Fits the 70 / 140 cm hit capsule. |
| `SM_MechSentinel_Far` | 844 | simplified head with 8 baked trailing tentacles (1.9 m): Low LOD and the "no ribbons" fallback |
| `SM_MechSentinel_Tentacle` | 654 | one straight tentacle: 11 armoured 18 cm sleeves + 3-prong claw (look reference for the ribbon material) |
| `SM_MechSentinel_TentacleTip` | 126 | the claw alone, base at the origin, pointing +X (optional mesh renderer at the ribbon tips) |

Material slots: `[0] MI_MechSentinel_Body`, `[1] MI_MechSentinel_Eyes`. Units are meters in Blender and come in as cm;
the nose points +X and the origin is the head centre (the entity location). The build script re-imports every FBX
and checks triangle counts, size, slots and sockets.

### How the tentacles work

```
 Mass (PostPhysics, client / standalone / listen server)                      Niagara (ForceTickLast)
 ---------------------------------------------------------                    ------------------------------------
 UMassVisualizationLODProcessor_Copy  -> LOD per sentinel
 UMechSentinelTentacleProcessor
   pass 1: wants ribbons = LOD High/Medium and distance < MaxDistance
   budget: closest MaxRiggedSentinels keep / get a rig (owners get a bonus)
   pass 2: no rig -> bForceLowLODMesh (ISM draws SM_MechSentinel_Far)
           rig    -> 8 chains x 12 points, 18 cm apart:                       NS_MechSentinelTentacles
                       root = head socket Tentacle_XX (follows the head)        TentacleCount * PointsPerTentacle
                       verlet inertia + drag + gravity                          particles, never die
                       pull toward a trailing pose (soft at the tip)            particle i: ribbon = i / Points
                       swimming wave root -> tip, faster when attacking         link order = i % Points
                       limp when dead, re-laid out on teleport                  position = TentaclePositions[i]
                       length constraint (never stretches)                      width = lerp(Root, Tip) * WidthScale
 UMechSentinelTentacleSubsystem::EndFrame                                      tube ribbon, M_MechSentinelTentacle
   free rigs of destroyed sentinels, upload arrays,  ------------------->     claw mesh on the last point (optional)
   fixed bounds = this frame's points
 UMassUpdateISMProcessor_Copy -> head (SM_MechSentinel_Head) or far mesh
```

Everything is client side visuals: nothing replicates, dedicated servers add nothing. One Niagara component per tentacle
set (one set per distinct trait description) draws every rigged sentinel, so the cost is one CPU emitter of
`MaxRiggedSentinels * NumTentacles * PointsPerTentacle` particles (48 x 8 x 12 = 4608 by default) plus 400 ribbons.

### Building NS_MechSentinelTentacles (about 10 minutes in the editor)

1. Content Browser > Niagara System > **New system from selected emitter(s)** > **Empty**. Name it
   `NS_MechSentinelTentacles`. Open it and select the emitter.
2. **User parameters** (Parameters panel > User Exposed > +). Names must match exactly:
   | Name | Type | Default |
   |---|---|---|
   | `TentaclePositions` | Niagara **Position Array** | empty |
   | `TentacleWidthScale` | Niagara **Float Array** | empty |
   | `TentacleGlow` | Niagara **Float Array** | empty |
   | `PointsPerTentacle` | int32 | 12 |
   | `TentacleCount` | int32 | 384 |
   | `RootWidth` | float | 18 |
   | `TipWidth` | float | 3.5 |
3. **Emitter Properties**: Sim Target **CPUSim**, Local Space **off**, Calculate Bounds Mode **Fixed** (the code sets the
   system's fixed bounds every frame).
4. **Emitter State**: Life Cycle Mode Self, Loop Behavior **Once**, Loop Duration Mode **Infinite**.
5. **Emitter Update**: remove Spawn Rate, add **Spawn Burst Instantaneous**, Spawn Time 0, Spawn Count =
   `TentacleCount * PointsPerTentacle` (dynamic input *Multiply Int*, both inputs linked to the user parameters).
6. **Particle Spawn**: keep Initialize Particle only (lifetime does not matter). **Particle Update**: remove *Particle State*
   (particles must never die) and add a **new Scratch Pad Module** `MechTentacleFromArrays`:
   * Module inputs: `Positions` (Position Array), `WidthScale` (Float Array), `Glow` (Float Array), `PointsPerTentacle`
     (int), `RootWidth`, `TipWidth` (float), `GlowColor` (Linear Color, e.g. 1, 0.06, 0.02). Link them to the user
     parameters on the module stack.
   * Graph (Map Get -> math -> Map Set):
     ```
     Index     = Particles.UniqueID                          (int)
     Ribbon    = Index / PointsPerTentacle                   (int divide)
     Link      = Index - Ribbon * PointsPerTentacle          (int)
     T         = float(Link) / float(PointsPerTentacle - 1)
     Particles.Position        = Positions.Get(Index)        (Array "Get" node)
     Particles.Velocity        = Positions.Get(Index) - Positions.Get(Index - 1)   (direction for the claw mesh)
     Particles.RibbonID        = Ribbon                      (int)
     Particles.RibbonLinkOrder = float(Link)
     Particles.RibbonWidth     = lerp(RootWidth, TipWidth, T) * WidthScale.Get(Ribbon)
     Particles.Color           = (GlowColor.rgb, Glow.Get(Ribbon) * T^4 * 30)
     Particles.VisibilityTag   = Link == PointsPerTentacle - 1 ? 1 : 0             (claw mesh only on the tip)
     Particles.MeshScale       = (1,1,1) * WidthScale.Get(Ribbon)
     ```
7. **Ribbon Renderer**: Material `M_MechSentinelTentacle`; Shape **Tube**, Tube Subdivisions **6**; bindings
   Ribbon Id = `Particles.RibbonID`, Ribbon Link Order = `Particles.RibbonLinkOrder`, Ribbon Width = `Particles.RibbonWidth`;
   UV0 distribution *Scaled Uniformly* (U runs 0 -> 1 from the root; if the sleeve bands taper the wrong way, add a
   OneMinus on U in the material).
8. Optional claw tips: add a **Mesh Renderer** with `SM_MechSentinel_TentacleTip`, Facing Mode **Velocity**,
   Renderer Visibility tag 1 bound to `Particles.VisibilityTag`.
9. System properties: no Effect Type distance culling (the component sits at the world origin). Save.
10. On the entity config add the **Mech Sentinel Tentacles (Niagara)** trait and set Niagara System to it.

Tuning: `MaxDistance` should be close to the Medium LOD distance of the visualization trait (beyond it the far mesh is
used anyway); raise `MaxRiggedSentinels` for big close swarms. The roots come from the head mesh sockets `Tentacle_XX`
(moved sockets are picked up), with a built-in ring identical to the Blender layout when they are missing.

Limitations: the chains do not collide with the level; ribbons swap to the baked far mesh without a blend when a
sentinel leaves the budget; tentacle physics restarts from the rest pose when a sentinel gets a rig.
