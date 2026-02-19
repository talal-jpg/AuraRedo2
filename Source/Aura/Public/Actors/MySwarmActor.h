// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Components/StaticMeshComponent.h"
#include "GameFramework/Actor.h"
#include "MySwarmActor.generated.h"

class USplineComponent;

UCLASS()
class AURA_API AMySwarmActor : public AActor
{
	GENERATED_BODY()
	
public:	
	// Sets default values for this actor's properties
	AMySwarmActor();

protected:
	// Called when the game starts or when spawned
	virtual void BeginPlay() override;

public:	
	// Called every frame
	virtual void Tick(float DeltaTime) override;

	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
	
	
	UPROPERTY()
	USplineComponent* SplineToFollow;
	
	float PredictedDistAlongSpline=0.0f;
	
	UPROPERTY(ReplicatedUsing = OnRep_UpdateServerDist)
	float ServerDistAlongSpline=0.0f;
	
	float ServerDistUpdatedTimeStamp=0.0f;
	
	UPROPERTY(Replicated)
	float Speed=0.0f;
	
	UPROPERTY(Replicated)
	int32 SplineIndex=0;
	
	int32 Id;

	UFUNCTION()
	void OnRep_UpdateServerDist();
	
	void PredictivelyMoveAlongSpline();
};
