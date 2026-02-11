// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameplayTagContainer.h"
#include "Engine/DataAsset.h"
#include "DA_MyEnemyCharacterClassInfo.generated.h"

class UGameplayEffect;

UENUM()
enum class ECharacterClass : uint8
{
	Elemental,
	Warrior,
	Ranger
};

USTRUCT()
struct FEnemyCharClassInfo
{
	GENERATED_BODY()
	
	UPROPERTY(EditAnywhere)
	ECharacterClass Class;
	
	UPROPERTY(EditAnywhere)
	TSubclassOf<UGameplayEffect> PrimaryAttributesEffect;
};
/**
 * 
 */
UCLASS()
class AURA_API UDA_MyEnemyCharacterClassInfo : public UDataAsset
{
	GENERATED_BODY()
	
public:
	
	UPROPERTY(EditAnywhere)
	TArray<FEnemyCharClassInfo> EnemyCharClassInfos;
	
	FEnemyCharClassInfo GetInfoForClass(ECharacterClass Class);
	
	UPROPERTY(EditAnywhere)
	TSubclassOf<UGameplayEffect> SecondaryAttributesEffect;
	
	UPROPERTY(EditAnywhere)
	TSubclassOf<UGameplayEffect> VitalAttributesEffect;
};
