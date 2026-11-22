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

class AActor;
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

/** Self-buff slots, also the bit index in FMechSentinelStateFragment::BuffMask. */
enum class EMechSentinelSelfBuff : uint8 { Armor = 0, Speed = 1, Damage = 2, Num = 3 };

namespace MechSentinelSelfBuff
{
	constexpr int32 Num = int32(EMechSentinelSelfBuff::Num);

	/** BuffMask with the bit of every slot. */
	constexpr uint8 AllBits = uint8((1u << Num) - 1u);

	/** ISM custom data index of slot 0's fade (0..1, UMechSentinelVisualDataProcessor): 4 armor, 5 speed, 6 damage. */
	constexpr int32 FirstFadeCustomDataIndex = 4;
}

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

	/** Stacks GAS resolved for this effect (stacking GEs). */
	UPROPERTY()
	int32 StackCount = 1;

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

/**
 * The tag container and the effect list are UE containers (heap storage, relocatable), so Mass may move this
 * fragment's memory freely. Mass asserts trivially copyable fragments unless the author opts out like this
 * (the engine does the same for FMassReplicationViewerInfoFragment).
 */
template<>
struct TMassFragmentTraits<FMechSentinelGASFragment> final
{
	enum
	{
		AuthorAcceptsItsNotTriviallyCopyable = true
	};
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

	/** Active self-buffs, bit (1 << EMechSentinelSelfBuff). Server computes it, replicated to clients. */
	UPROPERTY(VisibleAnywhere, Category = "State")
	uint8 BuffMask = 0;
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

	/**
	 * Around a player: its horizontal heading is the sentinel's place on the orbit circle (turned by the steering).
	 * Around a fallback point: the 3D offset direction of the gathering spot.
	 */
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

	/**
	 * Distance (cm) to the target at which the sentinel switches to its attack state and starts firing (ranged) or
	 * hitting (melee). Keep it above the orbit's 3D reach, sqrt((OrbitRadius * (1 + OrbitRadiusJitter))^2 +
	 * (OrbitHeightMax + OrbitBobAmplitude)^2) (2134 cm with the defaults), or the outer sentinels never attack.
	 */
	UPROPERTY(EditAnywhere, Category = "Combat", meta = (ClampMin = "0", ForceUnits = "cm"))
	float AttackRange = 2500.f;

	/** Leaves the attack state when farther than AttackRange * this (hysteresis). */
	UPROPERTY(EditAnywhere, Category = "Combat", meta = (ClampMin = "1"))
	float AttackExitRangeScale = 1.25f;

	/**
	 * Ranged attacks: every attack fires a bullet at the target (UMechSentinelSwarmSubsystem::FireSentinelBullet) that
	 * deals the attack damage to the first player it meets on its way. Off: the attack hits at once (melee); a melee
	 * config should also bring AttackRange and OrbitRadius back to close range (about 450 / 320 cm).
	 */
	UPROPERTY(EditAnywhere, Category = "Combat|Bullets")
	bool bRangedAttack = true;

	/**
	 * Bullet speed (cm/s). Keep 7500: NS_MechSentinelBullet (a copy of the gun's PS_06_Flipbook_Sprites_my) flies its
	 * tracer at a fixed 7500 cm/s, so another speed makes hits and visuals disagree.
	 */
	UPROPERTY(EditAnywhere, Category = "Combat|Bullets", meta = (ClampMin = "100", ForceUnits = "cm/s", EditCondition = "bRangedAttack"))
	float BulletSpeed = 7500.f;

	/** How far a bullet flies when it meets nothing (cm). */
	UPROPERTY(EditAnywhere, Category = "Combat|Bullets", meta = (ClampMin = "100", ForceUnits = "cm", EditCondition = "bRangedAttack"))
	float BulletRange = 5000.f;

	/** Random aim error (cone half angle, degrees): some bullets miss. */
	UPROPERTY(EditAnywhere, Category = "Combat|Bullets", meta = (ClampMin = "0", ClampMax = "45", ForceUnits = "deg", EditCondition = "bRangedAttack"))
	float BulletSpreadDegrees = 2.f;

	/** Aim ahead of a moving target by its velocity * flight time * this (0 = aim where it is). */
	UPROPERTY(EditAnywhere, Category = "Combat|Bullets", meta = (ClampMin = "0", ClampMax = "2", EditCondition = "bRangedAttack"))
	float BulletLeadFactor = 0.8f;

	/** Thickness of a bullet when it is checked against players on arrival (cm). */
	UPROPERTY(EditAnywhere, Category = "Combat|Bullets", meta = (ClampMin = "0", ForceUnits = "cm", EditCondition = "bRangedAttack"))
	float BulletRadius = 30.f;

