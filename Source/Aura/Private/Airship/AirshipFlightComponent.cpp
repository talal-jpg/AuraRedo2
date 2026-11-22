// Fill out your copyright notice in the Description page of Project Settings.


#include "Airship/AirshipFlightComponent.h"

#include "Airship/AirshipPawn.h"
#include "Components/PrimitiveComponent.h"
#include "DrawDebugHelpers.h"
#include "Engine/World.h"
#include "HAL/IConsoleManager.h"
#include "Net/UnrealNetwork.h"
#include "PhysicsEngine/BodyInstance.h"
#include "PhysicsEngine/PhysicsSettings.h"

DEFINE_LOG_CATEGORY_STATIC(LogAirshipFlight, Log, All);

// Named, not anonymous: the unity build compiles this file together with others
namespace AirshipFlightPrivate
{
	TAutoConsoleVariable<int32> CVarDebugForces(
		TEXT("Aura.Airship.Debug"),
		0,
		TEXT("1: the server draws every airship's flight forces (pods yellow, fans cyan, COM force green, torque magenta, velocity white, hold altitude blue, ground traces)."),
		ECVF_Default);

	/** First-order filter step toward Target with time constant Tau (s). */
	float Approach(float Current, float Target, float Dt, float Tau)
	{
		if (Tau <= KINDA_SMALL_NUMBER)
		{
			return Target;
		}
		return Current + (Target - Current) * (1.f - FMath::Exp(-Dt / Tau));
	}

	float ApproachUpDown(float Current, float Target, float Dt, float TauUp, float TauDown)
	{
		return Approach(Current, Target, Dt, FMath::Abs(Target) > FMath::Abs(Current) ? TauUp : TauDown);
	}

	/** Solves M x = B for a 3x3 M (rows). False when M is (nearly) singular. */
	bool Solve3x3(const double M[3][3], const double B[3], double X[3])
	{
		const double C00 = M[1][1] * M[2][2] - M[1][2] * M[2][1];
		const double C01 = M[1][2] * M[2][0] - M[1][0] * M[2][2];
		const double C02 = M[1][0] * M[2][1] - M[1][1] * M[2][0];
		const double Det = M[0][0] * C00 + M[0][1] * C01 + M[0][2] * C02;

		if (FMath::Abs(Det) < 1e-12)
		{
			return false;
		}

		const double InvDet = 1.0 / Det;
		const double Inv[3][3] =
		{
			{ C00 * InvDet, (M[0][2] * M[2][1] - M[0][1] * M[2][2]) * InvDet, (M[0][1] * M[1][2] - M[0][2] * M[1][1]) * InvDet },
			{ C01 * InvDet, (M[0][0] * M[2][2] - M[0][2] * M[2][0]) * InvDet, (M[0][2] * M[1][0] - M[0][0] * M[1][2]) * InvDet },
			{ C02 * InvDet, (M[0][1] * M[2][0] - M[0][0] * M[2][1]) * InvDet, (M[0][0] * M[1][1] - M[0][1] * M[1][0]) * InvDet },
		};

		for (int32 Row = 0; Row < 3; ++Row)
		{
			X[Row] = Inv[Row][0] * B[0] + Inv[Row][1] * B[1] + Inv[Row][2] * B[2];
		}
		return true;
	}
}

UAirshipFlightComponent::UAirshipFlightComponent()
{
	// The pawn calls UpdateFlight from its own Tick, so the order (input, forces, FX, camera) is fixed
	PrimaryComponentTick.bCanEverTick = false;
	SetIsReplicatedByDefault(true);

	for (int32 Pod = 0; Pod < Airship::NumPods; ++Pod)
	{
		PodLocal[Pod] = PodLocationsFallback.IsValidIndex(Pod) ? PodLocationsFallback[Pod] : FVector::ZeroVector;
		PodNozzleDepth[Pod] = NozzleDepthFallback;
	}

	for (int32 Fan = 0; Fan < Airship::NumFans; ++Fan)
	{
		FanLocal[Fan] = FanLocationsFallback.IsValidIndex(Fan) ? FanLocationsFallback[Fan] : FVector::ZeroVector;
	}
}

void UAirshipFlightComponent::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);

	// The pilot shapes its own input at once
	DOREPLIFETIME_CONDITION(UAirshipFlightComponent, RepInput, COND_SkipOwner);
	DOREPLIFETIME(UAirshipFlightComponent, BoostFuel);
}

void UAirshipFlightComponent::BeginPlay()
{
	Super::BeginPlay();

	if (GetOwner() && GetOwner()->HasAuthority())
	{
		BoostFuel = BoostFuelMax;
	}

	RefreshActuatorLocations();
	ApplyBodySettings();
}

AAirshipPawn* UAirshipFlightComponent::GetShip() const
{
	return Cast<AAirshipPawn>(GetOwner());
}

UPrimitiveComponent* UAirshipFlightComponent::GetBody() const
{
	return GetOwner() ? Cast<UPrimitiveComponent>(GetOwner()->GetRootComponent()) : nullptr;
}


// =============================================================================
// Setup
// =============================================================================

