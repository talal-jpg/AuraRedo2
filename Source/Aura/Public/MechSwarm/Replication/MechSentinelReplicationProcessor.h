// Mech Sentinel Swarm - server replication processor that runs under UE 5.8's Mass processing queue.

#pragma once

#include "CoreMinimal.h"
#include "MassReplicationProcessor.h"
#include "MechSentinelReplicationProcessor.generated.h"

/**
 * Takes over from the engine's UMassReplicationProcessor, which Config/DefaultMass.ini switches off.
 *
 * Why: UE 5.8.2's processor runs each replicator through a query it copies into every FMassReplicationSharedFragment.
 * A processor only owns queries that are its own member variables (UMassProcessor::RegisterQuery checks the address),
 * so that copy can never be registered, and 5.8's Mass processing queue (mass.UseProcessingQueue, on by default)
 * asserts on it: "Query not found! Processor attempting to run a query it doesn't own" (MassProcessingQueueTypes.cpp,
 * from MassReplicationProcessor.cpp:323). A server crashed as soon as a client was connected and sentinels spawned.
 *
 * What: the same steps as the engine's Execute (client sync, LOD, replication, sync back), except that the replicator
 * runs through ClientReplicationQuery, a member query registered with this processor: the engine's per-replicator
 * requirements plus UMechSentinelReplicator's. Registered queries also tell the queue which fragments this processor
 * reads, so it is not run alongside processors that write them. Only UMechSentinelReplicator is supported, which is the
 * only replicator in this project; others are reported once and skipped.
 *
 * Remove this class and the DefaultMass.ini lines once the engine registers its replication query.
 */
UCLASS()
class AURA_API UMechSentinelReplicationProcessor : public UMassReplicationProcessor
{
	GENERATED_BODY()

public:
	UMechSentinelReplicationProcessor();

protected:
	virtual void ConfigureQueries(const TSharedRef<FMassEntityManager>& EntityManager) override;
	virtual void Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context) override;

	/** UMassReplicationProcessor::EntityQuery's requirements plus UMechSentinelReplicator::AddRequirements. */
	FMassEntityQuery ClientReplicationQuery;

private:
	/** Logs once when an entity type replicates through another replicator, which this processor cannot run. */
	void ReportUnsupportedReplicators(FMassEntityManager& EntityManager);

	bool bReportedUnsupportedReplicator = false;
};
