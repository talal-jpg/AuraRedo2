// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Engine/DeveloperSettings.h"
#include "BurrowerSettings.generated.h"

class ABurrowerCharacter;

/**
 * Settings used by UBurrowerSpawnSubsystem, which spawns a Burrower behind every player and keeps it
 * following that player. Project Settings > Game > Burrower, saved to DefaultGame.ini.
 *
 * Per player: FirstSpawnDelay after the player's first pawn appears, the first Burrower spawns
 * SpawnDistanceBehind behind them. While the player has fewer than MaxAlivePerPlayer, another one
 * comes every SpawnInterval. When one dies or is removed, the next one waits at least SpawnInterval.
 * The countdown only runs while the player has a living pawn.
 */
UCLASS(Config = Game, DefaultConfig, meta = (DisplayName = "Burrower"))
class AURA_API UBurrowerSettings : public UDeveloperSettings
{
	GENERATED_BODY()

public:

	/** Off = no Burrowers are spawned (Aura.Burrower.SpawnNow still works). */
	UPROPERTY(Config, EditAnywhere, Category = "Spawning")
	bool bEnabled = true;

	/** Actor spawned for every player. Use BP_Burrower (a Blueprint child of ABurrowerCharacter with the mesh and AnimBP set). */
	UPROPERTY(Config, EditAnywhere, Category = "Spawning")
	TSoftClassPtr<ABurrowerCharacter> BurrowerClass;

	/** Map names (no path, no PIE prefix, e.g. StartupMap) Burrowers spawn in. Empty = every game map. */
	UPROPERTY(Config, EditAnywhere, Category = "Spawning")
	TArray<FString> AllowedMaps;

	/** Seconds after a player's first pawn appears before their first Burrower. */
	UPROPERTY(Config, EditAnywhere, Category = "Spawning", meta = (ClampMin = "0.0"))
	float FirstSpawnDelay = 10.f;

	/**
	 * Seconds between a player's Burrowers: after the previous one died or was removed, or after the
	 * previous spawn while the player has fewer than MaxAlivePerPlayer.
	 */
	UPROPERTY(Config, EditAnywhere, Category = "Spawning", meta = (ClampMin = "0.0"))
	float SpawnInterval = 30.f;

	/** After a player's pawn respawns, their next Burrower waits at least this long. */
	UPROPERTY(Config, EditAnywhere, Category = "Spawning", meta = (ClampMin = "0.0"))
	float PlayerRespawnGrace = 5.f;

	/** Distance behind the player (cm, horizontal) where a Burrower appears. Behind = against their velocity, or their facing when slow. */
	UPROPERTY(Config, EditAnywhere, Category = "Spawning", meta = (ClampMin = "0.0"))
	float SpawnDistanceBehind = 3000.f;

	/** Height (cm) of the spawn point above the player's actor location. Negative = below (in the tiles). */
	UPROPERTY(Config, EditAnywhere, Category = "Spawning")
	float SpawnHeightOffset = -150.f;

	/** Above this speed (cm/s, horizontal) "behind" is against the player's velocity, below it against their facing. */
	UPROPERTY(Config, EditAnywhere, Category = "Spawning", meta = (ClampMin = "0.0"))
	float MinSpeedForVelocityDirection = 150.f;

	/** Burrowers that may follow one player at the same time. */
	UPROPERTY(Config, EditAnywhere, Category = "Spawning", meta = (ClampMin = "1"))
	int32 MaxAlivePerPlayer = 1;

	/** Off: once one of a player's Burrowers has died, that player gets no new ones. Removed ones (DespawnDistance) still come back. */
	UPROPERTY(Config, EditAnywhere, Category = "Spawning")
	bool bRespawnAfterDeath = true;

	/** A Burrower further than this (cm) from its living player is removed (and comes back after SpawnInterval). 0 = never. */
	UPROPERTY(Config, EditAnywhere, Category = "Spawning", meta = (ClampMin = "0.0"))
	float DespawnDistance = 0.f;

	/** Only pawns with the combat interface (the player characters) get Burrowers, so menu or spectator pawns don't. */
	UPROPERTY(Config, EditAnywhere, Category = "Spawning")
	bool bOnlyCombatPawns = true;

	/** Seconds between the server's checks of the players (joins, leaves, respawns, deaths, countdowns). */
	UPROPERTY(Config, EditAnywhere, Category = "Spawning", meta = (ClampMin = "0.05"))
	float PollInterval = 0.25f;
};
