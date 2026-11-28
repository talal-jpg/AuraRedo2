// Mech Sentinel Swarm - MassReplication client bubble.

#include "MechSwarm/Replication/MechSentinelClientBubble.h"

#include "Algo/AllOf.h"
#include "Engine/World.h"
#include "MassEntityManager.h"
#include "MassExecutionContext.h"
#include "MassReplicationSubsystem.h"
#include "MassSpawnerSubsystem.h"
#include "Mass/EntityFragments.h"
#include "MechSwarm/Core/MechSentinelSwarmSubsystem.h"
#include "MechSwarm/MassCopies/MassMovementFragments_Copy.h"
#include "MechSwarm/Sentinel/MechSentinelFragments.h"
#include "Net/UnrealNetwork.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(MechSentinelClientBubble)

DEFINE_LOG_CATEGORY_STATIC(LogMechSentinelReplication, Log, All);

//----------------------------------------------------------------------//
// FMechSentinelClientBubbleHandler - server
//----------------------------------------------------------------------//
#if UE_REPLICATION_COMPILE_SERVER_CODE
bool FMechSentinelClientBubbleHandler::SetAgentData(const FMassReplicatedAgentHandle Handle, const FMechSentinelReplicatedData& NewData)
{
	FMechSentinelFastArrayItem& Item = GetAgentItem(Handle);
	if (!Item.Agent.Data.DiffersFrom(NewData))
	{
		return false;
	}

	Item.Agent.Data = NewData;
	MarkItemDirty(Item);
	return true;
}
#endif // UE_REPLICATION_COMPILE_SERVER_CODE

//----------------------------------------------------------------------//
// FMechSentinelClientBubbleHandler - client
//----------------------------------------------------------------------//
#if UE_REPLICATION_COMPILE_CLIENT_CODE
void FMechSentinelClientBubbleHandler::FilterSpawnableAgents(const TArrayView<int32> Indices, TArray<int32>& OutSpawnable) const
{
	OutSpawnable.Reset(Indices.Num());

	const UMassSpawnerSubsystem* SpawnerSubsystem = Serializer->GetSpawnerSubsystem();
	if (!SpawnerSubsystem)
	{
		return;
	}

	auto HasTemplate = [this, SpawnerSubsystem](const int32 Index)
	{
		return SpawnerSubsystem->GetMassEntityTemplate((*Agents)[Index].Agent.GetTemplateID()) != nullptr;
	};

	// Agents can arrive before the level-placed wave spawner built its template on this client: build what is missing.
	if (!Algo::AllOf(Indices, HasTemplate))
	{
		if (UMechSentinelSwarmSubsystem* Swarm = UMechSentinelSwarmSubsystem::Get(Serializer->GetWorld()))
		{
			Swarm->EnsureTemplatesBuilt();
		}
	}

	for (const int32 Index : Indices)
	{
		if (HasTemplate(Index))
		{
			OutSpawnable.Add(Index);
		}
		else
		{
			UE_LOG(LogMechSentinelReplication, Warning,
				TEXT("Replicated sentinel uses an entity template unknown on this client. Is the entity config referenced by a level-placed AMechSentinelWaveSpawner (or UMechSentinelSwarmSubsystem::RegisterEntityConfig on clients)? It will spawn once the template exists."));
		}
	}
}

void FMechSentinelClientBubbleHandler::PreReplicatedRemove(const TArrayView<int32> RemovedIndices, int32 FinalSize)
{
	// Agents whose add was postponed (missing template) never got an entity info entry; the base class expects one.
	const UMassReplicationSubsystem* ReplicationSubsystem = Serializer->GetReplicationSubsystem();
	TArray<int32> KnownIndices;
	KnownIndices.Reserve(RemovedIndices.Num());
	for (const int32 Index : RemovedIndices)
	{
		if (ReplicationSubsystem && ReplicationSubsystem->FindMassEntityInfo((*Agents)[Index].Agent.GetNetID()))
		{
			KnownIndices.Add(Index);
		}
	}

	Super::PreReplicatedRemove(KnownIndices, FinalSize);
}

void FMechSentinelClientBubbleHandler::PostReplicatedAdd(const TArrayView<int32> AddedIndices, int32 FinalSize)
{
	TArray<int32> Spawnable;
	FilterSpawnableAgents(AddedIndices, Spawnable);
	if (Spawnable.IsEmpty())
	{
		return;
	}

	auto AddRequirementsForSpawnQuery = [](FMassEntityQuery& InQuery)
	{
		InQuery.AddRequirement<FTransformFragment>(EMassFragmentAccess::ReadWrite);
	};

	auto CacheFragmentViewsForSpawnQuery = [](FMassExecutionContext& InExecContext)
	{
		// Everything is written through the entity view in SetSpawnedEntityData.
	};

	auto SetSpawnedEntityData = [this](const FMassEntityView& EntityView, const FReplicatedMechSentinelAgent& ReplicatedAgent, const int32 EntityIdx)
	{
		ApplyToEntity(EntityView, ReplicatedAgent, /*bJustSpawned*/true);
	};

	auto SetModifiedEntityData = [this](const FMassEntityView& EntityView, const FReplicatedMechSentinelAgent& ReplicatedAgent)
	{
		ApplyToEntity(EntityView, ReplicatedAgent, /*bJustSpawned*/false);
	};

	PostReplicatedAddHelper(Spawnable, AddRequirementsForSpawnQuery, CacheFragmentViewsForSpawnQuery, SetSpawnedEntityData, SetModifiedEntityData);
}

