// Fill out your copyright notice in the Description page of Project Settings.


#include "Burrower/BurrowerAnimInstance.h"

#include "AnimationRuntime.h"
#include "Burrower/BurrowerCharacter.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkinnedAsset.h"
#include "ReferenceSkeleton.h"

// Named, not anonymous: the unity build compiles this file together with others
namespace BurrowerAnimInstancePrivate
{
	// The chain, head to tail, and its reference-pose positions (mesh component space, cm) when the mesh lacks a bone
	constexpr int32 NumChainBones = 5;

	const TCHAR* const ChainBoneNames[NumChainBones] = { TEXT("J0_Head"), TEXT("J1_Forequarters"), TEXT("J2_Midbody"), TEXT("J3_Hindbody"), TEXT("J4_Tail") };

	const FVector FallbackChainPositions[NumChainBones] =
	{
		FVector(1000.0, 0.0, 180.0),
		FVector(660.0, 0.0, 193.0),
		FVector(260.0, 0.0, 200.0),
		FVector(-260.0, 0.0, 200.0),
		FVector(-560.0, 0.0, 202.0),
	};

	// The trail reaches this far (cm, unscaled) past the tail tip
	constexpr double TrailMargin = 200.0;

	// The head point jumping farther than this (cm, unscaled) in one update is a spawn or a teleport: the trail restarts
	constexpr double TrailResetDistance = 2000.0;

	// Hard cap on the trail (PathFollowSampleSpacing >= 10 cm keeps it near 230)
	constexpr int32 MaxTrailPoints = 512;

	// How fast the bend fades out after death (per second, as FInterpTo)
	constexpr float DeathFadeSpeed = 4.f;
}

void UBurrowerAnimInstance::NativeInitializeAnimation()
{
	Super::NativeInitializeAnimation();

	Burrower = Cast<ABurrowerCharacter>(TryGetPawnOwner());
}

void UBurrowerAnimInstance::NativeUpdateAnimation(float DeltaSeconds)
{
	Super::NativeUpdateAnimation(DeltaSeconds);

	if (!Burrower)
	{
		Burrower = Cast<ABurrowerCharacter>(TryGetPawnOwner());
	}

	// Editor preview (no Burrower): the class defaults, standing still
	const ABurrowerCharacter* Source = Burrower ? Burrower.Get() : GetDefault<ABurrowerCharacter>();

	Inputs.Speed = Burrower ? static_cast<float>(Burrower->GetVelocity().Size()) : 0.f;
	Inputs.bDead = Burrower ? Burrower->IsBurrowerDead() : false;
	Inputs.RotorSpinSpeed = Source->RotorSpinSpeed;
	Inputs.RotorSpinAcceleration = Source->RotorSpinAcceleration;
	Inputs.WaveAmplitudeDeg = Source->BodyWaveAmplitudeDeg;
	Inputs.WavePitchAmplitudeDeg = Source->BodyWavePitchAmplitudeDeg;
	Inputs.WaveIdleAmplitudeFraction = Source->BodyWaveIdleAmplitudeFraction;
	Inputs.WaveFullAmplitudeSpeed = Source->BodyWaveFullAmplitudeSpeed;
	Inputs.WavePhasePerJointDeg = Source->BodyWavePhasePerJointDeg;
	Inputs.WaveIdleFrequency = Source->BodyWaveIdleFrequency;
	Inputs.WaveCyclesPerMeter = Source->BodyWaveCyclesPerMeter;
	Inputs.WaveMaxFrequency = Source->BodyWaveMaxFrequency;
	Inputs.WaveAmplitudeInterpSpeed = Source->BodyWaveAmplitudeInterpSpeed;
	Inputs.PathFollowInterpSpeed = Source->PathFollowInterpSpeed;

	// Death: what the rig's ragdoll starts with, set in the same update as bDead
	Inputs.DeathVelocity = Inputs.bDead ? Burrower->GetDeathVelocity() : FVector::ZeroVector;
	Inputs.DeathAngularVelocity = Inputs.bDead ? Burrower->GetDeathAngularVelocity() : FVector::ZeroVector;

	// Path follow: no bend in the preview, and none to aim for once dead (the ragdoll takes over; the trail stays)
	const USkeletalMeshComponent* MeshComp = GetSkelMeshComponent();

	if (!Burrower || !MeshComp)
	{
		ClearFollowTargets();
		Trail.Reset();
		bHasLastHeadPoint = false;
	}
	else if (Inputs.bDead)
	{
		ClearFollowTargets();
	}
	else
	{
		UpdatePathFollow(*Burrower, *MeshComp);
	}
}

