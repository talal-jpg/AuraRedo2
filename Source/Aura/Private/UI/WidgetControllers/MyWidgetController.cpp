// Fill out your copyright notice in the Description page of Project Settings.


#include "UI/WidgetControllers/MyWidgetController.h"

#include "AbilitySystem/MyAbilitySystemComponent.h"

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


void UMyWidgetController::BroadcastAbilityInfo(UDA_MyAbilityInfo* AbilityInfo)
{
	
	FForEachAbilityDelegateSignature ForEachAbilityDelegate;
	
	ForEachAbilityDelegate.BindLambda(
		[this, &AbilityInfo](const FGameplayAbilitySpec& AbilitySpec)
		{
			FAbilityInfo Info=AbilityInfo->GetAbilityInfoForTag(MyAbilitySystemComponent->GetAbilityTagFromSpec(AbilitySpec));
			Info.InputTag= MyAbilitySystemComponent->GetInputTagFromSpec(AbilitySpec);
			
			BroadcastAbilityInfoDelegate.Broadcast(Info);
		}
	);
	MyAbilitySystemComponent->ForEachAbility(ForEachAbilityDelegate);
}
