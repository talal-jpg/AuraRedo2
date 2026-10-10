// Fill out your copyright notice in the Description page of Project Settings.


#include "AbilitySystem/Abilities/GA_Boost.h"
#include "GameFramework/CharacterMovementComponent.h"


class UCharacterMovementComponent;

void UGA_Boost::ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo,
                                const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData)
{
	Super::ActivateAbility(Handle, ActorInfo, ActivationInfo, TriggerEventData);
}

bool UGA_Boost::CanActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo,
	const FGameplayTagContainer* SourceTags, const FGameplayTagContainer* TargetTags,
	FGameplayTagContainer* OptionalRelevantTags) const
{
	
	if (ActorInfo && ActorInfo->IsLocallyControlled())
	{
		const UCharacterMovementComponent* MoveComp=Cast<UCharacterMovementComponent>(ActorInfo->MovementComponent.Get());
		if (!MoveComp || MoveComp->IsFalling())return false;
	}
	
	return Super::CanActivateAbility(Handle, ActorInfo, SourceTags, TargetTags, OptionalRelevantTags);
	
}
