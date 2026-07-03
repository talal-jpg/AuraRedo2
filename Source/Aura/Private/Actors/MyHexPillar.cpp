// Fill out your copyright notice in the Description page of Project Settings.


#include "Actors/MyHexPillar.h"

#include "TimerManager.h"
#include "Components/SkeletalMeshComponent.h"


// Sets default values
AMyHexPillar::AMyHexPillar()
{
	PrimaryActorTick.bCanEverTick = false;
	
	StaticMeshComponent=CreateDefaultSubobject<UStaticMeshComponent>(TEXT("StaticMeshComponent"));
	SetRootComponent(StaticMeshComponent);
	
	
}

// Called when the game starts or when spawned
void AMyHexPillar::BeginPlay()
{
	Super::BeginPlay();
	
	StaticMeshComponent->SetVisibility(true);
	StaticMeshComponent->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
	
	// SkeletalMeshComponent->SetVisibility(false);
	// SkeletalMeshComponent->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	
}

void AMyHexPillar::ActivateAnimation()
{
	SkeletalMeshComponent=NewObject<USkeletalMeshComponent>(this, USkeletalMeshComponent::StaticClass(),TEXT("SkeletalMeshComponent"));
	SkeletalMeshComponent->SetSkeletalMesh(SkeletalMesh);
	SkeletalMeshComponent->SetAnimationMode(EAnimationMode::AnimationSingleNode);	
	SkeletalMeshComponent->SetupAttachment(StaticMeshComponent);
	SkeletalMeshComponent->RegisterComponent();
	
	StaticMeshComponent->SetVisibility(false);
	StaticMeshComponent->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	
	SkeletalMeshComponent->SetVisibility(true);
	SkeletalMeshComponent->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
	
	SkeletalMeshComponent->PlayAnimation(RbdAnimSeq,false);
	
	FTimerHandle TimerHandle;
	GetWorld()->GetTimerManager().SetTimer(TimerHandle,FTimerDelegate::CreateLambda(
	[this]()
	{
		Destroy();
	}
		)
	,1,false,7);
	
	
}

