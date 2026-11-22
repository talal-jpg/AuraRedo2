# Burrower C++: notes for the editor session

Clone: `/home/claude/AuraRedo2`, branch `claude/project-thread-78otz4` (not committed). Nothing was compiled: no
Unreal Engine or engine headers in the container. Engine APIs used are old, stable ones. Where I relied on memory,
the API is listed under "Unsure" below.

## Files

New:
* `Source/Aura/Public/Burrower/BurrowerSettings.h`. Header only, like the project's other UDeveloperSettings
  (MyHexBridgeSettings, MyHexMinimapSettings have no .cpp).
* `Source/Aura/Public/Burrower/BurrowerCharacter.h` + `Source/Aura/Private/Burrower/BurrowerCharacter.cpp`
* `Source/Aura/Public/Burrower/BurrowerAnimInstance.h` + `Source/Aura/Private/Burrower/BurrowerAnimInstance.cpp`
* `Source/Aura/Public/Burrower/BurrowerSpawnSubsystem.h` + `Source/Aura/Private/Burrower/BurrowerSpawnSubsystem.cpp`
* No `ABurrowerAIController`. A plain `AAIController` possesses the Burrower, and the steering lives in the character.

Changed:
* `Source/Aura/Public/Actors/MyHexPlatform.h` / `Private/Actors/MyHexPlatform.cpp`:
  * public `int32 ActivateTilesInWorldBox(const FTransform& BoxToWorld, const FVector& BoxExtent)` and
    `bool CouldWorldBoxTouchTiles(...) const`
  * private `FBox TilesLocalBounds` (filled in `BuildTileInfos`, 2 lines)
  * a new section after `IsTileCollapsed`: namespace `HexBoxTest`, the exact hex-prism vs oriented-box SAT test.
  * This is hex_api.md section 6, copied as written. It goes through `ActivateHex`, so replication, props, bridges
    and the minimap all keep working. It does nothing before `bBridgesReady`.
* `Source/Aura/Aura.Build.cs`: `PrivateDependencyModuleNames += "AIModule"` (for `AAIController`). ControlRig is not
  needed: the C++ never touches the rig.
* `Aura.uproject`: `{"Name": "ControlRigPhysics", "Enabled": true}` right after ControlRigDynamics.

## Design (what the code does)

### UBurrowerSettings
* Project Settings > Game > Burrower. Saved to `DefaultGame.ini [/Script/Aura.BurrowerSettings]`.
* Settings: `bEnabled`, `BurrowerClass` (soft class), `AllowedMaps` (empty = every map), `FirstSpawnDelay` 10 s,
  `SpawnInterval` 30 s, `PlayerRespawnGrace` 5 s, `SpawnDistanceBehind` 3000 cm, `SpawnHeightOffset` -150 cm,
  `MinSpeedForVelocityDirection` 150 cm/s, `MaxAlivePerPlayer` 1, `bRespawnAfterDeath`, `DespawnDistance` 0 (never),
  `bOnlyCombatPawns` (only pawns with IMyCombatInterface, so menu/spectator pawns get no Burrower), `PollInterval` 0.25 s.

### UBurrowerSpawnSubsystem (UWorldSubsystem, Game + PIE worlds)
* Runs only on a listen server or standalone (OnWorldBeginPlay returns on `NM_Client` and, with a warning, on
  `NM_DedicatedServer`: there the health bar widget component creates no widget and `AMyEnemyChar::BeginPlay`
  dereferences it). It async-loads BurrowerClass and polls on a looping timer.
* Spawns (auto and SpawnNow) only where the GameMode is an `AMyGameMode` with `DA_MyEnemyCharacterClassInfo` set
  (`HasEnemyClassInfo`, one warning otherwise). The kill path dereferences it without a check.
* Polling, not delegates: every PollInterval it walks `GameState->PlayerArray`, with entries keyed by a weak
  APlayerState (the PlayerState survives respawns).
* Per entry:
  * The last living pawn. A new one counts as a respawn: the countdown becomes at least PlayerRespawnGrace, and the
    Burrowers are retargeted.
  * The living Burrowers (weak pointers).
  * A countdown, and a death count.
* Each poll, a Burrower that is dead or gone is dropped and the countdown re-arms to at least SpawnInterval. A
  Burrower beyond DespawnDistance is destroyed and re-armed the same way.
* The others get `SetTargetPlayer(livingPawn or null)`. With a null target the Burrower brakes and waits.
* The countdown runs only while the player has a living pawn, there is room under MaxAlivePerPlayer, and
  (bRespawnAfterDeath or nothing died yet). At 0 it spawns and resets to SpawnInterval. If the class is unset or not
  loaded, it retries after 1 s and logs one warning.
