// Fill out your copyright notice in the Description page of Project Settings.


#include "UI/MyHUD.h"

#include "MyPlayerState.h"
#include "AbilitySystem/MyAbilitySystemComponent.h"
#include "AbilitySystem/MyAttributeSet.h"
#include "Blueprint/GameViewportSubsystem.h"
#include "Blueprint/UserWidget.h"
#include "Engine/LocalPlayer.h"
#include "PlayerInput/MyPlayerController.h"
#include "Match/MyMatchHUDWidget.h"
#include "UI/UserWidgets/MyHexMinimapWidget.h"
#include "UI/UserWidgets/MyUserWidget.h"
#include "UI/WidgetControllers/MyWidgetController.h"
#include "UI/WidgetControllers/Overlay/MyOverlayWidgetController.h"

AMyHUD::AMyHUD()
{
	MinimapWidgetClass = UMyHexMinimapWidget::StaticClass();
	MatchWidgetClass = UMyMatchHUDWidget::StaticClass();
}

void AMyHUD::BeginPlay()
{
	Super::BeginPlay();

	AddMatchWidget();
}

void AMyHUD::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	if (MatchWidget)
	{
		MatchWidget->RemoveFromParent();
		MatchWidget = nullptr;
	}

	Super::EndPlay(EndPlayReason);
}

void AMyHUD::AddMatchWidget()
{
	APlayerController* PlayerController = GetOwningPlayerController();
	UGameViewportSubsystem* ViewportSubsystem = UGameViewportSubsystem::Get();

	if (MatchWidget || !MatchWidgetClass || !PlayerController || !PlayerController->IsLocalController() || !ViewportSubsystem)
	{
		return;
	}

	MatchWidget = CreateWidget<UMyMatchHUDWidget>(PlayerController, MatchWidgetClass);

	if (!MatchWidget)
	{
		return;
	}

	// The whole viewport (markers and name tags are drawn where the world projects), above the minimap
	FGameViewportWidgetSlot Slot;
	Slot.Anchors = FAnchors(0.f, 0.f, 1.f, 1.f);
	Slot.Alignment = FVector2D::ZeroVector;
	Slot.Offsets = FMargin(0.f);
	Slot.ZOrder = 2;

	ULocalPlayer* LocalPlayer = PlayerController->GetLocalPlayer();

	if (!(LocalPlayer ? ViewportSubsystem->AddWidgetForPlayer(MatchWidget, LocalPlayer, Slot) : ViewportSubsystem->AddWidget(MatchWidget, Slot)))
	{
		MatchWidget = nullptr;
	}
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
		// Every new pawn calls this (respawns too). The overlay listens to the PlayerState, its ASC and attributes,
		// which outlive the pawn, so the first one carries on
		if (OverlayWidget)
		{
			return;
		}
		AMyPlayerState* PlayerState=PlayerController->GetPlayerState<AMyPlayerState>();
		if (PlayerState == nullptr)
		{
			UE_LOG(LogTemp, Warning, TEXT("PlayerState is null in InitOverlay"));
			return;
		}
		OverlayWidget=CreateWidget<UMyUserWidget>(PlayerController, OverlayUserWidgetClass);
		UMyOverlayWidgetController* OverlayWidgetController= NewObject<UMyOverlayWidgetController>(this,OverlayWidgetControllerClass);
		UMyAbilitySystemComponent* MyAbilitySystemComponent=PlayerState->MyAbilitySystemComponent;
		UMyAttributeSet* AttributeSet=PlayerState->MyAttributeSet;
	
		FWidgetControllerParams Params(PlayerController,PlayerState,MyAbilitySystemComponent,AttributeSet);
		OverlayWidgetController->SetWidgetControllerParams(Params);
		OverlayWidget->SetWidgetController(OverlayWidgetController);
		OverlayWidget->AddToViewport();
		OverlayWidgetController->BindCallbacksToDependencies();
		OverlayWidgetController->BroadcastInitialValues();

		// BeginPlay adds it; a HUD whose controller wasn't local yet then gets it here
		AddMatchWidget();

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
