// Fill out your copyright notice in the Description page of Project Settings.

#include "EOS/MainMenu3.h"
#include "EOS/SessionEntry3.h"
#include "EOS/MultiplayerSessionsSubsystem.h"
#include "UI/Settings/SettingsMenu3.h"
#include "Components/Button.h"
#include "Components/CheckBox.h"
#include "Components/ComboBoxString.h"
#include "Components/EditableTextBox.h"
#include "Components/PanelWidget.h"
#include "Components/ScrollBox.h"
#include "Components/TextBlock.h"
#include "Components/WidgetSwitcher.h"
#include "GeneralProjectSettings.h"
#include "HAL/PlatformApplicationMisc.h"
#include "Kismet/GameplayStatics.h"
#include "Kismet/KismetSystemLibrary.h"

#define LOCTEXT_NAMESPACE "MainMenu3"

namespace
{
	// Seconds the credits rest at the bottom before starting over
	constexpr float CreditsEndPauseSeconds = 3.f;
	constexpr int32 MaxLobbyNameLength = 32;
}

void UMainMenu3::MenuSetup(int32 NumberOfPublicConnections, FString TypeOfMatch, FString LobbyPath)
{
	LobbyMapPath = LobbyPath;
	PathToLobby = FString::Printf(TEXT("%s?listen"), *LobbyPath);
	NumPublicConnections = NumberOfPublicConnections;
	MatchType = TypeOfMatch;

	// Seed the settings the Create Session panel edits. Like Far Far West a new lobby starts
	// private (friends / invite / code), the host opens it to the public on purpose.
	PendingHostSettings.NumPublicConnections = NumberOfPublicConnections;
	PendingHostSettings.MatchType = TypeOfMatch;
	PendingHostSettings.Privacy = EAuraSessionPrivacy::FriendsOnly;
	PendingHostSettings.Difficulty = DefaultDifficulty;
	if (RuleSets.Num() > 0)
	{
		PendingHostSettings.Rules = RuleSets[0];
	}

	if (!IsInViewport())
	{
		AddToViewport();
	}
	SetVisibility(ESlateVisibility::Visible);
	SetIsFocusable(true);

	if (UWorld* World = GetWorld())
	{
		if (APlayerController* PlayerController = World->GetFirstPlayerController())
		{
			FInputModeUIOnly InputModeData;
			InputModeData.SetWidgetToFocus(TakeWidget());
			InputModeData.SetLockMouseToViewportBehavior(EMouseLockMode::DoNotLock);
			PlayerController->SetInputMode(InputModeData);
			PlayerController->SetShowMouseCursor(true);
		}
	}

	if (UGameInstance* GameInstance = GetGameInstance())
	{
		MultiplayerSessionsSubsystem = GameInstance->GetSubsystem<UMultiplayerSessionsSubsystem>();
	}

	if (MultiplayerSessionsSubsystem)
	{
		// MenuSetup can run twice (level blueprint + re-open), never bind twice
		MultiplayerSessionsSubsystem->MultiplayerOnSessionsFound.RemoveAll(this);
		MultiplayerSessionsSubsystem->MultiplayerOnJoinSessionComplete.RemoveAll(this);

		MultiplayerSessionsSubsystem->MultiplayerOnCreateSessionComplete.AddUniqueDynamic(this, &ThisClass::OnCreateSession);
		MultiplayerSessionsSubsystem->MultiplayerOnSessionsFound.AddUObject(this, &ThisClass::OnSessionsFound);
		MultiplayerSessionsSubsystem->MultiplayerOnJoinSessionComplete.AddUObject(this, &ThisClass::OnJoinSession);
		MultiplayerSessionsSubsystem->MultiplayerOnInviteAccepted.AddUniqueDynamic(this, &ThisClass::OnInviteAccepted);
		MultiplayerSessionsSubsystem->MultiplayerOnSessionError.AddUniqueDynamic(this, &ThisClass::OnSessionError);
		MultiplayerSessionsSubsystem->MultiplayerOnFindSessionsCancelled.AddUniqueDynamic(this, &ThisClass::OnFindSessionsCancelled);
	}

	FillStaticOptions();
	RefreshPrivacyLabel();
	RefreshOnlineStatus();

	if (VersionText)
	{
		const FString ProjectVersion = GetDefault<UGeneralProjectSettings>()->ProjectVersion;
		VersionText->SetText(FText::Format(LOCTEXT("Version", "v{0}"), FText::FromString(ProjectVersion)));
	}
	if (TutorialButton)
	{
		TutorialButton->SetVisibility(TutorialMapPath.IsEmpty() ? ESlateVisibility::Collapsed : ESlateVisibility::Visible);
	}

	// Why the last session ended (kicked, lost connection, banned...), shown once
	const FString PendingMessage = MultiplayerSessionsSubsystem ? MultiplayerSessionsSubsystem->ConsumePendingMenuMessage() : FString();

	ClearHistory();
	if (!PendingMessage.IsEmpty())
	{
		ShowPanel(HomePanel);
		ShowMessage(LOCTEXT("DisconnectedTitle", "Disconnected"), FText::FromString(PendingMessage));
	}
	else if (bShowTitleScreen && TitlePanel)
	{
		ShowPanel(TitlePanel);
	}
	else
	{
		ShowPanel(HomePanel);
	}
}

