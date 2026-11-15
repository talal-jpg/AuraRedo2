// Mech Sentinel Swarm - sentinel specific Mass data.
//
// Mass owns every sentinel value (health, armor, state, target...). GAS only computes on a proxy and
// the results are written back here. See MyMechEntitySystemReadme.md for the full data flow.

#pragma once

#include "CoreMinimal.h"
#include "GameplayTagContainer.h"
#include "MassEntityTypes.h"
#include "Mass/EntityHandle.h"
#include "Templates/SubclassOf.h"
#include "MechSentinelFragments.generated.h"

class UGameplayEffect;
class UAbilitySystemComponent;

UENUM(BlueprintType)
enum class EMechSentinelState : uint8
{
	Seeking,
	Attacking,
	Stunned,
	Dead
};

/** Blueprint friendly wrapper of FMassEntityHandle. */
USTRUCT(BlueprintType)
struct AURA_API FMechSentinelHandle
{
	GENERATED_BODY()

	FMechSentinelHandle() = default;
	explicit FMechSentinelHandle(const FMassEntityHandle Entity)
		: Index(Entity.Index), SerialNumber(Entity.SerialNumber)
	{
	}

	FMassEntityHandle ToEntity() const { return FMassEntityHandle(Index, SerialNumber); }
	bool IsSet() const { return SerialNumber != 0; }

	bool operator==(const FMechSentinelHandle& Other) const { return Index == Other.Index && SerialNumber == Other.SerialNumber; }

	friend uint32 GetTypeHash(const FMechSentinelHandle& Handle) { return HashCombine(::GetTypeHash(Handle.Index), ::GetTypeHash(Handle.SerialNumber)); }

	UPROPERTY(BlueprintReadOnly, Category = "Sentinel")
	int32 Index = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Sentinel")
	int32 SerialNumber = 0;
};

//----------------------------------------------------------------------//
// Tags
//----------------------------------------------------------------------//

/** Every sentinel entity carries this. */
USTRUCT()
struct AURA_API FMechSentinelTag : public FMassTag
{
	GENERATED_BODY()
};

/** Attack state: close enough to hit the target character. */
USTRUCT()
struct AURA_API FMechSentinelAttackingTag : public FMassTag
{
	GENERATED_BODY()
};

/** Mirror of the State.Sentinel.Stunned gameplay tag. */
USTRUCT()
struct AURA_API FMechSentinelStunnedTag : public FMassTag
{
	GENERATED_BODY()
};

/** Mirror of the State.Sentinel.Dead gameplay tag. Dead sentinels fall, then get destroyed. */
USTRUCT()
struct AURA_API FMechSentinelDeadTag : public FMassTag
{
	GENERATED_BODY()
};

//----------------------------------------------------------------------//
// Attributes (the Mass side of GAS)
//----------------------------------------------------------------------//

/** Per-entity attribute storage. Base values are what spawn / permanent effects set, current values include active buffs. */
USTRUCT()
struct AURA_API FMechSentinelAttributesFragment : public FMassFragment
{
	GENERATED_BODY()

	UPROPERTY(VisibleAnywhere, Category = "Attributes")
	float Health = 100.f;

	UPROPERTY(VisibleAnywhere, Category = "Attributes")
	float MaxHealth = 100.f;

	UPROPERTY(VisibleAnywhere, Category = "Attributes")
	float BaseArmor = 0.f;

	UPROPERTY(VisibleAnywhere, Category = "Attributes")
	float Armor = 0.f;

	UPROPERTY(VisibleAnywhere, Category = "Attributes")
	float BaseAttackDamage = 10.f;

	UPROPERTY(VisibleAnywhere, Category = "Attributes")
	float AttackDamage = 10.f;

	/** Attacks per second. */
	UPROPERTY(VisibleAnywhere, Category = "Attributes")
	float BaseAttackSpeed = 1.f;

	UPROPERTY(VisibleAnywhere, Category = "Attributes")
	float AttackSpeed = 1.f;

	UPROPERTY(VisibleAnywhere, Category = "Attributes")
	float BaseMoveSpeedMultiplier = 1.f;

	UPROPERTY(VisibleAnywhere, Category = "Attributes")
	float MoveSpeedMultiplier = 1.f;

	float GetHealthFraction() const { return MaxHealth > 0.f ? FMath::Clamp(Health / MaxHealth, 0.f, 1.f) : 0.f; }
};

/** Swarm-wide attributes shared by every sentinel of a swarm group (mutable shared fragment). */
USTRUCT()
struct AURA_API FMechSentinelSharedAttributesFragment : public FMassSharedFragment
{
	GENERATED_BODY()

	/** Separates swarms that should have independent shared values. Part of the shared fragment hash. */
	UPROPERTY(EditAnywhere, Category = "Attributes")
	FName SwarmGroup = NAME_None;

