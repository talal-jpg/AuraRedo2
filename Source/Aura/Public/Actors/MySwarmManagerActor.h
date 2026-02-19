// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "ScalableFloat.h"
#include "GameFramework/Actor.h"
#include "MySwarmManagerActor.generated.h"

class AMySwarmActor;
class USplineComponent;

DECLARE_DELEGATE(FOnSplineConstructedDelegateSignature);
UCLASS()
class AURA_API AMySwarmManagerActor : public AActor
{
	GENERATED_BODY()
	
public:	
	// Sets default values for this actor's properties
	AMySwarmManagerActor();
	
	virtual void GetLifetimeReplicatedProps(TArray<class FLifetimeProperty>& OutLifetimeProps) const override;

protected:
	// Called when the game starts or when spawned
	virtual void BeginPlay() override;
	
	FOnSplineConstructedDelegateSignature OnSplineConstructedDelegate;
	

public:	
	// Called every frame
	virtual void Tick(float DeltaTime) override;
	
	USplineComponent* ConstructSpline(int32 Id);
	
	void ConstructSplines(int32 InNumSplines);
	
	int32 SplineCount=0;
	
	bool bSplineConstructed=false;
	
	
	//SplineParams
	// UPROPERTY(BlueprintReadWrite,EditAnywhere)
	// USplineComponent* SplineComponent;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite)
	TArray<USplineComponent*> SplineComponents;
	
	
	UPROPERTY(EditAnywhere,Replicated)
	int32 TotalNumOfSplinesToConstruct=5;
	
	UPROPERTY(ReplicatedUsing = OnRep_UpdateLocation,EditAnywhere,meta=(MakeEditWidget = true))
	FVector StartLocation;

	UPROPERTY(ReplicatedUsing = OnRep_UpdateLocation)
	FVector EndLocation;
	
	UPROPERTY(ReplicatedUsing = OnRep_UpdateLocation)
	FVector InterpedEndLocation;
	
	UPROPERTY(Replicated,EditAnywhere,Category="Spiral")
	float RotateIdOffsetMult=1.f;
	
	UPROPERTY(Replicated,EditAnywhere,Category="Spiral")
	float SpiralIdOffsetMult=1.f;
	
	UPROPERTY(Replicated,EditAnywhere,Category="Spiral")
	float RotateNoiseAmplitude=0.f;
	
	UPROPERTY(Replicated,EditAnywhere,Category="Spiral")
	float RotateNoiseFrequency=0.f;
	
	UPROPERTY(Replicated,EditAnywhere,Category="Spiral")
	float RotateNoiseOffsetSpeed=0.f;
	
	UPROPERTY(Replicated,EditAnywhere,Category="Spiral")
	float SpiralNoiseAmplitude=0.f;
	
	UPROPERTY(Replicated,EditAnywhere,Category="Spiral")
	float SpiralNoiseFrequency=0.f;
	
	UPROPERTY(Replicated,EditAnywhere,Category="Spiral")
	float SpiralNoiseOffsetSpeed=0.f;
	
	UPROPERTY(Replicated,EditAnywhere,Category="Spiral")
	FScalableFloat SpiralRamp;
	
	UPROPERTY(Replicated,EditAnywhere,Category="Spiral")
	FScalableFloat RotateRamp;
	
	UPROPERTY(Replicated,EditAnywhere,Category="Spiral")
	FScalableFloat EndsSnapRamp;
	
	UPROPERTY(Replicated,EditAnywhere,Category="Spiral")
	int32 SpiralTurns=5;
	
	UPROPERTY(Replicated,EditAnywhere,Category="Spiral")
	int32 RotateTurns=5;
	
	UPROPERTY(Replicated,EditAnywhere,Category="Spiral")
	float SpiralRadiusBase=1000.f;
	
	UPROPERTY(Replicated,EditAnywhere,Category="Spiral")
	float RotateRadiusBase=1000.f;
	
	UPROPERTY(Replicated,EditAnywhere,Category="Spiral")
	float SpiralOffsetSpeed=1.f;
	
	UPROPERTY(Replicated,EditAnywhere,Category="Spiral")
	float RotateOffsetSpeed=1.f;
	
	void SpawnSwarmActor(float InSpeed,int32 Id,int32 SplineToChoose);
	
	void SpawnSwarmActors(int32 InCount);
	
	
	UPROPERTY(EditAnywhere)
	TSubclassOf<AMySwarmActor> SwarmActorClass;
	
	int32 SwarmCount=0;
	
	
	UFUNCTION()
	void OnRep_UpdateLocation();
	
	
	UPROPERTY(EditAnywhere,Replicated)
	AActor* ActorToFollow;
	
	UPROPERTY(EditAnywhere,Replicated)
	float SwarmMinSpeed=2000.f;
	UPROPERTY(EditAnywhere,Replicated)
	float SwarmMaxSpeed=4000.f;
	
	
	
};
