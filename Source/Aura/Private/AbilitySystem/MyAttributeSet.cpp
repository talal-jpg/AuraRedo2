// Fill out your copyright notice in the Description page of Project Settings.


#include "AbilitySystem/MyAttributeSet.h"

#include <string>

#include "GameplayEffectExtension.h"
#include "GameplayEffectTypes.h"
#include "MyAiController.h"
#include "AbilitySystem/Data/MyGameplayTags.h"
#include "AbilitySystemBlueprintLibrary.h"
#include "BehaviorTree/BlackboardComponent.h"
#include "Character/MyCharBase.h"
#include "Character/MyEnemyChar.h"
#include "Character/MyPlayerInterface.h"
#include "Kismet/GameplayStatics.h"
#include "Kismet/KismetSystemLibrary.h"
#include "Net/UnrealNetwork.h"
#include "PlayerInput/MyPlayerController.h"
#include "StaticLib/MyBPFuncLib.h"

UMyAttributeSet::UMyAttributeSet()
{
	TagToAttributeMap.Add(MyTags::Attribute_Vital_Health,GetHealthAttribute());
	TagToAttributeMap.Add(MyTags::Attribute_Vital_Mana,GetManaAttribute());
	
	TagToAttributeMap.Add(MyTags::Attribute_Primary_Strength,GetStrengthAttribute());
	TagToAttributeMap.Add(MyTags::Attribute_Primary_Agility,GetAgilityAttribute());
	TagToAttributeMap.Add(MyTags::Attribute_Primary_Intelligence,GetIntelligenceAttribute());
	
	TagToAttributeMap.Add(MyTags::Attribute_Secondary_MaxHealth,GetMaxHealthAttribute());
	TagToAttributeMap.Add(MyTags::Attribute_Secondary_MaxMana,GetMaxManaAttribute());
	TagToAttributeMap.Add(MyTags::Attribute_Secondary_HealthRegen,GetHealthRegenAttribute());
	TagToAttributeMap.Add(MyTags::Attribute_Secondary_ManaRegen,GetManaRegenAttribute());
	TagToAttributeMap.Add(MyTags::Attribute_Secondary_MagicResist,GetMagicResistAttribute());
	TagToAttributeMap.Add(MyTags::Attribute_Secondary_Armor,GetArmorAttribute());
	TagToAttributeMap.Add(MyTags::Attribute_Secondary_AttackSpeed,GetAttackSpeedAttribute());
	TagToAttributeMap.Add(MyTags::Attribute_Secondary_MoveSpeed,GetMoveSpeedAttribute());
	TagToAttributeMap.Add(MyTags::Attribute_Secondary_TurnSpeed,GetTurnSpeedAttribute());
	TagToAttributeMap.Add(MyTags::Attribute_Secondary_AttackDamage,GetAttackDamageAttribute());
}

void UMyAttributeSet::GetLifetimeReplicatedProps(TArray<class FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME_CONDITION_NOTIFY(UMyAttributeSet,Health,COND_None,REPNOTIFY_Always);
	DOREPLIFETIME_CONDITION_NOTIFY(UMyAttributeSet,Mana,COND_None,REPNOTIFY_Always);
	DOREPLIFETIME_CONDITION_NOTIFY(UMyAttributeSet,MaxHealth,COND_None,REPNOTIFY_Always);
	DOREPLIFETIME_CONDITION_NOTIFY(UMyAttributeSet,MaxMana,COND_None,REPNOTIFY_Always);
	DOREPLIFETIME_CONDITION_NOTIFY(UMyAttributeSet,Strength,COND_None,REPNOTIFY_Always);
	DOREPLIFETIME_CONDITION_NOTIFY(UMyAttributeSet,Agility,COND_None,REPNOTIFY_Always);
	DOREPLIFETIME_CONDITION_NOTIFY(UMyAttributeSet,Intelligence,COND_None,REPNOTIFY_Always);
	DOREPLIFETIME_CONDITION_NOTIFY(UMyAttributeSet,HealthRegen,COND_None,REPNOTIFY_Always);
	DOREPLIFETIME_CONDITION_NOTIFY(UMyAttributeSet,ManaRegen,COND_None,REPNOTIFY_Always);
	DOREPLIFETIME_CONDITION_NOTIFY(UMyAttributeSet,MagicResist,COND_None,REPNOTIFY_Always);
	DOREPLIFETIME_CONDITION_NOTIFY(UMyAttributeSet,Armor,COND_None,REPNOTIFY_Always);
	DOREPLIFETIME_CONDITION_NOTIFY(UMyAttributeSet,AttackSpeed,COND_None,REPNOTIFY_Always);
	DOREPLIFETIME_CONDITION_NOTIFY(UMyAttributeSet,AttackDamage,COND_None,REPNOTIFY_Always);
	
}


