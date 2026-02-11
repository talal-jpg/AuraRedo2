// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Abilities/Tasks/AbilityTask.h"
#include "GT_GetMouseDataUnderCursor.generated.h"

class UGameplayAbility;
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnHitResultTargetDataSetDelegateSignature,FGameplayAbilityTargetDataHandle,TargetDataHandle);
/**
 * 
 */
UCLASS()
class AURA_API UGT_GetMouseDataUnderCursor : public UAbilityTask
{
	GENERATED_BODY()
	
	UFUNCTION(BlueprintCallable, Category = "GameplayTask")
	static UGT_GetMouseDataUnderCursor* GetMouseDataUnderCursor(UGameplayAbility* OwningAbility);
	
	UPROPERTY(BlueprintAssignable)
	FOnHitResultTargetDataSetDelegateSignature OnHitResultTargetDataSetDelegate;
	
	virtual void Activate() override;
	
	void SendMouseCursorData();
	
	void TargetDataSetCallbackOnServer(const FGameplayAbilityTargetDataHandle& TargetDataHandle,FGameplayTag GameplayTag);
};