bool UMainMenu3::Initialize()
{
	if (!Super::Initialize())
	{
		return false;
	}

	// Home
	if (CreateSessionButton)  CreateSessionButton->OnClicked.AddDynamic(this, &ThisClass::CreateSessionButtonClicked);
	if (BrowseSessionsButton) BrowseSessionsButton->OnClicked.AddDynamic(this, &ThisClass::BrowseSessionsButtonClicked);
	if (TutorialButton)       TutorialButton->OnClicked.AddDynamic(this, &ThisClass::TutorialButtonClicked);
	if (OptionsButton)        OptionsButton->OnClicked.AddDynamic(this, &ThisClass::OptionsButtonClicked);
	if (CreditsButton)        CreditsButton->OnClicked.AddDynamic(this, &ThisClass::CreditsButtonClicked);
	if (QuitButton)           QuitButton->OnClicked.AddDynamic(this, &ThisClass::QuitButtonClicked);

	// Host
	if (PrivacyPublicButton)      PrivacyPublicButton->OnClicked.AddDynamic(this, &ThisClass::PrivacyPublicClicked);
	if (PrivacyFriendsOnlyButton) PrivacyFriendsOnlyButton->OnClicked.AddDynamic(this, &ThisClass::PrivacyFriendsOnlyClicked);
	if (PrivacyCodeOnlyButton)    PrivacyCodeOnlyButton->OnClicked.AddDynamic(this, &ThisClass::PrivacyCodeOnlyClicked);
	if (StartLobbyButton)         StartLobbyButton->OnClicked.AddDynamic(this, &ThisClass::StartLobbyButtonClicked);
	if (PlaySoloButton)           PlaySoloButton->OnClicked.AddDynamic(this, &ThisClass::PlaySoloButtonClicked);

	// Browse
	if (RefreshSessionsButton) RefreshSessionsButton->OnClicked.AddDynamic(this, &ThisClass::RefreshSessionsButtonClicked);
	if (QuickJoinButton)       QuickJoinButton->OnClicked.AddDynamic(this, &ThisClass::QuickJoinButtonClicked);
	if (JoinWithCodeButton)    JoinWithCodeButton->OnClicked.AddDynamic(this, &ThisClass::JoinWithCodeButtonClicked);
	if (FriendsButton)         FriendsButton->OnClicked.AddDynamic(this, &ThisClass::FriendsButtonClicked);
	for (UComboBoxString* Combo : { DistanceComboBox, DifficultyFilterComboBox, RulesFilterComboBox })
	{
		if (Combo) Combo->OnSelectionChanged.AddDynamic(this, &ThisClass::OnBrowseFilterChanged);
	}
	if (ShowFullLobbiesCheckBox) ShowFullLobbiesCheckBox->OnCheckStateChanged.AddDynamic(this, &ThisClass::OnShowFullLobbiesChanged);

	// Code
	if (ConfirmJoinCodeButton) ConfirmJoinCodeButton->OnClicked.AddDynamic(this, &ThisClass::ConfirmJoinCodeButtonClicked);
	if (PasteCodeButton)       PasteCodeButton->OnClicked.AddDynamic(this, &ThisClass::PasteCodeButtonClicked);
	if (JoinCodeTextBox)
	{
		JoinCodeTextBox->OnTextChanged.AddDynamic(this, &ThisClass::OnJoinCodeTextChanged);
		JoinCodeTextBox->OnTextCommitted.AddDynamic(this, &ThisClass::OnJoinCodeTextCommitted);
	}

	// Busy / Confirm
	if (CancelBusyButton) CancelBusyButton->OnClicked.AddDynamic(this, &ThisClass::CancelBusyButtonClicked);
	if (ConfirmYesButton) ConfirmYesButton->OnClicked.AddDynamic(this, &ThisClass::ConfirmYesButtonClicked);
	if (ConfirmNoButton)  ConfirmNoButton->OnClicked.AddDynamic(this, &ThisClass::ConfirmNoButtonClicked);

	// Every Back button does the same thing
	for (UButton* Back : { HostBackButton, BrowseBackButton, CodeBackButton, CreditsBackButton })
	{
		if (Back) Back->OnClicked.AddDynamic(this, &ThisClass::BackButtonClicked);
	}

	if (OptionsMenu) OptionsMenu->OnClosed.AddDynamic(this, &ThisClass::OnOptionsClosed);

	return true;
}

void UMainMenu3::NativeConstruct()
{
	Super::NativeConstruct();

	ButtonFXState.Setup(WidgetTree, ButtonFX);
}

void UMainMenu3::NativeTick(const FGeometry& MyGeometry, float InDeltaTime)
{
	Super::NativeTick(MyGeometry, InDeltaTime);

	ButtonFXState.Tick(InDeltaTime);

	if (CurrentPanel && CurrentPanel == TitlePanel && PressAnyKeyText)
	{
		// Slow pulse on "Press any key"
		TitleTime += InDeltaTime;
		PressAnyKeyText->SetRenderOpacity(0.55f + 0.45f * FMath::Sin(TitleTime * 3.f));
	}

	if (CurrentPanel && CurrentPanel == CreditsPanel)
	{
		TickCredits(InDeltaTime);
	}
}

void UMainMenu3::NativeDestruct()
{
	ButtonFXState.Reset();

	if (MultiplayerSessionsSubsystem)
	{
		MultiplayerSessionsSubsystem->MultiplayerOnCreateSessionComplete.RemoveDynamic(this, &ThisClass::OnCreateSession);
		MultiplayerSessionsSubsystem->MultiplayerOnSessionsFound.RemoveAll(this);
		MultiplayerSessionsSubsystem->MultiplayerOnJoinSessionComplete.RemoveAll(this);
		MultiplayerSessionsSubsystem->MultiplayerOnInviteAccepted.RemoveDynamic(this, &ThisClass::OnInviteAccepted);
		MultiplayerSessionsSubsystem->MultiplayerOnSessionError.RemoveDynamic(this, &ThisClass::OnSessionError);
		MultiplayerSessionsSubsystem->MultiplayerOnFindSessionsCancelled.RemoveDynamic(this, &ThisClass::OnFindSessionsCancelled);
	}

	Super::NativeDestruct();
}

FReply UMainMenu3::NativeOnKeyDown(const FGeometry& InGeometry, const FKeyEvent& InKeyEvent)
{
	if (CurrentPanel && CurrentPanel == TitlePanel)
	{
		LeaveTitleScreen();
		return FReply::Handled();
	}

	if (AuraMenu::IsBackKey(InKeyEvent.GetKey()))
	{
		HandleBack();
		return FReply::Handled();
	}

	return Super::NativeOnKeyDown(InGeometry, InKeyEvent);
}

