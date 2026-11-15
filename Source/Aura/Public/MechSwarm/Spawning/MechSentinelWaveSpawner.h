// Mech Sentinel Swarm - level-placed wave spawner.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Mass/EntityHandle.h"
#include "MechSwarm/Core/MechSentinelSwarmSubsystem.h"
#include "MechSentinelWaveSpawner.generated.h"

class UMassEntityConfigAsset;

/** How the spawner moves on to the next wave. */
UENUM(BlueprintType)
enum class EMechSentinelWaveAdvance : uint8
{
	/** Next wave once every sentinel of the current wave is dead. */
	WhenCleared,
	/** Next wave after the wave's TimeLimit, even if sentinels are left. */
	OnTimer,
	/** Whichever happens first. */
	ClearedOrTimer
};

UENUM(BlueprintType)
enum class EMechSentinelWaveState : uint8
{
	Idle,
	/** Waiting DelayBefore of the upcoming wave. */
	Countdown,
	/** Spawning the wave over its SpawnDuration. */
	Spawning,
	/** Everything spawned, fighting. */
	Fighting,
	/** Last wave cleared and repeating is off. */
	Finished
};

/** One wave. Counts are multiplied by the spawner's CountMultiplier. */
USTRUCT(BlueprintType)
struct AURA_API FMechSentinelWave
{
	GENERATED_BODY()

	/** Sentinels in this wave. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Wave", meta = (ClampMin = "0"))
	int32 Count = 40;

	/** Seconds over which the wave is spawned (0 = all at once, still batched by SpawnBatchSize). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Wave", meta = (ClampMin = "0", ForceUnits = "s"))
	float SpawnDuration = 6.f;

	/** Countdown before the wave starts. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Wave", meta = (ClampMin = "0", ForceUnits = "s"))
	float DelayBefore = 4.f;

	/** For EMechSentinelWaveAdvance::OnTimer / ClearedOrTimer: seconds after the wave started until the next one (0 = never by timer). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Wave", meta = (ClampMin = "0", ForceUnits = "s"))
	float TimeLimit = 0.f;

	/** Multipliers applied to the attribute defaults of the entity config. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Wave|Scaling", meta = (ClampMin = "0.01"))
	float HealthMultiplier = 1.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Wave|Scaling", meta = (ClampMin = "0"))
	float ArmorMultiplier = 1.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Wave|Scaling", meta = (ClampMin = "0"))
	float DamageMultiplier = 1.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Wave|Scaling", meta = (ClampMin = "0.05"))
	float AttackSpeedMultiplier = 1.f;

	/** Per-sentinel MoveSpeedMultiplier attribute (the swarm's shared MovementSpeed is not changed). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Wave|Scaling", meta = (ClampMin = "0"))
	float MoveSpeedMultiplier = 1.f;
};

DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnMechSentinelWaveStarted, int32, WaveNumber, int32, SentinelCount);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnMechSentinelWaveCleared, int32, WaveNumber);

/**
 * Spawns sentinel Mass entities wave after wave (server). Place it in the level: it is replicated (always relevant)
 * so clients know the wave state and, just as important, build the entity template of EntityConfig before any
 * replicated sentinel arrives.
 *
 * Amount control: per-wave Count, CountMultiplier (runtime: SetCountMultiplier), repeat growth (ExtraCountPerRepeat),
 * caps (MaxAlive here, MaxAliveSentinels in the GameMode rules) and spawn pacing (SpawnDuration, SpawnBatchSize).
 */
UCLASS(Blueprintable)
class AURA_API AMechSentinelWaveSpawner : public AActor
{
	GENERATED_BODY()

public:
	AMechSentinelWaveSpawner();

	/** Builds the entity template of EntityConfig on this machine (server and clients). Safe to call often. */
	void EnsureTemplateBuilt();

	//----------------------------------------------------------------------//
	// Control (server)
	//----------------------------------------------------------------------//

	/** Starts from the first wave (or resumes a stopped spawner at its current wave). */
	UFUNCTION(BlueprintCallable, BlueprintAuthorityOnly, Category = "Mech Sentinels|Waves")
	void StartWaves(bool bRestartFromFirstWave = false);

	/** Stops spawning. Alive sentinels keep fighting. */
	UFUNCTION(BlueprintCallable, BlueprintAuthorityOnly, Category = "Mech Sentinels|Waves")
	void StopWaves();

	/** Skips the countdown / the rest of the current wave and starts the next one now. */
	UFUNCTION(BlueprintCallable, BlueprintAuthorityOnly, Category = "Mech Sentinels|Waves")
	void StartNextWave();

