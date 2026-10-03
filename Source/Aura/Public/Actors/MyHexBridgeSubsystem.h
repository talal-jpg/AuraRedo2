// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Engine/TimerHandle.h"
#include "Subsystems/WorldSubsystem.h"
#include "UObject/ObjectKey.h"
#include "MyHexBridgeSubsystem.generated.h"

class AMyHexPlatform;
class UMyHexBridgeSettings;

/**
 * Connects AMyHexPlatforms with AMyHexBridge actors. Server only.
 *
 * Platforms register themselves in BeginPlay. Registrations are batched for
 * UMyHexBridgeSettings::BuildDelay, then each new platform is bridged to the platforms near it and
 * told to start collapsing, so bridges are always built from the untouched, cached EdgeInstances.
 *
 * Avoiding the all-against-all search:
 * - Platforms are kept in a coarse 2D grid, so a new platform is only compared with platforms in
 *   nearby cells.
 * - Every platform pair is checked once and gets at most one bridge.
 * - For a pair, only the few edges on each side that face the other platform and are closest to
 *   it are compared, and the slope limit is checked before any line trace.
 */
UCLASS()
class AURA_API UMyHexBridgeSubsystem : public UWorldSubsystem
{
	GENERATED_BODY()

public:

	virtual void Deinitialize() override;

	/** Server only. Bridges the platform after BuildDelay, then calls its StartCollapsing(). */
	void RegisterPlatform(AMyHexPlatform* Platform);

	void UnregisterPlatform(AMyHexPlatform* Platform);

protected:

	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;

private:

	/** An edge tile and one of its missing neighbours, stored by coordinate (indices change on collapse). */
	struct FEdgeTile
	{
		FIntVector Tile;
		FIntVector MissingNeighbour;
	};

	/** One open side of an edge tile, in world space. */
	struct FEdgeWorld
	{
		FIntVector Tile;
		FVector Mid = FVector::ZeroVector;
		FVector Normal = FVector::ForwardVector;
		FVector Up = FVector::UpVector;
		double Score = 0.0;
	};

	struct FPlatformEntry
	{
		TWeakObjectPtr<AMyHexPlatform> Platform;
		FIntPoint Cell = FIntPoint::ZeroValue;
		float SearchRadius = 0.f;
		TArray<FEdgeTile> EdgeTiles;
	};

	using FPlatformKey = TObjectKey<AMyHexPlatform>;

	void ProcessPendingPlatforms();

	/** Builds at most one bridge between the two platforms. */
	void TryBridgePlatforms(const FPlatformEntry& A, const FPlatformEntry& B, const UMyHexBridgeSettings& Settings);

	/** The CandidateEdgesPerPlatform edges of Entry that face OtherCenter and are closest to it. */
	void GatherCandidateEdges(const FPlatformEntry& Entry, const FVector& OtherCenter, const UMyHexBridgeSettings& Settings, TArray<FEdgeWorld>& OutEdges) const;

	/** World-space open side of an edge tile, from the tile's live instance. False once it has collapsed. */
	static bool GetEdgeWorld(const AMyHexPlatform& Platform, const FEdgeTile& EdgeTile, FEdgeWorld& OutEdge);

	/** Does a line from From's open side reach To's open side, on Target, before hitting anything else? */
	bool TraceReaches(const FEdgeWorld& From, const FEdgeWorld& To, const AMyHexPlatform& Target, const UMyHexBridgeSettings& Settings) const;

	void SpawnBridge(const FPlatformEntry& A, const FEdgeWorld& EdgeA, const FPlatformEntry& B, const FEdgeWorld& EdgeB, const UMyHexBridgeSettings& Settings);

	FIntPoint GetCell(const FVector& Location, float CellSize) const;

	static TPair<FPlatformKey, FPlatformKey> MakePairKey(const AMyHexPlatform* A, const AMyHexPlatform* B);

	TMap<FPlatformKey, FPlatformEntry> Platforms;

	TMap<FIntPoint, TArray<FPlatformKey>> CellToPlatforms;

	/** Platform pairs already checked, whether or not they got a bridge. */
	TSet<TPair<FPlatformKey, FPlatformKey>> CheckedPairs;

	TArray<TWeakObjectPtr<AMyHexPlatform>> PendingPlatforms;

	/** Largest SearchRadius registered so far, so a small platform still finds a large one near it. */
	float MaxSearchRadius = 0.f;

	FTimerHandle ProcessTimerHandle;
};
