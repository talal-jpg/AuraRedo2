// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "MyGameplayAbility.h"
#include "GA_Beam.generated.h"

class UCameraShakeBase;
class UMaterialInterface;
class ACharacter;

/**
 * 
 */
UCLASS()
class AURA_API UGA_Beam : public UMyGameplayAbility
{
	GENERATED_BODY()
	
public:
	// Call on the server when the beam hits a player. Plays the impact frames post process, the FOV kick and HitCameraShake on the hit player's own screen
	UFUNCTION(BlueprintCallable,BlueprintAuthorityOnly,Category="Beam|HitImpact")
	void PlayBeamHitImpact(ACharacter* HitCharacter);
	
	// Runs on the hit player's machine (AMyPlayerController2::Client_PlayBeamHitImpact calls it on this class's CDO)
	void PlayBeamHitImpactLocal(APlayerController* HitPC) const;
	
	// Impact frames material (M_PP_ImpactFrames). Gets ImpactTime (world time of the hit) and Duration, and plays its own sequence from the Time node
	UPROPERTY(EditDefaultsOnly,BlueprintReadOnly,Category="Beam|HitImpact")
	TObjectPtr<UMaterialInterface> HitPostProcessMaterial;
	
	// Length of the impact frames, also how long the FOV kick takes to ease back
	UPROPERTY(EditDefaultsOnly,BlueprintReadOnly,Category="Beam|HitImpact",meta=(ClampMin="0.05"))
	float HitImpactDuration=0.8f;
	
	// A beam that keeps hitting only starts a new impact this long after the last one started (never sooner than HitImpactDuration)
	UPROPERTY(EditDefaultsOnly,BlueprintReadOnly,Category="Beam|HitImpact")
	float HitImpactMinInterval=1.5f;
	
	// Degrees added to the camera FOV at the moment of impact, eases back to normal (negative zooms in, 0 turns it off)
	UPROPERTY(EditDefaultsOnly,BlueprintReadOnly,Category="Beam|HitImpact")
	float HitFOVOffset=12.f;
	
	UPROPERTY(EditDefaultsOnly,BlueprintReadOnly,Category="Beam|HitImpact")
	TSubclassOf<UCameraShakeBase> HitCameraShake;
	
	UPROPERTY(EditDefaultsOnly,BlueprintReadOnly,Category="Beam|HitImpact")
	float HitCameraShakeScale=1.f;
	
	// virtual void ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData) override;
	//
	// UPROPERTY(EditAnywhere)
	// UAnimMontage* BeamAbilityMontageCharge;
	//
	// UPROPERTY(EditAnywhere)
	// UAnimMontage* BeamAbilityMontageRelease;
	//
	// UFUNCTION()
	// void OnInputReleasedCallback(float TimeHeld);
	//
	// UFUNCTION()
	// void OnReleaseMontageCompleteCallback();
};
