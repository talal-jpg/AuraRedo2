// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameStateBase.h"
#include "MyGameState.generated.h"

class AMyPlayerState;
class UNiagaraSystem;

DECLARE_DYNAMIC_MULTICAST_DELEGATE(FOnPlayerRankingChangedSignature);

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

private:

	/** Server. Activates (AMyHexPlatform::NotifyLeadLanded) every platform with SplineDistance <= MaxDistance. */
	void ActivatePlatformsUpTo(float MaxDistance);

	float ActivatedSplineDistance = -1.f;
};
