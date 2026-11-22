// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Animation/AnimInstance.h"
#include "BurrowerAnimInstance.generated.h"

class ABurrowerCharacter;
class USkeletalMeshComponent;
class USkinnedAsset;

/**
 * Parent class of ABP_Burrower. Works out, on every machine, the values the AnimGraph passes to the CR_Burrower
 * Control Rig node (pins of the same names): rotor spin, body wave, path-follow bend, death.
 *
 * NativeUpdateAnimation (game thread) copies what it needs from the ABurrowerCharacter and does the path-follow
 * geometry (head trail -> joint angles); the thread-safe update integrates and smooths from those copies only. In
 * the editor preview (no Burrower) it uses ABurrowerCharacter's class defaults, standing still, with no bend.
 * Units, as CR_Burrower expects them: degrees; WaveTime in wave cycles (1 = one period, wrapped to [0, 1)); DeathTime
 * in seconds since death (0 while alive). WaveAmplitudeDeg and WavePitchAmplitudeDeg are speed-scaled (no rig gate).
 */
UCLASS()
class AURA_API UBurrowerAnimInstance : public UAnimInstance
{
	GENERATED_BODY()

public:

	virtual void NativeInitializeAnimation() override;

	virtual void NativeUpdateAnimation(float DeltaSeconds) override;

	virtual void NativeThreadSafeUpdateAnimation(float DeltaSeconds) override;

	/** Rotor spin angle (degrees, [0, 360)), about the body's long axis. */
	UPROPERTY(Transient, BlueprintReadOnly, Category = "Burrower")
	float RotorAngleDeg = 0.f;

	/** Current rotor spin (degrees per second): spins up at spawn and down after death. */
	UPROPERTY(Transient, BlueprintReadOnly, Category = "Burrower")
	float RotorSpinSpeed = 0.f;

	/** Body wave phase in cycles, wrapped to [0, 1). Advances faster with speed. */
	UPROPERTY(Transient, BlueprintReadOnly, Category = "Burrower")
	float WaveTime = 0.f;

	/** Peak sideways swing (degrees) at the tail, already scaled with speed. */
	UPROPERTY(Transient, BlueprintReadOnly, Category = "Burrower")
	float WaveAmplitudeDeg = 0.f;

	/** Phase lag (degrees) from one joint to the next. */
	UPROPERTY(Transient, BlueprintReadOnly, Category = "Burrower")
	float WavePhasePerJointDeg = 65.f;

	/** Peak up/down swing (degrees) at the tail, already scaled with speed. */
	UPROPERTY(Transient, BlueprintReadOnly, Category = "Burrower")
	float WavePitchAmplitudeDeg = 0.f;

	/** Speed (cm/s). */
	UPROPERTY(Transient, BlueprintReadOnly, Category = "Burrower")
	float Speed = 0.f;

	/** True once the Burrower has died on this machine: the rig's ragdoll takes over. */
	UPROPERTY(Transient, BlueprintReadOnly, Category = "Burrower")
	bool bIsDead = false;

	/** Seconds since death, 0 while alive. */
	UPROPERTY(Transient, BlueprintReadOnly, Category = "Burrower")
	float DeathTime = 0.f;

	// Path-follow bend: local angles (degrees) of J1..J4 against the joint in front, so the body traces the head's
	// path. The rig applies them like the wave's angles and adds them to those. Yaw: about component +Z, + swings the
	// segments behind the joint toward -Y. Pitch: about component +Y, + lifts them toward +Z. 0 in the editor
	// preview; they fade to 0 after death.

	UPROPERTY(Transient, BlueprintReadOnly, Category = "Burrower")
	float FollowYawDeg1 = 0.f;

	UPROPERTY(Transient, BlueprintReadOnly, Category = "Burrower")
	float FollowYawDeg2 = 0.f;

	UPROPERTY(Transient, BlueprintReadOnly, Category = "Burrower")
	float FollowYawDeg3 = 0.f;

	UPROPERTY(Transient, BlueprintReadOnly, Category = "Burrower")
	float FollowYawDeg4 = 0.f;

	UPROPERTY(Transient, BlueprintReadOnly, Category = "Burrower")
	float FollowPitchDeg1 = 0.f;

