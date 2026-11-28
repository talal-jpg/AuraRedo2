// Fill out your copyright notice in the Description page of Project Settings.


#include "Airship/AirshipCannonball.h"

#include "AbilitySystemComponent.h"
#include "AbilitySystemGlobals.h"
#include "AbilitySystem/Data/MyGameplayTags.h"
#include "Airship/AirshipDamageEffect.h"
#include "Airship/AirshipPawn.h"
#include "Components/SphereComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/Engine.h"
#include "Engine/OverlapResult.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "GameFramework/ProjectileMovementComponent.h"
#include "GameplayEffect.h"
#include "Interfaces/MyCombatInterface.h"
#include "Match/MyTeamLibrary.h"
#include "MechSwarm/Combat/MechSentinelCombatLibrary.h"
#include "Net/UnrealNetwork.h"
#include "NiagaraComponent.h"
#include "NiagaraFunctionLibrary.h"
#include "TimerManager.h"

DEFINE_LOG_CATEGORY_STATIC(LogAirshipCannonball, Log, All);

AAirshipCannonball::AAirshipCannonball()
{
	PrimaryActorTick.bCanEverTick = true;

	bReplicates = true;
	// Every machine flies it from the same launch state; the server's impact decides
	SetReplicatingMovement(false);
	bAlwaysRelevant = true;
	InitialLifeSpan = MaxLifeSeconds;

	CollisionSphere = CreateDefaultSubobject<USphereComponent>(TEXT("CollisionSphere"));
	CollisionSphere->InitSphereRadius(Radius);
	CollisionSphere->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
	CollisionSphere->SetCollisionObjectType(ECC_WorldDynamic);
	CollisionSphere->SetCollisionResponseToAllChannels(ECR_Block);
	// Visibility blocks: the character gun's crosshair sweep and the ship turrets' traces hit the ball and can shoot it
	// down (ApplyShotDamage). The ship's own aim traces look past every ball (AAirshipPawn::TraceAimPoint).
	CollisionSphere->SetCollisionResponseToChannel(ECC_Visibility, ECR_Block);
	CollisionSphere->SetCollisionResponseToChannel(ECC_Camera, ECR_Ignore);
	// Pawns: overlap, so a hit on a character (or the Burrower's mesh, which only overlaps) explodes without a bounce
	CollisionSphere->SetCollisionResponseToChannel(ECC_Pawn, ECR_Overlap);
	CollisionSphere->SetGenerateOverlapEvents(true);
	CollisionSphere->SetCanEverAffectNavigation(false);
	SetRootComponent(CollisionSphere);

	BallMesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("BallMesh"));
	BallMesh->SetupAttachment(CollisionSphere);
	BallMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	BallMesh->SetGenerateOverlapEvents(false);
	BallMesh->SetCanEverAffectNavigation(false);

	TrailFX = CreateDefaultSubobject<UNiagaraComponent>(TEXT("TrailFX"));
	TrailFX->SetupAttachment(CollisionSphere);

	Movement = CreateDefaultSubobject<UProjectileMovementComponent>(TEXT("Movement"));
	Movement->SetUpdatedComponent(CollisionSphere);
	// The velocity comes from InitCannonball / LaunchVelocity, in world space (the engine's default would rotate it
	// again by the spawn rotation in InitializeComponent)
	Movement->bInitialVelocityInLocalSpace = false;
	Movement->InitialSpeed = 0.f;
	Movement->MaxSpeed = 0.f;
	Movement->bRotationFollowsVelocity = true;
	Movement->bShouldBounce = false;
	Movement->bIsHomingProjectile = false;
	Movement->ProjectileGravityScale = GravityScale;
}

void AAirshipCannonball::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);

	DOREPLIFETIME_CONDITION(AAirshipCannonball, SourceShip, COND_InitialOnly);
	// Clients' turret tracers look past teammates' balls like the server's rounds (UMyTeamLibrary::GetTeamId)
	DOREPLIFETIME_CONDITION(AAirshipCannonball, SourceTeamId, COND_InitialOnly);
	DOREPLIFETIME_CONDITION(AAirshipCannonball, LaunchVelocity, COND_InitialOnly);
	// Only differs from the class default for a test ball (SpawnTestCannonball's override), so it costs nothing otherwise
	DOREPLIFETIME_CONDITION(AAirshipCannonball, GravityScale, COND_InitialOnly);
	DOREPLIFETIME(AAirshipCannonball, bShotDown);
	DOREPLIFETIME(AAirshipCannonball, ShotDownLocation);
}

