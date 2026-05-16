// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameplayTagContainer.h"
#include "UI/WidgetControllers/MyWidgetController.h"
#include "MyAttributeMenuWidgetController.generated.h"

DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnAttributeValueChangeDelegateSignature,FGameplayTag,Tag,float,NewVal);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnAttribMenuStatChangeDelegateSignature,int32,NewVal);
/**
 * 
 */
UCLASS(BlueprintType)
class AURA_API UMyAttributeMenuWidgetController : public UMyWidgetController
{
	GENERATED_BODY()
	
private:
	
	UPROPERTY(BlueprintAssignable)
	FOnAttributeValueChangeDelegateSignature OnAttributeValueChangeDelegate;
	
	UPROPERTY(BlueprintAssignable)
	FOnAttribMenuStatChangeDelegateSignature OnAttribPointsChangeDelegate;
	
	virtual void BindCallbacksToDependencies() override;
	
	virtual void BroadcastInitialValues() override;
	
	public:
	
	UFUNCTION(BlueprintCallable)
	void UpgradeAttribButtonClicked(FGameplayTag InAttributeTag);
	
	
};
