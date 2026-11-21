// Fill out your copyright notice in the Description page of Project Settings.


#include "Burrower/BurrowerSpawnSubsystem.h"

#include "Burrower/BurrowerCharacter.h"
#include "Burrower/BurrowerSettings.h"
#include "Engine/AssetManager.h"
#include "Engine/StreamableManager.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/GameStateBase.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerState.h"
#include "HAL/IConsoleManager.h"
#include "Kismet/GameplayStatics.h"
#include "MyGameMode.h"
#include "TimerManager.h"

DEFINE_LOG_CATEGORY_STATIC(LogBurrowerSpawn, Log, All);


// =============================================================================
// Lifetime
// =============================================================================

UBurrowerSpawnSubsystem* UBurrowerSpawnSubsystem::Get(const UObject* WorldContextObject)
{
	const UWorld* World = WorldContextObject ? WorldContextObject->GetWorld() : nullptr;
	return World ? World->GetSubsystem<UBurrowerSpawnSubsystem>() : nullptr;
}

bool UBurrowerSpawnSubsystem::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

void UBurrowerSpawnSubsystem::OnWorldBeginPlay(UWorld& InWorld)
{
	Super::OnWorldBeginPlay(InWorld);

	// Server only: clients get the Burrowers by replication
	if (InWorld.GetNetMode() == NM_Client)
	{
		return;
	}

	// A dedicated server creates no health bar widget, and AMyEnemyChar::BeginPlay uses it without a check
	if (InWorld.GetNetMode() == NM_DedicatedServer)
	{
		UE_LOG(LogBurrowerSpawn, Warning, TEXT("No Burrowers on a dedicated server: AMyEnemyChar::BeginPlay would crash on the missing health bar widget"));
		return;
	}

	bActive = true;

	const UBurrowerSettings& Settings = *GetDefault<UBurrowerSettings>();

	// Load the class now rather than in a blocking load at the first spawn
	if (Settings.bEnabled && !Settings.BurrowerClass.IsNull() && UAssetManager::IsInitialized())
	{
		TArray<FSoftObjectPath> ClassPaths;
		ClassPaths.Add(Settings.BurrowerClass.ToSoftObjectPath());
		BurrowerClassHandle = UAssetManager::GetStreamableManager().RequestAsyncLoad(MoveTemp(ClassPaths));
	}

	// Polls even with bEnabled off, so Burrowers from Aura.Burrower.SpawnNow are still retargeted
	InWorld.GetTimerManager().SetTimer(PollTimerHandle, this, &UBurrowerSpawnSubsystem::Poll, FMath::Max(Settings.PollInterval, 0.05f), /*InbLoop=*/true);
}

void UBurrowerSpawnSubsystem::Deinitialize()
{
	if (UWorld* World = GetWorld())
	{
		World->GetTimerManager().ClearTimer(PollTimerHandle);
	}

	if (BurrowerClassHandle.IsValid())
	{
		BurrowerClassHandle->ReleaseHandle();
		BurrowerClassHandle.Reset();
	}

	Entries.Reset();
	bActive = false;

	Super::Deinitialize();
}

bool UBurrowerSpawnSubsystem::IsMapAllowed(const UBurrowerSettings& Settings) const
{
	if (Settings.AllowedMaps.IsEmpty())
	{
		return true;
	}

	// Without the PIE prefix (UEDPIE_N_)
	const FString MapName = UGameplayStatics::GetCurrentLevelName(GetWorld(), /*bRemovePrefixString=*/true);

	return Settings.AllowedMaps.ContainsByPredicate([&MapName](const FString& Allowed)
	{
		return Allowed.Equals(MapName, ESearchCase::IgnoreCase);
	});
}

bool UBurrowerSpawnSubsystem::HasEnemyClassInfo()
{
	const UWorld* World = GetWorld();
	const AMyGameMode* GameMode = World ? World->GetAuthGameMode<AMyGameMode>() : nullptr;

	if (GameMode && GameMode->DA_MyEnemyCharacterClassInfo)
	{
		return true;
	}

	if (!bWarnedMissingClassInfo)
	{
		bWarnedMissingClassInfo = true;
		UE_LOG(LogBurrowerSpawn, Warning, TEXT("No Burrower spawns here: the GameMode is not an AMyGameMode with DA_MyEnemyCharacterClassInfo set (the attributes need it, and the kill would crash in UMyBPFuncLib::GetXPRewardForCharacterClass)"));
	}

	return false;
}


