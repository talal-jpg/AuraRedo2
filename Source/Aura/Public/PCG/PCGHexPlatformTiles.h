#pragma once

#include "CoreMinimal.h"
#include "PCGSettings.h"
#include "PCGHexPlatformTiles.generated.h"

/**
 * Scatter points on the tops of the owning AMyHexPlatform's tiles, for rocks and ruins.
 *
 * Reads the tile infos the platform caches after BuildHexGrid (top centre, bounds, edge depth,
 * open sides), so it only works on a PCG component owned by an AMyHexPlatform.
 *
 * Edge tiles get more points, pushed towards their open sides; tiles further in get fewer, spread
 * around the middle. Every point carries the TileIndex attribute. Pack it into the Static Mesh
 * Spawner's custom data (Instance Data Packer "By Attribute", TileIndex first) so the platform
 * can find the props of a tile when it collapses.
 *
 * Output attributes: TileIndex (int32), EdgeDepth (int32, 0 = tile with an open side), IsEdge (bool),
 * PathDistance (int32, rings from the bridge path, 0 = on it, large when there is no path).
 *
 * The Path pin has one point per path tile (from each bridge end to the centre tile): tile top centre,
 * X along the path, scaled like the props, bounds = the tile. Same attributes.
 * Deterministic for a given seed and grid, so every machine scatters the same props.
 */
UCLASS(BlueprintType, ClassGroup = (Procedural))
class AURA_API UPCGHexPlatformTilesSettings : public UPCGSettings
{
	GENERATED_BODY()

public:

#if WITH_EDITOR
	virtual FName GetDefaultNodeName() const override { return FName(TEXT("HexPlatformTiles")); }
	virtual FText GetDefaultNodeTitle() const override { return NSLOCTEXT("PCGHexPlatformTiles", "NodeTitle", "Hex Platform Tile Scatter"); }
	virtual FText GetNodeTooltipText() const override { return NSLOCTEXT("PCGHexPlatformTiles", "NodeTooltip", "Scatter points on the owning hex platform's tile tops, more near the edges. Writes TileIndex, EdgeDepth, IsEdge, PathDistance. Path: one point per bridge path tile."); }
	virtual EPCGSettingsType GetType() const override { return EPCGSettingsType::Spatial; }
#endif

protected:

	virtual TArray<FPCGPinProperties> InputPinProperties() const override;
	virtual TArray<FPCGPinProperties> OutputPinProperties() const override;
	virtual FPCGElementPtr CreateElement() const override;

public:

	/** Attempts per tile with an open side (EdgeDepth 0). Each attempt spawns with the chance below. */
	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Edge", meta = (PCG_Overridable, ClampMin = "0"))
	int32 EdgeAttemptsPerTile = 2;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Edge", meta = (PCG_Overridable, ClampMin = "0.0", ClampMax = "1.0"))
	float EdgeChance = 0.5f;

	/** Edge points sit this far from the tile centre towards an open side, as a fraction of the tile apothem. */
	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Edge", meta = (PCG_Overridable, ClampMin = "0.0", ClampMax = "1.0"))
	FVector2D EdgeInsetRange = FVector2D(0.35f, 0.75f);

	/** Sideways jitter along the open side, as a fraction of the apothem. */
	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Edge", meta = (PCG_Overridable, ClampMin = "0.0", ClampMax = "1.0"))
	float EdgeSideJitter = 0.45f;

	/** Edge points face away from the platform (plus the yaw jitter). Off = fully random yaw. */
	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Edge", meta = (PCG_Overridable))
	bool bFaceOutward = true;

	/** Attempts per inner tile. */
	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Inner", meta = (PCG_Overridable, ClampMin = "0"))
	int32 InnerAttemptsPerTile = 1;

	/** Chance for tiles EdgeFalloffRings or more rings in from the edge. Closer tiles blend towards EdgeChance. */
	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Inner", meta = (PCG_Overridable, ClampMin = "0.0", ClampMax = "1.0"))
	float InnerChance = 0.08f;

	/** Rings over which the chance goes from EdgeChance to InnerChance. */
	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Inner", meta = (PCG_Overridable, ClampMin = "1"))
	int32 EdgeFalloffRings = 2;

	/** Inner points land within this fraction of the apothem from the tile centre. */
	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Inner", meta = (PCG_Overridable, ClampMin = "0.0", ClampMax = "1.0"))
	float InnerSpread = 0.55f;

	/** Random yaw added to every point (degrees, +/-). */
	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Transform", meta = (PCG_Overridable, ClampMin = "0.0", ClampMax = "180.0"))
	float YawJitter = 180.f;

	/** Uniform scale range. Multiplied by the platform's HexRadius / 100 so props follow the tile size. */
	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Transform", meta = (PCG_Overridable))
	FVector2D ScaleRange = FVector2D(0.7f, 1.3f);

	/** Max random tilt (degrees) so rocks don't all sit perfectly level. */
	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Transform", meta = (PCG_Overridable, ClampMin = "0.0", ClampMax = "45.0"))
	float TiltJitter = 6.f;

	/** Sink into the tile top (cm, before scale) so props don't float on the hex's bevel. */
	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Transform", meta = (PCG_Overridable))
	float ZOffset = -2.f;

	/** Half size of each point's bounds (cm, before scale). Used by Self Pruning downstream. */
	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Transform", meta = (PCG_Overridable, ClampMin = "1.0"))
	float PointExtent = 30.f;
};


class FPCGHexPlatformTilesElement : public IPCGElement
{
public:

	// Reads the platform actor
	virtual bool CanExecuteOnlyOnMainThread(FPCGContext* Context) const override { return true; }

	// The tiles change every time the platform is built
	virtual bool IsCacheable(const UPCGSettings* InSettings) const override { return false; }

protected:

	virtual bool ExecuteInternal(FPCGContext* Context) const override;
};
