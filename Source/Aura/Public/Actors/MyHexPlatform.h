#pragma once

#include "CoreMinimal.h"
#include "ScalableFloat.h"
#include "GameFramework/Actor.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/TimerHandle.h"
#include "Actors/MyHexPillarBreakSubsystem.h"
#include "MyHexPlatform.generated.h"


struct FScalableFloat;
class AMyHexBridge;
class AMyHexPlatform;
class APawn;
class USplineComponent;
class UMyHexBridgeSubsystem;
class UPCGComponent;
class UPCGGraphInterface;
class UGeometryCollection;

/** How a collapsing tile's props go (AMyHexPlatform::BreakTileProps). */
enum class EHexPropBreakMode : uint8
{
	/** Instances removed, nothing else (late join, props generated after the tile fell). */
	RemoveOnly,

	/** Near the local player: Geometry Collections (PropBreakables). */
	Near,

	/** Beyond the break-effects range: the baked far break (FarPropMeshes). */
	Far,
};

/** A tile started collapsing on this machine (server and clients). Coord is (Q, R, S). */
DECLARE_MULTICAST_DELEGATE_TwoParams(FOnHexTileActivatedSignature, AMyHexPlatform* /*Platform*/, const FIntVector& /*Coord*/);

USTRUCT()
struct FHexCoord
{
	GENERATED_BODY()

	UPROPERTY()
	int32 Q = 0;

	UPROPERTY()
	int32 R = 0;

	UPROPERTY()
	int32 S = 0;
};

/**
 * One tile's placement data, worked out once after BuildHexGrid (AMyHexPlatform::BuildTileInfos).
 * Everything is in actor space. Read by the PCG tile scatter node.
 */
USTRUCT(BlueprintType)
struct FHexTileInfo
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly, Category = "Hex Tile")
	FIntVector Coord = FIntVector::ZeroValue;

	/** Stable per-platform index (AMyHexPlatform::MakeTileIndex). Exact as a float, so it fits ISM custom data. */
	UPROPERTY(BlueprintReadOnly, Category = "Hex Tile")
	int32 TileIndex = INDEX_NONE;

	/** Centre of the pillar's top face. */
	UPROPERTY(BlueprintReadOnly, Category = "Hex Tile")
	FVector LocalTopCenter = FVector::ZeroVector;

	/** The pillar instance's bounds. */
	UPROPERTY(BlueprintReadOnly, Category = "Hex Tile")
	FBox LocalBounds = FBox(ForceInit);

	/** Centre to the middle of a flat side (the mesh's X half size, scaled). */
	UPROPERTY(BlueprintReadOnly, Category = "Hex Tile")
	float Apothem = 0.f;

	/** Rings in from the platform's outline: 0 = this tile has an open side. */
	UPROPERTY(BlueprintReadOnly, Category = "Hex Tile")
	int32 EdgeDepth = 0;

	/** Bit i set = no tile on side i (AMyHexPlatform::GetHexSideDirection), in actor space. The edge mask gets them turned with the pillar. */
	UPROPERTY(BlueprintReadOnly, Category = "Hex Tile")
	int32 OpenSideBits = 0;

	/** Rings from the bridge path (0 = on it). MAX_int32 while the platform has no path. */
	UPROPERTY(BlueprintReadOnly, Category = "Hex Tile")
	int32 PathDistance = MAX_int32;

	/** Path tiles: actor-space direction along the path, towards the centre tile. */
	UPROPERTY(BlueprintReadOnly, Category = "Hex Tile")
	FVector2D PathDirection = FVector2D::ZeroVector;
};

/** One stone of a paving pattern, in cells: X along the path, Y across it from its left edge. */
USTRUCT(BlueprintType)
struct FHexPavingPatternSlab
{
	GENERATED_BODY()

	/** The stone's first cell. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Hex Paving")
	FIntPoint Cell = FIntPoint::ZeroValue;

	/** Cells it covers. 1x1, 2x1, 1x2 and 2x2 have meshes on the tile scatter node. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Hex Paving", meta = (ClampMin = "1"))
	FIntPoint Size = FIntPoint(1, 1);
};

/** One copy of the paving pattern: stones covering PavingPatternLength x PavingCellsAcross cells. */
USTRUCT(BlueprintType)
struct FHexPavingPattern
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Hex Paving")
	TArray<FHexPavingPatternSlab> Slabs;
};

/** A paving stone laid on a bridge path by AMyHexPlatform::BuildBridgePaths. Actor space. */
USTRUCT(BlueprintType)
struct FHexPavingSlab
{
	GENERATED_BODY()

	/** Centre of the stone, at the top of the tile it lands on. */
	UPROPERTY(BlueprintReadOnly, Category = "Hex Paving")
	FVector Location = FVector::ZeroVector;

	/** Degrees. X runs along the stone's long side. */
	UPROPERTY(BlueprintReadOnly, Category = "Hex Paving")
	float Yaw = 0.f;

	/** Cells, long side first (1x1, 2x1 or 2x2 with the default patterns). */
	UPROPERTY(BlueprintReadOnly, Category = "Hex Paving")
	FIntPoint Size = FIntPoint(1, 1);

	/**
	 * Real size over Size cells, X along the long side. Stones on a bend span their own lane's stretch of
	 * the curve, plaza courses are stretched to fit their side, and a lane ending against another path is trimmed.
	 */
	UPROPERTY(BlueprintReadOnly, Category = "Hex Paving")
	FVector2D Scale = FVector2D(1.0, 1.0);

	/**
	 * Curvature (1/cm) of the stone's stretch of path, for the paving material to bend the stone into its curved
	 * keystone so the joints on a bend stay even. X: the path runs along the stone's X and turns towards its +Y.
	 * Y: the path runs along the stone's Y and turns towards its -X. One of them is 0; both are on straight runs.
	 * On a bend Location sits off the middle of the stone's chord by the bend's sagitta, so once bent the stone's
	 * ends land on its lane's curve.
	 */
	UPROPERTY(BlueprintReadOnly, Category = "Hex Paving")
	FVector2D Bend = FVector2D::ZeroVector;

	/** The tile under the stone's centre. The stone breaks when that tile collapses. */
	UPROPERTY(BlueprintReadOnly, Category = "Hex Paving")
	FIntVector Tile = FIntVector::ZeroValue;

	UPROPERTY(BlueprintReadOnly, Category = "Hex Paving")
	int32 TileIndex = INDEX_NONE;

	/** Index into PavingPatterns of the copy it came from. */
	UPROPERTY(BlueprintReadOnly, Category = "Hex Paving")
	int32 Pattern = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Hex Paving")
	int32 Seed = 0;
};

/**
 * The plaza the bridge paths meet in around the centre tile (AMyHexPlatform::BuildBridgePaths): a regular
 * polygon with one side per path into it (at least PavingPlazaMinSides), counting a path that would have
 * joined another one near it. Actor space.
 */
USTRUCT(BlueprintType)
struct FHexPathPlaza
{
	GENERATED_BODY()

