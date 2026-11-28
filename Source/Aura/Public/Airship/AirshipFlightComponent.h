// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "Airship/AirshipTypes.h"
#include "AirshipFlightComponent.generated.h"

class AAirshipPawn;
class UPrimitiveComponent;
struct FHitResult;

/**
 * Server: what an unpiloted ship does this frame (UAirshipFlightComponent::UpdateUnpilotedMode). A team ship's lane
 * (round 2 PR B, UAirshipLaneComponent) fills the same target in Lane mode: a moving hold point with its own velocity
 * and acceleration, and a height.
 */
struct FAirshipUnpilotedTarget
{
	EAirshipUnpilotedMode Mode = EAirshipUnpilotedMode::None;
	/** Drift: target speed along HeadingYaw (cm/s). */
	float ForwardSpeed = 0.f;
	/** Drift / Hold / Lane: world yaw to hold (deg). */
	float HeadingYaw = 0.f;
	/** Hold / Lane: centre of mass target (world XY, cm). */
	FVector2D HoldPoint = FVector2D::ZeroVector;
	/** Hold / Lane: target velocity (cm/s), 0 when parked. */
	FVector2D HoldVelocity = FVector2D::ZeroVector;
	/** Lane: the altitude loop follows HoldZ (world Z of the hull origin, cm) at ClimbRate. */
	bool bHasHoldZ = false;
	float HoldZ = 0.f;
	/** Lane: how fast the held altitude follows HoldZ (cm/s); 0 = UMyMatchSettings::LaneClimbRate. A recall over the field sets its own. */
	float ClimbRate = 0.f;
	/** Lane: the target's own acceleration (cm/s^2), fed forward so the ship doesn't trail a ramping target. */
	FVector2D HoldAccel = FVector2D::ZeroVector;
};

/**
 * The airship's flight model (Docs/Airship/research_flight.md section 3). Lives on AAirshipPawn, which calls
 * UpdateFlight from its Tick (TG_PrePhysics) on every machine.
 *
 * Server: picks the controls (the pilot's RPC, the host's own input, or DebugSetInput), shapes them, and applies the
 * forces to the simulating hull: 4 thruster forces at the pods (vertical collective + roll/pitch, mixed over the 4
 * pods), 2 fan forces at the rear fans (forward thrust + differential yaw), and one COM force / one torque for the rest
 * (lateral grip, drag, air brake, rudder, a capped hidden gyro, wind). Every axis is an acceleration command, so
 * handling is the same for any mass.
 *
 * Every machine: shapes the controls it has (the pilot's machine its own input at once, the others the replicated
 * copy) through the same filters and writes the cosmetic state (gimbals, fan yaw, thrust levels) the anim instance and
 * the Niagara update read.
 *
 * Control schemes (CPP_NOTES.md section 14): ActiveScheme, the pawn's replicated ControlScheme set on every machine,
 * selects the Galleon / Sky Racer / Point & Fly branches of the shaping and the forces. Classic runs v1 line for line:
 * every base fix and shared mechanism below is off at its default.
 *
 * Units: cm, s, kg, degrees in properties (radians inside). Tune live with Aura.Airship.Set <Property> <Value>.
 */
UCLASS(ClassGroup = (Airship), meta = (BlueprintSpawnableComponent))
class AURA_API UAirshipFlightComponent : public UActorComponent
{
	GENERATED_BODY()

public:

	UAirshipFlightComponent();

	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	/** Every machine, from the pawn's Tick: controls, shaping, forces (server), cosmetic state. */
	void UpdateFlight(float DeltaSeconds);

	/** Mass, centre of mass, damping, speed caps, client gravity on the hull. BeginPlay, death and after Aura.Airship.Set. */
	void ApplyBodySettings();

	/** Reads the pod and fan positions from the mesh bones (rest pose), else the fallbacks below. */
	void RefreshActuatorLocations();

	/** The pilot's machine: its controls this frame. Applied at once on the host, sent to the server otherwise. */
	void SetLocalInput(const FAirshipPilotInput& Input);

	/** Server: the pilot changed or left; forget the last controls (the ship holds its altitude). */
	void ResetInput();

	/** Off after death: no flight forces, controls neutral, dead damping. */
	void SetFlightEnabled(bool bEnabled);

	bool IsFlightEnabled() const { return bFlightEnabled; }

	/**
	 * Overrides the controls on this machine until ClearDebugInput. On the pilot's machine they replace the keys and go
	 * their way (AAirshipPawn::GatherLocalInput -> SetLocalInput: at once on the host, ServerSetPilotInput from a client);
	 * on the server's copy of a ship that is piloted from a client or by nobody they fly it directly.
	 */
	void SetDebugInput(const FAirshipPilotInput& Input);
	void ClearDebugInput();
	bool HasDebugInput() const { return bDebugInputActive; }
	const FAirshipPilotInput& GetDebugInput() const { return DebugInput; }

	const FAirshipCosmeticState& GetCosmeticState() const { return Cosmetic; }

	/** The flight part of the telemetry (the pawn adds health). */
	void FillTelemetry(FAirshipFlightTelemetry& Out) const;

	/** The controls used this frame (raw, before shaping). */
	const FAirshipPilotInput& GetCurrentControls() const { return CurrentControls; }


	// -------------------------------------------------------------------------
	// Unpiloted ship (server, every scheme; knobs in UAirshipSettings "Unpiloted"). After a moving exit the ship drifts
	// slowly ahead on its heading until something is in the way, then holds; left at rest (or never piloted) it holds
	// its spot and heading. Gunners don't count as a pilot.
	// -------------------------------------------------------------------------

	/** Server: None while piloted (or debug input, flight off); Coast, Drift or Hold otherwise. Clients: None. */
	UFUNCTION(BlueprintPure, Category = "Airship|Flight")
	EAirshipUnpilotedMode GetUnpilotedMode() const { return UnpilotedTarget.Mode; }

	const FAirshipUnpilotedTarget& GetUnpilotedTarget() const { return UnpilotedTarget; }

	/** Server, the pilot's exit (AAirshipPawn::UnboardPilot, after the possession): the next evaluation drifts or parks. */
	void NotifyPilotLeft(const FVector& ExitVelocity);

	/** Server, every hull contact (AAirshipPawn::OnHullHit): a drift ends on a contact at the bow. */
	void NotifyHullContact(const AActor* Other, const FHitResult& Hit);

	/**
	 * Server, every frame before UpdateFlight (UAirshipLaneComponent, round 2 PR B): this frame's lane target (Mode is
	 * forced to Lane). It wins over drift / hold when flight is on, the ship is alive, no debug input is active, and
	 * there is no pilot or bAssist (lane assist: the pilot's aim and fire bits pass, his drive is cleared). A frame
	 * without a call leaves Lane through None (hold if slow, else coast; a drift asked for by an exit still starts).
	 */
	void SetLaneTarget(const FAirshipUnpilotedTarget& Target, bool bAssist);

