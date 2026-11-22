// Mech Sentinel Swarm - 3D obstacle avoidance of live sentinels (hex platforms, boxes). Authority only.

#include "MechSwarm/Sentinel/MechSentinelObstacleAvoidanceProcessor.h"

#include "DrawDebugHelpers.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "HAL/IConsoleManager.h"
#include "MassCommonTypes.h"
#include "MassExecutionContext.h"
#include "Mass/EntityFragments.h"
#include "MechSwarm/Core/MechSentinelObstacleSubsystem.h"
#include "MechSwarm/MassCopies/MassAvoidanceFragments_Copy.h"
#include "MechSwarm/MassCopies/MassAvoidanceProcessors_Copy.h"
#include "MechSwarm/MassCopies/MassMovementFragments_Copy.h"
#include "MechSwarm/Sentinel/MechSentinelFragments.h"
#include "MechSwarm/Sentinel/MechSentinelOrbit.h"
#include "ProfilingDebugging/CpuProfilerTrace.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(MechSentinelObstacleAvoidanceProcessor)

namespace MechSwarm::ObstacleAvoidancePrivate
{
#if !UE_BUILD_SHIPPING
	TAutoConsoleVariable<int32> CVarDebugObstacles(
		TEXT("mech.Sentinel.DebugObstacles"),
		0,
		TEXT("Obstacles live sentinels avoid (server / standalone worlds). 1: draw the registered shapes (magenta = not hashed) and show counts. ")
		TEXT("2: also a line per sentinel near one along its new desired velocity (red: centre inside, yellow: sliding, cyan: pushed)."),
		ECVF_Cheat);
#endif

	/** Escape directions of sentinels on a cylinder's axis are spread by this angle (rad) per entity index. */
	constexpr double GoldenAngle = 2.399963229728653;

	/** The tuning of one chunk, sanitised (scripts can bypass ClampMin), in double precision. */
	struct FTuning
	{
		double HardRadius = 140.0;
		double SoftMargin = 250.0;
		double MinCushion = 40.0;
		double GoalClearance = 25.0;
		double SeparationAccel = 6000.0;
		double PenetrationAccel = 9000.0;
		double DampingTime = 0.2;
		double MaxObstacleAccel = 15000.0;
		double LookAheadTime = 0.8;
		double MaxLookAheadSpeed = 2000.0;
		double ExitSpeed = 600.0;
		double UpBias = 0.7;
		double ExitFaceBias = 0.7;
		double CapNormalZ = 0.7;
		double TangentMin = 0.2;
		double EscapeKeepVz = 150.0;

		/** Largest cushion any obstacle can get. */
		double MaxCushion = 250.0;

		/** Longest look-ahead (cm) whose hits the registry still lists in the sentinel's cell. */
		double MaxLookAhead = 1610.0;

		/** Longest look-ahead at any speed, for the broad phase. */
		double LookAheadReach = 1600.0;

		FTuning(const FMechSentinelObstacleAvoidanceParameters& Params, const float CapsuleHalfHeight)
		{
			// The parameter goes first in Max: a NaN then yields the bound
			HardRadius = FMath::Max(double(Params.HardRadius > 0.f ? Params.HardRadius : CapsuleHalfHeight), 1.0);
			SoftMargin = FMath::Max(double(Params.SoftMargin), 1.0);
			MinCushion = FMath::Max(double(Params.MinCushion), 1.0);
			GoalClearance = FMath::Max(double(Params.GoalClearance), 0.0);
			SeparationAccel = FMath::Max(double(Params.SeparationAccel), 0.0);
			PenetrationAccel = FMath::Max(double(Params.PenetrationAccel), 0.0);
			DampingTime = FMath::Max(double(Params.DampingTime), 0.01);
			MaxObstacleAccel = FMath::Max(double(Params.MaxObstacleAccel), 0.0);
			LookAheadTime = FMath::Max(double(Params.LookAheadTime), 0.0);
			MaxLookAheadSpeed = FMath::Max(double(Params.MaxLookAheadSpeed), 0.0);
			ExitSpeed = FMath::Max(double(Params.ExitSpeed), 0.0);
			UpBias = FMath::Max(double(Params.UpBias), 0.0);
			ExitFaceBias = FMath::Clamp(double(Params.ExitFaceBias), 0.0, 1.0);
			CapNormalZ = FMath::Clamp(double(Params.CapNormalZ), 0.0, 1.0);
			TangentMin = FMath::Clamp(double(Params.TangentMin), 0.0, 1.0);
			EscapeKeepVz = FMath::Max(double(Params.EscapeKeepVz), 0.0);

			MaxCushion = FMath::Max(SoftMargin, MinCushion);
			// A hit lies within shell + margin + cushion + look-ahead of the obstacle's bounds, and the registry lists an
			// obstacle in every cell within ObstacleReach + margin of them
			MaxLookAhead = FMath::Max(double(UMechSentinelObstacleSubsystem::ObstacleReach) - HardRadius - MaxCushion, 0.0);
			LookAheadReach = FMath::Min(MaxLookAheadSpeed * LookAheadTime, MaxLookAhead);
		}
	};

