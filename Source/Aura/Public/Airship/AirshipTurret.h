// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "AbilitySystemInterface.h"
#include "GameFramework/Actor.h"
#include "Interfaces/MyCombatInterface.h"
#include "Airship/AirshipTypes.h"
#include "AirshipTurret.generated.h"

class AAirshipCannonball;
class AAirshipPawn;
class UBoxComponent;
class UGameplayEffect;
class UMyAbilitySystemComponent;
class UMyAttributeSet;
class UNiagaraComponent;
class UNiagaraDataChannelAsset;
class UNiagaraSystem;
class USceneComponent;
class UStaticMeshComponent;
struct FCollisionQueryParams;

/**
 * A machine-gun turret on an airship's forward deck (Docs/Airship/round2/SPEC_A.md D6, NOTES_turret.md). Not a pawn:
 * the ship spawns two on the server (AAirshipPawn::SpawnTurrets), attaches them to its HullCollision without welding
 * and tells them every frame what to aim at and whether the trigger is held (SetServerCommand: the mounted gunner, the
 * pilot for an unmanned one, or the console). A gunner stays in their own character next to it.
 *
 * GAS like the ship: its own UMyAbilitySystemComponent + UMyAttributeSet (TurretMaxHealth), so every damage source of the
 * project hurts it; Health 0 -> Die -> a wreck that stays attached (fire FX, no shots, its HitBox still stops balls).
 *
 * Fire (server): hitscan along the real barrel at 1 / FireInterval rounds per second with SpreadDeg of spread and a heat
 * gauge (overheat locks it until it cools to OverheatRecover). A bullet deals TurretGunDamageMultiplier x the character
 * gun's damage per hit (read from GE_GunShootDamage at runtime) through the ship's ASC; it shoots enemy cannonballs
 * down (a sphere sweep along the shot, ApplyShotDamage in gun units) and damages Mech Sentinels on its line. It never
 * hits its own ship, that ship's turrets, its crew or its deck riders.
 *
 * Every machine aims the meshes (yaw base, pitch gun) and draws tracers into NDC_GunShootHit with TracerSystem: the
 * server sends each frame's shots in one unreliable multicast; the controlling client (its gunner, or the pilot's
 * machine for an unmanned turret) predicts its own shots from SetLocalCommand and skips that multicast while it does.
 *
 * Team match (round 2 PR B, SPEC_B B6.2, B6.4, B6.5): its rounds spare its ship's teammates (unless the rules allow
 * friendly fire) and look past their cannonballs like their own ship's; a round on a team ship or a team ship's turret
 * deals UMyMatchSettings::ShipDamageTurretRound instead of the gun-based bullet damage. Sentinel bullets damage it only
 * while its ship is driven (its ship sets the tag, AAirshipPawn::RefreshSentinelBulletTags).
 */
UCLASS(Blueprintable)
class AURA_API AAirshipTurret : public AActor, public IAbilitySystemInterface, public IMyCombatInterface
{
	GENERATED_BODY()

public:

	AAirshipTurret();

	virtual void Tick(float DeltaSeconds) override;

	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	/** Server, between SpawnActorDeferred and FinishSpawning: the ship, which turret this is (0 port, 1 starboard) and its mount. */
	void InitTurret(AAirshipPawn* InShip, int32 InTurretIndex, const FAirshipTurretMount& InMount);

	/** Server, every ship tick: what to aim at and whether the trigger is held (gunner, driver, console). */
	void SetServerCommand(const FAirshipTurretCommand& Command);

	/**
	 * The controlling client (its gunner, or the pilot's machine for an unmanned turret), every frame: local aim and
	 * predicted tracers. Ignored on the authority. Expires after LocalCommandTimeout.
	 */
	void SetLocalCommand(const FAirshipTurretCommand& Command);

	/** Server: wreck now (console, tests). */
	UFUNCTION(BlueprintCallable, BlueprintAuthorityOnly, Category = "Airship|Turret")
	void DestroyTurret();

	/**
	 * Server (round 2 PR B, SPEC_B B6.5): Damage through the turret's own damage effect on its own ASC (SetByCaller
	 * SetDamageByCaller), DamageInstigator in the context (null: the ship). The character gun's fixed hit on a team
	 * ship's turret uses it instead of its GE value. The spawn protection and the death rule apply as for any hit.
	 */
	void ApplyTurretDamage(float Damage, AActor* DamageInstigator);

