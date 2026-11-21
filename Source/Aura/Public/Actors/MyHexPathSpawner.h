// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Engine/TimerHandle.h"
#include "GameFramework/Actor.h"
#include "MyHexPathSpawner.generated.h"

class AMyHexAtmosphereFX;
class AMyHexPathSegment;
class AMyHexPathSpawner;
class UNiagaraSystem;
class UPCGGraphInterface;
class USplineComponent;

/** A segment was added to the path (server). Its path distances and assumed bounds are set and its PCG has started. */
DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnHexPathSegmentSpawned, AMyHexPathSpawner*, PathSpawner, AMyHexPathSegment*, Segment);

/** A Niagara effect kept on the local camera, with its own spawn rate and slow gusts. */
USTRUCT(BlueprintType)
struct FMyHexCameraEffect
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Atmosphere")
	TSoftObjectPtr<UNiagaraSystem> System;

	/** Particles per second (the system's User.SpawnRate). 0 = the system's default. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Atmosphere", meta = (ClampMin = "0.0"))
	float SpawnRate = 0.f;

	/** How far gusts and lulls dip the spawn rate (0 = steady, 0.6 = down to 40% in a lull). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Atmosphere", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float GustAmount = 0.f;

	/** Rough seconds between gusts. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Atmosphere", meta = (ClampMin = "0.5"))
	float GustPeriod = 8.f;
};

/**
 * One atmosphere layout (fog cards, mist, snow, clouds, height fog). AMyHexPathSpawner holds a list of
 * them and AtmosphereVariant picks the one in use, so layouts can be swapped without rewiring graphs.
 * Everything here is cosmetic and runs locally on every machine that renders.
 */
USTRUCT(BlueprintType)
struct FMyHexAtmosphereVariant
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Atmosphere")
	FName Name;

	/** Run by every platform on its AtmospherePCG component, with the tile props. None = nothing around the platforms. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Atmosphere")
	TObjectPtr<UPCGGraphInterface> PlatformGraph;

	/** Spawned once per machine with a local player and kept on its camera (falling snow that is the same everywhere). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Atmosphere")
	TArray<TSoftObjectPtr<UNiagaraSystem>> CameraSystems;

	/** Like CameraSystems, with a spawn rate and gusts per effect. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Atmosphere")
	TArray<FMyHexCameraEffect> CameraEffects;

	/** Offset (cm, world) of the camera effects from the camera. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Atmosphere")
	FVector CameraFXOffset = FVector::ZeroVector;

	/** Replace the level's Exponential Height Fog settings at runtime. Nothing is saved to the level. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Atmosphere|Height Fog")
	bool bOverrideHeightFog = false;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Atmosphere|Height Fog", meta = (EditCondition = "bOverrideHeightFog"))
	float FogDensity = 0.02f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Atmosphere|Height Fog", meta = (EditCondition = "bOverrideHeightFog"))
	float FogHeightFalloff = 0.2f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Atmosphere|Height Fog", meta = (EditCondition = "bOverrideHeightFog"))
	FLinearColor FogInscatteringColor = FLinearColor::Black;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Atmosphere|Height Fog", meta = (EditCondition = "bOverrideHeightFog"))
	bool bVolumetricFog = true;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Atmosphere|Height Fog", meta = (EditCondition = "bOverrideHeightFog"))
	float VolumetricFogDistance = 6000.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Atmosphere|Height Fog", meta = (EditCondition = "bOverrideHeightFog"))
	float VolumetricFogExtinctionScale = 1.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Atmosphere|Height Fog", meta = (EditCondition = "bOverrideHeightFog"))
	float VolumetricFogScatteringDistribution = 0.74f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Atmosphere|Height Fog", meta = (EditCondition = "bOverrideHeightFog"))
	FColor VolumetricFogAlbedo = FColor::White;
};

/**
 * Grows a path spline ahead of the players. Server only.
 *
 * Place one in the level; the path starts at the actor and heads along its forward (X) axis.
 * Whenever any player gets within ExtendDistance of the end, a segment of SegmentLength is added.
 * Its heading wanders around the start heading by up to MaxYawDeviation, driven by Perlin noise
 * over the distance travelled, and its height can wander the same way.
 *
 * PathSpline holds the whole path. Each extension also spawns a SegmentClass actor with its own
 * copy of that piece, and that actor's PCG graph samples it to spawn the AMyHexPlatforms.
 * The segment also gets the world box its platforms are assumed to fill (Segment bounds below), then
 * OnSegmentSpawned fires: a wave spawner in External mode starts a sentinel wave at the box's corners.
 */
