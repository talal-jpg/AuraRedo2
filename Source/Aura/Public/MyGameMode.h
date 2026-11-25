// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "Match/MyMatchTypes.h"
#include "MyGameMode.generated.h"

class AAirshipPawn;
class AMyGameState;
class AMyHexPathSpawner;
class AMyHexPlatform;
class AMyPlayerState;
class UAbilitySystemComponent;
class UMechSentinelSwarmRules;
struct FOnAttributeChangeData;
class UDA_MyAbilityInfo;
class UMyLevelUpInfo;
class UDA_MyEnemyCharacterClassInfo;
class UMySpellMenuWidgetController;
class UNiagaraSystem;
/**
 * 
 */
UCLASS()
class AURA_API AMyGameMode : public AGameModeBase
{
	GENERATED_BODY()
	
public:
	AMyGameMode();
	
	virtual void PostLogin(APlayerController* NewPlayer) override;
	
	// Refuses players the host banned from the lobby (Current Session > Ban) and joins past the lobby's player limit.
	// Team match: also a join when both teams are full (1v1, 2v2)
	virtual void PreLogin(const FString& Options, const FString& Address, const FUniqueNetIdRepl& UniqueId, FString& ErrorMessage) override;
	
	/** Team match: match on / off and the rules (UMyMatchSettings, the command line, the URL options), the round. */
	virtual void InitGame(const FString& MapName, const FString& Options, FString& ErrorMessage) override;
	
	/** Team match: the rules, round and expected players into AMyGameState, before any player logs in. */
	virtual void InitGameState() override;
	
	/** Team match: gives the player a team before the engine picks his start spot (Team<id> PlayerStarts first). */
	virtual FString InitNewPlayer(APlayerController* NewPlayerController, const FUniqueNetIdRepl& UniqueId, const FString& Options, const FString& Portal = TEXT("")) override;
	
	/** Team match: swarm difficulty before the spawners' BeginPlay, then practice counts down at once, versus waits for its players. */
	virtual void StartPlay() override;
	
	/** Team match: an unoccupied Team<id> PlayerStart, then any unoccupied one, then any (never none). Match off: the engine's. */
	virtual AActor* ChoosePlayerStart_Implementation(AController* Player) override;
	
	/**
	 * Team match: a player the engine starts while the match runs (a late joiner) spawns as a match-start player would
	 * (aboard his ship in versus, else past the lead on his own side); a start that leaves him without a pawn retries
	 * around the PlayerStart (8 directions at 250, 500, 750 cm). Match off: the engine's.
	 */
	virtual void RestartPlayer(AController* NewPlayer) override;
	
	/** Global, server side rules of the Mass sentinel swarm (targeting caps, armor formula, damage effects). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Mech Sentinels")
	TObjectPtr<class UMechSentinelSwarmRules> SentinelSwarmRules;
	
	UPROPERTY(EditAnywhere)
	UDA_MyEnemyCharacterClassInfo* DA_MyEnemyCharacterClassInfo;
	
	UPROPERTY(EditAnywhere)
	UMyLevelUpInfo* DA_MyLevelUpInfo;
	
	UPROPERTY(EditAnywhere)
	UDA_MyAbilityInfo* DA_MyAbilityInfo;
	
	UPROPERTY(EditAnywhere)
	TSubclassOf<UMySpellMenuWidgetController> SpellMenuWidgetControllerClass;
	
	// -------------------------------------------------------------------------
	// Respawn: RespawnDelay seconds after a player dies (or falls out of the world), its controller gets a new
	// pawn on the platform just past the lead player's (AMyGameState ranking). The PlayerState and its ASC carry
	// over, so XP, level, spent points and abilities stay. AMyGameState plays RespawnFX there on every machine.
	// -------------------------------------------------------------------------
	
	/** Server. Called for every (re)started pawn: watches it for death and destruction. Team match: 600 m net cull distance. */
	virtual void SetPlayerDefaults(APawn* PlayerPawn) override;
	
	/** Team match: the team counts, a countdown that loses its players, the forfeit timer. */
	virtual void Logout(AController* Exiting) override;
	
	/**
	 * False while a respawn is pending, so a client's ServerRestartPlayer can't skip the wait. Team match: false while a
	 * versus match waits for its players or counts down (nobody races ahead before the start).
	 */
	virtual bool PlayerCanRestart_Implementation(APlayerController* Player) override;
	
