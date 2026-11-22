// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Character/MyEnemyChar.h"
#include "BurrowerCharacter.generated.h"

class APawn;
class UBoxComponent;
class UGameplayEffect;

/**
 * The Burrower: a 20 m burrowing machine with a spinning cutter rotor at the front (mesh +X).
 *
 * Gameplay runs on the server: UBurrowerSpawnSubsystem spawns one behind every player and sets its
 * TargetPlayer; it flies after that player (no navmesh: flying movement, smooth turns, pitch clamped),
 * and every RotorCheckInterval the RotorBox collapses the AMyHexPlatform tiles it touches
 * (AMyHexPlatform::ActivateTilesInWorldBox, replicated by the platform).
 *
 * GAS like the other enemies (AMyEnemyChar: UMyAbilitySystemComponent + UMyAttributeSet), so every
 * player ability damages it through UExecCalc_Damage / UMyAttributeSet. The attribute effects are
 * applied here in C++ (BP_Burrower must not call InitializeEnemyAttributes as well).
 *
 * Death: server Die -> MulticastHandleDeath (and bBurrowerDead for late joiners) -> movement stops,
 * rotor off, then the Control Rig ragdolls (UBurrowerAnimInstance::bIsDead), or with
 * bUseMeshRagdollFallback the physics asset simulates as in AMyCharBase. LifeSpan after death.
 *
 * Everything the Control Rig needs (rotor spin, body wave) is cosmetic and worked out on every machine
 * by UBurrowerAnimInstance from the Body Wave / Rotor values below.
 *
 * The capsule covers the head (its centre is the actor location, at mesh (830, 0, 187)); the mesh
 * sits behind it at (-830, 0, -187), facing +X. The capsule collides with nothing, so it flies through
 * the tiles and the level; the mesh's physics asset bodies take the hits (Visibility, projectiles).
 */
UCLASS()
class AURA_API ABurrowerCharacter : public AMyEnemyChar
{
	GENERATED_BODY()

public:

	ABurrowerCharacter();

	virtual void Tick(float DeltaTime) override;

	virtual void OnConstruction(const FTransform& Transform) override;

	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	/** Server. Every fatal hit calls Die (Health stays at 0): only the first one counts. */
	virtual void Die() override;


	// -------------------------------------------------------------------------
	// Target
	// -------------------------------------------------------------------------

	/** Server. The player to follow; null = slow down and wait. UBurrowerSpawnSubsystem keeps it up to date. */
	void SetTargetPlayer(APawn* NewTarget);

	/** Server, before FinishSpawning: the spawner owns the target from now on, so the Burrower never picks one itself. */
	void MarkSpawnedBySubsystem() { bTargetManagedBySpawner = true; }

	UFUNCTION(BlueprintPure, Category = "Burrower")
	APawn* GetTargetPlayer() const { return TargetPlayer; }

	/** True on every machine once the death has run here (AMyCharBase::bIsDead). */
	UFUNCTION(BlueprintPure, Category = "Burrower")
	bool IsBurrowerDead() const { return bIsDead; }

	/**
	 * World velocity (cm/s) the corpse inherits, captured on this machine just before the death stops the movement
	 * (on a client whose replicated velocity is already 0: the last one seen while it moved). Times DeathVelocityScale;
	 * 0 with bInheritVelocityOnDeath off or before death.
	 */
	FVector GetDeathVelocity() const { return DeathVelocity; }

	/**
	 * World angular velocity (degrees per second) at death: the yaw rate about world +Z plus the pitch rate about
	 * the actor's right axis, measured from the actor's rotation. Physics convention: a point at offset R from the
	 * pivot moves at Omega x R (Omega in radians). 0 with bInheritTurnOnDeath off or before death.
	 */
	FVector GetDeathAngularVelocity() const { return DeathAngularVelocity; }

	UBoxComponent* GetRotorBox() const { return RotorBox; }

