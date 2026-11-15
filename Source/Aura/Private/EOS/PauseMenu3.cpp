// Fill out your copyright notice in the Description page of Project Settings.

#include "EOS/PauseMenu3.h"
#include "EOS/MultiplayerSessionsSubsystem.h"
#include "EOS/SessionPlayerRow3.h"
#include "UI/Settings/SettingsMenu3.h"
#include "Components/Button.h"
#include "Components/PanelWidget.h"
#include "Components/TextBlock.h"
#include "Components/WidgetSwitcher.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/GameStateBase.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/PlayerState.h"
#include "GameMapsSettings.h"
#include "HAL/PlatformApplicationMisc.h"
#include "Kismet/KismetSystemLibrary.h"

#define LOCTEXT_NAMESPACE "PauseMenu3"

void UPauseMenu3::OpenMenu()
{
	if (bMenuOpen)
	{
		return;
	}
	bMenuOpen = true;

	if (!IsInViewport())
	{
		// Above the HUD
		AddToViewport(50);
	}
	SetVisibility(ESlateVisibility::Visible);
	SetIsFocusable(true);

	if (APlayerController* PlayerController = GetOwningPlayer())
	{
		bCursorWasShown = PlayerController->ShouldShowMouseCursor();

		// Nothing stays held (moving, firing) while the menu has the input
		PlayerController->FlushPressedKeys();

		FInputModeUIOnly InputModeData;
		InputModeData.SetWidgetToFocus(TakeWidget());
		InputModeData.SetLockMouseToViewportBehavior(EMouseLockMode::DoNotLock);
		PlayerController->SetInputMode(InputModeData);
		PlayerController->SetShowMouseCursor(true);
	}

	CurrentPanel = nullptr;
	ShowPanel(PauseHomePanel);
}

void UPauseMenu3::CloseMenu()
{
	if (!bMenuOpen)
	{
		return;
	}
	bMenuOpen = false;

	if (OptionsMenu && CurrentPanel && CurrentPanel == GetOptionsPanel())
	{
		// Saves the settings; its OnClosed lands in OnOptionsClosed, which does nothing once closed
		OptionsMenu->CloseSettings();
	}

	PendingConfirmAction = EPauseMenu3ConfirmAction::None;
	PendingKickTarget.Reset();
	RemoveFromParent();

	if (APlayerController* PlayerController = GetOwningPlayer())
	{
		// The same input mode AMyPlayerController2::BeginPlay sets
		FInputModeGameOnly InputModeData;
		InputModeData.SetConsumeCaptureMouseDown(false);
		PlayerController->SetInputMode(InputModeData);
		PlayerController->SetShowMouseCursor(bCursorWasShown);
	}
}

