# Airship pawn: Aura C++ / content / config research

Read-only research for `AAirshipPawn` (drivable, possessable, GAS, Control Rig, Niagara, listen server).
Source: clone `/mnt/new_partition/UnrealProjects/_AirshipWork` (branch `claude/project-thread-0emzt1` = origin/redo3 96ce1fe).
Engine: `/mnt/new_partition/5.8/Engine`. Paths below are relative to `Source/Aura/` unless they start with `Engine/` or `Content/`.
Engine refs: `GAS/` = `Engine/Plugins/Runtime/GameplayAbilities/Source/GameplayAbilities/`, `EI/` = `Engine/Plugins/EnhancedInput/Source/EnhancedInput/`, `Eng/` = `Engine/Source/Runtime/Engine/`.
Blueprint values were decoded offline from the .uasset files (parser in `_AirshipWork_logs/scratch/cpp_research/`). Anything not checked is marked [unverified].

---

## 0. Short answer

* **Ship ASC + `UMyAttributeSet` on the ship itself** (`UMyAbilitySystemComponent`, `InitAbilityActorInfo(this, this)`), like an enemy, and the pawn implements `IAbilitySystemInterface` + `IMyCombatInterface` in C++.
  A new small `UAirshipAttributeSet` gets **zero damage from every existing source**: they all write `UMyAttributeSet::IncomingDamage`, and GAS drops modifiers for sets the target lacks (section 1.5).
* With `UMyAttributeSet` on the ship, these hurt the ship **with no code change**: projectiles (`AMyProjectile` + `GE_ProjectileDamage`), sentinel attacks (`GE_SentinelAttack`), Electrocute and Shards.
  **The gun needs one shared change**: `UGA_GunShoot::MyFunc` only accepts `AMyCharBase` targets (5 lines, section 1.6).
* **Possessing the ship breaks three things that crash the server**, all in the player's own GAS code. The unpossessed pilot has no Controller and no PlayerState:
  * `UAT_SendMouseCursorData::Activate` dereferences the avatar's controller (gun, beam).
  * The `UMyAttributeSet` IncomingXP block dereferences `SourceCharacter` (null while piloting).
  * `AMyCharPlayer::AddToXP/GetLevel` dereference `GetPlayerState()`.

  Guards:
  * a higher-priority ship IMC that consumes the player's keys
  * cancel the pilot's abilities on boarding
  * two 2-line shared null guards (section 1.6), recommended.
* **Re-possessing the character heals it fully.** `AMyCharPlayer::PossessedBy` runs `InitAbilitySystemAfterRespawn`, which re-applies VitalAttributesEffect. The ship's exit code must restore the saved Health/Mana afterwards.
* **Boarding without editing shared classes:**
  * `UAirshipSubsystem` (world subsystem) adds a replicated `UAirshipPilotComponent` to each PlayerController on the server, through `FGameModeEvents::GameModePostLoginEvent`.
  * The component carries the Server RPC and its own IMC / input component.
  * Exit can also go through an RPC on the possessed ship.
* Physics config is all engine defaults: no substepping, no async physics, MaxPhysicsDeltaTime 1/30, physics prediction off. There are no custom collision channels or profiles, so the ship sets every response in C++.
* No Build.cs or uproject change is needed (ControlRigPhysics and ControlRigDynamics are already enabled). This holds as long as C++ drives the rig only through `UAirshipAnimInstance` properties, as the Burrower does.

---

## 1. GAS

### 1.1 Who owns the ASC and attribute set

| | Player (`AMyCharPlayer`, BP_MyCharMech) | Enemy (`AMyEnemyChar`, Burrower) | Sentinels |
|---|---|---|---|
| ASC + set created | `AMyPlayerState` ctor MyPlayerState.cpp:95-99: `UMyAbilitySystemComponent` "MyAbilitySystemComponent" + `UMyAttributeSet` | MyEnemyChar.cpp:18-19 | `AMechSentinelGASProxy` ctor MechSentinelGASProxy.cpp:15-29: plain ASC, not replicated, `UMechSentinelAttributeSet` + `UMyAttributeSet` "SourceAttributeSet" (only so source captures work) |
| ASC replication | `UMyAbilitySystemComponent()` MyAbilitySystemComponent.cpp:16-21: `SetIsReplicated(true)`, `Mixed` | same | none |
| Set found by ASC | engine: `UAbilitySystemComponent::InitializeComponent` collects every `UAttributeSet` outered to the owner (GAS/Private/AbilitySystemComponent_Abilities.cpp:78-106); it also calls `InitAbilityActorInfo(Owner, Owner)` (:84) | same | same |
| InitAbilityActorInfo | server `PossessedBy` MyCharPlayer.cpp:303-340 (`InitAbilityActorInfo(PS, this)` :314); client `OnRep_PlayerState` :241-282 (:253). Re-run on every possession | `BeginPlay` on every machine, MyEnemyChar.cpp:30 | `PostInitializeComponents` MechSentinelGASProxy.cpp:31-37 |
| Startup abilities | `GiveStartupAbilities` + `GivePassiveStartupAbilities` on first possession (:323-325; also called on the client at :264-266, where GAS refuses with an error: GAS/Private/AbilitySystemComponent_Abilities.cpp:301-305). `bAbilitiesGiven` marks later possessions as respawns (:313) | `GiveStartupAbilities()` MyEnemyChar.cpp:31 (also on clients: error log) | none |
| Input → ASC | `AMyPlayerController2::PressedFunc/HeldFunc/ReleasedFunc` MyPlayerController2.cpp:355-376 → **PlayerState's** ASC (`GetMyASC` :216-223) → `AbilityInputPressed` (needs `bAbilitiesGiven`, MyAbilitySystemComponent.cpp:141-143) / `AbilityInputHeld` (TryActivateAbility, :168-182) / `AbilityInputReleased` (:184-200). Matching is by `InputTag` in `DynamicSpecSourceTags` (MyCharBase.cpp:77-89) | n/a | n/a |

PlayerController's `PlayerController` in ActorInfo: `FGameplayAbilityActorInfo::InitFromActor` walks the owner chain. A `APlayerController` is used directly; for an `APawn` it takes `Pawn->GetController()` (GAS/Private/GameplayAbilityTypes.cpp:23-55).
* For the PlayerState-owned player ASC this is always the PC.
* For a pawn-owned ship ASC it is null until possession. It must be refreshed with `RefreshAbilityActorInfo()` (AbilitySystemComponent_Abilities.cpp:286-290) on possess/unpossess, on the server and on the owning client.

### 1.2 Default attribute effects
* Player (BP_MyCharMech CDO, decoded):
  * `PrimaryAttributesEffect = /Game/Level/GAS/GameplayEffects/AttributeEffects/Aura/BP_PrimaryAttributesEffect`
  * `SecondaryAttributesEffect = .../AttributeEffects/BP_SecondaryAttributesEffect`
  * `VitalAttributesEffect = .../AttributeEffects/BP_VitalAttributesEffect`
  * They are applied at the PlayerState level in `InitializeAttributes` (MyCharPlayer.cpp:342-357).
  * `DebugDieAfterBeginPlaySeconds` = **0** on BP_MyCharMech (C++ default 3, MyCharPlayer.h:161), so there are no surprise deaths.
* Respawn: `InitAbilitySystemAfterRespawn` (MyCharPlayer.cpp:359-376) clears the loose tag `State.Dead` and re-applies only Vital (refills Health/Mana).
* Enemies: `UMyBPFuncLib::InitializeEnemyAttributes` (BP-called, private in C++), or the Burrower's own C++ copy (BurrowerCharacter.cpp:188-250): Primary → Secondary → Vital from `DA_CharClassInfo`.
* `PreAttributeChange` clamps Health to [0, MaxHealth] (MyAttributeSet.cpp:196-208). **MaxHealth must be set before Health.**
* Replicated attributes: MyAttributeSet.cpp:210-229. MoveSpeed is not replicated. OnRep_AttackDamage / OnRep_CritChance notify TurnSpeed (copy-paste, :307-315).