* Players who leave have their living Burrowers destroyed.
* Spawn location: `pawn location + behind * SpawnDistanceBehind + (0, 0, SpawnHeightOffset)`.
  * behind = against the horizontal velocity above MinSpeedForVelocityDirection, otherwise against the horizontal
    facing.
  * The Burrower spawns facing the player (yaw only).
  * `SpawnActorDeferred` with `AlwaysSpawn`, then `MarkSpawnedBySubsystem()` + `SetTargetPlayer()` before
    `FinishSpawning`.
* Console commands (not in shipping):
  * `Aura.Burrower.SpawnNow [PlayerIndex]` ignores the countdowns, bEnabled and MaxAlivePerPlayer.
  * `Aura.Burrower.KillAll` calls `Die()` on every living Burrower: the normal death path, no XP.
  * Both work only in the server's world (the listen-server window).

### ABurrowerCharacter : AMyEnemyChar (user decision)
* Ctor:
  * `CharacterClass = Warrior`, `CharacterLevel = 1`, `LifeSpan = 10`.
  * `bAlwaysRelevant = true` (only a few exist; this avoids any net-cull issue with a 20 m flyer).
  * `AutoPossessAI = PlacedInWorldOrSpawned`, `AIControllerClass = AAIController`.
  * `bUseControllerRotation* = false`.
  * CMC: DefaultLandMovementMode Flying, MaxFlySpeed 1400, MaxAcceleration 4000, BrakingDecelerationFlying 2000,
    GravityScale 0, no orient-to-movement.
* Capsule (actor location) on the head body of the physics asset (mesh (830, 0, 187)):
  * radius 160, half height 190
  * QueryOnly, object type Pawn, **ignores every channel**, no overlap events. So it flies through the tiles it cuts,
    players, and the level.
* Mesh:
  * relative location (-830, 0, -187), rotation 0 (the mesh faces +X).
  * QueryOnly, object type Pawn, ignore all, Visibility Block, WorldDynamic Overlap, PhysicsBody Overlap, overlap
    events on (per gas_patterns.md: aim traces and Electrocute/Shards use Visibility, projectiles overlap).
  * Players are not blocked by the body.
* `RotorBox` (UBoxComponent):
  * **Attached to the mesh with no socket**, at relative (977.9, 0, 180.5), the rotor centre from
    Burrower_rig_info.json. This differs from the brief ("socket/bone Rotor"), for two reasons:
    1. A server doesn't refresh the bones of a mesh it doesn't render (AlwaysTickPose), so a bone attachment goes
       stale there.
    2. The Rotor bone's local axes come from Blender, so the box extents would be on unknown axes.
  * While alive, the rig keeps the rotor at its rest place (J0_Head is not waved) and only spins it. The disc is round,
    so the box covers it.
  * Extent = RotorHalfSize (27.9, 105.8, 105.8) + RotorBoxPadding (50) on every side, applied in OnConstruction and
    BeginPlay.
  * NoCollision, no overlap events, hidden in game.
* Rotor check (server, every RotorCheckInterval = 0.05 s, from Tick; the timer keeps its remainder):
  * `TActorIterator<AMyHexPlatform>` over every platform (no physics query, so the tile collision settings don't
    matter), filtered by top/bottom, then `AMyHexPlatform::ActivateTilesInWorldBox`, which first tests the box
    against the grid's bounds and then does the exact test and the activation.
  * `bSweepRotorBox`: the box is stretched back along its X over the distance moved since the last check (jumps
    over 20 m are ignored), so fast movement can't skip a tile, and forward by the forward speed times
    max(RotorCheckInterval, DeltaTime), so a tile goes when the padded box reaches it rather than a check later.
  * `bCutTopPlatforms` / `bCutBottomPlatforms` filter the platforms.
  * CVar `Aura.Burrower.DebugRotorBox 1` draws the box on the server: green, red when it cut, yellow for the swept box.
