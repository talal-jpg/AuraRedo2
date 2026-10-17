// Fill out your copyright notice in the Description page of Project Settings.


#include "Actors/MyHexBridge.h"

#include "Actors/MyHexMinimapSubsystem.h"
#include "Actors/MyHexPlatform.h"
#include "Components/SplineComponent.h"
#include "Net/UnrealNetwork.h"
#include "PCGComponent.h"


// =============================================================================
// Constructor
// =============================================================================

AMyHexBridge::AMyHexBridge()
{
	PrimaryActorTick.bCanEverTick = false;

	bReplicates = true;

	// Same as AMyHexPlatform: every machine keeps every bridge, so none hangs without its platforms
	bAlwaysRelevant = true;

	// Bridges are placed in world space, so the actor transform never needs to move after spawning
	SetReplicateMovement(false);

	BridgeSpline = CreateDefaultSubobject<USplineComponent>(TEXT("BridgeSpline"));
	SetRootComponent(BridgeSpline);

	PCGComponent = CreateDefaultSubobject<UPCGComponent>(TEXT("PCGComponent"));

	// Generated from BeginPlay once the spline has its points, never on load
	PCGComponent->GenerationTrigger = EPCGComponentGenerationTrigger::GenerateOnDemand;
}


// =============================================================================
// Replication
// =============================================================================

void AMyHexBridge::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);

	// Set once before FinishSpawning and never changed
	DOREPLIFETIME_CONDITION(AMyHexBridge, Ends, COND_InitialOnly);
	DOREPLIFETIME_CONDITION(AMyHexBridge, bIsBottomBridge, COND_InitialOnly);
}

void AMyHexBridge::OnRep_Ends()
{
	ApplyEnds();
	BindToPlatforms();
}


// =============================================================================
// Init (server)
// =============================================================================

void AMyHexBridge::InitBridge(const FMyHexBridgeEnd& InStart, const FMyHexBridgeEnd& InEnd, const FVector& InStartTangent, const FVector& InEndTangent, bool bInIsBottomBridge)
{
	Ends.Start = InStart;
	Ends.End = InEnd;
	Ends.StartTangent = InStartTangent;
	Ends.EndTangent = InEndTangent;
	bIsBottomBridge = bInIsBottomBridge;
}


// =============================================================================
// BeginPlay / EndPlay
// =============================================================================

void AMyHexBridge::BeginPlay()
{
	Super::BeginPlay();

	// An end platform was culled between the bridge being planned and spawned
	if (HasAuthority() && (!IsValid(Ends.Start.Platform) || !IsValid(Ends.End.Platform)))
	{
		Destroy();
		return;
	}

	// On the server Ends was set before FinishSpawning. On a client the initial replicated
	// properties are applied before BeginPlay, so the points are already there too.
	ApplyEnds();
	BindToPlatforms();

	if (bGenerateOnBeginPlay && PCGComponent && PCGComponent->GetGraph())
	{
		// Local on every machine: PCG output is not replicated
		PCGComponent->GenerateLocal(/*bForce=*/true);
	}
}

void AMyHexBridge::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	for (AMyHexPlatform* Platform : { Ends.Start.Platform.Get(), Ends.End.Platform.Get() })
	{
		if (IsValid(Platform))
		{
			Platform->OnHexTileActivated.RemoveAll(this);
			Platform->OnEndPlay.RemoveDynamic(this, &ThisClass::HandleEndPlatformEndPlay);
			Platform->UnregisterBridge(this);
			Platform->UnregisterPathBridge(this);
		}
	}

	if (UWorld* World = GetWorld())
	{
		if (UMyHexMinimapSubsystem* Minimap = World->GetSubsystem<UMyHexMinimapSubsystem>())
		{
			Minimap->UnregisterBridge(this);
		}
	}

	Super::EndPlay(EndPlayReason);
}


// =============================================================================
// Spline
// =============================================================================

