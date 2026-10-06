// Fill out your copyright notice in the Description page of Project Settings.


#include "Actors/MyHexPathSegment.h"

#include "Components/SplineComponent.h"
#include "PCGComponent.h"


// =============================================================================
// Constructor
// =============================================================================

AMyHexPathSegment::AMyHexPathSegment()
{
	PrimaryActorTick.bCanEverTick = false;

	// Only the server builds the path. The platforms PCG spawns replicate on their own.
	bReplicates = false;

	SegmentSpline = CreateDefaultSubobject<USplineComponent>(TEXT("SegmentSpline"));
	SetRootComponent(SegmentSpline);

	PCGComponent = CreateDefaultSubobject<UPCGComponent>(TEXT("PCGComponent"));

	// Generated from InitSegment once the spline has its points, never on load
	PCGComponent->GenerationTrigger = EPCGComponentGenerationTrigger::GenerateOnDemand;
}


// =============================================================================
// Init
// =============================================================================

void AMyHexPathSegment::SetHexRadius(float InHexRadius)
{
	HexRadius = InHexRadius;
	LayoutScale = FMath::Max(InHexRadius / 100.f, KINDA_SMALL_NUMBER);
	LayoutUpScale = FVector(LayoutScale, LayoutScale, 1.f);
	LayoutDownScale = FVector(1.f / LayoutScale, 1.f / LayoutScale, 1.f);
}

void AMyHexPathSegment::InitSegment(int32 InSegmentIndex, const TArray<FVector>& Points, const TArray<FVector>& Tangents)
{
	SegmentIndex = InSegmentIndex;
	LayoutPathStartDistance = PathStartDistance / LayoutScale;

	// Layout space: X and Y shrunk by LayoutScale. A cubic spline scaled this way (points and tangents)
	// is exactly the scaled curve, so the PCG graph sees the path it was tuned on at HexRadius 100.
	TArray<FVector> LayoutPoints;
	LayoutPoints.Reserve(Points.Num());

	for (const FVector& Point : Points)
	{
		LayoutPoints.Add(Point * LayoutDownScale);
	}

	SegmentSpline->SetSplinePoints(LayoutPoints, ESplineCoordinateSpace::World, /*bUpdateSpline=*/false);

	// Copy the tangents from the full path, so this piece lines up with its neighbours
	for (int32 Index = 0; Index < Points.Num() && Index < Tangents.Num(); ++Index)
	{
		SegmentSpline->SetTangentAtSplinePoint(Index, Tangents[Index] * LayoutDownScale, ESplineCoordinateSpace::World, /*bUpdateSpline=*/false);
	}

	SegmentSpline->UpdateSpline();

	if (PCGComponent && PCGComponent->GetGraph())
	{
		// Different seed per segment, so segments don't repeat the same random choices
		PCGComponent->Seed = SegmentIndex;
		PCGComponent->GenerateLocal(/*bForce=*/true);
	}

	OnSegmentInitialized();
}
