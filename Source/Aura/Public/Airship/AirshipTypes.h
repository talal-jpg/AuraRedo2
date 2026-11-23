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

	/** Galleon: broadside stations (level gun deck, fine helm). Only read while the ship's scheme is Galleon. */
	constexpr uint8 Button_Stations = 1 << 4;
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
 * How the pilot's keys and camera fly the ship (Docs/Airship/controls/, CPP_NOTES.md "Control schemes"). The pawn owns
 * the replicated choice (AAirshipPawn::ControlScheme); every machine applies the same compiled-in preset for it.
 */
UENUM(BlueprintType)
enum class EAirshipControlScheme : uint8
{
	/** v1 as shipped: W/S throttle pedal, A/D turn, X brake (+ A/D = drift). */
	Classic = 0 UMETA(DisplayName = "Classic (v1)"),
	/** Engine-order telegraph on W/S, heavy heel, stern swing, broadside stations, ship-relative camera. */
	Galleon = 1,
	/** Hard acceleration, planted turn, drift with a three-tier mini-turbo, boost burst, chase camera. */
	SkyRacer = 2 UMETA(DisplayName = "Sky Racer"),
	/** The camera yaw is the heading target, A/D sidestep, Q/E turn, Aim = free look and gun lock. The pawn's default. */
	PointFly = 3 UMETA(DisplayName = "Point & Fly")
};

/**
 * The pilot's controls. The owning client sends them to the server (unreliable RPC with a sequence number), the
 * server replicates them to everyone else (cosmetics). Axes are -1..1 quantized to int8.
 */
USTRUCT(BlueprintType)
struct AURA_API FAirshipPilotInput
{
	GENERATED_BODY()

	/** Galleon: the engine order code (AirshipGalleon::NotchToThrottle), a latched state. */
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

	/**
	 * Point & Fly heading target (world yaw): 1..65534 = 1 + round(yaw mod 360 / 360 * 65534) % 65534; 0 = none, so a
	 * neutral input never means "head to yaw 0". Not in SameControls (camera driven: it rides the InputSendRate
	 * heartbeat like AimPoint).
	 */
	UPROPERTY()
	uint16 HeadingTarget = 0;

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

	/** Same controls (ignores Seq, the aim point and the heading target). */
	bool SameControls(const FAirshipPilotInput& Other) const
	{
		return Throttle == Other.Throttle && Steer == Other.Steer && Lift == Other.Lift && Strafe == Other.Strafe && Buttons == Other.Buttons;
	}

	static uint16 EncodeHeading(float YawDeg)
	{
		float Wrapped = FMath::Fmod(YawDeg, 360.f);

		if (Wrapped < 0.f)
		{
			Wrapped += 360.f;
		}
		return static_cast<uint16>(1 + FMath::RoundToInt(Wrapped / 360.f * 65534.f) % 65534);
	}

	bool HasHeadingTarget() const { return HeadingTarget != 0; }

	/** The heading target as a world yaw (-180..180); 0 without one. */
	float GetHeadingTargetDeg() const
	{
		return HeadingTarget != 0 ? static_cast<float>(FRotator::NormalizeAxis(static_cast<double>(HeadingTarget - 1) * (360.0 / 65534.0))) : 0.f;
	}
};

/** Point & Fly heading loop state (UAirshipFlightComponent::ComputeHeadingSteer): one on the server, one on the pilot's machine. */
struct FPointFlyLoopState
{
	/** A brake-drift is running (hysteresis on the turn still to come). */
	bool bDrift = false;
};

/**
 * Galleon's engine-order telegraph. The order rides FAirshipPilotInput::Throttle as a code that every machine decodes
 * the same way. Notches: -1 FULL ASTERN, 0 STOP, 1 SLOW, 2 HALF, 3 FULL.
 */
namespace AirshipGalleon
{
	constexpr int32 Astern = -1;
	constexpr int32 Stop = 0;
	constexpr int32 Slow = 1;
	constexpr int32 Half = 2;
	constexpr int32 Full = 3;

	/** -127, 0, 42, 85, 127. */
	inline int8 NotchToThrottle(int32 Notch)
	{
		return Notch < 0 ? static_cast<int8>(-127) : static_cast<int8>(FMath::RoundToInt(127.f * static_cast<float>(FMath::Clamp(Notch, 0, 3)) / 3.f));
	}

	inline int32 ThrottleToNotch(int8 Throttle)
	{
		const float Value = FAirshipPilotInput::AxisToFloat(Throttle);
		return Value <= -0.5f ? Astern : FMath::RoundToInt(FMath::Clamp(Value, 0.f, 1.f) * 3.f);
	}