bool UPauseMenu3::Initialize()
{
	if (!Super::Initialize())
	{
		return false;
	}

	// Home
	if (ResumeButton)         ResumeButton->OnClicked.AddDynamic(this, &ThisClass::ResumeButtonClicked);
	if (CurrentSessionButton) CurrentSessionButton->OnClicked.AddDynamic(this, &ThisClass::CurrentSessionButtonClicked);
	if (OptionsButton)        OptionsButton->OnClicked.AddDynamic(this, &ThisClass::OptionsButtonClicked);
	if (LeaveSessionButton)   LeaveSessionButton->OnClicked.AddDynamic(this, &ThisClass::LeaveSessionButtonClicked);
	if (QuitGameButton)       QuitGameButton->OnClicked.AddDynamic(this, &ThisClass::QuitGameButtonClicked);

	// Current Session
	if (CopyCodeButton)           CopyCodeButton->OnClicked.AddDynamic(this, &ThisClass::CopyCodeButtonClicked);
	if (InviteFriendsButton)      InviteFriendsButton->OnClicked.AddDynamic(this, &ThisClass::InviteFriendsButtonClicked);
	if (PrivacyPublicButton)      PrivacyPublicButton->OnClicked.AddDynamic(this, &ThisClass::PrivacyPublicClicked);
	if (PrivacyFriendsOnlyButton) PrivacyFriendsOnlyButton->OnClicked.AddDynamic(this, &ThisClass::PrivacyFriendsOnlyClicked);
	if (PrivacyCodeOnlyButton)    PrivacyCodeOnlyButton->OnClicked.AddDynamic(this, &ThisClass::PrivacyCodeOnlyClicked);
	if (OpenLobbyButton)          OpenLobbyButton->OnClicked.AddDynamic(this, &ThisClass::OpenLobbyButtonClicked);
	if (SessionBackButton)        SessionBackButton->OnClicked.AddDynamic(this, &ThisClass::BackToHomeClicked);

	// Confirm
	if (ConfirmYesButton) ConfirmYesButton->OnClicked.AddDynamic(this, &ThisClass::ConfirmYesButtonClicked);
	if (ConfirmNoButton)  ConfirmNoButton->OnClicked.AddDynamic(this, &ThisClass::ConfirmNoButtonClicked);

	if (OptionsMenu) OptionsMenu->OnClosed.AddDynamic(this, &ThisClass::OnOptionsClosed);

	return true;
}

void UPauseMenu3::NativeOnInitialized()
{
	Super::NativeOnInitialized();

	// Bound for the widget's whole life, not per open: a privacy change or Open Lobby still
	// finishes (and Open Lobby still starts the session) when the menu closes before the reply
	if (UMultiplayerSessionsSubsystem* Sessions = GetSessions())
	{
		Sessions->MultiplayerOnUpdateSessionComplete.AddUniqueDynamic(this, &ThisClass::OnUpdateSession);
		Sessions->MultiplayerOnCreateSessionComplete.AddUniqueDynamic(this, &ThisClass::OnCreateSession);
		Sessions->MultiplayerOnSessionError.AddUniqueDynamic(this, &ThisClass::OnSessionError);
	}
}

void UPauseMenu3::NativeConstruct()
{
	Super::NativeConstruct();

	ButtonFXState.Setup(WidgetTree, ButtonFX);
}

void UPauseMenu3::NativeTick(const FGeometry& MyGeometry, float InDeltaTime)
{
	Super::NativeTick(MyGeometry, InDeltaTime);

	ButtonFXState.Tick(InDeltaTime);

	if (CurrentPanel && CurrentPanel == SessionPanel)
	{
		SessionRefreshTimer -= InDeltaTime;
		if (SessionRefreshTimer <= 0.f)
		{
			RefreshSessionPanel();
		}
	}
}

void UPauseMenu3::NativeDestruct()
{
	ButtonFXState.Reset();

	Super::NativeDestruct();
}

FReply UPauseMenu3::NativeOnKeyDown(const FGeometry& InGeometry, const FKeyEvent& InKeyEvent)
{
	// Start toggles the menu like Esc does
	if (AuraMenu::IsBackKey(InKeyEvent.GetKey(), true))
	{
		HandleBack();
		return FReply::Handled();
	}

	return Super::NativeOnKeyDown(InGeometry, InKeyEvent);
}

//
// Home
//
void UPauseMenu3::ResumeButtonClicked()
{
	CloseMenu();
}

void UPauseMenu3::CurrentSessionButtonClicked()
{
	SelectedPrivacy = EAuraSessionPrivacy::FriendsOnly;
	FAuraSessionInfo Info;
	if (GetSessions() && GetSessions()->GetCurrentSessionInfo(Info))
	{
		SelectedPrivacy = Info.Privacy;
	}

	SetSessionStatus(FText::GetEmpty());
	ShowPanel(SessionPanel);
	RefreshSessionPanel();
}

void UPauseMenu3::OptionsButtonClicked()
{
	if (UWidget* Panel = GetOptionsPanel())
	{
		ShowPanel(Panel);
		if (OptionsMenu)
		{
			OptionsMenu->OpenSettings();
		}
	}
}

