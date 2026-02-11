// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "UI/Data/DA_MyAbilityInfo.h"
#include "UI/Data/UIDataTypes.h"
#include "UI/WidgetControllers/MyWidgetController.h"
#include "MyOverlayWidgetController.generated.h"

class UDA_MyAbilityInfo;
struct FGameplayAbilitySpec;
class UMyAttributeMenuWidgetController;
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnAttribChangeDelegateSignature, float, NewVal);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnEffectAppliedDelegateSignature,FPopupWidgetInfo , WidgetInfo);
DECLARE_DELEGATE_OneParam(FForEachAbilityDelegateSignature,const FGameplayAbilitySpec&);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FBroadcastAbilityInfoDelegateSignature, FAbilityInfo,AbilityInfo);
/**
 * 
 */
UCLASS(Blueprintable)
class AURA_API UMyOverlayWidgetController : public UMyWidgetController
{
	GENERATED_BODY()
public:
	
	UMyOverlayWidgetController();
	
	UPROPERTY(BlueprintAssignable)
	FOnAttribChangeDelegateSignature OnHealthChangeDelegate;
	
	UPROPERTY(BlueprintAssignable)
	FOnAttribChangeDelegateSignature OnMaxHealthChangeDelegate;
	
	UPROPERTY(BlueprintAssignable)
	FOnAttribChangeDelegateSignature OnManaChangeDelegate;
	
	UPROPERTY(BlueprintAssignable)
	FOnAttribChangeDelegateSignature OnMaxManaChangeDelegate;
	
	UPROPERTY(BlueprintAssignable)
	FOnEffectAppliedDelegateSignature OnEffectAppliedBroadcastPopupWidgetInfoDelegate;
	
	UPROPERTY(EditAnywhere)
	UDataTable* DT_PopupWidgetInfo;
	
	virtual void BroadcastInitialValues() override;
	virtual void BindCallbacksToDependencies() override;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite)
	UMyAttributeMenuWidgetController* AttributeMenuWidgetController=nullptr;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite)
	TSubclassOf<UMyUserWidget> AttributeMenuWidgetClass;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite)
	UMyUserWidget* AttributeMenuWidget=nullptr;
	
	UPROPERTY(EditAnywhere)
	UDA_MyAbilityInfo* DA_AbilityInfo;
	
	UPROPERTY(BlueprintAssignable)
	FBroadcastAbilityInfoDelegateSignature BroadcastAbilityInfoDelegate;
	
	void BroadcastAbilityInfo();
	
};
