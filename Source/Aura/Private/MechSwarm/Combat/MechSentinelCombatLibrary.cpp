// Mech Sentinel Swarm - hit functions.

#include "MechSwarm/Combat/MechSentinelCombatLibrary.h"

#include "AbilitySystemComponent.h"
#include "AbilitySystemGlobals.h"
#include "AbilitySystem/Data/MyGameplayTags.h"
#include "CollisionQueryParams.h"
#include "Components/PrimitiveComponent.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "GameFramework/Pawn.h"
#include "GameplayEffect.h"
#include "MassEntityManager.h"
#include "MassEntityView.h"
#include "Mass/EntityFragments.h"
#include "MechSwarm/Core/MechSentinelSwarmRules.h"
#include "MechSwarm/Sentinel/MechSentinelFragments.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(MechSentinelCombatLibrary)

DEFINE_LOG_CATEGORY_STATIC(LogMechSentinelCombat, Log, All);

namespace MechSwarm::CombatLibraryPrivate
{
	bool IsAlive(const UMechSentinelSwarmSubsystem& Swarm, const FMassEntityHandle Entity)
	{
		const FMassEntityManager* EntityManager = Swarm.GetEntityManager();
		if (!EntityManager || !EntityManager->IsEntityActive(Entity))
		{
			return false;
		}
		const FMechSentinelStateFragment* State = EntityManager->GetFragmentDataPtr<FMechSentinelStateFragment>(Entity);
		return State && State->State != EMechSentinelState::Dead;
	}

	UMechSentinelSwarmSubsystem* GetAuthoritySwarm(const UObject* WorldContextObject)
	{
		UMechSentinelSwarmSubsystem* Swarm = UMechSentinelSwarmSubsystem::Get(WorldContextObject);
		return (Swarm && Swarm->HasAuthority()) ? Swarm : nullptr;
	}
}

namespace MechSwarm::AimShotPrivate
{
	/**
	 * The aim comes from the client's target data, so the server bounds it. Farthest the aim trace may start from the
	 * shooter (cm), a sanity bound on the camera position.
	 */
	constexpr double MaxAimOriginDistance = 5000.0;

	/**
	 * Farthest the shot's line may pass from the shooter (cm), plus how far the shooter moves in MoveSlackSeconds. A
	 * crosshair ray passes the character within the camera's offset (arm height, socket offset, camera lag), and the
	 * server's character trails the client's. Beyond that (a modified client, or a broken trace) the shot follows the
	 * pawn's own view instead.
	 */
	constexpr double MaxShotLineOffset = 300.0;
	constexpr double MoveSlackSeconds = 0.25;

	/** Characters (and debris pieces) in a row the wall trace looks past; the next one counts as a wall. */
	constexpr int32 MaxCharactersSkipped = 8;

	/** The point of the line closest to Location, but never behind Origin. */
	FVector StartOnLine(const FVector& Origin, const FVector& Direction, const FVector& Location)
	{
		return Origin + Direction * FMath::Max(0.0, FVector::DotProduct(Location - Origin, Direction));
	}

	/**
	 * The pawn that Actor is, or is attached to (a character's weapon, for example). Every pawn is looked past, the
	 * airship's hull too: a moving ship sits elsewhere on the shooting client (its passengers aim and are aimed at on
	 * that lagged copy), so its server position is no wall.
	 */
	const APawn* GetCharacterOf(const AActor* Actor)
	{
		for (; Actor; Actor = Actor->GetAttachParentActor())
		{
			if (const APawn* Pawn = Cast<APawn>(Actor))
			{
				return Pawn;
			}
		}
		return nullptr;
	}

	/** Physics debris each machine simulates on its own (not replicated, e.g. a collapsing hex bridge's pieces): it lies elsewhere on every machine. */
	bool IsLocalDebris(const FHitResult& Hit)
	{
		const UPrimitiveComponent* Component = Hit.GetComponent();
		const AActor* Actor = Hit.GetActor();
		return Component && Actor && Component->IsSimulatingPhysics() && !Actor->GetIsReplicated();
	}

