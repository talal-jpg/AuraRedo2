// Fill out your copyright notice in the Description page of Project Settings.


#include "UI/WidgetControllers/MyWidgetController.h"

#include "MyPlayerState.h"
#include "AbilitySystem/MyAbilitySystemComponent.h"
#include "AbilitySystem/Data/DA_MyAbilityInfo.h"
#include "Kismet/KismetSystemLibrary.h"
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


void UMyWidgetController::BroadcastAbilityInfo()
{
	
	FForEachAbilityDelegateSignature ForEachAbilityDelegate;
	
	ForEachAbilityDelegate.BindLambda(
		[this](const FGameplayAbilitySpec& AbilitySpec)
		{
			FGameplayTag AbilityTag=MyAbilitySystemComponent->GetAbilityTagFromSpec(AbilitySpec);
			FAbilityInfo AbilityInfo=DA_AbilityInfo->GetAbilityInfoForTag(MyAbilitySystemComponent->GetAbilityTagFromSpec(AbilitySpec));
			AbilityInfo.InputTag= MyAbilitySystemComponent->GetInputTagFromSpec(AbilitySpec);
			UKismetSystemLibrary::PrintString(this,AbilityInfo.Description);
			UKismetSystemLibrary::PrintString(this,AbilityTag.ToString());
			
			BroadcastAbilityInfoDelegate.Broadcast(AbilityInfo);
		}
	);
	MyAbilitySystemComponent->ForEachAbility(ForEachAbilityDelegate);
}
