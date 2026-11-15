// Fill out your copyright notice in the Description page of Project Settings.


#include "Actors/MyHexPlatform.h"

#include <string>

#include "Actors/MyHexAtmosphereFX.h"
#include "Actors/MyHexBridge.h"
#include "Actors/MyHexBridgeSubsystem.h"
#include "Actors/MyHexMinimapSubsystem.h"
#include "Actors/MyHexPathSpawner.h"
#include "MyGameState.h"
#include "Animation/AnimSequence.h"
#include "Algo/BinarySearch.h"
#include "Curves/CurveFloat.h"
#include "CollisionQueryParams.h"
#include "Components/SplineComponent.h"
#include "DrawDebugHelpers.h"
#include "HAL/IConsoleManager.h"
#include "Math/InterpCurve.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "Camera/PlayerCameraManager.h"
#include "EngineUtils.h"
#include "TimerManager.h"
#include "Kismet/KismetMathLibrary.h"
#include "Kismet/KismetSystemLibrary.h"
#include "Net/UnrealNetwork.h"
#include "PCGComponent.h"
#include "PCGGraph.h"
#include "PCGManagedResource.h"
#include "Engine/StaticMesh.h"
#include "GeometryCollection/GeometryCollectionActor.h"
#include "GeometryCollection/GeometryCollectionComponent.h"
#include "GeometryCollection/GeometryCollectionObject.h"
#include "GeometryCollection/GeometryCollectionSimulationTypes.h"
#include "UObject/ConstructorHelpers.h"


// =============================================================================
// Constructor
// =============================================================================

AMyHexPlatform::AMyHexPlatform()
{
	PrimaryActorTick.bCanEverTick = false;

	bReplicates = true;

	// The server spawns platforms far ahead of the players (the path extends hundreds of metres
	// ahead). With the default 150 m net cull distance clients only had the platforms near them,
	// and lost and re-received them as they moved. Every machine keeps the same set instead.
	bAlwaysRelevant = true;

	// -------------------------------------------------------------------------
	// ISM
	// -------------------------------------------------------------------------

	HexPillarsISM = CreateDefaultSubobject<UInstancedStaticMeshComponent>(
		TEXT("HexPillarsISM")
	);
	HexPillarsISM->SetRemoveSwap();
	
	HexPillarsISM->NumCustomDataFloats=5;

	SetRootComponent(HexPillarsISM);

	HexPillarsISM->SetCollisionEnabled(
		ECollisionEnabled::QueryAndPhysics
	);

	HexPillarsISM->SetCollisionResponseToAllChannels(
		ECR_Block
	);

	// M_Pillar2's WPO is a static displacement (no Time node, custom data fixed after spawn). Writing
	// velocity for it kept every pillar in the velocity pass each frame (9.8 ms GPU on 2026-10-24).
	HexPillarsISM->bWorldPositionOffsetWritesVelocity = false;

	// Tile mesh of the bottom platforms (bIsBottomPlatform)
	static ConstructorHelpers::FObjectFinder<UStaticMesh> BottomMesh(
		TEXT("/Game/Assets/MyPlatform/geo/SM/HexPillarBottom.HexPillarBottom")
	);

	if (BottomMesh.Succeeded())
	{
		HexPillarBottomStaticMesh = BottomMesh.Object;
	}

	// The top pillar Geometry Collections (TopPillarHeightVariants) are set on BP_MyHexPlatform, not loaded
	// here: a load from this constructor comes before the Dataflow node types are registered, and the GCs'
	// embedded Dataflow graphs then lose their nodes.

	// -------------------------------------------------------------------------
	// Tile props
	// -------------------------------------------------------------------------

	// Every machine generates its own props after building its grid, so nothing is replicated
	TilePropsPCG = CreateDefaultSubobject<UPCGComponent>(TEXT("TilePropsPCG"));
	TilePropsPCG->GenerationTrigger = EPCGComponentGenerationTrigger::GenerateOnDemand;
	TilePropsPCG->SetIsReplicated(false);

	HexTileProps2 = CreateDefaultSubobject<UPCGComponent>(TEXT("HexTileProps2"));
	HexTileProps2->GenerationTrigger = EPCGComponentGenerationTrigger::GenerateOnDemand;
	HexTileProps2->SetIsReplicated(false);

	// The graph comes from the path spawner's active atmosphere variant
	AtmospherePCG = CreateDefaultSubobject<UPCGComponent>(TEXT("AtmospherePCG"));
	AtmospherePCG->GenerationTrigger = EPCGComponentGenerationTrigger::GenerateOnDemand;
	AtmospherePCG->SetIsReplicated(false);

	// -------------------------------------------------------------------------
	// Path paving
	// -------------------------------------------------------------------------

	// Three 4 x 4 copies after the stone path reference: one big 2x2 stone each, long 2x1 / 1x2
	// stones and small fillers. {cell along, cell across, cells along, cells across}
	static const int32 DefaultPatterns[3][9][4] =
	{
		{ {0, 0, 2, 2}, {2, 0, 2, 1}, {2, 1, 1, 1}, {3, 1, 1, 2}, {2, 2, 1, 1}, {0, 2, 1, 1}, {0, 3, 1, 1}, {1, 2, 1, 2}, {2, 3, 2, 1} },
		{ {0, 0, 2, 1}, {0, 1, 1, 2}, {1, 1, 1, 1}, {1, 2, 1, 1}, {0, 3, 2, 1}, {2, 0, 1, 1}, {3, 0, 1, 2}, {2, 1, 1, 1}, {2, 2, 2, 2} },
		{ {0, 0, 2, 1}, {0, 1, 2, 2}, {0, 3, 2, 1}, {2, 0, 2, 2}, {2, 2, 2, 1}, {2, 3, 1, 1}, {3, 3, 1, 1}, {0, 0, 0, 0}, {0, 0, 0, 0} },
	};

	for (const auto& Pattern : DefaultPatterns)
	{
		FHexPavingPattern& NewPattern = PavingPatterns.AddDefaulted_GetRef();

		for (const auto& Slab : Pattern)
		{
			if (Slab[2] > 0 && Slab[3] > 0)
			{
				FHexPavingPatternSlab& NewSlab = NewPattern.Slabs.AddDefaulted_GetRef();
				NewSlab.Cell = FIntPoint(Slab[0], Slab[1]);
				NewSlab.Size = FIntPoint(Slab[2], Slab[3]);
			}
		}
	}
}


// =============================================================================
// Replication
// =============================================================================

void AMyHexPlatform::GetLifetimeReplicatedProps(
	TArray<FLifetimeProperty>& OutLifetimeProps
) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);

	DOREPLIFETIME(
		AMyHexPlatform,
		ActivatedTiles
	);

	DOREPLIFETIME(AMyHexPlatform, PathStartTiles);
	DOREPLIFETIME(AMyHexPlatform, PathStartSides);
	DOREPLIFETIME(AMyHexPlatform, bPathFrozen);

	// Grid shape. Set once when the server spawns the platform (PCG property overrides) and never
	// changed, so it only goes in the first bunch. The engine applies it before the client's
	// BeginPlay, which is where the client builds its grid.
	DOREPLIFETIME_CONDITION(AMyHexPlatform, HexPillarStaticMesh, COND_InitialOnly);
	DOREPLIFETIME_CONDITION(AMyHexPlatform, bIsBottomPlatform, COND_InitialOnly);
	DOREPLIFETIME_CONDITION(AMyHexPlatform, HexPillarBottomStaticMesh, COND_InitialOnly);
	DOREPLIFETIME_CONDITION(AMyHexPlatform, HexPillarBottomScaleZ, COND_InitialOnly);
	DOREPLIFETIME_CONDITION(AMyHexPlatform, GridSize, COND_InitialOnly);
	DOREPLIFETIME_CONDITION(AMyHexPlatform, HexRadius, COND_InitialOnly);
	DOREPLIFETIME_CONDITION(AMyHexPlatform, VerticalScaling, COND_InitialOnly);
	DOREPLIFETIME_CONDITION(AMyHexPlatform, NoiseOffset, COND_InitialOnly);
	DOREPLIFETIME_CONDITION(AMyHexPlatform, NoiseFrequency, COND_InitialOnly);
	DOREPLIFETIME_CONDITION(AMyHexPlatform, NoiseStrength, COND_InitialOnly);
	DOREPLIFETIME_CONDITION(AMyHexPlatform, DetailStrength, COND_InitialOnly);
	DOREPLIFETIME_CONDITION(AMyHexPlatform, NoiseCurve, COND_InitialOnly);
	DOREPLIFETIME_CONDITION(AMyHexPlatform, DeletionThreshold, COND_InitialOnly);
	DOREPLIFETIME_CONDITION(AMyHexPlatform, SplineDistance, COND_InitialOnly);
}


// =============================================================================
// BeginPlay
// =============================================================================

void AMyHexPlatform::BeginPlay()
{
	Super::BeginPlay();

	// The grid itself is NOT replicated, every machine builds it here.
	//
	// OnConstruction() doesn't build it in game worlds: on a client it would run with the class
	// defaults, before the replicated shape (GridSize, NoiseOffset, ... set by PCG on the server)
	// arrived. That is applied before BeginPlay, so this build matches the server's grid.
	//
	// Only the shape and the activation state are replicated.
	
	BuildHexGrid();

	// The platform vanishes past this (hidden by the path-end fog)
	if (PlatformMaxDrawDistance > 0.f)
	{
		HexPillarsISM->SetCullDistance(PlatformMaxDrawDistance);
	}

	// Tiles that collapsed before this client received the platform (late join) came with the
	// initial properties; OnRep_ActivatedTiles skipped them because the grid wasn't built yet.
	// They fell long ago on the server, so remove them without replaying the fall.
	if (!HasAuthority())
	{
		ApplyActivatedTiles(/*bPlayEffect=*/false);
	}

	// Top tiles break into Geometry Collections: get their shaders compiling before the first break.
	// The variants share their material, so one of them covers the rest.
	if (!bIsBottomPlatform)
	{
		if (UMyHexPillarBreakSubsystem* PillarBreaks = GetWorld()->GetSubsystem<UMyHexPillarBreakSubsystem>())
		{
			PillarBreaks->PrecacheCollection(this, TopPillarGeometryCollection);

			if (!TopPillarHeightVariants.IsEmpty())
			{
				PillarBreaks->PrecacheCollection(this, TopPillarHeightVariants[0].Collection);
			}
		}
	}

	// The far-break ISMs are made now, empty, so their PSOs compile before the first far break: in a
	// cooked build a primitive gets no scene proxy until its PSOs are ready (pops in late otherwise)
	if (GetNetMode() != NM_DedicatedServer)
	{
		if (UMyHexPillarBreakSubsystem* Breaks = GetWorld()->GetSubsystem<UMyHexPillarBreakSubsystem>())
		{
			Breaks->PrewarmFarBreak(FarTopPillar);
			Breaks->PrewarmFarBreak(FarBottomPillar);

			for (const TPair<TObjectPtr<UStaticMesh>, FHexFarBreakMesh>& Pair : FarPropMeshes)
			{
				Breaks->PrewarmFarBreak(Pair.Value);
			}
		}
	}

	// Rocks and ruins on the tiles left after the late-join removal above. Their props break with them.
	// Generated a little later, once the bridges (and the path from them) are usually known.
	OnHexTileActivated.AddUObject(this, &ThisClass::HandleTileActivated);
	ScheduleTileProps(PropsBridgeWait);

	// Draws the live tiles on the minimap and follows their collapse (not on a dedicated server)
	if (UMyHexMinimapSubsystem* Minimap = GetWorld()->GetSubsystem<UMyHexMinimapSubsystem>())
	{
		Minimap->RegisterPlatform(this);
	}
	UE_LOG(
		LogTemp,
		Verbose,
		TEXT("%s BeginPlay: HexMap=%d | ISM=%d"),
		*GetName(),
		HexMap.Num(),
		HexPillarsISM->GetInstanceCount()
	);

	//TODO Can choose a grid randomly based on Grid size ( the larger the size the greater the chance is to get selected for destruction)
	// grids with a size of certain threshold get destroyed completely
	
	if (HasAuthority())
	{
		// Measured from the full grid, before any tile collapses
		FootprintRadius = ComputeFootprintRadius();

		// The bridge subsystem builds this platform's bridges from its untouched edges, then calls
		// NotifyBridgesReady(). Collapsing waits for that and for the lead player to land.
		UMyHexBridgeSubsystem* BridgeSubsystem = GetWorld()->GetSubsystem<UMyHexBridgeSubsystem>();

		if (BridgeSubsystem)
		{
			BridgeSubsystem->RegisterPlatform(this);
		}

		if (!BridgeSubsystem || !bWaitForBridgesBeforeCollapsing)
		{
			NotifyBridgesReady();
		}

		if (bCollapseOnlyWhenLeadLands || bAutoDestroyWhenLeftBehind)
		{
			const float Interval = FMath::Max(LeadCheckInterval, 0.02f);

			GetWorldTimerManager().SetTimer(
				LeadCheckTimerHandle,
				this,
				&ThisClass::UpdateLeadState,
				Interval,
				true,
				FMath::FRandRange(0.01f, Interval)
			);
		}
	}
}


// =============================================================================
// EndPlay
// =============================================================================

void AMyHexPlatform::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	if (UWorld* World = GetWorld())
	{
		// Lead check, collapse chain, per-tile and pillar timers. AActor::EndPlay doesn't clear them.
		World->GetTimerManager().ClearAllTimersForObject(this);

		if (UMyHexBridgeSubsystem* BridgeSubsystem = World->GetSubsystem<UMyHexBridgeSubsystem>())
		{
			BridgeSubsystem->UnregisterPlatform(this);
		}

		if (UMyHexMinimapSubsystem* Minimap = World->GetSubsystem<UMyHexMinimapSubsystem>())
		{
			Minimap->UnregisterPlatform(this);
		}
	}

	// Fog, snow and dust the tile prop graph spawned (PCG leaves them behind)
	AMyHexAtmosphereFX::DestroyAttachedTo(this);

	// Broadcasts OnEndPlay, which makes the bridges ending on this platform destroy themselves
	Super::EndPlay(EndPlayReason);
}


// =============================================================================
// Start Collapsing
// =============================================================================

void AMyHexPlatform::StartCollapsing()
{
	if (!HasAuthority() || bCollapseStarted)
	{
		return;
	}

	bCollapseStarted = true;
	FreezePath();

	// ---------------------------------------------------------------------
	// Start chain activation timer
	// ---------------------------------------------------------------------

	// A small platform goes in one chain (GenerateAndActivateChainFromRandomSelectedGrid takes every
	// tile when ChainLength or fewer are left), so it waits longer before that
	const float FirstDelay = HexMap.Num() <= SmallPlatformMaxTiles ? SmallPlatformFirstCollapseDelay : FirstCollapseDelay;

	ScheduleNextCollapseChain(FirstDelay);
}

void AMyHexPlatform::ScheduleNextCollapseChain(float Delay)
{
	GetWorldTimerManager().SetTimer(
		CollapseTimerHandle,
		this,
		&ThisClass::CollapseNextChain,
		FMath::Max(Delay, 0.01f), // a rate <= 0 would clear the timer instead
		false
	);
}

void AMyHexPlatform::CollapseNextChain()
{
	GenerateAndActivateChainFromRandomSelectedGrid();

	// Stop once every tile is gone. Tiles of the last chains are removed over the next second or so,
	// so it keeps ticking (and finding nothing to reserve) until then.
	if (HexMap.Num() > 0)
	{
		ScheduleNextCollapseChain(GetCollapseInterval());
	}
}

float AMyHexPlatform::GetCollapseInterval() const
{
	const AMyGameState* MyGameState = GetWorld()->GetGameState<AMyGameState>();
	const float LeadDistance = MyGameState ? MyGameState->GetLeadSplineDistance() : -1.f;

	// Nothing to measure against
	if (!HasSplineDistance() || LeadDistance < 0.f)
	{
		return CollapseIntervalAtLead;
	}

	// SplineDistance grows with HexRadius (PCG works in radius-100 layout space and scales it up)
	const float FalloffDistance = FMath::Max(CollapseFalloffDistance * HexRadius / 100.f, 1.f);

	// Ahead of the lead (activated before the old leader left) counts as at the lead
	const float Behind = FMath::Max(LeadDistance - SplineDistance, 0.f);

	return FMath::Lerp(CollapseIntervalAtLead, CollapseIntervalFarBehind, FMath::Min(Behind / FalloffDistance, 1.f));
}


// =============================================================================
// Collapse gate (server)
// =============================================================================

void AMyHexPlatform::NotifyBridgesReady()
{
	if (!HasAuthority() || bBridgesReady)
	{
		return;
	}

	bBridgesReady = true;
	TryStartCollapsing();
}

void AMyHexPlatform::NotifyLeadLanded()
{
	if (!HasAuthority() || bLeadLanded)
	{
		return;
	}

	bLeadLanded = true;
	FreezePath();
	TryStartCollapsing();
}

void AMyHexPlatform::TryStartCollapsing()
{
	// Spawned (or given its SplineDistance) after the lead already got this far along the path
	if (!bLeadLanded && HasSplineDistance())
	{
		const AMyGameState* MyGameState = GetWorld()->GetGameState<AMyGameState>();

		if (MyGameState && SplineDistance <= MyGameState->GetActivatedSplineDistance())
		{
			bLeadLanded = true;
		}
	}

	// Bridges first (they are built from the untouched edges), then the lead player
	if (bBridgesReady && (bLeadLanded || !bCollapseOnlyWhenLeadLands))
	{
		StartCollapsing();
	}
}


// =============================================================================
// Lead player and culling (server)
// =============================================================================

void AMyHexPlatform::UpdateLeadState()
{
	UMyHexBridgeSubsystem* Subsystem = GetWorld()->GetSubsystem<UMyHexBridgeSubsystem>();
	APawn* Lead = Subsystem ? Subsystem->GetLeadPawn() : nullptr;

	// No lead (not spawned yet, dead, respawning): nothing lands and nothing is culled
	if (!IsValid(Lead))
	{
		return;
	}

	const double Gap = FMath::Max(0.0, FVector::Dist2D(Lead->GetActorLocation(), GetActorLocation()) - FootprintRadius);
	const bool bLeadOn = IsPawnOnPlatform(Lead, Gap);

	if (bLeadOn || Gap <= 0.0)
	{
		bLeadReached = true;
	}

	// Platforms with a SplineDistance are activated by AMyGameState when the lead's distance passes
	// theirs. One the PCG graph gave no distance falls back to the lead standing on it.
	if (bLeadOn && !HasSplineDistance())
	{
		NotifyLeadLanded();
	}

	if (bAutoDestroyWhenLeftBehind
		&& !bLeadOn
		&& IsLeftBehind(*Subsystem, Gap)
		&& !(bKeepWhileAnyPlayerIsOnIt && IsAnyPlayerOnPlatform())
		&& Subsystem->TryConsumeCullBudget())
	{
		// Server only; destruction replicates. EndPlay clears timers and unregisters, and the
		// bridges ending here destroy themselves.
		Destroy();
		return;
	}

	// Nothing left to watch for
	if (!bAutoDestroyWhenLeftBehind && (bCollapseStarted || !bCollapseOnlyWhenLeadLands || HasSplineDistance()))
	{
		GetWorldTimerManager().ClearTimer(LeadCheckTimerHandle);
	}
}

bool AMyHexPlatform::IsPawnOnPlatform(const APawn* Pawn, double Gap) const
{
	// Standing on the ISM, or on a collapsing pillar (both owned by this actor). A bridge resolves
	// to AMyHexBridge, so standing on a bridge doesn't count.
	if (APawn::GetMovementBaseActor(Pawn) == this)
	{
		return true;
	}

	// Not over this platform at all
	if (Gap > 0.0)
	{
		return false;
	}

	// Walking on something else (a bridge, another platform)
	const ACharacter* Character = Cast<ACharacter>(Pawn);
	const UCharacterMovementComponent* Movement = Character ? Character->GetCharacterMovement() : nullptr;

	if (Movement && Movement->IsMovingOnGround())
	{
		return false;
	}

	if (LandingTolerance <= 0.f)
	{
		return false;
	}

	// Airborne (jumping between checks) or not a Character: counts if this platform is just below
	const FVector Start = Pawn->GetActorLocation();
	const FVector End = Start - FVector(0.0, 0.0, Pawn->GetSimpleCollisionHalfHeight() + LandingTolerance);

	FCollisionQueryParams Params(SCENE_QUERY_STAT(HexPlatformLeadTrace), false, Pawn);
	FHitResult Hit;

	return GetWorld()->LineTraceSingleByChannel(Hit, Start, End, ECC_Visibility, Params)
		&& Hit.GetActor() == this;
}

bool AMyHexPlatform::IsLeftBehind(const UMyHexBridgeSubsystem& Subsystem, double Gap)
{
	// Never anything physically near the lead
	if (Gap <= CullBehindDistance)
	{
		return false;
	}

	const USplineComponent* Spline = Subsystem.GetPathSpline();

	// No path in this level: only once the lead has been here and moved away
	if (!Spline)
	{
		return bLeadReached;
	}

	ResolvePathDistance(*Spline);

	// Still at the growing end of the path: wait until the path has moved past it
	if (!bPathResolved)
	{
		return false;
	}

	// Too far from the path to measure along it
	if (!bOnPath)
	{
		return bLeadReached;
	}

	// Measured along the path, so platforms ahead of the lead are never culled
	float LeadDistance = 0.f;
	return Subsystem.GetLeadPathDistance(LeadDistance)
		&& PathFrontDistance < LeadDistance - CullBehindDistance;
}

