// Fill out your copyright notice in the Description page of Project Settings.


#include "UI/WidgetControllers/AttributeMenu/MyAttributeMenuWidgetController.h"

#include "MyPlayerState.h"
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
	Cast<AMyPlayerState>(PlayerState)->OnAttribPointsChangedDelegate.AddLambda(
		[this](int32 NewAttribPoints)
		{
			OnAttribPointsChangeDelegate.Broadcast(NewAttribPoints);
			
		}
	);
}

void UMyAttributeMenuWidgetController::BroadcastInitialValues()
{
	for (auto Pair:MyAttributeSet->TagToAttributeMap)
	{
		OnAttributeValueChangeDelegate.Broadcast(Pair.Key,Pair.Value.GetNumericValue(MyAttributeSet));
	}
	
	OnAttribPointsChangeDelegate.Broadcast(Cast<AMyPlayerState>(PlayerState)->GetAttributePoints());
}

void UMyAttributeMenuWidgetController::UpgradeAttribButtonClicked(FGameplayTag InAttributeTag)
{
	// UKismetSystemLibrary::PrintString(GetWorld(),FString::Printf(TEXT("Upgrading %s"),*InAttributeTag.ToString()));
	MyAbilitySystemComponent->UpgradeAttribute(InAttributeTag);
}
