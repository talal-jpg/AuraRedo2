// Fill out your copyright notice in the Description page of Project Settings.


#include "AbilitySystem/Abilities/GA_Roll.h"

#include "Abilities/Tasks/AbilityTask_PlayMontageAndWait.h"
#include "Components/SkeletalMeshComponent.h"
#include "Kismet/KismetSystemLibrary.h"

void UGA_Roll::ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo,
                               const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData)
{
	Super::ActivateAbility(Handle, ActorInfo, ActivationInfo, TriggerEventData);
	
	// UKismetSystemLibrary::PrintString(
	// 	this,
	// 	FString::Printf(
	// 		TEXT("[%.3f] %s Role=%d Current=%s Pos=%.3f"),
	// 		GetWorld()->GetTimeSeconds(),
	// 		*GetNameSafe(GetAvatarActorFromActorInfo()),
	// 		(int32)GetAvatarActorFromActorInfo()->GetLocalRole(),
	// 		*GetNameSafe(Anim ? Anim->GetCurrentActiveMontage() : nullptr),
	// 		Anim && Anim->GetCurrentActiveMontage() ? Anim->Montage_GetPosition(Anim->GetCurrentActiveMontage()) : 0.f
	// 	),
	// 	true,   // to screen
	// 	true,   // to log
	// 	FLinearColor::Yellow,
	// 	40.f
	// );	
		UAbilityTask_PlayMontageAndWait* AT_PlayMontageAndWait=UAbilityTask_PlayMontageAndWait::CreatePlayMontageAndWaitProxy(this,FName("None"),RollMontage,.1,FName("roll"));
		AT_PlayMontageAndWait->OnCompleted.AddDynamic(this,&ThisClass::OnCompletedCallback);
		AT_PlayMontageAndWait->OnCancelled.AddDynamic(this,&ThisClass::OnCompletedCallback);
		AT_PlayMontageAndWait->OnInterrupted.AddDynamic(this,&ThisClass::OnCompletedCallback);
		// AT_PlayMontageAndWait->Activate();
		AT_PlayMontageAndWait->ReadyForActivation();
	// CommitAbility(GetCurrentAbilitySpecHandle(),GetCurrentActorInfo(),GetCurrentActivationInfo());
}

void UGA_Roll::OnCompletedCallback()
{
	EndAbility(CurrentSpecHandle,CurrentActorInfo,CurrentActivationInfo,false,false);
}