// =============================================================================
// Players
// =============================================================================

UBurrowerSpawnSubsystem::FPlayerEntry* UBurrowerSpawnSubsystem::FindEntry(const APlayerState* PlayerState)
{
	return Entries.FindByPredicate([PlayerState](const FPlayerEntry& Entry)
	{
		return Entry.PlayerState.Get() == PlayerState;
	});
}

UBurrowerSpawnSubsystem::FPlayerEntry& UBurrowerSpawnSubsystem::FindOrAddEntry(APlayerState* PlayerState, const UBurrowerSettings& Settings)
{
	if (FPlayerEntry* Existing = FindEntry(PlayerState))
	{
		return *Existing;
	}

	FPlayerEntry& Entry = Entries.AddDefaulted_GetRef();
	Entry.PlayerState = PlayerState;
	Entry.Countdown = Settings.FirstSpawnDelay;
	return Entry;
}

int32 UBurrowerSpawnSubsystem::GetNumAliveFor(const APlayerState* PlayerState) const
{
	const FPlayerEntry* Entry = Entries.FindByPredicate([PlayerState](const FPlayerEntry& Candidate)
	{
		return Candidate.PlayerState.Get() == PlayerState;
	});

	if (!Entry)
	{
		return 0;
	}

	int32 NumAlive = 0;

	for (const TWeakObjectPtr<ABurrowerCharacter>& Weak : Entry->Burrowers)
	{
		const ABurrowerCharacter* Burrower = Weak.Get();

		if (Burrower && !Burrower->IsBurrowerDead())
		{
			++NumAlive;
		}
	}

	return NumAlive;
}

void UBurrowerSpawnSubsystem::Poll()
{
	UWorld* World = GetWorld();
	const AGameStateBase* GameState = World ? World->GetGameState() : nullptr;

	if (!bActive || !GameState)
	{
		return;
	}

	const UBurrowerSettings& Settings = *GetDefault<UBurrowerSettings>();

	// Real time between polls (the timer can be late), game time so a pause stops the countdowns
	const double Now = World->GetTimeSeconds();
	const float Elapsed = LastPollTime >= 0.0 ? static_cast<float>(Now - LastPollTime) : 0.f;
	LastPollTime = Now;

	const bool bAutoSpawn = Settings.bEnabled && IsMapAllowed(Settings) && HasEnemyClassInfo();

	// Players who left take their living Burrowers with them
	for (int32 Index = Entries.Num() - 1; Index >= 0; --Index)
	{
		APlayerState* PlayerState = Entries[Index].PlayerState.Get();

		if (PlayerState && GameState->PlayerArray.Contains(PlayerState))
		{
			continue;
		}

		for (const TWeakObjectPtr<ABurrowerCharacter>& Weak : Entries[Index].Burrowers)
		{
			ABurrowerCharacter* Burrower = Weak.Get();

			if (Burrower && !Burrower->IsBurrowerDead())
			{
				Burrower->Destroy();
			}
		}

		Entries.RemoveAtSwap(Index);
	}

	for (const TObjectPtr<APlayerState>& PlayerStatePtr : GameState->PlayerArray)
	{
		APlayerState* PlayerState = PlayerStatePtr.Get();

		if (!PlayerState || PlayerState->IsOnlyASpectator())
		{
			continue;
		}

		FPlayerEntry& Entry = FindOrAddEntry(PlayerState, Settings);

		APawn* Pawn = PlayerState->GetPawn();
		APawn* LivingPawn = ABurrowerCharacter::IsLivingTarget(Pawn, Settings.bOnlyCombatPawns) ? Pawn : nullptr;

		// A new pawn (first one, or a respawn): retarget, and give a respawned player a moment
		if (LivingPawn && Entry.Pawn.Get() != LivingPawn)
		{
			if (Entry.bHadPawn)
			{
				Entry.Countdown = FMath::Max(Entry.Countdown, Settings.PlayerRespawnGrace);
			}

			Entry.bHadPawn = true;
			Entry.Pawn = LivingPawn;
		}

		UpdateEntryBurrowers(Entry, LivingPawn, Settings);

		// The countdown runs only while the player is alive and has room for one more
		const bool bRoom = Entry.Burrowers.Num() < FMath::Max(Settings.MaxAlivePerPlayer, 1);
		const bool bMayRespawn = Settings.bRespawnAfterDeath || Entry.NumDied == 0;

		if (!bAutoSpawn || !LivingPawn || !bRoom || !bMayRespawn)
		{
			continue;
		}

		Entry.Countdown -= Elapsed;

		if (Entry.Countdown > 0.f)
		{
			continue;
		}

		// No class yet (still loading, or unset): try again in a second
		Entry.Countdown = SpawnBehind(Entry, LivingPawn, Settings) ? Settings.SpawnInterval : 1.f;
	}
}

