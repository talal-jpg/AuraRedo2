// Fill out your copyright notice in the Description page of Project Settings.


#include "UI/WidgetControllers/MyWidgetController.h"

void UMyWidgetController::SetWidgetControllerParams(FWidgetControllerParams Params)
{
	MyAbilitySystemComponent=Params.AbilitySystemComponent;
	MyAttributeSet=Params.AttributeSet;
}

void UMyWidgetController::BindCallbacksToDependencies()
{
}

void UMyWidgetController::BroadcastInitialValues()
{
}