	/** The sentinel being solved. */
	struct FSentinel
	{
		FVector Position = FVector::ZeroVector;
		FVector Velocity = FVector::ZeroVector;

		/** Where the steering is heading (valid with bHasGoal). */
		FVector Goal = FVector::ZeroVector;
		bool bHasGoal = false;

		/** Stunned: the smallest cushion, no look-ahead (the sink is not steered). */
		bool bStunned = false;

		/** Fixed per entity: the escape direction off a cap when the sentinel is on the cylinder's axis right over the goal. */
		double EscapeAngle = 0.0;

		/** DesiredMaxSpeedOverride: the result never asks for more. */
		double SpeedCap = TNumericLimits<float>::Max();
	};

	/** An obstacle near the sentinel this frame. */
	struct FNearObstacle
	{
		const FMechSentinelObstacleShape* Shape = nullptr;

		/** R: the sentinel's hard shell plus the obstacle's Margin. */
		double HardRadius = 0.0;

		/** Z: the cushion kept around the hard shell. */
		double Cushion = 0.0;
	};

	enum class EOutcome : uint8
	{
		/** Near an obstacle, nothing to do. */
		Clear,
		/** In a cushion: pushed out. */
		Pushed,
		/** The look-ahead hit an obstacle: the desired velocity slides along it or goes round it. */
		Slid,
		/** The centre is inside an obstacle: flying out. */
		Inside,
	};

	FORCEINLINE bool IsWithinReach(const FBox& Bounds, const FVector& P, const double Reach)
	{
		return P.X >= Bounds.Min.X - Reach && P.X <= Bounds.Max.X + Reach
			&& P.Y >= Bounds.Min.Y - Reach && P.Y <= Bounds.Max.Y + Reach
			&& P.Z >= Bounds.Min.Z - Reach && P.Z <= Bounds.Max.Z + Reach;
	}

	/**
	 * Z of one obstacle (R = shell + its margin): SoftMargin, shrunk next to a goal close to the obstacle so the goal stays
	 * outside the cushion, which is force free, and never below MinCushion. Stunned sentinels keep MinCushion.
	 */
	double GetCushion(const FTuning& Tuning, const FSentinel& Sentinel, const FMechSentinelObstacleShape& Shape, const double R)
	{
		if (Sentinel.bStunned)
		{
			return Tuning.MinCushion;
		}
		if (!Sentinel.bHasGoal)
		{
			return Tuning.SoftMargin;
		}
		return FMath::Max(Tuning.MinCushion, FMath::Clamp(Shape.SignedDistance(Sentinel.Goal) - R - Tuning.GoalClearance, 0.0, Tuning.SoftMargin));
	}