void AMyHexBridge::ApplyEnds()
{
	if (!BridgeSpline)
	{
		return;
	}

	const FVector& P0 = Ends.Start.Location;
	const FVector& P1 = Ends.End.Location;

	// A curved deck: the server's tangents, applied verbatim so every machine gets the same curve
	const bool bCurved = !Ends.StartTangent.IsNearlyZero() || !Ends.EndTangent.IsNearlyZero();

	// A top bridge dips at the middle like a rope bridge. A bottom bridge keeps the planned deck.
	const double Sag = bIsBottomBridge ? 0.0 : SagRatio * FVector::Dist(P0, P1);

	if (Sag <= UE_KINDA_SMALL_NUMBER)
	{
		// Replaces the two default points a spline starts with
		BridgeSpline->SetSplinePoints({ P0, P1 }, ESplineCoordinateSpace::World, /*bUpdateSpline=*/false);

		if (bCurved)
		{
			BridgeSpline->SetTangentsAtSplinePoint(0, Ends.StartTangent, Ends.StartTangent, ESplineCoordinateSpace::World, /*bUpdateSpline=*/false);
			BridgeSpline->SetTangentsAtSplinePoint(1, Ends.EndTangent, Ends.EndTangent, ESplineCoordinateSpace::World, /*bUpdateSpline=*/false);
		}
	}
	else
	{
		// The planned deck is one cubic (the chord when straight). Split at its middle into two cubics,
		// it keeps exactly the same path seen from above; each half spans half the input range, so the
		// tangents halve. The middle point then drops by Sag and the end tangents' Z moves by Sag,
		// which is the dip the old inserted middle point gave. (Inserting that point into the curved
		// spline kept the full-length end tangents on half-length segments and pulled the middle back
		// onto the straight line, so curved decks bent the wrong way.)
		const FVector T0 = bCurved ? Ends.StartTangent : P1 - P0;
		const FVector T1 = bCurved ? Ends.EndTangent : P1 - P0;
		const FVector Down(0.0, 0.0, Sag);

		const FVector Mid = FMath::CubicInterp(P0, T0, P1, T1, 0.5) - Down;
		const FVector StartTangent = 0.5 * T0 - Down;
		const FVector MidTangent = 0.5 * FMath::CubicInterpDerivative(P0, T0, P1, T1, 0.5);
		const FVector EndTangent = 0.5 * T1 + Down;

		BridgeSpline->SetSplinePoints({ P0, Mid, P1 }, ESplineCoordinateSpace::World, /*bUpdateSpline=*/false);
		BridgeSpline->SetTangentsAtSplinePoint(0, StartTangent, StartTangent, ESplineCoordinateSpace::World, /*bUpdateSpline=*/false);
		BridgeSpline->SetTangentsAtSplinePoint(1, MidTangent, MidTangent, ESplineCoordinateSpace::World, /*bUpdateSpline=*/false);
		BridgeSpline->SetTangentsAtSplinePoint(2, EndTangent, EndTangent, ESplineCoordinateSpace::World, /*bUpdateSpline=*/false);
	}

	BridgeSpline->UpdateSpline();

	// Draws (or redraws) the deck on the minimap
	if (UWorld* World = GetWorld())
	{
		if (UMyHexMinimapSubsystem* Minimap = World->GetSubsystem<UMyHexMinimapSubsystem>())
		{
			Minimap->RegisterBridge(this);
		}
	}
}


// =============================================================================
// Tile collapse notifications
// =============================================================================

void AMyHexBridge::BindToPlatforms()
{
	for (AMyHexPlatform* Platform : { Ends.Start.Platform.Get(), Ends.End.Platform.Get() })
	{
		if (!IsValid(Platform))
		{
			continue;
		}

		Platform->OnHexTileActivated.RemoveAll(this);
		Platform->OnHexTileActivated.AddUObject(this, &ThisClass::OnPlatformTileActivated);

		if (HasAuthority())
		{
			Platform->OnEndPlay.AddUniqueDynamic(this, &ThisClass::HandleEndPlatformEndPlay);
			Platform->RegisterBridge(this);
			// Its end tile becomes a start of the platform's walkway (PathStartTiles, replicated)
			Platform->RegisterPathBridge(this);
		}
	}

	// A client that joins late, or a platform that arrives after the bridge, may already have
	// collapsed the tile. Treat that the same as seeing it collapse.
	for (const FMyHexBridgeEnd& BridgeEnd : { Ends.Start, Ends.End })
	{
		if (IsValid(BridgeEnd.Platform) && BridgeEnd.Platform->IsTileCollapsed(BridgeEnd.Tile))
		{
			NotifyEndTileCollapsed(BridgeEnd.Platform, BridgeEnd.Tile);
			return;
		}
	}
}

void AMyHexBridge::OnPlatformTileActivated(AMyHexPlatform* Platform, const FIntVector& Tile)
{
	const bool bIsStart = Platform == Ends.Start.Platform && Tile == Ends.Start.Tile;
	const bool bIsEnd = Platform == Ends.End.Platform && Tile == Ends.End.Tile;

	if (bIsStart || bIsEnd)
	{
		NotifyEndTileCollapsed(Platform, Tile);
	}
}

void AMyHexBridge::HandleEndPlatformEndPlay(AActor* Actor, EEndPlayReason::Type EndPlayReason)
{
	// Ignore PIE stop, quit and level travel: everything goes then anyway
	if (HasAuthority() && !IsActorBeingDestroyed()
		&& (EndPlayReason == EEndPlayReason::Destroyed || EndPlayReason == EEndPlayReason::RemovedFromWorld))
	{
		Destroy();
	}
}

void AMyHexBridge::NotifyEndTileCollapsed(AMyHexPlatform* Platform, const FIntVector& Tile)
{
	// Only the first end that collapses counts
	if (bEndTileCollapsed)
	{
		return;
	}

	bEndTileCollapsed = true;

	HandleEndTileCollapsed(Platform, Tile);
	OnEndTileCollapsed.Broadcast(this, Platform, Tile);
}

void AMyHexBridge::HandleEndTileCollapsed_Implementation(AMyHexPlatform* Platform, FIntVector Tile)
{
	// Destroying on the server destroys the replicated bridge on every client too
	if (!bDestroyWhenEndTileCollapses || !HasAuthority())
	{
		return;
	}

	if (DestroyDelay > 0.f)
	{
		SetLifeSpan(DestroyDelay);
	}
	else
	{
		Destroy();
	}
}
