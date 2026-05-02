// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameplayTagContainer.h"
#include "Kismet/BlueprintAsyncActionBase.h"
#include "BPAT_WaitForCooldownChange.generated.h"

struct FActiveGameplayEffectHandle;
struct FGameplayEffectSpec;
class UAbilitySystemComponent;
struct FGameplayTag;
/**
 * 
 */
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnCooldownStartedDelegateSignature,float,RemainingTime);
UCLASS()
class AURA_API UBPAT_WaitForCooldownChange : public UBlueprintAsyncActionBase
{
	GENERATED_BODY()
	
	
public:
	
	UFUNCTION(BlueprintCallable, Category = "AbilitySystem|Cooldown")
	static UBPAT_WaitForCooldownChange* WaitForCooldownChange(UAbilitySystemComponent* InASC,FGameplayTag InCooldownTag);
	
	void OnCooldownStartedCallback(UAbilitySystemComponent* ASC, const FGameplayEffectSpec& GESpec, FActiveGameplayEffectHandle ActiveGameplayEffectHandle);
	
	FGameplayTag CooldownTag;
	
	UPROPERTY()
	UAbilitySystemComponent* ASC;
	
	UPROPERTY(BlueprintAssignable)
	FOnCooldownStartedDelegateSignature OnCooldownStartedDelegate;
	
	void EndTask();
};
