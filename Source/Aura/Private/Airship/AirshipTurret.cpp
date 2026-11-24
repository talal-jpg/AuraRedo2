// Fill out your copyright notice in the Description page of Project Settings.


#include "Airship/AirshipTurret.h"

#include "AbilitySystemComponent.h"
#include "AbilitySystemGlobals.h"
#include "AbilitySystem/Data/MyGameplayTags.h"
#include "AbilitySystem/MyAbilitySystemComponent.h"
#include "AbilitySystem/MyAttributeSet.h"
#include "Airship/AirshipCannonball.h"
#include "Airship/AirshipDamageEffect.h"
#include "Airship/AirshipPawn.h"
#include "Airship/AirshipSettings.h"
#include "CollisionQueryParams.h"
#include "Components/BoxComponent.h"
#include "Components/SceneComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "GameplayEffect.h"
#include "MechSwarm/Combat/MechSentinelCombatLibrary.h"
#include "MechSwarm/Core/MechSentinelSwarmSubsystem.h"
#include "Net/UnrealNetwork.h"
#include "NiagaraComponent.h"
#include "NiagaraDataChannel.h"
#include "NiagaraDataChannelAccessor.h"
#include "NiagaraDataChannelFunctionLibrary.h"
#include "NiagaraFunctionLibrary.h"
#include "NiagaraSystem.h"
#include "TimerManager.h"

DEFINE_LOG_CATEGORY_STATIC(LogAirshipTurret, Log, All);

// Named, not anonymous: the unity build compiles this file together with others
namespace AirshipTurretPrivate
{
	/** The gun's tracer channel (MuzzlePos, HitLocation), used when the Blueprint sets none. */
	const TCHAR* GunTracerChannelPath = TEXT("/Game/Assets/Effects/AppreiticeFx/GunShootHit/NDC_GunShootHit.NDC_GunShootHit");

	/** Rounds one tick may fire after a hitch (the clock then drops what is left: no burst of catch-up rounds). */
	constexpr int32 MaxShotsPerTick = 4;

	/** Own cannonballs a round's line looks past (each one is a re-trace). */
	constexpr int32 MaxOwnBallRetraces = 4;

	/** Attach parents a hit looks up for an ASC (a weapon or prop attached to a character or another ship). */
	constexpr int32 MaxAttachDepth = 4;

	/**
	 * The ship sets the command every one of its ticks; one older than this (s) no longer fires (a safety net: the
	 * turret never keeps shooting on a command nobody refreshes).
	 */
	constexpr double ServerCommandTimeout = 0.5;

	/** A client that got the turret less than this long ago (s) was not there for the explosion. */
	constexpr double LateJoinExplosionWindow = 0.5;

	/** Other machines turn toward the replicated aim this much faster than the server (they catch up between updates). */
	constexpr float ReplicatedSlewScale = 2.f;

	/** A wreck's barrel sags toward the lower pitch limit at this rate (deg/s). */
	constexpr float WreckSagRateDeg = 30.f;

	int16 QuantizeDeg(float Deg)
	{
		return static_cast<int16>(FMath::Clamp(FMath::RoundToInt(Deg * 100.f), -32767, 32767));
	}

	float DequantizeDeg(int16 Value)
	{
		return static_cast<float>(Value) / 100.f;
	}
}

AAirshipTurret::AAirshipTurret()
{
	PrimaryActorTick.bCanEverTick = true;
	// After physics: the hull has moved this frame, so the muzzle the rounds leave from is where it is drawn
	PrimaryActorTick.TickGroup = TG_PostPhysics;

	bReplicates = true;
	// Attachment replication (the turret rides the hull on every machine)
	SetReplicatingMovement(true);
	// Like the ship: seen from far away
	bAlwaysRelevant = true;
	SetNetUpdateFrequency(30.f);

	Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	SetRootComponent(Root);

	HitBox = CreateDefaultSubobject<UBoxComponent>(TEXT("HitBox"));
	HitBox->SetupAttachment(Root);
	HitBox->InitBoxExtent(FVector(60.0, 60.0, 95.0));
	HitBox->SetRelativeLocation(FVector(0.0, 0.0, 95.0));
	HitBox->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
	HitBox->SetCollisionObjectType(ECC_WorldDynamic);
	HitBox->SetCollisionResponseToAllChannels(ECR_Block);
	// Spring arms pass through it; characters (deck riders, its gunner one metre behind it) walk through it
	HitBox->SetCollisionResponseToChannel(ECC_Camera, ECR_Ignore);
	HitBox->SetCollisionResponseToChannel(ECC_Pawn, ECR_Ignore);
	// AMyProjectile (fireballs) damages on overlap
	HitBox->SetGenerateOverlapEvents(true);
	HitBox->SetCanEverAffectNavigation(false);

	BaseMesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("BaseMesh"));
	BaseMesh->SetupAttachment(Root);
	BaseMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	BaseMesh->SetGenerateOverlapEvents(false);
	BaseMesh->SetCanEverAffectNavigation(false);

	GunMesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("GunMesh"));
	GunMesh->SetupAttachment(BaseMesh);
	GunMesh->SetRelativeLocation(FVector(0.0, 0.0, PivotHeight));
	GunMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	GunMesh->SetGenerateOverlapEvents(false);
	GunMesh->SetCanEverAffectNavigation(false);

	Muzzle = CreateDefaultSubobject<USceneComponent>(TEXT("Muzzle"));
	Muzzle->SetupAttachment(GunMesh);
	Muzzle->SetRelativeLocation(FVector(MuzzleForward, 0.0, 0.0));

	MuzzleFXComponent = CreateDefaultSubobject<UNiagaraComponent>(TEXT("MuzzleFXComponent"));
	MuzzleFXComponent->SetupAttachment(Muzzle);
	MuzzleFXComponent->SetAutoActivate(false);

	DestroyedFXComponent = CreateDefaultSubobject<UNiagaraComponent>(TEXT("DestroyedFXComponent"));
	DestroyedFXComponent->SetupAttachment(Root);
	DestroyedFXComponent->SetAutoActivate(false);

	// Replicated, Mixed (UMyAbilitySystemComponent's constructor); InitializeComponent finds the attribute set
	AbilitySystemComponent = CreateDefaultSubobject<UMyAbilitySystemComponent>(TEXT("AbilitySystemComponent"));
	AttributeSet = CreateDefaultSubobject<UMyAttributeSet>(TEXT("AttributeSet"));
}