	/** Base movement speed (cm/s) for every sentinel in the group. Each sentinel scales it by its MoveSpeedMultiplier attribute. */
	UPROPERTY(EditAnywhere, Category = "Attributes", meta = (ClampMin = "0", ForceUnits = "cm/s"))
	float MovementSpeed = 900.f;
};

/** One active duration / infinite gameplay effect on a sentinel (stored in Mass, re-evaluated through the proxy). */
USTRUCT()
struct AURA_API FMechSentinelActiveEffect
{
	GENERATED_BODY()

	UPROPERTY()
	TSubclassOf<UGameplayEffect> EffectClass;

	UPROPERTY()
	float Level = 1.f;

	/** Seconds left, < 0 means infinite. */
	UPROPERTY()
	float RemainingTime = -1.f;

	UPROPERTY()
	TMap<FGameplayTag, float> SetByCallerMagnitudes;

	TWeakObjectPtr<UAbilitySystemComponent> InstigatorASC;
};

/** GAS view of the sentinel: owned gameplay tags and the active effects that produced them. */
USTRUCT()
struct AURA_API FMechSentinelGASFragment : public FMassFragment
{
	GENERATED_BODY()

	UPROPERTY(VisibleAnywhere, Category = "GAS")
	FGameplayTagContainer OwnedTags;

	UPROPERTY(VisibleAnywhere, Category = "GAS")
	TArray<FMechSentinelActiveEffect> ActiveEffects;
};

//----------------------------------------------------------------------//
// Behaviour
//----------------------------------------------------------------------//

USTRUCT()
struct AURA_API FMechSentinelStateFragment : public FMassFragment
{
	GENERATED_BODY()

	UPROPERTY(VisibleAnywhere, Category = "State")
	EMechSentinelState State = EMechSentinelState::Seeking;

	UPROPERTY(VisibleAnywhere, Category = "State")
	float TimeInState = 0.f;

	/** Counts down while dead; the entity is destroyed at 0. */
	UPROPERTY(VisibleAnywhere, Category = "State")
	float DeathTimeRemaining = 0.f;

	/** 1 when hit, fades to 0. Fed to the material through ISM custom data. */
	UPROPERTY(VisibleAnywhere, Category = "State")
	float HitFlash = 0.f;

	/** Incremented by the server on every damaging hit; clients flash when the replicated value changes. */
	uint8 HitSerial = 0;
};

/** Per-entity target assignment, chosen from the swarm's shared targeting board. */
USTRUCT()
struct AURA_API FMechSentinelTargetFragment : public FMassFragment
{
	GENERATED_BODY()

	/** Index into FMechSentinelTargetingSharedFragment::PlayerSlots, or INDEX_NONE. */
	int32 PlayerSlot = INDEX_NONE;

	/** Index into FMechSentinelTargetingSharedFragment::FallbackSlots, or INDEX_NONE. */
	int32 FallbackSlot = INDEX_NONE;

	/** Where the sentinel is heading (target centre, before the orbit offset). */
	FVector TargetLocation = FVector::ZeroVector;

	/** Random unit direction that spreads attackers on a sphere around the target. */
	FVector OrbitDirection = FVector::UpVector;

	/** Counts down to the next re-evaluation of the target. */
	float RetargetTimer = 0.f;

	/** Board serial seen at the last evaluation; a change (player joined / died) forces a re-evaluation. */
	uint32 BoardSerialSeen = 0;

	bool HasTarget() const { return PlayerSlot != INDEX_NONE || FallbackSlot != INDEX_NONE; }
};

USTRUCT()
struct AURA_API FMechSentinelAttackFragment : public FMassFragment
{
	GENERATED_BODY()

	/** Seconds until the next attack is allowed. */
	float Cooldown = 0.f;

	/** 1 on attack, fades to 0 (material glow / beam). */
	float AttackGlow = 0.f;

	/** Incremented by the server on every attack; clients glow when the replicated value changes. */
	uint8 AttackSerial = 0;
};

/** Read-only tuning shared by all sentinels of one entity config. */
USTRUCT()
struct AURA_API FMechSentinelParameters : public FMassConstSharedFragment
{
	GENERATED_BODY()

	/** Distance (cm) at which the sentinel switches to its attack state and can hit the target character. */
	UPROPERTY(EditAnywhere, Category = "Combat", meta = (ClampMin = "0", ForceUnits = "cm"))
	float AttackRange = 450.f;

	/** Leaves the attack state when farther than AttackRange * this (hysteresis). */
	UPROPERTY(EditAnywhere, Category = "Combat", meta = (ClampMin = "1"))
	float AttackExitRangeScale = 1.25f;

	/** Radius (cm) of the sphere attackers spread on around a player. Should be below AttackRange. */
	UPROPERTY(EditAnywhere, Category = "Steering", meta = (ClampMin = "0", ForceUnits = "cm"))
	float OrbitRadius = 320.f;

