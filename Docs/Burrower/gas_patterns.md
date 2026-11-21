# Burrower: how the project's character / GAS / damage / death code works, and how ABurrowerCharacter fits in

Source read: clone `/home/claude/AuraRedo2` (branch `claude/project-thread-78otz4`, HEAD 063fdc5). MyCharBase, MyEnemyChar and
MyAttributeSet match the copies staged from the user's machine (`/mnt/user-data/uploads/AuraRedo3`), checked with `diff -w`.
Line numbers are per file. `Content/` in the clone holds only Git LFS pointers (130-byte files), so **Blueprint graphs
(GA_BeamBP, GA_GunShootBP, BP_GoblinSpear, DA_CharClassInfo, BP_MyGameMode, WBP_HealthBar) could not be read**. No engine
headers for Engine/GameplayAbilities/UMG are in this container. Engine behaviour that comes from memory, not from a header I
read, is marked **[unverified]**.

---

## 0. Short answer / recommendation

* **Derive from `AMyEnemyChar`** (user decision, and it fits). That gives:
  * the ASC (`UMyAbilitySystemComponent`, replicated, Mixed mode)
  * `UMyAttributeSet`
  * `InitAbilityActorInfo(this,this)` on every machine
  * the health-bar delegates
  * `LifeSpan`
  * the XP reward on kill
  * the `IMyCombatInterface` death path that every player ability already uses.
* **Attribute set: `UMyAttributeSet`, no new set.** `UExecCalc_Damage` captures the target's `UMyAttributeSet::Armor` and
  writes `UMyAttributeSet::IncomingDamage`. Only `UMyAttributeSet::PostGameplayEffectExecute` turns IncomingDamage into
  Health, Die(), XP and damage numbers. A different set would make every player ability do nothing.
* **Init:**
  * on the server, after `Super::BeginPlay()`, apply Primary → Secondary → Vital GEs at `CharacterLevel`
  * C++ cannot call `UMyBPFuncLib::InitializeEnemyAttributes`, because it is private (see 2.2)
  * code in section 9.
