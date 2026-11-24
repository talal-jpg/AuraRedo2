# Round 2, PR A: core notes

The core part of `SPEC_A.md`, in two passes:

* **Pass 1.** D5 gunner stations, D6.7 the ship side of the turrets, D10 the console and test hooks. Four small parts of
  other decisions sat in code that pass 1 rewrote, so they are in it too: the D1 C++ cap, D8 (boarding from under the
  hull), D2's `TraceAimPoint` and spawn offset, and D3's tag on the ship.
* **Pass 2.** D4 crew damage, the rest of D2 (ballistic aim, `CannonballSpeed` 7000), D9 drift and hold, the unpiloted
  telemetry fields, and `PilotSeatFallback` from the Blender step's `turret_dims.json`.

Builds: `_AirshipWork_logs/build_r2.sh` gives Result Succeeded every time (pass 1: `build_r2_132000.log`,
`build_r2_132318.log`; pass 2: `build_r2_133801.log`, then `build_r2_134529.log` after the last edit). None of these
files has a warning; the only warnings in the logs are the old `bIsFocusable` ones in `MainMenu.cpp` / `MainMenu2.cpp`.
**Nothing has run in the editor or PIE yet.**

All line numbers below are in the clone as it is at the end of pass 2.

## Files

| File | What |
|---|---|
| `Source/Aura/Public/Airship/AirshipPawn.h` | station and turret API, replicated arrays, per-cannon clocks, crew damage, ballistic helpers, `DebugKill` |
| `Source/Aura/Private/Airship/AirshipPawn.cpp` | the station and turret code, the per-cannon fire path, D1 cap, D8, `TraceAimPoint`, ballistic aim, crew damage, vitals on exit, drift hooks, telemetry |
| `Source/Aura/Public/Airship/AirshipFlightComponent.h` / `.cpp` | the unpiloted module (D9): `FAirshipUnpilotedTarget`, drift, hold, look-ahead, bow contact, telemetry |
| `Source/Aura/Public/Airship/AirshipPilotComponent.h` / `.cpp` | F (nearest helm or station), mount RPCs, the local gunner (input, camera, aim sends, HUD) |
| `Source/Aura/Public/Airship/AirshipSubsystem.h` / `.cpp` | `FindGunnerStation`, the `Settings.` prefix, the new console commands, the third telemetry line, `Kill` without the crew share |
| `Source/Aura/Public/Airship/AirshipHUDWidget.h` / `.cpp` | gunner mode (its cannon mark follows the ball's arc); on the pilot's panel a PILOT row, a GUNS row and MANNED |
| `Docs/Airship/CPP_NOTES.md` (section 15), `Docs/Airship/HOW_TO_FLY.md` ("Round 2") | the docs of both passes |

## Stations (D5, pass 1)

### Ship state (`AirshipPawn.h`)

* Replicated, COND_None (`AirshipPawn.cpp:398-400`). All three are sized in the constructor (`:369-371`).
  * `StationGunners` (OnRep), 6 entries.
  * `StationAims`, 6 entries.
  * `Turrets`, 2 entries.
* Server only:
  * `StationControllers[6]`, `StationTrigger[6]`, `bStationGunnerWasAlwaysRelevant[6]`.
  * the console aim: `StationConsoleAim[6]` and `StationConsoleAimUntil[6]`.
  * `bDebugTurretFire` with its point.
* Every machine: `StationSeatLocal[6]`, `LocalStationAim[6]` with `LocalStationAimFrame[6]`, and `KnownStationGunners[6]`
  (for the change events).
* Per-cannon clocks replace the per-side ones:
  * `LastCannonFireTime[4]` (server).
  * `LastPredictedCannonFireTime[4]` and `bPredictedShotPending[4]` (clients).
* New UPROPERTYs:
  * `CannonCarriageBones` (`Cannon_L1` .. `Cannon_R2`).
  * `CannonCarriageFallback` (README_rig.md carriages).
* `CannonSpawnForwardOffset` goes from 60 to 80. At runtime the offset is at least the ball's radius + 30
  (`SpawnCannonball`, `:2718`).

### Seats

`RefreshCannonGeometry` (`:2244`) sets the seats on every machine. It runs again after `Aura.Airship.Set`, so a changed
`Settings.CannonSeatOffset` takes effect.

| Station | Seat (hull cm) | Facing |
|---|---|---|
| 0 CannonL1 | carriage (-46.3, -598.5, 243.7) + (-90, +130, 0) = (-136.3, -468.5, 243.7) | -90 (port) |
| 1 CannonL2 | (-1147.2, -392.7, 283.6) + (-90, +130, 0) = (-1237.2, -262.7, 283.6) | -90 |
| 2 CannonR1 | (-46.3, 598.5, 243.7) + (-90, -130, 0) = (-136.3, 468.5, 243.7) | +90 |
| 3 CannonR2 | (-1237.2, 262.7, 283.6) | +90 |
| 4 TurretL | mount (2100, -245, 655) + (-100, 0, 0) = (2000, -245, 655) | 0 (bow) |
| 5 TurretR | (2000, 245, 655) | 0 |

The cannon rows come from the carriage bones when the mesh has them. The fallbacks give the same numbers.
`turret_dims.json` (`mounts.*.gunner_seat_cm`) has the same turret seats.

`GetStationSeatRelativeTransform` (`:1577`) puts the capsule centre at seat + half height + `PilotSeatClearance` (5).

### Mount, dismount, upkeep (server)

* `CanMount` (`:1639`) allows a mount only when all of these hold:
  * the candidate is a living player character with a PlayerState;
  * the station is free and the ship is alive;
  * for a turret station, the turret exists and isn't a wreck;
  * the candidate isn't at any helm and doesn't man another station (`UAirshipSubsystem::FindGunnerStation`,
    `AirshipSubsystem.cpp:166`).
* `IsWithinStationRange` (`:1690`) works in the hull frame, from the seat to the capsule centre:
  * horizontal distance <= `StationMountDistance` 350;
  * vertical -200 .. +600.
* `MountGunner` (`:1704`) follows spec D5.2 steps 1-11:
  * cancels the character's abilities;
  * stops the CMC, then `DisableMovement` and tick off;
  * attaches to `HullCollision` with actor collision kept on;
  * sets `bAlwaysRelevant`;
  * fills the arrays, with the rest aim 100 m along the gun;
  * then `RefreshPassengers`, the change event, `ForceNetUpdate`, `ClientMountChanged` and a log line.
* `DismountGunner` (`:1753`), in order:
  * clears the arrays first;
  * computes the exit: seat + `CannonExitOffset` (Y inboard, mirrored) or + `TurretExitOffset`;
  * drops it onto the hull top. Hull traces start 300, 600 and 900 cm above it; the first one that doesn't start
    inside a convex wins. The turret seats are inside the forward deck's convex.
  * detaches, teleports and restores relevancy, then `RepairPhysicsState`;
  * CMC tick on. If alive: Falling and launched with the ship's velocity, plus up and outboard when ejected;
  * `RefreshPassengers`;
  * `ClientMountChanged(null, -1, exit in hull space, launch)`.
  * An invalid gunner (logout) still gets its PC's input back.
* `UpdateStations` (`:1923`) runs every server tick from `Tick` (`:559-562`). It frees a station when:
  * the gunner is destroyed or dead;
  * its PC no longer possesses it;
  * it is no longer attached;
  * the ship is dead (ejected);
  * the turret is wrecked (ejected).

  It then calls `UpdateTurretCommands`.
* `Die` runs `EjectCrewAfterDeath` (`:3731`) next tick. It flushes the crew damage (pass 2), then ejects the pilot and
  every gunner.
* `EndPlay` (`:467`, Destroyed only): gunners are put down (not thrown), then the turrets are destroyed.
* `CanBoard` (`:1179`) refuses a mounted gunner.
* `IsWithinBoardRange` (`:1206`) has the D8 below-trace.

### Clients

* `OnRep_StationGunners` (`:1991`) turns a gunner's collision back on if `UpdatePassengerCollision` turned it off first.
  The attachment and the array replicate separately.
* `NotifyStationsChanged` broadcasts `OnStationsChanged(Ship, Station, Gunner)` (`:2032`). BeginPlay calls the OnRep
  again for the first bunch.
* `UpdatePassengerCollision` (`:1438`) skips stationed gunners and restores one it caught early.

### Cannons

* `FireCannons` (`:2733`) fires the side's cannons that are unmanned and loaded (`IsCannonLoadedServer`, tolerance
  0.1 s). Every ball of one broadside ignores every other.
