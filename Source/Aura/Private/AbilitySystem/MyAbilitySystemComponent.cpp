// Fill out your copyright notice in the Description page of Project Settings.


#include "AbilitySystem/MyAbilitySystemComponent.h"

#include "AbilitySystemBlueprintLibrary.h"
#include "MyPlayerState.h"
#include "AbilitySystem/MyAttributeSet.h"
#include "AbilitySystem/Data/MyGameplayTags.h"
#include "Interfaces/MyPlayerInterface.h"
#include "Kismet/GameplayStatics.h"
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

FGameplayTag UMyAbilitySystemComponent::GetStatusFromAbiltyTag(FGameplayTag AbilityTag)
{
	FGameplayAbilitySpec* AbilitySpec = GetAbilitySpecFromTag(AbilityTag);
	if (AbilitySpec)
	{
		return GetStatusTagFromSpec(*AbilitySpec);
		// FGameplayAbilitySpec AbilitySpecDeRef=*AbilitySpec;
		// for (FGameplayTag Tag:AbilitySpecDeRef.GetDynamicSpecSourceTags())
		// {
		// 	if (Tag.MatchesTagDepth(MyTags::Ability_Status_Eligible)> 1)
		// 	{
		// 		return Tag;
		// 	}
		// }
	}
	else
	{
		UKismetSystemLibrary::PrintString(GetWorld(),TEXT("SpecNotfoundForTag") + AbilityTag.ToString());
	}
	//TODO why do we need to Deref here when Server_EquipAbility removing adding InputTag works fine without Deref
	return FGameplayTag();
}

FGameplayTag UMyAbilitySystemComponent::GetAbilityTagFromSpec(const FGameplayAbilitySpec& AbilitySpec)
{
	for (FGameplayTag Tag:AbilitySpec.GetDynamicSpecSourceTags())
	{
		if (Tag.MatchesTagDepth(MyTags::Ability_None)> 0)
		{
			return Tag;
		}
	}
	return FGameplayTag();
}

FGameplayAbilitySpec* UMyAbilitySystemComponent::GetAbilitySpecFromTag(FGameplayTag AbilityTag)
{
	FScopedAbilityListLock ScopedAbilityListLock= FScopedAbilityListLock(*this);
	for (FGameplayAbilitySpec& AbilitySpec:GetActivatableAbilities())
	{
		for (FGameplayTag Tag:AbilitySpec.GetDynamicSpecSourceTags())
		{
			if (Tag.MatchesTag(AbilityTag))
			{
				return &AbilitySpec;
			}
		}
	}
	return nullptr;
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
	for (FGameplayTag Tag:AbilitySpec.GetDynamicSpecSourceTags())
	{
		if (Tag.MatchesTagDepth(MyTags::Ability_Status_Eligible)> 1)
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

//To call UpgradeAttrib locally first just to check if attrib points are available a then only send server rpc
void UMyAbilitySystemComponent::UpgradeAttribute(FGameplayTag AttribTag)
{
	if (GetAvatarActor()->Implements<UMyPlayerInterface>())
	{
		if (IMyPlayerInterface::Execute_GetAttribPoints(GetAvatarActor())>0)
		{
			Server_UpgradeAttribute(AttribTag);
		}
	}
}

void UMyAbilitySystemComponent::Server_SpendSpellPoint_Implementation(FGameplayTag AbilityTag,FGameplayTag StatusTag)
{
	if (GetAvatarActor()->Implements<UMyPlayerInterface>())
	{
		IMyPlayerInterface::Execute_AddToSpellPoints(GetAvatarActor(),-1);
		FGameplayAbilitySpec* GASpec=GetAbilitySpecFromTag(AbilityTag);
		if (StatusTag.MatchesTagExact(MyTags::Ability_Status_Unlocked) || StatusTag.MatchesTagExact(MyTags::Ability_Status_Equiped))
		{
			GASpec->Level+=1;
		}
		else if(StatusTag.MatchesTagExact(MyTags::Ability_Status_Eligible))
		{
			
		}
	}
	
}

void UMyAbilitySystemComponent::Server_EquipAbility_Implementation(FGameplayTag AbilityTag,FGameplayTag NewInputTag,FGameplayTag CurrentInputTag)
{
	
	FGameplayAbilitySpec* GASpec=GetAbilitySpecFromTag(AbilityTag);
	// TODO Get Ability In the CurrentInputTag slot and Remove InputTag from it
	// FGameplayTag CurrentInputTag=GASpec->GetDynamicSpecSourceTags().Filter(MyTags::Input_LMB.GetTag().GetSingleTagContainer()).First();
	GASpec->GetDynamicSpecSourceTags().RemoveTag(CurrentInputTag);
	GASpec->GetDynamicSpecSourceTags().AddTag(NewInputTag);
	Client_EquipAbility(AbilityTag,NewInputTag,GetStatusTagFromSpec(*GASpec),CurrentInputTag);
}

void UMyAbilitySystemComponent::Client_EquipAbility_Implementation(FGameplayTag AbilityTag,FGameplayTag InputTag, FGameplayTag StatusTag,FGameplayTag PrevInputTag)
{
	OnAbilityEquippedDelegate.Broadcast(AbilityTag,InputTag,StatusTag,PrevInputTag);
}

void UMyAbilitySystemComponent::Server_UpgradeAttribute_Implementation(FGameplayTag AttribTag)
{
	const FGameplayAttribute* AttribToUpgrade = Cast<UMyAttributeSet>(GetAttributeSet(UMyAttributeSet::StaticClass()))->TagToAttributeMap.Find(AttribTag);
	
	FGameplayEventData EventData;
	EventData.EventTag=AttribTag;
	EventData.EventMagnitude=1;
	
	UAbilitySystemBlueprintLibrary::SendGameplayEventToActor(GetAvatarActor(),AttribTag,EventData);
	
	if (GetAvatarActor()->Implements<UMyPlayerInterface>())
	{
		IMyPlayerInterface::Execute_AddToAttribPoints(GetAvatarActor(),-1);
	}
}
