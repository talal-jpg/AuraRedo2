// Mech Sentinel Swarm - Niagara ribbon tentacles: shared data types.
//
// Every near sentinel gets NumTentacles verlet chains (PointsPerTentacle points, SegmentLength apart) that hang from
// the sockets of the head mesh and trail behind it. The chains are simulated by UMechSentinelTentacleProcessor and
// pushed every frame into one Niagara system per tentacle set, which draws one ribbon per chain.
// See MyMechEntitySystemReadme.md, section "Tentacles".

#pragma once

#include "CoreMinimal.h"
#include "MassEntityTypes.h"
#include "MechSentinelTentacleTypes.generated.h"

class UNiagaraSystem;

/** Names of the Niagara user parameters the tentacle system must expose (see the README recipe). */
namespace MechSwarm::Tentacles::NiagaraParams
{
	/** Niagara Position Array: every chain point, [rig][tentacle][point], world space. */
	inline FName Positions() { return FName(TEXT("TentaclePositions")); }
	/** Niagara Float Array: per ribbon [rig][tentacle] width multiplier, 0 hides the ribbon (free rig). */
	inline FName WidthScales() { return FName(TEXT("TentacleWidthScale")); }
	/** Niagara Float Array: per ribbon glow 0..1 (attack glow / hit flash). */
	inline FName Glow() { return FName(TEXT("TentacleGlow")); }
	/** int32: points per ribbon. */
	inline FName PointsPerTentacle() { return FName(TEXT("PointsPerTentacle")); }
	/** int32: ribbons in the arrays (MaxRiggedSentinels * NumTentacles). Particles to spawn = TentacleCount * PointsPerTentacle. */
	inline FName TentacleCount() { return FName(TEXT("TentacleCount")); }
	/** float: ribbon width (cm) at the root and at the tip. */
	inline FName RootWidth() { return FName(TEXT("RootWidth")); }
	inline FName TipWidth() { return FName(TEXT("TipWidth")); }
}

/** How the tentacles of one kind of sentinel look and move. Edited on UMechSentinelTentacleTrait. */
USTRUCT(BlueprintType)
struct AURA_API FMechSentinelTentacleDesc
{
	GENERATED_BODY()

	/** Ribbon system built with the README recipe (user parameters listed in MechSwarm::Tentacles::NiagaraParams). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Tentacles")
	TObjectPtr<UNiagaraSystem> NiagaraSystem = nullptr;

	/** Chains per sentinel. Roots come from the head mesh sockets Tentacle_00, Tentacle_01... (built-in ring when missing). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Tentacles", meta = (ClampMin = "1", ClampMax = "16"))
	int32 NumTentacles = 8;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Tentacles", meta = (ClampMin = "3", ClampMax = "32"))
	int32 PointsPerTentacle = 12;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Tentacles", meta = (ClampMin = "1", ForceUnits = "cm"))
	float SegmentLength = 18.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Tentacles", meta = (ClampMin = "0", ForceUnits = "cm"))
	float RootWidth = 18.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Tentacles", meta = (ClampMin = "0", ForceUnits = "cm"))
	float TipWidth = 3.5f;

	/**
	 * Sentinels that get ribbons at the same time (the closest ones win). The others, and every sentinel beyond
	 * MaxDistance or at Low LOD, are drawn with the visualization LowLODMesh, which has the tentacles baked in.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Budget", meta = (ClampMin = "1", ClampMax = "1024"))
	int32 MaxRiggedSentinels = 48;

	/** Closest viewer distance under which a High / Medium LOD sentinel gets ribbons. Keep it near the Medium LOD distance. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Budget", meta = (ClampMin = "0", ForceUnits = "cm"))
	float MaxDistance = 9000.f;

	/** Outward fan of the rest direction away from the head's back axis. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Rest pose", meta = (ClampMin = "0", ClampMax = "80", ForceUnits = "deg"))
	float FanAngle = 20.f;

	/** How much the trailing direction spreads outward (0 = straight back). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Rest pose", meta = (ClampMin = "0", ClampMax = "2"))
	float TrailSpread = 0.22f;

	/** How much the trailing direction hangs below the head's back axis (head relative; gravity adds world droop). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Rest pose", meta = (ClampMin = "0", ClampMax = "2"))
	float TrailDroop = 0.42f;

	/** World gravity on the chain points (cm/s^2). Lower than real gravity reads as "floating in a current". */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Simulation", meta = (ClampMin = "0"))
	float Gravity = 300.f;

