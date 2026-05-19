// Fill out your copyright notice in the Description page of Project Settings.


#include "AbilitySystem/MyAttributeSet.h"

#include <string>

#include "AbilitySystemBlueprintLibrary.h"
#include "GameplayEffectExtension.h"
#include "MyGameMode.h"
#include "MyPlayerState.h"
#include "AbilitySystem/Data/MyGameplayTags.h"
#include "AbilitySystem/Data/MyLevelUpInfo.h"
#include "Interfaces/MyCombatInterface.h"
#include "Character/MyEnemyChar.h"
#include "GameFramework/Character.h"
#include "GeometryCollection/GeometryCollectionComponent.h"
#include "Interfaces/MyPlayerInterface.h"
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

void UMyAttributeSet::PostGameplayEffectExecute(FGameplayEffectModCallbackData& Data)
{
	Super::PostGameplayEffectExecute(Data);
	
	if (Data.EvaluatedData.Attribute == GetHealthAttribute())
	{
		SetHealth(FMath::Clamp(GetHealth(),0.0f,GetMaxHealth()));
	}
	
	if (Data.EvaluatedData.Attribute == GetManaAttribute())
	{
		SetMana(FMath::Clamp(GetMana(),0.0f,GetMaxMana()));
	}
	
	FEffectProperties Props;
	SetEffectProperties(Data,Props);
	
	if (Data.EvaluatedData.Attribute == GetIncomingDamageAttribute())
	{
		const float LocalIncomingDamage=GetIncomingDamage();
		SetIncomingDamage(0.f);
		if (LocalIncomingDamage>0.f)
		{
			const float NewHealth=GetHealth()-LocalIncomingDamage;
			SetHealth(FMath::Clamp(NewHealth,0.0f,GetMaxHealth()));
			
			const bool bFatal=NewHealth<=0.f;
			if (bFatal)
			{
				IMyCombatInterface* CombatInterface=Cast<IMyCombatInterface>(Props.TargetAvatarActor);
				if (CombatInterface)
				{
					CombatInterface->Die();
				}
				AMyEnemyChar* MyEnemyChar= Cast<AMyEnemyChar>(Props.TargetCharacter);
				
				if (!MyEnemyChar)return;
				
				int32 XPReward=UMyBPFuncLib::GetXPRewardForCharacterClass(MyEnemyChar->CharacterClass,MyEnemyChar->CharacterLevel,Props.TargetAvatarActor);
				
				// UKismetSystemLibrary::PrintString(Props.SourceAvatarActor,std::to_string(XPReward).c_str());
				FGameplayEventData EventData;
				EventData.EventTag=MyTags::Attribute_Meta_XP;
				EventData.EventMagnitude=XPReward;
				UAbilitySystemBlueprintLibrary::SendGameplayEventToActor(Props.SourceAvatarActor,MyTags::Attribute_Meta_XP,EventData);
				
			}
			else
			{
				bool Activated=Props.TargetASC->TryActivateAbilitiesByTag(MyTags::Ability_HitReact.GetTag().GetSingleTagContainer());
			}
			
			if (Props.SourceCharacter != Props.TargetCharacter)
			{
				if (AMyPlayerController* MyPC=Cast<AMyPlayerController>(Props.SourceController))
				{
					bool bIsCrit=UMyBPFuncLib::IsCrit(Props.EffectContextHandle,this);
					bool bIsBlocked= UMyBPFuncLib::IsBlocked(Props.EffectContextHandle);
					MyPC->ShowDamageNumber(LocalIncomingDamage,Props.TargetCharacter,bIsCrit,bIsBlocked);
				}
			}
		}
	}
	
	if (Data.EvaluatedData.Attribute == GetIncomingXPAttribute())
	{
		
		// FString Str=std::to_string(Data.EvaluatedData.Magnitude).c_str();
		
		// UKismetSystemLibrary::PrintString(Props.SourceAvatarActor,Str);
		// UKismetSystemLibrary::PrintString(Props.SourceAvatarActor,Str,true,true,FLinearColor::Black,30.f,FName("3"));
		//Getting IncomingXP From WaitingGA Now Update XP on PlayerState And LevelUp
		//Make PlayerInterface add to xp ,get xp to be funcs in that not CombatIF
		if (Props.SourceCharacter->Implements<UMyPlayerInterface>())
		{
			UMyLevelUpInfo* MyLevelUpInfo=Cast<ACharacter>(GetOwningAbilitySystemComponent()->GetAvatarActor())->GetPlayerState<AMyPlayerState>()->MyLevelUpInfo;
			
			checkf(MyLevelUpInfo,TEXT("PleaseSetLevelUpInfoOnPlayerStateSoThatItCanBePresentOnClientsAsWell"));
			
			int32 PreviousLevel=MyLevelUpInfo->GetLevelForXP(IMyPlayerInterface::Execute_GetXP(Props.SourceCharacter));
			
			IMyPlayerInterface::Execute_AddToXP(Props.SourceCharacter,Data.EvaluatedData.Magnitude);
			
			//Now check if and how many level ups and execute logic
			
			int32 CurrentLevel=MyLevelUpInfo->GetLevelForXP(IMyPlayerInterface::Execute_GetXP(Props.SourceCharacter));
			
			int32 NumLevelUps= CurrentLevel-PreviousLevel;
			
			// FString Str2=std::to_string(NumLevelUps).c_str();
			// UKismetSystemLibrary::PrintString(Props.SourceAvatarActor,Str2,true,true,FLinearColor::Black,30.f,FName("3"));
			
			if (NumLevelUps>0)
			{
				
				// int32 NumLoops=0;
				for (int32 Level=0; Level<NumLevelUps; Level++)
				{
					//Get Attrib pnt and spell Pnt reward for level from DA_LevelUpInfo
					
					int32 AttributePoints,SpellPoints;
					
					int32 AttributePointsAccumulate=0;
					int32 SpellPointsAccumulate=0;
					int32 LevelToQuery=PreviousLevel+Level;
					MyLevelUpInfo->GetPointsRewardForLevel(LevelToQuery,AttributePoints,SpellPoints);
					
					AttributePointsAccumulate+=AttributePoints;
					SpellPointsAccumulate+=SpellPoints;
					

					// FString Str3=std::to_string(AttributePointsAccumulate).c_str();
					// UKismetSystemLibrary::PrintString(Props.SourceAvatarActor,Str3,true,true,FLinearColor::Yellow,30.f,FName("4"));
					
					IMyPlayerInterface::Execute_AddToAttribPoints(Props.SourceCharacter,AttributePointsAccumulate);
					IMyPlayerInterface::Execute_AddToSpellPoints(Props.SourceCharacter,SpellPointsAccumulate);
					
					// NumLoops++;
					
				}
				// UKismetSystemLibrary::PrintString(Props.SourceAvatarActor,std::to_string(NumLoops).c_str(),true,true,FLinearColor::Red,30.f,FName("5"));
				IMyPlayerInterface::Execute_AddToLevel(Props.SourceCharacter,NumLevelUps);
				IMyPlayerInterface::Execute_LevelUp(Props.SourceCharacter);
			}
		}
	}
}

