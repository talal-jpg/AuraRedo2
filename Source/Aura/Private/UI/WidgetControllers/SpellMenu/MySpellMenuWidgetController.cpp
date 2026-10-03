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
			//this means this ability was previously assigned to a slot hence broadcast an empty info for that slot
			if (PrevInputTag.IsValid() && !PrevInputTag.MatchesTagExact(MyTags::Input_None))
			{
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
			
			// Don't touch the buttons here: the globe was already deselected in EquippedRowPressed,
			// only keep the status in sync if this ability happens to be selected
			if (SelectedAbility.AbilityTag.MatchesTagExact(AbilityTag))
			{
				SelectedAbility.StatusTag=StatusTag;
			}
			
			BroadcastAbilityInfoDelegate.Broadcast(Info);
		}
	);
	
	// AbilityStatusChanged  ,Get should enable buttons and broadcast that after
	// SpellPointChangedDelegate
	Cast<AMyPlayerState>(PlayerState)->OnSpellPointsChangedDelegate.AddLambda(
		[this](int32 NewSpellPoints)
		{
			OnSpellPointsChangedDelegate.Broadcast(NewSpellPoints);
			
			//When spell points change should enable or disable buttons again, get status , AbiltyTag from SelectedAbil
			
			bool bEnableEquip=false;
			bool bEnableSpendPoint=false;
			FString Description;
			
			if (SelectedAbility.AbilityTag.MatchesTagExact(MyTags::Ability_None))return;
			
			ShouldEnableButtons(SelectedAbility.AbilityTag,SelectedAbility.StatusTag,bEnableEquip,bEnableSpendPoint,Description);
			
			OnSpellGlobeClickedBroadCastShouldEnableDelegate.Broadcast(bEnableEquip,bEnableSpendPoint,Description);
		}
	);
	
	MyAbilitySystemComponent->OnAbilityStatusChangedDelegate.BindLambda(
		[this](FGameplayTag AbilityTag,FGameplayTag StatusTag,int32 AbilityLevel)
		{
			if (!SelectedAbility.AbilityTag.MatchesTagExact(AbilityTag))return;
			SelectedAbility.StatusTag=StatusTag;
			
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
	// UKismetSystemLibrary::PrintString(GetWorld(),TEXT("StatusTag: ") + StatusTag.ToString());
	
	if ((StatusTag.MatchesTagExact(MyTags::Ability_Status_Eligible)|| StatusTag.MatchesTagExact(MyTags::Ability_Status_Unlocked) || StatusTag.MatchesTagExact(MyTags::Ability_Status_Equiped)) && Cast<AMyPlayerState>(PlayerState)->GetSpellPoints()>0)
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
	// Selecting a different globe cancels a pending Equip
	bWaitingForEquippedRowPress=false;
	//Should enable buttons?
	if (!InAbilityTag.IsValid())
	{
		UKismetSystemLibrary::PrintString(GetWorld(),TEXT("Invalid Ability Tag"));
		return;
	}
	FGameplayTag StatusTag=MyAbilitySystemComponent->GetStatusFromAbiltyTag(InAbilityTag);
	SelectedAbility.AbilityTag=InAbilityTag;
	SelectedAbility.StatusTag=StatusTag;
	
	bool bEnableEquip=false;
	bool bEnableSpendPoint=false;
	FString Description;
	
	ShouldEnableButtons(InAbilityTag,StatusTag,bEnableEquip,bEnableSpendPoint,Description);
	
	OnSpellGlobeClickedBroadCastShouldEnableDelegate.Broadcast(bEnableEquip,bEnableSpendPoint,InAbilityTag.ToString());
}

void UMySpellMenuWidgetController::EquipButtonPressed()
{
	if(SelectedAbility.AbilityTag.MatchesTagExact(MyTags::Ability_None))return;
	if(!SelectedAbility.StatusTag.MatchesTagExact(MyTags::Ability_Status_Unlocked) && !SelectedAbility.StatusTag.MatchesTagExact(MyTags::Ability_Status_Equiped))return;
	bWaitingForEquippedRowPress=true;
}

void UMySpellMenuWidgetController::SpendSpellPointButtonPressed()
{
	if(SelectedAbility.AbilityTag.MatchesTagExact(MyTags::Ability_None))return;
	if(SelectedAbility.StatusTag.MatchesTagExact(MyTags::Ability_Status_Locked))return;
	
	if (Cast<AMyPlayerState>(PlayerState)->GetSpellPoints()>0)
	{
		MyAbilitySystemComponent->Server_SpendSpellPoint(SelectedAbility.AbilityTag,SelectedAbility.StatusTag);
	}
}

void UMySpellMenuWidgetController::EquippedRowPressed(FGameplayTag InInputTag)
{
	if (!bWaitingForEquippedRowPress)return;
	bWaitingForEquippedRowPress=false;
	
	// Server works out the current slot itself, the client's copy of the spec may not have replicated yet
	MyAbilitySystemComponent->Server_EquipAbility(SelectedAbility.AbilityTag,InInputTag);
	SpellGlobeDeselectDelegate.Broadcast(SelectedAbility.AbilityTag);
	
	
	
	//Empty SelectedAbility
	SelectedAbility.AbilityTag=MyTags::Ability_None;
	SelectedAbility.StatusTag=MyTags::Ability_Status_Unlocked;
	OnSpellGlobeClickedBroadCastShouldEnableDelegate.Broadcast(false,false,TEXT(""));
	
}


