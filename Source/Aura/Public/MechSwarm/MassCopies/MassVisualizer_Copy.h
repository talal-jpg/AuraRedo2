// Mech Sentinel Swarm - project-owned re-implementation of AMassVisualizer.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "MassVisualizer_Copy.generated.h"

class UMassVisualizationComponent_Copy;

/** Local-only, non-replicated actor at the world origin that hosts the swarm's ISM components. */
UCLASS(NotPlaceable, Transient)
class AURA_API AMassVisualizer_Copy : public AActor
{
	GENERATED_BODY()

public:
	AMassVisualizer_Copy();

	UMassVisualizationComponent_Copy& GetVisualizationComponent() const { return *VisualizationComponent; }

protected:
	UPROPERTY(VisibleAnywhere, Category = "Mass")
	TObjectPtr<UMassVisualizationComponent_Copy> VisualizationComponent;
};