	/**
	 * The first wall from From to To: the first blocking hit on the crosshair trace's channel that is not part of a
	 * pawn, nor local debris. Pawns (their components and attached actors, whatever their collision profiles) are
	 * looked past, because their positions on the server differ from what the shooting client saw. A character
	 * stops the shot only when it is the client's own crosshair hit (see GetAimShotSegment). What is looked past is
	 * added to Params.
	 */
	bool TraceWall(const UWorld& World, const FVector& From, const FVector& To, FCollisionQueryParams& Params,
		const FCollisionResponseParams& Responses, FHitResult& OutWall)
	{
		for (int32 Skipped = 0; ; ++Skipped)
		{
			if (!World.LineTraceSingleByChannel(OutWall, From, To, ECC_Visibility, Params, Responses))
			{
				return false;
			}
			const APawn* Character = GetCharacterOf(OutWall.GetActor());
			if ((!Character && !IsLocalDebris(OutWall)) || Skipped >= MaxCharactersSkipped)
			{
				return true;
			}
			if (Character)
			{
				TArray<AActor*> Attached;
				Character->GetAttachedActors(Attached, /*bResetArray*/ true, /*bRecursivelyIncludeAttachedActors*/ true);
				Params.AddIgnoredActor(Character);
				Params.AddIgnoredActors(Attached);
			}
			Params.AddIgnoredActor(OutWall.GetActor());
		}
	}

	/**
	 * The query of the server's wall traces: the crosshair trace's channel with complex collision, without Avatar and
	 * its attachments. The Pawn object type is skipped here, and TraceWall looks past the rest of every character.
	 */
	void MakeWallQuery(const AActor& Avatar, FCollisionQueryParams& OutParams, FCollisionResponseParams& OutResponses)
	{
		OutParams = FCollisionQueryParams(SCENE_QUERY_STAT(AimShotWalls), /*bTraceComplex*/ true, &Avatar);
		TArray<AActor*> Attached;
		Avatar.GetAttachedActors(Attached, /*bResetArray*/ true, /*bRecursivelyIncludeAttachedActors*/ true);
		OutParams.AddIgnoredActors(Attached);
		OutResponses = FCollisionResponseParams();
		OutResponses.CollisionResponse.SetResponse(ECC_Pawn, ECR_Ignore);
	}
}

//----------------------------------------------------------------------//
// Helpers
//----------------------------------------------------------------------//
void UMechSentinelCombatLibrary::GetCapsuleSegment(const FVector& Center, const FRotator& Rotation, const float Radius, const float HalfHeight, FVector& OutA, FVector& OutB)
{
	const FVector Up = Rotation.Quaternion().GetUpVector();
	const float HalfSegment = FMath::Max(0.f, HalfHeight - Radius);
	OutA = Center - Up * HalfSegment;
	OutB = Center + Up * HalfSegment;
}

