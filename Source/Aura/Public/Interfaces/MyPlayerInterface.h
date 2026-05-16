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

	// Add interface functions to this class. This is the class that will be inherited to implement this interface.
public:
	
		// virtual int32 GetPlayerXP();
	
	UFUNCTION(BlueprintNativeEvent)
	void AddToXP(int32 XP);
	
	UFUNCTION(BlueprintNativeEvent)	
	int32 GetXP();
	
	// virtual void 
	
	UFUNCTION(BlueprintNativeEvent)
	void AddToLevel(int32 InLevels);
	
	UFUNCTION(BlueprintNativeEvent)
	int32 GetLevel();
	
	UFUNCTION(BlueprintNativeEvent)
	void AddToAttribPoints(int32 InAttribPoints);
	
	UFUNCTION(BlueprintNativeEvent)
	int32 GetAttribPoints();
	
	UFUNCTION(BlueprintNativeEvent)
	void AddToSpellPoints(int32 InSpellPoints);
	
	UFUNCTION(BlueprintNativeEvent)
	int32 GetSpellPoints();
	
	UFUNCTION(BlueprintNativeEvent)
	void LevelUp();
	
};
