// Fill out your copyright notice in the Description page of Project Settings.

// Team match console (Docs/Airship/round2/SPEC_B.md B11, Appendix B): Aura.Match.* commands for tests and the CVar
// Aura.Match.Enable. The commands are compiled out of Shipping like Aura.Airship.* (the pause menu's Start match /
// Restart match buttons cover a packaged host); the CVar stays, AMyGameMode::InitGame reads it by name.

#include "MyGameMode.h"
#include "MyGameState.h"
#include "MyPlayerState.h"
#include "AbilitySystem/MyAttributeSet.h"
#include "Airship/AirshipLaneComponent.h"
#include "Airship/AirshipPawn.h"
#include "Airship/AirshipSubsystem.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "GameFramework/PlayerController.h"
#include "HAL/FileManager.h"
#include "HAL/IConsoleManager.h"
#include "Interfaces/MyCombatInterface.h"
#include "Match/MyLaneSubsystem.h"
#include "Match/MyMatchSettings.h"
#include "Match/MyMatchTypes.h"
#include "Match/MyTeamLibrary.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "UObject/UnrealType.h"

// Read at InitGame (a change applies on the next map load): -1 = by UMyMatchSettings::MatchMaps, 0 = off, 1 = on
static TAutoConsoleVariable<int32> CVarMatchEnable(
	TEXT("Aura.Match.Enable"),
	-1,
	TEXT("Team match (SPEC_B): -1 = on for the maps in Project Settings > Game > Match > MatchMaps (default), 0 = off, 1 = on. Read when a map loads; the URL option Match=0|1 wins."),
	ECVF_Default);

#if !UE_BUILD_SHIPPING
// Named, not anonymous: the unity build compiles this file together with others
namespace MyMatchConsole
{
	bool CheckServer(const UWorld* World, const TCHAR* Command)
	{
		if (!World || World->GetNetMode() == NM_Client)
		{
			UE_LOG(LogMatch, Warning, TEXT("%s: run it on the server (listen server window or standalone)"), Command);
			return false;
		}
		return true;
	}

	AMyGameMode* GetMatchGameMode(UWorld* World, const TCHAR* Command)
	{
		AMyGameMode* GameMode = World ? World->GetAuthGameMode<AMyGameMode>() : nullptr;

		if (!GameMode || !GameMode->IsMatchOn())
		{
			UE_LOG(LogMatch, Warning, TEXT("%s: no match runs here (AMyGameMode with the match on: MatchMaps, Aura.Match.Enable 1 before the map loads, or ?Match=1)"), Command);
			return nullptr;
		}
		return GameMode;
	}

	bool ParseTeam(const TArray<FString>& Args, int32 Index, uint8& OutTeam, const TCHAR* Command)
	{
		if (!Args.IsValidIndex(Index) || !Args[Index].IsNumeric())
		{
			UE_LOG(LogMatch, Warning, TEXT("%s: give the team, 0 (%s) or 1 (%s)"), Command, *UMyTeamLibrary::GetTeamName(0).ToString(), *UMyTeamLibrary::GetTeamName(1).ToString());
			return false;
		}

		const int32 Team = FCString::Atoi(*Args[Index]);

		if (Team < 0 || Team >= MyMatch::NumTeams)
		{
			UE_LOG(LogMatch, Warning, TEXT("%s: team %d is not 0 or 1"), Command, Team);
			return false;
		}

		OutTeam = static_cast<uint8>(Team);
		return true;
	}

	/** The team's living ship (the server's game state), or null with a log line. */
	AAirshipPawn* GetTeamShip(UWorld* World, uint8 Team, const TCHAR* Command)
	{
		const AMyGameState* GameState = World ? World->GetGameState<AMyGameState>() : nullptr;
		AAirshipPawn* Ship = GameState ? GameState->GetTeamState(Team).Ship.Get() : nullptr;

		if (!IsValid(Ship) || Ship->IsAirshipDead())
		{
			UE_LOG(LogMatch, Warning, TEXT("%s: %s has no ship right now"), Command, *UMyTeamLibrary::GetTeamName(Team).ToString());
			return nullptr;
		}
		return Ship;
	}

	/** PlayerIndex-th player controller of the world (0 = the host), the Aura.Airship.* order. */
	APlayerController* GetPlayerController(const UWorld* World, int32 PlayerIndex)
	{
		int32 Index = 0;

		for (FConstPlayerControllerIterator It = World->GetPlayerControllerIterator(); It; ++It, ++Index)
		{
			if (Index == PlayerIndex)
			{
				return It->Get();
			}
		}
		return nullptr;
	}

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

	const TCHAR* TeamModeName(EMyTeamMode Mode)
	{
		switch (Mode)
		{
		case EMyTeamMode::Practice: return TEXT("practice");
		case EMyTeamMode::OneVsOne: return TEXT("1v1");
		case EMyTeamMode::TwoVsTwo: return TEXT("2v2");
		default: return TEXT("auto");
		}
	}

	FString EnumText(const UEnum* Enum, int64 Value)
	{
		return Enum ? Enum->GetNameStringByValue(Value) : FString::FromInt(static_cast<int32>(Value));
	}

