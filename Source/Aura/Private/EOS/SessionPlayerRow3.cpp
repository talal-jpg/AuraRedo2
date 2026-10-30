// Fill out your copyright notice in the Description page of Project Settings.

#include "EOS/SessionPlayerRow3.h"
#include "EOS/PauseMenu3.h"
#include "Components/Button.h"
#include "Components/TextBlock.h"
#include "GameFramework/PlayerState.h"

#define LOCTEXT_NAMESPACE "SessionPlayerRow3"

bool USessionPlayerRow3::Initialize()
{
	if (!Super::Initialize())
	{
		return false;
	}

	if (ProfileButton) ProfileButton->OnClicked.AddDynamic(this, &ThisClass::ProfileButtonClicked);
	if (KickButton)    KickButton->OnClicked.AddDynamic(this, &ThisClass::KickButtonClicked);
	if (BanButton)     BanButton->OnClicked.AddDynamic(this, &ThisClass::BanButtonClicked);

	return true;
}

void USessionPlayerRow3::Setup(UPauseMenu3* InOwningMenu, APlayerState* InPlayerState, bool bInIsHostPlayer, bool bInIsLocalPlayer, bool bInCanModerate)
{
	OwningMenu = InOwningMenu;
	PlayerState = InPlayerState;
	bRowIsHostPlayer = bInIsHostPlayer;

	if (HostBadge)
	{
		HostBadge->SetVisibility(bInIsHostPlayer ? ESlateVisibility::HitTestInvisible : ESlateVisibility::Collapsed);
	}
	if (LocalPlayerBadge)
	{
		LocalPlayerBadge->SetVisibility(bInIsLocalPlayer ? ESlateVisibility::HitTestInvisible : ESlateVisibility::Collapsed);
	}

	// Your own profile is one Shift+Tab away, the button is for the others
	if (ProfileButton)
	{
		ProfileButton->SetVisibility(bInIsLocalPlayer ? ESlateVisibility::Collapsed : ESlateVisibility::Visible);
	}
	for (UButton* Button : { KickButton, BanButton })
	{
		if (Button)
		{
			Button->SetVisibility(bInCanModerate ? ESlateVisibility::Visible : ESlateVisibility::Collapsed);
		}
	}

	Refresh();
	OnRowSetup(bInIsHostPlayer, bInIsLocalPlayer, bInCanModerate);
}

void USessionPlayerRow3::Refresh()
{
	const APlayerState* State = PlayerState.Get();
	if (!State)
	{
		return;
	}

	if (PlayerNameText)
	{
		PlayerNameText->SetText(FText::FromString(State->GetPlayerName()));
	}
	if (PingText)
	{
		// The host's own ping is meaningless (always 0)
		PingText->SetText(bRowIsHostPlayer
			? LOCTEXT("HostPing", "Host")
			: FText::Format(LOCTEXT("Ping", "{0} ms"), FText::AsNumber(FMath::RoundToInt(State->GetPingInMilliseconds()))));
	}
}

void USessionPlayerRow3::ProfileButtonClicked()
{
	if (OwningMenu && PlayerState.IsValid())
	{
		OwningMenu->ShowPlayerProfile(PlayerState.Get());
	}
}

void USessionPlayerRow3::KickButtonClicked()
{
	if (OwningMenu && PlayerState.IsValid())
	{
		OwningMenu->RequestKick(PlayerState.Get(), false);
	}
}

void USessionPlayerRow3::BanButtonClicked()
{
	if (OwningMenu && PlayerState.IsValid())
	{
		OwningMenu->RequestKick(PlayerState.Get(), true);
	}
}

#undef LOCTEXT_NAMESPACE
