// Mech Sentinel Swarm - the swarm subsystem: global runtime data, the GAS bridge and the hit query service.

#include "MechSwarm/Core/MechSentinelSwarmSubsystem.h"

#include "AbilitySystemComponent.h"
#include "EngineUtils.h"
#include "Engine/World.h"
#include "GameFramework/GameStateBase.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerState.h"
#include "GameplayEffect.h"
#include "Interfaces/MyCombatInterface.h"
#include "MassEntityConfigAsset.h"
#include "MassEntityManager.h"
#include "MassEntityUtils.h"
#include "MassEntityView.h"
#include "MassReplicationSubsystem.h"
#include "MassReplicationTrait.h"
#include "MassSpawnerSubsystem.h"
#include "Mass/EntityFragments.h"
#include "MechSwarm/Core/MechSentinelSwarmRules.h"
#include "MechSwarm/GAS/MechSentinelGASProxy.h"
#include "MechSwarm/GAS/MechSentinelTags.h"
#include "MechSwarm/MassCopies/MassMovementFragments_Copy.h"
#include "MechSwarm/Replication/MechSentinelClientBubble.h"
#include "MechSwarm/Replication/MechSentinelReplicator.h"
#include "MechSwarm/Spawning/MechSentinelWaveSpawner.h"
#include "MyGameMode.h"
#include "TimerManager.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(MechSentinelSwarmSubsystem)

DEFINE_LOG_CATEGORY_STATIC(LogMechSentinel, Log, All);

namespace MechSwarm::SubsystemPrivate
{
	/**
	 * True while a Mass phase may be running next to the game thread: from TG_PrePhysics to TG_PostPhysics, and in
	 * TG_LastDemotable (FrameEnd). IsProcessing() alone is not enough: it reads false between two processors of a phase.
	 * Timers (after TG_PostPhysics), TG_PostUpdateWork and the network receive at the start of the frame are outside.
	 */
	bool MayRunNextToMassPhase(const FMassEntityManager& EntityManager)
	{
		if (EntityManager.IsProcessing())
		{
			return true;
		}
		const UWorld* World = EntityManager.GetWorld();
		const ETickingGroup Group = World ? ETickingGroup(World->TickGroup) : TG_NewlySpawned;
		return Group <= TG_PostPhysics || Group == TG_LastDemotable;
	}

	template<typename TTag>
	void SetMassTag(FMassEntityManager& EntityManager, const FMassEntityHandle Entity, const bool bPresent)
	{
		const FMassEntityView View(EntityManager, Entity);
		if (View.HasTag<TTag>() == bPresent)
		{
			return;
		}

		// Structural changes are not allowed while processors run: go through the command buffer then. Hits can come
		// from game-thread code ticking next to a phase (input, actor ticks, anim notifies), so that counts too.
		if (MayRunNextToMassPhase(EntityManager))
		{
			if (bPresent)
			{
				EntityManager.Defer().AddTag<TTag>(Entity);
			}
			else
			{
				EntityManager.Defer().RemoveTag<TTag>(Entity);
			}
		}
		else if (bPresent)
		{
			EntityManager.AddTagToEntity(Entity, TTag::StaticStruct());
		}
		else
		{
			EntityManager.RemoveTagFromEntity(Entity, TTag::StaticStruct());
		}
	}

	FORCEINLINE FIntVector ToCell(const FVector& Position, const float InvCellSize)
	{
		return FIntVector(
			FMath::FloorToInt32(Position.X * InvCellSize),
			FMath::FloorToInt32(Position.Y * InvCellSize),
			FMath::FloorToInt32(Position.Z * InvCellSize));
	}

	/** Avoids walking millions of cells for absurdly large queries; falls back to brute force. */
	constexpr int64 MaxCellsPerQuery = 4096;

	/**
	 * Largest coordinate (cm) a query walks the cell hash with, so cell indices stay far inside int32. Queries beyond it,
	 * or with NaN, test every capsule instead (bounded by the capsule count). Shots come from client target data, so
	 * the coordinates cannot be trusted.
	 */
	constexpr double MaxHashedCoordinate = 1.0e9;

	/**
	 * Drops the stored effects GAS removed after LoadEntity re-created them (a cleanse or "remove other effects"
	 * component of the incoming spec, ...), and entries without a class. StoredHandles is index-aligned with
	 * GAS.ActiveEffects, as built by AMechSentinelGASProxy::LoadEntity. An effect that failed to re-apply (application
	 * requirements that no longer hold) stays stored, as an active effect would in GAS; it is only missing from that one
	 * evaluation. Returns true when something was dropped.
	 */
	bool PruneRemovedEffects(const UAbilitySystemComponent& ASC, const TArray<FActiveGameplayEffectHandle>& StoredHandles, FMechSentinelGASFragment& GAS)
	{
		bool bPruned = false;
		for (int32 Index = FMath::Min(StoredHandles.Num(), GAS.ActiveEffects.Num()) - 1; Index >= 0; --Index)
		{
			bool bRemoved = !GAS.ActiveEffects[Index].EffectClass;
			if (!bRemoved && StoredHandles[Index].IsValid())
			{
				const FActiveGameplayEffect* Stored = ASC.GetActiveGameplayEffect(StoredHandles[Index]);
				bRemoved = !Stored || Stored->IsPendingRemove;
			}
			if (bRemoved)
			{
				// RemoveAt, not RemoveAtSwap: the list stays in application order.
				GAS.ActiveEffects.RemoveAt(Index, EAllowShrinking::No);
				bPruned = true;
			}
		}
		return bPruned;
	}

