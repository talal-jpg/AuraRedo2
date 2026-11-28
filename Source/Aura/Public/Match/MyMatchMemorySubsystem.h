// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "MyMatchMemorySubsystem.generated.h"

class AGameStateBase;
struct FUniqueNetIdRepl;

/**
 * Team match memory across a restart (Docs/Airship/round2/SPEC_B.md B1.6), host only, not replicated. The restart and the
 * return to the lobby (SPEC_B_LOBBY 5.3) rebuild the world, the game mode and every player state: a seamless ServerTravel
 * outside PIE (the team also travels in AMyPlayerState::CopyProperties), a hard one in PIE and an OpenLevel standalone,
 * where clients reconnect. So the teams live here too, on the game instance: each player's unique net id -> his team,
 * written when the host restarts or returns, read by AMyGameMode's team assignment, so friends stay together in 2v2.
 * RoundIndex counts the restarts (the lane sides swap on odd rounds).
 *
 * AMyGameMode::TravelToRound writes a Round option into the travel URL; a match map loaded without it (from the menu, a
 * console open) is a fresh start, and InitGame calls Reset. So nothing outside the game mode has to clear it.
 */
UCLASS()
class AURA_API UMyMatchMemorySubsystem : public UGameInstanceSubsystem
{
	GENERATED_BODY()

public:

	static UMyMatchMemorySubsystem* Get(const UObject* WorldContext);

	/** The team Id played last round. False for an invalid id (PIE without an online subsystem may give none) or a new player. */
	bool FindTeam(const FUniqueNetIdRepl& Id, uint8& OutTeam) const;

	/** Every player of GameState with a valid net id and a team (AMyPlayerState::GetTeamId != 255), replacing what was kept. */
	void RememberTeams(const AGameStateBase* GameState);

	int32 GetRoundIndex() const { return RoundIndex; }

	void NextRound() { ++RoundIndex; }

	/** The travel URL's Round option wins over what was counted here (a hand-typed URL). */
	void SetRoundIndex(int32 NewRoundIndex) { RoundIndex = FMath::Max(0, NewRoundIndex); }

	int32 GetNumRemembered() const { return Teams.Num(); }

	/** Forgets the teams; round 0. A fresh match from the menu. */
	void Reset();

private:

	/** FUniqueNetIdRepl::ToString -> TeamId. */
	TMap<FString, uint8> Teams;

	int32 RoundIndex = 0;
};
