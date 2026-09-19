// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Animation/AnimInstance.h"
#include "MyAnimInstance.generated.h"

class UAbilitySystemComponent;
struct FGameplayTag;
class UCharacterMovementComponent;
class UMovementComponent;
class AMyCharPlayer;
/**
 * 
 */
UCLASS()
class AURA_API UMyAnimInstance : public UAnimInstance
{
	GENERATED_BODY()
	
	virtual void NativeUpdateAnimation(float DeltaSeconds) override;
	
	virtual void NativeInitializeAnimation() override;
	
	virtual void NativeUninitializeAnimation() override;
	
	FDelegateHandle ShootingTagCountChangeDelegateHandle;
	FDelegateHandle BeamTagCountChangeDelegateHandle;
	FDelegateHandle BoostingTagCountChangeDelegateHandle;

	UPROPERTY()
	TObjectPtr<UAbilitySystemComponent> ASC;
	
	
public:
	UPROPERTY(EditAnywhere, BlueprintReadOnly)
	float ServerTime=0.f;
	
	//Multicast rpc whenever physics state to be set on char??
	
	void InitializeASC(UAbilitySystemComponent* InASC);
	
	UPROPERTY(BlueprintReadWrite)
	bool bUpdateServerTime=false;
	
	UPROPERTY(BlueprintReadWrite)
	float PhysicsStateSetTimeStamp=0;
	
	UPROPERTY(BlueprintReadWrite)
	float PhysicsStateSetDuration=0;
	
	UPROPERTY(BlueprintReadWrite)
	FName PhysicsBoneName=FName();
	
	UPROPERTY(BlueprintReadWrite)
	FVector PhysicsForceDir=FVector::ZeroVector;
	
protected:
	UPROPERTY(BlueprintReadOnly)
	AMyCharPlayer* MyCharPlayer;
	
	UPROPERTY(BlueprintReadOnly)
	UCharacterMovementComponent* MovementComponent;
	
	UFUNCTION()
	void OnMovementModeChanged(EMovementMode PreviousMovementMode);
	
	UPROPERTY(BlueprintReadOnly)
	FVector Velocity=FVector::ZeroVector;
	
	UPROPERTY(BlueprintReadOnly)
	FVector VelocityCharSpace=FVector::ZeroVector;
	
	UPROPERTY(BlueprintReadOnly)
	FVector ForwardVec=FVector::ZeroVector;
	
	UPROPERTY(BlueprintReadOnly)
	FVector ForwardVecChest=FVector::ZeroVector;
	
	UPROPERTY(BlueprintReadOnly)
	FVector TargetLoc=FVector::ZeroVector;
	
	UPROPERTY(BlueprintReadOnly)
	FVector TargetLocDelayed=FVector::ZeroVector;
	
	UPROPERTY(BlueprintReadOnly)
	float Speed= .0f;
	
	UPROPERTY(BlueprintReadOnly)
	float YawDelta= .0f;
	
	UPROPERTY(BlueprintReadOnly)
	float FireRate=0.f;
	
	UPROPERTY(BlueprintReadOnly)
	bool bIsShooting=false;
	
	UPROPERTY(BlueprintReadOnly)
	bool bIsBeaming=false;
	
	UPROPERTY(BlueprintReadOnly)
	bool bIsBoosting=false;
	
	UPROPERTY(BlueprintReadOnly)
	bool bIsFlying=false;
	
	void ShootingTagCountChangeCallback(FGameplayTag Tag,int32 TagCount);
	void BeamTagCountChangeCallback(FGameplayTag Tag,int32 TagCount);
	void BoostingTagCountChangeCallback(FGameplayTag Tag,int32 TagCount);
	
};