	/** False when no path reaches the centre tile, a bridge starts on it, or there is no room. */
	UPROPERTY(BlueprintReadOnly, Category = "Hex Paving")
	bool bValid = false;

	/** Middle of the plaza on the top of the centre tile, where the lamp stands. */
	UPROPERTY(BlueprintReadOnly, Category = "Hex Paving")
	FVector Centre = FVector::ZeroVector;

	/** Degrees. Side 0 faces out this way; side K at Yaw + 360 * K / NumSides. */
	UPROPERTY(BlueprintReadOnly, Category = "Hex Paving")
	float Yaw = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "Hex Paving")
	int32 NumSides = 0;

	/** cm */
	UPROPERTY(BlueprintReadOnly, Category = "Hex Paving")
	float SideLength = 0.f;

	/** The centre tile. The lamp breaks when it collapses. */
	UPROPERTY(BlueprintReadOnly, Category = "Hex Paving")
	FIntVector Tile = FIntVector::ZeroValue;

	UPROPERTY(BlueprintReadOnly, Category = "Hex Paving")
	int32 TileIndex = INDEX_NONE;
};


UCLASS()
class AURA_API AMyHexPlatform : public AActor
{
	GENERATED_BODY()
	
	friend class AMyHexBridgeBuilder;
	friend class UMyHexBridgeSubsystem;
	friend class UMyHexMinimapSubsystem;

public:

	AMyHexPlatform();

	/** Broadcast on every machine when a tile starts collapsing (from ActivateHexLocal). */
	FOnHexTileActivatedSignature OnHexTileActivated;

	/**
	 * Starts the timer that collapses chains of tiles. Server only; does nothing after the first call.
	 * Bypasses the gate below; normally reached through NotifyBridgesReady / NotifyLeadLanded.
	 */
	void StartCollapsing();

	/** Server. Called by UMyHexBridgeSubsystem once this platform's bridges are built from its untouched edges. */
	void NotifyBridgesReady();

	/**
	 * Server. The lead has moved past this platform: AMyGameState calls it on every platform whose
	 * SplineDistance is behind the lead's platform (AMyGameState::CollapseStartBehindLead), so the
	 * lead's own platform and the others at its distance wait. Latched, so it may arrive before the
	 * bridges are ready; the collapse is timed from this moment either way.
	 */
	void NotifyLeadLanded();

	/** Server. Bridges that end on this platform register so a player over them keeps it alive. */
	void RegisterBridge(AMyHexBridge* Bridge);
	void UnregisterBridge(AMyHexBridge* Bridge);

	/**
	 * Server. Bridges ending here: their end tiles become PathStartTiles (replicated), where the tile
	 * paths to the centre start. A change rebuilds the path and regenerates the tile props.
	 */
	void RegisterPathBridge(AMyHexBridge* Bridge);
	void UnregisterPathBridge(AMyHexBridge* Bridge);

	/** True once the tile has started collapsing, on this machine or on the server. */
	bool IsTileCollapsed(const FIntVector& Coord) const;

	bool IsBottomPlatform() const { return bIsBottomPlatform; }

	/** Server, for tests (Aura.BreakTopPlatform): collapses NumChains chains now, or every tile at once when NumChains <= 0. */
	void DebugBreakTiles(int32 NumChains);

	/**
	 * Server. Collapses now every standing tile whose pillar touches the box, through ActivateHex like the
	 * platform's own chains, so it replicates and the props, bridges and minimap follow. BoxExtent is the box's
	 * half size in world cm (a UBoxComponent's GetScaledBoxExtent); only BoxToWorld's location and rotation are
	 * used. Tiles a running chain has reserved go now too. Does nothing until the bridges are built (they are
	 * planned from the untouched edges). Returns how many tiles it collapsed. Used by the Burrower's rotor.
	 */
	int32 ActivateTilesInWorldBox(const FTransform& BoxToWorld, const FVector& BoxExtent);

	/**
	 * Cheap test: false when the box can't touch any tile (the bounds of the grid as built). ActivateTilesInWorldBox
	 * does it first itself. Any machine.
	 */
	bool CouldWorldBoxTouchTiles(const FTransform& BoxToWorld, const FVector& BoxExtent) const;
	
	TArray<FIntVector> GetOriginalEdgeHexes() const;

	TMap<int32, TArray<FIntVector>> GetEdgeInstances() const;
	int32 GetOpenSideBits(const FIntVector& Coord) const;

	TMap<int32, TArray<FIntVector>> EdgeInstances;

	/** Distance along the whole path spline at the point this platform was sampled from. -1 = not set. */
	UFUNCTION(BlueprintPure, Category = "Hex Platform|Path")
	float GetSplineDistance() const { return SplineDistance; }

	bool HasSplineDistance() const { return SplineDistance >= 0.f; }

	// -------------------------------------------------------------------------
	// Tile infos / tile props
	// -------------------------------------------------------------------------

	/** PCG attribute (and prop ISM custom data) that names the tile a prop stands on. */
	static const FName TileIndexAttributeName;

	/** Live tiles, rebuilt by BuildHexGrid. A tile is removed once it collapses. */
	const TMap<FIntVector, FHexTileInfo>& GetTileInfos() const { return TileInfos; }

	float GetHexRadius() const { return HexRadius; }

	/**
	 * UMyHexTilePropsScheduler: the queued tile prop generation may run now (nearest SplineDistance
	 * first). Rebuilds the bridge path, then regenerates the props.
	 */
	void RunQueuedTileProps();

	/** A tile prop or atmosphere generation of this platform is still running (this machine). */
	bool IsGeneratingTileProps() const;

	/** Paving stones on the bridge paths, laid out on the grid as built (fallen tiles included). */
	const TArray<FHexPavingSlab>& GetPavingSlabs() const { return PavingSlabs; }

	/** The plaza the paths meet in at the centre tile (bValid false if there is none). */
	const FHexPathPlaza& GetPathPlaza() const { return PathPlaza; }

	/** PavingCellSize scaled by HexRadius / 100 (cm). */
	float GetPavingCellSize() const { return PavingCellSize * HexRadius / 100.f; }

	/** (Q, R) packed into 0 .. (2 * GridSize + 1)^2 - 1. */
	int32 MakeTileIndex(const FIntVector& Coord) const;

	/** Unit vector (actor space, XY) from a tile's centre through its side Side (0..5, the open-side bit order). */
	static FVector2D GetHexSideDirection(int32 Side);

	/**
	 * Set by the PCG graph when it spawns the platform (Spawn Actor property override from the
	 * SplineDistance point attribute: the sampler's Distance plus the segment's GetPathStartDistance).
	 * Players are ranked by the SplineDistance of the platform they last landed on (AMyGameState).
	 */
	UPROPERTY(Replicated, EditAnywhere, BlueprintReadWrite, Category = "Hex Platform|Path")
	float SplineDistance = -1.f;

protected:

