// Fill out your copyright notice in the Description page of Project Settings.


#include "Airship/AirshipFlightComponent.h"

#include "Airship/AirshipCannonball.h"
#include "Airship/AirshipPawn.h"
#include "Airship/AirshipSettings.h"
#include "Components/PrimitiveComponent.h"
#include "DrawDebugHelpers.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "HAL/IConsoleManager.h"
#include "Match/MyMatchSettings.h"
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

	/** -180..180 (float). */
	float WrapDeg(float AngleDeg)
	{
		return static_cast<float>(FRotator::NormalizeAxis(static_cast<double>(AngleDeg)));
	}

	/**
	 * Round 2 PR B (lane assist): the controls drive the ship. The drive-intent bit (the pilot's machine: Point & Fly's
	 * keys and steering camera), or any drive axis past 0.05, boost, brake, a Galleon order other than STOP. Not the
	 * heading target, and in Point & Fly not the steer: there both come from the camera's heading loop (also in its
	 * parked free look, which holds a heading), which the bit already reports when it steers.
	 */
	bool IsDriveInput(const FAirshipPilotInput& Controls, EAirshipControlScheme Scheme)
	{
		constexpr float Dead = 0.05f;
		const bool bThrottle = Scheme == EAirshipControlScheme::Galleon
			? AirshipGalleon::ThrottleToNotch(Controls.Throttle) != AirshipGalleon::Stop
			: FMath::Abs(Controls.GetThrottle()) > Dead;
		const bool bSteer = Scheme != EAirshipControlScheme::PointFly && FMath::Abs(Controls.GetSteer()) > Dead;

		return Controls.HasButton(Airship::Button_DriveIntent) || bThrottle || bSteer || FMath::Abs(Controls.GetLift()) > Dead
			|| FMath::Abs(Controls.GetStrafe()) > Dead || Controls.IsBoost() || Controls.IsBrake();
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
// Control schemes
// =============================================================================

void UAirshipFlightComponent::SetActiveScheme(EAirshipControlScheme InScheme)
{
	ActiveScheme = InScheme;
	ResetSchemeState(true);
}

void UAirshipFlightComponent::ResetSchemeState(bool bSchemeSwitch)
{
	// Galleon: the order the controls carry now is no change (no pulse); a boost held through the reset is no start
	GalleonLastNotch = AirshipGalleon::ThrottleToNotch(CurrentControls.Throttle);
	GalleonOrderPulse01 = 0.f;
	GalleonBoostPulse01 = 0.f;
	bGalleonPrevBoost = CurrentControls.IsBoost();

	// Sky Racer: a drift in progress is dropped without a turbo (SkyTurboEventCount keeps counting: the pawn and the HUD
	// detect releases by its change)
	SkyClock = 0.0;
	SkyDriftDir = 0;
	SkyCharge = 0.f;
	SkyDriftTime = 0.f;
	SkyChain = 0;
	SkyLastReleaseTime = -1000.0;
	SkyTurboTier = 0;
	SkyTurboLeft = 0.f;
	SkyTurboTotal = 1.f;
	SkyTurboEvent = 0;
	SkyTurboChain = 0;
	SkyExitLeft = 0.f;
	SkySBrake = 0.f;
	SkyBoostStartTime = -1000.0;
	SkyLocalBoostStartTime = -1000.0;

	// Point & Fly
	ServerHeadingLoop = FPointFlyLoopState();
	LastGripAccelZ = 0.f;

	if (bSchemeSwitch)
	{
		DriftTime = 0.f;
	}
}

float UAirshipFlightComponent::GetYawRateMaxDeg(float ForwardSpeed, float Boost, bool bDrift) const
{
	const float AbsVf = FMath::Abs(ForwardSpeed);
	const float TableDeg = AbsVf <= YawRateMidSpeed
		? FMath::Lerp(YawRateAtRest, YawRateAtMid, AbsVf / FMath::Max(YawRateMidSpeed, 1.f))
		: FMath::Lerp(YawRateAtMid, YawRateAtTop, FMath::Clamp((AbsVf - YawRateMidSpeed) / FMath::Max(YawRateTopSpeed - YawRateMidSpeed, 1.f), 0.f, 1.f));
	return bDrift ? YawRateDrift : FMath::Lerp(TableDeg, YawRateBoost, Boost);
}

int32 UAirshipFlightComponent::GetGalleonNotch() const
{
	return AirshipGalleon::ThrottleToNotch(CurrentControls.Throttle);
}

float UAirshipFlightComponent::GetPilotYawRateCmdDeg() const
{
	if (ActiveScheme == EAirshipControlScheme::SkyRacer && SkyDriftDir != 0)
	{
		// The drift's path rate (the steer sets it)
		const float Dir = static_cast<float>(SkyDriftDir);
		return Dir * FMath::Lerp(SkyDriftPathRateMinDeg, SkyDriftPathRateMaxDeg, 0.5f * (FMath::Clamp(ShSteer * Dir, -1.f, 1.f) + 1.f));
	}

	return ShSteer * GetYawRateMaxDeg(Cosmetic.ForwardSpeed, ShBoost, false) * (bShGunDeck ? GunDeckYawScale : 1.f);
}

float UAirshipFlightComponent::ComputeHeadingSteer(float TargetYawDeg, float YawDeg, float YawRateDegS, float ForwardSpeed, float Boost, bool bBrake, FPointFlyLoopState& State) const
{
	using namespace AirshipFlightPrivate;

	const float Error = WrapDeg(TargetYawDeg - YawDeg);

	// Drift: brake + a big turn at speed (hysteresis). ShapeControls sees it as |Steer| above the drift threshold.
	if (!bBrake || ForwardSpeed <= DriftMinSpeed)
	{
		State.bDrift = false;
	}
	else if (!State.bDrift && FMath::Abs(Error) >= PFDriftStartDeg)
	{
		State.bDrift = true;
	}
	else if (State.bDrift && FMath::Abs(Error) < PFDriftEndDeg)
	{
		State.bDrift = false;
	}

	// Turn at full rate, brake onto the target (sqrt profile), on the error the loop will see after its own lag
	const float RateMaxDeg = FMath::Max(1.f, GetYawRateMaxDeg(ForwardSpeed, Boost, State.bDrift));
	const float Predicted = Error - YawRateDegS * PFHeadingLead;
	const float DecelDeg = FMath::Max(0.f, PFHeadingDecelDeg * (State.bDrift ? PFDriftDecelScale : 1.f));
	float Magnitude = FMath::Min(RateMaxDeg, FMath::Min(PFHeadingKp * FMath::Abs(Predicted), FMath::Sqrt(2.f * DecelDeg * FMath::Abs(Predicted))));

	// Wheel and fans rest on the target
	if (FMath::Abs(Error) < PFHeadingDeadbandDeg && FMath::Abs(YawRateDegS) < 2.f)
	{
		Magnitude = 0.f;
	}

	float SteerOut = (Predicted < 0.f ? -Magnitude : Magnitude) / RateMaxDeg;

	if (State.bDrift)
	{
		// Keep the slide alive until the end of the turn
		const float Dir = FMath::Abs(SteerOut) < 1e-6f ? (Error < 0.f ? -1.f : 1.f) : (SteerOut < 0.f ? -1.f : 1.f);
		SteerOut = Dir * FMath::Max(FMath::Abs(SteerOut), DriftSteerThreshold + 0.05f);
	}
	else if (bBrake && ForwardSpeed > DriftMinSpeed)
	{
		// Braking without a drift: stay under the drift threshold
		SteerOut = FMath::Clamp(SteerOut, -(DriftSteerThreshold - 0.02f), DriftSteerThreshold - 0.02f);
	}

	return FMath::Clamp(SteerOut, -1.f, 1.f);
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
		LastGoodServerInput = Input;
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
	// The drift bit is the server's own (an unpiloted ship's neutral controls), never a pilot's
	ServerInput.SetButton(Airship::Button_Drift, false);
	LastGoodServerInput = ServerInput;
	bHasServerInput = true;
	LastServerInputTime = Now;
}

void UAirshipFlightComponent::ResetInput()
{
	ServerInput = FAirshipPilotInput();
	LocalInput = FAirshipPilotInput();
	LastSentInput = FAirshipPilotInput();
	LastGoodServerInput = FAirshipPilotInput();
	bHasServerInput = false;

	// A new pilot (or none) starts the schemes' runtime state fresh (the shaped controls and the hold stay)
	ResetSchemeState(false);
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

		if (bFresh && Ship->GetController())
		{
			return ServerInput;
		}

		// Galleon, a pilot gone quiet: the engine room keeps the last order (a network hiccup costs the helm, not a
		// slow-down); the helm, lift, sidle and buttons go neutral
		if (ActiveScheme == EAirshipControlScheme::Galleon && Ship->GetController())
		{
			FAirshipPilotInput Held = LastGoodServerInput;
			Held.Steer = 0;
			Held.Lift = 0;
			Held.Strafe = 0;
			Held.SetButton(Airship::Button_Boost, false);
			Held.SetButton(Airship::Button_Brake, false);
			Held.SetButton(Airship::Button_Aim, false);
			Held.SetButton(Airship::Button_Stations, false);
			// A quiet pilot's held Fire doesn't keep the turrets firing
			Held.SetButton(Airship::Button_FireHeld, false);
			Held.HeadingTarget = 0;
			return Held;
		}

		// No pilot, or the pilot went quiet: neutral controls (the ship holds its altitude). An unpiloted cruise (a drift,
		// or a team ship on its lane) says so in them: RepInput carries the bit to every machine, so they all shape the
		// same cosmetics (Galleon: no STOP reverse)
		FAirshipPilotInput Neutral;
		Neutral.SetButton(Airship::Button_Drift, UnpilotedTarget.Mode == EAirshipUnpilotedMode::Drift || UnpilotedTarget.Mode == EAirshipUnpilotedMode::Lane);
		return Neutral;
	}

	return RepInput;
}

