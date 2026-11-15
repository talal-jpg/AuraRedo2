// Mech Sentinel Swarm - the sentinel trait (put it in the MassEntityConfigAsset with the _Copy traits).

#pragma once

#include "CoreMinimal.h"
#include "MassEntityTraitBase.h"
#include "MechSwarm/Sentinel/MechSentinelFragments.h"
#include "MechSentinelTrait.generated.h"

/** Starting attribute values of a sentinel (the wave spawner can scale them per wave). */
USTRUCT(BlueprintType)
struct AURA_API FMechSentinelAttributeDefaults
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Attributes", meta = (ClampMin = "1"))
	float MaxHealth = 120.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Attributes")
	float Armor = 4.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Attributes", meta = (ClampMin = "0"))
	float AttackDamage = 6.f;

	/** Attacks per second. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Attributes", meta = (ClampMin = "0.05"))
	float AttackSpeed = 0.8f;
};

/**
 * Everything that makes an entity a sentinel: transform, attributes (Mass side of GAS), state, target,
 * attack data, the shared targeting board and the shared movement speed. Clients additionally get the
 * net smoothing fragment.
 *
 * Typical config: Mech Sentinel + Movement (Copy) + Avoidance (Copy) + Smooth Orientation (Copy)
 *                 + Visualization ISM (Copy) + the engine Replication trait (Bubble Info Class = MechSentinelClientBubbleInfo,
 *                 Replicator Class = MechSentinelReplicator).
 */
UCLASS(meta = (DisplayName = "Mech Sentinel"))
class AURA_API UMechSentinelTrait : public UMassEntityTraitBase
{
	GENERATED_BODY()

public:
	FName GetSwarmGroup() const { return SwarmGroup; }

protected:
	virtual void BuildTemplate(FMassEntityTemplateBuildContext& BuildContext, const UWorld& World) const override;

	/** Sentinels of the same group share one targeting board and one movement speed. */
	UPROPERTY(EditAnywhere, Category = "Sentinel")
	FName SwarmGroup = TEXT("Sentinels");

	UPROPERTY(EditAnywhere, Category = "Sentinel")
	FMechSentinelAttributeDefaults Attributes;

	/** Shared by every sentinel of the group (Mass shared fragment). Change at runtime with UMechSentinelSwarmSubsystem::SetSwarmMovementSpeed. */
	UPROPERTY(EditAnywhere, Category = "Sentinel", meta = (ClampMin = "0", ForceUnits = "cm/s"))
	float MovementSpeed = 900.f;

	UPROPERTY(EditAnywhere, Category = "Sentinel")
	FMechSentinelParameters Parameters;
};
