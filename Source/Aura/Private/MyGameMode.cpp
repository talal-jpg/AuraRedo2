// Fill out your copyright notice in the Description page of Project Settings.


#include "MyGameMode.h"

#include "AbilitySystemComponent.h"
#include "EngineUtils.h"
#include "GameplayEffectExtension.h"
#include "MyGameState.h"
#include "MyPlayerState.h"
#include "TimerManager.h"
#include "AbilitySystem/MyAbilitySystemComponent.h"
#include "AbilitySystem/MyAttributeSet.h"
#include "Actors/MyHexPathSpawner.h"
#include "Actors/MyHexPlatform.h"
#include "Airship/AirshipLaneComponent.h"
#include "Airship/AirshipPawn.h"
#include "Airship/AirshipSettings.h"
#include "Airship/AirshipSubsystem.h"
#include "Burrower/BurrowerSpawnSubsystem.h"
#include "Components/CapsuleComponent.h"
#include "Engine/PlayerStartPIE.h"
#include "EOS/MultiplayerSessionsSubsystem.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerStart.h"
#include "HAL/IConsoleManager.h"
#include "Interfaces/MyCombatInterface.h"
#include "Kismet/GameplayStatics.h"
#include "Match/MyLaneSubsystem.h"
#include "Match/MyMatchMemorySubsystem.h"
#include "Match/MyMatchSettings.h"
#include "Match/MyTeamLibrary.h"
#include "MechSwarm/Core/MechSentinelSwarmRules.h"
#include "MechSwarm/Core/MechSentinelSwarmSubsystem.h"
#include "MechSwarm/Spawning/MechSentinelWaveSpawner.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "NiagaraSystem.h"
#include "UObject/ConstructorHelpers.h"

// Named, not anonymous: the unity build compiles this file together with others
namespace MyGameModeMatch
{
	const TCHAR* PhaseName(EMyMatchPhase Phase)
	{
		switch (Phase)
		{
		case EMyMatchPhase::WaitingToStart: return TEXT("WaitingToStart");
		case EMyMatchPhase::Countdown: return TEXT("Countdown");
		case EMyMatchPhase::InProgress: return TEXT("InProgress");
		case EMyMatchPhase::Ended: return TEXT("Ended");
		case EMyMatchPhase::Lobby: return TEXT("Lobby");
		default: return TEXT("None");
		}
	}

	/** The URL / menu option value of a team mode (the restart writes it, InitGame reads it). */
	const TCHAR* TeamModeOption(EMyTeamMode Mode)
	{
		switch (Mode)
		{
		case EMyTeamMode::Practice: return TEXT("practice");
		case EMyTeamMode::OneVsOne: return TEXT("1v1");
		case EMyTeamMode::TwoVsTwo: return TEXT("2v2");
		default: return TEXT("auto");
		}
	}

	/** auto / 1v1 / 2v2 / practice, case-insensitive; the menu's RuleSets strings and the enum names too. */
	bool ParseTeamMode(const FString& InValue, EMyTeamMode& OutMode)
	{
		const FString Value = InValue.TrimStartAndEnd();
		auto Is = [&Value](const TCHAR* Name) { return Value.Equals(Name, ESearchCase::IgnoreCase); };

		if (Is(TEXT("auto")) || Is(TEXT("Auto teams")) || Is(TEXT("0")))
		{
			OutMode = EMyTeamMode::Auto;
		}
		else if (Is(TEXT("practice")) || Is(TEXT("1")))
		{
			OutMode = EMyTeamMode::Practice;
		}
		else if (Is(TEXT("1v1")) || Is(TEXT("OneVsOne")) || Is(TEXT("2")))
		{
			OutMode = EMyTeamMode::OneVsOne;
		}
		else if (Is(TEXT("2v2")) || Is(TEXT("TwoVsTwo")) || Is(TEXT("3")))
		{
			OutMode = EMyTeamMode::TwoVsTwo;
		}
		else
		{
			return false;
		}
		return true;
	}

	bool ParseBool(const FString& InValue, bool& bOut)
	{
		const FString Value = InValue.TrimStartAndEnd();
		auto Is = [&Value](const TCHAR* Name) { return Value.Equals(Name, ESearchCase::IgnoreCase); };

		if (Is(TEXT("1")) || Is(TEXT("true")) || Is(TEXT("yes")) || Is(TEXT("on")))
		{
			bOut = true;
			return true;
		}
		if (Is(TEXT("0")) || Is(TEXT("false")) || Is(TEXT("no")) || Is(TEXT("off")))
		{
			bOut = false;
			return true;
		}
		return false;
	}

	bool ParseInt(const FString& InValue, int32& OutValue)
	{
		const FString Value = InValue.TrimStartAndEnd();

		if (Value.IsEmpty() || !Value.IsNumeric())
		{
			return false;
		}
		OutValue = FCString::Atoi(*Value);
		return true;
	}

	/** Clamps Value into [Min, Max] and logs when it had to. */
	int32 ClampLogged(int32 Value, int32 Min, int32 Max, const TCHAR* Name, const TCHAR* Source)
	{
		const int32 Clamped = FMath::Clamp(Value, Min, Max);

		if (Clamped != Value)
		{
			UE_LOG(LogMatch, Warning, TEXT("Match rules (%s): %s %d is out of %d..%d, using %d"), Source, Name, Value, Min, Max, Clamped);
		}
		return Clamped;
	}

	int32 MaxSwarmDifficulty()
	{
		const int32 NumPresets = UMyMatchSettings::Get()->SwarmDifficulties.Num();
		return FMath::Max(0, (NumPresets > 0 ? FMath::Min(NumPresets, MyMatch::NumDifficulties) : MyMatch::NumDifficulties) - 1);
	}

	void ClampRules(FMyMatchRules& Rules, const TCHAR* Source)
	{
		Rules.ShipLives = ClampLogged(Rules.ShipLives, 1, 9, TEXT("ShipLives"), Source);
		Rules.SwarmDifficulty = ClampLogged(Rules.SwarmDifficulty, 0, MaxSwarmDifficulty(), TEXT("Swarm"), Source);
		Rules.TimeLimitMinutes = ClampLogged(Rules.TimeLimitMinutes, 0, 60, TEXT("TimeLimit"), Source);
	}

	FString TeamLabel(uint8 TeamId)
	{
		return TeamId < MyMatch::NumTeams ? UMyTeamLibrary::GetTeamName(TeamId).ToString() : FString(TEXT("none"));
	}

	FString RulesText(const FMyMatchRules& Rules)
	{
		return FString::Printf(TEXT("Teams=%s ShipLives=%d Swarm=%d TimeLimit=%d FF=%d GrappleShips=%d LaneAssist=%d"), TeamModeOption(Rules.TeamMode),
			Rules.ShipLives, Rules.SwarmDifficulty, Rules.TimeLimitMinutes, Rules.bFriendlyFire ? 1 : 0, Rules.bGrappleShips ? 1 : 0, Rules.bLaneAssist ? 1 : 0);
	}

	/** Spawn transforms stand upright: a rolling deck must not tilt the new pawn. */
	FTransform YawOnly(const FTransform& Transform)
	{
		return FTransform(FRotator(0.0, Transform.Rotator().Yaw, 0.0), Transform.GetLocation());
	}

	bool IsDeadCharacter(AActor* Actor)
	{
		return Actor && Actor->Implements<UMyCombatInterface>() && IMyCombatInterface::Execute_IsDead(Actor);
	}
}


AMyGameMode::AMyGameMode()
{
	// Ranks players by how far along the path they are
	GameStateClass = AMyGameState::StaticClass();

	// Loaded with the class, so it is cooked too (the project cooks maps only)
	static ConstructorHelpers::FObjectFinder<UNiagaraSystem> RespawnFXSystem(
		TEXT("/Game/Level/GAS/GameplayAbilities/GA_Beam/Niagara/NS_BeamClaude/NS_Claude_RespawnFX.NS_Claude_RespawnFX"));
	RespawnFX = RespawnFXSystem.Object;
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

	// 1v1 / 2v2 have a hard cap per team, the same way the session check refuses a full lobby
	if (ErrorMessage.IsEmpty() && bMatchOn)
	{
		const int32 Cap = GetTeamCap();
		RecountTeams();
		const AMyGameState* MyGameState = GetMatchGameState();

		if (Cap > 0 && MyGameState && MyGameState->GetTeamState(0).NumPlayers >= Cap && MyGameState->GetTeamState(1).NumPlayers >= Cap)
		{
			ErrorMessage = FString::Printf(TEXT("That match is full (%s)."), MyGameModeMatch::TeamModeOption(MatchRules.TeamMode));
			UE_LOG(LogMatch, Log, TEXT("Join refused: %s"), *ErrorMessage);
		}
	}
}

void AMyGameMode::PostLogin(APlayerController* NewPlayer)
{
	Super::PostLogin(NewPlayer);

	// Check if this is the hosting player (the first local controller on the server). With the lobby the session starts
	// with each round instead (BeginRound, SPEC_B_LOBBY 5.6)
	if (NewPlayer && NewPlayer->IsLocalController() && !bLobbyRound)
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

	// The hard arrival; a seamless one comes through InitSeamlessTravelPlayer
	OnPlayerArrived(NewPlayer, false);
}

// The ASC is on the PlayerState and goes on to the next pawn, which shouldn't start with any of it. A static member (it was
// an anonymous-namespace function) so MyGameModeLobby.cpp uses the same one
void AMyGameMode::CancelActiveAbilities(const AController* Controller, const APawn* Pawn)
{
	const AMyPlayerState* MyPlayerState = Controller ? Controller->GetPlayerState<AMyPlayerState>() : nullptr;
	UAbilitySystemComponent* ASC = MyPlayerState ? MyPlayerState->MyAbilitySystemComponent : nullptr;

	if (!ASC || !Pawn || ASC->GetAvatarActor() != Pawn)
	{
		return;
	}

	TArray<FGameplayAbilitySpecHandle> ToCancel;

	for (const FGameplayAbilitySpec& Spec : ASC->GetActivatableAbilities())
	{
		// Passives (GiveAbilityAndActivateOnce) keep running for the next pawn
		if (Spec.IsActive() && !Spec.RemoveAfterActivation)
		{
			ToCancel.Add(Spec.Handle);
		}
	}

	for (const FGameplayAbilitySpecHandle& Handle : ToCancel)
	{
		ASC->CancelAbilityHandle(Handle);
	}
}

bool AMyGameMode::TakeBackPawn(AController* Controller, const TCHAR* Why)
{
	APawn* Pawn = Controller ? Controller->GetPawn() : nullptr;

	if (!Pawn)
	{
		return false;
	}

	// A seated pilot's pawn is his ship: put him back on his feet first, the ship isn't ours to destroy
	if (AAirshipPawn* Ship = Cast<AAirshipPawn>(Pawn))
	{
		Ship->UnboardPilot(false);
		Pawn = Controller->GetPawn();

		if (!Pawn || Cast<AAirshipPawn>(Pawn))
		{
			return false;
		}
	}

	UE_LOG(LogMatch, Log, TEXT("Match: %s's pawn taken back (%s)"), *GetNameSafe(Controller->PlayerState), Why);
	CancelActiveAbilities(Controller, Pawn);
	UnwatchPlayerPawn(Pawn);
	Controller->UnPossess();
	Pawn->Destroy();
	return true;
}

void AMyGameMode::SetPlayerDefaults(APawn* PlayerPawn)
{
	Super::SetPlayerDefaults(PlayerPawn);

	WatchPlayerPawn(PlayerPawn);

	// The lanes are 450 m apart at S = 2: with the engine's 150 m default, deck riders, reelers and enemies across the
	// field wouldn't replicate to most viewers, and a client can't aim at what it doesn't have (SPEC_B B10)
	const float CullDistance = UMyMatchSettings::Get()->MatchNetCullDistance;

	if (bMatchOn && CullDistance > 0.f && Cast<ACharacter>(PlayerPawn))
	{
		PlayerPawn->SetNetCullDistanceSquared(FMath::Square(static_cast<double>(CullDistance)));
	}
}

void AMyGameMode::Logout(AController* Exiting)
{
	if (FPendingRespawn* Pending = PendingRespawns.Find(Exiting))
	{
		GetWorldTimerManager().ClearTimer(Pending->FXTimer);
		GetWorldTimerManager().ClearTimer(Pending->RespawnTimer);
		PendingRespawns.Remove(Exiting);
	}

	// Its pawn is destroyed after this; with no entry, OnPlayerPawnDestroyed ignores it
	for (auto It = WatchedPawns.CreateIterator(); It; ++It)
	{
		if (!It.Value().IsValid() || It.Value() == Exiting)
		{
			It.RemoveCurrent();
		}
	}

	// The leaving player state is still in the player array until it is destroyed after this: counted out explicitly
	if (bMatchOn && Exiting)
	{
		UE_LOG(LogMatch, Log, TEXT("Team: %s leaves (%s)"), Exiting->PlayerState ? *Exiting->PlayerState->GetPlayerName() : *Exiting->GetName(),
			*MyGameModeMatch::TeamLabel(GetControllerTeam(Exiting)));
		EvaluateTeams(Exiting->PlayerState);
	}

	Super::Logout(Exiting);
}

bool AMyGameMode::PlayerCanRestart_Implementation(APlayerController* Player)
{
	return !IsHoldingPawns() && !IsWaitingForTeamStart(Player) && !PendingRespawns.Contains(Player) && Super::PlayerCanRestart_Implementation(Player);
}

// =============================================================================
// Team match (Docs/Airship/round2/SPEC_B.md B1-B5, B9, B10): teams, team ships, lives, phases, rules. Server only.
// =============================================================================

AMyGameState* AMyGameMode::GetMatchGameState() const
{
	return GetGameState<AMyGameState>();
}

EMyMatchPhase AMyGameMode::GetPhase() const
{
	const AMyGameState* MyGameState = GetMatchGameState();
	return MyGameState ? MyGameState->GetMatchPhase() : EMyMatchPhase::None;
}

double AMyGameMode::GetServerTime() const
{
	// The clock every machine shows the countdowns with (clients add their offset)
	const AMyGameState* MyGameState = GetMatchGameState();
	return MyGameState ? MyGameState->GetServerWorldTimeSeconds() : GetWorld()->GetTimeSeconds();
}

float AMyGameMode::GetLayoutScale()
{
	if (!PathSpawner.IsValid())
	{
		TActorIterator<AMyHexPathSpawner> It(GetWorld());
		PathSpawner = It ? *It : nullptr;
	}

	return PathSpawner.IsValid() ? PathSpawner->GetLayoutScale() : 1.f;
}

uint8 AMyGameMode::GetControllerTeam(const AController* Controller)
{
	const AMyPlayerState* MyPlayerState = Controller ? Controller->GetPlayerState<AMyPlayerState>() : nullptr;
	return MyPlayerState ? MyPlayerState->GetTeamId() : MyMatch::NoTeam;
}

void AMyGameMode::InitGame(const FString& MapName, const FString& Options, FString& ErrorMessage)
{
	Super::InitGame(MapName, Options, ErrorMessage);

	using namespace MyGameModeMatch;
	const UMyMatchSettings* Settings = UMyMatchSettings::Get();

	// RestartMatch writes Round into the travel URL. A match map loaded without it (from the menu, an open command) is
	// a fresh match: last match's teams are forgotten
	UMyMatchMemorySubsystem* Memory = UMyMatchMemorySubsystem::Get(this);
	RoundIndex = 0;

	bLobbyFromRound = UGameplayStatics::HasOption(Options, TEXT("Round"));

	if (bLobbyFromRound)
	{
		RoundIndex = FMath::Max(0, UGameplayStatics::GetIntOption(Options, TEXT("Round"), 0));

		if (Memory)
		{
			if (Memory->GetRoundIndex() != RoundIndex)
			{
				UE_LOG(LogMatch, Warning, TEXT("Match memory counted round %d, the URL says %d: using the URL's"), Memory->GetRoundIndex(), RoundIndex);
			}
			Memory->SetRoundIndex(RoundIndex);
		}
	}
	else if (Memory)
	{
		Memory->Reset();
	}

	// On / off: MatchMaps (short names, no PIE prefix), then the CVar Aura.Match.Enable, then the URL's Match option
	const FString ShortMapName = UGameplayStatics::GetCurrentLevelName(this, /*bRemovePrefixString=*/true);
	bool bOn = Settings->MatchMaps.IsEmpty() || Settings->MatchMaps.ContainsByPredicate([&ShortMapName](const FString& Map)
	{
		return Map.Equals(ShortMapName, ESearchCase::IgnoreCase);
	});
	FString Reason = Settings->MatchMaps.IsEmpty() ? TEXT("MatchMaps is empty") : (bOn ? TEXT("in MatchMaps") : TEXT("not in MatchMaps"));

	if (const IConsoleVariable* EnableCVar = IConsoleManager::Get().FindConsoleVariable(TEXT("Aura.Match.Enable")))
	{
		const int32 Enable = EnableCVar->GetInt();

		if (Enable >= 0)
		{
			bOn = Enable > 0;
			Reason = FString::Printf(TEXT("Aura.Match.Enable %d"), Enable);
		}
	}

	if (UGameplayStatics::HasOption(Options, TEXT("Match")))
	{
		bool bUrlOn = false;
		const FString Value = UGameplayStatics::ParseOption(Options, TEXT("Match"));

		if (ParseBool(Value, bUrlOn))
		{
			bOn = bUrlOn;
			Reason = FString::Printf(TEXT("URL Match=%s"), *Value);
		}
		else
		{
			UE_LOG(LogMatch, Warning, TEXT("URL option Match=%s: use 0 or 1"), *Value);
		}
	}

	bMatchOn = bOn;
	bLobbyRound = false;

	if (!bMatchOn)
	{
		UE_LOG(LogMatch, Log, TEXT("Match off on %s (%s): every player and ship stays team 255"), *ShortMapName, *Reason);
		return;
	}

	// SPEC_B_LOBBY 4.2: before ParseMatchOptions, which skips the AutoCoopPlayers switch with the lobby
	DecideLobby(Options);
	ParseMatchOptions(Options);

	if (bLobbyRound)
	{
		ResolveLobbySpawn(Settings->LobbySpawn);
	}

	UE_LOG(LogMatch, Log, TEXT("Match on on %s (%s): %s, expected players %d, round %d, lobby %s"), *ShortMapName, *Reason, *RulesText(MatchRules),
		bLobbyRound ? GetLobbyMaxPlayers() : ExpectedPlayers, RoundIndex,
		bLobbyRound ? *FString::Printf(TEXT("on (%s), spawn %s"), *LobbyReason, GetLobbyGroundName(LobbyGround)) : *FString::Printf(TEXT("off (%s)"), *LobbyReason));
}