void AMyHexPlatform::ResolvePathDistance(const USplineComponent& Spline)
{
	if (&Spline != ResolvedPathSpline.Get())
	{
		ResolvedPathSpline = &Spline;
		bPathResolved = false;
		bOnPath = false;
	}

	if (bPathResolved)
	{
		return;
	}

	const int32 NumPoints = Spline.GetNumberOfSplinePoints();

	if (NumPoints < 2)
	{
		return;
	}

	const FVector Center = GetActorLocation();
	const float Key = Spline.FindInputKeyClosestToWorldLocation(Center);

	// At or past the current end: the distance isn't final yet, retry after the path grows
	if (Key >= NumPoints - 1 - KINDA_SMALL_NUMBER)
	{
		return;
	}

	bPathResolved = true;
	bOnPath = FVector::Dist2D(Spline.GetLocationAtSplineInputKey(Key, ESplineCoordinateSpace::World), Center) <= MaxPathOffset * HexRadius / 100.f;

	// Position of the platform's far edge along the path
	PathFrontDistance = Spline.GetDistanceAlongSplineAtSplineInputKey(Key) + FootprintRadius;
}

bool AMyHexPlatform::IsAnyPlayerOnPlatform() const
{
	for (FConstPlayerControllerIterator It = GetWorld()->GetPlayerControllerIterator(); It; ++It)
	{
		const APlayerController* PlayerController = It->Get();
		const APawn* Pawn = PlayerController ? PlayerController->GetPawn() : nullptr;

		if (!Pawn)
		{
			continue;
		}

		const AActor* Base = APawn::GetMovementBaseActor(Pawn);

		if (Base == this)
		{
			return true;
		}

		// On a bridge that ends on this platform
		if (const AMyHexBridge* Bridge = Cast<AMyHexBridge>(Base))
		{
			const FMyHexBridgeEnds& Ends = Bridge->GetEnds();

			if (Ends.Start.Platform == this || Ends.End.Platform == this)
			{
				return true;
			}
		}

		const FVector PawnLocation(Pawn->GetActorLocation().X, Pawn->GetActorLocation().Y, 0.0);

		// Above it (jumping, falling)
		if (FVector::Dist2D(PawnLocation, GetActorLocation()) <= FootprintRadius)
		{
			return true;
		}

		// Over a bridge that ends here. A jumping or hovering player has no movement base.
		for (const TWeakObjectPtr<AMyHexBridge>& WeakBridge : Bridges)
		{
			const AMyHexBridge* Bridge = WeakBridge.Get();

			if (!Bridge)
			{
				continue;
			}

			const FVector& Start = Bridge->GetEnds().Start.Location;
			const FVector& End = Bridge->GetEnds().End.Location;

			if (FMath::PointDistToSegment(PawnLocation, FVector(Start.X, Start.Y, 0.0), FVector(End.X, End.Y, 0.0)) <= BridgeKeepDistance)
			{
				return true;
			}
		}
	}

	return false;
}

void AMyHexPlatform::RegisterBridge(AMyHexBridge* Bridge)
{
	Bridges.RemoveAll([](const TWeakObjectPtr<AMyHexBridge>& WeakBridge) { return !WeakBridge.IsValid(); });
	Bridges.AddUnique(Bridge);
}

void AMyHexPlatform::UnregisterBridge(AMyHexBridge* Bridge)
{
	Bridges.Remove(Bridge);
}

void AMyHexPlatform::RegisterPathBridge(AMyHexBridge* Bridge)
{
	if (!HasAuthority() || !Bridge)
	{
		return;
	}

	PathBridges.RemoveAll([](const TWeakObjectPtr<AMyHexBridge>& WeakBridge) { return !WeakBridge.IsValid(); });
	PathBridges.AddUnique(Bridge);

	UpdatePathStartTiles();
}

void AMyHexPlatform::UnregisterPathBridge(AMyHexBridge* Bridge)
{
	if (!HasAuthority() || !Bridge || IsActorBeingDestroyed())
	{
		return;
	}

	// Destroyed because one of its end tiles fell: the walkway to it stays, so nothing regenerates
	if (Bridge->HasEndTileCollapsed())
	{
		for (const FMyHexBridgeEnd* End : { &Bridge->GetEnds().Start, &Bridge->GetEnds().End })
		{
			if (End->Platform == this && !RetainedPathStarts.Contains(End->Tile))
			{
				// Keeps the side it already has (another bridge may still leave the same tile), so nothing changes
				const int32 Published = PathStartSides.Num() == PathStartTiles.Num() ? PathStartTiles.IndexOfByKey(End->Tile) : INDEX_NONE;
				RetainedPathStarts.Add(End->Tile, Published != INDEX_NONE ? PathStartSides[Published] : GetPathStartSide(End->Tile, End->Location));
			}
		}
	}

	if (PathBridges.Remove(Bridge) > 0)
	{
		UpdatePathStartTiles();
	}
}

void AMyHexPlatform::UpdatePathStartTiles()
{
	if (!HasAuthority() || bPathFrozen)
	{
		return;
	}

	// The first bridge found on a tile gives its side
	TMap<FIntVector, uint8> StartSides = RetainedPathStarts;
	TArray<FIntVector> Starts;
	RetainedPathStarts.GenerateKeyArray(Starts);

	for (const TWeakObjectPtr<AMyHexBridge>& WeakBridge : PathBridges)
	{
		const AMyHexBridge* Bridge = WeakBridge.Get();

		if (!Bridge)
		{
			continue;
		}

		for (const FMyHexBridgeEnd* End : { &Bridge->GetEnds().Start, &Bridge->GetEnds().End })
		{
			if (End->Platform == this && !StartSides.Contains(End->Tile))
			{
				Starts.Add(End->Tile);
				StartSides.Add(End->Tile, GetPathStartSide(End->Tile, End->Location));
			}
		}
	}

	// Only tiles of the built grid; sorted so every machine walks them in the same order
	Starts.RemoveAll([this](const FIntVector& Tile) { return !PathLayoutTiles.IsEmpty() && !PathLayoutTiles.Contains(Tile); });
	Starts.Sort([this](const FIntVector& A, const FIntVector& B) { return MakeTileIndex(A) < MakeTileIndex(B); });

	TArray<uint8> Sides;
	Sides.Reserve(Starts.Num());

	for (const FIntVector& Tile : Starts)
	{
		Sides.Add(StartSides.FindChecked(Tile));
	}

	if (Starts != PathStartTiles || Sides != PathStartSides)
	{
		PathStartTiles = MoveTemp(Starts);
		PathStartSides = MoveTemp(Sides);

		if (HasActorBegunPlay())
		{
			ScheduleTileProps(PropsRegenerateDelay);
		}
	}
}

uint8 AMyHexPlatform::GetPathStartSide(const FIntVector& Tile, const FVector& WorldLocation) const
{
	// The bridge end sits on the middle of the tile's open side; tiles are laid out in actor space
	const FVector Local = GetActorTransform().InverseTransformPosition(WorldLocation);
	const FVector2D Out = FVector2D(Local.X, Local.Y) - HexToWorld(Tile.X, Tile.Y, HexRadius);

	if (Out.IsNearlyZero())
	{
		return MAX_uint8;
	}

	uint8 BestSide = MAX_uint8;
	double BestDot = -TNumericLimits<double>::Max();

	for (int32 Side = 0; Side < 6; ++Side)
	{
		const double Dot = FVector2D::DotProduct(GetHexSideDirection(Side), Out);

		if (Dot > BestDot)
		{
			BestDot = Dot;
			BestSide = static_cast<uint8>(Side);
		}
	}

	return BestSide;
}

void AMyHexPlatform::OnRep_PathStartTiles()
{
	if (HasActorBegunPlay())
	{
		ScheduleTileProps(PropsRegenerateDelay);
	}
}

void AMyHexPlatform::FreezePath()
{
	if (HasAuthority())
	{
		bPathFrozen = true;
	}
}

bool AMyHexPlatform::AreTilePropsFrozen() const
{
	return bTilePropsGenerated && (bPathFrozen || !LocalActivatedTiles.IsEmpty());
}

float AMyHexPlatform::ComputeFootprintRadius() const
{
	// Tiles are laid out around the actor origin (HexToWorld in local space)
	double MaxRadius = 0.0;

	for (const TPair<FIntVector, int32>& Pair : HexMap)
	{
		MaxRadius = FMath::Max(MaxRadius, static_cast<double>(HexToWorld(Pair.Key.X, Pair.Key.Y, HexRadius).Size()));
	}

	return static_cast<float>((MaxRadius + HexRadius) * GetActorScale3D().GetAbsMax());
}


// =============================================================================
// OnConstruction
// =============================================================================

void AMyHexPlatform::OnConstruction(
	const FTransform& Transform
)
{
	Super::OnConstruction(Transform);

#if WITH_EDITOR
	// A freshly placed platform's PCG graph instances only listen to their graph after a load,
	// duplicate or graph change, so editing the graph (or toggling Debug) wouldn't regenerate it.
	for (UPCGComponent* PropsPCG : { TilePropsPCG.Get(), HexTileProps2.Get() })
	{
		if (PropsPCG && PropsPCG->GetGraphInstance())
		{
			PropsPCG->GetGraphInstance()->SetupCallbacks();
		}
	}
#endif

	// Game worlds build the grid in BeginPlay, once the replicated shape has arrived. Building it here
	// as well doubled the work for every platform the path spawns.
	if (const UWorld* World = GetWorld(); World && World->IsGameWorld())
	{
		return;
	}

	BuildHexGrid();
}


// =============================================================================
// Build Grid
// =============================================================================

// void AMyHexPlatform::BuildHexGrid()
// {
// 	if (!HexPillarsISM)
// 	{
// 		return;
// 	}
//
// 	// -------------------------------------------------------------------------
// 	// Clear old instances
// 	// -------------------------------------------------------------------------
//
// 	HexPillarsISM->ClearInstances();
//
// 	HexMap.Empty();
// 	InstanceToHex.Empty();
//
//
// 	// -------------------------------------------------------------------------
// 	// Set static mesh
// 	// -------------------------------------------------------------------------
//
// 	if (!HexPillarStaticMesh)
// 	{
// 		return;
// 	}
//
// 	HexPillarsISM->SetStaticMesh(
// 		HexPillarStaticMesh
// 	);
//
//
// 	// -------------------------------------------------------------------------
// 	// Generate grid
// 	// -------------------------------------------------------------------------
//
// 	const TArray<FHexCoord> HexCoords = GenerateHexGrid();
//
// 	
// 	for (const FHexCoord& HexCoord : HexCoords)
// 	{
// 		
// 		{}
// 		// calc dist from center
// 		const int32 DistanceFromCenter = FMath::Max3(FMath::Abs(HexCoord.Q),FMath::Abs(HexCoord.R),FMath::Abs(HexCoord.S));
//
// 		// Normalize 0 to1 
// 		const float Distance01 =static_cast<float>(DistanceFromCenter) /static_cast<float>(GridSize);
// 		
// 		const double BOH_NoiseScale = 0.2;
//
// 		float NoiseBOH = FMath::PerlinNoise3D(
// 			FVector3d(
// 				HexCoord.Q * BOH_NoiseScale,
// 				HexCoord.R * BOH_NoiseScale,
// 				HexCoord.S * BOH_NoiseScale
// 			)
// 		);
// 		
// 		NoiseBOH= (NoiseBOH+1.f)* 0.5f;
//
// 		// calc scale 
// 		const float Scale = FMath::Lerp(
// 			GridSize*VerticalScaling* NoiseBOH,   // center
// 			0.4f,   // edge
// 			Distance01
// 		);
// 		
// 		
// 		// calc offset in z due to scale 
// 		float ZOffsetDueToScale= GridSize-Scale;
// 		
// 		// Mult by instanced geo size
// 		ZOffsetDueToScale*= 1000.f;
// 		
// 		const FVector2D Loc2d = HexToWorld(
// 			HexCoord.Q,
// 			HexCoord.R,
// 			HexRadius
// 		);
//
// 		FTransform InstanceTransform;
//
// 		InstanceTransform.SetLocation(
// 			FVector(
// 				Loc2d.X,
// 				Loc2d.Y,
// 				//TODO Add slight randomness to z Loc
// 				0.f
// 			)
// 		);
// 		
// 		float InstanceRadius=HexRadius/100;
// 		InstanceTransform.SetScale3D(
// 			FVector(
// 				InstanceRadius,
// 				InstanceRadius,
// 				Scale
// 			)
// 		);
//
// 		const FIntVector Coord(
// 			HexCoord.Q,
// 			HexCoord.R,
// 			HexCoord.S
// 		);
//
// 			float noise=FMath::PerlinNoise2D((Loc2d*NoiseScale)+NoiseOffset);
// 			
// 			float Dist= NoiseCurve? NoiseCurve->GetFloatValue(Distance01) : Distance01;
// 			// float Dist= NoiseCurve.GetValueAtLevel(Distance01);
// 			noise= FMath::Max(1-Distance01,noise);
// 			
// 			FVector2D InputRange=FVector2D(0,1);
// 			FVector2D OutputRange=FVector2D(0,1);
// 			Dist=FMath::GetMappedRangeValueClamped(InputRange,OutputRange,Dist);
// 			
// 			noise= noise+Dist;
// 		
// 		int32 InstanceIndex=INDEX_NONE;
// 		
// 		if (noise>DeletionThreshold)
// 		{
// 			 InstanceIndex= AddHexInstance(Coord,InstanceTransform);
// 		}
// 		
//
// 		if (InstanceIndex != INDEX_NONE)
// 		{
// 			HexPillarsISM->SetCustomDataValue(InstanceIndex,0,Dist,true);
// 			
// 			HexMap.Add(
// 				Coord,
// 				InstanceIndex
// 			);
//
// 			InstanceToHex.Add(
// 				InstanceIndex,
// 				Coord
// 			);
// 		}
// 	}
// }
// Complete replacement for AMyHexPlatform::BuildHexGrid()
//
// How the outline works
// ---------------------
// Every hex is measured as a fraction of the platform radius (Radius01) and compared with an edge
// radius that depends only on its DIRECTION from the centre (noise sampled on a circle, so it loops
// seamlessly and does not change with GridSize). NoiseCurve turns that relative distance into a
// 0..1 falloff, and hexes at or below DeletionThreshold are not created.
//
//   DeletionThreshold  overall size. 0.5 puts the outline at roughly 3/4 of the platform radius
//                      with the current curve; higher = smaller.
//   NoiseStrength      max distance the edge moves in/out, as a fraction of its radius. Keep it
//                      <= ~0.35 at threshold 0.5, or spikes hit the edge of the grid and get cut flat.
//   NoiseFrequency     number of spikes around the edge (about 3x this value).
//   DetailStrength     finer jaggedness layered on top (0 = smooth lobes only).
//   NoiseOffset        seed. The same offset gives the same silhouette at any GridSize.

void AMyHexPlatform::BuildHexGrid()
{
	if (!HexPillarsISM)
	{
		return;
	}

	// -------------------------------------------------------------------------
	// Clear old instances
	// -------------------------------------------------------------------------

	HexPillarsISM->ClearInstances();
	// 0 falloff, 1/2 tile XY, 3 packed edge word, 4 packed path word (the edge word is packed below
	// with PackHexAngle, the path word in WritePathCustomData).
	// Packed words are integers below 2^24, so they survive the float exactly.
	HexPillarsISM->SetNumCustomDataFloats(5);

	HexMap.Empty();
	InstanceToHex.Empty();


	// -------------------------------------------------------------------------
	// Set static mesh
	// -------------------------------------------------------------------------

	// HexPillarBottom on bottom platforms, HexPillar on top ones
	UStaticMesh* TileMesh = GetTileMesh();

	if (!TileMesh)
	{
		return;
	}

	HexPillarsISM->SetStaticMesh(
		TileMesh
	);


	// -------------------------------------------------------------------------
	// Values that are the same for every hex
	// -------------------------------------------------------------------------

	const TArray<FHexCoord> HexCoords = GenerateHexGrid();

	// Avoids a divide by zero when GridSize is 0
	const int32 SafeGridSize = FMath::Max(1, GridSize);
	const float GridSizeF = static_cast<float>(SafeGridSize);

	// Radius of the largest circle that fits inside the hex-shaped grid (corner distance * cos 30 deg).
	// Radius01 == 1 means "touching the middle of the grid's flat edge", so the outline is always
	// measured against the grid it has to fit in, whatever GridSize is.
	const float PlatformRadius = FMath::Max(
		static_cast<float>(HexToWorld(SafeGridSize, 0, HexRadius).Size()) * 0.8660254f,
		1.e-4f
	);

	// PerlinNoise2D usually stays within about +-0.6, so stretch it. Together with the clamp below
	// this makes NoiseStrength the real maximum edge displacement.
	constexpr float PerlinGain = 2.f;

	// TODO Make tweakable Prop
	constexpr double BOH_NoiseScale = 0.2;

	const float InstanceRadius = HexRadius / 100;

	// Bottom platforms: one Z scale for every tile (no per-tile heights)
	const bool bUniformHeight = bIsBottomPlatform && TileMesh == HexPillarBottomStaticMesh;
	const float UniformScaleZ = InstanceRadius * HexPillarBottomScaleZ;

	// The side (GetHexSideDirection) of a tile that points most directly away from the platform centre.
	// The pillar has flat sides on +-X and only tiles when turned in 60 degree steps, so each pillar is
	// turned to put +X on that side (and -X towards the centre). Cube coordinate dot products are exact
	// integers, so every machine picks the same side, ties included (the lowest side wins).
	// The centre tile has no outward side and stays on side 0, i.e. unturned.
	const auto GetOutwardSide = [](const FIntVector& Coord)
	{
		static const FIntVector Directions[6] =
		{
			FIntVector( 1,  0, -1), FIntVector( 1, -1,  0), FIntVector( 0, -1,  1),
			FIntVector(-1,  0,  1), FIntVector(-1,  1,  0), FIntVector( 0,  1, -1)
		};

		int32 OutwardSide = 0;
		int32 BestDot = 0;

		for (int32 Side = 0; Side < 6; ++Side)
		{
			const FIntVector& D = Directions[Side];
			const int32 Dot = Coord.X * D.X + Coord.Y * D.Y + Coord.Z * D.Z;

			if (Dot > BestDot)
			{
				BestDot = Dot;
				OutwardSide = Side;
			}
		}

		return OutwardSide;
	};


	// -------------------------------------------------------------------------
	// Generate grid
	// -------------------------------------------------------------------------

	for (const FHexCoord& HexCoord : HexCoords)
	{
		const FVector2D Loc2d = HexToWorld(
			HexCoord.Q,
			HexCoord.R,
			HexRadius
		);

		// Hex-ring distance from the centre, 0..1 (only used for pillar height below)
		const int32 DistanceFromCenter = FMath::Max3(
			FMath::Abs(HexCoord.Q),
			FMath::Abs(HexCoord.R),
			FMath::Abs(HexCoord.S)
		);

		const float Distance01 = static_cast<float>(DistanceFromCenter) / GridSizeF;


		// ---------------------------------------------------------------------
		// Outline: does this hex exist?
		// ---------------------------------------------------------------------

		// Straight-line distance from the centre as a fraction of the platform radius
		const float Radius01 = static_cast<float>(Loc2d.Size()) / PlatformRadius;

		// Edge noise depends only on the direction from the centre
		const FVector2D Dir = Loc2d.GetSafeNormal();

		const float Broad = FMath::PerlinNoise2D(Dir * NoiseFrequency + NoiseOffset);
		const float Detail = FMath::PerlinNoise2D(Dir * (NoiseFrequency * 2.7f) + NoiseOffset);

		const float EdgeNoise = FMath::Clamp(
			(Broad + Detail * DetailStrength) * PerlinGain,
			-1.f,
			1.f
		);

		// Where the outline sits in this direction: 1 +/- NoiseStrength
		const float EdgeRadius = FMath::Max(0.1f, 1.f + EdgeNoise * NoiseStrength);

		// Distance measured relative to this direction's outline
		const float Local01 = Radius01 / EdgeRadius;

		// 1 at the centre, falling towards 0 at the outline (fallback without a curve is linear)
		const float Falloff = FMath::Clamp(
			NoiseCurve ? NoiseCurve->GetFloatValue(Local01) : 1.f - Local01,
			0.f,
			1.f
		);

		if (Falloff <= DeletionThreshold)
		{
			continue;
		}


		// ---------------------------------------------------------------------
		// Pillar height (same as before)
		// ---------------------------------------------------------------------

		float NoiseBOH = FMath::PerlinNoise3D(
			FVector3d(
				HexCoord.Q * BOH_NoiseScale,
				HexCoord.R * BOH_NoiseScale,
				HexCoord.S * BOH_NoiseScale
			)
		);

		NoiseBOH = (NoiseBOH + 1.f) * 0.5f;

		const float Scale = FMath::Lerp(
			GridSize * VerticalScaling * NoiseBOH,   // center
			0.4f,                                    // edge
			Distance01
		);


		// ---------------------------------------------------------------------
		// Create the instance
		// ---------------------------------------------------------------------

		const FIntVector Coord(
			HexCoord.Q,
			HexCoord.R,
			HexCoord.S
		);

		FTransform InstanceTransform;

		// +X out, -X towards the centre (side i of GetHexSideDirection is at -60 * i degrees)
		InstanceTransform.SetRotation(
			FRotator(0.f, -60.f * GetOutwardSide(Coord), 0.f).Quaternion()
		);

		InstanceTransform.SetLocation(
			FVector(
				Loc2d.X,
				Loc2d.Y,
				//TODO Add slight randomness to z Loc
				0.f
			)
		);

		InstanceTransform.SetScale3D(
			FVector(
				InstanceRadius,
				InstanceRadius,
				bUniformHeight ? UniformScaleZ : Scale
			)
		);

		const int32 InstanceIndex = AddHexInstance(Coord, InstanceTransform);

		if (InstanceIndex == INDEX_NONE)
		{
			continue;
		}

		// Render state is marked dirty once, after the loop
		HexPillarsISM->SetCustomDataValue(InstanceIndex, 0, Falloff, false);
		HexPillarsISM->SetCustomDataValue(InstanceIndex, 1, Loc2d.X, false);
		HexPillarsISM->SetCustomDataValue(InstanceIndex, 2, Loc2d.Y, false);

		HexMap.Add(
			Coord,
			InstanceIndex
		);

		InstanceToHex.Add(
			InstanceIndex,
			Coord
		);
	}
	 EdgeInstances= GetEdgeInstances();

	// Custom data 3 = open-side bits for M_Pillar1's edge mask. Written after the
	// loop so every neighbour already exists in HexMap. The mask reads the pillar's local
	// position, so the bits turn with the pillar: actor side i is local side i - OutwardSide.
	TMap<FIntVector, int32> LocalOpenBits;
	for (const TPair<FIntVector, int32>& Pair : HexMap)
	{
		const int32 Bits = GetOpenSideBits(Pair.Key);
		const int32 Turn = GetOutwardSide(Pair.Key);
		LocalOpenBits.Add(Pair.Key, ((Bits >> Turn) | (Bits << (6 - Turn))) & 0x3F);
	}

	// Custom data 3 = packed edge word for M_Pillar1's edge mask and the snow in M_SmallPillarLines:
	//   bits 0..5   open sides in the pillar's local frame (bit i = local side i)
	//   bits 6..11  rings in from the platform outline (0 = tile with an open side), capped at 63
	//   bits 12..19 direction towards the outline in the pillar's local frame, angle / 360 deg * 256
	// The material extends ring + direction into a distance to the outline that runs on across tiles:
	// ring * spacing + spacing / 2 - dot(LocalXY, Dir).
	{
		static const FIntVector SnowDirections[6] =
		{
			FIntVector( 1,  0, -1), FIntVector( 1, -1,  0), FIntVector( 0, -1,  1),
			FIntVector(-1,  0,  1), FIntVector(-1,  1,  0), FIntVector( 0,  1, -1)
		};

		MaxEdgeRing = 0;
		TMap<FIntVector, int32> Ring;
		TArray<FIntVector> Queue;
		for (const TPair<FIntVector, int32>& Pair : HexMap)
		{
			if (GetOpenSideBits(Pair.Key) != 0)
			{
				Ring.Add(Pair.Key, 0);
				Queue.Add(Pair.Key);
			}
		}
		for (int32 Head = 0; Head < Queue.Num(); ++Head)
		{
			const FIntVector Cur = Queue[Head];
			const int32 K = Ring[Cur];
			for (const FIntVector& D : SnowDirections)
			{
				const FIntVector N = Cur + D;
				if (HexMap.Contains(N) && !Ring.Contains(N))
				{
					Ring.Add(N, K + 1);
					Queue.Add(N);
				}
			}
		}

		for (const TPair<FIntVector, int32>& Pair : HexMap)
		{
			const int32* KPtr = Ring.Find(Pair.Key);
			const int32 K = KPtr ? *KPtr : 0;

			// Outward = open sides, or neighbours one ring closer to the outline
			FVector2D Dir(0.f, 0.f);
			for (int32 i = 0; i < 6; ++i)
			{
				const FIntVector N = Pair.Key + SnowDirections[i];
				const int32* KN = Ring.Find(N);
				if (!HexMap.Contains(N) || (KN && *KN < K))
				{
					const float A = FMath::DegreesToRadians(-60.f * i);
					Dir += FVector2D(FMath::Cos(A), FMath::Sin(A));
				}
			}
			Dir = Dir.GetSafeNormal();

			// Actor -> pillar local: the pillar is yawed by -60 * OutwardSide, so turn the direction by +60 * OutwardSide
			const float T = FMath::DegreesToRadians(60.f * GetOutwardSide(Pair.Key));
			const FVector2D LocalDir(
				Dir.X * FMath::Cos(T) - Dir.Y * FMath::Sin(T),
				Dir.X * FMath::Sin(T) + Dir.Y * FMath::Cos(T)
			);

			const int32 Word = LocalOpenBits.FindRef(Pair.Key) | (FMath::Min(K, 63) << 6) | (PackHexAngle(LocalDir) << 12);
			HexPillarsISM->SetCustomDataValue(Pair.Value, 3, static_cast<float>(Word), false);
			// Path word until the bridge paths are laid: no path
			HexPillarsISM->SetCustomDataValue(Pair.Value, 4, static_cast<float>(PackHexPathWord(15, FVector2D::ZeroVector)), false);
			MaxEdgeRing = FMath::Max(MaxEdgeRing, K);
		}
	}
	// Per platform (custom primitive data, shared by every pillar): 0 = deepest ring from the outline, 1 = tile count.
	// The snow scales its reach with these, so small platforms get a narrow drift and big ones a wide one.
	HexPillarsISM->SetCustomPrimitiveDataFloat(0, static_cast<float>(MaxEdgeRing));
	HexPillarsISM->SetCustomPrimitiveDataFloat(1, static_cast<float>(HexMap.Num()));
	HexPillarsISM->MarkRenderStateDirty();

	BuildTileInfos();
	
}