	virtual void BeginPlay() override;

	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

	virtual void OnConstruction(const FTransform& Transform) override;

	virtual void GetLifetimeReplicatedProps(
		TArray<FLifetimeProperty>& OutLifetimeProps
	) const override;


	// -------------------------------------------------------------------------
	// Components
	// -------------------------------------------------------------------------

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Hex Platform")
	TObjectPtr<UInstancedStaticMeshComponent> HexPillarsISM;

	/**
	 * Scatters rocks and ruins on the tiles (assign the graph in the Blueprint). Generated locally on
	 * every machine after BuildHexGrid in BeginPlay; the scatter is deterministic, so all machines match.
	 */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Hex Platform|Tile Props")
	TObjectPtr<UPCGComponent> TilePropsPCG;

	/**
	 * Second tile prop layer (ice cliffs and frozen rock formations, PCG_HexTileProps2). Generated and
	 * broken exactly like TilePropsPCG; its spawned meshes go in the same PropBreakables map.
	 */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Hex Platform|Tile Props")
	TObjectPtr<UPCGComponent> HexTileProps2;

	/**
	 * Fog cards, mist, snow and clouds around this platform: runs the PlatformGraph of the path
	 * spawner's active atmosphere variant (AMyHexPathSpawner::AtmosphereVariants). Generated locally
	 * with the tile props on every machine that renders; cosmetic only.
	 */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Hex Platform|Atmosphere")
	TObjectPtr<UPCGComponent> AtmospherePCG;

public:

	/**
	 * Radius (cm, horizontal) of the circle around TileFootprintCenter that holds every tile: furthest
	 * tile centre plus one HexRadius. Set before the tile props and atmosphere generate; PCG graphs
	 * read it with Get Actor Property.
	 */
	UPROPERTY(Transient, VisibleInstanceOnly, BlueprintReadOnly, Category = "Hex Platform|Atmosphere")
	float TileFootprintRadius = 0.f;

	/** World centre of the tiles (XY) at the height of the highest tile top (Z). */
	UPROPERTY(Transient, VisibleInstanceOnly, BlueprintReadOnly, Category = "Hex Platform|Atmosphere")
	FVector TileFootprintCenter = FVector::ZeroVector;

	/** Tiles standing when the footprint was measured. */
	UPROPERTY(Transient, VisibleInstanceOnly, BlueprintReadOnly, Category = "Hex Platform|Atmosphere")
	int32 TileFootprintCount = 0;

	/** Measures TileFootprintRadius, TileFootprintCenter and TileFootprintCount from the tile instances. */
	void UpdateTileFootprint();

	/**
	 * Server. Registers the standing tiles with the sentinel obstacle registry (UMechSentinelObstacleSubsystem), so live
	 * sentinels steer round them: a vertical cylinder around the tiles' centroid through the farthest tile, from the
	 * lowest pillar bottom to the highest top (the union of the tile instance boxes). No tile left = unregistered.
	 * Runs in BeginPlay and 0.5 s after tiles start collapsing.
	 */
	void RefreshSentinelObstacle();

protected:


	// -------------------------------------------------------------------------
	// Assets
	//
	// Everything BuildHexGrid reads is Replicated (initial only): the server spawns the platforms
	// with PCG overrides (GridSize, NoiseOffset, VerticalScaling, ...), and clients build the grid
	// themselves in BeginPlay, so they need the server's values, not the class defaults.
	// -------------------------------------------------------------------------

	UPROPERTY(Replicated, EditDefaultsOnly, BlueprintReadOnly, Category = "Hex Platform|Assets")
	TObjectPtr<UStaticMesh> HexPillarStaticMesh;

	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Hex Platform|Assets")
	TObjectPtr<USkeletalMesh> HexPillarSkeletalMesh;

	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Hex Platform|Assets")
	TObjectPtr<UAnimSequence> RbdAnimSeq;

	/**
	 * A platform of the bottom chain (BP_MyHexPlatformBottom, spawned by the path graph for the lower
	 * chain): its tiles are HexPillarBottomStaticMesh with one uniform Z scale instead of HexPillarStaticMesh,
	 * and they break into BottomPillarGeometryCollection (else fall with HexPillarBottomSkeletalMesh /
	 * BottomRbdAnimSeq). Top platforms keep the HexPillar assets and the per-tile heights. A class default,
	 * so every machine builds the same tiles.
	 */
	UPROPERTY(Replicated, EditDefaultsOnly, BlueprintReadOnly, Category = "Hex Platform|Assets")
	bool bIsBottomPlatform = false;

	/** The tile mesh of bottom platforms (pivot at the top, like HexPillar). None = they use HexPillarStaticMesh. */
	UPROPERTY(Replicated, EditDefaultsOnly, BlueprintReadOnly, Category = "Hex Platform|Assets")
	TObjectPtr<UStaticMesh> HexPillarBottomStaticMesh;

	/**
	 * Bottom platforms: every tile's Z scale, as a multiple of the XY scale (HexRadius / 100).
	 * The same on every tile (no per-tile heights). 1 = the mesh's own proportions.
	 */
	UPROPERTY(Replicated, EditDefaultsOnly, BlueprintReadOnly, Category = "Hex Platform|Assets", meta = (ClampMin = "0.01"))
	float HexPillarBottomScaleZ = 1.f;

	/**
	 * Bottom platforms, when BottomPillarGeometryCollection is unset: spawned in place of a collapsing tile,
	 * playing BottomRbdAnimSeq. Unset too = the tile just disappears.
	 */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Hex Platform|Assets")
	TObjectPtr<USkeletalMesh> HexPillarBottomSkeletalMesh;

	/** Bottom platforms: played on HexPillarBottomSkeletalMesh. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Hex Platform|Assets")
	TObjectPtr<UAnimSequence> BottomRbdAnimSeq;

	/**
	 * Bottom platforms: a collapsing tile breaks into this Geometry Collection, the fractured
	 * HexPillarBottomStaticMesh (GC_HexRockPillar_H100), the same way the top tiles break into theirs.
	 * Spawned at the instance's exact transform: every bottom tile has the same uniform scale, which the
	 * GC matches while HexPillarBottomScaleZ is 1 (another value stretches it; bake one at that ratio).
	 * Set it on the Blueprint, never from the constructor (see TopPillarHeightVariants). None = the
	 * skeletal fall above. Top platforms ignore it.
	 */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Hex Platform|Assets")
	TObjectPtr<UGeometryCollection> BottomPillarGeometryCollection;

	/**
	 * How BottomPillarGeometryCollection breaks. Its budget fields (MaxActive, MaxSpawnsPerFrame,
	 * MaxQueueTime, MinAgeToRecycle) are not used: bottom breaks queue under TopPillarBreak's, so the top and
	 * bottom pillars share one world-wide budget.
	 */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Hex Platform|Assets")
	FHexPillarBreakSettings BottomPillarBreak;

