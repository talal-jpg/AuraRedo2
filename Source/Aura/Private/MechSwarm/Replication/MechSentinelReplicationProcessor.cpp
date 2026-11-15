// Mech Sentinel Swarm - server replication processor that runs under UE 5.8's Mass processing queue.

#include "MechSwarm/Replication/MechSentinelReplicationProcessor.h"

#include "Engine/World.h"
#include "MassClientBubbleHandler.h"
#include "MassCommonFragments.h"
#include "MassEntityUtils.h"
#include "MassExecutionContext.h"
#include "MassLODSubsystem.h"
#include "MassReplicationFragments.h"
#include "MassReplicationSubsystem.h"
#include "MechSwarm/Replication/MechSentinelReplicator.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(MechSentinelReplicationProcessor)

DEFINE_LOG_CATEGORY_STATIC(LogMechSentinelReplicationProcessor, Log, All);

UMechSentinelReplicationProcessor::UMechSentinelReplicationProcessor()
	: ClientReplicationQuery(*this)
{
	// The engine constructor already set what this processor needs: server only, PostPhysics, game thread (it may
	// spawn the client bubble actors).
}

void UMechSentinelReplicationProcessor::ConfigureQueries(const TSharedRef<FMassEntityManager>& EntityManager)
{
	Super::ConfigureQueries(EntityManager);

	// The engine copies its EntityQuery into every FMassReplicationSharedFragment and adds the replicator's
	// requirements to the copy (UMassReplicationProcessor::PrepareExecution). The same query, as a registered member:
	ClientReplicationQuery.AddRequirement<FMassNetworkIDFragment>(EMassFragmentAccess::ReadOnly);
	ClientReplicationQuery.AddRequirement<FReplicationTemplateIDFragment>(EMassFragmentAccess::ReadOnly);
	ClientReplicationQuery.AddRequirement<FMassReplicationLODFragment>(EMassFragmentAccess::ReadWrite);
	ClientReplicationQuery.AddRequirement<FMassReplicatedAgentFragment>(EMassFragmentAccess::ReadWrite);
	ClientReplicationQuery.AddConstSharedRequirement<FMassReplicationParameters>();
	ClientReplicationQuery.AddSharedRequirement<FMassReplicationSharedFragment>(EMassFragmentAccess::ReadWrite);
	// AddRequirements only adds to the query it is given, so the class default object can do it.
	GetMutableDefault<UMechSentinelReplicator>()->AddRequirements(ClientReplicationQuery);
}

void UMechSentinelReplicationProcessor::ReportUnsupportedReplicators(FMassEntityManager& EntityManager)
{
	if (bReportedUnsupportedReplicator)
	{
		return;
	}

	EntityManager.ForEachSharedFragment<FMassReplicationSharedFragment>([this](FMassReplicationSharedFragment& RepSharedFragment)
	{
		if (!bReportedUnsupportedReplicator && RepSharedFragment.CachedReplicator && !RepSharedFragment.CachedReplicator->IsA<UMechSentinelReplicator>())
		{
			bReportedUnsupportedReplicator = true;
			UE_LOG(LogMechSentinelReplicationProcessor, Error,
				TEXT("%s replaces UMassReplicationProcessor (see Config/DefaultMass.ini) and only runs UMechSentinelReplicator. Entities using %s are not replicated."),
				*GetName(), *RepSharedFragment.CachedReplicator->GetClass()->GetName());
		}
	});
}

