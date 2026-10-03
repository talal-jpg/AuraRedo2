// Fill out your copyright notice in the Description page of Project Settings.


#include "Actors/MyHexPlatform.h"

#include <string>

#include "Engine/World.h"
#include "TimerManager.h"
#include "Kismet/KismetMathLibrary.h"
#include "Kismet/KismetSystemLibrary.h"
#include "Net/UnrealNetwork.h"


// =============================================================================
// Constructor
// =============================================================================

AMyHexPlatform::AMyHexPlatform()
{
	PrimaryActorTick.bCanEverTick = false;

	bReplicates = true;

	// -------------------------------------------------------------------------
	// ISM
	// -------------------------------------------------------------------------

	HexPillarsISM = CreateDefaultSubobject<UInstancedStaticMeshComponent>(
		TEXT("HexPillarsISM")
	);
	HexPillarsISM->SetRemoveSwap();
	
	HexPillarsISM->NumCustomDataFloats=1;

	SetRootComponent(HexPillarsISM);

	HexPillarsISM->SetCollisionEnabled(
		ECollisionEnabled::QueryAndPhysics
	);

	HexPillarsISM->SetCollisionResponseToAllChannels(
		ECR_Block
	);
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
}


// =============================================================================
// BeginPlay
// =============================================================================

void AMyHexPlatform::BeginPlay()
{
	Super::BeginPlay();

	// The grid itself is NOT replicated.
	//
	// Every machine already constructed the exact same static grid
	// in OnConstruction().
	//
	// Only activation state is replicated.
	
	BuildHexGrid();
	UKismetSystemLibrary::PrintString(
		this,
		TEXT("BEGIN PLAY: HexMap=%d | ISM=%d"),
		HexMap.Num(),
		HexPillarsISM
			? HexPillarsISM->GetInstanceCount()
			: -1
	);

	//TODO Can choose a grid randomly based on Grid size ( the larger the size the greater the chance is to get selected for destruction)
	// grids with a size of certain threshold get destroyed completely
	
	if (HasAuthority())
	{
		// ---------------------------------------------------------------------
		// Start chain activation timer
		// ---------------------------------------------------------------------

		FTimerHandle TimerHandle;
		
		GetWorld()->GetTimerManager().SetTimer(
			TimerHandle,
			this,
			&ThisClass::GenerateAndActivateChainFromRandomSelectedGrid,
			1.f,
			true,
			1.f
		);
	}
}


// =============================================================================
// OnConstruction
// =============================================================================

void AMyHexPlatform::OnConstruction(
	const FTransform& Transform
)
{
	Super::OnConstruction(Transform);

	BuildHexGrid();
	
	UKismetSystemLibrary::PrintString(this,TEXT("ConstructionEventCalled"));
	
	for (auto Hex:HexMap)
	{
		UKismetSystemLibrary::PrintString(this,Hex.Key.ToString());
	}
}


// =============================================================================
// Build Grid
// =============================================================================

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

	HexMap.Empty();
	InstanceToHex.Empty();


	// -------------------------------------------------------------------------
	// Set static mesh
	// -------------------------------------------------------------------------

	if (!HexPillarStaticMesh)
	{
		return;
	}

	HexPillarsISM->SetStaticMesh(
		HexPillarStaticMesh
	);


	// -------------------------------------------------------------------------
	// Generate grid
	// -------------------------------------------------------------------------

	const TArray<FHexCoord> HexCoords = GenerateHexGrid();

	
	for (const FHexCoord& HexCoord : HexCoords)
	{
		
		// calc dist from center
		const int32 DistanceFromCenter = FMath::Max3(FMath::Abs(HexCoord.Q),FMath::Abs(HexCoord.R),FMath::Abs(HexCoord.S));

		// Normalize 0 to1 
		const float Distance01 =static_cast<float>(DistanceFromCenter) /static_cast<float>(GridSize);
		
		//TODO Make tweakable Prop
		const double BOH_NoiseScale = 0.2;

		float NoiseBOH = FMath::PerlinNoise3D(
			FVector3d(
				HexCoord.Q * BOH_NoiseScale,
				HexCoord.R * BOH_NoiseScale,
				HexCoord.S * BOH_NoiseScale
			)
		);
		
		NoiseBOH= (NoiseBOH+1.f)* 0.5f;

		// calc scale 
		const float Scale = FMath::Lerp(
			GridSize*VerticalScaling* NoiseBOH,   // center
			0.4f,   // edge
			Distance01
		);
		
		
		// calc offset in z due to scale 
		float ZOffsetDueToScale= GridSize-Scale;
		
		// Mult by instanced geo size
		ZOffsetDueToScale*= 1000.f;
		
		const FVector2D Loc2d = HexToWorld(
			HexCoord.Q,
			HexCoord.R,
			HexRadius
		);

		FTransform InstanceTransform;

		InstanceTransform.SetLocation(
			FVector(
				Loc2d.X,
				Loc2d.Y,
				//TODO Add slight randomness to z Loc
				0.f
			)
		);
		
		float InstanceRadius=HexRadius/100;
		InstanceTransform.SetScale3D(
			FVector(
				InstanceRadius,
				InstanceRadius,
				Scale
			)
		);

		const FIntVector Coord(
			HexCoord.Q,
			HexCoord.R,
			HexCoord.S
		);

		float noise=FMath::PerlinNoise2D((Loc2d*NoiseScale)+NoiseOffset);
		
		float Dist= NoiseCurve? NoiseCurve->GetFloatValue(Distance01) : Distance01;
		// float Dist= NoiseCurve.GetValueAtLevel(Distance01);
		noise= FMath::Max(1-Distance01,noise);
		
		FVector2D InputRange=FVector2D(0,1);
		FVector2D OutputRange=FVector2D(0,1);
		Dist=FMath::GetMappedRangeValueClamped(InputRange,OutputRange,Dist);
		
		noise= noise+Dist;
		
		int32 InstanceIndex=INDEX_NONE;
		
		if (noise>DeletionThreshold)
		{
			 InstanceIndex= AddHexInstance(Coord,InstanceTransform);
		}
		

		if (InstanceIndex != INDEX_NONE)
		{
			HexPillarsISM->SetCustomDataValue(InstanceIndex,0,Dist,true);
			
			HexMap.Add(
				Coord,
				InstanceIndex
			);

			InstanceToHex.Add(
				InstanceIndex,
				Coord
			);
		}
	}
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
	// The client receives the complete/current ActivatedTiles array.
	//
	// Find anything that this machine hasn't visually activated yet.

	for (const FIntVector& Coord : ActivatedTiles)
	{
		if (!LocalActivatedTiles.Contains(Coord))
		{
			ActivateHexLocal(Coord);
		}
	}
}


// =============================================================================
// Activate Hex Locally
// =============================================================================

void AMyHexPlatform::ActivateHexLocal(const FIntVector& Coord)
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

	SkeletalMesh->SetSkeletalMesh(HexPillarSkeletalMesh);

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

	if (!RbdAnimSeq)
	{
		UE_LOG(
			LogTemp,
			Error,
			TEXT("ActivateHexLocal: RbdAnimSeq is NULL")
		);

		return;
	}

	SkeletalMesh->PlayAnimation(
		RbdAnimSeq,
		false
	);

	UE_LOG(
		LogTemp,
		Display,
		TEXT("Activated Hex %s"),
		*Coord.ToString()
	);

	// -------------------------------------------------------------------------
	// Destroy after animation
	// -------------------------------------------------------------------------

	const float AnimationLength =
		RbdAnimSeq->GetPlayLength();

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