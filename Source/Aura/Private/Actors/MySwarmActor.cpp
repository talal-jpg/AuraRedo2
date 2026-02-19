// Fill out your copyright notice in the Description page of Project Settings.


#include "Actors/MySwarmActor.h"

#include <string>

#include "Actors/MySwarmManagerActor.h"
#include "Components/SplineComponent.h"
#include "Kismet/GameplayStatics.h"
#include "Kismet/KismetSystemLibrary.h"
#include "Misc/MapErrors.h"
#include "Net/UnrealNetwork.h"

// Sets default values
AMySwarmActor::AMySwarmActor()
{
	PrimaryActorTick.bCanEverTick = true;
	bReplicates=true;
	SetNetUpdateFrequency(.5f);
}

// Called when the game starts or when spawned
void AMySwarmActor::BeginPlay()
{
	Super::BeginPlay();
	if (!SplineToFollow)
	{
		TArray<AActor*> MySwarmManagerActor;
		UGameplayStatics::GetAllActorsOfClass(this,AMySwarmManagerActor::StaticClass(),MySwarmManagerActor);
		AMySwarmManagerActor* MySwarmManager=Cast<AMySwarmManagerActor>(MySwarmManagerActor[0]);
		if (MySwarmManagerActor.Num()==0)
		{
			UKismetSystemLibrary::PrintString(this,"No SwarmManagerActor Found");
		}
		else
		{
			SplineToFollow=MySwarmManager->SplineComponents[SplineIndex];
		}
	}
}

// Called every frame
void AMySwarmActor::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);
	PredictivelyMoveAlongSpline();
}

void AMySwarmActor::OnRep_UpdateServerDist()
{
	ServerDistUpdatedTimeStamp=GetWorld()->GetTimeSeconds();
	// UKismetSystemLibrary::PrintString(GetWorld(),std::to_string(ServerDistAlongSpline).c_str());
}

void AMySwarmActor::PredictivelyMoveAlongSpline()
{
	if (!GetWorld() || !SplineToFollow)return;
	FVector NewLocation;
	if (HasAuthority())
	{
		ServerDistAlongSpline=Speed*GetWorld()->GetTimeSeconds();
		NewLocation=SplineToFollow->GetLocationAtDistanceAlongSpline(ServerDistAlongSpline,ESplineCoordinateSpace::World);
	}
	else
	{
		// ENetRole NetRole=GetLocalRole();
		// FString Str=StaticEnum<ENetRole>()->GetNameStringByValue(NetRole);
		// UKismetSystemLibrary::PrintString(this,Str);
		PredictedDistAlongSpline= ServerDistAlongSpline+(Speed*(GetWorld()->GetTimeSeconds()-ServerDistUpdatedTimeStamp));
		// PredictedDistAlongSpline= Speed*(GetWorld()->GetTimeSeconds());
		if (PredictedDistAlongSpline>.999)
		{
			//Explode
			
			
		}
		NewLocation=SplineToFollow->GetLocationAtDistanceAlongSpline(PredictedDistAlongSpline,ESplineCoordinateSpace::World);
	}
	SetActorLocation(NewLocation);
}

void AMySwarmActor::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(AMySwarmActor, ServerDistAlongSpline);
	DOREPLIFETIME_CONDITION(AMySwarmActor, Speed,COND_InitialOnly);
	DOREPLIFETIME_CONDITION(AMySwarmActor, SplineIndex,COND_InitialOnly);
}

