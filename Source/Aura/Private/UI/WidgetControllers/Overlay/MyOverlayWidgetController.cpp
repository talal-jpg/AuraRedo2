// Fill out your copyright notice in the Description page of Project Settings.


#include "UI/WidgetControllers/Overlay/MyOverlayWidgetController.h"

#include "MyGameMode.h"
#include "MyPlayerState.h"
#include "AbilitySystem/MyAbilitySystemComponent.h"
#include "AbilitySystem/MyAttributeSet.h"
#include "AbilitySystem/Data/MyGameplayTags.h"
#include "AbilitySystem/Data/MyLevelUpInfo.h"
#include "Kismet/GameplayStatics.h"
#include "UI/Data/DA_MyAbilityInfo.h"
#include "UI/WidgetControllers/SpellMenu/MySpellMenuWidgetController.h"

UMyOverlayWidgetController::UMyOverlayWidgetController()
{
}

void UMyOverlayWidgetController::BroadcastInitialValues()
{
	OnHealthChangeDelegate.Broadcast(MyAttributeSet->GetHealth());
	OnManaChangeDelegate.Broadcast(MyAttributeSet->GetMana());
	OnMaxHealthChangeDelegate.Broadcast(MyAttributeSet->GetMaxHealth());
	OnMaxManaChangeDelegate.Broadcast(MyAttributeSet->GetMaxMana());
	
	OnXPPercentChangeDelegate.Broadcast(0.0f);
	OnLevelChangeDelegate.Broadcast(1);
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
			FGameplayTagContainer MessageTagContainer= MyTags::Message.GetTag().GetSingleTagContainer();
			FGameplayTag MessageTag=AssetTags.Filter(MessageTagContainer).Last();
			if (!MessageTag.IsValid())return;
			FPopupWidgetInfo* PopupWidgetInfoRow=DT_PopupWidgetInfo->FindRow<FPopupWidgetInfo>(FName(MessageTag.ToString()),FString(""));
			OnEffectAppliedBroadcastPopupWidgetInfoDelegate.Broadcast(*PopupWidgetInfoRow);
		}
	);
	
	if (MyAbilitySystemComponent->bAbilitiesGiven)
	{
		BroadcastAbilityInfo(DA_AbilityInfo);
	}
	else
	{
		MyAbilitySystemComponent->OnAbilitiesGivenDelegate.AddUObject(this, &UMyOverlayWidgetController::OnAbiltiesGivenCallback);
	}
	
	Cast<AMyPlayerState>(PlayerState)->OnXPChangedDelegate.AddUObject(this,&ThisClass::OnXPChangedCallback);
	
	Cast<AMyPlayerState>(PlayerState)->OnLevelChangedDelegate.AddLambda(
		[this](int32 NewLevel)
		{
			OnLevelChangeDelegate.Broadcast(NewLevel);
		}
	);
	
	MyAbilitySystemComponent->OnAbilityEquippedDelegate.AddLambda(
		[this](FGameplayTag AbilityTag,FGameplayTag InputTag,FGameplayTag StatusTag,FGameplayTag PrevInputTag)
	{
			if (PrevInputTag.IsValid())//this means this ability was previously assigned to a slot hence broadcast an empty info for that slot
			{
				//Why is PrevInput not valid if I click on Equip again after the ability is already selected and once equip has been pressed already, should I just disable equip and delselect after AbilityRowPress??
				FAbilityInfo LastSlotInfo;
				LastSlotInfo.InputTag=PrevInputTag;
				LastSlotInfo.CooldownTag=MyTags::Ability_Cooldown_None;
				LastSlotInfo.AbilityTag=MyTags::Ability_None;
				LastSlotInfo.AbilityStatus=MyTags::Ability_Status_Unlocked;
				// EmptyInfo.Icon= UTexture2D();
				BroadcastAbilityInfoDelegate.Broadcast(LastSlotInfo);
				
			}
			FAbilityInfo Info= DA_AbilityInfo->GetAbilityInfoForTag(AbilityTag);
			Info.InputTag=InputTag;
			Info.AbilityStatus=StatusTag;
			
			BroadcastAbilityInfoDelegate.Broadcast(Info);
			
		}
	);
	
}


void UMyOverlayWidgetController::OnAbiltiesGivenCallback()
{
	BroadcastAbilityInfo(DA_AbilityInfo);
}

void UMyOverlayWidgetController::OnXPChangedCallback(int32 NewXP)
{
	//GameMode Doesnt exist on server have to put LevelUpInfo on PlayerState
	
	UMyLevelUpInfo* MyLevelUpInfo=Cast<AMyPlayerState>(PlayerState)->MyLevelUpInfo;
			
	checkf(MyLevelUpInfo,TEXT("PleaseSetLevelUpInfoOnPlayerStateSoThatItCanBePresentOnClientsAsWell"));
	
	int32 CurrentLevel=MyLevelUpInfo->GetLevelForXP(NewXP);
	
	// UKismetSystemLibrary::PrintString(GetWorld(),FString::Printf(TEXT("Current Level: %d"),CurrentLevel));
	
	//OPTIONAL can check if current level >0 && <= MaxLevel 
	int32 NextLevelXPReq=MyLevelUpInfo->LevelUpInfos[CurrentLevel].NextLevelXP;
	int32 PreviousLevelXPReq=MyLevelUpInfo->LevelUpInfos[CurrentLevel-1].NextLevelXP;
	
	int32 TotalXPReqForThisLevel=NextLevelXPReq-PreviousLevelXPReq;
	
	int32 CurrentXPAcquiredThisLevel=NewXP-PreviousLevelXPReq;
	
	float XPProgressThisLevel=static_cast<float>(CurrentXPAcquiredThisLevel)/static_cast<float>(TotalXPReqForThisLevel);
	
	OnXPPercentChangeDelegate.Broadcast(XPProgressThisLevel);
}


