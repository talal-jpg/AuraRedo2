// Fill out your copyright notice in the Description page of Project Settings.


#include "Actors/MyHexBridgeSubsystem.h"

#include "Actors/MyHexBridge.h"
#include "Actors/MyHexBridgeSettings.h"
#include "Actors/MyHexPlatform.h"
#include "CollisionQueryParams.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "DrawDebugHelpers.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "TimerManager.h"

DEFINE_LOG_CATEGORY_STATIC(LogHexBridgeSubsystem, Log, All);


// Named, not anonymous: Unreal's unity build compiles this file together with MyHexBridgeBuilder.cpp,
// which defines the same names in its own anonymous namespace.
namespace HexBridgeSubsystemTrace
{
	// Same trace layout as AMyHexBridgeBuilder.

	// The traces run this far below the walkable surface, inside the pillars rather than skimming
	// their top faces, which are coplanar with every edge's rim.
	constexpr float BridgeTraceDepth = 5.f;

	// A trace starts this far outside its own tile so it can't begin inside the source collision...
	constexpr float BridgeTraceStartOffset = 5.f;

	// ...and ends this far inside the target tile so it is guaranteed to hit it.
	constexpr float BridgeTraceOvershoot = 10.f;
}


// =============================================================================
// Lifetime
// =============================================================================

bool UMyHexBridgeSubsystem::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

void UMyHexBridgeSubsystem::Deinitialize()
{
	if (UWorld* World = GetWorld())
	{
		World->GetTimerManager().ClearTimer(ProcessTimerHandle);
	}

	Platforms.Empty();
	CellToPlatforms.Empty();
	CheckedPairs.Empty();
	PendingPlatforms.Empty();

	Super::Deinitialize();
}


// =============================================================================
// Registration
// =============================================================================

void UMyHexBridgeSubsystem::RegisterPlatform(AMyHexPlatform* Platform)
{
	if (!IsValid(Platform))
	{
		return;
	}

	PendingPlatforms.AddUnique(Platform);

	// One timer per batch: everything PCG spawns in the same frame is bridged together
	FTimerManager& TimerManager = GetWorld()->GetTimerManager();

	if (!TimerManager.IsTimerActive(ProcessTimerHandle))
	{
		TimerManager.SetTimer(
			ProcessTimerHandle,
			this,
			&ThisClass::ProcessPendingPlatforms,
			FMath::Max(GetDefault<UMyHexBridgeSettings>()->BuildDelay, 0.01f),
			false
		);
	}
}

void UMyHexBridgeSubsystem::UnregisterPlatform(AMyHexPlatform* Platform)
{
	PendingPlatforms.Remove(Platform);

	const FPlatformKey Key(Platform);

	if (const FPlatformEntry* Entry = Platforms.Find(Key))
	{
		if (TArray<FPlatformKey>* CellPlatforms = CellToPlatforms.Find(Entry->Cell))
		{
			CellPlatforms->Remove(Key);

			if (CellPlatforms->Num() == 0)
			{
				CellToPlatforms.Remove(Entry->Cell);
			}
		}

		Platforms.Remove(Key);
	}
}


// =============================================================================
// Process a batch of new platforms
// =============================================================================

