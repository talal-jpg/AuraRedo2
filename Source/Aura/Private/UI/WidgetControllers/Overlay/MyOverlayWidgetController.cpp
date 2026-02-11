// Fill out your copyright notice in the Description page of Project Settings.


#include "UI/WidgetControllers/Overlay/MyOverlayWidgetController.h"

#include "MyGameMode.h"
#include "AbilitySystem/MyAbilitySystemComponent.h"
#include "AbilitySystem/MyAttributeSet.h"
#include "AbilitySystem/Data/MyGameplayTags.h"
#include "Kismet/GameplayStatics.h"
#include "PlayerInput/MyPlayerController.h"
#include "UI/Data/DA_MyAbilityInfo.h"

UMyOverlayWidgetController::UMyOverlayWidgetController()
{
}

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
			// UKismetSystemLibrary::PrintString(GetWorld(),FString::Printf(TEXT("Health Changed: %f"),Data.NewValue));
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
	
	MyAbilitySystemComponent->OnGameplayEffectAppliedDelegateToSelf.AddLambda(
		[this](UAbilitySystemComponent* ASC, const FGameplayEffectSpec& GESpec, FActiveGameplayEffectHandle AtiveGEHandle)
		{
			FGameplayTagContainer AssetTags;
			GESpec.GetAllAssetTags(AssetTags);
			FGameplayTag MessageTag=AssetTags.GetByIndex(0);
			if (!MessageTag.IsValid())return;
			FPopupWidgetInfo* PopupWidgetInfoRow=DT_PopupWidgetInfo->FindRow<FPopupWidgetInfo>(FName(MessageTag.ToString()),FString(""));
			OnEffectAppliedBroadcastPopupWidgetInfoDelegate.Broadcast(*PopupWidgetInfoRow);
		}
	);
	
	if (MyAbilitySystemComponent->bAbilitiesGiven)
	{
		BroadcastAbilityInfo();
	}
	else
	{
		MyAbilitySystemComponent->OnAbilitiesGivenDelegate.AddUObject(this, &UMyOverlayWidgetController::BroadcastAbilityInfo);
	}
}

void UMyOverlayWidgetController::BroadcastAbilityInfo()
{
	
	FForEachAbilityDelegateSignature ForEachAbilityDelegate;
	
	ForEachAbilityDelegate.BindLambda(
		[this](const FGameplayAbilitySpec& AbilitySpec)
		{
			FAbilityInfo AbilityInfo=DA_AbilityInfo->GetAbilityInfoForTag(MyAbilitySystemComponent->GetAbilityTagFromSpec(AbilitySpec));
			AbilityInfo.InputTag= MyAbilitySystemComponent->GetInputTagFromSpec(AbilitySpec);
			
			BroadcastAbilityInfoDelegate.Broadcast(AbilityInfo);
		}
	);
	MyAbilitySystemComponent->ForEachAbility(ForEachAbilityDelegate);
}


