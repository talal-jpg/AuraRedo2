// Mech Sentinel Swarm - level-placed wave spawner.

#include "MechSwarm/Spawning/MechSentinelWaveSpawner.h"

#include "Components/SceneComponent.h"
#include "Engine/World.h"
#include "MassCommandBuffer.h"
#include "MassEntityConfigAsset.h"
#include "MassEntityManager.h"
#include "MassEntityTemplate.h"
#include "MassEntityUtils.h"
#include "MassSpawnerSubsystem.h"
#include "Mass/EntityFragments.h"
#include "MechSwarm/Core/MechSentinelSwarmRules.h"
#include "MechSwarm/Core/MechSentinelSwarmSubsystem.h"
#include "MechSwarm/MassCopies/MassMovementFragments_Copy.h"
#include "MechSwarm/Sentinel/MechSentinelFragments.h"
#include "MechSwarm/Sentinel/MechSentinelTrait.h"
#include "Net/UnrealNetwork.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(MechSentinelWaveSpawner)

AMechSentinelWaveSpawner::AMechSentinelWaveSpawner()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.bStartWithTickEnabled = false;

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

	// As early as possible on clients: replicated sentinels need this template to spawn.
	const UWorld* World = GetWorld();
	if (World && World->IsGameWorld())
	{
		EnsureTemplateBuilt();
	}
}

void AMechSentinelWaveSpawner::BeginPlay()
{
	Super::BeginPlay();

	EnsureTemplateBuilt();

	if (!HasAuthority())
	{
		return;
	}

	if (UMechSentinelSwarmSubsystem* Swarm = UMechSentinelSwarmSubsystem::Get(this))
	{
		TArray<FMechSentinelFallbackPoint> Points = FallbackTargets;
		if (bSpawnerIsFallbackTarget)
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
	if (bAutoStart)
	{
		StartWaves(/*bRestartFromFirstWave*/true);
	}
}

void AMechSentinelWaveSpawner::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
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
	OutStatScale = 1.f;
	if (Waves.IsEmpty() || WaveNumber < 1)
	{
		return FMechSentinelWave();
	}

	const int32 Index = WaveNumber - 1;
	if (Index < Waves.Num())
	{
		return Waves[Index];
	}

	// Endless mode: the last wave again, bigger and tougher each time.
	const int32 Repeats = Index - (Waves.Num() - 1);
	FMechSentinelWave Wave = Waves.Last();
	Wave.Count += ExtraCountPerRepeat * Repeats;
	OutStatScale = FMath::Pow(StatScalePerRepeat, float(Repeats));
	return Wave;
}

int32 AMechSentinelWaveSpawner::ResolveCount(const FMechSentinelWave& Wave, const int32 WaveNumber) const
{
	return FMath::Max(0, FMath::RoundToInt32(float(Wave.Count) * CountMultiplier));
}

void AMechSentinelWaveSpawner::StartWaves(const bool bRestartFromFirstWave)
{
	if (!HasAuthority())
	{
		return;
	}

	bStopped = false;
	SetActorTickEnabled(true);

	// Nothing to run: report the waves as finished right away instead of sitting in a countdown forever.
	if (Waves.IsEmpty())
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
	if (!HasAuthority() || Waves.IsEmpty())
	{
		return;
	}

	const int32 Next = (WaveState == EMechSentinelWaveState::Countdown) ? PendingWaveNumber : CurrentWaveNumber + 1;
	if (Next <= Waves.Num() || bRepeatLastWave)
	{
		bStopped = false;
		BeginWave(Next);
	}
}

void AMechSentinelWaveSpawner::SetCountMultiplier(const float NewMultiplier)
{
	CountMultiplier = FMath::Max(0.f, NewMultiplier);

	// Re-plan what is left of the current wave.
	if (WaveState == EMechSentinelWaveState::Spawning || WaveState == EMechSentinelWaveState::Fighting)
	{
		const int32 NewTotal = ResolveCount(ActiveWave, CurrentWaveNumber);
		RemainingToSpawn = FMath::Max(0, NewTotal - ActiveWaveSpawned);
		CurrentWaveTotal = ActiveWaveSpawned + RemainingToSpawn;
		if (RemainingToSpawn > 0)
		{
			WaveState = EMechSentinelWaveState::Spawning;
		}
	}
}

