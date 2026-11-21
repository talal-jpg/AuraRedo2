// Mech Sentinel Swarm - registry of the static obstacles (platforms) sentinels keep out of.

#include "MechSwarm/Core/MechSentinelObstacleSubsystem.h"

#include "Engine/World.h"

UMechSentinelObstacleSubsystem* UMechSentinelObstacleSubsystem::Get(const UObject* WorldContextObject)
{
	const UWorld* World = WorldContextObject ? WorldContextObject->GetWorld() : nullptr;
	return World ? World->GetSubsystem<UMechSentinelObstacleSubsystem>() : nullptr;
}

bool UMechSentinelObstacleSubsystem::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

void UMechSentinelObstacleSubsystem::RegisterObstacle(UObject* Owner, const FMechSentinelObstacle& Obstacle, const int32 Key)
{
	const UWorld* World = GetWorld();
	if (!Owner || !Obstacle.Bounds.IsValid || !World || World->GetNetMode() == NM_Client)
	{
		return;
	}

	for (FEntry& Entry : Entries)
	{
		if (Entry.Key == Key && Entry.Owner.Get() == Owner)
		{
			Entry.Obstacle = Obstacle;
			return;
		}
	}

	FEntry& Entry = Entries.AddDefaulted_GetRef();
	Entry.Owner = Owner;
	Entry.Key = Key;
	Entry.Obstacle = Obstacle;
}

void UMechSentinelObstacleSubsystem::UnregisterObstacle(UObject* Owner, const int32 Key)
{
	Entries.RemoveAllSwap([Owner, Key](const FEntry& Entry)
	{
		return !Entry.Owner.IsValid() || (Entry.Key == Key && Entry.Owner.Get() == Owner);
	});
}

void UMechSentinelObstacleSubsystem::UnregisterObstacles(UObject* Owner)
{
	Entries.RemoveAllSwap([Owner](const FEntry& Entry)
	{
		return !Entry.Owner.IsValid() || Entry.Owner.Get() == Owner;
	});
}

int32 UMechSentinelObstacleSubsystem::GetNumObstacles() const
{
	return Entries.Num();
}

bool UMechSentinelObstacleSubsystem::IsInsideObstacle(const FVector& Location, const float Inflate) const
{
	for (const FEntry& Entry : Entries)
	{
		const FMechSentinelObstacle& Obstacle = Entry.Obstacle;
		const double Grow = FMath::Max(double(Inflate), 0.0) + FMath::Max(double(Obstacle.Margin), 0.0);
		if (!Obstacle.Bounds.ExpandBy(Grow).IsInsideOrOn(Location))
		{
			continue;
		}

		if (Obstacle.FootprintRadius <= 0.f)
		{
			return true;
		}

		const double Radius = double(Obstacle.FootprintRadius) + Grow;
		if (FVector2D::DistSquared(FVector2D(Location.X, Location.Y), Obstacle.FootprintCenter) <= Radius * Radius)
		{
			return true;
		}
	}
	return false;
}
