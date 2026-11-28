// Fill out your copyright notice in the Description page of Project Settings.

#include "EOS/PauseMenu3.h"
#include "EOS/MainMenu3.h"
#include "EOS/MultiplayerSessionsSubsystem.h"
#include "EOS/SessionPlayerRow3.h"
#include "UI/Settings/SettingsMenu3.h"
#include "Match/MyTeamLibrary.h"
#include "MyGameMode.h"
#include "MyGameState.h"
#include "Blueprint/WidgetTree.h"
#include "Components/Button.h"
#include "Components/Image.h"
#include "Components/PanelWidget.h"
#include "Components/TextBlock.h"
#include "Components/WidgetSwitcher.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/GameStateBase.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/PlayerState.h"
#include "GameMapsSettings.h"
#include "HAL/PlatformApplicationMisc.h"
#include "Kismet/KismetSystemLibrary.h"

#define LOCTEXT_NAMESPACE "PauseMenu3"

namespace
{
	// The designer's look and layout of a widget, copied when a WBP row is duplicated. Never a slot, a child list,
	// a bound event, or an object reference that would point back into the source row.
	bool IsCopyableWidgetProperty(const FProperty* Property)
	{
		if (!Property->HasAnyPropertyFlags(CPF_Edit)
			|| Property->HasAnyPropertyFlags(CPF_Transient | CPF_EditorOnly | CPF_Deprecated | CPF_InstancedReference | CPF_ContainsInstancedReference))
		{
			return false;
		}
		if (Property->IsA<FObjectPropertyBase>() || Property->IsA<FInterfaceProperty>()
			|| Property->IsA<FDelegateProperty>() || Property->IsA<FMulticastDelegateProperty>())
		{
			return false;
		}
		if (const FArrayProperty* Array = CastField<FArrayProperty>(Property))
		{
			return !Array->Inner->IsA<FObjectPropertyBase>();
		}
		if (const FSetProperty* Set = CastField<FSetProperty>(Property))
		{
			return !Set->ElementProp->IsA<FObjectPropertyBase>();
		}
		if (const FMapProperty* Map = CastField<FMapProperty>(Property))
		{
			return !Map->KeyProp->IsA<FObjectPropertyBase>() && !Map->ValueProp->IsA<FObjectPropertyBase>();
		}
		return true;
	}

	// Source and its children as new widgets in Tree, with the same properties and slot layout. Names get From
	// replaced by To (Graffiti_Resume -> Graffiti_StartMatch keeps the "Graffiti_" FAuraMenuButtonFX looks for).
	UWidget* CloneWidgetTree(UWidgetTree* Tree, UWidget* Source, const FString& From, const FString& To, TMap<UWidget*, UWidget*>& OutClones)
	{
		FString NewName = Source->GetName().Replace(*From, *To);
		if (NewName == Source->GetName())
		{
			NewName += TEXT("_") + To;
		}
		FName CloneName(*NewName);
		if (StaticFindObjectFast(nullptr, Tree, CloneName))
		{
			CloneName = MakeUniqueObjectName(Tree, Source->GetClass(), CloneName);
		}

		UWidget* Clone = Tree->ConstructWidget<UWidget>(Source->GetClass(), CloneName);
		for (TFieldIterator<FProperty> It(Source->GetClass()); It; ++It)
		{
			if (IsCopyableWidgetProperty(*It))
			{
				It->CopyCompleteValue_InContainer(Clone, Source);
			}
		}
		OutClones.Add(Source, Clone);

		if (UPanelWidget* SourcePanel = Cast<UPanelWidget>(Source))
		{
			UPanelWidget* ClonePanel = CastChecked<UPanelWidget>(Clone);
			for (int32 Index = 0; Index < SourcePanel->GetChildrenCount(); ++Index)
			{
				if (UWidget* SourceChild = SourcePanel->GetChildAt(Index))
				{
					// The source child's slot is the template: padding, alignment, size rule
					ClonePanel->AddChild(CloneWidgetTree(Tree, SourceChild, From, To, OutClones), SourceChild->Slot);
				}
			}
		}
		return Clone;
	}

	// The widget a menu button comes in: the highest ancestor that holds no other button (Wrap_Resume for
	// ResumeButton: SizeBox > Overlay > graffiti, stamp, label, button)
	UWidget* FindButtonRow(UButton* Button)
	{
		UWidget* Row = Button;
		for (UPanelWidget* Parent = Button ? Button->GetParent() : nullptr; Parent; Parent = Parent->GetParent())
		{
			int32 NumButtons = 0;
			UWidgetTree::ForWidgetAndChildren(Parent, [&NumButtons](UWidget* Widget)
			{
				NumButtons += (Widget && Widget->IsA<UButton>()) ? 1 : 0;
			});
			if (NumButtons > 1)
			{
				break;
			}
			Row = Parent;
		}
		return Row;
	}

