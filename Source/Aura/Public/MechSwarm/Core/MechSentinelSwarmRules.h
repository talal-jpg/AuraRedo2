// Mech Sentinel Swarm - global, server side rules. Referenced by AMyGameMode (never DeveloperSettings).

#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "Templates/SubclassOf.h"
#include "MechSentinelSwarmRules.generated.h"

class UGameplayEffect;

/**
 * One self-buff a sentinel may cast on itself (UMechSentinelSelfBuffProcessor): a duration GE, how strong and long it is,
 * how often it may come back and when it is worth casting.
 */
USTRUCT(BlueprintType)
struct AURA_API FMechSentinelSelfBuffDef
{
	GENERATED_BODY()

	/**
	 * Has Duration GE with a modifier using the SetByCaller magnitude SetByCaller.MechSentinel.SelfBuffMagnitude (see the
	 * built-in UMechSentinelArmorBuffEffect). Null = this buff is off. Each buff needs its own class.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Self Buff")
	TSubclassOf<UGameplayEffect> Effect;

	/** SetByCaller magnitude: the attribute multiplier of the built-in effects (1.5 = +50%, on top of the wave scaling). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Self Buff", meta = (ClampMin = "0"))
	float Magnitude = 1.5f;

	/** Seconds the buff lasts (locked on the spec, whatever the GE's own duration says). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Self Buff", meta = (ClampMin = "0.1", ForceUnits = "s"))
	float Duration = 5.f;

	/** Seconds from one cast to the next possible one (counted from the cast, so it includes the Duration). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Self Buff", meta = (ClampMin = "0", ForceUnits = "s"))
	float Cooldown = 15.f;

	/** Relative chance of picking this buff when several are ready. 0 = never. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Self Buff", meta = (ClampMin = "0"))
	float Weight = 1.f;

	/** Cast only while the sentinel's target is at least this far (cm). 0 = no limit. A limit needs a target. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Self Buff", meta = (ClampMin = "0", ForceUnits = "cm"))
	float MinTargetDistance = 0.f;

	/** Cast only while the sentinel's target is at most this far (cm). 0 = no limit. A limit needs a target. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Self Buff", meta = (ClampMin = "0", ForceUnits = "cm"))
	float MaxTargetDistance = 0.f;
};

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
	UMechSentinelSwarmRules();

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
	 * Share of the attacker's AttackDamage (UMyAttributeSet on the effect's source ASC, read when the spec is made,
	 * buffs included) added to every hit on a sentinel, before armor: raw = base + this * AttackDamage. 0 = flat
	 * damage (the hit's SetByCaller base only). Hits with a base of 0 stay 0; sources without that set add nothing.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Combat", meta = (ClampMin = "0"))
	float SourceAttackDamageScale = 1.f;

	/**
	 * Instant GE used to damage sentinels when callers do not pass their own (GA_GunShoot, the hit capsule, the combat
	 * library). Defaults to the built-in UMechSentinelDamageEffect. A replacement should use UExecCalc_SentinelDamage and
	 * read the SetByCaller magnitude MyTags::SetDamageByCaller ("SetDamageByCaller"): only that execution applies armor
	 * and adds the attacker's AttackDamage (SourceAttackDamageScale).
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Combat")
	TSubclassOf<UGameplayEffect> DefaultSentinelDamageEffect;

	/**
	 * Instant GE a sentinel applies to the player it attacks, with the SetByCaller magnitude MyTags::SetDamageByCaller set
	 * to the sentinel's AttackDamage attribute. Defaults to the built-in UMechSentinelAttackEffect, which adds it to the
	 * player's IncomingDamage. A GE running the project's ExecCalc_Damage works too. Empty: attacks only show visually.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Combat")
	TSubclassOf<UGameplayEffect> SentinelAttackEffect;

	// Rewards

	/**
	 * XP the player who lands the killing hit gets for each sentinel. Sent like an enemy character's XP reward
	 * (UMyAttributeSet): the gameplay event Attribute.Meta.XP with this magnitude to the killer's avatar, whose
	 * GA_ListenForAttribEvents turns it into IncomingXP (the avatar needs that ability among its passive startup
	 * abilities). Only player avatars (IMyPlayerInterface) are rewarded; kills without an instigator (DespawnAll) give none. 0 = off.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Rewards", meta = (ClampMin = "0"))
	float KillXP = 10.f;

	// Simulation

	/** Cell size (cm) of the spatial hash used by capsule hit queries. ~2x the biggest sentinel capsule is a good value. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Simulation", meta = (ClampMin = "50", ForceUnits = "cm"))
	float CollisionCellSize = 500.f;

	/** Hard cap for alive sentinels over all spawners. Spawners wait while the cap is reached. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Simulation", meta = (ClampMin = "1"))
	int32 MaxAliveSentinels = 1500;

	// Self Buffs

	/** Sentinels cast the buffs below on themselves, at random, with cooldowns (server). Off: none are cast. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Self Buffs")
	bool bEnableSelfBuffs = true;

	/** Armor x Magnitude. Default: built-in UMechSentinelArmorBuffEffect, x1.75 for 6 s, every 18 s at most. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Self Buffs", meta = (EditCondition = "bEnableSelfBuffs"))
	FMechSentinelSelfBuffDef ArmorBuff;

	/** MoveSpeedMultiplier x Magnitude. Default: built-in, x1.5 for 4 s, every 12 s, only while the target is 15 m+ away. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Self Buffs", meta = (EditCondition = "bEnableSelfBuffs"))
	FMechSentinelSelfBuffDef SpeedBuff;

	/** AttackDamage x Magnitude. Default: built-in, x1.5 for 5 s, every 15 s, only while the target is within 25 m. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Self Buffs", meta = (EditCondition = "bEnableSelfBuffs"))
	FMechSentinelSelfBuffDef DamageBuff;

	/** Seconds between two buff decisions of a sentinel (randomised +-30% so the swarm does not buff in step). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Self Buffs", meta = (ClampMin = "0.05", ForceUnits = "s", EditCondition = "bEnableSelfBuffs"))
	float SelfBuffDecisionInterval = 1.5f;

	/**
	 * Chance that a decision casts a buff (one of the ready ones, by Weight), times the sentinel's wave
	 * SelfBuffChanceMultiplier, clamped to 1. Stunned sentinels skip their decisions.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Self Buffs", meta = (ClampMin = "0", ClampMax = "1", EditCondition = "bEnableSelfBuffs"))
	float SelfBuffChance = 0.25f;

	/** Casts applied per frame over the whole swarm (each costs two GAS evaluations); the rest wait for the next frames. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Self Buffs", meta = (ClampMin = "1", EditCondition = "bEnableSelfBuffs"))
	int32 MaxSelfBuffsPerFrame = 8;

	/** 0 Armor, 1 Speed, 2 Damage (EMechSentinelSelfBuff order). Out of range returns ArmorBuff. */
	const FMechSentinelSelfBuffDef& GetSelfBuffDef(int32 BuffIndex) const;
};
