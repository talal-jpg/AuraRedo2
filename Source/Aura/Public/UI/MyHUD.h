// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/HUD.h"
#include "MyHUD.generated.h"

class UMyOverlayWidgetController;
class UMyUserWidget;
/**
 * 
 */
UCLASS()
class AURA_API AMyHUD : public AHUD
{
	GENERATED_BODY()
	
public:
	void InitOverlay();

private:
	UPROPERTY()
	TObjectPtr<UMyUserWidget> OverlayWidget;

	UPROPERTY(EditAnywhere)
	TSubclassOf<UMyUserWidget> OverlayUserWidgetClass;
	
	
	UPROPERTY(EditAnywhere)
	TSubclassOf<UMyOverlayWidgetController> OverlayWidgetControllerClass;
	
	
};
