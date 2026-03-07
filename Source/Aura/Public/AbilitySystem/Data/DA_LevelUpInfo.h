// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "DA_LevelUpInfo.generated.h"

USTRUCT()
struct FLevelUpInfo
{
	GENERATED_BODY()
	
	UPROPERTY(EditAnywhere)
	int32 Level;
	
	//Requirement for the next level
	UPROPERTY(EditAnywhere)
	int32 LevelUpXPRequirement;
	
	//Rewards for the next level, last entry in level wont reward any points bcz thr wont be a next level to go to
	UPROPERTY(EditAnywhere)
	int32 AttributePointsReward;
	
	UPROPERTY(EditAnywhere)
	int32 SpellPointsReward;
};
/**
 * 
 */
UCLASS()
class AURA_API UDA_LevelUpInfo : public UDataAsset
{
	GENERATED_BODY()
	
	
	public:
	int32 FindLevelForXP(int32 InXP);
	
	UPROPERTY(EditAnywhere)
	TArray<FLevelUpInfo> LevelUpInfos;
	
};
