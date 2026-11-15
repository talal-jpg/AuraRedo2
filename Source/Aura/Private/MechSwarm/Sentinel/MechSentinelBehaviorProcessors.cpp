// Mech Sentinel Swarm - behaviour processors (effects, targeting, steering). Authority only.

#include "MechSwarm/Sentinel/MechSentinelProcessors.h"

#include "Engine/World.h"
#include "MassCommonTypes.h"
#include "MassEntityManager.h"
#include "MassExecutionContext.h"
#include "Mass/EntityFragments.h"
#include "MechSwarm/Core/MechSentinelSwarmRules.h"
#include "MechSwarm/Core/MechSentinelSwarmSubsystem.h"
#include "MechSwarm/MassCopies/MassMovementFragments_Copy.h"
#include "MechSwarm/Sentinel/MechSentinelFragments.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(MechSentinelProcessors)

namespace MechSwarm::Behavior
{
	constexpr int32 AuthorityFlags = (int32)(EProcessorExecutionFlags::Standalone | EProcessorExecutionFlags::Server);

	/** Current attackers of a player get this distance discount, so they do not hop between players. */
	constexpr float StickinessDistanceScale = 0.64f;

	FMechSentinelTargetSlot* GetPlayerSlot(FMechSentinelTargetingSharedFragment& Board, const int32 Index)
	{
		return Board.PlayerSlots.IsValidIndex(Index) ? &Board.PlayerSlots[Index] : nullptr;
	}

	FMechSentinelTargetSlot* GetFallbackSlot(FMechSentinelTargetingSharedFragment& Board, const int32 Index)
	{
		return Board.FallbackSlots.IsValidIndex(Index) ? &Board.FallbackSlots[Index] : nullptr;
	}
}

//----------------------------------------------------------------------//
// UMechSentinelEffectsProcessor
//----------------------------------------------------------------------//
UMechSentinelEffectsProcessor::UMechSentinelEffectsProcessor()
	: EntityQuery(*this)
{
	ExecutionFlags = MechSwarm::Behavior::AuthorityFlags;
	ExecutionOrder.ExecuteInGroup = UE::Mass::ProcessorGroupNames::Behavior;
	// Calls into GAS (game thread only).
	bRequiresGameThreadExecution = true;
}

void UMechSentinelEffectsProcessor::ConfigureQueries(const TSharedRef<FMassEntityManager>& EntityManager)
{
	EntityQuery.AddRequirement<FMechSentinelGASFragment>(EMassFragmentAccess::ReadWrite);
	EntityQuery.AddRequirement<FMechSentinelStateFragment>(EMassFragmentAccess::ReadWrite);
	EntityQuery.AddTagRequirement<FMechSentinelTag>(EMassFragmentPresence::All);
	EntityQuery.AddTagRequirement<FMechSentinelDeadTag>(EMassFragmentPresence::None);
}

void UMechSentinelEffectsProcessor::Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context)
{
	UMechSentinelSwarmSubsystem* Swarm = UWorld::GetSubsystem<UMechSentinelSwarmSubsystem>(EntityManager.GetWorld());
	if (!Swarm)
	{
		return;
	}

	TArray<FMassEntityHandle> ToRecompute;
	EntityQuery.ForEachEntityChunk(Context, [&ToRecompute](FMassExecutionContext& Context)
	{
		const float DeltaTime = Context.GetDeltaTimeSeconds();
		const TArrayView<FMechSentinelGASFragment> GASList = Context.GetMutableFragmentView<FMechSentinelGASFragment>();
		const TArrayView<FMechSentinelStateFragment> StateList = Context.GetMutableFragmentView<FMechSentinelStateFragment>();

		const int32 NumEntities = Context.GetNumEntities();
		for (int32 EntityIndex = 0; EntityIndex < NumEntities; ++EntityIndex)
		{
			StateList[EntityIndex].TimeInState += DeltaTime;

			TArray<FMechSentinelActiveEffect>& Effects = GASList[EntityIndex].ActiveEffects;
			bool bAnyExpired = false;
			for (int32 EffectIndex = Effects.Num() - 1; EffectIndex >= 0; --EffectIndex)
			{
				FMechSentinelActiveEffect& Effect = Effects[EffectIndex];
				if (Effect.RemainingTime < 0.f)
				{
					continue; // infinite
				}
				Effect.RemainingTime -= DeltaTime;
				if (Effect.RemainingTime <= 0.f)
				{
					Effects.RemoveAtSwap(EffectIndex);
					bAnyExpired = true;
				}
			}

			if (bAnyExpired)
			{
				ToRecompute.Add(Context.GetEntity(EntityIndex));
			}
		}
	});

	// Expired buffs / debuffs / stuns: let GAS recompute the current values and tags from what is left.
	for (const FMassEntityHandle Entity : ToRecompute)
	{
		Swarm->RecomputeSentinel(Entity);
	}
}

