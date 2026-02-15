// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameplayEffectExecutionCalculation.h"
#include "ExecCalc_Damage_Projectile.generated.h"

/**
 * 
 */
UCLASS()
class AURA_API UExecCalc_Damage_Projectile : public UGameplayEffectExecutionCalculation
{
	GENERATED_BODY()
	
	UExecCalc_Damage_Projectile();
	
	virtual void Execute_Implementation(const FGameplayEffectCustomExecutionParameters& ExecutionParams, FGameplayEffectCustomExecutionOutput& OutExecutionOutput) const override;
	
};