	/** Scales every wave count from now on (current wave included for what is not spawned yet). */
	UFUNCTION(BlueprintCallable, BlueprintAuthorityOnly, Category = "Mech Sentinels|Waves")
	void SetCountMultiplier(float NewMultiplier);

	/** Changes the count of one wave (0 based). */
	UFUNCTION(BlueprintCallable, BlueprintAuthorityOnly, Category = "Mech Sentinels|Waves")
	void SetWaveCount(int32 WaveIndex, int32 NewCount);

	/**
	 * Spawns sentinels outside the wave flow (they still count as alive for the current wave). They are created by the
	 * spawner's own tick later this frame, after the Mass phases, because Mass cannot create entities while a phase runs:
	 * at most SpawnBatchSize per frame, within MaxAlive and the rules' MaxAliveSentinels. What the caps leave out is
	 * dropped. Returns the number queued: 0 once the spawner has ended play (destroyed or unloaded).
	 */
	UFUNCTION(BlueprintCallable, BlueprintAuthorityOnly, Category = "Mech Sentinels|Waves")
	int32 SpawnSentinelsNow(int32 Count);

	/**
	 * Removes every sentinel this spawner created, on the spawner's own tick later this frame (after the Mass phases).
	 * Once the spawner has ended play (destroyed or unloaded), on the next timer tick instead, so it also works from the
	 * spawner's End Play and Destroyed events. bKill plays the death fall, otherwise they vanish. Cancels the
	 * SpawnSentinelsNow requests made before it.
	 */
	UFUNCTION(BlueprintCallable, BlueprintAuthorityOnly, Category = "Mech Sentinels|Waves")
	void DespawnAll(bool bKill = true);

	//----------------------------------------------------------------------//
	// State (replicated)
	//----------------------------------------------------------------------//

	/** 1 based number of the current / last wave, 0 before the first one. */
	UFUNCTION(BlueprintPure, Category = "Mech Sentinels|Waves")
	int32 GetCurrentWaveNumber() const { return CurrentWaveNumber; }

	UFUNCTION(BlueprintPure, Category = "Mech Sentinels|Waves")
	EMechSentinelWaveState GetWaveState() const { return WaveState; }

	/** Alive (not dead) sentinels of this spawner. */
	UFUNCTION(BlueprintPure, Category = "Mech Sentinels|Waves")
	int32 GetAliveCount() const { return AliveCount; }

	/** Sentinels of the current wave not spawned yet. */
	UFUNCTION(BlueprintPure, Category = "Mech Sentinels|Waves")
	int32 GetRemainingToSpawn() const { return RemainingToSpawn; }

	/** Planned size of the current wave (follows SetCountMultiplier / SetWaveCount). */
	UFUNCTION(BlueprintPure, Category = "Mech Sentinels|Waves")
	int32 GetCurrentWaveTotal() const { return CurrentWaveTotal; }

	UFUNCTION(BlueprintPure, Category = "Mech Sentinels|Waves")
	FName GetSwarmGroup() const;

	/** Server and clients (clients through the replicated wave number). */
	UPROPERTY(BlueprintAssignable, Category = "Mech Sentinels|Waves")
	FOnMechSentinelWaveStarted OnWaveStarted;

	/** Server only. */
	UPROPERTY(BlueprintAssignable, Category = "Mech Sentinels|Waves")
	FOnMechSentinelWaveCleared OnWaveCleared;

protected:
	virtual void PostInitializeComponents() override;
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
	virtual void Tick(float DeltaSeconds) override;
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	UFUNCTION()
	void OnRep_CurrentWaveNumber();

	//----------------------------------------------------------------------//
	// Config
	//----------------------------------------------------------------------//

