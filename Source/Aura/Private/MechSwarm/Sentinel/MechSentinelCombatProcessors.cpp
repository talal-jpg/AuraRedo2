// Mech Sentinel Swarm - combat processors (attack state + attacks, death fall, collision hash). Authority only.
// The generated code of MechSentinelProcessors.h is included by MechSentinelBehaviorProcessors.cpp.

#include "MechSwarm/Sentinel/MechSentinelProcessors.h"

#include "AbilitySystemComponent.h"
#include "AbilitySystemGlobals.h"
#include "AbilitySystem/Data/MyGameplayTags.h"
#include "CollisionQueryParams.h"
#include "Engine/HitResult.h"
#include "Engine/World.h"
#include "GameplayEffect.h"
#include "MassCommandBuffer.h"
#include "MassCommonTypes.h"
#include "MassEntityManager.h"
#include "MassExecutionContext.h"
#include "Mass/EntityFragments.h"
#include "MechSwarm/Core/MechSentinelSwarmRules.h"
#include "MechSwarm/Core/MechSentinelSwarmSubsystem.h"
#include "MechSwarm/Core/MechSwarmProcessorGroups.h"
#include "MechSwarm/MassCopies/MassMovementFragments_Copy.h"
#include "MechSwarm/Sentinel/MechSentinelFragments.h"

namespace MechSwarm::CombatPrivate
{
	constexpr int32 AuthorityFlags = (int32)(EProcessorExecutionFlags::Standalone | EProcessorExecutionFlags::Server);

	/** Attacks are collected inside the chunk loop and applied afterwards (GAS can run arbitrary game code). */
	struct FPendingAttack
	{
		TWeakObjectPtr<AActor> Target;
		FVector From = FVector::ZeroVector;
		FVector To = FVector::ZeroVector;
		float Damage = 0.f;
		/** Ranged: a bullet (FMechSentinelParameters' bullet settings); else the hit lands at once. */
		bool bRanged = false;
		FMechSentinelBulletSettings Bullet;
		float LeadFactor = 0.f;
		float MuzzleOffset = 0.f;
	};

	/** A wreck that ended up below every floor is removed early. */
	constexpr float MaxWreckFallSpeed = 6000.f;
}

//----------------------------------------------------------------------//
// UMechSentinelAttackProcessor
//----------------------------------------------------------------------//
UMechSentinelAttackProcessor::UMechSentinelAttackProcessor()
	: EntityQuery(*this)
{
	ExecutionFlags = MechSwarm::CombatPrivate::AuthorityFlags;
	ExecutionOrder.ExecuteInGroup = MechSwarm::ProcessorGroups::Combat();
	ExecutionOrder.ExecuteAfter.Add(UE::Mass::ProcessorGroupNames::Movement);
	// Applies gameplay effects to player ASCs.
	bRequiresGameThreadExecution = true;
}

void UMechSentinelAttackProcessor::ConfigureQueries(const TSharedRef<FMassEntityManager>& EntityManager)
{
	EntityQuery.AddRequirement<FTransformFragment>(EMassFragmentAccess::ReadOnly);
	EntityQuery.AddRequirement<FMechSentinelTargetFragment>(EMassFragmentAccess::ReadOnly);
	EntityQuery.AddRequirement<FMechSentinelAttributesFragment>(EMassFragmentAccess::ReadOnly);
	EntityQuery.AddRequirement<FMechSentinelAttackFragment>(EMassFragmentAccess::ReadWrite);
	EntityQuery.AddRequirement<FMechSentinelStateFragment>(EMassFragmentAccess::ReadWrite);
	EntityQuery.AddConstSharedRequirement<FMechSentinelParameters>(EMassFragmentPresence::All);
	EntityQuery.AddSharedRequirement<FMechSentinelTargetingSharedFragment>(EMassFragmentAccess::ReadOnly);
	EntityQuery.AddTagRequirement<FMechSentinelTag>(EMassFragmentPresence::All);
	EntityQuery.AddTagRequirement<FMechSentinelDeadTag>(EMassFragmentPresence::None);
	EntityQuery.AddTagRequirement<FMechSentinelStunnedTag>(EMassFragmentPresence::None);
}

