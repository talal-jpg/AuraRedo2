// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "AbilitySystemInterface.h"
#include "Interfaces/MyCombatInterface.h"
#include "MyCharBase.generated.h"

class UGameplayAbility;
class UMyAttributeSet;
class UMyAbilitySystemComponent;

UCLASS(Abstract)
class AURA_API AMyCharBase : public ACharacter, public IAbilitySystemInterface , public IMyCombatInterface
{
	GENERATED_BODY()

public:
	// Sets default values for this character's properties
	AMyCharBase();

protected:
	
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = Mesh)
	USkeletalMeshComponent* WeaponMesh;
	
	UPROPERTY(BlueprintReadOnly)
	UMyAbilitySystemComponent* MyAbilitySystemComponent;
	
	UPROPERTY()
	UMyAttributeSet* MyAttributeSet;
	
	virtual UAbilitySystemComponent* GetAbilitySystemComponent() const override;
	
	UPROPERTY(EditAnywhere)
	TArray<TSubclassOf<UGameplayAbility>> StartupAbilities;
	
	UPROPERTY(EditAnywhere)
	TArray<TSubclassOf<UGameplayAbility>> PassiveAbilities;
	
	virtual void GiveStartupAbilities();
	
	virtual void GivePassiveAbilities();
	
	virtual FVector GetCombatSocketLocation_Implementation() override;
	
	virtual void SetCombatTarget_Implementation(AActor* InCombatTarget) override;
	
	virtual ECharacterClass GetCharacterClass() override;
	
	virtual AActor* GetCombatTarget_Implementation() override;
	
	UPROPERTY(BlueprintReadWrite, Category = "Combat")
	AActor* CombatTarget;
	
	UFUNCTION(NetMulticast, reliable)
	virtual void HandleDeath() override;
	
	UPROPERTY(EditAnywhere)
	ECharacterClass CharacterClass;
	
public:	

};
