// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "Match/MyMatchTypes.h"
#include "MyTeamLibrary.generated.h"

class AAirshipPawn;

/**
 * Team rules every owner asks through one place (SPEC_B section 2.3). Works on every machine unless noted: it only reads
 * replicated team ids and the game state's replicated rules. With no match running every actor is team 255, so every
 * function returns the PR A answer (nobody is a teammate, nothing is blocked, every ship is usable).
 */
UCLASS()
class AURA_API UMyTeamLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:

	/** A match runs: the game state's phase isn't None. */
	UFUNCTION(BlueprintPure, Category = "Match", meta = (WorldContext = "WorldContext"))
	static bool IsMatchActive(const UObject* WorldContext);

	/**
	 * The running match's rules (the game state's, replicated) while IsMatchActive, else UMyMatchSettings::DefaultRules.
	 * With the match off the game state's copy is never written (default-constructed), so it would ignore the config.
	 */
	static const FMyMatchRules& GetRules(const UObject* WorldContext);

	/**
	 * Team of any actor, in this order: AMyPlayerState -> its TeamId; AController -> its player state; AAirshipPawn -> its
	 * TeamId; AAirshipTurret -> its ship's; AAirshipCannonball -> its SourceTeamId; APawn with a player state -> that;
	 * attached (up to 4 parents) to an AAirshipPawn -> the ship's (a seated pilot is unpossessed, so has no player state);
	 * attached to a character -> the character's; an actor whose ASC's owner is a player state -> that; else 255.
	 */
	UFUNCTION(BlueprintPure, Category = "Match")
	static uint8 GetTeamId(const AActor* Actor);

	/** Both resolve to the same valid team (not 255). */
	UFUNCTION(BlueprintPure, Category = "Match")
	static bool AreTeammates(const AActor* A, const AActor* B);

	/**
	 * Damage from Instigator to Target must not happen: the match is on, Rules.bFriendlyFire is off, both are on the same
	 * valid team and Target isn't the instigator itself. Team-less actors (sentinels, the Burrower, free ships) are never
	 * protected. Decide damage on the server with it; BlueprintPure for GA_BeamBP's knockback.
	 */
	UFUNCTION(BlueprintPure, Category = "Match")
	static bool IsFriendlyFireBlocked(const AActor* Instigator, const AActor* Target);

	/** User may pilot or man Ship: a free ship (255), no match, or the same team. Any machine (replicated team ids only). */
	UFUNCTION(BlueprintPure, Category = "Match")
	static bool CanUseShip(const AActor* User, const AAirshipPawn* Ship);

	/** Target is a team ship or a team ship's turret while the match is on: it takes the fixed ship damage (ShipDamageGunHit / TurretRound). */
	UFUNCTION(BlueprintPure, Category = "Match")
	static bool IsTeamShipTarget(const AActor* Target);

	/**
	 * The ship lives the time limit's tie-break compares (B4.4): LivesLeft without the smaller team's BonusLives (= fewer
	 * ships lost wins), or with them when UMyMatchSettings::bTimeLimitCountsHandicap. The server and the HUD use it alike.
	 */
	static int32 GetTimeLimitLives(const FMyTeamState& Team);

	/** UMyMatchSettings::TeamColors; grey for no team. */
	UFUNCTION(BlueprintPure, Category = "Match")
	static FLinearColor GetTeamColor(uint8 TeamId);

	/** UMyMatchSettings::TeamNames (BLUE, ORANGE); empty for no team. */
	UFUNCTION(BlueprintPure, Category = "Match")
	static FText GetTeamName(uint8 TeamId);
};
