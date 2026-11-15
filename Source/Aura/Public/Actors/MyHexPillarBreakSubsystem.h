// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "UObject/ObjectKey.h"
#include "MyHexPillarBreakSubsystem.generated.h"

class AMyHexPlatform;
class UGeometryCollection;
class UGeometryCollectionComponent;
class UInstancedStaticMeshComponent;
class UMaterialInterface;
class UStaticMesh;

/**
 * A baked break animation for tiles that collapse beyond the break-effects range (AMyHexPlatform::FarTopPillar,
 * FarBottomPillar, FarPropMeshes). Each break adds an instance of Mesh, at the removed instance's world transform,
 * to one world-wide ISM per mesh. Per-instance custom data: [0] = world time of the break (the material Time
 * node's clock), [1] = playback speed. MF_HexFarBreakFrame turns them into the current frame. The material
 * needs "Used with Instanced Static Meshes" saved on it, or cooked builds draw the default material.
 */
USTRUCT(BlueprintType)
struct FHexFarBreakMesh
{
	GENERATED_BODY()

	/** Every frame of the baked break in one static mesh (frame number in vertex colour). None = no animation: the tile just vanishes. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Far Break")
	TObjectPtr<UStaticMesh> Mesh;

	/** Put on every material slot of Mesh. None = the mesh's own materials. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Far Break")
	TObjectPtr<UMaterialInterface> Material;

	/** Seconds the animation lasts at speed 1. The instance is hidden and its slot reused after Length / speed. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Far Break", meta = (ClampMin = "0.05"))
	float Length = 6.f;

	/** Far away, so off by default. The ISM is shared by every break of this mesh: the first one to use it decides. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Far Break")
	bool bCastShadow = false;

	/** World Position Offset writes velocity (motion blur, TSR). Off: a far, time-driven WPO isn't worth the velocity pass. First one decides, as above. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Far Break")
	bool bWPOWritesVelocity = false;
};

/**
 * A top pillar Geometry Collection baked at one height: its source mesh is HexPillar scaled by
 * (1, 1, HeightRatio) about the pivot, so with a uniform scale it matches a tile whose Z scale is
 * HeightRatio times its XY scale.
 */
USTRUCT(BlueprintType)
struct FHexPillarGCVariant
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Pillar Break")
	TObjectPtr<UGeometryCollection> Collection;

	/** Tile Z scale / XY scale this one is made for. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Pillar Break", meta = (ClampMin = "0.01"))
	float HeightRatio = 1.f;
};

/** How a top platform's collapsing tile breaks into its Geometry Collection (AMyHexPlatform::TopPillarGeometryCollection). */
USTRUCT(BlueprintType)
struct FHexPillarBreakSettings
{
	GENERATED_BODY()