	/** RotorHalfSize + RotorBoxPadding, unscaled (the box's own extent). */
	FVector GetRotorBoxExtent() const;

	/**
	 * Valid, and not dead when it has the combat interface. bRequireCombatInterface: pawns without it
	 * (menu or spectator pawns) don't count.
	 */
	static bool IsLivingTarget(APawn* Pawn, bool bRequireCombatInterface);

	/**
	 * Unit vector (horizontal) pointing behind the pawn: against its velocity above MinSpeed (cm/s),
	 * otherwise against its facing.
	 */
	static FVector GetBehindDirection(const APawn* Pawn, float MinSpeed);


	// -------------------------------------------------------------------------
	// Rotor (cosmetic spin read by UBurrowerAnimInstance; the tile cutting is the server's RotorBox check)
	// -------------------------------------------------------------------------

	/** Rotor spin (degrees per second) while alive. It spins down after death. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Burrower|Rotor")
	float RotorSpinSpeed = 720.f;

	/** How fast the rotor spins up and down (degrees per second, per second). 0 = at once. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Burrower|Rotor", meta = (ClampMin = "0.0"))
	float RotorSpinAcceleration = 720.f;


	// -------------------------------------------------------------------------
	// Body wave (cosmetic, read by UBurrowerAnimInstance and passed to the Control Rig)
	// -------------------------------------------------------------------------

	/** Peak sideways swing (degrees) at the tail joint at full speed. The rig ramps it down toward the head. Keep <= 14. The path-follow bend adds to it. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Burrower|Body Wave", meta = (ClampMin = "0.0", ClampMax = "30.0"))
	float BodyWaveAmplitudeDeg = 12.f;

	/** Peak up/down swing (degrees) at the tail at full speed (a slight corkscrew). Keep <= 6. The path-follow bend adds to it. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Burrower|Body Wave", meta = (ClampMin = "0.0", ClampMax = "15.0"))
	float BodyWavePitchAmplitudeDeg = 5.f;

	/** Fraction of the amplitudes used when standing still. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Burrower|Body Wave", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float BodyWaveIdleAmplitudeFraction = 0.35f;

	/** Speed (cm/s) at which the amplitudes reach their full value. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Burrower|Body Wave", meta = (ClampMin = "0.0"))
	float BodyWaveFullAmplitudeSpeed = 800.f;

	/** Phase lag (degrees) from one joint to the next, so the wave travels head to tail. 45 = long wave, 90 = about one wave over the body. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Burrower|Body Wave", meta = (ClampMin = "0.0", ClampMax = "180.0"))
	float BodyWavePhasePerJointDeg = 65.f;

	/** Waves per second when standing still. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Burrower|Body Wave", meta = (ClampMin = "0.0"))
	float BodyWaveIdleFrequency = 0.3f;

	/** Extra waves per metre travelled (speed-linked part). About 1 / the body's wavelength in metres. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Burrower|Body Wave", meta = (ClampMin = "0.0"))
	float BodyWaveCyclesPerMeter = 0.045f;

	/** Highest waves per second, whatever the speed. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Burrower|Body Wave", meta = (ClampMin = "0.0"))
	float BodyWaveMaxFrequency = 1.5f;

	/** How quickly the amplitudes follow speed changes (higher = faster). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Burrower|Body Wave", meta = (ClampMin = "0.0"))
	float BodyWaveAmplitudeInterpSpeed = 2.f;


	// -------------------------------------------------------------------------
	// Path follow (cosmetic bend, worked out by UBurrowerAnimInstance and passed to the Control Rig)
	// -------------------------------------------------------------------------

	/**
	 * 0: the body turns rigidly with the head. 1: J1..J4 trace the path the head flew (yaw and pitch), measured
	 * along that path, so the bend doesn't depend on speed. The body wave stays on top.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Burrower|Path Follow", meta = (ClampMin = "0.0", ClampMax = "2.0", UIMax = "1.0"))
	float PathFollowStrength = 1.f;

	/** Largest sideways bend (degrees) of each joint against the one in front of it, before the wave is added. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Burrower|Path Follow", meta = (ClampMin = "0.0", ClampMax = "45.0"))
	float PathFollowMaxYawDeg = 14.f;

	/** Largest up/down bend (degrees) of each joint against the one in front of it, before the wave is added. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Burrower|Path Follow", meta = (ClampMin = "0.0", ClampMax = "45.0"))
	float PathFollowMaxPitchDeg = 10.f;

	/** Distance (cm) between the points of the head's trail. Smaller = finer path, more points (about 22 m of trail / spacing). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Burrower|Path Follow", meta = (ClampMin = "10.0"))
	float PathFollowSampleSpacing = 40.f;

	/** Length (cm) of the last segment, J4_Tail to the tail tip (no bone there). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Burrower|Path Follow", meta = (ClampMin = "0.0"))
	float PathFollowTailLength = 457.f;

	/** How quickly the bend angles follow the path (higher = faster). 0 = at once. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Burrower|Path Follow", meta = (ClampMin = "0.0"))
	float PathFollowInterpSpeed = 12.f;

protected:

	virtual void BeginPlay() override;

	/**
	 * Replaces the base death (AMyCharBase: whole-mesh physics at once): stops the movement and the rotor,
	 * then the Control Rig ragdoll or, with bUseMeshRagdollFallback, the base's physics asset ragdoll.
	 */
	virtual void MulticastHandleDeath_Implementation() override;

