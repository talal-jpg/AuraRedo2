// Mech Sentinel Swarm - sends the server's sentinel bullets to every machine as Niagara data channel entries.

#include "MechSwarm/Combat/MechSentinelBulletRelay.h"

#include "Net/UnrealNetwork.h"
#include "NiagaraDataChannel.h"
#include "NiagaraDataChannelAccessor.h"
#include "NiagaraDataChannelFunctionLibrary.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(MechSentinelBulletRelay)

AMechSentinelBulletRelay::AMechSentinelBulletRelay()
{
	PrimaryActorTick.bCanEverTick = false;
	bReplicates = true;
	bAlwaysRelevant = true;
	SetReplicatingMovement(false);
	SetNetUpdateFrequency(2.f);
}

void AMechSentinelBulletRelay::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(AMechSentinelBulletRelay, DataChannel);
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
		}
		UNiagaraDataChannelWriter* Writer = UNiagaraDataChannelLibrary::WriteToNiagaraDataChannel_WithContext(this, DataChannel, AccessContext, 1, false, true, true, TEXT("MechSentinelBullets"));
		if (!Writer)
		{
			return;
		}
		// Variable names must match NDC_MechSentinelBullet (a copy of the gun's NDC_GunShootHit).
		Writer->WritePosition(TEXT("MuzzlePos"), 0, Bullet.Start);
		Writer->WritePosition(TEXT("HitLocation"), 0, Bullet.End);
	}
}