UCLASS()
class AURA_API AMyHexPathSpawner : public AActor
{
	GENERATED_BODY()

public:

	AMyHexPathSpawner();

	/** Adds one segment to the end of the path. Server only. */
	UFUNCTION(BlueprintCallable, Category = "Hex Path")
	void ExtendPath();

	UFUNCTION(BlueprintPure, Category = "Hex Path")
	USplineComponent* GetPathSpline() const { return PathSpline; }

	UFUNCTION(BlueprintPure, Category = "Hex Path")
	const TArray<AMyHexPathSegment*>& GetSegments() const { return ToRawPtrTArrayUnsafe(Segments); }

	/**
	 * The atmosphere variant in use in WorldContext's world (its path spawner's AtmosphereVariant, or
	 * the console variable Aura.AtmosphereVariant when that is 0 or more). Null = none.
	 */
	static const FMyHexAtmosphereVariant* FindActiveAtmosphere(const UObject* WorldContext);

	/** WindYaw of WorldContext's path spawner (0 without one). */
	static float FindWindYaw(const UObject* WorldContext);

	const FMyHexAtmosphereVariant* GetActiveAtmosphere() const;

	/** HexRadius / 100: how much bigger than the original layout everything horizontal is. */
	UFUNCTION(BlueprintPure, Category = "Hex Path|Scale")
	float GetLayoutScale() const { return HexRadius / 100.f; }

	/**
	 * Server: fires in ExtendPath for every new segment (the InitialSegments too, during BeginPlay), once its assumed
	 * bounds are set. Listeners bound later catch up with GetSegments(). It runs wherever ExtendPath is called from
	 * (BeginPlay, the player check timer), so listeners should only queue work.
	 */
	UPROPERTY(BlueprintAssignable, Category = "Path")
	FOnHexPathSegmentSpawned OnSegmentSpawned;

	UFUNCTION(BlueprintPure, Category = "Sentinel Waves")
	bool ShouldSpawnSentinelWaves() const { return bSpawnSentinelWaves; }

	UFUNCTION(BlueprintPure, Category = "Sentinel Waves")
	int32 GetFirstSegmentWithSentinelWave() const { return FirstSegmentWithSentinelWave; }

protected:

	virtual void BeginPlay() override;

	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

