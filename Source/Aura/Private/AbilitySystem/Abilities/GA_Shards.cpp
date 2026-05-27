// Fill out your copyright notice in the Description page of Project Settings.


#include "AbilitySystem/Abilities/GA_Shards.h"

#include "Interfaces/MyCombatInterface.h"


void UGA_Shards::GetAliveActorsWithinRadius(FVector Location,float Radius, UPARAM(ref)TArray<AActor*>& OutActors)
{
	TArray<FOverlapResult> OverlapResults;
	FCollisionQueryParams CollisionQueryParams;
	TArray<AActor*> AliveActors;
	GetWorld()->OverlapMultiByChannel(OverlapResults,Location,FRotator(0,0,0).Quaternion(),ECC_Visibility,FCollisionShape::MakeSphere(100),CollisionQueryParams);
	for (FOverlapResult OverlapResult:OverlapResults)
	{
		if (OverlapResult.GetActor()->Implements<UMyCombatInterface>() && !IMyCombatInterface::Execute_IsDead(OverlapResult.GetActor()))
		{
			AliveActors.AddUnique(OverlapResult.GetActor());
		}
	}
	OutActors=AliveActors;
}
