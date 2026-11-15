// Mech Sentinel Swarm - project-owned re-implementation of AMassVisualizer.

#include "MechSwarm/MassCopies/MassVisualizer_Copy.h"

#include "Components/SceneComponent.h"
#include "MechSwarm/MassCopies/MassVisualizationComponent_Copy.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(MassVisualizer_Copy)

AMassVisualizer_Copy::AMassVisualizer_Copy()
{
	PrimaryActorTick.bCanEverTick = false;
	bReplicates = false;
	SetCanBeDamaged(false);

	USceneComponent* Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	Root->SetMobility(EComponentMobility::Static);
	RootComponent = Root;

	VisualizationComponent = CreateDefaultSubobject<UMassVisualizationComponent_Copy>(TEXT("VisualizationComponent"));
}
