// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "BehaviorTree/BTService.h"
#include "BehaviorTree/Services/BTService_BlueprintBase.h"
#include "BTService_FindNearestPlayer.generated.h"

/**
 * 
 */
UCLASS(Blueprintable,BlueprintType)
class AURA_API UBTService_FindNearestPlayer : public UBTService_BlueprintBase
{
	GENERATED_BODY()
	
	virtual void TickNode(UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory, float DeltaSeconds) override;
	
public:
	UPROPERTY(EditAnywhere,BLueprintReadWrite)
	FBlackboardKeySelector SelfActor;
	
	UPROPERTY(EditAnywhere,BLueprintReadWrite)
	FBlackboardKeySelector NearestPlayer;
	
	UPROPERTY(EditAnywhere,BLueprintReadWrite)
	FBlackboardKeySelector NearestPlayerLoc;
	
	UPROPERTY(EditAnywhere,BLueprintReadWrite)
	FBlackboardKeySelector NearestPlayerDist;
};
