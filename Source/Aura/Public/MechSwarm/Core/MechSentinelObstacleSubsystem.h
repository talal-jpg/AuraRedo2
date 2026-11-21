// Mech Sentinel Swarm - registry of the static obstacles (platforms) sentinels keep out of.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "MechSentinelObstacleSubsystem.generated.h"

/** One static obstacle, in world space. */
USTRUCT(BlueprintType)
struct AURA_API FMechSentinelObstacle
{
	GENERATED_BODY()

	/** World AABB. With FootprintRadius > 0 it bounds a vertical capped cylinder (the real shape); else it is the shape. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Obstacle")
	FBox Bounds = FBox(ForceInit);

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Obstacle")
	FVector2D FootprintCenter = FVector2D::ZeroVector;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Obstacle", meta = (ClampMin = "0", ForceUnits = "cm"))
	float FootprintRadius = 0.f;

	/** Extra clearance (cm) for this obstacle only. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Obstacle", meta = (ClampMin = "0", ForceUnits = "cm"))
	float Margin = 0.f;
};

/**
 * Server registry of static obstacles, keyed by owner and a per-owner key. Game and PIE worlds only.
 */
UCLASS()
class AURA_API UMechSentinelObstacleSubsystem : public UWorldSubsystem
{
	GENERATED_BODY()

public:
	/** Null outside game / PIE worlds. */
	static UMechSentinelObstacleSubsystem* Get(const UObject* WorldContextObject);

	/** Adds an obstacle; the same Owner + Key replaces it. No-op on clients. */
	UFUNCTION(BlueprintCallable, Category = "Mech Sentinels|Obstacles", meta = (DefaultToSelf = "Owner"))
	void RegisterObstacle(UObject* Owner, const FMechSentinelObstacle& Obstacle, int32 Key = 0);

	UFUNCTION(BlueprintCallable, Category = "Mech Sentinels|Obstacles", meta = (DefaultToSelf = "Owner"))
	void UnregisterObstacle(UObject* Owner, int32 Key = 0);

	/** Removes every obstacle of Owner. */
	UFUNCTION(BlueprintCallable, Category = "Mech Sentinels|Obstacles", meta = (DefaultToSelf = "Owner"))
	void UnregisterObstacles(UObject* Owner);

	UFUNCTION(BlueprintPure, Category = "Mech Sentinels|Obstacles")
	int32 GetNumObstacles() const;

	/** True when Location is inside any registered obstacle grown by Inflate (cm). Game thread. */
	bool IsInsideObstacle(const FVector& Location, float Inflate) const;

protected:
	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;

private:
	struct FEntry
	{
		TWeakObjectPtr<UObject> Owner;
		int32 Key = 0;
		FMechSentinelObstacle Obstacle;
	};

	TArray<FEntry> Entries;
};
