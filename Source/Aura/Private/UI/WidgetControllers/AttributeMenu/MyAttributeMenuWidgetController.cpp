// Fill out your copyright notice in the Description page of Project Settings.


#include "UI/WidgetControllers/AttributeMenu/MyAttributeMenuWidgetController.h"

#include "MyPlayerState.h"
#include "AbilitySystem/MyAbilitySystemComponent.h"
#include "AbilitySystem/MyAttributeSet.h"
#include "Kismet/KismetSystemLibrary.h"

void UMyAttributeMenuWidgetController::BindCallbacksToDependencies()
{
	if (bCallbacksBound)return;
	bCallbacksBound=true;
	
	// Weak lambdas so a GC'd controller is skipped instead of being called through a dangling [this]
	for (auto Pair:MyAttributeSet->TagToAttributeMap)
	{
		MyAbilitySystemComponent->GetGameplayAttributeValueChangeDelegate(Pair.Value).AddWeakLambda(this,
			[this, Pair](const FOnAttributeChangeData& Data)
			{
				OnAttributeValueChangeDelegate.Broadcast(Pair.Key,Data.NewValue);
			}
			);
	}
	Cast<AMyPlayerState>(PlayerState)->OnAttribPointsChangedDelegate.AddWeakLambda(this,
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
