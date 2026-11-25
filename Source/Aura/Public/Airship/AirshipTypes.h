// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Engine/NetSerialization.h"
#include "NativeGameplayTags.h"
#include "AirshipTypes.generated.h"

class AActor;

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

	/**
	 * Gunner stations (EAirshipStation order): the four cannons (station = cannon index), then the two front turrets
	 * (TurretL, TurretR; turret index = station - FirstTurretStation). The helm is not a station: it stays the pilot's.
	 */
	constexpr int32 NumStations = 6;
	constexpr int32 NumTurrets = 2;
	constexpr int32 FirstTurretStation = 4;
	inline bool IsCannonStation(int32 Station) { return Station >= 0 && Station < NumCannons; }
	inline bool IsTurretStation(int32 Station) { return Station >= FirstTurretStation && Station < NumStations; }
	inline int32 StationToTurret(int32 Station) { return Station - FirstTurretStation; }
	inline int32 TurretToStation(int32 Turret) { return Turret + FirstTurretStation; }

	/** FAirshipPilotInput::Buttons bits. */
	constexpr uint8 Button_Boost = 1 << 0;
	constexpr uint8 Button_Brake = 1 << 1;
	constexpr uint8 Button_Aim = 1 << 2;
	constexpr uint8 Button_HasAimPoint = 1 << 3;

	/** Galleon: broadside stations (level gun deck, fine helm). Only read while the ship's scheme is Galleon. */
	constexpr uint8 Button_Stations = 1 << 4;

	/** The pilot holds Fire with the camera in the bow arc: the unmanned turrets fire at AimPoint (every scheme). */
	constexpr uint8 Button_FireHeld = 1 << 5;

	/**
	 * Server -> every machine (in the neutral input of an unpiloted ship): the ship is drifting, so Galleon's STOP order
	 * doesn't reverse the engines on any machine's cosmetics.
	 */
	constexpr uint8 Button_Drift = 1 << 6;

	/**
	 * The pilot's machine: the pilot is driving this frame (round 2 PR B, SPEC_B B2.5 item 9). Point & Fly: a drive /
	 * sidestep / turn / boost key, or the camera steering (out of its parked free look); the other schemes: any drive
	 * axis or button. The server can't tell Point & Fly's Q/E from the heading target alone, so the pilot says it. Read
	 * only by the lane assist of team ships (UAirshipFlightComponent::HasPilotDriveInput); free ships ignore it.
	 */
	constexpr uint8 Button_DriveIntent = 1 << 7;
}

/** Native gameplay tags of the airship module (defined in AirshipPawn.cpp). */
namespace AirshipTags
{
	/**
	 * Loose tag on a team ship's ASC and its turrets' (server) while it is spawn protected (SPEC_B B3.4):
	 * UMyAttributeSet drops IncomingDamage on an ASC that has it. "Airship.State.SpawnProtected".
	 */
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(State_SpawnProtected)
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

/** A gunner station on the ship (Airship::NumStations of them; the index is the station number). */
UENUM(BlueprintType)
enum class EAirshipStation : uint8
{
	CannonL1 = 0,
	CannonL2 = 1,
	CannonR1 = 2,
	CannonR2 = 3,
	TurretL = 4,
	TurretR = 5,
	None = 255 UMETA(Hidden)
};

/** What a ship does while nobody flies it (server, UAirshipFlightComponent). Keep the values (telemetry, harnesses). */
UENUM(BlueprintType)
enum class EAirshipUnpilotedMode : uint8
{
	/** Piloted, debug input active, flight off or dead. */
	None = 0,
	/** Unpiloted and too fast to hold, no drift asked for: the old coast (station keeping as before). */
	Coast = 1,
	/** Keeps going slowly ahead along its heading after a moving exit. */
	Drift = 2,
	/** Holds a point and a heading (parked). */
	Hold = 3,
	/**
	 * A team ship on its lane (round 2 PR B, UAirshipLaneComponent sets the target every frame): the hold law on a moving
	 * point with the drag and the target's acceleration fed forward, and the lane's height. Also with a pilot at the helm
	 * whose drive keys are untouched (lane assist): he aims and fires, the lane flies.
	 */
	Lane = 4
};

/** Why the server refused a player's F (UAirshipPilotComponent::ClientUseRefused, the HUD's toast). */
UENUM(BlueprintType)
enum class EAirshipUseRefusal : uint8
{
	None,
	/** No free helm or gun station in range. */
	NothingInRange,
	/** The helm or a station in range belongs to the other team's ship. */
	EnemyShip
};

/** A turret mount in hull space (cm), its yaw limits (deg about hull +Z, 0 = bow, + = toward starboard) and pitch limits. */
USTRUCT(BlueprintType)
struct AURA_API FAirshipTurretMount
{
	GENERATED_BODY()

