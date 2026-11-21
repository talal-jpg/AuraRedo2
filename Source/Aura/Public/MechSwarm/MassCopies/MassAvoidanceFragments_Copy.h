// Mech Sentinel Swarm - project-owned re-implementation of the MassAvoidance parameters.
// Mirrors (by role): FMassMovingAvoidanceParameters from MassAI/MassNavigation.
// Deviation: the engine avoidance is 2D and navmesh/lane based; sentinels fly, so this one is a full 3D
// predictive separation computed on a spatial hash, with no navigation data required. The engine's obstacle edges
// (FMassNavigationEdgesFragment) are infinitely tall 2D walls; sentinels avoid 3D obstacles instead
// (FMechSentinelObstacleAvoidanceParameters below).

#pragma once

#include "CoreMinimal.h"
#include "MassEntityTypes.h"
#include "MassAvoidanceFragments_Copy.generated.h"

/** Shared tuning for agent-vs-agent avoidance. */
USTRUCT()
struct AURA_API FMassMovingAvoidanceParameters_Copy : public FMassConstSharedFragment
{
	GENERATED_BODY()

	/** Two agents closer than this (cm) push each other apart. The spatial hash cells are this plus the prediction reach (max 4x this). */
	UPROPERTY(EditAnywhere, Category = "Avoidance", meta = (ClampMin = "1", ForceUnits = "cm"))
	float SeparationDistance = 260.f;

	/** Acceleration (cm/s^2) applied at full overlap. Falls off quadratically to 0 at SeparationDistance. */
	UPROPERTY(EditAnywhere, Category = "Avoidance", meta = (ClampMin = "0"))
	float SeparationStrength = 3500.f;

	/** How far ahead (s) the relative motion is predicted, so agents start dodging before they touch (the hash reach is capped at 4x SeparationDistance). */
	UPROPERTY(EditAnywhere, Category = "Avoidance", meta = (ClampMin = "0", ForceUnits = "s"))
	float PredictionTime = 0.6f;

	/** Upper bound of neighbours considered per agent (keeps dense clumps cheap). */
	UPROPERTY(EditAnywhere, Category = "Avoidance", meta = (ClampMin = "1"))
	int32 MaxNeighbors = 10;

	/** Clamp for the summed avoidance acceleration. */
	UPROPERTY(EditAnywhere, Category = "Avoidance", meta = (ClampMin = "0"))
	float MaxAvoidanceForce = 7000.f;
};

/**
 * Shared tuning for sentinel-vs-obstacle avoidance (UMechSentinelObstacleAvoidanceProcessor): the hex platforms and boxes
 * registered in UMechSentinelObstacleSubsystem. Project-only, the engine has no 3D counterpart.
 *
 * A sentinel is a sphere of radius R (HardRadius, plus the obstacle's Margin). Inside a cushion of Z cm around that
 * hard shell it is pushed out, and its desired velocity is slid along the surface it is about to hit. Z is SoftMargin,
 * shrunk (down to MinCushion) when the goal is closer than that to the obstacle, so goals next to a platform stay
 * reachable. The registry finds obstacles within 2000 cm: HardRadius + SoftMargin + the look-ahead must fit in that
 * (the look-ahead is shortened to fit).
 */
USTRUCT()
struct AURA_API FMechSentinelObstacleAvoidanceParameters : public FMassConstSharedFragment
{
	GENERATED_BODY()

	/** Off = sentinels fly through the registered obstacles. */
	UPROPERTY(EditAnywhere, Category = "Obstacles")
	bool bEnabled = true;

	/** Radius (cm) of the sentinel's hard shell. 0 = the Mech Sentinel trait's CapsuleHalfHeight (a sphere around the capsule). */
	UPROPERTY(EditAnywhere, Category = "Obstacles", meta = (ClampMin = "0", ForceUnits = "cm"))
	float HardRadius = 0.f;

	/** Cushion (cm) kept between the hard shell and the obstacle when the goal is far from it. */
	UPROPERTY(EditAnywhere, Category = "Obstacles", meta = (ClampMin = "1", ForceUnits = "cm"))
	float SoftMargin = 250.f;

