// Fill out your copyright notice in the Description page of Project Settings.


#include "AbilitySystem/MyAbilitySystemComponent.h"

#include "AbilitySystem/Data/MyGameplayTags.h"
#include "Kismet/KismetSystemLibrary.h"

UMyAbilitySystemComponent::UMyAbilitySystemComponent()
{
	SetIsReplicated(true);
	ReplicationMode=EGameplayEffectReplicationMode::Mixed;
}

void UMyAbilitySystemComponent::ForEachAbility(const FForEachAbilityDelegateSignature& ForEachAbilityDelegate)
{
	for (auto Ability:GetActivatableAbilities())
	{
		ForEachAbilityDelegate.ExecuteIfBound(Ability);
	}
}

FGameplayTag UMyAbilitySystemComponent::GetAbilityTagFromSpec(const FGameplayAbilitySpec& AbilitySpec)
{
	for (FGameplayTag Tag:AbilitySpec.GetDynamicSpecSourceTags())
	{
		if (Tag.MatchesTag(UGameplayTagsManager::Get().RequestGameplayTag(FName("Abilities"))))
		{
			return Tag;
		}
	}
	return FGameplayTag();
}

FGameplayTag UMyAbilitySystemComponent::GetInputTagFromSpec(const FGameplayAbilitySpec& AbilitySpec)
{
	FScopedAbilityListLock ScopedAbilityListLock= FScopedAbilityListLock(*this);
	for (FGameplayTag Tag:AbilitySpec.GetDynamicSpecSourceTags())
	{
		if (Tag.MatchesTag(UGameplayTagsManager::Get().RequestGameplayTag(FName("Input"))))
		{
			return Tag;
		}
	}
	return FGameplayTag();
}

void UMyAbilitySystemComponent::AbilityInputPressed(FGameplayTag InputTag)
{
	FScopedAbilityListLock ScopedAbilityListLock= FScopedAbilityListLock(*this);
	for (auto AbilitySpec:GetActivatableAbilities())
	{
		if (AbilitySpec.GetDynamicSpecSourceTags().HasTagExact(InputTag)){
			AbilitySpecInputPressed(AbilitySpec);
			TryActivateAbility(AbilitySpec.Handle);
			//happens auto in AbilitySpecInputPressed
			// if (AbilitySpec.IsActive())
			// {
			// 	FPredictionKey OriginalPredictionKey=AbilitySpec.Ability->GetCurrentActivationInfo().GetActivationPredictionKey();
			// 	InvokeReplicatedEvent(EAbilityGenericReplicatedEvent::InputPressed,AbilitySpec.Handle,OriginalPredictionKey,ScopedPredictionKey);
			// }
			
		}
	}
}

void UMyAbilitySystemComponent::AbilityInputHeld(FGameplayTag InputTag)
{
}

void UMyAbilitySystemComponent::AbilityInputReleased(FGameplayTag InputTag)
{
}