void AAirshipCannonball::InitCannonball(AAirshipPawn* InShip, const FVector& InVelocity, const FGameplayEffectSpecHandle& InDamageSpec, float InDamage)
{
	SourceShip = InShip;
	// The ship's team; a free ship's ball takes its shooter's (the spec's instigator: a gunner, or the ship for its pilot)
	const AActor* Shooter = InDamageSpec.IsValid() ? InDamageSpec.Data->GetContext().GetInstigator() : nullptr;
	SourceTeamId = InShip ? UMyTeamLibrary::GetFiringTeamId(InShip, Shooter) : MyMatch::NoTeam;
	LaunchVelocity = InVelocity;
	DamageSpec = InDamageSpec;
	Damage = InDamage;

	if (Movement)
	{
		Movement->Velocity = InVelocity;
	}
}

void AAirshipCannonball::IgnoreActor(AActor* Actor)
{
	if (Actor && CollisionSphere)
	{
		CollisionSphere->IgnoreActorWhenMoving(Actor, true);
	}
}

void AAirshipCannonball::BeginPlay()
{
	Super::BeginPlay();

	// Every machine starts full; only the server counts hits (ApplyShotDamage)
	BallHealth = BallMaxHealth;

	if (CollisionSphere)
	{
		CollisionSphere->SetSphereRadius(Radius);
	}

	if (Movement)
	{
		Movement->ProjectileGravityScale = GravityScale;

		// Every machine starts from the launch velocity (InitCannonball set it on the server, clients get it replicated)
		if (!LaunchVelocity.IsNearlyZero())
		{
			Movement->Velocity = LaunchVelocity;
		}

		Movement->OnProjectileStop.AddDynamic(this, &ThisClass::OnProjectileStop);
	}

	// The ship and its pilot never block the ball (also on clients, so their flight matches)
	if (SourceShip && CollisionSphere)
	{
		CollisionSphere->IgnoreActorWhenMoving(SourceShip, true);

		TArray<AActor*> Attached;
		SourceShip->GetAttachedActors(Attached, true, true);

		for (AActor* Actor : Attached)
		{
			CollisionSphere->IgnoreActorWhenMoving(Actor, true);
		}
	}

	if (CollisionSphere && HasAuthority())
	{
		CollisionSphere->OnComponentBeginOverlap.AddDynamic(this, &ThisClass::OnSphereOverlap);
	}

	SetLifeSpan(MaxLifeSeconds);
	SentinelsHit = MakeShared<TSet<uint64>>();
	LastSweepLocation = GetActorLocation();
	bHasLastSweepLocation = true;

	// A client that first hears of the ball after it was shot down gets bShotDown with the spawn, and its OnRep runs
	// before BeginPlay (which just restarted the flight above): stop it again
	if (bShotDown)
	{
		EnterShotDownState();
	}
}

void AAirshipCannonball::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	if (!HasAuthority() || bExploded || !bDamageSentinels)
	{
		return;
	}

	// Sentinels have no collision: sweep them along the flight
	const FVector Location = GetActorLocation();

	if (bHasLastSweepLocation && !Location.Equals(LastSweepLocation, 1.0))
	{
		QueueSentinelSweep(LastSweepLocation, Location, SentinelHitRadius, false);
	}

	LastSweepLocation = Location;
	bHasLastSweepLocation = true;
}

