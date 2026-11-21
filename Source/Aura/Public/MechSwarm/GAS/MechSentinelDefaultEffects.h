// Mech Sentinel Swarm - built-in damage and self-buff effects, the defaults of UMechSentinelSwarmRules.

#pragma once

#include "CoreMinimal.h"
#include "GameplayEffect.h"
#include "MechSentinelDefaultEffects.generated.h"

/**
 * Damage dealt to a sentinel: instant, runs UExecCalc_SentinelDamage on the SetByCaller magnitude
 * MyTags::SetDamageByCaller (armor mitigation, Shielded, no damage once Dead). The default of the rules'
 * DefaultSentinelDamageEffect, so hits work without any asset; GE_SentinelDamage is the same thing as an asset.
 */
UCLASS(meta = (DisplayName = "Mech Sentinel Damage (built-in)"))
class AURA_API UMechSentinelDamageEffect : public UGameplayEffect
{
	GENERATED_BODY()

public:
	UMechSentinelDamageEffect();
};

/**
 * Damage a sentinel deals to the player it attacks: instant, adds the SetByCaller magnitude MyTags::SetDamageByCaller
 * (the sentinel's AttackDamage) to the player's IncomingDamage, which UMyAttributeSet turns into health loss, hit react
 * and death. The default of the rules' SentinelAttackEffect; GE_SentinelAttack is the same thing as an asset. It skips
 * ExecCalc_Damage (block / crit rolls and their debug prints): assign a GE that runs it to use those.
 */
UCLASS(meta = (DisplayName = "Mech Sentinel Attack (built-in)"))
class AURA_API UMechSentinelAttackEffect : public UGameplayEffect
{
	GENERATED_BODY()

public:
	UMechSentinelAttackEffect();
};

/**
 * Self-buffs a sentinel casts on itself (UMechSentinelSelfBuffProcessor, the rules' ArmorBuff / SpeedBuff / DamageBuff).
 * Has Duration (a 5 s placeholder: the swarm locks the rules' Duration on the spec), one Multiply (Additive) modifier
 * with the SetByCaller magnitude MechSentinelTags::SetByCaller_SelfBuffMagnitude (the rules' Magnitude, e.g. 1.75 = x1.75
 * on top of the wave-scaled base). Nothing else on purpose: no granted tags (the swarm recognises the class), no chance,
 * stacking, period or cues, which the sentinel GAS bridge would re-run or drop on every evaluation.
 * Three classes, because a sentinel stores one active effect per class. A replacement GE in the rules should follow the
 * same rules; it counts as the buff when its class is (a child of) the rules' one or it grants State.Sentinel.Buff.*.
 */
UCLASS(meta = (DisplayName = "Mech Sentinel Armor Buff (built-in)"))
class AURA_API UMechSentinelArmorBuffEffect : public UGameplayEffect
{
	GENERATED_BODY()

public:
	UMechSentinelArmorBuffEffect();
};

/** Self-buff on UMechSentinelAttributeSet::MoveSpeedMultiplier, same setup as UMechSentinelArmorBuffEffect. */
UCLASS(meta = (DisplayName = "Mech Sentinel Speed Buff (built-in)"))
class AURA_API UMechSentinelSpeedBuffEffect : public UGameplayEffect
{
	GENERATED_BODY()

public:
	UMechSentinelSpeedBuffEffect();
};

/** Self-buff on UMechSentinelAttributeSet::AttackDamage (the damage of its attacks on players), same setup as UMechSentinelArmorBuffEffect. */
UCLASS(meta = (DisplayName = "Mech Sentinel Damage Buff (built-in)"))
class AURA_API UMechSentinelDamageBuffEffect : public UGameplayEffect
{
	GENERATED_BODY()

public:
	UMechSentinelDamageBuffEffect();
};
