// Mech Sentinel Swarm - damage execution for hits on sentinels.

#pragma once

#include "CoreMinimal.h"
#include "GameplayEffectExecutionCalculation.h"
#include "ExecCalc_SentinelDamage.generated.h"

/**
 * Armor-mitigated damage into the IncomingDamage meta attribute of UMechSentinelAttributeSet.
 *
 *   RawDamage   = SetByCaller(MyTags::SetDamageByCaller)  (the same tag the player's abilities already use)
 *   Mitigation  = (k * Armor) / (1 + k * |Armor|)          k = rules ArmorMitigationPerPoint (default 0.06)
 *   Damage      = RawDamage * (1 - Mitigation)              negative armor amplifies damage
 *   Shielded    : Damage *= rules ShieldedDamageMultiplier
 *   Dead        : Damage  = 0
 *
 * Armor is captured from the target (the GAS proxy loaded with this sentinel's Mass values), so armor
 * buffs / shreds applied as duration effects are included automatically.
 */
UCLASS()
class AURA_API UExecCalc_SentinelDamage : public UGameplayEffectExecutionCalculation
{
	GENERATED_BODY()

public:
	UExecCalc_SentinelDamage();

	virtual void Execute_Implementation(const FGameplayEffectCustomExecutionParameters& ExecutionParams, FGameplayEffectCustomExecutionOutput& OutExecutionOutput) const override;

	/** Pure helper (also used by debug / UI to preview mitigation). */
	static float MitigateDamage(float RawDamage, float Armor, float ArmorPerPoint);
};
