// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "AbilitySystemInterface.h"
#include "AbilitySystem/MyAttributeSet.h"
#include "AbilitySystem/Data/DA_LevelUpInfo.h"
#include "GameFramework/PlayerState.h"
#include "MyPlayerState.generated.h"

class UAttributeSet;
class UMyAttributeSet;
class UMyAbilitySystemComponent;
/**
 * 
 */

DECLARE_MULTICAST_DELEGATE_OneParam(FOnPlayerStatChanged, int32 /*StatValue*/)
DECLARE_MULTICAST_DELEGATE_TwoParams(FOnLevelChanged, int32 /*StatValue*/, bool /*bLevelUp*/)

UCLASS()
class AURA_API AMyPlayerState : public APlayerState , public IAbilitySystemInterface
{
	GENERATED_BODY()
	
	public:
	
	virtual UAbilitySystemComponent* GetAbilitySystemComponent() const override;
	UAttributeSet* GetAttributeSet()const {return MyAttributeSet;}
	
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
	
	AMyPlayerState();
	
	UPROPERTY(EditAnywhere)
	UDA_LevelUpInfo* LevelUpInfo;
	
	FOnPlayerStatChanged OnXPChangedDelegate;
	FOnLevelChanged OnLevelChangedDelegate;
	FOnPlayerStatChanged OnAttributePointsChangedDelegate;
	FOnPlayerStatChanged OnSpellPointsChangedDelegate;
	
	FORCEINLINE int32 GetLevel() const { return Level; }
	FORCEINLINE int32 GetXP() const { return XP; }
	FORCEINLINE int32 GetAttributePoints() const { return AttributePoints; }
	FORCEINLINE int32 GetSpellPoints() const { return SpellPoints; }
	
	void AddToXP(int32 InXP);
	void AddToLevel(int32 InLevel);
	void AddToAttributePoints(int32 InAttributePoints);
	void AddToSpellPoints(int32 InSpellPoints);
	
	void SetLevel(int32 InLevel);
	void SetXP(int32 InXP);
	void SetAttributePoints(int32 InAttributePoints);
	void SetSpellPoints(int32 InSpellPoints);
	
	protected:
	
	UPROPERTY()
	UMyAbilitySystemComponent* MyAbilitySystemComponent;
	
	UPROPERTY()
	UMyAttributeSet* MyAttributeSet;
	
	private:
	
	UPROPERTY(VisibleAnywhere, ReplicatedUsing=OnRep_Level)
	int32 Level=1;
	
	UPROPERTY(VisibleAnywhere, ReplicatedUsing=OnRep_XP)
	int32 XP=0;
	
	UPROPERTY(VisibleAnywhere, ReplicatedUsing=OnRep_AttributePoints)
	int32 AttributePoints=0;
	
	UPROPERTY(VisibleAnywhere, ReplicatedUsing=OnRep_SpellPoints)
	int32 SpellPoints=0;
	
	UFUNCTION()
	void OnRep_Level(int32 OldLevel);
	
	UFUNCTION()
	void OnRep_XP(int32 OldXP);
	
	UFUNCTION()
	void OnRep_AttributePoints(int32 OldAttributePoints);
	
	UFUNCTION()
	void OnRep_SpellPoints(int32 OldSpellPoints);
	
};
