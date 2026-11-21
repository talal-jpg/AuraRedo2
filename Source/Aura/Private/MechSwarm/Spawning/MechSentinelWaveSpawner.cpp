// Mech Sentinel Swarm - level-placed wave spawner.

#include "MechSwarm/Spawning/MechSentinelWaveSpawner.h"

#include "Actors/MyHexPathSegment.h"
#include "Actors/MyHexPathSpawner.h"
#include "Components/SceneComponent.h"
#include "Curves/RichCurve.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "MassCommandBuffer.h"
#include "MassEntityConfigAsset.h"
#include "MassEntityManager.h"
#include "MassEntityTemplate.h"
#include "MassEntityUtils.h"
#include "MassSpawnerSubsystem.h"
#include "Mass/EntityFragments.h"
#include "MechSwarm/Core/MechSentinelObstacleSubsystem.h"
#include "MechSwarm/Core/MechSentinelSwarmRules.h"
#include "MechSwarm/Core/MechSentinelSwarmSubsystem.h"
#include "MechSwarm/MassCopies/MassMovementFragments_Copy.h"
#include "MechSwarm/Sentinel/MechSentinelFragments.h"
#include "MechSwarm/Sentinel/MechSentinelTrait.h"
#include "Net/UnrealNetwork.h"
#include "TimerManager.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(MechSentinelWaveSpawner)

namespace MechSwarm::WaveSpawnerPrivate
{
	/** Linear keys (X wave number, Y factor), flat before the first key and growing on past the last one at its slope. */
	void SetGrowthCurve(FRuntimeFloatCurve& Curve, const TArray<FVector2f>& Keys)
	{
		FRichCurve& RichCurve = Curve.EditorCurveData;
		for (const FVector2f& Key : Keys)
		{
			const FKeyHandle Handle = RichCurve.AddKey(Key.X, Key.Y);
			RichCurve.SetKeyInterpMode(Handle, RCIM_Linear);
		}
		RichCurve.PreInfinityExtrap = RCCE_Constant;
		RichCurve.PostInfinityExtrap = RCCE_Linear;
	}

	/** A wave curve's factor at a wave number: 1 when the curve has no keys. */
	float EvalWaveCurve(const FRuntimeFloatCurve& Curve, const int32 WaveNumber)
	{
		const FRichCurve* RichCurve = Curve.GetRichCurveConst();
		return RichCurve && RichCurve->GetNumKeys() > 0 ? RichCurve->Eval(float(WaveNumber)) : 1.f;
	}
}

FMechSentinelWaveCurves::FMechSentinelWaveCurves()
{
	using MechSwarm::WaveSpawnerPrivate::SetGrowthCurve;

	// Easy first waves, stronger toward wave 40, and on past it at the last slope: the level is endless.
	SetGrowthCurve(Count, { FVector2f(1.f, 1.f), FVector2f(5.f, 1.5f), FVector2f(10.f, 2.2f), FVector2f(20.f, 3.5f), FVector2f(40.f, 5.5f) });
	SetGrowthCurve(Health, { FVector2f(1.f, 1.f), FVector2f(5.f, 1.4f), FVector2f(10.f, 2.f), FVector2f(20.f, 3.5f), FVector2f(40.f, 7.f) });
	SetGrowthCurve(Armor, { FVector2f(1.f, 1.f), FVector2f(10.f, 1.5f), FVector2f(20.f, 2.25f), FVector2f(40.f, 3.5f) });
	SetGrowthCurve(Damage, { FVector2f(1.f, 1.f), FVector2f(10.f, 1.5f), FVector2f(20.f, 2.3f), FVector2f(40.f, 4.f) });
	SetGrowthCurve(AttackSpeed, { FVector2f(1.f, 1.f), FVector2f(20.f, 1.3f), FVector2f(40.f, 1.5f) });
	SetGrowthCurve(MoveSpeed, { FVector2f(1.f, 1.f), FVector2f(20.f, 1.2f), FVector2f(40.f, 1.35f) });
	// No self-buffs in waves 1 and 2, then more and more often.
	SetGrowthCurve(SelfBuffChance, { FVector2f(1.f, 0.f), FVector2f(2.f, 0.f), FVector2f(3.f, 0.5f), FVector2f(6.f, 1.f), FVector2f(20.f, 1.5f) });
}

AMechSentinelWaveSpawner::AMechSentinelWaveSpawner()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.bStartWithTickEnabled = false;
	// Spawning creates entities with Mass's synchronous API, which asserts while any processor runs. The Mass phases
	// tick in TG_PrePhysics..TG_PostPhysics (and FrameEnd in TG_LastDemotable) and run on worker tasks next to the other
	// tick functions of their group, so a TG_PrePhysics actor could spawn in the middle of a phase. Nothing of Mass runs
	// during TG_PostUpdateWork.
	PrimaryActorTick.TickGroup = TG_PostUpdateWork;

	// Clients need it for the wave state and to build the entity template before replicated sentinels arrive.
	bReplicates = true;
	bAlwaysRelevant = true;
	SetNetUpdateFrequency(4.f);
	SetMinNetUpdateFrequency(1.f);

	RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));

	// A sensible default ramp; the last wave repeats with growth.
	FMechSentinelWave& First = Waves.AddDefaulted_GetRef();
	First.Count = 30;

	FMechSentinelWave& Second = Waves.AddDefaulted_GetRef();
	Second.Count = 60;
	Second.HealthMultiplier = 1.25f;
	Second.DamageMultiplier = 1.15f;

	FMechSentinelWave& Third = Waves.AddDefaulted_GetRef();
	Third.Count = 100;
	Third.SpawnDuration = 10.f;
	Third.HealthMultiplier = 1.5f;
	Third.ArmorMultiplier = 1.5f;
	Third.DamageMultiplier = 1.3f;
	Third.AttackSpeedMultiplier = 1.1f;

	// Wave 1 of curve mode; WaveCurves scale it for the later waves.
	CurveBaseWave.Count = 20;
	CurveBaseWave.SpawnDuration = 8.f;
	CurveBaseWave.DelayBefore = 2.f;
	CurveBaseWave.TimeLimit = 0.f;
}

void AMechSentinelWaveSpawner::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);

	DOREPLIFETIME(AMechSentinelWaveSpawner, CurrentWaveNumber);
	DOREPLIFETIME(AMechSentinelWaveSpawner, WaveState);
	DOREPLIFETIME(AMechSentinelWaveSpawner, AliveCount);
	DOREPLIFETIME(AMechSentinelWaveSpawner, RemainingToSpawn);
	DOREPLIFETIME(AMechSentinelWaveSpawner, CurrentWaveTotal);
}

