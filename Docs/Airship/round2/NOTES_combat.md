# Round 2, PR A: combat notes (cannonballs, character gun, sentinel bullets)

What the "combat" part of `SPEC_A.md` delivers: D2 on the cannonball class (size, gravity, health, shoot-down,
Visibility blocking, replicated stop, crew and rider filtering, splash), the character gun's cannonball branch, and D3
(Mech Sentinel bullets damage airships and their turrets). Line numbers are in the clone's working tree after this
change.

Files (only these):

* `Source/Aura/Public/Airship/AirshipCannonball.h`, `Source/Aura/Private/Airship/AirshipCannonball.cpp`
* `Source/Aura/Public/AbilitySystem/Abilities/GA_GunShoot.h`, `Source/Aura/Private/AbilitySystem/Abilities/GA_GunShoot.cpp`
* `Source/Aura/Public/MechSwarm/Core/MechSentinelSwarmSubsystem.h`, `Source/Aura/Private/MechSwarm/Core/MechSentinelSwarmSubsystem.cpp`

Compile state: the three .cpp files built clean in `build_r2.sh` (log `_AirshipWork_logs/build_r2_122329.log`, steps
1, 5 and 6 with no output). That build failed only inside `AirshipTurret.h`, which the turret part was still writing
at the time. `AirshipCannonball.gen.cpp` compiled in the same unity file ahead of the turret's errors, and
`GA_GunShoot.gen.cpp` (after the error limit there) was compiled on its own from the real response file: clean.

---

## 1. Cannonball (D2)

### Defaults (`AirshipCannonball.h`)

| Property | Was | Now | Line |
|---|---|---|---|
| `Radius` | 28 | 50 cm | h:122 |
| `GravityScale` | 1.0 | 0.6 (now `Replicated`, initial only) | h:130 |
| `MaxLifeSeconds` | 8 | 10 s | h:134 |
| `SplashRadius` | 450 | 600 cm (falloff to `SplashMinFraction` 0.3 kept) | h:138 |
| `SentinelHitRadius` | 60 | 100 cm | h:145 |
| `BallMaxHealth` (new) | - | 30 gun units, 0 = can't be shot down | h:167 |
| `bSplashWhenShotDown` (new) | - | false | h:171 |

Range check behind 0.6: level range at the 8.5 deg cap = v^2 sin 17 / g' = 7000^2 x 0.292 / 588 = 244 m (with the
core's `CannonballSpeed` 7000).

`BP_AirshipCannonball` still holds `Radius 28 / SplashRadius 450 / MaxLifeSeconds 8`, which `as_03` wrote explicitly
(`as_03_physmat_cannonball.py:79-81`), until `as_52` runs. `GravityScale`, `SentinelHitRadius` and `BallMaxHealth`
were never written by as_03, so the BP picks up the new C++ defaults on its own. as_52 should also read back the
CollisionSphere's Visibility response on the CDO (expect Block; the BP never changed collision).

### Collision

`AirshipCannonball.cpp:43-46`: `ECC_Visibility` is now Block (was Ignore). Camera stays Ignore, Pawn stays Overlap.
Only traces against the ball change; its own flight sweep uses its object type, not the Visibility channel.

### API for core and turret (`AirshipCannonball.h:53-96`)

