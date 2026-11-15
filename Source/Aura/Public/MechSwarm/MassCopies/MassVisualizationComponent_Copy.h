// Mech Sentinel Swarm - project-owned re-implementation of UMassVisualizationComponent (ISM part only).
// Mirrors (by role): UMassVisualizationComponent from MassGameplay/MassRepresentation.

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "InstanceDataTypes.h"
#include "Mass/EntityHandle.h"
#include "MechSwarm/MassCopies/MassRepresentationFragments_Copy.h"
#include "MassVisualizationComponent_Copy.generated.h"

class UInstancedStaticMeshComponent;

/**
 * Owns one UInstancedStaticMeshComponent per (visual description, LOD mesh) and keeps an
 * entity -> instance id map, so instances are stable while entities live and disappear
 * automatically once an entity is destroyed or culled (it simply stops being submitted).
 *
 * Per frame: BeginVisualFrame() -> AddFrameInstance() for every drawn entity -> EndVisualFrame().
 */
UCLASS(ClassGroup = (MechSwarm))
class AURA_API UMassVisualizationComponent_Copy : public UActorComponent
{
	GENERATED_BODY()

public:
	UMassVisualizationComponent_Copy();

	/** Returns the ISM slot that draws Desc at the given LOD (creates ISM components on demand). INDEX_NONE if Desc is invalid. */
	int32 GetOrCreateSlot(int32 DescIndex, const FStaticMeshInstanceVisualizationDesc_Copy& Desc, bool bLowLOD);

	void BeginVisualFrame();
	void AddFrameInstance(int32 SlotIndex, FMassEntityHandle Entity, const FTransform& WorldTransform, TConstArrayView<float> CustomData);
	void EndVisualFrame();

	/** Number of instances currently drawn across all slots (debug / stats). */
	int32 GetNumDrawnInstances() const;

protected:
	virtual void OnUnregister() override;

private:
	struct FInstanceEntry
	{
		FPrimitiveInstanceId InstanceId;
		uint32 LastFrame = 0;
	};

	struct FSlot
	{
		TObjectPtr<UInstancedStaticMeshComponent> ISM = nullptr;
		int32 NumCustomFloats = 0;
		TMap<FMassEntityHandle, FInstanceEntry> EntityToInstance;

		// Per-frame submission buffers.
		TArray<FMassEntityHandle> FrameEntities;
		TArray<FTransform> FrameTransforms;
		TArray<float> FrameCustomData;
	};

	UInstancedStaticMeshComponent* CreateISM(const FStaticMeshInstanceVisualizationDesc_Copy& Desc, bool bLowLOD);
	void FlushSlot(FSlot& Slot);

	/** Keeps the ISM components alive for GC. */
	UPROPERTY(Transient)
	TArray<TObjectPtr<UInstancedStaticMeshComponent>> OwnedISMs;

	TArray<FSlot> Slots;

	/** Key: DescIndex * 2 + (bLowLOD ? 1 : 0). */
	TMap<int32, int32> DescLODToSlot;

	uint32 FrameCounter = 0;
};
