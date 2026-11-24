# Round 2, PR A: turret notes

The turret part of `SPEC_A.md` (D6), plus every new setting (Appendix A) and the shared types and telemetry fields
(section 2.1, Appendix B). It builds with `_AirshipWork_logs/build_r2.sh` (`build_r2_122918.log`: Result Succeeded, no
warnings in these files). Nothing has been tested in the editor yet: the ship doesn't spawn turrets until core adds
`SpawnTurrets` (D6.7).

## Files

| File | What |
|---|---|
| `Source/Aura/Public/Airship/AirshipTurret.h` (new) | `AAirshipTurret`, the D6.2 API |
| `Source/Aura/Private/Airship/AirshipTurret.cpp` (new) | the implementation |
| `Source/Aura/Public/Airship/AirshipTypes.h` | stations, buttons, enums, turret structs, telemetry fields |
| `Source/Aura/Public/Airship/AirshipSettings.h` | Appendix A, the turret mounts, the asset paths |

## AirshipTypes.h

* `Airship::NumStations` 6, `NumTurrets` 2, `FirstTurretStation` 4, `IsCannonStation`, `IsTurretStation`,
  `StationToTurret`, `TurretToStation` (`AirshipTypes.h:29-39`).
* `Airship::Button_FireHeld` = 1 << 5 and `Button_Drift` = 1 << 6 (`:50-57`). Bit 7 is still free.
* `EAirshipStation` (`:70-81`; `None` = 255 is hidden) and `EAirshipUnpilotedMode` None / Coast / Drift / Hold
  (`:87-98`). The values are fixed so that PR B can add `Lane` after `Hold`.
* `FAirshipTurretMount` (`:100-121`) is a USTRUCT so it can be edited in the settings, with clamps on the angles.
  `FAirshipTurretShot` (`:123-135`) holds a tracer end and an impact flag. `FAirshipTurretCommand` (`:137-147`) is a
  plain struct with aim point, has-aim, trigger and a weak instigator.
* `FAirshipPilotInput::IsFireHeld()` (`:228`).
* `FAirshipFlightTelemetry` gets every Appendix B field (`:472-524`). The unpiloted fields are for flight to fill, the
  station, turret, pilot-health and cannon-ready fields for the pawn. `PilotHealth` defaults to -1.

## AirshipSettings.h

The constructor fills `TurretClass` (BP_AirshipTurret_C), `GunDamageEffect` (GE_GunShootDamage_C) and the two
`TurretMounts` (`AirshipSettings.h:60-78`):

| Turret | Location (hull, cm) | Yaw min / max | Pitch min / max |
|---|---|---|---|
| 0 port | (2100, -245, 655) | -110 / +30 | -20 / +40 |
| 1 starboard | (2100, 245, 655) | -30 / +110 | -20 / +40 |

The new properties follow Appendix A, with the same defaults:

* Boarding: `BoardBelowDistance` 1000, with the anchor branch's comment (`:117-123`).
* Stations (`:211-276`).
* Crew: `CrewDamageShare` (`:284`).
* Cannons: `MuzzleFXMaxSeconds`, `bCannonAimLeadShipVelocity` (`:296-300`).
* Turrets (`:309-339`).
* Unpiloted (`:348-422`).

None of them is scheme-owned. All are `Config, EditAnywhere`, so `Aura.Airship.Set Settings.<Name>` (core's
`ResolveTarget` prefix) changes them at runtime.

## AAirshipTurret

### Setup

**Components** (constructor, `AirshipTurret.cpp:74-134`). The subobject names are the ones `as_55` sets: `Root`,
`HitBox`, `BaseMesh`, `GunMesh`, `Muzzle`, `MuzzleFXComponent`, `DestroyedFXComponent`, `AbilitySystemComponent`,
`AttributeSet`.

* `HitBox` has extent (60, 60, 95) at z 95. It is QueryOnly and WorldDynamic, and blocks every channel except Camera
  and Pawn, which it ignores. Overlap events are on.
* The meshes have no collision.
* The gun sits at (0, 0, `PivotHeight`) on the base and the muzzle at (`MuzzleForward`, 0, 0) on the gun.
  `ApplyGeometry` (`:205`) applies both again at BeginPlay, so the Blueprint's values win.
* Ticks in `TG_PostPhysics`. Replicates, with movement on (for attachment), `bAlwaysRelevant`, 30 Hz.

