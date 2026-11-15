// Mech Sentinel Swarm - server side replicator.

#include "MechSwarm/Replication/MechSentinelReplicator.h"

#include "MassExecutionContext.h"
#include "MassReplicationFragments.h"
#include "MassReplicationSubsystem.h"
#include "Mass/EntityFragments.h"
#include "MechSwarm/MassCopies/MassMovementFragments_Copy.h"
#include "MechSwarm/Replication/MechSentinelClientBubble.h"
#include "MechSwarm/Sentinel/MechSentinelFragments.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(MechSentinelReplicator)

void UMechSentinelReplicator::AddRequirements(FMassEntityQuery& EntityQuery)
{
	EntityQuery.AddRequirement<FTransformFragment>(EMassFragmentAccess::ReadOnly);
	EntityQuery.AddRequirement<FMassVelocityFragment_Copy>(EMassFragmentAccess::ReadOnly);
	EntityQuery.AddRequirement<FMechSentinelStateFragment>(EMassFragmentAccess::ReadOnly);
	EntityQuery.AddRequirement<FMechSentinelAttributesFragment>(EMassFragmentAccess::ReadOnly);
	EntityQuery.AddRequirement<FMechSentinelAttackFragment>(EMassFragmentAccess::ReadOnly);
	EntityQuery.AddTagRequirement<FMechSentinelTag>(EMassFragmentPresence::All);
	// FMassReplicatedAgentFragment (ReadWrite) and FMassReplicationParameters are already required by UMassReplicationProcessor.
}

void UMechSentinelReplicator::ProcessClientReplication(FMassExecutionContext& Context, FMassReplicationContext& ReplicationContext)
{
#if UE_REPLICATION_COMPILE_SERVER_CODE
	FMassReplicationSharedFragment* RepSharedFragment = nullptr;
	const FMassReplicationParameters* RepParams = nullptr;
	TConstArrayView<FTransformFragment> TransformList;
	TConstArrayView<FMassVelocityFragment_Copy> VelocityList;
	TConstArrayView<FMechSentinelStateFragment> StateList;
	TConstArrayView<FMechSentinelAttributesFragment> AttributeList;
	TConstArrayView<FMechSentinelAttackFragment> AttackList;
	TArrayView<FMassReplicatedAgentFragment> ReplicatedAgentList;

	auto MakeData = [&](const int32 EntityIdx)
	{
		return FMechSentinelReplicatedData::FromEntity(TransformList[EntityIdx].GetTransform(), VelocityList[EntityIdx].Value,
			StateList[EntityIdx], AttributeList[EntityIdx], AttackList[EntityIdx]);
	};

	auto GetBubble = [&RepSharedFragment](const FMassClientHandle ClientHandle) -> FMechSentinelClientBubbleHandler&
	{
		return RepSharedFragment->GetTypedClientBubbleInfoChecked<AMechSentinelClientBubbleInfo>(ClientHandle).GetSentinelSerializer().Bubble;
	};

	auto CacheViewsCallback = [&](FMassExecutionContext& InContext)
	{
		TransformList = InContext.GetFragmentView<FTransformFragment>();
		VelocityList = InContext.GetFragmentView<FMassVelocityFragment_Copy>();
		StateList = InContext.GetFragmentView<FMechSentinelStateFragment>();
		AttributeList = InContext.GetFragmentView<FMechSentinelAttributesFragment>();
		AttackList = InContext.GetFragmentView<FMechSentinelAttackFragment>();
		ReplicatedAgentList = InContext.GetMutableFragmentView<FMassReplicatedAgentFragment>();
		RepSharedFragment = &InContext.GetMutableSharedFragment<FMassReplicationSharedFragment>();
		RepParams = &InContext.GetConstSharedFragment<FMassReplicationParameters>();
	};

	auto AddEntityCallback = [&](FMassExecutionContext& InContext, const int32 EntityIdx, FReplicatedMechSentinelAgent& InReplicatedAgent, const FMassClientHandle ClientHandle) -> FMassReplicatedAgentHandle
	{
		InReplicatedAgent.Data = MakeData(EntityIdx);
		return GetBubble(ClientHandle).AddAgent(InContext.GetEntity(EntityIdx), InReplicatedAgent);
	};

	auto ModifyEntityCallback = [&](FMassExecutionContext& InContext, const int32 EntityIdx, const EMassLOD::Type LOD, const double Time, const FMassReplicatedAgentHandle Handle, const FMassClientHandle ClientHandle)
	{
		FMechSentinelClientBubbleHandler& Bubble = GetBubble(ClientHandle);
		const FMechSentinelReplicatedData NewData = MakeData(EntityIdx);

		// The agent data in the fragment is per client (UMassReplicationProcessor swaps it in / out per client).
		FMassReplicatedAgentData& AgentData = ReplicatedAgentList[EntityIdx].AgentData;
		const int32 LODIndex = FMath::Clamp(int32(LOD), 0, int32(EMassLOD::Max) - 1);
		const bool bIntervalElapsed = (Time - AgentData.LastUpdateTime) >= RepParams->UpdateInterval[LODIndex];

		// Hits, attacks, state and health changes go out at once; continuous movement is throttled by LOD.
		if (!bIntervalElapsed && !Bubble.GetAgentChecked(Handle).Data.HasDiscreteChange(NewData))
		{
			return;
		}

		if (Bubble.SetAgentData(Handle, NewData))
		{
			AgentData.LastUpdateTime = Time;
		}
	};

	auto RemoveEntityCallback = [&](FMassExecutionContext& InContext, const FMassReplicatedAgentHandle Handle, const FMassClientHandle ClientHandle)
	{
		GetBubble(ClientHandle).RemoveAgentChecked(Handle);
	};

	CalculateClientReplication<FMechSentinelFastArrayItem>(Context, ReplicationContext, CacheViewsCallback, AddEntityCallback, ModifyEntityCallback, RemoveEntityCallback);
#endif // UE_REPLICATION_COMPILE_SERVER_CODE
}

