// Fill out your copyright notice in the Description page of Project Settings.


#include "AbilitySystem/MMCs/MMC_ProjectileDamage.h"

#include "AbilitySystem/MyAttributeSet.h"

UMMC_ProjectileDamage::UMMC_ProjectileDamage()
{
	AttackDamageDef= FGameplayEffectAttributeCaptureDefinition(UMyAttributeSet::GetAttackDamageAttribute(),EGameplayEffectAttributeCaptureSource::Source,true);
	
	RelevantAttributesToCapture.Add(AttackDamageDef);
}

float UMMC_ProjectileDamage::CalculateBaseMagnitude_Implementation(const FGameplayEffectSpec& Spec) const
{
	FAggregatorEvaluateParameters Params;
	Params.SourceTags= Spec.CapturedSourceTags.GetAggregatedTags();
	Params.TargetTags= Spec.CapturedTargetTags.GetAggregatedTags();
	float AttackDamage=0.f;
	// Spec.GetSetByCallerMagnitude();
	GetCapturedAttributeMagnitude(AttackDamageDef,Spec,Params,AttackDamage);
	
	return AttackDamage;
	
}
