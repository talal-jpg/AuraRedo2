// Mech Sentinel Swarm - built-in damage and self-buff effects, the defaults of UMechSentinelSwarmRules.

#include "MechSwarm/GAS/MechSentinelDefaultEffects.h"

#include "AbilitySystem/Data/MyGameplayTags.h"
#include "AbilitySystem/MyAttributeSet.h"
#include "MechSwarm/GAS/ExecCalc_SentinelDamage.h"
#include "MechSwarm/GAS/MechSentinelAttributeSet.h"
#include "MechSwarm/GAS/MechSentinelTags.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(MechSentinelDefaultEffects)

namespace MechSwarm::DefaultEffectsPrivate
{
	/** Placeholder only: the swarm locks the rules' Duration on every self-buff spec (SetDuration). */
	constexpr float SelfBuffPlaceholderDuration = 5.f;

	/** Has Duration, one Multiply (Additive) modifier on Attribute, magnitude SetByCaller SetByCaller_SelfBuffMagnitude. */
	void InitSelfBuff(UGameplayEffect& Effect, const FGameplayAttribute& Attribute)
	{
		Effect.DurationPolicy = EGameplayEffectDurationType::HasDuration;
		Effect.DurationMagnitude = FGameplayEffectModifierMagnitude(FScalableFloat(SelfBuffPlaceholderDuration));

		FSetByCallerFloat SetByCaller;
		SetByCaller.DataTag = MechSentinelTags::SetByCaller_SelfBuffMagnitude;

		// Multiply (Additive): x Magnitude on the wave-scaled base; several multipliers on one attribute (a designer slow,
		// say) add up as 1 + sum(m - 1).
		FGameplayModifierInfo& Modifier = Effect.Modifiers.AddDefaulted_GetRef();
		Modifier.Attribute = Attribute;
		Modifier.ModifierOp = EGameplayModOp::MultiplyAdditive;
		Modifier.ModifierMagnitude = FGameplayEffectModifierMagnitude(SetByCaller);
	}
}

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

UMechSentinelArmorBuffEffect::UMechSentinelArmorBuffEffect()
{
	MechSwarm::DefaultEffectsPrivate::InitSelfBuff(*this, UMechSentinelAttributeSet::GetArmorAttribute());
}

UMechSentinelSpeedBuffEffect::UMechSentinelSpeedBuffEffect()
{
	MechSwarm::DefaultEffectsPrivate::InitSelfBuff(*this, UMechSentinelAttributeSet::GetMoveSpeedMultiplierAttribute());
}

UMechSentinelDamageBuffEffect::UMechSentinelDamageBuffEffect()
{
	MechSwarm::DefaultEffectsPrivate::InitSelfBuff(*this, UMechSentinelAttributeSet::GetAttackDamageAttribute());
}
