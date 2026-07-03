// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "MyGameplayAbility.h"
#include "GA_JumpHover.generated.h"

class UCharacterMovementComponent;
/**
 * 
 */
UCLASS()
class AURA_API UGA_JumpHover : public UMyGameplayAbility
{
	GENERATED_BODY()
	
private:
	
	virtual void ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData) override;
	
	virtual void EndAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, bool bReplicateEndAbility, bool bWasCancelled) override;
	
	UPROPERTY()
	UCharacterMovementComponent* CharacterMovementComponent;
	
	UFUNCTION()
	void OnInputPressed(float TimeWaited);
	
	UFUNCTION()
	void OnInputReleased(float TimeHeld);
	
	void ActivateHoverState();
	
	FTimerHandle HoverTimerHandle;
	
	void PrepareAndEndAbility();
};
