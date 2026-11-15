// Mech Sentinel Swarm - project-owned re-implementation of UMassRepresentationSubsystem (ISM part only).

#include "MechSwarm/MassCopies/MassRepresentationSubsystem_Copy.h"

#include "Engine/World.h"
#include "MechSwarm/MassCopies/MassVisualizationComponent_Copy.h"
#include "MechSwarm/MassCopies/MassVisualizer_Copy.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(MassRepresentationSubsystem_Copy)

bool UMassRepresentationSubsystem_Copy::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

int32 UMassRepresentationSubsystem_Copy::FindOrAddVisualDesc(const FStaticMeshInstanceVisualizationDesc_Copy& Desc)
{
	if (!Desc.IsValid())
	{
		return INDEX_NONE;
	}

	const int32 Existing = VisualDescs.IndexOfByKey(Desc);
	if (Existing != INDEX_NONE)
	{
		return Existing;
	}
	return VisualDescs.Add(Desc);
}

const FStaticMeshInstanceVisualizationDesc_Copy* UMassRepresentationSubsystem_Copy::GetVisualDesc(const int32 DescIndex) const
{
	return VisualDescs.IsValidIndex(DescIndex) ? &VisualDescs[DescIndex] : nullptr;
}

UMassVisualizationComponent_Copy* UMassRepresentationSubsystem_Copy::GetOrCreateVisualizationComponent()
{
	UWorld* World = GetWorld();
	if (!World || World->GetNetMode() == NM_DedicatedServer)
	{
		return nullptr;
	}

	if (!IsValid(Visualizer))
	{
		FActorSpawnParameters SpawnParams;
		SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		SpawnParams.ObjectFlags |= RF_Transient;
		Visualizer = World->SpawnActor<AMassVisualizer_Copy>(AMassVisualizer_Copy::StaticClass(), FTransform::Identity, SpawnParams);
	}

	return IsValid(Visualizer) ? &Visualizer->GetVisualizationComponent() : nullptr;
}

void UMassRepresentationSubsystem_Copy::Deinitialize()
{
	Visualizer = nullptr;
	VisualDescs.Reset();
	Super::Deinitialize();
}
