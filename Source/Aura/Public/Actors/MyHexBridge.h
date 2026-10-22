// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "MyHexBridge.generated.h"

class AMyHexPlatform;
class UGeometryCollection;
class UInstancedStaticMeshComponent;
class UPCGComponent;
class USplineComponent;
class UStaticMesh;

/** What happens to a bridge's PCG pieces when an end tile collapses. */
UENUM(BlueprintType)
enum class EMyHexBridgeCollapseMode : uint8
{
	/** The bridge disappears at once. */
	None,

	/** Each piece is swapped for its Geometry Collection (BreakableMeshes); a piece without one falls whole. */
	GeometryCollections,

	/** Each piece is swapped for a static mesh that simulates physics. */
	PhysicsMeshes,
};

/** One end of a bridge: the edge tile it starts from and the point on that tile's open side. */
USTRUCT(BlueprintType)
struct FMyHexBridgeEnd
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly, Category = "Hex Bridge")
	TObjectPtr<AMyHexPlatform> Platform = nullptr;

	/** Hex coordinate (Q, R, S) of the edge tile on that platform. */
	UPROPERTY(BlueprintReadOnly, Category = "Hex Bridge")
	FIntVector Tile = FIntVector::ZeroValue;

	/** World-space middle of the tile's open side, at walking-surface height. */
	UPROPERTY(BlueprintReadOnly, Category = "Hex Bridge")
	FVector Location = FVector::ZeroVector;
};

/** Both ends, replicated together so a client always gets a matching pair. */
USTRUCT(BlueprintType)
struct FMyHexBridgeEnds
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly, Category = "Hex Bridge")
	FMyHexBridgeEnd Start;

	UPROPERTY(BlueprintReadOnly, Category = "Hex Bridge")
	FMyHexBridgeEnd End;

	/**
	 * World-space spline tangents at Start and End (UE convention: the derivative with respect to the
	 * input key between the two points). Both zero = a straight bridge.
	 */
	UPROPERTY()
	FVector StartTangent = FVector::ZeroVector;

	UPROPERTY()
	FVector EndTangent = FVector::ZeroVector;
};

DECLARE_DYNAMIC_MULTICAST_DELEGATE_ThreeParams(
	FOnHexBridgeEndTileCollapsedSignature,
	AMyHexBridge*, Bridge,
	AMyHexPlatform*, Platform,
	FIntVector, Tile
);

/**
 * A bridge between two edge tiles of two AMyHexPlatforms.
 *
 * Spawned by UMyHexBridgeSubsystem on the server and replicated. Its spline runs from one tile's
 * open side to the other's, and its PCG component builds the bridge from that spline on every
 * machine (PCG output is not replicated).
 *
 * The bridge listens to both platforms. When either end tile collapses (activates), on any machine,
 * HandleEndTileCollapsed runs and OnEndTileCollapsed broadcasts.
 *
 * With a CollapseMode, the collapse then runs from that end to the other on every machine: each PCG
 * instance (walk colliders included) is removed when the front reaches it and, near the local
 * player, is replaced by falling debris. The server destroys the bridge once the front is through.
 */
UCLASS(Blueprintable)
class AURA_API AMyHexBridge : public AActor
{
	GENERATED_BODY()

public:

	AMyHexBridge();

	/** Server only, between SpawnActorDeferred and FinishSpawning. Zero tangents = straight. */
	void InitBridge(const FMyHexBridgeEnd& InStart, const FMyHexBridgeEnd& InEnd, const FVector& InStartTangent = FVector::ZeroVector, const FVector& InEndTangent = FVector::ZeroVector, bool bInIsBottomBridge = false);

	UFUNCTION(BlueprintPure, Category = "Hex Bridge")
	const FMyHexBridgeEnds& GetEnds() const { return Ends; }

	/** True once either end tile has collapsed. */
	UFUNCTION(BlueprintPure, Category = "Hex Bridge")
	bool HasEndTileCollapsed() const { return bEndTileCollapsed; }

