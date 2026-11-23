// Fill out your copyright notice in the Description page of Project Settings.


#include "Airship/AirshipPawn.h"

#include "AbilitySystemComponent.h"
#include "AbilitySystemGlobals.h"
#include "AbilitySystem/Data/MyGameplayTags.h"
#include "AbilitySystem/MyAbilitySystemComponent.h"
#include "AbilitySystem/MyAttributeSet.h"
#include "Airship/AirshipCannonball.h"
#include "Airship/AirshipDamageEffect.h"
#include "Airship/AirshipFlightComponent.h"
#include "Airship/AirshipHUDWidget.h"
#include "Airship/AirshipSettings.h"
#include "Airship/AirshipSubsystem.h"
#include "AnimationRuntime.h"
#include "Blueprint/GameViewportSubsystem.h"
#include "Blueprint/UserWidget.h"
#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/LocalPlayer.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/SkeletalMeshSocket.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EnhancedInputComponent.h"
#include "EnhancedInputSubsystems.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/GameStateBase.h"
#include "GameFramework/HUD.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/SpringArmComponent.h"
#include "HAL/IConsoleManager.h"
#include "InputAction.h"
#include "InputActionValue.h"
#include "InputMappingContext.h"
#include "Interfaces/MyCombatInterface.h"
#include "Misc/ScopeExit.h"
#include "Net/UnrealNetwork.h"
#include "NiagaraComponent.h"
#include "NiagaraFunctionLibrary.h"
#include "PhysicalMaterials/PhysicalMaterial.h"
#include "PhysicsEngine/PhysicsSettings.h"
#include "TimerManager.h"
#include "UI/Settings/MyGameUserSettings.h"
#include "UObject/ConstructorHelpers.h"
#include "UObject/UnrealType.h"

DEFINE_LOG_CATEGORY_STATIC(LogAirshipPawn, Log, All);

// Named, not anonymous: the unity build compiles this file together with others
namespace AirshipPawnPrivate
{
	TAutoConsoleVariable<int32> CVarRepMode(
		TEXT("Aura.Airship.RepMode"),
		0,
		TEXT("Physics replication of the airships (set it on every machine): 0 = Default (legacy, time based), 1 = PredictiveInterpolation (only with Project Settings > Physics > Physics Prediction; ignored with a warning otherwise)."),
		ECVF_Default);

	const FAirshipCosmeticState NeutralCosmetic{};

	int32 SideIndex(EAirshipSide Side)
	{
		return Side == EAirshipSide::Port ? 0 : 1;
	}

	EAirshipSide CannonSide(int32 Cannon)
	{
		return Airship::IsPortCannon(Cannon) ? EAirshipSide::Port : EAirshipSide::Starboard;
	}

	/**
	 * Spin change from Ref to W without the part that only slows Ref down (to a stop at most): losing spin is free, a
	 * reversal or a turned spin axis counts from the stop.
	 */
	FVector SpinGain(const FVector& Ref, const FVector& W)
	{
		const FVector Kick = W - Ref;
		const double RefSize = Ref.Size();

		if (RefSize <= UE_KINDA_SMALL_NUMBER)
		{
			return Kick;
		}

		const FVector Dir = Ref / RefSize;
		const double Slowing = FMath::Clamp(-FVector::DotProduct(Kick, Dir), 0.0, RefSize);
		return Kick + Dir * Slowing;
	}

	/**
	 * Impact cap: a gain of one physics step. Up to Free (flight forces, gravity) it passes; the rest spends the
	 * contact's budget (Used: part of Capacity, 0..1). Returns the gain allowed (Gain when it fits).
	 */
	double SpendKickBudget(double Gain, double Free, double Capacity, double& Used)
	{
		if (Gain <= Free)
		{
			return Gain;
		}

		const double Spent = FMath::Min(Gain - Free, FMath::Max(0.0, Capacity * (1.0 - Used)));

		if (Capacity > UE_KINDA_SMALL_NUMBER)
		{
			Used = FMath::Min(1.0, Used + Spent / Capacity);
		}

		return Free + Spent;
	}

	/** First-order filter step toward Target with time constant Tau (s), as the flight model's. */
	float ApproachExp(float Current, float Target, float Dt, float Tau)
	{
		if (Tau <= KINDA_SMALL_NUMBER)
		{
			return Target;
		}
		return Current + (Target - Current) * (1.f - FMath::Exp(-Dt / Tau));
	}

	/** -180..180 (float). */
	float WrapDeg(float AngleDeg)
	{
		return static_cast<float>(FRotator::NormalizeAxis(static_cast<double>(AngleDeg)));
	}

	FAirshipFeedbackEvent MakeFeedback(float Trauma, float FOVKickDeg, float Rumble, float RumbleTime, bool bRumbleLarge = true)
	{
		FAirshipFeedbackEvent Event;
		Event.Trauma = Trauma;
		Event.FOVKickDeg = FOVKickDeg;
		Event.Rumble = Rumble;
		Event.RumbleTime = RumbleTime;
		Event.bRumbleLarge = bRumbleLarge;
		return Event;
	}

	/** The ship HUD's slot: bottom-left corner, fixed size (the widget draws itself in NativePaint). */
	FGameViewportWidgetSlot MakeCornerSlot(const FVector2D& CornerOffset, const FVector2D& Size)
	{
		FGameViewportWidgetSlot CornerSlot;
		CornerSlot.Anchors = FAnchors(0.f, 1.f);
		CornerSlot.Alignment = FVector2D(0.f, 1.f);
		CornerSlot.Offsets = FMargin(CornerOffset.X, -CornerOffset.Y, Size.X, Size.Y);
		CornerSlot.ZOrder = 1;
		return CornerSlot;
	}
}

/**
 * The scheme-owned properties (IMPLEMENTATION_PLAN.md 1.13): every existing tunable a scheme changes and every new
 * tunable of the schemes. Applying a scheme copies all of them from the archetype (Classic = the class defaults), then
 * writes the scheme's overrides; Aura.Airship.Scheme check compares the same lists. Undefined at the end of the file.
 */
#define AIRSHIP_FC_EXISTING_SCHEME_PROPS(X) \
	X(AFan) X(AFanBoost) X(AlphaYawMax) X(BankFullSpeed) X(BankMaxBoostDeg) X(BankMaxDeg) X(BankMaxDriftDeg) X(BankMinFraction) \
	X(BoostALatMaxG) X(BoostDrainRate) X(BoostKickDV) X(BoostKlat) X(BoostMinFuelToStart) X(BoostPitchDeg) X(BoostRegenDelay) \
	X(BoostRegenRate) X(BoostTauDown) X(BoostTauUp) X(BrakeReverseThrottle) X(ClimbRate) X(CollectiveMax) X(CollectiveMin) \
	X(DescendRate) X(DriftALatMaxG) X(DriftBoostDV) X(DriftBoostMinTime) X(DriftBrakeScale) X(DriftEta) X(DriftKlat) X(DriftMinSpeed) \
	X(DriftSteerThreshold) X(FanMax) X(FanMaxBoost) X(GripALatMaxG) X(GripKlat) X(GyroTiltMax) X(GyroYawMax) X(Kbrake) X(KdRoll) \
	X(Kfloor) X(KpRoll) X(Kr) X(Kvz) X(LiftPitchDeg) X(LiftTau) X(MinClearance) X(PitchMaxDeg) X(PitchMinDeg) X(PitchPerG) \
	X(PodForceMax) X(RudderAuthority) X(RudderMaxAlpha) X(RudderRefSpeed) X(SteerTau) X(StrafeBankDeg) X(StrafeSpeed) X(StrafeTau) \
	X(ThrottleTauDown) X(ThrottleTauUp) X(ThrustFadeExponent) X(VTop) X(VTopBoost) X(YawRateAtMid) X(YawRateAtRest) X(YawRateAtTop) \
	X(YawRateBoost) X(YawRateDrift) X(YawRateMidSpeed) X(YawRateTopSpeed)

#define AIRSHIP_FC_BASEFIX_PROPS(X) \
	X(bHullAxisInertia) X(bFanTorqueFeedForward) X(VertBrakeAccel) X(HoldBrakeAccel) X(LiftTauRelease) X(bBrakeHoldLead) \
	X(BrakeFadeSpeed) X(StationKeepGain) X(StationKeepSpeed) X(StationKeepAccelMax)

#define AIRSHIP_FC_SHARED_PROPS(X) \
	X(bLevelGripForce) X(bLevelGripAlongHeading) X(BrakeMaxAccel) X(SteerTauRelease) X(KrSteady) X(AlphaYawMaxSteady) X(DriftKr) \
	X(DriftAlphaYawMax) X(DriftCosmeticSteerScale) X(GunDeckBankScale) X(GunDeckYawScale) X(GunDeckThrottleScale) X(GunDeckBrakeScale) \
	X(DriftBoostCapSpeed)

#define AIRSHIP_FC_GALLEON_PROPS(X) \
	X(GalleonOrderSlowSpeed) X(GalleonOrderHalfSpeed) X(GalleonOrderAsternSpeed) X(GalleonOrderSpeedGain) X(GalleonOrderReverseAccel) \
	X(GalleonOrderPulse) X(GalleonOrderPulseTime)

#define AIRSHIP_FC_SKYRACER_PROPS(X) \
	X(SkyDriftEnterSteer) X(SkyDriftEnterSpeed) X(SkyDriftExitSpeed) X(SkyDriftPathRateMinDeg) X(SkyDriftPathRateMaxDeg) \
	X(SkyDriftSlipMinDeg) X(SkyDriftSlipMaxDeg) X(SkyDriftSlipGain) X(SkyDriftPathLeadDeg) X(SkyDriftYawRateMaxDeg) X(SkyDriftALatMaxG) \
	X(SkyDriftScrub) X(SkyDriftBankDeg) X(SkyDriftGimbalRollDeg) X(SkyDriftExitTime) X(SkyDriftExitKlat) X(SkyDriftExitALatMaxG) \
	X(SkyDriftExitYawGain) X(SkyDriftThrottle) X(SkyChargeRateMin) X(SkyChargeRateMax) X(SkyTier1) X(SkyTier2) X(SkyTier3) X(SkyTierGrace) \
	X(SkyTurboKickDV1) X(SkyTurboKickDV2) X(SkyTurboKickDV3) X(SkyTurboTime1) X(SkyTurboTime2) X(SkyTurboTime3) X(SkyTurboAccel) \
	X(SkyTurboVTop) X(SkyTurboFuel1) X(SkyTurboFuel2) X(SkyTurboFuel3) X(SkyChainWindow) X(SkyChainBonus) X(SkyChainMax) \
	X(SkySBrakeSpeed) X(SkySBrakeTauUp) X(SkySBrakeTauDown) X(SkyGripCentripetalFF) X(SkyGripEnergyKeep) X(SkyDiveAccelPerSink) \
	X(SkyDiveMinSpeed) X(SkyBoostMinBurst) X(SkyFXDriftPulse) X(SkyFXTurboThrust) X(SkyFXChargeGlow1) X(SkyFXChargeGlow2) X(SkyFXChargeGlow3)

#define AIRSHIP_FC_POINTFLY_PROPS(X) \
	X(PFHeadingKp) X(PFHeadingLead) X(PFHeadingDecelDeg) X(PFHeadingDeadbandDeg) X(PFDriftStartDeg) X(PFDriftEndDeg) X(PFDriftDecelScale) \
	X(PFReverseBrakeAccel) X(PFTurnLiftComp)

#define AIRSHIP_FC_SCHEME_PROPS(X) \
	AIRSHIP_FC_EXISTING_SCHEME_PROPS(X) AIRSHIP_FC_BASEFIX_PROPS(X) AIRSHIP_FC_SHARED_PROPS(X) AIRSHIP_FC_GALLEON_PROPS(X) \
	AIRSHIP_FC_SKYRACER_PROPS(X) AIRSHIP_FC_POINTFLY_PROPS(X)

#define AIRSHIP_PAWN_EXISTING_SCHEME_PROPS(X) \
	X(AimFOVOffset) X(BaseFOV) X(BoostFOVExtra) X(CameraArmLength) X(CameraArmMax) X(CameraArmMin) X(CameraBoostArmExtra) \
	X(CameraDefaultPitch) X(CameraPitchMax) X(CameraPitchMin) X(FOVInterpSpeed) X(ImpactCooldown) X(ImpactDamagePerMS) \
	X(ImpactMaxDamage) X(ImpactMaxReboundSpeed) X(ImpactMaxSpeedGain) X(ImpactMaxSpinKickDeg) X(ImpactMinSpeed) X(RecenterDelay) \
	X(RecenterMinSpeed) X(RecenterSpeed) X(SpeedFOVExtra) X(SpeedFOVFull) X(SpeedFOVStart)

#define AIRSHIP_PAWN_SHARED_PROPS(X) \
	X(ImpactEpisodeAccelUp) X(ShakeRotDeg) X(ShakeLocCm) X(ShakeFrequency) X(ShakeDecay) X(FOVKickDecay) X(FOVMaxDeg) \
	X(CameraRollPerBank) X(CameraRollPerSteerDeg) X(CameraRollMaxDeg) X(CameraRollInterpSpeed) X(RumbleScale) X(ShakeHitPerMS) \
	X(ShakeHitMax) X(RumbleHitPerMS) X(DriftTraumaBase) X(DriftTraumaPerCharge) X(DriftRumbleBase) X(DriftRumblePerCharge) \
	X(FeedbackBoostStart) X(FeedbackOwnBroadside) X(FeedbackDriftKick) X(FeedbackTurbo1) X(FeedbackTurbo2) X(FeedbackTurbo3) \
	X(FeedbackOrderChange) X(FeedbackLockEngage)

#define AIRSHIP_PAWN_GALLEON_PROPS(X) \
	X(GalleonOrderAxisPress) X(GalleonOrderAxisRelease) X(GalleonOrderRepeatDelay) X(GalleonOrderRepeatInterval) \
	X(GalleonBeamWatchEnterDeg) X(GalleonBeamWatchExitDeg) X(GalleonStationsFireHoldTime) X(GalleonLookAheadDeg) X(GalleonLookAheadTau)

#define AIRSHIP_PAWN_SKYRACER_PROPS(X) \
	X(SkyLookIntoTurnTime) X(SkyLookIntoTurnMaxDeg) X(SkyCamSlipShare) X(bSkyCamYawRateFF) X(SkyCamDivePitchPerMS) \
	X(SkyCamDivePitchMaxDeg) X(SkyTurboArmExtra)

#define AIRSHIP_PAWN_POINTFLY_PROPS(X) \
	X(PFNudgeRateScale) X(PFHeadingMaxLeadDeg) X(PFLookReturnTau) X(bPFArcAssist) X(PFArcMarginDeg) X(PFArcMinBearingDeg) \
	X(PFArcMaxBearingDeg) X(PFArcApproachRateDeg) X(PFArcApproachTau) X(PFArcLockDelay) X(PFArcLockDeadbandDeg) X(PFArcRateDeg) \
	X(PFLockLeadTime) X(PFHeadingLeadRateMax) X(PFHeadingLeadTau) X(bPFPitchClimb) X(PFPitchClimbDeadbandDeg) X(PFPitchClimbFullDeg) \
	X(PFParkSpeed) X(PFLockArmTime)

#define AIRSHIP_PAWN_SCHEME_PROPS(X) \
	AIRSHIP_PAWN_EXISTING_SCHEME_PROPS(X) AIRSHIP_PAWN_SHARED_PROPS(X) AIRSHIP_PAWN_GALLEON_PROPS(X) AIRSHIP_PAWN_SKYRACER_PROPS(X) \
	AIRSHIP_PAWN_POINTFLY_PROPS(X)

/** The camera boom's scheme-owned values. */
#define AIRSHIP_BOOM_SCHEME_PROPS(X) X(TargetOffset) X(CameraLagSpeed) X(CameraLagMaxDistance) X(CameraRotationLagSpeed)

AAirshipPawn::AAirshipPawn()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickGroup = TG_PrePhysics;

	// Players possess it; no AI
	AutoPossessAI = EAutoPossessAI::Disabled;
	AIControllerClass = nullptr;
	SpawnCollisionHandlingMethod = ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn;

	// Server-authoritative physics; a 52 m ship is seen from far away
	bReplicates = true;
	SetReplicatingMovement(true);
	bAlwaysRelevant = true;
	SetNetUpdateFrequency(60.f);
	SetMinNetUpdateFrequency(30.f);
	// 16 bits per rotation axis: the byte default is 1.4 deg (0.6 m at the bow)
	GetReplicatedMovement_Mutable().RotationQuantizationLevel = ERotatorQuantization::ShortComponents;
	SetPhysicsReplicationMode(EPhysicsReplicationMode::Default);

	// ---- Physics body ----
	HullCollision = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("HullCollision"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> HullMesh(TEXT("/Game/Assets/MyShip/SM_Airship.SM_Airship"));

	if (HullMesh.Succeeded())
	{
		HullCollision->SetStaticMesh(HullMesh.Object);
	}

	HullCollision->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
	HullCollision->SetCollisionObjectType(ECC_PhysicsBody);
	HullCollision->SetCollisionResponseToAllChannels(ECR_Block);
	// Spring arms (also other players') pass through the hull
	HullCollision->SetCollisionResponseToChannel(ECC_Camera, ECR_Ignore);
	HullCollision->SetSimulatePhysics(true);
	HullCollision->SetNotifyRigidBodyCollision(true);
	// AMyProjectile (fireballs) damages on overlap: the hull counts even where PA_Airship has no body
	HullCollision->SetGenerateOverlapEvents(true);
	HullCollision->SetCanEverAffectNavigation(false);
	HullCollision->SetHiddenInGame(true);
	HullCollision->SetCastShadow(false);
	HullCollision->bReplicatePhysicsToAutonomousProxy = true;
	SetRootComponent(HullCollision);

	// ---- Visual mesh (Control Rig) ----
	Mesh = CreateDefaultSubobject<USkeletalMeshComponent>(TEXT("Mesh"));
	Mesh->SetupAttachment(HullCollision);
	Mesh->SetSimulatePhysics(false);
	// Hits for the aim, Electrocute, Shards (Visibility) and projectiles (overlap) on the physics asset bodies
	Mesh->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
	Mesh->SetCollisionObjectType(ECC_Pawn);
	Mesh->SetCollisionResponseToAllChannels(ECR_Ignore);
	Mesh->SetCollisionResponseToChannel(ECC_Visibility, ECR_Block);
	Mesh->SetCollisionResponseToChannel(ECC_WorldDynamic, ECR_Overlap);
	Mesh->SetGenerateOverlapEvents(true);
	Mesh->SetCanEverAffectNavigation(false);

	// ---- Camera ----
	CameraBoom = CreateDefaultSubobject<USpringArmComponent>(TEXT("CameraBoom"));
	CameraBoom->SetupAttachment(HullCollision);
	CameraBoom->TargetArmLength = CameraArmLength;
	CameraBoom->TargetOffset = FVector(0.0, 0.0, 900.0);
	CameraBoom->bUsePawnControlRotation = true;
	CameraBoom->bInheritPitch = true;
	CameraBoom->bInheritYaw = true;
	CameraBoom->bInheritRoll = false;
	CameraBoom->bEnableCameraLag = true;
	CameraBoom->CameraLagSpeed = 5.f;
	CameraBoom->CameraLagMaxDistance = 2500.f;
	CameraBoom->bEnableCameraRotationLag = true;
	CameraBoom->CameraRotationLagSpeed = 7.f;
	CameraBoom->bDoCollisionTest = true;
	CameraBoom->ProbeSize = 50.f;

	Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
	Camera->SetupAttachment(CameraBoom, USpringArmComponent::SocketName);
	Camera->bUsePawnControlRotation = false;
	Camera->SetFieldOfView(BaseFOV);

	// ---- Flight, GAS ----
	Flight = CreateDefaultSubobject<UAirshipFlightComponent>(TEXT("Flight"));

	// Replicated, Mixed (UMyAbilitySystemComponent's constructor); InitializeComponent finds the attribute set
	AbilitySystemComponent = CreateDefaultSubobject<UMyAbilitySystemComponent>(TEXT("AbilitySystemComponent"));
	AttributeSet = CreateDefaultSubobject<UMyAttributeSet>(TEXT("AttributeSet"));

	// ---- FX (systems set on the Blueprint) ----
	auto MakeFX = [this](const TCHAR* Name, const TCHAR* Socket)
	{
		UNiagaraComponent* FX = CreateDefaultSubobject<UNiagaraComponent>(Name);
		FX->SetupAttachment(Mesh, Socket);
		FX->SetAutoActivate(true);
		return FX;
	};

	ThrusterFX_FL = MakeFX(TEXT("ThrusterFX_FL"), TEXT("Thruster_FL_Flame"));
	ThrusterFX_FR = MakeFX(TEXT("ThrusterFX_FR"), TEXT("Thruster_FR_Flame"));
	ThrusterFX_RL = MakeFX(TEXT("ThrusterFX_RL"), TEXT("Thruster_RL_Flame"));
	ThrusterFX_RR = MakeFX(TEXT("ThrusterFX_RR"), TEXT("Thruster_RR_Flame"));
	TurbineFX_L = MakeFX(TEXT("TurbineFX_L"), TEXT("Turbine_L_Exhaust"));
	TurbineFX_R = MakeFX(TEXT("TurbineFX_R"), TEXT("Turbine_R_Exhaust"));

	CannonballClass = AAirshipCannonball::StaticClass();

	for (int32 Cannon = 0; Cannon < Airship::NumCannons; ++Cannon)
	{
		CannonMuzzleLocal[Cannon] = CannonMuzzleFallback.IsValidIndex(Cannon) ? CannonMuzzleFallback[Cannon] : FVector::ZeroVector;
		CannonRestDirLocal[Cannon] = Airship::IsPortCannon(Cannon) ? FVector(0.0, -1.0, 0.0) : FVector(0.0, 1.0, 0.0);
	}

	PilotSeatLocal = PilotSeatFallback;
}

