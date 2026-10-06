// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Engine/TimerHandle.h"
#include "GameFramework/Actor.h"
#include "MyHexPathSpawner.generated.h"

class AMyHexPathSegment;
class USplineComponent;

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

	/** Length of one extension, in cm. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Path", meta = (ClampMin = "100.0"))
	float SegmentLength = 10000.f;

	/** Spline points per segment. More points let the noise bend the path within a segment. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Path", meta = (ClampMin = "1"))
	int32 PointsPerSegment = 4;

	/** Segments built at BeginPlay, before any player has moved. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Path", meta = (ClampMin = "0"))
	int32 InitialSegments = 2;

	/** Extend when any player's pawn is within this distance (cm, horizontal) of the end of the path. */
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

	/** How quickly the heading changes: noise cycles per cm travelled. 0.0001 = a slow bend every ~100 m. */
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
	 * Destroy a segment actor once its end is this far (cm, along the path) behind the lead player.
	 * Only the server-side segment goes; its platforms cull themselves (AMyHexPlatform CullBehindDistance).
	 * 0 = keep every segment.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Path", meta = (ClampMin = "0.0"))
	float DestroySegmentsBehindDistance = 30000.f;

	/** Draw the path as it grows. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Path|Debug")
	bool bDrawDebug = false;

private:

	void CheckPlayers();

	/** Destroys segments that are DestroySegmentsBehindDistance behind the lead along the path. */
	void DestroyPassedSegments();

	/** Noise in roughly -1..1, stretched because Perlin noise rarely gets past +-0.6. */
	float SampleNoise(float Value) const;

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