//----------------------------------------------------------------------//
// UMechSentinelTargetSelectionProcessor
//----------------------------------------------------------------------//
UMechSentinelTargetSelectionProcessor::UMechSentinelTargetSelectionProcessor()
	: EntityQuery(*this)
{
	ExecutionFlags = MechSwarm::Behavior::AuthorityFlags;
	ExecutionOrder.ExecuteInGroup = UE::Mass::ProcessorGroupNames::Behavior;
	ExecutionOrder.ExecuteAfter.Add(UMechSentinelEffectsProcessor::StaticClass()->GetFName());
	// Reads player pawns.
	bRequiresGameThreadExecution = true;
}

void UMechSentinelTargetSelectionProcessor::ConfigureQueries(const TSharedRef<FMassEntityManager>& EntityManager)
{
	EntityQuery.AddRequirement<FTransformFragment>(EMassFragmentAccess::ReadOnly);
	EntityQuery.AddRequirement<FMechSentinelTargetFragment>(EMassFragmentAccess::ReadWrite);
	EntityQuery.AddConstSharedRequirement<FMechSentinelParameters>(EMassFragmentPresence::All);
	EntityQuery.AddSharedRequirement<FMechSentinelTargetingSharedFragment>(EMassFragmentAccess::ReadWrite);
	EntityQuery.AddTagRequirement<FMechSentinelTag>(EMassFragmentPresence::All);
	EntityQuery.AddTagRequirement<FMechSentinelDeadTag>(EMassFragmentPresence::None);
}