	/** Fires once, on every machine, when the first of the two end tiles collapses. */
	UPROPERTY(BlueprintAssignable, Category = "Hex Bridge")
	FOnHexBridgeEndTileCollapsedSignature OnEndTileCollapsed;

	/**
	 * Both end platforms are on the lower chain (HexLower). Set by UMyHexBridgeSubsystem at spawn and
	 * replicated with the first update, so every machine has it in BeginPlay. Never changes.
	 */
	UPROPERTY(Replicated, VisibleInstanceOnly, BlueprintReadOnly, Category = "Hex Bridge")
	bool bIsBottomBridge = false;

	/**
	 * Testing (console Aura.CollapseBridges): runs the collapse on this machine only, with debris,
	 * from the end nearer Near, as if that end tile had collapsed.
	 */
	void DebugCollapse(const FVector& Near);

protected:

	virtual void BeginPlay() override;

	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

	/** Only ticks while a collapse is running. */
	virtual void Tick(float DeltaSeconds) override;

	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	/**
	 * Runs once, on every machine, when the first end tile collapses. The default destroys the
	 * bridge on the server after DestroyDelay (when bDestroyWhenEndTileCollapses is set).
	 * Override in Blueprint to play an effect; call the parent to keep the destroy.
	 */
	UFUNCTION(BlueprintNativeEvent, Category = "Hex Bridge")
	void HandleEndTileCollapsed(AMyHexPlatform* Platform, FIntVector Tile);

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Hex Bridge")
	TObjectPtr<USplineComponent> BridgeSpline;

	/** Set its graph in a Blueprint child. Generation is started from BeginPlay, not on load. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Hex Bridge")
	TObjectPtr<UPCGComponent> PCGComponent;

	/** Run the PCG graph in BeginPlay, once the spline has its points. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Hex Bridge")
	bool bGenerateOnBeginPlay = true;

	/**
	 * A top bridge (not bIsBottomBridge) dips like a rope bridge: its middle sits this fraction of the
	 * distance between its ends below the planned deck. 0 = no dip. Bottom bridges never dip.
	 * The planner's slope and clearance checks don't include the dip.
	 */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Hex Bridge", meta = (ClampMin = "0.0"))
	float SagRatio = 0.1143f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Hex Bridge")
	bool bDestroyWhenEndTileCollapses = true;

	/**
	 * Seconds between the end tile collapsing and the server destroying the bridge. With a
	 * CollapseMode, counted from when the collapse has reached the far end instead.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Hex Bridge", meta = (ClampMin = "0.0", EditCondition = "bDestroyWhenEndTileCollapses"))
	float DestroyDelay = 0.f;

	/** How the pieces go when an end tile collapses. None = the bridge just disappears. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Hex Bridge|Collapse")
	EMyHexBridgeCollapseMode CollapseMode = EMyHexBridgeCollapseMode::PhysicsMeshes;

	/** GeometryCollections mode: the Geometry Collection each PCG mesh breaks into. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Hex Bridge|Collapse", meta = (EditCondition = "CollapseMode == EMyHexBridgeCollapseMode::GeometryCollections"))
	TMap<TObjectPtr<UStaticMesh>, TObjectPtr<UGeometryCollection>> BreakableMeshes;

	/** How fast the collapse travels along the bridge from the end whose tile broke, in cm/s. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Hex Bridge|Collapse", meta = (ClampMin = "1.0"))
	float CollapseSpeed = 1500.f;

	/** Up to this many seconds of random delay per piece, so pieces at the same distance don't all go together. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Hex Bridge|Collapse", meta = (ClampMin = "0.0"))
	float CollapseJitter = 0.15f;

	/** Debris (Geometry Collections and physics meshes) is removed this many seconds after it starts falling. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Hex Bridge|Collapse", meta = (ClampMin = "0.0"))
	float DebrisLifeSpan = 8.f;

	/** Starting velocity of each piece of debris; each also gets a random sideways spread of up to half its size. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Hex Bridge|Collapse")
	FVector DebrisVelocity = FVector(0.f, 0.f, -100.f);

	/** Physics meshes start spinning at up to this many degrees per second around each axis. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Hex Bridge|Collapse", meta = (ClampMin = "0.0"))
	float DebrisMaxSpin = 90.f;

	/** Geometry Collections break into their fragments this many seconds after they start falling (< 0 = never). */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Hex Bridge|Collapse")
	float CrumbleDelay = 0.25f;

