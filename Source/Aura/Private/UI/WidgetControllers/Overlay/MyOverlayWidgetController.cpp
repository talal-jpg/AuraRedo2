// Fill out your copyright notice in the Description page of Project Settings.


#include "UI/WidgetControllers/Overlay/MyOverlayWidgetController.h"

#include "AbilitySystem/MyAbilitySystemComponent.h"
#include "AbilitySystem/MyAttributeSet.h"

void UMyOverlayWidgetController::BroadcastInitialValues()
{
	OnHealthChangeDelegate.Broadcast(MyAttributeSet->GetHealth());
	OnManaChangeDelegate.Broadcast(MyAttributeSet->GetMana());
	OnMaxHealthChangeDelegate.Broadcast(MyAttributeSet->GetMaxHealth());
	OnMaxManaChangeDelegate.Broadcast(MyAttributeSet->GetMaxMana());
}

void UMyOverlayWidgetController::BindCallbacksToDependencies()
{
	MyAbilitySystemComponent->GetGameplayAttributeValueChangeDelegate(MyAttributeSet->GetHealthAttribute()).AddLambda(
		[this](const FOnAttributeChangeData& Data)
		{
			OnHealthChangeDelegate.Broadcast(Data.NewValue);
		}
	);
	
	MyAbilitySystemComponent->GetGameplayAttributeValueChangeDelegate(MyAttributeSet->GetMaxHealthAttribute()).AddLambda(
		[this](const FOnAttributeChangeData& Data)
		{
			OnMaxHealthChangeDelegate.Broadcast(Data.NewValue);
		}
	);
	
	MyAbilitySystemComponent->GetGameplayAttributeValueChangeDelegate(MyAttributeSet->GetManaAttribute()).AddLambda(
		[this](const FOnAttributeChangeData& Data)
		{
			OnManaChangeDelegate.Broadcast(Data.NewValue);
		}
	);
	
	MyAbilitySystemComponent->GetGameplayAttributeValueChangeDelegate(MyAttributeSet->GetMaxManaAttribute()).AddLambda(
		[this](const FOnAttributeChangeData& Data)
		{
			OnMaxManaChangeDelegate.Broadcast(Data.NewValue);
		}
	);
	
	
}
