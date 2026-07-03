// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "MyGameplayAbility.h"
#include "GA_Roll.generated.h"

/**
 * 
 */
UCLASS()
class AURA_API UGA_Roll : public UMyGameplayAbility
{
	GENERATED_BODY()
	
	virtual void ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData) override;
	
	UPROPERTY(EditAnywhere)
	UAnimMontage* RollMontage;
	
	UFUNCTION()
	void OnCompletedCallback();
};
