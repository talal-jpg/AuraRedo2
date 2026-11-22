// Fill out your copyright notice in the Description page of Project Settings.


#include "MyGameState.h"

#include "EngineUtils.h"
#include "MyPlayerState.h"
#include "NiagaraFunctionLibrary.h"
#include "NiagaraSystem.h"
#include "Actors/MyHexPlatform.h"
#include "Kismet/KismetSystemLibrary.h"
#include "Net/UnrealNetwork.h"


void AMyGameState::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);

	DOREPLIFETIME(AMyGameState, PlayerRanking);
}

void AMyGameState::AddPlayerState(APlayerState* PlayerState)
{
	Super::AddPlayerState(PlayerState);

	if (HasAuthority())
	{
		UpdatePlayerRanking();
	}
}

void AMyGameState::RemovePlayerState(APlayerState* PlayerState)
{
	Super::RemovePlayerState(PlayerState);

	if (HasAuthority())
	{
		UpdatePlayerRanking();
	}
}

void AMyGameState::UpdatePlayerRanking()
{
	if (!HasAuthority())
	{
		return;
	}

	TArray<TObjectPtr<AMyPlayerState>> Ranked;

	for (APlayerState* PlayerState : PlayerArray)
	{
		if (AMyPlayerState* MyPlayerState = Cast<AMyPlayerState>(PlayerState))
		{
			Ranked.Add(MyPlayerState);
		}
	}

	// Furthest first; -1 (no platform yet) sorts last. Stable, so ties keep join order.
	Ranked.StableSort([](const AMyPlayerState& A, const AMyPlayerState& B)
	{
		return A.GetPlatformSplineDistance() > B.GetPlatformSplineDistance();
	});

	int32 NumLeaders = 0;

	if (Ranked.Num() > 0 && Ranked[0]->HasPlatformSplineDistance())
	{
		const float LeadDistance = Ranked[0]->GetPlatformSplineDistance();

		while (NumLeaders < Ranked.Num()
			&& Ranked[NumLeaders]->GetPlatformSplineDistance() >= LeadDistance - LeadDistanceTolerance)
		{
			++NumLeaders;
		}
	}

	// The lead can move to a further platform without the order changing, so this runs before the
	// "nothing changed" early out below. Only platforms behind the lead's platform: the one the lead
	// stands on (and those at its distance) keep standing until the lead moves on.
	if (NumLeaders > 0)
	{
		ActivatePlatformsUpTo(Ranked[0]->GetPlatformSplineDistance() - CollapseStartBehindLead);
	}

	if (Ranked == PlayerRanking.PlayerStates && NumLeaders == PlayerRanking.NumLeaders)
	{
		return;
	}

	PlayerRanking.PlayerStates = MoveTemp(Ranked);
	PlayerRanking.NumLeaders = NumLeaders;

	//TODO Add Leaders PSs array to the broadcast and Sub to it in OverlayWC And show in HUD
	for (auto PS :GetLeadingPlayerStates() )
	{
		UKismetSystemLibrary::PrintString(GetWorld(), TEXT("Leader: ") + PS->GetPlayerName(),true,true,FLinearColor::Red,2000);
	}
	UKismetSystemLibrary::PrintString(GetWorld(), TEXT("NumLeaders: ") + FString::FromInt(NumLeaders));
	
	OnPlayerRankingChanged.Broadcast();
}

void AMyGameState::ActivatePlatformsUpTo(float MaxDistance)
{
	// Already activated everything up to here
	if (MaxDistance <= ActivatedSplineDistance)
	{
		return;
	}

	ActivatedSplineDistance = MaxDistance;

	// Platforms spawned later check GetActivatedSplineDistance() themselves once their bridges are ready
	for (TActorIterator<AMyHexPlatform> It(GetWorld()); It; ++It)
	{
		AMyHexPlatform* Platform = *It;

		if (IsValid(Platform) && Platform->HasSplineDistance() && Platform->GetSplineDistance() <= MaxDistance)
		{
			// Latched, and all at this moment, so platforms at the same distance collapse in step.
			// Collapsing starts once the platform's bridges are built (timed from now).
			Platform->NotifyLeadLanded();
		}
	}
}

float AMyGameState::GetLeadSplineDistance() const
{
	const AMyPlayerState* Lead = PlayerRanking.NumLeaders > 0 && PlayerRanking.PlayerStates.Num() > 0
		? PlayerRanking.PlayerStates[0].Get()
		: nullptr;

	return Lead ? Lead->GetPlatformSplineDistance() : -1.f;
}

TArray<AMyPlayerState*> AMyGameState::GetLeadingPlayerStates() const
{
	TArray<AMyPlayerState*> Leaders;
	const int32 NumLeaders = FMath::Min(PlayerRanking.NumLeaders, PlayerRanking.PlayerStates.Num());

	for (int32 Index = 0; Index < NumLeaders; ++Index)
	{
		if (AMyPlayerState* PlayerState = PlayerRanking.PlayerStates[Index])
		{
			Leaders.Add(PlayerState);
		}
	}

	return Leaders;
}

bool AMyGameState::IsLeading(const AMyPlayerState* PlayerState) const
{
	const int32 Index = PlayerRanking.PlayerStates.IndexOfByKey(PlayerState);
	return PlayerState && Index != INDEX_NONE && Index < PlayerRanking.NumLeaders;
}

void AMyGameState::OnRep_PlayerRanking()
{
	OnPlayerRankingChanged.Broadcast();
}

void AMyGameState::MulticastPlayRespawnFX_Implementation(UNiagaraSystem* System, FVector_NetQuantize Location, FRotator Rotation)
{
	if (System && GetNetMode() != NM_DedicatedServer)
	{
		UNiagaraFunctionLibrary::SpawnSystemAtLocation(this, System, Location, Rotation);
	}
}