// =============================================================================
// Generate Hex Grid
// =============================================================================

TArray<FHexCoord> AMyHexPlatform::GenerateHexGrid()
{
	TArray<FHexCoord> Hexes;

	for (int32 Q = -GridSize; Q <= GridSize; ++Q)
	{
		const int32 RMax = FMath::Max(-GridSize,-Q - GridSize);

		const int32 RMin = FMath::Min(GridSize,-Q + GridSize);

		for (int32 R = RMax; R <= RMin; ++R)
		{
			FHexCoord Hex;

			Hex.Q = Q;
			Hex.R = R;
			Hex.S = -Q - R;

			Hexes.Add(Hex);
		}
	}

	return Hexes;
}


// =============================================================================
// Hex -> World
// =============================================================================

FVector2D AMyHexPlatform::HexToWorld(int32 Q,int32 R,float InHexRadius) const
{
	const float X =
		InHexRadius *
		FMath::Sqrt(3.f) *
		(Q + R * 0.5f);

	const float Y =
		InHexRadius *
		1.5f *
		R;

	return FVector2D(
		X,
		Y
	);
}


// =============================================================================
// Get Neighbors
// =============================================================================

TArray<FIntVector> AMyHexPlatform::GetNeighbors(
	const FIntVector& Hex
)
{
	static const FIntVector Directions[6] =
	{
		FIntVector( 1,  0, -1),
		FIntVector( 1, -1,  0),
		FIntVector( 0, -1,  1),
		FIntVector(-1,  0,  1),
		FIntVector(-1,  1,  0),
		FIntVector( 0,  1, -1)
	};


	TArray<FIntVector> Result;

	for (const FIntVector& Direction : Directions)
	{
		const FIntVector Neighbor =
			Hex + Direction;

		// HexMap only contains tiles that still exist in the ISM.
		//
		// Therefore this automatically excludes already activated
		// tiles that have been removed from the ISM.

		if (HexMap.Contains(Neighbor) && !PendingActivationTiles.Contains(Neighbor))
		{
			Result.Add(Neighbor);
		}
	}

	return Result;
}


// =============================================================================
// Generate Chain
// =============================================================================

TArray<FIntVector> AMyHexPlatform::GenerateChain(
	int32 Length,
	const FIntVector& StartHex
)
{
	TArray<FIntVector> Chain;

	if (!HexMap.Contains(StartHex))
	{
		return Chain;
	}


	TSet<FIntVector> Visited;

	FIntVector Current = StartHex;

	Chain.Add(Current);
	Visited.Add(Current);


	for (int32 i = 1; i < Length; ++i)
	{
		TArray<FIntVector> Neighbors =
			GetNeighbors(Current);


		// Remove already visited coordinates.

		for (int32 j = Neighbors.Num() - 1; j >= 0; --j)
		{
			if (Visited.Contains(Neighbors[j]))
			{
				Neighbors.RemoveAt(j);
			}
		}


		if (Neighbors.Num() == 0)
		{
			break;
		}


		Current =
			Neighbors[
				FMath::RandRange(
					0,
					Neighbors.Num() - 1
				)
			];


		Chain.Add(Current);
		Visited.Add(Current);
	}


	return Chain;
}


// =============================================================================
// Generate Random Chain
// =============================================================================

void AMyHexPlatform::GenerateAndActivateChainFromRandomSelectedGrid()
{
	//TODO Set variable ChainLength based on grid size
	constexpr int32 ChainLength = 15;
	
	// Server only.

	if (!HasAuthority())
	{
		return;
	}

	// Every tile is gone: stop the chain timer
	if (HexMap.Num() == 0)
	{
		GetWorldTimerManager().ClearTimer(CollapseTimerHandle);
		return;
	}


	TArray<FIntVector> Keys;

	HexMap.GetKeys(Keys);

	
	// -------------------------------------------------------------
	// If only a few tiles remain, destroy ALL of them.
	// Don't rely on neighbor connectivity.
	// -------------------------------------------------------------

	if (Keys.Num() <= ChainLength)
	{
		for (const FIntVector& Coord : Keys)
		{
			PendingActivationTiles.Add(Coord);
		}

		ActivateChain(Keys);

		return;
	}
	
	// Remove tiles that are already scheduled
	// to be activated by another chain.
	Keys.RemoveAll(
		[this](const FIntVector& Coord)
		{
			return PendingActivationTiles.Contains(Coord);
		}
	);


	if (Keys.Num() == 0)
	{
		return;
	}
	

	// -------------------------------------------------------------
	// Normal case
	// -------------------------------------------------------------

	
	const FIntVector RandomStart =
		Keys[
			FMath::RandRange(
				0,
				Keys.Num() - 1
			)
		];




	const TArray<FIntVector> Chain =
		GenerateChain(
			ChainLength,
			RandomStart
		);

	// Reserve the entire chain immediately.
	// This prevents the next chain from using these tiles.
	for (const FIntVector& Coord : Chain)
	{
		PendingActivationTiles.Add(Coord);
	}


	ActivateChain(Chain);
}


// =============================================================================
// Activate Chain
// =============================================================================

void AMyHexPlatform::ActivateChain(
	const TArray<FIntVector>& Chain
)
{
	if (!HasAuthority())
	{
		return;
	}


	for (int32 i = 0; i <= Chain.Num()-1; i++)
	{
		const FIntVector Coord = Chain[i];
		
		if (i == 0)
		{
			// Activate first tile immediately.
			ActivateHex(Coord);
			continue;
		}

		FTimerHandle Handle;

		GetWorld()->GetTimerManager().SetTimer(
			Handle,

			FTimerDelegate::CreateWeakLambda(
				this,
				[this, Coord]()
				{
					ActivateHex(Coord);
				}
			),

			i * .1f,

			false
		);
	}
}


// =============================================================================
// Activate Hex - SERVER
// =============================================================================

void AMyHexPlatform::ActivateHex(
	const FIntVector& Coord
)
{
	if (!HasAuthority())
	{
		return;
	}



	// Don't activate it twice.

	if (LocalActivatedTiles.Contains(Coord))
	{
		return;
	}
	


	if (!HexMap.Contains(Coord))
	{
		return;
	}


	// -------------------------------------------------------------------------
	// Replicate the state
	// -------------------------------------------------------------------------

	ActivatedTiles.Add(Coord);


	// -------------------------------------------------------------------------
	// Perform the visual transition locally on the server too.
	// -------------------------------------------------------------------------

	ActivateHexLocal(Coord);
	
	
	PendingActivationTiles.Remove(Coord);
}


// =============================================================================
// OnRep Activated Tiles
// =============================================================================

void AMyHexPlatform::OnRep_ActivatedTiles()
{
	// The initial bunch arrives before BeginPlay builds the grid with the replicated shape.
	// BeginPlay applies these tiles itself.
	if (!HasActorBegunPlay())
	{
		return;
	}

	ApplyActivatedTiles(/*bPlayEffect=*/true);
}

void AMyHexPlatform::ApplyActivatedTiles(bool bPlayEffect)
{
	// The client receives the complete/current ActivatedTiles array.
	//
	// Find anything that this machine hasn't visually activated yet.

	for (const FIntVector& Coord : ActivatedTiles)
	{
		if (!LocalActivatedTiles.Contains(Coord))
		{
			ActivateHexLocal(Coord, bPlayEffect);
		}
	}
}


// =============================================================================
// Activate Hex Locally
// =============================================================================

void AMyHexPlatform::ActivateHexLocal(const FIntVector& Coord, bool bPlayEffect)
{
	if (LocalActivatedTiles.Contains(Coord))
	{
		return;
	}

	int32* InstanceIndexPtr = HexMap.Find(Coord);

	if (!InstanceIndexPtr)
	{
		UE_LOG(
			LogTemp,
			Error,
			TEXT("ActivateHexLocal: Could not find Coord %s in HexMap"),
			*Coord.ToString()
		);

		return;
	}

	// -------------------------------------------------------------------------
	// Get the exact transform BEFORE removing the ISM instance
	// -------------------------------------------------------------------------

	FTransform InstanceTransform;

	if (!HexPillarsISM->GetInstanceTransform(
		*InstanceIndexPtr,
		InstanceTransform,
		true))
	{
		UE_LOG(
			LogTemp,
			Error,
			TEXT("ActivateHexLocal: Failed to get ISM transform for %s"),
			*Coord.ToString()
		);

		return;
	}

	// -------------------------------------------------------------------------
	// Remove static instance
	// -------------------------------------------------------------------------

	if (!RemoveHexInstance(Coord))
	{
		UE_LOG(
			LogTemp,
			Error,
			TEXT("ActivateHexLocal: Failed to remove ISM instance for %s"),
			*Coord.ToString()
		);

		return;
	}

	LocalActivatedTiles.Add(Coord);

	// Break visuals (tile animation, prop debris) only near the local player; further out, up to
	// FarBreakMaxDistance, the baked far breaks. None without a local player (dedicated server).
	double PlayerDistance = 0.0;
	const bool bHasLocalPlayer = GetLocalPlayerDistance2D(InstanceTransform.GetLocation(), PlayerDistance);
	const bool bInEffectsRange = bHasLocalPlayer && PlayerDistance <= BreakEffectsMaxDistance;
	const bool bFar = bPlayEffect && bHasLocalPlayer && !bInEffectsRange
		&& (FarBreakMaxDistance <= 0.f || PlayerDistance <= FarBreakMaxDistance);

	// The pillar's far break goes first, so at FarBreakMaxActive the tile gets its slot before its props
	// (HandleTileActivated, during the broadcast below). Not where the platform itself is already culled.
	if (bFar && (PlatformMaxDrawDistance <= 0.f || PlayerDistance <= PlatformMaxDrawDistance))
	{
		PlayFarBreak(bIsBottomPlatform ? FarBottomPillar : FarTopPillar, InstanceTransform, GetPillarAnimRate(InstanceTransform.GetScale3D().Z));
	}

	// Bridges ending on this tile listen for this
	bBreakingTileInEffectsRange = bPlayEffect && bInEffectsRange;
	bBreakingTileFar = bFar;
	BreakingTileDistance = PlayerDistance;
	OnHexTileActivated.Broadcast(this, Coord);
	bBreakingTileInEffectsRange = false;
	bBreakingTileFar = false;

	if (bFar)
	{
		return;
	}

	if (!bPlayEffect || !bInEffectsRange)
	{
		return;
	}

	// Top platforms break into a Geometry Collection instead of the skeletal mesh fall. Every machine
	// makes its own from the replicated ActivatedTiles, under one world-wide budget.
	FTransform PillarSpawnTransform;
	UGeometryCollection* PillarCollection = bIsBottomPlatform ? nullptr : GetTopPillarCollection(InstanceTransform, PillarSpawnTransform);

	if (PillarCollection)
	{
		if (UMyHexPillarBreakSubsystem* PillarBreaks = GetWorld()->GetSubsystem<UMyHexPillarBreakSubsystem>())
		{
			// The pieces only spread out through sides with no standing neighbour (this tile already left HexMap)
			TArray<FVector> OpenSides;
			const int32 OpenSideBits = GetOpenSideBits(Coord);

			for (int32 Side = 0; Side < 6; ++Side)
			{
				if (OpenSideBits & (1 << Side))
				{
					OpenSides.Add(HexPillarsISM->GetComponentTransform().TransformVectorNoScale(FVector(GetHexSideDirection(Side), 0.0)).GetSafeNormal());
				}
			}

			// Gone after the same delay as the tile prop debris (BrokenPropLifeSpan), all at once
			const float RemoveAfter = TopPillarBreak.bMatchTilePropLifeSpan ? BrokenPropLifeSpan : TopPillarBreak.LifeSpan;

			PillarBreaks->QueueBreak(this, PillarCollection, PillarSpawnTransform, OpenSides, TopPillarBreak, HexRadius / 100.f, RemoveAfter);
		}

		return;
	}

	// Bottom platforms fall with the bottom assets; until both are set their tiles just disappear
	USkeletalMesh* FallMesh = bIsBottomPlatform ? HexPillarBottomSkeletalMesh.Get() : HexPillarSkeletalMesh.Get();
	UAnimSequence* FallAnim = bIsBottomPlatform ? BottomRbdAnimSeq.Get() : RbdAnimSeq.Get();

	if (bIsBottomPlatform && (!FallMesh || !FallAnim))
	{
		return;
	}

	// -------------------------------------------------------------------------
	// Spawn skeletal mesh at EXACT SAME TRANSFORM
	// -------------------------------------------------------------------------

	USkeletalMeshComponent* SkeletalMesh =
		NewObject<USkeletalMeshComponent>(
			this,
			USkeletalMeshComponent::StaticClass()
		);

	if (!SkeletalMesh)
	{
		return;
	}

	SkeletalMesh->SetSkeletalMesh(FallMesh);

	SkeletalMesh->SetAnimationMode(
		EAnimationMode::AnimationSingleNode
	);

	SkeletalMesh->SetCollisionEnabled(
		ECollisionEnabled::QueryAndPhysics
	);

	SkeletalMesh->SetCollisionResponseToAllChannels(
		ECR_Block
	);

	// Don't attach it to the ISM.
	//
	// The ISM is disappearing/losing instances, so there is no reason
	// for the animated mesh to be a child of it.

	SkeletalMesh->SetWorldTransform(InstanceTransform);

	SkeletalMesh->RegisterComponent();

	ActiveAnimatedPillars.Add(SkeletalMesh);

	// -------------------------------------------------------------------------
	// Play animation
	// -------------------------------------------------------------------------

	if (!FallAnim)
	{
		UE_LOG(
			LogTemp,
			Error,
			TEXT("ActivateHexLocal: RbdAnimSeq is NULL")
		);

		return;
	}

	
	
	// Mesh->OverrideAnimationData(MyAnimSequence, /*bIsLooping=*/true, /*bIsPlaying=*/true,
	// 						/*Position=*/0.f, /*PlayRate=*/1.5f);
	
	SkeletalMesh->PlayAnimation(
		FallAnim,
		false
	);
	
	const float AnimRate = GetPillarAnimRate(InstanceTransform.GetScale3D().Z);
	
	SkeletalMesh->SetPlayRate(AnimRate);

	UE_LOG(
		LogTemp,
		Display,
		TEXT("Activated Hex %s"),
		*Coord.ToString()
	);

	// -------------------------------------------------------------------------
	// Destroy after animation
	// -------------------------------------------------------------------------

	float AnimationLength =
		FallAnim->GetPlayLength();
	AnimationLength/= AnimRate;

	FTimerHandle TimerHandle;

	GetWorld()->GetTimerManager().SetTimer(
		TimerHandle,
		FTimerDelegate::CreateWeakLambda(
			this,
			[this, SkeletalMesh]()
			{
				RemoveAnimatedPillar(SkeletalMesh);
			}
		),
		AnimationLength,
		false
	);
}

// =============================================================================
// Add ISM Instance
// =============================================================================

int32 AMyHexPlatform::AddHexInstance(
	const FIntVector& Coord,
	const FTransform& Transform
)
{
	if (!HexPillarsISM)
	{
		return INDEX_NONE;
	}


	// false = transform is relative to the ISM component.
	//
	// Since HexPillarsISM is the root component, this means the
	// hex grid is relative to the platform Actor.

	const int32 InstanceIndex =
		HexPillarsISM->AddInstance(
			Transform,
			false
		);


	return InstanceIndex;
}


// =============================================================================
// Remove ISM Instance
// =============================================================================

bool AMyHexPlatform::RemoveHexInstance(const FIntVector& Coord)
{
	int32* InstanceIndexPtr = HexMap.Find(Coord);

	if (!InstanceIndexPtr)
	{
		return false;
	}

	const int32 RemovedIndex = *InstanceIndexPtr;
	const int32 LastIndex = HexPillarsISM->GetInstanceCount() - 1;

	if (RemovedIndex < 0 || RemovedIndex > LastIndex)
	{
		return false;
	}

	// If we are removing anything other than the last instance,
	// the last instance will be moved into RemovedIndex.
	FIntVector MovedCoord;

	if (RemovedIndex != LastIndex)
	{
		const FIntVector* MovedCoordPtr =
			InstanceToHex.Find(LastIndex);

		if (!MovedCoordPtr)
		{
			UE_LOG(
				LogTemp,
				Error,
				TEXT("RemoveHexInstance: InstanceToHex has no entry for LastIndex %d"),
				LastIndex
			);

			return false;
		}

		MovedCoord = *MovedCoordPtr;
	}

	// Remove the ISM instance.
	if (!HexPillarsISM->RemoveInstance(RemovedIndex))
	{
		return false;
	}

	// Remove the coordinate that was activated.
	HexMap.Remove(Coord);
	InstanceToHex.Remove(RemovedIndex);

	// Repair the coordinate whose instance was moved from LastIndex
	// into RemovedIndex.
	if (RemovedIndex != LastIndex)
	{
		HexMap.FindChecked(MovedCoord) = RemovedIndex;
		InstanceToHex.Add(RemovedIndex, MovedCoord);
	}

	return true;
}


