// Fill out your copyright notice in the Description page of Project Settings.


#include "Burrower/BurrowerCharacter.h"

#include "AIController.h"
#include "AbilitySystem/MyAbilitySystemComponent.h"
#include "AbilitySystem/MyAttributeSet.h"
#include "AbilitySystem/Data/DA_MyEnemyCharacterClassInfo.h"
#include "Actors/MyHexPlatform.h"
#include "Components/BoxComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/SplineMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/WidgetComponent.h"
#include "DrawDebugHelpers.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/GameStateBase.h"
#include "GameFramework/PlayerState.h"
#include "GameplayEffect.h"
#include "HAL/IConsoleManager.h"
#include "Interfaces/MyCombatInterface.h"
#include "MyGameMode.h"
#include "Net/UnrealNetwork.h"
#include "PhysicsEngine/BodyInstance.h"
#include "PhysicsEngine/BodySetup.h"
#include "UI/UserWidgets/MyUserWidget.h"

DEFINE_LOG_CATEGORY_STATIC(LogBurrower, Log, All);

// Named, not anonymous: the unity build compiles this file together with others
namespace BurrowerCharacterPrivate
{
	TAutoConsoleVariable<int32> CVarDebugRotorBox(
		TEXT("Aura.Burrower.DebugRotorBox"),
		0,
		TEXT("1: the server draws every Burrower's rotor box at each tile check (green, red when it cut tiles; the box stretched by the sweep and lead in yellow)."),
		ECVF_Default);

	// Below this speed (cm/s) the replicated velocity counts as "already stopped"
	constexpr double MinMovingSpeed = 10.0;

	// A client's rotation only changes when a movement update arrives: a turn-rate sample spans the time since the
	// last change, and after this long (s) without one it counts as not turning
	constexpr double MaxTurnSampleGap = 0.25;

	// Time constant (s) of the turn-rate smoothing
	constexpr double TurnRateSmoothingTime = 0.12;
}

ABurrowerCharacter::ABurrowerCharacter()
{
	PrimaryActorTick.bCanEverTick = true;

	// The kill looks up the XP reward of CharacterClass in DA_CharClassInfo (UMyAttributeSet), so it must have an entry there
	CharacterClass = ECharacterClass::Warrior;
	CharacterLevel = 1;
	LifeSpan = 10.f;

	// A handful exist at a time and they move fast: every client always gets them
	bAlwaysRelevant = true;

	// AddMovementInput needs a controller for the movement component to run on the server
	AutoPossessAI = EAutoPossessAI::PlacedInWorldOrSpawned;
	AIControllerClass = AAIController::StaticClass();

	// The server sets the rotation itself (heading toward the target)
	bUseControllerRotationPitch = false;
	bUseControllerRotationYaw = false;
	bUseControllerRotationRoll = false;

	// Flying, no navmesh: the hex platforms float and collapse
	UCharacterMovementComponent* Move = GetCharacterMovement();
	Move->DefaultLandMovementMode = MOVE_Flying;
	Move->bOrientRotationToMovement = false;
	Move->bUseControllerDesiredRotation = false;
	Move->MaxFlySpeed = FollowSpeed;
	Move->MaxAcceleration = 4000.f;
	Move->BrakingDecelerationFlying = 2000.f;
	Move->GravityScale = 0.f;

	// The capsule covers the head (head body of the physics asset: centre mesh (830, 0, 187), radius 160).
	// It collides with nothing, so it flies through the tiles it cuts and through the level.
	UCapsuleComponent* Capsule = GetCapsuleComponent();
	Capsule->InitCapsuleSize(160.f, 190.f);
	Capsule->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
	Capsule->SetCollisionObjectType(ECC_Pawn);
	Capsule->SetCollisionResponseToAllChannels(ECR_Ignore);
	Capsule->SetGenerateOverlapEvents(false);

	// The mesh faces +X; its origin (ground level under the body centre) sits behind and below the head
	USkeletalMeshComponent* MeshComp = GetMesh();
	MeshComp->SetRelativeLocationAndRotation(FVector(-830.0, 0.0, -187.0), FRotator::ZeroRotator);

	// Hits land on the physics asset bodies: the aim, Electrocute and Shards query ECC_Visibility, projectiles overlap
	MeshComp->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
	MeshComp->SetCollisionObjectType(ECC_Pawn);
	MeshComp->SetCollisionResponseToAllChannels(ECR_Ignore);
	MeshComp->SetCollisionResponseToChannel(ECC_Visibility, ECR_Block);
	MeshComp->SetCollisionResponseToChannel(ECC_WorldDynamic, ECR_Overlap);
	MeshComp->SetCollisionResponseToChannel(ECC_PhysicsBody, ECR_Overlap);
	MeshComp->SetGenerateOverlapEvents(true);

	// The rotor (rig: centre mesh (977.9, 0, 180.5), radius 105.8, 55.8 deep along X), on the mesh, not the bone
	RotorBox = CreateDefaultSubobject<UBoxComponent>(TEXT("RotorBox"));
	RotorBox->SetupAttachment(MeshComp);
	RotorBox->SetRelativeLocation(FVector(977.9, 0.0, 180.5));
	RotorBox->InitBoxExtent(RotorHalfSize + FVector(RotorBoxPadding));
	RotorBox->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	RotorBox->SetGenerateOverlapEvents(false);
	RotorBox->SetCanEverAffectNavigation(false);
	RotorBox->SetHiddenInGame(true);

	// Player-only parts the base class always creates
	JetPackMeshComponent->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	JetPackMeshComponent->SetGenerateOverlapEvents(false);
	JetPackMeshComponent->SetHiddenInGame(true);
	BeamSplineMeshComponent->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	BeamSplineMeshComponent->SetGenerateOverlapEvents(false);
	BeamSplineMeshComponent->SetHiddenInGame(true);
	// USplineMeshComponent is Static by default; attached to the movable capsule that logs "cannot attach ... static"
	BeamSplineMeshComponent->SetMobility(EComponentMobility::Movable);

	// Above the head, on screen (set WBP_HealthBar as its Widget Class in BP_Burrower)
	HealthBarWidgetComponent->SetRelativeLocation(FVector(0.0, 0.0, 400.0));
	HealthBarWidgetComponent->SetWidgetSpace(EWidgetSpace::Screen);
	HealthBarWidgetComponent->SetCollisionEnabled(ECollisionEnabled::NoCollision);
}

