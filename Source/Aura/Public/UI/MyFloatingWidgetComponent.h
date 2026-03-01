// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Components/WidgetComponent.h"
#include "MyFloatingWidgetComponent.generated.h"


class UMyUserWidget;

UCLASS(ClassGroup=(Custom), meta=(BlueprintSpawnableComponent))
class AURA_API UMyFloatingWidgetComponent : public UWidgetComponent
{
	GENERATED_BODY()

public:
	// Sets default values for this component's properties
	UMyFloatingWidgetComponent();
	
	UFUNCTION(BlueprintImplementableEvent, Category = "FloatingWidget")
	void ShowDamageNumber(float InDamageAmount);
	
	
};
