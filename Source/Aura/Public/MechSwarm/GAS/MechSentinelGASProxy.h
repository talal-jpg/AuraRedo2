// Mech Sentinel Swarm - the flyweight GAS proxy.
//
// One per world, server only, never replicated. It owns an AbilitySystemComponent + UMechSentinelAttributeSet.
// For each combat event the bridge (UMechSentinelSwarmSubsystem) does:
//   LoadEntity()  : Mass values -> attribute bases, re-apply the sentinel's active duration effects
//   ApplySpec()   : GAS runs the incoming effect (exec calc, modifiers, tag requirements, immunity)
//   ReadBack()    : attribute bases / currents + owned tags -> Mass
//   Unload()      : remove every temporary effect so the proxy is blank for the next sentinel
// This keeps thousands of sentinels on Mass memory while still using real GAS rules for the math.

#pragma once

#include "CoreMinimal.h"
#include "AbilitySystemInterface.h"
#include "ActiveGameplayEffectHandle.h"
#include "GameFramework/Actor.h"
#include "MechSentinelGASProxy.generated.h"

class UAbilitySystemComponent;
class UMechSentinelAttributeSet;
class UMyAttributeSet;
struct FGameplayEffectSpec;
struct FMechSentinelAttributesFragment;
struct FMechSentinelGASFragment;

UCLASS(NotPlaceable, Transient)
class AURA_API AMechSentinelGASProxy : public AActor, public IAbilitySystemInterface
{
	GENERATED_BODY()

public:
	AMechSentinelGASProxy();

	virtual UAbilitySystemComponent* GetAbilitySystemComponent() const override;
	UMechSentinelAttributeSet* GetAttributeSet() const { return AttributeSet; }

	/** Loads one sentinel. bAttacking adds State.Sentinel.Attacking as a loose tag for tag requirements. */
	void LoadEntity(const FMechSentinelAttributesFragment& Attributes, const FMechSentinelGASFragment& GAS, bool bAttacking);

	/** Applies an incoming spec to the loaded sentinel. Returned handle is valid for duration / infinite effects that were applied. */
	FActiveGameplayEffectHandle ApplySpec(const FGameplayEffectSpec& Spec);

	/** Writes the evaluated values back. Returns the damage removed from Health since LoadEntity. */
	float ReadBack(FMechSentinelAttributesFragment& OutAttributes, FMechSentinelGASFragment& OutGAS) const;

	/** Removes every effect / loose tag added since LoadEntity, including effects GAS applied on its own. */
	void Unload();

	/**
	 * Handles of the stored effects re-applied by LoadEntity, index-aligned with FMechSentinelGASFragment::ActiveEffects
	 * (invalid where the re-application failed). Lets the bridge see which stored effects GAS removed.
	 */
	const TArray<FActiveGameplayEffectHandle>& GetStoredHandles() const { return StoredHandles; }

	bool IsLoaded() const { return bLoaded; }

protected:
	virtual void PostInitializeComponents() override;

	UPROPERTY(VisibleAnywhere, Category = "GAS")
	TObjectPtr<UAbilitySystemComponent> AbilitySystemComponent;

	UPROPERTY(VisibleAnywhere, Category = "GAS")
	TObjectPtr<UMechSentinelAttributeSet> AttributeSet;

	/**
	 * The proxy is also the *source* ASC of sentinel attacks on players. The project's player damage exec calc
	 * (UExecCalc_Damage) captures source attributes from UMyAttributeSet (CritChance), so the proxy carries a
	 * default instance of it; it is never written by the swarm.
	 */
	UPROPERTY(VisibleAnywhere, Category = "GAS")
	TObjectPtr<UMyAttributeSet> SourceAttributeSet;

private:
	TArray<FActiveGameplayEffectHandle> TemporaryHandles;
	TArray<FActiveGameplayEffectHandle> StoredHandles;
	bool bLoaded = false;
	bool bAttackingTagAdded = false;
};
