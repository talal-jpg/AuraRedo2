// Mech Sentinel Swarm - Niagara ribbon tentacles: simulation processor.

#include "MechSwarm/Tentacles/MechSentinelTentacleProcessor.h"

#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "MassExecutionContext.h"
#include "Mass/EntityFragments.h"
#include "MechSwarm/Core/MechSwarmProcessorGroups.h"
#include "MechSwarm/MassCopies/MassLODFragments_Copy.h"
#include "MechSwarm/MassCopies/MassRepresentationFragments_Copy.h"
#include "MechSwarm/MassCopies/MassRepresentationProcessors_Copy.h"
#include "MechSwarm/MassCopies/MassRepresentationSubsystem_Copy.h"
#include "MechSwarm/Sentinel/MechSentinelFragments.h"
#include "MechSwarm/Sentinel/MechSentinelProcessors.h"
#include "MechSwarm/Tentacles/MechSentinelTentacleSubsystem.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(MechSentinelTentacleProcessor)

namespace MechSwarm::Tentacles
{
	/** Per-sentinel modifiers derived from its state and self-buffs. */
	struct FRigInputs
	{
		float StiffnessScale = 1.f;
		float GravityScale = 1.f;
		float SwayScale = 1.f;
		float SwaySpeedScale = 1.f;
		float WidthScale = 1.f;
		float Glow = 0.f;
	};

	/** Self-buff looks at full fade: damage glows, speed streamlines (stiffer, less sway), armor thickens (claws too). */
	constexpr float DamageBuffGlow = 0.45f;
	constexpr float SpeedBuffStiffnessScale = 1.4f;
	constexpr float SpeedBuffSwayScale = 0.6f;
	constexpr float ArmorBuffWidthScale = 1.2f;

	/**
	 * CustomData (optional): the sentinel's ISM custom data, whose [4..6] are the self-buff fades written by
	 * UMechSentinelVisualDataProcessor (0..1, from the replicated BuffMask).
	 */
	FRigInputs MakeInputs(const FMechSentinelTentacleDesc& Desc, const FMechSentinelStateFragment* State, const FMechSentinelAttackFragment* Attack,
		const FMassRepresentationCustomDataFragment_Copy* CustomData)
	{
		FRigInputs Inputs;
		if (State)
		{
			switch (State->State)
			{
			case EMechSentinelState::Attacking:
				Inputs.StiffnessScale = 1.2f;
				Inputs.SwayScale = 1.3f;
				Inputs.SwaySpeedScale = Desc.AttackSwayMultiplier;
				break;
			case EMechSentinelState::Stunned:
				Inputs.StiffnessScale = 0.35f;
				Inputs.GravityScale = 1.6f;
				Inputs.SwayScale = 0.25f;
				break;
			case EMechSentinelState::Dead:
				Inputs.StiffnessScale = Desc.DeadStiffnessScale;
				Inputs.GravityScale = 3.f;
				Inputs.SwayScale = 0.f;
				break;
			default:
				break;
			}
			Inputs.Glow = State->HitFlash;
		}
		if (Attack)
		{
			Inputs.Glow = FMath::Max(Inputs.Glow, Attack->AttackGlow);
		}

		// Self-buffs (none on wrecks). A stun's droop wins over the speed buff's streamlining. SwaySpeedScale is never
		// touched: it multiplies the absolute time, so changing it would make the sway jump.
		const EMechSentinelState SentinelState = State ? State->State : EMechSentinelState::Seeking;
		if (CustomData && SentinelState != EMechSentinelState::Dead)
		{
			const float* BuffFades = CustomData->Values + MechSentinelSelfBuff::FirstFadeCustomDataIndex;
			const float ArmorFade = FMath::Clamp(BuffFades[int32(EMechSentinelSelfBuff::Armor)], 0.f, 1.f);
			const float SpeedFade = FMath::Clamp(BuffFades[int32(EMechSentinelSelfBuff::Speed)], 0.f, 1.f);
			const float DamageFade = FMath::Clamp(BuffFades[int32(EMechSentinelSelfBuff::Damage)], 0.f, 1.f);

			Inputs.WidthScale = FMath::Lerp(1.f, ArmorBuffWidthScale, ArmorFade);
			Inputs.Glow = FMath::Max(Inputs.Glow, DamageBuffGlow * DamageFade);
			if (SentinelState != EMechSentinelState::Stunned)
			{
				Inputs.StiffnessScale *= FMath::Lerp(1.f, SpeedBuffStiffnessScale, SpeedFade);
				Inputs.SwayScale *= FMath::Lerp(1.f, SpeedBuffSwayScale, SpeedFade);
			}
		}

		Inputs.Glow = FMath::Clamp(Inputs.Glow, 0.f, 1.f);
		return Inputs;
	}