	/** The whole path so far. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Hex Path")
	TObjectPtr<USplineComponent> PathSpline;


	// -------------------------------------------------------------------------
	// Segments
	// -------------------------------------------------------------------------

	/** Spawned for every extension. Use a Blueprint child of AMyHexPathSegment with its PCG graph set. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Path")
	TSubclassOf<AMyHexPathSegment> SegmentClass;

	// -------------------------------------------------------------------------
	// Scale
	// -------------------------------------------------------------------------

	/**
	 * Hex radius (cm) of every platform along this path. The one knob for platform size: the layout was
	 * built for 100, and every horizontal distance scales with HexRadius / 100 (GetLayoutScale):
	 * - here: SegmentLength, ExtendDistance, DestroySegmentsBehindDistance, and the noise frequencies
	 *   (so the path bends the same relative to the platforms),
	 * - the PCG graph: lays platforms out on a copy of the path shrunk by HexRadius / 100, scales the
	 *   result back up and gives HexRadius to the platforms (see AMyHexPathSegment),
	 * - the bridges: UMyHexBridgeSubsystem scales its lengths by the platforms' HexRadius / 100.
	 * Heights (upper chain, height noise, pillar heights) are not scaled.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Path|Scale", meta = (ClampMin = "10.0"))
	float HexRadius = 100.f;

	/** Length of one extension, in cm (for HexRadius 100). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Path", meta = (ClampMin = "100.0"))
	float SegmentLength = 10000.f;

	/** Spline points per segment. More points let the noise bend the path within a segment. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Path", meta = (ClampMin = "1"))
	int32 PointsPerSegment = 4;

	/** Segments built at BeginPlay, before any player has moved. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Path", meta = (ClampMin = "0"))
	int32 InitialSegments = 2;

	/** Extend when any player's pawn is within this distance (cm, horizontal, for HexRadius 100) of the end of the path. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Path", meta = (ClampMin = "0.0"))
	float ExtendDistance = 15000.f;

	/** Seconds between checks of the players' positions. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Path", meta = (ClampMin = "0.02"))
	float CheckInterval = 0.25f;


	// -------------------------------------------------------------------------
	// Noise
	// -------------------------------------------------------------------------

	/** Most the heading can turn away from the start heading, in degrees. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Path|Noise", meta = (ClampMin = "0.0", ClampMax = "180.0"))
	float MaxYawDeviation = 60.f;

	/** How quickly the heading changes: noise cycles per cm travelled (for HexRadius 100). 0.0001 = a slow bend every ~100 m. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Path|Noise", meta = (ClampMin = "0.0"))
	float YawNoiseFrequency = 0.0001f;

	/** Most the path rises or falls from its start height, in cm. 0 keeps it flat. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Path|Noise", meta = (ClampMin = "0.0"))
	float HeightNoiseAmplitude = 0.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Path|Noise", meta = (ClampMin = "0.0"))
	float HeightNoiseFrequency = 0.0001f;

	/** Different seeds give different paths. The same seed always gives the same path. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Path|Noise")
	float NoiseSeed = 17.31f;

	/**
	 * Destroy a segment actor once its end is this far (cm along the path, for HexRadius 100) behind the lead player.
	 * Only the server-side segment goes; its platforms cull themselves (AMyHexPlatform CullBehindDistance).
	 * 0 = keep every segment.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Path", meta = (ClampMin = "0.0"))
	float DestroySegmentsBehindDistance = 30000.f;

	/** Draw the path as it grows. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Path|Debug")
	bool bDrawDebug = false;


	// -------------------------------------------------------------------------
	// Segment bounds
	//
	// When a segment spawns, before its PCG has run, it gets the world box its platforms are assumed to fill
	// (AMyHexPathSegment::GetSegmentBounds): the world path from the segment's start to its end, widened across it,
	// with the box X axis from start to end. The defaults mirror PCG_SplineIHexPlatformsFromSpline (platforms within
	// 9975 layout cm of the path, tile tops -1620..+4620 around it) and must follow it when the graph changes.
	// -------------------------------------------------------------------------

	/** Reach across the path on each side, in cm (for HexRadius 100). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Path|Segment Bounds", meta = (ClampMin = "0.0"))
	float SegmentBoundsHalfWidth = 10000.f;

	/** Reach back past the segment's start, in cm (for HexRadius 100), for platforms that start behind it. 0 = none. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Path|Segment Bounds", meta = (ClampMin = "0.0"))
	float SegmentBoundsBackReach = 0.f;

	/** Below the lowest path point of the segment, in cm (not scaled). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Path|Segment Bounds")
	float SegmentBoundsBelow = 1620.f;

	/** Above the highest path point of the segment, in cm (not scaled). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Path|Segment Bounds")
	float SegmentBoundsAbove = 4620.f;

	/** The path is sampled this often (cm along it, for HexRadius 100), plus its end. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Path|Segment Bounds", meta = (ClampMin = "50.0"))
	float SegmentBoundsSampleSpacing = 500.f;

	/** Draw each new segment's bounds for about 15 s (server; not in shipping builds). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Path|Segment Bounds")
	bool bDrawSegmentBounds = false;


	// -------------------------------------------------------------------------
	// Sentinel waves (read by AMechSentinelWaveSpawner in External mode)
	// -------------------------------------------------------------------------

	/** This lane starts a sentinel wave for each new segment, when the level's wave spawner is in External mode. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Sentinel Waves")
	bool bSpawnSentinelWaves = true;

	/** Segment index that gets wave 1; earlier segments get none. Wave number = SegmentIndex - this + 1. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Sentinel Waves", meta = (ClampMin = "0"))
	int32 FirstSegmentWithSentinelWave = 1;


	// -------------------------------------------------------------------------
	// Path-end fog
	//
	// Fog banks across the end of the path hide the platforms of a new segment while they spawn.
	// After an extension they wait PathEndFogMoveDelay seconds (the new platforms come up behind them),
	// then glide to the new end. Replicated actors (AMyHexAtmosphereFXNet), spawned by the server.
	// -------------------------------------------------------------------------

	/** The fog bank effect. None = no path-end fog. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Path|Fog")
	TSoftObjectPtr<UNiagaraSystem> PathEndFogSystem;

	/** Fog banks side by side across the path end. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Path|Fog", meta = (ClampMin = "0"))
	int32 PathEndFogCount = 3;

	/** Gap (cm, for HexRadius 100) between neighbouring banks, across the path. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Path|Fog", meta = (ClampMin = "0.0"))
	float PathEndFogSpacing = 5000.f;

	/** How far (cm, for HexRadius 100) before the end of the path the banks stand. Negative = past the end. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Path|Fog")
	float PathEndFogBackOff = 0.f;

	/** Height of the banks above the path (cm). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Path|Fog")
	float PathEndFogZOffset = 0.f;

	/** Actor scale of each bank. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Path|Fog")
	FVector PathEndFogScale = FVector::OneVector;

	/** Seconds after an extension before the banks start moving to the new end. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Path|Fog", meta = (ClampMin = "0.0"))
	float PathEndFogMoveDelay = 6.f;

	/** cm per second the banks glide at. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Path|Fog", meta = (ClampMin = "0.0"))
	float PathEndFogMoveSpeed = 6000.f;

	// -------------------------------------------------------------------------
	// Atmosphere
	// -------------------------------------------------------------------------

	/** Atmosphere layouts to choose from. AtmosphereVariant picks one. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Path|Atmosphere")
	TArray<FMyHexAtmosphereVariant> AtmosphereVariants;

	/**
	 * Index into AtmosphereVariants; -1 (or out of range) = none. The console variable
	 * Aura.AtmosphereVariant overrides it when 0 or more (set it before Play to compare layouts).
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Path|Atmosphere", meta = (ClampMin = "-1"))
	int32 AtmosphereVariant = -1;

	/**
	 * World yaw (degrees) the wind blows towards. Snow and mist with AMyHexAtmosphereFX::bAlignToWind
	 * turn to it, so every effect blows the same way.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Path|Atmosphere")
	float WindYaw = 30.f;

private:

	/** Local: spawns the active variant's camera effects and applies its height fog. Not on a dedicated server. */
	void StartAtmosphere();

