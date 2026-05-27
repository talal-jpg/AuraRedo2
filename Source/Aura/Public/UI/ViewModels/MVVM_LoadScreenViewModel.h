// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "MVVMViewModelBase.h"
#include "MVVM_LoadScreenViewModel.generated.h"

class UMVVM_LoadSlot;
/**
 * 
 */
UCLASS()
class AURA_API UMVVM_LoadScreenViewModel : public UMVVMViewModelBase
{
	GENERATED_BODY()
	
	public:
	
	UFUNCTION(BlueprintCallable)
	UMVVM_LoadSlot* GetLoadSlotMVVMByIndex(int32 LoadSlotIndex);
	
	
	void InitializeLoadSlots();
	
	private:
	UPROPERTY(EditDefaultsOnly)
	TSubclassOf<UMVVM_LoadSlot> LoadSlotViewModelClass;
	
	UPROPERTY()
	UMVVM_LoadSlot* LoadSlot1;
	
	UPROPERTY()
	UMVVM_LoadSlot* LoadSlot2;
	
	UPROPERTY()
	UMVVM_LoadSlot* LoadSlot3;
	
	UPROPERTY()
	TMap<int32,UMVVM_LoadSlot*> LoadSlotMap;
	
};
