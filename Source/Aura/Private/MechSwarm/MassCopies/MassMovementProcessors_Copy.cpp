// Mech Sentinel Swarm - project-owned re-implementation of the MassMovement processors.

#include "MechSwarm/MassCopies/MassMovementProcessors_Copy.h"

#include "MassCommonTypes.h"
#include "MassExecutionContext.h"
#include "Mass/EntityFragments.h"
#include "MechSwarm/MassCopies/MassMovementFragments_Copy.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(MassMovementProcessors_Copy)

namespace MechSwarm::Movement
{
	/** Large frame hitches would teleport the swarm; cap the integration step. */
	constexpr float MaxIntegrationStep = 0.1f;
}

//----------------------------------------------------------------------//
// UMassApplyForceProcessor_Copy
//----------------------------------------------------------------------//
UMassApplyForceProcessor_Copy::UMassApplyForceProcessor_Copy()
	: EntityQuery(*this)
{
	ExecutionFlags = (int32)(EProcessorExecutionFlags::Standalone | EProcessorExecutionFlags::Server);
	ExecutionOrder.ExecuteInGroup = UE::Mass::ProcessorGroupNames::ApplyForces;
	ExecutionOrder.ExecuteAfter.Add(UE::Mass::ProcessorGroupNames::Avoidance);
}

void UMassApplyForceProcessor_Copy::ConfigureQueries(const TSharedRef<FMassEntityManager>& EntityManager)
{
	EntityQuery.AddRequirement<FMassDesiredMovementFragment_Copy>(EMassFragmentAccess::ReadWrite);
	EntityQuery.AddRequirement<FMassForceFragment_Copy>(EMassFragmentAccess::ReadWrite);
	EntityQuery.AddConstSharedRequirement<FMassMovementParameters_Copy>(EMassFragmentPresence::All);
	EntityQuery.AddTagRequirement<FMassCustomMovementTag_Copy>(EMassFragmentPresence::None);
}

void UMassApplyForceProcessor_Copy::Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context)
{
	EntityQuery.ForEachEntityChunk(Context, [](FMassExecutionContext& Context)
	{
		const float DeltaTime = FMath::Min(MechSwarm::Movement::MaxIntegrationStep, Context.GetDeltaTimeSeconds());
		const FMassMovementParameters_Copy& Params = Context.GetConstSharedFragment<FMassMovementParameters_Copy>();
		const TArrayView<FMassDesiredMovementFragment_Copy> DesiredList = Context.GetMutableFragmentView<FMassDesiredMovementFragment_Copy>();
		const TArrayView<FMassForceFragment_Copy> ForceList = Context.GetMutableFragmentView<FMassForceFragment_Copy>();

		const int32 NumEntities = Context.GetNumEntities();
		for (int32 EntityIndex = 0; EntityIndex < NumEntities; ++EntityIndex)
		{
			FMassDesiredMovementFragment_Copy& Desired = DesiredList[EntityIndex];
			FMassForceFragment_Copy& Force = ForceList[EntityIndex];

			FVector NewDesired = Desired.DesiredVelocity + Force.Value * DeltaTime;
			if (!Params.bAllowVerticalMovement)
			{
				NewDesired.Z = 0.f;
			}

			const float SpeedCap = FMath::Min(Params.MaxSpeed, Desired.DesiredMaxSpeedOverride);
			Desired.DesiredVelocity = NewDesired.GetClampedToMaxSize(SpeedCap);
			Force.Value = FVector::ZeroVector;
		}
	});
}

//----------------------------------------------------------------------//
// UMassApplyMovementProcessor_Copy
//----------------------------------------------------------------------//
UMassApplyMovementProcessor_Copy::UMassApplyMovementProcessor_Copy()
	: EntityQuery(*this)
{
	ExecutionFlags = (int32)(EProcessorExecutionFlags::Standalone | EProcessorExecutionFlags::Server);
	ExecutionOrder.ExecuteInGroup = UE::Mass::ProcessorGroupNames::Movement;
	ExecutionOrder.ExecuteAfter.Add(UE::Mass::ProcessorGroupNames::ApplyForces);
}

void UMassApplyMovementProcessor_Copy::ConfigureQueries(const TSharedRef<FMassEntityManager>& EntityManager)
{
	EntityQuery.AddRequirement<FTransformFragment>(EMassFragmentAccess::ReadWrite);
	EntityQuery.AddRequirement<FMassVelocityFragment_Copy>(EMassFragmentAccess::ReadWrite);
	EntityQuery.AddRequirement<FMassDesiredMovementFragment_Copy>(EMassFragmentAccess::ReadOnly);
	EntityQuery.AddConstSharedRequirement<FMassMovementParameters_Copy>(EMassFragmentPresence::All);
	EntityQuery.AddTagRequirement<FMassCodeDrivenMovementTag_Copy>(EMassFragmentPresence::All);
	EntityQuery.AddTagRequirement<FMassCustomMovementTag_Copy>(EMassFragmentPresence::None);
}

void UMassApplyMovementProcessor_Copy::Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context)
{
	EntityQuery.ForEachEntityChunk(Context, [](FMassExecutionContext& Context)
	{
		const float DeltaTime = FMath::Min(MechSwarm::Movement::MaxIntegrationStep, Context.GetDeltaTimeSeconds());
		const FMassMovementParameters_Copy& Params = Context.GetConstSharedFragment<FMassMovementParameters_Copy>();
		const TArrayView<FTransformFragment> TransformList = Context.GetMutableFragmentView<FTransformFragment>();
		const TArrayView<FMassVelocityFragment_Copy> VelocityList = Context.GetMutableFragmentView<FMassVelocityFragment_Copy>();
		const TConstArrayView<FMassDesiredMovementFragment_Copy> DesiredList = Context.GetFragmentView<FMassDesiredMovementFragment_Copy>();

		const float MaxDeltaV = Params.MaxAcceleration * DeltaTime;

		const int32 NumEntities = Context.GetNumEntities();
		for (int32 EntityIndex = 0; EntityIndex < NumEntities; ++EntityIndex)
		{
			FVector& Velocity = VelocityList[EntityIndex].Value;
			const FVector& DesiredVelocity = DesiredList[EntityIndex].DesiredVelocity;

			if (Params.MaxAcceleration <= 0.f)
			{
				Velocity = DesiredVelocity;
			}
			else
			{
				const FVector DeltaV = (DesiredVelocity - Velocity).GetClampedToMaxSize(MaxDeltaV);
				Velocity += DeltaV;
			}

			FTransform& Transform = TransformList[EntityIndex].GetMutableTransform();
			Transform.SetTranslation(Transform.GetTranslation() + Velocity * DeltaTime);
		}
	});
}
