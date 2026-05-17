// Fill out your copyright notice in the Description page of Project Settings.


#include "UI/WidgetControllers/SpellMenu/MySpellMenuWidgetController.h"

#include "GameplayTagContainer.h"
#include "MyPlayerState.h"
#include "AbilitySystem/MyAbilitySystemComponent.h"
#include "AbilitySystem/Data/MyGameplayTags.h"
#include "Kismet/KismetSystemLibrary.h"

void UMySpellMenuWidgetController::BindCallbacksToDependencies()
{
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
			FAbilityInfo Info= MyAbilityInfo->GetAbilityInfoForTag(AbilityTag);
			Info.InputTag=InputTag;
			Info.AbilityStatus=StatusTag;
			
			BroadcastAbilityInfoDelegate.Broadcast(Info);
		}
	);
	
	// AbilityStatusChanged  ,Get should enable buttons and broadcast that after
	// SpellPointChangedDelegate
	Cast<AMyPlayerState>(PlayerState)->OnSpellPointsChangedDelegate.AddLambda(
		[this](int32 NewSpellPoints)
		{
			OnSpellPointsChangedDelegate.Broadcast(NewSpellPoints);
			
			//TODO When spell points change should enable or disable buttons again? get status , AbiltyTag from SelectedAbil
			
			// bool bEnableEquip=false;
			// bool bEnableSpendPoint=false;
			// FString Description;
			//
			// ShouldEnableButtons(AbilityTag,StatusTag,bEnableEquip,bEnableSpendPoint,Description);
			// OnSpellGlobeClickedBroadCastShouldEnableDelegate.Broadcast(bEnableEquip,bEnableSpendPoint,Description);
		}
	);
	
	MyAbilitySystemComponent->OnAbilityStatusChangedDelegate.BindLambda(
		[this](FGameplayTag AbilityTag,FGameplayTag StatusTag,int32 AbilityLevel)
		{
			bool bEnableEquip=false;
			bool bEnableSpendPoint=false;
			FString Description;
			
			ShouldEnableButtons(AbilityTag,StatusTag,bEnableEquip,bEnableSpendPoint,Description);
			OnSpellGlobeClickedBroadCastShouldEnableDelegate.Broadcast(bEnableEquip,bEnableSpendPoint,Description);
			
		}
		);
	
}

void UMySpellMenuWidgetController::ShouldEnableButtons(FGameplayTag InAbilityTag, FGameplayTag StatusTag,bool& bEnableEquip, bool& bEnableSpendSpellPoints, FString& Description)
{
	SelectedAbility.AbilityTag=InAbilityTag;
	SelectedAbility.StatusTag=StatusTag;
	if (FGameplayAbilitySpec* GASpec =MyAbilitySystemComponent->GetAbilitySpecFromTag(InAbilityTag))
	{
		SelectedAbility.InputTag=MyAbilitySystemComponent->GetInputTagFromSpec(*GASpec);
	}
	// UKismetSystemLibrary::PrintString(GetWorld(),TEXT("StatusTag: ") + StatusTag.ToString());
	
	if (StatusTag.MatchesTagExact(MyTags::Ability_Status_Eligible)|| StatusTag.MatchesTagExact(MyTags::Ability_Status_Unlocked) || StatusTag.MatchesTagExact(MyTags::Ability_Status_Equiped))
	{
		bEnableSpendSpellPoints=true;
	}
	
	if (StatusTag.MatchesTagExact(MyTags::Ability_Status_Equiped)|| StatusTag.MatchesTagExact(MyTags::Ability_Status_Unlocked))
	{
		bEnableEquip=true;
	}
	//TODO Get and Fill Description from Ability Spec bcz mana cost cool down change with level
}

void UMySpellMenuWidgetController::BroadcastInitialValues()
{
	Super::BroadcastInitialValues();
	if (MyAbilitySystemComponent->bAbilitiesGiven)
	{
		checkf(MyAbilityInfo,TEXT("MyAbilityInfoOnSpellMenu is null"));
		BroadcastAbilityInfo(MyAbilityInfo);
	}
	OnSpellGlobeClickedBroadCastShouldEnableDelegate.Broadcast(false,false,TEXT(""));
	
	OnSpellPointsChangedDelegate.Broadcast(Cast<AMyPlayerState>(PlayerState)->GetSpellPoints());
}

void UMySpellMenuWidgetController::SpellGlobeClicked(FGameplayTag InAbilityTag)
{
	FGameplayTag StatusTag=MyAbilitySystemComponent->GetStatusFromAbiltyTag(InAbilityTag);
	//Should enable buttons?
	if (!InAbilityTag.IsValid())
	{
		UKismetSystemLibrary::PrintString(GetWorld(),TEXT("Invalid Ability Tag"));
		return;
	}
	bool bEnableEquip=false;
	bool bEnableSpendPoint=false;
	FString Description;
	
	ShouldEnableButtons(InAbilityTag,StatusTag,bEnableEquip,bEnableSpendPoint,Description);
	
	OnSpellGlobeClickedBroadCastShouldEnableDelegate.Broadcast(bEnableEquip,bEnableSpendPoint,InAbilityTag.ToString());
}

void UMySpellMenuWidgetController::EquipButtonPressed()
{
	if(SelectedAbility.AbilityTag.MatchesTagExact(MyTags::Ability_None))return;
	bWaitingForEquippedRowPress=true;
}

void UMySpellMenuWidgetController::SpendSpellPointButtonPressed()
{
	if(SelectedAbility.AbilityTag.MatchesTagExact(MyTags::Ability_None))return;
	if(SelectedAbility.StatusTag.MatchesTagExact(MyTags::Ability_Status_Locked))return;
	
	MyAbilitySystemComponent->Server_SpendSpellPoint(SelectedAbility.AbilityTag,SelectedAbility.StatusTag);
	
	
}

void UMySpellMenuWidgetController::EquippedRowPressed(FGameplayTag InInputTag)
{
	if (!bWaitingForEquippedRowPress)return;
	bWaitingForEquippedRowPress=false;
	
	MyAbilitySystemComponent->Server_EquipAbility(SelectedAbility.AbilityTag,InInputTag,SelectedAbility.InputTag);
	SpellGlobeDeselectDelegate.Broadcast(SelectedAbility.AbilityTag);
	
	//Empty SelectedAbility
	SelectedAbility.AbilityTag=MyTags::Ability_None;
	SelectedAbility.InputTag=MyTags::Input_None;
	SelectedAbility.StatusTag=MyTags::Ability_Status_Unlocked;
	OnSpellGlobeClickedBroadCastShouldEnableDelegate.Broadcast(false,false,TEXT(""));
	
}