bool UMechSentinelCombatLibrary::GetAimShotSegment(const FHitResult& AimHit, const AActor& Avatar, const double MaxRange, FVector& OutStart, FVector& OutEnd)
{
	using namespace MechSwarm::AimShotPrivate;
	const UWorld* World = Avatar.GetWorld();
	if (!World)
	{
		return false;
	}
	const FVector AvatarLocation = Avatar.GetActorLocation();

	// The server traces the walls itself, whatever the client reports (see MakeWallQuery).
	FCollisionQueryParams Params;
	FCollisionResponseParams Responses;
	MakeWallQuery(Avatar, Params, Responses);
	FHitResult Wall;

	// The shot starts at the point of its line nearest the shooter, so nothing between the camera and the character is
	// hit. No wall may lie between the shooter's capsule centre (which movement keeps out of walls) and that point.
	const auto IsStartInTheOpen = [&]()
	{
		return FVector::DistSquared(AvatarLocation, OutStart) <= 1.0
			|| !TraceWall(*World, AvatarLocation, OutStart, Params, Responses, Wall);
	};

	// Along the aim trace: from the camera through the crosshair. The direction comes from the trace's own end, which is
	// right even when the sweep started inside something (its hit is then at its start). MyPlayerController2's trace ends
	// FLT_MAX away, so the vector is scaled into a sane range before it is normalized.
	FVector Origin = AimHit.TraceStart;
	FVector Direction = FVector(AimHit.TraceEnd) - Origin;
	const double Largest = Direction.GetAbsMax();
	Direction = (!Direction.ContainsNaN() && FMath::IsFinite(Largest) && Largest > UE_KINDA_SMALL_NUMBER)
		? (Direction / Largest).GetSafeNormal()
		: FVector::ZeroVector;

	// The client sends the aim. It is used when the camera is near the shooter, its line passes close to the shooter,
	// and the shot's start is in the open.
	bool bUseAimTrace = !Origin.ContainsNaN() && !Direction.IsNearlyZero()
		&& FVector::DistSquared(Origin, AvatarLocation) <= FMath::Square(MaxAimOriginDistance);
	if (bUseAimTrace)
	{
		OutStart = StartOnLine(Origin, Direction, AvatarLocation);
		const double MaxOffset = MaxShotLineOffset + GetMoveVelocityAt(Avatar, AvatarLocation).Size() * MoveSlackSeconds;
		bUseAimTrace = FVector::DistSquared(OutStart, AvatarLocation) <= FMath::Square(MaxOffset) && IsStartInTheOpen();
	}
	if (!bUseAimTrace)
	{
		// No usable aim trace: shoot where the pawn looks.
		const APawn* Pawn = Cast<APawn>(&Avatar);
		if (!Pawn)
		{
			return false;
		}
		Origin = Pawn->GetPawnViewLocation();
		Direction = Pawn->GetBaseAimRotation().Vector();
		OutStart = StartOnLine(Origin, Direction, AvatarLocation);
		if (!IsStartInTheOpen())
		{
			return false;
		}
	}

	// The crosshair trace's first hit stops the shot, when it lies ahead of the shooter: the only stop at characters.
	double Range = MaxRange;
	if (bUseAimTrace && AimHit.bBlockingHit)
	{
		const double BlockAlongShot = FVector::DotProduct(FVector(AimHit.Location) - OutStart, Direction);
		if (BlockAlongShot > 0.0)
		{
			Range = FMath::Min(Range, BlockAlongShot);
		}
	}

	// Walls stop it at the first one the server finds.
	if (TraceWall(*World, OutStart, OutStart + Direction * Range, Params, Responses, Wall))
	{
		Range = Wall.bStartPenetrating ? 0.0 : FMath::Min(Range, double(Wall.Distance));
	}
	if (Range <= UE_KINDA_SMALL_NUMBER)
	{
		// The line starts in a wall.
		return false;
	}
	OutEnd = OutStart + Direction * Range;
	return true;
}

bool UMechSentinelCombatLibrary::IsAimPathClear(const AActor& Avatar, const FVector& From, const FVector& To, TConstArrayView<const AActor*> IgnoreActors)
{
	using namespace MechSwarm::AimShotPrivate;
	const UWorld* World = Avatar.GetWorld();
	if (!World)
	{
		return false;
	}
	if (FVector::DistSquared(From, To) <= 1.0)
	{
		return true;
	}
	FCollisionQueryParams Params;
	FCollisionResponseParams Responses;
	MakeWallQuery(Avatar, Params, Responses);
	TArray<AActor*> Attached;
	for (const AActor* Ignored : IgnoreActors)
	{
		if (Ignored)
		{
			Ignored->GetAttachedActors(Attached, /*bResetArray*/ true, /*bRecursivelyIncludeAttachedActors*/ true);
			Params.AddIgnoredActor(Ignored);
			Params.AddIgnoredActors(Attached);
		}
	}
	FHitResult Wall;
	return !TraceWall(*World, From, To, Params, Responses, Wall);
}

