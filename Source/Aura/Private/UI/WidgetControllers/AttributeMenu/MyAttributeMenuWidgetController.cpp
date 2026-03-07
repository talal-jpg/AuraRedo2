// Fill out your copyright notice in the Description page of Project Settings.


#include "UI/WidgetControllers/AttributeMenu/MyAttributeMenuWidgetController.h"

#include "MyPlayerState.h"
#include "AbilitySystem/MyAbilitySystemComponent.h"
#include "AbilitySystem/MyAttributeSet.h"
#include "Kismet/KismetSystemLibrary.h"

void UMyAttributeMenuWidgetController::BindCallbacksToDependencies()
{
	GetMyPlayerState()->OnAttributePointsChangedDelegate.AddUObject(this,&ThisClass::OnAttributePointsChangedCallback);
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
	OnAttributePointsChangedDelegate.Broadcast(GetMyPlayerState()->GetAttributePoints());
}

void UMyAttributeMenuWidgetController::UpgradeAttribute(FGameplayTag InAttributeTag)
{
	MyAbilitySystemComponent->ServerUpgradeAttribute(InAttributeTag);
}

void UMyAttributeMenuWidgetController::OnAttributePointsChangedCallback(int32 NewAttributePoints)
{
	UKismetSystemLibrary::PrintString(GetWorld(),FString::Printf(TEXT("AttributePoints: %d"),NewAttributePoints));
	OnAttributePointsChangedDelegate.Broadcast(NewAttributePoints);
}
