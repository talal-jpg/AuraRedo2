// Fill out your copyright notice in the Description page of Project Settings.


#include "Actors/MyHexBridge.h"

#include "Actors/MyHexMinimapSubsystem.h"
#include "Actors/MyHexPlatform.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/SplineComponent.h"
#include "Engine/CollisionProfile.h"
#include "Engine/StaticMesh.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "GeometryCollection/GeometryCollectionActor.h"
#include "GeometryCollection/GeometryCollectionComponent.h"
#include "GeometryCollection/GeometryCollectionObject.h"
#include "GeometryCollection/GeometryCollectionSimulationTypes.h"
#include "Net/UnrealNetwork.h"
#include "PCGComponent.h"
#include "PhysicsEngine/BodySetup.h"
#include "EngineUtils.h"
#include "HAL/IConsoleManager.h"
#include "TimerManager.h"


// =============================================================================
// Constructor
// =============================================================================

AMyHexBridge::AMyHexBridge()
{
	// Ticks only while a collapse runs
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.bStartWithTickEnabled = false;

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

	// Not when an end tile had already collapsed (a late join): the bridge is on its way out
	if (bGenerateOnBeginPlay && !bEndTileCollapsed && PCGComponent && PCGComponent->GetGraph())
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
			bEndTileCollapseSeen = false;
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
	bCollapseFromStart = Platform == Ends.Start.Platform && Tile == Ends.Start.Tile;

	HandleEndTileCollapsed(Platform, Tile);
	OnEndTileCollapsed.Broadcast(this, Platform, Tile);
}

void AMyHexBridge::HandleEndTileCollapsed_Implementation(AMyHexPlatform* Platform, FIntVector Tile)
{
	if (CollapseMode != EMyHexBridgeCollapseMode::None)
	{
		// Every machine runs its own collapse (PCG output is local). The server destroys the bridge
		// once it has finished, in FinishCollapse.
		StartCollapse(/*bWithDebris=*/bEndTileCollapseSeen && IsNearLocalPlayer());
		return;
	}

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


// =============================================================================
// Collapse
// =============================================================================

void AMyHexBridge::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	if (bCollapsing)
	{
		CollapseElapsed += DeltaSeconds;
		AdvanceCollapse();
	}
}