	/**
	 * Top platforms: a collapsing tile breaks into a Geometry Collection (spawned where the instance was,
	 * at its size, and simulated) instead of HexPillarSkeletalMesh / RbdAnimSeq. Local and cosmetic, near
	 * the local player only (BreakEffectsMaxDistance), under the budget in TopPillarBreak. Bottom platforms
	 * ignore it.
	 *
	 * With TopPillarHeightVariants (and bUseTopPillarHeightVariants) the variant nearest the tile's height
	 * is used instead. This one is only the fallback when there are none, spawned at the instance's exact
	 * scale (none by default). None and no variants = top tiles fall with the skeletal mesh as before.
	 */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Hex Platform|Assets")
	TObjectPtr<UGeometryCollection> TopPillarGeometryCollection;

	/**
	 * Top platforms: the pillar Geometry Collection baked at a few heights (GC_HexPillar_H030 / H070 / H160:
	 * short, medium, tall). The one nearest the tile's Z / XY scale is used, at the tile's transform (see
	 * bExactTopPillarHeight). Fewer variants = less to load, but more leftover non-uniform scale.
	 */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Hex Platform|Assets")
	TArray<FHexPillarGCVariant> TopPillarHeightVariants;

	/**
	 * Scale the variant's Z by what is left over, so the pillar has the tile's exact height and the swap
	 * doesn't pop. That leftover is a non-uniform scale (up to 1.5x with three variants), which a Geometry
	 * Collection applies after each piece's own rotation (an FTransform can't shear): pieces that turn far
	 * stretch a little and drift from their collision. Off = uniform scale (exact pieces, height up to that
	 * much off at the bottom).
	 */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Hex Platform|Assets")
	bool bExactTopPillarHeight = true;

	/** Off = always TopPillarGeometryCollection at the instance's exact scale (for comparison). */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Hex Platform|Assets")
	bool bUseTopPillarHeightVariants = true;

	/**
	 * How TopPillarGeometryCollection breaks, and the world-wide budget for it and the bottom pillars. The
	 * budget is shared by every platform but read from each queued break, so keep it the same on every
	 * platform class.
	 */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Hex Platform|Assets")
	FHexPillarBreakSettings TopPillarBreak;


	// -------------------------------------------------------------------------
	// Optimization
	// -------------------------------------------------------------------------