* Follow (server Tick, `UpdateFollow`):
  * goal = target location + (0, 0, FollowHeightOffset = -150), optionally minus KeepBehindDistance along the
    target's behind direction.
  * Yaw and pitch each turn toward the goal at TurnRate (40 deg/s) at most, separately (one arc on the sphere is
    nearly all pitch for a goal behind and slightly above/below, and the pitch clamp would stall the yaw). The
    pitch goal is clamped to ±MaxPitch (25), roll 0. `SetActorRotation(heading)`, so the rotation follows the path
    (the CMC replicates it).
  * `AddMovementInput(heading, throttle)`. The throttle distance is measured from the front of the blades
    (distance to the goal minus |RotorBox centre - actor| minus RotorHalfSize.X, about 176 cm): throttle = 0 inside
    StopDistance (**0**) and ramps to 1 at SlowdownDistance (1500). So the padded box reaches past the goal and a
    player who stands still loses their tile.
  * MaxFlySpeed goes from FollowSpeed (1400) up to CatchUpSpeed (3200) between CatchUpStartDistance (3000) and
    CatchUpFullDistance (8000).
  * With no living target: no input, so the flying braking stops it.
  * Placed in a level (not spawned by the subsystem) with `bAutoTargetNearestPlayer`: it picks the nearest living
    player once a second while it has no target.
* GAS: per gas_patterns.md section 9.
  * The ASC and UMyAttributeSet come from AMyEnemyChar.
  * Server, after `Super::BeginPlay`: Primary -> Secondary -> Vital at CharacterLevel. Each comes from the per-class
    overrides (`PrimaryAttributesEffect` / `SecondaryAttributesEffect` / `VitalAttributesEffect`) or, when unset,
    from the GameMode's `DA_MyEnemyCharacterClassInfo`, with null checks.
  * Damage: the existing pipeline, unchanged.
* Health bar: AMyEnemyChar::BeginPlay dereferences the widget without a check.
  * If BP_Burrower sets no widget class, BeginPlay first sets `UMyUserWidget::StaticClass()` (empty, but no crash).
  * The component is placed at (0, 0, 400), Screen space, NoCollision.
* Death:
  * `Die()` (server) runs once only. It sets `bBurrowerDead` (replicated, for late joiners), then
    `Super::Die()` (SetLifeSpan + MulticastHandleDeath).
  * `MulticastHandleDeath_Implementation` (override only, no UFUNCTION redeclared) and `OnRep_BurrowerDead` (or
    BeginPlay when the first bunch carried it) both call `HandleBurrowerDeath()`, once per machine
    (`if (bIsDead) return`). It:
    * stops and disables movement, turns off the rotor box, hides the health bar
    * then either:
      * `bUseMeshRagdollFallback` (default **true**): mesh PhysicsOnly first, then the base
        `AMyCharBase::MulticastHandleDeath_Implementation` (SetSimulatePhysics, WorldStatic block, capsule off,
        Dissolve, bIsDead, OnDeathDelegate)
      * or (false): capsule + mesh NoCollision, Dissolve, `bIsDead = true`, broadcast. The mesh stays kinematic,
        so the Control Rig ragdoll is seen.
    * then `BP_OnBurrowerDied` (BlueprintImplementableEvent).
* `TargetPlayer` is replicated (`DOREPLIFETIME`), `GetTargetPlayer()` / `IsBurrowerDead()` are BlueprintPure.
* `bRefreshBonesOnServer` (default false): sets `VisibilityBasedAnimTickOption = AlwaysTickPoseAndRefreshBones` on
  the server, so the hit bodies follow the wave there too. It costs the rig every frame.

### UBurrowerAnimInstance (parent of ABP_Burrower)
* `NativeUpdateAnimation` (game thread) copies velocity size, dead flag, and the character's Rotor / Body Wave
  properties into a private struct. In the editor preview it uses `GetDefault<ABurrowerCharacter>()`.
* `NativeThreadSafeUpdateAnimation` integrates from the copies only.
* Public `Transient BlueprintReadOnly` properties, named exactly like the CR_Burrower variables:
  * `RotorAngleDeg` (deg, wrapped [0, 360))
  * `RotorSpinSpeed` (current deg/s; spins up at RotorSpinAcceleration, down to 0 after death)
  * `WaveTime` (**cycles**, wrapped to [0, 1); rate = BodyWaveIdleFrequency + speed(m/s) * BodyWaveCyclesPerMeter,
    capped at BodyWaveMaxFrequency). The rig's `WaveTimeToRadians` stays 2π.
  * `WaveAmplitudeDeg` and `WavePitchAmplitudeDeg`: **already speed-scaled**, from BodyWaveIdleAmplitudeFraction at
    rest to full at BodyWaveFullAmplitudeSpeed, smoothed, 0 after death. So **skip recipe Step 5.2** (the rig's
    optional speed gate).
  * `WavePhasePerJointDeg` (65)
  * `Speed` (cm/s)
  * `bIsDead`
  * `DeathTime` (**seconds since death, 0 while alive**)