	UPROPERTY(Transient)
	TArray<TObjectPtr<AMyHexAtmosphereFX>> CameraFXs;

	void CheckPlayers();

	/** Destroys segments that are DestroySegmentsBehindDistance behind the lead along the path. */
	void DestroyPassedSegments();

	/** The assumed bounds (see Segment bounds) of the path between two distances along PathSpline, in world space. */
	void ComputeSegmentBounds(float StartDistance, float EndDistance, FVector& OutCenter, FVector& OutExtent, FRotator& OutRotation) const;

	/** Noise in roughly -1..1, stretched because Perlin noise rarely gets past +-0.6. */
	float SampleNoise(float Value) const;

	/** Server. Spawns the path-end fog banks or sends them to the current end of the path. */
	void UpdatePathEndFog();

	UPROPERTY(Transient)
	TArray<TObjectPtr<AMyHexAtmosphereFX>> PathEndFogs;

	FTimerHandle PathEndFogTimerHandle;

	UPROPERTY(Transient)
	TArray<TObjectPtr<AMyHexPathSegment>> Segments;

	/** Distance along the path so far, the input to the noise. */
	float TravelledDistance = 0.f;

	float StartYaw = 0.f;

	double StartZ = 0.0;

	FTimerHandle CheckTimerHandle;

	/** Keeps PCG seeds unique after old segments are removed from Segments. */
	int32 NextSegmentIndex = 0;
};
