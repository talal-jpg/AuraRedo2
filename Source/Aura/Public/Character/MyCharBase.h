// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "MyCharBase.generated.h"

UCLASS(Abstract)
class AURA_API AMyCharBase : public ACharacter
{
	GENERATED_BODY()

public:
	// Sets default values for this character's properties
	AMyCharBase();

protected:
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = Mesh)
	USkeletalMeshComponent* CharMesh;
	
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = Mesh)
	USkeletalMeshComponent* WeaponMesh;

public:	

};
