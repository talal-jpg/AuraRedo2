// Splash (area) damage: every enemy around a point takes damage, GAS characters and Mech Sentinels alike.

#include "AbilitySystem/MySplashDamageLibrary.h"

#include "AbilitySystemComponent.h"
#include "AbilitySystemGlobals.h"
#include "AbilitySystem/MyAttributeSet.h"
#include "AbilitySystem/Data/MyGameplayTags.h"
#include "Components/PrimitiveComponent.h"
#include "Engine/OverlapResult.h"
#include "Engine/World.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerState.h"
#include "Interfaces/MyCombatInterface.h"
#include "MechSwarm/Combat/MechSentinelCombatLibrary.h"
#include "MechSwarm/Core/MechSentinelSwarmRules.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(MySplashDamageLibrary)

DEFINE_LOG_CATEGORY_STATIC(LogMySplashDamage, Log, All);

namespace MySplashDamagePrivate
{
	/** The damage-taking ASC of Actor, when it has UMyAttributeSet (without it IncomingDamage does nothing). */
	UAbilitySystemComponent* GetDamageableASC(const AActor* Actor)
	{
		UAbilitySystemComponent* ASC = Actor ? UAbilitySystemGlobals::GetAbilitySystemComponentFromActor(Actor) : nullptr;
		return (ASC && ASC->GetSet<UMyAttributeSet>()) ? ASC : nullptr;
	}

	bool IsDead(const AActor* Actor)
	{
		// Execute_IsDead takes a non-const object; IsDead only reads it.
		AActor* MutableActor = const_cast<AActor*>(Actor);
		return MutableActor && MutableActor->Implements<UMyCombatInterface>() && IMyCombatInterface::Execute_IsDead(MutableActor);
	}

	bool IsIgnored(const AActor* Actor, TConstArrayView<const AActor*> IgnoreActors)
	{
		for (const AActor* Ignored : IgnoreActors)
		{
			if (Ignored && (Ignored == Actor || Actor->IsAttachedTo(Ignored)))
			{
				return true;
			}
		}
		return false;
	}
}

//----------------------------------------------------------------------//
// Built-in effect
//----------------------------------------------------------------------//
UMySetByCallerDamageEffect::UMySetByCallerDamageEffect()
{
	DurationPolicy = EGameplayEffectDurationType::Instant;

	FSetByCallerFloat SetByCaller;
	SetByCaller.DataTag = MyTags::SetDamageByCaller;

	FGameplayModifierInfo& Modifier = Modifiers.AddDefaulted_GetRef();
	Modifier.Attribute = UMyAttributeSet::GetIncomingDamageAttribute();
	Modifier.ModifierOp = EGameplayModOp::Additive;
	Modifier.ModifierMagnitude = FGameplayEffectModifierMagnitude(SetByCaller);
}

//----------------------------------------------------------------------//
// Helpers
//----------------------------------------------------------------------//
AActor* UMySplashDamageLibrary::FindDamageableActor(AActor* Actor)
{
	for (; Actor; Actor = Actor->GetAttachParentActor())
	{
		if (MySplashDamagePrivate::GetDamageableASC(Actor))
		{
			return Actor;
		}
	}
	return nullptr;
}

bool UMySplashDamageLibrary::IsPlayerActor(const AActor* Actor, const UAbilitySystemComponent* ASC)
{
	if (ASC && Cast<APlayerState>(ASC->GetOwnerActor()))
	{
		return true;
	}
	const APawn* Pawn = Cast<APawn>(Actor);
	return Pawn && Pawn->IsPlayerControlled();
}

bool UMySplashDamageLibrary::IsDamageableEnemy(const AActor* Actor, const AActor* Instigator, const bool bIncludePlayers)
{
	const UAbilitySystemComponent* ASC = MySplashDamagePrivate::GetDamageableASC(Actor);
	if (!ASC || Actor == Instigator || MySplashDamagePrivate::IsDead(Actor))
	{
		return false;
	}
	// Never the instigator's own ability system, whichever actor it is reached through.
	if (Instigator && ASC == UAbilitySystemGlobals::GetAbilitySystemComponentFromActor(Instigator))
	{
		return false;
	}
	return bIncludePlayers || !IsPlayerActor(Actor, ASC);
}

float UMySplashDamageLibrary::GetFalloffScale(const float Distance, const float Radius, const float EdgeDamageScale)
{
	if (Radius <= UE_KINDA_SMALL_NUMBER)
	{
		return 1.f;
	}
	const float Alpha = FMath::Clamp(Distance / Radius, 0.f, 1.f);
	return FMath::Lerp(1.f, FMath::Clamp(EdgeDamageScale, 0.f, 1.f), Alpha);
}

