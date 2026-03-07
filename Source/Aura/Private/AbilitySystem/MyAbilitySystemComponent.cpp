// Fill out your copyright notice in the Description page of Project Settings.


#include "AbilitySystem/MyAbilitySystemComponent.h"

#include "AbilitySystemBlueprintLibrary.h"
#include "AbilitySystem/Abilities/MyGameplayAbility.h"
#include "AbilitySystem/Data/MyGameplayTags.h"
#include "Character/MyPlayerInterface.h"
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

FGameplayTag UMyAbilitySystemComponent::GetStatusTagFromSpec(const FGameplayAbilitySpec& AbilitySpec)
{
	FScopedAbilityListLock ScopedAbilityListLock= FScopedAbilityListLock(*this);
	for (FGameplayTag Tag:AbilitySpec.GetDynamicSpecSourceTags())
	{
		//Requesting Parent of Ability.Status.Equipped = Ability.Status
		if (Tag.MatchesTag(MyTags::Ability_Status_Equipped.GetTag().RequestDirectParent()))
		{
			return Tag;
		}
	}
	return FGameplayTag();
}

FGameplayAbilitySpec UMyAbilitySystemComponent::GetAbilitySpecFromTag(FGameplayTag AbilityTag)
{
	FScopedAbilityListLock ScopedAbilityListLock= FScopedAbilityListLock(*this);
	for (auto AbilitySpec:GetActivatableAbilities())
	{
		if (AbilitySpec.GetDynamicSpecSourceTags().HasTagExact(AbilityTag)){
			return AbilitySpec;
		}
	}
	return nullptr;
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

void UMyAbilitySystemComponent::AddStartupAbilities(TArray<TSubclassOf<UGameplayAbility>> StartupAbilities)
{
	for (TSubclassOf<UGameplayAbility> AbilityClass : StartupAbilities)
	{
		UMyGameplayAbility* MyGA =Cast<UMyGameplayAbility>(AbilityClass.GetDefaultObject());
		FGameplayTag InputTag= MyGA->InputTag;
		FGameplayTag AbilityTag= MyGA->AbilityTag;
		if (!MyGA)
		{
			UKismetSystemLibrary::PrintString(GetWorld(),TEXT("Invalid AbilityClass for Ability: ") + AbilityClass.Get()->GetName());
		}
		if (MyGA)
		{
			FGameplayAbilitySpec GameplayAbilitySpec=BuildAbilitySpecFromClass(AbilityClass);
			if (InputTag.IsValid())
			{
				GameplayAbilitySpec.GetDynamicSpecSourceTags().AddTag(InputTag);
			}
			if (AbilityTag.IsValid())
			{
				GameplayAbilitySpec.GetDynamicSpecSourceTags().AddTag(AbilityTag);
			}
			GameplayAbilitySpec.GetDynamicSpecSourceTags().AddTag(MyTags::Ability_Status_Equipped);
			
			GiveAbility(GameplayAbilitySpec);
		}
		else
		{
			UKismetSystemLibrary::PrintString(GetWorld(),TEXT("Invalid InputTag for Ability: ") + AbilityClass.Get()->GetName());
		}
	}
}

void UMyAbilitySystemComponent::ServerUpgradeAttribute_Implementation(FGameplayTag AttributeTag)
{
	
	//HasAuthority() Always returns true in server rpc
	if (GetAvatarActor()->Implements<UMyPlayerInterface>())
	{
		if (IMyPlayerInterface::Execute_GetAttributePoints(GetAvatarActor())>0)
		{
			FGameplayEventData EventData;
			EventData.EventTag=AttributeTag;
			EventData.EventMagnitude=1;
			UAbilitySystemBlueprintLibrary::SendGameplayEventToActor(GetAvatarActor(),AttributeTag,EventData);
			IMyPlayerInterface::Execute_AddToAttributePoints(GetAvatarActor(),-1);
		}
	}
}
