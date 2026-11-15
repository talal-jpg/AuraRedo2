// Mech Sentinel Swarm - project-owned re-implementation of UMassMovementTrait.

#pragma once

#include "CoreMinimal.h"
#include "MassEntityTraitBase.h"
#include "MechSwarm/MassCopies/MassMovementFragments_Copy.h"
#include "MassMovementTrait_Copy.generated.h"

/**
 * Adds the code-driven movement fragments (velocity, force, desired movement) and the shared
 * movement parameters. Requires FTransformFragment (added by UMechSentinelTrait).
 */
UCLASS(meta = (DisplayName = "Movement (Copy)"))
class AURA_API UMassMovementTrait_Copy : public UMassEntityTraitBase
{
	GENERATED_BODY()

protected:
	virtual void BuildTemplate(FMassEntityTemplateBuildContext& BuildContext, const UWorld& World) const override;

	UPROPERTY(EditAnywhere, Category = "Movement")
	FMassMovementParameters_Copy Movement;
};
