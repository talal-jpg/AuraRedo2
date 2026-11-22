// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Engine/NetSerialization.h"
#include "GameplayEffectTypes.h"
#include "AirshipCannonball.generated.h"

class AAirshipPawn;
class UGameplayEffect;
class UNiagaraComponent;
class UNiagaraSystem;
class UProjectileMovementComponent;
class USphereComponent;
class UStaticMeshComponent;

/**
 * An airship cannonball: replicated, ballistic (gravity, no homing), swept by UProjectileMovementComponent on every
 * machine from the same launch point and velocity (movement is not replicated: the flight is deterministic enough,
 * and the server's impact wins). Only the server decides hits: it ignores its own ship and everything attached to it (the pilot), damages a
 * directly hit GAS actor with the ship's spec (the project's SetByCaller damage through UMyAttributeSet), splashes
 * damage around the impact, and damages Mech Sentinels along its path and in the blast. Then it hides, tells every
 * machine to play the impact (ImpactFX / BP_OnImpact) and goes away after ImpactDestroyDelay.
 */
UCLASS()
class AURA_API AAirshipCannonball : public AActor
{
	GENERATED_BODY()

public:

	AAirshipCannonball();

	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	virtual void Tick(float DeltaSeconds) override;

	/**
	 * Server, between SpawnActorDeferred and FinishSpawning: the ship that fired, the launch velocity (cm/s) and the
	 * damage spec (from the ship's ASC; its SetByCaller SetDamageByCaller is the direct-hit damage).
	 */
	void InitCannonball(AAirshipPawn* InShip, const FVector& InVelocity, const FGameplayEffectSpecHandle& InDamageSpec, float InDamage);

	/** Server: also ignore this actor (the other ball of the same broadside). */
	void IgnoreActor(AActor* Actor);

protected:

	virtual void BeginPlay() override;

	/** Every machine, at the impact. */
	UFUNCTION(BlueprintImplementableEvent, Category = "Airship|Cannonball", meta = (DisplayName = "On Impact"))
	void BP_OnImpact(FVector Location, FVector Normal);

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Airship|Cannonball")
	TObjectPtr<USphereComponent> CollisionSphere;

	/** Visual only (no collision). Set the mesh on the Blueprint. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Airship|Cannonball")
	TObjectPtr<UStaticMeshComponent> BallMesh;

	/** Trail (set the system on the Blueprint). */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Airship|Cannonball")
	TObjectPtr<UNiagaraComponent> TrailFX;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Airship|Cannonball")
	TObjectPtr<UProjectileMovementComponent> Movement;

	/** Collision radius (cm). */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Airship|Cannonball", meta = (ClampMin = "1.0"))
	float Radius = 28.f;

	/** Multiplies the world gravity on the ball. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Airship|Cannonball", meta = (ClampMin = "0.0"))
	float GravityScale = 1.f;

	/** Seconds before an unexploded ball is removed. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Airship|Cannonball", meta = (ClampMin = "0.1"))
	float MaxLifeSeconds = 8.f;

	/** Splash radius (cm) around the impact. GAS actors inside take damage falling from 1 at the centre to SplashMinFraction at the edge. 0 = no splash. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Airship|Cannonball", meta = (ClampMin = "0.0"))
	float SplashRadius = 450.f;

	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Airship|Cannonball", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float SplashMinFraction = 0.3f;

	/** Mech Sentinels: sweep radius along the flight (cm); they take the ball's damage once (rules' sentinel damage effect), the blast uses SplashRadius. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Airship|Cannonball", meta = (ClampMin = "0.0"))
	float SentinelHitRadius = 60.f;

	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Airship|Cannonball")
	bool bDamageSentinels = true;

	/** After the impact the ball is hidden and removed this much later (s), so the impact multicast arrives. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Airship|Cannonball", meta = (ClampMin = "0.05"))
	float ImpactDestroyDelay = 1.f;

	/** Spawned at the impact (every machine). */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Airship|Cannonball")
	TObjectPtr<UNiagaraSystem> ImpactFX;

	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Airship|Cannonball", meta = (ClampMin = "0.0"))
	float ImpactFXScale = 1.f;

	/** The ship that fired (ignored by the hits). */
	UPROPERTY(Replicated, VisibleInstanceOnly, BlueprintReadOnly, Category = "Airship|Cannonball")
	TObjectPtr<AAirshipPawn> SourceShip;

	/** Launch velocity, so a client starts the ball exactly like the server. */
	UPROPERTY(Replicated)
	FVector_NetQuantize10 LaunchVelocity;

	UFUNCTION(NetMulticast, Unreliable)
	void MulticastImpact(FVector_NetQuantize Location, FVector_NetQuantizeNormal Normal);

private:

	UFUNCTION()
	void OnProjectileStop(const FHitResult& ImpactResult);

	UFUNCTION()
	void OnSphereOverlap(UPrimitiveComponent* OverlappedComponent, AActor* OtherActor, UPrimitiveComponent* OtherComp, int32 OtherBodyIndex, bool bFromSweep, const FHitResult& SweepResult);

	/** Server: the ship and what rides on it. */
	bool ShouldIgnore(const AActor* Actor) const;

	/** Server: damage, splash, sentinels, multicast, hide. */
	void Explode(const FVector& Location, const FVector& Normal, AActor* DirectHit);

	/** Server: applies the spec scaled to Damage to Target's ASC. */
	void ApplyDamageTo(AActor* Target, float Damage) const;

	/**
	 * Server: queues a sentinel sweep (sphere of SweepRadius from Start to End) for the next tick (outside the Mass
	 * phases). Each sentinel takes damage once per ball. bSplash: damage falls off from Start like the GAS splash.
	 */
	void QueueSentinelSweep(const FVector& Start, const FVector& End, float SweepRadius, bool bSplash) const;

	FGameplayEffectSpecHandle DamageSpec;
	float Damage = 0.f;
	bool bExploded = false;
	FVector LastSweepLocation = FVector::ZeroVector;
	bool bHasLastSweepLocation = false;

	/** Server: sentinels this ball already damaged (handle index + serial), shared with the queued sweeps. */
	TSharedPtr<TSet<uint64>> SentinelsHit;
};