**Replicated** (`:136-148`):

* Initial only: `Ship`, `TurretIndex`, `Mount`.
* Every update: `bDestroyed` (OnRep), `HeatQ` (heat x 255), `bOverheated`, `AimYawQ`, `AimPitchQ` (hundredths of a
  degree, relative to the mount).
* `GetShip()` (`:1051`) falls back to the owner, then to the attach parent, while a client's `Ship` reference is not
  mapped yet.

**BeginPlay** (`:158-188`):

* `InitAbilityActorInfo(this, this)`.
* On the server: MaxHealth, then Health = `TurretMaxHealth` 400, then Armor. It adds
  `UMechSentinelSwarmSubsystem::BulletTargetTag` to itself (the ship adds it too, but this also covers a turret spawned
  any other way) and caches the gun base damage. It logs one line: turret, ship, mount, bullet damage, health.
* A client that gets the turret already destroyed plays the fire FX without the explosion.

### Aim

`UpdateAim` (`:301-371`) runs on every machine. Which aim it follows:

* The server uses its command (rest when stale).
* A client with a fresh local command uses that command.
* Other clients follow the replicated angles at twice the slew rate, so they catch up between updates.

How it aims:

* The aim point becomes yaw = atan2(Y, X) and pitch = atan2(Z, |XY|) in the turret's own frame, from the pivot
  (`ComputeAimRaw`, `:281`). That frame is the mount's: the ship attaches the turret at `Mount.Location` with no
  rotation, so this is the same as the spec's `HullTM.Inverse(Aim) - (Mount.Location + (0, 0, PivotHeight))`.
* The angles are clamped to the mount's limits, then slewed at `YawRateDeg` 180 / `PitchRateDeg` 120 with
  `FInterpConstantTo`.
* Yaw goes to `BaseMesh` and pitch to `GunMesh` (only when they change).
* With no aim the gun rests (0, 0). A wreck's barrel sags to the lower pitch limit at 30 deg/s.

`IsAimInArc(Point, Tol)` (`:291`) uses the same angles against the limits plus the tolerance.

### Fire (server)

`UpdateServerFire` (`:424-497`) fires when all of these hold:

* the command is fresh (at most 0.5 s old: a safety net, since the ship refreshes it every tick);
* the trigger is held and there is an aim point;
* the turret isn't destroyed and isn't overheated;
* the ship is alive;
* `IsAimInArc(aim, ArcToleranceDeg 3)` is true.

The shot clock (`AdvanceShotClock`, `:388`):

* The phase starts on each false-to-true edge of "can fire". Turret 0 fires at once; turret 1 fires
  `FireInterval * 0.5` = 0.05 s later.
* Then one round every `FireInterval` (0.1 s). At most 4 rounds in a tick, and no catch-up burst after a hitch.

Heat:

* Each round adds `HeatPerShot` 1/30. At >= 1 the gun is overheated and the rest of the tick's rounds are dropped.
* Cooling starts `CoolDelay` 0.2 s after the last round, at `CoolRate` 0.4/s.
* The overheat clears at `OverheatRecover` 0.35. So 30 rounds (2.9 s from the first) overheat it, and it fires again
  about 1.8 s after its last round.
* The frame's rounds go out in one `MulticastShots`, followed by `ForceNetUpdate`.

`FireOneShot` (`:647-701`) does the following for each round:

1. Start = muzzle. Dir = `VRandCone(barrel, SpreadDeg 1)` (half angle, as the cannons' spread). Range 25000 cm.
2. Ignores (`BuildShotQueryParams`, `:533`): the turret; the ship; every actor attached to the ship (recursive: both
   turrets, the pilot, the gunners); the ship's riders and the actors attached to them. Since the review fixes
   (2026-11-25, SPEC_A.md section 6.4) the riders are `GetDamageRiders()` (`AAirshipPawn::IsRiderForDamage`), not
   `GetPassengers()`, whose no-base zone also took in enemies jumping or hovering next to the ship.
3. `TraceShotLine` (`:563`) runs a Visibility line trace. It looks past this ship's own cannonballs (adding them to the
   ignores) up to 4 times. Review fix (SPEC_A.md section 6.3): a hit on another ship's hull goes on to that ship's
   turret behind it when there is one (`AAirshipPawn::FindTurretBehindHullHit`; the turrets sit inside the hull's
   forward deck convex). The server's damage and a client's predicted tracer both end there.
