// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Runtime/AIModule/Classes/AIController.h"
#include "MyAiController.generated.h"

class UBehaviorTreeComponent;

UCLASS()
class AURA_API AMyAiController : public AAIController
{
	GENERATED_BODY()

public:
	// Sets default values for this actor's properties
	AMyAiController();

protected:

public:
	
	UPROPERTY()
	UBehaviorTreeComponent* BehaviorTree;
};
