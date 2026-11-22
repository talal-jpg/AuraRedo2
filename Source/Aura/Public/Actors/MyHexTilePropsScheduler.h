// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "Engine/TimerHandle.h"
#include "MyHexTilePropsScheduler.generated.h"

class AMyHexPlatform;

/**
 * Runs the hex platforms' tile prop generation (path rebuild, tile props and atmosphere PCG) nearest
 * first: lowest SplineDistance first, and only a few at a time (Aura.HexPropsConcurrency), so the
 * platforms a player reaches first get their props first instead of every platform of a segment
 * generating at once. Every machine generates its own props, so this runs on clients too.
 */
UCLASS()
class AURA_API UMyHexTilePropsScheduler : public UWorldSubsystem
{
	GENERATED_BODY()

public:

	/** Queues Platform's next tile prop generation (once; a platform already queued keeps its place). */
	void Enqueue(AMyHexPlatform* Platform);

protected:

	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;
	virtual void Deinitialize() override;

private:

	/** Timer: frees the slots of finished generations, then starts the nearest queued platforms. */
	void Pump();

	struct FRunningProps
	{
		TWeakObjectPtr<AMyHexPlatform> Platform;
		double StartTime = 0.0;
	};

	TArray<TWeakObjectPtr<AMyHexPlatform>> Queue;
	TArray<FRunningProps> Running;

	FTimerHandle PumpTimer;
};