	/** Blueprint hook on every machine when the death runs (sounds, FX). */
	UFUNCTION(BlueprintImplementableEvent, Category = "Burrower", meta = (DisplayName = "On Burrower Died"))
	void BP_OnBurrowerDied();


	// -------------------------------------------------------------------------
	// Components
	// -------------------------------------------------------------------------

	/**
	 * The rotor's cutting volume. Attached to the mesh (no bone) at the rotor's centre, mesh (977.9, 0, 180.5):
	 * the server doesn't refresh bones it doesn't render, and the Rotor bone's axes come from Blender. Alive,
	 * the rig keeps the rotor at that spot (J0_Head doesn't wave), so only its spin differs, and the disc is
	 * round. Its extent is RotorHalfSize + RotorBoxPadding (set in OnConstruction); move it in the Blueprint
	 * viewport if the rotor moves. No collision of its own: the server queries the tiles with its transform.
	 */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Burrower|Rotor")
	TObjectPtr<UBoxComponent> RotorBox;


	// -------------------------------------------------------------------------
	// Follow (server)
	// -------------------------------------------------------------------------

	/** The player followed. Set by the server (UBurrowerSpawnSubsystem), replicated for Blueprints and UI. */
	UPROPERTY(Replicated, VisibleInstanceOnly, BlueprintReadOnly, Category = "Burrower|Follow")
	TObjectPtr<APawn> TargetPlayer;

