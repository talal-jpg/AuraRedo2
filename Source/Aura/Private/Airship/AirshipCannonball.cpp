// Fill out your copyright notice in the Description page of Project Settings.


#include "Airship/AirshipCannonball.h"

#include "AbilitySystemComponent.h"
#include "AbilitySystemGlobals.h"
#include "AbilitySystem/Data/MyGameplayTags.h"
#include "Airship/AirshipPawn.h"
#include "Components/SphereComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/OverlapResult.h"
#include "Engine/World.h"
#include "GameFramework/ProjectileMovementComponent.h"
#include "GameplayEffect.h"
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
	CollisionSphere->SetCollisionResponseToChannel(ECC_Visibility, ECR_Ignore);
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
	DOREPLIFETIME_CONDITION(AAirshipCannonball, LaunchVelocity, COND_InitialOnly);
}

void AAirshipCannonball::InitCannonball(AAirshipPawn* InShip, const FVector& InVelocity, const FGameplayEffectSpecHandle& InDamageSpec, float InDamage)
{
	SourceShip = InShip;
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

	// Another ball (same broadside or a crossing one)
	return Actor->IsA<AAirshipCannonball>();
}

void AAirshipCannonball::OnProjectileStop(const FHitResult& ImpactResult)
{
	if (!HasAuthority())
	{
		// Clients: wait for the server's impact (or the actor's removal), hidden
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
	SetActorHiddenInGame(true);

	if (Movement)
	{
		Movement->StopMovementImmediately();
	}

	if (ImpactFX && GetNetMode() != NM_DedicatedServer)
	{
		UNiagaraFunctionLibrary::SpawnSystemAtLocation(this, ImpactFX, Location, FVector(Normal).Rotation(), FVector(ImpactFXScale));
	}

	BP_OnImpact(Location, Normal);
}