### 1.3 Damage pipeline (all server)
1. Source ability or actor builds a spec from **its own ASC**: `MakeOutgoingSpec(GE, Level, Ctx)`, then SetByCaller `MyTags::SetDamageByCaller` ("SetDamageByCaller", MyGameplayTags.cpp:105).
2. Damage GEs (decoded):

   | GE | How it damages |
   |---|---|
   | `GE_ProjectileDamage` | execution `UExecCalc_Damage` |
   | `GE_GunShootDamage` | modifier on `MyAttributeSet.IncomingDamage` |
   | `GE_BeamDamage` | modifier on `MyAttributeSet.IncomingDamage` |
   | `GE_SentinelAttack` (rules asset) | modifier on `MyAttributeSet.IncomingDamage` + SetByCaller |
   | C++ fallback `UMechSentinelAttackEffect` | Additive on `UMyAttributeSet::IncomingDamage` (MechSentinelDefaultEffects.cpp:45-56) |
   | `GE_SentinelDamage` | `UExecCalc_SentinelDamage`, for hits **on** sentinels only |

3. `UExecCalc_Damage` (ExecCalcs/ExecCalc_Damage.cpp):
   * Captures Target `UMyAttributeSet::Armor` and Source `CritChance` (:14-26, :36-37). Reads SetByCaller (:61).
   * Block and crit are cosmetic: random vs Armor/CritChance, the scaling is commented out (:67-76, :94-95). It prints debug strings on every hit (:80-91).
   * Writes `IncomingDamage` **Override** = SetByCaller (:97-98).
4. `UMyAttributeSet::PostGameplayEffectExecute` (MyAttributeSet.cpp:47-194):
   * IncomingDamage → `Health -= dmg` (:64-72).
   * Fatal (`NewHealth <= 0`, every later hit too, because Health stays 0):
     * `Cast<IMyCombatInterface>(TargetAvatar)->Die()` (:74-80), a native C++ cast, so the interface must be inherited in C++
     * XP **only if the target is an `AMyEnemyChar`**, otherwise `return` (:81-83, which also skips the damage number)
     * then `SendGameplayEventToActor(SourceAvatarActor, Attribute.Meta.XP)` (:85-91).
   * Non-fatal: `TargetASC->TryActivateAbilitiesByTag(Ability.HitReact)` (:96). TargetASC is dereferenced unchecked.
   * Damage numbers (:99-128): if `SourceCharacter != TargetCharacter`, cast `SourceController` to `AMyPlayerController`, else to `AMyPlayerController2` (:115), then call `ShowDamageNumber_2(dmg, TargetCharacter, …)`.
   * Both `SourceCharacter = Cast<ACharacter>(SourceController->GetPawn())` (:335) and `TargetCharacter = Cast<ACharacter>(TargetAvatar)` (:343) are `ACharacter*`.
   * `AMyPlayerController2::ShowDamageNumber_2` returns on `!IsValid(TargetCharacter)` (MyPlayerController2.cpp:514), and the widget version does the same (:496). So **no numbers on a non-Character target**.
5. IncomingXP block (MyAttributeSet.cpp:132-193):
   * `Props.SourceCharacter->Implements<UMyPlayerInterface>()` (:141), unchecked
   * `Cast<ACharacter>(Avatar)->GetPlayerState<AMyPlayerState>()->MyLevelUpInfo` (:143), unchecked
   * then `IMyPlayerInterface::Execute_AddToXP` → `AMyCharPlayer::AddToXP_Implementation` → `GetPlayerState<AMyPlayerState>()->AddToXP` (MyCharPlayer.cpp:391-394), unchecked.
6. Death:
   * Enemy: `AMyEnemyChar::Die` = `SetLifeSpan(LifeSpan)` + `AMyCharBase::Die` (MyEnemyChar.cpp:73-77) → `MulticastHandleDeath` (NetMulticast Reliable, MyCharBase.h:93-94).
   * `MulticastHandleDeath_Implementation` (MyCharBase.cpp:132-149):
     * mesh simulate + PhysicsOnly + WorldStatic block
     * capsule NoCollision
     * `Dissolve()` (slot 0)
     * `bIsDead = true`
     * `OnDeathDelegate.Broadcast`.
   * Player: `AMyCharPlayer::Die` guards `bIsDead` (MyCharPlayer.cpp:494-501) → `MulticastHandlePlayerDeath` adds loose `State.Dead` and broadcasts (:503-513). The GameMode respawns (section 3).
7. Sentinel kill XP:
   * `UMechSentinelSwarmSubsystem::GrantKillXP(Instigator)` (MechSentinelSwarmSubsystem.cpp:787-812) takes the instigator's ASC avatar.
   * It sends the XP event only if that avatar `Implements<UMyPlayerInterface>`.

### 1.4 What each damage source needs from the ship

| Source | Query / hit test | Requirement on the ship | Works with `UMyAttributeSet` on ship? |
|---|---|---|---|
| GA_GunShoot (BP calls `UGA_GunShoot::MyFunc`, decoded import list) | aim sweep `ECC_Visibility` sphere r 10, `bTraceComplex`, from the PC2 camera (MyPlayerController2.cpp:80-108), read by `UAT_SendMouseCursorData` (AT_SendMouseCursorData.cpp:23-26) | a component that **blocks Visibility**; then `Cast<AMyCharBase>(InTargetActor)` + `GetMyAttributeSet()` (GA_GunShoot.cpp:297-317) | **No.** The cast fails, so it needs the MyFunc patch (1.6) |
| GA_Projectile → `AMyProjectile` (GE_ProjectileDamage) | `CollisionSphere` BeginOverlap (MyProjectile.cpp:37) | `GenerateOverlapEvents` + overlap response to the sphere's object type; `Cast<IAbilitySystemInterface>(OtherActor)` (:42) | **Yes**, unchanged |
| Mech sentinels (GE_SentinelAttack) | target = `PlayerState->GetPawn()` of every player, skipped if `Execute_IsDead` (MechSentinelSwarmSubsystem.cpp:424-448). Hit = `UAbilitySystemGlobals::GetAbilitySystemComponentFromActor(target)` + `ApplyGameplayEffectSpecToTarget` (MechSentinelCombatProcessors.cpp:179-208) | ASC via the interface; `IsDead` | **Yes**: a possessed ship *becomes* the sentinels' target |
| GA_Electrocute | first hit `SphereTraceSingle(TraceTypeQuery1)` (GA_Electrocute.cpp:28), chain `OverlapMultiByChannel(ECC_Visibility, 1000)` (:58); `Implements<UMyCombatInterface>`, `!IsDead`, binds `GetOnDeathDelegate()` (:35-38, :65-68) | Visibility block/overlap, a real `OnDeathDelegate`; damage GE in BP | Yes [damage GE target set not decoded] |
| GA_Shards | `OverlapMultiByChannel(ECC_Visibility, sphere 100)` (GA_Shards.cpp:16-19) | same | Yes [same] |
| GA_Beam | GA_BeamBP imports no damage GE (only GE_BeamCooldown, GE_GCBeamChargeLooping). `GE_BeamDamage` is referenced by no asset under `Content/Level` or `Content/Assets` | n/a | the beam currently deals no GAS damage [checked by import list + grep] |
| Burrower | no direct damage (cuts hex tiles, no `ApplyGameplayEffect` in Burrower/) | it chases `PlayerState->GetPawn()` (section 3) | n/a |
| Ship cannons → others | own ASC as source; GE_ProjectileDamage (ExecCalc captures source CritChance) | source ASC should have `UMyAttributeSet` | Yes. Sentinels: `UMechSentinelCombatLibrary::ApplyDamageToSentinelsInSweep/InCapsule(Instigator = ship, …)` (MechSentinelCombatLibrary.h:81, 86), from a next-tick timer (outside Mass phases) |

### 1.5 `UMyAttributeSet` vs a new `UAirshipAttributeSet` (Health, MaxHealth, IncomingDamage)

