// Mech Sentinel Swarm - registers its owner's collision as boxes live sentinels steer around (floor, airship, bridges).

#include "MechSwarm/Core/MechSentinelObstacleComponent.h"

#include "Components/PrimitiveComponent.h"
#include "Engine/World.h"
#include "GameFramework/Actor.h"
#include "MechSwarm/Core/MechSentinelObstacleSubsystem.h"
#include "TimerManager.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(MechSentinelObstacleComponent)

UMechSentinelObstacleComponent::UMechSentinelObstacleComponent()
{
	PrimaryComponentTick.bCanEverTick = false;
}

void UMechSentinelObstacleComponent::BeginPlay()
{
	Super::BeginPlay();

	// The registry and the avoidance live on the server
	const UMechSentinelObstacleSubsystem* Obstacles = UMechSentinelObstacleSubsystem::Get(this);
	if (!Obstacles || !Obstacles->HasAuthority())
	{
		return;
	}

	Refresh();

	if (RefreshInterval > 0.f)
	{
		GetWorld()->GetTimerManager().SetTimer(RefreshTimer, this, &ThisClass::Refresh, RefreshInterval, true);
	}
}

void UMechSentinelObstacleComponent::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	if (UWorld* World = GetWorld())
	{
		World->GetTimerManager().ClearTimer(RefreshTimer);
	}

	if (UMechSentinelObstacleSubsystem* Obstacles = UMechSentinelObstacleSubsystem::Get(this))
	{
		Obstacles->UnregisterObstacles(this);
	}

	Super::EndPlay(EndPlayReason);
}

void UMechSentinelObstacleComponent::Refresh()
{
	UMechSentinelObstacleSubsystem* Obstacles = UMechSentinelObstacleSubsystem::Get(this);
	const AActor* OwnerActor = GetOwner();
	if (!Obstacles || !Obstacles->HasAuthority() || !OwnerActor)
	{
		return;
	}

	// Fewer components than last time leave no stale boxes behind
	Obstacles->UnregisterObstacles(this);

	FBox Union(ForceInit);
	int32 Key = 0;

	const TInlineComponentArray<UPrimitiveComponent*> Primitives(OwnerActor);
	for (const UPrimitiveComponent* Primitive : Primitives)
	{
		// What players stand on or bump into, not triggers
		if (!Primitive || !Primitive->IsRegistered() || !Primitive->IsCollisionEnabled()
			|| Primitive->GetCollisionResponseToChannel(ECC_Pawn) != ECR_Block)
		{
			continue;
		}

		const FBox Box = Primitive->Bounds.GetBox();
		if (!Box.IsValid)
		{
			continue;
		}

		if (bOneBoxPerComponent)
		{
			FMechSentinelObstacle Obstacle;
			Obstacle.Bounds = Box;
			Obstacle.Margin = Margin;
			Obstacles->RegisterObstacle(this, Obstacle, Key++);
		}
		else
		{
			Union += Box;
		}
	}

	if (!bOneBoxPerComponent && Union.IsValid)
	{
		FMechSentinelObstacle Obstacle;
		Obstacle.Bounds = Union;
		Obstacle.Margin = Margin;
		Obstacles->RegisterObstacle(this, Obstacle);
	}
}
