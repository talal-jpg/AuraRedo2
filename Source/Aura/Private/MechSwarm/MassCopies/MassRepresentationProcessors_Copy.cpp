// Mech Sentinel Swarm - project-owned re-implementation of the MassRepresentation processors.

#include "MechSwarm/MassCopies/MassRepresentationProcessors_Copy.h"

#include "Engine/World.h"
#include "MassExecutionContext.h"
#include "Mass/EntityFragments.h"
#include "MechSwarm/Core/MechSwarmProcessorGroups.h"
#include "MechSwarm/MassCopies/MassLODFragments_Copy.h"
#include "MechSwarm/MassCopies/MassRepresentationFragments_Copy.h"
#include "MechSwarm/MassCopies/MassRepresentationSubsystem_Copy.h"
#include "MechSwarm/MassCopies/MassVisualizationComponent_Copy.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(MassRepresentationProcessors_Copy)

namespace MechSwarm::Representation
{
	EMassLOD::Type ComputeLOD(const float Distance, const FMassVisualizationLODParameters_Copy& Params, const float Scale)
	{
		if (Distance < Params.HighDistance * Scale)
		{
			return EMassLOD::High;
		}
		if (Distance < Params.MediumDistance * Scale)
		{
			return EMassLOD::Medium;
		}
		if (Distance < Params.LowDistance * Scale)
		{
			return EMassLOD::Low;
		}
		return EMassLOD::Off;
	}
}

//----------------------------------------------------------------------//
// UMassVisualizationLODProcessor_Copy
//----------------------------------------------------------------------//
UMassVisualizationLODProcessor_Copy::UMassVisualizationLODProcessor_Copy()
	: EntityQuery(*this)
{
	ExecutionFlags = (int32)(EProcessorExecutionFlags::Standalone | EProcessorExecutionFlags::Client);
	ProcessingPhase = EMassProcessingPhase::PostPhysics;
	ExecutionOrder.ExecuteInGroup = MechSwarm::ProcessorGroups::Representation();
	ExecutionOrder.ExecuteAfter.Add(MechSwarm::ProcessorGroups::LODCollector());
}

void UMassVisualizationLODProcessor_Copy::ConfigureQueries(const TSharedRef<FMassEntityManager>& EntityManager)
{
	EntityQuery.AddRequirement<FMassViewerInfoFragment_Copy>(EMassFragmentAccess::ReadOnly);
	EntityQuery.AddRequirement<FMassRepresentationLODFragment_Copy>(EMassFragmentAccess::ReadWrite);
	EntityQuery.AddConstSharedRequirement<FMassVisualizationLODParameters_Copy>(EMassFragmentPresence::All);
}

void UMassVisualizationLODProcessor_Copy::Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context)
{
	EntityQuery.ForEachEntityChunk(Context, [](FMassExecutionContext& Context)
	{
		using namespace MechSwarm::Representation;

		const FMassVisualizationLODParameters_Copy& Params = Context.GetConstSharedFragment<FMassVisualizationLODParameters_Copy>();
		const TConstArrayView<FMassViewerInfoFragment_Copy> ViewerList = Context.GetFragmentView<FMassViewerInfoFragment_Copy>();
		const TArrayView<FMassRepresentationLODFragment_Copy> LODList = Context.GetMutableFragmentView<FMassRepresentationLODFragment_Copy>();

		const int32 NumEntities = Context.GetNumEntities();
		for (int32 EntityIndex = 0; EntityIndex < NumEntities; ++EntityIndex)
		{
			const FMassViewerInfoFragment_Copy& Viewer = ViewerList[EntityIndex];
			FMassRepresentationLODFragment_Copy& LODFragment = LODList[EntityIndex];

			float Distance = Viewer.ClosestViewerDistanceSq < FLT_MAX ? FMath::Sqrt(Viewer.ClosestViewerDistanceSq) : FLT_MAX;
			if (Viewer.bBehindAllViewers && Distance < FLT_MAX)
			{
				Distance *= Params.BehindViewerDistanceScale;
			}

			const EMassLOD::Type Prev = LODFragment.LOD;
			EMassLOD::Type NewLOD;
			if (Prev == EMassLOD::Max)
			{
				NewLOD = ComputeLOD(Distance, Params, 1.f);
			}
			else
			{
				// Moving away must pass the boundary by the hysteresis margin, moving closer flips right away.
				const EMassLOD::Type Farther = ComputeLOD(Distance, Params, 1.f + Params.Hysteresis);
				const EMassLOD::Type Closer = ComputeLOD(Distance, Params, 1.f);
				NewLOD = Farther > Prev ? Farther : (Closer < Prev ? Closer : Prev);
			}

			LODFragment.PrevLOD = Prev;
			LODFragment.LOD = NewLOD;
		}
	});
}

