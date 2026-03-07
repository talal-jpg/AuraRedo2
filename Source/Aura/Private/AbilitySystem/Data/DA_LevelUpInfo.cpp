// Fill out your copyright notice in the Description page of Project Settings.


#include "AbilitySystem/Data/DA_LevelUpInfo.h"

int32 UDA_LevelUpInfo::FindLevelForXP(int32 InXP)
{
	int32 Level=1;
	bool bSearching=true;
	while (bSearching)
	{
		if (LevelUpInfos.Num()-1<=Level) return Level;
		
		if (LevelUpInfos[Level].LevelUpXPRequirement<InXP)
		{
			Level++;
		}
		else
		{
			bSearching=false;
		}
	}
	return Level;
}
