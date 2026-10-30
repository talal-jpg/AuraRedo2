// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Engine/DeveloperSettings.h"
#include "MyMenuSettings.generated.h"

class USoundMix;
class USoundClass;
class UInputMappingContext;

/**
 * Assets the Menu3 Options screen needs. Project Settings > Game > Aura Menu, saved to DefaultGame.ini.
 *
 * Volumes: each slider overrides its sound class in VolumeSoundMix. Master falls back to the
 * engine's default sound class (Project Settings > Audio > Default Sound Class), so it works
 * with nothing set here; Music / Effects / Voice / Interface do nothing until their class is set
 * and your sounds use it (make them children of the master class).
 */
UCLASS(Config = Game, DefaultConfig, meta = (DisplayName = "Aura Menu"))
class AURA_API UMyMenuSettings : public UDeveloperSettings
{
	GENERATED_BODY()

public:
	/** Sound mix the volume sliders write their class overrides into. Empty = one is made at runtime. */
	UPROPERTY(Config, EditAnywhere, Category = "Audio")
	TSoftObjectPtr<USoundMix> VolumeSoundMix;

	/** Empty = Project Settings > Audio > Default Sound Class. */
	UPROPERTY(Config, EditAnywhere, Category = "Audio")
	TSoftObjectPtr<USoundClass> MasterSoundClass;

	UPROPERTY(Config, EditAnywhere, Category = "Audio")
	TSoftObjectPtr<USoundClass> MusicSoundClass;

	UPROPERTY(Config, EditAnywhere, Category = "Audio")
	TSoftObjectPtr<USoundClass> EffectsSoundClass;

	UPROPERTY(Config, EditAnywhere, Category = "Audio")
	TSoftObjectPtr<USoundClass> VoiceSoundClass;

	UPROPERTY(Config, EditAnywhere, Category = "Audio")
	TSoftObjectPtr<USoundClass> InterfaceSoundClass;

	/**
	 * Mapping contexts whose player-mappable keys show up in Options > Controls (e.g. IMC_PlayerInputMappingContext).
	 * A mapping is listed when its Input Action (or the mapping itself) has Player Mappable Key Settings with a Name.
	 */
	UPROPERTY(Config, EditAnywhere, Category = "Controls")
	TArray<TSoftObjectPtr<UInputMappingContext>> RebindableMappingContexts;
};