void AMyGameMode::ParseMatchOptions(const FString& Options)
{
	using namespace MyGameModeMatch;
	const UMyMatchSettings* Settings = UMyMatchSettings::Get();

	// Later wins: the settings' defaults, the command line, the URL (the host's: client join options never reach here)
	MatchRules = Settings->DefaultRules;
	ClampRules(MatchRules, TEXT("DefaultRules"));

	static const TCHAR* CommandLineKeys[][2] =
	{
		{ TEXT("MatchTeams="), TEXT("Teams") },
		{ TEXT("MatchShipLives="), TEXT("ShipLives") },
		{ TEXT("MatchSwarm="), TEXT("Swarm") },
		{ TEXT("MatchTimeLimit="), TEXT("TimeLimit") },
		{ TEXT("MatchFF="), TEXT("FF") },
		{ TEXT("MatchGrappleShips="), TEXT("GrappleShips") },
		{ TEXT("MatchLaneAssist="), TEXT("LaneAssist") },
	};

	FString CommandLineOptions;

	for (const auto& Key : CommandLineKeys)
	{
		FString Value;

		if (FParse::Value(FCommandLine::Get(), Key[0], Value))
		{
			CommandLineOptions += FString::Printf(TEXT("?%s=%s"), Key[1], *Value);
		}
	}

	ParseRulesOptions(CommandLineOptions, MatchRules, TEXT("command line"));
	ParseRulesOptions(Options, MatchRules, TEXT("URL"));
	NextTeamMode = MatchRules.TeamMode;

	// Our own option name, not the engine's MaxPlayers (AGameSession reads that one)
	ExpectedPlayers = Settings->DefaultExpectedPlayers;

	if (UGameplayStatics::HasOption(Options, TEXT("Players")))
	{
		int32 Players = 0;
		const FString Value = UGameplayStatics::ParseOption(Options, TEXT("Players"));

		if (ParseInt(Value, Players))
		{
			ExpectedPlayers = ClampLogged(Players, 1, 64, TEXT("Players"), TEXT("URL"));
		}
		else
		{
			UE_LOG(LogMatch, Warning, TEXT("URL option Players=%s is not a number"), *Value);
		}
	}

	ExpectedPlayers = FMath::Max(1, ExpectedPlayers);

	// SPEC_B Q19's alternative, behind a setting: Auto with this many players plays co-op (one ship) instead of 2v1. This
	// round only: NextTeamMode stays Auto, so the restart decides again from the players then in
	// With the lobby, Players is Max Players (not the player count) and the host picks Practice for co-op (SPEC_B_LOBBY 4.2)
	if (!bLobbyRound && MatchRules.TeamMode == EMyTeamMode::Auto && Settings->AutoCoopPlayers > 0 && ExpectedPlayers == Settings->AutoCoopPlayers)
	{
		MatchRules.TeamMode = EMyTeamMode::Practice;
		UE_LOG(LogMatch, Log, TEXT("Match: Auto with %d players plays co-op practice (AutoCoopPlayers)"), ExpectedPlayers);
	}
}

bool AMyGameMode::ParseRulesOptions(const FString& Options, FMyMatchRules& InOutRules, const TCHAR* Source)
{
	using namespace MyGameModeMatch;
	bool bAny = false;

	auto Option = [&Options, &bAny](const TCHAR* Key, FString& OutValue)
	{
		if (!UGameplayStatics::HasOption(Options, Key))
		{
			return false;
		}
		OutValue = UGameplayStatics::ParseOption(Options, Key);
		bAny = true;
		return true;
	};

	auto Warn = [Source](const TCHAR* Key, const FString& Value, const TCHAR* Expected)
	{
		UE_LOG(LogMatch, Warning, TEXT("Match rules (%s): %s=%s is not %s, ignored"), Source, Key, *Value, Expected);
	};

	FString Value;
	int32 Number = 0;
	bool bFlag = false;

	if (Option(TEXT("Teams"), Value) && !ParseTeamMode(Value, InOutRules.TeamMode))
	{
		Warn(TEXT("Teams"), Value, TEXT("auto, 1v1, 2v2 or practice"));
	}

	if (Option(TEXT("ShipLives"), Value))
	{
		if (ParseInt(Value, Number))
		{
			InOutRules.ShipLives = ClampLogged(Number, 1, 9, TEXT("ShipLives"), Source);
		}
		else
		{
			Warn(TEXT("ShipLives"), Value, TEXT("a number"));
		}
	}

	if (Option(TEXT("Swarm"), Value))
	{
		if (ParseInt(Value, Number))
		{
			InOutRules.SwarmDifficulty = ClampLogged(Number, 0, MaxSwarmDifficulty(), TEXT("Swarm"), Source);
		}
		else
		{
			Warn(TEXT("Swarm"), Value, TEXT("a number"));
		}
	}

	if (Option(TEXT("TimeLimit"), Value))
	{
		if (ParseInt(Value, Number))
		{
			InOutRules.TimeLimitMinutes = ClampLogged(Number, 0, 60, TEXT("TimeLimit"), Source);
		}
		else
		{
			Warn(TEXT("TimeLimit"), Value, TEXT("a number of minutes"));
		}
	}

	if (Option(TEXT("FF"), Value))
	{
		if (ParseBool(Value, bFlag))
		{
			InOutRules.bFriendlyFire = bFlag;
		}
		else
		{
			Warn(TEXT("FF"), Value, TEXT("0 or 1"));
		}
	}

	if (Option(TEXT("GrappleShips"), Value))
	{
		if (ParseBool(Value, bFlag))
		{
			InOutRules.bGrappleShips = bFlag;
		}
		else
		{
			Warn(TEXT("GrappleShips"), Value, TEXT("0 or 1"));
		}
	}

	if (Option(TEXT("LaneAssist"), Value))
	{
		if (ParseBool(Value, bFlag))
		{
			InOutRules.bLaneAssist = bFlag;
		}
		else
		{
			Warn(TEXT("LaneAssist"), Value, TEXT("0 or 1"));
		}
	}

	return bAny;
}

FString AMyGameMode::BuildRulesOptions(const FMyMatchRules& Rules, EMyTeamMode TeamMode) const
{
	return FString::Printf(TEXT("?Teams=%s?ShipLives=%d?Swarm=%d?TimeLimit=%d?FF=%d?GrappleShips=%d?LaneAssist=%d"),
		MyGameModeMatch::TeamModeOption(TeamMode), Rules.ShipLives, Rules.SwarmDifficulty, Rules.TimeLimitMinutes,
		Rules.bFriendlyFire ? 1 : 0, Rules.bGrappleShips ? 1 : 0, Rules.bLaneAssist ? 1 : 0);
}

bool AMyGameMode::IsPracticeStart() const
{
	// A standalone game has nobody to wait for. One expected player, in any team mode: the menu's Play Solo (Players=1,
	// whatever the Rules box says; it creates no session, so nobody could join a versus wait) or a restart with only the
	// host left. Someone who joins later (a lobby opened from the pause menu) turns it into versus (B1.3)
	return MatchRules.TeamMode == EMyTeamMode::Practice || GetNetMode() == NM_Standalone || ExpectedPlayers <= 1;
}

int32 AMyGameMode::GetNeededPlayers() const
{
	if (IsPracticeStart())
	{
		return 1;
	}

	switch (MatchRules.TeamMode)
	{
	case EMyTeamMode::OneVsOne: return 2;
	case EMyTeamMode::TwoVsTwo: return 4;
	default: return FMath::Max(2, ExpectedPlayers);
	}
}

int32 AMyGameMode::GetTeamCap() const
{
	switch (MatchRules.TeamMode)
	{
	case EMyTeamMode::OneVsOne: return 1;
	case EMyTeamMode::TwoVsTwo: return 2;
	// Auto keeps balancing past 4 players unless the settings cap it (SPEC_B Q7)
	case EMyTeamMode::Auto: return FMath::Max(0, UMyMatchSettings::Get()->AutoMaxPlayersPerTeam);
	default: return 0;
	}
}

bool AMyGameMode::IsHoldingPawns() const
{
	if (!bMatchOn)
	{
		return false;
	}

	// No pawns while a versus match waits for its players or counts down: nobody races ahead, grows the path or starts
	// the collapse before the others are in (B4.2). The host logs in before StartPlay (phase None): he waits too. With
	// bStartAboard practice starts aboard as well (SPEC_B_LOBBY D10): no pawn during its countdown either. The lobby
	// gives pawns in StartPlay, and holds them only while PathStart waits for its platform
	const bool bStartAboard = UMyMatchSettings::Get()->bStartAboard;

	switch (GetPhase())
	{
	case EMyMatchPhase::None: return bLobbyRound || !IsPracticeStart() || bStartAboard;
	case EMyMatchPhase::Lobby: return !bLobbyGroundReady;
	case EMyMatchPhase::WaitingToStart: return true;
	case EMyMatchPhase::Countdown: return bCountdownVersus || bPracticeToVersus || bStartAboard;
	default: return false;
	}
}

bool AMyGameMode::IsWaitingForTeamStart(const AController* Player) const
{
	const AMyGameState* MyGameState = GetMatchGameState();

	if (!bMatchOn || !MyGameState || GetPhase() != EMyMatchPhase::Countdown)
	{
		return false;
	}

	// A practice countdown (the start, or the host's start with one team) that someone joins on the empty team turns
	// versus when it ends: he waits for that with no pawn and starts aboard with the others (B1.3, B4.2), instead of on
	// the floor at once while the other team's players go to their deck
	const uint8 Team = GetControllerTeam(Player);
	return Team < MyMatch::NumTeams && !MyGameState->GetTeamState(Team).bActive;
}

void AMyGameMode::InitGameState()
{
	Super::InitGameState();

	// Before any player logs in (the host's login comes before StartPlay): HUDs and the lane sides read these
	if (AMyGameState* MyGameState = GetMatchGameState(); MyGameState && bMatchOn)
	{
		MyGameState->SetMatchRules(MatchRules);
		MyGameState->SetRoundIndex(RoundIndex);
		// With the lobby the header shows "n / Max" from the first frame (SPEC_B_LOBBY 4.2)
		MyGameState->SetExpectedPlayers(bLobbyRound ? GetLobbyMaxPlayers() : GetNeededPlayers());
		MyGameState->SetLobbyRound(bLobbyRound);
	}
}

FString AMyGameMode::InitNewPlayer(APlayerController* NewPlayerController, const FUniqueNetIdRepl& UniqueId, const FString& Options, const FString& Portal)
{
	AMyPlayerState* MyPlayerState = NewPlayerController ? NewPlayerController->GetPlayerState<AMyPlayerState>() : nullptr;

	// Before Super: it picks the start spot, and ChoosePlayerStart prefers the team's PlayerStarts. Super is also where
	// the engine makes a ?SpectatorOnly=1 joiner a spectator (the same option test), so that is read here: no team
	const bool bSpectatorOnly = FCString::Stricmp(*UGameplayStatics::ParseOption(Options, TEXT("SpectatorOnly")), TEXT("1")) == 0;

	if (bMatchOn && !bSpectatorOnly)
	{
		AssignTeam(MyPlayerState, UniqueId);
	}

	const FString Error = Super::InitNewPlayer(NewPlayerController, UniqueId, Options, Portal);

	// MustSpectate made him a spectator after all: he plays for nobody
	if (bMatchOn && MyPlayerState && MyPlayerState->IsOnlyASpectator() && MyPlayerState->GetTeamId() != MyMatch::NoTeam)
	{
		MyPlayerState->SetTeamId(MyMatch::NoTeam);
		RecountTeams();
	}

	if (bMatchOn && MyPlayerState)
	{
		const AMyGameState* MyGameState = GetMatchGameState();
		UE_LOG(LogMatch, Log, TEXT("Team: %s joins %s (teams %d / %d, phase %s)"), *MyPlayerState->GetPlayerName(),
			*MyGameModeMatch::TeamLabel(MyPlayerState->GetTeamId()), MyGameState ? MyGameState->GetTeamState(0).NumPlayers : 0,
			MyGameState ? MyGameState->GetTeamState(1).NumPlayers : 0, MyGameModeMatch::PhaseName(GetPhase()));

		// Here, not in PostLogin: a join that starts a countdown (or practice -> versus) must do it before the engine
		// asks PlayerCanRestart for the new player's pawn
		EvaluateTeams();
	}

	return Error;
}

void AMyGameMode::StartPlay()
{
	AMyGameState* MyGameState = GetMatchGameState();

	if (bMatchOn && MyGameState)
	{
		MyGameState->SetMatchRules(MatchRules);
		MyGameState->SetRoundIndex(RoundIndex);
		MyGameState->SetExpectedPlayers(bLobbyRound ? GetLobbyMaxPlayers() : GetNeededPlayers());

		// Before Super: the path spawner builds its first segments in its BeginPlay and the wave spawners queue wave 1 from
		// them (B5.4), so the difficulty has to be in place first
		ApplySwarmDifficulty();
	}

	Super::StartPlay();

	if (!bMatchOn || !MyGameState)
	{
		return;
	}

	// The ships the map brought (B3.1): claimed by a ShipTeam<id> tag, or removed in versus
	for (TActorIterator<AAirshipPawn> It(GetWorld()); It; ++It)
	{
		if (IsValid(*It))
		{
			PlacedShips.Add(*It);
		}
	}

	FTimerManager& TimerManager = GetWorldTimerManager();
	TimerManager.SetTimer(MatchTickTimer, this, &ThisClass::MatchTick, 0.5f, true);
	TimerManager.SetTimer(HealthTickTimer, this, &ThisClass::HealthTick, 0.25f, true);

	// The lobby (SPEC_B_LOBBY 4.7): phase Lobby, the swarm stopped, pawns at the lobby spots; the host starts later
	if (bLobbyRound)
	{
		BeginLobby();
		return;
	}

	if (IsPracticeStart())
	{
		UE_LOG(LogMatch, Log, TEXT("Match: practice start (%s)"), GetNetMode() == NM_Standalone ? TEXT("standalone") : MyGameModeMatch::TeamModeOption(MatchRules.TeamMode));
		StartCountdown(false);
		return;
	}

	MyGameState->SetMatchPhase(EMyMatchPhase::WaitingToStart, 0.0);
	UE_LOG(LogMatch, Log, TEXT("Match: phase WaitingToStart (%s, %d players expected)"), MyGameModeMatch::TeamModeOption(MatchRules.TeamMode), GetNeededPlayers());

	// Listen PIE opens the listen port only after the host's login (UGameInstance::StartPlayInEditorGameInstance), so
	// he looked like a standalone (practice) player then and got a pawn. A versus match holds every pawn until the start
	// (B4.2): take it back, before it has done anything
	for (FConstPlayerControllerIterator It = GetWorld()->GetPlayerControllerIterator(); It; ++It)
	{
		TakeBackPawn(It->Get(), TEXT("it waits for the start: spawned before the listen server opened"));
	}

	EvaluateTeams();
}

void AMyGameMode::AssignTeam(AMyPlayerState* PlayerState, const FUniqueNetIdRepl& UniqueId, uint8 PreferredTeam)
{
	AMyGameState* MyGameState = GetMatchGameState();

	if (!PlayerState || !MyGameState || PlayerState->IsOnlyASpectator())
	{
		return;
	}

	// The new player state is in the player array already, still team 255: not counted
	RecountTeams();
	const int32 Count[MyMatch::NumTeams] = { MyGameState->GetTeamState(0).NumPlayers, MyGameState->GetTeamState(1).NumPlayers };
	uint8 Pick = 0;
	const TCHAR* Why = TEXT("practice");

	if (MatchRules.TeamMode != EMyTeamMode::Practice)
	{
		const int32 Cap = GetTeamCap();
		uint8 Remembered = MyMatch::NoTeam;
		const UMyMatchMemorySubsystem* Memory = UMyMatchMemorySubsystem::Get(this);

		// A seamless arrival's own copied team first (SPEC_B_LOBBY 5.4), with the same cap test
		if (PreferredTeam < MyMatch::NumTeams && (Cap == 0 || Count[PreferredTeam] < Cap))
		{
			Pick = PreferredTeam;
			Why = TEXT("kept");
		}
		// Last round was balanced, so keeping a remembered team keeps it balanced; friends stay together in 2v2
		else if (Memory && Memory->FindTeam(UniqueId, Remembered) && Remembered < MyMatch::NumTeams && (Cap == 0 || Count[Remembered] < Cap))
		{
			Pick = Remembered;
			Why = TEXT("remembered");
		}
		else
		{
			// The smaller team; a tie goes to team 0
			Pick = Count[0] <= Count[1] ? 0 : 1;
			Why = TEXT("balance");
		}

		// PreLogin refused the join if both were full
		if (Cap > 0 && Count[Pick] >= Cap)
		{
			Pick = 1 - Pick;
		}
	}

	PlayerState->SetTeamId(Pick);
	RecountTeams();
	UE_LOG(LogMatch, Verbose, TEXT("Team: player %d -> %s (%s)"), PlayerState->GetPlayerId(), *MyGameModeMatch::TeamLabel(Pick), Why);
}

