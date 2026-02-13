// Fill out your copyright notice in the Description page of Project Settings.


#include "Character/GT_GetMouseDataUnderCursor.h"

#include "AbilitySystemComponent.h"
#include "Abilities/GameplayAbility.h"
#include "Kismet/KismetSystemLibrary.h"

UGT_GetMouseDataUnderCursor* UGT_GetMouseDataUnderCursor::GetMouseDataUnderCursor(UGameplayAbility* OwningAbility)
{
	UGT_GetMouseDataUnderCursor* MouseData=NewAbilityTask<UGT_GetMouseDataUnderCursor>(OwningAbility);
	return MouseData;
}

void UGT_GetMouseDataUnderCursor::Activate()
{
	bool bIsLocalllyControlled=Ability->GetCurrentActorInfo()->IsLocallyControlled();
	if (bIsLocalllyControlled)
	{
		// UKismetSystemLibrary::PrintString(GetWorld(),TEXT("Locally Controlled"));
		SendMouseCursorData();
	}
	else
	{
		AbilitySystemComponent.Get()->AbilityTargetDataSetDelegate(GetAbilitySpecHandle(),GetActivationPredictionKey()).AddUObject(this,&ThisClass::TargetDataSetCallbackOnServer);
		bool bTargetDataSent=AbilitySystemComponent.Get()->CallReplicatedTargetDataDelegatesIfSet(GetAbilitySpecHandle(),GetActivationPredictionKey());
		if (!bTargetDataSent)
		{
			SetWaitingOnRemotePlayerData();
		}
	}
}

void UGT_GetMouseDataUnderCursor::SendMouseCursorData()
{
	FScopedPredictionWindow PredictionWindow((AbilitySystemComponent.Get()));
	APlayerController* PC=Cast<APlayerController>(GetAvatarActor()->GetInstigatorController());
	FHitResult HitResult;
	PC->GetHitResultUnderCursor(ECC_Visibility,false,HitResult);
	FGameplayAbilityTargetData_SingleTargetHit* TargetData=new FGameplayAbilityTargetData_SingleTargetHit();
	FGameplayAbilityTargetDataHandle TargetDataHandle;
	TargetData->HitResult=HitResult;
	TargetDataHandle.Add(TargetData);
	// UKismetSystemLibrary::PrintString(GetWorld(),TEXT("Mouse Cursor HitResult: ") + HitResult.ToString());
	AbilitySystemComponent.Get()->ServerSetReplicatedTargetData(GetAbilitySpecHandle(),GetActivationPredictionKey(),TargetDataHandle,FGameplayTag(),AbilitySystemComponent->ScopedPredictionKey);
	
	if (ShouldBroadcastAbilityTaskDelegates())
	{
		OnHitResultTargetDataSetDelegate.Broadcast(TargetDataHandle);
	}
}

void UGT_GetMouseDataUnderCursor::TargetDataSetCallbackOnServer(const FGameplayAbilityTargetDataHandle& TargetDataHandle, FGameplayTag GameplayTag)
{
	if (ShouldBroadcastAbilityTaskDelegates())
	{
		OnHitResultTargetDataSetDelegate.Broadcast(TargetDataHandle);
	}
}
