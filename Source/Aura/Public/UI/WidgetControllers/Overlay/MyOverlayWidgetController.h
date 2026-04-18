// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "AbilitySystem/Data/DA_MyAbilityInfo.h"
#include "UI/Data/UIDataTypes.h"
#include "UI/WidgetControllers/MyWidgetController.h"
#include "UI/WidgetControllers/SpellMenu/MySpellMenuWidgetController.h"
#include "MyOverlayWidgetController.generated.h"

class UDA_MyAbilityInfo;
struct FGameplayAbilitySpec;
class UMyAttributeMenuWidgetController;
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnAttribChangeDelegateSignature, float, NewVal);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnEffectAppliedDelegateSignature,FPopupWidgetInfo , WidgetInfo);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnXPPercentChangedDelegateSignature, float, XPPercent);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnLevelChangedDelegateSignature, int32, InNewLevel);

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
	
	UPROPERTY(BlueprintAssignable)
	FOnXPPercentChangedDelegateSignature OnXPPercentChangedDelegate;
	
	UPROPERTY(BlueprintAssignable)
	FOnLevelChangedDelegateSignature OnLevelChangedDelegate;
	
	
	UPROPERTY(EditAnywhere)
	UDataTable* DT_PopupWidgetInfo;
	
	virtual void BroadcastInitialValues() override;
	virtual void BindCallbacksToDependencies() override;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite)
	UMyAttributeMenuWidgetController* AttributeMenuWidgetController=nullptr;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite)
	UMySpellMenuWidgetController* SpellMenuWidgetController=nullptr;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite)
	TSubclassOf<UMyUserWidget> AttributeMenuWidgetClass;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite)
	UMyUserWidget* AttributeMenuWidget=nullptr;
	
	
	UPROPERTY(EditAnywhere)
	TSubclassOf<UMyAttributeMenuWidgetController> AttributeMenuWidgetControllerClassToConstruct;
	
	UPROPERTY(EditAnywhere)
	TSubclassOf<UMySpellMenuWidgetController> SpellMenuWidgetControllerClassConstruct;
	
	
	void OnXPChangedCallback(int32 NewXP);
	void OnLevelChangedCallback(int32 NewLevel,bool bLevelUp);
	
	
};
