// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "AbilitySystem/Data/DA_MyEnemyCharacterClassInfo.h"
#include "UObject/Interface.h"
#include "MyCombatInterface.generated.h"

class AMyCharBase;
// This class does not need to be modified.
UINTERFACE(Blueprintable)
class UMyCombatInterface : public UInterface
{
	GENERATED_BODY()
};

/**
 * 
 */
class AURA_API IMyCombatInterface
{
	GENERATED_BODY()

	// Add interface functions to this class. This is the class that will be inherited to implement this interface.
public:
	
	UFUNCTION(BlueprintNativeEvent,BlueprintCallable)
	FVector GetCombatSocketLocation();
	
	UFUNCTION(BlueprintCallable,BlueprintNativeEvent)
	void SetCombatTarget(AActor* InCombatTarget);
	
	UFUNCTION(BlueprintCallable,BlueprintNativeEvent)
	AActor* GetCombatTarget();
	
	virtual void HandleDeath();
	
	virtual int32 GetCharLevel();
	
	virtual ECharacterClass GetCharacterClass();
	
};