void UMechSentinelTargetSelectionProcessor::Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context)
{
	using namespace MechSwarm::Behavior;

	UMechSentinelSwarmSubsystem* Swarm = UWorld::GetSubsystem<UMechSentinelSwarmSubsystem>(EntityManager.GetWorld());
	if (!Swarm)
	{
		return;
	}
	const UMechSentinelSwarmRules* Rules = Swarm->GetRules();

	// 1) Refresh every board (one per swarm group) from the live world.
	TArray<TPair<AActor*, FVector>> Players;
	Swarm->GatherPlayerTargets(Players);

	EntityManager.ForEachSharedFragment<FMechSentinelTargetingSharedFragment>([&Players, Swarm, Rules](FMechSentinelTargetingSharedFragment& Board)
	{
		bool bChanged = Board.PlayerSlots.Num() != Players.Num();
		for (int32 Index = 0; !bChanged && Index < Players.Num(); ++Index)
		{
			bChanged = Board.PlayerSlots[Index].Actor.Get() != Players[Index].Key;
		}
		Board.PlayerSlots.SetNum(Players.Num());
		for (int32 Index = 0; Index < Players.Num(); ++Index)
		{
			FMechSentinelTargetSlot& Slot = Board.PlayerSlots[Index];
			Slot.Actor = Players[Index].Key;
			Slot.Location = Players[Index].Value;
			Slot.Claims = 0;
			Slot.Capacity = Rules->MaxAttackersPerPlayer;
			Slot.bValid = true;
		}

		const TConstArrayView<FMechSentinelFallbackPoint> Fallbacks = Swarm->GetFallbackTargets(Board.SwarmGroup);
		bChanged |= Board.FallbackSlots.Num() != Fallbacks.Num();
		for (int32 Index = 0; !bChanged && Index < Fallbacks.Num(); ++Index)
		{
			bChanged = Board.FallbackSlots[Index].Actor.Get() != Fallbacks[Index].Actor.Get();
		}
		Board.FallbackSlots.SetNum(Fallbacks.Num());
		for (int32 Index = 0; Index < Fallbacks.Num(); ++Index)
		{
			FMechSentinelTargetSlot& Slot = Board.FallbackSlots[Index];
			Slot.Actor = Fallbacks[Index].Actor.Get();
			Slot.Location = Fallbacks[Index].GetLocation();
			Slot.Claims = 0;
			Slot.Capacity = Fallbacks[Index].Capacity;
			Slot.bValid = true;
		}

		if (bChanged)
		{
			// Slot indices are no longer meaningful: every sentinel re-evaluates this frame.
			++Board.BoardSerial;
		}
	});

	// 2) Count the claims of sentinels whose assignment is still valid.
	EntityQuery.ForEachEntityChunk(Context, [](FMassExecutionContext& Context)
	{
		FMechSentinelTargetingSharedFragment& Board = Context.GetMutableSharedFragment<FMechSentinelTargetingSharedFragment>();
		const TConstArrayView<FMechSentinelTargetFragment> TargetList = Context.GetFragmentView<FMechSentinelTargetFragment>();

		const int32 NumEntities = Context.GetNumEntities();
		for (int32 EntityIndex = 0; EntityIndex < NumEntities; ++EntityIndex)
		{
			const FMechSentinelTargetFragment& Target = TargetList[EntityIndex];
			if (Target.BoardSerialSeen != Board.BoardSerial)
			{
				continue;
			}
			if (FMechSentinelTargetSlot* PlayerSlot = GetPlayerSlot(Board, Target.PlayerSlot))
			{
				++PlayerSlot->Claims;
			}
			else if (FMechSentinelTargetSlot* FallbackSlot = GetFallbackSlot(Board, Target.FallbackSlot))
			{
				++FallbackSlot->Claims;
			}
		}
	});

	// 3) (Re)assign: nearest player with room -> other players -> fallback points -> least crowded player.
	const float RetargetInterval = Rules->RetargetInterval;
	const float MaxDistanceSq = Rules->MaxTargetDistance > 0.f ? FMath::Square(Rules->MaxTargetDistance) : FLT_MAX;

	EntityQuery.ForEachEntityChunk(Context, [RetargetInterval, MaxDistanceSq](FMassExecutionContext& Context)
	{
		const float DeltaTime = Context.GetDeltaTimeSeconds();
		const FMechSentinelParameters& Params = Context.GetConstSharedFragment<FMechSentinelParameters>();
		FMechSentinelTargetingSharedFragment& Board = Context.GetMutableSharedFragment<FMechSentinelTargetingSharedFragment>();
		const TConstArrayView<FTransformFragment> TransformList = Context.GetFragmentView<FTransformFragment>();
		const TArrayView<FMechSentinelTargetFragment> TargetList = Context.GetMutableFragmentView<FMechSentinelTargetFragment>();

		const int32 NumEntities = Context.GetNumEntities();
		for (int32 EntityIndex = 0; EntityIndex < NumEntities; ++EntityIndex)
		{
			FMechSentinelTargetFragment& Target = TargetList[EntityIndex];
			const FVector Position = TransformList[EntityIndex].GetTransform().GetLocation();

			const bool bStale = Target.BoardSerialSeen != Board.BoardSerial;
			if (bStale)
			{
				Target.PlayerSlot = INDEX_NONE;
				Target.FallbackSlot = INDEX_NONE;
			}

			Target.RetargetTimer -= DeltaTime;
			const FMechSentinelTargetSlot* CurrentPlayer = GetPlayerSlot(Board, Target.PlayerSlot);
			const bool bOverCapacity = CurrentPlayer && CurrentPlayer->Capacity > 0 && CurrentPlayer->Claims > CurrentPlayer->Capacity;

			if (bStale || !Target.HasTarget() || Target.RetargetTimer <= 0.f || bOverCapacity)
			{
				// Release the current claim so this sentinel competes fairly.
				const int32 PreviousPlayer = Target.PlayerSlot;
				if (FMechSentinelTargetSlot* Slot = GetPlayerSlot(Board, Target.PlayerSlot))
				{
					--Slot->Claims;
				}
				else if (FMechSentinelTargetSlot* Fallback = GetFallbackSlot(Board, Target.FallbackSlot))
				{
					--Fallback->Claims;
				}
				Target.PlayerSlot = INDEX_NONE;
				Target.FallbackSlot = INDEX_NONE;

				int32 BestPlayer = INDEX_NONE;
				float BestScore = FLT_MAX;
				for (int32 SlotIndex = 0; SlotIndex < Board.PlayerSlots.Num(); ++SlotIndex)
				{
					const FMechSentinelTargetSlot& Slot = Board.PlayerSlots[SlotIndex];
					const float DistSq = FVector::DistSquared(Slot.Location, Position);
					if (!Slot.HasRoom() || DistSq > MaxDistanceSq)
					{
						continue;
					}
					const float Score = DistSq * (SlotIndex == PreviousPlayer ? MechSwarm::Behavior::StickinessDistanceScale : 1.f);
					if (Score < BestScore)
					{
						BestScore = Score;
						BestPlayer = SlotIndex;
					}
				}

				if (BestPlayer != INDEX_NONE)
				{
					Target.PlayerSlot = BestPlayer;
					++Board.PlayerSlots[BestPlayer].Claims;
				}
				else
				{
					int32 BestFallback = INDEX_NONE;
					float BestFallbackDistSq = FLT_MAX;
					for (int32 SlotIndex = 0; SlotIndex < Board.FallbackSlots.Num(); ++SlotIndex)
					{
						const FMechSentinelTargetSlot& Slot = Board.FallbackSlots[SlotIndex];
						const float DistSq = FVector::DistSquared(Slot.Location, Position);
						if (Slot.HasRoom() && DistSq < BestFallbackDistSq)
						{
							BestFallbackDistSq = DistSq;
							BestFallback = SlotIndex;
						}
					}

					if (BestFallback != INDEX_NONE)
					{
						Target.FallbackSlot = BestFallback;
						++Board.FallbackSlots[BestFallback].Claims;
					}
					else if (Board.PlayerSlots.Num() > 0)
					{
						// Everything is crowded and there is nowhere else to go: join the least crowded player.
						int32 LeastCrowded = 0;
						for (int32 SlotIndex = 1; SlotIndex < Board.PlayerSlots.Num(); ++SlotIndex)
						{
							if (Board.PlayerSlots[SlotIndex].Claims < Board.PlayerSlots[LeastCrowded].Claims)
							{
								LeastCrowded = SlotIndex;
							}
						}
						Target.PlayerSlot = LeastCrowded;
						++Board.PlayerSlots[LeastCrowded].Claims;
					}
				}

				Target.BoardSerialSeen = Board.BoardSerial;
				Target.RetargetTimer = RetargetInterval * FMath::FRandRange(0.7f, 1.3f);
			}

			// Follow the (moving) target every frame.
			if (const FMechSentinelTargetSlot* Player = GetPlayerSlot(Board, Target.PlayerSlot))
			{
				Target.TargetLocation = Player->Location + FVector(0.f, 0.f, Params.TargetHeightOffset);
			}
			else if (const FMechSentinelTargetSlot* Fallback = GetFallbackSlot(Board, Target.FallbackSlot))
			{
				Target.TargetLocation = Fallback->Location;
			}
		}
	});
}