void UMyHexBridgeSubsystem::ProcessPendingPlatforms()
{
	const UMyHexBridgeSettings& Settings = *GetDefault<UMyHexBridgeSettings>();
	const double StartTime = FPlatformTime::Seconds();

	TArray<AMyHexPlatform*> NewPlatforms;


	// -------------------------------------------------------------------------
	// 1. Add the new platforms to the spatial grid, with their edges stored by coordinate.
	//    Nothing has collapsed yet, so the cached EdgeInstances indices are still valid here.
	// -------------------------------------------------------------------------

	for (const TWeakObjectPtr<AMyHexPlatform>& WeakPlatform : PendingPlatforms)
	{
		AMyHexPlatform* Platform = WeakPlatform.Get();

		if (!IsValid(Platform) || Platforms.Contains(FPlatformKey(Platform)))
		{
			continue;
		}

		FPlatformEntry Entry;
		Entry.Platform = Platform;
		Entry.Cell = GetCell(Platform->GetActorLocation(), Settings.SpatialCellSize);
		Entry.SearchRadius = Settings.NeighborRadiusMultiplier * Platform->GridSize * Platform->HexRadius;

		for (const TPair<int32, TArray<FIntVector>>& Pair : Platform->EdgeInstances)
		{
			const FIntVector* Tile = Platform->InstanceToHex.Find(Pair.Key);

			if (!Tile)
			{
				continue;
			}

			for (const FIntVector& Missing : Pair.Value)
			{
				Entry.EdgeTiles.Add({ *Tile, Missing });
			}
		}

		MaxSearchRadius = FMath::Max(MaxSearchRadius, Entry.SearchRadius);

		CellToPlatforms.FindOrAdd(Entry.Cell).Add(FPlatformKey(Platform));
		Platforms.Add(FPlatformKey(Platform), MoveTemp(Entry));

		NewPlatforms.Add(Platform);
	}

	PendingPlatforms.Reset();


	// -------------------------------------------------------------------------
	// 2. Bridge each new platform to the platforms in nearby cells
	// -------------------------------------------------------------------------

	const int32 CellReach = FMath::CeilToInt(MaxSearchRadius / Settings.SpatialCellSize);
	const int32 CheckedPairsBefore = CheckedPairs.Num();

	for (AMyHexPlatform* Platform : NewPlatforms)
	{
		// Copy: TryBridgePlatforms spawns actors, and nothing may hold a pointer into the map meanwhile
		const FPlatformEntry Entry = Platforms.FindChecked(FPlatformKey(Platform));

		for (int32 X = -CellReach; X <= CellReach; ++X)
		{
			for (int32 Y = -CellReach; Y <= CellReach; ++Y)
			{
				const TArray<FPlatformKey>* CellPlatforms = CellToPlatforms.Find(Entry.Cell + FIntPoint(X, Y));

				if (!CellPlatforms)
				{
					continue;
				}

				// Copy for the same reason as above
				const TArray<FPlatformKey> Others = *CellPlatforms;

				for (const FPlatformKey& OtherKey : Others)
				{
					AMyHexPlatform* Other = OtherKey.ResolveObjectPtr();

					if (!IsValid(Other) || Other == Platform)
					{
						continue;
					}

					// Each pair is checked once, whether or not it ends up with a bridge
					bool bAlreadyChecked = false;
					CheckedPairs.Add(MakePairKey(Platform, Other), &bAlreadyChecked);

					if (bAlreadyChecked)
					{
						continue;
					}

					const FPlatformEntry OtherEntry = Platforms.FindChecked(OtherKey);
					TryBridgePlatforms(Entry, OtherEntry, Settings);
				}
			}
		}
	}


	// -------------------------------------------------------------------------
	// 3. Bridges are built, the new platforms may start collapsing
	// -------------------------------------------------------------------------

	for (AMyHexPlatform* Platform : NewPlatforms)
	{
		if (IsValid(Platform))
		{
			Platform->StartCollapsing();
		}
	}

	UE_LOG(
		LogHexBridgeSubsystem,
		Log,
		TEXT("Bridged %d new platforms (%d total), %d pairs checked, %.1f ms"),
		NewPlatforms.Num(),
		Platforms.Num(),
		CheckedPairs.Num() - CheckedPairsBefore,
		(FPlatformTime::Seconds() - StartTime) * 1000.0
	);
}


// =============================================================================
// Bridge one platform pair
// =============================================================================

