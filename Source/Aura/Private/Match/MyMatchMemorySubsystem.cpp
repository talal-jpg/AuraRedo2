// Fill out your copyright notice in the Description page of Project Settings.


#include "Match/MyMatchMemorySubsystem.h"

#include "MyPlayerState.h"
#include "Engine/GameInstance.h"
#include "Engine/World.h"
#include "GameFramework/GameStateBase.h"
#include "GameFramework/OnlineReplStructs.h"
#include "Match/MyMatchTypes.h"

UMyMatchMemorySubsystem* UMyMatchMemorySubsystem::Get(const UObject* WorldContext)
{
	const UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	const UGameInstance* GameInstance = World ? World->GetGameInstance() : nullptr;
	return GameInstance ? GameInstance->GetSubsystem<UMyMatchMemorySubsystem>() : nullptr;
}

bool UMyMatchMemorySubsystem::FindTeam(const FUniqueNetIdRepl& Id, uint8& OutTeam) const
{
	if (!Id.IsValid())
	{
		return false;
	}

	const uint8* Team = Teams.Find(Id.ToString());

	if (!Team || *Team >= MyMatch::NumTeams)
	{
		return false;
	}

	OutTeam = *Team;
	return true;
}

void UMyMatchMemorySubsystem::RememberTeams(const AGameStateBase* GameState)
{
	if (!GameState)
	{
		return;
	}

	Teams.Reset();
	int32 NumWithoutId = 0;

	for (const APlayerState* PlayerState : GameState->PlayerArray)
	{
		const AMyPlayerState* MyPlayerState = Cast<AMyPlayerState>(PlayerState);

		if (!MyPlayerState || MyPlayerState->GetTeamId() >= MyMatch::NumTeams)
		{
			continue;
		}

		const FUniqueNetIdRepl& Id = MyPlayerState->GetUniqueId();

		if (!Id.IsValid())
		{
			++NumWithoutId;
			continue;
		}

		Teams.Add(Id.ToString(), MyPlayerState->GetTeamId());
	}

	UE_LOG(LogMatch, Log, TEXT("Match memory: %d team(s) remembered for round %d%s"), Teams.Num(), RoundIndex + 1,
		NumWithoutId > 0 ? *FString::Printf(TEXT(", %d player(s) without a net id fall back to join order"), NumWithoutId) : TEXT(""));
}

void UMyMatchMemorySubsystem::Reset()
{
	if (Teams.Num() > 0 || RoundIndex != 0)
	{
		UE_LOG(LogMatch, Log, TEXT("Match memory: reset (fresh match, round 0)"));
	}

	Teams.Reset();
	RoundIndex = 0;
}
