// Mech Sentinel Swarm - sentinel processors.
//
// Authority (server / standalone), PrePhysics:
//   Behavior : UMechSentinelEffectsProcessor -> UMechSentinelTargetSelectionProcessor -> UMechSentinelSelfBuffProcessor
//              (casts are applied by the swarm subsystem in a timer, after the phases)
//   Tasks    : UMechSentinelSteeringProcessor
//   (Avoidance -> ApplyForces -> Movement from the _Copy processors)
//   Combat   : UMechSentinelAttackProcessor, UMechSentinelDeathProcessor -> UMechSentinelCollisionHashProcessor
// Where frames are rendered (client / listen / standalone):
//   UMechSentinelNetSmoothingProcessor (clients only, PrePhysics)
//   UMechSentinelVisualDataProcessor   (PostPhysics, before the ISM update)

#pragma once

#include "CoreMinimal.h"
#include "MassProcessor.h"
#include "MassEntityQuery.h"
#include "MechSentinelProcessors.generated.h"

/** Ticks durations of the sentinel's stored gameplay effects and asks the GAS bridge to re-evaluate when one expires. */
UCLASS()
class AURA_API UMechSentinelEffectsProcessor : public UMassProcessor
{
	GENERATED_BODY()

public:
	UMechSentinelEffectsProcessor();

protected:
	virtual void ConfigureQueries(const TSharedRef<FMassEntityManager>& EntityManager) override;
	virtual void Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context) override;

	FMassEntityQuery EntityQuery;
};

/**
 * Self-buff decisions (server): ticks each sentinel's buff cooldowns and decision timer; at each decision a sentinel
 * that is not stunned rolls the rules' SelfBuffChance and picks a ready buff by weight (off cooldown, not active, its
 * target distance window met). The cast is only queued here: UMechSentinelSwarmSubsystem applies the buff's GE after
 * the Mass phases (GAS writes fragments and may change tags), at most MaxSelfBuffsPerFrame per frame.
 */
UCLASS()
class AURA_API UMechSentinelSelfBuffProcessor : public UMassProcessor
{
	GENERATED_BODY()

public:
	UMechSentinelSelfBuffProcessor();

protected:
	virtual void ConfigureQueries(const TSharedRef<FMassEntityManager>& EntityManager) override;
	virtual void Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context) override;

	FMassEntityQuery EntityQuery;
};

/**
 * Refreshes every swarm group's shared targeting board (players + fallback points), then assigns each
 * sentinel a target: nearest player with room, else another player, else a fallback point.
 */
UCLASS()
class AURA_API UMechSentinelTargetSelectionProcessor : public UMassProcessor
{
	GENERATED_BODY()

public:
	UMechSentinelTargetSelectionProcessor();

protected:
	virtual void ConfigureQueries(const TSharedRef<FMassEntityManager>& EntityManager) override;
	virtual void Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context) override;

	FMassEntityQuery EntityQuery;
};

/** Turns the target into a desired velocity / facing: approach, orbit around the player, loiter at fallbacks, sink when stunned. */
UCLASS()
class AURA_API UMechSentinelSteeringProcessor : public UMassProcessor
{
	GENERATED_BODY()

public:
	UMechSentinelSteeringProcessor();

protected:
	virtual void ConfigureQueries(const TSharedRef<FMassEntityManager>& EntityManager) override;
	virtual void Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context) override;

	FMassEntityQuery EntityQuery;
};

/** Enters / leaves the attack state by range and applies the attack gameplay effect to the target player at AttackSpeed. */
UCLASS()
class AURA_API UMechSentinelAttackProcessor : public UMassProcessor
{
	GENERATED_BODY()

public:
	UMechSentinelAttackProcessor();

protected:
	virtual void ConfigureQueries(const TSharedRef<FMassEntityManager>& EntityManager) override;
	virtual void Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context) override;

	FMassEntityQuery EntityQuery;
};

/** Dead sentinels tumble down under gravity and are destroyed after DeathFallDuration. */
UCLASS()
class AURA_API UMechSentinelDeathProcessor : public UMassProcessor
{
	GENERATED_BODY()

public:
	UMechSentinelDeathProcessor();

protected:
	virtual void ConfigureQueries(const TSharedRef<FMassEntityManager>& EntityManager) override;
	virtual void Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context) override;

	FMassEntityQuery EntityQuery;
};

/** Rebuilds the subsystem's spatial hash of sentinel collision capsules (used by every hit query). */
UCLASS()
class AURA_API UMechSentinelCollisionHashProcessor : public UMassProcessor
{
	GENERATED_BODY()

public:
	UMechSentinelCollisionHashProcessor();

protected:
	virtual void ConfigureQueries(const TSharedRef<FMassEntityManager>& EntityManager) override;
	virtual void Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context) override;

	FMassEntityQuery EntityQuery;
};

/** Writes state / health / hit flash / attack glow / buff fades into the ISM custom data floats (and fades the flashes). */
UCLASS()
class AURA_API UMechSentinelVisualDataProcessor : public UMassProcessor
{
	GENERATED_BODY()

public:
	UMechSentinelVisualDataProcessor();

protected:
	virtual void ConfigureQueries(const TSharedRef<FMassEntityManager>& EntityManager) override;
	virtual void Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context) override;

	FMassEntityQuery EntityQuery;
};

/** Network clients: eases the transform toward the last replicated sample, extrapolated with its velocity. */
UCLASS()
class AURA_API UMechSentinelNetSmoothingProcessor : public UMassProcessor
{
	GENERATED_BODY()

public:
	UMechSentinelNetSmoothingProcessor();

protected:
	virtual void ConfigureQueries(const TSharedRef<FMassEntityManager>& EntityManager) override;
	virtual void Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context) override;

	FMassEntityQuery EntityQuery;
};
