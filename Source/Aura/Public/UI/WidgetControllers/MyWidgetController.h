// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "MyWidgetController.generated.h"

class UMyAttributeSet;
class UMyAbilitySystemComponent;

USTRUCT()
struct FWidgetControllerParams
{
	GENERATED_BODY()
	FWidgetControllerParams() = default;
	FWidgetControllerParams(APlayerController* PC,APlayerState* PS,UMyAbilitySystemComponent* ASC, UMyAttributeSet* AS):PlayerController(PC),PlayerState(PS),AbilitySystemComponent(ASC),AttributeSet(AS)
	{};
	UPROPERTY()
	APlayerController* PlayerController;
	UPROPERTY()
	APlayerState* PlayerState;
	UPROPERTY()
	UMyAbilitySystemComponent* AbilitySystemComponent;
	UPROPERTY()
	UMyAttributeSet* AttributeSet;
};
/**
 * 
 */
UCLASS()
class AURA_API UMyWidgetController : public UObject
{
	GENERATED_BODY()
public:
	UPROPERTY()
	UMyAbilitySystemComponent* MyAbilitySystemComponent;
	UPROPERTY()
	UMyAttributeSet* MyAttributeSet;
	
	UPROPERTY()
	APlayerController* PlayerController;
	
	UPROPERTY()
	APlayerState* PlayerState;
	
	void SetWidgetControllerParams(FWidgetControllerParams Params);
	
	virtual void BindCallbacksToDependencies();
	virtual void BroadcastInitialValues();
};