// =============================================================================
// Spawn Animated Pillar
// =============================================================================

float AMyHexPlatform::GetPillarAnimRate(float PillarScaleZ)
{
	return FMath::GetMappedRangeValueClamped(FVector2D(1.f, .4f), FVector2D(1.f, 2.5f), PillarScaleZ);
}

UGeometryCollection* AMyHexPlatform::GetTopPillarCollection(const FTransform& InstanceTransform, FTransform& OutSpawnTransform) const
{
	OutSpawnTransform = InstanceTransform;

	const FVector Scale = InstanceTransform.GetScale3D();
	const double ScaleXY = 0.5 * (FMath::Abs(Scale.X) + FMath::Abs(Scale.Y));

	if (bUseTopPillarHeightVariants && ScaleXY > UE_KINDA_SMALL_NUMBER)
	{
		// Nearest height in ratio terms (log space): steps are a constant factor apart
		const double LogRatio = FMath::Loge(FMath::Max(FMath::Abs(Scale.Z) / ScaleXY, UE_KINDA_SMALL_NUMBER));
		const FHexPillarGCVariant* Best = nullptr;
		double BestError = TNumericLimits<double>::Max();

		for (const FHexPillarGCVariant& Variant : TopPillarHeightVariants)
		{
			if (!Variant.Collection || Variant.HeightRatio <= 0.f)
			{
				continue;
			}

			const double Error = FMath::Abs(FMath::Loge(static_cast<double>(Variant.HeightRatio)) - LogRatio);

			if (Error < BestError)
			{
				BestError = Error;
				Best = &Variant;
			}
		}

		if (Best)
		{
			// The variant carries most of the height. bExactTopPillarHeight: the rest goes in the Z scale, so the
			// pillar matches the tile exactly (Z / XY left over: 0.66 .. 1.5 with the default three); else a
			// uniform scale, which keeps turning pieces exact but leaves the height up to that much off.
			const double ScaleZ = bExactTopPillarHeight ? FMath::Abs(Scale.Z) / Best->HeightRatio : ScaleXY;
			OutSpawnTransform.SetScale3D(FVector(Scale.X, Scale.Y, ScaleZ));
			return Best->Collection;
		}
	}

	return TopPillarGeometryCollection;
}

UStaticMesh* AMyHexPlatform::GetTileMesh() const
{
	return bIsBottomPlatform && HexPillarBottomStaticMesh ? HexPillarBottomStaticMesh.Get() : HexPillarStaticMesh.Get();
}


// =============================================================================
// Remove Animated Pillar
// =============================================================================

void AMyHexPlatform::RemoveAnimatedPillar(
	USkeletalMeshComponent* SkeletalMeshComponent
)
{
	if (!SkeletalMeshComponent)
	{
		return;
	}


	ActiveAnimatedPillars.Remove(
		SkeletalMeshComponent
	);


	SkeletalMeshComponent->DestroyComponent();
}


// =============================================================================
// Utility
// =============================================================================

bool AMyHexPlatform::IsValidHex(
	const FIntVector& Coord
) const
{
	return HexMap.Contains(Coord);
}

void AMyHexPlatform::DebugBreakTiles(int32 NumChains)
{
	if (!HasAuthority())
	{
		return;
	}

	if (NumChains <= 0)
	{
		TArray<FIntVector> Coords;
		HexMap.GetKeys(Coords);

		for (const FIntVector& Coord : Coords)
		{
			ActivateHex(Coord);
		}

		return;
	}

	for (int32 Chain = 0; Chain < NumChains; ++Chain)
	{
		GenerateAndActivateChainFromRandomSelectedGrid();
	}
}

bool AMyHexPlatform::IsTileCollapsed(
	const FIntVector& Coord
) const
{
	// ActivatedTiles is replicated, so a late-joining client knows before it plays the collapse
	return LocalActivatedTiles.Contains(Coord) || ActivatedTiles.Contains(Coord);
}


// GetEdges

TArray<FIntVector> AMyHexPlatform::GetOriginalEdgeHexes() const
{
	TArray<FIntVector> EdgeHexes;

	for (int32 Q = -GridSize; Q <= GridSize; ++Q)
	{
		const int32 RMin = FMath::Max(
			-GridSize,
			-Q - GridSize
		);

		const int32 RMax = FMath::Min(
			GridSize,
			-Q + GridSize
		);

		for (int32 R = RMin; R <= RMax; ++R)
		{
			const int32 S = -Q - R;

			if (FMath::Max3(
				FMath::Abs(Q),
				FMath::Abs(R),
				FMath::Abs(S)
			) == GridSize)
			{
				EdgeHexes.Add(
					FIntVector(Q, R, S)
				);
			}
		}
	}

	return EdgeHexes;
}


// GetEdgeInstancesAfterDeletion

TMap<int32, TArray<FIntVector>> AMyHexPlatform::GetEdgeInstances() const
{
	TMap<int32, TArray<FIntVector>> OutEdgeInstances;

	static const FIntVector Directions[6] =
	{
		FIntVector( 1,  0, -1),
		FIntVector( 1, -1,  0),
		FIntVector( 0, -1,  1),
		FIntVector(-1,  0,  1),
		FIntVector(-1,  1,  0),
		FIntVector( 0,  1, -1)
	};

	for (const auto& Pair : HexMap)
	{
		const FIntVector& Coord = Pair.Key;
		const int32 InstanceIndex = Pair.Value;

		TArray<FIntVector> MissingNeighbors;

		for (const FIntVector& Direction : Directions)
		{
			const FIntVector Neighbor = Coord + Direction;

			// Neighbor does not currently exist.
			if (!HexMap.Contains(Neighbor))
			{
				MissingNeighbors.Add(Neighbor);
			}
		}

		// Only store instances that have at least one missing neighbor.
		if (MissingNeighbors.Num() > 0)
		{
			OutEdgeInstances.Add(
				InstanceIndex,
				MoveTemp(MissingNeighbors)
			);
		}
	}

	return OutEdgeInstances;
}

// Bit i set = side Directions[i] has no neighbour. 0..63, exact as a float.
int32 AMyHexPlatform::GetOpenSideBits(const FIntVector& Coord) const
{
	static const FIntVector Directions[6] =
	{
		FIntVector( 1,  0, -1), FIntVector( 1, -1,  0), FIntVector( 0, -1,  1),
		FIntVector(-1,  0,  1), FIntVector(-1,  1,  0), FIntVector( 0,  1, -1)
	};

	int32 Bits = 0;
	for (int32 i = 0; i < 6; ++i)
	{
		if (!HexMap.Contains(Coord + Directions[i]))
		{
			Bits |= 1 << i;
		}
	}
	return Bits;
}


// =============================================================================
// Tile infos
// =============================================================================

const FName AMyHexPlatform::TileIndexAttributeName(TEXT("TileIndex"));

int32 AMyHexPlatform::MakeTileIndex(const FIntVector& Coord) const
{
	const int32 Size = FMath::Max(0, GridSize);
	const int32 Width = 2 * Size + 1;

	return (Coord.X + Size) * Width + (Coord.Y + Size);
}

FVector2D AMyHexPlatform::GetHexSideDirection(int32 Side)
{
	// Same order as the Directions in GetOpenSideBits, turned into actor space with HexToWorld's formula
	static const FIntVector Directions[6] =
	{
		FIntVector( 1,  0, -1), FIntVector( 1, -1,  0), FIntVector( 0, -1,  1),
		FIntVector(-1,  0,  1), FIntVector(-1,  1,  0), FIntVector( 0,  1, -1)
	};

	const FIntVector& D = Directions[((Side % 6) + 6) % 6];

	return FVector2D(FMath::Sqrt(3.f) * (D.X + D.Y * 0.5f), 1.5f * D.Y).GetSafeNormal();
}

void AMyHexPlatform::BuildTileInfos()
{
	TileInfos.Reset();

	if (!HexPillarsISM || !HexPillarsISM->GetStaticMesh())
	{
		return;
	}

	const FBox MeshBox = HexPillarsISM->GetStaticMesh()->GetBoundingBox();

	for (const TPair<FIntVector, int32>& Pair : HexMap)
	{
		FTransform InstanceTransform;

		if (!HexPillarsISM->GetInstanceTransform(Pair.Value, InstanceTransform, /*bWorldSpace=*/false))
		{
			continue;
		}

		// Without the pillar's 60 degree turn: the hex covers the same ground, but its turned box wouldn't
		InstanceTransform.SetRotation(FQuat::Identity);

		const FBox Box = MeshBox.TransformBy(InstanceTransform);
		const FVector Location = InstanceTransform.GetLocation();

		FHexTileInfo& Info = TileInfos.Add(Pair.Key);
		Info.Coord = Pair.Key;
		Info.TileIndex = MakeTileIndex(Pair.Key);
		Info.LocalTopCenter = FVector(Location.X, Location.Y, Box.Max.Z);
		Info.LocalBounds = Box;
		Info.Apothem = static_cast<float>(MeshBox.GetExtent().X * InstanceTransform.GetScale3D().X);
		Info.OpenSideBits = GetOpenSideBits(Pair.Key);
		Info.EdgeDepth = MAX_int32;
	}

	// Edge depth: rings in from the outline, breadth first from every tile with an open side
	TArray<FIntVector> Queue;
	Queue.Reserve(TileInfos.Num());

	for (TPair<FIntVector, FHexTileInfo>& Pair : TileInfos)
	{
		if (Pair.Value.OpenSideBits != 0)
		{
			Pair.Value.EdgeDepth = 0;
			Queue.Add(Pair.Key);
		}
	}

	for (int32 Head = 0; Head < Queue.Num(); ++Head)
	{
		const FIntVector Current = Queue[Head];
		const int32 NextDepth = TileInfos.FindChecked(Current).EdgeDepth + 1;

		for (const FIntVector& Neighbor : GetNeighbors(Current))
		{
			FHexTileInfo* NeighborInfo = TileInfos.Find(Neighbor);

			if (NeighborInfo && NeighborInfo->EdgeDepth > NextDepth)
			{
				NeighborInfo->EdgeDepth = NextDepth;
				Queue.Add(Neighbor);
			}
		}
	}

	// The grid as built, for the bridge paths (late joiners remove fallen tiles after this)
	PathLayoutTiles.Reset();
	for (const TPair<FIntVector, FHexTileInfo>& Pair : TileInfos)
	{
		PathLayoutTiles.Add(Pair.Key, Pair.Value.LocalTopCenter);
	}
}


// =============================================================================
// Tile props
// =============================================================================

void AMyHexPlatform::ScheduleTileProps(float Delay)
{
	UWorld* World = GetWorld();

	if (!World || AreTilePropsFrozen())
	{
		return;
	}

	// Coalesce bursts of bridge changes, but never bring a pending generation forward
	// (the first bridge must not cut PropsBridgeWait short)
	FTimerManager& TimerManager = World->GetTimerManager();

	if (TimerManager.IsTimerActive(TilePropsTimerHandle))
	{
		Delay = FMath::Max(Delay, TimerManager.GetTimerRemaining(TilePropsTimerHandle));
	}

	TimerManager.SetTimer(TilePropsTimerHandle, this, &ThisClass::RebuildPathAndTileProps, FMath::Max(Delay, 0.01f), false);
}

void AMyHexPlatform::RebuildPathAndTileProps()
{
	// The lead landed, collapsing started or a tile fell since this was scheduled
	if (AreTilePropsFrozen())
	{
		return;
	}

	// A generation still running would ignore the new request, so come back once it's done
	for (const UPCGComponent* PropsPCG : { TilePropsPCG.Get(), HexTileProps2.Get() })
	{
		if (PropsPCG && PropsPCG->IsGenerating())
		{
			ScheduleTileProps(0.25f);
			return;
		}
	}

	UE_LOG(LogTemp, Log, TEXT("%s: generating tile props (%d path start tiles, %d tiles fallen)"), *GetName(), PathStartTiles.Num(), LocalActivatedTiles.Num());

	BuildBridgePaths();
	WritePathCustomData();
	GenerateTileProps();
}

int32 AMyHexPlatform::PackHexAngle(const FVector2D& Dir)
{
	if (Dir.IsNearlyZero())
	{
		return 0;
	}
	const float Turns = FMath::Atan2(Dir.Y, Dir.X) / (2.f * PI);
	return FMath::RoundToInt32((Turns - FMath::FloorToFloat(Turns)) * 256.f) & 0xFF;
}

int32 AMyHexPlatform::PackHexPathWord(int32 PathRing, const FVector2D& LocalDir)
{
	// bits 0..3 rings from the bridge path (0 = on it, 15 = no path / far), bits 4..11 direction:
	// on path tiles along the path, elsewhere towards the nearest path tile (pillar-local angle)
	return FMath::Clamp(PathRing, 0, 15) | (PackHexAngle(LocalDir) << 4);
}

void AMyHexPlatform::WritePathCustomData()
{
	if (!HexPillarsISM)
	{
		return;
	}

	static const FIntVector Directions[6] =
	{
		FIntVector( 1,  0, -1), FIntVector( 1, -1,  0), FIntVector( 0, -1,  1),
		FIntVector(-1,  0,  1), FIntVector(-1,  1,  0), FIntVector( 0,  1, -1)
	};

	for (const TPair<FIntVector, int32>& Pair : HexMap)
	{
		const FHexTileInfo* Info = TileInfos.Find(Pair.Key);
		const int32 Dist = Info ? Info->PathDistance : MAX_int32;
		FVector2D Dir = FVector2D::ZeroVector;

		if (Dist == 0)
		{
			Dir = Info->PathDirection;
		}
		else if (Dist < 15)
		{
			// Towards the path = towards neighbours that are closer to it
			for (int32 i = 0; i < 6; ++i)
			{
				const FHexTileInfo* N = TileInfos.Find(Pair.Key + Directions[i]);
				if (N && N->PathDistance < Dist)
				{
					const float A = FMath::DegreesToRadians(-60.f * i);
					Dir += FVector2D(FMath::Cos(A), FMath::Sin(A));
				}
			}
		}
		Dir = Dir.GetSafeNormal();

		// Actor -> pillar local: undo the pillar's yaw (-60 * OutwardSide, see BuildHexGrid)
		FTransform InstanceTransform;
		HexPillarsISM->GetInstanceTransform(Pair.Value, InstanceTransform, /*bWorldSpace=*/false);
		const float T = -FMath::DegreesToRadians(InstanceTransform.GetRotation().Rotator().Yaw);
		const FVector2D LocalDir(Dir.X * FMath::Cos(T) - Dir.Y * FMath::Sin(T), Dir.X * FMath::Sin(T) + Dir.Y * FMath::Cos(T));

		HexPillarsISM->SetCustomDataValue(Pair.Value, 4, static_cast<float>(PackHexPathWord(FMath::Min(Dist, 15), LocalDir)), false);
	}
	HexPillarsISM->MarkRenderStateDirty();
}

static TAutoConsoleVariable<int32> CVarPathPavingDebug(
	TEXT("Aura.PathPavingDebug"),
	0,
	TEXT("Bridge path paving debug on every hex platform, when its paving is next laid.\n")
	TEXT("1: draw it (as bDrawPavingDebug). 2: also write each platform's paving input to Saved/PathPaving."),
	ECVF_Cheat);

void AMyHexPlatform::BuildBridgePaths()
{
	for (TPair<FIntVector, FHexTileInfo>& Pair : TileInfos)
	{
		Pair.Value.PathDistance = MAX_int32;
		Pair.Value.PathDirection = FVector2D::ZeroVector;
	}

	PavingSlabs.Reset();
	PathPlaza = FHexPathPlaza();

	if (!bBuildBridgePaths || PathLayoutTiles.IsEmpty() || PathStartTiles.IsEmpty())
	{
		return;
	}

	// Everything below works on the grid as built, not on the live tiles, so every machine (late
	// joiners too) lays the same path; results only go to the tiles still standing.
	static const FIntVector Directions[6] =
	{
		FIntVector( 1,  0, -1), FIntVector( 1, -1,  0), FIntVector( 0, -1,  1),
		FIntVector(-1,  0,  1), FIntVector(-1,  1,  0), FIntVector( 0,  1, -1)
	};

	auto LayoutNeighbors = [this](const FIntVector& Coord)
	{
		TArray<FIntVector, TInlineAllocator<6>> Result;
		for (const FIntVector& Direction : Directions)
		{
			if (PathLayoutTiles.Contains(Coord + Direction))
			{
				Result.Add(Coord + Direction);
			}
		}
		return Result;
	};

	auto TileXY = [this](const FIntVector& Coord)
	{
		const FVector& Top = PathLayoutTiles.FindChecked(Coord);
		return FVector(Top.X, Top.Y, 0.0);
	};

	// Centre: the tile nearest the middle of all tiles (ties to the lower TileIndex)
	FVector Centroid = FVector::ZeroVector;
	for (const TPair<FIntVector, FVector>& Pair : PathLayoutTiles)
	{
		Centroid += TileXY(Pair.Key);
	}
	Centroid /= PathLayoutTiles.Num();

	FIntVector Centre = FIntVector::ZeroValue;
	double BestDistSq = TNumericLimits<double>::Max();
	int32 BestIndex = MAX_int32;

	for (const TPair<FIntVector, FVector>& Pair : PathLayoutTiles)
	{
		const double DistSq = FVector::DistSquared(TileXY(Pair.Key), Centroid);
		const int32 Index = MakeTileIndex(Pair.Key);

		if (DistSq < BestDistSq - 1.0 || (FMath::IsNearlyEqual(DistSq, BestDistSq, 1.0) && Index < BestIndex))
		{
			BestDistSq = DistSq;
			BestIndex = Index;
			Centre = Pair.Key;
		}
	}

	// Steps from the centre
	TMap<FIntVector, int32> StepsToCentre;
	StepsToCentre.Add(Centre, 0);
	TArray<FIntVector> Queue = { Centre };

	for (int32 Head = 0; Head < Queue.Num(); ++Head)
	{
		const FIntVector Current = Queue[Head];
		const int32 NextSteps = StepsToCentre.FindChecked(Current) + 1;

		for (const FIntVector& Neighbor : LayoutNeighbors(Current))
		{
			if (!StepsToCentre.Contains(Neighbor))
			{
				StepsToCentre.Add(Neighbor, NextSteps);
				Queue.Add(Neighbor);
			}
		}
	}

	// Walk down the step count from each start tile (already sorted), keeping close to the straight
	// line to the centre, until the centre or a tile an earlier walk laid (that one already leads to
	// the centre). A start the walk can't leave is still kept clear.
	TSet<FIntVector> PathSet;
	TMap<FIntVector, FVector2D> PathDirections;

	// Each walk's tiles in order, for the paving
	TArray<TArray<FIntVector>> Routes;

	for (const FIntVector& Start : PathStartTiles)
	{
		if (!PathLayoutTiles.Contains(Start))
		{
			continue;
		}

		TArray<FIntVector>& Route = Routes.AddDefaulted_GetRef();
		Route.Add(Start);

		bool bAlreadyInSet = false;
		PathSet.Add(Start, &bAlreadyInSet);

		if (bAlreadyInSet || !StepsToCentre.Contains(Start))
		{
			continue;
		}

		const FVector LineStart = TileXY(Start);
		const FVector LineEnd = TileXY(Centre);
		FIntVector Current = Start;

		while (Current != Centre)
		{
			const int32 WantedSteps = StepsToCentre.FindChecked(Current) - 1;
			FIntVector Next = Current;
			double BestLineDist = TNumericLimits<double>::Max();

			for (const FIntVector& Neighbor : LayoutNeighbors(Current))
			{
				const int32* Steps = StepsToCentre.Find(Neighbor);

				if (!Steps || *Steps != WantedSteps)
				{
					continue;
				}

				const double LineDist = FMath::PointDistToSegment(TileXY(Neighbor), LineStart, LineEnd);

				if (LineDist < BestLineDist - 0.5 || (FMath::IsNearlyEqual(LineDist, BestLineDist, 0.5) && MakeTileIndex(Neighbor) < MakeTileIndex(Next)))
				{
					BestLineDist = LineDist;
					Next = Neighbor;
				}
			}

			if (Next == Current)
			{
				break;
			}

			// First path through a tile sets its direction
			if (!PathDirections.Contains(Current))
			{
				const FVector Step = TileXY(Next) - TileXY(Current);
				PathDirections.Add(Current, FVector2D(Step.X, Step.Y).GetSafeNormal());
			}

			Current = Next;
			Route.Add(Current);

			bool bJoined = false;
			PathSet.Add(Current, &bJoined);

			if (bJoined)
			{
				break;
			}
		}
	}

	// The centre carries on in the direction of a path that reached it
	if (PathSet.Contains(Centre) && !PathDirections.Contains(Centre))
	{
		for (const FIntVector& Neighbor : LayoutNeighbors(Centre))
		{
			if (const FVector2D* Direction = PathDirections.Find(Neighbor))
			{
				PathDirections.Add(Centre, *Direction);
				break;
			}
		}
	}

#if !UE_BUILD_SHIPPING
	// Aura.PathPavingDebug 2: what the paving is laid from, in the paving test harness's format
	if (bPaveBridgePaths && CVarPathPavingDebug.GetValueOnAnyThread() >= 2)
	{
		FString Text = FString::Printf(TEXT("TILES %d\n"), PathLayoutTiles.Num());

		for (const TPair<FIntVector, FVector>& Pair : PathLayoutTiles)
		{
			Text += FString::Printf(TEXT("%d %d %d %.6f %.6f %.6f\n"), Pair.Key.X, Pair.Key.Y, Pair.Key.Z, Pair.Value.X, Pair.Value.Y, Pair.Value.Z);
		}

		Text += FString::Printf(TEXT("CENTRE %d %d %d\nSTARTS %d\n"), Centre.X, Centre.Y, Centre.Z, PathStartTiles.Num());

		for (int32 Index = 0; Index < PathStartTiles.Num(); ++Index)
		{
			const FIntVector& Start = PathStartTiles[Index];
			Text += FString::Printf(TEXT("%d %d %d %d\n"), Start.X, Start.Y, Start.Z, PathStartSides.IsValidIndex(Index) ? static_cast<int32>(PathStartSides[Index]) : 255);
		}

		Text += FString::Printf(TEXT("ROUTES %d\n"), Routes.Num());

		for (const TArray<FIntVector>& Route : Routes)
		{
			Text += FString::Printf(TEXT("%d"), Route.Num());

			for (const FIntVector& Coord : Route)
			{
				Text += FString::Printf(TEXT(" %d %d %d"), Coord.X, Coord.Y, Coord.Z);
			}

			Text += TEXT("\n");
		}

		Text += FString::Printf(TEXT("PLAZA %d\n"), bPavePlaza ? 1 : 0);
		Text += FString::Printf(TEXT("PARAM HexRadius %.6f\nPARAM GridSize %d\nPARAM PavingCellSize %.6f\nPARAM PavingCellsAcross %d\nPARAM PavingPatternLength %d\n"),
			HexRadius, GridSize, PavingCellSize, PavingCellsAcross, PavingPatternLength);
		Text += FString::Printf(TEXT("PARAM PavingMaxBend %.6f\nPARAM PavingSmoothing %d\nPARAM PavingSmoothMaxOffset %.6f\nPARAM PavingEdgeReach %.6f\nPARAM PavingStepSplitHeight %.6f\n"),
			PavingMaxBend, PavingSmoothing, PavingSmoothMaxOffset, PavingEdgeReach, PavingStepSplitHeight);
		Text += FString::Printf(TEXT("PARAM PavingPlazaSideCells %.6f\nPARAM PavingPlazaSizeRatio %.6f\nPARAM PavingPlazaMinSides %d\nPARAM PavingPlazaLead %.6f\nPARAM PavingPlazaTurn %.6f\n"),
			PavingPlazaSideCells, PavingPlazaSizeRatio, PavingPlazaMinSides, PavingPlazaLead, PavingPlazaTurn);

		for (const FHexPavingPattern& Pattern : PavingPatterns)
		{
			Text += FString::Printf(TEXT("PATTERN %d"), Pattern.Slabs.Num());

			for (const FHexPavingPatternSlab& Slab : Pattern.Slabs)
			{
				Text += FString::Printf(TEXT(" %d %d %d %d"), Slab.Cell.X, Slab.Cell.Y, Slab.Size.X, Slab.Size.Y);
			}

			Text += TEXT("\n");
		}

		// Named after the map (a PIE world's carries its instance) and the net mode too, so the server's and each
		// PIE client's copies don't overwrite each other
		const UWorld* World = GetWorld();
		const FString FileName = FString::Printf(TEXT("%s_%s_%s.txt"), World ? *World->GetMapName() : TEXT("NoWorld"),
			GetNetMode() == NM_Client ? TEXT("Client") : TEXT("Server"), *GetName());
		const FString FilePath = FPaths::ProjectSavedDir() / TEXT("PathPaving") / FileName;

		if (FFileHelper::SaveStringToFile(Text, *FilePath))
		{
			UE_LOG(LogTemp, Log, TEXT("%s: paving input written to %s"), *GetName(), *FilePath);
		}
		else
		{
			UE_LOG(LogTemp, Warning, TEXT("%s: couldn't write the paving input to %s"), *GetName(), *FilePath);
		}
	}
#endif

	if (bPaveBridgePaths)
	{
		BuildPathPaving(Routes, Centre, PathSet, PathDirections);
	}

	// Straight hex distance to the nearest path tile, so a notch in the outline doesn't let big props closer
	for (TPair<FIntVector, FHexTileInfo>& Pair : TileInfos)
	{
		const FIntVector& Coord = Pair.Key;
		int32 Distance = MAX_int32;

		for (const FIntVector& PathTile : PathSet)
		{
			const FIntVector D = Coord - PathTile;
			Distance = FMath::Min(Distance, FMath::Max3(FMath::Abs(D.X), FMath::Abs(D.Y), FMath::Abs(D.Z)));
		}

		Pair.Value.PathDistance = Distance;

		if (Distance == 0)
		{
			Pair.Value.PathDirection = PathDirections.FindRef(Coord);
		}
	}
}