void UMyAttributeSet::OnRep_Health(const FGameplayAttributeData& OldHealth)
{
	GAMEPLAYATTRIBUTE_REPNOTIFY(UMyAttributeSet,Health,OldHealth);
}

void UMyAttributeSet::OnRep_Mana(const FGameplayAttributeData& OldMana)
{
	GAMEPLAYATTRIBUTE_REPNOTIFY(UMyAttributeSet,Mana,OldMana);
}

void UMyAttributeSet::OnRep_MaxHealth(const FGameplayAttributeData& OldMaxHealth)
{
	GAMEPLAYATTRIBUTE_REPNOTIFY(UMyAttributeSet,MaxHealth,OldMaxHealth);
}

void UMyAttributeSet::OnRep_MaxMana(const FGameplayAttributeData& OldMaxMana)
{
	GAMEPLAYATTRIBUTE_REPNOTIFY(UMyAttributeSet,MaxMana,OldMaxMana);
}

void UMyAttributeSet::OnRep_Strength(const FGameplayAttributeData& OldStrength)
{
	GAMEPLAYATTRIBUTE_REPNOTIFY(UMyAttributeSet,Strength,OldStrength);
}

void UMyAttributeSet::OnRep_Agility(const FGameplayAttributeData& OldAgility)
{
	GAMEPLAYATTRIBUTE_REPNOTIFY(UMyAttributeSet,Agility,OldAgility);
}

void UMyAttributeSet::OnRep_Intelligence(const FGameplayAttributeData& OldIntelligence)
{
	GAMEPLAYATTRIBUTE_REPNOTIFY(UMyAttributeSet,Intelligence,OldIntelligence);
}

void UMyAttributeSet::OnRep_HealthRegen(const FGameplayAttributeData& OldHealthRegen)
{
	GAMEPLAYATTRIBUTE_REPNOTIFY(UMyAttributeSet,HealthRegen,OldHealthRegen);
}

void UMyAttributeSet::OnRep_ManaRegen(const FGameplayAttributeData& OldManaRegen)
{
	GAMEPLAYATTRIBUTE_REPNOTIFY(UMyAttributeSet,ManaRegen,OldManaRegen);
}

void UMyAttributeSet::OnRep_MagicResist(const FGameplayAttributeData& OldMagicResist)
{
	GAMEPLAYATTRIBUTE_REPNOTIFY(UMyAttributeSet,MagicResist,OldMagicResist);
}

void UMyAttributeSet::OnRep_Armor(const FGameplayAttributeData& OldArmor)
{
	GAMEPLAYATTRIBUTE_REPNOTIFY(UMyAttributeSet,Armor,OldArmor);
}

void UMyAttributeSet::OnRep_AttackSpeed(const FGameplayAttributeData& OldAttackSpeed)
{
	GAMEPLAYATTRIBUTE_REPNOTIFY(UMyAttributeSet,AttackSpeed,OldAttackSpeed);
}

void UMyAttributeSet::OnRep_MoveSpeed(const FGameplayAttributeData& OldMoveSpeed)
{
	GAMEPLAYATTRIBUTE_REPNOTIFY(UMyAttributeSet,MoveSpeed,OldMoveSpeed);
}

