// Fill out your copyright notice in the Description page of Project Settings.


#include "AbilitySystem/Data/GA_HitReact.h"
#include "Abilities/Tasks/AbilityTask_WaitGameplayEvent.h"
#include "Abilities/Tasks/AbilityTask_PlayMontageAndWait.h"

#include "AbilitySystem/Data/MyGameplayTags.h"

void UGA_HitReact::ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData)
{
	Super::ActivateAbility(Handle, ActorInfo, ActivationInfo, TriggerEventData);
	if (UAbilityTask_WaitGameplayEvent::WaitGameplayEvent(this,MyTags::Event_HitReact))
	{
		UAbilityTask_PlayMontageAndWait* AT_PlayeMontageAndWait=UAbilityTask_PlayMontageAndWait::CreatePlayMontageAndWaitProxy(this,FName("None"),HitReactMontage);
		
		AT_PlayeMontageAndWait->OnCompleted.AddDynamic(this,&ThisClass::OnCompletedCallback);
		AT_PlayeMontageAndWait->Activate();
		AT_PlayeMontageAndWait->OnCancelled.AddDynamic(this,&ThisClass::OnCompletedCallback);
		AT_PlayeMontageAndWait->OnInterrupted.AddDynamic(this,&ThisClass::OnCompletedCallback);
	}
}

void UGA_HitReact::OnCompletedCallback()
{
	EndAbility(CurrentSpecHandle,CurrentActorInfo,CurrentActivationInfo,false,false);
}