void AAirshipTurret::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);

	DOREPLIFETIME_CONDITION(AAirshipTurret, Ship, COND_InitialOnly);
	DOREPLIFETIME_CONDITION(AAirshipTurret, TurretIndex, COND_InitialOnly);
	DOREPLIFETIME_CONDITION(AAirshipTurret, Mount, COND_InitialOnly);
	DOREPLIFETIME(AAirshipTurret, bDestroyed);
	DOREPLIFETIME(AAirshipTurret, HeatQ);
	DOREPLIFETIME(AAirshipTurret, bOverheated);
	DOREPLIFETIME(AAirshipTurret, AimYawQ);
	DOREPLIFETIME(AAirshipTurret, AimPitchQ);
}

void AAirshipTurret::InitTurret(AAirshipPawn* InShip, int32 InTurretIndex, const FAirshipTurretMount& InMount)
{
	Ship = InShip;
	TurretIndex = InTurretIndex;
	Mount = InMount;
	bHasShip = InShip != nullptr;
}

void AAirshipTurret::BeginPlay()
{
	Super::BeginPlay();

	BeginPlayTime = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0;
	ApplyGeometry();

	AbilitySystemComponent->InitAbilityActorInfo(this, this);

	if (HasAuthority())
	{
		// MaxHealth first: PreAttributeChange clamps Health to it
		AbilitySystemComponent->SetNumericAttributeBase(UMyAttributeSet::GetMaxHealthAttribute(), TurretMaxHealth);
		AbilitySystemComponent->SetNumericAttributeBase(UMyAttributeSet::GetHealthAttribute(), TurretMaxHealth);
		AbilitySystemComponent->SetNumericAttributeBase(UMyAttributeSet::GetArmorAttribute(), TurretArmor);

		// Sentinel bullets hit it through their Visibility trace (actor tags don't replicate; hits are server-only).
		// The ship adds it too after spawning; this covers a turret spawned any other way.
		Tags.AddUnique(UMechSentinelSwarmSubsystem::BulletTargetTag);

		CachedGunBaseDamage = ReadGunBaseDamage();
		UE_LOG(LogAirshipTurret, Log, TEXT("%s: turret %d on %s at %s, bullet damage %.2f (%.2f x gun %.2f), health %.0f."),
			*GetName(), TurretIndex, *GetNameSafe(GetShip()), *Mount.Location.ToCompactString(), GetBulletDamage(),
			UAirshipSettings::Get()->TurretGunDamageMultiplier, CachedGunBaseDamage, TurretMaxHealth);
	}
	else if (bDestroyed)
	{
		// Got the actor after it was wrecked (joined late): burning, no explosion
		PlayDestroyedFX(false);
	}
}

void AAirshipTurret::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	GetWorldTimerManager().ClearAllTimersForObject(this);

	if (MuzzleFXComponent)
	{
		MuzzleFXComponent->DeactivateImmediate();
	}

	PendingSentinelSegments.Reset();
	bSentinelFlushQueued = false;

	Super::EndPlay(EndPlayReason);
}

void AAirshipTurret::ApplyGeometry()
{
	if (GunMesh)
	{
		GunMesh->SetRelativeLocation(FVector(0.0, 0.0, PivotHeight));
	}

	if (Muzzle)
	{
		Muzzle->SetRelativeLocation(FVector(MuzzleForward, 0.0, 0.0));
	}
}

void AAirshipTurret::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	// Attached actors don't go with their parent: a turret whose ship is gone (destroyed without its EndPlay cleanup) goes too
	if (HasAuthority() && bHasShip && !IsValid(Ship))
	{
		Destroy();
		return;
	}

	UpdateAim(DeltaSeconds);

	if (HasAuthority())
	{
		UpdateServerFire(DeltaSeconds);
	}
	else
	{
		UpdatePredictedFire(DeltaSeconds);
	}
}


// -----------------------------------------------------------------------------
// Commands, aim
// -----------------------------------------------------------------------------

void AAirshipTurret::SetServerCommand(const FAirshipTurretCommand& Command)
{
	if (!HasAuthority())
	{
		return;
	}

	ServerCommand = Command;
	ServerCommandTime = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0;
}

void AAirshipTurret::SetLocalCommand(const FAirshipTurretCommand& Command)
{
	// The server's own aim and rounds come from SetServerCommand
	if (HasAuthority())
	{
		return;
	}

	LocalCommand = Command;
	LocalCommandTime = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0;
}