void AMyGameMode::RecountTeams(const APlayerState* Leaving)
{
	AMyGameState* MyGameState = GetMatchGameState();

	if (!MyGameState)
	{
		return;
	}

	int32 Count[MyMatch::NumTeams] = {};

	for (const APlayerState* PlayerState : MyGameState->PlayerArray)
	{
		const AMyPlayerState* MyPlayerState = Cast<AMyPlayerState>(PlayerState);

		// A player state carried by a seamless travel whose owner is still loading isn't in yet (SPEC_B_LOBBY 5.4 row 4)
		if (MyPlayerState && MyPlayerState != Leaving && !MyPlayerState->IsActorBeingDestroyed() && !MyPlayerState->IsOnlyASpectator()
			&& !MyPlayerState->IsArriving() && MyPlayerState->GetTeamId() < MyMatch::NumTeams)
		{
			++Count[MyPlayerState->GetTeamId()];
		}
	}

	bool bChanged = false;

	for (int32 Team = 0; Team < MyMatch::NumTeams; ++Team)
	{
		if (MyGameState->GetTeamState(Team).NumPlayers != Count[Team])
		{
			MyGameState->EditTeam(Team).NumPlayers = Count[Team];
			bChanged = true;
		}
	}

	if (bChanged)
	{
		MyGameState->MarkTeamsDirty();
	}
}

bool AMyGameMode::IsStartConditionMet() const
{
	const AMyGameState* MyGameState = GetMatchGameState();

	if (!MyGameState)
	{
		return false;
	}

	const int32 Count0 = MyGameState->GetTeamState(0).NumPlayers;
	const int32 Count1 = MyGameState->GetTeamState(1).NumPlayers;

	switch (MatchRules.TeamMode)
	{
	case EMyTeamMode::OneVsOne: return Count0 >= 1 && Count1 >= 1;
	case EMyTeamMode::TwoVsTwo: return Count0 >= 2 && Count1 >= 2;
	case EMyTeamMode::Practice: return Count0 + Count1 >= 1;
	default: return Count0 + Count1 >= GetNeededPlayers();
	}
}

void AMyGameMode::EvaluateTeams(const APlayerState* Leaving)
{
	AMyGameState* MyGameState = GetMatchGameState();

	if (!bMatchOn || !MyGameState)
	{
		return;
	}

	RecountTeams(Leaving);
	const EMyMatchPhase Phase = GetPhase();

	if (Phase == EMyMatchPhase::None)
	{
		return;
	}

	// One wave per path segment is shared by every player: the count factor follows the player count (B5.4)
	// (counted as ApplySwarmDifficulty counts them: the recount just above leaves the leaving player out)
	const int32 NumPlayers = FMath::Max(1, MyGameState->GetTeamState(0).NumPlayers + MyGameState->GetTeamState(1).NumPlayers);

	if (NumPlayers != SwarmPlayerCount)
	{
		ApplySwarmDifficulty();
	}

	switch (Phase)
	{
	case EMyMatchPhase::Lobby:
		// No auto start in the lobby: the host starts (SPEC_B_LOBBY 4.7)
		UpdateLobbyState(Leaving);
		break;

	case EMyMatchPhase::WaitingToStart:
		if (IsStartConditionMet())
		{
			StartCountdown(false);
		}
		break;

	case EMyMatchPhase::Countdown:
		// The lobby countdown: a 1v1 / 2v2 team that empties cancels it (back to the lobby); otherwise PR B's rules below
		if (IsLobbyCountingDown())
		{
			int32 NotReady = 0;

			if (GetLobbyStartBlocks(NotReady, Leaving) & (1u << static_cast<uint32>(EMyLobbyStartBlock::NeedOpponent)))
			{
				const uint8 Empty = MyGameState->GetTeamState(0).NumPlayers == 0 ? 0 : 1;
				CancelLobbyStart(FString::Printf(TEXT("%s has no players"), *MyGameModeMatch::TeamLabel(Empty)), EMyLobbyStartBlock::NeedOpponent);
				break;
			}

			UpdateLobbyState(Leaving);
		}

		if (bPracticeToVersus)
		{
			// The player who turned practice into versus left again before it started
			if (MyGameState->GetTeamState(0).NumPlayers == 0 || MyGameState->GetTeamState(1).NumPlayers == 0)
			{
				CancelPracticeToVersus();
			}
			break;
		}

		// A team that empties before the start goes back to inactive; a versus start that no longer holds waits again
		for (uint8 Team = 0; Team < MyMatch::NumTeams; ++Team)
		{
			const FMyTeamState& State = MyGameState->GetTeamState(Team);

			if (State.bActive && State.NumPlayers == 0 && MyGameState->GetTeamState(1 - Team).NumPlayers > 0)
			{
				MyGameState->EditTeam(Team).bActive = false;
				RemoveTeamShip(Team, TEXT("its players left during the countdown"));
			}
		}

		if (bCountdownVersus && !bHostForcedStart && !IsStartConditionMet())
		{
			BackToWaiting();
		}
		break;

	case EMyMatchPhase::InProgress:
		if (!bVersusRound)
		{
			// Practice turning into versus: a player joined the team nobody played (B1.3). Not in the Practice mode, where
			// everyone is on team 0
			if (MatchRules.TeamMode != EMyTeamMode::Practice)
			{
				for (uint8 Team = 0; Team < MyMatch::NumTeams; ++Team)
				{
					const FMyTeamState& State = MyGameState->GetTeamState(Team);

					if (!State.bActive && State.NumPlayers > 0)
					{
						StartPracticeToVersus(Team);
						break;
					}
				}
			}
		}
		else
		{
			UpdateForfeits();
		}
		break;

	default:
		break;
	}
}

int8 AMyGameMode::GetSideForTeam(uint8 TeamId) const
{
	if (const UMyLaneSubsystem* Lanes = UMyLaneSubsystem::Get(this))
	{
		return Lanes->GetSideForTeam(TeamId);
	}

	// No lane subsystem (a client world never runs this): the same table, swapped as StartCountdown decided
	const AMyGameState* MyGameState = GetMatchGameState();
	const int8 Side = UMyMatchSettings::Get()->GetBaseLaneSide(TeamId);
	return (MyGameState && MyGameState->AreLaneSidesSwapped()) ? -Side : Side;
}

void AMyGameMode::UpdateHandicap()
{
	AMyGameState* MyGameState = GetMatchGameState();
	const UMyMatchSettings* Settings = UMyMatchSettings::Get();

	for (uint8 Team = 0; Team < MyMatch::NumTeams; ++Team)
	{
		MyGameState->EditTeam(Team).BonusLives = 0;
	}

	const FMyTeamState& Team0 = MyGameState->GetTeamState(0);
	const FMyTeamState& Team1 = MyGameState->GetTeamState(1);

	// The bigger team can fly and shoot at once (a pilot plus gunners, about double the firepower): the smaller one gets
	// one extra ship life per missing player, at most 9 lives in all (B1.2)
	if (Settings->bSmallTeamHandicap && Team0.bActive && Team1.bActive && Team0.NumPlayers != Team1.NumPlayers)
	{
		const uint8 Smaller = Team0.NumPlayers < Team1.NumPlayers ? 0 : 1;
		const int32 Difference = FMath::Abs(Team0.NumPlayers - Team1.NumPlayers);
		MyGameState->EditTeam(Smaller).BonusLives = FMath::Clamp(Difference, 0, FMath::Max(0, 9 - MatchRules.ShipLives));
	}
}

void AMyGameMode::ResetTeamsForRound()
{
	AMyGameState* MyGameState = GetMatchGameState();

	for (uint8 Team = 0; Team < MyMatch::NumTeams; ++Team)
	{
		FMyTeamState& State = MyGameState->EditTeam(Team);
		State.LivesLeft = State.bActive ? MatchRules.ShipLives + State.BonusLives : 0;
		State.ShipsLost = 0;
		State.bEliminated = false;
		State.EmptySinceServerTime = 0.0;
	}

	MyGameState->MarkTeamsDirty();
}

void AMyGameMode::StartCountdown(bool bForced, float DelayOverride, bool bFromLobby)
{
	AMyGameState* MyGameState = GetMatchGameState();
	const UMyMatchSettings* Settings = UMyMatchSettings::Get();

	if (!MyGameState)
	{
		return;
	}

	GetWorldTimerManager().ClearTimer(CountdownTimer);
	bHostForcedStart = bForced;
	bPracticeToVersus = false;
	RecountTeams();

	// The active teams: those with players now (decided again when the countdown ends)
	int32 NumActive = 0;

	for (uint8 Team = 0; Team < MyMatch::NumTeams; ++Team)
	{
		FMyTeamState& State = MyGameState->EditTeam(Team);
		State.bActive = State.NumPlayers > 0;
		State.ShipRespawnServerTime = 0.0;
		NumActive += State.bActive ? 1 : 0;
	}

	// A host who is the only player but a spectator: still one team to show
	if (NumActive == 0)
	{
		MyGameState->EditTeam(0).bActive = true;
		NumActive = 1;
	}

	bCountdownVersus = NumActive == 2;

	// This round's lane sides (B1.6), decided once here and kept until the next round: swapped on odd versus rounds only.
	// A practice has no opponent to be fair to, and its lone ship would sit on the lane about 274 m from the start floor.
	// A ship left from a countdown that went back to waiting is placed again when its side changes
	const bool bSwapSides = Settings->bAlternateSides && bCountdownVersus && RoundIndex % 2 == 1;

	if (bSwapSides != MyGameState->AreLaneSidesSwapped())
	{
		MyGameState->SetLaneSidesSwapped(bSwapSides);

		for (uint8 Team = 0; Team < MyMatch::NumTeams; ++Team)
		{
			if (IsValid(MyGameState->GetTeamState(Team).Ship))
			{
				RemoveTeamShip(Team, TEXT("lane sides changed"));
			}
		}
	}

	for (uint8 Team = 0; Team < MyMatch::NumTeams; ++Team)
	{
		MyGameState->EditTeam(Team).LaneSide = GetSideForTeam(Team);
	}

	UpdateHandicap();
	ResetTeamsForRound();

	const float Delay = FMath::Max(0.f, DelayOverride >= 0.f ? DelayOverride : Settings->MatchStartDelay);
	MyGameState->SetMatchPhase(EMyMatchPhase::Countdown, GetServerTime() + Delay);
	MyGameState->SetMatchEndServerTime(0.0);

	// The ships are there to put the players on when it ends; they wait in their lanes until then (Clamp NotStarted).
	// From the lobby the untagged placed ship stays until the end: its removal can't be undone by a cancel (SPEC_B_LOBBY 4.7)
	ClaimOrSpawnShips(bCountdownVersus, /*bRemoveUntaggedPlaced=*/!bFromLobby);
	MyGameState->MarkTeamsDirty();
	MyGameState->MulticastMatchEvent(EMyMatchEvent::Countdown, MyMatch::NoTeam, FMath::CeilToInt(Delay));

	UE_LOG(LogMatch, Log, TEXT("Match: phase Countdown %.1f s (%s%s, BLUE %d / ORANGE %d players, lives %d / %d)"), Delay,
		bCountdownVersus ? TEXT("versus") : TEXT("practice"), bFromLobby ? TEXT(", from the lobby") : (bForced ? TEXT(", started by the host") : TEXT("")),
		MyGameState->GetTeamState(0).NumPlayers, MyGameState->GetTeamState(1).NumPlayers,
		MyGameState->GetTeamState(0).LivesLeft, MyGameState->GetTeamState(1).LivesLeft);

	if (Delay > 0.f)
	{
		GetWorldTimerManager().SetTimer(CountdownTimer, this, &ThisClass::OnCountdownEnd, Delay, false);
	}
	else
	{
		GetWorldTimerManager().SetTimerForNextTick(this, &ThisClass::OnCountdownEnd);
	}
}

void AMyGameMode::OnCountdownEnd()
{
	AMyGameState* MyGameState = GetMatchGameState();

	if (!MyGameState || GetPhase() != EMyMatchPhase::Countdown)
	{
		return;
	}

	GetWorldTimerManager().ClearTimer(CountdownTimer);
	RecountTeams();

	// The lobby countdown: a 1v1 / 2v2 team that emptied in the last moment goes back to the lobby (SPEC_B_LOBBY 4.7)
	if (IsLobbyCountingDown())
	{
		int32 NotReady = 0;

		if (GetLobbyStartBlocks(NotReady) & (1u << static_cast<uint32>(EMyLobbyStartBlock::NeedOpponent)))
		{
			CancelLobbyStart(TEXT("a team has no players at the start"), EMyLobbyStartBlock::NeedOpponent);
			return;
		}
	}

	// Practice -> versus (B1.3): both teams start over, the players already in keep playing
	if (bPracticeToVersus)
	{
		bPracticeToVersus = false;

		if (MyGameState->GetTeamState(0).NumPlayers == 0 || MyGameState->GetTeamState(1).NumPlayers == 0)
		{
			bPracticeToVersus = true;
			CancelPracticeToVersus();
			return;
		}

		bVersusRound = true;

		for (uint8 Team = 0; Team < MyMatch::NumTeams; ++Team)
		{
			MyGameState->EditTeam(Team).bActive = true;
		}

		UpdateHandicap();
		ResetTeamsForRound();

		for (uint8 Team = 0; Team < MyMatch::NumTeams; ++Team)
		{
			AAirshipPawn* Ship = MyGameState->GetTeamState(Team).Ship;

			if (IsValid(Ship) && !Ship->IsAirshipDead())
			{
				HealShip(Ship);
				ProtectShip(Ship);
			}
			else
			{
				SpawnTeamShip(Team, GetShipRespawnU(Team));
			}
		}

		BeginRound();
		return;
	}

	// The active teams again: a team that emptied loses its ship (no life counted), a team that got its first player
	// meanwhile (a host-started practice that someone joined) plays
	int32 NumActive = 0;

	for (uint8 Team = 0; Team < MyMatch::NumTeams; ++Team)
	{
		FMyTeamState& State = MyGameState->EditTeam(Team);
		const bool bHasPlayers = State.NumPlayers > 0;

		if (State.bActive && !bHasPlayers)
		{
			State.bActive = false;
			RemoveTeamShip(Team, TEXT("empty when the countdown ended"));
		}
		else if (!State.bActive && bHasPlayers && MatchRules.TeamMode != EMyTeamMode::Practice)
		{
			State.bActive = true;
			State.LaneSide = GetSideForTeam(Team);
		}

		NumActive += MyGameState->GetTeamState(Team).bActive ? 1 : 0;
	}

	if (NumActive == 0)
	{
		MyGameState->EditTeam(0).bActive = true;
		NumActive = 1;
	}

	if (bCountdownVersus && NumActive < 2 && !bHostForcedStart)
	{
		BackToWaiting();
		return;
	}

	bVersusRound = NumActive == 2;
	bCountdownVersus = false;
	UpdateHandicap();
	ResetTeamsForRound();
	ClaimOrSpawnShips(bVersusRound);

	// The 15 s of protection count from the start, not from the countdown's spawn
	for (uint8 Team = 0; Team < MyMatch::NumTeams; ++Team)
	{
		AAirshipPawn* Ship = MyGameState->GetTeamState(Team).Ship;

		if (IsValid(Ship) && !Ship->IsAirshipDead())
		{
			ProtectShip(Ship);
		}
	}

	BeginRound();
}

void AMyGameMode::BeginRound()
{
	AMyGameState* MyGameState = GetMatchGameState();
	const double Now = GetServerTime();

	// Versus only: lanes are out of each other's range and an undriven ship is safe from the swarm, so a match nobody
	// fights would never end otherwise (B4.4)
	const double MatchEnd = (bVersusRound && MatchRules.TimeLimitMinutes > 0) ? Now + MatchRules.TimeLimitMinutes * 60.0 : 0.0;
	MyGameState->SetMatchEndServerTime(MatchEnd);
	bTimeWarningSent = false;

	MyGameState->SetMatchPhase(EMyMatchPhase::InProgress, 0.0);
	MyGameState->MarkTeamsDirty();
	MyGameState->MulticastMatchEvent(EMyMatchEvent::Started, MyMatch::NoTeam, bVersusRound ? 1 : 0);

	UE_LOG(LogMatch, Log, TEXT("Match: phase InProgress, %s: BLUE %d players %d lives%s, ORANGE %d players %d lives%s, time limit %s"),
		bVersusRound ? TEXT("versus") : TEXT("practice"),
		MyGameState->GetTeamState(0).NumPlayers, MyGameState->GetTeamState(0).LivesLeft, MyGameState->GetTeamState(0).bActive ? TEXT("") : TEXT(" (inactive)"),
		MyGameState->GetTeamState(1).NumPlayers, MyGameState->GetTeamState(1).LivesLeft, MyGameState->GetTeamState(1).bActive ? TEXT("") : TEXT(" (inactive)"),
		MatchEnd > 0.0 ? *FString::Printf(TEXT("%d min"), MatchRules.TimeLimitMinutes) : TEXT("none"));

	// The lobby's end (SPEC_B_LOBBY 4.7): lobby pawns and their timed effects go, lobby rules off, the swarm runs
	if (MyGameState->IsInLobby())
	{
		TakeBackLobbyPawns();

		// Ready flags and switch requests mean something in the lobby only; a player state carried to the next lobby
		// must not arrive ready (it counts only once it has arrived, AMyPlayerState::IsArriving)
		for (APlayerState* PlayerState : MyGameState->PlayerArray)
		{
			if (AMyPlayerState* MyPlayerState = Cast<AMyPlayerState>(PlayerState))
			{
				MyPlayerState->SetLobbyReady(false);
				MyPlayerState->SetRequestedTeam(MyMatch::NoTeam);
			}
		}

		MyGameState->SetInLobby(false);
		GetWorldTimerManager().ClearTimer(LobbyTickTimer);
		ResumeSwarm();
		UE_LOG(LogMatch, Log, TEXT("Lobby: over, the match runs (ships unlocked, damage on, ranking on)"));
	}

	// Every round (5.6): Steam and EOS start a session from Pending or Ended only, so a running one is left alone
	StartSessionIfHost();

	SpawnWaitingPlayers();
}

