// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "MyHexAtmosphereFX.generated.h"

class UNiagaraComponent;
class UNiagaraSystem;

/**
 * One Niagara system (fog, mist, snow, dust) placed by a PCG graph or by code. The actor's scale
 * scales the effect.
 *
 * Local: the tile prop graphs run on every machine, so each machine spawns its own (PCG Spawn Actor,
 * System from a soft object path attribute). Graphs that only run on the server (the path segment
 * graph) and the path-end fog use AMyHexAtmosphereFXNet instead.
 */
UCLASS()
class AURA_API AMyHexAtmosphereFX : public AActor
{
	GENERATED_BODY()

public:

	AMyHexAtmosphereFX();

	/** Server (or local actor). Sets the system and starts it. */
	void SetSystem(const TSoftObjectPtr<UNiagaraSystem>& InSystem);

	/**
	 * Server (or local actor). Glides to this location and yaw at MoveSpeed on every machine.
	 * The first target is applied at once.
	 */
	void SetMoveTarget(const FVector& Location, float Yaw);

	/** Server (or local actor), right after spawning: cm per second for SetMoveTarget. */
	void SetMoveSpeed(float InMoveSpeed) { MoveSpeed = InMoveSpeed; }

	/** Local actor: keep this actor on the local player's camera (location only), plus Offset. */
	void SetFollowLocalCamera(bool bFollow, const FVector& Offset = FVector::ZeroVector);

	/** Before BeginPlay: drive the float user parameter Parameter at Rate per second (0 = leave it), dipped by gusts. */
	void SetSpawnRate(FName Parameter, float Rate, float InGustAmount, float InGustPeriod);

	/**
	 * Destroys the AMyHexAtmosphereFX actors attached to Parent (the ones this machine may destroy).
	 * PCG doesn't destroy the actors it spawned when the spawning actor goes, so the platforms and
	 * path segments call this in EndPlay.
	 */
	static void DestroyAttachedTo(AActor* Parent);

protected:

	virtual void BeginPlay() override;

	virtual void Tick(float DeltaSeconds) override;

	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Atmosphere")
	TObjectPtr<UNiagaraComponent> Niagara;

