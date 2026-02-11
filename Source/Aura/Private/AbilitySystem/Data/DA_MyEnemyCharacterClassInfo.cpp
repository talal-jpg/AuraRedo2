// Fill out your copyright notice in the Description page of Project Settings.


#include "AbilitySystem/Data/DA_MyEnemyCharacterClassInfo.h"

FEnemyCharClassInfo UDA_MyEnemyCharacterClassInfo::GetInfoForClass(ECharacterClass Class)
{
	for (auto CharClassInfo:EnemyCharClassInfos)
	{
		if(CharClassInfo.Class==Class)
		{
			return CharClassInfo;
		}
	}
	return FEnemyCharClassInfo();
}
