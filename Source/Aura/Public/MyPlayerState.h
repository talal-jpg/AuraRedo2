// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PlayerState.h"
#include "MyPlayerState.generated.h"

class UMySpellMenuWidgetController;
class UMyLevelUpInfo;
class UMyAttributeSet;
class UMyAbilitySystemComponent;
/**
 * 
 */
DECLARE_MULTICAST_DELEGATE_OneParam(FOnStatChangedDelegateSignature,int32);//NewXP

UCLASS()
class AURA_API AMyPlayerState : public APlayerState
{
	GENERATED_BODY()
	
public:
	
	UPROPERTY(EditAnywhere)
	UMyLevelUpInfo* MyLevelUpInfo;
	
	UPROPERTY(EditAnywhere)
	TSubclassOf<UMySpellMenuWidgetController> MySpellMenuWidgetControllerClass;
	
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
	
	UPROPERTY()
	UMyAbilitySystemComponent* MyAbilitySystemComponent;
	
	UPROPERTY()
	UMyAttributeSet* MyAttributeSet;
	
	AMyPlayerState();
	
	
	FOnStatChangedDelegateSignature OnXPChangedDelegate;
	
	FOnStatChangedDelegateSignature OnLevelChangedDelegate;
	
	FOnStatChangedDelegateSignature OnAttribPointsChangedDelegate;
	
	FOnStatChangedDelegateSignature OnSpellPointsChangedDelegate;
	
	int32 GetXP() const {return XP;}
	
	int32 GetLevel() const {return Level;}
	
	int32 GetAttributePoints() const {return AttributePoints;}
	
	int32 GetSpellPoints() const {return SpellPoints;}
	
	void AddToXP(int32 InExp);
	
	void AddToLevel(int32 InLevels);
	
	void AddToAttributePoints(int32 InAttributePoints);
	
	void AddToSpellPoints(int32 InSpellPoints);
	
	private:
	
	
	UPROPERTY(ReplicatedUsing=OnRep_XP)
	int32 XP=0;
	
	UPROPERTY(ReplicatedUsing=OnRep_Level)
	int32 Level=1;
	
	UPROPERTY(ReplicatedUsing=OnRep_AttributePoints)
	int32 AttributePoints=0;
	
	UPROPERTY(ReplicatedUsing=OnRep_SpellPoints)
	int32 SpellPoints=0;
	
	UFUNCTION()
	void OnRep_XP(int32 OldExp);
	
	UFUNCTION()
	void OnRep_Level(int32 OldLevel);
	
	UFUNCTION()
	void OnRep_AttributePoints(int32 OldAttributePoints);
	
	UFUNCTION()
	void OnRep_SpellPoints(int32 OldSpellPoints);
	
};