//----------------------------------------------------------------------//
// UMechSentinelReplicationDestroyObserver
//----------------------------------------------------------------------//
UMechSentinelReplicationDestroyObserver::UMechSentinelReplicationDestroyObserver()
	: EntityQuery(*this)
{
	ExecutionFlags = (int32)EProcessorExecutionFlags::Server;
	ObservedTypes.Add(FMassReplicatedAgentFragment::StaticStruct());
	ObservedOperations = EMassObservedOperationFlags::DestroyEntity;
	// Touches the replication subsystem and the bubble actors, like the engine's destruction observer.
	bRequiresGameThreadExecution = true;
}

void UMechSentinelReplicationDestroyObserver::ConfigureQueries(const TSharedRef<FMassEntityManager>& EntityManager)
{
	EntityQuery.AddRequirement<FMassReplicatedAgentFragment>(EMassFragmentAccess::ReadOnly);
	EntityQuery.AddTagRequirement<FMechSentinelTag>(EMassFragmentPresence::All);
}

void UMechSentinelReplicationDestroyObserver::Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context)
{
#if UE_REPLICATION_COMPILE_SERVER_CODE
	UMassReplicationSubsystem* ReplicationSubsystem = UWorld::GetSubsystem<UMassReplicationSubsystem>(EntityManager.GetWorld());
	if (!ReplicationSubsystem)
	{
		return;
	}

	const FMassBubbleInfoClassHandle BubbleClassHandle = ReplicationSubsystem->GetBubbleInfoClassHandle(AMechSentinelClientBubbleInfo::StaticClass());
	if (!ReplicationSubsystem->IsBubbleClassHandleValid(BubbleClassHandle))
	{
		return;
	}

	const TArray<FMassClientHandle>& Clients = ReplicationSubsystem->GetClientReplicationHandles();
	if (Clients.IsEmpty())
	{
		return;
	}

	EntityQuery.ForEachEntityChunk(Context, [ReplicationSubsystem, BubbleClassHandle, &Clients](FMassExecutionContext& Context)
	{
		for (FMassExecutionContext::FEntityIterator EntityIt = Context.CreateEntityIterator(); EntityIt; ++EntityIt)
		{
			const FMassEntityHandle Entity = Context.GetEntity(EntityIt);
			for (const FMassClientHandle& Client : Clients)
			{
				if (!ReplicationSubsystem->IsValidClientHandle(Client))
				{
					continue;
				}

				FMassClientReplicationInfo* ClientInfo = ReplicationSubsystem->GetMutableClientReplicationInfo(Client);
				FMassReplicatedAgentData* AgentData = ClientInfo ? ClientInfo->AgentsData.Find(Entity) : nullptr;
				if (!AgentData || !AgentData->Handle.IsValid())
				{
					continue;
				}

				if (AMechSentinelClientBubbleInfo* Bubble = ReplicationSubsystem->GetTypedClientBubble<AMechSentinelClientBubbleInfo>(BubbleClassHandle, Client))
				{
					Bubble->GetSentinelSerializer().Bubble.RemoveAgent(AgentData->Handle);
				}
				AgentData->Invalidate();
			}
		}
	});
#endif // UE_REPLICATION_COMPILE_SERVER_CODE
}