void UPauseMenu3::LeaveSessionButtonClicked()
{
	ShowConfirm(LOCTEXT("LeaveTitle", "Leave session"),
		IsServer()
			? LOCTEXT("LeaveHostMessage", "Return to the main menu? You are the host: everyone else will be disconnected.")
			: LOCTEXT("LeaveMessage", "Return to the main menu?"),
		EPauseMenu3ConfirmAction::LeaveSession);
}

void UPauseMenu3::QuitGameButtonClicked()
{
	ShowConfirm(LOCTEXT("QuitTitle", "Quit game"),
		IsServer()
			? LOCTEXT("QuitHostMessage", "Quit to desktop? You are the host: everyone else will be disconnected.")
			: LOCTEXT("QuitMessage", "Quit to desktop?"),
		EPauseMenu3ConfirmAction::QuitGame);
}

//
// Current Session
//
void UPauseMenu3::CopyCodeButtonClicked()
{
	FAuraSessionInfo Info;
	if (GetSessions() && GetSessions()->GetCurrentSessionInfo(Info) && !Info.JoinCode.IsEmpty())
	{
		FPlatformApplicationMisc::ClipboardCopy(*Info.JoinCode);
		SetSessionStatus(LOCTEXT("CodeCopied", "Join code copied to the clipboard."));
	}
}

void UPauseMenu3::InviteFriendsButtonClicked()
{
	if (UMultiplayerSessionsSubsystem* Sessions = GetSessions())
	{
		Sessions->ShowSteamInviteUI();
	}
}

void UPauseMenu3::PrivacyPublicClicked()
{
	SetPrivacy(EAuraSessionPrivacy::Public);
}

void UPauseMenu3::PrivacyFriendsOnlyClicked()
{
	SetPrivacy(EAuraSessionPrivacy::FriendsOnly);
}

void UPauseMenu3::PrivacyCodeOnlyClicked()
{
	SetPrivacy(EAuraSessionPrivacy::CodeOnly);
}

void UPauseMenu3::SetPrivacy(EAuraSessionPrivacy Privacy)
{
	SelectedPrivacy = Privacy;

	UMultiplayerSessionsSubsystem* Sessions = GetSessions();
	FAuraHostSettings Settings;
	if (Sessions && Sessions->IsHostingSession() && Sessions->GetCurrentHostSettings(Settings))
	{
		// Running lobby: change it in place, the code and everyone in it stay
		Settings.Privacy = Privacy;
		bAwaitingUpdate = true;
		SetSessionStatus(LOCTEXT("UpdatingPrivacy", "Updating lobby..."));
		Sessions->UpdateHostSettings(Settings);
	}

	RefreshSessionPanel();
}

void UPauseMenu3::OpenLobbyButtonClicked()
{
	UMultiplayerSessionsSubsystem* Sessions = GetSessions();
	if (!Sessions || Sessions->IsInSession())
	{
		return;
	}

	FAuraHostSettings Settings = OpenLobbySettings;
	Settings.Privacy = SelectedPrivacy;
	if (Settings.LobbyName.IsEmpty())
	{
		const FString Nickname = Sessions->GetLocalPlayerNickname();
		if (!Nickname.IsEmpty())
		{
			Settings.LobbyName = FText::Format(LOCTEXT("DefaultLobbyName", "{0}'s lobby"), FText::FromString(Nickname)).ToString();
		}
	}

	if (OpenLobbyButton)
	{
		OpenLobbyButton->SetIsEnabled(false);
	}
	bAwaitingCreate = true;
	SetSessionStatus(LOCTEXT("OpeningLobby", "Opening lobby..."));
	// No travel: this world already listens, the session just lets others find and join it
	Sessions->CreateSessionWithSettings(Settings);
}

void UPauseMenu3::BackToHomeClicked()
{
	ShowPanel(PauseHomePanel);
}

