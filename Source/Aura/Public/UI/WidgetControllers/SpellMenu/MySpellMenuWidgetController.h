// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameplayTagContainer.h"
#include "MyPlayerState.h"
#include "AbilitySystem/Data/MyGameplayTags.h"
#include "UI/WidgetControllers/MyWidgetController.h"
#include "MySpellMenuWidgetController.generated.h"

struct FSelectedAbility
{
	FGameplayTag Ability = FGameplayTag();
	FGameplayTag Status = FGameplayTag();
};

DECLARE_DYNAMIC_MULTICAST_DELEGATE_FourParams(FSpellGlobeSelectedSignature, bool, bSpendPointsButtonEnabled, bool, bEquipButtonEnabled, FString, DescriptionString, FString, NextLevelDescriptionString);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FWaitForEquipSelectionSignature, const FGameplayTag&, AbilityType);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FSpellGlobeReassignedSignature, const FGameplayTag&, AbilityTag);

/**
 * 
 */
UCLASS(BlueprintType, Blueprintable)
class AURA_API UMySpellMenuWidgetController : public UMyWidgetController
{
	GENERATED_BODY()

public:
	virtual void BroadcastInitialValues() override;
	virtual void BindCallbacksToDependencies() override;

	UPROPERTY(BlueprintAssignable)
	FOnPlayerStatChangedDelegateSignature SpellPointsChanged;

	UPROPERTY(BlueprintAssignable)
	FSpellGlobeSelectedSignature SpellGlobeSelectedDelegate;

	UPROPERTY(BlueprintAssignable)
	FWaitForEquipSelectionSignature WaitForEquipDelegate;

	UPROPERTY(BlueprintAssignable)
	FWaitForEquipSelectionSignature StopWaitingForEquipDelegate;

	UPROPERTY(BlueprintAssignable)
	FSpellGlobeReassignedSignature SpellGlobeReassignedDelegate;

	UFUNCTION(BlueprintCallable)
	void SpellGlobeSelected(const FGameplayTag& AbilityTag);

	UFUNCTION(BlueprintCallable)
	void SpendPointButtonPressed();
	//
	UFUNCTION(BlueprintCallable)
	void GlobeDeselect();
	//
	UFUNCTION(BlueprintCallable)
	void EquipButtonPressed();
	//
	UFUNCTION(BlueprintCallable)
	void SpellRowGlobePressed(const FGameplayTag& SlotTag, const FGameplayTag& AbilityType);
	
	void OnAbilityEquipped(const FGameplayTag& AbilityTag, const FGameplayTag& Slot);

private:
	
	static void ShouldEnableButtons(const FGameplayTag& AbilityStatus, int32 SpellPoints, bool& bShouldEnableSpellPointsButton, bool& bShouldEnableEquipButton);
	FSelectedAbility SelectedAbility = { MyTags::Ability_None,MyTags::Ability_Status_Locked};
	int32 CurrentSpellPoints = 0;
	bool bWaitingForEquipSelection = false;
	FGameplayTag SelectedSlot;

};
