// Fill out your copyright notice in the Description page of Project Settings.


#include "AbilitySystem/Data/DA_LevelUpInfo.h"

int32 UDA_LevelUpInfo::FindLevelForXp(int32 InXp)
{
	int32 Level=1;
	bool bSearching=true;
	while (bSearching)
	{
		if (LevelUpInfos.Num()-1<=Level) return Level;
		
		if (InXp>=LevelUpInfos[Level].XpRequired)
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
