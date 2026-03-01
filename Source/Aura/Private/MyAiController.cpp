// Fill out your copyright notice in the Description page of Project Settings.


#include "MyAiController.h"
#include "BehaviorTree/BehaviorTreeComponent.h"
#include "BehaviorTree/BlackboardComponent.h"


// Sets default values
AMyAiController::AMyAiController()
{
	// Set this actor to call Tick() every frame.  You can turn this off to improve performance if you don't need it.
	PrimaryActorTick.bCanEverTick = false;
	BehaviorTree= CreateDefaultSubobject<UBehaviorTreeComponent>(FName("BehaviorTreeComponent"));
	Blackboard= CreateDefaultSubobject<UBlackboardComponent>(FName("BlackboardComponent"));
	
}