	/** Stores (or refreshes, same class) an active effect of the loaded proxy on the entity, appended in application order. */
	void StoreActiveEffect(FMechSentinelGASFragment& GAS, const FActiveGameplayEffect& ActiveEffect, const float WorldTime)
	{
		const TSubclassOf<UGameplayEffect> EffectClass = ActiveEffect.Spec.Def->GetClass();
		FMechSentinelActiveEffect* Entry = GAS.ActiveEffects.FindByPredicate([EffectClass](const FMechSentinelActiveEffect& Existing)
		{
			return Existing.EffectClass == EffectClass;
		});
		if (!Entry)
		{
			Entry = &GAS.ActiveEffects.AddDefaulted_GetRef();
		}

		// Same class again refreshes the stored effect with what GAS resolved (respects the GE stacking setup).
		Entry->EffectClass = EffectClass;
		Entry->Level = ActiveEffect.Spec.GetLevel();
		Entry->RemainingTime = ActiveEffect.GetTimeRemaining(WorldTime);
		Entry->SetByCallerMagnitudes = ActiveEffect.Spec.SetByCallerTagMagnitudes;
		Entry->StackCount = FMath::Max(1, ActiveEffect.Spec.GetStackCount());
		Entry->InstigatorASC = ActiveEffect.Spec.GetEffectContext().GetInstigatorAbilitySystemComponent();
	}

	/**
	 * FMechSentinelStateFragment::BuffMask from the GAS view: bit i while a stored effect is (a child of) the rules' buff i
	 * effect, or the owned tags have that buff's State.Sentinel.Buff.* tag (designer GEs).
	 */
	uint8 ComputeBuffMask(const FMechSentinelGASFragment& GAS, const UMechSentinelSwarmRules& Rules)
	{
		const FGameplayTag BuffTags[MechSentinelSelfBuff::Num] =
		{
			MechSentinelTags::State_Sentinel_Buff_Armor,
			MechSentinelTags::State_Sentinel_Buff_Speed,
			MechSentinelTags::State_Sentinel_Buff_Damage
		};

		uint8 Mask = 0;
		for (int32 BuffIndex = 0; BuffIndex < MechSentinelSelfBuff::Num; ++BuffIndex)
		{
			bool bActive = GAS.OwnedTags.HasTag(BuffTags[BuffIndex]);
			const UClass* BuffClass = Rules.GetSelfBuffDef(BuffIndex).Effect.Get();
			for (int32 EffectIndex = 0; !bActive && BuffClass && EffectIndex < GAS.ActiveEffects.Num(); ++EffectIndex)
			{
				const UClass* EffectClass = GAS.ActiveEffects[EffectIndex].EffectClass.Get();
				bActive = EffectClass && EffectClass->IsChildOf(BuffClass);
			}
			if (bActive)
			{
				Mask |= uint8(1u << BuffIndex);
			}
		}
		return Mask;
	}
}

//----------------------------------------------------------------------//
// Lifecycle
//----------------------------------------------------------------------//
UMechSentinelSwarmSubsystem* UMechSentinelSwarmSubsystem::Get(const UObject* WorldContextObject)
{
	const UWorld* World = WorldContextObject ? WorldContextObject->GetWorld() : nullptr;
	return World ? World->GetSubsystem<UMechSentinelSwarmSubsystem>() : nullptr;
}

bool UMechSentinelSwarmSubsystem::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

void UMechSentinelSwarmSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);

	Collection.InitializeDependency<UMassSpawnerSubsystem>();

	// Must happen before any template with the replication trait is built and before the first client
	// joins, otherwise FMassReplicationSharedFragment asserts. Initialize is the earliest safe point.
	if (UMassReplicationSubsystem* ReplicationSubsystem = Collection.InitializeDependency<UMassReplicationSubsystem>())
	{
		ReplicationSubsystem->RegisterBubbleInfoClass(AMechSentinelClientBubbleInfo::StaticClass());
	}
}

void UMechSentinelSwarmSubsystem::Deinitialize()
{
	// Timers live in the game instance's timer manager, which can outlive this world.
	if (UWorld* World = GetWorld())
	{
		World->GetTimerManager().ClearTimer(SelfBuffFlushTimer);
	}
	PendingSelfBuffs.Reset();
	bSelfBuffFlushScheduled = false;

	GASProxy = nullptr;
	RegisteredConfigs.Reset();
	RejectedConfigs.Reset();
	FallbackRegistrations.Reset();
	FallbacksByGroup.Reset();
	CollisionEntries.Reset();
	CollisionCells.Reset();
	Super::Deinitialize();
}

void UMechSentinelSwarmSubsystem::OnWorldBeginPlay(UWorld& InWorld)
{
	Super::OnWorldBeginPlay(InWorld);

	if (HasAuthority())
	{
		if (const AMyGameMode* GameMode = InWorld.GetAuthGameMode<AMyGameMode>())
		{
			GameModeRules = GameMode->SentinelSwarmRules;
		}
		GetOrCreateProxy();
	}

	EnsureTemplatesBuilt();
}