void UBurrowerAnimInstance::NativeThreadSafeUpdateAnimation(float DeltaSeconds)
{
	Super::NativeThreadSafeUpdateAnimation(DeltaSeconds);

	// Only the copies in Inputs from here on: this may run on a worker thread
	const float Dt = FMath::Max(DeltaSeconds, 0.f);

	Speed = Inputs.Speed;

	// Death
	if (Inputs.bDead)
	{
		DeathTime = bIsDead ? DeathTime + Dt : Dt;
		bIsDead = true;
	}
	else
	{
		DeathTime = 0.f;
		bIsDead = false;
	}

	DeathVelocity = bIsDead ? Inputs.DeathVelocity : FVector::ZeroVector;
	DeathAngularVelocity = bIsDead ? Inputs.DeathAngularVelocity : FVector::ZeroVector;

	// Rotor: spins up / down toward its speed (0 once dead)
	const float TargetSpin = bIsDead ? 0.f : Inputs.RotorSpinSpeed;

	RotorSpinSpeed = Inputs.RotorSpinAcceleration > 0.f
		? FMath::FInterpConstantTo(RotorSpinSpeed, TargetSpin, Dt, Inputs.RotorSpinAcceleration)
		: TargetSpin;

	RotorAngleDeg = FMath::Fmod(RotorAngleDeg + RotorSpinSpeed * Dt, 360.f);

	if (RotorAngleDeg < 0.f)
	{
		RotorAngleDeg += 360.f;
	}

	// Body wave: the amplitudes grow with speed (from the idle fraction) and fade out after death
	const float SpeedAlpha = Inputs.WaveFullAmplitudeSpeed > 0.f ? FMath::Clamp(Speed / Inputs.WaveFullAmplitudeSpeed, 0.f, 1.f) : 1.f;
	const float AmplitudeScale = bIsDead ? 0.f : FMath::Lerp(Inputs.WaveIdleAmplitudeFraction, 1.f, SpeedAlpha);

	WaveAmplitudeDeg = FMath::FInterpTo(WaveAmplitudeDeg, Inputs.WaveAmplitudeDeg * AmplitudeScale, Dt, Inputs.WaveAmplitudeInterpSpeed);
	WavePitchAmplitudeDeg = FMath::FInterpTo(WavePitchAmplitudeDeg, Inputs.WavePitchAmplitudeDeg * AmplitudeScale, Dt, Inputs.WaveAmplitudeInterpSpeed);
	WavePhasePerJointDeg = Inputs.WavePhasePerJointDeg;

	// Waves per second: idle + per metre travelled, capped. Integrated, so a speed change never jumps the phase.
	float Frequency = Inputs.WaveIdleFrequency + Speed * 0.01f * Inputs.WaveCyclesPerMeter;

	if (Inputs.WaveMaxFrequency > 0.f)
	{
		Frequency = FMath::Min(Frequency, Inputs.WaveMaxFrequency);
	}

	// Whole cycles dropped: the rig's sine doesn't see the wrap
	WaveTime = FMath::Fmod(WaveTime + FMath::Max(Frequency, 0.f) * Dt, 1.f);

	// Path-follow bend: smoothed toward the game thread's targets (0 = at once); after death it fades to 0
	const float FollowInterpSpeed = bIsDead ? BurrowerAnimInstancePrivate::DeathFadeSpeed : Inputs.PathFollowInterpSpeed;
	float* const FollowYaw[NumFollowJoints] = { &FollowYawDeg1, &FollowYawDeg2, &FollowYawDeg3, &FollowYawDeg4 };
	float* const FollowPitch[NumFollowJoints] = { &FollowPitchDeg1, &FollowPitchDeg2, &FollowPitchDeg3, &FollowPitchDeg4 };

	for (int32 Joint = 0; Joint < NumFollowJoints; ++Joint)
	{
		*FollowYaw[Joint] = FMath::FInterpTo(*FollowYaw[Joint], Inputs.FollowYawTargetDeg[Joint], Dt, FollowInterpSpeed);
		*FollowPitch[Joint] = FMath::FInterpTo(*FollowPitch[Joint], Inputs.FollowPitchTargetDeg[Joint], Dt, FollowInterpSpeed);
	}
}


// =============================================================================
// Path follow (game thread)
// =============================================================================

void UBurrowerAnimInstance::ClearFollowTargets()
{
	for (int32 Joint = 0; Joint < NumFollowJoints; ++Joint)
	{
		Inputs.FollowYawTargetDeg[Joint] = 0.f;
		Inputs.FollowPitchTargetDeg[Joint] = 0.f;
	}
}

