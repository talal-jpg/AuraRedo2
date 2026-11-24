# Airship round 2, PR A: implementation spec

Status: contract for the parallel implementers (2026-11-24). Base: `redo3` 53198d0, clone
`/mnt/new_partition/UnrealProjects/_AirshipWork`, on the thread's PR branch. Every `file:line` below is at
53198d0. Maps this spec was written from: `scratchpad/map/round2_map.json`, `scratchpad/map/lanes_map.json`.

What PR A delivers (the user's asks of 2026-11-24, minus lanes, teams, ship lives and swarm difficulty, which are PR B):

1. Two front machine-gun turrets with health, 4x the character gun per bullet, mountable, driver-fired when unmanned.
2. Bigger, slower cannonballs on a visible ballistic arc, with health (they can be shot down), splash damage.
3. Cannons and turrets mountable by any player (gunner stations); the driver fires only the unmanned guns.
4. Crew (pilot, gunners) and ship take damage, including from the Mech Sentinel swarm (which can't hurt ships today).
5. The ship keeps drifting slowly after the pilot leaves, or holds still when left at rest.
6. Steering wheel at character size; five marked deck pieces removed; bigger cannon bore; turret meshes.
7. Cannon smoke gone within 1 s.

Rules every implementer follows: work only in the clone, no commits, no editor, no Blender MCP, builds only through
`/mnt/new_partition/UnrealProjects/_AirshipWork_logs/build_r2.sh`, Classic (scheme 0) unchanged unless this spec says a
change applies to every scheme on purpose, code style of the existing Airship code (tabs, UE naming, comments that say
why), plain English in docs, no model names in any file.

Contents

* 0. Conventions and shared vocabulary
* 1. Decisions D1-D10 (design, API, replication, edge cases, hook points)
* 2. File ownership and the cross-owner API contract
* 3. Editor steps (asset scripts as_51-as_59)
* 4. PIE test plan
* 5. Risks, open items, order of work
* 6. Review fixes (2026-11-25): what the code review changed, with file:line after the fix build
* Appendix A: new settings table. Appendix B: new telemetry fields. Appendix C: console commands.

---

## 0. Conventions and shared vocabulary

* Hull space = HullCollision's component space = SK_Airship component space (Mesh sits at identity under HullCollision,
  `as_21_blueprint.py`). Units cm. +X bow, +Y starboard, +Z up. Port (L) = -Y.
* Stations (new, `EAirshipStation`, `Airship::NumStations = 6`):

  | Index | Name | Gun | Seat |
  |---|---|---|---|
  | 0 | CannonL1 | cannon 0 (forward port) | carriage `Cannon_L1` + `CannonSeatOffset` (mirrored) |
  | 1 | CannonL2 | cannon 1 (aft port) | carriage `Cannon_L2` + offset |
  | 2 | CannonR1 | cannon 2 (forward starboard) | carriage `Cannon_R1` + offset |
  | 3 | CannonR2 | cannon 3 (aft starboard) | carriage `Cannon_R2` + offset |
  | 4 | TurretL | turret 0 (port) | `TurretMounts[0].Location` + `TurretSeatOffset` |
  | 5 | TurretR | turret 1 (starboard) | `TurretMounts[1].Location` + `TurretSeatOffset` |

  Station index = cannon index for 0-3; turret index = station - 4. The helm is not a station (it stays the pilot's
  possession flow).
* "Gun units": damage measured in hits of the character gun. 1 unit = one GA_GunShoot hit. A turret bullet is
  `TurretGunDamageMultiplier` (4) units. Cannonball health is in gun units (decouples it from the GE value, which is 1 in
  the repo and 1000 in the user's local tree).
* "Gun base damage": the sum of GE_GunShootDamage's additive `IncomingDamage` modifier magnitudes at level 1, read at
  runtime (1.0 committed, 1000 in the user's local tree), fallback `GunDamageFallback` 1.0.
* Server = authority (listen host or dedicated). "Controlling machine" of a gun = the machine of its gunner, or the
  pilot's machine for an unmanned turret the driver fires.
* Every new tunable that is not a property of one class's own behaviour lives in `UAirshipSettings` (Project Settings >
  Game > Airship). Class-intrinsic tunables (cannonball radius / health, turret fire rate / heat) are UPROPERTYs of their
  class, editable on the Blueprint. None of the new properties is scheme-owned, so `Aura.Airship.Scheme 0` + `check` still
  lists 0 differences.
* `Aura.Airship.Set Settings.<Name> <Value>` (new prefix, D10) changes a setting at runtime on that machine (harness).

---

## 1. Decisions

### D1. Cannon smoke stops within 1 s

Cause (round2_map cannons_smoke): `NS_AirshipMuzzle`'s `Blast_Puffs` emitter (added by `as_06_muzzle.py:22-29` from the
engine Fountain template) keeps the template's own looping cycle (EmitterState Loop Duration 2 s, Loop Behavior
Infinite), and its puffs live 1.2-2.2 s. The system never completes, so every `bAutoDestroy` component spawned by
`HandleCannonsFired` (`AirshipPawn.cpp:1750`) stays on the muzzle socket and re-bursts every 2 s.

**Asset fix (assets owner, run by the lead in the editor stage).** New `as_51_muzzle_once.py`, in place on
`/Game/Assets/MyShip/Drivable/FX/NS_AirshipMuzzle` (pattern of `as_07_fix_muzzle_compile.py`, helpers `as_nh.py` /
`as_fxlib.py`):

1. Probe first and print: every emitter's `EmitterUpdateScript/EmitterState` inputs (`GetModuleInputValues`), the
   enum identifiers of Life Cycle Mode / Loop Behavior as the toolset returns them, and Blast_Puffs' InitializeParticle
   lifetimes. Never hard-code an enum value the probe didn't print.
2. For EVERY emitter whose Loop Behavior is not Once: Loop Behavior = Once, Loop Duration = 0.2 s (Life Cycle Mode
   stays Self). The muzzle is a one-shot effect.
3. Blast_Puffs: InitializeParticle Lifetime Min/Max 1.2/2.2 -> 0.5/0.85. Alpha fades to 0 by NormalizedAge 1: if the
   emitter has a ScaleColor (or color curve) module, set its alpha curve to 1 at age 0 and 0 at age 1; if it has none,
   add `/Niagara/Modules/Update/Color/ScaleColor` with Scale Alpha = `1.0 - Particles.NormalizedAge`
   (`fx_set` + `f_expr`; no `User.Global Scale` in the expression, see as_07).
4. Muzzle_Smoke lifetimes stay (0.2-0.3 s).
5. Read back every changed input, check the system compiles (`GetSystemCompileState`, latent: read it in a second
   inbox call with `as_pending_read`), save only this asset.

**as_06 rebuild keeps it (assets owner edits `as_06_muzzle.py`).** `fx_fountain_to(... (1.2, 2.2) ...)` at
`as_06_muzzle.py:24` becomes `(0.5, 0.85)`; after it, the same Loop Behavior Once / Loop Duration 0.2 / alpha fade as
as_51 step 2-3 (call a shared function defined in as_51, guarded so exec'ing as_51 from as_06 doesn't run its main).
Update the header comment.

**C++ safety net (core).** `UAirshipSettings::MuzzleFXMaxSeconds` (float, s, default 1.0, 0 = no cap). In
`HandleCannonsFired` (`AirshipPawn.cpp:1744-1756`) keep the returned component of both spawn paths
(`SpawnSystemAttached` and `SpawnSystemAtLocation`), and when it is valid and the cap > 0:

```cpp
TWeakObjectPtr<UNiagaraComponent> WeakFX(FX);
FTimerHandle Unused;
GetWorldTimerManager().SetTimer(Unused, FTimerDelegate::CreateWeakLambda(this, [WeakFX]()
{
	if (UNiagaraComponent* Component = WeakFX.Get())
	{
		// bAutoDestroy: completing removes the component
		Component->DeactivateImmediate();
	}
}), Settings->MuzzleFXMaxSeconds, false);
```

A weak lambda bound to the ship, so `EndPlay`'s `ClearAllTimersForObject` clears it. Same cap for the turret muzzle
flash (turret owner, see D6, `MuzzleFlashMaxSeconds` on the turret).

Edge cases: dedicated server spawns no FX (existing guard). A ship destroyed within 1 s: the components go with the
mesh. Client prediction plays the shot once (D5 per-cannon pending flags), so no double components.

### D2. Cannonballs: bigger, slower, ballistic aim, health, shot down in the air

**Class changes (combat owner, `AirshipCannonball.h/.cpp`).**

| Property | Was | Now | Where / why |
|---|---|---|---|
| `Radius` | 28 (h:73) | **50** cm | ball 1 m across |
| `GravityScale` | 1.0 (h:77) | **0.6** | slower ball keeps a usable range: level range at the 8.5 deg cap = v^2 sin 17 / g' = 7000^2 x 0.292 / 588 = 244 m |
| `MaxLifeSeconds` | 8 (h:81) | **10** s | slower ball; a downhill shot from altitude flies longer than 8 s |
| `SplashRadius` | 450 (h:85) | **600** cm | falloff to `SplashMinFraction` 0.3 kept |
| `SentinelHitRadius` | 60 (h:92) | **100** cm | scaled with the ball (50/28) |
| new `BallMaxHealth` | - | **30** gun units | EditDefaultsOnly; 0 = can't be shot |
| new `bSplashWhenShotDown` | - | **false** | a shot-down ball deals no damage (lead decision) |

New state: `float BallHealth` (server, set to `BallMaxHealth` in BeginPlay), `UPROPERTY(ReplicatedUsing =
OnRep_ShotDown) bool bShotDown`, `UPROPERTY(Replicated) FVector_NetQuantize ShotDownLocation` (both COND_None).

Collision: `CollisionSphere->SetCollisionResponseToChannel(ECC_Visibility, ECR_Block)` (replaces the Ignore at
`AirshipCannonball.cpp:39`), so the character gun's Visibility sweep (`MyPlayerController2.cpp:98-99`) and the turrets'
traces hit it. Camera stays Ignore, Pawn stays Overlap.

New public API (exact signatures; core and turret call these):

```cpp
/** Server: shot damage in gun units (1 = one character-gun hit; a turret bullet = TurretGunDamageMultiplier). At 0
 * health the ball bursts in the air: impact FX, no damage, no splash. True if this hit shot it down. Clients: false. */
UFUNCTION(BlueprintCallable, BlueprintAuthorityOnly, Category = "Airship|Cannonball")
bool ApplyShotDamage(float DamageUnits, AActor* DamageInstigator);

UFUNCTION(BlueprintPure, Category = "Airship|Cannonball")
float GetBallHealth() const { return BallHealth; }          // server value; clients see BallMaxHealth

UFUNCTION(BlueprintPure, Category = "Airship|Cannonball")
float GetBallMaxHealth() const { return BallMaxHealth; }

UFUNCTION(BlueprintPure, Category = "Airship|Cannonball")
bool IsShotDown() const { return bShotDown; }               // every machine (replicated)

/** Server: exploded or shot down (no longer a target). */
bool IsSpent() const { return bExploded || bShotDown; }

AAirshipPawn* GetSourceShip() const { return SourceShip; }  // every machine (InitialOnly)
float GetRadius() const { return Radius; }                  // the class default works on the CDO
float GetGravityScale() const { return GravityScale; }      // the class default works on the CDO

/** Test hook (server): spawns a ball like FireCannons does, without a cannon. SourceShip may be null (no damage spec:
 * the ball still flies, bursts and can be shot down). GravityScaleOverride >= 0 replaces the class's GravityScale. */
UFUNCTION(BlueprintCallable, BlueprintAuthorityOnly, Category = "Airship|Test", meta = (WorldContext = "WorldContextObject"))
static AAirshipCannonball* SpawnTestCannonball(UObject* WorldContextObject, TSubclassOf<AAirshipCannonball> BallClass,
	FVector Location, FVector Velocity, AAirshipPawn* SourceShip, float Damage = 60.f, float GravityScaleOverride = -1.f);

UFUNCTION(BlueprintImplementableEvent, Category = "Airship|Cannonball", meta = (DisplayName = "On Shot Down"))
void BP_OnShotDown(FVector Location);
```

`ApplyShotDamage` (server only; `!HasAuthority() || IsSpent() || BallMaxHealth <= 0 || DamageUnits <= 0` returns false):
`BallHealth -= DamageUnits`; at <= 0: `bExploded = true` (so `Explode` never runs), `bShotDown = true`,
`ShotDownLocation = GetActorLocation()`, `Movement->StopMovementImmediately()`, collision off, hidden,
`PlayShotDownFX()` locally (not on a dedicated server), `ForceNetUpdate()`, `SetLifeSpan(ImpactDestroyDelay)`, log
`Verbose` "shot down by <instigator>". If `bSplashWhenShotDown` (off by default) it calls `Explode` instead.
`OnRep_ShotDown` (clients): stop movement, hide, collision off, play the same FX at `ShotDownLocation` (late joiner: the
ball is hidden, FX only if the actor began play less than `ImpactDestroyDelay` ago). `PlayShotDownFX`: `ImpactFX` at
`ImpactFXScale` (the impact burst, "bursts in the air with its impact FX") + `BP_OnShotDown`. Why replicated state, not
a multicast: `MulticastImpact` is unreliable (h:116); a shot-down ball that keeps flying on a client would look like a
miss, and replicated state also reaches late joiners.

`ShouldIgnore` (`AirshipCannonball.cpp:166-180`), add before the cannonball test:

```cpp
// Deck riders of the firing ship (not attached, so IsAttachedTo misses them): no friendly fire on its own crew
if (SourceShip)
{
	if (const ACharacter* Character = Cast<ACharacter>(Actor); Character && SourceShip->IsPassengerCandidate(Character))
	{
		return true;
	}
}
```

(Review fix, section 6.4: the code now calls `AAirshipPawn::IsRiderForDamage` instead of `IsPassengerCandidate`.)
Attached gunners and turrets of the firing ship are already covered by `IsAttachedTo(SourceShip)` (recursive).
`BeginPlay` already ignores the source ship's attached actors (recursive) for movement (`:121-132`), which now includes
turrets and gunners.

`MulticastImpact` stays unreliable (unchanged behaviour for ordinary impacts).

**Character gun (combat owner, `GA_GunShoot.h/.cpp`).** New `UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category =
"Airship") float CannonballShotUnits = 1.f;`. At the top of `MyFunc` (`GA_GunShoot.cpp:297`), before the
`IAbilitySystemInterface` branch:

```cpp
// Airship cannonballs block Visibility and have health in gun units (no ASC): the server counts the hit
if (AAirshipCannonball* Ball = Cast<AAirshipCannonball>(InTargetActor))
{
	AActor* Avatar = GetAvatarActorFromActorInfo();
	if (Avatar && Avatar->HasAuthority())
	{
		Ball->ApplyShotDamage(CannonballShotUnits, Avatar);
	}
	return;
}
```

(The sentinel segment of the gun's shot now stops at a ball it hits, because `TraceWall` uses Visibility: correct, no
change needed.)

**Ballistic aim (core owner, `AirshipPawn.cpp:1429-1457` `ComputeCannonAimRaw`).** One function feeds firing
(`FireCannons` / `FireStation`), barrel tracking (`UpdateCannonAim`) and the HUD arc test (`IsAimInCannonArc`). Replace
the straight-line elevation with the low-arc solution, computed in world space and then converted to hull space:

```
Muzzle   = HullTM.TransformPosition(GetCannonMuzzleLocal(Cannon))
v        = CannonballSpeed
g        = |World->GetGravityZ()| * BallCDO->GetGravityScale()        // BallCDO = GetDefault of CannonballClass (or AAirshipCannonball)
Target'  = Target
if Settings->bCannonAimLeadShipVelocity:                              // the ball inherits the muzzle velocity (FireCannons :1664)
    repeat 2x: t = FlightTime(Muzzle, Target'); Target' = Target - ShipVelocity * t
d = horizontal distance Muzzle -> Target', h = Target'.Z - Muzzle.Z
if g <= 0 or d < 1: WorldDir = (Target' - Muzzle).GetSafeNormal()     // straight line
else:
    disc = v^4 - g (g d^2 + 2 h v^2)
    if disc < 0: theta = 45 deg (out of range: the max-range angle; the elevation clamp then caps it)
    else:        theta = atan((v^2 - sqrt(disc)) / (g d))              // low arc
    WorldDir = HorizontalDir * cos(theta) + Up * sin(theta)
FlightTime = d / max(v cos theta, 1)
ToTarget = HullTM.InverseTransformVectorNoScale(WorldDir), then yaw / elevation exactly as today (:1447-1456)
```

`ShipVelocity` = HullCollision's physics linear velocity (or `GetVelocity()` when not simulating). Why the lead
correction (a refinement with a reason, on in every scheme on purpose): at cruise the inherited 48 m/s would carry a
100 m shot (1.4 s) about 70 m off the crosshair. The elevation cap `CannonElevMaxDeg` 8.5 (h:612, the rig limit) is
unchanged; beyond 244 m level range the raw elevation is 45 deg, so `IsAimInCannonArc` reports out of arc and the shot
falls short at the cap.

Pawn default changes (core): `CannonballSpeed` 12000 -> **7000** cm/s (h:590); `CannonSpawnForwardOffset` 60 -> **80**
cm (h:620) and at runtime `max(CannonSpawnForwardOffset, BallCDO->GetRadius() + 30)` so a bigger ball never spawns
inside the barrel. Neither property is scheme-owned (not in the `AIRSHIP_PAWN_*_PROPS` lists, `AirshipPawn.cpp:202-231`).

