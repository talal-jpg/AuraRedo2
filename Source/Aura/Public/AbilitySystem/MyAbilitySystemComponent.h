// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "AbilitySystemComponent.h"
#include "UI/WidgetControllers/Overlay/MyOverlayWidgetController.h"
#include "MyAbilitySystemComponent.generated.h"

DECLARE_MULTICAST_DELEGATE(FOnAbilitiesGivenDelegateSignature)

/**
 * 
 */
UCLASS()
class AURA_API UMyAbilitySystemComponent : public UAbilitySystemComponent
{
	GENERATED_BODY()
	
	public:
	
	UMyAbilitySystemComponent();
	
	void ForEachAbility(const FForEachAbilityDelegateSignature& ForEachAbilityDelegate);
	
	bool bAbilitiesGiven=false;
	
	FOnAbilitiesGivenDelegateSignature OnAbilitiesGivenDelegate;
	
	FGameplayTag GetAbilityTagFromSpec(const FGameplayAbilitySpec& AbilitySpec);
	
	FGameplayTag GetInputTagFromSpec(const FGameplayAbilitySpec& AbilitySpec);
	
	FGameplayTag GetStatusTagFromSpec(const FGameplayAbilitySpec& AbilitySpec);
	
	FGameplayAbilitySpec GetAbilitySpecFromTag(FGameplayTag AbilityTag);
	
	
	void UpdateAbilityStauses();
	
	UFUNCTION(BlueprintCallable,Category="AbilitySystem")
	
	void AbilityInputPressed(FGameplayTag InputTag);
	
	void AbilityInputHeld(FGameplayTag InputTag);
	
	void AbilityInputReleased(FGameplayTag InputTag);
	
	UFUNCTION(Server,Reliable)
	void ServerUpgradeAttribute(FGameplayTag AttributeTag);
	
	void AddStartupAbilities(TArray<TSubclassOf<UGameplayAbility>> StartupAbilities);
	
};
