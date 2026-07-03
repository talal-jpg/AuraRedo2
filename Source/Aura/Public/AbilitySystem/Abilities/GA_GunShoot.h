// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "MyGameplayAbility.h"
#include "GA_GunShoot.generated.h"

class UMyAbilitySystemComponent;
/**
 * 
 */
UCLASS()
class AURA_API UGA_GunShoot : public UMyGameplayAbility
{
	GENERATED_BODY()
	
	UFUNCTION(BlueprintCallable)
	void MyFunc(FVector ImpactPoint,AActor* TargetActor);
	
public:	
	UPROPERTY(BlueprintReadOnly)
	UAbilitySystemComponent* TargetAsc;
	
	UPROPERTY(EditAnywhere)
	TSubclassOf<UGameplayEffect> DamageEffectClass;
	
};
