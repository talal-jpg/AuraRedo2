// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Engine/DeveloperSettings.h"
#include "Match/MyMatchTypes.h"
#include "MyMatchSettings.generated.h"

/**
 * Team match settings: Project Settings > Game > Match, saved to DefaultGame.ini ([/Script/Aura.MyMatchSettings]).
 * Everything has a C++ default (Docs/Airship/round2/SPEC_B.md Appendix A), so nothing has to be saved. Aura.Match.Set /
 * Aura.Match.Get change a value on one machine for tests.
 *
 * Units: cm, s, cm/s. "x S" = multiplied by the path spawner's layout scale (HexRadius / 100) where it is used.
 */
UCLASS(Config = Game, DefaultConfig, meta = (DisplayName = "Match"))
class AURA_API UMyMatchSettings : public UDeveloperSettings
{
	GENERATED_BODY()

public:

	UMyMatchSettings()
	{
		MatchMaps.Add(TEXT("StartupMap"));

		// Round 0: team 0 right of the start heading, team 1 left (swapped on odd versus rounds with bAlternateSides)
		TeamLaneSide[0] = 1;
		TeamLaneSide[1] = -1;

		TeamColors[0] = FLinearColor(0.25f, 0.66f, 0.96f);
		TeamColors[1] = FLinearColor(0.96f, 0.54f, 0.25f);
		TeamNames[0] = NSLOCTEXT("MyMatch", "TeamBlue", "BLUE");
		TeamNames[1] = NSLOCTEXT("MyMatch", "TeamOrange", "ORANGE");

		// Index = Rules.SwarmDifficulty = the host menu's DifficultyNames. Normal is exactly today's game. First guesses (SPEC_B Q13).
		auto Preset = [](const TCHAR* Name, float Count, float Health, float Armor, float Damage, float AttackSpeed, float MoveSpeed,
			float SelfBuffChance, float MaxAlive, int32 MaxAttackers, float BurrowerInterval, int32 BurrowerMaxAlive, int32 BurrowerLevel)
		{
			FMySwarmDifficultyPreset Result;
			Result.Name = FName(Name);
			Result.Count = Count;
			Result.Health = Health;
			Result.Armor = Armor;
			Result.Damage = Damage;
			Result.AttackSpeed = AttackSpeed;
			Result.MoveSpeed = MoveSpeed;
			Result.SelfBuffChance = SelfBuffChance;
			Result.MaxAlive = MaxAlive;
			Result.MaxAttackersPerPlayer = MaxAttackers;
			Result.BurrowerSpawnIntervalScale = BurrowerInterval;
			Result.BurrowerMaxAlivePerPlayer = BurrowerMaxAlive;
			Result.BurrowerLevel = BurrowerLevel;
			return Result;
		};

		//                                   Count Health Armor Damage AtkSpd MoveSpd SelfBuff MaxAlive Attackers BurInterval BurMax BurLevel
		SwarmDifficulties.Add(Preset(TEXT("Easy"),      0.6f, 0.7f, 0.75f, 0.6f, 0.85f, 0.9f,  0.5f,  0.6f,  6, 1.5f,  0, 1));
		SwarmDifficulties.Add(Preset(TEXT("Normal"),    1.0f, 1.0f, 1.0f,  1.0f, 1.0f,  1.0f,  1.0f,  1.0f,  0, 1.0f,  0, 1));
		SwarmDifficulties.Add(Preset(TEXT("Hard"),      1.3f, 1.3f, 1.15f, 1.3f, 1.1f,  1.05f, 1.25f, 1.2f, 12, 0.8f,  0, 2));
		SwarmDifficulties.Add(Preset(TEXT("Very Hard"), 1.6f, 1.6f, 1.3f,  1.6f, 1.2f,  1.1f,  1.5f,  1.4f, 14, 0.65f, 2, 3));
		SwarmDifficulties.Add(Preset(TEXT("Nightmare"), 2.0f, 2.0f, 1.5f,  2.0f, 1.3f,  1.15f, 2.0f,  1.6f, 16, 0.5f,  2, 4));
	}

	static const UMyMatchSettings* Get() { return GetDefault<UMyMatchSettings>(); }

