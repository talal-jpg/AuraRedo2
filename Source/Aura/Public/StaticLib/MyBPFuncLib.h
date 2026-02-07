// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "MyBPFuncLib.generated.h"

struct FGameplayTagContainer;
class UMyOverlayWidgetController;
class UMyWidgetController;
/**
 * 
 */
UCLASS()
class AURA_API UMyBPFuncLib : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()
	
	UFUNCTION(BlueprintCallable, Category = "MyBPFuncLib")
	static void GetAttributeMenuWidgetController(UMyOverlayWidgetController* OverlayWidgetController,UObject* WorldContextObject, UMyWidgetController*& OutWidgetController, APlayerController* PlayerController);
	
	UFUNCTION(BlueprintCallable, Category = "MyBPFuncLib")
	static void GetAllGameplayTags(UPARAM(ref) FGameplayTagContainer& OutGameplayTags);
};