void AMyGameMode::BackToWaiting()
{
	// Never in a lobby round: its countdown goes back to the lobby instead (SPEC_B_LOBBY 4.7)
	if (IsInLobby())
	{
		CancelLobbyStart(TEXT("not enough players"));
		return;
	}

	AMyGameState* MyGameState = GetMatchGameState();
	GetWorldTimerManager().ClearTimer(CountdownTimer);
	bCountdownVersus = false;
	bHostForcedStart = false;

	for (uint8 Team = 0; Team < MyMatch::NumTeams; ++Team)
	{
		if (MyGameState->GetTeamState(Team).NumPlayers == 0)
		{
			MyGameState->EditTeam(Team).bActive = false;
			RemoveTeamShip(Team, TEXT("back to waiting for players"));
		}
	}

	MyGameState->SetMatchPhase(EMyMatchPhase::WaitingToStart, 0.0);
	MyGameState->MarkTeamsDirty();
	UE_LOG(LogMatch, Log, TEXT("Match: back to WaitingToStart (BLUE %d / ORANGE %d players)"), MyGameState->GetTeamState(0).NumPlayers,
		MyGameState->GetTeamState(1).NumPlayers);
}

void AMyGameMode::StartPracticeToVersus(uint8 JoinedTeam)
{
	AMyGameState* MyGameState = GetMatchGameState();
	const UMyMatchSettings* Settings = UMyMatchSettings::Get();

	GetWorldTimerManager().ClearTimer(CountdownTimer);
	bPracticeToVersus = true;
	bHostForcedStart = false;
	bCountdownVersus = false;

	FMyTeamState& Joined = MyGameState->EditTeam(JoinedTeam);
	Joined.bActive = true;

	for (uint8 Team = 0; Team < MyMatch::NumTeams; ++Team)
	{
		MyGameState->EditTeam(Team).LaneSide = GetSideForTeam(Team);
	}

	UpdateHandicap();
	RemoveUntaggedPlacedShips();

	// The players already in keep playing through it (B1.3), so their ship keeps cruising or returning too (the lane
	// reads bPlayGoesOn); the sides stay this round's (decided by the practice's own countdown)
	const float Delay = FMath::Max(0.f, Settings->MatchStartDelay);
	MyGameState->SetMatchPhase(EMyMatchPhase::Countdown, GetServerTime() + Delay, /*bInPlayGoesOn=*/true);
	MyGameState->SetMatchEndServerTime(0.0);
	MyGameState->MarkTeamsDirty();
	MyGameState->MulticastMatchEvent(EMyMatchEvent::PracticeToVersus, JoinedTeam, FMath::CeilToInt(Delay));
	UE_LOG(LogMatch, Log, TEXT("Match: practice -> versus, %s joined: countdown %.1f s, then both teams start over"),
		*MyGameModeMatch::TeamLabel(JoinedTeam), Delay);

	if (Delay > 0.f)
	{
		GetWorldTimerManager().SetTimer(CountdownTimer, this, &ThisClass::OnCountdownEnd, Delay, false);
	}
	else
	{
		GetWorldTimerManager().SetTimerForNextTick(this, &ThisClass::OnCountdownEnd);
	}
}

void AMyGameMode::CancelPracticeToVersus()
{
	AMyGameState* MyGameState = GetMatchGameState();
	GetWorldTimerManager().ClearTimer(CountdownTimer);
	bPracticeToVersus = false;

	for (uint8 Team = 0; Team < MyMatch::NumTeams; ++Team)
	{
		if (MyGameState->GetTeamState(Team).NumPlayers == 0)
		{
			MyGameState->EditTeam(Team).bActive = false;
			RemoveTeamShip(Team, TEXT("practice -> versus cancelled"));
		}
	}

	UpdateHandicap();
	MyGameState->SetMatchPhase(EMyMatchPhase::InProgress, 0.0);
	MyGameState->MarkTeamsDirty();
	UE_LOG(LogMatch, Log, TEXT("Match: practice -> versus cancelled (the new player left), practice goes on"));
}

void AMyGameMode::SpawnWaitingPlayers()
{
	AMyGameState* MyGameState = GetMatchGameState();
	const UMyMatchSettings* Settings = UMyMatchSettings::Get();
	TArray<AController*> Aboard[MyMatch::NumTeams];
	TArray<AController*> Others;

	for (FConstPlayerControllerIterator It = GetWorld()->GetPlayerControllerIterator(); It; ++It)
	{
		APlayerController* PC = It->Get();

		if (!PC || PC->GetPawn() || PendingRespawns.Contains(PC) || MustSpectate(PC) || !PlayerCanRestart(PC))
		{
			continue;
		}

		const uint8 Team = GetControllerTeam(PC);
		const AAirshipPawn* Ship = Team < MyMatch::NumTeams ? MyGameState->GetTeamState(Team).Ship.Get() : nullptr;

		// On the own ship's deck, the only per-round fair start without a map change (B4.2, flag 5); practice too, on team
		// 0's ship, so the match never needs the start floor (SPEC_B_LOBBY D10, 3.4)
		if (Settings->bStartAboard && IsValid(Ship) && !Ship->IsAirshipDead())
		{
			Aboard[Team].Add(PC);
		}
		else
		{
			Others.Add(PC);
		}
	}

	for (uint8 Team = 0; Team < MyMatch::NumTeams; ++Team)
	{
		AAirshipPawn* Ship = MyGameState->GetTeamState(Team).Ship;

		if (Aboard[Team].IsEmpty() || !IsValid(Ship))
		{
			continue;
		}

		TArray<FTransform> Spots;
		Ship->GetDeckSpawnTransforms(Aboard[Team].Num(), Spots);

		for (int32 Index = 0; Index < Aboard[Team].Num(); ++Index)
		{
			AController* Controller = Aboard[Team][Index];

			if (Spots.IsValidIndex(Index))
			{
				RestartPlayerAtTransform(Controller, MyGameModeMatch::YawOnly(Spots[Index]));
			}

			if (Controller->GetPawn())
			{
				UE_LOG(LogMatch, Log, TEXT("Start: %s aboard the %s ship"), *GetNameSafe(Controller->PlayerState), *MyGameModeMatch::TeamLabel(Team));
			}
			else
			{
				UE_LOG(LogMatch, Warning, TEXT("Start: no room on the %s deck for %s, normal start"), *MyGameModeMatch::TeamLabel(Team), *GetNameSafe(Controller->PlayerState));
				RestartPlayer(Controller);
			}
		}
	}

	for (AController* Controller : Others)
	{
		RestartPlayer(Controller);
	}
}

void AMyGameMode::RequestStartMatch()
{
	// The lobby: the host's START MATCH ignores the soft blocks, as a second click would (SPEC_B_LOBBY 7.3)
	if (bMatchOn && GetPhase() == EMyMatchPhase::Lobby)
	{
		FText Why;

		if (!StartFromLobby(/*bForce=*/true, Why))
		{
			UE_LOG(LogMatch, Log, TEXT("Start match: %s"), *Why.ToString());
		}
		return;
	}

	if (!bMatchOn || GetPhase() != EMyMatchPhase::WaitingToStart)
	{
		UE_LOG(LogMatch, Log, TEXT("Start match: only while waiting for players (phase %s)"), MyGameModeMatch::PhaseName(GetPhase()));
		return;
	}

	UE_LOG(LogMatch, Log, TEXT("Start match: the host starts with whoever is in"));
	StartCountdown(true);
}

void AMyGameMode::StartMatchNow()
{
	if (!bMatchOn)
	{
		return;
	}

	if (GetPhase() == EMyMatchPhase::WaitingToStart)
	{
		StartCountdown(true);
	}
	else if (GetPhase() == EMyMatchPhase::Lobby)
	{
		RequestStartMatch();
	}

	if (GetPhase() == EMyMatchPhase::Countdown)
	{
		UE_LOG(LogMatch, Log, TEXT("Start match now: countdown skipped"));
		OnCountdownEnd();
	}
}

void AMyGameMode::EndMatch(EMyMatchResult Result, uint8 WinningTeam, EMyMatchEndReason Reason)
{
	AMyGameState* MyGameState = GetMatchGameState();
	const EMyMatchPhase Phase = GetPhase();

	// The lobby and its countdown have no match to end
	if (!bMatchOn || !MyGameState || GetNetMode() == NM_Client || Phase == EMyMatchPhase::None || Phase == EMyMatchPhase::Ended
		|| Phase == EMyMatchPhase::Lobby || MyGameState->IsInLobby())
	{
		return;
	}

	const UMyMatchSettings* Settings = UMyMatchSettings::Get();
	GetWorldTimerManager().ClearTimer(CountdownTimer);
	bPracticeToVersus = false;
	bCountdownVersus = false;

	for (uint8 Team = 0; Team < MyMatch::NumTeams; ++Team)
	{
		MyGameState->EditTeam(Team).ShipRespawnServerTime = 0.0;
	}

	const uint8 Winner = Result == EMyMatchResult::TeamWon ? WinningTeam : MyMatch::NoTeam;
	const float EndScreen = FMath::Max(0.f, Settings->EndScreenSeconds);
	MyGameState->SetResult(Result, Winner, Reason);
	MyGameState->SetMatchEndServerTime(0.0);
	MyGameState->SetMatchPhase(EMyMatchPhase::Ended, EndScreen > 0.f ? GetServerTime() + EndScreen : 0.0);
	MyGameState->MarkTeamsDirty();
	MyGameState->MulticastMatchEvent(EMyMatchEvent::Ended, Winner, static_cast<int32>(Result));

	// Everything else keeps running (the cruising ships stop on their own: the lane reads the phase)
	StopSwarm();

	// Back to the lobby when this load had one or the host has a session now (Play Solo + Open Lobby included); the end
	// panel reads the game state's copy (SPEC_B_LOBBY 2.5). The session ends with the match (5.6)
	bEndReturnsToLobby = WillReturnToLobby();
	MyGameState->SetLobbyRound(bEndReturnsToLobby);
	EndSessionIfHost();

	if (EndScreen > 0.f)
	{
		GetWorldTimerManager().SetTimer(RestartTimer, this, &ThisClass::OnEndScreenDone, EndScreen, false);
	}

	UE_LOG(LogMatch, Log, TEXT("Match: phase Ended, result %s, winner %s, reason %s, BLUE %d / ORANGE %d ships left, restart in %s%s"),
		*UEnum::GetValueAsString(Result), *MyGameModeMatch::TeamLabel(Winner), *UEnum::GetValueAsString(Reason),
		MyGameState->GetTeamState(0).LivesLeft, MyGameState->GetTeamState(1).LivesLeft,
		EndScreen > 0.f ? *FString::Printf(TEXT("%.0f s"), EndScreen) : TEXT("(host)"), bEndReturnsToLobby ? TEXT(", back to the lobby") : TEXT(""));
}

void AMyGameMode::OnEndScreenDone()
{
	if (bEndReturnsToLobby)
	{
		ReturnToLobby();
	}
	else
	{
		RestartMatch();
	}
}

void AMyGameMode::RestartMatch()
{
	// The same travel as the return to the lobby, without the lobby (SPEC_B_LOBBY 5.3): seamless outside PIE, so Steam
	// clients stay connected (a hard travel drops them, 5.1)
	TravelToRound(/*bLobby=*/false);
}

void AMyGameMode::SetPlayerTeam(AMyPlayerState* Player, uint8 TeamId)
{
	if (!bMatchOn || !Player || TeamId >= MyMatch::NumTeams || Player->GetTeamId() == TeamId)
	{
		return;
	}

	AController* Controller = Player->GetOwningController();
	APawn* Pawn = Controller ? Controller->GetPawn() : nullptr;

	// Off the other team's ship first: its helm or its gun (a deck rider just stands there)
	if (AAirshipPawn* PilotedShip = Cast<AAirshipPawn>(Pawn))
	{
		if (PilotedShip->GetTeamId() != MyMatch::NoTeam && PilotedShip->GetTeamId() != TeamId)
		{
			UE_LOG(LogMatch, Log, TEXT("Team change: %s leaves the %s helm"), *Player->GetPlayerName(), *MyGameModeMatch::TeamLabel(PilotedShip->GetTeamId()));
			PilotedShip->UnboardPilot(false);
		}
	}
	else if (const ACharacter* Character = Cast<ACharacter>(Pawn))
	{
		AAirshipPawn* GunShip = nullptr;
		int32 Station = INDEX_NONE;
		const UAirshipSubsystem* Airships = UAirshipSubsystem::Get(this);

		if (Airships && Airships->FindGunnerStation(Character, GunShip, Station) && GunShip
			&& GunShip->GetTeamId() != MyMatch::NoTeam && GunShip->GetTeamId() != TeamId)
		{
			UE_LOG(LogMatch, Log, TEXT("Team change: %s leaves station %d of the %s ship"), *Player->GetPlayerName(), Station,
				*MyGameModeMatch::TeamLabel(GunShip->GetTeamId()));
			GunShip->DismountGunner(Station, false);
		}
	}

	const uint8 OldTeam = Player->GetTeamId();
	Player->SetTeamId(TeamId);
	Player->SetRequestedTeam(MyMatch::NoTeam);
	UE_LOG(LogMatch, Log, TEXT("Team change: %s %s -> %s"), *Player->GetPlayerName(), *MyGameModeMatch::TeamLabel(OldTeam), *MyGameModeMatch::TeamLabel(TeamId));
	EvaluateTeams();
}

void AMyGameMode::ApplyRules(const FMyMatchRules& NewRules)
{
	FMyMatchRules Rules = NewRules;
	MyGameModeMatch::ClampRules(Rules, TEXT("ApplyRules"));
	NextTeamMode = Rules.TeamMode;

	// The running round keeps its team mode: teams, ships and lives were set up for it. The restart takes the new one.
	// In the lobby (phase Lobby, not its countdown) it applies at once: nothing is set up yet (SPEC_B_LOBBY 4.6)
	const bool bLobbyNow = bMatchOn && GetPhase() == EMyMatchPhase::Lobby;

	if (bMatchOn && GetPhase() != EMyMatchPhase::None && !bLobbyNow && Rules.TeamMode != MatchRules.TeamMode)
	{
		UE_LOG(LogMatch, Log, TEXT("Match rules: Teams=%s from the next restart"), MyGameModeMatch::TeamModeOption(Rules.TeamMode));
		Rules.TeamMode = MatchRules.TeamMode;
	}

	const FMyMatchRules Old = MatchRules;
	MatchRules = Rules;
	AMyGameState* MyGameState = GetMatchGameState();

	if (!bMatchOn || !MyGameState)
	{
		return;
	}

	MyGameState->SetMatchRules(MatchRules);
	UE_LOG(LogMatch, Log, TEXT("Match rules: %s"), *MyGameModeMatch::RulesText(MatchRules));

	// Every caller (the lobby widget, the console, the pause menu) gets the same lobby result: Max Players follows a 1v1 /
	// 2v2, teams again in join order, ready flags off
	if (bLobbyNow && Old.TeamMode != MatchRules.TeamMode)
	{
		const int32 ModeMax = UMyTeamLibrary::GetTeamModeMaxPlayers(MatchRules.TeamMode);

		if (ModeMax > 0)
		{
			ExpectedPlayers = ModeMax;
			MyGameState->SetExpectedPlayers(ModeMax);
		}

		RebalanceLobbyTeams();
		ClearLobbyReady(TEXT("the team mode changed"));
		UpdateLobbyState();
	}

	if (Old.SwarmDifficulty != MatchRules.SwarmDifficulty)
	{
		ApplySwarmDifficulty();
	}

	if (Old.ShipLives != MatchRules.ShipLives)
	{
		const EMyMatchPhase Phase = GetPhase();

		for (uint8 Team = 0; Team < MyMatch::NumTeams; ++Team)
		{
			const FMyTeamState& State = MyGameState->GetTeamState(Team);

			if (!State.bActive)
			{
				continue;
			}

			if (Phase == EMyMatchPhase::InProgress)
			{
				SetTeamShipLives(Team, MatchRules.ShipLives + State.BonusLives);
			}
			else if (Phase == EMyMatchPhase::Countdown || Phase == EMyMatchPhase::WaitingToStart)
			{
				UpdateHandicap();
				MyGameState->EditTeam(Team).LivesLeft = MatchRules.ShipLives + MyGameState->GetTeamState(Team).BonusLives;
				MyGameState->MarkTeamsDirty();
			}
		}
	}

	if (Old.TimeLimitMinutes != MatchRules.TimeLimitMinutes)
	{
		RestartTimeLimit();
	}
}

void AMyGameMode::RestartTimeLimit()
{
	AMyGameState* MyGameState = GetMatchGameState();

	if (!bMatchOn || !MyGameState || GetPhase() != EMyMatchPhase::InProgress || !bVersusRound)
	{
		return;
	}

	const double MatchEnd = MatchRules.TimeLimitMinutes > 0 ? GetServerTime() + MatchRules.TimeLimitMinutes * 60.0 : 0.0;
	MyGameState->SetMatchEndServerTime(MatchEnd);
	bTimeWarningSent = false;
	UE_LOG(LogMatch, Log, TEXT("Match: time limit %d min from now"), MatchRules.TimeLimitMinutes);
}

