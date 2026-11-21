// Mech Sentinel Swarm - damage execution for hits on sentinels.

#pragma once

#include "CoreMinimal.h"
#include "GameplayEffectExecutionCalculation.h"
#include "ExecCalc_SentinelDamage.generated.h"

/**
 * Armor-mitigated damage into the IncomingDamage meta attribute of UMechSentinelAttributeSet.
 *
 *   BaseDamage  = max(0, SetByCaller(MyTags::SetDamageByCaller))  (the same tag the player's abilities already use)
 *   AttackDmg   = the source's UMyAttributeSet AttackDamage, snapshot when the spec is made (0 when not captured)
 *   RawDamage   = BaseDamage > 0 ? BaseDamage + S * max(0, AttackDmg) : 0
 *                 S = rules SourceAttackDamageScale (default 1; 0 = flat damage)
 *   Mitigation  = (k * Armor) / (1 + k * |Armor|)          k = rules ArmorMitigationPerPoint (default 0.06)
 *   Damage      = RawDamage * (1 - Mitigation)              negative armor amplifies damage
 *   Shielded    : Damage *= rules ShieldedDamageMultiplier
 *   Dead        : Damage  = 0
 *
 * Armor is captured from the target (the GAS proxy loaded with this sentinel's Mass values), so armor
 * buffs / shreds applied as duration effects are included automatically. AttackDamage is captured from the effect
 * context's instigator ASC (a gun shot: the player's, buffs included). An instigator without an ASC (the combat
 * library then makes the spec on the proxy) or without UMyAttributeSet captures nothing: flat damage, no warning.
 * A base of 0 (effect-only specs: stuns, shields...) stays 0.
 */
UCLASS()
class AURA_API UExecCalc_SentinelDamage : public UGameplayEffectExecutionCalculation
{
	GENERATED_BODY()

public:
	UExecCalc_SentinelDamage();

	virtual void Execute_Implementation(const FGameplayEffectCustomExecutionParameters& ExecutionParams, FGameplayEffectCustomExecutionOutput& OutExecutionOutput) const override;

	/** Pure helper: damage before armor. A base <= 0 stays 0; negative AttackDamage or scale count as 0. */
	static float ComputeRawDamage(float BaseDamage, float SourceAttackDamage, float AttackDamageScale);

	/** Pure helper (also used by debug / UI to preview mitigation). */
	static float MitigateDamage(float RawDamage, float Armor, float ArmorPerPoint);
};