void UMySplashDamageLibrary::ApplyScaledSpecToCharacter(const FGameplayEffectSpec& Spec, UAbilitySystemComponent& Target, const float Scale)
{
	if (FMath::IsNearlyEqual(Scale, 1.f))
	{
		Target.ApplyGameplayEffectSpecToSelf(Spec);
		return;
	}
	FGameplayEffectSpec Scaled(Spec);
	Scaled.SetSetByCallerMagnitude(MyTags::SetDamageByCaller, Spec.GetSetByCallerMagnitude(MyTags::SetDamageByCaller, /*WarnIfNotFound*/ false, 0.f) * Scale);
	Target.ApplyGameplayEffectSpecToSelf(Scaled);
}

float UMySplashDamageLibrary::ApplyScaledSpecToSentinel(UMechSentinelSwarmSubsystem& Swarm, const FGameplayEffectSpec& Spec, const FMechSentinelHit& Hit, const float Scale)
{
	if (FMath::IsNearlyEqual(Scale, 1.f))
	{
		return Swarm.ApplyGameplayEffectSpecToSentinel(Hit.Sentinel.ToEntity(), Spec, &Hit.ImpactPoint);
	}
	FGameplayEffectSpec Scaled(Spec);
	Scaled.SetSetByCallerMagnitude(MyTags::SetDamageByCaller, Spec.GetSetByCallerMagnitude(MyTags::SetDamageByCaller, /*WarnIfNotFound*/ false, 0.f) * Scale);
	return Swarm.ApplyGameplayEffectSpecToSentinel(Hit.Sentinel.ToEntity(), Scaled, &Hit.ImpactPoint);
}

void UMySplashDamageLibrary::GatherCharacters(const UWorld& World, const AActor* Instigator, const FVector& Center, const float Radius, const bool bIncludePlayers,
	TConstArrayView<const AActor*> IgnoreActors, TArray<FCharacterCandidate>& OutCandidates)
{
	OutCandidates.Reset();
	if (Radius <= 0.f)
	{
		return;
	}

	// Object types, not a trace channel: the overlap finds a capsule or a physics asset body whatever it responds to.
	// Pawn: character capsules and meshes (the Burrower's bodies, the airship's mesh); PhysicsBody: the airship hull.
	FCollisionObjectQueryParams ObjectParams;
	ObjectParams.AddObjectTypesToQuery(ECC_Pawn);
	ObjectParams.AddObjectTypesToQuery(ECC_PhysicsBody);
	ObjectParams.AddObjectTypesToQuery(ECC_Vehicle);
	ObjectParams.AddObjectTypesToQuery(ECC_WorldDynamic);

	FCollisionQueryParams Params(SCENE_QUERY_STAT(MySplashDamage), /*bTraceComplex*/ false, Instigator);
	TArray<FOverlapResult> Overlaps;
	World.OverlapMultiByObjectType(Overlaps, Center, FQuat::Identity, ObjectParams, FCollisionShape::MakeSphere(Radius), Params);

	// One entry per ability system: a character's capsule, mesh and weapon all count once, at their nearest point.
	TMap<UAbilitySystemComponent*, int32> IndexByASC;
	for (const FOverlapResult& Overlap : Overlaps)
	{
		AActor* Actor = FindDamageableActor(Overlap.GetActor());
		if (!Actor || MySplashDamagePrivate::IsIgnored(Actor, IgnoreActors) || !IsDamageableEnemy(Actor, Instigator, bIncludePlayers))
		{
			continue;
		}
		UAbilitySystemComponent* ASC = MySplashDamagePrivate::GetDamageableASC(Actor);

		// Distance to the overlapping collision itself (0 inside it), so a long body is hit where it passes the centre. For
		// a skeletal mesh this is its nearest physics body, not only its root body.
		float Distance = -1.f;
		if (const UPrimitiveComponent* Component = Overlap.GetComponent())
		{
			FVector OnBody;
			Distance = Component->GetDistanceToCollision(Center, OnBody);
		}
		if (Distance < 0.f)
		{
			Distance = FMath::Min(float(FVector::Dist(Center, Actor->GetActorLocation())), Radius);
		}

		if (const int32* Existing = IndexByASC.Find(ASC))
		{
			OutCandidates[*Existing].Distance = FMath::Min(OutCandidates[*Existing].Distance, Distance);
			continue;
		}
		IndexByASC.Add(ASC, OutCandidates.Num());
		OutCandidates.Add({ Actor, ASC, Distance });
	}

	OutCandidates.Sort([](const FCharacterCandidate& A, const FCharacterCandidate& B) { return A.Distance < B.Distance; });
}