	/** The preset for a Rules.SwarmDifficulty, clamped into the list; all 1 (today's game) when the list is empty. */
	const FMySwarmDifficultyPreset& GetSwarmDifficulty(int32 Difficulty) const
	{
		static const FMySwarmDifficultyPreset Neutral;
		return SwarmDifficulties.Num() > 0 ? SwarmDifficulties[FMath::Clamp(Difficulty, 0, SwarmDifficulties.Num() - 1)] : Neutral;
	}

	/** TeamLaneSide of TeamId on round 0 as +1 (right) or -1 (left); 0 for no team. */
	int8 GetBaseLaneSide(uint8 TeamId) const
	{
		return TeamId < MyMatch::NumTeams ? (TeamLaneSide[TeamId] < 0 ? -1 : 1) : 0;
	}

	// -------------------------------------------------------------------------
	// Match
	// -------------------------------------------------------------------------

	/** Map names (no path, no PIE prefix, e.g. StartupMap) that run a match. Empty = every map with AMyGameMode. CVar Aura.Match.Enable and the URL's Match=0|1 win. */
	UPROPERTY(Config, EditAnywhere, Category = "Match")
	TArray<FString> MatchMaps;

	/** Rules before the command line (-MatchTeams= ...) and the URL options (Teams, ShipLives, Swarm, ...). */
	UPROPERTY(Config, EditAnywhere, Category = "Match")
	FMyMatchRules DefaultRules;

	/** The countdown (s). */
	UPROPERTY(Config, EditAnywhere, Category = "Match", meta = (ClampMin = "0.0"))
	float MatchStartDelay = 5.f;

	/** Auto on a listen server without a Players URL option (listen PIE, a console-opened listen game): versus waits for this many. 1 = such a game starts as practice at once (one-player listen PIE doesn't wait for a second player), and a player who joins turns it into versus. */
	UPROPERTY(Config, EditAnywhere, Category = "Match", meta = (ClampMin = "1"))
	int32 DefaultExpectedPlayers = 2;

	/** Auto teams: at most this many players per team, a join is refused when both are full (SPEC_B Q7). 0 = no cap: more than 4 players keep balancing (3v2, 3v3). */
	UPROPERTY(Config, EditAnywhere, Category = "Match", meta = (ClampMin = "0"))
	int32 AutoMaxPlayersPerTeam = 0;

	/** Auto teams with exactly this many expected players (the URL's Players, the host menu's Max Players) play co-op practice, everyone on one ship, instead of versus. 3 = Q19's alternative to 2v1. 0 = never. */
	UPROPERTY(Config, EditAnywhere, Category = "Match", meta = (ClampMin = "0"))
	int32 AutoCoopPlayers = 0;

	/** Each team starts on its own ship's deck (the only per-round fair start without a map change). Practice too: on team 0's ship (SPEC_B_LOBBY D10), so the match never needs the start floor. */
	UPROPERTY(Config, EditAnywhere, Category = "Match")
	bool bStartAboard = true;

	/** Respawned players go to their team ship's deck instead of past the lead on their own side. */
	UPROPERTY(Config, EditAnywhere, Category = "Match")
	bool bRespawnAboard = false;

	/** Lane sides swap every versus round, so the start floor's side alternates between the teams. A practice round keeps round 0's sides (its lone ship stays near the floor). */
	UPROPERTY(Config, EditAnywhere, Category = "Match")
	bool bAlternateSides = true;

	/** The smaller team gets one extra ship life per missing player (capped at 9). */
	UPROPERTY(Config, EditAnywhere, Category = "Match")
	bool bSmallTeamHandicap = true;

	/** The time limit's tie-break counts the handicap's extra lives too. Off: ship lives left without them (= fewer ships lost), so the handicap helps in fights but doesn't win a match nobody fought. */
	UPROPERTY(Config, EditAnywhere, Category = "Match")
	bool bTimeLimitCountsHandicap = false;

	/** The ship hook also works with the match off (free ships on any map). Off: outside a match the grapple is exactly PR A's (a ship is a pawn, never an anchor). */
	UPROPERTY(Config, EditAnywhere, Category = "Match")
	bool bShipHookOutsideMatch = false;

