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
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite)
	bool bIsChanneling=false;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite)
	bool bIsFlying= false;
	
	
	//MyPlayerIF
	
	virtual int32 GetLevel_Implementation() override;
	
	virtual void GiveStartupAbilities() override;
	
	virtual void AddToXP_Implementation(int32 XP) override;
	
	virtual int32 GetXP_Implementation() override;
	
	virtual void AddToLevel_Implementation(int32 InLevels) override;
	
	virtual void AddToAttribPoints_Implementation(int32 InAttribPoints) override;
	
	virtual int32 GetAttribPoints_Implementation() override;
	
	virtual void AddToSpellPoints_Implementation(int32 InSpellPoints) override;
	
	virtual int32 GetSpellPoints_Implementation() override;
	
	virtual void LevelUp_Implementation() override;
	
	
	//MyCombatIF
	
	virtual void SetLookAtTarget_Implementation(FVector TargetLocation) override;
	
	virtual bool IsChanneling_Implementation() override;
	
	virtual void SetChanneling_Implementation(bool InbIsChanneling) override;
	
	virtual void SetIsFlying_Implementation(bool InbIsFlying) override;	
	
	virtual bool IsFlying_Implementation() override;
	
	// AimRot&Location
	UPROPERTY(BlueprintReadOnly)
	FVector ForwardVecChest=FVector::ZeroVector;
	
	UPROPERTY(BlueprintReadOnly)
	float YawDelta=0.f;
	
	void LerpChestRotToRot();
	
	void LerpFeetRotToRot();
	
	UPROPERTY(BlueprintReadOnly)
	FVector VelocityCharSpace=FVector::ZeroVector;
	
	UPROPERTY(BlueprintReadOnly)
	FVector ControlRotForwardVec=FVector::ZeroVector;
	
	//FeetIK
	UPROPERTY(BlueprintReadOnly)
	bool bFootLock_Left=false;
	UPROPERTY(BlueprintReadOnly)
	bool bFootLock_Right=false;
	
	UPROPERTY(BlueprintReadOnly)
	FVector FootLockLoc_L=FVector::ZeroVector;
	
	UPROPERTY(BlueprintReadOnly)
	FVector FootLockLoc_R=FVector::ZeroVector;
	
	UPROPERTY(BlueprintReadOnly)
	FVector FootLockNormal_L=FVector::ZeroVector;
	
	UPROPERTY(BlueprintReadOnly)
	FVector FootLockNormal_R=FVector::ZeroVector;
	
	void SetFootLockLoc();
	
};