bool UMechSentinelSwarmSubsystem::HasAuthority() const
{
	const UWorld* World = GetWorld();
	return World && World->GetNetMode() != NM_Client;
}

FMassEntityManager* UMechSentinelSwarmSubsystem::GetEntityManager() const
{
	return UE::Mass::Utils::GetEntityManager(GetWorld());
}

//----------------------------------------------------------------------//
// Global data
//----------------------------------------------------------------------//
const UMechSentinelSwarmRules* UMechSentinelSwarmSubsystem::GetRules() const
{
	if (RulesOverride)
	{
		return RulesOverride;
	}
	if (GameModeRules)
	{
		return GameModeRules;
	}
	return GetDefault<UMechSentinelSwarmRules>();
}

void UMechSentinelSwarmSubsystem::SetRulesOverride(UMechSentinelSwarmRules* NewRules)
{
	RulesOverride = NewRules;
}

void UMechSentinelSwarmSubsystem::SetSwarmMovementSpeed(const FName SwarmGroup, const float NewMovementSpeed)
{
	if (!HasAuthority())
	{
		return;
	}

	if (FMassEntityManager* EntityManager = GetEntityManager())
	{
		EntityManager->ForEachSharedFragment<FMechSentinelSharedAttributesFragment>([SwarmGroup, NewMovementSpeed](FMechSentinelSharedAttributesFragment& Shared)
		{
			if (Shared.SwarmGroup == SwarmGroup)
			{
				Shared.MovementSpeed = FMath::Max(0.f, NewMovementSpeed);
			}
		});
	}
}

//----------------------------------------------------------------------//
// Templates
//----------------------------------------------------------------------//
bool UMechSentinelSwarmSubsystem::RegisterEntityConfig(const UMassEntityConfigAsset* Config)
{
	UWorld* World = GetWorld();
	if (!Config || !World || RejectedConfigs.Contains(Config))
	{
		return false;
	}

	if (!RegisteredConfigs.Contains(Config))
	{
		if (!ValidateEntityConfig(*Config))
		{
			RejectedConfigs.Add(Config);
			return false;
		}
		RegisteredConfigs.Add(Config);
	}

	// Builds and registers the template in the spawner subsystem's registry (no-op when it already exists).
	// The template ID only depends on the config GUID, so server and clients agree on it.
	Config->GetOrCreateEntityTemplate(*World);
	return true;
}

bool UMechSentinelSwarmSubsystem::ValidateEntityConfig(const UMassEntityConfigAsset& Config) const
{
	const UWorld* World = GetWorld();
	if (!World || World->GetNetMode() == NM_Standalone)
	{
		// The Replication trait does nothing in standalone.
		return true;
	}

	const UMassReplicationTrait* ReplicationTrait = Cast<UMassReplicationTrait>(Config.FindTrait(UMassReplicationTrait::StaticClass()));
	if (!ReplicationTrait)
	{
		UE_LOG(LogMechSentinel, Warning, TEXT("%s has no Replication trait: its sentinels will only exist on the server."), *Config.GetName());
		return true;
	}

	// The engine asserts on both of these while building the template, so catch them here with a readable message.
	const FMassReplicationParameters& Params = ReplicationTrait->Params;
	// The exact replicator class: UMechSentinelReplicationProcessor runs only that one (a subclass may need more fragments).
	if (Params.BubbleInfoClass.Get() != AMechSentinelClientBubbleInfo::StaticClass() || Params.ReplicatorClass.Get() != UMechSentinelReplicator::StaticClass())
	{
		UE_LOG(LogMechSentinel, Error,
			TEXT("%s: set its Replication trait to Bubble Info Class = MechSentinelClientBubbleInfo and Replicator Class = MechSentinelReplicator. The config is ignored until then."),
			*Config.GetName());
		return false;
	}
	return true;
}

void UMechSentinelSwarmSubsystem::EnsureTemplatesBuilt()
{
	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}

	for (const TObjectPtr<const UMassEntityConfigAsset>& Config : RegisteredConfigs)
	{
		if (Config)
		{
			Config->GetOrCreateEntityTemplate(*World);
		}
	}

	for (TActorIterator<AMechSentinelWaveSpawner> It(World); It; ++It)
	{
		It->EnsureTemplateBuilt();
	}
}

//----------------------------------------------------------------------//
// Targets
//----------------------------------------------------------------------//
void UMechSentinelSwarmSubsystem::RegisterFallbackTargets(const FName SwarmGroup, const TArray<FMechSentinelFallbackPoint>& Points, UObject* Owner)
{
	FFallbackRegistration& Registration = FallbackRegistrations.AddDefaulted_GetRef();
	Registration.Owner = Owner;
	Registration.SwarmGroup = SwarmGroup;
	Registration.Points.Reserve(Points.Num());
	for (const FMechSentinelFallbackPoint& Point : Points)
	{
		Registration.Points.Emplace(Point);
	}
	RebuildFallbackMap();
}

