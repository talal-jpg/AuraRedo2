// Fill out your copyright notice in the Description page of Project Settings.


#include "AbilitySystem/Abilities/GA_Projectile.h"

#include "AbilitySystemComponent.h"
#include "AbilitySystem/Data/MyGameplayTags.h"
#include "Actors/MyProjectile.h"
#include "Character/MyCombatInterface.h"
#include "Kismet/GameplayStatics.h"

void UGA_Projectile::ActivateAbility(const FGameplayAbilitySpecHandle Handle,
                                     const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo,
                                     const FGameplayEventData* TriggerEventData)
{
	Super::ActivateAbility(Handle, ActorInfo, ActivationInfo, TriggerEventData);
}

void UGA_Projectile::SpawnProjectile(AActor* AvatarActor,UAbilitySystemComponent* ASC,FVector TargetLocation)
{
	// AActor* AvatarActor= ActorInfo->AvatarActor.Get();
	// UAbilitySystemComponent* ASC= ActorInfo->AbilitySystemComponent.Get();
	IMyCombatInterface* CombatInterface=Cast<IMyCombatInterface>(AvatarActor);
	float Level=CombatInterface->GetLevel();
	FVector SpawnLocation=CombatInterface->GetCombatSocketLocation();
	
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
	MyProjectile->FinishSpawning(SpawnXform);
}