	/** Off: dead players stay dead. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category="Respawn")
	bool bRespawnEnabled=true;
	
	/** Seconds from death to the new pawn. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category="Respawn", meta=(ClampMin="0.1"))
	float RespawnDelay=5.f;
	
	/** Plays at the respawn spot on every machine. Defaults to NS_Claude_RespawnFX. None = no FX. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category="Respawn")
	TObjectPtr<UNiagaraSystem> RespawnFX;
	
	/**
	 * The FX starts this long before the pawn appears, so its flash and the pawn showing line up
	 * (NS_Claude_RespawnFX flashes about 3 s in). The spot is picked when the FX starts. Capped at RespawnDelay.
	 */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category="Respawn", meta=(ClampMin="0"))
	float RespawnFXLeadTime=3.f;
	
	/** Gap (cm) between the top of the tile and the bottom of the new pawn's capsule. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category="Respawn", meta=(ClampMin="0"))
	float RespawnHeightAboveTile=10.f;
	
	// -------------------------------------------------------------------------
	// Team match (Docs/Airship/round2/SPEC_B.md): teams, team ships on their lanes, ship lives, match rules. Server
	// only; AMyGameState replicates the state. With the match off (map not in UMyMatchSettings::MatchMaps,
	// Aura.Match.Enable 0, URL Match=0) every player and ship stays team 255 and nothing below changes the game.
	// -------------------------------------------------------------------------
	
	/** Decided in InitGame from MatchMaps, the CVar Aura.Match.Enable and the URL's Match option. */
	bool IsMatchOn() const { return bMatchOn; }
	
	/**
	 * Live: swarm difficulty, lives, friendly fire, grapple, assist, time limit (a changed limit restarts the clock). The
	 * team mode takes effect at the next restart (GetNextTeamMode); the running round keeps its own.
	 */
	void ApplyRules(const FMyMatchRules& NewRules);
	
	/** The rules in force (the running round's team mode). */
	const FMyMatchRules& GetMatchRules() const { return MatchRules; }
	
	/** The team mode the next restart uses (ApplyRules' latest). */
	EMyTeamMode GetNextTeamMode() const { return NextTeamMode; }
	
	/** The running round (or its countdown) has two teams. False in practice. */
	bool IsVersusRound() const { return bVersusRound || bCountdownVersus || bPracticeToVersus; }
	
	/** Console (Aura.Match.Rules TimeLimit=..): the time limit runs again from now. */
	void RestartTimeLimit();
	
	/** Console (Aura.Match.ShipLives): TeamId may lose NewLives ships in all; LivesLeft = max(NewLives - ShipsLost, ship alive ? 1 : 0). */
	void SetTeamShipLives(uint8 TeamId, int32 NewLives);
	
	/** The rules as URL options (?Teams=..?ShipLives=..?Swarm=..?TimeLimit=..?FF=..?GrappleShips=..?LaneAssist=..), the restart's. */
	FString BuildRulesOptions(const FMyMatchRules& Rules, EMyTeamMode TeamMode) const;
	
	/**
	 * Reads the rule options (Teams, ShipLives, Swarm, TimeLimit, FF, GrappleShips, LaneAssist) present in Options into
	 * InOutRules, clamped (bad values logged with Source). True if any was present. The console's Aura.Match.Rules uses it.
	 */
	static bool ParseRulesOptions(const FString& Options, FMyMatchRules& InOutRules, const TCHAR* Source);
	
	/** Spawns TeamId's ship on its lane at progress U (cm), protected, and makes it the team's ship. Null when it can't. */
	AAirshipPawn* SpawnTeamShip(uint8 TeamId, float U);
	
	/** Host (pause menu's Start match, Aura.Match.Start): WaitingToStart -> Countdown with whoever is in. */
	void RequestStartMatch();
	
	/** Console: skips the countdown too. */
	void StartMatchNow();
	
	void EndMatch(EMyMatchResult Result, uint8 WinningTeam, EMyMatchEndReason Reason);
	
	/** Remembers the teams, next round, reloads the map with the current rules as URL options. */
	void RestartMatch();
	
	/** Console: ejects the player from the other team's ship first, then moves him and updates the counts. */
	void SetPlayerTeam(AMyPlayerState* Player, uint8 TeamId);
	
