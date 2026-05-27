// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "MyLoadScreenUserWidget.generated.h"

/**
 * 
 */
UCLASS()
class AURA_API UMyLoadScreenUserWidget : public UUserWidget
{
	GENERATED_BODY()
	
	public:
	
	UFUNCTION(BlueprintImplementableEvent,BlueprintCallable)
	void InitializeUserWidget();
	
};
