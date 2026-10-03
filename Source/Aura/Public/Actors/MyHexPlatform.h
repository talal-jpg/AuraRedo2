#pragma once

#include "CoreMinimal.h"
#include "ScalableFloat.h"
#include "GameFramework/Actor.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "MyHexPlatform.generated.h"


struct FScalableFloat;
class AMyHexPlatform;

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

	/** Starts the timer that collapses chains of tiles. Server only; does nothing after the first call. */
	void StartCollapsing();

	/** True once the tile has started collapsing, on this machine or on the server. */
	bool IsTileCollapsed(const FIntVector& Coord) const;
	
	TArray<FIntVector> GetOriginalEdgeHexes() const;

	TMap<int32, TArray<FIntVector>> GetEdgeInstances() const;
	
	TMap<int32, TArray<FIntVector>> EdgeInstances;
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
	// -------------------------------------------------------------------------

	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Hex Platform|Assets")
	TObjectPtr<UStaticMesh> HexPillarStaticMesh;

	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Hex Platform|Assets")
	TObjectPtr<USkeletalMesh> HexPillarSkeletalMesh;

	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Hex Platform|Assets")
	TObjectPtr<UAnimSequence> RbdAnimSeq;


	// -------------------------------------------------------------------------
	// Grid
	// -------------------------------------------------------------------------

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Hex Platform|Deletion")
	int32 GridSize = 10;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Grid")
	float HexRadius = 100.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Grid")
	float VerticalScaling= .5;
	
	
	//NoiseDeletion
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Deletion")
	FVector2D NoiseOffset=FVector2D(0,0);
	
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Deletion")
	float NoiseScale=1;
	
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Deletion")
	float DistRangeMaxToStopDeletion=0.f;
	
	
	UPROPERTY(EditAnywhere, Category="Hex Platform|Deletion", meta=(ClampMin="0.1"))
	float NoiseFrequency = 3.f;    // spikes around the edge, roughly 3x this

	UPROPERTY(EditAnywhere, Category="Hex Platform|Deletion", meta=(ClampMin="0.0", ClampMax="0.6"))
	float NoiseStrength = 0.3f;    // how far the edge moves in/out, fraction of its radius

	UPROPERTY(EditAnywhere, Category="Hex Platform|Deletion", meta=(ClampMin="0.0", ClampMax="1.0"))
	float DetailStrength = 0.3f;   // extra fine jaggedness, 0 = off
	
	
	// UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Deletion")
	// FRuntimeFloatCurve NoiseCurve;
	
	// UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Deletion")
	// FScalableFloat NoiseCurve;
	
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Deletion")
	UCurveFloat* NoiseCurve;
	
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Deletion")
	float DeletionThreshold=-1;

	/**
	 * Wait for UMyHexBridgeSubsystem to build this platform's bridges before collapsing starts,
	 * so the bridges are made from the untouched edges. Off = start collapsing in BeginPlay.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Platform|Bridges")
	bool bWaitForBridgesBeforeCollapsing = true;

	bool bCollapseStarted = false;

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
	void ActivateHexLocal(
		const FIntVector& Coord
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
};
