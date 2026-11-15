// Mech Sentinel Swarm - project-owned re-implementation of UMassMovingAvoidanceProcessor (3D variant).

#include "MechSwarm/MassCopies/MassAvoidanceProcessors_Copy.h"

#include "MassCommonTypes.h"
#include "MassExecutionContext.h"
#include "Mass/EntityFragments.h"
#include "MechSwarm/MassCopies/MassAvoidanceFragments_Copy.h"
#include "MechSwarm/MassCopies/MassMovementFragments_Copy.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(MassAvoidanceProcessors_Copy)

namespace MechSwarm::Avoidance
{
	FORCEINLINE FIntVector ToCell(const FVector& Position, const float InvCellSize)
	{
		return FIntVector(
			FMath::FloorToInt32(Position.X * InvCellSize),
			FMath::FloorToInt32(Position.Y * InvCellSize),
			FMath::FloorToInt32(Position.Z * InvCellSize));
	}
}

UMassMovingAvoidanceProcessor_Copy::UMassMovingAvoidanceProcessor_Copy()
	: EntityQuery(*this)
{
	ExecutionFlags = (int32)(EProcessorExecutionFlags::Standalone | EProcessorExecutionFlags::Server);
	ExecutionOrder.ExecuteInGroup = UE::Mass::ProcessorGroupNames::Avoidance;
	ExecutionOrder.ExecuteAfter.Add(UE::Mass::ProcessorGroupNames::Tasks);
	// Uses member scratch buffers and a two-pass gather, keep it on one thread.
	bRequiresGameThreadExecution = true;
}

void UMassMovingAvoidanceProcessor_Copy::ConfigureQueries(const TSharedRef<FMassEntityManager>& EntityManager)
{
	EntityQuery.AddRequirement<FTransformFragment>(EMassFragmentAccess::ReadOnly);
	EntityQuery.AddRequirement<FMassVelocityFragment_Copy>(EMassFragmentAccess::ReadOnly);
	EntityQuery.AddRequirement<FMassForceFragment_Copy>(EMassFragmentAccess::ReadWrite);
	EntityQuery.AddConstSharedRequirement<FMassMovingAvoidanceParameters_Copy>(EMassFragmentPresence::All);
	EntityQuery.AddTagRequirement<FMassCustomMovementTag_Copy>(EMassFragmentPresence::None);
}

