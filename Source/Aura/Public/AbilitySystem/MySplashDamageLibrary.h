// Splash (area) damage: every enemy around a point takes damage, GAS characters and Mech Sentinels alike.

#pragma once

#include "CoreMinimal.h"
#include "GameplayEffect.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "MechSwarm/Core/MechSentinelSwarmSubsystem.h"
#include "MySplashDamageLibrary.generated.h"

class UAbilitySystemComponent;

/**
 * Damage for characters without an asset: instant, adds the SetByCaller magnitude MyTags::SetDamageByCaller to the
 * target's IncomingDamage, which UMyAttributeSet turns into health loss, hit react, death and damage numbers. The
 * default effect of the splash functions and of GA_Beam's character hits. It skips ExecCalc_Damage (its block / crit
 * rolls): assign a GE that runs it to use those.
 */
UCLASS(meta = (DisplayName = "SetByCaller Damage (built-in)"))
class AURA_API UMySetByCallerDamageEffect : public UGameplayEffect
{
	GENERATED_BODY()

public:
	UMySetByCallerDamageEffect();
};

/** Who a splash reaches and how its damage is applied (the damage amount itself is passed separately). */
USTRUCT(BlueprintType)
struct AURA_API FMySplashDamageSettings
{
	GENERATED_BODY()

	/** Enemies whose collision (characters) or hit capsule (sentinels) is within this distance of the centre are hit. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Splash", meta = (ClampMin = "0", ForceUnits = "cm"))
	float Radius = 600.f;

	/**
	 * Damage multiplier for an enemy at the edge of Radius, linear from 1 at the centre. 1 = the same damage everywhere.
	 * It scales the SetByCaller MyTags::SetDamageByCaller, so only effects that read it fall off. Characters with the
	 * built-in effect: their whole damage. Sentinels (ExecCalc_SentinelDamage): only the base, the instigator's
	 * AttackDamage bonus stays whole, and a base scaled to 0 deals no damage at all (the bonus is only added to a base
	 * above 0).
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Splash", meta = (ClampMin = "0", ClampMax = "1"))
	float EdgeDamageScale = 1.f;

	/** GAS characters and pawns: anything whose ASC has UMyAttributeSet (enemies, the Burrower, airships, players). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Splash")
	bool bDamageCharacters = true;

	/** Also player characters (and ships players fly) other than the instigator. Off: no friendly fire. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Splash", meta = (EditCondition = "bDamageCharacters"))
	bool bDamagePlayers = true;

	/** Mech Sentinels (the swarm). Server only: their hit capsules only exist on the authority. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Splash")
	bool bDamageSentinels = true;

	/** Characters hit at most, closest first. 0 = all. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Splash", meta = (ClampMin = "0", EditCondition = "bDamageCharacters"))
	int32 MaxCharacters = 0;

	/** Sentinels hit at most, closest first. 0 = all. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Splash", meta = (ClampMin = "0", EditCondition = "bDamageSentinels"))
	int32 MaxSentinels = 0;

	/** Effect for characters, given the damage as SetByCaller MyTags::SetDamageByCaller. Empty: UMySetByCallerDamageEffect. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Splash", meta = (EditCondition = "bDamageCharacters"))
	TSubclassOf<UGameplayEffect> CharacterDamageEffect;

	/** Effect for sentinels (should run ExecCalc_SentinelDamage). Empty: the GameMode rules' DefaultSentinelDamageEffect. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Splash", meta = (EditCondition = "bDamageSentinels"))
	TSubclassOf<UGameplayEffect> SentinelDamageEffect;
};

/** What a splash hit. */
USTRUCT(BlueprintType)
struct AURA_API FMySplashDamageResult
{
	GENERATED_BODY()

	/** Characters the damage effect was applied to (the actor that owns the hit ASC's avatar), closest first. */
	UPROPERTY(BlueprintReadOnly, Category = "Splash")
	TArray<TObjectPtr<AActor>> Characters;

	/** Sentinels the damage effect was applied to, closest first. */
	UPROPERTY(BlueprintReadOnly, Category = "Splash")
	TArray<FMechSentinelHit> Sentinels;

	/** Health actually removed from the sentinels. */
	UPROPERTY(BlueprintReadOnly, Category = "Splash")
	float SentinelDamageDealt = 0.f;

	int32 Num() const { return Characters.Num() + Sentinels.Num(); }
};

UCLASS()
class AURA_API UMySplashDamageLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	/**
	 * Every enemy around Center: characters and pawns whose ASC has UMyAttributeSet, alive, other than Instigator (and
	 * whatever is attached to it), found by an overlap of Pawn, PhysicsBody, Vehicle and WorldDynamic collision; and the
	 * Mech Sentinels whose hit capsule touches the sphere (server only, 0 on clients). Both lists are sorted closest first.
	 * @param Instigator      Never in the result, nor anything sharing its ability system (its weapon, its player state).
	 * @param bIncludePlayers Player characters and ships other than the instigator count as enemies.
	 * @param IgnoreActors    Left out as well (e.g. the enemy the hit itself already damaged).
	 * @return the number of enemies found.
	 */
	UFUNCTION(BlueprintCallable, Category = "Combat|Splash", meta = (WorldContext = "WorldContextObject", AutoCreateRefTerm = "IgnoreActors", AdvancedDisplay = "IgnoreActors"))
	static int32 GetEnemiesInRadius(const UObject* WorldContextObject, AActor* Instigator, FVector Center, float Radius, bool bIncludePlayers, bool bIncludeSentinels,
		const TArray<AActor*>& IgnoreActors, TArray<AActor*>& OutCharacters, TArray<FMechSentinelHit>& OutSentinels);

