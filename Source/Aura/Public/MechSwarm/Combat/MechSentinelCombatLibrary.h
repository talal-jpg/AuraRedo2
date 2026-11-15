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
	 * @param Instigator    Who dealt the damage (its ASC is the effect source when it has one).
	 * @param MaxTargets    0 = everyone in the capsule, otherwise the closest N.
	 * @return number of sentinels hit. OutTotalDamage is the health actually removed.
	 * Server. Call it outside the Mass phases: from input, an anim notify or an actor tick, go through Set Timer for Next Tick.
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

	/** Damages one sentinel. Returns the health removed. Server. Call it outside the Mass phases: from input, an anim notify or an actor tick, go through Set Timer for Next Tick. */
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

	/** Damage spec for sentinels: Effect (or the rules default) with SetByCaller MyTags::SetDamageByCaller = Damage. Invalid handle when no effect is set up. */
	static FGameplayEffectSpecHandle MakeSentinelDamageSpec(const UObject* WorldContextObject, AActor* Instigator, float Damage, TSubclassOf<UGameplayEffect> Effect, float Level = 1.f);

	/** Applies one spec to a list of hits (respecting MaxTargets). Returns the number of sentinels the spec was applied to. */
	static int32 ApplySpecToHits(UMechSentinelSwarmSubsystem& Swarm, const FGameplayEffectSpec& Spec, TArray<FMechSentinelHit>& InOutHits, int32 MaxTargets, float* OutTotalDamage = nullptr);

	/** Segment of a UE style capsule (axis = up vector of Rotation). */
	static void GetCapsuleSegment(const FVector& Center, const FRotator& Rotation, float Radius, float HalfHeight, FVector& OutA, FVector& OutB);
};
