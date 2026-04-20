// Fill out your copyright notice in the Description page of Project Settings.

#include "UI/WidgetControllers/SpellMenu/MySpellMenuWidgetController.h"

#include "AbilitySystem/MyAbilitySystemComponent.h"
#include "AbilitySystem/Data/DA_MyAbilityInfo.h"
#include "MyPlayerState.h"
#include "Kismet/KismetSystemLibrary.h"
#include "StaticLib/MyBPFuncLib.h"

void UMySpellMenuWidgetController::BroadcastInitialValues()
{
	BroadcastAbilityInfo();
	SpellPointsChanged.Broadcast(GetMyPlayerState()->GetSpellPoints());
}

void UMySpellMenuWidgetController::BindCallbacksToDependencies()
{
	MyAbilitySystemComponent->AbilityStatusChangedDelegate.AddLambda([this](const FGameplayTag& AbilityTag, const FGameplayTag& StatusTag, int32 NewLevel)
	{
		if (SelectedAbility.Ability.MatchesTagExact(AbilityTag))
		{
			SelectedAbility.Status = StatusTag;
			bool bEnableSpendPoints = false;
			bool bEnableEquip = false;
			ShouldEnableButtons(StatusTag, CurrentSpellPoints, bEnableSpendPoints, bEnableEquip);
			FString Description;
			FString NextLevelDescription;
			MyAbilitySystemComponent->GetDescriptionsByAbilityTag(AbilityTag, Description, NextLevelDescription);
			SpellGlobeSelectedDelegate.Broadcast(bEnableSpendPoints, bEnableEquip, Description, NextLevelDescription);
		}
	});
		
// 		
// 		if (AbilityInfo)
// 		{
// 			FAuraAbilityInfo Info = AbilityInfo->FindAbilityInfoForTag(AbilityTag);
// 			Info.StatusTag = StatusTag;
// 			AbilityInfoDelegate.Broadcast(Info);
// 		}
// 	});
//
	MyAbilitySystemComponent->AbilityEquipChangedDelegate.AddUObject(this, &UMySpellMenuWidgetController::OnAbilityEquipped);
//
	GetMyPlayerState()->OnSpellPointsChangedDelegate.AddLambda([this](int32 SpellPoints)
	{
		SpellPointsChanged.Broadcast(SpellPoints);
		CurrentSpellPoints = SpellPoints;

		bool bEnableSpendPoints = false;
		bool bEnableEquip = false;
		ShouldEnableButtons(SelectedAbility.Status, CurrentSpellPoints, bEnableSpendPoints, bEnableEquip);
		FString Description;
		FString NextLevelDescription;
		MyAbilitySystemComponent->GetDescriptionsByAbilityTag(SelectedAbility.Ability, Description, NextLevelDescription);
		SpellGlobeSelectedDelegate.Broadcast(bEnableSpendPoints, bEnableEquip, Description, NextLevelDescription);
	});
	
	//TODO Add delegate to send to widget 
	
	MyAbilitySystemComponent->RegisterGameplayTagEvent(MyTags::Cooldown_Firebolt,EGameplayTagEventType::NewOrRemoved).AddLambda(
		[this](const FGameplayTag Tag, int32 Count)
		{
			UKismetSystemLibrary::PrintString(this,FString::Printf(TEXT("Cooldown Count: %d"),Count));
		}
	);
}

void UMySpellMenuWidgetController::SpellGlobeSelected(const FGameplayTag& AbilityTag)
{
	
	UKismetSystemLibrary::PrintString(this, AbilityTag.ToString());
	if (bWaitingForEquipSelection)
	{
		const FGameplayTag SelectedAbilityType = DA_AbilityInfo->GetAbilityInfoForTag(AbilityTag).AbilityType;
		StopWaitingForEquipDelegate.Broadcast(SelectedAbilityType);
		bWaitingForEquipSelection = false;
	}
	
	// const FAuraGameplayTags GameplayTags = FAuraGameplayTags::Get();	
	const int32 SpellPoints = GetMyPlayerState()->GetSpellPoints();
	FGameplayTag AbilityStatus;	
	
	const bool bTagValid = AbilityTag.IsValid();
	const bool bTagNone = AbilityTag.MatchesTag(MyTags::Ability_None);
	const FGameplayAbilitySpec* AbilitySpec = MyAbilitySystemComponent->GetAbilitySpecFromTag(AbilityTag);
	const bool bSpecValid = AbilitySpec != nullptr;
	if (!bTagValid || bTagNone || !bSpecValid)
	{
		AbilityStatus = MyTags::Ability_Status_Locked;
	}
	else
	{
		// was trying to iterate on TagContainer as array , was causing crash
		AbilityStatus = MyAbilitySystemComponent->GetStatusTagFromSpec(*AbilitySpec);
	}

	SelectedAbility.Ability = AbilityTag;
	SelectedAbility.Status = AbilityStatus;
	bool bEnableSpendPoints = false;
	bool bEnableEquip = false;
	ShouldEnableButtons(AbilityStatus, SpellPoints, bEnableSpendPoints, bEnableEquip);
	FString Description;
	FString NextLevelDescription;
	
	// Was getting Null game mode On Client
	MyAbilitySystemComponent->GetDescriptionsByAbilityTag(AbilityTag, Description, NextLevelDescription);
	SpellGlobeSelectedDelegate.Broadcast(bEnableSpendPoints, bEnableEquip, Description, NextLevelDescription);
}