4. `FindBallOnShot` (`:608`) runs a `SweepMultiByObjectType(WorldDynamic)` sphere of `BallSweepRadius` 40 cm from the
   muzzle to the line hit (or the end). The nearest `AAirshipCannonball` that isn't this ship's and isn't `IsSpent()`
   wins. Because the sweep stops at the line hit, a ball it finds is nearer than whatever the line hit.
5. Ball hit: `ApplyShotDamage(TurretGunDamageMultiplier, instigator)`, in gun units, so 8 rounds take down a 30-unit
   ball.
6. Otherwise, when the line hits an enemy ball (balls now block Visibility), the same call.
7. Otherwise, `ApplyBulletDamage` (`:703-765`):
   * The target is the hit actor or one of its attach parents (up to 4) that has an ASC with `UMyAttributeSet` health
     and isn't dead.
   * The spec is made from the ship's ASC (`DamageEffectClass`, or `UAirshipDamageEffect` when null) at the ship's
     level.
   * `Context.AddInstigator(gunner or ship, turret)`, plus `AddSourceObject(turret)` and `AddHitResult`.
   * SetByCaller `SetDamageByCaller` = `GetBulletDamage()`, applied with `ApplyGameplayEffectSpecToTarget`.
   * With the gunner as instigator, the gunner's ASC becomes the context's instigator ASC, so damage numbers and XP go
     to the gunner (as with `FireStation`).
   * This is the single target filter, where PR B adds its team test.
8. Sentinels: `QueueSentinelSegment` (`:767`) stores (muzzle, round end) and sets one next-tick timer per frame.
   `FlushSentinelSegments` (`:789`) then runs `QueryCapsule(r = SentinelShotRadius 20)` and
   `ApplySpecToHits(SentinelMaxTargets 1)`, with `MakeSentinelDamageSpec(world, gunner or ship, bullet damage)`. The
   query runs outside the Mass phases, because this tick runs in `TG_PostPhysics`.
9. The tracer end is added to the frame's shot list. `ShotCount` goes up by one, and the listen host draws its own
   tracer.

Bullet damage:

* `GetBulletDamage()` (`:1067`) = `TurretGunDamageMultiplier` (read every call, so the console setting takes effect at
  once) x `ReadGunBaseDamage()` (read once).
* `ReadGunBaseDamage()` (`:1078-1122`) sums GE_GunShootDamage's additive IncomingDamage modifiers through
  `GetStaticMagnitudeIfPossible(1)`. If any of them can't be read statically, or there are none, or the GE is
  missing, it uses `GunDamageFallback` 1.
* Committed GE (1.0): 4 per bullet, 80 DPS for both turrets. The user's local GE (1000): 4000 per bullet.

### Tracers, flash, prediction

* `DrawTracer` (`:895`) is a copy of `AMechSentinelBulletRelay::ShowBulletsLocal`. It writes `NDC_GunShootHit`
  (`MuzzlePos`, `HitLocation`) through the access context with `bOverrideSystemToSpawn` / `SystemToSpawn =
  TracerSystem`.