	/** Bullets start this far in front of the sentinel's centre (its gun / face), along the aim (cm). */
	UPROPERTY(EditAnywhere, Category = "Combat|Bullets", meta = (ClampMin = "0", ForceUnits = "cm", EditCondition = "bRangedAttack"))
	float MuzzleOffset = 90.f;

	/**
	 * Distance (cm) from the target at which attackers circle it (the Matrix swarm). Each sentinel picks its own radius
	 * within +- OrbitRadiusJitter. Should be below AttackRange so orbiting sentinels can fire.
	 */
	UPROPERTY(EditAnywhere, Category = "Steering", meta = (ClampMin = "0", ForceUnits = "cm"))
	float OrbitRadius = 1500.f;

	/** Per-sentinel orbit radius spread, as a fraction of OrbitRadius (0.25 = 75% to 125%). */
	UPROPERTY(EditAnywhere, Category = "Steering", meta = (ClampMin = "0", ClampMax = "0.9"))
	float OrbitRadiusJitter = 0.25f;

	/** Lowest orbit height above the target point (cm); each sentinel picks its own between Min and Max. */
	UPROPERTY(EditAnywhere, Category = "Steering", meta = (ClampMin = "0", ForceUnits = "cm"))
	float OrbitHeightMin = 200.f;

	/** Highest orbit height above the target point (cm). */
	UPROPERTY(EditAnywhere, Category = "Steering", meta = (ClampMin = "0", ForceUnits = "cm"))
	float OrbitHeightMax = 900.f;

	/** Up and down bob on the orbit (cm). */
	UPROPERTY(EditAnywhere, Category = "Steering", meta = (ClampMin = "0", ForceUnits = "cm"))
	float OrbitBobAmplitude = 120.f;

	/** Bob cycles per second. */
	UPROPERTY(EditAnywhere, Category = "Steering", meta = (ClampMin = "0", ForceUnits = "Hz"))
	float OrbitBobFrequency = 0.35f;

	/** Height (cm) added to the target actor location (aim at the torso / head, not the feet). */
	UPROPERTY(EditAnywhere, Category = "Steering", meta = (ForceUnits = "cm"))
	float TargetHeightOffset = 90.f;

	/**
	 * Speed (cm/s) at which attackers' orbit spots travel around their player (the swirling swarm look). Linear, so wide
	 * and tight orbits look alike; keep it well below MovementSpeed or the sentinels fall behind their spots.
	 */
	UPROPERTY(EditAnywhere, Category = "Steering", meta = (ClampMin = "0", ForceUnits = "cm/s"))
	float OrbitSpeed = 400.f;

	/** Per-sentinel orbit speed spread, as a fraction of OrbitSpeed. */
	UPROPERTY(EditAnywhere, Category = "Steering", meta = (ClampMin = "0", ClampMax = "1"))
	float OrbitSpeedJitter = 0.4f;

	/** Share of sentinels that circle the other way. */
	UPROPERTY(EditAnywhere, Category = "Steering", meta = (ClampMin = "0", ClampMax = "1"))
	float OrbitReverseChance = 0.35f;

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

	/**
	 * Stunned sentinels sink at the start of the stun, slowing to a stop over this many seconds, then hover in place
	 * (alive sentinels have no ground check, so they must not keep sinking during a long stun).
	 */
	UPROPERTY(EditAnywhere, Category = "Death", meta = (ClampMin = "0", ForceUnits = "s"))
	float StunnedSinkDuration = 0.6f;

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
// Server only
//----------------------------------------------------------------------//

/**
 * Server-only self-buff timers, read and written by UMechSentinelSelfBuffProcessor. Added by UMechSentinelTrait where the
 * swarm is simulated (not on NM_Client); the wave spawner jitters the timers at spawn.
 */
USTRUCT()
struct AURA_API FMechSentinelSelfBuffFragment : public FMassFragment
{
	GENERATED_BODY()

	/** Seconds until each buff (EMechSentinelSelfBuff order) may be cast again. */
	UPROPERTY(VisibleAnywhere, Category = "Self Buff")
	float Cooldown[3] = { 0.f, 0.f, 0.f };

	/** Seconds until the next buff decision. */
	UPROPERTY(VisibleAnywhere, Category = "Self Buff")
	float DecisionTimer = 0.f;

	/** The wave's SelfBuffChanceMultiplier: scales the rules' SelfBuffChance for this sentinel. */
	UPROPERTY(VisibleAnywhere, Category = "Self Buff")
	float ChanceScale = 1.f;
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
