// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "UObject/ObjectKey.h"
#include "MyHexMinimapSubsystem.generated.h"

class AMyHexBridge;
class AMyHexPlatform;
class UTexture2D;

/**
 * Bakes every AMyHexPlatform tile and AMyHexBridge into one texture for the minimap material.
 * Runs on every machine that renders (clients and listen servers), from the replicated platforms
 * and bridges, so nothing extra goes over the network.
 *
 * The texture is a window of TextureSize x TextureSize pixels (CmPerPixel each) around the local
 * player. It wraps: world XY / window size is the UV, so when the player moves only the strip that
 * scrolls in is redrawn, and a collapsing tile or a new platform only redraws its own rectangle.
 * The material samples it once per pixel; it never loops over platforms.
 *
 * Channels (linear, 0..255):
 * - R: 255 on a tile.
 * - G: bridge, 255 on its centre line falling to 0 at its edge.
 * - B: height of the tile top / bridge deck in HeightMin..HeightMax as 1..255, 0 = empty.
 * - A: on a tile, 255 at its centre falling to 0 at its hexagon edge (for tile outlines).
 *
 * Platforms and bridges register themselves (BeginPlay / EndPlay); collapsing tiles are picked up
 * from AMyHexPlatform::OnHexTileActivated. Settings: Project Settings > Game > Hex Minimap.
 */
UCLASS()
class AURA_API UMyHexMinimapSubsystem : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:

	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void Deinitialize() override;
	virtual void Tick(float DeltaTime) override;
	virtual TStatId GetStatId() const override;

	/** Call once the platform's grid is built (end of BeginPlay). Draws its live tiles and follows its collapses. */
	void RegisterPlatform(AMyHexPlatform* Platform);
	void UnregisterPlatform(AMyHexPlatform* Platform);

	/** Call whenever the bridge's ends are set (again). */
	void RegisterBridge(AMyHexBridge* Bridge);
	void UnregisterBridge(AMyHexBridge* Bridge);

	/** The baked texture. Null until the first platform registers. Sample it with Wrap addressing (it already is). */
	UFUNCTION(BlueprintPure, Category = "Hex Minimap")
	UTexture2D* GetMinimapTexture() const { return Texture; }

	/** True once the texture exists and covers the area around the local player. */
	UFUNCTION(BlueprintPure, Category = "Hex Minimap")
	bool IsMinimapReady() const { return Texture != nullptr && bWindowValid; }

	/**
	 * (MinX, MinY, Size, 0) in world cm: the area the texture currently holds. UV = WorldXY / Size;
	 * anything outside this square is stale.
	 */
	UFUNCTION(BlueprintPure, Category = "Hex Minimap")
	FLinearColor GetWindowParam() const;

	/** (HeightMin, HeightMax, 0, 0) from the settings, to decode the blue channel. */
	UFUNCTION(BlueprintPure, Category = "Hex Minimap")
	FLinearColor GetHeightParam() const;

	/** Platform HexRadius / 100 of the first platform registered (1 before any). Lengths in the settings are scaled by it. */
	UFUNCTION(BlueprintPure, Category = "Hex Minimap")
	float GetLengthScale() const { return LengthScale > 0.f ? LengthScale : 1.f; }

protected:

	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;

private:

	struct FPlatformEntry
	{
		TWeakObjectPtr<AMyHexPlatform> Platform;

		/** World -> platform local, 2D: rotate by -yaw, then divide by the XY scale. */
		FVector2D Origin = FVector2D::ZeroVector;
		double YawCos = 1.0;
		double YawSin = 0.0;
		FVector2D InvScale = FVector2D::UnitVector;

		/** Tile (Q + GridSize, R + GridSize) -> height byte, 0 = no tile (never had one, or collapsed). */
		TArray<uint8> Cells;
		int32 GridSize = 0;
		int32 Dim = 1;

		double HexRadius = 100.0;

		FVector2D Scale = FVector2D::UnitVector;

		/** World cm one tile spans from its centre (HexRadius times the larger XY scale). */
		double TileReach = 100.0;

		/** World XY box covering every tile. */
		FBox2D Bounds = FBox2D(ForceInit);
	};

	struct FBridgeEntry
	{
		TWeakObjectPtr<AMyHexBridge> Bridge;
		TArray<FVector, TInlineAllocator<33>> Points;
		double HalfWidth = 40.0;

		/** World XY box covering the deck. */
		FBox2D Bounds = FBox2D(ForceInit);
	};

	void OnTileActivated(AMyHexPlatform* Platform, const FIntVector& Coord);

	/** Creates the texture and the window around Focus. Lengths are fixed from here on. */
	void InitTexture(const FVector& Focus);

	/** Scrolls the window when the local player gets RecenterFraction away from its centre. */
	void UpdateWindow();

	bool GetFocus(FVector& OutFocus) const;

	/** World rectangle -> global texels (the inclusive-exclusive pixels it touches). */
	FIntRect WorldToTexels(const FVector2D& Min, const FVector2D& Max) const;

	/** Redraw this world XY box at the next flush (nothing before the texture exists). */
	void MarkDirty(const FBox2D& WorldBox);

	/** Redraws the dirty rectangles and uploads them. */
	void Flush();

	/** Clears and redraws one rectangle of global texels (inside the window) in Pixels. */
	void RasterRect(const FIntRect& Rect);

	uint8 HeightByte(double Z) const;

	int32 Wrap(int32 Value) const { return ((Value % Size) + Size) % Size; }

	TMap<TObjectKey<AMyHexPlatform>, FPlatformEntry> Platforms;
	TMap<TObjectKey<AMyHexBridge>, FBridgeEntry> Bridges;

	UPROPERTY(Transient)
	TObjectPtr<UTexture2D> Texture;

	/** CPU copy of the texture, BGRA, indexed by wrapped texel. */
	TArray<FColor> Pixels;

	TArray<FIntRect> DirtyRects;

	int32 Size = 0;
	double CmPerPixel = 40.0;
	float LengthScale = 0.f;

	/** Global texel of the window's min corner; the window is [WindowMin, WindowMin + Size). */
	FIntPoint WindowMin = FIntPoint::ZeroValue;
	bool bWindowValid = false;

	double LastUploadTime = -1.e9;

	/** False on a dedicated server: nothing is drawn there. */
	bool IsActive() const;
};
