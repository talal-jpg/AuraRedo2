// Fill out your copyright notice in the Description page of Project Settings.


#include "Actors/MyHexBridge.h"

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
}

void AMyHexBridge::OnRep_Ends()
{
	ApplyEnds();
	BindToPlatforms();
}


// =============================================================================
// Init (server)
// =============================================================================

void AMyHexBridge::InitBridge(const FMyHexBridgeEnd& InStart, const FMyHexBridgeEnd& InEnd)
{
	Ends.Start = InStart;
	Ends.End = InEnd;
}


// =============================================================================
// BeginPlay / EndPlay
// =============================================================================

void AMyHexBridge::BeginPlay()
{
	Super::BeginPlay();

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

	// Replaces the two default points a spline starts with
	BridgeSpline->SetSplinePoints(
		{ Ends.Start.Location, Ends.End.Location },
		ESplineCoordinateSpace::World
	);
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
