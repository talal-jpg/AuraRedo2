// Mech Sentinel Swarm - Blueprint / C++ entry points to hit sentinels with actors through their simple collision capsules.

#pragma once

#include "CoreMinimal.h"
#include "GameplayEffectTypes.h"
#include "GameplayTagContainer.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "MechSwarm/Core/MechSentinelSwarmSubsystem.h"
#include "MechSentinelCombatLibrary.generated.h"

class UGameplayEffect;

/** Snapshot of a sentinel's Mass data (server values; on clients only location / state / health fraction are meaningful). */
USTRUCT(BlueprintType)
struct AURA_API FMechSentinelInfo
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly, Category = "Sentinel")
	FVector Location = FVector::ZeroVector;

	UPROPERTY(BlueprintReadOnly, Category = "Sentinel")
	EMechSentinelState State = EMechSentinelState::Seeking;

	UPROPERTY(BlueprintReadOnly, Category = "Sentinel")
	float Health = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "Sentinel")
	float MaxHealth = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "Sentinel")
	float Armor = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "Sentinel")
	float AttackDamage = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "Sentinel")
	float AttackSpeed = 0.f;

	/** Gameplay tags granted by active effects (Stunned, Shielded, Dead...). Server only. */
	UPROPERTY(BlueprintReadOnly, Category = "Sentinel")
	FGameplayTagContainer OwnedTags;
};

