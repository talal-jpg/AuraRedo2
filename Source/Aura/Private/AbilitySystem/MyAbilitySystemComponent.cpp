// Fill out your copyright notice in the Description page of Project Settings.


#include "AbilitySystem/MyAbilitySystemComponent.h"

#include "AbilitySystemBlueprintLibrary.h"
#include "MyGameMode.h"
#include "MyPlayerState.h"
#include "AbilitySystem/MyAttributeSet.h"
#include "AbilitySystem/Data/MyGameplayTags.h"
#include "Character/MyCharPlayer.h"
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
	return MyTags::Ability_Status_Locked;
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

FGameplayAbilitySpec* UMyAbilitySystemComponent::GetAbilitySpecFromSlotTag(FGameplayTag InSlotTag)
{
	FScopedAbilityListLock ScopedAbilityListLock= FScopedAbilityListLock(*this);
	for (FGameplayAbilitySpec& AbilitySpec:GetActivatableAbilities())
	{
		for (FGameplayTag Tag:AbilitySpec.GetDynamicSpecSourceTags())
		{
			if (Tag.MatchesTagExact(InSlotTag))
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
		int32 SpellPoints=IMyPlayerInterface::Execute_GetSpellPoints(GetAvatarActor());
		
		UKismetSystemLibrary::PrintString(GetWorld(),FString::Printf(TEXT("SpendSpellPoint:SpellPoints = %d for "),SpellPoints) + AbilityTag.ToString());
		
		FGameplayAbilitySpec* GASpec=GetAbilitySpecFromTag(AbilityTag);
		// if (GASpec) dont need to check bcz can only press Spend point if found a valid Ability
		
		if (StatusTag.MatchesTagExact(MyTags::Ability_Status_Unlocked) || StatusTag.MatchesTagExact(MyTags::Ability_Status_Equiped))
		{
			GASpec->Level+=1;
			UKismetSystemLibrary::PrintString(GetWorld(),FString::Printf(TEXT("LevelUp:NowLevel = %d for "),GASpec->Level) + AbilityTag.ToString());
		}
		else if(StatusTag.MatchesTagExact(MyTags::Ability_Status_Eligible))
		{
			GASpec->GetDynamicSpecSourceTags().RemoveTag(StatusTag);
			GASpec->GetDynamicSpecSourceTags().AddTag(MyTags::Ability_Status_Unlocked);
			MarkAbilitySpecDirty(*GASpec);
			StatusTag=MyTags::Ability_Status_Unlocked;
		}
		
		Client_UpdateAbilityStatus(AbilityTag,StatusTag,GASpec->Level);
	}
}

void UMyAbilitySystemComponent::Client_UpdateAbilityStatus_Implementation(FGameplayTag AbilityTag,FGameplayTag StatusTag,int32 AbilityLevel)
{
	OnAbilityStatusChangedDelegate.ExecuteIfBound(AbilityTag,StatusTag,AbilityLevel);
	
}

void UMyAbilitySystemComponent::Server_EquipAbility_Implementation(FGameplayTag AbilityTag,FGameplayTag NewInputTag,FGameplayTag CurrentInputTag)
{
	
	FGameplayAbilitySpec* GASpec=GetAbilitySpecFromTag(AbilityTag);
	// Getting Ability In the NewInputTag slot and Remove InputTag from it
	if (FGameplayAbilitySpec* NewInputGASpec=GetAbilitySpecFromSlotTag(NewInputTag))
	{
		NewInputGASpec->GetDynamicSpecSourceTags().RemoveTag(NewInputTag);
		MarkAbilitySpecDirty(*NewInputGASpec);
		// UKismetSystemLibrary::PrintString(GetWorld(),TEXT("Replacing Ability: ") + NewInputGASpec->Ability->GetName());
	}
	
	GASpec->GetDynamicSpecSourceTags().RemoveTag(CurrentInputTag);
	GASpec->GetDynamicSpecSourceTags().AddTag(NewInputTag);
	MarkAbilitySpecDirty(*GASpec);
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