	/** Solo practice (one team, one player) doesn't count lives: every lost ship comes back. */
	UPROPERTY(Config, EditAnywhere, Category = "Match")
	bool bSoloPracticeUnlimitedShips = true;

	/** Seconds from a ship's death to its team's next ship (the wreck is well below the lane by then). */
	UPROPERTY(Config, EditAnywhere, Category = "Match", meta = (ClampMin = "0.0"))
	float ShipRespawnDelay = 10.f;

	/** A new ship takes no damage until its team first boards or mans it, or for this long (s). 0 = off. */
	UPROPERTY(Config, EditAnywhere, Category = "Match", meta = (ClampMin = "0.0"))
	float ShipSpawnProtection = 15.f;

	/** A respawning ship moves back along its lane until the enemy ship is at least this far (cm, just over cannon and turret range). */
	UPROPERTY(Config, EditAnywhere, Category = "Match", meta = (ClampMin = "0.0"))
	float ShipSpawnMinEnemyDistance = 25000.f;

	/** A team empty this long while the other one plays forfeits (s). 0 = never. */
	UPROPERTY(Config, EditAnywhere, Category = "Match", meta = (ClampMin = "0.0"))
	float TeamEmptyForfeitSeconds = 30.f;

	/** The end screen's time before the automatic restart (s). 0 = no automatic restart. */
	UPROPERTY(Config, EditAnywhere, Category = "Match", meta = (ClampMin = "0.0"))
	float EndScreenSeconds = 20.f;

	/** Ships placed in the map without a ShipTeam<id> tag are destroyed when a 2-team match starts (kept free in practice). */
	UPROPERTY(Config, EditAnywhere, Category = "Match")
	bool bDestroyUntaggedPlacedShipsInVersus = true;

	/** On-foot players this far (cm) below the lane / path height die. 0 = off. */
	UPROPERTY(Config, EditAnywhere, Category = "Match", meta = (ClampMin = "0.0"))
	float FallDeathDepth = 8000.f;

	/** ... and only after falling with no base for this long (s). */
	UPROPERTY(Config, EditAnywhere, Category = "Match", meta = (ClampMin = "0.0"))
	float FallDeathMinFallTime = 1.f;

	/** On: sentinel bullets damage team ships nobody drives (PR A behaviour). Off: only a driven ship is hit, as it is targeted. */
	UPROPERTY(Config, EditAnywhere, Category = "Match")
	bool bSentinelBulletsHitUndrivenShips = false;

	/** Character gun damage per hit on a team ship or its turret, instead of GE_GunShootDamage's value. 0 = the GE value. */
	UPROPERTY(Config, EditAnywhere, Category = "Match", meta = (ClampMin = "0.0"))
	float ShipDamageGunHit = 5.f;

	/** Turret round damage on a team ship or its turret, instead of the turret's bullet damage. 0 = the turret's. */
	UPROPERTY(Config, EditAnywhere, Category = "Match", meta = (ClampMin = "0.0"))
	float ShipDamageTurretRound = 4.f;

	/** Seconds between ShipUnderAttack events per team. */
	UPROPERTY(Config, EditAnywhere, Category = "Match", meta = (ClampMin = "0.0"))
	float ShipUnderAttackInterval = 5.f;

	/** Net cull distance (cm) of player characters while the match is on: covers the lane separation (engine default 150 m). */
	UPROPERTY(Config, EditAnywhere, Category = "Match", meta = (ClampMin = "0.0"))
	float MatchNetCullDistance = 60000.f;

	/** Lane side per team on round 0: +1 right of the start heading, -1 left. Read through GetBaseLaneSide. */
	UPROPERTY(Config, EditAnywhere, Category = "Match", meta = (ClampMin = "-1", ClampMax = "1"))
	int32 TeamLaneSide[MyMatch::NumTeams];

	/** HUD only (markers, name tags, the match bar), linear. */
	UPROPERTY(Config, EditAnywhere, Category = "Match")
	FLinearColor TeamColors[MyMatch::NumTeams];

	UPROPERTY(Config, EditAnywhere, Category = "Match")
	FText TeamNames[MyMatch::NumTeams];