| | Ship ASC has `UMyAttributeSet` | Ship ASC has only `UAirshipAttributeSet` |
|---|---|---|
| ExecCalc_Damage Armor capture | captured | skipped: `CaptureAttributeForGameplayEffect` needs the set (GAS/Private/AbilitySystemComponent.cpp:445-452) |
| Damage written | `UMyAttributeSet::IncomingDamage` → Health → Die | **dropped**: instant modifiers / exec outputs go through `InternalExecuteMod`, which finds no set and executes nothing (GAS/Private/GameplayEffect.cpp:3259, 3300, 4090-4105) |
| Gun / projectile / sentinel / Electrocute / Shards | work (gun after the MyFunc patch) | none of them work. Every GE would need a second modifier or a new exec, and `UMyAttributeSet::PostGameplayEffectExecute`'s death/XP/number logic would have to be copied |
| Death call | `IMyCombatInterface::Die()` on the ship (MyAttributeSet.cpp:76-79) | the ship's own PostGameplayEffectExecute |
| Side effects | XP lookup skipped (not an AMyEnemyChar, :81-83); HitReact activation finds nothing (:96); no damage numbers on the ship (TargetCharacter null) | — |
| Ship as source (cannons) | CritChance capture works | CritChance 0 (no crash) |

**Choice: `UMyAttributeSet`.** A second set for ship-only stats (heat, fuel) is fine, since GAS allows several sets. It just cannot hold the damage meta attribute.

### 1.6 Recommended minimal code

Ship GAS core (new file, the pattern from AMyEnemyChar + Burrower):

```cpp
// Public/Airship/AirshipPawn.h (GAS part)
UCLASS()
class AURA_API AAirshipPawn : public APawn, public IAbilitySystemInterface, public IMyCombatInterface
{
	GENERATED_BODY()
public:
	AAirshipPawn();
	virtual UAbilitySystemComponent* GetAbilitySystemComponent() const override { return AbilitySystemComponent; }

	/** Server. Every fatal hit calls it (Health stays at 0): only the first one counts. */
	virtual void Die() override;
	virtual bool IsDead_Implementation() override { return bShipDead; }
	virtual int32 GetLevel_Implementation() override { return ShipLevel; }
	virtual FOnDeathDelegateSignature& GetOnDeathDelegate() override { return OnDeathDelegate; }

protected:
	virtual void BeginPlay() override;
	virtual void PossessedBy(AController* NewController) override;   // + RefreshAbilityActorInfo
	virtual void UnPossessed() override;                              // + RefreshAbilityActorInfo
	virtual void NotifyControllerChanged() override;                  // client: Refresh + IMC add/remove

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Airship|GAS")
	TObjectPtr<UMyAbilitySystemComponent> AbilitySystemComponent;

	UPROPERTY()
	TObjectPtr<UMyAttributeSet> AttributeSet;

	/** Health the ship starts with (server, BeginPlay). The gun deals 1 per hit (GA_GunShoot.cpp:322). */
	UPROPERTY(EditDefaultsOnly, Category = "Airship|GAS", meta = (ClampMin = "1"))
	float MaxHealth = 300.f;

	/** UExecCalc_Damage: percent chance a hit shows as Blocked (cosmetic). */
	UPROPERTY(EditDefaultsOnly, Category = "Airship|GAS", meta = (ClampMin = "0", ClampMax = "100"))
	float Armor = 0.f;

	UPROPERTY(EditDefaultsOnly, Category = "Airship|GAS", meta = (ClampMin = "1"))
	int32 ShipLevel = 1;

	UPROPERTY(ReplicatedUsing = OnRep_ShipDead)
	bool bShipDead = false;

	FOnDeathDelegateSignature OnDeathDelegate;
};

// Private/Airship/AirshipPawn.cpp (excerpt)
AAirshipPawn::AAirshipPawn()
{
	AbilitySystemComponent = CreateDefaultSubobject<UMyAbilitySystemComponent>(TEXT("AbilitySystemComponent"));
	AttributeSet = CreateDefaultSubobject<UMyAttributeSet>(TEXT("AttributeSet"));
}

void AAirshipPawn::BeginPlay()
{
	Super::BeginPlay();
	AbilitySystemComponent->InitAbilityActorInfo(this, this);
	if (HasAuthority())
	{
		// MaxHealth first: PreAttributeChange clamps Health to it
		AbilitySystemComponent->SetNumericAttributeBase(UMyAttributeSet::GetMaxHealthAttribute(), MaxHealth);
		AbilitySystemComponent->SetNumericAttributeBase(UMyAttributeSet::GetHealthAttribute(), MaxHealth);
		AbilitySystemComponent->SetNumericAttributeBase(UMyAttributeSet::GetArmorAttribute(), Armor);
	}
}

void AAirshipPawn::Die()
{
	if (!HasAuthority() || bShipDead)
	{
		return;
	}
	bShipDead = true;            // late joiners (OnRep), like ABurrowerCharacter::bBurrowerDead
	MulticastHandleShipDeath();  // wreck: anim bIsDead -> CR physics, FX, stop forces
	SetLifeSpan(WreckLifeSpan);
	// Called from inside the GE execution: eject the pilot next tick, not here (re-possess, launch)
	GetWorldTimerManager().SetTimerForNextTick(this, &ThisClass::EjectPilotOnDeath);
}
```

APIs checked in the 5.8 source:
* `SetNumericAttributeBase` GAS/Public/AbilitySystemComponent.h:233
* `RefreshAbilityActorInfo` :1546
* `GetSet<T>` :128
* `CancelAbilities` :1058
* `GameplayEffectApplicationQueries` (a friendly-fire filter hook) :77, :560, used in AbilitySystemComponent.cpp:1037.

The UHT-generated defaults for the other `IMyCombatInterface` events exist (Intermediate/.../MyCombatInterface.generated.h:23-32), so only the ones above need overriding.

**Shared patch 1: the gun can hurt any ASC actor with `UMyAttributeSet`** (GA_GunShoot.cpp:297-317, replaces the `AMyCharBase` cast):

```cpp
void UGA_GunShoot::MyFunc(FVector InImpactPoint, AActor* InTargetActor)
{
	// Characters and any other actor whose ASC has UMyAttributeSet (AAirshipPawn)
	IAbilitySystemInterface* AscIF = Cast<IAbilitySystemInterface>(InTargetActor);
	TargetAsc = AscIF ? AscIF->GetAbilitySystemComponent() : nullptr;
	const UMyAttributeSet* TargetAttributeSet = TargetAsc ? TargetAsc->GetSet<UMyAttributeSet>() : nullptr;
	if (!TargetAttributeSet) return;
	// ... unchanged from "FGameplayEffectContextHandle GEContext=ASC->MakeEffectContext();" on
}
```

For players this is the same set as before: `AMyCharBase::GetAbilitySystemComponent` returns the PlayerState ASC (MyCharBase.cpp:61-64).

**Shared patch 2 (crash guard): XP while piloting** (MyAttributeSet.cpp:141, top of the IncomingXP block):

```cpp
// Piloting an AAirshipPawn: the character is unpossessed (no PlayerState) and the PC's pawn is not a Character
if (!Props.SourceCharacter || !Props.SourceCharacter->GetPlayerState()) return;
```

This drops XP that arrives while piloting, for example from a projectile still in flight when the player boarded. Without the guard the server crashes.

**Shared patch 3 (crash guard): abilities on an unpossessed avatar** (AT_SendMouseCursorData.cpp:18):

```cpp
const AController* InstigatorController = GetAvatarActor() ? GetAvatarActor()->GetInstigatorController() : nullptr;
if (!InstigatorController) { EndTask(); return; }
const bool bIsLocalController = InstigatorController->IsLocalController();
```

Optional: before the damage block in PostGameplayEffectExecute (:64), add `if (Props.TargetAvatarActor && Props.TargetAvatarActor->Implements<UMyCombatInterface>() && IMyCombatInterface::Execute_IsDead(Props.TargetAvatarActor)) return;`. That is the corpse-XP fix from the Burrower notes; it also stops wreck hits.

---

## 2. Patterns to copy

