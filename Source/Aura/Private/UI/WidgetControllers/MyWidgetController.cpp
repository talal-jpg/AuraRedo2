// Fill out your copyright notice in the Description page of Project Settings.


#include "UI/WidgetControllers/MyWidgetController.h"

#include "MyPlayerState.h"
#include "PlayerInput/MyPlayerController.h"

void UMyWidgetController::SetWidgetControllerParams(FWidgetControllerParams Params)
{
	MyAbilitySystemComponent=Params.AbilitySystemComponent;
	MyAttributeSet=Params.AttributeSet;
	PlayerController=Params.PlayerController;
	PlayerState=Params.PlayerState;
	
}

void UMyWidgetController::BindCallbacksToDependencies()
{
}

void UMyWidgetController::BroadcastInitialValues()
{
}

AMyPlayerState* UMyWidgetController::GetMyPlayerState()
{
	if (MyPlayerState)return MyPlayerState;
	else return Cast<AMyPlayerState>(PlayerState);
}

AMyPlayerController* UMyWidgetController::GetMyPlayerController()
{
	if (MyPlayerController)return MyPlayerController;
	else return Cast<AMyPlayerController>(PlayerController);
}