	// A copy of SourceButton's row right after InsertAfter's row, reading Label. Null when the row can't be copied.
	UButton* CloneButtonRow(UWidgetTree* Tree, UButton* SourceButton, UWidget* InsertAfter, const FText& Label, const FString& Name, UWidget*& OutRow)
	{
		OutRow = nullptr;
		UWidget* SourceRow = FindButtonRow(SourceButton);
		UPanelWidget* List = SourceRow ? SourceRow->GetParent() : nullptr;
		if (!Tree || !List || !InsertAfter || InsertAfter->GetParent() != List)
		{
			return nullptr;
		}

		// A nested user widget's own tree can't be copied property by property
		bool bHasUserWidget = false;
		UWidgetTree::ForWidgetAndChildren(SourceRow, [&bHasUserWidget](UWidget* Widget)
		{
			bHasUserWidget |= Widget && Widget->IsA<UUserWidget>();
		});
		if (bHasUserWidget)
		{
			UE_LOG(LogMatch, Warning, TEXT("PauseMenu3: %s's row holds a user widget, no %s button built (Aura.Match.Start / Aura.Match.Restart still work)"),
				*SourceButton->GetName(), *Name);
			return nullptr;
		}

		FString From = SourceButton->GetName();
		From.RemoveFromEnd(TEXT("Button"));
		TMap<UWidget*, UWidget*> Clones;
		UWidget* Row = CloneWidgetTree(Tree, SourceRow, From.IsEmpty() ? SourceButton->GetName() : From, Name, Clones);
		List->InsertChildAt(List->GetChildIndex(InsertAfter) + 1, Row, SourceRow->Slot);

		const FString LabelString = Label.ToString();
		for (const TPair<UWidget*, UWidget*>& Pair : Clones)
		{
			if (UTextBlock* Text = Cast<UTextBlock>(Pair.Value))
			{
				// The big one-letter stamp behind the label gets the new label's first letter, anything longer the label
				const bool bStamp = CastChecked<UTextBlock>(Pair.Key)->GetText().ToString().Len() <= 1;
				Text->SetText(bStamp ? FText::FromString(LabelString.Left(1)) : Label);
			}
			else if (UImage* Image = Cast<UImage>(Pair.Value))
			{
				// FAuraMenuButtonFX gives every graffiti its own dynamic material; never share the source's
				if (const UMaterialInstanceDynamic* Dynamic = Cast<UMaterialInstanceDynamic>(Image->GetBrush().GetResourceObject()))
				{
					Image->SetBrushResourceObject(Dynamic->Parent);
				}
			}
		}

		OutRow = Row;
		return Cast<UButton>(Clones.FindRef(SourceButton));
	}
}

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
	RefreshMatchButtons();
	if (GetHostMatchGameMode())
	{
		BindMatchChanged();
	}
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
	UnbindMatchChanged();
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

	// Before the first NativeConstruct, so FAuraMenuButtonFX picks up built buttons with the others
	SetupMatchButtons();
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
	UnbindMatchChanged();

	// Removed while open without CloseMenu (a world cleanup, a HUD rebuild): the flag and the UI-only input must not
	// outlive it. A seamless travel gives the host a new controller whose BeginPlay sets game input anyway
	// (GameModeBase.cpp HandleSeamlessTravelPlayer); this covers every other removal
	if (bMenuOpen)
	{
		bMenuOpen = false;
		PendingConfirmAction = EPauseMenu3ConfirmAction::None;
		PendingKickTarget.Reset();
		APlayerController* PlayerController = GetOwningPlayer();

		if (IsValid(PlayerController) && PlayerController->IsLocalController() && !PlayerController->IsActorBeingDestroyed())
		{
			FInputModeGameOnly InputModeData;
			InputModeData.SetConsumeCaptureMouseDown(false);
			PlayerController->SetInputMode(InputModeData);
			PlayerController->SetShowMouseCursor(bCursorWasShown);
		}
	}

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

