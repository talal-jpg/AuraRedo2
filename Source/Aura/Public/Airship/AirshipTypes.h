// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Engine/NetSerialization.h"
#include "AirshipTypes.generated.h"

/**
 * Fixed part counts and orders shared by the pawn, the flight model and the anim instance (Docs/Airship/RIG_CONTRACT.md).
 * Pods: FL, FR, RL, RR. Fans (turbines): L, R. Cannons: L1 (forward port), L2 (aft port), R1, R2.
 * L = port = Unreal -Y, R = starboard = Unreal +Y.
 */
namespace Airship
{
	constexpr int32 NumPods = 4;
	constexpr int32 NumFans = 2;
	constexpr int32 NumCannons = 4;

	/** Pods at the front (FL, FR) and on the left (FL, RL). */
	inline bool IsFrontPod(int32 Pod) { return Pod < 2; }
	inline bool IsLeftPod(int32 Pod) { return Pod == 0 || Pod == 2; }

	/** Cannons L1, L2 are on the port side. */
	inline bool IsPortCannon(int32 Cannon) { return Cannon < 2; }

	/** FAirshipPilotInput::Buttons bits. */
	constexpr uint8 Button_Boost = 1 << 0;
	constexpr uint8 Button_Brake = 1 << 1;
	constexpr uint8 Button_Aim = 1 << 2;
	constexpr uint8 Button_HasAimPoint = 1 << 3;
}

/** Broadside: the two cannons on one side. */
UENUM(BlueprintType)
enum class EAirshipSide : uint8
{
	/** Left (L1, L2), Unreal -Y. */
	Port,
	/** Right (R1, R2), Unreal +Y. */
	Starboard
};

/**
 * The pilot's controls. The owning client sends them to the server (unreliable RPC with a sequence number), the
 * server replicates them to everyone else (cosmetics). Axes are -1..1 quantized to int8.
 */
USTRUCT(BlueprintType)
struct AURA_API FAirshipPilotInput
{
	GENERATED_BODY()

	UPROPERTY()
	int8 Throttle = 0;

	UPROPERTY()
	int8 Steer = 0;

	UPROPERTY()
	int8 Lift = 0;

	UPROPERTY()
	int8 Strafe = 0;

	UPROPERTY()
	uint8 Buttons = 0;

	/** Wraps at 255. The server drops packets older than the last one it used. */
	UPROPERTY()
	uint8 Seq = 0;

	/** Where the pilot's camera looks (world, cm): the cannons aim there. Valid with Airship::Button_HasAimPoint. */
	UPROPERTY()
	FVector_NetQuantize AimPoint = FVector::ZeroVector;

	static int8 QuantizeAxis(float Value)
	{
		return static_cast<int8>(FMath::RoundToInt(FMath::Clamp(Value, -1.f, 1.f) * 127.f));
	}

	static float AxisToFloat(int8 Value)
	{
		return FMath::Clamp(static_cast<float>(Value) / 127.f, -1.f, 1.f);
	}

	float GetThrottle() const { return AxisToFloat(Throttle); }
	float GetSteer() const { return AxisToFloat(Steer); }
	float GetLift() const { return AxisToFloat(Lift); }
	float GetStrafe() const { return AxisToFloat(Strafe); }

	bool HasButton(uint8 Button) const { return (Buttons & Button) != 0; }
	void SetButton(uint8 Button, bool bOn) { Buttons = bOn ? (Buttons | Button) : (Buttons & ~Button); }

	bool IsBoost() const { return HasButton(Airship::Button_Boost); }
	bool IsBrake() const { return HasButton(Airship::Button_Brake); }
	bool IsAiming() const { return HasButton(Airship::Button_Aim); }
	bool HasAimPoint() const { return HasButton(Airship::Button_HasAimPoint); }

	/** Same controls (ignores Seq and the aim point). */
	bool SameControls(const FAirshipPilotInput& Other) const
	{
		return Throttle == Other.Throttle && Steer == Other.Steer && Lift == Other.Lift && Strafe == Other.Strafe && Buttons == Other.Buttons;
	}
};

/** Measured flight state for test harnesses and UI. Speeds in m/s, angles in degrees. */
USTRUCT(BlueprintType)
struct AURA_API FAirshipFlightTelemetry
{
	GENERATED_BODY()

	/** |velocity| (m/s). */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	float SpeedMS = 0.f;

	/** Velocity along the ship's forward axis (m/s, + = forward). */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	float ForwardSpeedMS = 0.f;

	/** Velocity along the ship's right axis (m/s, + = right). */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	float LateralSpeedMS = 0.f;

	/** World Z of the actor (m). */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	float AltitudeM = 0.f;

	/** Lowest ground distance under the four nozzle exits (m), -1 when nothing is below (server only, -1 on clients). */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	float GroundClearanceM = -1.f;

	/** World vertical speed (m/s, + = up). */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	float VerticalSpeedMS = 0.f;

	/** Turn rate about world Z (deg/s, + = turning right). */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	float YawRateDegS = 0.f;

	/** + = right side down. */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	float RollDeg = 0.f;

	/** + = nose up. */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	float PitchDeg = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	float YawDeg = 0.f;

	/** Altitude the hold loop keeps (m), server only. */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	float HoldAltitudeM = 0.f;

	/** 0..BoostFuelMax (replicated). */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	float BoostFuel = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	float Health = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	float MaxHealth = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	float MassKg = 0.f;

	/** Shaped controls used this frame (-1..1, boost 0..1). */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	float Throttle = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	float Steer = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	float Lift = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	float Strafe = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	float Boost = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	bool bBraking = false;

	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	bool bDrifting = false;

	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	bool bHasPilot = false;

	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	bool bIsDead = false;
};

/**
 * Cosmetic outputs of the flight model, worked out on every machine from the shaped controls (the server uses the same
 * gimbal and fan yaw values for the forces). Read by UAirshipAnimInstance and the Niagara update.
 */
struct FAirshipCosmeticState
{
	float Throttle = 0.f;
	float Steer = 0.f;
	float Lift = 0.f;
	float Strafe = 0.f;
	float Boost = 0.f;
	bool bBrake = false;
	bool bAiming = false;

	/** Thrust lean (deg): + pitch = thrust leans forward, + roll = thrust leans right (Unreal +Y). */
	float PodGimbalPitchDeg[Airship::NumPods] = {};
	float PodGimbalRollDeg[Airship::NumPods] = {};

	/** Thrust level per pod, 1 = hover share, 0..1.5. */
	float PodThrustAlpha[Airship::NumPods] = {};

	/** Fan housing yaw (deg), + turns the fan axis from +X toward +Y. Same for both fans. */
	float FanYawDeg = 0.f;

	/** Signed fan thrust per fan (L, R), -1..1 of the fan's maximum (negative = reverse). */
	float FanThrust[Airship::NumFans] = {};

	/** Forward speed (cm/s) and |velocity| (cm/s). */
	float ForwardSpeed = 0.f;
	float Speed = 0.f;
};