//----------------------------------------------------------------------//
// Lifecycle
//----------------------------------------------------------------------//
void AMechSentinelWaveSpawner::PostInitializeComponents()
{
	Super::PostInitializeComponents();

	// A level shown again initializes all of its actors before any of their BeginPlay: spawn requests made from those
	// BeginPlays are queued again, as on the first play.
	bSpawnerEndedPlay = false;

	// As early as possible on clients: replicated sentinels need this template to spawn.
	const UWorld* World = GetWorld();
	if (World && World->IsGameWorld() && CanBuildTemplateNow())
	{
		EnsureTemplateBuilt();
	}
}

void AMechSentinelWaveSpawner::BeginPlay()
{
	// Also for instances or Blueprints saved with another group: see the constructor.
	SetTickGroup(TG_PostUpdateWork);
	// A spawner whose level streams back in plays again: DespawnAll and SpawnSentinelsNow go through Tick again.
	bSpawnerEndedPlay = false;

	Super::BeginPlay();

	if (CanBuildTemplateNow())
	{
		EnsureTemplateBuilt();
	}

	if (!HasAuthority())
	{
		return;
	}

	const bool bExternal = AdvanceMode == EMechSentinelWaveAdvance::External;

	if (UMechSentinelSwarmSubsystem* Swarm = UMechSentinelSwarmSubsystem::Get(this))
	{
		TArray<FMechSentinelFallbackPoint> Points = FallbackTargets;
		// Not in External mode: the spawner stays behind at the start of an endless level, the overflow would go back there.
		if (bSpawnerIsFallbackTarget && !bExternal)
		{
			FMechSentinelFallbackPoint& Self = Points.AddDefaulted_GetRef();
			Self.Actor = this;
			Self.Capacity = 0;
		}
		if (!Points.IsEmpty())
		{
			Swarm->RegisterFallbackTargets(GetSwarmGroup(), Points, this);
			bFallbacksRegistered = true;
		}
	}

	SetActorTickEnabled(true);
	if (bExternal)
	{
		// The waves come from the path segments and StartWaveAtPoints: armed now, or waiting for StartWaves.
		bStopped = !bAutoStart;
		if (bBindToPathSpawners)
		{
			BindToPathSpawners();
		}
	}
	else if (bAutoStart)
	{
		StartWaves(/*bRestartFromFirstWave*/true);
	}
}

void AMechSentinelWaveSpawner::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	// The spawner's tick will not run again, but its sentinels outlive it. From here on DespawnAll is finished on a timer
	// (which also runs outside the Mass phases): one queued earlier this frame, and one called from Event End Play,
	// OnEndPlay, Event Destroyed or OnDestroyed, which all run after this point. Spawn requests are dropped: queued ones
	// would otherwise burst out when an unloaded level streams back in.
	bSpawnerEndedPlay = HasAuthority()
		&& (EndPlayReason == EEndPlayReason::Destroyed || EndPlayReason == EEndPlayReason::RemovedFromWorld);
	if (bSpawnerEndedPlay)
	{
		PendingManualSpawns = 0;
		if (bPendingDespawn)
		{
			bPendingDespawn = false;
			QueueDespawnOnTimer(bPendingDespawnKill);
		}
	}

	// The waves started at points end here too; their sentinels stay in SpawnedEntities like every other one.
	PendingWaveRequests.Reset();
	Runs.Reset();
	UnbindFromPathSpawners();

	if (bFallbacksRegistered)
	{
		if (UMechSentinelSwarmSubsystem* Swarm = UMechSentinelSwarmSubsystem::Get(this))
		{
			Swarm->UnregisterFallbackTargets(this);
		}
		bFallbacksRegistered = false;
	}

	Super::EndPlay(EndPlayReason);
}

bool AMechSentinelWaveSpawner::CanBuildTemplateNow() const
{
	// Building a template creates a Mass archetype, which must not happen while a phase runs. Before play, and on
	// clients (replicated spawners are created during network receive, before the tick groups), it is safe. A spawner
	// spawned on the server during play may be spawned next to a phase: SpawnBatch builds the template from Tick.
	const UWorld* World = GetWorld();
	return !HasAuthority() || !World || !World->HasBegunPlay();
}

void AMechSentinelWaveSpawner::EnsureTemplateBuilt()
{
	if (!EntityConfig)
	{
		return;
	}
	if (UMechSentinelSwarmSubsystem* Swarm = UMechSentinelSwarmSubsystem::Get(this))
	{
		Swarm->RegisterEntityConfig(EntityConfig);
	}
}

FName AMechSentinelWaveSpawner::GetSwarmGroup() const
{
	const UMechSentinelTrait* Trait = EntityConfig ? Cast<UMechSentinelTrait>(EntityConfig->FindTrait(UMechSentinelTrait::StaticClass())) : nullptr;
	return Trait ? Trait->GetSwarmGroup() : NAME_None;
}

FMassEntityManager* AMechSentinelWaveSpawner::GetEntityManager() const
{
	return UE::Mass::Utils::GetEntityManager(GetWorld());
}

//----------------------------------------------------------------------//
// Wave flow
//----------------------------------------------------------------------//
FMechSentinelWave AMechSentinelWaveSpawner::ResolveWave(const int32 WaveNumber, float& OutStatScale) const
{
	using MechSwarm::WaveSpawnerPrivate::EvalWaveCurve;

	OutStatScale = 1.f;
	FMechSentinelWave Wave;

	if (bUseWaveCurves)
	{
		// Every field follows its curve over the wave number; the hand-made Waves are ignored.
		Wave = CurveBaseWave;
		Wave.Count = FMath::RoundToInt32(float(CurveBaseWave.Count) * EvalWaveCurve(WaveCurves.Count, WaveNumber));
		Wave.HealthMultiplier *= EvalWaveCurve(WaveCurves.Health, WaveNumber);
		Wave.ArmorMultiplier *= EvalWaveCurve(WaveCurves.Armor, WaveNumber);
		Wave.DamageMultiplier *= EvalWaveCurve(WaveCurves.Damage, WaveNumber);
		Wave.AttackSpeedMultiplier *= EvalWaveCurve(WaveCurves.AttackSpeed, WaveNumber);
		Wave.MoveSpeedMultiplier *= EvalWaveCurve(WaveCurves.MoveSpeed, WaveNumber);
		Wave.SelfBuffChanceMultiplier *= EvalWaveCurve(WaveCurves.SelfBuffChance, WaveNumber);
	}
	else if (!Waves.IsEmpty() && WaveNumber >= 1)
	{
		const int32 Index = WaveNumber - 1;
		if (Index < Waves.Num())
		{
			Wave = Waves[Index];
		}
		else
		{
			// Endless mode: the last wave again, bigger and tougher each time.
			const int32 Repeats = Index - (Waves.Num() - 1);
			Wave = Waves.Last();
			Wave.Count += ExtraCountPerRepeat * Repeats;
			OutStatScale = FMath::Pow(StatScalePerRepeat, float(Repeats));
		}
	}

	ClampWave(Wave);
	return Wave;
}