| Symbol | Line | Notes |
|---|---|---|
| `bool ApplyShotDamage(float DamageUnits, AActor* DamageInstigator)` | h:59, cpp:458 | server; true if this hit shot it down |
| `GetBallHealth()` / `GetBallMaxHealth()` | h:63-67 | server value; clients see the max |
| `IsShotDown()` | h:70 | every machine (replicated) |
| `IsSpent()` | h:73 | server: exploded or shot down |
| `GetSourceShip()` | h:76 | every machine |
| `GetRadius()` / `GetGravityScale()` | h:79-82 | read them on the CDO (`GetDefault<AAirshipCannonball>()` or the class's CDO) |
| `static SpawnTestCannonball(...)` | h:91, cpp:554 | test hook, see below |
| `BP_OnShotDown(FVector)` | h:96 | every machine but a dedicated server |

### Shoot-down (`ApplyShotDamage`, cpp:458-499)

* Refuses (false): not the server, before BeginPlay (`BallHealth` is set there, cpp:113), already spent,
  `BallMaxHealth <= 0`, damage not > 0 (NaN included).
* `BallHealth -= DamageUnits`. Above 0: Verbose log, false.
* At 0: `bShotDown = true`, `ShotDownLocation = actor location`, then
  * default (`bSplashWhenShotDown` off): `bExploded = true` so `Explode` never runs (no damage, no splash, no sentinel
    sweep), `PlayShotDownFX()`, `EnterShotDownState()`, `SetLifeSpan(ImpactDestroyDelay)`;
  * with `bSplashWhenShotDown`: `Explode` at the ball (damage, splash, sentinels, `MulticastImpact`), then the same FX
    and state calls.
  * `ForceNetUpdate()`, Verbose log "shot down by <instigator>", returns true.
* `EnterShotDownState()` (cpp:515): collision off, hidden, movement stopped **and its tick turned off** (the projectile
  adds gravity every tick, so a stopped but ticking ball would fall on, hidden, until it is removed).
* `PlayShotDownFX()` (cpp:528): `ImpactFX` at `ShotDownLocation` and `ImpactFXScale`, facing back along the flight
  (the launch direction for a copy that already stopped), then `BP_OnShotDown`. Not on a dedicated server.
* `bImpactFXPlayed` (h:222): the impact burst plays once per machine, whichever of `MulticastImpact` (cpp:451) and the
  shoot-down comes first (only matters with `bSplashWhenShotDown`).

### Clients (`OnRep_ShotDown`, cpp:501; BeginPlay cpp:157-161)

Replicated state, not a multicast (`MulticastImpact` is unreliable; state reaches every client and late joiners):
`bShotDown` (ReplicatedUsing) and `ShotDownLocation`, both COND_None (cpp:83-84). The OnRep turns collision off, moves
the client's copy to `ShotDownLocation` (its own flight drifted), plays the burst, then stops and hides it.

A client that receives the ball with `bShotDown` already set (it joined, or the ball spawned and died in one net
update): the engine runs OnReps of the first bunch before BeginPlay (`DataChannel.cpp`, `PostReceivedBunch` then
`PostNetInit`), and BeginPlay restarts the flight from `LaunchVelocity`, so BeginPlay ends with `EnterShotDownState()`
when `bShotDown` is set. The burst plays in that case too: the ball only exists for `ImpactDestroyDelay` (1 s) after a
shoot-down, so any OnRep is within a second of it.

`GravityScale` is replicated initial-only (cpp:82), so a test ball's `GravityScaleOverride` flies the same arc on the
clients. For a normal ball it equals the class default and costs nothing.

### Own crew and riders (`ShouldIgnore`, cpp:186-222)

Added before the cannonball test: for the firing ship, walk from the actor up its attachment chain to the first
character; ignore it when `SourceShip->IsPassengerCandidate(Character)` is true, or when its movement base is the ship
or something attached to it. The second test keeps riders safe when the ship's `bPassengersQueryOnly` is off (then
`IsPassengerCandidate` answers false for everyone). Attached gunners and the ship's turrets are already covered by
`IsAttachedTo(SourceShip)` (recursive), and BeginPlay ignores the ship's attached actors for movement. `ShouldIgnore`
feeds the direct hit, the overlap path and the splash, so the firing ship's pilot, gunners, turrets and deck riders
take nothing from its own balls.

Known limit (from `IsPassengerCandidate`): a character with no movement base (jumping, falling) inside the hull bounds
+ `PassengerZoneMargin` (300 cm) of the firing ship counts as its rider, enemy or not. PR B's team test belongs here.

