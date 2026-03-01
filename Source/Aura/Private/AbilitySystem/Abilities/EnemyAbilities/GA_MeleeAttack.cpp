// Fill out your copyright notice in the Description page of Project Settings.


#include "AbilitySystem/Abilities/EnemyAbilities/GA_MeleeAttack.h"

#include "AbilitySystemComponent.h"
#include "AbilitySystemInterface.h"
#include "Kismet/GameplayStatics.h"

void UGA_MeleeAttack::ActivateAbility(const FGameplayAbilitySpecHandle Handle,
                                      const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo,
                                      const FGameplayEventData* TriggerEventData)
{
	
	Super::ActivateAbility(Handle, ActorInfo, ActivationInfo, TriggerEventData);
	
	
}

void UGA_MeleeAttack::ApplyDamageAtLocation(FVector HitLocation)
{
	AActor* AvatarActor= GetAvatarActorFromActorInfo();
	TArray<FOverlapResult> OverlappingStructs;
	FCollisionQueryParams Params;
	Params.AddIgnoredActor(AvatarActor);
	
	IAbilitySystemInterface* AbilitySystemIF=Cast<IAbilitySystemInterface>(AvatarActor);
	FGameplayEffectContextHandle GEContextHandle=AbilitySystemIF->GetAbilitySystemComponent()->MakeEffectContext();
	GEContextHandle.AddInstigator(AvatarActor,AvatarActor);
	FGameplayEffectSpecHandle GESpecHandle=AbilitySystemIF->GetAbilitySystemComponent()->MakeOutgoingSpec(DamageEffectClass,1,GEContextHandle);
	
	GetWorld()->OverlapMultiByChannel(OverlappingStructs,HitLocation,FQuat::Identity,ECC_Visibility,FCollisionShape::MakeSphere(10),Params);
	
	// DrawDebugSphere(GetWorld(),HitLocation,10,32,FColor::Red,true,10.f);
	
	if (OverlappingStructs.Num()==0) return;
	for (auto OverlappingStruct : OverlappingStructs)
	{
		UKismetSystemLibrary::PrintString(this,OverlappingStruct.GetActor()->GetName());
	}
	if (IAbilitySystemInterface* AbilitySystemInterface=Cast<IAbilitySystemInterface>(OverlappingStructs[0].GetActor()))
	{
		UAbilitySystemComponent* TargetASC=AbilitySystemInterface->GetAbilitySystemComponent();
		AbilitySystemIF->GetAbilitySystemComponent()->ApplyGameplayEffectSpecToTarget(*GESpecHandle.Data.Get(),TargetASC);
	}
}
