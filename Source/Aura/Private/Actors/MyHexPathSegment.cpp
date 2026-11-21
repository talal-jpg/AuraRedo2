// Fill out your copyright notice in the Description page of Project Settings.


#include "Actors/MyHexPathSegment.h"

#include "Actors/MyHexAtmosphereFX.h"
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
// EndPlay
// =============================================================================

void AMyHexPathSegment::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	AMyHexAtmosphereFX::DestroyAttachedTo(this);

	Super::EndPlay(EndPlayReason);
}


// =============================================================================
// Init
// =============================================================================

void AMyHexPathSegment::SetLayout(float InHexRadius, const FVector& InLayoutOrigin)
{
	HexRadius = InHexRadius;
	LayoutScale = FMath::Max(InHexRadius / 100.f, KINDA_SMALL_NUMBER);
	LayoutUpScale = FVector(LayoutScale, LayoutScale, 1.f);
	LayoutDownScale = FVector(1.f / LayoutScale, 1.f / LayoutScale, 1.f);

	// Scaling around the origin: O + (P - O) * Scale = P * Scale + (O - O * Scale). Z stays (its scale is 1).
	LayoutUpOffset = InLayoutOrigin - InLayoutOrigin * LayoutUpScale;
	LayoutDownOffset = InLayoutOrigin - InLayoutOrigin * LayoutDownScale;
}


// =============================================================================
// Assumed bounds
// =============================================================================

void AMyHexPathSegment::SetSegmentBounds(const FVector& Center, const FVector& Extent, const FRotator& Rotation)
{
	SegmentBoundsCenter = Center;
	SegmentBoundsExtent = Extent.GetAbs();
	SegmentBoundsRotation = Rotation;
	bHasSegmentBounds = true;
}

void AMyHexPathSegment::GetSegmentBounds(FVector& OutCenter, FVector& OutExtent, FRotator& OutRotation) const
{
	OutCenter = SegmentBoundsCenter;
	OutExtent = SegmentBoundsExtent;
	OutRotation = SegmentBoundsRotation;
}

TArray<FVector> AMyHexPathSegment::GetSegmentBoundsCorners(bool bTop, bool bBottom) const
{
	TArray<FVector> Corners;

	if (!bHasSegmentBounds)
	{
		return Corners;
	}

	// Box space (-X,-Y), (+X,-Y), (+X,+Y), (-X,+Y): X is along the path, so start, end, end, start
	static constexpr double SignX[4] = { -1.0, 1.0, 1.0, -1.0 };
	static constexpr double SignY[4] = { -1.0, -1.0, 1.0, 1.0 };

	const FQuat Rotation = SegmentBoundsRotation.Quaternion();
	const FVector& Extent = SegmentBoundsExtent;

	auto AddLayer = [&](double SignZ)
	{
		for (int32 Index = 0; Index < 4; ++Index)
		{
			const FVector Local(SignX[Index] * Extent.X, SignY[Index] * Extent.Y, SignZ * Extent.Z);
			Corners.Add(SegmentBoundsCenter + Rotation.RotateVector(Local));
		}
	};

	Corners.Reserve((bTop ? 4 : 0) + (bBottom ? 4 : 0));

	if (bTop)
	{
		AddLayer(1.0);
	}

	if (bBottom)
	{
		AddLayer(-1.0);
	}

	return Corners;
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
		LayoutPoints.Add(Point * LayoutDownScale + LayoutDownOffset);
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
