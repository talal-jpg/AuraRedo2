// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "ActiveGameplayEffectHandle.h"
#include "GameFramework/Actor.h"
#include "MyEffectActor.generated.h"

struct FGameplayTag;
class UAbilitySystemComponent;
class UGameplayEffect;

UENUM(BlueprintType)
enum class EApplicationPolicy : uint8
{
	ApplyOnOverlap,
	ApplyOnEndOverlap
};
UENUM(BlueprintType)
enum class ERemovalPolicy : uint8
{
	RemoveOnOverlap,
	RemoveOnEndOverlap,
	DoNotRemove
};
UENUM(BlueprintType)
enum class EDurationType : uint8
{
	Instant,
	Periodic,
	Infinite
};

UCLASS()
class AURA_API AMyEffectActor : public AActor
{
	GENERATED_BODY()

public:
	// Sets default values for this actor's properties
	AMyEffectActor();
	
	UPROPERTY(EditAnywhere,Category = "EffectActor")
	EApplicationPolicy ApplicationPolicy=EApplicationPolicy::ApplyOnOverlap;
	
	UPROPERTY(EditAnywhere,Category = "EffectActor")
	ERemovalPolicy RemovalPolicy=ERemovalPolicy::RemoveOnEndOverlap;
	
	
	
	UPROPERTY(EditAnywhere,Category = "EffectActor")
	int32 ActorLevel=1;
	
	UPROPERTY(EditAnywhere,Category = "EffectActor")
	TSubclassOf<UGameplayEffect> GameplayEffectClass;
	
	UFUNCTION(BlueprintCallable)
	void OnOverlap(AActor* OverlappingActor);
	
	UFUNCTION(BlueprintCallable)
	void OnEndOverlap(AActor* OverlappingActor);
	
	UPROPERTY()
	TMap<UAbilitySystemComponent*,FActiveGameplayEffectHandle> ActiveGEHandles;

protected:
	// Called when the game starts or when spawned
	virtual void BeginPlay() override;
	
};
