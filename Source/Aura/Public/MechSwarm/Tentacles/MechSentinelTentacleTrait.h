// Mech Sentinel Swarm - Niagara ribbon tentacles: trait.

#pragma once

#include "CoreMinimal.h"
#include "MassEntityTraitBase.h"
#include "MechSwarm/Tentacles/MechSentinelTentacleTypes.h"
#include "MechSentinelTentacleTrait.generated.h"

/**
 * Gives near sentinels Niagara ribbon tentacles that hang from the head mesh sockets and trail behind it.
 * Needs the "Visualization ISM (Copy)" trait: its Mesh should be the head without tentacles (SM_MechSentinel_Head) and
 * its LowLODMesh the far mesh with baked tentacles (SM_MechSentinel_Far), which is also used for sentinels that get no
 * ribbons (over budget or too far). Nothing is added on dedicated servers.
 */
UCLASS(meta = (DisplayName = "Mech Sentinel Tentacles (Niagara)"))
class AURA_API UMechSentinelTentacleTrait : public UMassEntityTraitBase
{
	GENERATED_BODY()

protected:
	virtual void BuildTemplate(FMassEntityTemplateBuildContext& BuildContext, const UWorld& World) const override;

	UPROPERTY(EditAnywhere, Category = "Tentacles", meta = (ShowOnlyInnerProperties))
	FMechSentinelTentacleDesc Tentacles;
};
