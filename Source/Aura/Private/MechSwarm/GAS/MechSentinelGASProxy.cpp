// Mech Sentinel Swarm - the flyweight GAS proxy.

#include "MechSwarm/GAS/MechSentinelGASProxy.h"

#include "AbilitySystemComponent.h"
#include "AbilitySystem/MyAttributeSet.h"
#include "GameplayEffect.h"
#include "MechSwarm/GAS/MechSentinelAttributeSet.h"
#include "MechSwarm/GAS/MechSentinelTags.h"
#include "MechSwarm/Sentinel/MechSentinelFragments.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(MechSentinelGASProxy)

AMechSentinelGASProxy::AMechSentinelGASProxy()
{
	PrimaryActorTick.bCanEverTick = false;
	bReplicates = false;
	SetCanBeDamaged(false);
	SetActorHiddenInGame(true);

	AbilitySystemComponent = CreateDefaultSubobject<UAbilitySystemComponent>(TEXT("AbilitySystemComponent"));
	AbilitySystemComponent->SetIsReplicated(false);
	// Cues from the proxy would play at the proxy location (world origin); sentinel visuals go through Mass instead.
	AbilitySystemComponent->bSuppressGameplayCues = true;

	AttributeSet = CreateDefaultSubobject<UMechSentinelAttributeSet>(TEXT("AttributeSet"));
	SourceAttributeSet = CreateDefaultSubobject<UMyAttributeSet>(TEXT("SourceAttributeSet"));
}

void AMechSentinelGASProxy::PostInitializeComponents()
{
	Super::PostInitializeComponents();

	AbilitySystemComponent->InitAbilityActorInfo(this, this);
	AbilitySystemComponent->AddLooseGameplayTag(MechSentinelTags::Unit_Sentinel);
}

UAbilitySystemComponent* AMechSentinelGASProxy::GetAbilitySystemComponent() const
{
	return AbilitySystemComponent;
}

void AMechSentinelGASProxy::LoadEntity(const FMechSentinelAttributesFragment& Attributes, const FMechSentinelGASFragment& GAS, const bool bAttacking)
{
	if (bLoaded)
	{
		Unload();
	}
	bLoaded = true;

	UAbilitySystemComponent* ASC = AbilitySystemComponent;

	// MaxHealth first: Health is clamped against it.
	ASC->SetNumericAttributeBase(UMechSentinelAttributeSet::GetMaxHealthAttribute(), Attributes.MaxHealth);
	ASC->SetNumericAttributeBase(UMechSentinelAttributeSet::GetHealthAttribute(), Attributes.Health);
	ASC->SetNumericAttributeBase(UMechSentinelAttributeSet::GetArmorAttribute(), Attributes.BaseArmor);
	ASC->SetNumericAttributeBase(UMechSentinelAttributeSet::GetAttackDamageAttribute(), Attributes.BaseAttackDamage);
	ASC->SetNumericAttributeBase(UMechSentinelAttributeSet::GetAttackSpeedAttribute(), Attributes.BaseAttackSpeed);
	ASC->SetNumericAttributeBase(UMechSentinelAttributeSet::GetMoveSpeedMultiplierAttribute(), Attributes.BaseMoveSpeedMultiplier);
	ASC->SetNumericAttributeBase(UMechSentinelAttributeSet::GetIncomingDamageAttribute(), 0.f);
	AttributeSet->ConsumeLastResolvedDamage();

	if (bAttacking)
	{
		ASC->AddLooseGameplayTag(MechSentinelTags::State_Sentinel_Attacking);
		bAttackingTagAdded = true;
	}

	// Re-create the sentinel's active buffs / debuffs so GAS aggregates them (modifiers + granted tags).
	StoredHandles.Reset(GAS.ActiveEffects.Num());
	for (const FMechSentinelActiveEffect& Active : GAS.ActiveEffects)
	{
		FActiveGameplayEffectHandle& StoredHandle = StoredHandles.AddDefaulted_GetRef();
		if (!Active.EffectClass)
		{
			continue;
		}

		FGameplayEffectContextHandle Context = ASC->MakeEffectContext();
		// Not "Instigator": that name would shadow AActor::Instigator (shadow warnings are errors).
		if (UAbilitySystemComponent* SourceASC = Active.InstigatorASC.Get())
		{
			Context.AddInstigator(SourceASC->GetOwnerActor(), SourceASC->GetAvatarActor());
		}

		const FGameplayEffectSpecHandle SpecHandle = ASC->MakeOutgoingSpec(Active.EffectClass, Active.Level, Context);
		if (!SpecHandle.IsValid())
		{
			continue;
		}

		for (const TPair<FGameplayTag, float>& SetByCaller : Active.SetByCallerMagnitudes)
		{
			SpecHandle.Data->SetSetByCallerMagnitude(SetByCaller.Key, SetByCaller.Value);
		}
		if (Active.RemainingTime > 0.f)
		{
			SpecHandle.Data->SetDuration(Active.RemainingTime, /*bLockDuration*/true);
		}
		if (Active.StackCount > 1)
		{
			SpecHandle.Data->SetStackCount(Active.StackCount);
		}

		const FActiveGameplayEffectHandle Handle = ASC->ApplyGameplayEffectSpecToSelf(*SpecHandle.Data.Get());
		if (Handle.IsValid())
		{
			TemporaryHandles.Add(Handle);
			StoredHandle = Handle;
		}
	}
}

