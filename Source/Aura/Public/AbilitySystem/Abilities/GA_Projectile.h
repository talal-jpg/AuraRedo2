// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "MyGameplayAbility.h"
#include "GA_Projectile.generated.h"

class AMyProjectile;
/**
 * 
 */
UCLASS()
class AURA_API UGA_Projectile : public UMyGameplayAbility
{
	GENERATED_BODY()
	virtual void ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData) override;
	
	UPROPERTY(EditAnywhere)
	TSubclassOf<AMyProjectile> ProjectileClass;
	
	UPROPERTY(EditAnywhere)
	TSubclassOf<UGameplayEffect> DamageEffectClass;
	
public:
	
	
	UFUNCTION(BlueprintCallable)
	void SpawnProjectile(AActor* AvatarActor,UAbilitySystemComponent* ASC,FVector TargetLocation);
	
	
};
