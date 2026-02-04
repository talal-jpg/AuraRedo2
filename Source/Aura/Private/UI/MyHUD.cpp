// Fill out your copyright notice in the Description page of Project Settings.


#include "UI/MyHUD.h"

#include "MyPlayerState.h"
#include "AbilitySystem/MyAbilitySystemComponent.h"
#include "AbilitySystem/MyAttributeSet.h"
#include "Blueprint/UserWidget.h"
#include "PlayerInput/MyPlayerController.h"
#include "UI/UserWidgets/MyUserWidget.h"
#include "UI/WidgetControllers/MyWidgetController.h"
#include "UI/WidgetControllers/Overlay/MyOverlayWidgetController.h"

void AMyHUD::InitOverlay()
{
	APlayerController* PlayerController = GetOwningPlayerController();
	OverlayWidget=CreateWidget<UMyUserWidget>(PlayerController, OverlayUserWidgetClass);
	UMyOverlayWidgetController* OverlayWidgetController= NewObject<UMyOverlayWidgetController>();
	AMyPlayerState* PlayerState=PlayerController->GetPlayerState<AMyPlayerState>();
	UMyAbilitySystemComponent* MyAbilitySystemComponent=PlayerState->AbilitySystemComponent;
	UMyAttributeSet* AttributeSet=PlayerState->AttributeSet;
	
	FWidgetControllerParams Params(PlayerController,PlayerState,MyAbilitySystemComponent,AttributeSet);
	OverlayWidgetController->SetWidgetControllerParams(Params);
	OverlayWidget->SetWidgetController(OverlayWidgetController);
	OverlayWidget->AddToViewport();
	OverlayWidgetController->BindCallbacksToDependencies();
	OverlayWidgetController->BroadcastInitialValues();
	
}