| Pattern | Where | Copy for the ship |
|---|---|---|
| UDeveloperSettings, header-only, `UCLASS(Config = Game, DefaultConfig, meta = (DisplayName = "Burrower"))`, `TSoftClassPtr` class | Burrower/BurrowerSettings.h:20-85 → DefaultGame.ini `[/Script/Aura.BurrowerSettings]` (:182-183) | `UAirshipSettings`: boarding radius, interact IMC/IA soft refs, `AirshipClass` for the spawn command. Add `+DirectoriesToAlwaysCook=(Path="/Game/Assets/MyShip")` (cook list DefaultGame.ini:139-143 is maps-only otherwise) |
| Data asset on the GameMode instead | `BP_MyGameMode.SentinelSwarmRules = DA_MechSentinelSwarmRules` (decoded) | not needed. Per-ship tuning = EditDefaultsOnly on `AAirshipPawn` (BP_AirshipPawn) |
| Console commands, non-shipping, **named** namespace (unity build) | BurrowerSpawnSubsystem.cpp:456-497 (`FAutoConsoleCommandWithWorldAndArgs`, `FAutoConsoleCommandWithWorld`), CVar BurrowerCharacter.cpp:33-40 (`TAutoConsoleVariable<int32>`) | `Aura.Airship.Spawn`, `Aura.Airship.KillAll`, `Aura.Airship.Damage N`, `Aura.Airship.Board [PlayerIndex]`, CVar `Aura.Airship.DebugForces` |
| Log category per file | `DEFINE_LOG_CATEGORY_STATIC(LogBurrower, Log, All)` BurrowerCharacter.cpp:30 | `LogAirship` |
| Anim instance, thread-safe | Burrower/BurrowerAnimInstance.h:23-96, .cpp:8-95: game-thread `NativeUpdateAnimation` copies into a private `FInputs`, `NativeThreadSafeUpdateAnimation` integrates (angles wrapped, `FInterpConstantTo`), editor preview uses `GetDefault<ABurrowerCharacter>()`, public `Transient BlueprintReadOnly` props named like the CR pins | `UAirshipAnimInstance`: FanYawDeg[2], FanSpinDeg[2], ThrusterPitchDeg[4], Thrust[4], WheelAngleDeg, CannonRecoil[4], Speed, bIsDead, DeathTime |
| Death: server once + replicated bool + multicast + local once | Burrower: `Die` guard + `bBurrowerDead` (BurrowerCharacter.cpp:255-267), `MulticastHandleDeath_Implementation` → `HandleBurrowerDeath` (:269-331, `if (bIsDead) return`), `OnRep_BurrowerDead` (:274-281), BeginPlay covers the first bunch (:158) | `Die` → `bShipDead` + `MulticastHandleShipDeath` + OnRep → `HandleShipDeath()` once per machine: forces off, anim bIsDead (CR physics), FX, `BP_OnShipDied` |
| LifeSpan | `SetLifeSpan(LifeSpan)` in `AMyEnemyChar::Die` (MyEnemyChar.cpp:75) | `WreckLifeSpan` |
| Relevancy | Burrower `bAlwaysRelevant = true` (BurrowerCharacter.cpp:52); engine default cull 150 m (Eng/Private/Actor.cpp:312) | `bAlwaysRelevant = true` (52 m hull); use `SetNetUpdateFrequency` (Eng/Classes/GameFramework/Actor.h:4624, the public field is deprecated) |
| Server-only poll of players | BurrowerSpawnSubsystem.cpp:224-245 (`PlayerArray`, `PS->GetPawn()`, keyed by PlayerState) | ship registry / nearest-ship lookup in `UAirshipSubsystem` |
| C++-defined GEs (no asset) | MechSentinelDefaultEffects.cpp:36-56 (exec or SetByCaller modifier built in the ctor) | optional `UAirshipCannonDamageEffect` (exec `UExecCalc_Damage`) if GE_ProjectileDamage should not be shared |
| Native tags in a feature file | MechSwarm/GAS/MechSentinelTags.cpp (`UE_DEFINE_GAMEPLAY_TAG`) | `AirshipTags.cpp` (e.g. `State.Airship.Piloting`), no edit to MyGameplayTags |
| Sentinels avoid a moving actor | `UMechSentinelObstacleComponent` (MechSwarm/Core/MechSentinelObstacleComponent.h:7-40, "a floor, the airship, a bridge"; `RefreshInterval` for movers) | add it to the ship, `RefreshInterval ≈ 0.25 s`. It is a world AABB of pawn-blocking components, so it is loose for a rotated 52 m hull |

---

## 3. Input, and what breaks when the PC possesses a non-Character pawn

**Which controller:** decoded `BP_MyGameMode` defaults:
* `PlayerControllerClass = /Game/Level/PlayerInput/BP_MyPlayerController2` (parent `AMyPlayerController2`)
* `ReplaySpectatorPlayerControllerClass = BP_MyPlayerController` (`AMyPlayerController`, the old top-down Aura PC, not used in play)
* `DefaultPawnClass = /Game/Level/MechChar/BP_MyCharMech`, `PlayerStateClass = BP_MyPlayerState`, `HUDClass = BP_MyHUD`
* `GlobalDefaultGameMode` in DefaultEngine.ini:6.

**Input assets** (decoded `BP_MyPlayerController2` defaults):
* IMC `IMC_PlayerMappings` with IA_Move, IA_Rotate, IA_Q, IA_E, IA_Pause; `IA_Jump` is unset; `InputConfig = DA_MyInputCofig`.
* `DA_MyInputCofig`: IA_LMB → Input.LMB, IA_RMB → Input.RMB, IA_Shift → Input.Shift, IA_Space → Input.Space (pairs by name [unverified order]).
* IMC key names (PlayerMappableKeySettings, rebindable):
  * MoveForward / MoveBackward / MoveLeft / MoveRight (IA_Move)
  * JumpHover (SpaceBar)
  * BoostGrapple (LeftShift)
  * Shoot (LeftMouseButton)
  * Beam (RightMouseButton)
  * AttributeMenu (Q), SpellMenu (E)
  * Escape / Gamepad_Special_Right (IA_Pause)
  * IA_Rotate on Mouse2D.
* `IMC_PlayerMappings` is added at **priority 0** (MyPlayerController2.cpp:139-141).
* Bindings: MyPlayerController2.cpp:143-157. `DefaultInputComponentClass=/Script/Aura.MyInputComponent` (DefaultInput.ini:80). `bEnableUserSettings=True` (:88).

**Key masking works by key:**
* Enhanced Input sorts contexts by priority (EI/Private/EnhancedInputSubsystemInterface.cpp:946).
* A mapping whose action has `bConsumeInput` (default true, EI/Public/InputAction.h:94-96) adds its key to `AppliedKeys`, and lower-priority contexts skip that key (:1041-1055, :1091).
* So **`IMC_Airship` at priority ≥ 1, mapping the same keys, silences the on-foot abilities and IA_Move while piloting**.
* It must map the *same physical keys* the player bound. Rebinding is per mapping name, so give the ship mappings their own PlayerMappableKeySettings names, or read the user's keys [design choice].
* Leave Mouse2D (IA_Rotate) and Escape unmapped in IMC_Airship, so camera look and the pause menu keep working.