FReply UMainMenu3::NativeOnMouseButtonDown(const FGeometry& InGeometry, const FPointerEvent& InMouseEvent)
{
	if (CurrentPanel && CurrentPanel == TitlePanel)
	{
		LeaveTitleScreen();
		return FReply::Handled();
	}

	return Super::NativeOnMouseButtonDown(InGeometry, InMouseEvent);
}

//
// Title
//
void UMainMenu3::LeaveTitleScreen()
{
	ShowPanel(HomePanel);
	// Back from Home asks to quit instead of returning to the title
	ClearHistory();
}

//
// Home
//
void UMainMenu3::CreateSessionButtonClicked()
{
	ShowPanel(HostPanel);
	RefreshPrivacyLabel();
}

void UMainMenu3::BrowseSessionsButtonClicked()
{
	// Searches below anyway
	bBrowseListStale = false;
	ShowPanel(BrowsePanel);
	RefreshSessionsButtonClicked();
}

void UMainMenu3::TutorialButtonClicked()
{
	if (!TutorialMapPath.IsEmpty())
	{
		ShowBusy(LOCTEXT("LoadingTutorial", "Loading tutorial..."), false);
		OpenLevelLeavingSession(TutorialMapPath);
	}
}

void UMainMenu3::OptionsButtonClicked()
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

void UMainMenu3::CreditsButtonClicked()
{
	if (CreditsScrollBox)
	{
		CreditsScrollBox->ScrollToStart();
	}
	CreditsEndPause = 0.f;
	ShowPanel(CreditsPanel);
}

void UMainMenu3::QuitButtonClicked()
{
	ShowConfirm(LOCTEXT("QuitTitle", "Quit"), LOCTEXT("QuitMessage", "Quit to desktop?"), EMainMenu3ConfirmAction::Quit);
}

void UMainMenu3::RefreshOnlineStatus()
{
	const bool bOnline = MultiplayerSessionsSubsystem && MultiplayerSessionsSubsystem->IsOnlineServiceAvailable();

	// Like Far Far West: without the online service, hosting and browsing are greyed out,
	// solo play and the tutorial still work
	if (BrowseSessionsButton) BrowseSessionsButton->SetIsEnabled(bOnline);
	if (StartLobbyButton)     StartLobbyButton->SetIsEnabled(bOnline);

	if (!OnlineStatusText)
	{
		return;
	}

	if (!bOnline)
	{
		OnlineStatusText->SetText(LOCTEXT("OfflineStatus", "Can't reach the online service. Solo play still works."));
		OnlineStatusText->SetColorAndOpacity(FSlateColor(FLinearColor(0.9f, 0.15f, 0.1f, 1.f)));
		return;
	}

	const FString Nickname = MultiplayerSessionsSubsystem->GetLocalPlayerNickname();
	const FString Service = MultiplayerSessionsSubsystem->GetOnlineServiceName();
	OnlineStatusText->SetText(Nickname.IsEmpty()
		? FText::Format(LOCTEXT("OnlineStatusNoName", "Online ({0})"), FText::FromString(Service))
		: FText::Format(LOCTEXT("OnlineStatus", "Online as {0} ({1})"), FText::FromString(Nickname), FText::FromString(Service)));
}

//
// Host panel
//
void UMainMenu3::PrivacyPublicClicked()
{
	PendingHostSettings.Privacy = EAuraSessionPrivacy::Public;
	RefreshPrivacyLabel();
}

void UMainMenu3::PrivacyFriendsOnlyClicked()
{
	PendingHostSettings.Privacy = EAuraSessionPrivacy::FriendsOnly;
	RefreshPrivacyLabel();
}

void UMainMenu3::PrivacyCodeOnlyClicked()
{
	PendingHostSettings.Privacy = EAuraSessionPrivacy::CodeOnly;
	RefreshPrivacyLabel();
}

void UMainMenu3::RefreshPrivacyLabel()
{
	// The chosen option's button is disabled, so its Disabled style reads as "selected"
	if (PrivacyPublicButton)      PrivacyPublicButton->SetIsEnabled(PendingHostSettings.Privacy != EAuraSessionPrivacy::Public);
	if (PrivacyFriendsOnlyButton) PrivacyFriendsOnlyButton->SetIsEnabled(PendingHostSettings.Privacy != EAuraSessionPrivacy::FriendsOnly);
	if (PrivacyCodeOnlyButton)    PrivacyCodeOnlyButton->SetIsEnabled(PendingHostSettings.Privacy != EAuraSessionPrivacy::CodeOnly);

	if (!PrivacyLabelText)
	{
		return;
	}

	switch (PendingHostSettings.Privacy)
	{
	case EAuraSessionPrivacy::Public:
		PrivacyLabelText->SetText(LOCTEXT("PrivacyPublic", "Public: listed in Browse Sessions, anyone can join."));
		break;
	case EAuraSessionPrivacy::FriendsOnly:
		PrivacyLabelText->SetText(LOCTEXT("PrivacyFriends", "Solo or with friends: Steam friends and invites only. Open it to everyone later from the pause menu."));
		break;
	case EAuraSessionPrivacy::CodeOnly:
		PrivacyLabelText->SetText(LOCTEXT("PrivacyCode", "Code only: hidden from Browse Sessions, join with your code or an invite."));
		break;
	}
}

