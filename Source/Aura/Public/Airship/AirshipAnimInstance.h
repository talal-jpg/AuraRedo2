// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Animation/AnimInstance.h"
#include "Airship/AirshipTypes.h"
#include "AirshipAnimInstance.generated.h"

class AAirshipPawn;
class FProperty;
class FStructProperty;
class UControlRig;

/**
 * Parent class of ABP_Airship. Works out, on every machine, the values of CR_Airship's rig variables
 * (Docs/Airship/RIG_CONTRACT.md section 5) and writes them straight into the Control Rig node's rig instance, so the
 * AnimBP needs no "Use Pin" wiring and a rebuilt rig keeps working.
 *
 * NativeUpdateAnimation (game thread) copies what it needs from the AAirshipPawn (cosmetic flight state, cannon aim,
 * shot counters, death); NativeThreadSafeUpdateAnimation integrates from those copies only (springs, spins, slew
 * limits) and writes the rig variables. The same values are public BlueprintReadOnly properties of the same names, so
 * the Burrower's "Use Pin" path works as a fallback (expose a pin only if it is wired to the property: an unwired
 * exposed pin overwrites the C++ value every update).
 *
 * In the editor preview (no ship) everything idles: rotors at idle speed, searchlights panning.
 * Units: degrees, cm, seconds since death.
 */
UCLASS()
class AURA_API UAirshipAnimInstance : public UAnimInstance
{
	GENERATED_BODY()

public:

	virtual void NativeInitializeAnimation() override;

	virtual void NativeUpdateAnimation(float DeltaSeconds) override;

	virtual void NativeThreadSafeUpdateAnimation(float DeltaSeconds) override;


	// -------------------------------------------------------------------------
	// Rig variables (names = CR_Airship variables)
	// -------------------------------------------------------------------------

	/** Nozzle about hull +Y (deg, +-5): + swings the exit aft (thrust pushes forward). */
	UPROPERTY(Transient, BlueprintReadOnly, Category = "Airship|Rig")
	float NozzlePitchDeg_FL = 0.f;

	UPROPERTY(Transient, BlueprintReadOnly, Category = "Airship|Rig")
	float NozzlePitchDeg_FR = 0.f;

	UPROPERTY(Transient, BlueprintReadOnly, Category = "Airship|Rig")
	float NozzlePitchDeg_RL = 0.f;

	UPROPERTY(Transient, BlueprintReadOnly, Category = "Airship|Rig")
	float NozzlePitchDeg_RR = 0.f;

	/** Nozzle about hull +X (deg, +-5): + swings the exit toward +Y (thrust pushes left). */
	UPROPERTY(Transient, BlueprintReadOnly, Category = "Airship|Rig")
	float NozzleRollDeg_FL = 0.f;

	UPROPERTY(Transient, BlueprintReadOnly, Category = "Airship|Rig")
	float NozzleRollDeg_FR = 0.f;

	UPROPERTY(Transient, BlueprintReadOnly, Category = "Airship|Rig")
	float NozzleRollDeg_RL = 0.f;

	UPROPERTY(Transient, BlueprintReadOnly, Category = "Airship|Rig")
	float NozzleRollDeg_RR = 0.f;

	/** Petal flare (deg, -10..35), + = open. */
	UPROPERTY(Transient, BlueprintReadOnly, Category = "Airship|Rig")
	float NozzleFlareDeg_FL = 0.f;

	UPROPERTY(Transient, BlueprintReadOnly, Category = "Airship|Rig")
	float NozzleFlareDeg_FR = 0.f;

	UPROPERTY(Transient, BlueprintReadOnly, Category = "Airship|Rig")
	float NozzleFlareDeg_RL = 0.f;

	UPROPERTY(Transient, BlueprintReadOnly, Category = "Airship|Rig")
	float NozzleFlareDeg_RR = 0.f;

	/** Thrust level (0..1.5, 1 = hover). */
	UPROPERTY(Transient, BlueprintReadOnly, Category = "Airship|Rig")
	float ThrustAlpha_FL = 0.f;

	UPROPERTY(Transient, BlueprintReadOnly, Category = "Airship|Rig")
	float ThrustAlpha_FR = 0.f;