Review fix (2026-11-25, SPEC_A.md section 6.4): the loop now asks `SourceShip->IsRiderForDamage(Character)` (attached,
standing on the ship, or no base inside the hull's own turned box up to `RiderZoneHeight` above it). The world bounding
box + 300 cm is gone from the damage rule, so an enemy jumping or hovering next to the ship is hit; one right over the
deck still counts as a rider. The separate movement-base test is part of `IsRiderForDamage`.

Review fix (SPEC_A.md section 6.2): `MulticastImpact_Implementation` and the client branch of `OnProjectileStop` turn
the client copy's collision off, as `Explode` does on the server. A hidden spent ball blocked Visibility on the target
for a second and caught the client's crosshair, so the gun did nothing there.

### Test hook (`SpawnTestCannonball`, cpp:554-607)

`AAirshipCannonball::SpawnTestCannonball(WorldContext, BallClass, Location, Velocity, SourceShip, Damage = 60,
GravityScaleOverride = -1)` (Python: `unreal.AirshipCannonball.spawn_test_cannonball(...)`):

* server only (a client world logs a warning and returns None);
* `BallClass` null -> `AAirshipCannonball` (no mesh: pass the BP class for captures);
* `SourceShip` null -> no spec and damage 0: harmless (no GAS damage, no sentinel damage), still flies, bursts and can
  be shot down;
* with a ship: the spec comes from the ship's ASC with the built-in `UAirshipDamageEffect` (the ship's own
  `DamageEffectClass` is protected; BP_AirshipPawn leaves it unset, so this is the same effect), the ship's level
  (`IMyCombatInterface::GetLevel`), instigator and source the ship, SetByCaller `Damage`;
* `GravityScaleOverride >= 0` replaces `GravityScale` before `FinishSpawning`; logs the ball.

---

## 2. Character gun (`GA_GunShoot`)

* `CannonballShotUnits` (h:83, EditDefaultsOnly, category Airship, default 1): gun units per hit.
* `MyFunc` (cpp:349-370), first thing: a hit `AAirshipCannonball` -> on the server (`Avatar->HasAuthority()`)
  `Ball->ApplyShotDamage(CannonballShotUnits, Avatar)`, then return (a ball has no ASC, so the old path did nothing
  with it anyway). Clients do nothing (the predicted call on a client returns at once).
* Refinement beyond the spec: no damage to a ball whose source ship the shooter rides
  (`BallShip->IsPassengerCandidate(Shooter)`: deck, helm or station). Same rule as the turrets, which re-trace past
  their own ship's balls. The ball still takes the shot (it blocks Visibility), it just isn't counted.
* The sentinel segment of a shot now stops at a ball it hits (`TraceWall` uses Visibility): correct, unchanged code.
* Review fixes (2026-11-25, SPEC_A.md sections 6.3-6.4):
  * the own-ship test for balls uses `IsRiderForDamage` (not the wide passenger zone);
  * a hit on a ship's hull over its forward deck goes on to the turret behind it (`FindTurretBehindHullHit`; the
    turrets sit inside that convex). The shot's direction is the camera's line of the last crosshair hit, which
    `OnServerMouseCursorData` now keeps (`GetShotDirection`), else from the pawn's view;
  * no damage to anything attached to a ship the shooter rides (its turrets, its gunners). The own hull is still hit
    as in round 1.

Numbers: committed gun = 1 gun unit per hit at about 4.6 hits/s, so one player needs 30 hits (6.5 s) for a ball that
flies 1-3 s; turrets (4 units per bullet) need 8 bullets. Balls are in gun units, so the user's local
GE_GunShootDamage value (1000) doesn't change this.

---

## 3. Sentinel bullets damage ships and turrets (D3)

Cause: the bullet's end comes from a Visibility trace that stops on the hull (PhysicsBody), but hits were only taken
from a sphere sweep on **Pawn** object types against player-controlled pawns, which never finds the hull.

* `UMechSentinelSwarmSubsystem::BulletTargetTag` = `"MechSentinelBulletTarget"` (h:152, cpp:46). Core adds it to every
  `AAirshipPawn` (constructor) and to every turret it spawns. Actor tags don't replicate; hits are server-only.
