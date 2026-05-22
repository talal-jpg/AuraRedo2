// Fill out your copyright notice in the Description page of Project Settings.


#include "AbilitySystem/Abilities/GA_Electrocute.h"

#include "AbilitySystemBlueprintLibrary.h"
#include "AbilitySystemGlobals.h"
#include "Interfaces/MyCombatInterface.h"
#include "Kismet/KismetSystemLibrary.h"

void UGA_Electrocute::ActivateAbility(const FGameplayAbilitySpecHandle Handle,
                                      const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo,
                                      const FGameplayEventData* TriggerEventData)
{
	Super::ActivateAbility(Handle, ActorInfo, ActivationInfo, TriggerEventData);
}

void UGA_Electrocute::TraceFirstTarget()
{
	if (GetAvatarActorFromActorInfo()->Implements<UMyCombatInterface>())
	{
		OwnerWeaponSocketLocation=IMyCombatInterface::Execute_GetCombatSocketLocation(GetAvatarActorFromActorInfo());
		TArray<AActor*> IgnoredActors;
		FHitResult HitResult;
		UKismetSystemLibrary::SphereTraceSingle(this,OwnerWeaponSocketLocation,FirstHitActorLocation,10,ETraceTypeQuery::TraceTypeQuery1,false,IgnoredActors,EDrawDebugTrace::None,HitResult,true);
		if (HitResult.bBlockingHit)
		{
			FirstHitActor=HitResult.GetActor();
			FirstHitActorLocation=HitResult.ImpactPoint;
		}
	}
}

void UGA_Electrocute::AddAdditionalTargets()
{
	
	if (FirstHitActor==nullptr)return;
	// FOverlapResult	OverlapResult;
	// OverlapResult
	//Getting Actors with combatIF in a radius
	TArray<FOverlapResult> OverlapResults;
	const FCollisionShape& SphereShape = FCollisionShape::MakeSphere(100);
	FCollisionQueryParams CollisionQueryParams;
	CollisionQueryParams.AddIgnoredActor(FirstHitActor);
	CollisionQueryParams.AddIgnoredActor(GetAvatarActorFromActorInfo());
	
	//Should not get world by GEngine in a multiplayer
	if (UWorld* World=GetWorld())
	{
		World->OverlapMultiByChannel(OverlapResults,FirstHitActorLocation,FQuat::Identity,ECC_Visibility,FCollisionShape::MakeSphere(1000),CollisionQueryParams);
		
		// UKismetSystemLibrary::DrawDebugSphere(World,FirstHitActorLocation,1000,10,FColor::Red,30,0.1f);
	}
	
	for (FOverlapResult OverlapResult:OverlapResults)
	{
		if (OverlapResult.GetActor()->Implements<UMyCombatInterface>())
		{
			AdditionalTargets.AddUnique(OverlapResult.GetActor());
		}
	}
}
