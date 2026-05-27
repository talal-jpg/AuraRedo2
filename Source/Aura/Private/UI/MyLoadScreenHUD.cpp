// Fill out your copyright notice in the Description page of Project Settings.


#include "UI/MyLoadScreenHUD.h"

#include "Blueprint/UserWidget.h"
#include "UI/UserWidgets/MyLoadScreenUserWidget.h"
#include "UI/UserWidgets/MyUserWidget.h"
#include "UI/ViewModels/MVVM_LoadScreenViewModel.h"

void AMyLoadScreenHUD::BeginPlay()
{
	Super::BeginPlay();
	
	LoadScreenViewModel=NewObject<UMVVM_LoadScreenViewModel>(this,LoadScreenViewModelClass );
	LoadScreenViewModel->InitializeLoadSlots();
	
	// CreateLoadSlotViewModelsForAllThreeSlots
	//  vars for ViewModels
	// Map for All Three slots 
	// GetterFunc to get slot by index
	// LoadScreenViewModel->InitializeLoadSlots();
	
	LoadScreenUserWidget=CreateWidget<UMyLoadScreenUserWidget>(GetWorld(),LoadScreenUserWidgetClass);
	LoadScreenUserWidget->AddToViewport();
	
	// LoadScreen Widget Base has viewModel set and getting by func 
	// all widgets inherit from Base so have the Manual made FindModelFunc but view model is set per WBP i.e. no inheritance || but dont have view model set || inherited only to inherit the FindLoadScreenViewModel func
	// then widgetSwitcher doesnt have viewModel set , but sets view model of SubWidgets by calling auto made FindViewModelFunc on them and setting thr slotIndex int32 
	// Subwidgets also have subbed to both LoadScreenVM and LoadSlotVM
	
	LoadScreenUserWidget->InitializeUserWidget();
	
	
}
