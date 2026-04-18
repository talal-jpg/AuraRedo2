// Fill out your copyright notice in the Description page of Project Settings.


#include "AbilitySystem/MyAbilitySystemComponent.h"

#include <string>

#include "AbilitySystemBlueprintLibrary.h"
#include "AbilitySystem/Abilities/MyGameplayAbility.h"
#include "AbilitySystem/Data/MyGameplayTags.h"
#include "Interfaces/MyPlayerInterface.h"
#include "Kismet/KismetSystemLibrary.h"
#include "StaticLib/MyBPFuncLib.h"

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
		if (Tag.MatchesTag(UGameplayTagsManager::Get().RequestGameplayTag(FName("Ability"))))
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
	return MyTags::Input;
}

FGameplayTag UMyAbilitySystemComponent::GetStatusTagFromSpec(const FGameplayAbilitySpec& AbilitySpec)
{
	// FScopedAbilityListLock ScopedAbilityListLock= FScopedAbilityListLock(*this);
	for (FGameplayTag Tag:AbilitySpec.GetDynamicSpecSourceTags().GetGameplayTagArray())
	{
		//Requesting Parent of Ability.Status.Equipped = Ability.Status
		if (Tag.MatchesTag(MyTags::Ability_Status_Equipped.GetTag().RequestDirectParent()))
		{
			return Tag;
		}
	}
	return FGameplayTag();
}

FGameplayAbilitySpec* UMyAbilitySystemComponent::GetAbilitySpecFromTag(FGameplayTag AbilityTag)
{
	FScopedAbilityListLock ScopedAbilityListLock= FScopedAbilityListLock(*this);
	for (auto& AbilitySpec:GetActivatableAbilities())
	{
		if (AbilitySpec.GetDynamicSpecSourceTags().HasTagExact(AbilityTag)){
			return &AbilitySpec;
		}
	}
	return nullptr;
}

void UMyAbilitySystemComponent::GetDescriptionsByAbilityTag(FGameplayTag AbilityTag, FString& Description,FString& NextLevelDescription)
{
	UDA_MyAbilityInfo* MyAbilityInfo=UMyBPFuncLib::GetAbilityInfo(GetAvatarActor());
	if (!MyAbilityInfo)
	{
		UKismetSystemLibrary::PrintString(GetWorld(),TEXT("MyAbilityInfo is null No GameMode Present"));
		return;
	}
	FAbilityInfo AbilityInfo=MyAbilityInfo->GetAbilityInfoForTag(AbilityTag);
	Description=AbilityInfo.Description;
	NextLevelDescription=AbilityInfo.NextLevelDescription;
}