void UMechSentinelAttackProcessor::Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context)
{
	using namespace MechSwarm::CombatPrivate;

	UMechSentinelSwarmSubsystem* Swarm = UWorld::GetSubsystem<UMechSentinelSwarmSubsystem>(EntityManager.GetWorld());
	if (!Swarm)
	{
		return;
	}

	TArray<FPendingAttack> PendingAttacks;
	EntityQuery.ForEachEntityChunk(Context, [&PendingAttacks](FMassExecutionContext& Context)
	{
		const float DeltaTime = Context.GetDeltaTimeSeconds();
		const FMechSentinelParameters& Params = Context.GetConstSharedFragment<FMechSentinelParameters>();
		const FMechSentinelTargetingSharedFragment& Board = Context.GetSharedFragment<FMechSentinelTargetingSharedFragment>();
		const bool bChunkAttacking = Context.DoesArchetypeHaveTag<FMechSentinelAttackingTag>();

		const TConstArrayView<FTransformFragment> TransformList = Context.GetFragmentView<FTransformFragment>();
		const TConstArrayView<FMechSentinelTargetFragment> TargetList = Context.GetFragmentView<FMechSentinelTargetFragment>();
		const TConstArrayView<FMechSentinelAttributesFragment> AttributeList = Context.GetFragmentView<FMechSentinelAttributesFragment>();
		const TArrayView<FMechSentinelAttackFragment> AttackList = Context.GetMutableFragmentView<FMechSentinelAttackFragment>();
		const TArrayView<FMechSentinelStateFragment> StateList = Context.GetMutableFragmentView<FMechSentinelStateFragment>();

		const float EnterRangeSq = FMath::Square(Params.AttackRange);
		const float ExitRangeSq = FMath::Square(Params.AttackRange * Params.AttackExitRangeScale);

		const int32 NumEntities = Context.GetNumEntities();
		for (int32 EntityIndex = 0; EntityIndex < NumEntities; ++EntityIndex)
		{
			const FMechSentinelTargetFragment& Target = TargetList[EntityIndex];
			const FMechSentinelAttributesFragment& Attributes = AttributeList[EntityIndex];
			FMechSentinelAttackFragment& Attack = AttackList[EntityIndex];
			FMechSentinelStateFragment& State = StateList[EntityIndex];
			const FVector Position = TransformList[EntityIndex].GetTransform().GetLocation();

			// A kill or stun from a hit made next to this phase sets State at once, but its tags only arrive when the
			// phase's commands are flushed: until then, no attack, and State is not overwritten.
			if (State.State == EMechSentinelState::Dead || State.State == EMechSentinelState::Stunned)
			{
				continue;
			}

			Attack.Cooldown -= DeltaTime;

			// Only players can be attacked; fallback points are just gathering places.
			const FMechSentinelTargetSlot* PlayerSlot = Board.PlayerSlots.IsValidIndex(Target.PlayerSlot) ? &Board.PlayerSlots[Target.PlayerSlot] : nullptr;
			AActor* PlayerActor = (PlayerSlot && PlayerSlot->bValid) ? PlayerSlot->Actor.Get() : nullptr;
			const float DistanceSq = PlayerActor ? FVector::DistSquared(Position, Target.TargetLocation) : FLT_MAX;
			const float AttackInterval = 1.f / FMath::Max(0.05f, Attributes.AttackSpeed);

			if (!bChunkAttacking)
			{
				if (DistanceSq <= EnterRangeSq)
				{
					// Close enough to hit the target character: attack state.
					Context.Defer().AddTag<FMechSentinelAttackingTag>(Context.GetEntity(EntityIndex));
					State.State = EMechSentinelState::Attacking;
					State.TimeInState = 0.f;
					// Short wind-up so a wave arriving together does not fire in the same frame.
					Attack.Cooldown = FMath::Max(Attack.Cooldown, FMath::FRandRange(0.15f, 0.6f) * AttackInterval);
				}
				else
				{
					// Never bank more than one attack while travelling.
					Attack.Cooldown = FMath::Max(Attack.Cooldown, 0.f);
				}
				continue;
			}

			if (DistanceSq > ExitRangeSq)
			{
				// Target moved away, died or the sentinel was reassigned: back to seeking.
				Context.Defer().RemoveTag<FMechSentinelAttackingTag>(Context.GetEntity(EntityIndex));
				State.State = EMechSentinelState::Seeking;
				State.TimeInState = 0.f;
				continue;
			}

			// The tag can arrive after the state changed (command buffer); keep them in sync.
			State.State = EMechSentinelState::Attacking;

			if (Attack.Cooldown <= 0.f)
			{
				// Keep the rate exact at high frame times, but never fire more than once per frame.
				Attack.Cooldown = FMath::Max(Attack.Cooldown + AttackInterval, 0.25f * AttackInterval);
				Attack.AttackGlow = 1.f;
				++Attack.AttackSerial;

				FPendingAttack& Pending = PendingAttacks.AddDefaulted_GetRef();
				Pending.Target = PlayerActor;
				Pending.From = Position;
				Pending.To = Target.TargetLocation;
				Pending.Damage = Attributes.AttackDamage;
				Pending.bRanged = Params.bRangedAttack;
				Pending.Bullet.Speed = Params.BulletSpeed;
				Pending.Bullet.Range = Params.BulletRange;
				Pending.Bullet.SpreadDegrees = Params.BulletSpreadDegrees;
				Pending.Bullet.Radius = Params.BulletRadius;
				Pending.LeadFactor = Params.BulletLeadFactor;
				Pending.MuzzleOffset = Params.MuzzleOffset;
			}
		}
	});

	if (PendingAttacks.IsEmpty())
	{
		return;
	}

	for (const FPendingAttack& Pending : PendingAttacks)
	{
		AActor* TargetActor = Pending.Target.Get();
		if (!TargetActor)
		{
			continue;
		}

		if (!Pending.bRanged)
		{
			// Melee: the hit lands now.
			Swarm->ApplySentinelAttack(TargetActor, Pending.From, Pending.To, Pending.Damage);
			continue;
		}

		// Ranged: aim ahead of a moving target by its velocity over the flight time, then fire from the muzzle.
		FVector AimPoint = Pending.To;
		// The target's module may pick another part of it for this bullet (an airship's turret); the lead still applies
		if (Swarm->BulletAimRedirect.IsBound())
		{
			Swarm->BulletAimRedirect.Execute(TargetActor, Pending.From, AimPoint);
		}
		if (Pending.LeadFactor > 0.f)
		{
			const float FlightTime = FVector::Dist(Pending.From, AimPoint) / FMath::Max(100.f, Pending.Bullet.Speed);
			AimPoint += TargetActor->GetVelocity() * (FlightTime * Pending.LeadFactor);
		}
		const FVector Muzzle = Pending.From + (AimPoint - Pending.From).GetSafeNormal() * Pending.MuzzleOffset;
		Swarm->FireSentinelBullet(Muzzle, AimPoint, Pending.Damage, Pending.Bullet);
	}
}

