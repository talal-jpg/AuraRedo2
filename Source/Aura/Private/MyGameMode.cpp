// Fill out your copyright notice in the Description page of Project Settings.


#include "MyGameMode.h"

#include "MyGameState.h"
#include "EOS/MultiplayerSessionsSubsystem.h"


AMyGameMode::AMyGameMode()
{
	// Ranks players by how far along the path they are
	GameStateClass = AMyGameState::StaticClass();
}


void AMyGameMode::PreLogin(const FString& Options, const FString& Address, const FUniqueNetIdRepl& UniqueId, FString& ErrorMessage)
{
	Super::PreLogin(Options, Address, UniqueId, ErrorMessage);
	if (!ErrorMessage.IsEmpty())
	{
		return;
	}

	if (UGameInstance* GameInstance = GetGameInstance())
	{
		if (UMultiplayerSessionsSubsystem* Subsystem = GameInstance->GetSubsystem<UMultiplayerSessionsSubsystem>())
		{
			// A non-empty message refuses the connection and is what the joining player sees
			ErrorMessage = Subsystem->CheckJoinAllowed(UniqueId, GetNumPlayers());
		}
	}
}

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
