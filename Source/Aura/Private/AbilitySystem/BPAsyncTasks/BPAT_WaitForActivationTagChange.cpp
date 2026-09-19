// Fill out your copyright notice in the Description page of Project Settings.


#include "AbilitySystem/BPAsyncTasks/BPAT_WaitForActivationTagChange.h"

#include "AbilitySystemComponent.h"
#include "GameplayTagContainer.h"
#include "AbilitySystem/Data/MyGameplayTags.h"

UBPAT_WaitForActivationTagChange* UBPAT_WaitForActivationTagChange::Get_BPAT_WaitForActivationTagChange(UAbilitySystemComponent* InASC, FGameplayTag InActivationTag)
{
	UBPAT_WaitForActivationTagChange* WaitForActivationTagChange=NewObject<UBPAT_WaitForActivationTagChange>();
	if (!IsValid(InASC) || !InActivationTag.IsValid())
	{
		WaitForActivationTagChange->EndTask();
		return nullptr;
	}
	WaitForActivationTagChange->ActivationTag=InActivationTag;
	WaitForActivationTagChange->ASC=InASC;
	
	InASC->RegisterGameplayTagEvent(InActivationTag,EGameplayTagEventType::NewOrRemoved).AddUObject(WaitForActivationTagChange,&UBPAT_WaitForActivationTagChange::OnActivationTagChangeCallback);
	
	return WaitForActivationTagChange;
}

void UBPAT_WaitForActivationTagChange::EndTask()
{
	if (!IsValid(ASC))return;
	ASC->RegisterGameplayTagEvent(ActivationTag,EGameplayTagEventType::NewOrRemoved).RemoveAll(this);
	// bool Removed=ASC->OnActiveGameplayEffectAddedDelegateToSelf.Remove(ActiveGEAddedDelegateHandle);
	SetReadyToDestroy();
	MarkAsGarbage();
}

void UBPAT_WaitForActivationTagChange::OnActivationTagChangeCallback(const FGameplayTag Tag, int32 TagCount)
{
	OnActivationTagCountChangedDelegate.Broadcast(TagCount);
}
