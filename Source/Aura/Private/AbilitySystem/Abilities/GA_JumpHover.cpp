// Fill out your copyright notice in the Description page of Project Settings.


#include "AbilitySystem/Abilities/GA_JumpHover.h"

#include "AbilitySystemComponent.h"
#include "AbilitySystemGlobals.h"
#include "TimerManager.h"
#include "AbilitySystem/Data/MyGameplayTags.h"
#include "Character/MyCharacterMovementComponent.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"

DEFINE_LOG_CATEGORY_STATIC(LogJumpHover, Log, All);

namespace JumpHover
{
	// Server -> owning client of the same activation: out of mana, drop out of the hover
	constexpr EAbilityGenericReplicatedEvent::Type StopHoverEvent=EAbilityGenericReplicatedEvent::GameCustom1;

	// Owning client / listen host: how often it looks for the landing that ends the activation
	constexpr float LandingCheckInterval=0.05f;

	const TCHAR* ActionName(int32 Action)
	{
		static const TCHAR* Names[]={TEXT("None"),TEXT("Jump"),TEXT("AirJump"),TEXT("StartHover"),TEXT("StopHover")};
		return Action>=0 && Action<static_cast<int32>(UE_ARRAY_COUNT(Names)) ? Names[Action] : TEXT("?");
	}
}

UGA_JumpHover::UGA_JumpHover()
{
	InstancingPolicy=EGameplayAbilityInstancingPolicy::InstancedPerActor;
	NetExecutionPolicy=EGameplayAbilityNetExecutionPolicy::LocalPredicted;
}

ACharacter* UGA_JumpHover::GetCharacter() const
{
	return Cast<ACharacter>(GetAvatarActorFromActorInfo());
}

UMyCharacterMovementComponent* UGA_JumpHover::GetMovement() const
{
	const ACharacter* Character=GetCharacter();
	return Character ? Cast<UMyCharacterMovementComponent>(Character->GetCharacterMovement()) : nullptr;
}

void UGA_JumpHover::ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo,const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData)
{
	// GA_JumpHover_C's K2_ActivateAbility (does nothing)
	Super::ActivateAbility(Handle, ActorInfo, ActivationInfo, TriggerEventData);

	bHovering=false;
	bEndWhenReleased=false;
	bLeftGround=false;
	bServerStopSent=false;
	PressCount=0;
	LastGroundJumpTime=-1.0;

	UWorld* World=GetWorld();
	if (!World || !GetCharacter() || !GetMovement())
	{
		// Not a character with UMyCharacterMovementComponent (AMyCharPlayer)
		EndAbility(Handle,ActorInfo,ActivationInfo,true,true);
		return;
	}

	if (ActorInfo->IsNetAuthority())
	{
		World->GetTimerManager().SetTimer(HoverCostTimerHandle,this,&ThisClass::HoverCostTick,HoverCostInterval,true);
	}
	if (!IsLocallyControlled())
	{
		// Server copy of a remote client's activation: the jumps and the hover arrive with the client's moves, this
		// copy only charges the mana. It ends when the client ends it
		return;
	}
	if (!ActorInfo->IsNetAuthority())
	{
		if (UAbilitySystemComponent* ASC=ActorInfo->AbilitySystemComponent.Get())
		{
			ServerStopHoverHandle=ASC->AbilityReplicatedEventDelegate(JumpHover::StopHoverEvent,Handle,ActivationInfo.GetActivationPredictionKey()).AddUObject(this,&ThisClass::OnServerStopHover);
		}
	}
	World->GetTimerManager().SetTimer(LandingCheckTimerHandle,this,&ThisClass::LandingCheckTick,JumpHover::LandingCheckInterval,true);
	HandlePress();
}

void UGA_JumpHover::InputPressed(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo)
{
	Super::InputPressed(Handle, ActorInfo, ActivationInfo);
	if (!IsActive() || !IsLocallyControlled())return;
	// Waiting for a release that never came (focus lost): this press starts over
	bEndWhenReleased=false;
	HandlePress();
}

void UGA_JumpHover::InputReleased(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo)
{
	Super::InputReleased(Handle, ActorInfo, ActivationInfo);
	if (bEndWhenReleased && IsActive())
	{
		EndAbility(GetCurrentAbilitySpecHandle(),GetCurrentActorInfo(),GetCurrentActivationInfo(),true,false);
	}
}