void UMySplashDamageLibrary::GatherSentinels(const UMechSentinelSwarmSubsystem& Swarm, const FVector& Center, const float Radius, const FMechSentinelHandle IgnoreSentinel,
	TArray<FMechSentinelHit>& OutHits)
{
	OutHits.Reset();
	if (Radius <= 0.f || !Swarm.HasAuthority())
	{
		return;
	}

	// A sphere is a capsule with a zero-length segment.
	Swarm.QueryCapsule(Center, Center, Radius, OutHits);
	for (int32 Index = OutHits.Num() - 1; Index >= 0; --Index)
	{
		FMechSentinelHit& Hit = OutHits[Index];
		if ((IgnoreSentinel.IsSet() && Hit.Sentinel == IgnoreSentinel) || !UMechSentinelCombatLibrary::IsSentinelAlive(&Swarm, Hit.Sentinel))
		{
			OutHits.RemoveAtSwap(Index, EAllowShrinking::No);
			continue;
		}
		// An overlap has no sweep distance: sort by the distance from the centre to the sentinel's axis instead.
		Hit.Distance = float(FVector::Dist(Center, Hit.ImpactPoint));
	}
	OutHits.Sort([](const FMechSentinelHit& A, const FMechSentinelHit& B) { return A.Distance < B.Distance; });
}

//----------------------------------------------------------------------//
// Blueprint
//----------------------------------------------------------------------//
int32 UMySplashDamageLibrary::GetEnemiesInRadius(const UObject* WorldContextObject, AActor* Instigator, const FVector Center, const float Radius, const bool bIncludePlayers,
	const bool bIncludeSentinels, const TArray<AActor*>& IgnoreActors, TArray<AActor*>& OutCharacters, TArray<FMechSentinelHit>& OutSentinels)
{
	OutCharacters.Reset();
	OutSentinels.Reset();

	const UWorld* World = WorldContextObject ? WorldContextObject->GetWorld() : nullptr;
	if (!World)
	{
		return 0;
	}

	TArray<const AActor*> Ignore;
	Ignore.Reserve(IgnoreActors.Num());
	for (const AActor* Actor : IgnoreActors)
	{
		Ignore.Add(Actor);
	}
	TArray<FCharacterCandidate> Candidates;
	GatherCharacters(*World, Instigator, Center, Radius, bIncludePlayers, Ignore, Candidates);
	for (const FCharacterCandidate& Candidate : Candidates)
	{
		OutCharacters.Add(Candidate.Actor);
	}

	if (bIncludeSentinels)
	{
		if (const UMechSentinelSwarmSubsystem* Swarm = UMechSentinelSwarmSubsystem::Get(WorldContextObject))
		{
			GatherSentinels(*Swarm, Center, Radius, FMechSentinelHandle(), OutSentinels);
		}
	}
	return OutCharacters.Num() + OutSentinels.Num();
}

FMySplashDamageResult UMySplashDamageLibrary::ApplySplashDamage(const UObject* WorldContextObject, AActor* Instigator, const FVector Center, const float Damage,
	const FMySplashDamageSettings& Settings, const TArray<AActor*>& IgnoreActors, const FMechSentinelHandle IgnoreSentinel)
{
	FMySplashDamageResult Result;
	UWorld* World = WorldContextObject ? WorldContextObject->GetWorld() : nullptr;
	if (!World || World->GetNetMode() == NM_Client)
	{
		return Result;
	}

	TArray<const AActor*> Ignore;
	Ignore.Reserve(IgnoreActors.Num());
	for (const AActor* Actor : IgnoreActors)
	{
		Ignore.Add(Actor);
	}

	if (Settings.bDamageCharacters)
	{
		const TSubclassOf<UGameplayEffect> CharacterEffect = Settings.CharacterDamageEffect
			? Settings.CharacterDamageEffect : TSubclassOf<UGameplayEffect>(UMySetByCallerDamageEffect::StaticClass());
		FMySplashDamageSettings CharactersOnly = Settings;
		CharactersOnly.bDamageSentinels = false;

		if (UAbilitySystemComponent* SourceASC = UAbilitySystemGlobals::GetAbilitySystemComponentFromActor(Instigator))
		{
			// The instigator's ASC makes the spec, so damage numbers and kill XP go to it.
			const FGameplayEffectSpecHandle Spec = SourceASC->MakeOutgoingSpec(CharacterEffect, 1.f, SourceASC->MakeEffectContext());
			if (Spec.IsValid())
			{
				Spec.Data->SetSetByCallerMagnitude(MyTags::SetDamageByCaller, Damage);
				Result = ApplySplashDamageWithSpecs(*World, Instigator, Center, CharactersOnly, Spec, FGameplayEffectSpecHandle(), Ignore, FMechSentinelHandle());
			}
		}
		else
		{
			// No ASC to be the source (a plain actor): each target makes the spec itself, with the instigator in the context.
			TArray<FCharacterCandidate> Candidates;
			GatherCharacters(*World, Instigator, Center, Settings.Radius, Settings.bDamagePlayers, Ignore, Candidates);
			for (const FCharacterCandidate& Candidate : Candidates)
			{
				if (Settings.MaxCharacters > 0 && Result.Characters.Num() >= Settings.MaxCharacters)
				{
					break;
				}
				if (MySplashDamagePrivate::IsDead(Candidate.Actor))
				{
					continue;
				}
				FGameplayEffectContextHandle Context = Candidate.ASC->MakeEffectContext();
				Context.AddInstigator(Instigator, Instigator);
				const FGameplayEffectSpecHandle Spec = Candidate.ASC->MakeOutgoingSpec(CharacterEffect, 1.f, Context);
				if (Spec.IsValid())
				{
					Spec.Data->SetSetByCallerMagnitude(MyTags::SetDamageByCaller, Damage);
					ApplyScaledSpecToCharacter(*Spec.Data.Get(), *Candidate.ASC, GetFalloffScale(Candidate.Distance, Settings.Radius, Settings.EdgeDamageScale));
					Result.Characters.Add(Candidate.Actor);
				}
			}
		}
	}

	if (Settings.bDamageSentinels)
	{
		// The instigator's ASC is the source when it has one (its AttackDamage is added), else the swarm's proxy.
		const FGameplayEffectSpecHandle Spec = UMechSentinelCombatLibrary::MakeSentinelDamageSpec(WorldContextObject, Instigator, Damage, Settings.SentinelDamageEffect);
		FMySplashDamageSettings SentinelsOnly = Settings;
		SentinelsOnly.bDamageCharacters = false;
		const FMySplashDamageResult SentinelResult = ApplySplashDamageWithSpecs(*World, Instigator, Center, SentinelsOnly, FGameplayEffectSpecHandle(), Spec, Ignore, IgnoreSentinel);
		Result.Sentinels = SentinelResult.Sentinels;
		Result.SentinelDamageDealt = SentinelResult.SentinelDamageDealt;
	}
	return Result;
}

