// Mech Sentinel Swarm - drop-in capsule that lets any actor (projectile, sword, beam) hit sentinels.

#pragma once

#include "CoreMinimal.h"
#include "Components/CapsuleComponent.h"
#include "MechSwarm/Core/MechSentinelSwarmSubsystem.h"
#include "MechSentinelHitCapsuleComponent.generated.h"

class UGameplayEffect;

DECLARE_DYNAMIC_MULTICAST_DELEGATE_ThreeParams(FOnMechSentinelCapsuleHit, FMechSentinelHandle, Sentinel, FVector, ImpactPoint, float, DamageDealt);

/**
 * Add it to a projectile (or any moving actor). On the server it tests its capsule against the sentinels' simple
 * collision capsules every frame, sweeping from the previous position so fast projectiles cannot tunnel through,
 * and damages each sentinel once through GAS. Sentinels are Mass entities, not physics bodies: this component
 * does not use (or need) engine collision, so its own collision is off by default.
 */
UCLASS(ClassGroup = (MechSentinels), meta = (BlueprintSpawnableComponent))
class AURA_API UMechSentinelHitCapsuleComponent : public UCapsuleComponent
{
	GENERATED_BODY()

public:
	UMechSentinelHitCapsuleComponent();

	/** Tests now (e.g. on a melee swing frame). Returns the number of sentinels newly hit. */
	UFUNCTION(BlueprintCallable, BlueprintAuthorityOnly, Category = "Mech Sentinels|Hit")
	int32 ApplyHitsNow();

	/** Forgets which sentinels were hit, so they can be hit again (e.g. next melee swing). */
	UFUNCTION(BlueprintCallable, Category = "Mech Sentinels|Hit")
	void ResetHitSentinels();

	UFUNCTION(BlueprintCallable, Category = "Mech Sentinels|Hit")
	void SetHitsEnabled(bool bEnabled);

	/** Server: fired for every sentinel hit. */
	UPROPERTY(BlueprintAssignable, Category = "Mech Sentinels|Hit")
	FOnMechSentinelCapsuleHit OnSentinelHit;

	/** Damage per hit, before armor (SetByCaller MyTags::SetDamageByCaller). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Mech Sentinels|Hit", meta = (ClampMin = "0"))
	float Damage = 25.f;

	/** Damage effect; empty = the GameMode rules' DefaultSentinelDamageEffect. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Mech Sentinels|Hit")
	TSubclassOf<UGameplayEffect> DamageEffect;

	/** Extra effects applied to every sentinel hit (stun, slow...). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Mech Sentinels|Hit")
	TArray<TSubclassOf<UGameplayEffect>> ExtraEffects;

	/** How many different sentinels can be hit in total (1 = a normal bullet, 0 = unlimited / piercing). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Mech Sentinels|Hit", meta = (ClampMin = "0"))
	int32 MaxSentinelsHit = 1;

	/** Destroy the owning actor once MaxSentinelsHit is reached. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Mech Sentinels|Hit")
	bool bDestroyOwnerWhenSpent = true;

	/** Test every tick (projectiles). Off: only ApplyHitsNow (melee). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Mech Sentinels|Hit")
	bool bHitEveryTick = true;

	/** Sweep from last frame's position to the current one (no tunnelling for fast projectiles). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Mech Sentinels|Hit")
	bool bSweepFromLastPosition = true;

protected:
	virtual void BeginPlay() override;
	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

	AActor* GetDamageInstigator() const;

private:
	TSet<FMechSentinelHandle> HitSentinels;
	FVector LastLocation = FVector::ZeroVector;
	bool bHasLastLocation = false;
	bool bHitsEnabled = true;
	int32 TotalHits = 0;
};