void UMyHexBridgeSubsystem::TryBridgePlatforms(const FPlatformEntry& A, const FPlatformEntry& B, const UMyHexBridgeSettings& Settings)
{
	const AMyHexPlatform* PlatformA = A.Platform.Get();
	const AMyHexPlatform* PlatformB = B.Platform.Get();

	if (!PlatformA || !PlatformB)
	{
		return;
	}

	const FVector CenterA = PlatformA->GetActorLocation();
	const FVector CenterB = PlatformB->GetActorLocation();

	const float Range = FMath::Max(A.SearchRadius, B.SearchRadius);

	if (FVector::DistSquared2D(CenterA, CenterB) > FMath::Square(Range))
	{
		return;
	}


	// -------------------------------------------------------------------------
	// A few candidate edges per side instead of every edge
	// -------------------------------------------------------------------------

	TArray<FEdgeWorld> EdgesA;
	TArray<FEdgeWorld> EdgesB;

	GatherCandidateEdges(A, CenterB, Settings, EdgesA);
	GatherCandidateEdges(B, CenterA, Settings, EdgesB);

	if (EdgesA.Num() == 0 || EdgesB.Num() == 0)
	{
		return;
	}


	// -------------------------------------------------------------------------
	// Shortest edge pairs first; the first one that passes every check gets the bridge
	// -------------------------------------------------------------------------

	struct FEdgePair
	{
		int32 IndexA;
		int32 IndexB;
		double DistSq;
	};

	TArray<FEdgePair> EdgePairs;
	EdgePairs.Reserve(EdgesA.Num() * EdgesB.Num());

	for (int32 IndexA = 0; IndexA < EdgesA.Num(); ++IndexA)
	{
		for (int32 IndexB = 0; IndexB < EdgesB.Num(); ++IndexB)
		{
			EdgePairs.Add({ IndexA, IndexB, FVector::DistSquared(EdgesA[IndexA].Mid, EdgesB[IndexB].Mid) });
		}
	}

	EdgePairs.Sort([](const FEdgePair& Left, const FEdgePair& Right) { return Left.DistSq < Right.DistSq; });

	const double MaxSlopeSin = FMath::Sin(FMath::DegreesToRadians(Settings.MaxSlopeDegrees));

	for (const FEdgePair& EdgePair : EdgePairs)
	{
		const FEdgeWorld& EdgeA = EdgesA[EdgePair.IndexA];
		const FEdgeWorld& EdgeB = EdgesB[EdgePair.IndexB];

		const FVector Delta = EdgeB.Mid - EdgeA.Mid;
		const double Length = FMath::Sqrt(EdgePair.DistSq);

		if (Length < KINDA_SMALL_NUMBER
			|| (Settings.MaxBridgeLength > 0.f && Length > Settings.MaxBridgeLength))
		{
			continue;
		}

		// Height difference: Z of the straight bridge's unit tangent, i.e. sin(slope angle)
		if (FMath::Abs(Delta.Z) / Length > MaxSlopeSin)
		{
			continue;
		}

		// Both open sides must face each other across the gap
		const FVector FlatDir = FVector(Delta.X, Delta.Y, 0.0).GetSafeNormal();

		if (FVector::DotProduct(EdgeA.Normal, FlatDir) <= 0.0
			|| FVector::DotProduct(EdgeB.Normal, -FlatDir) <= 0.0)
		{
			continue;
		}

		// Traced both ways, so the two edges really can see each other
		if (TraceReaches(EdgeA, EdgeB, *PlatformB, Settings) && TraceReaches(EdgeB, EdgeA, *PlatformA, Settings))
		{
			SpawnBridge(A, EdgeA, B, EdgeB, Settings);
			return;
		}
	}
}


// =============================================================================
// Candidate edges
// =============================================================================

void UMyHexBridgeSubsystem::GatherCandidateEdges(const FPlatformEntry& Entry, const FVector& OtherCenter, const UMyHexBridgeSettings& Settings, TArray<FEdgeWorld>& OutEdges) const
{
	const AMyHexPlatform* Platform = Entry.Platform.Get();

	if (!Platform)
	{
		return;
	}

	for (const FEdgeTile& EdgeTile : Entry.EdgeTiles)
	{
		FEdgeWorld Edge;

		// Skips tiles that have collapsed since the platform registered
		if (!GetEdgeWorld(*Platform, EdgeTile, Edge))
		{
			continue;
		}

		const FVector ToOther = FVector(OtherCenter.X - Edge.Mid.X, OtherCenter.Y - Edge.Mid.Y, 0.0);

		if (FVector::DotProduct(Edge.Normal, ToOther.GetSafeNormal()) < Settings.MinFacingDot)
		{
			continue;
		}

		Edge.Score = ToOther.SizeSquared();
		OutEdges.Add(Edge);
	}

	OutEdges.Sort([](const FEdgeWorld& Left, const FEdgeWorld& Right) { return Left.Score < Right.Score; });

	if (OutEdges.Num() > Settings.CandidateEdgesPerPlatform)
	{
		OutEdges.SetNum(Settings.CandidateEdgesPerPlatform);
	}
}

bool UMyHexBridgeSubsystem::GetEdgeWorld(const AMyHexPlatform& Platform, const FEdgeTile& EdgeTile, FEdgeWorld& OutEdge)
{
	const UInstancedStaticMeshComponent* ISM = Platform.HexPillarsISM;

	if (!ISM || !ISM->GetStaticMesh())
	{
		return false;
	}

	// The tile's current instance index (indices move when other tiles collapse)
	const int32* InstanceIndex = Platform.HexMap.Find(EdgeTile.Tile);

	if (!InstanceIndex)
	{
		return false;
	}

	FTransform TileLocal;

	if (!ISM->GetInstanceTransform(*InstanceIndex, TileLocal, /*bWorldSpace=*/false))
	{
		return false;
	}

	// Top of the pillar mesh, so the edge sits on the walkable surface whatever the mesh pivot is
	const FBoxSphereBounds MeshBounds = ISM->GetStaticMesh()->GetBounds();
	const double MeshTopZ = MeshBounds.Origin.Z + MeshBounds.BoxExtent.Z;

	const FTransform& ToWorld = ISM->GetComponentTransform();
	const FVector TileTop = TileLocal.TransformPosition(FVector(0.0, 0.0, MeshTopZ));

	// The missing neighbour has no instance, but its centre follows from the hex layout
	const FVector2D NeighbourXY = Platform.HexToWorld(EdgeTile.MissingNeighbour.X, EdgeTile.MissingNeighbour.Y, Platform.HexRadius);
	const FVector NeighbourTop(NeighbourXY.X, NeighbourXY.Y, TileTop.Z);

	// The shared side sits exactly half way between the two tile centres
	OutEdge.Tile = EdgeTile.Tile;
	OutEdge.Mid = ToWorld.TransformPosition((TileTop + NeighbourTop) * 0.5);
	OutEdge.Normal = ToWorld.TransformVectorNoScale((NeighbourTop - TileTop).GetSafeNormal());
	OutEdge.Up = ToWorld.GetUnitAxis(EAxis::Z);

	return true;
}