	UFUNCTION(BlueprintPure, Category = "Airship|Turret")
	bool IsTurretDestroyed() const { return bDestroyed; }

	/** 0..1 (server: its gauge; clients: the replicated one). */
	UFUNCTION(BlueprintPure, Category = "Airship|Turret")
	float GetHeat01() const;

	UFUNCTION(BlueprintPure, Category = "Airship|Turret")
	bool IsOverheated() const { return bOverheated; }

	UFUNCTION(BlueprintPure, Category = "Airship|Turret")
	float GetHealth() const;

	UFUNCTION(BlueprintPure, Category = "Airship|Turret")
	float GetMaxHealth() const;

	UFUNCTION(BlueprintPure, Category = "Airship|Turret")
	int32 GetTurretIndex() const { return TurretIndex; }

	/** The ship it is mounted on (the replicated reference, else its owner, else its attach parent). */
	UFUNCTION(BlueprintPure, Category = "Airship|Turret")
	AAirshipPawn* GetShip() const;

	/** Shots this machine fired (server) or drew (clients: replicated + predicted tracers). Tests. */
	UFUNCTION(BlueprintPure, Category = "Airship|Turret")
	int32 GetShotCount() const { return ShotCount; }

	/** The meshes' aim on this machine (deg, mount-relative: yaw 0 = bow, + = toward starboard; pitch + = up). Tests. */
	UFUNCTION(BlueprintPure, Category = "Airship|Turret")
	float GetAimYawDeg() const { return CurrentYawDeg; }

	UFUNCTION(BlueprintPure, Category = "Airship|Turret")
	float GetAimPitchDeg() const { return CurrentPitchDeg; }

	/** True if WorldPoint is inside the yaw / pitch limits (+ ToleranceDeg), seen from the gun pivot. */
	bool IsAimInArc(const FVector& WorldPoint, float ToleranceDeg = 0.f) const;

	FVector GetMuzzleLocation() const;

	FVector GetBarrelDirection() const;

	const FAirshipTurretMount& GetMount() const { return Mount; }

	/** What hits the turret (AAirshipPawn::FindTurretBehindHullHit traces it: the mount sits inside the hull's collision). */
	UBoxComponent* GetHitBox() const { return HitBox; }

	/** Damage of one bullet: Settings->TurretGunDamageMultiplier x ReadGunBaseDamage() (the base is read once). */
	float GetBulletDamage() const;

	/**
	 * GE_GunShootDamage's additive IncomingDamage magnitudes at level 1 (Settings->GunDamageEffect,
	 * FGameplayEffectModifierMagnitude::GetStaticMagnitudeIfPossible), or Settings->GunDamageFallback when it can't be read
	 * statically (SetByCaller, attribute based, an execution): the same value GA_GunShoot::GetSentinelBaseDamage reads.
	 */
	static float ReadGunBaseDamage();

	// IAbilitySystemInterface
	virtual UAbilitySystemComponent* GetAbilitySystemComponent() const override;

	// IMyCombatInterface
	/** Server: UMyAttributeSet calls it at Health 0 (every fatal hit): the first one wrecks the turret. */
	virtual void Die() override;
	virtual bool IsDead_Implementation() override { return bDestroyed; }
	/** The ship's level, else 1. */
	virtual int32 GetLevel_Implementation() override;
	/** The muzzle. */
	virtual FVector GetCombatSocketLocation_Implementation() override;
	virtual FOnDeathDelegateSignature& GetOnDeathDelegate() override { return OnDeathDelegate; }

protected:

	virtual void BeginPlay() override;

	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

	/** Every machine, when the turret is wrecked. bExplosion: false for a client that joined after it happened. */
	UFUNCTION(BlueprintImplementableEvent, Category = "Airship|Turret", meta = (DisplayName = "On Turret Destroyed"))
	void BP_OnTurretDestroyed(bool bExplosion);


	// -------------------------------------------------------------------------
	// Components
	// -------------------------------------------------------------------------

	/** At the mount: the yaw axis on the deck top (z 0 = deck). */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Airship|Turret")
	TObjectPtr<USceneComponent> Root;