void UMechSentinelSwarmSubsystem::UnregisterFallbackTargets(UObject* Owner)
{
	FallbackRegistrations.RemoveAll([Owner](const FFallbackRegistration& Registration)
	{
		return !Registration.Owner.IsValid() || Registration.Owner.Get() == Owner;
	});
	RebuildFallbackMap();
}

void UMechSentinelSwarmSubsystem::RebuildFallbackMap()
{
	FallbacksByGroup.Reset();
	for (const FFallbackRegistration& Registration : FallbackRegistrations)
	{
		FallbacksByGroup.FindOrAdd(Registration.SwarmGroup).Append(Registration.Points);
	}
}

TConstArrayView<FMechSentinelFallbackTarget> UMechSentinelSwarmSubsystem::GetFallbackTargets(const FName SwarmGroup) const
{
	if (const TArray<FMechSentinelFallbackTarget>* Points = FallbacksByGroup.Find(SwarmGroup))
	{
		return *Points;
	}
	return TConstArrayView<FMechSentinelFallbackTarget>();
}

void UMechSentinelSwarmSubsystem::GatherPlayerTargets(TArray<TPair<AActor*, FVector>>& OutTargets) const
{
	OutTargets.Reset();

	const UWorld* World = GetWorld();
	const AGameStateBase* GameState = World ? World->GetGameState() : nullptr;
	if (!GameState)
	{
		return;
	}

	for (const TObjectPtr<APlayerState>& PlayerState : GameState->PlayerArray)
	{
		APawn* Pawn = PlayerState ? PlayerState->GetPawn() : nullptr;
		if (!IsValid(Pawn))
		{
			continue;
		}
		if (Pawn->Implements<UMyCombatInterface>() && IMyCombatInterface::Execute_IsDead(Pawn))
		{
			continue;
		}
		OutTargets.Emplace(Pawn, Pawn->GetActorLocation());
	}
}

//----------------------------------------------------------------------//
// GAS bridge
//----------------------------------------------------------------------//
AMechSentinelGASProxy* UMechSentinelSwarmSubsystem::GetOrCreateProxy()
{
	if (!IsValid(GASProxy) && HasAuthority())
	{
		if (UWorld* World = GetWorld())
		{
			FActorSpawnParameters SpawnParams;
			SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
			SpawnParams.ObjectFlags |= RF_Transient;
			GASProxy = World->SpawnActor<AMechSentinelGASProxy>(AMechSentinelGASProxy::StaticClass(), FTransform::Identity, SpawnParams);
		}
	}
	return GASProxy;
}

UAbilitySystemComponent* UMechSentinelSwarmSubsystem::GetSentinelSourceASC()
{
	AMechSentinelGASProxy* Proxy = GetOrCreateProxy();
	return Proxy ? Proxy->GetAbilitySystemComponent() : nullptr;
}

//----------------------------------------------------------------------//
// Self buffs
//----------------------------------------------------------------------//
bool UMechSentinelSwarmSubsystem::QueueSelfBuff(const FMassEntityHandle Entity, const int32 BuffIndex)
{
	if (!HasAuthority() || !Entity.IsSet() || BuffIndex < 0 || BuffIndex >= MechSentinelSelfBuff::Num)
	{
		return false;
	}

	// A longer backlog would cast long after the decision (and its target distance window), and keep growing while
	// casts come faster than the flush budget.
	const int32 MaxPending = FMath::Max(1, GetRules()->MaxSelfBuffsPerFrame) * 30;
	if (PendingSelfBuffs.Num() >= MaxPending)
	{
		return false;
	}

	FPendingSelfBuff& Pending = PendingSelfBuffs.AddDefaulted_GetRef();
	Pending.Entity = Entity;
	Pending.BuffIndex = BuffIndex;
	ScheduleSelfBuffFlush();
	return true;
}

void UMechSentinelSwarmSubsystem::ScheduleSelfBuffFlush()
{
	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}
	FTimerManager& TimerManager = World->GetTimerManager();
	// The handle check keeps the queue going should this object's timers ever be cleared from outside.
	if (bSelfBuffFlushScheduled && TimerManager.TimerExists(SelfBuffFlushTimer))
	{
		return;
	}

	// Timers run after TG_PostPhysics: outside every Mass phase but FrameEnd, like GA_GunShoot's hits. Armed from the
	// decision processor (PrePhysics), the flush runs later the same frame; armed from the flush, the next frame.
	SelfBuffFlushTimer = TimerManager.SetTimerForNextTick(this, &UMechSentinelSwarmSubsystem::FlushSelfBuffs);
	bSelfBuffFlushScheduled = true;
}

