// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameplayTagContainer.h"
#include "UI/WidgetControllers/MyWidgetController.h"
#include "MyAttributeMenuWidgetController.generated.h"

DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnAttributeValueChangeDelegateSignature,FGameplayTag,Tag,float,NewVal);
/**
 * 
 */
UCLASS(BlueprintType)
class AURA_API UMyAttributeMenuWidgetController : public UMyWidgetController
{
	GENERATED_BODY()
	
	UPROPERTY(BlueprintAssignable)
	FOnAttributeValueChangeDelegateSignature OnAttributeValueChangeDelegate;
	
	virtual void BindCallbacksToDependencies() override;
	
	virtual void BroadcastInitialValues() override;
	
};