void UPauseMenu3::RefreshSessionPanel()
{
	SessionRefreshTimer = SessionRefreshSeconds;

	UMultiplayerSessionsSubsystem* Sessions = GetSessions();
	FAuraSessionInfo Info;
	const bool bInSession = Sessions && Sessions->GetCurrentSessionInfo(Info);
	const bool bHosting = Sessions && Sessions->IsHostingSession();
	const UWorld* World = GetWorld();
	// A solo game is a listen server without a session, it can be opened to others
	const bool bCanOpenLobby = !bInSession && Sessions && Sessions->IsOnlineServiceAvailable() && World && World->GetNetMode() == NM_ListenServer;
	const EAuraSessionPrivacy ShownPrivacy = bInSession ? Info.Privacy : SelectedPrivacy;

	if (SessionCodeText)
	{
		SessionCodeText->SetText(bInSession && !Info.JoinCode.IsEmpty() ? FText::FromString(Info.JoinCode) : LOCTEXT("NoCode", "-"));
	}
	if (CopyCodeButton)      CopyCodeButton->SetIsEnabled(bInSession && !Info.JoinCode.IsEmpty());
	if (InviteFriendsButton) InviteFriendsButton->SetIsEnabled(bInSession);
	if (OpenLobbyButton)
	{
		OpenLobbyButton->SetVisibility(bCanOpenLobby ? ESlateVisibility::Visible : ESlateVisibility::Collapsed);
		OpenLobbyButton->SetIsEnabled(bCanOpenLobby && !bAwaitingCreate);
	}

	// Only the host changes privacy (or picks it before opening a solo game). The current choice is disabled = "selected".
	const bool bCanChoosePrivacy = (bHosting || bCanOpenLobby) && !bAwaitingUpdate;
	if (PrivacyPublicButton)      PrivacyPublicButton->SetIsEnabled(bCanChoosePrivacy && ShownPrivacy != EAuraSessionPrivacy::Public);
	if (PrivacyFriendsOnlyButton) PrivacyFriendsOnlyButton->SetIsEnabled(bCanChoosePrivacy && ShownPrivacy != EAuraSessionPrivacy::FriendsOnly);
	if (PrivacyCodeOnlyButton)    PrivacyCodeOnlyButton->SetIsEnabled(bCanChoosePrivacy && ShownPrivacy != EAuraSessionPrivacy::CodeOnly);

	if (PrivacyLabelText)
	{
		switch (ShownPrivacy)
		{
		case EAuraSessionPrivacy::Public:
			PrivacyLabelText->SetText(LOCTEXT("PrivacyPublic", "Public: listed in Browse Sessions, anyone can join."));
			break;
		case EAuraSessionPrivacy::FriendsOnly:
			PrivacyLabelText->SetText(LOCTEXT("PrivacyFriends", "Friends: Steam friends and invites only."));
			break;
		case EAuraSessionPrivacy::CodeOnly:
			PrivacyLabelText->SetText(LOCTEXT("PrivacyCode", "Code only: hidden from Browse Sessions, join with the code or an invite."));
			break;
		}
	}

	if (SessionInfoText)
	{
		const AGameStateBase* GameState = World ? World->GetGameState() : nullptr;
		const int32 NumPlayers = GameState ? GameState->PlayerArray.Num() : 1;
		if (bInSession)
		{
			const FString LobbyName = Info.LobbyName.IsEmpty() ? Info.HostName : Info.LobbyName;
			SessionInfoText->SetText(FText::Format(LOCTEXT("SessionInfo", "{0}  -  {1} / {2} players"),
				FText::FromString(LobbyName), FText::AsNumber(NumPlayers), FText::AsNumber(Info.MaxSlots)));
		}
		else if (bCanOpenLobby)
		{
			SessionInfoText->SetText(LOCTEXT("SoloInfo", "Solo game. Open the lobby to let friends join."));
		}
		else
		{
			SessionInfoText->SetText(LOCTEXT("OfflineInfo", "Offline game."));
		}
	}

	RefreshPlayerList();
}

