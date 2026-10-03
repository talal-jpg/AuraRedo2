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
		// Only direct children of "Ability" (Ability.FireBolt), not Ability.Status.X / Ability.Cooldown.X
		if (Tag.RequestDirectParent().MatchesTagExact(FGameplayTag(MyTags::Ability_None).RequestDirectParent()))
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
			if (Tag.MatchesTagExact(AbilityTag))
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
		if (Tag.MatchesTag(FGameplayTag(MyTags::Input_None).RequestDirectParent()))
		{
			return Tag;
		}
	}
	return FGameplayTag();
}

void UMyAbilitySystemComponent::SetInputTagOnSpec(FGameplayAbilitySpec& AbilitySpec, FGameplayTag NewInputTag)
{
	FGameplayTagContainer& DynamicTags=AbilitySpec.GetDynamicSpecSourceTags();
	// Remove all Input tags, not just the first, so a spec can never end up bound to two slots
	FGameplayTagContainer InputTags=DynamicTags.Filter(FGameplayTagContainer(FGameplayTag(MyTags::Input_None).RequestDirectParent()));
	DynamicTags.RemoveTags(InputTags);
	DynamicTags.AddTag(NewInputTag);
}

void UMyAbilitySystemComponent::SetStatusTagOnSpec(FGameplayAbilitySpec& AbilitySpec, FGameplayTag NewStatusTag)
{
	FGameplayTagContainer& DynamicTags=AbilitySpec.GetDynamicSpecSourceTags();
	FGameplayTagContainer StatusTags=DynamicTags.Filter(FGameplayTagContainer(FGameplayTag(MyTags::Ability_Status_Locked).RequestDirectParent()));
	DynamicTags.RemoveTags(StatusTags);
	DynamicTags.AddTag(NewStatusTag);
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
	if (!bAbilitiesGiven)return;
	FScopedAbilityListLock ScopedAbilityListLock= FScopedAbilityListLock(*this);
	for (FGameplayAbilitySpec& AbilitySpec:GetActivatableAbilities())
	{
		// UKismetSystemLibrary::PrintString(GetWorld(),TEXT("AbilityInputPressed") + InputTag.ToString());
		if (AbilitySpec.GetDynamicSpecSourceTags().HasTagExact(InputTag)){
			// TryActivateAbility(AbilitySpec.Handle);
			//Assuming the ability is active and the Ability is instanced per actor , non instanced per actor will cause crash here
			AbilitySpecInputPressed(AbilitySpec);
			// Only instanced-per-actor abilities have a primary instance; others would crash here
			if (UGameplayAbility* PrimaryInstance=AbilitySpec.GetPrimaryInstance())
			{
				InvokeReplicatedEvent(EAbilityGenericReplicatedEvent::InputPressed,AbilitySpec.Handle,PrimaryInstance->GetCurrentActivationInfo().GetActivationPredictionKey());
			}
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
	FScopedAbilityListLock ScopedAbilityListLock= FScopedAbilityListLock(*this);
	for (FGameplayAbilitySpec& AbilitySpec: GetActivatableAbilities())
	{
		if (AbilitySpec.GetDynamicSpecSourceTags().HasTagExact(InputTag))
		{
			// AbilitySpecInputPressed(AbilitySpec);
			if (!AbilitySpec.IsActive())
			{
				TryActivateAbility(AbilitySpec.Handle);
			}
		}
	}
}

void UMyAbilitySystemComponent::AbilityInputReleased(FGameplayTag InputTag)
{
	// UKismetSystemLibrary::PrintString(this,TEXT("AbilityInputReleased") + InputTag.ToString());
	FScopedAbilityListLock ScopedAbilityListLock= FScopedAbilityListLock(*this);
	for (FGameplayAbilitySpec& AbilitySpec: GetActivatableAbilities())
	{
		if (AbilitySpec.GetDynamicSpecSourceTags().HasTagExact(InputTag))
		{
			AbilitySpecInputReleased(AbilitySpec);
			if (UGameplayAbility* PrimaryInstance=AbilitySpec.GetPrimaryInstance())
			{
				InvokeReplicatedEvent(EAbilityGenericReplicatedEvent::InputReleased,AbilitySpec.Handle,PrimaryInstance->GetCurrentActivationInfo().GetActivationPredictionKey());
			}
		}
	}
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
		
		// int32 SpellPoints=IMyPlayerInterface::Execute_GetSpellPoints(GetAvatarActor());
		//
		// UKismetSystemLibrary::PrintString(GetWorld(),FString::Printf(TEXT("SpendSpellPoint:SpellPoints = %d for "),SpellPoints) + AbilityTag.ToString());
		
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

void UMyAbilitySystemComponent::Server_EquipAbility_Implementation(FGameplayTag AbilityTag,FGameplayTag NewInputTag)
{
	// Server is the source of truth: never trust the client's idea of the current slot or status
	if (!NewInputTag.MatchesTag(FGameplayTag(MyTags::Input_None).RequestDirectParent()) || NewInputTag.MatchesTagExact(MyTags::Input_None))return;
	
	FGameplayAbilitySpec* GASpec=GetAbilitySpecFromTag(AbilityTag);
	if (!GASpec)return;
	
	const FGameplayTag StatusTag=GetStatusTagFromSpec(*GASpec);
	if (!StatusTag.MatchesTagExact(MyTags::Ability_Status_Unlocked) && !StatusTag.MatchesTagExact(MyTags::Ability_Status_Equiped))return;
	
	const FGameplayTag PrevInputTag=GetInputTagFromSpec(*GASpec);
	
	if (!PrevInputTag.MatchesTagExact(NewInputTag))
	{
		// Unequip every other ability in the NewInputTag slot, they go back to Unlocked with no slot
		FScopedAbilityListLock ScopedAbilityListLock= FScopedAbilityListLock(*this);
		for (FGameplayAbilitySpec& OtherSpec:GetActivatableAbilities())
		{
			if (&OtherSpec==GASpec || !OtherSpec.GetDynamicSpecSourceTags().HasTagExact(NewInputTag))continue;
			
			// Cancel so a held ability doesn't get stuck waiting for an input release that will never arrive
			if (OtherSpec.IsActive())
			{
				CancelAbilityHandle(OtherSpec.Handle);
			}
			SetInputTagOnSpec(OtherSpec,MyTags::Input_None);
			SetStatusTagOnSpec(OtherSpec,MyTags::Ability_Status_Unlocked);
			MarkAbilitySpecDirty(OtherSpec);
			// Sent before the equipped ability's RPC (reliable RPCs stay ordered) so the slot is cleared then refilled
			Client_EquipAbility(GetAbilityTagFromSpec(OtherSpec),MyTags::Input_None,MyTags::Ability_Status_Unlocked,NewInputTag);
		}
		
		if (GASpec->IsActive())
		{
			CancelAbilityHandle(GASpec->Handle);
		}
		SetInputTagOnSpec(*GASpec,NewInputTag);
	}
	
	SetStatusTagOnSpec(*GASpec,MyTags::Ability_Status_Equiped);
	MarkAbilitySpecDirty(*GASpec);
	Client_EquipAbility(AbilityTag,NewInputTag,MyTags::Ability_Status_Equiped,PrevInputTag);
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