	UPROPERTY(Transient, BlueprintReadOnly, Category = "Airship|Rig")
	float ThrustAlpha_RL = 0.f;

	UPROPERTY(Transient, BlueprintReadOnly, Category = "Airship|Rig")
	float ThrustAlpha_RR = 0.f;

	/** Fan housing about hull +Z (deg, +-12): + turns the fan axis from +X toward +Y. */
	UPROPERTY(Transient, BlueprintReadOnly, Category = "Airship|Rig")
	float TurbineYawDeg_L = 0.f;

	UPROPERTY(Transient, BlueprintReadOnly, Category = "Airship|Rig")
	float TurbineYawDeg_R = 0.f;

	/** Rotor spin angle (deg, [0, 360)). */
	UPROPERTY(Transient, BlueprintReadOnly, Category = "Airship|Rig")
	float RotorAngleDeg_L = 0.f;

	UPROPERTY(Transient, BlueprintReadOnly, Category = "Airship|Rig")
	float RotorAngleDeg_R = 0.f;

	/** Rudder about its hinge, hull +Z (deg, +-30): + swings the trailing edge toward -Y (port), so a right turn is negative. */
	UPROPERTY(Transient, BlueprintReadOnly, Category = "Airship|Rig")
	float RudderDeg = 0.f;

	/** Helm wheel angle about its axle, hull +X (deg, unbounded): a right turn (clockwise seen from the pilot) is negative. */
	UPROPERTY(Transient, BlueprintReadOnly, Category = "Airship|Rig")
	float WheelAngleDeg = 0.f;

	/** Cannon yaw about hull +Z (deg, +-20). L1, L2, R1, R2. */
	UPROPERTY(Transient, BlueprintReadOnly, Category = "Airship|Rig")
	float CannonYawDeg_L1 = 0.f;

	UPROPERTY(Transient, BlueprintReadOnly, Category = "Airship|Rig")
	float CannonYawDeg_L2 = 0.f;

	UPROPERTY(Transient, BlueprintReadOnly, Category = "Airship|Rig")
	float CannonYawDeg_R1 = 0.f;

	UPROPERTY(Transient, BlueprintReadOnly, Category = "Airship|Rig")
	float CannonYawDeg_R2 = 0.f;

	/** Cannon elevation (deg, -10..9): + raises the muzzle. */
	UPROPERTY(Transient, BlueprintReadOnly, Category = "Airship|Rig")
	float CannonElevDeg_L1 = 0.f;

	UPROPERTY(Transient, BlueprintReadOnly, Category = "Airship|Rig")
	float CannonElevDeg_L2 = 0.f;

	UPROPERTY(Transient, BlueprintReadOnly, Category = "Airship|Rig")
	float CannonElevDeg_R1 = 0.f;

	UPROPERTY(Transient, BlueprintReadOnly, Category = "Airship|Rig")
	float CannonElevDeg_R2 = 0.f;

	/** Recoil slide back along -aim (cm, 0..60). */
	UPROPERTY(Transient, BlueprintReadOnly, Category = "Airship|Rig")
	float CannonRecoilCm_L1 = 0.f;

	UPROPERTY(Transient, BlueprintReadOnly, Category = "Airship|Rig")
	float CannonRecoilCm_L2 = 0.f;

	UPROPERTY(Transient, BlueprintReadOnly, Category = "Airship|Rig")
	float CannonRecoilCm_R1 = 0.f;

	UPROPERTY(Transient, BlueprintReadOnly, Category = "Airship|Rig")
	float CannonRecoilCm_R2 = 0.f;

	/** Shared slow pan of the 4 searchlight heads (deg). */
	UPROPERTY(Transient, BlueprintReadOnly, Category = "Airship|Rig")
	float SearchLightPanDeg = 0.f;

	/** Death switch: Fx solver off, wreck solver on. */
	UPROPERTY(Transient, BlueprintReadOnly, Category = "Airship|Rig")
	bool bIsDead = false;

	/** Seconds since death (the ship's world time since the server's death, also for late joiners), 0 alive. */
	UPROPERTY(Transient, BlueprintReadOnly, Category = "Airship|Rig")
	float DeathTime = 0.f;


