// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "AbilitySystem/Abilities/MyGameplayAbility.h"
#include "GA_MeleeAttack.generated.h"

/**
 * 
 */
UCLASS()
class AURA_API UGA_MeleeAttack : public UMyGameplayAbility
{
	GENERATED_BODY()
	
	virtual void ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData) override;
	
	UPROPERTY(EditAnywhere)
	TSubclassOf<UGameplayEffect> DamageEffectClass;
	
	UFUNCTION(BlueprintCallable)
	void ApplyDamageAtLocation(FVector HitLocation);
	
	
	
};
