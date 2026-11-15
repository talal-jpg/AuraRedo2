// Mech Sentinel Swarm - project-owned re-implementation of the MassNavigation smooth orientation feature.
// Mirrors (by role): FMassSmoothOrientationParameters, UMassSmoothOrientationProcessor, UMassSmoothOrientationTrait.
// Deviation: full 3D (yaw + clamped pitch + banking) because sentinels fly.

#pragma once

#include "CoreMinimal.h"
#include "MassEntityTypes.h"
#include "MassProcessor.h"
#include "MassEntityQuery.h"
#include "MassEntityTraitBase.h"
#include "MassSmoothOrientation_Copy.generated.h"

USTRUCT()
struct AURA_API FMassSmoothOrientationParameters_Copy : public FMassConstSharedFragment
{
	GENERATED_BODY()

	/** Exponential interpolation speed toward the wanted orientation (higher = snappier). */
	UPROPERTY(EditAnywhere, Category = "Orientation", meta = (ClampMin = "0"))
	float OrientationSpeed = 5.f;

	/** Below this speed (cm/s) the velocity is not trusted as a facing direction. */
	UPROPERTY(EditAnywhere, Category = "Orientation", meta = (ClampMin = "0", ForceUnits = "cm/s"))
	float MinSpeedForVelocityFacing = 40.f;

	/** Maximum nose up / down (degrees). */
	UPROPERTY(EditAnywhere, Category = "Orientation", meta = (ClampMin = "0", ClampMax = "89"))
	float MaxPitch = 55.f;

	/** Roll (degrees) per 90 deg/s of yaw rate, gives the swarm a living, banking motion. 0 disables. */
	UPROPERTY(EditAnywhere, Category = "Orientation", meta = (ClampMin = "0", ClampMax = "80"))
	float BankingAmount = 25.f;
};

/** Rotates the transform toward FMassDesiredMovementFragment_Copy::DesiredFacing, or the velocity when no facing is set. */
UCLASS()
class AURA_API UMassSmoothOrientationProcessor_Copy : public UMassProcessor
{
	GENERATED_BODY()

public:
	UMassSmoothOrientationProcessor_Copy();

protected:
	virtual void ConfigureQueries(const TSharedRef<FMassEntityManager>& EntityManager) override;
	virtual void Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context) override;

	FMassEntityQuery EntityQuery;
};

UCLASS(meta = (DisplayName = "Smooth Orientation (Copy)"))
class AURA_API UMassSmoothOrientationTrait_Copy : public UMassEntityTraitBase
{
	GENERATED_BODY()

protected:
	virtual void BuildTemplate(FMassEntityTemplateBuildContext& BuildContext, const UWorld& World) const override;

	UPROPERTY(EditAnywhere, Category = "Orientation")
	FMassSmoothOrientationParameters_Copy Orientation;
};
