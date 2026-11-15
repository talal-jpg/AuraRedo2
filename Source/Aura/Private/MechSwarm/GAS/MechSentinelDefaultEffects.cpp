// Mech Sentinel Swarm - built-in damage effects, the defaults of UMechSentinelSwarmRules.

#include "MechSwarm/GAS/MechSentinelDefaultEffects.h"

#include "AbilitySystem/Data/MyGameplayTags.h"
#include "AbilitySystem/MyAttributeSet.h"
#include "MechSwarm/GAS/ExecCalc_SentinelDamage.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(MechSentinelDefaultEffects)

UMechSentinelDamageEffect::UMechSentinelDamageEffect()
{
	DurationPolicy = EGameplayEffectDurationType::Instant;

	// Reads SetByCaller SetDamageByCaller itself and writes the sentinel's IncomingDamage.
	FGameplayEffectExecutionDefinition& Execution = Executions.AddDefaulted_GetRef();
	Execution.CalculationClass = UExecCalc_SentinelDamage::StaticClass();
}

UMechSentinelAttackEffect::UMechSentinelAttackEffect()
{
	DurationPolicy = EGameplayEffectDurationType::Instant;

	FSetByCallerFloat SetByCaller;
	SetByCaller.DataTag = MyTags::SetDamageByCaller;

	FGameplayModifierInfo& Modifier = Modifiers.AddDefaulted_GetRef();
	Modifier.Attribute = UMyAttributeSet::GetIncomingDamageAttribute();
	Modifier.ModifierOp = EGameplayModOp::Additive;
	Modifier.ModifierMagnitude = FGameplayEffectModifierMagnitude(SetByCaller);
}