	/** Server: the drift's distance limit (cm from the exit point) instead of UAirshipSettings::DriftMaxDistance; 0 = the setting's. */
	void SetDriftMaxDistanceOverride(float Distance) { DriftMaxDistanceOverride = FMath::Max(0.f, Distance); }

	float GetDriftMaxDistanceOverride() const { return DriftMaxDistanceOverride; }

	/**
	 * Server: the pilot drove this frame (the drive-intent bit, or a drive axis / button of the controls used:
	 * |axis| > 0.05, boost, brake, a Galleon order other than STOP). False without a pilot. The lane assist reads it.
	 */
	bool HasPilotDriveInput() const { return bPilotDriveInput; }

	/** Server: the lane target of this frame won and came with bAssist (the pilot's drive is cleared this frame). */
	bool IsLaneAssistActive() const { return bLaneAssistThisFrame; }

	/**
	 * Server: the hull's box (the drift look-ahead's, inset and lifted off the ground) swept Distance (cm) along the
	 * world yaw HeadingYaw. True if something the hull would bump into is in the way (the drift's rules: characters,
	 * cannonballs, pawns that aren't ships and the ship's own attachments don't count). OutHit: the first such hit.
	 */
	bool SweepHullAhead(float HeadingYaw, float Distance, FHitResult* OutHit) const;

	UFUNCTION(BlueprintPure, Category = "Airship|Flight")
	float GetBoostFuel() const { return BoostFuel; }

	/** Hull-local pod / fan positions used by the forces (cm). */
	FVector GetPodLocation(int32 Pod) const { return PodLocal[FMath::Clamp(Pod, 0, Airship::NumPods - 1)]; }
	FVector GetFanLocation(int32 Fan) const { return FanLocal[FMath::Clamp(Fan, 0, Airship::NumFans - 1)]; }

	/** Unreliable, about InputSendRate per second while possessed. Seq drops reordered packets. */
	UFUNCTION(Server, Unreliable)
	void ServerSetPilotInput(const FAirshipPilotInput& Input);


	// -------------------------------------------------------------------------
	// Control schemes (CPP_NOTES.md "Control schemes"). The pawn owns the replicated scheme and applies its preset; this
	// is the flight model's copy, set on every machine.
	// -------------------------------------------------------------------------

	/** ActiveScheme = InScheme, then ResetSchemeState(true). */
	void SetActiveScheme(EAirshipControlScheme InScheme);

	EAirshipControlScheme GetActiveScheme() const { return ActiveScheme; }

	/**
	 * Clears the schemes' runtime state (Galleon order pulses, Sky Racer drift / charge / chain / turbo / S-brake / burst
	 * timers, Point & Fly server heading loop); bSchemeSwitch also the v1 drift timer. Never the hold altitude, the pod
	 * spool, the boost latch, the fuel or the shaped controls (no jump in forces or cosmetics).
	 */
	void ResetSchemeState(bool bSchemeSwitch);

	/** Full-steer turn rate (deg/s) of the yaw table at |ForwardSpeed| (cm/s), lerped to YawRateBoost by Boost; YawRateDrift when drifting. */
	float GetYawRateMaxDeg(float ForwardSpeed, float Boost, bool bDrift) const;

	/** The drift kick (cm/s) a drift ending at ForwardSpeed (cm/s) pays: DriftBoostDV, capped by DriftBoostCapSpeed when that is set. */
	float GetDriftKickDV(float ForwardSpeed) const
	{
		return DriftBoostCapSpeed > 0.f ? FMath::Min(DriftBoostDV, FMath::Max(0.f, DriftBoostCapSpeed - ForwardSpeed)) : DriftBoostDV;
	}

	/** Shaped controls and states of this frame on this machine. */
	float GetShapedSteer() const { return ShSteer; }
	float GetShapedBoost() const { return ShBoost; }
	bool IsDrifting() const { return bDrifting; }
	bool IsGunDeck() const { return bShGunDeck; }

	/** Galleon: the engine order notch (-1..3) of the controls used this frame. */
	int32 GetGalleonNotch() const;

	/** Sky Racer: the turn rate (deg/s, + right) this machine's own shaped controls command now (drift path rate or grip rate). */
	float GetPilotYawRateCmdDeg() const;

	/**
	 * Point & Fly heading loop: the Classic-shaped steer (-1..1) that turns the hull from YawDeg (turning at YawRateDegS)
	 * onto TargetYawDeg without overshoot, at ForwardSpeed (cm/s) and shaped Boost. bBrake with a big turn left starts a
	 * brake-drift (State keeps its hysteresis). The server's call is authoritative, the pilot's only drives its cosmetics.
	 */
	float ComputeHeadingSteer(float TargetYawDeg, float YawDeg, float YawRateDegS, float ForwardSpeed, float Boost, bool bBrake, FPointFlyLoopState& State) const;


	// -------------------------------------------------------------------------
	// Body
	// -------------------------------------------------------------------------