void AAirshipPawn::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);

	DOREPLIFETIME(AAirshipPawn, PilotCharacter);
	DOREPLIFETIME(AAirshipPawn, bIsDead);
	DOREPLIFETIME(AAirshipPawn, DeathServerTime);

	// Every connection: the observers' cosmetics run the same scheme
	DOREPLIFETIME(AAirshipPawn, ControlScheme);
}

void AAirshipPawn::BeginPlay()
{
	// Components first (UAirshipFlightComponent reads the mesh bones and sets mass, centre of mass, damping)
	Super::BeginPlay();

	// The control scheme's preset on every machine (a client's OnRep before BeginPlay only stored it)
	ApplyControlScheme(false);

	if (HullPhysicalMaterial)
	{
		HullCollision->SetPhysMaterialOverride(HullPhysicalMaterial);
	}

	HullCollision->OnComponentHit.AddDynamic(this, &ThisClass::OnHullHit);

	// A plain AAirshipPawn (no SK_Airship, e.g. Aura.Airship.Spawn without BP_AirshipPawn): show the hull
	if (bShowHullWithoutMesh && Mesh && !Mesh->GetSkeletalMeshAsset())
	{
		HullCollision->SetHiddenInGame(false);
	}

	RefreshCannonGeometry();
	ZoomTarget = CameraArmLength;
	CameraBoom->TargetArmLength = CameraArmLength;

	AbilitySystemComponent->InitAbilityActorInfo(this, this);

	if (HasAuthority())
	{
		// MaxHealth first: PreAttributeChange clamps Health to it
		AbilitySystemComponent->SetNumericAttributeBase(UMyAttributeSet::GetMaxHealthAttribute(), MaxHealth);
		AbilitySystemComponent->SetNumericAttributeBase(UMyAttributeSet::GetHealthAttribute(), MaxHealth);
		AbilitySystemComponent->SetNumericAttributeBase(UMyAttributeSet::GetArmorAttribute(), Armor);
	}

	if (UAirshipSubsystem* Subsystem = UAirshipSubsystem::Get(this))
	{
		Subsystem->RegisterAirship(this);
	}

	// A client that got the actor after its death (joined late: no explosion), or with a pilot aboard
	if (bIsDead)
	{
		HandleDeath(!HasAuthority());
	}

	OnRep_PilotCharacter();
}

void AAirshipPawn::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	GetWorldTimerManager().ClearAllTimersForObject(this);

	// The pilot's machine: ship HUD off, on-foot overlay back
	HideShipHUD();

	if (HasAuthority() && PilotCharacter && EndPlayReason == EEndPlayReason::Destroyed)
	{
		const APlayerController* PC = PilotController.Get();

		if (!PC || PC->IsActorBeingDestroyed())
		{
			// The player left (APlayerController::PawnLeavingGame destroys the possessed ship): their character goes too
			ACharacter* Pilot = PilotCharacter;
			PilotCharacter = nullptr;
			Pilot->Destroy();
		}
		else
		{
			// The ship goes away under its pilot (console, kill Z): give the character back
			UnboardPilot(false);
		}
	}

	RemoveLocalMappingContext();

	// Clients: characters this ship made non-colliding get their collision back (and a body lost meanwhile)
	for (const TWeakObjectPtr<ACharacter>& Weak : PassengersWithCollisionOff)
	{
		if (ACharacter* Passenger = Weak.Get())
		{
			Passenger->SetActorEnableCollision(true);
			UAirshipSubsystem::RepairPhysicsState(Passenger);
		}
	}
	PassengersWithCollisionOff.Reset();

	if (UAirshipSubsystem* Subsystem = UAirshipSubsystem::Get(this))
	{
		Subsystem->UnregisterAirship(this);
	}

	Super::EndPlay(EndPlayReason);
}

void AAirshipPawn::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	// Before the physics step (TG_PrePhysics): what a hit this frame is measured against
	RecordPreStepState();

	// The pilot's machine: controls this frame (applied at once on the host, sent to the server from a client)
	if (IsLocallyControlled() && !bIsDead)
	{
		GatherLocalInput(DeltaSeconds);
	}

	if (Flight)
	{
		Flight->UpdateFlight(DeltaSeconds);
	}

	UpdateCannonAim();
	UpdateFX();

	if (IsLocallyControlled())
	{
		UpdateCamera(DeltaSeconds);
	}

	UpdateShipHUD();
	UpdateRepMode();

	// Server: this frame's hull state goes out in this frame's net flush (see bReplicateEveryFrame)
	if (bReplicateEveryFrame && HasAuthority() && GetNetMode() != NM_Standalone && HullCollision && HullCollision->IsAnyRigidBodyAwake())
	{
		ForceNetUpdate();
	}

	if (!HasAuthority())
	{
		UpdatePassengerCollision();
	}

	// Lost local control without a controller change notification: drop the ship's keys
	if (!IsLocallyControlled() && MappingSubsystem.IsValid())
	{
		RemoveLocalMappingContext();
	}

	// The pilot's character was destroyed while aboard (the player keeps flying; exit has nothing to return to)
	if (HasAuthority() && PilotCharacter && !IsValid(PilotCharacter))
	{
		PilotCharacter = nullptr;
		PilotController.Reset();
		OnRep_PilotCharacter();
	}
}

UAbilitySystemComponent* AAirshipPawn::GetAbilitySystemComponent() const
{
	return AbilitySystemComponent;
}

const FAirshipCosmeticState& AAirshipPawn::GetCosmeticState() const
{
	return Flight ? Flight->GetCosmeticState() : AirshipPawnPrivate::NeutralCosmetic;
}

FVector AAirshipPawn::GetCombatSocketLocation_Implementation()
{
	// The first muzzle of the side the cannons face
	const int32 Cannon = AimSide == EAirshipSide::Port ? 0 : 2;
	return HullCollision ? HullCollision->GetComponentTransform().TransformPosition(CannonMuzzleLocal[Cannon]) : GetActorLocation();
}

void AAirshipPawn::UpdateRepMode()
{
	EPhysicsReplicationMode Wanted = AirshipPawnPrivate::CVarRepMode.GetValueOnGameThread() == 1
		? EPhysicsReplicationMode::PredictiveInterpolation
		: EPhysicsReplicationMode::Default;

	// Listen-server test 2026-11-22: without Physics Prediction (Project Settings > Physics, off in this project) the
	// client copies under PredictiveInterpolation were never corrected (they coasted hundreds of metres off)
	if (Wanted == EPhysicsReplicationMode::PredictiveInterpolation && !UPhysicsSettings::Get()->PhysicsPrediction.bEnablePhysicsPrediction)
	{
		static bool bWarned = false;

		if (!bWarned)
		{
			bWarned = true;
			UE_LOG(LogAirshipPawn, Warning, TEXT("Aura.Airship.RepMode 1 (PredictiveInterpolation) needs Project Settings > Physics > Physics Prediction: staying on Default"));
		}

		Wanted = EPhysicsReplicationMode::Default;
	}

	if (GetPhysicsReplicationMode() != Wanted)
	{
		SetPhysicsReplicationMode(Wanted);
	}
}


// =============================================================================
// Possession
// =============================================================================

void AAirshipPawn::PossessedBy(AController* NewController)
{
	// Calls NotifyControllerChanged (ASC actor info, IMC on a listen server host)
	Super::PossessedBy(NewController);

	if (Flight)
	{
		Flight->ResetInput();
	}
}

void AAirshipPawn::UnPossessed()
{
	Super::UnPossessed();

	if (Flight)
	{
		Flight->ResetInput();
	}

	// Unpossessed some other way than UnboardPilot (the controller took another pawn): put the pilot back on foot
	if (HasAuthority() && PilotCharacter && !bUnboarding)
	{
		TWeakObjectPtr<AAirshipPawn> WeakThis(this);
		GetWorldTimerManager().SetTimerForNextTick([WeakThis]()
		{
			AAirshipPawn* Ship = WeakThis.Get();

			if (Ship && Ship->PilotCharacter && !Ship->GetController())
			{
				Ship->UnboardPilot(false);
			}
		});
	}
}

void AAirshipPawn::NotifyControllerChanged()
{
	UpdateLocalMappingContext();
	UpdateShipHUD();

	// The PlayerController in the ASC's actor info (damage numbers of cannon hits, Mixed replication).
	// The actor info exists once the ASC is initialized (before any possession or OnRep_Controller).
	if (AbilitySystemComponent && AbilitySystemComponent->AbilityActorInfo.IsValid())
	{
		AbilitySystemComponent->RefreshAbilityActorInfo();
	}

	Super::NotifyControllerChanged();
}


// =============================================================================
// Input
// =============================================================================

void AAirshipPawn::ResolveInputAssets()
{
	if (bInputAssetsResolved)
	{
		return;
	}

	bInputAssetsResolved = true;
	const UAirshipSettings* Settings = UAirshipSettings::Get();

	auto Resolve = [](TObjectPtr<UInputAction>& Action, const TSoftObjectPtr<UInputAction>& Soft)
	{
		if (!Action && !Soft.IsNull())
		{
			Action = Soft.LoadSynchronous();
		}
	};

	Resolve(ThrottleAction, Settings->ThrottleAction);
	Resolve(SteerAction, Settings->SteerAction);
	Resolve(LiftAction, Settings->LiftAction);
	Resolve(StrafeAction, Settings->StrafeAction);
	Resolve(BoostAction, Settings->BoostAction);
	Resolve(BrakeAction, Settings->BrakeAction);
	Resolve(FireAction, Settings->FireAction);
	Resolve(LookAction, Settings->LookAction);
	Resolve(ZoomAction, Settings->ZoomAction);
	Resolve(ExitAction, Settings->ExitAction);
	Resolve(AimAction, Settings->AimAction);

	if (!AirshipMappingContext && !Settings->AirshipMappingContext.IsNull())
	{
		AirshipMappingContext = Settings->AirshipMappingContext.LoadSynchronous();
	}

	if (!AirshipMappingContext || !ThrottleAction || !SteerAction || !LiftAction)
	{
		UE_LOG(LogAirshipPawn, Warning, TEXT("%s: IMC_Airship / IA_Airship* assets missing (Project Settings > Game > Airship); the ship can't be flown with the keyboard"), *GetName());
	}
}

void AAirshipPawn::SetupPlayerInputComponent(UInputComponent* PlayerInputComponent)
{
	Super::SetupPlayerInputComponent(PlayerInputComponent);

	ResolveInputAssets();
	UEnhancedInputComponent* Input = Cast<UEnhancedInputComponent>(PlayerInputComponent);

	if (!Input)
	{
		UE_LOG(LogAirshipPawn, Warning, TEXT("%s: the input component is not an Enhanced Input component"), *GetName());
		return;
	}

	// Axes and held buttons are read every frame (GatherLocalInput). Fire's value is read only by Point & Fly (Fire held
	// arms the gun lock); its press is the Started binding below, so holding Fire still fires once
	for (const UInputAction* Action : { ThrottleAction.Get(), SteerAction.Get(), LiftAction.Get(), StrafeAction.Get(), BoostAction.Get(), BrakeAction.Get(), AimAction.Get(),
		FireAction.Get() })
	{
		if (Action)
		{
			Input->BindActionValue(Action);
		}
	}

	if (LookAction)
	{
		Input->BindAction(LookAction, ETriggerEvent::Triggered, this, &ThisClass::OnLookInput);
	}

	if (ZoomAction)
	{
		Input->BindAction(ZoomAction, ETriggerEvent::Triggered, this, &ThisClass::OnZoomInput);
	}

	if (FireAction)
	{
		Input->BindAction(FireAction, ETriggerEvent::Started, this, &ThisClass::OnFireInput);
	}

	if (ExitAction)
	{
		Input->BindAction(ExitAction, ETriggerEvent::Started, this, &ThisClass::OnExitInput);
	}
}

void AAirshipPawn::UpdateLocalMappingContext()
{
	APlayerController* PC = Cast<APlayerController>(GetController());

	if (!PC || !PC->IsLocalController())
	{
		RemoveLocalMappingContext();
		return;
	}

	ResolveInputAssets();

	const ULocalPlayer* LocalPlayer = PC->GetLocalPlayer();
	UEnhancedInputLocalPlayerSubsystem* Subsystem = LocalPlayer ? LocalPlayer->GetSubsystem<UEnhancedInputLocalPlayerSubsystem>() : nullptr;

	if (!Subsystem || !AirshipMappingContext)
	{
		return;
	}

	if (MappingSubsystem.Get() == Subsystem && AddedMappingContext.Get() == AirshipMappingContext)
	{
		return;
	}

	RemoveLocalMappingContext();

	// Above IMC_PlayerMappings (priority 0): the ship's keys are consumed, so the on-foot abilities don't fire
	FModifyContextOptions Options;
	Options.bNotifyUserSettings = true;
	Subsystem->AddMappingContext(AirshipMappingContext, UAirshipSettings::Get()->AirshipMappingPriority, Options);
	MappingSubsystem = Subsystem;
	AddedMappingContext = AirshipMappingContext;

	// The view starts behind the ship (first local tick: OnPossess sets the control rotation after this)
	bPendingCameraReset = true;
	ZoomTarget = CameraArmLength;
	LastLookInputTime = -1000.0;

	// A new local pilot: the schemes' pilot-side state starts fresh (Galleon rings STOP)
	ResetSchemePilotState(false);
}

void AAirshipPawn::RemoveLocalMappingContext()
{
	// The continuous drift rumble belongs to the local controller that is leaving
	StopDriftRumble();

	UEnhancedInputLocalPlayerSubsystem* Subsystem = MappingSubsystem.Get();
	const UInputMappingContext* Context = AddedMappingContext.Get();

	if (Subsystem && Context)
	{
		FModifyContextOptions Options;
		Options.bNotifyUserSettings = true;
		Subsystem->RemoveMappingContext(Context, Options);
	}

	MappingSubsystem.Reset();
	AddedMappingContext.Reset();
}

void AAirshipPawn::GatherLocalInput(float DeltaSeconds)
{
	if (!Flight)
	{
		return;
	}

	const UEnhancedInputComponent* Input = Cast<UEnhancedInputComponent>(InputComponent);

	auto Axis = [Input](const UInputAction* Action)
	{
		return (Input && Action) ? Input->GetBoundActionValue(Action).Get<float>() : 0.f;
	};

	auto Button = [Input](const UInputAction* Action)
	{
		return (Input && Action) ? Input->GetBoundActionValue(Action).Get<bool>() : false;
	};

	APlayerController* PC = Cast<APlayerController>(GetController());
	const double Now = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0;
	FAirshipPilotInput Controls;

	if (Flight->HasDebugInput())
	{
		// Test hook (DebugSetInput, Aura.Airship.Input) on the pilot's machine: in place of the keys, so a client's debug
		// controls reach the server the same way (ServerSetPilotInput) instead of only moving its own cosmetics. They carry
		// no heading target or stations bit (Classic-style cross-checks in every scheme).
		Controls = Flight->GetDebugInput();

		// Point & Fly: the heading target restarts on the hull's heading once the debug controls end
		bPFValid = false;
	}
	else if (ControlScheme == EAirshipControlScheme::PointFly && PC)
	{
		using namespace AirshipPawnPrivate;

		// The camera first: its yaw is the heading target (Q/E on IA_AirshipStrafe turn it). Any drive / sidestep / turn /
		// boost key ends the parked free look. Fire held (LMB / RB, FireAction's value binding) arms the gun lock, as does
		// PFLockArmTime after an own broadside; the shot itself is OnFireInput (Started), once per press.
		const bool bAimHeld = Button(AimAction);
		const float NudgeAxis = Axis(StrafeAction);
		const bool bMoveKeys = FMath::Abs(Axis(ThrottleAction)) > 0.05f || FMath::Abs(Axis(SteerAction)) > 0.05f || FMath::Abs(NudgeAxis) > 0.05f
			|| Button(BoostAction);
		UpdatePointFlyCamera(DeltaSeconds, PC, NudgeAxis, bAimHeld, bMoveKeys, Button(FireAction));

		Controls.Throttle = FAirshipPilotInput::QuantizeAxis(Axis(ThrottleAction));

		// A/D sidestep: the Strafe axis
		Controls.Strafe = FAirshipPilotInput::QuantizeAxis(Axis(SteerAction));

		// Camera pitch -> climb / sink (off by default: looking down at the platforms never changes height)
		float LiftValue = Axis(LiftAction);

		if (bPFPitchClimb && !bAimHeld && FMath::Abs(LiftValue) < 0.05f)
		{
			const float PitchFromDefault = WrapDeg(static_cast<float>(PC->GetControlRotation().Pitch)) - CameraDefaultPitch;

			if (FMath::Abs(PitchFromDefault) > PFPitchClimbDeadbandDeg)
			{
				LiftValue = FMath::Clamp((FMath::Abs(PitchFromDefault) - PFPitchClimbDeadbandDeg) / FMath::Max(PFPitchClimbFullDeg, 1.f), 0.f, 1.f)
					* (PitchFromDefault > 0.f ? 1.f : -1.f);
				// Coarse steps: the send-on-change stays rare
				LiftValue = FMath::RoundToFloat(LiftValue * 16.f) / 16.f;
			}
		}

		Controls.Lift = FAirshipPilotInput::QuantizeAxis(LiftValue);
		Controls.SetButton(Airship::Button_Boost, Button(BoostAction));
		Controls.SetButton(Airship::Button_Brake, Button(BrakeAction));
		Controls.SetButton(Airship::Button_Aim, bAimHeld);

		// Lock lead: while the gun lock drags the target along, send it ahead by its own rate (the beam doesn't trail the
		// aim). Steering mode sends the plain target (a lead there overshoots when the camera stops).
		const float StepDt = FMath::Max(DeltaSeconds, UE_KINDA_SMALL_NUMBER);
		const float HeadingRateRaw = WrapDeg(PFHeading - PFPrevHeading) / StepDt;
		PFPrevHeading = PFHeading;
		PFHeadingRate = ApproachExp(PFHeadingRate, FMath::Clamp(HeadingRateRaw, -PFHeadingLeadRateMax, PFHeadingLeadRateMax), StepDt, PFHeadingLeadTau);
		const float LeadTime = (bPFLock && bPFFree) ? PFLockLeadTime : 0.f;
		PFSentHeading = WrapDeg(PFHeading + LeadTime * PFHeadingRate);
		Controls.HeadingTarget = FAirshipPilotInput::EncodeHeading(PFSentHeading);

		// The pilot's own copy of the heading loop on its view of the hull: its wheel, fans and bank answer at once. The
		// server overwrites the steer with its own loop on the authoritative hull.
		const bool bHullSimulating = HullCollision && HullCollision->IsSimulatingPhysics();
		const FVector HullVelocity = bHullSimulating ? HullCollision->GetPhysicsLinearVelocity() : GetVelocity();
		const float ViewForwardSpeed = static_cast<float>(FVector::DotProduct(HullVelocity, GetActorForwardVector()));
		const float ViewYawRate = bHullSimulating ? static_cast<float>(HullCollision->GetPhysicsAngularVelocityInDegrees().Z) : 0.f;
		Controls.Steer = FAirshipPilotInput::QuantizeAxis(Flight->ComputeHeadingSteer(PFSentHeading, static_cast<float>(GetActorRotation().Yaw), ViewYawRate,
			ViewForwardSpeed, Flight->GetShapedBoost(), Controls.IsBrake(), PilotHeadingLoop));
	}
	else
	{
		Controls.Throttle = FAirshipPilotInput::QuantizeAxis(Axis(ThrottleAction));
		Controls.Steer = FAirshipPilotInput::QuantizeAxis(Axis(SteerAction));
		Controls.Lift = FAirshipPilotInput::QuantizeAxis(Axis(LiftAction));
		Controls.Strafe = FAirshipPilotInput::QuantizeAxis(Axis(StrafeAction));
		Controls.SetButton(Airship::Button_Boost, Button(BoostAction));
		Controls.SetButton(Airship::Button_Brake, Button(BrakeAction));
		Controls.SetButton(Airship::Button_Aim, Button(AimAction));

		// Galleon: W / S ring the engine telegraph (the order rides Throttle as a latched code), stations ride bit 4
		if (ControlScheme == EAirshipControlScheme::Galleon)
		{
			UpdateGalleonOrders(Axis(ThrottleAction), Button(AimAction), PC, Now);
			Controls.Throttle = AirshipGalleon::NotchToThrottle(GalleonNotch);
			Controls.SetButton(Airship::Button_Stations, bGalleonStations);
		}
	}

	bLocalAimValid = ComputeLocalAimPoint(LocalAimPoint);

	if (bLocalAimValid)
	{
		Controls.AimPoint = LocalAimPoint;
		Controls.SetButton(Airship::Button_HasAimPoint, true);
	}

	Flight->SetLocalInput(Controls);
}

