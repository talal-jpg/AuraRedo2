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
 *
 * Lengths are for platforms of HexRadius 100. MaxEdgeGap, MaxBridgeLength, LoopMaxLength,
 * IsletMaxLength, RouteMaxLength and MaxSplineDistanceJump are multiplied by HexRadius / 100 when the
 * platforms are bigger (UMyHexBridgeSubsystem::GetLengthScale). Heights, clearances and separations
 * are not: the deck and the player keep their size.
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
	 * Seconds to wait after a platform registers before building the batch's bridges. Restarted by
	 * every registration (up to MaxBuildDelay), so everything PCG spawns for one segment is one batch.
	 * A platform can't start collapsing before its bridges are built, and then only once the lead
	 * player is on it.
	 */
	UPROPERTY(Config, EditAnywhere, Category = "Bridges", meta = (ClampMin = "0.01"))
	float BuildDelay = 0.1f;

	/** BuildDelay keeps restarting, but a batch is built at most this many seconds after its first registration. */
	UPROPERTY(Config, EditAnywhere, Category = "Bridges", meta = (ClampMin = "0.01"))
	float MaxBuildDelay = 0.5f;

	/**
	 * Two platforms are considered when the distance between their origins is at most
	 * NeighborRadiusMultiplier * GridSize * HexRadius (the larger of the two platforms' values),
	 * or within MaxEdgeGap of each other's footprints.
	 */
	UPROPERTY(Config, EditAnywhere, Category = "Bridges", meta = (ClampMin = "0.0"))
	float NeighborRadiusMultiplier = 5.f;

	/** Two platforms are also considered when their origins are at most FootprintA + FootprintB + this (cm) apart. */
	UPROPERTY(Config, EditAnywhere, Category = "Bridges", meta = (ClampMin = "0.0"))
	float MaxEdgeGap = 3000.f;

	/** Bridges longer than this (cm, straight end to end) are not built, except as a last resort (RESCUE). */
	UPROPERTY(Config, EditAnywhere, Category = "Bridges", meta = (ClampMin = "100.0"))
	float MaxBridgeLength = 4500.f;

	/**
	 * Steepest bridge allowed, in degrees. Checked end to end for straight bridges and along the
	 * whole curve for curved ones, before any trace.
	 */
	UPROPERTY(Config, EditAnywhere, Category = "Bridges", meta = (ClampMin = "0.0", ClampMax = "89.0"))
	float MaxSlopeDegrees = 30.f;

	/** Trace channel the platforms block. They block everything, so Visibility works. */
	UPROPERTY(Config, EditAnywhere, Category = "Bridges")
	TEnumAsByte<ECollisionChannel> TraceChannel = ECC_Visibility;

	/** Size (cm) of the grid cells used to find nearby platforms without checking every platform. */
	UPROPERTY(Config, EditAnywhere, Category = "Bridges", meta = (ClampMin = "100.0"))
	float SpatialCellSize = 10000.f;


	// -------------------------------------------------------------------------
	// Shape
	// -------------------------------------------------------------------------

	/**
	 * Decks bend gently (one spline segment, turn radius >= 4 m, bulge <= 1.5 m) to meet two tile
	 * sides that are offset, instead of leaving them at an angle. Off = straight bridges only.
	 */
	UPROPERTY(Config, EditAnywhere, Category = "Shape")
	bool bCurvedBridges = true;

	/** Largest angle (degrees) between the straight line between the two ends and either tile side's normal. */
	UPROPERTY(Config, EditAnywhere, Category = "Shape", meta = (ClampMin = "0.0", ClampMax = "89.0"))
	float MaxEndAngleDegrees = 40.f;

	/** A deck that stays straight (shorter than 5 m, or no valid curve) must be this square-on (degrees) at both ends. */
	UPROPERTY(Config, EditAnywhere, Category = "Shape", meta = (ClampMin = "0.0", ClampMax = "89.0"))
	float MaxStraightEndAngleDegrees = 15.f;

	/** MaxEndAngleDegrees when bCurvedBridges is off. */
	UPROPERTY(Config, EditAnywhere, Category = "Shape", meta = (ClampMin = "0.0", ClampMax = "89.0"))
	float StraightOnlyMaxEndAngleDegrees = 30.f;


	// -------------------------------------------------------------------------
	// Pairing
	// -------------------------------------------------------------------------

	/** Most bridges on an islet (GridSize <= 2). Connectivity passes may add up to 2, never past MaxBridgesLarge. */
	UPROPERTY(Config, EditAnywhere, Category = "Pairing", meta = (ClampMin = "1"))
	int32 MaxBridgesSmall = 3;

	/** Most bridges on a medium platform (GridSize 3 to 5). */
	UPROPERTY(Config, EditAnywhere, Category = "Pairing", meta = (ClampMin = "1"))
	int32 MaxBridgesMedium = 4;

	/** Most bridges on a large platform (GridSize >= 6), and the hard limit for every platform. */
	UPROPERTY(Config, EditAnywhere, Category = "Pairing", meta = (ClampMin = "1"))
	int32 MaxBridgesLarge = 6;

	/**
	 * Smallest distance between two bridge ends on one platform, in HexRadius. An islet may have two
	 * closer ends (1.4 R) when the bridges leave at least 100 degrees apart (a stepping stone).
	 */
	UPROPERTY(Config, EditAnywhere, Category = "Pairing", meta = (ClampMin = "0.0"))
	float MinEndSpacingRadii = 3.f;

	/**
	 * Smallest angle (around the platform's centre) between two bridge ends on one platform.
	 * Waived for ends at least 6 HexRadius apart whose bridges diverge by at least 25 degrees.
	 */
	UPROPERTY(Config, EditAnywhere, Category = "Pairing", meta = (ClampMin = "0.0", ClampMax = "180.0"))
	float MinBridgeSpreadDegrees = 40.f;

	/** Bridges of the same chain never come closer than this (cm) in the top-down view, at any height. */
	UPROPERTY(Config, EditAnywhere, Category = "Pairing", meta = (ClampMin = "0.0"))
	float SameChainSeparation = 250.f;

	/**
	 * Two bridges that pass within this distance (cm) of each other in the top-down view, at heights
	 * closer than MinBridgeVerticalClearance, count as crossing. Crossing bridges are never built.
	 */
	UPROPERTY(Config, EditAnywhere, Category = "Pairing", meta = (ClampMin = "0.0"))
	float BridgeSeparation = 300.f;

	/** A bridge this far (cm) above or below another may pass over it (other chain only). */
	UPROPERTY(Config, EditAnywhere, Category = "Pairing", meta = (ClampMin = "0.0"))
	float MinBridgeVerticalClearance = 500.f;

	/**
	 * A deck keeps at least this distance (cm, top-down, to the exact hexagon) from every pillar of a
	 * third platform while it is at the height of that pillar (top + 5 m down to its bottom - 2.5 m).
	 */
	UPROPERTY(Config, EditAnywhere, Category = "Pairing", meta = (ClampMin = "0.0"))
	float PlatformClearance = 230.f;

	/** Longest loop bridge (cm), added for an alternative route. */
	UPROPERTY(Config, EditAnywhere, Category = "Pairing", meta = (ClampMin = "0.0"))
	float LoopMaxLength = 2200.f;

	/** Longest optional bridge (cm) onto an islet; up to 22 m when the islet becomes a through stepping stone. */
	UPROPERTY(Config, EditAnywhere, Category = "Pairing", meta = (ClampMin = "0.0"))
	float IsletMaxLength = 1800.f;

	/** Longest bridge (cm) added to remove a single bridge the route depends on. */
	UPROPERTY(Config, EditAnywhere, Category = "Pairing", meta = (ClampMin = "0.0"))
	float RouteMaxLength = 2500.f;

	/** > 0: optional bridges never join platforms further apart than this (cm) along the path. 0 = off. */
	UPROPERTY(Config, EditAnywhere, Category = "Pairing", meta = (ClampMin = "0.0"))
	float MaxSplineDistanceJump = 0.f;

	/** Bridges may join the lower and upper chains (HexLower / HexUpper), under the same rules. */
	UPROPERTY(Config, EditAnywhere, Category = "Pairing")
	bool bAllowCrossChain = false;

	/**
	 * Platforms that started collapsing are never paired, and their bridges stop counting for
	 * connectivity (only when their collapse waits for the lead, or tiles have fallen).
	 */
	UPROPERTY(Config, EditAnywhere, Category = "Pairing")
	bool bSkipCollapsingPlatforms = true;

	/**
	 * Fallback for a platform with neither the HexLower nor the HexUpper tag: upper chain when it is
	 * more than this (cm) above the path spline's closest point. A warning is logged once.
	 */
	UPROPERTY(Config, EditAnywhere, Category = "Pairing")
	float ChainSplitHeight = 860.f;


	// -------------------------------------------------------------------------
	// Bursts
	// -------------------------------------------------------------------------

	/**
	 * Bridges spawned in the current burst are re-planned with each new batch of the burst, so a
	 * segment arriving in pieces ends with the same bridges. Identical bridges keep their actor.
	 * Off = each batch is planned on its own.
	 */
	UPROPERTY(Config, EditAnywhere, Category = "Bursts")
	bool bReplanBursts = true;

	/** Seconds without a batch that end a burst (its bridges become fixed). */
	UPROPERTY(Config, EditAnywhere, Category = "Bursts", meta = (ClampMin = "0.0"))
	float BurstQuietTime = 1.f;

	/** A burst longer than this (seconds) is cut, which bounds the re-planning work. */
	UPROPERTY(Config, EditAnywhere, Category = "Bursts", meta = (ClampMin = "0.0"))
	float BurstMaxDuration = 8.f;

	/**
	 * A fixed bridge that a platform of a new batch clips is destroyed (unless a player is on it or
	 * near it) and its two platforms are re-planned.
	 */
	UPROPERTY(Config, EditAnywhere, Category = "Bursts")
	bool bRevalidateBridges = true;

	/** Clip distance (cm, top-down, to the exact hexagon, inside the pillar's height band) for bRevalidateBridges. */
	UPROPERTY(Config, EditAnywhere, Category = "Bursts", meta = (ClampMin = "0.0"))
	float RevalidateClearance = 120.f;


	// -------------------------------------------------------------------------
	// Debug
	// -------------------------------------------------------------------------

	/** Draw the planned decks and the bridge traces (green = reached, red = rejected). */
	UPROPERTY(Config, EditAnywhere, Category = "Debug")
	bool bDrawDebug = false;
};