	// -------------------------------------------------------------------------
	// Lobby (Docs/Airship/round2/SPEC_B_LOBBY.md Appendix L-A): the in-level lobby on the match map
	// -------------------------------------------------------------------------

	/** The main menu's Host Game travels with ?Lobby=1: the hosted game starts in the lobby. */
	UPROPERTY(Config, EditAnywhere, Category = "Lobby")
	bool bLobbyWhenHosting = true;

	/** ReturnToLobby and RestartMatch add ?SeamlessTravel: clients stay connected (a hard travel drops Steam clients). PIE travels hard unless net.AllowPIESeamlessTravel 1. */
	UPROPERTY(Config, EditAnywhere, Category = "Lobby")
	bool bSeamlessTravel = true;

	/** Where the lobby stands. Aura.Lobby.Resolve picks again. */
	UPROPERTY(Config, EditAnywhere, Category = "Lobby")
	EMyLobbySpawn LobbySpawn = EMyLobbySpawn::Auto;

	/** The capsule sweep under each PlayerStart (cm). */
	UPROPERTY(Config, EditAnywhere, Category = "Lobby", meta = (ClampMin = "0.0"))
	float LobbyGroundTraceDepth = 5000.f;

	/** A lobby ground hit must be at least this flat (ImpactNormal.Z). */
	UPROPERTY(Config, EditAnywhere, Category = "Lobby", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float LobbyGroundMinNormalZ = 0.7f;

	/** The lobby zone: the ground's bounds grown by this in X and Y (cm). */
	UPROPERTY(Config, EditAnywhere, Category = "Lobby", meta = (ClampMin = "0.0"))
	float LobbyZoneMargin = 1500.f;

	/** The lobby zone reaches this far above the ground's top (cm). */
	UPROPERTY(Config, EditAnywhere, Category = "Lobby", meta = (ClampMin = "0.0"))
	float LobbyZoneHeight = 6000.f;

	/** ... and this far below it (cm). Without a zone it is the fall catch under the PlayerStart. */
	UPROPERTY(Config, EditAnywhere, Category = "Lobby", meta = (ClampMin = "0.0"))
	float LobbyZoneDepth = 2000.f;

	/** Seconds outside the zone before the teleport back. */
	UPROPERTY(Config, EditAnywhere, Category = "Lobby", meta = (ClampMin = "0.0"))
	float LobbyZoneGraceSeconds = 0.5f;

	/** Seconds from the host's Start to the match (PR B's Countdown phase). */
	UPROPERTY(Config, EditAnywhere, Category = "Lobby", meta = (ClampMin = "0.0"))
	float LobbyCountdownSeconds = 5.f;

	/** Seconds after the lobby began during which players still loading (a seamless return) block the Start. */
	UPROPERTY(Config, EditAnywhere, Category = "Lobby", meta = (ClampMin = "0.0"))
	float LobbyArrivalTimeout = 45.f;

	/** PathStart: seconds to wait for the path's first platform before the PlayerStart (fall catch only) is used. */
	UPROPERTY(Config, EditAnywhere, Category = "Lobby", meta = (ClampMin = "0.0"))
	float LobbyPathStartWait = 10.f;

	/** True = a player who isn't ready blocks the Start. False = shown; the host starts anyway with a second click. */
	UPROPERTY(Config, EditAnywhere, Category = "Lobby")
	bool bLobbyRequireReady = false;

	/** Players may ask to switch team in the lobby. */
	UPROPERTY(Config, EditAnywhere, Category = "Lobby")
	bool bLobbyTeamSwitch = true;

	/** A team mode or Max Players change clears every ready flag (other rules never do). */
	UPROPERTY(Config, EditAnywhere, Category = "Lobby")
	bool bLobbyRulesClearReady = true;

	/** True = damage applies in the lobby. */
	UPROPERTY(Config, EditAnywhere, Category = "Lobby")
	bool bLobbyDamage = false;

	/** Actors with this tag are hidden (no collision) outside the lobby. None carries it today. */
	UPROPERTY(Config, EditAnywhere, Category = "Lobby")
	FName LobbyOnlyActorTag = TEXT("LobbyOnly");

	// -------------------------------------------------------------------------
	// Difficulty
	// -------------------------------------------------------------------------

	/** Index = Rules.SwarmDifficulty (0 Easy .. 4 Nightmare). Read through GetSwarmDifficulty. */
	UPROPERTY(Config, EditAnywhere, Category = "Difficulty")
	TArray<FMySwarmDifficultyPreset> SwarmDifficulties;

	/** Sentinel count factor for N players = min(Base + PerPlayer x N, Max): one wave per path segment is shared by every player. */
	UPROPERTY(Config, EditAnywhere, Category = "Difficulty", meta = (ClampMin = "0.0"))
	float SwarmPlayerCountBase = 0.6f;

	UPROPERTY(Config, EditAnywhere, Category = "Difficulty", meta = (ClampMin = "0.0"))
	float SwarmPlayerCountPerPlayer = 0.4f;

	UPROPERTY(Config, EditAnywhere, Category = "Difficulty", meta = (ClampMin = "0.0"))
	float SwarmPlayerCountMax = 2.2f;

	// -------------------------------------------------------------------------
	// Lanes (geometry; changes need Aura.Lane.Rebuild)
	// -------------------------------------------------------------------------

	/** Lane distance beyond the platform field (cm, not scaled): the hull's half width plus the gap to any platform. */
	UPROPERTY(Config, EditAnywhere, Category = "Lanes", meta = (ClampMin = "0.0"))
	float LaneClearance = 2500.f;

	/** Hull origin above path height (cm, not scaled). */
	UPROPERTY(Config, EditAnywhere, Category = "Lanes")
	float LaneHeight = 200.f;

	/** Path sample and lane value step (cm x S). */
	UPROPERTY(Config, EditAnywhere, Category = "Lanes", meta = (ClampMin = "10.0"))
	float LaneSampleStep = 500.f;

	/** Moving average half window (cm x S); the lane then takes the max with the unsmoothed envelope, so it only moves outward. */
	UPROPERTY(Config, EditAnywhere, Category = "Lanes", meta = (ClampMin = "0.0"))
	float LaneSmoothHalfWindow = 2500.f;

	/** The lane continues straight back along the start heading this far before the path start (cm x S). */
	UPROPERTY(Config, EditAnywhere, Category = "Lanes", meta = (ClampMin = "0.0"))
	float LaneBackReach = 6000.f;

	/** Cruising stops this far short of the built path's end (cm x S): CruiseEndU = PathEndU - LaneEndMargin. */
	UPROPERTY(Config, EditAnywhere, Category = "Lanes", meta = (ClampMin = "0.0"))
	float LaneEndMargin = 5000.f;

	/** u of the match-start ship spawn (cm; 0 = level with the path start). */
	UPROPERTY(Config, EditAnywhere, Category = "Lanes")
	float LaneSpawnU = 0.f;

	/** Spawner MaxYawDeviation (deg) from which the lanes fall back to straight lines (the path could double back). */
	UPROPERTY(Config, EditAnywhere, Category = "Lanes", meta = (ClampMin = "0.0", ClampMax = "90.0"))
	float MaxYawForEnvelope = 80.f;

	/** No path spawner: an actor tagged MatchLaneOrigin gives a straight virtual path of this half width (cm, not scaled) ... */
	UPROPERTY(Config, EditAnywhere, Category = "Lanes", meta = (ClampMin = "0.0"))
	float FallbackLaneHalfWidth = 10000.f;

	/** ... and this length (cm). */
	UPROPERTY(Config, EditAnywhere, Category = "Lanes", meta = (ClampMin = "0.0"))
	float FallbackLaneLength = 150000.f;

	// -------------------------------------------------------------------------
	// Cruise (lane target pace)
	// -------------------------------------------------------------------------

	/** Cruise speed (cm/s), and the floor while the team front is known. */
	UPROPERTY(Config, EditAnywhere, Category = "Cruise", meta = (ClampMin = "0.0"))
	float LaneSpeed = 600.f;

	/** The lane's top speed (cm/s) when catching up with the team. */
	UPROPERTY(Config, EditAnywhere, Category = "Cruise", meta = (ClampMin = "0.0"))
	float LaneCatchUpSpeed = 2800.f;

	/** Proportional pace (1/s) toward a point LanePaceOffset (cm) ahead of the team front. */
	UPROPERTY(Config, EditAnywhere, Category = "Cruise", meta = (ClampMin = "0.0"))
	float LanePaceGain = 0.3f;

	UPROPERTY(Config, EditAnywhere, Category = "Cruise")
	float LanePaceOffset = 1500.f;

	/** The target stays at most this far (cm) ahead of the team front. 0 = no pace limit. */
	UPROPERTY(Config, EditAnywhere, Category = "Cruise", meta = (ClampMin = "0.0"))
	float LaneMaxLead = 4000.f;

	/** Target speed ramp (cm/s^2). */
	UPROPERTY(Config, EditAnywhere, Category = "Cruise", meta = (ClampMin = "1.0"))
	float LaneAccel = 250.f;

	/** The target never runs more than this (cm) ahead of the ship. */
	UPROPERTY(Config, EditAnywhere, Category = "Cruise", meta = (ClampMin = "0.0"))
	float LaneMaxTargetLead = 1500.f;

	/** The target point is at most this far (cm) across the lane from the ship (joins the lane gradually). */
	UPROPERTY(Config, EditAnywhere, Category = "Cruise", meta = (ClampMin = "0.0"))
	float LaneJoinStep = 1000.f;

	/** Lane position law: spring (1/s^2) and damper (1/s), capped at LaneAccelMax (cm/s^2). */
	UPROPERTY(Config, EditAnywhere, Category = "Cruise", meta = (ClampMin = "0.0"))
	float LaneKp = 0.4f;

	UPROPERTY(Config, EditAnywhere, Category = "Cruise", meta = (ClampMin = "0.0"))
	float LaneKd = 0.8f;

	UPROPERTY(Config, EditAnywhere, Category = "Cruise", meta = (ClampMin = "0.0"))
	float LaneAccelMax = 600.f;

	/** How fast the held altitude follows the lane's (cm/s). */
	UPROPERTY(Config, EditAnywhere, Category = "Cruise", meta = (ClampMin = "0.0"))
	float LaneClimbRate = 200.f;

	// -------------------------------------------------------------------------
	// Zone (the own team's lane zone, hysteresis, at the hull origin)
	// -------------------------------------------------------------------------

	/** Enter the zone within these errors (cm) ... */
	UPROPERTY(Config, EditAnywhere, Category = "Zone", meta = (ClampMin = "0.0"))
	float LaneZoneEnterLateral = 2000.f;

	UPROPERTY(Config, EditAnywhere, Category = "Zone", meta = (ClampMin = "0.0"))
	float LaneZoneEnterVertical = 1500.f;

	/** ... leave it beyond these (cm). */
	UPROPERTY(Config, EditAnywhere, Category = "Zone", meta = (ClampMin = "0.0"))
	float LaneZoneExitLateral = 4000.f;

	UPROPERTY(Config, EditAnywhere, Category = "Zone", meta = (ClampMin = "0.0"))
	float LaneZoneExitVertical = 2500.f;

	/** "Parked in lane": in the zone and at most this horizontal speed (cm/s, a little above the lane speed). */
	UPROPERTY(Config, EditAnywhere, Category = "Zone", meta = (ClampMin = "0.0"))
	float LaneParkSpeed = 800.f;

	/** A Parked ship parked in its lane this long (s) cruises again. */
	UPROPERTY(Config, EditAnywhere, Category = "Zone", meta = (ClampMin = "0.0"))
	float LaneParkSettleTime = 0.5f;

	// -------------------------------------------------------------------------
	// Assist (a pilot at the helm of a cruising ship, Rules.bLaneAssist)
	// -------------------------------------------------------------------------

	/** No drive input this long (s) in the zone hands the helm back to the lane ... */
	UPROPERTY(Config, EditAnywhere, Category = "Assist", meta = (ClampMin = "0.0"))
	float LaneAssistDelay = 1.f;

	/** ... below this speed (cm/s). */
	UPROPERTY(Config, EditAnywhere, Category = "Assist", meta = (ClampMin = "0.0"))
	float LaneAssistMaxSpeed = 1500.f;

	// -------------------------------------------------------------------------
	// Safety (look-ahead, blockers, out-of-lane drift)
	// -------------------------------------------------------------------------

	/** Look-ahead sweep length = max(LaneLookAheadMin, speed x LaneLookAheadTime + stopping distance) (cm, s). */
	UPROPERTY(Config, EditAnywhere, Category = "Safety", meta = (ClampMin = "0.0"))
	float LaneLookAheadMin = 1500.f;

	UPROPERTY(Config, EditAnywhere, Category = "Safety", meta = (ClampMin = "0.0"))
	float LaneLookAheadTime = 3.f;

	/** Seconds between look-ahead sweeps while cruising. */
	UPROPERTY(Config, EditAnywhere, Category = "Safety", meta = (ClampMin = "0.01"))
	float LaneSweepInterval = 0.25f;

	/** Clear sweeps in a row before a blocked ship cruises again. */
	UPROPERTY(Config, EditAnywhere, Category = "Safety", meta = (ClampMin = "1"))
	int32 LaneBlockedClearChecks = 3;

	/** Drift limit (cm, from the exit point) of a team ship left outside its lane (PR A's DriftMaxDistance is 0 = never). */
	UPROPERTY(Config, EditAnywhere, Category = "Safety", meta = (ClampMin = "0.0"))
	float LaneOutDriftMaxDistance = 30000.f;

	/** Blocked this long (s): try going round the blocker LaneBypassOffset (cm) further outward. */
	UPROPERTY(Config, EditAnywhere, Category = "Safety", meta = (ClampMin = "0.0"))
	float LaneBlockedTimeout = 5.f;

	UPROPERTY(Config, EditAnywhere, Category = "Safety", meta = (ClampMin = "0.0"))
	float LaneBypassOffset = 3500.f;

	// -------------------------------------------------------------------------
	// Recall (a team ship left outside its lane flies itself back)
	// -------------------------------------------------------------------------

	UPROPERTY(Config, EditAnywhere, Category = "Recall")
	bool bShipRecall = true;

	/** Parked this long (s) while the match is in progress: the ship returns to its lane. */
	UPROPERTY(Config, EditAnywhere, Category = "Recall", meta = (ClampMin = "0.0"))
	float ShipRecallDelay = 20.f;

	/** Recall target speed (cm/s). */
	UPROPERTY(Config, EditAnywhere, Category = "Recall", meta = (ClampMin = "0.0"))
	float ShipRecallSpeed = 2500.f;

	/** Crossing the field, the recall climbs this far above path height first (cm: above every platform and the sentinel waves). */
	UPROPERTY(Config, EditAnywhere, Category = "Recall", meta = (ClampMin = "0.0"))
	float ShipRecallCrossHeight = 8000.f;

	/**
	 * How fast a returning ship's held altitude climbs and descends (cm/s; 0 = LaneClimbRate). At LaneClimbRate (200) the
	 * climb over the field and the descent to the lane take 78 s, past ShipRecallMaxTime, so every crossing would end in
	 * a replacement. Kept under the flight's HoldMaxSpeed (800) so the altitude hold can follow it.
	 */
	UPROPERTY(Config, EditAnywhere, Category = "Recall", meta = (ClampMin = "0.0"))
	float ShipRecallClimbRate = 600.f;

	/** The ship is replaced (no life lost) when not back after this long (s) ... */
	UPROPERTY(Config, EditAnywhere, Category = "Recall", meta = (ClampMin = "0.0"))
	float ShipRecallMaxTime = 60.f;

	/** ... when farther than this from its lane point (cm) ... */
	UPROPERTY(Config, EditAnywhere, Category = "Recall", meta = (ClampMin = "0.0"))
	float ShipRecallMaxDistance = 100000.f;

	/** ... or when blocked this long (s). */
	UPROPERTY(Config, EditAnywhere, Category = "Recall", meta = (ClampMin = "0.0"))
	float ShipRecallBlockedTime = 10.f;

	// -------------------------------------------------------------------------
	// Net
	// -------------------------------------------------------------------------

	/** Seconds between FMyLaneHint updates per ship. */
	UPROPERTY(Config, EditAnywhere, Category = "Net", meta = (ClampMin = "0.0"))
	float LaneHintInterval = 0.25f;
};
