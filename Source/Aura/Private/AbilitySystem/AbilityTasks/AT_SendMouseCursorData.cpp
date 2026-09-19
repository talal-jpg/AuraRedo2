// Fill out your copyright notice in the Description page of Project Settings.


#include "AbilitySystem/AbilityTasks/AT_SendMouseCursorData.h"
#include "AbilitySystemComponent.h"
#include "Character/MyCharPlayer.h"
#include "GameFramework/GameSession.h"
#include "PlayerInput/MyPlayerController2.h"

UAT_SendMouseCursorData* UAT_SendMouseCursorData::GetSendMouseCursorDataTaskInstance(UGameplayAbility* OwningAbility)
{
	return NewAbilityTask<UAT_SendMouseCursorData>(OwningAbility);
}

void UAT_SendMouseCursorData::Activate()
{
	Super::Activate();
	bool bIsLocalController= GetAvatarActor()->GetInstigatorController()->IsLocalController();
	if (bIsLocalController)
	{
		FScopedPredictionWindow PredictionWindow= FScopedPredictionWindow(AbilitySystemComponent.Get());
		AMyPlayerController2* PC=Cast<AMyPlayerController2>(GetAvatarActor()->GetInstigatorController());
		// AMyCharPlayer* MyCharPlayer=Cast<AMyCharPlayer>(GetAvatarActor());
		// if (!PC)return;
		FHitResult HitResult = PC->HitResultLineTrace;
		FGameplayAbilityTargetData_SingleTargetHit* TargetData_SingleHit=new FGameplayAbilityTargetData_SingleTargetHit();
		TargetData_SingleHit->HitResult=HitResult;
		FGameplayAbilityTargetDataHandle TargetDataHandle;
		TargetDataHandle.Add(TargetData_SingleHit);
		AbilitySystemComponent.Get()->ServerSetReplicatedTargetData(GetAbilitySpecHandle(),GetActivationPredictionKey(),TargetDataHandle,FGameplayTag(),AbilitySystemComponent->ScopedPredictionKey);
		AbilitySystemComponent->ConsumeClientReplicatedTargetData(GetAbilitySpecHandle(),GetActivationPredictionKey());
		
		if (ShouldBroadcastAbilityTaskDelegates())
		{
			OnReplicatedDataSetSendMouseCursorDataDelegate.Broadcast(TargetDataHandle);
		}
	}
	else if (!bIsLocalController)
	{
		AbilitySystemComponent.Get()->AbilityTargetDataSetDelegate(GetAbilitySpecHandle(),GetActivationPredictionKey()).AddUObject(this,&ThisClass::OnTargetDataSetBroadcastMouseCursorDataDelegateCallback);
		bool bIsCalled=AbilitySystemComponent.Get()->CallReplicatedTargetDataDelegatesIfSet(GetAbilitySpecHandle(),GetActivationPredictionKey());
		if (!bIsCalled)
		{
			SetWaitingOnRemotePlayerData();
		}
	}
}

void UAT_SendMouseCursorData::OnTargetDataSetBroadcastMouseCursorDataDelegateCallback(
	const FGameplayAbilityTargetDataHandle& TargetDataHandle, FGameplayTag GameplayTag)
{

	if (ShouldBroadcastAbilityTaskDelegates())
	{
		OnReplicatedDataSetSendMouseCursorDataDelegate.Broadcast(TargetDataHandle);
	}
	
	AbilitySystemComponent->ConsumeClientReplicatedTargetData(
		GetAbilitySpecHandle(),
		GetActivationPredictionKey());

	EndTask();
}

void UAT_SendMouseCursorData::OnDestroy(bool bInOwnerFinished)
{
	if (AbilitySystemComponent.Get())
	{
		AbilitySystemComponent
			->AbilityTargetDataSetDelegate(
				GetAbilitySpecHandle(),
				GetActivationPredictionKey())
			.RemoveAll(this);
	}

	Super::OnDestroy(bInOwnerFinished);
}
