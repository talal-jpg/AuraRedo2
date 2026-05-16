// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Abilities/GameplayAbility.h"
#include "MyGameplayAbility.generated.h"

/**
 * 
 */
UCLASS()
class AURA_API UMyGameplayAbility : public UGameplayAbility
{
	GENERATED_BODY()
	
public:
	UPROPERTY(EditAnywhere, Category = "Tags")
	FGameplayTag InputTag;
	
	UPROPERTY(EditAnywhere, Category = "Tags")
	FGameplayTag AbilityTag;
	
	UPROPERTY(EditAnywhere, Category = "Tags")
	FGameplayTag CooldownTag;
	
	UPROPERTY(EditDefaultsOnly,BlueprintReadOnly, Category = "Damage")
	FScalableFloat Damage;
};
