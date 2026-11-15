// Mech Sentinel Swarm - processors that run where frames are rendered (visual data) and on network clients (smoothing).
// The generated code of MechSentinelProcessors.h is included by MechSentinelBehaviorProcessors.cpp.

#include "MechSwarm/Sentinel/MechSentinelProcessors.h"

#include "Engine/World.h"
#include "MassCommonTypes.h"
#include "MassEntityManager.h"
#include "MassExecutionContext.h"
#include "Mass/EntityFragments.h"
#include "MechSwarm/Core/MechSwarmProcessorGroups.h"
#include "MechSwarm/MassCopies/MassMovementFragments_Copy.h"
#include "MechSwarm/MassCopies/MassRepresentationFragments_Copy.h"
#include "MechSwarm/MassCopies/MassRepresentationProcessors_Copy.h"
#include "MechSwarm/Sentinel/MechSentinelFragments.h"

namespace MechSwarm::ClientPrivate
{
	/** Hit flash fades in ~0.25 s, attack glow in ~0.4 s. */
	constexpr float HitFlashFadeSpeed = 4.f;
	constexpr float AttackGlowFadeSpeed = 2.5f;

	/** Never extrapolate further than this past the last replicated sample (s). */
	constexpr float MaxExtrapolationTime = 0.3f;

	/** Exponential smoothing rates (1/s). Higher = tighter. */
	constexpr float PositionSharpness = 10.f;
	constexpr float RotationSharpness = 8.f;

	/** Teleport instead of easing when the error is this large (cm), e.g. right after becoming relevant. */
	constexpr float SnapDistance = 2000.f;
}

//----------------------------------------------------------------------//
// UMechSentinelVisualDataProcessor
//----------------------------------------------------------------------//
UMechSentinelVisualDataProcessor::UMechSentinelVisualDataProcessor()
	: EntityQuery(*this)
{
	// Wherever frames are rendered: standalone, listen server (Client flag) and clients.
	ExecutionFlags = (int32)(EProcessorExecutionFlags::Standalone | EProcessorExecutionFlags::Client);
	ProcessingPhase = EMassProcessingPhase::PostPhysics;
	ExecutionOrder.ExecuteInGroup = MechSwarm::ProcessorGroups::Representation();
	ExecutionOrder.ExecuteBefore.Add(UMassUpdateISMProcessor_Copy::StaticClass()->GetFName());
}

void UMechSentinelVisualDataProcessor::ConfigureQueries(const TSharedRef<FMassEntityManager>& EntityManager)
{
	EntityQuery.AddRequirement<FMechSentinelStateFragment>(EMassFragmentAccess::ReadWrite);
	EntityQuery.AddRequirement<FMechSentinelAttackFragment>(EMassFragmentAccess::ReadWrite);
	EntityQuery.AddRequirement<FMechSentinelAttributesFragment>(EMassFragmentAccess::ReadOnly);
	EntityQuery.AddRequirement<FMassRepresentationCustomDataFragment_Copy>(EMassFragmentAccess::ReadWrite);
	EntityQuery.AddTagRequirement<FMechSentinelTag>(EMassFragmentPresence::All);
}

void UMechSentinelVisualDataProcessor::Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context)
{
	using namespace MechSwarm::ClientPrivate;

	EntityQuery.ForEachEntityChunk(Context, [](FMassExecutionContext& Context)
	{
		const float DeltaTime = Context.GetDeltaTimeSeconds();
		const TArrayView<FMechSentinelStateFragment> StateList = Context.GetMutableFragmentView<FMechSentinelStateFragment>();
		const TArrayView<FMechSentinelAttackFragment> AttackList = Context.GetMutableFragmentView<FMechSentinelAttackFragment>();
		const TConstArrayView<FMechSentinelAttributesFragment> AttributeList = Context.GetFragmentView<FMechSentinelAttributesFragment>();
		const TArrayView<FMassRepresentationCustomDataFragment_Copy> CustomList = Context.GetMutableFragmentView<FMassRepresentationCustomDataFragment_Copy>();

		const int32 NumEntities = Context.GetNumEntities();
		for (int32 EntityIndex = 0; EntityIndex < NumEntities; ++EntityIndex)
		{
			FMechSentinelStateFragment& State = StateList[EntityIndex];
			FMechSentinelAttackFragment& Attack = AttackList[EntityIndex];

			// ISM custom data layout (read it in the material with PerInstanceCustomData):
			//   [0] state (0 Seeking, 1 Attacking, 2 Stunned, 3 Dead)  [1] health fraction
			//   [2] hit flash 0..1                                      [3] attack glow 0..1
			float* Values = CustomList[EntityIndex].Values;
			Values[0] = float(uint8(State.State));
			Values[1] = AttributeList[EntityIndex].GetHealthFraction();
			Values[2] = State.HitFlash;
			Values[3] = Attack.AttackGlow;

			State.HitFlash = FMath::Max(0.f, State.HitFlash - HitFlashFadeSpeed * DeltaTime);
			Attack.AttackGlow = FMath::Max(0.f, Attack.AttackGlow - AttackGlowFadeSpeed * DeltaTime);
		}
	});
}