bool AAirshipTurret::IsServerCommandFresh() const
{
	const UWorld* World = GetWorld();
	return HasAuthority() && World && ServerCommandTime >= 0.0 && World->GetTimeSeconds() - ServerCommandTime <= AirshipTurretPrivate::ServerCommandTimeout;
}

bool AAirshipTurret::HasFreshLocalCommand() const
{
	const UWorld* World = GetWorld();
	return !HasAuthority() && World && LocalCommandTime >= 0.0 && World->GetTimeSeconds() - LocalCommandTime <= LocalCommandTimeout;
}

void AAirshipTurret::ComputeAimRaw(const FVector& WorldPoint, float& OutYawDeg, float& OutPitchDeg) const
{
	// The turret's frame is the mount's (hull rotation, origin on the deck at the yaw axis), so the ship's heel and
	// pitch are already in it. The pivot is on the yaw axis, PivotHeight above the deck.
	const FVector Local = GetActorTransform().InverseTransformPositionNoScale(WorldPoint) - FVector(0.0, 0.0, PivotHeight);

	OutYawDeg = static_cast<float>(FMath::RadiansToDegrees(FMath::Atan2(Local.Y, Local.X)));
	OutPitchDeg = static_cast<float>(FMath::RadiansToDegrees(FMath::Atan2(Local.Z, FVector2D(Local.X, Local.Y).Size())));
}

bool AAirshipTurret::IsAimInArc(const FVector& WorldPoint, float ToleranceDeg) const
{
	float YawDeg = 0.f;
	float PitchDeg = 0.f;
	ComputeAimRaw(WorldPoint, YawDeg, PitchDeg);

	return YawDeg >= Mount.YawMinDeg - ToleranceDeg && YawDeg <= Mount.YawMaxDeg + ToleranceDeg
		&& PitchDeg >= Mount.PitchMinDeg - ToleranceDeg && PitchDeg <= Mount.PitchMaxDeg + ToleranceDeg;
}

void AAirshipTurret::UpdateAim(float DeltaSeconds)
{
	using namespace AirshipTurretPrivate;

	float TargetYaw = 0.f;
	float TargetPitch = 0.f;
	float RateScale = 1.f;

	// Which command aims the meshes on this machine: the server's own (a stale one = none), a controlling client's fresh
	// local one (no round trip for its own gun), else the server's replicated aim
	const FAirshipTurretCommand* Command = nullptr;
	bool bFollowReplicated = false;

	if (HasAuthority())
	{
		Command = IsServerCommandFresh() ? &ServerCommand : nullptr;
	}
	else if (HasFreshLocalCommand())
	{
		Command = &LocalCommand;
	}
	else
	{
		bFollowReplicated = true;
	}

	if (bDestroyed)
	{
		// The wreck's barrel sags and stays where the yaw stopped
		TargetYaw = CurrentYawDeg;
		TargetPitch = Mount.PitchMinDeg;
		RateScale = WreckSagRateDeg / FMath::Max(PitchRateDeg, 1.f);
	}
	else if (bFollowReplicated)
	{
		TargetYaw = DequantizeDeg(AimYawQ);
		TargetPitch = DequantizeDeg(AimPitchQ);
		RateScale = ReplicatedSlewScale;
	}
	else if (Command && Command->bHasAim)
	{
		// Beyond the limits the gun waits at the nearest one (it fires only within ArcToleranceDeg of them)
		ComputeAimRaw(Command->AimPoint, TargetYaw, TargetPitch);
		TargetYaw = FMath::Clamp(TargetYaw, Mount.YawMinDeg, Mount.YawMaxDeg);
		TargetPitch = FMath::Clamp(TargetPitch, Mount.PitchMinDeg, Mount.PitchMaxDeg);
	}
	// else no aim: rest (straight ahead, level)

	// The limits never span +-180, so the yaw moves linearly (no wrap)
	CurrentYawDeg = FMath::FInterpConstantTo(CurrentYawDeg, TargetYaw, DeltaSeconds, YawRateDeg * RateScale);
	CurrentPitchDeg = FMath::FInterpConstantTo(CurrentPitchDeg, TargetPitch, DeltaSeconds, PitchRateDeg * RateScale);

	// Only on a change: each set moves the gun, the muzzle and the flash
	if (BaseMesh && CurrentYawDeg != AppliedYawDeg)
	{
		BaseMesh->SetRelativeRotation(FRotator(0.f, CurrentYawDeg, 0.f));
		AppliedYawDeg = CurrentYawDeg;
	}

	if (GunMesh && CurrentPitchDeg != AppliedPitchDeg)
	{
		GunMesh->SetRelativeRotation(FRotator(CurrentPitchDeg, 0.f, 0.f));
		AppliedPitchDeg = CurrentPitchDeg;
	}

	if (HasAuthority())
	{
		AimYawQ = QuantizeDeg(CurrentYawDeg);
		AimPitchQ = QuantizeDeg(CurrentPitchDeg);
	}
}

FVector AAirshipTurret::GetMuzzleLocation() const
{
	return Muzzle ? Muzzle->GetComponentLocation() : GetActorLocation() + GetActorUpVector() * PivotHeight;
}

FVector AAirshipTurret::GetBarrelDirection() const
{
	return Muzzle ? Muzzle->GetForwardVector() : GetActorForwardVector();
}


// -----------------------------------------------------------------------------
// Fire
// -----------------------------------------------------------------------------