void AMyHexBridge::StartCollapse(bool bWithDebris)
{
	if (bCollapsing || !BridgeSpline)
	{
		return;
	}

	bCollapsing = true;
	CollapseElapsed = 0.f;

	// Still generating: stop it. Nothing has been spawned yet, so nothing falls.
	if (PCGComponent && PCGComponent->IsGenerating())
	{
		PCGComponent->CancelGeneration();
		PCGComponent->CleanupLocal(/*bRemoveComponents=*/true);
	}

	const float Length = BridgeSpline->GetSplineLength();

	// The same jitter on every machine, so the walk colliders go at about the same time everywhere
	FRandomStream Stream(HashCombine(GetTypeHash(Ends.Start.Location), GetTypeHash(Ends.End.Location)));

	auto TimeAt = [&](const FVector& WorldLoc)
	{
		const float Key = BridgeSpline->FindInputKeyClosestToWorldLocation(WorldLoc);
		const float Distance = BridgeSpline->GetDistanceAlongSplineAtSplineInputKey(Key);
		const float FromBrokenEnd = bCollapseFromStart ? Distance : Length - Distance;
		return FMath::Max(FromBrokenEnd, 0.f) / CollapseSpeed + Stream.FRandRange(0.f, CollapseJitter);
	};

	TInlineComponentArray<UInstancedStaticMeshComponent*> ISMs(this);

	for (UInstancedStaticMeshComponent* ISM : ISMs)
	{
		const int32 Count = ISM ? ISM->GetInstanceCount() : 0;

		if (Count == 0 || !ISM->GetStaticMesh())
		{
			continue;
		}

		const int32 Owner = CollapseISMs.Num();
		FCollapseISM& Entry = CollapseISMs.AddDefaulted_GetRef();
		Entry.ISM = ISM;

		// Invisible meshes (the walk colliders) just go
		Entry.bDebris = bWithDebris && ISM->GetVisibleFlag();

		if (Entry.bDebris && CollapseMode == EMyHexBridgeCollapseMode::GeometryCollections)
		{
			if (const TObjectPtr<UGeometryCollection>* Found = BreakableMeshes.Find(ISM->GetStaticMesh()))
			{
				Entry.Collection = *Found;
			}
		}

		// Removing an instance moves the last one into its slot (HISMs always do), which
		// PieceAtInstance mirrors
		ISM->SetRemoveSwap();

		Entry.PieceAtInstance.Reserve(Count);

		for (int32 Instance = 0; Instance < Count; ++Instance)
		{
			FCollapsePiece Piece;
			Piece.Owner = Owner;
			Piece.Instance = Instance;
			ISM->GetInstanceTransform(Instance, Piece.WorldTransform, /*bWorldSpace=*/true);
			Piece.Time = TimeAt(Piece.WorldTransform.GetLocation());

			Entry.PieceAtInstance.Add(CollapsePieces.Add(Piece));
		}
	}

	// Actors the graph spawned (torches): removed when the front reaches them
	TArray<AActor*> Attached;
	GetAttachedActors(Attached);

	for (AActor* Child : Attached)
	{
		if (IsValid(Child) && !Child->GetIsReplicated())
		{
			FCollapsePiece Piece;
			Piece.Actor = Child;
			Piece.WorldTransform = Child->GetActorTransform();
			Piece.Time = TimeAt(Piece.WorldTransform.GetLocation());
			CollapsePieces.Add(Piece);
		}
	}

	CollapseOrder.Reserve(CollapsePieces.Num());

	for (int32 Index = 0; Index < CollapsePieces.Num(); ++Index)
	{
		CollapseOrder.Add(Index);
	}

	CollapseOrder.Sort([this](int32 A, int32 B) { return CollapsePieces[A].Time < CollapsePieces[B].Time; });

	// Physics mesh debris outlives the bridge: a holder actor owns it
	if (bWithDebris && !CollapsePieces.IsEmpty())
	{
		FActorSpawnParameters Params;
		Params.Owner = this;
		Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;

		if (AActor* Holder = GetWorld()->SpawnActor<AActor>(AActor::StaticClass(), GetActorTransform(), Params))
		{
			Holder->SetReplicates(false);

			USceneComponent* Root = NewObject<USceneComponent>(Holder, TEXT("Root"));
			Holder->SetRootComponent(Root);
			Root->RegisterComponent();

			const float LastTime = CollapsePieces[CollapseOrder.Last()].Time;
			Holder->SetLifeSpan(LastTime + DebrisLifeSpan + 0.5f);
			DebrisHolder = Holder;
		}
	}

	UE_LOG(LogTemp, Verbose, TEXT("%s: collapsing %d pieces from the %s end (debris %d)"),
		*GetName(), CollapsePieces.Num(), bCollapseFromStart ? TEXT("start") : TEXT("end"), bWithDebris ? 1 : 0);

	SetActorTickEnabled(true);
	AdvanceCollapse();
}

void AMyHexBridge::AdvanceCollapse()
{
	// Pieces the front has reached, grouped by ISM so each ISM is updated once
	TArray<TArray<int32>, TInlineAllocator<8>> Reached;
	Reached.SetNum(CollapseISMs.Num());

	while (CollapseOrder.IsValidIndex(CollapseCursor))
	{
		const int32 PieceIndex = CollapseOrder[CollapseCursor];
		const FCollapsePiece& Piece = CollapsePieces[PieceIndex];

		if (Piece.Time > CollapseElapsed)
		{
			break;
		}

		++CollapseCursor;

		if (Piece.Owner == INDEX_NONE)
		{
			if (AActor* Child = Piece.Actor.Get())
			{
				Child->Destroy();
			}
		}
		else
		{
			Reached[Piece.Owner].Add(PieceIndex);
		}
	}

	for (int32 Owner = 0; Owner < CollapseISMs.Num(); ++Owner)
	{
		FCollapseISM& Entry = CollapseISMs[Owner];
		UInstancedStaticMeshComponent* ISM = Entry.ISM.Get();

		if (Reached[Owner].IsEmpty() || !ISM)
		{
			continue;
		}

		TArray<int32> Instances;
		Instances.Reserve(Reached[Owner].Num());

		for (const int32 PieceIndex : Reached[Owner])
		{
			Instances.Add(CollapsePieces[PieceIndex].Instance);

			if (Entry.bDebris)
			{
				SpawnDebris(Entry, CollapsePieces[PieceIndex].WorldTransform);
			}
		}

		// High to low, so each remove-at-swap only moves an instance that stays
		Instances.Sort(TGreater<int32>());

		if (!ISM->RemoveInstances(Instances, /*bInstanceArrayAlreadySortedInReverseOrder=*/true))
		{
			continue;
		}

		for (const int32 Instance : Instances)
		{
			const int32 Last = Entry.PieceAtInstance.Num() - 1;

			if (Instance != Last)
			{
				const int32 Moved = Entry.PieceAtInstance[Last];
				Entry.PieceAtInstance[Instance] = Moved;
				CollapsePieces[Moved].Instance = Instance;
			}

			Entry.PieceAtInstance.Pop(EAllowShrinking::No);
		}
	}

	if (!CollapseOrder.IsValidIndex(CollapseCursor))
	{
		FinishCollapse();
	}
}

