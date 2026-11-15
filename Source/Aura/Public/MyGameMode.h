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
	AMyGameMode();
	
	virtual void PostLogin(APlayerController* NewPlayer) override;
	
	// Refuses players the host banned from the lobby (Current Session > Ban) and joins past the lobby's player limit
	virtual void PreLogin(const FString& Options, const FString& Address, const FUniqueNetIdRepl& UniqueId, FString& ErrorMessage) override;
	
	/** Global, server side rules of the Mass sentinel swarm (targeting caps, armor formula, damage effects). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Mech Sentinels")
	TObjectPtr<class UMechSentinelSwarmRules> SentinelSwarmRules;
	
	UPROPERTY(EditAnywhere)
	UDA_MyEnemyCharacterClassInfo* DA_MyEnemyCharacterClassInfo;
	
	UPROPERTY(EditAnywhere)
	UMyLevelUpInfo* DA_MyLevelUpInfo;
	
	UPROPERTY(EditAnywhere)
	UDA_MyAbilityInfo* DA_MyAbilityInfo;
	
	UPROPERTY(EditAnywhere)
	TSubclassOf<UMySpellMenuWidgetController> SpellMenuWidgetControllerClass;
	
};
