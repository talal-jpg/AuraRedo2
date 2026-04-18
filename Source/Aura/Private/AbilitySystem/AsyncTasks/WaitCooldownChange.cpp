// Fill out your copyright notice in the Description page of Project Settings.


#include "AbilitySystem/AsyncTasks/WaitCooldownChange.h"

#include "AbilitySystemComponent.h"

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
		
	
	return WaitCooldownChange;
}

void UWaitCooldownChange::EndTask()
{
}
