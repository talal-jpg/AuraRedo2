// Fill out your copyright notice in the Description page of Project Settings.


#include "MyGameMode.h"

#include "EOS/MultiplayerSessionsSubsystem.h"


void AMyGameMode::PostLogin(APlayerController* NewPlayer)
{
	Super::PostLogin(NewPlayer);

	// Check if this is the hosting player (the first local controller on the server)
	if (NewPlayer && NewPlayer->IsLocalController())
	{
		UGameInstance* GameInstance = GetGameInstance();
		if (GameInstance)
		{
			UMultiplayerSessionsSubsystem* Subsystem = GameInstance->GetSubsystem<UMultiplayerSessionsSubsystem>();
			if (Subsystem)
			{
				// This registers the host fully into the active Steam/EOS session roster
				Subsystem->StartSession();
				UE_LOG(LogTemp, Log, TEXT("Host has logged into map. Starting Online Session."));
			}
		}
	}
	
}
