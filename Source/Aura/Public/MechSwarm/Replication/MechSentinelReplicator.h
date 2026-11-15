// Mech Sentinel Swarm - server side replicator: Mass fragments -> each client's bubble.

#pragma once

#include "CoreMinimal.h"
#include "MassObserverProcessor.h"
#include "MassReplicationProcessor.h"
#include "MechSentinelReplicator.generated.h"

/**
 * Plugged into the engine "Replication" trait (Params -> Replicator Class). UMassReplicationProcessor calls it once per
 * client per chunk. Adds relevant sentinels to the client's bubble, updates them (movement throttled by the trait's
 * UpdateInterval per replication LOD, state / hit / attack changes immediately) and removes them when irrelevant.
 */
UCLASS()
class AURA_API UMechSentinelReplicator : public UMassReplicatorBase
{
	GENERATED_BODY()

public:
	virtual void AddRequirements(FMassEntityQuery& EntityQuery) override;
	virtual void ProcessClientReplication(FMassExecutionContext& Context, FMassReplicationContext& ReplicationContext) override;
};

/**
 * Server: removes a destroyed sentinel from every client bubble right away.
 * The engine only removes destroyed agents from inside UMassReplicationProcessor's per-chunk replicator callback.
 * When every entity a client had in range is destroyed in the same frame (the end of a wave), no chunk is processed
 * for that client, the agent is never removed, and the processor's cleanup asserts on the still-valid agent handle
 * (in Shipping the client keeps a frozen ghost sentinel). Removing the agent here and invalidating its handle makes
 * the engine's later bookkeeping a no-op.
 */
UCLASS()
class AURA_API UMechSentinelReplicationDestroyObserver : public UMassObserverProcessor
{
	GENERATED_BODY()

public:
	UMechSentinelReplicationDestroyObserver();

protected:
	virtual void ConfigureQueries(const TSharedRef<FMassEntityManager>& EntityManager) override;
	virtual void Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context) override;

	FMassEntityQuery EntityQuery;
};
