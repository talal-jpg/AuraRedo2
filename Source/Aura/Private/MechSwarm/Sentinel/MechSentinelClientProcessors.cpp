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

	/** Self-buff looks (custom data 4..6) fade in / out in ~0.33 s, following the replicated BuffMask. */
	constexpr float BuffFadeSpeed = 3.f;

	/**
	 * Eye glow floor (custom data 3, under the attack glow) while a self-buff is on: damage steady, speed a fast flicker,
	 * armor slow breathing. At most 0.3, so an attack (glow 1) still stands out.
	 */
	constexpr float DamageEyeFloor = 0.22f;
	constexpr float SpeedEyeFloorMin = 0.05f;
	constexpr float SpeedEyeFloorMax = 0.3f;
	constexpr double SpeedFlickerFrequency = 6.0;
	constexpr float ArmorEyeFloorMin = 0.06f;
	constexpr float ArmorEyeFloorMax = 0.26f;
	constexpr double ArmorBreathFrequency = 0.8;

	static_assert(MechSentinelSelfBuff::FirstFadeCustomDataIndex + MechSentinelSelfBuff::Num <= MechSwarm::Representation::MaxCustomDataFloats,
		"The self-buff fades must fit in the ISM custom data.");

	/** 0..1, fixed per entity: spreads the buff pulses so a buffed swarm does not blink in step. */
	FORCEINLINE float EntityPulseOffset(const FMassEntityHandle Entity)
	{
		return float((uint32(Entity.Index) * 2654435761u) >> 8) * (1.f / 16777216.f);
	}
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

	// This frame's phase (0..1) of each buff rhythm, reduced in double so the pulses stay smooth in long sessions.
	const UWorld* World = EntityManager.GetWorld();
	const double Time = World ? World->GetTimeSeconds() : 0.0;
	const float SpeedPhase = float(FMath::Frac(Time * SpeedFlickerFrequency));
	const float ArmorPhase = float(FMath::Frac(Time * ArmorBreathFrequency));

	EntityQuery.ForEachEntityChunk(Context, [SpeedPhase, ArmorPhase](FMassExecutionContext& Context)
	{
		constexpr int32 ArmorIndex = int32(EMechSentinelSelfBuff::Armor);
		constexpr int32 SpeedIndex = int32(EMechSentinelSelfBuff::Speed);
		constexpr int32 DamageIndex = int32(EMechSentinelSelfBuff::Damage);

		const float DeltaTime = Context.GetDeltaTimeSeconds();
		const float BuffFadeStep = BuffFadeSpeed * DeltaTime;
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
			//   [2] hit flash 0..1                                      [3] attack glow 0..1 (+ buff eye pulse)
			//   [4] armor buff 0..1   [5] speed buff 0..1   [6] damage buff 0..1 (fades of FMechSentinelStateFragment::BuffMask)
			float* Values = CustomList[EntityIndex].Values;
			Values[0] = float(uint8(State.State));
			Values[1] = AttributeList[EntityIndex].GetHealthFraction();
			Values[2] = State.HitFlash;
			Values[3] = Attack.AttackGlow;

			// The fades live in the custom data itself (the fragment keeps them between frames). Wrecks show no buff:
			// the body material has no dead mask.
			float* BuffFades = Values + MechSentinelSelfBuff::FirstFadeCustomDataIndex;
			const bool bDead = State.State == EMechSentinelState::Dead;
			bool bAnyBuff = false;
			for (int32 BuffIndex = 0; BuffIndex < MechSentinelSelfBuff::Num; ++BuffIndex)
			{
				float& Fade = BuffFades[BuffIndex];
				if (bDead)
				{
					Fade = 0.f;
					continue;
				}
				Fade = (State.BuffMask & (1u << BuffIndex)) != 0
					? FMath::Min(1.f, Fade + BuffFadeStep)
					: FMath::Max(0.f, Fade - BuffFadeStep);
				bAnyBuff |= Fade > 0.f;
			}

			if (bAnyBuff)
			{
				const float Offset = EntityPulseOffset(Context.GetEntity(EntityIndex));
				// Armor: smooth breathing. Speed: a sharp flick that decays within each cycle.
				const float Breath = 0.5f - 0.5f * FMath::Cos(UE_TWO_PI * (ArmorPhase + Offset));
				const float Flick = FMath::Square(1.f - FMath::Frac(SpeedPhase + Offset));
				const float EyeFloor = FMath::Max3(
					BuffFades[ArmorIndex] * FMath::Lerp(ArmorEyeFloorMin, ArmorEyeFloorMax, Breath),
					BuffFades[SpeedIndex] * FMath::Lerp(SpeedEyeFloorMin, SpeedEyeFloorMax, Flick),
					BuffFades[DamageIndex] * DamageEyeFloor);
				Values[3] = FMath::Max(Values[3], EyeFloor);
			}

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