void UAirshipFlightComponent::RefreshActuatorLocations()
{
	const AAirshipPawn* Ship = GetShip();

	for (int32 Pod = 0; Pod < Airship::NumPods; ++Pod)
	{
		const FName Bone = PodBoneNames.IsValidIndex(Pod) ? PodBoneNames[Pod] : NAME_None;

		if (!(bUseMeshBones && Ship && Ship->GetMeshRestLocation(Bone, PodLocal[Pod])))
		{
			PodLocal[Pod] = PodLocationsFallback.IsValidIndex(Pod) ? PodLocationsFallback[Pod] : FVector::ZeroVector;
		}

		// How far the nozzle exit hangs below the pod pivot (the ground clearance is measured from the exit)
		const FName Exit = NozzleExitNames.IsValidIndex(Pod) ? NozzleExitNames[Pod] : NAME_None;
		FVector ExitLocal;
		PodNozzleDepth[Pod] = (bUseMeshBones && Ship && Ship->GetMeshRestLocation(Exit, ExitLocal))
			? FMath::Max(0.f, static_cast<float>(PodLocal[Pod].Z - ExitLocal.Z))
			: FMath::Max(0.f, NozzleDepthFallback);
	}

	for (int32 Fan = 0; Fan < Airship::NumFans; ++Fan)
	{
		const FName Bone = FanBoneNames.IsValidIndex(Fan) ? FanBoneNames[Fan] : NAME_None;

		if (!(bUseMeshBones && Ship && Ship->GetMeshRestLocation(Bone, FanLocal[Fan])))
		{
			FanLocal[Fan] = FanLocationsFallback.IsValidIndex(Fan) ? FanLocationsFallback[Fan] : FVector::ZeroVector;
		}
	}
}

void UAirshipFlightComponent::ApplyBodySettings()
{
	UPrimitiveComponent* Body = GetBody();

	if (!Body || !Body->IsSimulatingPhysics())
	{
		return;
	}

	if (MassKg > 0.f)
	{
		Body->SetMassOverrideInKg(NAME_None, MassKg, true);
	}

	if (bOverrideCenterOfMass)
	{
		// SetCenterOfMass sets an offset from the computed centre (COMNudge), so take the current nudge out first
		const FTransform BodyTM = Body->GetComponentTransform();
		const FVector CurrentLocal = BodyTM.InverseTransformPosition(Body->GetCenterOfMass());
		const FVector Natural = CurrentLocal - Body->BodyInstance.COMNudge;
		Body->SetCenterOfMass(DesiredCenterOfMass - Natural);
	}

	Body->SetAngularDamping(bFlightEnabled ? AngularDamping : DeadAngularDamping);
	Body->SetLinearDamping(bFlightEnabled ? LinearDamping : DeadLinearDamping);
	Body->SetPhysicsMaxAngularVelocityInDegrees(bFlightEnabled ? MaxAngularVelocityDeg : DeadMaxAngularVelocityDeg);
	Body->SetUseCCD(bUseCCD);

	// Clients: the server's hover forces don't run here, so without this the body sags between updates
	const bool bClient = GetOwner() && !GetOwner()->HasAuthority();
	Body->SetEnableGravity(!(bClient && bDisableGravityOnClients && bFlightEnabled));
}

void UAirshipFlightComponent::SetFlightEnabled(bool bEnabled)
{
	if (bFlightEnabled == bEnabled)
	{
		return;
	}

	bFlightEnabled = bEnabled;
	ResetInput();
	ApplyBodySettings();
}


// =============================================================================
// Controls
// =============================================================================

void UAirshipFlightComponent::SetLocalInput(const FAirshipPilotInput& Input)
{
	LocalInput = Input;

	if (GetOwner() && GetOwner()->HasAuthority())
	{
		// Listen server host: no RPC
		ServerInput = Input;
		bHasServerInput = true;
		LastServerInputTime = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0;
		return;
	}

	SendLocalInput();
}

void UAirshipFlightComponent::SendLocalInput()
{
	const UWorld* World = GetWorld();

	if (!World)
	{
		return;
	}

	const double Now = World->GetRealTimeSeconds();
	const bool bChanged = !LocalInput.SameControls(LastSentInput);
	const double Interval = 1.0 / FMath::Max(InputSendRate, 1.f);

	if (!bChanged && Now - LastSendTime < Interval)
	{
		return;
	}

	FAirshipPilotInput Packet = LocalInput;
	Packet.Seq = ++LocalSeq;
	LastSentInput = Packet;
	LastSendTime = Now;
	ServerSetPilotInput(Packet);
}

void UAirshipFlightComponent::ServerSetPilotInput_Implementation(const FAirshipPilotInput& Input)
{
	// Unreliable: drop packets older than the last one used (wrap-aware). After a long loss (128+ packets) the order
	// test means nothing, so a stale stored input takes any packet.
	const double Now = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0;
	const bool bStale = Now - LastServerInputTime > InputTimeout;

	if (bHasServerInput && !bStale && static_cast<int8>(Input.Seq - ServerInput.Seq) <= 0)
	{
		return;
	}

	ServerInput = Input;
	bHasServerInput = true;
	LastServerInputTime = Now;
}

void UAirshipFlightComponent::ResetInput()
{
	ServerInput = FAirshipPilotInput();
	LocalInput = FAirshipPilotInput();
	LastSentInput = FAirshipPilotInput();
	bHasServerInput = false;
}

void UAirshipFlightComponent::SetDebugInput(const FAirshipPilotInput& Input)
{
	DebugInput = Input;
	bDebugInputActive = true;
}

void UAirshipFlightComponent::ClearDebugInput()
{
	DebugInput = FAirshipPilotInput();
	bDebugInputActive = false;
}

FAirshipPilotInput UAirshipFlightComponent::SelectControls() const
{
	const AAirshipPawn* Ship = GetShip();

	if (!bFlightEnabled || !Ship)
	{
		return FAirshipPilotInput();
	}

	// The pilot's machine: its keys, or the debug controls in their place (AAirshipPawn::GatherLocalInput), which go to
	// the server the same way
	if (Ship->IsLocallyControlled())
	{
		return LocalInput;
	}

	// The server's copy of a ship (piloted from a client or by nobody): the debug controls fly it directly
	if (bDebugInputActive)
	{
		return DebugInput;
	}

	if (Ship->HasAuthority())
	{
		const UWorld* World = GetWorld();
		const bool bFresh = bHasServerInput && World && World->GetTimeSeconds() - LastServerInputTime <= InputTimeout;

		// No pilot, or the pilot went quiet: neutral controls (the ship holds its altitude)
		return (bFresh && Ship->GetController()) ? ServerInput : FAirshipPilotInput();
	}

	return RepInput;
}

