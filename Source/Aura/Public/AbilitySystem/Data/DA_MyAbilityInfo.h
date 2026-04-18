// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameplayTagContainer.h"
#include "Engine/DataAsset.h"
#include "DA_MyAbilityInfo.generated.h"

class UGameplayAbility;

USTRUCT(BlueprintType)
struct FAbilityInfo
{
	GENERATED_BODY()
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite)
	FGameplayTag AbilityTag;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite)
	FGameplayTag AbilityStatus;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite)
	FGameplayTag AbilityType;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite)
	FGameplayTag CooldownTag;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite)
	FGameplayTag InputTag;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite)
	UTexture2D* Icon;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite)
	UTexture2D* BackgroundMaterial;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite)
	int32 LevelRequirement;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite)
	TSubclassOf<UGameplayAbility> GameplayAbilityClass;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite)
	FString Description;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite)
	FString NextLevelDescription;
	
};

/**
 * 
 */
UCLASS()
class AURA_API UDA_MyAbilityInfo : public UDataAsset
{
	GENERATED_BODY()
	
	
public:
	FAbilityInfo GetAbilityInfoForTag(FGameplayTag AbilityTag);
	
	UPROPERTY(EditAnywhere)
	TArray<FAbilityInfo> AbilityInfos;
};
