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

#include UE_INLINE_GENERATED_CPP_BY_NAME(MechSentinelSwarmSubsystem)

DEFINE_LOG_CATEGORY_STATIC(LogMechSentinel, Log, All);

namespace MechSwarm::SubsystemPrivate
{
	template<typename TTag>
	void SetMassTag(FMassEntityManager& EntityManager, const FMassEntityHandle Entity, const bool bPresent)
	{
		const FMassEntityView View(EntityManager, Entity);
		if (View.HasTag<TTag>() == bPresent)
		{
			return;
		}

		// Structural changes are not allowed while processors run: go through the command buffer then.
		if (EntityManager.IsProcessing())
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
	if (Params.BubbleInfoClass.Get() != AMechSentinelClientBubbleInfo::StaticClass() || !Params.ReplicatorClass || !Params.ReplicatorClass->IsChildOf(UMechSentinelReplicator::StaticClass()))
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
	Registration.Points = Points;
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

TConstArrayView<FMechSentinelFallbackPoint> UMechSentinelSwarmSubsystem::GetFallbackTargets(const FName SwarmGroup) const
{
	if (const TArray<FMechSentinelFallbackPoint>* Points = FallbacksByGroup.Find(SwarmGroup))
	{
		return *Points;
	}
	return TConstArrayView<FMechSentinelFallbackPoint>();
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

	bool bStoredDurationEffect = false;
	if (Spec.Def->DurationPolicy != EGameplayEffectDurationType::Instant && AppliedHandle.IsValid())
	{
		if (const FActiveGameplayEffect* ActiveEffect = ProxyASC->GetActiveGameplayEffect(AppliedHandle))
		{
			if (ActiveEffect->GetPeriod() > 0.f)
			{
				UE_LOG(LogMechSentinel, Warning, TEXT("%s is periodic. Periodic effects are not persisted on sentinels; use an instant effect applied repeatedly for damage over time."), *GetNameSafe(Spec.Def));
			}
			else
			{
				const TSubclassOf<UGameplayEffect> EffectClass = Spec.Def->GetClass();
				FMechSentinelActiveEffect* Entry = GAS->ActiveEffects.FindByPredicate([EffectClass](const FMechSentinelActiveEffect& Existing)
				{
					return Existing.EffectClass == EffectClass;
				});
				if (!Entry)
				{
					Entry = &GAS->ActiveEffects.AddDefaulted_GetRef();
				}

				// Same class again refreshes the stored effect with what GAS resolved (respects the GE stacking setup).
				const UWorld* World = GetWorld();
				Entry->EffectClass = EffectClass;
				Entry->Level = ActiveEffect->Spec.GetLevel();
				Entry->RemainingTime = ActiveEffect->GetTimeRemaining(World ? World->GetTimeSeconds() : 0.f);
				Entry->SetByCallerMagnitudes = ActiveEffect->Spec.SetByCallerTagMagnitudes;
				Entry->InstigatorASC = Spec.GetEffectContext().GetInstigatorAbilitySystemComponent();
				bStoredDurationEffect = true;
			}
		}
	}

	const float Damage = Proxy->ReadBack(*Attributes, *GAS);
	Proxy->Unload();

	// Pass 2: re-evaluate the current values from the updated effect list (no double counting of a refreshed effect).
	if (bStoredDurationEffect)
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

	Proxy->LoadEntity(*Attributes, *GAS, View.HasTag<FMechSentinelAttackingTag>());
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
		if (State->State != EMechSentinelState::Dead)
		{
			const FMechSentinelParameters* Params = View.GetConstSharedFragmentDataPtr<FMechSentinelParameters>();
			State->State = EMechSentinelState::Dead;
			State->TimeInState = 0.f;
			State->DeathTimeRemaining = Params ? Params->DeathFallDuration : 2.f;
			GAS->OwnedTags.AddTag(MechSentinelTags::State_Sentinel_Dead);
			// Death owns the position from now on (fall), default movement must leave it alone.
			SetMassTag<FMechSentinelDeadTag>(EntityManager, Entity, true);
			SetMassTag<FMassCustomMovementTag_Copy>(EntityManager, Entity, true);
			SetMassTag<FMechSentinelAttackingTag>(EntityManager, Entity, false);
			SetMassTag<FMechSentinelStunnedTag>(EntityManager, Entity, false);

			const FVector Location = View.GetFragmentData<FTransformFragment>().GetTransform().GetLocation();
			OnSentinelKilled.Broadcast(FMechSentinelHandle(Entity), Location, Instigator);
		}
		return;
	}

	const bool bStunned = GAS->OwnedTags.HasTagExact(MechSentinelTags::State_Sentinel_Stunned);
	SetMassTag<FMechSentinelStunnedTag>(EntityManager, Entity, bStunned);
	if (bStunned)
	{
		if (State->State != EMechSentinelState::Stunned)
		{
			State->State = EMechSentinelState::Stunned;
			State->TimeInState = 0.f;
			SetMassTag<FMechSentinelAttackingTag>(EntityManager, Entity, false);
		}
	}
	else if (State->State == EMechSentinelState::Stunned)
	{
		State->State = EMechSentinelState::Seeking;
		State->TimeInState = 0.f;
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
	const float InvCellSize = 1.f / CollisionCellSize;
	const FIntVector MinCell = ToCell(Min, InvCellSize);
	const FIntVector MaxCell = ToCell(Max, InvCellSize);
	const int64 NumCells = int64(MaxCell.X - MinCell.X + 1) * int64(MaxCell.Y - MinCell.Y + 1) * int64(MaxCell.Z - MinCell.Z + 1);

	if (NumCells > MaxCellsPerQuery || NumCells > CollisionCells.Num() * 4)
	{
		// Huge query (or sparse hash): testing every capsule is cheaper than walking empty cells.
		for (int32 EntryIndex = 0; EntryIndex < CollisionEntries.Num(); ++EntryIndex)
		{
			TestEntry(EntryIndex);
		}
	}
	else
	{
		for (int32 Z = MinCell.Z; Z <= MaxCell.Z; ++Z)
		for (int32 Y = MinCell.Y; Y <= MaxCell.Y; ++Y)
		for (int32 X = MinCell.X; X <= MaxCell.X; ++X)
		{
			if (const TArray<int32>* Cell = CollisionCells.Find(FIntVector(X, Y, Z)))
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