	/** The effect. Set before BeginPlay (PCG property override "System") or with SetSystem. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, ReplicatedUsing = OnRep_System, Category = "Atmosphere")
	TSoftObjectPtr<UNiagaraSystem> System;

	/** Desired Max Draw Distance (cm) of the Niagara component. 0 = never culled by distance (the system's Effect Type may still cull it). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Atmosphere", meta = (ClampMin = "0.0"))
	float MaxDrawDistance = 0.f;

	/** cm per second for SetMoveTarget. 0 = jump. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Replicated, Category = "Atmosphere", meta = (ClampMin = "0.0"))
	float MoveSpeed = 4000.f;

	// -------------------------------------------------------------------------
	// Wind and size. Set on the PCG Spawn Actor template (or before BeginPlay).
	// PCG attaches the actors it spawns after their BeginPlay, so fitting and starting wait a tick.
	// -------------------------------------------------------------------------

	/** Turn to the path spawner's WindYaw (world) when starting, so every snow and mist effect blows the same way. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Atmosphere|Wind")
	bool bAlignToWind = false;

	/** Added to the wind yaw (for an effect that blows along another axis than X). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Atmosphere|Wind", meta = (EditCondition = "bAlignToWind"))
	float WindYawOffset = 0.f;

	/**
	 * Fit to the AMyHexPlatform this actor is attached to when starting: XY scale so FitBaseRadius
	 * covers the platform's footprint radius plus FitMargin (times FitRadiusScale).
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Atmosphere|Fit to Platform")
	bool bFitToPlatform = false;

	/** Radius (cm) the effect covers at scale 1 (its spawn shape's radius or half width). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Atmosphere|Fit to Platform", meta = (EditCondition = "bFitToPlatform", ClampMin = "1.0"))
	float FitBaseRadius = 4000.f;

	/** Added to the platform's footprint radius (cm). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Atmosphere|Fit to Platform", meta = (EditCondition = "bFitToPlatform"))
	float FitMargin = 1000.f;

	/** Multiplies the fitted radius (after the margin). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Atmosphere|Fit to Platform", meta = (EditCondition = "bFitToPlatform", ClampMin = "0.0"))
	float FitRadiusScale = 1.f;

	/** Limits of the fitted XY scale. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Atmosphere|Fit to Platform", meta = (EditCondition = "bFitToPlatform"))
	FVector2D FitScaleRange = FVector2D(0.05f, 20.f);

	/** Z scale after fitting. 0 = keep the actor's Z scale. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Atmosphere|Fit to Platform", meta = (EditCondition = "bFitToPlatform", ClampMin = "0.0"))
	float FitScaleZ = 0.f;

	/** Move to the footprint centre, FitZOffset above the highest tile top. Off = keep the PCG location. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Atmosphere|Fit to Platform", meta = (EditCondition = "bFitToPlatform"))
	bool bFitCenter = true;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Atmosphere|Fit to Platform", meta = (EditCondition = "bFitToPlatform && bFitCenter"))
	float FitZOffset = 0.f;

	/**
	 * Float user parameter (name without "User.") set to SpawnRateAtScale1 x scale X x Y x Z x DensityScale
	 * before the effect starts, so particles stay as dense at any size. None = leave it.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Atmosphere|Parameters")
	FName SpawnRateParameter;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Atmosphere|Parameters", meta = (ClampMin = "0.0"))
	float SpawnRateAtScale1 = 0.f;

	/** Multiplies the spawn rate (a PCG property override can set it per point). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Atmosphere|Parameters", meta = (ClampMin = "0.0"))
	float DensityScale = 1.f;

	/** Most particles per second. 0 = no limit. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Atmosphere|Parameters", meta = (ClampMin = "0.0"))
	float MaxSpawnRate = 0.f;

	/** Gusts and lulls: the spawn rate dips by up to this fraction, following slow noise. 0 = steady. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Atmosphere|Parameters", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float GustAmount = 0.f;

	/** Rough seconds between gusts. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Atmosphere|Parameters", meta = (ClampMin = "0.5"))
	float GustPeriod = 8.f;

	/** Float user parameters (names without "User.") set before the effect starts. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Atmosphere|Parameters")
	TMap<FName, float> FloatParameters;

	/** Vector user parameters (names without "User.") set before the effect starts. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Atmosphere|Parameters")
	TMap<FName, FVector> VectorParameters;

	/** Stay on the local player's camera (location only): snow that falls around the player wherever they go. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Atmosphere|Follow Camera")
	bool bFollowLocalCamera = false;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Atmosphere|Follow Camera", meta = (EditCondition = "bFollowLocalCamera"))
	FVector FollowOffset = FVector::ZeroVector;

	UFUNCTION()
	void OnRep_System();

	UFUNCTION()
	void OnRep_MoveTarget();

private:

	/** Aligns to the wind, fits to the platform, then starts the system. */
	void StartEffect();

	void FitToPlatform();

	/** Sets the user parameters (call before activating). */
	void ApplyParameters();

	void ApplySystem();

	/** StartEffect has run: the system may start. */
	bool bEffectStarted = false;

	/** Spawn rate ApplyParameters set (before gusts). 0 = no rate driven. */
	float BaseSpawnRate = 0.f;

	/** Random start in the gust noise, so effects don't gust together. */
	float GustPhase = 0.f;

	void UpdateGust();

	UPROPERTY(ReplicatedUsing = OnRep_MoveTarget)
	FVector_NetQuantize MoveTargetLocation = FVector::ZeroVector;

	UPROPERTY(ReplicatedUsing = OnRep_MoveTarget)
	float MoveTargetYaw = 0.f;

	/** Bumped by SetMoveTarget, so a client can tell the first target (jump) from later ones (glide). */
	UPROPERTY(ReplicatedUsing = OnRep_MoveTarget)
	uint8 MoveTargetCount = 0;

	/** MoveTargetCount this machine has applied. */
	uint8 AppliedMoveTargetCount = 0;
};

/** Replicated AMyHexAtmosphereFX: spawned on the server and sent to every client. */
UCLASS()
class AURA_API AMyHexAtmosphereFXNet : public AMyHexAtmosphereFX
{
	GENERATED_BODY()

public:

	AMyHexAtmosphereFXNet();
};
