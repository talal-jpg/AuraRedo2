// Fill out your copyright notice in the Description page of Project Settings.


#include "Actors/MyHexPathSpawner.h"

#include "Actors/MyHexBridgeSubsystem.h"
#include "Actors/MyHexPathSegment.h"
#include "Components/SplineComponent.h"
#include "DrawDebugHelpers.h"
#include "Engine/World.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "TimerManager.h"

DEFINE_LOG_CATEGORY_STATIC(LogHexPath, Log, All);


// =============================================================================
// Constructor
// =============================================================================

AMyHexPathSpawner::AMyHexPathSpawner()
{
	PrimaryActorTick.bCanEverTick = false;

	// Only the server grows the path. The platforms PCG spawns replicate on their own.
	bReplicates = false;

	PathSpline = CreateDefaultSubobject<USplineComponent>(TEXT("PathSpline"));
	SetRootComponent(PathSpline);
}


// =============================================================================
// BeginPlay
// =============================================================================

void AMyHexPathSpawner::BeginPlay()
{
	Super::BeginPlay();

	if (!HasAuthority())
	{
		return;
	}

	StartYaw = GetActorRotation().Yaw;
	StartZ = GetActorLocation().Z;
	TravelledDistance = 0.f;

	// The path starts with a single point at the actor
	PathSpline->ClearSplinePoints(/*bUpdateSpline=*/false);
	PathSpline->AddSplinePoint(GetActorLocation(), ESplineCoordinateSpace::World, /*bUpdateSpline=*/true);
	NextSegmentIndex = 0;

	// Platforms measure "left behind" along this spline
	if (UMyHexBridgeSubsystem* Subsystem = GetWorld()->GetSubsystem<UMyHexBridgeSubsystem>())
	{
		Subsystem->RegisterPathSpline(PathSpline);
	}

	for (int32 Index = 0; Index < InitialSegments; ++Index)
	{
		ExtendPath();
	}

	GetWorldTimerManager().SetTimer(
		CheckTimerHandle,
		this,
		&ThisClass::CheckPlayers,
		CheckInterval,
		true
	);
}


// =============================================================================
// EndPlay
// =============================================================================

void AMyHexPathSpawner::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	if (HasAuthority())
	{
		if (UWorld* World = GetWorld())
		{
			if (UMyHexBridgeSubsystem* Subsystem = World->GetSubsystem<UMyHexBridgeSubsystem>())
			{
				Subsystem->UnregisterPathSpline(PathSpline);
			}
		}
	}

	Super::EndPlay(EndPlayReason);
}


// =============================================================================
// Player check
// =============================================================================

void AMyHexPathSpawner::CheckPlayers()
{
	DestroyPassedSegments();

	const int32 LastIndex = PathSpline->GetNumberOfSplinePoints() - 1;

	if (LastIndex < 0)
	{
		return;
	}

	const FVector PathEnd = PathSpline->GetLocationAtSplinePoint(LastIndex, ESplineCoordinateSpace::World);

	for (FConstPlayerControllerIterator It = GetWorld()->GetPlayerControllerIterator(); It; ++It)
	{
		const APlayerController* PlayerController = It->Get();
		const APawn* Pawn = PlayerController ? PlayerController->GetPawn() : nullptr;

		if (Pawn && FVector::DistSquared2D(Pawn->GetActorLocation(), PathEnd) <= FMath::Square(ExtendDistance * GetLayoutScale()))
		{
			// One segment per check; if the player is still close, the next check adds another
			ExtendPath();
			return;
		}
	}
}


// =============================================================================
// Extend
// =============================================================================