	/**
	 * Desired Max Draw Distance (cm) of HexPillarsISM, set in BeginPlay: the platform is not drawn when
	 * its bounds are further away. Keep it beyond the path-end fog. 0 = always drawn.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Optimization", meta = (ClampMin = "0.0"))
	float PlatformMaxDrawDistance = 0.f;

	/** Desired Max Draw Distance (cm) put on the tile prop ISMs when they are generated. 0 = always drawn. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Optimization", meta = (ClampMin = "0.0"))
	float PropMaxDrawDistance = 0.f;


	// -------------------------------------------------------------------------
	// Grid
	// -------------------------------------------------------------------------

	UPROPERTY(Replicated, EditAnywhere, BlueprintReadWrite, Category = "Hex Platform|Deletion")
	int32 GridSize = 10;

	UPROPERTY(Replicated, EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Grid")
	float HexRadius = 100.f;

	UPROPERTY(Replicated, EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Grid")
	float VerticalScaling= .5;
	
	
	//NoiseDeletion
	UPROPERTY(Replicated, EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Deletion")
	FVector2D NoiseOffset=FVector2D(0,0);
	
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Deletion")
	float NoiseScale=1;
	
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Deletion")
	float DistRangeMaxToStopDeletion=0.f;
	
	
	UPROPERTY(Replicated, EditAnywhere, Category="Hex Platform|Deletion", meta=(ClampMin="0.1"))
	float NoiseFrequency = 3.f;    // spikes around the edge, roughly 3x this

	UPROPERTY(Replicated, EditAnywhere, Category="Hex Platform|Deletion", meta=(ClampMin="0.0", ClampMax="0.6"))
	float NoiseStrength = 0.3f;    // how far the edge moves in/out, fraction of its radius

	UPROPERTY(Replicated, EditAnywhere, Category="Hex Platform|Deletion", meta=(ClampMin="0.0", ClampMax="1.0"))
	float DetailStrength = 0.3f;   // extra fine jaggedness, 0 = off
	
	
	// UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Deletion")
	// FRuntimeFloatCurve NoiseCurve;
	
	// UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Deletion")
	// FScalableFloat NoiseCurve;
	
	UPROPERTY(Replicated, EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Deletion")
	UCurveFloat* NoiseCurve;
	
	UPROPERTY(Replicated, EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Deletion")
	float DeletionThreshold=-1;

	/**
	 * Wait for UMyHexBridgeSubsystem to build this platform's bridges before collapsing can start,
	 * so the bridges are made from the untouched edges. Off = bridges count as ready in BeginPlay
	 * (the platform still waits for the lead player when bCollapseOnlyWhenLeadLands is on).
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Bridges")
	bool bWaitForBridgesBeforeCollapsing = true;

	bool bCollapseStarted = false;


	// -------------------------------------------------------------------------
	// Collapse timing (server only)
	//
	// Every platform collapses in the same time once it starts, whatever its size: CollapseDuration
	// seconds from its first chain to its last tile. Platforms activated together at the same
	// SplineDistance therefore start together and lose their last tile together, the small ones by
	// dropping single tiles more slowly. The duration follows how far this platform is behind the
	// lead's platform and is re-read on every update: slowest right behind the lead, staying slow up
	// to CollapseEaseStartDistance, then speeding up along an ease-in curve to its fastest at
	// CollapseFarBehindDistance.
	// -------------------------------------------------------------------------

	/** Seconds to collapse a whole platform while it is CollapseEaseStartDistance or less behind the lead's platform. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Collapse", meta = (ClampMin = "0.5"))
	float CollapseDurationNearLead = 60.f;

	/** Seconds to collapse a whole platform once it is CollapseFarBehindDistance or more behind the lead's platform. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Collapse", meta = (ClampMin = "0.5"))
	float CollapseDurationFarBehind = 20.f;

	/**
	 * Path distance behind the lead's platform (cm at HexRadius 100, scaled by HexRadius / 100) up to
	 * which platforms collapse at their slowest (CollapseDurationNearLead). Centre platforms are 5000 apart.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Collapse", meta = (ClampMin = "0.0"))
	float CollapseEaseStartDistance = 5000.f;

	/** Path distance behind the lead's platform (as above) from which platforms collapse at their fastest (CollapseDurationFarBehind). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Collapse", meta = (ClampMin = "1.0"))
	float CollapseFarBehindDistance = 25000.f;

	/**
	 * Shape of the speed-up between the two distances: 1 = linear, 2 = ease in (stays slow longer,
	 * then ramps up hard), higher = later and harder. The speed (1 / duration) follows this curve.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Collapse", meta = (ClampMin = "0.1"))
	float CollapseEaseExponent = 2.f;

	/**
	 * Optional, replaces CollapseEaseExponent. X = 0..1 from CollapseEaseStartDistance to
	 * CollapseFarBehindDistance, Y = 0..1 from the slowest to the fastest speed.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Collapse")
	TObjectPtr<UCurveFloat> CollapseSpeedCurve;

	/**
	 * About how many chains a platform collapses in. Chain length = tiles / this, clamped to
	 * CollapseMinChainLength..CollapseMaxChainLength, so small platforms get short chains.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Collapse", meta = (ClampMin = "1"))
	int32 CollapseChainsPerPlatform = 12;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Collapse", meta = (ClampMin = "1"))
	int32 CollapseMinChainLength = 1;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Collapse", meta = (ClampMin = "1"))
	int32 CollapseMaxChainLength = 15;

	/** Seconds between the tiles of one chain. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Collapse", meta = (ClampMin = "0.0"))
	float CollapseTileStep = 0.1f;

	/** Seconds from activation to the first chain. The same for every platform, so they still start together. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Collapse", meta = (ClampMin = "0.0"))
	float FirstCollapseDelay = 0.5f;

	/** Seconds between checks of a collapsing platform for the next chain. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Collapse", meta = (ClampMin = "0.02"))
	float CollapseUpdateInterval = 0.1f;


	// -------------------------------------------------------------------------
	// Lead player (server only)
	// -------------------------------------------------------------------------

	/**
	 * Collapse starts only once the lead player's platform distance (AMyGameState ranking) reaches
	 * this platform's SplineDistance and its bridges are built. Off = collapse as soon as the bridges
	 * are built.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Lead")
	bool bCollapseOnlyWhenLeadLands = true;

	/** Seconds between checks of the lead player. The first check is randomly offset so platforms don't all check in the same frame. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Lead", meta = (ClampMin = "0.02"))
	float LeadCheckInterval = 0.1f;

	/**
	 * How far below the capsule (cm) an airborne lead can be and still count as on the platform.
	 * Covers jumps and hops that land between checks. 0 = only walking on it counts.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Lead", meta = (ClampMin = "0.0"))
	float LandingTolerance = 150.f;

	/** The server destroys this platform (and its bridges) once it has been left behind. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Lead")
	bool bAutoDestroyWhenLeftBehind = true;

	/**
	 * "Left behind" distance (cm). The platform must be this far from the lead horizontally (to its
	 * footprint edge) and, when it lies on the path, this far behind the lead along the path.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Lead", meta = (ClampMin = "0.0", EditCondition = "bAutoDestroyWhenLeftBehind"))
	float CullBehindDistance = 20000.f;

	/**
	 * A platform whose centre is within this horizontal distance (cm, for HexRadius 100; scaled by HexRadius / 100) of the path spline is judged by
	 * distance along the path. Further away (or with no path in the level) it is culled only after the
	 * lead has reached it and moved CullBehindDistance away.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Lead", meta = (ClampMin = "0.0", EditCondition = "bAutoDestroyWhenLeftBehind"))
	float MaxPathOffset = 10000.f;

	/** Don't cull while any player stands on it, on one of its bridges, or is above its footprint. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Lead", meta = (EditCondition = "bAutoDestroyWhenLeftBehind"))
	bool bKeepWhileAnyPlayerIsOnIt = true;

	/**
	 * A player within this horizontal distance (cm) of a bridge that ends here counts as on that bridge.
	 * Covers jumping and hovering, when the player has no movement base.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Lead", meta = (ClampMin = "0.0", EditCondition = "bAutoDestroyWhenLeftBehind && bKeepWhileAnyPlayerIsOnIt"))
	float BridgeKeepDistance = 300.f;

	// -------------------------------------------------------------------------
	// Tile props (rocks and ruins scattered by TilePropsPCG)
	// -------------------------------------------------------------------------

	/** Run TilePropsPCG and HexTileProps2 in BeginPlay. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Tile Props")
	bool bSpawnTileProps = true;

	/**
	 * Custom data slot that holds the TileIndex in the PCG-spawned prop ISMs. The Static Mesh
	 * Spawner's "By Attribute" packer writes TileIndex here when it is the first packed attribute.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Tile Props", meta = (ClampMin = "0"))
	int32 PropTileIndexCustomDataSlot = 0;

	/**
	 * Prop mesh -> the Geometry Collection spawned in its place when its tile collapses. The prop
	 * ISM is matched by its static mesh. Meshes not in the map just disappear.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Tile Props")
	TMap<TObjectPtr<UStaticMesh>, TObjectPtr<UGeometryCollection>> PropBreakables;

	/**
	 * Lay a path of tiles from every bridge end to the centre tile (FHexTileInfo::PathDistance /
	 * PathDirection, read by the Hex Platform Tile Scatter node: path floor, no props on it).
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Tile Props")
	bool bBuildBridgePaths = true;

	// -------------------------------------------------------------------------
	// Path paving (stones along the bridge paths, the tile scatter node's Paving pin)
	// -------------------------------------------------------------------------

	/**
	 * Pave the bridge paths: a spline through each path's tile centres, cut into pieces by how much
	 * it bends, with copies of PavingPatterns laid along it. Each stone breaks with the tile under it.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Paving", meta = (EditCondition = "bBuildBridgePaths"))
	bool bPaveBridgePaths = true;

	/** Side of one pattern cell (cm, for HexRadius 100; scaled by HexRadius / 100). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Paving", meta = (ClampMin = "5.0"))
	float PavingCellSize = 40.f;

	/** Cells across the path. The path is PavingCellsAcross * PavingCellSize wide. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Paving", meta = (ClampMin = "1", ClampMax = "16"))
	int32 PavingCellsAcross = 4;

	/** Cells along the path covered by one pattern copy. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Paving", meta = (ClampMin = "1", ClampMax = "16"))
	int32 PavingPatternLength = 4;

	/**
	 * The pattern copies laid one after another along the path; each copy picks one (and maybe mirrors
	 * it) from the start tile and its position. Stones outside the copy's cells are skipped.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Paving")
	TArray<FHexPavingPattern> PavingPatterns;

	/**
	 * Most the spline may turn (degrees) inside one piece. Straight runs take whole pattern copies;
	 * bends are cut into 2-cell and 1-cell pieces, and a stone that crosses a cut is split there.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Paving", meta = (ClampMin = "1.0", ClampMax = "90.0"))
	float PavingMaxBend = 14.f;

	/** Smoothing passes over the tile centres before the spline goes through them (takes out the hex zigzag). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Paving", meta = (ClampMin = "0", ClampMax = "50"))
	int32 PavingSmoothing = 10;

	/** How far smoothing may move a point from its tile centre, as a fraction of the tile apothem. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Paving", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float PavingSmoothMaxOffset = 0.75f;

	/** How far past the bridge tile's centre the paving runs, towards its open side (fraction of the apothem). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Paving", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float PavingEdgeReach = 0.92f;

	/**
	 * A stone over tiles whose tops differ by more than this (cm) is halved until each piece sits on
	 * one height, so big stones don't hang over a step.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Paving", meta = (ClampMin = "0.0"))
	float PavingStepSplitHeight = 4.f;

	/**
	 * The paths that reach the centre tile meet in a paved plaza there: a square, or a pentagon / hexagon when
	 * 5 / 6 paths come in, each path turning square onto its own side. A path that would join another one near
	 * the plaza goes on to a side of its own instead, unless some path would then have to loop round the plaza (or
	 * hook in right by its bridge) to reach its side, or the plaza would no longer fit. Its middle is the Lamp point.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Paving", meta = (EditCondition = "bPaveBridgePaths"))
	bool bPavePlaza = true;

	/**
	 * Side length of the plaza (cells) before PavingPlazaSizeRatio grows it, at least the path width plus a cell.
	 * Where a bridge tile would end up under it, the plaza shrinks further, down to the path width plus a cell.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Paving", meta = (ClampMin = "1.0", EditCondition = "bPavePlaza"))
	float PavingPlazaSideCells = 6.f;

	/**
	 * The plaza grows with the platform: its sides stand this fraction of the way from the centre to the nearest
	 * bridge tile, when that is bigger than PavingPlazaSideCells gives. 0 leaves its size to PavingPlazaSideCells.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Paving", meta = (ClampMin = "0.0", ClampMax = "0.6", EditCondition = "bPavePlaza"))
	float PavingPlazaSizeRatio = 0.15f;

	/** Fewest sides the plaza has. More paths into the centre than this give it one side each. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Paving", meta = (ClampMin = "4", ClampMax = "8", EditCondition = "bPavePlaza"))
	int32 PavingPlazaMinSides = 4;

	/** Cells of straight path square onto the plaza side before it. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Paving", meta = (ClampMin = "0.0", EditCondition = "bPavePlaza"))
	float PavingPlazaLead = 1.5f;

	/** Cells (at least) a path gets to turn onto that straight lead: the path is cut back this far before it. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Paving", meta = (ClampMin = "0.0", EditCondition = "bPavePlaza"))
	float PavingPlazaTurn = 3.f;

	/**
	 * Draw each path spline, its cuts, the stones and the plaza outline for 30 s after the paving is laid.
	 * The console variable Aura.PathPavingDebug 1 turns it on for every platform.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Paving")
	bool bDrawPavingDebug = false;

	/**
	 * Seconds after BeginPlay before the first tile prop generation, so the bridges (and with them the
	 * path) are usually known. Bridges arriving later regenerate the props.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Tile Props", meta = (ClampMin = "0.0"))
	float PropsBridgeWait = 3.f;

	/** Seconds after the last bridge change before the path is rebuilt and the props regenerate. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Tile Props", meta = (ClampMin = "0.0"))
	float PropsRegenerateDelay = 0.5f;

	/** Seconds the broken Geometry Collections live. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Tile Props", meta = (ClampMin = "0.1"))
	float BrokenPropLifeSpan = 6.f;

	/** Break every cluster as soon as the Geometry Collection spawns. Off = it falls whole and breaks on impact. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Tile Props")
	bool bCrumbleBrokenProps = true;

	/** Velocity change (cm/s) given to the broken pieces, in world space, plus a little random spread. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Tile Props")
	FVector BrokenPropImpulse = FVector(0.f, 0.f, 150.f);

	/**
	 * Tiles further than this (cm) from the locally controlled player collapse without the broken tile
	 * animation or the prop Geometry Collections; their instances are still removed. Up to
	 * FarBreakMaxDistance they play the baked far breaks instead (FarTopPillar, FarBottomPillar, FarPropMeshes).
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Tile Props", meta = (ClampMin = "0.0"))
	float BreakEffectsMaxDistance = 5000.f;

	// -------------------------------------------------------------------------
	// Far breaks (baked animation for tiles beyond BreakEffectsMaxDistance)
	//
	// Each break adds an instance at the removed instance's world transform to a world-wide ISM per mesh
	// (UMyHexPillarBreakSubsystem), with custom data [0] = world time of the break, [1] = playback speed.
	// Local and cosmetic. An empty Mesh = the tile vanishes as before.
	// -------------------------------------------------------------------------

	/** Top platform tiles. Speed = GetPillarAnimRate(tile Z scale): short pillars play faster, like the old fall animation. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Far Break")
	FHexFarBreakMesh FarTopPillar;

	/** Bottom platform tiles. Speed as for the top tiles. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Far Break")
	FHexFarBreakMesh FarBottomPillar;

	/** Tile prop mesh -> its baked break. Props whose mesh isn't here just vanish. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Far Break")
	TMap<TObjectPtr<UStaticMesh>, FHexFarBreakMesh> FarPropMeshes;

	/** Playback speed of far prop breaks, random in this range. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Far Break")
	FVector2D FarPropSpeedRange = FVector2D(1.0, 1.0);

	/**
	 * Also multiply far prop speed by 1 / sqrt(instance Z scale), clamped to 0.25-4. The baked break is scaled
	 * with the instance, so this keeps a fall baked at scale 1 at true gravity whatever the prop's scale.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Far Break")
	bool bFarPropSpeedFromScale = true;

	/**
	 * No far breaks beyond this horizontal distance (cm) from the local player (the path-end fog hides them).
	 * 0 = no limit. Nor beyond PlatformMaxDrawDistance (pillars) / PropMaxDrawDistance (props), where they are culled.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Far Break", meta = (ClampMin = "0.0"))
	float FarBreakMaxDistance = 20000.f;

	/** World-wide limit of far breaks playing at once (all platforms); over it, the tile or prop just vanishes. 0 = no limit. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Far Break", meta = (ClampMin = "0"))
	int32 FarBreakMaxActive = 512;

	// -------------------------------------------------------------------------
	// Runtime ISM bookkeeping
	// -------------------------------------------------------------------------

	// Hex coordinate -> current ISM instance index
	//
	// IMPORTANT:
	// ISM instance indices can change when RemoveInstance() is called.
	// This map is therefore updated whenever an instance is removed.
	TMap<FIntVector, int32> HexMap;

	// Current ISM instance index -> hex coordinate
	//
	// Used to correctly repair HexMap when RemoveInstance()
	// moves the last instance into the removed instance's slot.
	TMap<int32, FIntVector> InstanceToHex;

	

	// -------------------------------------------------------------------------
	// Replication
	// -------------------------------------------------------------------------

	// Server adds coordinates here when a hex starts activating.
	// Clients receive the coordinates and perform the visual transition locally.
	UPROPERTY(ReplicatedUsing = OnRep_ActivatedTiles)
	TArray<FIntVector> ActivatedTiles;
	
	//
	UPROPERTY()
	TSet<FIntVector> PendingActivationTiles;

	UFUNCTION()
	void OnRep_ActivatedTiles();

	/**
	 * Server-owned bridge end tiles on this platform, sorted by TileIndex: the tile paths start here.
	 * Every machine lays the same path from these and the grid layout. Stops changing with bPathFrozen.
	 */
	UPROPERTY(ReplicatedUsing = OnRep_PathStartTiles)
	TArray<FIntVector> PathStartTiles;