UGA_JumpHover::EJumpHoverAction UGA_JumpHover::ChooseAction() const
{
	const ACharacter* Character=GetCharacter();
	const UMyCharacterMovementComponent* Move=GetMovement();
	if (!Character || !Move)return EJumpHoverAction::None;
	const UAbilitySystemComponent* ASC=GetAbilitySystemComponentFromActorInfo();
	if (ASC && ASC->HasMatchingGameplayTag(MyTags::State_Dead))return EJumpHoverAction::None;

	if (bHovering)return EJumpHoverAction::StopHover;
	// A root motion source owns the movement (GA_GrappleSwing2's swing): the jump flag lets go of the rope, no hover.
	// UMyCharacterMovementComponent::DoJump doesn't jump there, so the air jump is kept for after the swing
	if (Move->HasRootMotionSources())return EJumpHoverAction::Jump;
	if (Move->IsMovingOnGround())return EJumpHoverAction::Jump;
	if (Move->IsFalling())
	{
		// JumpMaxCount 2: in the air CanJump() is true while the air jump is left (also when falling without a jump)
		if (Character->CanJump())return EJumpHoverAction::AirJump;
		return CanPayHoverCost() ? EJumpHoverAction::StartHover : EJumpHoverAction::None;
	}
	// Flying for another reason (GA_BoostBP), swimming...
	return EJumpHoverAction::None;
}

void UGA_JumpHover::HandlePress()
{
	ACharacter* Character=GetCharacter();
	UMyCharacterMovementComponent* Move=GetMovement();
	if (!Character || !Move)return;
	++PressCount;

	const EJumpHoverAction Action=ChooseAction();
	UE_LOG(LogJumpHover,Verbose,TEXT("%s %s press %d: %s (mode %d, jump count %d/%d)"),*GetNameSafe(Character),
		CurrentActorInfo && CurrentActorInfo->IsNetAuthority() ? TEXT("host") : TEXT("client"),PressCount,
		JumpHover::ActionName(static_cast<int32>(Action)),static_cast<int32>(Move->MovementMode.GetValue()),Character->JumpCurrentCount,Character->JumpMaxCount);

	switch (Action)
	{
	case EJumpHoverAction::Jump:
	case EJumpHoverAction::AirJump:
		// Through the move stream: the server simulates the same jump on the same move, and the air jump's turn
		// toward the input happens in UMyCharacterMovementComponent on both
		if (Move->IsMovingOnGround())
		{
			LastGroundJumpTime=GetWorld()->GetTimeSeconds();
		}
		Character->Jump();
		break;
	case EJumpHoverAction::StartHover:
		SetHover(true);
		break;
	case EJumpHoverAction::StopHover:
		SetHover(false);
		break;
	case EJumpHoverAction::None:
	default:
		// Nothing to do on activation (dead, out of mana, flying by another ability): end, once the button is up
		if (PressCount==1)
		{
			FinishWhenReleased();
		}
		break;
	}
}

void UGA_JumpHover::SetHover(bool bOn)
{
	bHovering=bOn;
	if (UMyCharacterMovementComponent* Move=GetMovement())
	{
		Move->SetHoverRequest(bOn);
	}
}

bool UGA_JumpHover::CheckCost(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, FGameplayTagContainer* OptionalRelevantTags) const
{
	return true;
}

bool UGA_JumpHover::CanPayHoverCost() const
{
	if (UAbilitySystemGlobals::Get().ShouldIgnoreCosts())return true;
	if (!CurrentActorInfo || !CurrentActorInfo->AbilitySystemComponent.IsValid())return false;
	return Super::CheckCost(GetCurrentAbilitySpecHandle(),GetCurrentActorInfo(),nullptr);
}

void UGA_JumpHover::HoverCostTick()
{
	const UMyCharacterMovementComponent* Move=GetMovement();
	UAbilitySystemComponent* ASC=GetAbilitySystemComponentFromActorInfo();
	if (!IsActive() || !Move || !ASC)return;

	const bool bInHover=Move->IsHovering();
	if (!IsLocallyControlled())
	{
		bHovering=bInHover;
	}
	if (!bInHover)
	{
		bServerStopSent=false;
		return;
	}
	// GA_BoostBP pays for its own flight
	if (ASC->HasMatchingGameplayTag(MyTags::State_Boosting) || bServerStopSent)return;

	if (!CanPayHoverCost())
	{
		if (!bEndHoverWhenOutOfMana)return;
		UE_LOG(LogJumpHover,Log,TEXT("%s: out of mana, the hover ends"),*GetNameSafe(GetCharacter()));
		if (IsLocallyControlled())
		{
			// Listen server host
			SetHover(false);
		}
		else
		{
			// The hover is the client's wish in its moves: the client has to drop it
			bServerStopSent=true;
			ASC->ClientSetReplicatedEvent(JumpHover::StopHoverEvent,GetCurrentAbilitySpecHandle(),GetCurrentActivationInfo().GetActivationPredictionKey());
		}
		return;
	}
	ApplyCost(GetCurrentAbilitySpecHandle(),GetCurrentActorInfo(),GetCurrentActivationInfo());
}