namespace HexPaving
{
	static const FIntVector Directions[6] =
	{
		FIntVector( 1,  0, -1), FIntVector( 1, -1,  0), FIntVector( 0, -1,  1),
		FIntVector(-1,  0,  1), FIntVector(-1,  1,  0), FIntVector( 0,  1, -1)
	};

	/** Same on every machine (the pattern picks must match). */
	static uint32 Hash(uint32 A, uint32 B)
	{
		uint32 H = A ^ (B * 0x9E3779B1u + 0x7F4A7C15u);
		H ^= H >> 16; H *= 0x7FEB352Du;
		H ^= H >> 15; H *= 0x846CA68Bu;
		H ^= H >> 16;
		return H;
	}

	/** The tile whose centre is nearest an actor-space point: HexToWorld inverted, then cube-rounded. */
	static FIntVector WorldToHex(const FVector2D& Point, double HexRadius)
	{
		const double R = Point.Y / (1.5 * HexRadius);
		const double Q = Point.X / (FMath::Sqrt(3.0) * HexRadius) - R * 0.5;
		const double S = -Q - R;

		double RoundQ = FMath::RoundToDouble(Q);
		double RoundR = FMath::RoundToDouble(R);
		double RoundS = FMath::RoundToDouble(S);

		const double DiffQ = FMath::Abs(RoundQ - Q);
		const double DiffR = FMath::Abs(RoundR - R);
		const double DiffS = FMath::Abs(RoundS - S);

		if (DiffQ > DiffR && DiffQ > DiffS)
		{
			RoundQ = -RoundR - RoundS;
		}
		else if (DiffR > DiffS)
		{
			RoundR = -RoundQ - RoundS;
		}
		else
		{
			RoundS = -RoundQ - RoundR;
		}

		return FIntVector(FMath::RoundToInt32(RoundQ), FMath::RoundToInt32(RoundR), FMath::RoundToInt32(RoundS));
	}

	/** A path spline sampled into a polyline: distance along it -> position and heading. */
	struct FRail
	{
		TArray<FVector2D> Points;

		/** Distance along the rail at each point. */
		TArray<double> Distances;

		/** Radians, one per segment, unwrapped so neighbours never differ by more than pi. */
		TArray<double> Headings;

		/** Bounds of each run of ChunkSegments segments, so InCorridor skips the parts far from a point. */
		TArray<FBox2D> ChunkBounds;

		static constexpr int32 ChunkSegments = 16;

		double Length() const { return Distances.IsEmpty() ? 0.0 : Distances.Last(); }

		bool IsValid() const { return Points.Num() >= 2 && Length() > UE_KINDA_SMALL_NUMBER; }

		void Build(const TArray<FVector2D>& Samples)
		{
			Points.Reset(Samples.Num());

			for (const FVector2D& Sample : Samples)
			{
				if (Points.IsEmpty() || FVector2D::DistSquared(Sample, Points.Last()) > 1.e-4)
				{
					Points.Add(Sample);
				}
			}

			Distances.Reset(Points.Num());
			Headings.Reset(Points.Num());

			double Distance = 0.0;

			for (int32 Index = 0; Index < Points.Num(); ++Index)
			{
				if (Index > 0)
				{
					const FVector2D Step = Points[Index] - Points[Index - 1];
					Distance += Step.Size();

					double Heading = FMath::Atan2(Step.Y, Step.X);

					if (!Headings.IsEmpty())
					{
						Heading = Headings.Last() + FMath::UnwindRadians(Heading - Headings.Last());
					}

					Headings.Add(Heading);
				}

				Distances.Add(Distance);
			}

			ChunkBounds.Reset();

			for (int32 First = 0; First < Points.Num() - 1; First += ChunkSegments)
			{
				FBox2D& Bounds = ChunkBounds.Emplace_GetRef(ForceInit);

				for (int32 Index = First; Index <= FMath::Min(First + ChunkSegments, Points.Num() - 1); ++Index)
				{
					Bounds += Points[Index];
				}
			}
		}

		void Eval(double S, FVector2D& OutPosition, double& OutHeading) const
		{
			S = FMath::Clamp(S, 0.0, Length());

			const int32 Index = FMath::Clamp(static_cast<int32>(Algo::UpperBound(Distances, S)) - 1, 0, Points.Num() - 2);
			const double SegmentLength = Distances[Index + 1] - Distances[Index];
			const double T = SegmentLength > UE_KINDA_SMALL_NUMBER ? (S - Distances[Index]) / SegmentLength : 0.0;

			OutPosition = FMath::Lerp(Points[Index], Points[Index + 1], T);

			// Blend with the neighbouring segment around each point, so the heading doesn't step
			OutHeading = Headings[Index];

			if (T < 0.5 && Index > 0)
			{
				OutHeading = FMath::Lerp(Headings[Index - 1], Headings[Index], T + 0.5);
			}
			else if (T >= 0.5 && Index < Headings.Num() - 1)
			{
				OutHeading = FMath::Lerp(Headings[Index], Headings[Index + 1], T - 0.5);
			}
		}

		/** The point Offset to the left of the rail (to the right if negative) at distance S. */
		FVector2D At(double S, double Offset) const
		{
			FVector2D Position;
			double Heading;
			Eval(S, Position, Heading);

			return Position + FVector2D(-FMath::Sin(Heading), FMath::Cos(Heading)) * Offset;
		}

		/** Total turning (radians, left and right both count) between two distances. */
		double Turning(double S0, double S1) const
		{
			const int32 Steps = FMath::Max(2, FMath::CeilToInt32((S1 - S0) / 5.0));

			FVector2D Position;
			double Previous;
			Eval(S0, Position, Previous);

			double Total = 0.0;

			for (int32 Step = 1; Step <= Steps; ++Step)
			{
				double Heading;
				Eval(FMath::Lerp(S0, S1, static_cast<double>(Step) / Steps), Position, Heading);
				Total += FMath::Abs(Heading - Previous);
				Previous = Heading;
			}

			return Total;
		}

		/** The tightest turn (radius, cm) between distance S0 and the end, measured over steps of about Step. */
		double TightestRadius(double S0, double Step) const
		{
			const int32 Steps = FMath::Max(1, FMath::CeilToInt32((Length() - S0) / Step));
			const double StepLength = (Length() - S0) / Steps;
			double Tightest = TNumericLimits<double>::Max();

			FVector2D Position;
			double Previous;
			Eval(S0, Position, Previous);

			for (int32 Index = 1; Index <= Steps; ++Index)
			{
				double Heading;
				Eval(S0 + StepLength * Index, Position, Heading);
				const double Turn = FMath::Abs(Heading - Previous);

				if (Turn > 1.e-9)
				{
					Tightest = FMath::Min(Tightest, StepLength / Turn);
				}

				Previous = Heading;
			}

			return Tightest;
		}

		/**
		 * Point closer than HalfWidth to the rail. A point whose nearest rail point is an end, and that lies
		 * beyond it, is outside: the strip has flat end caps.
		 */
		bool InCorridor(const FVector2D& Point, double HalfWidth) const
		{
			const double HalfWidthSq = HalfWidth * HalfWidth;
			const int32 LastSegment = Points.Num() - 2;
			double BestSq = TNumericLimits<double>::Max();
			bool bBeyondEnd = false;

			for (int32 Chunk = 0; Chunk < ChunkBounds.Num(); ++Chunk)
			{
				// Nothing in this chunk is nearer than the best so far, or near enough to count
				if (ChunkBounds[Chunk].ComputeSquaredDistanceToPoint(Point) >= FMath::Min(BestSq, HalfWidthSq))
				{
					continue;
				}

				const int32 First = Chunk * ChunkSegments;
				const int32 Last = FMath::Min(First + ChunkSegments - 1, LastSegment);

				for (int32 Index = First; Index <= Last; ++Index)
				{
					const FVector2D& A = Points[Index];
					const FVector2D AB = Points[Index + 1] - A;
					const double LengthSq = AB.SizeSquared();
					const double T = LengthSq > UE_KINDA_SMALL_NUMBER ? FVector2D::DotProduct(Point - A, AB) / LengthSq : 0.0;
					const double DistSq = FVector2D::DistSquared(Point, A + AB * FMath::Clamp(T, 0.0, 1.0));

					// The first nearest segment decides
					if (DistSq < BestSq)
					{
						BestSq = DistSq;
						bBeyondEnd = (Index == 0 && T < 0.0) || (Index == LastSegment && T > 1.0);
					}
				}
			}

			return BestSq < HalfWidthSq && !bBeyondEnd;
		}
	};

	/** A stone along a route: from S0 to S1 (cm along its rail), across lanes V .. V + H - 1. */
	struct FStone
	{
		double S0 = 0.0;
		double S1 = 0.0;
		int32 V = 0;
		int32 H = 1;
		int32 Pattern = 0;
	};

	/** One way to lay out the plaza for a set of routes into it. */
	struct FPlazaPlan
	{
		int32 NumSides = 0;
		double SideLength = 0.0;

		/** Radians: side 0's normal. */
		double Alpha = 0.0;

		/** Per route into it: its side, and its points cut back to where it turns in. */
		TArray<int32> Sides;
		TArray<TArray<FVector2D>> Points;

		/**
		 * Radians: the furthest a route's way in (the centre out to where it turns in) is off its side's normal, a
		 * route cut back to its bridge counting several times over (it has no room to turn).
		 */
		double WorstAngle = 0.0;

		bool bValid = false;

		/**
		 * Valid first, then the one that turns its worst route in least. Of two that don't fit, the one with fewer
		 * sides: at its smallest a plaza with fewer sides is smaller, so it gets closer to fitting.
		 */
		bool IsBetterThan(const FPlazaPlan& Other) const
		{
			if (bValid != Other.bValid)
			{
				return bValid;
			}

			return bValid ? WorstAngle < Other.WorstAngle - 1.e-6 : NumSides < Other.NumSides;
		}
	};

	/** A regular polygon around the centre tile. Side K faces out along Normals[K]. */
	struct FPlaza
	{
		FVector2D Centre = FVector2D::ZeroVector;
		int32 NumSides = 0;

		/** Radians: side 0's normal. */
		double Alpha = 0.0;

		/** Side length. */
		double Side = 0.0;

		double Apothem = 0.0;
		TArray<FVector2D> Normals;

		bool IsValid() const { return NumSides >= 3; }

		void Init(const FVector2D& InCentre, int32 InNumSides, double InAlpha, double InSide)
		{
			Centre = InCentre;
			NumSides = InNumSides;
			Alpha = InAlpha;
			Side = InSide;
			Apothem = Side / (2.0 * FMath::Tan(UE_DOUBLE_PI / NumSides));
			Normals.Reset(NumSides);

			for (int32 K = 0; K < NumSides; ++K)
			{
				const double Angle = Alpha + UE_DOUBLE_TWO_PI * K / NumSides;
				Normals.Add(FVector2D(FMath::Cos(Angle), FMath::Sin(Angle)));
			}
		}

		/** How far inside the polygon Point is (negative outside). */
		double Depth(const FVector2D& Point) const
		{
			double Result = TNumericLimits<double>::Max();

			for (const FVector2D& Normal : Normals)
			{
				Result = FMath::Min(Result, Apothem - FVector2D::DotProduct(Point - Centre, Normal));
			}

			return Result;
		}

		FVector2D SideMiddle(int32 K) const { return Centre + Normals[K] * Apothem; }

		/** The angle out to the corner between side K and side K + 1. */
		double CornerAngle(int32 K) const { return Alpha + UE_DOUBLE_TWO_PI * K / NumSides + UE_DOUBLE_PI / NumSides; }
	};

	/**
	 * Routes into the plaza -> its sides, keeping their order around it, and the polygon's turn (OutAlpha,
	 * side 0's normal) that bends them least. Every order-keeping assignment is tried; the best turn for one
	 * is the circular mean of its differences. Thetas: the angle from the centre out to each route. Ties go
	 * to the first assignment tried.
	 */
	static void AssignPlazaSides(const TArray<double>& Thetas, int32 NumSides, double& OutAlpha, TArray<int32>& OutSides)
	{
		const int32 NumRoutes = Thetas.Num();
		const double Step = UE_DOUBLE_TWO_PI / NumSides;

		OutAlpha = 0.0;
		OutSides.Init(0, NumRoutes);

		if (NumRoutes == 0 || NumRoutes > NumSides)
		{
			return;
		}

		// Routes by angle (ties by index)
		TArray<int32> Order;

		for (int32 Index = 0; Index < NumRoutes; ++Index)
		{
			Order.Add(Index);
		}

		Order.StableSort([&Thetas](int32 A, int32 B) { return Thetas[A] < Thetas[B]; });

		// Increasing side sequences (one side per route, in angle order), each turned all the way round
		TArray<int32> Sequence;

		for (int32 Index = 0; Index < NumRoutes; ++Index)
		{
			Sequence.Add(Index);
		}

		TArray<double> Diffs;
		Diffs.SetNum(NumRoutes);
		double BestCost = TNumericLimits<double>::Max();

		while (true)
		{
			for (int32 Turn = 0; Turn < NumSides; ++Turn)
			{
				double SumSin = 0.0;
				double SumCos = 0.0;

				for (int32 Index = 0; Index < NumRoutes; ++Index)
				{
					Diffs[Index] = Thetas[Order[Index]] - ((Sequence[Index] + Turn) % NumSides) * Step;
					SumSin += FMath::Sin(Diffs[Index]);
					SumCos += FMath::Cos(Diffs[Index]);
				}

				const double Alpha = FMath::Atan2(SumSin, SumCos);
				double Cost = 0.0;

				for (const double Diff : Diffs)
				{
					Cost += 1.0 - FMath::Cos(Diff - Alpha);
				}

				if (Cost < BestCost - 1.e-6)
				{
					BestCost = Cost;
					OutAlpha = Alpha;

					for (int32 Index = 0; Index < NumRoutes; ++Index)
					{
						OutSides[Order[Index]] = (Sequence[Index] + Turn) % NumSides;
					}
				}
			}

			// The next sequence, in lexicographic order
			int32 Last = NumRoutes - 1;

			while (Last >= 0 && Sequence[Last] == NumSides - NumRoutes + Last)
			{
				--Last;
			}

			if (Last < 0)
			{
				break;
			}

			++Sequence[Last];

			for (int32 Index = Last + 1; Index < NumRoutes; ++Index)
			{
				Sequence[Index] = Sequence[Index - 1] + 1;
			}
		}
	}
}