void UMyAttributeSet::PreAttributeChange(const FGameplayAttribute& Attribute, float& NewValue)
{
	Super::PreAttributeChange(Attribute, NewValue);
	if (Attribute== GetHealthAttribute())
	{
		NewValue=FMath::Clamp(NewValue,0.0f,GetMaxHealth());
	}
	
	if (Attribute== GetManaAttribute())
	{
		NewValue=FMath::Clamp(NewValue,0.0f,GetMaxMana());
	}
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
	DOREPLIFETIME_CONDITION_NOTIFY(UMyAttributeSet,TurnSpeed,COND_None,REPNOTIFY_Always);
	DOREPLIFETIME_CONDITION_NOTIFY(UMyAttributeSet,AttackDamage,COND_None,REPNOTIFY_Always);
	DOREPLIFETIME_CONDITION_NOTIFY(UMyAttributeSet,CritChance,COND_None,REPNOTIFY_Always);
	
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
	GAMEPLAYATTRIBUTE_REPNOTIFY(UMyAttributeSet,TurnSpeed,OldAttackDamage);
}

void UMyAttributeSet::OnRep_CritChance(const FGameplayAttributeData& OldCritChance)
{
	GAMEPLAYATTRIBUTE_REPNOTIFY(UMyAttributeSet,TurnSpeed,OldCritChance);
}

void UMyAttributeSet::SetEffectProperties(const FGameplayEffectModCallbackData& Data, FEffectProperties& Props)
{
	Props.EffectContextHandle=Data.EffectSpec.GetContext();
	Props.SourceASC=Props.EffectContextHandle.GetInstigatorAbilitySystemComponent();
	
	if ( IsValid(Props.SourceASC) && Props.SourceASC->AbilityActorInfo.IsValid() && Props.SourceASC->AbilityActorInfo.Get()->AvatarActor.IsValid())
	{
		Props.SourceAvatarActor=Props.SourceASC->AbilityActorInfo.Get()->AvatarActor.Get();
		Props.SourceController=Props.SourceASC->AbilityActorInfo.Get()->PlayerController.Get();
		if (Props.SourceController == nullptr && Props.SourceAvatarActor != nullptr)
		{
			if (const APawn* Pawn= Cast<APawn>(Props.SourceAvatarActor))
			{
				Props.SourceController=Pawn->GetController();
			}
		}
		if (Props.SourceController)
		{
			Props.SourceCharacter= Cast<ACharacter>(Props.SourceController->GetPawn());
		}
	}
	
	if ( Data.Target.AbilityActorInfo.IsValid() && Data.Target.AbilityActorInfo.Get()->AvatarActor.IsValid())
	{
		Props.TargetAvatarActor = Data.Target.AbilityActorInfo->AvatarActor.Get();
		Props.TargetController= Data.Target.AbilityActorInfo->PlayerController.Get();
		Props.TargetCharacter= Cast<ACharacter>(Props.TargetAvatarActor);
		Props.TargetASC= UAbilitySystemBlueprintLibrary::GetAbilitySystemComponent(Props.TargetAvatarActor);
	}
}
