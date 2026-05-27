// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "AbilitySystemInterface.h"
#include "Interfaces/MyCombatInterface.h"
#include "MyCharBase.generated.h"

enum class ECharacterClass : uint8;
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

	void Dissolve();
	
	UFUNCTION(BlueprintImplementableEvent)
	void StartDissolveTimeline(UMaterialInstanceDynamic* MaterialInstanceDynamic);
	
	UFUNCTION(BlueprintImplementableEvent)
	void StartWeaponDissolveTimeline(UMaterialInstanceDynamic* MaterialInstanceDynamic);
	
	UPROPERTY(EditAnywhere, BlueprintReadOnly)
	TObjectPtr<UMaterialInstance> DissolveMaterialInstance;
	
	UPROPERTY(EditAnywhere, BlueprintReadOnly)
	TObjectPtr<UMaterialInstance> WeaponDissolveMaterialInstance;
	
	UPROPERTY(EditAnywhere,BlueprintReadOnly)
	ECharacterClass CharacterClass;
	
	

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
	TArray<TSubclassOf<UGameplayAbility>> PassiveStartupAbilities;
	
	virtual void GiveStartupAbilities();
	
	virtual void GivePassiveStartupAbilities();
	
	
	virtual FVector GetCombatSocketLocation_Implementation() override;
	
	virtual void Die() override;
	
	virtual bool IsDead_Implementation() override{return bIsDead;};
	
	bool bIsDead=false;
	
	
	UFUNCTION(NetMulticast,Reliable)
	virtual void MulticastHandleDeath();
	
	FOnDeathDelegateSignature OnDeathDelegate;
	
	virtual FOnDeathDelegateSignature& GetOnDeathDelegate() override; 
public:	

};