void AMechSentinelWaveSpawner::ClampWave(FMechSentinelWave& Wave) const
{
	// The ClampMin metadata only binds the editor; curves and Blueprint writes can go past it. In the auto-advancing
	// modes a wave of 0 would clear at once and push the wave number on.
	Wave.Count = FMath::Max(Wave.Count, AdvanceMode == EMechSentinelWaveAdvance::External ? 0 : 1);
	Wave.SpawnDuration = FMath::Max(Wave.SpawnDuration, 0.f);
	Wave.DelayBefore = FMath::Max(Wave.DelayBefore, 0.f);
	Wave.TimeLimit = FMath::Max(Wave.TimeLimit, 0.f);
	Wave.HealthMultiplier = FMath::Max(Wave.HealthMultiplier, 0.01f);
	Wave.ArmorMultiplier = FMath::Max(Wave.ArmorMultiplier, 0.f);
	Wave.DamageMultiplier = FMath::Max(Wave.DamageMultiplier, 0.f);
	Wave.AttackSpeedMultiplier = FMath::Max(Wave.AttackSpeedMultiplier, 0.05f);
	Wave.MoveSpeedMultiplier = FMath::Max(Wave.MoveSpeedMultiplier, 0.f);
	Wave.SelfBuffChanceMultiplier = FMath::Max(Wave.SelfBuffChanceMultiplier, 0.f);
}

FMechSentinelWave AMechSentinelWaveSpawner::ResolveWaveFolded(const int32 WaveNumber) const
{
	float StatScale = 1.f;
	FMechSentinelWave Wave = ResolveWave(WaveNumber, StatScale);
	Wave.HealthMultiplier *= StatScale;
	Wave.ArmorMultiplier *= StatScale;
	Wave.DamageMultiplier *= StatScale;
	// StatScalePerRepeat may have been set out of the editor's range at runtime.
	ClampWave(Wave);
	return Wave;
}

FMechSentinelWave AMechSentinelWaveSpawner::GetWaveDefinition(const int32 WaveNumber) const
{
	return ResolveWaveFolded(WaveNumber);
}

int32 AMechSentinelWaveSpawner::ResolveCount(const FMechSentinelWave& Wave, const int32 WaveNumber) const
{
	return FMath::Max(0, FMath::RoundToInt32(float(Wave.Count) * CountMultiplier));
}

bool AMechSentinelWaveSpawner::HasWave(const int32 WaveNumber) const
{
	return bUseWaveCurves || WaveNumber <= Waves.Num() || (bRepeatLastWave && Waves.Num() > 0);
}

void AMechSentinelWaveSpawner::StartWaves(const bool bRestartFromFirstWave)
{
	if (!HasAuthority())
	{
		return;
	}

	bStopped = false;
	SetActorTickEnabled(true);

	// The waves come from the path segments and StartWaveAtPoints: nothing to count down, nothing to finish.
	if (AdvanceMode == EMechSentinelWaveAdvance::External)
	{
		return;
	}

	// Nothing to run: report the waves as finished right away instead of sitting in a countdown forever.
	if (!HasWave(1))
	{
		FinishWaves();
		return;
	}

	if (bRestartFromFirstWave || CurrentWaveNumber == 0 || WaveState == EMechSentinelWaveState::Idle || WaveState == EMechSentinelWaveState::Finished)
	{
		BeginCountdown(1);
	}
	// Otherwise: resume where StopWaves left off.
}

void AMechSentinelWaveSpawner::StopWaves()
{
	bStopped = true;
}

void AMechSentinelWaveSpawner::StartNextWave()
{
	if (!HasAuthority())
	{
		return;
	}

	if (AdvanceMode == EMechSentinelWaveAdvance::External)
	{
		bStopped = false;
		QueueWaveRun(TArray<FVector>(), 0, nullptr, /*bSkipDelay*/true);
		return;
	}

	const int32 Next = (WaveState == EMechSentinelWaveState::Countdown) ? PendingWaveNumber : CurrentWaveNumber + 1;
	if (HasWave(Next))
	{
		bStopped = false;
		BeginWave(Next);
	}
}

void AMechSentinelWaveSpawner::SetCountMultiplier(const float NewMultiplier)
{
	CountMultiplier = FMath::Max(0.f, NewMultiplier);

	// Re-plan what is left of the current wave.
	if (AdvanceMode != EMechSentinelWaveAdvance::External
		&& (WaveState == EMechSentinelWaveState::Spawning || WaveState == EMechSentinelWaveState::Fighting))
	{
		const int32 NewTotal = ResolveCount(ActiveWave, CurrentWaveNumber);
		RemainingToSpawn = FMath::Max(0, NewTotal - ActiveWaveSpawned);
		CurrentWaveTotal = ActiveWaveSpawned + RemainingToSpawn;
		if (RemainingToSpawn > 0)
		{
			WaveState = EMechSentinelWaveState::Spawning;
		}
	}

	// And of the waves started at points.
	ReplanRuns();
}

void AMechSentinelWaveSpawner::SetWaveCount(const int32 WaveIndex, const int32 NewCount)
{
	if (!Waves.IsValidIndex(WaveIndex))
	{
		return;
	}

	Waves[WaveIndex].Count = FMath::Max(0, NewCount);

	// The waves started at points take their new count (the last entry also sizes the repeats after it).
	for (FWaveRun& Run : Runs)
	{
		Run.Def.Count = ResolveWaveFolded(Run.WaveNumber).Count;
	}

	const bool bIsCurrent = AdvanceMode != EMechSentinelWaveAdvance::External
		&& WaveIndex == CurrentWaveNumber - 1
		&& (WaveState == EMechSentinelWaveState::Spawning || WaveState == EMechSentinelWaveState::Fighting);
	if (bIsCurrent)
	{
		// Re-resolved, not copied: the runtime clamps (and curves, which ignore the entry) apply as at the wave's start.
		float StatScale = 1.f;
		ActiveWave.Count = ResolveWave(CurrentWaveNumber, StatScale).Count;
		SetCountMultiplier(CountMultiplier);
	}
	else
	{
		ReplanRuns();
	}
}

void AMechSentinelWaveSpawner::BeginCountdown(const int32 NextWaveNumber)
{
	float StatScale = 1.f;
	const FMechSentinelWave Next = ResolveWave(NextWaveNumber, StatScale);
	PendingWaveNumber = NextWaveNumber;
	StateTimer = Next.DelayBefore;
	RemainingToSpawn = 0;
	WaveState = EMechSentinelWaveState::Countdown;
}