bool UAirshipFlightComponent::UpdateBoostServer(bool bWantBoost, float Dt, UPrimitiveComponent* Body)
{
	if (bWantBoost && !bBoostActive && BoostFuel >= BoostMinFuelToStart)
	{
		bBoostActive = true;

		// Every start costs fuel and the kick has a cooldown: tapping Shift is no cheaper than holding it
		BoostFuel = FMath::Max(0.f, BoostFuel - BoostStartFuelCost);
		const double Now = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0;

		if (Body && Body->IsSimulatingPhysics() && BoostKickDV > 0.f && Now - LastBoostKickTime >= BoostKickCooldown)
		{
			const FVector KickDV = Body->GetForwardVector() * BoostKickDV;
			Body->AddImpulse(KickDV, NAME_None, true);
			LastBoostKickTime = Now;

			// The ship's own speed for the impact cap (a kick while scraping isn't a contact's kick)
			if (AAirshipPawn* Ship = GetShip())
			{
				Ship->NoteFlightKick(KickDV);
			}
		}
	}

	if (!bWantBoost || BoostFuel <= 0.f)
	{
		bBoostActive = false;
	}

	if (bBoostActive)
	{
		BoostFuel = FMath::Max(0.f, BoostFuel - BoostDrainRate * Dt);
		BoostRegenTimer = 0.f;
	}
	else
	{
		BoostRegenTimer += Dt;

		if (BoostRegenTimer >= BoostRegenDelay)
		{
			BoostFuel = FMath::Min(BoostFuelMax, BoostFuel + BoostRegenRate * Dt);
		}
	}

	return bBoostActive;
}

void UAirshipFlightComponent::ShapeControls(const FAirshipPilotInput& Controls, float Dt, float ForwardSpeed)
{
	using namespace AirshipFlightPrivate;

	const float RawSteer = Controls.GetSteer();
	bShBrake = Controls.IsBrake();
	bShAiming = Controls.IsAiming();
	bDrifting = bShBrake && FMath::Abs(RawSteer) > DriftSteerThreshold && ForwardSpeed > DriftMinSpeed;

	// Braking: the fans reverse while still moving forward and the throttle key is ignored. A drift (brake + steer)
	// keeps the throttle: it slides, it doesn't stop.
	float ThrottleTarget = Controls.GetThrottle();

	if (bShBrake && !bDrifting)
	{
		ThrottleTarget = ForwardSpeed > 100.f ? -BrakeReverseThrottle : 0.f;
	}

	ShThrottle = ApproachUpDown(ShThrottle, ThrottleTarget, Dt, ThrottleTauUp, ThrottleTauDown);
	ShBoost = Approach(ShBoost, Controls.IsBoost() ? 1.f : 0.f, Dt, Controls.IsBoost() ? BoostTauUp : BoostTauDown);
	ShLift = Approach(ShLift, Controls.GetLift(), Dt, LiftTau);
	ShSteer = Approach(ShSteer, RawSteer, Dt, SteerTau);
	ShStrafe = Approach(ShStrafe, Controls.GetStrafe(), Dt, StrafeTau);
}

void UAirshipFlightComponent::ComputeGimbals(float OutPitchDeg[Airship::NumPods], float OutRollDeg[Airship::NumPods]) const
{
	const float MaxDeg = FMath::Max(ThrusterGimbalMaxDeg, 0.f);
	const float Pitch = GimbalPitchPerThrottle * ShThrottle + GimbalPitchPerBoost * ShBoost - (bShBrake ? GimbalPitchPerBrake : 0.f);

	for (int32 Pod = 0; Pod < Airship::NumPods; ++Pod)
	{
		const float Roll = GimbalRollPerStrafe * ShStrafe + GimbalRollPerSteer * ShSteer * (Airship::IsFrontPod(Pod) ? 1.f : -1.f);
		float P = FMath::Clamp(Pitch, -MaxDeg, MaxDeg);
		float R = FMath::Clamp(Roll, -MaxDeg, MaxDeg);

		// Total lean inside the cone
		const float Total = FMath::Sqrt(P * P + R * R);

		if (Total > MaxDeg && Total > KINDA_SMALL_NUMBER)
		{
			P *= MaxDeg / Total;
			R *= MaxDeg / Total;
		}

		OutPitchDeg[Pod] = P;
		OutRollDeg[Pod] = R;
	}
}


// =============================================================================
// Update
// =============================================================================