FVector UMechSentinelCombatLibrary::GetMoveVelocityAt(const AActor& Actor, const FVector& Point)
{
	// A simulating body (the airship's hull): its velocity at the point, its rotation included.
	UPrimitiveComponent* Root = Cast<UPrimitiveComponent>(Actor.GetRootComponent());
	if (Root && Root->IsSimulatingPhysics())
	{
		return Root->GetPhysicsLinearVelocityAtPoint(Point);
	}
	// A character's movement velocity leaves out the base it stands on (an airship's deck, a moving platform).
	FVector Velocity = Actor.GetVelocity();
	if (const ACharacter* Character = Cast<ACharacter>(&Actor))
	{
		if (UPrimitiveComponent* Base = Cast<UPrimitiveComponent>(Character->GetMovementBaseObject()))
		{
			// The base's own body, or the simulating body it rides on: an airship's deck is its skeletal mesh's kinematic
			// boxes, attached to the simulating hull, and such a component has no velocity of its own.
			const UPrimitiveComponent* Mover = nullptr;
			for (USceneComponent* Link = Base; Link && !Mover; Link = Link->GetAttachParent())
			{
				const UPrimitiveComponent* Primitive = Cast<UPrimitiveComponent>(Link);
				if (Primitive && Primitive->IsSimulatingPhysics())
				{
					Mover = Primitive;
				}
			}
			Velocity += Mover ? Mover->GetPhysicsLinearVelocityAtPoint(Point) : Base->GetComponentVelocity();
		}
	}
	return Velocity;
}

FGameplayEffectSpecHandle UMechSentinelCombatLibrary::MakeSentinelDamageSpec(const UObject* WorldContextObject, AActor* Instigator, const float Damage, TSubclassOf<UGameplayEffect> Effect, const float Level)
{
	UMechSentinelSwarmSubsystem* Swarm = MechSwarm::CombatLibraryPrivate::GetAuthoritySwarm(WorldContextObject);
	if (!Swarm)
	{
		return FGameplayEffectSpecHandle();
	}

	const TSubclassOf<UGameplayEffect> EffectClass = Effect ? Effect : Swarm->GetRules()->DefaultSentinelDamageEffect;
	if (!EffectClass)
	{
		UE_LOG(LogMechSentinelCombat, Warning, TEXT("No damage effect: pass one or set DefaultSentinelDamageEffect in the GameMode's Sentinel Swarm Rules."));
		return FGameplayEffectSpecHandle();
	}

	// The instigator's ASC is the source when it has one (its tags / attributes can take part in the calculation).
	UAbilitySystemComponent* SourceASC = UAbilitySystemGlobals::GetAbilitySystemComponentFromActor(Instigator);
	FGameplayEffectContextHandle Context;
	if (SourceASC)
	{
		Context = SourceASC->MakeEffectContext();
	}
	else
	{
		SourceASC = Swarm->GetSentinelSourceASC();
		if (!SourceASC)
		{
			return FGameplayEffectSpecHandle();
		}
		Context = SourceASC->MakeEffectContext();
		Context.AddInstigator(Instigator, Instigator);
	}

	FGameplayEffectSpecHandle SpecHandle = SourceASC->MakeOutgoingSpec(EffectClass, Level, Context);
	if (SpecHandle.IsValid())
	{
		SpecHandle.Data->SetSetByCallerMagnitude(MyTags::SetDamageByCaller, Damage);
	}
	return SpecHandle;
}

int32 UMechSentinelCombatLibrary::ApplySpecToHits(UMechSentinelSwarmSubsystem& Swarm, const FGameplayEffectSpec& Spec, TArray<FMechSentinelHit>& InOutHits, const int32 MaxTargets, float* OutTotalDamage)
{
	float TotalDamage = 0.f;
	int32 Applied = 0;

	// Hits are sorted by distance: the closest MaxTargets living sentinels are affected; the rest is dropped from the list.
	for (int32 Index = 0; Index < InOutHits.Num();)
	{
		const FMechSentinelHit& Hit = InOutHits[Index];
		const FMassEntityHandle Entity = Hit.Sentinel.ToEntity();
		if ((MaxTargets > 0 && Applied >= MaxTargets) || !MechSwarm::CombatLibraryPrivate::IsAlive(Swarm, Entity))
		{
			InOutHits.RemoveAt(Index, EAllowShrinking::No);
			continue;
		}

		TotalDamage += Swarm.ApplyGameplayEffectSpecToSentinel(Entity, Spec, &Hit.ImpactPoint);
		++Applied;
		++Index;
	}

	if (OutTotalDamage)
	{
		*OutTotalDamage = TotalDamage;
	}
	return Applied;
}

