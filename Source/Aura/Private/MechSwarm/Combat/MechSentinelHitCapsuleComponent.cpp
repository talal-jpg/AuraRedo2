// Mech Sentinel Swarm - drop-in capsule that lets any actor hit sentinels.

#include "MechSwarm/Combat/MechSentinelHitCapsuleComponent.h"

#include "Engine/CollisionProfile.h"
#include "GameFramework/Actor.h"
#include "GameFramework/Pawn.h"
#include "GameplayEffect.h"
#include "MechSwarm/Combat/MechSentinelCombatLibrary.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(MechSentinelHitCapsuleComponent)

UMechSentinelHitCapsuleComponent::UMechSentinelHitCapsuleComponent()
{
	PrimaryComponentTick.bCanEverTick = true;
	PrimaryComponentTick.bStartWithTickEnabled = true;
	// After the owner moved this frame (projectile movement runs before), and outside the Mass phases: a hit writes
	// sentinel fragments and can change their tags, which must not happen while Mass processors run on worker tasks
	// (TG_PrePhysics..TG_PostPhysics, and TG_LastDemotable).
	PrimaryComponentTick.TickGroup = TG_PostUpdateWork;

	// Sentinels are Mass entities, not physics bodies: no engine collision needed.
	SetCollisionProfileName(UCollisionProfile::NoCollision_ProfileName);
	SetGenerateOverlapEvents(false);
	SetCanEverAffectNavigation(false);
	InitCapsuleSize(20.f, 20.f);
}

void UMechSentinelHitCapsuleComponent::BeginPlay()
{
	// Also for components saved with another group: see the constructor.
	SetTickGroup(TG_PostUpdateWork);

	Super::BeginPlay();

	// Only the server resolves hits; clients see the result through replication.
	const AActor* Owner = GetOwner();
	if (!Owner || !Owner->HasAuthority())
	{
		SetComponentTickEnabled(false);
	}

	LastLocation = GetComponentLocation();
	bHasLastLocation = true;
}

AActor* UMechSentinelHitCapsuleComponent::GetDamageInstigator() const
{
	AActor* Owner = GetOwner();
	if (!Owner)
	{
		return nullptr;
	}
	// Projectiles: the pawn that fired them (its ASC becomes the effect source).
	if (APawn* InstigatorPawn = Owner->GetInstigator())
	{
		return InstigatorPawn;
	}
	return Owner->GetOwner() ? Owner->GetOwner() : Owner;
}

void UMechSentinelHitCapsuleComponent::ResetHitSentinels()
{
	HitSentinels.Reset();
	TotalHits = 0;
}

void UMechSentinelHitCapsuleComponent::SetHitsEnabled(const bool bEnabled)
{
	bHitsEnabled = bEnabled;
	// Do not sweep across the gap when re-enabled.
	LastLocation = GetComponentLocation();
	bHasLastLocation = true;
}

void UMechSentinelHitCapsuleComponent::TickComponent(const float DeltaTime, const ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);

	if (bHitEveryTick)
	{
		ApplyHitsNow();
	}
	LastLocation = GetComponentLocation();
	bHasLastLocation = true;
}

int32 UMechSentinelHitCapsuleComponent::ApplyHitsNow()
{
	AActor* Owner = GetOwner();
	if (!bHitsEnabled || !Owner || !Owner->HasAuthority() || (MaxSentinelsHit > 0 && TotalHits >= MaxSentinelsHit))
	{
		return 0;
	}

	UMechSentinelSwarmSubsystem* Swarm = UMechSentinelSwarmSubsystem::Get(this);
	if (!Swarm)
	{
		return 0;
	}

	const float Radius = GetScaledCapsuleRadius();
	const float HalfHeight = GetScaledCapsuleHalfHeight();
	const FVector Center = GetComponentLocation();

	// Overlap of the capsule itself...
	TArray<FMechSentinelHit> Hits;
	UMechSentinelCombatLibrary::FindSentinelsInCapsule(this, Center, GetComponentRotation(), Radius, HalfHeight, Hits);

	// ...plus the path travelled since last frame.
	if (bSweepFromLastPosition && bHasLastLocation && !LastLocation.Equals(Center, 1.f))
	{
		TArray<FMechSentinelHit> SweepHits;
		Swarm->QueryCapsule(LastLocation, Center, Radius, SweepHits);
		for (const FMechSentinelHit& SweepHit : SweepHits)
		{
			if (!Hits.ContainsByPredicate([&SweepHit](const FMechSentinelHit& Existing) { return Existing.Sentinel == SweepHit.Sentinel; }))
			{
				Hits.Add(SweepHit);
			}
		}
		// Closest to where the projectile came from first.
		Hits.Sort([this](const FMechSentinelHit& A, const FMechSentinelHit& B)
		{
			return FVector::DistSquared(A.ImpactPoint, LastLocation) < FVector::DistSquared(B.ImpactPoint, LastLocation);
		});
	}

	Hits.RemoveAll([this](const FMechSentinelHit& Hit) { return HitSentinels.Contains(Hit.Sentinel); });
	if (Hits.IsEmpty())
	{
		return 0;
	}

	AActor* DamageInstigator = GetDamageInstigator();
	const FGameplayEffectSpecHandle DamageSpec = UMechSentinelCombatLibrary::MakeSentinelDamageSpec(this, DamageInstigator, Damage, DamageEffect);

	TArray<FGameplayEffectSpecHandle> ExtraSpecs;
	for (const TSubclassOf<UGameplayEffect>& Extra : ExtraEffects)
	{
		if (Extra)
		{
			const FGameplayEffectSpecHandle ExtraSpec = UMechSentinelCombatLibrary::MakeSentinelDamageSpec(this, DamageInstigator, 0.f, Extra);
			if (ExtraSpec.IsValid())
			{
				ExtraSpecs.Add(ExtraSpec);
			}
		}
	}

	int32 NewHits = 0;
	for (const FMechSentinelHit& Hit : Hits)
	{
		if (MaxSentinelsHit > 0 && TotalHits >= MaxSentinelsHit)
		{
			break;
		}
		if (!UMechSentinelCombatLibrary::IsSentinelAlive(this, Hit.Sentinel))
		{
			continue;
		}

		const FMassEntityHandle Entity = Hit.Sentinel.ToEntity();
		float Dealt = 0.f;
		if (DamageSpec.IsValid())
		{
			Dealt = Swarm->ApplyGameplayEffectSpecToSentinel(Entity, *DamageSpec.Data.Get(), &Hit.ImpactPoint);
		}
		for (const FGameplayEffectSpecHandle& ExtraSpec : ExtraSpecs)
		{
			Swarm->ApplyGameplayEffectSpecToSentinel(Entity, *ExtraSpec.Data.Get(), &Hit.ImpactPoint);
		}

		HitSentinels.Add(Hit.Sentinel);
		++TotalHits;
		++NewHits;
		OnSentinelHit.Broadcast(Hit.Sentinel, Hit.ImpactPoint, Dealt);
	}

	if (NewHits > 0 && bDestroyOwnerWhenSpent && MaxSentinelsHit > 0 && TotalHits >= MaxSentinelsHit && IsValid(Owner))
	{
		Owner->Destroy();
	}
	return NewHits;
}
