// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "MyCharBase.h"
#include "Interfaces/MyPlayerInterface.h"
#include "MyCharPlayer.generated.h"

class UGameplayEffect;
class UCameraComponent;
class USpringArmComponent;
class UInputMappingContext;

UCLASS()
class AURA_API AMyCharPlayer : public AMyCharBase , public IMyPlayerInterface
{
	GENERATED_BODY()

public:
	// Sets default values for this character's properties
	AMyCharPlayer();

protected:
	// Called when the game starts or when spawned
	virtual void BeginPlay() override;

public:
	// Called every frame
	virtual void Tick(float DeltaTime) override;
	
	virtual void OnRep_PlayerState() override;
	virtual void PossessedBy(AController* NewController) override;
	
	
	void InitializeAttributes();
	
	UPROPERTY(EditAnywhere)
	TSubclassOf<UGameplayEffect> PrimaryAttributesEffect;
	
	UPROPERTY(EditAnywhere)
	TSubclassOf<UGameplayEffect> SecondaryAttributesEffect;
	
	UPROPERTY(EditAnywhere)
	TSubclassOf<UGameplayEffect> VitalAttributesEffect;
	
	virtual void GiveStartupAbilities() override;
	
	virtual void GivePassiveAbilities() override;
	
	virtual int32 GetCharLevel_Implementation() override;
	
	//** MyPlayerInterface **//
	virtual void AddToXP_Implementation(int32 InXP) override;
	virtual void AddToPlayerLevel_Implementation(int32 InPlayerLevel) override;
	virtual void LevelUp_Implementation() override;
	virtual int32 FindLevelForXP_Implementation(int32 XP) override;
	virtual int32 GetXP_Implementation() override;
	virtual int32 GetAttributePoints_Implementation() override;
	virtual int32 GetSpellPoints_Implementation() override;
	virtual void AddToAttributePoints_Implementation(int32 InAttributePoints) override;
	virtual void AddToSpellPoints_Implementation(int32 InSpellPoints) override;
	virtual int32 GetAttributePointsReward_Implementation(int32 Level) override;
	virtual int32 GetSpellPointsReward_Implementation(int32 Level) override;
	
	
	
	
	
	
};