void UGA_JumpHover::OnServerStopHover()
{
	if (UAbilitySystemComponent* ASC=GetAbilitySystemComponentFromActorInfo())
	{
		ASC->ConsumeGenericReplicatedEvent(JumpHover::StopHoverEvent,GetCurrentAbilitySpecHandle(),GetCurrentActivationInfo().GetActivationPredictionKey());
	}
	UE_LOG(LogJumpHover,Verbose,TEXT("%s client: the server is out of mana for the hover"),*GetNameSafe(GetCharacter()));
	if (IsActive() && bHovering)
	{
		SetHover(false);
	}
}

void UGA_JumpHover::LandingCheckTick()
{
	// A timer runs after the movement tick, so a correction's replay is already done: only real landings count here
	const UMyCharacterMovementComponent* Move=GetMovement();
	if (!IsActive() || !Move)return;
	if (!Move->IsMovingOnGround())
	{
		bLeftGround=true;
		return;
	}
	if (bHovering)
	{
		// Put on the ground by something else (GA_BoostBP ending on the ground): the hover is over
		SetHover(false);
	}
	// Right after a ground jump the jump may not have been simulated yet: give it GroundJumpCheckDelay
	if (bLeftGround || LastGroundJumpTime<0.0 || GetWorld()->GetTimeSeconds()-LastGroundJumpTime>=GroundJumpCheckDelay)
	{
		// Landed: the air jump is back (ACharacter::ResetJumpState), this activation is done
		FinishWhenReleased();
	}
}

void UGA_JumpHover::FinishWhenReleased()
{
	if (!IsActive() || bEndWhenReleased)return;
	const FGameplayAbilitySpec* Spec=GetCurrentAbilitySpec();
	if (Spec && Spec->InputPressed)
	{
		// Still held: ending now would let the held button activate it again (a jump every landing)
		bEndWhenReleased=true;
		return;
	}
	EndAbility(GetCurrentAbilitySpecHandle(),GetCurrentActorInfo(),GetCurrentActivationInfo(),true,false);
}

void UGA_JumpHover::EndAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo,const FGameplayAbilityActivationInfo ActivationInfo, bool bReplicateEndAbility, bool bWasCancelled)
{
	const bool bLocal=ActorInfo && ActorInfo->IsLocallyControlled();
	UE_LOG(LogJumpHover,Verbose,TEXT("%s %s end (presses %d, hovering %d, cancelled %d)"),*GetNameSafe(GetCharacter()),
		!bLocal ? TEXT("server") : (ActorInfo->IsNetAuthority() ? TEXT("host") : TEXT("client")),PressCount,bHovering ? 1 : 0,bWasCancelled ? 1 : 0);

	if (UWorld* World=GetWorld())
	{
		World->GetTimerManager().ClearTimer(HoverCostTimerHandle);
		World->GetTimerManager().ClearTimer(LandingCheckTimerHandle);
	}
	// Owning client / host: drop out of the hover (the server follows through the moves)
	if (bLocal)
	{
		SetHover(false);
	}
	bHovering=false;
	bEndWhenReleased=false;

	if (ServerStopHoverHandle.IsValid())
	{
		if (UAbilitySystemComponent* ASC=ActorInfo ? ActorInfo->AbilitySystemComponent.Get() : nullptr)
		{
			ASC->AbilityReplicatedEventDelegate(JumpHover::StopHoverEvent,Handle,ActivationInfo.GetActivationPredictionKey()).Remove(ServerStopHoverHandle);
		}
		ServerStopHoverHandle.Reset();
	}

	Super::EndAbility(Handle, ActorInfo, ActivationInfo, bReplicateEndAbility, bWasCancelled);
}
