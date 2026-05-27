// Fill out your copyright notice in the Description page of Project Settings.


#include "UI/ViewModels/MVVM_LoadSlot.h"

#include "Kismet/KismetSystemLibrary.h"

void UMVVM_LoadSlot::EmptyButtonClicked(int32 SlotIndex)
{
	UKismetSystemLibrary::PrintString(this,"AddSlotButtonClicked");
	//1 Because need to switch to Enter mode
	SwitchWidgetDelegate.Broadcast(1);
	// while this is being recorded 
	// I just need to type something in order to check the quality
}

void UMVVM_LoadSlot::AddSlotButtonClicked(int32 SlotIndex,FString SlotName)
{
	//Save data using slot index and slot name
}