	/** Mass entity config with the Mech Sentinel trait (+ Movement/Avoidance/Orientation/Visualization copies + Replication). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Mech Sentinels")
	TObjectPtr<UMassEntityConfigAsset> EntityConfig;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Mech Sentinels|Waves")
	TArray<FMechSentinelWave> Waves;

	/** After the last wave, keep repeating it (endless mode). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Mech Sentinels|Waves")
	bool bRepeatLastWave = true;

	/** Each repeat of the last wave adds this many sentinels. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Mech Sentinels|Waves", meta = (EditCondition = "bRepeatLastWave", ClampMin = "0"))
	int32 ExtraCountPerRepeat = 10;

	/** Each repeat of the last wave multiplies health / armor / damage by this (compounding). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Mech Sentinels|Waves", meta = (EditCondition = "bRepeatLastWave", ClampMin = "1"))
	float StatScalePerRepeat = 1.1f;

	/** Global amount knob: every wave count is multiplied by it. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Mech Sentinels|Waves", meta = (ClampMin = "0"))
	float CountMultiplier = 1.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Mech Sentinels|Waves")
	EMechSentinelWaveAdvance AdvanceMode = EMechSentinelWaveAdvance::WhenCleared;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Mech Sentinels|Waves")
	bool bAutoStart = true;

	/** Alive sentinels of this spawner at most (0 = only the global MaxAliveSentinels rule). Spawning waits while full. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Mech Sentinels|Spawning", meta = (ClampMin = "0"))
	int32 MaxAlive = 0;

	/** Max entities created per frame (smooths the cost of big waves). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Mech Sentinels|Spawning", meta = (ClampMin = "1"))
	int32 SpawnBatchSize = 25;

	/** Sentinels appear inside this ellipsoid around the spawner (cm). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Mech Sentinels|Spawning", meta = (ClampMin = "0", ForceUnits = "cm"))
	FVector SpawnExtent = FVector(1500.f, 1500.f, 400.f);

	/** Fallback locations used by this spawner's swarm group when every player is crowded. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Mech Sentinels|Targets")
	TArray<FMechSentinelFallbackPoint> FallbackTargets;

	/** Adds the spawner itself as an unlimited fallback point (the swarm hovers here when it has nowhere else to go). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Mech Sentinels|Targets")
	bool bSpawnerIsFallbackTarget = true;

	//----------------------------------------------------------------------//
	// Replicated state
	//----------------------------------------------------------------------//

	UPROPERTY(ReplicatedUsing = OnRep_CurrentWaveNumber, Transient)
	int32 CurrentWaveNumber = 0;

	UPROPERTY(Replicated, Transient)
	EMechSentinelWaveState WaveState = EMechSentinelWaveState::Idle;

	UPROPERTY(Replicated, Transient)
	int32 AliveCount = 0;

	UPROPERTY(Replicated, Transient)
	int32 RemainingToSpawn = 0;

	/** Replicated with the wave number so the client side OnWaveStarted reports the same count as the server. */
	UPROPERTY(Replicated, Transient)
	int32 CurrentWaveTotal = 0;

private:
	/** Wave definition for a 1 based wave number (repeats the last one with growth). */
	FMechSentinelWave ResolveWave(int32 WaveNumber, float& OutStatScale) const;
	int32 ResolveCount(const FMechSentinelWave& Wave, int32 WaveNumber) const;

	void BeginCountdown(int32 NextWaveNumber);
	void BeginWave(int32 WaveNumber);
	void FinishWaves();

	/** Spawns up to Count sentinels with the current wave scaling. Returns how many were created. */
	int32 SpawnBatch(int32 Count);

	/** Drops destroyed handles and recounts the alive sentinels. */
	void RefreshAlive();

	/** DespawnAll's work, run from Tick. */
	void DespawnAllNow(bool bKill);

	/** DespawnAll's work for a spawner that ended play: hands the sentinels to a timer (next tick, outside the phases). */
	void QueueDespawnOnTimer(bool bKill);

	/** Kills (bKill) or destroys the given entities; drops the destroyed ones from the array. Outside the Mass phases. */
	static void DespawnEntities(UWorld& World, TArray<FMassEntityHandle>& Entities, bool bKill);

	/** False on the server once play began: building a template then waits for Tick (see the .cpp). */
	bool CanBuildTemplateNow() const;

	/** Entities created by this spawner since the swarm last rebuilt its alive set (soft global cap). */
	int32 SpawnedSinceHashRefresh() const;

	FMassEntityManager* GetEntityManager() const;

	TArray<FMassEntityHandle> SpawnedEntities;

	FMechSentinelWave ActiveWave;
	float ActiveStatScale = 1.f;
	int32 ActiveWaveSpawned = 0;
	int32 PendingWaveNumber = 0;
	int32 SpawnedThisFrame = 0;
	uint64 SpawnedFrameNumber = 0;
	bool bClearedThisWave = false;
	float StateTimer = 0.f;
	float WaveElapsed = 0.f;
	float SpawnAccumulator = 0.f;
	bool bStopped = false;
	bool bFallbacksRegistered = false;

	/** SpawnSentinelsNow / DespawnAll requests, carried out by the next Tick. */
	int32 PendingManualSpawns = 0;
	bool bPendingDespawn = false;
	bool bPendingDespawnKill = true;
	/**
	 * Set in EndPlay (Destroyed, RemovedFromWorld) on the authority, cleared in BeginPlay: Tick will not run again, so
	 * DespawnAll uses a timer and SpawnSentinelsNow does nothing.
	 */
	bool bSpawnerEndedPlay = false;
};