int32 AAirshipTurret::AdvanceShotClock(bool bCanFire, float DeltaSeconds, float& InOutClock, bool& bInOutFiring) const
{
	using namespace AirshipTurretPrivate;

	if (!bCanFire)
	{
		bInOutFiring = false;
		InOutClock = 0.f;
		return 0;
	}

	if (!bInOutFiring)
	{
		// Turret 0 fires at once, turret 1 half an interval later: the two guns alternate
		bInOutFiring = true;
		InOutClock = FireInterval - static_cast<float>(TurretIndex) * FireInterval * 0.5f;
	}

	InOutClock += DeltaSeconds;

	int32 Due = 0;

	while (InOutClock >= FireInterval && Due < MaxShotsPerTick)
	{
		InOutClock -= FireInterval;
		++Due;
	}

	if (Due >= MaxShotsPerTick)
	{
		InOutClock = FMath::Min(InOutClock, FireInterval);
	}

	return Due;
}

void AAirshipTurret::UpdateServerFire(float DeltaSeconds)
{
	const UWorld* World = GetWorld();

	if (!World)
	{
		return;
	}

	const double Now = World->GetTimeSeconds();
	AAirshipPawn* OwnShip = GetShip();

	const bool bCanFire = IsServerCommandFresh() && ServerCommand.bTrigger && ServerCommand.bHasAim && !bDestroyed && !bOverheated
		&& OwnShip && !OwnShip->IsAirshipDead() && IsAimInArc(ServerCommand.AimPoint, ArcToleranceDeg);

	const int32 Due = AdvanceShotClock(bCanFire, DeltaSeconds, ShotClock, bServerFiring);
	int32 Fired = 0;

	if (Due > 0)
	{
		FCollisionQueryParams Params(SCENE_QUERY_STAT(AirshipTurretShot), false, this);
		BuildShotQueryParams(Params);

		// The gunner (damage numbers and XP), or the ship for the driver and the console
		AActor* DamageInstigator = ServerCommand.Instigator.Get();

		if (!DamageInstigator)
		{
			DamageInstigator = OwnShip;
		}

		for (int32 Shot = 0; Shot < Due && !bOverheated; ++Shot)
		{
			FireOneShot(Params, DamageInstigator);
			++Fired;

			Heat += HeatPerShot;

			// 30 x (1/30) lands a hair under 1 in floats
			if (Heat >= 1.f - KINDA_SMALL_NUMBER)
			{
				Heat = 1.f;
				bOverheated = true;
				UE_LOG(LogAirshipTurret, Verbose, TEXT("%s: overheated."), *GetName());
			}
		}
	}

	if (Fired > 0)
	{
		LastShotTime = Now;
		PlayMuzzleFlash();
	}
	else if (LastShotTime < 0.0 || Now - LastShotTime >= CoolDelay)
	{
		Heat = FMath::Max(0.f, Heat - CoolRate * DeltaSeconds);
	}

	if (bOverheated && Heat <= OverheatRecover)
	{
		bOverheated = false;
		UE_LOG(LogAirshipTurret, Verbose, TEXT("%s: cooled down."), *GetName());
	}

	HeatQ = static_cast<uint8>(FMath::Clamp(FMath::RoundToInt(Heat * 255.f), 0, 255));

	if (PendingShots.Num() > 0)
	{
		MulticastShots(PendingShots);
		PendingShots.Reset();
		// Unreliable multicasts wait for the next net update
		ForceNetUpdate();
	}
}

void AAirshipTurret::UpdatePredictedFire(float DeltaSeconds)
{
	AAirshipPawn* OwnShip = GetShip();

	// The replicated overheat lags by a round trip: a tracer or two too many at the edge, cosmetic only
	const bool bCanFire = HasFreshLocalCommand() && LocalCommand.bTrigger && LocalCommand.bHasAim && !bDestroyed && !bOverheated
		&& OwnShip && !OwnShip->IsAirshipDead() && IsAimInArc(LocalCommand.AimPoint, ArcToleranceDeg);

	const int32 Due = AdvanceShotClock(bCanFire, DeltaSeconds, LocalShotClock, bLocalFiring);

	if (Due <= 0)
	{
		return;
	}

	FCollisionQueryParams Params(SCENE_QUERY_STAT(AirshipTurretPredictedShot), false, this);
	BuildShotQueryParams(Params);

	for (int32 Shot = 0; Shot < Due; ++Shot)
	{
		// The look of the round only: the same trace as the server (spread is random, so the ends differ), no damage
		const FVector Start = GetMuzzleLocation();
		const FVector Dir = SpreadDeg > 0.f ? FMath::VRandCone(GetBarrelDirection(), FMath::DegreesToRadians(SpreadDeg)) : GetBarrelDirection();
		const FVector End = Start + Dir * Range;

		FHitResult Hit;
		const bool bHit = TraceShotLine(Start, End, Params, Hit);
		DrawTracer(Start, bHit ? FVector(Hit.ImpactPoint) : End);
		++ShotCount;
	}

	PlayMuzzleFlash();
}

