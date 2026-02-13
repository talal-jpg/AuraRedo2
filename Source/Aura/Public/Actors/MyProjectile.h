// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameplayEffect.h"
#include "GameFramework/Actor.h"
#include "NiagaraComponent.h"
#include "MyProjectile.generated.h"

struct FGameplayEffectSpec;
class UGameplayEffect;
class USphereComponent;
class UProjectileMovementComponent;

UCLASS()
class AURA_API AMyProjectile : public AActor
{
	GENERATED_BODY()

public:
	// Sets default values for this actor's properties
	AMyProjectile();

protected:
	// Called when the game starts or when spawned
	virtual void BeginPlay() override;

public:
	
	UPROPERTY(EditAnywhere)
	USphereComponent* CollisionSphere;
	
	UPROPERTY(EditAnywhere)
	UProjectileMovementComponent* ProjectileMovementComponent;
	
	UPROPERTY(EditAnywhere)
	UNiagaraComponent* NiagaraComponent;
	
	UFUNCTION()
	void OnSphereBeginOverlapCallback(UPrimitiveComponent* OverlappedComponent, AActor* OtherActor, UPrimitiveComponent* OtherComp, int32 OtherBodyIndex, bool bFromSweep, const FHitResult & SweepResult);
	
	UPROPERTY(EditAnywhere)
	FGameplayEffectSpec DamageEffectSpec;
	
	UPROPERTY(EditAnywhere)
	UNiagaraSystem* BurstNiagaraSystem;
	
};
