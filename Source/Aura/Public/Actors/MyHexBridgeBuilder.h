// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Engine/EngineTypes.h"
#include "Engine/TimerHandle.h"
#include "GameFramework/Actor.h"
#include "MyHexBridgeBuilder.generated.h"

class USplineComponent;


/**
 * Connects nearby AMyHexPlatforms with splines.
 *
 * For every pair of platforms in range it line-traces between the open sides ("edges") of their
 * edge tiles. Two edges are connected when the trace from each of them reaches the other one
 * (the first thing the line hits is the other platform, at that edge). Every connected pair gets
 * its own USplineComponent running from one edge to the other.
 *
 * Nothing is replicated: every machine builds the same splines from the same static grids.
 */
UCLASS()
class AMyHexBridgeBuilder : public AActor
{
	GENERATED_BODY()

public:

	AMyHexBridgeBuilder();

	/** Destroys the old splines and rebuilds them from the platforms' current edges. */
	UFUNCTION(BlueprintCallable, CallInEditor, Category = "Hex Bridges")
	void BuildBridges();

	/** Destroys every spline created by BuildBridges. */
	UFUNCTION(BlueprintCallable, CallInEditor, Category = "Hex Bridges")
	void ClearBridges();

	/** Splines created by the last BuildBridges call. */
	const TArray<TObjectPtr<USplineComponent>>& GetBridgeSplines() const { return BridgeSplines; }


	// -------------------------------------------------------------------------
	// Settings
	// -------------------------------------------------------------------------

	/** Build automatically shortly after BeginPlay. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Hex Bridges")
	bool bBuildOnBeginPlay = true;

	/**
	 * Seconds to wait after BeginPlay before building, so every platform has finished its own
	 * BeginPlay (which rebuilds its grid) and its collision exists.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Hex Bridges",
		meta = (EditCondition = "bBuildOnBeginPlay", ClampMin = "0.01"))
	float BuildDelay = 0.1f;

	/**
	 * Two platforms are paired when the distance between their origins is at most
	 * NeighborRadiusMultiplier * GridSize * HexRadius (the larger of the two platforms' values).
	 *
	 * A grid reaches up to ~1.7 * GridSize * HexRadius from its origin, so 2 only pairs platforms
	 * that almost touch. Raise it to bridge real gaps.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Hex Bridges", meta = (ClampMin = "0.0"))
	float NeighborRadiusMultiplier = 2.f;

	/** Edge pairs further apart than this (cm) are skipped without tracing. 0 = unlimited. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Hex Bridges", meta = (ClampMin = "0.0"))
	float MaxBridgeLength = 0.f;

	/**
	 * Only trace between edges whose outward normals face each other. Edges that don't face each
	 * other can't be bridged anyway, and skipping them removes most of the traces.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Hex Bridges")
	bool bRequireFacingEdges = true;

	/** Trace channel the platforms block. They block everything, so Visibility works. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Hex Bridges")
	TEnumAsByte<ECollisionChannel> TraceChannel = ECC_Visibility;


protected:

	virtual void BeginPlay() override;

private:

	USplineComponent* CreateBridgeSpline(const FVector& From, const FVector& To);

	UPROPERTY(Transient)
	TArray<TObjectPtr<USplineComponent>> BridgeSplines;

	FTimerHandle BuildTimerHandle;
};