	/** Telemetry ThrottleOrder: -1, 0, 1/3, 2/3, 1. */
	inline float NotchToOrderValue(int32 Notch)
	{
		return Notch < 0 ? -1.f : static_cast<float>(Notch) / 3.f;
	}

	inline const TCHAR* NotchName(int32 Notch)
	{
		static const TCHAR* Names[] = { TEXT("ASTERN"), TEXT("STOP"), TEXT("SLOW"), TEXT("HALF"), TEXT("FULL") };
		return Names[FMath::Clamp(Notch, -1, 3) + 1];
	}
}

/**
 * Pilot-side feedback of one event (AAirshipPawn::AddFeedback): camera trauma, FOV punch and gamepad rumble. All zero
 * = nothing (Classic).
 */
USTRUCT(BlueprintType)
struct AURA_API FAirshipFeedbackEvent
{
	GENERATED_BODY()

	/** Camera trauma added (0..1; the shake grows with its square). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship")
	float Trauma = 0.f;

	/** FOV punch (deg), decays with AAirshipPawn::FOVKickDecay. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship")
	float FOVKickDeg = 0.f;

	/** Rumble intensity (0..1, times AAirshipPawn::RumbleScale) and length (s). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship")
	float Rumble = 0.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship")
	float RumbleTime = 0.f;

	/** Large motors (else small). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship")
	bool bRumbleLarge = true;
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

	// ---- Control schemes (CPP_NOTES.md "Control schemes"). Pilot-side values are valid on the pilot's machine and,
	// ---- where they reach the server through the input, on the server.

	/** EAirshipControlScheme the flight model runs (every machine). */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	uint8 Scheme = 0;

	/** Galleon engine order (-1 ASTERN, 0 STOP, 1/3 SLOW, 2/3 HALF, 1 FULL) on every machine; -2 in other schemes. */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	float ThrottleOrder = -2.f;

	/** Sky Racer drift charge 0..1 (every machine runs the drift); 0 in other schemes. */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	float DriftCharge = 0.f;

	/** Point & Fly: a heading target is set (pilot: its own; server and observers: the received one). */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	bool bHeadingTargetActive = false;

	/** Point & Fly heading target (world yaw, -180..180; pilot: the sent target with the lock lead); 0 otherwise. */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	float HeadingTargetDeg = 0.f;

	/**
	 * Point & Fly: broadside mode, Aim held (pilot: its own flag; server and observers: the Aim bit). False in steering
	 * mode and in the parked free look, whose camera is free too (AAirshipPawn::IsPFParked). True in the other schemes.
	 */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	bool bFreeLook = true;

	/** Drift direction -1 / 0 / +1 (Sky Racer: its drift; other schemes: the v1 drift / swing by the shaped steer). */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	int32 DriftDir = 0;

	/** Sky Racer: the tier the drift charge has reached (0..3, no grace); 0 otherwise. */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	int32 DriftTier = 0;

	/** Sky Racer: mini-turbo burn left (1 -> 0); 0 otherwise. */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	float TurboAlpha = 0.f;

	/** Sky Racer: chain links of the current / last drift (0..SkyChainMax); 0 otherwise. */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	int32 TurboChain = 0;

	/** The steady gun deck is on (Galleon: the stations bit; other schemes: Aim held). */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	bool bGunDeck = false;

	/** Point & Fly gun lock engaged (pilot's machine only); false otherwise. */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	bool bGunLock = false;
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

	/** The shaped drift on this machine (v1 drift, Galleon swing, Sky Racer drift) and the steady gun deck. */
	bool bDrifting = false;
	bool bGunDeck = false;

	/** Sky Racer: drift direction (-1, 0, +1), charge (0..1) and the tier it reached (no grace). */
	int8 DriftDir = 0;
	float DriftCharge = 0.f;
	uint8 DriftTier = 0;

	/** Sky Racer: mini-turbo burn left (1 -> 0), tier of the last release, live chain links, releases on this machine (wraps). */
	float TurboAlpha = 0.f;
	uint8 TurboTier = 0;
	uint8 TurboChain = 0;
	uint8 TurboEventCount = 0;

	/** Niagara Boost user parameter (v1: = Boost) and a floor for the fans' Thrust parameter (Sky Racer turbo burn). */
	float FXBoost = 0.f;
	float FXFanThrust = 0.f;
};
