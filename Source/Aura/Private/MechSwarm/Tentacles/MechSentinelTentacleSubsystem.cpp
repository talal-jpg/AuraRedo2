// Mech Sentinel Swarm - Niagara ribbon tentacles: rig pool and Niagara output.

#include "MechSwarm/Tentacles/MechSentinelTentacleSubsystem.h"

#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshSocket.h"
#include "Engine/World.h"
#include "NiagaraComponent.h"
#include "NiagaraDataInterfaceArrayFunctionLibrary.h"
#include "NiagaraFunctionLibrary.h"
#include "NiagaraSystem.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(MechSentinelTentacleSubsystem)

DEFINE_LOG_CATEGORY_STATIC(LogMechSentinelTentacles, Log, All);

namespace MechSwarm::Tentacles
{
	// Built-in root ring, identical to SourceArt/MechSentinel/mech_sentinel_head.py (Blender -Y is Unreal +Y).
	constexpr float RingX = -100.f;
	constexpr float RingRadiusY = 31.f;
	constexpr float RingRadiusZ = 27.f;
	constexpr float RingCenterZ = -5.f;
	constexpr float RestDroop = 0.08f;

	/** How far the optional claw mesh (SM_MechSentinel_TentacleTip, 13 cm + prongs) reaches past the last point. */
	constexpr float TipMeshReach = 15.f;
}

int32 UMechSentinelTentacleSubsystem::FindOrAddSet(const FMechSentinelTentacleDesc& Desc)
{
	const int32 Existing = Sets.IndexOfByPredicate([&Desc](const FMechSentinelTentacleSet& Set) { return Set.Desc == Desc; });
	if (Existing != INDEX_NONE)
	{
		return Existing;
	}

	FMechSentinelTentacleSet& Set = Sets.AddDefaulted_GetRef();
	Set.Desc = Desc;
	Set.Desc.NumTentacles = FMath::Clamp(Desc.NumTentacles, 1, 16);
	Set.Desc.PointsPerTentacle = FMath::Clamp(Desc.PointsPerTentacle, 3, 32);
	Set.Desc.MaxRiggedSentinels = FMath::Clamp(Desc.MaxRiggedSentinels, 1, 1024);

	const int32 NumRigs = Set.Desc.MaxRiggedSentinels;
	const int32 NumRibbons = Set.Desc.GetNumRibbons();
	Set.Positions.Init(FVector::ZeroVector, NumRibbons * Set.Desc.PointsPerTentacle);
	Set.PrevPositions.Init(FVector::ZeroVector, NumRibbons * Set.Desc.PointsPerTentacle);
	Set.WidthScales.Init(0.f, NumRibbons);
	Set.Glow.Init(0.f, NumRibbons);
	Set.RigOwners.Init(FMassEntityHandle(), NumRigs);
	Set.RigPhases.Init(0.f, NumRigs);
	Set.RigSeen.Init(false, NumRigs);
	Set.FreeRigs.Reserve(NumRigs);
	for (int32 Rig = NumRigs - 1; Rig >= 0; --Rig)
	{
		Set.FreeRigs.Add(Rig);
	}
	ResolveLayout(Set, nullptr);

	return Sets.Num() - 1;
}

int32 UMechSentinelTentacleSubsystem::AcquireRig(const int32 SetIndex, const FMassEntityHandle Entity)
{
	FMechSentinelTentacleSet* Set = GetMutableSet(SetIndex);
	if (!Set || Set->FreeRigs.IsEmpty())
	{
		return INDEX_NONE;
	}

	const int32 Rig = Set->FreeRigs.Pop(EAllowShrinking::No);
	Set->RigOwners[Rig] = Entity;
	// Golden-angle spread so neighbours never sway in sync.
	Set->RigPhases[Rig] = FMath::Fmod(float(Entity.Index) * 2.39996f, UE_TWO_PI);
	Set->RigSeen[Rig] = true;
	++Set->NumActiveRigs;
	return Rig;
}