	/** Per PathStartTiles entry: the tile side (GetHexSideDirection) its bridge leaves through, 255 if unknown. */
	UPROPERTY(ReplicatedUsing = OnRep_PathStartTiles)
	TArray<uint8> PathStartSides;

	/** Set by the server when the lead lands or collapsing starts: the path and the tile props stop changing. */
	UPROPERTY(Replicated)
	bool bPathFrozen = false;

	UFUNCTION()
	void OnRep_PathStartTiles();

	/**
	 * Collapses locally every replicated tile this machine hasn't collapsed yet. bPlayEffect = false
	 * only removes the tiles (no falling pillars), for tiles that fell before this client got the platform.
	 */
	void ApplyActivatedTiles(bool bPlayEffect);


	// Tracks which coordinates this particular machine has already
	// visually activated.
	TSet<FIntVector> LocalActivatedTiles;


	// -------------------------------------------------------------------------
	// Animated pillars
	// -------------------------------------------------------------------------

	// These are temporary components owned by this actor.
	// There are no replicated pillar Actors.
	UPROPERTY()
	TArray<TObjectPtr<USkeletalMeshComponent>> ActiveAnimatedPillars;


	// -------------------------------------------------------------------------
	// Grid functions
	// -------------------------------------------------------------------------

	TArray<FHexCoord> GenerateHexGrid();