	/**
	 * What hits the turret: QueryOnly, WorldDynamic, blocks everything but Camera and Pawn (gun traces, sentinel bullet
	 * traces and cannonballs stop on it; characters walk through; overlap events for projectiles). Not part of the hull's
	 * simulated body (attached without welding).
	 */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Airship|Turret")
	TObjectPtr<UBoxComponent> HitBox;

	/** Yaw part (turns about Root's Z). No collision; set the mesh on the Blueprint (SM_AirshipTurret_Base). */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Airship|Turret")
	TObjectPtr<UStaticMeshComponent> BaseMesh;

	/** Pitch part, at (0, 0, PivotHeight) on the base; fires along its +X. No collision (SM_AirshipTurret_Gun). */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Airship|Turret")
	TObjectPtr<UStaticMeshComponent> GunMesh;

	/** Where the bullets leave, at (MuzzleForward, 0, 0) on the gun. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Airship|Turret")
	TObjectPtr<USceneComponent> Muzzle;

	/** Muzzle flash (auto-activate off; NS_AirshipTurretMuzzle on the Blueprint). Reset for each batch of shots. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Airship|Turret")
	TObjectPtr<UNiagaraComponent> MuzzleFXComponent;

	/** Burns while wrecked (auto-activate off; NS_AirshipTurretFire on the Blueprint). */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Airship|Turret")
	TObjectPtr<UNiagaraComponent> DestroyedFXComponent;

	/** Replicated, Mixed (UMyAbilitySystemComponent's constructor); InitializeComponent finds the attribute set. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Airship|Turret")
	TObjectPtr<UMyAbilitySystemComponent> AbilitySystemComponent;

	UPROPERTY()
	TObjectPtr<UMyAttributeSet> AttributeSet;


	// -------------------------------------------------------------------------
	// Tunables
	// -------------------------------------------------------------------------

	/** Seconds between two rounds (0.1 = 10 rounds/s). The starboard turret fires half an interval after the port one. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Airship|Turret", meta = (ClampMin = "0.02"))
	float FireInterval = 0.1f;

	/** Half angle (deg) of the cone a round leaves in around the barrel. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Airship|Turret", meta = (ClampMin = "0.0"))
	float SpreadDeg = 1.f;

	/** cm. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Airship|Turret", meta = (ClampMin = "100.0"))
	float Range = 25000.f;

	/** Heat per round (1 = overheated): 1/30 = 3 s of continuous fire at 10 rounds/s. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Airship|Turret", meta = (ClampMin = "0.0"))
	float HeatPerShot = 1.f / 30.f;

	/** Heat lost per second once it cools. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Airship|Turret", meta = (ClampMin = "0.0"))
	float CoolRate = 0.4f;

	/** Cooling starts this long (s) after the last round (longer than FireInterval: no cooling during a burst). */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Airship|Turret", meta = (ClampMin = "0.0"))
	float CoolDelay = 0.2f;

	/** An overheated gun fires again once its heat is down to this. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Airship|Turret", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float OverheatRecover = 0.35f;

	/** Slew rates (deg/s). */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Airship|Turret", meta = (ClampMin = "1.0"))
	float YawRateDeg = 180.f;

	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Airship|Turret", meta = (ClampMin = "1.0"))
	float PitchRateDeg = 120.f;

	/** Fires only while the aim point is within the mount's limits + this (deg); beyond, the gun waits at its limit. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Airship|Turret", meta = (ClampMin = "0.0"))
	float ArcToleranceDeg = 3.f;

	/** Set at BeginPlay (server): MaxHealth first, then Health = MaxHealth. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Airship|Turret", meta = (ClampMin = "1.0"))
	float TurretMaxHealth = 400.f;

	/** UExecCalc_Damage: percent chance a hit shows as blocked (cosmetic). */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Airship|Turret", meta = (ClampMin = "0.0", ClampMax = "100.0"))
	float TurretArmor = 0.f;

	/** Radius (cm) of the sweep along each round that finds enemy cannonballs (aim assist against 1 m balls). 0 = only the line. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Airship|Turret", meta = (ClampMin = "0.0"))
	float BallSweepRadius = 40.f;

	/** Mech Sentinels: capsule radius (cm) along each round and how many it may hit (the nearest first). */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Airship|Turret", meta = (ClampMin = "0.0"))
	float SentinelShotRadius = 20.f;

	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Airship|Turret", meta = (ClampMin = "0"))
	int32 SentinelMaxTargets = 1;