//----------------------------------------------------------------------//
// UMechSentinelSteeringProcessor
//----------------------------------------------------------------------//
UMechSentinelSteeringProcessor::UMechSentinelSteeringProcessor()
	: EntityQuery(*this)
{
	ExecutionFlags = MechSwarm::Behavior::AuthorityFlags;
	ExecutionOrder.ExecuteInGroup = UE::Mass::ProcessorGroupNames::Tasks;
	ExecutionOrder.ExecuteAfter.Add(UE::Mass::ProcessorGroupNames::Behavior);
}

void UMechSentinelSteeringProcessor::ConfigureQueries(const TSharedRef<FMassEntityManager>& EntityManager)
{
	EntityQuery.AddRequirement<FTransformFragment>(EMassFragmentAccess::ReadOnly);
	EntityQuery.AddRequirement<FMechSentinelTargetFragment>(EMassFragmentAccess::ReadWrite);
	EntityQuery.AddRequirement<FMechSentinelAttributesFragment>(EMassFragmentAccess::ReadOnly);
	EntityQuery.AddRequirement<FMassDesiredMovementFragment_Copy>(EMassFragmentAccess::ReadWrite);
	EntityQuery.AddConstSharedRequirement<FMechSentinelParameters>(EMassFragmentPresence::All);
	EntityQuery.AddSharedRequirement<FMechSentinelSharedAttributesFragment>(EMassFragmentAccess::ReadOnly);
	EntityQuery.AddTagRequirement<FMechSentinelTag>(EMassFragmentPresence::All);
	EntityQuery.AddTagRequirement<FMechSentinelDeadTag>(EMassFragmentPresence::None);
	EntityQuery.AddTagRequirement<FMassCustomMovementTag_Copy>(EMassFragmentPresence::None);
}