* **What to override:**
  * the constructor (collision, unused base components, CharacterClass/Level, health bar)
  * `BeginPlay` (widget guard + attribute init + flying)
  * `Die` (once only)
  * `MulticastHandleDeath_Implementation` (Control Rig ragdoll instead of the base's whole-mesh SetSimulatePhysics, stop
    movement, kill the corpse's query collision)
  * nothing in the base classes needs to change.
* **To be hit:**
  * the mesh (physics asset bodies) must **Block `ECC_Visibility`** and **GenerateOverlapEvents = true**, with Overlap
    toward WorldDynamic
  * the actor already implements `IAbilitySystemInterface` and `IMyCombatInterface`, and is an `AMyCharBase`
  * the rotor box must ignore Visibility, Camera and WorldDynamic, or it swallows aim traces and projectiles.

---

## 1. ASC and attribute set: who owns them, when InitAbilityActorInfo runs

| | Enemy (`AMyEnemyChar`) | Player (`AMyCharPlayer`) |
|---|---|---|
| ASC / AttributeSet created | `AMyEnemyChar::AMyEnemyChar()` MyEnemyChar.cpp:18-19: `CreateDefaultSubobject<UMyAbilitySystemComponent>("AbilitySystemComponent")`, `CreateDefaultSubobject<UMyAttributeSet>("AttributeSet")` into the base members `AMyCharBase::MyAbilitySystemComponent` / `MyAttributeSet` (protected, MyCharBase.h:64-68) | On `AMyPlayerState` (`MyAbilitySystemComponent`, `MyAttributeSet`); pawn pointers set in `PossessedBy` (server, MyCharPlayer.cpp:303) and `OnRep_PlayerState` (client, :241) |
| InitAbilityActorInfo | `AMyEnemyChar::BeginPlay` MyEnemyChar.cpp:30, **on server and clients**: `InitAbilityActorInfo(this, this)` then `GiveStartupAbilities()` | `InitAbilityActorInfo(PlayerState, Pawn)`, re-run for each respawned pawn |
| Replication | `UMyAbilitySystemComponent()` ctor: `SetIsReplicated(true)`, `ReplicationMode = Mixed` (MyAbilitySystemComponent.cpp:16-21). The attribute set is a default subobject of the actor, so the ASC picks it up by itself **[unverified: engine behaviour, UAbilitySystemComponent::InitializeComponent]** and replicates it | same |
| GetAbilitySystemComponent | `AMyCharBase::GetAbilitySystemComponent()` returns `MyAbilitySystemComponent` (IAbilitySystemInterface) | same |

The burrower inherits all of this. It needs no ASC code of its own beyond the attribute init.

* `GiveStartupAbilities()` also runs on clients (MyEnemyChar.cpp:31). GAS refuses GiveAbility on a client and logs an error.
* So leave `StartupAbilities` empty on the burrower (it needs no abilities). Above all, do not give it GA_HitReact (see 4.4).

Attribute notes (`UMyAttributeSet`):
* Vital: Health, MaxHealth, Mana, MaxMana.
* Primary: Strength, Agility, Intelligence.
* Secondary: HealthRegen, ManaRegen, MagicResist, Armor, AttackSpeed, MoveSpeed, TurnSpeed, AttackDamage, CritChance.
* Meta: IncomingDamage, IncomingXP.
* `MoveSpeed` is **not in `GetLifetimeReplicatedProps`** (MyAttributeSet.cpp:210-229), so clients never get it. Do not
  drive client-side visuals from it. Driving server movement from it is fine.
* `OnRep_AttackDamage` / `OnRep_CritChance` notify TurnSpeed (copy-paste, :307-315). This does not matter for the burrower.
* `PreAttributeChange` clamps Health to [0, MaxHealth]. That is why Vital has to be applied after Secondary (see 2).

---

## 2. Default attributes

### 2.1 Project pattern
* Enemies do **not** initialise attributes in C++. MyEnemyChar.cpp:32 only has the comment
  `//InitAttrToBeCalledInBPCharClassToBeDifferentForEachEnemy`.
* The enemy Blueprints call `UMyBPFuncLib::InitializeEnemyAttributes(CharacterClass, ASC, CharacterLevel)`
  (MyBPFuncLib.cpp:77-95). I could not read those Blueprints, so I cannot say whether they gate this on authority.
* That function:
  * `Cast<AMyGameMode>(UGameplayStatics::GetGameMode(ASC))->DA_MyEnemyCharacterClassInfo` (**no null checks**: it
    crashes on a client, under a GameMode that is not AMyGameMode, or with the data asset unset)
  * `GetInfoForClass(Class).PrimaryAttributesEffect` (`checkf` that it is set)
  * then the asset's shared `SecondaryAttributesEffect` and `VitalAttributesEffect`
  * each one goes through `MakeOutgoingSpec(GE, Level, Ctx)` and `ApplyGameplayEffectSpecToSelf`, with
    `Ctx.AddInstigator(Avatar, Avatar)`.
* Data: `UDA_MyEnemyCharacterClassInfo` (DA_MyEnemyCharacterClassInfo.h) holds `TArray<FEnemyCharClassInfo>`, where each
  entry is {`ECharacterClass Class`, `PrimaryAttributesEffect`, `FScalableFloat XPReward`}, plus the shared Secondary and
  Vital GE. The asset is `/Game/Level/GAS/Data/DA_CharClassInfo` and is set on `BP_MyGameMode`.
* `ECharacterClass` = {Elemental, Warrior, Ranger}. Matching assets exist:
  `/Game/Level/GAS/GameplayEffects/AttributeEffects/Enemy/BP_PrimaryAttributesEffect_{Elemental,Warrior,Ranger}`,
  `.../BP_SecondaryAttributesEffect`, `.../BP_VitalAttributesEffect`, and the XP curve
  `/Game/Level/GAS/GameplayEffects/Curves/CT_XPRewardForEnemy`.
* The player pattern is the same, with effects on the character (`AMyCharPlayer::Primary/Secondary/VitalAttributesEffect`,
  MyCharPlayer.cpp:342-357). Per the comments at :364-365, Primary is an instant override and Secondary is infinite.

### 2.2 Why the burrower must do it itself
* `UMyBPFuncLib::InitializeEnemyAttributes` is declared at MyBPFuncLib.h:34. That is **above the first `public:`**
  (h:40), right after `GENERATED_BODY()` (h:22).
* `GENERATED_BODY()` in a UCLASS leaves access `private` **[unverified, standard UHT behaviour]**. So in C++ the function
  is private: BlueprintCallable, but `ABurrowerCharacter` cannot call it.
* Two options:
  * **recommended:** reimplement the same three applies in the burrower (section 9). This needs no change to shared code
    and adds null checks.
  * or move that declaration under `public:` in MyBPFuncLib.h. This is harmless for Blueprints.
* **Recommended init:**
  * use per-class `TSubclassOf<UGameplayEffect>` overrides on the burrower (Primary/Secondary/Vital)
  * when one is unset, fall back to the GameMode's class info, like the enemies do
  * apply them on the server only, after `Super::BeginPlay()` (that is when `InitAbilityActorInfo` has run), at
    `CharacterLevel`
  * order: Primary → Secondary → Vital.
* The burrower is probably much tougher than a goblin, so a dedicated `GE_BurrowerPrimary` (or a Vital/MaxHealth
  override) is the easy way to tune its health.
* Damage values to tune against:
  * `UGA_GunShoot::MyFunc` deals a hard-coded **1** per hit (GA_GunShoot.cpp:281)
  * GA_Projectile deals `Damage.GetValueAtLevel(abilityLevel)`
  * Beam and Shards are in Blueprints.

### 2.3 Defaults that are wrong for a new enemy
* `AMyCharBase::CharacterClass` has no initialiser (MyCharBase.h:42). `AMyEnemyChar::CharacterLevel` has none either
  (MyEnemyChar.h:59). UObject memory is zeroed, so a new subclass gets **Elemental, level 0**.
* Set `CharacterClass` and `CharacterLevel = 1` in the constructor.
* Level 0 into a curve-table GE or into `XPReward.GetValueAtLevel(0)` gives whatever the curve has at 0.

---

## 3. How player damage reaches a target (what the burrower needs in order to be hit)

### 3.1 Shared pipeline
1. The ability makes a spec from its own ASC: the damage GE (`GE_GunShootDamage`, `GE_ProjectileDamage`, `GE_BeamDamage`,
   `GE_ShardsDamage`, all Blueprints) with SetByCaller `MyTags::SetDamageByCaller` ("SetDamageByCaller") = damage.
2. `UExecCalc_Damage` (ExecCalc_Damage.cpp):
   * captures Target `Armor` and Source `CritChance` from `UMyAttributeSet`
   * `bIsBlocked = rand(0..100) < Armor`, `bIsCrit = rand < CritChance`. These are cosmetic only: the damage scaling is
     commented out.
   * writes `IncomingDamage` (Override) = SetByCaller.
   * **The target must own a `UMyAttributeSet`, otherwise nothing happens.**
3. `UMyAttributeSet::PostGameplayEffectExecute` (server, MyAttributeSet.cpp:47-130):
   * `Health -= IncomingDamage` (clamped).
   * If `NewHealth <= 0`:
     * `Cast<IMyCombatInterface>(TargetAvatar)->Die()` (:79)
     * then, **only if the target is an `AMyEnemyChar`**, `UMyBPFuncLib::GetXPRewardForCharacterClass(CharacterClass,
       CharacterLevel)` (:85), which `checkf`s `XPReward.IsValid()` and dereferences GameMode/DA with no null checks
     * then `SendGameplayEventToActor(SourceAvatar, Attribute.Meta.XP)` (the player's passive listener turns it into
       IncomingXP).
   * Otherwise: `TargetASC->TryActivateAbilitiesByTag(Ability.HitReact)` (:96).
   * Then damage numbers: `AMyPlayerController(2)::ShowDamageNumber(_2)(Damage, TargetCharacter, ...)` (:99-127). The
     number appears at capsule top + offset, so it shows at the head. That is fine.

### 3.2 Per ability: query and what the target needs

| Ability | Query (code) | Target requirement |
|---|---|---|
| **GA_GunShoot** (C++ part) | The aim hit comes from `AMyPlayerController2::Tick`: `SweepSingleByChannel(ECC_Visibility, sphere r = 10 cm, bTraceComplex = true, ignores own pawn)`, from the screen centre to FLT_MAX (MyPlayerController2.cpp:91-92). It is sent as target data by `UAT_SendMouseCursorData` (uses `PC->HitResultLineTrace`). `UGA_GunShoot::MyFunc(ImpactPoint, TargetActor)` (called from GA_GunShootBP, **not verified**) applies the damage | A component that **blocks ECC_Visibility** (a sweep-single only reports blocking hits). `Cast<AMyCharBase>(Actor)` must succeed and `GetMyAttributeSet()` must be non-null (GA_GunShoot.cpp:258-275). The burrower meets both through AMyEnemyChar. No IMyCombatInterface check |
| GA_GunShoot sentinel path | `OnServerMouseCursorData` → Mass capsules. `TraceWall` (ECC_Visibility, ignores ECC_Pawn objects, looks past any APawn) | Not relevant. A burrower that is the crosshair hit stops the sentinel shot at its range, which is correct |
| **GA_Projectile** → `AMyProjectile` | `CollisionSphere->OnComponentBeginOverlap` (MyProjectile.cpp:37). The sphere's profile is set in the projectile BP. A USphereComponent defaults to OverlapAllDynamic / WorldDynamic **[unverified]** | Any component of the burrower with **GenerateOverlapEvents = true** and Overlap/Block toward the sphere's object type. `OtherActor` must implement `IAbilitySystemInterface` (:42). It then does `ASC->ApplyGameplayEffectSpecToSelf(DamageEffectSpec)` and `Destroy()`. ACharacter turns the mesh's overlap events off by default **[unverified]**, so enable them. Homing targets `HomingTarget->GetRootComponent()`, which is the capsule (the head) |
| **GA_Electrocute** | `SphereTraceSingle(TraceTypeQuery1 = Visibility, r = 10)` (GA_Electrocute.cpp:28). Chain: `OverlapMultiByChannel(ECC_Visibility, sphere 1000)` (:58) | Block (first hit) or Overlap/Block (chain) on Visibility. `Implements<UMyCombatInterface>()`, `!Execute_IsDead`. Binds `GetOnDeathDelegate()` (FirstTargetDied / AdditionalTargetDied, BP events). Damage itself is in the BP |
| **GA_Shards** | `OverlapMultiByChannel(ECC_Visibility, sphere 100)` (GA_Shards.cpp:16; ignores its Radius argument) | Visibility Overlap/Block, IMyCombatInterface, !IsDead |
| **GA_Beam** | C++ has only camera impact helpers. The damage and trace are in **GA_BeamBP** (not readable) | Probably Visibility, like the rest. **Open question** |
| Mech sentinels | Only target `GameState->PlayerArray` pawns (`UMechSentinelSwarmSubsystem::GatherPlayerTargets`, MechSentinelSwarmSubsystem.cpp:380-404). Their hits use `SourceASC->ApplyGameplayEffectSpecToTarget` against those pawns | Never target or hit the burrower. Nothing to do |

**Collision recipe for the burrower:**
* Mesh, on the physics asset bodies:
  * `QueryOnly`, object type `Pawn`
  * Ignore all, then Visibility = Block, WorldDynamic = Overlap, PhysicsBody = Overlap
  * Camera = Ignore (the 20 m body must not push players' spring arms)
  * `SetGenerateOverlapEvents(true)`.
* Capsule (head):
  * keep the Pawn profile, but set Camera = Ignore
  * leave Visibility as the profile has it. I believe it ignores Visibility **[unverified]**, so hits land on the
    accurate mesh bodies.
* Rotor box:
  * `NoCollision`, or `QueryOnly` with every response Ignore, and `GenerateOverlapEvents = false`
  * the tile test is done in code
  * otherwise it eats aim traces, gets hit by projectiles (it is part of the actor, so those would still damage the
    burrower), and blocks the camera.
* Object type Pawn (not WorldStatic) also keeps GA_GrappleSwing2 off the worm: its rope traces query
  `ECC_WorldStatic` objects (GA_GrappleSwing2.cpp:119).
* Side effects of the worm blocking Visibility. These are minor, but list them for the test pass:
  * player foot traces (MyCharPlayer.cpp:567, 590)
  * `AMyHexPlatform` airborne-lead check (MyHexPlatform.cpp:543)
  * `GetHitResultUnderCursor`.

---

## 4. Death flow

### 4.1 Sequence (server → all)
* `UMyAttributeSet::PostGameplayEffectExecute`, server, fatal hit:
  * `IMyCombatInterface::Die()`
  * `AMyEnemyChar::Die()` (MyEnemyChar.cpp:73-77): `SetLifeSpan(LifeSpan)` (default 5 s), then `AMyCharBase::Die()`
  * `AMyCharBase::Die()` → `MulticastHandleDeath()` (NetMulticast, Reliable; runs on the server immediately, then on
    clients)
  * `AMyCharBase::MulticastHandleDeath_Implementation` (MyCharBase.cpp:132-149):
    * `Mesh->SetSimulatePhysics(true)`, `SetEnableGravity(true)`, `SetCollisionEnabled(PhysicsOnly)`,
      `SetCollisionResponseToChannel(ECC_WorldStatic, Block)`
    * `Capsule->SetCollisionEnabled(NoCollision)`
    * `Dissolve()`
    * `bIsDead = true`
    * `OnDeathDelegate.Broadcast(this)`
* Then, still inside the same PostGameplayEffectExecute: XP reward + XP event (enemies only).
* `Dissolve()` (MyCharBase.cpp:39-54, not virtual):
  * if `DissolveMaterialInstance` is set, it makes a MID, `GetMesh()->SetMaterial(0, MID)` (**slot 0 only**) and calls
    BlueprintImplementableEvent `StartDissolveTimeline(MID)`
  * the same for `WeaponDissolveMaterialInstance` (no weapon mesh any more).
  * Unset = no dissolve, no crash.
* `bIsDead` is a plain protected bool (not replicated) set inside the multicast. `IsDead_Implementation` returns it.
* `OnDeathDelegate`:
  * a plain `FOnDeathDelegateSignature` member (protected, not a UPROPERTY)
  * reached through the public `GetOnDeathDelegate()`
  * dynamic: `AddDynamic` / `AddUniqueDynamic` with a `UFUNCTION(AActor* DeadActor)`.
* Players differ:
  * `AMyCharPlayer::Die` guards `if (bIsDead) return;` and calls `MulticastHandlePlayerDeath` (anim only)
  * that adds loose tag `State.Dead` and broadcasts
  * no ragdoll, dissolve or lifespan.

### 4.2 Who listens to OnDeathDelegate
* `AMyGameMode::OnPlayerPawnDied`: player pawns only. Bound in `WatchPlayerPawn` from `SetPlayerDefaults`, which never
  runs for AI pawns.
* `UGA_Electrocute`: FirstTargetDied / AdditionalTargetDied, Blueprint events. Bound to any hit IMyCombatInterface
  target, including the burrower.
* `UMyAnimInstance`: player only, through an AMyCharPlayer pointer.
* New: the burrower spawner should bind it too, plus `OnDestroyed`.
* The broadcast fires synchronously inside the GE execution on the server. Handlers should only record the death and
  start timers. They should not spawn or destroy actors there.

### 4.3 Problems for the burrower in this flow
1. **Die() runs on every fatal hit, not once.**
   * Health stays at 0, so every later hit is "fatal" again.
   * Neither `AMyEnemyChar::Die` nor `AMyCharBase::Die` checks `bIsDead`.
   * Result: the reliable multicast is sent again, LifeSpan restarts (a corpse under fire never despawns), and **XP is
     paid again for every hit on the corpse** (MyAttributeSet.cpp:81-91 has no IsDead check).
   * Fix in the burrower: `Die() { if (bIsDead) return; Super::Die(); }`.
   * Also make the corpse unhittable: disable query collision in the death multicast. The base already does this through
     PhysicsOnly + capsule NoCollision. A Control Rig ragdoll path should use NoCollision on the mesh.
   * Damage already in flight (a Beam BP that caches the target) can still pay XP. The proper fix is one line in shared
     code: `if (IMyCombatInterface::Execute_IsDead(Props.TargetAvatarActor)) return;` before the damage block in
     `UMyAttributeSet::PostGameplayEffectExecute`. Leave that to the lead, because it changes all enemies.
2. **The base multicast ragdolls the whole mesh with engine physics right away.**
   * This conflicts with "Control Rig ragdoll on death".
   * Override `MulticastHandleDeath_Implementation`. It is a UFUNCTION RPC: override only the `_Implementation` and do not
     redeclare the UFUNCTION. The generated `_Implementation` is declared virtual and public by UHT **[unverified for
     5.8, standard]**.
   * Call `Super::MulticastHandleDeath_Implementation()` only on the `bUseMeshRagdollFallback` path. The base *is* the
     C++ ragdoll fallback.
3. **Movement does not stop.**
   * The base never stops the CharacterMovementComponent.
   * A flying CMC keeps its velocity: flying braking is small by default **[unverified: BrakingDecelerationFlying = 0]**.
   * The AI controller keeps steering unless the follow logic checks `bIsDead`.
   * In the override: `GetCharacterMovement()->StopMovementImmediately(); GetCharacterMovement()->DisableMovement();`. The
     follow and rotor ticks should early-out on `bIsDead`.
4. **Dissolve handles material slot 0 only.** The burrower almost certainly has several slots. Either leave
   `DissolveMaterialInstance` unset, or do a per-slot dissolve in the override.
5. **Late joiners:**
   * death is a multicast, and `bIsDead` is not replicated
   * a client that gets the actor after death sees it alive until LifeSpan destroys it
   * optional: a replicated `bBurrowerDead` with an OnRep that runs the same local death code.
6. **XP lookup runs for every AMyEnemyChar.** The burrower's `CharacterClass` must have an entry in DA_CharClassInfo with
   an `XPReward` curve. Otherwise `checkf(XPReward.IsValid())` (MyBPFuncLib.cpp:141) can fire on the kill.
   * `FScalableFloat::IsValid` semantics for a default value are **[unverified]**, so treat a missing entry as a crash.
   * Any GameMode that is not an `AMyGameMode`, or an unset `DA_MyEnemyCharacterClassInfo`, is a **null-deref crash on
     the kill**. This applies, for example, to `/Game/MechSentinel/Demo/BP_MechSentinelDemoGameMode` if it is not an
     AMyGameMode child.

### 4.4 Hit react
* Non-fatal hits call `TryActivateAbilitiesByTag(Ability.HitReact)`. Without an ability with that tag this does nothing.
* Do not give the burrower GA_HitReact: it plays a montage and waits for `Event.HitReact`.

---

## 5. Things in AMyCharBase / AMyEnemyChar that misbehave for a 20 m flying worm

| What | Where | Effect | Fix in ABurrowerCharacter |
|---|---|---|---|
| Health bar dereferenced without check | MyEnemyChar.cpp:34-35 `HealthBar = Cast<UMyUserWidget>(HealthBarWidgetComponent->GetUserWidgetObject()); HealthBar->SetWidgetController(this);` | **Crash in BeginPlay** if `BP_Burrower`'s HealthBar component has no widget class, or the class is not a `UMyUserWidget`. Also crashes where the widget is not created at all (dedicated server, where Slate is not initialised **[unverified]**). The project uses listen servers | BP: set Widget Class = `/Game/Level/UI/UserWidgets/Enemy/WBP_HealthBar`. C++ guard before `Super::BeginPlay()`: `if (!HealthBarWidgetComponent->GetWidgetClass()) HealthBarWidgetComponent->SetWidgetClass(UMyUserWidget::StaticClass());` (an empty native UMyUserWidget is valid). Or set it in the ctor with `ConstructorHelpers::FClassFinder<UUserWidget>(TEXT("/Game/Level/UI/UserWidgets/Enemy/WBP_HealthBar"))` |
| Health bar placement | `HealthBarWidgetComponent->SetupAttachment(GetRootComponent())` at the capsule centre (MyEnemyChar.cpp:20-21) | Inside the head | Screen space, a relative offset above the head, or hidden (`SetHiddenInGame(true)`; keep the component so BeginPlay still works) |
| Mesh parent is not the capsule | MyCharBase.cpp:23-25: `SceneComponentToRotateCharMesh` (child of the capsule), then Mesh | The mesh relative transform is relative to this scene component (identity, so the same as the capsule). Only the player rotates it (`LerpFeetRotToRot`). Harmless; know it when placing the 20 m mesh | Set `GetMesh()->SetRelativeLocationAndRotation(...)` as usual. Do not rotate SceneComponentToRotateCharMesh |
| JetPack static mesh | MyCharBase.cpp:27-28, attached to socket `JetPackSocket` (the burrower has none, so it sits at the mesh origin), no mesh assigned | Harmless (no mesh means no render and no body) | `SetCollisionEnabled(NoCollision)`, `SetGenerateOverlapEvents(false)`, `SetHiddenInGame(true)`. You cannot skip creating it: the base ctor dereferences it |
| Beam spline mesh | MyCharBase.cpp:29-30 | same | same |
| Highlight (`IMyHighlightInterface`) | MyEnemyChar.cpp:61-69, sets the custom depth stencil on the mesh | Dead code: `CursorTrace()` is commented out in both player controllers. Harmless | nothing |
| `OnMovementModeChanged` broadcast | MyCharBase.cpp:106-112 | Harmless | nothing (set `DefaultLandMovementMode = MOVE_Flying` and `SetMovementMode(MOVE_Flying)` in BeginPlay) |
| `GetCombatSocketLocation` returns ZeroVector | MyCharBase.cpp:114-118 | Only used by the caster's own abilities | nothing |
| `CharacterClass` / `CharacterLevel` zero-initialised | see 2.3 | Elemental / level 0 | set in the ctor |
| Death | see 4.3 | whole-mesh ragdoll, repeated Die, movement continues, slot-0 dissolve | override Die + MulticastHandleDeath_Implementation |
| StartupAbilities given on clients too | MyEnemyChar.cpp:31 | error log per ability | keep the list empty |
| Tick | MyEnemyChar.cpp:17 `bCanEverTick = true`, empty Tick | fine (the burrower ticks anyway) | — |
| Network relevancy | ACharacter default `NetCullDistanceSquared` (about 150 m) **[unverified]** | A worm more than about 150 m from a client's view target is not replicated to that client | Raise it if `SpawnDistanceBehind` or `DespawnDistance` get that large |
| ACharacter rotation defaults | `bUseControllerRotationYaw = true` **[unverified, ACharacter default]** | Rotation would follow the AI controller | `bUseControllerRotationYaw = false`. Rotate from velocity yourself, or use CMC `bOrientRotationToMovement` + `RotationRate` |
| AI possession | No AIController code anywhere in the project. `Aura.Build.cs` has **no AIModule** | — | `AutoPossessAI = EAutoPossessAI::PlacedInWorldOrSpawned`. APawn already defaults `AIControllerClass` to AAIController from engine config **[unverified]**. Add `"AIModule"` to Build.cs only if C++ names `AAIController` or a subclass |

---

## 6. Players on the server, and how player pawns change (for UBurrowerSpawnSubsystem)

* **Enumerate:** `GetWorld()->GetGameState()->PlayerArray` (`TArray<TObjectPtr<APlayerState>>`) and
  `PlayerState->GetPawn()`. This is exactly `UMechSentinelSwarmSubsystem::GatherPlayerTargets`
  (MechSentinelSwarmSubsystem.cpp:381-404). It skips dead pawns with
  `Pawn->Implements<UMyCombatInterface>() && IMyCombatInterface::Execute_IsDead(Pawn)`.
  * `AMyGameState` overrides `AddPlayerState` / `RemovePlayerState` only to re-rank.
  * `AMyGameMode::WatchedPawns` / `PendingRespawns` are private.
* **Key the entries by `APlayerState`** (weak pointer). It survives respawns, keeps the ASC, XP and level, and is destroyed
  on logout. The GameMode itself keys by `AController`.
* **Respawn timeline** (`AMyGameMode`, MyGameMode.cpp):
  1. Death: `AMyCharPlayer::MulticastHandlePlayerDeath`. `IsDead` is true and loose tag `State.Dead` is on the
     PlayerState's ASC. `AMyGameMode::OnPlayerPawnDied` cancels abilities and `ScheduleRespawn`. **The dead pawn stays
     possessed and valid** for `RespawnDelay` (default 5 s; FX starts `RespawnFXLeadTime` = 3 s before).
  2. `RespawnPlayer`: `CancelActiveAbilities`, `UnwatchPlayerPawn`, `Controller->UnPossess()`, `DeadPawn->Destroy()`,
     then `RestartPlayerAtTransform(Controller, Spot)` (fallback `RestartPlayer`). This lands on a tile of the platform
     past the lead's, or a PlayerStart.
  3. New pawn: `SetPlayerDefaults` → `WatchPlayerPawn`; `PossessedBy` → `InitAbilityActorInfo(PS, NewPawn)` +
     `InitAbilitySystemAfterRespawn` (clears State.Dead, refills vitals).
  4. Falling out of the world destroys the pawn **without Die** (`OnPlayerPawnDestroyed` → `ScheduleRespawn`). Between
     that and the respawn, `PlayerState->GetPawn()` and `Controller->GetPawn()` are null.
  5. `bRespawnEnabled = false`: dead players stay dead (pawn alive and possessed, IsDead true).
* **Spawner rule that covers all of this:**
  * poll `PlayerArray` on a short timer (0.25–1 s)
  * for each PlayerState, take `PS->GetPawn()`
  * if it is null or `Execute_IsDead`, the player has no target: pause that player's timer, and optionally despawn or
    idle its burrower
  * if the pawn changed, retarget the burrower (`TargetPlayer = NewPawn`) or despawn it
  * drop entries whose PlayerState is gone.
  * Polling needs no engine delegates. `APlayerState::OnPawnSet`, `AController::OnPossessedPawnChanged` and
    `FGameModeEvents::GameModePostLoginEvent/LogoutEvent` exist in UE5 as far as I know **[unverified for 5.8]**.
* **Player facing for "behind":**
  * `AMyCharPlayer` has `bUseControllerRotationYaw = false`
  * actor rotation can have pitch while boosting in flight (`LerpFeetRotToRot`)
  * use the yaw-only forward (`GetActorForwardVector().GetSafeNormal2D()`), or `Velocity.GetSafeNormal2D()` when moving.
* **Testing hazard:**
  * `AMyCharPlayer::DebugDieAfterBeginPlaySeconds = 3.f` is the C++ default (MyCharPlayer.h:161,
    MyCharPlayer.cpp:133-137): "TEMP death test: the server calls Die() this many seconds after BeginPlay".
  * Unless the player BP sets it to 0, every player pawn dies 3 s after spawning and respawns 5 s later. That churns the
    spawner.
  * Check BP_MyCharMech's value before PIE testing.
* The burrower is AI (no PlayerState). It never shows up in `PlayerArray`, never goes through `SetPlayerDefaults`, and
  sentinels ignore it.

---

## 7. Config: collision channels, profiles, settings sections

* **`DefaultEngine.ini` defines no custom collision channels or profiles.** There is no `[/Script/Engine.CollisionProfile]`
  section, and the staged copy from the user's machine is identical.
* The only channels in the project are the engine defaults. `ETraceTypeQuery::TraceTypeQuery1` = ECC_Visibility.
  `ECC_GameTraceChannelN` is used nowhere in the source.
* Engine profile facts I rely on, all **[unverified, from BaseEngine.ini memory]**:
  * `Pawn` (capsule): object Pawn, blocks everything except Visibility (Ignore)
  * `CharacterMesh` (ACharacter's mesh): QueryOnly, object Pawn, ignores Pawn/Vehicle; I don't remember its Visibility
    response
  * shape components default to `OverlapAllDynamic`.
  * The burrower ctor should set every response it relies on explicitly (section 9), so these do not matter.
* **Settings sections:**
  * `DefaultGame.ini` has `[/Script/Aura.MyHexBridgeSettings]` and `[/Script/Aura.MyMenuSettings]` (UDeveloperSettings,
    `Config = Game, DefaultConfig`)
  * `UMyHexMinimapSettings` has no section yet (defaults)
  * a `UBurrowerSettings` with `UCLASS(Config = Game, DefaultConfig, meta = (DisplayName = "Burrower"))` saves to
    `[/Script/Aura.BurrowerSettings]`
  * the settings classes use `TSoftClassPtr<>` + `LoadSynchronous()` (MyHexBridgeSubsystem.cpp:5272-5276) or an async
    load through `UAssetManager::GetStreamableManager()`.
  * **Packaging:** `MapsToCook` lists only `/Game/Maps/StartupMap`, and AMyGameMode's comment says "the project cooks maps
    only". A `BurrowerClass` that only a config soft pointer references may not be cooked. Add
    `+DirectoriesToAlwaysCook` for the burrower folder in the recipe. PIE is not affected.
* `DefaultGame.ini [/Script/GameplayAbilities.AbilitySystemGlobals]`:
  * stock `AbilitySystemGlobals`: no custom GE context, so `IsCrit` / `IsBlocked` piggy-back on the context hit result
    (`UMyBPFuncLib::SetIsCrit/SetIsBlocked`)
  * `ReplicateActivationOwnedTags = True`, `PredictTargetGameplayEffects = True`
  * GameplayCue path `/Game/Level/GAS/GameplayCues`
  * nothing burrower-specific.
* `DefaultEngine.ini`: GameMode `GlobalDefaultGameMode = /Game/Level/BP_MyGameMode`, server map `StartupMap`.
* `Aura.uproject`: ControlRigDynamics enabled; ControlRigPhysics not listed (the brief covers enabling it).

---

## 8. Damage sources other than players, for completeness

* Sentinel attacks: `MechSentinelCombatProcessors.cpp:170-208`. Source = the swarm's `AMechSentinelGASProxy` ASC (it
  carries a default `UMyAttributeSet` only so that `UExecCalc_Damage` can capture CritChance). Effect =
  `Rules->SentinelAttackEffect`, SetByCaller damage, `ApplyGameplayEffectSpecToTarget` to player ASCs.
* If the burrower is ever meant to hurt players on contact, the same pattern works: its own ASC as source (it has a
  UMyAttributeSet, so the CritChance capture works), `MyTags::SetDamageByCaller`, a GE with `UExecCalc_Damage`, applied
  to the player PlayerState's ASC.
* Player death is anim-only and the GameMode respawns. Nothing more is needed. This was not in the request.

---

## 9. Recommended ABurrowerCharacter GAS / death code

Only the parts that touch the patterns above. Follow, rotor and anim code are other tasks.

```cpp
// Public/Burrower/BurrowerCharacter.h (excerpt)
#include "Character/MyEnemyChar.h"

class UGameplayEffect;

UCLASS()
class AURA_API ABurrowerCharacter : public AMyEnemyChar
{
	GENERATED_BODY()

public:
	ABurrowerCharacter();

	/** Every fatal hit calls Die (Health stays at 0): only the first one counts. */
	virtual void Die() override;

protected:
	virtual void BeginPlay() override;

	/** Replaces the base death (whole-mesh physics, slot 0 dissolve): stops movement, then ragdoll by Control Rig or, with bUseMeshRagdollFallback, by the physics asset. */
	virtual void MulticastHandleDeath_Implementation() override;

	/** Unset: the GameMode's DA_MyEnemyCharacterClassInfo effect for CharacterClass (as the other enemies get). */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Burrower|GAS")
	TSubclassOf<UGameplayEffect> PrimaryAttributesEffect;

	/** Unset: DA_MyEnemyCharacterClassInfo->SecondaryAttributesEffect. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Burrower|GAS")
	TSubclassOf<UGameplayEffect> SecondaryAttributesEffect;

	/** Unset: DA_MyEnemyCharacterClassInfo->VitalAttributesEffect. Applied last (fills Health to MaxHealth). */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Burrower|GAS")
	TSubclassOf<UGameplayEffect> VitalAttributesEffect;

	/** The physics asset ragdolls in C++ (base death) instead of the Control Rig. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Burrower|Death")
	bool bUseMeshRagdollFallback = true;

private:
	/** Server: Primary -> Secondary -> Vital at CharacterLevel. */
	void InitializeBurrowerAttributes();
};
```

```cpp
// Private/Burrower/BurrowerCharacter.cpp (excerpt)
#include "Burrower/BurrowerCharacter.h"
#include "MyGameMode.h"
#include "AbilitySystem/MyAbilitySystemComponent.h"
#include "AbilitySystem/MyAttributeSet.h"
#include "AbilitySystem/Data/DA_MyEnemyCharacterClassInfo.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/SplineMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/WidgetComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameplayEffect.h"
#include "UI/UserWidgets/MyUserWidget.h"

ABurrowerCharacter::ABurrowerCharacter()
{
	// Must have an entry with an XPReward curve in DA_CharClassInfo: the kill looks it up (UMyAttributeSet)
	CharacterClass = ECharacterClass::Warrior;
	CharacterLevel = 1;
	LifeSpan = 10.f;

	AutoPossessAI = EAutoPossessAI::PlacedInWorldOrSpawned;
	bUseControllerRotationYaw = false;
	GetCharacterMovement()->DefaultLandMovementMode = MOVE_Flying;

	// Player-only parts the base class always creates
	JetPackMeshComponent->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	JetPackMeshComponent->SetGenerateOverlapEvents(false);
	JetPackMeshComponent->SetHiddenInGame(true);
	BeamSplineMeshComponent->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	BeamSplineMeshComponent->SetGenerateOverlapEvents(false);
	BeamSplineMeshComponent->SetHiddenInGame(true);

	// Hits land on the physics asset bodies: aim / Electrocute / Shards query ECC_Visibility, projectiles overlap
	USkeletalMeshComponent* MeshComp = GetMesh();
	MeshComp->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
	MeshComp->SetCollisionObjectType(ECC_Pawn);
	MeshComp->SetCollisionResponseToAllChannels(ECR_Ignore);
	MeshComp->SetCollisionResponseToChannel(ECC_Visibility, ECR_Block);
	MeshComp->SetCollisionResponseToChannel(ECC_WorldDynamic, ECR_Overlap);
	MeshComp->SetCollisionResponseToChannel(ECC_PhysicsBody, ECR_Overlap);
	MeshComp->SetGenerateOverlapEvents(true);

	// The 20 m body must not pull players' cameras in
	GetCapsuleComponent()->SetCollisionResponseToChannel(ECC_Camera, ECR_Ignore);
}

void ABurrowerCharacter::BeginPlay()
{
	// AMyEnemyChar::BeginPlay uses the health bar widget without a check
	if (HealthBarWidgetComponent && !HealthBarWidgetComponent->GetWidgetClass())
	{
		HealthBarWidgetComponent->SetWidgetClass(UMyUserWidget::StaticClass());
	}

	// InitAbilityActorInfo(this, this), startup abilities, health bar delegates
	Super::BeginPlay();

	if (HasAuthority())
	{
		InitializeBurrowerAttributes();
	}
	GetCharacterMovement()->SetMovementMode(MOVE_Flying);
}

void ABurrowerCharacter::InitializeBurrowerAttributes()
{
	if (!MyAbilitySystemComponent)
	{
		return;
	}

	TSubclassOf<UGameplayEffect> Primary = PrimaryAttributesEffect;
	TSubclassOf<UGameplayEffect> Secondary = SecondaryAttributesEffect;
	TSubclassOf<UGameplayEffect> Vital = VitalAttributesEffect;

	// Same effects the other enemies get (UMyBPFuncLib::InitializeEnemyAttributes, private in C++)
	const AMyGameMode* GameMode = GetWorld()->GetAuthGameMode<AMyGameMode>();
	if (UDA_MyEnemyCharacterClassInfo* ClassInfo = GameMode ? GameMode->DA_MyEnemyCharacterClassInfo : nullptr)
	{
		if (!Primary) { Primary = ClassInfo->GetInfoForClass(CharacterClass).PrimaryAttributesEffect; }
		if (!Secondary) { Secondary = ClassInfo->SecondaryAttributesEffect; }
		if (!Vital) { Vital = ClassInfo->VitalAttributesEffect; }
	}

	FGameplayEffectContextHandle Context = MyAbilitySystemComponent->MakeEffectContext();
	Context.AddInstigator(this, this);

	// Secondary derives from primary; vital fills up to the max secondary set (PreAttributeChange clamps Health)
	const TSubclassOf<UGameplayEffect> Effects[] = { Primary, Secondary, Vital };
	for (const TSubclassOf<UGameplayEffect>& Effect : Effects)
	{
		if (!Effect)
		{
			UE_LOG(LogTemp, Warning, TEXT("%s: missing attribute effect (set it on the Blueprint or fill DA_CharClassInfo)"), *GetName());
			continue;
		}
		const FGameplayEffectSpecHandle Spec = MyAbilitySystemComponent->MakeOutgoingSpec(Effect, CharacterLevel, Context);
		if (Spec.IsValid())
		{
			MyAbilitySystemComponent->ApplyGameplayEffectSpecToSelf(*Spec.Data.Get());
		}
	}
}

void ABurrowerCharacter::Die()
{
	if (bIsDead)
	{
		return;
	}
	Super::Die();   // SetLifeSpan(LifeSpan), MulticastHandleDeath
}

void ABurrowerCharacter::MulticastHandleDeath_Implementation()
{
	GetCharacterMovement()->StopMovementImmediately();
	GetCharacterMovement()->DisableMovement();
	// + RotorBox->SetCollisionEnabled(NoCollision), anim instance bIsDead / DeathTime, stop rotor checks

	if (bUseMeshRagdollFallback)
	{
		// Base: physics asset simulates (gravity, blocks WorldStatic, PhysicsOnly = no more hits), capsule off,
		// slot 0 dissolve, bIsDead, OnDeathDelegate
		Super::MulticastHandleDeath_Implementation();
		return;
	}

	// Control Rig ragdoll: the component stays kinematic; nothing may hit the corpse (each hit would pay XP again)
	GetCapsuleComponent()->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	GetMesh()->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Dissolve();
	bIsDead = true;   // before the broadcast: listeners call IsDead()
	OnDeathDelegate.Broadcast(this);
}
```

Notes on that code:
* All base members used are `protected` or `public` in `AMyCharBase` / `AMyEnemyChar`, so they are reachable from the
  subclass: `MyAbilitySystemComponent`, `bIsDead`, `OnDeathDelegate`, `JetPackMeshComponent`, `BeamSplineMeshComponent`,
  `HealthBarWidgetComponent`, `CharacterClass`, `CharacterLevel`, `LifeSpan`, `Dissolve()`.
  `AMyGameMode::DA_MyEnemyCharacterClassInfo` and `UDA_MyEnemyCharacterClassInfo::GetInfoForClass /
  SecondaryAttributesEffect / VitalAttributesEffect` are public.
* Engine APIs used, which I believe exist in 5.x but could not check against headers here:
  * `UWorld::GetAuthGameMode<T>()`
  * `UWidgetComponent::GetWidgetClass/SetWidgetClass`
  * `UPrimitiveComponent::SetCollisionObjectType/SetCollisionResponseToAllChannels/SetGenerateOverlapEvents/SetHiddenInGame`
  * `UCharacterMovementComponent::DisableMovement/StopMovementImmediately/SetMovementMode/DefaultLandMovementMode`
  * `UAbilitySystemComponent::MakeOutgoingSpec/MakeEffectContext/ApplyGameplayEffectSpecToSelf`.
  * The project already calls the GAS ones the same way (MyBPFuncLib.cpp:81-94).
* A Blueprint child (BP_Burrower) overrides anything set in the C++ ctor that it changes in its own defaults. The recipe
  should say "leave collision presets as inherited".
* Spawner: bind `Burrower->GetOnDeathDelegate().AddUniqueDynamic(this, &UBurrowerSpawnSubsystem::OnBurrowerDied)` (a
  `UFUNCTION() void OnBurrowerDied(AActor* DeadActor)`) and `OnDestroyed`, the way `AMyGameMode::WatchPlayerPawn` does
  (MyGameMode.cpp:161-164). From the death callback, start the re-arm timer only.
