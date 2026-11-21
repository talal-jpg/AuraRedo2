// Mech Sentinel Swarm - attribute set used only for combat math on the GAS proxy.

#include "MechSwarm/GAS/MechSentinelAttributeSet.h"

#include "GameplayEffectExtension.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(MechSentinelAttributeSet)

UMechSentinelAttributeSet::UMechSentinelAttributeSet()
{
	InitHealth(100.f);
	InitMaxHealth(100.f);
	InitArmor(0.f);
	InitAttackDamage(10.f);
	InitAttackSpeed(1.f);
	InitMoveSpeedMultiplier(1.f);
	InitIncomingDamage(0.f);
}

void UMechSentinelAttributeSet::PreAttributeChange(const FGameplayAttribute& Attribute, float& NewValue)
{
	Super::PreAttributeChange(Attribute, NewValue);

	if (Attribute == GetHealthAttribute())
	{
		NewValue = FMath::Clamp(NewValue, 0.f, GetMaxHealth());
	}
	else if (Attribute == GetMaxHealthAttribute())
	{
		NewValue = FMath::Max(1.f, NewValue);
	}
	else if (Attribute == GetAttackSpeedAttribute())
	{
		NewValue = FMath::Max(0.05f, NewValue);
	}
	else if (Attribute == GetMoveSpeedMultiplierAttribute() || Attribute == GetAttackDamageAttribute())
	{
		NewValue = FMath::Max(0.f, NewValue);
	}
}

void UMechSentinelAttributeSet::PreAttributeBaseChange(const FGameplayAttribute& Attribute, float& NewValue) const
{
	Super::PreAttributeBaseChange(Attribute, NewValue);

	if (Attribute == GetHealthAttribute())
	{
		NewValue = FMath::Clamp(NewValue, 0.f, GetMaxHealth());
	}
}

void UMechSentinelAttributeSet::PostGameplayEffectExecute(const FGameplayEffectModCallbackData& Data)
{
	Super::PostGameplayEffectExecute(Data);

	if (Data.EvaluatedData.Attribute == GetIncomingDamageAttribute())
	{
		const float Damage = FMath::Max(0.f, GetIncomingDamage());
		SetIncomingDamage(0.f);

		if (Damage > 0.f)
		{
			const float OldHealth = GetHealth();
			const float NewHealth = FMath::Clamp(OldHealth - Damage, 0.f, GetMaxHealth());
			SetHealth(NewHealth);
			LastResolvedDamage += OldHealth - NewHealth;
			LastIncomingDamage += Damage;
		}
	}
	else if (Data.EvaluatedData.Attribute == GetHealthAttribute())
	{
		// Direct heals / damage through Health modifiers.
		SetHealth(FMath::Clamp(GetHealth(), 0.f, GetMaxHealth()));
	}
}

float UMechSentinelAttributeSet::ConsumeLastResolvedDamage()
{
	const float Value = LastResolvedDamage;
	LastResolvedDamage = 0.f;
	return Value;
}

float UMechSentinelAttributeSet::ConsumeLastIncomingDamage()
{
	const float Value = LastIncomingDamage;
	LastIncomingDamage = 0.f;
	return Value;
}

void UMechSentinelAttributeSet::ResetDamageTracking()
{
	LastResolvedDamage = 0.f;
	LastIncomingDamage = 0.f;
}
