// Fill out your copyright notice in the Description page of Project Settings.


#include "Burrower/BurrowerAnimInstance.h"

#include "Burrower/BurrowerCharacter.h"

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
}