bool AAirshipPawn::ComputeLocalAimPoint(FVector& OutAimPoint) const
{
	const AController* LocalController = GetController();
	const UWorld* World = GetWorld();

	if (!LocalController || !World)
	{
		return false;
	}

	FVector ViewLocation;
	FRotator ViewRotation;
	LocalController->GetPlayerViewPoint(ViewLocation, ViewRotation);

	const FVector End = ViewLocation + ViewRotation.Vector() * CannonAimTraceDistance;
	FCollisionQueryParams Params(SCENE_QUERY_STAT(AirshipAim), false, this);
	TArray<AActor*> Attached;
	GetAttachedActors(Attached);
	Params.AddIgnoredActors(Attached);

	FHitResult Hit;
	OutAimPoint = World->LineTraceSingleByChannel(Hit, ViewLocation, End, ECC_Visibility, Params) ? FVector(Hit.ImpactPoint) : End;
	return true;
}

void AAirshipPawn::OnLookInput(const FInputActionValue& Value)
{
	FVector2D Look = Value.Get<FVector2D>();

	// Same as the on-foot camera (AMyPlayerController2::Rotate): Options > Controls sensitivity and invert
	if (const UMyGameUserSettings* Settings = UMyGameUserSettings::GetMyGameUserSettings())
	{
		Look *= Settings->GetLookSensitivity();

		if (Settings->GetInvertLookX())
		{
			Look.X = -Look.X;
		}
		if (Settings->GetInvertLookY())
		{
			Look.Y = -Look.Y;
		}
	}

	AddControllerYawInput(static_cast<float>(Look.X));
	AddControllerPitchInput(static_cast<float>(Look.Y));

	if (!Look.IsNearlyZero() && GetWorld())
	{
		LastLookInputTime = GetWorld()->GetTimeSeconds();

		// Point & Fly: this frame's control rotation change is the player's look input, not a set from outside
		LastLookInputFrame = GFrameCounter;
	}
}

void AAirshipPawn::OnZoomInput(const FInputActionValue& Value)
{
	// Wheel up (+) = closer
	ZoomTarget = FMath::Clamp(ZoomTarget - Value.Get<float>() * CameraZoomStep, CameraArmMin, FMath::Max(CameraArmMin, CameraArmMax));
}

void AAirshipPawn::OnFireInput(const FInputActionValue& Value)
{
	RequestFire();
}

void AAirshipPawn::OnExitInput(const FInputActionValue& Value)
{
	if (HasAuthority())
	{
		UnboardPilot(false);
	}
	else
	{
		ServerRequestExit();
	}
}

void AAirshipPawn::ServerRequestExit_Implementation()
{
	const UWorld* World = GetWorld();
	const double Now = World ? World->GetTimeSeconds() : 0.0;

	if (!PilotCharacter || !GetController() || Now - LastExitRequestTime < UAirshipSettings::Get()->BoardCooldown)
	{
		return;
	}

	LastExitRequestTime = Now;
	UnboardPilot(false);
}


// =============================================================================
// Boarding
// =============================================================================

bool AAirshipPawn::GetMeshRestLocation(FName BoneOrSocket, FVector& OutHullLocal) const
{
	const USkeletalMesh* SkelMesh = Mesh ? Mesh->GetSkeletalMeshAsset() : nullptr;

	if (!SkelMesh || !HullCollision || BoneOrSocket.IsNone())
	{
		return false;
	}

	const FReferenceSkeleton& RefSkeleton = SkelMesh->GetRefSkeleton();
	FTransform MeshSpace;
	const int32 BoneIndex = RefSkeleton.FindBoneIndex(BoneOrSocket);

	if (BoneIndex != INDEX_NONE)
	{
		MeshSpace = FAnimationRuntime::GetComponentSpaceTransformRefPose(RefSkeleton, BoneIndex);
	}
	else if (const USkeletalMeshSocket* Socket = SkelMesh->FindSocket(BoneOrSocket))
	{
		const int32 SocketBone = RefSkeleton.FindBoneIndex(Socket->BoneName);

		if (SocketBone == INDEX_NONE)
		{
			return false;
		}
		MeshSpace = Socket->GetSocketLocalTransform() * FAnimationRuntime::GetComponentSpaceTransformRefPose(RefSkeleton, SocketBone);
	}
	else
	{
		return false;
	}

	// Rest pose: the bones don't move relative to the hull while alive (and a server that doesn't render never
	// refreshes them anyway)
	const FTransform MeshToHull = Mesh->GetComponentTransform().GetRelativeTransform(HullCollision->GetComponentTransform());
	OutHullLocal = (MeshSpace * MeshToHull).GetLocation();
	return true;
}

FVector AAirshipPawn::GetPilotSeatLocal() const
{
	return PilotSeatLocal;
}

FVector AAirshipPawn::GetPilotSeatLocation() const
{
	return HullCollision ? HullCollision->GetComponentTransform().TransformPosition(PilotSeatLocal) : GetActorLocation();
}

FTransform AAirshipPawn::GetPilotSeatRelativeTransform(const ACharacter* Pilot) const
{
	// The seat is where the feet go; the actor location is the capsule centre. Facing the bow (+X).
	const float HalfHeight = (Pilot && Pilot->GetCapsuleComponent()) ? Pilot->GetCapsuleComponent()->GetScaledCapsuleHalfHeight() : 90.f;
	return FTransform(FRotator::ZeroRotator, PilotSeatLocal + FVector(0.0, 0.0, HalfHeight + PilotSeatClearance));
}

bool AAirshipPawn::CanBoard(const APawn* Candidate) const
{
	const ACharacter* Character = Cast<ACharacter>(Candidate);

	if (!HasAuthority() || bIsDead || PilotCharacter || !Character || !Character->GetPlayerState() || Character->IsActorBeingDestroyed())
	{
		return false;
	}

	if (Character->Implements<UMyCombatInterface>() && IMyCombatInterface::Execute_IsDead(const_cast<ACharacter*>(Character)))
	{
		return false;
	}

	return true;
}

bool AAirshipPawn::IsWithinBoardRange(const FVector& Location, float SeatDistance, float HullDistance) const
{
	if (SeatDistance > 0.f && FVector::DistSquared(Location, GetPilotSeatLocation()) <= FMath::Square(SeatDistance))
	{
		return true;
	}

	if (HullDistance > 0.f && HullCollision)
	{
		FVector Closest;
		const float Distance = HullCollision->GetClosestPointOnCollision(Location, Closest);

		// -1: no collision to measure; 0: inside
		if (Distance >= 0.f && Distance <= HullDistance)
		{
			return true;
		}
	}

	return false;
}

void AAirshipPawn::CancelPilotAbilities(ACharacter* Pilot)
{
	// Like AMyGameMode's respawn: the ASC is on the PlayerState and stays with the player
	UAbilitySystemComponent* ASC = UAbilitySystemGlobals::GetAbilitySystemComponentFromActor(Pilot);

	if (!ASC || ASC->GetAvatarActor() != Pilot)
	{
		return;
	}

	TArray<FGameplayAbilitySpecHandle> ToCancel;

	for (const FGameplayAbilitySpec& Spec : ASC->GetActivatableAbilities())
	{
		// Passives (GiveAbilityAndActivateOnce) keep running
		if (Spec.IsActive() && !Spec.RemoveAfterActivation)
		{
			ToCancel.Add(Spec.Handle);
		}
	}

	for (const FGameplayAbilitySpecHandle& Handle : ToCancel)
	{
		ASC->CancelAbilityHandle(Handle);
	}
}

bool AAirshipPawn::BoardPilot(ACharacter* Pilot, APlayerController* PC)
{
	if (!CanBoard(Pilot) || !PC || PC->GetPawn() != Pilot)
	{
		return false;
	}

	// Beam, boost, hover... end while the character is still the ASC's avatar (they need its controller)
	CancelPilotAbilities(Pilot);

	// Re-possessing the character later refills Health / Mana (AMyCharPlayer::PossessedBy): keep them
	bHasSavedPilotVitals = false;

	if (const UAbilitySystemComponent* PilotASC = UAbilitySystemGlobals::GetAbilitySystemComponentFromActor(Pilot))
	{
		if (PilotASC->HasAttributeSetForAttribute(UMyAttributeSet::GetHealthAttribute()))
		{
			SavedPilotHealth = PilotASC->GetNumericAttribute(UMyAttributeSet::GetHealthAttribute());
			SavedPilotMana = PilotASC->GetNumericAttribute(UMyAttributeSet::GetManaAttribute());
			bHasSavedPilotVitals = true;
		}
	}

	if (UCharacterMovementComponent* Move = Pilot->GetCharacterMovement())
	{
		Move->StopMovementImmediately();
		Move->DisableMovement();
	}

	// No collision aboard: the capsule would push the hull's physics body (clients do the same in UpdatePassengerCollision)
	bPilotHadCollision = Pilot->GetActorEnableCollision();
	Pilot->SetActorEnableCollision(false);

	// On the root: attachment replication resolves the parent's root component
	Pilot->AttachToComponent(HullCollision, FAttachmentTransformRules::SnapToTargetNotIncludingScale);
	Pilot->SetActorRelativeTransform(GetPilotSeatRelativeTransform(Pilot));

	// Attached actors don't share the ship's relevancy
	bPilotWasAlwaysRelevant = Pilot->bAlwaysRelevant;
	Pilot->bAlwaysRelevant = true;

	PilotCharacter = Pilot;
	PilotController = PC;
	OnRep_PilotCharacter();

	// Attached: a passenger. Its capsule goes query only once its collision is back on (exit), not now: with the actor's
	// collision off that switch would destroy the capsule's body and make none (it would fall through the deck)
	RefreshPassengers();

	PC->Possess(this);

	if (GetController() != PC)
	{
		UE_LOG(LogAirshipPawn, Warning, TEXT("%s: %s could not possess the ship"), *GetName(), *PC->GetName());
		UnboardPilot(false);
		return false;
	}

	return true;
}

void AAirshipPawn::UnboardPilot(bool bEject)
{
	if (!HasAuthority() || !PilotCharacter || bUnboarding)
	{
		return;
	}

	TGuardValue<bool> UnboardingGuard(bUnboarding, true);

	ACharacter* Pilot = PilotCharacter;
	APlayerController* PC = PilotController.Get();
	PilotCharacter = nullptr;
	PilotController.Reset();

	const FTransform HullTM = HullCollision->GetComponentTransform();
	const FVector Up = HullTM.GetUnitAxis(EAxis::Z);
	const FVector ShipVelocity = HullCollision->IsSimulatingPhysics() ? HullCollision->GetPhysicsLinearVelocity() : GetVelocity();
	const float HalfHeight = Pilot->GetCapsuleComponent() ? Pilot->GetCapsuleComponent()->GetScaledCapsuleHalfHeight() : 90.f;

	// Next to the seat, dropped onto the deck (a trace on the hull only)
	FVector Exit = HullTM.TransformPosition(PilotSeatLocal + ExitOffset);
	FHitResult DeckHit;
	FCollisionQueryParams Params(SCENE_QUERY_STAT(AirshipExit), false);

	if (HullCollision->LineTraceComponent(DeckHit, Exit + Up * 300.f, Exit - Up * 600.f, Params))
	{
		Exit = DeckHit.ImpactPoint;
	}
	Exit += FVector(0.0, 0.0, HalfHeight + PilotSeatClearance);

	Pilot->DetachFromActor(FDetachmentTransformRules::KeepWorldTransform);
	Pilot->SetActorLocationAndRotation(Exit, FRotator(0.0, GetActorRotation().Yaw, 0.0), false, nullptr, ETeleportType::TeleportPhysics);
	Pilot->bAlwaysRelevant = bPilotWasAlwaysRelevant;
	Pilot->SetActorEnableCollision(bPilotHadCollision);

	// Safety net: a body something destroyed while the collision was off (the movement sweeps need it)
	UAirshipSubsystem::RepairPhysicsState(Pilot);

	if (UCharacterMovementComponent* Move = Pilot->GetCharacterMovement())
	{
		Move->SetMovementMode(MOVE_Falling);
	}

	// Before the next physics step: on the deck (or thrown clear next to it) it is a passenger, its capsule query only
	// (switched now, with its collision on: a valid QueryOnly body)
	RefreshPassengers();

	// Back to the character (unless the player already went elsewhere)
	if (PC && !PC->IsActorBeingDestroyed() && (PC->GetPawn() == this || PC->GetPawn() == nullptr) && !Pilot->IsActorBeingDestroyed())
	{
		PC->Possess(Pilot);
	}

	// After the possession, which refilled them
	if (bHasSavedPilotVitals)
	{
		if (UAbilitySystemComponent* PilotASC = UAbilitySystemGlobals::GetAbilitySystemComponentFromActor(Pilot))
		{
			PilotASC->SetNumericAttributeBase(UMyAttributeSet::GetHealthAttribute(), SavedPilotHealth);
			PilotASC->SetNumericAttributeBase(UMyAttributeSet::GetManaAttribute(), SavedPilotMana);
		}
		bHasSavedPilotVitals = false;
	}

	FVector Launch = ShipVelocity;

	if (bEject)
	{
		const FVector Side = HullTM.TransformVectorNoScale(FVector(0.0, ExitOffset.Y >= 0.0 ? 1.0 : -1.0, 0.0));
		Launch += FVector(0.0, 0.0, EjectUpSpeed) + Side * EjectSideSpeed;
	}

	Pilot->LaunchCharacter(Launch, true, true);

	OnRep_PilotCharacter();
}

void AAirshipPawn::OnRep_PilotCharacter()
{
	ACharacter* NewPilot = PilotCharacter;

	if (KnownPilot.Get() == NewPilot)
	{
		return;
	}

	KnownPilot = NewPilot;

	// Every machine (PossessedBy / UnPossessed only run on the server): the schemes' runtime state starts fresh with
	// each pilot (a drift in progress is dropped without a turbo; Galleon rings STOP)
	if (Flight)
	{
		Flight->ResetSchemeState(false);
	}
	ResetSchemePilotState(false);

	// Clients: no collision while attached (the old pilot gets it back in UpdatePassengerCollision once detached)
	if (!HasAuthority() && NewPilot && NewPilot->GetActorEnableCollision())
	{
		NewPilot->SetActorEnableCollision(false);
		PassengersWithCollisionOff.AddUnique(NewPilot);
	}

	OnPilotChanged.Broadcast(this, NewPilot);
}

void AAirshipPawn::UpdatePassengerCollision()
{
	// Attachment and PilotCharacter replicate separately: catch an attached character either way
	if (HullCollision)
	{
		for (const TObjectPtr<USceneComponent>& Child : HullCollision->GetAttachChildren())
		{
			ACharacter* Passenger = Child ? Cast<ACharacter>(Child->GetOwner()) : nullptr;

			if (Passenger && Passenger->GetActorEnableCollision())
			{
				Passenger->SetActorEnableCollision(false);
				PassengersWithCollisionOff.AddUnique(Passenger);
			}
		}
	}

	bool bRestored = false;

	for (int32 Index = PassengersWithCollisionOff.Num() - 1; Index >= 0; --Index)
	{
		ACharacter* Passenger = PassengersWithCollisionOff[Index].Get();

		if (!Passenger)
		{
			PassengersWithCollisionOff.RemoveAt(Index);
			continue;
		}

		if (Passenger != PilotCharacter && !Passenger->IsAttachedTo(this))
		{
			Passenger->SetActorEnableCollision(true);
			UAirshipSubsystem::RepairPhysicsState(Passenger);
			PassengersWithCollisionOff.RemoveAt(Index);
			bRestored = true;
		}
	}

	// The old pilot stands on the deck now: passenger collision before the next physics step
	if (bRestored)
	{
		RefreshPassengers();
	}
}

void AAirshipPawn::RefreshPassengers() const
{
	if (UAirshipSubsystem* Subsystem = UAirshipSubsystem::Get(this))
	{
		Subsystem->UpdatePassengers();
	}
}

bool AAirshipPawn::IsPassengerCandidate(const ACharacter* Character) const
{
	if (!bPassengersQueryOnly || !Character || !HullCollision || Character->IsActorBeingDestroyed() || IsActorBeingDestroyed())
	{
		return false;
	}

	// The pilot (actor collision off while attached; the capsule's own setting is what matters when it steps off)
	if (Character->IsAttachedTo(this))
	{
		return true;
	}

	// Standing on something: on this ship (HullCollision, or an actor attached to it), or elsewhere
	if (Character->GetMovementBaseObject())
	{
		const AActor* BaseActor = APawn::GetMovementBaseActor(Character);
		return BaseActor && (BaseActor == this || BaseActor->IsAttachedTo(this));
	}

	// No base (jumping on deck, stepping off, falling onto it, the ejected pilot): near the hull. Query only changes
	// nothing for the character's own sweeps, so a wide zone costs nothing. Alive or dead alike (see the header).
	return HullCollision->Bounds.GetBox().ExpandBy(PassengerZoneMargin).IsInsideOrOn(Character->GetActorLocation());
}

TArray<ACharacter*> AAirshipPawn::GetPassengers() const
{
	const UAirshipSubsystem* Subsystem = UAirshipSubsystem::Get(this);
	return Subsystem ? Subsystem->GetPassengers(this) : TArray<ACharacter*>();
}


// =============================================================================
// Cannons
// =============================================================================

