// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "MyPointCollectionActor.generated.h"

UCLASS()
class AURA_API AMyPointCollectionActor : public AActor
{
	GENERATED_BODY()

public:
	// Sets default values for this actor's properties
	AMyPointCollectionActor();
	
	UPROPERTY(EditAnywhere)
	USceneComponent* Point1;
	UPROPERTY(EditAnywhere)
	USceneComponent* Point2;
	UPROPERTY(EditAnywhere)
	USceneComponent* Point3;
	UPROPERTY(EditAnywhere)
	USceneComponent* Point4;
	UPROPERTY(EditAnywhere)
	USceneComponent* Point5;
	UPROPERTY(EditAnywhere)
	USceneComponent* Point6;
	
	UPROPERTY(EditDefaultsOnly, Category = Billboard)
	UBillboardComponent* BillboardPoint1;
	
	UPROPERTY(EditDefaultsOnly, Category = Billboard)
	UBillboardComponent* BillboardPoint2;
	
	UPROPERTY(EditDefaultsOnly, Category = Billboard)
	UBillboardComponent* BillboardPoint3;
	
	UPROPERTY(EditDefaultsOnly, Category = Billboard)
	UBillboardComponent* BillboardPoint4;
	
	UPROPERTY(EditDefaultsOnly, Category = Billboard)
	UBillboardComponent* BillboardPoint5;
	
	UPROPERTY(EditDefaultsOnly, Category = Billboard)
	UBillboardComponent* BillboardPoint6;
	
	
	UPROPERTY(EditAnywhere)
	TArray<USceneComponent*> Points;
	
	UFUNCTION(BlueprintCallable)
	TArray<USceneComponent*> GetPoints();

	UFUNCTION(BlueprintCallable)
	void RotatePoints(float RandZRot);
	
};