void UMainMenu3::ReadHostSettingsFromWidgets()
{
	if (MaxPlayersComboBox)
	{
		const int32 Index = MaxPlayersComboBox->GetSelectedIndex();
		if (MaxPlayerChoices.IsValidIndex(Index))
		{
			PendingHostSettings.NumPublicConnections = MaxPlayerChoices[Index];
		}
	}
	if (HostDifficultyComboBox && HostDifficultyComboBox->GetSelectedIndex() >= 0)
	{
		PendingHostSettings.Difficulty = HostDifficultyComboBox->GetSelectedIndex();
	}
	if (HostRulesComboBox && !HostRulesComboBox->GetSelectedOption().IsEmpty())
	{
		PendingHostSettings.Rules = HostRulesComboBox->GetSelectedOption();
	}
	if (LobbyNameTextBox)
	{
		PendingHostSettings.LobbyName = LobbyNameTextBox->GetText().ToString().TrimStartAndEnd().Left(MaxLobbyNameLength);
	}
	if (PendingHostSettings.LobbyName.IsEmpty() && MultiplayerSessionsSubsystem)
	{
		const FString Nickname = MultiplayerSessionsSubsystem->GetLocalPlayerNickname();
		if (!Nickname.IsEmpty())
		{
			PendingHostSettings.LobbyName = FText::Format(LOCTEXT("DefaultLobbyName", "{0}'s lobby"), FText::FromString(Nickname)).ToString().Left(MaxLobbyNameLength);
		}
	}
}

void UMainMenu3::StartLobbyButtonClicked()
{
	if (!MultiplayerSessionsSubsystem)
	{
		return;
	}

	ReadHostSettingsFromWidgets();

	bAwaitingCreate = true;
	ShowBusy(LOCTEXT("CreatingLobby", "Creating lobby..."), false);
	MultiplayerSessionsSubsystem->CreateSessionWithSettings(PendingHostSettings);
}

void UMainMenu3::PlaySoloButtonClicked()
{
	// A listen server with no online session: the pause menu's Current Session tab can still
	// create one later and let friends in
	ShowBusy(LOCTEXT("LoadingSolo", "Loading..."), false);
	OpenLevelLeavingSession(PathToLobby);
}

//
// Browse panel
//
void UMainMenu3::RefreshSessionsButtonClicked()
{
	if (!MultiplayerSessionsSubsystem)
	{
		return;
	}

	if (MultiplayerSessionsSubsystem->IsSearchInProgress())
	{
		// The filters changed mid-search: search again with them once this one reports back
		if (QueuedSearch == EMainMenu3QueuedSearch::None)
		{
			QueuedSearch = EMainMenu3QueuedSearch::Refresh;
		}
		return;
	}

	SetBrowseButtonsEnabled(false);
	bBrowseListStale = false;
	if (SessionListPanel)
	{
		SessionListPanel->ClearChildren();
	}
	if (SessionListHintText)
	{
		SessionListHintText->SetText(LOCTEXT("Searching", "Searching for lobbies..."));
		SessionListHintText->SetVisibility(ESlateVisibility::HitTestInvisible);
	}

	bBrowseSearchPending = true;
	MultiplayerSessionsSubsystem->FindSessionsFiltered(BuildFilterFromWidgets());
}

void UMainMenu3::QuickJoinButtonClicked()
{
	StartQuickJoin();
}

void UMainMenu3::JoinWithCodeButtonClicked()
{
	if (JoinCodeTextBox)
	{
		JoinCodeTextBox->SetText(FText::GetEmpty());
	}
	if (ConfirmJoinCodeButton)
	{
		ConfirmJoinCodeButton->SetIsEnabled(false);
	}
	ShowPanel(CodePanel);
	if (JoinCodeTextBox)
	{
		JoinCodeTextBox->SetKeyboardFocus();
	}
}

void UMainMenu3::FriendsButtonClicked()
{
	if (MultiplayerSessionsSubsystem)
	{
		MultiplayerSessionsSubsystem->ShowFriendsUI();
	}
}

void UMainMenu3::OnBrowseFilterChanged(FString SelectedItem, ESelectInfo::Type SelectionType)
{
	// FillStaticOptions selecting the defaults is not a player change
	if (SelectionType != ESelectInfo::Direct && CurrentPanel == BrowsePanel)
	{
		RefreshSessionsButtonClicked();
	}
}

void UMainMenu3::OnShowFullLobbiesChanged(bool bIsChecked)
{
	if (CurrentPanel == BrowsePanel)
	{
		RefreshSessionsButtonClicked();
	}
}

FAuraSessionFilter UMainMenu3::BuildFilterFromWidgets() const
{
	FAuraSessionFilter Filter;

	// Option order matches EAuraSearchDistance, see FillStaticOptions
	if (DistanceComboBox && DistanceComboBox->GetSelectedIndex() >= 0)
	{
		Filter.Distance = static_cast<EAuraSearchDistance>(FMath::Clamp(DistanceComboBox->GetSelectedIndex(), 0, static_cast<int32>(EAuraSearchDistance::Worldwide)));
	}

	// Index 0 is "Any"
	if (DifficultyFilterComboBox)
	{
		const int32 Index = DifficultyFilterComboBox->GetSelectedIndex();
		Filter.Difficulty = Index > 0 ? Index - 1 : -1;
	}
	if (RulesFilterComboBox)
	{
		const int32 Index = RulesFilterComboBox->GetSelectedIndex();
		Filter.Rules = Index > 0 ? RulesFilterComboBox->GetSelectedOption() : FString();
	}

	Filter.bOnlyJoinable = !(ShowFullLobbiesCheckBox && ShowFullLobbiesCheckBox->IsChecked());
	Filter.MaxSearchResults = 10000;
	return Filter;
}

void UMainMenu3::RebuildSessionList(const TArray<FAuraSessionInfo>& SessionInfos)
{
	if (!SessionListPanel)
	{
		return;
	}

	SessionListPanel->ClearChildren();

	if (!SessionEntryClass)
	{
		return;
	}

	for (const FAuraSessionInfo& Info : SessionInfos)
	{
		if (USessionEntry3* Entry = CreateWidget<USessionEntry3>(this, SessionEntryClass))
		{
			Entry->Setup(this, Info);
			SessionListPanel->AddChild(Entry);
		}
	}
}

void UMainMenu3::SetBrowseButtonsEnabled(bool bEnabled)
{
	if (RefreshSessionsButton)
	{
		RefreshSessionsButton->SetIsEnabled(bEnabled);
	}
}

void UMainMenu3::JoinLobbyByIndex(int32 ResultIndex)
{
	if (!MultiplayerSessionsSubsystem)
	{
		return;
	}

	bAwaitingJoin = true;
	ShowBusy(LOCTEXT("JoiningLobby", "Joining lobby..."), false);
	MultiplayerSessionsSubsystem->JoinCachedSession(ResultIndex);
}