	/** Height (cm) of the gun's trunnion above the deck (GunMesh's place on the base; turret_dims.json). */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Airship|Turret", meta = (ClampMin = "0.0"))
	float PivotHeight = 150.f;

	/** Muzzle distance (cm) ahead of the trunnion along the barrel (turret_dims.json). */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Airship|Turret", meta = (ClampMin = "0.0"))
	float MuzzleForward = 180.f;

	/** A client's local command (SetLocalCommand) counts this long (s) after its last update. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Airship|Turret", meta = (ClampMin = "0.02"))
	float LocalCommandTimeout = 0.25f;

	/** The muzzle flash is cut this long (s) after the last round, whatever its system does. 0 = no cap. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Airship|Turret", meta = (ClampMin = "0.0"))
	float MuzzleFlashMaxSeconds = 1.f;

	/** Bullet damage: SetByCaller SetDamageByCaller, made from the ship's ASC. Null = UAirshipDamageEffect (built in). */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Airship|Turret")
	TSubclassOf<UGameplayEffect> DamageEffectClass;

	/** Spawned by TracerDataChannel for each round (NS_AirshipTurretTracer). Null: the channel's own system (the gun's tracer). */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Airship|Turret")
	TObjectPtr<UNiagaraSystem> TracerSystem;

	/**
	 * The gun's NDC_GunShootHit (MuzzlePos, HitLocation). Write a copied system through it with TracerSystem, never a
	 * channel of its own: a copied system's readers still read the original channel. Null: NDC_GunShootHit by path.
	 */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Airship|Turret")
	TObjectPtr<UNiagaraDataChannelAsset> TracerDataChannel;

	/** Spawned once when the turret is wrecked (NS_FireExplosion). */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Airship|Turret")
	TObjectPtr<UNiagaraSystem> DestroyedExplosionFX;

	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Airship|Turret", meta = (ClampMin = "0.0"))
	float DestroyedExplosionScale = 1.f;


	// -------------------------------------------------------------------------
	// Replicated state
	// -------------------------------------------------------------------------

	UPROPERTY(Replicated, VisibleInstanceOnly, BlueprintReadOnly, Category = "Airship|Turret")
	TObjectPtr<AAirshipPawn> Ship;

	UPROPERTY(Replicated, VisibleInstanceOnly, BlueprintReadOnly, Category = "Airship|Turret")
	int32 TurretIndex = 0;

	UPROPERTY(Replicated, VisibleInstanceOnly, BlueprintReadOnly, Category = "Airship|Turret")
	FAirshipTurretMount Mount;

	UPROPERTY(ReplicatedUsing = OnRep_Destroyed, VisibleInstanceOnly, BlueprintReadOnly, Category = "Airship|Turret")
	bool bDestroyed = false;

	/** Heat x 255 (the HUD's bar on every machine). */
	UPROPERTY(Replicated)
	uint8 HeatQ = 0;

	UPROPERTY(Replicated, VisibleInstanceOnly, BlueprintReadOnly, Category = "Airship|Turret")
	bool bOverheated = false;

	/** The server's aim (hundredths of a degree, mount-relative): other machines turn the meshes toward it. */
	UPROPERTY(Replicated)
	int16 AimYawQ = 0;

	UPROPERTY(Replicated)
	int16 AimPitchQ = 0;

private:

	UFUNCTION()
	void OnRep_Destroyed();

	/** Server -> every machine: this frame's rounds (tracer ends). Unreliable: a lost batch only loses their look. */
	UFUNCTION(NetMulticast, Unreliable)
	void MulticastShots(const TArray<FAirshipTurretShot>& Shots);

	/** Every machine: turns the meshes toward the active command's aim (or the replicated aim) at the slew rates. */
	void UpdateAim(float DeltaSeconds);

	/** Server: shot clock, heat, rounds, the multicast. */
	void UpdateServerFire(float DeltaSeconds);

	/** The controlling client: predicted rounds (tracer and flash only). */
	void UpdatePredictedFire(float DeltaSeconds);

	/**
	 * The shot clock both fire paths share: false -> true of bCanFire starts the phase (turret 0 at once, turret 1 half
	 * an interval later), then a round every FireInterval while it stays true. Returns the rounds due this tick.
	 */
	int32 AdvanceShotClock(bool bCanFire, float DeltaSeconds, float& InOutClock, bool& bInOutFiring) const;

