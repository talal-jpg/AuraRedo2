// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameplayTagContainer.h"
#include "Kismet/BlueprintAsyncActionBase.h"
#include "BPAT_WaitForActivationTagChange.generated.h"

struct FGameplayTag;
class UAbilitySystemComponent;
/**
 * 
 */
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnActivationTagCountChangedDelegateSignature,int32 ,TagCount);

UCLASS(BlueprintType,meta= (ExposedAsyncProxy = "AsyncTask"))
class AURA_API UBPAT_WaitForActivationTagChange : public UBlueprintAsyncActionBase
{
	GENERATED_BODY()
	UFUNCTION(BlueprintCallable) 
	static UBPAT_WaitForActivationTagChange* Get_BPAT_WaitForActivationTagChange(UAbilitySystemComponent* InASC , FGameplayTag InActivationTag);
	
	UPROPERTY()
	UAbilitySystemComponent* ASC;
	
	FGameplayTag ActivationTag;
	
	UFUNCTION(BlueprintCallable)
	void EndTask();
	
	void OnActivationTagChangeCallback(const FGameplayTag Tag , int32 TagCount);
	
	UPROPERTY(BlueprintAssignable)
	FOnActivationTagCountChangedDelegateSignature OnActivationTagCountChangedDelegate;
};