void UAirshipFlightComponent::UpdateFlight(float DeltaSeconds)
{
	AAirshipPawn* Ship = GetShip();
	UPrimitiveComponent* Body = GetBody();
	const UWorld* World = GetWorld();

	if (!Ship || !Body || !World || DeltaSeconds <= 0.f)
	{
		return;
	}

	const bool bAuthority = Ship->HasAuthority();

	// The physics step of this frame (no substepping in this project): the loops see the time that is simulated
	const float MaxPhysicsDt = UPhysicsSettings::Get() ? UPhysicsSettings::Get()->MaxPhysicsDeltaTime : (1.f / 30.f);
	const float Dt = FMath::Min(DeltaSeconds, FMath::Max(MaxPhysicsDt, KINDA_SMALL_NUMBER));

	const FVector Velocity = Body->IsSimulatingPhysics() ? Body->GetPhysicsLinearVelocity() : Ship->GetVelocity();
	const float ForwardSpeed = static_cast<float>(FVector::DotProduct(Velocity, Body->GetForwardVector()));

	FAirshipPilotInput Controls = SelectControls();

	if (bAuthority)
	{
		Controls.SetButton(Airship::Button_Boost, bFlightEnabled && UpdateBoostServer(Controls.IsBoost(), Dt, Body));

		// The other machines shape the same controls for their cosmetics
		RepInput = Controls;
	}
	else if (Ship->IsLocallyControlled())
	{
		// The pilot's client: gate the boost by the replicated fuel, like the server does
		if (Controls.IsBoost() && !bLocalBoostActive && BoostFuel >= BoostMinFuelToStart)
		{
			bLocalBoostActive = true;
		}
		if (!Controls.IsBoost() || BoostFuel <= 0.f)
		{
			bLocalBoostActive = false;
		}
		Controls.SetButton(Airship::Button_Boost, bLocalBoostActive);
	}

	CurrentControls = Controls;
	// The simulated step, like the forces (every machine, so the cosmetics match)
	ShapeControls(Controls, Dt, ForwardSpeed);

	if (bAuthority && bFlightEnabled && Body->IsSimulatingPhysics())
	{
		if (bGroundTraces)
		{
			TraceGround(Body);
		}
		else
		{
			// Turned off live: no floor or cushion from old distances
			MinGroundDist = -1.f;

			for (float& Distance : GroundDist)
			{
				Distance = -1.f;
			}
		}

		ApplyForces(Body, Dt);
	}
	else if (!bFlightEnabled)
	{
		bHoldValid = false;
		bPodForceInitialized = false;
		DriftTime = 0.f;
	}

	UpdateCosmetic(ForwardSpeed, static_cast<float>(Velocity.Size()));
}

void UAirshipFlightComponent::TraceGround(UPrimitiveComponent* Body)
{
	const UWorld* World = GetWorld();
	const FTransform BodyTM = Body->GetComponentTransform();

	FCollisionQueryParams Params(SCENE_QUERY_STAT(AirshipGround), false, GetOwner());
	TArray<AActor*> Attached;
	GetOwner()->GetAttachedActors(Attached);
	Params.AddIgnoredActors(Attached);

	// The ground and the platforms, not the players walking below
	FCollisionObjectQueryParams Objects;
	Objects.AddObjectTypesToQuery(ECC_WorldStatic);
	Objects.AddObjectTypesToQuery(ECC_WorldDynamic);

	MinGroundDist = -1.f;

	for (int32 Pod = 0; Pod < Airship::NumPods; ++Pod)
	{
		// From the pod pivot (inside the hull pocket), measured from the nozzle exit below it
		const float Depth = PodNozzleDepth[Pod];
		const FVector Start = BodyTM.TransformPosition(PodLocal[Pod]);
		const FVector End = Start - FVector(0.0, 0.0, GroundTraceLength + Depth);
		FHitResult Hit;

		GroundDist[Pod] = World->LineTraceSingleByObjectType(Hit, Start, End, Objects, Params) ? FMath::Max(0.f, static_cast<float>(Hit.Distance) - Depth) : -1.f;

		if (GroundDist[Pod] >= 0.f && (MinGroundDist < 0.f || GroundDist[Pod] < MinGroundDist))
		{
			MinGroundDist = GroundDist[Pod];
		}

		if (AirshipFlightPrivate::CVarDebugForces.GetValueOnGameThread() > 0)
		{
			const FVector LineEnd = GroundDist[Pod] >= 0.f ? FVector(Hit.ImpactPoint) : End;
			DrawDebugLine(World, Start, LineEnd, GroundDist[Pod] >= 0.f ? FColor::Orange : FColor(80, 80, 80), false, -1.f, 0, 4.f);
		}
	}
}

