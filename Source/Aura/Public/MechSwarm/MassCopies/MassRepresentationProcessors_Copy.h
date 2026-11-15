// Mech Sentinel Swarm - project-owned re-implementation of the MassRepresentation processors.
// Mirrors (by role): UMassVisualizationLODProcessor and UMassUpdateISMProcessor.

#pragma once

#include "CoreMinimal.h"
#include "MassProcessor.h"
#include "MassEntityQuery.h"
#include "MassRepresentationProcessors_Copy.generated.h"

/** Converts the viewer distance into a visual LOD (High / Medium / Low / Off) with hysteresis. */
UCLASS()
class AURA_API UMassVisualizationLODProcessor_Copy : public UMassProcessor
{
	GENERATED_BODY()

public:
	UMassVisualizationLODProcessor_Copy();

protected:
	virtual void ConfigureQueries(const TSharedRef<FMassEntityManager>& EntityManager) override;
	virtual void Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context) override;

	FMassEntityQuery EntityQuery;
};

/** Submits every visible entity transform + custom data to the visualizer's ISM components. Game thread. */
UCLASS()
class AURA_API UMassUpdateISMProcessor_Copy : public UMassProcessor
{
	GENERATED_BODY()

public:
	UMassUpdateISMProcessor_Copy();

protected:
	virtual void ConfigureQueries(const TSharedRef<FMassEntityManager>& EntityManager) override;
	virtual void Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context) override;

	FMassEntityQuery EntityQuery;
};