void UMyAbilitySystemComponent::UpdateAbilityStatuses(int32 InPlayerLevel)
{
	UDA_MyAbilityInfo* DA_AbilityInfo= UMyBPFuncLib::GetAbilityInfo(GetAvatarActor());
	FScopedAbilityListLock ScopedAbilityListLock= FScopedAbilityListLock(*this);
	for (auto AbilityInfo: DA_AbilityInfo->AbilityInfos)
	{
		if (InPlayerLevel<AbilityInfo.LevelRequirement)continue;
		if (GetAbilitySpecFromTag(AbilityInfo.AbilityTag)==nullptr)
		{
			FGameplayAbilitySpec GASpec= FGameplayAbilitySpec(AbilityInfo.GameplayAbilityClass,1);
			GASpec.GetDynamicSpecSourceTags().AddTag(AbilityInfo.AbilityTag);
			GASpec.GetDynamicSpecSourceTags().AddTag(MyTags::Ability_Status_Eligible);
			
			FGameplayAbilitySpecHandle GASpecHandle=GiveAbility(GASpec);
			// MarkAbilitySpecDirty(*FindAbilitySpecFromHandle(GASpecHandle));
			ClientUpdateAbilityStatus(AbilityInfo.AbilityTag,MyTags::Ability_Status_Eligible,AbilityInfo.LevelRequirement);
		}
	}
	
	
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

void UMyAbilitySystemComponent::ServerSpendSpellPoints_Implementation(FGameplayTag AbilityTag)
{
	FScopedAbilityListLock ScopedAbilityListLock= FScopedAbilityListLock(*this);
	if (FGameplayAbilitySpec* AbilitySpec=GetAbilitySpecFromTag(AbilityTag))
	{
		if (GetAvatarActor()->Implements<UMyPlayerInterface>())
		{
			IMyPlayerInterface::Execute_AddToSpellPoints(GetAvatarActor(),-1);
		}
		
		FGameplayTag StatusTag=GetStatusTagFromSpec(*AbilitySpec);
		if (StatusTag.MatchesTagExact(MyTags::Ability_Status_Eligible))
		{
			FGameplayTagContainer& DynamicTags=AbilitySpec->GetDynamicSpecSourceTags();
			
			
			DynamicTags.RemoveTag(MyTags::Ability_Status_Eligible);
			DynamicTags.AddTag(MyTags::Ability_Status_Unlocked);
			StatusTag=MyTags::Ability_Status_Unlocked;
		}
		else if (StatusTag.MatchesTagExact(MyTags::Ability_Status_Equipped) || StatusTag.MatchesTagExact(MyTags::Ability_Status_Unlocked))
		{
			AbilitySpec->Level +=1;
		}
		ClientUpdateAbilityStatus(AbilityTag,StatusTag,AbilitySpec->Level);
		MarkAbilitySpecDirty(*AbilitySpec);
	}
}

void UMyAbilitySystemComponent::ClientUpdateAbilityStatus_Implementation(FGameplayTag AbilityTag,FGameplayTag StatusTag, int32 AbilityLevel)
{
	AbilityStatusChangedDelegate.Broadcast(AbilityTag,StatusTag,AbilityLevel);
}

void UMyAbilitySystemComponent::ServerEquipAbility_Implementation(FGameplayTag AbilityTag,FGameplayTag SlotTag)
{
	if (FGameplayAbilitySpec* AbilitySpec=GetAbilitySpecFromTag(AbilityTag))
	{
		UKismetSystemLibrary::PrintString(GetWorld(),AbilitySpec->Ability->GetName());
		//TODO Talal Fix func , accounting for all the edge cases
		FGameplayTag PrevSlot= GetInputTagFromSpec(*AbilitySpec);
		FGameplayTag Status=GetStatusTagFromSpec(*AbilitySpec);
		
		bool bStatusValid=Status == MyTags::Ability_Status_Equipped || Status == MyTags::Ability_Status_Unlocked;
		if (bStatusValid)
		{
			// CancelAbilityHandle(AbilitySpec->Handle);
			//if have slot (HaveAbilitySpec) , Clear , if it i passive ability also stop the ability
			if (FGameplayAbilitySpec* AbilitySpecInSlot=GetAbilitySpecFromSlot(SlotTag))
			{
				AbilitySpecInSlot->GetDynamicSpecSourceTags().RemoveTag(SlotTag);
				AbilitySpecInSlot->GetDynamicSpecSourceTags().RemoveTag(GetStatusTagFromSpec(*AbilitySpecInSlot));
				AbilitySpecInSlot->GetDynamicSpecSourceTags().AddTag(MyTags::Ability_Status_Unlocked);
			}
			//if not have a slot , ie Input_Tag not found 
			if(GetInputTagFromSpec(*AbilitySpec).IsValid())
			{
				UKismetSystemLibrary::PrintString(this, "InSideLoop");
				FGameplayTagContainer& DynamicTags=AbilitySpec->GetDynamicSpecSourceTags();
				DynamicTags.RemoveTag(GetStatusTagFromSpec(*AbilitySpec));
				DynamicTags.AddTag(MyTags::Ability_Status_Equipped);
				
				UKismetSystemLibrary::PrintString(this, SlotTag.ToString(),true,true,FLinearColor::Red,10.f);
				DynamicTags.AddTag(SlotTag);
				
				MarkAbilitySpecDirty(*AbilitySpec);
				
				UKismetSystemLibrary::PrintString(this, GetInputTagFromSpec(*AbilitySpec).ToString(),true,true,FLinearColor::Red,10.f);
				// if (AbilityType==Passive){Activate}
			}
			//remove tag current status, add equip status , assign Slot ie add inputTag,activate only for passive 
			ClientUpdateAbilityEquip(AbilityTag,SlotTag);
		}
		
		// FGameplayTagContainer& DynamicTagsContainer=AbilitySpec->GetDynamicSpecSourceTags();
		// FGameplayTagContainer TagContainer=DynamicTagsContainer.Filter(FGameplayTagContainer(MyTags::Input));
		// DynamicTagsContainer.RemoveTag(TagContainer.First());
		// DynamicTagsContainer.AddTag(SlotTag);
	}
}

void UMyAbilitySystemComponent::ClientUpdateAbilityEquip_Implementation(FGameplayTag AbilityTag, FGameplayTag SlotTag)
{
	AbilityEquipChangedDelegate.Broadcast(AbilityTag,SlotTag);
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

void UMyAbilitySystemComponent::OnRep_ActivateAbilities()
{
	Super::OnRep_ActivateAbilities();
	
	if (!bAbilitiesGiven)
	{
		bAbilitiesGiven=true;
		OnAbilitiesGivenDelegate.Broadcast();
	}
}

FGameplayTag UMyAbilitySystemComponent::GetStatusTagFromAbilityTag(const FGameplayTag& AbilityTag)
{
	if (const FGameplayAbilitySpec* AbilitySpec=GetAbilitySpecFromTag(AbilityTag))
	{
		return GetStatusTagFromSpec(*AbilitySpec);
	}
	return FGameplayTag();
}

FGameplayTag UMyAbilitySystemComponent::GetSlotFromAbilityTag(const FGameplayTag& AbilityTag)
{
	if (const FGameplayAbilitySpec* AbilitySpec=GetAbilitySpecFromTag(AbilityTag))
	{
		return GetInputTagFromSpec(*AbilitySpec);
	}
	return FGameplayTag();
}

FGameplayAbilitySpec* UMyAbilitySystemComponent::GetAbilitySpecFromSlot(const FGameplayTag& SlotTag)
{
	FScopedAbilityListLock ScopedAbilityListLock= FScopedAbilityListLock(*this);
	for (auto& AbilitySpec:GetActivatableAbilities())
	{
		if (AbilitySpec.GetDynamicSpecSourceTags().HasTagExact(SlotTag)){
			return &AbilitySpec;
		}
	}
	return nullptr;
}

bool UMyAbilitySystemComponent::IsSlotEmpty(FGameplayTag SlotTag)
{
	FScopedAbilityListLock ScopedAbilityListLock= FScopedAbilityListLock(*this);
	for (auto AbilitySpec:GetActivatableAbilities())
	{
		if (AbilitySpec.GetDynamicSpecSourceTags().HasTagExact(SlotTag)){
			return false;
		}
	}
	return true;
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
