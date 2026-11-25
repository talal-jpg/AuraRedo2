// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameStateBase.h"
#include "Match/MyMatchTypes.h"
#include "MyGameState.generated.h"

class AMyPlayerState;
class UNiagaraSystem;

DECLARE_DYNAMIC_MULTICAST_DELEGATE(FOnPlayerRankingChangedSignature);

/** AMyGameState::OnMatchEvent: the event, its team (255 = none) and its value (lives left, seconds, ...). */
DECLARE_MULTICAST_DELEGATE_ThreeParams(FOnMatchEvent, EMyMatchEvent /*Event*/, uint8 /*TeamId*/, int32 /*Value*/);

/** Player states sorted by how far along the path their platform is. Replicated as one piece. */
USTRUCT(BlueprintType)
struct FMyPlayerRanking
{
	GENERATED_BODY()

	/** Furthest first. Players who haven't landed on a platform with a spline distance yet are last. */
	UPROPERTY(BlueprintReadOnly)
	TArray<TObjectPtr<AMyPlayerState>> PlayerStates;

	/** The first NumLeaders entries share the greatest distance. 0 until someone lands on a platform. */
	UPROPERTY(BlueprintReadOnly)
	int32 NumLeaders = 0;
};

/**
 * Ranks the players by AMyHexPlatform::SplineDistance of the platform each one last landed on
 * (AMyPlayerState::GetPlatformSplineDistance). The server re-sorts whenever a player lands on a
 * different platform, or a player joins or leaves, and the result replicates to everyone.
 */
UCLASS()
class AURA_API AMyGameState : public AGameStateBase
{
	GENERATED_BODY()

public:

	AMyGameState();

	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	virtual void AddPlayerState(APlayerState* PlayerState) override;
	virtual void RemovePlayerState(APlayerState* PlayerState) override;

	/**
	 * Server. Called when a player lands on a new platform (and on join / leave): re-sorts the players
	 * by platform distance, works out who is leading, then activates every platform behind the lead's
	 * platform (SplineDistance <= the lead's - CollapseStartBehindLead).
	 */
	void UpdatePlayerRanking();

	/**
	 * Server. Furthest activated SplineDistance so far (the lead's platform distance minus
	 * CollapseStartBehindLead); platforms at or below it are activated. -1 until someone lands on a
	 * platform. Never goes down, so a leader leaving doesn't un-activate anything.
	 */
	float GetActivatedSplineDistance() const { return ActivatedSplineDistance; }

	/** Platform SplineDistance of the top-ranked player. -1 until someone lands on a platform that has one. */
	UFUNCTION(BlueprintPure, Category = "Player Ranking")
	float GetLeadSplineDistance() const;

	const TArray<TObjectPtr<AMyPlayerState>>& GetRankedPlayerStates() const { return PlayerRanking.PlayerStates; }

	/** Every player at the greatest distance (several when they are on the same platform). */
	UFUNCTION(BlueprintPure, Category = "Player Ranking")
	TArray<AMyPlayerState*> GetLeadingPlayerStates() const;

	UFUNCTION(BlueprintPure, Category = "Player Ranking")
	bool IsLeading(const AMyPlayerState* PlayerState) const;

	/** Broadcast on the server after each re-sort and on clients when the ranking replicates. */
	UPROPERTY(BlueprintAssignable, Category = "Player Ranking")
	FOnPlayerRankingChangedSignature OnPlayerRankingChanged;

	/**
	 * Server. Plays System at Location on every machine (the game state is always relevant). AMyGameMode calls it
	 * when a respawn's FX starts, RespawnFXLeadTime before the pawn appears.
	 */
	UFUNCTION(NetMulticast, Reliable)
	void MulticastPlayRespawnFX(UNiagaraSystem* System, FVector_NetQuantize Location, FRotator Rotation);

	// -------------------------------------------------------------------------
	// Team match (Docs/Airship/round2/SPEC_B.md): phase, rules, both teams and the result, written by AMyGameMode on the
	// server and replicated to everyone (the game state is always relevant). Phase None = no match: PR A behaviour.
	// -------------------------------------------------------------------------

	UFUNCTION(BlueprintPure, Category = "Match")
	EMyMatchPhase GetMatchPhase() const { return MatchPhase; }

	const FMyMatchRules& GetMatchRules() const { return MatchRules; }

	/** Teams[TeamId]; a default entry (TeamId 255, inactive) for an invalid id. */
	const FMyTeamState& GetTeamState(uint8 TeamId) const;

	UFUNCTION(BlueprintPure, Category = "Match")
	EMyMatchResult GetMatchResult() const { return MatchResult; }

	/** 255 unless the result is TeamWon. */
	UFUNCTION(BlueprintPure, Category = "Match")
	uint8 GetWinningTeam() const { return WinningTeam; }

	/** Server time the current phase ends (countdown end, automatic restart); 0 = none. */
	UFUNCTION(BlueprintPure, Category = "Match")
	double GetPhaseEndServerTime() const { return PhaseEndServerTime; }

	UFUNCTION(BlueprintPure, Category = "Match")
	EMyMatchEndReason GetEndReason() const { return EndReason; }

	/** Server time the time limit runs out; 0 = none. */
	UFUNCTION(BlueprintPure, Category = "Match")
	double GetMatchEndServerTime() const { return MatchEndServerTime; }

	/** Versus waits for this many players before the countdown. */
	UFUNCTION(BlueprintPure, Category = "Match")
	int32 GetExpectedPlayers() const { return ExpectedPlayers; }