void ABurrowerCharacter::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);

	DOREPLIFETIME(ABurrowerCharacter, TargetPlayer);
	DOREPLIFETIME(ABurrowerCharacter, bBurrowerDead);
}

void ABurrowerCharacter::OnConstruction(const FTransform& Transform)
{
	Super::OnConstruction(Transform);

	ApplyRotorBoxExtent();
}

void ABurrowerCharacter::BeginPlay()
{
	// AMyEnemyChar::BeginPlay uses the health bar widget without a check: an empty native one if BP_Burrower sets none
	if (HealthBarWidgetComponent && !HealthBarWidgetComponent->GetWidgetClass())
	{
		HealthBarWidgetComponent->SetWidgetClass(UMyUserWidget::StaticClass());
	}

	ApplyRotorBoxExtent();

	// InitAbilityActorInfo(this, this), startup abilities (keep the list empty), health bar delegates
	Super::BeginPlay();

	if (HasAuthority())
	{
		InitializeBurrowerAttributes();

		if (bRefreshBonesOnServer)
		{
			GetMesh()->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;
		}
	}

	// A client that got the actor after its death
	if (bBurrowerDead)
	{
		HandleBurrowerDeath();
		return;
	}

	if (HasAuthority())
	{
		GetCharacterMovement()->SetMovementMode(MOVE_Flying);
	}
}

FVector ABurrowerCharacter::GetRotorBoxExtent() const
{
	return RotorHalfSize.GetAbs() + FVector(FMath::Max(RotorBoxPadding, 0.f));
}

void ABurrowerCharacter::ApplyRotorBoxExtent()
{
	if (RotorBox)
	{
		RotorBox->SetBoxExtent(GetRotorBoxExtent(), /*bUpdateOverlaps=*/false);
	}
}


// =============================================================================
// GAS
// =============================================================================

