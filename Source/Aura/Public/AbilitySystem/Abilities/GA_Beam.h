// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "MyGameplayAbility.h"
#include "AbilitySystem/MySplashDamageLibrary.h"
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
	// Plays the hit impact on the hit player's own screen: impact frames post process (HitPostProcessMaterial), FOV kick (HitFOVOffset) and HitCameraShake.
	// Call it where the beam lands, from the server or from the hit player's own machine: a locally controlled character plays it directly, otherwise the server sends it
	UFUNCTION(BlueprintCallable,Category="Beam|HitImpact")
	void PlayBeamHitImpact(ACharacter* HitCharacter);
	
	// Runs on the hit player's machine (AMyPlayerController2::Client_PlayBeamImpact calls it on this class's CDO with bFromServer true).
	// bFromServer: the server already spaced these out, so the local gate only drops a copy of an impact this machine just played itself
	void PlayBeamHitImpactLocal(APlayerController* HitPC,bool bFromServer=false) const;
	
	// Plays the cast impact on the casting player's own screen: impact frames post process (CastPostProcessMaterial), FOV kick (CastFOVOffset) and CastCameraShake.
	// Call it where the beam lands, from the server or from the caster's own machine: a locally controlled caster plays it directly, otherwise the server sends it
	UFUNCTION(BlueprintCallable,Category="Beam|CastImpact")
	void PlayBeamCastImpact(ACharacter* CasterCharacter);
	
	// Runs on the caster's machine, bFromServer as in PlayBeamHitImpactLocal
	void PlayBeamCastImpactLocal(APlayerController* CasterPC,bool bFromServer=false) const;
	
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
	
	// Degrees added to the caster's camera FOV when the beam lands, eases back to normal over CastImpactDuration (negative zooms in, 0 turns it off)
	UPROPERTY(EditDefaultsOnly,BlueprintReadOnly,Category="Beam|CastImpact")
	float CastFOVOffset=-8.f;
	
	UPROPERTY(EditDefaultsOnly,BlueprintReadOnly,Category="Beam|CastImpact")
	TSubclassOf<UCameraShakeBase> CastCameraShake;
	
	UPROPERTY(EditDefaultsOnly,BlueprintReadOnly,Category="Beam|CastImpact")
	float CastCameraShakeScale=1.f;
	
	//----------------------------------------------------------------------//
	// Damage (server): the hit enemy and every enemy around it
	//----------------------------------------------------------------------//
	
	/**
	 * Damages on the server when the beam is released: AT_SendMouseCursorData hands the release's aim to
	 * OnServerMouseCursorData before GA_BeamBP's graph sees it, which calls ApplyBeamDamage. Off: the beam only does what
	 * the graph does (knockback and effects); the graph can still call ApplyBeamDamage itself.
	 */
	UPROPERTY(EditDefaultsOnly,BlueprintReadOnly,Category="Beam|Damage")
	bool bApplyDamageOnRelease=true;
	
	/**
	 * Server: finds what the beam hit along the aim in TargetData (AT_SendMouseCursorData's crosshair hit) and damages it
	 * and every enemy within Splash.Radius of it. The hit enemy is the first one along the beam: a Mech Sentinel (swept
	 * against their hit capsules, which the crosshair trace passes through) or the character the crosshair hit, whichever
	 * is closer. The client reports that character hit, so the server only takes it when the hit point lies on its own
	 * beam line (stopped by the first wall it finds), on that character's collision on the server, within a slack for
	 * lag, and in the open from the beam's start. The damage lands later this frame, outside the Mass phases. Returns
	 * false when the data holds no aim or was already used.
	 */
	UFUNCTION(BlueprintCallable,BlueprintAuthorityOnly,Category="Beam|Damage")
	bool ApplyBeamDamage(const FGameplayAbilityTargetDataHandle& TargetData);
	
	/**
	 * Damage to the enemy the beam hits, at the ability level. Characters: added to IncomingDamage through
	 * CharacterDamageEffect. Sentinels: the base; the caster's AttackDamage and the sentinel's armor apply on top
	 * (ExecCalc_SentinelDamage).
	 */
	UPROPERTY(EditDefaultsOnly,BlueprintReadOnly,Category="Beam|Damage")
	FScalableFloat HitDamage=FScalableFloat(150.f);
	
	/** The hit enemy takes HitDamage. Off: only the enemies around it are damaged. */
	UPROPERTY(EditDefaultsOnly,BlueprintReadOnly,Category="Beam|Damage")
	bool bDamageHitEnemy=true;
	
	/** The beam also hits players (and ships players fly), like the knockback in GA_BeamBP. Off: only the splash can reach them (Splash.bDamagePlayers). */
	UPROPERTY(EditDefaultsOnly,BlueprintReadOnly,Category="Beam|Damage",meta=(EditCondition="bDamageHitEnemy"))
	bool bHitDamagesPlayers=true;
	
	/** Damage to each enemy around the hit (not the hit enemy itself), at the ability level. Same rules as HitDamage. */
	UPROPERTY(EditDefaultsOnly,BlueprintReadOnly,Category="Beam|Damage")
	FScalableFloat SplashDamage=FScalableFloat(75.f);
	
	/**
	 * Who the splash reaches: radius around the hit, falloff, characters / players / sentinels, caps. Its damage effects are
	 * also the ones the hit enemy gets (empty: the built-in SetByCaller damage for characters, the GameMode rules'
	 * DefaultSentinelDamageEffect for sentinels).
	 */
	UPROPERTY(EditDefaultsOnly,BlueprintReadOnly,Category="Beam|Damage")
	FMySplashDamageSettings Splash;
	
	/** Splash only around an enemy the beam hit. Off: a beam that hits the ground or a wall splashes there too. */
	UPROPERTY(EditDefaultsOnly,BlueprintReadOnly,Category="Beam|Damage")
	bool bSplashOnlyOnEnemyHit=true;
	
	/** Optional cue executed at the splash centre (Location, RawMagnitude = Splash.Radius), e.g. a burst effect. Empty: none. */
	UPROPERTY(EditDefaultsOnly,BlueprintReadOnly,Category="Beam|Damage",meta=(Categories="GameplayCue"))
	FGameplayTag SplashGameplayCue;
	
	/** Thickness of the beam against the sentinels' hit capsules (cm). */
	UPROPERTY(EditDefaultsOnly,BlueprintReadOnly,Category="Beam|Damage",meta=(ClampMin="0",ForceUnits="cm"))
	float BeamSentinelRadius=40.f;
	
	/** How far the beam reaches sentinels and characters when no wall stops it (cm). */
	UPROPERTY(EditDefaultsOnly,BlueprintReadOnly,Category="Beam|Damage",meta=(ClampMin="100",ForceUnits="cm"))
	float BeamRange=20000.f;
	
	/** Server: the release's target data from AT_SendMouseCursorData; applies the beam damage (bApplyDamageOnRelease). */
	virtual void OnServerMouseCursorData(const FGameplayAbilityTargetDataHandle& Data) override;
	
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
	
private:
	/** The last target data damaged, kept alive so a replay of it is told apart from new data that reused its memory. */
	TSharedPtr<FGameplayAbilityTargetData> LastDamagedTargetData;
};