**Aim traces ignore cannonballs (core).** New public helper on the pawn, used by the pilot's aim
(`ComputeLocalAimPoint`, `AirshipPawn.cpp:885-908`) and by gunners (D5):

```cpp
/** Visibility trace for aiming from this ship (camera or gunner view): ignores the ship, every actor attached to it
 * (recursive: turrets, pilot, gunners), its deck passengers and every cannonball (re-traced past them, at most 4 times).
 * OutPoint = the hit, or Start + Dir * Distance. */
bool TraceAimPoint(const FVector& Start, const FVector& Dir, float Distance, FVector& OutPoint) const;
```

Every cannonball, not just its own: a ball crossing the camera ray would otherwise yank the whole broadside onto it. The
turrets' own bullets use their own trace (D6) in which enemy balls are targets.

**BP_AirshipCannonball (assets, `as_52`):** BallMesh scale 0.56 -> 1.0, ImpactFXScale 2 -> 3, and the class values
above written explicitly on the CDO (as_03 sets Radius 28 / SplashRadius 450 / MaxLifeSeconds 8 explicitly at
`as_03_physmat_cannonball.py:79-81`: re-running as_03 would revert them, so as_52 must run after any as_03 run).

Edge cases: a ball shot down after its source ship died: no spec needed (no damage). Two of a broadside crossing:
unchanged. A ball shot by its own ship's turret: impossible (turret traces ignore own balls, D6). Clients that never
receive `bShotDown` (actor destroyed first): the actor destroy hides it anyway.

### D3. Mech Sentinel bullets damage airships and turrets

Root cause (round2_map damage_swarm): `FireSentinelBullet` traces Visibility for the end (`MechSentinelSwarmSubsystem.cpp
:543-546`), the hull (PhysicsBody) stops it, and `TickBullets` only accepts hits from a sphere sweep on **ECC_Pawn**
object types against player-controlled pawns (`:642-662`). The hull is never a Pawn body; the Mesh's Pawn bodies depend
on PA_Airship, which is empty in the user's tree.

**Design (combat owner, `MechSentinelSwarmSubsystem.h/.cpp`)**: opt-in by actor tag, no dependency on PA_Airship, no
change for anything untagged.

* `MechSentinelSwarmSubsystem.h`: `static const FName BulletTargetTag;` (public, on `UMechSentinelSwarmSubsystem`);
  `.cpp`: `const FName UMechSentinelSwarmSubsystem::BulletTargetTag(TEXT("MechSentinelBulletTarget"));` with a comment:
  actors with this tag take sentinel bullet hits found by a Visibility trace (airship hulls and turrets).
* `FFlyingBullet` (h:352-362) unchanged.
* `TickBullets` (`:644-673`): keep the Pawn sweep exactly as is. If it found no player pawn in this stretch, add:

```cpp
// Tagged non-pawn targets (airship hulls and turrets, whose collision is PhysicsBody / WorldDynamic): the first thing
// on this stretch that blocks Visibility, a little past the end because the target may have moved since the bullet
// was fired (BulletTargetSlack)
FHitResult Block;
const FVector TraceTo = bArrived ? To + Bullet.Direction * BulletTargetSlack : To;
FCollisionQueryParams BlockParams(SCENE_QUERY_STAT(MechSentinelBulletTarget), /*bTraceComplex*/ false);
if (World->LineTraceSingleByChannel(Block, From, TraceTo, ECC_Visibility, BlockParams))
{
	AActor* Target = Block.GetActor();
	const bool bDead = Target && Target->Implements<UMyCombatInterface>() && IMyCombatInterface::Execute_IsDead(Target);
	if (Target && !bDead && Target->ActorHasTag(BulletTargetTag))
	{
		ApplySentinelAttack(Target, Bullet.Start, Block.ImpactPoint, Bullet.Damage);
		bDone = true;
	}
}
```

  `BulletTargetSlack` = `constexpr float` 150 cm in the .cpp's private namespace (catches a hull that moved up to 4.5 m/s
  sideways during the 0.33 s flight; a ship moving along its own length still crosses the line). Untagged blockers
  (walls, enemies) do nothing, as before. `ApplySentinelAttack` (`:486-517`) already applies `GE_SentinelAttack` to the
  tagged actor's ASC (the ship's or the turret's UMyAttributeSet).
* Who tags: core adds `Tags.AddUnique(UMechSentinelSwarmSubsystem::BulletTargetTag)` in `AAirshipPawn`'s constructor
  (`AirshipPawn.cpp:236`), and to every turret right after spawning it (D6). Actor tags don't replicate; hits are
  server-only, which is enough.
* Targeting unchanged: `GatherPlayerTargets` (`:436-460`) still targets `PlayerState->GetPawn()` (the ship while
  piloted, the gunner's character while mounted).
* Test hook (dev builds, `#if !UE_BUILD_SHIPPING`, in the subsystem .cpp, pattern of `AirshipSubsystem.cpp:563`):
  `Aura.MechSentinel.TestBullet <FromX> <FromY> <FromZ> <ToX> <ToY> <ToZ> [Damage=3]` (server world): calls
  `FireSentinelBullet(From, To, Damage, Settings)` with a default `FMechSentinelBulletSettings` whose `Range` is
  `max(5000, |To - From| + 200)`. Logs the bullet. This is what the PIE harness uses for deterministic hits.

Edge cases: an unpiloted ship is never targeted (no PlayerState pawn), but a stray bullet that hits it now damages it
(intended, "an airship they hit"). A piloted ship with Pawn bodies in its PA: the Pawn sweep hits the Mesh first and
damages the ship exactly as today; only one path applies per bullet (`bDone`). A dead ship (IsDead) is skipped. A bullet
that hits a cannonball (now blocking Visibility) ends there, as any wall.

Not in PR A: a `MechSentinelObstacleComponent` on BP_AirshipPawn (sentinels fly through hulls today); who sentinels
target when a ship is unmanned (PR B).

Review fix (section 6.3): both turret mounts sit inside the hull's forward deck convex (UCX_01), so the Visibility trace
above always finds the hull first. `UMechSentinelSwarmSubsystem::BulletTargetRedirect` (bound by `UAirshipSubsystem`)
hands such a hull hit to the turret behind it.

### D4. Crew damage

**Server, core owner (`AirshipPawn.h/.cpp`).**

* In `BeginPlay` after the attribute init (`AirshipPawn.cpp:388-394`), on authority:
  `AbilitySystemComponent->GetGameplayAttributeValueChangeDelegate(UMyAttributeSet::GetHealthAttribute()).AddUObject(this,
  &ThisClass::OnShipHealthChanged);`
* `void OnShipHealthChanged(const FOnAttributeChangeData& Data)`: if authority, `Settings->CrewDamageShare > 0`,
  `Data.NewValue < Data.OldValue`: `PendingCrewDamage += (Old - New) * CrewDamageShare` and, if no flush is queued,
  `GetWorldTimerManager().SetTimerForNextTick(this, &ThisClass::FlushCrewDamage)`. Why deferred: the change fires inside
  the damage effect's execution (as `Die`, `:2266`), and ejecting possesses / detaches characters.
* `void FlushCrewDamage()`: take `PendingCrewDamage` (reset to 0). Crew = `PilotCharacter` + every valid
  `StationGunners[s]`. For each living crew member with an ASC that has `UMyAttributeSet` (`HasAttributeSetForAttribute
  (Health)`):
  * Health = its current Health. If `Damage >= Health` (the share would kill): pilot -> `UnboardPilot(true)`; gunner ->
    `DismountGunner(Station, true)`. Then apply (the normal on-foot death runs, GameMode respawn included).
  * Apply: spec from the **ship's** ASC with `DamageEffectClass` (null -> `UAirshipDamageEffect`), level `ShipLevel`,
    context `AddInstigator(this, this)`, `SetSetByCallerMagnitude(MyTags::SetDamageByCaller, Damage)`,
    `AbilitySystemComponent->ApplyGameplayEffectSpecToTarget(*Spec.Data.Get(), CrewASC)`.
  * Log `Log`: "crew damage <name> <amount> (<share> of <loss>)".
* `Die()` (`:2252`) keeps its next-tick `EjectPilotAfterDeath` (renamed `EjectCrewAfterDeath`), which first calls
  `FlushCrewDamage()` (the last loss reaches the crew) and then ejects the pilot (`UnboardPilot(true)`) and every gunner
  (`DismountGunner(s, true)`).
* Pilot vitals: **remove** the boarding snapshot (`BoardPilot`, `:1115-1126`, and the members `SavedPilotHealth`,
  `SavedPilotMana`, `bHasSavedPilotVitals` at h:1208-1211). In `UnboardPilot`, right before `PC->Possess(Pilot)`
  (`:1216`), read the pilot ASC's current Health and Mana; after the possession (which refills them through
  `AMyCharPlayer::PossessedBy -> InitAbilitySystemAfterRespawn`, `MyCharPlayer.cpp:374-381, 420-436`), write them back
  (`:1220-1228` keeps its shape with the new values). Damage taken while flying stays.
* Gunners: no vitals handling (they stay possessed, nothing refills them).
* Direct hits: gunners keep actor collision with a QueryOnly capsule (D5), so overlaps (cannonball splash, Pawn sweeps)
  and traces can reach them. Known limit: SM_Airship's walkable UCX lid sits 1.2-2.9 m above the planks
  (CPP_NOTES.md:111-117) and the gantry convex reaches z 1080, so most Visibility traces at a gunner hit the hull first;
  the ship then loses Health and the gunner takes the crew share instead. Overlap-based damage (splash) reaches them
  directly, so a gunner near an enemy ball's impact can take both (intended: they were hit).
* The pilot keeps actor collision off (unchanged): only the crew share reaches the pilot.

Edge cases: a crew member already dead (IsDead) is skipped. A pilot/gunner with no ASC (non-player test pawns) is
skipped. Repeated hits in one frame add up in `PendingCrewDamage` (one flush). `CrewDamageShare` 0 = off. Ship healing
(Health up) gives nothing back. Damage numbers: the source is the ship's ASC, whose PlayerController is the pilot's, so
the pilot sees crew-damage numbers on his own screen (cosmetic, accepted).

Numbers to watch (tuning, not decided here): a 60 hit = 15 to every crew member; the character's MaxHealth comes from
its attribute GE, not checked here.

### D5. Gunner stations (cannons + turrets)

#### D5.1 Model

* The gunner **stays possessed** in its own character. The character is attached to the ship's **HullCollision** at the
  station seat, movement off, active abilities cancelled, actor collision **on** (capsule QueryOnly through the passenger
  path). Its own camera aims (the control rotation's view ray). Sentinels keep targeting it (PlayerState pawn).
* RPCs go through `UAirshipPilotComponent` (on every PlayerController, `AirshipSubsystem.cpp:84-94`).
* The ship holds the station state.

#### D5.2 Ship state and API (core, `AirshipPawn.h/.cpp`)

Replicated (add to `GetLifetimeReplicatedProps`, `AirshipPawn.cpp:349-359`, COND_None):

```cpp
/** Who mans each station (EAirshipStation order; size Airship::NumStations, set in the constructor). */
UPROPERTY(ReplicatedUsing = OnRep_StationGunners, VisibleInstanceOnly, BlueprintReadOnly, Category = "Airship|Stations")
TArray<TObjectPtr<ACharacter>> StationGunners;

/** Each manned station's aim point (world, cm), from its gunner (ServerSetGunnerAim). Observers aim the guns with it. */
UPROPERTY(Replicated)
TArray<FVector_NetQuantize> StationAims;

/** The two turrets (server spawns them; clients get the actors). Size Airship::NumTurrets. */
UPROPERTY(Replicated, VisibleInstanceOnly, BlueprintReadOnly, Category = "Airship|Turrets")
TArray<TObjectPtr<AAirshipTurret>> Turrets;
```

Server-only: `TWeakObjectPtr<APlayerController> StationControllers[Airship::NumStations]`, `bool
StationTrigger[Airship::NumStations]`, `bool bStationGunnerWasAlwaysRelevant[...]`, `FVector StationSeatLocal[...]`
(every machine, from `RefreshCannonGeometry`).

Every machine, local: `FVector LocalStationAim[...]`, `uint64 LocalStationAimFrame[...]` (set by this machine's own
gunner every frame; used instead of the replicated aim for that station on that machine).

Public API (the pilot component and the subsystem call these):

```cpp
// Server
bool CanMount(const ACharacter* Candidate, int32 Station) const;             // living player character, station free, not piloting, not mounted anywhere, ship alive, turret not destroyed
bool IsWithinStationRange(int32 Station, const FVector& PawnLocation) const;   // horizontal <= StationMountDistance from the seat, vertical -StationMountHeightBelow..+StationMountHeightAbove
bool MountGunner(ACharacter* Gunner, APlayerController* PC, int32 Station);
void DismountGunner(int32 Station, bool bEject);
void SetStationAim(int32 Station, const FVector& AimPoint);                   // validated: finite, within GunnerMaxAimDistance of the seat
void SetStationTrigger(int32 Station, bool bHeld);                            // turrets only
void FireStation(int32 Station, const FVector& AimPoint);                     // cannons: one ball if loaded (per-cannon cooldown)
int32 FindStationOf(const ACharacter* Character) const;                       // -1 if none (every machine, from StationGunners)

// Every machine
UFUNCTION(BlueprintPure) ACharacter* GetStationGunner(int32 Station) const;
UFUNCTION(BlueprintPure) bool IsStationManned(int32 Station) const;
bool IsCannonManned(int32 Cannon) const { return IsStationManned(Cannon); }
FVector GetStationSeatLocation(int32 Station) const;                          // world
FTransform GetStationSeatRelativeTransform(int32 Station, const ACharacter* Gunner) const; // hull-relative, feet + half height + PilotSeatClearance, facing
AAirshipTurret* GetTurret(int32 TurretIndex) const;
float GetCannonReloadAlpha(int32 Cannon) const;                               // new overload, per cannon (see D5.6)
bool IsSideFullyManned(EAirshipSide Side) const;

// A gunner's own machine (the pilot component calls it every frame): responsive barrel tracking there
void SetLocalStationAim(int32 Station, const FVector& AimPoint);
// A gunner's own machine: shows its cannon shot at once (recoil, flash); the multicast skips it there
bool PredictStationFire(int32 Station);                                       // false if this machine's reload isn't done

bool TraceAimPoint(const FVector& Start, const FVector& Dir, float Distance, FVector& OutPoint) const; // D2
float GetCannonAimTraceDistance() const { return CannonAimTraceDistance; }   // gunners trace as far as the pilot

static void CancelPilotAbilities(ACharacter* Pilot);                          // moved from private (h:1203) to public
```

Seat positions (`RefreshCannonGeometry`, `AirshipPawn.cpp:1361-1395`, every machine):

* Cannons: carriage bones `CannonCarriageBones = { "Cannon_L1", "Cannon_L2", "Cannon_R1", "Cannon_R2" }` (new
  UPROPERTY, EditFixedSize, next to `CannonBarrelSockets` h:578), fallback `CannonCarriageFallback = { (-46.3, -598.5,
  243.7), (-1147.2, -392.7, 283.6), (-46.3, 598.5, 243.7), (-1147.2, 392.7, 283.6) }` (README_rig.md cannon table).
  Seat = carriage + `(O.X, Inboard * O.Y, O.Z)` with `O = Settings->CannonSeatOffset` (-90, 130, 0) and Inboard = +1 for
  port, -1 for starboard. Results: L1 (-136, -469, 244), L2 (-1237, -263, 284), R mirrored. Why there: 1.3 m inboard of
  the carriage and 0.9 m aft of it, beside the breech, clear of the 60 cm recoil (the breech reaches about 1.65 m inboard
  of the carriage at full recoil, on the barrel axis; the seat is 0.9 m off that axis).
* Turrets: `Settings->TurretMounts[t].Location + Settings->TurretSeatOffset` (-100, 0, 0): (2000, -/+245, 655).
* Facing (relative yaw): cannons outboard (port -90, starboard +90), turrets 0 (bow).

`MountGunner` (server; modelled on `BoardPilot` `:1105-1164`):

1. `CanMount(Gunner, Station)` and `PC && PC->GetPawn() == Gunner`, else false.
2. `CancelPilotAbilities(Gunner)`.
3. `Move->StopMovementImmediately(); Move->DisableMovement(); Move->SetComponentTickEnabled(false);`
4. Actor collision stays **on** (do NOT call `SetActorEnableCollision(false)`).
5. `Gunner->AttachToComponent(HullCollision, SnapToTargetNotIncludingScale)`;
   `SetActorRelativeTransform(GetStationSeatRelativeTransform(Station, Gunner))`.
6. `bStationGunnerWasAlwaysRelevant[s] = Gunner->bAlwaysRelevant; Gunner->bAlwaysRelevant = true;` (attached actors
   don't share the ship's relevancy).
7. `StationGunners[s] = Gunner; StationControllers[s] = PC; StationTrigger[s] = false;` `StationAims[s]` = seat +
   station rest direction x 10000 (cannon rest dir, turret +X).
8. `RefreshPassengers()` (capsule -> QueryOnly now, collision is on: a valid QueryOnly body).
9. Turret station: `Turrets[t]` gets its command from now on (D6).
10. `ForceNetUpdate()`; the PC's `UAirshipPilotComponent->ClientMountChanged(this, Station, FVector::ZeroVector,
    FVector::ZeroVector)`.
11. Log "mounted <name> at <station>".

`DismountGunner(Station, bEject)` (server):

1. Take the gunner and PC, clear `StationGunners[s]`, `StationControllers[s]`, `StationTrigger[s]` first (guard against
   re-entry). If the gunner is invalid: `ForceNetUpdate()` and return.
2. Exit point (hull-relative): seat + `Settings->CannonExitOffset` (0, 120 inboard, 0; Y mirrored like the seat) for
   cannons, seat + `Settings->TurretExitOffset` (-150, 0, 0) for turrets; then the `UnboardPilot` deck trace
   (`HullCollision->LineTraceComponent` from +300 above to -600 below, `:1186-1194`) puts the feet on the top hull
   surface (the UCX lid), + half height + `PilotSeatClearance`.
3. `DetachFromActor(KeepWorldTransform)`, `SetActorLocationAndRotation(exit, yaw = hull yaw, TeleportPhysics)`,
   `bAlwaysRelevant` restored, `UAirshipSubsystem::RepairPhysicsState(Gunner)`.
4. Alive: `Move->SetComponentTickEnabled(true); Move->SetMovementMode(MOVE_Falling)`, launch with the ship's velocity
   (+ `EjectUpSpeed` / `EjectSideSpeed` outboard when `bEject`, as `:1230-1238`). Dead: tick back on, no launch.
5. `RefreshPassengers()`.
6. `PC's pilot component->ClientMountChanged(nullptr, -1, ExitHullLocal, LaunchVelocity)` (hull-relative exit so the
   client puts its own copy where the server did, against its own hull transform; less snap than the pilot's exit).