* Answers to control_rig_recipe.md open questions 1 and 2: WaveTime in cycles, DeathTime in seconds since death, and
  the amplitude is already scaled by speed.

## What the editor session must create or set

1. Build. Accept the ControlRigPhysics plugin and restart.
2. Import `SourceArt/Burrower/Burrower_UE.fbx` as SK_Burrower. Create PA_Burrower as in control_rig_recipe.md Step 1.3
   (bodies on J0..J4 only, capsules, 20° constraints) and set it as the mesh's physics asset. The C++ hit collision
   and the fallback ragdoll use it as well.
3. **BP_Burrower**, parent `ABurrowerCharacter` (suggested `/Game/Assets/Enemies/Burrower/BP_Burrower`):
   * Mesh: Skeletal Mesh = SK_Burrower, Anim Class = ABP_Burrower. Keep the C++ relative location (-830, 0, -187),
     rotation 0. Check in the viewport that the head sits in the capsule.
   * RotorBox: check in the viewport that it covers the rotor disc (relative (977.9, 0, 180.5) on the mesh). Tune
     RotorHalfSize / RotorBoxPadding in Details > Burrower|Rotor. **Do not set a Parent Socket on it** (not `Rotor`,
     not `J0_Head`): it stays on the mesh with no socket, because a server that doesn't render the Burrower doesn't
     refresh its bones. Older text in control_rig_recipe.md Step 7 said otherwise; it is fixed.
   * HealthBar: Widget Class = `WBP_HealthBar` (gas_patterns gives `/Game/Level/UI/UserWidgets/Enemy/WBP_HealthBar`,
     not verified), Draw Size as on the other enemies.
   * **Leave the collision presets of the Capsule, Mesh and RotorBox as inherited.** The C++ sets them, and a
     Blueprint override wins.
   * StartupAbilities empty: no GA_HitReact, since its montage waits forever.
   * **Do not** call `InitializeEnemyAttributes` in the BP graph. The C++ already applies the attributes, and doing it
     twice stacks them.
   * Leave DissolveMaterialInstance unset: the base dissolves material slot 0 only, and the Burrower has many slots.
   * Optional: a dedicated GE for the Burrower's health (PrimaryAttributesEffect / VitalAttributesEffect overrides).
     The gun deals 1 per hit.
   * `bUseMeshRagdollFallback`: keep it true until CR_Burrower's ragdoll works, then set it false. With both, the two
     ragdolls fight over the bones.
4. **DA_CharClassInfo** (`/Game/Level/GAS/Data/DA_CharClassInfo`) must have an entry for the Burrower's
   CharacterClass (C++ default Warrior), with an XPReward curve. Otherwise `UMyBPFuncLib::GetXPRewardForCharacterClass`
   hits `checkf` on the kill. The GameMode must be an AMyGameMode with that data asset set; otherwise there is a
   null dereference on the kill (shared code).
5. **ABP_Burrower**: parent `BurrowerAnimInstance`, Control Rig node (CR_Burrower), with the pins wired to the
   properties of the same names (recipe Step 6).
6. **Project Settings > Game > Burrower**: Burrower Class = BP_Burrower. Optionally AllowedMaps = StartupMap (empty =
   every game map, including menus, if their pawns implement the combat interface).
   * This writes `[/Script/Aura.BurrowerSettings]` to DefaultGame.ini. Commit that.
7. Packaging: add `+DirectoriesToAlwaysCook=(Path="/Game/Assets/Enemies/Burrower")` (or wherever BP_Burrower lives).
   Only the config soft pointer references it, and the project cooks maps only.
8. **No sockets are needed.** The C++ does not use any bone or socket names. The rig uses `root`, `J0_Head`..`J4_Tail`,
   `Rotor` and the pipe chains.
