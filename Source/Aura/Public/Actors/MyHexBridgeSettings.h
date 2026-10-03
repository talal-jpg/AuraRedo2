// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Engine/DeveloperSettings.h"
#include "Engine/EngineTypes.h"
#include "MyHexBridgeSettings.generated.h"

class AMyHexBridge;

/**
 * Settings used by UMyHexBridgeSubsystem when it connects AMyHexPlatforms.
 *
 * A subsystem has no per-level properties, so these live in Project Settings > Game > Hex Bridges
 * and are saved to DefaultGame.ini.
 */
UCLASS(Config = Game, DefaultConfig, meta = (DisplayName = "Hex Bridges"))
class AURA_API UMyHexBridgeSettings : public UDeveloperSettings
{
	GENERATED_BODY()

public:

	/** Actor spawned for every bridge. Use a Blueprint child of AMyHexBridge with its PCG graph set. */
	UPROPERTY(Config, EditAnywhere, Category = "Bridges")
	TSoftClassPtr<AMyHexBridge> BridgeClass;

	/**
	 * Seconds to wait after the first platform of a batch registers before building its bridges.
	 * Gives every platform spawned in the same frame time to register and its collision time to exist.
	 * The platforms start collapsing straight after their bridges are built.
	 */
	UPROPERTY(Config, EditAnywhere, Category = "Bridges", meta = (ClampMin = "0.01"))
	float BuildDelay = 0.1f;

	/**
	 * Two platforms are considered when the distance between their origins is at most
	 * NeighborRadiusMultiplier * GridSize * HexRadius (the larger of the two platforms' values).
	 * A grid reaches up to ~1.7 * GridSize * HexRadius from its origin.
	 */
	UPROPERTY(Config, EditAnywhere, Category = "Bridges", meta = (ClampMin = "0.0"))
	float NeighborRadiusMultiplier = 3.f;

	/** Bridges longer than this (cm) are not built. 0 = unlimited. */
	UPROPERTY(Config, EditAnywhere, Category = "Bridges", meta = (ClampMin = "0.0"))
	float MaxBridgeLength = 0.f;

	/**
	 * Steepest bridge allowed, in degrees. For a straight two-point spline this is the same as
	 * checking the unit tangent's Z against sin(MaxSlopeDegrees), but it runs before any trace.
	 */
	UPROPERTY(Config, EditAnywhere, Category = "Bridges", meta = (ClampMin = "0.0", ClampMax = "89.0"))
	float MaxSlopeDegrees = 30.f;

	/**
	 * Per platform pair, only this many edges on each side are compared (the ones closest to the
	 * other platform that face it), so at most N * N edge pairs are checked instead of all of them.
	 */
	UPROPERTY(Config, EditAnywhere, Category = "Bridges", meta = (ClampMin = "1"))
	int32 CandidateEdgesPerPlatform = 4;

	/**
	 * How directly an edge must face the other platform's centre to be a candidate
	 * (dot product of its outward normal and the direction to the other platform). 0.5 = within 60 degrees.
	 */
	UPROPERTY(Config, EditAnywhere, Category = "Bridges", meta = (ClampMin = "-1.0", ClampMax = "1.0"))
	float MinFacingDot = 0.5f;

	/** Trace channel the platforms block. They block everything, so Visibility works. */
	UPROPERTY(Config, EditAnywhere, Category = "Bridges")
	TEnumAsByte<ECollisionChannel> TraceChannel = ECC_Visibility;

	/** Size (cm) of the grid cells used to find nearby platforms without checking every platform. */
	UPROPERTY(Config, EditAnywhere, Category = "Bridges", meta = (ClampMin = "100.0"))
	float SpatialCellSize = 10000.f;

	/** Draw the bridge traces (green = bridge built, red = rejected). */
	UPROPERTY(Config, EditAnywhere, Category = "Debug")
	bool bDrawDebug = false;
};