void AMechSentinelWaveSpawner::BeginWave(const int32 WaveNumber)
{
	ActiveWave = ResolveWave(WaveNumber, ActiveStatScale);
	CurrentWaveNumber = WaveNumber;
	ActiveWaveSpawned = 0;
	RemainingToSpawn = ResolveCount(ActiveWave, WaveNumber);
	CurrentWaveTotal = RemainingToSpawn;
	SpawnAccumulator = 0.f;
	WaveElapsed = 0.f;
	bClearedThisWave = false;
	WaveState = EMechSentinelWaveState::Spawning;

	// Server side broadcast; clients broadcast from OnRep_CurrentWaveNumber.
	OnWaveStarted.Broadcast(CurrentWaveNumber, CurrentWaveTotal);
}

void AMechSentinelWaveSpawner::FinishWaves()
{
	RemainingToSpawn = 0;
	WaveState = EMechSentinelWaveState::Finished;
}

void AMechSentinelWaveSpawner::OnRep_CurrentWaveNumber()
{
	// CurrentWaveTotal is declared after CurrentWaveNumber but replicated in the same bunch (both change in BeginWave),
	// and OnRep functions run after every property of the bunch is applied.
	OnWaveStarted.Broadcast(CurrentWaveNumber, CurrentWaveTotal);
}

void AMechSentinelWaveSpawner::Tick(const float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	if (!HasAuthority())
	{
		return;
	}

	// Overlapping waves started from outside: a flow of its own (below). The other modes run the single-wave flow.
	if (AdvanceMode == EMechSentinelWaveAdvance::External)
	{
		TickExternal(DeltaSeconds);
		return;
	}

	if (bPendingDespawn)
	{
		bPendingDespawn = false;
		DespawnAllNow(bPendingDespawnKill);
	}

	RefreshAlive();
	RefreshRunsAlive();

	// What the manual spawns and the regular wave leave of this frame's batch goes to the waves started at points.
	int32 RunBudget = SpawnBatchSize;
	if (PendingManualSpawns > 0)
	{
		const int32 Requested = FMath::Min(PendingManualSpawns, SpawnBatchSize);
		RunBudget -= SpawnBatch(Requested, ActiveWave, ActiveStatScale, TConstArrayView<FVector>(), nullptr, SpawnExtent, nullptr);
		// Whatever the caps did not allow is dropped, not retried.
		PendingManualSpawns -= Requested;
	}

	AcceptWaveRequests();

	if (bStopped)
	{
		return;
	}

	switch (WaveState)
	{
	case EMechSentinelWaveState::Countdown:
		StateTimer -= DeltaSeconds;
		if (StateTimer <= 0.f)
		{
			BeginWave(PendingWaveNumber);
		}
		break;

	case EMechSentinelWaveState::Spawning:
	case EMechSentinelWaveState::Fighting:
	{
		WaveElapsed += DeltaSeconds;

		if (RemainingToSpawn > 0)
		{
			const int32 WaveTotal = ActiveWaveSpawned + RemainingToSpawn;
			const float Rate = ActiveWave.SpawnDuration > KINDA_SMALL_NUMBER ? float(WaveTotal) / ActiveWave.SpawnDuration : float(WaveTotal);
			SpawnAccumulator = FMath::Min(SpawnAccumulator + Rate * DeltaSeconds, float(RemainingToSpawn));
			if (ActiveWave.SpawnDuration <= KINDA_SMALL_NUMBER)
			{
				SpawnAccumulator = float(RemainingToSpawn);
			}

			const int32 Wanted = FMath::Min3(FMath::FloorToInt32(SpawnAccumulator), SpawnBatchSize, RemainingToSpawn);
			if (Wanted > 0)
			{
				const int32 Spawned = SpawnBatch(Wanted, ActiveWave, ActiveStatScale, TConstArrayView<FVector>(), nullptr, SpawnExtent, nullptr);
				SpawnAccumulator -= float(Spawned);
				RemainingToSpawn -= Spawned;
				ActiveWaveSpawned += Spawned;
				RunBudget -= Spawned;
			}
		}
		if (RemainingToSpawn <= 0)
		{
			WaveState = EMechSentinelWaveState::Fighting;
		}

		const bool bCleared = WaveState == EMechSentinelWaveState::Fighting && AliveCount == 0;
		if (bCleared && !bClearedThisWave)
		{
			bClearedThisWave = true;
			OnWaveCleared.Broadcast(CurrentWaveNumber);
		}

		const bool bTimerDone = ActiveWave.TimeLimit > 0.f && WaveElapsed >= ActiveWave.TimeLimit;
		bool bAdvance = false;
		switch (AdvanceMode)
		{
		case EMechSentinelWaveAdvance::WhenCleared:
			bAdvance = bCleared;
			break;
		case EMechSentinelWaveAdvance::OnTimer:
			// Without a time limit the timer never fires: fall back to clearing.
			bAdvance = ActiveWave.TimeLimit > 0.f ? bTimerDone : bCleared;
			break;
		case EMechSentinelWaveAdvance::ClearedOrTimer:
			bAdvance = bCleared || bTimerDone;
			break;
		default:
			break;
		}

		if (bAdvance)
		{
			const int32 Next = CurrentWaveNumber + 1;
			if (HasWave(Next))
			{
				BeginCountdown(Next);
			}
			else if (bCleared)
			{
				FinishWaves();
			}
		}
		break;
	}

	case EMechSentinelWaveState::Idle:
	case EMechSentinelWaveState::Finished:
	default:
		break;
	}

	// Waves started at points run next to the regular ones and leave their replicated state alone.
	TickRuns(DeltaSeconds, RunBudget, /*bExternal*/false);
}

//----------------------------------------------------------------------//
// External mode: overlapping waves started at points
//----------------------------------------------------------------------//
void AMechSentinelWaveSpawner::TickExternal(const float DeltaSeconds)
{
	if (bPendingDespawn)
	{
		bPendingDespawn = false;
		DespawnAllNow(bPendingDespawnKill);
	}

	RefreshAlive();
	RefreshRunsAlive();

	// One batch per frame for the manual spawns and every wave together.
	int32 Budget = FMath::Max(SpawnBatchSize, 1);
	if (PendingManualSpawns > 0)
	{
		const int32 Requested = FMath::Min(PendingManualSpawns, Budget);
		Budget -= SpawnBatch(Requested, ActiveWave, ActiveStatScale, TConstArrayView<FVector>(), nullptr, SpawnExtent, nullptr);
		// Whatever the caps did not allow is dropped, not retried.
		PendingManualSpawns -= Requested;
	}

	AcceptWaveRequests();

	TickRuns(DeltaSeconds, Budget, /*bExternal*/true);
}

