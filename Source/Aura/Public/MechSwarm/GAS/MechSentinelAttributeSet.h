// Mech Sentinel Swarm - attribute set used only for combat math on the GAS proxy.
//
// The values here are NOT the source of truth. The source of truth is FMechSentinelAttributesFragment in Mass.
// For each hit / effect change, the bridge loads one entity's values into this set, lets GAS run
// (modifiers, executions, tag requirements, immunity, stacking), then writes the results back to Mass.

#pragma once

#include "CoreMinimal.h"
#include "AttributeSet.h"
#include "AbilitySystemComponent.h"
#include "MechSentinelAttributeSet.generated.h"

UCLASS()
class AURA_API UMechSentinelAttributeSet : public UAttributeSet
{
	GENERATED_BODY()

public:
	UMechSentinelAttributeSet();

	virtual void PreAttributeChange(const FGameplayAttribute& Attribute, float& NewValue) override;
	virtual void PreAttributeBaseChange(const FGameplayAttribute& Attribute, float& NewValue) const override;
	virtual void PostGameplayEffectExecute(const FGameplayEffectModCallbackData& Data) override;

	/** Damage actually removed from Health by the last executed effect (after armor / shield). Reset by the bridge. */
	float ConsumeLastResolvedDamage();

	// Vital
	UPROPERTY(BlueprintReadOnly, Category = "Sentinel|Vital")
	FGameplayAttributeData Health;
	ATTRIBUTE_ACCESSORS_BASIC(UMechSentinelAttributeSet, Health)

	UPROPERTY(BlueprintReadOnly, Category = "Sentinel|Vital")
	FGameplayAttributeData MaxHealth;
	ATTRIBUTE_ACCESSORS_BASIC(UMechSentinelAttributeSet, MaxHealth)

	// Combat
	UPROPERTY(BlueprintReadOnly, Category = "Sentinel|Combat")
	FGameplayAttributeData Armor;
	ATTRIBUTE_ACCESSORS_BASIC(UMechSentinelAttributeSet, Armor)

	UPROPERTY(BlueprintReadOnly, Category = "Sentinel|Combat")
	FGameplayAttributeData AttackDamage;
	ATTRIBUTE_ACCESSORS_BASIC(UMechSentinelAttributeSet, AttackDamage)

	/** Attacks per second. */
	UPROPERTY(BlueprintReadOnly, Category = "Sentinel|Combat")
	FGameplayAttributeData AttackSpeed;
	ATTRIBUTE_ACCESSORS_BASIC(UMechSentinelAttributeSet, AttackSpeed)

	/**
	 * Per-entity multiplier on the swarm-wide MovementSpeed (which lives in a Mass shared fragment).
	 * Lets slow / haste effects target single sentinels while the base speed stays shared.
	 */
	UPROPERTY(BlueprintReadOnly, Category = "Sentinel|Movement")
	FGameplayAttributeData MoveSpeedMultiplier;
	ATTRIBUTE_ACCESSORS_BASIC(UMechSentinelAttributeSet, MoveSpeedMultiplier)

	// Meta
	/** Meta attribute written by ExecCalc_SentinelDamage, turned into Health loss in PostGameplayEffectExecute. */
	UPROPERTY(BlueprintReadOnly, Category = "Sentinel|Meta")
	FGameplayAttributeData IncomingDamage;
	ATTRIBUTE_ACCESSORS_BASIC(UMechSentinelAttributeSet, IncomingDamage)

private:
	float LastResolvedDamage = 0.f;
};