void AMyHexPlatform::BuildPathPaving(const TArray<TArray<FIntVector>>& Routes, const FIntVector& Centre, TSet<FIntVector>& PathSet, TMap<FIntVector, FVector2D>& PathDirections)
{
	using namespace HexPaving;

	const double CellSize = GetPavingCellSize();
	const int32 CellsAcross = FMath::Max(1, PavingCellsAcross);
	const int32 PatternLength = FMath::Max(1, PavingPatternLength);

	if (CellSize <= UE_KINDA_SMALL_NUMBER || PavingPatterns.IsEmpty())
	{
		return;
	}

	const double Apothem = HexRadius * FMath::Sqrt(3.0) * 0.5;
	const double PathWidth = CellsAcross * CellSize;
	const double HalfWidth = PathWidth * 0.5;
	const double MaxBend = FMath::DegreesToRadians(static_cast<double>(PavingMaxBend));
	const double Lead = PavingPlazaLead * CellSize;

	// Lane ends are searched in steps of ClipStep, on the lane's edges EdgeInset in from the stones' sides.
	// A stone trimmed shorter than MinPiece there is left out.
	const double ClipStep = CellSize * 0.125;
	const double EdgeInset = CellSize * 0.0375;
	const double MinPiece = CellSize * 0.35;

	// Each pattern's stones, clipped to its cells; a stone over cells already taken is skipped
	TArray<TArray<FIntRect>> Patterns;

	for (const FHexPavingPattern& Pattern : PavingPatterns)
	{
		TArray<FIntRect>& Rects = Patterns.AddDefaulted_GetRef();
		TBitArray<> Taken(false, PatternLength * CellsAcross);

		for (const FHexPavingPatternSlab& Slab : Pattern.Slabs)
		{
			const FIntPoint Min(FMath::Max(Slab.Cell.X, 0), FMath::Max(Slab.Cell.Y, 0));
			const FIntPoint Max(FMath::Min(Slab.Cell.X + Slab.Size.X, PatternLength), FMath::Min(Slab.Cell.Y + Slab.Size.Y, CellsAcross));

			if (Max.X <= Min.X || Max.Y <= Min.Y)
			{
				continue;
			}

			bool bOverlaps = false;

			for (int32 X = Min.X; X < Max.X && !bOverlaps; ++X)
			{
				for (int32 Y = Min.Y; Y < Max.Y && !bOverlaps; ++Y)
				{
					bOverlaps = Taken[X * CellsAcross + Y];
				}
			}

			if (bOverlaps)
			{
				continue;
			}

			for (int32 X = Min.X; X < Max.X; ++X)
			{
				for (int32 Y = Min.Y; Y < Max.Y; ++Y)
				{
					Taken[X * CellsAcross + Y] = true;
				}
			}

			Rects.Add(FIntRect(Min, Max));
		}
	}

	auto TileXY = [this](const FIntVector& Coord)
	{
		const FVector& Top = PathLayoutTiles.FindChecked(Coord);
		return FVector2D(Top.X, Top.Y);
	};

	// The tile under a point, looked up a hair along X (never along a hex edge), so a point exactly on an edge
	// or corner doesn't take its tile from rounding noise that can differ between machines
	auto TileAt = [this](const FVector2D& Point)
	{
		return WorldToHex(Point + FVector2D(0.01, 0.0), HexRadius);
	};

	auto TopAt = [this, &TileAt](const FVector2D& Point)
	{
		return PathLayoutTiles.Find(TileAt(Point));
	};

	// Lays a stone of Cells (Size cm, X along Heading in radians) centred on Point. It lands on, and breaks
	// with, the tile under its centre; none there (a notch in the outline, past the edge) = no stone.
	// Curvature: of the path under it (1/cm, positive turning left of Heading), for the material to bend it.
	auto AddSlab = [&](const FVector2D& Point, double Heading, FIntPoint Cells, FVector2D Size, int32 Pattern, uint32 Seed, double Curvature)
	{
		const FIntVector Coord = TileAt(Point);
		const FVector* Top = PathLayoutTiles.Find(Coord);

		if (!Top)
		{
			return;
		}

		// Paved tiles are path tiles: no props on them
		PathSet.Add(Coord);

		if (!PathDirections.Contains(Coord))
		{
			PathDirections.Add(Coord, FVector2D(FMath::Cos(Heading), FMath::Sin(Heading)));
		}

		// Long side first
		FVector2D Bend(Curvature, 0.0);

		if (Cells.Y > Cells.X)
		{
			Swap(Cells.X, Cells.Y);
			Swap(Size.X, Size.Y);
			Heading += UE_DOUBLE_HALF_PI;

			// Turned a quarter: the path runs along the stone's -Y, so a left turn is towards its +X
			Bend = FVector2D(0.0, -Curvature);
		}

		FHexPavingSlab& Slab = PavingSlabs.AddDefaulted_GetRef();
		Slab.Location = FVector(Point.X, Point.Y, Top->Z);
		Slab.Yaw = static_cast<float>(FRotator::NormalizeAxis(FMath::RadiansToDegrees(Heading)));
		Slab.Size = Cells;
		Slab.Scale = FVector2D(Size.X / (Cells.X * CellSize), Size.Y / (Cells.Y * CellSize));
		Slab.Bend = Bend;
		Slab.Tile = Coord;
		Slab.TileIndex = MakeTileIndex(Coord);
		Slab.Pattern = Pattern;
		Slab.Seed = static_cast<int32>(Seed);
	};

	UWorld* World = bDrawPavingDebug || CVarPathPavingDebug.GetValueOnAnyThread() > 0 ? GetWorld() : nullptr;
	const FTransform& ActorTransform = GetActorTransform();

	auto ToWorld = [&](const FVector2D& Point, double Lift)
	{
		const FVector* Top = TopAt(Point);
		return ActorTransform.TransformPosition(FVector(Point, (Top ? Top->Z : 0.0) + Lift));
	};

	auto DrawSlabs = [&](int32 FirstSlab)
	{
		for (int32 Index = FirstSlab; Index < PavingSlabs.Num(); ++Index)
		{
			const FHexPavingSlab& Slab = PavingSlabs[Index];
			const FVector Extent(
				FMath::Max(Slab.Size.X * CellSize * Slab.Scale.X * 0.5 - 1.5, 0.5),
				FMath::Max(Slab.Size.Y * CellSize * Slab.Scale.Y * 0.5 - 1.5, 0.5),
				2.0);
			const FTransform SlabTransform = FTransform(FRotator(0.f, Slab.Yaw, 0.f), Slab.Location + FVector(0.0, 0.0, 10.0)) * ActorTransform;
			DrawDebugBox(World, SlabTransform.GetLocation(), Extent * ActorTransform.GetScale3D(), SlabTransform.GetRotation(), FColor::Orange, false, 30.f, 0, 1.f);
		}
	};

	// Every route's points: out at its bridge side, then the tile centres, with the hex zigzag smoothed out
	TArray<TArray<FVector2D>> RoutePoints;
	RoutePoints.SetNum(Routes.Num());

	// Routes given a run-on point past their last tile (nothing past that tile is paved)
	TBitArray<> RunsOn(false, Routes.Num());

	// Tiles of the routes so far
	TSet<FIntVector> Laid;

	for (int32 RouteIndex = 0; RouteIndex < Routes.Num(); ++RouteIndex)
	{
		const TArray<FIntVector>& Route = Routes[RouteIndex];

		if (Route.IsEmpty())
		{
			continue;
		}

		const FIntVector& Start = Route[0];

		// Out to the bridge: the side the server says its bridge leaves through. Without one (sides not
		// replicated yet), the start tile's open side facing most directly away from the centre.
		FVector2D OutDirection = FVector2D::ZeroVector;
		const int32 StartIndex = PathStartSides.Num() == PathStartTiles.Num() ? PathStartTiles.IndexOfByKey(Start) : INDEX_NONE;

		if (StartIndex != INDEX_NONE && PathStartSides[StartIndex] < 6)
		{
			OutDirection = GetHexSideDirection(PathStartSides[StartIndex]);
		}
		else
		{
			const FVector2D Away = (TileXY(Start) - TileXY(Centre)).GetSafeNormal();
			double BestDot = -TNumericLimits<double>::Max();

			for (int32 Side = 0; Side < 6; ++Side)
			{
				if (PathLayoutTiles.Contains(Start + Directions[Side]))
				{
					continue;
				}

				const FVector2D SideDirection = GetHexSideDirection(Side);
				const double Dot = FVector2D::DotProduct(SideDirection, Away);

				// Near ties go to the lower side on every machine
				if (Dot > BestDot + 1.e-4)
				{
					BestDot = Dot;
					OutDirection = SideDirection;
				}
			}

			if (OutDirection.IsZero())
			{
				OutDirection = Away;
			}
		}

		TArray<FVector2D>& Points = RoutePoints[RouteIndex];

		if (!OutDirection.IsZero())
		{
			Points.Add(TileXY(Start) + OutDirection * Apothem * PavingEdgeReach);
		}

		for (const FIntVector& Coord : Route)
		{
			Points.Add(TileXY(Coord));
		}

		// Joined an earlier route: run on into it (past its middle), so its lanes can end flush against it
		if (Points.Num() >= 2 && Laid.Contains(Route.Last()))
		{
			Points.Add(Points.Last() + (Points.Last() - Points.Last(1)).GetSafeNormal() * (HalfWidth + CellSize));
			RunsOn[RouteIndex] = true;
		}

		Laid.Append(Route);

		// Take out the hex zigzag; both ends stay, no point leaves its tile by more than the max offset
		const TArray<FVector2D> Anchors = Points;
		const double MaxOffset = PavingSmoothMaxOffset * Apothem;

		for (int32 Pass = 0; Pass < PavingSmoothing; ++Pass)
		{
			TArray<FVector2D> Smoothed = Points;

			for (int32 Index = 1; Index < Points.Num() - 1; ++Index)
			{
				const FVector2D Target = Points[Index] + ((Points[Index - 1] + Points[Index + 1]) * 0.5 - Points[Index]) * 0.5;
				FVector2D Offset = Target - Anchors[Index];
				const double OffsetSize = Offset.Size();

				if (OffsetSize > MaxOffset)
				{
					Offset *= MaxOffset / OffsetSize;
				}

				Smoothed[Index] = Anchors[Index] + Offset;
			}

			Points = MoveTemp(Smoothed);
		}
	}

	// The plaza: each route that reaches the centre tile ends square on its own side of a regular polygon
	// around it (a square for up to PavingPlazaMinSides routes), turned so the routes bend least into it. A route
	// that ran into one of those near the plaza gets a side of its own as well, rather than a shared one, unless that
	// leaves a route coming at its side from too far off square (above all one with no room left to turn), or the
	// plaza no longer fits.
	FPlaza Plaza;
	TArray<int32> PlazaSides;
	PlazaSides.Init(INDEX_NONE, Routes.Num());

	if (bPavePlaza)
	{
		const FVector2D CentreXY = TileXY(Centre);
		double NearestStart = TNumericLimits<double>::Max();
		bool bStartOnCentre = false;

		for (const TArray<FIntVector>& Route : Routes)
		{
			if (Route.IsEmpty())
			{
				continue;
			}

			if (Route[0] == Centre)
			{
				bStartOnCentre = true;
			}

			NearestStart = FMath::Min(NearestStart, FVector2D::Distance(TileXY(Route[0]), CentreXY));
		}

		// At least PavingPlazaSideCells a side; on a bigger platform its sides stand PavingPlazaSizeRatio of the way
		// out to the nearest bridge tile
		const double MinSide = FMath::Max(PavingPlazaSideCells * CellSize, PathWidth + CellSize);
		const double WantedApothem = PavingPlazaSizeRatio * NearestStart;

		// The routes into the centre, and the ones that ran into one of them within a tile of where the paths would
		// turn onto a square plaza of that size (with the route they ran into)
		const double JoinReach = FMath::Max(MinSide * 0.5, WantedApothem) + Lead + PavingPlazaTurn * CellSize + Apothem * 2.0;
		TArray<int32> HubRoutes;
		TArray<int32> JoinedRoutes;
		JoinedRoutes.Init(INDEX_NONE, Routes.Num());

		for (int32 RouteIndex = 0; RouteIndex < Routes.Num(); ++RouteIndex)
		{
			const TArray<FIntVector>& Route = Routes[RouteIndex];

			if (Route.Num() < 2)
			{
				continue;
			}

			if (Route.Last() == Centre)
			{
				HubRoutes.Add(RouteIndex);
			}
			else if (RunsOn[RouteIndex] && FVector2D::Distance(TileXY(Route.Last()), CentreXY) <= JoinReach)
			{
				// The earlier route that laid the tile it ran into
				int32 Joined = INDEX_NONE;

				for (int32 Earlier = 0; Earlier < RouteIndex && Joined == INDEX_NONE; ++Earlier)
				{
					if (Routes[Earlier].Contains(Route.Last()))
					{
						Joined = Earlier;
					}
				}

				if (HubRoutes.Contains(Joined))
				{
					JoinedRoutes[RouteIndex] = Joined;
					HubRoutes.Add(RouteIndex);
				}
			}
		}

		if (!HubRoutes.IsEmpty() && !bStartOnCentre)
		{
			// Further off than this, a route comes at its side from beside it and loops round to get in. A route cut back
			// to its bridge has no room to turn, so it hooks in right there much sooner: it counts this many times over.
			constexpr double MaxSideAngle = UE_DOUBLE_PI * 75.0 / 180.0;
			constexpr double ShortRouteAngleScale = 5.0;
			const double MaxCircumradius = NearestStart - Apothem * 1.2;

			// Further off than this, routes bunched up on one side turn in sharply though within bounds: a spare side, which
			// puts the sides closer together, is tried, and taken if it turns them in less by at least this much
			constexpr double SpareSideAngle = UE_DOUBLE_PI * 40.0 / 180.0;
			constexpr double SpareSideGain = UE_DOUBLE_PI * 10.0 / 180.0;

			auto DistanceTo = [](const FVector2D& Point, const TArray<FVector2D>& Line)
			{
				double Best = Line.IsEmpty() ? TNumericLimits<double>::Max() : FVector2D::Distance(Point, Line[0]);

				for (int32 Index = 1; Index < Line.Num(); ++Index)
				{
					const FVector2D Segment = Line[Index] - Line[Index - 1];
					const double T = FMath::Clamp(FVector2D::DotProduct(Point - Line[Index - 1], Segment) / FMath::Max(Segment.SizeSquared(), 1.e-8), 0.0, 1.0);
					Best = FMath::Min(Best, FVector2D::Distance(Point, Line[Index - 1] + Segment * T));
				}

				return Best;
			};

			// The plaza for these routes into it, a side each (at least PavingPlazaMinSides) and as many spare: its size,
			// each route's side, and where each one turns in
			auto PlanPlaza = [&](const TArray<int32>& Hubs, FPlazaPlan& Plan, int32 SpareSides = 0)
			{
				const int32 NumSides = FMath::Max(FMath::Clamp(PavingPlazaMinSides, 4, 8), Hubs.Num()) + SpareSides;
				const double Tan = FMath::Tan(UE_DOUBLE_PI / NumSides);

				// Shrunk (not below the path width plus a cell) so no bridge tile ends up under it, and so a plaza bigger
				// than the smallest stays over the platform's tiles all round
				auto Circumradius = [NumSides](double SideLength) { return SideLength / (2.0 * FMath::Sin(UE_DOUBLE_PI / NumSides)); };

				auto OverTiles = [&](double SideLength)
				{
					constexpr int32 Samples = 24;

					for (int32 Sample = 0; Sample < Samples; ++Sample)
					{
						const double Angle = UE_DOUBLE_TWO_PI * Sample / Samples;

						if (!TopAt(CentreXY + FVector2D(FMath::Cos(Angle), FMath::Sin(Angle)) * Circumradius(SideLength)))
						{
							return false;
						}
					}

					return true;
				};

				double SideLength = FMath::Max(MinSide, 2.0 * Tan * WantedApothem);

				while (SideLength > PathWidth + CellSize && (Circumradius(SideLength) > MaxCircumradius || (SideLength > MinSide && !OverTiles(SideLength))))
				{
					// Not past the smallest side while that fits: below it only so no bridge tile ends up under it
					const double Floor = SideLength > MinSide && Circumradius(MinSide) <= MaxCircumradius ? MinSide : PathWidth + CellSize;
					SideLength = FMath::Max(SideLength - CellSize * 0.5, Floor);
				}

				Plan.NumSides = NumSides;
				Plan.SideLength = SideLength;
				Plan.bValid = Circumradius(SideLength) <= MaxCircumradius;

				if (!Plan.bValid)
				{
					return;
				}

				// Each route is cut back to its last point outside the turning zone; that point picks its side. One that
				// ran into another is cut back further, to where it runs a path's width (and a bit) clear of that one.
				const double Zone = SideLength / (2.0 * Tan) + Lead + PavingPlazaTurn * CellSize;
				TArray<double> Thetas;
				Plan.Points.Reset(Hubs.Num());

				for (const int32 RouteIndex : Hubs)
				{
					TArray<FVector2D>& Points = Plan.Points.Add_GetRef(RoutePoints[RouteIndex]);

					if (RunsOn[RouteIndex])
					{
						Points.Pop(EAllowShrinking::No);
					}

					while (Points.Num() > 1 && FVector2D::Distance(Points.Last(), CentreXY) < Zone)
					{
						Points.Pop(EAllowShrinking::No);
					}

					if (JoinedRoutes[RouteIndex] != INDEX_NONE)
					{
						while (Points.Num() > 1 && DistanceTo(Points.Last(), RoutePoints[JoinedRoutes[RouteIndex]]) < PathWidth + CellSize * 0.5)
						{
							Points.Pop(EAllowShrinking::No);
						}
					}

					const FVector2D Out = Points.Last() - CentreXY;
					Thetas.Add(FMath::Atan2(Out.Y, Out.X));
				}

				AssignPlazaSides(Thetas, NumSides, Plan.Alpha, Plan.Sides);
				Plan.WorstAngle = 0.0;

				for (int32 Index = 0; Index < Hubs.Num(); ++Index)
				{
					const double Scale = Plan.Points[Index].Num() <= 2 ? ShortRouteAngleScale : 1.0;
					const double Normal = Plan.Alpha + UE_DOUBLE_TWO_PI * Plan.Sides[Index] / NumSides;
					Plan.WorstAngle = FMath::Max(Plan.WorstAngle, Scale * FMath::Abs(FMath::UnwindRadians(Thetas[Index] - Normal)));
				}
			};

			FPlazaPlan Plan;
			PlanPlaza(HubRoutes, Plan);

			// While the plaza doesn't fit, or a route comes at its side from too far off square, a route that ran into
			// another runs into it again, with the routes that ran into it (the one whose merging helps most), if that
			// helps; failing that, all of them do
			while (!Plan.bValid || Plan.WorstAngle > MaxSideAngle)
			{
				bool bMerge = false;
				TArray<int32> BetterHubs;
				FPlazaPlan Better;

				for (const int32 Joiner : HubRoutes)
				{
					if (JoinedRoutes[Joiner] == INDEX_NONE)
					{
						continue;
					}

					// A route comes after the one it ran into, so that one is already in Merged if it goes
					TArray<int32> Merged;
					TArray<int32> Fewer;

					for (const int32 RouteIndex : HubRoutes)
					{
						if (RouteIndex == Joiner || Merged.Contains(JoinedRoutes[RouteIndex]))
						{
							Merged.Add(RouteIndex);
						}
						else
						{
							Fewer.Add(RouteIndex);
						}
					}

					FPlazaPlan Candidate;
					PlanPlaza(Fewer, Candidate);

					if (Candidate.IsBetterThan(bMerge ? Better : Plan))
					{
						bMerge = true;
						BetterHubs = MoveTemp(Fewer);
						Better = MoveTemp(Candidate);
					}
				}

				if (!bMerge)
				{
					// No side of their own for any of them, then: the plaza is as it would be without them
					TArray<int32> Hubs;

					for (const int32 RouteIndex : HubRoutes)
					{
						if (JoinedRoutes[RouteIndex] == INDEX_NONE)
						{
							Hubs.Add(RouteIndex);
						}
					}

					if (Hubs.Num() < HubRoutes.Num())
					{
						HubRoutes = MoveTemp(Hubs);
						Plan = FPlazaPlan();
						PlanPlaza(HubRoutes, Plan);
					}

					break;
				}

				HubRoutes = MoveTemp(BetterHubs);
				Plan = MoveTemp(Better);
			}

			// Every side taken, and a route on one of them well off square
			if (Plan.bValid && Plan.NumSides == HubRoutes.Num() && Plan.NumSides < 8 && Plan.WorstAngle > SpareSideAngle && Plan.WorstAngle <= MaxSideAngle)
			{
				FPlazaPlan Spare;
				PlanPlaza(HubRoutes, Spare, 1);

				if (Spare.bValid && Spare.WorstAngle < Plan.WorstAngle - SpareSideGain)
				{
					Plan = MoveTemp(Spare);
				}
			}

			if (Plan.bValid)
			{
				Plaza.Init(CentreXY, Plan.NumSides, Plan.Alpha, Plan.SideLength);

				for (int32 Index = 0; Index < HubRoutes.Num(); ++Index)
				{
					const int32 RouteIndex = HubRoutes[Index];
					RoutePoints[RouteIndex] = MoveTemp(Plan.Points[Index]);
					RunsOn[RouteIndex] = false;
					PlazaSides[RouteIndex] = Plan.Sides[Index];
				}
			}
		}
	}

	// A lane ends where its edges run into the plaza or an earlier route's strip
	TArray<FRail> Rails;
	Rails.Reserve(Routes.Num());

	auto IsBlocked = [&](const FVector2D& Point)
	{
		if (Plaza.IsValid() && Plaza.Depth(Point) > CellSize * 0.025)
		{
			return true;
		}

		for (const FRail& Earlier : Rails)
		{
			if (Earlier.InCorridor(Point, HalfWidth))
			{
				return true;
			}
		}

		return false;
	};

	// The spline through a route's points, sampled into a rail
	auto BuildRail = [&](TArray<FVector2D> Points, int32 PlazaSide, FRail& OutRail)
	{
		FInterpCurveVector Curve;

		if (PlazaSide == INDEX_NONE)
		{
			for (int32 Index = 0; Index < Points.Num(); ++Index)
			{
				const int32 Key = Curve.AddPoint(static_cast<float>(Index), FVector(Points[Index], 0.0));
				Curve.Points[Key].InterpMode = CIM_CurveAuto;
			}

			Curve.AutoSetTangents(0.f, /*bStationaryEndpoints=*/false);
		}
		else
		{
			// Into the plaza: on to a straight lead square onto its side, then the side. Met where the route's
			// own heading would meet it (as far as the side has room for the whole width), so no sideways S-bend.
			const FVector2D Normal = Plaza.Normals[PlazaSide];
			const FVector2D AlongSide(-Normal.Y, Normal.X);
			FVector2D Target = Plaza.SideMiddle(PlazaSide);

			if (Points.Num() >= 2)
			{
				const FVector2D Heading = (Points.Last() - Points.Last(1)).GetSafeNormal();
				const double Facing = -FVector2D::DotProduct(Heading, Normal);

				if (Facing > 0.2)
				{
					const FVector2D Hit = Points.Last() + Heading * ((FVector2D::DotProduct(Points.Last() - Plaza.Centre, Normal) - Plaza.Apothem) / Facing);
					const double Room = FMath::Max(0.0, (Plaza.Side - PathWidth) * 0.5);
					Target += AlongSide * FMath::Clamp(FVector2D::DotProduct(Hit - Target, AlongSide), -Room, Room);
				}
			}

			const int32 NumOwn = Points.Num();
			Points.Add(Target + Normal * Lead);
			Points.Add(Target);

			for (int32 Index = 0; Index < Points.Num(); ++Index)
			{
				const int32 Key = Curve.AddPoint(static_cast<float>(Index), FVector(Points[Index], 0.0));
				Curve.Points[Key].InterpMode = Index < NumOwn - 1 ? CIM_CurveAuto : CIM_CurveBreak;
			}

			Curve.AutoSetTangents(0.f, /*bStationaryEndpoints=*/false);

			// Tangents scaled to each segment, so the turn onto the lead is one smooth curve
			const FVector2D Inward = -Normal;
			const double TurnLength = FVector2D::Distance(Points[NumOwn], Points[NumOwn - 1]);
			FInterpCurvePoint<FVector>& TurnPoint = Curve.Points[NumOwn - 1];
			FInterpCurvePoint<FVector>& LeadStart = Curve.Points[NumOwn];
			FInterpCurvePoint<FVector>& SidePoint = Curve.Points[NumOwn + 1];

			if (NumOwn >= 2)
			{
				const FVector2D Through = ((Points[NumOwn] - Points[NumOwn - 1]).GetSafeNormal() + (Points[NumOwn - 1] - Points[NumOwn - 2]).GetSafeNormal()).GetSafeNormal();
				TurnPoint.ArriveTangent = FVector(Through * FVector2D::Distance(Points[NumOwn - 1], Points[NumOwn - 2]), 0.0);
				TurnPoint.LeaveTangent = FVector(Through * TurnLength, 0.0);
			}
			else
			{
				TurnPoint.ArriveTangent = FVector((Points[NumOwn] - Points[NumOwn - 1]).GetSafeNormal() * TurnLength, 0.0);
				TurnPoint.LeaveTangent = TurnPoint.ArriveTangent;
			}

			LeadStart.ArriveTangent = FVector(Inward * TurnLength, 0.0);
			LeadStart.LeaveTangent = FVector(Inward * Lead, 0.0);
			SidePoint.ArriveTangent = FVector(Inward * Lead, 0.0);
			SidePoint.LeaveTangent = SidePoint.ArriveTangent;
		}

		// Sampled
		constexpr int32 SamplesPerSegment = 24;
		TArray<FVector2D> Samples;
		Samples.Reserve((Points.Num() - 1) * SamplesPerSegment + 1);

		for (int32 Index = 0; Index < Points.Num() - 1; ++Index)
		{
			for (int32 Step = Index == 0 ? 0 : 1; Step <= SamplesPerSegment; ++Step)
			{
				const float Key = static_cast<float>(Index) + static_cast<float>(Step) / SamplesPerSegment;
				Samples.Add(FVector2D(Curve.Eval(Key, FVector::ZeroVector)));
			}
		}

		OutRail.Build(Samples);
	};

	for (int32 RouteIndex = 0; RouteIndex < Routes.Num(); ++RouteIndex)
	{
		const TArray<FIntVector>& Route = Routes[RouteIndex];
		TArray<FVector2D> OwnPoints = RoutePoints[RouteIndex];
		const int32 PlazaSide = PlazaSides[RouteIndex];

		if (Route.IsEmpty() || (OwnPoints.Num() < 2 && PlazaSide == INDEX_NONE))
		{
			continue;
		}

		const FIntVector& Start = Route[0];

		FRail Rail;
		BuildRail(OwnPoints, PlazaSide, Rail);

		// A turn onto the plaza's lead tighter than half the path's width folds the inner lanes, and one not much
		// wider hooks in: start it one point earlier until it's half as wide again (keeping two of the route's own
		// points). Once it's wider than half the width, not at the cost of a fold further back, at the bridge.
		if (PlazaSide != INDEX_NONE)
		{
			const double TailLength = Lead + (PavingPlazaTurn + 2.0) * CellSize;

			while (OwnPoints.Num() > 2 && Rail.IsValid())
			{
				const double TailRadius = Rail.TightestRadius(FMath::Max(0.0, Rail.Length() - TailLength), CellSize * 0.25);

				if (TailRadius >= HalfWidth * 1.5)
				{
					break;
				}

				TArray<FVector2D> ShorterPoints = OwnPoints;
				ShorterPoints.Pop(EAllowShrinking::No);
				FRail ShorterRail;
				BuildRail(ShorterPoints, PlazaSide, ShorterRail);

				if (TailRadius >= HalfWidth && ShorterRail.IsValid()
					&& ShorterRail.TightestRadius(0.0, CellSize * 0.25) < FMath::Min(HalfWidth, Rail.TightestRadius(0.0, CellSize * 0.25)))
				{
					break;
				}

				OwnPoints = MoveTemp(ShorterPoints);
				Rail = MoveTemp(ShorterRail);
			}
		}

		if (!Rail.IsValid())
		{
			continue;
		}

		const double Length = Rail.Length();
		const int32 NumCells = FMath::Max(1, FMath::RoundToInt32(Length / CellSize));
		const double CellAlong = Length / NumCells;

		// Subdivide by bending: whole pattern copies where it runs straight, halves and single cells
		// where it bends, then back onto the copy grid
		TBitArray<> IsCut(false, NumCells + 1);
		IsCut[0] = true;

		for (int32 Cell = 0; Cell < NumCells;)
		{
			int32 Piece = 1;

			for (int32 Candidate = FMath::Min(PatternLength - Cell % PatternLength, NumCells - Cell); Candidate > 1; Candidate /= 2)
			{
				if (Rail.Turning(Cell * CellAlong, (Cell + Candidate) * CellAlong) <= MaxBend)
				{
					Piece = Candidate;
					break;
				}
			}

			Cell += Piece;
			IsCut[Cell] = true;
		}

		// Pattern copies along the route; each picks a pattern and maybe mirrors it across the path. A stone
		// that crosses a cut is split there, so the stones follow the bend.
		const uint32 RouteSeed = Hash(static_cast<uint32>(MakeTileIndex(Start)), static_cast<uint32>(RouteIndex));
		TArray<FStone> Stones;

		for (int32 Copy = 0; Copy * PatternLength < NumCells; ++Copy)
		{
			const uint32 CopySeed = Hash(RouteSeed, static_cast<uint32>(Copy));
			const int32 PatternIndex = static_cast<int32>(CopySeed % static_cast<uint32>(Patterns.Num()));
			const bool bMirror = ((CopySeed >> 8) & 1u) != 0;

			for (const FIntRect& Rect : Patterns[PatternIndex])
			{
				const int32 U = Copy * PatternLength + Rect.Min.X;

				if (U >= NumCells)
				{
					continue;
				}

				const int32 End = FMath::Min(U + Rect.Width(), NumCells);
				int32 From = U;

				for (int32 To = U + 1; To <= End; ++To)
				{
					if (To == End || IsCut[To])
					{
						FStone& Stone = Stones.AddDefaulted_GetRef();
						Stone.S0 = From * CellAlong;
						Stone.S1 = To * CellAlong;
						Stone.V = bMirror ? CellsAcross - Rect.Max.Y : Rect.Min.Y;
						Stone.H = Rect.Height();
						Stone.Pattern = PatternIndex;
						From = To;
					}
				}
			}
		}

		// Each lane ends where its edges first enter an earlier route's strip or the plaza: halfway between
		// where its two edges enter (a slanted meeting leaves as much overlap as gap at the corners), at most
		// half a cell past the first. A lane whose edge starts inside an earlier route's strip (a route that
		// leaves right beside another) starts where it comes out the same way, if it then runs clear for a
		// cell before any run-on; otherwise it is left out.
		TArray<double> LaneStarts;
		TArray<double> LaneEnds;
		LaneStarts.Init(0.0, CellsAcross);
		LaneEnds.Init(Length, CellsAcross);

		if (Plaza.IsValid() || !Rails.IsEmpty())
		{
			// Where an edge, from From on, first becomes blocked (bBlocked) or clear again (!bBlocked), narrowed
			// down between samples: the last clear point before, or the first clear point after. Length if never.
			auto FindChange = [&](double Offset, double From, bool bBlocked)
			{
				double Previous = From;

				for (int32 Step = 1; ; ++Step)
				{
					const double S = FMath::Min(From + Step * ClipStep, Length);

					if (IsBlocked(Rail.At(S, Offset)) == bBlocked)
					{
						double Lo = Previous;
						double Hi = S;

						for (int32 Bisect = 0; Bisect < 8; ++Bisect)
						{
							const double Mid = (Lo + Hi) * 0.5;

							if (IsBlocked(Rail.At(Mid, Offset)) == bBlocked)
							{
								Hi = Mid;
							}
							else
							{
								Lo = Mid;
							}
						}

						return bBlocked ? Lo : Hi;
					}

					if (S >= Length)
					{
						return Length;
					}

					Previous = S;
				}
			};

			const double LastStart = RunsOn[RouteIndex] ? Length - (HalfWidth + CellSize) : Length;

			for (int32 Lane = 0; Lane < CellsAcross; ++Lane)
			{
				const double EdgeOffsets[2] =
				{
					(Lane - CellsAcross * 0.5) * CellSize + EdgeInset,
					(Lane + 1 - CellsAcross * 0.5) * CellSize - EdgeInset
				};

				double Exits[2] = { 0.0, 0.0 };
				double Entries[2] = { Length, Length };

				for (int32 Edge = 0; Edge < 2; ++Edge)
				{
					if (!IsBlocked(Rail.At(0.0, EdgeOffsets[Edge])))
					{
						Entries[Edge] = FindChange(EdgeOffsets[Edge], 0.0, true);
						continue;
					}

					Exits[Edge] = FindChange(EdgeOffsets[Edge], 0.0, false);
					Entries[Edge] = Exits[Edge] < Length ? FindChange(EdgeOffsets[Edge], Exits[Edge], true) : Length;

					if (FMath::Min(Entries[Edge], LastStart) - Exits[Edge] < CellSize)
					{
						Exits[Edge] = 0.0;
						Entries[Edge] = 0.0;
					}
				}

				const double FirstEntry = FMath::Min(Entries[0], Entries[1]);
				const double SecondEntry = FMath::Max(Entries[0], Entries[1]);
				LaneEnds[Lane] = FMath::Min((FirstEntry + SecondEntry) * 0.5, FirstEntry + CellSize * 0.5);

				const double FirstExit = FMath::Min(Exits[0], Exits[1]);
				const double LastExit = FMath::Max(Exits[0], Exits[1]);
				LaneStarts[Lane] = FMath::Max((FirstExit + LastExit) * 0.5, LastExit - CellSize * 0.5);
			}
		}

		// Stones before a lane's start or past its end: each of their lanes keeps its own piece between the
		// two, if long enough
		TArray<FStone> Clipped;
		Clipped.Reserve(Stones.Num());

		for (const FStone& Stone : Stones)
		{
			double StoneStart = 0.0;
			double StoneEnd = Length;

			for (int32 Lane = Stone.V; Lane < Stone.V + Stone.H; ++Lane)
			{
				StoneStart = FMath::Max(StoneStart, LaneStarts[Lane]);
				StoneEnd = FMath::Min(StoneEnd, LaneEnds[Lane]);
			}

			if (Stone.S0 >= StoneStart - 1.e-6 && Stone.S1 <= StoneEnd + 1.e-6)
			{
				Clipped.Add(Stone);
				continue;
			}

			for (int32 Lane = Stone.V; Lane < Stone.V + Stone.H; ++Lane)
			{
				const double PieceStart = FMath::Max(Stone.S0, LaneStarts[Lane]);
				const double PieceEnd = FMath::Min(Stone.S1, LaneEnds[Lane]);

				if (PieceEnd - PieceStart >= MinPiece)
				{
					FStone& Piece = Clipped.Add_GetRef(Stone);
					Piece.S0 = PieceStart;
					Piece.S1 = PieceEnd;
					Piece.V = Lane;
					Piece.H = 1;
				}
			}
		}

		// Whole cells along a stone (at least one)
		auto CellsAlong = [CellAlong](const FStone& Stone)
		{
			return FMath::Max(1, FMath::RoundToInt32((Stone.S1 - Stone.S0) / CellAlong));
		};

		// Every cell of the stone (and its centre) over a tile, all on one height
		auto IsLevel = [&](const FStone& Stone)
		{
			double MinZ = TNumericLimits<double>::Max();
			double MaxZ = -TNumericLimits<double>::Max();

			auto Sample = [&](double S, double Offset)
			{
				const FVector* Top = TopAt(Rail.At(S, Offset));

				if (!Top)
				{
					return false;
				}

				MinZ = FMath::Min(MinZ, Top->Z);
				MaxZ = FMath::Max(MaxZ, Top->Z);
				return true;
			};

			const int32 Along = CellsAlong(Stone);

			for (int32 Step = 0; Step < Along; ++Step)
			{
				const double S = Stone.S0 + (Step + 0.5) * (Stone.S1 - Stone.S0) / Along;

				for (int32 Lane = Stone.V; Lane < Stone.V + Stone.H; ++Lane)
				{
					if (!Sample(S, (Lane + 0.5 - CellsAcross * 0.5) * CellSize))
					{
						return false;
					}
				}
			}

			if (!Sample((Stone.S0 + Stone.S1) * 0.5, (Stone.V + Stone.H * 0.5 - CellsAcross * 0.5) * CellSize))
			{
				return false;
			}

			return MaxZ - MinZ <= PavingStepSplitHeight;
		};

		// Big stones over a step are halved (along the path, on whole cells, or across it, whichever leaves
		// more halves on one height) until every piece sits on one height
		TArray<FStone> Fitted;
		TArray<FStone> Stack;

		for (int32 Index = Clipped.Num() - 1; Index >= 0; --Index)
		{
			Stack.Push(Clipped[Index]);
		}

		while (!Stack.IsEmpty())
		{
			const FStone Stone = Stack.Pop(EAllowShrinking::No);
			const int32 WholeCells = FMath::RoundToInt32((Stone.S1 - Stone.S0) / CellAlong);

			if ((WholeCells <= 1 && Stone.H == 1) || IsLevel(Stone))
			{
				Fitted.Add(Stone);
				continue;
			}

			FStone Along[2] = { Stone, Stone };
			int32 AlongLevel = -1;

			if (WholeCells >= 2)
			{
				Along[0].S1 = Along[1].S0 = Stone.S0 + (WholeCells / 2) * CellAlong;
				AlongLevel = static_cast<int32>(IsLevel(Along[0])) + static_cast<int32>(IsLevel(Along[1]));
			}

			FStone Across[2] = { Stone, Stone };
			int32 AcrossLevel = -1;

			if (Stone.H > 1)
			{
				Across[0].H = Stone.H / 2;
				Across[1].V = Stone.V + Stone.H / 2;
				Across[1].H = Stone.H - Stone.H / 2;
				AcrossLevel = static_cast<int32>(IsLevel(Across[0])) + static_cast<int32>(IsLevel(Across[1]));
			}

			const FStone* Halves = AlongLevel >= AcrossLevel ? Along : Across;

			Stack.Push(Halves[1]);
			Stack.Push(Halves[0]);
		}

		// Lay them: each stone spans its own lane's stretch of the curve, from where its lane crosses its
		// start to where it crosses its end, so on a bend the outer lanes get longer stones and they still meet.
		// Where a turn is sharp for a lane, a stretch half again as long as the stone or more is laid as that
		// many stones, and one squeezed to under MinSqueeze of its length, or folded back, is left out.
		// On a bend the paving material bends each stone into its stretch (Bend), so its ends land where its
		// lane crosses its start and end, and the joints stay even.
		constexpr double MinSqueeze = 0.35;
		const int32 FirstSlab = PavingSlabs.Num();
		TArray<double> Cuts;
		TArray<double> LaneLengths;

		for (const FStone& Stone : Fitted)
		{
			const double Offset = (Stone.V + Stone.H * 0.5 - CellsAcross * 0.5) * CellSize;
			const FIntPoint Cells(CellsAlong(Stone), Stone.H);
			const uint32 StoneSeed = Hash(RouteSeed, Hash(static_cast<uint32>(FMath::RoundToInt32(Stone.S0 / CellAlong)), static_cast<uint32>(Stone.V)));
			const double Reach = FVector2D::Distance(Rail.At(Stone.S0, Offset), Rail.At(Stone.S1, Offset));
			const int32 Parts = FMath::Max(1, FMath::RoundToInt32(Reach / (Cells.X * CellSize)));

			// Where the parts meet: evenly along the lane's own curve, so they share the turn's stretch
			Cuts.Reset();
			Cuts.Add(Stone.S0);

			if (Parts > 1)
			{
				const int32 Samples = Parts * 8;
				FVector2D Previous = Rail.At(Stone.S0, Offset);
				LaneLengths.Reset();
				LaneLengths.Add(0.0);

				for (int32 Index = 1; Index <= Samples; ++Index)
				{
					const FVector2D Point = Rail.At(FMath::Lerp(Stone.S0, Stone.S1, static_cast<double>(Index) / Samples), Offset);
					LaneLengths.Add(LaneLengths.Last() + FVector2D::Distance(Previous, Point));
					Previous = Point;
				}

				for (int32 Part = 1, Index = 1; Part < Parts; ++Part)
				{
					const double Target = LaneLengths.Last() * Part / Parts;

					while (Index < Samples && LaneLengths[Index] < Target)
					{
						++Index;
					}

					const double Span = LaneLengths[Index] - LaneLengths[Index - 1];
					const double T = Span > 1.e-9 ? (Target - LaneLengths[Index - 1]) / Span : 0.0;
					Cuts.Add(FMath::Lerp(Stone.S0, Stone.S1, (Index - 1 + T) / Samples));
				}
			}

			Cuts.Add(Stone.S1);

			for (int32 Part = 0; Part < Parts; ++Part)
			{
				const double S0 = Cuts[Part];
				const double S1 = Cuts[Part + 1];
				const FVector2D From = Rail.At(S0, Offset);
				const FVector2D To = Rail.At(S1, Offset);
				const FVector2D Chord = To - From;

				FVector2D Middle;
				double Heading;
				Rail.Eval((S0 + S1) * 0.5, Middle, Heading);

				const double ChordLength = Chord.Size();

				if (ChordLength < (S1 - S0) * MinSqueeze || FVector2D::DotProduct(Chord, FVector2D(FMath::Cos(Heading), FMath::Sin(Heading))) <= 0.0)
				{
					continue;
				}

				// The lane's curvature over the stretch (a circle through both ends, turning as the rail does),
				// held to where the stone's inner side keeps a fifth of its length
				FVector2D Unused;
				double HeadingFrom;
				double HeadingTo;
				Rail.Eval(S0, Unused, HeadingFrom);
				Rail.Eval(S1, Unused, HeadingTo);
				const double MaxCurvature = 1.6 / (Stone.H * CellSize);
				const double Curvature = FMath::Clamp(2.0 * FMath::Sin((HeadingTo - HeadingFrom) * 0.5) / ChordLength, -MaxCurvature, MaxCurvature);

				// Bent, the stone's ends come a sagitta (Curvature * ChordLength^2 / 8) to its left, so its pivot goes that
				// far to the right of the chord's middle and its ends land on From and To
				const FVector2D Pivot = (From + To) * 0.5 - FVector2D(-Chord.Y, Chord.X) * (Curvature * ChordLength * 0.125);
				const uint32 Seed = Part == 0 ? StoneSeed : Hash(StoneSeed, static_cast<uint32>(Part));
				AddSlab(Pivot, FMath::Atan2(Chord.Y, Chord.X), Cells, FVector2D(ChordLength, Stone.H * CellSize), Stone.Pattern, Seed, Curvature);
			}
		}

		if (World)
		{
			for (int32 Index = 1; Index < Rail.Points.Num(); ++Index)
			{
				DrawDebugLine(World, ToWorld(Rail.Points[Index - 1], 25.0), ToWorld(Rail.Points[Index], 25.0), FColor::Red, false, 30.f, 0, 2.f);
			}

			for (int32 Cell = 0; Cell <= NumCells; ++Cell)
			{
				if (IsCut[Cell])
				{
					DrawDebugLine(World, ToWorld(Rail.At(Cell * CellAlong, -HalfWidth * 1.15), 25.0), ToWorld(Rail.At(Cell * CellAlong, HalfWidth * 1.15), 25.0), FColor::Cyan, false, 30.f, 0, 1.5f);
				}
			}

			// Where each lane was cut short, at either end
			for (int32 Lane = 0; Lane < CellsAcross; ++Lane)
			{
				const double Offset = (Lane - CellsAcross * 0.5) * CellSize;

				if (LaneStarts[Lane] > 0.0)
				{
					DrawDebugLine(World, ToWorld(Rail.At(LaneStarts[Lane], Offset), 30.0), ToWorld(Rail.At(LaneStarts[Lane], Offset + CellSize), 30.0), FColor::Magenta, false, 30.f, 0, 2.f);
				}

				if (LaneEnds[Lane] < Length)
				{
					DrawDebugLine(World, ToWorld(Rail.At(LaneEnds[Lane], Offset), 30.0), ToWorld(Rail.At(LaneEnds[Lane], Offset + CellSize), 30.0), FColor::Magenta, false, 30.f, 0, 2.f);
				}
			}

			DrawSlabs(FirstSlab);
		}

		Rails.Add(MoveTemp(Rail));
	}

	// The plaza's own stones: rings of one-cell-deep courses along the sides, outside in, then a plinth for
	// the lamp in the middle. A square's courses each own the corner cell at their start (a pinwheel), so
	// every stone is whole. Other polygons' courses stop where their inner corner meets the mitre, stretched
	// evenly to fill their side, and the kite left at each corner of each ring gets a small diamond keystone.
	if (Plaza.IsValid())
	{
		const int32 FirstSlab = PavingSlabs.Num();
		const uint32 PlazaSeed = Hash(static_cast<uint32>(MakeTileIndex(Centre)), static_cast<uint32>(Plaza.NumSides));
		const bool bSquare = Plaza.NumSides == 4;
		const double HalfAngle = UE_DOUBLE_PI / Plaza.NumSides;
		const double Tan = FMath::Tan(HalfAngle);

		// Rings until an inner polygon with an apothem of half a cell to a cell and a half is left for the plinth
		const int32 Rings = FMath::Max(0, FMath::RoundToInt32((Plaza.Apothem - CellSize) / CellSize));

		// Every corner kite is the same: its inscribed circle, and how far out from the ring's inner corner it sits
		const double KiteRadius = CellSize * Tan / (1.0 + Tan);
		const double KiteFromInnerCorner = KiteRadius / FMath::Sin(HalfAngle);
		uint32 PlazaStone = 0;

		auto AddPlazaStone = [&](const FVector2D& Point, double Heading, const FIntPoint& Cells, const FVector2D& Size, int32 Pattern)
		{
			AddSlab(Point, Heading, Cells, Size, Pattern % Patterns.Num(), Hash(PlazaSeed, PlazaStone++), 0.0);
		};

		for (int32 Ring = 0; Ring < Rings; ++Ring)
		{
			// Side length of this ring's outer edge
			const double RingSide = Plaza.Side - 2.0 * Ring * CellSize * Tan;

			for (int32 K = 0; K < Plaza.NumSides; ++K)
			{
				const FVector2D& Normal = Plaza.Normals[K];
				const FVector2D AlongSide(-Normal.Y, Normal.X);
				const double Heading = FMath::Atan2(AlongSide.Y, AlongSide.X);
				const FVector2D CourseMiddle = Plaza.Centre + Normal * (Plaza.Apothem - (Ring + 0.5) * CellSize);
				const double CourseLength = bSquare ? RingSide - CellSize : RingSide - 2.0 * CellSize * Tan;

				if (CourseLength >= CellSize * 0.35)
				{
					const int32 Cells = FMath::Max(1, FMath::RoundToInt32(CourseLength / CellSize));
					const double Stretch = CourseLength / (Cells * CellSize);

					// 2-cell and 1-cell stones, picked by hash so the rings differ
					const uint32 CourseHash = Hash(PlazaSeed, Hash(static_cast<uint32>(Ring), static_cast<uint32>(K)));
					double Position = bSquare ? -RingSide * 0.5 : -CourseLength * 0.5;

					for (int32 Left = Cells, Run = 0; Left > 0; ++Run)
					{
						const int32 Width = Left >= 2 && ((CourseHash >> (Run % 16)) & 3u) != 0 ? 2 : 1;
						const double StoneLength = Width * CellSize * Stretch;
						const FVector2D Point = CourseMiddle + AlongSide * (Position + StoneLength * 0.5);

						Left -= Width;
						Position += StoneLength;

						// A 2-cell stone over a step (or off the platform at one end) is halved
						if (Width == 2)
						{
							const FVector2D Quarter = AlongSide * (StoneLength * 0.25);
							const FVector* TopA = TopAt(Point - Quarter);
							const FVector* TopB = TopAt(Point + Quarter);

							if (!TopA || !TopB || FMath::Abs(TopA->Z - TopB->Z) > PavingStepSplitHeight)
							{
								AddPlazaStone(Point - Quarter, Heading, FIntPoint(1, 1), FVector2D(StoneLength * 0.5, CellSize), Ring);
								AddPlazaStone(Point + Quarter, Heading, FIntPoint(1, 1), FVector2D(StoneLength * 0.5, CellSize), Ring);
								continue;
							}
						}

						AddPlazaStone(Point, Heading, FIntPoint(Width, 1), FVector2D(StoneLength, CellSize), Ring);
					}
				}

				if (!bSquare)
				{
					// Keystone in the kite at this course's counter-clockwise end
					const double CornerAngle = Plaza.CornerAngle(K);
					const double InnerCorner = (Plaza.Apothem - (Ring + 1) * CellSize) / FMath::Cos(HalfAngle);
					const FVector2D Point = Plaza.Centre + FVector2D(FMath::Cos(CornerAngle), FMath::Sin(CornerAngle)) * (InnerCorner + KiteFromInnerCorner);
					const double KeySide = KiteRadius * UE_DOUBLE_SQRT_2;

					AddPlazaStone(Point, CornerAngle + UE_DOUBLE_PI * 0.25, FIntPoint(1, 1), FVector2D(KeySide, KeySide), 2);
				}
			}
		}

		// The plinth under the lamp: the biggest square (turned with side 0) inside the inner polygon left. A square
		// plaza's fills it; other polygons' are at most 2 x 2 cells.
		const double InnerApothem = Plaza.Apothem - Rings * CellSize;
		const double PlinthHeading = Plaza.Alpha + UE_DOUBLE_HALF_PI;
		const FVector2D PlinthX(FMath::Cos(PlinthHeading), FMath::Sin(PlinthHeading));
		const FVector2D PlinthY(-PlinthX.Y, PlinthX.X);
		double PlinthHalf = TNumericLimits<double>::Max();

		for (const FVector2D& Normal : Plaza.Normals)
		{
			PlinthHalf = FMath::Min(PlinthHalf, InnerApothem / (FMath::Abs(FVector2D::DotProduct(Normal, PlinthX)) + FMath::Abs(FVector2D::DotProduct(Normal, PlinthY))));
		}

		const double Plinth = bSquare ? 2.0 * PlinthHalf : FMath::Min(2.0 * CellSize, 2.0 * PlinthHalf);
		AddPlazaStone(Plaza.Centre, PlinthHeading, FIntPoint(2, 2), FVector2D(Plinth, Plinth), 0);

		PathPlaza.bValid = true;
		PathPlaza.Centre = FVector(Plaza.Centre, PathLayoutTiles.FindChecked(Centre).Z);
		PathPlaza.Yaw = static_cast<float>(FRotator::NormalizeAxis(FMath::RadiansToDegrees(Plaza.Alpha)));
		PathPlaza.NumSides = Plaza.NumSides;
		PathPlaza.SideLength = static_cast<float>(Plaza.Side);
		PathPlaza.Tile = Centre;
		PathPlaza.TileIndex = MakeTileIndex(Centre);

		if (World)
		{
			const double Circumradius = Plaza.Apothem / FMath::Cos(HalfAngle);

			for (int32 K = 0; K < Plaza.NumSides; ++K)
			{
				const double From = Plaza.CornerAngle(K);
				const double To = Plaza.CornerAngle(K + 1);
				DrawDebugLine(World, ToWorld(Plaza.Centre + FVector2D(FMath::Cos(From), FMath::Sin(From)) * Circumradius, 25.0),
					ToWorld(Plaza.Centre + FVector2D(FMath::Cos(To), FMath::Sin(To)) * Circumradius, 25.0), FColor::Yellow, false, 30.f, 0, 2.f);
			}

			DrawSlabs(FirstSlab);
		}
	}

	UE_LOG(LogTemp, Verbose, TEXT("%s: %d paving stones on %d routes, %d-sided plaza"), *GetName(), PavingSlabs.Num(), Routes.Num(), Plaza.NumSides);
}

