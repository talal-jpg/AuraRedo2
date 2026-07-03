// Fill out your copyright notice in the Description page of Project Settings.


#include "AbilitySystem/Abilities/GA_JumpHover.h"

#include "TimerManager.h"
#include "Abilities/Tasks/AbilityTask_WaitInputRelease.h"
#include "Abilities/Tasks/AbilityTask_WaitInputPress.h"

#include "UnrealClient.h"
#include "Character/MyCharBase.h"
#include "Engine/World.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Kismet/KismetSystemLibrary.h"

void UGA_JumpHover::ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo,const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData)
{
	Super::ActivateAbility(Handle, ActorInfo, ActivationInfo, TriggerEventData);
	
	UAbilityTask_WaitInputRelease* WaitReleaseTask =UAbilityTask_WaitInputRelease::WaitInputRelease(this, false);
	WaitReleaseTask->OnRelease.AddDynamic(this, &ThisClass::OnInputReleased);
	WaitReleaseTask->ReadyForActivation();
	
	UAbilityTask_WaitInputPress* WaitPressTask =UAbilityTask_WaitInputPress::WaitInputPress(this, false);
	WaitPressTask->OnPress.AddDynamic(this, &ThisClass::OnInputPressed);
	WaitPressTask->ReadyForActivation();
	
	AMyCharBase* CharBase=Cast<AMyCharBase>(GetAvatarActorFromActorInfo());
	CharacterMovementComponent=Cast<UCharacterMovementComponent>(CharBase->GetMovementComponent());
	if (CharBase->CanJump())
	{
		//Jump
		CharBase->Jump();
		FTimerHandle TimerHandle;
		GetWorld()->GetTimerManager().SetTimer(TimerHandle,this,&UGA_JumpHover::PrepareAndEndAbility,.2,false,-1);
	}
	else
	{
		// HoverState
		CharacterMovementComponent->SetMovementMode(EMovementMode::MOVE_Flying);
		GetWorld()->GetTimerManager().SetTimer(HoverTimerHandle, this, &ThisClass::ActivateHoverState, .1f, true);
	}
}

void UGA_JumpHover::OnInputPressed(float TimeWaited)
{
	UKismetSystemLibrary::PrintString(this,TEXT("InputPressedAgain"));
	CharacterMovementComponent->SetMovementMode(EMovementMode::MOVE_Falling);
	FTimerHandle TimerHandle;
	GetWorld()->GetTimerManager().SetTimer(TimerHandle,this,&UGA_JumpHover::PrepareAndEndAbility,.2,false,-1);
}

void UGA_JumpHover::OnInputReleased(float TimeHeld)
{
	// UKismetSystemLibrary::PrintString(this,TEXT("InputReleased"));
}

void UGA_JumpHover::ActivateHoverState()
{
	CommitAbility(GetCurrentAbilitySpecHandle(),GetCurrentActorInfo(),GetCurrentActivationInfo());
}

void UGA_JumpHover::PrepareAndEndAbility()
{
	EndAbility(GetCurrentAbilitySpecHandle(), GetCurrentActorInfo(), GetCurrentActivationInfo(), false, false);
}

void UGA_JumpHover::EndAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo,const FGameplayAbilityActivationInfo ActivationInfo, bool bReplicateEndAbility, bool bWasCancelled)
{
	Super::EndAbility(Handle, ActorInfo, ActivationInfo, bReplicateEndAbility, bWasCancelled);
}