	/** Yaw axis on the deck top (hull space, cm). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship")
	FVector Location = FVector::ZeroVector;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship", meta = (ClampMin = "-180.0", ClampMax = "180.0"))
	float YawMinDeg = -30.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship", meta = (ClampMin = "-180.0", ClampMax = "180.0"))
	float YawMaxDeg = 30.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship", meta = (ClampMin = "-89.0", ClampMax = "89.0"))
	float PitchMinDeg = -20.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship", meta = (ClampMin = "-89.0", ClampMax = "89.0"))
	float PitchMaxDeg = 40.f;
};

/** One turret bullet as the tracers see it: it flies from the drawing machine's own muzzle to End. */
USTRUCT()
struct AURA_API FAirshipTurretShot
{
	GENERATED_BODY()

	UPROPERTY()
	FVector_NetQuantize End = FVector::ZeroVector;

	/** The bullet hit something (else End is the end of its range). */
	UPROPERTY()
	bool bImpact = false;
};

/** What a turret aims at and whether it fires (not replicated: the server's comes from the ship, a client's is cosmetic). */
struct FAirshipTurretCommand
{
	/** World, cm. */
	FVector AimPoint = FVector::ZeroVector;
	bool bHasAim = false;
	bool bTrigger = false;
	/** Who the damage is credited to: the gunner, or the ship for the driver and the console. */
	TWeakObjectPtr<AActor> Instigator;
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
	bool IsFireHeld() const { return HasButton(Airship::Button_FireHeld); }

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

	// ---- Unpiloted ship (UAirshipFlightComponent, server values; 0 / false on clients).

	/** EAirshipUnpilotedMode. */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	uint8 UnpilotedMode = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	bool bUnpilotedDrift = false;

	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	bool bUnpilotedHold = false;

	/** Drift target speed along the held heading (m/s). */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	float DriftTargetSpeedMS = 0.f;

	/** Horizontal distance from the centre of mass to the hold point (m). */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	float HoldOffsetM = 0.f;

	// ---- Gunner stations and turrets (AAirshipPawn, every machine).

	/** Bit s = station s (EAirshipStation) manned. */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	int32 StationMask = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	int32 NumGunners = 0;

	/** 0..1 per turret (L, R). */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	TArray<float> TurretHeat;

	/** Health per turret (L, R). */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	TArray<float> TurretHealth;

	/** Bit t = turret t destroyed. */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	int32 TurretDestroyedMask = 0;

	/** AAirshipTurret::GetShotCount per turret on this machine (server: fired; clients: drawn). */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	TArray<int32> TurretShots;

	/** The pilot character's Health, -1 without a pilot. */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	float PilotHealth = -1.f;

	/** Bit c = cannon c loaded on this machine's clock. */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	int32 CannonReadyMask = 0;

	// ---- Team match (round 2 PR B, every machine from the replicated team, lane state and lane hint unless noted).

	/** The ship's team: 0, 1, or 255 (a free ship, or no match). */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	uint8 TeamId = 255;

	/** EMyLaneState (NoLane on free ships). */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	uint8 LaneState = 0;

	/** The ship's progress u along the start heading (m), from the lane hint. */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	float LaneUM = 0.f;

	/** Ship minus its lane (m): sideways in the start-heading frame (+ = right) and up. */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	float LaneLateralErrorM = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	float LaneVerticalErrorM = 0.f;

	/** The lane tangent's world yaw at the ship (deg), from the lane hint. */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	float LaneYawDeg = 0.f;

	/** The lane target's speed (m/s), server only (0 on clients and outside Lane mode). */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	float LaneTargetSpeedMS = 0.f;

	/** EMyLaneClamp: what limits the lane target. */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	uint8 LaneClamp = 0;

	/** The unpiloted mode is Lane this frame (server). */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	bool bUnpilotedLane = false;

	/** Lane assist this frame: a pilot at the helm, the lane flies (server: the flight model's; clients: the lane state). */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	bool bLaneAssist = false;

	/** Seconds until the ship flies itself back to its lane (the recall timer, B2.11); 0 = none. */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	float RecallInS = 0.f;

	/** Spawn protection (B3.4): seconds left, 0 = not protected. */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	float ProtectionLeftS = 0.f;

	/** Someone reels in toward the ship with the ship hook (server; the lane holds its speed, B7.4). */
	UPROPERTY(BlueprintReadOnly, Category = "Airship")
	bool bIncomingReel = false;
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