	// -------------------------------------------------------------------------
	// Feed
	// -------------------------------------------------------------------------

	/** Write the values into the Control Rig node's rig instance every update. Off: only the properties (Use Pin). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Rig Feed")
	bool bWriteRigVariables = true;


	// -------------------------------------------------------------------------
	// Thrusters
	// -------------------------------------------------------------------------

	/** Nozzle pitch / roll limit (deg) and how fast they follow (1/s). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Thrusters", meta = (ClampMin = "0.0", ClampMax = "30.0"))
	float NozzleMaxDeg = 5.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Thrusters", meta = (ClampMin = "0.0"))
	float NozzleInterpSpeed = 8.f;

	/** Petal flare (deg): FlareAtHoverDeg at thrust 1, + FlarePerThrust per unit above, clamped to FlareMinDeg..FlareMaxDeg. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Thrusters")
	float FlareAtHoverDeg = 6.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Thrusters")
	float FlarePerThrust = 40.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Thrusters")
	float FlareMinDeg = -10.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Thrusters")
	float FlareMaxDeg = 35.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Thrusters", meta = (ClampMin = "0.0"))
	float FlareInterpSpeed = 6.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Thrusters", meta = (ClampMin = "0.0"))
	float ThrustAlphaInterpSpeed = 6.f;


	// -------------------------------------------------------------------------
	// Turbines (rear fans)
	// -------------------------------------------------------------------------

	/** Housing yaw limit (deg) and slew rate (deg/s). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Turbines", meta = (ClampMin = "0.0", ClampMax = "45.0"))
	float TurbineYawMaxDeg = 12.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Turbines", meta = (ClampMin = "0.0"))
	float TurbineYawSlewDegPerSec = 40.f;

	/** Rotor spin (deg/s): idle + per unit fan thrust (signed: reverse thrust spins backward), x RotorBoostMultiplier at full boost. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Turbines", meta = (ClampMin = "0.0"))
	float RotorIdleDegPerSec = 300.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Turbines", meta = (ClampMin = "0.0"))
	float RotorMaxDegPerSec = 1500.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Turbines", meta = (ClampMin = "1.0"))
	float RotorBoostMultiplier = 2.f;

	/** Rotor spin change (deg/s per s) alive, and the spin-down after death. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Turbines", meta = (ClampMin = "0.0"))
	float RotorSpinAcceleration = 1500.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Turbines", meta = (ClampMin = "0.0"))
	float RotorSpinDownRate = 250.f;


	// -------------------------------------------------------------------------
	// Rudder and helm
	// -------------------------------------------------------------------------

	/** Rudder angle per unit steer (deg; negative: D swings the trailing edge to starboard, RIG_CONTRACT 5), its limit, follow speed (1/s). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Helm")
	float RudderDegPerSteer = -25.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Helm", meta = (ClampMin = "0.0", ClampMax = "90.0"))
	float RudderMaxDeg = 30.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Helm", meta = (ClampMin = "0.0"))
	float RudderInterpSpeed = 6.f;

	/** Wheel turn per unit steer (deg; negative: D turns it clockwise as the pilot sees it, RIG_CONTRACT 5). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Helm")
	float WheelDegPerSteer = -270.f;

	/** Wheel spring: natural frequency (rad/s) and damping ratio (< 1 overshoots). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Helm", meta = (ClampMin = "0.1"))
	float WheelSpringOmega = 6.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Helm", meta = (ClampMin = "0.0", ClampMax = "2.0"))
	float WheelSpringDamping = 0.4f;

	/** Death: the wheel gets this spin (deg/s) and spins down freely (1/s). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Helm")
	float WheelDeathSpinDegPerSec = 540.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Helm", meta = (ClampMin = "0.0"))
	float WheelDeathSpinDecay = 0.5f;


	// -------------------------------------------------------------------------
	// Cannons
	// -------------------------------------------------------------------------

	/** Aim limits (deg) and slew rate (deg/s). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Cannons", meta = (ClampMin = "0.0", ClampMax = "90.0"))
	float CannonYawLimitDeg = 20.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Cannons", meta = (ClampMin = "-90.0", ClampMax = "0.0"))
	float CannonElevMinDeg = -10.f;

	/**
	 * The barrel meets its own carriage at 8.75 (README_rig.md ranges); 8.5 leaves room for the barrel drive's overshoot.
	 * Keep it equal to the pawn's.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Cannons", meta = (ClampMin = "0.0", ClampMax = "90.0"))
	float CannonElevMaxDeg = 8.5f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Cannons", meta = (ClampMin = "0.0"))
	float CannonAimSlewDegPerSec = 45.f;

	/**
	 * Elevation eases into its target (1/s): the slew is min(CannonAimSlewDegPerSec, error * rate), so the barrel's
	 * physics drive is not stopped dead at 45 deg/s (that overshot 0.57 deg into the carriage). 0 = constant slew.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Cannons", meta = (ClampMin = "0.0"))
	float CannonElevSettleRate = 8.f;

	/** Recoil (cm, rig 0..60): out in CannonRecoilAttackTime (s), eased back over CannonRecoilReturnTime (s). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Cannons", meta = (ClampMin = "0.0", ClampMax = "60.0"))
	float CannonRecoilMaxCm = 45.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Cannons", meta = (ClampMin = "0.001"))
	float CannonRecoilAttackTime = 0.06f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Cannons", meta = (ClampMin = "0.001"))
	float CannonRecoilReturnTime = 0.5f;


	// -------------------------------------------------------------------------
	// Searchlights
	// -------------------------------------------------------------------------

	/** Pan amplitude (deg) and frequency (Hz) of the shared searchlight sweep. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Searchlights", meta = (ClampMin = "0.0"))
	float SearchLightPanAmplitudeDeg = 30.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Searchlights", meta = (ClampMin = "0.0"))
	float SearchLightPanFrequency = 0.05f;

private:

	/** Copied on the game thread (NativeUpdateAnimation), read by the thread-safe update. */
	struct FInputs
	{
		bool bHasShip = false;
		bool bDead = false;
		float DeathTime = 0.f;
		FAirshipCosmeticState Cosmetic;
		float CannonAimYawDeg[Airship::NumCannons] = {};
		float CannonAimElevDeg[Airship::NumCannons] = {};
		int32 CannonFireCount[Airship::NumCannons] = {};
	};