//----------------------------------------------------------------------//
// Queries
//----------------------------------------------------------------------//
int32 UMechSentinelCombatLibrary::FindSentinelsInCapsule(const UObject* WorldContextObject, const FVector Center, const FRotator Rotation, const float Radius, const float HalfHeight, TArray<FMechSentinelHit>& OutHits)
{
	OutHits.Reset();
	const UMechSentinelSwarmSubsystem* Swarm = UMechSentinelSwarmSubsystem::Get(WorldContextObject);
	if (!Swarm)
	{
		return 0;
	}

	FVector A, B;
	GetCapsuleSegment(Center, Rotation, Radius, HalfHeight, A, B);
	return Swarm->QueryCapsule(A, B, Radius, OutHits);
}

int32 UMechSentinelCombatLibrary::SweepSentinels(const UObject* WorldContextObject, const FVector Start, const FVector End, const float Radius, TArray<FMechSentinelHit>& OutHits)
{
	OutHits.Reset();
	const UMechSentinelSwarmSubsystem* Swarm = UMechSentinelSwarmSubsystem::Get(WorldContextObject);
	return Swarm ? Swarm->QueryCapsule(Start, End, Radius, OutHits) : 0;
}

//----------------------------------------------------------------------//
// Damage / effects
//----------------------------------------------------------------------//
int32 UMechSentinelCombatLibrary::ApplyDamageToSentinelsInCapsule(const UObject* WorldContextObject, AActor* Instigator, const FVector Center, const FRotator Rotation, const float Radius,
	const float HalfHeight, const float Damage, TSubclassOf<UGameplayEffect> DamageEffect, const int32 MaxTargets, TArray<FMechSentinelHit>& OutHits, float& OutTotalDamage)
{
	OutTotalDamage = 0.f;
	OutHits.Reset();

	UMechSentinelSwarmSubsystem* Swarm = MechSwarm::CombatLibraryPrivate::GetAuthoritySwarm(WorldContextObject);
	if (!Swarm || FindSentinelsInCapsule(WorldContextObject, Center, Rotation, Radius, HalfHeight, OutHits) == 0)
	{
		return 0;
	}

	const FGameplayEffectSpecHandle SpecHandle = MakeSentinelDamageSpec(WorldContextObject, Instigator, Damage, DamageEffect);
	if (!SpecHandle.IsValid())
	{
		OutHits.Reset();
		return 0;
	}
	return ApplySpecToHits(*Swarm, *SpecHandle.Data.Get(), OutHits, MaxTargets, &OutTotalDamage);
}

int32 UMechSentinelCombatLibrary::ApplyDamageToSentinelsInSweep(const UObject* WorldContextObject, AActor* Instigator, const FVector Start, const FVector End, const float Radius,
	const float Damage, TSubclassOf<UGameplayEffect> DamageEffect, const int32 MaxTargets, TArray<FMechSentinelHit>& OutHits, float& OutTotalDamage)
{
	OutTotalDamage = 0.f;
	OutHits.Reset();

	UMechSentinelSwarmSubsystem* Swarm = MechSwarm::CombatLibraryPrivate::GetAuthoritySwarm(WorldContextObject);
	if (!Swarm || Swarm->QueryCapsule(Start, End, Radius, OutHits) == 0)
	{
		return 0;
	}

	const FGameplayEffectSpecHandle SpecHandle = MakeSentinelDamageSpec(WorldContextObject, Instigator, Damage, DamageEffect);
	if (!SpecHandle.IsValid())
	{
		OutHits.Reset();
		return 0;
	}
	return ApplySpecToHits(*Swarm, *SpecHandle.Data.Get(), OutHits, MaxTargets, &OutTotalDamage);
}

int32 UMechSentinelCombatLibrary::ApplyEffectToSentinelsInCapsule(const UObject* WorldContextObject, AActor* Instigator, const FVector Center, const FRotator Rotation, const float Radius,
	const float HalfHeight, TSubclassOf<UGameplayEffect> Effect, const float Level, const int32 MaxTargets)
{
	UMechSentinelSwarmSubsystem* Swarm = MechSwarm::CombatLibraryPrivate::GetAuthoritySwarm(WorldContextObject);
	if (!Swarm || !Effect)
	{
		return 0;
	}

	TArray<FMechSentinelHit> Hits;
	if (FindSentinelsInCapsule(WorldContextObject, Center, Rotation, Radius, HalfHeight, Hits) == 0)
	{
		return 0;
	}

	// Damage 0: the effect decides what it does (stun, shield, slow...).
	const FGameplayEffectSpecHandle SpecHandle = MakeSentinelDamageSpec(WorldContextObject, Instigator, 0.f, Effect, Level);
	return SpecHandle.IsValid() ? ApplySpecToHits(*Swarm, *SpecHandle.Data.Get(), Hits, MaxTargets) : 0;
}