void UMechSentinelTentacleSubsystem::ReleaseRig(const int32 SetIndex, const int32 RigIndex)
{
	FMechSentinelTentacleSet* Set = GetMutableSet(SetIndex);
	if (!Set || !Set->RigOwners.IsValidIndex(RigIndex) || !Set->RigOwners[RigIndex].IsValid())
	{
		return;
	}

	Set->RigOwners[RigIndex] = FMassEntityHandle();
	Set->FreeRigs.Add(RigIndex);
	--Set->NumActiveRigs;
	for (int32 Tentacle = 0; Tentacle < Set->Desc.NumTentacles; ++Tentacle)
	{
		const int32 Ribbon = Set->RibbonIndex(RigIndex, Tentacle);
		Set->WidthScales[Ribbon] = 0.f;
		Set->Glow[Ribbon] = 0.f;
	}
}

bool UMechSentinelTentacleSubsystem::IsRigOwnedBy(const int32 SetIndex, const int32 RigIndex, const FMassEntityHandle Entity) const
{
	return Sets.IsValidIndex(SetIndex)
		&& Sets[SetIndex].RigOwners.IsValidIndex(RigIndex)
		&& Sets[SetIndex].RigOwners[RigIndex] == Entity;
}

void UMechSentinelTentacleSubsystem::ResolveLayout(FMechSentinelTentacleSet& Set, const UStaticMesh* Mesh)
{
	using namespace MechSwarm::Tentacles;

	if (Set.bLayoutResolved && Set.LayoutMesh.Get() == Mesh)
	{
		return;
	}
	Set.bLayoutResolved = true;
	Set.LayoutMesh = Mesh;

	const int32 NumTentacles = Set.Desc.NumTentacles;
	Set.RootOffsets.SetNum(NumTentacles);
	Set.RootDirections.SetNum(NumTentacles);
	Set.RootRadials.SetNum(NumTentacles);

	const float Fan = FMath::DegreesToRadians(Set.Desc.FanAngle);
	for (int32 Tentacle = 0; Tentacle < NumTentacles; ++Tentacle)
	{
		// No root exactly at the top or bottom (22.5 deg + 45 deg steps for 8 tentacles).
		const float Angle = UE_TWO_PI * (float(Tentacle) + 0.5f) / float(NumTentacles);
		FVector Root(RingX, -RingRadiusY * FMath::Cos(Angle), RingCenterZ + RingRadiusZ * FMath::Sin(Angle));

		if (Mesh)
		{
			if (const UStaticMeshSocket* Socket = Mesh->FindSocket(FName(*FString::Printf(TEXT("Tentacle_%02d"), Tentacle))))
			{
				Root = Socket->RelativeLocation;
			}
		}

		// The rest direction is derived from the root position (not from the socket rotation), so it does not depend
		// on how the FBX importer converted the socket axes.
		FVector Radial(0.f, Root.Y, Root.Z - RingCenterZ);
		Radial = Radial.GetSafeNormal(UE_SMALL_NUMBER, FVector(0.f, 0.f, -1.f));
		Set.RootOffsets[Tentacle] = Root;
		Set.RootRadials[Tentacle] = Radial;
		Set.RootDirections[Tentacle] = FVector(-FMath::Cos(Fan), FMath::Sin(Fan) * Radial.Y, FMath::Sin(Fan) * Radial.Z - RestDroop).GetSafeNormal();
	}
}

void UMechSentinelTentacleSubsystem::BeginFrame()
{
	for (FMechSentinelTentacleSet& Set : Sets)
	{
		Set.RigSeen.SetRange(0, Set.RigSeen.Num(), false);
		Set.FrameBounds = FBox(ForceInit);
	}
}