	/** Height (cm) added to the target actor location (aim at the torso / head, not the feet). */
	UPROPERTY(EditAnywhere, Category = "Steering", meta = (ForceUnits = "cm"))
	float TargetHeightOffset = 90.f;

	/** Attackers circle their player at this angular speed (deg/s), the swirling swarm look. */
	UPROPERTY(EditAnywhere, Category = "Steering", meta = (ForceUnits = "deg/s"))
	float OrbitAngularSpeed = 35.f;

	/** Organic wobble added to the steering, as a fraction of the movement speed. */
	UPROPERTY(EditAnywhere, Category = "Steering", meta = (ClampMin = "0", ClampMax = "1"))
	float WobbleAmount = 0.18f;

	/** Starts braking this far (cm) from the orbit point. */
	UPROPERTY(EditAnywhere, Category = "Steering", meta = (ClampMin = "1", ForceUnits = "cm"))
	float SlowdownRadius = 600.f;

	/** Fallback points: how close (cm) counts as "arrived" (then the sentinel loiters around it). */
	UPROPERTY(EditAnywhere, Category = "Steering", meta = (ClampMin = "0", ForceUnits = "cm"))
	float FallbackLoiterRadius = 900.f;

	/** Simple collision capsule for hits: radius (cm). Axis follows the sentinel's forward vector. */
	UPROPERTY(EditAnywhere, Category = "Collision", meta = (ClampMin = "1", ForceUnits = "cm"))
	float CapsuleRadius = 70.f;

	/** Simple collision capsule for hits: half height (cm), including the hemispherical caps. */
	UPROPERTY(EditAnywhere, Category = "Collision", meta = (ClampMin = "1", ForceUnits = "cm"))
	float CapsuleHalfHeight = 140.f;

	/** Seconds the wreck falls before the entity is destroyed. */
	UPROPERTY(EditAnywhere, Category = "Death", meta = (ClampMin = "0", ForceUnits = "s"))
	float DeathFallDuration = 2.5f;

	/** Gravity (cm/s^2) applied to dead and stunned sentinels. */
	UPROPERTY(EditAnywhere, Category = "Death", meta = (ClampMin = "0"))
	float FallGravity = 1400.f;

	/** Stunned sentinels sink at this fraction of gravity (they hover, but badly). */
	UPROPERTY(EditAnywhere, Category = "Death", meta = (ClampMin = "0", ClampMax = "1"))
	float StunnedGravityScale = 0.25f;

	/** Wrecks stop on WorldStatic geometry (one short line trace per falling wreck per frame) instead of falling through the floor. */
	UPROPERTY(EditAnywhere, Category = "Death")
	bool bWrecksCollideWithWorld = true;

	/** Tumble speed (deg/s) of a falling wreck. */
	UPROPERTY(EditAnywhere, Category = "Death", meta = (ClampMin = "0", ForceUnits = "deg/s"))
	float WreckTumbleSpeed = 220.f;
};

/** One candidate target on the shared board. */
USTRUCT()
struct AURA_API FMechSentinelTargetSlot
{
	GENERATED_BODY()

	TWeakObjectPtr<AActor> Actor;
	FVector Location = FVector::ZeroVector;
	int32 Claims = 0;
	/** Max sentinels engaging this slot (players: rules MaxAttackersPerPlayer, fallbacks: per point, 0 = unlimited). */
	int32 Capacity = 0;
	bool bValid = false;

	bool HasRoom() const { return bValid && (Capacity <= 0 || Claims < Capacity); }
};

/**
 * The shared target fragment: one targeting board per swarm group, shared by every sentinel of that group.
 * Refreshed once per frame on the authority by UMechSentinelTargetSelectionProcessor from the swarm subsystem
 * (players in the level + fallback points registered by spawners).
 */
USTRUCT()
struct AURA_API FMechSentinelTargetingSharedFragment : public FMassSharedFragment
{
	GENERATED_BODY()

	/** Part of the shared fragment hash: one board per group. */
	UPROPERTY(EditAnywhere, Category = "Targeting")
	FName SwarmGroup = NAME_None;

	TArray<FMechSentinelTargetSlot> PlayerSlots;
	TArray<FMechSentinelTargetSlot> FallbackSlots;

	/** Bumped whenever the set of valid slots changes. */
	uint32 BoardSerial = 1;
};

//----------------------------------------------------------------------//
// Client only
//----------------------------------------------------------------------//

/** Last replicated movement sample; only present on network clients (added by UMechSentinelTrait for NM_Client). */
USTRUCT()
struct AURA_API FMechSentinelNetSmoothingFragment : public FMassFragment
{
	GENERATED_BODY()

	FVector NetLocation = FVector::ZeroVector;
	FVector NetVelocity = FVector::ZeroVector;
	FQuat NetRotation = FQuat::Identity;
	double NetReceiveTime = 0.0;
	bool bHasSample = false;
};
