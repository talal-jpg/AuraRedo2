// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "AbilitySystem/Data/DA_MyAbilityInfo.h"
#include "UObject/Object.h"
#include "MyWidgetController.generated.h"

struct FGameplayAbilitySpec;
class UDA_MyAbilityInfo;
class AMyPlayerController;
class AMyPlayerState;
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

DECLARE_DELEGATE_OneParam(FForEachAbilityDelegateSignature,const FGameplayAbilitySpec&);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FBroadcastAbilityInfoDelegateSignature, FAbilityInfo,AbilityInfo);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnPlayerStatChangedDelegateSignature, int32, NewValue);
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
	
	UPROPERTY(BlueprintReadOnly)
	APlayerController* PlayerController;
	
	UPROPERTY()
	APlayerState* PlayerState;
	
	UPROPERTY()
	AMyPlayerController* MyPlayerController;
	
	UPROPERTY()
	AMyPlayerState* MyPlayerState;
	
	void SetWidgetControllerParams(FWidgetControllerParams Params);
	
	UFUNCTION(BlueprintCallable)
	virtual void BindCallbacksToDependencies();
	
	UFUNCTION(BlueprintCallable)
	virtual void BroadcastInitialValues();
	
	UPROPERTY(EditAnywhere)
	UDA_MyAbilityInfo* DA_AbilityInfo;
	
	void BroadcastAbilityInfo();
	
	UPROPERTY(BlueprintAssignable)
	FBroadcastAbilityInfoDelegateSignature BroadcastAbilityInfoDelegate;
	
	AMyPlayerState* GetMyPlayerState();
	AMyPlayerController* GetMyPlayerController();
};