//----------------------------------------------------------------------//
// C++
//----------------------------------------------------------------------//
FMySplashDamageResult UMySplashDamageLibrary::ApplySplashDamageWithSpecs(UWorld& World, const AActor* Instigator, const FVector& Center, const FMySplashDamageSettings& Settings,
	const FGameplayEffectSpecHandle& CharacterSpec, const FGameplayEffectSpecHandle& SentinelSpec, TConstArrayView<const AActor*> IgnoreActors, const FMechSentinelHandle IgnoreSentinel)
{
	FMySplashDamageResult Result;
	if (World.GetNetMode() == NM_Client || Settings.Radius <= 0.f)
	{
		return Result;
	}

	if (Settings.bDamageCharacters && CharacterSpec.IsValid())
	{
		TArray<FCharacterCandidate> Candidates;
		GatherCharacters(World, Instigator, Center, Settings.Radius, Settings.bDamagePlayers, IgnoreActors, Candidates);
		for (const FCharacterCandidate& Candidate : Candidates)
		{
			if (Settings.MaxCharacters > 0 && Result.Characters.Num() >= Settings.MaxCharacters)
			{
				break;
			}
			// A target killed earlier in this loop (a reaction to another hit) is skipped.
			if (MySplashDamagePrivate::IsDead(Candidate.Actor))
			{
				continue;
			}
			ApplyScaledSpecToCharacter(*CharacterSpec.Data.Get(), *Candidate.ASC, GetFalloffScale(Candidate.Distance, Settings.Radius, Settings.EdgeDamageScale));
			Result.Characters.Add(Candidate.Actor);
		}
	}

	UMechSentinelSwarmSubsystem* Swarm = UMechSentinelSwarmSubsystem::Get(&World);
	if (Settings.bDamageSentinels && SentinelSpec.IsValid() && Swarm && Swarm->HasAuthority())
	{
		TArray<FMechSentinelHit> Hits;
		GatherSentinels(*Swarm, Center, Settings.Radius, IgnoreSentinel, Hits);
		for (const FMechSentinelHit& Hit : Hits)
		{
			if (Settings.MaxSentinels > 0 && Result.Sentinels.Num() >= Settings.MaxSentinels)
			{
				break;
			}
			Result.SentinelDamageDealt += ApplyScaledSpecToSentinel(*Swarm, *SentinelSpec.Data.Get(), Hit, GetFalloffScale(Hit.Distance, Settings.Radius, Settings.EdgeDamageScale));
			Result.Sentinels.Add(Hit);
		}
	}

	UE_LOG(LogMySplashDamage, Verbose, TEXT("Splash at %s (r %.0f): %d character(s), %d sentinel(s), %.1f sentinel damage."),
		*Center.ToCompactString(), Settings.Radius, Result.Characters.Num(), Result.Sentinels.Num(), Result.SentinelDamageDealt);
	return Result;
}