void UPauseMenu3::RefreshPlayerList()
{
	const UWorld* World = GetWorld();
	const AGameStateBase* GameState = World ? World->GetGameState() : nullptr;
	if (!PlayerListPanel || !PlayerRowClass || !GameState)
	{
		return;
	}

	// Same players in the same order: just update names and pings, so gamepad focus on a row survives
	bool bSamePlayers = PlayerRows.Num() == GameState->PlayerArray.Num();
	for (int32 Index = 0; bSamePlayers && Index < PlayerRows.Num(); ++Index)
	{
		bSamePlayers = PlayerRows[Index] && PlayerRows[Index]->GetPlayerState() == GameState->PlayerArray[Index];
	}
	if (bSamePlayers)
	{
		for (USessionPlayerRow3* Row : PlayerRows)
		{
			Row->Refresh();
		}
		return;
	}

	PlayerListPanel->ClearChildren();
	PlayerRows.Reset();

	UMultiplayerSessionsSubsystem* Sessions = GetSessions();
	const APlayerController* OwningPlayer = GetOwningPlayer();
	const bool bServer = IsServer();

	for (APlayerState* PlayerState : GameState->PlayerArray)
	{
		if (!PlayerState)
		{
			continue;
		}

		const bool bIsLocal = OwningPlayer && OwningPlayer->PlayerState == PlayerState;
		// The server knows its own controller; a client asks the session who owns it
		const AController* Owner = PlayerState->GetOwningController();
		const bool bIsHostPlayer = bServer
			? (Owner && Owner->IsLocalController())
			: (Sessions && Sessions->IsSessionOwner(PlayerState->GetUniqueId()));
		const bool bCanModerate = bServer && !bIsHostPlayer && Cast<APlayerController>(Owner) != nullptr;

		if (USessionPlayerRow3* Row = CreateWidget<USessionPlayerRow3>(this, PlayerRowClass))
		{
			Row->Setup(this, PlayerState, bIsHostPlayer, bIsLocal, bCanModerate);
			PlayerListPanel->AddChild(Row);
			PlayerRows.Add(Row);
		}
	}
}

void UPauseMenu3::SetSessionStatus(const FText& Message)
{
	if (SessionStatusText)
	{
		SessionStatusText->SetText(Message);
	}
}

void UPauseMenu3::ShowPlayerProfile(APlayerState* PlayerState)
{
	if (UMultiplayerSessionsSubsystem* Sessions = GetSessions())
	{
		if (PlayerState)
		{
			Sessions->ShowPlayerProfile(PlayerState->GetUniqueId());
		}
	}
}

void UPauseMenu3::RequestKick(APlayerState* PlayerState, bool bBan)
{
	if (!PlayerState || !IsServer())
	{
		return;
	}

	PendingKickTarget = PlayerState;
	const FText Name = FText::FromString(PlayerState->GetPlayerName());
	if (bBan)
	{
		ShowConfirm(LOCTEXT("BanTitle", "Ban player"),
			FText::Format(LOCTEXT("BanMessage", "Ban {0}? They can't rejoin until you host a new lobby."), Name),
			EPauseMenu3ConfirmAction::BanPlayer);
	}
	else
	{
		ShowConfirm(LOCTEXT("KickTitle", "Kick player"),
			FText::Format(LOCTEXT("KickMessage", "Kick {0} from the lobby? They can join again."), Name),
			EPauseMenu3ConfirmAction::KickPlayer);
	}
}

