// // Fill out your copyright notice in the Description page of Project Settings.
//
//
// #include "AbilitySystem/Abilities/GA_Beam.h"
//
// #include "AudioMixerBlueprintLibrary.h"
// #include "MyAnimInstance.h"
// #include "Abilities/Tasks/AbilityTask_PlayMontageAndWait.h"
// #include "Abilities/Tasks/AbilityTask_WaitInputRelease.h"
// #include "Character/MyCharPlayer.h"
// #include "Engine/World.h"
// #include "GameFramework/GameStateBase.h"
//
// void UGA_Beam::ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo,
//                                const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData)
// {
// 	Super::ActivateAbility(Handle, ActorInfo, ActivationInfo, TriggerEventData);
// 	
// 	UAbilityTask_PlayMontageAndWait* AT_PlayMontageAndWait=UAbilityTask_PlayMontageAndWait::CreatePlayMontageAndWaitProxy(this,FName("foo"),BeamAbilityMontageCharge,1,FName("Default"));
// 	AT_PlayMontageAndWait->Activate();
// 	UAbilityTask_WaitInputRelease* WaitReleaseTask=UAbilityTask_WaitInputRelease::WaitInputRelease(this,false);
// 	WaitReleaseTask->OnRelease.AddDynamic(this,&ThisClass::OnInputReleasedCallback);
// 	WaitReleaseTask->ReadyForActivation();
// }
//
// void UGA_Beam::OnInputReleasedCallback(float TimeHeld)
// {
// 	UAbilityTask_PlayMontageAndWait* AT_PlayMontageAndWait=UAbilityTask_PlayMontageAndWait::CreatePlayMontageAndWaitProxy(this,FName("foo"),BeamAbilityMontageRelease,1,FName("Release"));
// 	if (GetOwningActorFromActorInfo()->HasAuthority())
// 	{
// 		float TimeStamp= GetWorld()->GetGameState()->GetServerWorldTimeSeconds();
// 		float Duration=TimeHeld;
// 		Cast<AMyCharPlayer>(GetAvatarActorFromActorInfo())->Multicast_SetPhysicsState(TimeStamp,Duration);
// 	}
// 	AT_PlayMontageAndWait->OnCompleted.AddDynamic(this,&ThisClass::OnReleaseMontageCompleteCallback);
// 	AT_PlayMontageAndWait->ReadyForActivation();
// }
//
// void UGA_Beam::OnReleaseMontageCompleteCallback()
// {
// 	EndAbility(CurrentSpecHandle,CurrentActorInfo,CurrentActivationInfo,false,false);
// }
