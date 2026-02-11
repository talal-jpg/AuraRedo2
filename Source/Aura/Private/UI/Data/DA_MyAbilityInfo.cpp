// Fill out your copyright notice in the Description page of Project Settings.


#include "UI/Data/DA_MyAbilityInfo.h"

FAbilityInfo UDA_MyAbilityInfo::GetAbilityInfoForTag(FGameplayTag AbilityTag)
{
	for(const FAbilityInfo& AbilityInfo:AbilityInfos)
	{
		if(AbilityInfo.AbilityTag==AbilityTag)
		{
			return AbilityInfo;
		}
	}
	return FAbilityInfo();
}