int32 AMechSentinelWaveSpawner::StartWaveAtPoints(const TArray<FVector>& SpawnPoints, const int32 WaveNumber, AActor* Source)
{
	return QueueWaveRun(SpawnPoints, WaveNumber, Source, /*bSkipDelay*/false);
}

int32 AMechSentinelWaveSpawner::QueueWaveRun(const TArray<FVector>& SpawnPoints, const int32 WaveNumber, AActor* Source, const bool bSkipDelay)
{
	// After end play the tick that would run it does not come.
	if (!HasAuthority() || bSpawnerEndedPlay)
	{
		return 0;
	}

	const int32 Number = WaveNumber > 0 ? WaveNumber : FMath::Max(HighestRunWaveNumber, CurrentWaveNumber) + 1;
	HighestRunWaveNumber = FMath::Max(HighestRunWaveNumber, Number);

	// Like SpawnSentinelsNow: the caller may be ticking next to a running Mass phase, so Tick (TG_PostUpdateWork) runs it.
	FWaveRequest& Request = PendingWaveRequests.AddDefaulted_GetRef();
	Request.SpawnPoints = SpawnPoints;
	Request.WaveNumber = Number;
	Request.Source = Source;
	Request.bHadSource = Source != nullptr;
	Request.bSkipDelay = bSkipDelay;

	SetActorTickEnabled(true);
	return Number;
}

void AMechSentinelWaveSpawner::AcceptWaveRequests()
{
	if (PendingWaveRequests.IsEmpty())
	{
		return;
	}

	for (FWaveRequest& Request : PendingWaveRequests)
	{
		FWaveRun& Run = Runs.AddDefaulted_GetRef();
		Run.WaveNumber = Request.WaveNumber;
		Run.Def = ResolveWaveFolded(Request.WaveNumber);
		Run.SpawnPoints = MoveTemp(Request.SpawnPoints);
		Run.Source = Request.Source;
		Run.bHadSource = Request.bHadSource;
		Run.DelayRemaining = Request.bSkipDelay ? 0.f : Run.Def.DelayBefore;
		Run.Total = ResolveCount(Run.Def, Run.WaveNumber);
		Run.Remaining = Run.Total;
	}
	PendingWaveRequests.Reset();

	EnforceMaxActiveWaves();
}

void AMechSentinelWaveSpawner::EnforceMaxActiveWaves()
{
	if (MaxActiveWaves <= 0)
	{
		return;
	}

	int32 WithRemainder = 0;
	for (const FWaveRun& Run : Runs)
	{
		WithRemainder += Run.Remaining > 0 ? 1 : 0;
	}

	// Oldest first: the newest waves are the ones near the players.
	for (int32 Index = 0; Index < Runs.Num() && WithRemainder > MaxActiveWaves; ++Index)
	{
		if (Runs[Index].Remaining > 0)
		{
			DropRunRemainder(Runs[Index]);
			--WithRemainder;
		}
	}
}

void AMechSentinelWaveSpawner::DropRunRemainder(FWaveRun& Run)
{
	Run.Remaining = 0;
	Run.Total = Run.Spawned;
	Run.Accumulator = 0.f;
	Run.bDropped = true;
}

void AMechSentinelWaveSpawner::TickRuns(const float DeltaSeconds, int32 Budget, const bool bExternal)
{
	TArray<TPair<int32, int32>, TInlineAllocator<4>> StartedWaves;
	TArray<int32, TInlineAllocator<4>> ClearedWaves;

	if (!bStopped)
	{
		for (int32 Index = 0; Index < Runs.Num(); ++Index)
		{
			FWaveRun& Run = Runs[Index];

			// Its segment was destroyed behind the lead: nobody is near those points any more.
			if (Run.bHadSource && !Run.bDropped && !Run.Source.IsValid())
			{
				DropRunRemainder(Run);
			}

			if (!Run.bStarted)
			{
				// Cancelled before it started: it never was a wave, so no events.
				if (Run.bDropped)
				{
					Runs.RemoveAt(Index--);
					continue;
				}

				Run.DelayRemaining -= DeltaSeconds;
				if (Run.DelayRemaining > 0.f)
				{
					continue;
				}

				Run.bStarted = true;
				StartedWaves.Emplace(Run.WaveNumber, Run.Total);

				if (bExternal)
				{
					// The replicated wave number is the highest one started (clients broadcast OnWaveStarted from it).
					if (Run.WaveNumber > CurrentWaveNumber)
					{
						CurrentWaveNumber = Run.WaveNumber;
					}
					if (Run.WaveNumber == CurrentWaveNumber)
					{
						// SpawnSentinelsNow uses the latest wave's scaling, as in the other modes.
						ActiveWave = Run.Def;
						ActiveStatScale = 1.f;
					}
					ForceNetUpdate();
				}

				// Spawning starts on the next tick, as for a regular wave.
				continue;
			}

			Run.Elapsed += DeltaSeconds;

			if (Run.Remaining > 0)
			{
				// The pacing of a regular wave: Total / SpawnDuration per second, or everything at once.
				const int32 RunTotal = Run.Spawned + Run.Remaining;
				const bool bAllAtOnce = Run.Def.SpawnDuration <= KINDA_SMALL_NUMBER;
				const float Rate = bAllAtOnce ? float(RunTotal) : float(RunTotal) / Run.Def.SpawnDuration;
				Run.Accumulator = bAllAtOnce ? float(Run.Remaining) : FMath::Min(Run.Accumulator + Rate * DeltaSeconds, float(Run.Remaining));

				// The oldest waves take the frame's batch first.
				const int32 Wanted = FMath::Min3(FMath::FloorToInt32(Run.Accumulator), Budget, Run.Remaining);
				if (Wanted > 0)
				{
					const FVector& Extent = Run.SpawnPoints.IsEmpty() ? SpawnExtent : CornerSpawnExtent;
					const int32 Spawned = SpawnBatch(Wanted, Run.Def, 1.f, Run.SpawnPoints, &Run.NextPointIndex, Extent, &Run.Entities);
					Run.Accumulator -= float(Spawned);
					Run.Remaining -= Spawned;
					Run.Spawned += Spawned;
					Run.Alive += Spawned;
					Budget -= Spawned;
				}
			}

			if (Run.Remaining <= 0 && Run.Alive <= 0)
			{
				ClearedWaves.Add(Run.WaveNumber);
				Runs.RemoveAt(Index--);
			}
		}
	}

	if (bExternal)
	{
		UpdateExternalAggregates();
	}

	// Last, so the handlers may start, stop or despawn waves, or destroy the spawner.
	for (const TPair<int32, int32>& Started : StartedWaves)
	{
		OnWaveStarted.Broadcast(Started.Key, Started.Value);
	}
	for (const int32 WaveNumber : ClearedWaves)
	{
		OnWaveCleared.Broadcast(WaveNumber);
	}
}

