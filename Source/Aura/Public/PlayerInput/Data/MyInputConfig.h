// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameplayTagContainer.h"
#include "InputAction.h"
#include "Engine/DataAsset.h"
#include "MyInputConfig.generated.h"

/**
 * 
 */
USTRUCT()
struct FInputConfig
{
	GENERATED_BODY()
	
	UPROPERTY(EditAnywhere)
	FGameplayTag InputTag;
	
	UPROPERTY(EditAnywhere)
	UInputAction* InputAction;
	
};
UCLASS()
class AURA_API UMyInputConfig : public UDataAsset
{
	GENERATED_BODY()
	public:
	UPROPERTY(EditAnywhere)
	TArray<FInputConfig> InputConfigs;
};
