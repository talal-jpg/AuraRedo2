// Mech Sentinel Swarm - hit functions.

#include "MechSwarm/Combat/MechSentinelCombatLibrary.h"

#include "AbilitySystemComponent.h"
#include "AbilitySystemGlobals.h"
#include "AbilitySystem/Data/MyGameplayTags.h"
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
