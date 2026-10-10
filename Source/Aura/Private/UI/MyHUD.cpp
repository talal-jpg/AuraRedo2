// Fill out your copyright notice in the Description page of Project Settings.


#include "UI/MyHUD.h"

#include "MyPlayerState.h"
#include "AbilitySystem/MyAbilitySystemComponent.h"
#include "AbilitySystem/MyAttributeSet.h"
#include "Blueprint/GameViewportSubsystem.h"
#include "Blueprint/UserWidget.h"
#include "PlayerInput/MyPlayerController.h"
#include "UI/UserWidgets/MyHexMinimapWidget.h"
#include "UI/UserWidgets/MyUserWidget.h"
#include "UI/WidgetControllers/MyWidgetController.h"
#include "UI/WidgetControllers/Overlay/MyOverlayWidgetController.h"

AMyHUD::AMyHUD()
{
	MinimapWidgetClass = UMyHexMinimapWidget::StaticClass();
}

void AMyHUD::InitOverlay()
{
	if (APlayerController* PlayerController = GetOwningPlayerController())
	{
		if (OverlayUserWidgetClass == nullptr)
		{
			UE_LOG(LogTemp, Error, TEXT("OverlayUserWidgetClass is not set in MyHUD!"));
			return;
		}
		OverlayWidget=CreateWidget<UMyUserWidget>(PlayerController, OverlayUserWidgetClass);
		UMyOverlayWidgetController* OverlayWidgetController= NewObject<UMyOverlayWidgetController>(this,OverlayWidgetControllerClass);
		AMyPlayerState* PlayerState=PlayerController->GetPlayerState<AMyPlayerState>();
		if (PlayerState == nullptr)
		{
			UE_LOG(LogTemp, Warning, TEXT("PlayerState is null in InitOverlay"));
			return;
		}
		UMyAbilitySystemComponent* MyAbilitySystemComponent=PlayerState->MyAbilitySystemComponent;
		UMyAttributeSet* AttributeSet=PlayerState->MyAttributeSet;
	
		FWidgetControllerParams Params(PlayerController,PlayerState,MyAbilitySystemComponent,AttributeSet);
		OverlayWidgetController->SetWidgetControllerParams(Params);
		OverlayWidget->SetWidgetController(OverlayWidgetController);
		OverlayWidget->AddToViewport();
		OverlayWidgetController->BindCallbacksToDependencies();
		OverlayWidgetController->BroadcastInitialValues();

		if (MinimapWidgetClass && !MinimapWidget)
		{
			MinimapWidget = CreateWidget<UMyHexMinimapWidget>(PlayerController, MinimapWidgetClass);

			UGameViewportSubsystem* ViewportSubsystem = UGameViewportSubsystem::Get();

			if (MinimapWidget && ViewportSubsystem)
			{
				// One slot for everything: SetPositionInViewport and SetDesiredSizeInViewport both reset
				// the anchors to the top-left corner
				FGameViewportWidgetSlot Slot;
				Slot.Anchors = FAnchors(1.f, 0.f);
				Slot.Alignment = FVector2D(1.f, 0.f);
				Slot.Offsets = FMargin(-MinimapCornerOffset.X, MinimapCornerOffset.Y, MinimapWidget->MinimapSize, MinimapWidget->MinimapSize);
				Slot.ZOrder = 1;

				ViewportSubsystem->AddWidget(MinimapWidget, Slot);
			}
		}
	}
}