	/** Hull mass override (kg). Handling is mass independent; mass matters for collisions. 0 = the mesh's own mass. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Body", meta = (ClampMin = "0.0", ForceUnits = "kg"))
	float MassKg = 40000.f;

	/** Move the centre of mass to DesiredCenterOfMass (hull space), so the 4 pods share the hover load evenly. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Body")
	bool bOverrideCenterOfMass = true;

	/** Hull-space centre of mass (cm): the thrust centroid in X. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Body", meta = (EditCondition = "bOverrideCenterOfMass"))
	FVector DesiredCenterOfMass = FVector(-170.0, 0.0, 0.0);

	/** Engine angular damping while alive (1/s). The yaw loop feeds it forward. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Body", meta = (ClampMin = "0.0"))
	float AngularDamping = 0.5f;

	/** Engine linear damping while alive (1/s). 0: the drag below is the flight model's own. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Body", meta = (ClampMin = "0.0"))
	float LinearDamping = 0.f;

	/** Engine angular speed cap while alive (deg/s). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Body", meta = (ClampMin = "1.0"))
	float MaxAngularVelocityDeg = 120.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Body", meta = (ClampMin = "0.0"))
	float DeadAngularDamping = 0.12f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Body", meta = (ClampMin = "0.0"))
	float DeadLinearDamping = 0.02f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Body", meta = (ClampMin = "1.0"))
	float DeadMaxAngularVelocityDeg = 180.f;

	/** Continuous collision on the hull (about 3 m per step at 90 m/s, research_flight 3.9). Cost not measured yet. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Body")
	bool bUseCCD = true;

	/** Clients turn the hull's gravity off while alive, so between server updates it coasts like the hovering server body. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Body")
	bool bDisableGravityOnClients = true;


	// -------------------------------------------------------------------------
	// Geometry (hull space, cm; the mesh bones win when they exist)
	// -------------------------------------------------------------------------

	/** Read pod and fan positions from the mesh's rest pose (bones below). Off: the fallbacks. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Geometry")
	bool bUseMeshBones = true;

	/** Thrust points, FL, FR, RL, RR. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Geometry", EditFixedSize)
	TArray<FName> PodBoneNames = { TEXT("Thruster_FL"), TEXT("Thruster_FR"), TEXT("Thruster_RL"), TEXT("Thruster_RR") };

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Geometry", EditFixedSize)
	TArray<FVector> PodLocationsFallback = { FVector(383.3, -465.6, -93.4), FVector(383.3, 491.8, -113.0), FVector(-716.7, -513.0, -120.4), FVector(-716.7, 576.8, -123.9) };

	/** Nozzle exits (FX bones), FL, FR, RL, RR: the ground clearance is measured from them. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Geometry", EditFixedSize)
	TArray<FName> NozzleExitNames = { TEXT("Thruster_FL_Flame"), TEXT("Thruster_FR_Flame"), TEXT("Thruster_RL_Flame"), TEXT("Thruster_RR_Flame") };

	/** How far (cm) a nozzle exit hangs below its pod pivot when the mesh has no exit bone (RIG_CONTRACT 3: about 4.3-5 m). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Geometry", meta = (ClampMin = "0.0"))
	float NozzleDepthFallback = 470.f;

	/** Fan thrust points (rotor centres), L, R. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Geometry", EditFixedSize)
	TArray<FName> FanBoneNames = { TEXT("Turbine_L_Rotor"), TEXT("Turbine_R_Rotor") };

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Geometry", EditFixedSize)
	TArray<FVector> FanLocationsFallback = { FVector(-1720.0, -760.0, 140.0), FVector(-1720.0, 760.0, 140.0) };


	// -------------------------------------------------------------------------
	// Input shaping (every machine; first-order filters, time constants in s)
	// -------------------------------------------------------------------------

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Shaping", meta = (ClampMin = "0.0", ForceUnits = "s"))
	float ThrottleTauUp = 0.30f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Shaping", meta = (ClampMin = "0.0", ForceUnits = "s"))
	float ThrottleTauDown = 0.45f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Shaping", meta = (ClampMin = "0.0", ForceUnits = "s"))
	float BoostTauUp = 0.15f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Shaping", meta = (ClampMin = "0.0", ForceUnits = "s"))
	float BoostTauDown = 0.60f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Shaping", meta = (ClampMin = "0.0", ForceUnits = "s"))
	float LiftTau = 0.25f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Shaping", meta = (ClampMin = "0.0", ForceUnits = "s"))
	float SteerTau = 0.15f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Shaping", meta = (ClampMin = "0.0", ForceUnits = "s"))
	float StrafeTau = 0.20f;

	/** Thruster force spool (actuator lag inside the loops). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Shaping", meta = (ClampMin = "0.0", ForceUnits = "s"))
	float PodForceTauUp = 0.10f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Shaping", meta = (ClampMin = "0.0", ForceUnits = "s"))
	float PodForceTauDown = 0.15f;


	// -------------------------------------------------------------------------
	// Vertical: climb / descend speed, altitude hold, floor and ceiling
	// -------------------------------------------------------------------------

	/** Climb speed at full lift (cm/s). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Vertical", meta = (ClampMin = "0.0"))
	float ClimbRate = 1200.f;

	/** Descent speed at full negative lift (cm/s). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Vertical", meta = (ClampMin = "0.0"))
	float DescendRate = 1500.f;

	/** Vertical speed loop gain (1/s). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Vertical", meta = (ClampMin = "0.0"))
	float Kvz = 2.0f;

	/** Altitude hold gain (1/s): speed command per cm of height error. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Vertical", meta = (ClampMin = "0.0"))
	float Kz = 0.8f;

	/** Fastest the hold loop climbs or sinks (cm/s). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Vertical", meta = (ClampMin = "0.0"))
	float HoldMaxSpeed = 800.f;

	/** On lift release the hold altitude is the current one plus the vertical speed times this (s), so it settles without a bounce. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Vertical", meta = (ClampMin = "0.0", ForceUnits = "s"))
	float HoldCaptureLead = 0.5f;

	/** |lift| below this counts as released. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Vertical", meta = (ClampMin = "0.0", ClampMax = "0.5"))
	float LiftDeadZone = 0.05f;

	/** Collective clamp, as a fraction of the ship's weight. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Vertical", meta = (ClampMin = "0.0"))
	float CollectiveMin = 0.25f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Vertical", meta = (ClampMin = "0.0"))
	float CollectiveMax = 1.9f;

	/** The ship climbs to keep at least this much space (cm) between its nozzle exits and the ground below (hops over platforms). 0 = off. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Vertical", meta = (ClampMin = "0.0"))
	float MinClearance = 400.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Vertical", meta = (ClampMin = "0.0"))
	float Kfloor = 1.5f;

	/** Descending toward the ground the sink speed is limited so the ship can stop at MinClearance with this deceleration (cm/s^2, 588 = 0.6 g). 0 = off. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Vertical", meta = (ClampMin = "0.0"))
	float FloorBrakeAccel = 588.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Vertical")
	bool bUseCeiling = false;

	/** World Z (cm) the ship can't climb above with bUseCeiling. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Vertical", meta = (EditCondition = "bUseCeiling"))
	float CeilingZ = 100000.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Vertical", meta = (ClampMin = "0.0", EditCondition = "bUseCeiling"))
	float Kceil = 1.0f;


	// -------------------------------------------------------------------------
	// Attitude: lean targets + PD (auto-level with no input)
	// -------------------------------------------------------------------------

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Attitude", meta = (ClampMin = "0.0"))
	float KpRoll = 6.25f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Attitude", meta = (ClampMin = "0.0"))
	float KdRoll = 4.5f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Attitude", meta = (ClampMin = "0.0"))
	float KpPitch = 4.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Attitude", meta = (ClampMin = "0.0"))
	float KdPitch = 3.2f;

	/** Bank into turns at full steer (deg), grip / drift / boost. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Attitude", meta = (ClampMin = "0.0", ClampMax = "60.0"))
	float BankMaxDeg = 18.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Attitude", meta = (ClampMin = "0.0", ClampMax = "60.0"))
	float BankMaxDriftDeg = 22.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Attitude", meta = (ClampMin = "0.0", ClampMax = "60.0"))
	float BankMaxBoostDeg = 12.f;

	/** Extra bank per unit strafe (deg). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Attitude")
	float StrafeBankDeg = 6.f;

	/** Forward speed (cm/s) at which the turn bank is full; below it the bank fades down to BankMinFraction. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Attitude", meta = (ClampMin = "1.0"))
	float BankFullSpeed = 2000.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Attitude", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float BankMinFraction = 0.25f;

	/** Nose dip per g of commanded forward acceleration (deg): accelerating dips the nose, braking flares it. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Attitude")
	float PitchPerG = 8.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Attitude")
	float PitchMinDeg = -8.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Attitude")
	float PitchMaxDeg = 6.f;

	/** Nose down at full boost (deg). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Attitude")
	float BoostPitchDeg = 3.f;

	/** Nose up at full lift (deg). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Attitude")
	float LiftPitchDeg = 3.f;

	/** Cap (rad/s^2) of the hidden roll/pitch stabiliser that adds what the pods can't deliver. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Attitude", meta = (ClampMin = "0.0"))
	float GyroTiltMax = 0.8f;


	// -------------------------------------------------------------------------
	// Thrusters (4 pods)
	// -------------------------------------------------------------------------

	/** Pod force range, as a fraction of the ship's weight per pod. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Thrusters", meta = (ClampMin = "0.0"))
	float PodForceMin = 0.02f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Thrusters", meta = (ClampMin = "0.0"))
	float PodForceMax = 0.55f;

	/** Largest thrust lean of a pod (deg, total). Physics and nozzle visuals use the same angles (rig limit +-5). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Thrusters", meta = (ClampMin = "0.0", ClampMax = "30.0"))
	float ThrusterGimbalMaxDeg = 5.f;

	/** Thrust lean forward per unit throttle / boost / brake (deg, brake leans back). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Thrusters")
	float GimbalPitchPerThrottle = 10.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Thrusters")
	float GimbalPitchPerBoost = 5.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Thrusters")
	float GimbalPitchPerBrake = 6.f;

	/** Thrust lean right per unit strafe (deg). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Thrusters")
	float GimbalRollPerStrafe = 12.f;

	/** Front pods lean right, rear pods left, per unit steer (deg): a little yaw help. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Thrusters")
	float GimbalRollPerSteer = 5.f;

	/** Extra pod force near the ground (cushion): fraction of the hover share at 0 height (nozzle exit), fading out over GroundTraceLength. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Thrusters", meta = (ClampMin = "0.0"))
	float GroundEffectStrength = 0.35f;

	/** Server: 4 traces down from the pods each frame (floor, ground effect, telemetry). GroundTraceLength counts from the nozzle exits. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Thrusters")
	bool bGroundTraces = true;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Thrusters", meta = (ClampMin = "1.0"))
	float GroundTraceLength = 1500.f;


	// -------------------------------------------------------------------------
	// Yaw: fans, rudder, stabiliser
	// -------------------------------------------------------------------------

	/** Yaw rate loop gain (1/s). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Yaw", meta = (ClampMin = "0.0"))
	float Kr = 3.0f;

	/** Largest commanded yaw acceleration (rad/s^2). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Yaw", meta = (ClampMin = "0.0"))
	float AlphaYawMax = 1.0f;

	/** Turn rate at full steer (deg/s): standing, at YawRateMidSpeed, at YawRateTopSpeed and above (linear between). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Yaw", meta = (ClampMin = "0.0"))
	float YawRateAtRest = 30.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Yaw", meta = (ClampMin = "0.0"))
	float YawRateAtMid = 45.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Yaw", meta = (ClampMin = "1.0"))
	float YawRateMidSpeed = 1500.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Yaw", meta = (ClampMin = "0.0"))
	float YawRateAtTop = 35.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Yaw", meta = (ClampMin = "1.0"))
	float YawRateTopSpeed = 4800.f;

	/** Turn rate while drifting / at full boost (deg/s). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Yaw", meta = (ClampMin = "0.0"))
	float YawRateDrift = 50.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Yaw", meta = (ClampMin = "0.0"))
	float YawRateBoost = 25.f;

	/** Fan housing yaw at full steer (deg); physics and visuals (TurbineYawDeg, rig limit +-12). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Yaw", meta = (ClampMin = "0.0", ClampMax = "45.0"))
	float FanYawMaxDeg = 12.f;

	/** Largest rudder yaw acceleration at full steer and RudderRefSpeed (rad/s^2), growing with speed squared. Allocated inside the yaw loop. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Yaw", meta = (ClampMin = "0.0"))
	float RudderAuthority = 0.6f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Yaw", meta = (ClampMin = "1.0"))
	float RudderRefSpeed = 4800.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Yaw", meta = (ClampMin = "0.0"))
	float RudderMaxAlpha = 1.2f;

	/** Cap (rad/s^2) of the hidden yaw stabiliser that adds what fans and rudder can't deliver. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Yaw", meta = (ClampMin = "0.0"))
	float GyroYawMax = 0.5f;


	// -------------------------------------------------------------------------
	// Forward: fan thrust, drag, brake
	// -------------------------------------------------------------------------

	/** Fan acceleration at full throttle (cm/s^2, 1323 = 1.35 g), fading to 0 at VTop. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Forward", meta = (ClampMin = "0.0"))
	float AFan = 1323.f;

	/** Top speed (cm/s). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Forward", meta = (ClampMin = "1.0"))
	float VTop = 5000.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Forward", meta = (ClampMin = "0.0"))
	float AFanBoost = 1960.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Forward", meta = (ClampMin = "1.0"))
	float VTopBoost = 9600.f;

	/** Reverse (S) acceleration and top reverse speed. Braking reverses the fans with AFan instead. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Forward", meta = (ClampMin = "0.0"))
	float AFanRev = 490.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Forward", meta = (ClampMin = "1.0"))
	float VTopRev = 1800.f;

	/** Thrust fade 1 - (v / VTop)^n: higher = full thrust closer to the top speed. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Forward", meta = (ClampMin = "1.0"))
	float ThrustFadeExponent = 6.f;

	/** Drag: -(C1 v + C2 v |v|) along the ship's forward axis. Long coasts by design. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Forward", meta = (ClampMin = "0.0"))
	float DragC1 = 0.05f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Forward", meta = (ClampMin = "0.0"))
	float DragC2 = 3e-6f;

	/** Air brake (1/s) while brake is held. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Forward", meta = (ClampMin = "0.0"))
	float Kbrake = 0.9f;

	/** Throttle the fans reverse to while braking (and moving forward faster than 100 cm/s). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Forward", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float BrakeReverseThrottle = 0.5f;

	/** Each fan's largest force, as a fraction of the ship's weight (normal / full boost). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Forward", meta = (ClampMin = "0.0"))
	float FanMax = 0.68f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Forward", meta = (ClampMin = "0.0"))
	float FanMaxBoost = 1.0f;

	/** Above this speed (cm/s) a strong pull caps it. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Forward", meta = (ClampMin = "1.0"))
	float HardSpeedCap = 11000.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Forward", meta = (ClampMin = "0.0"))
	float HardCapGain = 3.f;


	// -------------------------------------------------------------------------
	// Lateral: grip, strafe, drift
	// -------------------------------------------------------------------------

	/** Sideways speed at full strafe (cm/s). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Lateral", meta = (ClampMin = "0.0"))
	float StrafeSpeed = 1200.f;

	/** Grip: lateral speed loop gain (1/s), its cap (g) and the share of the scrubbed side speed turned into forward speed. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Lateral", meta = (ClampMin = "0.0"))
	float GripKlat = 4.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Lateral", meta = (ClampMin = "0.0"))
	float GripALatMaxG = 2.5f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Lateral", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float GripEta = 0.35f;

	/** Drift (brake + steer): looser grip, faster turn. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Lateral", meta = (ClampMin = "0.0"))
	float DriftKlat = 1.2f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Lateral", meta = (ClampMin = "0.0"))
	float DriftALatMaxG = 1.2f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Lateral", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float DriftEta = 0.4f;

	/** At full boost. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Lateral", meta = (ClampMin = "0.0"))
	float BoostKlat = 3.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Lateral", meta = (ClampMin = "0.0"))
	float BoostALatMaxG = 2.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Lateral", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float BoostEta = 0.3f;

	/** The side-to-forward redirect only works above this forward speed (cm/s). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Lateral", meta = (ClampMin = "0.0"))
	float RedirectMinSpeed = 500.f;

	/** Drift = brake held, |steer| above this, forward speed above DriftMinSpeed (cm/s). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Lateral", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float DriftSteerThreshold = 0.3f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Lateral", meta = (ClampMin = "0.0"))
	float DriftMinSpeed = 800.f;

	/** Air brake share kept while drifting (the fans don't reverse, the throttle stays). 0: a drift slides without slowing (research_flight 3.8). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Lateral", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float DriftBrakeScale = 0.f;

	/** A drift held this long (s) pays a forward kick of DriftBoostDV (cm/s) when it ends. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Lateral", meta = (ClampMin = "0.0"))
	float DriftBoostMinTime = 1.2f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Lateral", meta = (ClampMin = "0.0"))
	float DriftBoostDV = 600.f;

	/**
	 * The drift kick only tops the ship up to this forward speed (cm/s): kick = min(DriftBoostDV, max(0, this - forward
	 * speed)), so rhythmic drifts can't beat holding W on a straight. 0 = off (the full kick, v1). Point & Fly: 4800.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Lateral", meta = (ClampMin = "0.0"))
	float DriftBoostCapSpeed = 0.f;


	// -------------------------------------------------------------------------
	// Boost (fuel gated by the server)
	// -------------------------------------------------------------------------

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Boost", meta = (ClampMin = "0.0"))
	float BoostFuelMax = 100.f;

	/** Fuel per second while boosting / refilled per second after BoostRegenDelay (s). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Boost", meta = (ClampMin = "0.0"))
	float BoostDrainRate = 25.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Boost", meta = (ClampMin = "0.0"))
	float BoostRegenRate = 12.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Boost", meta = (ClampMin = "0.0"))
	float BoostRegenDelay = 1.f;

	/** A boost only starts with at least this much fuel. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Boost", meta = (ClampMin = "0.0"))
	float BoostMinFuelToStart = 20.f;

	/** Fuel each boost start costs on top of the drain (tapping Shift is no cheaper than holding it). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Boost", meta = (ClampMin = "0.0"))
	float BoostStartFuelCost = 10.f;

	/** Forward kick (cm/s) when a boost starts, at most once per BoostKickCooldown (s). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Boost", meta = (ClampMin = "0.0"))
	float BoostKickDV = 400.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Boost", meta = (ClampMin = "0.0"))
	float BoostKickCooldown = 1.5f;


	// -------------------------------------------------------------------------
	// Wind sway (fades out with speed)
	// -------------------------------------------------------------------------

	/** Sideways push (cm/s^2) and its frequency (Hz). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Wind", meta = (ClampMin = "0.0"))
	float WindLateralAccel = 25.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Wind", meta = (ClampMin = "0.0"))
	float WindLateralFrequency = 0.15f;

	/** Roll / pitch sway (rad/s^2) and frequencies (Hz). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Wind", meta = (ClampMin = "0.0"))
	float WindRollAccel = 0.03f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Wind", meta = (ClampMin = "0.0"))
	float WindRollFrequency = 0.12f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Wind", meta = (ClampMin = "0.0"))
	float WindPitchAccel = 0.015f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Wind", meta = (ClampMin = "0.0"))
	float WindPitchFrequency = 0.21f;

	/** No wind at this speed (cm/s) and above. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Wind", meta = (ClampMin = "1.0"))
	float WindFadeSpeed = 3000.f;


	// -------------------------------------------------------------------------
	// Cosmetic thrust levels (every machine, approximate; 1 = hover)
	// -------------------------------------------------------------------------

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Cosmetic")
	float PodAlphaPerLift = 0.6f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Cosmetic")
	float PodAlphaPerBoost = 0.3f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Cosmetic")
	float PodAlphaPerThrottle = 0.15f;

	/** Pods on the outside of a turn burn harder (bank). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Cosmetic")
	float PodAlphaPerSteer = 0.15f;

	/** Fan differential at full steer (pivot turn: the fans counter-rotate at rest). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Cosmetic", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float FanSteerShare = 0.6f;


	// -------------------------------------------------------------------------
	// Network
	// -------------------------------------------------------------------------

	/** Pilot input packets per second (more on change). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Network", meta = (ClampMin = "1.0", ClampMax = "120.0"))
	float InputSendRate = 30.f;

	/** Server: no packet for this long (s) = neutral controls (Galleon keeps the last engine order). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Network", meta = (ClampMin = "0.05"))
	float InputTimeout = 0.5f;


	// -------------------------------------------------------------------------
	// Base fixes (Docs/Airship/controls/BASELINE.md 4f). The defaults are v1 (off): Classic keeps them.
	// -------------------------------------------------------------------------

	/** 4a-1: build the roll / pitch / yaw torque requests from the hull-axis inertia tensor (v1 read the principal moments as hull axes). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|BaseFix")
	bool bHullAxisInertia = false;

	/** 4a-2: the pods' attitude solve takes out the roll / pitch torque of the fans' forward force (pushing 1.4 m above the COM). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|BaseFix")
	bool bFanTorqueFeedForward = false;

	/** 4b-1: hidden vertical brake (cm/s^2) while the vertical speed runs past its command in its own direction. 0 = off. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|BaseFix", meta = (ClampMin = "0.0"))
	float VertBrakeAccel = 0.f;

	/** 4b-2: the hold loop stops with at most this deceleration (cm/s^2): sqrt speed limit, stopping-distance capture. 0 = v1 (linear, HoldCaptureLead). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|BaseFix", meta = (ClampMin = "0.0"))
	float HoldBrakeAccel = 0.f;

	/** 4b-3: lift filter time constant (s) toward a smaller command on the same side (the release). 0 = LiftTau. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|BaseFix", meta = (ClampMin = "0.0"))
	float LiftTauRelease = 0.f;

	/** 4c-1: a brake press in hold mode holds at the stopping point (the release lead), not at the current height. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|BaseFix")
	bool bBrakeHoldLead = false;

	/** 4c-2: the brake's reverse throttle fades out below this forward speed (cm/s). 0 = v1 (full reverse above 100 cm/s). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|BaseFix", meta = (ClampMin = "0.0"))
	float BrakeFadeSpeed = 0.f;

	/** 4d: station keeping with no throttle, strafe or boost: forward speed loop gain (1/s), full below StationKeepSpeed (cm/s), gone at twice it, capped (cm/s^2). 0 = off. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|BaseFix", meta = (ClampMin = "0.0"))
	float StationKeepGain = 0.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|BaseFix", meta = (ClampMin = "1.0"))
	float StationKeepSpeed = 300.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|BaseFix", meta = (ClampMin = "0.0"))
	float StationKeepAccelMax = 150.f;


	// -------------------------------------------------------------------------
	// Shared scheme mechanisms (IMPLEMENTATION_PLAN.md 1.9). The defaults are v1 (off): Classic keeps them.
	// -------------------------------------------------------------------------

	/** The grip / sidle force acts level (no turn sink from a banked hull), along bLevelGripAlongHeading's direction. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Lateral")
	bool bLevelGripForce = false;

	/** With bLevelGripForce: level and perpendicular to the heading (Sky Racer); false = the hull's right axis made level (Galleon). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Lateral")
	bool bLevelGripAlongHeading = false;

	/** Air brake cap (cm/s^2): a constant-deceleration stop. 0 = no cap (v1). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Forward", meta = (ClampMin = "0.0"))
	float BrakeMaxAccel = 0.f;

	/** Steer filter time constant (s) while the steer is being taken off (the helm returns). 0 = SteerTau. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Shaping", meta = (ClampMin = "0.0"))
	float SteerTauRelease = 0.f;

	/** "Meet her": the yaw loop gain (1/s) and cap (rad/s^2, at least AlphaYawMax) while a turn is being taken off. 0 = Kr. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Yaw", meta = (ClampMin = "0.0"))
	float KrSteady = 0.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Yaw", meta = (ClampMin = "0.0"))
	float AlphaYawMaxSteady = 0.f;

	/** Yaw loop gain (1/s) and cap (rad/s^2) while drifting. 0 = Kr / AlphaYawMax. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Yaw", meta = (ClampMin = "0.0"))
	float DriftKr = 0.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Yaw", meta = (ClampMin = "0.0"))
	float DriftAlphaYawMax = 0.f;

	/** Wheel and rudder swing (cosmetic Steer, clamped to 1.3) per unit shaped steer while drifting. The fan yaw stays the forces'. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Cosmetic", meta = (ClampMin = "0.0"))
	float DriftCosmeticSteerScale = 1.f;

	/**
	 * The steady gun deck (Galleon: broadside stations; Sky Racer and Point & Fly: Aim held). Bank always; turn rate,
	 * forward thrust and air brake when not drifting. 1 = v1.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|GunDeck", meta = (ClampMin = "0.0"))
	float GunDeckBankScale = 1.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|GunDeck", meta = (ClampMin = "0.0"))
	float GunDeckYawScale = 1.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|GunDeck", meta = (ClampMin = "0.0"))
	float GunDeckThrottleScale = 1.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|GunDeck", meta = (ClampMin = "0.0"))
	float GunDeckBrakeScale = 1.f;


	// -------------------------------------------------------------------------
	// Galleon (SCHEME_GALLEON.md). Only read while ActiveScheme == Galleon: the defaults are Galleon's values.
	// -------------------------------------------------------------------------

	/** Speeds the SLOW / HALF / FULL ASTERN orders hold (cm/s); FULL is throttle 1. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Galleon", meta = (ClampMin = "0.0"))
	float GalleonOrderSlowSpeed = 1400.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Galleon", meta = (ClampMin = "0.0"))
	float GalleonOrderHalfSpeed = 2800.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Galleon", meta = (ClampMin = "0.0"))
	float GalleonOrderAsternSpeed = 1200.f;

	/** Speed loop P gain (throttle per cm/s of error), on top of the drag-balancing throttle. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Galleon", meta = (ClampMin = "0.0"))
	float GalleonOrderSpeedGain = 0.001f;

	/** The engines back at this (cm/s^2) to slow the ship to a lower order while it still moves forward. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Galleon", meta = (ClampMin = "0.0"))
	float GalleonOrderReverseAccel = 800.f;

	/** Cosmetic pod thrust pulse on an order change or a boost start, and its fade (s). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Galleon", meta = (ClampMin = "0.0"))
	float GalleonOrderPulse = 0.35f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Galleon", meta = (ClampMin = "0.0"))
	float GalleonOrderPulseTime = 0.45f;


	// -------------------------------------------------------------------------
	// Sky Racer (SCHEME_SKYRACER.md). Only read while ActiveScheme == SkyRacer: the defaults are Sky Racer's values.
	// -------------------------------------------------------------------------

	/** Drift entry: brake + |steer| >= SkyDriftEnterSteer at SkyDriftEnterSpeed (cm/s) or faster; it ends below SkyDriftExitSpeed. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyDriftEnterSteer = 0.5f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyDriftEnterSpeed = 1500.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyDriftExitSpeed = 800.f;

	/** The steer sets the drift's path turn rate (deg/s, counter-steer .. full in) and the slip it holds (deg). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyDriftPathRateMinDeg = 24.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyDriftPathRateMaxDeg = 46.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyDriftSlipMinDeg = 16.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyDriftSlipMaxDeg = 26.f;

	/** Slip hold gain (1/s), how far the path may lead the hull at turn-in (deg/s), and the nose's yaw rate limit (deg/s). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyDriftSlipGain = 3.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyDriftPathLeadDeg = 10.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyDriftYawRateMaxDeg = 65.f;

	/** Path force cap (g), slide scrub (1/s), drift bank (deg) and the pods' roll into the slide (deg). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyDriftALatMaxG = 5.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyDriftScrub = 0.08f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyDriftBankDeg = 24.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyDriftGimbalRollDeg = 4.f;

	/** Exit snap after a drift: window (s, 0 = off), grip gain (1/s) and cap (g), the nose's swing back per rad of slip (1/s). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyDriftExitTime = 0.4f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyDriftExitKlat = 8.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyDriftExitALatMaxG = 5.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyDriftExitYawGain = 6.f;

	/** While drifting with S not held, the throttle target is at least this: a drift drives at full power, W optional (review R1; 0 = as designed). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyDriftThrottle = 1.f;

	/** Charge per second (counter-steer .. full in), the tier thresholds, and the server's charge grace for remote pilots. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyChargeRateMin = 0.2f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyChargeRateMax = 0.5f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyTier1 = 0.25f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyTier2 = 0.55f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyTier3 = 1.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyTierGrace = 0.03f;

	/** Mini-turbo per tier: forward kick (cm/s), burn length (s), boost fuel paid. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyTurboKickDV1 = 300.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyTurboKickDV2 = 500.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyTurboKickDV3 = 750.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyTurboTime1 = 0.5f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyTurboTime2 = 0.8f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyTurboTime3 = 1.2f;

	/** Burn acceleration (cm/s^2, fading 1 -> 0 over the burn) and the speed (cm/s) where it fades out. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyTurboAccel = 490.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "1.0"))
	float SkyTurboVTop = 9000.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyTurboFuel1 = 4.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyTurboFuel2 = 8.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyTurboFuel3 = 15.f;

	/** A drift started within this (s) of a turbo chains: the kick grows by SkyChainBonus per link, up to SkyChainMax links. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyChainWindow = 2.5f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyChainBonus = 0.15f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0"))
	int32 SkyChainMax = 3;

	/** S is a progressive brake above this forward speed (cm/s; 0 = v1 reverse), ramping in / out with these time constants (s). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkySBrakeSpeed = 300.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkySBrakeTauUp = 0.3f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkySBrakeTauDown = 0.08f;

	/** Grip turn: share of the centripetal acceleration fed forward, and the share of the scrubbed side energy given back forward. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyGripCentripetalFF = 0.5f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyGripEnergyKeep = 0.85f;

	/** Diving (lift held down, sinking) above SkyDiveMinSpeed (cm/s) adds this forward acceleration per cm/s of sink (1/s). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyDiveAccelPerSink = 0.06f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyDiveMinSpeed = 1500.f;

	/** Every boost press gives at least this much boost (s). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyBoostMinBurst = 0.5f;

	/** Cosmetic (guesses): rear pod thrust flicker per unit charge, pod thrust per unit burn, Niagara Boost glow at tier 1 / 2 / 3. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyFXDriftPulse = 0.25f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyFXTurboThrust = 0.4f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyFXChargeGlow1 = 0.25f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyFXChargeGlow2 = 0.45f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyFXChargeGlow3 = 0.65f;


	// -------------------------------------------------------------------------
	// Point & Fly (SCHEME_POINTFLY.md). Only read while ActiveScheme == PointFly: the defaults are Point & Fly's values.
	// -------------------------------------------------------------------------

	/** Heading loop: turn rate per degree of predicted error (1/s), prediction time (s), planned yaw deceleration (deg/s^2), dead band (deg). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|PointFly", meta = (ClampMin = "0.0"))
	float PFHeadingKp = 6.5f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|PointFly", meta = (ClampMin = "0.0"))
	float PFHeadingLead = 0.18f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|PointFly", meta = (ClampMin = "0.0"))
	float PFHeadingDecelDeg = 55.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|PointFly", meta = (ClampMin = "0.0"))
	float PFHeadingDeadbandDeg = 0.25f;

	/** Brake with this much turn left (deg) starts a drift, which ends with PFDriftEndDeg left; the sliding hull's deceleration scale. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|PointFly", meta = (ClampMin = "0.0"))
	float PFDriftStartDeg = 40.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|PointFly", meta = (ClampMin = "0.0"))
	float PFDriftEndDeg = 15.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|PointFly", meta = (ClampMin = "0.0"))
	float PFDriftDecelScale = 0.8f;

	/** S while moving forward slows at this (cm/s^2), then backs up as v1. 0 = off. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|PointFly", meta = (ClampMin = "0.0"))
	float PFReverseBrakeAccel = 980.f;

	/** Share (0..1) of the turn's downward grip the collective makes up (no sink in turns). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|PointFly", meta = (ClampMin = "0.0"))
	float PFTurnLiftComp = 1.f;

protected:

	virtual void BeginPlay() override;

	/** Server: the controls used, boost gated by fuel, for the other machines' cosmetics. */
	UPROPERTY(Replicated)
	FAirshipPilotInput RepInput;

