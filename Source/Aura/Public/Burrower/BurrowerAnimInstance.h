// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Animation/AnimInstance.h"
#include "BurrowerAnimInstance.generated.h"

class ABurrowerCharacter;

/**
 * Parent class of ABP_Burrower. Works out, on every machine, the values the AnimGraph passes to the
 * CR_Burrower Control Rig node (pins of the same names): rotor spin, body wave, death.
 *
 * NativeUpdateAnimation (game thread) copies what it needs from the ABurrowerCharacter; the
 * thread-safe update integrates the angles from those copies only. In the editor preview (no
 * Burrower) it uses ABurrowerCharacter's class defaults, standing still.
 *
 * Units, as CR_Burrower expects them: degrees; WaveTime in wave cycles (1 = one period, wrapped to
 * [0, 1)); DeathTime in seconds since death (0 while alive). WaveAmplitudeDeg and
 * WavePitchAmplitudeDeg are already scaled with speed here (skip the rig's optional speed gate).
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

private:

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
	};

	FInputs Inputs;
};