void AMyHexPlatform::GenerateTileProps()
{
	UpdateTileFootprint();
	GenerateAtmosphere();

	if (!bSpawnTileProps)
	{
		return;
	}

	// Tiles that fell before this client got the platform: no props on them
	for (const FIntVector& Coord : LocalActivatedTiles)
	{
		TileInfos.Remove(Coord);
	}

	bTilePropsGenerated = true;

	for (UPCGComponent* PropsPCG : { TilePropsPCG.Get(), HexTileProps2.Get() })
	{
		if (!PropsPCG || !PropsPCG->GetGraph())
		{
			continue;
		}

		PropsPCG->OnPCGGraphGeneratedDelegate.RemoveAll(this);
		PropsPCG->OnPCGGraphGeneratedDelegate.AddUObject(this, &ThisClass::OnTilePropsGenerated);

		PropsPCG->GenerateLocal(/*bForce=*/true);
	}
}

void AMyHexPlatform::UpdateTileFootprint()
{
	TileFootprintRadius = 0.f;
	TileFootprintCount = 0;
	TileFootprintCenter = GetActorLocation();

	const int32 Count = HexPillarsISM ? HexPillarsISM->GetInstanceCount() : 0;

	if (Count == 0)
	{
		return;
	}

	TArray<FVector> Centres;
	Centres.Reserve(Count);
	FVector2D Sum = FVector2D::ZeroVector;

	for (int32 Index = 0; Index < Count; ++Index)
	{
		FTransform Transform;

		if (HexPillarsISM->GetInstanceTransform(Index, Transform, /*bWorldSpace=*/true))
		{
			Centres.Add(Transform.GetLocation());
			Sum += FVector2D(Transform.GetLocation());
		}
	}

	if (Centres.IsEmpty())
	{
		return;
	}

	const FVector2D Centre = Sum / Centres.Num();
	double MaxDistance = 0.0;

	for (const FVector& Location : Centres)
	{
		MaxDistance = FMath::Max(MaxDistance, FVector2D::Distance(Centre, FVector2D(Location)));
	}

	TileFootprintCount = Centres.Num();
	TileFootprintRadius = static_cast<float>(MaxDistance) + HexRadius;
	TileFootprintCenter = FVector(Centre, HexPillarsISM->Bounds.GetBox().Max.Z);
}

