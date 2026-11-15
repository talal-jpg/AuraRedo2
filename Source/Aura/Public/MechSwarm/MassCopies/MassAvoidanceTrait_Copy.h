// Mech Sentinel Swarm - project-owned re-implementation of UMassObstacleAvoidanceTrait.

#pragma once

#include "CoreMinimal.h"
#include "MassEntityTraitBase.h"
#include "MechSwarm/MassCopies/MassAvoidanceFragments_Copy.h"
#include "MassAvoidanceTrait_Copy.generated.h"

/** Enables 3D agent-vs-agent avoidance. Requires the Movement (Copy) trait. */
UCLASS(meta = (DisplayName = "Avoidance (Copy)"))
class AURA_API UMassObstacleAvoidanceTrait_Copy : public UMassEntityTraitBase
{
	GENERATED_BODY()

protected:
	virtual void BuildTemplate(FMassEntityTemplateBuildContext& BuildContext, const UWorld& World) const override;

	UPROPERTY(EditAnywhere, Category = "Avoidance")
	FMassMovingAvoidanceParameters_Copy Avoidance;
};
