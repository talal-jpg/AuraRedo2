// Mech Sentinel Swarm - project-owned re-implementation of the MassMovement fragments.
// Mirrors (by role, not by code): FMassVelocityFragment, FMassForceFragment,
// FMassDesiredMovementFragment, FMassCodeDrivenMovementTag, FMassMovementParameters
// from Engine/Plugins/Runtime/MassGameplay/Source/MassMovement.

#pragma once

#include "CoreMinimal.h"
#include "MassEntityTypes.h"
#include "MassMovementFragments_Copy.generated.h"

/** Actual velocity of the entity in world space (cm/s). Integrated into the transform by UMassApplyMovementProcessor_Copy. */
USTRUCT()
struct AURA_API FMassVelocityFragment_Copy : public FMassFragment
{
	GENERATED_BODY()

	UPROPERTY(VisibleAnywhere, Category = "Movement")
	FVector Value = FVector::ZeroVector;
};

/**
 * Acceleration accumulator (cm/s^2). Avoidance and other steering helpers add to it,
 * UMassApplyMovementProcessor_Copy applies it to the velocity and clears it every frame.
 * Deviation from the engine: there, ApplyForce folds forces into the desired velocity because engine steering is
 * force based; sentinel steering assigns the desired velocity directly, so forces act on the velocity instead.
 */
USTRUCT()
struct AURA_API FMassForceFragment_Copy : public FMassFragment
{
	GENERATED_BODY()

	UPROPERTY(VisibleAnywhere, Category = "Movement")
	FVector Value = FVector::ZeroVector;
};

/** Output of every "decision" processor that wants to move the entity; input of the movement integration. */
USTRUCT()
struct AURA_API FMassDesiredMovementFragment_Copy : public FMassFragment
{
	GENERATED_BODY()

	/** Velocity the entity would like to reach (cm/s). */
	UPROPERTY(VisibleAnywhere, Category = "Movement")
	FVector DesiredVelocity = FVector::ZeroVector;

	/** Orientation the entity would like to face. Identity means "face the velocity". */
	UPROPERTY(VisibleAnywhere, Category = "Movement")
	FQuat DesiredFacing = FQuat::Identity;

	/** Per-entity speed cap for this frame (FLT_MAX = use FMassMovementParameters_Copy::MaxSpeed). */
	UPROPERTY(VisibleAnywhere, Category = "Movement")
	float DesiredMaxSpeedOverride = FLT_MAX;
};

/** Presence means: velocity is driven by code (desired velocity), not by root motion / physics. */
USTRUCT()
struct AURA_API FMassCodeDrivenMovementTag_Copy : public FMassTag
{
	GENERATED_BODY()
};

/** Presence means: some other processor owns this entity's position (e.g. client net smoothing, death fall). */
USTRUCT()
struct AURA_API FMassCustomMovementTag_Copy : public FMassTag
{
	GENERATED_BODY()
};

/** Shared, read-only movement tuning. One instance per unique set of values. */
USTRUCT()
struct AURA_API FMassMovementParameters_Copy : public FMassConstSharedFragment
{
	GENERATED_BODY()

	/** Hard cap on speed (cm/s), applied after forces. */
	UPROPERTY(EditAnywhere, Category = "Movement", meta = (ClampMin = "0", ForceUnits = "cm/s"))
	float MaxSpeed = 2400.f;

	/** How fast the velocity may change toward the desired velocity (cm/s^2). 0 = snap instantly (engine default behaviour). */
	UPROPERTY(EditAnywhere, Category = "Movement", meta = (ClampMin = "0", ForceUnits = "cm/s^2"))
	float MaxAcceleration = 3000.f;

	/** When false the vertical component of velocity is removed (ground units). Sentinels fly, so true. */
	UPROPERTY(EditAnywhere, Category = "Movement")
	bool bAllowVerticalMovement = true;
};
