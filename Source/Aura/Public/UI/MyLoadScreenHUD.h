// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/HUD.h"
#include "MyLoadScreenHUD.generated.h"

class UMyUserWidget;
class UMyLoadScreenUserWidget;
class UMVVM_LoadScreenViewModel;
/**
 * 
 */
UCLASS()
class AURA_API AMyLoadScreenHUD : public AHUD
{
	GENERATED_BODY()
	
	virtual void BeginPlay() override;
	
	
	public:
	
	UPROPERTY(EditDefaultsOnly)
	TSubclassOf<UMVVM_LoadScreenViewModel> LoadScreenViewModelClass;
	
	UPROPERTY(EditDefaultsOnly,BlueprintReadOnly)
	UMVVM_LoadScreenViewModel* LoadScreenViewModel;
	
	UPROPERTY(EditDefaultsOnly)
	UMyLoadScreenUserWidget* LoadScreenUserWidget;
	
	UPROPERTY(EditDefaultsOnly)
	TSubclassOf<UMyLoadScreenUserWidget> LoadScreenUserWidgetClass;
};
