// Fill out your copyright notice in the Description page of Project Settings.


#include "MyAnimInstance.h"

#include "AbilitySystemComponent.h"
#include "VectorTypes.h"
#include "Abilities/GameplayAbilityTargetTypes.h"
#include "AbilitySystem/Abilities/GA_GrappleSwing2.h"
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
#include "Materials/Material.h"
#include "Materials/MaterialInterface.h"
#include "Materials/MaterialInstance.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "NiagaraComponent.h"
#include "NiagaraFunctionLibrary.h"
#include "NiagaraSystem.h"
#include "PostProcess/PostProcessMaterialInputs.h"
#include "TimerManager.h"

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
	if (bIsSwinging)
	{
		// Holds the last value when there is no swing, so blending out doesn't pop
		float Phase=0.f;
		if (UGA_GrappleSwing2::GetGrappleSwing2Phase(MyCharPlayer,Phase))
		{
			SwingPhase=Phase;
			UKismetSystemLibrary::PrintString(this,std::to_string(SwingPhase).c_str());
		}
		else if (MyCharPlayer->GetLocalRole()==ROLE_SimulatedProxy)
		{
			// Other players' swings: the server's value, smoothed between net updates
			SwingPhase=FMath::FInterpTo(SwingPhase,MyCharPlayer->ReplicatedSwingPhase/127.f,DeltaSeconds,20.f);
			// UKismetSystemLibrary::PrintString(GetOwningActor(),std::to_string(SwingPhase).c_str());
		}
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
	// FOnDeathDelegateSignature is a dynamic delegate: AddDynamic, not AddUObject
	MyCharPlayer->GetOnDeathDelegate().AddDynamic(this,&ThisClass::OnDeathCallback);
	
}

