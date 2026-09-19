// Fill out your copyright notice in the Description page of Project Settings.


#include "MyAnimInstance.h"

#include "AbilitySystemComponent.h"
#include "VectorTypes.h"
#include "Abilities/GameplayAbilityTargetTypes.h"
#include "AbilitySystem/MyAbilitySystemComponent.h"
#include "AbilitySystem/MyAttributeSet.h"
#include "AbilitySystem/Data/MyGameplayTags.h"
#include "Character/MyCharBase.h"
#include "Character/MyCharPlayer.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/World.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/GameStateBase.h"
#include "GameFramework/MovementComponent.h"
#include "Kismet/KismetSystemLibrary.h"
#include "PostProcess/PostProcessMaterialInputs.h"

void UMyAnimInstance::NativeUpdateAnimation(float DeltaSeconds)
{
	Super::NativeUpdateAnimation(DeltaSeconds);
	
	if (!MyCharPlayer ||!MovementComponent)return;
	Velocity=MovementComponent->Velocity;
	Speed=Velocity.Length();
	VelocityCharSpace=MyCharPlayer->VelocityCharSpace;
	ForwardVec=MyCharPlayer->GetActorRotation().Vector();
	ForwardVecChest=MyCharPlayer->ForwardVecChest;
	YawDelta=MyCharPlayer->YawDelta;
	
	if (GetWorld()->GetGameState() && bUpdateServerTime )
	{
		ServerTime=GetWorld()->GetGameState()->GetServerWorldTimeSeconds();
		if (ServerTime>= PhysicsStateSetTimeStamp+PhysicsStateSetDuration)
		{
			bUpdateServerTime=false;
		}
	}
	if (bIsBeaming)
	{
		// ForwardVec=ForwardVec.RotateAngleAxis(90,FVector(0,0,1));
		ForwardVec= MyCharPlayer->GetMesh()->GetComponentTransform().InverseTransformVector(ForwardVec);
		// ForwardVec=MyCharPlayer->GetTransform().InverseTransformVector(ForwardVec);
	}
	if (bIsFlying && bIsBoosting)
	{
		float AmountToLerp=.05;
		TargetLocDelayed= FMath::Lerp(TargetLocDelayed,TargetLoc,AmountToLerp);
		
	}
	if (!bIsShooting && !bIsBoosting)return;
	TargetLoc=MyCharPlayer->TargetLocation;
	
}

void UMyAnimInstance::NativeInitializeAnimation()
{
	Super::NativeInitializeAnimation();
	MyCharPlayer=Cast<AMyCharPlayer>(TryGetPawnOwner());
	if (!MyCharPlayer)return;
	MovementComponent=Cast<UCharacterMovementComponent>(MyCharPlayer->GetMovementComponent());
	if (!MovementComponent)return;
	MyCharPlayer->OnMovementModeChangedDelegate.AddDynamic( this,&ThisClass::OnMovementModeChanged);
}

void UMyAnimInstance::NativeUninitializeAnimation()
{
	Super::NativeUninitializeAnimation();
	if (ASC)
	{
		ASC->RegisterGameplayTagEvent(MyTags::State_Shooting,EGameplayTagEventType::NewOrRemoved).RemoveAll(this);
	}
	if (MyCharPlayer)
	{
		MyCharPlayer->OnMovementModeChangedDelegate.RemoveDynamic(this,&ThisClass::OnMovementModeChanged);
	}
}

void UMyAnimInstance::OnMovementModeChanged(EMovementMode PreviousMovementModeassign)
{
	if (MovementComponent->MovementMode== EMovementMode::MOVE_Walking && MovementComponent->Velocity.Length()>1000 && GetOwningActor()->HasAuthority())
	{
		//TODO PlayMontage Multicast To be converted to c++
	}
	if (MovementComponent->MovementMode== EMovementMode::MOVE_Flying )
	{
		bIsFlying=true;
	}
	else
	{
		bIsFlying=false;
	}
}

void UMyAnimInstance::ShootingTagCountChangeCallback(FGameplayTag Tag, int32 TagCount)
{
	if (TagCount>0)
	{
		bIsShooting=true;
		
		//TODO
		// FireRate= MyCharPlayer->GetMyAttributeSet()->GetAttackSpeed();
		// Create set matching var in CR
	}
	else
	{
		bIsShooting=false;
	}
}

void UMyAnimInstance::BeamTagCountChangeCallback(FGameplayTag Tag, int32 TagCount)
{
	if (TagCount>0)
	{
		bIsBeaming=true;
	}
	else
	{
		bIsBeaming=false;
	}
}

void UMyAnimInstance::BoostingTagCountChangeCallback(FGameplayTag Tag, int32 TagCount)
{
	if (TagCount>0)
	{
		bIsBoosting=true;
		TargetLocDelayed=TargetLoc;
		UKismetSystemLibrary::PrintString(GetOwningActor(),TargetLoc.ToString());
		// UKismetSystemLibrary::PrintString(GetOwningActor(),TargetLoc.ToString());
	}
	else
	{
		bIsBoosting=false;
	}
}

void UMyAnimInstance::InitializeASC(UAbilitySystemComponent* InASC)
{
	if (!InASC || ASC == InASC)
	{
		return;
	}

	ASC = InASC;

	ShootingTagCountChangeDelegateHandle =ASC->RegisterGameplayTagEvent(MyTags::State_Shooting,EGameplayTagEventType::NewOrRemoved).AddUObject(this, &ThisClass::ShootingTagCountChangeCallback);
	
	BeamTagCountChangeDelegateHandle =ASC->RegisterGameplayTagEvent(MyTags::Ability_Beam,EGameplayTagEventType::NewOrRemoved).AddUObject(this,&UMyAnimInstance::BeamTagCountChangeCallback);
	
	BoostingTagCountChangeDelegateHandle= ASC->RegisterGameplayTagEvent(MyTags::State_Boosting,EGameplayTagEventType::NewOrRemoved).AddUObject(this,&UMyAnimInstance::BoostingTagCountChangeCallback);
	
}
				
