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

void AMyHexPathSegment::InitSegment(int32 InSegmentIndex, const TArray<FVector>& Points, const TArray<FVector>& Tangents)
{
	SegmentIndex = InSegmentIndex;

	SegmentSpline->SetSplinePoints(Points, ESplineCoordinateSpace::World, /*bUpdateSpline=*/false);

	// Copy the tangents from the full path, so this piece lines up with its neighbours
	for (int32 Index = 0; Index < Points.Num() && Index < Tangents.Num(); ++Index)
	{
		SegmentSpline->SetTangentAtSplinePoint(Index, Tangents[Index], ESplineCoordinateSpace::World, /*bUpdateSpline=*/false);
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