	UPROPERTY(Replicated)
	float BoostFuel = 100.f;

private:

	AAirshipPawn* GetShip() const;
	UPrimitiveComponent* GetBody() const;

	/** The controls this machine uses this frame. */
	FAirshipPilotInput SelectControls() const;

	/** Server: fuel, the boost latch and its kick. Returns the gated boost. */
	bool UpdateBoostServer(bool bWantBoost, float Dt, UPrimitiveComponent* Body);

	/** First-order filters toward the controls (and each scheme's throttle / brake / drift decisions). */
	void ShapeControls(const FAirshipPilotInput& Controls, float Dt, float ForwardSpeed);

	/** Galleon shaping: order decode and pulses, the stern swing, the speed loop's throttle target, the brake. */
	void ShapeGalleon(const FAirshipPilotInput& Controls, float Dt, float ForwardSpeed, float RawSteer, float& ThrottleTarget);

	/** Sky Racer shaping: the drift state machine (charge, tier, chain, turbo release), the S-brake ramp, the throttle target. */
	void ShapeSkyRacer(const FAirshipPilotInput& Controls, float Dt, float ForwardSpeed, float RawSteer, float& ThrottleTarget);

	/** Galleon: the throttle (-1..1) that balances the drag at OrderSpeed (cm/s), forward or astern. */
	float GalleonHoldThrottle(float OrderSpeed) const;

