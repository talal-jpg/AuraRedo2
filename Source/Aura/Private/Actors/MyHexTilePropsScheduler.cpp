// Fill out your copyright notice in the Description page of Project Settings.

#include "Actors/MyHexTilePropsScheduler.h"

#include "Actors/MyHexPlatform.h"
#include "Engine/World.h"
#include "HAL/IConsoleManager.h"
#include "TimerManager.h"

namespace HexTilePropsScheduler
{
	static TAutoConsoleVariable<int32> CVarConcurrency(
		TEXT("Aura.HexPropsConcurrency"),
		2,
		TEXT("Hex platforms generating their tile props at the same time, nearest (lowest SplineDistance) first. 0 = no limit."),
		ECVF_Default);

	static TAutoConsoleVariable<float> CVarMaxSlotTime(
		TEXT("Aura.HexPropsMaxSlotTime"),
		4.f,
		TEXT("Seconds a running tile prop generation holds its slot at most, so a stuck one can't block the queue."),
		ECVF_Default);

	/** Seconds between pumps while anything is queued or running. */
	constexpr float PumpInterval = 0.05f;
}

void UMyHexTilePropsScheduler::Enqueue(AMyHexPlatform* Platform)
{
	if (!IsValid(Platform))
	{
		return;
	}

	Queue.AddUnique(Platform);

	// The first pump comes a moment later, so every platform of a segment (they ask in the same frame)
	// is sorted together
	UWorld* World = GetWorld();

	if (World && !World->GetTimerManager().IsTimerActive(PumpTimer))
	{
		World->GetTimerManager().SetTimer(PumpTimer, this, &ThisClass::Pump, HexTilePropsScheduler::PumpInterval, true);
	}
}

bool UMyHexTilePropsScheduler::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

void UMyHexTilePropsScheduler::Deinitialize()
{
	if (UWorld* World = GetWorld())
	{
		World->GetTimerManager().ClearTimer(PumpTimer);
	}

	Queue.Reset();
	Running.Reset();

	Super::Deinitialize();
}

void UMyHexTilePropsScheduler::Pump()
{
	UWorld* World = GetWorld();

	if (!World)
	{
		return;
	}

	const double Now = World->GetTimeSeconds();
	const double MaxSlotTime = FMath::Max(HexTilePropsScheduler::CVarMaxSlotTime.GetValueOnGameThread(), 0.1f);

	// Free the slots of generations that finished (or whose platform is gone)
	Running.RemoveAll([Now, MaxSlotTime](const FRunningProps& Entry)
	{
		const AMyHexPlatform* Platform = Entry.Platform.Get();
		return !IsValid(Platform) || !Platform->IsGeneratingTileProps() || Now - Entry.StartTime > MaxSlotTime;
	});

	Queue.RemoveAll([](const TWeakObjectPtr<AMyHexPlatform>& Platform) { return !Platform.IsValid(); });

	if (Queue.Num() > 1)
	{
		// Nearest along the path first. The start platform placed in the level has no distance (-1), so it goes first.
		Queue.StableSort([](const TWeakObjectPtr<AMyHexPlatform>& A, const TWeakObjectPtr<AMyHexPlatform>& B)
		{
			return A->GetSplineDistance() < B->GetSplineDistance();
		});
	}

	const int32 Limit = HexTilePropsScheduler::CVarConcurrency.GetValueOnGameThread();

	for (int32 Index = 0; Index < Queue.Num() && (Limit <= 0 || Running.Num() < Limit);)
	{
		AMyHexPlatform* Platform = Queue[Index].Get();

		if (!IsValid(Platform))
		{
			Queue.RemoveAt(Index, EAllowShrinking::No);
			continue;
		}

		// Its previous generation is still running (it holds a slot, or held one until MaxSlotTime):
		// it stays queued and goes once that is done, without taking a second slot
		if (Platform->IsGeneratingTileProps())
		{
			++Index;
			continue;
		}

		Queue.RemoveAt(Index, EAllowShrinking::No);
		Platform->RunQueuedTileProps();

		// Nothing started (props frozen or nothing to spawn): no slot taken
		if (Platform->IsGeneratingTileProps())
		{
			Running.Add({ Platform, Now });
		}
	}

	if (Queue.IsEmpty() && Running.IsEmpty())
	{
		World->GetTimerManager().ClearTimer(PumpTimer);
	}
}