void UPauseMenu3::RequestLeaveSession()
{
	if (!bMenuOpen)
	{
		OpenMenu();
	}
	LeaveSessionButtonClicked();
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
// Home: team match
//
void UPauseMenu3::SetupMatchButtons()
{
	// Built only for the host of a match (decided at InitGame, fixed for the map; this widget lives with its
	// controller on this map): clients and match-off games keep exactly the WBP's Home panel.
	// After Resume, Start first: Resume, Start match, Restart match, Current Session...
	if (GetHostMatchGameMode() && ResumeButton)
	{
		UWidget* InsertAfter = FindButtonRow(ResumeButton);
		if (!StartMatchButton)
		{
			UWidget* Row = nullptr;
			StartMatchButton = CloneButtonRow(WidgetTree, ResumeButton, InsertAfter, StartMatchLabel, TEXT("StartMatch"), Row);
			InsertAfter = Row ? Row : InsertAfter;
		}
		if (!RestartMatchButton)
		{
			UWidget* Row = nullptr;
			RestartMatchButton = CloneButtonRow(WidgetTree, ResumeButton, InsertAfter, RestartMatchLabel, TEXT("RestartMatch"), Row);
		}
	}

	auto SetupRow = [](UButton* Button, FPauseMenu3MatchRow& MatchRow)
	{
		if (!Button)
		{
			return;
		}
		UWidget* Row = FindButtonRow(Button);
		const ESlateVisibility Visibility = Row->GetVisibility();
		MatchRow.Row = Row;
		MatchRow.ShownVisibility = (Visibility == ESlateVisibility::Collapsed || Visibility == ESlateVisibility::Hidden) ? ESlateVisibility::Visible : Visibility;
		// Hidden until OpenMenu knows the match phase
		Row->SetVisibility(ESlateVisibility::Collapsed);
	};
	SetupRow(StartMatchButton, StartMatchRow);
	SetupRow(RestartMatchButton, RestartMatchRow);

	if (StartMatchButton)   StartMatchButton->OnClicked.AddUniqueDynamic(this, &ThisClass::StartMatchButtonClicked);
	if (RestartMatchButton) RestartMatchButton->OnClicked.AddUniqueDynamic(this, &ThisClass::RestartMatchButtonClicked);
}

AMyGameMode* UPauseMenu3::GetHostMatchGameMode() const
{
	// The game mode lives on the server only, and the listen host's menu runs there, so it calls the game mode
	// directly; a client's menu never shows the buttons
	const APlayerController* PlayerController = GetOwningPlayer();
	UWorld* World = GetWorld();
	if (!World || !PlayerController || !PlayerController->IsLocalController() || !PlayerController->HasAuthority())
	{
		return nullptr;
	}
	AMyGameMode* GameMode = World->GetAuthGameMode<AMyGameMode>();
	return GameMode && GameMode->IsMatchOn() ? GameMode : nullptr;
}

void UPauseMenu3::RefreshMatchButtons()
{
	const UWorld* World = GetWorld();
	const AMyGameState* GameState = World ? World->GetGameState<AMyGameState>() : nullptr;
	AMyGameMode* GameMode = GetHostMatchGameMode();
	const EMyMatchPhase Phase = (GameMode && GameState) ? GameState->GetMatchPhase() : EMyMatchPhase::None;
	const bool bInLobby = GameState && GameState->IsInLobby();

	// Start: a versus match waiting for its players starts with whoever is in (alone: practice); in the lobby it starts
	// the lobby countdown (AMyGameMode::RequestStartMatch forces it, SPEC_B_LOBBY 7.3).
	// Restart: from the countdown on; while waiting it would only reload the same empty lobby. Never during the lobby or
	// its countdown (phase Countdown): RestartMatch would reload the map without the lobby.
	SetMatchRowVisible(StartMatchRow, Phase == EMyMatchPhase::WaitingToStart || Phase == EMyMatchPhase::Lobby);
	SetMatchRowVisible(RestartMatchRow, !bInLobby && (Phase == EMyMatchPhase::Countdown || Phase == EMyMatchPhase::InProgress || Phase == EMyMatchPhase::Ended));

	// A match that ends in the lobby (a lobby round, or the host has a session now): BACK TO LOBBY
	const bool bLobby = GameMode && GameMode->WillReturnToLobby();
	if (!bRestartRowLabelSet || bLobby != bRestartRowIsLobby)
	{
		bRestartRowIsLobby = bLobby;
		bRestartRowLabelSet = true;
		SetMatchRowLabel(RestartMatchRow, bLobby ? BackToLobbyLabel : RestartMatchLabel);
	}
}

void UPauseMenu3::SetMatchRowLabel(FPauseMenu3MatchRow& MatchRow, const FText& Label)
{
	UWidget* Row = MatchRow.Row.Get();
	if (!Row)
	{
		return;
	}

	const FString LabelString = Label.ToString();
	UWidgetTree::ForWidgetAndChildren(Row, [&Label, &LabelString](UWidget* Widget)
	{
		if (UTextBlock* Text = Cast<UTextBlock>(Widget))
		{
			// The big one-letter stamp behind the label gets the label's first letter, anything longer the label
			const bool bStamp = Text->GetText().ToString().Len() <= 1;
			Text->SetText(bStamp ? FText::FromString(LabelString.Left(1)) : Label);
		}
	});
}

void UPauseMenu3::SetMatchRowVisible(FPauseMenu3MatchRow& MatchRow, bool bVisible)
{
	UWidget* Row = MatchRow.Row.Get();
	if (!Row)
	{
		return;
	}

	// Hiding the focused button (Start match once the countdown runs) would leave a gamepad with nothing focused
	const bool bLosesFocus = !bVisible && Row->IsVisible() && Row->HasFocusedDescendants();
	Row->SetVisibility(bVisible ? MatchRow.ShownVisibility : ESlateVisibility::Collapsed);
	if (bLosesFocus && CurrentPanel && !AuraMenu::FocusFirstControl(CurrentPanel))
	{
		SetKeyboardFocus();
	}
}

void UPauseMenu3::BindMatchChanged()
{
	UnbindMatchChanged();
	UWorld* World = GetWorld();
	if (AMyGameState* GameState = World ? World->GetGameState<AMyGameState>() : nullptr)
	{
		MatchChangedHandle = GameState->OnMatchChanged.AddUObject(this, &ThisClass::RefreshMatchButtons);
		MatchGameState = GameState;
	}
}

void UPauseMenu3::UnbindMatchChanged()
{
	if (AMyGameState* GameState = MatchGameState.Get())
	{
		GameState->OnMatchChanged.Remove(MatchChangedHandle);
	}
	MatchGameState.Reset();
	MatchChangedHandle.Reset();
}

void UPauseMenu3::StartMatchButtonClicked()
{
	if (AMyGameMode* GameMode = GetHostMatchGameMode())
	{
		GameMode->RequestStartMatch();
		// Back to the game for the countdown
		CloseMenu();
	}
}

void UPauseMenu3::RestartMatchButtonClicked()
{
	if (AMyGameMode* GameMode = GetHostMatchGameMode())
	{
		if (GameMode->WillReturnToLobby())
		{
			ShowConfirm(LOCTEXT("BackToLobbyTitle", "Back to the lobby"),
				LOCTEXT("BackToLobbyMessage", "End the match and take everyone back to the lobby?"),
				EPauseMenu3ConfirmAction::ReturnToLobby);
			return;
		}
	}

	ShowConfirm(LOCTEXT("RestartMatchTitle", "Restart match"),
		LOCTEXT("RestartMatchMessage", "Restart the match? The map reloads for everyone with the same rules, and every team gets its ship lives back."),
		EPauseMenu3ConfirmAction::RestartMatch);
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
	// A running team match advertises what it really is (the browse filters' Rules and Difficulty), and a 1v1 or 2v2
	// only the slots its teams have, as the main menu's host panel does
	if (UMyTeamLibrary::IsMatchActive(this))
	{
		// IN MATCH / IN LOBBY in the browser (SPEC_B_LOBBY 5.6)
		Settings.bInMatch = !UMyTeamLibrary::IsInLobby(this);
		const FMyMatchRules& Rules = UMyTeamLibrary::GetRules(this);
		Settings.Rules = UMainMenu3::GetRuleSetForTeamMode(Rules.TeamMode);
		Settings.Difficulty = Rules.SwarmDifficulty;
		const int32 ModePlayers = UMainMenu3::GetTeamModeMaxPlayers(Rules.TeamMode);
		if (ModePlayers > 0)
		{
			Settings.NumPublicConnections = ModePlayers;
		}
	}
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
	case EPauseMenu3ConfirmAction::RestartMatch:
		if (AMyGameMode* GameMode = GetHostMatchGameMode())
		{
			// Input back to the game first; the reload replaces this controller's menu anyway
			CloseMenu();
			GameMode->RestartMatch();
			return;
		}
		break;
	case EPauseMenu3ConfirmAction::ReturnToLobby:
		if (AMyGameMode* GameMode = GetHostMatchGameMode())
		{
			// Input back to the game first; the travel replaces this controller's menu anyway
			CloseMenu();
			GameMode->ReturnToLobby();
			return;
		}
		break;
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
		// What AMyGameMode::PostLogin does for a lobby hosted from the main menu. In the lobby the session starts with the
		// round instead (AMyGameMode::BeginRound, SPEC_B_LOBBY 5.6)
		UMultiplayerSessionsSubsystem* Sessions = GetSessions();
		if (Sessions && !UMyTeamLibrary::IsInLobby(this))
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
