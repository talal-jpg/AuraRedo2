// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "MyUserWidget.generated.h"

class UMyWidgetController;
/**
 * 
 */
UCLASS()
class AURA_API UMyUserWidget : public UUserWidget
{
	GENERATED_BODY()
	
public:
	UPROPERTY()
	UMyWidgetController* MyWidgetController;
	
	void SetWidgetController(UMyWidgetController* InWidgetController);
	void WidgetControllerSet();
};