	FString RulesText(const FMyMatchRules& Rules)
	{
		return FString::Printf(TEXT("Teams=%s ShipLives=%d Swarm=%d TimeLimit=%d FF=%d GrappleShips=%d LaneAssist=%d"), TeamModeName(Rules.TeamMode),
			Rules.ShipLives, Rules.SwarmDifficulty, Rules.TimeLimitMinutes, Rules.bFriendlyFire ? 1 : 0, Rules.bGrappleShips ? 1 : 0, Rules.bLaneAssist ? 1 : 0);
	}

	/**
	 * "Name", "Struct.Field", "StaticArray[1]", "Array[0].Field" from Container (of Struct): the property and its value.
	 * The last part's static array index picks the element; a TArray index goes through the array.
	 */
	bool ResolvePath(const UStruct* Struct, void* Container, const FString& Path, FProperty*& OutProperty, void*& OutValue)
	{
		TArray<FString> Parts;
		Path.ParseIntoArray(Parts, TEXT("."));

		for (int32 PartIndex = 0; PartIndex < Parts.Num(); ++PartIndex)
		{
			FString Name = Parts[PartIndex];
			int32 ElementIndex = INDEX_NONE;
			int32 Open = INDEX_NONE;

			if (Name.FindChar(TEXT('['), Open))
			{
				ElementIndex = FCString::Atoi(*Name.Mid(Open + 1));
				Name.LeftInline(Open);
			}

			FProperty* Property = Struct ? FindFProperty<FProperty>(Struct, *Name) : nullptr;

			if (!Property)
			{
				return false;
			}

			const bool bStaticArray = Property->ArrayDim > 1;

			if (bStaticArray && ElementIndex >= Property->ArrayDim)
			{
				return false;
			}

			void* Value = Property->ContainerPtrToValuePtr<void>(Container, bStaticArray && ElementIndex > 0 ? ElementIndex : 0);
			FProperty* ValueProperty = Property;

			if (ElementIndex != INDEX_NONE && !bStaticArray)
			{
				FArrayProperty* ArrayProperty = CastField<FArrayProperty>(Property);

				if (!ArrayProperty)
				{
					return false;
				}

				FScriptArrayHelper Helper(ArrayProperty, Value);

				if (!Helper.IsValidIndex(ElementIndex))
				{
					return false;
				}

				Value = Helper.GetRawPtr(ElementIndex);
				ValueProperty = ArrayProperty->Inner;
			}

			if (PartIndex == Parts.Num() - 1)
			{
				OutProperty = ValueProperty;
				OutValue = Value;
				return true;
			}

			const FStructProperty* StructProperty = CastField<FStructProperty>(ValueProperty);

			if (!StructProperty)
			{
				return false;
			}

			Struct = StructProperty->Struct;
			Container = Value;
		}

		return false;
	}

	FString ExportValue(const FProperty* Property, const void* Value, UObject* Owner)
	{
		FString Text;
		Property->ExportTextItem_Direct(Text, Value, nullptr, Owner, PPF_None);
		return Text;
	}

	FString JoinArgs(const TArray<FString>& Args, int32 First)
	{
		FString Result;

		for (int32 Index = First; Index < Args.Num(); ++Index)
		{
			Result += (Index > First ? TEXT(" ") : TEXT("")) + Args[Index];
		}
		return Result;
	}

	// --- JSON (by hand: a flat writer keeps the module free of the Json dependency) ---

	FString JsonString(const FString& Value)
	{
		FString Escaped = Value.ReplaceCharWithEscapedChar();
		return TEXT("\"") + Escaped + TEXT("\"");
	}

	FString JsonNumber(double Value)
	{
		return FMath::IsFinite(Value) ? FString::SanitizeFloat(Value) : FString(TEXT("null"));
	}

	FString JsonVector(const FVector& Value)
	{
		return FString::Printf(TEXT("[%s, %s, %s]"), *JsonNumber(Value.X), *JsonNumber(Value.Y), *JsonNumber(Value.Z));
	}

	/** Builds one JSON object from "key": value pairs (values already JSON). */
	struct FJsonObjectText
	{
		TArray<FString> Fields;

		FJsonObjectText& Raw(const TCHAR* Key, const FString& JsonValue)
		{
			Fields.Add(FString::Printf(TEXT("\"%s\": %s"), Key, *JsonValue));
			return *this;
		}
		FJsonObjectText& Str(const TCHAR* Key, const FString& Value) { return Raw(Key, JsonString(Value)); }
		FJsonObjectText& Num(const TCHAR* Key, double Value) { return Raw(Key, JsonNumber(Value)); }
		FJsonObjectText& Bool(const TCHAR* Key, bool bValue) { return Raw(Key, bValue ? TEXT("true") : TEXT("false")); }
		FJsonObjectText& Vec(const TCHAR* Key, const FVector& Value) { return Raw(Key, JsonVector(Value)); }

		FString ToString(const FString& Indent) const
		{
			if (Fields.IsEmpty())
			{
				return TEXT("{}");
			}
			const FString Inner = Indent + TEXT("  ");
			return TEXT("{\n") + Inner + FString::Join(Fields, *(TEXT(",\n") + Inner)) + TEXT("\n") + Indent + TEXT("}");
		}
	};