* If `TracerDataChannel` is unset, it loads `NDC_GunShootHit` by path once. If `TracerSystem` is unset, the channel
  spawns its own system (the gun's tracer).
* `MulticastShots_Implementation` (`:840`): the authority skips it (it drew while firing) and a dedicated server draws
  nothing. Every other client draws from its own muzzle to each end, adds to `ShotCount` and flashes once.
* Prediction: `UpdatePredictedFire` (`:499`) runs on a client with a fresh local command, trigger held, not overheated
  (the replicated value) and in arc. It uses the same clock and phase. Each round is a local trace with the same
  ignores, a tracer and a `ShotCount`; no damage.
* `PlayMuzzleFlash` (`:934`) calls `Activate(true)` once per batch, and a timer calls `DeactivateImmediate`
  `MuzzleFlashMaxSeconds` 1.0 s after the last batch (the D1 cap).

### Destroyed

* `Die()` (`:987`, from `UMyAttributeSet` at Health 0) and `DestroyTurret()` (`:997`) run once, on the server:
  * `bDestroyed`, command cleared, Health set to 0 (for the console wreck), `ForceNetUpdate`, log.
  * `OnDeathDelegate.Broadcast`, then `PlayDestroyedFX(true)`.
* `OnRep_Destroyed` (`:1023`) plays the FX, without the explosion when the actor began play less than 0.5 s ago.
* `PlayDestroyedFX` (`:959`):
  * stops the muzzle flash;
  * activates `DestroyedFXComponent` (burns until the turret goes);
  * spawns `DestroyedExplosionFX` once at the pivot, scaled `DestroyedExplosionScale`;
  * calls the new `BP_OnTurretDestroyed(bExplosion)` hook.
* The wreck stays attached and its HitBox still stops balls. A dead turret takes no damage, `IsDead` is true (so
  sentinel bullets skip it), and core's `UpdateStations` ejects its gunner.
* On the server, a turret whose ship is gone removes itself (`Tick`, `:218`). Attached actors don't go with their
  parent, so this is a safety net behind core's EndPlay cleanup.

## What differs from the spec, and why

1. **Multicast skip rule.** A client skips `MulticastShots` only while its fresh local command also holds the trigger
   (the spec says "local command is fresh"). The pilot's machine refreshes a local command for every unmanned turret
   every frame, so the spec's rule would hide console `TurretFire` rounds, and the round-trip tail after a release,
   on the pilot's screen.
2. **Shot clock phase.** The phase starts on the edge of "can fire" (trigger held and in arc, not overheated, ship
   alive), not only on the trigger's own edge. After an overheat or an arc re-entry, the two guns alternate again.
3. **Server command timeout.** A server command older than 0.5 s neither aims nor fires. This is a safety net, since
   the ship refreshes it every tick.
4. **Extra hooks:**
   * BlueprintPure `GetAimYawDeg` / `GetAimPitchDeg` for the harness.
   * `BP_OnTurretDestroyed(bExplosion)`.
   * A turret adds `BulletTargetTag` to itself.
   * Hits look up to 4 attach parents for an ASC.

## For core

* `SpawnTurrets`: `SpawnActorDeferred<AAirshipTurret>(Class, FTransform(Mount.Location) * HullTM, this, nullptr,
  AlwaysSpawn)` -> `InitTurret` -> `FinishSpawning` -> attach without welding -> relative transform =
  `FTransform(Mount.Location)` (no rotation: the aim assumes the turret frame is the hull's).
* The driver's local command: use the same `bHasAim` as the server (`Turret->IsAimInArc(AimPoint, 10)`), not
  `bLocalAimValid` alone. Otherwise the pilot's copy clamps to its limit while the server's rests.
* `SetServerCommand` every ship tick, also `{zero, false, false, nullptr}` for rest. A command not refreshed for 0.5 s
  stops the turret anyway.
* Use the turret's `GetHeat01`, `IsOverheated`, `GetHealth`, `GetMaxHealth`, `IsTurretDestroyed` and `GetShotCount`
  for the HUD and telemetry. Use `GetMuzzleLocation` / `GetBarrelDirection` for the gunner HUD's "where the gun
  points" mark.
* `FAirshipUnpilotedTarget` (D9.2) isn't in `AirshipTypes.h` (section 2.1 doesn't list it). It belongs in the flight
  component's header.

## How to test (once core spawns them)

* After spawn: `Aura.Airship.Telemetry` shows 2 turrets, health 400 / 400, heat 0. The log has one
  `LogAirshipTurret: ... bullet damage 4.00 (4.00 x gun 1.00), health 400.` line per turret (T6.1, T6.8).
* `Aura.Airship.TurretFire 1` (core) at a parked dummy ship 60 m ahead for 1 s: about 20 rounds, -80 health on the
  dummy (T6.4). Shot counts from `GetShotCount()` on server and client.
* Hold 3.5 s: `IsOverheated()` true at about 2.9 s, no rounds until heat is back at 0.35 (T5.7).
* `Aura.Airship.TurretDamage 0 400`: `IsTurretDestroyed()` on server and client, the fire FX on the client, no rounds
  from it under `TurretFire 1` (T6.6).
* A hovering `SpawnTestCannonball` 30 m ahead with `TurretFire 1` at it: `IsShotDown()` within 1 s, 8 rounds (T2.7).
* `Aura.MechSentinel.TestBullet` at the turret's HitBox: turret health -3, ship unchanged (T3.2).
* Verbose logs: `log LogAirshipTurret Verbose` shows overheat / cool and sentinel hits; `VeryVerbose` shows every hit.