	/** Head-relative trailing pose: leaves the socket along its rest direction and bends back / down along the chain. */
	FORCEINLINE FVector RestDirectionAt(const FVector& RootDirection, const FVector& TrailDirection, const float T)
	{
		const float Blend = FMath::SmoothStep(0.f, 1.f, FMath::Min(1.f, T * 2.2f));
		return FMath::Lerp(RootDirection, TrailDirection, Blend).GetSafeNormal();
	}

	/**
	 * The current the tentacles drift in: two octaves of an ABC flow (each component varies only across the other two
	 * axes, so the field is divergence free and swirls instead of pushing everything one way). World space and shared,
	 * so neighbouring sentinels sway together. Unit RMS magnitude.
	 */
	FORCEINLINE FVector FlowAt(const FVector& Position, const double InvScale, const double Time)
	{
		const FVector A = Position * InvScale;
		const FVector B = A * 2.13;
		return FVector(
			FMath::Cos(A.Z + 0.71 * Time) + 0.5 * FMath::Cos(B.Y - 1.37 * Time + 1.7),
			FMath::Cos(A.X + 1.13 * Time) + 0.5 * FMath::Cos(B.Z - 0.93 * Time + 4.1),
			FMath::Cos(A.Y + 0.89 * Time) + 0.5 * FMath::Cos(B.X - 1.21 * Time + 2.3)) * (1.0 / 1.37);
	}

	/** The current at a point of a chain, from samples at the root, the middle point and the tip (linear in between). */
	FORCEINLINE FVector InterpolateFlow(const FVector (&Samples)[3], const int32 Point, const int32 MidPoint, const int32 LastPoint)
	{
		return Point <= MidPoint
			? FMath::Lerp(Samples[0], Samples[1], float(Point) / float(MidPoint))
			: FMath::Lerp(Samples[1], Samples[2], float(Point - MidPoint) / float(LastPoint - MidPoint));
	}

	/** Direction turned toward Reference until it is at most the max bend angle away from it. */
	FORCEINLINE FVector LimitBend(const FVector& Direction, const FVector& Reference, const FVector& Fallback, const double CosMax, const double SinMax)
	{
		const double Cos = FVector::DotProduct(Direction, Reference);
		if (Cos >= CosMax)
		{
			return Direction;
		}
		// Bend in the plane of the two directions (folded straight back: the plane of the fallback).
		FVector Perpendicular = Direction - Reference * Cos;
		if (!Perpendicular.Normalize(UE_KINDA_SMALL_NUMBER))
		{
			Perpendicular = Fallback - Reference * FVector::DotProduct(Fallback, Reference);
			if (!Perpendicular.Normalize(UE_KINDA_SMALL_NUMBER))
			{
				Perpendicular = FVector::CrossProduct(Reference, FVector::UpVector).GetSafeNormal(UE_KINDA_SMALL_NUMBER, FVector::RightVector);
			}
		}
		return Reference * CosMax + Perpendicular * SinMax;
	}

