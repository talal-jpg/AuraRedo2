// Fill out your copyright notice in the Description page of Project Settings.

// The lobby's console (Docs/Airship/round2/SPEC_B_LOBBY.md Appendix L-B): the CVar Aura.Lobby.Enable and the
// Aura.Lobby.* commands the PIE harnesses use. The commands are compiled out of Shipping like Aura.Match.*; the CVar stays,
// AMyGameMode::DecideLobby reads it by name at InitGame.

#include "DrawDebugHelpers.h"
#include "Engine/GameInstance.h"
#include "Engine/GameViewportClient.h"
#include "Engine/LocalPlayer.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "HAL/IConsoleManager.h"
#include "Match/MyLobbyPanel.h"
#include "Match/MyMatchSettings.h"
#include "Match/MyMatchTypes.h"
#include "Match/MyTeamLibrary.h"
#include "MyGameMode.h"
#include "MyGameState.h"
#include "MyPlayerState.h"
#include "PlayerInput/MyPlayerController2.h"

// Read at InitGame (a change applies on the next map load). The URL's Lobby=0|1 wins
static TAutoConsoleVariable<int32> CVarLobbyEnable(
	TEXT("Aura.Lobby.Enable"),
	-1,
	TEXT("In-level lobby (SPEC_B_LOBBY): -1 = by the URL's Lobby option (default; the main menu's Host Game adds Lobby=1), 0 = off, 1 = on. Read when a map loads with the match on; the URL option wins."),
	ECVF_Default);

#if !UE_BUILD_SHIPPING
// Named, not anonymous: the unity build compiles this file together with others
namespace MyLobbyConsole
{
	AMyGameMode* GetLobbyGameMode(UWorld* World, const TCHAR* Command)
	{
		if (!World || World->GetNetMode() == NM_Client)
		{
			UE_LOG(LogMatch, Warning, TEXT("%s: run it on the server (listen server window or standalone)"), Command);
			return nullptr;
		}

		AMyGameMode* GameMode = World->GetAuthGameMode<AMyGameMode>();

		if (!GameMode || !GameMode->IsMatchOn())
		{
			UE_LOG(LogMatch, Warning, TEXT("%s: no match runs here (the lobby needs the match on)"), Command);
			return nullptr;
		}
		return GameMode;
	}

	/** PlayerIndex = the index in GameState->PlayerArray (join order, 0 = the host, bots included). */
	AMyPlayerState* GetPlayer(UWorld* World, const TArray<FString>& Args, int32 ArgIndex, const TCHAR* Command)
	{
		const AGameStateBase* GameState = World ? World->GetGameState() : nullptr;

		if (!GameState || !Args.IsValidIndex(ArgIndex) || !Args[ArgIndex].IsNumeric())
		{
			UE_LOG(LogMatch, Warning, TEXT("%s: give the player index (GameState PlayerArray order: 0 = the host, bots included)"), Command);
			return nullptr;
		}

		const int32 Index = FCString::Atoi(*Args[ArgIndex]);
		AMyPlayerState* Player = GameState->PlayerArray.IsValidIndex(Index) ? Cast<AMyPlayerState>(GameState->PlayerArray[Index]) : nullptr;

		if (!Player)
		{
			UE_LOG(LogMatch, Warning, TEXT("%s: no player %d (%d in the player array)"), Command, Index, GameState->PlayerArray.Num());
		}
		return Player;
	}

	bool GetInt(const TArray<FString>& Args, int32 ArgIndex, int32& OutValue)
	{
		if (!Args.IsValidIndex(ArgIndex) || !Args[ArgIndex].IsNumeric())
		{
			return false;
		}
		OutValue = FCString::Atoi(*Args[ArgIndex]);
		return true;
	}

	void Report(bool bOk, const FText& Why, const TCHAR* Command, const FString& What)
	{
		if (bOk)
		{
			UE_LOG(LogMatch, Log, TEXT("%s: %s%s"), Command, *What, Why.IsEmpty() ? TEXT("") : *FString::Printf(TEXT(" (%s)"), *Why.ToString()));
		}
		else
		{
			UE_LOG(LogMatch, Warning, TEXT("%s: %s refused%s"), Command, *What, Why.IsEmpty() ? TEXT("") : *FString::Printf(TEXT(": %s"), *Why.ToString()));
		}
	}

