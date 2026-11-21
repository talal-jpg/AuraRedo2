// Mech Sentinel Swarm - project-owned re-implementation of UMassObstacleAvoidanceTrait.

#include "MechSwarm/MassCopies/MassAvoidanceTrait_Copy.h"

#include "MassEntityTemplateRegistry.h"
#include "MassEntityUtils.h"
#include "Mass/EntityFragments.h"
#include "MechSwarm/MassCopies/MassMovementFragments_Copy.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(MassAvoidanceTrait_Copy)

void UMassObstacleAvoidanceTrait_Copy::BuildTemplate(FMassEntityTemplateBuildContext& BuildContext, const UWorld& World) const
{
	FMassEntityManager& EntityManager = UE::Mass::Utils::GetEntityManagerChecked(World);

	BuildContext.RequireFragment<FTransformFragment>();
	BuildContext.RequireFragment<FMassVelocityFragment_Copy>();
	BuildContext.RequireFragment<FMassForceFragment_Copy>();

	BuildContext.AddConstSharedFragment(EntityManager.GetOrCreateConstSharedFragment(Avoidance));
	BuildContext.AddConstSharedFragment(EntityManager.GetOrCreateConstSharedFragment(Obstacles));
}
