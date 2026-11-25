// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Engine/NetSerialization.h"
#include "GameplayEffectTypes.h"
#include "Match/MyMatchTypes.h"
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
 * and the server's impact wins). Only the server decides hits: it ignores its own ship, everything attached to it (the
 * pilot, gunners, turrets) and its deck riders, damages a directly hit GAS actor with the ship's spec (the project's
 * SetByCaller damage through UMyAttributeSet), splashes damage around the impact, and damages Mech Sentinels along its
 * path and in the blast. Then it hides, tells every machine to play the impact (ImpactFX / BP_OnImpact) and goes away
 * after ImpactDestroyDelay.
 *
 * The ball blocks the Visibility channel and has health in gun units (BallMaxHealth), so the character gun and the
 * ship turrets can shoot it down (ApplyShotDamage): it then bursts in the air with its impact FX and deals no damage.
 * The shoot-down replicates as state (bShotDown), so every client stops its copy, late or not.
 *
 * Team match (round 2 PR B, SPEC_B B6.2): the ball carries its ship's team (SourceTeamId, stored at spawn: the ship may
 * be gone when it lands) and spares that team's players, ships and turrets unless the rules allow friendly fire.
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
	 * Server, between SpawnActorDeferred and FinishSpawning: the ship that fired (and its team, SourceTeamId), the launch
	 * velocity (cm/s) and the damage spec (from the ship's ASC; its SetByCaller SetDamageByCaller is the direct-hit damage).
	 */
	void InitCannonball(AAirshipPawn* InShip, const FVector& InVelocity, const FGameplayEffectSpecHandle& InDamageSpec, float InDamage);

	/**
	 * The firing ship's team at spawn (server, replicated once): UMyTeamLibrary::GetTeamId reads it, so the friendly
	 * fire rule holds after the ship is gone (a gone ship would resolve to 255). 255 = a free ship's ball, or no match.
	 */
	UPROPERTY(Replicated, VisibleInstanceOnly, BlueprintReadOnly, Category = "Airship|Cannonball")
	uint8 SourceTeamId = MyMatch::NoTeam;

	/** Server: also ignore this actor (the other ball of the same broadside). */
	void IgnoreActor(AActor* Actor);

	/**
	 * Server: shot damage in gun units (1 = one character-gun hit; a turret bullet = TurretGunDamageMultiplier). At 0
	 * health the ball bursts in the air: impact FX, no damage, no splash. True if this hit shot it down. Clients: false.
	 */
	UFUNCTION(BlueprintCallable, BlueprintAuthorityOnly, Category = "Airship|Cannonball")
	bool ApplyShotDamage(float DamageUnits, AActor* DamageInstigator);

	/** Server value; clients see BallMaxHealth (only the server counts hits). */
	UFUNCTION(BlueprintPure, Category = "Airship|Cannonball")
	float GetBallHealth() const { return BallHealth; }

	UFUNCTION(BlueprintPure, Category = "Airship|Cannonball")
	float GetBallMaxHealth() const { return BallMaxHealth; }

	/** Every machine (replicated). */
	UFUNCTION(BlueprintPure, Category = "Airship|Cannonball")
	bool IsShotDown() const { return bShotDown; }

	/** Server: exploded or shot down (no longer a target). */
	bool IsSpent() const { return bExploded || bShotDown; }

	/** Every machine (replicated once, at spawn). */
	AAirshipPawn* GetSourceShip() const { return SourceShip; }

	/** The class default works on the CDO (the ship's ballistic aim and spawn offset read it there). */
	float GetRadius() const { return Radius; }

	/** The class default works on the CDO. */
	float GetGravityScale() const { return GravityScale; }

	/**
	 * Test hook (server): spawns a ball like the ship's FireCannons does, without a cannon. SourceShip may be null: no
	 * damage spec, so the ball is harmless (no GAS or sentinel damage) but still flies, bursts and can be shot down.
	 * With a ship, the spec is the built-in airship damage effect from the ship's ASC at the ship's level, SetByCaller
	 * Damage. GravityScaleOverride >= 0 replaces the class's GravityScale (replicated, so clients fly the same arc).
	 */
	UFUNCTION(BlueprintCallable, BlueprintAuthorityOnly, Category = "Airship|Test", meta = (WorldContext = "WorldContextObject"))
	static AAirshipCannonball* SpawnTestCannonball(UObject* WorldContextObject, TSubclassOf<AAirshipCannonball> BallClass,
		FVector Location, FVector Velocity, AAirshipPawn* SourceShip, float Damage = 60.f, float GravityScaleOverride = -1.f);

	/** Every machine, when the ball is shot down (after the impact FX). */
	UFUNCTION(BlueprintImplementableEvent, Category = "Airship|Cannonball", meta = (DisplayName = "On Shot Down"))
	void BP_OnShotDown(FVector Location);

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

	/** Collision radius (cm). 50: a 1 m ball, which turrets and the character gun can see and hit. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Airship|Cannonball", meta = (ClampMin = "1.0"))
	float Radius = 50.f;

	/**
	 * Multiplies the world gravity on the ball. 0.6 with the ship's 7000 cm/s keeps a usable range on a visible arc:
	 * level range at the cannons' 8.5 deg elevation cap = v^2 sin 17 / g' = 7000^2 x 0.292 / 588 = 244 m. Replicated
	 * once at spawn (a test ball's override reaches the clients); the ship's aim reads the class default.
	 */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Replicated, Category = "Airship|Cannonball", meta = (ClampMin = "0.0"))
	float GravityScale = 0.6f;

	/** Seconds before an unexploded ball is removed (a slow ball fired downhill from altitude flies longer than 8 s). */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Airship|Cannonball", meta = (ClampMin = "0.1"))
	float MaxLifeSeconds = 10.f;

	/** Splash radius (cm) around the impact. GAS actors inside take damage falling from 1 at the centre to SplashMinFraction at the edge. 0 = no splash. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Airship|Cannonball", meta = (ClampMin = "0.0"))
	float SplashRadius = 600.f;

	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Airship|Cannonball", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float SplashMinFraction = 0.3f;

	/** Mech Sentinels: sweep radius along the flight (cm, scaled with the ball); they take the ball's damage once (rules' sentinel damage effect), the blast uses SplashRadius. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Airship|Cannonball", meta = (ClampMin = "0.0"))
	float SentinelHitRadius = 100.f;

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

	/**
	 * Health in gun units (1 = one character-gun hit, a turret bullet = the project setting TurretGunDamageMultiplier),
	 * so it doesn't depend on the gun effect's damage value. 30: eight turret bullets, or a few players together.
	 * 0 = can't be shot down.
	 */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Airship|Cannonball", meta = (ClampMin = "0.0"))
	float BallMaxHealth = 30.f;

	/** A shot-down ball explodes like an impact (damage and splash) instead of bursting harmlessly. Off: shooting a ball down defuses it. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Airship|Cannonball")
	bool bSplashWhenShotDown = false;

	/** The ship that fired (ignored by the hits). */
	UPROPERTY(Replicated, VisibleInstanceOnly, BlueprintReadOnly, Category = "Airship|Cannonball")
	TObjectPtr<AAirshipPawn> SourceShip;

	/** Launch velocity, so a client starts the ball exactly like the server. */
	UPROPERTY(Replicated)
	FVector_NetQuantize10 LaunchVelocity;

	UFUNCTION(NetMulticast, Unreliable)
	void MulticastImpact(FVector_NetQuantize Location, FVector_NetQuantizeNormal Normal);

	/**
	 * Shot down (ApplyShotDamage). Replicated state rather than a multicast: MulticastImpact is unreliable, and a
	 * shot-down ball that kept flying on a client would read as a miss; state also reaches a client that joins late.
	 */
	UPROPERTY(ReplicatedUsing = OnRep_ShotDown)
	bool bShotDown = false;

	/** Where the server's ball was shot down (clients burst their copy there). */
	UPROPERTY(Replicated)
	FVector_NetQuantize ShotDownLocation = FVector::ZeroVector;

	UFUNCTION()
	void OnRep_ShotDown();