private:
	
	// -------------------------------------------------------------------------
	// Team match state (server)
	// -------------------------------------------------------------------------
	
	bool bMatchOn=false;
	
	/** The rules in force (InitGame's, then ApplyRules); copied into AMyGameState::MatchRules. */
	FMyMatchRules MatchRules;
	
	/** ApplyRules' team mode, used by the restart (the running round keeps MatchRules.TeamMode). */
	EMyTeamMode NextTeamMode=EMyTeamMode::Auto;
	
	/** The URL's Players (the host menu's Max Players), else UMyMatchSettings::DefaultExpectedPlayers. Auto versus waits for this many. */
	int32 ExpectedPlayers=1;
	
	/** 0 on a fresh map load, +1 per restart (UMyMatchMemorySubsystem). */
	int32 RoundIndex=0;
	
	/** The round that runs has two active teams (InProgress, set at the countdown's end). */
	bool bVersusRound=false;
	
	/** The running countdown is a versus start (two active teams at its start): no pawns until it ends. */
	bool bCountdownVersus=false;
	
	/** The running countdown was started by the host (Start match, Aura.Match.Start): it doesn't go back to waiting. */
	bool bHostForcedStart=false;
	
	/** The running countdown turns a practice into versus (B1.3): the players already in keep playing through it. */
	bool bPracticeToVersus=false;
	
	bool bTimeWarningSent=false;
	bool bEndCheckPending=false;
	bool bRestarting=false;
	
	/** RespawnPlayer's last resort RestartPlayer: no start-aboard rule for a respawn. */
	bool bRestartFromRespawn=false;
	
	/** The player count the swarm difficulty was last built for (the count factor follows it). */
	int32 SwarmPlayerCount=-1;
	
	FTimerHandle CountdownTimer;
	FTimerHandle MatchTickTimer;
	FTimerHandle HealthTickTimer;
	FTimerHandle RestartTimer;
	
	/** Ships placed in the map (seen at StartPlay): claimed by their ShipTeam<id> tag or removed in versus. */
	TArray<TWeakObjectPtr<AAirshipPawn>> PlacedShips;
	
	/** Team ships and ship wrecks the game mode listens to. */
	struct FWatchedShip
	{
		uint8 TeamId=MyMatch::NoTeam;
		TWeakObjectPtr<UAbilitySystemComponent> ASC;
		FDelegateHandle HealthHandle;
	};
	
	TMap<TWeakObjectPtr<AAirshipPawn>, FWatchedShip> WatchedShips;
	
	/** Progress u of each team's last ship when it died (respawn fallback). */
	float LastShipU[MyMatch::NumTeams]={};
	
	/** Server time each team ship last lost health (bRespawnAboard). */
	double LastShipDamageTime[MyMatch::NumTeams]={};
	
	/** Fall death: since when each player's character has been falling with no base. */
	TMap<TWeakObjectPtr<APawn>, double> FallingSince;
	
	/** The swarm rules asset copy with the difficulty's MaxAttackersPerPlayer (SetRulesOverride), kept alive here. */
	UPROPERTY(Transient)
	TObjectPtr<UMechSentinelSwarmRules> SwarmRulesCopy;
	
	TWeakObjectPtr<AMyHexPathSpawner> PathSpawner;
	
	// Setup
	void ParseMatchOptions(const FString& Options);
	bool IsPracticeStart() const;
	int32 GetNeededPlayers() const;
	bool IsHoldingPawns() const;
	/** A countdown is on and Player's team isn't active yet: he starts when it ends, with the others (B1.3). */
	bool IsWaitingForTeamStart(const AController* Player) const;
	AMyGameState* GetMatchGameState() const;
	EMyMatchPhase GetPhase() const;
	double GetServerTime() const;
	float GetLayoutScale();
	
	// Teams
	void AssignTeam(AMyPlayerState* PlayerState, const FUniqueNetIdRepl& UniqueId);
	void RecountTeams(const APlayerState* Leaving = nullptr);
	void EvaluateTeams(const APlayerState* Leaving = nullptr);
	int32 GetTeamCap() const;
	bool IsStartConditionMet() const;
	void UpdateHandicap();
	int8 GetSideForTeam(uint8 TeamId) const;
	static uint8 GetControllerTeam(const AController* Controller);
	
	// Flow
	void StartCountdown(bool bForced);
	void OnCountdownEnd();
	void BackToWaiting();
	void StartPracticeToVersus(uint8 JoinedTeam);
	void CancelPracticeToVersus();
	void BeginRound();
	void SpawnWaitingPlayers();
	void ResetTeamsForRound();
	void MatchTick();
	void HealthTick();
	void ScheduleEndCheck();
	void CheckEnd();
	void ResolveTimeLimit();
	float GetTeamProgress(uint8 TeamId) const;
	void UpdateForfeits();
	void UpdateShipRespawns();
	void UpdateFallDeaths();
	void ApplySwarmDifficulty();
	void StopSwarm();
	
	// Team ships
	void ClaimOrSpawnShips(bool bTwoTeams);
	void RemoveUntaggedPlacedShips();
	void AdoptTeamShip(AAirshipPawn* Ship, uint8 TeamId);
	void WatchShip(AAirshipPawn* Ship, uint8 TeamId);
	void UnwatchShip(AAirshipPawn* Ship);
	void RemoveTeamShip(uint8 TeamId, const TCHAR* Reason);
	void ProtectShip(AAirshipPawn* Ship) const;
	void HealShip(AAirshipPawn* Ship) const;
	float GetShipHealthFraction(const AAirshipPawn* Ship) const;
	float GetShipRespawnU(uint8 TeamId) const;
	bool FindAboardTransform(const AController* Controller, const AAirshipPawn* Ship, int32 SpotIndex, FTransform& OutTransform) const;
	
	UFUNCTION()
	void OnTeamShipDied(AActor* DeadActor);
	
	UFUNCTION()
	void OnTeamShipDestroyed(AActor* DestroyedActor);
	
	void OnTeamShipHealthChanged(const FOnAttributeChangeData& Data, TWeakObjectPtr<AAirshipPawn> WeakShip);
	
	/** Where a respawn's pawn goes. */
	struct FRespawnSpot
	{
		FTransform PawnTransform;
		
		/** Under the pawn's capsule, where the FX plays. */
		FVector GroundLocation=FVector::ZeroVector;
		
		/** False for a PlayerStart. */
		bool bOnTile=false;
		TWeakObjectPtr<AMyHexPlatform> Platform;
		FIntVector TileCoord=FIntVector::ZeroValue;
		
		/** Team match bRespawnAboard: a deck spot, kept relative to the moving ship until the pawn spawns. */
		TWeakObjectPtr<AAirshipPawn> Ship;
		FTransform ShipLocal;
	};
	
	struct FPendingRespawn
	{
		FTimerHandle FXTimer;
		FTimerHandle RespawnTimer;
		
		/** Picked when the FX starts. Other respawns keep clear of it until this one spawns. */
		TOptional<FRespawnSpot> Spot;
	};
	
	/** The pawn a respawn spawns, for the fit tests: its class default and capsule size. */
	struct FPawnFit
	{
		const APawn* PawnToFit=nullptr;
		float HalfHeight=0.f;
		float Radius=0.f;
	};
	
	/** Starts the FX and respawn timers. Does nothing while one is pending for Controller. */
	void ScheduleRespawn(AController* Controller);
	
	/** Picks the spot and plays the FX there. */
	void StartRespawnFX(TWeakObjectPtr<AController> WeakController);
	
	/** Replaces the controller's dead pawn (if it still has one) with a new pawn at the picked spot. */
	void RespawnPlayer(TWeakObjectPtr<AController> WeakController);
	
	/** False when Controller has no default pawn class. */
	bool GetPawnFit(AController* Controller, FPawnFit& OutFit);
	
	/**
	 * A tile on the nearest platform past the lead's (the lead's own platform at the end of the path), or a
	 * PlayerStart when nobody has landed on a platform yet. False = nowhere.
	 */
	bool FindRespawnSpot(AController* Controller, const FPawnFit& Fit, FRespawnSpot& OutSpot);
	
	/** A live tile on Platform the pawn fits on: bridge path first (no props), then away from the edge, then near the centre. */
	bool FindRespawnTile(AMyHexPlatform* Platform, const FPawnFit& Fit, const FRotator& Rotation, const AController* Controller,
		FRespawnSpot& OutSpot) const;
	
	/**
	 * The pawn fits on the tile: it is still there, nothing blocks it (props, pawns), it isn't pushed off it, and
	 * it is clear of the spots other pending respawns (not Controller's) have picked.
	 */
	bool FitPawnOnTile(AMyHexPlatform* Platform, const FIntVector& TileCoord, const FPawnFit& Fit, const FRotator& Rotation,
		const AController* Controller, FRespawnSpot& OutSpot) const;
	
	void PlayRespawnFX(const FRespawnSpot& Spot) const;
	
	void WatchPlayerPawn(APawn* PlayerPawn);
	void UnwatchPlayerPawn(APawn* PlayerPawn);
	
	/** Bound to the pawn's OnDeathDelegate (IMyCombatInterface). */
	UFUNCTION()
	void OnPlayerPawnDied(AActor* DeadActor);
	
	/** Bound to the pawn's OnDestroyed: falling out of the world destroys the pawn without a death. */
	UFUNCTION()
	void OnPlayerPawnDestroyed(AActor* DestroyedActor);
	
	TMap<TWeakObjectPtr<AController>, FPendingRespawn> PendingRespawns;
	
	/** Watched pawns and their controllers (a pawn has none any more by the time OnDestroyed fires). */
	TMap<TWeakObjectPtr<APawn>, TWeakObjectPtr<AController>> WatchedPawns;
	
};
