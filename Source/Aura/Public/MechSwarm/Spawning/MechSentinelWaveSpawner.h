// Mech Sentinel Swarm - level-placed wave spawner.

#pragma once

#include "CoreMinimal.h"
#include "Curves/CurveFloat.h"
#include "GameFramework/Actor.h"
#include "Mass/EntityHandle.h"
#include "MechSwarm/Core/MechSentinelSwarmSubsystem.h"
#include "MechSentinelWaveSpawner.generated.h"

class AMyHexPathSegment;
class AMyHexPathSpawner;
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
	ClearedOrTimer,
	/**
	 * Waves are started from outside: one per new path segment (bBindToPathSpawners) or StartWaveAtPoints. They may
	 * overlap, each one spawns and clears on its own, and nothing advances by itself.
	 */
	External UMETA(DisplayName = "External (path segments)")
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

/** Which corners of a path segment's bounds box get a spawn point of the segment's wave. */
UENUM(BlueprintType)
enum class EMechSentinelSegmentCorners : uint8
{
	/** The 4 top corners. */
	Top,
	/** The 4 bottom corners. */
	Bottom,
	/** All 8. */
	All
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

	/** Scales the rules' SelfBuffChance for this wave's sentinels (0 = never). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Wave|Scaling", meta = (ClampMin = "0"))
	float SelfBuffChanceMultiplier = 1.f;
};

/**
 * Curve mode (AMechSentinelWaveSpawner::bUseWaveCurves): one factor per wave field over the wave number. X = wave
 * number (1 based), Y = factor on the matching CurveBaseWave field. A curve without keys is a factor of 1. A float
 * curve asset in a curve's External Curve slot replaces it and can be shared between spawners. The defaults are linear
 * keys that are flat before wave 1 and keep growing past their last key.
 */
USTRUCT(BlueprintType)
struct AURA_API FMechSentinelWaveCurves
{
	GENERATED_BODY()

	/** Fills the default curves (see the .cpp). */
	FMechSentinelWaveCurves();

	/** x CurveBaseWave.Count, rounded. */
	UPROPERTY(EditAnywhere, Category = "Wave Curves")
	FRuntimeFloatCurve Count;

	/** x HealthMultiplier. */
	UPROPERTY(EditAnywhere, Category = "Wave Curves")
	FRuntimeFloatCurve Health;

	/** x ArmorMultiplier. */
	UPROPERTY(EditAnywhere, Category = "Wave Curves")
	FRuntimeFloatCurve Armor;

	/** x DamageMultiplier. */
	UPROPERTY(EditAnywhere, Category = "Wave Curves")
	FRuntimeFloatCurve Damage;

	/** x AttackSpeedMultiplier. */
	UPROPERTY(EditAnywhere, Category = "Wave Curves")
	FRuntimeFloatCurve AttackSpeed;

	/** x MoveSpeedMultiplier. */
	UPROPERTY(EditAnywhere, Category = "Wave Curves")
	FRuntimeFloatCurve MoveSpeed;

	/** x SelfBuffChanceMultiplier (0 = these waves never self-buff). */
	UPROPERTY(EditAnywhere, Category = "Wave Curves")
	FRuntimeFloatCurve SelfBuffChance;
};

/**
 * Runtime difficulty on top of the waves as designed (AMechSentinelWaveSpawner::SetDifficultyScale; the match's swarm
 * difficulty, SPEC_B B5.4). All 1 = the waves as designed. Each field multiplies the matching one of every resolved wave
 * (after the curves or the hand-made entry and the repeat growth, before the runtime clamps); Count goes next to
 * CountMultiplier, MaxAlive multiplies the spawner's own MaxAlive as placed.
 */
USTRUCT(BlueprintType)
struct AURA_API FMechSentinelDifficultyScale
{
	GENERATED_BODY()

