// Mech Sentinel Swarm - project-owned re-implementation of the MassMovement processors.
// Mirrors (by role): UMassApplyForceProcessor and UMassApplyMovementProcessor.

#pragma once

#include "CoreMinimal.h"
#include "MassProcessor.h"
#include "MassEntityQuery.h"
#include "MassMovementProcessors_Copy.generated.h"

/**
 * Clamps the desired velocity to the allowed speed / plane, and drops the accumulated force of entities that
 * UMassApplyMovementProcessor_Copy will not integrate (custom movement). The force itself is applied to the
 * velocity by UMassApplyMovementProcessor_Copy.
 * Runs on the authority only (server / standalone); clients get positions from replication.
 */
UCLASS()
class AURA_API UMassApplyForceProcessor_Copy : public UMassProcessor
{
	GENERATED_BODY()

public:
	UMassApplyForceProcessor_Copy();

protected:
	virtual void ConfigureQueries(const TSharedRef<FMassEntityManager>& EntityManager) override;
	virtual void Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context) override;

	FMassEntityQuery EntityQuery;
};

/**
 * Moves velocity toward the desired velocity (acceleration limited), adds the accumulated force (acceleration)
 * and integrates the transform location.
 * Entities tagged FMassCustomMovementTag_Copy are skipped (someone else owns their position).
 */
UCLASS()
class AURA_API UMassApplyMovementProcessor_Copy : public UMassProcessor
{
	GENERATED_BODY()

public:
	UMassApplyMovementProcessor_Copy();

protected:
	virtual void ConfigureQueries(const TSharedRef<FMassEntityManager>& EntityManager) override;
	virtual void Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context) override;

	FMassEntityQuery EntityQuery;
};