void UBurrowerSpawnSubsystem::UpdateEntryBurrowers(FPlayerEntry& Entry, APawn* LivingPawn, const UBurrowerSettings& Settings)
{
	for (int32 Index = Entry.Burrowers.Num() - 1; Index >= 0; --Index)
	{
		ABurrowerCharacter* Burrower = Entry.Burrowers[Index].Get();

		// Destroyed without dying (by something else): comes back after SpawnInterval
		if (!Burrower)
		{
			Entry.Burrowers.RemoveAtSwap(Index);
			Entry.Countdown = FMath::Max(Entry.Countdown, Settings.SpawnInterval);
			continue;
		}

		// Died: the next one waits SpawnInterval from now (the corpse stays for its LifeSpan)
		if (Burrower->IsBurrowerDead())
		{
			Entry.Burrowers.RemoveAtSwap(Index);
			++Entry.NumDied;
			Entry.Countdown = FMath::Max(Entry.Countdown, Settings.SpawnInterval);
			continue;
		}

		// Too far behind its player: removed, comes back behind them after SpawnInterval
		if (LivingPawn && Settings.DespawnDistance > 0.f
			&& FVector::DistSquared(Burrower->GetActorLocation(), LivingPawn->GetActorLocation()) > FMath::Square(static_cast<double>(Settings.DespawnDistance)))
		{
			Burrower->Destroy();
			Entry.Burrowers.RemoveAtSwap(Index);
			Entry.Countdown = FMath::Max(Entry.Countdown, Settings.SpawnInterval);
			continue;
		}

		// Dead or missing player: it waits (no target) until they are back
		Burrower->SetTargetPlayer(LivingPawn);
	}
}


// =============================================================================
// Spawning
// =============================================================================

UClass* UBurrowerSpawnSubsystem::ResolveBurrowerClass()
{
	const UBurrowerSettings& Settings = *GetDefault<UBurrowerSettings>();

	UClass* Class = Settings.BurrowerClass.Get();

	if (!Class && !Settings.BurrowerClass.IsNull())
	{
		// Not loaded yet (or bEnabled was off at BeginPlay): blocking load, once
		Class = Settings.BurrowerClass.LoadSynchronous();
	}

	if (!Class && !bWarnedMissingClass)
	{
		bWarnedMissingClass = true;
		UE_LOG(LogBurrowerSpawn, Warning, TEXT("No Burrower spawned: set Burrower Class in Project Settings > Game > Burrower (BP_Burrower). Was: '%s'"),
			*Settings.BurrowerClass.ToString());
	}

	return Class;
}

ABurrowerCharacter* UBurrowerSpawnSubsystem::SpawnBehind(FPlayerEntry& Entry, APawn* Pawn, const UBurrowerSettings& Settings)
{
	UWorld* World = GetWorld();

	if (!bActive || !World || !Pawn || !HasEnemyClassInfo())
	{
		return nullptr;
	}

	UClass* Class = ResolveBurrowerClass();

	if (!Class)
	{
		return nullptr;
	}

	// Behind the player (against their velocity, or their facing when slow), facing them
	const FVector PawnLocation = Pawn->GetActorLocation();
	const FVector Behind = ABurrowerCharacter::GetBehindDirection(Pawn, Settings.MinSpeedForVelocityDirection);
	const FVector Location = PawnLocation + Behind * Settings.SpawnDistanceBehind + FVector(0.0, 0.0, Settings.SpawnHeightOffset);
	const FRotator Rotation(0.0, (-Behind).Rotation().Yaw, 0.0);
	const FTransform SpawnTransform(Rotation, Location);

	// It flies through everything, so it always spawns where it is put
	ABurrowerCharacter* Burrower = World->SpawnActorDeferred<ABurrowerCharacter>(Class, SpawnTransform, nullptr, nullptr,
		ESpawnActorCollisionHandlingMethod::AlwaysSpawn);

	if (!Burrower)
	{
		return nullptr;
	}

	Burrower->MarkSpawnedBySubsystem();
	Burrower->SetTargetPlayer(Pawn);
	Burrower->FinishSpawning(SpawnTransform);

	if (!IsValid(Burrower))
	{
		return nullptr;
	}

	Entry.Burrowers.Add(Burrower);

	UE_LOG(LogBurrowerSpawn, Log, TEXT("Spawned %s behind %s at %s"), *Burrower->GetName(), *Pawn->GetName(), *Location.ToCompactString());

	return Burrower;
}