void ABurrowerCharacter::InitializeBurrowerAttributes()
{
	UWorld* World = GetWorld();

	if (!MyAbilitySystemComponent || !World)
	{
		return;
	}

	TSubclassOf<UGameplayEffect> Primary = PrimaryAttributesEffect;
	TSubclassOf<UGameplayEffect> Secondary = SecondaryAttributesEffect;
	TSubclassOf<UGameplayEffect> Vital = VitalAttributesEffect;

	// Unset ones: the same effects the other enemies get (UMyBPFuncLib::InitializeEnemyAttributes, private in C++)
	const AMyGameMode* GameMode = World->GetAuthGameMode<AMyGameMode>();

	if (UDA_MyEnemyCharacterClassInfo* ClassInfo = GameMode ? GameMode->DA_MyEnemyCharacterClassInfo : nullptr)
	{
		if (!Primary)
		{
			Primary = ClassInfo->GetInfoForClass(CharacterClass).PrimaryAttributesEffect;
		}

		if (!Secondary)
		{
			Secondary = ClassInfo->SecondaryAttributesEffect;
		}

		if (!Vital)
		{
			Vital = ClassInfo->VitalAttributesEffect;
		}
	}
	else
	{
		// The kill reads the same data asset (UMyBPFuncLib::GetXPRewardForCharacterClass, no null check)
		UE_LOG(LogBurrower, Error, TEXT("%s: the GameMode is not an AMyGameMode with DA_MyEnemyCharacterClassInfo set"), *GetName());
	}

	FGameplayEffectContextHandle Context = MyAbilitySystemComponent->MakeEffectContext();
	Context.AddInstigator(this, this);

	// Secondary derives from primary; vital fills up to the max that secondary set (PreAttributeChange clamps Health)
	const TSubclassOf<UGameplayEffect> Effects[] = { Primary, Secondary, Vital };

	for (const TSubclassOf<UGameplayEffect>& Effect : Effects)
	{
		if (!Effect)
		{
			UE_LOG(LogBurrower, Error, TEXT("%s: an attribute effect is missing, so MaxHealth stays 0 (set it on the Blueprint or fill DA_CharClassInfo)"), *GetName());
			continue;
		}

		const FGameplayEffectSpecHandle Spec = MyAbilitySystemComponent->MakeOutgoingSpec(Effect, static_cast<float>(CharacterLevel), Context);

		if (Spec.IsValid())
		{
			MyAbilitySystemComponent->ApplyGameplayEffectSpecToSelf(*Spec.Data.Get());
		}
	}
}


// =============================================================================
// Death
// =============================================================================

void ABurrowerCharacter::Die()
{
	if (!HasAuthority() || bIsDead || bBurrowerDead)
	{
		return;
	}

	// For clients that get the actor later (the multicast only reaches those connected now)
	bBurrowerDead = true;

	// AMyEnemyChar: SetLifeSpan(LifeSpan); AMyCharBase: MulticastHandleDeath
	Super::Die();
}

void ABurrowerCharacter::MulticastHandleDeath_Implementation()
{
	HandleBurrowerDeath();
}

void ABurrowerCharacter::OnRep_BurrowerDead()
{
	// The actor's first bunch arrives before BeginPlay, which runs it then
	if (bBurrowerDead && HasActorBegunPlay())
	{
		HandleBurrowerDeath();
	}
}

void ABurrowerCharacter::HandleBurrowerDeath()
{
	// The multicast and bBurrowerDead both lead here
	if (bIsDead)
	{
		return;
	}

	// Before the movement stops: what the ragdoll starts with (the Control Rig reads it through the AnimBP)
	CaptureDeathMotion();

	if (UCharacterMovementComponent* Move = GetCharacterMovement())
	{
		Move->StopMovementImmediately();
		Move->DisableMovement();
	}

	if (RotorBox)
	{
		RotorBox->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	}

	bHasLastRotorBoxCentre = false;

	if (bHideHealthBarOnDeath && HealthBarWidgetComponent)
	{
		HealthBarWidgetComponent->SetHiddenInGame(true);
	}

	if (bUseMeshRagdollFallback)
	{
		// Physics collision before the bodies start simulating (they are QueryOnly while alive)
		GetMesh()->SetCollisionEnabled(ECollisionEnabled::PhysicsOnly);

		// Base: the physics asset simulates (gravity, blocks WorldStatic, PhysicsOnly so nothing hits the corpse),
		// capsule off, slot 0 dissolve, bIsDead, OnDeathDelegate
		Super::MulticastHandleDeath_Implementation();

		// Before their first simulated step
		ApplyDeathMotionToMeshBodies();
	}
	else
	{
		// Control Rig ragdoll (UBurrowerAnimInstance::bIsDead): the mesh stays kinematic, since a simulating mesh
		// takes the bones from the AnimBP. Nothing may hit the corpse (each fatal hit would pay XP again).
		GetCapsuleComponent()->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		GetMesh()->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Dissolve();

		// Before the broadcast: listeners call IsDead()
		bIsDead = true;
		OnDeathDelegate.Broadcast(this);
	}

	BP_OnBurrowerDied();
}

