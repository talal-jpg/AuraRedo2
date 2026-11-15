// Mech Sentinel Swarm - project-owned re-implementation of UMassRepresentationSubsystem (ISM part only).

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "MechSwarm/MassCopies/MassRepresentationFragments_Copy.h"
#include "MassRepresentationSubsystem_Copy.generated.h"

class AMassVisualizer_Copy;
class UMassVisualizationComponent_Copy;

/**
 * Registry of visual descriptions plus owner of the local visualizer actor.
 * Descriptions are registered by UMassVisualizationTrait_Copy while templates are built;
 * the visualizer actor is spawned lazily the first time something is drawn.
 */
UCLASS()
class AURA_API UMassRepresentationSubsystem_Copy : public UWorldSubsystem
{
	GENERATED_BODY()

public:
	/** Returns a stable index for Desc, adding it when unseen. */
	int32 FindOrAddVisualDesc(const FStaticMeshInstanceVisualizationDesc_Copy& Desc);

	const FStaticMeshInstanceVisualizationDesc_Copy* GetVisualDesc(int32 DescIndex) const;

	/** Spawns the visualizer when needed. Returns null on worlds that never render (dedicated servers). */
	UMassVisualizationComponent_Copy* GetOrCreateVisualizationComponent();

protected:
	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;
	virtual void Deinitialize() override;

	UPROPERTY(Transient)
	TArray<FStaticMeshInstanceVisualizationDesc_Copy> VisualDescs;

	UPROPERTY(Transient)
	TObjectPtr<AMassVisualizer_Copy> Visualizer;
};