void UMechSentinelSteeringProcessor::Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context)
{
	const UWorld* World = EntityManager.GetWorld();
	const float Time = World ? (float)World->GetTimeSeconds() : 0.f;

	EntityQuery.ForEachEntityChunk(Context, [Time](FMassExecutionContext& Context)
	{
		const float DeltaTime = Context.GetDeltaTimeSeconds();
		const FMechSentinelParameters& Params = Context.GetConstSharedFragment<FMechSentinelParameters>();
		const FMechSentinelSharedAttributesFragment& Shared = Context.GetSharedFragment<FMechSentinelSharedAttributesFragment>();
		const bool bStunned = Context.DoesArchetypeHaveTag<FMechSentinelStunnedTag>();
		const bool bAttacking = Context.DoesArchetypeHaveTag<FMechSentinelAttackingTag>();

		const TConstArrayView<FTransformFragment> TransformList = Context.GetFragmentView<FTransformFragment>();
		const TArrayView<FMechSentinelTargetFragment> TargetList = Context.GetMutableFragmentView<FMechSentinelTargetFragment>();
		const TConstArrayView<FMechSentinelAttributesFragment> AttributeList = Context.GetFragmentView<FMechSentinelAttributesFragment>();
		const TArrayView<FMassDesiredMovementFragment_Copy> DesiredList = Context.GetMutableFragmentView<FMassDesiredMovementFragment_Copy>();

		const int32 NumEntities = Context.GetNumEntities();
		for (int32 EntityIndex = 0; EntityIndex < NumEntities; ++EntityIndex)
		{
			FMassDesiredMovementFragment_Copy& Desired = DesiredList[EntityIndex];
			FMechSentinelTargetFragment& Target = TargetList[EntityIndex];
			const FVector Position = TransformList[EntityIndex].GetTransform().GetLocation();
			const float Speed = Shared.MovementSpeed * AttributeList[EntityIndex].MoveSpeedMultiplier;

			if (bStunned)
			{
				// Systems offline: sink slowly, no steering.
				Desired.DesiredVelocity = FVector(0.f, 0.f, -Params.FallGravity * Params.StunnedGravityScale);
				Desired.DesiredFacing = FQuat::Identity;
				Desired.DesiredMaxSpeedOverride = FMath::Max(50.f, Speed * 0.35f);
				continue;
			}

			// Organic wobble, de-phased per entity so the swarm does not move in lockstep.
			const float Phase = float(Context.GetEntity(EntityIndex).Index) * 0.6180339f;
			const FVector Wobble(
				FMath::Sin(Time * 1.7f + Phase * 3.1f),
				FMath::Sin(Time * 1.3f + Phase * 5.3f),
				FMath::Sin(Time * 2.3f + Phase * 7.7f));

			if (!Target.HasTarget())
			{
				Desired.DesiredVelocity = Wobble * (Speed * Params.WobbleAmount);
				Desired.DesiredFacing = FQuat::Identity;
				Desired.DesiredMaxSpeedOverride = Speed;
				continue;
			}

			const bool bHasPlayer = Target.PlayerSlot != INDEX_NONE;
			if (bHasPlayer)
			{
				// Circle around the player.
				Target.OrbitDirection = Target.OrbitDirection.RotateAngleAxis(Params.OrbitAngularSpeed * DeltaTime, FVector::UpVector);
			}

			const float OrbitRadius = bHasPlayer ? Params.OrbitRadius : Params.FallbackLoiterRadius;
			const FVector Goal = Target.TargetLocation + Target.OrbitDirection * OrbitRadius;
			const FVector ToGoal = Goal - Position;
			const float Distance = ToGoal.Size();
			const float Arrival = FMath::Clamp(Distance / Params.SlowdownRadius, 0.f, 1.f);

			FVector Velocity = Distance > 1.f ? ToGoal * (Speed * Arrival / Distance) : FVector::ZeroVector;
			Velocity += Wobble * (Speed * Params.WobbleAmount);

			Desired.DesiredVelocity = Velocity;
			Desired.DesiredMaxSpeedOverride = Speed;
			Desired.DesiredFacing = (bAttacking && bHasPlayer)
				? (Target.TargetLocation - Position).GetSafeNormal().ToOrientationQuat()
				: FQuat::Identity;
		}
	});
}