	/** Server: one round (trace, ball sweep, damage, sentinels, tracer). */
	void FireOneShot(FCollisionQueryParams& Params, AActor* DamageInstigator);

	/** Ignores the turret, its ship, every actor attached to the ship (both turrets, the pilot, gunners) and its deck riders. */
	void BuildShotQueryParams(FCollisionQueryParams& Params) const;

	/** Visibility line along a round, looking past this ship's own and its teammates' cannonballs (added to Params, at most a few times). */
	bool TraceShotLine(const FVector& Start, const FVector& End, FCollisionQueryParams& Params, FHitResult& OutHit) const;

	/** A ball this turret doesn't shoot down: its own ship's, or (team match, no friendly fire) a teammate ship's. Every machine. */
	bool IsFriendlyBall(const AAirshipCannonball* Ball) const;

	/** The nearest enemy cannonball (not this ship's or a teammate's, not spent) within BallSweepRadius of the segment, or null. */
	AAirshipCannonball* FindBallOnShot(const FVector& Start, const FVector& End, const FCollisionQueryParams& Params, FVector& OutPoint) const;

	/** Server: one bullet's damage to the GAS actor a round hit (through the ship's ASC). */
	void ApplyBulletDamage(const FHitResult& Hit, AActor* DamageInstigator) const;

	/** Server: a round's segment for the sentinel query on the next tick (outside the Mass phases). */
	void QueueSentinelSegment(const FVector& Start, const FVector& End, AActor* DamageInstigator);

	void FlushSentinelSegments();

	/** Mount-relative yaw / pitch (deg) from the gun pivot to WorldPoint, without the limits. */
	void ComputeAimRaw(const FVector& WorldPoint, float& OutYawDeg, float& OutPitchDeg) const;

	/** True on a client whose local command is newer than LocalCommandTimeout. */
	bool HasFreshLocalCommand() const;

	/** True on the server while the ship keeps the command up to date (a stale one neither aims nor fires). */
	bool IsServerCommandFresh() const;

	/** Writes one tracer into the data channel on this machine (nothing on a dedicated server). */
	void DrawTracer(const FVector& Start, const FVector& End);

	void PlayMuzzleFlash();

	void StopMuzzleFlash();

	void PlayDestroyedFX(bool bExplosion);

	/** Applies PivotHeight / MuzzleForward to the components (the Blueprint's values win over the constructor's). */
	void ApplyGeometry();

	UNiagaraDataChannelAsset* GetTracerChannel();

	FAirshipTurretCommand ServerCommand;
	double ServerCommandTime = -1.0;

	FAirshipTurretCommand LocalCommand;
	double LocalCommandTime = -1.0;

	/** Server: the gauge (HeatQ is its replicated copy). */
	float Heat = 0.f;
	double LastShotTime = -1.0;

	float ShotClock = 0.f;
	bool bServerFiring = false;

	float LocalShotClock = 0.f;
	bool bLocalFiring = false;

	/** The meshes' aim on this machine (deg). */
	float CurrentYawDeg = 0.f;
	float CurrentPitchDeg = 0.f;
	float AppliedYawDeg = TNumericLimits<float>::Max();
	float AppliedPitchDeg = TNumericLimits<float>::Max();

	int32 ShotCount = 0;

	/** Server: the rounds of this tick, sent in one multicast. */
	TArray<FAirshipTurretShot> PendingShots;

	/** Server: rounds waiting for the next-tick sentinel query, and who they are credited to. */
	TArray<TPair<FVector, FVector>> PendingSentinelSegments;
	TWeakObjectPtr<AActor> PendingSentinelInstigator;
	bool bSentinelFlushQueued = false;

	FTimerHandle MuzzleFlashTimer;

	double BeginPlayTime = 0.0;

	/** InitTurret ran (server): a turret whose ship is gone removes itself. */
	bool bHasShip = false;

	/** ReadGunBaseDamage, read once (-1 = not yet). */
	mutable float CachedGunBaseDamage = -1.f;

	/** NDC_GunShootHit found by path when TracerDataChannel is unset. */
	UPROPERTY(Transient)
	TObjectPtr<UNiagaraDataChannelAsset> FallbackTracerChannel;

	bool bTracerChannelLookedUp = false;

	FOnDeathDelegateSignature OnDeathDelegate;
};