* `BulletTargetSlack` = 150 cm (cpp:55, private namespace).
* `TickBullets` (cpp:666-712): the Pawn sweep is unchanged and runs first. Only if it found no player pawn on this
  stretch: a Visibility line trace over the same stretch (to `end + 150 cm` once the bullet has arrived). If the first
  blocker carries the tag and is not dead (`IMyCombatInterface::IsDead`), `ApplySentinelAttack` hits it (the
  existing GE_SentinelAttack path onto the actor's ASC: the ship's or the turret's `UMyAttributeSet`) and the bullet
  ends. One path per bullet. Untagged blockers do nothing, as before. A dead tagged target (a turret wreck) doesn't
  consume the bullet.
* Nothing depends on PA_Airship (the user's local one is empty).
* Targeting is unchanged: `GatherPlayerTargets` still uses `PlayerState->GetPawn()` (the ship while piloted, a gunner's
  character while mounted). An unpiloted ship isn't targeted, but a stray bullet that hits it now damages it.
* `FFlyingBullet`, `FireSentinelBullet` and the bullet FX are unchanged.
* Review fix (2026-11-25, SPEC_A.md section 6.3): `BulletTargetRedirect` (a plain delegate on the subsystem, unbound by
  default) can hand a tagged hit to another actor and impact point. `TickBullets` asks it before `ApplySentinelAttack`.
  `UAirshipSubsystem::OnWorldBeginPlay` (server) binds `AAirshipPawn::RedirectBulletHitToTurret`: the turrets sit
  inside the hull's forward deck convex, so the trace always finds the hull first. Without the binding (no airship
  code) nothing changes.

### Test hook

`Aura.MechSentinel.TestBullet <FromX> <FromY> <FromZ> <ToX> <ToY> <ToZ> [Damage=3]` (cpp:1270-1325, non-shipping,
server world): fires one bullet with default speed (7500 cm/s) and radius (30 cm), no spread,
`Range = max(5000, |To - From| + 200)`. Logs from, to, damage, speed, radius, range and whether a bullet was added.
Bad arguments print the usage.

---

## 4. How to test (PIE, editor stage)

Logs: `log LogAirshipCannonball Verbose` and `log LogMechSentinel Verbose` show hits, shoot-downs and tagged bullet
hits.

| Check | How | Pass |
|---|---|---|
| T2.1 ball | fire a broadside, read the ball: `CollisionSphere` radius, `Movement.ProjectileGravityScale` | 50 cm, 0.6 (after as_52: BallMesh scale 1.0) |
| T2.6 gun vs ball | `spawn_test_cannonball(world, BP class, 15 m ahead of the host, (0, 200, 0), None, 0, 0)`, host fires GA_GunShoot at it | `get_ball_health` drops by 1 per hit on the server; `is_shot_down` after 30 hits; a dummy 1 m away loses nothing |
| T2.7 replicated stop | same ball shot down by a turret (listen) | server `is_shot_down` within 1 s; client copy hidden, `ProjectileMovement` tick off, location = server's shoot-down point, within 0.5 s |
| T2.8 own crew | rider + gunner on ship 1, ship 1 fires point-blank at a wall 8 m off the beam | rider, gunner, pilot and ship health unchanged |
| Splash 600 | T2.5 (spec table) | `60 x lerp(1, 0.3, d/600)` |
| T3.1 hull | ship unpiloted, harness turns the Mesh's collision off, `Aura.MechSentinel.TestBullet` from 25 m beside the hull at its centre | ship health -3 |
| T3.2 turret | TestBullet at turret 0's HitBox | turret health -3, ship unchanged |
| T3.3 character | TestBullet at the on-foot host | character -3 through the Pawn sweep |
| T3.4 untagged | TestBullet at an untagged GAS actor | no damage |

The gun's ball hit relies on GA_GunShootBP calling `MyFunc` with the hit actor on the server (as it does for
characters and the ship). If T2.6 shows no health change, check the graph passes non-ASC actors through.

---

## 5. Decisions and refinements (for the lead)

1. `GravityScale` replicated initial-only, so `SpawnTestCannonball`'s override reaches the clients (the spec only said
   "replaces the class's GravityScale").
2. A shot-down ball stops for good (movement tick off) and the client's copy is moved to the server's shoot-down point
   before its burst.
3. Impact / shoot-down FX de-duplicated per machine (`bImpactFXPlayed`).
4. First-bunch OnRep handled (BeginPlay re-applies the shot-down state); the burst always plays on an OnRep, since a
   shot-down ball lives at most `ImpactDestroyDelay`.
5. `ShouldIgnore` also covers actors attached to a rider, and riders when `bPassengersQueryOnly` is off.
6. The character gun doesn't count hits on its own ship's balls.
7. `SpawnTestCannonball` with a ship uses `UAirshipDamageEffect` and the ship's level; with no ship it deals no damage at
   all, sentinels included.
8. Spec D3 edge case "a bullet that hits a cannonball ends there, as any wall": true for a ball on the line when the
   bullet is fired (its end trace stops there). A ball that crosses the line mid-flight is an untagged blocker and the
   bullet flies on, like any untagged blocker in the code the spec gives.