	/**
	 * Most pillar Geometry Collections alive at once in the world (all platforms together). A break over
	 * the cap retires the oldest pillar whose pieces have come to rest (asleep), else the oldest one, if it
	 * is at least MinAgeToRecycle old; otherwise the break waits in the queue.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Pillar Break|Budget", meta = (ClampMin = "1"))
	int32 MaxActive = 64;

	/** Most pillar Geometry Collections created in one frame. The rest wait for the next frames. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Pillar Break|Budget", meta = (ClampMin = "1"))
	int32 MaxSpawnsPerFrame = 2;

	/** A queued break older than this (s) is dropped: its tile is long gone, so it would only pop in late. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Pillar Break|Budget", meta = (ClampMin = "0.0"))
	float MaxQueueTime = 0.5f;

	/** Over MaxActive, the oldest pillar is destroyed early once it is this old (s). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Pillar Break|Budget", meta = (ClampMin = "0.0"))
	float MinAgeToRecycle = 1.f;

	/**
	 * The pillar disappears after the platform's BrokenPropLifeSpan, the same delay and the same way as the
	 * tile prop debris (the whole Geometry Collection goes at once, full size). Off = after LifeSpan.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Pillar Break|Look")
	bool bMatchTilePropLifeSpan = true;

	/** Seconds a pillar lives when bMatchTilePropLifeSpan is off. Default: the props' 6 s plus a margin. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Pillar Break|Look", meta = (ClampMin = "0.1"))
	float LifeSpan = 6.5f;

	/**
	 * Let the asset's own removal run (Remove On Sleep / Remove On Break, which shrink pieces away). Off:
	 * pieces stay full size until the pillar goes.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Pillar Break|Look")
	bool bAssetRemoval = false;

	/** Seconds from spawn until the pillar comes apart (0 = at once). It drops whole until then. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Pillar Break|Look", meta = (ClampMin = "0.0"))
	float CrumbleDelay = 0.08f;

	/** Velocity (cm/s, world) the whole pillar starts with. The pieces keep it when it comes apart. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Pillar Break|Look")
	FVector InitialVelocity = FVector(0.f, 0.f, -150.f);

	/**
	 * Outward speed (cm/s) each piece gets when the pillar comes apart, away from the pillar's axis, times
	 * 0.5 .. 1 at random. Only towards the tile's open sides (no standing neighbour), so pieces aren't
	 * driven into the pillars next to it; a tile with none just drops apart. Scaled by HexRadius / 100.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Pillar Break|Look", meta = (ClampMin = "0.0"))
	float PieceSpreadSpeed = 120.f;

	/** Random vertical speed (cm/s, +-) added to each piece. Scaled like PieceSpreadSpeed. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Pillar Break|Look", meta = (ClampMin = "0.0"))
	float PieceVerticalJitter = 60.f;

	/**
	 * Most spin (deg/s) each piece gets, about a random axis. Keep it low if the platform spawns its
	 * pillars at a non-uniform scale (no height variants): a piece that turns far gets stretched.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Pillar Break|Look", meta = (ClampMin = "0.0"))
	float PieceMaxSpin = 90.f;

	/**
	 * The pieces block pawns and traces (Visibility, Camera) too. Off = cosmetic: they only hit the world
	 * and each other. Only for standalone: every machine places its own pieces, so blocking pawns with them
	 * makes the server's and the clients' movement disagree.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Pillar Break|Look")
	bool bBlocksPawns = false;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Pillar Break|Look")
	bool bCastShadow = true;

	/**
	 * Put the pieces in Lumen's scene (Affect Dynamic Indirect Lighting). Off: they are still lit by Lumen
	 * but don't bounce light or show in Lumen reflections, and Lumen doesn't capture cards for every new
	 * moving piece (that capture cost several GPU ms per break burst). Console override for tests:
	 * Aura.PillarBreak.Lumen 0/1 (-1 = this setting).
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Pillar Break|Look")
	bool bAffectLumen = false;
};

/**
 * Breaks top platform tiles into Geometry Collections under one world-wide budget.
 *
 * AMyHexPlatform::ActivateHexLocal queues a break when a top tile collapses near the local player
 * (the same trigger and range as the skeletal mesh fall of the bottom platforms). This runs on every
 * machine that renders, from the replicated ActivatedTiles, so the pieces are local and cosmetic:
 * nothing about them is replicated.
 *
 * Each break is a UGeometryCollectionComponent owned by its platform, placed where the removed instance
 * was, at its size (AMyHexPlatform::GetTopPillarCollection). It is set up before it is registered, so its
 * physics proxy is built once with the right velocity, scale and collision. Settings come from the
 * platform (FHexPillarBreakSettings).
 *
 * It also plays the far breaks (AddFarBreak): tiles and props that collapse beyond the break-effects range
 * get an instance of a baked-animation mesh in a world ISM per mesh, reusing hidden slots.
 */
UCLASS()
class AURA_API UMyHexPillarBreakSubsystem : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:

	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;
	virtual void Deinitialize() override;
	virtual void Tick(float DeltaTime) override;
	virtual bool IsTickable() const override;
	virtual TStatId GetStatId() const override;

	/**
	 * Breaks Collection at WorldTransform (a tile instance's) as soon as the budget allows. OpenSides =
	 * world space directions (XY) from the tile through its sides that have no standing neighbour.
	 * RemoveAfter = seconds until the pillar disappears.
	 */
	void QueueBreak(AMyHexPlatform* Platform, UGeometryCollection* Collection, const FTransform& WorldTransform,
		const TArray<FVector>& OpenSides, const FHexPillarBreakSettings& Settings, float LengthScale, float RemoveAfter);

	/**
	 * Starts compiling Collection's shaders (PSO precache) before its first break, once per world. In a
	 * packaged game a Geometry Collection draws nothing until they are ready, so the first pillar would be
	 * invisible. Platform owns the throwaway component.
	 */
	void PrecacheCollection(AMyHexPlatform* Platform, UGeometryCollection* Collection);

