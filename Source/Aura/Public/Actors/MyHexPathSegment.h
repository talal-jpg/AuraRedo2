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
 */
UCLASS(Blueprintable)
class AURA_API AMyHexPathSegment : public AActor
{
	GENERATED_BODY()

public:

	AMyHexPathSegment();

	/** Sets the spline and runs the PCG graph. Points and tangents are world space. */
	void InitSegment(int32 InSegmentIndex, const TArray<FVector>& Points, const TArray<FVector>& Tangents);

	UFUNCTION(BlueprintPure, Category = "Hex Path")
	int32 GetSegmentIndex() const { return SegmentIndex; }

	/** Distances along the spawner's PathSpline where this segment starts and ends. Set by the spawner. */
	void SetPathDistances(float InStartDistance, float InEndDistance) { PathStartDistance = InStartDistance; PathEndDistance = InEndDistance; }

	/**
	 * Distance along the spawner's PathSpline where this segment starts. SegmentSpline has the same
	 * points and tangents as that part of the path, so a distance along SegmentSpline plus this is the
	 * distance along the whole path (what the PCG graph writes to AMyHexPlatform::SplineDistance).
	 */
	UFUNCTION(BlueprintPure, Category = "Hex Path")
	float GetPathStartDistance() const { return PathStartDistance; }

	UFUNCTION(BlueprintPure, Category = "Hex Path")
	float GetPathEndDistance() const { return PathEndDistance; }

	UFUNCTION(BlueprintPure, Category = "Hex Path")
	USplineComponent* GetSegmentSpline() const { return SegmentSpline; }

protected:

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
};
