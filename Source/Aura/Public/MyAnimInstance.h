// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Animation/AnimInstance.h"
#include "MyAnimInstance.generated.h"

class UAbilitySystemComponent;
struct FGameplayTag;
class UCharacterMovementComponent;
class UMovementComponent;
class AMyCharPlayer;
class UNiagaraSystem;
class UMaterialInterface;
/**
 * 
 */
UCLASS()
class AURA_API UMyAnimInstance : public UAnimInstance
{
	GENERATED_BODY()
	
	virtual void NativeUpdateAnimation(float DeltaSeconds) override;
	
	virtual void NativeInitializeAnimation() override;
	
	virtual void NativeUninitializeAnimation() override;
	
	FDelegateHandle ShootingTagCountChangeDelegateHandle;
	FDelegateHandle BeamTagCountChangeDelegateHandle;
	FDelegateHandle BoostingTagCountChangeDelegateHandle;
	FDelegateHandle SwingTagCountChangeDelegateHandle;

	UPROPERTY()
	TObjectPtr<UAbilitySystemComponent> ASC;
	
	
public:
	UPROPERTY(EditAnywhere, BlueprintReadOnly)
	float ServerTime=0.f;
	
	//Multicast rpc whenever physics state to be set on char??
	
	void InitializeASC(UAbilitySystemComponent* InASC);
	
	UPROPERTY(BlueprintReadWrite)
	bool bUpdateServerTime=false;
	
	UPROPERTY(BlueprintReadWrite)
	float PhysicsStateSetTimeStamp=0;
	
	UPROPERTY(BlueprintReadWrite)
	float PhysicsStateSetDuration=0;
	
	UPROPERTY(BlueprintReadWrite)
	FName PhysicsBoneName=FName();
	
	UPROPERTY(BlueprintReadWrite)
	FVector PhysicsForceDir=FVector::ZeroVector;
	
protected:
	UPROPERTY(BlueprintReadOnly)
	AMyCharPlayer* MyCharPlayer;
	
	UPROPERTY(BlueprintReadOnly)
	UCharacterMovementComponent* MovementComponent;
	
	UFUNCTION()
	void OnMovementModeChanged(EMovementMode PreviousMovementMode);
	
	UPROPERTY(BlueprintReadOnly)
	FVector Velocity=FVector::ZeroVector;
	
	UPROPERTY(BlueprintReadOnly)
	FVector VelocityCharSpace=FVector::ZeroVector;
	
	UPROPERTY(BlueprintReadOnly)
	FVector ForwardVec=FVector::ZeroVector;
	
	UPROPERTY(BlueprintReadOnly)
	FVector ForwardVecChest=FVector::ZeroVector;
	
	UPROPERTY(BlueprintReadOnly)
	FVector TargetLoc=FVector::ZeroVector;
	
	UPROPERTY(BlueprintReadOnly)
	FVector TargetLocDelayed=FVector::ZeroVector;
	
	UPROPERTY(BlueprintReadOnly)
	float Speed= .0f;
	
	UPROPERTY(BlueprintReadOnly)
	float YawDelta= .0f;
	
	UPROPERTY(BlueprintReadOnly)
	float FireRate=0.f;
	
	UPROPERTY(BlueprintReadOnly)
	bool bIsShooting=false;
	
	UPROPERTY(BlueprintReadOnly)
	bool bIsBeaming=false;
	
	UPROPERTY(BlueprintReadOnly)
	bool bIsBoosting=false;
	
	UPROPERTY(BlueprintReadOnly)
	bool bIsFlying=false;
	
	UPROPERTY(BlueprintReadOnly)
	bool bIsSwinging=false;
	
	
	// Set by OnDeathCallback on every machine; ABP_MyCharMech passes it to CR_Mech,
	// whose death branch ragdolls the mech
	UPROPERTY(BlueprintReadOnly)
	bool bIsDead=false;
	
	UPROPERTY(BlueprintReadOnly)
	float SwingPhase=0.f;
	
	void ShootingTagCountChangeCallback(FGameplayTag Tag,int32 TagCount);
	void BeamTagCountChangeCallback(FGameplayTag Tag,int32 TagCount);
	void BoostingTagCountChangeCallback(FGameplayTag Tag,int32 TagCount);
	void SwingTagCountChangeCallback(FGameplayTag Tag,int32 TagCount);
	// Bound with AddDynamic, so it must be a UFUNCTION
	UFUNCTION()
	void OnDeathCallback(AActor* DeadActor);
	
	// Death: NS_Claude_Disintegrate on the mesh (its cubes are born from the falling body and inherit its velocity) while
	// every body slot switches to a masked dynamic copy of its material (DisintegrateDissolveParent + the slot's own
	// parameters) that MF_MechDisintegrate eats away in noisy patches with a burnt, glowing rim.
	UPROPERTY(EditDefaultsOnly, Category="Death")
	TSoftObjectPtr<UNiagaraSystem> DisintegrateSystem{FSoftObjectPath(TEXT("/Game/Level/GAS/GameplayAbilities/GA_Beam/Niagara/NS_BeamClaude/NS_Claude_Disintegrate.NS_Claude_Disintegrate"))};
	
	// Seconds after death before it starts (0 = the moment bIsDead is set, while the control rig ragdoll falls)
	UPROPERTY(EditDefaultsOnly, Category="Death")
	float DisintegrateDelay=0.f;
	
	// Custom Primitive Data slot read by MF_MechDisintegrate's DisintegrateTime parameter (world time the effect starts, 0 = alive)
	UPROPERTY(EditDefaultsOnly, Category="Death")
	int32 DisintegrateDataIndex=0;
	
	// Masked copy of M_MasterMech: every slot whose material is based on M_MasterMech gets a dynamic instance of this
	// with the slot's own parameter values, so the mech keeps its look until each patch is eaten away
	UPROPERTY(EditDefaultsOnly, Category="Death")
	TSoftObjectPtr<UMaterialInterface> DisintegrateDissolveParent{FSoftObjectPath(TEXT("/Game/Level/MechChar/Mats/M_MasterMechDissolve.M_MasterMechDissolve"))};
	
	// Slots with other materials (emissive panels, outline) switch to this masked material instead
	UPROPERTY(EditDefaultsOnly, Category="Death")
	TSoftObjectPtr<UMaterialInterface> DisintegrateBodyMaterial{FSoftObjectPath(TEXT("/Game/Level/MechChar/Mats/M_MechDisintegrateBody.M_MechDisintegrateBody"))};
	
	// Seconds after the effect starts before the material swap (0 = at once; the dissolve materials start from the intact look)
	UPROPERTY(EditDefaultsOnly, Category="Death")
	float DisintegrateSwapDelay=0.f;
	
	void StartDisintegrate();
	
	void SwapToDisintegrateMaterial();
	
	FTimerHandle DisintegrateTimerHandle;
	
	// Owner's (capsule's) world velocity the moment the death callback ran, passed to the system as User.DeathVelocity so the
	// cubes are kicked along the way the character was moving even if the capsule stops a frame later
	FVector DeathVelocity=FVector::ZeroVector;
	
};