	/** x every wave count (with CountMultiplier). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Difficulty", meta = (ClampMin = "0"))
	float Count = 1.f;

	/** x HealthMultiplier. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Difficulty", meta = (ClampMin = "0"))
	float Health = 1.f;

	/** x ArmorMultiplier. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Difficulty", meta = (ClampMin = "0"))
	float Armor = 1.f;

	/** x DamageMultiplier. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Difficulty", meta = (ClampMin = "0"))
	float Damage = 1.f;

	/** x AttackSpeedMultiplier. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Difficulty", meta = (ClampMin = "0"))
	float AttackSpeed = 1.f;

	/** x MoveSpeedMultiplier. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Difficulty", meta = (ClampMin = "0"))
	float MoveSpeed = 1.f;

	/** x SelfBuffChanceMultiplier (which already scales the rules' SelfBuffChance: scale only here, not the rules too). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Difficulty", meta = (ClampMin = "0"))
	float SelfBuffChance = 1.f;

	/** x the spawner's MaxAlive as placed (0 = unlimited stays unlimited). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Difficulty", meta = (ClampMin = "0"))
	float MaxAlive = 1.f;
};

DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnMechSentinelWaveStarted, int32, WaveNumber, int32, SentinelCount);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnMechSentinelWaveCleared, int32, WaveNumber);

/**
 * Spawns sentinel Mass entities wave after wave (server). Place it in the level: it is replicated (always relevant)
 * so clients know the wave state and, just as important, build the entity template of EntityConfig before any
 * replicated sentinel arrives.
 *
 * Amount control: per-wave Count, CountMultiplier (runtime: SetCountMultiplier), repeat growth (ExtraCountPerRepeat),
 * curves over the wave number (bUseWaveCurves), caps (MaxAlive here, MaxAliveSentinels in the GameMode rules) and
 * spawn pacing (SpawnDuration, SpawnBatchSize).
 *
 * External mode (endless path levels): every new segment of the level's AMyHexPathSpawners starts its own wave at the
 * corners of the segment's assumed bounds. Those waves overlap; each one counts down, spawns and clears on its own.
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

	/**
	 * Starts from the first wave (or resumes a stopped spawner at its current wave). External mode: only resumes (the
	 * waves come from the path segments and StartWaveAtPoints).
	 */
	UFUNCTION(BlueprintCallable, BlueprintAuthorityOnly, Category = "Mech Sentinels|Waves")
	void StartWaves(bool bRestartFromFirstWave = false);

	/** Stops spawning. Alive sentinels keep fighting. External mode: every wave pauses its countdown and spawning. */
	UFUNCTION(BlueprintCallable, BlueprintAuthorityOnly, Category = "Mech Sentinels|Waves")
	void StopWaves();

	/** StopWaves ran (or, external mode, bAutoStart was off at BeginPlay) and nothing started the waves since. The match's lobby resumes only the spawners that were running. */
	UFUNCTION(BlueprintPure, Category = "Mech Sentinels|Waves")
	bool IsStopped() const { return bStopped; }

	/**
	 * Skips the countdown / the rest of the current wave and starts the next one now. External mode: starts the next
	 * wave number at the spawner (inside SpawnExtent), without a countdown.
	 */
	UFUNCTION(BlueprintCallable, BlueprintAuthorityOnly, Category = "Mech Sentinels|Waves")
	void StartNextWave();

	/** Scales every wave count from now on (current wave included for what is not spawned yet, every started wave in External mode). */
	UFUNCTION(BlueprintCallable, BlueprintAuthorityOnly, Category = "Mech Sentinels|Waves")
	void SetCountMultiplier(float NewMultiplier);

	/** Changes the count of one wave (0 based). The waves in progress are re-planned. */
	UFUNCTION(BlueprintCallable, BlueprintAuthorityOnly, Category = "Mech Sentinels|Waves")
	void SetWaveCount(int32 WaveIndex, int32 NewCount);