bool AAirshipCannonball::ShouldIgnore(const AActor* Actor) const
{
	if (!Actor || Actor == this)
	{
		return true;
	}

	if (SourceShip && (Actor == SourceShip || Actor->IsAttachedTo(SourceShip)))
	{
		return true;
	}

	// Deck riders of the firing ship (not attached, so IsAttachedTo misses them): no friendly fire on its own crew.
	// The actor may be something a rider carries, so the character it is attached to counts. IsRiderForDamage, not the
	// wider passenger zone: an enemy jumping or hovering next to the ship is hit.
	if (SourceShip)
	{
		for (const AActor* Link = Actor; Link; Link = Link->GetAttachParentActor())
		{
			const ACharacter* Character = Cast<ACharacter>(Link);

			if (!Character)
			{
				continue;
			}

			if (SourceShip->IsRiderForDamage(Character))
			{
				return true;
			}
			break;
		}
	}

	// Another ball (same broadside or a crossing one)
	if (Actor->IsA<AAirshipCannonball>())
	{
		return true;
	}

	// Team match: the firing ship's teammates (players, their ship, its turrets), from SourceTeamId (a free ship's ball
	// carries its shooter's team, InitCannonball); a team-less ball and the match off: nobody (UMyTeamLibrary resolves a
	// ball to its SourceTeamId)
	return UMyTeamLibrary::IsFriendlyFireBlocked(this, Actor);
}

void AAirshipCannonball::OnProjectileStop(const FHitResult& ImpactResult)
{
	if (!HasAuthority())
	{
		// Clients: wait for the server's impact (or the actor's removal), hidden. Collision off as Explode does on the
		// server: the ball blocks Visibility, and a hidden one left on a target would catch this machine's crosshair
		// sweep and turret tracers there.
		SetActorEnableCollision(false);
		SetActorHiddenInGame(true);
		return;
	}

	Explode(ImpactResult.ImpactPoint, ImpactResult.ImpactNormal, ImpactResult.GetActor());
}

void AAirshipCannonball::OnSphereOverlap(UPrimitiveComponent* OverlappedComponent, AActor* OtherActor, UPrimitiveComponent* OtherComp, int32 OtherBodyIndex, bool bFromSweep, const FHitResult& SweepResult)
{
	if (!HasAuthority() || bExploded || ShouldIgnore(OtherActor))
	{
		return;
	}

	// Only GAS actors stop the ball this way (characters, the Burrower); the rest blocks it
	if (!UAbilitySystemGlobals::GetAbilitySystemComponentFromActor(OtherActor))
	{
		return;
	}

	const FVector Location = bFromSweep ? FVector(SweepResult.ImpactPoint) : GetActorLocation();
	const FVector Normal = bFromSweep ? FVector(SweepResult.ImpactNormal) : -GetVelocity().GetSafeNormal();
	Explode(Location, Normal, OtherActor);
}

void AAirshipCannonball::Explode(const FVector& Location, const FVector& Normal, AActor* DirectHit)
{
	if (bExploded)
	{
		return;
	}

	bExploded = true;

	if (DirectHit && !ShouldIgnore(DirectHit))
	{
		ApplyDamageTo(DirectHit, Damage);
	}
	else
	{
		DirectHit = nullptr;
	}

	// Splash: every other GAS actor in the radius, once
	if (SplashRadius > 0.f && GetWorld())
	{
		TArray<FOverlapResult> Overlaps;
		FCollisionObjectQueryParams Objects;
		Objects.AddObjectTypesToQuery(ECC_Pawn);
		Objects.AddObjectTypesToQuery(ECC_PhysicsBody);
		Objects.AddObjectTypesToQuery(ECC_WorldDynamic);
		FCollisionQueryParams Params(SCENE_QUERY_STAT(AirshipCannonballSplash), false, this);

		GetWorld()->OverlapMultiByObjectType(Overlaps, Location, FQuat::Identity, Objects, FCollisionShape::MakeSphere(SplashRadius), Params);

		TSet<AActor*> Done;

		if (DirectHit)
		{
			Done.Add(DirectHit);
		}

		for (const FOverlapResult& Overlap : Overlaps)
		{
			AActor* Actor = Overlap.GetActor();

			if (!Actor || Done.Contains(Actor) || ShouldIgnore(Actor) || !UAbilitySystemGlobals::GetAbilitySystemComponentFromActor(Actor))
			{
				continue;
			}

			Done.Add(Actor);

			const float Distance = static_cast<float>(FVector::Dist(Location, Actor->GetActorLocation()));
			const float Alpha = FMath::Clamp(Distance / SplashRadius, 0.f, 1.f);
			ApplyDamageTo(Actor, Damage * FMath::Lerp(1.f, SplashMinFraction, Alpha));
		}
	}

	// The last bit of the flight, then the blast (sentinels already hit by this ball are skipped)
	if (bDamageSentinels)
	{
		if (bHasLastSweepLocation)
		{
			QueueSentinelSweep(LastSweepLocation, Location, SentinelHitRadius, false);
		}

		if (SplashRadius > 0.f)
		{
			QueueSentinelSweep(Location, Location, SplashRadius, true);
		}
	}

	MulticastImpact(Location, Normal);

	// Hidden until removed, so the impact multicast still reaches everyone
	if (Movement)
	{
		Movement->StopMovementImmediately();
	}
	SetActorEnableCollision(false);
	SetActorHiddenInGame(true);
	SetLifeSpan(ImpactDestroyDelay);
}