* `MulticastCannonsFired(mask)` follows.
* `FireStation` (`:2791`) fires one ball, credited to the gunner (`MakeCannonballSpec(Gunner)`, `:2666`), then
  `MulticastCannonsFired(1 << c)`.
* `MulticastCannonsFired_Implementation` (`:2848`):
  * skips each cannon this machine predicted (pending, and within cooldown + 0.5 s);
  * on a client, sets the reload clock of every cannon it plays from the multicast (see deviation 4);
  * plays the rest.
* `HandleCannonsFired(mask, bLocalShot)` (`:2886`): recoil count, muzzle FX with the D1 cap (weak lambda timer,
  `MuzzleFXMaxSeconds` 1.0, both spawn paths, `:2906-2950`), hull kick, and `BP_OnCannonsFired` (side of the lowest
  cannon).
* `RequestFire` (`:2597`): nothing in the driver turret arc. On a client, the mask is the side's unmanned cannons whose
  local reload is done; an empty mask sends nothing.
* `PredictStationFire` (`:2825`) is the gunner client's prediction.
* `UpdateCannonAim` (`:2554`): a manned cannon always tracks `GetStationAimPoint`. That is the console's aim, this
  machine's own gunner's aim (this or last frame), or the replicated one (`:1607`).
* `IsAimInCannonArc` counts only unmanned cannons. `IsCannonAimInArc` (`:2510`) is new.
* `GetCannonReloadAlpha(Side)`: the minimum over the unmanned cannons, 1 when all are manned.
  `GetCannonReloadAlpha(int32)` (`:2332`) is new.
