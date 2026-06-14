// Fill out your copyright notice in the Description page of Project Settings.


#include "Actors/MyHexPlatform.h"

#include "Actors/MyEffectActor.h"
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
	
	FTransform Transform;
	
	TArray<FHexCoord> HexCoords=GenerateHexGrid(10);
	
	for (auto HexCoord:HexCoords)
	{
		FVector2D Loc2d=HexToWorld(HexCoord.Q,HexCoord.R,HexRadius);
		Transform.SetLocation(FVector(Loc2d.X,Loc2d.Y,0));
		
		GetWorld()->SpawnActor<AActor>(HexagonPillarActorClass,Transform);
	}
	
}



TArray<FHexCoord> AMyHexPlatform::GenerateHexGrid(int32 GridSize)
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


FVector2D AMyHexPlatform::HexToWorld(int32 Q, int32 R, float HexRadius)
{
	const float X = HexRadius * FMath::Sqrt(3.f) * (Q + R * 0.5f);
	const float Y = HexRadius * 1.5f * R;

	return FVector2D(X, Y);
}
