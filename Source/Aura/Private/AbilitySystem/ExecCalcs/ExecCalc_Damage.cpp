// Fill out your copyright notice in the Description page of Project Settings.


#include "AbilitySystem/ExecCalcs/ExecCalc_Damage.h"

#include <string>

#include "AbilitySystem/MyAttributeSet.h"
#include "AbilitySystem/Data/MyGameplayTags.h"
#include "Kismet/KismetArrayLibrary.h"
#include "Kismet/KismetSystemLibrary.h"

struct FDamageStatics
{
	DECLARE_ATTRIBUTE_CAPTUREDEF(Armor)
	DECLARE_ATTRIBUTE_CAPTUREDEF(IncomingDamage)
	DECLARE_ATTRIBUTE_CAPTUREDEF(CritChance)
	
	FDamageStatics()
	{
		DEFINE_ATTRIBUTE_CAPTUREDEF(UMyAttributeSet,Armor,Target,true);
		DEFINE_ATTRIBUTE_CAPTUREDEF(UMyAttributeSet,IncomingDamage,Target,true);
		DEFINE_ATTRIBUTE_CAPTUREDEF(UMyAttributeSet,CritChance,Source,true);
	};
};

static const FDamageStatics& DamageStatics()
{
	static FDamageStatics DStatics;
	return DStatics;
}

UExecCalc_Damage::UExecCalc_Damage()
{
	RelevantAttributesToCapture.Add(DamageStatics().ArmorDef);
	RelevantAttributesToCapture.Add(DamageStatics().CritChanceDef);
	
}

void UExecCalc_Damage::Execute_Implementation(const FGameplayEffectCustomExecutionParameters& ExecutionParams,FGameplayEffectCustomExecutionOutput& OutExecutionOutput) const
{
	const UAbilitySystemComponent* SourceASC=ExecutionParams.GetSourceAbilitySystemComponent();
	const UAbilitySystemComponent* TargetASC=ExecutionParams.GetTargetAbilitySystemComponent();
	
	const AActor* SourceAvatar=SourceASC->GetAvatarActor();
	const AActor* TargetAvatar=TargetASC->GetAvatarActor();
	
	const FGameplayEffectSpec& Spec= ExecutionParams.GetOwningSpec();
	
	FAggregatorEvaluateParameters Params;
	Params.SourceTags=Spec.CapturedSourceTags.GetAggregatedTags();
	Params.TargetTags=Spec.CapturedTargetTags.GetAggregatedTags();
	
	float Armor=0.f;
	float CritChance=0.f;
	
	ExecutionParams.AttemptCalculateCapturedAttributeMagnitude(DamageStatics().ArmorDef,Params,Armor);
	ExecutionParams.AttemptCalculateCapturedAttributeMagnitude(DamageStatics().CritChanceDef,Params,CritChance);
	
	
	
	float Damage=Spec.GetSetByCallerMagnitude(MyTags::SetDamageByCaller);
	
	int32 RandIntBlock=FMath::RandRange(0,100);
	int32 RandIntCrit=FMath::RandRange(0,100);
	
	UKismetSystemLibrary::PrintString(GetWorld(),std::to_string(CritChance).c_str());
	
	Damage= RandIntBlock<Armor ? Damage* .5f : Damage;
	Damage= RandIntCrit<CritChance ? Damage* 2.f : Damage;
	
	
	FGameplayModifierEvaluatedData EvaluatedData(DamageStatics().IncomingDamageProperty,EGameplayModOp::Additive,Damage);
	OutExecutionOutput.AddOutputModifier(EvaluatedData);
	
}
