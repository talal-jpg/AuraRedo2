// Fill out your copyright notice in the Description page of Project Settings.


#include "AbilitySystem/Abilities/GA_Projectile.h"

#include "AbilitySystemBlueprintLibrary.h"
#include "AbilitySystemComponent.h"
#include "AbilitySystem/Data/MyGameplayTags.h"
#include "Actors/MyProjectile.h"
#include "GameFramework/ProjectileMovementComponent.h"
#include "Interfaces/MyCombatInterface.h"
#include "Kismet/GameplayStatics.h"
#include "Kismet/KismetMathLibrary.h"

void UGA_Projectile::ActivateAbility(const FGameplayAbilitySpecHandle Handle,
                                     const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo,
                                     const FGameplayEventData* TriggerEventData)
{
	Super::ActivateAbility(Handle, ActorInfo, ActivationInfo, TriggerEventData);
}

void UGA_Projectile::SpawnProjectile(AActor* AvatarActor,UAbilitySystemComponent* ASC,FVector TargetLocation, AActor* HomingTarget)
{
	// AActor* AvatarActor= ActorInfo->AvatarActor.Get();
	// UAbilitySystemComponent* ASC= ActorInfo->AbilitySystemComponent.Get();
	IMyCombatInterface* CombatInterface=Cast<IMyCombatInterface>(AvatarActor);
	if (!AvatarActor->Implements<UMyCombatInterface>())return;
		
	float Level=IMyCombatInterface::Execute_GetLevel(AvatarActor);
	FVector SpawnLocation=IMyCombatInterface::Execute_GetCombatSocketLocation(AvatarActor);
	
	//SpawnXform
	FTransform SpawnXform=FTransform();
	SpawnXform.SetLocation(SpawnLocation);
	FVector ToTarget=TargetLocation-SpawnLocation;
	ToTarget.Normalize();
	ToTarget.Z=0;
	
	
	//GESpec
	FGameplayEffectContextHandle GEContextHandle=ASC->MakeEffectContext();
	
	GEContextHandle.AddInstigator(AvatarActor,AvatarActor);
	GEContextHandle.AddSourceObject(AvatarActor);
	FGameplayEffectSpecHandle GESpecHandle=ASC->MakeOutgoingSpec(DamageEffectClass,Level,GEContextHandle);
	float Magnitude=Damage.GetValueAtLevel(GetAbilityLevel());
	// UKismetSystemLibrary::PrintString(GetWorld(),TEXT("Damage: ") + FString::FromInt(Magnitude));
	UAbilitySystemBlueprintLibrary::AssignTagSetByCallerMagnitude(GESpecHandle,MyTags::SetDamageByCaller,Magnitude);
	
	FGameplayEffectContextHandle GEContextHandle2=ASC->MakeEffectContext();
	
	
	ASC->ExecuteGameplayCue(MyTags::GameplayCue_FireballBurst,GEContextHandle2);
	
	for (int32 i=0;i<NumProjectiles;i++)
	{
		const float Step = AngleSpan / (NumProjectiles - 1);
		float Angle = -AngleSpan * 0.5f + Step * i;
		UKismetSystemLibrary::PrintString(GetWorld(),FString::Printf(TEXT("Angle: %f"),Angle));
		FVector RotatedToTarget=ToTarget.RotateAngleAxis(Angle,FVector::UpVector);
		
		// UKismetSystemLibrary::DrawDebugArrow(this,SpawnLocation,SpawnLocation+RotatedToTarget*1000,10,FLinearColor::Yellow,30,10*i);
		
		FRotator Rot=RotatedToTarget.Rotation();
		SpawnXform.SetRotation(Rot.Quaternion());
		//SpawnProj
		AMyProjectile* MyProjectile=GetWorld()->SpawnActorDeferred<AMyProjectile>(ProjectileClass,SpawnXform,nullptr);
		MyProjectile->ProjectileMovementComponent->bIsHomingProjectile=true;
		MyProjectile->SetLifeSpan(5.f);
		
		//Homing Target Actor* Set here 
		if (HomingTarget !=nullptr)
		{
			MyProjectile->HomingTargetActor=HomingTarget;
			MyProjectile->ProjectileMovementComponent->HomingTargetComponent= HomingTarget->GetRootComponent();
		}
		else
		{
			USceneComponent* SceneComp=NewObject<USceneComponent>();
			MyProjectile->ProjectileMovementComponent->HomingTargetComponent=SceneComp;
		}
		
		MyProjectile->ProjectileMovementComponent->HomingAccelerationMagnitude= 5000;
			
		
		MyProjectile->DamageEffectSpec=*GESpecHandle.Data.Get();
		MyProjectile->FinishSpawning(SpawnXform);
	}
	
}
