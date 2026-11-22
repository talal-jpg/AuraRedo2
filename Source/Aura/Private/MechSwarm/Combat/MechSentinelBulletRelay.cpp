// Mech Sentinel Swarm - sends the server's sentinel bullets to every machine as Niagara data channel entries.

#include "MechSwarm/Combat/MechSentinelBulletRelay.h"

#include "Net/UnrealNetwork.h"
#include "NiagaraDataChannel.h"
#include "NiagaraDataChannelAccessor.h"
#include "NiagaraDataChannelFunctionLibrary.h"
#include "NiagaraSystem.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(MechSentinelBulletRelay)

AMechSentinelBulletRelay::AMechSentinelBulletRelay()
{
	PrimaryActorTick.bCanEverTick = false;
	bReplicates = true;
	bAlwaysRelevant = true;
	SetReplicatingMovement(false);
	// The server calls ForceNetUpdate after each batch (unreliable multicasts wait for the next net update).
	SetNetUpdateFrequency(10.f);
}

void AMechSentinelBulletRelay::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(AMechSentinelBulletRelay, DataChannel);
	DOREPLIFETIME(AMechSentinelBulletRelay, BulletSystem);
}

void AMechSentinelBulletRelay::Multicast_ShowBullets_Implementation(const TArray<FMechSentinelBulletFx>& Bullets)
{
	ShowBulletsLocal(Bullets);
}

void AMechSentinelBulletRelay::ShowBulletsLocal(const TArray<FMechSentinelBulletFx>& Bullets)
{
	if (!DataChannel || GetNetMode() == NM_DedicatedServer)
	{
		return;
	}

	for (const FMechSentinelBulletFx& Bullet : Bullets)
	{
		// GameplayBurst channels only accept the access context path (as AMyPlayerController2::WriteDamageNumber).
		FNDCAccessContextInst& AccessContext = UNiagaraDataChannelLibrary::GetUsableAccessContextFromNDC(DataChannel);
		if (FNDCAccessContext* Context = AccessContext.Get<FNDCAccessContext>())
		{
			Context->Location = Bullet.Start;
			Context->bOverrideLocation = true;
			// Our own effect in the channel: the map key includes the system, so gun and sentinel bullets keep their own
			// buckets, and the spawned effect's readers (which read this channel) auto-link to the sentinel entries.
			Context->bOverrideSystemToSpawn = BulletSystem != nullptr;
			Context->SystemToSpawn = BulletSystem;
		}
		// CPU readers only (every emitter of the bullet effect is a CPU sim).
		UNiagaraDataChannelWriter* Writer = UNiagaraDataChannelLibrary::WriteToNiagaraDataChannel_WithContext(this, DataChannel, AccessContext, 1, false, true, false, TEXT("MechSentinelBullets"));
		if (!Writer)
		{
			continue;
		}
		// Variable names must match the channel (the gun's NDC_GunShootHit).
		Writer->WritePosition(TEXT("MuzzlePos"), 0, Bullet.Start);
		Writer->WritePosition(TEXT("HitLocation"), 0, Bullet.End);
	}
}
