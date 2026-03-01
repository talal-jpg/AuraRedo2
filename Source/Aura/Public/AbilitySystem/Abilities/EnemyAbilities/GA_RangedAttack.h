// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "AbilitySystem/Abilities/MyGameplayAbility.h"
#include "GA_RangedAttack.generated.h"

class AMyProjectile;
/**
 * 
 */
UCLASS()
class AURA_API UGA_RangedAttack : public UMyGameplayAbility
{
	GENERATED_BODY()
	
	virtual void ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData) override;
	
	UFUNCTION(BlueprintCallable)
	void SpawnProjectile(AActor* AvatarActor,UAbilitySystemComponent* ASC,FVector TargetLocation);
	
	
	UPROPERTY(EditAnywhere)
	TSubclassOf<UGameplayEffect> DamageEffectClass;
	
	
	UPROPERTY(EditAnywhere)
	TSubclassOf<AMyProjectile> ProjectileClass;
	
};