	FString EnumText(const UEnum* Enum, int64 Value)
	{
		return Enum ? Enum->GetNameStringByValue(Value) : FString::FromInt(static_cast<int32>(Value));
	}

	FAutoConsoleCommandWithWorldAndArgs GStatusCommand(
		TEXT("Aura.Lobby.Status"),
		TEXT("Aura.Lobby.Status - the lobby on this machine (any): phase, in lobby, countdown, start block, rematch, arriving; the server's spawn mode and zones; per player team, ready, request, host, arriving; per local player panel open, IgnoreInput, mouse capture, cursor."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			const AMyGameState* GameState = World ? World->GetGameState<AMyGameState>() : nullptr;

			if (!GameState)
			{
				UE_LOG(LogMatch, Log, TEXT("Aura.Lobby.Status: no AMyGameState in this world"));
				return;
			}

			const double Now = GameState->GetServerWorldTimeSeconds();
			const ENetMode NetMode = World->GetNetMode();
			UE_LOG(LogMatch, Log, TEXT("Lobby status (%s %s): phase %s, in lobby %d, counting %d, countdown %.1f s, lobby round %d, start block %s, not ready %d, rematch %d, arriving %d, expected %d, teams %d / %d, rules Teams=%s"),
				NetMode == NM_Client ? TEXT("client") : (NetMode == NM_Standalone ? TEXT("standalone") : TEXT("server")), *GetNameSafe(World),
				UMyTeamLibrary::GetMatchPhaseName(GameState->GetMatchPhase()), GameState->IsInLobby() ? 1 : 0, GameState->IsLobbyCountingDown() ? 1 : 0,
				GameState->IsLobbyCountingDown() ? GameState->GetPhaseEndServerTime() - Now : -1.0, GameState->IsLobbyRound() ? 1 : 0,
				*EnumText(StaticEnum<EMyLobbyStartBlock>(), static_cast<int64>(GameState->GetLobbyStartBlock())), GameState->GetLobbyNotReady(),
				GameState->IsLobbyRematch() ? 1 : 0, GameState->CountArrivingPlayers(), GameState->GetExpectedPlayers(),
				GameState->GetTeamState(0).NumPlayers, GameState->GetTeamState(1).NumPlayers, UMyTeamLibrary::GetTeamModeOption(GameState->GetMatchRules().TeamMode));

			if (const AMyGameMode* GameMode = World->GetAuthGameMode<AMyGameMode>())
			{
				UE_LOG(LogMatch, Log, TEXT("  server: spawn %s (request %s), ground %s, ground ready %d, zones %d, bots %d, will return to the lobby %d"),
					AMyGameMode::GetLobbyGroundName(GameMode->GetLobbyGround()), *EnumText(StaticEnum<EMyLobbySpawn>(), static_cast<int64>(GameMode->GetLobbySpawnRequest())),
					GameMode->GetLobbyGroundText().IsEmpty() ? TEXT("-") : *GameMode->GetLobbyGroundText(), GameMode->IsLobbyGroundReady() ? 1 : 0,
					GameMode->GetLobbyZones().Num(), GameMode->GetNumLobbyBots(), GameMode->WillReturnToLobby() ? 1 : 0);

				for (int32 Index = 0; Index < GameMode->GetLobbyZones().Num(); ++Index)
				{
					const FBox& Zone = GameMode->GetLobbyZones()[Index];
					UE_LOG(LogMatch, Log, TEXT("  zone %d: min (%.0f, %.0f, %.0f) max (%.0f, %.0f, %.0f)"), Index, Zone.Min.X, Zone.Min.Y, Zone.Min.Z,
						Zone.Max.X, Zone.Max.Y, Zone.Max.Z);
				}
			}

			for (int32 Index = 0; Index < GameState->PlayerArray.Num(); ++Index)
			{
				const AMyPlayerState* Player = Cast<AMyPlayerState>(GameState->PlayerArray[Index]);

				if (!Player)
				{
					continue;
				}

				const APawn* Pawn = Player->GetPawn();
				UE_LOG(LogMatch, Log, TEXT("  player %d %s: id %d, team %d, ready %d, request %d, host %d, arriving %d, bot %d, pawn %s%s"), Index,
					*Player->GetPlayerName(), Player->GetPlayerId(), Player->GetTeamId(), Player->IsLobbyReady() ? 1 : 0, Player->GetRequestedTeam(),
					Player->IsHost() ? 1 : 0, Player->IsArriving() ? 1 : 0, Player->IsABot() ? 1 : 0, Pawn ? *Pawn->GetClass()->GetName() : TEXT("none"),
					Pawn ? *FString::Printf(TEXT(" at %s"), *Pawn->GetActorLocation().ToCompactString()) : TEXT(""));
			}

			// The local players of this world: the lobby panel and the input mode (critique M2: the panel closes at the start)
			const UGameInstance* GameInstance = World->GetGameInstance();
			UGameViewportClient* Viewport = World->GetGameViewport();

			if (GameInstance)
			{
				int32 LocalIndex = 0;

				for (const ULocalPlayer* LocalPlayer : GameInstance->GetLocalPlayers())
				{
					APlayerController* PC = LocalPlayer ? LocalPlayer->GetPlayerController(World) : nullptr;
					const AMyPlayerController2* MyPC = Cast<AMyPlayerController2>(PC);
					IMyLobbyPanel* Panel = MyPC ? MyPC->GetLobbyPanel() : nullptr;

					UE_LOG(LogMatch, Log, TEXT("  local %d %s: panel %d (widget %d), IgnoreInput %d, capture %d, cursor %d, pause menu %d"), LocalIndex++,
						*GetNameSafe(PC), Panel && Panel->IsPanelOpen() ? 1 : 0, Panel ? 1 : 0, Viewport && Viewport->IgnoreInput() ? 1 : 0,
						Viewport ? static_cast<int32>(Viewport->GetMouseCaptureMode()) : -1, PC && PC->bShowMouseCursor ? 1 : 0,
						MyPC && MyPC->IsPauseMenuOpen() ? 1 : 0);
				}
			}
		})
	);

	FAutoConsoleCommandWithWorldAndArgs GStartCommand(
		TEXT("Aura.Lobby.Start"),
		TEXT("Aura.Lobby.Start [strict] - server: the host's Start (the lobby countdown). Soft blocks (not ready, uneven, one ship) are ignored unless strict."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (AMyGameMode* GameMode = GetLobbyGameMode(World, TEXT("Aura.Lobby.Start")))
			{
				const bool bStrict = Args.Num() > 0 && Args[0].Equals(TEXT("strict"), ESearchCase::IgnoreCase);
				FText Why;
				const bool bOk = GameMode->StartFromLobby(/*bForce=*/!bStrict, Why);
				Report(bOk, Why, TEXT("Aura.Lobby.Start"), bStrict ? TEXT("start (strict)") : TEXT("start"));
			}
		})
	);

	FAutoConsoleCommandWithWorldAndArgs GCancelCommand(
		TEXT("Aura.Lobby.Cancel"),
		TEXT("Aura.Lobby.Cancel - server: cancels the lobby countdown (back to phase Lobby, the team ships released or removed)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (AMyGameMode* GameMode = GetLobbyGameMode(World, TEXT("Aura.Lobby.Cancel")))
			{
				Report(GameMode->CancelLobbyStart(TEXT("Aura.Lobby.Cancel")), FText::GetEmpty(), TEXT("Aura.Lobby.Cancel"), TEXT("cancel"));
			}
		})
	);

	FAutoConsoleCommandWithWorldAndArgs GReadyCommand(
		TEXT("Aura.Lobby.Ready"),
		TEXT("Aura.Lobby.Ready <PlayerIndex> <0|1> - server: a player's ready flag (PlayerArray order, 0 = the host, who has none)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			AMyGameMode* GameMode = GetLobbyGameMode(World, TEXT("Aura.Lobby.Ready"));
			AMyPlayerState* Player = GameMode ? GetPlayer(World, Args, 0, TEXT("Aura.Lobby.Ready")) : nullptr;
			int32 Value = 0;

			if (!Player || !GetInt(Args, 1, Value))
			{
				UE_LOG(LogMatch, Warning, TEXT("Usage: Aura.Lobby.Ready <PlayerIndex> <0|1>"));
				return;
			}

			FText Why;
			const bool bOk = GameMode->SetLobbyReady(Player, Value != 0, Why);
			Report(bOk, Why, TEXT("Aura.Lobby.Ready"), FString::Printf(TEXT("%s ready %d"), *Player->GetPlayerName(), Value != 0 ? 1 : 0));
		})
	);

	FAutoConsoleCommandWithWorldAndArgs GTeamCommand(
		TEXT("Aura.Lobby.Team"),
		TEXT("Aura.Lobby.Team <PlayerIndex> <0|1|255> - server: that player's switch request (a move, a swap or pending; 255 cancels), as his SWITCH button."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			AMyGameMode* GameMode = GetLobbyGameMode(World, TEXT("Aura.Lobby.Team"));
			AMyPlayerState* Player = GameMode ? GetPlayer(World, Args, 0, TEXT("Aura.Lobby.Team")) : nullptr;
			int32 Team = 0;

			if (!Player || !GetInt(Args, 1, Team))
			{
				UE_LOG(LogMatch, Warning, TEXT("Usage: Aura.Lobby.Team <PlayerIndex> <0|1|255>"));
				return;
			}

			FText Why;
			const bool bOk = GameMode->RequestLobbyTeam(Player, static_cast<uint8>(FMath::Clamp(Team, 0, 255)), Why);
			Report(bOk, Why, TEXT("Aura.Lobby.Team"), FString::Printf(TEXT("%s asks for team %d"), *Player->GetPlayerName(), Team));
		})
	);

	FAutoConsoleCommandWithWorldAndArgs GMoveCommand(
		TEXT("Aura.Lobby.Move"),
		TEXT("Aura.Lobby.Move <PlayerIndex> <0|1> - server: the host's MOVE (a swap when that team is full)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			AMyGameMode* GameMode = GetLobbyGameMode(World, TEXT("Aura.Lobby.Move"));
			AMyPlayerState* Player = GameMode ? GetPlayer(World, Args, 0, TEXT("Aura.Lobby.Move")) : nullptr;
			int32 Team = 0;

			if (!Player || !GetInt(Args, 1, Team) || Team < 0 || Team >= MyMatch::NumTeams)
			{
				UE_LOG(LogMatch, Warning, TEXT("Usage: Aura.Lobby.Move <PlayerIndex> <0|1>"));
				return;
			}

			FText Why;
			const bool bOk = GameMode->MoveLobbyPlayer(Player, static_cast<uint8>(Team), Why);
			Report(bOk, Why, TEXT("Aura.Lobby.Move"), FString::Printf(TEXT("%s to team %d"), *Player->GetPlayerName(), Team));
		})
	);

	FAutoConsoleCommandWithWorldAndArgs GBotsCommand(
		TEXT("Aura.Lobby.Bots"),
		TEXT("Aura.Lobby.Bots <n> - server, tests: keeps n bot player states (an AI controller with a player state, no pawn, a team by the join rule); 0 removes them. Start refuses while bots exist."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			AMyGameMode* GameMode = GetLobbyGameMode(World, TEXT("Aura.Lobby.Bots"));
			int32 Count = 0;

			if (!GameMode || !GetInt(Args, 0, Count))
			{
				UE_LOG(LogMatch, Warning, TEXT("Usage: Aura.Lobby.Bots <n>"));
				return;
			}

			FText Why;
			const int32 Kept = GameMode->SetLobbyBots(Count, Why);
			Report(Kept == FMath::Clamp(Count, 0, 8), Why, TEXT("Aura.Lobby.Bots"), FString::Printf(TEXT("%d bot(s)"), Kept));
		})
	);

	FAutoConsoleCommandWithWorldAndArgs GResolveCommand(
		TEXT("Aura.Lobby.Resolve"),
		TEXT("Aura.Lobby.Resolve [Auto|PlayerStarts|PathStart] - server: picks the lobby ground again (default UMyMatchSettings::LobbySpawn) and sends every lobby pawn to a lobby spot."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			AMyGameMode* GameMode = GetLobbyGameMode(World, TEXT("Aura.Lobby.Resolve"));

			if (!GameMode)
			{
				return;
			}

			if (!GameMode->IsInLobby())
			{
				UE_LOG(LogMatch, Warning, TEXT("Aura.Lobby.Resolve: not in the lobby"));
				return;
			}

			EMyLobbySpawn Request = UMyMatchSettings::Get()->LobbySpawn;

			if (Args.Num() > 0)
			{
				if (Args[0].Equals(TEXT("Auto"), ESearchCase::IgnoreCase))
				{
					Request = EMyLobbySpawn::Auto;
				}
				else if (Args[0].Equals(TEXT("PlayerStarts"), ESearchCase::IgnoreCase))
				{
					Request = EMyLobbySpawn::PlayerStarts;
				}
				else if (Args[0].Equals(TEXT("PathStart"), ESearchCase::IgnoreCase))
				{
					Request = EMyLobbySpawn::PathStart;
				}
				else
				{
					UE_LOG(LogMatch, Warning, TEXT("Usage: Aura.Lobby.Resolve [Auto|PlayerStarts|PathStart]"));
					return;
				}
			}

			GameMode->ResolveLobbySpawn(Request);
			GameMode->SendLobbyPawnsToSpots();
			UE_LOG(LogMatch, Log, TEXT("Aura.Lobby.Resolve: %s picked %s (ground %s)"), *EnumText(StaticEnum<EMyLobbySpawn>(), static_cast<int64>(Request)),
				AMyGameMode::GetLobbyGroundName(GameMode->GetLobbyGround()), GameMode->GetLobbyGroundText().IsEmpty() ? TEXT("-") : *GameMode->GetLobbyGroundText());
		})
	);

	FAutoConsoleCommandWithWorldAndArgs GReturnCommand(
		TEXT("Aura.Lobby.Return"),
		TEXT("Aura.Lobby.Return - server: back to the lobby now (the pause menu's BACK TO LOBBY): remembers the teams, travels to this map with Lobby=1 (seamless outside PIE)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (AMyGameMode* GameMode = GetLobbyGameMode(World, TEXT("Aura.Lobby.Return")))
			{
				GameMode->ReturnToLobby();
			}
		})
	);

	FAutoConsoleCommandWithWorldAndArgs GZoneCommand(
		TEXT("Aura.Lobby.Zone"),
		TEXT("Aura.Lobby.Zone [seconds] - server: draws the lobby zone boxes (10 s default)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			const AMyGameMode* GameMode = GetLobbyGameMode(World, TEXT("Aura.Lobby.Zone"));

			if (!GameMode)
			{
				return;
			}

			const float Seconds = Args.Num() > 0 ? FMath::Max(0.1f, FCString::Atof(*Args[0])) : 10.f;

			for (const FBox& Zone : GameMode->GetLobbyZones())
			{
				DrawDebugBox(World, Zone.GetCenter(), Zone.GetExtent(), FColor::Cyan, false, Seconds, 0, 30.f);
			}

			UE_LOG(LogMatch, Log, TEXT("Aura.Lobby.Zone: %d zone box(es) drawn for %.0f s"), GameMode->GetLobbyZones().Num(), Seconds);
		})
	);

	FAutoConsoleCommandWithWorldAndArgs GPanelCommand(
		TEXT("Aura.Lobby.Panel"),
		TEXT("Aura.Lobby.Panel <0|1> - local: closes / opens this machine's lobby panel (the lobby widget must exist)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			int32 Open = 0;
			const UGameInstance* GameInstance = World ? World->GetGameInstance() : nullptr;
			const ULocalPlayer* LocalPlayer = GameInstance ? GameInstance->GetFirstGamePlayer() : nullptr;
			const AMyPlayerController2* PC = LocalPlayer ? Cast<AMyPlayerController2>(LocalPlayer->GetPlayerController(World)) : nullptr;
			IMyLobbyPanel* Panel = PC ? PC->GetLobbyPanel() : nullptr;

			if (!GetInt(Args, 0, Open))
			{
				UE_LOG(LogMatch, Warning, TEXT("Usage: Aura.Lobby.Panel <0|1>"));
				return;
			}

			if (!Panel)
			{
				UE_LOG(LogMatch, Warning, TEXT("Aura.Lobby.Panel: no lobby widget on this machine"));
				return;
			}

			if (Open != 0)
			{
				Panel->OpenPanel();
			}
			else
			{
				Panel->ClosePanel();
			}

			UE_LOG(LogMatch, Log, TEXT("Aura.Lobby.Panel: %s"), Panel->IsPanelOpen() ? TEXT("open") : TEXT("closed"));
		})
	);
}
#endif
