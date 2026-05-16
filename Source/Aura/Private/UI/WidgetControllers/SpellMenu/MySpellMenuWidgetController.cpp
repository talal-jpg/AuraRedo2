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
}

void UMySpellMenuWidgetController::SpellGlobeClicked(FGameplayTag InAbilityTag)
{
	//Should enable buttons?
	if (!InAbilityTag.IsValid())
	{
		UKismetSystemLibrary::PrintString(GetWorld(),TEXT("Invalid Ability Tag"));
		return;
	}
	FGameplayTag StatusTag=MyAbilitySystemComponent->GetStatusFromAbiltyTag(InAbilityTag);
	
	SelectedAbility.AbilityTag=InAbilityTag;
	SelectedAbility.StatusTag=StatusTag;
	if (FGameplayAbilitySpec* GASpec =MyAbilitySystemComponent->GetAbilitySpecFromTag(InAbilityTag))
	{
		SelectedAbility.InputTag=MyAbilitySystemComponent->GetInputTagFromSpec(*GASpec);
	}
	// UKismetSystemLibrary::PrintString(GetWorld(),TEXT("StatusTag: ") + StatusTag.ToString());
	
	bool bEnableEquip= false;
	bool bEnableSpendPoint= false;
	if (StatusTag.MatchesTagExact(MyTags::Ability_Status_Eligible)|| StatusTag.MatchesTagExact(MyTags::Ability_Status_Unlocked) || StatusTag.MatchesTagExact(MyTags::Ability_Status_Equiped))
	{
		bEnableSpendPoint=true;
	}
	
	if (StatusTag.MatchesTagExact(MyTags::Ability_Status_Equiped)|| StatusTag.MatchesTagExact(MyTags::Ability_Status_Unlocked))
	{
		bEnableEquip=true;
	}
	
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