	/**
	 * Runtime difficulty (the match's swarm difficulty) on top of the waves, the curves and CountMultiplier, which stay
	 * as designed. Sentinels spawned from now on get the new stats, the ones of waves already counting down or spawning
	 * included; alive sentinels keep theirs. Count re-plans the waves like SetCountMultiplier. MaxAlive scales the
	 * spawner's own MaxAlive as placed. Safe before BeginPlay: the scale is stored and BeginPlay applies it, so the waves
	 * the path's first segments queue in their own BeginPlay already spawn with it.
	 */
	UFUNCTION(BlueprintCallable, BlueprintAuthorityOnly, Category = "Mech Sentinels|Waves")
	void SetDifficultyScale(const FMechSentinelDifficultyScale& Scale);

	/** The scale SetDifficultyScale set (all 1 until then). */
	const FMechSentinelDifficultyScale& GetDifficultyScale() const { return DifficultyScale; }

	/**
	 * Spawns sentinels outside the wave flow (they still count as alive for the current wave). They are created by the
	 * spawner's own tick later this frame, after the Mass phases, because Mass cannot create entities while a phase runs:
	 * at most SpawnBatchSize per frame, within MaxAlive and the rules' MaxAliveSentinels. What the caps leave out is
	 * dropped. Returns the number queued: 0 from the spawner's end of play (destroyed or unloaded) until its level is
	 * shown again.
	 */
	UFUNCTION(BlueprintCallable, BlueprintAuthorityOnly, Category = "Mech Sentinels|Waves")
	int32 SpawnSentinelsNow(int32 Count);

	/**
	 * Starts a wave at world points. Meant for External mode (path segments call it), works in every mode. After the
	 * wave's DelayBefore its sentinels appear inside CornerSpawnExtent around the points in turn (no points: inside
	 * SpawnExtent around the spawner). Such waves overlap and each fires OnWaveStarted / OnWaveCleared on its own; in the
	 * other modes they run next to the regular waves and leave the replicated wave number and state alone.
	 * WaveNumber <= 0 = the next number after the highest one started so far. With a Source, what the wave has not
	 * spawned yet is dropped once Source is destroyed (a path segment left behind). Like SpawnSentinelsNow it only
	 * queues: the spawner's tick does the work, after the Mass phases. Returns the wave number: 0 without authority and
	 * from the spawner's end of play until its level is shown again.
	 */
	UFUNCTION(BlueprintCallable, BlueprintAuthorityOnly, Category = "Mech Sentinels|Waves")
	int32 StartWaveAtPoints(const TArray<FVector>& SpawnPoints, int32 WaveNumber, AActor* Source);

	/**
	 * Removes every sentinel this spawner created, on the spawner's own tick later this frame (after the Mass phases).
	 * Once the spawner has ended play (destroyed or unloaded), on the next timer tick instead, so it also works from the
	 * spawner's End Play and Destroyed events. bKill plays the death fall, otherwise they vanish. Cancels the
	 * SpawnSentinelsNow requests made before it, and what the waves started at points have not spawned yet.
	 */
	UFUNCTION(BlueprintCallable, BlueprintAuthorityOnly, Category = "Mech Sentinels|Waves")
	void DespawnAll(bool bKill = true);

	//----------------------------------------------------------------------//
	// State (replicated)
	//----------------------------------------------------------------------//

	/** 1 based number of the current / last wave, 0 before the first one. External mode: the highest one started. */
	UFUNCTION(BlueprintPure, Category = "Mech Sentinels|Waves")
	int32 GetCurrentWaveNumber() const { return CurrentWaveNumber; }

	UFUNCTION(BlueprintPure, Category = "Mech Sentinels|Waves")
	EMechSentinelWaveState GetWaveState() const { return WaveState; }

	/** Alive (not dead) sentinels of this spawner. */
	UFUNCTION(BlueprintPure, Category = "Mech Sentinels|Waves")
	int32 GetAliveCount() const { return AliveCount; }

	/** Sentinels of the current wave not spawned yet (External mode: of every started wave). */
	UFUNCTION(BlueprintPure, Category = "Mech Sentinels|Waves")
	int32 GetRemainingToSpawn() const { return RemainingToSpawn; }

	/** Planned size of the current wave (follows SetCountMultiplier / SetWaveCount). External mode: summed over the lanes that started it. */
	UFUNCTION(BlueprintPure, Category = "Mech Sentinels|Waves")
	int32 GetCurrentWaveTotal() const { return CurrentWaveTotal; }

