// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameplayTagContainer.h"
#include "AbilitySystem/Data/MyGameplayTags.h"
#include "UI/WidgetControllers/MyWidgetController.h"
#include "MySpellMenuWidgetController.generated.h"

struct FGameplayTag;
/**
 * 
 */
USTRUCT()
struct FSelectedAbility
{
	GENERATED_BODY()
	
	FGameplayTag AbilityTag=MyTags::Ability_None;
	FGameplayTag InputTag=MyTags::Input_None;
	FGameplayTag StatusTag=MyTags::Ability_Status_Unlocked;
	
};


DECLARE_DYNAMIC_MULTICAST_DELEGATE_ThreeParams(FOnSpellGlobeClickedBroadCastShouldEnableDelegateSignature, bool, bEnableEquip,bool , bEnableSpendSpellPoint, FString,SpellDescription);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FSpellGlobeDeselectDelegateSignature,FGameplayTag, AbilityTag);

UCLASS(Blueprintable)
class AURA_API UMySpellMenuWidgetController : public UMyWidgetController
{
	GENERATED_BODY()
	
	public:
	
	UFUNCTION(BlueprintCallable)
	void SpellGlobeClicked(FGameplayTag InAbilityTag);
	
	UFUNCTION(BlueprintCallable)
	void EquipButtonPressed();
	
	UFUNCTION(BlueprintCallable)
	void EquippedRowPressed(FGameplayTag InInputTag);
	
	UFUNCTION(BlueprintCallable)
	void SpendSpellPointButtonPressed();
	
	bool bWaitingForEquippedRowPress=false;
	
	FSelectedAbility SelectedAbility;
	
	UPROPERTY(BlueprintAssignable)
	FOnSpellGlobeClickedBroadCastShouldEnableDelegateSignature OnSpellGlobeClickedBroadCastShouldEnableDelegate;
	
	UPROPERTY(BlueprintAssignable)
	FSpellGlobeDeselectDelegateSignature SpellGlobeDeselectDelegate;
	
	virtual void BroadcastInitialValues() override;
	
	virtual void BindCallbacksToDependencies() override;
	
	UPROPERTY(EditAnywhere)
	UDA_MyAbilityInfo* MyAbilityInfo;
	
	
};