	/** One rig variable: its property in the current rig's variable struct (the memory is read every update). */
	struct FRigVariableSlot
	{
		const FProperty* Property = nullptr;
	};

	/** Finds the Control Rig node's rig instance (the first Control Rig node of the AnimGraph). */
	UControlRig* FindControlRig();

	/** Writes every rig variable into Rig (properties cached per rig instance and variable struct). */
	void WriteRigVariables(UControlRig* Rig);

	UPROPERTY(Transient)
	TObjectPtr<AAirshipPawn> Ship;

	FInputs Inputs;

	// Integrator state (thread-safe update)
	float NozzlePitch[Airship::NumPods] = {};
	float NozzleRoll[Airship::NumPods] = {};
	float NozzleFlare[Airship::NumPods] = {};
	float ThrustAlpha[Airship::NumPods] = {};
	float TurbineYaw[Airship::NumFans] = {};
	float RotorAngle[Airship::NumFans] = {};
	float RotorSpeed[Airship::NumFans] = {};
	float CannonYaw[Airship::NumCannons] = {};
	float CannonElev[Airship::NumCannons] = {};
	float RecoilTime[Airship::NumCannons] = { 1000.f, 1000.f, 1000.f, 1000.f };
	int32 SeenFireCount[Airship::NumCannons] = {};
	bool bFireCountsSeeded = false;
	float WheelVelocity = 0.f;
	float SearchLightTime = 0.f;
	bool bRotorsStarted = false;

	// Rig variable cache
	const FStructProperty* ControlRigNodeProperty = nullptr;
	bool bSearchedControlRigNode = false;
	UControlRig* CachedRig = nullptr;
	uint32 CachedRigUniqueId = 0;
	const UStruct* CachedVariablesStruct = nullptr;
	TArray<FRigVariableSlot> RigSlots;
};