void UMechSentinelSwarmSubsystem::FlushSelfBuffs()
{
	QUICK_SCOPE_CYCLE_COUNTER(MechSentinelSwarm_FlushSelfBuffs);

	bSelfBuffFlushScheduled = false;
	SelfBuffFlushTimer.Invalidate();
	if (PendingSelfBuffs.IsEmpty())
	{
		return;
	}

	FMassEntityManager* EntityManager = GetEntityManager();
	UAbilitySystemComponent* SourceASC = HasAuthority() ? GetSentinelSourceASC() : nullptr;
	const UMechSentinelSwarmRules* Rules = GetRules();
	if (!EntityManager || !SourceASC || !Rules->bEnableSelfBuffs)
	{
		PendingSelfBuffs.Reset();
		return;
	}

	// This frame's share, oldest first. Taken out before applying: GAS and the events it fires run game code.
	const int32 NumToApply = FMath::Min(PendingSelfBuffs.Num(), FMath::Max(1, Rules->MaxSelfBuffsPerFrame));
	TArray<FPendingSelfBuff> Batch;
	Batch.Append(PendingSelfBuffs.GetData(), NumToApply);
	PendingSelfBuffs.RemoveAt(0, NumToApply, EAllowShrinking::No);

	for (const FPendingSelfBuff& Pending : Batch)
	{
		ApplySelfBuff(*EntityManager, *SourceASC, *Rules, Pending.Entity, Pending.BuffIndex);
	}

	if (!PendingSelfBuffs.IsEmpty())
	{
		ScheduleSelfBuffFlush();
	}
}

bool UMechSentinelSwarmSubsystem::ApplySelfBuff(FMassEntityManager& EntityManager, UAbilitySystemComponent& SourceASC, const UMechSentinelSwarmRules& Rules,
	const FMassEntityHandle Entity, const int32 BuffIndex)
{
	const FMechSentinelSelfBuffDef& Def = Rules.GetSelfBuffDef(BuffIndex);
	if (!Def.Effect || !EntityManager.IsEntityActive(Entity))
	{
		return false;
	}

	// An instant GE would change the base value for good on every cast (and is not stored, so it would show nothing).
	if (Def.Effect.GetDefaultObject()->DurationPolicy == EGameplayEffectDurationType::Instant)
	{
		static bool bWarned = false;
		UE_CLOG(!bWarned, LogMechSentinel, Warning, TEXT("Self-buff effect %s is Instant and is never cast: self-buffs need a Has Duration effect."),
			*GetNameSafe(Def.Effect.Get()));
		bWarned = true;
		return false;
	}

	// Re-checked: a hit or an expiry may have run between the decision and now.
	const FMechSentinelStateFragment* State = EntityManager.GetFragmentDataPtr<FMechSentinelStateFragment>(Entity);
	if (!State || State->State == EMechSentinelState::Dead || State->State == EMechSentinelState::Stunned
		|| (State->BuffMask & (1u << BuffIndex)) != 0)
	{
		return false;
	}

	// Source = the proxy ASC, like sentinel attacks. The duration is locked on the spec, so the rules are the only knob.
	const FGameplayEffectSpecHandle Spec = SourceASC.MakeOutgoingSpec(Def.Effect, 1.f, SourceASC.MakeEffectContext());
	if (!Spec.IsValid())
	{
		return false;
	}
	Spec.Data->SetSetByCallerMagnitude(MechSentinelTags::SetByCaller_SelfBuffMagnitude, FMath::Max(0.f, Def.Magnitude));
	Spec.Data->SetDuration(FMath::Max(0.1f, Def.Duration), /*bLockDuration*/true);

	// Stores the effect, recomputes the attributes and sets the BuffMask bit (SyncStateFromGAS).
	ApplyGameplayEffectSpecToSentinel(Entity, *Spec.Data.Get());
	return true;
}