//----------------------------------------------------------------------//
// UMechSentinelDeathProcessor
//----------------------------------------------------------------------//
UMechSentinelDeathProcessor::UMechSentinelDeathProcessor()
	: EntityQuery(*this)
{
	ExecutionFlags = MechSwarm::CombatPrivate::AuthorityFlags;
	ExecutionOrder.ExecuteInGroup = MechSwarm::ProcessorGroups::Combat();
	ExecutionOrder.ExecuteAfter.Add(UMechSentinelAttackProcessor::StaticClass()->GetFName());
	// World traces for the wreck.
	bRequiresGameThreadExecution = true;
}

void UMechSentinelDeathProcessor::ConfigureQueries(const TSharedRef<FMassEntityManager>& EntityManager)
{
	EntityQuery.AddRequirement<FTransformFragment>(EMassFragmentAccess::ReadWrite);
	EntityQuery.AddRequirement<FMassVelocityFragment_Copy>(EMassFragmentAccess::ReadWrite);
	EntityQuery.AddRequirement<FMechSentinelStateFragment>(EMassFragmentAccess::ReadWrite);
	EntityQuery.AddConstSharedRequirement<FMechSentinelParameters>(EMassFragmentPresence::All);
	EntityQuery.AddTagRequirement<FMechSentinelDeadTag>(EMassFragmentPresence::All);
}

