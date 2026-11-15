// Mech Sentinel Swarm - project-owned re-implementation of the LOD collector.

#include "MechSwarm/MassCopies/MassLODFragments_Copy.h"

#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "MassCommonTypes.h"
#include "MassExecutionContext.h"
#include "Mass/EntityFragments.h"
#include "MechSwarm/Core/MechSwarmProcessorGroups.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(MassLODFragments_Copy)

UMassLODCollectorProcessor_Copy::UMassLODCollectorProcessor_Copy()
	: EntityQuery(*this)
{
	// Visual LOD only matters where frames are rendered: clients, listen servers (they carry the Client flag) and standalone.
	ExecutionFlags = (int32)(EProcessorExecutionFlags::Standalone | EProcessorExecutionFlags::Client);
	ProcessingPhase = EMassProcessingPhase::PostPhysics;
	ExecutionOrder.ExecuteInGroup = MechSwarm::ProcessorGroups::LODCollector();
	// Reads player controllers / cameras.
	bRequiresGameThreadExecution = true;
}

void UMassLODCollectorProcessor_Copy::ConfigureQueries(const TSharedRef<FMassEntityManager>& EntityManager)
{
	EntityQuery.AddRequirement<FTransformFragment>(EMassFragmentAccess::ReadOnly);
	EntityQuery.AddRequirement<FMassViewerInfoFragment_Copy>(EMassFragmentAccess::ReadWrite);
}

void UMassLODCollectorProcessor_Copy::Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context)
{
	const UWorld* World = EntityManager.GetWorld();
	if (!World)
	{
		return;
	}

	struct FViewer
	{
		FVector Location;
		FVector Forward;
	};
	TArray<FViewer, TInlineAllocator<4>> Viewers;
	for (FConstPlayerControllerIterator It = World->GetPlayerControllerIterator(); It; ++It)
	{
		const APlayerController* PC = It->Get();
		if (PC && PC->IsLocalController())
		{
			FVector ViewLocation;
			FRotator ViewRotation;
			PC->GetPlayerViewPoint(ViewLocation, ViewRotation);
			Viewers.Add({ ViewLocation, ViewRotation.Vector() });
		}
	}

	EntityQuery.ForEachEntityChunk(Context, [&Viewers](FMassExecutionContext& Context)
	{
		const TConstArrayView<FTransformFragment> TransformList = Context.GetFragmentView<FTransformFragment>();
		const TArrayView<FMassViewerInfoFragment_Copy> ViewerInfoList = Context.GetMutableFragmentView<FMassViewerInfoFragment_Copy>();

		const int32 NumEntities = Context.GetNumEntities();
		for (int32 EntityIndex = 0; EntityIndex < NumEntities; ++EntityIndex)
		{
			const FVector Location = TransformList[EntityIndex].GetTransform().GetLocation();
			float BestDistSq = FLT_MAX;
			bool bBehindAll = Viewers.Num() > 0;
			for (const FViewer& Viewer : Viewers)
			{
				const FVector ToEntity = Location - Viewer.Location;
				BestDistSq = FMath::Min(BestDistSq, ToEntity.SizeSquared());
				bBehindAll &= FVector::DotProduct(ToEntity, Viewer.Forward) < 0.f;
			}

			FMassViewerInfoFragment_Copy& Info = ViewerInfoList[EntityIndex];
			Info.ClosestViewerDistanceSq = BestDistSq;
			Info.bBehindAllViewers = bBehindAll;
		}
	});
}