	/** Smallest cushion (cm): goals closer to the obstacle than this are unreachable, the sentinel hovers this far out. Stunned sentinels use it too. */
	UPROPERTY(EditAnywhere, Category = "Obstacles", meta = (ClampMin = "1", ForceUnits = "cm"))
	float MinCushion = 40.f;

	/** The cushion shrinks to the goal's distance from the obstacle minus the hard shell and this (cm). */
	UPROPERTY(EditAnywhere, Category = "Obstacles", meta = (ClampMin = "0", ForceUnits = "cm"))
	float GoalClearance = 25.f;

	/** Push (cm/s^2) at the hard shell, rising quadratically through the cushion. Keep it above the movement's MaxAcceleration (3000). */
	UPROPERTY(EditAnywhere, Category = "Obstacles", meta = (ClampMin = "0"))
	float SeparationAccel = 6000.f;

	/** Extra push (cm/s^2) once the hard shell overlaps the obstacle, full at an overlap of HardRadius. */
	UPROPERTY(EditAnywhere, Category = "Obstacles", meta = (ClampMin = "0"))
	float PenetrationAccel = 9000.f;

	/** Inside the cushion, the velocity into the obstacle is cancelled over about this time (s). */
	UPROPERTY(EditAnywhere, Category = "Obstacles", meta = (ClampMin = "0.01", ForceUnits = "s"))
	float DampingTime = 0.2f;

	/** Clamp for the summed obstacle push (cm/s^2). Keep it above the agent avoidance's MaxAvoidanceForce + MaxAcceleration (7000 + 3000). */
	UPROPERTY(EditAnywhere, Category = "Obstacles", meta = (ClampMin = "0"))
	float MaxObstacleAccel = 15000.f;

	/** The desired velocity is cast this far ahead (s) against the obstacles grown by the shell and cushion, to slide early. */
	UPROPERTY(EditAnywhere, Category = "Obstacles", meta = (ClampMin = "0", ForceUnits = "s"))
	float LookAheadTime = 0.8f;

	/** Speed (cm/s) above which the look-ahead stops growing. */
	UPROPERTY(EditAnywhere, Category = "Obstacles", meta = (ClampMin = "0", ForceUnits = "cm/s"))
	float MaxLookAheadSpeed = 2000.f;

	/** A sentinel whose centre is inside an obstacle flies out along the cheapest exit at least this fast (cm/s). */
	UPROPERTY(EditAnywhere, Category = "Obstacles", meta = (ClampMin = "0", ForceUnits = "cm/s"))
	float ExitSpeed = 600.f;

	/** Going round a platform's side towards a goal behind it: the way up counts this fraction of its length (below 1 favours over). */
	UPROPERTY(EditAnywhere, Category = "Obstacles", meta = (ClampMin = "0"))
	float UpBias = 0.7f;

	/** Inside an obstacle, the exit towards the goal counts this fraction of its depth. */
	UPROPERTY(EditAnywhere, Category = "Obstacles", meta = (ClampMin = "0", ClampMax = "1"))
	float ExitFaceBias = 0.7f;

	/** A hit normal with |Z| above this is a top / bottom face (cap), else a side. */
	UPROPERTY(EditAnywhere, Category = "Obstacles", meta = (ClampMin = "0", ClampMax = "1"))
	float CapNormalZ = 0.7f;

	/** A goal behind the hit face is head-on when its direction along the face is below this fraction: the sentinel goes round instead of sliding. */
	UPROPERTY(EditAnywhere, Category = "Obstacles", meta = (ClampMin = "0", ClampMax = "1"))
	float TangentMin = 0.2f;

	/** Going round a side: a sentinel already climbing or sinking faster than this (cm/s) keeps that way. */
	UPROPERTY(EditAnywhere, Category = "Obstacles", meta = (ClampMin = "0", ForceUnits = "cm/s"))
	float EscapeKeepVz = 150.f;
};