void ABurrowerCharacter::SampleDeathMotion()
{
	using namespace BurrowerCharacterPrivate;

	const UWorld* World = GetWorld();

	if (!World)
	{
		return;
	}

	const FVector CurrentVelocity = GetVelocity();

	if (CurrentVelocity.SizeSquared() > FMath::Square(MinMovingSpeed))
	{
		LastMovingVelocity = CurrentVelocity;
	}

	const double Now = World->GetTimeSeconds();
	const FRotator Rotation = GetActorRotation();

	if (!bHasTurnSample)
	{
		LastTurnSampleRotation = Rotation;
		LastTurnSampleTime = Now;
		bHasTurnSample = true;
		return;
	}

	const double Elapsed = Now - LastTurnSampleTime;

	if (Elapsed <= UE_KINDA_SMALL_NUMBER)
	{
		return;
	}

	// The server turns the actor every tick. A client's actor only turns when a movement update arrives, so it
	// measures from one change to the next (the rate over the gap) instead of every tick (0, 0, then a jump).
	if (!HasAuthority() && Rotation.Equals(LastTurnSampleRotation, 1.e-3) && Elapsed < MaxTurnSampleGap)
	{
		return;
	}

	// Clamped: a spawn or a teleport is not a turn
	const double MaxRate = 2.0 * FMath::Max(static_cast<double>(TurnRate), 1.0);
	const double YawSample = FMath::Clamp(FMath::FindDeltaAngleDegrees(LastTurnSampleRotation.Yaw, Rotation.Yaw) / Elapsed, -MaxRate, MaxRate);
	const double PitchSample = FMath::Clamp(FMath::FindDeltaAngleDegrees(LastTurnSampleRotation.Pitch, Rotation.Pitch) / Elapsed, -MaxRate, MaxRate);
	const double Alpha = 1.0 - FMath::Exp(-Elapsed / TurnRateSmoothingTime);

	TurnYawRateDeg = FMath::Lerp(TurnYawRateDeg, YawSample, Alpha);
	TurnPitchRateDeg = FMath::Lerp(TurnPitchRateDeg, PitchSample, Alpha);

	LastTurnSampleRotation = Rotation;
	LastTurnSampleTime = Now;
}

void ABurrowerCharacter::CaptureDeathMotion()
{
	using namespace BurrowerCharacterPrivate;

	// A client may get the server's stop (replicated velocity 0) before or with the death multicast
	FVector Inherited = GetVelocity();

	if (!HasAuthority() && Inherited.SizeSquared() <= FMath::Square(MinMovingSpeed))
	{
		Inherited = LastMovingVelocity;
	}

	DeathVelocity = bInheritVelocityOnDeath ? Inherited * static_cast<double>(DeathVelocityScale) : FVector::ZeroVector;

	// Omega such that a point at offset R from the actor moves at Omega x R (radians), as the physics bodies do:
	// * yaw: FRotator yaw grows from +X toward +Y, and UpVector x ForwardVector = +Y, so it is +Z * yaw rate.
	// * pitch: nose up is pitch growing, and RightVector x ForwardVector = -Z (nose down), so it is -Right * pitch rate.
	// Worked example, heading +X (Right = +Y), the tail 1800 cm behind the head (R = (-1800, 0, 0)):
	// * yaw rate +40 deg/s: Omega = (0, 0, 0.698) rad/s, Omega x R = (0, -1257, 0): the nose turns toward +Y and
	//   the tail swings toward -Y about the head, as the rigid body does.
	// * pitch rate +20 deg/s (nose rising): Omega = (0, -0.349, 0), Omega x R = (0, 0, -628): the tail drops.
	// For a body lying on a constant turn of radius r = |V| / |Omega|, V + Omega x R is the rotation about the turn's
	// centre, so every body moves along the curve (the corpse keeps curving).
	DeathAngularVelocity = bInheritTurnOnDeath
		? FVector::UpVector * TurnYawRateDeg - GetActorRightVector() * TurnPitchRateDeg
		: FVector::ZeroVector;
}

