// Fill out your copyright notice in the Description page of Project Settings.


#include "UI/ViewModels/MVVM_LoadScreenViewModel.h"

#include "UI/ViewModels/MVVM_LoadSlot.h"

UMVVM_LoadSlot* UMVVM_LoadScreenViewModel::GetLoadSlotMVVMByIndex(int32 LoadSlotIndex)
{
	return LoadSlotMap.FindRef(LoadSlotIndex);
}

void UMVVM_LoadScreenViewModel::InitializeLoadSlots()
{
	checkf(LoadSlotViewModelClass,TEXT("PleaseFillOutMVVMLoadSlotClassOnBP_MVVMLoadScreen"))
	LoadSlot1=NewObject<UMVVM_LoadSlot>(this,LoadSlotViewModelClass);
	LoadSlotMap.Add(1,LoadSlot1);
	LoadSlot2=NewObject<UMVVM_LoadSlot>(this,LoadSlotViewModelClass);
	LoadSlotMap.Add(2,LoadSlot2);
	LoadSlot3=NewObject<UMVVM_LoadSlot>(this,LoadSlotViewModelClass);
	LoadSlotMap.Add(3,LoadSlot3);
	
}
