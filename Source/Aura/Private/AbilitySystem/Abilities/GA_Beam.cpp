// Fill out your copyright notice in the Description page of Project Settings.


#include "AbilitySystem/Abilities/GA_Beam.h"

#include "Camera/CameraShakeBase.h"
#include "Camera/PlayerCameraManager.h"
#include "GameFramework/Character.h"
#include "PlayerInput/MyPlayerController2.h"

void UGA_Beam::PlayBeamHitImpact(ACharacter* HitCharacter)
{
	if (!HitCharacter) return;
	APlayerController* HitPC=Cast<APlayerController>(HitCharacter->GetController());
	if (!HitPC) return;
	
	// Hit player on this machine (listen server host, or a client calling it for itself): play it here, no RPC needed
	if (HitPC->IsLocalController())
	{
		PlayBeamHitImpactLocal(HitPC);
		return;
	}
	
	// Remote hit player: same route as damage numbers, the server tells their own controller, which plays the effect on that machine
	if (!HitCharacter->HasAuthority()) return;
	if (AMyPlayerController2* MyHitPC=Cast<AMyPlayerController2>(HitPC))
	{
		// A continuous beam calls this every frame: only send the reliable RPC once the last impact is over
		const float Now=HitCharacter->GetWorld()->GetTimeSeconds();
		if (Now-MyHitPC->LastHitImpactSentTime<FMath::Max(HitImpactMinInterval,HitImpactDuration)) return;
		MyHitPC->LastHitImpactSentTime=Now;
		MyHitPC->Client_PlayBeamImpact(GetClass(),false);
	}
	else if (HitCameraShake)
	{
		// Not the mech controller, only the shake has a built in client RPC
		HitPC->ClientStartCameraShake(HitCameraShake,HitCameraShakeScale);
	}
}

void UGA_Beam::PlayBeamHitImpactLocal(APlayerController* HitPC) const
{
	AMyPlayerController2* MyPC=Cast<AMyPlayerController2>(HitPC);
	if (!MyPC || !MyPC->IsLocalController()) return;
	
	// A continuous beam hits every frame, only start a new impact once the last one is over
	const float Now=MyPC->GetWorld()->GetTimeSeconds();
	if (Now-MyPC->LastHitImpactStartTime<FMath::Max(HitImpactMinInterval,HitImpactDuration)) return;
	MyPC->LastHitImpactStartTime=Now;
	
	MyPC->StartHitImpact(HitPostProcessMaterial,HitImpactDuration,HitFOVOffset);
	
	if (HitCameraShake && MyPC->PlayerCameraManager)
	{
		MyPC->PlayerCameraManager->StartCameraShake(HitCameraShake,HitCameraShakeScale);
	}
}

void UGA_Beam::PlayBeamCastImpact(ACharacter* CasterCharacter)
{
	if (!CasterCharacter) return;
	AMyPlayerController2* CasterPC=Cast<AMyPlayerController2>(CasterCharacter->GetController());
	if (!CasterPC) return;
	
	// Caster on this machine (client, or the listen server host): play it here, no RPC needed
	if (CasterPC->IsLocalController())
	{
		PlayBeamCastImpactLocal(CasterPC);
		return;
	}
	
	// Remote caster: only the server can reach their screen
	if (!CasterCharacter->HasAuthority()) return;
	const float Now=CasterCharacter->GetWorld()->GetTimeSeconds();
	if (Now-CasterPC->LastCastImpactSentTime<FMath::Max(CastImpactMinInterval,CastImpactDuration)) return;
	CasterPC->LastCastImpactSentTime=Now;
	CasterPC->Client_PlayBeamImpact(GetClass(),true);
}

void UGA_Beam::PlayBeamCastImpactLocal(APlayerController* CasterPC) const
{
	AMyPlayerController2* MyPC=Cast<AMyPlayerController2>(CasterPC);
	if (!MyPC || !MyPC->IsLocalController()) return;
	
	const float Now=MyPC->GetWorld()->GetTimeSeconds();
	if (Now-MyPC->LastCastImpactStartTime<FMath::Max(CastImpactMinInterval,CastImpactDuration)) return;
	MyPC->LastCastImpactStartTime=Now;
	
	MyPC->StartHitImpact(CastPostProcessMaterial,CastImpactDuration,CastFOVOffset);
	
	if (CastCameraShake && MyPC->PlayerCameraManager)
	{
		MyPC->PlayerCameraManager->StartCameraShake(CastCameraShake,CastCameraShakeScale);
	}
}

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
