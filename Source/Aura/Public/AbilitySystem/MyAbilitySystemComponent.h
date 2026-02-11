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
};