//
// Code panel
//
FString UMainMenu3::SanitizeJoinCode(const FString& Raw)
{
	FString Code;
	for (const TCHAR Character : Raw.ToUpper())
	{
		if (UMultiplayerSessionsSubsystem::IsJoinCodeCharacter(Character))
		{
			Code.AppendChar(Character);
		}
	}
	return Code.Left(UMultiplayerSessionsSubsystem::JoinCodeLength);
}

bool UMainMenu3::IsJoinCodeComplete() const
{
	return JoinCodeTextBox && JoinCodeTextBox->GetText().ToString().Len() == UMultiplayerSessionsSubsystem::JoinCodeLength;
}

void UMainMenu3::OnJoinCodeTextChanged(const FText& Text)
{
	// Upper case, code letters only, capped at the code length. Setting the text fires this
	// again with the clean code, which then matches and stops.
	const FString Raw = Text.ToString();
	const FString Clean = SanitizeJoinCode(Raw);
	if (JoinCodeTextBox && !Clean.Equals(Raw, ESearchCase::CaseSensitive))
	{
		JoinCodeTextBox->SetText(FText::FromString(Clean));
	}

	// Confirm stays disabled until the whole code is typed
	if (ConfirmJoinCodeButton)
	{
		ConfirmJoinCodeButton->SetIsEnabled(Clean.Len() == UMultiplayerSessionsSubsystem::JoinCodeLength);
	}
}

void UMainMenu3::OnJoinCodeTextCommitted(const FText& Text, ETextCommit::Type CommitMethod)
{
	if (CommitMethod == ETextCommit::OnEnter && IsJoinCodeComplete())
	{
		ConfirmJoinCodeButtonClicked();
	}
}

void UMainMenu3::PasteCodeButtonClicked()
{
	FString Clipboard;
	FPlatformApplicationMisc::ClipboardPaste(Clipboard);
	if (JoinCodeTextBox)
	{
		JoinCodeTextBox->SetText(FText::FromString(SanitizeJoinCode(Clipboard)));
	}
}

void UMainMenu3::ConfirmJoinCodeButtonClicked()
{
	if (!JoinCodeTextBox || !IsJoinCodeComplete())
	{
		SetStatus(FText::Format(LOCTEXT("CodeIncomplete", "Join codes are {0} characters long."), FText::AsNumber(UMultiplayerSessionsSubsystem::JoinCodeLength)));
		return;
	}

	StartCodeLookup(JoinCodeTextBox->GetText().ToString());
}

//
// Searches that take over the screen
//
void UMainMenu3::StartCodeLookup(const FString& Code)
{
	if (!MultiplayerSessionsSubsystem)
	{
		return;
	}

	ShowBusy(LOCTEXT("LookingUpCode", "Looking for that lobby..."), true);

	if (MultiplayerSessionsSubsystem->IsSearchInProgress())
	{
		QueuedSearch = EMainMenu3QueuedSearch::CodeLookup;
		QueuedJoinCode = Code;
		return;
	}

	bAwaitingCodeLookup = true;
	MultiplayerSessionsSubsystem->LookupSessionByCode(Code);
}

void UMainMenu3::StartQuickJoin()
{
	if (!MultiplayerSessionsSubsystem)
	{
		return;
	}

	ShowBusy(LOCTEXT("QuickJoining", "Looking for an open lobby..."), true);

	if (MultiplayerSessionsSubsystem->IsSearchInProgress())
	{
		QueuedSearch = EMainMenu3QueuedSearch::QuickJoin;
		return;
	}

	bAwaitingQuickJoin = true;
	MultiplayerSessionsSubsystem->QuickJoin(BuildFilterFromWidgets());
}

void UMainMenu3::RunQueuedSearch()
{
	const EMainMenu3QueuedSearch Queued = QueuedSearch;
	QueuedSearch = EMainMenu3QueuedSearch::None;

	switch (Queued)
	{
	case EMainMenu3QueuedSearch::Refresh:
		if (CurrentPanel == BrowsePanel || PanelHistory.Contains(BrowsePanel))
		{
			RefreshSessionsButtonClicked();
		}
		break;
	case EMainMenu3QueuedSearch::CodeLookup:
		StartCodeLookup(QueuedJoinCode);
		break;
	case EMainMenu3QueuedSearch::QuickJoin:
		StartQuickJoin();
		break;
	case EMainMenu3QueuedSearch::None:
		break;
	}
}

//
// Busy panel
//
void UMainMenu3::ShowBusy(const FText& Message, bool bCancellable)
{
	if (BusyText)
	{
		BusyText->SetText(Message);
	}
	if (CancelBusyButton)
	{
		CancelBusyButton->SetVisibility(bCancellable ? ESlateVisibility::Visible : ESlateVisibility::Collapsed);
	}

	if (BusyPanel)
	{
		ShowPanel(BusyPanel);
	}
	else
	{
		SetStatus(Message);
	}
}

void UMainMenu3::CancelBusyButtonClicked()
{
	if (QueuedSearch == EMainMenu3QueuedSearch::CodeLookup || QueuedSearch == EMainMenu3QueuedSearch::QuickJoin)
	{
		// Never started, the running search is the browse list's
		QueuedSearch = EMainMenu3QueuedSearch::None;
	}
	else if ((bAwaitingCodeLookup || bAwaitingQuickJoin) && MultiplayerSessionsSubsystem)
	{
		bAwaitingCodeLookup = false;
		bAwaitingQuickJoin = false;
		MultiplayerSessionsSubsystem->CancelFindSessions();
	}

	GoBack();
}