7. `ForceNetUpdate()`; log.

`UpdateStations()` (server, in `Tick` after `UpdateCannonAim`, `AirshipPawn.cpp:474`): for each manned station, dismount
when the gunner is invalid / being destroyed / dead (`IMyCombatInterface::Execute_IsDead`) / no longer possessed by its
controller (`PC->GetPawn() != Gunner`, logout or respawn) / no longer attached to this ship / the station's turret is
destroyed (`bEject` true for the turret case and when the ship is dead). Then `UpdateTurretCommands()` (D6).

`CanBoard` (`:1039-1054`): also refuse when `UAirshipSubsystem::FindGunnerStation(Character, Ship, Station)` finds the
character mounted anywhere.

`EndPlay` (`:410-454`, authority): before the pilot block, `DismountGunner(s, false)` for every manned station; after
it, destroy every turret (`Turrets[t]->Destroy()`).

`OnRep_StationGunners` (clients): for every gunner now manning a station: if it is in `PassengersWithCollisionOff`,
turn its actor collision back on + `RepairPhysicsState` + remove it from the list, then `RefreshPassengers()`; for every
character that left a station: nothing (the normal passenger restore handles it). Broadcast a new
`OnStationsChanged` (dynamic multicast, `(AAirshipPawn*, int32 Station, ACharacter* Gunner)`) for HUD/BP.

`UpdatePassengerCollision` (`AirshipPawn.cpp:1272-1315`, clients): skip stationed gunners when turning collision off
(`FindStationOf(Passenger) >= 0` -> continue at `:1281`), and restore a listed character when it is a stationed gunner
(add `|| FindStationOf(Passenger) >= 0` to the restore test at `:1301`). Why: attachment and `StationGunners` replicate
separately, and a gunner's client-side collision is needed so other clients' gun traces (client-reported target data)
can hit it.

#### D5.3 Pilot component (core, `AirshipPilotComponent.h/.cpp`)

