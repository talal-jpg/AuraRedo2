// Fill out your copyright notice in the Description page of Project Settings.


#include "Actors/MyTargetDecalActor.h"

#include "Components/DecalComponent.h"


// Sets default values
AMyTargetDecalActor::AMyTargetDecalActor()
{
	// Set this actor to call Tick() every frame.  You can turn this off to improve performance if you don't need it.
	PrimaryActorTick.bCanEverTick = true;
	
	DecalComponent=CreateDefaultSubobject<UDecalComponent>(TEXT("DecalComp"));
	DecalComponent->SetupAttachment(GetRootComponent());
	
}

// Called when the game starts or when spawned
void AMyTargetDecalActor::BeginPlay()
{
	Super::BeginPlay();
	
}

// Called every frame
void AMyTargetDecalActor::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);
}

