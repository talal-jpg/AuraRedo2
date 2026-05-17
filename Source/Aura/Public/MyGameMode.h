// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "MyGameMode.generated.h"

class UDA_MyAbilityInfo;
class UMyLevelUpInfo;
class UDA_MyEnemyCharacterClassInfo;
class UMySpellMenuWidgetController;
/**
 * 
 */
UCLASS()
class AURA_API AMyGameMode : public AGameModeBase
{
	GENERATED_BODY()
	
public:
	
	UPROPERTY(EditAnywhere)
	UDA_MyEnemyCharacterClassInfo* DA_MyEnemyCharacterClassInfo;
	
	UPROPERTY(EditAnywhere)
	UMyLevelUpInfo* DA_MyLevelUpInfo;
	
	UPROPERTY(EditAnywhere)
	UDA_MyAbilityInfo* DA_MyAbilityInfo;
	
	UPROPERTY(EditAnywhere)
	TSubclassOf<UMySpellMenuWidgetController> SpellMenuWidgetControllerClass;
	
};
