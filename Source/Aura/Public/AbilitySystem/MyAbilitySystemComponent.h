// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "AbilitySystemComponent.h"
#include "UI/WidgetControllers/Overlay/MyOverlayWidgetController.h"
#include "MyAbilitySystemComponent.generated.h"

DECLARE_MULTICAST_DELEGATE(FOnAbilitiesGivenDelegateSignature)
DECLARE_MULTICAST_DELEGATE_FourParams(FOnAbilityEquippedDelegateSiganature, FGameplayTag/*AbilityTag*/, FGameplayTag /*StatusTag*/,FGameplayTag /*InputTag*/,FGameplayTag /*PrevInputTag*/);
DECLARE_DELEGATE_ThreeParams(FOnAbilityStatusChangedDelegateSignature,FGameplayTag,FGameplayTag,int32);

/**
 * 
 */
UCLASS()
class AURA_API UMyAbilitySystemComponent : public UAbilitySystemComponent
{
	GENERATED_BODY()
	
	public:
	UMyAbilitySystemComponent();
	
	void ForEachAbility(const FForEachAbilityDelegateSignature& ForEachAbilityDelegate);
	
	bool bAbilitiesGiven=false;
	
	// Delegates
	FOnAbilitiesGivenDelegateSignature OnAbilitiesGivenDelegate;
	FOnAbilityEquippedDelegateSiganature OnAbilityEquippedDelegate;
	FOnAbilityStatusChangedDelegateSignature OnAbilityStatusChangedDelegate;
	
	// utilityFuncs
	FGameplayTag GetStatusFromAbiltyTag(FGameplayTag AbilityTag);
	
	FGameplayTag GetAbilityTagFromSpec(const FGameplayAbilitySpec& AbilitySpec);
	
	FGameplayAbilitySpec* GetAbilitySpecFromTag(FGameplayTag AbilityTag);
	
	FGameplayAbilitySpec* GetAbilitySpecFromSlotTag(FGameplayTag InSlotTag);
	
	FGameplayTag GetInputTagFromSpec(const FGameplayAbilitySpec& AbilitySpec);
	
	FGameplayTag GetStatusTagFromSpec(const FGameplayAbilitySpec& AbilitySpec);
	
	
	
	
	void AbilityInputPressed(FGameplayTag InputTag);
	
	void AbilityInputHeld(FGameplayTag InputTag);
	
	void AbilityInputReleased(FGameplayTag InputTag);
	
	void UpgradeAttribute(FGameplayTag AttribTag);
	
	UFUNCTION(Server,Reliable)
	void Server_EquipAbility(FGameplayTag AbilityTag,FGameplayTag NewInputTag,FGameplayTag CurrentInputTag);
	
	UFUNCTION(Client,Reliable)
	void Client_EquipAbility(FGameplayTag AbilityTag,FGameplayTag InputTag, FGameplayTag StatusTag,FGameplayTag PrevInputTag);
	
	UFUNCTION(Server,Reliable)
	void Server_SpendSpellPoint(FGameplayTag AbilityTag,FGameplayTag StatusTag);
	
	UFUNCTION(Client,Reliable)
	void Client_UpdateAbilityStatus(FGameplayTag AbilityTag,FGameplayTag StatusTag,int32 AbilityLevel);
	
	UFUNCTION(Server,Reliable)
	void Server_UpgradeAttribute(FGameplayTag AttribTag);
	
};
