// Fill out your copyright notice in the Description page of Project Settings.

#include "UI/WidgetControllers/SpellMenu/MySpellMenuWidgetController.h"

#include "AbilitySystem/MyAbilitySystemComponent.h"
#include "AbilitySystem/Data/DA_MyAbilityInfo.h"
#include "MyPlayerState.h"

// void UMySpellMenuWidgetController::BroadcastInitialValues()
// {
// 	BroadcastAbilityInfo();
// 	SpellPointsChanged.Broadcast(GetMyPlayerState()->GetSpellPoints());
// }

// void UMySpellMenuWidgetController::BindCallbacksToDependencies()
// {
// 	MyAbilitySystemComponent()->AbilityStatusChanged.AddLambda([this](const FGameplayTag& AbilityTag, const FGameplayTag& StatusTag, int32 NewLevel)
// 	{
// 		if (SelectedAbility.Ability.MatchesTagExact(AbilityTag))
// 		{
// 			SelectedAbility.Status = StatusTag;
// 			bool bEnableSpendPoints = false;
// 			bool bEnableEquip = false;
// 			ShouldEnableButtons(StatusTag, CurrentSpellPoints, bEnableSpendPoints, bEnableEquip);
// 			FString Description;
// 			FString NextLevelDescription;
// 			GetAuraASC()->GetDescriptionsByAbilityTag(AbilityTag, Description, NextLevelDescription);
// 			SpellGlobeSelectedDelegate.Broadcast(bEnableSpendPoints, bEnableEquip, Description, NextLevelDescription);
// 		}
// 		
// 		if (AbilityInfo)
// 		{
// 			FAuraAbilityInfo Info = AbilityInfo->FindAbilityInfoForTag(AbilityTag);
// 			Info.StatusTag = StatusTag;
// 			AbilityInfoDelegate.Broadcast(Info);
// 		}
// 	});
//
// 	GetAuraASC()->AbilityEquipped.AddUObject(this, &USpellMenuWidgetController::OnAbilityEquipped);
//
// 	GetAuraPS()->OnSpellPointsChangedDelegate.AddLambda([this](int32 SpellPoints)
// 	{
// 		SpellPointsChanged.Broadcast(SpellPoints);
// 		CurrentSpellPoints = SpellPoints;
//
// 		bool bEnableSpendPoints = false;
// 		bool bEnableEquip = false;
// 		ShouldEnableButtons(SelectedAbility.Status, CurrentSpellPoints, bEnableSpendPoints, bEnableEquip);
// 		FString Description;
// 		FString NextLevelDescription;
// 		GetAuraASC()->GetDescriptionsByAbilityTag(SelectedAbility.Ability, Description, NextLevelDescription);
// 		SpellGlobeSelectedDelegate.Broadcast(bEnableSpendPoints, bEnableEquip, Description, NextLevelDescription);
// 	});
// }

void UMySpellMenuWidgetController::SpellGlobeSelected(const FGameplayTag& AbilityTag)
{
	// if (bWaitingForEquipSelection)
	// {
	// 	const FGameplayTag SelectedAbilityType = AbilityInfo->FindAbilityInfoForTag(AbilityTag).AbilityType;
	// 	StopWaitingForEquipDelegate.Broadcast(SelectedAbilityType);
	// 	bWaitingForEquipSelection = false;
	// }
	
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
		AbilityStatus = MyAbilitySystemComponent->GetStatusTagFromSpec(*AbilitySpec);
	}

	SelectedAbility.Ability = AbilityTag;
	SelectedAbility.Status = AbilityStatus;
	bool bEnableSpendPoints = false;
	bool bEnableEquip = false;
	ShouldEnableButtons(AbilityStatus, SpellPoints, bEnableSpendPoints, bEnableEquip);
	FString Description;
	FString NextLevelDescription;
	MyAbilitySystemComponent->GetDescriptionsByAbilityTag(AbilityTag, Description, NextLevelDescription);
	SpellGlobeSelectedDelegate.Broadcast(bEnableSpendPoints, bEnableEquip, Description, NextLevelDescription);
}

