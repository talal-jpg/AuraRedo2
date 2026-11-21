// Mech Sentinel Swarm - damage execution for hits on sentinels.

#include "MechSwarm/GAS/ExecCalc_SentinelDamage.h"

#include "AbilitySystemComponent.h"
#include "AbilitySystem/Data/MyGameplayTags.h"
#include "AbilitySystem/MyAttributeSet.h"
#include "Engine/World.h"
#include "MechSwarm/Core/MechSentinelSwarmRules.h"
#include "MechSwarm/Core/MechSentinelSwarmSubsystem.h"
#include "MechSwarm/GAS/MechSentinelAttributeSet.h"
#include "MechSwarm/GAS/MechSentinelTags.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(ExecCalc_SentinelDamage)

namespace MechSwarm::DamageCapture
{
	struct FSentinelDamageStatics
	{
		DECLARE_ATTRIBUTE_CAPTUREDEF(Armor);

		/** Source UMyAttributeSet::AttackDamage (not the macro: the sentinel set has an AttackDamage too). */
		FGameplayEffectAttributeCaptureDefinition SourceAttackDamageDef;

		FSentinelDamageStatics()
		{
			// Not snapshotted: the proxy holds the entity's live values at execution time.
			DEFINE_ATTRIBUTE_CAPTUREDEF(UMechSentinelAttributeSet, Armor, Target, false);

			// Snapshot when the spec is made, like MMC_ProjectileDamage (a gun shot: on the server, before its timer).
			SourceAttackDamageDef = FGameplayEffectAttributeCaptureDefinition(UMyAttributeSet::GetAttackDamageAttribute(), EGameplayEffectAttributeCaptureSource::Source, true);
		}
	};

	static const FSentinelDamageStatics& Statics()
	{
		static FSentinelDamageStatics Instance;
		return Instance;
	}
}

UExecCalc_SentinelDamage::UExecCalc_SentinelDamage()
{
	RelevantAttributesToCapture.Add(MechSwarm::DamageCapture::Statics().ArmorDef);
	RelevantAttributesToCapture.Add(MechSwarm::DamageCapture::Statics().SourceAttackDamageDef);
}

float UExecCalc_SentinelDamage::ComputeRawDamage(const float BaseDamage, const float SourceAttackDamage, const float AttackDamageScale)
{
	return BaseDamage > 0.f ? BaseDamage + FMath::Max(0.f, AttackDamageScale) * FMath::Max(0.f, SourceAttackDamage) : 0.f;
}

float UExecCalc_SentinelDamage::MitigateDamage(const float RawDamage, const float Armor, const float ArmorPerPoint)
{
	const float Mitigation = (ArmorPerPoint * Armor) / (1.f + ArmorPerPoint * FMath::Abs(Armor));
	return FMath::Max(0.f, RawDamage * (1.f - Mitigation));
}

void UExecCalc_SentinelDamage::Execute_Implementation(const FGameplayEffectCustomExecutionParameters& ExecutionParams, FGameplayEffectCustomExecutionOutput& OutExecutionOutput) const
{
	const FGameplayEffectSpec& Spec = ExecutionParams.GetOwningSpec();

	const FGameplayTagContainer* TargetTags = Spec.CapturedTargetTags.GetAggregatedTags();
	if (TargetTags && TargetTags->HasTagExact(MechSentinelTags::State_Sentinel_Dead))
	{
		return;
	}

	FAggregatorEvaluateParameters EvalParams;
	EvalParams.SourceTags = Spec.CapturedSourceTags.GetAggregatedTags();
	EvalParams.TargetTags = TargetTags;

	float Armor = 0.f;
	ExecutionParams.AttemptCalculateCapturedAttributeMagnitude(MechSwarm::DamageCapture::Statics().ArmorDef, EvalParams, Armor);

	// No instigator ASC, or one without UMyAttributeSet: nothing was captured, the hit stays flat.
	float SourceAttackDamage = 0.f;
	if (!ExecutionParams.AttemptCalculateCapturedAttributeMagnitude(MechSwarm::DamageCapture::Statics().SourceAttackDamageDef, EvalParams, SourceAttackDamage))
	{
		SourceAttackDamage = 0.f;
	}

	const float BaseDamage = FMath::Max(0.f, Spec.GetSetByCallerMagnitude(MyTags::SetDamageByCaller, /*WarnIfNotFound*/false, 0.f));

	float ArmorPerPoint = 0.06f;
	float ShieldMultiplier = 0.25f;
	float AttackDamageScale = 1.f;
	const UAbilitySystemComponent* TargetASC = ExecutionParams.GetTargetAbilitySystemComponent();
	if (const UWorld* World = TargetASC ? TargetASC->GetWorld() : nullptr)
	{
		if (const UMechSentinelSwarmSubsystem* Swarm = World->GetSubsystem<UMechSentinelSwarmSubsystem>())
		{
			if (const UMechSentinelSwarmRules* Rules = Swarm->GetRules())
			{
				ArmorPerPoint = Rules->ArmorMitigationPerPoint;
				ShieldMultiplier = Rules->ShieldedDamageMultiplier;
				AttackDamageScale = Rules->SourceAttackDamageScale;
			}
		}
	}

	const float RawDamage = ComputeRawDamage(BaseDamage, SourceAttackDamage, AttackDamageScale);
	float Damage = MitigateDamage(RawDamage, Armor, ArmorPerPoint);
	if (TargetTags && TargetTags->HasTagExact(MechSentinelTags::State_Sentinel_Shielded))
	{
		Damage *= ShieldMultiplier;
	}

	if (Damage > 0.f)
	{
		OutExecutionOutput.AddOutputModifier(FGameplayModifierEvaluatedData(UMechSentinelAttributeSet::GetIncomingDamageAttribute(), EGameplayModOp::Override, Damage));
	}
}
