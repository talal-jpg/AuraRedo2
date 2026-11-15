// Mech Sentinel Swarm - Niagara ribbon tentacles: trait.

#include "MechSwarm/Tentacles/MechSentinelTentacleTrait.h"

#include "Engine/World.h"
#include "MassEntityTemplateRegistry.h"
#include "MassEntityUtils.h"
#include "Mass/EntityFragments.h"
#include "MechSwarm/MassCopies/MassLODFragments_Copy.h"
#include "MechSwarm/MassCopies/MassRepresentationFragments_Copy.h"
#include "MechSwarm/Tentacles/MechSentinelTentacleSubsystem.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(MechSentinelTentacleTrait)

DEFINE_LOG_CATEGORY_STATIC(LogMechSentinelTentacleTrait, Log, All);

void UMechSentinelTentacleTrait::BuildTemplate(FMassEntityTemplateBuildContext& BuildContext, const UWorld& World) const
{
	const bool bInspecting = BuildContext.IsInspectingData();
	if (World.GetNetMode() == NM_DedicatedServer && !bInspecting)
	{
		return;
	}

	if (!Tentacles.NiagaraSystem && !bInspecting)
	{
		UE_LOG(LogMechSentinelTentacleTrait, Warning, TEXT("%s: no Niagara system set, sentinels keep the baked-tentacle LOD mesh."), *GetPathNameSafe(GetOuter()));
		return;
	}

	FMassEntityManager& EntityManager = UE::Mass::Utils::GetEntityManagerChecked(World);

	// Provided by UMassVisualizationTrait_Copy: the ribbons follow its LOD and draw from its head mesh sockets.
	BuildContext.RequireFragment<FTransformFragment>();
	BuildContext.RequireFragment<FMassViewerInfoFragment_Copy>();
	BuildContext.RequireFragment<FMassRepresentationLODFragment_Copy>();

	BuildContext.AddFragment<FMechSentinelTentacleFragment>();

	FMechSentinelTentacleParams Params;
	if (!bInspecting)
	{
		if (UMechSentinelTentacleSubsystem* TentacleSubsystem = World.GetSubsystem<UMechSentinelTentacleSubsystem>())
		{
			Params.SetIndex = TentacleSubsystem->FindOrAddSet(Tentacles);
		}
	}
	BuildContext.AddConstSharedFragment(EntityManager.GetOrCreateConstSharedFragment(Params));
}