* `PointFlyGunLock` (`:4927`): a fully manned side behaves as outside the sector.

### Pilot component

* F on foot: `ServerRequestBoard` -> `TryUseNearest` (`AirshipPilotComponent.cpp:367`). The candidates are:
  * the helm of each free living ship, within the old range plus `BoardBelowDistance`, at its distance to the pilot
    seat;
  * each free station in range, at its 3D distance to the seat.

  The nearest wins. A mounted gunner's F dismounts.
* `TryMount` (`:452`): a null ship means the nearest ship with that station free; the range is skipped for the
  console. `TryDismount` (`:498`).
* RPCs:
  * `ServerRequestMount` / `ServerRequestDismount` (`:239`, `:247`) share the board cooldown.
  * `ServerSetGunnerAim` (`:517`, unreliable), `ServerGunnerFire` (`:529`), `ServerGunnerTrigger` (`:544`).
  * `ClientMountChanged` (`:562`).
* `BeginLocalGunner` (`:579`):
  * a client attaches its own copy at the seat with the CMC off;
  * the view starts along the gun (pitch -5);
  * it saves the camera FOV and arm length;
  * it pushes the gunner input and IMC_Airship at priority 1, and shows the HUD.
* `SetupGunnerInput` (`:734`):
  * value bindings for all 11 IMC_Airship actions;
  * Look (sensitivity and invert as on foot);
  * Fire Started / Completed / Canceled;
  * Aim (FOV + `GunnerAimFOVOffset`);
  * Zoom (arm length clamped to 0.5-1.5 x its value at mount);
  * Exit, which dismounts.