float UMechSentinelCombatLibrary::ApplyDamageToSentinel(const UObject* WorldContextObject, AActor* Instigator, const FMechSentinelHandle Sentinel, const float Damage, const FVector HitLocation,
	TSubclassOf<UGameplayEffect> DamageEffect)
{
	UMechSentinelSwarmSubsystem* Swarm = MechSwarm::CombatLibraryPrivate::GetAuthoritySwarm(WorldContextObject);
	if (!Swarm)
	{
		return 0.f;
	}

	const FGameplayEffectSpecHandle SpecHandle = MakeSentinelDamageSpec(WorldContextObject, Instigator, Damage, DamageEffect);
	return SpecHandle.IsValid() ? Swarm->ApplyGameplayEffectSpecToSentinel(Sentinel.ToEntity(), *SpecHandle.Data.Get(), &HitLocation) : 0.f;
}

float UMechSentinelCombatLibrary::ApplyGameplayEffectSpecToSentinel(const UObject* WorldContextObject, const FGameplayEffectSpecHandle& SpecHandle, const FMechSentinelHandle Sentinel, const FVector HitLocation)
{
	UMechSentinelSwarmSubsystem* Swarm = MechSwarm::CombatLibraryPrivate::GetAuthoritySwarm(WorldContextObject);
	if (!Swarm || !SpecHandle.IsValid())
	{
		return 0.f;
	}
	return Swarm->ApplyGameplayEffectSpecToSentinel(Sentinel.ToEntity(), *SpecHandle.Data.Get(), &HitLocation);
}

//----------------------------------------------------------------------//
// Info
//----------------------------------------------------------------------//
bool UMechSentinelCombatLibrary::GetSentinelInfo(const UObject* WorldContextObject, const FMechSentinelHandle Sentinel, FMechSentinelInfo& OutInfo)
{
	OutInfo = FMechSentinelInfo();

	const UMechSentinelSwarmSubsystem* Swarm = UMechSentinelSwarmSubsystem::Get(WorldContextObject);
	const FMassEntityManager* EntityManager = Swarm ? Swarm->GetEntityManager() : nullptr;
	const FMassEntityHandle Entity = Sentinel.ToEntity();
	if (!EntityManager || !EntityManager->IsEntityActive(Entity))
	{
		return false;
	}

	const FMassEntityView View(*EntityManager, Entity);
	if (const FTransformFragment* Transform = View.GetFragmentDataPtr<FTransformFragment>())
	{
		OutInfo.Location = Transform->GetTransform().GetLocation();
	}
	if (const FMechSentinelStateFragment* State = View.GetFragmentDataPtr<FMechSentinelStateFragment>())
	{
		OutInfo.State = State->State;
	}
	if (const FMechSentinelAttributesFragment* Attributes = View.GetFragmentDataPtr<FMechSentinelAttributesFragment>())
	{
		OutInfo.Health = Attributes->Health;
		OutInfo.MaxHealth = Attributes->MaxHealth;
		OutInfo.Armor = Attributes->Armor;
		OutInfo.AttackDamage = Attributes->AttackDamage;
		OutInfo.AttackSpeed = Attributes->AttackSpeed;
	}
	if (const FMechSentinelGASFragment* GAS = View.GetFragmentDataPtr<FMechSentinelGASFragment>())
	{
		OutInfo.OwnedTags = GAS->OwnedTags;
	}
	return true;
}

bool UMechSentinelCombatLibrary::IsSentinelAlive(const UObject* WorldContextObject, const FMechSentinelHandle Sentinel)
{
	const UMechSentinelSwarmSubsystem* Swarm = UMechSentinelSwarmSubsystem::Get(WorldContextObject);
	return Swarm && MechSwarm::CombatLibraryPrivate::IsAlive(*Swarm, Sentinel.ToEntity());
}