void AMyHexBridge::FinishCollapse()
{
	bCollapsing = false;
	SetActorTickEnabled(false);

	CollapsePieces.Empty();
	CollapseOrder.Empty();
	CollapseISMs.Empty();
	CollapseCursor = 0;

	// Destroying on the server destroys the replicated bridge on every client too. Clients start
	// their collapse a little later, so a short DestroyDelay lets theirs finish.
	if (!bDestroyWhenEndTileCollapses || !HasAuthority() || IsActorBeingDestroyed())
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

void AMyHexBridge::SpawnDebris(const FCollapseISM& Entry, const FTransform& WorldTransform)
{
	UInstancedStaticMeshComponent* ISM = Entry.ISM.Get();

	if (!ISM)
	{
		return;
	}

	const float Size = ISM->GetStaticMesh()->GetBounds().SphereRadius * WorldTransform.GetMaximumAxisScale();
	const FVector Spread(FMath::FRandRange(-1.f, 1.f), FMath::FRandRange(-1.f, 1.f), 0.f);
	const FVector Velocity = DebrisVelocity + Spread * FMath::Min(Size, 200.f) * 0.5f;

	if (Entry.Collection)
	{
		SpawnDebrisCollection(Entry.Collection, WorldTransform, Velocity);
	}
	else
	{
		// PhysicsMeshes, or a GeometryCollections mesh without a collection
		SpawnDebrisMesh(ISM, WorldTransform, Velocity);
	}
}

void AMyHexBridge::SpawnDebrisCollection(UGeometryCollection* Collection, const FTransform& WorldTransform, const FVector& Velocity)
{
	UWorld* World = GetWorld();

	if (!World)
	{
		return;
	}

	AGeometryCollectionActor* Debris = World->SpawnActorDeferred<AGeometryCollectionActor>(
		AGeometryCollectionActor::StaticClass(),
		WorldTransform,
		this,
		nullptr,
		ESpawnActorCollisionHandlingMethod::AlwaysSpawn
	);

	if (!Debris)
	{
		return;
	}

	// Each machine spawns its own debris
	Debris->SetReplicates(false);

	UGeometryCollectionComponent* GC = Debris->GetGeometryCollectionComponent();

	if (GC)
	{
		// Before SetRestCollection, which builds the physics proxy from them
		GC->ObjectType = EObjectStateTypeEnum::Chaos_Object_Dynamic;
		GC->InitialVelocityType = EInitialVelocityTypeEnum::Chaos_Initial_Velocity_User_Defined;
		GC->InitialLinearVelocity = Velocity;
		GC->SetCollisionResponseToChannel(ECC_Pawn, ECR_Ignore);
		GC->SetCollisionResponseToChannel(ECC_Camera, ECR_Ignore);
		GC->SetRestCollection(Collection);
	}

	Debris->FinishSpawning(WorldTransform);
	Debris->SetLifeSpan(DebrisLifeSpan);

	if (!GC || CrumbleDelay < 0.f)
	{
		return;
	}

	if (CrumbleDelay == 0.f)
	{
		GC->CrumbleActiveClusters();
		return;
	}

	FTimerHandle Handle;
	World->GetTimerManager().SetTimer(
		Handle,
		FTimerDelegate::CreateWeakLambda(GC, [GC]() { GC->CrumbleActiveClusters(); }),
		CrumbleDelay,
		false
	);
}

void AMyHexBridge::SpawnDebrisMesh(UInstancedStaticMeshComponent* Source, const FTransform& WorldTransform, const FVector& Velocity)
{
	AActor* Holder = DebrisHolder.Get();
	UStaticMesh* Mesh = Source->GetStaticMesh();

	// A mesh without simple collision can't simulate: it just goes
	const UBodySetup* BodySetup = Mesh ? Mesh->GetBodySetup() : nullptr;

	if (!Holder || !BodySetup || BodySetup->AggGeom.GetElementCount() == 0)
	{
		return;
	}

	UStaticMeshComponent* Piece = NewObject<UStaticMeshComponent>(Holder);
	Piece->SetMobility(EComponentMobility::Movable);
	Piece->SetStaticMesh(Mesh);

	for (int32 Slot = 0; Slot < Source->GetNumMaterials(); ++Slot)
	{
		Piece->SetMaterial(Slot, Source->GetMaterial(Slot));
	}

	Piece->SetCastShadow(Source->CastShadow);
	Piece->SetCollisionProfileName(UCollisionProfile::PhysicsActor_ProfileName);
	Piece->SetCollisionResponseToChannel(ECC_Pawn, ECR_Ignore);
	Piece->SetCollisionResponseToChannel(ECC_Camera, ECR_Ignore);
	Piece->SetSimulatePhysics(true);

	// Not attached: the root is only there to own it
	Piece->SetWorldTransform(WorldTransform);
	Piece->RegisterComponent();
	Holder->AddInstanceComponent(Piece);

	const FVector Spin(FMath::FRandRange(-1.f, 1.f), FMath::FRandRange(-1.f, 1.f), FMath::FRandRange(-1.f, 1.f));
	Piece->SetPhysicsLinearVelocity(Velocity);
	Piece->SetPhysicsAngularVelocityInDegrees(Spin * DebrisMaxSpin);
}

bool AMyHexBridge::IsNearLocalPlayer() const
{
	const UWorld* World = GetWorld();

	if (!World || !BridgeSpline)
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

		FVector Closest = BridgeSpline->FindLocationClosestToWorldLocation(ViewLoc, ESplineCoordinateSpace::World);
		Closest.Z = ViewLoc.Z = 0.0;
		return FVector::DistSquared(ViewLoc, Closest) <= FMath::Square(DebrisMaxDistance);
	}

	return false;
}

