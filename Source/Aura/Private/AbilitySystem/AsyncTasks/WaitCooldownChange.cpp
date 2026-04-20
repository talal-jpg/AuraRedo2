// Fill out your copyright notice in the Description page of Project Settings.


#include "AbilitySystem/AsyncTasks/WaitCooldownChange.h"

#include "AbilitySystemComponent.h"
#include "AbilitySystem/Data/MyGameplayTags.h"

UWaitCooldownChange* UWaitCooldownChange::WaitCooldownChange(UAbilitySystemComponent* InASC,const FGameplayTag& InCooldownTag)
{
	UWaitCooldownChange* WaitCooldownChange=NewObject<UWaitCooldownChange>();
	WaitCooldownChange->ASC=InASC;
	WaitCooldownChange->CooldownTag=InCooldownTag;
	
	if (!IsValid(InASC)|| InCooldownTag.IsValid())
	{
		WaitCooldownChange->EndTask();
		return nullptr;
	}
		
	InASC->RegisterGameplayTagEvent(InCooldownTag,EGameplayTagEventType::NewOrRemoved).AddUObject(WaitCooldownChange,&UWaitCooldownChange::OnCooldownTagChanged);
	InASC->OnActiveGameplayEffectAddedDelegateToSelf.AddUObject(WaitCooldownChange,&ThisClass::OnActiveGameplayEffectAdded);
	
	return WaitCooldownChange;
}

void UWaitCooldownChange::EndTask()
{
	
	ASC->RegisterGameplayTagEvent(CooldownTag,EGameplayTagEventType::NewOrRemoved).RemoveAll(this);
	SetReadyToDestroy();
	MarkAsGarbage();
}

void UWaitCooldownChange::OnCooldownTagChanged(const FGameplayTag InCooldownTag, int32 count)
{
	if (InCooldownTag==CooldownTag)
	{
		OnCooldownEndDelegate.Broadcast(0.f);
	}
}

void UWaitCooldownChange::OnActiveGameplayEffectAdded(UAbilitySystemComponent* ASC, const FGameplayEffectSpec& GESpec, FActiveGameplayEffectHandle ActiveGameplayEffectHandle)
{
	
	FGameplayTagContainer AssetTags;
	GESpec.GetAllAssetTags(AssetTags);
	
	FGameplayTagContainer GrantedTags;
	GESpec.GetAllGrantedTags(GrantedTags);
	
	if (AssetTags.HasTagExact(CooldownTag) || GrantedTags.HasTagExact(CooldownTag))
	{
		FGameplayEffectQuery Query= FGameplayEffectQuery::MakeQuery_MatchAnyOwningTags(CooldownTag.GetSingleTagContainer());
		// ASC->GetActiveEffectsDuration()
		
	}
	
}

