// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "MyCharBase.h"
#include "MyCharPlayer.generated.h"

class UInputMappingContext;

UCLASS()
class AURA_API AMyCharPlayer : public AMyCharBase
{
	GENERATED_BODY()

public:
	// Sets default values for this character's properties
	AMyCharPlayer();

protected:
	// Called when the game starts or when spawned
	virtual void BeginPlay() override;

public:
	// Called every frame
	virtual void Tick(float DeltaTime) override;
	
	virtual void OnRep_PlayerState() override;
	virtual void PossessedBy(AController* NewController) override;

};