void UMyAttributeSet::OnRep_TurnSpeed(const FGameplayAttributeData& OldTurnSpeed)
{
	GAMEPLAYATTRIBUTE_REPNOTIFY(UMyAttributeSet,TurnSpeed,OldTurnSpeed);
}

void UMyAttributeSet::OnRep_AttackDamage(const FGameplayAttributeData& OldAttackDamage)
{
	GAMEPLAYATTRIBUTE_REPNOTIFY(UMyAttributeSet,AttackDamage,OldAttackDamage);
}

void UMyAttributeSet::PostGameplayEffectExecute(FGameplayEffectModCallbackData& Data)
{
	FEffectProperties EffectProperties;
	SetEffectProperties(Data,EffectProperties);
	if (Data.EvaluatedData.Attribute==GetIncomingDamageAttribute())
	{
		float NewHealth=GetHealth()-Data.EvaluatedData.Magnitude;
		if (bool bIsFatal =NewHealth<=0.f)
		{
				UKismetSystemLibrary::PrintString(GetOwningActor(),TEXT("Fatal Damage from server"));
			if (!GetOwningActor()->HasAuthority())
			{
				UKismetSystemLibrary::PrintString(GetOwningActor(),TEXT("Fatal Damage from Client"));
			}
			// HandleDeath
			if (IMyCombatInterface* MyCombatIF=Cast<IMyCombatInterface>(GetOwningActor()))
			{
				MyCombatIF->HandleDeath();
				
				FGameplayEventData GameplayEventData;
				
				int32 TargetCharLevel=IMyCombatInterface::Execute_GetCharLevel(EffectProperties.TargetAvatarActor);
				ECharacterClass TargetCharClass=MyCombatIF->GetCharacterClass();
				int32 IncomingXpReward=0;
				UMyBPFuncLib::GetXpRewardForCharacterClassAtLevel(EffectProperties.SourceAvatarActor,TargetCharClass,TargetCharLevel,IncomingXpReward);
				// UKismetSystemLibrary::PrintString(EffectProperties.SourceAvatarActor,FString::Printf(TEXT("Incoming Xp Reward: %d"),IncomingXpReward));
				GameplayEventData.EventMagnitude=IncomingXpReward;
				GameplayEventData.EventTag=MyTags::Attribute_Meta_IncomingXp;
				//Event not being rec even on server when enemy dies from client
				UAbilitySystemBlueprintLibrary::SendGameplayEventToActor(EffectProperties.SourceAvatarActor,MyTags::Attribute_Meta_IncomingXp,GameplayEventData);
				UKismetSystemLibrary::PrintString(this, FString::Printf(TEXT("SERVER: Sent XP Event to %s"), *EffectProperties.SourceAvatarActor->GetName()));
			}
		}
		else
		{
			FGameplayTag HitReactTag= MyTags::Ability_HitReact;
			
			GetOwningAbilitySystemComponent()->TryActivateAbilitiesByTag(HitReactTag.GetSingleTagContainer());
			
		}
		SetHealth(NewHealth);
	}
	
	//ClampHealth
	if (Data.EvaluatedData.Attribute==GetHealthAttribute())
	{
		// Data.EvaluatedData.Magnitude=FMath::Clamp(Data.EvaluatedData.Magnitude,0.f,GetMaxHealth());
		SetHealth(FMath::Clamp(GetHealth(), 0.f, GetMaxHealth()));
	}
	
	//ShowDamageTextFloatingWidget
	if (EffectProperties.SourceAvatarActor != EffectProperties.TargetAvatarActor)
	{
		if (AMyPlayerController* PC=Cast<AMyPlayerController>(EffectProperties.SourceController))
		{
			PC->ShowDamageTextOnHit(10,EffectProperties.TargetCharacter);
		}
	}
	
	if (Data.EvaluatedData.Attribute==GetIncomingXpAttribute())
	{
		//Source and Target Actor is the same
		if (EffectProperties.SourceAvatarActor && EffectProperties.SourceAvatarActor->Implements<UMyPlayerInterface>() && EffectProperties.SourceAvatarActor->Implements<UMyCombatInterface>())
		{
			int32 LocalIncomingXp=GetIncomingXp();
			UKismetSystemLibrary::PrintString(EffectProperties.SourceAvatarActor,FString::Printf(TEXT("Incoming Xp: %d"),LocalIncomingXp));
			SetIncomingXp(0.f);
			AActor* TargetActor=EffectProperties.TargetAvatarActor;
			int32 CurrentLevel=IMyCombatInterface::Execute_GetCharLevel(TargetActor);
			int32 CurrentXP= IMyPlayerInterface::Execute_GetXP(TargetActor);
			int32 NewLevel=IMyPlayerInterface::Execute_FindLevelForXP(TargetActor,LocalIncomingXp+CurrentXP);
			int32 NumLevelUps=NewLevel-CurrentLevel;
			
			if (NumLevelUps>0)
			{
				IMyPlayerInterface::Execute_AddToPlayerLevel(TargetActor,NumLevelUps);
				int32 AttributePointsReward=0;
				int32 SpellPointsReward=0;
				
				for (int i=0;i<NumLevelUps;++i)
				{
					AttributePointsReward+=IMyPlayerInterface::Execute_GetAttributePointsReward(TargetActor,CurrentLevel+i);
					SpellPointsReward+=IMyPlayerInterface::Execute_GetSpellPointsReward(TargetActor,CurrentLevel+i);
				}
				IMyPlayerInterface::Execute_AddToAttributePoints(TargetActor,AttributePointsReward);
				IMyPlayerInterface::Execute_AddToSpellPoints(TargetActor,SpellPointsReward);
				
				IMyPlayerInterface::Execute_LevelUp(TargetActor);
			}
			IMyPlayerInterface::Execute_AddToXP(EffectProperties.SourceAvatarActor,LocalIncomingXp);
		}
	}
}