	FVector2D HexToWorld(
		int32 Q,
		int32 R,
		float InHexRadius
	) const;

	TArray<FIntVector> GetNeighbors(
		const FIntVector& Hex
	);

	TArray<FIntVector> GenerateChain(
		int32 Length,
		const FIntVector& StartHex
	);


	// -------------------------------------------------------------------------
	// Grid construction
	// -------------------------------------------------------------------------

	void BuildHexGrid();


	// -------------------------------------------------------------------------
	// Activation
	// -------------------------------------------------------------------------

	/**
	 * Server. Reserves one chain of up to Length free tiles (every free tile once Length or fewer are
	 * left) and starts it. Returns how many tiles it reserved.
	 */
	int32 ActivateRandomChain(int32 Length);

	/** Tiles still standing that no chain has reserved. */
	int32 CountFreeTiles() const;

	void ActivateChain(
		const TArray<FIntVector>& Chain
	);

	void ActivateHex(
		const FIntVector& Coord
	);

	// Performs the local visual transition:
	//
	// ISM instance
	//      ->
	// remove instance
	//      ->
	// Geometry Collection (UMyHexPillarBreakSubsystem, GetPillarCollection: the top variants or
	// BottomPillarGeometryCollection)
	// none set: skeletal mesh component -> play animation
	//
	// bPlayEffect = false stops after removing the instance (no pieces, skeletal mesh or animation).
	void ActivateHexLocal(
		const FIntVector& Coord,
		bool bPlayEffect = true
	);


	// -------------------------------------------------------------------------
	// ISM management
	// -------------------------------------------------------------------------

	bool RemoveHexInstance(
		const FIntVector& Coord
	);

	int32 AddHexInstance(
		const FIntVector& Coord,
		const FTransform& Transform
	);


	// -------------------------------------------------------------------------
	// Animated mesh
	// -------------------------------------------------------------------------

	USkeletalMeshComponent* SpawnAnimatedPillar(
		const FIntVector& Coord
	);

	/** Collapse animation play rate for a pillar of this Z scale: short pillars fall faster. */
	static float GetPillarAnimRate(float PillarScaleZ);

	/**
	 * The Geometry Collection a top tile with this instance transform breaks into, and the transform to
	 * spawn it at (uniform scale when a height variant is used). Null = none set.
	 */
	UGeometryCollection* GetTopPillarCollection(const FTransform& InstanceTransform, FTransform& OutSpawnTransform) const;

	/**
	 * The Geometry Collection this platform's tile with this instance transform breaks into, and the
	 * transform to spawn it at: BottomPillarGeometryCollection at the exact transform on bottom platforms,
	 * GetTopPillarCollection on top ones. Null = none set.
	 */
	UGeometryCollection* GetPillarCollection(const FTransform& InstanceTransform, FTransform& OutSpawnTransform) const;

	/** TopPillarBreak or BottomPillarBreak, with TopPillarBreak's budget either way (one world-wide budget). */
	FHexPillarBreakSettings GetPillarBreakSettings() const;

	/** The tile mesh: HexPillarBottomStaticMesh on bottom platforms (when set), else HexPillarStaticMesh. */
	UStaticMesh* GetTileMesh() const;

	void RemoveAnimatedPillar(
		USkeletalMeshComponent* SkeletalMeshComponent
	);


	// -------------------------------------------------------------------------
	// Utility
	// -------------------------------------------------------------------------

	bool IsValidHex(
		const FIntVector& Coord
	) const;

private:

	// -------------------------------------------------------------------------
	// Lead player / culling (server only)
	// -------------------------------------------------------------------------

	/** Starts collapsing once the bridges are ready and (if required) the lead has landed. */
	void TryStartCollapsing();

	/**
	 * Looping CollapseTimerHandle callback: advances CollapseProgress by the elapsed time over the
	 * current duration and starts chains until the reserved tiles catch up with it.
	 */
	void UpdateCollapse();

	/** Seconds the whole collapse takes at this platform's current distance behind the lead's platform. */
	float GetCollapseDuration() const;

	/** 0 (slowest) .. 1 (fastest): the eased position between CollapseEaseStartDistance and CollapseFarBehindDistance. */
	float GetCollapseSpeedAlpha() const;

	/** Chain length for a platform of TotalTiles tiles (CollapseChainsPerPlatform, clamped). */
	int32 GetCollapseChainLength(int32 TotalTiles) const;

	/** Looping timer: detects the lead landing on this platform and culls it once it is left behind. */
	void UpdateLeadState();

	/** Is Pawn on this platform? Gap = horizontal distance from the pawn to this platform's footprint edge. */
	bool IsPawnOnPlatform(const APawn* Pawn, double Gap) const;

	/** Has the lead left this platform behind? See CullBehindDistance / MaxPathOffset. */
	bool IsLeftBehind(const UMyHexBridgeSubsystem& Subsystem, double Gap);

	/** Caches this platform's position along the path spline (once it is no longer at the growing end). */
	void ResolvePathDistance(const USplineComponent& Spline);

	/** Any player standing on this platform, on one of its bridges, or above its footprint. */
	bool IsAnyPlayerOnPlatform() const;

	/** Radius (cm) from the actor origin that covers every tile, scaled by the actor scale. */
	float ComputeFootprintRadius() const;

	bool bBridgesReady = false;
	bool bLeadLanded = false;

	/** World time NotifyLeadLanded latched. The collapse is timed from it (plus FirstCollapseDelay). -1 = not yet. */
	double LeadLandedTime = -1.0;

