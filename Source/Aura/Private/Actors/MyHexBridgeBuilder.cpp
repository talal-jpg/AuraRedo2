// Fill out your copyright notice in the Description page of Project Settings.


#include "Actors/MyHexBridgeBuilder.h"

#include "Actors/MyHexPlatform.h"
#include "CollisionQueryParams.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/SceneComponent.h"
#include "Components/SplineComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "TimerManager.h"
#include "Kismet/KismetSystemLibrary.h"

DEFINE_LOG_CATEGORY_STATIC(LogHexBridges, Log, All);


// =============================================================================
// Helpers
// =============================================================================

namespace
{
	// The traces run this far below the walkable surface. That keeps them inside the thickness of
	// the pillars instead of skimming the top faces, which are coplanar with every edge's rim.
	constexpr float BridgeTraceDepth = 5.f;

	// A trace starts this far outside its own tile so it can't begin inside the source collision...
	constexpr float BridgeTraceStartOffset = 5.f;

	// ...and ends this far inside the target tile so it is guaranteed to register a hit on it.
	constexpr float BridgeTraceOvershoot = 10.f;


	/** One open side of an edge tile, in world space. */
	struct FBridgeEdge
	{
		/** Middle of the open side, at walking-surface height. */
		FVector Mid = FVector::ZeroVector;

		/** Horizontal, unit length, points away from the platform. */
		FVector Normal = FVector::ForwardVector;

		/** Platform up axis. */
		FVector Up = FVector::UpVector;
	};


	/** A platform together with all of its open sides. */
	struct FBridgePlatform
	{
		const AMyHexPlatform* Platform = nullptr;
		FVector Center = FVector::ZeroVector;
		float HexRadius = 0.f;
		float SearchRadius = 0.f;
		TArray<FBridgeEdge> Edges;
	};
}


// =============================================================================
// Constructor
// =============================================================================

AMyHexBridgeBuilder::AMyHexBridgeBuilder()
{
	PrimaryActorTick.bCanEverTick = false;

	SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("Root")));
}


// =============================================================================
// BeginPlay
// =============================================================================

void AMyHexBridgeBuilder::BeginPlay()
{
	Super::BeginPlay();

	if (bBuildOnBeginPlay)
	{
		GetWorldTimerManager().SetTimer(
			BuildTimerHandle,
			this,
			&ThisClass::BuildBridges,
			FMath::Max(BuildDelay, 0.01f),
			false
		);
	}
}


// =============================================================================
// Build Bridges
// =============================================================================