//----------------------------------------------------------------------//
// UMassUpdateISMProcessor_Copy
//----------------------------------------------------------------------//
UMassUpdateISMProcessor_Copy::UMassUpdateISMProcessor_Copy()
	: EntityQuery(*this)
{
	ExecutionFlags = (int32)(EProcessorExecutionFlags::Standalone | EProcessorExecutionFlags::Client);
	ProcessingPhase = EMassProcessingPhase::PostPhysics;
	ExecutionOrder.ExecuteInGroup = MechSwarm::ProcessorGroups::Representation();
	ExecutionOrder.ExecuteAfter.Add(UMassVisualizationLODProcessor_Copy::StaticClass()->GetFName());
	// Touches UInstancedStaticMeshComponents.
	bRequiresGameThreadExecution = true;
}

void UMassUpdateISMProcessor_Copy::ConfigureQueries(const TSharedRef<FMassEntityManager>& EntityManager)
{
	EntityQuery.AddRequirement<FTransformFragment>(EMassFragmentAccess::ReadOnly);
	EntityQuery.AddRequirement<FMassRepresentationLODFragment_Copy>(EMassFragmentAccess::ReadOnly);
	EntityQuery.AddRequirement<FMassRepresentationCustomDataFragment_Copy>(EMassFragmentAccess::ReadOnly, EMassFragmentPresence::Optional);
	EntityQuery.AddConstSharedRequirement<FMassRepresentationParameters_Copy>(EMassFragmentPresence::All);
	EntityQuery.AddTagRequirement<FMassVisualizationTag_Copy>(EMassFragmentPresence::All);
}

void UMassUpdateISMProcessor_Copy::Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context)
{
	UWorld* World = EntityManager.GetWorld();
	UMassRepresentationSubsystem_Copy* RepresentationSubsystem = World ? World->GetSubsystem<UMassRepresentationSubsystem_Copy>() : nullptr;
	if (!RepresentationSubsystem)
	{
		return;
	}

	UMassVisualizationComponent_Copy* Visualization = RepresentationSubsystem->GetOrCreateVisualizationComponent();
	if (!Visualization)
	{
		return;
	}

	Visualization->BeginVisualFrame();

	EntityQuery.ForEachEntityChunk(Context, [RepresentationSubsystem, Visualization](FMassExecutionContext& Context)
	{
		const FMassRepresentationParameters_Copy& RepParams = Context.GetConstSharedFragment<FMassRepresentationParameters_Copy>();
		const FStaticMeshInstanceVisualizationDesc_Copy* Desc = RepresentationSubsystem->GetVisualDesc(RepParams.DescIndex);
		if (!Desc)
		{
			return;
		}

		const int32 HighSlot = Visualization->GetOrCreateSlot(RepParams.DescIndex, *Desc, /*bLowLOD*/false);
		const int32 LowSlot = Visualization->GetOrCreateSlot(RepParams.DescIndex, *Desc, /*bLowLOD*/true);

		const TConstArrayView<FTransformFragment> TransformList = Context.GetFragmentView<FTransformFragment>();
		const TConstArrayView<FMassRepresentationLODFragment_Copy> LODList = Context.GetFragmentView<FMassRepresentationLODFragment_Copy>();
		const TConstArrayView<FMassRepresentationCustomDataFragment_Copy> CustomList = Context.GetFragmentView<FMassRepresentationCustomDataFragment_Copy>();

		const int32 NumEntities = Context.GetNumEntities();
		for (int32 EntityIndex = 0; EntityIndex < NumEntities; ++EntityIndex)
		{
			const EMassLOD::Type LOD = LODList[EntityIndex].LOD;
			if (LOD >= EMassLOD::Off)
			{
				continue;
			}

			const int32 Slot = (LOD == EMassLOD::Low || LODList[EntityIndex].bForceLowLODMesh) ? LowSlot : HighSlot;
			const FTransform InstanceTransform = Desc->MeshRelativeTransform * TransformList[EntityIndex].GetTransform();
			const TConstArrayView<float> Custom = CustomList.Num() > 0
				? TConstArrayView<float>(CustomList[EntityIndex].Values, 4)
				: TConstArrayView<float>();

			Visualization->AddFrameInstance(Slot, Context.GetEntity(EntityIndex), InstanceTransform, Custom);
		}
	});

	Visualization->EndVisualFrame();
}
