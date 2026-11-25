// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "MyMatchTypes.generated.h"

class AAirshipPawn;

/**
 * Team match (round 2 PR B, Docs/Airship/round2/SPEC_B.md): two teams, one ship per team on a lane beside the platform
 * field, ship lives, match rules. Shared types for the match, lanes, airship, combat, grapple and menu code.
 * The server decides everything; clients only display what replicates.
 */

/** Every match state change logs one line here (the PIE harnesses scan it). Defined in MyTeamLibrary.cpp. */
DECLARE_LOG_CATEGORY_EXTERN(LogMatch, Log, All);

namespace MyMatch
{
	/** Free ships and every actor while no match runs: never a teammate of anything. */
	constexpr uint8 NoTeam = 255;
	constexpr int32 NumTeams = 2;

	/** Swarm difficulties: the host menu's DifficultyNames (Easy .. Nightmare), UMyMatchSettings::SwarmDifficulties. */
	constexpr int32 NumDifficulties = 5;
}

/** Replicated on AMyGameState. None = no match (map not in MatchMaps, or Aura.Match.Enable 0): nothing of PR B shows. */
UENUM(BlueprintType)
enum class EMyMatchPhase : uint8
{
	None,
	/** Versus only: no pawns until the expected players are in or the host starts the match. */
	WaitingToStart,
	Countdown,
	InProgress,
	Ended
};

/** Rules.TeamMode. Auto: balanced teams from the player count (1 player = practice). */
UENUM(BlueprintType)
enum class EMyTeamMode : uint8
{
	Auto,
	/** Everyone on team 0, one ship, no opponent. */
	Practice,
	OneVsOne,
	TwoVsTwo
};

UENUM(BlueprintType)
enum class EMyMatchResult : uint8
{
	None,
	TeamWon,
	Draw,
	/** Co-op practice lost its last ship. */
	PracticeOver
};

UENUM(BlueprintType)
enum class EMyMatchEndReason : uint8
{
	None,
	/** A team lost its last ship life. */
	Eliminated,
	/** A team stayed empty for TeamEmptyForfeitSeconds. */
	Forfeit,
	/** Rules.TimeLimitMinutes ran out: the tie-break decided. */
	TimeLimit,
	/** Aura.Match.End. */
	Host
};

/** AMyGameState::MulticastMatchEvent: HUD toasts and harness log lines. Value depends on the event (lives left, seconds). */
UENUM(BlueprintType)
enum class EMyMatchEvent : uint8
{
	Countdown,
	Started,
	ShipDestroyed,
	ShipRespawned,
	TeamEliminated,
	ForfeitWarning,
	Forfeited,
	PracticeToVersus,
	Ended,
	ShipUnderAttack,
	ShipReturning,
	TimeWarning
};

/** A team ship's lane state (UAirshipLaneComponent, server, replicated). Free ships stay NoLane. */
UENUM(BlueprintType)
enum class EMyLaneState : uint8
{
	/** Free ship, match off, no lane source, or the ship is dead: PR A behaviour. */
	NoLane,
	/** Unpiloted, follows the lane, target moving. */
	Cruising,
	/** Unpiloted, follows the lane, target stopped (team behind, path end, blocked, match not started / over). */
	Waiting,
	/** A pilot at the helm with his drive keys untouched, in the lane zone: the lane flies, he aims and fires. */
	Assist,
	/** A pilot flies, inside the lane zone. */
	PilotedInLane,
	/** A pilot flies, outside the lane zone. */
	OutOfLane,
	/** Unpiloted, not following the lane (left outside it, or still too fast): PR A drift / hold / coast. */
	Parked,
	/** Unpiloted, flying itself back to its own lane (recall). */
	Returning
};

/** What limits a lane target this frame (FMyLaneHint::Clamp, the pilot panel and Aura.Lane.Status). */
UENUM(BlueprintType)
enum class EMyLaneClamp : uint8
{
	None,
	/** At the team front + LaneMaxLead. */
	TeamPace,
	/** At CruiseEndU (the built path's end - LaneEndMargin). */
	PathEnd,
	/** The look-ahead found something in the lane. */
	Blocked,
	NotStarted,
	Ended,
	/** Going round a blocker, LaneBypassOffset further out. */
	Bypass,
	/** Speed frozen while someone reels in with the ship hook. */
	Reel
};

/** The host's match rules. Replicated on AMyGameState; defaults in UMyMatchSettings::DefaultRules. */
USTRUCT(BlueprintType)
struct AURA_API FMyMatchRules
{
	GENERATED_BODY()