void AMyHexBridge::DebugCollapse(const FVector& Near)
{
	if (bEndTileCollapsed || CollapseMode == EMyHexBridgeCollapseMode::None)
	{
		return;
	}

	bEndTileCollapsed = true;
	bCollapseFromStart = FVector::DistSquared2D(Near, Ends.Start.Location) <= FVector::DistSquared2D(Near, Ends.End.Location);
	StartCollapse(/*bWithDebris=*/true);
}

#if !UE_BUILD_SHIPPING
namespace
{
	// Aura.CollapseBridges X Y Z Radius: collapses (locally, with debris) every bridge that passes within
	// Radius of (X, Y, Z), from its end nearer that point. Works in Simulate, where no tile ever breaks.
	FAutoConsoleCommandWithWorldAndArgs GCollapseBridgesCommand(
		TEXT("Aura.CollapseBridges"),
		TEXT("Aura.CollapseBridges X Y Z Radius - collapse the hex bridges near (X, Y, Z) on this machine, with debris"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (!World || Args.Num() < 4)
			{
				return;
			}

			const FVector Near(FCString::Atod(*Args[0]), FCString::Atod(*Args[1]), FCString::Atod(*Args[2]));
			const double Radius = FCString::Atod(*Args[3]);
			int32 Count = 0;

			for (TActorIterator<AMyHexBridge> It(World); It; ++It)
			{
				const USplineComponent* Spline = It->FindComponentByClass<USplineComponent>();
				const FVector Closest = Spline ? Spline->FindLocationClosestToWorldLocation(Near, ESplineCoordinateSpace::World) : It->GetActorLocation();

				if (FVector::DistSquared(Closest, Near) <= FMath::Square(Radius))
				{
					It->DebugCollapse(Near);
					++Count;
				}
			}

			UE_LOG(LogTemp, Display, TEXT("Aura.CollapseBridges: %d bridges in %s"), Count, *World->GetName());
		})
	);
}
#endif