	/**
	 * Steps one rig. Returns true when the rig was laid out from scratch this frame (new owner or teleport): its points
	 * jumped from wherever they were, so its ribbons are hidden for this one frame (no stretched ribbon or motion-vector
	 * streak) and the caller draws the baked far mesh instead, which is what the sentinel showed before.
	 *
	 * Each point is a verlet particle with drag (Damping), gravity, the flow field and a spring toward the trailing pose.
	 * Then, from the root to the tip, it is tied to the point before it: it may bend at most MaxBendAngle, and a stretched
	 * segment springs back toward SegmentLength (XPBD, critically damped) up to StretchRatio. Because the tie only pulls,
	 * a fast head drags its tentacles into long streams that catch up when it slows down. Every rate is frame rate
	 * independent (checked offline at 15 to 240 fps). VelocityScale is this frame's time over last frame's (time-corrected
	 * verlet): the motion a long frame made is carried on at the speed it was made at, so a hitch does not fling the chains.
	 */
	bool SimulateRig(FMechSentinelTentacleSet& Set, const int32 Rig, const FTransform& MeshTransform, const bool bReset,
		const FRigInputs& Inputs, const float DeltaTime, const float VelocityScale, const float Time)
	{
		const FMechSentinelTentacleDesc& Desc = Set.Desc;
		const int32 NumPoints = Desc.PointsPerTentacle;
		const float Segment = Desc.SegmentLength;
		const float MaxSegment = Segment * FMath::Max(1.f, Desc.StretchRatio);
		const float InvLastPoint = 1.f / float(NumPoints - 1);
		const float DeltaTimeSq = FMath::Square(DeltaTime);

		const FQuat Rotation = MeshTransform.GetRotation();
		const FVector Forward = Rotation.GetAxisX();
		const FVector Up = Rotation.GetAxisZ();
		const FVector GravityAccel(0.f, 0.f, -Desc.Gravity * Inputs.GravityScale);
		const float Retain = FMath::Pow(1.f - FMath::Clamp(Desc.Damping, 0.f, 1.f), DeltaTime * 60.f) * VelocityScale;
		const float SwayAngle = UE_TWO_PI * Desc.SwayFrequency * Inputs.SwaySpeedScale * Time;
		const float TeleportSq = FMath::Square(Desc.TeleportDistance);

		// Catch-up: XPBD fraction of a spring of CatchUpRate rad/s (stable at any frame rate), plus critical damping of
		// how fast the segment stretches or shrinks, so it catches up without bouncing.
		const float CatchUpStep = Desc.CatchUpRate * DeltaTime;
		const float CatchUp = FMath::Square(CatchUpStep) / (1.f + FMath::Square(CatchUpStep));
		const float CatchUpDamping = 1.f - FMath::Exp(-2.f * CatchUpStep);
		const float Straighten = 1.f - FMath::Exp(-Desc.Straightening * Inputs.StiffnessScale * DeltaTime);
		const float MaxBend = FMath::DegreesToRadians(FMath::Clamp(Desc.MaxBendAngle, 1.f, 180.f));
		const double CosMaxBend = FMath::Cos(MaxBend);
		const double SinMaxBend = FMath::Sin(MaxBend);
		const double InvFlowScale = 1.0 / FMath::Max(Desc.FlowScale, 1.f);
		const double FlowTime = double(Time) * Desc.FlowSpeed;
		const float FlowAccel = Desc.FlowStrength * Inputs.SwayScale;
		const int32 MidPoint = (NumPoints - 1) / 2;

		Set.RigSeen[Rig] = true;

		// Decided per rig (not per chain) so a rig is either all ribbons or all far mesh.
		const FVector FirstRoot = MeshTransform.TransformPosition(Set.RootOffsets[0]);
		const bool bLayOut = bReset || FVector::DistSquared(Set.Positions[Set.PointIndex(Rig, 0, 0)], FirstRoot) > TeleportSq;

		for (int32 Tentacle = 0; Tentacle < Desc.NumTentacles; ++Tentacle)
		{
			const int32 Base = Set.PointIndex(Rig, Tentacle, 0);
			const FVector Root = MeshTransform.TransformPosition(Set.RootOffsets[Tentacle]);
			const FVector RootDirection = Rotation.RotateVector(Set.RootDirections[Tentacle]);
			const FVector Radial = Rotation.RotateVector(Set.RootRadials[Tentacle]);
			const FVector Trail = (-Forward + Radial * Desc.TrailSpread - Up * Desc.TrailDroop).GetSafeNormal();
			FVector Side = FVector::CrossProduct(Trail, Up);
			Side = Side.GetSafeNormal(UE_SMALL_NUMBER, Rotation.GetAxisY());
			const float Phase = Set.RigPhases[Rig] + 0.9f * float(Tentacle);

			const int32 Ribbon = Set.RibbonIndex(Rig, Tentacle);
			Set.WidthScales[Ribbon] = bLayOut ? 0.f : Inputs.WidthScale;
			Set.Glow[Ribbon] = Inputs.Glow;

			// The root keeps last frame's position as its previous one: the catch-up damping needs the root's motion.
			Set.PrevPositions[Base] = bLayOut ? Root : Set.Positions[Base];
			Set.Positions[Base] = Root;
			Set.FrameBounds += Root;

			// The current is sampled at the root, the middle and the tip (where the points were last frame) and
			// interpolated in between: its wavelengths are metres, the points centimetres apart, and it is the costliest
			// part of a step.
			const bool bFlow = FlowAccel > 0.f && !bLayOut;
			FVector FlowSamples[3] = { FVector::ZeroVector, FVector::ZeroVector, FVector::ZeroVector };
			if (bFlow)
			{
				FlowSamples[0] = FlowAt(Root, InvFlowScale, FlowTime);
				FlowSamples[1] = FlowAt(Set.Positions[Base + MidPoint], InvFlowScale, FlowTime);
				FlowSamples[2] = FlowAt(Set.Positions[Base + NumPoints - 1], InvFlowScale, FlowTime);
			}

			FVector RestPoint = Root;
			for (int32 Point = 1; Point < NumPoints; ++Point)
			{
				const float T = float(Point) * InvLastPoint;
				const FVector RestDirection = RestDirectionAt(RootDirection, Trail, T);
				RestPoint += RestDirection * Segment;

				FVector& Position = Set.Positions[Base + Point];
				FVector& PrevPosition = Set.PrevPositions[Base + Point];

				if (bLayOut)
				{
					Position = PrevPosition = RestPoint;
					Set.FrameBounds += Position;
					continue;
				}

				// Swimming wave travelling from the root to the tip, growing along the chain.
				const float Wave = FMath::Sin(SwayAngle + Phase - Desc.SwayPhasePerPoint * float(Point)) * Desc.SwayAmplitude * Inputs.SwayScale * T;
				const FVector Target = RestPoint + Side * Wave + Up * (0.3f * Wave * FMath::Cos(Phase));

				// Verlet step: inertia (with drag), gravity and the current (0 at the root, full at the tip).
				const FVector Flow = bFlow ? InterpolateFlow(FlowSamples, Point, MidPoint, NumPoints - 1) * (FlowAccel * T) : FVector::ZeroVector;
				const FVector Velocity = (Position - PrevPosition) * Retain;
				PrevPosition = Position;
				Position += Velocity + (GravityAccel + Flow) * DeltaTimeSq;

				// Spring toward the trailing pose, softer toward the tip so the ends lag and whip. Applied to the predicted
				// position, like the pose it pulls toward (both are this frame's).
				const float Stiffness = Desc.Stiffness * Inputs.StiffnessScale * FMath::Lerp(1.f, Desc.TipStiffnessScale, T);
				Position += (Target - Position) * FMath::Min(Stiffness * DeltaTimeSq, 1.f);

				// Straightening: ease toward the continuation of the segment before. The previous position moves too, so
				// it smooths the shape without adding speed.
				const FVector& Parent = Set.Positions[Base + Point - 1];
				const FVector ParentDirection = Point > 1
					? (Parent - Set.Positions[Base + Point - 2]).GetSafeNormal(UE_SMALL_NUMBER, RootDirection)
					: RootDirection;
				const FVector Smooth = (Parent + ParentDirection * Segment - Position) * Straighten;
				Position += Smooth;
				PrevPosition += Smooth;

				// Tie to the point before: bend at most MaxBendAngle, length between SegmentLength and MaxSegment, a
				// stretched segment springing back toward SegmentLength.
				const FVector Delta = Position - Parent;
				double Length = Delta.Size();
				const FVector Direction = LimitBend(Length > UE_KINDA_SMALL_NUMBER ? Delta / Length : RestDirection, ParentDirection, RestDirection, CosMaxBend, SinMaxBend);
				if (Length > Segment)
				{
					Length = FMath::Min(Length - (Length - Segment) * CatchUp, double(MaxSegment));
				}
				Length = FMath::Max(Length, double(Segment));
				Position = Parent + Direction * Length;

				if (Length > Segment)
				{
					const FVector ParentMotion = Parent - Set.PrevPositions[Base + Point - 1];
					const double StretchSpeed = FVector::DotProduct((Position - PrevPosition) - ParentMotion, Direction);
					PrevPosition += Direction * (StretchSpeed * CatchUpDamping);
				}

				Set.FrameBounds += Position;
			}
		}
		return bLayOut;
	}
}