void UAirshipFlightComponent::ApplyForces(UPrimitiveComponent* Body, float Dt)
{
	using namespace AirshipFlightPrivate;

	const UWorld* World = GetWorld();
	const FTransform BodyTM = Body->GetComponentTransform();
	const FQuat Q = BodyTM.GetRotation();
	const FVector Fwd = Q.GetForwardVector();
	const FVector Right = Q.GetRightVector();
	const FVector Up = Q.GetUpVector();

	const float Mass = Body->GetMass();
	const float Gravity = FMath::Max(-World->GetGravityZ(), 1.f);
	const float Weight = Mass * Gravity;

	if (Mass <= KINDA_SMALL_NUMBER)
	{
		return;
	}

	const FVector V = Body->GetPhysicsLinearVelocity();
	const FVector AngVel = Body->GetPhysicsAngularVelocityInRadians();
	const FVector COMLocal = BodyTM.InverseTransformPosition(Body->GetCenterOfMass());
	const FVector Vb = Q.UnrotateVector(V);
	const float Vf = static_cast<float>(Vb.X);
	const float Vl = static_cast<float>(Vb.Y);
	const float Vz = static_cast<float>(V.Z);
	const float Z = static_cast<float>(BodyTM.GetLocation().Z);

	// Local principal inertia (kg cm^2), the loops scale with it
	const FVector Inertia = Body->GetInertiaTensor();

	const float Boost = ShBoost;
	const float Steer = ShSteer;
	const float Strafe = ShStrafe;
	const float Lift = ShLift;
	const float Throttle = ShThrottle;

	// ---- Forward command (also sets the pitch lean) -------------------------------------------------------------
	// Aura.Airship.Set skips the ClampMin metadata: keep every divisor above zero
	const float AFanEff = FMath::Lerp(AFan, AFanBoost, Boost);
	const float VTopEff = FMath::Max(FMath::Lerp(VTop, VTopBoost, Boost), 1.f);
	float AFanCmd = 0.f;

	if (Throttle >= 0.f)
	{
		AFanCmd = AFanEff * Throttle * FMath::Max(0.f, 1.f - FMath::Pow(FMath::Max(Vf, 0.f) / VTopEff, ThrustFadeExponent));
	}
	else
	{
		// Braking reverses the fans at full power (48 -> 0 m/s in about 2 s); S alone backs up gently
		const float ARev = (bShBrake && !bDrifting) ? AFan : AFanRev;
		AFanCmd = ARev * Throttle * FMath::Max(0.f, 1.f - FMath::Square(FMath::Max(-Vf, 0.f) / FMath::Max(VTopRev, 1.f)));
	}

	const float ADrag = -(DragC1 * Vf + DragC2 * Vf * FMath::Abs(Vf));
	const float ABrake = bShBrake ? -Kbrake * Vf * (bDrifting ? DriftBrakeScale : 1.f) : 0.f;
	const float ACmd = AFanCmd + ADrag + ABrake;

	// ---- Vertical: speed command, altitude hold, floor, ceiling --------------------------------------------------
	float VzCmd = 0.f;
	const bool bBrakePressed = bShBrake && !bBrakeWasHeld;
	bBrakeWasHeld = bShBrake;

	if (FMath::Abs(Lift) >= LiftDeadZone)
	{
		VzCmd = Lift * (Lift > 0.f ? ClimbRate : DescendRate);
		bHoldValid = false;
	}
	else
	{
		if (!bHoldValid)
		{
			HoldZ = Z + Vz * HoldCaptureLead;
			bHoldValid = true;
		}

		// Brake = hover here
		if (bBrakePressed)
		{
			HoldZ = Z;
		}

		VzCmd = FMath::Clamp(Kz * (HoldZ - Z), -HoldMaxSpeed, HoldMaxSpeed);
	}

	if (MinClearance > 0.f && MinGroundDist >= 0.f)
	{
		VzCmd = FMath::Max(VzCmd, Kfloor * (MinClearance - MinGroundDist));

		// Coming down: slow in time (at most FloorBrakeAccel) so the nozzles stop above the ground
		if (FloorBrakeAccel > 0.f)
		{
			VzCmd = FMath::Max(VzCmd, -FMath::Sqrt(2.f * FloorBrakeAccel * FMath::Max(MinGroundDist - MinClearance, 0.f)));
		}
	}

	if (bUseCeiling)
	{
		VzCmd = FMath::Min(VzCmd, Kceil * (CeilingZ - Z));
	}

	const float FvWorld = FMath::Clamp(Mass * (Gravity + Kvz * (VzCmd - Vz)), CollectiveMin * Weight, CollectiveMax * Weight);
	const float FvBody = FvWorld / FMath::Max(0.5f, static_cast<float>(Up.Z));

	// ---- Attitude: lean targets, quaternion error, PD --------------------------------------------------------------
	const float BankMax = bDrifting ? BankMaxDriftDeg : FMath::Lerp(BankMaxDeg, BankMaxBoostDeg, Boost);
	const float BankDeg = BankMax * Steer * FMath::Clamp(Vf / FMath::Max(BankFullSpeed, 1.f), BankMinFraction, 1.f) + StrafeBankDeg * Strafe;
	const float PitchDeg = FMath::Clamp(-PitchPerG * ACmd / Gravity, PitchMinDeg, PitchMaxDeg) - BoostPitchDeg * Boost + LiftPitchDeg * Lift;

	const FRotator Current = Q.Rotator();
	const FQuat QDesired = FRotator(PitchDeg, Current.Yaw, BankDeg).Quaternion();
	FQuat QError = QDesired * Q.Inverse();

	if (QError.W < 0.f)
	{
		QError = FQuat(-QError.X, -QError.Y, -QError.Z, -QError.W);
	}

	FVector ErrorAxis = FVector::UpVector;
	double ErrorAngle = 0.0;
	QError.ToAxisAndAngle(ErrorAxis, ErrorAngle);
	const FVector Error = ErrorAxis * ErrorAngle;

	// The D terms damp the tilt rate only: in a level banked turn the yaw rate (world Z) has parts along Fwd / Right
	// that are no error (damping them dips the nose and flattens the bank)
	const FVector TiltRate = AngVel - FVector::UpVector * AngVel.Z;
	const FVector AlphaTilt =
		Fwd * (KpRoll * FVector::DotProduct(Error, Fwd) - KdRoll * FVector::DotProduct(TiltRate, Fwd)) +
		Right * (KpPitch * FVector::DotProduct(Error, Right) - KdPitch * FVector::DotProduct(TiltRate, Right));

	const FVector AlphaTiltBody = Q.UnrotateVector(AlphaTilt);
	const double TauX = Inertia.X * AlphaTiltBody.X;
	const double TauY = Inertia.Y * AlphaTiltBody.Y;

	// ---- Thruster mixing: collective + roll/pitch torque over 4 pods ---------------------------------------------
	float GimbalPitch[Airship::NumPods];
	float GimbalRoll[Airship::NumPods];
	ComputeGimbals(GimbalPitch, GimbalRoll);

	FVector PodDir[Airship::NumPods];
	FVector PodArm[Airship::NumPods];
	double A[3][Airship::NumPods];

	for (int32 Pod = 0; Pod < Airship::NumPods; ++Pod)
	{
		PodDir[Pod] = FVector(FMath::Tan(FMath::DegreesToRadians(GimbalPitch[Pod])), FMath::Tan(FMath::DegreesToRadians(GimbalRoll[Pod])), 1.0).GetSafeNormal();
		PodArm[Pod] = PodLocal[Pod] - COMLocal;
		const FVector TorquePerForce = FVector::CrossProduct(PodArm[Pod], PodDir[Pod]);
		A[0][Pod] = PodDir[Pod].Z;
		A[1][Pod] = TorquePerForce.X;
		A[2][Pod] = TorquePerForce.Y;
	}

	double M[3][3];

	for (int32 Row = 0; Row < 3; ++Row)
	{
		for (int32 Col = 0; Col < 3; ++Col)
		{
			double Sum = 0.0;
			for (int32 Pod = 0; Pod < Airship::NumPods; ++Pod)
			{
				Sum += A[Row][Pod] * A[Col][Pod];
			}
			M[Row][Col] = Sum;
		}
	}

	double Collective[Airship::NumPods] = {};
	double Attitude[Airship::NumPods] = {};
	const double BCollective[3] = { FvBody, 0.0, 0.0 };
	const double BAttitude[3] = { 0.0, TauX, TauY };
	double YC[3];
	double YA[3];

	if (Solve3x3(M, BCollective, YC) && Solve3x3(M, BAttitude, YA))
	{
		for (int32 Pod = 0; Pod < Airship::NumPods; ++Pod)
		{
			Collective[Pod] = A[0][Pod] * YC[0] + A[1][Pod] * YC[1] + A[2][Pod] * YC[2];
			Attitude[Pod] = A[0][Pod] * YA[0] + A[1][Pod] * YA[1] + A[2][Pod] * YA[2];
		}
	}
	else
	{
		// Degenerate layout (all pods on one line): even shares, the stabiliser does the attitude
		for (int32 Pod = 0; Pod < Airship::NumPods; ++Pod)
		{
			Collective[Pod] = FvBody / Airship::NumPods;
		}
	}

	const double FMin = PodForceMin * Weight;
	const double FMax = FMath::Max(PodForceMax, PodForceMin) * Weight;

	// Largest share of the attitude part the pods can deliver inside their range
	double S = 1.0;

	for (int32 Pod = 0; Pod < Airship::NumPods; ++Pod)
	{
		if (Attitude[Pod] > 1e-6)
		{
			S = FMath::Min(S, (FMax - Collective[Pod]) / Attitude[Pod]);
		}
		else if (Attitude[Pod] < -1e-6)
		{
			S = FMath::Min(S, (FMin - Collective[Pod]) / Attitude[Pod]);
		}
	}
	S = FMath::Clamp(S, 0.0, 1.0);

	if (!bPodForceInitialized)
	{
		// Spawned hovering: no drop while the pods spool up
		for (int32 Pod = 0; Pod < Airship::NumPods; ++Pod)
		{
			PodForce[Pod] = static_cast<float>(FMath::Clamp(Collective[Pod], FMin, FMax));
		}
		bPodForceInitialized = true;
	}

	FVector PodForceWorld[Airship::NumPods];
	FVector PodSumBody = FVector::ZeroVector;
	double PodTauZ = 0.0;

	for (int32 Pod = 0; Pod < Airship::NumPods; ++Pod)
	{
		const float Target = static_cast<float>(FMath::Clamp(Collective[Pod] + S * Attitude[Pod], FMin, FMax));
		PodForce[Pod] = Approach(PodForce[Pod], Target, Dt, Target > PodForce[Pod] ? PodForceTauUp : PodForceTauDown);

		// Cushion near the ground (outside the loops)
		float Cushion = 0.f;

		if (GroundEffectStrength > 0.f && GroundDist[Pod] >= 0.f && GroundDist[Pod] < GroundTraceLength)
		{
			Cushion = 0.25f * Weight * GroundEffectStrength * FMath::Square(1.f - GroundDist[Pod] / FMath::Max(GroundTraceLength, 1.f));
		}

		const FVector ForceBody = PodDir[Pod] * (PodForce[Pod] + Cushion);
		PodSumBody += ForceBody;
		PodTauZ += FVector::CrossProduct(PodArm[Pod], ForceBody).Z;
		PodForceWorld[Pod] = Q.RotateVector(ForceBody);
	}

	// What the pods couldn't deliver goes to the hidden stabiliser, capped
	FVector AlphaGyroTilt = AlphaTilt * (1.0 - S);
	AlphaGyroTilt = AlphaGyroTilt.GetClampedToMaxSize(GyroTiltMax);

	// ---- Yaw command -------------------------------------------------------------------------------------------------
	const float AbsVf = FMath::Abs(Vf);
	float RmaxDeg = AbsVf <= YawRateMidSpeed
		? FMath::Lerp(YawRateAtRest, YawRateAtMid, AbsVf / FMath::Max(YawRateMidSpeed, 1.f))
		: FMath::Lerp(YawRateAtMid, YawRateAtTop, FMath::Clamp((AbsVf - YawRateMidSpeed) / FMath::Max(YawRateTopSpeed - YawRateMidSpeed, 1.f), 0.f, 1.f));
	RmaxDeg = bDrifting ? YawRateDrift : FMath::Lerp(RmaxDeg, YawRateBoost, Boost);

	const float YawRateCmd = Steer * FMath::DegreesToRadians(RmaxDeg);
	const float YawRate = static_cast<float>(AngVel.Z);
	const float AlphaZ = FMath::Clamp(Kr * (YawRateCmd - YawRate) + AngularDamping * YawRateCmd, -AlphaYawMax, AlphaYawMax);
	const double TauZ = Inertia.Z * AlphaZ;

	// ---- Fans: forward thrust + differential for yaw -----------------------------------------------------------------
	const float Psi = FMath::DegreesToRadians(-FanYawMaxDeg * Steer);
	const FVector FanDir(1.0, FMath::Tan(Psi), 0.0);
	const double KL = FVector::CrossProduct(FanLocal[0] - COMLocal, FanDir).Z;
	const double KR = FVector::CrossProduct(FanLocal[1] - COMLocal, FanDir).Z;
	const double KDiff = 0.5 * (KL - KR);

	const double FanMaxForce = FMath::Lerp(FanMax, FanMaxBoost, Boost) * Weight;
	const double Total = FMath::Clamp(Mass * AFanCmd - PodSumBody.X, -2.0 * FanMaxForce, 2.0 * FanMaxForce);

	// Rudder: inside the yaw loop, it gives what the pods and the fan housings don't (never more), up to an authority
	// that grows with forward speed squared. Open loop it overpowered the gyro on a boost turn and spun the ship out.
	const float RudderCap = FMath::Min(RudderAuthority * FMath::Square(Vf / FMath::Max(RudderRefSpeed, 1.f)), RudderMaxAlpha) * FMath::Abs(Steer);
	const float RudderAlpha = Inertia.Z > KINDA_SMALL_NUMBER
		? FMath::Clamp(static_cast<float>(AlphaZ - (PodTauZ + 0.5 * Total * (KL + KR)) / Inertia.Z), -RudderCap, RudderCap)
		: 0.f;

	const double TauKnown = PodTauZ + 0.5 * Total * (KL + KR) + Inertia.Z * RudderAlpha;
	const double DMax = FMath::Max(0.0, 2.0 * FanMaxForce - FMath::Abs(Total));
	const double D = FMath::Abs(KDiff) > 1.0 ? FMath::Clamp((TauZ - TauKnown) / KDiff, -DMax, DMax) : 0.0;
	const double FanForce[Airship::NumFans] = { 0.5 * Total + 0.5 * D, 0.5 * Total - 0.5 * D };
	const float AlphaGyroZ = Inertia.Z > KINDA_SMALL_NUMBER ? FMath::Clamp(static_cast<float>((TauZ - TauKnown - KDiff * D) / Inertia.Z), -GyroYawMax, GyroYawMax) : 0.f;

	// ---- Lateral grip, strafe, drift ----------------------------------------------------------------------------------
	const float Klat = bDrifting ? DriftKlat : FMath::Lerp(GripKlat, BoostKlat, Boost);
	const float ALatMax = (bDrifting ? DriftALatMaxG : FMath::Lerp(GripALatMaxG, BoostALatMaxG, Boost)) * Gravity;
	const float Eta = bDrifting ? DriftEta : FMath::Lerp(GripEta, BoostEta, Boost);

	const float ALatCmd = FMath::Clamp(Klat * (Strafe * StrafeSpeed - Vl), -ALatMax, ALatMax);
	const float ALatPhys = static_cast<float>((PodSumBody.Y + (FanForce[0] + FanForce[1]) * FanDir.Y) / Mass);
	const float AGrip = ALatCmd - ALatPhys;

	// Turning carves: part of the scrubbed side speed comes back as forward speed
	const float ARedirect = (Vf > RedirectMinSpeed && AGrip * Vl < 0.f) ? Eta * FMath::Abs(AGrip) : 0.f;

	// Drift boost when a long drift ends
	if (bDrifting)
	{
		DriftTime += Dt;
	}
	else
	{
		if (DriftTime >= DriftBoostMinTime && DriftBoostDV > 0.f)
		{
			const FVector KickDV = Fwd * DriftBoostDV;
			Body->AddImpulse(KickDV, NAME_None, true);

			// The ship's own speed for the impact cap (DriftBoostDV is more than ImpactMaxSpeedGain)
			if (AAirshipPawn* Ship = GetShip())
			{
				Ship->NoteFlightKick(KickDV);
			}
		}
		DriftTime = 0.f;
	}

	// ---- Wind ---------------------------------------------------------------------------------------------------------
	const float WindScale = 1.f - FMath::Clamp(static_cast<float>(V.Size()) / FMath::Max(WindFadeSpeed, 1.f), 0.f, 1.f);
	const float Time = static_cast<float>(World->GetTimeSeconds());
	// Different phase offsets per channel (and per ship), so they don't move together
	const float Seed = static_cast<float>(GetOwner()->GetUniqueID() % 97) * 3.7f;
	const float WindLat = WindLateralAccel * WindScale * FMath::PerlinNoise1D(Time * WindLateralFrequency + Seed);
	const float WindRoll = WindRollAccel * WindScale * FMath::PerlinNoise1D(Time * WindRollFrequency + Seed + 17.3f);
	const float WindPitch = WindPitchAccel * WindScale * FMath::PerlinNoise1D(Time * WindPitchFrequency + Seed + 41.9f);

	// ---- Apply ---------------------------------------------------------------------------------------------------------
	for (int32 Pod = 0; Pod < Airship::NumPods; ++Pod)
	{
		Body->AddForceAtLocation(PodForceWorld[Pod], BodyTM.TransformPosition(PodLocal[Pod]));
	}

	FVector FanForceWorld[Airship::NumFans];

	for (int32 Fan = 0; Fan < Airship::NumFans; ++Fan)
	{
		FanForceWorld[Fan] = Q.RotateVector(FanDir * FanForce[Fan]);
		Body->AddForceAtLocation(FanForceWorld[Fan], BodyTM.TransformPosition(FanLocal[Fan]));
	}

	FVector ACom = Right * (AGrip + WindLat) + Fwd * (ADrag + ABrake + ARedirect);
	const float SpeedNow = static_cast<float>(V.Size());

	if (SpeedNow > HardSpeedCap)
	{
		ACom -= V.GetSafeNormal() * (HardCapGain * (SpeedNow - HardSpeedCap));
	}

	const FVector AlphaCom = Up * (RudderAlpha + AlphaGyroZ) + AlphaGyroTilt + Fwd * WindRoll + Right * WindPitch;

	Body->AddForce(ACom, NAME_None, true);
	Body->AddTorqueInRadians(AlphaCom, NAME_None, true);

	// ---- Debug ---------------------------------------------------------------------------------------------------------
	if (CVarDebugForces.GetValueOnGameThread() > 0)
	{
		const float Scale = 2000.f / Weight;
		const FVector COMWorld = Body->GetCenterOfMass();

		for (int32 Pod = 0; Pod < Airship::NumPods; ++Pod)
		{
			const FVector P = BodyTM.TransformPosition(PodLocal[Pod]);
			DrawDebugDirectionalArrow(World, P, P - PodForceWorld[Pod] * Scale, 200.f, FColor::Yellow, false, -1.f, 0, 12.f);
		}

		for (int32 Fan = 0; Fan < Airship::NumFans; ++Fan)
		{
			const FVector P = BodyTM.TransformPosition(FanLocal[Fan]);
			DrawDebugDirectionalArrow(World, P, P - FanForceWorld[Fan] * Scale, 200.f, FColor::Cyan, false, -1.f, 0, 12.f);
		}

		DrawDebugSphere(World, COMWorld, 120.f, 12, FColor::Red, false, -1.f, 0, 6.f);
		DrawDebugDirectionalArrow(World, COMWorld, COMWorld + ACom * 2.f, 150.f, FColor::Green, false, -1.f, 0, 10.f);
		DrawDebugDirectionalArrow(World, COMWorld, COMWorld + AlphaCom * 3000.f, 150.f, FColor::Magenta, false, -1.f, 0, 10.f);
		DrawDebugDirectionalArrow(World, COMWorld, COMWorld + V, 150.f, FColor::White, false, -1.f, 0, 8.f);

		if (bHoldValid)
		{
			const FVector HoldPoint(COMWorld.X, COMWorld.Y, HoldZ);
			DrawDebugLine(World, HoldPoint - Right * 1500.f, HoldPoint + Right * 1500.f, FColor::Blue, false, -1.f, 0, 10.f);
		}
	}
}

