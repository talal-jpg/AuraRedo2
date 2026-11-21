// Mech Sentinel Swarm - project-owned re-implementation of UMassVisualizationComponent (ISM part only).

#include "MechSwarm/MassCopies/MassVisualizationComponent_Copy.h"

#include "Components/InstancedStaticMeshComponent.h"
#include "Engine/CollisionProfile.h"
#include "Engine/StaticMesh.h"
#include "GameFramework/Actor.h"
#include "Materials/MaterialInterface.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(MassVisualizationComponent_Copy)

UMassVisualizationComponent_Copy::UMassVisualizationComponent_Copy()
{
	PrimaryComponentTick.bCanEverTick = false;
	SetIsReplicatedByDefault(false);
}

int32 UMassVisualizationComponent_Copy::GetOrCreateSlot(const int32 DescIndex, const FStaticMeshInstanceVisualizationDesc_Copy& Desc, const bool bLowLOD)
{
	if (DescIndex == INDEX_NONE || !Desc.IsValid())
	{
		return INDEX_NONE;
	}

	// No dedicated low mesh: Low LOD shares the main ISM.
	const bool bUseLowSlot = bLowLOD && Desc.LowLODMesh != nullptr;
	const int32 Key = DescIndex * 2 + (bUseLowSlot ? 1 : 0);
	if (const int32* Existing = DescLODToSlot.Find(Key))
	{
		return *Existing;
	}

	UInstancedStaticMeshComponent* ISM = CreateISM(Desc, bUseLowSlot);
	if (!ISM)
	{
		return INDEX_NONE;
	}

	FSlot& NewSlot = Slots.AddDefaulted_GetRef();
	NewSlot.ISM = ISM;
	NewSlot.NumCustomFloats = FMath::Clamp(Desc.NumCustomDataFloats, 0, MechSwarm::Representation::MaxCustomDataFloats);

	const int32 SlotIndex = Slots.Num() - 1;
	DescLODToSlot.Add(Key, SlotIndex);
	return SlotIndex;
}

UInstancedStaticMeshComponent* UMassVisualizationComponent_Copy::CreateISM(const FStaticMeshInstanceVisualizationDesc_Copy& Desc, const bool bLowLOD)
{
	AActor* Owner = GetOwner();
	if (!Owner)
	{
		return nullptr;
	}

	UInstancedStaticMeshComponent* ISM = NewObject<UInstancedStaticMeshComponent>(Owner, NAME_None, RF_Transient);
	ISM->SetStaticMesh(bLowLOD ? Desc.LowLODMesh.Get() : Desc.Mesh.Get());
	for (int32 MaterialIndex = 0; MaterialIndex < Desc.MaterialOverrides.Num(); ++MaterialIndex)
	{
		if (UMaterialInterface* Material = Desc.MaterialOverrides[MaterialIndex])
		{
			ISM->SetMaterial(MaterialIndex, Material);
		}
	}

	// Instances move every frame: movable, no collision (hits are resolved by the capsule queries), no navigation.
	ISM->SetMobility(EComponentMobility::Movable);
	ISM->SetCollisionProfileName(UCollisionProfile::NoCollision_ProfileName);
	ISM->SetCanEverAffectNavigation(false);
	ISM->SetCastShadow(Desc.bCastShadows);
	ISM->SetNumCustomDataFloats(FMath::Clamp(Desc.NumCustomDataFloats, 0, MechSwarm::Representation::MaxCustomDataFloats));
	ISM->SetupAttachment(Owner->GetRootComponent());
	ISM->RegisterComponent();
	Owner->AddInstanceComponent(ISM);

	OwnedISMs.Add(ISM);
	return ISM;
}

void UMassVisualizationComponent_Copy::BeginVisualFrame()
{
	++FrameCounter;
	for (FSlot& Slot : Slots)
	{
		Slot.FrameEntities.Reset();
		Slot.FrameTransforms.Reset();
		Slot.FrameCustomData.Reset();
	}
}

void UMassVisualizationComponent_Copy::AddFrameInstance(const int32 SlotIndex, const FMassEntityHandle Entity, const FTransform& WorldTransform, TConstArrayView<float> CustomData)
{
	if (!Slots.IsValidIndex(SlotIndex))
	{
		return;
	}

	FSlot& Slot = Slots[SlotIndex];
	Slot.FrameEntities.Add(Entity);
	Slot.FrameTransforms.Add(WorldTransform);
	for (int32 FloatIndex = 0; FloatIndex < Slot.NumCustomFloats; ++FloatIndex)
	{
		Slot.FrameCustomData.Add(CustomData.IsValidIndex(FloatIndex) ? CustomData[FloatIndex] : 0.f);
	}
}

void UMassVisualizationComponent_Copy::EndVisualFrame()
{
	for (FSlot& Slot : Slots)
	{
		FlushSlot(Slot);
	}
}

void UMassVisualizationComponent_Copy::FlushSlot(FSlot& Slot)
{
	UInstancedStaticMeshComponent* ISM = Slot.ISM;
	if (!IsValid(ISM))
	{
		Slot.EntityToInstance.Reset();
		return;
	}

	const int32 NumFloats = Slot.NumCustomFloats;
	for (int32 Index = 0; Index < Slot.FrameEntities.Num(); ++Index)
	{
		const FTransform& Transform = Slot.FrameTransforms[Index];
		const TConstArrayView<float> Custom = NumFloats > 0
			? MakeArrayView(Slot.FrameCustomData.GetData() + Index * NumFloats, NumFloats)
			: TConstArrayView<float>();

		if (FInstanceEntry* Entry = Slot.EntityToInstance.Find(Slot.FrameEntities[Index]))
		{
			// The visualizer actor sits at the origin with identity transform, so local == world space.
			ISM->UpdateInstanceTransformById(Entry->InstanceId, Transform);
			if (NumFloats > 0)
			{
				ISM->SetCustomDataById(Entry->InstanceId, Custom);
			}
			Entry->LastFrame = FrameCounter;
		}
		else
		{
			FInstanceEntry NewEntry;
			NewEntry.InstanceId = ISM->AddInstanceById(Transform);
			NewEntry.LastFrame = FrameCounter;
			if (NumFloats > 0)
			{
				ISM->SetCustomDataById(NewEntry.InstanceId, Custom);
			}
			Slot.EntityToInstance.Add(Slot.FrameEntities[Index], NewEntry);
		}
	}

	// Anything not submitted this frame was destroyed, culled (LOD Off) or moved to another LOD slot.
	TArray<FPrimitiveInstanceId> ToRemove;
	for (auto It = Slot.EntityToInstance.CreateIterator(); It; ++It)
	{
		if (It.Value().LastFrame != FrameCounter)
		{
			ToRemove.Add(It.Value().InstanceId);
			It.RemoveCurrent();
		}
	}
	if (ToRemove.Num() > 0)
	{
		ISM->RemoveInstancesById(ToRemove);
	}
}

int32 UMassVisualizationComponent_Copy::GetNumDrawnInstances() const
{
	int32 Total = 0;
	for (const FSlot& Slot : Slots)
	{
		Total += Slot.EntityToInstance.Num();
	}
	return Total;
}

void UMassVisualizationComponent_Copy::OnUnregister()
{
	Slots.Reset();
	DescLODToSlot.Reset();
	Super::OnUnregister();
}
