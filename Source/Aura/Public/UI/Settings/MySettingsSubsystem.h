// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "Engine/World.h"
#include "MySettingsSubsystem.generated.h"

/**
 * Applies the saved UMyGameUserSettings without a menu being open: the rendering and
 * accessibility values once at startup, and the volumes for every map this game
 * instance loads (a sound mix only lives as long as the world's audio state).
 */
UCLASS()
class AURA_API UMySettingsSubsystem : public UGameInstanceSubsystem
{
	GENERATED_BODY()

public:
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void Deinitialize() override;

private:
	void HandleWorldInitializedActors(const UWorld::FActorsInitializedParams& Params);

	FDelegateHandle WorldInitializedActorsHandle;
};