void UAirshipFlightComponent::UpdateCosmetic(float ForwardSpeed, float Speed)
{
	FAirshipCosmeticState& C = Cosmetic;

	C.Throttle = ShThrottle;
	C.Steer = ShSteer;
	C.Lift = ShLift;
	C.Strafe = ShStrafe;
	C.Boost = ShBoost;
	C.bBrake = bShBrake;
	C.bAiming = bShAiming;
	C.ForwardSpeed = ForwardSpeed;
	C.Speed = Speed;

	ComputeGimbals(C.PodGimbalPitchDeg, C.PodGimbalRollDeg);

	for (int32 Pod = 0; Pod < Airship::NumPods; ++Pod)
	{
		// The pods on the outside of the turn lift the low side (left pods for a right bank)
		const float Bank = PodAlphaPerSteer * ShSteer * (Airship::IsLeftPod(Pod) ? 1.f : -1.f);
		C.PodThrustAlpha[Pod] = bFlightEnabled
			? FMath::Clamp(1.f + PodAlphaPerLift * ShLift + PodAlphaPerBoost * ShBoost + PodAlphaPerThrottle * FMath::Abs(ShThrottle) + Bank, 0.f, 1.5f)
			: 0.f;
	}

	C.FanYawDeg = -FanYawMaxDeg * ShSteer;

	// Fan thrust as the forces see it, normalized: forward part with the speed fade, differential for the turn
	const float VTopEff = FMath::Max(FMath::Lerp(VTop, VTopBoost, ShBoost), 1.f);
	const float Forward = ShThrottle >= 0.f
		? ShThrottle * FMath::Max(0.f, 1.f - FMath::Pow(FMath::Max(ForwardSpeed, 0.f) / VTopEff, ThrustFadeExponent))
		: ShThrottle;
	const float Diff = ShSteer * FanSteerShare * (1.f - 0.5f * FMath::Abs(Forward));

	C.FanThrust[0] = bFlightEnabled ? FMath::Clamp(Forward + Diff, -1.f, 1.f) : 0.f;
	C.FanThrust[1] = bFlightEnabled ? FMath::Clamp(Forward - Diff, -1.f, 1.f) : 0.f;
}

