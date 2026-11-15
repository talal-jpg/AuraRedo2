// Mech Sentinel Swarm - Niagara ribbon tentacles: simulation processor.

#pragma once

#include "CoreMinimal.h"
#include "MassEntityQuery.h"
#include "MassProcessor.h"
#include "Mass/EntityHandle.h"
#include "MechSentinelTentacleProcessor.generated.h"

/**
 * Runs where something is rendered (standalone, listen server, clients), between the visual LOD and the ISM update:
 *  1. picks the sentinels that get ribbons: High / Medium LOD, within MaxDistance, the closest MaxRiggedSentinels;
 *  2. flags the others so the ISM draws them with the baked-tentacle LowLODMesh;
 *  3. simulates the chains of the rigged ones (verlet, pull toward a head-relative trailing pose, gravity, a swimming
 *     wave, length constraints) and writes them into the tentacle set, which UMechSentinelTentacleSubsystem::EndFrame
 *     pushes to Niagara.
 */
UCLASS()
class AURA_API UMechSentinelTentacleProcessor : public UMassProcessor
{
	GENERATED_BODY()

public:
	UMechSentinelTentacleProcessor();

protected:
	virtual void ConfigureQueries(const TSharedRef<FMassEntityManager>& EntityManager) override;
	virtual void Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context) override;

	FMassEntityQuery EntityQuery;

	struct FCandidate
	{
		FMassEntityHandle Entity;
		float DistanceSq = 0.f;
		int32 SetIndex = INDEX_NONE;
		int32 RigIndex = INDEX_NONE;
		bool bWants = false;
	};

	/** Scratch, in query order (the processor is game-thread only). */
	TArray<FCandidate> Candidates;
	TArray<int32> SortScratch;

	/** Last frame's delta time, unclamped (0 before the first frame): the chains' velocity is scaled by the ratio. */
	float PreviousDeltaTime = 0.f;
};
