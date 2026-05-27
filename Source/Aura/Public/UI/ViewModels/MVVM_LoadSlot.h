// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "MVVMViewModelBase.h"
#include "MVVM_LoadSlot.generated.h"
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FSwitchWidgetDelegateSignature, int32, SlotIndex);

/**
 * 
 */
UCLASS()
class AURA_API UMVVM_LoadSlot : public UMVVMViewModelBase
{
	GENERATED_BODY()
	
	UFUNCTION(BlueprintCallable)
	void EmptyButtonClicked(int32 SlotIndex);
	
	UFUNCTION(BlueprintCallable)
	void AddSlotButtonClicked(int32 SlotIndex,FString SlotName);
	
	UPROPERTY(BlueprintAssignable)
	FSwitchWidgetDelegateSignature SwitchWidgetDelegate;
	
	
	
};
