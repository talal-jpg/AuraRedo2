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
}

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
}

void AAirshipPawn::BeginPlay()
{
	// Components first (UAirshipFlightComponent reads the mesh bones and sets mass, centre of mass, damping)
	Super::BeginPlay();

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

	// Axes and held buttons are read every frame (GatherLocalInput)
	for (const UInputAction* Action : { ThrottleAction.Get(), SteerAction.Get(), LiftAction.Get(), StrafeAction.Get(), BoostAction.Get(), BrakeAction.Get(), AimAction.Get() })
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
}

void AAirshipPawn::RemoveLocalMappingContext()
{
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

	FAirshipPilotInput Controls;

	if (Flight->HasDebugInput())
	{
		// Test hook (DebugSetInput, Aura.Airship.Input) on the pilot's machine: in place of the keys, so a client's debug
		// controls reach the server the same way (ServerSetPilotInput) instead of only moving its own cosmetics
		Controls = Flight->GetDebugInput();
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

	OutYawDeg = FMath::Clamp(static_cast<float>(FMath::RadiansToDegrees(YawRad)), -CannonYawLimitDeg, CannonYawLimitDeg);
	OutElevDeg = FMath::Clamp(static_cast<float>(FMath::RadiansToDegrees(ElevRad)), CannonElevMinDeg, CannonElevMaxDeg);
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
			FX->SetVariableFloat(FXBoostParam, C.Boost);
		}
	}

	for (int32 Fan = 0; Fan < Airship::NumFans; ++Fan)
	{
		if (UNiagaraComponent* FX = Turbines[Fan]; FX && FX->GetAsset())
		{
			FX->SetVariableFloat(FXThrustParam, FMath::Abs(C.FanThrust[Fan]));
			FX->SetVariableFloat(FXBoostParam, C.Boost);
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

	if (bPendingCameraReset)
	{
		Control = FRotator(CameraDefaultPitch, GetActorRotation().Yaw, 0.0);
		bControlChanged = true;
		bPendingCameraReset = false;
	}

	Control.Pitch = FRotator::NormalizeAxis(Control.Pitch);

	// Recenter behind the ship when the pilot doesn't look around
	if (RecenterSpeed > 0.f && Now - LastLookInputTime > RecenterDelay && C.ForwardSpeed > RecenterMinSpeed && !C.bAiming)
	{
		const double Alpha = 1.0 - FMath::Exp(-RecenterSpeed * DeltaSeconds);
		Control.Yaw += FRotator::NormalizeAxis(GetActorRotation().Yaw - Control.Yaw) * Alpha;
		Control.Pitch += (CameraDefaultPitch - Control.Pitch) * Alpha;
		bControlChanged = true;
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

	// Zoom, and the camera falls back on boost
	const float ArmTarget = ZoomTarget + CameraBoostArmExtra * C.Boost;
	CameraBoom->TargetArmLength = FMath::FInterpTo(CameraBoom->TargetArmLength, ArmTarget, DeltaSeconds, CameraZoomInterpSpeed);

	// FOV: speed, boost, aim, plus the player's FOV setting (AMyPlayerController2 applies it once per change)
	const float SpeedAlpha = FMath::Clamp((C.ForwardSpeed - SpeedFOVStart) / FMath::Max(SpeedFOVFull - SpeedFOVStart, 1.f), 0.f, 1.f);
	float TargetFOV = BaseFOV + SpeedFOVExtra * SpeedAlpha + BoostFOVExtra * C.Boost + (C.bAiming ? AimFOVOffset : 0.f);

	if (const UMyGameUserSettings* Settings = UMyGameUserSettings::GetMyGameUserSettings())
	{
		TargetFOV += Settings->GetFieldOfView() - UMyGameUserSettings::DefaultFieldOfView;
	}

	Camera->SetFieldOfView(FMath::Clamp(FMath::FInterpTo(Camera->FieldOfView, TargetFOV, DeltaSeconds, FOVInterpSpeed), 20.f, 170.f));
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
	const double FreeUp = bIsDead ? 0.0 : Free;
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

	if (!HasAuthority() || bIsDead || ImpactDamagePerMS <= 0.f)
	{
		return;
	}

	// Its own pilot and cannonballs, and characters (a kinematic capsule would count as a wall hit)
	if (OtherActor && (OtherActor == this || OtherActor->IsAttachedTo(this) || OtherActor->IsA<AAirshipCannonball>() || OtherActor->IsA<ACharacter>()))
	{
		return;
	}

	if (OtherComp && OtherComp->GetCollisionObjectType() == ECC_Pawn)
	{
		return;
	}

	const float Mass = HullCollision->GetMass();

	if (Mass <= KINDA_SMALL_NUMBER)
	{
		return;
	}

	// NormalImpulse is the contact's accumulated impulse: below a small speed change it's resting contact, not a hit
	const float ImpulseSpeed = static_cast<float>(NormalImpulse.Size()) / Mass;

	if (ImpulseSpeed < 50.f)
	{
		return;
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

	if (ImpactSpeed < ImpactMinSpeed)
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

	// Bottom-left corner, fixed size (the widget draws itself in NativePaint)
	const FVector2D Size = Widget->GetPanelSize();
	FGameViewportWidgetSlot Slot;
	Slot.Anchors = FAnchors(0.f, 1.f);
	Slot.Alignment = FVector2D(0.f, 1.f);
	Slot.Offsets = FMargin(ShipHUDCornerOffset.X, -ShipHUDCornerOffset.Y, Size.X, Size.Y);
	Slot.ZOrder = 1;

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

	return true;
}

void AAirshipPawn::HideShipHUD()
{
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
