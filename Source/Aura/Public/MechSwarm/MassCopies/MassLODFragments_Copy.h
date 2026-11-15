// Mech Sentinel Swarm - project-owned re-implementation of the MassLOD viewer data.
// Mirrors (by role): FMassViewerInfoFragment and UMassLODCollectorProcessor from MassGameplay/MassLOD.
// Deviation: only local viewers (this machine's cameras) are collected, because this LOD only drives
// visuals. Network relevancy LOD is still done by the engine's MassReplication (per client viewer).

#pragma once

#include "CoreMinimal.h"
#include "MassEntityTypes.h"
#include "MassProcessor.h"
#include "MassEntityQuery.h"
#include "MassLODFragments_Copy.generated.h"

/** Distance information of an entity relative to the closest local viewer. */
USTRUCT()
struct AURA_API FMassViewerInfoFragment_Copy : public FMassFragment
{
	GENERATED_BODY()

	/** Squared distance (cm^2) to the closest local camera. */
	UPROPERTY(VisibleAnywhere, Category = "LOD")
	float ClosestViewerDistanceSq = FLT_MAX;

	/** True when the entity is behind every local camera (used to lower the LOD a little). */
	UPROPERTY(VisibleAnywhere, Category = "LOD")
	bool bBehindAllViewers = false;
};

/** Fills FMassViewerInfoFragment_Copy from the local player cameras. Runs where something is rendered. */
UCLASS()
class AURA_API UMassLODCollectorProcessor_Copy : public UMassProcessor
{
	GENERATED_BODY()

public:
	UMassLODCollectorProcessor_Copy();

protected:
	virtual void ConfigureQueries(const TSharedRef<FMassEntityManager>& EntityManager) override;
	virtual void Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context) override;

	FMassEntityQuery EntityQuery;
};