RPCs (all on the PlayerController's component, so the owning connection may call them):

```cpp
// F on foot (existing, extended): the server picks the nearest of the helm (existing range rule) and the free stations
UFUNCTION(Server, Reliable) void ServerRequestBoard();
// Explicit station (UI, tests)
UFUNCTION(Server, Reliable) void ServerRequestMount(AAirshipPawn* Ship, uint8 Station);
UFUNCTION(Server, Reliable) void ServerRequestDismount();
// Mounted gunner: aim (25 Hz and on change), cannon press, machine-gun trigger
UFUNCTION(Server, Unreliable) void ServerSetGunnerAim(FVector_NetQuantize AimPoint);
UFUNCTION(Server, Reliable) void ServerGunnerFire(FVector_NetQuantize AimPoint);
UFUNCTION(Server, Reliable) void ServerGunnerTrigger(bool bHeld, FVector_NetQuantize AimPoint);
// Server -> owning client: mounted (Ship, Station >= 0) or dismounted (null, -1, exit point in hull space, launch velocity)
UFUNCTION(Client, Reliable) void ClientMountChanged(AAirshipPawn* Ship, int8 Station, FVector_NetQuantize ExitHullLocal, FVector_NetQuantize LaunchVelocity);
```

Server side (validation in the `_Implementation`s; nothing trusts the client beyond its aim):

* `ServerRequestBoard` (`:179-185`): cooldown, then `TryUseNearest()`: candidates = the helm of every living ship
  without a pilot within `IsWithinBoardRange(Location, BoardDistance, BoardHullDistance, BoardBelowDistance)` (distance
  = to the pilot seat), and every free station `s` of every living ship with `IsWithinStationRange(s, Location)`
  (distance = 3D to the seat). Nearest wins: helm -> `Ship->BoardPilot`, station -> `Ship->MountGunner`. Nothing in
  range: refused (log).
* `TryMount(Ship, Station, bIgnoreRange)`, `TryDismount()` (public, the console uses them).
* `ServerRequestMount`: cooldown, `TryMount(Ship, Station, false)`.
* `ServerRequestDismount`: cooldown, `TryDismount()`.
* `ServerSetGunnerAim` / `ServerGunnerFire` / `ServerGunnerTrigger`: find the PC's pawn's station
  (`UAirshipSubsystem::FindGunnerStation`); ignore if not mounted or the aim has NaN; `SetStationAim`, then
  `FireStation` (cannon stations only) or `SetStationTrigger` (turret stations only).

Owning client (also the listen host for its own player):

* `ClientMountChanged(Ship, Station >= 0)`:
  * store `LocalShip`, `LocalStation`; enable component tick with `TickInterval 0`.
  * attach the local character to `Ship->GetHull()` at `GetStationSeatRelativeTransform` (same as the server; the
    replicated attachment then agrees), `CMC->DisableMovement()`, `CMC->SetComponentTickEnabled(false)`.
  * push `GunnerInputComponent` (a new `UEnhancedInputComponent`, like `BoardInputComponent` at `:106-109`) and add
    `IMC_Airship` at `AirshipMappingPriority` (1). Bindings (actions from UAirshipSettings, loaded synchronously):
    * `BindActionValue` for every IMC_Airship action (throttle, steer, lift, strafe, boost, brake, fire, aim, look, zoom,
      exit), so each of their keys is consumed (on-foot movement, jump and abilities on those keys stay quiet).
    * Look (Triggered): `PC->AddYawInput` / `AddPitchInput` with the Options sensitivity and invert, copy of
      `AAirshipPawn::OnLookInput` (`AirshipPawn.cpp:910-939`).
    * Fire (Started): cannon station -> `RequestGunnerCannonFire()`; turret -> `bLocalTrigger = true`,
      `ServerGunnerTrigger(true, aim)`. Fire (Completed, Canceled): turret -> `bLocalTrigger = false`,
      `ServerGunnerTrigger(false, aim)`.
    * Aim (Started/Completed): the character's first `UCameraComponent` FOV += `GunnerAimFOVOffset` / restored.
    * Zoom (Triggered): the character's first `USpringArmComponent` `TargetArmLength` -/+ `GunnerZoomStep`, clamped to
      [`GunnerZoomMinScale`, `GunnerZoomMaxScale`] x its value at mount.
    * Exit (Started): `RequestDismount()` -> `ServerRequestDismount()` (F: IMC_Airship's F consumes IA_AirshipBoard,
      `OnBoardPressed` never sees it).
  * gunner HUD (D5.7).
* `ClientMountChanged(null, -1, ExitHullLocal, Launch)`: pop the input component, remove IMC_Airship, restore FOV and
  arm length, remove the HUD; detach the local character (if still attached), put it at
  `LocalShip hull transform * ExitHullLocal` when the ship is still valid, `CMC->SetComponentTickEnabled(true)`,
  `SetMovementMode(MOVE_Falling)`, `Velocity = Launch`; clear local state; tick back to the 0.25 s setup mode
  (disabled once setup is done).
* `TickComponent` while mounted locally:
  * if `LocalShip` is gone or no longer lists the pawn at `LocalStation` for 1 s: unmount locally (safety net).
  * `PC->GetPlayerViewPoint` -> `LocalShip->TraceAimPoint(ViewLocation, ViewRotation.Vector(),
    LocalShip->GetCannonAimTraceDistance(), Aim)`; `LocalShip->SetLocalStationAim(Station, Aim)`; turret station:
    `Turret->SetLocalCommand({Aim, true, bLocalTrigger, Pawn})` (cosmetic prediction).
  * send `ServerSetGunnerAim(Aim)` when `Now - LastAimSend >= 1 / GunnerAimSendRate` and (moved more than
    `GunnerAimSendMinDelta` cm or `Now - LastAimSend >= GunnerAimHeartbeat`). Listen host: call the ship directly.
* `RequestGunnerCannonFire()`: host -> `Ship->FireStation(Station, Aim)`. Client -> if `Ship->PredictStationFire(Station)`
  (its own per-cannon reload done: plays recoil/flash once, marks the cannon pending) then `ServerGunnerFire(Aim)`.
* `OnBoardPressed` (`:142-153`): unchanged rule for a pilot (pawn is an AAirshipPawn -> ignore); mounted locally ->
  `RequestDismount()` (defensive; normally the Exit binding has it); else `RequestBoard()`.
* `EndPlay`: tear the gunner input down too.

#### D5.4 Driver vs mounted guns (core, `AirshipPawn.cpp`)

* Per-cannon cooldowns: `LastSideFireTime[2]` (h:1297) -> `double LastCannonFireTime[Airship::NumCannons]` (server);
  `LastPredictedFireTime[2]` / `bPredictedShotPending[2]` (h:1298-1299) -> per cannon
  `LastPredictedCannonFireTime[4]`, `bPredictedShotPending[4]` (set only on the machine that predicted: the pilot's
  client or a gunner's client; never on the server).
* `FireCannons(Side, Aim)` (`:1597-1691`, server): mask = cannons of `Side` that are **not manned** and loaded
  (`Now - LastCannonFireTime[c] >= CannonCooldown - 0.1`). Empty mask: return. For each: the existing spawn body,
  factored into `SpawnCannonball(int32 Cannon, const FVector& AimPoint, const FGameplayEffectSpecHandle& Spec)`
  (returns the ball). Broadside spec instigator stays the ship (`:1623`). Balls of one broadside ignore each other
  (`:1684-1688`, generalised to every pair). Then `MulticastCannonsFired(Mask)`.
* `FireStation(Station, Aim)` (server, cannon stations): manned by a living gunner, loaded (same tolerance) -> spec from
  the ship's ASC with `Context.AddInstigator(Gunner, this)` (damage numbers and XP go to the gunner) ->
  `SpawnCannonball(c, Aim, Spec)` -> `MulticastCannonsFired(1 << c)`.
* `MulticastCannonsFired(uint8 CannonMask)` replaces `(EAirshipSide Side)` (h:1074-1075). Implementation: for each
  cannon in the mask, skip it if `bPredictedShotPending[c]` and `Now - LastPredictedCannonFireTime[c] < CannonCooldown +
  0.5` (clear the flag either way); play the rest with `HandleCannonsFired(RemainingMask, false)`. The
  `IsLocallyControlled() && !HasAuthority()` gate (`:1696`) goes: the pending flags carry the same meaning per cannon.
* `HandleCannonsFired(uint8 Mask, bool bLocalShot)` replaces `(EAirshipSide Side)`: recoil count, muzzle FX (D1 cap),
  hull kick for the cannons in the mask; `AddFeedback(FeedbackOwnBroadside)` and `LastOwnBroadsideTime` only when
  `bLocalShot && IsLocallyControlled()` (the pilot's own broadside); `BP_OnCannonsFired(side of the lowest cannon in the
  mask)` (signature kept).
* `RequestFire` (`:1550-1586`, pilot's machine): first `if (IsDriverTurretArc()) return;` (D6: LMB in the forward arc
  drives the turrets). Then mask = unmanned and locally loaded cannons of the aim side; empty -> return (no prediction,
  no RPC). Host: `FireCannons`. Client: mark the mask's cannons pending + times, `HandleCannonsFired(Mask, true)`,
  `ServerFireCannons(Side, Aim)` (signature unchanged).
* `ServerFireCannons_Implementation` (`:1588-1595`): unchanged.
* `UpdateCannonAim` (`:1512-1548`): per cannon: manned -> aim at `LocalStationAim[c]` when this machine set it this or
  last frame, else `StationAims[c]` (replicated), always tracked (not only on the aim side); unmanned on the pilot's
  aim side -> the pilot's aim (as today); else rest.
* `IsAimInCannonArc(Side, Aim)`: only unmanned cannons of the side. New `bool IsCannonAimInArc(int32 Cannon, const
  FVector& Aim) const` for the gunner HUD.
* `GetCannonReloadAlpha(EAirshipSide)` (`:1407-1420`): min over the side's unmanned cannons of the per-cannon alpha
  (server clock on the server, the predicted clock on a client); 1 when all are manned. New `GetCannonReloadAlpha(int32
  Cannon)`.
* `PointFlyGunLock` (`:3523-3578`): in the sector branch, if the side the aim is on (`Bearing > 0` -> starboard) is
  fully manned, behave as outside the sector (no lock, return H).
* `GetCombatSocketLocation` (`:521-526`): unchanged.

#### D5.5 Edge cases

* A gunner may man a gun with no pilot aboard (drift/hold continue, D9).
* Ship death: gunners ejected (`EjectCrewAfterDeath`), turrets stop (D6).
* Gunner death (any cause): `UpdateStations` dismounts the dead character the next tick (no launch); the GameMode's
  respawn later destroys the body (`MyGameMode.cpp:290-296`). Review fix (section 6.6): from the death on, the ragdoll
  ignores the hull (its seat is inside the hull's convex hulls); PIE check T5.15.
* Logout: the PC is destroyed, its pawn goes (`PawnLeavingGame`), the station clears next tick.
* EndPlay of the ship: gunners dismounted (not ejected), turrets destroyed.
* Two players race for one station: the server serialises; the second is refused (log).
* The pilot can't mount (his PC's pawn is the ship); a gunner can't board (CanBoard); a gunner presses F -> dismount.
* Scheme switch, debug input: no effect on stations.
* Listen-server host as gunner: every RPC path runs locally (Client RPC on a local PC executes locally; the host calls
  the ship directly for aim and fire, no prediction).
* Late joiners: `StationGunners`, `StationAims`, `Turrets` and attachment replicate; `OnRep_StationGunners` and the
  passenger fix keep their collision on; turret `bDestroyed` has an OnRep (D6).
* Autonomous proxy while attached: CMC ticking off on server and owner, so no new ServerMoves. Moves already on the way
  when the mount happens still reach the server (ServerMove only checks `IsActive`), and their corrections would move
  the attached capsule on the client. Review fix (section 6.1): the server ignores the gunner's move errors while it is
  mounted, the owner ignores corrections, and the owner puts its copy back on the seat if it drifts (PIE check T5.13).
* Abilities: `CancelPilotAbilities` at mount; keys mapped in IMC_Airship are consumed. Ability keys that IMC_Airship
  doesn't map stay live, exactly as for the pilot today (known limit, section 5).

#### D5.6 Reload clocks

`GetCannonReloadAlpha(int32 Cannon)` = clamp((Now - Last) / CannonCooldown, 0, 1) with Last = `LastCannonFireTime[c]`
on the server, `LastPredictedCannonFireTime[c]` on a client. A gunner client's own cannon reload is its prediction
clock; the pilot's client uses its own for the cannons it fired.

#### D5.7 HUD (core, `AirshipHUDWidget.h/.cpp`)

* New gunner mode: `void SetGunnerStation(AAirshipPawn* Ship, int32 Station)` (null / -1 = off). The pilot component
  creates one `UAirshipHUDWidget` over the whole viewport (ZOrder 1, like `AddShipOverlay`, `AirshipPawn.cpp:2566-2605`)
  on mount and removes it on dismount. It draws: a crosshair at the screen centre, the projected point where the gun
  actually points (barrel direction x 100 m), a small panel bottom-left: station name (`CANNON L1` .. `GUN R`), cannon
  reload bar (`GetCannonReloadAlpha(c)`, `OUT OF ARC` tag when `!IsCannonAimInArc`) or turret heat bar (`OVERHEAT` tag)
  + turret health bar, the ship's hull bar, `F  LEAVE`.
* Pilot panel: a `GUNS` row (+`GunsRowHeight` 24 to `GetPanelSize()`): two heat bars with health underline for the
  turrets (an `X` when destroyed), six station dots (filled = manned); PORT / STBD show `MANNED` when
  `IsSideFullyManned`. A `PILOT` health bar (the pilot character's own ASC Health / MaxHealth, replicated to the owner)
  next to the hull bar, because the on-foot overlay is hidden while flying. Applies to every scheme on purpose (new
  hardware on the ship).

### D6. Front machine-gun turrets

#### D6.1 Placement (refined from the lead's x 2400-2900, with a reason)

The user's image 2 puts the turrets on the side edges of the narrow forward deck, a bit **behind** the small grate near
the bow. Measured on the image: the arrow tips sit about 40 % of the way from the end of the big flat hatch (hull x 1712,
deck slab `gantry_high_25`) to the corner posts `SearchLight_MidL/MidR` (x 2460), i.e. x about 2000-2150, and the small
grate itself is islands 234-236 at x 2249-2347 (`Docs/Airship/research/sm_airship_islands.json`). So the mounts are at
**x 2100**. The narrow deck (Gantry island 232) is |y| <= 320 with its top at **z 655**; its side rails (islands 319/339)
run at |y| 292-308, top z 768. A turret base of radius 45 cm stays inboard of the rail at **|y| 245**. The gun pivot at
deck + 150 (z 805) clears the rail top even at -20 deg pitch. Default mounts (UAirshipSettings, hull space):

| Turret | Location | Yaw min / max (deg, 0 = bow, + = toward starboard) | Pitch min / max |
|---|---|---|---|
| 0, port (station 4) | (2100, -245, 655) | -110 / +30 | -20 / +40 |
| 1, starboard (station 5) | (2100, 245, 655) | -30 / +110 | -20 / +40 |

The Blender step writes the measured deck top and rail clearance at these points to
`SourceArt/Airship/turret_dims.json` (D7); the lead updates the settings defaults if they differ by more than 5 cm.
Shots ignore the own ship, so the forward lamp posts and the raised bow tier (z 735) never block them.

#### D6.2 Class (turret owner, new `AirshipTurret.h/.cpp`)

`UCLASS(Blueprintable) class AURA_API AAirshipTurret : public AActor, public IAbilitySystemInterface, public
IMyCombatInterface`.

Construction: `bReplicates`, `SetReplicatingMovement(true)` (attachment replication), `bAlwaysRelevant`,
`NetUpdateFrequency 30`, `PrimaryActorTick` on, `TG_PostPhysics` (after the hull moved). Components:

| Component | Type | Setup |
|---|---|---|
| `Root` | USceneComponent | root, at the mount on the deck (z 0 = deck top) |
| `HitBox` | UBoxComponent | child of Root, extent (60, 60, 95) at z 95; QueryOnly; object WorldDynamic; Block all, Ignore Camera, Ignore Pawn; overlap events on (AMyProjectile) |
| `BaseMesh` | UStaticMeshComponent | child of Root; yaw part; NoCollision; mesh set on the BP |
| `GunMesh` | UStaticMeshComponent | child of BaseMesh at (0, 0, `PivotHeight`); pitch part; NoCollision |
| `Muzzle` | USceneComponent | child of GunMesh at (`MuzzleForward`, 0, 0) |
| `MuzzleFXComponent` | UNiagaraComponent | child of Muzzle; auto-activate off; system on the BP (NS_AirshipTurretMuzzle) |
| `DestroyedFXComponent` | UNiagaraComponent | child of Root; auto-activate off; NS_AirshipTurretFire, scale 0.3 on the BP |
| `AbilitySystemComponent` | UMyAbilitySystemComponent | as the ship (`AirshipPawn.cpp:319-320`) |
| `AttributeSet` | UMyAttributeSet | |

Tunables (EditDefaultsOnly, BlueprintReadOnly, category `Airship|Turret`): `FireInterval` 0.1 s (10 rounds/s),
`SpreadDeg` 1.0, `Range` 25000 cm, `HeatPerShot` 1/30 (30 shots = 3 s to overheat), `CoolRate` 0.4 /s, `CoolDelay` 0.2 s
(cooling starts this long after the last shot), `OverheatRecover` 0.35, `YawRateDeg` 180, `PitchRateDeg` 120,
`ArcToleranceDeg` 3 (fires only while the target is within the limits + this), `TurretMaxHealth` 400, `TurretArmor` 0,
`BallSweepRadius` 40 cm, `SentinelShotRadius` 20 cm, `SentinelMaxTargets` 1, `PivotHeight` 150 cm, `MuzzleForward` 180
cm, `LocalCommandTimeout` 0.25 s, `MuzzleFlashMaxSeconds` 1.0, `DamageEffectClass` (null = `UAirshipDamageEffect`),
`TracerSystem` (NS_AirshipTurretTracer), `TracerDataChannel` (NDC_GunShootHit), `DestroyedExplosionFX`
(NS_FireExplosion), `DestroyedExplosionScale` 1.0. `PivotHeight` / `MuzzleForward` come from `turret_dims.json` via
as_55.

Replicated: `Ship` (InitialOnly), `TurretIndex` (InitialOnly), `Mount` (FAirshipTurretMount, InitialOnly),
`bDestroyed` (OnRep_Destroyed), `uint8 HeatQ` (heat x 255), `bool bOverheated`, `int16 AimYawQ`, `int16 AimPitchQ`
(hundredths of a degree, relative to the mount).

Public API (exact; core calls these):

```cpp
AAirshipTurret();
virtual void Tick(float DeltaSeconds) override;
virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

/** Server, between SpawnActorDeferred and FinishSpawning. */
void InitTurret(AAirshipPawn* InShip, int32 InTurretIndex, const FAirshipTurretMount& InMount);

/** Server, every ship tick: what to aim at and whether the trigger is held (gunner, driver, console). */
void SetServerCommand(const FAirshipTurretCommand& Command);

/** The controlling client (its gunner, or the pilot's machine for an unmanned turret), every frame: local aim and
 * predicted tracers. Ignored on the authority. Expires after LocalCommandTimeout. */
void SetLocalCommand(const FAirshipTurretCommand& Command);

/** Server: wreck now (console, tests). */
UFUNCTION(BlueprintCallable, BlueprintAuthorityOnly, Category = "Airship|Turret") void DestroyTurret();

UFUNCTION(BlueprintPure, Category = "Airship|Turret") bool IsTurretDestroyed() const;
UFUNCTION(BlueprintPure, Category = "Airship|Turret") float GetHeat01() const;
UFUNCTION(BlueprintPure, Category = "Airship|Turret") bool IsOverheated() const;
UFUNCTION(BlueprintPure, Category = "Airship|Turret") float GetHealth() const;
UFUNCTION(BlueprintPure, Category = "Airship|Turret") float GetMaxHealth() const;
UFUNCTION(BlueprintPure, Category = "Airship|Turret") int32 GetTurretIndex() const;
UFUNCTION(BlueprintPure, Category = "Airship|Turret") AAirshipPawn* GetShip() const;
/** Shots this machine fired (server) or drew (clients: replicated + predicted tracers). Tests. */
UFUNCTION(BlueprintPure, Category = "Airship|Turret") int32 GetShotCount() const;

/** True if WorldPoint is inside the yaw / pitch limits (+ ToleranceDeg), seen from the gun pivot. */
bool IsAimInArc(const FVector& WorldPoint, float ToleranceDeg = 0.f) const;
FVector GetMuzzleLocation() const;
FVector GetBarrelDirection() const;
const FAirshipTurretMount& GetMount() const { return Mount; }

/** Damage of one bullet: Settings->TurretGunDamageMultiplier x ReadGunBaseDamage(). Cached at BeginPlay (server). */
float GetBulletDamage() const;

/** GE_GunShootDamage's additive IncomingDamage magnitudes at level 1 (Settings->GunDamageEffect,
 * FGameplayEffectModifierMagnitude::GetStaticMagnitudeIfPossible), or Settings->GunDamageFallback when it can't be read
 * statically (SetByCaller, attribute based, an execution): the same value GA_GunShoot::GetSentinelBaseDamage reads. */
static float ReadGunBaseDamage();

// IAbilitySystemInterface / IMyCombatInterface
virtual UAbilitySystemComponent* GetAbilitySystemComponent() const override;
virtual void Die() override;                                 // server: health 0 -> wreck (once)
virtual bool IsDead_Implementation() override { return bDestroyed; }
virtual int32 GetLevel_Implementation() override;            // the ship's level, else 1
virtual FVector GetCombatSocketLocation_Implementation() override; // muzzle
virtual FOnDeathDelegateSignature& GetOnDeathDelegate() override { return OnDeathDelegate; }
```

The turret uses only existing public ship API: `GetHull()`, `IsAirshipDead()`, `GetPassengers()`,
`GetAbilitySystemComponent()`, `GetAttachedActors()`, and the combat API `AAirshipCannonball::ApplyShotDamage`,
`GetSourceShip`, `IsSpent`, `IsShotDown` (D2).

BeginPlay: `AbilitySystemComponent->InitAbilityActorInfo(this, this)` (every machine); authority: MaxHealth then Health
= `TurretMaxHealth`, Armor = `TurretArmor`; cache `GetBulletDamage()`; set `Muzzle` relative location from
`MuzzleForward`, `GunMesh` from `PivotHeight` (so BP values win).

#### D6.3 Aim (every machine)

Target from the active command: server -> `ServerCommand`; a client with a fresh local command -> it; other clients ->
replicated `AimYawQ`/`AimPitchQ`. A command aim point becomes mount-relative yaw/pitch: `P = HullTM.Inverse(AimPoint) -
(Mount.Location + (0, 0, PivotHeight))`, yaw = atan2(P.Y, P.X), pitch = atan2(P.Z, |P.XY|), clamped to the mount limits.
No aim (`!bHasAim`): rest (yaw 0, pitch 0). Slew at `YawRateDeg` / `PitchRateDeg`. Apply as `BaseMesh` relative yaw and
`GunMesh` relative pitch (UE pitch + = up). Server writes the quantized result.

#### D6.4 Fire (server)

```
Trigger edge (false -> true): ShotClock = FireInterval - TurretIndex * FireInterval * 0.5   // turret 0 at once, turret 1 0.05 s later
Each tick, if command.bTrigger && !bDestroyed && Ship valid && !Ship->IsAirshipDead() && !bOverheated
           && IsAimInArc(command.AimPoint, ArcToleranceDeg):
    ShotClock += Dt; while ShotClock >= FireInterval: ShotClock -= FireInterval; FireOneShot()
else ShotClock = 0 (until the next edge)
Heat: each shot += HeatPerShot; >= 1 -> bOverheated. No shot for CoolDelay: Heat -= CoolRate * Dt (>= 0);
      bOverheated && Heat <= OverheatRecover -> false.
End of tick: shots fired this tick -> MulticastShots(Shots), ForceNetUpdate().
```

`FireOneShot()`:

1. `Start = GetMuzzleLocation()`, `Dir = VRandCone(GetBarrelDirection(), SpreadDeg)`, `End = Start + Dir * Range`.
2. Ignore list: the ship, every actor attached to it (recursive: both turrets, pilot, gunners), `Ship->GetPassengers()`.
3. `LineTraceSingleByChannel(Visibility)`; if the hit actor is an `AAirshipCannonball` whose `GetSourceShip() == Ship`,
   add it to the ignore list and re-trace (at most 4 times).
4. Ball sweep: `SweepMultiByObjectType(WorldDynamic, sphere BallSweepRadius)` from Start to the line hit (or End),
   same ignores; the nearest `AAirshipCannonball` that is not this ship's and not `IsSpent()` and nearer than the line
   hit wins (aim assist against 1 m balls).
5. Ball: `Ball->ApplyShotDamage(Settings->TurretGunDamageMultiplier, Instigator)` (gun units).
   Else line hit: an enemy `AAirshipCannonball` (blocks Visibility now) -> same; else an actor with an ASC that has
   UMyAttributeSet (`HasAttributeSetForAttribute(Health)`) and is not dead -> damage spec: made from the **ship's** ASC
   (`MakeOutgoingSpec(DamageEffectClass or UAirshipDamageEffect, ship level, Context)`), `Context.AddInstigator(
   Command.Instigator (gunner, or the ship for the driver/console), this)`, `Context.AddHitResult(Hit)`, SetByCaller
   `SetDamageByCaller` = `GetBulletDamage()`, `ShipASC->ApplyGameplayEffectSpecToTarget(Spec, TargetASC)`. Targets:
   characters, other ships (hull or mesh), other turrets, the Burrower and enemies; never this ship, its turrets, crew or
   deck riders (ignored in step 2).
6. Sentinels: queue `(Start, ShotEnd)`; one next-tick timer per frame (Mass phases, pattern of
   `GA_GunShoot.cpp:149-165`) runs `Swarm->QueryCapsule(Start, End, SentinelShotRadius, Hits)` and
   `UMechSentinelCombatLibrary::ApplySpecToHits(*Swarm, *Spec, Hits, SentinelMaxTargets)` with
   `Spec = MakeSentinelDamageSpec(World, Command.Instigator or Ship, GetBulletDamage(), nullptr)`.
7. Record `FAirshipTurretShot{ShotEnd, bImpact = blocking hit}`; `++ShotCount`; muzzle flash (below).

#### D6.5 Tracers and flash (every machine)

* `UFUNCTION(NetMulticast, Unreliable) void MulticastShots(const TArray<FAirshipTurretShot>& Shots);` on the turret (one
  per turret per frame with shots; `ForceNetUpdate` after it: unreliable multicasts wait for the next net update,
  memory note "net gotcha").
* Implementation: on a client whose local command is fresh (it drew its own) -> skip. Else for each shot: tracer from
  this machine's own `GetMuzzleLocation()` to `End` (`ShotCount += 1` on clients). Dedicated server: nothing.
* Tracer drawing: a private copy of `AMechSentinelBulletRelay::ShowBulletsLocal` (`MechSentinelBulletRelay.cpp:92-121`):
  write `NDC_GunShootHit` through the access context with `bOverrideSystemToSpawn` / `SystemToSpawn = TracerSystem`
  (never a new channel: copied systems' readers still point at the original channel), `MuzzlePos` / `HitLocation`.
* Muzzle flash: `MuzzleFXComponent->Activate(true)` (reset) once per shot batch; a timer deactivates it
  `MuzzleFlashMaxSeconds` after the last shot (D1 cap). 
* Prediction (controlling client, `!HasAuthority()`, local command fresh and `bTrigger`, `!bOverheated` (replicated),
  in arc): its own shot clock with the same phase rule; each predicted shot: local Visibility trace with the same
  ignores (no damage), tracer + flash, `++ShotCount`.

#### D6.6 Destroyed (wreck)

`Die()` (UMyAttributeSet calls it at Health 0, `MyAttributeSet.cpp:72-79`) or `DestroyTurret()`: once, server:
`bDestroyed = true`, trigger off, `ForceNetUpdate()`, `OnDeathDelegate.Broadcast(this)`, local FX. `OnRep_Destroyed`:
FX. FX: `DestroyedFXComponent->Activate()` (burns until the ship goes); `DestroyedExplosionFX` once, unless the actor
began play less than 0.5 s ago (a late joiner). The wreck stays attached; HitBox stays (it still stops balls; damage to
a dead turret does nothing). The ship's `UpdateStations` ejects its gunner (`bEject` true).

#### D6.7 Ship side (core)

* `SpawnTurrets()` (authority, end of `BeginPlay` before `OnRep_PilotCharacter`, `AirshipPawn.cpp:407`): if
  `Settings->bSpawnTurrets`: class = `Settings->TurretClass.LoadSynchronous()` or `AAirshipTurret::StaticClass()` (warn
  once: no meshes); for t < min(NumTurrets, TurretMounts.Num()): `SpawnActorDeferred<AAirshipTurret>(Class,
  FTransform(Mount.Location) * HullTM, this, nullptr, AlwaysSpawn)` -> `InitTurret(this, t, Mount)` -> `FinishSpawning` ->
  `AttachToComponent(HullCollision, KeepWorldTransform)` (the stock rules don't weld: the QueryOnly HitBox must never
  become part of the hull's simulated body) -> `SetActorRelativeTransform(FTransform(Mount.Location))` ->
  `Tags.AddUnique(UMechSentinelSwarmSubsystem::BulletTargetTag)` -> `Turrets[t] = Turret`.
* `UpdateTurretCommands()` (server, from `UpdateStations`): per turret (skip null/destroyed):
  * manned: `{StationAims[s], true, StationTrigger[s], Gunner}`;
  * else console override (D10 `TurretFire`): `{override point or muzzle + hull fwd x 10000, true, true, this}`;
  * else piloted and `Flight->GetCurrentControls().HasAimPoint()`: `{AimPoint, Turret->IsAimInArc(AimPoint, 10),
    bDriverFire, this}` where `bDriverFire = Controls.IsFireHeld()` and the aim point's bearing from the hull's
    centre is within `DriverTurretArcDeg + 10` of the bow (server re-check of the client's bit);
  * else `{zero, false, false, nullptr}` (rest).
* Pilot's machine (`GatherLocalInput`, `AirshipPawn.cpp:764-883`): `const bool bTurretArc = IsDriverTurretArc();`
  `Controls.SetButton(Airship::Button_FireHeld, bTurretArc && Button(FireAction))` in both branches (P&F and the
  others), after the aim point is computed (`:874-880`). On a client, each unmanned living turret gets
  `SetLocalCommand({LocalAimPoint, bLocalAimValid, FireHeld bit, this})`.
* `bool IsDriverTurretArc() const` (pilot's machine): `DriverTurretArcDeg > 0`, at least one turret alive and unmanned,
  and |WrapDeg(view yaw - hull yaw)| <= `DriverTurretArcDeg` (view = `GetController()->GetPlayerViewPoint` rotation).
  Applies to every scheme on purpose: the turrets exist on every ship. P&F's gun lock works 55-150 deg off the bow
  (h:934-939), so the 50 deg arc never overlaps it.
* Telemetry and HUD read `Turrets` (Appendix B).

Numbers (committed GE value 1): 4 per bullet, 2 x 10/s = 80 DPS (a 2000 HP ship in 25 s; the same as one broadside
side's average); a ball (30 units) takes 8 bullets. With the user's local GE value 1000: 4000 per bullet (one-shots a
2000 HP ship): a test value in his tree, flagged in section 5.

### D7. Model changes (Blender, headless, on the rig copy)

All in `SourceArt/Airship/scripts` (source of truth in the repo), copied to
`/mnt/new_partition/BlenderProjects/StylizedAirship/rig/scripts/` before running (`rig_all.sh` runs from there); outputs
copied back into `SourceArt/Airship`. Blender binary: `/home/talal/.local/bin/blender` (set `B` in `rig_all.sh` and
`verify_all.sh` from `${BLENDER:-/home/talal/.local/bin/blender}`). Never open or write
`StylizedAirship.blend`; `rig_all.sh` only `cp`s it to `AirshipRig_src.blend` when missing.

1. **Steering wheel to character size** (`props/model_helm.py:37-61` knobs + `rig_common.py:44-46`). Target: wheel 140
   cm across the handle tips, hub at about chest height of the 141.6 cm mech capsule. Knobs: `AXLE_H` 1.65 -> 1.00,
   `TIP_R` 1.55 -> 0.70, `RIM_RO/RIM_RI` 1.17/0.99 -> 0.54/0.44 (rim kept a little chunkier than a pure 0.45 scale so it
   reads from the 65 m camera), `RIM_HB` 0.075 -> 0.05, `SPOKE_SCALE` 1.45 -> 0.70, `HUB_FLANGE_R` 0.33 -> 0.15,
   `BOLT_RING_R` 0.25 -> 0.11, `BAND_ARC` 0.11 -> 0.06, `FERRULE` scaled with TIP_R, `WHEEL_X` -0.63 -> -0.35,
   pedestal parts (stanchions, drum, knees) scaled to the new axle height (the script derives most from AXLE_H; check the
   ones it doesn't). `rig_common.HELM_WHEEL_OFS` = (-0.35, 0, 1.00) (must equal WHEEL_X / AXLE_H), `PILOT_BEHIND_AXLE`
   1.3 -> 0.55 (capsule axis 55 cm behind the wheel plane: radius 34 + 21 cm). Bones keep names; `Helm_Wheel` and
   `PilotSeat` move (expected about (-685, 0, ~360) and (-740, 0, ~262)). Report the new PilotSeat in
   `turret_dims.json` (`pilot_seat_ue`), core sets `PilotSeatFallback` (h:539) to it.
2. **Delete the five marked deck pieces** in the rig copy's SM_Airship mesh (they belong to the Hull bone, no bone
   changes). Candidates identified from `Docs/Airship/research/sm_airship_islands.json` against the user's image 1
   (arrows top to bottom, image bow = bottom, port = image right):

   | Arrow | Piece | Islands (src) | Blender bbox (m) |
   |---|---|---|---|
   | 1 grate box near the stern fans | aft hatch + 5 slats | 18-24 (DeckProps) | x -12.1..-8.9, y +-1.5, z 2.79-3.47 |
   | 2 grate box mid-deck, wide part | forward hatch + 5 slats (the ship origin is inside it in the image) | 11-17 (DeckProps) | x -0.5..3.5, y +-1.5, z 2.41-3.09 |
   | 3 tall narrow post at the waist | BowFin (+ 2 side plates) | 0-2 (BowFin) | x 7.0..10.19, y +-0.23, z 2.36-7.86 |
   | 4 big flat hatch, narrow deck | raised slab | 237 (Gantry) | x 12.75..17.25, y +-1.3, z 6.55-7.45 |
   | 5 small grate near the bow tip | three stepped boxes | 234-236 (Gantry) | x 22.49..23.47, y +-0.8, z 6.54-7.34 |

   Confirm before deleting: render a top view of the rig copy with these islands highlighted (red) in the same framing
   as image 1 (`/home/talal/.claude/uploads/d2a7b3c7-4c60-4fb3-a1d8-2c94df94e717/b28d7773-image.png`) and compare;
   adjust the list if a highlighted piece isn't what an arrow points at (and list any extra islands found in the same
   boxes). Implementation in `rig_build.py`: after the source checks at `:41-55` (36908 verts, 1150 islands, centroid
   match), delete the listed islands' vertices from the rig copy's mesh, then skin as before. The hash assert at
   `:284` becomes: hash of the kept vertices (computed before the deletion over the kept index set, with the same
   function) == hash after; record `removed_islands`, `removed_verts`, `removed_tris` in the build JSON (`:366`).
   `rig_export.py:30` (31 mesh nodes) is unchanged (islands are inside the SM_Airship node). Update every check that
   counts vertices/triangles (verify_fbx.py, verify_import.py, rig_readme.py totals 55,948 / 104,730, Hull 26,594) to
   the new totals, derived, not hand-typed. SM_Airship in Unreal (`/Game/Assets/MyShip/SM_Airship`, the hidden physics
   body with the UCX) is NOT changed: its collision stays as it is.
3. **Cannon bore** (`props/model_cannon.py:48-93`): `BORE_R` 0.13 -> 0.22, muzzle face entry `(2.600, 0.160)` ->
   `(2.600, 0.250)`, countersink `(2.585, BORE_R)` stays relative; lip outer radius 0.28 unchanged (6 cm wall). The
   1 m ball still spawns 80 cm ahead of the muzzle (D2), the larger dark bore just reads right.
4. **Turret meshes** (new `props/model_turret.py`, style of `model_cannon.py`: bmesh, metres, smooth + sharp-by-angle,
   one UV map, part_kind face attribute, placeholder colours): output `rig/props/Turret.blend`, objects:
   * `Turret_Base` (yaw part): origin = yaw axis on the deck (z 0 = deck). A round iron pedestal (radius 0.40-0.45,
     height ~0.9 with a bolted foot ring), a turning ring, a yoke with two cheeks holding the trunnion at
     z = `PIVOT_H` 1.50, a curved armour shield in front of the gunner, an ammo box on one side. Fits inside
     (0.9 x 0.9 m footprint), clear of a gunner standing 1.0 m behind the axis.
   * `Turret_Gun` (pitch part): origin = trunnion axis centre, fires +X. Twin water-jacketed barrels (comic chunky:
     jacket radius 0.07, barrel radius 0.03, length 1.5-1.8 m), receiver block behind the trunnion (<= 0.45 m behind),
     spade grips at the rear, a ring sight. Muzzle at gun-local (`MUZZLE_X` about 1.80, 0, 0) between the barrels.
   * UVs on the props atlas: `props/uv_layouts.py` reserves an overlap-free region for both pieces;
     `props/bake_props_comic.py` includes them in its assemble / atlas / bake stages (the atlas repacks: helm, cannons and
     turret all move in UV; `T_AirshipProps_ComicLines/Mask` are rewritten).
   * New `export_turret.py`: two static-mesh FBX files `SourceArt/Airship/SM_AirshipTurret_Base.fbx` and
     `SM_AirshipTurret_Gun.fbx`, same axis/unit conventions as `rig_export.py` (cm, X forward, Z up, no armature, smoothing
     by face, normals per corner, no tangents), material slot `M_AirshipProps`, pivot at the object origin. No UCX (the
     C++ HitBox is the collision).
   * `SourceArt/Airship/turret_dims.json`: `pivot_height_cm`, `muzzle_forward_cm`, `base_radius_cm`, `gun_length_cm`,
     `deck_top_cm_at_mounts` (measured on the rig copy at (21.0, +-2.45) Blender = UE (2100, -/+245)), `rail_top_cm`,
     `rail_inner_y_cm`, `pilot_seat_ue`, `helm_wheel_ue`, `removed_islands`.
5. Re-run `rig_all.sh` and `verify_all.sh`; both must pass with **118 bones**, the same bone names, 31 mesh nodes
   (`rig_export.py:30`), `as_12`'s 118-bone check (`as_12_control_rig.py:592`) unaffected. Copy `export/SK_Airship.fbx`,
   `SK_Airship_testanim.fbx`, `textures/T_AirshipProps_Comic{Lines,Mask}.png` and the two turret FBX into
   `SourceArt/Airship`. Regenerate `README_rig.md` (`rig_readme.py`), add a "Round 2" section: what changed, the removed
   islands, the new wheel numbers, the turret files.
6. Renders for the lead (`rig/renders/round2/`): top view before/after (same framing as image 1), helm close-up with a
   141.6 cm capsule stand-in at the PilotSeat, turret base+gun at the port mount with a capsule at the seat, cannon muzzle
   close-up with a 1 m sphere 80 cm ahead.
7. `rig/props/AirshipProps.blend` and `Turret.blend` stay in rig/ (not in the repo), as today.

Searchlights and other props stay as they are (lead decision).

### D8. Board from under the hull

Port from the parked local branch `airship-anchor-wip` (1f3d2b7, `git show airship-anchor-wip`), boarding part only:

* Settings (turret owner): `UPROPERTY(Config, EditAnywhere, Category = "Boarding", meta = (ClampMin = "0.0")) float
  BoardBelowDistance = 1000.f;` with the branch's comment (after `BoardHullDistance`, `AirshipSettings.h:90-92`).
* Core: `IsWithinBoardRange(const FVector& Location, float SeatDistance, float HullDistance, float BelowDistance = 0.f)
  const` (h:109, cpp:1056) with the branch's up-trace block (`HullCollision->LineTraceComponent` from Location to
  Location + (0, 0, BelowDistance)). Both callers in the pilot component (`AirshipPilotComponent.cpp:213` and `:269`, and
  the new `TryUseNearest`) pass `Settings->BoardBelowDistance`.
* The anchor part of that branch is not merged; its hold law and heading loop are reused inside D9's module.

### D9. Drift after dismount, hold when parked (flight module)

#### D9.1 States (server only)

`EAirshipUnpilotedMode` (AirshipTypes.h): `None` (piloted, debug input active, flight off/dead), `Coast` (unpiloted and
too fast to hold, no drift requested: today's behaviour, station keeping as before), `Drift`, `Hold`. PR B adds `Lane`.

Transitions (evaluated every server frame in `UpdateUnpilotedMode`, before `SelectControls` in `UpdateFlight`, i.e.
between `AirshipFlightComponent.cpp:832` and `:834`):

```
if !bFlightEnabled or Ship->HasPilot() or bDebugInputActive:   Mode = None; DriftRequest cleared if debug
else if Mode == None:
    if DriftRequest pending and DriftSpeed > 0 and ExitForwardSpeed > DriftMinExitSpeed:  -> Drift (consume request)
    else if bHoldWhenUnpiloted and |V_xy| < HoldEngageSpeed:                              -> Hold here
    else                                                                                  -> Coast
Coast: |V_xy| < HoldEngageSpeed and bHoldWhenUnpiloted -> Hold here
Drift: blocked (bow contact or look-ahead sweep), or DriftMaxDistance > 0 travelled -> Hold here
Hold:  pushed beyond HoldResetDistance or turned beyond HoldResetYawDeg -> Hold re-dropped here when slow (Coast until then)
```

"Hold here" = `HoldPoint = COM.xy`, `HeadingYaw = hull yaw`. A ship that was never piloted (placed in the map, spawned)
holds once slow: the parked creep (about 5 cm/s and 0.15 deg/s, round2_map drift) goes away. Gunners without a pilot
don't count as a pilot (drift and hold continue).

`NotifyPilotLeft(const FVector& ExitVelocity)` (called by core at the very end of `UnboardPilot`, after `PC->Possess`,
`AirshipPawn.cpp:1238-1240`, so the `UnPossessed -> ResetInput` before it can't clear the request): records
`DriftRequest = true`, `ExitForwardSpeed = dot(ExitVelocity, hull forward)`, `HeadingYaw = hull yaw`,
`DriftStart = COM`. `ResetInput` (`:395-405`) does NOT touch the unpiloted state; `PossessedBy` (board) makes the next
evaluation return None.

#### D9.2 Target (the clean module PR B replaces)

```cpp
/** Server: what an unpiloted ship does this frame. PR B's lane cruising fills the same target (a moving hold point with
 * its own velocity), so the force and heading hooks in ApplyForces don't change. */
struct FAirshipUnpilotedTarget
{
	EAirshipUnpilotedMode Mode = EAirshipUnpilotedMode::None;
	float ForwardSpeed = 0.f;                         // Drift: target speed along HeadingYaw (cm/s)
	float HeadingYaw = 0.f;                           // Drift / Hold: world yaw to hold (deg)
	FVector2D HoldPoint = FVector2D::ZeroVector;      // Hold: COM target (world XY, cm)
	FVector2D HoldVelocity = FVector2D::ZeroVector;   // Hold: target velocity (cm/s), 0 when parked
};
```

Drift target speed = `min(ExitForwardSpeed, DriftSpeed)` (a slow exit never speeds up).

#### D9.3 Hooks in `UAirshipFlightComponent` (core, `AirshipFlightComponent.h/.cpp`)

* `UpdateFlight` (`:814-918`): authority, after `ForwardSpeed` (`:832`): `UpdateUnpilotedMode(Body, Dt)`. In the
  `!bFlightEnabled` branch (`:909-916`): `UnpilotedTarget = {}` and the request cleared.
* `SelectControls` (`:419-472`), the no-pilot return at `:467-468`: return a neutral input with
  `Airship::Button_Drift` set when `UnpilotedTarget.Mode == Drift` (it rides `RepInput` to every machine, so every
  machine shapes the same cosmetics).
* `ShapeGalleon` (`:601-649`): after the order's ThrottleTarget (`:626-636`), `if
  (Controls.HasButton(Airship::Button_Drift)) { ThrottleTarget = 0.f; }` (no STOP reverse while drifting).
* `ApplyForces`, heading (after the Sky Racer yaw block, before "The steady gun deck" at `:1239`):

```cpp
// Unpiloted drift / hold: hold the heading (no pilot, so the steer is neutral)
if (UnpilotedTarget.Mode == EAirshipUnpilotedMode::Drift || UnpilotedTarget.Mode == EAirshipUnpilotedMode::Hold)
{
	const UAirshipSettings* S = UAirshipSettings::Get();
	const float ErrDeg = WrapDeg(UnpilotedTarget.HeadingYaw - static_cast<float>(Current.Yaw));
	YawRateCmd = FMath::DegreesToRadians(FMath::Clamp(S->HoldYawGain * ErrDeg, -S->HoldYawRateMax, S->HoldYawRateMax));
}
```

* `ApplyForces`, station keeping gate (`:1598`): add `&& UnpilotedTarget.Mode != Drift && != Hold` (it would brake the
  drift: 2.5 m/s is inside its full-strength band; the hold law replaces it at rest).
* `ApplyForces`, before `ACom.Z += AVert;` (`:1643`):

```cpp
if (UnpilotedTarget.Mode == EAirshipUnpilotedMode::Drift)
{
	// Along the hull: track the drift speed, drag fed forward at that speed (ADragFwd above takes the real drag off), capped
	const float T = UnpilotedTarget.ForwardSpeed;
	const float ADrift = FMath::Clamp(S->DriftGain * (T - Vf) + (DragC1 * T + DragC2 * T * FMath::Abs(T)), -S->DriftDecelMax, S->DriftAccelMax);
	ACom += Fwd * ADrift;
}
else if (UnpilotedTarget.Mode == EAirshipUnpilotedMode::Hold)
{
	// Capped spring + damper on the centre of mass back to the hold point (the anchor branch's law)
	const FVector COM = Body->GetCenterOfMass();
	const FVector2D Err = UnpilotedTarget.HoldPoint - FVector2D(COM.X, COM.Y);
	const FVector2D VErr = UnpilotedTarget.HoldVelocity - FVector2D(V.X, V.Y);
	const FVector2D A = (Err * S->HoldKp + VErr * S->HoldKd).GetClampedToMaxSize(S->HoldAccelMax);
	ACom += FVector(A.X, A.Y, 0.0);
}
```

  COM accelerations, like every other ACom term (`AddForce(..., true)`):
  the fans stay idle on every machine, which reads as coasting.
* Obstacles:
  * `void NotifyHullContact(const AActor* Other, const FHitResult& Hit)` (core calls it from `OnHullHit` on the server,
    before the `ImpactMinSpeed` return at `AirshipPawn.cpp:2154`): while drifting, ignore characters, pawns, cannonballs,
    actors attached to the ship; else if the contact point is ahead of the COM by more than 30 % of the hull's local
    half length and `|dot(Hit.ImpactNormal, DriftDir)| >= DriftBowHitMinDot` (0.5; absolute value: the normal's sign in
    rigid-body hit events is not relied on) -> blocked.
  * Look-ahead sweep every `DriftSweepInterval` (0.25 s): a box from the hull's local bounds
    (`Body->CalcBounds(FTransform::Identity)`, cached at BeginPlay) shrunk by `DriftSweepInset` (100 cm) on every side
    and with its bottom lifted by `DriftSweepFloorLift` (200 cm, so level flight over ground doesn't count; the
    MinClearance floor lifts the ship over rising ground), rotated with the hull, swept along the drift direction for
    `max(DriftLookAheadMin 600, ForwardSpeed x DriftLookAheadTime 3 s)` cm (review fix, section 6.5: the ship's real
    forward speed, plus its stopping distance at `HoldAccelMax`), `SweepMultiByObjectType(WorldStatic,
    WorldDynamic, PhysicsBody)`, ignoring the ship and its attached actors (recursive), pawns/characters and
    cannonballs. The first remaining hit (or a start overlap) -> blocked.
* Public: `EAirshipUnpilotedMode GetUnpilotedMode() const`, `const FAirshipUnpilotedTarget& GetUnpilotedTarget() const`,
  `void NotifyPilotLeft(const FVector& ExitVelocity)`, `void NotifyHullContact(const AActor*, const FHitResult&)`.
* `FillTelemetry` (`:1797`): Appendix B unpiloted fields.

All D9 knobs are in `UAirshipSettings` (Appendix A), not scheme-owned. They apply to every scheme on purpose (the user's
ask). Classic, Galleon, Sky Racer and Point & Fly all drift after a moving exit and hold when parked.

#### D9.4 Edge cases

* Exit while reversing or sideways (forward speed <= 100 cm/s): no drift; Coast until slow, then Hold.
* Boarding while drifting: the pilot takes over at once (None); Galleon's STOP order applies as today
  (`ResetSchemePilotState`).
* Debug input (`Aura.Airship.Input`, harness): None while active; on clear: Hold if slow, else Coast then Hold (no
  spring from cruise speed: `HoldEngageSpeed` 300 cm/s, as the anchor branch's engage speed).
* Death: flight off -> None.
* Ship pushed far while holding (another ship rams it): re-drops after `HoldResetDistance` 20 m / `HoldResetYawDeg` 60.
* Over the void: the drift continues (altitude hold); `DriftMaxDistance` (0 = no limit) can end it; PR B's lanes replace
  it.
* Network: no new replicated state for the motion (the hull replicates; only the server applies forces); the drift bit
  rides RepInput for the cosmetics.

### D10. Console and test hooks

Core adds to `AirshipSubsystem.cpp` (non-shipping block, pattern `:563-890`, server-only ones use `CheckServer`):

| Command | Where | What |
|---|---|---|
| `Aura.Airship.Mount <PlayerIndex> <Station 0-5>` | server | `TryMount(nearest living ship with that station free, Station, bIgnoreRange true)` |
| `Aura.Airship.Dismount <PlayerIndex>` | server | `TryDismount()` |
| `Aura.Airship.TurretFire <0/1> [X Y Z]` | server | every ship's unmanned turrets fire (1) at the point (default: 100 m ahead of the bow at muzzle height) or stop (0) |
| `Aura.Airship.TurretDamage <Turret 0/1> <Amount>` | server | damage through the turret's ASC (UAirshipDamageEffect) on every ship |
| `Aura.Airship.StationFire <PlayerIndex> [X Y Z] [Seconds=1]` | server | that player's station: a cannon fires once (`FireStation`), a turret holds its trigger for Seconds, at the point (default: its current StationAim) |
| `Aura.Airship.Set Settings.<Name> <Value>` | any | `ResolveTarget` (`AirshipSubsystem.cpp:522-540`) maps prefix `Settings` to `GetMutableDefault<UAirshipSettings>()` |
| `Aura.Airship.Telemetry` | any | adds a third line: unpiloted mode, drift target, hold offset, station mask + gunner names, turret heat/health/destroyed/shots, pilot health |
| `Aura.MechSentinel.TestBullet ...` | server | combat owner, D3 |

`UAirshipSubsystem` additions: `bool FindGunnerStation(const ACharacter* Character, AAirshipPawn*& OutShip, int32&
OutStation) const` (every machine, from the replicated StationGunners).

Telemetry fields: Appendix B (types owned by turret, filled by core and flight).

---

## 2. File ownership and the cross-owner API contract

No two owners touch the same file. The lead owns this spec, commits, editor runs and `Config/*` (no ini change is
needed: new settings have C++ defaults; `/Game/Assets/MyShip/Drivable` is already always cooked, `DefaultGame.ini:145`).

| Owner | Files (only these) |
|---|---|
| **combat** | `Source/Aura/Public/Airship/AirshipCannonball.h`, `Source/Aura/Private/Airship/AirshipCannonball.cpp`, `Source/Aura/Public/MechSwarm/Core/MechSentinelSwarmSubsystem.h`, `Source/Aura/Private/MechSwarm/Core/MechSentinelSwarmSubsystem.cpp`, `Source/Aura/Public/AbilitySystem/Abilities/GA_GunShoot.h`, `Source/Aura/Private/AbilitySystem/Abilities/GA_GunShoot.cpp` |
| **turret** | new `Source/Aura/Public/Airship/AirshipTurret.h`, new `Source/Aura/Private/Airship/AirshipTurret.cpp`, `Source/Aura/Public/Airship/AirshipSettings.h`, `Source/Aura/Public/Airship/AirshipTypes.h` |
| **blender** | `SourceArt/Airship/**` (scripts, FBX, textures, README_rig.md, turret_dims.json); writes outputs under `/mnt/new_partition/BlenderProjects/StylizedAirship/rig/` (the thread's own folder) |
| **assets** | new `Docs/Airship/scripts/ue/as_51_*.py` .. `as_59*.py`, and the edit of `Docs/Airship/scripts/ue/as_06_muzzle.py` |
| **core** (after the four above) | `Source/Aura/Public|Private/Airship/AirshipPawn.*`, `AirshipPilotComponent.*`, `AirshipFlightComponent.*`, `AirshipHUDWidget.*`, `AirshipSubsystem.*`; `Docs/Airship/CPP_NOTES.md`, `Docs/Airship/HOW_TO_FLY.md` |

`AirshipAnimInstance.*` and `AirshipDamageEffect.*` need no change (the anim instance already reads per-cannon aim and
fire counts, `AirshipAnimInstance.cpp:133-135`). No `Aura.Build.cs` change (Niagara, GameplayAbilities, EnhancedInput
are already dependencies).

Compile order: combat and turret are written in parallel against the signatures below; the turret uses the combat API
(D2) and core uses both, so the first build runs after core.

### 2.1 Turret owner: `AirshipTypes.h` (exact)

```cpp
namespace Airship
{
	// existing ...
	constexpr int32 NumStations = 6;
	constexpr int32 NumTurrets = 2;
	constexpr int32 FirstTurretStation = 4;
	inline bool IsCannonStation(int32 Station) { return Station >= 0 && Station < NumCannons; }
	inline bool IsTurretStation(int32 Station) { return Station >= FirstTurretStation && Station < NumStations; }
	inline int32 StationToTurret(int32 Station) { return Station - FirstTurretStation; }
	inline int32 TurretToStation(int32 Turret) { return Turret + FirstTurretStation; }

	/** The pilot holds Fire with the camera in the bow arc: the unmanned turrets fire at AimPoint (D6). */
	constexpr uint8 Button_FireHeld = 1 << 5;

	/** Server -> every machine (in the neutral input of an unpiloted ship): the ship is drifting (D9); Galleon's STOP
	 * order doesn't reverse the engines. */
	constexpr uint8 Button_Drift = 1 << 6;
}

UENUM(BlueprintType)
enum class EAirshipStation : uint8
{
	CannonL1 = 0, CannonL2 = 1, CannonR1 = 2, CannonR2 = 3, TurretL = 4, TurretR = 5,
	None = 255 UMETA(Hidden)
};

UENUM(BlueprintType)
enum class EAirshipUnpilotedMode : uint8 { None = 0, Coast = 1, Drift = 2, Hold = 3 };

/** A turret mount in hull space (cm), its yaw limits (deg about hull +Z, 0 = bow, + = toward starboard) and pitch limits. */
USTRUCT(BlueprintType)
struct AURA_API FAirshipTurretMount
{
	GENERATED_BODY()
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship") FVector Location = FVector::ZeroVector;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship") float YawMinDeg = -30.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship") float YawMaxDeg = 30.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship") float PitchMinDeg = -20.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship") float PitchMaxDeg = 40.f;
};