//
// Confirm panel
//
void UMainMenu3::ShowConfirm(const FText& Title, const FText& Message, EMainMenu3ConfirmAction Action)
{
	PendingConfirmAction = Action;

	if (ConfirmTitleText)   ConfirmTitleText->SetText(Title);
	if (ConfirmMessageText) ConfirmMessageText->SetText(Message);
	// A message (no action) only needs OK
	if (ConfirmNoButton)    ConfirmNoButton->SetVisibility(Action == EMainMenu3ConfirmAction::None ? ESlateVisibility::Collapsed : ESlateVisibility::Visible);
	if (ConfirmYesText)     ConfirmYesText->SetText(Action == EMainMenu3ConfirmAction::None ? LOCTEXT("Ok", "OK") : LOCTEXT("Yes", "Yes"));

	if (ConfirmPanel)
	{
		ShowPanel(ConfirmPanel);
	}
	else
	{
		// No dialog in the WBP: messages go to the status line, questions answer themselves "no"
		SetStatus(Message.IsEmpty() ? Title : Message);
		PendingConfirmAction = EMainMenu3ConfirmAction::None;
		if (CurrentPanel && CurrentPanel == BusyPanel)
		{
			GoBack();
		}
	}
}

void UMainMenu3::ShowMessage(const FText& Title, const FText& Message)
{
	ShowConfirm(Title, Message, EMainMenu3ConfirmAction::None);
}

void UMainMenu3::ConfirmYesButtonClicked()
{
	const EMainMenu3ConfirmAction Action = PendingConfirmAction;
	PendingConfirmAction = EMainMenu3ConfirmAction::None;

	switch (Action)
	{
	case EMainMenu3ConfirmAction::Quit:
		if (APlayerController* PlayerController = GetOwningPlayer())
		{
			UKismetSystemLibrary::QuitGame(GetWorld(), PlayerController, EQuitPreference::Quit, false);
		}
		break;
	case EMainMenu3ConfirmAction::JoinLobby:
		JoinLobbyByIndex(PendingJoinIndex);
		break;
	case EMainMenu3ConfirmAction::None:
		GoBack();
		break;
	}
}

void UMainMenu3::ConfirmNoButtonClicked()
{
	PendingConfirmAction = EMainMenu3ConfirmAction::None;
	GoBack();
}

//
// Options / Credits
//
void UMainMenu3::OnOptionsClosed()
{
	if (CurrentPanel && CurrentPanel == GetOptionsPanel())
	{
		GoBack();
	}
}

void UMainMenu3::BackButtonClicked()
{
	GoBack();
}

void UMainMenu3::TickCredits(float DeltaTime)
{
	if (!CreditsScrollBox)
	{
		return;
	}

	const float End = CreditsScrollBox->GetScrollOffsetOfEnd();
	const float Offset = CreditsScrollBox->GetScrollOffset();
	if (Offset < End)
	{
		CreditsScrollBox->SetScrollOffset(FMath::Min(Offset + CreditsScrollSpeed * DeltaTime, End));
		return;
	}

	// Rest at the bottom, then roll again
	CreditsEndPause += DeltaTime;
	if (CreditsEndPause >= CreditsEndPauseSeconds)
	{
		CreditsEndPause = 0.f;
		CreditsScrollBox->ScrollToStart();
	}
}

//
// Panel switching
//
TArray<UWidget*> UMainMenu3::GetAllPanels() const
{
	return { TitlePanel, HomePanel, HostPanel, BrowsePanel, CodePanel, BusyPanel, ConfirmPanel, GetOptionsPanel(), CreditsPanel };
}

UWidget* UMainMenu3::GetOptionsPanel() const
{
	return OptionsPanel ? OptionsPanel : static_cast<UWidget*>(OptionsMenu);
}

bool UMainMenu3::IsOverlayPanel(const UWidget* Panel) const
{
	return Panel && (Panel == BusyPanel || Panel == ConfirmPanel || Panel == TitlePanel);
}

void UMainMenu3::ShowPanel(UWidget* PanelToShow)
{
	if (!PanelToShow)
	{
		return;
	}

	// Remember where we came from, overlays excluded so closing one lands on the screen below
	if (CurrentPanel && CurrentPanel != PanelToShow && !IsOverlayPanel(CurrentPanel))
	{
		PanelHistory.Add(CurrentPanel);
	}
	// Re-opening a screen that is already on the stack trims back to it, no loops
	const int32 ExistingIndex = PanelHistory.Find(PanelToShow);
	if (ExistingIndex != INDEX_NONE)
	{
		PanelHistory.SetNum(ExistingIndex);
	}

	ActivatePanel(PanelToShow);
}

void UMainMenu3::ActivatePanel(UWidget* Panel)
{
	if (!Panel)
	{
		return;
	}

	CurrentPanel = Panel;

	// Busy / Confirm placed outside the switcher float on top of the current screen
	for (UWidget* Overlay : { BusyPanel, ConfirmPanel })
	{
		if (Overlay && !(MenuSwitcher && MenuSwitcher->HasChild(Overlay)))
		{
			Overlay->SetVisibility(Overlay == Panel ? ESlateVisibility::Visible : ESlateVisibility::Collapsed);
		}
	}

	if (Panel == BrowsePanel && bBrowseListStale)
	{
		RefreshSessionsButtonClicked();
	}

	if (MenuSwitcher && MenuSwitcher->HasChild(Panel))
	{
		MenuSwitcher->SetActiveWidget(Panel);
	}
	else if (!MenuSwitcher)
	{
		// Fallback for menus built before a WidgetSwitcher exists: plain visibility toggling.
		for (UWidget* Other : GetAllPanels())
		{
			if (Other && Other != BusyPanel && Other != ConfirmPanel)
			{
				Other->SetVisibility(Other == Panel ? ESlateVisibility::Visible : ESlateVisibility::Collapsed);
			}
		}
	}

	// Gamepad / keyboard: land on the first control, or keep focus on the menu so Esc works
	if (Panel == TitlePanel || !AuraMenu::FocusFirstControl(Panel))
	{
		SetKeyboardFocus();
	}

	OnPanelChanged(Panel);
}