UMechSentinelTentacleProcessor::UMechSentinelTentacleProcessor()
	: EntityQuery(*this)
{
	ExecutionFlags = (int32)(EProcessorExecutionFlags::Standalone | EProcessorExecutionFlags::Client);
	ProcessingPhase = EMassProcessingPhase::PostPhysics;
	ExecutionOrder.ExecuteInGroup = MechSwarm::ProcessorGroups::Representation();
	ExecutionOrder.ExecuteAfter.Add(UMassVisualizationLODProcessor_Copy::StaticClass()->GetFName());
	// Reads this frame's self-buff fades from the ISM custom data.
	ExecutionOrder.ExecuteAfter.Add(UMechSentinelVisualDataProcessor::StaticClass()->GetFName());
	// The ISM update must see this frame's bForceLowLODMesh.
	ExecutionOrder.ExecuteBefore.Add(UMassUpdateISMProcessor_Copy::StaticClass()->GetFName());
	// Rig pool, member scratch arrays and the Niagara component.
	bRequiresGameThreadExecution = true;
}

void UMechSentinelTentacleProcessor::ConfigureQueries(const TSharedRef<FMassEntityManager>& EntityManager)
{
	EntityQuery.AddRequirement<FTransformFragment>(EMassFragmentAccess::ReadOnly);
	EntityQuery.AddRequirement<FMassViewerInfoFragment_Copy>(EMassFragmentAccess::ReadOnly);
	EntityQuery.AddRequirement<FMassRepresentationLODFragment_Copy>(EMassFragmentAccess::ReadWrite);
	EntityQuery.AddRequirement<FMechSentinelTentacleFragment>(EMassFragmentAccess::ReadWrite);
	EntityQuery.AddRequirement<FMechSentinelStateFragment>(EMassFragmentAccess::ReadOnly, EMassFragmentPresence::Optional);
	EntityQuery.AddRequirement<FMechSentinelAttackFragment>(EMassFragmentAccess::ReadOnly, EMassFragmentPresence::Optional);
	// Self-buff fades (written by UMechSentinelVisualDataProcessor just before).
	EntityQuery.AddRequirement<FMassRepresentationCustomDataFragment_Copy>(EMassFragmentAccess::ReadOnly, EMassFragmentPresence::Optional);
	EntityQuery.AddConstSharedRequirement<FMechSentinelTentacleParams>(EMassFragmentPresence::All);
	EntityQuery.AddConstSharedRequirement<FMassRepresentationParameters_Copy>(EMassFragmentPresence::All);
}