	/** Off a cap the goal is past (or right behind): out over the rim the short way, or out through the nearest box side. */
	FVector GetCapEscapeDirection(const FMechSentinelObstacleShape& Shape, const FSentinel& Sentinel)
	{
		const FVector& P = Sentinel.Position;
		if (Shape.IsCylinder())
		{
			const FVector2D Radial = FVector2D(P) - Shape.Center;
			if (Radial.SizeSquared() > 1.0)
			{
				return FVector(Radial.GetSafeNormal(), 0.0);
			}

			// On the axis: away from the goal, else a fixed direction per sentinel
			const FVector2D FromGoal = FVector2D(P) - FVector2D(Sentinel.Goal);
			if (FromGoal.SizeSquared() > 1.0)
			{
				return FVector(FromGoal.GetSafeNormal(), 0.0);
			}
			return FVector(FMath::Cos(Sentinel.EscapeAngle), FMath::Sin(Sentinel.EscapeAngle), 0.0);
		}

		const FBox& Bounds = Shape.Bounds;
		const double Depths[4] = { P.X - Bounds.Min.X, Bounds.Max.X - P.X, P.Y - Bounds.Min.Y, Bounds.Max.Y - P.Y };
		const FVector Normals[4] = { FVector(-1.0, 0.0, 0.0), FVector(1.0, 0.0, 0.0), FVector(0.0, -1.0, 0.0), FVector(0.0, 1.0, 0.0) };
		int32 Nearest = 0;
		for (int32 Index = 1; Index < 4; ++Index)
		{
			if (Depths[Index] < Depths[Nearest])
			{
				Nearest = Index;
			}
		}
		return Normals[Nearest];
	}

	/**
	 * Box side face (outward Normal mostly along X or Y) with the goal past its plane and within the face grown by Inflate:
	 * sliding along the flat face towards the goal would stop at the goal's projection on it (the cap rule, for a side).
	 */
	bool IsGoalBehindBoxSide(const FBox& Bounds, const FVector& Normal, const FVector& Goal, const double Inflate)
	{
		if (Goal.Z <= Bounds.Min.Z - Inflate || Goal.Z >= Bounds.Max.Z + Inflate)
		{
			return false;
		}
		if (FMath::Abs(Normal.X) >= FMath::Abs(Normal.Y))
		{
			return (Normal.X < 0.0 ? Goal.X > Bounds.Min.X : Goal.X < Bounds.Max.X)
				&& Goal.Y > Bounds.Min.Y - Inflate && Goal.Y < Bounds.Max.Y + Inflate;
		}
		return (Normal.Y < 0.0 ? Goal.Y > Bounds.Min.Y : Goal.Y < Bounds.Max.Y)
			&& Goal.X > Bounds.Min.X - Inflate && Goal.X < Bounds.Max.X + Inflate;
	}

	/**
	 * Off a side the goal is behind: over or under, the shorter way (UpBias favours over). A clear climb or dive goes on.
	 * A box goes over to a goal above it and under to one below it (the cap rule would send the other way back out).
	 */
	FVector GetSideEscapeDirection(const FTuning& Tuning, const FMechSentinelObstacleShape& Shape, const FSentinel& Sentinel, const double Inflate)
	{
		if (!Shape.IsCylinder() && Sentinel.bHasGoal)
		{
			if (Sentinel.Goal.Z > Shape.Bounds.Max.Z)
			{
				return FVector::UpVector;
			}
			if (Sentinel.Goal.Z < Shape.Bounds.Min.Z)
			{
				return FVector::DownVector;
			}
		}

		const double VerticalSpeed = Sentinel.Velocity.Z;
		if (FMath::Abs(VerticalSpeed) > Tuning.EscapeKeepVz)
		{
			return VerticalSpeed > 0.0 ? FVector::UpVector : FVector::DownVector;
		}

		const double Up = (Shape.Bounds.Max.Z + Inflate - Sentinel.Position.Z) * Tuning.UpBias;
		const double Down = Sentinel.Position.Z - (Shape.Bounds.Min.Z - Inflate);
		return Up <= Down ? FVector::UpVector : FVector::DownVector;
	}