void AMechSentinelWaveSpawner::UpdateExternalAggregates()
{
	int32 Remaining = 0;
	int32 CurrentTotal = 0;
	bool bCurrentFound = false;
	bool bAnySpawning = false;
	bool bAnyCountdown = false;

	for (const FWaveRun& Run : Runs)
	{
		if (!Run.bStarted)
		{
			bAnyCountdown |= !Run.bDropped;
			continue;
		}

		Remaining += Run.Remaining;
		bAnySpawning |= Run.Remaining > 0;

		// Every lane's part of the current wave.
		if (Run.WaveNumber == CurrentWaveNumber)
		{
			CurrentTotal += Run.Total;
			bCurrentFound = true;
		}
	}

	RemainingToSpawn = Remaining;
	if (bCurrentFound)
	{
		CurrentWaveTotal = CurrentTotal;
	}

	if (bAnySpawning)
	{
		WaveState = EMechSentinelWaveState::Spawning;
	}
	else if (AliveCount > 0)
	{
		WaveState = EMechSentinelWaveState::Fighting;
	}
	else if (bAnyCountdown)
	{
		WaveState = EMechSentinelWaveState::Countdown;
	}
	else
	{
		WaveState = EMechSentinelWaveState::Idle;
	}
}

void AMechSentinelWaveSpawner::ReplanRuns()
{
	if (Runs.IsEmpty())
	{
		return;
	}

	for (FWaveRun& Run : Runs)
	{
		// What was dropped stays dropped.
		if (Run.bDropped)
		{
			continue;
		}

		const int32 NewTotal = ResolveCount(Run.Def, Run.WaveNumber);
		Run.Remaining = FMath::Max(0, NewTotal - Run.Spawned);
		Run.Total = Run.Spawned + Run.Remaining;
	}

	EnforceMaxActiveWaves();

	if (AdvanceMode == EMechSentinelWaveAdvance::External)
	{
		UpdateExternalAggregates();
	}
}

void AMechSentinelWaveSpawner::CancelRuns()
{
	PendingWaveRequests.Reset();

	for (FWaveRun& Run : Runs)
	{
		DropRunRemainder(Run);
	}
}

int32 AMechSentinelWaveSpawner::GetNumActiveWaves() const
{
	int32 Num = PendingWaveRequests.Num();
	for (const FWaveRun& Run : Runs)
	{
		// One cancelled before it started is only waiting to be removed.
		Num += (Run.bStarted || !Run.bDropped) ? 1 : 0;
	}
	return Num;
}

void AMechSentinelWaveSpawner::RefreshRunsAlive()
{
	if (Runs.IsEmpty())
	{
		return;
	}

	FMassEntityManager* EntityManager = GetEntityManager();
	for (FWaveRun& Run : Runs)
	{
		if (!EntityManager)
		{
			Run.Entities.Reset();
			Run.Alive = 0;
			continue;
		}

		int32 Alive = 0;
		for (int32 Index = Run.Entities.Num() - 1; Index >= 0; --Index)
		{
			const FMassEntityHandle Entity = Run.Entities[Index];
			if (!EntityManager->IsEntityActive(Entity))
			{
				Run.Entities.RemoveAtSwap(Index, EAllowShrinking::No);
				continue;
			}

			const FMechSentinelStateFragment* State = EntityManager->GetFragmentDataPtr<FMechSentinelStateFragment>(Entity);
			if (State && State->State != EMechSentinelState::Dead)
			{
				++Alive;
			}
		}
		Run.Alive = Alive;
	}
}

//----------------------------------------------------------------------//
// External mode: path segments
//----------------------------------------------------------------------//
void AMechSentinelWaveSpawner::BindToPathSpawners()
{
	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}

	for (TActorIterator<AMyHexPathSpawner> It(World); It; ++It)
	{
		AMyHexPathSpawner* PathSpawner = *It;
		if (!IsValid(PathSpawner))
		{
			continue;
		}

		PathSpawner->OnSegmentSpawned.AddUniqueDynamic(this, &ThisClass::HandlePathSegmentSpawned);
		BoundPathSpawners.AddUnique(PathSpawner);

		// The path spawners that began play first have built their InitialSegments already.
		for (AMyHexPathSegment* Segment : PathSpawner->GetSegments())
		{
			HandlePathSegmentSpawned(PathSpawner, Segment);
		}
	}
}

void AMechSentinelWaveSpawner::UnbindFromPathSpawners()
{
	for (const TWeakObjectPtr<AMyHexPathSpawner>& WeakPathSpawner : BoundPathSpawners)
	{
		if (AMyHexPathSpawner* PathSpawner = WeakPathSpawner.Get())
		{
			PathSpawner->OnSegmentSpawned.RemoveDynamic(this, &ThisClass::HandlePathSegmentSpawned);
		}
	}
	BoundPathSpawners.Reset();
}

void AMechSentinelWaveSpawner::HandlePathSegmentSpawned(AMyHexPathSpawner* PathSpawner, AMyHexPathSegment* Segment)
{
	if (AdvanceMode != EMechSentinelWaveAdvance::External || !HasAuthority() || !IsValid(PathSpawner) || !IsValid(Segment))
	{
		return;
	}

	// Each segment once: the catch-up in BeginPlay and the event can both report it.
	const TWeakObjectPtr<AMyHexPathSegment> WeakSegment(Segment);
	if (HandledSegments.Contains(WeakSegment))
	{
		return;
	}

	// Segments left behind are destroyed: forget them now and then.
	if (HandledSegments.Num() >= 64)
	{
		for (auto It = HandledSegments.CreateIterator(); It; ++It)
		{
			if (!It->IsValid())
			{
				It.RemoveCurrent();
			}
		}
	}
	HandledSegments.Add(WeakSegment);

	if (!PathSpawner->ShouldSpawnSentinelWaves())
	{
		return;
	}

	// Every lane counts from its own first segment, so the lanes' segment k all get wave k.
	const int32 WaveNumber = Segment->GetSegmentIndex() - PathSpawner->GetFirstSegmentWithSentinelWave() + 1;
	if (WaveNumber < 1)
	{
		return;
	}

	TArray<FVector> Points;
	GetSegmentSpawnPoints(*Segment, Points);
	StartWaveAtPoints(Points, WaveNumber, Segment);
}