bool UAirshipFlightComponent::UpdateBoostServer(bool bWantBoost, float Dt, UPrimitiveComponent* Body)
{
	const double Now = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0;

	// Sky Racer: every press gives at least SkyBoostMinBurst of boost
	if (ActiveScheme == EAirshipControlScheme::SkyRacer && SkyBoostMinBurst > 0.f && bBoostActive && Now - SkyBoostStartTime < SkyBoostMinBurst)
	{
		bWantBoost = true;
	}

	const bool bWasBoostActive = bBoostActive;

	if (bWantBoost && !bBoostActive && BoostFuel >= BoostMinFuelToStart)
	{
		bBoostActive = true;

		// Every start costs fuel and the kick has a cooldown: tapping Shift is no cheaper than holding it
		BoostFuel = FMath::Max(0.f, BoostFuel - BoostStartFuelCost);

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

	if (bBoostActive && !bWasBoostActive)
	{
		SkyBoostStartTime = Now;
	}

	return bBoostActive;
}

void UAirshipFlightComponent::ShapeControls(const FAirshipPilotInput& Controls, float Dt, float ForwardSpeed)
{
	using namespace AirshipFlightPrivate;

	const float RawSteer = Controls.GetSteer();
	bShAiming = Controls.IsAiming();
	bShGunDeck = ActiveScheme == EAirshipControlScheme::Galleon ? Controls.HasButton(Airship::Button_Stations) : bShAiming;

	float ThrottleTarget = Controls.GetThrottle();
	ShBrakeAmount = 0.f;

	switch (ActiveScheme)
	{
	case EAirshipControlScheme::Galleon:
		ShapeGalleon(Controls, Dt, ForwardSpeed, RawSteer, ThrottleTarget);
		break;

	case EAirshipControlScheme::SkyRacer:
		ShapeSkyRacer(Controls, Dt, ForwardSpeed, RawSteer, ThrottleTarget);
		break;

	default:
		// Classic, Point & Fly (v1). Braking: the fans reverse while still moving forward and the throttle key is
		// ignored. A drift (brake + steer) keeps the throttle: it slides, it doesn't stop.
		bShBrake = Controls.IsBrake();
		bDrifting = bShBrake && FMath::Abs(RawSteer) > DriftSteerThreshold && ForwardSpeed > DriftMinSpeed;
		ShBrakeAmount = bShBrake ? 1.f : 0.f;

		if (bShBrake && !bDrifting)
		{
			// Base fix 4c-2: the reverse fades out below BrakeFadeSpeed (no back-up after the stop); 0 = v1
			ThrottleTarget = BrakeFadeSpeed > 0.f
				? -BrakeReverseThrottle * FMath::Clamp(ForwardSpeed / BrakeFadeSpeed, 0.f, 1.f)
				: (ForwardSpeed > 100.f ? -BrakeReverseThrottle : 0.f);
		}
		break;
	}

	ShThrottle = ApproachUpDown(ShThrottle, ThrottleTarget, Dt, ThrottleTauUp, ThrottleTauDown);
	ShBoost = Approach(ShBoost, Controls.IsBoost() ? 1.f : 0.f, Dt, Controls.IsBoost() ? BoostTauUp : BoostTauDown);

	// Base fix 4b-3: the release (a smaller command on the same side) uses LiftTauRelease
	const float LiftTarget = Controls.GetLift();
	const bool bLiftRelease = LiftTauRelease > 0.f && FMath::Abs(LiftTarget) < FMath::Abs(ShLift) && LiftTarget * ShLift >= 0.f;
	ShLift = Approach(ShLift, LiftTarget, Dt, bLiftRelease ? LiftTauRelease : LiftTau);

	// "Meet her": the helm returns with SteerTauRelease
	const bool bSteerRelease = SteerTauRelease > 0.f && FMath::Abs(RawSteer) < FMath::Abs(ShSteer);
	ShSteer = Approach(ShSteer, RawSteer, Dt, bSteerRelease ? SteerTauRelease : SteerTau);
	ShStrafe = Approach(ShStrafe, Controls.GetStrafe(), Dt, StrafeTau);
}

float UAirshipFlightComponent::GalleonHoldThrottle(float OrderSpeed) const
{
	const float Drag = DragC1 * OrderSpeed + DragC2 * OrderSpeed * FMath::Abs(OrderSpeed);

	if (OrderSpeed >= 0.f)
	{
		const float FadeForward = FMath::Max(1e-3f, 1.f - FMath::Pow(OrderSpeed / FMath::Max(VTop, 1.f), ThrustFadeExponent));
		return FMath::Clamp(Drag / FMath::Max(AFan * FadeForward, KINDA_SMALL_NUMBER), 0.f, 1.f);
	}

	const float FadeReverse = FMath::Max(1e-3f, 1.f - FMath::Square(-OrderSpeed / FMath::Max(VTopRev, 1.f)));
	return FMath::Clamp(Drag / FMath::Max(AFanRev * FadeReverse, KINDA_SMALL_NUMBER), -1.f, 0.f);
}

void UAirshipFlightComponent::ShapeGalleon(const FAirshipPilotInput& Controls, float Dt, float ForwardSpeed, float RawSteer, float& ThrottleTarget)
{
	// The order on the wire (a latched code: a lost packet changes nothing) and the telegraph "ring"
	const int32 Notch = AirshipGalleon::ThrottleToNotch(Controls.Throttle);

	if (Notch != GalleonLastNotch)
	{
		GalleonOrderPulse01 = 1.f;
		GalleonLastNotch = Notch;
	}

	// The gated boost bit: FULL STEAM
	const bool bBoostOn = Controls.IsBoost();

	if (bBoostOn && !bGalleonPrevBoost)
	{
		GalleonBoostPulse01 = 1.f;
	}
	bGalleonPrevBoost = bBoostOn;

	// The stern swing is the v1 drift test with Galleon's values
	bShBrake = Controls.IsBrake();
	bDrifting = bShBrake && FMath::Abs(RawSteer) > DriftSteerThreshold && ForwardSpeed > DriftMinSpeed;
	ShBrakeAmount = bShBrake ? 1.f : 0.f;

	// The speed loop: FULL and FULL STEAM are open loop (as Classic W), the other orders hold their speed hands-free
	if (bBoostOn || Notch >= AirshipGalleon::Full)
	{
		ThrottleTarget = 1.f;
	}
	else
	{
		const float OrderSpeed = Notch < 0 ? -GalleonOrderAsternSpeed
			: (Notch == AirshipGalleon::Slow ? GalleonOrderSlowSpeed : (Notch == AirshipGalleon::Half ? GalleonOrderHalfSpeed : 0.f));
		ThrottleTarget = FMath::Clamp(GalleonHoldThrottle(OrderSpeed) + GalleonOrderSpeedGain * (OrderSpeed - ForwardSpeed), -1.f, 1.f);
	}

	// An unpiloted drift: the neutral controls decode as STOP, whose speed loop would back the engines against the drift.
	// The engines idle (the drift force eases the speed down instead, ApplyForces).
	if (Controls.HasButton(Airship::Button_Drift))
	{
		ThrottleTarget = 0.f;
	}

	// The air brake while held (the order resumes on release); the swing keeps the order's throttle
	if (bShBrake && !bDrifting)
	{
		ThrottleTarget = BrakeFadeSpeed > 0.f
			? -BrakeReverseThrottle * FMath::Clamp(ForwardSpeed / BrakeFadeSpeed, 0.f, 1.f)
			: (ForwardSpeed > 100.f ? -BrakeReverseThrottle : 0.f);
	}

	const float PulseTime = FMath::Max(GalleonOrderPulseTime, 1e-3f);
	GalleonOrderPulse01 = FMath::Max(0.f, GalleonOrderPulse01 - Dt / PulseTime);
	GalleonBoostPulse01 = FMath::Max(0.f, GalleonBoostPulse01 - Dt / PulseTime);
}

int32 UAirshipFlightComponent::SkyTierOf(float Charge) const
{
	if (Charge >= SkyTier3 - 1e-6f)
	{
		return 3;
	}
	if (Charge >= SkyTier2 - 1e-6f)
	{
		return 2;
	}
	if (Charge >= SkyTier1 - 1e-6f)
	{
		return 1;
	}
	return 0;
}

void UAirshipFlightComponent::ShapeSkyRacer(const FAirshipPilotInput& Controls, float Dt, float ForwardSpeed, float RawSteer, float& ThrottleTarget)
{
	using namespace AirshipFlightPrivate;

	// This machine's own clock (the sum of the shaping steps): the chain window, the burn
	SkyClock += Dt;
	SkyTurboEvent = 0;

	const bool bBrakeButton = Controls.IsBrake();
	const float ThrottleRaw = Controls.GetThrottle();

	// ---- Drift state machine (every machine, from the controls it has, like v1's bDrifting) -------------------------
	if (SkyDriftDir == 0)
	{
		if (bBrakeButton && FMath::Abs(RawSteer) >= SkyDriftEnterSteer && ForwardSpeed >= SkyDriftEnterSpeed)
		{
			SkyDriftDir = static_cast<int8>(RawSteer > 0.f ? 1 : -1);
			SkyCharge = 0.f;
			SkyDriftTime = 0.f;

			// Started within the window of the last turbo: one more chain link
			const bool bLinked = SkyClock - SkyLastReleaseTime <= SkyChainWindow;
			SkyChain = bLinked ? static_cast<uint8>(FMath::Clamp(static_cast<int32>(SkyChain) + 1, 0, FMath::Clamp(SkyChainMax, 0, 255))) : static_cast<uint8>(0);
		}
	}
	else if (!bBrakeButton || ForwardSpeed < SkyDriftExitSpeed)
	{
		// Release: the server gives a remote pilot a little charge grace (packet timing can cost its copy 1-2 frames)
		const AAirshipPawn* Ship = GetShip();
		const bool bRemotePilot = GetOwner() && GetOwner()->HasAuthority() && Ship && !Ship->IsLocallyControlled();
		const int32 Tier = SkyTierOf(SkyCharge + (bRemotePilot ? SkyTierGrace : 0.f));

		if (Tier > 0 && ForwardSpeed >= SkyDriftExitSpeed)
		{
			const float BurnTime = Tier >= 3 ? SkyTurboTime3 : (Tier == 2 ? SkyTurboTime2 : SkyTurboTime1);
			SkyTurboTier = static_cast<uint8>(Tier);
			SkyTurboTotal = FMath::Max(BurnTime, 1e-3f);
			SkyTurboLeft = SkyTurboTotal;
			SkyTurboEvent = static_cast<uint8>(Tier);
			SkyTurboChain = SkyChain;
			SkyLastReleaseTime = SkyClock;
			++SkyTurboEventCount;
		}
		else
		{
			SkyChain = 0;
		}

		SkyDriftDir = 0;
		SkyCharge = 0.f;
		SkyExitLeft = SkyDriftExitTime;
	}
	else
	{
		// Charging: faster the harder the steer goes into the drift
		const float SteerIn = FMath::Clamp(RawSteer * static_cast<float>(SkyDriftDir), -1.f, 1.f);
		SkyCharge = FMath::Min(1.f, SkyCharge + FMath::Lerp(SkyChargeRateMin, SkyChargeRateMax, 0.5f * (SteerIn + 1.f)) * Dt);
		SkyDriftTime += Dt;
	}

	if (SkyTurboLeft > 0.f)
	{
		SkyTurboLeft = FMath::Max(0.f, SkyTurboLeft - Dt);
	}

	if (SkyExitLeft > 0.f && SkyDriftDir == 0 && SkyTurboEvent == 0)
	{
		SkyExitLeft = FMath::Max(0.f, SkyExitLeft - Dt);
	}

	bDrifting = SkyDriftDir != 0;

	// ---- Brake: X when not drifting, or S above SkySBrakeSpeed (analog, progressive) -------------------------------
	const float SBrakeTarget = (!bDrifting && ThrottleRaw < 0.f && SkySBrakeSpeed > 0.f && ForwardSpeed > SkySBrakeSpeed) ? -ThrottleRaw : 0.f;
	SkySBrake = ApproachUpDown(SkySBrake, SBrakeTarget, Dt, SkySBrakeTauUp, SkySBrakeTauDown);

	if (SBrakeTarget <= 0.f && SkySBrake < 0.02f)
	{
		SkySBrake = 0.f;
	}

	ShBrakeAmount = (bBrakeButton && !bDrifting) ? 1.f : (bDrifting ? 0.f : SkySBrake);
	bShBrake = ShBrakeAmount > 0.f;

	// W/S as read (S below SkySBrakeSpeed = reverse); a drift drives at full power unless S is held (review R1)
	ThrottleTarget = ThrottleRaw;

	if (bDrifting && SkyDriftThrottle > 0.f && ThrottleRaw >= 0.f)
	{
		ThrottleTarget = FMath::Max(ThrottleTarget, SkyDriftThrottle);
	}

	if (bShBrake)
	{
		// Base fix 4c-2
		const float Fade = BrakeFadeSpeed > 0.f ? FMath::Clamp(ForwardSpeed / BrakeFadeSpeed, 0.f, 1.f) : (ForwardSpeed > 100.f ? 1.f : 0.f);
		ThrottleTarget = -BrakeReverseThrottle * ShBrakeAmount * Fade;
	}
}

void UAirshipFlightComponent::ComputeGimbals(float OutPitchDeg[Airship::NumPods], float OutRollDeg[Airship::NumPods]) const
{
	const float MaxDeg = FMath::Max(ThrusterGimbalMaxDeg, 0.f);
	const float Pitch = GimbalPitchPerThrottle * ShThrottle + GimbalPitchPerBoost * ShBoost - (bShBrake ? GimbalPitchPerBrake : 0.f);

	// Sky Racer: the nozzles lean into the slide (a real side force; the drift's path loop takes it into account)
	const bool bSkyRoll = ActiveScheme == EAirshipControlScheme::SkyRacer && SkyDriftDir != 0 && SkyDriftGimbalRollDeg > 0.f;

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

		// On top of the v1 lean, back inside the cone (as the bench's SkyFlightModel.compute_gimbals)
		if (bSkyRoll)
		{
			R = FMath::Clamp(R + SkyDriftGimbalRollDeg * static_cast<float>(SkyDriftDir), -MaxDeg, MaxDeg);
			const float SkyTotal = FMath::Sqrt(P * P + R * R);

			if (SkyTotal > MaxDeg && SkyTotal > KINDA_SMALL_NUMBER)
			{
				P *= MaxDeg / SkyTotal;
				R *= MaxDeg / SkyTotal;
			}
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

	// Server: what the ship does without a pilot (before the controls: a drift sets a bit in the neutral ones)
	if (bAuthority)
	{
		UpdateUnpilotedMode(Body, Velocity);
	}

	FAirshipPilotInput Controls = SelectControls();

	if (bAuthority)
	{
		// Round 2 PR B: did the pilot drive this frame (the lane component hands him the helm on the first drive), and
		// the lane assist: the lane flies, the pilot keeps his aim, fire and stations, his drive goes (SPEC_B B2.9)
		const bool bPiloted = Ship->HasPilot() || Ship->GetController() != nullptr;
		bPilotDriveInput = bPiloted && bFlightEnabled && AirshipFlightPrivate::IsDriveInput(Controls, ActiveScheme);

		if (bLaneAssistThisFrame)
		{
			Controls.Throttle = 0;
			Controls.Steer = 0;
			Controls.Lift = 0;
			Controls.Strafe = 0;
			Controls.HeadingTarget = 0;
			Controls.SetButton(Airship::Button_Boost, false);
			Controls.SetButton(Airship::Button_Brake, false);
			Controls.SetButton(Airship::Button_DriveIntent, false);
			// Galleon: the cleared order decodes as STOP, whose speed loop would back the engines against the cruise
			Controls.SetButton(Airship::Button_Drift, true);
		}

		Controls.SetButton(Airship::Button_Boost, bFlightEnabled && UpdateBoostServer(Controls.IsBoost(), Dt, Body));

		// Point & Fly: the heading loop on the authoritative hull writes the steer the forces and every observer use
		// (last frame's shaped boost, as the pilot's copy has it)
		if (ActiveScheme == EAirshipControlScheme::PointFly && bFlightEnabled && Controls.HasHeadingTarget())
		{
			const float BodyYawDeg = static_cast<float>(Body->GetComponentRotation().Yaw);
			const float BodyYawRateDeg = static_cast<float>(Body->GetPhysicsAngularVelocityInDegrees().Z);
			Controls.Steer = FAirshipPilotInput::QuantizeAxis(ComputeHeadingSteer(Controls.GetHeadingTargetDeg(), BodyYawDeg, BodyYawRateDeg, ForwardSpeed, ShBoost,
				Controls.IsBrake(), ServerHeadingLoop));
		}
		else
		{
			ServerHeadingLoop = FPointFlyLoopState();
		}

		// The other machines shape the same controls for their cosmetics
		RepInput = Controls;
	}
	else if (Ship->IsLocallyControlled())
	{
		// The pilot's client: gate the boost by the replicated fuel, like the server does (Sky Racer: the same burst
		// latch on this machine's clock)
		const double Now = World->GetTimeSeconds();
		bool bWantBoost = Controls.IsBoost();

		if (ActiveScheme == EAirshipControlScheme::SkyRacer && SkyBoostMinBurst > 0.f && bLocalBoostActive && Now - SkyLocalBoostStartTime < SkyBoostMinBurst)
		{
			bWantBoost = true;
		}

		const bool bWasLocalBoostActive = bLocalBoostActive;

		if (bWantBoost && !bLocalBoostActive && BoostFuel >= BoostMinFuelToStart)
		{
			bLocalBoostActive = true;
		}
		if (!bWantBoost || BoostFuel <= 0.f)
		{
			bLocalBoostActive = false;
		}
		if (bLocalBoostActive && !bWasLocalBoostActive)
		{
			SkyLocalBoostStartTime = Now;
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
		ResetSchemeState(false);
		UnpilotedTarget = FAirshipUnpilotedTarget();
		bDriftRequest = false;
	}

	UpdateCosmetic(ForwardSpeed, static_cast<float>(Velocity.Size()));
}


// =============================================================================
// Unpiloted ship (server): drift after a moving exit, hold when parked
// =============================================================================

namespace AirshipFlightPrivate
{
	const TCHAR* UnpilotedModeName(EAirshipUnpilotedMode Mode)
	{
		switch (Mode)
		{
		case EAirshipUnpilotedMode::Coast: return TEXT("Coast");
		case EAirshipUnpilotedMode::Drift: return TEXT("Drift");
		case EAirshipUnpilotedMode::Hold: return TEXT("Hold");
		case EAirshipUnpilotedMode::Lane: return TEXT("Lane");
		default: return TEXT("None");
		}
	}
}

void UAirshipFlightComponent::SetLaneTarget(const FAirshipUnpilotedTarget& Target, bool bAssist)
{
	if (!GetOwner() || !GetOwner()->HasAuthority())
	{
		return;
	}

	// Read by this frame's UpdateUnpilotedMode (the pawn's Tick calls the lane right before UpdateFlight)
	LaneTarget = Target;
	LaneTarget.Mode = EAirshipUnpilotedMode::Lane;
	LaneTargetFrame = GFrameCounter;
	bLaneTargetAssist = bAssist;
}

void UAirshipFlightComponent::NotifyPilotLeft(const FVector& ExitVelocity)
{
	const UPrimitiveComponent* Body = GetBody();

	if (!Body || !GetOwner() || !GetOwner()->HasAuthority())
	{
		return;
	}

	// ResetInput (UnPossessed, before this) leaves it alone; the next evaluation drifts or parks
	bDriftRequest = true;
	DriftExitForwardSpeed = static_cast<float>(FVector::DotProduct(ExitVelocity, Body->GetForwardVector()));
	DriftRequestYaw = static_cast<float>(Body->GetComponentRotation().Yaw);
	DriftStart = Body->GetCenterOfMass();
	bDriftBlocked = false;
}

bool UAirshipFlightComponent::IsDriftIgnored(const AActor* Other) const
{
	const AActor* Owner = GetOwner();

	if (!Other)
	{
		return false;
	}

	// Its own parts and riders, characters anywhere and cannonballs never stop it. Other ships do (they are pawns too).
	return Other == Owner
		|| (Owner && Other->IsAttachedTo(Owner))
		|| Other->IsA<ACharacter>()
		|| Other->IsA<AAirshipCannonball>()
		|| (Other->IsA<APawn>() && !Other->IsA<AAirshipPawn>());
}

void UAirshipFlightComponent::NotifyHullContact(const AActor* Other, const FHitResult& Hit)
{
	UPrimitiveComponent* Body = GetBody();

	if (UnpilotedTarget.Mode != EAirshipUnpilotedMode::Drift || bDriftBlocked || !Body || IsDriftIgnored(Other))
	{
		return;
	}

	// At the bow: ahead of the centre of mass by more than 30 % of the hull's half length, and facing the drift (the
	// normal's sign in rigid-body hit events is not relied on). A graze along the side or the ground under it doesn't count.
	const FTransform BodyTM = Body->GetComponentTransform();
	const FBox Local = Body->CalcBounds(FTransform::Identity).GetBox();
	const double HalfLength = Local.IsValid ? 0.5 * (Local.Max.X - Local.Min.X) : 0.0;
	const double AheadOfCOM = BodyTM.InverseTransformPosition(Hit.ImpactPoint).X - BodyTM.InverseTransformPosition(Body->GetCenterOfMass()).X;
	const FVector DriftDir = FRotator(0.0, UnpilotedTarget.HeadingYaw, 0.0).Vector();

	if (AheadOfCOM <= 0.3 * HalfLength || FMath::Abs(FVector::DotProduct(Hit.ImpactNormal, DriftDir)) < UAirshipSettings::Get()->DriftBowHitMinDot)
	{
		return;
	}

	bDriftBlocked = true;
	UE_LOG(LogAirshipFlight, Log, TEXT("%s: drift ends, bow contact with %s"), *GetNameSafe(GetOwner()), *GetNameSafe(Other));
}

float UAirshipFlightComponent::GetDriftLookAheadDistance(float ForwardSpeed) const
{
	const UAirshipSettings* S = UAirshipSettings::Get();

	// Never shorter than the drift target's own look-ahead. At speed: the time ahead, plus the stop the hold's capped
	// spring needs from there (drag helps it, so this errs long). After a 48 m/s exit that is about 720 m, falling as
	// the ship slows: a far wall ends the drift only once the ship couldn't stop short of it any more.
	const float Speed = FMath::Max(ForwardSpeed, UnpilotedTarget.ForwardSpeed);
	const float StopDistance = FMath::Square(Speed) / (2.f * FMath::Max(S->HoldAccelMax, 1.f));
	return FMath::Max(S->DriftLookAheadMin, Speed * S->DriftLookAheadTime + StopDistance);
}

bool UAirshipFlightComponent::SweepDriftAhead(UPrimitiveComponent* Body, float ForwardSpeed, float& OutDistance) const
{
	OutDistance = GetDriftLookAheadDistance(ForwardSpeed);
	return SweepHullBox(Body, UnpilotedTarget.HeadingYaw, OutDistance, nullptr, TEXT("drift ends"));
}

bool UAirshipFlightComponent::SweepHullAhead(float HeadingYaw, float Distance, FHitResult* OutHit) const
{
	// The lane component logs what it does with the answer
	return SweepHullBox(GetBody(), HeadingYaw, Distance, OutHit, nullptr);
}

bool UAirshipFlightComponent::SweepHullBox(const UPrimitiveComponent* Body, float HeadingYaw, float Distance, FHitResult* OutHit, const TCHAR* LogContext) const
{
	const UWorld* World = GetWorld();
	const AActor* Owner = GetOwner();
	const UAirshipSettings* S = UAirshipSettings::Get();

	if (!World || !Body || !Owner || Distance <= 0.f)
	{
		return false;
	}

	// The hull's own box (the hidden SM_Airship body), inset on every side and with its bottom lifted, so level flight over
	// the ground doesn't count (the MinClearance floor lifts the ship over rising ground)
	const FBox Local = Body->CalcBounds(FTransform::Identity).GetBox();

	if (!Local.IsValid)
	{
		return false;
	}

	FVector Min = Local.Min + FVector(S->DriftSweepInset);
	FVector Max = Local.Max - FVector(S->DriftSweepInset);
	Min.Z += S->DriftSweepFloorLift;

	for (int32 Axis = 0; Axis < 3; ++Axis)
	{
		// Aura.Airship.Set skips the ClampMin metadata: keep a box at least 20 cm across
		if (Max[Axis] - Min[Axis] < 20.0)
		{
			const double Mid = 0.5 * (Max[Axis] + Min[Axis]);
			Min[Axis] = Mid - 10.0;
			Max[Axis] = Mid + 10.0;
		}
	}

	const FTransform BodyTM = Body->GetComponentTransform();
	const FVector Extent = 0.5 * (Max - Min) * BodyTM.GetScale3D().GetAbs();
	const FVector Start = BodyTM.TransformPosition(0.5 * (Min + Max));
	const FVector Dir = FRotator(0.0, HeadingYaw, 0.0).Vector();

	FCollisionQueryParams Params(SCENE_QUERY_STAT(AirshipDriftAhead), false, Owner);
	TArray<AActor*> Attached;
	Owner->GetAttachedActors(Attached, true, true);
	Params.AddIgnoredActors(Attached);

	FCollisionObjectQueryParams Objects;
	Objects.AddObjectTypesToQuery(ECC_WorldStatic);
	Objects.AddObjectTypesToQuery(ECC_WorldDynamic);
	Objects.AddObjectTypesToQuery(ECC_PhysicsBody);

	TArray<FHitResult> Hits;
	World->SweepMultiByObjectType(Hits, Start, Start + Dir * Distance, BodyTM.GetRotation(), Objects, FCollisionShape::MakeBox(Extent), Params);

	const ECollisionChannel HullChannel = Body->GetCollisionObjectType();

	for (const FHitResult& Hit : Hits)
	{
		const UPrimitiveComponent* Other = Hit.GetComponent();

		if (!Other || IsDriftIgnored(Hit.GetActor()))
		{
			continue;
		}

		// Only what the hull would bump into (a physics body that blocks the hull's channel): no trigger volumes
		if (!CollisionEnabledHasPhysics(Other->GetCollisionEnabled()) || Other->GetCollisionResponseToChannel(HullChannel) != ECR_Block)
		{
			continue;
		}

		if (LogContext)
		{
			UE_LOG(LogAirshipFlight, Log, TEXT("%s: %s, %s %.0f cm ahead"), *GetNameSafe(Owner), LogContext, *GetNameSafe(Hit.GetActor()),
				Hit.bStartPenetrating ? 0.f : Hit.Distance);
		}

		if (OutHit)
		{
			*OutHit = Hit;
		}
		return true;
	}

	return false;
}

void UAirshipFlightComponent::BeginHold(UPrimitiveComponent* Body)
{
	const FVector COM = Body->GetCenterOfMass();
	UnpilotedTarget = FAirshipUnpilotedTarget();
	UnpilotedTarget.Mode = EAirshipUnpilotedMode::Hold;
	UnpilotedTarget.HoldPoint = FVector2D(COM.X, COM.Y);
	UnpilotedTarget.HeadingYaw = static_cast<float>(Body->GetComponentRotation().Yaw);
}

void UAirshipFlightComponent::UpdateUnpilotedMode(UPrimitiveComponent* Body, const FVector& Velocity)
{
	using namespace AirshipFlightPrivate;

	const AAirshipPawn* Ship = GetShip();
	const UWorld* World = GetWorld();
	const UAirshipSettings* S = UAirshipSettings::Get();

	if (!Ship || !World || !Body)
	{
		return;
	}

	const EAirshipUnpilotedMode OldMode = UnpilotedTarget.Mode;
	const bool bPiloted = Ship->HasPilot() || Ship->GetController() != nullptr;

	// Round 2 PR B: a team ship's lane target of this frame (UAirshipLaneComponent) wins, also with a pilot at the helm
	// while the lane assists him. Flight off, death and the harness's debug controls still win over it.
	const bool bLaneWins = LaneTargetFrame == GFrameCounter && bFlightEnabled && !bDebugInputActive && !Ship->IsAirshipDead()
		&& (!bPiloted || bLaneTargetAssist);
	bLaneAssistThisFrame = bLaneWins && bPiloted;

	if (!bLaneWins && UnpilotedTarget.Mode == EAirshipUnpilotedMode::Lane)
	{
		// The lane let go (a pilot took the helm, the ship is parked outside its lane, the lane state is NoLane): out
		// through None, where an exit's drift request still starts a drift, else it holds if slow or coasts
		UnpilotedTarget = FAirshipUnpilotedTarget();
	}

	if (bLaneWins)
	{
		UnpilotedTarget = LaneTarget;
		bDriftRequest = false;
		bDriftBlocked = false;
	}
	// A pilot at the helm (or a controller on the ship: a pilot whose character is gone keeps flying), debug controls
	// (the harness), flight off (death): nobody else's business. A later exit asks again (NotifyPilotLeft).
	else if (!bFlightEnabled || bPiloted || bDebugInputActive || Ship->IsAirshipDead())
	{
		// Any drift asked for before is dropped: the request comes after the possession ends (debug controls cleared on
		// an unpiloted ship: Hold if slow, else Coast then Hold)
		UnpilotedTarget = FAirshipUnpilotedTarget();
		bDriftBlocked = false;
		bDriftRequest = false;
	}
	else
	{
		const FVector COM = Body->GetCenterOfMass();
		const FVector2D COMXY(COM.X, COM.Y);
		const float HullYaw = static_cast<float>(Body->GetComponentRotation().Yaw);
		const bool bSlow = static_cast<float>(Velocity.Size2D()) < S->HoldEngageSpeed;
		const bool bCanHold = S->bHoldWhenUnpiloted;
		const double Now = World->GetTimeSeconds();

		switch (UnpilotedTarget.Mode)
		{
		case EAirshipUnpilotedMode::None:
		{
			if (bDriftRequest && S->DriftSpeed > 0.f && DriftExitForwardSpeed > S->DriftMinExitSpeed)
			{
				// A moving exit: ahead on the exit heading at DriftSpeed (or slower: a slow exit never speeds up)
				UnpilotedTarget = FAirshipUnpilotedTarget();
				UnpilotedTarget.Mode = EAirshipUnpilotedMode::Drift;
				UnpilotedTarget.HeadingYaw = DriftRequestYaw;
				DriftSpeedLimit = DriftExitForwardSpeed;
				UnpilotedTarget.ForwardSpeed = FMath::Min(DriftSpeedLimit, S->DriftSpeed);
				bDriftBlocked = false;
				NextDriftSweepTime = Now;
			}
			else if (bCanHold && bSlow)
			{
				// Left at rest, or never piloted (placed, spawned): parked here (no creep off its trim)
				BeginHold(Body);
			}
			else
			{
				UnpilotedTarget = FAirshipUnpilotedTarget();
				UnpilotedTarget.Mode = EAirshipUnpilotedMode::Coast;
			}

			bDriftRequest = false;
			break;
		}

		case EAirshipUnpilotedMode::Coast:
		{
			if (bCanHold && bSlow)
			{
				BeginHold(Body);
			}
			break;
		}

		case EAirshipUnpilotedMode::Drift:
		{
			// Live tuning follows (Aura.Airship.Set Settings.DriftSpeed); 0 ends the drift
			UnpilotedTarget.ForwardSpeed = FMath::Min(DriftSpeedLimit, S->DriftSpeed);

			if (!bDriftBlocked && Now >= NextDriftSweepTime)
			{
				// The real speed along the heading: after a fast exit the ship is still slowing from cruise for a while
				const FVector DriftDir = FRotator(0.0, UnpilotedTarget.HeadingYaw, 0.0).Vector();
				const float AlongSpeed = FMath::Max(0.f, static_cast<float>(FVector::DotProduct(Velocity, DriftDir)));
				float LookAhead = 0.f;
				bDriftBlocked = SweepDriftAhead(Body, AlongSpeed, LookAhead);

				// The next sweep before the ship has covered half of this one (consecutive boxes overlap at any speed)
				const float HalfCoverTime = 0.5f * LookAhead / FMath::Max(AlongSpeed, 1.f);
				NextDriftSweepTime = Now + FMath::Clamp(HalfCoverTime, 0.02f, FMath::Max(S->DriftSweepInterval, 0.02f));
			}

			// A team ship left outside its lane (round 2 PR B) drifts at most the lane's limit (SetDriftMaxDistanceOverride)
			const float DriftLimit = DriftMaxDistanceOverride > 0.f ? DriftMaxDistanceOverride : S->DriftMaxDistance;
			const bool bFar = DriftLimit > 0.f && FVector2D::Distance(COMXY, FVector2D(DriftStart.X, DriftStart.Y)) > DriftLimit;
			const bool bBlocked = bDriftBlocked;

			if (bBlocked || bFar || S->DriftSpeed <= 0.f)
			{
				// Something ahead (or far enough): stop where it is. Without the hold: the old coast.
				bDriftBlocked = false;

				// The lane's distance end while still faster than HoldEngageSpeed coasts first (Coast holds once slow): a
				// hold spring started at speed overshoots by v^2 / (2 HoldAccelMax). A blocked drift still holds at once.
				// Only with the override, so free ships keep PR A's ending.
				const bool bCoastFirst = bFar && !bBlocked && S->DriftSpeed > 0.f && DriftMaxDistanceOverride > 0.f && !bSlow;

				if (bCanHold && !bCoastFirst)
				{
					BeginHold(Body);
				}
				else
				{
					UnpilotedTarget = FAirshipUnpilotedTarget();
					UnpilotedTarget.Mode = EAirshipUnpilotedMode::Coast;
				}
			}
			break;
		}

		case EAirshipUnpilotedMode::Hold:
		{
			if (!bCanHold)
			{
				UnpilotedTarget = FAirshipUnpilotedTarget();
				UnpilotedTarget.Mode = EAirshipUnpilotedMode::Coast;
				break;
			}

			// Pushed far or turned hard (a ram, a tow, a teleport): the hold drops again where it is once slow, coasting until then
			const bool bFar = S->HoldResetDistance > 0.f && FVector2D::Distance(COMXY, UnpilotedTarget.HoldPoint) > S->HoldResetDistance;
			const bool bTurned = S->HoldResetYawDeg > 0.f && FMath::Abs(WrapDeg(UnpilotedTarget.HeadingYaw - HullYaw)) > S->HoldResetYawDeg;

			if (bFar || bTurned)
			{
				if (bSlow)
				{
					BeginHold(Body);
				}
				else
				{
					UnpilotedTarget = FAirshipUnpilotedTarget();
					UnpilotedTarget.Mode = EAirshipUnpilotedMode::Coast;
				}
			}
			break;
		}

		default:
			break;
		}
	}

	if (UnpilotedTarget.Mode != OldMode)
	{
		const FString Extra = UnpilotedTarget.Mode == EAirshipUnpilotedMode::Drift ? FString::Printf(TEXT(", drift %.0f cm/s"), UnpilotedTarget.ForwardSpeed) : FString();
		UE_LOG(LogAirshipFlight, Log, TEXT("%s: unpiloted %s -> %s (%.0f cm/s%s)"), *GetNameSafe(GetOwner()), UnpilotedModeName(OldMode),
			UnpilotedModeName(UnpilotedTarget.Mode), static_cast<float>(Velocity.Size2D()), *Extra);
	}
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

	// Base fix 4a-1: GetInertiaTensor is the diagonal in the principal mass frame (Chaos orders it largest, smallest,
	// middle); the hull-axis torque is R diag(I) R^-1 alpha with the mass frame rotation R
	FQuat MassRot = FQuat::Identity;

	if (bHullAxisInertia)
	{
		if (const FBodyInstance* BodyInstance = Body->GetBodyInstance())
		{
			MassRot = BodyInstance->GetMassSpaceLocal().GetRotation();
		}
	}

	auto HullTorque = [&MassRot, &Inertia](const FVector& AlphaHull)
	{
		return MassRot.RotateVector(Inertia * MassRot.UnrotateVector(AlphaHull));
	};

	const float Boost = ShBoost;
	const float Steer = ShSteer;
	const float Strafe = ShStrafe;
	const float Lift = ShLift;
	const float Throttle = ShThrottle;

	const bool bGalleon = ActiveScheme == EAirshipControlScheme::Galleon;
	const bool bSky = ActiveScheme == EAirshipControlScheme::SkyRacer;
	const bool bPointFly = ActiveScheme == EAirshipControlScheme::PointFly;

	// Round 2 PR B: a team ship on its lane (UpdateUnpilotedMode), also under a pilot while the lane assists him
	const bool bUnpilotedLane = UnpilotedTarget.Mode == EAirshipUnpilotedMode::Lane;
	const UMyMatchSettings* LaneSettings = UMyMatchSettings::Get();

	// Sky Racer drift: direction, the shaped steer into the drift (-1 counter .. +1 full in) as 0..1
	const bool bSkyDrift = bSky && SkyDriftDir != 0;
	const float SkyDir = static_cast<float>(SkyDriftDir);
	const float SkyIn01 = bSkyDrift ? 0.5f * (FMath::Clamp(Steer * SkyDir, -1.f, 1.f) + 1.f) : 0.5f;
	const float VH = static_cast<float>(V.Size2D());

	// ---- Forward command (also sets the pitch lean) -------------------------------------------------------------
	// Aura.Airship.Set skips the ClampMin metadata: keep every divisor above zero
	const float AFanEff = FMath::Lerp(AFan, AFanBoost, Boost);
	const float VTopEff = FMath::Max(FMath::Lerp(VTop, VTopBoost, Boost), 1.f);
	// Sky Racer drift: the thrust fade uses the whole horizontal speed (the slide is no free speed)
	const float VFade = bSkyDrift ? VH : Vf;
	float AFanCmd = 0.f;

	if (Throttle >= 0.f)
	{
		AFanCmd = AFanEff * Throttle * FMath::Max(0.f, 1.f - FMath::Pow(FMath::Max(VFade, 0.f) / VTopEff, ThrustFadeExponent));
	}
	else
	{
		// Braking reverses the fans at full power (48 -> 0 m/s in about 2 s); S alone backs up gently. Galleon: moving
		// forward, the engines back at GalleonOrderReverseAccel to slow the ship to a lower order.
		const float ARev = (bShBrake && !bDrifting) ? AFan : ((bGalleon && Vf > 0.f) ? GalleonOrderReverseAccel : AFanRev);
		AFanCmd = ARev * Throttle * FMath::Max(0.f, 1.f - FMath::Square(FMath::Max(-Vf, 0.f) / FMath::Max(VTopRev, 1.f)));
	}

	// Point & Fly: S while moving forward is a firm slow-down (then the gentle reverse)
	if (bPointFly && PFReverseBrakeAccel > 0.f && Throttle < 0.f && !bShBrake && Vf > 200.f)
	{
		AFanCmd = FMath::Min(AFanCmd, PFReverseBrakeAccel * Throttle * FMath::Clamp(Vf / 600.f, 0.f, 1.f));
	}

	float ADrag = -(DragC1 * Vf + DragC2 * Vf * FMath::Abs(Vf));
	float ADragPath = 0.f;

	if (bSkyDrift)
	{
		// Drag along the horizontal velocity plus a scrub growing with the slip; ADrag keeps its share along the hull
		// (the pitch lean only: it is left out of the COM force)
		const FVector VbHorizontal = Q.UnrotateVector(FVector(V.X, V.Y, 0.0));
		const float SinSlip = static_cast<float>(FMath::Abs(VbHorizontal.Y)) / FMath::Max(VH, 1.f);
		ADragPath = -(DragC1 * VH + DragC2 * VH * VH + SkyDriftScrub * VH * SinSlip);
		ADrag = ADragPath * FMath::Sqrt(FMath::Max(0.f, 1.f - SinSlip * SinSlip));
	}

	// Air brake, capped by BrakeMaxAccel (0 = v1), times the brake share (Sky Racer's analog S-brake)
	float ABrake = 0.f;

	if (bShBrake)
	{
		float BrakeRaw = Kbrake * Vf * (bDrifting ? DriftBrakeScale : 1.f);

		if (BrakeMaxAccel > 0.f)
		{
			BrakeRaw = FMath::Clamp(BrakeRaw, -BrakeMaxAccel, BrakeMaxAccel);
		}
		ABrake = -BrakeRaw * ShBrakeAmount;
	}

	// The steady gun deck: gentler thrust and brake (not while drifting)
	if (bShGunDeck && !bDrifting)
	{
		if (AFanCmd > 0.f)
		{
			AFanCmd *= GunDeckThrottleScale;
		}
		ABrake *= GunDeckBrakeScale;
	}

	const float ACmd = AFanCmd + ADrag + ABrake;

	// ---- Vertical: speed command, altitude hold, floor, ceiling --------------------------------------------------
	float VzCmd = 0.f;
	const bool bBrakePressed = bShBrake && !bBrakeWasHeld;
	bBrakeWasHeld = bShBrake;

	// Base fix 4b-2: with HoldBrakeAccel the capture lead is the stopping distance (v1: HoldCaptureLead seconds)
	auto StopLead = [this](float VzNow)
	{
		return HoldBrakeAccel > 0.f ? VzNow * FMath::Abs(VzNow) / (2.f * HoldBrakeAccel) : VzNow * HoldCaptureLead;
	};

	if (FMath::Abs(Lift) >= LiftDeadZone)
	{
		VzCmd = Lift * (Lift > 0.f ? ClimbRate : DescendRate);
		bHoldValid = false;
	}
	else
	{
		if (!bHoldValid)
		{
			HoldZ = Z + StopLead(Vz);
			bHoldValid = true;
		}

		// Brake = hover here (base fix 4c-1: at the stopping point)
		if (bBrakePressed)
		{
			HoldZ = Z + (bBrakeHoldLead ? StopLead(Vz) : 0.f);
		}

		// Lane: the held altitude follows the lane's at LaneClimbRate, or the target's own rate (a recall climbing over the
		// field: at 200 cm/s its 80 m climb and descent alone would outlast ShipRecallMaxTime). The MinClearance floor
		// below still lifts the ship over anything under its pods
		if (bUnpilotedLane && UnpilotedTarget.bHasHoldZ)
		{
			const float ClimbRateNow = UnpilotedTarget.ClimbRate > 0.f ? UnpilotedTarget.ClimbRate : LaneSettings->LaneClimbRate;
			HoldZ = FMath::FInterpConstantTo(HoldZ, UnpilotedTarget.HoldZ, Dt, ClimbRateNow);
		}

		const float HoldError = HoldZ - Z;
		VzCmd = Kz * HoldError;

		// Base fix 4b-2: no faster than it can stop with HoldBrakeAccel
		if (HoldBrakeAccel > 0.f)
		{
			VzCmd = HoldError == 0.f ? 0.f : FMath::Sign(HoldError) * FMath::Min(FMath::Abs(VzCmd), FMath::Sqrt(2.f * HoldBrakeAccel * FMath::Abs(HoldError)));
		}

		VzCmd = FMath::Clamp(VzCmd, -HoldMaxSpeed, HoldMaxSpeed);
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

	// Point & Fly: the collective makes up the turn's downward grip (last frame's value)
	const float ATurnZ = bPointFly ? PFTurnLiftComp * LastGripAccelZ : 0.f;
	const float FvWorld = FMath::Clamp(Mass * (Gravity + Kvz * (VzCmd - Vz) - ATurnZ), CollectiveMin * Weight, CollectiveMax * Weight);
	const float FvBody = FvWorld / FMath::Max(0.5f, static_cast<float>(Up.Z));

	// Base fix 4b-1: a hidden vertical brake while the vertical speed runs past its command in its own direction
	float AVert = 0.f;

	if (VertBrakeAccel > 0.f && Vz * (Vz - VzCmd) > 0.f && FMath::Abs(Vz) > FMath::Abs(VzCmd))
	{
		AVert = -FMath::Sign(Vz) * FMath::Min(VertBrakeAccel, Kvz * FMath::Abs(Vz - VzCmd));
	}

	// ---- Attitude: lean targets, quaternion error, PD --------------------------------------------------------------
	float BankDeg = 0.f;

	if (bSkyDrift)
	{
		// The bank follows the drift direction (counter-steer only shallows it), not the momentary steer
		BankDeg = SkyDriftBankDeg * SkyDir * FMath::Lerp(0.7f, 1.f, SkyIn01) * FMath::Clamp(Vf / FMath::Max(BankFullSpeed, 1.f), BankMinFraction, 1.f)
			+ StrafeBankDeg * Strafe;
	}
	else
	{
		const float BankMax = bDrifting ? BankMaxDriftDeg : FMath::Lerp(BankMaxDeg, BankMaxBoostDeg, Boost);
		BankDeg = BankMax * Steer * FMath::Clamp(Vf / FMath::Max(BankFullSpeed, 1.f), BankMinFraction, 1.f) + StrafeBankDeg * Strafe;
	}

	// The steady gun deck keeps the deck near level (also while drifting)
	if (bShGunDeck)
	{
		BankDeg *= GunDeckBankScale;
	}

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

	// ---- Yaw command (above the mixer: the hull-axis tensor couples it into the roll / pitch torques) -------------------
	const float YawRate = static_cast<float>(AngVel.Z);
	float RmaxDeg = GetYawRateMaxDeg(Vf, Boost, bDrifting);
	float YawRateCmd = Steer * FMath::DegreesToRadians(RmaxDeg);
	float SkyPathRate = 0.f;

	if (bSky)
	{
		// Slip: nose relative to the horizontal velocity (deg, + = nose right of it)
		const float CourseDeg = VH > 100.f ? static_cast<float>(FMath::RadiansToDegrees(FMath::Atan2(V.Y, V.X))) : static_cast<float>(Current.Yaw);
		const float SlipDeg = WrapDeg(static_cast<float>(Current.Yaw) - CourseDeg);

		if (bSkyDrift)
		{
			// The steer sets the PATH turn rate; the yaw loop swings the nose in to hold a slip on top of it
			SkyPathRate = SkyDir * FMath::DegreesToRadians(FMath::Lerp(SkyDriftPathRateMinDeg, SkyDriftPathRateMaxDeg, SkyIn01));
			const float SlipTargetDeg = SkyDir * FMath::Lerp(SkyDriftSlipMinDeg, SkyDriftSlipMaxDeg, SkyIn01);
			const float NoseRateMax = FMath::DegreesToRadians(SkyDriftYawRateMaxDeg);
			YawRateCmd = FMath::Clamp(SkyPathRate + SkyDriftSlipGain * FMath::DegreesToRadians(SlipTargetDeg - SlipDeg), -NoseRateMax, NoseRateMax);
			RmaxDeg = FMath::RadiansToDegrees(FMath::Abs(YawRateCmd));

			// Turn-in first, then the tail steps out: the path never runs ahead of the hull plus what its slip allows
			SkyPathRate = SkyDir * FMath::Min(FMath::Abs(SkyPathRate), FMath::Max(0.f, YawRate * SkyDir + FMath::DegreesToRadians(SkyDriftPathLeadDeg)
				+ SkyDriftSlipGain * FMath::DegreesToRadians(FMath::Max(0.f, SlipDeg * SkyDir))));
		}
		else if (SkyExitLeft > 0.f)
		{
			// Drift exit: the nose swings back part of the slip while the grip pulls the path onto it
			YawRateCmd -= SkyDriftExitYawGain * FMath::DegreesToRadians(SlipDeg);
		}
	}

	// Unpiloted drift / hold / lane: hold the heading (no pilot, or the lane assist cleared his steer; the anchor
	// branch's yaw loop)
	const bool bUnpilotedDrift = UnpilotedTarget.Mode == EAirshipUnpilotedMode::Drift;
	const bool bUnpilotedHold = UnpilotedTarget.Mode == EAirshipUnpilotedMode::Hold;
	const UAirshipSettings* UnpilotedSettings = UAirshipSettings::Get();

	if (bUnpilotedDrift || bUnpilotedHold || bUnpilotedLane)
	{
		const float HeadingErrDeg = WrapDeg(UnpilotedTarget.HeadingYaw - static_cast<float>(Current.Yaw));
		YawRateCmd = FMath::DegreesToRadians(FMath::Clamp(UnpilotedSettings->HoldYawGain * HeadingErrDeg, -UnpilotedSettings->HoldYawRateMax, UnpilotedSettings->HoldYawRateMax));
	}

	// The steady gun deck: fine helm (not while drifting)
	if (bShGunDeck && !bDrifting)
	{
		YawRateCmd *= GunDeckYawScale;
		RmaxDeg *= GunDeckYawScale;
	}

	// Loop gain / cap: the drift's own, or "meet her" while a turn is being taken off
	float KrEff = Kr;
	float AlphaYawCap = AlphaYawMax;

	if (bDrifting)
	{
		KrEff = DriftKr > 0.f ? DriftKr : Kr;
		AlphaYawCap = DriftAlphaYawMax > 0.f ? DriftAlphaYawMax : AlphaYawMax;
	}
	else if (KrSteady > 0.f && FMath::Abs(YawRateCmd) < FMath::Abs(YawRate) - 1e-3f)
	{
		KrEff = KrSteady;
		AlphaYawCap = FMath::Max(AlphaYawMax, AlphaYawMaxSteady);
	}

	const float AlphaZ = FMath::Clamp(KrEff * (YawRateCmd - YawRate) + AngularDamping * YawRateCmd, -AlphaYawCap, AlphaYawCap);

	// ---- Torque requests ------------------------------------------------------------------------------------------------
	double TauX = 0.0;
	double TauY = 0.0;
	double TauZ = 0.0;
	double Izz = 0.0;

	if (bHullAxisInertia)
	{
		const FVector TauHull = HullTorque(FVector(AlphaTiltBody.X, AlphaTiltBody.Y, AlphaZ));
		TauX = TauHull.X;
		TauY = TauHull.Y;
		TauZ = TauHull.Z;
		Izz = HullTorque(FVector::UpVector).Z;
	}
	else
	{
		TauX = Inertia.X * AlphaTiltBody.X;
		TauY = Inertia.Y * AlphaTiltBody.Y;
		TauZ = Inertia.Z * AlphaZ;
		Izz = Inertia.Z;
	}

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

	// Fan geometry (also needed by base fix 4a-2 before the attitude solve)
	const float Psi = FMath::DegreesToRadians(-FanYawMaxDeg * Steer);
	const FVector FanDir(1.0, FMath::Tan(Psi), 0.0);
	const double FanMaxForce = FMath::Lerp(FanMax, FanMaxBoost, Boost) * Weight;

	double Collective[Airship::NumPods] = {};
	double Attitude[Airship::NumPods] = {};
	const double BCollective[3] = { FvBody, 0.0, 0.0 };
	double YC[3];
	double YA[3];
	const bool bCollectiveSolved = Solve3x3(M, BCollective, YC);

	// Base fix 4a-2: the fans' estimated forward total (from the collective's share), its roll / pitch torque at the
	// fan points comes off the pods' attitude request (the yaw differential adds none)
	FVector TauFan = FVector::ZeroVector;

	if (bFanTorqueFeedForward && bCollectiveSolved)
	{
		double TotalEstimate = Mass * AFanCmd;

		for (int32 Pod = 0; Pod < Airship::NumPods; ++Pod)
		{
			TotalEstimate -= (A[0][Pod] * YC[0] + A[1][Pod] * YC[1] + A[2][Pod] * YC[2]) * PodDir[Pod].X;
		}
		TotalEstimate = FMath::Clamp(TotalEstimate, -2.0 * FanMaxForce, 2.0 * FanMaxForce);

		for (int32 Fan = 0; Fan < Airship::NumFans; ++Fan)
		{
			TauFan += FVector::CrossProduct(FanLocal[Fan] - COMLocal, FanDir * (0.5 * TotalEstimate));
		}
	}

	const double BAttitude[3] = { 0.0, TauX - TauFan.X, TauY - TauFan.Y };

	if (bCollectiveSolved && Solve3x3(M, BAttitude, YA))
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

	// ---- Fans: forward thrust + differential for yaw -----------------------------------------------------------------
	const double KL = FVector::CrossProduct(FanLocal[0] - COMLocal, FanDir).Z;
	const double KR = FVector::CrossProduct(FanLocal[1] - COMLocal, FanDir).Z;
	const double KDiff = 0.5 * (KL - KR);

	const double Total = FMath::Clamp(Mass * AFanCmd - PodSumBody.X, -2.0 * FanMaxForce, 2.0 * FanMaxForce);

	// Rudder: inside the yaw loop, it gives what the pods and the fan housings don't (never more), up to an authority
	// that grows with forward speed squared. Open loop it overpowered the gyro on a boost turn and spun the ship out.
	// A Sky Racer drift turns with the rudder whatever the steer.
	const float RudderSteer = bSkyDrift ? 1.f : FMath::Abs(Steer);
	const float RudderCap = FMath::Min(RudderAuthority * FMath::Square(Vf / FMath::Max(RudderRefSpeed, 1.f)), RudderMaxAlpha) * RudderSteer;
	const float RudderAlpha = Izz > KINDA_SMALL_NUMBER
		? FMath::Clamp(static_cast<float>(AlphaZ - (PodTauZ + 0.5 * Total * (KL + KR)) / Izz), -RudderCap, RudderCap)
		: 0.f;

	const double TauKnown = PodTauZ + 0.5 * Total * (KL + KR) + Izz * RudderAlpha;
	const double DMax = FMath::Max(0.0, 2.0 * FanMaxForce - FMath::Abs(Total));
	const double D = FMath::Abs(KDiff) > 1.0 ? FMath::Clamp((TauZ - TauKnown) / KDiff, -DMax, DMax) : 0.0;
	const double FanForce[Airship::NumFans] = { 0.5 * Total + 0.5 * D, 0.5 * Total - 0.5 * D };
	const float AlphaGyroZ = Izz > KINDA_SMALL_NUMBER ? FMath::Clamp(static_cast<float>((TauZ - TauKnown - KDiff * D) / Izz), -GyroYawMax, GyroYawMax) : 0.f;

	// ---- Lateral grip, strafe, drift ----------------------------------------------------------------------------------
	float Klat = bDrifting ? DriftKlat : FMath::Lerp(GripKlat, BoostKlat, Boost);
	float ALatMax = (bDrifting ? DriftALatMaxG : FMath::Lerp(GripALatMaxG, BoostALatMaxG, Boost)) * Gravity;
	const float Eta = bDrifting ? DriftEta : FMath::Lerp(GripEta, BoostEta, Boost);

	float AGrip = 0.f;
	float ARedirect = 0.f;
	float APath = 0.f;
	FVector PathN = FVector::ZeroVector;

	if (bSkyDrift)
	{
		// Sky Racer drift: a level path force perpendicular to the velocity turns it at the path rate; the physical
		// forces' share along it comes off, the rest is hidden, capped. It replaces the grip loop.
		PathN = VH > 1.f ? FVector(-V.Y / VH, V.X / VH, 0.0) : Right;
		FVector PhysicalForce = FVector::ZeroVector;

		for (int32 Pod = 0; Pod < Airship::NumPods; ++Pod)
		{
			PhysicalForce += PodForceWorld[Pod];
		}
		for (int32 Fan = 0; Fan < Airship::NumFans; ++Fan)
		{
			PhysicalForce += Q.RotateVector(FanDir * FanForce[Fan]);
		}

		const float PathAccelMax = SkyDriftALatMaxG * Gravity;
		APath = FMath::Clamp(SkyPathRate * VH - static_cast<float>(FVector::DotProduct(PhysicalForce, PathN)) / Mass, -PathAccelMax, PathAccelMax);
	}
	else
	{
		float CentripetalFF = 0.f;
		float EnergyKeep = 0.f;

		if (bSky)
		{
			// Drift exit snap: the slide straightens out fast
			if (SkyExitLeft > 0.f)
			{
				Klat = FMath::Max(Klat, SkyDriftExitKlat);
				ALatMax = FMath::Max(ALatMax, SkyDriftExitALatMaxG * Gravity);
			}

			// A planted carve: part of the centripetal acceleration fed forward, the scrubbed energy given back
			CentripetalFF = SkyGripCentripetalFF * YawRate * FMath::Max(Vf, 0.f);
			EnergyKeep = SkyGripEnergyKeep;
		}

		// Lane: the grip's sideways speed is the lane law's own (its target velocity plus the position error over the
		// spring / damper ratio), so the grip helps the ship back onto the lane instead of holding it where it is (with a
		// zero target the grip's 4 /s against the law's 0.4 /s^2 left a sideways error a 12 s time constant)
		float LatSpeedTarget = Strafe * StrafeSpeed;

		if (bUnpilotedLane)
		{
			const FVector LaneCOM = Body->GetCenterOfMass();
			const FVector2D LaneErr = UnpilotedTarget.HoldPoint - FVector2D(LaneCOM.X, LaneCOM.Y);
			const FVector2D LaneWant = UnpilotedTarget.HoldVelocity + LaneErr * (LaneSettings->LaneKp / FMath::Max(LaneSettings->LaneKd, 0.1f));
			const FVector2D Right2D = FVector2D(Right.X, Right.Y).GetSafeNormal();
			LatSpeedTarget = FMath::Clamp(static_cast<float>(FVector2D::DotProduct(LaneWant, Right2D)), -StrafeSpeed, StrafeSpeed);
		}

		const float GripTerm = Klat * (LatSpeedTarget - Vl);
		const float ALatCmd = FMath::Clamp(bSky ? CentripetalFF + GripTerm : GripTerm, -ALatMax, ALatMax);
		const float ALatPhys = static_cast<float>((PodSumBody.Y + (FanForce[0] + FanForce[1]) * FanDir.Y) / Mass);
		AGrip = ALatCmd - ALatPhys;

		if (EnergyKeep > 0.f)
		{
			// The energy the side force really scrubs (power -a_lat * vl), given back along Fwd
			ARedirect = Vf > RedirectMinSpeed ? EnergyKeep * FMath::Max(0.f, -ALatCmd * Vl) / FMath::Max(Vf, 500.f) : 0.f;
		}
		else
		{
			// Turning carves: part of the scrubbed side speed comes back as forward speed
			ARedirect = (Vf > RedirectMinSpeed && AGrip * Vl < 0.f) ? Eta * FMath::Abs(AGrip) : 0.f;
		}
	}

	// Point & Fly: the vertical part of the grip, made up by next frame's collective
	LastGripAccelZ = bPointFly ? AGrip * static_cast<float>(Right.Z) : 0.f;

	// Level grip (no turn sink): perpendicular to the heading, or the hull's right axis made level
	FVector GripDir = Right;

	if (bLevelGripForce)
	{
		const FVector LevelDir = (bLevelGripAlongHeading ? FVector(-Fwd.Y, Fwd.X, 0.0) : FVector(Right.X, Right.Y, 0.0)).GetSafeNormal();

		if (!LevelDir.IsZero())
		{
			GripDir = LevelDir;
		}
	}

	// ---- Kicks and extras -----------------------------------------------------------------------------------------------
	if (!bSky)
	{
		// Drift boost when a long drift ends (Galleon: the stern swing's exit surge)
		if (bDrifting)
		{
			DriftTime += Dt;
		}
		else
		{
			// DriftBoostCapSpeed (Point & Fly): the kick only tops the ship up to that forward speed (0 = the full v1 kick)
			const float KickSpeed = GetDriftKickDV(Vf);

			if (DriftTime >= DriftBoostMinTime && DriftBoostDV > 0.f && KickSpeed > 0.f)
			{
				const FVector KickDV = Fwd * KickSpeed;
				Body->AddImpulse(KickDV, NAME_None, true);

				// The ship's own speed for the impact cap (DriftBoostDV is more than ImpactMaxSpeedGain)
				if (AAirshipPawn* Ship = GetShip())
				{
					Ship->NoteFlightKick(KickDV);
				}
			}
			DriftTime = 0.f;
		}
	}

	float ATurbo = 0.f;
	float ADive = 0.f;

	if (bSky)
	{
		// Mini-turbo released this frame: a kick (the ship's own speed for the impact cap) and boost fuel
		if (SkyTurboEvent > 0)
		{
			const int32 Tier = SkyTurboEvent;
			const float KickBase = Tier >= 3 ? SkyTurboKickDV3 : (Tier == 2 ? SkyTurboKickDV2 : SkyTurboKickDV1);
			const float Links = static_cast<float>(FMath::Min(static_cast<int32>(SkyTurboChain), FMath::Max(SkyChainMax, 0)));
			const FVector KickDV = Fwd * (KickBase * (1.f + SkyChainBonus * Links));
			Body->AddImpulse(KickDV, NAME_None, true);

			if (AAirshipPawn* Ship = GetShip())
			{
				Ship->NoteFlightKick(KickDV);
			}

			const float TurboFuel = Tier >= 3 ? SkyTurboFuel3 : (Tier == 2 ? SkyTurboFuel2 : SkyTurboFuel1);
			BoostFuel = FMath::Min(BoostFuelMax, BoostFuel + TurboFuel);
		}

		// The burn fades 1 -> 0 over its time
		const float TurboAlpha = SkyTurboLeft > 0.f ? SkyTurboLeft / FMath::Max(SkyTurboTotal, 1e-3f) : 0.f;

		if (TurboAlpha > 0.f)
		{
			ATurbo = SkyTurboAccel * TurboAlpha * FMath::Max(0.f, 1.f - FMath::Pow(FMath::Max(Vf, 0.f) / FMath::Max(SkyTurboVTop, 1.f), 4.f));
		}

		// Diving turns height into speed
		if (SkyDiveAccelPerSink > 0.f && Lift <= -LiftDeadZone && Vz < 0.f && Vf > SkyDiveMinSpeed)
		{
			ADive = SkyDiveAccelPerSink * -Vz;
		}
	}

	// Base fix 4d: station keeping at low speed with no throttle, strafe or boost
	float AKeepF = 0.f;

	// Not while drifting (2.5 m/s is inside its full-strength band: it would brake the drift), holding (the hold law
	// replaces it at rest) or on a lane (it would brake the 6 m/s cruise)
	if (StationKeepGain > 0.f && FMath::Abs(Throttle) < 0.05f && FMath::Abs(Strafe) < 0.05f && Boost < 0.05f && !bUnpilotedDrift && !bUnpilotedHold
		&& !bUnpilotedLane)
	{
		const float Fade = FMath::Clamp(2.f - FMath::Sqrt(Vf * Vf + Vl * Vl) / FMath::Max(StationKeepSpeed, 1.f), 0.f, 1.f);
		AKeepF = FMath::Clamp(-StationKeepGain * Vf, -StationKeepAccelMax, StationKeepAccelMax) * Fade;
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

	// The v1 terms (grip along Right, drag, brake, redirect), then the schemes' (all 0 in Classic). A Sky Racer drift
	// drags along the velocity instead of along the hull.
	const float ADragFwd = bSkyDrift ? 0.f : ADrag;
	FVector ACom = bLevelGripForce ? GripDir * AGrip + Right * WindLat : Right * (AGrip + WindLat);
	ACom += Fwd * (ADragFwd + ABrake + ARedirect + ATurbo + ADive + AKeepF);

	if (bSkyDrift)
	{
		ACom += PathN * APath;

		if (VH > 1.f)
		{
			ACom += FVector(V.X / VH, V.Y / VH, 0.0) * ADragPath;
		}
	}

	if (bUnpilotedDrift)
	{
		// Along the hull: track the drift speed, with the drag at that speed fed forward (ADragFwd above takes the real
		// drag off), capped both ways: from cruise speed it eases down at DriftDecelMax
		const float T = UnpilotedTarget.ForwardSpeed;
		const float ADrift = FMath::Clamp(UnpilotedSettings->DriftGain * (T - Vf) + (DragC1 * T + DragC2 * T * FMath::Abs(T)),
			-UnpilotedSettings->DriftDecelMax, UnpilotedSettings->DriftAccelMax);
		ACom += Fwd * ADrift;
	}
	else if (bUnpilotedHold)
	{
		// Capped spring and damper on the centre of mass back to the hold point (the anchor branch's law); the target
		// velocity is 0 when parked (a lane cruise moves the point)
		const FVector HoldCOM = Body->GetCenterOfMass();
		const FVector2D Err = UnpilotedTarget.HoldPoint - FVector2D(HoldCOM.X, HoldCOM.Y);
		const FVector2D VErr = UnpilotedTarget.HoldVelocity - FVector2D(V.X, V.Y);
		const FVector2D AHold = (Err * UnpilotedSettings->HoldKp + VErr * UnpilotedSettings->HoldKd).GetClampedToMaxSize(UnpilotedSettings->HoldAccelMax);
		ACom += FVector(AHold.X, AHold.Y, 0.0);
	}
	else if (bUnpilotedLane)
	{
		// The hold law on a moving point (LaneKp, LaneKd), with the hull drag at the lane speed and the target's own
		// acceleration fed forward so the ship doesn't trail its target (ADragFwd above takes the real drag off), capped
		// at LaneAccelMax: 28 m/s needs 164 cm/s^2 of drag plus the 250 cm/s^2 ramp (SPEC_B B2.5 item 6)
		const FVector LaneCOM = Body->GetCenterOfMass();
		const FVector2D Err = UnpilotedTarget.HoldPoint - FVector2D(LaneCOM.X, LaneCOM.Y);
		const FVector2D VErr = UnpilotedTarget.HoldVelocity - FVector2D(V.X, V.Y);
		const FVector2D Fwd2D(Fwd.X, Fwd.Y);
		const float T = static_cast<float>(FVector2D::DotProduct(UnpilotedTarget.HoldVelocity, Fwd2D));
		const FVector2D DragFF = Fwd2D * (DragC1 * T + DragC2 * T * FMath::Abs(T));
		const FVector2D ALane = (Err * LaneSettings->LaneKp + VErr * LaneSettings->LaneKd + DragFF + UnpilotedTarget.HoldAccel)
			.GetClampedToMaxSize(LaneSettings->LaneAccelMax);
		ACom += FVector(ALane.X, ALane.Y, 0.0);
	}

	ACom.Z += AVert;

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

	// ---- Control schemes (every value v1-neutral outside its scheme) -----------------------------------------------
	C.bDrifting = bDrifting;
	C.bGunDeck = bShGunDeck;
	C.FXBoost = ShBoost;
	C.FXFanThrust = 0.f;
	C.DriftDir = 0;
	C.DriftCharge = 0.f;
	C.DriftTier = 0;
	C.TurboAlpha = 0.f;
	C.TurboTier = 0;
	C.TurboChain = 0;
	C.TurboEventCount = SkyTurboEventCount;

	// Wheel and rudder thrown hard over in a drift (only they read C.Steer; the fan yaw stays the forces')
	if (bDrifting && DriftCosmeticSteerScale != 1.f)
	{
		C.Steer = FMath::Clamp(ShSteer * DriftCosmeticSteerScale, -1.3f, 1.3f);
	}

	if (ActiveScheme == EAirshipControlScheme::Galleon && bFlightEnabled)
	{
		// The engines answer the telegraph and full steam: a short thrust pulse on the pods
		const float Pulse = GalleonOrderPulse * FMath::Max(GalleonOrderPulse01, GalleonBoostPulse01);

		if (Pulse > 0.f)
		{
			for (int32 Pod = 0; Pod < Airship::NumPods; ++Pod)
			{
				C.PodThrustAlpha[Pod] = FMath::Clamp(C.PodThrustAlpha[Pod] + Pulse, 0.f, 1.5f);
			}
		}
	}
	else if (ActiveScheme == EAirshipControlScheme::SkyRacer)
	{
		const int32 Tier = SkyDriftDir != 0 ? SkyTierOf(SkyCharge) : 0;
		const float TurboAlpha = SkyTurboLeft > 0.f ? SkyTurboLeft / FMath::Max(SkyTurboTotal, 1e-3f) : 0.f;
		const float ClockSeconds = static_cast<float>(FMath::Fmod(SkyClock, 64.0));

		C.DriftDir = SkyDriftDir;
		C.DriftCharge = SkyDriftDir != 0 ? SkyCharge : 0.f;
		C.DriftTier = static_cast<uint8>(Tier);
		C.TurboAlpha = TurboAlpha;
		C.TurboTier = SkyTurboTier;
		C.TurboChain = SkyChain;

		if (bFlightEnabled)
		{
			// Drift held: the rear pods flicker with the charge (4 / 6 / 9 Hz by tier); the burn lifts every pod
			const float FlickerHz = Tier >= 3 ? 9.f : (Tier == 2 ? 6.f : 4.f);
			const float DriftPulse = SkyDriftDir != 0 ? SkyFXDriftPulse * SkyCharge * (0.75f + 0.25f * FMath::Sin(2.f * UE_PI * FlickerHz * ClockSeconds)) : 0.f;

			for (int32 Pod = 0; Pod < Airship::NumPods; ++Pod)
			{
				const float RearPulse = Airship::IsFrontPod(Pod) ? 0.f : DriftPulse;
				C.PodThrustAlpha[Pod] = FMath::Clamp(C.PodThrustAlpha[Pod] + RearPulse + SkyFXTurboThrust * TurboAlpha, 0.f, 1.5f);
			}

			// The exhaust heats up as the drift charges (Niagara Boost), the burn on top; the fans spin with the burn
			float ChargeGlow = 0.f;

			if (SkyDriftDir != 0)
			{
				ChargeGlow = Tier >= 3 ? SkyFXChargeGlow3 + 0.1f * FMath::Sin(2.f * UE_PI * 8.f * ClockSeconds)
					: (Tier == 2 ? SkyFXChargeGlow2 : (Tier == 1 ? SkyFXChargeGlow1 : 0.3f * SkyCharge));
			}

			C.FXBoost = FMath::Max(ShBoost, FMath::Max(ChargeGlow, TurboAlpha));
			C.FXFanThrust = TurboAlpha;
		}
	}
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

	// Control schemes (the pawn overrides the Point & Fly pilot-side values on the pilot's machine)
	const bool bSky = ActiveScheme == EAirshipControlScheme::SkyRacer;
	const bool bPointFly = ActiveScheme == EAirshipControlScheme::PointFly;

	Out.Scheme = static_cast<uint8>(ActiveScheme);
	Out.ThrottleOrder = ActiveScheme == EAirshipControlScheme::Galleon ? AirshipGalleon::NotchToOrderValue(GetGalleonNotch()) : -2.f;
	Out.DriftCharge = (bSky && SkyDriftDir != 0) ? SkyCharge : 0.f;
	Out.bHeadingTargetActive = bPointFly && CurrentControls.HasHeadingTarget();
	Out.HeadingTargetDeg = Out.bHeadingTargetActive ? CurrentControls.GetHeadingTargetDeg() : 0.f;
	Out.bFreeLook = bPointFly ? CurrentControls.IsAiming() : true;
	Out.DriftDir = bSky ? static_cast<int32>(SkyDriftDir) : (bDrifting ? static_cast<int32>(FMath::Sign(ShSteer)) : 0);
	Out.DriftTier = (bSky && SkyDriftDir != 0) ? SkyTierOf(SkyCharge) : 0;
	Out.TurboAlpha = (bSky && SkyTurboLeft > 0.f) ? SkyTurboLeft / FMath::Max(SkyTurboTotal, 1e-3f) : 0.f;
	Out.TurboChain = bSky ? static_cast<int32>(SkyChain) : 0;
	Out.bGunDeck = bShGunDeck;
	Out.bGunLock = false;

	// Unpiloted (server values; the target stays None on clients)
	Out.UnpilotedMode = static_cast<uint8>(UnpilotedTarget.Mode);
	Out.bUnpilotedDrift = UnpilotedTarget.Mode == EAirshipUnpilotedMode::Drift;
	Out.bUnpilotedHold = UnpilotedTarget.Mode == EAirshipUnpilotedMode::Hold;
	Out.DriftTargetSpeedMS = Out.bUnpilotedDrift ? UnpilotedTarget.ForwardSpeed * 0.01f : 0.f;

	// Round 2 PR B: the lane target (the pawn adds the team and the lane component's state and hint)
	Out.bUnpilotedLane = UnpilotedTarget.Mode == EAirshipUnpilotedMode::Lane;
	Out.LaneTargetSpeedMS = Out.bUnpilotedLane ? static_cast<float>(UnpilotedTarget.HoldVelocity.Size()) * 0.01f : 0.f;
	Out.bLaneAssist = Out.bUnpilotedLane && bLaneAssistThisFrame;

	if (Out.bUnpilotedHold || Out.bUnpilotedLane)
	{
		const FVector COM = Body->GetCenterOfMass();
		Out.HoldOffsetM = static_cast<float>(FVector2D::Distance(UnpilotedTarget.HoldPoint, FVector2D(COM.X, COM.Y))) * 0.01f;
	}
}