9. (Dropped: the rotor no longer finds platforms by a physics query, so the `HexPillarsISM` collision settings
   don't matter.)

## Test

* PIE, listen server + 1 client. Run `Aura.Burrower.SpawnNow` in the server window. Then
  `Aura.Burrower.DebugRotorBox 1` to watch the cuts, and `Aura.Burrower.KillAll` for the death and ragdoll. The
  respawn comes SpawnInterval later.
* `AMyCharPlayer::DebugDieAfterBeginPlaySeconds = 3` is the C++ default. If BP_MyCharMech doesn't set it to 0, players
  die every 3 s and the spawner keeps pausing.
* Log category `LogBurrowerSpawn` (spawns, missing class) and `LogBurrower` (missing attribute effects).

## Unsure / to check while compiling

* UHT declares `MulticastHandleDeath_Implementation` virtual in AMyCharBase's generated body. That is standard for
  RPCs, so the subclass `override` should compile.
* Engine APIs used from memory. They are all long-standing, but I could not check them against 5.8 headers:
  * `UAnimInstance::NativeThreadSafeUpdateAnimation(float)`
  * the `USkinnedMeshComponent::VisibilityBasedAnimTickOption` public member
  * `UWidgetComponent::GetWidgetClass/SetWidgetClass/SetWidgetSpace`
  * `APlayerState::IsOnlyASpectator`
  * `UGameplayStatics::GetCurrentLevelName(World, true)`
  * `FStreamableManager::RequestAsyncLoad(TArray<FSoftObjectPath>)`, same call as MyHexBridgeSubsystem
  * `UWorld::GetAuthGameMode<T>`
  * `DrawDebugBox` with an FQuat.
  * `FAutoConsoleCommandWithWorldAndArgs` / `FAutoConsoleCommandWithWorld` and their delegate signatures
  * `FVector::Dist`, `FTransform::GetUnitAxis` (the latter is used in MyHexPlatform.cpp too)
* Confirmed by identical uses in the project: `FMath::FindDeltaAngleDegrees(double, double)`, `FRotator::NormalizeAxis`,
  `FMath::Fmod(float, float)`, `TActorIterator<AMyHexPlatform>` + EngineUtils.h, `World->GetAuthGameMode<AMyGameMode>()`.
* The plugin name `ControlRigPhysics` in Aura.uproject is not verified: only its `Source/ControlRigPhysics` module
  folder was staged, no .uplugin. If the editor reports a missing plugin, check the .uplugin name under Engine/Plugins.
* Velocity vs heading: the flying CMC turns the velocity toward the input through acceleration, so at CatchUpSpeed
  the body can slip sideways a little in tight turns. If it shows, raise MaxAcceleration on the CharacterMovement
  component or lower TurnRate.
* The actor pivot is the head, so a turn swings the tail (about 18 m behind) quickly. TurnRate 40 keeps it moderate.
  Simulated-proxy mesh smoothing also rotates the mesh about its own origin, not the capsule, so expect a few cm of
  head offset during smoothing on clients.
* The capsule ignores everything, so nothing can stop the Burrower and it can't push players. The mesh ignores Pawn,
  so players pass through the body. If the body should block players, set the mesh Pawn response to Block in
  BP_Burrower (it could jitter players it overtakes).
* Damage already in flight after death can still reach the corpse through a cached target, and every fatal hit pays
  XP again in `UMyAttributeSet::PostGameplayEffectExecute` (shared code, all enemies). The Burrower's Die is guarded
  and its corpse loses query collision. The real fix is one line in shared code:
  `if (IMyCombatInterface::Execute_IsDead(Props.TargetAvatarActor)) return;` before the damage block. I left it to
  the lead.
* Dedicated server: AMyEnemyChar::BeginPlay crashes for every enemy if the widget component creates no widget there
  (base class issue, not touched). The project uses listen servers. The spawner is off there; a Burrower placed in a
  level would still crash like any other enemy. The real fix is one line in the base:
  `if (HealthBar) { HealthBar->SetWidgetController(this); }`. Then the dedicated-server return in
  `UBurrowerSpawnSubsystem::OnWorldBeginPlay` can go.
* `ActivateTilesInWorldBox` collapses tiles that a running chain had reserved right away. See hex_api.md to skip them
  instead. It skips tiles that `IsTileCollapsed` (local or replicated record), so a tile whose ActivateHexLocal
  failed isn't appended to ActivatedTiles again at every check.

## Review fixes

Fixed (10 findings checked; 9 led to a change, 1 was a note only, none rejected as wrong):
1. **Shadowed `PlayerState`** in `ABurrowerCharacter::FindNearestLivingPlayer`: the loop variable is now
   `OtherPlayerState`. APawn::PlayerState is an inherited (private) member, and MSVC C4458 counts inherited ones. The
   project builds on Linux, so this matters only for a Windows build, but the rename costs nothing. No base field of
   AMyCharBase / AMyEnemyChar matches any other local, old or new.
2. **Yaw stall in UpdateFollow** (major): confirmed. For a goal behind and slightly above (forward x (-cos e, 0, sin e)
   = (0, -sin e, 0)), the arc turn was pure pitch, the clamp undid it every frame, and the Burrower flew away
   straight. Yaw and pitch now turn separately at TurnRate each (`FindDeltaAngleDegrees` for yaw, the pitch goal
   clamped to ±MaxPitch). The `TurnTowards` helper is removed, and so is `FMath::ClampAngle`.
3. **Spawning without the GameMode setup** (major): confirmed (`UMyBPFuncLib::GetXPRewardForCharacterClass` casts
   and dereferences without a check). New `UBurrowerSpawnSubsystem::HasEnemyClassInfo()` gates the auto-spawn
   (in `bAutoSpawn`) and `SpawnBehind` (so SpawnNow too), with one warning. `InitializeBurrowerAttributes` now logs
   an Error when the class info is missing, and the missing-effect log is an Error too.
4. **StopDistance measured from the head**: confirmed (the padded box front is ~226 cm ahead; with 400 the rotor
   stopped ~174 cm short of the goal). The throttle distance is now measured from the blade front (without the
   padding, ~176 cm ahead), and the StopDistance default is 0, so the padded box reaches 50 cm past the goal. Not
   the reviewer's padded-front measure: with that, the box front only creeps toward the goal asymptotically and can
   stop short of a tile edge at the goal. The catch-up speed still uses the head distance. Running players are still
   trailed by a few metres (throttle ramp to SlowdownDistance), by design: their tiles fall behind them.
5. **Dedicated server crash**: confirmed (MyEnemyChar.cpp:34-35). I chose the subsystem side: `OnWorldBeginPlay`
   returns on `NM_DedicatedServer` with a warning, and the header comment no longer says "dedicated server". The base
   class is not touched (brief: neutralise in the subclass); the one-line base guard is under "Unsure" for the lead.
6. **Rotor timing**: confirmed. The tile-check timer keeps its remainder (`FMath::Fmod`, 0 when the interval is 0),
   and with `bSweepRotorBox` the box is also stretched forward by forward speed x max(RotorCheckInterval, DeltaTime).
   `CheckRotorTiles` now takes DeltaTime. The debug draw shows the stretched box in yellow, and the CVar help text
   says so.
7. **Physics query for platforms**: confirmed as a silent dependency on Blueprint collision settings. Replaced with
   `TActorIterator<AMyHexPlatform>` (EngineUtils.h, as MyGameState/MyGameMode/MyHexBridgeBuilder do). It calls
   `ActivateTilesInWorldBox` directly, which already starts with the same bounds test as `CouldWorldBoxTouchTiles`,
   so the bounds test isn't run twice. `CouldWorldBoxTouchTiles` stays in the API and is unused. `RotorQueryMargin`,
   the root-component filter, the `CollisionQueryParams.h` / `Engine/OverlapResult.h` includes and editor-session
   item 9 are removed.
8. **Hex skip check**: confirmed (ActivateHex appends to the replicated TArray before ActivateHexLocal, which can
   return early). The loop now skips `IsTileCollapsed(Coord)`, and the comment says what it does.
9. **Recipe Step 7 RotorBox bullet**: confirmed it contradicted the code. Rewritten in control_rig_recipe.md (and the
   matching line under the multiplayer pitfalls). Editor-session item 3 above now warns against a parent socket.

Not changed:
* Finding 2 (engine APIs from memory) is a note, not a defect. No engine headers are available here to check them
  (only the ControlRigDynamics/ControlRigPhysics plugin headers). The list is under "Unsure" above, with the APIs this
  pass added. The new code uses project-confirmed APIs where it could.

Still uncertain:
* Nothing was compiled. The new calls are typed for UE5 doubles (FRotator/FVector components, `FMath::Clamp` with
  all-double arguments).
* MSVC C4458 for an inherited private member: the rename makes the question moot.
* That a dedicated server's UWidgetComponent creates no widget (Slate not initialised) is from memory. It matches the
  existing note about the base class.

## Death velocity and path-follow bend (2026-11-22)

Two playtest fixes from Talal: the ragdoll dropped straight down (the flight velocity was lost), and the body bent like
a fish sideways but stayed rigid up and down. C++ side in `BurrowerCharacter.h/.cpp` and `BurrowerAnimInstance.h/.cpp`;
the rig (`CR_Burrower`) and ABP pins are separate steps (bw_04 / bw_05).

### Death velocity (ABurrowerCharacter)
* New `Burrower|Death` properties: `bInheritVelocityOnDeath` (true), `DeathVelocityScale` (1, linear velocity only),
  `bInheritTurnOnDeath` (true). Plain C++ getters (no UFUNCTION): `GetDeathVelocity()` (world cm/s, already times
  the scale) and `GetDeathAngularVelocity()` (world deg/s).
* Every machine, every tick while alive (`SampleDeathMotion`, at the end of Tick, after the server's steering):
  * `LastMovingVelocity` = the last `GetVelocity()` above 10 cm/s.
  * Turn rates from the actor rotation change: yaw and pitch (deg/s), clamped to 2 x TurnRate (spawn/teleport),
    smoothed with a 0.12 s time constant. The server samples every tick. A client's actor only turns when a
    movement update arrives (replicated rotation, quantized), so it samples from one change to the next, or after
    0.25 s without one (then 0).
* `HandleBurrowerDeath` (once per machine) calls `CaptureDeathMotion()` first, before `StopMovementImmediately`:
  * V = `GetVelocity()`; on a client below 10 cm/s (the server's stop already replicated) `LastMovingVelocity`.
  * Omega = `UpVector * YawRate - GetActorRightVector() * PitchRate` (deg/s). Signs: physics moves a point at offset
    R at Omega x R (Chaos `GetWorldVelocityAtPoint` = V - R x W). Z x X = +Y matches yaw growing toward +Y; nose up
    needs X toward +Z, and Y x X = -Z, hence -Right. Worked example in the code: heading +X, tail R = (-1800, 0, 0),
    yaw +40 deg/s gives (0, -1257, 0) (tail swings to -Y about the head), pitch +20 deg/s gives (0, 0, -628).
  * For a body lying on a constant turn of radius |V|/|Omega|, V + Omega x R is the rotation about the turn's centre,
    so every body moves along the arc (checked numerically: 0.0000 deg off the tangent at 5.4, 10 and 17.9 m behind).
* Mesh fallback (`bUseMeshRagdollFallback`): right after `Super::MulticastHandleDeath_Implementation()` (which calls
  `SetSimulatePhysics(true)`), `ApplyDeathMotionToMeshBodies()` loops `USkeletalMeshComponent::Bodies` (public
  `TArray<FBodyInstance*>`), skips invalid bodies and `PhysType_Kinematic` setups, and sets
  `SetLinearVelocity(V + Omega_rad x (GetCOMPosition() - ActorLocation), false)` and
  `SetAngularVelocityInRadians(Omega_rad, false)`. 5.8 has no `FBodyInstance::SetAngularVelocityInDegrees`.
  Chaos pushes the velocities before the kinematic -> dynamic state in the same dirty data and does not reset them,
  so the bodies start their first simulated step with it. `FBodyInstance::IsInstanceSimulatingPhysics` is avoided
  on purpose: it calls a PHYSICSCORE_API function and Aura does not link PhysicsCore.
* Control Rig ragdoll: `UBurrowerAnimInstance::DeathVelocity` / `DeathAngularVelocity` (0 while alive) are set in the
  same update as `bIsDead`. The pivot for Omega x R is the actor location = the capsule centre = mesh component
  (830, 0, 187). Rig side: each body's initial velocity = DeathVelocity + Rad(DeathAngularVelocity) x (body centre -
  pivot), angular velocity = Rad(DeathAngularVelocity).

### Path-follow bend (UBurrowerAnimInstance)
* New `Burrower|Path Follow` properties on the character (public, read by the anim instance): `PathFollowStrength` 1,
  `PathFollowMaxYawDeg` 14, `PathFollowMaxPitchDeg` 10, `PathFollowSampleSpacing` 40 cm (min 10),
  `PathFollowTailLength` 457 cm, `PathFollowInterpSpeed` 12. Wave defaults raised: `BodyWaveAmplitudeDeg` 12,
  `BodyWavePitchAmplitudeDeg` 5 (BP_Burrower doesn't override either, checked in the .uasset name table).
* New anim instance outputs (rig variables of the same names): `FollowYawDeg1..4`, `FollowPitchDeg1..4`,
  `DeathVelocity`, `DeathAngularVelocity`.
* Game thread (`NativeUpdateAnimation` -> `UpdatePathFollow`):
  * Reference pose read once per mesh asset (`RefreshRefPose`): `FAnimationRuntime::GetComponentSpaceTransformRefPose`
    of J0_Head..J4_Tail from the mesh's `FReferenceSkeleton`; if any bone is missing, all five fall back to
    (1000,0,180) (660,0,193) (260,0,200) (-260,0,200) (-560,0,202). Arc lengths J1..J4 = 340.2 / 740.3 / 1260.3 /
    1560.3 cm, tip = J4 + PathFollowTailLength (2017.3).
  * Head point H = mesh component transform x ref J0 (the mesh, so a client's mesh smoothing is part of the path).
    A new trail point whenever H is PathFollowSampleSpacing from the newest one; trimmed to body + 2 m + one
    spacing (about 57 points at 40 cm, hard cap 512). First update or a jump over 20 m (spawn, teleport): the trail
    restarts as a straight line behind the head, so the body starts straight.
  * Targets T1..T5 on the polyline at those arc lengths behind the current H (past the oldest point it carries on
    along the mesh's -X).
  * For segment k (J_k -> J_k+1, the tip after J4): d = T_k+1 - T_k in component space, then seen from the parent
    segment's frame: e = Delta(k-1)^-1 d with Delta(0) = identity (J0 not turned: the head stays on its heading) and
    Delta(k) = Delta(k-1) * Quat(+Z, Yaw_k) * Quat(+Y, Pitch_k), exactly how the wave stage composes joint angles.
    Yaw_k = atan2(-e.y, -e.x), Pitch_k = atan2(e.z, |e.xy|).
  * Signs, verified: for a segment along -X, Quat(+Z, a) gives (-cos a, -sin a, 0), so atan2(y, x) rises by a and
    the tail goes to -Y; Quat(+Y, b) gives (-cos b, 0, sin b), so the elevation rises by b (tail up). Both match the
    brief.
  * Measured against -X, not against the slightly bent rest segments (J1 -> J2 rises 1 deg, J3 -> J4 0.4 deg):
    with the rest directions a straight path would give about +-1 deg and flatten the modelled shape. The angles are
    deltas on top of the rest pose, so a straight path gives exactly 0.
  * For pure yaw or pure pitch paths this equals the brief's "global_k - global_k-1". In a climbing turn the brief's
    additive form misses the rig's pose by up to 0.21 deg at J4 (helix R 20 m, 20 deg climb); the parent-frame form
    is exact (0.00).
  * Target = angle x PathFollowStrength, clamped to +-PathFollowMax*Deg per joint (the ideal, unclamped bend carries
    on to the next joint). Editor preview (no Burrower): 0 and the trail is cleared. Dead: target 0.
* Thread-safe update: `FInterpTo` toward the targets at PathFollowInterpSpeed (0 = at once); after death at a fixed
  4/s, so the bend fades while the ragdoll takes over.
* Cost per frame: 5 targets on a ~45-60 point polyline, 4 quaternion steps, one append + trim walk when a point is
  added. No allocations after the first frames (`EAllowShrinking::No`).
* Test numbers (Python re-implementation, `pathfollow_sim.py` in the session scratchpad, unclamped unless noted):
  * Straight line at yaw 30 / pitch 10: all 0.
  * Steady yaw turn at TurnRate 40: 1400 cm/s (R 20.05 m): yaw J1..J4 = -15.43 / -13.14 / -11.75 / -10.79
    (J1 clamped to -14); 3200 cm/s (R 45.8 m): -6.75 / -5.76 / -5.12 / -4.73. Turning toward +Y gives minus (the
    tail swings to +Y, the inside). Matches the chord estimate -(s_k+1 - s_k-1) / 2R; J1 gets more because the head
    segment stays on the tangent. Not equal per joint because the segments are not equal.
  * Pull-up from level to a 25 deg climb (R 20 m): pitch J1 +15.4 peak, then the bend travels back (+5.5 / +11.6 /
    +7.4 at J2..J4), then all 0 on the straight climb. Plus = tail lifted against the rigid pose: the past path is on
    the centre side of the head's backward line, so the tail stays on the lower, level path instead of swinging
    under it. Levelling off from a climb (concave down) gives the mirror image (-15.4 ...), the tail below the
    head-line extension.
  * S-curve (left 60 deg then right 120 deg): yaw sign flips at J1..J4 0.21 / 0.56 / 0.87 / 1.16 s after the
    inflection (arc length / speed: 0.24 / 0.53 / 0.90 / 1.12): the front bends first.
  * Speed independence: 4 m into the turn, 700, 1400 and 3200 cm/s at 60 fps agree to 0.02 deg; 3200 cm/s at 20 fps
    (1.6 m per frame) to 0.2 deg.
  * A teleport (head jump over 20 m): all 0 right after, the trail restarts straight.

### Compile check
* Both .cpp files compiled with the unity rsp (`Module.Aura.3.cpp.o.rsp`) with the source swapped and the outputs in
  the scratchpad, SDK clang 20, from `Engine/Source`: no errors, no warnings (-Wall -Werror -Wshadow). New undefined
  symbols are all exported by libUnrealEditor-Engine.so.
* No UFUNCTION added. The `GENERATED_BODY()` lines did not move (anim instance 26, character 39), so the old
  .generated.h still matched. UHT regenerates on the next real build; restart the editor for the new anim instance
  UPROPERTYs (legacy hot reload).
