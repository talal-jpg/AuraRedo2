// Fill out your copyright notice in the Description page of Project Settings.

#include "Match/MyLobbyPlayerRow.h"

#include "MyGameState.h"
#include "MyPlayerState.h"
#include "Components/Button.h"
#include "Components/TextBlock.h"
#include "Match/MyLobbyWidget.h"
#include "Match/MyTeamLibrary.h"

#define LOCTEXT_NAMESPACE "MyLobby"

bool UMyLobbyPlayerRow::Initialize()
{
	if (!Super::Initialize())
	{
		return false;
	}

	if (MoveButton)
	{
		MoveButton->OnClicked.AddUniqueDynamic(this, &ThisClass::MoveButtonClicked);
	}

	return true;
}

void UMyLobbyPlayerRow::Setup(UMyLobbyWidget* InOwner, AMyPlayerState* InPlayer, bool bInIsLocal, bool bInHostView)
{
	Owner = InOwner;
	Player = InPlayer;
	bIsLocal = bInIsLocal;
	bHostView = bInHostView;

	if (LocalHighlight)
	{
		LocalHighlight->SetVisibility(bIsLocal ? ESlateVisibility::HitTestInvisible : ESlateVisibility::Collapsed);
	}

	Refresh();
	OnRowSetup(bIsLocal, bHostView);
}

void UMyLobbyPlayerRow::Refresh()
{
	const AMyPlayerState* State = Player.Get();

	if (!State)
	{
		return;
	}

	const UMyLobbyWidget* LobbyWidget = Owner.Get();
	const AMyGameState* GameState = LobbyWidget ? LobbyWidget->GetLobbyGameState() : nullptr;
	const bool bArriving = State->IsArriving();
	const uint8 Team = State->GetTeamId();
	const uint8 Requested = State->GetRequestedTeam();

	if (PlayerNameText)
	{
		PlayerNameText->SetText(FText::FromString(State->GetPlayerName()));
	}

	if (StatusText)
	{
		FText Status;

		if (bArriving)
		{
			Status = LOCTEXT("RowLoading", "LOADING");
		}
		else if (State->IsHost())
		{
			Status = LOCTEXT("RowHost", "HOST");
		}
		else if (Requested < MyMatch::NumTeams && Requested != Team)
		{
			Status = FText::Format(LOCTEXT("RowWants", "WANTS {0}"), UMyTeamLibrary::GetTeamName(Requested));
		}
		else if (State->IsLobbyReady())
		{
			Status = LOCTEXT("RowReady", "READY");
		}
		else
		{
			Status = LOCTEXT("RowNotReady", "NOT READY");
		}

		StatusText->SetText(Status);
	}

	if (PingText)
	{
		// The host's own ping is always 0, a loading player has none yet
		PingText->SetText(bArriving || State->IsHost() ? FText::GetEmpty()
			: FText::Format(LOCTEXT("RowPing", "{0} ms"), FText::AsNumber(FMath::RoundToInt(State->GetPingInMilliseconds()))));
	}

	if (MoveButton)
	{
		const bool bPractice = GameState && GameState->GetMatchRules().TeamMode == EMyTeamMode::Practice;
		const bool bShow = bHostView && !bArriving && !bPractice && Team < MyMatch::NumTeams;
		// The chip's ring goes with it (as_77's Item_Move)
		UMyLobbyWidget::SetButtonShown(MoveButton, bShow);
		MoveButton->SetIsEnabled(bShow && GameState && GameState->GetMatchPhase() == EMyMatchPhase::Lobby);

		if (MoveText && bShow)
		{
			const uint8 Other = 1 - Team;
			const int32 Cap = LobbyWidget ? LobbyWidget->GetDisplayTeamCap(Other) : 0;
			const bool bFull = Cap > 0 && GameState && GameState->GetTeamState(Other).NumPlayers >= Cap;
			MoveText->SetText(FText::Format(bFull ? LOCTEXT("RowSwap", "SWAP TO {0}") : LOCTEXT("RowMove", "TO {0}"), UMyTeamLibrary::GetTeamName(Other)));
		}
	}
}

void UMyLobbyPlayerRow::MoveButtonClicked()
{
	if (UMyLobbyWidget* LobbyWidget = Owner.Get())
	{
		LobbyWidget->RequestMovePlayer(Player.Get());
	}
}

#undef LOCTEXT_NAMESPACE
