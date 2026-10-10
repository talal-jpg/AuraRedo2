// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/HUD.h"
#include "MyHUD.generated.h"

class UMyHexMinimapWidget;
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
	AMyHUD();

	void InitOverlay();

private:
	UPROPERTY()
	TObjectPtr<UMyUserWidget> OverlayWidget;

	UPROPERTY(EditAnywhere)
	TSubclassOf<UMyUserWidget> OverlayUserWidgetClass;
	
	
	UPROPERTY(EditAnywhere)
	TSubclassOf<UMyOverlayWidgetController> OverlayWidgetControllerClass;

	/** Hex platform minimap, added to the top-right corner with the overlay. None = no minimap. */
	UPROPERTY(EditAnywhere, Category = "Minimap")
	TSubclassOf<UMyHexMinimapWidget> MinimapWidgetClass;

	/** Gap (slate units) between the minimap and the top-right corner of the screen. */
	UPROPERTY(EditAnywhere, Category = "Minimap")
	FVector2D MinimapCornerOffset = FVector2D(24.f, 24.f);

	UPROPERTY()
	TObjectPtr<UMyHexMinimapWidget> MinimapWidget;
	
	
};