private:

	UFUNCTION()
	void OnProjectileStop(const FHitResult& ImpactResult);

	UFUNCTION()
	void OnSphereOverlap(UPrimitiveComponent* OverlappedComponent, AActor* OtherActor, UPrimitiveComponent* OtherComp, int32 OtherBodyIndex, bool bFromSweep, const FHitResult& SweepResult);

	/** Server: the ship and what rides on it, and (team match) the ship's teammates unless friendly fire is on. */
	bool ShouldIgnore(const AActor* Actor) const;

	/** Server: damage, splash, sentinels, multicast, hide. */
	void Explode(const FVector& Location, const FVector& Normal, AActor* DirectHit);

	/** Server: applies the spec scaled to Damage to Target's ASC. */
	void ApplyDamageTo(AActor* Target, float Damage) const;

	/** Every machine: stops, hides and turns off the shot-down ball (it stays until its life span ends, so the state replicates). */
	void EnterShotDownState();

	/** Every machine but a dedicated server: the impact burst at ShotDownLocation (ImpactFX, ImpactFXScale) + BP_OnShotDown. */
	void PlayShotDownFX();

	/** This machine already played the impact or shoot-down burst (the two can't play twice, whatever arrives first). */
	bool bImpactFXPlayed = false;

	/**
	 * Server: queues a sentinel sweep (sphere of SweepRadius from Start to End) for the next tick (outside the Mass
	 * phases). Each sentinel takes damage once per ball. bSplash: damage falls off from Start like the GAS splash.
	 */
	void QueueSentinelSweep(const FVector& Start, const FVector& End, float SweepRadius, bool bSplash) const;

	FGameplayEffectSpecHandle DamageSpec;
	float Damage = 0.f;
	bool bExploded = false;

	/** Server: gun units left (BallMaxHealth at BeginPlay; every machine starts there, only the server counts down). */
	float BallHealth = 0.f;
	FVector LastSweepLocation = FVector::ZeroVector;
	bool bHasLastSweepLocation = false;

	/** Server: sentinels this ball already damaged (handle index + serial), shared with the queued sweeps. */
	TSharedPtr<TSet<uint64>> SentinelsHit;
};
