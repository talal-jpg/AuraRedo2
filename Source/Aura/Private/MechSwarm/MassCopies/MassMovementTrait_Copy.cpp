// Mech Sentinel Swarm - project-owned re-implementation of UMassMovementTrait.

#include "MechSwarm/MassCopies/MassMovementTrait_Copy.h"

#include "MassEntityTemplateRegistry.h"
#include "MassEntityUtils.h"
#include "Mass/EntityFragments.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(MassMovementTrait_Copy)

void UMassMovementTrait_Copy::BuildTemplate(FMassEntityTemplateBuildContext& BuildContext, const UWorld& World) const
{
	FMassEntityManager& EntityManager = UE::Mass::Utils::GetEntityManagerChecked(World);

	BuildContext.RequireFragment<FTransformFragment>();

	BuildContext.AddFragment<FMassVelocityFragment_Copy>();
	BuildContext.AddFragment<FMassForceFragment_Copy>();
	BuildContext.AddFragment<FMassDesiredMovementFragment_Copy>();
	BuildContext.AddTag<FMassCodeDrivenMovementTag_Copy>();

	BuildContext.AddConstSharedFragment(EntityManager.GetOrCreateConstSharedFragment(Movement));
}
