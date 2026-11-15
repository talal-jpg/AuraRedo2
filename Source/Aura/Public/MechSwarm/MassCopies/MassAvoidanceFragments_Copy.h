// Mech Sentinel Swarm - project-owned re-implementation of the MassAvoidance parameters.
// Mirrors (by role): FMassMovingAvoidanceParameters from MassAI/MassNavigation.
// Deviation: the engine avoidance is 2D and navmesh/lane based; sentinels fly, so this one is a full 3D
// predictive separation computed on a spatial hash, with no navigation data required.

#pragma once

#include "CoreMinimal.h"
#include "MassEntityTypes.h"
#include "MassAvoidanceFragments_Copy.generated.h"

/** Shared tuning for agent-vs-agent avoidance. */
USTRUCT()
struct AURA_API FMassMovingAvoidanceParameters_Copy : public FMassConstSharedFragment
{
	GENERATED_BODY()

	/** Two agents closer than this (cm) push each other apart. The spatial hash cells are this plus the prediction reach (max 4x this). */
	UPROPERTY(EditAnywhere, Category = "Avoidance", meta = (ClampMin = "1", ForceUnits = "cm"))
	float SeparationDistance = 260.f;

	/** Acceleration (cm/s^2) applied at full overlap. Falls off quadratically to 0 at SeparationDistance. */
	UPROPERTY(EditAnywhere, Category = "Avoidance", meta = (ClampMin = "0"))
	float SeparationStrength = 3500.f;

	/** How far ahead (s) the relative motion is predicted, so agents start dodging before they touch (the hash reach is capped at 4x SeparationDistance). */
	UPROPERTY(EditAnywhere, Category = "Avoidance", meta = (ClampMin = "0", ForceUnits = "s"))
	float PredictionTime = 0.6f;

	/** Upper bound of neighbours considered per agent (keeps dense clumps cheap). */
	UPROPERTY(EditAnywhere, Category = "Avoidance", meta = (ClampMin = "1"))
	int32 MaxNeighbors = 10;

	/** Clamp for the summed avoidance acceleration. */
	UPROPERTY(EditAnywhere, Category = "Avoidance", meta = (ClampMin = "0"))
	float MaxAvoidanceForce = 7000.f;
};
