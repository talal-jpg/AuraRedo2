// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Abilities/Tasks/AbilityTask.h"
#include "AT_SendMouseCursorData.generated.h"

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnReplicatedDataSetSendMouseCursorDataDelegateSignature,FGameplayAbilityTargetDataHandle,TargetDataHandle);
/**
 * 
 */
UCLASS()
class AURA_API UAT_SendMouseCursorData : public UAbilityTask
{
	GENERATED_BODY()
public:
	UFUNCTION(BlueprintCallable)
	static UAT_SendMouseCursorData* GetSendMouseCursorDataTaskInstance(UGameplayAbility* OwningAbility);

	UPROPERTY(BlueprintAssignable)
	FOnReplicatedDataSetSendMouseCursorDataDelegateSignature OnReplicatedDataSetSendMouseCursorDataDelegate;

	
	virtual void Activate() override;
	
	virtual void OnDestroy(bool bInOwnerFinished) override;
	
	UFUNCTION()
	void OnTargetDataSetBroadcastMouseCursorDataDelegateCallback(const FGameplayAbilityTargetDataHandle& TargetDataHandle, FGameplayTag GameplayTag);

};