void UMassMovingAvoidanceProcessor_Copy::Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context)
{
	using namespace MechSwarm::Avoidance;

	Samples.Reset();
	for (TPair<FIntVector, TArray<int32>>& Cell : Grid)
	{
		Cell.Value.Reset();
	}

	// Pass 1: gather positions / velocities in query order and find the largest separation distance.
	float CellSize = 1.f;
	EntityQuery.ForEachEntityChunk(Context, [this, &CellSize](FMassExecutionContext& Context)
	{
		const FMassMovingAvoidanceParameters_Copy& Params = Context.GetConstSharedFragment<FMassMovingAvoidanceParameters_Copy>();
		const TConstArrayView<FTransformFragment> TransformList = Context.GetFragmentView<FTransformFragment>();
		const TConstArrayView<FMassVelocityFragment_Copy> VelocityList = Context.GetFragmentView<FMassVelocityFragment_Copy>();

		CellSize = FMath::Max(CellSize, Params.SeparationDistance);

		const int32 NumEntities = Context.GetNumEntities();
		for (int32 EntityIndex = 0; EntityIndex < NumEntities; ++EntityIndex)
		{
			Samples.Add({ TransformList[EntityIndex].GetTransform().GetLocation(), VelocityList[EntityIndex].Value });
		}
	});

	if (Samples.Num() < 2)
	{
		return;
	}

	const float InvCellSize = 1.f / CellSize;
	for (int32 SampleIndex = 0; SampleIndex < Samples.Num(); ++SampleIndex)
	{
		Grid.FindOrAdd(ToCell(Samples[SampleIndex].Position, InvCellSize)).Add(SampleIndex);
	}

	// Drop cells that stayed empty this frame so the map does not grow forever as the swarm travels.
	for (auto It = Grid.CreateIterator(); It; ++It)
	{
		if (It.Value().IsEmpty())
		{
			It.RemoveCurrent();
		}
	}

	// Pass 2: same iteration order, so a running index maps each entity back to its sample.
	int32 RunningIndex = 0;
	EntityQuery.ForEachEntityChunk(Context, [this, &RunningIndex, InvCellSize](FMassExecutionContext& Context)
	{
		const FMassMovingAvoidanceParameters_Copy& Params = Context.GetConstSharedFragment<FMassMovingAvoidanceParameters_Copy>();
		const TArrayView<FMassForceFragment_Copy> ForceList = Context.GetMutableFragmentView<FMassForceFragment_Copy>();

		const float Radius = Params.SeparationDistance;
		const float RadiusSq = FMath::Square(Radius);
		const float Horizon = Params.PredictionTime;

		const int32 NumEntities = Context.GetNumEntities();
		for (int32 EntityIndex = 0; EntityIndex < NumEntities; ++EntityIndex, ++RunningIndex)
		{
			const FAgentSample& Self = Samples[RunningIndex];
			const FIntVector SelfCell = ToCell(Self.Position, InvCellSize);

			FVector Accumulated = FVector::ZeroVector;
			int32 NeighborCount = 0;

			for (int32 DZ = -1; DZ <= 1 && NeighborCount < Params.MaxNeighbors; ++DZ)
			for (int32 DY = -1; DY <= 1 && NeighborCount < Params.MaxNeighbors; ++DY)
			for (int32 DX = -1; DX <= 1 && NeighborCount < Params.MaxNeighbors; ++DX)
			{
				const TArray<int32>* CellEntries = Grid.Find(SelfCell + FIntVector(DX, DY, DZ));
				if (!CellEntries)
				{
					continue;
				}

				for (const int32 OtherIndex : *CellEntries)
				{
					if (OtherIndex == RunningIndex)
					{
						continue;
					}

					const FAgentSample& Other = Samples[OtherIndex];
					const FVector RelPos = Self.Position - Other.Position;
					const float CurrentDistSq = RelPos.SizeSquared();
					if (CurrentDistSq > FMath::Square(Radius + Horizon * (Self.Velocity - Other.Velocity).Size()))
					{
						continue;
					}

					// Closest approach of the two agents within the prediction horizon.
					const FVector RelVel = Self.Velocity - Other.Velocity;
					const float RelSpeedSq = RelVel.SizeSquared();
					float TimeOfClosest = 0.f;
					if (RelSpeedSq > KINDA_SMALL_NUMBER)
					{
						TimeOfClosest = FMath::Clamp(-FVector::DotProduct(RelPos, RelVel) / RelSpeedSq, 0.f, Horizon);
					}
					const FVector ClosestRel = RelPos + RelVel * TimeOfClosest;
					const float ClosestDistSq = ClosestRel.SizeSquared();
					if (ClosestDistSq >= RadiusSq)
					{
						continue;
					}

					const float ClosestDist = FMath::Sqrt(ClosestDistSq);
					// Exact overlap: pick a deterministic direction from the sample indices.
					const FVector PushDir = ClosestDist > KINDA_SMALL_NUMBER
						? ClosestRel / ClosestDist
						: FVector(FMath::Sin(float(RunningIndex)), FMath::Cos(float(RunningIndex)), (RunningIndex & 1) ? 0.3f : -0.3f).GetSafeNormal();

					const float Falloff = FMath::Square(1.f - ClosestDist / Radius);
					// Imminent contacts (small TimeOfClosest) weigh more than far-future ones.
					const float Urgency = Horizon > 0.f ? 1.f - 0.5f * (TimeOfClosest / Horizon) : 1.f;
					Accumulated += PushDir * (Params.SeparationStrength * Falloff * Urgency);

					if (++NeighborCount >= Params.MaxNeighbors)
					{
						break;
					}
				}
			}

			ForceList[EntityIndex].Value += Accumulated.GetClampedToMaxSize(Params.MaxAvoidanceForce);
		}
	});
}
