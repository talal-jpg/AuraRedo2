// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "MyGameplayAbility.h"
#include "GA_GunShoot.generated.h"

class UMyAbilitySystemComponent;
/**
 * 
 */
UCLASS()
class AURA_API UGA_GunShoot : public UMyGameplayAbility
{
	GENERATED_BODY()
	
	UFUNCTION(BlueprintCallable)
	void MyFunc(FVector ImpactPoint,AActor* TargetActor);
	
public:	
	UPROPERTY(BlueprintReadOnly)
	UAbilitySystemComponent* TargetAsc;
	
	UPROPERTY(EditAnywhere)
	TSubclassOf<UGameplayEffect> DamageEffectClass;

	/**
	 * Mech Sentinels: the server also damages the sentinels along each shot. Sentinels are Mass entities without engine
	 * collision, so the crosshair trace (AT_SendMouseCursorData) passes through them; the shot is swept against their hit
	 * capsules instead, from the character along the aim. It stops at the first wall, which the server traces itself
	 * from the character's capsule on, or at the first character the crosshair trace hit. The task hands each shot to
	 * OnServerMouseCursorData before the graph sees it, so ending the ability on a shot still damages.
	 */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Mech Sentinels")
	bool bDamageSentinels = true;

	/** Damage per sentinel hit, before the sentinel's armor. Evaluated at the ability level. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Mech Sentinels", meta = (EditCondition = "bDamageSentinels"))
	FScalableFloat SentinelDamage = FScalableFloat(40.f);

	/** Effect for sentinel hits. Empty: the GameMode rules' DefaultSentinelDamageEffect (GE_SentinelDamage or the built-in one). */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Mech Sentinels", meta = (EditCondition = "bDamageSentinels"))
	TSubclassOf<UGameplayEffect> SentinelDamageEffect;

	/** Thickness of the shot, added to the sentinels' capsules: some slack for fast sentinels seen through latency. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Mech Sentinels", meta = (EditCondition = "bDamageSentinels", ClampMin = "0", ForceUnits = "cm"))
	float SentinelShotRadius = 15.f;

	/** How far sentinels can be shot when no wall or character stops the shot. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Mech Sentinels", meta = (EditCondition = "bDamageSentinels", ClampMin = "100", ForceUnits = "cm"))
	float SentinelShotRange = 20000.f;

	/** Sentinels one shot can hit: 1 = the closest one, 0 = every sentinel on the line (piercing). */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Mech Sentinels", meta = (EditCondition = "bDamageSentinels", ClampMin = "0"))
	int32 SentinelMaxTargets = 1;

	/** Server: a shot's target data from AT_SendMouseCursorData; damages the sentinels along it (later this frame). */
	virtual void OnServerMouseCursorData(const FGameplayAbilityTargetDataHandle& Data) override;

private:
	/**
	 * The segment swept against the sentinels for an aim trace. False when there is nothing to shoot along: no aim, or a
	 * start that a wall hides from the shooter's capsule.
	 */
	bool GetSentinelShotSegment(const FHitResult& AimHit, const AActor& Avatar, FVector& OutStart, FVector& OutEnd) const;

	/** The last shot damaged, kept alive so it is told apart from a replay of the same data (and not from a new shot that reused its memory). */
	TSharedPtr<FGameplayAbilityTargetData> LastSentinelShot;
};
