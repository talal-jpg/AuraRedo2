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
#include "MechSwarm/Tentacles/MechSentinelTentacleSubsystem.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(MechSentinelTentacleProcessor)

namespace MechSwarm::Tentacles
{
	/** Per-sentinel modifiers derived from its state. */
	struct FRigInputs
	{
		float StiffnessScale = 1.f;
		float GravityScale = 1.f;
		float SwayScale = 1.f;
		float SwaySpeedScale = 1.f;
		float Glow = 0.f;
	};

	FRigInputs MakeInputs(const FMechSentinelTentacleDesc& Desc, const FMechSentinelStateFragment* State, const FMechSentinelAttackFragment* Attack)
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
		Inputs.Glow = FMath::Clamp(Inputs.Glow, 0.f, 1.f);
		return Inputs;
	}

	/** Head-relative trailing pose: leaves the socket along its rest direction and bends back / down along the chain. */
	FORCEINLINE FVector RestDirectionAt(const FVector& RootDirection, const FVector& TrailDirection, const float T)
	{
		const float Blend = FMath::SmoothStep(0.f, 1.f, FMath::Min(1.f, T * 2.2f));
		return FMath::Lerp(RootDirection, TrailDirection, Blend).GetSafeNormal();
	}

	void SimulateRig(FMechSentinelTentacleSet& Set, const int32 Rig, const FTransform& MeshTransform, const bool bReset,
		const FRigInputs& Inputs, const float DeltaTime, const float Time)
	{
		const FMechSentinelTentacleDesc& Desc = Set.Desc;
		const int32 NumPoints = Desc.PointsPerTentacle;
		const float Segment = Desc.SegmentLength;
		const float InvLastPoint = 1.f / float(NumPoints - 1);

		const FQuat Rotation = MeshTransform.GetRotation();
		const FVector Forward = Rotation.GetAxisX();
		const FVector Up = Rotation.GetAxisZ();
		const FVector GravityStep = FVector(0.f, 0.f, -Desc.Gravity * Inputs.GravityScale) * FMath::Square(DeltaTime);
		const float Retain = FMath::Pow(1.f - FMath::Clamp(Desc.Damping, 0.f, 1.f), DeltaTime * 60.f);
		const float SwayAngle = UE_TWO_PI * Desc.SwayFrequency * Inputs.SwaySpeedScale * Time;
		const float TeleportSq = FMath::Square(Desc.TeleportDistance);

		Set.RigSeen[Rig] = true;

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
			Set.WidthScales[Ribbon] = 1.f;
			Set.Glow[Ribbon] = Inputs.Glow;

			const bool bLayOut = bReset || FVector::DistSquared(Set.Positions[Base], Root) > TeleportSq;

			FVector RestPoint = Root;
			Set.Positions[Base] = Root;
			Set.PrevPositions[Base] = Root;
			Set.FrameBounds += Root;

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

				// Verlet step: inertia (with drag) + gravity.
				const FVector Velocity = (Position - PrevPosition) * Retain;
				PrevPosition = Position;
				Position += Velocity + GravityStep;

				// Pull toward the trailing pose, softer toward the tip so the ends lag and whip.
				const float Stiffness = Desc.Stiffness * Inputs.StiffnessScale * FMath::Lerp(1.f, Desc.TipStiffnessScale, T);
				Position += (Target - Position) * (1.f - FMath::Exp(-Stiffness * DeltaTime));

				// Length constraint against the (already solved) previous point: the chain never stretches.
				const FVector& Parent = Set.Positions[Base + Point - 1];
				const FVector Delta = Position - Parent;
				const double Length = Delta.Size();
				Position = Parent + (Length > UE_KINDA_SMALL_NUMBER ? Delta / Length : RestDirection) * Segment;

				Set.FrameBounds += Position;
			}
		}
	}
}

UMechSentinelTentacleProcessor::UMechSentinelTentacleProcessor()
	: EntityQuery(*this)
{
	ExecutionFlags = (int32)(EProcessorExecutionFlags::Standalone | EProcessorExecutionFlags::Client);
	ProcessingPhase = EMassProcessingPhase::PostPhysics;
	ExecutionOrder.ExecuteInGroup = MechSwarm::ProcessorGroups::Representation();
	ExecutionOrder.ExecuteAfter.Add(UMassVisualizationLODProcessor_Copy::StaticClass()->GetFName());
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
	EntityQuery.AddConstSharedRequirement<FMechSentinelTentacleParams>(EMassFragmentPresence::All);
	EntityQuery.AddConstSharedRequirement<FMassRepresentationParameters_Copy>(EMassFragmentPresence::All);
}

void UMechSentinelTentacleProcessor::Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context)
{
	using namespace MechSwarm::Tentacles;

	UWorld* World = EntityManager.GetWorld();
	UMechSentinelTentacleSubsystem* TentacleSubsystem = World ? World->GetSubsystem<UMechSentinelTentacleSubsystem>() : nullptr;
	const UMassRepresentationSubsystem_Copy* RepresentationSubsystem = World ? World->GetSubsystem<UMassRepresentationSubsystem_Copy>() : nullptr;
	if (!TentacleSubsystem || TentacleSubsystem->GetNumSets() == 0)
	{
		return;
	}

	// Large hitches would explode the verlet step; the chains just lag a little instead.
	const float DeltaTime = FMath::Clamp(Context.GetDeltaTimeSeconds(), 1.e-4f, 1.f / 15.f);
	const float Time = float(World->GetTimeSeconds());

	TentacleSubsystem->BeginFrame();
	Candidates.Reset();

	// Pass 1: who wants ribbons this frame.
	EntityQuery.ForEachEntityChunk(Context, [this, TentacleSubsystem](FMassExecutionContext& Context)
	{
		const FMechSentinelTentacleParams& Params = Context.GetConstSharedFragment<FMechSentinelTentacleParams>();
		const FMechSentinelTentacleSet* Set = TentacleSubsystem->GetMutableSet(Params.SetIndex);
		const float MaxDistanceSq = Set ? FMath::Square(Set->Desc.MaxDistance) : 0.f;

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
			Candidate.bWants = Set != nullptr && LOD <= EMassLOD::Medium && DistanceSq < MaxDistanceSq;
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
	EntityQuery.ForEachEntityChunk(Context, [this, TentacleSubsystem, RepresentationSubsystem, &RunningIndex, DeltaTime, Time](FMassExecutionContext& Context)
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
			LODList[EntityIndex].bForceLowLODMesh = (Rig == INDEX_NONE);
			if (Rig == INDEX_NONE || !Set)
			{
				continue;
			}

			const FRigInputs Inputs = MakeInputs(Set->Desc,
				StateList.Num() > 0 ? &StateList[EntityIndex] : nullptr,
				AttackList.Num() > 0 ? &AttackList[EntityIndex] : nullptr);
			const FTransform MeshTransform = MeshRelativeTransform * TransformList[EntityIndex].GetTransform();
			SimulateRig(*Set, Rig, MeshTransform, bNewRig, Inputs, DeltaTime, Time);
		}
	});

	TentacleSubsystem->EndFrame();
}