void AAirshipPawn::RefreshCannonGeometry()
{
	for (int32 Cannon = 0; Cannon < Airship::NumCannons; ++Cannon)
	{
		FVector Muzzle;

		if (!GetMeshRestLocation(CannonMuzzleSockets.IsValidIndex(Cannon) ? CannonMuzzleSockets[Cannon] : NAME_None, Muzzle))
		{
			Muzzle = CannonMuzzleFallback.IsValidIndex(Cannon) ? CannonMuzzleFallback[Cannon] : FVector::ZeroVector;
		}

		CannonMuzzleLocal[Cannon] = Muzzle;

		// Rest firing direction: barrel -> muzzle, else straight outboard
		FVector Dir = Airship::IsPortCannon(Cannon) ? FVector(0.0, -1.0, 0.0) : FVector(0.0, 1.0, 0.0);
		FVector Barrel;

		if (GetMeshRestLocation(CannonBarrelSockets.IsValidIndex(Cannon) ? CannonBarrelSockets[Cannon] : NAME_None, Barrel))
		{
			const FVector FromBarrel = Muzzle - Barrel;

			if (FromBarrel.SizeSquared() > 1.0)
			{
				Dir = FromBarrel.GetSafeNormal();
			}
		}

		CannonRestDirLocal[Cannon] = Dir;
	}

	if (!GetMeshRestLocation(PilotSeatSocket, PilotSeatLocal))
	{
		PilotSeatLocal = PilotSeatFallback;
	}
}

FVector AAirshipPawn::GetCannonMuzzleLocal(int32 Cannon) const
{
	return CannonMuzzleLocal[FMath::Clamp(Cannon, 0, Airship::NumCannons - 1)];
}

FVector AAirshipPawn::GetCannonRestDirLocal(int32 Cannon) const
{
	return CannonRestDirLocal[FMath::Clamp(Cannon, 0, Airship::NumCannons - 1)];
}

float AAirshipPawn::GetCannonReloadAlpha(EAirshipSide Side) const
{
	const UWorld* World = GetWorld();

	if (!World || CannonCooldown <= 0.f)
	{
		return 1.f;
	}

	// The server's own clock, or the pilot client's prediction clock (it only asks once that one is done)
	const int32 SideIndex = AirshipPawnPrivate::SideIndex(Side);
	const double LastFire = HasAuthority() ? LastSideFireTime[SideIndex] : LastPredictedFireTime[SideIndex];
	return FMath::Clamp(static_cast<float>((World->GetTimeSeconds() - LastFire) / CannonCooldown), 0.f, 1.f);
}

void AAirshipPawn::ComputeCannonAim(int32 Cannon, const FVector& Target, float& OutYawDeg, float& OutElevDeg) const
{
	ComputeCannonAimRaw(Cannon, Target, OutYawDeg, OutElevDeg);
	OutYawDeg = FMath::Clamp(OutYawDeg, -CannonYawLimitDeg, CannonYawLimitDeg);
	OutElevDeg = FMath::Clamp(OutElevDeg, CannonElevMinDeg, CannonElevMaxDeg);
}

void AAirshipPawn::ComputeCannonAimRaw(int32 Cannon, const FVector& Target, float& OutYawDeg, float& OutElevDeg) const
{
	OutYawDeg = 0.f;
	OutElevDeg = 0.f;

	if (!HullCollision)
	{
		return;
	}

	const FTransform HullTM = HullCollision->GetComponentTransform();
	FVector ToTarget = HullTM.InverseTransformVectorNoScale(Target - HullTM.TransformPosition(GetCannonMuzzleLocal(Cannon)));

	if (!ToTarget.Normalize())
	{
		return;
	}

	const FVector Rest = GetCannonRestDirLocal(Cannon);
	const FVector RestFlat = FVector(Rest.X, Rest.Y, 0.0).GetSafeNormal();
	const FVector TargetFlat(ToTarget.X, ToTarget.Y, 0.0);

	// Signed angle about hull +Z from the rest direction (the rig turns the carriage the same way)
	const double YawRad = FMath::Atan2(FVector::CrossProduct(RestFlat, TargetFlat).Z, FVector::DotProduct(RestFlat, TargetFlat));
	const double ElevRad = FMath::Atan2(ToTarget.Z, TargetFlat.Size());

	OutYawDeg = static_cast<float>(FMath::RadiansToDegrees(YawRad));
	OutElevDeg = static_cast<float>(FMath::RadiansToDegrees(ElevRad));
}

bool AAirshipPawn::IsAimInCannonArc(EAirshipSide Side, const FVector& AimPoint) const
{
	for (int32 Cannon = 0; Cannon < Airship::NumCannons; ++Cannon)
	{
		if (AirshipPawnPrivate::CannonSide(Cannon) != Side)
		{
			continue;
		}

		float YawDeg = 0.f;
		float ElevDeg = 0.f;
		ComputeCannonAimRaw(Cannon, AimPoint, YawDeg, ElevDeg);

		if (FMath::Abs(YawDeg) <= CannonYawLimitDeg && ElevDeg >= CannonElevMinDeg && ElevDeg <= CannonElevMaxDeg)
		{
			return true;
		}
	}

	return false;
}

FVector AAirshipPawn::GetCannonDirLocal(int32 Cannon, float YawDeg, float ElevDeg) const
{
	const FVector Rest = GetCannonRestDirLocal(Cannon);
	const FVector RestFlat = FVector(Rest.X, Rest.Y, 0.0).GetSafeNormal();
	const FVector Yawed = FQuat(FVector::UpVector, FMath::DegreesToRadians(YawDeg)).RotateVector(RestFlat);
	const float Elev = FMath::DegreesToRadians(ElevDeg);
	return (Yawed * FMath::Cos(Elev) + FVector::UpVector * FMath::Sin(Elev)).GetSafeNormal();
}

EAirshipSide AAirshipPawn::ComputeAimSide(const FVector& AimPoint) const
{
	if (!HullCollision)
	{
		return AimSide;
	}

	const double LocalY = HullCollision->GetComponentTransform().InverseTransformPositionNoScale(AimPoint).Y;

	if (AimSide == EAirshipSide::Port && LocalY > AimSideHysteresis)
	{
		return EAirshipSide::Starboard;
	}

	if (AimSide == EAirshipSide::Starboard && LocalY < -AimSideHysteresis)
	{
		return EAirshipSide::Port;
	}

	return AimSide;
}

void AAirshipPawn::UpdateCannonAim()
{
	// The pilot's machine aims from its own camera, the others from the replicated aim point
	bool bHasAim = false;
	FVector Aim = FVector::ZeroVector;

	if (IsLocallyControlled())
	{
		bHasAim = bLocalAimValid;
		Aim = LocalAimPoint;
	}
	else if (Flight)
	{
		const FAirshipPilotInput& Controls = Flight->GetCurrentControls();
		bHasAim = Controls.HasAimPoint();
		Aim = Controls.AimPoint;
	}

	if (bHasAim && !bIsDead)
	{
		AimSide = ComputeAimSide(Aim);
	}

	for (int32 Cannon = 0; Cannon < Airship::NumCannons; ++Cannon)
	{
		if (bHasAim && !bIsDead && AirshipPawnPrivate::CannonSide(Cannon) == AimSide)
		{
			ComputeCannonAim(Cannon, Aim, CannonAimYawDeg[Cannon], CannonAimElevDeg[Cannon]);
		}
		else
		{
			// The other side rests
			CannonAimYawDeg[Cannon] = 0.f;
			CannonAimElevDeg[Cannon] = 0.f;
		}
	}
}

void AAirshipPawn::RequestFire()
{
	if (bIsDead || !IsLocallyControlled() || !GetWorld())
	{
		return;
	}

	FVector Aim;

	if (!ComputeLocalAimPoint(Aim))
	{
		return;
	}

	const EAirshipSide Side = ComputeAimSide(Aim);

	if (HasAuthority())
	{
		FireCannons(Side, Aim);
		return;
	}

	// The pilot's client shows its shot at once and asks only when its own reload is done (the server allows 0.1 s of
	// clock difference), so every real shot has a prediction and the multicast skips exactly that one
	const int32 SideIndex = AirshipPawnPrivate::SideIndex(Side);
	const double Now = GetWorld()->GetTimeSeconds();

	if (Now - LastPredictedFireTime[SideIndex] < CannonCooldown)
	{
		return;
	}

	LastPredictedFireTime[SideIndex] = Now;
	bPredictedShotPending[SideIndex] = true;
	HandleCannonsFired(Side);
	ServerFireCannons(Side, Aim);
}

void AAirshipPawn::ServerFireCannons_Implementation(EAirshipSide Side, FVector_NetQuantize AimPoint)
{
	// Only the pilot (the owning connection) can call it
	if (PilotCharacter && GetController())
	{
		FireCannons(Side, AimPoint);
	}
}

void AAirshipPawn::FireCannons(EAirshipSide Side, const FVector& AimPoint)
{
	UWorld* World = GetWorld();

	if (!HasAuthority() || bIsDead || !World || !HullCollision)
	{
		return;
	}

	// Small tolerance: the client's own cooldown runs on its clock
	const int32 SideIndex = AirshipPawnPrivate::SideIndex(Side);
	const double Now = World->GetTimeSeconds();

	if (Now - LastSideFireTime[SideIndex] < FMath::Max(CannonCooldown - 0.1f, 0.f))
	{
		return;
	}

	LastSideFireTime[SideIndex] = Now;

	// The project's damage: a spec from the ship's ASC, SetByCaller SetDamageByCaller (sources capture the ship)
	FGameplayEffectSpecHandle Spec;

	if (AbilitySystemComponent)
	{
		FGameplayEffectContextHandle Context = AbilitySystemComponent->MakeEffectContext();
		Context.AddInstigator(this, this);
		Context.AddSourceObject(this);
		const TSubclassOf<UGameplayEffect> EffectClass = DamageEffectClass ? DamageEffectClass : TSubclassOf<UGameplayEffect>(UAirshipDamageEffect::StaticClass());
		Spec = AbilitySystemComponent->MakeOutgoingSpec(EffectClass, static_cast<float>(ShipLevel), Context);

		if (Spec.IsValid())
		{
			Spec.Data->SetSetByCallerMagnitude(MyTags::SetDamageByCaller, CannonballDamage);
		}
	}

	const FTransform HullTM = HullCollision->GetComponentTransform();
	const bool bSimulating = HullCollision->IsSimulatingPhysics();
	const FVector ShipVelocity = bSimulating ? HullCollision->GetPhysicsLinearVelocity() : GetVelocity();
	const FVector AngularVelocity = bSimulating ? HullCollision->GetPhysicsAngularVelocityInRadians() : FVector::ZeroVector;
	const FVector COM = bSimulating ? HullCollision->GetCenterOfMass() : GetActorLocation();
	UClass* BallClass = CannonballClass ? CannonballClass.Get() : AAirshipCannonball::StaticClass();

	AAirshipCannonball* Fired[2] = { nullptr, nullptr };
	int32 NumFired = 0;

	for (int32 Cannon = 0; Cannon < Airship::NumCannons; ++Cannon)
	{
		if (AirshipPawnPrivate::CannonSide(Cannon) != Side)
		{
			continue;
		}

		float YawDeg = 0.f;
		float ElevDeg = 0.f;
		ComputeCannonAim(Cannon, AimPoint, YawDeg, ElevDeg);

		FVector Dir = HullTM.TransformVectorNoScale(GetCannonDirLocal(Cannon, YawDeg, ElevDeg));

		if (CannonSpreadDeg > 0.f)
		{
			Dir = FMath::VRandCone(Dir, FMath::DegreesToRadians(CannonSpreadDeg));
		}

		// The ball keeps the muzzle's own velocity (the ship moving and turning)
		const FVector Muzzle = HullTM.TransformPosition(GetCannonMuzzleLocal(Cannon));
		const FVector MuzzleVelocity = ShipVelocity + FVector::CrossProduct(AngularVelocity, Muzzle - COM);
		const FVector Velocity = Dir * CannonballSpeed + MuzzleVelocity;
		const FTransform SpawnTM(Velocity.Rotation(), Muzzle + Dir * CannonSpawnForwardOffset);

		AAirshipCannonball* Ball = World->SpawnActorDeferred<AAirshipCannonball>(BallClass, SpawnTM, this, this, ESpawnActorCollisionHandlingMethod::AlwaysSpawn);

		if (!Ball)
		{
			continue;
		}

		Ball->InitCannonball(this, Velocity, Spec, CannonballDamage);
		Ball->FinishSpawning(SpawnTM);

		if (NumFired < 2)
		{
			Fired[NumFired++] = Ball;
		}
	}

	if (Fired[0] && Fired[1])
	{
		Fired[0]->IgnoreActor(Fired[1]);
		Fired[1]->IgnoreActor(Fired[0]);
	}

	MulticastCannonsFired(Side);
}

void AAirshipPawn::MulticastCannonsFired_Implementation(EAirshipSide Side)
{
	// The pilot's client played this shot when it pressed fire (a prediction the server dropped expires)
	if (IsLocallyControlled() && !HasAuthority() && GetWorld())
	{
		const int32 SideIndex = AirshipPawnPrivate::SideIndex(Side);
		const double SincePredicted = GetWorld()->GetTimeSeconds() - LastPredictedFireTime[SideIndex];
		const bool bPending = bPredictedShotPending[SideIndex];
		bPredictedShotPending[SideIndex] = false;

		if (bPending && SincePredicted < CannonCooldown + 0.5)
		{
			return;
		}
	}

	HandleCannonsFired(Side);
}

void AAirshipPawn::HandleCannonsFired(EAirshipSide Side)
{
	if (!HullCollision)
	{
		return;
	}

	// The pilot's machine (the host's real shot, a client's predicted one): the broadside punch, and Galleon's beam watch
	// may give broadside stations for a while
	if (IsLocallyControlled())
	{
		LastOwnBroadsideTime = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0;
		AddFeedback(FeedbackOwnBroadside);
	}

	const FTransform HullTM = HullCollision->GetComponentTransform();
	const bool bSimulating = HullCollision->IsSimulatingPhysics();
	const float Mass = bSimulating ? HullCollision->GetMass() : 0.f;

	for (int32 Cannon = 0; Cannon < Airship::NumCannons; ++Cannon)
	{
		if (AirshipPawnPrivate::CannonSide(Cannon) != Side)
		{
			continue;
		}

		// The anim instance starts the recoil when the count goes up
		++CannonFireCount[Cannon];

		const FVector Muzzle = HullTM.TransformPosition(GetCannonMuzzleLocal(Cannon));
		const FVector Dir = HullTM.TransformVectorNoScale(GetCannonDirLocal(Cannon, CannonAimYawDeg[Cannon], CannonAimElevDeg[Cannon]));

		if (MuzzleFX && GetNetMode() != NM_DedicatedServer)
		{
			const FName Socket = CannonMuzzleSockets.IsValidIndex(Cannon) ? CannonMuzzleSockets[Cannon] : NAME_None;

			if (Mesh && !Socket.IsNone() && Mesh->DoesSocketExist(Socket))
			{
				UNiagaraFunctionLibrary::SpawnSystemAttached(MuzzleFX, Mesh, Socket, FVector::ZeroVector, FRotator::ZeroRotator, EAttachLocation::SnapToTarget, true);
			}
			else
			{
				UNiagaraFunctionLibrary::SpawnSystemAtLocation(this, MuzzleFX, Muzzle, Dir.Rotation());
			}
		}

		// Recoil kick on the hull (the server's is the real one; clients get corrected toward it)
		if (bSimulating && CannonRecoilImpulseDV > 0.f && Mass > 0.f)
		{
			HullCollision->AddImpulseAtLocation(-Dir * Mass * CannonRecoilImpulseDV, Muzzle);
		}
	}

	BP_OnCannonsFired(Side);
}


// =============================================================================
// FX
// =============================================================================

void AAirshipPawn::UpdateFX()
{
	// Dead: HandleDeath turned the jets off
	if (GetNetMode() == NM_DedicatedServer || bIsDead)
	{
		return;
	}

	const FAirshipCosmeticState& C = GetCosmeticState();
	UNiagaraComponent* const Thrusters[Airship::NumPods] = { ThrusterFX_FL, ThrusterFX_FR, ThrusterFX_RL, ThrusterFX_RR };
	UNiagaraComponent* const Turbines[Airship::NumFans] = { TurbineFX_L, TurbineFX_R };

	for (int32 Pod = 0; Pod < Airship::NumPods; ++Pod)
	{
		if (UNiagaraComponent* FX = Thrusters[Pod]; FX && FX->GetAsset())
		{
			FX->SetVariableFloat(FXThrustParam, C.PodThrustAlpha[Pod]);
			// v1: the shaped boost; Sky Racer adds the drift charge glow and the turbo burn
			FX->SetVariableFloat(FXBoostParam, C.FXBoost);
		}
	}

	for (int32 Fan = 0; Fan < Airship::NumFans; ++Fan)
	{
		if (UNiagaraComponent* FX = Turbines[Fan]; FX && FX->GetAsset())
		{
			FX->SetVariableFloat(FXThrustParam, FMath::Max(FMath::Abs(C.FanThrust[Fan]), C.FXFanThrust));
			FX->SetVariableFloat(FXBoostParam, C.FXBoost);
		}
	}
}


// =============================================================================
// Camera
// =============================================================================

void AAirshipPawn::UpdateCamera(float DeltaSeconds)
{
	APlayerController* PC = Cast<APlayerController>(GetController());
	const UWorld* World = GetWorld();

	if (!PC || !World || !CameraBoom || !Camera)
	{
		return;
	}

	const FAirshipCosmeticState& C = GetCosmeticState();
	const double Now = World->GetTimeSeconds();
	FRotator Control = PC->GetControlRotation();
	bool bControlChanged = false;

	if (ControlScheme == EAirshipControlScheme::Galleon)
	{
		// Ship-relative camera (it turns with the ship; it consumes bPendingCameraReset)
		Control.Pitch = FRotator::NormalizeAxis(Control.Pitch);
		UpdateGalleonCamera(DeltaSeconds, Now, C, Control);
		bControlChanged = true;
	}
	else
	{
		if (bPendingCameraReset)
		{
			Control = FRotator(CameraDefaultPitch, GetActorRotation().Yaw, 0.0);
			bControlChanged = true;
			bPendingCameraReset = false;
		}

		Control.Pitch = FRotator::NormalizeAxis(Control.Pitch);

		// Recenter behind the ship when the pilot doesn't look around (Sky Racer: the chase camera's auto-follow;
		// Point & Fly: off, RecenterSpeed 0, the camera is the steering)
		if (RecenterSpeed > 0.f && Now - LastLookInputTime > RecenterDelay && C.ForwardSpeed > RecenterMinSpeed && !C.bAiming)
		{
			const double Alpha = 1.0 - FMath::Exp(-RecenterSpeed * DeltaSeconds);

			if (ControlScheme == EAirshipControlScheme::SkyRacer)
			{
				UpdateSkyRacerFollow(DeltaSeconds, Alpha, Control);
			}
			else
			{
				Control.Yaw += FRotator::NormalizeAxis(GetActorRotation().Yaw - Control.Yaw) * Alpha;
				Control.Pitch += (CameraDefaultPitch - Control.Pitch) * Alpha;
			}
			bControlChanged = true;
		}
	}

	const double ClampedPitch = FMath::Clamp(Control.Pitch, static_cast<double>(CameraPitchMin), static_cast<double>(CameraPitchMax));

	if (!FMath::IsNearlyEqual(ClampedPitch, Control.Pitch))
	{
		Control.Pitch = ClampedPitch;
		bControlChanged = true;
	}

	if (bControlChanged)
	{
		Control.Roll = 0.0;
		PC->SetControlRotation(Control);
	}

	// Zoom, and the camera falls back on boost (Sky Racer: and with a fresh mini-turbo)
	const float TurboArm = ControlScheme == EAirshipControlScheme::SkyRacer ? SkyTurboArmExtra * C.TurboAlpha : 0.f;
	const float ArmTarget = ZoomTarget + CameraBoostArmExtra * C.Boost + TurboArm;
	CameraBoom->TargetArmLength = FMath::FInterpTo(CameraBoom->TargetArmLength, ArmTarget, DeltaSeconds, CameraZoomInterpSpeed);

	// FOV: speed, boost, aim, plus the player's FOV setting (AMyPlayerController2 applies it once per change)
	const float SpeedAlpha = FMath::Clamp((C.ForwardSpeed - SpeedFOVStart) / FMath::Max(SpeedFOVFull - SpeedFOVStart, 1.f), 0.f, 1.f);
	float TargetFOV = BaseFOV + SpeedFOVExtra * SpeedAlpha + BoostFOVExtra * C.Boost + (C.bAiming ? AimFOVOffset : 0.f);

	if (const UMyGameUserSettings* Settings = UMyGameUserSettings::GetMyGameUserSettings())
	{
		TargetFOV += Settings->GetFieldOfView() - UMyGameUserSettings::DefaultFieldOfView;
	}

	// The feedback's FOV punch goes on after the interpolation (it isn't smoothed away). With no punch and no FOVMaxDeg
	// this is v1's Clamp(FInterpTo(FieldOfView, TargetFOV), 20, 170). A FOV someone else wrote is followed, as v1 does.
	if (!FMath::IsNearlyEqual(Camera->FieldOfView, LastAppliedFOV, 0.01f))
	{
		SmoothedFOV = Camera->FieldOfView - CameraFOVKick;
	}

	const float MaxFOV = FOVMaxDeg > 0.f ? FOVMaxDeg : 170.f;
	SmoothedFOV = FMath::Clamp(FMath::FInterpTo(SmoothedFOV, TargetFOV, DeltaSeconds, FOVInterpSpeed), 20.f, MaxFOV);
	LastAppliedFOV = FMath::Clamp(SmoothedFOV + CameraFOVKick, 20.f, MaxFOV);
	Camera->SetFieldOfView(LastAppliedFOV);

	// Shake, camera roll, rumble, events
	UpdateFeedback(DeltaSeconds, C);
}