	UPROPERTY(Transient, BlueprintReadOnly, Category = "Burrower")
	float FollowPitchDeg2 = 0.f;

	UPROPERTY(Transient, BlueprintReadOnly, Category = "Burrower")
	float FollowPitchDeg3 = 0.f;

	UPROPERTY(Transient, BlueprintReadOnly, Category = "Burrower")
	float FollowPitchDeg4 = 0.f;

	/** World velocity (cm/s) the ragdoll starts with (ABurrowerCharacter::GetDeathVelocity). 0 while alive. */
	UPROPERTY(Transient, BlueprintReadOnly, Category = "Burrower")
	FVector DeathVelocity = FVector::ZeroVector;

	/** World angular velocity (degrees per second) at death; a body at offset R from the head pivot adds Omega x R. 0 while alive. */
	UPROPERTY(Transient, BlueprintReadOnly, Category = "Burrower")
	FVector DeathAngularVelocity = FVector::ZeroVector;

private:

	/** J1..J4 */
	static constexpr int32 NumFollowJoints = 4;

	UPROPERTY(Transient)
	TObjectPtr<ABurrowerCharacter> Burrower;

	/** Copied on the game thread (NativeUpdateAnimation), read by the thread-safe update. */
	struct FInputs
	{
		float Speed = 0.f;
		bool bDead = false;
		float RotorSpinSpeed = 0.f;
		float RotorSpinAcceleration = 0.f;
		float WaveAmplitudeDeg = 0.f;
		float WavePitchAmplitudeDeg = 0.f;
		float WaveIdleAmplitudeFraction = 1.f;
		float WaveFullAmplitudeSpeed = 0.f;
		float WavePhasePerJointDeg = 65.f;
		float WaveIdleFrequency = 0.f;
		float WaveCyclesPerMeter = 0.f;
		float WaveMaxFrequency = 0.f;
		float WaveAmplitudeInterpSpeed = 0.f;
		float FollowYawTargetDeg[NumFollowJoints] = {};
		float FollowPitchTargetDeg[NumFollowJoints] = {};
		float PathFollowInterpSpeed = 0.f;
		FVector DeathVelocity = FVector::ZeroVector;
		FVector DeathAngularVelocity = FVector::ZeroVector;
	};

	FInputs Inputs;

	// -------------------------------------------------------------------------
	// Path follow (game thread only)
	// -------------------------------------------------------------------------

	/** Trail -> target angles in Inputs (strength and limits applied). */
	void UpdatePathFollow(const ABurrowerCharacter& Character, const USkeletalMeshComponent& MeshComp);

	/** RefHeadPosition and RefArcLength from the mesh's reference skeleton, again whenever the mesh asset changes. */
	void RefreshRefPose(const USkeletalMeshComponent& MeshComp);

	/** Restarts the trail as a straight line behind the head point (spawn, teleport). */
	void ResetTrail(const FVector& HeadPoint, const FVector& BackDirection, double Spacing, double NeededLength);

	/** Drops the points the body no longer reaches. */
	void TrimTrail(double NeededLength);

	/**
	 * Points on the trail at the given arc lengths (ascending, cm) behind HeadPoint. Past the oldest point it carries
	 * on straight along BackDirection.
	 */
	void SampleTrail(const FVector& HeadPoint, const FVector& BackDirection, const double* ArcLengths, int32 Num, FVector* OutPoints) const;

	void ClearFollowTargets();

	/** World positions of the head point, oldest first, about PathFollowSampleSpacing apart. */
	TArray<FVector> Trail;

	/** Head point at the last update (a long jump restarts the trail). */
	FVector LastHeadPoint = FVector::ZeroVector;
	bool bHasLastHeadPoint = false;

	/** Reference pose, mesh component space (cm): J0_Head, and the chain length from it to J1..J4. */
	FVector RefHeadPosition = FVector(1000.0, 0.0, 180.0);
	double RefArcLength[NumFollowJoints] = { 340.2, 740.3, 1260.3, 1560.3 };

	/** The mesh asset RefHeadPosition / RefArcLength were read from. */
	TWeakObjectPtr<const USkinnedAsset> RefPoseAsset;
	bool bRefPoseRead = false;
};
