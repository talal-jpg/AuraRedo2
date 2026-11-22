// Fill out your copyright notice in the Description page of Project Settings.


#include "Airship/AirshipAnimInstance.h"

#include "AnimNode_ControlRig.h"
#include "Animation/AnimClassInterface.h"
#include "Airship/AirshipPawn.h"
#include "ControlRig.h"
#include "UObject/UnrealType.h"

// Named, not anonymous: the unity build compiles this file together with others
namespace AirshipAnimPrivate
{
	/** A float rig variable and the property that holds its value here (same name). */
	struct FFloatVariable
	{
		const TCHAR* Name;
		float UAirshipAnimInstance::* Member;
	};

	/** RIG_CONTRACT.md section 5, in order. bIsDead is written separately (bool). */
	const FFloatVariable FloatVariables[] =
	{
		{ TEXT("NozzlePitchDeg_FL"), &UAirshipAnimInstance::NozzlePitchDeg_FL },
		{ TEXT("NozzlePitchDeg_FR"), &UAirshipAnimInstance::NozzlePitchDeg_FR },
		{ TEXT("NozzlePitchDeg_RL"), &UAirshipAnimInstance::NozzlePitchDeg_RL },
		{ TEXT("NozzlePitchDeg_RR"), &UAirshipAnimInstance::NozzlePitchDeg_RR },
		{ TEXT("NozzleRollDeg_FL"), &UAirshipAnimInstance::NozzleRollDeg_FL },
		{ TEXT("NozzleRollDeg_FR"), &UAirshipAnimInstance::NozzleRollDeg_FR },
		{ TEXT("NozzleRollDeg_RL"), &UAirshipAnimInstance::NozzleRollDeg_RL },
		{ TEXT("NozzleRollDeg_RR"), &UAirshipAnimInstance::NozzleRollDeg_RR },
		{ TEXT("NozzleFlareDeg_FL"), &UAirshipAnimInstance::NozzleFlareDeg_FL },
		{ TEXT("NozzleFlareDeg_FR"), &UAirshipAnimInstance::NozzleFlareDeg_FR },
		{ TEXT("NozzleFlareDeg_RL"), &UAirshipAnimInstance::NozzleFlareDeg_RL },
		{ TEXT("NozzleFlareDeg_RR"), &UAirshipAnimInstance::NozzleFlareDeg_RR },
		{ TEXT("ThrustAlpha_FL"), &UAirshipAnimInstance::ThrustAlpha_FL },
		{ TEXT("ThrustAlpha_FR"), &UAirshipAnimInstance::ThrustAlpha_FR },
		{ TEXT("ThrustAlpha_RL"), &UAirshipAnimInstance::ThrustAlpha_RL },
		{ TEXT("ThrustAlpha_RR"), &UAirshipAnimInstance::ThrustAlpha_RR },
		{ TEXT("TurbineYawDeg_L"), &UAirshipAnimInstance::TurbineYawDeg_L },
		{ TEXT("TurbineYawDeg_R"), &UAirshipAnimInstance::TurbineYawDeg_R },
		{ TEXT("RotorAngleDeg_L"), &UAirshipAnimInstance::RotorAngleDeg_L },
		{ TEXT("RotorAngleDeg_R"), &UAirshipAnimInstance::RotorAngleDeg_R },
		{ TEXT("RudderDeg"), &UAirshipAnimInstance::RudderDeg },
		{ TEXT("WheelAngleDeg"), &UAirshipAnimInstance::WheelAngleDeg },
		{ TEXT("CannonYawDeg_L1"), &UAirshipAnimInstance::CannonYawDeg_L1 },
		{ TEXT("CannonYawDeg_L2"), &UAirshipAnimInstance::CannonYawDeg_L2 },
		{ TEXT("CannonYawDeg_R1"), &UAirshipAnimInstance::CannonYawDeg_R1 },
		{ TEXT("CannonYawDeg_R2"), &UAirshipAnimInstance::CannonYawDeg_R2 },
		{ TEXT("CannonElevDeg_L1"), &UAirshipAnimInstance::CannonElevDeg_L1 },
		{ TEXT("CannonElevDeg_L2"), &UAirshipAnimInstance::CannonElevDeg_L2 },
		{ TEXT("CannonElevDeg_R1"), &UAirshipAnimInstance::CannonElevDeg_R1 },
		{ TEXT("CannonElevDeg_R2"), &UAirshipAnimInstance::CannonElevDeg_R2 },
		{ TEXT("CannonRecoilCm_L1"), &UAirshipAnimInstance::CannonRecoilCm_L1 },
		{ TEXT("CannonRecoilCm_L2"), &UAirshipAnimInstance::CannonRecoilCm_L2 },
		{ TEXT("CannonRecoilCm_R1"), &UAirshipAnimInstance::CannonRecoilCm_R1 },
		{ TEXT("CannonRecoilCm_R2"), &UAirshipAnimInstance::CannonRecoilCm_R2 },
		{ TEXT("SearchLightPanDeg"), &UAirshipAnimInstance::SearchLightPanDeg },
		{ TEXT("DeathTime"), &UAirshipAnimInstance::DeathTime },
	};

