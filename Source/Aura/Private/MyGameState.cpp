// Fill out your copyright notice in the Description page of Project Settings.


#include "MyGameState.h"

#include "MyPlayerState.h"
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