| What | Code | With the ship possessed | Guard |
|---|---|---|---|
| Move (WASD) | `AMyPlayerController2::Move` returns on `!GetCharacter()` (MyPlayerController2.cpp:225-253) | nothing (no crash) | ship binds its own throttle/steer IAs in `SetupPlayerInputComponent` (created in `APawn::PawnClientRestart`, Eng/Private/Pawn.cpp:496-512) |
| Rotate (mouse) | `GetPawn()->AddControllerYawInput/PitchInput` (:260-274) | rotates the PC control rotation, which is what the ship camera needs | ship `USpringArmComponent` with `bUsePawnControlRotation` (BP_MyCharMech does the same: arm 355.7, target offset z 99.4, lag 17.5 / rot lag 4, decoded). `OnPossess` sets control rotation to the ship's rotation (Eng/Private/PlayerController.cpp:893) |
| Jump | `Cast<AMyCharBase>(GetPawn())` (:276-284); IA_Jump unset | nothing | none |
| Q / E | PC2: `MenuButtonPressed` (attribute/spell menus, :149-150, :286-289); old PC: camera yaw ±1 (MyPlayerController.cpp:74-75, 232-240) | PC2: the menus still open (they bind to the PlayerState) | map Q/E in IMC_Airship only if the ship uses them (they get consumed) |
| Ability input (LMB/RMB/Shift/Space) | PC2 → PlayerState ASC → abilities on the **pilot** avatar (:355-376) | gun/beam: `UAT_SendMouseCursorData::Activate` dereferences `GetAvatarActor()->GetInstigatorController()` (AT_SendMouseCursorData.cpp:18, :23-26), which is null → **crash**; boost/hover: unpossessed CMC | (1) IMC_Airship consumes those keys; (2) server cancels the pilot's active non-passive abilities on boarding (copy `CancelActiveAbilities`, MyGameMode.cpp:73-105, anonymous namespace = not callable); (3) shared patch 3 |
| CursorTrace / AutoMove | commented out in both PCs (MyPlayerController2.cpp:71-72, MyPlayerController.cpp:51-52) | nothing | none |
| PC2 Tick aim sweep | ignores `GetPawn()` only (MyPlayerController2.cpp:90-108); `TargetLocation` public (h:157-158); debug arrow from pawn (:110) | the sweep can hit the pilot attached at the helm | pilot capsule + mesh `NoCollision` while aboard. Cannons send the client's `TargetLocation` in their Server RPC (on the server, remote PCs deproject garbage) |
| Old `AMyPlayerController` | `GetCharacter()->` unchecked in Move (:220-230), ReleasedFunc LMB (:320), AutoMove (:243-256) | crash, but only if it were the play PC | n/a (replay spectator only) |
| HUD overlay | `AMyHUD::InitOverlay` idempotent (MyHUD.cpp:33-36), bound to the PlayerState ASC (:37-53); called from AMyCharPlayer PossessedBy/OnRep_PlayerState (MyCharPlayer.cpp:274-281, 334-339) | keeps showing the **pilot's** health/mana/XP (correct) | ship health = its own widget (WidgetComponent or HUD widget bound to the ship ASC) |
| Damage numbers dealt by the ship | Props.SourceController = ship ActorInfo PC (needs refresh), SourceCharacter = null, TargetCharacter = enemy → PC2 path (MyAttributeSet.cpp:99-127) | work once `RefreshAbilityActorInfo` has run after possession | Refresh in PossessedBy/UnPossessed/NotifyControllerChanged |
| Damage numbers on the ship | TargetCharacter null → `ShowDamageNumber_2` returns (MyPlayerController2.cpp:514) | none shown | optional shared change: `ShowDamageNumber_2(float, AActor*, …)` using actor bounds |
| Sentinel damage numbers from cannons | `IsSentinelDamageInstigator` walks the owner chain (MyPlayerController2.cpp:539-552); the ship's owner = PC after possession (Eng/Private/Pawn.cpp:673) | work | none |
| FOV setting / hit-impact PP | `FindComponentByClass<UCameraComponent>()` on the new pawn (MyPlayerController2.cpp:432-458, 644-646) | apply to the ship camera | none |
| Minimap | `PlayerController->GetPawn()` / `PlayerState->GetPawn()` (MyHexMinimapWidget.cpp:86-92, 114-128; MyHexMinimapSubsystem.cpp:404-406) | follows the ship (yaw from ship) | none |
| Ranking (AMyGameState) | only `AMyCharPlayer::BaseChange` → `PS->SetCurrentPlatform` (MyCharPlayer.cpp:284-301; MyPlayerState.cpp:27-49 → `UpdatePlayerRanking` → `ActivatePlatformsUpTo`, MyGameState.cpp:42-82, 103) | rank frozen while flying | ship (server, timer ~0.5 s): trace down from the hull, if `AMyHexPlatform` hit → `PS->SetCurrentPlatform(Platform)` (public, MyPlayerState.h:68) |
| Hex platform / bridge / path logic | `PC->GetPawn()` locations and `GetMovementBaseActor` (MyHexPlatform.cpp:515-555, 630-650; MyHexBridgeSubsystem.cpp:1183-1193, 4786-4795; MyHexPathSpawner.cpp:262-272) | follows the ship. A non-Character counts as "on" a platform within `LandingTolerance` 150 cm below (MyHexPlatform.cpp:543-555, h:640) | none |
| Burrower | `PS->GetPawn()` + `IsLivingTarget(Pawn, bOnlyCombatPawns=true)` (BurrowerSpawnSubsystem.cpp:228-245; BurrowerCharacter.cpp:349-364) | the ship has the combat interface, so the Burrower **retargets the ship** and follows it at -150 cm. The pawn change counts as a respawn: countdown ≥ PlayerRespawnGrace | accept, or (shared) skip `AAirshipPawn` in IsLivingTarget |
| Sentinels | `GatherPlayerTargets` = `PS->GetPawn()` (MechSentinelSwarmSubsystem.cpp:424-448) | **the ship is attacked instead of the pilot**; damage lands in the ship's UMyAttributeSet | ship `IsDead` → skipped after death; `UMechSentinelObstacleComponent` so they don't fly into the hull |
| Edge fog RVT | `AMyCharPlayer::RefreshEdgeFogTimer` stops when not locally controlled (MyCharPlayer.cpp:631-656); `UpdateEdgeFogVolumes` early-outs (:658-663). The fog cube `EdgeFogVolume` on BP_MyCharMech is `bOnlyOwnerSee`, scale (120,120,12) at z -220 (decoded); the owner list is the owner chain at proxy creation (Eng/Private/PrimitiveSceneProxyDesc.cpp:147-153) | RVT volumes stop following; the pilot's cube is no longer seen through the ship view | ship carries its own `EdgeFogVolume` cube (M_EdgeFogVolume, OnlyOwnerSee) + a copy of the 40-line follow logic (tag `EdgeFogRVT`, snap 2048, Z range -2000..8200) |
| Pilot `GetLevel` / XP functions | `GetPlayerState<AMyPlayerState>()->` unchecked (MyCharPlayer.cpp:379-424; 14 such sites in Private/) | crash if called while unpossessed (GA_Projectile `Execute_GetLevel`, GA_Projectile.cpp:29; XP) | IMC masking + ability cancel + shared patch 2 |
| Exit = full heal | `PossessedBy` → `bRespawned` → `InitAbilitySystemAfterRespawn` (MyCharPlayer.cpp:313-320, 359-376) | Health/Mana refilled on every exit | ship saves the pilot's Health/Mana on boarding and restores them (server, `SetNumericAttributeBase`) right after `Possess(Pilot)`. Shared alternative: a per-pawn "already initialised" flag |
| Player death / respawn | GameMode watches the **character** (`SetPlayerDefaults` → `WatchPlayerPawn`, MyGameMode.cpp:107-112, 140-165). `OnPlayerPawnDied` uses `DeadPawn->GetController()` (:184-193). `OnPlayerPawnDestroyed` returns when `Controller->GetPawn()` is another pawn (:213-216) | character dying or destroyed while unpossessed → **no respawn** (stuck); the ship is not watched | re-possess the character **before** any damage/Die on it; never destroy it while aboard; on ship death eject first (section 4) |
| Logout while piloting | `APlayerController::Destroyed` → `PawnLeavingGame` destroys the **ship** (Eng/Private/PlayerController.cpp:1572-1579, 1633-1641), before `Logout` (:1675 → Controller.cpp:603 → GameModeBase.cpp:1056) | ship gone, the pilot is left unpossessed forever | ship `EndPlay(Destroyed)`: if the pilot is still attached and their PC is gone or being destroyed → `Pilot->Destroy()`; else eject + re-possess |
| Pilot relevancy | attached actors use the parent's relevancy only for a skeletal-mesh parent or the same owner (Eng/Private/ActorReplication.cpp:388-405) | the pilot can drop out of far clients | `Pilot->bAlwaysRelevant = true` while aboard (restore after) [unverified that the flag change is picked up mid-life] |

