// Fill out your copyright notice in the Description page of Project Settings.


#include "UI/WidgetControllers/Overlay/MyOverlayWidgetController.h"

#include "MyGameMode.h"
#include "MyPlayerState.h"
#include "AbilitySystem/MyAbilitySystemComponent.h"
#include "AbilitySystem/MyAttributeSet.h"
#include "AbilitySystem/Data/MyGameplayTags.h"
#include "Kismet/GameplayStatics.h"
#include "PlayerInput/MyPlayerController.h"
#include "AbilitySystem/Data/DA_MyAbilityInfo.h"

UMyOverlayWidgetController::UMyOverlayWidgetController()
{
}

void UMyOverlayWidgetController::BroadcastInitialValues()
{
	OnHealthChangeDelegate.Broadcast(MyAttributeSet->GetHealth());
	OnManaChangeDelegate.Broadcast(MyAttributeSet->GetMana());
	OnMaxHealthChangeDelegate.Broadcast(MyAttributeSet->GetMaxHealth());
	OnMaxManaChangeDelegate.Broadcast(MyAttributeSet->GetMaxMana());
	//HardCoding Initial vals for XP and level
	OnXPPercentChangedDelegate.Broadcast(0.0f);
	OnLevelChangedDelegate.Broadcast(1);
}

void UMyOverlayWidgetController::BindCallbacksToDependencies()
{
	GetMyPlayerState()->OnXPChangedDelegate.AddUObject(this,&ThisClass::OnXPChangedCallback);	
	GetMyPlayerState()->OnLevelChangedDelegate.AddUObject(this,&ThisClass::OnLevelChangedCallback);
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


void UMyOverlayWidgetController::OnXPChangedCallback(int32 NewXP)
{
	
	
	UDA_LevelUpInfo* LevelUpInfo = GetMyPlayerState()->LevelUpInfo;
	checkf(LevelUpInfo, TEXT("Unabled to find LevelUpInfo. Please fill out AuraPlayerState Blueprint"));
	
	const int32 Level = LevelUpInfo->FindLevelForXP(NewXP);
	const int32 MaxLevel = LevelUpInfo->LevelUpInfos.Num();
	
	if (Level <= MaxLevel && Level > 0)
	{
		const int32 LevelUpRequirement = LevelUpInfo->LevelUpInfos[Level].LevelUpXPRequirement;
		const int32 PreviousLevelUpRequirement = LevelUpInfo->LevelUpInfos[Level - 1].LevelUpXPRequirement;
	
		const int32 DeltaLevelRequirement = LevelUpRequirement - PreviousLevelUpRequirement;
		const int32 XPForThisLevel = NewXP - PreviousLevelUpRequirement;
	
		const float XPBarPercent = static_cast<float>(XPForThisLevel) / static_cast<float>(DeltaLevelRequirement);
	
		OnXPPercentChangedDelegate.Broadcast(XPBarPercent);
		// UKismetSystemLibrary::PrintString(GetWorld(),FString::Printf(TEXT("Level Up: %d/%d"),Level,MaxLevel));
	}
}

void UMyOverlayWidgetController::OnLevelChangedCallback(int32 NewLevel,bool bLevelUp)
{
	OnLevelChangedDelegate.Broadcast(NewLevel);
}



