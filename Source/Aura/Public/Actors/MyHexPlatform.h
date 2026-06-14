// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "MyHexPlatform.generated.h"

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
	
	TArray<FHexCoord> GenerateHexGrid(int32 GridSize);
	
	FVector2D HexToWorld(int32 Q, int32 R, float HexRadius);
	
	UPROPERTY(EditAnywhere)
	int32 GridSize=0;
	
	UPROPERTY(EditAnywhere)
	int32 HexRadius=1;
	
	UPROPERTY(EditAnywhere)
	TSubclassOf<AActor> HexagonPillarActorClass;
	
	
};