---

## 4. Boarding and exiting

### 4.1 How the client asks

| Option | Shared edits | Notes |
|---|---|---|
| **A. `UAirshipSubsystem` (UWorldSubsystem) adds a replicated `UAirshipPilotComponent` to every PlayerController** (recommended) | none | Server: bind `FGameModeEvents::GameModePostLoginEvent` (Eng/Classes/GameFramework/GameModeBase.h:635, 655; broadcast in `AGameModeBase::OnPostLogin`, Eng/Private/GameModeBase.cpp:1042-1047) + iterate existing PCs in `OnWorldBeginPlay` (the PIE host). `NewObject<UAirshipPilotComponent>(PC)`, `SetIsReplicated(true)`, `RegisterComponent()`; runtime replicated components are handled by `AActor::UpdateReplicatedComponent` (Eng/Private/Actor.cpp:3856-3890). The PC replicates only to its owner, which is all we need. The owning client's component pushes its own `UEnhancedInputComponent` (`PC->PushInputComponent`) + adds `IMC_AirshipOnFoot` (F → `IA_AirshipInteract`, priority 1). `UFUNCTION(Server, Reliable) Server_RequestInteract()`: the server picks the nearest free ship within BoardRadius of the PC's pawn (board) or, if the pawn is an `AAirshipPawn`, exits. Seamless travel re-login path [unverified] |
| B. Add to `AMyPlayerController2` | ~20 lines in a shared class | `UPROPERTY IA_Interact` + bind + `Server_RequestInteract`. Simplest to debug, but touches Talal's PC |
| C. `GA_BoardAirship` on the player ASC (Input.Interact) | assets: DA_MyInputCofig +1 entry, IMC_PlayerMappings +F, BP_MyCharMech StartupAbilities +1 | reuses PC2 → ASC routing (Held → TryActivateAbility, MyAbilitySystemComponent.cpp:168-182), ServerOnly ability. Binary asset edits risk conflicts with Talal's tree |

Exit can also be `UFUNCTION(Server, Reliable) Server_RequestExit()` on the ship itself. The ship is owned by the PC once possessed (Pawn.cpp:673), so its RPCs work. With option A, the same component handles both.

### 4.2 Flow (all server unless noted)

**Board** (`AAirshipPawn::BoardPilot(AMyCharPlayer* Pilot, APlayerController* PC)`):
1. Validate:
   * the pawn is `AMyCharPlayer`, not `IsDead`, has a PlayerState
   * the ship is alive and has no pilot
   * distance(pilot, `HelmPoint`) ≤ BoardRadius (≈ 400 cm).
2. Cancel the pilot's active non-passive abilities (pattern from MyGameMode.cpp:73-105).
3. Save the pilot's Health/Mana (exit heal, section 3).
4. `Pilot->GetCharacterMovement()->StopMovementImmediately(); DisableMovement();`.
5. Capsule + mesh `NoCollision`. Save the old values, and keep them off so the capsule doesn't touch the hull physics.
6. `Pilot->AttachToActor(this, FAttachmentTransformRules::SnapToTargetNotIncludingScale)`:
   * this rule doesn't weld (Eng/Private/EngineTypes.cpp:18, weld = false)
   * then `SetActorRelativeTransform(HelmPoint->GetRelativeTransform())`
   * Attach to the ship's **root**: attachment replication assumes the parent's root component (Eng/Private/ActorReplication.cpp:511-512). HelmPoint is only a marker on the root.
7. `Pilot->bAlwaysRelevant = true`; replicated `Pilot` pointer on the ship (anim/UI).
8. `PC->Possess(this)`:
   * `APlayerController::OnPossess` unpossesses the character (Eng/Private/PlayerController.cpp:873-918)
   * `APawn::UnPossessed` clears the character's PlayerState and owner (Pawn.cpp:713-721)
   * `ClientRestart` → the client builds the ship's input component.
9. `RefreshAbilityActorInfo()`; zero the controls.
10. Client (`NotifyControllerChanged`, Pawn.cpp:740; called from OnRep_Controller :643): add `IMC_Airship` (priority 2) when locally controlled, remove it when control is lost (keep a weak pointer to the subsystem used).

**Exit** (`UnboardPilot(bool bEject)`):
1. Pick an exit spot: HelmPoint + side offset, a trace down onto the deck or the ground.
2. Detach (KeepWorld), restore collision, `SetMovementMode(MOVE_Falling)`, restore `bAlwaysRelevant`.
3. `PC->Possess(Pilot)`. Then restore the saved Health/Mana immediately (vitals were refilled, MyCharPlayer.cpp:366-375).
4. Eject: `Pilot->LaunchCharacter(Up * 1200 + Side * 600, true, true)` [numbers to tune].
5. The ship keeps simulating with zero input: the unmanned behaviour (hover-hold or slow sink) is a design choice.

**Ship dies with the pilot aboard:**
1. `Die` → next tick → `UnboardPilot(bEject = true)`. Not inside the GE callback: the Burrower notes say handlers must not spawn or destroy there.
2. Optionally damage the pilot after the re-possess: ship ASC as source, `ApplyGameplayEffectSpecToTarget(GE_ProjectileDamage, SetByCaller = EjectDamage)` to the pilot. A fatal hit → `AMyCharPlayer::Die`, and the GameMode respawns normally because the controller is valid again (MyGameMode.cpp:184-193).
3. Then the wreck: replicated `bShipDead` → anim bIsDead → Control Rig physics.
   * The root keeps simulating with gravity (or gets a strong downward pull).
   * Lift is off; cannons lose their constraints in the rig.
   * `SetLifeSpan(WreckLifeSpan)` → Destroy, with no pilot left aboard.

**Size of the pilot** (BP_MyCharMech, decoded):

| Value | Number |
|---|---|
| capsule radius | 34 (engine default, Eng/Private/Character.cpp:78) |
| capsule half height | 70.79, so 141.6 cm tall |
| mesh offset | (-2.1, 8.0, -72.1) |
| spring arm | 355.7 cm, target offset z 99.4 |

Helm and wheel for this mech:
* HelmPoint (capsule centre) = deck + 71 cm.
* Wheel hub at ≈ deck + 95-100 cm (chest), wheel ≈ 100-120 cm across.
* Wheel plane ≈ 50 cm in front of the capsule axis (radius 34 + ~15 cm hand room).

For scale, SM_Airship ApproxSize is 5189 × 2386 × 1698 cm (asset registry tag), 69,210 tris, so the ship is about 37 mech-heights long. A real-sized wheel will look tiny on the hull; that is a design call for the rig/art pass.

StartupMap already has a static `StaticMeshActor_4` with SM_Airship at (13340, 8972.4, 893.2), scale 1 (StartupMap.umap export 99).

---

## 5. Existing VFX to reuse

| Use | Asset (committed) | Notes |
|---|---|---|
| Thruster jet (scaled by thrust) | `/Game/NiagaraExamples/FX_Misc/NS_Boost` (951 KB) | User params: `Flame Color`, `Flame Material`, `Flame Scale`, `Spawn Rate`, `Lifetime Scale`, `Float_Sprite Size`, `B_Lifetime` → drive `Flame Scale` / `Spawn Rate` from thrust |
| Thruster mesh flame | `/Game/Assets/Effects/MyThruster/Thruster_ftl` (StaticMesh, 20 MB) + `M_Thruster`, `M_Fire`, `SM_Thruster` | what the mech's jets use (`JetPackMeshComponent1.StaticMesh`, decoded). The mech's `NS_Thrusters` component has no Asset saved on its template |
| Thruster ignition / muzzle flash | `/Game/Assets/Effects/MyThruster/NS_ThursterFlash`, `/Game/NiagaraExamples/FX_Weapons/MuzzleFlashes/NS_MuzzleFlash`, `NS_GunWispySmoke` | `User.Global Scale`, `Flash Base Color`, `Smoke Color`, `Use Smoke`, `Use Sparks`, `Use Bullet Shell` (set false for cannons) |
| Cannonball trail / body | `/Game/Assets/Effects/Projectiles/FireBolt/NS_Fireball`, `NS_Fire_1..4`, `/Game/Assets/Effects/Combat/Trail/NS_CombatTrail` | no User params found |
| Impact / explosion | `/Game/Assets/Effects/Projectiles/FireExplosion/NS_FireExplosion`, `NS_FireExplosion1`; `/Game/VFXASandbox/VFX/01_FireExplosion/PS_Fire_Explosion_Niagara` (7.6 MB); `/Game/Assets/Effects/Combat/NS_CombatImpact`; `/Game/Assets/Effects/AirExplosion/AirExplo_ftc` (StaticMesh 39 MB) | |
| Burning / damaged / wreck | `/Game/Assets/Effects/Fire/NS_Fire`, `/Game/NiagaraExamples/FX_Misc/NS_Fire` (light + flame params), `/Game/Assets/MyPlatform/VFX/NS_HexDust` | |

