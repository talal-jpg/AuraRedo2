// Fill out your copyright notice in the Description page of Project Settings.

#include "EOS/SessionEntry3.h"
#include "EOS/MainMenu3.h"
#include "Components/Button.h"
#include "Components/TextBlock.h"

#define LOCTEXT_NAMESPACE "SessionEntry3"

bool USessionEntry3::Initialize()
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

void USessionEntry3::Setup(UMainMenu3* InOwningMenu, const FAuraSessionInfo& Info)
{
	OwningMenu = InOwningMenu;
	SessionInfo = Info;

	const FString HostName = Info.HostName.IsEmpty() ? LOCTEXT("UnknownHost", "Unknown Host").ToString() : Info.HostName;
	const bool bFull = Info.OpenSlots <= 0;

	if (LobbyNameText)
	{
		LobbyNameText->SetText(FText::FromString(Info.LobbyName.IsEmpty() ? HostName : Info.LobbyName));
	}
	if (HostNameText)
	{
		HostNameText->SetText(FText::FromString(HostName));
	}
	if (PlayersText)
	{
		PlayersText->SetText(FText::Format(LOCTEXT("Players", "{0} / {1}"), FText::AsNumber(Info.MaxSlots - Info.OpenSlots), FText::AsNumber(Info.MaxSlots)));
	}
	if (PingText)
	{
		PingText->SetText(FText::Format(LOCTEXT("Ping", "{0} ms"), FText::AsNumber(Info.PingInMs)));

		const FLinearColor PingColor = Info.PingInMs <= GoodPingMs ? FLinearColor(0.3f, 0.9f, 0.3f)
			: Info.PingInMs <= OkPingMs ? FLinearColor(0.95f, 0.8f, 0.2f)
			: FLinearColor(0.95f, 0.3f, 0.2f);
		PingText->SetColorAndOpacity(FSlateColor(PingColor));
	}
	if (DifficultyText)
	{
		DifficultyText->SetText(OwningMenu ? OwningMenu->GetDifficultyName(Info.Difficulty) : FText::AsNumber(Info.Difficulty));
	}
	if (RulesText)
	{
		// IN LOBBY / IN MATCH from the advertised InMatch key (SPEC_B_LOBBY 5.6)
		RulesText->SetText(FText::Format(LOCTEXT("RulesAndState", "{0}  {1}"), FText::FromString(Info.Rules),
			Info.bInMatch ? LOCTEXT("InMatch", "IN MATCH") : LOCTEXT("InLobby", "IN LOBBY")));
	}
	if (FullBadge)
	{
		FullBadge->SetVisibility(bFull ? ESlateVisibility::HitTestInvisible : ESlateVisibility::Collapsed);
	}
	if (JoinEntryButton)
	{
		JoinEntryButton->SetIsEnabled(!bFull);
	}

	OnSessionInfoSet(Info);
}

void USessionEntry3::JoinEntryButtonClicked()
{
	if (OwningMenu)
	{
		// Left disabled until the list is rebuilt, so a double click can't start two joins
		if (JoinEntryButton)
		{
			JoinEntryButton->SetIsEnabled(false);
		}
		OwningMenu->JoinLobbyByIndex(SessionInfo.ResultIndex);
	}
}

#undef LOCTEXT_NAMESPACE
