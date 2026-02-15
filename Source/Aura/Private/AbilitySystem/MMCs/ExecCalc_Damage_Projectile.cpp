// Fill out your copyright notice in the Description page of Project Settings.


#include "AbilitySystem/MMCs/ExecCalc_Damage_Projectile.h"
#include "AbilitySystem/MyAttributeSet.h"
#include "Curves/BezierUtilities.h"

struct FDamageStatics
{
	DECLARE_ATTRIBUTE_CAPTUREDEF(AttackDamage)
	DECLARE_ATTRIBUTE_CAPTUREDEF(Armor)
	DECLARE_ATTRIBUTE_CAPTUREDEF(IncomingDamage)
	
	FDamageStatics()
	{
		DEFINE_ATTRIBUTE_CAPTUREDEF(UMyAttributeSet,AttackDamage,Source,true);
		DEFINE_ATTRIBUTE_CAPTUREDEF(UMyAttributeSet,Armor,Target,true);
		DEFINE_ATTRIBUTE_CAPTUREDEF(UMyAttributeSet,IncomingDamage,Target,true);
	}
	
};

static const FDamageStatics& GetDamageStaticsStruct()
{
	static FDamageStatics DamageStatics;
	return DamageStatics;
}

UExecCalc_Damage_Projectile::UExecCalc_Damage_Projectile()
{
	RelevantAttributesToCapture.Add(GetDamageStaticsStruct().AttackDamageDef);
	RelevantAttributesToCapture.Add(GetDamageStaticsStruct().ArmorDef);
}

void UExecCalc_Damage_Projectile::Execute_Implementation(
	const FGameplayEffectCustomExecutionParameters& ExecutionParams,
	FGameplayEffectCustomExecutionOutput& OutExecutionOutput) const
{
	
	FAggregatorEvaluateParameters EvalParams;
	FGameplayEffectSpec GESpec= ExecutionParams.GetOwningSpec();
	EvalParams.SourceTags=GESpec.CapturedSourceTags.GetAggregatedTags();
	EvalParams.TargetTags=GESpec.CapturedTargetTags.GetAggregatedTags();
	
	float AttackDamage=0.f;
	float Armor=0.f;
	float FinalOutgoingDamage=0.f;
	ExecutionParams.AttemptCalculateCapturedAttributeMagnitude(GetDamageStaticsStruct().AttackDamageDef,EvalParams,AttackDamage);
	ExecutionParams.AttemptCalculateCapturedAttributeMagnitude(GetDamageStaticsStruct().ArmorDef,EvalParams,Armor);
	
	FinalOutgoingDamage= AttackDamage-Armor;
	
	FGameplayModifierEvaluatedData EvalData=FGameplayModifierEvaluatedData(GetDamageStaticsStruct().IncomingDamageProperty,EGameplayModOp::Override,FinalOutgoingDamage);
	OutExecutionOutput.AddOutputModifier(EvalData);
}