void ABurrowerCharacter::ApplyDeathMotionToMeshBodies()
{
	USkeletalMeshComponent* MeshComp = GetMesh();

	// Not simulating: a dedicated server (SetSimulatePhysics does nothing there) or no physics asset
	if (!MeshComp || !MeshComp->IsSimulatingPhysics() || (DeathVelocity.IsNearlyZero() && DeathAngularVelocity.IsNearlyZero()))
	{
		return;
	}

	const FVector OmegaRadians = DeathAngularVelocity * (UE_DOUBLE_PI / 180.0);
	const FVector Pivot = GetActorLocation();

	for (FBodyInstance* Body : MeshComp->Bodies)
	{
		if (!Body || !Body->IsValidBodyInstance())
		{
			continue;
		}

		// Kinematic bodies of the physics asset don't simulate
		const UBodySetup* Setup = Body->GetBodySetup();

		if (Setup && Setup->PhysicsType == EPhysicsType::PhysType_Kinematic)
		{
			continue;
		}

		const FVector Offset = Body->GetCOMPosition() - Pivot;

		Body->SetLinearVelocity(DeathVelocity + FVector::CrossProduct(OmegaRadians, Offset), /*bAddToCurrent=*/false);
		Body->SetAngularVelocityInRadians(OmegaRadians, /*bAddToCurrent=*/false);
	}
}


// =============================================================================
// Target
// =============================================================================

void ABurrowerCharacter::SetTargetPlayer(APawn* NewTarget)
{
	if (!HasAuthority() || TargetPlayer == NewTarget)
	{
		return;
	}

	TargetPlayer = NewTarget;
}

bool ABurrowerCharacter::IsLivingTarget(APawn* Pawn, bool bRequireCombatInterface)
{
	if (!IsValid(Pawn))
	{
		return false;
	}

	const bool bCombat = Pawn->Implements<UMyCombatInterface>();

	if (!bCombat)
	{
		return !bRequireCombatInterface;
	}

	return !IMyCombatInterface::Execute_IsDead(Pawn);
}

FVector ABurrowerCharacter::GetBehindDirection(const APawn* Pawn, float MinSpeed)
{
	if (!Pawn)
	{
		return -FVector::ForwardVector;
	}

	const FVector Velocity = Pawn->GetVelocity();
	const FVector Velocity2D(Velocity.X, Velocity.Y, 0.0);

	if (Velocity2D.SizeSquared() > FMath::Square(FMath::Max(MinSpeed, 1.f)))
	{
		return -Velocity2D.GetSafeNormal();
	}

	const FVector Forward = Pawn->GetActorForwardVector().GetSafeNormal2D();

	return Forward.IsNearlyZero() ? -FVector::ForwardVector : -Forward;
}

APawn* ABurrowerCharacter::FindNearestLivingPlayer() const
{
	const UWorld* World = GetWorld();
	const AGameStateBase* GameState = World ? World->GetGameState() : nullptr;

	if (!GameState)
	{
		return nullptr;
	}

	APawn* Best = nullptr;
	double BestDistSq = TNumericLimits<double>::Max();
	const FVector Location = GetActorLocation();

	// Not named PlayerState: that is an APawn member (MSVC C4458, an error at this warning level)
	for (const TObjectPtr<APlayerState>& OtherPlayerState : GameState->PlayerArray)
	{
		APawn* Pawn = OtherPlayerState ? OtherPlayerState->GetPawn() : nullptr;

		if (!IsLivingTarget(Pawn, /*bRequireCombatInterface=*/true))
		{
			continue;
		}

		const double DistSq = FVector::DistSquared(Location, Pawn->GetActorLocation());

		if (DistSq < BestDistSq)
		{
			BestDistSq = DistSq;
			Best = Pawn;
		}
	}

	return Best;
}


