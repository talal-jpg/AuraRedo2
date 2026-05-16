// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "UI/Data/DA_MyAbilityInfo.h"
#include "UObject/Object.h"
#include "MyWidgetController.generated.h"

struct FGameplayAbilitySpec;
class UMyAttributeSet;
class UMyAbilitySystemComponent;

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FBroadcastAbilityInfoDelegateSignature, FAbilityInfo,AbilityInfo);
DECLARE_DELEGATE_OneParam(FForEachAbilityDelegateSignature,const FGameplayAbilitySpec&);

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
	UPROPERTY(BlueprintReadOnly)
	UMyAbilitySystemComponent* MyAbilitySystemComponent;
	UPROPERTY()
	UMyAttributeSet* MyAttributeSet;
	
	UPROPERTY(BlueprintReadOnly)
	APlayerController* PlayerController;
	
	UPROPERTY()
	APlayerState* PlayerState;
	
	void SetWidgetControllerParams(FWidgetControllerParams Params);
	
	UFUNCTION(BlueprintCallable)
	virtual void BindCallbacksToDependencies();
	
	UFUNCTION(BlueprintCallable)
	virtual void BroadcastInitialValues();
	
	UPROPERTY(BlueprintAssignable)
	FBroadcastAbilityInfoDelegateSignature BroadcastAbilityInfoDelegate;
	
	void BroadcastAbilityInfo(UDA_MyAbilityInfo* AbilityInfo);
};