void FMechSentinelClientBubbleHandler::PostReplicatedChange(const TArrayView<int32> ChangedIndices, int32 FinalSize)
{
	// Same as the engine helper, but tolerant to agents whose add was postponed (they are added now instead).
	FMassEntityManager& EntityManager = Serializer->GetEntityManagerChecked();
	const UMassReplicationSubsystem* ReplicationSubsystem = Serializer->GetReplicationSubsystem();
	if (!ReplicationSubsystem)
	{
		return;
	}

	TArray<int32> LateAdds;
	for (const int32 Index : ChangedIndices)
	{
		const FMechSentinelFastArrayItem& Item = (*Agents)[Index];
		const FMassReplicationEntityInfo* EntityInfo = ReplicationSubsystem->FindMassEntityInfo(Item.Agent.GetNetID());
		if (!EntityInfo)
		{
			LateAdds.Add(Index);
			continue;
		}

		if (EntityInfo->ReplicationID != Item.ReplicationID || !EntityManager.IsEntityActive(EntityInfo->Entity))
		{
			continue;
		}

		const FMassEntityView EntityView(EntityManager, EntityInfo->Entity);
		ApplyToEntity(EntityView, Item.Agent, /*bJustSpawned*/false);
	}

	if (!LateAdds.IsEmpty())
	{
		PostReplicatedAdd(LateAdds, FinalSize);
	}
}

void FMechSentinelClientBubbleHandler::ApplyToEntity(const FMassEntityView& EntityView, const FReplicatedMechSentinelAgent& Agent, const bool bJustSpawned) const
{
	const FMechSentinelReplicatedData& Data = Agent.Data;
	const FVector Location = Data.Position;
	const FVector Velocity = Data.Velocity;
	const FQuat Rotation = Data.GetRotation();

	const UWorld* World = Serializer->GetWorld();
	FMechSentinelNetSmoothingFragment* Smoothing = EntityView.GetFragmentDataPtr<FMechSentinelNetSmoothingFragment>();
	if (Smoothing)
	{
		Smoothing->NetLocation = Location;
		Smoothing->NetVelocity = Velocity;
		Smoothing->NetRotation = Rotation;
		Smoothing->NetReceiveTime = World ? World->GetTimeSeconds() : 0.0;
		Smoothing->bHasSample = true;
	}

	// New entities appear where the server has them; afterwards UMechSentinelNetSmoothingProcessor eases toward the samples.
	if (bJustSpawned || !Smoothing)
	{
		if (FTransformFragment* Transform = EntityView.GetFragmentDataPtr<FTransformFragment>())
		{
			Transform->GetMutableTransform().SetLocation(Location);
			Transform->GetMutableTransform().SetRotation(Rotation);
		}
	}

	if (FMassVelocityFragment_Copy* VelocityFragment = EntityView.GetFragmentDataPtr<FMassVelocityFragment_Copy>())
	{
		VelocityFragment->Value = Velocity;
	}

	if (FMechSentinelStateFragment* State = EntityView.GetFragmentDataPtr<FMechSentinelStateFragment>())
	{
		const EMechSentinelState NewState = EMechSentinelState(FMath::Min<uint8>(Data.State, uint8(EMechSentinelState::Dead)));
		if (State->State != NewState)
		{
			State->State = NewState;
			State->TimeInState = 0.f;
		}
		if (!bJustSpawned && State->HitSerial != Data.HitSerial)
		{
			State->HitFlash = 1.f;
		}
		State->HitSerial = Data.HitSerial;
		// A level, not an event: always the server's current value (the visuals fade toward it).
		State->BuffMask = uint8(Data.BuffMask & MechSentinelSelfBuff::AllBits);
	}

	if (FMechSentinelAttackFragment* Attack = EntityView.GetFragmentDataPtr<FMechSentinelAttackFragment>())
	{
		if (!bJustSpawned && Attack->AttackSerial != Data.AttackSerial)
		{
			Attack->AttackGlow = 1.f;
		}
		Attack->AttackSerial = Data.AttackSerial;
	}

	// Clients only need the fraction (visuals); other attributes stay server side.
	if (FMechSentinelAttributesFragment* Attributes = EntityView.GetFragmentDataPtr<FMechSentinelAttributesFragment>())
	{
		Attributes->Health = Attributes->MaxHealth * (float(Data.HealthByte) / 255.f);
	}
}
#endif // UE_REPLICATION_COMPILE_CLIENT_CODE

//----------------------------------------------------------------------//
// AMechSentinelClientBubbleInfo
//----------------------------------------------------------------------//
AMechSentinelClientBubbleInfo::AMechSentinelClientBubbleInfo(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	Serializers.Add(&SentinelSerializer);

	// Swarm movement: 20 Hz bubble updates; per-entity rates are further limited by the replication LOD update intervals.
	SetNetUpdateFrequency(20.f);
}

void AMechSentinelClientBubbleInfo::Tick(float DeltaTime)
{
	// A client keeps its copy of this replicated actor through a seamless travel (FSeamlessTravelHandler keeps every
	// non-startup actor it doesn't own, World.cpp), and garbage collection then nulls the serializer's World (a Transient
	// UPROPERTY) with the old world: the engine handler's check(World) (MassClientBubbleHandler.h:736) took the client
	// down on the seamless return to the lobby (as_80 LM1.13, 2026-11-28). The new world's server makes new bubbles; this
	// stale copy only waits for its channel to close
	const UWorld* SerializerWorld = SentinelSerializer.GetWorld();

	if (!SerializerWorld || SerializerWorld != GetWorld())
	{
		return;
	}

	Super::Tick(DeltaTime);
}

void AMechSentinelClientBubbleInfo::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);

	FDoRepLifetimeParams SharedParams;
	SharedParams.bIsPushBased = true;

	// Fast arrays ignore the push model; the flag only keeps the property cheap when push model is enabled.
	DOREPLIFETIME_WITH_PARAMS_FAST(AMechSentinelClientBubbleInfo, SentinelSerializer, SharedParams);
}