	/** Sky Racer: the tier (0..3) a drift charge has reached. */
	int32 SkyTierOf(float Charge) const;

	/** Thrust lean of each pod (deg) from the shaped controls. */
	void ComputeGimbals(float OutPitchDeg[Airship::NumPods], float OutRollDeg[Airship::NumPods]) const;

	/** Server: the force model (section 3 of research_flight.md). */
	void ApplyForces(UPrimitiveComponent* Body, float Dt);

	/** Server, every frame before SelectControls: the unpiloted mode and its target (see GetUnpilotedMode). */
	void UpdateUnpilotedMode(UPrimitiveComponent* Body, const FVector& Velocity);

	/**
	 * Server, while drifting: the hull's box swept ahead finds something it would bump into. The sweep covers the ship's
	 * real forward speed (not the drift target: after a fast exit it is still slowing from cruise) times
	 * DriftLookAheadTime, plus what it needs to stop at HoldAccelMax, so the hold starts in time. OutDistance: its length.
	 */
	bool SweepDriftAhead(UPrimitiveComponent* Body, float ForwardSpeed, float& OutDistance) const;

	/** The box sweep of SweepDriftAhead / SweepHullAhead along HeadingYaw. LogContext: the log line's reason (null = no log). */
	bool SweepHullBox(const UPrimitiveComponent* Body, float HeadingYaw, float Distance, FHitResult* OutHit, const TCHAR* LogContext) const;