void UMechSentinelTentacleSubsystem::EndFrame()
{
	for (int32 SetIndex = 0; SetIndex < Sets.Num(); ++SetIndex)
	{
		FMechSentinelTentacleSet& Set = Sets[SetIndex];

		// Rigs whose owner was not processed this frame: the entity was destroyed or lost its tentacle fragment.
		for (int32 Rig = 0; Rig < Set.RigOwners.Num(); ++Rig)
		{
			if (Set.RigOwners[Rig].IsValid() && !Set.RigSeen[Rig])
			{
				ReleaseRig(SetIndex, Rig);
			}
		}

		// Created as soon as the set is in use, not with the first rig: the ribbon PSOs precache while the swarm is
		// still far away, instead of the first close sentinel showing a bare head until they are compiled.
		EnsureComponent(Set);

		UNiagaraComponent* Component = Set.Component;
		if (!IsValid(Component))
		{
			continue;
		}

		const bool bActive = Set.NumActiveRigs > 0;
		if (Component->IsVisible() != bActive)
		{
			Component->SetVisibility(bActive);
			Component->SetPaused(!bActive);
		}
		if (bActive)
		{
			PushToNiagara(Set);
		}
	}
}

void UMechSentinelTentacleSubsystem::PushToNiagara(FMechSentinelTentacleSet& Set)
{
	using namespace MechSwarm::Tentacles;

	UNiagaraComponent* Component = Set.Component;
	UNiagaraDataInterfaceArrayFunctionLibrary::SetNiagaraArrayPosition(Component, NiagaraParams::Positions(), Set.Positions);
	UNiagaraDataInterfaceArrayFunctionLibrary::SetNiagaraArrayFloat(Component, NiagaraParams::WidthScales(), Set.WidthScales);
	UNiagaraDataInterfaceArrayFunctionLibrary::SetNiagaraArrayFloat(Component, NiagaraParams::Glow(), Set.Glow);

	// The component sits at the world origin with an identity transform, so world bounds are its local bounds.
	// Padding: the tube radius around the points plus the claw mesh past the tips.
	if (Set.FrameBounds.IsValid)
	{
		Component->SetSystemFixedBounds(Set.FrameBounds.ExpandBy(FMath::Max(Set.Desc.RootWidth, 10.f) + TipMeshReach));
	}
}

void UMechSentinelTentacleSubsystem::EnsureComponent(FMechSentinelTentacleSet& Set)
{
	using namespace MechSwarm::Tentacles;

	if (IsValid(Set.Component) || !Set.Desc.NiagaraSystem)
	{
		return;
	}

	UWorld* World = GetWorld();
	if (!World || World->GetNetMode() == NM_DedicatedServer)
	{
		return;
	}

	UNiagaraComponent* Component = UNiagaraFunctionLibrary::SpawnSystemAtLocation(World, Set.Desc.NiagaraSystem,
		FVector::ZeroVector, FRotator::ZeroRotator, FVector::OneVector,
		/*bAutoDestroy*/ false, /*bAutoActivate*/ false, ENCPoolMethod::None, /*bPreCullCheck*/ false);
	if (!Component)
	{
		UE_LOG(LogMechSentinelTentacles, Warning, TEXT("Could not spawn tentacle system %s."), *GetNameSafe(Set.Desc.NiagaraSystem));
		return;
	}

	// Mass writes the chains in PostPhysics; the ribbons must be built from this frame's data.
	Component->SetTickBehavior(ENiagaraTickBehavior::ForceTickLast);
	// A spawned Niagara component does not cast shadows by default; the heads do.
	Component->SetCastShadow(Set.Desc.bCastShadows);
	Component->SetVariableInt(NiagaraParams::PointsPerTentacle(), Set.Desc.PointsPerTentacle);
	Component->SetVariableInt(NiagaraParams::TentacleCount(), Set.Desc.GetNumRibbons());
	Component->SetVariableFloat(NiagaraParams::RootWidth(), Set.Desc.RootWidth);
	Component->SetVariableFloat(NiagaraParams::TipWidth(), Set.Desc.TipWidth);
	Set.Component = Component;
	PushToNiagara(Set);
	Component->Activate(true);
}

bool UMechSentinelTentacleSubsystem::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

void UMechSentinelTentacleSubsystem::Deinitialize()
{
	for (FMechSentinelTentacleSet& Set : Sets)
	{
		if (IsValid(Set.Component))
		{
			Set.Component->DestroyComponent();
		}
		Set.Component = nullptr;
	}
	Sets.Reset();
	Super::Deinitialize();
}