	FString JsonArray(const TArray<FString>& Items, const FString& Indent)
	{
		if (Items.IsEmpty())
		{
			return TEXT("[]");
		}
		const FString Inner = Indent + TEXT("  ");
		return TEXT("[\n") + Inner + FString::Join(Items, *(TEXT(",\n") + Inner)) + TEXT("\n") + Indent + TEXT("]");
	}

	FString ShipJson(const AAirshipPawn* Ship, const UMyLaneSubsystem* Lanes, double Now, const FString& Indent)
	{
		FJsonObjectText Object;
		Object.Str(TEXT("name"), Ship->GetName())
			.Num(TEXT("team"), Ship->GetTeamId())
			.Bool(TEXT("alive"), !Ship->IsAirshipDead())
			.Vec(TEXT("location"), Ship->GetActorLocation())
			.Vec(TEXT("velocity"), Ship->GetVelocity())
			.Num(TEXT("yaw"), Ship->GetActorRotation().Yaw)
			.Bool(TEXT("protected"), Ship->IsSpawnProtected())
			.Num(TEXT("protection_left_s"), Ship->GetProtectionEndServerTime() > 0.0 ? FMath::Max(0.0, Ship->GetProtectionEndServerTime() - Now) : 0.0)
			.Bool(TEXT("piloted"), Ship->HasPilot() || Ship->GetController() != nullptr)
			.Str(TEXT("pilot"), Ship->GetPlayerState() ? Ship->GetPlayerState()->GetPlayerName() : FString());

		const FAirshipFlightTelemetry Telemetry = Ship->GetFlightTelemetry();
		Object.Num(TEXT("speed_ms"), Telemetry.SpeedMS).Num(TEXT("health"), Telemetry.Health).Num(TEXT("max_health"), Telemetry.MaxHealth);

		if (Lanes && Lanes->HasLanes())
		{
			Object.Num(TEXT("u_m"), Lanes->ProjectU(Ship->GetActorLocation()) / 100.0);
		}

		if (const UAirshipLaneComponent* Lane = Ship->GetLane())
		{
			Object.Str(TEXT("lane_state"), UAirshipLaneComponent::GetLaneStateName(Lane->GetLaneState()))
				.Num(TEXT("lane_side"), Lane->GetLaneSide())
				.Num(TEXT("lane_u_m"), Lane->GetShipU() / 100.0)
				.Num(TEXT("lane_lateral_error_m"), Lane->GetLateralError() / 100.0)
				.Num(TEXT("lane_vertical_error_m"), Lane->GetVerticalError() / 100.0)
				.Num(TEXT("lane_target_u_m"), Lane->GetTargetU() / 100.0)
				.Num(TEXT("lane_target_speed_ms"), Lane->GetTargetSpeed() / 100.0)
				.Str(TEXT("lane_clamp"), UAirshipLaneComponent::GetClampName(Lane->GetClamp()))
				.Num(TEXT("lane_bypass_m"), Lane->GetBypassOffset() / 100.0)
				.Num(TEXT("recall_in_s"), Lane->GetRecallServerTime() > 0.0 ? Lane->GetRecallServerTime() - Now : -1.0)
				.Num(TEXT("lane_update_ms"), Lane->GetUpdateTimeMs());
		}

		return Object.ToString(Indent);
	}

