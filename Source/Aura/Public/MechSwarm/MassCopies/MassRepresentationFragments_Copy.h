// Mech Sentinel Swarm - project-owned re-implementation of the MassRepresentation data types.
// Mirrors (by role): FStaticMeshInstanceVisualizationDesc, FMassRepresentationLODFragment,
// FMassVisualizationLODParameters, FMassRepresentationParameters from MassGameplay/MassRepresentation.
// Deviation: ISM-only (no actor or skinned-mesh representation), which is all a swarm of sentinels needs.

#pragma once

#include "CoreMinimal.h"
#include "MassEntityTypes.h"
#include "MassLODTypes.h"
#include "MassRepresentationFragments_Copy.generated.h"

class UStaticMesh;
class UMaterialInterface;

namespace MechSwarm::Representation
{
	/** Per-instance custom data floats an entity can carry (FMassRepresentationCustomDataFragment_Copy::Values). */
	constexpr int32 MaxCustomDataFloats = 7;
}

/** How one kind of entity is drawn with instanced static meshes. */
USTRUCT(BlueprintType)
struct AURA_API FStaticMeshInstanceVisualizationDesc_Copy
{
	GENERATED_BODY()

	/** Mesh used for High and Medium LOD. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Visualization")
	TObjectPtr<UStaticMesh> Mesh = nullptr;

	/** Optional cheaper mesh for Low LOD (falls back to Mesh). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Visualization")
	TObjectPtr<UStaticMesh> LowLODMesh = nullptr;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Visualization")
	TArray<TObjectPtr<UMaterialInterface>> MaterialOverrides;

	/** Offset applied to the entity transform, e.g. to align the mesh nose with +X or scale it. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Visualization")
	FTransform MeshRelativeTransform = FTransform::Identity;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Visualization")
	bool bCastShadows = true;

	/**
	 * Per-instance custom data floats sent to the material (PerInstanceCustomData).
	 * Sentinels write: [0] state (0 seek, 1 attack, 2 stunned, 3 dead), [1] health 0..1, [2] hit flash 0..1, [3] attack glow 0..1,
	 * [4] armor / [5] speed / [6] damage self-buff 0..1 (fades). Fewer floats just cut the list (materials read the
	 * PerInstanceCustomData default for missing ones).
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Visualization", meta = (ClampMin = "0", ClampMax = "7"))
	int32 NumCustomDataFloats = 7;

	bool IsValid() const { return Mesh != nullptr; }

	bool operator==(const FStaticMeshInstanceVisualizationDesc_Copy& Other) const
	{
		return Mesh == Other.Mesh
			&& LowLODMesh == Other.LowLODMesh
			&& MaterialOverrides == Other.MaterialOverrides
			&& MeshRelativeTransform.Equals(Other.MeshRelativeTransform)
			&& bCastShadows == Other.bCastShadows
			&& NumCustomDataFloats == Other.NumCustomDataFloats;
	}
};

/** Visual LOD of an entity (High/Medium/Low drawn, Off culled). */
USTRUCT()
struct AURA_API FMassRepresentationLODFragment_Copy : public FMassFragment
{
	GENERATED_BODY()

	TEnumAsByte<EMassLOD::Type> LOD = EMassLOD::Max;
	TEnumAsByte<EMassLOD::Type> PrevLOD = EMassLOD::Max;

	/**
	 * Project addition: draw the LowLODMesh even at High / Medium LOD. Set by UMechSentinelTentacleProcessor for
	 * sentinels without Niagara ribbons, because the low mesh has the tentacles baked in.
	 */
	bool bForceLowLODMesh = false;
};

/** Distances driving FMassRepresentationLODFragment_Copy. */
USTRUCT()
struct AURA_API FMassVisualizationLODParameters_Copy : public FMassConstSharedFragment
{
	GENERATED_BODY()

	/** Closer than this: High. */
	UPROPERTY(EditAnywhere, Category = "LOD", meta = (ForceUnits = "cm"))
	float HighDistance = 4000.f;

	/** Closer than this: Medium. */
	UPROPERTY(EditAnywhere, Category = "LOD", meta = (ForceUnits = "cm"))
	float MediumDistance = 9000.f;

	/** Closer than this: Low (uses LowLODMesh). Farther: Off (not drawn). */
	UPROPERTY(EditAnywhere, Category = "LOD", meta = (ForceUnits = "cm"))
	float LowDistance = 25000.f;

	/** Entities behind every camera are evaluated as if they were this much farther. */
	UPROPERTY(EditAnywhere, Category = "LOD", meta = (ClampMin = "1"))
	float BehindViewerDistanceScale = 1.5f;

	/** Fraction of a band an entity must travel past a boundary before its LOD flips (prevents popping). */
	UPROPERTY(EditAnywhere, Category = "LOD", meta = (ClampMin = "0", ClampMax = "0.5"))
	float Hysteresis = 0.1f;
};

/** Which registered visual description draws this entity. Built by UMassVisualizationTrait_Copy. */
USTRUCT()
struct AURA_API FMassRepresentationParameters_Copy : public FMassConstSharedFragment
{
	GENERATED_BODY()

	/** Index into UMassRepresentationSubsystem_Copy's description table. */
	UPROPERTY()
	int32 DescIndex = INDEX_NONE;
};

/** Per-entity floats forwarded to the ISM per-instance custom data. Gameplay writes, the ISM processor reads. */
USTRUCT()
struct AURA_API FMassRepresentationCustomDataFragment_Copy : public FMassFragment
{
	GENERATED_BODY()

	float Values[MechSwarm::Representation::MaxCustomDataFloats] = { 0.f, 1.f, 0.f, 0.f, 0.f, 0.f, 0.f };
};

/** Marks entities that are drawn by the ISM representation copy. */
USTRUCT()
struct AURA_API FMassVisualizationTag_Copy : public FMassTag
{
	GENERATED_BODY()
};