* `TickLocalGunner` (`:907`), every frame:
  * the safety net (ship gone, other pawn, not listed);
  * the aim trace (`TraceAimPoint` from the player's view);
  * `SetLocalStationAim`;
  * the turret's local command on a client;
  * aim sends: at most 25 Hz, when it moved more than 5 cm or after the 0.5 s heartbeat. The host calls the ship
    directly.
* `EndLocalGunner` (`:650`):
  * sends the turret a released local command;
  * input and HUD off, camera restored;
  * a client puts its copy at hull TM x exit point, CMC on, Falling, with the launch velocity.

## Turrets on the ship (D6.7, pass 1)

* `SpawnTurrets` (`AirshipPawn.cpp:2057`) runs on the server at the end of BeginPlay when `bSpawnTurrets` is on:
  * the class is `TurretClass`, or `AAirshipTurret` with one warning;
  * the turret is spawned deferred at `FTransform(Mount.Location) * HullTM` with the ship as owner, then
    `InitTurret` and `FinishSpawning`;
  * it is attached with `KeepWorldTransform` (no weld) and its relative transform set to `FTransform(Mount.Location)`;
  * it gets `BulletTargetTag`.
* `UpdateTurretCommands` (`:2163`) sets every turret's command every server tick, rest included. In order of priority:
  * Manned: `{GetStationAimPoint(s), true, StationTrigger[s], Gunner}`.
  * `TurretFire` on: the point, or muzzle + hull forward x 10000.
  * Piloted with an aim point: `{AimPoint, IsAimInArc(AimPoint, 10), FireHeld && |bearing from the hull origin| <= DriverTurretArcDeg + 10, ship}`.
  * Otherwise rest.
* The pilot's machine (`GatherLocalInput`, `:972-981`) does three things:
  * `Button_FireHeld = IsDriverTurretArc() && Fire held`, in every scheme and every input branch;
  * on a client, `UpdateLocalTurretCommands` (`:2218`), with the same arc rule as the server;
  * `IsDriverTurretArc` (`:2115`) needs `DriverTurretArcDeg` > 0, a living unmanned turret, and the view yaw within
    50 deg of the hull yaw.
* `TraceAimPoint` (`:1003`) is used by the pilot's aim (`ComputeLocalAimPoint`, `:986`) and by gunners. It ignores:
  * the ship and its attached actors (recursive);
  * its passengers;
  * every cannonball (traced past them up to 4 times).
* Telemetry (`GetFlightTelemetry`, `:4036`): `StationMask`, `NumGunners`, `TurretHeat` / `TurretHealth` /
  `TurretShots`, `TurretDestroyedMask`, `PilotHealth` (-1 without a pilot), `CannonReadyMask`. The unpiloted fields come
  from the flight component (pass 2, below).

## Crew damage (D4, pass 2)

* **Hook.** `BeginPlay` binds `OnShipHealthChanged` to the ship ASC's Health change delegate on the server, right after
  the attribute init (`AirshipPawn.cpp:437-438`). The init itself is a rise, so it gives nothing.
* **`OnShipHealthChanged`** (`:3220`): a drop adds `loss x CrewDamageShare` (0.25) to `PendingCrewDamage` and queues
  `FlushCrewDamage` for the next tick once (`bCrewDamageFlushQueued`). Hits of one frame add up. It is deferred because
  the change fires inside the damage effect's execution, and ejecting someone possesses and detaches characters. A rise
  (healing, the init) gives nothing back.
* **`FlushCrewDamage`** (`:3242`):
  * The crew is gathered first: the pilot (station -1), then every gunner. Ejecting clears `PilotCharacter` and the
    stations.
  * It skips dead members, and anyone without an ASC carrying `UMyAttributeSet`.
  * If the share is at least the member's Health, they go on foot first: `UnboardPilot(true)` for the pilot,
    `DismountGunner(s, true)` for a gunner. The damage then kills them as on foot (ragdoll, GameMode respawn).
  * Damage: a spec from the **ship's** ASC with `DamageEffectClass` (null: `UAirshipDamageEffect`), level `ShipLevel`,
    context instigator and causer the ship, SetByCaller `SetDamageByCaller`. It is applied with
    `ApplyGameplayEffectSpecToTarget` on the member's own ASC (on the PlayerState).
  * Log: `LogAirshipPawn: <ship>: crew damage <char> 25.0 (0.25 of 100.0)`.
* **Ship death.** `EjectCrewAfterDeath` (`:3731`) calls `FlushCrewDamage` first, so the killing blow's share reaches the
  crew before they are thrown clear. Its queued flush, if any, then finds nothing left.
* **`DebugKill`** (`:3200`, new; `Aura.Airship.Kill` uses it, `AirshipSubsystem.cpp:822`) drops the health to 0 under
  `bSuppressCrewDamage`, then calls `Die`. Why: an admin kill would otherwise give every crew member 25 % of the full
  health (500 for a 2000 HP ship) and kill them, and spec T5.11 expects the gunner to be ejected alive.
  `Aura.Airship.Damage` (`ApplyShipDamage`) does give the share (T4.1-T4.3).
* **Pilot vitals.** The boarding snapshot is gone (`BoardPilot` `:1269`; the members `SavedPilotHealth`,
  `SavedPilotMana` and `bHasSavedPilotVitals` are removed). `UnboardPilot` (`:1317`) reads the pilot ASC's Health and
  Mana right before `PC->Possess(Pilot)` (`:1363-1376`). The possession refills them
  (`AMyCharPlayer::PossessedBy -> InitAbilitySystemAfterRespawn`, synchronous). Once the possession has happened, the
  values read before it are written back. Damage taken while flying stays (T4.4: 100 - 25 = 75 after F).
* Gunners: no vitals handling. They stay possessed, so nothing refills them.

Numbers: one 60 hit gives 15 to every crew member. 0 = off (`Aura.Airship.Set Settings.CrewDamageShare 0`).

Accepted side effects:

* The source of crew damage is the ship's ASC, whose controller is the pilot's. So the pilot's
  `MyPlayerController2::ShowDamageNumber_2` shows the crew numbers on the pilot's screen (spec D4).
* A non-lethal share can start the member's HitReact ability. It is tried by tag in
  `UMyAttributeSet::PostGameplayEffectExecute`. On a seated pilot or a gunner that is at most a montage: movement is off
  and the pilot is unpossessed.

## Ballistic aim (D2 ship side, pass 2)

* `CannonballSpeed` 12000 -> **7000** cm/s (`AirshipPawn.h:762`). Not scheme-owned.
* `ComputeCannonAimRaw` (`:2359`) now gets the world launch direction from **`ComputeCannonLaunchDir`** (`:2438`). It
  then splits it into hull-frame yaw and elevation exactly as before. That one function feeds:
  * firing (`SpawnCannonball` -> `ComputeCannonAim`);
  * barrel tracking (`UpdateCannonAim`);
  * the pilot HUD's arc test (`IsAimInCannonArc`) and the gunner HUD's (`IsCannonAimInArc`).
* `ComputeCannonLaunchDir` works like this:
  * g = |world gravity| x the ball class's `GravityScale` (`GetCannonballGravity`, `:2391`, on the CDO of
    `CannonballClass` or `AAirshipCannonball`).
  * Low arc: `theta = atan((v^2 - sqrt(v^4 - g (g d^2 + 2 h v^2))) / (g d))`.
  * If the target is out of range (negative discriminant), theta is 45 deg, so the shot reports out of arc and the
    8.5 deg cap makes it fall short.
  * Straight at the target when g = 0 or the target is right above or below (d < 1 cm).
  * Flight time `d / (v cos theta)`.
* **Lead** (`bCannonAimLeadShipVelocity`, on). The aim point becomes `Target - Inherited x t`, with two fixed-point
  steps on t. `Inherited` is **the muzzle's velocity**: the ship's linear velocity plus its turn at the muzzle
  (`GetInheritedMuzzleVelocity`, `:2400`). That is exactly what `SpawnCannonball` adds to the ball; it now calls the
  same helper (`:2717`).