void AAirshipCannonball::ApplyDamageTo(AActor* Target, float InDamage) const
{
	UAbilitySystemComponent* TargetASC = UAbilitySystemGlobals::GetAbilitySystemComponentFromActor(Target);

	if (!TargetASC || !DamageSpec.IsValid() || InDamage <= 0.f)
	{
		return;
	}

	// The ship is gone (destroyed, its player left): an effect with an execution (UExecCalc_Damage) reads the source
	// ASC without a check, so only the built-in kind (plain modifier) still deals its damage
	const UGameplayEffect* Effect = DamageSpec.Data->Def;
	if (!DamageSpec.Data->GetContext().GetInstigatorAbilitySystemComponent() && (!Effect || Effect->Executions.Num() > 0))
	{
		return;
	}

	// The target's own death check (IsDead) is UMyAttributeSet's business; dead targets just keep Health 0
	FGameplayEffectSpec Spec(*DamageSpec.Data.Get());
	Spec.SetSetByCallerMagnitude(MyTags::SetDamageByCaller, InDamage);
	TargetASC->ApplyGameplayEffectSpecToSelf(Spec);
}

void AAirshipCannonball::QueueSentinelSweep(const FVector& Start, const FVector& End, float SweepRadius, bool bSplash) const
{
	UWorld* World = GetWorld();

	if (!World || Damage <= 0.f || SweepRadius <= 0.f || !SentinelsHit.IsValid())
	{
		return;
	}

	// The ship's ASC is the source (its AttackDamage counts); a ball whose ship is gone deals flat damage
	TWeakObjectPtr<AActor> SweepInstigator = SourceShip ? static_cast<AActor*>(SourceShip.Get()) : const_cast<AAirshipCannonball*>(this);
	TWeakObjectPtr<UWorld> WeakWorld = World;
	const TSharedPtr<TSet<uint64>> AlreadyHit = SentinelsHit;
	const float SweepDamage = Damage;
	const float MinFraction = SplashMinFraction;

	// The library must run outside the Mass phases
	World->GetTimerManager().SetTimerForNextTick([WeakWorld, SweepInstigator, AlreadyHit, Start, End, SweepRadius, SweepDamage, MinFraction, bSplash]()
	{
		UWorld* TimerWorld = WeakWorld.Get();
		UMechSentinelSwarmSubsystem* Swarm = TimerWorld ? UMechSentinelSwarmSubsystem::Get(TimerWorld) : nullptr;

		if (!Swarm || !Swarm->HasAuthority())
		{
			return;
		}

		TArray<FMechSentinelHit> Hits;

		if (UMechSentinelCombatLibrary::SweepSentinels(TimerWorld, Start, End, SweepRadius, Hits) == 0)
		{
			return;
		}

		// Each sentinel once per ball: consecutive segments overlap, and the blast covers the last one
		auto Key = [](const FMechSentinelHandle& Handle)
		{
			return (static_cast<uint64>(static_cast<uint32>(Handle.SerialNumber)) << 32) | static_cast<uint32>(Handle.Index);
		};

		Hits.RemoveAll([&AlreadyHit, &Key](const FMechSentinelHit& Hit)
		{
			return AlreadyHit->Contains(Key(Hit.Sentinel));
		});

		if (Hits.IsEmpty())
		{
			return;
		}

		const FGameplayEffectSpecHandle Spec = UMechSentinelCombatLibrary::MakeSentinelDamageSpec(TimerWorld, SweepInstigator.Get(), SweepDamage, nullptr);

		if (!Spec.IsValid())
		{
			return;
		}

		for (const FMechSentinelHit& Hit : Hits)
		{
			AlreadyHit->Add(Key(Hit.Sentinel));

			if (!bSplash)
			{
				Swarm->ApplyGameplayEffectSpecToSentinel(Hit.Sentinel.ToEntity(), *Spec.Data.Get(), &Hit.ImpactPoint);
				continue;
			}

			// Blast: the same falloff as the GAS splash
			const float Alpha = FMath::Clamp(static_cast<float>(FVector::Dist(Start, Hit.ImpactPoint)) / SweepRadius, 0.f, 1.f);
			FGameplayEffectSpec SplashSpec(*Spec.Data.Get());
			SplashSpec.SetSetByCallerMagnitude(MyTags::SetDamageByCaller, SweepDamage * FMath::Lerp(1.f, MinFraction, Alpha));
			Swarm->ApplyGameplayEffectSpecToSentinel(Hit.Sentinel.ToEntity(), SplashSpec, &Hit.ImpactPoint);
		}
	});
}

