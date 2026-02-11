// Fill out your copyright notice in the Description page of Project Settings.


#include "UI/WidgetControllers/AttributeMenu/MyAttributeMenuWidgetController.h"

#include "AbilitySystem/MyAbilitySystemComponent.h"
#include "AbilitySystem/MyAttributeSet.h"
#include "Kismet/KismetSystemLibrary.h"

void UMyAttributeMenuWidgetController::BindCallbacksToDependencies()
{
	for (auto Pair:MyAttributeSet->TagToAttributeMap)
	{
		MyAbilitySystemComponent->GetGameplayAttributeValueChangeDelegate(Pair.Value).AddLambda(
			[this, Pair](const FOnAttributeChangeData& Data)
			{
				OnAttributeValueChangeDelegate.Broadcast(Pair.Key,Data.NewValue);
			}
			);
	}
}

void UMyAttributeMenuWidgetController::BroadcastInitialValues()
{
	for (auto Pair:MyAttributeSet->TagToAttributeMap)
	{
		OnAttributeValueChangeDelegate.Broadcast(Pair.Key,Pair.Value.GetNumericValue(MyAttributeSet));
	}
}