	/** 0 on a map load from the menu, +1 on every restart after a versus round (lane sides swap on odd versus rounds). */
	UFUNCTION(BlueprintPure, Category = "Match")
	int32 GetRoundIndex() const { return RoundIndex; }

	/** This round's lane sides are swapped (an odd versus round with bAlternateSides; decided when its countdown starts). */
	UFUNCTION(BlueprintPure, Category = "Match")
	bool AreLaneSidesSwapped() const { return bLaneSidesSwapped; }

	/** A Countdown the round keeps playing through (practice -> versus, B1.3): lane ships keep cruising. */
	UFUNCTION(BlueprintPure, Category = "Match")
	bool IsPlayGoingOn() const { return bPlayGoesOn; }

	/** Server -> every machine: OnMatchEvent (HUD toasts). */
	UFUNCTION(NetMulticast, Reliable)
	void MulticastMatchEvent(EMyMatchEvent Event, uint8 TeamId, int32 Value);

	/** Every machine: after any match property replicates, and on the server after every write below. */
	FSimpleMulticastDelegate OnMatchChanged;

	/** Every machine, from MulticastMatchEvent. */
	FOnMatchEvent OnMatchEvent;

	// Server-only writers, used by AMyGameMode only. Each one forces a net update and broadcasts OnMatchChanged.

	/** bInPlayGoesOn: a Countdown the round plays through (practice -> versus); any other call clears it. */
	void SetMatchPhase(EMyMatchPhase NewPhase, double NewPhaseEndServerTime, bool bInPlayGoesOn = false);
	void SetMatchRules(const FMyMatchRules& NewRules);
	void SetLaneSidesSwapped(bool bSwapped);

	/** Teams[TeamId] to change in place; call MarkTeamsDirty after. An invalid id gets a scratch entry (and an ensure). */
	FMyTeamState& EditTeam(uint8 TeamId);

	void SetResult(EMyMatchResult NewResult, uint8 NewWinningTeam, EMyMatchEndReason NewEndReason = EMyMatchEndReason::None);
	void SetMatchEndServerTime(double NewMatchEndServerTime);
	void SetExpectedPlayers(int32 NewExpectedPlayers);
	void SetRoundIndex(int32 NewRoundIndex);
	void MarkTeamsDirty();

protected:

	UPROPERTY(ReplicatedUsing = OnRep_PlayerRanking, BlueprintReadOnly, Category = "Player Ranking")
	FMyPlayerRanking PlayerRanking;

	/**
	 * Players within this distance (cm) of the furthest one also count as leading. 0 = only those on a
	 * platform with exactly the same spline distance.
	 */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Player Ranking", meta = (ClampMin = "0.0"))
	float LeadDistanceTolerance = 0.f;

	/**
	 * Platforms start collapsing once the lead's platform is more than this (cm of SplineDistance)
	 * ahead of theirs. The default 1 starts every platform behind the lead's platform, while the lead's
	 * own platform and the ring platforms that share its distance wait until the lead moves on.
	 */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Player Ranking", meta = (ClampMin = "0.0"))
	float CollapseStartBehindLead = 1.f;

	UFUNCTION()
	void OnRep_PlayerRanking();

	UPROPERTY(ReplicatedUsing = OnRep_Match)
	EMyMatchPhase MatchPhase = EMyMatchPhase::None;

	UPROPERTY(ReplicatedUsing = OnRep_Match)
	FMyMatchRules MatchRules;

	/** Fixed: one entry per team, Teams[i].TeamId == i. */
	UPROPERTY(ReplicatedUsing = OnRep_Match)
	FMyTeamState Teams[MyMatch::NumTeams];

	UPROPERTY(ReplicatedUsing = OnRep_Match)
	EMyMatchResult MatchResult = EMyMatchResult::None;

	UPROPERTY(ReplicatedUsing = OnRep_Match)
	EMyMatchEndReason EndReason = EMyMatchEndReason::None;

	UPROPERTY(ReplicatedUsing = OnRep_Match)
	uint8 WinningTeam = MyMatch::NoTeam;

	UPROPERTY(ReplicatedUsing = OnRep_Match)
	double PhaseEndServerTime = 0.0;

	UPROPERTY(ReplicatedUsing = OnRep_Match)
	double MatchEndServerTime = 0.0;

	UPROPERTY(ReplicatedUsing = OnRep_Match)
	int32 ExpectedPlayers = 0;

	UPROPERTY(ReplicatedUsing = OnRep_Match)
	int32 RoundIndex = 0;

	UPROPERTY(ReplicatedUsing = OnRep_Match)
	bool bLaneSidesSwapped = false;

	UPROPERTY(ReplicatedUsing = OnRep_Match)
	bool bPlayGoesOn = false;

	/** Every match property: the engine calls the notifies after the whole update is applied, so the state is consistent. */
	UFUNCTION()
	void OnRep_Match();

private:

	/** Server. Activates (AMyHexPlatform::NotifyLeadLanded) every platform with SplineDistance <= MaxDistance. */
	void ActivatePlatformsUpTo(float MaxDistance);

	/** Server: ForceNetUpdate and OnMatchChanged after a match write. */
	void NotifyMatchWritten();

	float ActivatedSplineDistance = -1.f;

	/** EditTeam's answer for an invalid id, so a bad caller can't write into a real team. */
	FMyTeamState ScratchTeam;
};