	/** The drift's look-ahead length (cm) at ForwardSpeed (cm/s along the drift heading): see SweepDriftAhead. */
	float GetDriftLookAheadDistance(float ForwardSpeed) const;

	/** UnpilotedTarget = Hold at the centre of mass and the hull's heading now. */
	void BeginHold(UPrimitiveComponent* Body);

	/** True for what a drift ignores: characters, other pawns that aren't ships, cannonballs, its own ship and what is attached to it. */
	bool IsDriftIgnored(const AActor* Other) const;

	/** Server: ground distance under each pod. */
	void TraceGround(UPrimitiveComponent* Body);

	void UpdateCosmetic(float ForwardSpeed, float Speed);

	/** The pilot's machine: sends LocalInput when it changed or the send interval passed. */
	void SendLocalInput();

	// Controls
	FAirshipPilotInput LocalInput;
	FAirshipPilotInput ServerInput;
	FAirshipPilotInput DebugInput;
	FAirshipPilotInput CurrentControls;
	FAirshipPilotInput LastSentInput;
	bool bDebugInputActive = false;
	bool bHasServerInput = false;
	double LastServerInputTime = -1000.0;
	double LastSendTime = -1000.0;
	uint8 LocalSeq = 0;
	bool bFlightEnabled = true;

	// Shaped controls
	float ShThrottle = 0.f;
	float ShBoost = 0.f;
	float ShLift = 0.f;
	float ShSteer = 0.f;
	float ShStrafe = 0.f;
	bool bShBrake = false;
	bool bShAiming = false;
	bool bDrifting = false;

