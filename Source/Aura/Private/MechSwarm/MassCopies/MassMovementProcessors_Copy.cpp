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
}

void UMassApplyForceProcessor_Copy::Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context)
{
	EntityQuery.ForEachEntityChunk(Context, [](FMassExecutionContext& Context)
	{
		const FMassMovementParameters_Copy& Params = Context.GetConstSharedFragment<FMassMovementParameters_Copy>();
		const TArrayView<FMassDesiredMovementFragment_Copy> DesiredList = Context.GetMutableFragmentView<FMassDesiredMovementFragment_Copy>();
		const TArrayView<FMassForceFragment_Copy> ForceList = Context.GetMutableFragmentView<FMassForceFragment_Copy>();

		// Entities whose position is owned by someone else (dead wrecks, ...) never reach the movement integration,
		// so their force would pile up: drop it here.
		const bool bIntegratedLater = Context.DoesArchetypeHaveTag<FMassCodeDrivenMovementTag_Copy>()
			&& !Context.DoesArchetypeHaveTag<FMassCustomMovementTag_Copy>();

		const int32 NumEntities = Context.GetNumEntities();
		for (int32 EntityIndex = 0; EntityIndex < NumEntities; ++EntityIndex)
		{
			FMassDesiredMovementFragment_Copy& Desired = DesiredList[EntityIndex];

			FVector NewDesired = Desired.DesiredVelocity;
			if (!Params.bAllowVerticalMovement)
			{
				NewDesired.Z = 0.f;
				ForceList[EntityIndex].Value.Z = 0.f;
			}

			const float SpeedCap = FMath::Min(Params.MaxSpeed, Desired.DesiredMaxSpeedOverride);
			Desired.DesiredVelocity = NewDesired.GetClampedToMaxSize(SpeedCap);

			if (!bIntegratedLater)
			{
				ForceList[EntityIndex].Value = FVector::ZeroVector;
			}
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
	EntityQuery.AddRequirement<FMassForceFragment_Copy>(EMassFragmentAccess::ReadWrite, EMassFragmentPresence::Optional);
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
		const TArrayView<FMassForceFragment_Copy> ForceList = Context.GetMutableFragmentView<FMassForceFragment_Copy>();

		const float MaxDeltaV = Params.MaxAcceleration * DeltaTime;

		const int32 NumEntities = Context.GetNumEntities();
		for (int32 EntityIndex = 0; EntityIndex < NumEntities; ++EntityIndex)
		{
			FVector& Velocity = VelocityList[EntityIndex].Value;
			const FMassDesiredMovementFragment_Copy& Desired = DesiredList[EntityIndex];

			// 1) Steer toward the desired velocity (limited by MaxAcceleration).
			if (Params.MaxAcceleration <= 0.f)
			{
				Velocity = Desired.DesiredVelocity;
			}
			else
			{
				const FVector DeltaV = (Desired.DesiredVelocity - Velocity).GetClampedToMaxSize(MaxDeltaV);
				Velocity += DeltaV;
			}

			// 2) Forces (avoidance...) are accelerations on the real velocity. The velocity persists between frames,
			//    so they integrate over time and balance against step 1 instead of being a one-frame nudge.
			//    Steering processors assign DesiredVelocity from scratch every frame, so folding forces into it
			//    (as the engine pipeline does with its force-based steering) would lose them.
			if (ForceList.Num() > 0)
			{
				FMassForceFragment_Copy& Force = ForceList[EntityIndex];
				Velocity += Force.Value * DeltaTime;
				Force.Value = FVector::ZeroVector;
				if (!Params.bAllowVerticalMovement)
				{
					Velocity.Z = 0.f;
				}
				Velocity = Velocity.GetClampedToMaxSize(FMath::Min(Params.MaxSpeed, Desired.DesiredMaxSpeedOverride));
			}

			FTransform& Transform = TransformList[EntityIndex].GetMutableTransform();
			Transform.SetTranslation(Transform.GetTranslation() + Velocity * DeltaTime);
		}
	});
}
