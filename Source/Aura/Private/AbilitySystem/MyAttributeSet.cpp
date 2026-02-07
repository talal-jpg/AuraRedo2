// Fill out your copyright notice in the Description page of Project Settings.


#include "AbilitySystem/MyAttributeSet.h"

#include "AbilitySystem/Data/MyGameplayTags.h"
#include "Net/UnrealNetwork.h"

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
	
	InitHealth(50);
	InitMana(50);
	InitMaxHealth(100);
	InitMaxMana(100);
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
