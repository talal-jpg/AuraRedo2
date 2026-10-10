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
	// Call on the server when the beam hits a player. Plays HitPostProcessMaterial, the FOV kick and HitCameraShake on the hit player's own screen
	UFUNCTION(BlueprintCallable,BlueprintAuthorityOnly,Category="Beam|HitImpact")
	void PlayBeamHitImpact(ACharacter* HitCharacter);
	
	// Runs on the hit player's machine (AMyPlayerController2::Client_PlayBeamHitImpact calls it on this class's CDO)
	void PlayBeamHitImpactLocal(APlayerController* HitPC) const;
	
	// Post process material blended onto the hit player's camera, fades out over HitImpactDuration
	UPROPERTY(EditDefaultsOnly,BlueprintReadOnly,Category="Beam|HitImpact")
	TObjectPtr<UMaterialInterface> HitPostProcessMaterial;
	
	UPROPERTY(EditDefaultsOnly,BlueprintReadOnly,Category="Beam|HitImpact",meta=(ClampMin="0",ClampMax="1"))
	float HitPostProcessWeight=1.f;
	
	// Degrees added to the camera FOV at the moment of impact, eases back to normal over HitImpactDuration (negative zooms in)
	UPROPERTY(EditDefaultsOnly,BlueprintReadOnly,Category="Beam|HitImpact")
	float HitFOVOffset=12.f;
	
	UPROPERTY(EditDefaultsOnly,BlueprintReadOnly,Category="Beam|HitImpact",meta=(ClampMin="0.01"))
	float HitImpactDuration=0.4f;
	
	UPROPERTY(EditDefaultsOnly,BlueprintReadOnly,Category="Beam|HitImpact")
	TSubclassOf<UCameraShakeBase> HitCameraShake;
	
	UPROPERTY(EditDefaultsOnly,BlueprintReadOnly,Category="Beam|HitImpact")
	float HitCameraShakeScale=1.f;
	
	// A beam that hits every frame only restarts the shake this often; post process and FOV are refreshed on every hit
	UPROPERTY(EditDefaultsOnly,BlueprintReadOnly,Category="Beam|HitImpact")
	float HitCameraShakeMinInterval=0.25f;
	
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