void UAirshipFlightComponent::FillTelemetry(FAirshipFlightTelemetry& Out) const
{
	const UPrimitiveComponent* Body = GetBody();

	if (!Body)
	{
		return;
	}

	const FTransform BodyTM = Body->GetComponentTransform();
	const FQuat Q = BodyTM.GetRotation();
	const FVector V = Body->IsSimulatingPhysics() ? Body->GetPhysicsLinearVelocity() : Body->GetComponentVelocity();
	const FVector AngVel = Body->IsSimulatingPhysics() ? Body->GetPhysicsAngularVelocityInRadians() : FVector::ZeroVector;
	const FVector Vb = Q.UnrotateVector(V);
	const FRotator Rot = Q.Rotator();

	Out.SpeedMS = static_cast<float>(V.Size()) * 0.01f;
	Out.ForwardSpeedMS = static_cast<float>(Vb.X) * 0.01f;
	Out.LateralSpeedMS = static_cast<float>(Vb.Y) * 0.01f;
	Out.VerticalSpeedMS = static_cast<float>(V.Z) * 0.01f;
	Out.AltitudeM = static_cast<float>(BodyTM.GetLocation().Z) * 0.01f;
	Out.GroundClearanceM = MinGroundDist >= 0.f ? MinGroundDist * 0.01f : -1.f;
	Out.YawRateDegS = FMath::RadiansToDegrees(static_cast<float>(AngVel.Z));
	Out.RollDeg = static_cast<float>(Rot.Roll);
	Out.PitchDeg = static_cast<float>(Rot.Pitch);
	Out.YawDeg = static_cast<float>(Rot.Yaw);
	Out.HoldAltitudeM = bHoldValid ? HoldZ * 0.01f : Out.AltitudeM;
	Out.BoostFuel = BoostFuel;
	Out.MassKg = Body->IsSimulatingPhysics() ? Body->GetMass() : 0.f;
	Out.Throttle = ShThrottle;
	Out.Steer = ShSteer;
	Out.Lift = ShLift;
	Out.Strafe = ShStrafe;
	Out.Boost = ShBoost;
	Out.bBraking = bShBrake;
	Out.bDrifting = bDrifting;
}