	/** Takes effect at the next restart when changed live. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Match")
	EMyTeamMode TeamMode = EMyTeamMode::Auto;

	/** Ships a team may lose (the first one included). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Match", meta = (ClampMin = "1", ClampMax = "9"))
	int32 ShipLives = 3;

	/** Index into UMyMatchSettings::SwarmDifficulties (the menu's DifficultyNames). 1 = Normal = today's game. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Match", meta = (ClampMin = "0", ClampMax = "4"))
	int32 SwarmDifficulty = 1;

	/** Versus only. 0 = none. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Match", meta = (ClampMin = "0", ClampMax = "60"))
	int32 TimeLimitMinutes = 15;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Match")
	bool bFriendlyFire = false;

	/** The grapple can reel a player onto his own team's ship. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Match")
	bool bGrappleShips = true;

	/** A pilot who boards a cruising ship and leaves the drive keys alone lets the lane fly it. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Match")
	bool bLaneAssist = true;
};

/** One team (AMyGameState::Teams, 2 entries, replicated). */
USTRUCT(BlueprintType)
struct AURA_API FMyTeamState
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly, Category = "Match")
	uint8 TeamId = MyMatch::NoTeam;

	/** Decided at the countdown's start and end, from NumPlayers > 0. */
	UPROPERTY(BlueprintReadOnly, Category = "Match")
	bool bActive = false;

	UPROPERTY(BlueprintReadOnly, Category = "Match")
	int32 NumPlayers = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Match")
	int32 LivesLeft = 0;

	/** Smaller team handicap: one extra ship life per missing player. */
	UPROPERTY(BlueprintReadOnly, Category = "Match")
	int32 BonusLives = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Match")
	int32 ShipsLost = 0;

	/** +1 right of the start heading, -1 left, 0 none; swaps every round with bAlternateSides. Not BlueprintReadOnly: Blueprint has no int8. */
	UPROPERTY()
	int8 LaneSide = 0;

	/** 0..100, written at most 4 times a second. */
	UPROPERTY(BlueprintReadOnly, Category = "Match")
	uint8 ShipHealthPct = 0;

	/** Null while dead or respawning. */
	UPROPERTY(BlueprintReadOnly, Category = "Match")
	TObjectPtr<AAirshipPawn> Ship;

	/** 0 = no respawn pending. */
	UPROPERTY(BlueprintReadOnly, Category = "Match")
	double ShipRespawnServerTime = 0.0;

	/** 0 = has players. */
	UPROPERTY(BlueprintReadOnly, Category = "Match")
	double EmptySinceServerTime = 0.0;

	/** Server rate limit of the ShipUnderAttack event; clients don't need it. */
	UPROPERTY(NotReplicated, BlueprintReadOnly, Category = "Match")
	double LastUnderAttackServerTime = 0.0;

	UPROPERTY(BlueprintReadOnly, Category = "Match")
	bool bEliminated = false;
};

/**
 * One swarm difficulty (UMyMatchSettings::SwarmDifficulties, index = Rules.SwarmDifficulty). Multipliers stack on the
 * wave curves; 1 / 0 everywhere = today's game. Count is multiplied by the player-count factor too.
 */
USTRUCT(BlueprintType)
struct AURA_API FMySwarmDifficultyPreset
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, Category = "Difficulty")
	FName Name;

	/** Sentinels per wave. */
	UPROPERTY(EditAnywhere, Category = "Difficulty", meta = (ClampMin = "0.0"))
	float Count = 1.f;

	UPROPERTY(EditAnywhere, Category = "Difficulty", meta = (ClampMin = "0.0"))
	float Health = 1.f;

	UPROPERTY(EditAnywhere, Category = "Difficulty", meta = (ClampMin = "0.0"))
	float Armor = 1.f;

	UPROPERTY(EditAnywhere, Category = "Difficulty", meta = (ClampMin = "0.0"))
	float Damage = 1.f;

	UPROPERTY(EditAnywhere, Category = "Difficulty", meta = (ClampMin = "0.0"))
	float AttackSpeed = 1.f;

	UPROPERTY(EditAnywhere, Category = "Difficulty", meta = (ClampMin = "0.0"))
	float MoveSpeed = 1.f;

	/** The wave's SelfBuffChanceMultiplier only (it already multiplies the rules asset's chance). */
	UPROPERTY(EditAnywhere, Category = "Difficulty", meta = (ClampMin = "0.0"))
	float SelfBuffChance = 1.f;

	/** The wave spawner's own MaxAlive cap. */
	UPROPERTY(EditAnywhere, Category = "Difficulty", meta = (ClampMin = "0.0"))
	float MaxAlive = 1.f;

	/** 0 = the swarm rules asset's. */
	UPROPERTY(EditAnywhere, Category = "Difficulty", meta = (ClampMin = "0"))
	int32 MaxAttackersPerPlayer = 0;

	/** Multiplies UBurrowerSettings::SpawnInterval. */
	UPROPERTY(EditAnywhere, Category = "Difficulty", meta = (ClampMin = "0.0"))
	float BurrowerSpawnIntervalScale = 1.f;

	/** At least this many per player: raises UBurrowerSettings::MaxAlivePerPlayer, never lowers it. 0 = the setting's. */
	UPROPERTY(EditAnywhere, Category = "Difficulty", meta = (ClampMin = "0"))
	int32 BurrowerMaxAlivePerPlayer = 0;

	/** Level of the Burrower's attribute effects. */
	UPROPERTY(EditAnywhere, Category = "Difficulty", meta = (ClampMin = "1"))
	int32 BurrowerLevel = 1;
};

/**
 * What a team ship's lane looks like from the ship (UAirshipLaneComponent, replicated at most every LaneHintInterval):
 * the lane geometry lives on the server only, the pilot panel and the HUD read this. About 11 bytes.
 */
USTRUCT(BlueprintType)
struct AURA_API FMyLaneHint
{
	GENERATED_BODY()

	/** Ship minus lane, decimetres, + = toward the start heading's right. */
	UPROPERTY()
	int16 LateralDm = 0;

	UPROPERTY()
	int16 VerticalDm = 0;

	/** u (progress along the start heading), decimetres. */
	UPROPERTY()
	int32 ProgressDm = 0;

	/** Lane tangent yaw at the ship, 0.1 deg. */
	UPROPERTY()
	int16 LaneYawDeg10 = 0;

	/** EMyLaneClamp. */
	UPROPERTY()
	uint8 Clamp = 0;
};
