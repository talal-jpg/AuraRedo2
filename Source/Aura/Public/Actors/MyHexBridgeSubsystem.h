// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Engine/TimerHandle.h"
#include "Subsystems/WorldSubsystem.h"
#include "UObject/ObjectKey.h"
#include "MyHexBridgeSubsystem.generated.h"

class AMyHexBridge;
class AMyHexPlatform;
class APawn;
class UMyHexBridgeSettings;
class USplineComponent;
struct FCollisionQueryParams;

/**
 * Connects AMyHexPlatforms with AMyHexBridge actors. Server only.
 *
 * Platforms register themselves in BeginPlay. Registrations are batched (BuildDelay, restarted on
 * every registration but capped at MaxBuildDelay, so one PCG segment is normally one batch), then
 * the batch is bridged and every new platform is told its bridges are ready (NotifyBridgesReady),
 * so bridges are always built from the untouched edges. A platform then starts collapsing once the
 * lead player is on it.
 *
 * Also the per-world home of the lead player (GetLeadPawn) and of the path spline that platforms
 * measure "left behind" against.
 *
 * Pairing (FPlanner, in the .cpp): every nearby platform pair gets a few edge-pair options, cheapest
 * first (short, square-on, little bending). Bridges are planned in passes, without traces until a
 * plan passes every geometric rule (end spacing and spread, no crossings, clear of other platforms'
 * pillars):
 * - SPINE / TREE give a spanning network along the path, LOOP / LEAF add short natural loops,
 * - ROUTE / BYPASS / BRANCH remove single bridges whose loss would split the route,
 * - FALLBACK / RESCUE relax the rules for anything still unconnected.
 * Decks bend (one cubic Hermite segment) when the two tile sides are offset.
 *
 * Batches less than BurstQuietTime apart form a burst: the bridges of the burst are re-planned with
 * every batch and identical ones keep their actor, so a segment split into batches ends with the
 * same bridges as one batch. A fixed bridge that a new platform clips is replaced.
 */
UCLASS()
class AURA_API UMyHexBridgeSubsystem : public UWorldSubsystem
{
	GENERATED_BODY()

public:

	virtual void Deinitialize() override;

	/** Server only. Bridges the platform after BuildDelay, then calls its NotifyBridgesReady(). */
	void RegisterPlatform(AMyHexPlatform* Platform);

	void UnregisterPlatform(AMyHexPlatform* Platform);

	/**
	 * The player whose landing starts platforms collapsing and whose progress decides what is left
	 * behind. Server only (nullptr on clients). Cached per frame; the rule is SelectLeadPawn().
	 */
	UFUNCTION(BlueprintPure, Category = "Hex Platforms")
	APawn* GetLeadPawn() const;

	/** Lead's distance along the registered path spline (cached per frame). False if there is no lead or no path. */
	bool GetLeadPathDistance(float& OutDistance) const;

	/** The path spline platforms are measured along. One per world; the last one registered wins. */
	void RegisterPathSpline(USplineComponent* Spline);
	void UnregisterPathSpline(USplineComponent* Spline);
	const USplineComponent* GetPathSpline() const { return PathSpline.Get(); }

	/** Server. False once MaxPlatformCullsPerFrame platforms have been culled this frame. */
	bool TryConsumeCullBudget();

	/**
	 * Platform HexRadius / 100 (the largest registered so far, 1 before any). The planner's horizontal
	 * lengths (Hex Bridges settings and planner constants, tuned for HexRadius 100) are multiplied by it.
	 */
	float GetLengthScale() const { return LengthScale > 0.f ? LengthScale : 1.f; }

protected:

	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;

private:

	/** Per-batch planner (bursts, revalidation, pairs, passes, actors). Defined in the .cpp. */
	struct FPlanner;

	using FPlatformKey = TObjectKey<AMyHexPlatform>;

	/** Role of a platform, from its size and its distance to the path. */
	enum class EPlatformKind : uint8
	{
		Centre,		// GridSize >= 6 near the path
		Side,		// GridSize >= 6 away from the path
		Ring		// GridSize <= 5
	};