// void USpellMenuWidgetController::SpendPointButtonPressed()
// {
// 	if (GetAuraASC())
// 	{
// 		GetAuraASC()->ServerSpendSpellPoint(SelectedAbility.Ability);
// 	}
// }
//
// void USpellMenuWidgetController::GlobeDeselect()
// {
// 	if (bWaitingForEquipSelection)
// 	{
// 		const FGameplayTag SelectedAbilityType = AbilityInfo->FindAbilityInfoForTag(SelectedAbility.Ability).AbilityType;
// 		StopWaitingForEquipDelegate.Broadcast(SelectedAbilityType);
// 		bWaitingForEquipSelection = false;
// 	}
// 	
// 	SelectedAbility.Ability = FAuraGameplayTags::Get().Abilities_None;
// 	SelectedAbility.Status = FAuraGameplayTags::Get().Abilities_Status_Locked;
//
// 	SpellGlobeSelectedDelegate.Broadcast(false, false, FString(), FString());
// }
//
// void USpellMenuWidgetController::EquipButtonPressed()
// {
// 	const FGameplayTag AbilityType = AbilityInfo->FindAbilityInfoForTag(SelectedAbility.Ability).AbilityType;
//
// 	WaitForEquipDelegate.Broadcast(AbilityType);
// 	bWaitingForEquipSelection = true;
//
// 	const FGameplayTag SelectedStatus = GetAuraASC()->GetStatusFromAbilityTag(SelectedAbility.Ability);
// 	if (SelectedStatus.MatchesTagExact(FAuraGameplayTags::Get().Abilities_Status_Equipped))
// 	{
// 		SelectedSlot = GetAuraASC()->GetSlotFromAbilityTag(SelectedAbility.Ability);
// 	}
// }
//
// void USpellMenuWidgetController::SpellRowGlobePressed(const FGameplayTag& SlotTag, const FGameplayTag& AbilityType)
// {
// 	if (!bWaitingForEquipSelection) return;
// 	// Check selected ability against the slot's ability type.
// 	// (don't equip an offensive spell in a passive slot and vice versa)
// 	const FGameplayTag& SelectedAbilityType = AbilityInfo->FindAbilityInfoForTag(SelectedAbility.Ability).AbilityType;
// 	if (!SelectedAbilityType.MatchesTagExact(AbilityType)) return;
//
// 	GetAuraASC()->ServerEquipAbility(SelectedAbility.Ability, SlotTag);
// }
//
// void USpellMenuWidgetController::OnAbilityEquipped(const FGameplayTag& AbilityTag, const FGameplayTag& Status, const FGameplayTag& Slot, const FGameplayTag& PreviousSlot)
// {
// 	bWaitingForEquipSelection = false;
//
// 	const FAuraGameplayTags& GameplayTags = FAuraGameplayTags::Get();
// 	
// 	FAuraAbilityInfo LastSlotInfo;
// 	LastSlotInfo.StatusTag = GameplayTags.Abilities_Status_Unlocked;
// 	LastSlotInfo.InputTag = PreviousSlot;
// 	LastSlotInfo.AbilityTag = GameplayTags.Abilities_None;
// 	// Broadcast empty info if PreviousSlot is a valid slot. Only if equipping an already-equipped spell
// 	AbilityInfoDelegate.Broadcast(LastSlotInfo);
//
// 	FAuraAbilityInfo Info = AbilityInfo->FindAbilityInfoForTag(AbilityTag);
// 	Info.StatusTag = Status;
// 	Info.InputTag = Slot;
// 	AbilityInfoDelegate.Broadcast(Info);
//
// 	StopWaitingForEquipDelegate.Broadcast(AbilityInfo->FindAbilityInfoForTag(AbilityTag).AbilityType);
// 	SpellGlobeReassignedDelegate.Broadcast(AbilityTag);
// 	GlobeDeselect();
// }

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