	/** No debris when the bridge is further than this (horizontally) from the local player: pieces just vanish. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Hex Bridge|Collapse", meta = (ClampMin = "0.0"))
	float DebrisMaxDistance = 5000.f;

private:

	UPROPERTY(ReplicatedUsing = OnRep_Ends)
	FMyHexBridgeEnds Ends;

	UFUNCTION()
	void OnRep_Ends();

	/** Puts the spline on the two end points, with the custom tangents when there are any and the dip of a top bridge. */
	void ApplyEnds();

	/**
	 * (Re)binds to both platforms' tile-activated delegates. Safe to call more than once: on a client
	 * a platform reference can arrive after the bridge, and OnRep_Ends runs again when it resolves.
	 */
	void BindToPlatforms();

	void OnPlatformTileActivated(AMyHexPlatform* Platform, const FIntVector& Tile);

	/** Server. An end platform was destroyed (culled) or streamed out: the bridge goes with it. */
	UFUNCTION()
	void HandleEndPlatformEndPlay(AActor* Actor, EEndPlayReason::Type EndPlayReason);

	void NotifyEndTileCollapsed(AMyHexPlatform* Platform, const FIntVector& Tile);

	bool bEndTileCollapsed = false;

	/** The end tile went down while this machine watched. False on a late join: the pieces just vanish. */
	bool bEndTileCollapseSeen = true;

	/** The end the collapse starts from (the tile that broke first) is Ends.Start. */
	bool bCollapseFromStart = true;

	// ---- Collapse (every machine) ----

	/** One PCG instance or attached actor, in the order the collapse reaches it. */
	struct FCollapsePiece
	{
		/** Seconds after the collapse starts. */
		float Time = 0.f;

		/** Into CollapseISMs, or INDEX_NONE for an attached actor. */
		int32 Owner = INDEX_NONE;

		/** Current instance index in its ISM. */
		int32 Instance = INDEX_NONE;

		FTransform WorldTransform;

		TWeakObjectPtr<AActor> Actor;
	};

	struct FCollapseISM
	{
		TWeakObjectPtr<UInstancedStaticMeshComponent> ISM;

		/** Piece at each current instance index, kept in step with the ISM's remove-at-swap. */
		TArray<int32> PieceAtInstance;

		/** Spawn debris for its instances (a visible mesh, near the local player). */
		bool bDebris = false;

		UGeometryCollection* Collection = nullptr;
	};

	/** Starts the front at the bCollapseFromStart end. bWithDebris false = pieces just vanish. */
	void StartCollapse(bool bWithDebris);

	/** Removes every piece the front has reached by CollapseElapsed. */
	void AdvanceCollapse();

	void FinishCollapse();

	void SpawnDebris(const FCollapseISM& Entry, const FTransform& WorldTransform);

	void SpawnDebrisCollection(UGeometryCollection* Collection, const FTransform& WorldTransform, const FVector& Velocity);

	void SpawnDebrisMesh(UInstancedStaticMeshComponent* Source, const FTransform& WorldTransform, const FVector& Velocity);

	/** True if any point of the bridge is within DebrisMaxDistance of the local player. */
	bool IsNearLocalPlayer() const;

	TArray<FCollapsePiece> CollapsePieces;

	/** CollapsePieces indices sorted by Time; CollapseCursor = next to go. */
	TArray<int32> CollapseOrder;

	int32 CollapseCursor = 0;

	TArray<FCollapseISM> CollapseISMs;

	float CollapseElapsed = 0.f;

	bool bCollapsing = false;

	/** Holds the physics mesh debris, so it outlives the bridge. Spawned on first use. */
	TWeakObjectPtr<AActor> DebrisHolder;
};