void AMyHexBridgeBuilder::BuildBridges()
{
	ClearBridges();

	UWorld* World = GetWorld();

	if (!World)
	{
		return;
	}

	const double StartTime = FPlatformTime::Seconds();


	// -------------------------------------------------------------------------
	// Reads the open sides of one platform
	// -------------------------------------------------------------------------

	// This is a lambda rather than a free function on purpose. AMyHexPlatform only befriends
	// AMyHexBridgeBuilder, and friendship covers this class's member functions (and the lambdas
	// inside them) but not free functions, so a free function can't read the protected members.
	const auto GatherEdges = [this](const AMyHexPlatform& Platform, TArray<FBridgeEdge>& OutEdges)
	{
		const UInstancedStaticMeshComponent* ISM = Platform.HexPillarsISM;

		if (!ISM || !ISM->GetStaticMesh())
		{
			return;
		}

		// Top of the pillar mesh in its own space, so the edge sits on the walkable surface
		// whatever the mesh pivot is.
		const FBoxSphereBounds MeshBounds = ISM->GetStaticMesh()->GetBounds();
		const double MeshTopZ = MeshBounds.Origin.Z + MeshBounds.BoxExtent.Z;

		const FTransform& ToWorld = ISM->GetComponentTransform();
		const FVector WorldUp = ToWorld.GetUnitAxis(EAxis::Z);

		// Built from the live HexMap, so the instance indices are valid even after tiles have been
		// removed. The cached EdgeInstances member is NOT updated by RemoveHexInstance(), which
		// swaps the last instance into the removed slot.
		// const TMap<int32, TArray<FIntVector>> LiveEdges = Platform.GetEdgeInstances();
		const TMap<int32, TArray<FIntVector>> Edges = Platform.EdgeInstances;

		for (const TPair<int32, TArray<FIntVector>>& Pair : Edges)
		{
			FTransform TileLocal;

			if (!ISM->GetInstanceTransform(Pair.Key, TileLocal, /*bWorldSpace=*/false))
			{
				continue;
			}

			const FVector TileTop = TileLocal.TransformPosition(FVector(0.0, 0.0, MeshTopZ));

			for (const FIntVector& Missing : Pair.Value)
			{
				// The missing neighbour has no instance, but its centre follows from the hex layout.
				const FVector2D NeighbourXY = Platform.HexToWorld(Missing.X, Missing.Y, Platform.HexRadius);
				const FVector NeighbourTop(NeighbourXY.X, NeighbourXY.Y, TileTop.Z);

				// The shared side sits exactly half way between the two tile centres.
				FBridgeEdge& Edge = OutEdges.AddDefaulted_GetRef();
				Edge.Mid = ToWorld.TransformPosition((TileTop + NeighbourTop) * 0.5);
				Edge.Normal = ToWorld.TransformVectorNoScale((NeighbourTop - TileTop).GetSafeNormal());
				Edge.Up = WorldUp;
			}
		}
	};


	// -------------------------------------------------------------------------
	// 1. Every platform in the world and its open sides
	// -------------------------------------------------------------------------

	TArray<FBridgePlatform> Platforms;

	for (TActorIterator<AMyHexPlatform> It(World); It; ++It)
	{
		FBridgePlatform Data;

		GatherEdges(**It, Data.Edges);

		if (Data.Edges.Num() == 0)
		{
			continue;
		}

		Data.Platform = *It;
		Data.Center = It->GetActorLocation();
		Data.HexRadius = It->HexRadius;
		Data.SearchRadius = NeighborRadiusMultiplier * It->GridSize * It->HexRadius;

		Platforms.Add(MoveTemp(Data));
	}


	// -------------------------------------------------------------------------
	// 2. Trace between the edges of every pair of platforms that are in range
	// -------------------------------------------------------------------------

	FCollisionQueryParams QueryParams(SCENE_QUERY_STAT(HexBridgeTrace), /*bTraceComplex=*/false);

	// Does a line from From's open side reach To's open side without hitting anything else first?
	// The source platform is deliberately NOT ignored, so an edge on the far side of a platform
	// (whose line would pass through its own tiles) is rejected.
	const auto TraceReaches = [&](const FBridgeEdge& From, const FBridgeEdge& To, const FBridgePlatform& Target)
	{
		const FVector Start = From.Mid + From.Normal * BridgeTraceStartOffset - From.Up * BridgeTraceDepth;
		const FVector End = To.Mid - To.Normal * BridgeTraceOvershoot - To.Up * BridgeTraceDepth;
		DrawDebugLine(World, Start, End, FColor::Red, false, 0.f, 0.f, 10.f);

		FHitResult Hit;

		if (!World->LineTraceSingleByChannel(Hit, Start, End, TraceChannel, QueryParams))
		{
			return false;
		}

		// The first thing the line meets must be the target platform, on the target tile's side.
		// Anything else (a third platform, the source platform, or a pillar further along the
		// target's outline) means the two edges can't see each other.
		const FVector Expected = To.Mid - To.Up * BridgeTraceDepth;

		return Hit.GetActor() == Target.Platform
			&& FVector::DistSquared(Hit.ImpactPoint, Expected) <= FMath::Square(Target.HexRadius * 0.6f);
	};

	int32 PairsInRange = 0;
	int32 EdgePairsTraced = 0;

	for (int32 i = 0; i < Platforms.Num(); ++i)
	{
		for (int32 j = i + 1; j < Platforms.Num(); ++j)
		{
			const FBridgePlatform& A = Platforms[i];
			const FBridgePlatform& B = Platforms[j];

			const float Range = FMath::Max(A.SearchRadius, B.SearchRadius);

			if (FVector::DistSquared(A.Center, B.Center) > FMath::Square(Range))
			{
				continue;
			}

			++PairsInRange;

			for (const FBridgeEdge& EdgeA : A.Edges)
			{
				for (const FBridgeEdge& EdgeB : B.Edges)
				{
					const FVector Delta = EdgeB.Mid - EdgeA.Mid;
					const double DistSq = Delta.SizeSquared();

					if (DistSq < KINDA_SMALL_NUMBER
						|| (MaxBridgeLength > 0.f && DistSq > FMath::Square(MaxBridgeLength)))
					{
						continue;
					}

					if (bRequireFacingEdges)
					{
						const FVector Dir = Delta / FMath::Sqrt(DistSq);

						if (FVector::DotProduct(EdgeA.Normal, Dir) <= 0.0
							|| FVector::DotProduct(EdgeB.Normal, -Dir) <= 0.0)
						{
							continue;
						}
					}

					++EdgePairsTraced;

					// Traced both ways, so the two edges really can "hit" one another.
					if (TraceReaches(EdgeA, EdgeB, B) && TraceReaches(EdgeB, EdgeA, A))
					{
						CreateBridgeSpline(EdgeA.Mid, EdgeB.Mid);
					}
				}
			}
		}
	}

	UE_LOG(
		LogHexBridges,
		Log,
		TEXT("%s: %d platforms, %d pairs in range, %d edge pairs traced, %d bridges, %.1f ms"),
		*GetName(),
		Platforms.Num(),
		PairsInRange,
		EdgePairsTraced,
		BridgeSplines.Num(),
		(FPlatformTime::Seconds() - StartTime) * 1000.0
	);
}


// =============================================================================
// Clear Bridges
// =============================================================================

void AMyHexBridgeBuilder::ClearBridges()
{
	for (USplineComponent* Spline : BridgeSplines)
	{
		if (IsValid(Spline))
		{
			Spline->DestroyComponent();
		}
	}

	BridgeSplines.Reset();
}


// =============================================================================
// Create Bridge Spline
// =============================================================================

USplineComponent* AMyHexBridgeBuilder::CreateBridgeSpline(const FVector& From, const FVector& To)
{
	UKismetSystemLibrary::PrintString(this,TEXT("CreateBridgeSpline"));
	USplineComponent* Spline = NewObject<USplineComponent>(this, NAME_None, RF_Transient);

	Spline->SetupAttachment(GetRootComponent());
	Spline->RegisterComponent();

	// Replaces the two default points a new spline starts with. World space, so it doesn't
	// matter where this actor sits.
	Spline->SetSplinePoints({ From, To }, ESplineCoordinateSpace::World);

	BridgeSplines.Add(Spline);

	return Spline;
}
