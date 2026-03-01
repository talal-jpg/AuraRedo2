// Fill out your copyright notice in the Description page of Project Settings.


#include "BTService_FindNearestPlayer.h"

#include <string>

#include "AIController.h"
#include "Actors/MyEffectActor.h"
#include "BehaviorTree/BTFunctionLibrary.h"
#include "Character/MyCharPlayer.h"
#include "Kismet/GameplayStatics.h"

void UBTService_FindNearestPlayer::TickNode(UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory, float DeltaSeconds)
{
	Super::TickNode(OwnerComp, NodeMemory, DeltaSeconds);
	TArray<AActor*> PlayerActors;
	UGameplayStatics::GetAllActorsOfClassWithTag(this,AMyCharPlayer::StaticClass(),FName("Player"),PlayerActors);
	AActor* MyActor=UBTFunctionLibrary::GetBlackboardValueAsActor(this,SelfActor);
	// if (!MyActor)
	// {
	// 	UKismetSystemLibrary::PrintString(this,"No SelfActor Found");
	// 	return;
	// }
	// FVector MyLoc=MyActor->GetActorLocation();
	FVector MyLoc=OwnerComp.GetAIOwner()->GetPawn()->GetActorLocation();
	float NearestDist= TNumericLimits<float>::Max();
	FVector NearestLoc=FVector(0,0,0);
	AActor* TargetPlayer=nullptr;
	
	for (AActor* PlayerActor : PlayerActors)
	{
		FVector PlayerLoc=PlayerActor->GetActorLocation();
		float Dist=FVector::Dist(MyLoc,PlayerLoc);
		if (Dist<NearestDist)
		{
			NearestDist=Dist;
			NearestLoc=PlayerLoc;
			TargetPlayer=PlayerActor;
		}
	}
	
	UBlackboardComponent* BBComp=OwnerComp.GetAIOwner()->GetBlackboardComponent();
	
	// UKismetSystemLibrary::PrintString(this,std::to_string(NearestDist).c_str());
	UBTFunctionLibrary::SetBlackboardValueAsObject(this,NearestPlayer,TargetPlayer);
	UBTFunctionLibrary::SetBlackboardValueAsVector(this,NearestPlayerLoc,NearestLoc);
	UBTFunctionLibrary::SetBlackboardValueAsFloat(this,NearestPlayerDist,NearestDist);
	
}