void UMechSentinelTentacleProcessor::Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context)
{
	using namespace MechSwarm::Tentacles;

	UWorld* World = EntityManager.GetWorld();
	UMechSentinelTentacleSubsystem* TentacleSubsystem = World ? World->GetSubsystem<UMechSentinelTentacleSubsystem>() : nullptr;
	const UMassRepresentationSubsystem_Copy* RepresentationSubsystem = World ? World->GetSubsystem<UMassRepresentationSubsystem_Copy>() : nullptr;
	// No early out on "no sets": configs without a Niagara system still need bForceLowLODMesh written below.
	if (!TentacleSubsystem)
	{
		return;
	}

	// Large hitches would explode the verlet step; the chains just lag a little instead.
	const float RawDeltaTime = Context.GetDeltaTimeSeconds();
	const float DeltaTime = FMath::Clamp(RawDeltaTime, 1.e-4f, 1.f / 15.f);
	// Last frame's motion covered last frame's real time (a hitch's included): carry it on at that speed.
	const float VelocityScale = PreviousDeltaTime > 0.f ? FMath::Min(DeltaTime / FMath::Max(PreviousDeltaTime, 1.e-4f), 4.f) : 1.f;
	PreviousDeltaTime = RawDeltaTime;
	const float Time = float(World->GetTimeSeconds());

	TentacleSubsystem->BeginFrame();
	Candidates.Reset();

	// Pass 1: who wants ribbons this frame.
	EntityQuery.ForEachEntityChunk(Context, [this, TentacleSubsystem](FMassExecutionContext& Context)
	{
		const FMechSentinelTentacleParams& Params = Context.GetConstSharedFragment<FMechSentinelTentacleParams>();
		const FMechSentinelTentacleSet* Set = TentacleSubsystem->GetMutableSet(Params.SetIndex);
		const float MaxDistanceSq = Set ? FMath::Square(Set->Desc.MaxDistance) : 0.f;
		// Hysteresis: a sentinel keeps its ribbons until 10% past MaxDistance, so it does not flicker at the edge.
		const float KeepDistanceSq = MaxDistanceSq * 1.21f;

		const TConstArrayView<FMassViewerInfoFragment_Copy> ViewerList = Context.GetFragmentView<FMassViewerInfoFragment_Copy>();
		const TConstArrayView<FMassRepresentationLODFragment_Copy> LODList = Context.GetFragmentView<FMassRepresentationLODFragment_Copy>();
		const TConstArrayView<FMechSentinelTentacleFragment> TentacleList = Context.GetFragmentView<FMechSentinelTentacleFragment>();

		const int32 NumEntities = Context.GetNumEntities();
		for (int32 EntityIndex = 0; EntityIndex < NumEntities; ++EntityIndex)
		{
			const float DistanceSq = ViewerList[EntityIndex].ClosestViewerDistanceSq;
			const EMassLOD::Type LOD = LODList[EntityIndex].LOD;

			FCandidate& Candidate = Candidates.AddDefaulted_GetRef();
			Candidate.Entity = Context.GetEntity(EntityIndex);
			Candidate.DistanceSq = DistanceSq;
			Candidate.SetIndex = Params.SetIndex;
			Candidate.RigIndex = TentacleList[EntityIndex].RigIndex;
			const bool bOwnsRig = TentacleSubsystem->IsRigOwnedBy(Params.SetIndex, Candidate.RigIndex, Candidate.Entity);
			Candidate.bWants = Set != nullptr && LOD <= EMassLOD::Medium && DistanceSq < (bOwnsRig ? KeepDistanceSq : MaxDistanceSq);
		}
	});

	// Budget: the closest sentinels win. Current owners count as 20% closer so rigs do not flip between neighbours.
	for (int32 SetIndex = 0; SetIndex < TentacleSubsystem->GetNumSets(); ++SetIndex)
	{
		const int32 Capacity = TentacleSubsystem->GetMutableSet(SetIndex)->Desc.MaxRiggedSentinels;
		SortScratch.Reset();
		for (int32 CandidateIndex = 0; CandidateIndex < Candidates.Num(); ++CandidateIndex)
		{
			if (Candidates[CandidateIndex].SetIndex == SetIndex && Candidates[CandidateIndex].bWants)
			{
				SortScratch.Add(CandidateIndex);
			}
		}
		if (SortScratch.Num() <= Capacity)
		{
			continue;
		}

		auto Score = [this, TentacleSubsystem, SetIndex](const int32 CandidateIndex)
		{
			const FCandidate& Candidate = Candidates[CandidateIndex];
			const bool bOwnsRig = TentacleSubsystem->IsRigOwnedBy(SetIndex, Candidate.RigIndex, Candidate.Entity);
			return Candidate.DistanceSq * (bOwnsRig ? 0.64f : 1.f);
		};
		SortScratch.Sort([&Score](const int32 A, const int32 B) { return Score(A) < Score(B); });
		for (int32 Rank = Capacity; Rank < SortScratch.Num(); ++Rank)
		{
			Candidates[SortScratch[Rank]].bWants = false;
		}
	}

	// Free the rigs of everyone who lost their place before anyone acquires one.
	for (FCandidate& Candidate : Candidates)
	{
		if (!Candidate.bWants && TentacleSubsystem->IsRigOwnedBy(Candidate.SetIndex, Candidate.RigIndex, Candidate.Entity))
		{
			TentacleSubsystem->ReleaseRig(Candidate.SetIndex, Candidate.RigIndex);
			Candidate.RigIndex = INDEX_NONE;
		}
	}

	// Pass 2: same query order, so a running index maps every entity back to its candidate.
	int32 RunningIndex = 0;
	EntityQuery.ForEachEntityChunk(Context, [this, TentacleSubsystem, RepresentationSubsystem, &RunningIndex, DeltaTime, VelocityScale, Time](FMassExecutionContext& Context)
	{
		const FMechSentinelTentacleParams& Params = Context.GetConstSharedFragment<FMechSentinelTentacleParams>();
		FMechSentinelTentacleSet* Set = TentacleSubsystem->GetMutableSet(Params.SetIndex);

		// Head mesh (root sockets) and its offset from the entity transform, shared with the ISM representation.
		const FMassRepresentationParameters_Copy& RepParams = Context.GetConstSharedFragment<FMassRepresentationParameters_Copy>();
		const FStaticMeshInstanceVisualizationDesc_Copy* VisualDesc = RepresentationSubsystem ? RepresentationSubsystem->GetVisualDesc(RepParams.DescIndex) : nullptr;
		const FTransform MeshRelativeTransform = VisualDesc ? VisualDesc->MeshRelativeTransform : FTransform::Identity;
		if (Set)
		{
			UMechSentinelTentacleSubsystem::ResolveLayout(*Set, VisualDesc ? VisualDesc->Mesh.Get() : nullptr);
		}

		const TConstArrayView<FTransformFragment> TransformList = Context.GetFragmentView<FTransformFragment>();
		const TArrayView<FMassRepresentationLODFragment_Copy> LODList = Context.GetMutableFragmentView<FMassRepresentationLODFragment_Copy>();
		const TArrayView<FMechSentinelTentacleFragment> TentacleList = Context.GetMutableFragmentView<FMechSentinelTentacleFragment>();
		const TConstArrayView<FMechSentinelStateFragment> StateList = Context.GetFragmentView<FMechSentinelStateFragment>();
		const TConstArrayView<FMechSentinelAttackFragment> AttackList = Context.GetFragmentView<FMechSentinelAttackFragment>();
		const TConstArrayView<FMassRepresentationCustomDataFragment_Copy> CustomList = Context.GetFragmentView<FMassRepresentationCustomDataFragment_Copy>();

		const int32 NumEntities = Context.GetNumEntities();
		for (int32 EntityIndex = 0; EntityIndex < NumEntities; ++EntityIndex, ++RunningIndex)
		{
			const FCandidate& Candidate = Candidates[RunningIndex];
			FMechSentinelTentacleFragment& Tentacle = TentacleList[EntityIndex];

			int32 Rig = TentacleSubsystem->IsRigOwnedBy(Params.SetIndex, Tentacle.RigIndex, Candidate.Entity) ? Tentacle.RigIndex : INDEX_NONE;
			bool bNewRig = false;
			if (Candidate.bWants && Rig == INDEX_NONE)
			{
				Rig = TentacleSubsystem->AcquireRig(Params.SetIndex, Candidate.Entity);
				bNewRig = Rig != INDEX_NONE;
			}
			Tentacle.RigIndex = Rig;

			// No ribbons: draw the far mesh, which has the tentacles baked in, even at High / Medium LOD.
			LODList[EntityIndex].bForceLowLODMesh = true;
			if (Rig == INDEX_NONE || !Set)
			{
				continue;
			}

			const FRigInputs Inputs = MakeInputs(Set->Desc,
				StateList.Num() > 0 ? &StateList[EntityIndex] : nullptr,
				AttackList.Num() > 0 ? &AttackList[EntityIndex] : nullptr,
				CustomList.Num() > 0 ? &CustomList[EntityIndex] : nullptr);
			const FTransform MeshTransform = MeshRelativeTransform * TransformList[EntityIndex].GetTransform();
			const bool bLaidOut = SimulateRig(*Set, Rig, MeshTransform, bNewRig, Inputs, DeltaTime, VelocityScale, Time);
			// The ribbons show from the frame after the layout; until then the far mesh stays.
			LODList[EntityIndex].bForceLowLODMesh = bLaidOut;
		}
	});

	TentacleSubsystem->EndFrame();
}