	UFUNCTION(BlueprintPure, Category = "Mech Sentinels|Waves")
	FName GetSwarmGroup() const;

	/**
	 * What wave WaveNumber (1 based) spawns with: the curves, or the hand-made entry and the repeat growth, with the
	 * difficulty's stat scales (SetDifficultyScale), the runtime clamps and the repeat stat scale folded into the
	 * multipliers. Count is before CountMultiplier and the difficulty's Count.
	 */
	UFUNCTION(BlueprintPure, Category = "Mech Sentinels|Waves")
	FMechSentinelWave GetWaveDefinition(int32 WaveNumber) const;

	/** Server: waves started at points (path segments, StartWaveAtPoints) that are queued, counting down, spawning or not cleared yet. 0 on clients. */
	UFUNCTION(BlueprintPure, Category = "Mech Sentinels|Waves")
	int32 GetNumActiveWaves() const;

	/**
	 * Server and clients (clients through the replicated wave number). External mode: clients get one event for the
	 * waves that start within the same net update, and none for a wave numbered below the current one.
	 */
	UPROPERTY(BlueprintAssignable, Category = "Mech Sentinels|Waves")
	FOnMechSentinelWaveStarted OnWaveStarted;

	/** Server only. External mode: once per wave started at points (each lane on its own), in the order they clear. */
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

	/** AMyHexPathSpawner::OnSegmentSpawned (server, External mode): starts the segment's wave at its corners. */
	UFUNCTION()
	void HandlePathSegmentSpawned(AMyHexPathSpawner* PathSpawner, AMyHexPathSegment* Segment);

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

	/** Set it before play: switching between External and the other modes during play is not supported. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Mech Sentinels|Waves")
	EMechSentinelWaveAdvance AdvanceMode = EMechSentinelWaveAdvance::WhenCleared;

	/** Starts wave 1 on BeginPlay. External mode: the spawner is armed on BeginPlay, otherwise its waves wait for StartWaves. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Mech Sentinels|Waves")
	bool bAutoStart = true;

	/**
	 * Every wave is CurveBaseWave with each field scaled by its curve over the wave number (WaveCurves). The hand-made
	 * Waves and the repeat growth are ignored, and the waves never run out.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Mech Sentinels|Waves|Curves")
	bool bUseWaveCurves = false;

	/** The wave the curves scale (their factor 1). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Mech Sentinels|Waves|Curves", meta = (EditCondition = "bUseWaveCurves"))
	FMechSentinelWave CurveBaseWave;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Mech Sentinels|Waves|Curves", meta = (EditCondition = "bUseWaveCurves"))
	FMechSentinelWaveCurves WaveCurves;

	/**
	 * External mode: on BeginPlay, listen to every AMyHexPathSpawner in the level and start a wave at the corners of each
	 * new segment (lanes with bSpawnSentinelWaves; wave number = segment index - FirstSegmentWithSentinelWave + 1).
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Mech Sentinels|Waves|Path")
	bool bBindToPathSpawners = true;

	/** Which corners of the segment's bounds box get a spawn point. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Mech Sentinels|Waves|Path")
	EMechSentinelSegmentCorners SegmentCorners = EMechSentinelSegmentCorners::Top;

	/** Moves the corners toward the box centre by this much (cm), along both horizontal box axes. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Mech Sentinels|Waves|Path", meta = (ClampMin = "0", ForceUnits = "cm"))
	float CornerInset = 0.f;

	/** Raises (negative: lowers) the corners (cm). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Mech Sentinels|Waves|Path", meta = (ForceUnits = "cm"))
	float CornerHeightOffset = 0.f;

	/** Sentinels of a wave started at points (segment corners, StartWaveAtPoints) appear inside this ellipsoid around each point. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Mech Sentinels|Waves|Path", meta = (ClampMin = "0", ForceUnits = "cm"))
	FVector CornerSpawnExtent = FVector(800.f, 800.f, 300.f);

	/**
	 * 0 = unlimited. When more waves started at points than this still have sentinels left to spawn, the oldest ones
	 * drop what they have not spawned yet (their spawned sentinels fight on).
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Mech Sentinels|Waves|Path", meta = (ClampMin = "0"))
	int32 MaxActiveWaves = 0;

	/**
	 * Alive sentinels of this spawner at most (0 = only the global MaxAliveSentinels rule). Spawning waits while full.
	 * During play: the placed value x the difficulty's MaxAlive (SetDifficultyScale).
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Mech Sentinels|Spawning", meta = (ClampMin = "0"))
	int32 MaxAlive = 0;

	/** Runtime difficulty (SetDifficultyScale). All 1 = the waves as designed. */
	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Transient, Category = "Mech Sentinels|Difficulty")
	FMechSentinelDifficultyScale DifficultyScale;