void UMyAnimInstance::NativeUninitializeAnimation()
{
	Super::NativeUninitializeAnimation();
	if (UWorld* World=GetWorld())
	{
		World->GetTimerManager().ClearTimer(DisintegrateTimerHandle);
	}
	if (ASC)
	{
		ASC->RegisterGameplayTagEvent(MyTags::State_Shooting,EGameplayTagEventType::NewOrRemoved).RemoveAll(this);
		ASC->RegisterGameplayTagEvent(MyTags::Ability_Beam,EGameplayTagEventType::NewOrRemoved).RemoveAll(this);
		ASC->RegisterGameplayTagEvent(MyTags::State_Boosting,EGameplayTagEventType::NewOrRemoved).RemoveAll(this);
		ASC->RegisterGameplayTagEvent(MyTags::Event_Swing,EGameplayTagEventType::NewOrRemoved).RemoveAll(this);
	}
	if (MyCharPlayer)
	{
		MyCharPlayer->OnMovementModeChangedDelegate.RemoveDynamic(this,&ThisClass::OnMovementModeChanged);
		MyCharPlayer->GetOnDeathDelegate().RemoveDynamic(this,&ThisClass::OnDeathCallback);
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

void UMyAnimInstance::SwingTagCountChangeCallback(FGameplayTag Tag, int32 TagCount)
{
	bIsSwinging=TagCount>0;
}

void UMyAnimInstance::OnDeathCallback(AActor* DeadActor)
{
	bIsDead=true;
	DeathVelocity=DeadActor ? DeadActor->GetVelocity() : (GetOwningActor() ? GetOwningActor()->GetVelocity() : FVector::ZeroVector);
	// Runs on every machine (the death delegate is broadcast from a multicast), so each one plays its own FX
	if (DisintegrateDelay>0.f && GetWorld())
	{
		GetWorld()->GetTimerManager().SetTimer(DisintegrateTimerHandle,this,&ThisClass::StartDisintegrate,DisintegrateDelay,false);
		return;
	}
	StartDisintegrate();
}

void UMyAnimInstance::StartDisintegrate()
{
	USkeletalMeshComponent* Mesh=GetSkelMeshComponent();
	UWorld* World=GetWorld();
	if (!Mesh || !World)return;
	
	// The system samples the skeletal mesh it is attached to
	if (UNiagaraSystem* System=DisintegrateSystem.LoadSynchronous())
	{
		// Not auto-activated, so User.DeathVelocity is set before the system's first tick
		if (UNiagaraComponent* FX=UNiagaraFunctionLibrary::SpawnSystemAttached(System,Mesh,NAME_None,FVector::ZeroVector,FRotator::ZeroRotator,
			EAttachLocation::KeepRelativeOffset,true,false))
		{
			FX->SetVariableVec3(TEXT("DeathVelocity"),DeathVelocity);
			FX->Activate(true);
		}
	}
	
	// One value drives the dissolve on every material slot (no per-slot dynamic materials, no UVs involved).
	// The material's Time node is world game time, so pass the same clock.
	const float DeathTime=FMath::Max(World->GetTimeSeconds(),KINDA_SMALL_NUMBER);
	Mesh->SetCustomPrimitiveDataFloat(DisintegrateDataIndex,DeathTime);
	// Attached meshes that use the body's materials (e.g. the jetpack) dissolve with it
	TSet<UMaterial*> BodyBaseMaterials;
	for (int32 Slot=0; Slot<Mesh->GetNumMaterials(); ++Slot)
	{
		if (UMaterialInterface* Material=Mesh->GetMaterial(Slot))
		{
			BodyBaseMaterials.Add(Material->GetBaseMaterial());
		}
	}
	TArray<USceneComponent*> Children;
	Mesh->GetChildrenComponents(true,Children);
	for (USceneComponent* Child : Children)
	{
		UMeshComponent* ChildMesh=Cast<UMeshComponent>(Child);
		if (!ChildMesh)continue;
		for (int32 Slot=0; Slot<ChildMesh->GetNumMaterials(); ++Slot)
		{
			UMaterialInterface* Material=ChildMesh->GetMaterial(Slot);
			if (Material && BodyBaseMaterials.Contains(Material->GetBaseMaterial()))
			{
				ChildMesh->SetCustomPrimitiveDataFloat(DisintegrateDataIndex,DeathTime);
				break;
			}
		}
	}
	
	if (DisintegrateSwapDelay>0.f)
	{
		World->GetTimerManager().SetTimer(DisintegrateTimerHandle,this,&ThisClass::SwapToDisintegrateMaterial,DisintegrateSwapDelay,false);
		return;
	}
	SwapToDisintegrateMaterial();
}

void UMyAnimInstance::SwapToDisintegrateMaterial()
{
	USkeletalMeshComponent* Mesh=GetSkelMeshComponent();
	UMaterialInterface* BodyMaterial=DisintegrateBodyMaterial.LoadSynchronous();
	UMaterialInterface* DissolveParent=DisintegrateDissolveParent.LoadSynchronous();
	if (!Mesh)return;
	
	// Slots based on the same material as the dissolve parent (M_MasterMech) get a dynamic copy of the parent carrying
	// the slot's own textures and values; anything else falls back to the shared body material.
	// Attached meshes only swap slots that use the same base materials as the body (leaves e.g. the edge fog cube alone).
	auto MakeDissolve=[&](UMeshComponent* Owner, UMaterialInterface* Current)->UMaterialInterface*
	{
		UMaterialInstance* CurrentInstance=Cast<UMaterialInstance>(Current);
		if (DissolveParent && CurrentInstance && Current->GetBaseMaterial()->GetName()==TEXT("M_MasterMech"))
		{
			UMaterialInstanceDynamic* Dynamic=UMaterialInstanceDynamic::Create(DissolveParent,Owner);
			Dynamic->CopyParameterOverrides(CurrentInstance);
			return Dynamic;
		}
		return BodyMaterial;
	};
	TSet<UMaterial*> BodyBaseMaterials;
	for (int32 Slot=0; Slot<Mesh->GetNumMaterials(); ++Slot)
	{
		UMaterialInterface* Material=Mesh->GetMaterial(Slot);
		if (!Material)continue;
		BodyBaseMaterials.Add(Material->GetBaseMaterial());
		if (UMaterialInterface* Replacement=MakeDissolve(Mesh,Material))
		{
			Mesh->SetMaterial(Slot,Replacement);
		}
	}
	TArray<USceneComponent*> Children;
	Mesh->GetChildrenComponents(true,Children);
	for (USceneComponent* Child : Children)
	{
		UMeshComponent* ChildMesh=Cast<UMeshComponent>(Child);
		if (!ChildMesh)continue;
		for (int32 Slot=0; Slot<ChildMesh->GetNumMaterials(); ++Slot)
		{
			UMaterialInterface* Material=ChildMesh->GetMaterial(Slot);
			if (Material && BodyBaseMaterials.Contains(Material->GetBaseMaterial()))
			{
				if (UMaterialInterface* Replacement=MakeDissolve(ChildMesh,Material))
				{
					ChildMesh->SetMaterial(Slot,Replacement);
				}
			}
		}
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
	
	SwingTagCountChangeDelegateHandle= ASC->RegisterGameplayTagEvent(MyTags::Event_Swing,EGameplayTagEventType::NewOrRemoved).AddUObject(this,&UMyAnimInstance::SwingTagCountChangeCallback);
	// The tag may already be on when the ASC arrives (late join, respawn)
	bIsSwinging=ASC->HasMatchingGameplayTag(MyTags::Event_Swing);
	
}
				