	/** 0..1 through the collapse: the share of the tiles after the first chain that are reserved by now. */
	float CollapseProgress = 0.f;

	/** World time CollapseProgress was last advanced to. */
	double CollapseProgressTime = 0.0;

	/** Standing tiles when collapsing started, and the chain length worked out from them. */
	int32 CollapseTotalTiles = 0;
	int32 CollapseChainLength = 1;

	/** The lead has stood on, or been above, this platform at least once. */
	bool bLeadReached = false;

	bool bPathResolved = false;
	bool bOnPath = false;

	/** Distance along the path spline of this platform's far edge. */
	float PathFrontDistance = 0.f;

	float FootprintRadius = 0.f;

	TWeakObjectPtr<const USplineComponent> ResolvedPathSpline;

	/** Server. Bridges ending on this platform. */
	TArray<TWeakObjectPtr<AMyHexBridge>> Bridges;

	FTimerHandle LeadCheckTimerHandle;
	FTimerHandle CollapseTimerHandle;

	/** Server. One RefreshSentinelObstacle per burst of collapsing tiles. */
	FTimerHandle SentinelObstacleTimer;

	/** Server. Bridges ending on this platform, for PathStartTiles. */
	TArray<TWeakObjectPtr<AMyHexBridge>> PathBridges;

	/** Server. Start tiles (and bridge sides) of bridges destroyed because an end tile fell: the walkway to them stays. */
	TMap<FIntVector, uint8> RetainedPathStarts;

	/** Every tile's top centre as built (before late-join removals), so every machine lays the same path. */
	TMap<FIntVector, FVector> PathLayoutTiles;

	FTimerHandle TilePropsTimerHandle;

	/** GenerateTileProps has run at least once. */
	bool bTilePropsGenerated = false;

	// -------------------------------------------------------------------------
	// Tile infos / tile props
	// -------------------------------------------------------------------------

	/** Fills TileInfos from HexMap (top centre, bounds, edge depth, open sides). End of BuildHexGrid. */
	void BuildTileInfos();

	/** (Re)starts the tile prop timer: path rebuild + GenerateTileProps after Delay. */
	void ScheduleTileProps(float Delay);

	/**
	 * TilePropsTimerHandle: hands the generation to UMyHexTilePropsScheduler, which runs nearer platforms
	 * first and only a few at a time (RunQueuedTileProps). Runs it here when there is no scheduler.
	 */
	void RequestTileProps();

	/** Rebuilds the bridge path, then regenerates the props (comes back later while a component is still generating). */
	void RebuildPathAndTileProps();

	/** Sets PathDistance / PathDirection on every tile from PathStartTiles, laid out on PathLayoutTiles. */
	void BuildBridgePaths();

	/** Custom data 4 of every pillar: rings from the bridge path + direction (see PackHexPathWord), for the path snow. */
	void WritePathCustomData();

	/** Pillar-local direction as an 8 bit angle (angle / 360 deg * 256), for the packed custom data words. */
	static int32 PackHexAngle(const FVector2D& Dir);

	/** Path word: bits 0..3 rings from the path (15 = none), bits 4..11 direction (along the path on it, else towards it). */
	static int32 PackHexPathWord(int32 PathRing, const FVector2D& LocalDir);

	/** Deepest ring from the outline (BuildHexGrid), also in custom primitive data 0 for the snow. */
	int32 MaxEdgeRing = 0;

	/**
	 * Fills PavingSlabs along Routes (each from a bridge tile to Centre or to an earlier route) and around
	 * the plaza at Centre (PathPlaza). Tiles the stones land on join PathSet; PathDirections gets their
	 * direction if they had none.
	 */
	void BuildPathPaving(const TArray<TArray<FIntVector>>& Routes, const FIntVector& Centre, TSet<FIntVector>& PathSet, TMap<FIntVector, FVector2D>& PathDirections);

	/** Paving stones from the last BuildBridgePaths. */
	TArray<FHexPavingSlab> PavingSlabs;

	/** The plaza from the last BuildBridgePaths. */
	FHexPathPlaza PathPlaza;

	/** Server. PathStartTiles from PathBridges (+ RetainedPathStarts); schedules a rebuild if they changed. */
	void UpdatePathStartTiles();

	/** The side of Tile (GetHexSideDirection) nearest a bridge end's world location. */
	uint8 GetPathStartSide(const FIntVector& Tile, const FVector& WorldLocation) const;

	/** Server. The lead landed or collapsing started. */
	void FreezePath();

	/** Props exist and the platform is frozen or losing tiles: no more regeneration. */
	bool AreTilePropsFrozen() const;

	/** Starts TilePropsPCG and HexTileProps2 (local, not replicated). */
	void GenerateTileProps();

	/** Runs AtmospherePCG with the active atmosphere variant's graph (local, not on a dedicated server). */
	void GenerateAtmosphere();

	/** The graph GenerateAtmosphere last gave AtmospherePCG. */
	TWeakObjectPtr<UPCGGraphInterface> AtmosphereGraphSet;

	/** A tile prop component finished: maps its prop ISMs to the tiles they have instances on. */
	void OnTilePropsGenerated(UPCGComponent* InComponent);

	/** OnHexTileActivated: the tile collapsed, so its props break. */
	void HandleTileActivated(AMyHexPlatform* Platform, const FIntVector& Coord);

	/** Removes the tile's prop instances; Near spawns their Geometry Collections in their place, Far their baked far breaks. */
	void BreakTileProps(int32 TileIndex, EHexPropBreakMode Mode);

	/** Far's baked break at WorldTransform through UMyHexPillarBreakSubsystem (nothing if Far.Mesh is None). */
	void PlayFarBreak(const FHexFarBreakMesh& Far, const FTransform& WorldTransform, float Speed);

	void SpawnBrokenProp(UGeometryCollection* Collection, const FTransform& WorldTransform);

	/** Horizontal distance from the local player (pawn, else camera) to WorldLoc. False with no local player. */
	bool GetLocalPlayerDistance2D(FVector WorldLoc, double& OutDistance) const;

	/**
	 * The tile ActivateHexLocal is breaking, read by HandleTileActivated during the broadcast: plays its
	 * effects near the local player / its far break / its distance from the local player.
	 */
	bool bBreakingTileInEffectsRange = false;
	bool bBreakingTileFar = false;
	double BreakingTileDistance = 0.0;

	TMap<FIntVector, FHexTileInfo> TileInfos;

	/** Every tile's LocalBounds together, as built (BuildTileInfos). Doesn't shrink as tiles fall. */
	FBox TilesLocalBounds = FBox(ForceInit);

	/**
	 * TileIndex -> prop ISMs (from both tile prop components) that have instances on that tile. The
	 * instances themselves are found by their TileIndex custom data, since indices shift on removal.
	 */
	TMap<int32, TArray<TWeakObjectPtr<UInstancedStaticMeshComponent>>> TilePropISMs;
};
