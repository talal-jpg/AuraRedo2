// Fill out your copyright notice in the Description page of Project Settings.

#include "AbilitySystem/BPAsyncTasks/BPAT_WaitForCooldownChange.h"

#include "AbilitySystemComponent.h"
#include "GameplayTagContainer.h"
#include "AbilitySystem/Data/MyGameplayTags.h"
#include "Kismet/KismetSystemLibrary.h"

UBPAT_WaitForCooldownChange* UBPAT_WaitForCooldownChange::WaitForCooldownChange(UAbilitySystemComponent* InASC,FGameplayTag InCooldownTag)
{
	
	UBPAT_WaitForCooldownChange* WaitForCooldownChange=NewObject<UBPAT_WaitForCooldownChange>();
	if (!IsValid(InASC) || !InCooldownTag.IsValid() || InCooldownTag.MatchesTagExact(MyTags::Ability_Cooldown_None))
	{
		WaitForCooldownChange->EndTask();
		return nullptr;
	}
	WaitForCooldownChange->CooldownTag=InCooldownTag;
	WaitForCooldownChange->ASC=InASC;
	
	WaitForCooldownChange->ActiveGEAddedDelegateHandle=InASC->OnActiveGameplayEffectAddedDelegateToSelf.AddUObject(WaitForCooldownChange,&UBPAT_WaitForCooldownChange::OnCooldownStartedCallback);
	
	return WaitForCooldownChange;
}

void UBPAT_WaitForCooldownChange::EndTask()
{
	
	if (!IsValid(ASC))return;
	ASC->RegisterGameplayTagEvent(CooldownTag,EGameplayTagEventType::NewOrRemoved).RemoveAll(this);
	// bool Removed=ASC->OnActiveGameplayEffectAddedDelegateToSelf.Remove(ActiveGEAddedDelegateHandle);
	ASC->OnActiveGameplayEffectAddedDelegateToSelf.Remove(ActiveGEAddedDelegateHandle);
	// if (Removed)
	// {
	// 	FString Str=CooldownTag.ToString();
	// 	UKismetSystemLibrary::PrintString(GetWorld(),FString::Printf(TEXT("Removed OnActiveGameplayEffectAddedDelegateToSelf,%s"),*Str));
	// }
	
	
	//Kinda true but can also unbind to the delegates especially if the WidgetController is being destroyed
	//Tag events = subscription system stored in a map → manual unsubscribe needed
	//ASC delegates = engine-managed event streams → safer bindings
	
	SetReadyToDestroy();
	MarkAsGarbage();
}

void UBPAT_WaitForCooldownChange::OnCooldownStartedCallback(UAbilitySystemComponent* ASC, const FGameplayEffectSpec& GESpec,FActiveGameplayEffectHandle ActiveGameplayEffectHandle)
{
	FGameplayTagContainer GrantedTags;
	GESpec.GetAllGrantedTags(GrantedTags);
	
	if (GrantedTags.HasTagExact(CooldownTag))
	{
		
		//Owning Tags= GrantedTags  EffectTags= AssetTags SpecSourceTags= TagsCapturedWhenMakingASpecFromTheSource
		// Match with any works if the cooldown effect asset tags has the tag?
		// To be called within SpellGlobe not the ability itself 
		
		FGameplayEffectQuery Query= FGameplayEffectQuery::MakeQuery_MatchAnyOwningTags(CooldownTag.GetSingleTagContainer());
		float TimeRemaining= ASC->GetActiveEffectsDuration(Query)[0];
		
		OnCooldownStartedDelegate.Broadcast(TimeRemaining);
		
		// UKismetSystemLibrary::PrintString(GetWorld(),TEXT("Cooldown Remaining: ") + FString::FromInt(TimeRemaining));
	}
}

