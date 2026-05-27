// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "MyGameplayAbility.h"
#include "GA_Shards.generated.h"

/**
 * 
 */
UCLASS()
class AURA_API UGA_Shards : public UMyGameplayAbility
{
	GENERATED_BODY()
	
	
	UFUNCTION(BlueprintCallable)
	void GetAliveActorsWithinRadius(FVector Location,float Radius, UPARAM(ref)TArray<AActor*>& OutActors);
	
	
};