// =============================================================================
// Trace
// =============================================================================

bool UMyHexBridgeSubsystem::TraceReaches(const FEdgeWorld& From, const FEdgeWorld& To, const AMyHexPlatform& Target, const UMyHexBridgeSettings& Settings) const
{
	UWorld* World = GetWorld();

	const FVector Start = From.Mid + From.Normal * HexBridgeSubsystemTrace::BridgeTraceStartOffset - From.Up * HexBridgeSubsystemTrace::BridgeTraceDepth;
	const FVector End = To.Mid - To.Normal * HexBridgeSubsystemTrace::BridgeTraceOvershoot - To.Up * HexBridgeSubsystemTrace::BridgeTraceDepth;

	// The source platform is deliberately NOT ignored, so an edge whose line would pass back
	// through its own tiles is rejected
	const FCollisionQueryParams QueryParams(SCENE_QUERY_STAT(HexBridgeSubsystemTrace), /*bTraceComplex=*/false);

	FHitResult Hit;
	bool bReaches = false;

	if (World->LineTraceSingleByChannel(Hit, Start, End, Settings.TraceChannel, QueryParams))
	{
		// The first thing the line meets must be the target platform, at the target tile's side.
		// Anything else (a third platform, the source platform, another part of the target's
		// outline) means the two edges can't see each other.
		const FVector Expected = To.Mid - To.Up * HexBridgeSubsystemTrace::BridgeTraceDepth;

		bReaches = Hit.GetActor() == &Target
			&& FVector::DistSquared(Hit.ImpactPoint, Expected) <= FMath::Square(Target.HexRadius * 0.6f);
	}

	if (Settings.bDrawDebug)
	{
		DrawDebugLine(World, Start, End, bReaches ? FColor::Green : FColor::Red, false, 10.f, 0, 4.f);
	}

	return bReaches;
}


// =============================================================================
// Spawn
// =============================================================================

void UMyHexBridgeSubsystem::SpawnBridge(const FPlatformEntry& A, const FEdgeWorld& EdgeA, const FPlatformEntry& B, const FEdgeWorld& EdgeB, const UMyHexBridgeSettings& Settings)
{
	UClass* BridgeClass = Settings.BridgeClass.LoadSynchronous();

	if (!BridgeClass)
	{
		BridgeClass = AMyHexBridge::StaticClass();
	}

	const FTransform SpawnTransform(EdgeA.Mid);

	AMyHexBridge* Bridge = GetWorld()->SpawnActorDeferred<AMyHexBridge>(
		BridgeClass,
		SpawnTransform,
		nullptr,
		nullptr,
		ESpawnActorCollisionHandlingMethod::AlwaysSpawn
	);

	if (!Bridge)
	{
		return;
	}

	FMyHexBridgeEnd Start;
	Start.Platform = A.Platform.Get();
	Start.Tile = EdgeA.Tile;
	Start.Location = EdgeA.Mid;

	FMyHexBridgeEnd End;
	End.Platform = B.Platform.Get();
	End.Tile = EdgeB.Tile;
	End.Location = EdgeB.Mid;

	// Set before FinishSpawning so BeginPlay already has the spline points
	Bridge->InitBridge(Start, End);
	Bridge->FinishSpawning(SpawnTransform);
}


// =============================================================================
// Helpers
// =============================================================================

FIntPoint UMyHexBridgeSubsystem::GetCell(const FVector& Location, float CellSize) const
{
	return FIntPoint(
		FMath::FloorToInt(Location.X / CellSize),
		FMath::FloorToInt(Location.Y / CellSize)
	);
}

TPair<UMyHexBridgeSubsystem::FPlatformKey, UMyHexBridgeSubsystem::FPlatformKey> UMyHexBridgeSubsystem::MakePairKey(const AMyHexPlatform* A, const AMyHexPlatform* B)
{
	// Same key whichever platform comes first
	if (A > B)
	{
		Swap(A, B);
	}

	return TPair<FPlatformKey, FPlatformKey>(FPlatformKey(A), FPlatformKey(B));
}
