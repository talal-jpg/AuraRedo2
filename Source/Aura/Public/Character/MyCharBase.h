// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "AbilitySystemInterface.h"
#include "MyCharBase.generated.h"

class UMyAttributeSet;
class UMyAbilitySystemComponent;

UCLASS(Abstract)
class AURA_API AMyCharBase : public ACharacter, public IAbilitySystemInterface
{
	GENERATED_BODY()

public:
	// Sets default values for this character's properties
	AMyCharBase();

protected:
	
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = Mesh)
	USkeletalMeshComponent* WeaponMesh;
	
	UPROPERTY()
	UMyAbilitySystemComponent* MyAbilitySystemComponent;
	
	UPROPERTY()
	UMyAttributeSet* MyAttributeSet;
	
	virtual UAbilitySystemComponent* GetAbilitySystemComponent() const override;
	
	
	

public:	

};
