// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "MyLevelUpInfo.generated.h"

class UGameplayAbility;

USTRUCT(BlueprintType)
struct FLevelUpInfo
{
	GENERATED_BODY()
	
	UPROPERTY(EditAnywhere)
	int32 NextLevelXP=0;
	
	UPROPERTY(EditAnywhere)
	int32 AttributePointsReward=0;
	
	UPROPERTY(EditAnywhere)
	int32 SpellPointsReward=0;
	
	UPROPERTY(EditAnywhere)
	TArray<TSubclassOf<UGameplayAbility>> AbilitiesUnlocked;
	
};
/**
 * 
 */
UCLASS()
class AURA_API UMyLevelUpInfo : public UDataAsset
{
	GENERATED_BODY()
	
public:
	
	UPROPERTY(EditAnywhere)
	TArray<FLevelUpInfo> LevelUpInfos;
	
	int32 GetLevelForXP(int32 XP);
	
	void GetPointsRewardForLevel(int32 InLevel,int32& AttributePoints,int32& SpellPoints);
	
	void GetAbilitiesForLevel(int32 InLevel,TArray<TSubclassOf<UGameplayAbility>>& Abilities);
	
};