How the project spawns FX today:
* Jets: `State.Boosting` tag event → `InitJets` / `StopJets` (BlueprintImplementableEvent, MyCharPlayer.cpp:100-118). BP_MyCharMech implements them with `NiagaraComponent.ResetSystem` / `SetVariableFloat` (imports). GA_BoostBP and GA_JumpHover reference no FX, only `GE_HoverCost`.
* Gun: muzzle FX are components on BP_MyCharMech (`NS_GunShoot`, `NS_GunShoot1` = NS_MuzzleFlash; `NS_GunWispySmoke(1)`), toggled by the StartFiring/StopFiring events. Hits come from the GameplayCue `GC_BurstActor_GunShoot` / `GC_GunShootLooping` (PS_06_Flipbook_Sprites_my) and the Niagara data channel.
* Projectile: `ExecuteGameplayCue(GameplayCue.FireballBurst)` (GA_Projectile.cpp:53) + `SpawnSystemAtLocation(BurstNiagaraSystem)` on overlap (MyProjectile.cpp:46).

For the ship:
* Thruster `UNiagaraComponent`s on mesh sockets, `SetVariableFloat("User.Thrust", x)` every frame **on every machine**, from replicated control values (Burrower rule: cosmetics computed locally).
* Cannon muzzle + impact: an unreliable multicast, or a GameplayCue from the ship ASC (cues are under `/Game/Level/GAS/GameplayCues`, cooked via DefaultGame.ini:142).

**AMyProjectile for cannonballs: don't reuse as is.** Its overlap handler (MyProjectile.cpp:40-48):
* damages **any** IAbilitySystemInterface actor, including its own ship and the attached pilot (no owner or instigator filter)
* runs on clients too: the client-side apply fails the GAS authority check (GAS/Private/AbilitySystemComponent.cpp:455-458), and the client can't Destroy a replicated actor (Eng/Private/LevelActor.cpp:877)
* has homing on and gravity 0 (:25-28)
* `OnSphereBeginOverlapCallback` is a non-virtual UFUNCTION bound in BeginPlay.

So write a new `AAirshipCannonball`:
* server-only hit; ignores the owner ship, its attached actors, and passengers
* gravity on, no homing
* damage spec handle made from the ship ASC with GE_ProjectileDamage (ExecCalc_Damage, SetByCaller)
* optional splash via an overlap sphere → ASC actors
* sentinels: each tick (next-tick timer) `ApplyDamageToSentinelsInSweep(this, Ship, PrevLoc, Loc, Radius, Damage, …)`, and `ApplyDamageToSentinelsInCapsule` on explode.

---

## 6. Build, plugins, style, config

* **Aura.Build.cs** (Source/Aura/Aura.Build.cs) already has:
  * Public: Core, CoreUObject, Engine, InputCore, EnhancedInput, GameplayAbilities, NavigationSystem, UMG, GameplayTasks, Niagara, OnlineSubsystem(+Utils, Steam), Mass*
  * Private: GameplayTags, NetCore, PCG, ApplicationCore, DeveloperSettings, GeometryCollectionEngine, Chaos, Slate(Core), EngineSettings, CoreOnline, AIModule
  * So **no change** is needed for the ship.
  * Add `"ControlRig"` (+ `"RigVM"`) only if C++ touches `UControlRig` directly [unverified module names for 5.8]. The Burrower drives the rig only through AnimInstance properties (Docs/Burrower/cpp_notes.md "ControlRig is not needed").
* **Aura.uproject** already enables ControlRigDynamics, ControlRigPhysics (Engine/Plugins/Experimental/ControlRigPhysics/ControlRigPhysics.uplugin), GameplayAbilities, MotionWarping, MassGameplay, OnlineSubsystemSteam/EOS, SteamSockets. **No change.**
* **Physics** (`DefaultEngine.ini` has no `[/Script/Engine.PhysicsSettings]`), so these are the engine defaults:

  | Setting | Default | Where |
  |---|---|---|
  | `MaxPhysicsDeltaTime` | 1/30 | Eng/Private/PhysicsEngine/PhysicsSettings.cpp:22 |
  | `bSubstepping` | false | :23 |
  | `bTickPhysicsAsync` | false | :24 |
  | `AsyncFixedTimeStepSize` | 1/30 | :25 |
  | `MaxSubstepDeltaTime` | 1/60 | :26 |
  | `MaxSubsteps` | 6 | :27 |
  | `bEnablePhysicsPrediction` | false | Eng/Classes/PhysicsEngine/PhysicsSettings.h:233 |
  | DefaultGravityZ | -980 | BaseEngine.ini |

  * Below 30 fps the simulated time slows (the dt is clamped).
  * Turning on substepping or async physics project-wide also changes the GC pillar breaks, the bridge collapse physics and the GC props. **Recommend v1 without ini changes**: forces from Tick via `AddForce(…, bAccelChange = true)` / `AddForceAtLocation` / `AddTorqueInRadians(…, bAccelChange = true)` (Eng/Classes/Components/PrimitiveComponent.h:1759, 1770, 1802).
  * Use `AsyncPhysicsTickActor` / `bAsyncPhysicsTickEnabled` (Eng/Classes/GameFramework/Actor.h:2930, 699) only if async physics is ever enabled.
* **Physics replication**: `EPhysicsReplicationMode` {Default, PredictiveInterpolation, Resimulation (WIP), None} (Eng/Classes/Engine/EngineTypes.h:3614-3634); `AActor::SetPhysicsReplicationMode` (Actor.h:924). PredictiveInterpolation is "not viable for AutonomousProxy if input latency is of concern" (:3619-3623).
  * v1: Default. The server applies forces from the replicated controls, and the owning client applies the same forces locally (cheap prediction, corrected by replication).
  * Resimulation needs Physics Prediction on [unverified quality].
  * A simulating root replicates through `ReplicatedMovement.bRepPhysics` (Eng/Private/ActorReplication.cpp:426-480).
* **Collision**: `DefaultEngine.ini` has no `[/Script/Engine.CollisionProfile]` (no custom channels or profiles; sections at lines 3-137). Set every response in the ctor (Burrower pattern, gas_patterns.md section 9). Ship needs:
  * **Hull physics body (root)**: QueryAndPhysics, object WorldDynamic or PhysicsBody.
    * Blocks: WorldStatic, WorldDynamic, PhysicsBody, Vehicle, Pawn (so players can stand on deck), Visibility (aim / Electrocute / Shards / ranking trace).
    * Overlap: projectiles' sphere type [check the projectile BP profile].
    * Camera Ignore (else every pilot spring arm collapses).
  * **Skeletal mesh (visual, Control Rig)**: QueryOnly or NoCollision; don't let it carry physics while alive.
  * **Pilot**: NoCollision while aboard.
