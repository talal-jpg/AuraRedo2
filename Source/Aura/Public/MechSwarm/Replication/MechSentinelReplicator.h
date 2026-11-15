// Mech Sentinel Swarm - server side replicator: Mass fragments -> each client's bubble.

#pragma once

#include "CoreMinimal.h"
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
