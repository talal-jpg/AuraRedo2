// Mech Sentinel Swarm - project-owned re-implementation of UMassVisualizationTrait (ISM only).

#pragma once

#include "CoreMinimal.h"
#include "MassEntityTraitBase.h"
#include "MechSwarm/MassCopies/MassRepresentationFragments_Copy.h"
#include "MassVisualizationTrait_Copy.generated.h"

/**
 * Draws the entity with instanced static meshes. Nothing is added on dedicated servers,
 * which never render, so the server archetype stays lean.
 */
UCLASS(meta = (DisplayName = "Visualization ISM (Copy)"))
class AURA_API UMassVisualizationTrait_Copy : public UMassEntityTraitBase
{
	GENERATED_BODY()

protected:
	virtual void BuildTemplate(FMassEntityTemplateBuildContext& BuildContext, const UWorld& World) const override;

	UPROPERTY(EditAnywhere, Category = "Visualization")
	FStaticMeshInstanceVisualizationDesc_Copy StaticMeshInstanceDesc;

	UPROPERTY(EditAnywhere, Category = "Visualization")
	FMassVisualizationLODParameters_Copy LODParams;
};