	/** Max entities created per frame (smooths the cost of big waves). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Mech Sentinels|Spawning", meta = (ClampMin = "1"))
	int32 SpawnBatchSize = 25;

	/** Sentinels appear inside this ellipsoid around the spawner (cm). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Mech Sentinels|Spawning", meta = (ClampMin = "0", ForceUnits = "cm"))
	FVector SpawnExtent = FVector(1500.f, 1500.f, 400.f);

	/**
	 * A spawn location inside a registered obstacle (UMechSentinelObstacleSubsystem: the platforms) grown by this much
	 * (cm) is rolled again, up to 4 times. 0 = no check. Every mode.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Mech Sentinels|Spawning", meta = (ClampMin = "0", ForceUnits = "cm"))
	float SpawnObstacleClearance = 200.f;

	/** Fallback locations used by this spawner's swarm group when every player is crowded. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Mech Sentinels|Targets")
	TArray<FMechSentinelFallbackPoint> FallbackTargets;

	/**
	 * Adds the spawner itself as an unlimited fallback point (the swarm hovers here when it has nowhere else to go).
	 * Not in External mode: a fixed point at the start of an endless level would pull the overflow back there.
	 */
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
	/** One wave started at points (StartWaveAtPoints, a path segment). Server only. */
	struct FWaveRun
	{
		int32 WaveNumber = 0;
		/** Resolved when the run is created, with the repeat stat scale folded into the multipliers. */
		FMechSentinelWave Def;
		TArray<FVector> SpawnPoints;
		int32 NextPointIndex = 0;
		/** When one was given (bHadSource) and it is gone, the unspawned rest is dropped. */
		TWeakObjectPtr<AActor> Source;
		bool bHadSource = false;
		float DelayRemaining = 0.f;
		/** Seconds since the start. */
		float Elapsed = 0.f;
		float Accumulator = 0.f;
		int32 Total = 0;
		int32 Spawned = 0;
		int32 Remaining = 0;
		/** Not dead, refreshed every tick. */
		int32 Alive = 0;
		bool bStarted = false;
		/** The unspawned rest was dropped (DespawnAll, MaxActiveWaves, Source gone): re-plans leave the run alone. */
		bool bDropped = false;
		TArray<FMassEntityHandle> Entities;
	};

	/** A StartWaveAtPoints call; the next Tick turns it into a run. */
	struct FWaveRequest
	{
		TArray<FVector> SpawnPoints;
		int32 WaveNumber = 0;
		TWeakObjectPtr<AActor> Source;
		bool bHadSource = false;
		/** StartNextWave in External mode: no countdown. */
		bool bSkipDelay = false;
	};

	/** Wave definition for a 1 based wave number (curves, or the hand-made waves with repeat growth), clamped. */
	FMechSentinelWave ResolveWave(int32 WaveNumber, float& OutStatScale) const;
	int32 ResolveCount(const FMechSentinelWave& Wave, int32 WaveNumber) const;

	/** ResolveWave with the stat scale folded into the health, armor and damage multipliers. */
	FMechSentinelWave ResolveWaveFolded(int32 WaveNumber) const;

	/** Runtime clamps of a resolved wave (the ClampMin metadata only binds the editor). */
	void ClampWave(FMechSentinelWave& Wave) const;