void AAirshipCannonball::MulticastImpact_Implementation(FVector_NetQuantize Location, FVector_NetQuantizeNormal Normal)
{
	// Spent on every machine: no Visibility block left where it hit (a client's crosshair sweep would pick the hidden
	// ball, and GA_GunShoot ignores a spent one, so shots at the target would do nothing for ImpactDestroyDelay)
	SetActorEnableCollision(false);
	SetActorHiddenInGame(true);

	if (Movement)
	{
		Movement->StopMovementImmediately();
	}

	// Once per machine: with bSplashWhenShotDown a shot-down ball also explodes, and the replicated shoot-down may arrive first
	if (ImpactFX && GetNetMode() != NM_DedicatedServer && !bImpactFXPlayed)
	{
		bImpactFXPlayed = true;
		UNiagaraFunctionLibrary::SpawnSystemAtLocation(this, ImpactFX, Location, FVector(Normal).Rotation(), FVector(ImpactFXScale));
	}

	BP_OnImpact(Location, Normal);
}

bool AAirshipCannonball::ApplyShotDamage(float DamageUnits, AActor* DamageInstigator)
{
	// Not before BeginPlay (BallHealth is set there); NaN fails the > test
	if (!HasAuthority() || !HasActorBegunPlay() || IsSpent() || BallMaxHealth <= 0.f || !(DamageUnits > 0.f))
	{
		return false;
	}

	BallHealth -= DamageUnits;

	if (BallHealth > 0.f)
	{
		UE_LOG(LogAirshipCannonball, Verbose, TEXT("%s hit by %s: %.1f of %.1f left"), *GetName(), *GetNameSafe(DamageInstigator), BallHealth, BallMaxHealth);
		return false;
	}

	BallHealth = 0.f;
	bShotDown = true;
	ShotDownLocation = GetActorLocation();

	UE_LOG(LogAirshipCannonball, Verbose, TEXT("%s shot down by %s at %s"), *GetName(), *GetNameSafe(DamageInstigator), *ShotDownLocation.ToCompactString());

	if (bSplashWhenShotDown)
	{
		// Explodes like an impact (damage, splash, sentinels, MulticastImpact); bShotDown still stops every client's copy
		Explode(ShotDownLocation, -GetVelocity().GetSafeNormal(), nullptr);
		PlayShotDownFX();
		EnterShotDownState();
	}
	else
	{
		// Defused: Explode never runs (no damage, no splash, no sentinel sweep)
		bExploded = true;
		PlayShotDownFX();
		EnterShotDownState();
		SetLifeSpan(ImpactDestroyDelay);
	}

	// The state is what clients act on: send it now, not at the next net update
	ForceNetUpdate();
	return true;
}

void AAirshipCannonball::OnRep_ShotDown()
{
	if (!bShotDown)
	{
		return;
	}

	// The client's copy flew on its own: burst it where the server's ball was, then stop it there
	SetActorEnableCollision(false);
	SetActorLocation(ShotDownLocation, false, nullptr, ETeleportType::TeleportPhysics);
	PlayShotDownFX();
	EnterShotDownState();
}