void AAirshipPawn::UpdateGalleonCamera(float DeltaSeconds, double Now, const FAirshipCosmeticState& C, FRotator& Control)
{
	using namespace AirshipPawnPrivate;

	// The hull as this machine sees it
	const float HullYaw = static_cast<float>(GetActorRotation().Yaw);
	float Offset = 0.f;

	if (bPendingCameraReset || !bGalleonCamInit)
	{
		GalleonLookAhead = 0.f;
		Control = FRotator(CameraDefaultPitch, HullYaw, 0.f);
		bPendingCameraReset = false;
		bGalleonCamInit = true;
	}
	else
	{
		// The offset from the hull, this frame's mouse included: the camera turns with the ship
		Offset = WrapDeg(static_cast<float>(Control.Yaw) - GalleonLastHullYaw - GalleonLastLookAhead);
	}

	// Beam watch (updated at the start of GatherLocalInput from the same offset) never recentres; otherwise the view
	// eases back behind the ship, slow and majestic
	if (!bGalleonBeamWatch && !C.bAiming && RecenterSpeed > 0.f && Now - LastLookInputTime > RecenterDelay && C.ForwardSpeed > RecenterMinSpeed)
	{
		const float Alpha = 1.f - FMath::Exp(-RecenterSpeed * DeltaSeconds);
		Offset -= Offset * Alpha;
		Control.Pitch += (CameraDefaultPitch - Control.Pitch) * Alpha;
	}

	// Look into the turn from the pilot's own shaped helm (it moves at once on any connection)
	const float LookAheadTarget = (bGalleonBeamWatch || C.bAiming) ? 0.f : GalleonLookAheadDeg * (Flight ? Flight->GetShapedSteer() : 0.f);
	GalleonLookAhead = ApproachExp(GalleonLookAhead, LookAheadTarget, DeltaSeconds, GalleonLookAheadTau);
	GalleonCamOffsetYaw = Offset;

	Control.Yaw = HullYaw + Offset + GalleonLookAhead;
	GalleonLastHullYaw = HullYaw;
	GalleonLastLookAhead = GalleonLookAhead;
}

void AAirshipPawn::UpdateSkyRacerFollow(float DeltaSeconds, double Alpha, FRotator& Control) const
{
	// The turn this machine's own controls command now (no latency), looked into
	const float Rate = Flight ? Flight->GetPilotYawRateCmdDeg() : 0.f;
	const float LookDeg = FMath::Clamp(SkyLookIntoTurnTime * Rate, -SkyLookIntoTurnMaxDeg, SkyLookIntoTurnMaxDeg);

	// The slip of the hull copy on this machine (+ = nose right of the velocity): a share of it shows the slide
	const FVector HullVelocity = (HullCollision && HullCollision->IsSimulatingPhysics()) ? HullCollision->GetPhysicsLinearVelocity() : GetVelocity();
	const FRotator HullRotation = GetActorRotation();
	const FVector LocalVelocity = HullRotation.UnrotateVector(HullVelocity);
	const double SlipDeg = LocalVelocity.X > 300.0 ? FMath::RadiansToDegrees(FMath::Atan2(-LocalVelocity.Y, LocalVelocity.X)) : 0.0;
	const double TargetYaw = HullRotation.Yaw + LookDeg - SkyCamSlipShare * SlipDeg;

	// Look down into a dive
	const double DiveMS = FMath::Max(0.0, -HullVelocity.Z * 0.01);
	const double TargetPitch = CameraDefaultPitch - FMath::Min(SkyCamDivePitchPerMS * DiveMS, static_cast<double>(SkyCamDivePitchMaxDeg));

	// The control yaw also turns at the commanded rate: no follow lag in a steady turn
	if (bSkyCamYawRateFF)
	{
		Control.Yaw += Rate * DeltaSeconds;
	}

	Control.Yaw += FRotator::NormalizeAxis(TargetYaw - Control.Yaw) * Alpha;
	Control.Pitch += (TargetPitch - Control.Pitch) * Alpha;
}


// =============================================================================
// Damage and death
// =============================================================================

void AAirshipPawn::ApplyShipDamage(float Damage)
{
	if (!HasAuthority() || bIsDead || Damage <= 0.f || !AbilitySystemComponent)
	{
		return;
	}

	FGameplayEffectContextHandle Context = AbilitySystemComponent->MakeEffectContext();
	Context.AddInstigator(this, this);

	const TSubclassOf<UGameplayEffect> EffectClass = DamageEffectClass ? DamageEffectClass : TSubclassOf<UGameplayEffect>(UAirshipDamageEffect::StaticClass());
	const FGameplayEffectSpecHandle Spec = AbilitySystemComponent->MakeOutgoingSpec(EffectClass, static_cast<float>(ShipLevel), Context);

	if (!Spec.IsValid())
	{
		return;
	}

	Spec.Data->SetSetByCallerMagnitude(MyTags::SetDamageByCaller, Damage);
	AbilitySystemComponent->ApplyGameplayEffectSpecToSelf(*Spec.Data.Get());
}

void AAirshipPawn::RecordPreStepState()
{
	// The flight update after this (same tick) notes this step's boost / drift kicks
	PreStepFlightKick = FVector::ZeroVector;

	if (!HullCollision || !HullCollision->IsSimulatingPhysics())
	{
		PreStepFrame = 0;
		return;
	}

	PreStepLinearVelocity = HullCollision->GetPhysicsLinearVelocity();
	PreStepAngularVelocity = HullCollision->GetPhysicsAngularVelocityInRadians();
	PreStepCenterOfMass = HullCollision->GetCenterOfMass();
	PreStepFrame = GFrameCounter;
}

void AAirshipPawn::LimitImpactResponse()
{
	// Hit events come after this frame's step; the record is from before it (no substepping in this project). Every
	// contact pair of the frame calls OnHullHit: the caps don't depend on the contact, so once per frame.
	const UWorld* World = GetWorld();

	if (!bLimitImpactResponse || !World || !HullCollision || !HullCollision->IsSimulatingPhysics() || PreStepFrame != GFrameCounter
		|| ImpactLimitFrame == GFrameCounter)
	{
		return;
	}

	ImpactLimitFrame = GFrameCounter;
	const double Now = World->GetTimeSeconds();
	const double FrameDt = FMath::Max(static_cast<double>(World->GetDeltaSeconds()), UE_KINDA_SMALL_NUMBER);
	const UPhysicsSettings* PhysicsSettings = UPhysicsSettings::Get();
	const double MaxStepDt = PhysicsSettings ? FMath::Max(static_cast<double>(PhysicsSettings->MaxPhysicsDeltaTime), UE_KINDA_SMALL_NUMBER) : 1.0 / 30.0;
	const double StepDt = FMath::Min(FrameDt, MaxStepDt);

	// One contact while its hits come less than ImpactEpisodeGap apart (2.5 frames at least: at a low frame rate not every
	// frame is a new contact). Its hits share the kick budgets, so a push-out over several frames (PBD turns the position
	// correction into velocity) can't add its kicks up; during a long contact (landed, scraping) they come back over
	// ImpactKickRefillTime, so a hit late in it is capped like the first one.
	double* const Budgets[] = { &ImpactUsedUp, &ImpactUsedHorizontal, &ImpactUsedSpeed, &ImpactUsedSpin };

	if (Now - ImpactEpisodeLast > FMath::Max(static_cast<double>(ImpactEpisodeGap), 2.5 * FrameDt))
	{
		for (double* Used : Budgets)
		{
			*Used = 0.0;
		}
	}
	else
	{
		const double Refill = (Now - ImpactEpisodeLast) / FMath::Max(static_cast<double>(ImpactKickRefillTime), 0.01);

		for (double* Used : Budgets)
		{
			*Used = FMath::Max(0.0, *Used - Refill);
		}
	}

	ImpactEpisodeLast = Now;

	// What flight forces and gravity can do in this step is never a kick (the wreck has no lift: nothing free upward).
	// Every gain is measured from this step's own start; the flight model's boost / drift kicks of this step are the
	// ship's own speed.
	const double Free = ImpactEpisodeAccel * StepDt;
	// Base fix 4e: upward its own rate (0 = ImpactEpisodeAccel, v1)
	const double FreeUp = bIsDead ? 0.0 : (ImpactEpisodeAccelUp > 0.f ? ImpactEpisodeAccelUp : ImpactEpisodeAccel) * StepDt;
	const double FreeSpin = FMath::DegreesToRadians(static_cast<double>(ImpactEpisodeSpinAccelDeg)) * StepDt;
	const FVector PreV = PreStepLinearVelocity + PreStepFlightKick;
	FVector V = HullCollision->GetPhysicsLinearVelocity();
	bool bChangedV = false;

	// Tolerance (cm/s, rad/s): a gain that fits is never rewritten
	constexpr double Tolerance = 0.01;

	// No bounce, no pop upward: above the upward speed it had (0 when falling)
	const double BaseUp = FMath::Max(PreV.Z, 0.0);
	const double GainUp = V.Z - BaseUp;
	const double AllowedUp = AirshipPawnPrivate::SpendKickBudget(GainUp, FreeUp, ImpactMaxReboundSpeed, ImpactUsedUp);

	if (AllowedUp < GainUp - Tolerance)
	{
		V.Z = BaseUp + AllowedUp;
		bChangedV = true;
	}

	// No sideways kick (a fall onto a slope or an edge, a glancing hit)
	const double BaseHorizontal = PreV.Size2D();
	const double Horizontal = V.Size2D();
	const double GainHorizontal = Horizontal - BaseHorizontal;
	const double AllowedHorizontal = AirshipPawnPrivate::SpendKickBudget(GainHorizontal, Free, ImpactMaxSpeedGain, ImpactUsedHorizontal);

	if (AllowedHorizontal < GainHorizontal - Tolerance && Horizontal > UE_KINDA_SMALL_NUMBER)
	{
		const double Scale = (BaseHorizontal + AllowedHorizontal) / Horizontal;
		V.X *= Scale;
		V.Y *= Scale;
		bChangedV = true;
	}

	// No pop downward either
	const double BaseSpeed = PreV.Size();
	const double Speed = V.Size();
	const double GainSpeed = Speed - BaseSpeed;
	const double AllowedSpeed = AirshipPawnPrivate::SpendKickBudget(GainSpeed, Free, ImpactMaxSpeedGain, ImpactUsedSpeed);

	if (AllowedSpeed < GainSpeed - Tolerance && Speed > UE_KINDA_SMALL_NUMBER)
	{
		V *= (BaseSpeed + AllowedSpeed) / Speed;
		bChangedV = true;
	}

	if (bChangedV)
	{
		HullCollision->SetPhysicsLinearVelocity(V);
	}

	// Spin kick (slowing down is free; a reversal or a turned spin axis counts from the stop)
	const FVector W = HullCollision->GetPhysicsAngularVelocityInRadians();
	const FVector Gain = AirshipPawnPrivate::SpinGain(PreStepAngularVelocity, W);
	const double GainSpin = Gain.Size();
	const double SpinCapacity = FMath::DegreesToRadians(static_cast<double>(bIsDead ? DeadImpactMaxSpinKickDeg : ImpactMaxSpinKickDeg));
	const double AllowedSpin = AirshipPawnPrivate::SpendKickBudget(GainSpin, FreeSpin, SpinCapacity, ImpactUsedSpin);

	if (AllowedSpin < GainSpin - FMath::DegreesToRadians(Tolerance) && GainSpin > UE_KINDA_SMALL_NUMBER)
	{
		HullCollision->SetPhysicsAngularVelocityInRadians(W - Gain * (1.0 - AllowedSpin / GainSpin));
	}
}

void AAirshipPawn::OnHullHit(UPrimitiveComponent* HitComponent, AActor* OtherActor, UPrimitiveComponent* OtherComp, FVector NormalImpulse, const FHitResult& Hit)
{
	if (!HullCollision)
	{
		return;
	}

	// Every machine (each simulates its hull; the server's result wins): no big bounce, pop or spin from one hit
	LimitImpactResponse();

	// The pilot's machine: a hard hit shakes the camera and rumbles (once per frame; every machine gets its hull's hits)
	if (IsLocallyControlled() && !bIsDead && LastFeedbackHitFrame != GFrameCounter && (ShakeHitPerMS > 0.f || RumbleHitPerMS > 0.f))
	{
		const float FeedbackSpeed = MeasureHullImpactSpeed(OtherActor, OtherComp, NormalImpulse, Hit);
		const float ExcessMS = (FeedbackSpeed - ImpactMinSpeed) * 0.01f;

		if (FeedbackSpeed >= 0.f && ExcessMS > 0.f)
		{
			LastFeedbackHitFrame = GFrameCounter;
			CameraTrauma = FMath::Min(1.f, CameraTrauma + FMath::Min(ShakeHitMax, ShakeHitPerMS * ExcessMS));
			PlayRumble(FMath::Min(1.f, RumbleHitPerMS * ExcessMS), 0.25f, true);
		}
	}

	if (!HasAuthority() || bIsDead || ImpactDamagePerMS <= 0.f)
	{
		return;
	}

	// -1: the hit doesn't count (its own pilot and cannonballs, characters, resting contact)
	const float ImpactSpeed = MeasureHullImpactSpeed(OtherActor, OtherComp, NormalImpulse, Hit);

	if (ImpactSpeed < 0.f || ImpactSpeed < ImpactMinSpeed)
	{
		return;
	}

	// Linear in the impact speed above the threshold, capped (the response cap above doesn't change it: the speed is
	// from before the step)
	const float Damage = FMath::Min((ImpactSpeed - ImpactMinSpeed) * 0.01f * ImpactDamagePerMS, ImpactMaxDamage);

	// Every contact pair of a frame calls this, in no particular order: the hardest contact of the frame counts
	if (ImpactDamageFrame == GFrameCounter)
	{
		if (Damage > ImpactDamageThisFrame)
		{
			const float Extra = Damage - ImpactDamageThisFrame;
			ImpactDamageThisFrame = Damage;
			ApplyShipDamage(Extra);
		}
		return;
	}

	const double Now = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0;

	if (Now - LastImpactTime < ImpactCooldown)
	{
		return;
	}

	LastImpactTime = Now;
	ImpactDamageFrame = GFrameCounter;
	ImpactDamageThisFrame = Damage;

	BP_OnHullImpact(ImpactSpeed, Damage, Hit);
	ApplyShipDamage(Damage);
}

float AAirshipPawn::MeasureHullImpactSpeed(const AActor* OtherActor, const UPrimitiveComponent* OtherComp, const FVector& NormalImpulse, const FHitResult& Hit) const
{
	// Its own pilot and cannonballs, and characters (a kinematic capsule would count as a wall hit)
	if (OtherActor && (OtherActor == this || OtherActor->IsAttachedTo(this) || OtherActor->IsA<AAirshipCannonball>() || OtherActor->IsA<ACharacter>()))
	{
		return -1.f;
	}

	if (OtherComp && OtherComp->GetCollisionObjectType() == ECC_Pawn)
	{
		return -1.f;
	}

	const float Mass = HullCollision ? HullCollision->GetMass() : 0.f;

	if (Mass <= KINDA_SMALL_NUMBER)
	{
		return -1.f;
	}

	// NormalImpulse is the contact's accumulated impulse: below a small speed change it's resting contact, not a hit
	const float ImpulseSpeed = static_cast<float>(NormalImpulse.Size()) / Mass;

	if (ImpulseSpeed < 50.f)
	{
		return -1.f;
	}

	// Impact speed: closing speed along the contact normal at the contact point, from the velocities before the step
	// (hull velocity + spin, minus the other body's), independent of restitution. Either normal sign (absolute value).
	float ImpactSpeed = ImpulseSpeed;
	const FVector Normal = Hit.ImpactNormal.GetSafeNormal();

	if (PreStepFrame == GFrameCounter && !Normal.IsNearlyZero())
	{
		const FVector Point = Hit.ImpactPoint;
		FVector Relative = PreStepLinearVelocity + FVector::CrossProduct(PreStepAngularVelocity, Point - PreStepCenterOfMass);

		if (OtherComp && OtherComp->IsSimulatingPhysics())
		{
			Relative -= OtherComp->GetPhysicsLinearVelocityAtPoint(Point);
		}
		else if (OtherActor)
		{
			// Moving platforms (kinematic); static geometry: zero
			Relative -= OtherActor->GetVelocity();
		}

		ImpactSpeed = static_cast<float>(FMath::Abs(FVector::DotProduct(Relative, Normal)));
	}

	return ImpactSpeed;
}

void AAirshipPawn::Die()
{
	if (!HasAuthority() || bIsDead)
	{
		return;
	}

	// For clients that get the actor later (the multicast only reaches those connected now)
	bIsDead = true;
	const AGameStateBase* GameState = GetWorld() ? GetWorld()->GetGameState() : nullptr;
	DeathServerTime = GameState ? GameState->GetServerWorldTimeSeconds() : (GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0);
	MulticastHandleDeath();
	SetLifeSpan(WreckLifeSpan);

	// Called from inside the damage effect's execution: the pilot gets their character back next tick
	GetWorldTimerManager().SetTimerForNextTick(this, &ThisClass::EjectPilotAfterDeath);
}

void AAirshipPawn::MulticastHandleDeath_Implementation()
{
	HandleDeath(false);
}

void AAirshipPawn::OnRep_IsDead()
{
	// The actor's first bunch arrives before BeginPlay, which runs it then
	if (bIsDead && HasActorBegunPlay())
	{
		HandleDeath(false);
	}
}