void AMechSentinelWaveSpawner::GetSegmentSpawnPoints(const AMyHexPathSegment& Segment, TArray<FVector>& OutPoints) const
{
	const FVector Lift(0.0, 0.0, double(CornerHeightOffset));

	if (!Segment.HasSegmentBounds())
	{
		// A segment from a spawner that sets no bounds: its start.
		OutPoints.Add(Segment.GetActorLocation() + Lift);
		return;
	}

	FVector Center;
	FVector Extent;
	FRotator Rotation;
	Segment.GetSegmentBounds(Center, Extent, Rotation);

	OutPoints = Segment.GetSegmentBoundsCorners(
		/*bTop*/SegmentCorners != EMechSentinelSegmentCorners::Bottom,
		/*bBottom*/SegmentCorners != EMechSentinelSegmentCorners::Top);

	// Toward the centre along both horizontal box axes, never past it.
	const FQuat BoxRotation = Rotation.Quaternion();
	const double Inset = FMath::Max(double(CornerInset), 0.0);
	for (FVector& Point : OutPoints)
	{
		FVector Local = BoxRotation.UnrotateVector(Point - Center);
		Local.X = FMath::Sign(Local.X) * FMath::Max(FMath::Abs(Local.X) - Inset, 0.0);
		Local.Y = FMath::Sign(Local.Y) * FMath::Max(FMath::Abs(Local.Y) - Inset, 0.0);
		Point = Center + BoxRotation.RotateVector(Local) + Lift;
	}
}

//----------------------------------------------------------------------//
// Spawning
//----------------------------------------------------------------------//
int32 AMechSentinelWaveSpawner::SpawnSentinelsNow(const int32 Count)
{
	// After end play the tick that would create them does not run.
	if (!HasAuthority() || Count <= 0 || bSpawnerEndedPlay)
	{
		return 0;
	}

	// The caller may be ticking next to a running Mass phase: Tick (TG_PostUpdateWork) creates them.
	PendingManualSpawns += Count;
	SetActorTickEnabled(true);
	return Count;
}

int32 AMechSentinelWaveSpawner::SpawnBatch(const int32 Count, const FMechSentinelWave& Def, const float StatScale, const TConstArrayView<FVector> SpawnPoints, int32* PointCursor, const FVector& Extent, TArray<FMassEntityHandle>* RunEntities)
{
	UWorld* World = GetWorld();
	FMassEntityManager* EntityManager = GetEntityManager();
	UMassSpawnerSubsystem* SpawnerSubsystem = World ? World->GetSubsystem<UMassSpawnerSubsystem>() : nullptr;
	UMechSentinelSwarmSubsystem* Swarm = UMechSentinelSwarmSubsystem::Get(this);
	if (Count <= 0 || !EntityConfig || !EntityManager || !SpawnerSubsystem || !Swarm)
	{
		return 0;
	}

	// Tick runs outside the Mass phases (see the constructor); this only guards other callers.
	if (EntityManager->IsProcessing() || !Swarm->RegisterEntityConfig(EntityConfig))
	{
		return 0;
	}

	const UMechSentinelSwarmRules* Rules = Swarm->GetRules();

	// Caps: this spawner's MaxAlive and the global MaxAliveSentinels (soft: counted from last frame's alive set).
	int32 Allowed = Count;
	if (MaxAlive > 0)
	{
		Allowed = FMath::Min(Allowed, MaxAlive - AliveCount);
	}
	Allowed = FMath::Min(Allowed, Rules->MaxAliveSentinels - Swarm->GetNumAliveSentinels() - SpawnedSinceHashRefresh());
	if (Allowed <= 0)
	{
		return 0;
	}

	const FMassEntityTemplate& Template = EntityConfig->GetOrCreateEntityTemplate(*World);
	if (!Template.IsValid())
	{
		return 0;
	}

	// A location inside a registered obstacle (a platform) grown by the clearance is rolled again.
	const UMechSentinelObstacleSubsystem* Obstacles = SpawnObstacleClearance > 0.f ? UMechSentinelObstacleSubsystem::Get(this) : nullptr;
	if (Obstacles && Obstacles->GetNumObstacles() == 0)
	{
		Obstacles = nullptr;
	}

	TArray<FMassEntityHandle> NewEntities;
	{
		// Keep the creation context alive while initialising: observers run when it is released.
		const TSharedPtr<FMassEntityManager::FEntityCreationContext> CreationContext = SpawnerSubsystem->SpawnEntities(Template, uint32(Allowed), NewEntities);

		const FVector ActorLocation = GetActorLocation();
		int32 Cursor = PointCursor ? FMath::Max(*PointCursor, 0) : 0;

		for (const FMassEntityHandle Entity : NewEntities)
		{
			if (FTransformFragment* TransformFragment = EntityManager->GetFragmentDataPtr<FTransformFragment>(Entity))
			{
				// Around the spawn points in turn, or around the spawner.
				FVector Origin = ActorLocation;
				if (!SpawnPoints.IsEmpty())
				{
					Origin = SpawnPoints[Cursor % SpawnPoints.Num()];
					Cursor = (Cursor + 1) % SpawnPoints.Num();
				}

				// Uniform inside the ellipsoid.
				FVector Offset = FMath::VRand() * FMath::Pow(FMath::FRand(), 1.f / 3.f) * Extent;
				for (int32 Attempt = 0; Obstacles && Attempt < 4 && Obstacles->IsInsideObstacle(Origin + Offset, SpawnObstacleClearance); ++Attempt)
				{
					Offset = FMath::VRand() * FMath::Pow(FMath::FRand(), 1.f / 3.f) * Extent;
				}

				FTransform& Transform = TransformFragment->GetMutableTransform();
				Transform.SetLocation(Origin + Offset);
				Transform.SetRotation(FRotator(0.f, FMath::FRandRange(-180.f, 180.f), 0.f).Quaternion());
			}

			float AttackSpeed = 1.f;
			if (FMechSentinelAttributesFragment* Attributes = EntityManager->GetFragmentDataPtr<FMechSentinelAttributesFragment>(Entity))
			{
				// The fragment holds the trait defaults (template values); scale them for this wave.
				Attributes->MaxHealth = FMath::Max(1.f, Attributes->MaxHealth * Def.HealthMultiplier * StatScale);
				Attributes->Health = Attributes->MaxHealth;
				Attributes->BaseArmor = Attributes->Armor = Attributes->BaseArmor * Def.ArmorMultiplier * StatScale;
				Attributes->BaseAttackDamage = Attributes->AttackDamage = Attributes->BaseAttackDamage * Def.DamageMultiplier * StatScale;
				Attributes->BaseAttackSpeed = Attributes->AttackSpeed = FMath::Max(0.05f, Attributes->BaseAttackSpeed * Def.AttackSpeedMultiplier);
				Attributes->BaseMoveSpeedMultiplier = Attributes->MoveSpeedMultiplier = Attributes->BaseMoveSpeedMultiplier * Def.MoveSpeedMultiplier;
				AttackSpeed = Attributes->AttackSpeed;
			}

			// Self-buff timers (the fragment is server only): staggered, so a wave does not buff all at once.
			if (FMechSentinelSelfBuffFragment* SelfBuff = EntityManager->GetFragmentDataPtr<FMechSentinelSelfBuffFragment>(Entity))
			{
				SelfBuff->ChanceScale = FMath::Max(0.f, Def.SelfBuffChanceMultiplier);
				if (Rules)
				{
					SelfBuff->DecisionTimer = FMath::FRand() * Rules->SelfBuffDecisionInterval;
					for (int32 BuffIndex = 0; BuffIndex < int32(UE_ARRAY_COUNT(SelfBuff->Cooldown)); ++BuffIndex)
					{
						SelfBuff->Cooldown[BuffIndex] = FMath::FRand() * 0.5f * Rules->GetSelfBuffDef(BuffIndex).Cooldown;
					}
				}
			}

			if (FMechSentinelTargetFragment* Target = EntityManager->GetFragmentDataPtr<FMechSentinelTargetFragment>(Entity))
			{
				// Mostly above the target: sentinels hunt from the air.
				FVector Orbit = FMath::VRand();
				Orbit.Z = FMath::Lerp(0.15f, 1.f, FMath::Abs(Orbit.Z));
				Target->OrbitDirection = Orbit.GetSafeNormal(UE_SMALL_NUMBER, FVector::UpVector);
				Target->RetargetTimer = FMath::FRandRange(0.f, 0.5f);
			}

			if (FMechSentinelAttackFragment* Attack = EntityManager->GetFragmentDataPtr<FMechSentinelAttackFragment>(Entity))
			{
				Attack->Cooldown = FMath::FRandRange(0.f, 1.f / AttackSpeed);
			}
		}

		if (PointCursor)
		{
			*PointCursor = Cursor;
		}
	}

	SpawnedEntities.Append(NewEntities);
	if (RunEntities)
	{
		RunEntities->Append(NewEntities);
	}
	AliveCount += NewEntities.Num();
	SpawnedThisFrame += NewEntities.Num();
	SpawnedFrameNumber = GFrameCounter;
	return NewEntities.Num();
}