void AMechSentinelWaveSpawner::SetWaveCount(const int32 WaveIndex, const int32 NewCount)
{
	if (!Waves.IsValidIndex(WaveIndex))
	{
		return;
	}

	Waves[WaveIndex].Count = FMath::Max(0, NewCount);

	const bool bIsCurrent = WaveIndex == CurrentWaveNumber - 1
		&& (WaveState == EMechSentinelWaveState::Spawning || WaveState == EMechSentinelWaveState::Fighting);
	if (bIsCurrent)
	{
		ActiveWave.Count = Waves[WaveIndex].Count;
		SetCountMultiplier(CountMultiplier);
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

	RefreshAlive();

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
				const int32 Spawned = SpawnBatch(Wanted);
				SpawnAccumulator -= float(Spawned);
				RemainingToSpawn -= Spawned;
				ActiveWaveSpawned += Spawned;
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
		}

		if (bAdvance)
		{
			const int32 Next = CurrentWaveNumber + 1;
			if (Next <= Waves.Num() || (bRepeatLastWave && !Waves.IsEmpty()))
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
}

//----------------------------------------------------------------------//
// Spawning
//----------------------------------------------------------------------//
int32 AMechSentinelWaveSpawner::SpawnSentinelsNow(const int32 Count)
{
	return HasAuthority() ? SpawnBatch(Count) : 0;
}

int32 AMechSentinelWaveSpawner::SpawnBatch(const int32 Count)
{
	UWorld* World = GetWorld();
	FMassEntityManager* EntityManager = GetEntityManager();
	UMassSpawnerSubsystem* SpawnerSubsystem = World ? World->GetSubsystem<UMassSpawnerSubsystem>() : nullptr;
	UMechSentinelSwarmSubsystem* Swarm = UMechSentinelSwarmSubsystem::Get(this);
	if (Count <= 0 || !EntityConfig || !EntityManager || !SpawnerSubsystem || !Swarm)
	{
		return 0;
	}

	// Never create entities in the middle of a Mass phase; the next tick will try again.
	if (EntityManager->IsProcessing() || !Swarm->RegisterEntityConfig(EntityConfig))
	{
		return 0;
	}

	// Caps: this spawner's MaxAlive and the global MaxAliveSentinels (soft: counted from last frame's alive set).
	int32 Allowed = Count;
	if (MaxAlive > 0)
	{
		Allowed = FMath::Min(Allowed, MaxAlive - AliveCount);
	}
	Allowed = FMath::Min(Allowed, Swarm->GetRules()->MaxAliveSentinels - Swarm->GetNumAliveSentinels() - SpawnedSinceHashRefresh());
	if (Allowed <= 0)
	{
		return 0;
	}

	const FMassEntityTemplate& Template = EntityConfig->GetOrCreateEntityTemplate(*World);
	if (!Template.IsValid())
	{
		return 0;
	}

	TArray<FMassEntityHandle> NewEntities;
	{
		// Keep the creation context alive while initialising: observers run when it is released.
		const TSharedPtr<FMassEntityManager::FEntityCreationContext> CreationContext = SpawnerSubsystem->SpawnEntities(Template, uint32(Allowed), NewEntities);

		const FVector Origin = GetActorLocation();
		const float Scale = ActiveStatScale;

		for (const FMassEntityHandle Entity : NewEntities)
		{
			if (FTransformFragment* TransformFragment = EntityManager->GetFragmentDataPtr<FTransformFragment>(Entity))
			{
				// Uniform inside the ellipsoid.
				const FVector Offset = FMath::VRand() * FMath::Pow(FMath::FRand(), 1.f / 3.f) * SpawnExtent;
				FTransform& Transform = TransformFragment->GetMutableTransform();
				Transform.SetLocation(Origin + Offset);
				Transform.SetRotation(FRotator(0.f, FMath::FRandRange(-180.f, 180.f), 0.f).Quaternion());
			}

			float AttackSpeed = 1.f;
			if (FMechSentinelAttributesFragment* Attributes = EntityManager->GetFragmentDataPtr<FMechSentinelAttributesFragment>(Entity))
			{
				// The fragment holds the trait defaults (template values); scale them for this wave.
				Attributes->MaxHealth = FMath::Max(1.f, Attributes->MaxHealth * ActiveWave.HealthMultiplier * Scale);
				Attributes->Health = Attributes->MaxHealth;
				Attributes->BaseArmor = Attributes->Armor = Attributes->BaseArmor * ActiveWave.ArmorMultiplier * Scale;
				Attributes->BaseAttackDamage = Attributes->AttackDamage = Attributes->BaseAttackDamage * ActiveWave.DamageMultiplier * Scale;
				Attributes->BaseAttackSpeed = Attributes->AttackSpeed = FMath::Max(0.05f, Attributes->BaseAttackSpeed * ActiveWave.AttackSpeedMultiplier);
				Attributes->BaseMoveSpeedMultiplier = Attributes->MoveSpeedMultiplier = Attributes->BaseMoveSpeedMultiplier * ActiveWave.MoveSpeedMultiplier;
				AttackSpeed = Attributes->AttackSpeed;
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
	}

	SpawnedEntities.Append(NewEntities);
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

	FMassEntityManager* EntityManager = GetEntityManager();
	UMechSentinelSwarmSubsystem* Swarm = UMechSentinelSwarmSubsystem::Get(this);
	UMassSpawnerSubsystem* SpawnerSubsystem = GetWorld() ? GetWorld()->GetSubsystem<UMassSpawnerSubsystem>() : nullptr;
	if (!EntityManager)
	{
		return;
	}

	RefreshAlive();

	if (bKill && Swarm)
	{
		for (const FMassEntityHandle Entity : SpawnedEntities)
		{
			Swarm->KillSentinel(Entity, nullptr);
		}
		// The wrecks clean themselves up after their fall.
	}
	else
	{
		if (EntityManager->IsProcessing())
		{
			for (const FMassEntityHandle Entity : SpawnedEntities)
			{
				EntityManager->Defer().DestroyEntity(Entity);
			}
		}
		else if (SpawnerSubsystem)
		{
			SpawnerSubsystem->DestroyEntities(SpawnedEntities);
		}
		SpawnedEntities.Reset();
	}

	AliveCount = 0;
}