//
// Confirm
//
void UPauseMenu3::ShowConfirm(const FText& Title, const FText& Message, EPauseMenu3ConfirmAction Action)
{
	PendingConfirmAction = Action;

	if (!ConfirmPanel)
	{
		// No dialog in the WBP: just do it
		ConfirmYesButtonClicked();
		return;
	}

	if (ConfirmTitleText)   ConfirmTitleText->SetText(Title);
	if (ConfirmMessageText) ConfirmMessageText->SetText(Message);

	if (CurrentPanel != ConfirmPanel)
	{
		PanelBeforeConfirm = CurrentPanel;
	}
	ShowPanel(ConfirmPanel);
}

void UPauseMenu3::ConfirmYesButtonClicked()
{
	const EPauseMenu3ConfirmAction Action = PendingConfirmAction;
	PendingConfirmAction = EPauseMenu3ConfirmAction::None;

	switch (Action)
	{
	case EPauseMenu3ConfirmAction::LeaveSession:
		LeaveSession();
		return;
	case EPauseMenu3ConfirmAction::QuitGame:
		if (APlayerController* PlayerController = GetOwningPlayer())
		{
			SendClientsHostLeft();
			UKismetSystemLibrary::QuitGame(GetWorld(), PlayerController, EQuitPreference::Quit, false);
		}
		return;
	case EPauseMenu3ConfirmAction::KickPlayer:
	case EPauseMenu3ConfirmAction::BanPlayer:
		if (APlayerState* Target = PendingKickTarget.Get())
		{
			const bool bBan = Action == EPauseMenu3ConfirmAction::BanPlayer;
			APlayerController* TargetController = Cast<APlayerController>(Target->GetOwningController());
			UMultiplayerSessionsSubsystem* Sessions = GetSessions();
			const bool bKicked = Sessions && Sessions->KickPlayer(TargetController, bBan ? BanReason : KickReason, bBan);
			SetSessionStatus(bKicked
				? FText::Format(bBan ? LOCTEXT("Banned", "{0} was banned.") : LOCTEXT("Kicked", "{0} was kicked."), FText::FromString(Target->GetPlayerName()))
				: LOCTEXT("KickFailed", "Couldn't remove that player."));
		}
		PendingKickTarget.Reset();
		break;
	case EPauseMenu3ConfirmAction::None:
		break;
	}

	ConfirmNoButtonClicked();
}

void UPauseMenu3::ConfirmNoButtonClicked()
{
	PendingConfirmAction = EPauseMenu3ConfirmAction::None;
	PendingKickTarget.Reset();
	ShowPanel(PanelBeforeConfirm ? PanelBeforeConfirm : PauseHomePanel);
	if (CurrentPanel == SessionPanel)
	{
		RefreshSessionPanel();
	}
}

void UPauseMenu3::SendClientsHostLeft()
{
	UWorld* World = GetWorld();
	UMultiplayerSessionsSubsystem* Sessions = GetSessions();
	if (!World || !Sessions || !IsServer())
	{
		return;
	}

	TArray<APlayerController*> Clients;
	for (FConstPlayerControllerIterator It = World->GetPlayerControllerIterator(); It; ++It)
	{
		APlayerController* PlayerController = It->Get();
		if (PlayerController && !PlayerController->IsLocalController())
		{
			Clients.Add(PlayerController);
		}
	}
	// Collected first: kicking destroys controllers, which would break the iterator
	for (APlayerController* Client : Clients)
	{
		Sessions->KickPlayer(Client, HostLeftReason, false);
	}
}

void UPauseMenu3::LeaveSession()
{
	SendClientsHostLeft();

	FString MapPath = MainMenuMapPath;
	if (MapPath.IsEmpty())
	{
		MapPath = UGameMapsSettings::GetGameDefaultMap();
	}

	if (UMultiplayerSessionsSubsystem* Sessions = GetSessions())
	{
		// Destroys the session first, so the next host / join from the main menu works
		Sessions->LeaveSessionAndOpenLevel(MapPath);
	}
	else if (APlayerController* PlayerController = GetOwningPlayer())
	{
		PlayerController->ClientTravel(MapPath, ETravelType::TRAVEL_Absolute);
	}
}

