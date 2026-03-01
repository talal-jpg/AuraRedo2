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
	
	UPROPERTY(EditAnywhere)
	int32 XpRequired;
	
	UPROPERTY(EditAnywhere)
	int32 AttributePoints;
	
	UPROPERTY(EditAnywhere)
	int32 SpellPoints;
};
/**
 * 
 */
UCLASS()
class AURA_API UDA_LevelUpInfo : public UDataAsset
{
	GENERATED_BODY()
	
	UPROPERTY(EditAnywhere)
	TArray<FLevelUpInfo> LevelUpInfos;
	
	public:
	int32 FindLevelForXp(int32 InXp);
	
	
};
