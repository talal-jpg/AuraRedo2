// Mech Sentinel Swarm - 3D obstacle avoidance of live sentinels (hex platforms, boxes). Authority only.

#pragma once

#include "CoreMinimal.h"
#include "MassEntityQuery.h"
#include "MassProcessor.h"
#include "MechSentinelObstacleAvoidanceProcessor.generated.h"

/**
 * Keeps live sentinels out of the obstacles registered in UMechSentinelObstacleSubsystem (hex platforms, boxes).
 * Authority (standalone / server), Avoidance group after UMassMovingAvoidanceProcessor_Copy, game thread (actors change
 * the registry on the game thread). Per sentinel, for every obstacle within reach (see FMechSentinelObstacleAvoidanceParameters):
 *  1. Force_Copy: a push out of the cushion around the sentinel's hard shell plus damping of its velocity into the
 *     obstacle, and the part of the agent avoidance push that points into the obstacle is taken out;
 *  2. a sentinel whose centre is inside an obstacle flies out through the cheapest exit (DesiredVelocity);
 *  3. otherwise the desired velocity is cast ahead against the obstacles grown by the shell and cushion, and slid along
 *     the face it would hit, or turned round the obstacle (over the rim, over or under a side) when the goal lies behind
 *     it; a second cast slides along the next obstacle.
 * The goal is recomputed as UMechSentinelSteeringProcessor does. No obstacles registered = nothing to do.
 * Console: mech.Sentinel.DebugObstacles 1 draws the registered shapes, 2 also the sentinels near them (non-shipping).
 */
UCLASS()
class AURA_API UMechSentinelObstacleAvoidanceProcessor : public UMassProcessor
{
	GENERATED_BODY()

public:
	UMechSentinelObstacleAvoidanceProcessor();

protected:
	virtual void ConfigureQueries(const TSharedRef<FMassEntityManager>& EntityManager) override;
	virtual void Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context) override;

	FMassEntityQuery EntityQuery;
};