int32 UBurrowerSpawnSubsystem::SpawnNow(int32 PlayerIndex)
{
	UWorld* World = GetWorld();
	const AGameStateBase* GameState = World ? World->GetGameState() : nullptr;

	if (!bActive || !GameState)
	{
		return 0;
	}

	const UBurrowerSettings& Settings = *GetDefault<UBurrowerSettings>();
	int32 NumSpawned = 0;

	for (int32 Index = 0; Index < GameState->PlayerArray.Num(); ++Index)
	{
		if (PlayerIndex >= 0 && Index != PlayerIndex)
		{
			continue;
		}

		APlayerState* PlayerState = GameState->PlayerArray[Index].Get();
		APawn* Pawn = PlayerState ? PlayerState->GetPawn() : nullptr;

		if (!PlayerState || !ABurrowerCharacter::IsLivingTarget(Pawn, Settings.bOnlyCombatPawns))
		{
			continue;
		}

		FPlayerEntry& Entry = FindOrAddEntry(PlayerState, Settings);

		if (!Entry.bHadPawn)
		{
			Entry.bHadPawn = true;
			Entry.Pawn = Pawn;
		}

		if (SpawnBehind(Entry, Pawn, Settings))
		{
			++NumSpawned;
			Entry.Countdown = FMath::Max(Entry.Countdown, Settings.SpawnInterval);
		}
	}

	return NumSpawned;
}

int32 UBurrowerSpawnSubsystem::KillAll()
{
	UWorld* World = GetWorld();

	if (!bActive || !World)
	{
		return 0;
	}

	int32 NumKilled = 0;

	for (TActorIterator<ABurrowerCharacter> It(World); It; ++It)
	{
		if (It->HasAuthority() && !It->IsBurrowerDead())
		{
			It->Die();
			++NumKilled;
		}
	}

	return NumKilled;
}


// =============================================================================
// Console
// =============================================================================

#if !UE_BUILD_SHIPPING
// Named, not anonymous: the unity build compiles this file together with others
namespace BurrowerSpawnConsole
{
	FAutoConsoleCommandWithWorldAndArgs GBurrowerSpawnNowCommand(
		TEXT("Aura.Burrower.SpawnNow"),
		TEXT("Aura.Burrower.SpawnNow [PlayerIndex] - server: spawn a Burrower behind every player now (or only GameState PlayerArray[PlayerIndex]), ignoring the countdowns and MaxAlivePerPlayer"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			UBurrowerSpawnSubsystem* Subsystem = UBurrowerSpawnSubsystem::Get(World);

			if (!Subsystem || !Subsystem->IsActive())
			{
				UE_LOG(LogBurrowerSpawn, Warning, TEXT("Aura.Burrower.SpawnNow: run it on the server (listen server window or standalone)"));
				return;
			}

			const int32 PlayerIndex = Args.Num() > 0 ? FCString::Atoi(*Args[0]) : -1;
			const int32 NumSpawned = Subsystem->SpawnNow(PlayerIndex);

			UE_LOG(LogBurrowerSpawn, Log, TEXT("Aura.Burrower.SpawnNow: %d spawned"), NumSpawned);
		})
	);

	FAutoConsoleCommandWithWorld GBurrowerKillAllCommand(
		TEXT("Aura.Burrower.KillAll"),
		TEXT("Aura.Burrower.KillAll - server: every living Burrower dies through its normal death (ragdoll, LifeSpan, respawn countdown); no XP"),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* World)
		{
			UBurrowerSpawnSubsystem* Subsystem = UBurrowerSpawnSubsystem::Get(World);

			if (!Subsystem || !Subsystem->IsActive())
			{
				UE_LOG(LogBurrowerSpawn, Warning, TEXT("Aura.Burrower.KillAll: run it on the server (listen server window or standalone)"));
				return;
			}

			UE_LOG(LogBurrowerSpawn, Log, TEXT("Aura.Burrower.KillAll: %d killed"), Subsystem->KillAll());
		})
	);
}
#endif
