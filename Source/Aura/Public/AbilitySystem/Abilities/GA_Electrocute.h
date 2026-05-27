// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "MyGameplayAbility.h"
#include "GA_Electrocute.generated.h"

/**
 * 
 */
UCLASS()
class AURA_API UGA_Electrocute : public UMyGameplayAbility
{
	GENERATED_BODY()
	
	virtual void ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData) override;
	
public:
	UFUNCTION(BlueprintCallable)
	void TraceFirstTarget();
	
	UFUNCTION(BlueprintCallable)
	void AddAdditionalTargets();
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite)
	AActor* FirstHitActor;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite)
	FVector FirstHitActorLocation;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite)
	FVector OwnerWeaponSocketLocation;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite)
	TArray<AActor*> AdditionalTargets;
	
	UFUNCTION(BlueprintImplementableEvent)
	void FirstTargetDied(AActor* DeadActor);
	
	UFUNCTION(BlueprintImplementableEvent)
	void AdditionalTargetDied(AActor* DeadActor);
	
};
