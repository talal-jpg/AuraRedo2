// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "MyHexPathSegment.generated.h"

class UPCGComponent;
class USplineComponent;

/**
 * One piece of the path built by AMyHexPathSpawner. Server only.
 *
 * Holds a copy of its part of the path spline and a PCG component that samples it, so each
 * extension generates on its own. Regenerating one long spline would clean up and respawn every
 * platform spawned before, including their collapse state.
 *
 * Use a Blueprint child with the PCG graph set. Inside the graph, Get Spline Data on this actor
 * returns SegmentSpline.
 *
 * Layout space: the PCG graph was tuned for platforms of HexRadius 100. For bigger platforms
 * SegmentSpline holds the path shrunk horizontally by LayoutScale around the path's start (X and Y
 * only; heights unchanged). That is exactly the path the spawner grows at HexRadius 100, so the graph
 * lays platforms out exactly as at HexRadius 100, random choices included. It then maps the results
 * back to the world (position * LayoutUpScale + LayoutUpOffset) and shrinks the obstacles it reads
 * from the world (position * LayoutDownScale + LayoutDownOffset, scale * LayoutDownScale).
 * At HexRadius 100 all of this is the identity.
 *
 * The spawner also stores the world box the segment's platforms are assumed to fill (SetSegmentBounds), worked out
 * from the world path before PCG runs, so sentinel waves can spawn at its corners.
 */
UCLASS(Blueprintable)
class AURA_API AMyHexPathSegment : public AActor
{
	GENERATED_BODY()

public:

	AMyHexPathSegment();

	/** Sets the spline (in layout space, see above) and runs the PCG graph. Points and tangents are world space. */
	void InitSegment(int32 InSegmentIndex, const TArray<FVector>& Points, const TArray<FVector>& Tangents);

	UFUNCTION(BlueprintPure, Category = "Hex Path")
	int32 GetSegmentIndex() const { return SegmentIndex; }

	/** Distances along the spawner's PathSpline where this segment starts and ends. Set by the spawner. */
	void SetPathDistances(float InStartDistance, float InEndDistance) { PathStartDistance = InStartDistance; PathEndDistance = InEndDistance; }

	/**
	 * Distance along the spawner's PathSpline where this segment starts. SegmentSpline is that part of
	 * the path in layout space, so (distance along SegmentSpline + LayoutPathStartDistance) * LayoutScale
	 * is the distance along the whole path (what the PCG graph writes to AMyHexPlatform::SplineDistance).
	 */
	UFUNCTION(BlueprintPure, Category = "Hex Path")
	float GetPathStartDistance() const { return PathStartDistance; }

	UFUNCTION(BlueprintPure, Category = "Hex Path")
	float GetPathEndDistance() const { return PathEndDistance; }

	UFUNCTION(BlueprintPure, Category = "Hex Path")
	USplineComponent* GetSegmentSpline() const { return SegmentSpline; }

	/**
	 * Set by the spawner before InitSegment: the platforms' HexRadius (LayoutScale = HexRadius / 100)
	 * and the point layout space is scaled around (the start of the path).
	 */
	void SetLayout(float InHexRadius, const FVector& InLayoutOrigin);

	/**
	 * Set by the spawner when the segment spawns, before PCG has spawned anything: the world box its platforms are
	 * assumed to fill (AMyHexPathSpawner, Path|Segment Bounds). Extent is the half size along the box's own axes, and
	 * Rotation turns the box (yaw only): box X runs along the path from the segment's start to its end, box Y across it.
	 */
	void SetSegmentBounds(const FVector& Center, const FVector& Extent, const FRotator& Rotation);

	UFUNCTION(BlueprintPure, Category = "Hex Path|Bounds")
	bool HasSegmentBounds() const { return bHasSegmentBounds; }

	/** World centre, half size along the box axes and rotation of the assumed bounds (zero without bounds). */
	UFUNCTION(BlueprintPure, Category = "Hex Path|Bounds")
	void GetSegmentBounds(FVector& OutCenter, FVector& OutExtent, FRotator& OutRotation) const;

	/**
	 * World corners of the assumed bounds, empty without bounds. Fixed order: the 4 top corners (bTop), then the 4
	 * bottom ones (bBottom), each 4 in box space (-X,-Y), (+X,-Y), (+X,+Y), (-X,+Y): start, end, end, start of the segment.
	 */
	UFUNCTION(BlueprintPure, Category = "Hex Path|Bounds")
	TArray<FVector> GetSegmentBoundsCorners(bool bTop = true, bool bBottom = false) const;

protected:

	/** Destroys the fog banks the graph spawned (PCG leaves the actors it spawned behind). */
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

	/** Runs after the spline is set and PCG generation has been requested. */
	UFUNCTION(BlueprintImplementableEvent, Category = "Hex Path")
	void OnSegmentInitialized();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Hex Path")
	TObjectPtr<USplineComponent> SegmentSpline;

	/** Set its graph in a Blueprint child. Generation is started by InitSegment, not on load. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Hex Path")
	TObjectPtr<UPCGComponent> PCGComponent;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "Hex Path")
	int32 SegmentIndex = INDEX_NONE;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "Hex Path")
	float PathStartDistance = 0.f;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "Hex Path")
	float PathEndDistance = 0.f;

	// -------------------------------------------------------------------------
	// Scale. The PCG graph reads these with Get Actor Property on Self.
	// -------------------------------------------------------------------------

	/** The spawner's HexRadius, passed to every platform as the HexRadius override. */
	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "Hex Path|Scale")
	float HexRadius = 100.f;

	/** HexRadius / 100: layout space is the world shrunk horizontally by this. Spline distances are multiplied by it. */
	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "Hex Path|Scale")
	float LayoutScale = 1.f;

	/** (LayoutScale, LayoutScale, 1). */
	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "Hex Path|Scale")
	FVector LayoutUpScale = FVector::OneVector;

	/** Layout space to world: world = layout * LayoutUpScale + LayoutUpOffset. */
	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "Hex Path|Scale")
	FVector LayoutUpOffset = FVector::ZeroVector;

	/** (1 / LayoutScale, 1 / LayoutScale, 1). */
	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "Hex Path|Scale")
	FVector LayoutDownScale = FVector::OneVector;

	/** World to layout space: layout = world * LayoutDownScale + LayoutDownOffset. */
	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "Hex Path|Scale")
	FVector LayoutDownOffset = FVector::ZeroVector;

	/** PathStartDistance / LayoutScale, the segment start in layout-space distance along the path. */
	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "Hex Path|Scale")
	float LayoutPathStartDistance = 0.f;

	// -------------------------------------------------------------------------
	// Assumed bounds (SetSegmentBounds), world space. Read them with the getters.
	// -------------------------------------------------------------------------

	UPROPERTY(VisibleInstanceOnly, Category = "Hex Path|Bounds")
	bool bHasSegmentBounds = false;

	UPROPERTY(VisibleInstanceOnly, Category = "Hex Path|Bounds")
	FVector SegmentBoundsCenter = FVector::ZeroVector;

	/** Half size along the box axes. */
	UPROPERTY(VisibleInstanceOnly, Category = "Hex Path|Bounds")
	FVector SegmentBoundsExtent = FVector::ZeroVector;

	/** Yaw only. */
	UPROPERTY(VisibleInstanceOnly, Category = "Hex Path|Bounds")
	FRotator SegmentBoundsRotation = FRotator::ZeroRotator;
};