	constexpr int32 NumFloatVariables = UE_ARRAY_COUNT(FloatVariables);

	/** Slot index of bIsDead (after the floats). */
	constexpr int32 DeadSlot = NumFloatVariables;

	const FName DeadVariableName(TEXT("bIsDead"));

	float WrapDegrees(float Angle)
	{
		Angle = FMath::Fmod(Angle, 360.f);
		return Angle < 0.f ? Angle + 360.f : Angle;
	}

	/** Recoil curve: smooth out over Attack, eased back over Return. Time = since the shot. */
	float RecoilCurve(float Time, float MaxCm, float Attack, float Return)
	{
		if (Time < 0.f || Time >= Attack + Return)
		{
			return 0.f;
		}

		if (Time < Attack)
		{
			const float A = Time / Attack;
			return MaxCm * (1.f - FMath::Square(1.f - A));
		}

		const float B = (Time - Attack) / Return;
		return MaxCm * (1.f - FMath::SmoothStep(0.f, 1.f, B));
	}
}

void UAirshipAnimInstance::NativeInitializeAnimation()
{
	Super::NativeInitializeAnimation();

	Ship = Cast<AAirshipPawn>(GetOwningActor());
}

void UAirshipAnimInstance::NativeUpdateAnimation(float DeltaSeconds)
{
	Super::NativeUpdateAnimation(DeltaSeconds);

	if (!Ship)
	{
		Ship = Cast<AAirshipPawn>(GetOwningActor());
	}

	Inputs.bHasShip = Ship != nullptr;

	if (!Ship)
	{
		// Editor preview: idle
		Inputs.bDead = false;
		Inputs.DeathTime = 0.f;
		Inputs.Cosmetic = FAirshipCosmeticState();

		for (int32 Pod = 0; Pod < Airship::NumPods; ++Pod)
		{
			Inputs.Cosmetic.PodThrustAlpha[Pod] = 1.f;
		}
		return;
	}

	Inputs.bDead = Ship->IsAirshipDead();
	Inputs.DeathTime = Ship->GetDeathTime();
	Inputs.Cosmetic = Ship->GetCosmeticState();

	for (int32 Cannon = 0; Cannon < Airship::NumCannons; ++Cannon)
	{
		Inputs.CannonAimYawDeg[Cannon] = Ship->GetCannonAimYawDeg(Cannon);
		Inputs.CannonAimElevDeg[Cannon] = Ship->GetCannonAimElevDeg(Cannon);
		Inputs.CannonFireCount[Cannon] = Ship->GetCannonFireCount(Cannon);
	}
}