FActiveGameplayEffectHandle AMechSentinelGASProxy::ApplySpec(const FGameplayEffectSpec& Spec)
{
	const FActiveGameplayEffectHandle Handle = AbilitySystemComponent->ApplyGameplayEffectSpecToSelf(Spec);
	if (Handle.IsValid())
	{
		TemporaryHandles.Add(Handle);
	}
	return Handle;
}

float AMechSentinelGASProxy::ReadBack(FMechSentinelAttributesFragment& OutAttributes, FMechSentinelGASFragment& OutGAS) const
{
	const UAbilitySystemComponent* ASC = AbilitySystemComponent;

	// Instant effects change base values (permanent); duration effects only change current values (temporary).
	OutAttributes.MaxHealth = ASC->GetNumericAttributeBase(UMechSentinelAttributeSet::GetMaxHealthAttribute());
	OutAttributes.Health = FMath::Clamp(ASC->GetNumericAttributeBase(UMechSentinelAttributeSet::GetHealthAttribute()), 0.f, OutAttributes.MaxHealth);

	OutAttributes.BaseArmor = ASC->GetNumericAttributeBase(UMechSentinelAttributeSet::GetArmorAttribute());
	OutAttributes.Armor = ASC->GetNumericAttribute(UMechSentinelAttributeSet::GetArmorAttribute());

	OutAttributes.BaseAttackDamage = ASC->GetNumericAttributeBase(UMechSentinelAttributeSet::GetAttackDamageAttribute());
	OutAttributes.AttackDamage = ASC->GetNumericAttribute(UMechSentinelAttributeSet::GetAttackDamageAttribute());

	OutAttributes.BaseAttackSpeed = ASC->GetNumericAttributeBase(UMechSentinelAttributeSet::GetAttackSpeedAttribute());
	OutAttributes.AttackSpeed = ASC->GetNumericAttribute(UMechSentinelAttributeSet::GetAttackSpeedAttribute());

	OutAttributes.BaseMoveSpeedMultiplier = ASC->GetNumericAttributeBase(UMechSentinelAttributeSet::GetMoveSpeedMultiplierAttribute());
	OutAttributes.MoveSpeedMultiplier = ASC->GetNumericAttribute(UMechSentinelAttributeSet::GetMoveSpeedMultiplierAttribute());

	// Tags granted by the active effects (Stunned, Shielded, ...). The bridge adds Dead itself.
	OutGAS.OwnedTags.Reset();
	OutGAS.OwnedTags.AppendTags(ASC->GetOwnedGameplayTags());
	OutGAS.OwnedTags.RemoveTag(MechSentinelTags::Unit_Sentinel);
	OutGAS.OwnedTags.RemoveTag(MechSentinelTags::State_Sentinel_Attacking);

	return AttributeSet->ConsumeLastResolvedDamage();
}

void AMechSentinelGASProxy::Unload()
{
	UAbilitySystemComponent* ASC = AbilitySystemComponent;
	for (const FActiveGameplayEffectHandle& Handle : TemporaryHandles)
	{
		ASC->RemoveActiveGameplayEffect(Handle);
	}
	TemporaryHandles.Reset();
	StoredHandles.Reset();

	// GAS can apply effects on its own (additional "on application" effects, on-complete effects fired by the removals
	// above...). The proxy is shared by every sentinel, so nothing may survive the unload: an empty query matches every
	// active effect. A few passes because each removal can apply further on-complete effects.
	const FGameplayEffectQuery MatchAll;
	for (int32 Pass = 0; Pass < 4 && ASC->GetActiveEffects(MatchAll).Num() > 0; ++Pass)
	{
		ASC->RemoveActiveEffects(MatchAll);
	}

	if (bAttackingTagAdded)
	{
		ASC->RemoveLooseGameplayTag(MechSentinelTags::State_Sentinel_Attacking);
		bAttackingTagAdded = false;
	}

	ASC->SetNumericAttributeBase(UMechSentinelAttributeSet::GetIncomingDamageAttribute(), 0.f);
	AttributeSet->ConsumeLastResolvedDamage();
	bLoaded = false;
}