void AAirshipCannonball::EnterShotDownState()
{
	SetActorEnableCollision(false);
	SetActorHiddenInGame(true);

	if (Movement)
	{
		Movement->StopMovementImmediately();
		// The projectile adds gravity every tick: without this the hidden ball would fall on until it is removed
		Movement->SetComponentTickEnabled(false);
	}
}

void AAirshipCannonball::PlayShotDownFX()
{
	if (GetNetMode() == NM_DedicatedServer)
	{
		return;
	}

	if (ImpactFX && !bImpactFXPlayed)
	{
		bImpactFXPlayed = true;

		// Faces back along the flight, like the normal of a wall hit (a copy that already stopped uses its launch direction)
		FVector Back = Movement ? -Movement->Velocity.GetSafeNormal() : FVector::ZeroVector;

		if (Back.IsNearlyZero())
		{
			Back = -FVector(LaunchVelocity).GetSafeNormal();
		}

		const FRotator Rotation = Back.IsNearlyZero() ? FRotator::ZeroRotator : Back.Rotation();
		UNiagaraFunctionLibrary::SpawnSystemAtLocation(this, ImpactFX, ShotDownLocation, Rotation, FVector(ImpactFXScale));
	}

	BP_OnShotDown(ShotDownLocation);
}

AAirshipCannonball* AAirshipCannonball::SpawnTestCannonball(UObject* WorldContextObject, TSubclassOf<AAirshipCannonball> BallClass,
	FVector Location, FVector Velocity, AAirshipPawn* SourceShip, float InDamage, float GravityScaleOverride)
{
	UWorld* World = GEngine ? GEngine->GetWorldFromContextObject(WorldContextObject, EGetWorldErrorMode::LogAndReturnNull) : nullptr;

	if (!World || World->GetNetMode() == NM_Client)
	{
		UE_LOG(LogAirshipCannonball, Warning, TEXT("SpawnTestCannonball: needs a server world (listen server or standalone)"));
		return nullptr;
	}

	UClass* Class = BallClass ? BallClass.Get() : AAirshipCannonball::StaticClass();

	// The damage path of FireCannons (ship ASC, SetByCaller); the ship's own DamageEffectClass is not public, so the
	// built-in effect stands in. No ship: no spec and no damage at all (sentinels included)
	FGameplayEffectSpecHandle Spec;
	float SpecDamage = 0.f;
	UAbilitySystemComponent* ShipASC = SourceShip ? SourceShip->GetAbilitySystemComponent() : nullptr;

	if (ShipASC && InDamage > 0.f)
	{
		FGameplayEffectContextHandle Context = ShipASC->MakeEffectContext();
		Context.AddInstigator(SourceShip, SourceShip);
		Context.AddSourceObject(SourceShip);
		const float Level = static_cast<float>(IMyCombatInterface::Execute_GetLevel(SourceShip));
		Spec = ShipASC->MakeOutgoingSpec(TSubclassOf<UGameplayEffect>(UAirshipDamageEffect::StaticClass()), Level, Context);

		if (Spec.IsValid())
		{
			Spec.Data->SetSetByCallerMagnitude(MyTags::SetDamageByCaller, InDamage);
			SpecDamage = InDamage;
		}
	}

	const FTransform SpawnTM(Velocity.IsNearlyZero() ? FRotator::ZeroRotator : Velocity.Rotation(), Location);
	AAirshipCannonball* Ball = World->SpawnActorDeferred<AAirshipCannonball>(Class, SpawnTM, SourceShip, SourceShip, ESpawnActorCollisionHandlingMethod::AlwaysSpawn);

	if (!Ball)
	{
		return nullptr;
	}

	Ball->InitCannonball(SourceShip, Velocity, Spec, SpecDamage);

	if (GravityScaleOverride >= 0.f)
	{
		Ball->GravityScale = GravityScaleOverride;
	}

	Ball->FinishSpawning(SpawnTM);

	UE_LOG(LogAirshipCannonball, Log, TEXT("SpawnTestCannonball: %s at %s, velocity %s, gravity %.2f, ship %s, damage %.1f"),
		*Ball->GetName(), *Location.ToCompactString(), *Velocity.ToCompactString(), Ball->GravityScale, *GetNameSafe(SourceShip), SpecDamage);
	return Ball;
}
