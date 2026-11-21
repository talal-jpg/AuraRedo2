// Mech Sentinel Swarm - registers its owner's collision as boxes live sentinels steer around (floor, airship, bridges).

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "Engine/TimerHandle.h"
#include "MechSentinelObstacleComponent.generated.h"

/**
 * Add it to an actor live sentinels must not fly through (a floor, the airship, a bridge). On the server it registers the
 * world bounding box of the owner's components that block pawns with UMechSentinelObstacleSubsystem (BeginPlay, Refresh),
 * and removes it in EndPlay. Hex platforms register themselves, as a cylinder that follows their tiles.
 * The box is the shape: keep it for box-like geometry (around a disc, a box reaches 41% of the radius past the rim).
 */
UCLASS(ClassGroup = (MechSentinels), meta = (BlueprintSpawnableComponent))
class AURA_API UMechSentinelObstacleComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UMechSentinelObstacleComponent();

	/** Measures the owner's colliding components again and registers the result (after the owner moved or changed). */
	UFUNCTION(BlueprintCallable, BlueprintAuthorityOnly, Category = "Mech Sentinels|Obstacles")
	void Refresh();

	/** Extra clearance (cm) sentinels keep from this obstacle. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Obstacle", meta = (ClampMin = "0", ForceUnits = "cm"))
	float Margin = 0.f;

	/** One box per colliding component instead of one box around all of them (an owner made of separate parts). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Obstacle")
	bool bOneBoxPerComponent = false;

	/** Seconds between automatic refreshes, for an owner that moves. 0 = BeginPlay and Refresh calls only. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Obstacle", meta = (ClampMin = "0", ForceUnits = "s"))
	float RefreshInterval = 0.f;

protected:
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

private:
	FTimerHandle RefreshTimer;
};
