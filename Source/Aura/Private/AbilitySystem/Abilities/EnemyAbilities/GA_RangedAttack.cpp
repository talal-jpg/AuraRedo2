// Fill out your copyright notice in the Description page of Project Settings.


#include "AbilitySystem/Abilities/EnemyAbilities/GA_RangedAttack.h"

#include "AbilitySystemComponent.h"
#include "Actors/MyProjectile.h"
#include "Interfaces/MyCombatInterface.h"

void UGA_RangedAttack::ActivateAbility(const FGameplayAbilitySpecHandle Handle,
                                       const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo,
                                       const FGameplayEventData* TriggerEventData)
{
	Super::ActivateAbility(Handle, ActorInfo, ActivationInfo, TriggerEventData);
	
}

void UGA_RangedAttack::SpawnProjectile(AActor* AvatarActor, UAbilitySystemComponent* ASC, FVector TargetLocation)
{
	// AActor* AvatarActor= ActorInfo->AvatarActor.Get();
	// UAbilitySystemComponent* ASC= ActorInfo->AbilitySystemComponent.Get();
	IMyCombatInterface* CombatInterface=Cast<IMyCombatInterface>(AvatarActor);
	float Level=CombatInterface->GetLevel();
	
	if (!AvatarActor->Implements<UMyCombatInterface>())return;
	FVector SpawnLocation=IMyCombatInterface::Execute_GetCombatSocketLocation(AvatarActor);
	// FVector SpawnLocation=CombatInterface->GetCombatSocketLocation();
	
	//SpawnXform
	FTransform SpawnXform=FTransform();
	SpawnXform.SetLocation(SpawnLocation);
	FVector ToTarget=TargetLocation-SpawnLocation;
	ToTarget.Normalize();
	FRotator Rot=ToTarget.Rotation();
	SpawnXform.SetRotation(Rot.Quaternion());
	
	//GESpec
	FGameplayEffectContextHandle GEContextHandle=ASC->MakeEffectContext();
	
	GEContextHandle.AddInstigator(AvatarActor,AvatarActor);
	GEContextHandle.AddSourceObject(AvatarActor);
	FGameplayEffectSpecHandle GESpecHandle=ASC->MakeOutgoingSpec(DamageEffectClass,Level,GEContextHandle);
	// GESpecHandle.Data.Get()->SetSetByCallerMagnitude(MyTags::SetDamageByCaller,)
	
	//SpawnProj
	AMyProjectile* MyProjectile=GetWorld()->SpawnActorDeferred<AMyProjectile>(ProjectileClass,SpawnXform,nullptr);
	MyProjectile->DamageEffectSpec=*GESpecHandle.Data.Get();
	MyProjectile->SpawningActorToIgnore=AvatarActor;
	MyProjectile->FinishSpawning(SpawnXform);
}
