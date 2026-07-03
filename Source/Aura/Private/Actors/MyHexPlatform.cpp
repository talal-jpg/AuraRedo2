// Fill out your copyright notice in the Description page of Project Settings.


#include "Actors/MyHexPlatform.h"

#include "Actors/MyEffectActor.h"
#include "Actors/MyHexPillar.h"
#include "Kismet/GameplayStatics.h"


// Sets default values
AMyHexPlatform::AMyHexPlatform()
{
	// Set this actor to call Tick() every frame.  You can turn this off to improve performance if you don't need it.
	PrimaryActorTick.bCanEverTick = false;
}

// Called when the game starts or when spawned
void AMyHexPlatform::BeginPlay()
{
	Super::BeginPlay();
	
	//Spawning 
	FTransform Transform;
	
	TArray<FHexCoord> HexCoords=GenerateHexGrid(10);
	
	for (auto HexCoord:HexCoords)
	{
		FVector2D Loc2d=HexToWorld(HexCoord.Q,HexCoord.R,HexRadius);
		Transform.SetLocation(FVector(Loc2d.X,Loc2d.Y,0));
		
		AMyHexPillar* Spawned=GetWorld()->SpawnActor<AMyHexPillar>(HexagonPillarActorClass,Transform);
		
		FIntVector Key(HexCoord.Q, HexCoord.R, HexCoord.S);

		HexMap.Add(Key, Spawned);
	}
	//EndSpawning
	for (auto Hex:HexMap)
	{
		FIntVector Vec=Hex.Key;
		// UKismetSystemLibrary::PrintString(GetWorld(),FString::Printf(TEXT("Hex: %d,%d,%d"),Vec.X,Vec.Y,Vec.Z));
	}
	
	FTimerHandle TimerHandle;
	
	GetWorld()->GetTimerManager().SetTimer(TimerHandle,this,&ThisClass::GenerateAndActivateChainFromRandomSelectedGrid,10,true,10);
	
}



TArray<FHexCoord> AMyHexPlatform::GenerateHexGrid(int32 InGridSize)
{
	TArray<FHexCoord> Hexes;

	for (int32 Q = -GridSize; Q <= GridSize; ++Q)
	{
		const int32 RMax = FMath::Max(-GridSize, -Q - GridSize);
		const int32 RMin = FMath::Min(GridSize, -Q + GridSize);

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

FVector2D AMyHexPlatform::HexToWorld(int32 Q, int32 R, float InHexRadius)
{
	const float X = HexRadius * FMath::Sqrt(3.f) * (Q + R * 0.5f);
	const float Y = HexRadius * 1.5f * R;

	return FVector2D(X, Y);
}

TArray<FIntVector> AMyHexPlatform::GetNeighbors(const FIntVector& Hex)
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

	for (const FIntVector& Dir : Directions)
	{
		FIntVector Neighbor = Hex + Dir;

		if (HexMap.Contains(Neighbor) && !ConsumedTiles.Contains(Neighbor))
		{
			Result.Add(Neighbor);
		}
	}

	return Result;
}

TArray<FIntVector> AMyHexPlatform::GenerateChain(int32 Length,FIntVector StartHex)
{
	ConsumedTiles.Empty();
	
	TArray<FIntVector> Chain;
	TSet<FIntVector> Visited;

	FIntVector Current = StartHex;

	Chain.Add(Current);
	Visited.Add(Current);

	for (int32 i = 1; i < Length; i++)
	{
		TArray<FIntVector> Neighbors = GetNeighbors(Current);

		// for (FIntVector& Neighbor : Neighbors)
		// {
		// 	if (Visited.Contains(Neighbor))
		// 	{
		// 		Neighbors.Remove(Neighbor);
		// 	}
		// }
		
		//does the same as above makes it more complicated also makes safe to remove from array while iterating on it
		// Neighbors.RemoveAll([&Visited](const FIntVector& Coord)
		// 	{
		// 		return Visited.Contains(Coord);
		// 	});
		
		//is safe iterate on array backwards and keep removing
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

		Current = Neighbors[FMath::RandRange(0, Neighbors.Num() - 1)];

		ConsumedTiles.Add(Current);
		Chain.Add(Current);
		Visited.Add(Current);
	}

	return Chain;
}

void AMyHexPlatform::ActivateChain(const TArray<FIntVector>& Chain)
{
	// for (const FIntVector& Coord : Chain)
	// {
	// 	//TODO Replace with my custom actor adding Activate RBD functionality
	// 	if (AActor** ActorPtr =HexMap.Find(Coord))
	// 	{
	// 		// (*ActorPtr)->ActivateRBD();
	// 	}
	// }
		
		//delayed activation along the chain
		for (int32 i = 0; i < Chain.Num(); i++)
		{
			FTimerHandle Handle;

			GetWorld()->GetTimerManager().SetTimer(
				Handle,
				FTimerDelegate::CreateLambda(
					[this, Chain, i]()
					{
						if (AMyHexPillar** MyHexPillarActorPtr =HexMap.Find(Chain[i]))
						{
							UKismetSystemLibrary::PrintString(GetWorld(),TEXT("DestroyingActor"));
							(*MyHexPillarActorPtr)->ActivateAnimation();
							HexMap.Remove(Chain[i]);
						}
					}),i * 1.f,false);
		}
	
}

void AMyHexPlatform::GenerateAndActivateChainFromRandomSelectedGrid()
{

	TArray<FIntVector> Keys;
	HexMap.GetKeys(Keys);

	if (Keys.Num() == 0)
	{
		return;
	}

	const FIntVector RandomStart =Keys[FMath::RandRange(0, Keys.Num() - 1)];

	const int32 ChainLength = 15;

	TArray<FIntVector> Chain =GenerateChain(ChainLength,RandomStart);

	ActivateChain(Chain);
	// UKismetSystemLibrary::PrintString(GetWorld(),FString::Printf(TEXT("Chain Activated Length: %d"),ChainLength));
	
}
