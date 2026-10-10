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
	
	// Runs on the hit player's machine (AMyPlayerController2::Client_PlayBeamImpact calls it on this class's CDO)
	void PlayBeamHitImpactLocal(APlayerController* HitPC) const;
	
	// Plays the caster's impact frames post process and CastCameraShake on the casting player's own screen (no FOV change).
	// Call it where the beam lands, from the server or from the caster's own machine: a locally controlled caster plays it directly, otherwise the server sends it
	UFUNCTION(BlueprintCallable,Category="Beam|CastImpact")
	void PlayBeamCastImpact(ACharacter* CasterCharacter);
	
	// Runs on the caster's machine
	void PlayBeamCastImpactLocal(APlayerController* CasterPC) const;
	
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
	
	// Caster's impact frames material (M_PP_CastFrames), driven by ImpactTime and Duration like the hit one
	UPROPERTY(EditDefaultsOnly,BlueprintReadOnly,Category="Beam|CastImpact")
	TObjectPtr<UMaterialInterface> CastPostProcessMaterial;
	
	UPROPERTY(EditDefaultsOnly,BlueprintReadOnly,Category="Beam|CastImpact",meta=(ClampMin="0.05"))
	float CastImpactDuration=0.9f;
	
	// A beam that keeps landing only starts a new caster impact this long after the last one started (never sooner than CastImpactDuration)
	UPROPERTY(EditDefaultsOnly,BlueprintReadOnly,Category="Beam|CastImpact")
	float CastImpactMinInterval=1.5f;
	
	UPROPERTY(EditDefaultsOnly,BlueprintReadOnly,Category="Beam|CastImpact")
	TSubclassOf<UCameraShakeBase> CastCameraShake;
	
	UPROPERTY(EditDefaultsOnly,BlueprintReadOnly,Category="Beam|CastImpact")
	float CastCameraShakeScale=1.f;
	
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