// =============================================================================
// Tick: follow, rotor (server); death motion samples (every machine)
// =============================================================================

void ABurrowerCharacter::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);

	if (bIsDead)
	{
		return;
	}

	if (HasAuthority())
	{
		// Placed in the level: pick the nearest living player, once a second while it has none
		if (!bTargetManagedBySpawner && bAutoTargetNearestPlayer)
		{
			AutoTargetTimer -= DeltaTime;

			if (AutoTargetTimer <= 0.f)
			{
				AutoTargetTimer = 1.f;

				if (!IsLivingTarget(TargetPlayer, /*bRequireCombatInterface=*/false))
				{
					SetTargetPlayer(FindNearestLivingPlayer());
				}
			}
		}

		UpdateFollow(DeltaTime);

		RotorCheckTimer += DeltaTime;

		if (RotorCheckTimer >= RotorCheckInterval)
		{
			// The remainder carries over, so the checks keep their interval instead of rounding up to whole frames
			RotorCheckTimer = RotorCheckInterval > 0.f ? FMath::Fmod(RotorCheckTimer, RotorCheckInterval) : 0.f;
			CheckRotorTiles(DeltaTime);
		}
	}

	// After the server's turn this tick, so its sample is exactly this tick's turn
	SampleDeathMotion();
}

void ABurrowerCharacter::UpdateFollow(float DeltaTime)
{
	UCharacterMovementComponent* Move = GetCharacterMovement();

	if (!Move || DeltaTime <= 0.f)
	{
		return;
	}

	APawn* Target = TargetPlayer;

	// Nothing to follow: no input, so the flying braking slows it down
	if (!IsLivingTarget(Target, /*bRequireCombatInterface=*/false))
	{
		Move->MaxFlySpeed = FollowSpeed;
		return;
	}

	FVector Goal = Target->GetActorLocation() + FVector(0.0, 0.0, FollowHeightOffset);

	if (KeepBehindDistance > 0.f)
	{
		Goal += GetBehindDirection(Target, 150.f) * KeepBehindDistance;
	}

	const FVector ToGoal = Goal - GetActorLocation();
	const double Distance = ToGoal.Size();

	// Faster when far behind
	float CatchUpAlpha = 0.f;

	if (CatchUpFullDistance > CatchUpStartDistance)
	{
		CatchUpAlpha = FMath::Clamp(static_cast<float>((Distance - CatchUpStartDistance) / (CatchUpFullDistance - CatchUpStartDistance)), 0.f, 1.f);
	}
	else if (Distance > CatchUpStartDistance)
	{
		CatchUpAlpha = 1.f;
	}

	Move->MaxFlySpeed = FMath::Lerp(FollowSpeed, FMath::Max(CatchUpSpeed, FollowSpeed), CatchUpAlpha);

	// Heading: yaw and pitch each turn toward the goal at TurnRate at most, so the body sweeps in curves. Apart, not
	// along one arc: with the goal behind and a little above or below, that arc is nearly all pitch, which the
	// pitch clamp throws away, and the yaw would hardly turn.
	const FRotator Current = GetActorRotation();
	const FRotator Wanted = ToGoal.Rotation();
	const double MaxStep = static_cast<double>(TurnRate) * DeltaTime;
	const double MaxPitchDeg = static_cast<double>(MaxPitch);

	FRotator HeadingRotation(Current.Pitch, Current.Yaw, 0.0);

	// Straight above or below: no yaw to turn to
	if (ToGoal.SizeSquared2D() > 1.0)
	{
		HeadingRotation.Yaw = Current.Yaw + FMath::Clamp(FMath::FindDeltaAngleDegrees(Current.Yaw, Wanted.Yaw), -MaxStep, MaxStep);
	}

	const double CurrentPitch = FRotator::NormalizeAxis(Current.Pitch);
	const double WantedPitch = FMath::Clamp(FRotator::NormalizeAxis(Wanted.Pitch), -MaxPitchDeg, MaxPitchDeg);
	HeadingRotation.Pitch = CurrentPitch + FMath::Clamp(WantedPitch - CurrentPitch, -MaxStep, MaxStep);

	SetActorRotation(HeadingRotation);

	// Throttle, from the front of the blades (the rotor box without its padding, about 1.8 m ahead of the actor
	// location): full beyond SlowdownDistance, none inside StopDistance
	const double BladeReach = RotorBox ? FVector::Dist(RotorBox->GetComponentLocation(), GetActorLocation()) + FMath::Abs(RotorHalfSize.X) : 0.0;
	const double ThrottleDistance = FMath::Max(Distance - BladeReach, 0.0);
	float Throttle = 1.f;

	if (ThrottleDistance <= StopDistance)
	{
		Throttle = 0.f;
	}
	else if (SlowdownDistance > StopDistance)
	{
		Throttle = FMath::Clamp(static_cast<float>((ThrottleDistance - StopDistance) / (SlowdownDistance - StopDistance)), 0.f, 1.f);
	}

	// Moves along its heading (the movement component's acceleration is limited by MaxAcceleration)
	AddMovementInput(HeadingRotation.Vector(), Throttle);
}