void UMechSentinelDeathProcessor::Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context)
{
	const UWorld* World = EntityManager.GetWorld();

	EntityQuery.ForEachEntityChunk(Context, [World](FMassExecutionContext& Context)
	{
		const float DeltaTime = FMath::Min(0.1f, Context.GetDeltaTimeSeconds());
		const FMechSentinelParameters& Params = Context.GetConstSharedFragment<FMechSentinelParameters>();
		const TArrayView<FTransformFragment> TransformList = Context.GetMutableFragmentView<FTransformFragment>();
		const TArrayView<FMassVelocityFragment_Copy> VelocityList = Context.GetMutableFragmentView<FMassVelocityFragment_Copy>();
		const TArrayView<FMechSentinelStateFragment> StateList = Context.GetMutableFragmentView<FMechSentinelStateFragment>();

		const FCollisionObjectQueryParams ObjectParams(ECC_WorldStatic);
		const FCollisionQueryParams QueryParams(SCENE_QUERY_STAT(MechSentinelWreck), /*bTraceComplex*/false);
		const float Damping = FMath::Exp(-0.8f * DeltaTime);

		const int32 NumEntities = Context.GetNumEntities();
		for (int32 EntityIndex = 0; EntityIndex < NumEntities; ++EntityIndex)
		{
			FMechSentinelStateFragment& State = StateList[EntityIndex];
			const FMassEntityHandle Entity = Context.GetEntity(EntityIndex);

			State.DeathTimeRemaining -= DeltaTime;
			FVector& Velocity = VelocityList[EntityIndex].Value;
			if (State.DeathTimeRemaining <= 0.f || Velocity.Z < -MechSwarm::CombatPrivate::MaxWreckFallSpeed)
			{
				Context.Defer().DestroyEntity(Entity);
				continue;
			}

			// Ballistic fall: keep some of the flight momentum, add gravity.
			Velocity.X *= Damping;
			Velocity.Y *= Damping;
			Velocity.Z -= Params.FallGravity * DeltaTime;

			FTransform& Transform = TransformList[EntityIndex].GetMutableTransform();
			const FVector Start = Transform.GetLocation();
			FVector End = Start + Velocity * DeltaTime;

			if (Params.bWrecksCollideWithWorld && World)
			{
				// Trace a bit further than the move so the wreck rests on its capsule radius, not its centre.
				const FVector Dir = (End - Start).GetSafeNormal();
				FHitResult Hit;
				if (!Dir.IsZero() && World->LineTraceSingleByObjectType(Hit, Start, End + Dir * Params.CapsuleRadius, ObjectParams, QueryParams))
				{
					End = Hit.Location + Hit.ImpactNormal * Params.CapsuleRadius;
					Velocity = FVector::ZeroVector;
				}
			}
			Transform.SetLocation(End);

			// Tumble, slowing down as the wreck comes to rest.
			const float TumbleScale = FMath::Clamp(Velocity.Size() / 400.f, 0.f, 1.f);
			if (TumbleScale > 0.f)
			{
				const float Seed = float(Entity.Index);
				const FVector Axis = FVector(FMath::Sin(Seed * 1.3f), FMath::Cos(Seed * 2.1f), 0.35f).GetSafeNormal();
				const FQuat Spin(Axis, FMath::DegreesToRadians(Params.WreckTumbleSpeed * TumbleScale * DeltaTime));
				Transform.SetRotation((Spin * Transform.GetRotation()).GetNormalized());
			}
		}
	});
}

//----------------------------------------------------------------------//
// UMechSentinelCollisionHashProcessor
//----------------------------------------------------------------------//
UMechSentinelCollisionHashProcessor::UMechSentinelCollisionHashProcessor()
	: EntityQuery(*this)
{
	ExecutionFlags = MechSwarm::CombatPrivate::AuthorityFlags;
	ExecutionOrder.ExecuteInGroup = MechSwarm::ProcessorGroups::Combat();
	ExecutionOrder.ExecuteAfter.Add(UMechSentinelDeathProcessor::StaticClass()->GetFName());
	// Writes into the subsystem.
	bRequiresGameThreadExecution = true;
}

void UMechSentinelCollisionHashProcessor::ConfigureQueries(const TSharedRef<FMassEntityManager>& EntityManager)
{
	EntityQuery.AddRequirement<FTransformFragment>(EMassFragmentAccess::ReadOnly);
	EntityQuery.AddConstSharedRequirement<FMechSentinelParameters>(EMassFragmentPresence::All);
	EntityQuery.AddTagRequirement<FMechSentinelTag>(EMassFragmentPresence::All);
	EntityQuery.AddTagRequirement<FMechSentinelDeadTag>(EMassFragmentPresence::None);
}

void UMechSentinelCollisionHashProcessor::Execute(FMassEntityManager& EntityManager, FMassExecutionContext& Context)
{
	UMechSentinelSwarmSubsystem* Swarm = UWorld::GetSubsystem<UMechSentinelSwarmSubsystem>(EntityManager.GetWorld());
	if (!Swarm)
	{
		return;
	}

	Swarm->BeginCollisionFrame(Swarm->GetRules()->CollisionCellSize);

	EntityQuery.ForEachEntityChunk(Context, [Swarm](FMassExecutionContext& Context)
	{
		const FMechSentinelParameters& Params = Context.GetConstSharedFragment<FMechSentinelParameters>();
		const TConstArrayView<FTransformFragment> TransformList = Context.GetFragmentView<FTransformFragment>();

		const int32 NumEntities = Context.GetNumEntities();
		for (int32 EntityIndex = 0; EntityIndex < NumEntities; ++EntityIndex)
		{
			const FTransform& Transform = TransformList[EntityIndex].GetTransform();
			// The capsule lies along the body (forward axis), like the squid-like sentinel silhouette.
			Swarm->AddCollisionCapsule(Context.GetEntity(EntityIndex), Transform.GetLocation(), Transform.GetRotation().GetForwardVector(),
				Params.CapsuleRadius, Params.CapsuleHalfHeight);
		}
	});

	Swarm->EndCollisionFrame();
}