	/**
	 * The desired velocity U hits Obstacle's grown shape (shell + cushion) HitDistance ahead, of LookAhead, on a face with
	 * outward normal Normal. Slides U along the face towards the goal at its speed, or, when the goal lies behind the
	 * obstacle, turns it round the obstacle. The closer the hit, the stronger.
	 */
	FVector Slide(const FTuning& Tuning, const FSentinel& Sentinel, const FNearObstacle& Obstacle, const FVector& U, const double HitDistance, const FVector& Normal, const double LookAhead)
	{
		const double Weight = FMath::Square(1.0 - HitDistance / LookAhead);
		const double Into = FMath::Max(0.0, -FVector::DotProduct(U, Normal));
		if (Into <= 0.0)
		{
			return U;
		}

		const FVector& P = Sentinel.Position;
		const FVector ToGoal = Sentinel.bHasGoal ? Sentinel.Goal - P : U;
		const FVector GoalAlongFace = ToGoal - Normal * FVector::DotProduct(ToGoal, Normal);

		// The goal lies behind the hard face the ray hits (not merely inside the cushion on this side)
		const double Inflate = Obstacle.HardRadius + Obstacle.Cushion;
		const FVector HardFacePoint = P + U.GetSafeNormal() * HitDistance - Normal * Inflate;
		const bool bBehind = Sentinel.bHasGoal && FVector::DotProduct(Sentinel.Goal - HardFacePoint, Normal) < 0.0;
		const bool bHeadOn = bBehind && GoalAlongFace.Size() < Tuning.TangentMin * ToGoal.Size();

		const FMechSentinelObstacleShape& Shape = *Obstacle.Shape;
		bool bEscape = false;
		FVector Escape = FVector::ZeroVector;
		if (FMath::Abs(Normal.Z) > Tuning.CapNormalZ)
		{
			// Top or bottom: a goal past the other cap and over the footprint is only reached round the rim
			const bool bGoalPastCap = Sentinel.bHasGoal
				&& (Normal.Z < 0.0 ? Sentinel.Goal.Z > Shape.Bounds.Min.Z : Sentinel.Goal.Z < Shape.Bounds.Max.Z)
				&& Shape.IsOverFootprint(Sentinel.Goal, Inflate);
			if (bGoalPastCap || bHeadOn)
			{
				Escape = GetCapEscapeDirection(Shape, Sentinel);
				bEscape = true;
			}
		}
		else if (bHeadOn || (!Shape.IsCylinder() && Sentinel.bHasGoal && IsGoalBehindBoxSide(Shape.Bounds, Normal, Sentinel.Goal, Inflate)))
		{
			// A flat side has no curve to slide round: a goal behind it is only reached over or under
			Escape = GetSideEscapeDirection(Tuning, Shape, Sentinel, Inflate);
			bEscape = true;
		}

		if (bEscape)
		{
			// Steering's own sideways part points the wrong way here: blend onto the escape, along the face, at full speed
			const FVector Tangent = (Escape - Normal * FVector::DotProduct(Escape, Normal)).GetSafeNormal();
			return U * (1.0 - Weight) + Tangent * (Weight * U.Size());
		}

		// Keep the speed: take out the part into the face and turn it along the face towards the goal, instead of stopping
		const FVector Tangent = GoalAlongFace.GetSafeNormal();
		return U + (Normal + Tangent) * (Weight * Into);
	}

