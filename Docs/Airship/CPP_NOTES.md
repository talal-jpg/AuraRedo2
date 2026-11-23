# Airship C++ (drivable, possessable airship)

Code: `Source/Aura/Public/Airship/`, `Source/Aura/Private/Airship/`. Design: `RIG_CONTRACT.md`, `research_cpp.md`,
`research_flight.md`, `research_control_rig.md`. Units: cm, s, kg; degrees in properties.

## 1. Classes

| Class | File | What it does |
|---|---|---|
| `AAirshipPawn` (APawn, IAbilitySystemInterface, IMyCombatInterface) | `AirshipPawn.h/.cpp` | The ship. Root `HullCollision` (UStaticMeshComponent, `/Game/Assets/MyShip/SM_Airship`, 8 UCX hulls, simulates physics on every machine, hidden in game, PhysicsBody, blocks everything except Camera, overlap events on so AMyProjectile hits the hull itself). `Mesh` (USkeletalMeshComponent, visual, QueryOnly: Visibility block, WorldDynamic overlap). `CameraBoom` + `Camera`. `Flight` (UAirshipFlightComponent). GAS: `AbilitySystemComponent` (UMyAbilitySystemComponent, Mixed) + `AttributeSet` (UMyAttributeSet), `InitAbilityActorInfo(this, this)` on every machine, MaxHealth then Health set on the server. 6 Niagara components. Boarding / exit, cannons, hull impact damage + impact response cap (every machine), death, camera, input, FX update, which characters ride it (`IsPassengerCandidate`), the ship HUD on the pilot's machine, test hooks. |
| `UAirshipFlightComponent` | `AirshipFlightComponent.h/.cpp` | The flight model of research_flight section 3, all parameters as EditAnywhere UPROPERTYs with the research defaults. Called from the pawn's Tick (TG_PrePhysics). Server: controls -> shaping -> 4 pod forces (collective + roll/pitch mixed with a 3x3 solve), 2 fan forces (forward + differential yaw), one COM acceleration (grip, drag, brake, redirect, wind, hard cap) and one torque (rudder allocated inside the yaw loop, capped hidden gyro, wind). The attitude D terms damp the tilt rate only (angular velocity minus its world-Z part), the yaw loop reads world `w.Z`. Boost fuel (replicated; each start costs `BoostStartFuelCost` 10, the kick has `BoostKickCooldown` 1.5 s), drift kick, ground traces from the pods measured from the nozzle exits (floor + descent limiter + cushion). Every machine: shaped controls -> cosmetic state (gimbals, fan yaw, thrust levels). Input RPC + replicated input copy. |
| `UAirshipAnimInstance` | `AirshipAnimInstance.h/.cpp` | Parent of ABP_Airship. Game thread copies the pawn's cosmetic state, cannon aim, shot counters, death; the thread-safe update integrates (rotor spin, wheel spring with overshoot, nozzle/flare/turbine slew, recoil curve, searchlight pan, death spin-down) and writes the RIG_CONTRACT section 5 variables straight into the AnimBP's Control Rig node instance (`FAnimNode_ControlRig::GetControlRig()` + `GetPublicVariableByName`; the properties are cached per rig instance and variable struct (`GetVariablesStruct`), the memory is taken from `GetVariablesMemory()` every update, so a rebuilt property bag never leaves a dangling pointer; float or double, bool `bIsDead`). `DeathTime` comes from the ship's clock (`AAirshipPawn::GetDeathTime`). The same names are BlueprintReadOnly properties (Use Pin fallback). |
| `UAirshipPilotComponent` | `AirshipPilotComponent.h/.cpp` | Replicated, on every PlayerController (added by the subsystem). Owning client: pushes its own Enhanced Input component and adds `IMC_AirshipBoard`; `IA_AirshipBoard` -> `ServerRequestBoard`. Server: nearest free living ship in range -> `AAirshipPawn::BoardPilot`. `ServerRequestExit` / `TryExit`. `FindBoardableAirship()` (BlueprintPure, any machine) for a "Press F" prompt. |
| `UAirshipSubsystem` (UWorldSubsystem, Game + PIE worlds) | `AirshipSubsystem.h/.cpp` | Server: adds the pilot component on `FGameModeEvents::GameModePostLoginEvent` and to existing PCs in `OnWorldBeginPlay`. Registry of ships (BeginPlay/EndPlay, every machine). Deck passengers (every machine, section 3) and `RepairPhysicsState` (rebuilds a body lost while an actor's collision was off). Spawn helper. All console commands. |
| `UAirshipHUDWidget` (UUserWidget, C++ only) | `AirshipHUDWidget.h/.cpp` | The ship HUD: a 292 x 136 comic-ink panel (paper, ink outline + drop shadow) bottom-left, drawn in `NativePaint` with Slate boxes / lines and the engine font (no assets): HULL bar + value, BOOST fuel bar + % (the label turns into an ink tag while boosting), speed (m/s) and ALT (m above the ground: `TraceGroundDistance` every 0.1 s) in big digits, PORT / STBD reload (READY, or a bar + seconds; the side the cannons face is an ink tag). HitTestInvisible. Colours / size are UPROPERTYs (a Blueprint child via `AAirshipPawn::ShipHUDClass`). |
| `UAirshipSettings` (UDeveloperSettings, Config=Game, DefaultConfig) | `AirshipSettings.h` | Project Settings > Game > Airship (`[/Script/Aura.AirshipSettings]`). `AirshipClass` (soft class), spawn distance/height, `bAddPilotComponent`, `BoardDistance` 1200 (to the pilot seat) / `BoardHullDistance` 400 (to the hull collision), `BoardCooldown` 0.5, `PassengerCheckInterval` 0.1 s, all IMC/IA soft pointers with default paths (section 2). No ini change needed. |
| `AAirshipCannonball` | `AirshipCannonball.h/.cpp` | Replicated ball, UProjectileMovementComponent (gravity 1, no homing), movement not replicated: every machine flies it from the replicated launch velocity. Server only: ignores its ship, everything attached to it (pilot) and other balls; direct hit on a GAS actor -> the ship's spec; splash (450 cm, falloff to 0.3); Mech Sentinels swept along the flight (60 cm) and in the blast (`SplashRadius`, same falloff), each sentinel once per ball (shared hit set; `SweepSentinels` + the rules' damage spec, next-tick timer). If the ship is gone when the ball lands and the damage effect has an execution (UExecCalc_Damage reads the source ASC unchecked), the GAS hit is skipped; the built-in effect still applies. Then hides, `MulticastImpact` (ImpactFX + `BP_OnImpact`), removed after 1 s. |
| `UAirshipDamageEffect` (UGameplayEffect) | `AirshipDamageEffect.h/.cpp` | Built-in instant GE: Additive `UMyAttributeSet::IncomingDamage`, SetByCaller `SetDamageByCaller`. Default for impacts, console damage and cannonballs when `DamageEffectClass` is unset. |
| types | `AirshipTypes.h` | `FAirshipPilotInput` (int8 axes, button bits, uint8 Seq, FVector_NetQuantize AimPoint, uint16 HeadingTarget), `FAirshipFlightTelemetry` (BlueprintType), `FAirshipCosmeticState` (C++ only), `EAirshipSide`, `EAirshipControlScheme`, `FAirshipFeedbackEvent`, `FPointFlyLoopState`, `Airship::` constants (pod order FL FR RL RR, fans L R, cannons L1 L2 R1 R2, button bits), `AirshipGalleon::` (the engine order code). Control schemes: section 14. |

No new gameplay tags (damage uses `MyTags::SetDamageByCaller`).

## 2. What the editor step must create or set (exact names)