void AAirshipPawn::HandleDeath(bool bLateJoin)
{
	// The multicast and bIsDead both lead here
	if (bDeathHandled)
	{
		return;
	}

	bDeathHandled = true;
	bIsDead = true;
	DeathWorldTime = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0;

	// Joined after the death: the rig's DeathTime continues from the server's death time (the explosion is over)
	if (bLateJoin)
	{
		const AGameStateBase* GameState = GetWorld() ? GetWorld()->GetGameState() : nullptr;

		if (GameState)
		{
			DeathWorldTime -= FMath::Max(0.0, GameState->GetServerWorldTimeSeconds() - DeathServerTime);
		}
	}

	// No flight forces; the hull keeps simulating: gravity (also on clients now), dead damping, tumbling
	if (Flight)
	{
		Flight->SetFlightEnabled(false);
	}

	// The schemes' pilot-side state (and the drift rumble) end with the ship
	ResetSchemePilotState(false);

	if (HasAuthority() && HullCollision && HullCollision->IsSimulatingPhysics())
	{
		const FTransform HullTM = HullCollision->GetComponentTransform();
		const FVector Spin(
			FMath::FRandRange(-1.f, 1.f) * DeathAngularKick.X,
			FMath::FRandRange(-1.f, 1.f) * DeathAngularKick.Y,
			FMath::FRandRange(-1.f, 1.f) * DeathAngularKick.Z);
		HullCollision->AddAngularImpulseInRadians(HullTM.TransformVectorNoScale(Spin), NAME_None, true);

		// One pod cuts out: a push down at a random pod tips the ship over that side
		if (DeathPodKickDV > 0.f && Flight)
		{
			const FVector Pod = HullTM.TransformPosition(Flight->GetPodLocation(FMath::RandRange(0, Airship::NumPods - 1)));
			HullCollision->AddImpulseAtLocation(-HullTM.GetUnitAxis(EAxis::Z) * HullCollision->GetMass() * DeathPodKickDV, Pod);
		}
	}

	// Every machine: the engines die with the ship (the pods and fans break off later with their sockets). The jets
	// go out at once: NS_AirshipThruster's jet is one persistent mesh particle per emitter, which a soft Deactivate
	// can leave burning on a flying pod. The fan wash (short-lived puffs) stops spawning and fades. A late joiner never
	// saw any of it. UpdateFX stops feeding them. No auto-activation if a component registers again or gets a new
	// system (RegisterComponentWithWorld, UNiagaraComponent::SetAsset): the flag itself, since SetAutoActivate on a
	// registered component only logs a warning.
	for (UNiagaraComponent* FX : { ThrusterFX_FL.Get(), ThrusterFX_FR.Get(), ThrusterFX_RL.Get(), ThrusterFX_RR.Get() })
	{
		if (FX)
		{
			FX->bAutoActivate = false;
			FX->DeactivateImmediate();
		}
	}

	for (UNiagaraComponent* FX : { TurbineFX_L.Get(), TurbineFX_R.Get() })
	{
		if (FX)
		{
			FX->bAutoActivate = false;

			if (bLateJoin)
			{
				FX->DeactivateImmediate();
			}
			else
			{
				FX->Deactivate();
			}
		}
	}

	if (GetNetMode() != NM_DedicatedServer)
	{
		if (DeathExplosionFX && !bLateJoin)
		{
			UNiagaraFunctionLibrary::SpawnSystemAtLocation(this, DeathExplosionFX, GetActorLocation(), GetActorRotation());
		}

		if (DeathFireFX && Mesh)
		{
			UNiagaraFunctionLibrary::SpawnSystemAttached(DeathFireFX, Mesh, DeathFireSocket, FVector::ZeroVector, FRotator::ZeroRotator, EAttachLocation::SnapToTarget, true);
		}
	}

	// The pilot's machine: the ship HUD goes with the ship (the on-foot overlay comes back)
	UpdateShipHUD();

	BP_OnAirshipDied();

	// After bIsDead: listeners call IsDead()
	OnDeathDelegate.Broadcast(this);
}

void AAirshipPawn::EjectPilotAfterDeath()
{
	if (PilotCharacter)
	{
		UnboardPilot(true);
	}
}

float AAirshipPawn::GetDeathTime() const
{
	const UWorld* World = GetWorld();
	return (bDeathHandled && World) ? static_cast<float>(World->GetTimeSeconds() - DeathWorldTime) : 0.f;
}

float AAirshipPawn::TraceGroundDistance(float MaxDistance) const
{
	const UWorld* World = GetWorld();

	if (!World || !HullCollision || MaxDistance <= 0.f)
	{
		return -1.f;
	}

	// From the lowest point of the hull's bounds (the pods' nozzles when level), straight down
	const FBoxSphereBounds& Bounds = HullCollision->Bounds;
	const double BottomZ = Bounds.Origin.Z - Bounds.BoxExtent.Z;
	const FVector Location = GetActorLocation();
	const FVector Start(Location.X, Location.Y, Location.Z);
	const FVector End(Location.X, Location.Y, BottomZ - MaxDistance);

	FCollisionQueryParams Params(SCENE_QUERY_STAT(AirshipGroundDistance), false, this);
	TArray<AActor*> Attached;
	GetAttachedActors(Attached);
	Params.AddIgnoredActors(Attached);

	FHitResult Hit;

	if (!World->LineTraceSingleByChannel(Hit, Start, End, ECC_Visibility, Params))
	{
		return -1.f;
	}

	return static_cast<float>(FMath::Max(0.0, BottomZ - Hit.ImpactPoint.Z));
}


// =============================================================================
// HUD (pilot's machine)
// =============================================================================

void AAirshipPawn::UpdateShipHUD()
{
	APlayerController* PC = Cast<APlayerController>(GetController());
	const bool bWanted = bShowShipHUD && !bIsDead && PC && PC->IsLocalController() && GetNetMode() != NM_DedicatedServer
		&& !IsActorBeingDestroyed() && HasActorBegunPlay();

	if (!bWanted)
	{
		if (bShipHUDActive)
		{
			HideShipHUD();
		}
		return;
	}

	const double Now = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0;

	if (bShipHUDActive && ShipHUDOwner.Get() != PC)
	{
		HideShipHUD();
	}

	// Shown only once the widget is on screen; a failed try (no game viewport, no widget) comes again a second later
	if (!bShipHUDActive && Now >= NextShipHUDAttemptTime && !ShowShipHUD(PC))
	{
		NextShipHUDAttemptTime = Now + 1.0;
	}

	// The overlay may be made after the ship was boarded (it comes with the character's first possession)
	if (bShipHUDActive && bHideOnFootHUD && !HiddenOnFootWidget.IsValid() && Now - LastOnFootHUDSearchTime > 0.5)
	{
		HideOnFootHUD(PC);
	}
}

bool AAirshipPawn::ShowShipHUD(APlayerController* PC)
{
	UGameViewportSubsystem* ViewportSubsystem = UGameViewportSubsystem::Get();

	if (!PC || !ViewportSubsystem)
	{
		return false;
	}

	const TSubclassOf<UAirshipHUDWidget> WidgetClass = ShipHUDClass ? ShipHUDClass : TSubclassOf<UAirshipHUDWidget>(UAirshipHUDWidget::StaticClass());
	UAirshipHUDWidget* Widget = CreateWidget<UAirshipHUDWidget>(PC, WidgetClass);

	if (!Widget)
	{
		return false;
	}

	Widget->SetAirship(this);

	// Bottom-left corner, fixed size (the widget draws itself in NativePaint; the size follows the scheme)
	const FGameViewportWidgetSlot Slot = AirshipPawnPrivate::MakeCornerSlot(ShipHUDCornerOffset, Widget->GetPanelSize());

	ULocalPlayer* LocalPlayer = PC->GetLocalPlayer();
	const bool bAdded = LocalPlayer ? ViewportSubsystem->AddWidgetForPlayer(Widget, LocalPlayer, Slot) : ViewportSubsystem->AddWidget(Widget, Slot);

	if (!bAdded)
	{
		Widget->SetAirship(nullptr);
		return false;
	}

	ShipHUDWidget = Widget;
	ShipHUDOwner = PC;
	bShipHUDActive = true;

	// The on-foot overlay goes only with the ship HUD on screen
	if (bHideOnFootHUD)
	{
		HideOnFootHUD(PC);
	}

	// Point & Fly: crosshair, nose marker and gun state over the whole viewport
	if (ControlScheme == EAirshipControlScheme::PointFly)
	{
		AddShipOverlay(PC);
	}

	return true;
}

void AAirshipPawn::HideShipHUD()
{
	RemoveShipOverlay();

	if (ShipHUDWidget)
	{
		ShipHUDWidget->SetAirship(nullptr);
		ShipHUDWidget->RemoveFromParent();
		ShipHUDWidget = nullptr;
	}

	RestoreOnFootHUD();
	ShipHUDOwner.Reset();
	bShipHUDActive = false;
}

void AAirshipPawn::RefreshShipHUDLayout()
{
	APlayerController* PC = ShipHUDOwner.Get();
	UGameViewportSubsystem* ViewportSubsystem = UGameViewportSubsystem::Get();

	if (!bShipHUDActive || !ShipHUDWidget || !PC || !ViewportSubsystem)
	{
		return;
	}

	// The panel's height follows the scheme (Galleon's telegraph rows, Sky Racer's TURBO row): a new slot in place, no
	// hide / re-show (that would flash the on-foot overlay for a frame)
	ShipHUDWidget->RefreshLayoutScheme();
	ViewportSubsystem->SetWidgetSlot(ShipHUDWidget.Get(), AirshipPawnPrivate::MakeCornerSlot(ShipHUDCornerOffset, ShipHUDWidget->GetPanelSize()));

	if (ControlScheme == EAirshipControlScheme::PointFly)
	{
		if (!ShipOverlayWidget)
		{
			AddShipOverlay(PC);
		}
	}
	else
	{
		RemoveShipOverlay();
	}
}

bool AAirshipPawn::AddShipOverlay(APlayerController* PC)
{
	UGameViewportSubsystem* ViewportSubsystem = UGameViewportSubsystem::Get();

	if (ShipOverlayWidget)
	{
		return true;
	}

	if (!PC || !ViewportSubsystem)
	{
		return false;
	}

	const TSubclassOf<UAirshipHUDWidget> WidgetClass = ShipHUDClass ? ShipHUDClass : TSubclassOf<UAirshipHUDWidget>(UAirshipHUDWidget::StaticClass());
	UAirshipHUDWidget* Overlay = CreateWidget<UAirshipHUDWidget>(PC, WidgetClass);

	if (!Overlay)
	{
		return false;
	}

	// Overlay mode before it is added; the default slot covers the whole viewport, ZOrder 0 (below the panel)
	Overlay->SetOverlayMode(true);
	Overlay->SetAirship(this);
	FGameViewportWidgetSlot FullScreenSlot;
	FullScreenSlot.ZOrder = 0;

	ULocalPlayer* LocalPlayer = PC->GetLocalPlayer();
	const bool bAdded = LocalPlayer ? ViewportSubsystem->AddWidgetForPlayer(Overlay, LocalPlayer, FullScreenSlot) : ViewportSubsystem->AddWidget(Overlay, FullScreenSlot);

	if (!bAdded)
	{
		Overlay->SetAirship(nullptr);
		return false;
	}

	ShipOverlayWidget = Overlay;
	return true;
}

void AAirshipPawn::RemoveShipOverlay()
{
	if (ShipOverlayWidget)
	{
		ShipOverlayWidget->SetAirship(nullptr);
		ShipOverlayWidget->RemoveFromParent();
		ShipOverlayWidget = nullptr;
	}
}

void AAirshipPawn::HideOnFootHUD(APlayerController* PC)
{
	LastOnFootHUDSearchTime = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0;

	// AMyHUD keeps the overlay in a private UPROPERTY: read it by reflection, no change to the shared class
	AHUD* HUD = PC ? PC->GetHUD() : nullptr;
	const FObjectPropertyBase* Property = (HUD && !OnFootHUDWidgetProperty.IsNone()) ? FindFProperty<FObjectPropertyBase>(HUD->GetClass(), OnFootHUDWidgetProperty) : nullptr;
	UUserWidget* Overlay = Property ? Cast<UUserWidget>(Property->GetObjectPropertyValue_InContainer(HUD)) : nullptr;

	if (!Overlay || Overlay->GetVisibility() == ESlateVisibility::Collapsed)
	{
		return;
	}

	HiddenOnFootWidget = Overlay;
	HiddenOnFootVisibility = Overlay->GetVisibility();
	Overlay->SetVisibility(ESlateVisibility::Collapsed);
}

void AAirshipPawn::RestoreOnFootHUD()
{
	UUserWidget* Overlay = HiddenOnFootWidget.Get();

	// Only if nobody changed it since
	if (Overlay && Overlay->GetVisibility() == ESlateVisibility::Collapsed)
	{
		Overlay->SetVisibility(HiddenOnFootVisibility);
	}

	HiddenOnFootWidget.Reset();
	LastOnFootHUDSearchTime = -1000.0;
}


// =============================================================================
// Test hooks
// =============================================================================

void AAirshipPawn::DebugSetInput(float Throttle, float Steer, float Lift, float Strafe, bool bBoost, bool bBrake)
{
	if (!Flight)
	{
		return;
	}

	FAirshipPilotInput Controls;
	Controls.Throttle = FAirshipPilotInput::QuantizeAxis(Throttle);
	Controls.Steer = FAirshipPilotInput::QuantizeAxis(Steer);
	Controls.Lift = FAirshipPilotInput::QuantizeAxis(Lift);
	Controls.Strafe = FAirshipPilotInput::QuantizeAxis(Strafe);
	Controls.SetButton(Airship::Button_Boost, bBoost);
	Controls.SetButton(Airship::Button_Brake, bBrake);
	Flight->SetDebugInput(Controls);
}

void AAirshipPawn::DebugClearInput()
{
	if (Flight)
	{
		Flight->ClearDebugInput();
	}
}

FAirshipFlightTelemetry AAirshipPawn::GetFlightTelemetry() const
{
	FAirshipFlightTelemetry Telemetry;

	if (Flight)
	{
		Flight->FillTelemetry(Telemetry);
	}

	// Point & Fly, the pilot's machine: its own heading target (with the lock lead), camera mode and gun lock
	if (ControlScheme == EAirshipControlScheme::PointFly && IsLocallyControlled())
	{
		Telemetry.bHeadingTargetActive = bPFValid;
		Telemetry.HeadingTargetDeg = bPFValid ? PFSentHeading : 0.f;
		Telemetry.bFreeLook = bPFFree;
		Telemetry.bGunLock = bPFLock;
	}

	if (AbilitySystemComponent)
	{
		Telemetry.Health = AbilitySystemComponent->GetNumericAttribute(UMyAttributeSet::GetHealthAttribute());
		Telemetry.MaxHealth = AbilitySystemComponent->GetNumericAttribute(UMyAttributeSet::GetMaxHealthAttribute());
	}

	Telemetry.bHasPilot = PilotCharacter != nullptr;
	Telemetry.bIsDead = bIsDead;
	return Telemetry;
}

void AAirshipPawn::OnTuningChanged()
{
	if (Flight)
	{
		Flight->RefreshActuatorLocations();
		Flight->ApplyBodySettings();
	}

	RefreshCannonGeometry();
	ZoomTarget = FMath::Clamp(ZoomTarget, CameraArmMin, FMath::Max(CameraArmMin, CameraArmMax));
}


// =============================================================================
// Control schemes (CPP_NOTES.md "Control schemes")
// =============================================================================

void AAirshipPawn::SetControlScheme(EAirshipControlScheme NewScheme)
{
	if (!HasAuthority())
	{
		UE_LOG(LogAirshipPawn, Warning, TEXT("%s: SetControlScheme(%s) ignored on a client: the server sets the control scheme (it replicates)"),
			*GetName(), *UEnum::GetDisplayValueAsText(NewScheme).ToString());
		return;
	}

	// Re-applying the same scheme is allowed: it resets live tuning (Aura.Airship.Set) on this machine
	ControlScheme = NewScheme;

	// Before BeginPlay it is applied there
	if (HasActorBegunPlay())
	{
		ApplyControlScheme(true);
	}

	ForceNetUpdate();
}

void AAirshipPawn::OnRep_ControlScheme()
{
	// The actor's first bunch arrives before BeginPlay, which applies it then
	if (HasActorBegunPlay())
	{
		ApplyControlScheme(true);
	}
}

void AAirshipPawn::ApplyControlScheme(bool bSwitch)
{
	// Every scheme-owned tunable: the same compiled-in preset on every machine (never replicated)
	ApplySchemePreset(ControlScheme);

	if (Flight)
	{
		Flight->SetActiveScheme(ControlScheme);
	}

	// Actuator positions, body settings, cannon geometry, zoom clamp
	OnTuningChanged();

	// The arm eases to the scheme's length (TargetArmLength keeps interpolating: no jump)
	ZoomTarget = CameraArmLength;

	ResetSchemePilotState(bSwitch);

	// Nothing of a scheme's camera roll or shake is left over (Classic's camera is exactly v1)
	if (Camera)
	{
		Camera->SetRelativeRotation(FRotator::ZeroRotator);
		Camera->SetRelativeLocation(FVector::ZeroVector);
		SmoothedFOV = Camera->FieldOfView;
		LastAppliedFOV = Camera->FieldOfView;
	}
	bCameraFeedbackApplied = false;

	RefreshShipHUDLayout();
}

void AAirshipPawn::ApplySchemePreset(EAirshipControlScheme Scheme)
{
	if (!Flight || !CameraBoom)
	{
		return;
	}

	// Classic = the archetype (the Blueprint class defaults, which override none of these): switching is
	// order-independent and Classic restores v1 exactly. A level instance's overrides of these are discarded.
	const AAirshipPawn* NativeDefaults = GetDefault<AAirshipPawn>();
	const UAirshipFlightComponent* FlightArchetype = Cast<UAirshipFlightComponent>(Flight->GetArchetype());
	const AAirshipPawn* PawnArchetype = Cast<AAirshipPawn>(GetArchetype());
	const USpringArmComponent* BoomArchetype = Cast<USpringArmComponent>(CameraBoom->GetArchetype());

	if (!FlightArchetype)
	{
		FlightArchetype = NativeDefaults->Flight.Get();
	}
	if (!PawnArchetype)
	{
		PawnArchetype = NativeDefaults;
	}
	if (!BoomArchetype)
	{
		BoomArchetype = NativeDefaults->CameraBoom.Get();
	}

	if (!FlightArchetype || !PawnArchetype || !BoomArchetype || FlightArchetype == Flight.Get() || PawnArchetype == this)
	{
		UE_LOG(LogAirshipPawn, Warning, TEXT("%s: no archetype to take the control scheme's base values from"), *GetName());
		return;
	}

#define AIRSHIP_COPY_FC(Name) Flight->Name = FlightArchetype->Name;
	AIRSHIP_FC_SCHEME_PROPS(AIRSHIP_COPY_FC)
#undef AIRSHIP_COPY_FC

#define AIRSHIP_COPY_PAWN(Name) Name = PawnArchetype->Name;
	AIRSHIP_PAWN_SCHEME_PROPS(AIRSHIP_COPY_PAWN)
#undef AIRSHIP_COPY_PAWN

#define AIRSHIP_COPY_BOOM(Name) CameraBoom->Name = BoomArchetype->Name;
	AIRSHIP_BOOM_SCHEME_PROPS(AIRSHIP_COPY_BOOM)
#undef AIRSHIP_COPY_BOOM

	switch (Scheme)
	{
	case EAirshipControlScheme::Galleon:
		ApplyGalleonPreset();
		break;

	case EAirshipControlScheme::SkyRacer:
		ApplySkyRacerPreset();
		break;

	case EAirshipControlScheme::PointFly:
		ApplyPointFlyPreset();
		break;

	default:
		break;
	}
}