void UAirshipAnimInstance::NativeThreadSafeUpdateAnimation(float DeltaSeconds)
{
	Super::NativeThreadSafeUpdateAnimation(DeltaSeconds);

	using namespace AirshipAnimPrivate;

	// Only the copies in Inputs from here on: this may run on a worker thread
	const float Dt = FMath::Clamp(DeltaSeconds, 0.f, 0.1f);
	const FAirshipCosmeticState& C = Inputs.Cosmetic;

	// ---- Death ----
	const bool bWasDead = bIsDead;

	if (Inputs.bDead)
	{
		// The ship's clock: a client that joins after the death doesn't replay the timed break-offs
		DeathTime = FMath::Max(Inputs.DeathTime, 0.f);
		bIsDead = true;
	}
	else
	{
		DeathTime = 0.f;
		bIsDead = false;
	}

	const bool bAlive = !bIsDead;

	// ---- Thrusters ----
	for (int32 Pod = 0; Pod < Airship::NumPods; ++Pod)
	{
		// Rig: + pitch swings the exit aft = thrust leans forward; + roll swings the exit toward +Y = thrust leans left
		const float PitchTarget = bAlive ? FMath::Clamp(C.PodGimbalPitchDeg[Pod], -NozzleMaxDeg, NozzleMaxDeg) : 0.f;
		const float RollTarget = bAlive ? FMath::Clamp(-C.PodGimbalRollDeg[Pod], -NozzleMaxDeg, NozzleMaxDeg) : 0.f;
		NozzlePitch[Pod] = FMath::FInterpTo(NozzlePitch[Pod], PitchTarget, Dt, NozzleInterpSpeed);
		NozzleRoll[Pod] = FMath::FInterpTo(NozzleRoll[Pod], RollTarget, Dt, NozzleInterpSpeed);

		const float AlphaTarget = bAlive ? FMath::Clamp(C.PodThrustAlpha[Pod], 0.f, 1.5f) : 0.f;
		ThrustAlpha[Pod] = FMath::FInterpTo(ThrustAlpha[Pod], AlphaTarget, Dt, ThrustAlphaInterpSpeed);

		const float FlareTarget = bAlive ? FMath::Clamp(FlareAtHoverDeg + (ThrustAlpha[Pod] - 1.f) * FlarePerThrust, FlareMinDeg, FlareMaxDeg) : 0.f;
		NozzleFlare[Pod] = FMath::FInterpTo(NozzleFlare[Pod], FlareTarget, Dt, FlareInterpSpeed);
	}

	// ---- Turbines: housing yaw (slew limited) and rotor spin ----
	if (!bRotorsStarted)
	{
		// Start at idle, not from a standstill (the ship spawns flying)
		RotorSpeed[0] = RotorIdleDegPerSec;
		RotorSpeed[1] = RotorIdleDegPerSec;
		bRotorsStarted = true;
	}

	for (int32 Fan = 0; Fan < Airship::NumFans; ++Fan)
	{
		const float YawTarget = bAlive ? FMath::Clamp(C.FanYawDeg, -TurbineYawMaxDeg, TurbineYawMaxDeg) : TurbineYaw[Fan];
		TurbineYaw[Fan] = FMath::FInterpConstantTo(TurbineYaw[Fan], YawTarget, Dt, TurbineYawSlewDegPerSec);

		const float Thrust = C.FanThrust[Fan];
		const float BoostScale = FMath::Lerp(1.f, RotorBoostMultiplier, C.Boost);
		const float SpinTarget = bAlive
			? (Thrust >= 0.f ? 1.f : -1.f) * (RotorIdleDegPerSec + RotorMaxDegPerSec * FMath::Abs(Thrust)) * BoostScale
			: 0.f;

		RotorSpeed[Fan] = FMath::FInterpConstantTo(RotorSpeed[Fan], SpinTarget, Dt, bAlive ? RotorSpinAcceleration : RotorSpinDownRate);
		RotorAngle[Fan] = WrapDegrees(RotorAngle[Fan] + RotorSpeed[Fan] * Dt);
	}

	// ---- Rudder ----
	const float RudderTarget = bAlive ? FMath::Clamp(C.Steer * RudderDegPerSteer, -RudderMaxDeg, RudderMaxDeg) : RudderDeg;
	RudderDeg = FMath::FInterpTo(RudderDeg, RudderTarget, Dt, RudderInterpSpeed);

	// ---- Helm wheel: spring with overshoot; after death it spins down freely ----
	if (bAlive)
	{
		const float Target = C.Steer * WheelDegPerSteer;
		const float Omega = WheelSpringOmega;
		WheelVelocity += (Omega * Omega * (Target - WheelAngleDeg) - 2.f * WheelSpringDamping * Omega * WheelVelocity) * Dt;
	}
	else
	{
		if (!bWasDead)
		{
			WheelVelocity += WheelDeathSpinDegPerSec;
		}
		WheelVelocity *= FMath::Exp(-WheelDeathSpinDecay * Dt);
	}
	WheelAngleDeg += WheelVelocity * Dt;

	// ---- Cannons: aim (slew limited) and recoil ----
	for (int32 Cannon = 0; Cannon < Airship::NumCannons; ++Cannon)
	{
		if (bAlive)
		{
			const float YawTarget = FMath::Clamp(Inputs.CannonAimYawDeg[Cannon], -CannonYawLimitDeg, CannonYawLimitDeg);
			const float ElevTarget = FMath::Clamp(Inputs.CannonAimElevDeg[Cannon], CannonElevMinDeg, CannonElevMaxDeg);
			CannonYaw[Cannon] = FMath::FInterpConstantTo(CannonYaw[Cannon], YawTarget, Dt, CannonAimSlewDegPerSec);
			const float ElevSlew = CannonElevSettleRate > 0.f
				? FMath::Min(CannonAimSlewDegPerSec, FMath::Abs(ElevTarget - CannonElev[Cannon]) * CannonElevSettleRate)
				: CannonAimSlewDegPerSec;
			CannonElev[Cannon] = FMath::FInterpConstantTo(CannonElev[Cannon], ElevTarget, Dt, ElevSlew);
		}

		// A higher shot count than last time = it fired (counts only go up)
		if (!bFireCountsSeeded)
		{
			SeenFireCount[Cannon] = Inputs.CannonFireCount[Cannon];
		}
		else if (Inputs.CannonFireCount[Cannon] != SeenFireCount[Cannon])
		{
			SeenFireCount[Cannon] = Inputs.CannonFireCount[Cannon];
			RecoilTime[Cannon] = 0.f;
		}

		RecoilTime[Cannon] = FMath::Min(RecoilTime[Cannon] + Dt, 1000.f);
	}
	bFireCountsSeeded = true;

	// ---- Searchlights ----
	if (bAlive)
	{
		SearchLightTime += Dt;
	}
	SearchLightPanDeg = SearchLightPanAmplitudeDeg * FMath::Sin(2.f * PI * SearchLightPanFrequency * SearchLightTime);

	// ---- Named outputs ----
	NozzlePitchDeg_FL = NozzlePitch[0];
	NozzlePitchDeg_FR = NozzlePitch[1];
	NozzlePitchDeg_RL = NozzlePitch[2];
	NozzlePitchDeg_RR = NozzlePitch[3];
	NozzleRollDeg_FL = NozzleRoll[0];
	NozzleRollDeg_FR = NozzleRoll[1];
	NozzleRollDeg_RL = NozzleRoll[2];
	NozzleRollDeg_RR = NozzleRoll[3];
	NozzleFlareDeg_FL = NozzleFlare[0];
	NozzleFlareDeg_FR = NozzleFlare[1];
	NozzleFlareDeg_RL = NozzleFlare[2];
	NozzleFlareDeg_RR = NozzleFlare[3];
	ThrustAlpha_FL = ThrustAlpha[0];
	ThrustAlpha_FR = ThrustAlpha[1];
	ThrustAlpha_RL = ThrustAlpha[2];
	ThrustAlpha_RR = ThrustAlpha[3];
	TurbineYawDeg_L = TurbineYaw[0];
	TurbineYawDeg_R = TurbineYaw[1];
	RotorAngleDeg_L = RotorAngle[0];
	RotorAngleDeg_R = RotorAngle[1];

	CannonYawDeg_L1 = CannonYaw[0];
	CannonYawDeg_L2 = CannonYaw[1];
	CannonYawDeg_R1 = CannonYaw[2];
	CannonYawDeg_R2 = CannonYaw[3];
	CannonElevDeg_L1 = CannonElev[0];
	CannonElevDeg_L2 = CannonElev[1];
	CannonElevDeg_R1 = CannonElev[2];
	CannonElevDeg_R2 = CannonElev[3];
	CannonRecoilCm_L1 = RecoilCurve(RecoilTime[0], CannonRecoilMaxCm, CannonRecoilAttackTime, CannonRecoilReturnTime);
	CannonRecoilCm_L2 = RecoilCurve(RecoilTime[1], CannonRecoilMaxCm, CannonRecoilAttackTime, CannonRecoilReturnTime);
	CannonRecoilCm_R1 = RecoilCurve(RecoilTime[2], CannonRecoilMaxCm, CannonRecoilAttackTime, CannonRecoilReturnTime);
	CannonRecoilCm_R2 = RecoilCurve(RecoilTime[3], CannonRecoilMaxCm, CannonRecoilAttackTime, CannonRecoilReturnTime);

	// ---- Into the rig ----
	if (bWriteRigVariables)
	{
		if (UControlRig* Rig = FindControlRig())
		{
			WriteRigVariables(Rig);
		}
	}
}