void UMainMenu3::GoBack()
{
	UWidget* Previous = nullptr;
	while (!Previous && PanelHistory.Num() > 0)
	{
		Previous = PanelHistory.Pop();
	}

	if (!Previous)
	{
		Previous = HomePanel;
	}
	if (Previous && Previous != CurrentPanel)
	{
		ActivatePanel(Previous);
	}
}

void UMainMenu3::ClearHistory()
{
	PanelHistory.Reset();
}

void UMainMenu3::HandleBack()
{
	if (!CurrentPanel)
	{
		return;
	}

	if (CurrentPanel == ConfirmPanel)
	{
		// OK on a message, No on a question
		if (PendingConfirmAction == EMainMenu3ConfirmAction::None)
		{
			ConfirmYesButtonClicked();
		}
		else
		{
			ConfirmNoButtonClicked();
		}
	}
	else if (CurrentPanel == BusyPanel)
	{
		if (CancelBusyButton && CancelBusyButton->IsVisible())
		{
			CancelBusyButtonClicked();
		}
	}
	else if (CurrentPanel == GetOptionsPanel() && OptionsMenu)
	{
		OptionsMenu->HandleBack();
	}
	else if (CurrentPanel == HomePanel)
	{
		QuitButtonClicked();
	}
	else
	{
		GoBack();
	}
}

void UMainMenu3::SetStatus(const FText& Message)
{
	if (StatusText)
	{
		StatusText->SetText(Message);
	}
}

void UMainMenu3::FillStaticOptions()
{
	if (MaxPlayersComboBox)
	{
		MaxPlayersComboBox->ClearOptions();
		for (const int32 Count : MaxPlayerChoices)
		{
			MaxPlayersComboBox->AddOption(FString::FromInt(Count));
		}
		const int32 Preselect = MaxPlayerChoices.Find(NumPublicConnections);
		MaxPlayersComboBox->SetSelectedIndex(Preselect != INDEX_NONE ? Preselect : MaxPlayerChoices.Num() - 1);
	}

	if (HostDifficultyComboBox)
	{
		HostDifficultyComboBox->ClearOptions();
		for (const FString& Name : DifficultyNames)
		{
			HostDifficultyComboBox->AddOption(Name);
		}
		HostDifficultyComboBox->SetSelectedIndex(FMath::Clamp(DefaultDifficulty, 0, FMath::Max(DifficultyNames.Num() - 1, 0)));
	}

	if (HostRulesComboBox)
	{
		HostRulesComboBox->ClearOptions();
		for (const FString& Rules : RuleSets)
		{
			HostRulesComboBox->AddOption(Rules);
		}
		HostRulesComboBox->SetSelectedIndex(0);
	}

	if (DistanceComboBox)
	{
		// Same order as EAuraSearchDistance
		DistanceComboBox->ClearOptions();
		DistanceComboBox->AddOption(LOCTEXT("DistanceClose", "Close").ToString());
		DistanceComboBox->AddOption(LOCTEXT("DistanceMedium", "Medium").ToString());
		DistanceComboBox->AddOption(LOCTEXT("DistanceFar", "Far").ToString());
		DistanceComboBox->AddOption(LOCTEXT("DistanceWorldwide", "Worldwide").ToString());
		DistanceComboBox->SetSelectedIndex(static_cast<int32>(EAuraSearchDistance::Worldwide));
	}

	const FString AnyOption = LOCTEXT("Any", "Any").ToString();
	if (DifficultyFilterComboBox)
	{
		DifficultyFilterComboBox->ClearOptions();
		DifficultyFilterComboBox->AddOption(AnyOption);
		for (const FString& Name : DifficultyNames)
		{
			DifficultyFilterComboBox->AddOption(Name);
		}
		DifficultyFilterComboBox->SetSelectedIndex(0);
	}

	if (RulesFilterComboBox)
	{
		RulesFilterComboBox->ClearOptions();
		RulesFilterComboBox->AddOption(AnyOption);
		for (const FString& Rules : RuleSets)
		{
			RulesFilterComboBox->AddOption(Rules);
		}
		RulesFilterComboBox->SetSelectedIndex(0);
	}

	if (LobbyNameTextBox && MultiplayerSessionsSubsystem)
	{
		const FString Nickname = MultiplayerSessionsSubsystem->GetLocalPlayerNickname();
		if (!Nickname.IsEmpty())
		{
			LobbyNameTextBox->SetHintText(FText::Format(LOCTEXT("DefaultLobbyName", "{0}'s lobby"), FText::FromString(Nickname)));
		}
	}
}

FText UMainMenu3::GetDifficultyName(int32 Difficulty) const
{
	if (DifficultyNames.IsValidIndex(Difficulty))
	{
		return FText::FromString(DifficultyNames[Difficulty]);
	}
	return FText::Format(LOCTEXT("DifficultyNumber", "Difficulty {0}"), FText::AsNumber(Difficulty));
}

void UMainMenu3::OpenLevelLeavingSession(const FString& LevelPath)
{
	if (MultiplayerSessionsSubsystem)
	{
		// Drops a session left over from an earlier lobby first, or the next host / join fails
		MultiplayerSessionsSubsystem->LeaveSessionAndOpenLevel(LevelPath);
	}
	else
	{
		UGameplayStatics::OpenLevel(this, FName(*LevelPath));
	}
}

//
// Subsystem callbacks
//
void UMainMenu3::OnCreateSession(bool bWasSuccessful)
{
	if (!bAwaitingCreate)
	{
		return;
	}
	bAwaitingCreate = false;

	if (bWasSuccessful)
	{
		ShowBusy(LOCTEXT("LoadingLobby", "Loading lobby..."), false);
		if (UWorld* World = GetWorld())
		{
			World->ServerTravel(PathToLobby);
		}
	}
	else
	{
		ShowMessage(LOCTEXT("CreateFailedTitle", "Couldn't create lobby"), LOCTEXT("CreateFailed", "The lobby could not be created. Check your connection and try again."));
	}
}