void AAirshipPawn::ApplyGalleonPreset()
{
	using AirshipPawnPrivate::MakeFeedback;

	// Flight (SCHEME_GALLEON.md 5.1 / 5.2; Galleon-only tunables keep their defaults)
	UAirshipFlightComponent& F = *Flight;
	F.ThrottleTauUp = 0.15f;
	F.ThrottleTauDown = 0.25f;
	F.ClimbRate = 1000.f;
	F.DescendRate = 1300.f;
	F.PitchPerG = 4.f;
	F.PitchMinDeg = -4.f;
	F.PitchMaxDeg = 3.f;
	F.BoostPitchDeg = 1.5f;
	F.YawRateAtRest = 26.f;
	F.YawRateAtMid = 44.f;
	F.YawRateAtTop = 34.f;
	F.YawRateBoost = 24.f;
	F.YawRateDrift = 54.f;
	F.BankMaxDeg = 26.f;
	F.BankMaxBoostDeg = 18.f;
	F.BankMaxDriftDeg = 28.f;
	F.BankFullSpeed = 2400.f;
	F.StrafeBankDeg = 3.f;
	F.KpRoll = 18.f;
	F.KdRoll = 5.4f;
	F.GyroTiltMax = 1.5f;
	F.StrafeSpeed = 1000.f;
	F.StrafeTau = 0.25f;
	F.BoostKickDV = 550.f;
	F.BoostDrainRate = 22.f;
	F.DriftMinSpeed = 600.f;
	F.DriftKlat = 1.6f;
	F.DriftALatMaxG = 1.6f;
	F.DriftEta = 0.15f;
	F.DriftBrakeScale = 0.3f;
	F.DriftBoostMinTime = 0.6f;
	F.DriftBoostDV = 250.f;

	// Base fixes
	F.bHullAxisInertia = true;
	F.bFanTorqueFeedForward = true;
	F.VertBrakeAccel = 784.f;
	F.HoldBrakeAccel = 1470.f;
	F.LiftTauRelease = 0.08f;
	F.bBrakeHoldLead = true;
	F.BrakeFadeSpeed = 1000.f;
	F.StationKeepGain = 1.f;

	// Shared mechanisms
	F.bLevelGripForce = true;
	F.BrakeMaxAccel = 1400.f;
	F.SteerTauRelease = 0.12f;
	F.KrSteady = 4.f;
	F.AlphaYawMaxSteady = 1.2f;
	F.DriftKr = 4.f;
	F.DriftAlphaYawMax = 1.5f;
	F.DriftCosmeticSteerScale = 1.3f;
	F.GunDeckBankScale = 0.2f;
	F.GunDeckYawScale = 0.5f;

	// Pawn (5.3 / 5.4): higher, farther, slower camera; impact fix 4e
	CameraArmLength = 8000.f;
	CameraArmMin = 5000.f;
	CameraArmMax = 14000.f;
	CameraBoostArmExtra = 1400.f;
	BaseFOV = 80.f;
	BoostFOVExtra = 14.f;
	AimFOVOffset = -18.f;
	CameraPitchMin = -65.f;
	CameraPitchMax = 20.f;
	CameraDefaultPitch = -16.f;
	RecenterDelay = 2.f;
	RecenterSpeed = 1.2f;
	ImpactEpisodeAccelUp = 2050.f;
	ImpactMaxReboundSpeed = 120.f;

	// Feedback
	ShakeRotDeg = 1.f;
	ShakeLocCm = 20.f;
	ShakeFrequency = 8.f;
	ShakeDecay = 1.8f;
	CameraRollPerSteerDeg = 6.5f;
	CameraRollInterpSpeed = 8.f;
	RumbleScale = 1.f;
	ShakeHitPerMS = 0.06f;
	RumbleHitPerMS = 0.06f;
	DriftRumbleBase = 0.2f;
	FeedbackBoostStart = MakeFeedback(0.3f, 6.f, 0.4f, 0.4f);
	FeedbackOwnBroadside = MakeFeedback(0.35f, -3.f, 0.6f, 0.25f);
	FeedbackDriftKick = MakeFeedback(0.25f, 4.f, 0.5f, 0.2f);
	FeedbackOrderChange = MakeFeedback(0.06f, 1.5f, 0.25f, 0.08f);

	// Camera boom
	CameraBoom->TargetOffset.Z = 1200.0;
	CameraBoom->CameraLagSpeed = 3.5f;
	CameraBoom->CameraLagMaxDistance = 3000.f;
	CameraBoom->CameraRotationLagSpeed = 6.f;
}

void AAirshipPawn::ApplySkyRacerPreset()
{
	using AirshipPawnPrivate::MakeFeedback;

	// Flight (SCHEME_SKYRACER.md 4.1 / 4.2; Sky Racer-only tunables keep their defaults)
	UAirshipFlightComponent& F = *Flight;
	F.ThrottleTauUp = 0.18f;
	F.ThrottleTauDown = 0.3f;
	F.BoostTauUp = 0.08f;
	F.BoostTauDown = 0.45f;
	F.LiftTau = 0.12f;
	F.SteerTau = 0.09f;
	F.StrafeTau = 0.14f;
	F.ClimbRate = 1350.f;
	F.DescendRate = 1650.f;
	F.Kvz = 3.f;
	F.CollectiveMin = 0.15f;
	F.CollectiveMax = 2.1f;
	F.PodForceMax = 0.62f;
	F.MinClearance = 500.f;
	F.Kfloor = 2.f;
	F.KpRoll = 9.f;
	F.KdRoll = 5.4f;
	F.BankMaxDeg = 22.f;
	F.BankMaxBoostDeg = 15.f;
	F.BankFullSpeed = 1800.f;
	F.StrafeBankDeg = 5.f;
	F.PitchPerG = 4.5f;
	F.PitchMinDeg = -5.f;
	F.PitchMaxDeg = 4.f;
	F.BoostPitchDeg = 1.5f;
	F.LiftPitchDeg = 4.f;
	F.BoostDrainRate = 28.f;
	F.BoostRegenRate = 10.f;
	F.BoostRegenDelay = 1.2f;
	F.BoostMinFuelToStart = 18.f;
	F.BoostKickDV = 600.f;
	F.AFan = 1860.f;
	F.VTop = 5900.f;
	F.ThrustFadeExponent = 5.f;
	F.AFanBoost = 2550.f;
	F.VTopBoost = 10000.f;
	F.FanMax = 0.95f;
	F.FanMaxBoost = 1.3f;
	F.Kbrake = 1.5f;
	F.BrakeReverseThrottle = 0.4f;
	F.StrafeSpeed = 1400.f;
	F.GripKlat = 4.5f;
	F.GripALatMaxG = 4.f;
	F.BoostKlat = 3.5f;
	F.BoostALatMaxG = 3.f;
	F.Kr = 4.5f;
	F.AlphaYawMax = 1.5f;
	F.YawRateAtRest = 34.f;
	F.YawRateAtMid = 50.f;
	F.YawRateAtTop = 38.f;
	F.YawRateMidSpeed = 1600.f;
	F.YawRateTopSpeed = 5600.f;
	F.YawRateBoost = 30.f;
	F.RudderAuthority = 0.9f;
	F.RudderRefSpeed = 5000.f;
	F.RudderMaxAlpha = 1.6f;
	F.GyroYawMax = 0.6f;

	// Base fixes
	F.bHullAxisInertia = true;
	F.bFanTorqueFeedForward = true;
	F.VertBrakeAccel = 1180.f;
	F.HoldBrakeAccel = 1960.f;
	F.LiftTauRelease = 0.06f;
	F.bBrakeHoldLead = true;
	F.BrakeFadeSpeed = 1000.f;
	F.StationKeepGain = 1.f;

	// Shared mechanisms (bench names: bSkyLevelGrip, SkyBrakeAccelMax, SkyDriftAlphaYawMax, SkyAim*Scale)
	F.bLevelGripForce = true;
	F.bLevelGripAlongHeading = true;
	F.BrakeMaxAccel = 1470.f;
	F.DriftAlphaYawMax = 2.5f;
	F.GunDeckBankScale = 0.35f;
	F.GunDeckThrottleScale = 0.6f;
	F.GunDeckBrakeScale = 0.3f;
	F.GunDeckYawScale = 0.8f;

	// Pawn (4.3): a lower, closer chase camera; forgiving collisions; impact fix 4e
	CameraArmLength = 5400.f;
	CameraDefaultPitch = -8.f;
	CameraBoostArmExtra = 1200.f;
	RecenterDelay = 0.6f;
	RecenterMinSpeed = 500.f;
	RecenterSpeed = 4.f;
	BaseFOV = 82.f;
	SpeedFOVExtra = 18.f;
	SpeedFOVStart = 1500.f;
	SpeedFOVFull = 5500.f;
	BoostFOVExtra = 14.f;
	AimFOVOffset = -14.f;
	FOVInterpSpeed = 6.f;
	ImpactMinSpeed = 700.f;
	ImpactDamagePerMS = 4.f;
	ImpactMaxDamage = 350.f;
	ImpactCooldown = 0.6f;
	ImpactMaxSpinKickDeg = 12.f;
	ImpactMaxSpeedGain = 400.f;
	ImpactMaxReboundSpeed = 120.f;
	ImpactEpisodeAccelUp = 2650.f;

	// Feedback
	ShakeRotDeg = 1.2f;
	ShakeFrequency = 14.f;
	ShakeDecay = 1.8f;
	FOVKickDecay = 2.5f;
	FOVMaxDeg = 112.f;
	CameraRollPerBank = 0.25f;
	RumbleScale = 1.f;
	ShakeHitPerMS = 0.05f;
	ShakeHitMax = 0.8f;
	DriftTraumaBase = 0.08f;
	DriftTraumaPerCharge = 0.12f;
	DriftRumbleBase = 0.15f;
	DriftRumblePerCharge = 0.35f;
	FeedbackBoostStart = MakeFeedback(0.35f, 6.f, 0.6f, 0.2f);
	FeedbackTurbo1 = MakeFeedback(0.3f, 4.f, 0.5f, 0.25f);
	FeedbackTurbo2 = MakeFeedback(0.45f, 7.f, 0.75f, 0.25f);
	FeedbackTurbo3 = MakeFeedback(0.65f, 10.f, 1.f, 0.25f);

	// Camera boom
	CameraBoom->TargetOffset.Z = 650.0;
	CameraBoom->CameraLagSpeed = 6.5f;
	CameraBoom->CameraRotationLagSpeed = 10.f;
}

void AAirshipPawn::ApplyPointFlyPreset()
{
	using AirshipPawnPrivate::MakeFeedback;

	// Flight (SCHEME_POINTFLY.md 4; Point & Fly-only tunables keep their defaults)
	UAirshipFlightComponent& F = *Flight;
	F.SteerTau = 0.1f;
	F.Kr = 5.5f;
	F.StrafeTau = 0.12f;
	F.StrafeSpeed = 1400.f;
	F.StrafeBankDeg = 7.f;
	F.Kbrake = 2.f;
	F.AFan = 1400.f;
	F.PitchPerG = 4.f;
	F.PitchMinDeg = -4.f;
	F.BoostPitchDeg = 1.5f;

	// Polish after judging (SCHEME_POINTFLY.md "Review changes", P2): a fast turn stops where the pilot looks. The hidden
	// yaw stabiliser may add up to 1 rad/s^2 (v1 0.5: fans + gyro capped the stop near 1 rad/s^2, so a 50 deg/s drift
	// exit overshot 8.6 deg; now 1.7). Turn onset is unchanged: AlphaYawMax 1 still caps it.
	F.GyroYawMax = 1.f;

	// Base fixes
	F.bHullAxisInertia = true;
	F.bFanTorqueFeedForward = true;
	F.VertBrakeAccel = 784.f;
	F.HoldBrakeAccel = 1470.f;
	F.LiftTauRelease = 0.08f;
	F.bBrakeHoldLead = true;
	F.BrakeFadeSpeed = 1000.f;
	F.StationKeepGain = 1.f;

	// Shared mechanisms (bench names: PFBrakeAccelMax, PFAimBankScale)
	F.BrakeMaxAccel = 1470.f;
	F.GunDeckBankScale = 0.4f;

	// Polish (P2): Galleon's "meet her" while a turn is taken off (the request may reach 1.5 rad/s^2 there; the gain stays Kr)
	F.KrSteady = 5.5f;
	F.AlphaYawMaxSteady = 1.5f;

	// Polish (P1): the brake-drift kick only tops the ship up to cruise (48 m/s): rhythmic drifts no longer beat W
	F.DriftBoostCapSpeed = 4800.f;

	// Pawn: the camera is the steering (it never moves by itself); impact fix 4e
	RecenterSpeed = 0.f;
	ImpactEpisodeAccelUp = 2000.f;
	ImpactMaxReboundSpeed = 120.f;

	// Feedback
	ShakeRotDeg = 1.2f;
	ShakeFrequency = 13.f;
	ShakeDecay = 2.5f;
	FOVKickDecay = 5.f;
	CameraRollPerBank = 0.15f;
	CameraRollMaxDeg = 3.f;
	CameraRollInterpSpeed = 6.f;
	RumbleScale = 1.f;
	ShakeHitPerMS = 0.05f;
	RumbleHitPerMS = 0.067f;
	FeedbackBoostStart = MakeFeedback(0.f, 5.f, 0.3f, 0.35f, false);
	FeedbackOwnBroadside = MakeFeedback(0.25f, -3.f, 0.5f, 0.15f);
	FeedbackDriftKick = MakeFeedback(0.2f, 4.f, 0.6f, 0.2f);
	FeedbackLockEngage = MakeFeedback(0.f, 0.f, 0.15f, 0.06f, false);
}

int32 AAirshipPawn::GetSchemePropertyDifferences(TArray<FString>& OutDifferences) const
{
	const int32 Before = OutDifferences.Num();

	if (!Flight || !CameraBoom)
	{
		return 0;
	}

	// The same archetypes ApplySchemePreset copies from
	const AAirshipPawn* NativeDefaults = GetDefault<AAirshipPawn>();
	const UAirshipFlightComponent* FlightArchetype = Cast<UAirshipFlightComponent>(Flight->GetArchetype());
	const AAirshipPawn* PawnArchetype = Cast<AAirshipPawn>(GetArchetype());
	const USpringArmComponent* BoomArchetype = Cast<USpringArmComponent>(CameraBoom->GetArchetype());
	FlightArchetype = FlightArchetype ? FlightArchetype : NativeDefaults->Flight.Get();
	PawnArchetype = PawnArchetype ? PawnArchetype : NativeDefaults;
	BoomArchetype = BoomArchetype ? BoomArchetype : NativeDefaults->CameraBoom.Get();

	if (!FlightArchetype || !PawnArchetype || !BoomArchetype)
	{
		OutDifferences.Add(TEXT("no archetype"));
		return OutDifferences.Num() - Before;
	}

	auto CheckProperty = [&OutDifferences](const UObject* InObject, const UObject* InArchetype, const TCHAR* InOwnerName, const TCHAR* InPropertyName)
	{
		const FProperty* Property = FindFProperty<FProperty>(InObject->GetClass(), InPropertyName);

		if (!Property)
		{
			OutDifferences.Add(FString::Printf(TEXT("%s.%s: no such property"), InOwnerName, InPropertyName));
			return;
		}

		if (!Property->Identical_InContainer(InObject, InArchetype))
		{
			FString Value;
			FString Default;
			Property->ExportTextItem_InContainer(Value, InObject, nullptr, nullptr, PPF_None);
			Property->ExportTextItem_InContainer(Default, InArchetype, nullptr, nullptr, PPF_None);
			OutDifferences.Add(FString::Printf(TEXT("%s.%s = %s (default %s)"), InOwnerName, InPropertyName, *Value, *Default));
		}
	};

	const UObject* FlightObject = Flight.Get();
	const UObject* BoomObject = CameraBoom.Get();

#define AIRSHIP_CHECK_FC(Name) CheckProperty(FlightObject, FlightArchetype, TEXT("Flight"), TEXT(#Name));
	AIRSHIP_FC_SCHEME_PROPS(AIRSHIP_CHECK_FC)
#undef AIRSHIP_CHECK_FC

#define AIRSHIP_CHECK_PAWN(Name) CheckProperty(this, PawnArchetype, TEXT("Pawn"), TEXT(#Name));
	AIRSHIP_PAWN_SCHEME_PROPS(AIRSHIP_CHECK_PAWN)
#undef AIRSHIP_CHECK_PAWN

#define AIRSHIP_CHECK_BOOM(Name) CheckProperty(BoomObject, BoomArchetype, TEXT("CameraBoom"), TEXT(#Name));
	AIRSHIP_BOOM_SCHEME_PROPS(AIRSHIP_CHECK_BOOM)
#undef AIRSHIP_CHECK_BOOM

	return OutDifferences.Num() - Before;
}

int32 AAirshipPawn::NotchForSpeed(float ForwardSpeedCms)
{
	// Midway between the notch speeds (FULL 48, HALF 28, SLOW 14, STOP 0, ASTERN -12 m/s)
	if (ForwardSpeedCms >= 3800.f)
	{
		return AirshipGalleon::Full;
	}
	if (ForwardSpeedCms >= 2100.f)
	{
		return AirshipGalleon::Half;
	}
	if (ForwardSpeedCms >= 700.f)
	{
		return AirshipGalleon::Slow;
	}
	if (ForwardSpeedCms > -300.f)
	{
		return AirshipGalleon::Stop;
	}
	return AirshipGalleon::Astern;
}

void AAirshipPawn::ResetSchemePilotState(bool bFromSwitch)
{
	const FAirshipCosmeticState& C = GetCosmeticState();

	// Galleon: a switch at cruise keeps cruising; boarding, exit and death ring STOP. The hull's forward speed now (as
	// UpdateFlight measures it): the cosmetic state's is last frame's, stale right after a teleport
	const bool bHullSimulating = HullCollision && HullCollision->IsSimulatingPhysics();
	const FVector HullVelocity = bHullSimulating ? HullCollision->GetPhysicsLinearVelocity() : GetVelocity();
	const float ForwardSpeedNow = static_cast<float>(FVector::DotProduct(HullVelocity, GetActorForwardVector()));
	GalleonNotch = bFromSwitch ? NotchForSpeed(ForwardSpeedNow) : AirshipGalleon::Stop;
	bGalleonUpHeld = false;
	bGalleonDownHeld = false;
	GalleonRepeatDir = 0;
	GalleonNextRepeatTime = 0.0;
	GalleonCamOffsetYaw = 0.f;
	GalleonLookAhead = 0.f;
	GalleonLastLookAhead = 0.f;
	GalleonLastHullYaw = static_cast<float>(GetActorRotation().Yaw);
	bGalleonBeamWatch = false;
	bGalleonStations = false;
	bGalleonCamInit = false;

	// Point & Fly: the heading target restarts on the hull's heading next frame (after a switch the camera eases in)
	bPFValid = false;
	bPFFree = false;
	bPFLock = false;
	bPFParked = false;
	PFLockDwell = 0.f;
	PFPrevOffBeam = -1.f;
	PFOffBeamRate = 0.f;
	PFHeadingRate = 0.f;
	PFLockSwingDir = 0;
	PilotHeadingLoop = FPointFlyLoopState();

	// Feedback (a boost held or a turbo counted before the reset is no new event)
	CameraTrauma = 0.f;
	CameraFOVKick = 0.f;
	CameraRollDeg = 0.f;
	LocalDriftTime = 0.f;
	bPrevLocalDrift = false;
	LastTurboEventCount = C.TurboEventCount;
	bPrevBoostBit = Flight ? Flight->GetCurrentControls().IsBoost() : false;
	StopDriftRumble();
}

void AAirshipPawn::UpdateGalleonOrders(float ThrottleAxis, bool bAimHeld, const APlayerController* PC, double Now)
{
	using namespace AirshipPawnPrivate;

	// (a) Beam watch: the camera's offset from the bow, this frame's mouse included (UpdateCamera runs after this)
	float Offset = 0.f;

	if (PC && bGalleonCamInit && !bPendingCameraReset)
	{
		Offset = WrapDeg(static_cast<float>(PC->GetControlRotation().Yaw) - GalleonLastHullYaw - GalleonLastLookAhead);
	}

	bGalleonBeamWatch = !bGalleonBeamWatch ? FMath::Abs(Offset) > GalleonBeamWatchEnterDeg : FMath::Abs(Offset) >= GalleonBeamWatchExitDeg;

	// Stations: Aim at once; beam watch only while fighting (an own broadside in the last GalleonStationsFireHoldTime s,
	// review R1: merely looking around never changes the handling)
	const bool bRecentBroadside = GalleonStationsFireHoldTime <= 0.f || Now - LastOwnBroadsideTime < GalleonStationsFireHoldTime;
	bGalleonStations = bAimHeld || (bGalleonBeamWatch && bRecentBroadside);

	// (b) The telegraph: a press steps one notch, holding auto-steps (never through STOP)
	const bool bUp = ThrottleAxis > GalleonOrderAxisPress || (bGalleonUpHeld && ThrottleAxis > GalleonOrderAxisRelease);
	const bool bDown = ThrottleAxis < -GalleonOrderAxisPress || (bGalleonDownHeld && ThrottleAxis < -GalleonOrderAxisRelease);

	for (const int32 Dir : { 1, -1 })
	{
		const bool bHeld = Dir > 0 ? bUp : bDown;
		const bool bWasHeld = Dir > 0 ? bGalleonUpHeld : bGalleonDownHeld;

		if (bHeld && !bWasHeld)
		{
			StepGalleonOrder(Dir, false);
			GalleonNextRepeatTime = Now + GalleonOrderRepeatDelay;
			GalleonRepeatDir = Dir;
		}
		else if (bHeld && GalleonRepeatDir == Dir && Now >= GalleonNextRepeatTime - 1e-6)
		{
			StepGalleonOrder(Dir, true);
			GalleonNextRepeatTime = Now + GalleonOrderRepeatInterval;
		}
	}

	bGalleonUpHeld = bUp;
	bGalleonDownHeld = bDown;

	if (!bUp && !bDown)
	{
		GalleonRepeatDir = 0;
	}
}