void AMyGameMode::SetTeamShipLives(uint8 TeamId, int32 NewLives)
{
	AMyGameState* MyGameState = GetMatchGameState();

	if (!bMatchOn || !MyGameState || TeamId >= MyMatch::NumTeams)
	{
		return;
	}

	FMyTeamState& State = MyGameState->EditTeam(TeamId);
	const bool bShipAlive = IsValid(State.Ship) && !State.Ship->IsAirshipDead();
	State.LivesLeft = FMath::Max(FMath::Max(0, NewLives) - State.ShipsLost, bShipAlive ? 1 : 0);

	if (GetPhase() == EMyMatchPhase::InProgress)
	{
		// A team at 0 with its ship dead is out at once; one given lives back gets a ship again
		if (State.LivesLeft == 0 && !bShipAlive && !State.bEliminated)
		{
			State.bEliminated = true;
			State.ShipRespawnServerTime = 0.0;
			MyGameState->MulticastMatchEvent(EMyMatchEvent::TeamEliminated, TeamId, 0);
			ScheduleEndCheck();
		}
		else if (State.LivesLeft > 0 && !bShipAlive && State.ShipRespawnServerTime <= 0.0)
		{
			State.bEliminated = false;
			State.ShipRespawnServerTime = GetServerTime() + UMyMatchSettings::Get()->ShipRespawnDelay;
		}
	}

	MyGameState->MarkTeamsDirty();
	UE_LOG(LogMatch, Log, TEXT("Match: %s ship lives %d -> %d left (%d lost)"), *MyGameModeMatch::TeamLabel(TeamId), NewLives, State.LivesLeft, State.ShipsLost);
}

void AMyGameMode::ApplySwarmDifficulty()
{
	using namespace MyGameModeMatch;
	const UMyMatchSettings* Settings = UMyMatchSettings::Get();
	const FMySwarmDifficultyPreset& Preset = Settings->GetSwarmDifficulty(MatchRules.SwarmDifficulty);
	const AMyGameState* MyGameState = GetMatchGameState();

	// The teams' counts (RecountTeams, kept current on every join and leave), not the player array: during Logout the
	// leaving player state is still in the array, and counting it kept the factor one player too high until the next join
	const int32 NumPlayers = MyGameState ? FMath::Max(1, MyGameState->GetTeamState(0).NumPlayers + MyGameState->GetTeamState(1).NumPlayers) : 1;
	SwarmPlayerCount = NumPlayers;

	// Waves are per path segment with no player factor: more players share one wave, so it grows with them (B5.4)
	const float CountFactor = FMath::Min(Settings->SwarmPlayerCountBase + Settings->SwarmPlayerCountPerPlayer * NumPlayers, Settings->SwarmPlayerCountMax);

	FMechSentinelDifficultyScale Scale;
	Scale.Count = Preset.Count * CountFactor;
	Scale.Health = Preset.Health;
	Scale.Armor = Preset.Armor;
	Scale.Damage = Preset.Damage;
	Scale.AttackSpeed = Preset.AttackSpeed;
	Scale.MoveSpeed = Preset.MoveSpeed;
	Scale.SelfBuffChance = Preset.SelfBuffChance;
	Scale.MaxAlive = Preset.MaxAlive;

	int32 NumSpawners = 0;

	for (TActorIterator<AMechSentinelWaveSpawner> It(GetWorld()); It; ++It)
	{
		if (IsValid(*It))
		{
			It->SetDifficultyScale(Scale);
			++NumSpawners;
		}
	}

	// Only MaxAttackersPerPlayer from the preset: SelfBuffChance is scaled once, on the wave (B5.4)
	if (UMechSentinelSwarmSubsystem* Swarm = UMechSentinelSwarmSubsystem::Get(this))
	{
		if (Preset.MaxAttackersPerPlayer > 0)
		{
			const UMechSentinelSwarmRules* BaseRules = SentinelSwarmRules ? SentinelSwarmRules.Get() : GetDefault<UMechSentinelSwarmRules>();
			SwarmRulesCopy = DuplicateObject<UMechSentinelSwarmRules>(BaseRules, this);
			SwarmRulesCopy->MaxAttackersPerPlayer = Preset.MaxAttackersPerPlayer;
			Swarm->SetRulesOverride(SwarmRulesCopy);
		}
		else if (SwarmRulesCopy)
		{
			Swarm->SetRulesOverride(nullptr);
			SwarmRulesCopy = nullptr;
		}
	}

	if (UBurrowerSpawnSubsystem* Burrowers = UBurrowerSpawnSubsystem::Get(this))
	{
		Burrowers->SetDifficultyOverride(Preset.BurrowerSpawnIntervalScale, Preset.BurrowerMaxAlivePerPlayer, Preset.BurrowerLevel);
	}

	UE_LOG(LogMatch, Log, TEXT("Swarm difficulty %d (%s) for %d player(s): count x%.2f (preset %.2f x players %.2f), health x%.2f, damage x%.2f, max alive x%.2f, attackers/player %s, Burrower interval x%.2f level %d, %d wave spawner(s)"),
		MatchRules.SwarmDifficulty, *Preset.Name.ToString(), NumPlayers, Scale.Count, Preset.Count, CountFactor, Scale.Health, Scale.Damage, Scale.MaxAlive,
		Preset.MaxAttackersPerPlayer > 0 ? *FString::FromInt(Preset.MaxAttackersPerPlayer) : TEXT("asset"), Preset.BurrowerSpawnIntervalScale,
		Preset.BurrowerLevel, NumSpawners);
}

void AMyGameMode::StopSwarm()
{
	for (TActorIterator<AMechSentinelWaveSpawner> It(GetWorld()); It; ++It)
	{
		if (IsValid(*It))
		{
			It->StopWaves();
		}
	}

	if (UBurrowerSpawnSubsystem* Burrowers = UBurrowerSpawnSubsystem::Get(this))
	{
		Burrowers->SetSpawningPaused(true);
	}
}

// -----------------------------------------------------------------------------
// Team ships (B3)
// -----------------------------------------------------------------------------

void AMyGameMode::RemoveUntaggedPlacedShips()
{
	if (!UMyMatchSettings::Get()->bDestroyUntaggedPlacedShipsInVersus)
	{
		return;
	}

	for (const TWeakObjectPtr<AAirshipPawn>& WeakShip : PlacedShips)
	{
		AAirshipPawn* Ship = WeakShip.Get();

		if (!IsValid(Ship) || Ship->GetTeamId() != MyMatch::NoTeam || WatchedShips.Contains(Ship))
		{
			continue;
		}

		bool bTagged = false;

		for (int32 Team = 0; Team < MyMatch::NumTeams; ++Team)
		{
			bTagged |= Ship->ActorHasTag(FName(*FString::Printf(TEXT("ShipTeam%d"), Team)));
		}

		if (!bTagged)
		{
			// A free ship in a versus match is a third ship anyone could take: tag it ShipTeam<id> to keep it
			UE_LOG(LogMatch, Log, TEXT("Team ships: %s (placed in the map, no ShipTeam<id> tag) removed for the versus match"), *Ship->GetName());

			if (Ship->HasPilot())
			{
				Ship->UnboardPilot(false);
			}

			Ship->Destroy();
		}
	}
}

void AMyGameMode::ClaimOrSpawnShips(bool bTwoTeams, bool bRemoveUntaggedPlaced)
{
	AMyGameState* MyGameState = GetMatchGameState();
	const UMyMatchSettings* Settings = UMyMatchSettings::Get();

	// Placed ships tagged ShipTeam<id>: that team's ship where it is (not teleported: the lane captures it once it is
	// parked in its zone, or the recall flies it home)
	for (const TWeakObjectPtr<AAirshipPawn>& WeakShip : PlacedShips)
	{
		AAirshipPawn* Ship = WeakShip.Get();

		if (!IsValid(Ship) || Ship->IsAirshipDead() || WatchedShips.Contains(Ship))
		{
			continue;
		}

		for (uint8 Team = 0; Team < MyMatch::NumTeams; ++Team)
		{
			const FMyTeamState& State = MyGameState->GetTeamState(Team);

			if (State.bActive && !IsValid(State.Ship) && Ship->ActorHasTag(FName(*FString::Printf(TEXT("ShipTeam%d"), Team))))
			{
				Ship->SetTeamId(Team);
				AdoptTeamShip(Ship, Team);
				ProtectShip(Ship);
				UE_LOG(LogMatch, Log, TEXT("Team ships: %s claims %s (placed, ShipTeam%d)"), *MyGameModeMatch::TeamLabel(Team), *Ship->GetName(), Team);
				break;
			}
		}
	}

	if (bTwoTeams && bRemoveUntaggedPlaced)
	{
		RemoveUntaggedPlacedShips();
	}

	for (uint8 Team = 0; Team < MyMatch::NumTeams; ++Team)
	{
		const FMyTeamState& State = MyGameState->GetTeamState(Team);

		if (State.bActive)
		{
			if (!IsValid(State.Ship) || State.Ship->IsAirshipDead())
			{
				SpawnTeamShip(Team, Settings->LaneSpawnU);
			}
			else
			{
				ProtectShip(State.Ship);
			}
		}
		else if (IsValid(State.Ship))
		{
			RemoveTeamShip(Team, TEXT("team inactive"));
		}
	}
}

AAirshipPawn* AMyGameMode::SpawnTeamShip(uint8 TeamId, float U)
{
	UWorld* World = GetWorld();

	if (!bMatchOn || !World || TeamId >= MyMatch::NumTeams || GetNetMode() == NM_Client || !GetMatchGameState())
	{
		return nullptr;
	}

	// Where: the team's lane at U; else an actor tagged ShipStart<id>; else in front of the team's PlayerStart, the
	// Aura.Airship.Spawn rule (B3.1)
	FTransform SpawnTransform;
	bool bHasTransform = false;
	const TCHAR* Source = TEXT("lane");

	if (const UMyLaneSubsystem* Lanes = UMyLaneSubsystem::Get(this); Lanes && Lanes->HasLanes())
	{
		bHasTransform = Lanes->GetSpawnTransform(TeamId, U, SpawnTransform);
	}

	if (!bHasTransform)
	{
		const FName StartTag(*FString::Printf(TEXT("ShipStart%d"), TeamId));
		Source = TEXT("ShipStart tag");

		for (TActorIterator<AActor> It(World); It && !bHasTransform; ++It)
		{
			if (It->ActorHasTag(StartTag))
			{
				SpawnTransform = FTransform(FRotator(0.0, It->GetActorRotation().Yaw, 0.0), It->GetActorLocation());
				bHasTransform = true;
			}
		}
	}

	const UAirshipSettings* AirshipSettings = UAirshipSettings::Get();

	if (!bHasTransform)
	{
		const FName TeamTag(*FString::Printf(TEXT("Team%d"), TeamId));
		APlayerStart* Start = nullptr;
		Source = TEXT("PlayerStart");

		for (TActorIterator<APlayerStart> It(World); It; ++It)
		{
			if (!Start || It->PlayerStartTag == TeamTag)
			{
				Start = *It;
			}
		}

		if (Start)
		{
			const FRotator Yaw(0.0, Start->GetActorRotation().Yaw, 0.0);
			SpawnTransform = FTransform(Yaw, Start->GetActorLocation() + Yaw.Vector() * AirshipSettings->SpawnDistance + FVector(0.0, 0.0, AirshipSettings->SpawnHeight));
			bHasTransform = true;
		}
	}

	if (!bHasTransform)
	{
		UE_LOG(LogMatch, Warning, TEXT("Team ships: nowhere to spawn the %s ship (no lane, no ShipStart%d actor, no PlayerStart)"), *MyGameModeMatch::TeamLabel(TeamId), TeamId);
		return nullptr;
	}

	UClass* Class = AirshipSettings->AirshipClass.IsNull() ? nullptr : AirshipSettings->AirshipClass.LoadSynchronous();

	if (!Class)
	{
		UE_LOG(LogMatch, Warning, TEXT("AirshipClass (Project Settings > Game > Airship) not found: spawning a plain AAirshipPawn (hull only)"));
		Class = AAirshipPawn::StaticClass();
	}

	// The team before BeginPlay: the turrets and the lane component read it there
	AAirshipPawn* Ship = World->SpawnActorDeferred<AAirshipPawn>(Class, SpawnTransform, nullptr, nullptr,
		ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn);

	if (!Ship)
	{
		UE_LOG(LogMatch, Warning, TEXT("Team ships: spawning the %s ship failed"), *MyGameModeMatch::TeamLabel(TeamId));
		return nullptr;
	}

	Ship->SetTeamId(TeamId);
	Ship->FinishSpawning(SpawnTransform);

	if (!IsValid(Ship))
	{
		return nullptr;
	}

	AdoptTeamShip(Ship, TeamId);
	ProtectShip(Ship);

	UE_LOG(LogMatch, Log, TEXT("Team ships: %s ship %s spawned at u %.0f m (%s) at %s"), *MyGameModeMatch::TeamLabel(TeamId), *Ship->GetName(), U / 100.f, Source,
		*Ship->GetActorLocation().ToCompactString());
	return Ship;
}

void AMyGameMode::AdoptTeamShip(AAirshipPawn* Ship, uint8 TeamId)
{
	AMyGameState* MyGameState = GetMatchGameState();
	FMyTeamState& State = MyGameState->EditTeam(TeamId);
	AAirshipPawn* OldShip = State.Ship;

	// A replacement (the lane's recall): the old one's destruction must not count
	if (IsValid(OldShip) && OldShip != Ship)
	{
		UE_LOG(LogMatch, Log, TEXT("Team ships: %s replaces %s for %s"), *Ship->GetName(), *OldShip->GetName(), *MyGameModeMatch::TeamLabel(TeamId));
		UnwatchShip(OldShip);
	}

	WatchShip(Ship, TeamId);
	State.Ship = Ship;
	State.ShipRespawnServerTime = 0.0;
	State.ShipHealthPct = static_cast<uint8>(FMath::Clamp(FMath::RoundToInt(100.f * GetShipHealthFraction(Ship)), 1, 100));
	LastShipDamageTime[TeamId] = 0.0;
	MyGameState->MarkTeamsDirty();
}

void AMyGameMode::WatchShip(AAirshipPawn* Ship, uint8 TeamId)
{
	FWatchedShip& Entry = WatchedShips.FindOrAdd(Ship);
	Entry.TeamId = TeamId;

	Ship->GetOnDeathDelegate().AddUniqueDynamic(this, &ThisClass::OnTeamShipDied);
	Ship->OnDestroyed.AddUniqueDynamic(this, &ThisClass::OnTeamShipDestroyed);

	if (!Entry.HealthHandle.IsValid())
	{
		if (UAbilitySystemComponent* ASC = Ship->GetAbilitySystemComponent())
		{
			Entry.ASC = ASC;
			Entry.HealthHandle = ASC->GetGameplayAttributeValueChangeDelegate(UMyAttributeSet::GetHealthAttribute())
				.AddUObject(this, &ThisClass::OnTeamShipHealthChanged, TWeakObjectPtr<AAirshipPawn>(Ship));
		}
	}
}

void AMyGameMode::UnwatchShip(AAirshipPawn* Ship)
{
	FWatchedShip Entry;

	if (!WatchedShips.RemoveAndCopyValue(Ship, Entry))
	{
		return;
	}

	if (IsValid(Ship))
	{
		Ship->GetOnDeathDelegate().RemoveDynamic(this, &ThisClass::OnTeamShipDied);
		Ship->OnDestroyed.RemoveDynamic(this, &ThisClass::OnTeamShipDestroyed);
	}

	if (UAbilitySystemComponent* ASC = Entry.ASC.Get())
	{
		ASC->GetGameplayAttributeValueChangeDelegate(UMyAttributeSet::GetHealthAttribute()).Remove(Entry.HealthHandle);
	}
}

void AMyGameMode::RemoveTeamShip(uint8 TeamId, const TCHAR* Reason)
{
	AMyGameState* MyGameState = GetMatchGameState();

	if (!MyGameState || TeamId >= MyMatch::NumTeams)
	{
		return;
	}

	FMyTeamState& State = MyGameState->EditTeam(TeamId);
	AAirshipPawn* Ship = State.Ship;
	State.Ship = nullptr;
	State.ShipRespawnServerTime = 0.0;
	State.ShipHealthPct = 0;
	MyGameState->MarkTeamsDirty();

	if (!IsValid(Ship))
	{
		return;
	}

	// No life counted: the game mode takes it away, nobody sank it
	UnwatchShip(Ship);

	if (PlacedShips.Contains(Ship))
	{
		// A claimed map ship goes back to being free, it isn't ours to delete
		Ship->SetTeamId(MyMatch::NoTeam);
		UE_LOG(LogMatch, Log, TEXT("Team ships: %s released by %s (%s)"), *Ship->GetName(), *MyGameModeMatch::TeamLabel(TeamId), Reason);
		return;
	}

	// The ship's EndPlay would take its pilot's character with it: put him and the gunners back on foot first
	if (Ship->HasPilot())
	{
		Ship->UnboardPilot(false);
	}

	for (int32 Station = 0; Station < Airship::NumStations; ++Station)
	{
		if (Ship->IsStationManned(Station))
		{
			Ship->DismountGunner(Station, false);
		}
	}

	UE_LOG(LogMatch, Log, TEXT("Team ships: %s ship %s removed (%s), no life lost"), *MyGameModeMatch::TeamLabel(TeamId), *Ship->GetName(), Reason);
	Ship->Destroy();
}

void AMyGameMode::ProtectShip(AAirshipPawn* Ship) const
{
	const float Protection = UMyMatchSettings::Get()->ShipSpawnProtection;

	if (!IsValid(Ship) || Protection <= 0.f)
	{
		return;
	}

	// Spawned for a countdown: its 15 s count from the start (re-armed then), so the countdown is added
	float Seconds = Protection;
	const EMyMatchPhase Phase = GetPhase();
	const AMyGameState* MyGameState = GetMatchGameState();

	if (Phase == EMyMatchPhase::Countdown && MyGameState)
	{
		Seconds += static_cast<float>(FMath::Max(0.0, MyGameState->GetPhaseEndServerTime() - GetServerTime()));
	}
	else if (Phase == EMyMatchPhase::WaitingToStart || Phase == EMyMatchPhase::None)
	{
		Seconds += UMyMatchSettings::Get()->MatchStartDelay;
	}

	Ship->SetSpawnProtected(Seconds);
}

void AMyGameMode::HealShip(AAirshipPawn* Ship) const
{
	UAbilitySystemComponent* ASC = IsValid(Ship) ? Ship->GetAbilitySystemComponent() : nullptr;

	if (ASC)
	{
		ASC->SetNumericAttributeBase(UMyAttributeSet::GetHealthAttribute(), ASC->GetNumericAttribute(UMyAttributeSet::GetMaxHealthAttribute()));
	}
}

