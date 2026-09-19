// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "MyHexPlatform.generated.h"

class AMyHexPillar;

struct FHexCoord
{
	int32 Q;
	int32 R;
	int32 S;
};

UCLASS()
class AURA_API AMyHexPlatform : public AActor
{
	GENERATED_BODY()

public:
	// Sets default values for this actor's properties
	AMyHexPlatform();

protected:
	// Called when the game starts or when spawned
	virtual void BeginPlay() override;

public:
	
	TArray<FHexCoord> GenerateHexGrid();
	
	FVector2D HexToWorld(int32 Q, int32 R, float HexRadius);
	
	UPROPERTY(EditAnywhere)
	int32 GridSize=0;
	
	UPROPERTY(EditAnywhere)
	int32 HexRadius=1;
	
	UPROPERTY(EditAnywhere)
	TSubclassOf<AMyHexPillar> HexagonPillarActorClass;
	
	UPROPERTY()
	TMap<FIntVector,AMyHexPillar*> HexMap;
	
	
	TArray<FIntVector> ConsumedTiles;
	
	TArray<FIntVector> GetNeighbors(const FIntVector& Hex);
	
	TArray<FIntVector> GenerateChain(int32 Length,FIntVector StartHex);
	
	void ActivateChain(const TArray<FIntVector>& Chain);
	
	void GenerateAndActivateChainFromRandomSelectedGrid();
	
	//Preview Pillars
#if WITH_EDITORONLY_DATA
	UPROPERTY(Transient)
	TArray<TObjectPtr<AMyHexPillar>> PreviewPillars;
#endif
	
	virtual void OnConstruction(const FTransform& Transform) override;
	
};