	/** MaxAlive = the placed value x DifficultyScale.MaxAlive. Remembers the placed value the first time (BeginPlay). */
	void ApplyDifficultyMaxAlive();

	/** The scaling multipliers of From (health .. self-buff chance) into To; count and timing stay. */
	static void CopyWaveStats(const FMechSentinelWave& From, FMechSentinelWave& To);

	/** MaxAlive as placed, before DifficultyScale.MaxAlive; INDEX_NONE until ApplyDifficultyMaxAlive first runs. */
	int32 BaseMaxAlive = INDEX_NONE;

	/** True when the regular (not External) wave flow has a wave WaveNumber. */
	bool HasWave(int32 WaveNumber) const;

	void BeginCountdown(int32 NextWaveNumber);
	void BeginWave(int32 WaveNumber);
	void FinishWaves();

	/**
	 * Spawns up to Count sentinels with Def's scaling (health, armor and damage also x StatScale). Each one appears
	 * inside the Extent ellipsoid around the next of SpawnPoints (round robin from *PointCursor), or around the spawner
	 * when there are none. Appends them to RunEntities too, when given. Returns how many were created.
	 */
	int32 SpawnBatch(int32 Count, const FMechSentinelWave& Def, float StatScale, TConstArrayView<FVector> SpawnPoints, int32* PointCursor, const FVector& Extent, TArray<FMassEntityHandle>* RunEntities);

	/** Drops destroyed handles and recounts the alive sentinels. */
	void RefreshAlive();

	/** RefreshAlive for each run. */
	void RefreshRunsAlive();

	/** Tick of External mode. */
	void TickExternal(float DeltaSeconds);

	/** Queues a run request. Returns its wave number (0 when refused). */
	int32 QueueWaveRun(const TArray<FVector>& SpawnPoints, int32 WaveNumber, AActor* Source, bool bSkipDelay);

	/** Turns the queued requests into runs, then applies MaxActiveWaves. */
	void AcceptWaveRequests();

	void EnforceMaxActiveWaves();

	/**
	 * Counts down, starts, spawns (at most Budget entities in all) and clears the runs, oldest first, unless stopped.
	 * The events are broadcast at the end, so their handlers may call anything. bExternal: the runs drive the replicated
	 * wave number and state.
	 */
	void TickRuns(float DeltaSeconds, int32 Budget, bool bExternal);

	/** External mode: RemainingToSpawn, CurrentWaveTotal and WaveState from the runs. */
	void UpdateExternalAggregates();

	/** Re-plans the runs' totals after a count change. */
	void ReplanRuns();

	/** Drops the requests and what the runs have not spawned yet (DespawnAll). Runs that never started go on the next tick. */
	void CancelRuns();

	static void DropRunRemainder(FWaveRun& Run);

	/** BeginPlay, External mode: binds OnSegmentSpawned of every path spawner and catches up on their segments. */
	void BindToPathSpawners();
	void UnbindFromPathSpawners();

	/** The segment's corners (SegmentCorners, CornerInset, CornerHeightOffset), its location without bounds. */
	void GetSegmentSpawnPoints(const AMyHexPathSegment& Segment, TArray<FVector>& OutPoints) const;

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

	/** Every sentinel this spawner created, the runs' included. */
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
	 * Set in EndPlay (Destroyed, RemovedFromWorld) on the authority, cleared when the spawner initializes again (its
	 * level shown again): Tick will not run until then, so DespawnAll uses a timer and SpawnSentinelsNow does nothing.
	 */
	bool bSpawnerEndedPlay = false;

	/** Waves started at points, oldest first. */
	TArray<FWaveRun> Runs;
	TArray<FWaveRequest> PendingWaveRequests;
	/** Highest wave number started at points (or queued) so far. */
	int32 HighestRunWaveNumber = 0;

	TArray<TWeakObjectPtr<AMyHexPathSpawner>> BoundPathSpawners;
	/** Segments already handled (wave started or skipped): never twice. */
	TSet<TWeakObjectPtr<AMyHexPathSegment>> HandledSegments;
};