void AAirshipTurret::BuildShotQueryParams(FCollisionQueryParams& Params) const
{
	Params.AddIgnoredActor(this);

	AAirshipPawn* OwnShip = GetShip();

	if (!OwnShip)
	{
		return;
	}

	// The ship and everything on it: both turrets, the pilot, the gunners (recursive), and the deck riders (not attached).
	// Riders by IsRiderForDamage, not the passenger zone: an enemy jumping or hovering next to the ship is shot.
	Params.AddIgnoredActor(OwnShip);

	TArray<AActor*> Attached;
	OwnShip->GetAttachedActors(Attached, true, true);
	Params.AddIgnoredActors(Attached);

	for (ACharacter* Rider : OwnShip->GetDamageRiders())
	{
		Params.AddIgnoredActor(Rider);

		// A rider's own attached actors (weapons) too
		TArray<AActor*> RiderAttached;
		Rider->GetAttachedActors(RiderAttached, true, true);
		Params.AddIgnoredActors(RiderAttached);
	}
}

bool AAirshipTurret::TraceShotLine(const FVector& Start, const FVector& End, FCollisionQueryParams& Params, FHitResult& OutHit) const
{
	using namespace AirshipTurretPrivate;

	const UWorld* World = GetWorld();

	if (!World)
	{
		return false;
	}

	const AAirshipPawn* OwnShip = GetShip();

	for (int32 Retrace = 0; ; ++Retrace)
	{
		if (!World->LineTraceSingleByChannel(OutHit, Start, End, ECC_Visibility, Params))
		{
			return false;
		}

		// Cannonballs block Visibility: this ship's own are looked past (they stay ignored for the rest of the batch)
		const AAirshipCannonball* Ball = Cast<AAirshipCannonball>(OutHit.GetActor());

		if (Ball && OwnShip && Ball->GetSourceShip() == OwnShip && Retrace < MaxOwnBallRetraces)
		{
			Params.AddIgnoredActor(Ball);
			continue;
		}

		// Another ship's hull over its forward deck: its turrets sit inside that collision, so the round goes on to the
		// turret behind it (the server damages that one; a predicted tracer ends there too)
		if (const AAirshipPawn* HitShip = Cast<AAirshipPawn>(OutHit.GetActor()); HitShip && HitShip != OwnShip)
		{
			FHitResult TurretHit;

			if (HitShip->FindTurretBehindHullHit(OutHit.ImpactPoint, End - Start, TurretHit))
			{
				OutHit = TurretHit;
			}
		}

		return true;
	}
}

AAirshipCannonball* AAirshipTurret::FindBallOnShot(const FVector& Start, const FVector& End, const FCollisionQueryParams& Params, FVector& OutPoint) const
{
	const UWorld* World = GetWorld();

	if (!World || BallSweepRadius <= 0.f || Start.Equals(End, 1.0))
	{
		return nullptr;
	}

	// Balls are WorldDynamic spheres: an object sweep finds the ones the thin line just missed
	TArray<FHitResult> Hits;
	const FCollisionObjectQueryParams Objects(ECC_WorldDynamic);
	World->SweepMultiByObjectType(Hits, Start, End, FQuat::Identity, Objects, FCollisionShape::MakeSphere(BallSweepRadius), Params);

	const AAirshipPawn* OwnShip = GetShip();
	AAirshipCannonball* Best = nullptr;
	float BestDistance = TNumericLimits<float>::Max();

	for (const FHitResult& Hit : Hits)
	{
		AAirshipCannonball* Ball = Cast<AAirshipCannonball>(Hit.GetActor());

		if (!Ball || Ball->IsSpent() || (OwnShip && Ball->GetSourceShip() == OwnShip))
		{
			continue;
		}

		if (Hit.Distance < BestDistance)
		{
			Best = Ball;
			BestDistance = Hit.Distance;
			// A sweep that starts inside the ball has no useful impact point
			OutPoint = Hit.bStartPenetrating ? Ball->GetActorLocation() : FVector(Hit.ImpactPoint);
		}
	}

	return Best;
}

void AAirshipTurret::FireOneShot(FCollisionQueryParams& Params, AActor* DamageInstigator)
{
	const FVector Start = GetMuzzleLocation();
	const FVector Barrel = GetBarrelDirection();
	const FVector Dir = SpreadDeg > 0.f ? FMath::VRandCone(Barrel, FMath::DegreesToRadians(SpreadDeg)) : Barrel;
	const FVector End = Start + Dir * Range;

	FHitResult LineHit;
	const bool bLineHit = TraceShotLine(Start, End, Params, LineHit);

	FVector ShotEnd = bLineHit ? FVector(LineHit.ImpactPoint) : End;
	bool bImpact = bLineHit;

	// Gun units: one bullet = TurretGunDamageMultiplier character-gun hits (the ball's health doesn't depend on the GE value)
	const float BallUnits = UAirshipSettings::Get()->TurretGunDamageMultiplier;

	FVector BallPoint = FVector::ZeroVector;

	if (AAirshipCannonball* SweptBall = FindBallOnShot(Start, ShotEnd, Params, BallPoint))
	{
		// Nearer than whatever the line hit (the sweep stops at the line's hit), or the line hit this very ball
		SweptBall->ApplyShotDamage(BallUnits, DamageInstigator);
		ShotEnd = BallPoint;
		bImpact = true;
	}
	else if (bLineHit)
	{
		if (AAirshipCannonball* LineBall = Cast<AAirshipCannonball>(LineHit.GetActor()))
		{
			// An enemy ball on the line (own ones were looked past; one past the re-trace limit just stops the round)
			const AAirshipPawn* OwnShip = GetShip();

			if (!LineBall->IsSpent() && (!OwnShip || LineBall->GetSourceShip() != OwnShip))
			{
				LineBall->ApplyShotDamage(BallUnits, DamageInstigator);
			}
		}
		else
		{
			ApplyBulletDamage(LineHit, DamageInstigator);
		}
	}

	// Sentinels have no collision: they are queried along the round up to where it stopped
	QueueSentinelSegment(Start, ShotEnd, DamageInstigator);

	FAirshipTurretShot Shot;
	Shot.End = ShotEnd;
	Shot.bImpact = bImpact;
	PendingShots.Add(Shot);
	++ShotCount;

	// The listen host's view (the multicast skips the authority)
	DrawTracer(Start, ShotEnd);
}