float AMyGameMode::GetShipHealthFraction(const AAirshipPawn* Ship) const
{
	const UAbilitySystemComponent* ASC = IsValid(Ship) && !Ship->IsAirshipDead() ? Ship->GetAbilitySystemComponent() : nullptr;

	if (!ASC)
	{
		return 0.f;
	}

	const float MaxHealth = ASC->GetNumericAttribute(UMyAttributeSet::GetMaxHealthAttribute());
	return MaxHealth > 0.f ? FMath::Clamp(ASC->GetNumericAttribute(UMyAttributeSet::GetHealthAttribute()) / MaxHealth, 0.f, 1.f) : 0.f;
}

float AMyGameMode::GetShipRespawnU(uint8 TeamId) const
{
	const UMyLaneSubsystem* Lanes = UMyLaneSubsystem::Get(this);
	const AMyGameState* MyGameState = GetMatchGameState();

	if (!Lanes || !Lanes->HasLanes() || TeamId >= MyMatch::NumTeams || !MyGameState)
	{
		return TeamId < MyMatch::NumTeams ? LastShipU[TeamId] : 0.f;
	}

	// The team front, else the match front (any on-foot player), else where the last ship went down (B3.1)
	float Front = 0.f;

	if (!Lanes->GetTeamFrontU(TeamId, Front) && !Lanes->GetTeamFrontU(MyMatch::NoTeam, Front))
	{
		Front = LastShipU[TeamId];
	}

	const float StartU = Lanes->GetLaneStartU();
	const float U = FMath::Clamp(Front, StartU, FMath::Max(StartU, Lanes->GetCruiseEndU()));

	// Away from the enemy ship: back along the lane in 50 m steps until it is out of cannon and turret range; if no such
	// point exists the spawn protection covers it
	const AAirshipPawn* Enemy = MyGameState->GetTeamState(1 - TeamId).Ship;
	const float MinDistance = UMyMatchSettings::Get()->ShipSpawnMinEnemyDistance;

	if (IsValid(Enemy) && !Enemy->IsAirshipDead() && MinDistance > 0.f)
	{
		const int8 Side = GetSideForTeam(TeamId);

		for (float Try = U; Try >= StartU - 1.f; Try -= 5000.f)
		{
			FVector Point;
			FVector Tangent;

			if (Lanes->GetLanePoint(Side, Try, Point, Tangent) && FVector::DistSquared(Point, Enemy->GetActorLocation()) >= FMath::Square(MinDistance))
			{
				return Try;
			}
		}
	}

	return U;
}

bool AMyGameMode::FindAboardTransform(const AController* Controller, const AAirshipPawn* Ship, int32 SpotIndex, FTransform& OutTransform) const
{
	if (!IsValid(Ship) || Ship->IsAirshipDead())
	{
		return false;
	}

	TArray<FTransform> Spots;
	Ship->GetDeckSpawnTransforms(FMath::Max(4, SpotIndex + 1), Spots);

	if (Spots.IsEmpty())
	{
		return false;
	}

	if (SpotIndex >= 0)
	{
		OutTransform = MyGameModeMatch::YawOnly(Spots[SpotIndex % Spots.Num()]);
		return true;
	}

	// The first spot no player stands on
	const APawn* OwnPawn = Controller ? Controller->GetPawn() : nullptr;

	for (const FTransform& Spot : Spots)
	{
		bool bTaken = false;

		for (FConstPlayerControllerIterator It = GetWorld()->GetPlayerControllerIterator(); It && !bTaken; ++It)
		{
			const APawn* Pawn = It->Get() ? It->Get()->GetPawn() : nullptr;
			bTaken = Pawn && Pawn != OwnPawn && FVector::DistSquared(Pawn->GetActorLocation(), Spot.GetLocation()) < FMath::Square(150.0);
		}

		if (!bTaken)
		{
			OutTransform = MyGameModeMatch::YawOnly(Spot);
			return true;
		}
	}

	OutTransform = MyGameModeMatch::YawOnly(Spots[0]);
	return true;
}

void AMyGameMode::OnTeamShipDied(AActor* DeadActor)
{
	AAirshipPawn* Ship = Cast<AAirshipPawn>(DeadActor);
	const FWatchedShip* Entry = Ship ? WatchedShips.Find(Ship) : nullptr;
	AMyGameState* MyGameState = GetMatchGameState();

	if (!Entry || !MyGameState)
	{
		return;
	}

	const uint8 TeamId = Entry->TeamId;
	FMyTeamState& State = MyGameState->EditTeam(TeamId);

	// Only the team's current ship counts (a replaced one is unwatched already)
	if (State.Ship != Ship)
	{
		return;
	}

	// The wreck stays watched until it is destroyed (its life span), so its OnDestroyed unbinds everything
	State.Ship = nullptr;
	State.ShipHealthPct = 0;

	if (const UMyLaneSubsystem* Lanes = UMyLaneSubsystem::Get(this); Lanes && Lanes->HasLanes())
	{
		LastShipU[TeamId] = Lanes->ProjectU(Ship->GetActorLocation());
	}

	const UMyMatchSettings* Settings = UMyMatchSettings::Get();
	const EMyMatchPhase Phase = GetPhase();
	const double Now = GetServerTime();

	if (Phase == EMyMatchPhase::InProgress && State.bActive)
	{
		// Solo practice: a learner shouldn't be sent back to a reload after three crashes (B3.2)
		const bool bUnlimited = !bVersusRound && Settings->bSoloPracticeUnlimitedShips && State.NumPlayers <= 1;
		++State.ShipsLost;

		if (!bUnlimited)
		{
			State.LivesLeft = FMath::Max(0, State.LivesLeft - 1);
		}

		const bool bEliminated = !bUnlimited && State.LivesLeft <= 0;

		if (bEliminated)
		{
			State.bEliminated = true;
		}
		else
		{
			State.ShipRespawnServerTime = Now + FMath::Max(0.f, Settings->ShipRespawnDelay);
		}

		MyGameState->MarkTeamsDirty();
		MyGameState->MulticastMatchEvent(EMyMatchEvent::ShipDestroyed, TeamId, bUnlimited ? -1 : State.LivesLeft);

		UE_LOG(LogMatch, Log, TEXT("Team ships: %s ship %s destroyed, %d lost, %s"), *MyGameModeMatch::TeamLabel(TeamId), *Ship->GetName(),
			State.ShipsLost, bUnlimited ? TEXT("unlimited (solo practice)") : *FString::Printf(TEXT("%d lives left"), State.LivesLeft));

		if (bEliminated)
		{
			MyGameState->MulticastMatchEvent(EMyMatchEvent::TeamEliminated, TeamId, 0);
			UE_LOG(LogMatch, Log, TEXT("Team ships: %s has no ships left"), *MyGameModeMatch::TeamLabel(TeamId));

			// Next tick: both teams losing their last ship in the same frame is a draw
			ScheduleEndCheck();
		}
		return;
	}

	// Before the start nothing counts: a new ship after the delay
	if ((Phase == EMyMatchPhase::Countdown || Phase == EMyMatchPhase::WaitingToStart) && State.bActive)
	{
		State.ShipRespawnServerTime = Now + FMath::Max(0.f, Settings->ShipRespawnDelay);
	}

	MyGameState->MarkTeamsDirty();
	UE_LOG(LogMatch, Log, TEXT("Team ships: %s ship %s destroyed in phase %s, no life lost"), *MyGameModeMatch::TeamLabel(TeamId), *Ship->GetName(),
		MyGameModeMatch::PhaseName(Phase));
}

void AMyGameMode::OnTeamShipDestroyed(AActor* DestroyedActor)
{
	AAirshipPawn* Ship = Cast<AAirshipPawn>(DestroyedActor);
	const FWatchedShip* Entry = Ship ? WatchedShips.Find(Ship) : nullptr;

	if (!Entry)
	{
		return;
	}

	const uint8 TeamId = Entry->TeamId;
	const bool bRecall = Ship->GetLane() && Ship->GetLane()->IsRecallReplacing();
	UnwatchShip(Ship);

	AMyGameState* MyGameState = GetMatchGameState();

	if (!MyGameState || GetWorld()->bIsTearingDown || bRestarting)
	{
		return;
	}

	FMyTeamState& State = MyGameState->EditTeam(TeamId);

	// A wreck (its death was counted) or a ship already replaced
	if (State.Ship != Ship)
	{
		return;
	}

	// Destroyed without a death (console, a recall replacement, a disconnect before PawnLeavingGame's fix): no life lost,
	// a replacement after the delay, at once for a recall (B3.2)
	State.Ship = nullptr;
	State.ShipHealthPct = 0;

	if (const UMyLaneSubsystem* Lanes = UMyLaneSubsystem::Get(this); Lanes && Lanes->HasLanes())
	{
		LastShipU[TeamId] = Lanes->ProjectU(Ship->GetActorLocation());
	}

	const EMyMatchPhase Phase = GetPhase();

	if (State.bActive && (Phase == EMyMatchPhase::InProgress || Phase == EMyMatchPhase::Countdown || Phase == EMyMatchPhase::WaitingToStart))
	{
		State.ShipRespawnServerTime = GetServerTime() + (bRecall ? 0.0 : FMath::Max(0.f, UMyMatchSettings::Get()->ShipRespawnDelay));
	}

	MyGameState->MarkTeamsDirty();
	UE_LOG(LogMatch, Log, TEXT("Team ships: %s ship %s destroyed without a death (%s), no life lost"), *MyGameModeMatch::TeamLabel(TeamId), *Ship->GetName(),
		bRecall ? TEXT("recall replacement") : TEXT("removed"));
}

void AMyGameMode::OnTeamShipHealthChanged(const FOnAttributeChangeData& Data, TWeakObjectPtr<AAirshipPawn> WeakShip)
{
	AAirshipPawn* Ship = WeakShip.Get();
	const FWatchedShip* Entry = Ship ? WatchedShips.Find(Ship) : nullptr;
	AMyGameState* MyGameState = GetMatchGameState();

	if (!Entry || !MyGameState || Data.NewValue >= Data.OldValue)
	{
		return;
	}

	const uint8 TeamId = Entry->TeamId;
	const double Now = GetServerTime();
	LastShipDamageTime[TeamId] = Now;

	// A shot, not a crash: hull impacts go through the ship's own ASC (instigator = the ship), console sets have no
	// effect at all (B8.3)
	const AActor* Instigator = Data.GEModData ? Data.GEModData->EffectSpec.GetEffectContext().GetInstigator() : nullptr;

	if (!Instigator || Instigator == Ship || GetPhase() != EMyMatchPhase::InProgress)
	{
		return;
	}

	FMyTeamState& State = MyGameState->EditTeam(TeamId);

	if (State.Ship != Ship || Now - State.LastUnderAttackServerTime < UMyMatchSettings::Get()->ShipUnderAttackInterval)
	{
		return;
	}

	State.LastUnderAttackServerTime = Now;
	const int32 Percent = FMath::RoundToInt(100.f * GetShipHealthFraction(Ship));
	MyGameState->MulticastMatchEvent(EMyMatchEvent::ShipUnderAttack, TeamId, Percent);
	UE_LOG(LogMatch, Log, TEXT("Team ships: %s ship under attack by %s (%d %%)"), *MyGameModeMatch::TeamLabel(TeamId), *GetNameSafe(Instigator), Percent);
}

// -----------------------------------------------------------------------------
// Match tick (B4.3): every 0.5 s on the server
// -----------------------------------------------------------------------------

void AMyGameMode::MatchTick()
{
	AMyGameState* MyGameState = GetMatchGameState();

	if (!bMatchOn || !MyGameState || bRestarting)
	{
		return;
	}

	const EMyMatchPhase Phase = GetPhase();

	if (Phase == EMyMatchPhase::InProgress || Phase == EMyMatchPhase::Countdown)
	{
		UpdateShipRespawns();
	}

	if (Phase == EMyMatchPhase::InProgress)
	{
		UpdateForfeits();
	}

	// The time limit (versus only): the tie-break decides at once (B4.4)
	const double MatchEnd = MyGameState->GetMatchEndServerTime();

	if (GetPhase() == EMyMatchPhase::InProgress && bVersusRound && MatchEnd > 0.0)
	{
		const double Remaining = MatchEnd - GetServerTime();

		if (!bTimeWarningSent && Remaining <= 60.0)
		{
			bTimeWarningSent = true;
			MyGameState->MulticastMatchEvent(EMyMatchEvent::TimeWarning, MyMatch::NoTeam, FMath::CeilToInt(FMath::Max(0.0, Remaining)));
			UE_LOG(LogMatch, Log, TEXT("Match: %.0f s left"), FMath::Max(0.0, Remaining));
		}

		if (Remaining <= 0.0)
		{
			ResolveTimeLimit();
		}
	}

	// Not in the lobby or its countdown (phase Countdown): the lobby zone and its fall catch bring players back instead
	if (GetPhase() != EMyMatchPhase::None && GetPhase() != EMyMatchPhase::WaitingToStart && GetPhase() != EMyMatchPhase::Lobby && !IsInLobby())
	{
		UpdateFallDeaths();
	}
}

void AMyGameMode::HealthTick()
{
	AMyGameState* MyGameState = GetMatchGameState();

	if (!bMatchOn || !MyGameState)
	{
		return;
	}

	// Both hulls on everyone's match bar, at most 4 times a second (B8.1)
	bool bChanged = false;

	for (uint8 Team = 0; Team < MyMatch::NumTeams; ++Team)
	{
		const AAirshipPawn* Ship = MyGameState->GetTeamState(Team).Ship;
		const bool bAlive = IsValid(Ship) && !Ship->IsAirshipDead();
		const float Fraction = bAlive ? GetShipHealthFraction(Ship) : 0.f;
		// A living ship never shows an empty bar
		const uint8 Percent = bAlive ? static_cast<uint8>(FMath::Clamp(FMath::RoundToInt(100.f * Fraction), Fraction > 0.f ? 1 : 0, 100)) : 0;

		if (MyGameState->GetTeamState(Team).ShipHealthPct != Percent)
		{
			MyGameState->EditTeam(Team).ShipHealthPct = Percent;
			bChanged = true;
		}
	}

	if (bChanged)
	{
		MyGameState->MarkTeamsDirty();
	}
}

void AMyGameMode::UpdateShipRespawns()
{
	AMyGameState* MyGameState = GetMatchGameState();
	const double Now = GetServerTime();

	for (uint8 Team = 0; Team < MyMatch::NumTeams; ++Team)
	{
		const FMyTeamState& State = MyGameState->GetTeamState(Team);

		if (!State.bActive || IsValid(State.Ship) || State.ShipRespawnServerTime <= 0.0 || Now < State.ShipRespawnServerTime)
		{
			continue;
		}

		if (SpawnTeamShip(Team, GetShipRespawnU(Team)))
		{
			MyGameState->MulticastMatchEvent(EMyMatchEvent::ShipRespawned, Team, MyGameState->GetTeamState(Team).LivesLeft);
		}
		else
		{
			// Try again in a second (nowhere to spawn right now)
			MyGameState->EditTeam(Team).ShipRespawnServerTime = Now + 1.0;
			MyGameState->MarkTeamsDirty();
		}
	}
}

void AMyGameMode::UpdateForfeits()
{
	AMyGameState* MyGameState = GetMatchGameState();
	const UMyMatchSettings* Settings = UMyMatchSettings::Get();

	if (!bVersusRound || GetPhase() != EMyMatchPhase::InProgress)
	{
		return;
	}

	const double Now = GetServerTime();
	bool bChanged = false;

	for (uint8 Team = 0; Team < MyMatch::NumTeams; ++Team)
	{
		FMyTeamState& State = MyGameState->EditTeam(Team);
		const uint8 Other = 1 - Team;

		if (!State.bActive)
		{
			continue;
		}

		// A team nobody plays any more keeps its ship and lives for a while; a new join goes to it (the smaller team)
		if (State.NumPlayers == 0 && MyGameState->GetTeamState(Other).NumPlayers > 0)
		{
			if (State.EmptySinceServerTime <= 0.0)
			{
				State.EmptySinceServerTime = Now;
				bChanged = true;

				if (Settings->TeamEmptyForfeitSeconds > 0.f)
				{
					MyGameState->MulticastMatchEvent(EMyMatchEvent::ForfeitWarning, Team, FMath::CeilToInt(Settings->TeamEmptyForfeitSeconds));
				}
				UE_LOG(LogMatch, Log, TEXT("Match: %s has no players%s"), *MyGameModeMatch::TeamLabel(Team),
					Settings->TeamEmptyForfeitSeconds > 0.f ? *FString::Printf(TEXT(", forfeits in %.0f s"), Settings->TeamEmptyForfeitSeconds) : TEXT(""));
			}
			else if (Settings->TeamEmptyForfeitSeconds > 0.f && Now - State.EmptySinceServerTime >= Settings->TeamEmptyForfeitSeconds)
			{
				MyGameState->MarkTeamsDirty();
				MyGameState->MulticastMatchEvent(EMyMatchEvent::Forfeited, Team, 0);
				EndMatch(EMyMatchResult::TeamWon, Other, EMyMatchEndReason::Forfeit);
				return;
			}
		}
		else if (State.EmptySinceServerTime > 0.0)
		{
			State.EmptySinceServerTime = 0.0;
			bChanged = true;
			UE_LOG(LogMatch, Log, TEXT("Match: %s has a player again, no forfeit"), *MyGameModeMatch::TeamLabel(Team));
		}
	}

	if (bChanged)
	{
		MyGameState->MarkTeamsDirty();
	}
}

