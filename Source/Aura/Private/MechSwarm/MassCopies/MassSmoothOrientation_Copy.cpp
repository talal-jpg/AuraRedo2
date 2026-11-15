// Mech Sentinel Swarm - project-owned re-implementation of the smooth orientation feature.

#include "MechSwarm/MassCopies/MassSmoothOrientation_Copy.h"

#include "MassCommonTypes.h"
#include "MassEntityTemplateRegistry.h"
#include "MassEntityUtils.h"
#include "MassExecutionContext.h"
#include "Mass/EntityFragments.h"
#include "MechSwarm/MassCopies/MassMovementFragments_Copy.h"
#include "MechSwarm/MassCopies/MassMovementProcessors_Copy.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(MassSmoothOrientation_Copy)

//----------------------------------------------------------------------//
// UMassSmoothOrientationProcessor_Copy
//----------------------------------------------------------------------//
UMassSmoothOrientationProcessor_Copy::UMassSmoothOrientationProcessor_Copy()
	: EntityQuery(*this)
{
	ExecutionFlags = (int32)(EProcessorExecutionFlags::Standalone | EProcessorExecutionFlags::Server);
	ExecutionOrder.ExecuteInGroup = UE::Mass::ProcessorGroupNames::Movement;
	ExecutionOrder.ExecuteAfter.Add(UMassApplyMovementProcessor_Copy::StaticClass()->GetFName());
}

void UMassSmoothOrientationProcessor_Copy::ConfigureQueries(const TSharedRef<FMassEntityManager>& EntityManager)
{
	EntityQuery.AddRequirement<FTransformFragment>(EMassFragmentAccess::ReadWrite);
	EntityQuery.AddRequirement<FMassVelocityFragment_Copy>(EMassFragmentAccess::ReadOnly);
	EntityQuery.AddRequirement<FMassDesiredMovementFragment_Copy>(EMassFragmentAccess::ReadOnly);
	EntityQuery.AddConstSharedRequirement<FMassSmoothOrientationParameters_Copy>(EMassFragmentPresence::All);
	EntityQuery.AddTagRequirement<FMassCustomMovementTag_Copy>(EMassFragmentPresence::None);
}

void UMassSmoothOrientationProcessor_Copy::Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context)
{
	EntityQuery.ForEachEntityChunk(Context, [](FMassExecutionContext& Context)
	{
		const float DeltaTime = FMath::Min(0.1f, Context.GetDeltaTimeSeconds());
		if (DeltaTime <= 0.f)
		{
			return;
		}

		const FMassSmoothOrientationParameters_Copy& Params = Context.GetConstSharedFragment<FMassSmoothOrientationParameters_Copy>();
		const TArrayView<FTransformFragment> TransformList = Context.GetMutableFragmentView<FTransformFragment>();
		const TConstArrayView<FMassVelocityFragment_Copy> VelocityList = Context.GetFragmentView<FMassVelocityFragment_Copy>();
		const TConstArrayView<FMassDesiredMovementFragment_Copy> DesiredList = Context.GetFragmentView<FMassDesiredMovementFragment_Copy>();

		const float Alpha = 1.f - FMath::Exp(-Params.OrientationSpeed * DeltaTime);

		const int32 NumEntities = Context.GetNumEntities();
		for (int32 EntityIndex = 0; EntityIndex < NumEntities; ++EntityIndex)
		{
			FTransform& Transform = TransformList[EntityIndex].GetMutableTransform();
			const FQuat Current = Transform.GetRotation();
			const FVector& Velocity = VelocityList[EntityIndex].Value;
			const FQuat& DesiredFacing = DesiredList[EntityIndex].DesiredFacing;

			FVector WantedForward;
			if (!DesiredFacing.Equals(FQuat::Identity, KINDA_SMALL_NUMBER))
			{
				WantedForward = DesiredFacing.GetForwardVector();
			}
			else if (Velocity.SizeSquared() > FMath::Square(Params.MinSpeedForVelocityFacing))
			{
				WantedForward = Velocity.GetUnsafeNormal();
			}
			else
			{
				continue;
			}

			FRotator Wanted = WantedForward.Rotation();
			Wanted.Pitch = FMath::Clamp(Wanted.Pitch, -Params.MaxPitch, Params.MaxPitch);

			const FRotator CurrentRot = Current.Rotator();
			const float YawRate = FMath::FindDeltaAngleDegrees(CurrentRot.Yaw, Wanted.Yaw) * Params.OrientationSpeed;
			Wanted.Roll = FMath::Clamp(-YawRate / 90.f * Params.BankingAmount, -Params.BankingAmount, Params.BankingAmount);

			Transform.SetRotation(FQuat::Slerp(Current, Wanted.Quaternion(), Alpha).GetNormalized());
		}
	});
}

//----------------------------------------------------------------------//
// UMassSmoothOrientationTrait_Copy
//----------------------------------------------------------------------//
void UMassSmoothOrientationTrait_Copy::BuildTemplate(FMassEntityTemplateBuildContext& BuildContext, const UWorld& World) const
{
	FMassEntityManager& EntityManager = UE::Mass::Utils::GetEntityManagerChecked(World);

	BuildContext.RequireFragment<FTransformFragment>();
	BuildContext.RequireFragment<FMassVelocityFragment_Copy>();
	BuildContext.RequireFragment<FMassDesiredMovementFragment_Copy>();

	BuildContext.AddConstSharedFragment(EntityManager.GetOrCreateConstSharedFragment(Orientation));
}