void AAirshipTurret::ApplyBulletDamage(const FHitResult& Hit, AActor* DamageInstigator) const
{
	using namespace AirshipTurretPrivate;

	AAirshipPawn* OwnShip = GetShip();
	UAbilitySystemComponent* ShipASC = OwnShip ? OwnShip->GetAbilitySystemComponent() : nullptr;

	if (!ShipASC)
	{
		return;
	}

	// The GAS actor that was hit: the actor itself, or what it is attached to (a weapon on a character, a prop on a ship).
	// Never this ship or what rides on it: those are ignored by the trace.
	UAbilitySystemComponent* TargetASC = nullptr;
	AActor* Target = Hit.GetActor();

	for (int32 Depth = 0; Target && Depth < MaxAttachDepth; ++Depth)
	{
		TargetASC = UAbilitySystemGlobals::GetAbilitySystemComponentFromActor(Target);

		if (TargetASC)
		{
			break;
		}

		Target = Target->GetAttachParentActor();
	}

	// Team checks (a later PR) go here: this is the turret's one target filter
	if (!TargetASC || Target == OwnShip || !TargetASC->HasAttributeSetForAttribute(UMyAttributeSet::GetHealthAttribute()))
	{
		return;
	}

	AActor* Avatar = TargetASC->GetAvatarActor();

	if (Avatar && Avatar->Implements<UMyCombatInterface>() && IMyCombatInterface::Execute_IsDead(Avatar))
	{
		return;
	}

	// The project's damage, like the cannons: a spec from the ship's ASC, SetByCaller SetDamageByCaller. The instigator
	// is the gunner (its ASC is then the source: damage numbers and XP go to it) or the ship; this turret is the causer.
	FGameplayEffectContextHandle Context = ShipASC->MakeEffectContext();
	Context.AddInstigator(DamageInstigator ? DamageInstigator : static_cast<AActor*>(OwnShip), const_cast<AAirshipTurret*>(this));
	Context.AddSourceObject(this);
	Context.AddHitResult(Hit);

	const TSubclassOf<UGameplayEffect> EffectClass = DamageEffectClass ? DamageEffectClass : TSubclassOf<UGameplayEffect>(UAirshipDamageEffect::StaticClass());
	const float Level = static_cast<float>(IMyCombatInterface::Execute_GetLevel(OwnShip));
	const FGameplayEffectSpecHandle Spec = ShipASC->MakeOutgoingSpec(EffectClass, Level, Context);

	if (!Spec.IsValid())
	{
		return;
	}

	Spec.Data->SetSetByCallerMagnitude(MyTags::SetDamageByCaller, GetBulletDamage());
	ShipASC->ApplyGameplayEffectSpecToTarget(*Spec.Data.Get(), TargetASC);

	UE_LOG(LogAirshipTurret, VeryVerbose, TEXT("%s: hit %s for %.2f."), *GetName(), *GetNameSafe(Target), GetBulletDamage());
}

void AAirshipTurret::QueueSentinelSegment(const FVector& Start, const FVector& End, AActor* DamageInstigator)
{
	UWorld* World = GetWorld();
	const UMechSentinelSwarmSubsystem* Swarm = World ? UMechSentinelSwarmSubsystem::Get(World) : nullptr;

	if (!Swarm || !Swarm->HasAuthority() || SentinelShotRadius <= 0.f)
	{
		return;
	}

	PendingSentinelSegments.Emplace(Start, End);
	PendingSentinelInstigator = DamageInstigator;

	// One query batch per frame. Hitting sentinels reads and writes Mass entities, which must not happen while a Mass
	// phase runs (this tick is in TG_PostPhysics, one of them): timers run outside them.
	if (!bSentinelFlushQueued)
	{
		bSentinelFlushQueued = true;
		World->GetTimerManager().SetTimerForNextTick(this, &ThisClass::FlushSentinelSegments);
	}
}

void AAirshipTurret::FlushSentinelSegments()
{
	bSentinelFlushQueued = false;

	TArray<TPair<FVector, FVector>> Segments = MoveTemp(PendingSentinelSegments);
	PendingSentinelSegments.Reset();

	UWorld* World = GetWorld();
	UMechSentinelSwarmSubsystem* Swarm = World ? UMechSentinelSwarmSubsystem::Get(World) : nullptr;

	if (!Swarm || !Swarm->HasAuthority() || Segments.IsEmpty())
	{
		return;
	}

	// The gunner's ASC is the source when there is one (its AttackDamage counts, as for the gun), else the ship's
	AActor* SentinelInstigator = PendingSentinelInstigator.Get();

	if (!SentinelInstigator)
	{
		SentinelInstigator = GetShip() ? static_cast<AActor*>(GetShip()) : static_cast<AActor*>(this);
	}

	const FGameplayEffectSpecHandle Spec = UMechSentinelCombatLibrary::MakeSentinelDamageSpec(World, SentinelInstigator, GetBulletDamage(), nullptr);

	if (!Spec.IsValid())
	{
		return;
	}

	int32 TotalHits = 0;
	float TotalDamage = 0.f;

	for (const TPair<FVector, FVector>& Segment : Segments)
	{
		TArray<FMechSentinelHit> Hits;

		if (Swarm->QueryCapsule(Segment.Key, Segment.Value, SentinelShotRadius, Hits) > 0)
		{
			float Damage = 0.f;
			TotalHits += UMechSentinelCombatLibrary::ApplySpecToHits(*Swarm, *Spec.Data.Get(), Hits, SentinelMaxTargets, &Damage);
			TotalDamage += Damage;
		}
	}

	if (TotalHits > 0)
	{
		UE_LOG(LogAirshipTurret, Verbose, TEXT("%s: %d round(s) hit %d sentinel(s) for %.1f damage."), *GetName(), Segments.Num(), TotalHits, TotalDamage);
	}
}