UCLASS()
class AURA_API UMechSentinelCombatLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	//----------------------------------------------------------------------//
	// Queries (server: the collision hash is built on the authority)
	//----------------------------------------------------------------------//

	/** Sentinels whose collision capsule overlaps a capsule (UE convention: axis = Rotation's up vector, HalfHeight includes the caps). Sorted by distance to the bottom end. */
	UFUNCTION(BlueprintCallable, Category = "Mech Sentinels|Combat", meta = (WorldContext = "WorldContextObject"))
	static int32 FindSentinelsInCapsule(const UObject* WorldContextObject, FVector Center, FRotator Rotation, float Radius, float HalfHeight, TArray<FMechSentinelHit>& OutHits);

	/** Sentinels touched by a sphere of Radius swept from Start to End (projectiles, beams, melee arcs). Sorted along the sweep. */
	UFUNCTION(BlueprintCallable, Category = "Mech Sentinels|Combat", meta = (WorldContext = "WorldContextObject"))
	static int32 SweepSentinels(const UObject* WorldContextObject, FVector Start, FVector End, float Radius, TArray<FMechSentinelHit>& OutHits);

	//----------------------------------------------------------------------//
	// Damage / effects (server)
	//----------------------------------------------------------------------//

	/**
	 * THE hit function: every sentinel whose simple collision capsule touches the given capsule takes Damage through GAS
	 * (DamageEffect, or the rules' DefaultSentinelDamageEffect: armor mitigation, Shielded, Dead...).
	 * Server. Call it outside the Mass phases: from input, an anim notify or an actor tick, go through Set Timer for
	 * Next Tick.
	 * @param Instigator    Who dealt the damage (its ASC is the effect source when it has one). Pass the pawn, not
	 *                      its controller, which has no ASC: the player's AttackDamage would not be added.
	 * @param Damage        Base damage per sentinel; UExecCalc_SentinelDamage adds the source's AttackDamage (x the
	 *                      rules' SourceAttackDamageScale) to a base above 0, then applies armor.
	 * @param MaxTargets    0 = everyone in the capsule, otherwise the closest N.
	 * @return number of sentinels hit. OutTotalDamage is the health actually removed.
	 */
	UFUNCTION(BlueprintCallable, BlueprintAuthorityOnly, Category = "Mech Sentinels|Combat", meta = (WorldContext = "WorldContextObject", AdvancedDisplay = "DamageEffect,MaxTargets"))
	static int32 ApplyDamageToSentinelsInCapsule(const UObject* WorldContextObject, AActor* Instigator, FVector Center, FRotator Rotation, float Radius, float HalfHeight,
		float Damage, TSubclassOf<UGameplayEffect> DamageEffect, int32 MaxTargets, TArray<FMechSentinelHit>& OutHits, float& OutTotalDamage);

	/** Same as ApplyDamageToSentinelsInCapsule but for a sweep (sphere of Radius from Start to End). Server. Call it outside the Mass phases: from input, an anim notify or an actor tick, go through Set Timer for Next Tick. */
	UFUNCTION(BlueprintCallable, BlueprintAuthorityOnly, Category = "Mech Sentinels|Combat", meta = (WorldContext = "WorldContextObject", AdvancedDisplay = "DamageEffect,MaxTargets"))
	static int32 ApplyDamageToSentinelsInSweep(const UObject* WorldContextObject, AActor* Instigator, FVector Start, FVector End, float Radius,
		float Damage, TSubclassOf<UGameplayEffect> DamageEffect, int32 MaxTargets, TArray<FMechSentinelHit>& OutHits, float& OutTotalDamage);

	/** Applies any gameplay effect (stun, shield, slow, buff...) to the sentinels in a capsule. Server. Call it outside the Mass phases: from input, an anim notify or an actor tick, go through Set Timer for Next Tick. */
	UFUNCTION(BlueprintCallable, BlueprintAuthorityOnly, Category = "Mech Sentinels|Combat", meta = (WorldContext = "WorldContextObject", AdvancedDisplay = "Level,MaxTargets"))
	static int32 ApplyEffectToSentinelsInCapsule(const UObject* WorldContextObject, AActor* Instigator, FVector Center, FRotator Rotation, float Radius, float HalfHeight,
		TSubclassOf<UGameplayEffect> Effect, float Level, int32 MaxTargets);

	/** Damages one sentinel (Damage is the base, see ApplyDamageToSentinelsInCapsule). Returns the health removed. Server. Call it outside the Mass phases: from input, an anim notify or an actor tick, go through Set Timer for Next Tick. */
	UFUNCTION(BlueprintCallable, BlueprintAuthorityOnly, Category = "Mech Sentinels|Combat", meta = (WorldContext = "WorldContextObject", AdvancedDisplay = "DamageEffect"))
	static float ApplyDamageToSentinel(const UObject* WorldContextObject, AActor* Instigator, FMechSentinelHandle Sentinel, float Damage, FVector HitLocation, TSubclassOf<UGameplayEffect> DamageEffect);

	/** Runs an existing spec (e.g. from an ability) against one sentinel. Returns the health removed. Server. Call it outside the Mass phases: from input, an anim notify or an actor tick, go through Set Timer for Next Tick. */
	UFUNCTION(BlueprintCallable, BlueprintAuthorityOnly, Category = "Mech Sentinels|Combat", meta = (WorldContext = "WorldContextObject"))
	static float ApplyGameplayEffectSpecToSentinel(const UObject* WorldContextObject, const FGameplayEffectSpecHandle& SpecHandle, FMechSentinelHandle Sentinel, FVector HitLocation);

	//----------------------------------------------------------------------//
	// Info
	//----------------------------------------------------------------------//

	UFUNCTION(BlueprintPure, Category = "Mech Sentinels|Combat", meta = (WorldContext = "WorldContextObject"))
	static bool GetSentinelInfo(const UObject* WorldContextObject, FMechSentinelHandle Sentinel, FMechSentinelInfo& OutInfo);

	UFUNCTION(BlueprintPure, Category = "Mech Sentinels|Combat", meta = (WorldContext = "WorldContextObject"))
	static bool IsSentinelAlive(const UObject* WorldContextObject, FMechSentinelHandle Sentinel);

	//----------------------------------------------------------------------//
	// C++ helpers
	//----------------------------------------------------------------------//

	/**
	 * Damage spec for sentinels: Effect (or the rules default) with SetByCaller MyTags::SetDamageByCaller = Damage, the
	 * base (UExecCalc_SentinelDamage adds the source's AttackDamage). The instigator's ASC is the source when it has
	 * one; otherwise the proxy ASC makes the spec and nothing is captured (flat damage). Invalid handle when no effect
	 * is set up.
	 */
	static FGameplayEffectSpecHandle MakeSentinelDamageSpec(const UObject* WorldContextObject, AActor* Instigator, float Damage, TSubclassOf<UGameplayEffect> Effect, float Level = 1.f);

	/** Applies one spec to a list of hits (respecting MaxTargets). Returns the number of sentinels the spec was applied to. */
	static int32 ApplySpecToHits(UMechSentinelSwarmSubsystem& Swarm, const FGameplayEffectSpec& Spec, TArray<FMechSentinelHit>& InOutHits, int32 MaxTargets, float* OutTotalDamage = nullptr);

	/** Segment of a UE style capsule (axis = up vector of Rotation). */
	static void GetCapsuleSegment(const FVector& Center, const FRotator& Rotation, float Radius, float HalfHeight, FVector& OutA, FVector& OutB);

	/**
	 * Server: the segment to sweep against the sentinels for a crosshair shot (AT_SendMouseCursorData's hit result), shared
	 * by GA_GunShoot and GA_Beam. Sentinels are Mass entities without engine collision, so the crosshair trace passes
	 * through them. The segment runs along the aim, from the point of the aim line nearest Avatar, and stops at the first
	 * wall (traced here from Avatar's capsule on; pawns, the airship's hull included, and local physics debris are
	 * looked past), at the crosshair trace's first hit when that lies
	 * ahead, or after MaxRange. A client aim that starts far from Avatar or passes far from it is replaced by Avatar's own
	 * view. False when there is nothing to shoot along: no aim, or a start that a wall hides from Avatar.
	 */
	static bool GetAimShotSegment(const FHitResult& AimHit, const AActor& Avatar, double MaxRange, FVector& OutStart, FVector& OutEnd);

	/**
	 * Server: no wall between From and To, by GetAimShotSegment's rules (the crosshair trace's channel, pawns and local
	 * physics debris looked past). Avatar, IgnoreActors and what is attached to them are left out.
	 */
	static bool IsAimPathClear(const AActor& Avatar, const FVector& From, const FVector& To, TConstArrayView<const AActor*> IgnoreActors);

	/**
	 * How fast Point moves along with Actor: a physics-simulating root's velocity at Point (its rotation included, e.g. the
	 * airship's hull), else the actor's velocity plus the base a character stands on (an airship's deck).
	 */
	static FVector GetMoveVelocityAt(const AActor& Actor, const FVector& Point);
};
