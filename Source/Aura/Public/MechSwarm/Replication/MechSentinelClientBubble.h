// Mech Sentinel Swarm - MassReplication client bubble (one per connected client, owned by its PlayerController).
//
// Server: UMechSentinelReplicator adds / updates / removes agents in each client's bubble.
// Client: the fast array callbacks spawn, update and destroy the matching client-side Mass entities.

#pragma once

#include "CoreMinimal.h"
#include "MassClientBubbleHandler.h"
#include "MassClientBubbleInfoBase.h"
#include "MassEntityView.h"
#include "MechSwarm/Replication/MechSentinelReplicatedAgent.h"
#include "MechSentinelClientBubble.generated.h"

class FMechSentinelClientBubbleHandler : public TClientBubbleHandlerBase<FMechSentinelFastArrayItem>
{
public:
	typedef TClientBubbleHandlerBase<FMechSentinelFastArrayItem> Super;

#if UE_REPLICATION_COMPILE_SERVER_CODE
	/** Server: stores NewData in the agent and marks it dirty when a client would notice the difference. Returns true when marked. */
	bool SetAgentData(FMassReplicatedAgentHandle Handle, const FMechSentinelReplicatedData& NewData);
#endif // UE_REPLICATION_COMPILE_SERVER_CODE

protected:
#if UE_REPLICATION_COMPILE_CLIENT_CODE
	virtual void PreReplicatedRemove(const TArrayView<int32> RemovedIndices, int32 FinalSize) override;
	virtual void PostReplicatedAdd(const TArrayView<int32> AddedIndices, int32 FinalSize) override;
	virtual void PostReplicatedChange(const TArrayView<int32> ChangedIndices, int32 FinalSize) override;

	/** Keeps only agents whose entity template exists on this client (builds missing templates first). */
	void FilterSpawnableAgents(const TArrayView<int32> Indices, TArray<int32>& OutSpawnable) const;

	/** Writes a replicated snapshot into the client entity. bJustSpawned snaps the transform and suppresses flashes. */
	void ApplyToEntity(const FMassEntityView& EntityView, const FReplicatedMechSentinelAgent& Agent, bool bJustSpawned) const;
#endif // UE_REPLICATION_COMPILE_CLIENT_CODE
};

/** The replicated fast array of sentinel agents of one client. */
USTRUCT()
struct FMechSentinelClientBubbleSerializer : public FMassClientBubbleSerializerBase
{
	GENERATED_BODY()

	FMechSentinelClientBubbleSerializer()
	{
		Bubble.Initialize(Sentinels, *this);
	}

	bool NetDeltaSerialize(FNetDeltaSerializeInfo& DeltaParams)
	{
		return FFastArraySerializer::FastArrayDeltaSerialize<FMechSentinelFastArrayItem, FMechSentinelClientBubbleSerializer>(Sentinels, DeltaParams, *this);
	}

	FMechSentinelClientBubbleHandler Bubble;

protected:
	/** Free-list on the server (indices are agent handles). Order differs on clients; the NetID is what matches. */
	UPROPERTY(Transient)
	TArray<FMechSentinelFastArrayItem> Sentinels;
};

template<>
struct TStructOpsTypeTraits<FMechSentinelClientBubbleSerializer> : public TStructOpsTypeTraitsBase2<FMechSentinelClientBubbleSerializer>
{
	enum
	{
		WithNetDeltaSerializer = true,
		WithCopy = false,
	};
};

/**
 * The bubble info actor that carries the sentinel fast array to one client. Registered by UMechSentinelSwarmSubsystem
 * and referenced by the engine "Replication" trait (Params -> Bubble Info Class) of the sentinel entity config.
 */
UCLASS()
class AURA_API AMechSentinelClientBubbleInfo : public AMassClientBubbleInfoBase
{
	GENERATED_BODY()

public:
	AMechSentinelClientBubbleInfo(const FObjectInitializer& ObjectInitializer);

	FMechSentinelClientBubbleSerializer& GetSentinelSerializer() { return SentinelSerializer; }

	/** Skips a stale client copy kept through a seamless travel (its serializer's world is gone). */
	virtual void Tick(float DeltaTime) override;

protected:
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	UPROPERTY(Replicated, Transient)
	FMechSentinelClientBubbleSerializer SentinelSerializer;
};