	/** The steady gun deck this frame (Galleon: the stations bit; other schemes: Aim). */
	bool bShGunDeck = false;

	/** Air brake share this frame (0..1): 1 with the brake bit (v1), Sky Racer's analog S-brake, 0 in a Sky Racer drift. */
	float ShBrakeAmount = 0.f;

	// Control scheme (the pawn's ControlScheme, set on every machine by the pawn's BeginPlay / OnRep). Classic until then on
	// purpose: this component's tunables are the class defaults (v1) until the pawn writes its scheme's preset.
	EAirshipControlScheme ActiveScheme = EAirshipControlScheme::Classic;

	// Galleon (every machine: from the controls it has)
	int32 GalleonLastNotch = 0;
	float GalleonOrderPulse01 = 0.f;
	float GalleonBoostPulse01 = 0.f;
	bool bGalleonPrevBoost = false;

	/** Server: the last packet accepted, for Galleon's timeout rule (the engine room keeps the order). */
	FAirshipPilotInput LastGoodServerInput;

	// Sky Racer (every machine runs the drift state machine from the controls it has; the server pays the turbo)
	double SkyClock = 0.0;
	int8 SkyDriftDir = 0;
	float SkyCharge = 0.f;
	float SkyDriftTime = 0.f;
	uint8 SkyChain = 0;
	double SkyLastReleaseTime = -1000.0;
	uint8 SkyTurboTier = 0;
	float SkyTurboLeft = 0.f;
	float SkyTurboTotal = 1.f;
	/** Tier released this frame (0 = none): ApplyForces pays its kick and fuel. */
	uint8 SkyTurboEvent = 0;
	uint8 SkyTurboChain = 0;
	uint8 SkyTurboEventCount = 0;
	float SkyExitLeft = 0.f;
	float SkySBrake = 0.f;
	double SkyBoostStartTime = -1000.0;
	double SkyLocalBoostStartTime = -1000.0;

