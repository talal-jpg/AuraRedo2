// Mech Sentinel Swarm - built-in damage effects, the defaults of UMechSentinelSwarmRules.

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