	/**
	 * One sentinel against the obstacles near it (with their cushions). Force holds the agent push on entry and gets the
	 * obstacle push; DesiredVelocity is the steering's on entry.
	 */
	EOutcome Solve(const FTuning& Tuning, const FSentinel& Sentinel, const TConstArrayView<FNearObstacle> Near, FVector& Force, FVector& DesiredVelocity)
	{
		const FVector& P = Sentinel.Position;
		const FVector& V = Sentinel.Velocity;
		const FVector GoalDir = Sentinel.bHasGoal ? Sentinel.Goal - P : DesiredVelocity;

		FVector ObstacleForce = FVector::ZeroVector;
		bool bPushed = false;
		bool bInside = false;
		double DeepestDistance = 0.0;
		FVector DeepestNormal = FVector::ZeroVector;

		for (const FNearObstacle& Obstacle : Near)
		{
			FVector Normal;
			const double Distance = Obstacle.Shape->Closest(P, GoalDir, Tuning.ExitFaceBias, Normal);
			const double Cushion = Obstacle.Cushion;
			const double Clearance = Distance - Obstacle.HardRadius;
			const double Eta = (Cushion - Clearance) / Cushion;
			if (Eta > 0.0)
			{
				const double Weight = FMath::Min(Eta, 1.0);

				// The agent push must not shove the sentinel into the obstacle
				Force += Normal * (Weight * FMath::Max(0.0, -FVector::DotProduct(Force, Normal)));

				const double Accel = Tuning.SeparationAccel * Weight * Weight
					+ Tuning.PenetrationAccel * FMath::Clamp((Eta - 1.0) * Cushion / Obstacle.HardRadius, 0.0, 1.0)
					+ Weight * FMath::Max(0.0, -FVector::DotProduct(V, Normal)) / Tuning.DampingTime;
				ObstacleForce += Normal * Accel;
				bPushed = true;
			}

			if (Distance < 0.0 && (!bInside || Distance < DeepestDistance))
			{
				bInside = true;
				DeepestDistance = Distance;
				DeepestNormal = Normal;
			}
		}
		Force += ObstacleForce.GetClampedToMaxSize(Tuning.MaxObstacleAccel);

		if (bInside)
		{
			// The centre is inside: straight out through the cheapest exit (towards the goal when it is about as cheap)
			DesiredVelocity = (DeepestNormal * FMath::Max(DesiredVelocity.Size(), Tuning.ExitSpeed)).GetClampedToMaxSize(Sentinel.SpeedCap);
			return EOutcome::Inside;
		}

		if (Sentinel.bStunned)
		{
			return bPushed ? EOutcome::Pushed : EOutcome::Clear;
		}

		// Look ahead along the desired velocity: slide along the first grown face it hits, then once more along the next
		// obstacle the slid velocity hits
		FVector U = DesiredVelocity;
		int32 FirstHit = INDEX_NONE;
		bool bSlid = false;
		for (int32 Pass = 0; Pass < 2; ++Pass)
		{
			const double Speed = U.Size();
			const double LookAhead = FMath::Min(FMath::Min(Speed, Tuning.MaxLookAheadSpeed) * Tuning.LookAheadTime, Tuning.MaxLookAhead);
			if (Speed <= 1.0 || LookAhead <= 0.0)
			{
				break;
			}
			const FVector Dir = U / Speed;

			int32 Best = INDEX_NONE;
			double BestDistance = 0.0;
			FVector BestNormal = FVector::ZeroVector;
			bool bBestInside = false;
			for (int32 Index = 0; Index < Near.Num(); ++Index)
			{
				if (Index == FirstHit)
				{
					continue;
				}

				const FNearObstacle& Obstacle = Near[Index];
				double HitDistance = 0.0;
				FVector HitNormal = FVector::ZeroVector;
				bool bHitInside = false;
				if (Obstacle.Shape->Raycast(P, Dir, LookAhead, Obstacle.HardRadius + Obstacle.Cushion, HitDistance, HitNormal, bHitInside)
					&& (Best == INDEX_NONE || HitDistance < BestDistance))
				{
					Best = Index;
					BestDistance = HitDistance;
					BestNormal = HitNormal;
					bBestInside = bHitInside;
				}
			}
			if (Best == INDEX_NONE)
			{
				break;
			}

			FirstHit = Best;
			if (bBestInside)
			{
				// Already in the grown shape: slide along the real surface below
				Near[Best].Shape->Closest(P, GoalDir, Tuning.ExitFaceBias, BestNormal);
			}
			U = Slide(Tuning, Sentinel, Near[Best], U, BestDistance, BestNormal, LookAhead);
			bSlid = true;
		}

		DesiredVelocity = U.GetClampedToMaxSize(Sentinel.SpeedCap);
		return bSlid ? EOutcome::Slid : bPushed ? EOutcome::Pushed : EOutcome::Clear;
	}

#if !UE_BUILD_SHIPPING
	void DrawObstacles(const UWorld* World, const UMechSentinelObstacleSubsystem& Obstacles)
	{
		TArray<FMechSentinelObstacleShape> Shapes;
		TArray<bool> Oversized;
		Obstacles.GetObstacleShapes(Shapes, &Oversized);

		for (int32 Index = 0; Index < Shapes.Num(); ++Index)
		{
			const FMechSentinelObstacleShape& Shape = Shapes[Index];
			const FColor Color = Oversized[Index] ? FColor::Magenta : FColor::Orange;
			if (Shape.IsCylinder())
			{
				DrawDebugCylinder(World, FVector(Shape.Center, Shape.Bounds.Min.Z), FVector(Shape.Center, Shape.Bounds.Max.Z),
					float(Shape.Radius), 48, Color, false, -1.f, 0, 8.f);
			}
			else
			{
				DrawDebugBox(World, Shape.Bounds.GetCenter(), Shape.Bounds.GetExtent(), Color, false, -1.f, 0, 8.f);
			}
		}
	}
#endif
}