	// Point & Fly (server)
	FPointFlyLoopState ServerHeadingLoop;
	/** The vertical part of last frame's lateral grip (cm/s^2): the collective makes it up (PFTurnLiftComp). */
	float LastGripAccelZ = 0.f;

	// Server state
	bool bBoostActive = false;
	bool bLocalBoostActive = false;
	double LastBoostKickTime = -1000.0;
	float BoostRegenTimer = 0.f;
	float DriftTime = 0.f;
	bool bHoldValid = false;

	// Unpiloted (server; UpdateUnpilotedMode)
	FAirshipUnpilotedTarget UnpilotedTarget;
	/** NotifyPilotLeft: the next evaluation decides drift or park from these. */
	bool bDriftRequest = false;
	float DriftExitForwardSpeed = 0.f;
	float DriftRequestYaw = 0.f;
	FVector DriftStart = FVector::ZeroVector;
	/** The exit speed the drift may not go above (a slow exit never speeds up). */
	float DriftSpeedLimit = 0.f;
	/** A bow contact or the look-ahead sweep: the drift ends next evaluation. */
	bool bDriftBlocked = false;

	// Lane (server, round 2 PR B): SetLaneTarget's target and the frame it was set, the drift limit override, the
	// pilot's drive this frame (HasPilotDriveInput) and whether the lane assist cleared it
	FAirshipUnpilotedTarget LaneTarget;
	uint64 LaneTargetFrame = 0;
	bool bLaneTargetAssist = false;
	bool bLaneAssistThisFrame = false;
	float DriftMaxDistanceOverride = 0.f;
	bool bPilotDriveInput = false;
	double NextDriftSweepTime = 0.0;
	bool bBrakeWasHeld = false;
	float HoldZ = 0.f;
	bool bPodForceInitialized = false;
	float PodForce[Airship::NumPods] = {};
	float GroundDist[Airship::NumPods] = { -1.f, -1.f, -1.f, -1.f };
	float MinGroundDist = -1.f;

	// Geometry (hull space, cm)
	FVector PodLocal[Airship::NumPods];
	float PodNozzleDepth[Airship::NumPods] = {};
	FVector FanLocal[Airship::NumFans];

	FAirshipCosmeticState Cosmetic;
};
