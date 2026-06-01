// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "UObject/Interface.h"
#include "MyCombatInterface.generated.h"

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnDeathDelegateSignature, AActor*,DeadActor);
// This class does not need to be modified.
UINTERFACE(BlueprintType)
class UMyCombatInterface : public UInterface
{
	GENERATED_BODY()
};

/**
 * 
 */
class AURA_API IMyCombatInterface
{
	GENERATED_BODY()

	// Add interface functions to this class. This is the class that will be inherited to implement this interface.
public:
	
	UFUNCTION(BlueprintNativeEvent,BlueprintCallable)
	int32 GetLevel();
	
	UFUNCTION(BlueprintNativeEvent,BlueprintCallable)
	FVector GetCombatSocketLocation();
	
	UFUNCTION(BlueprintNativeEvent,BlueprintCallable)
	void SetLookAtTarget(FVector TargetLocation);
	
	virtual void Die();
	
	UFUNCTION(BlueprintNativeEvent,BlueprintCallable)
	bool IsDead();
	
	UFUNCTION(BlueprintNativeEvent,BlueprintCallable)
	bool IsChanneling();
	
	UFUNCTION(BlueprintNativeEvent,BlueprintCallable)
	void SetChanneling(bool bIsChanneling);
	
	UFUNCTION(BlueprintNativeEvent,BlueprintCallable)
	bool IsShooting();
	
	UFUNCTION(BlueprintNativeEvent,BlueprintCallable)
	void SetIsShooting(bool bIsShooting);
	
	virtual FOnDeathDelegateSignature& GetOnDeathDelegate() = 0;
	
};