	/** Cruising speed (cm/s) near the target. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Burrower|Follow", meta = (ClampMin = "0.0"))
	float FollowSpeed = 1400.f;

	/** Speed (cm/s) once the target is CatchUpFullDistance or more away. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Burrower|Follow", meta = (ClampMin = "0.0"))
	float CatchUpSpeed = 3200.f;

	/** Beyond this distance (cm) from the goal the speed starts rising toward CatchUpSpeed. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Burrower|Follow", meta = (ClampMin = "0.0"))
	float CatchUpStartDistance = 3000.f;

	/** At this distance (cm) and beyond it flies at CatchUpSpeed. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Burrower|Follow", meta = (ClampMin = "0.0"))
	float CatchUpFullDistance = 8000.f;

	/** Fastest turn (degrees per second), yaw and pitch each. Lower = wider, smoother curves. The body turns about the head, so the tail swings fast. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Burrower|Follow", meta = (ClampMin = "1.0"))
	float TurnRate = 40.f;

	/** Steepest climb or dive (degrees). The whole 20 m body tilts with it. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Burrower|Follow", meta = (ClampMin = "0.0", ClampMax = "80.0"))
	float MaxPitch = 25.f;

	/**
	 * It stops pushing forward when the front of the blades (RotorHalfSize, without the padding) is this close (cm)
	 * to the goal. 0: the padded box reaches past the goal, so a player who stands still loses their tile.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Burrower|Follow", meta = (ClampMin = "0.0"))
	float StopDistance = 0.f;

	/** It starts slowing down when the front of the blades is this far (cm) from the goal (full speed beyond). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Burrower|Follow", meta = (ClampMin = "0.0"))
	float SlowdownDistance = 1500.f;

	/**
	 * Goal height (cm) relative to the target's actor location. Negative = below the player's feet, so
	 * the rotor cuts the tiles they run on. The head (actor location) aims here; the rotor is at its height.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Burrower|Follow")
	float FollowHeightOffset = -150.f;

	/** > 0: the goal is this far (cm) behind the target (against its velocity or facing) instead of on it. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Burrower|Follow", meta = (ClampMin = "0.0"))
	float KeepBehindDistance = 0.f;

	/** Placed in a level (not spawned by UBurrowerSpawnSubsystem): follow the nearest living player. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Burrower|Follow")
	bool bAutoTargetNearestPlayer = true;


	// -------------------------------------------------------------------------
	// Rotor box (server)
	// -------------------------------------------------------------------------

	/** Half size of the rotor in mesh space (cm): half its depth along X, its radius in Y and Z. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Burrower|Rotor")
	FVector RotorHalfSize = FVector(27.9, 105.8, 105.8);

	/** Added to RotorHalfSize on every side (cm), so tiles go a little before the blades reach them. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Burrower|Rotor", meta = (ClampMin = "0.0"))
	float RotorBoxPadding = 50.f;

	/** Seconds between the server's tile checks. 0 = every frame. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Burrower|Rotor", meta = (ClampMin = "0.0"))
	float RotorCheckInterval = 0.05f;

	/**
	 * Stretch the box back over the distance moved since the last check, so a fast rotor can't jump over a tile,
	 * and forward over the distance it moves before the next one, so tiles go when the padded box reaches them.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Burrower|Rotor")
	bool bSweepRotorBox = true;

	/** Cut the tiles of top platforms. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Burrower|Rotor")
	bool bCutTopPlatforms = true;

	/** Cut the tiles of bottom platforms (BP_MyHexPlatformBottom). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Burrower|Rotor")
	bool bCutBottomPlatforms = true;


	// -------------------------------------------------------------------------
	// GAS
	// -------------------------------------------------------------------------

	/** Unset: the GameMode's DA_MyEnemyCharacterClassInfo effect for CharacterClass (as the other enemies get). */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Burrower|GAS")
	TSubclassOf<UGameplayEffect> PrimaryAttributesEffect;

	/** Unset: DA_MyEnemyCharacterClassInfo->SecondaryAttributesEffect. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Burrower|GAS")
	TSubclassOf<UGameplayEffect> SecondaryAttributesEffect;

	/** Unset: DA_MyEnemyCharacterClassInfo->VitalAttributesEffect. Applied last (fills Health up to MaxHealth). */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Burrower|GAS")
	TSubclassOf<UGameplayEffect> VitalAttributesEffect;


	// -------------------------------------------------------------------------
	// Death
	// -------------------------------------------------------------------------

