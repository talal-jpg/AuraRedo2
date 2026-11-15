// Mech Sentinel Swarm - what the server sends to clients for each sentinel (MassReplication fast array item).

#pragma once

#include "CoreMinimal.h"
#include "Engine/NetSerialization.h"
#include "MassClientBubbleHandler.h"
#include "MassReplicationTypes.h"
#include "MechSentinelReplicatedAgent.generated.h"

struct FMechSentinelAttackFragment;
struct FMechSentinelAttributesFragment;
struct FMechSentinelStateFragment;

/**
 * Compact per-sentinel snapshot (~22 bytes before delta compression).
 * Clients do not simulate: they ease toward Position extrapolated with Velocity, and flash when a serial changes.
 */
USTRUCT()
struct FMechSentinelReplicatedData
{
	GENERATED_BODY()

	/** World position, 0.1 cm precision. */
	UPROPERTY(Transient)
	FVector_NetQuantize10 Position{ ForceInitToZero };

	/** Velocity (cm/s), integer precision. Used for client extrapolation. */
	UPROPERTY(Transient)
	FVector_NetQuantize Velocity{ ForceInitToZero };

	/** Rotation axes compressed to 16 bits (FRotator::CompressAxisToShort). Roll carries the banking. */
	UPROPERTY(Transient)
	uint16 Yaw = 0;

	UPROPERTY(Transient)
	uint16 Pitch = 0;

	UPROPERTY(Transient)
	uint16 Roll = 0;

	/** EMechSentinelState. */
	UPROPERTY(Transient)
	uint8 State = 0;

	/** Health fraction * 255 (health bar / damage look on the material). */
	UPROPERTY(Transient)
	uint8 HealthByte = 255;

	/** Incremented by the server on each damaging hit / attack. A change triggers the flash / glow on clients. */
	UPROPERTY(Transient)
	uint8 HitSerial = 0;

	UPROPERTY(Transient)
	uint8 AttackSerial = 0;

	static FMechSentinelReplicatedData FromEntity(const FTransform& Transform, const FVector& InVelocity, const FMechSentinelStateFragment& StateFragment,
		const FMechSentinelAttributesFragment& Attributes, const FMechSentinelAttackFragment& Attack);

	void SetRotation(const FQuat& Rotation);
	FQuat GetRotation() const;

	/** Anything a client would notice (with small movement tolerances). */
	bool DiffersFrom(const FMechSentinelReplicatedData& Other) const;

	/** State / health / hit / attack changes: sent right away, not throttled by the LOD update interval. */
	bool HasDiscreteChange(const FMechSentinelReplicatedData& Other) const;
};

/** The replicated agent: MassReplication base (NetID + template ID) + the sentinel snapshot. */
USTRUCT()
struct FReplicatedMechSentinelAgent : public FReplicatedAgentBase
{
	GENERATED_BODY()

	UPROPERTY(Transient)
	FMechSentinelReplicatedData Data;
};

/** Fast array item. Mark it dirty through the bubble handler whenever Agent changes. */
USTRUCT()
struct FMechSentinelFastArrayItem : public FMassFastArrayItemBase
{
	GENERATED_BODY()

	FMechSentinelFastArrayItem() = default;
	FMechSentinelFastArrayItem(const FReplicatedMechSentinelAgent& InAgent, const FMassReplicatedAgentHandle InHandle)
		: FMassFastArrayItemBase(InHandle)
		, Agent(InAgent)
	{
	}

	/** Required by TClientBubbleHandlerBase / UMassReplicatorBase::CalculateClientReplication. */
	typedef FReplicatedMechSentinelAgent FReplicatedAgentType;

	UPROPERTY()
	FReplicatedMechSentinelAgent Agent;
};