* **Style of the new code** (Burrower / MechSwarm / Hex, not the older Aura classes):
  * files in `Public/<Feature>/` + `Private/<Feature>/` (here `Airship/`)
  * class doc block `/** … */` above `UCLASS()` explaining the design (BurrowerCharacter.h:13-34)
  * `/** */` on every UPROPERTY, units in the text
  * `Category = "Burrower|Rotor"` style categories with spaces around `=`; `meta = (ClampMin = "0", ForceUnits = "cm")` (GA_GunShoot.h:66)
  * `TObjectPtr<>` members
  * `// -----` section headers in headers, `// =====` in .cpp
  * `DEFINE_LOG_CATEGORY_STATIC`
  * **named** (not anonymous) namespaces for file-local helpers, because of the unity build (BurrowerSpawnSubsystem.cpp:458, BurrowerCharacter.cpp:33; GA_GunShoot.cpp:24 `MechSwarm::GunShootPrivate`)
  * Allman braces, tabs
  * the first line `// Fill out your copyright notice…` (Burrower) or `// <Feature> - <what>` (MechSwarm). MechSwarm also uses `#include UE_INLINE_GENERATED_CPP_BY_NAME(...)`.
  * Server-only functions say "Server." in their doc comment.

---

## 7. Content conventions

* Gameplay BPs and data:
  * `/Game/Level/...`: BP_MyGameMode, BP_MyPlayerState, MechChar/BP_MyCharMech, PlayerInput/IA_*, IMC_*, Data/DA_MyInputCofig, `GAS/GameplayAbilities/GA_<Name>/GA_<Name>BP`, `GAS/GameplayEffects/GE_*`, `GAS/GameplayCues/GC_*`, `UI/...`
  * Art: `/Game/Assets/...` (Characters/Mech, Effects/*, MyPlatform/*).
  * Features with their own folder: `/Game/Assets/Enemies/Burrower/{BP_Burrower, SK_Burrower, SKEL_Burrower, PA_Burrower, ABP_Burrower, CR_Burrower, M_Burrower_Grey}`; `/Game/MechSentinel/{Data, GAS, FX, Meshes, Materials, Demo}`.
* `/Game/Assets/MyShip` (committed b895169): `SM_Airship`, `M_Airship`, `T_Airship_ComicLines`, `T_Airship_ComicMask`.
* Proposed:

  | Asset | Purpose |
  |---|---|
  | `/Game/Assets/MyShip/SK_Airship`, `SKEL_Airship`, `PA_Airship` | the rigged mesh |
  | `ABP_Airship` (parent `UAirshipAnimInstance`), `CR_Airship` | animation and rig |
  | `BP_AirshipPawn` (parent `AAirshipPawn`) | the pawn |
  | `SK_PirateWheel` / `SM_PirateCannon` | or parts of SK_Airship |
  | `Input/IMC_Airship`, `IMC_AirshipOnFoot`, `IA_AirshipThrottle`, `IA_AirshipSteer`, `IA_AirshipLift`, `IA_AirshipFire`, `IA_AirshipInteract` | input |
  | `GAS/` (only if C++ GEs aren't used) | effects |
  | `FX/NS_AirshipThruster` (copy of NS_Boost with a `User.Thrust` param) | thruster jets |
  | `BP_AirshipCannonball` | cannonball |

* Cook: add `+DirectoriesToAlwaysCook=(Path="/Game/Assets/MyShip")` if the ship is only referenced from settings or console. A placed BP_AirshipPawn in StartupMap gets cooked through the map.

---

## 8. Recommended classes

| Class | Files | Responsibilities |
|---|---|---|
| `AAirshipPawn` : APawn, IAbilitySystemInterface, IMyCombatInterface | `Public/Airship/AirshipPawn.h`, `Private/Airship/AirshipPawn.cpp` | Components: `HullBody` root (UStaticMeshComponent, simplified hull collision, simulate physics, mass override); `Mesh` (USkeletalMeshComponent, `UAirshipAnimInstance`, kinematic); `HelmPoint`, 4 `CannonMuzzle_*`, 4 `ThrusterPoint_*`, 2 `FanPoint_*` (scene markers on the root, used for forces and spawns; mesh sockets aren't refreshed on a server that doesn't render, per the Burrower notes); `CameraBoom` + `Camera`; `ThrusterFX[4]` / `FanFX[2]` UNiagaraComponents; `EdgeFogVolume` cube; `UMechSentinelObstacleComponent`; `UMyAbilitySystemComponent` + `UMyAttributeSet`. Logic: replicated controls (`FAirshipControls` throttle/lift/steer as int8, from an unreliable Server RPC at ~30 Hz), board/unboard/eject, Die / death multicast / OnRep, cannons (Server_Fire(aim) → spawn cannonballs, per-cannon cooldown), ranking platform update, edge fog follow (local), console helpers. Replication: `bAlwaysRelevant`, `SetReplicatingMovement(true)`, `SetNetUpdateFrequency(60)` [tune] |
| `UAirshipFlightComponent` : UActorComponent (optional split) | `Public/Airship/AirshipFlightComponent.h/.cpp` | flight math: 4 lift forces at the thruster points (hover PID on altitude/vertical speed + throttle), 2 rear vectoring fans (forward thrust + yaw torque from fan angle), upright stabilisation torque, drag/damping; runs on server + owning client; outputs per-thruster thrust/angle for anim and FX |
| `UAirshipAnimInstance` : UAnimInstance | `Public/Airship/AirshipAnimInstance.h/.cpp` | Burrower thread-safe pattern; pins for CR_Airship: fan yaw/spin, thruster pitch/thrust, wheel angle (from steer, smoothed), cannon recoil impulses, speed, bIsDead/DeathTime (CR physics on) |
| `UAirshipPilotComponent` : UActorComponent (replicated, on the PC) | `Public/Airship/AirshipPilotComponent.h/.cpp` | owning client: pushes a UEnhancedInputComponent + `IMC_AirshipOnFoot`, binds `IA_AirshipInteract` → `Server_RequestInteract()`; server: nearest-ship lookup through the subsystem, calls `AAirshipPawn::BoardPilot/UnboardPilot`; optional UI prompt "Press F" when near a free ship (client-side distance check) |
| `UAirshipSubsystem` : UWorldSubsystem | `Public/Airship/AirshipSubsystem.h/.cpp` | server: adds the pilot component on PostLogin (+ existing PCs); ship registry (Register/Unregister from ship BeginPlay/EndPlay); console commands `Aura.Airship.*` |
| `UAirshipSettings` : UDeveloperSettings (header only) | `Public/Airship/AirshipSettings.h` | BoardRadius, interact IMC/IA soft refs, AirshipClass (spawn cmd), bAddPilotComponent |
| `AAirshipCannonball` : AActor | `Public/Airship/AirshipCannonball.h/.cpp` | replicated projectile, gravity, server-only hit and splash, ignores its ship, passengers and pilot, damage spec handle from the ship ASC, sentinel sweep, impact FX multicast |
| `AirshipTags` (namespace) | `Public/Airship/AirshipTags.h/.cpp` | native tags if needed (e.g. `State.Airship.Piloting` as a loose tag on the pilot ASC for BP checks) |

Shared-code changes, smallest set:
1. `UGA_GunShoot::MyFunc` patch (needed for the gun to hurt ships).
2. UMyAttributeSet IncomingXP null guard (crash guard).
3. AT_SendMouseCursorData controller null guard (crash guard).

Optional:
* the IsDead early-out in PostGameplayEffectExecute
* `ShowDamageNumber_2(AActor*)`
* the Burrower ignoring ships.

---

## 9. Open points / unverified

* DA_MyInputCofig IA → tag pairing was read as strings, not as decoded structs.
* The projectile BP's sphere collision profile (decides the ship's overlap response for projectiles) was not decoded.
* Electrocute/Shards damage GEs (BP) were not decoded. Assumed to target UMyAttributeSet like the others.
* Seamless-travel login path for the subsystem's component hook.
* `bAlwaysRelevant` toggled at runtime on the pilot; attachment replication to a non-root component.
* A client-side force "prediction" with Default physics replication: feel to be tested in PIE (listen server + 1 client).
* CMC based movement for passengers walking on a simulating hull is likely jittery. Passengers are not in scope for v1 (pilot only).