float UMechSentinelSwarmSubsystem::ApplyGameplayEffectSpecToSentinel(const FMassEntityHandle Entity, const FGameplayEffectSpec& Spec, const FVector* HitLocation)
{
	if (!HasAuthority() || !Spec.Def)
	{
		return 0.f;
	}

	FMassEntityManager* EntityManager = GetEntityManager();
	if (!EntityManager || !EntityManager->IsEntityActive(Entity))
	{
		return 0.f;
	}

	const FMassEntityView View(*EntityManager, Entity);
	FMechSentinelAttributesFragment* Attributes = View.GetFragmentDataPtr<FMechSentinelAttributesFragment>();
	FMechSentinelGASFragment* GAS = View.GetFragmentDataPtr<FMechSentinelGASFragment>();
	FMechSentinelStateFragment* State = View.GetFragmentDataPtr<FMechSentinelStateFragment>();
	if (!Attributes || !GAS || !State || State->State == EMechSentinelState::Dead)
	{
		return 0.f;
	}

	AMechSentinelGASProxy* Proxy = GetOrCreateProxy();
	if (!Proxy || !Proxy->GetAbilitySystemComponent())
	{
		return 0.f;
	}
	UAbilitySystemComponent* ProxyASC = Proxy->GetAbilitySystemComponent();
	const bool bAttacking = View.HasTag<FMechSentinelAttackingTag>();

	// Pass 1: run the incoming effect.
	Proxy->LoadEntity(*Attributes, *GAS, bAttacking);
	const FActiveGameplayEffectHandle AppliedHandle = Proxy->ApplySpec(Spec);

	// Pass 2 is needed whenever the stored effect list changed or the read would include something that is not stored.
	bool bReevaluate = false;

	// The incoming effect may have removed stored ones (cleanse / remove-effects components, immunity...): drop them from
	// Mass too, otherwise they would come back on the next evaluation.
	if (MechSwarm::SubsystemPrivate::PruneRemovedEffects(*ProxyASC, Proxy->GetStoredHandles(), *GAS))
	{
		bReevaluate = true;
	}

	const UWorld* World = GetWorld();
	const float WorldTime = World ? float(World->GetTimeSeconds()) : 0.f;

	// Stores a duration / infinite effect now active on the proxy. Periodic ones are not persisted: their tags /
	// modifiers must not stay in Mass either, so the values are rebuilt from the stored list.
	auto StoreOrReevaluate = [&bReevaluate, GAS, WorldTime](const FActiveGameplayEffect& ActiveEffect)
	{
		if (ActiveEffect.GetPeriod() > 0.f)
		{
			UE_LOG(LogMechSentinel, Warning, TEXT("%s is periodic. Periodic effects are not persisted on sentinels; use an instant effect applied repeatedly for damage over time."), *GetNameSafe(ActiveEffect.Spec.Def));
		}
		else
		{
			MechSwarm::SubsystemPrivate::StoreActiveEffect(*GAS, ActiveEffect, WorldTime);
		}
		bReevaluate = true;
	};

	// The incoming effect first (GAS adds it before running its on-application components)...
	if (Spec.Def->DurationPolicy != EGameplayEffectDurationType::Instant && AppliedHandle.IsValid())
	{
		if (const FActiveGameplayEffect* ActiveEffect = ProxyASC->GetActiveGameplayEffect(AppliedHandle))
		{
			StoreOrReevaluate(*ActiveEffect);
		}
	}

	// ... then what GAS applied on its own while running it (additional on-application effects, overflow effects...),
	// even for an instant spec. Unload removes them from the proxy, so unless they are stored a stun or a slow they
	// grant would stay in Mass with nothing to expire it. LoadEntity already stripped the side effects of the stored
	// effects' re-creation, so everything active that is not a stored handle or the spec's own is new.
	{
		FGameplayEffectQuery NewEffects;
		for (const FActiveGameplayEffectHandle& StoredHandle : Proxy->GetStoredHandles())
		{
			if (StoredHandle.IsValid())
			{
				NewEffects.IgnoreHandles.Add(StoredHandle);
			}
		}
		if (AppliedHandle.IsValid())
		{
			NewEffects.IgnoreHandles.Add(AppliedHandle);
		}
		for (const FActiveGameplayEffectHandle& Handle : ProxyASC->GetActiveEffects(NewEffects))
		{
			const FActiveGameplayEffect* Extra = ProxyASC->GetActiveGameplayEffect(Handle);
			if (Extra && !Extra->IsPendingRemove && Extra->Spec.Def)
			{
				StoreOrReevaluate(*Extra);
			}
		}
	}

	float IncomingDamage = 0.f;
	const float Damage = Proxy->ReadBack(*Attributes, *GAS, &IncomingDamage);
	Proxy->Unload();

	// Pass 2: re-evaluate the current values from the updated effect list (no double counting of a refreshed effect).
	if (bReevaluate)
	{
		Proxy->LoadEntity(*Attributes, *GAS, bAttacking);
		Proxy->ReadBack(*Attributes, *GAS);
		Proxy->Unload();
	}

	AActor* Instigator = Spec.GetEffectContext().GetInstigator();
	if (Damage > 0.f)
	{
		State->HitFlash = 1.f;
		++State->HitSerial;
		const FVector Location = HitLocation ? *HitLocation : View.GetFragmentData<FTransformFragment>().GetTransform().GetLocation();
		OnSentinelDamaged.Broadcast(FMechSentinelHandle(Entity), Damage, Location, Instigator);

		if (OnSentinelDamagedNative.IsBound())
		{
			FMechSentinelDamageEvent Event;
			Event.Sentinel = FMechSentinelHandle(Entity);
			Event.Damage = Damage;
			Event.IncomingDamage = FMath::Max(Damage, IncomingDamage);
			Event.Location = Location;
			Event.Instigator = Instigator;
			Event.EffectContext = Spec.GetEffectContext();
			Event.bShielded = GAS->OwnedTags.HasTagExact(MechSentinelTags::State_Sentinel_Shielded);
			OnSentinelDamagedNative.Broadcast(Event);
		}
	}

	SyncStateFromGAS(*EntityManager, Entity, Instigator);
	return Damage;
}

void UMechSentinelSwarmSubsystem::RecomputeSentinel(const FMassEntityHandle Entity)
{
	if (!HasAuthority())
	{
		return;
	}

	FMassEntityManager* EntityManager = GetEntityManager();
	AMechSentinelGASProxy* Proxy = GetOrCreateProxy();
	if (!EntityManager || !Proxy || !EntityManager->IsEntityActive(Entity))
	{
		return;
	}

	const FMassEntityView View(*EntityManager, Entity);
	FMechSentinelAttributesFragment* Attributes = View.GetFragmentDataPtr<FMechSentinelAttributesFragment>();
	FMechSentinelGASFragment* GAS = View.GetFragmentDataPtr<FMechSentinelGASFragment>();
	FMechSentinelStateFragment* State = View.GetFragmentDataPtr<FMechSentinelStateFragment>();
	if (!Attributes || !GAS || !State || State->State == EMechSentinelState::Dead)
	{
		return;
	}

	const bool bAttacking = View.HasTag<FMechSentinelAttackingTag>();
	Proxy->LoadEntity(*Attributes, *GAS, bAttacking);
	// Safety net: stored effects that removed each other on re-creation are dropped (cannot happen while the list is
	// kept in application order, but a stale entry must not come back on every evaluation).
	const bool bPruned = MechSwarm::SubsystemPrivate::PruneRemovedEffects(*Proxy->GetAbilitySystemComponent(), Proxy->GetStoredHandles(), *GAS);
	if (bPruned)
	{
		Proxy->Unload();
		Proxy->LoadEntity(*Attributes, *GAS, bAttacking);
	}
	Proxy->ReadBack(*Attributes, *GAS);
	Proxy->Unload();

	SyncStateFromGAS(*EntityManager, Entity, nullptr);
}