* Numbers (v 7000, g' 588):
  * level range at the 8.5 deg cap: 244 m;
  * at 150 m: elevation 5.2 deg, apex about 3.4 m above the muzzle-target line (T2.2 wants >= 2 m).
* Visible change in every scheme: when the pilot aims past about 244 m, or at empty sky, the aim point is 600 m out
  (`CannonAimTraceDistance`). It is then out of range, so the barrels sit at 8.5 deg and the pilot HUD's ring shows
  out of arc (dashed). Before, the straight-line test called such an aim in arc. The Point & Fly gun lock uses only the
  bearing and is not affected.
* **Gunner HUD mark** (`AirshipHUDWidget.cpp:1087`, new `GetCannonBallPathPoint`, `:2412`). The cannon's mark is where
  a ball fired now along the barrel (its limits applied, the muzzle velocity, the ball's gravity) is once it has covered
  the aim's horizontal distance. On target it sits on the crosshair; capped, it sits low. The turret mark is unchanged
  (100 m along the barrel, hitscan).

## Drift and hold (D9, pass 2, `AirshipFlightComponent`)

### States (server only)

`UpdateUnpilotedMode` (`AirshipFlightComponent.cpp:1112`) runs every server frame in `UpdateFlight` (`:852-855`),
before `SelectControls`.

| Mode | When |
|---|---|
| None | flight off or dead, a pilot aboard **or a controller on the ship** (a pilot whose character was destroyed keeps flying), or debug input. Clears a pending drift request |
| -> Drift | from None: a request from `NotifyPilotLeft`, `DriftSpeed` > 0 and exit forward speed > `DriftMinExitSpeed` (100). Target speed `min(exit speed, DriftSpeed)` (250): a slow exit never speeds up |
| -> Hold | from None or Coast: `bHoldWhenUnpiloted` and horizontal speed < `HoldEngageSpeed` (300). The point is the centre of mass now and the heading is the hull yaw now (`BeginHold`, `:1103`) |
| -> Coast | from None otherwise (today's behaviour) |
| Drift -> Hold | the look-ahead sweep or a bow contact (`bDriftBlocked`), `DriftMaxDistance` (0 = no limit) reached, or `DriftSpeed` set to 0. Without `bHoldWhenUnpiloted`: Coast |
| Hold -> re-drop | farther than `HoldResetDistance` (20 m) or turned more than `HoldResetYawDeg` (60): a new hold here if slow, Coast until then. `bHoldWhenUnpiloted` off: Coast |

* `NotifyPilotLeft` (`:964`) is called by the pawn at the very end of `UnboardPilot` (`AirshipPawn.cpp:1403-1406`),
  after the possession and its `ResetInput`. It records the request, the exit forward speed (exit velocity . hull
  forward), the heading and the start point. `ResetInput` doesn't touch the unpiloted state.
* Every mode change is logged once: `LogAirshipFlight: <ship>: unpiloted None -> Drift (4800 cm/s, drift 250 cm/s)`.
* A ship that was never piloted (placed or spawned) holds once slow, so the parked creep goes away.

### Forces (`ApplyForces`)

* Heading (`:1577-1584`): in Drift and Hold, `YawRateCmd = clamp(HoldYawGain 0.5 x heading error, +-HoldYawRateMax 10
  deg/s)`. This is the anchor branch's yaw loop. It sits after the Sky Racer block and before the gun deck.
* Station keeping is off in Drift and Hold (`:1948`). The drift's 2.5 m/s is inside its full-strength band, so it would
  brake the drift; at rest the hold replaces it.
* Drift (`:1993-2000`): along the hull, `clamp(DriftGain x (T - Vf) + drag(T), -DriftDecelMax 200, +DriftAccelMax
  100)`. The drag at the target speed is fed forward because `ADragFwd` already takes the real drag off. From 48 m/s
  it eases down at 2 m/s^2 plus the drag, so it reaches 2.5 m/s in well under 30 s.
* Hold (`:2002-2010`): a capped spring and damper on the centre of mass, `(Err x HoldKp 0.4 + VErr x HoldKd 0.8)`
  capped at `HoldAccelMax` 200, with the target velocity `HoldVelocity` (0 parked). This is the anchor branch's law.
* Both are COM accelerations like every other `ACom` term, so the fans stay idle on every machine and it reads as a
  coast.

### Obstacles

* **Look-ahead** (`SweepDriftAhead`, `:1024`), every `DriftSweepInterval` (0.25 s) while drifting:
  * The box is the hull's local bounds (`CalcBounds(Identity)` of HullCollision), inset 100 cm on every side, with its
    bottom lifted 200 cm, rotated with the hull.
  * It is swept along the held heading for `max(600, ForwardSpeed x 3 s)`, against WorldStatic, WorldDynamic and
    PhysicsBody.
  * It skips what `IsDriftIgnored` (`:981`) names: the ship, everything attached to it (recursive: turrets, pilot,
    gunners), characters, cannonballs, and pawns that aren't airships.
  * It only counts components the hull would really bump into: physics collision on, and Block to the hull's object
    type. That leaves out trigger volumes.
  * The first such hit, or a start overlap, ends the drift.
* **Bow contact** (`NotifyHullContact`, `:998`). The pawn calls it from `OnHullHit` on the server, before the damage
  threshold (`AirshipPawn.cpp:3491-3496`). It ends the drift when the contact is:
  * not ignored;
  * more than 30 % of the hull's half length ahead of the centre of mass;
  * facing the drift: |normal . drift direction| >= `DriftBowHitMinDot` 0.5. Ground contact under the hull doesn't
    count.

### Cosmetics and network

* No new replicated state for the motion: only the server applies forces, and the hull replicates.
* The unpiloted neutral controls carry `Button_Drift` while drifting (`SelectControls`, `:476-479`). They ride
  `RepInput` to every machine.
* `ShapeGalleon` (`:650-653`) idles the engines with the bit set. The neutral controls decode as STOP, and its speed loop
  would back the engines against the drift.
* `ServerSetPilotInput` masks the bit off a pilot's packets (`:394`): it is the server's own.

### Telemetry

`FillTelemetry` (`:2222-2232`) fills `UnpilotedMode`, `bUnpilotedDrift`, `bUnpilotedHold`, `DriftTargetSpeedMS` and
`HoldOffsetM`. They are server values; on clients they stay 0 / false. `Aura.Airship.Telemetry`'s third line prints them
(`AirshipSubsystem.cpp:930`).

### For PR B

* A lane cruise fills the same `FAirshipUnpilotedTarget` (`AirshipFlightComponent.h:19`): a moving `HoldPoint` with its
  own `HoldVelocity`. The hold law already uses both, so the force and heading hooks don't change.
* `UpdateUnpilotedMode` is the one place to add an `EAirshipUnpilotedMode::Lane`.

## Smaller items (pass 2)

* `PilotSeatFallback` (-843, 0, 262) -> **(-740, 0, 264.2)** (`AirshipPawn.h:700`), from `turret_dims.json`
  `pilot_seat_ue` (-740, 0, 264.19). as_57 checks it within 2 cm.
* D1 (pass 1, unchanged): `HandleCannonsFired` keeps the component of both spawn paths and cuts it after
  `MuzzleFXMaxSeconds` with a weak lambda timer on the ship.
* D8 (pass 1, unchanged): `IsWithinBoardRange(..., BelowDistance)` (`:1206`); all three callers in the pilot component
  pass `Settings->BoardBelowDistance` (`AirshipPilotComponent.cpp:274`, `:330`, `:404`).

## Console (D10, `AirshipSubsystem.cpp`)

| Command | Line | Notes |
|---|---|---|
| `Aura.Airship.Mount <Player> <Station>` | `:1033` | `TryMount(null, Station, true)` |
| `Aura.Airship.Dismount [Player]` | `:1057` | |
| `Aura.Airship.TurretFire <0/1> [X Y Z]` | `:1073` | every ship's unmanned turrets |
| `Aura.Airship.TurretDamage <Turret> <Amount>` | `:1101` | turret ASC, `UAirshipDamageEffect`, SetByCaller |
| `Aura.Airship.StationFire <Player> [X Y Z] [Seconds=1]` | `:1148` | with a point, the console aim wins over the gunner's (1 s for a cannon, Seconds + 0.2 for a turret); a turret's trigger is released by a weak timer on the ship |
| `Aura.Airship.Set/Get Settings.<Name>` | `Set`/`Get` | the mutable class default of `UAirshipSettings` on this machine, once; then `OnTuningChanged` on every ship |
| `Aura.Airship.Telemetry` | `:893` | a third line: unpiloted mode, drift, hold, drift target, hold offset, stations with gunner names, turrets, pilot health, cannons ready |
| `Aura.Airship.Kill` | `:801` | pass 2: `DebugKill` (no crew share, the crew is ejected alive) |

## What differs from the spec, and why

1. **The PILOT bar has a row of its own** under the HULL bar (`PilotRowHeight` 24), not beside it on the same row. A
   second bar with its value didn't fit in the 292-unit panel.
2. **HandleCannonsFired feedback.** The pilot's broadside punch plays for a client's predicted shot (`bLocalShot`), and
   also for the host's own shot (`HasAuthority() && IsLocallyControlled()`). It never plays when the mask's first
   cannon is manned. The spec's `bLocalShot` alone would drop the host's punch: the host's shot reaches it through the
   multicast.
3. **Console aim override** (`SetStationConsoleAim`). Without it, the host gunner's own camera aim (sent every frame)
   would replace `StationFire`'s point in standalone. That would break T5.6 / T5.9.
4. **Client reload clocks follow the shots they see.** A cannon played from the multicast (not predicted here) sets that
   cannon's local clock. So a pilot client doesn't predict a phantom shot of a cannon a gunner just fired, and every
   client's reload bars are right.
5. **The gunner's view starts along the gun** at mount (control rotation, pitch -5).
6. **The local safety net waits 5 s** until the ship first lists the pawn, then 1 s. The spec has 1 s from the start,
   which would drop a mount under a lag spike where the RPC arrives long before the array.
7. **The exit trace starts at three heights.** One that starts inside a convex is skipped: the turret seats are inside
   the forward deck's convex, and a hit at the trace start would leave the gunner inside it.
8. **F while mounted dismounts**, on the server too (`TryUseNearest`). This is defensive: the Exit binding normally
   takes the key.
9. `GetCannonReloadAlpha(int32)` is a plain C++ overload, not Blueprint-callable, because UFUNCTIONs can't be
   overloaded.
10. Galleon's held input for a pilot who has gone quiet clears `Button_FireHeld`
    (`AirshipFlightComponent.cpp:469`), so a lost connection doesn't keep the turrets firing.
11. D1 C++ (the muzzle cap), D8 (board from below), `TraceAimPoint`, the runtime spawn offset and the ship's
    `BulletTargetTag` are in pass 1, because they sit in code that pass 1 rewrote.
12. **Pass 2: `Aura.Airship.Kill` gives the crew no share** (`DebugKill`, see Crew damage). Without it T5.11 (gunner
    ejected alive) fails.
13. **Pass 2: the lead uses the muzzle's velocity** (linear + turn), not only the hull's linear velocity. That is what
    the ball inherits: at 10 deg/s of yaw, a muzzle 8 m from the centre of mass moves 1.4 m/s more.
14. **Pass 2: the gunner HUD's cannon mark follows the ball's arc** instead of sitting 100 m along the barrel. With the
    ballistic elevation, the barrel points about 5 deg above a 150 m target, and a barrel-line mark would sit about
    9 m above the crosshair while the gun is on target.
15. **Pass 2: other airships stop a drift.** The spec's look-ahead ignores "pawns/characters"; ships are pawns too.
    The sweep and the bow test ignore characters and non-ship pawns, but a parked ship ahead ends the drift before the
    ram.
16. **Pass 2: the look-ahead counts only real blockers** (physics collision on and Block to the hull's object type). An
    object-type sweep also returns trigger volumes (WorldDynamic, query only), which would end every drift near one.
17. **Pass 2: "piloted" includes a controller on the ship** (`GetController()`), not only `HasPilot()`. A player whose
    character was destroyed while aboard keeps flying with `PilotCharacter` null (`Tick`); the drift and hold forces
    must not fight them.
18. **Pass 2: `bHoldWhenUnpiloted` off also turns the post-drift hold into a coast,** so the regression harness's
    `bHoldWhenUnpiloted 0` + `DriftSpeed 0` gives exactly the old behaviour.
19. **Pass 2: the `Button_Drift` bit is masked off a pilot's packets** on the server (`ServerSetPilotInput`).

## How to test (editor stage, after as_53-as_57)

Pass 1:

* **T6.1.** After spawn, `Aura.Airship.Telemetry` shows two turrets with health 400. Look for `LogAirshipTurret: ...
  bullet damage 4.00` once per turret. On the client, `Turrets` holds two actors attached at the mounts.
* **T5.9 / T5.4 / T5.10 / T5.8.**
  * `Aura.Airship.Mount 0 2`, then check the log: `LogAirshipPawn: <ship>: <char> mounted CannonR1`. `StationMask` is 4,
    the CMC isn't ticking, actor collision is on and the capsule is QUERY_ONLY.
  * `Aura.Airship.StationFire 0 X Y Z` twice, 0.5 s apart: one ball.
  * `Aura.Airship.Board 0` is refused.
  * `Aura.Airship.Dismount 0`: the character is detached, the CMC ticks and it is falling.
* **T5.6 / T5.7.** `Aura.Airship.Mount 0 4`, then `Aura.Airship.StationFire 0 X Y Z 1.0`: 9-11 shots, heat about 0.33.
  With 3.5 s it overheats at about 3 s.
* **T6.2 / T6.3.** Client pilots:
  * camera within 50 deg of the bow, LMB held: both turrets fire and the cannon fire counts don't change;
  * camera 90 deg to port, LMB: a broadside.
* **T5.5 / T5.12.** With L1 manned, the pilot's port broadside fires only cannon 1.
* **T6.6.** `Aura.Airship.TurretDamage 0 400` with a gunner on turret L: the gunner is ejected, the station is free and
  the turret gives no more shots.
* **T5.11.** `Aura.Airship.Kill` with a gunner: the gunner is ejected (thrown) the next tick, **alive**.
* **T8.1.** Client 7 m under the hovering hull: F boards. At 12 m it is refused (`BoardBelowDistance` 1000).
* **T1.1.** After a broadside, there are no NS_AirshipMuzzle components under the Mesh at +1.5 s.
  `Aura.Airship.Set Settings.MuzzleFXMaxSeconds 0` turns the cap off for T1.2.

Pass 2:

* **T4.1.** Host pilots, client mans L1 (`Aura.Airship.Mount 1 0`). `Aura.Airship.Damage 100`, then the next frame
  read both characters' Health on the server. Each is -25. The log has two `crew damage ... 25.0 (0.25 of 100.0)` lines.
* **T4.2 / T4.3.** Set the pilot's (or the gunner's) Health base to 10 on the server ASC, then `Aura.Airship.Damage
  100`. The pilot's PC pawn is the character again (or the station is free), then that character is dead. The ship is
  alive with no pilot (it drifts or holds).
* **T4.4.** Pilot at 100, `Aura.Airship.Damage 100`, F: the character has Health 75 after the exit.
* **T2.2 / T2.4.** Ship parked, aim 150 m off the port beam at muzzle height:
  * `Aura.Airship.Telemetry` and the barrel elevations read about 5.2 deg on the aim side;
  * the ball lands within 3 m and climbs about 3.4 m above the line;
  * at 300 m, `IsAimInCannonArc` is false and the barrels sit at 8.5.
* **T2.3.** At 30 m/s the lead keeps a 120 m shot within 6 m. To compare, set `Aura.Airship.Set
  Settings.bCannonAimLeadShipVelocity 0`: the shot lands about the ship's travel during the 1.7 s flight (about 50 m)
  off.
* **T9.1 / T9.2.** Cruise at 48 m/s in each scheme, then F.
  * The log has `unpiloted None -> Drift (4800 cm/s, drift 250 cm/s)`.
  * Telemetry line 3 shows mode 2 and drift 2.5.
  * The speed is 2.5 +- 0.3 m/s within 30 s, and the yaw holds within 2 deg for 60 s.
  * Galleon: `ThrottleOrder` STOP, but the shaped throttle is 0 (no reverse).
* **T9.3.** F at rest: mode 3, `HoldOffsetM` under 0.5 for 30 s.
* **T9.4.** Drift toward a wall. The log has `drift ends, <wall> N cm ahead` (look-ahead), or `bow contact`. Then mode
  3, with no hull damage (2.5 m/s is far below `ImpactMinSpeed`).
* **T9.5.** Board while drifting: mode 0 and the throttle works at once.
* **T9.6.** `Aura.Airship.Input 1 0` on an unpiloted ship: mode 0. `InputClear` at speed: mode 1 (Coast), then 3 below
  3 m/s.
* **T9.7.** On the client, the ship's replicated input has bit 0x40 while drifting.
* **Regression switches** (per phase, spec section 4): `Aura.Airship.Set Settings.bHoldWhenUnpiloted 0` and
  `Settings.DriftSpeed 0` give the old coast; `Settings.CrewDamageShare 0` turns crew damage off.

## Review fixes (2026-11-25)

The decision record with file:line is `SPEC_A.md` section 6. The file:line references in the sections above are from
the pass 2 build: the fixes moved later lines of `AirshipPawn.cpp`, `AirshipPilotComponent.cpp` and
`AirshipFlightComponent.cpp` by up to about 200 lines (search for the function name). Core's part:

* **Gunner corrections** (6.1). `MountGunner` sets the gunner's `bIgnoreClientMovementErrorChecksAndCorrection` (saved
  per station in `bStationGunnerIgnoredCorrections`); `DismountGunner` restores it before the launch.
  `BeginLocalGunner` sets `bClientIgnoreMovementCorrections` on the owner (restored in `EndLocalGunner`).
  `TickLocalGunner` re-seats the client's copy (`GetStationSeatRelativeTransform`) when it is more than 5 cm off,
  before the view is read. Moves sent before the mount still reach the server (ServerMove only checks `IsActive`):
  without this, their world-space corrections moved the attached capsule off the seat for the whole mount.
* **Turrets inside the hull's collision** (6.3). `AAirshipPawn::FindTurretBehindHullHit` and the static
  `RedirectBulletHitToTurret`, which `UAirshipSubsystem::OnWorldBeginPlay` binds to the swarm's new
  `BulletTargetRedirect` (server). The turret calls it from `TraceShotLine`, the gun from `MyFunc`.
* **Riders for damage** (6.4). `IsRiderForDamage` / `GetDamageRiders` and the pawn property `RiderZoneHeight` (400).
  `TraceAimPoint` ignores the damage riders instead of the passengers. `IsPassengerCandidate` (collision) is unchanged.
* **Drift look-ahead** (6.5). `GetDriftLookAheadDistance(ForwardSpeed)`: max(DriftLookAheadMin, v x DriftLookAheadTime +
  v^2 / (2 HoldAccelMax)), v = max(the real speed along the drift heading, the target). `SweepDriftAhead` takes that
  speed and returns the length; the next sweep is due before the ship covers half of it (at most
  `DriftSweepInterval`).
* **A gunner killed at the gun** (6.6). `NotifyStationsChanged` binds each gunner's `OnDeathDelegate` on every machine
  (unbound when it leaves and is off the hull; the server unbinds in `DismountGunner` after the detach).
  `OnStationGunnerDied` -> `KeepCorpseOffHull`: the simulating parts of a body still attached to the ship ignore the
  hull's object type, so the ragdoll doesn't start inside the simulated hull. Needs PIE T5.15.

## Open items

* `CPP_NOTES.md` section 15 and the `HOW_TO_FLY.md` round 2 section are written from this pass, before the editor
  stage. The PIE results still have to be added to both.
* Nothing has run in PIE. Watch most closely:
  * T5.13: a possessed character attached to a simulated hull (client corrections; review fix 6.1, test with
    `Net PktLag=100` and a mount while walking);
  * T5.15: a gunner killed at the gun (review fix 6.6);
  * T5.1 / T5.8: the client's own attach and detach;
  * the dismount exit trace onto the forward deck's convex for turret gunners;
  * T9.4: the look-ahead box against `L_AirshipTest`'s walls and its ground plane (the box bottom is lifted 2 m above
    the hull's lowest point plus the 1 m inset);
  * T4.2: the ejected pilot dying from the share in the same frame as the possession.
