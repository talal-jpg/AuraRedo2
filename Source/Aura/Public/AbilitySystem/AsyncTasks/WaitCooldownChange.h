// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameplayTagContainer.h"
#include "Kismet/BlueprintAsyncActionBase.h"
#include "WaitCooldownChange.generated.h"

struct FGameplayTag;
class UAbilitySystemComponent;
DECLARE_DYNAMIC_DELEGATE_OneParam(FOnCooldownChangeDelegateSignature, float, TimeRemaining);
/**
 * 
 */
UCLASS()
class AURA_API UWaitCooldownChange : public UBlueprintAsyncActionBase
{
	GENERATED_BODY()
	
	public:
	UPROPERTY(BlueprintAssignable)
	FOnCooldownChangeDelegateSignature OnCooldownStartDelegate;
	
	UPROPERTY(BlueprintAssignable)
	FOnCooldownChangeDelegateSignature OnCooldownEndDelegate;
	
	UFUNCTION(BlueprintCallable, meta= (BlueprintInternalUseOnly = "true"))
	static UWaitCooldownChange* WaitCooldownChange(UAbilitySystemComponent* InASC, const FGameplayTag& InCooldownTag);
	
	void EndTask();
	
	private:

	UPROPERTY()
	UAbilitySystemComponent* ASC;
	
	FGameplayTag CooldownTag;
	
};
