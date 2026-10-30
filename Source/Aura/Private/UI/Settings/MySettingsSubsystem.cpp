// Fill out your copyright notice in the Description page of Project Settings.

#include "UI/Settings/MySettingsSubsystem.h"
#include "UI/Settings/MyGameUserSettings.h"
#include "Engine/GameInstance.h"

void UMySettingsSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);

	if (UMyGameUserSettings* Settings = UMyGameUserSettings::GetMyGameUserSettings())
	{
		Settings->ApplyRenderingAndAccessibilitySettings();
	}
	else
	{
		UE_LOG(LogTemp, Warning, TEXT("MySettingsSubsystem: GameUserSettingsClassName isn't UMyGameUserSettings, Options screen values won't persist"));
	}

	WorldInitializedActorsHandle = FWorldDelegates::OnWorldInitializedActors.AddUObject(this, &ThisClass::HandleWorldInitializedActors);
}

void UMySettingsSubsystem::Deinitialize()
{
	FWorldDelegates::OnWorldInitializedActors.Remove(WorldInitializedActorsHandle);

	Super::Deinitialize();
}

void UMySettingsSubsystem::HandleWorldInitializedActors(const UWorld::FActorsInitializedParams& Params)
{
	// Every world in the process reports here (PIE runs one per client)
	UWorld* World = Params.World;
	if (!World || World->GetGameInstance() != GetGameInstance())
	{
		return;
	}

	if (UMyGameUserSettings* Settings = UMyGameUserSettings::GetMyGameUserSettings())
	{
		Settings->ApplyAudioSettings(World);
	}
}