void UMyAttributeSet::PreAttributeChange(const FGameplayAttribute& Attribute, float& NewValue)
{
	if (Attribute==GetHealthAttribute())
	{
		// SetHealth(FMath::Clamp(NewValue,0.f,GetMaxHealth()));
		NewValue = FMath::Clamp(NewValue, 0.f, GetMaxHealth());
	}
}

void UMyAttributeSet::SetEffectProperties(FGameplayEffectModCallbackData& Data, FEffectProperties& EffectProperties)
{
	EffectProperties.EffectContextHandle= Data.EffectSpec.GetContext();
	EffectProperties.SourceASC= EffectProperties.EffectContextHandle.GetOriginalInstigatorAbilitySystemComponent();
	
	if (IsValid(EffectProperties.SourceASC) && EffectProperties.SourceASC->AbilityActorInfo.IsValid() && EffectProperties.SourceASC->AbilityActorInfo->AvatarActor.IsValid())
	{
		EffectProperties.SourceAvatarActor=EffectProperties.SourceASC->AbilityActorInfo->AvatarActor.Get();
		EffectProperties.SourceController=EffectProperties.SourceASC->AbilityActorInfo->PlayerController.Get();
		
		if (EffectProperties.SourceController == nullptr && EffectProperties.SourceAvatarActor != nullptr)
		{
			if (const APawn* Pawn = Cast<APawn>(EffectProperties.SourceAvatarActor))
			{
				EffectProperties.SourceController = Pawn->GetController();
			}
		}
		if (EffectProperties.SourceController)
		{
			EffectProperties.SourceCharacter = Cast<ACharacter>(EffectProperties.SourceController->GetPawn());
		}
	}

	if (Data.Target.AbilityActorInfo.IsValid() && Data.Target.AbilityActorInfo->AvatarActor.IsValid())
	{
		EffectProperties.TargetAvatarActor = Data.Target.AbilityActorInfo->AvatarActor.Get();
		EffectProperties.TargetController = Data.Target.AbilityActorInfo->PlayerController.Get();
		EffectProperties.TargetCharacter = Cast<ACharacter>(EffectProperties.TargetAvatarActor);
		EffectProperties.TargetASC = UAbilitySystemBlueprintLibrary::GetAbilitySystemComponent(EffectProperties.TargetAvatarActor);
	}
	
}
	