/** One turret bullet as the tracers see it (D6.5). */
USTRUCT()
struct AURA_API FAirshipTurretShot
{
	GENERATED_BODY()
	UPROPERTY() FVector_NetQuantize End = FVector::ZeroVector;
	UPROPERTY() bool bImpact = false;
};

/** What a turret aims at and whether it fires (not replicated). */
struct FAirshipTurretCommand
{
	FVector AimPoint = FVector::ZeroVector;
	bool bHasAim = false;
	bool bTrigger = false;
	TWeakObjectPtr<AActor> Instigator;
};
```

`FAirshipPilotInput`: add `bool IsFireHeld() const { return HasButton(Airship::Button_FireHeld); }`. Telemetry fields:
Appendix B.

### 2.2 Turret owner: `AirshipSettings.h`

All of Appendix A, with the constructor filling `TurretClass` (`/Game/Assets/MyShip/Drivable/Turret/BP_AirshipTurret.
BP_AirshipTurret_C`), `GunDamageEffect` (`/Game/Level/GAS/GameplayEffects/GE_GunShootDamage.GE_GunShootDamage_C`) and
`TurretMounts` (D6.1 table). Forward-declare `AAirshipTurret`, `UGameplayEffect`; include `Airship/AirshipTypes.h`.

### 2.3 Turret owner: `AirshipTurret.h/.cpp`

D6.2 exactly. Private: `OnRep_Destroyed`, `MulticastShots`, `FireOneShot`, `DrawTracer`, `UpdateAim`, heat state,
shot clocks, `TArray<TPair<FVector, FVector>> PendingSentinelSegments` + its next-tick timer, `FAirshipTurretCommand
ServerCommand, LocalCommand`, `double LocalCommandTime`, `FOnDeathDelegateSignature OnDeathDelegate`.

### 2.4 Combat owner API

D2 cannonball API, D2 GA_GunShoot branch + `CannonballShotUnits`, D3 `UMechSentinelSwarmSubsystem::BulletTargetTag` +
the TickBullets block + `Aura.MechSentinel.TestBullet`.

### 2.5 What core expects (summary)

| From | Symbol |
|---|---|
| combat | `AAirshipCannonball::GetRadius()`, `GetGravityScale()` (on the CDO), `IsShotDown()`; `UMechSentinelSwarmSubsystem::BulletTargetTag` |
| turret | `AAirshipTurret` (D6.2 API), `FAirshipTurretMount`, `FAirshipTurretCommand`, `EAirshipStation`, `EAirshipUnpilotedMode`, `Airship::NumStations/NumTurrets/...`, `Button_FireHeld`, `Button_Drift`, all Appendix A settings, Appendix B fields |

---

## 3. Editor steps (assets owner writes them; the lead runs them in the editor stage)

All in `Docs/Airship/scripts/ue/`, run through `Docs/Airship/scripts/harness/inbox.sh <id> <script> <timeout>` with the
clone's editor (no PIE running; every script refuses to change assets while PIE runs, as `as_21:63-66`). Each script:
re-runnable, saves only its own assets by explicit path, prints `PASS/FAIL/WARN/INFO` lines and writes
`Saved/Airship/as_5x_*.json`. Existing scripts are re-run as they are (not edited) unless stated.

| Order | Script | What |
|---|---|---|
| 1 | `as_51_muzzle_once.py` | D1 asset fix on NS_AirshipMuzzle (probe, every emitter Loop Once 0.2 s, Blast_Puffs lifetime 0.5-0.85 + alpha fade), compile check, save. Also defines the shared function the edited `as_06_muzzle.py` calls. |
| 2 | `as_52_cannonball_bp.py` | BP_AirshipCannonball CDO: BallMesh scale (1, 1, 1), ImpactFXScale 3.0, Radius 50, GravityScale 0.6, SplashRadius 600, SentinelHitRadius 100, MaxLifeSeconds 10, BallMaxHealth 30; compile, read back, save. Header: run after any as_03 run. |
| 3 | (existing) `as_02_textures_material.py` | re-import `T_AirshipProps_ComicLines/Mask` from SourceArt (the atlas repacked in D7) |
| 4 | `as_56_reimport_airship.py` | wrapper: `AS10_EXISTING = 'reimport'` then exec `as_10_import.py` (SK_Airship over the existing asset, skeleton kept, bones checked against the new `bones_ue.csv`). Then checks: 118 bones, `Helm_Wheel`/`PilotSeat` rest positions = `turret_dims.json`, SK still points at PA_Airship, prints PilotSeat for `PilotSeatFallback`. Does NOT rebuild PA_Airship. |
| 5 | (existing, headless Blender) `as_09_part_bounds_blender.py` | new `part_bounds.json` (helm bounds changed) |
| 6 | (existing) `as_12_reuse.py`, then `as_13_cr_eval.py` | CR_Airship rebuilt in place (Helm wreck body from the new bounds, wheel position); eval must pass as before (144 checks) |
| 7 | `as_53_turret_import.py` | import `SourceArt/Airship/SM_AirshipTurret_Base.fbx` / `_Gun.fbx` -> `/Game/Assets/MyShip/Drivable/Turret/SM_AirshipTurret_Base`, `SM_AirshipTurret_Gun` (static mesh, no collision generated, Nanite off, combine meshes, material slot -> `/Game/Assets/MyShip/Drivable/Materials/M_AirshipProps`, normals imported, pivot kept); check bounds against `turret_dims.json` (+-2 cm) |
| 8 | `as_54_turret_fx.py` | three copies in `/Game/Assets/MyShip/Drivable/FX`: `NS_AirshipTurretTracer` (dup of `/Game/Assets/Effects/AppreiticeFx/GunShootHit/PS_06_Flipbook_Sprites_my`; probe every module input for the fixed 7500 cm/s tracer speed and set it to 30000; print what was found; if none is found, WARN and leave it); `NS_AirshipTurretMuzzle` (dup of `/Game/NiagaraExamples/FX_Weapons/MuzzleFlashes/NS_MuzzleFlash`, remove `Bullet_Shell_Eject`, `User.Use Bullet Shell` 0, `User.Global Scale` 1.5, every emitter Loop Once 0.2 s, smoke lifetimes <= 0.5 s); `NS_AirshipTurretFire` (dup of `/Game/Assets/Effects/Fire/NS_Fire`, unchanged). Compile state checked, saved. |
| 9 | `as_55_turret_bp.py` | `/Game/Assets/MyShip/Drivable/Turret/BP_AirshipTurret` (parent `/Script/Aura.AirshipTurret`, create or reuse, never delete): BaseMesh/GunMesh meshes, `PivotHeight` / `MuzzleForward` from `turret_dims.json`, MuzzleFXComponent system NS_AirshipTurretMuzzle, DestroyedFXComponent NS_AirshipTurretFire (relative scale 0.3), TracerSystem NS_AirshipTurretTracer, TracerDataChannel `/Game/Assets/Effects/AppreiticeFx/GunShootHit/NDC_GunShootHit`, DestroyedExplosionFX NS_FireExplosion; HitBox extent from the dims; compile, save. |
| 10 | `as_57_pawn_defaults.py` | BP_AirshipPawn: verify the CDO doesn't override CannonballSpeed / CannonSpawnForwardOffset / PilotSeatFallback (reset to the class default if it does, and report); report the project setting TurretClass resolves to BP_AirshipTurret_C. Saves only if something changed. |
| 11 | `as_58_verify_round2.py` | read-only: every asset above loads, key properties as specified, NS compile states OK, IMC_Airship unchanged (no new input assets), PA_Airship untouched (file size/hash vs the clone's committed one). |
| 12 | `as_59_pie_round2.py` (+ `as_59s_status.py`, `as_59x_stop.py`) | PIE harness, section 4 |

Input: no new input actions or contexts (gunners reuse IMC_Airship / IA_Airship*; D5.3).

Must not be regenerated / overwritten: **PA_Airship** (not rebuilt in PR A: D3 no longer needs it, and the user's own
tree has an uncommitted, empty PA_Airship; a committed PA change would collide with his local file when he pulls). The
stale helm boxes in the committed PA are larger than the new wheel: only aim traces notice (they hit the ship), noted in
section 5. ABP_Airship: unchanged. SM_Airship (static, UCX): unchanged.

Order matters: 3-6 need the Blender outputs (D7); 7 and 9 need the turret FBX and dims; 9 needs the built C++ (the
`AirshipTurret` class); 4 must not run while CR_Airship is open in an editor tab (the delete-while-in-use crash in the
memory notes; `as_12_reuse` rebuilds in place).

---

## 4. PIE test plan

Harness `as_59_pie_round2.py` (assets owner), built like `as_45_pie_mp.py` (frame-driven state machine, both worlds
driven from editor Python, fixed 30 fps, results `Saved/Airship/round2/r2_result.json` + `r2_report.txt`, captures
`Saved/Airship/captures/round2/`). Map `L_AirshipTest`. Modes: standalone (`set_play_mode.sh standalone`) and Play As
Listen Server with 1 client (`set_play_mode.sh listen 2`). Scheme Point & Fly unless stated; the Classic regression runs
as_43 / as_45 as before. Wind off for position checks (as as_43's `AS43_WIND_OFF`). Sentinel bullets come from
`Aura.MechSentinel.TestBullet` (deterministic). Damage dummies: a second ship (`Aura.Airship.Spawn`, unpiloted, it
holds) and the other player's character.

Each check prints PASS/FAIL with the measured values. "S" = standalone, "L" = listen (server + client copies both
checked where noted).

| ID | Mode | Decision | Check | Pass |
|---|---|---|---|---|
| T1.1 | S | D1 | Pilot fires a port broadside; count NiagaraComponents with asset NS_AirshipMuzzle under the ship's Mesh (`as_45_pie_mp.py:548` `muzzle_comps`) at +0.3 s and +1.5 s | >= 2 at +0.3 s, **0** at +1.5 s |
| T1.2 | S | D1 | Same with `Aura.Airship.Set Settings.MuzzleFXMaxSeconds 0` (asset fix alone) | 0 at +1.2 s |
| T1.3 | S | D1 | Captures at +0.3 s and +1.2 s of the muzzle | puffs visible at 0.3, none at 1.2 |
| T2.1 | S | D2 | A fired ball: sphere radius, BallMesh world scale, projectile gravity scale, launch speed relative to the muzzle velocity | 50 cm, 1.0, 0.6, 7000 +-1 % |
| T2.2 | S | D2 | Ship parked, aim at a point 150 m off the port beam at muzzle height (harness sets the camera); impact point vs aim point; apex of the ball path above the muzzle-target line | impact within 3 m; apex >= 2 m |
| T2.3 | S | D2 | Ship moving 30 m/s, same aim at 120 m | impact within 6 m (lead correction) |
| T2.4 | S | D2 | Aim 300 m away level | `IsAimInCannonArc` false, elevation at 8.5, ball lands short |
| T2.5 | S | D2 | Splash: dummy ship's hull 550 cm from a ball impact on a wall | dummy loses 60 x lerp(1, 0.3, d/600) +-15 % (d = centre distance) |
| T2.6 | S | D2 | `SpawnTestCannonball` hovering (GravityScaleOverride 0, velocity 200 cm/s) 15 m in front of the host character; host fires GA_GunShoot at it (as as_45 'gun' phase) | ball health -1 per hit (server); after 30 hits bShotDown, no damage to a dummy 1 m away |
| T2.7 | L | D2 | Same ball shot down by a turret (`TurretFire` at it) | server `bShotDown` within 1 s (8 bullets); client copy hidden and still within 0.5 s of the server |
| T2.8 | S | D2 | Own crew: a deck rider and a gunner (L1) on ship 1; ship 1 fires L2 point-blank at a wall 8 m off the beam (splash reaches the deck) | rider, gunner, pilot and ship health unchanged |
| T2.9 | S | D2 | Pilot aim trace with a ball crossing the camera ray (harness spawns a test ball on the ray) | `GetLocalAimPoint` stays on the wall (< 50 cm change) |
| T3.1 | S | D3 | `TestBullet` from 25 m beside ship 1 at its hull centre, ship unpiloted, Mesh collision turned off by the harness (no PA bodies involved) | ship health -3 (AttackDamage of the test bullet) |
| T3.2 | S | D3 | `TestBullet` from 25 m outboard at turret 0's HitBox, the hull's Visibility left on (a real line: it meets the hull's forward deck convex first) | turret health -3, ship unchanged; the report names the first Visibility hit (the hull) |
| T3.3 | S | D3 | `TestBullet` at the on-foot host character | character -3 via the Pawn sweep, as before |
| T3.4 | S | D3 | `TestBullet` at an untagged GAS actor (an enemy character if the map has one, else skip) | no damage (unchanged behaviour) |
| T3.5 | S | D3 | Swarm live (if the demo spawner is in the map): pilot hovers 30 s | ship health decreases; log shows tagged hits |
| T4.1 | L | D4 | Host pilots, client mans L1; `Aura.Airship.Damage 100` | pilot -25, gunner -25 (+-0.5), next frame |
| T4.2 | L | D4 | Pilot health set to 10 (harness, server ASC base); `Aura.Airship.Damage 100` | pilot ejected (PC pawn = character), then IsDead; ship alive without pilot |
| T4.3 | L | D4 | Same for the gunner at 10 | gunner dismounted, then dead, station free |
| T4.4 | L | D4 | Pilot at 100, damage 100 (-25), F exit | pilot health 75 after exit (not refilled, not reset) |
| T4.5 | L | D4 | Ship 2 fires at ship 1's L1 station area (impact within 3 m of the gunner) | gunner takes splash + crew share; logged |
| T5.1 | L | D5 | Client teleported onto the lid above L1's seat (2 m horizontal), 9 m from the helm seat; F | server `StationGunners[0]` = client char within 0.5 s; client attached at the seat, CMC tick off, IMC_Airship added (client subsystem) |
| T5.2 | L | D5 | Client at 4.5 m horizontal from every station but on the deck | F boards the helm (nearest valid = helm) or is refused if the helm is taken |
| T5.3 | L | D5 | Client (L1) control rotation toward a point 100 m off the port beam | server StationAims[0] within 2 m in 0.5 s; cannon 0 yaw/elev on server and client within 1 deg |
| T5.4 | L | D5 | Client LMB (injected into its Enhanced Input, as as_45) | one ball from L1; a second press 0.5 s later: no ball; client recoil count +1 exactly once |
| T5.5 | L | D5 | Host pilot fires the port broadside while L1 is manned | only cannon 1 fires (fire counts [0] unchanged, [1] +1) |
| T5.6 | L | D5 | `Aura.Airship.Mount 1 4` (client on turret L); client holds LMB 1.0 s at a target 60 m ahead | server shots 9-11; client tracer writes 9-11 (predicted); host draws 9-11 from the multicast; heat ~0.33 |
| T5.7 | L | D5 | Hold 3.5 s | overheat at about 3 s; no shots until heat <= 0.35 (~1.8 s after release) |
| T5.8 | L | D5 | Client F while mounted | detached on the lid, CMC on, falling then walking; IMC removed; injected W moves it >= 1 m |
| T5.9 | S | D5 | No pilot: player mans R1 and fires | works; ship keeps its hold/drift state |
| T5.10 | L | D5 | `Aura.Airship.Board 1` while the client is mounted | refused |
| T5.11 | L | D5 | `Aura.Airship.Kill` with a gunner | gunner ejected alive (detached, launched) next tick |
| T5.12 | L | D5 | Host mans R1 (`Aura.Airship.Mount 0 2`) while the client pilots; host fires | ball + client sees R1 recoil once; client's starboard broadside fires only R2 |
| T5.13 | L | D5 | Client mounts while it walks (moves in flight), then the ship is flown at 30 m/s for 10 s with `Net PktLag=100` on both worlds (`p.NetShowCorrections 1`) | no correction applied to the gunner on the client (the server logs "set to ignore error checks"); the client's copy stays within 5 cm of the seat (hull-relative) on the client, and `back on the seat` (Verbose) is rare |
| T5.15 | S | D5 | A gunner killed at R1 (respawned player, `Aura.Airship.Mount 0 2`, then a GE for its health) | its ragdoll mesh ignores PhysicsBody; hull speed change < 0.5 m/s and spin change < 2 deg/s in 2.5 s; body not thrown up (< 1 m); station free |
| T5.14 | L | D5 | Gunner's collision on the client and server while mounted | actor collision on, capsule QueryOnly, both machines |
| T6.1 | L | D6 | After spawn: turrets on server and client | 2 AAirshipTurret attached at the mounts (+-1 cm hull-relative), health 400 |
| T6.2 | L | D6 | Client pilots; camera within 30 deg of the bow; LMB held 1 s | both turrets fire 9-11 each; cannon fire counts unchanged |
| T6.3 | L | D6 | Camera 90 deg to port; LMB press | port broadside fires; turret shot counts unchanged |
| T6.4 | S | D6 | Dummy ship 2 parked 60 m ahead; `TurretFire 1` at its hull 1 s | ship 2 health drop 80 +-25 % (20 bullets x 4 x gun base 1) |
| T6.5 | S | D6 | `TurretFire 1` aimed at a rider on ship 1's own deck | rider and ship 1 health unchanged |
| T6.6 | L | D6 | `Aura.Airship.TurretDamage 0 400` with a gunner on turret L | bDestroyed on server and client; fire FX active on the client; gunner ejected; `TurretFire 1` gives no shots from it |
| T6.7 | S | D6 | Sentinel in range (swarm demo) and `TurretFire` at it | sentinel health decreases |
| T6.8 | S | D6 | GE_GunShootDamage value read at runtime | `GetBulletDamage()` = 4 x the GE's IncomingDamage magnitude (4 in the clone) |
| T6.9 | S | D6 | Ship 1's turrets fire 1 s at ship 2's port turret HitBox from behind ship 2 (ship 2's hull Visibility on) | the first Visibility hit on the line is ship 2's hull; ship 2's turret 0 loses health in whole bullets (> 0) |
| T7.1 | - | D7 | Blender `rig_all.sh` + `verify_all.sh` | PASS, 118 bones, 31 meshes |
| T7.2 | S | D7 | Pilot at the helm, capture from the side | wheel hub near the character's chest; wheel about 140 cm across (bounds of Helm_Wheel's vertices from part_bounds.json 136-144 cm) |
| T7.3 | S | D7 | Top capture of the deck | the 5 pieces gone; turrets at the forward deck edges |
| T8.1 | L | D8 | Client 7 m below the hovering ship's belly, under the hull | F boards; 12 m below: refused |
| T9.1 | S | D9 | P&F cruise 48 m/s, F exit | speed 2.5 +-0.3 m/s within 30 s; heading within 2 deg for 60 s; mode Drift |
| T9.2 | S | D9 | Galleon and Classic: same | same (Galleon: no reverse; fans idle) |
| T9.3 | S | D9 | Exit at rest | mode Hold; moves < 0.5 m in 30 s |
| T9.4 | S | D9 | Drift toward a wall of L_AirshipTest | stops >= 0.5 m short (look-ahead) or on contact; no hull damage; mode Hold |
| T9.5 | S | D9 | Board while drifting | mode None; throttle works at once |
| T9.6 | S | D9 | `Aura.Airship.Input 1 0` on an unpiloted ship, then InputClear at speed | None while active; Coast, then Hold below 3 m/s |
| T9.7 | L | D9 | Client sees the drift | client copy's RepInput has the drift bit; Galleon cosmetics no reverse |
| T10.1 | S/L | D10 | Every new console command runs and logs; Telemetry line 3 present | PASS |

Regression (lead, same editor session):

* Crew share: `as_30`, `as_43` and `as_45` set `UAirshipSettings.CrewDamageShare` to 0 for the whole run (knobs
  `AS30_CREW_SHARE` / `AS45_CREW_SHARE`, default 0.0, None keeps the project value; restored at the end). D4 would hurt
  the pilot in as_43's damage phase (3 x 300: the second hit's share kills the 85-health pilot, the respawn destroys the
  harness's character, j2_death and b4_hud_after_death fail) and in as_45's `gun` phase (k1_client_exit and
  d2_pilot_ejected compare the pilot's health with its value before boarding). as_30 passed j2 by luck.
* `as_43_pie_validate.py` (Classic): 24/25 as before (f2_boost_path is the documented v1 limit). `a3_deck_stand`
  starts after `debug_clear_input` on an unpiloted, slow ship: it now holds (expected to pass better). If a check
  depends on the old coast, the harness sets `Aura.Airship.Set Settings.bHoldWhenUnpiloted 0` and
  `Settings.DriftSpeed 0` for that phase only.
* `as_45_pie_mp.py` (Classic): 22/22. Its `cannons` phase sets the client's yaw (`as_45_pie_mp.py:975`); if a press
  ever happens within 50 deg of the bow, set `Settings.DriverTurretArcDeg 0` on the client for that phase. After
  `c_exit` the ship drifts (moving exit): any position check after it must allow for it (or set
  `Settings.DriftSpeed 0` on the server for that phase).
* `Aura.Airship.Scheme check`: 0 differences under Classic; the other schemes' counts unchanged (none of the new
  properties are scheme-owned).
* `as_50f` follow-up checks: 9/9.

Not testable in PIE: late join (the design relies on replicated state and OnReps; code review covers it), logout of a
mounted gunner (simulated by destroying the client's character: the station clears next tick, T5 extra).

---

## 5. Risks, open items, order of work

### 5.1 Risks

1. **Walkable lid (UCX) hides gunners.** Gunners stand on the planks inside SM_Airship's convex hulls (lid 1.2-2.9 m
   above the planks, gantry convex up to z 1080). Visibility traces at them mostly hit the hull: they take the crew share,
   not direct hits. (The turrets sit inside the same convex: since the review fixes their hits are handed on from the
   hull, section 6.3. Gunners are not.) Turret gunners can only be reached on foot by standing on top of the gantry convex
   (`StationMountHeightAbove` 600 makes that count), and dismounting puts them on top of it. The real fix is re-authored
   UCX hulls (CPP_NOTES.md:111-117), not in PR A.
2. **Possessed character attached to a simulated hull.** Never tested before (round2_map seats). Mitigated by CMC
   ticking off on server and owner (T5.13). The dismount snap (one round trip) exists today for the pilot; the
   hull-relative exit point reduces it.
3. **Unmapped ability keys** stay live for gunners (and for the pilot, today). If the on-foot mapping has ability keys
   IMC_Airship doesn't map, a gunner can cast from the seat. Check IMC_PlayerMappings in the editor stage; if it
   matters, a follow-up adds those keys to IMC_Airship (an asset change, out of PR A's no-new-input rule).
4. **User's local GE_GunShootDamage = 1000** (his uncommitted test value): turret bullets do 4000 in his tree and
   one-shot a 2000 HP ship; balls are unaffected (gun units). Tell him.
5. **User's empty local PA_Airship**: D3 doesn't need it; PR A doesn't touch PA. The committed PA keeps the old helm
   boxes (bigger than the new wheel).
6. **Balls now block Visibility**: every Visibility trace in the project can hit a ball for the second it flies (beam,
   electrocute, sentinel bullets, the gun's wall trace). Acceptable; the ship's aim traces ignore them.
7. **Drift and hold change every scheme after an exit** (on purpose). Old harness checks that assumed a coasting or
   creeping ship need the settings switches above.
8. **Driver LMB in the bow arc fires turrets instead of a broadside** in every scheme (on purpose). Classic players who
   fired broadsides while looking ahead now fire turrets; `DriverTurretArcDeg 0` restores the old LMB.
9. **Balance numbers are first guesses**: CrewDamageShare 0.25 vs the characters' MaxHealth; BallMaxHealth 30 means a
   character alone can't shoot a ball down in its 1-3 s flight (30 gun hits at 4.6/s), only turrets (8 bullets) or
   several players; 244 m max level range at the rig's 8.5 deg cap.
10. **NDC tracer gotcha**: copied systems must be written to the original channel with SystemToSpawn (memory note);
    the tracer speed constant inside PS_06 may not be found by the probe (as_54 warns; tracers then lag at long range).
11. **Atlas repack** changes the prop textures; the cannons and helm must look the same after re-import (T7.2 capture).
12. **CR_Airship rebuild** in place (as_12_reuse) after the bone moves: the Helm wreck body and wheel pivot depend on
    the new rest pose; as_13 must pass. Never delete CR_Airship while it is loaded (memory: crash).
13. **Bandwidth**: StationAims ride the ship's every-frame replication; each turret's multicast + ForceNetUpdate at up
    to 10 Hz. Small, but the listen-server test should keep an eye on the net stats.

### 5.2 Open items for the user (not blocking PR A)

* Wheel size: 140 cm across the tips (character height) as asked; the research target was 100-120 cm.
* Turret placement x 2100 from image 2 (the lead's first range was x 2400-2900).
* BallMaxHealth 30 and CrewDamageShare 0.25 tuning; 4x vs 10x (TurretGunDamageMultiplier is a project setting).
* His local PA_Airship (empty) and GE_GunShootDamage (1000): keep or revert.

### 5.3 PR B hooks left open

* `EAirshipUnpilotedMode::Lane` slots into `UpdateUnpilotedMode`; the hold law already takes a moving point and velocity
  (`FAirshipUnpilotedTarget::HoldVelocity`).
* Team checks: `AAirshipCannonball::ShouldIgnore`, the turret's target filter (`FireOneShot` step 5), `CanBoard` /
  `CanMount` are the single places to add a same-team test.
* Sentinel targeting of unmanned ships: `GatherPlayerTargets` untouched; `BulletTargetTag` already lets bullets hurt any
  ship.

### 5.4 Order of work

1. **Parallel**: combat, turret (C++ per sections 1-2), blender (D7: scripts, run `rig_all.sh` + `verify_all.sh`,
   renders, FBX, dims JSON), assets (write as_51-as_59 and the as_06 edit; nothing runs yet).
2. **core** (needs the combat and turret headers and the blender dims for `PilotSeatFallback` / mounts).
3. **Build**: `/mnt/new_partition/UnrealProjects/_AirshipWork_logs/build_r2.sh` (foreground, long timeout, `free -g`
   first). Fix compile errors in the owning files.
4. Reviews (correctness, multiplayer, style) and fixes, rebuild.
5. **Editor stage (lead)**: editor on the clone; as_51, as_52; as_02, as_56, as_09 (headless Blender), as_12_reuse,
   as_13; as_53, as_54, as_55, as_57, as_58; then PIE: as_59 standalone, as_59 listen; regression as_43, as_45, scheme
   check, as_50f. Editor closed at the end (memory: keep the editor closed when idle).
6. Docs (core): CPP_NOTES.md new section 15 "Round 2" (stations, turrets, crew damage, drift/hold, D3, console),
   HOW_TO_FLY.md (gunner keys, F near a gun, the turrets, drift/park after exit, boarding from under the hull).
7. Lead: commit, PR A.

---

## 6. Review fixes (2026-11-25)

The review of the built PR A code found ten problems (two of them the same one). What changed, file:line in the clone
after the fix build (`build_r2.sh`, EXIT 0). Nothing here has run in PIE yet: the PIE checks named below belong to the
editor stage.

### 6.1 A mounted gunner's own copy left the seat (must fix)

* **Problem.** The gunner stays the player's controlled character. Moves the client sent before `ClientMountChanged`
  reached it still arrive: `ServerMove_PerformMovement` only checks `IsActive`, not the tick. The server answered each
  with a correction (the movement mode differs, MOVE_None with no base, so a world-space one), and the client applied
  it with `SetWorldLocation` to its capsule, which was attached to the hull by then. Nothing put it back: the gunner's
  own view sat off the seat by the hull's client/server lag for the whole mount (about 5 m at 48 m/s with 100 ms).
* **Fix.**
  * Server: `MountGunner` sets the gunner's `bIgnoreClientMovementErrorChecksAndCorrection` (`AirshipPawn.cpp:1791`),
    so those moves are acked. `DismountGunner` restores the old value before the launch (`:1923`, saved per station
    in `bStationGunnerIgnoredCorrections`, `AirshipPawn.h:1607`).
  * Owner: `BeginLocalGunner` sets `bClientIgnoreMovementCorrections` (`AirshipPilotComponent.cpp:617-620`), and
    `EndLocalGunner` restores it (`:702`).
  * Safety net: `TickLocalGunner` puts the client's copy back on the seat (hull-relative, the same point on every
    machine) when it drifts more than 5 cm (`:964-967`).
* **PIE:** T5.13 now mounts while walking and flies 30 m/s with `Net PktLag=100` (section 4). No listen-server harness
  exists for round 2 yet; as_45's lag phases show how to emulate it.

### 6.2 Client copies of spent balls kept their Visibility block (should fix)

* **Problem.** `MulticastImpact_Implementation` and the client branch of `OnProjectileStop` hid and stopped the ball but
  left its collision on. The hidden ball sat on the target for `ImpactDestroyDelay` plus latency, the client's
  crosshair sweep picked it, and `GA_GunShoot::MyFunc` ignores balls (a spent one takes no damage): a client's shots at
  a target a ball had just hit did nothing.
* **Fix.** Both now call `SetActorEnableCollision(false)` (`AirshipCannonball.cpp:231`, `:440`), as `Explode` does on
  the server.

### 6.3 The turrets sat inside the hull's collision (must fix; two findings)

* **Problem.** Both mounts (2100, +-245, 655) put the HitBox inside SM_Airship's forward deck convex (UCX_01: x 10.2-31.2
  m, |y| <= 3.6 m, z 3.0-10.8 m; checked against its face planes: every HitBox corner at least 9 cm inside). The hull
  blocks Visibility, so sentinel bullets, enemy turret rounds and the character gun all stopped on the hull: the ship
  took the damage and a turret could only be hurt by cannonball splash. T3.2 hid this by turning the hull's Visibility
  off.
* **Fix.** A hull hit is handed on to the turret behind it:
  * `AAirshipPawn::FindTurretBehindHullHit` (`AirshipPawn.cpp:2195`): from the hull impact along the shot, up to
    `TurretHullReach` (25 m: a shot from dead ahead enters UCX_01 about 10 m in front of the turrets), it traces each
    living turret's HitBox with `LineTraceComponent` and returns the nearest. Only when the hull impact is at or above
    the turret's deck plane less `TurretHullPassMargin` (25 cm, `:181-187`): the main hull's convex (UCX_00) ends 55 cm
    below that deck, so the line from there to the turret runs through the open air over the forward deck, never
    through the hull's body. A wreck is skipped (the hull keeps the hit).
  * Sentinel bullets: a new generic hook, `UMechSentinelSwarmSubsystem::BulletTargetRedirect`
    (`MechSentinelSwarmSubsystem.h:30`, `:159`), asked in `TickBullets` for a tagged hit (`.cpp:695-697`). The swarm
    still knows nothing about airships; `UAirshipSubsystem::OnWorldBeginPlay` binds `AAirshipPawn::
    RedirectBulletHitToTurret` (a static function, `AirshipSubsystem.cpp:82`).
  * Turret rounds: `AAirshipTurret::TraceShotLine` (`AirshipTurret.cpp:598`), so the server's damage and a client's
    predicted tracer both end on the turret.
  * Character gun: `GA_GunShoot::MyFunc` (`GA_GunShoot.cpp:377`), with the shot's direction from the camera of the
    last crosshair hit (`OnServerMouseCursorData` keeps it, `:122`; `GetShotDirection`, `:328`), else from the pawn's
    view.
* Gunners are still hidden inside the convex (risk 1). The real fix stays re-authored UCX hulls (CPP_NOTES.md:111-117).
* **PIE:** T3.2 keeps the hull's Visibility on and names the first Visibility hit; new T6.9 fires ship 1's turrets at
  ship 2's turret through ship 2's hull (section 4).

### 6.4 Friendly fire (should fix; two findings)

* **Own turrets.** The character gun damaged the turrets of the shooter's own ship (the new turret has an ASC, and the
  generic branch of `MyFunc` hits any GAS actor). `MyFunc` now skips any target attached to an airship that the shooter
  rides (`GetShipCarrying`, `GA_GunShoot.cpp:97`, `:386-388`): its turrets and its gunners. The same rule as the balls.
  The shooter's own hull is left as it was (round 1 behaviour; a lead question). `AMyProjectile` (fireballs) has no
  friendly-fire rule for anything, the own hull included, so a turret-only rule there would be odd: left as is.
* **The passenger zone was too wide for damage.** `IsPassengerCandidate` counts any character with no movement base
  inside the hull's world bounding box + 300 cm; next to a turned 52 m ship that box reaches tens of metres out. An enemy
  mech jumping or hovering beside a ship was skipped by its turrets, its aim traces and its cannonballs. New
  `AAirshipPawn::IsRiderForDamage` (`AirshipPawn.cpp:1539`): attached to the ship, or its movement base is the ship or
  attached to it, or no base inside the hull's own local box (turned with the ship) up to `RiderZoneHeight` (400 cm, a
  pawn property, `AirshipPawn.h:755`) above it. `GetDamageRiders()` (`:1573`) lists them from every character in the
  world (not the passenger list, which is empty while `bPassengersQueryOnly` is off). Used by
  `AAirshipCannonball::ShouldIgnore` (`AirshipCannonball.cpp:212`), `AAirshipTurret::BuildShotQueryParams`
  (`AirshipTurret.cpp:552`), `AAirshipPawn::TraceAimPoint` (`AirshipPawn.cpp:1035`) and `GA_GunShoot::MyFunc`
  (`:363`, `:388`). The collision side (QueryOnly passengers) keeps `IsPassengerCandidate`. An enemy right over the
  deck still counts as a rider (a known limit).

### 6.5 The drift look-ahead used the target speed (should fix)

* **Problem.** The sweep length came from the drift target (250 cm/s x 3 s = 7.5 m) while the ship was still slowing
  from cruise (48 m/s to 2.5 m/s over about 13 s and 260 m). Sweeps 0.25 s apart didn't even overlap above 30 m/s, so
  obstacles were found by ramming.
* **Fix.** `UAirshipFlightComponent::GetDriftLookAheadDistance` (`AirshipFlightComponent.cpp:1024`): the ship's real
  speed along the drift heading (at least the target) x `DriftLookAheadTime`, plus its stopping distance at
  `HoldAccelMax` (v^2 / 2a, drag ignored, so it errs long), at least `DriftLookAheadMin`. After a 48 m/s exit that is
  about 720 m, shrinking as the ship slows: a far wall ends the drift only once the ship could no longer stop short of
  it. The next sweep comes before the ship has covered half of this one (`:1212-1213`), at most every
  `DriftSweepInterval`.

### 6.6 A gunner killed at the gun ragdolled inside the hull (should fix, needs PIE)

* **Problem.** Gunner seats are at plank height, inside UCX_00 (under the lid) or UCX_01. AMyCharBase's death turns the
  mesh into a simulating ragdoll there (it blocks PhysicsBody, the hull's object type), and `UpdateStations` only moves
  the capsule a tick later. Expected: the body thrown out of the deck and a depenetration kick on the ship, on every
  machine. Not verified (no PIE here).
* **Fix (defensive).** `NotifyStationsChanged` (every machine) binds each gunner's `OnDeathDelegate`
  (`AirshipPawn.cpp:2130`), which the death multicast broadcasts right after starting the ragdoll, before its first
  physics step. `OnStationGunnerDied` -> `KeepCorpseOffHull` (`:2148`, `:2159`): if the body is still attached to this
  ship there, its simulating parts ignore the hull's object type; the body drops through the deck and the GameMode's
  respawn removes it 5 s later. Unbound when the gunner leaves (`:2140`; the server in `DismountGunner`, `:1906`, after
  its detach). A crew-share death dismounts first (D4), so it never gets here and lies on the deck as before.
* **PIE:** new T5.15 (section 4). If the lead prefers a body on the deck: move the ragdoll to the exit point instead
  (simulation off, move, on again), which needs a PIE check of its own.

### 6.7 The regression harnesses and the crew share (should fix; two findings)

D4 hurts the pilot whenever the ship loses Health. as_43's damage phase (3 x 300) kills the 85-health pilot on the second
hit, the respawn destroys the harness's character, and j2_death / b4_hud_after_death fail (as_30's 3 x 500 passed j2 by
luck). as_45's `gun` phase gives the client pilot a quarter of each hit, and k1_client_exit / d2_pilot_ejected compare
with the health before boarding. `as_30_pie_smoke.py` (`crew_share_set` / `crew_share_restore`, used by its `arm` /
`restore`; as_43 inherits them) and `as_45_pie_mp.py` now set `CrewDamageShare` to 0 for the whole run and restore it.
Section 4 lists it with the other switches.

---

## Appendix A. New settings (`UAirshipSettings`, all `UPROPERTY(Config, EditAnywhere)`)

| Category | Name | Type | Default | Unit / meaning |
|---|---|---|---|---|
| Boarding | `BoardBelowDistance` | float | 1000 | cm: a pawn under the hull (trace straight up hits it) can board; 0 = off |
| Stations | `StationMountDistance` | float | 350 | cm, horizontal radius around a station seat for F |
| Stations | `StationMountHeightAbove` | float | 600 | cm the pawn may be above the seat (the lid, the gantry convex) |
| Stations | `StationMountHeightBelow` | float | 200 | cm the pawn may be below the seat |
| Stations | `CannonSeatOffset` | FVector | (-90, 130, 0) | cm from the carriage bone: hull X, inboard (mirrored), Z |
| Stations | `TurretSeatOffset` | FVector | (-100, 0, 0) | cm from the turret mount, hull space |
| Stations | `CannonExitOffset` | FVector | (0, 120, 0) | cm from the seat (Y inboard, mirrored); then dropped onto the hull top |
| Stations | `TurretExitOffset` | FVector | (-150, 0, 0) | cm from the seat; then dropped onto the hull top |
| Stations | `GunnerAimSendRate` | float | 25 | Hz, most aim RPCs per second |
| Stations | `GunnerAimSendMinDelta` | float | 5 | cm the aim must move to send before the heartbeat |
| Stations | `GunnerAimHeartbeat` | float | 0.5 | s, longest gap between aim RPCs |
| Stations | `GunnerMaxAimDistance` | float | 70000 | cm, server rejects aim points farther from the seat |
| Stations | `GunnerAimFOVOffset` | float | -15 | deg added to the gunner's camera FOV while Aim is held |
| Stations | `GunnerZoomStep` | float | 75 | cm of arm length per wheel step |
| Stations | `GunnerZoomMinScale` / `GunnerZoomMaxScale` | float | 0.5 / 1.5 | of the arm length at mount |
| Crew | `CrewDamageShare` | float | 0.25 | share of each ship Health loss dealt to the pilot and each gunner; 0 = off |
| Cannons | `MuzzleFXMaxSeconds` | float | 1.0 | s, cannon muzzle FX components are cut after this; 0 = no cap |
| Cannons | `bCannonAimLeadShipVelocity` | bool | true | ballistic aim corrects for the velocity the ball inherits |
| Turrets | `bSpawnTurrets` | bool | true | |
| Turrets | `TurretClass` | TSoftClassPtr<AAirshipTurret> | BP_AirshipTurret_C | missing -> AAirshipTurret (no meshes) |
| Turrets | `TurretMounts` | TArray<FAirshipTurretMount> | D6.1 table | hull space |
| Turrets | `TurretGunDamageMultiplier` | float | 4 | bullet damage = this x gun base damage; also the gun units a bullet does to a ball |
| Turrets | `GunDamageEffect` | TSoftClassPtr<UGameplayEffect> | GE_GunShootDamage_C | where the gun base damage is read |
| Turrets | `GunDamageFallback` | float | 1 | gun base damage when the GE can't be read statically |
| Turrets | `DriverTurretArcDeg` | float | 50 | deg off the bow in which the pilot's LMB drives the unmanned turrets; 0 = LMB always fires broadsides |
| Unpiloted | `DriftSpeed` | float | 250 | cm/s; 0 = no drift |
| Unpiloted | `DriftMinExitSpeed` | float | 100 | cm/s forward at exit to start a drift |
| Unpiloted | `DriftGain` | float | 1.0 | 1/s, forward speed loop |
| Unpiloted | `DriftAccelMax` / `DriftDecelMax` | float | 100 / 200 | cm/s^2 caps of the drift force |
| Unpiloted | `DriftLookAheadTime` / `DriftLookAheadMin` | float | 3.0 / 600 | s / cm of the look-ahead sweep |
| Unpiloted | `DriftSweepInterval` | float | 0.25 | s |
| Unpiloted | `DriftSweepInset` / `DriftSweepFloorLift` | float | 100 / 200 | cm |
| Unpiloted | `DriftBowHitMinDot` | float | 0.5 | |
| Unpiloted | `DriftMaxDistance` | float | 0 | cm; 0 = no limit |
| Unpiloted | `bHoldWhenUnpiloted` | bool | true | hold position when unpiloted, slow and not drifting |
| Unpiloted | `HoldEngageSpeed` | float | 300 | cm/s |
| Unpiloted | `HoldKp` / `HoldKd` | float | 0.4 / 0.8 | 1/s^2 / 1/s |
| Unpiloted | `HoldAccelMax` | float | 200 | cm/s^2 |
| Unpiloted | `HoldYawGain` / `HoldYawRateMax` | float | 0.5 / 10 | deg/s per deg / deg/s (drift and hold) |
| Unpiloted | `HoldResetDistance` / `HoldResetYawDeg` | float | 2000 / 60 | cm / deg |

## Appendix B. New telemetry fields (`FAirshipFlightTelemetry`, `BlueprintReadOnly`)

| Field | Type | Filled by | Meaning |
|---|---|---|---|
| `UnpilotedMode` | uint8 | flight | EAirshipUnpilotedMode (server; 0 on clients) |
| `bUnpilotedDrift` / `bUnpilotedHold` | bool | flight | mode 2 / 3 |
| `DriftTargetSpeedMS` | float | flight | m/s |
| `HoldOffsetM` | float | flight | horizontal distance COM -> hold point, m |
| `StationMask` | int32 | pawn | bit s = station s manned (every machine) |
| `NumGunners` | int32 | pawn | |
| `TurretHeat` | TArray<float> | pawn | 0..1 per turret (L, R) |
| `TurretHealth` | TArray<float> | pawn | per turret |
| `TurretDestroyedMask` | int32 | pawn | bit t |
| `TurretShots` | TArray<int32> | pawn | `GetShotCount()` per turret on this machine |
| `PilotHealth` | float | pawn | the pilot character's Health, -1 without a pilot |
| `CannonReadyMask` | int32 | pawn | bit c = cannon c loaded on this machine's clock |

## Appendix C. Hook point index (53198d0)

| Where | Change | Owner |
|---|---|---|
| `AirshipCannonball.h:73,77,81,85,92` | defaults | combat |
| `AirshipCannonball.cpp:39` | Visibility Block | combat |
| `AirshipCannonball.cpp:166-180` | ShouldIgnore riders | combat |
| `AirshipCannonball.cpp:212` (Explode) / new ApplyShotDamage | shot down | combat |
| `GA_GunShoot.cpp:297` | cannonball branch | combat |
| `MechSentinelSwarmSubsystem.cpp:644-673` | tagged-target trace | combat |
| `AirshipPawn.cpp:236` | BulletTargetTag on the ship | core |
| `AirshipPawn.cpp:349-359` | replicated stations, turrets | core |
| `AirshipPawn.cpp:388-394, 407` | health delegate, SpawnTurrets | core |
| `AirshipPawn.cpp:410-454` | EndPlay gunners + turrets | core |
| `AirshipPawn.cpp:474` | UpdateStations, UpdateTurretCommands | core |
| `AirshipPawn.cpp:764-883` | FireHeld bit, local turret commands | core |
| `AirshipPawn.cpp:885-908` | TraceAimPoint | core |
| `AirshipPawn.cpp:1039-1076` | CanBoard, IsWithinBoardRange(+below) | core |
| `AirshipPawn.cpp:1105-1241` | vitals snapshot moved, NotifyPilotLeft | core |
| `AirshipPawn.cpp:1272-1315` | passenger collision skips gunners | core |
| `AirshipPawn.cpp:1361-1395` | seats | core |
| `AirshipPawn.cpp:1407-1548` | reload per cannon, ballistic aim, manned aim | core |
| `AirshipPawn.cpp:1550-1766` | RequestFire, FireCannons, FireStation, multicast mask, D1 cap | core |
| `AirshipPawn.cpp:2130-2154` | NotifyHullContact | core |
| `AirshipPawn.cpp:2252-2268, 2387-2393` | EjectCrewAfterDeath | core |
| `AirshipPawn.cpp:2680-2707` | telemetry | core |
| `AirshipPawn.cpp:3523-3578` | gun lock skips a manned side | core |
| `AirshipPawn.h:590, 620, 539` | CannonballSpeed, spawn offset, PilotSeatFallback | core |
| `AirshipPawn.h:1074-1075, 1186, 1203, 1208-1211, 1297-1299` | multicast mask, HandleCannonsFired, public CancelPilotAbilities, vitals removed, per-cannon clocks | core |
| `AirshipFlightComponent.cpp:419-472, 601-649, 814-918, 1239, 1598, 1643, 1797` | D9 hooks | core |
| `AirshipPilotComponent.cpp:142-292` | stations, RPCs, gunner input | core |
| `AirshipSubsystem.cpp:522-540, 807-841` + new commands | console, FindGunnerStation | core |
| `AirshipHUDWidget.cpp:177-286, 288-368, 370+` | gunner mode, GUNS / PILOT rows | core |
| `as_06_muzzle.py:24` | lifetimes + loop once | assets |