	int32 GetNumActive() const { return Active.Num(); }
	int32 GetNumQueued() const { return Queue.Num(); }

	/**
	 * Plays Far's baked break at WorldTransform: an instance in the world ISM for Far.Mesh with custom data
	 * [0] = world time now, [1] = Speed. Its slot is hidden and reused after Far.Length / Speed. False (and
	 * nothing added) when MaxActive (> 0) far breaks are already playing.
	 */
	bool AddFarBreak(const FHexFarBreakMesh& Far, const FTransform& WorldTransform, float Speed, int32 MaxActive);

	/** Makes Far's ISM now (empty), so its PSOs are compiled before the first far break needs them. */
	void PrewarmFarBreak(const FHexFarBreakMesh& Far);

	int32 GetNumFarActive() const { return NumFarActive; }

	/** Logs the counts (Aura.PillarBreakStats). */
	void LogStats() const;

protected:

	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;

private:

	struct FPendingBreak
	{
		TWeakObjectPtr<AMyHexPlatform> Platform;
		TWeakObjectPtr<UGeometryCollection> Collection;
		FTransform WorldTransform;
		TArray<FVector> OpenSides;
		FHexPillarBreakSettings Settings;
		float LengthScale = 1.f;
		float RemoveAfter = 6.f;
		double QueuedTime = 0.0;
	};

	struct FActiveBreak
	{
		TWeakObjectPtr<UGeometryCollectionComponent> Component;
		TArray<FVector> OpenSides;
		FHexPillarBreakSettings Settings;
		float LengthScale = 1.f;
		float RemoveAfter = 6.f;
		double SpawnTime = 0.0;
		bool bCrumbled = false;
	};

	/** A level 1 piece of a collection: its transform index and its centre in component space. */
	struct FPiece
	{
		int32 TransformIndex = INDEX_NONE;
		FVector Center = FVector::ZeroVector;
	};

	/** Spawns queued breaks within the budget (MaxSpawnsPerFrame, MaxActive); drops stale ones. */
	void ProcessQueue();

	UGeometryCollectionComponent* SpawnBreak(const FPendingBreak& Break);

	/** Breaks every cluster and pushes the pieces apart (out through the open sides, with spin). */
	void Crumble(FActiveBreak& Break);

	/** Every piece the crumble freed is asleep (lying still). */
	bool IsResting(const FActiveBreak& Break);

	/** Destroys the component and logs how long it lived. */
	void Retire(FActiveBreak& Break, const TCHAR* Reason);

	/** The root's children and their centres, worked out once per collection. */
	const TArray<FPiece>& GetPieces(const UGeometryCollection& Collection);

	/** Oldest first. */
	TArray<FPendingBreak> Queue;

	/** Oldest first. */
	TArray<FActiveBreak> Active;

	TMap<TObjectKey<UGeometryCollection>, TArray<FPiece>> PieceCache;

	/** Collections PrecacheCollection has started. */
	TSet<TObjectKey<UGeometryCollection>> PrecachedCollections;

	/** Spawns so far in frame SpawnFrame (GFrameCounter), for MaxSpawnsPerFrame. */
	uint64 SpawnFrame = 0;
	int32 SpawnedThisFrame = 0;

	/** One world ISM of far-break instances per mesh + material. */
	struct FFarPool
	{
		TWeakObjectPtr<UInstancedStaticMeshComponent> ISM;

		/** Per instance: world time it is freed (0 = free, hidden at zero scale). */
		TArray<double> FreeAt;

		TArray<int32> FreeSlots;
		int32 NumActive = 0;
	};

	FFarPool* FindOrAddFarPool(const FHexFarBreakMesh& Far);

	/** Hides the far-break instances whose animation has ended and frees their slots. */
	void TickFarBreaks(double Now);

	TMap<TPair<TObjectKey<UStaticMesh>, TObjectKey<UMaterialInterface>>, FFarPool> FarPools;

	/** Transient, never replicated: owns the far-break ISMs. */
	TWeakObjectPtr<AActor> FarBreakActor;

	int32 NumFarActive = 0;
	int32 NumFarAdded = 0;
	int32 NumFarReused = 0;
	int32 NumFarSkipped = 0;

	/** Totals since the world started, for the log. */
	int32 NumSpawned = 0;
	int32 NumDropped = 0;
	int32 NumRecycled = 0;
	int32 NumRecycledMoving = 0;
};