void AMyHexPathSpawner::ExtendPath()
{
	if (!HasAuthority())
	{
		return;
	}

	const int32 FirstIndex = PathSpline->GetNumberOfSplinePoints() - 1;

	if (FirstIndex < 0)
	{
		return;
	}

	FVector Current = PathSpline->GetLocationAtSplinePoint(FirstIndex, ESplineCoordinateSpace::World);

	const int32 NumPoints = FMath::Max(PointsPerSegment, 1);
	const float Scale = GetLayoutScale();
	const float Step = SegmentLength * Scale / NumPoints;


	// -------------------------------------------------------------------------
	// Walk forward, steering with noise
	// -------------------------------------------------------------------------

	for (int32 Index = 0; Index < NumPoints; ++Index)
	{
		// Heading for this step, sampled half way along it
		const float Yaw = StartYaw + SampleNoise((TravelledDistance + Step * 0.5f) / Scale * YawNoiseFrequency + NoiseSeed) * MaxYawDeviation;

		TravelledDistance += Step;

		FVector Next = Current + FRotator(0.f, Yaw, 0.f).Vector() * Step;

		// Height follows its own noise (offset seed), around the start height
		Next.Z = StartZ + SampleNoise(TravelledDistance / Scale * HeightNoiseFrequency + NoiseSeed + 101.7f) * HeightNoiseAmplitude;

		PathSpline->AddSplinePoint(Next, ESplineCoordinateSpace::World, /*bUpdateSpline=*/false);

		if (bDrawDebug)
		{
			DrawDebugLine(GetWorld(), Current, Next, FColor::Cyan, true, -1.f, 0, 20.f);
		}

		Current = Next;
	}

	PathSpline->UpdateSpline();


	// -------------------------------------------------------------------------
	// Copy the new piece into its own segment actor
	// -------------------------------------------------------------------------

	if (!SegmentClass)
	{
		UE_LOG(LogHexPath, Warning, TEXT("%s: SegmentClass is not set, the path grows but nothing is spawned along it"), *GetName());
		return;
	}

	const int32 LastIndex = PathSpline->GetNumberOfSplinePoints() - 1;

	TArray<FVector> Points;
	TArray<FVector> Tangents;

	for (int32 Index = FirstIndex; Index <= LastIndex; ++Index)
	{
		Points.Add(PathSpline->GetLocationAtSplinePoint(Index, ESplineCoordinateSpace::World));
		Tangents.Add(PathSpline->GetTangentAtSplinePoint(Index, ESplineCoordinateSpace::World));
	}

	const FTransform SpawnTransform(Points[0]);

	FActorSpawnParameters SpawnParams;
	SpawnParams.Owner = this;
	SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;

	AMyHexPathSegment* Segment = GetWorld()->SpawnActor<AMyHexPathSegment>(SegmentClass, SpawnTransform, SpawnParams);

	if (!Segment)
	{
		return;
	}

	Segment->SetHexRadius(HexRadius);
	Segment->SetPathDistances(
		PathSpline->GetDistanceAlongSplineAtSplinePoint(FirstIndex),
		PathSpline->GetDistanceAlongSplineAtSplinePoint(LastIndex)
	);
	Segment->InitSegment(NextSegmentIndex++, Points, Tangents);
	Segments.Add(Segment);
}


// =============================================================================
// Destroy passed segments
// =============================================================================

void AMyHexPathSpawner::DestroyPassedSegments()
{
	if (DestroySegmentsBehindDistance <= 0.f)
	{
		return;
	}

	const float BehindDistance = DestroySegmentsBehindDistance * GetLayoutScale();

	const UMyHexBridgeSubsystem* Subsystem = GetWorld()->GetSubsystem<UMyHexBridgeSubsystem>();
	float LeadDistance = 0.f;

	if (!Subsystem || Subsystem->GetPathSpline() != PathSpline.Get() || !Subsystem->GetLeadPathDistance(LeadDistance))
	{
		return;
	}

	// Segments are in path order, so stop at the first one that isn't far enough behind.
	// Safe for the platforms: PCG doesn't delete the actors it spawned when its component is torn down.
	while (Segments.Num() > 0
		&& (!IsValid(Segments[0]) || Segments[0]->GetPathEndDistance() < LeadDistance - BehindDistance))
	{
		if (IsValid(Segments[0]))
		{
			Segments[0]->Destroy();
		}

		Segments.RemoveAt(0);
	}
}


// =============================================================================
// Noise
// =============================================================================

float AMyHexPathSpawner::SampleNoise(float Value) const
{
	constexpr float PerlinGain = 2.f;

	return FMath::Clamp(FMath::PerlinNoise1D(Value) * PerlinGain, -1.f, 1.f);
}