	/**
	 * THE splash function: every enemy around Center (see GetEnemiesInRadius) takes Damage through GAS. Characters get
	 * Settings.CharacterDamageEffect; sentinels get Settings.SentinelDamageEffect, where Damage is the base that
	 * ExecCalc_SentinelDamage adds the instigator's AttackDamage to before their armor. The instigator's ASC is the effect
	 * source when it has one (damage numbers, kill XP).
	 * Server. Hitting sentinels must happen outside the Mass phases: from input, an anim notify or an ability event, go
	 * through Set Timer for Next Tick and call it from there (GA_Beam does).
	 * @param Instigator     Who deals the damage. Pass the pawn, not its controller.
	 * @param IgnoreActors   Not damaged (e.g. the enemy a hit already damaged).
	 * @param IgnoreSentinel Not damaged (e.g. the sentinel a hit already damaged).
	 * @return what was hit.
	 */
	UFUNCTION(BlueprintCallable, BlueprintAuthorityOnly, Category = "Combat|Splash", meta = (WorldContext = "WorldContextObject", AutoCreateRefTerm = "IgnoreActors", AdvancedDisplay = "IgnoreActors,IgnoreSentinel"))
	static FMySplashDamageResult ApplySplashDamage(const UObject* WorldContextObject, AActor* Instigator, FVector Center, float Damage, const FMySplashDamageSettings& Settings,
		const TArray<AActor*>& IgnoreActors, FMechSentinelHandle IgnoreSentinel);

	//----------------------------------------------------------------------//
	// C++
	//----------------------------------------------------------------------//

	/**
	 * ApplySplashDamage with specs the caller made (e.g. an ability's MakeOutgoingGameplayEffectSpec, so its level, tags and
	 * source go with the damage). Each spec carries its damage as SetByCaller MyTags::SetDamageByCaller; falloff scales a
	 * copy of it per enemy. An invalid spec skips that kind of enemy. Server, outside the Mass phases.
	 */
	static FMySplashDamageResult ApplySplashDamageWithSpecs(UWorld& World, const AActor* Instigator, const FVector& Center, const FMySplashDamageSettings& Settings,
		const FGameplayEffectSpecHandle& CharacterSpec, const FGameplayEffectSpecHandle& SentinelSpec, TConstArrayView<const AActor*> IgnoreActors, FMechSentinelHandle IgnoreSentinel);

	/** The actor whose ability system takes damage for Actor: Actor or the first actor it is attached to with an ASC that has UMyAttributeSet. Null when none. */
	static AActor* FindDamageableActor(AActor* Actor);

	/** Actor (see FindDamageableActor) is something Instigator can damage: an ASC with UMyAttributeSet that is not the instigator's, alive, and not a player unless bIncludePlayers. */
	static bool IsDamageableEnemy(const AActor* Actor, const AActor* Instigator, bool bIncludePlayers);

	/** Player characters and ships players fly: the ASC lives on a player state, or the pawn is player controlled. */
	static bool IsPlayerActor(const AActor* Actor, const UAbilitySystemComponent* ASC);

	/** Damage multiplier at Distance from the centre of a splash of Radius (1 at the centre, EdgeDamageScale at the edge). */
	static float GetFalloffScale(float Distance, float Radius, float EdgeDamageScale);

	/** Applies Spec to Target, with its SetByCaller MyTags::SetDamageByCaller multiplied by Scale when Scale is not 1. */
	static void ApplyScaledSpecToCharacter(const FGameplayEffectSpec& Spec, UAbilitySystemComponent& Target, float Scale);

	/** Same for a sentinel. Returns the health removed. */
	static float ApplyScaledSpecToSentinel(UMechSentinelSwarmSubsystem& Swarm, const FGameplayEffectSpec& Spec, const FMechSentinelHit& Hit, float Scale);

private:
	struct FCharacterCandidate
	{
		AActor* Actor = nullptr;
		UAbilitySystemComponent* ASC = nullptr;
		float Distance = 0.f;
	};

	/** The characters within Radius of Center, sorted closest first (Distance = from Center to their nearest overlapping collision). */
	static void GatherCharacters(const UWorld& World, const AActor* Instigator, const FVector& Center, float Radius, bool bIncludePlayers,
		TConstArrayView<const AActor*> IgnoreActors, TArray<FCharacterCandidate>& OutCandidates);

	/** The living sentinels touching the sphere, sorted closest first (Distance = from Center to the sentinel's axis). Authority only. */
	static void GatherSentinels(const UMechSentinelSwarmSubsystem& Swarm, const FVector& Center, float Radius, FMechSentinelHandle IgnoreSentinel, TArray<FMechSentinelHit>& OutHits);
};
