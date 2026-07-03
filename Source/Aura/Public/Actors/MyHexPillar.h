// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "MyHexPillar.generated.h"

class USkeletalMesh;

UCLASS()
class AURA_API AMyHexPillar : public AActor
{
	GENERATED_BODY()

public:
	// Sets default values for this actor's properties
	AMyHexPillar();

	void ActivateAnimation();
	
protected:
	// Called when the game starts or when spawned
	virtual void BeginPlay() override;
	
	UPROPERTY(EditAnywhere)
	UStaticMeshComponent* StaticMeshComponent;
	
	UPROPERTY(EditAnywhere)
	USkeletalMeshComponent* SkeletalMeshComponent;
	
	UPROPERTY(EditAnywhere)
	UAnimationAsset* RbdAnimSeq;
	
	UPROPERTY(EditAnywhere)
	USkeletalMesh* SkeletalMesh;
	
	
};

