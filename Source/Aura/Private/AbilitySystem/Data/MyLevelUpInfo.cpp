// Fill out your copyright notice in the Description page of Project Settings.


#include "AbilitySystem/Data/MyLevelUpInfo.h"

int32 UMyLevelUpInfo::GetLevelForXP(int32 XP)
{
	int32 Level=1;
	bool bSearching = true;
	while(bSearching)
	{
		//Safety check to not check further entry if already at max level
		// first and last entries in the DA are only placeHolders 
		if (Level >= LevelUpInfos.Num() -1 ) return Level;
		
		if (XP>=LevelUpInfos[Level].NextLevelXP)
		{
			++Level;
		}
		else
		{
			bSearching=false;
		}
	}
	return Level;
}

void UMyLevelUpInfo::GetPointsRewardForLevel(int32 InLevel, int32& AttributePoints, int32& SpellPoints)
{
	AttributePoints=LevelUpInfos[InLevel].AttributePointsReward;
	SpellPoints=LevelUpInfos[InLevel].SpellPointsReward;
}

void UMyLevelUpInfo::GetAbilitiesForLevel(int32 InLevel, TArray<TSubclassOf<UGameplayAbility>>& Abilities)
{
	Abilities=LevelUpInfos[InLevel].AbilitiesUnlocked;
}
