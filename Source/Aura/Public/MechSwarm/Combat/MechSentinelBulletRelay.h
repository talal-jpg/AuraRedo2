// Mech Sentinel Swarm - sends the server's sentinel bullets to every machine as Niagara data channel entries.

#pragma once

#include "CoreMinimal.h"
#include "Engine/NetSerialization.h"
#include "GameFramework/Actor.h"
#include "MechSentinelBulletRelay.generated.h"

class UNiagaraDataChannelAsset;

/** One bullet as the effect sees it: it flies from Start to End (NDC MuzzlePos -> HitLocation) and bursts at End. */
USTRUCT()
struct FMechSentinelBulletFx
{
	GENERATED_BODY()

	UPROPERTY()
	FVector_NetQuantize Start = FVector::ZeroVector;

	UPROPERTY()
	FVector_NetQuantize End = FVector::ZeroVector;
};

/**
 * One per world, spawned by UMechSentinelSwarmSubsystem on the server and replicated to every client (always relevant).
 * Sentinels are Mass entities, not actors, so their bullets need a carrier: the server batches each frame's new bullets
 * into one unreliable multicast, and every machine with a view (standalone, listen host, clients) writes them into
 * DataChannel (NDC_MechSentinelBullet by default, which spawns NS_MechSentinelBullet). Hits are decided by the server
 * only; this is just the look.
 */
UCLASS(NotPlaceable, Transient)
class AURA_API AMechSentinelBulletRelay : public AActor
{
	GENERATED_BODY()

public:
	AMechSentinelBulletRelay();

	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	/** The data channel the bullets are written to (set by the server from the rules' BulletDataChannel). */
	UPROPERTY(Replicated)
	TObjectPtr<UNiagaraDataChannelAsset> DataChannel;

	/** Server: shows Bullets on every machine. Unreliable: a lost batch only loses the look of those bullets. */
	UFUNCTION(NetMulticast, Unreliable)
	void Multicast_ShowBullets(const TArray<FMechSentinelBulletFx>& Bullets);

	/** Writes Bullets into DataChannel on this machine (nothing on a dedicated server). */
	void ShowBulletsLocal(const TArray<FMechSentinelBulletFx>& Bullets);
};