void AAirshipTurret::MulticastShots_Implementation(const TArray<FAirshipTurretShot>& Shots)
{
	// The server drew its rounds when it fired them (FireOneShot); a dedicated server draws nothing
	if (HasAuthority() || GetNetMode() == NM_DedicatedServer)
	{
		return;
	}

	// The controlling client drew its own while its trigger was held (UpdatePredictedFire). Rounds that arrive after it
	// let go (the round trip's tail) or while it isn't firing (the console, another machine's trigger) are drawn here.
	if (HasFreshLocalCommand() && LocalCommand.bTrigger)
	{
		return;
	}

	const FVector Start = GetMuzzleLocation();

	for (const FAirshipTurretShot& Shot : Shots)
	{
		DrawTracer(Start, Shot.End);
		++ShotCount;
	}

	if (Shots.Num() > 0)
	{
		PlayMuzzleFlash();
	}
}


// -----------------------------------------------------------------------------
// FX
// -----------------------------------------------------------------------------

UNiagaraDataChannelAsset* AAirshipTurret::GetTracerChannel()
{
	if (TracerDataChannel)
	{
		return TracerDataChannel;
	}

	if (!bTracerChannelLookedUp)
	{
		bTracerChannelLookedUp = true;
		FallbackTracerChannel = LoadObject<UNiagaraDataChannelAsset>(nullptr, AirshipTurretPrivate::GunTracerChannelPath, {}, LOAD_NoWarn | LOAD_Quiet);

		if (!FallbackTracerChannel)
		{
			UE_LOG(LogAirshipTurret, Warning, TEXT("%s: no TracerDataChannel and %s not found: no tracers."), *GetName(), AirshipTurretPrivate::GunTracerChannelPath);
		}
	}

	return FallbackTracerChannel;
}

void AAirshipTurret::DrawTracer(const FVector& Start, const FVector& End)
{
	if (GetNetMode() == NM_DedicatedServer)
	{
		return;
	}

	UNiagaraDataChannelAsset* Channel = GetTracerChannel();

	if (!Channel)
	{
		return;
	}

	// As AMechSentinelBulletRelay::ShowBulletsLocal: GameplayBurst channels only accept the access context path, and our
	// own system in the channel (the map key includes the system, so the gun's tracers keep their own bucket)
	FNDCAccessContextInst& AccessContext = UNiagaraDataChannelLibrary::GetUsableAccessContextFromNDC(Channel);

	if (FNDCAccessContext* Context = AccessContext.Get<FNDCAccessContext>())
	{
		Context->Location = Start;
		Context->bOverrideLocation = true;
		Context->bOverrideSystemToSpawn = TracerSystem != nullptr;
		Context->SystemToSpawn = TracerSystem;
	}

	// CPU readers only (the gun's tracer emitters are CPU sims)
	UNiagaraDataChannelWriter* Writer = UNiagaraDataChannelLibrary::WriteToNiagaraDataChannel_WithContext(this, Channel, AccessContext, 1, false, true, false, TEXT("AirshipTurretTracer"));

	if (!Writer)
	{
		return;
	}

	// Variable names must match the channel (the gun's NDC_GunShootHit)
	Writer->WritePosition(TEXT("MuzzlePos"), 0, Start);
	Writer->WritePosition(TEXT("HitLocation"), 0, End);
}

void AAirshipTurret::PlayMuzzleFlash()
{
	if (GetNetMode() == NM_DedicatedServer || !MuzzleFXComponent || !MuzzleFXComponent->GetAsset())
	{
		return;
	}

	// Once per batch of rounds: restart the one-shot flash
	MuzzleFXComponent->Activate(true);

	// Cut it MuzzleFlashMaxSeconds after the last round, whatever its system does (a looping smoke never lingers)
	if (MuzzleFlashMaxSeconds > 0.f)
	{
		GetWorldTimerManager().SetTimer(MuzzleFlashTimer, this, &ThisClass::StopMuzzleFlash, MuzzleFlashMaxSeconds, false);
	}
}

void AAirshipTurret::StopMuzzleFlash()
{
	if (MuzzleFXComponent)
	{
		MuzzleFXComponent->DeactivateImmediate();
	}
}

void AAirshipTurret::PlayDestroyedFX(bool bExplosion)
{
	GetWorldTimerManager().ClearTimer(MuzzleFlashTimer);
	StopMuzzleFlash();

	if (GetNetMode() != NM_DedicatedServer)
	{
		// Burns until the ship (and with it the turret) goes
		if (DestroyedFXComponent && DestroyedFXComponent->GetAsset())
		{
			DestroyedFXComponent->Activate(true);
		}

		if (bExplosion && DestroyedExplosionFX)
		{
			const FVector Location = GetActorLocation() + GetActorUpVector() * PivotHeight;
			UNiagaraFunctionLibrary::SpawnSystemAtLocation(this, DestroyedExplosionFX, Location, GetActorRotation(), FVector(DestroyedExplosionScale));
		}
	}

	BP_OnTurretDestroyed(bExplosion);
}


