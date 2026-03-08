// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "UObject/Interface.h"
#include "MyPlayerInterface.generated.h"

// This class does not need to be modified.
UINTERFACE()
class UMyPlayerInterface : public UInterface
{
	GENERATED_BODY()
};

/**
 * 
 */
class AURA_API IMyPlayerInterface
{
	GENERATED_BODY()
	
public:
	UFUNCTION(BlueprintNativeEvent)
	void AddToXP(int32 XP);
	
	UFUNCTION(BlueprintNativeEvent)
	void LevelUp();
	
	UFUNCTION(BlueprintNativeEvent)
	int32 GetAttributePointsReward(int32 Level);
	
	UFUNCTION(BlueprintNativeEvent)
	int32 GetSpellPointsReward(int32 Level);
	
	UFUNCTION(BlueprintNativeEvent)
	void AddToPlayerLevel(int32 InPlayerLevel);
	
	UFUNCTION(BlueprintNativeEvent)
	void AddToAttributePoints(int32 InAttributePoints);
	
	UFUNCTION(BlueprintNativeEvent)
	void AddToSpellPoints(int32 InSpellPoints);
	
	UFUNCTION(BlueprintNativeEvent)
	int32 GetAttributePoints();
	
	UFUNCTION(BlueprintNativeEvent)
	int32 GetSpellPoints();
	
	UFUNCTION(BlueprintNativeEvent)
	int32 FindLevelForXP(int32 XP);
	
	UFUNCTION(BlueprintNativeEvent)
	int32 GetXP();
	
	
	// Add interface functions to this class. This is the class that will be inherited to implement this interface.
public:
};
