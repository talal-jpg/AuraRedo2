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

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnMovementModeChangedDelegateSignature,EMovementMode,PrevMovementMode);
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
	
	UPROPERTY(BlueprintAssignable)
	FOnMovementModeChangedDelegateSignature OnMovementModeChangedDelegate;
	
	UFUNCTION(BlueprintCallable)
	UMyAttributeSet* GetMyAttributeSet();

protected:
	
	// UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = Mesh)
	// USkeletalMeshComponent* WeaponMesh;
	
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = Mesh)
	USceneComponent* SceneComponentToRotateCharMesh;
	
	UPROPERTY(EditAnywhere)
	UStaticMeshComponent* JetPackMeshComponent;
	
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
	
	virtual void OnMovementModeChanged(EMovementMode PrevMovementMode, uint8 PreviousCustomMode = 0) override;
	
	//CombatIF
	
	virtual void Die() override;
	
	virtual bool IsDead_Implementation() override{return bIsDead;};
	
	bool bIsDead=false;
	
	UFUNCTION(NetMulticast,Reliable)
	virtual void MulticastHandleDeath();
	
	FOnDeathDelegateSignature OnDeathDelegate;
	
	virtual FOnDeathDelegateSignature& GetOnDeathDelegate() override; 
	
	
	//CombatIF
	
	UPROPERTY(BlueprintReadWrite)
	bool bIsShooting=false;
	
	UFUNCTION(NetMulticast,Reliable)
	void MultiCastSetIsShooting(bool InbIsShooting);
	
	virtual void SetIsShooting_Implementation(bool InbIsShooting) override;
	
	virtual FVector GetCombatSocketLocation_Implementation() override;
	
	virtual bool IsShooting_Implementation() override;
	
public:	

};