//
// Options
//
void UPauseMenu3::OnOptionsClosed()
{
	if (bMenuOpen && CurrentPanel && CurrentPanel == GetOptionsPanel())
	{
		ShowPanel(PauseHomePanel);
	}
}

//
// Subsystem callbacks
//
void UPauseMenu3::OnUpdateSession(bool bWasSuccessful)
{
	if (!bAwaitingUpdate)
	{
		return;
	}
	bAwaitingUpdate = false;

	SetSessionStatus(bWasSuccessful ? LOCTEXT("LobbyUpdated", "Lobby updated.") : LOCTEXT("LobbyUpdateFailed", "Couldn't change the lobby settings."));
	RefreshSessionPanel();
}

void UPauseMenu3::OnCreateSession(bool bWasSuccessful)
{
	if (!bAwaitingCreate)
	{
		return;
	}
	bAwaitingCreate = false;

	if (bWasSuccessful)
	{
		// What AMyGameMode::PostLogin does for a lobby hosted from the main menu
		if (UMultiplayerSessionsSubsystem* Sessions = GetSessions())
		{
			Sessions->StartSession();
		}
		SetSessionStatus(LOCTEXT("LobbyOpened", "Lobby open. Share the code or invite friends."));
	}
	else
	{
		SetSessionStatus(LOCTEXT("LobbyOpenFailed", "Couldn't open the lobby."));
	}
	RefreshSessionPanel();
}

void UPauseMenu3::OnSessionError(const FString& Message)
{
	bAwaitingCreate = false;
	bAwaitingUpdate = false;
	SetSessionStatus(FText::FromString(Message));
	if (CurrentPanel == SessionPanel)
	{
		RefreshSessionPanel();
	}
}

//
// Shared
//
void UPauseMenu3::ShowPanel(UWidget* PanelToShow)
{
	if (!PanelToShow)
	{
		return;
	}

	CurrentPanel = PanelToShow;

	if (MenuSwitcher && MenuSwitcher->HasChild(PanelToShow))
	{
		MenuSwitcher->SetActiveWidget(PanelToShow);
	}
	else if (!MenuSwitcher)
	{
		// Fallback without a WidgetSwitcher: plain visibility toggling
		for (UWidget* Panel : { PauseHomePanel, SessionPanel, GetOptionsPanel(), ConfirmPanel })
		{
			if (Panel)
			{
				Panel->SetVisibility(Panel == PanelToShow ? ESlateVisibility::Visible : ESlateVisibility::Collapsed);
			}
		}
	}

	if (!AuraMenu::FocusFirstControl(PanelToShow))
	{
		SetKeyboardFocus();
	}

	OnPanelChanged(PanelToShow);
}

void UPauseMenu3::HandleBack()
{
	if (!CurrentPanel || CurrentPanel == PauseHomePanel)
	{
		CloseMenu();
	}
	else if (CurrentPanel == ConfirmPanel)
	{
		ConfirmNoButtonClicked();
	}
	else if (CurrentPanel == GetOptionsPanel() && OptionsMenu)
	{
		OptionsMenu->HandleBack();
	}
	else
	{
		ShowPanel(PauseHomePanel);
	}
}

UWidget* UPauseMenu3::GetOptionsPanel() const
{
	return OptionsPanel ? OptionsPanel : static_cast<UWidget*>(OptionsMenu);
}

UMultiplayerSessionsSubsystem* UPauseMenu3::GetSessions() const
{
	const UGameInstance* GameInstance = GetGameInstance();
	return GameInstance ? GameInstance->GetSubsystem<UMultiplayerSessionsSubsystem>() : nullptr;
}

bool UPauseMenu3::IsServer() const
{
	const UWorld* World = GetWorld();
	return World && World->GetNetMode() != NM_Client;
}

#undef LOCTEXT_NAMESPACE