// =============================================================================
// Rig variables
// =============================================================================

UControlRig* UAirshipAnimInstance::FindControlRig()
{
	if (!bSearchedControlRigNode)
	{
		bSearchedControlRigNode = true;
		ControlRigNodeProperty = nullptr;

		if (const IAnimClassInterface* AnimClass = IAnimClassInterface::GetFromClass(GetClass()))
		{
			for (const FStructProperty* NodeProperty : AnimClass->GetAnimNodeProperties())
			{
				if (NodeProperty && NodeProperty->Struct && NodeProperty->Struct->IsChildOf(FAnimNode_ControlRig::StaticStruct()))
				{
					ControlRigNodeProperty = NodeProperty;
					break;
				}
			}
		}
	}

	if (!ControlRigNodeProperty)
	{
		return nullptr;
	}

	const FAnimNode_ControlRig* Node = ControlRigNodeProperty->ContainerPtrToValuePtr<FAnimNode_ControlRig>(this);
	return Node ? Node->GetControlRig() : nullptr;
}

void UAirshipAnimInstance::WriteRigVariables(UControlRig* Rig)
{
	using namespace AirshipAnimPrivate;

	// The variables live in the rig's class (rig blueprint) or in a property bag (runtime rig asset) that the rig can
	// rebuild (InitializeVM after a recompile). Look the properties up again for a new rig instance or a new variable
	// struct, and take the memory fresh every update, so nothing points into a freed bag.
	if (Rig != CachedRig || Rig->GetUniqueID() != CachedRigUniqueId || Rig->GetVariablesStruct() != CachedVariablesStruct)
	{
		CachedRig = Rig;
		CachedRigUniqueId = Rig->GetUniqueID();
		RigSlots.SetNum(NumFloatVariables + 1);

		for (int32 Index = 0; Index <= NumFloatVariables; ++Index)
		{
			const FName Name = Index < NumFloatVariables ? FName(FloatVariables[Index].Name) : DeadVariableName;
			const FRigVMExternalVariable Variable = Rig->GetPublicVariableByName(Name);
			RigSlots[Index].Property = Variable.IsValid() && !Variable.IsArray() ? Variable.GetProperty() : nullptr;
		}

		// After the lookups (they can initialize the bag)
		CachedVariablesStruct = Rig->GetVariablesStruct();
	}

	uint8* Container = Rig->GetVariablesMemory();

	if (!Container)
	{
		return;
	}

	for (int32 Index = 0; Index < NumFloatVariables; ++Index)
	{
		const FProperty* Property = RigSlots[Index].Property;

		if (!Property)
		{
			continue;
		}

		const float Value = this->*(FloatVariables[Index].Member);
		void* Memory = Property->ContainerPtrToValuePtr<void>(Container);

		// The rig variables are 'float'; a 'double' one still works
		if (const FFloatProperty* FloatProperty = CastField<FFloatProperty>(Property))
		{
			FloatProperty->SetPropertyValue(Memory, Value);
		}
		else if (const FDoubleProperty* DoubleProperty = CastField<FDoubleProperty>(Property))
		{
			DoubleProperty->SetPropertyValue(Memory, static_cast<double>(Value));
		}
	}

	if (const FBoolProperty* BoolProperty = CastField<FBoolProperty>(RigSlots[DeadSlot].Property))
	{
		BoolProperty->SetPropertyValue(BoolProperty->ContainerPtrToValuePtr<void>(Container), bIsDead);
	}
}