void UMechSentinelSwarmSubsystem::KillSentinel(const FMassEntityHandle Entity, AActor* Instigator)
{
	FMassEntityManager* EntityManager = GetEntityManager();
	if (!HasAuthority() || !EntityManager || !EntityManager->IsEntityActive(Entity))
	{
		return;
	}

	if (FMechSentinelAttributesFragment* Attributes = EntityManager->GetFragmentDataPtr<FMechSentinelAttributesFragment>(Entity))
	{
		Attributes->Health = 0.f;
		SyncStateFromGAS(*EntityManager, Entity, Instigator);
	}
}

void UMechSentinelSwarmSubsystem::SyncStateFromGAS(FMassEntityManager& EntityManager, const FMassEntityHandle Entity, AActor* Instigator)
{
	using namespace MechSwarm::SubsystemPrivate;

	if (!EntityManager.IsEntityActive(Entity))
	{
		return;
	}

	// Every fragment read / write happens first: outside processing, a tag change below moves the entity to another
	// archetype right away, which invalidates the view and the fragment pointers.
	bool bKilled = false;
	bool bStunned = false;
	bool bEnteredStun = false;
	FVector Location = FVector::ZeroVector;
	{
		const FMassEntityView View(EntityManager, Entity);
		FMechSentinelAttributesFragment* Attributes = View.GetFragmentDataPtr<FMechSentinelAttributesFragment>();
		FMechSentinelGASFragment* GAS = View.GetFragmentDataPtr<FMechSentinelGASFragment>();
		FMechSentinelStateFragment* State = View.GetFragmentDataPtr<FMechSentinelStateFragment>();
		if (!Attributes || !GAS || !State)
		{
			return;
		}

		if (Attributes->Health <= 0.f)
		{
			if (State->State == EMechSentinelState::Dead)
			{
				return;
			}
			const FMechSentinelParameters* Params = View.GetConstSharedFragmentDataPtr<FMechSentinelParameters>();
			State->State = EMechSentinelState::Dead;
			State->TimeInState = 0.f;
			State->DeathTimeRemaining = Params ? Params->DeathFallDuration : 2.f;
			State->BuffMask = 0;
			GAS->OwnedTags.AddTag(MechSentinelTags::State_Sentinel_Dead);
			Location = View.GetFragmentData<FTransformFragment>().GetTransform().GetLocation();
			bKilled = true;
		}
		else
		{
			State->BuffMask = ComputeBuffMask(*GAS, *GetRules());

			bStunned = GAS->OwnedTags.HasTagExact(MechSentinelTags::State_Sentinel_Stunned);
			const bool bWasStunned = State->State == EMechSentinelState::Stunned;
			if (bStunned && !bWasStunned)
			{
				State->State = EMechSentinelState::Stunned;
				State->TimeInState = 0.f;
				bEnteredStun = true;
			}
			else if (!bStunned && bWasStunned)
			{
				State->State = EMechSentinelState::Seeking;
				State->TimeInState = 0.f;
			}
		}
	}

	// Tag changes only from here on (no fragment access).
	if (bKilled)
	{
		// Death owns the position from now on (fall), default movement must leave it alone.
		SetMassTag<FMechSentinelDeadTag>(EntityManager, Entity, true);
		SetMassTag<FMassCustomMovementTag_Copy>(EntityManager, Entity, true);
		SetMassTag<FMechSentinelAttackingTag>(EntityManager, Entity, false);
		SetMassTag<FMechSentinelStunnedTag>(EntityManager, Entity, false);
		OnSentinelKilled.Broadcast(FMechSentinelHandle(Entity), Location, Instigator);
		return;
	}

	SetMassTag<FMechSentinelStunnedTag>(EntityManager, Entity, bStunned);
	if (bEnteredStun)
	{
		SetMassTag<FMechSentinelAttackingTag>(EntityManager, Entity, false);
	}
}

//----------------------------------------------------------------------//
// Collision hash
//----------------------------------------------------------------------//
void UMechSentinelSwarmSubsystem::BeginCollisionFrame(const float CellSize)
{
	CollisionCellSize = FMath::Max(50.f, CellSize);
	MaxCollisionExtent = 0.f;
	CollisionEntries.Reset();
	for (TPair<FIntVector, TArray<int32>>& Cell : CollisionCells)
	{
		Cell.Value.Reset();
	}
}

