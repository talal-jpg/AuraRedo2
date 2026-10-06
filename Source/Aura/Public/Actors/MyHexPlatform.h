#pragma once

#include "CoreMinimal.h"
#include "ScalableFloat.h"
#include "GameFramework/Actor.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/TimerHandle.h"
#include "MyHexPlatform.generated.h"


struct FScalableFloat;
class AMyHexBridge;
class AMyHexPlatform;
class APawn;
class USplineComponent;
class UMyHexBridgeSubsystem;

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


UCLASS()
class AURA_API AMyHexPlatform : public AActor
{
	GENERATED_BODY()
	
	friend class AMyHexBridgeBuilder;
	friend class UMyHexBridgeSubsystem;

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

	/** Server. The lead player is on this platform. Latched, so it may arrive before the bridges are ready. */
	void NotifyLeadLanded();

	/** Server. Bridges that end on this platform register so a player over them keeps it alive. */
	void RegisterBridge(AMyHexBridge* Bridge);
	void UnregisterBridge(AMyHexBridge* Bridge);

	/** True once the tile has started collapsing, on this machine or on the server. */
	bool IsTileCollapsed(const FIntVector& Coord) const;
	
	TArray<FIntVector> GetOriginalEdgeHexes() const;

	TMap<int32, TArray<FIntVector>> GetEdgeInstances() const;
	
	TMap<int32, TArray<FIntVector>> EdgeInstances;

	/** Distance along the whole path spline at the point this platform was sampled from. -1 = not set. */
	UFUNCTION(BlueprintPure, Category = "Hex Platform|Path")
	float GetSplineDistance() const { return SplineDistance; }

	bool HasSplineDistance() const { return SplineDistance >= 0.f; }

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
	// Lead player (server only)
	// -------------------------------------------------------------------------

	/**
	 * Collapse starts only once the lead player (UMyHexBridgeSubsystem::GetLeadPawn) is on this
	 * platform and its bridges are built. Off = collapse as soon as the bridges are built.
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
	 * A platform whose centre is within this horizontal distance (cm) of the path spline is judged by
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

	void GenerateAndActivateChainFromRandomSelectedGrid();

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
	// skeletal mesh component
	//      ->
	// play animation
	//
	// bPlayEffect = false stops after removing the instance (no skeletal mesh or animation).
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
};
