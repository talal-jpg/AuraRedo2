// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameplayTagContainer.h"
#include "Engine/DataAsset.h"
#include "DA_MyAbilityInfo.generated.h"

USTRUCT(BlueprintType)
struct FAbilityInfo
{
	GENERATED_BODY()
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite)
	FGameplayTag AbilityTag;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite)
	FGameplayTag AbilityStatus;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite)
	FGameplayTag InputTag;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite)
	UTexture2D* Icon;
	
	
	
};

/**
 * 
 */
UCLASS()
class AURA_API UDA_MyAbilityInfo : public UDataAsset
{
	GENERATED_BODY()
	
	UPROPERTY(EditAnywhere)
	TArray<FAbilityInfo> AbilityInfos;
	
public:
	FAbilityInfo GetAbilityInfoForTag(FGameplayTag AbilityTag);
};
