// Mech Sentinel Swarm - project-owned re-implementation of UMassVisualizationTrait (ISM only).

#include "MechSwarm/MassCopies/MassVisualizationTrait_Copy.h"

#include "Engine/World.h"
#include "MassEntityTemplateRegistry.h"
#include "MassEntityUtils.h"
#include "Mass/EntityFragments.h"
#include "MechSwarm/MassCopies/MassLODFragments_Copy.h"
#include "MechSwarm/MassCopies/MassRepresentationSubsystem_Copy.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(MassVisualizationTrait_Copy)

void UMassVisualizationTrait_Copy::BuildTemplate(FMassEntityTemplateBuildContext& BuildContext, const UWorld& World) const
{
	if (World.GetNetMode() == NM_DedicatedServer && !BuildContext.IsInspectingData())
	{
		return;
	}

	FMassEntityManager& EntityManager = UE::Mass::Utils::GetEntityManagerChecked(World);

	BuildContext.RequireFragment<FTransformFragment>();
	BuildContext.AddFragment<FMassViewerInfoFragment_Copy>();
	BuildContext.AddFragment<FMassRepresentationLODFragment_Copy>();
	BuildContext.AddFragment<FMassRepresentationCustomDataFragment_Copy>();
	BuildContext.AddTag<FMassVisualizationTag_Copy>();

	BuildContext.AddConstSharedFragment(EntityManager.GetOrCreateConstSharedFragment(LODParams));

	FMassRepresentationParameters_Copy RepParams;
	if (!BuildContext.IsInspectingData())
	{
		if (UMassRepresentationSubsystem_Copy* RepresentationSubsystem = World.GetSubsystem<UMassRepresentationSubsystem_Copy>())
		{
			RepParams.DescIndex = RepresentationSubsystem->FindOrAddVisualDesc(StaticMeshInstanceDesc);
		}
	}
	BuildContext.AddConstSharedFragment(EntityManager.GetOrCreateConstSharedFragment(RepParams));
}
