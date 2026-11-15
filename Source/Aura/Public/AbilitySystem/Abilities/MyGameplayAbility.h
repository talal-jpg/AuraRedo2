// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Abilities/GameplayAbility.h"
#include "MyGameplayAbility.generated.h"

/**
 * 
 */
UCLASS()
class AURA_API UMyGameplayAbility : public UGameplayAbility
{
	GENERATED_BODY()
	
public:
	UPROPERTY(EditAnywhere, Category = "Tags")
	FGameplayTag InputTag;
	
	UPROPERTY(EditAnywhere, Category = "Tags")
	FGameplayTag AbilityTag;
	
	UPROPERTY(EditAnywhere, Category = "Tags")
	FGameplayTag CooldownTag;
	
	UPROPERTY(EditDefaultsOnly,BlueprintReadOnly, Category = "Damage")
	FScalableFloat Damage;

	/**
	 * Server only: UAT_SendMouseCursorData hands its target data to the ability here just before broadcasting it to the
	 * ability's graph, for the listen server host's own data as well as for remote clients'. The graph may end the
	 * ability in that broadcast, so this runs first. Does nothing by default (UGA_GunShoot damages Mech Sentinels).
	 */
	virtual void OnServerMouseCursorData(const FGameplayAbilityTargetDataHandle& TargetData) {}
};