void AMyGameMode::UpdateFallDeaths()
{
	const UMyMatchSettings* Settings = UMyMatchSettings::Get();
	const UMyLaneSubsystem* Lanes = UMyLaneSubsystem::Get(this);
	const AMyGameState* MyGameState = GetMatchGameState();

	if (Settings->FallDeathDepth <= 0.f || !Lanes || !Lanes->HasLanes() || !MyGameState)
	{
		FallingSince.Reset();
		return;
	}

	const double Now = GetServerTime();

	for (auto It = FallingSince.CreateIterator(); It; ++It)
	{
		if (!It.Key().IsValid())
		{
			It.RemoveCurrent();
		}
	}

	// Each player state's own pawn only: a seated pilot's pawn is his ship, and a dead pilot's death would reach
	// OnPlayerPawnDied with no controller (B9.6)
	for (const APlayerState* PlayerState : MyGameState->PlayerArray)
	{
		ACharacter* Character = PlayerState ? Cast<ACharacter>(PlayerState->GetPawn()) : nullptr;

		if (!IsValid(Character) || Character->IsActorBeingDestroyed())
		{
			continue;
		}

		// Aboard (attached as pilot or gunner, riding a deck) nobody dies of the fall: ships have no altitude floor over
		// the void
		const UCharacterMovementComponent* Movement = Character->GetCharacterMovement();
		const bool bFalling = Movement && Movement->MovementMode == MOVE_Falling && !Character->GetMovementBaseObject();

		if (!bFalling || MyGameModeMatch::IsDeadCharacter(Character) || UAirshipSubsystem::IsShipBorne(Character))
		{
			FallingSince.Remove(Character);
			continue;
		}

		const double* Since = FallingSince.Find(Character);

		if (!Since)
		{
			FallingSince.Add(Character, Now);
			continue;
		}

		if (Now - *Since < Settings->FallDeathMinFallTime)
		{
			continue;
		}

		// Below the lane (= path height + LaneHeight) at its own progress: lower than every platform of both chains
		const FVector Location = Character->GetActorLocation();
		FVector LanePoint;
		FVector LaneTangent;

		if (!Lanes->GetLanePoint(1, Lanes->ProjectU(Location), LanePoint, LaneTangent) || Location.Z > LanePoint.Z - Settings->FallDeathDepth)
		{
			continue;
		}

		UE_LOG(LogMatch, Log, TEXT("Match: fall death of %s at z %.0f m (%.0f m below the lane), falling for %.1f s"), *PlayerState->GetPlayerName(),
			Location.Z / 100.0, (LanePoint.Z - Location.Z) / 100.0, Now - *Since);
		FallingSince.Remove(Character);

		if (IMyCombatInterface* Combat = Cast<IMyCombatInterface>(Character))
		{
			Combat->Die();
		}
	}
}

void AMyGameMode::ScheduleEndCheck()
{
	if (!bEndCheckPending)
	{
		bEndCheckPending = true;
		GetWorldTimerManager().SetTimerForNextTick(this, &ThisClass::CheckEnd);
	}
}

void AMyGameMode::CheckEnd()
{
	bEndCheckPending = false;
	const AMyGameState* MyGameState = GetMatchGameState();

	if (!MyGameState || GetPhase() != EMyMatchPhase::InProgress)
	{
		return;
	}

	const bool bOut0 = MyGameState->GetTeamState(0).bActive && MyGameState->GetTeamState(0).bEliminated;
	const bool bOut1 = MyGameState->GetTeamState(1).bActive && MyGameState->GetTeamState(1).bEliminated;

	if (bVersusRound)
	{
		if (bOut0 && bOut1)
		{
			EndMatch(EMyMatchResult::Draw, MyMatch::NoTeam, EMyMatchEndReason::Eliminated);
		}
		else if (bOut0 || bOut1)
		{
			EndMatch(EMyMatchResult::TeamWon, bOut0 ? 1 : 0, EMyMatchEndReason::Eliminated);
		}
	}
	else if (bOut0 || bOut1)
	{
		// Co-op practice lost its last ship
		EndMatch(EMyMatchResult::PracticeOver, MyMatch::NoTeam, EMyMatchEndReason::Eliminated);
	}
}

float AMyGameMode::GetTeamProgress(uint8 TeamId) const
{
	const UMyLaneSubsystem* Lanes = UMyLaneSubsystem::Get(this);
	const AMyGameState* MyGameState = GetMatchGameState();

	if (!Lanes || !MyGameState)
	{
		return -UE_BIG_NUMBER;
	}

	// The team front (on-foot players), else its players' last platforms (a team all aboard keeps its race)
	float Front = 0.f;

	if (Lanes->GetTeamFrontU(TeamId, Front))
	{
		return Front;
	}

	float Best = -UE_BIG_NUMBER;

	for (const APlayerState* PlayerState : MyGameState->PlayerArray)
	{
		const AMyPlayerState* MyPlayerState = Cast<AMyPlayerState>(PlayerState);
		const AMyHexPlatform* Platform = MyPlayerState && MyPlayerState->GetTeamId() == TeamId ? MyPlayerState->GetCurrentPlatform() : nullptr;

		// Only path platforms are race progress: the placed one above the start floor has no SplineDistance (SPEC_B_LOBBY 3.4)
		if (IsValid(Platform) && Platform->HasSplineDistance())
		{
			Best = FMath::Max(Best, Lanes->ProjectU(Platform->GetActorLocation()));
		}
	}

	return Best;
}

void AMyGameMode::ResolveTimeLimit()
{
	const AMyGameState* MyGameState = GetMatchGameState();
	const FMyTeamState& Team0 = MyGameState->GetTeamState(0);
	const FMyTeamState& Team1 = MyGameState->GetTeamState(1);
	uint8 Winner = MyMatch::NoTeam;
	FString By = TEXT("a draw");

	// More ship lives left (without the handicap's, unless bTimeLimitCountsHandicap), then more hull (a dead ship counts
	// 0), then further along the race (B4.4)
	const int32 Lives0 = UMyTeamLibrary::GetTimeLimitLives(Team0);
	const int32 Lives1 = UMyTeamLibrary::GetTimeLimitLives(Team1);

	if (Lives0 != Lives1)
	{
		Winner = Lives0 > Lives1 ? 0 : 1;
		By = FString::Printf(TEXT("ship lives %d / %d (left %d / %d, bonus %d / %d)"), Lives0, Lives1, Team0.LivesLeft, Team1.LivesLeft,
			Team0.BonusLives, Team1.BonusLives);
	}
	else
	{
		const float Hull0 = GetShipHealthFraction(Team0.Ship);
		const float Hull1 = GetShipHealthFraction(Team1.Ship);

		if (FMath::Abs(Hull0 - Hull1) > 0.001f)
		{
			Winner = Hull0 > Hull1 ? 0 : 1;
			By = FString::Printf(TEXT("hull %.0f %% / %.0f %%"), Hull0 * 100.f, Hull1 * 100.f);
		}
		else
		{
			const float Progress0 = GetTeamProgress(0);
			const float Progress1 = GetTeamProgress(1);

			if (FMath::Abs(Progress0 - Progress1) > 100.f)
			{
				Winner = Progress0 > Progress1 ? 0 : 1;
				By = FString::Printf(TEXT("race u %.0f / %.0f m"), Progress0 / 100.f, Progress1 / 100.f);
			}
		}
	}

	UE_LOG(LogMatch, Log, TEXT("Match: time up, tie-break by %s: %s"), *By, Winner != MyMatch::NoTeam ? *MyGameModeMatch::TeamLabel(Winner) : TEXT("draw"));
	EndMatch(Winner != MyMatch::NoTeam ? EMyMatchResult::TeamWon : EMyMatchResult::Draw, Winner, EMyMatchEndReason::TimeLimit);
}

// -----------------------------------------------------------------------------
// Player starts (B4.2 spawn fix, B9.7 late joiners)
// -----------------------------------------------------------------------------

AActor* AMyGameMode::ChoosePlayerStart_Implementation(AController* Player)
{
	if (!bMatchOn)
	{
		return Super::ChoosePlayerStart_Implementation(Player);
	}

	UWorld* World = GetWorld();
	UClass* PawnClass = GetDefaultPawnClassForController(Player);
	const APawn* PawnToFit = PawnClass ? PawnClass->GetDefaultObject<APawn>() : nullptr;
	const uint8 Team = GetControllerTeam(Player);
	const FName TeamTag = Team < MyMatch::NumTeams ? FName(*FString::Printf(TEXT("Team%d"), Team)) : NAME_None;

	TArray<APlayerStart*> TeamFree;
	TArray<APlayerStart*> Free;
	TArray<APlayerStart*> TeamAny;
	TArray<APlayerStart*> Any;
	TArray<APlayerStart*> LobbyFree;
	TArray<APlayerStart*> LobbyAny;

	// The lobby stands on its own starts (Lobby-tagged ones first, those with ground under them: ResolveLobbySpawn); the
	// match skips Lobby-tagged starts unless there is nothing else (SPEC_B_LOBBY 4.7)
	// (also in phase None of a lobby round: the host's login picks his StartSpot before StartPlay, and the engine reuses it)
	const bool bLobbyStarts = (IsInLobby() || (bLobbyRound && GetPhase() == EMyMatchPhase::None)) && LobbyGround == EMyLobbyGround::PlayerStarts;
	static const FName LobbyTag(TEXT("Lobby"));

	for (TActorIterator<APlayerStart> It(World); It; ++It)
	{
		APlayerStart* Start = *It;

		// "Play from Here" in PIE always wins, as in the engine
		if (Start->IsA<APlayerStartPIE>())
		{
			return Start;
		}

		const bool bFreeStart = !PawnToFit || !World->EncroachingBlockingGeometry(PawnToFit, Start->GetActorLocation(), Start->GetActorRotation());

		if (bLobbyStarts ? LobbyStarts.Contains(Start) : Start->PlayerStartTag == LobbyTag)
		{
			if (bFreeStart)
			{
				LobbyFree.Add(Start);
			}
			LobbyAny.Add(Start);
			continue;
		}

		const bool bTeam = !TeamTag.IsNone() && Start->PlayerStartTag == TeamTag;

		(bTeam ? TeamAny : Any).Add(Start);

		if (bFreeStart)
		{
			(bTeam ? TeamFree : Free).Add(Start);
		}
	}

	// The team's free starts, then any free one, then any (the team's first): never none, so the engine's "NO
	// PLAYERSTART with positive rating" path doesn't leave a second player without a pawn (flag 7); RestartPlayer
	// rings an occupied start. The lobby: its own starts first; the match: Lobby-tagged ones last
	const TArray<const TArray<APlayerStart*>*> Order = bLobbyStarts
		? TArray<const TArray<APlayerStart*>*>{ &LobbyFree, &LobbyAny, &TeamFree, &Free, &TeamAny, &Any }
		: TArray<const TArray<APlayerStart*>*>{ &TeamFree, &Free, &TeamAny, &Any, &LobbyFree, &LobbyAny };

	for (const TArray<APlayerStart*>* Starts : Order)
	{
		if (Starts->Num() > 0)
		{
			return (*Starts)[FMath::RandRange(0, Starts->Num() - 1)];
		}
	}

	return nullptr;
}

void AMyGameMode::RestartPlayer(AController* NewPlayer)
{
	if (!bMatchOn || !NewPlayer || NewPlayer->IsPendingKillPending())
	{
		Super::RestartPlayer(NewPlayer);
		return;
	}

	// A player the engine starts while the match runs (a late joiner, B9.7): as a match-start player would, aboard his
	// ship in versus, else past the lead on his own side. Not for RespawnPlayer's last resort (respawns stay off decks)
	const EMyMatchPhase Phase = GetPhase();
	const AMyGameState* MyGameState = GetMatchGameState();

	// The lobby (SPEC_B_LOBBY 4.7): PathStart puts the pawn on a tile of its platform; PlayerStarts and the fallback take
	// the engine's start (ChoosePlayerStart prefers the lobby's) and the ring search below
	if (!NewPlayer->GetPawn() && !bRestartFromRespawn && Phase == EMyMatchPhase::Lobby && IsInLobby() && LobbyGround == EMyLobbyGround::PathStart)
	{
		FPawnFit Fit;
		FRespawnSpot Spot;

		if (GetPawnFit(NewPlayer, Fit) && GetLobbySpot(NewPlayer, Fit, Spot))
		{
			RestartPlayerAtTransform(NewPlayer, Spot.PawnTransform);

			if (NewPlayer->GetPawn())
			{
				UE_LOG(LogMatch, Log, TEXT("Lobby: %s spawns on %s"), *GetNameSafe(NewPlayer->PlayerState), *GetNameSafe(LobbyPlatform.Get()));
				return;
			}
		}
	}

	if (!NewPlayer->GetPawn() && !bRestartFromRespawn && MyGameState && (Phase == EMyMatchPhase::InProgress || Phase == EMyMatchPhase::Ended))
	{
		const uint8 Team = GetControllerTeam(NewPlayer);
		const AAirshipPawn* Ship = Team < MyMatch::NumTeams ? MyGameState->GetTeamState(Team).Ship.Get() : nullptr;
		FTransform SpawnTransform;
		bool bHasSpot = false;
		const TCHAR* Where = TEXT("aboard");

		// Practice too (SPEC_B_LOBBY D10): aboard team 0's ship
		if (UMyMatchSettings::Get()->bStartAboard)
		{
			bHasSpot = FindAboardTransform(NewPlayer, Ship, INDEX_NONE, SpawnTransform);
		}

		// No landing needed: with nobody landed FindRespawnSpot gives the path's first platforms (SPEC_B_LOBBY 3.4)
		if (!bHasSpot)
		{
			FPawnFit Fit;
			FRespawnSpot Spot;

			if (GetPawnFit(NewPlayer, Fit) && FindRespawnSpot(NewPlayer, Fit, Spot) && (Spot.bOnTile || Spot.Ship.IsValid()))
			{
				SpawnTransform = Spot.PawnTransform;
				bHasSpot = true;
				Where = TEXT("past the lead");
			}
		}

		if (bHasSpot)
		{
			RestartPlayerAtTransform(NewPlayer, SpawnTransform);

			if (NewPlayer->GetPawn())
			{
				UE_LOG(LogMatch, Log, TEXT("Start: %s joins the running match %s"), *GetNameSafe(NewPlayer->PlayerState), Where);
				return;
			}
		}
	}

	Super::RestartPlayer(NewPlayer);

	if (NewPlayer->GetPawn() || NewPlayer->IsPendingKillPending())
	{
		return;
	}

	// The start is taken and the engine found no room next to it (it keeps an occupied start only if FindTeleportSpot
	// does): try around it
	AActor* Start = FindPlayerStart(NewPlayer);
	FPawnFit Fit;

	if (!Start || !GetPawnFit(NewPlayer, Fit))
	{
		UE_LOG(LogMatch, Warning, TEXT("Start: no PlayerStart or pawn class for %s"), *GetNameSafe(NewPlayer));
		return;
	}

	const FRotator Rotation(0.0, Start->GetActorRotation().Yaw, 0.0);

	for (const float Radius : { 250.f, 500.f, 750.f })
	{
		for (int32 Direction = 0; Direction < 8; ++Direction)
		{
			FVector Location = Start->GetActorLocation() + FRotator(0.0, Direction * 45.0, 0.0).Vector() * Radius;

			if (!GetWorld()->FindTeleportSpot(Fit.PawnToFit, Location, Rotation))
			{
				continue;
			}

			RestartPlayerAtTransform(NewPlayer, FTransform(Rotation, Location));

			if (NewPlayer->GetPawn())
			{
				UE_LOG(LogMatch, Log, TEXT("Start: %s placed %.0f cm from the occupied %s"), *GetNameSafe(NewPlayer->PlayerState), Radius, *Start->GetName());
				return;
			}
		}
	}

	UE_LOG(LogMatch, Warning, TEXT("Start: no room around %s for %s"), *Start->GetName(), *GetNameSafe(NewPlayer->PlayerState));
}

void AMyGameMode::WatchPlayerPawn(APawn* PlayerPawn)
{
	AController* Controller = PlayerPawn ? PlayerPawn->GetController() : nullptr;

	if (!Controller)
	{
		return;
	}

	for (auto It = WatchedPawns.CreateIterator(); It; ++It)
	{
		if (!It.Key().IsValid())
		{
			It.RemoveCurrent();
		}
	}

	WatchedPawns.Add(PlayerPawn, Controller);

	if (IMyCombatInterface* CombatInterface = Cast<IMyCombatInterface>(PlayerPawn))
	{
		CombatInterface->GetOnDeathDelegate().AddUniqueDynamic(this, &ThisClass::OnPlayerPawnDied);
	}

	PlayerPawn->OnDestroyed.AddUniqueDynamic(this, &ThisClass::OnPlayerPawnDestroyed);
}

void AMyGameMode::UnwatchPlayerPawn(APawn* PlayerPawn)
{
	if (!PlayerPawn)
	{
		return;
	}

	WatchedPawns.Remove(PlayerPawn);

	if (IMyCombatInterface* CombatInterface = Cast<IMyCombatInterface>(PlayerPawn))
	{
		CombatInterface->GetOnDeathDelegate().RemoveDynamic(this, &ThisClass::OnPlayerPawnDied);
	}

	PlayerPawn->OnDestroyed.RemoveDynamic(this, &ThisClass::OnPlayerPawnDestroyed);
}

void AMyGameMode::OnPlayerPawnDied(AActor* DeadActor)
{
	// The dead pawn stays possessed (death anim, camera) until RespawnPlayer replaces it, but stops beaming,
	// boosting, ... now
	if (const APawn* DeadPawn = Cast<APawn>(DeadActor))
	{
		CancelActiveAbilities(DeadPawn->GetController(), DeadPawn);
		ScheduleRespawn(DeadPawn->GetController());
	}
}

void AMyGameMode::OnPlayerPawnDestroyed(AActor* DestroyedActor)
{
	TWeakObjectPtr<AController> WeakController;

	if (!WatchedPawns.RemoveAndCopyValue(Cast<APawn>(DestroyedActor), WeakController))
	{
		return;
	}

	AController* Controller = WeakController.Get();

	// Leaving, or the world is going away
	if (!Controller || Controller->IsActorBeingDestroyed() || GetWorld()->bIsTearingDown)
	{
		return;
	}

	// Already on another pawn
	if (Controller->GetPawn() && Controller->GetPawn() != DestroyedActor)
	{
		return;
	}

	// Still the avatar while it is being destroyed; by the respawn it is gone
	CancelActiveAbilities(Controller, Cast<APawn>(DestroyedActor));
	ScheduleRespawn(Controller);
}