void UBurrowerAnimInstance::RefreshRefPose(const USkeletalMeshComponent& MeshComp)
{
	using namespace BurrowerAnimInstancePrivate;

	const USkinnedAsset* Asset = MeshComp.GetSkinnedAsset();

	if (bRefPoseRead && RefPoseAsset.Get() == Asset)
	{
		return;
	}

	bRefPoseRead = true;
	RefPoseAsset = Asset;

	FVector Positions[NumChainBones];

	for (int32 Bone = 0; Bone < NumChainBones; ++Bone)
	{
		Positions[Bone] = FallbackChainPositions[Bone];
	}

	// All five bones from the mesh, or the numbers above for all of them (no mix)
	if (Asset)
	{
		const FReferenceSkeleton& RefSkeleton = Asset->GetRefSkeleton();
		FVector FromMesh[NumChainBones];
		bool bFoundAll = true;

		for (int32 Bone = 0; Bone < NumChainBones && bFoundAll; ++Bone)
		{
			const int32 BoneIndex = RefSkeleton.FindBoneIndex(FName(ChainBoneNames[Bone]));
			bFoundAll = BoneIndex != INDEX_NONE;

			if (bFoundAll)
			{
				FromMesh[Bone] = FAnimationRuntime::GetComponentSpaceTransformRefPose(RefSkeleton, BoneIndex).GetLocation();
			}
		}

		if (bFoundAll)
		{
			for (int32 Bone = 0; Bone < NumChainBones; ++Bone)
			{
				Positions[Bone] = FromMesh[Bone];
			}
		}
	}

	RefHeadPosition = Positions[0];

	double ChainLength = 0.0;

	for (int32 Joint = 0; Joint < NumFollowJoints; ++Joint)
	{
		ChainLength += FVector::Dist(Positions[Joint], Positions[Joint + 1]);
		RefArcLength[Joint] = ChainLength;
	}
}

void UBurrowerAnimInstance::ResetTrail(const FVector& HeadPoint, const FVector& BackDirection, double Spacing, double NeededLength)
{
	using namespace BurrowerAnimInstancePrivate;

	// The body lies straight behind the head, as at spawn
	const int32 NumBehind = FMath::Clamp(FMath::CeilToInt32(NeededLength / Spacing), 1, MaxTrailPoints - 1);

	Trail.Reset(NumBehind + 1);

	for (int32 Point = NumBehind; Point >= 1; --Point)
	{
		Trail.Add(HeadPoint + BackDirection * (Spacing * Point));
	}

	Trail.Add(HeadPoint);
}

void UBurrowerAnimInstance::TrimTrail(double NeededLength)
{
	using namespace BurrowerAnimInstancePrivate;

	// Keep the newest points whose length reaches NeededLength
	double Length = 0.0;

	for (int32 Point = Trail.Num() - 1; Point > 0; --Point)
	{
		Length += FVector::Dist(Trail[Point], Trail[Point - 1]);

		if (Length >= NeededLength)
		{
			// Trail[Point - 1] is the oldest one still needed
			if (Point - 1 > 0)
			{
				Trail.RemoveAt(0, Point - 1, EAllowShrinking::No);
			}

			break;
		}
	}

	if (Trail.Num() > MaxTrailPoints)
	{
		Trail.RemoveAt(0, Trail.Num() - MaxTrailPoints, EAllowShrinking::No);
	}
}

void UBurrowerAnimInstance::SampleTrail(const FVector& HeadPoint, const FVector& BackDirection, const double* ArcLengths, int32 Num, FVector* OutPoints) const
{
	int32 Next = 0;
	FVector SegmentStart = HeadPoint;
	double StartArc = 0.0;

	// Newest point first: the polyline from the head point back in time
	for (int32 Point = Trail.Num() - 1; Point >= 0 && Next < Num; --Point)
	{
		const FVector& SegmentEnd = Trail[Point];
		const double SegmentLength = FVector::Dist(SegmentStart, SegmentEnd);

		if (SegmentLength < UE_KINDA_SMALL_NUMBER)
		{
			continue;
		}

		const double EndArc = StartArc + SegmentLength;

		while (Next < Num && ArcLengths[Next] <= EndArc)
		{
			OutPoints[Next] = FMath::Lerp(SegmentStart, SegmentEnd, (ArcLengths[Next] - StartArc) / SegmentLength);
			++Next;
		}

		SegmentStart = SegmentEnd;
		StartArc = EndArc;
	}

	// Trail too short: straight on behind its end
	for (; Next < Num; ++Next)
	{
		OutPoints[Next] = SegmentStart + BackDirection * (ArcLengths[Next] - StartArc);
	}
}

