// Fill out your copyright notice in the Description page of Project Settings.

#include "EOS/SessionEntry2.h"
#include "EOS/MainMenu2.h"
#include "Components/Button.h"
#include "Components/TextBlock.h"

bool USessionEntry2::Initialize()
{
	if (!Super::Initialize())
	{
		return false;
	}

	if (JoinEntryButton)
	{
		JoinEntryButton->OnClicked.AddDynamic(this, &ThisClass::JoinEntryButtonClicked);
	}

	return true;
}

void USessionEntry2::Setup(UMainMenu2* InOwningMenu, const FAuraSessionInfo& Info)
{
	OwningMenu = InOwningMenu;
	ResultIndex = Info.ResultIndex;

	if (HostNameText)
	{
		HostNameText->SetText(FText::FromString(Info.HostName.IsEmpty() ? TEXT("Unknown Host") : Info.HostName));
	}
	if (PlayersText)
	{
		PlayersText->SetText(FText::FromString(FString::Printf(TEXT("%d / %d"), Info.MaxSlots - Info.OpenSlots, Info.MaxSlots)));
	}
	if (PingText)
	{
		PingText->SetText(FText::FromString(FString::Printf(TEXT("%d ms"), Info.PingInMs)));
	}
	if (DifficultyText)
	{
		DifficultyText->SetText(FText::FromString(FString::Printf(TEXT("Difficulty %d"), Info.Difficulty)));
	}
	if (RulesText)
	{
		RulesText->SetText(FText::FromString(Info.Rules));
	}
}

void USessionEntry2::JoinEntryButtonClicked()
{
	if (OwningMenu)
	{
		// Left disabled until the next list refresh: this prevents a double JoinSession()
		// call (which would double-bind JoinSessionCompleteDelegateHandle) if the player
		// double-clicks. A failed join is best resolved by refreshing the list anyway.
		if (JoinEntryButton)
		{
			JoinEntryButton->SetIsEnabled(false);
		}
		OwningMenu->JoinLobbyByIndex(ResultIndex);
	}
}
