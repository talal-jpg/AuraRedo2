// Mech Sentinel Swarm - Niagara ribbon tentacles: rig pool and Niagara output.

#pragma once

#include "CoreMinimal.h"
#include "Containers/BitArray.h"
#include "Mass/EntityHandle.h"
#include "Subsystems/WorldSubsystem.h"
#include "MechSwarm/Tentacles/MechSentinelTentacleTypes.h"
#include "MechSentinelTentacleSubsystem.generated.h"

class UNiagaraComponent;
class UStaticMesh;

/**
 * One tentacle set: a fixed pool of rigs (one rig = the chains of one sentinel) drawn by one Niagara component.
 * Arrays are laid out [rig][tentacle][point] so a ribbon is a contiguous run of PointsPerTentacle points.
 */
USTRUCT()
struct AURA_API FMechSentinelTentacleSet
{
	GENERATED_BODY()

	UPROPERTY()
	FMechSentinelTentacleDesc Desc;

	/** Created on the first frame that has a rig. World space, at the origin, ticks after Mass (ForceTickLast). */
	UPROPERTY(Transient)
	TObjectPtr<UNiagaraComponent> Component = nullptr;

	/** Mesh the root layout was read from (null = built-in ring matching the Blender source art). */
	TWeakObjectPtr<const UStaticMesh> LayoutMesh;
	bool bLayoutResolved = false;

	/** Per tentacle, in head mesh space: root location (cm), rest direction, outward radial direction. */
	TArray<FVector> RootOffsets;
	TArray<FVector> RootDirections;
	TArray<FVector> RootRadials;

	/** Chain points (world) and their previous positions (verlet). */
	TArray<FVector> Positions;
	TArray<FVector> PrevPositions;

	/** Per ribbon: width multiplier (0 = hidden) and glow. */
	TArray<float> WidthScales;
	TArray<float> Glow;

	/** Per rig: owner (invalid = free), sway phase, touched this frame. */
	TArray<FMassEntityHandle> RigOwners;
	TArray<float> RigPhases;
	TBitArray<> RigSeen;
	TArray<int32> FreeRigs;
	int32 NumActiveRigs = 0;

	/** World bounds of every active point this frame (fixed bounds of the Niagara component). */
	FBox FrameBounds = FBox(ForceInit);

	int32 RibbonIndex(const int32 Rig, const int32 Tentacle) const { return Rig * Desc.NumTentacles + Tentacle; }
	int32 PointIndex(const int32 Rig, const int32 Tentacle, const int32 Point) const { return RibbonIndex(Rig, Tentacle) * Desc.PointsPerTentacle + Point; }
};

/**
 * Owns the tentacle sets. UMechSentinelTentacleTrait registers a set per distinct description while templates are
 * built, UMechSentinelTentacleProcessor acquires / releases rigs and writes the chains, EndFrame() pushes them to Niagara.
 * Only exists in game worlds; nothing is registered on dedicated servers.
 */
UCLASS()
class AURA_API UMechSentinelTentacleSubsystem : public UWorldSubsystem
{
	GENERATED_BODY()

public:
	/** Returns a stable set index for Desc, adding the set when unseen. */
	int32 FindOrAddSet(const FMechSentinelTentacleDesc& Desc);

	FMechSentinelTentacleSet* GetMutableSet(int32 SetIndex) { return Sets.IsValidIndex(SetIndex) ? &Sets[SetIndex] : nullptr; }
	int32 GetNumSets() const { return Sets.Num(); }

	/** Takes a free rig for Entity. INDEX_NONE when the pool is full. */
	int32 AcquireRig(int32 SetIndex, FMassEntityHandle Entity);
	void ReleaseRig(int32 SetIndex, int32 RigIndex);
	bool IsRigOwnedBy(int32 SetIndex, int32 RigIndex, FMassEntityHandle Entity) const;

	/** Reads the root sockets Tentacle_XX of Mesh (or the built-in ring) when the mesh changed. */
	static void ResolveLayout(FMechSentinelTentacleSet& Set, const UStaticMesh* Mesh);

	/** Frame bracket used by the processor: rigs nobody touched between the two (destroyed entities) are freed. */
	void BeginFrame();
	void EndFrame();

protected:
	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;
	virtual void Deinitialize() override;

	void EnsureComponent(FMechSentinelTentacleSet& Set);
	static void PushToNiagara(FMechSentinelTentacleSet& Set);

	UPROPERTY(Transient)
	TArray<FMechSentinelTentacleSet> Sets;
};