	/** Velocity lost per 1/60 s (0 = no drag, 1 = no inertia). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Simulation", meta = (ClampMin = "0", ClampMax = "1"))
	float Damping = 0.06f;

	/** Pull (1/s) toward the head-relative rest pose at the root; the tip uses Stiffness * TipStiffnessScale. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Simulation", meta = (ClampMin = "0"))
	float Stiffness = 5.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Simulation", meta = (ClampMin = "0", ClampMax = "1"))
	float TipStiffnessScale = 0.3f;

	/** Swimming wave travelling down the chain: side amplitude at the tip (cm), frequency, phase step per point. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Simulation", meta = (ClampMin = "0", ForceUnits = "cm"))
	float SwayAmplitude = 12.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Simulation", meta = (ClampMin = "0", ForceUnits = "Hz"))
	float SwayFrequency = 0.7f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Simulation", meta = (ClampMin = "0"))
	float SwayPhasePerPoint = 0.55f;

	/** Sway speed multiplier while attacking (the tentacles thrash). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Simulation", meta = (ClampMin = "0"))
	float AttackSwayMultiplier = 2.2f;

	/** Stiffness multiplier once dead: the tentacles go limp and fall with the wreck. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Simulation", meta = (ClampMin = "0", ClampMax = "1"))
	float DeadStiffnessScale = 0.03f;

	/** A root that moves farther than this in one frame re-lays the chain in its rest pose (spawn, teleport). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Simulation", meta = (ClampMin = "1", ForceUnits = "cm"))
	float TeleportDistance = 400.f;

	/** The ribbons (and claw meshes) cast shadows like the ISM head does. Off saves the shadow pass for the tubes. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Rendering")
	bool bCastShadows = true;

	int32 GetNumRibbons() const { return MaxRiggedSentinels * NumTentacles; }

	bool operator==(const FMechSentinelTentacleDesc& Other) const
	{
		return NiagaraSystem == Other.NiagaraSystem && NumTentacles == Other.NumTentacles
			&& PointsPerTentacle == Other.PointsPerTentacle && SegmentLength == Other.SegmentLength
			&& RootWidth == Other.RootWidth && TipWidth == Other.TipWidth
			&& MaxRiggedSentinels == Other.MaxRiggedSentinels && MaxDistance == Other.MaxDistance
			&& FanAngle == Other.FanAngle && TrailSpread == Other.TrailSpread && TrailDroop == Other.TrailDroop
			&& Gravity == Other.Gravity && Damping == Other.Damping && Stiffness == Other.Stiffness
			&& TipStiffnessScale == Other.TipStiffnessScale && SwayAmplitude == Other.SwayAmplitude
			&& SwayFrequency == Other.SwayFrequency && SwayPhasePerPoint == Other.SwayPhasePerPoint
			&& AttackSwayMultiplier == Other.AttackSwayMultiplier && DeadStiffnessScale == Other.DeadStiffnessScale
			&& TeleportDistance == Other.TeleportDistance && bCastShadows == Other.bCastShadows;
	}
};

/** Which rig of the tentacle set this sentinel currently owns (INDEX_NONE = drawn with the baked-tentacle mesh). */
USTRUCT()
struct AURA_API FMechSentinelTentacleFragment : public FMassFragment
{
	GENERATED_BODY()

	int32 RigIndex = INDEX_NONE;
};

/** Index of the tentacle set in UMechSentinelTentacleSubsystem (one set per distinct FMechSentinelTentacleDesc). */
USTRUCT()
struct AURA_API FMechSentinelTentacleParams : public FMassConstSharedFragment
{
	GENERATED_BODY()

	UPROPERTY()
	int32 SetIndex = INDEX_NONE;
};