void AMyGameMode::ScheduleRespawn(AController* Controller)
{
	if (!bRespawnEnabled || !Controller || PendingRespawns.Contains(Controller))
	{
		return;
	}

	// Leaving the map (StartToLeaveMap cleared the timers), or the lobby countdown: everyone starts aboard at 0 anyway
	if (bRestarting || IsLobbyCountingDown())
	{
		return;
	}

	FPendingRespawn& Pending = PendingRespawns.Add(Controller);
	const TWeakObjectPtr<AController> WeakController(Controller);
	FTimerManager& TimerManager = GetWorldTimerManager();

	// Never in the same frame as the death: this can run inside the dead pawn's Destroy
	const float Delay = FMath::Max(RespawnDelay, 0.1f);
	TimerManager.SetTimer(Pending.RespawnTimer, FTimerDelegate::CreateUObject(this, &ThisClass::RespawnPlayer, WeakController), Delay, false);

	const float FXDelay = Delay - FMath::Clamp(RespawnFXLeadTime, 0.f, Delay);

	if (FXDelay > 0.f)
	{
		TimerManager.SetTimer(Pending.FXTimer, FTimerDelegate::CreateUObject(this, &ThisClass::StartRespawnFX, WeakController), FXDelay, false);
	}
	else
	{
		StartRespawnFX(WeakController);
	}
}

void AMyGameMode::StartRespawnFX(TWeakObjectPtr<AController> WeakController)
{
	FPendingRespawn* Pending = PendingRespawns.Find(WeakController);
	AController* Controller = WeakController.Get();

	if (!Pending || !Controller)
	{
		return;
	}

	FPawnFit Fit;
	FRespawnSpot Spot;

	if (GetPawnFit(Controller, Fit) && FindRespawnSpot(Controller, Fit, Spot))
	{
		PlayRespawnFX(Spot);
		Pending->Spot = Spot;
	}
}

void AMyGameMode::RespawnPlayer(TWeakObjectPtr<AController> WeakController)
{
	FPendingRespawn Pending;

	if (!PendingRespawns.RemoveAndCopyValue(WeakController, Pending))
	{
		return;
	}

	GetWorldTimerManager().ClearTimer(Pending.FXTimer);

	AController* Controller = WeakController.Get();

	// The lobby countdown began meanwhile: the start puts him aboard (BeginRound takes the dead lobby pawn back)
	if (!IsValid(Controller) || Controller->IsActorBeingDestroyed() || IsLobbyCountingDown())
	{
		return;
	}

	// First, so the dead pawn's capsule doesn't get in the way of the fit tests. RestartPlayerAtTransform only
	// spawns a pawn for a controller without one
	if (APawn* DeadPawn = Controller->GetPawn())
	{
		CancelActiveAbilities(Controller, DeadPawn);
		UnwatchPlayerPawn(DeadPawn);
		Controller->UnPossess();
		DeadPawn->Destroy();
	}

	FPawnFit Fit;
	FRespawnSpot Spot;
	bool bHasSpot = false;

	if (GetPawnFit(Controller, Fit))
	{
		if (Pending.Spot.IsSet())
		{
			const FRespawnSpot& Picked = Pending.Spot.GetValue();

			if (!Picked.bOnTile && Picked.Ship.IsExplicitlyNull())
			{
				Spot = Picked;
				bHasSpot = true;
			}
			else if (!Picked.bOnTile)
			{
				// A deck spot (bRespawnAboard) moves with its ship since the FX started; a ship sunk meanwhile: pick again
				if (const AAirshipPawn* Ship = Picked.Ship.Get(); Ship && !Ship->IsAirshipDead())
				{
					Spot = Picked;
					Spot.PawnTransform = MyGameModeMatch::YawOnly(Picked.ShipLocal * Ship->GetActorTransform());
					bHasSpot = true;
				}
			}
			else if (AMyHexPlatform* Platform = Picked.Platform.Get())
			{
				// Tested again: since the FX started the tile may have fallen, or someone may be standing on it
				bHasSpot = FitPawnOnTile(Platform, Picked.TileCoord, Fit, Picked.PawnTransform.Rotator(), Controller, Spot);
			}
		}

		if (!bHasSpot && FindRespawnSpot(Controller, Fit, Spot))
		{
			// This FX is late, but plays where the pawn appears
			PlayRespawnFX(Spot);
			bHasSpot = true;
		}
	}

	if (bHasSpot)
	{
		RestartPlayerAtTransform(Controller, Spot.PawnTransform);
	}

	if (!Controller->GetPawn())
	{
		// Team match: the late joiner's start-aboard rule isn't for respawns
		TGuardValue<bool> FromRespawn(bRestartFromRespawn, true);
		RestartPlayer(Controller);
	}

	if (!Controller->GetPawn())
	{
		UE_LOG(LogTemp, Warning, TEXT("Respawn: couldn't spawn a pawn for %s"), *GetNameSafe(Controller));
	}
}

bool AMyGameMode::GetPawnFit(AController* Controller, FPawnFit& OutFit)
{
	UClass* PawnClass = GetDefaultPawnClassForController(Controller);
	OutFit.PawnToFit = PawnClass ? PawnClass->GetDefaultObject<APawn>() : nullptr;

	if (!OutFit.PawnToFit)
	{
		return false;
	}

	// The class default's capsule: its transform isn't set up, so the scale comes from the relative scale
	const ACharacter* CharacterToFit = Cast<ACharacter>(OutFit.PawnToFit);

	if (const UCapsuleComponent* Capsule = CharacterToFit ? CharacterToFit->GetCapsuleComponent() : nullptr)
	{
		const FVector Scale = Capsule->GetRelativeScale3D();
		OutFit.HalfHeight = Capsule->GetUnscaledCapsuleHalfHeight() * static_cast<float>(Scale.Z);
		OutFit.Radius = Capsule->GetUnscaledCapsuleRadius() * static_cast<float>(FMath::Max(Scale.X, Scale.Y));
	}
	else
	{
		OutFit.HalfHeight = OutFit.PawnToFit->GetDefaultHalfHeight();
		OutFit.Radius = OutFit.HalfHeight;
	}

	return true;
}

bool AMyGameMode::FindRespawnSpot(AController* Controller, const FPawnFit& Fit, FRespawnSpot& OutSpot)
{
	const AMyGameState* MyGameState = GetGameState<AMyGameState>();
	const uint8 MatchTeam = bMatchOn ? GetControllerTeam(Controller) : MyMatch::NoTeam;

	// A lobby pawn destroyed anyway (out of the world) comes back at a lobby spot (SPEC_B_LOBBY 3.3)
	if (bMatchOn && IsInLobby() && GetLobbySpot(Controller, Fit, OutSpot))
	{
		return true;
	}

	// Team match option (bRespawnAboard, off by default): the own ship's deck while it is alive, in its lane and hasn't
	// been hit for 5 s. Off because a respawn aboard leaves a runner 225 m out until a pilot flies him in (B9.7)
	if (bMatchOn && MyGameState && MatchTeam < MyMatch::NumTeams && UMyMatchSettings::Get()->bRespawnAboard && GetPhase() == EMyMatchPhase::InProgress)
	{
		AAirshipPawn* Ship = MyGameState->GetTeamState(MatchTeam).Ship;
		const UAirshipLaneComponent* Lane = IsValid(Ship) ? Ship->GetLane() : nullptr;
		const EMyLaneState LaneState = Lane ? Lane->GetLaneState() : EMyLaneState::NoLane;
		const bool bInLane = LaneState == EMyLaneState::Cruising || LaneState == EMyLaneState::Waiting || LaneState == EMyLaneState::Assist
			|| LaneState == EMyLaneState::PilotedInLane;
		FTransform DeckTransform;

		if (bInLane && GetServerTime() - LastShipDamageTime[MatchTeam] >= 5.0 && FindAboardTransform(Controller, Ship, INDEX_NONE, DeckTransform))
		{
			OutSpot = FRespawnSpot();
			OutSpot.PawnTransform = DeckTransform;
			OutSpot.GroundLocation = DeckTransform.GetLocation() - FVector(0.f, 0.f, Fit.HalfHeight);
			OutSpot.Ship = Ship;
			OutSpot.ShipLocal = DeckTransform.GetRelativeTransform(Ship->GetActorTransform());
			return true;
		}
	}

	// Team match: also with nobody landed yet (PastDistance -1: the path's first platforms, nearest the path start first),
	// so a respawn never needs the start floor (SPEC_B_LOBBY 3.4). Match off: the PlayerStart until someone lands
	if (MyGameState && (MyGameState->GetLeadSplineDistance() >= 0.f || bMatchOn))
	{
		// Platforms up to the furthest distance the lead has reached are collapsing. It only goes up, so a
		// lead that walks back (or leaves) doesn't put the spot on one of them
		const float PastDistance = FMath::Max(MyGameState->GetLeadSplineDistance(), MyGameState->GetActivatedSplineDistance());

		AMyHexPlatform* LeadPlatform = nullptr;

		for (const AMyPlayerState* Leader : MyGameState->GetLeadingPlayerStates())
		{
			if (Leader && IsValid(Leader->GetCurrentPlatform()))
			{
				LeadPlatform = Leader->GetCurrentPlatform();
				break;
			}
		}

		struct FCandidate
		{
			AMyHexPlatform* Platform;
			float SplineDistance;
			double DistSqToLead;
			
			/** Team match: how far toward the player's own lane (side x lateral offset from the path). */
			double OwnSide = 0.0;
		};

		TArray<FCandidate> Candidates;

		for (TActorIterator<AMyHexPlatform> It(GetWorld()); It; ++It)
		{
			AMyHexPlatform* Platform = *It;

			if (IsValid(Platform) && Platform->HasSplineDistance() && Platform->GetSplineDistance() > PastDistance
				&& Platform->GetTileInfos().Num() > 0)
			{
				const double DistSqToLead = LeadPlatform
					? FVector::DistSquared(Platform->GetActorLocation(), LeadPlatform->GetActorLocation())
					: 0.0;
				Candidates.Add({ Platform, Platform->GetSplineDistance(), DistSqToLead });
			}
		}

		// Nearest along the path first; at the same distance (both chains), the one nearest the lead's platform
		Candidates.Sort([](const FCandidate& A, const FCandidate& B)
		{
			return A.SplineDistance != B.SplineDistance ? A.SplineDistance < B.SplineDistance : A.DistSqToLead < B.DistSqToLead;
		});

		// Team match, versus: still past the lead (everything behind it collapses), but on the player's own side of the
		// path. Of the nearest few (6, within 60 m x S along the path), the one furthest toward his own lane first: else
		// a respawn could land on the enemy's side, about 425 m from his own lane (B9.7)
		const int8 OwnSide = MatchTeam < MyMatch::NumTeams && IsVersusRound() ? GetSideForTeam(MatchTeam) : 0;
		const UMyLaneSubsystem* Lanes = OwnSide != 0 ? UMyLaneSubsystem::Get(this) : nullptr;

		if (Lanes && Lanes->HasLanes() && Candidates.Num() > 1)
		{
			constexpr int32 MaxOwnSideCandidates = 6;
			const float Window = 6000.f * GetLayoutScale();
			const float Nearest = Candidates[0].SplineDistance;
			int32 NumNear = 0;

			while (NumNear < Candidates.Num() && NumNear < MaxOwnSideCandidates && Candidates[NumNear].SplineDistance <= Nearest + Window)
			{
				Candidates[NumNear].OwnSide = OwnSide * Lanes->GetLateralFromPath(Candidates[NumNear].Platform->GetActorLocation());
				++NumNear;
			}

			TArray<FCandidate> Near(Candidates.GetData(), NumNear);
			Near.StableSort([](const FCandidate& A, const FCandidate& B) { return A.OwnSide > B.OwnSide; });

			for (int32 Index = 0; Index < NumNear; ++Index)
			{
				Candidates[Index] = Near[Index];
			}
		}

		// Last resort (the end of the path, or no room ahead): the lead's own platform
		if (LeadPlatform && LeadPlatform->GetTileInfos().Num() > 0)
		{
			Candidates.Add({ LeadPlatform, LeadPlatform->GetSplineDistance(), 0.0 });
		}

		for (const FCandidate& Candidate : Candidates)
		{
			// Face on along the path, away from the lead (nobody landed: the path's start heading)
			const FVector Forward = LeadPlatform && LeadPlatform != Candidate.Platform
				? (Candidate.Platform->GetActorLocation() - LeadPlatform->GetActorLocation()).GetSafeNormal2D()
				: FVector::ZeroVector;
			const UMyLaneSubsystem* HeadingLanes = LeadPlatform ? nullptr : UMyLaneSubsystem::Get(this);
			const double Yaw = !Forward.IsNearlyZero() ? Forward.Rotation().Yaw
				: (HeadingLanes && HeadingLanes->HasLanes() ? static_cast<double>(HeadingLanes->GetStartYaw()) : Controller->GetControlRotation().Yaw);

			if (FindRespawnTile(Candidate.Platform, Fit, FRotator(0.0, Yaw, 0.0), Controller, OutSpot))
			{
				return true;
			}
		}
	}

	// Nobody has landed on a platform yet, or no platform has room
	AActor* StartSpot = FindPlayerStart(Controller);

	if (!StartSpot)
	{
		return false;
	}

	OutSpot = FRespawnSpot();
	OutSpot.PawnTransform = FTransform(FRotator(0.0, StartSpot->GetActorRotation().Yaw, 0.0), StartSpot->GetActorLocation());
	OutSpot.GroundLocation = StartSpot->GetActorLocation() - FVector(0.f, 0.f, Fit.HalfHeight);
	return true;
}

bool AMyGameMode::FindRespawnTile(AMyHexPlatform* Platform, const FPawnFit& Fit, const FRotator& Rotation,
	const AController* Controller, FRespawnSpot& OutSpot) const
{
	// Each try is a few overlap tests; a platform that fits nobody in this many tiles is crowded or covered in props
	constexpr int32 MaxTileTries = 12;

	TArray<const FHexTileInfo*> Tiles;

	for (const TPair<FIntVector, FHexTileInfo>& Tile : Platform->GetTileInfos())
	{
		if (!Platform->IsTileCollapsed(Tile.Key))
		{
			Tiles.Add(&Tile.Value);
		}
	}

	// A pointer array's Sort compares the pointed-to tiles
	Tiles.Sort([](const FHexTileInfo& A, const FHexTileInfo& B)
	{
		const bool bAOnPath = A.PathDistance == 0;
		const bool bBOnPath = B.PathDistance == 0;

		if (bAOnPath != bBOnPath)
		{
			return bAOnPath;
		}

		const bool bAInside = A.EdgeDepth > 0;
		const bool bBInside = B.EdgeDepth > 0;

		if (bAInside != bBInside)
		{
			return bAInside;
		}

		return A.LocalTopCenter.SizeSquared2D() < B.LocalTopCenter.SizeSquared2D();
	});

	for (int32 Index = 0; Index < Tiles.Num() && Index < MaxTileTries; ++Index)
	{
		if (FitPawnOnTile(Platform, Tiles[Index]->Coord, Fit, Rotation, Controller, OutSpot))
		{
			return true;
		}
	}

	return false;
}

bool AMyGameMode::FitPawnOnTile(AMyHexPlatform* Platform, const FIntVector& TileCoord, const FPawnFit& Fit, const FRotator& Rotation,
	const AController* Controller, FRespawnSpot& OutSpot) const
{
	const FHexTileInfo* Tile = Platform ? Platform->GetTileInfos().Find(TileCoord) : nullptr;

	if (!Tile || Platform->IsTileCollapsed(TileCoord))
	{
		return false;
	}

	const FTransform& PlatformTransform = Platform->GetActorTransform();
	const float CapsuleLift = Fit.HalfHeight + RespawnHeightAboveTile;
	const FVector Ground = PlatformTransform.TransformPosition(Tile->LocalTopCenter);
	FVector Location = Ground + FVector(0.f, 0.f, CapsuleLift);

	// Moves the spot off pawns and props; false when nothing close by fits
	if (!GetWorld()->FindTeleportSpot(Fit.PawnToFit, Location, Rotation))
	{
		return false;
	}

	// Pushed off the tile, possibly over the edge
	const double TileReach = Tile->Apothem * PlatformTransform.GetScale3D().GetAbsMax();

	if (FVector::DistSquared2D(Location, Ground) > FMath::Square(TileReach))
	{
		return false;
	}

	// Pawns that haven't spawned yet are invisible to FindTeleportSpot: keep a capsule's width from their spots
	const double MinGap = 2.0 * Fit.Radius;

	for (const TPair<TWeakObjectPtr<AController>, FPendingRespawn>& Other : PendingRespawns)
	{
		if (Other.Key != Controller && Other.Value.Spot.IsSet()
			&& FVector::DistSquared(Other.Value.Spot->PawnTransform.GetLocation(), Location) < FMath::Square(MinGap))
		{
			return false;
		}
	}

	OutSpot = FRespawnSpot();
	OutSpot.PawnTransform = FTransform(Rotation, Location);
	OutSpot.GroundLocation = Location - FVector(0.f, 0.f, CapsuleLift);
	OutSpot.bOnTile = true;
	OutSpot.Platform = Platform;
	OutSpot.TileCoord = TileCoord;
	return true;
}

void AMyGameMode::PlayRespawnFX(const FRespawnSpot& Spot) const
{
	AMyGameState* MyGameState = GetGameState<AMyGameState>();

	if (MyGameState && RespawnFX)
	{
		MyGameState->MulticastPlayRespawnFX(RespawnFX, Spot.GroundLocation, Spot.PawnTransform.Rotator());
	}
}