//----------------------------------------------------------------------//
// UMechSentinelObstacleAvoidanceProcessor
//----------------------------------------------------------------------//
UMechSentinelObstacleAvoidanceProcessor::UMechSentinelObstacleAvoidanceProcessor()
	: EntityQuery(*this)
{
	ExecutionFlags = (int32)(EProcessorExecutionFlags::Standalone | EProcessorExecutionFlags::Server);
	ExecutionOrder.ExecuteInGroup = UE::Mass::ProcessorGroupNames::Avoidance;
	// Reads this frame's agent push, to take out its part into obstacles
	ExecutionOrder.ExecuteAfter.Add(UMassMovingAvoidanceProcessor_Copy::StaticClass()->GetFName());
	// Reads the obstacle registry, which actors change on the game thread
	bRequiresGameThreadExecution = true;
}

void UMechSentinelObstacleAvoidanceProcessor::ConfigureQueries(const TSharedRef<FMassEntityManager>& EntityManager)
{
	EntityQuery.AddRequirement<FTransformFragment>(EMassFragmentAccess::ReadOnly);
	EntityQuery.AddRequirement<FMassVelocityFragment_Copy>(EMassFragmentAccess::ReadOnly);
	EntityQuery.AddRequirement<FMassForceFragment_Copy>(EMassFragmentAccess::ReadWrite);
	EntityQuery.AddRequirement<FMassDesiredMovementFragment_Copy>(EMassFragmentAccess::ReadWrite);
	EntityQuery.AddRequirement<FMechSentinelTargetFragment>(EMassFragmentAccess::ReadOnly);
	EntityQuery.AddConstSharedRequirement<FMechSentinelParameters>(EMassFragmentPresence::All);
	EntityQuery.AddConstSharedRequirement<FMechSentinelObstacleAvoidanceParameters>(EMassFragmentPresence::All);
	EntityQuery.AddTagRequirement<FMechSentinelTag>(EMassFragmentPresence::All);
	EntityQuery.AddTagRequirement<FMechSentinelDeadTag>(EMassFragmentPresence::None);
	EntityQuery.AddTagRequirement<FMassCustomMovementTag_Copy>(EMassFragmentPresence::None);
}