//----------------------------------------------------------------------//
// UMechSentinelNetSmoothingProcessor
//----------------------------------------------------------------------//
UMechSentinelNetSmoothingProcessor::UMechSentinelNetSmoothingProcessor()
	: EntityQuery(*this)
{
	// The net smoothing fragment only exists on NM_Client, so a listen server never matches this query.
	ExecutionFlags = (int32)EProcessorExecutionFlags::Client;
	ExecutionOrder.ExecuteInGroup = UE::Mass::ProcessorGroupNames::Movement;
}

void UMechSentinelNetSmoothingProcessor::ConfigureQueries(const TSharedRef<FMassEntityManager>& EntityManager)
{
	EntityQuery.AddRequirement<FTransformFragment>(EMassFragmentAccess::ReadWrite);
	EntityQuery.AddRequirement<FMechSentinelNetSmoothingFragment>(EMassFragmentAccess::ReadWrite);
	EntityQuery.AddRequirement<FMassVelocityFragment_Copy>(EMassFragmentAccess::ReadWrite, EMassFragmentPresence::Optional);
	EntityQuery.AddTagRequirement<FMechSentinelTag>(EMassFragmentPresence::All);
}

void UMechSentinelNetSmoothingProcessor::Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context)
{
	using namespace MechSwarm::ClientPrivate;

	const UWorld* World = EntityManager.GetWorld();
	if (!World)
	{
		return;
	}
	const double Now = World->GetTimeSeconds();

	EntityQuery.ForEachEntityChunk(Context, [Now](FMassExecutionContext& Context)
	{
		const float DeltaTime = FMath::Min(0.1f, Context.GetDeltaTimeSeconds());
		const float PositionAlpha = 1.f - FMath::Exp(-PositionSharpness * DeltaTime);
		const float RotationAlpha = 1.f - FMath::Exp(-RotationSharpness * DeltaTime);

		const TArrayView<FTransformFragment> TransformList = Context.GetMutableFragmentView<FTransformFragment>();
		const TArrayView<FMechSentinelNetSmoothingFragment> SmoothingList = Context.GetMutableFragmentView<FMechSentinelNetSmoothingFragment>();
		const TArrayView<FMassVelocityFragment_Copy> VelocityList = Context.GetMutableFragmentView<FMassVelocityFragment_Copy>();

		const int32 NumEntities = Context.GetNumEntities();
		for (int32 EntityIndex = 0; EntityIndex < NumEntities; ++EntityIndex)
		{
			const FMechSentinelNetSmoothingFragment& Net = SmoothingList[EntityIndex];
			if (!Net.bHasSample)
			{
				continue;
			}

			FTransform& Transform = TransformList[EntityIndex].GetMutableTransform();
			const float SinceSample = FMath::Clamp(float(Now - Net.NetReceiveTime), 0.f, MaxExtrapolationTime);
			const FVector Predicted = Net.NetLocation + Net.NetVelocity * SinceSample;

			const FVector Current = Transform.GetLocation();
			if (FVector::DistSquared(Current, Predicted) > FMath::Square(SnapDistance))
			{
				Transform.SetLocation(Predicted);
				Transform.SetRotation(Net.NetRotation);
			}
			else
			{
				Transform.SetLocation(FMath::Lerp(Current, Predicted, PositionAlpha));
				Transform.SetRotation(FQuat::Slerp(Transform.GetRotation(), Net.NetRotation, RotationAlpha).GetNormalized());
			}

			if (VelocityList.Num() > 0)
			{
				VelocityList[EntityIndex].Value = Net.NetVelocity;
			}
		}
	});
}