	/** The match state as JSON (B11): phase, rules, result, teams, ships, players, the path / cruise end. */
	FString BuildDump(UWorld* World)
	{
		const AMyGameState* GameState = World->GetGameState<AMyGameState>();
		const AMyGameMode* GameMode = World->GetAuthGameMode<AMyGameMode>();
		const UMyLaneSubsystem* Lanes = UMyLaneSubsystem::Get(World);
		const double Now = GameState ? GameState->GetServerWorldTimeSeconds() : World->GetTimeSeconds();
		const FString Indent1 = TEXT("  ");
		const FString Indent2 = TEXT("    ");

		FJsonObjectText Root;
		Root.Str(TEXT("map"), World->GetMapName())
			.Num(TEXT("server_time"), Now)
			.Bool(TEXT("match_on"), GameMode && GameMode->IsMatchOn());

		if (!GameState)
		{
			return Root.ToString(FString());
		}

		const FMyMatchRules& Rules = GameState->GetMatchRules();
		Root.Str(TEXT("phase"), PhaseName(GameState->GetMatchPhase()))
			.Num(TEXT("phase_end_in_s"), GameState->GetPhaseEndServerTime() > 0.0 ? GameState->GetPhaseEndServerTime() - Now : -1.0)
			.Num(TEXT("time_left_s"), GameState->GetMatchEndServerTime() > 0.0 ? GameState->GetMatchEndServerTime() - Now : -1.0)
			.Num(TEXT("expected_players"), GameState->GetExpectedPlayers())
			.Num(TEXT("round"), GameState->GetRoundIndex())
			.Bool(TEXT("sides_swapped"), GameState->AreLaneSidesSwapped())
			.Bool(TEXT("play_goes_on"), GameState->IsPlayGoingOn())
			.Bool(TEXT("versus"), GameMode && GameMode->IsVersusRound())
			.Str(TEXT("next_team_mode"), GameMode ? TeamModeName(GameMode->GetNextTeamMode()) : TEXT(""))
			.Str(TEXT("result"), EnumText(StaticEnum<EMyMatchResult>(), static_cast<int64>(GameState->GetMatchResult())))
			.Str(TEXT("end_reason"), EnumText(StaticEnum<EMyMatchEndReason>(), static_cast<int64>(GameState->GetEndReason())))
			.Num(TEXT("winning_team"), GameState->GetWinningTeam())
			.Num(TEXT("lead_spline_distance"), GameState->GetLeadSplineDistance());

		FJsonObjectText RulesObject;
		RulesObject.Str(TEXT("teams"), TeamModeName(Rules.TeamMode)).Num(TEXT("ship_lives"), Rules.ShipLives).Num(TEXT("swarm"), Rules.SwarmDifficulty)
			.Num(TEXT("time_limit_min"), Rules.TimeLimitMinutes).Bool(TEXT("friendly_fire"), Rules.bFriendlyFire)
			.Bool(TEXT("grapple_ships"), Rules.bGrappleShips).Bool(TEXT("lane_assist"), Rules.bLaneAssist);
		Root.Raw(TEXT("rules"), RulesObject.ToString(Indent1));

		Root.Bool(TEXT("has_lanes"), Lanes && Lanes->HasLanes());

		if (Lanes && Lanes->HasLanes())
		{
			Root.Num(TEXT("lane_start_u_m"), Lanes->GetLaneStartU() / 100.0)
				.Num(TEXT("path_end_u_m"), Lanes->GetPathEndU() / 100.0)
				.Num(TEXT("cruise_end_u_m"), Lanes->GetCruiseEndU() / 100.0);
		}

		TArray<FString> TeamItems;

		for (uint8 Team = 0; Team < MyMatch::NumTeams; ++Team)
		{
			const FMyTeamState& State = GameState->GetTeamState(Team);
			float FrontU = 0.f;
			const bool bFront = Lanes && Lanes->GetTeamFrontU(Team, FrontU);

			FJsonObjectText Object;
			Object.Num(TEXT("team"), Team).Str(TEXT("name"), UMyTeamLibrary::GetTeamName(Team).ToString()).Bool(TEXT("active"), State.bActive)
				.Num(TEXT("players"), State.NumPlayers).Num(TEXT("lives_left"), State.LivesLeft).Num(TEXT("bonus_lives"), State.BonusLives)
				.Num(TEXT("ships_lost"), State.ShipsLost).Num(TEXT("lane_side"), State.LaneSide).Num(TEXT("ship_health_pct"), State.ShipHealthPct)
				.Str(TEXT("ship"), IsValid(State.Ship) ? State.Ship->GetName() : FString())
				.Num(TEXT("ship_respawn_in_s"), State.ShipRespawnServerTime > 0.0 ? State.ShipRespawnServerTime - Now : -1.0)
				.Num(TEXT("empty_for_s"), State.EmptySinceServerTime > 0.0 ? Now - State.EmptySinceServerTime : -1.0)
				.Bool(TEXT("eliminated"), State.bEliminated)
				.Raw(TEXT("front_u_m"), bFront ? JsonNumber(FrontU / 100.0) : FString(TEXT("null")));
			TeamItems.Add(Object.ToString(Indent2));
		}

		Root.Raw(TEXT("teams"), JsonArray(TeamItems, Indent1));

		TArray<FString> ShipItems;

		if (const UAirshipSubsystem* Airships = UAirshipSubsystem::Get(World))
		{
			for (const AAirshipPawn* Ship : Airships->GetAirships())
			{
				ShipItems.Add(ShipJson(Ship, Lanes, Now, Indent2));
			}
		}

		Root.Raw(TEXT("ships"), JsonArray(ShipItems, Indent1));

		TArray<FString> PlayerItems;

		for (const APlayerState* PlayerState : GameState->PlayerArray)
		{
			const AMyPlayerState* MyPlayerState = Cast<AMyPlayerState>(PlayerState);

			if (!MyPlayerState)
			{
				continue;
			}

			const APawn* Pawn = MyPlayerState->GetPawn();
			FJsonObjectText Object;
			Object.Str(TEXT("name"), MyPlayerState->GetPlayerName()).Num(TEXT("team"), MyPlayerState->GetTeamId())
				.Str(TEXT("pawn_class"), Pawn ? Pawn->GetClass()->GetName() : FString())
				.Bool(TEXT("ship_borne"), Pawn && UAirshipSubsystem::IsShipBorne(Pawn))
				.Num(TEXT("platform_spline_distance"), MyPlayerState->GetPlatformSplineDistance())
				.Num(TEXT("health"), MyPlayerState->MyAttributeSet ? MyPlayerState->MyAttributeSet->GetHealth() : -1.f);

			if (Pawn)
			{
				Object.Vec(TEXT("location"), Pawn->GetActorLocation());

				if (Lanes && Lanes->HasLanes())
				{
					Object.Num(TEXT("u_m"), Lanes->ProjectU(Pawn->GetActorLocation()) / 100.0)
						.Num(TEXT("lateral_from_path_m"), Lanes->GetLateralFromPath(Pawn->GetActorLocation()) / 100.0);
				}

				Object.Bool(TEXT("dead"), Pawn->Implements<UMyCombatInterface>() && IMyCombatInterface::Execute_IsDead(const_cast<APawn*>(Pawn)));
			}

			PlayerItems.Add(Object.ToString(Indent2));
		}

		Root.Raw(TEXT("players"), JsonArray(PlayerItems, Indent1));
		return Root.ToString(FString());
	}