void UMechSentinelSwarmSubsystem::AddCollisionCapsule(const FMassEntityHandle Entity, const FVector& Center, const FVector& Axis, const float Radius, const float HalfHeight)
{
	const float HalfSegment = FMath::Max(0.f, HalfHeight - Radius);
	const FVector SafeAxis = Axis.GetSafeNormal(UE_SMALL_NUMBER, FVector::ForwardVector);

	FCollisionEntry& Entry = CollisionEntries.AddDefaulted_GetRef();
	Entry.Entity = Entity;
	Entry.SegmentA = Center - SafeAxis * HalfSegment;
	Entry.SegmentB = Center + SafeAxis * HalfSegment;
	Entry.Radius = Radius;

	MaxCollisionExtent = FMath::Max(MaxCollisionExtent, HalfSegment + Radius);
	CollisionCells.FindOrAdd(MechSwarm::SubsystemPrivate::ToCell(Center, 1.f / CollisionCellSize)).Add(CollisionEntries.Num() - 1);
}

void UMechSentinelSwarmSubsystem::EndCollisionFrame()
{
	for (auto It = CollisionCells.CreateIterator(); It; ++It)
	{
		if (It.Value().IsEmpty())
		{
			It.RemoveCurrent();
		}
	}
}

int32 UMechSentinelSwarmSubsystem::QueryCapsule(const FVector& SegmentStart, const FVector& SegmentEnd, const float Radius, TArray<FMechSentinelHit>& OutHits) const
{
	using namespace MechSwarm::SubsystemPrivate;

	OutHits.Reset();
	if (CollisionEntries.IsEmpty())
	{
		return 0;
	}

	const FVector SweepDir = SegmentEnd - SegmentStart;
	const float SweepLength = SweepDir.Size();

	auto TestEntry = [&](const int32 EntryIndex)
	{
		const FCollisionEntry& Entry = CollisionEntries[EntryIndex];
		FVector OnQuery, OnSentinel;
		FMath::SegmentDistToSegmentSafe(SegmentStart, SegmentEnd, Entry.SegmentA, Entry.SegmentB, OnQuery, OnSentinel);
		if (FVector::DistSquared(OnQuery, OnSentinel) <= FMath::Square(Radius + Entry.Radius))
		{
			FMechSentinelHit& Hit = OutHits.AddDefaulted_GetRef();
			Hit.Sentinel = FMechSentinelHandle(Entry.Entity);
			Hit.ImpactPoint = OnSentinel;
			Hit.Distance = SweepLength > KINDA_SMALL_NUMBER ? FVector::DotProduct(OnQuery - SegmentStart, SweepDir / SweepLength) : 0.f;
		}
	};

	// Bounds of the query, inflated by the biggest sentinel capsule seen this frame.
	const float Inflate = Radius + MaxCollisionExtent;
	const FVector Min = SegmentStart.ComponentMin(SegmentEnd) - FVector(Inflate);
	const FVector Max = SegmentStart.ComponentMax(SegmentEnd) + FVector(Inflate);
	const bool bHashable = !Min.ContainsNaN() && !Max.ContainsNaN()
		&& Min.GetAbsMax() < MaxHashedCoordinate && Max.GetAbsMax() < MaxHashedCoordinate;

	const float InvCellSize = 1.f / CollisionCellSize;
	FIntVector MinCell = FIntVector::ZeroValue;
	FIntVector MaxCell = FIntVector::ZeroValue;
	int64 NumCells = TNumericLimits<int64>::Max();
	if (bHashable)
	{
		MinCell = ToCell(Min, InvCellSize);
		MaxCell = ToCell(Max, InvCellSize);
		// Each axis is checked before multiplying, so the product (at most MaxCellsPerQuery^3) cannot overflow.
		const int64 SpanX = FMath::Max<int64>(0, int64(MaxCell.X) - MinCell.X + 1);
		const int64 SpanY = FMath::Max<int64>(0, int64(MaxCell.Y) - MinCell.Y + 1);
		const int64 SpanZ = FMath::Max<int64>(0, int64(MaxCell.Z) - MinCell.Z + 1);
		if (SpanX <= MaxCellsPerQuery && SpanY <= MaxCellsPerQuery && SpanZ <= MaxCellsPerQuery)
		{
			NumCells = SpanX * SpanY * SpanZ;
		}
	}

	if (NumCells > MaxCellsPerQuery || NumCells > int64(CollisionCells.Num()) * 4)
	{
		// Huge or invalid query (or sparse hash): testing every capsule is cheaper than walking empty cells.
		for (int32 EntryIndex = 0; EntryIndex < CollisionEntries.Num(); ++EntryIndex)
		{
			TestEntry(EntryIndex);
		}
	}
	else
	{
		// int64 counters: the loops end even at the edge of the int32 range.
		for (int64 Z = MinCell.Z; Z <= MaxCell.Z; ++Z)
		for (int64 Y = MinCell.Y; Y <= MaxCell.Y; ++Y)
		for (int64 X = MinCell.X; X <= MaxCell.X; ++X)
		{
			if (const TArray<int32>* Cell = CollisionCells.Find(FIntVector(int32(X), int32(Y), int32(Z))))
			{
				for (const int32 EntryIndex : *Cell)
				{
					TestEntry(EntryIndex);
				}
			}
		}
	}

	OutHits.Sort([](const FMechSentinelHit& A, const FMechSentinelHit& B) { return A.Distance < B.Distance; });
	return OutHits.Num();
}