void UMechSentinelReplicationProcessor::Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context)
{
#if UE_REPLICATION_COMPILE_SERVER_CODE
	// UMassReplicationProcessor::Execute (UE 5.8.2), step for step, except for the "ProcessClientReplication" step and
	// the debug LOD display (mass.debug.ClientReplicationLOD), which ran the same unregistered queries.
	UWorld* World = EntityManager.GetWorld();
	check(World);
	check(ReplicationSubsystem);

	{
		QUICK_SCOPE_CYCLE_COUNTER(MechSentinelReplicationProcessor_Preparation);
		// Synchronizes clients and viewers and caches each fragment's bubbles. It also builds the per-fragment queries
		// this processor never runs, which costs nothing.
		PrepareExecution(EntityManager);
	}

	ReportUnsupportedReplicators(EntityManager);

	const UMassLODSubsystem& LODSubsystem = Context.GetSubsystemChecked<UMassLODSubsystem>();
	const TArray<FViewerInfo>& AllViewersInfo = LODSubsystem.GetViewers();
	const TArray<FMassClientHandle>& ClientHandles = ReplicationSubsystem->GetClientReplicationHandles();
	for (const FMassClientHandle ClientHandle : ClientHandles)
	{
		if (ReplicationSubsystem->IsValidClientHandle(ClientHandle) == false)
		{
			continue;
		}

		FMassClientReplicationInfo& ClientReplicationInfo = ReplicationSubsystem->GetMutableClientReplicationInfoChecked(ClientHandle);

		// Figure out all viewers of this client.
		TArray<FViewerInfo> Viewers;
		for (const FMassViewerHandle ClientViewerHandle : ClientReplicationInfo.Handles)
		{
			const FViewerInfo* ViewerInfo = AllViewersInfo.FindByPredicate([ClientViewerHandle](const FViewerInfo& Info) { return ClientViewerHandle == Info.Handle; });
			if (ensureMsgf(ViewerInfo, TEXT("Expecting to find the client viewer handle in the all viewers info list")))
			{
				Viewers.Add(*ViewerInfo);
			}
		}

		// Prepare the LOD collector and calculator, and remember the biggest LOD distance.
		float MaxLODDistance = 0.0f;
		EntityManager.ForEachSharedFragment<FMassReplicationSharedFragment>([&Viewers, &MaxLODDistance](FMassReplicationSharedFragment& RepSharedFragment)
		{
			RepSharedFragment.LODCollector.PrepareExecution(Viewers);
			RepSharedFragment.LODCalculator.PrepareExecution(Viewers);
			MaxLODDistance = FMath::Max(MaxLODDistance, RepSharedFragment.LODCalculator.GetMaxLODDistance());
		});

		// Fetch all the entities to process.
		const FVector HalfExtent(MaxLODDistance, MaxLODDistance, 0.0f);
		TArray<FMassEntityHandle> EntitiesInRange;
		for (const FViewerInfo& Viewer : Viewers)
		{
			const FBox Bounds(Viewer.Location - HalfExtent, Viewer.Location + HalfExtent);
			ReplicationSubsystem->GetGrid().Query(Bounds, EntitiesInRange);
		}

		EntitiesInRange.Append(ClientReplicationInfo.HandledEntities);
		TArray<FMassArchetypeEntityCollection> EntitySets;
		UE::Mass::Utils::CreateEntityCollections(Context.GetEntityManagerChecked(), EntitiesInRange, FMassArchetypeEntityCollection::FoldDuplicates, EntitySets);

		TArray<FMassEntityHandle> EntitiesHandledThisFrame;

		for (FMassArchetypeEntityCollection& Set : EntitySets)
		{
			checkf(Set.IsEmpty() == false, TEXT("We don't expect to get empty collections from UE::Mass::Utils::CreateEntityCollections"));

			Context.SetEntityCollection(Set);

			// A deduplicated list of the entities handled, so ClientReplicationInfo.HandledEntities does not grow
			// over several frames.
			Set.ExportEntityHandles(EntitiesHandledThisFrame);

			{
				QUICK_SCOPE_CYCLE_COUNTER(MechSentinelReplicationProcessor_SyncToMass);
				SyncClientData.ForEachEntityChunk(Context, [&ClientReplicationInfo](FMassExecutionContext& Context)
				{
					const TArrayView<FMassReplicationLODFragment> ViewerLODList = Context.GetMutableFragmentView<FMassReplicationLODFragment>();
					const TArrayView<FMassReplicatedAgentFragment> ReplicatedAgentList = Context.GetMutableFragmentView<FMassReplicatedAgentFragment>();

					for (FMassExecutionContext::FEntityIterator EntityIt = Context.CreateEntityIterator(); EntityIt; ++EntityIt)
					{
						const FMassEntityHandle EntityHandle = Context.GetEntity(EntityIt);
						FMassReplicatedAgentFragment& AgentFragment = ReplicatedAgentList[EntityIt];
						FMassReplicationLODFragment& LODFragment = ViewerLODList[EntityIt];

						if (const FMassReplicatedAgentData* AgentData = ClientReplicationInfo.AgentsData.Find(EntityHandle))
						{
							LODFragment.LOD = AgentData->LOD;
							AgentFragment.AgentData = *AgentData;
						}
						else
						{
							LODFragment.LOD = EMassLOD::Off;
							AgentFragment.AgentData.Invalidate();
						}
					}
				});
			}

			{
				QUICK_SCOPE_CYCLE_COUNTER(MechSentinelReplicationProcessor_LODCollection);
				CollectViewerInfoQuery.ForEachEntityChunk(Context, [](FMassExecutionContext& Context)
				{
					const TConstArrayView<FTransformFragment> LocationList = Context.GetFragmentView<FTransformFragment>();
					const TArrayView<FMassReplicationViewerInfoFragment> ViewersInfoList = Context.GetMutableFragmentView<FMassReplicationViewerInfoFragment>();
					FMassReplicationSharedFragment& RepSharedFragment = Context.GetMutableSharedFragment<FMassReplicationSharedFragment>();
					RepSharedFragment.LODCollector.CollectLODInfo(Context, LocationList, ViewersInfoList, ViewersInfoList);
				});
			}

			{
				QUICK_SCOPE_CYCLE_COUNTER(MechSentinelReplicationProcessor_LODCalculation);
				CalculateLODQuery.ForEachEntityChunk(Context, [](FMassExecutionContext& Context)
				{
					const TConstArrayView<FMassReplicationViewerInfoFragment> ViewersInfoList = Context.GetFragmentView<FMassReplicationViewerInfoFragment>();
					const TArrayView<FMassReplicationLODFragment> ViewerLODList = Context.GetMutableFragmentView<FMassReplicationLODFragment>();
					FMassReplicationSharedFragment& RepSharedFragment = Context.GetMutableSharedFragment<FMassReplicationSharedFragment>();
					RepSharedFragment.LODCalculator.CalculateLOD(Context, ViewersInfoList, ViewerLODList, ViewersInfoList);
				});
			}
			Context.ClearEntityCollection();
		}

		{
			QUICK_SCOPE_CYCLE_COUNTER(MechSentinelReplicationProcessor_LODAdjustDistance);
			EntityManager.ForEachSharedFragment<FMassReplicationSharedFragment>([](FMassReplicationSharedFragment& RepSharedFragment)
			{
				RepSharedFragment.bHasAdjustedDistancesFromCount = RepSharedFragment.LODCalculator.AdjustDistancesFromCount();
			});
		}

		for (FMassArchetypeEntityCollection& Set : EntitySets)
		{
			Context.SetEntityCollection(Set);

			{
				QUICK_SCOPE_CYCLE_COUNTER(MechSentinelReplicationProcessor_LODAdjustLODFromCount);
				AdjustLODDistancesQuery.ForEachEntityChunk(Context, [](FMassExecutionContext& Context)
				{
					const TConstArrayView<FMassReplicationViewerInfoFragment> ViewersInfoList = Context.GetFragmentView<FMassReplicationViewerInfoFragment>();
					const TArrayView<FMassReplicationLODFragment> ViewerLODList = Context.GetMutableFragmentView<FMassReplicationLODFragment>();
					FMassReplicationSharedFragment& RepSharedFragment = Context.GetMutableSharedFragment<FMassReplicationSharedFragment>();
					RepSharedFragment.LODCalculator.AdjustLODFromCount(Context, ViewersInfoList, ViewerLODList, ViewersInfoList);
				});
			}

			{
				QUICK_SCOPE_CYCLE_COUNTER(MechSentinelReplicationProcessor_ProcessClientReplication);
				FMassReplicationContext ReplicationContext(*World, LODSubsystem, *ReplicationSubsystem);
				// The engine runs RepSharedFragment.EntityQuery (one unregistered copy per shared fragment) here. The
				// registered query reaches the same chunks: each chunk carries its shared fragment, so the replicator and
				// the client handle are taken from there, which is what the copies' chunk filter selected.
				ClientReplicationQuery.ForEachEntityChunk(Context, [&ReplicationContext, ClientHandle](FMassExecutionContext& Context)
				{
					FMassReplicationSharedFragment& RepSharedFragment = Context.GetMutableSharedFragment<FMassReplicationSharedFragment>();
					// PrepareExecution skipped (and reported) fragments without a bubble class; their bubbles were never cached.
					if (!RepSharedFragment.BubbleInfoClassHandle.IsValid() || !RepSharedFragment.CachedReplicator)
					{
						return;
					}

					RepSharedFragment.CurrentClientHandle = ClientHandle;
					RepSharedFragment.CachedReplicator->ProcessClientReplication(Context, ReplicationContext);
				});
			}

			{
				QUICK_SCOPE_CYCLE_COUNTER(MechSentinelReplicationProcessor_SyncFromMass);
				SyncClientData.ForEachEntityChunk(Context, [&ClientReplicationInfo](FMassExecutionContext& Context)
				{
					const TArrayView<FMassReplicatedAgentFragment> ReplicatedAgentList = Context.GetMutableFragmentView<FMassReplicatedAgentFragment>();

					for (FMassExecutionContext::FEntityIterator EntityIt = Context.CreateEntityIterator(); EntityIt; ++EntityIt)
					{
						const FMassEntityHandle EntityHandle = Context.GetEntity(EntityIt);
						const FMassReplicatedAgentFragment& AgentFragment = ReplicatedAgentList[EntityIt];
						ClientReplicationInfo.AgentsData.Add(EntityHandle, AgentFragment.AgentData);
					}
				});
			}

			Context.ClearEntityCollection();
		}

		// Moving EntitiesHandledThisFrame resets it.
		ClientReplicationInfo.HandledEntities = MoveTemp(EntitiesHandledThisFrame);

		// Drop the agent data that is not relevant any more (EMassLOD::Off or pending destruction).
		for (FMassReplicationAgentDataMap::TIterator It = ClientReplicationInfo.AgentsData.CreateIterator(); It; ++It)
		{
			const FMassReplicatedAgentData& AgentData = It.Value();
			if (AgentData.bPendingDestruction || AgentData.LOD == EMassLOD::Off)
			{
				checkf(!AgentData.Handle.IsValid(), TEXT("This replicated agent should have been removed from this client and was not"));
				It.RemoveCurrent();
			}
		}
	}
#endif // UE_REPLICATION_COMPILE_SERVER_CODE
}