void UMainMenu3::OnSessionsFound(const TArray<FAuraSessionInfo>& SessionInfos, bool bWasSuccessful)
{
	if (bAwaitingCodeLookup)
	{
		bAwaitingCodeLookup = false;

		// The lookup replaced the cached results the browse rows' Join buttons index into
		if (SessionListPanel)
		{
			SessionListPanel->ClearChildren();
		}
		bBrowseListStale = true;

		if (SessionInfos.Num() == 0)
		{
			ShowMessage(LOCTEXT("CodeNotFoundTitle", "Lobby not found"),
				LOCTEXT("CodeNotFound", "No lobby uses that code. Hosts get a new code every time they create a lobby."));
			return;
		}

		const FAuraSessionInfo& Info = SessionInfos[0];
		if (Info.OpenSlots <= 0)
		{
			ShowMessage(LOCTEXT("LobbyFullTitle", "Lobby full"), LOCTEXT("LobbyFull", "That lobby is full."));
			return;
		}

		// Far Far West asks before joining a code's lobby
		PendingJoinIndex = Info.ResultIndex;
		const FText LobbyName = FText::FromString(Info.LobbyName.IsEmpty() ? Info.HostName : Info.LobbyName);
		const FText Message = FText::Format(
			LOCTEXT("JoinCodeConfirm", "Join {0}?\nHost: {1}\nPlayers: {2} / {3}\nDifficulty: {4}\nPing: {5} ms"),
			LobbyName, FText::FromString(Info.HostName), FText::AsNumber(Info.MaxSlots - Info.OpenSlots), FText::AsNumber(Info.MaxSlots),
			GetDifficultyName(Info.Difficulty), FText::AsNumber(Info.PingInMs));
		ShowConfirm(LOCTEXT("JoinCodeConfirmTitle", "Join lobby?"), Message, EMainMenu3ConfirmAction::JoinLobby);
		return;
	}

	if (bAwaitingQuickJoin)
	{
		bAwaitingQuickJoin = false;
		RebuildSessionList(SessionInfos);

		// The subsystem now joins the best open lobby, or reports "none found" as an error
		const bool bAnyOpen = SessionInfos.ContainsByPredicate([](const FAuraSessionInfo& Info) { return Info.OpenSlots > 0; });
		if (bAnyOpen)
		{
			bAwaitingJoin = true;
			ShowBusy(LOCTEXT("JoiningLobby", "Joining lobby..."), false);
		}
		return;
	}

	// Browse list
	bBrowseSearchPending = false;
	SetBrowseButtonsEnabled(true);
	RebuildSessionList(SessionInfos);
	OnLobbyListUpdated(SessionInfos);

	if (SessionListHintText)
	{
		if (!bWasSuccessful)
		{
			SessionListHintText->SetText(LOCTEXT("SearchFailed", "Couldn't get the lobby list. Try Refresh."));
		}
		else if (SessionInfos.Num() == 0)
		{
			SessionListHintText->SetText(LOCTEXT("NoLobbies", "No lobbies found. Create one, or change the filters."));
		}
		SessionListHintText->SetVisibility(SessionInfos.Num() == 0 ? ESlateVisibility::HitTestInvisible : ESlateVisibility::Collapsed);
	}
	SetStatus(bWasSuccessful
		? FText::Format(LOCTEXT("FoundLobbies", "Found {0} {0}|plural(one=lobby,other=lobbies)."), FText::AsNumber(SessionInfos.Num()))
		: FText::GetEmpty());

	RunQueuedSearch();
}

void UMainMenu3::OnJoinSession(EOnJoinSessionCompleteResult::Type Result)
{
	bAwaitingJoin = false;

	FText Reason;
	switch (Result)
	{
	case EOnJoinSessionCompleteResult::Success:
		ShowBusy(LOCTEXT("Connecting", "Connecting to the host..."), false);
		if (MultiplayerSessionsSubsystem)
		{
			MultiplayerSessionsSubsystem->TravelToJoinedSession();
		}
		return;
	case EOnJoinSessionCompleteResult::SessionIsFull:
		Reason = LOCTEXT("JoinFull", "That lobby is full.");
		break;
	case EOnJoinSessionCompleteResult::SessionDoesNotExist:
		Reason = LOCTEXT("JoinGone", "That lobby no longer exists.");
		break;
	case EOnJoinSessionCompleteResult::CouldNotRetrieveAddress:
		Reason = LOCTEXT("JoinNoAddress", "Could not retrieve the host's address.");
		break;
	case EOnJoinSessionCompleteResult::AlreadyInSession:
		Reason = LOCTEXT("JoinAlreadyIn", "You're already in a session.");
		break;
	default:
		Reason = LOCTEXT("JoinUnknown", "Could not join that lobby.");
		break;
	}

	ShowMessage(LOCTEXT("JoinFailedTitle", "Couldn't join"), Reason);

	// The row's Join button stays disabled after a click: fetch a fresh list behind the message
	if (PanelHistory.Contains(BrowsePanel))
	{
		RefreshSessionsButtonClicked();
	}
}

void UMainMenu3::OnInviteAccepted(bool bWasSuccessful)
{
	if (bWasSuccessful)
	{
		// The subsystem joins and travels by itself
		bAwaitingJoin = true;
		ShowBusy(LOCTEXT("JoiningFriend", "Joining your friend's lobby..."), false);
	}
}

void UMainMenu3::OnSessionError(const FString& Message)
{
	bAwaitingCodeLookup = false;
	bAwaitingQuickJoin = false;
	bAwaitingJoin = false;
	bAwaitingCreate = false;
	if (!bBrowseSearchPending)
	{
		SetBrowseButtonsEnabled(true);
	}

	// Shown here, so the next MenuSetup doesn't show it again
	if (MultiplayerSessionsSubsystem)
	{
		MultiplayerSessionsSubsystem->ConsumePendingMenuMessage();
	}

	ShowMessage(LOCTEXT("ErrorTitle", "Notice"), FText::FromString(Message));
}

void UMainMenu3::OnFindSessionsCancelled()
{
	bBrowseSearchPending = false;
	SetBrowseButtonsEnabled(true);
}

#undef LOCTEXT_NAMESPACE