void ABurrowerCharacter::CheckRotorTiles(float DeltaTime)
{
	UWorld* World = GetWorld();

	if (!World || !RotorBox || (!bCutTopPlatforms && !bCutBottomPlatforms))
	{
		return;
	}

	FTransform BoxToWorld = RotorBox->GetComponentTransform();
	FVector Extent = RotorBox->GetScaledBoxExtent();
	const FVector Centre = BoxToWorld.GetLocation();
	const FVector AxisX = BoxToWorld.GetUnitAxis(EAxis::X);
	bool bStretched = false;

	if (bSweepRotorBox)
	{
		// Back along its X over the distance moved since the last check, so it can't skip a tile.
		// A jump of more than 20 m (spawn, teleport) isn't a sweep.
		if (bHasLastRotorBoxCentre)
		{
			const double Moved = FVector::DotProduct(Centre - LastRotorBoxCentre, AxisX);
			const double MovedAbs = FMath::Abs(Moved);

			if (MovedAbs > 1.0 && MovedAbs < 2000.0)
			{
				BoxToWorld.SetLocation(BoxToWorld.GetLocation() - AxisX * (Moved * 0.5));
				Extent.X += MovedAbs * 0.5;
				bStretched = true;
			}
		}

		// Forward over the distance it moves before the next check, so a tile goes when the padded box reaches it,
		// not up to a check later (at 3200 cm/s a check is 1.6 m)
		const double Lead = FMath::Max(FVector::DotProduct(GetVelocity(), AxisX), 0.0) * FMath::Max(RotorCheckInterval, DeltaTime);

		if (Lead > 1.0)
		{
			BoxToWorld.SetLocation(BoxToWorld.GetLocation() + AxisX * (Lead * 0.5));
			Extent.X += Lead * 0.5;
			bStretched = true;
		}
	}

	LastRotorBoxCentre = Centre;
	bHasLastRotorBoxCentre = true;

	// Every platform, not a physics query, so the tiles' collision settings don't matter: each one first tests the
	// box against the bounds of its grid (one inverse transform), then against the same tiles it collapses
	int32 NumCut = 0;

	for (TActorIterator<AMyHexPlatform> It(World); It; ++It)
	{
		AMyHexPlatform* Platform = *It;

		if (Platform->IsBottomPlatform() ? bCutBottomPlatforms : bCutTopPlatforms)
		{
			NumCut += Platform->ActivateTilesInWorldBox(BoxToWorld, Extent);
		}
	}

#if !UE_BUILD_SHIPPING
	if (BurrowerCharacterPrivate::CVarDebugRotorBox.GetValueOnGameThread() > 0)
	{
		const float LifeTime = FMath::Max(RotorCheckInterval, 0.f);
		DrawDebugBox(World, Centre, RotorBox->GetScaledBoxExtent(), BoxToWorld.GetRotation(), NumCut > 0 ? FColor::Red : FColor::Green, false, LifeTime, 0, 4.f);

		if (bStretched)
		{
			DrawDebugBox(World, BoxToWorld.GetLocation(), Extent, BoxToWorld.GetRotation(), FColor::Yellow, false, LifeTime, 0, 2.f);
		}
	}
#endif
}
