// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "Airship/AirshipTypes.h"
#include "AirshipFlightComponent.generated.h"

class AAirshipPawn;
class UPrimitiveComponent;

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

	UFUNCTION(BlueprintPure, Category = "Airship|Flight")
	float GetBoostFuel() const { return BoostFuel; }

	/** Hull-local pod / fan positions used by the forces (cm). */
	FVector GetPodLocation(int32 Pod) const { return PodLocal[FMath::Clamp(Pod, 0, Airship::NumPods - 1)]; }
	FVector GetFanLocation(int32 Fan) const { return FanLocal[FMath::Clamp(Fan, 0, Airship::NumFans - 1)]; }

	/** Unreliable, about InputSendRate per second while possessed. Seq drops reordered packets. */
	UFUNCTION(Server, Unreliable)
	void ServerSetPilotInput(const FAirshipPilotInput& Input);


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

	/** Server: no packet for this long (s) = neutral controls. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Network", meta = (ClampMin = "0.05"))
	float InputTimeout = 0.5f;

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

	/** First-order filters toward the controls. */
	void ShapeControls(const FAirshipPilotInput& Controls, float Dt, float ForwardSpeed);

	/** Thrust lean of each pod (deg) from the shaped controls. */
	void ComputeGimbals(float OutPitchDeg[Airship::NumPods], float OutRollDeg[Airship::NumPods]) const;

	/** Server: the force model (section 3 of research_flight.md). */
	void ApplyForces(UPrimitiveComponent* Body, float Dt);

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

	// Server state
	bool bBoostActive = false;
	bool bLocalBoostActive = false;
	double LastBoostKickTime = -1000.0;
	float BoostRegenTimer = 0.f;
	float DriftTime = 0.f;
	bool bHoldValid = false;
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
