// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Engine/TimerHandle.h"
#include "Subsystems/WorldSubsystem.h"
#include "BurrowerSpawnSubsystem.generated.h"

struct FStreamableHandle;
class ABurrowerCharacter;
class APawn;
class APlayerState;
class UBurrowerSettings;

/**
 * Server only (listen server or standalone; nothing on clients, and off on a dedicated server, where
 * AMyEnemyChar::BeginPlay would crash on the missing health bar widget). Only where the GameMode is an
 * AMyGameMode with DA_MyEnemyCharacterClassInfo set (the attributes and the kill's XP need it). Gives every player
 * their own Burrower: spawned SpawnDistanceBehind behind them after a per-player countdown, told to
 * follow them, tracked, and replaced SpawnInterval after it dies (UBurrowerSettings, Project Settings >
 * Game > Burrower).
 *
 * Players are polled every PollInterval from GameState->PlayerArray and keyed by their PlayerState, which
 * survives respawns: a new pawn is retargeted, a dead or missing pawn pauses that player's countdown
 * and leaves their Burrower waiting, a player who leaves takes their Burrower with them. A player aboard an
 * airship (piloting, manning a gun, riding on deck) counts as one without a pawn (ABurrowerCharacter::IsLivingTarget).
 *
 * The match changes the settings at runtime only (SetDifficultyOverride, SetSpawningPaused): UBurrowerSettings
 * stays the base.
 *
 * Console (not shipping): Aura.Burrower.SpawnNow [PlayerIndex], Aura.Burrower.KillAll.
 */
UCLASS()
class AURA_API UBurrowerSpawnSubsystem : public UWorldSubsystem
{
	GENERATED_BODY()

public:

	static UBurrowerSpawnSubsystem* Get(const UObject* WorldContextObject);

	virtual void OnWorldBeginPlay(UWorld& InWorld) override;

	virtual void Deinitialize() override;

	/**
	 * Server. A Burrower behind every player with a living pawn now, ignoring the countdowns, bEnabled and
	 * MaxAlivePerPlayer. PlayerIndex >= 0: only GameState->PlayerArray[PlayerIndex]. Returns how many spawned.
	 */
	int32 SpawnNow(int32 PlayerIndex = -1);

	/** Server. Kills every living Burrower in the world through its normal death (for tests). Returns how many. */
	int32 KillAll();

	/** Server. Living Burrowers following this player. */
	int32 GetNumAliveFor(const APlayerState* PlayerState) const;

	/** True on the machine that runs the spawning (listen server or standalone). */
	bool IsActive() const { return bActive; }

	/**
	 * Server: the match's swarm difficulty on top of UBurrowerSettings, which stays the base (the project's and the
	 * user's own values). InSpawnIntervalScale multiplies SpawnInterval from the next re-arm of each countdown;
	 * InMaxAlivePerPlayer > 0 is a floor on the setting's (max of the two; 0 = the setting); InCharacterLevel > 0 is the level of the
	 * Burrowers spawned from now on, set before their attribute effects apply (0 = the Burrower class's own, 1). Safe
	 * before OnWorldBeginPlay (only stored).
	 */
	void SetDifficultyOverride(float InSpawnIntervalScale, int32 InMaxAlivePerPlayer, int32 InCharacterLevel);

	/**
	 * Server: no automatic spawns while paused (the match waiting for players, counting down or over). The countdowns
	 * hold where they are; living Burrowers keep following. SpawnNow still works.
	 */
	void SetSpawningPaused(bool bPaused);

	bool IsSpawningPaused() const { return bSpawningPaused; }

	/** UBurrowerSettings::SpawnInterval x the difficulty's scale (s). */
	float GetSpawnInterval() const;

	/** UBurrowerSettings' MaxAlivePerPlayer, raised to the difficulty's when that is higher. */
	int32 GetMaxAlivePerPlayer() const;

	/** Level given to new Burrowers; 0 = their class's own. */
	int32 GetCharacterLevelOverride() const { return CharacterLevelOverride; }

protected:

	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;

private:

	struct FPlayerEntry
	{
		TWeakObjectPtr<APlayerState> PlayerState;

		/** The last living pawn seen, to notice respawns. */
		TWeakObjectPtr<APawn> Pawn;

		/** Living Burrowers following this player. Dead ones are dropped when the death is seen. */
		TArray<TWeakObjectPtr<ABurrowerCharacter>> Burrowers;

		/** Seconds until the next spawn. Only runs while the player has a living pawn and room for one more. */
		float Countdown = 0.f;

		int32 NumDied = 0;

		bool bHadPawn = false;
	};

	TArray<FPlayerEntry> Entries;

	FTimerHandle PollTimerHandle;

	/** World time of the last poll; -1 = none yet. */
	double LastPollTime = -1.0;

	TSharedPtr<FStreamableHandle> BurrowerClassHandle;

	bool bActive = false;

	bool bWarnedMissingClass = false;

	bool bWarnedMissingClassInfo = false;

	/** SetDifficultyOverride: x SpawnInterval, MaxAlivePerPlayer (0 = the setting), new Burrowers' level (0 = their own). */
	float SpawnIntervalScale = 1.f;

	int32 MaxAlivePerPlayerOverride = 0;

	int32 CharacterLevelOverride = 0;

	/** SetSpawningPaused. */
	bool bSpawningPaused = false;

	/** Joins, leaves, respawns, deaths, retargeting and the countdowns. */
	void Poll();

	FPlayerEntry& FindOrAddEntry(APlayerState* PlayerState, const UBurrowerSettings& Settings);

	FPlayerEntry* FindEntry(const APlayerState* PlayerState);

	/** Drops dead or destroyed Burrowers (re-arming the countdown), removes far ones, retargets the rest. */
	void UpdateEntryBurrowers(FPlayerEntry& Entry, APawn* LivingPawn, const UBurrowerSettings& Settings);

	/** BurrowerClass from the settings (loaded), or null with a warning once. */
	UClass* ResolveBurrowerClass();

	/** Spawns one behind the pawn, following it, and adds it to the entry. */
	ABurrowerCharacter* SpawnBehind(FPlayerEntry& Entry, APawn* Pawn, const UBurrowerSettings& Settings);

	bool IsMapAllowed(const UBurrowerSettings& Settings) const;

	/** An AMyGameMode with DA_MyEnemyCharacterClassInfo (the kill dereferences it). Warns once if not. */
	bool HasEnemyClassInfo();
};