void UMechSentinelObstacleAvoidanceProcessor::Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context)
{
	using namespace MechSwarm::ObstacleAvoidancePrivate;

	UWorld* World = EntityManager.GetWorld();
	UMechSentinelObstacleSubsystem* Obstacles = UMechSentinelObstacleSubsystem::Get(World);
	if (!Obstacles)
	{
		return;
	}

	// Owners destroyed without unregistering (once per second); nothing else changes the registry during the loop below
	Obstacles->SweepStaleOwners();

#if !UE_BUILD_SHIPPING
	const int32 DebugMode = CVarDebugObstacles.GetValueOnGameThread();
	if (DebugMode > 0)
	{
		DrawObstacles(World, *Obstacles);
	}
	int32 NumNear = 0;
	int32 NumSliding = 0;
	int32 NumInside = 0;
#endif

	if (Obstacles->GetNumObstacles() == 0)
	{
		return;
	}

	TRACE_CPUPROFILER_EVENT_SCOPE(MechSentinelObstacleAvoidance);

	// The steering's clock for the orbit bob (MechSwarm::Orbit::GetGoal)
	const float OrbitTime = World ? float(World->GetTimeSeconds()) : 0.f;

	// Other name than Context: the default capture would make a same-named parameter shadow it
	EntityQuery.ForEachEntityChunk(Context, [&](FMassExecutionContext& ChunkContext)
	{
		const FMechSentinelObstacleAvoidanceParameters& ObstacleParams = ChunkContext.GetConstSharedFragment<FMechSentinelObstacleAvoidanceParameters>();
		if (!ObstacleParams.bEnabled)
		{
			return;
		}

		const FMechSentinelParameters& Params = ChunkContext.GetConstSharedFragment<FMechSentinelParameters>();
		const FTuning Tuning(ObstacleParams, Params.CapsuleHalfHeight);
		const bool bStunned = ChunkContext.DoesArchetypeHaveTag<FMechSentinelStunnedTag>();

		// Broad phase: no force beyond shell + cushion, no hit beyond that plus the look-ahead
		const double BroadReach = Tuning.MaxCushion + (bStunned ? 0.0 : Tuning.LookAheadReach);

		const TConstArrayView<FTransformFragment> TransformList = ChunkContext.GetFragmentView<FTransformFragment>();
		const TConstArrayView<FMassVelocityFragment_Copy> VelocityList = ChunkContext.GetFragmentView<FMassVelocityFragment_Copy>();
		const TArrayView<FMassForceFragment_Copy> ForceList = ChunkContext.GetMutableFragmentView<FMassForceFragment_Copy>();
		const TArrayView<FMassDesiredMovementFragment_Copy> DesiredList = ChunkContext.GetMutableFragmentView<FMassDesiredMovementFragment_Copy>();
		const TConstArrayView<FMechSentinelTargetFragment> TargetList = ChunkContext.GetFragmentView<FMechSentinelTargetFragment>();

		TArray<FNearObstacle, TInlineAllocator<16>> Near;

		const int32 NumEntities = ChunkContext.GetNumEntities();
		for (int32 EntityIndex = 0; EntityIndex < NumEntities; ++EntityIndex)
		{
			FMassDesiredMovementFragment_Copy& Desired = DesiredList[EntityIndex];
			const FMechSentinelTargetFragment& Target = TargetList[EntityIndex];

			FSentinel Sentinel;
			Sentinel.Position = TransformList[EntityIndex].GetTransform().GetLocation();
			Sentinel.Velocity = VelocityList[EntityIndex].Value;
			Sentinel.bStunned = bStunned;
			Sentinel.bHasGoal = Target.HasTarget();
			if (Sentinel.bHasGoal)
			{
				// As the steering computes it (it already turned the orbit this frame)
				Sentinel.Goal = MechSwarm::Orbit::GetGoal(Target, Params, ChunkContext.GetEntity(EntityIndex).Index, OrbitTime);
			}
			Sentinel.EscapeAngle = double(ChunkContext.GetEntity(EntityIndex).Index) * GoldenAngle;
			Sentinel.SpeedCap = Desired.DesiredMaxSpeedOverride;

			Near.Reset();
			const auto Gather = [&Near, &Sentinel, &Tuning, Obstacles, BroadReach](const TConstArrayView<int32> SlotIndices)
			{
				for (const int32 SlotIndex : SlotIndices)
				{
					const FMechSentinelObstacleShape& Shape = Obstacles->GetObstacleShape(SlotIndex);
					const double HardRadius = Tuning.HardRadius + Shape.Margin;
					if (IsWithinReach(Shape.Bounds, Sentinel.Position, HardRadius + BroadReach))
					{
						FNearObstacle& Entry = Near.AddDefaulted_GetRef();
						Entry.Shape = &Shape;
						Entry.HardRadius = HardRadius;
						Entry.Cushion = GetCushion(Tuning, Sentinel, Shape, HardRadius);
					}
				}
			};
			Gather(Obstacles->GetObstacleCandidates(Sentinel.Position));
			Gather(Obstacles->GetOversizedObstacles());
			if (Near.IsEmpty())
			{
				continue;
			}

			const EOutcome Outcome = Solve(Tuning, Sentinel, Near, ForceList[EntityIndex].Value, Desired.DesiredVelocity);

#if !UE_BUILD_SHIPPING
			if (DebugMode > 0)
			{
				++NumNear;
				NumSliding += Outcome == EOutcome::Slid ? 1 : 0;
				NumInside += Outcome == EOutcome::Inside ? 1 : 0;
				if (DebugMode > 1 && Outcome != EOutcome::Clear)
				{
					const FColor Color = Outcome == EOutcome::Inside ? FColor::Red : Outcome == EOutcome::Slid ? FColor::Yellow : FColor::Cyan;
					DrawDebugLine(World, Sentinel.Position, Sentinel.Position + Desired.DesiredVelocity * 0.3, Color, false, -1.f, 0, 3.f);
				}
			}
#endif
		}
	});

#if !UE_BUILD_SHIPPING
	if (DebugMode > 0 && GEngine)
	{
		GEngine->AddOnScreenDebugMessage(int32(0x4D534F42), 0.f, FColor::Orange, FString::Printf(
			TEXT("Sentinel obstacles: %d registered | sentinels near one %d, sliding %d, centre inside %d"),
			Obstacles->GetNumObstacles(), NumNear, NumSliding, NumInside));
	}
#endif
}