void AMyHexPlatform::GenerateAtmosphere()
{
	if (!AtmospherePCG || GetNetMode() == NM_DedicatedServer)
	{
		return;
	}

	const FMyHexAtmosphereVariant* Atmosphere = AMyHexPathSpawner::FindActiveAtmosphere(this);
	UPCGGraphInterface* Graph = Atmosphere ? Atmosphere->PlatformGraph.Get() : nullptr;

	if (!Graph)
	{
		// The active variant has no platform graph (or there is no variant): clear what an earlier one spawned
		if (AtmospherePCG->bGenerated)
		{
			AtmospherePCG->CleanupLocal(/*bRemoveComponents=*/true);
		}

		return;
	}

	// SetGraphLocal does a structural refresh of the component, so only set the graph when the variant changed it
	if (AtmosphereGraphSet.Get() != Graph)
	{
		AtmospherePCG->SetGraphLocal(Graph);
		AtmosphereGraphSet = Graph;
	}

	AtmospherePCG->GenerateLocal(/*bForce=*/true);
}

void AMyHexPlatform::OnTilePropsGenerated(UPCGComponent* InComponent)
{
	if (!InComponent)
	{
		return;
	}

	// This component's prop ISMs. The other component's entries in TilePropISMs stay.
	TArray<UInstancedStaticMeshComponent*> ComponentISMs;

	InComponent->ForEachManagedResource([this, &ComponentISMs](UPCGManagedResource* Resource)
	{
		const UPCGManagedISMComponent* ManagedISM = Cast<UPCGManagedISMComponent>(Resource);
		UInstancedStaticMeshComponent* ISM = ManagedISM ? ManagedISM->GetComponent() : nullptr;

		if (ISM && ISM != HexPillarsISM && ISM->NumCustomDataFloats > PropTileIndexCustomDataSlot)
		{
			ComponentISMs.Add(ISM);
		}
	});

	if (PropMaxDrawDistance > 0.f)
	{
		for (UInstancedStaticMeshComponent* ISM : ComponentISMs)
		{
			ISM->SetCullDistance(PropMaxDrawDistance);
		}
	}

	// Drop what an earlier generation of this component left (and anything destroyed)
	for (auto It = TilePropISMs.CreateIterator(); It; ++It)
	{
		It.Value().RemoveAll([&ComponentISMs](const TWeakObjectPtr<UInstancedStaticMeshComponent>& WeakISM)
		{
			return !WeakISM.IsValid() || ComponentISMs.Contains(WeakISM.Get());
		});

		if (It.Value().IsEmpty())
		{
			It.RemoveCurrent();
		}
	}

	TSet<int32> PropTiles;

	for (UInstancedStaticMeshComponent* ISM : ComponentISMs)
	{
		const int32 NumFloats = ISM->NumCustomDataFloats;
		const int32 Count = ISM->GetInstanceCount();

		for (int32 Instance = 0; Instance < Count; ++Instance)
		{
			const int32 DataIndex = Instance * NumFloats + PropTileIndexCustomDataSlot;

			if (!ISM->PerInstanceSMCustomData.IsValidIndex(DataIndex))
			{
				break;
			}

			const int32 TileIndex = FMath::RoundToInt(ISM->PerInstanceSMCustomData[DataIndex]);

			TilePropISMs.FindOrAdd(TileIndex).AddUnique(ISM);
			PropTiles.Add(TileIndex);
		}
	}

	// Tiles that collapsed while the graph was running
	for (const FIntVector& Coord : LocalActivatedTiles)
	{
		BreakTileProps(MakeTileIndex(Coord), EHexPropBreakMode::RemoveOnly);
	}

	UE_LOG(LogTemp, Verbose, TEXT("%s: %s props on %d tiles"), *GetName(), *InComponent->GetName(), PropTiles.Num());
}

void AMyHexPlatform::HandleTileActivated(AMyHexPlatform* Platform, const FIntVector& Coord)
{
	TileInfos.Remove(Coord);

	// The first tile to fall freezes the props: drop any pending regeneration
	if (bTilePropsGenerated)
	{
		GetWorldTimerManager().ClearTimer(TilePropsTimerHandle);
	}

	// Debris is cosmetic: none on a dedicated server (no local player). Far from the local player, the baked
	// far breaks, unless the props are already culled there.
	const bool bPropsDrawn = PropMaxDrawDistance <= 0.f || BreakingTileDistance <= PropMaxDrawDistance;
	const EHexPropBreakMode Mode = bBreakingTileInEffectsRange ? EHexPropBreakMode::Near
		: bBreakingTileFar && bPropsDrawn ? EHexPropBreakMode::Far : EHexPropBreakMode::RemoveOnly;

	BreakTileProps(MakeTileIndex(Coord), Mode);
}

bool AMyHexPlatform::GetLocalPlayerDistance2D(FVector WorldLoc, double& OutDistance) const
{
	const UWorld* World = GetWorld();

	if (!World)
	{
		return false;
	}

	for (FConstPlayerControllerIterator It = World->GetPlayerControllerIterator(); It; ++It)
	{
		const APlayerController* PC = It->Get();

		if (!PC || !PC->IsLocalController())
		{
			continue;
		}

		FVector ViewLoc;

		if (const APawn* Pawn = PC->GetPawn())
		{
			ViewLoc = Pawn->GetActorLocation();
		}
		else if (PC->PlayerCameraManager)
		{
			ViewLoc = PC->PlayerCameraManager->GetCameraLocation();
		}
		else
		{
			continue;
		}

		OutDistance = FVector::Dist2D(ViewLoc, WorldLoc);
		return true;
	}

	return false;
}

void AMyHexPlatform::BreakTileProps(int32 TileIndex, EHexPropBreakMode Mode)
{
	TArray<TWeakObjectPtr<UInstancedStaticMeshComponent>> ISMs;

	if (!TilePropISMs.RemoveAndCopyValue(TileIndex, ISMs))
	{
		return;
	}

	for (const TWeakObjectPtr<UInstancedStaticMeshComponent>& WeakISM : ISMs)
	{
		UInstancedStaticMeshComponent* ISM = WeakISM.Get();

		if (!ISM || ISM->NumCustomDataFloats <= PropTileIndexCustomDataSlot)
		{
			continue;
		}

		// Instance indices shift as others are removed, so find this tile's by their custom data
		const int32 NumFloats = ISM->NumCustomDataFloats;
		TArray<int32> ToRemove;

		for (int32 Instance = ISM->GetInstanceCount() - 1; Instance >= 0; --Instance)
		{
			const int32 DataIndex = Instance * NumFloats + PropTileIndexCustomDataSlot;

			if (ISM->PerInstanceSMCustomData.IsValidIndex(DataIndex)
				&& FMath::RoundToInt(ISM->PerInstanceSMCustomData[DataIndex]) == TileIndex)
			{
				ToRemove.Add(Instance);
			}
		}

		if (ToRemove.IsEmpty())
		{
			continue;
		}

		if (Mode == EHexPropBreakMode::Far)
		{
			if (const FHexFarBreakMesh* Far = FarPropMeshes.Find(ISM->GetStaticMesh()))
			{
				for (const int32 Instance : ToRemove)
				{
					FTransform WorldTransform;

					if (ISM->GetInstanceTransform(Instance, WorldTransform, /*bWorldSpace=*/true))
					{
						float Speed = FMath::FRandRange(FarPropSpeedRange.X, FarPropSpeedRange.Y);

						// Fall distance scales with the instance, so play 1 / sqrt(scale) times as fast for true gravity
						if (bFarPropSpeedFromScale)
						{
							const float ScaleZ = FMath::Max(FMath::Abs(static_cast<float>(WorldTransform.GetScale3D().Z)), UE_KINDA_SMALL_NUMBER);
							Speed *= FMath::Clamp(1.f / FMath::Sqrt(ScaleZ), 0.25f, 4.f);
						}

						PlayFarBreak(*Far, WorldTransform, Speed);
					}
				}
			}
		}
		else if (Mode == EHexPropBreakMode::Near)
		{
			const TObjectPtr<UGeometryCollection>* Collection = PropBreakables.Find(ISM->GetStaticMesh());

			if (Collection && *Collection)
			{
				for (const int32 Instance : ToRemove)
				{
					FTransform WorldTransform;

					if (ISM->GetInstanceTransform(Instance, WorldTransform, /*bWorldSpace=*/true))
					{
						// Pieces tumble inside the actor's scale, so a stretched paving stone's would shear: same volume, uniform
						const FVector Scale = WorldTransform.GetScale3D().GetAbs();
						WorldTransform.SetScale3D(FVector(FMath::Pow(Scale.X * Scale.Y * Scale.Z, 1.0 / 3.0)));

						SpawnBrokenProp(*Collection, WorldTransform);
					}
				}
			}
		}

		// Already sorted high to low
		ISM->RemoveInstances(ToRemove, /*bInstanceArrayAlreadySortedInReverseOrder=*/true);
	}
}

void AMyHexPlatform::PlayFarBreak(const FHexFarBreakMesh& Far, const FTransform& WorldTransform, float Speed)
{
	if (!Far.Mesh)
	{
		return;
	}

	if (UMyHexPillarBreakSubsystem* Breaks = GetWorld()->GetSubsystem<UMyHexPillarBreakSubsystem>())
	{
		Breaks->AddFarBreak(Far, WorldTransform, Speed, FarBreakMaxActive);
	}
}

void AMyHexPlatform::SpawnBrokenProp(UGeometryCollection* Collection, const FTransform& WorldTransform)
{
	UWorld* World = GetWorld();

	if (!World || !Collection)
	{
		return;
	}

	AGeometryCollectionActor* Broken = World->SpawnActorDeferred<AGeometryCollectionActor>(
		AGeometryCollectionActor::StaticClass(),
		WorldTransform,
		this,
		nullptr,
		ESpawnActorCollisionHandlingMethod::AlwaysSpawn
	);

	if (!Broken)
	{
		return;
	}

	// Each machine spawns its own debris
	Broken->SetReplicates(false);

	UGeometryCollectionComponent* GC = Broken->GetGeometryCollectionComponent();

	if (GC)
	{
		GC->SetRestCollection(Collection);
		GC->ObjectType = EObjectStateTypeEnum::Chaos_Object_Dynamic;

		// Set before the physics state is created, so it applies on the first frame
		const FVector Spread(FMath::FRandRange(-1.f, 1.f), FMath::FRandRange(-1.f, 1.f), 0.f);
		GC->InitialVelocityType = EInitialVelocityTypeEnum::Chaos_Initial_Velocity_User_Defined;
		GC->InitialLinearVelocity = BrokenPropImpulse + Spread * BrokenPropImpulse.Size() * 0.5f;
	}

	Broken->FinishSpawning(WorldTransform);
	Broken->SetLifeSpan(BrokenPropLifeSpan);

	if (GC && bCrumbleBrokenProps)
	{
		GC->CrumbleActiveClusters();
	}
}


#if !UE_BUILD_SHIPPING
namespace
{
	// Aura.BreakTopPlatform [Chains] [X Y Z]: the server collapses tile chains of the top platform nearest
	// (X, Y, Z), or the local pawn, through the normal replicated path. Chains <= 0 = every tile at once.
	FAutoConsoleCommandWithWorldAndArgs GBreakTopPlatformCommand(
		TEXT("Aura.BreakTopPlatform"),
		TEXT("Aura.BreakTopPlatform [Chains=1] [X Y Z] [Bottom=0] - server: collapse Chains tile chains (0 = every tile at once) of the top platform (Bottom=1: bottom platform) nearest (X, Y, Z) or the local pawn"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (!World)
			{
				return;
			}

			const int32 Chains = Args.Num() > 0 ? FCString::Atoi(*Args[0]) : 1;
			const bool bBottom = Args.Num() > 4 && FCString::Atoi(*Args[4]) != 0;
			FVector Near = FVector::ZeroVector;

			if (Args.Num() >= 4)
			{
				Near = FVector(FCString::Atod(*Args[1]), FCString::Atod(*Args[2]), FCString::Atod(*Args[3]));
			}
			else if (const APlayerController* PC = World->GetFirstPlayerController())
			{
				if (const APawn* Pawn = PC->GetPawn())
				{
					Near = Pawn->GetActorLocation();
				}
			}

			AMyHexPlatform* Best = nullptr;
			double BestDistSq = TNumericLimits<double>::Max();

			for (TActorIterator<AMyHexPlatform> It(World); It; ++It)
			{
				if (!It->HasAuthority() || It->IsBottomPlatform() != bBottom || It->GetTileInfos().IsEmpty())
				{
					continue;
				}

				const double DistSq = FVector::DistSquared(It->GetActorLocation(), Near);

				if (DistSq < BestDistSq)
				{
					BestDistSq = DistSq;
					Best = *It;
				}
			}

			if (!Best)
			{
				UE_LOG(LogTemp, Warning, TEXT("Aura.BreakTopPlatform: no %s platform with tiles in %s (run it on the server)"), bBottom ? TEXT("bottom") : TEXT("top"), *World->GetName());
				return;
			}

			// Pieces only spawn near the local player (BreakEffectsMaxDistance), as in normal play
			UE_LOG(LogTemp, Display, TEXT("Aura.BreakTopPlatform: %s (%d tiles) at %s, chains %d, %.0f cm from the search point"),
				*Best->GetName(), Best->GetTileInfos().Num(), *Best->GetActorLocation().ToCompactString(), Chains, FMath::Sqrt(BestDistSq));

			Best->DebugBreakTiles(Chains);
		})
	);
}
#endif