	FAutoConsoleCommandWithWorldAndArgs GStatusCommand(
		TEXT("Aura.Match.Status"),
		TEXT("Aura.Match.Status - the team match on this machine (any): phase, rules, result, teams (players, lives, ship, lane state, respawn in), players (team, ship-borne)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			const AMyGameState* GameState = World ? World->GetGameState<AMyGameState>() : nullptr;

			if (!GameState)
			{
				UE_LOG(LogMatch, Log, TEXT("Aura.Match.Status: no AMyGameState in this world"));
				return;
			}

			const double Now = GameState->GetServerWorldTimeSeconds();
			UE_LOG(LogMatch, Log, TEXT("Match: phase %s (ends in %.1f s), round %d, expected %d, %s"), PhaseName(GameState->GetMatchPhase()),
				GameState->GetPhaseEndServerTime() > 0.0 ? GameState->GetPhaseEndServerTime() - Now : -1.0, GameState->GetRoundIndex(),
				GameState->GetExpectedPlayers(), *RulesText(GameState->GetMatchRules()));

			if (GameState->GetMatchEndServerTime() > 0.0)
			{
				UE_LOG(LogMatch, Log, TEXT("  time left %.1f s"), GameState->GetMatchEndServerTime() - Now);
			}

			// One lobby line (SPEC_B_LOBBY Appendix L-B); Aura.Lobby.Status has the rest
			UE_LOG(LogMatch, Log, TEXT("  lobby: round %d, in lobby %d, counting %d, start block %s, not ready %d, rematch %d, arriving %d"),
				GameState->IsLobbyRound() ? 1 : 0, GameState->IsInLobby() ? 1 : 0, GameState->IsLobbyCountingDown() ? 1 : 0,
				*EnumText(StaticEnum<EMyLobbyStartBlock>(), static_cast<int64>(GameState->GetLobbyStartBlock())), GameState->GetLobbyNotReady(),
				GameState->IsLobbyRematch() ? 1 : 0, GameState->CountArrivingPlayers());

			if (GameState->GetMatchPhase() == EMyMatchPhase::Ended)
			{
				UE_LOG(LogMatch, Log, TEXT("  result %s, winner %d, reason %s"), *EnumText(StaticEnum<EMyMatchResult>(), static_cast<int64>(GameState->GetMatchResult())),
					GameState->GetWinningTeam(), *EnumText(StaticEnum<EMyMatchEndReason>(), static_cast<int64>(GameState->GetEndReason())));
			}

			for (uint8 Team = 0; Team < MyMatch::NumTeams; ++Team)
			{
				const FMyTeamState& State = GameState->GetTeamState(Team);
				const AAirshipPawn* Ship = State.Ship;
				const UAirshipLaneComponent* Lane = IsValid(Ship) ? Ship->GetLane() : nullptr;

				UE_LOG(LogMatch, Log, TEXT("  %s: %s, %d player(s), lives %d (+%d bonus), lost %d, side %d, hull %d %%, ship %s%s%s%s"),
					*UMyTeamLibrary::GetTeamName(Team).ToString(), State.bActive ? TEXT("active") : TEXT("inactive"), State.NumPlayers, State.LivesLeft,
					State.BonusLives, State.ShipsLost, State.LaneSide, State.ShipHealthPct, IsValid(Ship) ? *Ship->GetName() : TEXT("none"),
					Lane ? *FString::Printf(TEXT(" (%s)"), UAirshipLaneComponent::GetLaneStateName(Lane->GetLaneState())) : TEXT(""),
					State.ShipRespawnServerTime > 0.0 ? *FString::Printf(TEXT(", back in %.1f s"), State.ShipRespawnServerTime - Now) : TEXT(""),
					State.bEliminated ? TEXT(", ELIMINATED") : TEXT(""));
			}

			for (const APlayerState* PlayerState : GameState->PlayerArray)
			{
				const AMyPlayerState* MyPlayerState = Cast<AMyPlayerState>(PlayerState);
				const APawn* Pawn = MyPlayerState ? MyPlayerState->GetPawn() : nullptr;

				if (MyPlayerState)
				{
					UE_LOG(LogMatch, Log, TEXT("  player %s: team %d, pawn %s%s"), *MyPlayerState->GetPlayerName(), MyPlayerState->GetTeamId(),
						Pawn ? *Pawn->GetClass()->GetName() : TEXT("none"), Pawn && UAirshipSubsystem::IsShipBorne(Pawn) ? TEXT(", ship-borne") : TEXT(""));
				}
			}
		})
	);

	FAutoConsoleCommandWithWorldAndArgs GRulesCommand(
		TEXT("Aura.Match.Rules"),
		TEXT("Aura.Match.Rules Teams=auto|1v1|2v2|practice ShipLives=1..9 Swarm=0..4 TimeLimit=0..60 FF=0|1 GrappleShips=0|1 LaneAssist=0|1 - changes the rules live (server). Teams takes effect at the next restart; TimeLimit restarts the clock from now."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			AMyGameMode* GameMode = CheckServer(World, TEXT("Aura.Match.Rules")) ? GetMatchGameMode(World, TEXT("Aura.Match.Rules")) : nullptr;

			if (!GameMode)
			{
				return;
			}

			if (Args.IsEmpty())
			{
				UE_LOG(LogMatch, Log, TEXT("Aura.Match.Rules: %s (next restart: Teams=%s)"), *RulesText(GameMode->GetMatchRules()), TeamModeName(GameMode->GetNextTeamMode()));
				return;
			}

			FString Options;

			for (const FString& Arg : Args)
			{
				Options += TEXT("?") + Arg;
			}

			FMyMatchRules Rules = GameMode->GetMatchRules();
			Rules.TeamMode = GameMode->GetNextTeamMode();
			const int32 OldTimeLimit = Rules.TimeLimitMinutes;
			AMyGameMode::ParseRulesOptions(Options, Rules, TEXT("Aura.Match.Rules"));

			// The lobby: the widget's route, so the console gets the same refusals (SPEC_B_LOBBY 4.6), Max Players kept
			const AMyGameState* LobbyState = World->GetGameState<AMyGameState>();

			if (LobbyState && LobbyState->GetMatchPhase() == EMyMatchPhase::Lobby)
			{
				FText Why;

				if (!GameMode->ApplyLobbyRules(Rules, GameMode->GetLobbyMaxPlayers(), Why))
				{
					UE_LOG(LogMatch, Warning, TEXT("Aura.Match.Rules: refused in the lobby: %s"), *Why.ToString());
					return;
				}

				UE_LOG(LogMatch, Log, TEXT("Aura.Match.Rules: %s (the lobby, max players %d)"), *RulesText(GameMode->GetMatchRules()), GameMode->GetLobbyMaxPlayers());
				return;
			}

			GameMode->ApplyRules(Rules);

			// Given and unchanged: the clock still runs again from now (ApplyRules restarts it only on a change)
			if (Options.Contains(TEXT("TimeLimit="), ESearchCase::IgnoreCase) && OldTimeLimit == GameMode->GetMatchRules().TimeLimitMinutes)
			{
				GameMode->RestartTimeLimit();
			}

			UE_LOG(LogMatch, Log, TEXT("Aura.Match.Rules: %s (next restart: Teams=%s)"), *RulesText(GameMode->GetMatchRules()), TeamModeName(GameMode->GetNextTeamMode()));
		})
	);

	FAutoConsoleCommandWithWorldAndArgs GSetCommand(
		TEXT("Aura.Match.Set"),
		TEXT("Aura.Match.Set <Name> <Value> - sets a UMyMatchSettings value (Project Settings > Game > Match) on this machine: Name, Struct.Field (DefaultRules.SwarmDifficulty), Array[i] (TeamLaneSide[1], SwarmDifficulties[0].Count). Lane geometry needs Aura.Lane.Rebuild; DefaultRules and the on/off apply at the next map load."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (Args.Num() < 2)
			{
				UE_LOG(LogMatch, Warning, TEXT("Usage: Aura.Match.Set <Name> <Value>"));
				return;
			}

			UMyMatchSettings* Settings = GetMutableDefault<UMyMatchSettings>();
			FProperty* Property = nullptr;
			void* Value = nullptr;

			if (!ResolvePath(Settings->GetClass(), Settings, Args[0], Property, Value))
			{
				UE_LOG(LogMatch, Warning, TEXT("Aura.Match.Set: UMyMatchSettings has no %s"), *Args[0]);
				return;
			}

			const FString Text = JoinArgs(Args, 1);

			if (!Property->ImportText_Direct(*Text, Value, Settings, PPF_None))
			{
				UE_LOG(LogMatch, Warning, TEXT("Aura.Match.Set: '%s' is not a valid %s"), *Text, *Property->GetCPPType());
				return;
			}

			UE_LOG(LogMatch, Log, TEXT("Aura.Match.Set: %s = %s (this machine)"), *Args[0], *ExportValue(Property, Value, Settings));
		})
	);

	FAutoConsoleCommandWithWorldAndArgs GGetCommand(
		TEXT("Aura.Match.Get"),
		TEXT("Aura.Match.Get <Name> - prints a UMyMatchSettings value on this machine (the names of Aura.Match.Set)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (Args.Num() < 1)
			{
				UE_LOG(LogMatch, Warning, TEXT("Usage: Aura.Match.Get <Name>"));
				return;
			}

			UMyMatchSettings* Settings = GetMutableDefault<UMyMatchSettings>();
			FProperty* Property = nullptr;
			void* Value = nullptr;

			if (!ResolvePath(Settings->GetClass(), Settings, Args[0], Property, Value))
			{
				UE_LOG(LogMatch, Warning, TEXT("Aura.Match.Get: UMyMatchSettings has no %s"), *Args[0]);
				return;
			}

			UE_LOG(LogMatch, Log, TEXT("Aura.Match.Get: %s = %s"), *Args[0], *ExportValue(Property, Value, Settings));
		})
	);

	FAutoConsoleCommandWithWorldAndArgs GStartCommand(
		TEXT("Aura.Match.Start"),
		TEXT("Aura.Match.Start - server: waiting for players -> the countdown starts with whoever is in (the pause menu's Start match); during the countdown -> it ends now."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			AMyGameMode* GameMode = CheckServer(World, TEXT("Aura.Match.Start")) ? GetMatchGameMode(World, TEXT("Aura.Match.Start")) : nullptr;
			const AMyGameState* GameState = World ? World->GetGameState<AMyGameState>() : nullptr;

			if (!GameMode || !GameState)
			{
				return;
			}

			// The lobby: Aura.Lobby.Start (soft blocks ignored)
			if (GameState->GetMatchPhase() == EMyMatchPhase::WaitingToStart || GameState->GetMatchPhase() == EMyMatchPhase::Lobby)
			{
				GameMode->RequestStartMatch();
			}
			else if (GameState->GetMatchPhase() == EMyMatchPhase::Countdown)
			{
				GameMode->StartMatchNow();
			}
			else
			{
				UE_LOG(LogMatch, Log, TEXT("Aura.Match.Start: phase %s, nothing to start"), PhaseName(GameState->GetMatchPhase()));
			}
		})
	);

	FAutoConsoleCommandWithWorldAndArgs GEndCommand(
		TEXT("Aura.Match.End"),
		TEXT("Aura.Match.End <Team or -1> - server: ends the match now, that team wins (-1 = a draw), reason Host."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			AMyGameMode* GameMode = CheckServer(World, TEXT("Aura.Match.End")) ? GetMatchGameMode(World, TEXT("Aura.Match.End")) : nullptr;

			if (!GameMode)
			{
				return;
			}

			const int32 Team = Args.Num() > 0 && Args[0].IsNumeric() ? FCString::Atoi(*Args[0]) : -1;

			if (Team >= 0 && Team < MyMatch::NumTeams)
			{
				GameMode->EndMatch(EMyMatchResult::TeamWon, static_cast<uint8>(Team), EMyMatchEndReason::Host);
			}
			else
			{
				GameMode->EndMatch(EMyMatchResult::Draw, MyMatch::NoTeam, EMyMatchEndReason::Host);
			}
		})
	);

	FAutoConsoleCommandWithWorldAndArgs GRestartCommand(
		TEXT("Aura.Match.Restart"),
		TEXT("Aura.Match.Restart - server: remembers the teams and reloads the map with the current rules (the pause menu's Restart match)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (AMyGameMode* GameMode = CheckServer(World, TEXT("Aura.Match.Restart")) ? GetMatchGameMode(World, TEXT("Aura.Match.Restart")) : nullptr)
			{
				GameMode->RestartMatch();
			}
		})
	);

	FAutoConsoleCommandWithWorldAndArgs GTeamCommand(
		TEXT("Aura.Match.Team"),
		TEXT("Aura.Match.Team <PlayerIndex> <0|1> - server: moves a player (0 = the host, the Aura.Airship.* order) to a team; off the other team's helm or gun first."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			AMyGameMode* GameMode = CheckServer(World, TEXT("Aura.Match.Team")) ? GetMatchGameMode(World, TEXT("Aura.Match.Team")) : nullptr;
			uint8 Team = MyMatch::NoTeam;

			if (!GameMode || Args.Num() < 2 || !Args[0].IsNumeric() || !ParseTeam(Args, 1, Team, TEXT("Aura.Match.Team")))
			{
				UE_LOG(LogMatch, Warning, TEXT("Usage: Aura.Match.Team <PlayerIndex> <0|1>"));
				return;
			}

			const APlayerController* PC = GetPlayerController(World, FCString::Atoi(*Args[0]));
			AMyPlayerState* PlayerState = PC ? PC->GetPlayerState<AMyPlayerState>() : nullptr;

			if (!PlayerState)
			{
				UE_LOG(LogMatch, Warning, TEXT("Aura.Match.Team: no player %s"), *Args[0]);
				return;
			}

			GameMode->SetPlayerTeam(PlayerState, Team);
		})
	);

	FAutoConsoleCommandWithWorldAndArgs GShipLivesCommand(
		TEXT("Aura.Match.ShipLives"),
		TEXT("Aura.Match.ShipLives <Team> <N> - server: the team may lose N ships in all; lives left = max(N - ships lost, ship alive ? 1 : 0); 0 with a dead ship eliminates it."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			AMyGameMode* GameMode = CheckServer(World, TEXT("Aura.Match.ShipLives")) ? GetMatchGameMode(World, TEXT("Aura.Match.ShipLives")) : nullptr;
			uint8 Team = MyMatch::NoTeam;

			if (!GameMode || !ParseTeam(Args, 0, Team, TEXT("Aura.Match.ShipLives")) || Args.Num() < 2 || !Args[1].IsNumeric())
			{
				UE_LOG(LogMatch, Warning, TEXT("Usage: Aura.Match.ShipLives <Team> <N>"));
				return;
			}

			GameMode->SetTeamShipLives(Team, FCString::Atoi(*Args[1]));
		})
	);

	FAutoConsoleCommandWithWorldAndArgs GKillShipCommand(
		TEXT("Aura.Match.KillShip"),
		TEXT("Aura.Match.KillShip <Team> - server: that team's ship dies now (DebugKill: health set directly, so spawn protection doesn't stop it; no crew share, the crew is ejected alive)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			uint8 Team = MyMatch::NoTeam;

			if (!CheckServer(World, TEXT("Aura.Match.KillShip")) || !GetMatchGameMode(World, TEXT("Aura.Match.KillShip")) || !ParseTeam(Args, 0, Team, TEXT("Aura.Match.KillShip")))
			{
				return;
			}

			if (AAirshipPawn* Ship = GetTeamShip(World, Team, TEXT("Aura.Match.KillShip")))
			{
				UE_LOG(LogMatch, Log, TEXT("Aura.Match.KillShip: %s (%s)"), *Ship->GetName(), *UMyTeamLibrary::GetTeamName(Team).ToString());
				Ship->DebugKill();
			}
		})
	);

	FAutoConsoleCommandWithWorldAndArgs GDamageShipCommand(
		TEXT("Aura.Match.DamageShip"),
		TEXT("Aura.Match.DamageShip <Team> <Amount> - server: that team's ship takes Amount through its own damage path (ApplyShipDamage: spawn protection and the crew share apply, no instigator)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			uint8 Team = MyMatch::NoTeam;

			if (!CheckServer(World, TEXT("Aura.Match.DamageShip")) || !GetMatchGameMode(World, TEXT("Aura.Match.DamageShip")) || !ParseTeam(Args, 0, Team, TEXT("Aura.Match.DamageShip")))
			{
				return;
			}

			const float Amount = Args.Num() > 1 ? FCString::Atof(*Args[1]) : 100.f;

			if (AAirshipPawn* Ship = GetTeamShip(World, Team, TEXT("Aura.Match.DamageShip")))
			{
				UE_LOG(LogMatch, Log, TEXT("Aura.Match.DamageShip: %s takes %.0f%s"), *Ship->GetName(), Amount, Ship->IsSpawnProtected() ? TEXT(" (spawn protected)") : TEXT(""));
				Ship->ApplyShipDamage(Amount);
			}
		})
	);

	FAutoConsoleCommandWithWorldAndArgs GSwarmCommand(
		TEXT("Aura.Match.Swarm"),
		TEXT("Aura.Match.Swarm <0-4> - server: the swarm difficulty now (0 Easy, 1 Normal, 2 Hard, 3 Very Hard, 4 Nightmare). Sentinels already alive keep their stats."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			AMyGameMode* GameMode = CheckServer(World, TEXT("Aura.Match.Swarm")) ? GetMatchGameMode(World, TEXT("Aura.Match.Swarm")) : nullptr;

			if (!GameMode || Args.Num() < 1 || !Args[0].IsNumeric())
			{
				UE_LOG(LogMatch, Warning, TEXT("Usage: Aura.Match.Swarm <0-4>"));
				return;
			}

			FMyMatchRules Rules = GameMode->GetMatchRules();
			Rules.TeamMode = GameMode->GetNextTeamMode();
			Rules.SwarmDifficulty = FCString::Atoi(*Args[0]);
			GameMode->ApplyRules(Rules);
		})
	);

	FAutoConsoleCommandWithWorldAndArgs GRecallCommand(
		TEXT("Aura.Match.Recall"),
		TEXT("Aura.Match.Recall <Team> - server: that team's ship starts flying back to its lane now (it must be unpiloted and outside its lane)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			uint8 Team = MyMatch::NoTeam;

			if (!CheckServer(World, TEXT("Aura.Match.Recall")) || !GetMatchGameMode(World, TEXT("Aura.Match.Recall")) || !ParseTeam(Args, 0, Team, TEXT("Aura.Match.Recall")))
			{
				return;
			}

			AAirshipPawn* Ship = GetTeamShip(World, Team, TEXT("Aura.Match.Recall"));
			UAirshipLaneComponent* Lane = Ship ? Ship->GetLane() : nullptr;

			if (Lane)
			{
				const bool bStarted = Lane->StartRecall();
				UE_LOG(LogMatch, Log, TEXT("Aura.Match.Recall: %s %s (lane state %s)"), *Ship->GetName(), bStarted ? TEXT("returns to its lane") : TEXT("can't recall now"),
					UAirshipLaneComponent::GetLaneStateName(Lane->GetLaneState()));
			}
		})
	);

	FAutoConsoleCommandWithWorldAndArgs GDumpCommand(
		TEXT("Aura.Match.Dump"),
		TEXT("Aura.Match.Dump [path] - server: writes the match state as JSON (default Saved/Match/match_state.json): phase, rules, result, teams, ships (lane state, errors, target), players (team, pawn, ship-borne, u, health), the path and cruise end."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (!CheckServer(World, TEXT("Aura.Match.Dump")))
			{
				return;
			}

			const FString Path = Args.Num() > 0 ? JoinArgs(Args, 0) : FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("Match"), TEXT("match_state.json"));
			IFileManager::Get().MakeDirectory(*FPaths::GetPath(Path), true);

			if (FFileHelper::SaveStringToFile(BuildDump(World), *Path, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM))
			{
				UE_LOG(LogMatch, Log, TEXT("Aura.Match.Dump: %s"), *FPaths::ConvertRelativePathToFull(Path));
			}
			else
			{
				UE_LOG(LogMatch, Warning, TEXT("Aura.Match.Dump: couldn't write %s"), *Path);
			}
		})
	);
}
#endif