int32 AMechSentinelWaveSpawner::SpawnedSinceHashRefresh() const
{
	// The swarm's alive count is rebuilt once per frame; add what this spawner created this frame.
	return SpawnedFrameNumber == GFrameCounter ? SpawnedThisFrame : 0;
}

void AMechSentinelWaveSpawner::RefreshAlive()
{
	if (SpawnedFrameNumber != GFrameCounter)
	{
		SpawnedThisFrame = 0;
	}

	FMassEntityManager* EntityManager = GetEntityManager();
	if (!EntityManager)
	{
		SpawnedEntities.Reset();
		AliveCount = 0;
		return;
	}

	int32 Alive = 0;
	for (int32 Index = SpawnedEntities.Num() - 1; Index >= 0; --Index)
	{
		const FMassEntityHandle Entity = SpawnedEntities[Index];
		if (!EntityManager->IsEntityActive(Entity))
		{
			SpawnedEntities.RemoveAtSwap(Index, EAllowShrinking::No);
			continue;
		}

		const FMechSentinelStateFragment* State = EntityManager->GetFragmentDataPtr<FMechSentinelStateFragment>(Entity);
		if (State && State->State != EMechSentinelState::Dead)
		{
			++Alive;
		}
	}
	AliveCount = Alive;
}

void AMechSentinelWaveSpawner::DespawnAll(const bool bKill)
{
	if (!HasAuthority())
	{
		return;
	}

	// Manual spawns queued before this call are cancelled (they would otherwise appear right after the despawn); the
	// ones queued after it still run after it, unless the spawner has ended play. The same goes for what the waves
	// started at points have not spawned yet.
	PendingManualSpawns = 0;
	CancelRuns();

	// Ended play (destroyed or unloaded): the tick will not run again.
	if (bSpawnerEndedPlay)
	{
		bPendingDespawn = false;
		QueueDespawnOnTimer(bKill);
		return;
	}

	// Like SpawnSentinelsNow: done by Tick, outside the Mass phases.
	bPendingDespawn = true;
	bPendingDespawnKill = bKill;
	SetActorTickEnabled(true);
}

void AMechSentinelWaveSpawner::QueueDespawnOnTimer(const bool bKill)
{
	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}

	// The handles move to the timer: a second call has nothing left to do, and a spawner that streams back in starts
	// without stale ones.
	const TWeakObjectPtr<UWorld> WeakWorld(World);
	World->GetTimerManager().SetTimerForNextTick(FTimerDelegate::CreateLambda(
		[WeakWorld, Entities = MoveTemp(SpawnedEntities), bKill]() mutable
		{
			if (UWorld* WorldNow = WeakWorld.Get())
			{
				DespawnEntities(*WorldNow, Entities, bKill);
			}
		}));
	SpawnedEntities.Reset();
	AliveCount = 0;
}

void AMechSentinelWaveSpawner::DespawnAllNow(const bool bKill)
{
	UWorld* World = GetWorld();
	if (!World || !GetEntityManager())
	{
		return;
	}

	RefreshAlive();
	DespawnEntities(*World, SpawnedEntities, bKill);
	AliveCount = 0;
}

void AMechSentinelWaveSpawner::DespawnEntities(UWorld& World, TArray<FMassEntityHandle>& Entities, const bool bKill)
{
	FMassEntityManager* EntityManager = UE::Mass::Utils::GetEntityManager(&World);
	if (!EntityManager)
	{
		return;
	}

	// Already destroyed ones are dropped (wrecks of killed sentinels destroy themselves after their fall).
	Entities.RemoveAllSwap([EntityManager](const FMassEntityHandle Entity) { return !EntityManager->IsEntityActive(Entity); });

	UMechSentinelSwarmSubsystem* Swarm = World.GetSubsystem<UMechSentinelSwarmSubsystem>();
	if (bKill && Swarm)
	{
		for (const FMassEntityHandle Entity : Entities)
		{
			Swarm->KillSentinel(Entity, nullptr);
		}
		// The wrecks clean themselves up after their fall.
	}
	else
	{
		if (EntityManager->IsProcessing())
		{
			for (const FMassEntityHandle Entity : Entities)
			{
				EntityManager->Defer().DestroyEntity(Entity);
			}
		}
		else if (UMassSpawnerSubsystem* SpawnerSubsystem = World.GetSubsystem<UMassSpawnerSubsystem>())
		{
			SpawnerSubsystem->DestroyEntities(Entities);
		}
		Entities.Reset();
	}
}
