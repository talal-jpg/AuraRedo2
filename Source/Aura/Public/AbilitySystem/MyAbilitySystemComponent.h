// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "AbilitySystemComponent.h"
#include "GameplayAbilitySpec.h"
#include "UI/WidgetControllers/Overlay/MyOverlayWidgetController.h"
#include "MyAbilitySystemComponent.generated.h"

DECLARE_MULTICAST_DELEGATE(FOnAbilitiesGivenDelegateSignature)
DECLARE_MULTICAST_DELEGATE_ThreeParams(FAbilityStatusChangedDelegateSignature, const FGameplayTag& /*AbilityTag*/, const FGameplayTag& /*StatusTag*/, int32 /*AbilityLevel*/);
DECLARE_MULTICAST_DELEGATE_TwoParams(FAbilityEquipChangedDelegateSignature, const FGameplayTag& /*AbilityTag*/, const FGameplayTag& /*InputTag*/);


/**
 * 
 */
UCLASS()
class AURA_API UMyAbilitySystemComponent : public UAbilitySystemComponent
{
	GENERATED_BODY()
	
	public:
	
	FAbilityStatusChangedDelegateSignature AbilityStatusChangedDelegate;
	
	FAbilityEquipChangedDelegateSignature AbilityEquipChangedDelegate;
	
	UMyAbilitySystemComponent();
	
	void ForEachAbility(const FForEachAbilityDelegateSignature& ForEachAbilityDelegate);
	
	bool bAbilitiesGiven=false;
	
	FOnAbilitiesGivenDelegateSignature OnAbilitiesGivenDelegate;
	
	FGameplayTag GetAbilityTagFromSpec(const FGameplayAbilitySpec& AbilitySpec);
	
	FGameplayTag GetInputTagFromSpec(const FGameplayAbilitySpec& AbilitySpec);
	
	FGameplayTag GetStatusTagFromSpec(const FGameplayAbilitySpec& AbilitySpec);
	
	FGameplayAbilitySpec* GetAbilitySpecFromTag(FGameplayTag AbilityTag);
	
	void GetDescriptionsByAbilityTag(FGameplayTag AbilityTag,FString& Description,FString& NextLevelDescription);
	
	
	// 
	void UpdateAbilityStatuses(int32 InPlayerLevel);
	
	UFUNCTION(BlueprintCallable,Category="AbilitySystem")
	
	void AbilityInputPressed(FGameplayTag InputTag);
	
	void AbilityInputHeld(FGameplayTag InputTag);
	
	void AbilityInputReleased(FGameplayTag InputTag);
	
	UFUNCTION(Server,Reliable)
	void ServerUpgradeAttribute(FGameplayTag AttributeTag);
	
	UFUNCTION(Server,Reliable)
	void ServerSpendSpellPoints(FGameplayTag AbilityTag);
	
	UFUNCTION(Server,Reliable)
	void ServerEquipAbility(FGameplayTag AbilityTag,FGameplayTag SlotTag);
	
	UFUNCTION(Client,Reliable)
	void ClientUpdateAbilityStatus(FGameplayTag AbilityTag,FGameplayTag StatusTag,int32 AbilityLevel);
	
	UFUNCTION(Client,Reliable)
	void ClientUpdateAbilityEquip(FGameplayTag AbilityTag,FGameplayTag SlotTag);
	
	void AddStartupAbilities(TArray<TSubclassOf<UGameplayAbility>> StartupAbilities);
	
	virtual void OnRep_ActivateAbilities() override;
	
	TMap<FGameplayAbilitySpec*,FGameplayTagContainer> AbilitySpecToTags;
	
	FGameplayTag GetStatusTagFromAbilityTag(const FGameplayTag& AbilityTag);
	FGameplayTag GetSlotFromAbilityTag(const FGameplayTag& AbilityTag);
	FGameplayAbilitySpec* GetAbilitySpecFromSlot(const FGameplayTag& SlotTag);
	
	bool IsSlotEmpty(FGameplayTag SlotTag);
	
	
};