void AAirshipPawn::StepGalleonOrder(int32 Dir, bool bRepeat)
{
	const int32 Next = FMath::Clamp(GalleonNotch + Dir, AirshipGalleon::Astern, AirshipGalleon::Full);

	// The STOP detent: auto-repeat stops at STOP (never through it); a fresh press passes it
	const bool bCrossesStop = (GalleonNotch > AirshipGalleon::Stop && Next < AirshipGalleon::Stop) || (GalleonNotch < AirshipGalleon::Stop && Next > AirshipGalleon::Stop);

	if (bRepeat && (GalleonNotch == AirshipGalleon::Stop || bCrossesStop))
	{
		return;
	}

	if (Next != GalleonNotch)
	{
		GalleonNotch = Next;

		// The telegraph rings: the FOV kick's sign is the order's direction
		AddFeedback(FeedbackOrderChange, static_cast<float>(Dir));
	}
}

void AAirshipPawn::UpdatePointFlyCamera(float Dt, APlayerController* PC, float NudgeAxis, bool bAimHeld, bool bMoveKeys, bool bFireHeld)
{
	using namespace AirshipPawnPrivate;

	if (!PC || !Flight)
	{
		return;
	}

	const float StepDt = FMath::Max(Dt, UE_KINDA_SMALL_NUMBER);
	const float ViewYaw = static_cast<float>(GetActorRotation().Yaw);
	const FRotator Control = PC->GetControlRotation();
	const float ControlYaw = static_cast<float>(Control.Yaw);

	// Board, possession, scheme switch, debug input ended: the target starts on the ship's heading (a switch keeps the
	// camera where it is and eases it in; a camera reset puts it behind the ship)
	bool bJustStarted = false;

	if (!bPFValid || bPendingCameraReset)
	{
		PFHeading = ViewYaw;
		PFLookOffset = bPendingCameraReset ? 0.f : WrapDeg(ControlYaw - ViewYaw);
		PFLastSetYaw = WrapDeg(PFHeading + PFLookOffset);
		bPFLock = false;
		PFLockDwell = 0.f;
		PFPrevOffBeam = -1.f;
		PFOffBeamRate = 0.f;
		PFHeadingRate = 0.f;
		PFPrevHeading = PFHeading;
		PFLockSwingDir = 0;
		PilotHeadingLoop = FPointFlyLoopState();
		bPFParked = false;
		bPFValid = true;
		bJustStarted = true;
	}

	// This frame's look input: the control yaw's change since this code set it (the PlayerController applied the mouse
	// delta before this tick). A change without IA_AirshipLook this frame was set from outside (harness, reset): an
	// absolute set. Below 0.001 deg it is the float round trip, not input. On the start frame this code places the
	// camera itself (the old control yaw, e.g. the character's, is no set).
	float LookDelta = bJustStarted ? 0.f : WrapDeg(ControlYaw - PFLastSetYaw);

	if (FMath::Abs(LookDelta) < 1e-3f)
	{
		LookDelta = 0.f;
	}

	const bool bExternal = LookDelta != 0.f && LastLookInputFrame != GFrameCounter;

	// Q/E: the target turns at the ship's own full turn rate for its speed (open loop: no loop over the network)
	const bool bHullSimulating = HullCollision && HullCollision->IsSimulatingPhysics();
	const FVector HullVelocity = bHullSimulating ? HullCollision->GetPhysicsLinearVelocity() : GetVelocity();
	const float ViewForwardSpeed = static_cast<float>(FVector::DotProduct(HullVelocity, GetActorForwardVector()));
	const float Nudge = FMath::Clamp(NudgeAxis, -1.f, 1.f) * PFNudgeRateScale * Flight->GetYawRateMaxDeg(ViewForwardSpeed, Flight->GetShapedBoost(), false) * StepDt;

	bPFFree = bAimHeld;

	// Parked free look (polish P3): at rest with no drive / sidestep / turn / boost key the mouse looks around and the
	// heading holds, as on foot. The first such key takes the camera's yaw as the heading (below). An outside set (harness,
	// reset) still sets the heading, as in steering mode. Entering needs |forward speed| < PFParkSpeed; once parked it holds
	// at any speed until such a key, Aim, or an outside set above PFParkSpeed (follow-up F-B): a hit or a collision that
	// pushes the ship past PFParkSpeed no longer ends it, so the heading holds and the heading loop turns a knocked hull back
	const bool bParkedNow = PFParkSpeed > 0.f && !bPFFree && !bMoveKeys
		&& (FMath::Abs(ViewForwardSpeed) < PFParkSpeed || (bPFParked && !bExternal));

	if (bParkedNow)
	{
		if (bExternal)
		{
			PFHeading = ControlYaw;
			PFLookOffset = 0.f;
		}
		else
		{
			PFLookOffset += LookDelta;
		}

		bPFLock = false;
		PFLockDwell = 0.f;
		PFPrevOffBeam = -1.f;
		PFOffBeamRate = 0.f;
		PFLockSwingDir = 0;
	}
	else if (bPFFree)
	{
		// Broadside mode: the camera looks around, the heading holds; Q/E turn the ship, the camera stays on its point
		PFLookOffset += LookDelta;
		PFHeading += Nudge;
		PFLookOffset -= Nudge;

		// The gun lock is armed only while Fire is held or PFLockArmTime s after the pilot's own broadside (polish P4):
		// Aim alone is a clean free look
		const UWorld* World = GetWorld();
		const double Now = World ? World->GetTimeSeconds() : 0.0;
		const bool bLockArmed = PFLockArmTime <= 0.f || bFireHeld || Now - LastOwnBroadsideTime <= static_cast<double>(PFLockArmTime);

		if (Nudge != 0.f || !bLockArmed)
		{
			// A manual turn overrides the gun lock; unarmed, it forgets the aim's approach too
			bPFLock = false;
			PFLockDwell = 0.f;
			PFLockSwingDir = 0;

			if (!bLockArmed)
			{
				PFPrevOffBeam = -1.f;
				PFOffBeamRate = 0.f;
			}
		}
		else if (bPFArcAssist)
		{
			const float LockedHeading = PointFlyGunLock(PFHeading, PFHeading + PFLookOffset, StepDt);
			PFLookOffset -= WrapDeg(LockedHeading - PFHeading);
			PFHeading = LockedHeading;
		}
	}
	else
	{
		if (bPFParked)
		{
			// The first frame out of parking in steering mode: go where the camera looks. A drive / sidestep / turn / boost
			// key, or an outside set above PFParkSpeed (then the set yaw, below); a push past PFParkSpeed alone keeps the
			// ship parked (above). The reach clamp keeps the camera still: the part beyond PFHeadingMaxLeadDeg eases back as
			// after broadside mode.
			const float CameraYaw = bExternal ? ControlYaw : WrapDeg(PFHeading + PFLookOffset + LookDelta);
			const float CameraLead = WrapDeg(CameraYaw - ViewYaw);
			PFHeading = FMath::Abs(CameraLead) <= PFHeadingMaxLeadDeg ? CameraYaw : WrapDeg(ViewYaw + (CameraLead > 0.f ? PFHeadingMaxLeadDeg : -PFHeadingMaxLeadDeg));
			PFLookOffset = WrapDeg(CameraYaw - PFHeading);
			LookDelta = 0.f;
		}

		// Steering mode: the camera yaw is the heading target
		if (bExternal)
		{
			PFHeading = ControlYaw;
			PFLookOffset = 0.f;
		}
		else
		{
			PFHeading += LookDelta;
		}
		PFHeading += Nudge;

		// Ease back onto the heading after broadside mode
		PFLookOffset *= FMath::Exp(-StepDt / FMath::Max(PFLookReturnTau, 1e-3f));

		if (FMath::Abs(PFLookOffset) < 0.05f)
		{
			PFLookOffset = 0.f;
		}

		bPFLock = false;
		PFLockDwell = 0.f;
		PFPrevOffBeam = -1.f;
		PFOffBeamRate = 0.f;
		PFLockSwingDir = 0;

		// The target stays within reach of the nose (no +-180 flip on the server)
		const float Lead = WrapDeg(PFHeading - ViewYaw);

		if (FMath::Abs(Lead) > PFHeadingMaxLeadDeg)
		{
			PFHeading = ViewYaw + (Lead > 0.f ? PFHeadingMaxLeadDeg : -PFHeadingMaxLeadDeg);
		}
	}

	bPFParked = bParkedNow;
	PFHeading = WrapDeg(PFHeading);
	PFLookOffset = WrapDeg(PFLookOffset);
	PFLastSetYaw = WrapDeg(PFHeading + PFLookOffset);

	const float Pitch = FMath::Clamp(WrapDeg(static_cast<float>(Control.Pitch)), CameraPitchMin, CameraPitchMax);
	PC->SetControlRotation(FRotator(Pitch, PFLastSetYaw, 0.f));
}

float AAirshipPawn::PointFlyGunLock(float H, float CamYaw, float Dt)
{
	using namespace AirshipPawnPrivate;

	// The aim's bearing off the heading TARGET (not the lagging hull: no loop over the network), its distance from the
	// beam, and how fast that closes (filtered, review R2)
	const float Bearing = WrapDeg(CamYaw - H);
	const float AbsBearing = FMath::Abs(Bearing);
	const float OffBeamAbs = FMath::Abs(AbsBearing - 90.f);
	const float RateRaw = (PFPrevOffBeam >= 0.f && Dt > 0.f) ? (OffBeamAbs - PFPrevOffBeam) / Dt : 0.f;
	PFPrevOffBeam = OffBeamAbs;
	PFOffBeamRate = ApproachExp(PFOffBeamRate, RateRaw, Dt, PFArcApproachTau);

	// Looking ahead or astern: plain free look (review R1: the sector starts at 55 deg)
	if (AbsBearing < PFArcMinBearingDeg || AbsBearing > PFArcMaxBearingDeg)
	{
		bPFLock = false;
		PFLockDwell = 0.f;
		PFLockSwingDir = 0;
		return H;
	}

	if (!bPFLock)
	{
		// Outside the arc and not coming in (a target the ship is sailing past is waited for) long enough: lock
		const bool bOutside = OffBeamAbs > CannonYawLimitDeg - PFArcMarginDeg;
		const bool bComingIn = PFOffBeamRate < -PFArcApproachRateDeg;
		PFLockDwell = (bOutside && !bComingIn) ? PFLockDwell + Dt : 0.f;

		if (PFLockDwell >= PFArcLockDelay)
		{
			bPFLock = true;
			AddFeedback(FeedbackLockEngage);
		}
	}

	if (!bPFLock)
	{
		return H;
	}

	// Locked: the beam stays within the dead band of the aim, swinging at most PFArcRateDeg
	const float OffBeam = AbsBearing - 90.f;

	if (FMath::Abs(OffBeam) <= PFArcLockDeadbandDeg)
	{
		PFLockSwingDir = 0;
		return H;
	}

	const float Excess = OffBeam - (OffBeam > 0.f ? PFArcLockDeadbandDeg : -PFArcLockDeadbandDeg);
	const float MaxSwing = PFArcRateDeg * Dt;
	const float Swing = FMath::Clamp((Bearing > 0.f ? 1.f : -1.f) * Excess, -MaxSwing, MaxSwing);
	PFLockSwingDir = Swing > 0.f ? 1 : (Swing < 0.f ? -1 : 0);
	return H + Swing;
}

void AAirshipPawn::AddFeedback(const FAirshipFeedbackEvent& Event, float FOVSign)
{
	// The pilot's machine only (camera and rumble)
	if (!IsLocallyControlled())
	{
		return;
	}

	CameraTrauma = FMath::Clamp(CameraTrauma + Event.Trauma, 0.f, 1.f);
	CameraFOVKick += FOVSign * Event.FOVKickDeg;
	PlayRumble(Event.Rumble, Event.RumbleTime, Event.bRumbleLarge);
}

void AAirshipPawn::PlayRumble(float Intensity, float Duration, bool bLarge)
{
	APlayerController* PC = Cast<APlayerController>(GetController());

	if (!PC || !PC->IsLocalController() || RumbleScale <= 0.f || Intensity <= 0.f || Duration <= 0.f)
	{
		return;
	}

	// The native overload (6 arguments; the 8-argument one is the Blueprint latent action)
	PC->PlayDynamicForceFeedback(FMath::Min(Intensity * RumbleScale, 1.f), Duration, bLarge, !bLarge, bLarge, !bLarge);
}

void AAirshipPawn::UpdateFeedback(float DeltaSeconds, const FAirshipCosmeticState& C)
{
	const UWorld* World = GetWorld();

	if (!World || !Camera || !Flight)
	{
		return;
	}

	// ---- Events on this machine --------------------------------------------------------------------------------------
	// Boost start: the gated boost bit this machine flies with
	const bool bBoostBit = Flight->GetCurrentControls().IsBoost();

	if (bBoostBit && !bPrevBoostBit)
	{
		AddFeedback(FeedbackBoostStart);
	}
	bPrevBoostBit = bBoostBit;

	// The v1 drift kick when a long drift ends (Galleon: the swing's exit surge; Point & Fly: the brake-drift). Sky
	// Racer pays mini-turbos instead.
	const bool bLocalDrift = Flight->IsDrifting();

	if (bLocalDrift)
	{
		LocalDriftTime += DeltaSeconds;
	}
	else
	{
		if (bPrevLocalDrift && ControlScheme != EAirshipControlScheme::SkyRacer && LocalDriftTime >= Flight->DriftBoostMinTime && Flight->DriftBoostDV > 0.f)
		{
			// The punch follows the kick this drift pays (DriftBoostCapSpeed, Point & Fly: none at cruise); 1 without the cap
			const float KickShare = FMath::Clamp(Flight->GetDriftKickDV(C.ForwardSpeed) / Flight->DriftBoostDV, 0.f, 1.f);

			if (KickShare >= 0.999f)
			{
				AddFeedback(FeedbackDriftKick);
			}
			else if (KickShare > 0.05f)
			{
				FAirshipFeedbackEvent Scaled = FeedbackDriftKick;
				Scaled.Trauma *= KickShare;
				Scaled.FOVKickDeg *= KickShare;
				Scaled.Rumble *= KickShare;
				AddFeedback(Scaled);
			}
		}
		LocalDriftTime = 0.f;
	}
	bPrevLocalDrift = bLocalDrift;

	// Sky Racer: a mini-turbo released on this machine
	if (C.TurboEventCount != LastTurboEventCount)
	{
		LastTurboEventCount = C.TurboEventCount;
		AddFeedback(C.TurboTier >= 3 ? FeedbackTurbo3 : (C.TurboTier == 2 ? FeedbackTurbo2 : FeedbackTurbo1));
	}

	// ---- Trauma shake and camera roll (the camera component, relative to the boom: aim and control rotation untouched)
	CameraTrauma = FMath::Max(0.f, CameraTrauma - ShakeDecay * DeltaSeconds);

	if (C.bDrifting)
	{
		CameraTrauma = FMath::Max(CameraTrauma, FMath::Min(1.f, DriftTraumaBase + DriftTraumaPerCharge * C.DriftCharge));
	}

	CameraFOVKick *= FMath::Exp(-FOVKickDecay * DeltaSeconds);

	const float Trauma2 = FMath::Square(CameraTrauma);
	const float Jitter = ShakeRotDeg * Trauma2;
	const float Wobble = ShakeLocCm * Trauma2;
	const float RollTarget = FMath::Clamp(CameraRollPerBank * static_cast<float>(GetActorRotation().Roll)
		+ CameraRollPerSteerDeg * C.Steer * (C.bGunDeck ? Flight->GunDeckBankScale : 1.f), -CameraRollMaxDeg, CameraRollMaxDeg);
	CameraRollDeg = CameraRollInterpSpeed > 0.f ? FMath::FInterpTo(CameraRollDeg, RollTarget, DeltaSeconds, CameraRollInterpSpeed) : RollTarget;

	// All off (Classic): the camera's relative transform is never touched
	const bool bFeedbackActive = Jitter > 0.f || Wobble > 0.f || CameraRollDeg != 0.f;

	if (bFeedbackActive || bCameraFeedbackApplied)
	{
		// PerlinNoise1D repeats every 256: the wrapped time keeps its precision in a long session
		const float T = static_cast<float>(FMath::Fmod(World->GetTimeSeconds() * static_cast<double>(ShakeFrequency), 256.0));
		Camera->SetRelativeRotation(FRotator(Jitter * FMath::PerlinNoise1D(T + 11.3f), Jitter * FMath::PerlinNoise1D(T + 47.1f),
			CameraRollDeg + Jitter * FMath::PerlinNoise1D(T + 83.9f)));
		Camera->SetRelativeLocation(FVector(Wobble * FMath::PerlinNoise1D(T + 5.1f), Wobble * FMath::PerlinNoise1D(T + 19.7f),
			Wobble * FMath::PerlinNoise1D(T + 61.3f)));
		bCameraFeedbackApplied = bFeedbackActive;
	}

	// ---- The continuous drift rumble (small motors) ------------------------------------------------------------------
	APlayerController* PC = Cast<APlayerController>(GetController());
	const float DriftRumble = (C.bDrifting && RumbleScale > 0.f)
		? FMath::Clamp((DriftRumbleBase + DriftRumblePerCharge * C.DriftCharge) * RumbleScale, 0.f, 1.f)
		: 0.f;

	if (DriftRumble > 0.f && PC && PC->IsLocalController())
	{
		if (DriftRumblePC.Get() != PC)
		{
			StopDriftRumble();
		}

		const EDynamicForceFeedbackAction::Type Action = DriftRumbleHandle != 0 ? EDynamicForceFeedbackAction::Update : EDynamicForceFeedbackAction::Start;
		const FDynamicForceFeedbackHandle Handle = PC->PlayDynamicForceFeedback(DriftRumble, -1.f, false, true, false, true, Action, DriftRumbleHandle);
		DriftRumbleHandle = Handle;
		DriftRumblePC = PC;
	}
	else
	{
		StopDriftRumble();
	}
}

void AAirshipPawn::StopDriftRumble()
{
	if (DriftRumbleHandle != 0)
	{
		if (APlayerController* RumblePC = DriftRumblePC.Get())
		{
			RumblePC->PlayDynamicForceFeedback(0.f, 0.f, false, false, false, false, EDynamicForceFeedbackAction::Stop, DriftRumbleHandle);
		}
	}

	DriftRumbleHandle = 0;
	DriftRumblePC.Reset();
}

#undef AIRSHIP_FC_EXISTING_SCHEME_PROPS
#undef AIRSHIP_FC_BASEFIX_PROPS
#undef AIRSHIP_FC_SHARED_PROPS
#undef AIRSHIP_FC_GALLEON_PROPS
#undef AIRSHIP_FC_SKYRACER_PROPS
#undef AIRSHIP_FC_POINTFLY_PROPS
#undef AIRSHIP_FC_SCHEME_PROPS
#undef AIRSHIP_PAWN_EXISTING_SCHEME_PROPS
#undef AIRSHIP_PAWN_SHARED_PROPS
#undef AIRSHIP_PAWN_GALLEON_PROPS
#undef AIRSHIP_PAWN_SKYRACER_PROPS
#undef AIRSHIP_PAWN_POINTFLY_PROPS
#undef AIRSHIP_PAWN_SCHEME_PROPS
#undef AIRSHIP_BOOM_SCHEME_PROPS
