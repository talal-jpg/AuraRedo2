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
	int32 FindLevelForXP(int32 XP);
	
	UFUNCTION(BlueprintNativeEvent)
	int32 GetXP();
	

	// Add interface functions to this class. This is the class that will be inherited to implement this interface.
public:
};