Folder `/Game/Assets/MyShip/Drivable/` (RIG_CONTRACT section 1). Input assets in `/Game/Assets/MyShip/Drivable/Input/`
(the settings' default paths; change Project Settings > Game > Airship if they go elsewhere).

### Input (Enhanced Input). Every action keeps `bConsumeInput` = true (default)

| Asset | Value type | Mappings (KB+M / gamepad) | Read as |
|---|---|---|---|
| `IA_AirshipThrottle` | Axis1D | W; S + Negate; Gamepad Left Thumbstick Y-Axis | value each frame |
| `IA_AirshipSteer` | Axis1D | D; A + Negate; Gamepad Left Thumbstick X-Axis (DeadZone 0.15, Response Curve Exponential 1.6) | value each frame |
| `IA_AirshipLift` | Axis1D | Space Bar; Left Ctrl + Negate (optionally C + Negate); Gamepad Right Trigger Axis; Gamepad Left Trigger Axis + Negate | value each frame |
| `IA_AirshipStrafe` | Axis1D | E; Q + Negate; Gamepad D-pad Right; D-pad Left + Negate | value each frame |
| `IA_AirshipBoost` | Digital (bool) | Left Shift; Gamepad Face Button Bottom (A) | held, each frame |
| `IA_AirshipBrake` | Digital (bool) | X; Gamepad Face Button Right (B) | held, each frame |
| `IA_AirshipFire` | Digital (bool) | Left Mouse Button; Gamepad Right Shoulder | `Started` |
| `IA_AirshipLook` | Axis2D | Mouse XY 2D-Axis with the same modifiers IA_Rotate has in IMC_PlayerMappings; Gamepad Right Thumbstick 2D-Axis (Response Curve Exponential 2.0) | `Triggered` -> AddControllerYaw/PitchInput (Options look sensitivity/invert applied) |
| `IA_AirshipZoom` | Axis1D | Mouse Wheel Axis (+ = in); D-pad Up; D-pad Down + Negate | `Triggered` |
| `IA_AirshipExit` | Digital (bool) | F; Gamepad Face Button Top (Y) | `Started` |
| `IA_AirshipAim` (recommended) | Digital (bool) | Right Mouse Button; Gamepad Left Shoulder | held (aim FOV). Mapping RMB keeps the on-foot beam from firing while flying |
| `IMC_Airship` | context | holds all of the above; added at priority 1 (`AirshipMappingPriority`) while the ship is locally possessed | |
| `IA_AirshipBoard` | Digital (bool) | F; Gamepad Face Button Top (Y) | `Started` |
| `IMC_AirshipBoard` | context | holds IA_AirshipBoard; added at priority 0 (`BoardMappingPriority`) by the pilot component on the owning client | |

IMC_Airship must map the same physical keys as IMC_PlayerMappings (WASD, Space, Shift, LMB, RMB, Q/E, mouse) so the on-foot
abilities, IA_Move and the attribute/spell menus are consumed while flying. Leave Escape (pause) unmapped.

### BP_AirshipPawn (parent AAirshipPawn)

* `Mesh`: Skeletal Mesh `SK_Airship` (with PA_Airship; its bodies are only needed for traces/overlaps on moving parts, the hull covers the rest), Anim Class `ABP_Airship`. Keep the Mesh at relative (0,0,0),
  rotation 0, scale 1 under HullCollision (the bone positions are read through that transform).
* `ThrusterFX_FL/FR/RL/RR`: Niagara System (e.g. NS_AirshipThruster, a copy of `/Game/NiagaraExamples/FX_Misc/NS_Boost`
  with float User parameters `Thrust` (0..1.5, 1 = hover) and `Boost` (0..1)). Parent sockets are `Thruster_*_Flame`.
* `TurbineFX_L/R`: Niagara System for the fan exhaust (same `Thrust` 0..1 / `Boost` params), sockets `Turbine_*_Exhaust`.
* `MuzzleFX` (e.g. `/Game/NiagaraExamples/FX_Weapons/MuzzleFlashes/NS_MuzzleFlash`, set Use Bullet Shell off in a copy),
  `DeathExplosionFX` (e.g. NS_FireExplosion), `DeathFireFX` (e.g. `/Game/Assets/Effects/Fire/NS_Fire`), `DeathFireSocket`
  (default `Hull`).
* `CannonballClass`: BP_AirshipCannonball.
* Optional: `DamageEffectClass` (unset = built-in; GE_ProjectileDamage gives block/crit text), `HullPhysicalMaterial`
  (PM_AirshipHull: Friction 0.2, Restitution 0.08, Restitution Combine Mode Min + override since the validation session; was 0.35 Max), the input UPROPERTYs
  (unset = Project Settings), `MaxHealth` (2000), `ShipLevel`, FX param names `FXThrustParam`/`FXBoostParam`.
* Optional: add a `MechSentinelObstacleComponent` (RefreshInterval about 0.25) so sentinels avoid the hull.

### BP_AirshipCannonball (parent AAirshipCannonball)

`BallMesh` (a sphere about 56 cm, no collision), `TrailFX` system (e.g. NS_CombatTrail), `ImpactFX` (e.g. NS_FireExplosion),
`Radius` 28, `SplashRadius` 450, `MaxLifeSeconds` 8.

### ABP_Airship (parent UAirshipAnimInstance)

AnimGraph: Control Rig node (`CR_Airship`) -> Output Pose, Alpha 1, no exposed pins (C++ writes the variables).
Multi-threaded update on. Limits/feel (nozzle, flare, turbine, rotor, rudder, wheel spring, cannon slew/limits, recoil,
searchlight) are EditAnywhere on the class defaults. `bWriteRigVariables` off = only the properties (Use Pin path: expose
a pin only if it is wired to the same-named property).

### CR_Airship

Public variables exactly as RIG_CONTRACT section 5: float `NozzlePitchDeg_FL/FR/RL/RR`, `NozzleRollDeg_*`,
`NozzleFlareDeg_*`, `ThrustAlpha_*`, `TurbineYawDeg_L/R`, `RotorAngleDeg_L/R`, `RudderDeg`, `WheelAngleDeg`,
`CannonYawDeg_L1/L2/R1/R2`, `CannonElevDeg_*`, `CannonRecoilCm_*`, `SearchLightPanDeg`, `DeathTime`; bool `bIsDead`.

### SK_Airship bones the C++ reads (rest pose)

`PilotSeat` (pilot feet; fallback hull (-843, 0, 262)), `Thruster_FL/FR/RL/RR` (pod force points), `Thruster_*_Flame`
(nozzle exits: ground clearance is measured from them; fallback 470 cm below the pod, `NozzleDepthFallback`), `Turbine_L_Rotor` /
`Turbine_R_Rotor` (fan force points), `Cannon_L1/L2/R1/R2_Muzzle` + `_Barrel` (muzzle position, rest direction
barrel -> muzzle), sockets for FX `Thruster_*_Flame`, `Turbine_*_Exhaust`, `Hull`. Missing bones use the hull-space
fallbacks (`PodLocationsFallback`, `FanLocationsFallback`, `CannonMuzzleFallback`, `PilotSeatFallback`).

### Packaging

The BP and input assets are referenced only from config/soft pointers: add
`+DirectoriesToAlwaysCook=(Path="/Game/Assets/MyShip/Drivable")` to DefaultGame.ini before packaging (PIE doesn't need it).

## 3. Boarding, exit, death

* Board (server, `BoardPilot`): the pawn must be a living ACharacter with a PlayerState, the ship alive without a pilot,
  the pawn within BoardDistance of the seat or BoardHullDistance of the hull. Then: cancel the pilot's active non-passive
  abilities (like AMyGameMode), save Health/Mana, stop + disable movement, collision off, attach to the hull root at
  the seat (+ capsule half height + 5 cm, facing +X), `bAlwaysRelevant` on, `PilotCharacter` replicated, `PC->Possess`.
  Clients turn the pilot's collision off themselves (OnRep + any character attached to the hull) and back on once it
  is detached.
* Exit (F = `IA_AirshipExit` -> `ServerRequestExit`, or the pilot component): detach next to the seat (`ExitOffset` (0,
  -250, 0): 2.5 m to port of the PilotSeat; a line trace on HullCollision only, from 3 m above to 6 m below that point,
  puts the feet on the top hull surface there + 5 cm), collision and relevancy restored, falling,
  `PC->Possess(character)`, saved Health/Mana restored (re-possessing refills them), the ship's velocity given to the
  character. Its capsule goes query only right then (it is a passenger, below), with the collision already back on. A
  plain AAirshipPawn without SK_Airship shows its hull in game (`bShowHullWithoutMesh`), so C++-only tests can see it.
  The ship then holds its altitude with neutral controls. **The top hull surface at the helm is not the deck**:
  SM_Airship's `UCX_SM_Airship_00` is a sloped lid 5.8 m (stern) .. 3.5 m (bow) high on the centreline, 4.6 m at the
  exit point, while the planks are at 2.3-2.9 m (`deck_slabs.json`). exit_probe.json agrees: feet 4.61 m above the hull
  origin after Exit, 1.9 m above the seat. So the exited pilot (and anyone walking "on deck") stands on an invisible lid
  1.2-2.9 m above the planks. C++ can't place anyone on the planks while that convex fills the space above them:
  SM_Airship needs UCX hulls whose tops follow the deck (split UCX_00 at the deck; cabin, masts, gantries as their own
  convexes). The exit code needs no change for that.
* Deck passengers (every machine, `UAirshipSubsystem::UpdatePassengers`, every `PassengerCheckInterval` 0.1 s while a
  ship exists or an entry waits to be restored, and at once on board / exit / a client restoring the old pilot's
  collision / a ship's EndPlay): a character a ship claims (`AAirshipPawn::IsPassengerCandidate`: attached to it, its
  movement base is the hull or anything attached to the ship, or no base and inside the hull's bounds +
  `PassengerZoneMargin` 3 m) gets every non-simulating primitive that blocks the hull's object type with physics
  switched to QueryOnly (PhysicsOnly -> NoCollision), re-checked every pass (an ability switching it back is caught
  again). Given back (only where nobody changed it since) when the character leaves, its ship's EndPlay, or
  `bPassengersQueryOnly` off; a dead ship keeps its riders until they leave or the wreck goes (a kinematic capsule given
  back its physics mid-tumble would shove the wreck like an immovable post). Why: the capsule is a kinematic body; on a
  simulated base the CMC moves it before physics and follows the base only after the step (`MaybeUpdateBasedMovement` ->
  post-physics tick for an `IsSimulatedBase`), so every step the hull's upward correction ran into an infinitely heavy
  capsule (the ship sank ~18 cm/s with a character on deck, also with CMC physics interaction off). QueryOnly removes
  the capsule from the simulation (`BuildBodyCollisionFlags`) and keeps the CMC on the hull, but only through the
  capsule's own body: `MoveComponent` sweeps the component's own shapes (`UWorld::ComponentSweepMulti` ->
  `GetAllPhysicsObjects`), so without a body there are no blocking hits, no landing, no overlaps. The physics on/off
  switch rebuilds the body (`FBodyInstance::SetCollisionEnabled` -> `RecreatePhysicsState`, once per boarding and
  leaving), and the rebuild makes one only while the actor's collision is on
  (`UPrimitiveComponent::ShouldCreatePhysicsState` reads the owner-checked `GetCollisionEnabled`, NoCollision while it
  is off); `SetActorEnableCollision(true)` later only updates filters (`OnActorEnableCollisionChanged`). So the
  subsystem never switches a character whose actor collision is off: the attached pilot stays a passenger untouched and
  is switched right after Exit (round 2 switched it at boarding, so the ex-pilot had no capsule body and fell through
  the lid, the deck and, landed, the ground; found in the review of round 2, fixed in round 3, section 11). A rider that
  leaves while its collision is off keeps its entry without a ship until the collision is back, then is restored (the
  timer runs while such entries exist). Safety net: `UAirshipSubsystem::RepairPhysicsState` rebuilds any registered
  primitive's missing body (`!IsPhysicsStateCreated() && ShouldCreatePhysicsState()`, never during async creation) after
  every `SetActorEnableCollision(true)` of the pawn (exit, client restore, client EndPlay) and on every rider check; it
  logs each rebuild. The CMC's own physics interaction stays (100 kg standing force on a 40 t ship).
  `Aura.Airship.Passengers` logs them; `GetPassengers()` (BlueprintPure, riders only).
* Death (Health <= 0 -> `Die`, server, once): `bIsDead` (replicated) + reliable multicast -> every machine once: flight
  off, dead damping, client gravity back on, server spin kick + one pod pushed down, the 4 thruster jets
  `DeactivateImmediate` (each jet is one persistent mesh particle that a soft Deactivate could leave burning on a pod
  flying off) and the fan wash `Deactivate` (fades; immediate for a late joiner), `bAutoActivate` cleared on the
  component itself (no restart on a re-register or `SetAsset`; `SetAutoActivate` on a registered component only logs a
  warning), explosion + fire FX, the ship HUD goes, `BP_OnAirshipDied`, `OnDeathDelegate`. Next tick the pilot is
  ejected (thrown up and sideways) and re-possessed. LifeSpan `WreckLifeSpan` 25 s. The anim instance sets `bIsDead` /
  `DeathTime` (wreck solver). A client that joins after the death (BeginPlay sees `bIsDead`) skips the explosion FX, and
  its `DeathTime` continues from the replicated `DeathServerTime` (`AGameStateBase::GetServerWorldTimeSeconds`), so
  timed break-offs don't replay.
* Logout while flying: the engine destroys the possessed ship (APlayerController::PawnLeavingGame); the ship's EndPlay
  then destroys the pilot character too. Ship destroyed otherwise (console, kill Z) with a pilot: the pilot is put back
  on foot first.
* Hull impacts, response (every machine, `LimitImpactResponse` from `OnHullHit`, once per frame; kick budgets since
  round 3): each physics step is measured from the hull's velocities before it (`RecordPreStepState`, pawn Tick in
  TG_PrePhysics, plus the boost / drift kick the flight model put into that step, `NoteFlightKick`; hit events come
  after the step in `FPhysScene_Chaos::HandleCollisionEvents`). What flight forces and gravity can do in one step
  passes (`ImpactEpisodeAccel` 2500 cm/s per s and `ImpactEpisodeSpinAccelDeg` 90 deg/s per s times the step; the
  wreck gets nothing free upward, it has no lift). Beyond that every contact has budgets: `ImpactMaxReboundSpeed` 250
  cm/s of upward speed above max(upward speed before, 0), `ImpactMaxSpeedGain` 500 cm/s of horizontal speed and 500 of
  speed, `ImpactMaxSpinKickDeg` 20 deg/s of spin (dead `DeadImpactMaxSpinKickDeg` 40; a reversal or a turned spin axis
  counts from the stop, slowing down is free). Hits less than max(`ImpactEpisodeGap` 0.25 s, 2.5 frames) apart are one
  contact and share the budgets (a push-out over several frames can't add its kicks up); while it lasts they come back
  over `ImpactKickRefillTime` 1 s, so a hit late in a long contact (landed, scraping into a pillar) is capped like the
  first one. Losing speed or spin is never limited. Targets: the PBD depenetration pop (clipping AS_Obstacle_1 at 86
  m/s gave +26 m/s up in one sample), the wreck's bounce and its sideways kick off a slanted contact (68 m/s down -> 18
  m/s sideways). Offline port + scenarios: `Docs/Airship/sims/fix3/cap_model.py`, `scenarios.py` (section 11).
  Restitution itself is the physical material's (`HullPhysicalMaterial`). `bLimitImpactResponse` off = engine response.
* Hull impacts, damage (server): `|NormalImpulse| / mass` below 50 cm/s is resting contact. Impact speed = closing speed
  along the contact normal at the contact point before the step (hull velocity + spin, minus the other body's), above
  `ImpactMinSpeed` 400 cm/s -> `ImpactDamagePerMS` 6 per m/s above it (max 500: 50 m/s head-on 276, 87 m/s 498).
  The hardest contact of a frame counts (later pairs of the same frame add only the difference), cooldown 0.4 s
  between frames, `BP_OnHullImpact` once. Characters and Pawn-type components never count (a kinematic capsule looks
  like a wall hit); its own pilot and cannonballs neither; a light body barely changes the hull's speed (impulse test).

## 4. Cannons

Fire (LMB) on the pilot's machine: camera aim trace (Visibility, 600 m, ignores the ship and the pilot) -> side = the aim
point's hull-space Y (300 cm hysteresis) -> `ServerFireCannons(Side, AimPoint)`. Server: per-side cooldown 1.5 s; for
each cannon of that side yaw/elevation toward the aim point clamped to +-20 / -10..+8.5 (`CannonElevMaxDeg` on the pawn and the
anim instance; the barrel meets its carriage at 8.75; 9 before 2026-11-22, then 8.75 gave a 9.32 deg transient in cr_eval R2;
the anim instance also eases the elevation in, `CannonElevSettleRate` 8/s: slew = min(45, error x 8) deg/s, so the
barrel's physics drive isn't stopped dead at the limit; `as_13_cr_eval.py` ramps the rig the same way to 8.5, its Blender
sweep cross-check keeps the test anim's 8.75), spread 0.6 deg, velocity =
dir * 12000 + the muzzle's own velocity (v + w x r), spec from the ship's ASC (SetByCaller 60), then
`MulticastCannonsFired` (recoil counter, muzzle FX, hull kick 80 cm/s per cannon on every machine). The pilot's client
only sends the RPC once its own 1.5 s reload of that side is done (the server allows 0.1 s of clock difference), plays
that shot at once and marks it pending; the multicast skips exactly the pending shot (a pending shot older than
cooldown + 0.5 s expires), so every real shot shows once on the pilot's screen. The camera-facing side's cannons track the aim point on every
machine (pilot: local camera, others: replicated aim point); the other side rests.

## 5. Network model

* Server-authoritative physics. `EPhysicsReplicationMode::Default`; `Aura.Airship.RepMode 1` asks for
  PredictiveInterpolation (set it on every machine; PIE shares CVars) but is only applied with Project Settings >
  Physics > Physics Prediction on (off in this project: the client copies were never corrected, section 13; the ship
  stays on Default and logs one warning). Replicated movement, NetUpdateFrequency 60 / min 30, plus
  `bReplicateEveryFrame` (default on: `ForceNetUpdate` every server frame while the hull is awake, section 13),
  `bAlwaysRelevant`, rotation `ShortComponents`, `bReplicatePhysicsToAutonomousProxy` true.
* Pilot input: `UAirshipFlightComponent::ServerSetPilotInput` (unreliable, 30/s + on change, Seq wrap-aware, neutral
  after 0.5 s; once the stored input is older than `InputTimeout` any packet is taken, so a long loss can't lock the
  8-bit order test). Listen-server host: applied directly. The server copies the used controls (boost gated by fuel) to
  `RepInput` (COND_SkipOwner).
* Forces only on the server. Clients: hull gravity off while alive (coasts between corrections), on at death.
* Cosmetics (nozzles, fans, wheel, rudder, cannons, FX, camera FOV) from the same filters on every machine: the pilot's
  machine from its own input at once, the others from `RepInput`.
* Fire: reliable server RPC + unreliable multicast. Death: replicated bool + `DeathServerTime` + reliable multicast.
  Pilot: replicated pointer.

## 6. Console commands and test hooks (non-shipping)

| Command | Where | Does |
|---|---|---|
| `Aura.Airship.Spawn` | server | AirshipClass 60 m in front of / 15 m above player 0's pawn (plain AAirshipPawn if the class is missing) |
| `Aura.Airship.Board [Player]` | server | player (default 0) boards the nearest free ship, any distance |
| `Aura.Airship.Exit [Player]` | server | player leaves the helm |
| `Aura.Airship.Damage <n>` | server | every living ship takes n through its damage effect |
| `Aura.Airship.Kill` | server | Health 0 + Die on every living ship |
| `Aura.Airship.Set <Name> <Value>` | any (forces: server) | sets a property on every ship by reflection: flight component by default, `Pawn.<Name>`, `Anim.<Name>`; any text-importable type; re-applies body settings |
| `Aura.Airship.Get <Name>` | any | prints it |
| `Aura.Airship.Input <thr> <steer> [lift] [strafe] [boost] [brake]` / `Aura.Airship.InputClear` | server (a client's own ship: its client, through the input RPC) | flies every ship (DebugSetInput) |
| `Aura.Airship.Telemetry` | any | logs the telemetry of every ship, a second line with the control scheme's state (scheme, Galleon order, Sky Racer drift / turbo, Point & Fly heading target, free look, gun deck, gun lock) and a third with the hull inertia (`GetInertiaTensor`, the mass frame from `GetMassSpaceLocal`, the hull-space COM; BASELINE 4f row 0) |
| `Aura.Airship.Scheme [0-3 \| check]` | `0-3`: server; no argument and `check`: any | `0-3`: every ship switches control scheme (0 Classic (v1), 1 Galleon, 2 Sky Racer, 3 Point & Fly = the default; replicated, section 14). No argument: each ship's scheme and the flight model's copy. `check`: every scheme-owned property that differs from the class defaults, and the count (0 after `Aura.Airship.Scheme 0`) |
| `Aura.Airship.Debug 0/1` (CVar) | server | draws pod (yellow, exhaust direction), fan (cyan), COM force (green), torque (magenta), velocity (white), hold altitude (blue), ground traces |
| `Aura.Airship.RepMode 0/1` (CVar) | every machine | Default / PredictiveInterpolation (1 only with Physics Prediction on; otherwise Default + one warning) |
| `Aura.Airship.Passengers` | any | re-checks the deck passengers of this world now and logs each (root collision enabled value (1 = QueryOnly), whether the root has a physics body, actor collision, attached or not) |

BlueprintCallable for a Python PIE harness: `AAirshipPawn::DebugSetInput(Throttle, Steer, Lift, Strafe,
bBoost, bBrake)` (`debug_set_input`; on the pilot's machine, host or client, it replaces the keys in `GatherLocalInput`
and reaches the server through `ServerSetPilotInput` like them; on the server's copy of a ship piloted from a client or
by nobody it drives the forces directly), `DebugClearInput`, `GetFlightTelemetry()` -> `FAirshipFlightTelemetry`
(SpeedMS, ForwardSpeedMS, LateralSpeedMS, AltitudeM, GroundClearanceM, VerticalSpeedMS, YawRateDegS, RollDeg, PitchDeg,
YawDeg, HoldAltitudeM, BoostFuel, Health, MaxHealth, MassKg, shaped Throttle/Steer/Lift/Strafe/Boost, bBraking,
bDrifting, bHasPilot, bIsDead, and the control-scheme fields of section 14.6), `SetControlScheme` / `GetControlScheme`
(section 14), `ApplyShipDamage`, `RequestFire` (locally controlled only), `GetPilot`, `HasPilot`,
`IsAirshipDead`, `GetPassengers()` (this machine's riders), `IsShipHUDShown()` (the pilot's machine: true only with the
widget on screen), `TraceGroundDistance(MaxDistance)` (cm from the bottom of the hull's bounds to the ground, -1 =
nothing). The pilot component: `RequestBoard`, `RequestExit`, `FindBoardableAirship`. From Python a passenger's capsule
setting is `character.get_editor_property('capsule_component').get_collision_enabled()`: QUERY_ONLY for a rider on deck,
NO_COLLISION for the attached pilot (that getter includes the actor's collision switch, which is off while attached).
It reads the flag, not the body: whether the capsule HAS a body is `capsule.line_trace_component(top, bottom, False,
False, False)[0]` (a trace against that component alone; False = no body). `as_30_pie_smoke.py` check `k2_exit_body`
does both after Exit, plus the character's z over the hull for the last 2 s of the exit phase (span < 30 cm), Walking,
and the ship's `GetPassengers()`. A rebuilt body logs `LogAirship: <character>: rebuilt the physics body of <component>`.

## 7. Shared code touched (tiny, commented)

* `GA_GunShoot::MyFunc`: any GAS actor whose ASC has `UMyAttributeSet` (was `AMyCharBase` only), so the gun hurts ships.
* `UMyAttributeSet` IncomingXP: returns when there is no SourceCharacter or the avatar has no PlayerState (piloting).
* `UAT_SendMouseCursorData::Activate`: when the avatar has no controller (unpossessed pilot) it cancels the ability
  (`CancelAbilityHandle`) and ends the task, so a gun press that reaches the server after boarding doesn't leave
  GA_GunShoot active.
* `AMyPlayerController2::TickFieldOfViewSetting`: returns while the pawn is an AAirshipPawn (the ship applies the FOV
  setting to its own camera), so boarding and leaving no longer add the setting's delta to the character camera again.
* `Aura.Build.cs`: private `ControlRig`, `RigVM`, `PhysicsCore`.

## 8. Known limits / to check in PIE

* Round 3 (section 11) ran in the validation PIE runs (section 12): `k2_exit_body` PASS and no `rebuilt the physics
  body` log line in a board / exit / re-board / death (one would mean something else switched a collision while the
  actor's was off).
* A character walking on deck still nudges the hovering ship sideways (validation: 1.4 m in 8 s of walking, 0.3 m in
  10 s standing; no sink, pitch < 0.6 deg): the CMC's own physics interaction on its base, the capsule is query only.
* Impact cap: the per-step free part (2.5 g, 90 deg/s per s) is granted to every contact step, so a sustained push of
  up to about 2.5 g (wedged, scraping) is never limited, and a push of 200 cm/s every frame still gains about 35 m/s in
  1 s (round 2: 29; scenario S12). It can't tell flight forces from contact pushes; lower `ImpactEpisodeAccel` toward
  the boost's 1960 if crashes still look too lively.
* Signs to confirm with `Aura.Airship.Debug 1`: yaw right = D, fan housing sign,
  nozzle roll sign in the rig, impact normal impulse size. Rudder and wheel signs are now pinned in RIG_CONTRACT 5
  (standard rotation about hull +Z / +X: a right turn is negative), so `RudderDegPerSteer` -25 and `WheelDegPerSteer`
  -270 by default; the rig must not negate them again.
* CCD is on (`bUseCCD`, research_flight 3.9); its cost is not measured. The hull now generates overlap events (it moves
  every frame, so it runs an overlap query of the 8 hulls each frame): measure with `stat game` if it shows up; the
  fallback is overlap events off plus a PA_Airship that covers the whole hull.
* A character on the ground next to / under the ship (not riding it: its base is the ground) keeps its physics
  capsule; a low ship coming down onto it rests on it like on a post. Only riders are query only.
* Walking on deck happens on the UCX lid, not the planks (section 3, Exit) until SM_Airship's hulls are re-authored.
* Grip at top speed with the tilt-rate fix (flight sim): slip 7/9/12/17 deg at 1/2/4/8 s against research 7/13/23/30.
  `GripALatMaxG` 2.2 gives 7/12/21/32 but the nose dips to -7 deg; kept 2.5.
* Real COM / inertia of the 8 hulls: log `GetFlightTelemetry().MassKg`; loops use the runtime mass and inertia.
* Client pilot latency = RTT + about one send interval (option A of research_flight 6.2); cosmetics are instant.
  Measured (section 13): the server applies a client's input 2 frames later without lag, 0.17-0.2 s with `Net PktLag=100`
  on both sides; the pilot's own ship answers after 0.07-0.17 s / 0.3-0.37 s; wheel, fans and nozzles after 0.07 s.
  With 100 ms lag the client copy still judders in bursts (lagged packets bunch up) and the engine hard-snaps it now
  and then (once by 6.3 m at 54 m/s, otherwise 0.1-0.7 m). No `UNetworkPhysicsSettingsComponent` (hard snap distance
  400 cm, error accumulation 0.5 s); `Aura.Airship.RepMode 1` needs Physics Prediction (section 5).
* No XP while piloting (kills by cannonballs are the ship's; the XP guard drops XP that arrives while flying).
* No damage numbers on the ship (ShowDamageNumber_2 needs a Character target).
* The Burrower and the sentinels target the possessed ship (PlayerState->GetPawn()).
* Edge fog RVT and the mech's own camera effects stop while flying (AMyCharPlayer only runs them locally controlled).
* The path ranking (AMyGameState) stays at the pilot's last platform while flying (only AMyCharPlayer::BaseChange sets it).
* The pilot is attached to the hull root at the PilotSeat bone's rest position (not to the bone itself): attachment
  replication resolves the parent's root, and the bone doesn't move relative to the hull while alive.
* `RepInput` carries the controls the server used (raw, boost gated); every machine runs them through the same
  shaping filters, so the cosmetics match without sending filter state.
* Passengers on a moving hull: the CMC follows a simulating base in its post-physics tick (one frame behind the hull);
  at speed a rider may slide a little on turns. Not tuned beyond the query-only capsule.
* A pilot who disconnects takes the ship with them (engine PawnLeavingGame).
* `Pawn.MaxHealth` / `Pawn.Armor` via Aura.Airship.Set only apply to newly spawned ships (BeginPlay).
* `DebugSetInput` on the pilot's machine goes through the pilot's input path (`ServerSetPilotInput` from a client) since
  the multiplayer test (section 13); on the server's copy of a client-piloted or empty ship it drives the forces
  directly. Flight forces only run on the server.

## 9. Review round 1 (2026-11-22): what changed

Three reviews (crash, net/GAS, flight with a 6-DOF Python port of ApplyForces). Re-run the flight checks with
`Docs/Airship/sims/fix_flight/` (`sim_fixed.py` = the port with one flag per
fix, `cases.py` coded vs fixed, `floor.py` descent onto ground, `grip.py`).

| Area | Change | Sim result (fixed) |
|---|---|---|
| Cannonball | `bInitialVelocityInLocalSpace = false` (the engine default rotated the world velocity again in InitializeComponent: server balls flew at twice the yaw/pitch); BeginPlay sets the launch velocity on every machine | |
| Cannonball | sentinels hit once per ball, blast radius `SplashRadius` with falloff, exec-calc effect skipped when the ship is gone | |
| Rudder | allocated inside the yaw loop (cap `RudderAuthority * (v/4800)^2 * abs(steer)`, max 1.2) instead of open loop | boost turn holds 24 deg/s (was a 180 deg spin-out); top-speed turn 33.6 deg/s |
| Attitude | D terms damp the tilt rate only; yaw loop on world `w.Z` | top-speed turn: bank 18 deg, pitch -1.3..+0.8 (was -10.6 at 8 s); pivot pitch -0.3 |
| Boost | `BoostStartFuelCost` 10 per start, `BoostKickCooldown` 1.5 s | tapping Shift at 7.5 Hz: 52 m/s (was 114); holding: 3.6 s of boost (was 4) |
| Brake | the fans reverse with `AFan` while braking (S alone keeps `AFanRev`) | 48 -> 0 m/s in 2.07 s (target 2.0; was 2.6) |
| Drift | keeps the throttle, `DriftBrakeScale` 0 | slip 16/42/64/74 deg at 1/2/3/4 s at ~50 m/s (was a stop at 5.7 m/s) |
| Floor | clearance measured from the nozzle exits, `MinClearance` 400, descent limiter `FloorBrakeAccel` 0.6 g | full Ctrl onto flat ground: exits stop 2.9 m above it (were 2 m into it) |
| Misc | shaping uses the physics dt; `bGroundTraces` off clears the distances; `bUseCCD` true; input Seq stale reset; hull overlap events; impact damage ignores characters; fire prediction only when locally reloaded + pending flag; late-join death; rig variable cache per variable struct; rudder/wheel defaults negative | |

## 10. Fix round 2 (2026-11-22, after the first PIE smoke test): what changed

First PIE smoke test: `Docs/Airship/reports/pie_smoke.txt` (15/15 PASS) with the problems below. Build clean
(`_AirshipWork_logs/build_141313.log`, no Airship warnings). Not run in PIE yet: the tune step and the multiplayer PIE
check these.

| Problem (smoke test) | Change | Where |
|---|---|---|
| A character on deck sinks the hovering ship (~18 cm/s, +2..7 deg pitch; 7 m in 3 s at 30 fps), also with CMC physics interaction off | Deck passengers: riders' kinematic primitives that block the hull go QueryOnly while aboard, every machine (section 3). Dead ships keep their riders. | `UAirshipSubsystem::UpdatePassengers` / `ApplyPassengerCollision` / `RestorePassenger`, `AAirshipPawn::IsPassengerCandidate`, `RefreshPassengers` (board, exit, client collision restore), `UAirshipSettings::PassengerCheckInterval`, `Aura.Airship.Passengers` |
| Exit placement | Checked, unchanged: 2.5 m to port of the seat, feet on the top hull surface, which at the helm is UCX_SM_Airship_00's lid 1.9 m above the planks. Needs re-authored UCX hulls (section 3, Exit). | `AAirshipPawn::UnboardPilot` |
| Detached pods keep their idle flame after death | At death on every machine: thruster jets `DeactivateImmediate`, fan wash `Deactivate` (immediate for a late joiner), auto-activate off; `UpdateFX` stops feeding them | `AAirshipPawn::HandleDeath`, `UpdateFX` |
| Lively crashes: hull bounce 12 m at 68 m/s, +26 m/s up clipping an obstacle at 86 m/s, 18 m/s sideways kick off the ground | Impact response cap per contact episode (up, horizontal, speed, spin) on every machine; damage from the hardest contact of the frame (section 3). Restitution stays with `PM_AirshipHull` (tune step). Wreck parts scattering / tunnelling are the rig's Wreck solver (tune step). | `AAirshipPawn::LimitImpactResponse`, `OnHullHit` |
| Barrel elevation transient 9.32 deg at an 8.75 target (carriage contact ~1 cm) | `CannonElevMaxDeg` 8.5 (pawn and anim instance) + `CannonElevSettleRate` 8/s ease-in. Offline drive model (`Docs/Airship/sims/fix2/barrel_sim2.py`): barrel-to-carriage peak 8.50-8.55 deg for a carriage reaction ratio 1-3 (8.5 without the ease-in: 8.72-8.90). cr_eval steps the variable directly, so re-check with the eased input | `AAirshipPawn::CannonElevMaxDeg`, `UAirshipAnimInstance::CannonElevMaxDeg` / `CannonElevSettleRate` |
| On-foot HUD (globes, ability icons) stays while flying, no ship HUD | Pilot's machine: AMyHUD's `OverlayWidget` (read by reflection, `OnFootHUDWidgetProperty`, no change to AMyHUD) collapsed while flying, its old visibility restored after (only if still collapsed); `UAirshipHUDWidget` bottom-left via `UGameViewportSubsystem::AddWidgetForPlayer`. Shown while a local PlayerController possesses the living ship; removed on exit, unpossess, death, EndPlay. The hex minimap stays. | `AAirshipPawn::UpdateShipHUD` (Tick, `NotifyControllerChanged`, `HandleDeath`), `ShowShipHUD`, `HideShipHUD`, `HideOnFootHUD`, `RestoreOnFootHUD`; `UAirshipHUDWidget` |

Not in this round (other steps): flight feel (problem 4), the green jet / square puffs materials (asset swap), M_Airship /
M_Fire usage flags (saved in the editor). The review of this round (section 11) found the passenger switch broke Exit
(no capsule body), reworked the impact cap into kick budgets and fixed the rest; section 3 describes the result.

## 11. Fix round 3 (2026-11-22, review of round 2): what changed

Adversarial review of round 2, each finding checked in the 5.8 source. Build clean, no warnings
(`_AirshipWork_logs/build_151247.log`; final `build_151817.log` after a teardown guard in `RepairPhysicsState` and the
body / actor-collision columns of `Aura.Airship.Passengers`).
Compile-checked only, not run in PIE yet.

| Finding | Verdict | Change | Where |
|---|---|---|---|
| 1 critical: the ex-pilot has no capsule body after Exit and falls through the lid, the deck and (landed) the ground; same on clients and for the pilot ejected at death | Real. Round 2 switched the attached pilot's capsule QueryAndPhysics -> QueryOnly while its actor collision was off: `RecreatePhysicsState` destroyed the body and made none (`ShouldCreatePhysicsState` is owner-checked), `SetActorEnableCollision(true)` doesn't make one, and `MoveComponent` sweeps only the component's own body. The suggested PIE check (`get_collision_enabled`) reads the flag and would have passed | (a) `ApplyPassengerCollision` does nothing while the actor's collision is off (the entry stays; the checks right after Exit / the client restore apply it with a valid body). (b) A rider leaving with its collision off keeps its entry without a ship until the collision is back (no restore that would destroy the body); the timer runs while entries exist; `IsPassenger` / `GetPassengers` count riders only. (c) `UAirshipSubsystem::RepairPhysicsState`: rebuilds missing bodies after every `SetActorEnableCollision(true)` of the pawn and on every rider check (logged). PIE check `k2_exit_body` in as_30 (trace on the capsule alone, QUERY_ONLY, z held on the hull 2 s, Walking, passenger) | `AirshipSubsystem.cpp` `UpdatePassengers`, `ApplyPassengerCollision`, `RepairPhysicsState`, `FindPassengerEntry`; `AirshipPawn.cpp` `UnboardPilot`, `UpdatePassengerCollision`, `EndPlay`; section 3 |
| 2 minor: the impact cap stops working after a couple of seconds of contact (frozen episode reference, allowance growing without end); spin reversal passes; < 4 fps every frame a new episode; drift kick trimmed | Real (scenario S4: after 10 s landed, round 2 let +18 m/s sideways, +26 m/s up and 60 deg/s through) | Kick budgets per contact (section 3): gains per step from the step's own start, the flight-force part free, the rest from budgets that refill over `ImpactKickRefillTime` 1 s (new) and reset after a gap of max(0.25 s, 2.5 frames); spin gain without the slowing part (a reversal counts from the stop); the wreck gets no free upward change; boost / drift kicks noted by the flight component (`NoteFlightKick`) | `AAirshipPawn::LimitImpactResponse`, `RecordPreStepState`, `AirshipPawnPrivate::SpinGain` / `SpendKickBudget`; `UAirshipFlightComponent::UpdateBoostServer`, `ApplyForces` |
| 3 minor: `SetAutoActivate(false)` at death does nothing and warns 6 times | Real (`UActorComponent::SetAutoActivate` only logs once registered; `RegisterComponentWithWorld` and `UNiagaraComponent::SetAsset` do re-activate on `bAutoActivate`) | `FX->bAutoActivate = false` | `AAirshipPawn::HandleDeath` |
| 4 minor: `ShowShipHUD` marks the HUD shown before it exists | Real | `ShowShipHUD` returns whether the widget is on screen (viewport subsystem first, `CreateWidget`, `AddWidgetForPlayer` / `AddWidget` result); only then `bShipHUDActive`, the owner and the hidden on-foot overlay. A failed try comes again after 1 s (`NextShipHUDAttemptTime`), not every frame; the late overlay search runs only with the HUD shown | `AAirshipPawn::UpdateShipHUD`, `ShowShipHUD` |
| 5 minor: stale harness checks | Partly. `as_21_blueprint.py` (8.75 checks) and the `as_13_cr_eval.py` R2 ramp: real, now 8.5 with the eased input (`eased_elev`: FInterpConstantTo at min(45, err x 8)), PASS at <= 8.75 (carriage contact), WARN to 9.0; as_21 also checks `CannonElevSettleRate` 8. `as_13_cr_eval.py` SWEEP 'CannonElevDeg +8.75': not stale, rejected: it compares the settled rig pose with the Blender test anim A_Airship_TestSweep, whose key there is 8.75 (`rig_build.py`: 8.75 sin(2 pi t) at t = 0.25); 8.5 would fail it. Commented | `Docs/Airship/scripts/ue/as_21_blueprint.py`, `as_13_cr_eval.py` |

Impact cap scenarios (`Docs/Airship/sims/fix3/scenarios.py`, 30 fps, round 2 -> round 3):

| Scenario | Round 2 | Round 3 |
|---|---|---|
| S1 clipping an obstacle at 86 m/s (+26 m/s up), one step / two steps of push | 2.5 / 3.3 m/s up | 3.3 / 4.3 m/s up |
| S2 wreck onto the ground at 68 m/s (18 m/s sideways) | 5.0 m/s sideways | 5.8 m/s |
| S3 wreck bounce (two push steps) | 3.3 m/s, 0.57 m high | 2.6 m/s, 0.34 m |
| S4 10 s landed, then a pop (+18 sideways, +26 up, 60 deg/s) | 38 m/s (+18), 26 up, 60 deg/s: all through | 25.6 m/s (+5.6), 3.3 up, 23 deg/s |
| S6 drift kick (600 cm/s) while scraping at 30 m/s | 35.0 (trimmed 1 m/s) | 36.0 (noted; 35.8 if not) |
| S7 spin reversal 30 -> -30 deg/s; spin axis turned 30 yaw -> 30 roll | -30 / 30: through | -23 / 23 |
| S8 5 fps, 3 steps of +10 m/s push | +15 m/s | +9.5 m/s |
| S9 boost scrape 3 s; S10 take-off from landed; S11 yaw spin-up while scraping | untouched | untouched |
| S12 wedge push 200 cm/s every step for 1 s | +29 m/s | +35 m/s (section 8) |

## 12. Validation session (2026-11-22, after round 3): what changed

Editor validation of rounds 2-3 plus the asset items of the first smoke test. Results, numbers and captures:
`Docs/Airship/reports/pie_validate.md` (harness `Docs/Airship/scripts/ue/as_43_pie_validate.py` = as_30 + deck / HUD / bump /
wreck checks; X window grabs of the PIE viewport for the HUD with `scripts/harness/xgrab_loop.sh`, read-only X calls).

| Item | Change | Where |
|---|---|---|
| Ship HUD panel / tags drawn white: the facing side's PORT / STBD ink tag and the boosting BOOST tag were invisible (paper text on white) | `FSlateDrawElement::MakeBox` fills a RoundedBox brush with the element tint alone (it never reads the brush's TintColor; widgets multiply `GetTint` in themselves): `Box()` now passes `Brush.GetTint(InWidgetStyle) * Tint * Opacity`, so the paper panel, ink shadow, bar tracks and ink tags get their colours | `AirshipHUDWidget.cpp` `NativePaint` (`Box` lambda) |
| The BOOST ink tag cut the T off | tag width = measured "BOOST" + 8, clamped to [LabelWidth - 4, LabelWidth] (never into the bar) | `AirshipHUDWidget.cpp` `NativePaint` |
| Assets (no C++): jet / puff materials, M_Airship skeletal-mesh usage saved, PM_AirshipHull restitution 0.08 combine Min + override, CR_Airship death kick x0.5 (spin x0.6) + CCD on the fast Wreck bodies | see pie_validate.md | `as_41`, `as_42`, `as_12` V1/V2 |

Builds: `_AirshipWork_logs/build_155203.log` (HUD tint), `build_155938.log` (BOOST tag), both clean.

## 13. Multiplayer PIE test (2026-11-22, Play As Listen Server + 1 client)

Results, numbers and captures: `Docs/Airship/reports/mp_test.md` (harness `Docs/Airship/scripts/ue/as_45_pie_mp.py`, the
replication comparison `as_46_pie_mp_rep.py` / `as_47_pie_mp_rep_fix.py`, play mode switch
`scripts/harness/set_play_mode.sh listen 2|standalone` with the editor closed, X grabs `scripts/harness/xgrab_mp.sh`).
Boarding (F), flying, cannons, exit (F), death + eject, the host's gun and a host-piloted ship with the client on deck all
work over the network; the C++ changes:

| Finding | Change | Where |
|---|---|---|
| `DebugSetInput` on the client's ship only moved the client's cosmetics: the pilot's machine still sent its (idle) keys, so the server never flew it (test hook; `Aura.Airship.Input` in a client window the same; found by reading the code before the first run, fixed before it) | On the pilot's machine the debug controls replace the keys in `GatherLocalInput` and go out through `SetLocalInput` -> `ServerSetPilotInput`; `SelectControls` takes `LocalInput` first on the pilot's machine, `DebugInput` only on the server's copy of a client-piloted or empty ship. Listen host / standalone unchanged (same controls, now with the aim bits) | `AAirshipPawn::GatherLocalInput`, `UAirshipFlightComponent::SelectControls`, `GetDebugInput` |
| The client's copy of a flying ship juddered: steps alternating ~145 / 165 cm at 50 m/s (accel noise 10.5-11 cm/frame^2 against 1.8-2.0 on the server, ~165 snaps over 10 cm/frame^2 in 14 s). The net driver schedules the next update 1/NetUpdateFrequency + rand x server tick ahead (`UNetDriver::ServerReplicateActors`), so at a 30 Hz server about every other frame is skipped, and Default replication chases a target that moves in uneven steps | `bReplicateEveryFrame` (default true): `ForceNetUpdate` in Tick on the server while the hull is awake (not standalone). Client accel noise 2.36 (median 1.6 = the server's), view (ship minus the pilot's camera) 3.6 from 12.4, snaps 4 per flight; the client watching a host-piloted ship 1.35 from 4.96. With Net PktLag=100 each way: median 3.4 from 11-13, mean 7.9-12.7 (packet bursts) | `AAirshipPawn::Tick`, `bReplicateEveryFrame` |
| `Aura.Airship.RepMode 1`: the client copies were never corrected under PredictiveInterpolation (they coasted 290-690 m off over 4 flights); the project has Physics Prediction off | `UpdateRepMode` applies PredictiveInterpolation only with `UPhysicsSettings::PhysicsPrediction.bEnablePhysicsPrediction`, else stays on Default and warns once | `AAirshipPawn::UpdateRepMode` |

Builds: `_AirshipWork_logs/build_161635.log` (DebugSetInput), `build_164949.log` (every-frame replication + RepMode
guard), both clean.

## 14. Control schemes (2026-11-23)

Four ways to fly the ship in one build: Classic (v1), Galleon, Sky Racer and Point & Fly. Design, tuning and the bench
numbers are in `Docs/Airship/controls/`: `IMPLEMENTATION_PLAN.md` (the change list this code follows), the three
`SCHEME_*.md` specs, `BASELINE.md` (v1 and the base fixes) and the Python bench in `controls/sims/`. **Status:** built
clean on the first try (2026-11-22 22:24 UTC), PIE pass 1 for all four schemes (`controls/PIE_RESULTS.md`), judged:
**Point & Fly won and is the default** since the polish of 14.12 (built clean 2026-11-23 01:03 UTC; the final play
test of that build: `controls/PIE_RESULTS.md` "Final"). Classic, Galleon and Sky Racer stay switchable: console
`Aura.Airship.Scheme <0-3>` on the server (0 Classic (v1), 1 Galleon, 2 Sky Racer, 3 Point & Fly; section 6), the
`ControlScheme` property (BP_AirshipPawn's Details panel, Airship > Controls) or `SetControlScheme` (14.3). User docs:
`Docs/Airship/HOW_TO_FLY.md` (v2: keys, HUD and moves per scheme), `controls/RESULTS.md` (what was built, tested,
judged and polished), `controls/README.md` (the folder index).

### 14.1 The schemes

| Scheme (`EAirshipControlScheme`) | W / S | A / D | Q / E | X (brake) | Mouse / right stick | Aim (RMB / LB) |
|---|---|---|---|---|---|---|
| `Classic` = 0, "Classic (v1)" | throttle pedal | turn | sidestep | brake; + A/D = drift | free look, recentres | FOV -15 |
| `Galleon` = 1 | engine telegraph: one notch per press (ASTERN, STOP, SLOW, HALF, FULL), held = auto-step, STOP is a detent; the ship holds the ordered speed | helm with "meet her" | sidle | air brake, then the order resumes; + A/D = stern swing | ship-relative camera; past 55 deg off the bow = beam watch | broadside stations (level gun deck, helm x 0.5), also from beam watch within 6 s of an own broadside |
| `SkyRacer` = 2, "Sky Racer" | W drive, S progressive brake (reverse below 3 m/s) | fast planted turn | sidestep | brake; + A/D above 15 m/s = drift that charges a 3-tier mini-turbo, released with X | chase camera that looks into the turn | gun deck |
| `PointFly` = 3, "Point & Fly" (**the default**) | drive / firm slow-down | sidestep | turn the heading target | brake; with a big turn left = brake-drift (kick only up to cruise) | **the camera yaw is the heading target**; at rest with no key it only looks (parked free look) | free look, the ship holds its heading; for 6 s after an own broadside the gun lock keeps a broadside on an aim 55-150 deg off the bow (Fire held was meant to arm it too, but is never read: 14.12 P4 note) |

All four share the base fixes of BASELINE 4f (off in Classic), the shared mechanisms of IMPLEMENTATION_PLAN 1.9 and
one feedback implementation (camera shake, FOV punch, camera roll, rumble; off in Classic).

### 14.2 What runs where

| Part | Pilot's machine | Server | Observers |
|---|---|---|---|
| The scheme | applies the preset (OnRep or host) | owns `ControlScheme`, applies the preset | apply the preset (OnRep) |
| Galleon telegraph, beam watch, stations flag | `GatherLocalInput` (`UpdateGalleonOrders`): the order rides `Throttle` as a code, stations ride `Buttons` bit 4 | reads them | - |
| Galleon speed loop, order pulses, stern swing | `ShapeControls` (`ShapeGalleon`) | the same, plus the forces | the same from `RepInput` |
| Sky Racer drift state machine (charge, tier, chain, turbo, S-brake ramp) | `ShapeControls` (`ShapeSkyRacer`), from its own controls | the same; pays the turbo kick and fuel (`ApplyForces`) | the same from `RepInput` |
| Point & Fly camera -> heading target, gun lock, lock lead | `UpdatePointFlyCamera` at the start of `GatherLocalInput`; sends `HeadingTarget`, and its own copy of the heading loop's steer (its wheel / fans / bank) | runs `ComputeHeadingSteer` on the authoritative hull and writes `Controls.Steer` before `RepInput` | shape the server's steer |
| Forces (every scheme, every base fix) | - | `ApplyForces` | - |
| Camera, feedback, HUD | `UpdateCamera`, `UpdateFeedback`, `UAirshipHUDWidget` | - | - |

### 14.3 Switching and the preset table

* `AAirshipPawn::ControlScheme` (EditAnywhere, BlueprintReadOnly, `ReplicatedUsing = OnRep_ControlScheme`, every
  connection; default **Point & Fly** since the polish, 14.12; Classic before. The tunables' class defaults are still
  v1, so the Classic preset is unchanged). `SetControlScheme(NewScheme)` (BlueprintCallable): authority applies, replicates and
  `ForceNetUpdate`s; a client only logs a warning. `GetControlScheme()` (BlueprintPure). From Python:
  `ship.set_control_scheme(unreal.AirshipControlScheme.SKY_RACER)`.
* Applying (`ApplyControlScheme`, private): BeginPlay (after the components), `SetControlScheme`, `OnRep_ControlScheme`
  (only after BeginPlay). Steps: `ApplySchemePreset`, `Flight->SetActiveScheme` (the flight model's copy,
  `UAirshipFlightComponent::ActiveScheme`, which every scheme branch tests), `OnTuningChanged`, `ZoomTarget =
  CameraArmLength` (the arm eases there), `ResetSchemePilotState`, the camera component's relative transform zeroed,
  the FOV filter re-synced, `RefreshShipHUDLayout`.
* **The preset table** is in `AirshipPawn.cpp`: the X-macro lists at the top (`AIRSHIP_FC_*_PROPS`,
  `AIRSHIP_PAWN_*_PROPS`, `AIRSHIP_BOOM_SCHEME_PROPS`: every scheme-owned property), `ApplySchemePreset` (copies all of
  them from the archetype: the Blueprint class defaults, which override none of them, so Classic is v1 by
  construction and switching is order-independent) and `ApplyGalleonPreset` / `ApplySkyRacerPreset` /
  `ApplyPointFlyPreset` (plain assignments of the values that differ from Classic, as in IMPLEMENTATION_PLAN 1.13).
  A level instance's own overrides of these properties are discarded on every apply.
* Scheme-only tunables (`Galleon*`, `Sky*`, `PF*` on the flight component and the pawn) default to their scheme's
  value and are only read under that scheme. Tunables are never replicated: every machine writes the same preset.
  `Aura.Airship.Set` stays per machine and lasts until the next scheme apply.

### 14.4 Wire and replication

* `FAirshipPilotInput::HeadingTarget` (uint16, +2 bytes per packet): Point & Fly's heading target, 1..65534 = the
  yaw, 0 = none (so neutral input never means "head north"). Not in `SameControls`: it rides the `InputSendRate`
  heartbeat like `AimPoint`. `EncodeHeading`, `HasHeadingTarget`, `GetHeadingTargetDeg`.
* `Airship::Button_Stations` (bit 4): Galleon's broadside stations; only read under Galleon.
* Galleon's order on `Throttle`: `AirshipGalleon::NotchToThrottle` (-127, 0, 42, 85, 127) / `ThrottleToNotch`, a
  latched code (a lost packet changes nothing). Neutral input = STOP. Server timeout under Galleon: the last accepted
  packet is kept with helm, lift, sidle and buttons neutral (`LastGoodServerInput`), so a hiccup costs the helm, not
  the speed.
* `DebugSetInput` / `Aura.Airship.Input` carry no heading target and no stations bit: Classic-style cross-checks in
  every scheme (under Galleon the throttle value is the order code: 1 FULL, 0.67 HALF, 0.33 SLOW, 0 STOP, -1 ASTERN).
* Switch window (half a round trip before the client's OnRep): Galleon reads Classic throttle values as order codes (at
  most one notch of lurch); Point & Fly uses a packet's Steer axis when it carries no target. No scheme id in the packet.

### 14.5 Reset rules

| Event | Machine | Flight component | Pawn (pilot side) |
|---|---|---|---|
| Scheme applied | all | `SetActiveScheme` -> `ResetSchemeState(true)` (also the v1 drift timer) | `ResetSchemePilotState(true)`: Galleon's notch from the speed (`NotchForSpeed`), camera transform zeroed |
| Pilot changes (`OnRep_PilotCharacter`, also called by the server at board / exit) | all | `ResetSchemeState(false)` | `ResetSchemePilotState(false)`: Galleon rings STOP |
| Local player boards (`UpdateLocalMappingContext` adds the IMC) | pilot | - | `ResetSchemePilotState(false)` + `bPendingCameraReset` |
| Possession change (`PossessedBy` / `UnPossessed` -> `ResetInput`) | server | `ResetSchemeState(false)`, `LastGoodServerInput` cleared | - |
| Death (`SetFlightEnabled(false)` -> `ResetInput`; every frame while dead) | all | `ResetSchemeState(false)` | `ResetSchemePilotState(false)` in `HandleDeath` |
| Debug input on the pilot's machine | pilot | - | Point & Fly: `bPFValid = false` every frame |

`ResetSchemeState` never touches the hold altitude, the pod spool, the boost latch, the fuel or the shaped controls
(no jump in forces or cosmetics). `SkyTurboEventCount` keeps counting (the pawn and the HUD detect releases by its
change). A Sky Racer drift in progress is dropped without a turbo.

### 14.6 Telemetry (`FAirshipFlightTelemetry`, `GetFlightTelemetry()`)

| Field | Type | Meaning |
|---|---|---|
| `Scheme` | uint8 | the flight model's `ActiveScheme`, every machine |
| `ThrottleOrder` | float | Galleon: -1 ASTERN, 0 STOP, 1/3 SLOW, 2/3 HALF, 1 FULL (every machine, decoded from the controls); else -2 |
| `DriftCharge` | float | Sky Racer: 0..1 while drifting (every machine runs the drift); else 0 |
| `bHeadingTargetActive`, `HeadingTargetDeg` | bool, float | Point & Fly: pilot = its own target (with the lock lead), server = the received one, observers = from `RepInput`; else false / 0 |
| `bFreeLook` | bool | false only in Point & Fly's steering mode (pilot: Aim up; others: the Aim bit). The parked free look (14.12 P3) is not in it: `AAirshipPawn::IsPFParked()` |
| `DriftDir`, `DriftTier` | int32 | Sky Racer: drift direction, the tier of the charge (no grace); other schemes: the v1 drift / swing direction, tier 0 |
| `TurboAlpha`, `TurboChain` | float, int32 | Sky Racer: burn left 1 -> 0, chain links of the current / last drift; else 0 |
| `bGunDeck` | bool | the steady gun deck (Galleon: stations bit; others: Aim) |
| `bGunLock` | bool | Point & Fly gun lock (pilot's machine only) |

`Aura.Airship.Telemetry` prints them on a second line per ship (section 6).

### 14.7 Feedback (pilot's machine)

One implementation for every scheme (`AddFeedback`, `PlayRumble`, `UpdateFeedback` at the end of `UpdateCamera`), all
off in Classic: trauma shake on the camera component (`ShakeRotDeg`, `ShakeLocCm`, `ShakeFrequency`, `ShakeDecay`;
Perlin noise on the relative rotation / location, never the control rotation), a FOV punch added after the FOV
interpolation (`FOVKickDecay`, `FOVMaxDeg`), camera roll (`CameraRollPerBank`, `CameraRollPerSteerDeg`,
`CameraRollMaxDeg`, `CameraRollInterpSpeed`), rumble through the native `APlayerController::PlayDynamicForceFeedback`
overload (`RumbleScale`), a drift trauma floor and continuous rumble (`DriftTrauma*`, `DriftRumble*`) and hull-hit
shake / rumble (`ShakeHitPerMS`, `ShakeHitMax`, `RumbleHitPerMS`). Per event an `FAirshipFeedbackEvent` (trauma, FOV
kick, rumble, rumble time, large motors): `FeedbackBoostStart`, `FeedbackOwnBroadside` (`HandleCannonsFired` on the
pilot's machine), `FeedbackDriftKick` (the v1 drift / Galleon swing exit), `FeedbackTurbo1/2/3`, `FeedbackOrderChange`
(Galleon telegraph, FOV sign = direction), `FeedbackLockEngage` (Point & Fly). With everything at 0 the camera's
relative transform is never written and the FOV path is v1's exactly.

### 14.8 HUD

* The panel (`UAirshipHUDWidget`) reads the ship's scheme every frame. Galleon (+`GalleonExtraHeight` 78): the
  telegraph row (the ordered notch inverted, a blink on a change, STEAM on FULL while boosting), a speed rule (fill =
  forward speed, hollow triangle = the ordered speed), the helm row (needle, turn rate, SWING / STATIONS tags) and the
  facing side's in-arc outline / FIRE. Sky Racer (+`SkyRowHeight` 26): the DRIFT / TURBO row (charge or burn, tier
  colour and I / II / III, chain xN, an outline flash on a release). Classic and Point & Fly: the v1 panel.
* After a switch the pawn re-applies the panel's viewport slot at the new size (`RefreshShipHUDLayout`,
  `UGameViewportSubsystem::SetWidgetSlot`); no hide / re-show.
* Point & Fly adds a second widget in overlay mode over the whole viewport (`ShipOverlayWidget`, ZOrder 0): a 24 px
  crosshair (steering; faded while parked) or the gun ring with brackets (broadside: the ring solid in the arc and
  dashed out of it, filling amber while the facing side reloads in the arc, the brackets amber in the arc and loaded),
  the nose chevron (projected with `UWidgetLayoutLibrary::ProjectWorldLocationToWidgetPosition`) with an amber line to
  the centre while the turn still to come is over 3 deg (not while parked), the heading strip (broadside: +-180 deg
  around the bow with both guns' arcs, the aim ring and the heading-target diamond), the LOCK tag with the swing arrow,
  the boarding hint (at least 8 s and until Aim has been held once, at most 45 s; once per local player and session)
  and the contextual "HOLD RMB / LB TO LOOK" hint (14.12 P6, P7). All marks are lines and the engine font (no assets).

### 14.9 How to add a scheme

1. Add the enumerator to `EAirshipControlScheme` (`AirshipTypes.h`), with a `DisplayName`.
2. New tunables: flight component or pawn UPROPERTYs whose default is v1-neutral (shared) or the scheme's own value
   (scheme-only, read only under `ActiveScheme == NewScheme` / `ControlScheme == NewScheme`). Add each one to the matching
   X-macro list at the top of `AirshipPawn.cpp`, so every apply resets it and `Aura.Airship.Scheme check` sees it.
3. Write `ApplyNewSchemePreset()` (assignments of the values that differ from Classic) and call it from the `switch`
   in `ApplySchemePreset`.
4. Behaviour: shaping in a `ShapeNewScheme` branch of `ShapeControls` (it must set `bShBrake`, `bDrifting`,
   `ShBrakeAmount` and the throttle target), forces in `ApplyForces` gated by `ActiveScheme`, pilot-side input in
   `GatherLocalInput`, camera in `UpdateCamera`. Anything the server needs from the pilot's keys or camera goes into
   `FAirshipPilotInput` (a small quantized field or a free `Buttons` bit: bits 5-7 are free).
5. Runtime state: reset it in `UAirshipFlightComponent::ResetSchemeState` / `AAirshipPawn::ResetSchemePilotState`.
6. Telemetry, HUD (`GetPanelSize` / `NativePaint` by `LayoutScheme`), `Aura.Airship.Scheme` (its range check and help
   text), this section, and a bench plug-in in `controls/sims/` (`scheme_template.py`).
7. Check: `Aura.Airship.Scheme 0` then `Aura.Airship.Scheme check` must print 0 differences.

### 14.10 Where the code differs from IMPLEMENTATION_PLAN.md

* Sky Racer's nozzle roll into the slide is added after the v1 cone limit and the result is limited again, as the
  bench's `SkyFlightModel.compute_gimbals` does (the plan and the spec say "before the cone clamp"; with the throttle
  lean saturated in a drift that would lose most of the roll on the front pods, and the bench numbers were made with
  the bench's order).
* Galleon's look-ahead follows the shaped helm (`GetShapedSteer`, as the bench), the camera roll the cosmetic steer
  (`C.Steer`, x1.3 in a swing), as the plan writes.
* Point & Fly: a control yaw change under 0.001 deg counts as no change (the float round trip through the
  PlayerController), so the external-set rule only fires on a real set. The gun lock also reports its swing direction
  (`GetPFLockSwingDir`, for the LOCK arrow).
* The shake's Perlin time is wrapped mod 256 (the noise's period), so it keeps its precision in a long session; rumble
  intensities are clamped to 1.
* Helpers not named in the plan: `GetSchemePropertyDifferences` (the `check` command), `MeasureHullImpactSpeed` (the
  damage's impact speed, shared with the hull-hit feedback), `UAirshipHUDWidget::RefreshLayoutScheme`,
  `AddShipOverlay` / `RemoveShipOverlay`.
* The Point & Fly overlay draws its gun ring with lines, not with two rounded-box brushes.

### 14.11 Pre-build review (2026-11-23)

A review of the unbuilt code and of the PIE harness `Docs/Airship/scripts/ue/as_50_pie_controls.py`, before the first
build. No compiler, UHT or editor was allowed, so the code was read against the UE 5.8 headers and checked with
scripts. **Result: no compile error and no logic error found in the schemes; one robustness fix.**

| Check | How | Result |
|---|---|---|
| Declarations vs definitions | script over the three headers and their .cpp files (both ways) | all match (signature and const) |
| X-macro preset lists | every name a public UPROPERTY of the flight component (160), a pawn UPROPERTY (85) or a `USpringArmComponent` member (4); every assignment in `Apply*Preset` in a list; every new tunable in a list | complete: switching Galleon -> Classic restores every value a preset writes |
| Preset values | script: `Apply*Preset` against the IMPLEMENTATION_PLAN 1.13 table; Classic column against the header / constructor defaults | all equal |
| UE 5.8 APIs | `PlayDynamicForceFeedback` (the 6- and 8-argument native calls can't bind to the latent one: a `uint64` is no `FLatentActionInfo`), `FindFProperty(UStruct*, const TCHAR*)`, `Identical_InContainer` / `ExportTextItem_InContainer` (`TNotNull<const void*>`), `GetMassSpaceLocal`, `GetInertiaTensor`, `GetPhysicsAngularVelocityInDegrees`, `SetWidgetSlot`, `FGameViewportWidgetSlot` defaults, `ProjectWorldLocationToWidgetPosition`, `MakeLines(TArray<FVector2f>)`, `TArray` initializer lists, spring arm members, `UEnum::GetDisplayValueAsText` | all as used |
| Warnings that are errors here (`-Wall -Werror -Wshadow -Wundef -Wunreachable-code-aggressive`, from the build's .rsp) | heuristic scan: locals against outer locals, locals and parameters against own and engine base-class fields; new `#if`s; code after `return`; discarded `[[nodiscard]]` results; `UE_LOG` / `Printf` specifiers against their arguments | none found |
| Unity build | the new helpers (`WrapDeg`, `ApproachExp`, `MakeFeedback`, `MakeCornerSlot`, `ArcPoints`, `PointFlyHintSeen`) are only in the three named namespaces; no file-scope `using namespace` in `Source/Aura` | no clash |
| Classic = v1 | every changed code path compared with `git diff` | v1 arithmetic in `ShapeControls`, `ApplyForces`, `ComputeGimbals`, `UpdateCosmetic`, `UpdateCamera`, `UpdateFX`, `LimitImpactResponse`, `OnHullHit` (new terms are `x * 1` or `x + 0`). The only extra work: BeginPlay's scheme apply runs `OnTuningChanged` once more, so `ApplyBodySettings` sets the same mass and centre of mass a second time (idempotent; float noise in the COM nudge at most) |
| Multiplayer | the pilot-side state, the wire fields, OnRep before / after BeginPlay, late joiners, the switch window, host pilot vs client pilot | as IMPLEMENTATION_PLAN 1.3 |
| Stability, guards | every new loop is an exact exponential filter or a time-based timer; every new division has a floor | no NaN or zero-divide path found |
| Harness | protocol self-test against the bench (`as_50_protocol.py --selftest` for all four schemes: 0 differences); mock PIE (`as_50t_mock_pie.py`) standalone with all four schemes and the listen pass with two (0 script errors, 0 TEMP actors left, settings restored); every `unreal` name compared with as_30 / as_43 / as_45, which ran (the names those don't use, `StaticMeshActor`, `ComponentMobility`, `spawn_actor_from_object`, `set_actor_scale3d`, `set_collision_profile_name`, `set_material`, `get_control_rotation`, `get_aim_side` and the two scheme UFUNCTIONs, are all engine or Aura UFUNCTIONs / types that exist) | OK; CONTRACT names (telemetry fields, `AirshipControlScheme.CLASSIC / GALLEON / SKY_RACER / POINT_FLY`, the `check` and inertia log lines) match the C++ |

Fix made: `ResetSchemePilotState(true)` sets Galleon's notch (`NotchForSpeed`) from the hull's live forward speed
(the expression `UpdateFlight` uses), no longer from the cosmetic state, which is last frame's and was stale right
after a teleport (a scheme apply just after a teleport from cruise would have rung FULL). The harness's 2-frame wait
before its re-apply stays as a margin; its comment and TEST_PROTOCOL.md 3.1 say so.

Checked and right as written: Point & Fly's start-frame guard in `UpdatePointFlyCamera` (no look delta on the frame
the target is re-initialised: without it, boarding would read the character's old control yaw as an outside set and
send the target there); the gun lock and the lock lead against the bench's `arc_assist` / `pilot_input`; the
Galleon telegraph, detent, beam watch and stern swing against `scheme_galleon.py`; Sky Racer's state machine, drift
forces, turbo and gimbal order against `scheme_skyracer.py`; the shared base fixes and the hull-axis tensor against
the bench's `TENSOR_ACTOR` form.

To watch in the first build and PIE (not errors, the places a compiler or the engine could still disagree with a
reader): the X-macro expansions in `AirshipPawn.cpp` (one long list; a typo there is a compile error in a macro),
the HUD's braced point lists passed to the `Lines` / `Stroke` lambdas, the inertia line of `Aura.Airship.Telemetry`
(IMPLEMENTATION_PLAN 5.4: principal moments about (6.86, 1.10, 6.57) e10 kg cm²) and `Aura.Airship.Scheme check` = 0
after `Aura.Airship.Scheme 0`.

### 14.12 Polish after judging (2026-11-23): Point & Fly is the default

Three judges ranked the schemes on PIE pass 1 and the bench (weighted totals: Point & Fly 22.31, Sky Racer 22.07,
Galleon 21.17, Classic 14.03). The winner became the default and got the changes below: tuning values first, three
small mechanics where the judges agreed and the bench showed the gain. Each one was modelled in the bench first
(`controls/sims/scheme_pointfly.py`, checks `exit kick park rival m12cam` in `pointfly_checks.py`); the design notes and
the rejected ideas are in `SCHEME_POINTFLY.md` "Review changes", "Polish after judging". **Built clean** (01:03 UTC,
0 new warnings). **Verified in PIE** 01:14-02:07 UTC (`controls/PIE_RESULTS.md` "Final"): a fresh ship starts in Point
& Fly, 17/17 standalone and 9/9 client-pilot runs, every polish check met, Classic still v1 (`check` 0 differences).
The verify step found one HUD bug and fixed it (F1, last row), built clean at 02:01 UTC (`build_020125.log`).

| # | What | Where | Old -> new |
|---|---|---|---|
| P0 | Default scheme | `AAirshipPawn::ControlScheme` initializer (AirshipPawn.h); the HUD's first `LayoutScheme`; the enum comment; the `Aura.Airship.Scheme` help | Classic -> **PointFly**. No tunable's class default changed, so `Aura.Airship.Scheme 0` + `check` still lists 0 differences. `UAirshipFlightComponent::ActiveScheme` stays Classic until the pawn applies its scheme (its tunables are v1 until then). `BP_AirshipPawn` and `L_AirshipTest` can't override it: neither file (unchanged since 90e164b, saved before the property existed) has the name `ControlScheme` in its name table |
| P1 | Drift-kick cap: the kick only tops the ship up to cruise | new FC tunable `DriftBoostCapSpeed` (0 = off, the v1 kick) + `GetDriftKickDV(Vf)`, used in `ApplyForces` and by the pilot's drift-kick feedback (scaled by the share paid) | 0 (all schemes) -> **4800 cm/s** in the Point & Fly preset |
| P2 | A fast turn stops where the pilot looks | Point & Fly preset (shared tunables) | `GyroYawMax` 0.5 -> **1.0** rad/s²; "meet her" `KrSteady` 0 -> **5.5** /s, `AlphaYawMaxSteady` 0 -> **1.5** rad/s² |
| P3 | Parked free look: at rest the mouse only looks; the first drive / sidestep / turn / boost key takes the camera's yaw as the heading (the 150 deg reach clamp keeps the camera still) | new pawn tunable `PFParkSpeed`; `UpdatePointFlyCamera` (new arguments `bMoveKeys`, `bFireHeld`), `bPFParked`, `IsPFParked()` (BlueprintPure) | new, **300 cm/s** (0 = off). An outside set of the control rotation (harness, reset) still sets the heading while parked |
| P4 | The gun lock is armed only while Fire is held or for a while after the pilot's own broadside (`LastOwnBroadsideTime`), so Aim alone is a clean free look. **Note:** the Fire-held half never fires (below) | new pawn tunable `PFLockArmTime`; `UpdatePointFlyCamera` | new, **6 s** (0 = always armed, pass 1) |
| P5 | Lock lead for a crosshair-held target | `PFLockLeadTime` | 0.45 -> **0.6 s** |
| P6 | Overlay legibility and the broadside strip | `UAirshipHUDWidget::PaintPointFlyOverlay` / `RefreshOverlayValues` | crosshair 14 -> 24 px (2 px lines; faded while parked); nose chevron 10 -> 18 px; gap line 1 px ink -> 2 px amber with an ink outline (hidden while parked); LOCK tag 1.5 x (font 11 -> 16); heading strip +-60 deg around the camera at 3 px/deg -> **+-180 deg around the bow** at 1.5 px/deg, ticks every 30 deg, the two guns' arcs (beam +-`CannonYawLimitDeg`, the facing side amber in arc and loaded), the aim as a ring, the heading target as a diamond, the bow fixed at the centre |
| P7 | Look hints | same | boarding hint 8 s -> at least 8 s and until Aim has been held once (at most 45 s); new contextual "HOLD RMB / LB TO LOOK" under the crosshair while steering with the camera more than 50 deg off the nose for 0.3 s, until Aim has been held once (per local player and session: `PointFlyLookLearned`) |
| - | Comment fix | `HullPhysicalMaterial` (AirshipPawn.h) | "restitution 0.35 suggested" -> PM_AirshipHull's real values: friction 0.2, restitution 0.08, combine Min + override (as_42) |
| - | Harness | `as_43_pie_validate.py`, `as_45_pie_mp.py` (`start_settle`: `AS43_SCHEME` / `AS45_SCHEME`, default 0 = Classic, the v1 checks), `as_50t_mock_pie.py` (mock ship starts in Point & Fly), `_AirshipWork_logs/run_controls_pie2.sh` comment | they used the pawn's default scheme. as_45 sets only the first ship: its second ship (`Aura.Airship.Spawn`) starts in Point & Fly, so `e3_hud_host_flying` sees 2 HUD widgets even in a Classic run |
| F1 | Overlay text plates sized at the paint scale (verify step) | `AirshipHUDWidget.cpp`: new `AirshipHUDPrivate::MeasureWidthAtScale` (`FSlateFontMeasure::Measure` at the paint geometry's accumulated layout scale, divided by it), used by the overlay's `Tag` (LOCK, "HOLD RMB / LB TO LOOK") and the two boarding-hint rows in `PaintPointFlyOverlay` | the text was measured at scale 1 but drawn at the viewport's DPI scale (about 1.12 in PIE), where the rounded glyph advances made it about 7 % wider: "Q/E TU\|RN" ran past its plate. The v1 panel keeps `MeasureWidth`, so Classic's HUD is unchanged. Seen fixed on the client's boarding grab (as_45, another window size) |

**P4 note (docs step, from the code):** `GatherLocalInput` passes `Button(FireAction)` as `bFireHeld`, but
`Button` reads `UEnhancedInputComponent::GetBoundActionValue`, which only knows the actions bound with
`BindActionValue`. `SetupPlayerInputComponent` binds Throttle, Steer, Lift, Strafe, Boost, Brake and Aim that way and
`IA_AirshipFire` only with `BindAction(..., Started, OnFireInput)`, so the value is always false (the engine returns
zero for an unbound action, EnhancedInputComponent.cpp:106). In play the lock is armed only for `PFLockArmTime` after
each own broadside; a press fires at once when the facing side is loaded, so the gap is small (holding Fire past those
6 s does not keep it armed). The bench's charge check holds Fire, so it models the intended rule. One-line fix: add
`FireAction.Get()` to the `BindActionValue` list in `SetupPlayerInputComponent`. Not changed here (docs only).

Bench (pass 1 -> polish; `pointfly_metrics_pass1.json` / `pointfly_checks_pass1.json` keep pass 1):

| Check | Pass 1 | Polish |
|---|---|---|
| Kick snake: 1.23 s brake-drifts, 0.1 / 0.4 s gaps; 1.5 s drifts (W held: 48.0 m/s) | 71.5 / 57.7 / 60.5 m/s | 48.8 / 47.4 / 48.1 m/s |
| 180 deg brake-drift reversal: speed 8 s later, kick paid | 47.9 m/s, 6 m/s | same |
| M9 drift exit (PIE m9 protocol): overshoot, host / 100 ms | 8.63 / 11.62 deg | 1.67 / 6.33 deg; within 0.5 deg after 1.07 s (was 1.8) |
| 179 deg brake-drift reversal overshoot | 2.9 deg | 0.3 deg |
| Camera orbit 360 deg in 4 s at hover, no keys: hull turn during / 6 s later | 111 / 100 deg | 0 / 0 deg |
| Aim held 3 s on a rival 60 or 120 deg off the bow, no Fire | 26.9 deg swing, 62 m off the line | 0 deg, 0 m |
| M12 with the PIE-calibrated camera, precise: harness bot / a hand on the crosshair | -7.38 / -2.92 deg (PIE -7.39) | -4.71 / -0.19 deg |
| Steps, sweeps, M1-M8, M10, the racing pass | - | unchanged (M4 t63 0.43 s, no overshoot) |
| M11 course (0 / 100 ms): precise, sloppy | 59.13 / 60.2, 59.83 / 59.1 s, 0 missed | 59.13 / 60.1, 59.33 / 58.83 s, 0 missed |