void UMySpellMenuWidgetController::SpendPointButtonPressed()
{
	if (MyAbilitySystemComponent)
	{
		MyAbilitySystemComponent->ServerSpendSpellPoints(SelectedAbility.Ability);
	}
}

void UMySpellMenuWidgetController::GlobeDeselect()
{
	if (bWaitingForEquipSelection)
	{
		const FGameplayTag SelectedAbilityType = DA_AbilityInfo->GetAbilityInfoForTag(SelectedAbility.Ability).AbilityType;
		StopWaitingForEquipDelegate.Broadcast(SelectedAbilityType);
		bWaitingForEquipSelection = false;
	}
	
	SelectedAbility.Ability = MyTags::Ability_None;
	SelectedAbility.Status = MyTags::Ability_Status_Locked;

	SpellGlobeSelectedDelegate.Broadcast(false, false, FString(), FString());
}

void UMySpellMenuWidgetController::EquipButtonPressed()
{
	const FGameplayTag AbilityType = DA_AbilityInfo->GetAbilityInfoForTag(SelectedAbility.Ability).AbilityType;

	WaitForEquipDelegate.Broadcast(AbilityType);
	bWaitingForEquipSelection = true;

	const FGameplayTag SelectedStatus = MyAbilitySystemComponent->GetStatusTagFromAbilityTag(SelectedAbility.Ability);
	if (SelectedStatus.MatchesTagExact(MyTags::Ability_Status_Equipped))
	{
		SelectedSlot = MyAbilitySystemComponent->GetSlotFromAbilityTag(SelectedAbility.Ability);
	}
}

void UMySpellMenuWidgetController::SpellRowGlobePressed(const FGameplayTag& SlotTag, const FGameplayTag& AbilityType)
{
	if (!bWaitingForEquipSelection) return;
	// Check selected ability against the slot's ability type.
	// (don't equip an offensive spell in a passive slot and vice versa)
	const FGameplayTag& SelectedAbilityType = DA_AbilityInfo->GetAbilityInfoForTag(SelectedAbility.Ability).AbilityType;
	if (!SelectedAbilityType.MatchesTagExact(AbilityType)) return;

	MyAbilitySystemComponent->ServerEquipAbility(SelectedAbility.Ability, SlotTag);
}

void UMySpellMenuWidgetController::OnAbilityEquipped(const FGameplayTag& AbilityTag, const FGameplayTag& Slot)
{
	bWaitingForEquipSelection = false;
	
	// FAuraAbilityInfo LastSlotInfo;
	// LastSlotInfo.StatusTag = GameplayTags.Abilities_Status_Unlocked;
	// LastSlotInfo.InputTag = PreviousSlot;
	// LastSlotInfo.AbilityTag = GameplayTags.Abilities_None;
	// // Broadcast empty info if PreviousSlot is a valid slot. Only if equipping an already-equipped spell
	// AbilityInfoDelegate.Broadcast(LastSlotInfo);

	FAbilityInfo Info = DA_AbilityInfo->GetAbilityInfoForTag(AbilityTag);
	// Info.StatusTag = Status;
	Info.InputTag = Slot;
	BroadcastAbilityInfoDelegate.Broadcast(Info);
	

	// StopWaitingForEquipDelegate.Broadcast(AbilityInfo->FindAbilityInfoForTag(AbilityTag).AbilityType);
	// SpellGlobeReassignedDelegate.Broadcast(AbilityTag);
	GlobeDeselect();
}

void UMySpellMenuWidgetController::ShouldEnableButtons(const FGameplayTag& AbilityStatus, int32 SpellPoints, bool& bShouldEnableSpellPointsButton, bool& bShouldEnableEquipButton)
{
	// const FAuraGameplayTags GameplayTags = FAuraGameplayTags::Get();

	bShouldEnableSpellPointsButton = false;
	bShouldEnableEquipButton = false;
	if (AbilityStatus.MatchesTagExact(MyTags::Ability_Status_Equipped))
	{
		bShouldEnableEquipButton = true;
		if (SpellPoints > 0)
		{
			bShouldEnableSpellPointsButton = true;
		}
	}
	else if (AbilityStatus.MatchesTagExact(MyTags::Ability_Status_Eligible))
	{
		if (SpellPoints > 0)
		{
			bShouldEnableSpellPointsButton = true;
		}
	}
	else if (AbilityStatus.MatchesTagExact(MyTags::Ability_Status_Unlocked))
	{
		bShouldEnableEquipButton = true;
		if (SpellPoints > 0)
		{
			bShouldEnableSpellPointsButton = true;
		}
	}
}