	/**
	 * On: the physics asset ragdolls in C++ (AMyCharBase's death). Off: the Control Rig ragdolls (the mesh
	 * stays kinematic). Turn it off once CR_Burrower's ragdoll works; both at once fight over the bones.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Burrower|Death")
	bool bUseMeshRagdollFallback = true;

	/** Hide the health bar when it dies. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Burrower|Death")
	bool bHideHealthBarOnDeath = true;

	/** The ragdoll starts with the velocity it flew at (both ragdolls: every body, on its first simulated frame). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Burrower|Death")
	bool bInheritVelocityOnDeath = true;

	/** Multiplies the inherited velocity (not the turn). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Burrower|Death", meta = (ClampMin = "0.0", UIMax = "2.0"))
	float DeathVelocityScale = 1.f;

	/** The ragdoll also keeps turning as it turned at death (each body gets the turn's share, Omega x offset), so a corpse that dies mid-turn keeps curving. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Burrower|Death")
	bool bInheritTurnOnDeath = true;

	/**
	 * Set on the server at death, for clients that get the actor after the death multicast was sent
	 * (they run the same local death in OnRep / BeginPlay).
	 */
	UPROPERTY(ReplicatedUsing = OnRep_BurrowerDead)
	bool bBurrowerDead = false;

	UFUNCTION()
	void OnRep_BurrowerDead();


	// -------------------------------------------------------------------------
	// Server cost
	// -------------------------------------------------------------------------

	/**
	 * The server refreshes the bones every frame even when it doesn't render the Burrower, so its
	 * physics asset hit bodies follow the body wave there too. Costs the full rig evaluation per frame.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Burrower|Mesh")
	bool bRefreshBonesOnServer = false;

private:

	/** Server: Primary -> Secondary -> Vital at CharacterLevel. */
	void InitializeBurrowerAttributes();

	/** Every machine, once: from the death multicast or, for a late joiner, bBurrowerDead. */
	void HandleBurrowerDeath();

	/** Every machine, every tick while alive: the last moving velocity and the turn rates the corpse would inherit. */
	void SampleDeathMotion();

	/** Every machine, at death, before the movement stops: DeathVelocity and DeathAngularVelocity. */
	void CaptureDeathMotion();

	/** Mesh ragdoll fallback, right after the bodies start simulating: each one gets DeathVelocity plus the turn's share. */
	void ApplyDeathMotionToMeshBodies();

	/** RotorBox extent from RotorHalfSize + RotorBoxPadding. */
	void ApplyRotorBoxExtent();

	/** Server, every tick: steering and speed toward the target. */
	void UpdateFollow(float DeltaTime);

	/** Server: collapses the tiles the rotor box touches. */
	void CheckRotorTiles(float DeltaTime);

	/** Server: nearest living player pawn, or null. */
	APawn* FindNearestLivingPlayer() const;

	bool bTargetManagedBySpawner = false;

	float RotorCheckTimer = 0.f;
	float AutoTargetTimer = 0.f;

	/** Rotor box centre at the last check (for bSweepRotorBox). */
	FVector LastRotorBoxCentre = FVector::ZeroVector;
	bool bHasLastRotorBoxCentre = false;

	/** Captured at death (GetDeathVelocity / GetDeathAngularVelocity). */
	FVector DeathVelocity = FVector::ZeroVector;
	FVector DeathAngularVelocity = FVector::ZeroVector;

	/** Last velocity above a crawl, for a client whose replicated velocity is already 0 when the death arrives. */
	FVector LastMovingVelocity = FVector::ZeroVector;

	/** World time when LastMovingVelocity was last refreshed (it expires after MovingVelocityHoldTime). */
	double LastMovingVelocityTime = 0.0;

	/** Smoothed actor turn rates (degrees per second): yaw increasing, and pitch increasing (nose up). */
	double TurnYawRateDeg = 0.0;
	double TurnPitchRateDeg = 0.0;

	/** Actor rotation and world time at the last turn-rate sample. */
	FRotator LastTurnSampleRotation = FRotator::ZeroRotator;
	double LastTurnSampleTime = 0.0;
	bool bHasTurnSample = false;
};