void UBurrowerAnimInstance::UpdatePathFollow(const ABurrowerCharacter& Character, const USkeletalMeshComponent& MeshComp)
{
	using namespace BurrowerAnimInstancePrivate;

	RefreshRefPose(MeshComp);

	// The mesh, not the actor: a client's mesh smoothing is part of the path
	const FTransform MeshToWorld = MeshComp.GetComponentTransform();
	const FQuat MeshRotation = MeshToWorld.GetRotation();
	const FVector HeadPoint = MeshToWorld.TransformPosition(RefHeadPosition);
	const FVector BackDirection = -MeshRotation.GetForwardVector();
	const double MeshScale = FMath::Max(static_cast<double>(MeshToWorld.GetMaximumAxisScale()), UE_KINDA_SMALL_NUMBER);
	const double Spacing = FMath::Max(static_cast<double>(Character.PathFollowSampleSpacing), 10.0) * MeshScale;

	// Arc lengths behind the head point (world cm): J1..J4, then the tail tip
	double ArcLengths[NumFollowJoints + 1];

	for (int32 Joint = 0; Joint < NumFollowJoints; ++Joint)
	{
		ArcLengths[Joint] = RefArcLength[Joint] * MeshScale;
	}

	ArcLengths[NumFollowJoints] = ArcLengths[NumFollowJoints - 1] + FMath::Max(static_cast<double>(Character.PathFollowTailLength), 0.0) * MeshScale;

	const double NeededLength = ArcLengths[NumFollowJoints] + TrailMargin * MeshScale + Spacing;

	// Trail: a new point every Spacing; a jump (spawn, teleport, first update) restarts it straight behind the head
	if (!bHasLastHeadPoint || Trail.Num() == 0 || FVector::DistSquared(HeadPoint, LastHeadPoint) > FMath::Square(TrailResetDistance * MeshScale))
	{
		ResetTrail(HeadPoint, BackDirection, Spacing, NeededLength);
	}
	else if (FVector::DistSquared(HeadPoint, Trail.Last()) >= FMath::Square(Spacing))
	{
		Trail.Add(HeadPoint);
		TrimTrail(NeededLength);
	}

	LastHeadPoint = HeadPoint;
	bHasLastHeadPoint = true;

	// Where J1..J4 and the tail tip would be if the body lay on the head's path
	FVector Targets[NumFollowJoints + 1];
	SampleTrail(HeadPoint, BackDirection, ArcLengths, NumFollowJoints + 1, Targets);

	const double Strength = FMath::Max(static_cast<double>(Character.PathFollowStrength), 0.0);
	const double MaxYawDeg = FMath::Max(static_cast<double>(Character.PathFollowMaxYawDeg), 0.0);
	const double MaxPitchDeg = FMath::Max(static_cast<double>(Character.PathFollowMaxPitchDeg), 0.0);

	// Each segment J(k) -> J(k+1) (the tail tip after J4) points from its target to the next one. Its joint's local
	// angles are that direction seen from the segment in front of it, as the rig bends it: the rig sets
	// Delta(k) = Delta(k-1) * Quat(+Z, Yaw(k)) * Quat(+Y, Pitch(k)) in component space (J0 not turned: the head stays
	// on its heading), and for a segment at rest along -X, Quat(+Z, a) raises atan2(y, x) by a (the tail swings to -Y)
	// and Quat(+Y, b) raises its elevation by b. So Yaw = atan2(-e.y, -e.x) and Pitch = atan2(e.z, |e.xy|), with e the
	// direction in the parent's frame. Measured against -X, not the slightly bent rest segments, so a straight path
	// gives 0. For pure yaw or pure pitch this is the heading change from the segment in front.
	FQuat ParentDelta = FQuat::Identity;

	for (int32 Joint = 0; Joint < NumFollowJoints; ++Joint)
	{
		const FVector Segment = MeshRotation.UnrotateVector(Targets[Joint + 1] - Targets[Joint]);
		const FVector Local = ParentDelta.UnrotateVector(Segment);
		double YawRad = 0.0;
		double PitchRad = 0.0;

		if (Local.SizeSquared() > UE_KINDA_SMALL_NUMBER)
		{
			YawRad = FMath::Atan2(-Local.Y, -Local.X);
			PitchRad = FMath::Atan2(Local.Z, FMath::Sqrt(FMath::Square(Local.X) + FMath::Square(Local.Y)));
		}

		// The ideal bend (no strength, no limits) carries on to the next joint, so each one stays a local angle
		ParentDelta = ParentDelta * FQuat(FVector::UpVector, YawRad) * FQuat(FVector::RightVector, PitchRad);

		Inputs.FollowYawTargetDeg[Joint] = static_cast<float>(FMath::Clamp(FMath::RadiansToDegrees(YawRad) * Strength, -MaxYawDeg, MaxYawDeg));
		Inputs.FollowPitchTargetDeg[Joint] = static_cast<float>(FMath::Clamp(FMath::RadiansToDegrees(PitchRad) * Strength, -MaxPitchDeg, MaxPitchDeg));
	}
}