	/** The pass that planned a bridge (logging and debug colours). */
	enum class EBridgePass : uint8
	{
		Spine,
		Tree,
		Loop,
		Leaf,
		Route,
		Bypass,
		Branch,
		Fallback,
		Rescue,
		Num
	};

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
		FIntVector Missing;
		FVector Mid = FVector::ZeroVector;
		FVector Normal = FVector::ForwardVector;
		FVector Up = FVector::UpVector;

		/** Normal flattened to the ground plane (unit). */
		FVector2D Normal2D = FVector2D(1.0, 0.0);

		/** Index in the platform's EdgeTiles. With the platform's Serial it is the edge key. */
		int32 Order = INDEX_NONE;
	};

	/** One pillar of a platform, in world space. */
	struct FTileInfo
	{
		FIntVector Coord;
		FVector2D Center = FVector2D::ZeroVector;
		double Top = 0.0;
		double Bottom = 0.0;
	};

	/** A registered platform. Everything but Platform is filled in when its batch is processed. */
	struct FPlatformEntry
	{
		TWeakObjectPtr<AMyHexPlatform> Platform;
		TArray<FEdgeTile> EdgeTiles;
		TArray<FTileInfo> Tiles;

		FVector Location = FVector::ZeroVector;

		/** Pillar hexagon vertex offsets (world, radius HexRadius) and the platform yaw. */
		FVector2D HexVerts[6];
		double YawCos = 1.0;
		double YawSin = 0.0;

		float HexRadius = 100.f;
		float Footprint = 0.f;
		float SplineDistance = -1.f;

		/** Registration counter: the only ordering key, never pointer order. */
		int32 Serial = INDEX_NONE;

		/** Burst this platform was registered in. */
		int32 Burst = 0;

		int32 GridSize = 0;

		/** 0 = lower chain, 1 = upper chain. */
		uint8 Chain = 0;

		EPlatformKind Kind = EPlatformKind::Ring;

		/** GridSize <= 2: the end rules allow a stepping stone with two close ends. */
		bool bIslet = false;
	};

	/** A bridge that exists (or, during a batch, is planned), kept so later batches know what is linked. */
	struct FBridgeRecord
	{
		TWeakObjectPtr<AMyHexBridge> Bridge;
		FPlatformKey KeyA;
		FPlatformKey KeyB;

		int32 Id = INDEX_NONE;

		/** A is the platform with the higher Serial (the bridge start), B the other one. */
		int32 SerialA = INDEX_NONE;
		int32 SerialB = INDEX_NONE;

		/** Edge index in each platform's EdgeTiles (edge key = Serial + Order). */
		int32 OrderA = INDEX_NONE;
		int32 OrderB = INDEX_NONE;

		FIntVector TileA;
		FIntVector TileB;
		FIntVector MissingA;
		FIntVector MissingB;
		FVector MidA = FVector::ZeroVector;
		FVector MidB = FVector::ZeroVector;

		/** Deck direction leaving each platform (2D unit). */
		FVector2D DirA = FVector2D::ZeroVector;
		FVector2D DirB = FVector2D::ZeroVector;

		/** Spline tangents from A to B (UE convention). Zero for a straight deck. */
		FVector TangentA = FVector::ZeroVector;
		FVector TangentB = FVector::ZeroVector;

		/** Coarse deck polyline, A to B: 2 points when straight. */
		TArray<FVector, TInlineAllocator<2>> Deck;

		FBox2D Bounds = FBox2D(ForceInit);

		/** Deck arc length. */
		double Length = 0.0;

		int32 Burst = 0;

		uint8 Chain = 0;

		EBridgePass Pass = EBridgePass::Tree;

		bool bCurved = false;

		/** Planned in this batch, no actor yet. */
		bool bPlanned = false;

		/** Per batch: an end is on a collapsing platform. Keeps its ends, ignored for connectivity. */
		bool bDying = false;

		/** Per batch: index of each platform in the planner. */
		int32 LocalA = INDEX_NONE;
		int32 LocalB = INDEX_NONE;
	};

	void ProcessPendingPlatforms();

	/** Fills the registration fields of a platform (serial, chain, kind, tiles, edges, ...). */
	void InitPlatformEntry(AMyHexPlatform& Platform, FPlatformEntry& Entry);

	/**
	 * Has this platform started collapsing for pairing purposes? Only when its collapse waits for the
	 * lead (the normal case) or tiles have actually fallen, so platforms that collapse on their own
	 * timer are still bridged to their intact edges.
	 */
	static bool IsPlatformCollapsing(const AMyHexPlatform& Platform);

	/** Any tile of this platform may have collapsed (worth checking tiles one by one). */
	static bool MayHaveCollapsedTiles(const AMyHexPlatform& Platform);

	/** The platform's BridgeKeepDistance: a player this close to a bridge keeps it alive. */
	static float GetBridgeKeepDistance(const AMyHexPlatform& Platform);

	/** World-space open side of an edge tile, from the tile's live instance. False once it has collapsed. */
	static bool GetEdgeWorld(const AMyHexPlatform& Platform, const FEdgeTile& EdgeTile, FEdgeWorld& OutEdge);

	/**
	 * Does a line from From's open side reach To's open side, on Target, before hitting anything else?
	 * QueryParams: the planner's, which ignore bridge actors (null = ignore nothing).
	 */
	bool TraceReaches(const FEdgeWorld& From, const FEdgeWorld& To, const AMyHexPlatform& Target, const UMyHexBridgeSettings& Settings, const FCollisionQueryParams* QueryParams = nullptr) const;

	/** Tangents are world-space spline tangents from EdgeA to EdgeB (zero = straight). */
	AMyHexBridge* SpawnBridge(AMyHexPlatform& A, const FEdgeWorld& EdgeA, AMyHexPlatform& B, const FEdgeWorld& EdgeB, const FVector& StartTangent, const FVector& EndTangent, const UMyHexBridgeSettings& Settings);

	FIntPoint GetCell(const FVector& Location, float CellSize) const;

	TMap<FPlatformKey, FPlatformEntry> Platforms;

	TArray<TWeakObjectPtr<AMyHexPlatform>> PendingPlatforms;

	/** Bridges built so far (pruned when a bridge or one of its platforms goes). */
	TArray<FBridgeRecord> Bridges;

	/** Trace results per (edge key, edge key), valid for the current burst. */
	TMap<TPair<uint64, uint64>, bool> TraceCache;

	int32 NextSerial = 0;
	int32 NextRecordId = 0;

	int32 CurrentBurst = 0;
	double BurstStartTime = -1.e9;
	double LastBatchTime = -1.e9;

	/** When the first registration of the pending batch arrived (debounce cap). */
	double FirstPendingTime = 0.0;

	/** Largest footprint and pair reach registered so far, so a small platform still finds a large one. */
	float MaxFootprint = 0.f;
	float MaxReach = 0.f;

	/** See GetLengthScale. 0 until a platform registers. */
	float LengthScale = 0.f;

	/** The untagged-platform chain fallback has been reported. */
	bool bWarnedChainFallback = false;

	/** THE lead rule. For now: the first player on the server. Replace the body to change who leads. */
	APawn* SelectLeadPawn() const;

	mutable TWeakObjectPtr<APawn> CachedLeadPawn;
	mutable uint64 LeadPawnFrame = MAX_uint64;
	mutable float CachedLeadPathDistance = 0.f;
	mutable bool bLeadPathDistanceValid = false;
	mutable uint64 LeadPathFrame = MAX_uint64;

	TWeakObjectPtr<USplineComponent> PathSpline;

	uint64 CullBudgetFrame = MAX_uint64;
	int32 CullsThisFrame = 0;

	FTimerHandle ProcessTimerHandle;
};