// -----------------------------------------------------------------------------
// Health, death
// -----------------------------------------------------------------------------

void AAirshipTurret::Die()
{
	if (!HasAuthority())
	{
		return;
	}

	DestroyTurret();
}

void AAirshipTurret::DestroyTurret()
{
	if (!HasAuthority() || bDestroyed)
	{
		return;
	}

	bDestroyed = true;
	ServerCommand = FAirshipTurretCommand();
	bServerFiring = false;
	ShotClock = 0.f;

	// The console's wreck shows an empty bar too (a fatal hit already left Health at 0)
	if (AbilitySystemComponent && AbilitySystemComponent->GetNumericAttribute(UMyAttributeSet::GetHealthAttribute()) > 0.f)
	{
		AbilitySystemComponent->SetNumericAttributeBase(UMyAttributeSet::GetHealthAttribute(), 0.f);
	}

	ForceNetUpdate();

	UE_LOG(LogAirshipTurret, Log, TEXT("%s: turret %d of %s destroyed."), *GetName(), TurretIndex, *GetNameSafe(GetShip()));

	OnDeathDelegate.Broadcast(this);
	PlayDestroyedFX(true);
}

void AAirshipTurret::OnRep_Destroyed()
{
	// Before BeginPlay (the first replication of a late joiner) BeginPlay plays it, without the explosion
	if (!bDestroyed || !HasActorBegunPlay())
	{
		return;
	}

	const UWorld* World = GetWorld();
	const bool bJustArrived = World && World->GetTimeSeconds() - BeginPlayTime < AirshipTurretPrivate::LateJoinExplosionWindow;
	PlayDestroyedFX(!bJustArrived);
}

float AAirshipTurret::GetHeat01() const
{
	return HasAuthority() ? Heat : static_cast<float>(HeatQ) / 255.f;
}

float AAirshipTurret::GetHealth() const
{
	return AttributeSet ? AttributeSet->GetHealth() : 0.f;
}

float AAirshipTurret::GetMaxHealth() const
{
	return AttributeSet ? AttributeSet->GetMaxHealth() : 0.f;
}

AAirshipPawn* AAirshipTurret::GetShip() const
{
	if (Ship)
	{
		return Ship;
	}

	// A client whose replicated reference isn't mapped yet: the owner (the ship spawned it) or the attach parent
	if (AAirshipPawn* OwnerShip = Cast<AAirshipPawn>(GetOwner()))
	{
		return OwnerShip;
	}

	return Cast<AAirshipPawn>(GetAttachParentActor());
}

float AAirshipTurret::GetBulletDamage() const
{
	if (CachedGunBaseDamage < 0.f)
	{
		CachedGunBaseDamage = ReadGunBaseDamage();
	}

	// The multiplier is read every time, so Aura.Airship.Set Settings.TurretGunDamageMultiplier takes effect at once
	return UAirshipSettings::Get()->TurretGunDamageMultiplier * CachedGunBaseDamage;
}

float AAirshipTurret::ReadGunBaseDamage()
{
	const UAirshipSettings* Settings = UAirshipSettings::Get();
	const float Fallback = Settings->GunDamageFallback;

	if (Settings->GunDamageEffect.IsNull())
	{
		return Fallback;
	}

	UClass* EffectClass = Settings->GunDamageEffect.LoadSynchronous();
	const UGameplayEffect* Effect = EffectClass ? GetDefault<UGameplayEffect>(EffectClass) : nullptr;

	if (!Effect)
	{
		UE_LOG(LogAirshipTurret, Warning, TEXT("Gun damage effect %s not found: turret bullets use the fallback %.2f."),
			*Settings->GunDamageEffect.ToString(), Fallback);
		return Fallback;
	}

	// The sum GA_GunShoot::GetSentinelBaseDamage reads (its additive IncomingDamage modifiers), but without a spec: only
	// magnitudes that need no context (a scalable float) count; anything else means the gun's value can't be known here
	float Damage = 0.f;
	bool bFoundDamage = false;

	for (const FGameplayModifierInfo& Modifier : Effect->Modifiers)
	{
		if (Modifier.Attribute != UMyAttributeSet::GetIncomingDamageAttribute() || Modifier.ModifierOp != EGameplayModOp::Additive)
		{
			continue;
		}

		float Magnitude = 0.f;

		if (!Modifier.ModifierMagnitude.GetStaticMagnitudeIfPossible(1.f, Magnitude))
		{
			return Fallback;
		}

		Damage += Magnitude;
		bFoundDamage = true;
	}

	return bFoundDamage ? FMath::Max(0.f, Damage) : Fallback;
}

UAbilitySystemComponent* AAirshipTurret::GetAbilitySystemComponent() const
{
	return AbilitySystemComponent;
}

int32 AAirshipTurret::GetLevel_Implementation()
{
	AAirshipPawn* OwnShip = GetShip();
	return OwnShip ? IMyCombatInterface::Execute_GetLevel(OwnShip) : 1;
}

FVector AAirshipTurret::GetCombatSocketLocation_Implementation()
{
	return GetMuzzleLocation();
}
