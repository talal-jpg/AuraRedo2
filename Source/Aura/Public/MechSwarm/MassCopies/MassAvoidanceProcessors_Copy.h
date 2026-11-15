// Mech Sentinel Swarm - project-owned re-implementation of UMassMovingAvoidanceProcessor (3D variant).

#pragma once

#include "CoreMinimal.h"
#include "MassProcessor.h"
#include "MassEntityQuery.h"
#include "MassAvoidanceProcessors_Copy.generated.h"

/**
 * Agent-vs-agent avoidance. Gathers every avoiding agent into a 3D spatial hash, then for each agent sums
 * a predictive separation acceleration from its nearest neighbours into FMassForceFragment_Copy.
 * Authority only (server / standalone).
 */
UCLASS()
class AURA_API UMassMovingAvoidanceProcessor_Copy : public UMassProcessor
{
	GENERATED_BODY()

public:
	UMassMovingAvoidanceProcessor_Copy();

protected:
	virtual void ConfigureQueries(const TSharedRef<FMassEntityManager>& EntityManager) override;
	virtual void Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context) override;

	FMassEntityQuery EntityQuery;

private:
	struct FAgentSample
	{
		FVector Position;
		FVector Velocity;
	};

	/** Scratch buffers kept between frames to avoid reallocations. */
	TArray<FAgentSample> Samples;
	TMap<FIntVector, TArray<int32>> Grid;
};
