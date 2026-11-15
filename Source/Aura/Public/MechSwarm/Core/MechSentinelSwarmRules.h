// Mech Sentinel Swarm - global, server side rules. Referenced by AMyGameMode (never DeveloperSettings).

#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "Templates/SubclassOf.h"
#include "MechSentinelSwarmRules.generated.h"

class UGameplayEffect;

/**
 * Global swarm rules. Assign one on the GameMode (BP_MyGameMode -> Mech Sentinels -> Sentinel Swarm Rules).
 * The GameMode exists only on the server, which is exactly where these rules are needed:
 * targeting, combat and spawning are server authoritative. Clients only need visuals, which come from
 * the entity config asset on the (replicated, level placed) wave spawner.
 */
UCLASS(BlueprintType)
class AURA_API UMechSentinelSwarmRules : public UPrimaryDataAsset
{
	GENERATED_BODY()

public:
	// Targeting

	/** How many sentinels may engage one player before newcomers pick another player or a fallback point. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Targeting", meta = (ClampMin = "1"))
	int32 MaxAttackersPerPlayer = 14;

	/** Seconds between target re-evaluations per sentinel (randomised +-30% so the swarm does not pulse). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Targeting", meta = (ClampMin = "0.05", ForceUnits = "s"))
	float RetargetInterval = 1.25f;

	/** Players farther than this (cm) are ignored. 0 = no limit. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Targeting", meta = (ClampMin = "0", ForceUnits = "cm"))
	float MaxTargetDistance = 0.f;

	// Combat

	/** Armor formula constant k: mitigation = k*Armor / (1 + k*|Armor|). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Combat", meta = (ClampMin = "0"))
	float ArmorMitigationPerPoint = 0.06f;

	/** Damage multiplier while State.Sentinel.Shielded is present. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Combat", meta = (ClampMin = "0", ClampMax = "1"))
	float ShieldedDamageMultiplier = 0.25f;

	/**
	 * Instant GE used to damage sentinels when callers do not pass their own.
	 * It should use UExecCalc_SentinelDamage and read the SetByCaller magnitude MyTags::SetDamageByCaller ("SetDamageByCaller").
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Combat")
	TSubclassOf<UGameplayEffect> DefaultSentinelDamageEffect;

	/**
	 * Instant GE a sentinel applies to the player it attacks. The SetByCaller magnitude MyTags::SetDamageByCaller is set
	 * to the sentinel's AttackDamage attribute, so the project's existing player damage GE (ExecCalc_Damage) works as is.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Combat")
	TSubclassOf<UGameplayEffect> SentinelAttackEffect;

	// Simulation

	/** Cell size (cm) of the spatial hash used by capsule hit queries. ~2x the biggest sentinel capsule is a good value. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Simulation", meta = (ClampMin = "50", ForceUnits = "cm"))
	float CollisionCellSize = 500.f;

	/** Hard cap for alive sentinels over all spawners. Spawners wait while the cap is reached. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Simulation", meta = (ClampMin = "1"))
	int32 MaxAliveSentinels = 1500;
};
