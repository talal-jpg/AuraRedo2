// Fill out your copyright notice in the Description page of Project Settings.

#include "Match/MyLobbyWidget.h"

#include "MyGameState.h"
#include "MyPlayerState.h"
#include "Blueprint/WidgetTree.h"
#include "Components/Button.h"
#include "Components/CheckBox.h"
#include "Components/ComboBoxString.h"
#include "Components/PanelWidget.h"
#include "Components/TextBlock.h"
#include "EOS/MainMenu3.h"
#include "EOS/MultiplayerSessionsSubsystem.h"
#include "Engine/GameInstance.h"
#include "Engine/GameViewportClient.h"
#include "Framework/Application/SlateApplication.h"
#include "Widgets/SViewport.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "HAL/PlatformApplicationMisc.h"
#include "Match/MyLobbyPlayerRow.h"
#include "Match/MyMatchSettings.h"
#include "Match/MyTeamLibrary.h"
#include "PlayerInput/MyPlayerController2.h"

#define LOCTEXT_NAMESPACE "MyLobby"

// Named, not anonymous: the unity build compiles this file together with others
namespace MyLobbyWidgetPrivate
{
	void SetShown(UWidget* Widget, bool bShown, ESlateVisibility ShownVisibility = ESlateVisibility::SelfHitTestInvisible)
	{
		if (!Widget)
		{
			return;
		}

		const ESlateVisibility Want = bShown ? ShownVisibility : ESlateVisibility::Collapsed;

		if (Widget->GetVisibility() != Want)
		{
			Widget->SetVisibility(Want);
		}
	}

	void SetTextIfChanged(UTextBlock* Text, const FText& Value)
	{
		if (Text && !Text->GetText().EqualTo(Value))
		{
			Text->SetText(Value);
		}
	}

	void SetEnabled(UWidget* Widget, bool bEnabled)
	{
		if (Widget && Widget->GetIsEnabled() != bEnabled)
		{
			Widget->SetIsEnabled(bEnabled);
		}
	}

	FString TimeLimitLabel(int32 Minutes)
	{
		return Minutes <= 0 ? FString(TEXT("None")) : FString::Printf(TEXT("%d min"), Minutes);
	}
}

// -------------------------------------------------------------------------------------------------------------------
// Life
// -------------------------------------------------------------------------------------------------------------------

bool UMyLobbyWidget::Initialize()
{
	if (!Super::Initialize())
	{
		return false;
	}

	if (CopyCodeButton)   CopyCodeButton->OnClicked.AddUniqueDynamic(this, &ThisClass::CopyCodeButtonClicked);
	if (SwitchTeamButton) SwitchTeamButton->OnClicked.AddUniqueDynamic(this, &ThisClass::SwitchTeamButtonClicked);
	if (ReadyButton)      ReadyButton->OnClicked.AddUniqueDynamic(this, &ThisClass::ReadyButtonClicked);
	if (StartButton)      StartButton->OnClicked.AddUniqueDynamic(this, &ThisClass::StartButtonClicked);
	if (CloseButton)      CloseButton->OnClicked.AddUniqueDynamic(this, &ThisClass::CloseButtonClicked);
	if (MenuButton)       MenuButton->OnClicked.AddUniqueDynamic(this, &ThisClass::MenuButtonClicked);
	if (LeaveButton)      LeaveButton->OnClicked.AddUniqueDynamic(this, &ThisClass::LeaveButtonClicked);

	if (TeamModeComboBox) TeamModeComboBox->OnSelectionChanged.AddUniqueDynamic(this, &ThisClass::OnTeamModeChanged);

	for (UComboBoxString* Combo : { ShipLivesComboBox, SwarmComboBox, MaxPlayersComboBox, TimeLimitComboBox })
	{
		if (Combo)
		{
			Combo->OnSelectionChanged.AddUniqueDynamic(this, &ThisClass::OnRuleComboChanged);
		}
	}

	for (UCheckBox* Check : { FriendlyFireCheckBox, GrappleShipsCheckBox, LaneAssistCheckBox })
	{
		if (Check)
		{
			Check->OnCheckStateChanged.AddUniqueDynamic(this, &ThisClass::OnRuleCheckChanged);
		}
	}

	return true;
}

void UMyLobbyWidget::NativeConstruct()
{
	Super::NativeConstruct();

	// The root never takes a click (the game is under it); the panel's own plate does
	SetVisibility(ESlateVisibility::SelfHitTestInvisible);
	SetIsFocusable(true);

	FillRuleOptions();
	ButtonFXState.Setup(WidgetTree, ButtonFX);
	BindController();
	BindGameState();

	// Nothing shows until the first refresh says the lobby is on
	MyLobbyWidgetPrivate::SetShown(LobbyPanel, false);
	MyLobbyWidgetPrivate::SetShown(CompactPanel, false);
	MyLobbyWidgetPrivate::SetShown(CountdownText, false);
	MyLobbyWidgetPrivate::SetShown(CountdownHintText, false);
	MyLobbyWidgetPrivate::SetShown(MessageText, false);
	bRefreshPending = true;
}

void UMyLobbyWidget::NativeDestruct()
{
	if (bPanelOpen)
	{
		// Give the input back if the world goes on (a seamless travel tears the controller down itself)
		APlayerController* PC = GetOwningPlayer();
		bPanelOpen = false;

		if (IsValid(PC) && PC->IsLocalController() && !PC->IsActorBeingDestroyed())
		{
			FInputModeGameOnly InputMode;
			InputMode.SetConsumeCaptureMouseDown(false);
			PC->SetInputMode(InputMode);
			PC->SetShowMouseCursor(bCursorWasShown);
		}
	}

	UnbindGameState();
	UnbindController();
	ButtonFXState.Reset();

	Super::NativeDestruct();
}

void UMyLobbyWidget::BindController()
{
	if (ControllerWeak.IsValid())
	{
		return;
	}

	if (AMyPlayerController2* PC = Cast<AMyPlayerController2>(GetOwningPlayer()))
	{
		ControllerWeak = PC;
		PC->SetLobbyPanel(this);
		LobbyMessageHandle = PC->OnLobbyMessage.AddUObject(this, &ThisClass::HandleLobbyMessage);
	}
}

void UMyLobbyWidget::UnbindController()
{
	if (AMyPlayerController2* PC = ControllerWeak.Get())
	{
		PC->OnLobbyMessage.Remove(LobbyMessageHandle);

		if (PC->GetLobbyPanel() == static_cast<IMyLobbyPanel*>(this))
		{
			PC->SetLobbyPanel(nullptr);
		}
	}

	LobbyMessageHandle.Reset();
	ControllerWeak.Reset();
}

void UMyLobbyWidget::BindGameState()
{
	if (GameStateWeak.IsValid())
	{
		return;
	}

	const UWorld* World = GetWorld();

	if (AMyGameState* GameState = World ? World->GetGameState<AMyGameState>() : nullptr)
	{
		GameStateWeak = GameState;
		MatchChangedHandle = GameState->OnMatchChanged.AddUObject(this, &ThisClass::HandleMatchChanged);
		bRefreshPending = true;
	}
}

void UMyLobbyWidget::UnbindGameState()
{
	if (AMyGameState* GameState = GameStateWeak.Get())
	{
		GameState->OnMatchChanged.Remove(MatchChangedHandle);
	}

	MatchChangedHandle.Reset();
	GameStateWeak.Reset();
}

void UMyLobbyWidget::HandleMatchChanged()
{
	// Several setters can fire in one frame on the server: one refresh next tick
	bRefreshPending = true;
}

void UMyLobbyWidget::HandleLobbyMessage(const FText& Text)
{
	++LobbyMessageCount;
	ShowMessage(Text);

	// A message right after a rules request is its answer (a refusal): the rules box says it too
	if (RulesHintText && IsHostView() && WidgetTime - LastRulesSendTime < 2.f)
	{
		RulesHintText->SetText(Text);
		RulesHintTimeLeft = MessageSeconds;
	}
}

void UMyLobbyWidget::ShowMessage(const FText& Text)
{
	if (MessageText)
	{
		MessageText->SetText(Text);
		MyLobbyWidgetPrivate::SetShown(MessageText, !Text.IsEmpty(), ESlateVisibility::HitTestInvisible);
	}
	MessageTimeLeft = Text.IsEmpty() ? 0.f : MessageSeconds;
}

AMyGameState* UMyLobbyWidget::GetLobbyGameState() const
{
	return GameStateWeak.Get();
}

UWidget* UMyLobbyWidget::FindButtonItem(UWidget* Button)
{
	UWidget* Item = Button;

	for (UPanelWidget* Parent = Button ? Button->GetParent() : nullptr; Parent; Parent = Parent->GetParent())
	{
		const FString Name = Parent->GetName();

		if (!Name.StartsWith(TEXT("Item_")) && !Name.StartsWith(TEXT("Wrap_")))
		{
			break;
		}

		int32 NumButtons = 0;
		UWidgetTree::ForWidgetAndChildren(Parent, [&NumButtons](UWidget* Widget)
		{
			NumButtons += (Widget && Widget->IsA<UButton>()) ? 1 : 0;
		});

		if (NumButtons > 1)
		{
			break;
		}

		Item = Parent;
	}

	return Item;
}

void UMyLobbyWidget::SetButtonShown(UWidget* Button, bool bShown)
{
	if (!Button)
	{
		return;
	}

	UWidget* Item = FindButtonItem(Button);

	if (Item == Button)
	{
		MyLobbyWidgetPrivate::SetShown(Button, bShown, ESlateVisibility::Visible);
		return;
	}

	// The item's own visibility only: the button and its label stay as the layout made them
	MyLobbyWidgetPrivate::SetShown(Button, true, ESlateVisibility::Visible);
	MyLobbyWidgetPrivate::SetShown(Item, bShown, ESlateVisibility::SelfHitTestInvisible);
}

AMyPlayerController2* UMyLobbyWidget::GetLobbyController() const
{
	return Cast<AMyPlayerController2>(GetOwningPlayer());
}

AMyPlayerState* UMyLobbyWidget::GetLocalPlayerState() const
{
	const APlayerController* PC = GetOwningPlayer();
	return PC ? PC->GetPlayerState<AMyPlayerState>() : nullptr;
}

bool UMyLobbyWidget::IsHostView() const
{
	if (const AMyPlayerState* Local = GetLocalPlayerState())
	{
		if (Local->IsHost())
		{
			return true;
		}
	}

	// Before OnPlayerArrived set the flag: the listen server's (or a standalone game's) own player is the host
	const APlayerController* PC = GetOwningPlayer();
	const UWorld* World = GetWorld();
	return PC && World && PC->IsLocalController() && World->GetNetMode() != NM_Client;
}

// -------------------------------------------------------------------------------------------------------------------
// The panel (IMyLobbyPanel)
// -------------------------------------------------------------------------------------------------------------------

void UMyLobbyWidget::OpenPanel()
{
	const AMyGameState* GameState = GetLobbyGameState();
	APlayerController* PC = GetOwningPlayer();

	if (bPanelOpen || !GameState || !GameState->IsInLobby() || !PC || !PC->IsLocalController())
	{
		return;
	}

	bPanelOpen = true;
	bCursorWasShown = PC->ShouldShowMouseCursor();

	// Nothing stays held (moving, firing) while the panel has the input
	PC->FlushPressedKeys();

	FInputModeUIOnly InputMode;
	InputMode.SetWidgetToFocus(TakeWidget());
	InputMode.SetLockMouseToViewportBehavior(EMouseLockMode::DoNotLock);
	PC->SetInputMode(InputMode);
	PC->SetShowMouseCursor(true);

	Refresh();

	if (LobbyPanel && !AuraMenu::FocusFirstControl(LobbyPanel))
	{
		SetKeyboardFocus();
	}

	UE_LOG(LogMatch, Log, TEXT("Lobby panel open (%s)"), *GetNameSafe(PC));
	OnPanelToggled(true);
}

void UMyLobbyWidget::ClosePanel()
{
	if (!bPanelOpen)
	{
		return;
	}

	bPanelOpen = false;
	StartConfirmTimeLeft = 0.f;

	// A host edit still waiting goes out now
	if (bRulesDirty)
	{
		SendRules();
	}

	APlayerController* PC = GetOwningPlayer();

	if (PC && PC->IsLocalController())
	{
		// The input mode AMyPlayerController2::BeginPlay sets (and UPauseMenu3::CloseMenu)
		FInputModeGameOnly InputMode;
		InputMode.SetConsumeCaptureMouseDown(false);
		PC->SetInputMode(InputMode);
		PC->SetShowMouseCursor(bCursorWasShown);
	}

	const AMyGameState* GameState = GetLobbyGameState();
	RefreshViews(GameState && GameState->IsInLobby(), GameState && GameState->IsLobbyCountingDown());

	UE_LOG(LogMatch, Log, TEXT("Lobby panel closed (%s)"), *GetNameSafe(PC));
	OnPanelToggled(false);
}

FReply UMyLobbyWidget::NativeOnKeyDown(const FGeometry& InGeometry, const FKeyEvent& InKeyEvent)
{
	// UI-only input eats IA_Pause: the panel closes itself (as UPauseMenu3, Start included)
	if (bPanelOpen && AuraMenu::IsBackKey(InKeyEvent.GetKey(), true))
	{
		ClosePanel();
		return FReply::Handled();
	}

	return Super::NativeOnKeyDown(InGeometry, InKeyEvent);
}

// -------------------------------------------------------------------------------------------------------------------
// Tick
// -------------------------------------------------------------------------------------------------------------------

void UMyLobbyWidget::NativeTick(const FGeometry& MyGeometry, float InDeltaTime)
{
	Super::NativeTick(MyGeometry, InDeltaTime);

	WidgetTime += InDeltaTime;
	BindController();
	BindGameState();

	const AMyGameState* GameState = GetLobbyGameState();

	RefreshTimer -= InDeltaTime;

	if (bRefreshPending || RefreshTimer <= 0.f)
	{
		Refresh();
	}

	if (!GameState || !GameState->IsInLobby())
	{
		return;
	}

	ButtonFXState.Tick(InDeltaTime);
	RefreshCountdown(GameState);

	if (MessageTimeLeft > 0.f)
	{
		MessageTimeLeft -= InDeltaTime;

		if (MessageTimeLeft <= 0.f)
		{
			MyLobbyWidgetPrivate::SetShown(MessageText, false);
		}
	}

	if (RulesHintTimeLeft > 0.f)
	{
		RulesHintTimeLeft -= InDeltaTime;

		if (RulesHintTimeLeft <= 0.f)
		{
			bRefreshPending = true;
		}
	}

	if (StartConfirmTimeLeft > 0.f)
	{
		StartConfirmTimeLeft -= InDeltaTime;

		if (StartConfirmTimeLeft <= 0.f)
		{
			bRefreshPending = true;
		}
	}

	if (bRulesDirty)
	{
		RulesSendTimeLeft -= InDeltaTime;

		if (RulesSendTimeLeft <= 0.f)
		{
			SendRules();
		}
	}

	APlayerController* PC = GetOwningPlayer();

	// Once per map load: the first lobby pawn of this player, in phase Lobby (not during the countdown)
	if (bAutoOpen && !bAutoOpenDone && PC && PC->GetPawn() && GameState->GetMatchPhase() == EMyMatchPhase::Lobby)
	{
		const AMyPlayerController2* MyPC = Cast<AMyPlayerController2>(PC);
		bAutoOpenDone = true;

		if (!bPanelOpen && !(MyPC && MyPC->IsPauseMenuOpen()))
		{
			OpenPanel();
		}
	}

	// A click on the world outside the panel gives the focus to this viewport; Esc must keep working. Only from this
	// world's own viewport: in single-process PIE the other windows' widgets share the Slate user
	if (bPanelOpen && !HasAnyUserFocus() && !HasFocusedDescendants() && !IsAnyComboOpen() && FSlateApplication::IsInitialized())
	{
		const UWorld* World = GetWorld();
		const UGameViewportClient* Viewport = World ? World->GetGameViewport() : nullptr;
		const TSharedPtr<SViewport> ViewportWidget = Viewport ? Viewport->GetGameViewportWidget() : nullptr;
		const TSharedPtr<SWidget> Focused = FSlateApplication::Get().GetKeyboardFocusedWidget();

		if (ViewportWidget.IsValid() && Focused.Get() == static_cast<SWidget*>(ViewportWidget.Get()))
		{
			SetKeyboardFocus();
		}
	}
}

bool UMyLobbyWidget::IsAnyComboOpen() const
{
	for (const UComboBoxString* Combo : { TeamModeComboBox, ShipLivesComboBox, SwarmComboBox, MaxPlayersComboBox, TimeLimitComboBox })
	{
		if (Combo && Combo->IsOpen())
		{
			return true;
		}
	}
	return false;
}

// -------------------------------------------------------------------------------------------------------------------
// Refresh
// -------------------------------------------------------------------------------------------------------------------

void UMyLobbyWidget::Refresh()
{
	bRefreshPending = false;
	RefreshTimer = RefreshInterval;

	const AMyGameState* GameState = GetLobbyGameState();
	const bool bInLobby = GameState && GameState->IsInLobby();
	const bool bCounting = GameState && GameState->IsLobbyCountingDown();

	// Every machine closes the panel when the lobby countdown starts, and when the lobby ends (major M2)
	if (bCounting && !bWasCounting && bPanelOpen)
	{
		ClosePanel();
	}
	if (!bInLobby && bWasInLobby && bPanelOpen)
	{
		ClosePanel();
	}
	if (bCounting != bWasCounting)
	{
		StartConfirmTimeLeft = 0.f;
		LastCountdownSecond = -1;
	}

	bWasCounting = bCounting;
	bWasInLobby = bInLobby;

	RefreshViews(bInLobby, bCounting);

	if (!bInLobby)
	{
		return;
	}

	RefreshRows(GameState);
	RefreshCompact(GameState, bCounting);
	RefreshCountdown(GameState);

	// The full panel's contents only while it shows
	if (bPanelOpen)
	{
		RefreshHeader();
		RefreshTeams(GameState, bCounting);
		RefreshRules(GameState, bCounting);
		RefreshActions(GameState, bCounting);
	}
}

void UMyLobbyWidget::RefreshViews(bool bInLobby, bool bCounting)
{
	// The panel's plate takes clicks (they must not fall through to the game while it has the input)
	MyLobbyWidgetPrivate::SetShown(LobbyPanel, bInLobby && bPanelOpen, ESlateVisibility::Visible);
	// Not during the countdown: the match HUD's bar sits there then (BarTop 16), and CountdownText / its hint say it all
	MyLobbyWidgetPrivate::SetShown(CompactPanel, bInLobby && !bPanelOpen && !bCounting, ESlateVisibility::HitTestInvisible);
	MyLobbyWidgetPrivate::SetShown(CountdownText, bInLobby && bCounting, ESlateVisibility::HitTestInvisible);
	MyLobbyWidgetPrivate::SetShown(CountdownHintText, bInLobby && bCounting && !bPanelOpen, ESlateVisibility::HitTestInvisible);

	if (!bInLobby)
	{
		MyLobbyWidgetPrivate::SetShown(MessageText, false);
		MessageTimeLeft = 0.f;
	}
}

void UMyLobbyWidget::RefreshCountdown(const AMyGameState* GameState)
{
	if (!GameState || !GameState->IsLobbyCountingDown())
	{
		return;
	}

	const double Left = GameState->GetPhaseEndServerTime() - GameState->GetServerWorldTimeSeconds();
	const int32 Second = FMath::Max(0, FMath::CeilToInt(Left));

	if (Second == LastCountdownSecond)
	{
		return;
	}

	LastCountdownSecond = Second;
	MyLobbyWidgetPrivate::SetTextIfChanged(CountdownText, FText::Format(LOCTEXT("Countdown", "MATCH STARTS IN {0}"), Second));
	MyLobbyWidgetPrivate::SetTextIfChanged(CountdownHintText, IsHostView() ? LOCTEXT("CountdownHintHost", "Esc: lobby (CANCEL)") : LOCTEXT("CountdownHint", "Esc: lobby"));
}

void UMyLobbyWidget::RefreshRows(const AMyGameState* GameState)
{
	// One entry per PlayerId: a carried old player state and its replacement share it (5.4); the one not arriving wins
	TArray<AMyPlayerState*> Players;
	TMap<int32, int32> IndexById;

	for (APlayerState* PlayerState : GameState->PlayerArray)
	{
		AMyPlayerState* MyPlayerState = Cast<AMyPlayerState>(PlayerState);

		if (!IsValid(MyPlayerState))
		{
			continue;
		}

		const int32 Id = MyPlayerState->GetPlayerId();

		if (const int32* Existing = IndexById.Find(Id))
		{
			if (Players[*Existing]->IsArriving() && !MyPlayerState->IsArriving())
			{
				Players[*Existing] = MyPlayerState;
			}
			continue;
		}

		// No team yet (the first frame of a join): it shows once AssignTeam has run
		if (MyPlayerState->GetTeamId() >= MyMatch::NumTeams && !MyPlayerState->IsArriving())
		{
			continue;
		}

		IndexById.Add(Id, Players.Num());
		Players.Add(MyPlayerState);
	}

	const AMyPlayerState* Local = GetLocalPlayerState();
	const bool bHostView = IsHostView();
	FString Signature = FString::Printf(TEXT("%s|%d|%d|"), *GetNameSafe(Local), bHostView ? 1 : 0, PlayerRowClass ? 1 : 0);

	for (const AMyPlayerState* Player : Players)
	{
		Signature += FString::Printf(TEXT("%d:%d:%d:%s;"), Player->GetPlayerId(), Player->GetTeamId(), Player->IsArriving() ? 1 : 0, *Player->GetName());
	}

	if (Signature != RowSignature)
	{
		RowSignature = Signature;
		RebuildRows(Players);
	}

	RefreshRowTexts();
}

void UMyLobbyWidget::RefreshRowTexts()
{
	const AMyPlayerState* Local = GetLocalPlayerState();

	// Same players on the same teams: texts in place, so a click on a row's MOVE lands on the widget it pressed
	for (UMyLobbyPlayerRow* Row : Rows)
	{
		if (Row)
		{
			Row->Refresh();
		}
	}

	for (int32 Index = 0; Index < FallbackRows.Num(); ++Index)
	{
		const AMyPlayerState* Player = FallbackRowPlayers.IsValidIndex(Index) ? FallbackRowPlayers[Index].Get() : nullptr;

		if (FallbackRows[Index] && Player)
		{
			const FText Status = Player->IsArriving() ? LOCTEXT("FallbackLoading", "LOADING") : Player->IsHost() ? LOCTEXT("FallbackHost", "HOST")
				: Player->IsLobbyReady() ? LOCTEXT("FallbackReady", "READY") : LOCTEXT("FallbackNotReady", "NOT READY");
			MyLobbyWidgetPrivate::SetTextIfChanged(FallbackRows[Index], FText::Format(LOCTEXT("FallbackRow", "{0}{1}   {2}"),
				Player == Local ? FText::FromString(TEXT("* ")) : FText::GetEmpty(), FText::FromString(Player->GetPlayerName()), Status));
		}
	}
}

void UMyLobbyWidget::RebuildRows(const TArray<AMyPlayerState*>& Players)
{
	if (BlueList)
	{
		BlueList->ClearChildren();
	}
	if (OrangeList)
	{
		OrangeList->ClearChildren();
	}

	Rows.Reset();
	FallbackRows.Reset();
	FallbackRowPlayers.Reset();

	const AMyPlayerState* Local = GetLocalPlayerState();
	const bool bHostView = IsHostView();

	for (AMyPlayerState* Player : Players)
	{
		UPanelWidget* List = Player->GetTeamId() == 1 ? OrangeList : BlueList;

		if (!List)
		{
			continue;
		}

		if (PlayerRowClass)
		{
			if (UMyLobbyPlayerRow* Row = CreateWidget<UMyLobbyPlayerRow>(this, PlayerRowClass))
			{
				Row->Setup(this, Player, Player == Local, bHostView);
				List->AddChild(Row);
				Rows.Add(Row);
			}
			continue;
		}

		// Without a row class (6.6): one plain line per player
		if (UTextBlock* Line = WidgetTree ? WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass()) : nullptr)
		{
			List->AddChild(Line);
			FallbackRows.Add(Line);
			FallbackRowPlayers.Add(Player);
		}
	}

	UE_LOG(LogMatch, Verbose, TEXT("Lobby panel: %d row(s) rebuilt"), Players.Num());
}

void UMyLobbyWidget::RefreshHeader()
{
	FString LobbyName;
	const FString Code = GetJoinCode(&LobbyName);
	const bool bSession = !LobbyName.IsEmpty() || !Code.IsEmpty();

	MyLobbyWidgetPrivate::SetTextIfChanged(TitleText, bSession ? FText::FromString(LobbyName) : LOCTEXT("LocalGame", "Local game (no online session)"));
	MyLobbyWidgetPrivate::SetShown(JoinCodeText, !Code.IsEmpty(), ESlateVisibility::HitTestInvisible);
	SetButtonShown(CopyCodeButton, !Code.IsEmpty());

	if (!Code.IsEmpty())
	{
		MyLobbyWidgetPrivate::SetTextIfChanged(JoinCodeText, FText::FromString(Code));
	}
}

FString UMyLobbyWidget::GetJoinCode(FString* OutLobbyName) const
{
	const UGameInstance* GameInstance = GetGameInstance();
	const UMultiplayerSessionsSubsystem* Sessions = GameInstance ? GameInstance->GetSubsystem<UMultiplayerSessionsSubsystem>() : nullptr;

	if (!Sessions)
	{
		return FString();
	}

	FString Code;
	FAuraSessionInfo Info;

	if (Sessions->GetCurrentSessionInfo(Info))
	{
		Code = Info.JoinCode;

		if (OutLobbyName)
		{
			*OutLobbyName = Info.LobbyName.IsEmpty() ? Info.HostName : Info.LobbyName;
		}
	}

	// The host knows his own code even when the session info doesn't carry it
	if (Code.IsEmpty() && Sessions->IsHostingSession())
	{
		Code = Sessions->GetCurrentJoinCode();
	}

	return Code;
}

int32 UMyLobbyWidget::GetDisplayTeamCap(uint8 TeamId) const
{
	const AMyGameState* GameState = GetLobbyGameState();

	if (!GameState || TeamId >= MyMatch::NumTeams)
	{
		return 0;
	}

	const int32 MaxPlayers = FMath::Max(1, GameState->GetExpectedPlayers());

	switch (GameState->GetMatchRules().TeamMode)
	{
	case EMyTeamMode::OneVsOne: return 1;
	case EMyTeamMode::TwoVsTwo: return 2;
	case EMyTeamMode::Practice: return TeamId == 0 ? MaxPlayers : 0;
	default:
	{
		// The server's cap (AMyGameMode::GetTeamCap) when the settings set one, else half of Max Players to show
		const int32 Cap = UMyMatchSettings::Get()->AutoMaxPlayersPerTeam;
		return Cap > 0 ? Cap : (MaxPlayers + 1) / 2;
	}
	}
}

void UMyLobbyWidget::RefreshTeams(const AMyGameState* GameState, bool bCounting)
{
	const bool bPractice = GameState->GetMatchRules().TeamMode == EMyTeamMode::Practice;

	for (uint8 Team = 0; Team < MyMatch::NumTeams; ++Team)
	{
		UTextBlock* Header = Team == 0 ? BlueHeaderText : OrangeHeaderText;

		if (!Header)
		{
			continue;
		}

		const int32 Count = GameState->GetTeamState(Team).NumPlayers;
		const int32 Cap = GetDisplayTeamCap(Team);
		const FText Name = UMyTeamLibrary::GetTeamName(Team);
		FText Value;

		if (bPractice && Team == 1)
		{
			Value = FText::Format(LOCTEXT("TeamUnused", "{0}  -  practice: one ship"), Name);
		}
		else
		{
			Value = Cap > 0 ? FText::Format(LOCTEXT("TeamCountCap", "{0}  {1} / {2}"), Name, Count, Cap) : FText::Format(LOCTEXT("TeamCount", "{0}  {1}"), Name, Count);
		}

		MyLobbyWidgetPrivate::SetTextIfChanged(Header, Value);
		Header->SetColorAndOpacity(FSlateColor(UMyTeamLibrary::GetTeamColor(Team)));
	}

	if (SwitchTeamButton)
	{
		const AMyPlayerState* Local = GetLocalPlayerState();
		const uint8 Team = Local ? Local->GetTeamId() : MyMatch::NoTeam;
		const bool bShow = !bPractice && UMyMatchSettings::Get()->bLobbyTeamSwitch && Team < MyMatch::NumTeams;
		SetButtonShown(SwitchTeamButton, bShow);
		MyLobbyWidgetPrivate::SetEnabled(SwitchTeamButton, bShow && !bCounting);

		if (bShow)
		{
			const uint8 Requested = Local->GetRequestedTeam();
			MyLobbyWidgetPrivate::SetTextIfChanged(SwitchTeamText, Requested < MyMatch::NumTeams && Requested != Team ? LOCTEXT("CancelSwitch", "CANCEL SWITCH")
				: FText::Format(LOCTEXT("SwitchTo", "SWITCH TO {0}"), UMyTeamLibrary::GetTeamName(1 - Team)));
		}
	}
}

void UMyLobbyWidget::RefreshCompact(const AMyGameState* GameState, bool bCounting)
{
	if (!CompactText)
	{
		return;
	}

	const FMyMatchRules& Rules = GameState->GetMatchRules();
	FText Teams;

	if (Rules.TeamMode == EMyTeamMode::Practice)
	{
		Teams = FText::Format(LOCTEXT("CompactPractice", "PRACTICE  {0} {0}|plural(one=PLAYER,other=PLAYERS)"), GameState->GetTeamState(0).NumPlayers);
	}
	else
	{
		Teams = FText::Format(LOCTEXT("CompactTeams", "{0} {1} - {2} {3}"), UMyTeamLibrary::GetTeamName(0), GameState->GetTeamState(0).NumPlayers,
			UMyTeamLibrary::GetTeamName(1), GameState->GetTeamState(1).NumPlayers);
	}

	FText Value;

	if (bCounting)
	{
		Value = FText::Format(LOCTEXT("CompactCounting", "MATCH STARTING   {0}   Esc: lobby"), Teams);
	}
	else
	{
		const int32 NotReady = GameState->GetLobbyNotReady();
		const FText Ready = NotReady > 0 ? FText::Format(LOCTEXT("CompactNotReady", "   {0} NOT READY"), NotReady) : FText::GetEmpty();
		Value = FText::Format(LOCTEXT("CompactLobby", "LOBBY   {0}{1}   Esc: lobby"), Teams, Ready);
	}

	MyLobbyWidgetPrivate::SetTextIfChanged(CompactText, Value);
}

// -------------------------------------------------------------------------------------------------------------------
// Rules
// -------------------------------------------------------------------------------------------------------------------

void UMyLobbyWidget::FillRuleOptions()
{
	// The host menu's lists (UMainMenu3's C++ class defaults), so the menu and the lobby can't drift apart
	if (TeamModeComboBox)
	{
		TeamModeComboBox->ClearOptions();
		TeamModeOptions.Reset();

		for (const FString& RuleSet : UMainMenu3::GetDefaultRuleSets())
		{
			const EMyTeamMode Mode = UMainMenu3::GetTeamModeForRuleSet(RuleSet);

			if (TeamModeOptions.Contains(Mode))
			{
				continue;
			}

			TeamModeOptions.Add(Mode);
			TeamModeComboBox->AddOption(Mode == EMyTeamMode::Practice ? PracticeRuleLabel.ToString() : RuleSet);
		}
	}

	if (ShipLivesComboBox)
	{
		ShipLivesComboBox->ClearOptions();
		ShipLivesOptions = UMainMenu3::GetDefaultShipLivesChoices();
		ShipLivesOptions.Sort();

		for (const int32 Lives : ShipLivesOptions)
		{
			ShipLivesComboBox->AddOption(FString::FromInt(Lives));
		}
	}

	if (SwarmComboBox)
	{
		SwarmComboBox->ClearOptions();
		SwarmOptions.Reset();
		const TArray<FString>& Names = UMainMenu3::GetDefaultDifficultyNames();

		for (int32 Index = 0; Index < MyMatch::NumDifficulties; ++Index)
		{
			SwarmOptions.Add(Index);
			SwarmComboBox->AddOption(Names.IsValidIndex(Index) ? Names[Index] : FString::Printf(TEXT("Difficulty %d"), Index));
		}
	}

	if (MaxPlayersComboBox)
	{
		MaxPlayersComboBox->ClearOptions();
		MaxPlayerOptions = UMainMenu3::GetDefaultMaxPlayerChoices();
		MaxPlayerOptions.Sort();

		for (const int32 Count : MaxPlayerOptions)
		{
			MaxPlayersComboBox->AddOption(FString::FromInt(Count));
		}
	}

	if (TimeLimitComboBox)
	{
		TimeLimitComboBox->ClearOptions();
		TimeLimitOptions = TimeLimitChoices;
		TimeLimitOptions.Sort();

		for (const int32 Minutes : TimeLimitOptions)
		{
			TimeLimitComboBox->AddOption(MyLobbyWidgetPrivate::TimeLimitLabel(Minutes));
		}
	}
}

void UMyLobbyWidget::SetComboToInt(UComboBoxString* Combo, TArray<int32>& Values, int32 Value, bool bTimeLimit)
{
	if (!Combo)
	{
		return;
	}

	int32 Index = Values.Find(Value);

	if (Index == INDEX_NONE)
	{
		// A value the box doesn't offer (a console edit, a config default): added in order, so the box shows the truth
		Index = 0;
		while (Index < Values.Num() && Values[Index] < Value)
		{
			++Index;
		}
		Values.Insert(Value, Index);
		Combo->ClearOptions();

		for (const int32 Each : Values)
		{
			Combo->AddOption(bTimeLimit ? MyLobbyWidgetPrivate::TimeLimitLabel(Each) : FString::FromInt(Each));
		}
	}

	if (Combo->GetSelectedIndex() != Index)
	{
		Combo->SetSelectedIndex(Index);
	}
}

void UMyLobbyWidget::ApplyRulesToControls(const FMyMatchRules& Rules, int32 MaxPlayers)
{
	if (TeamModeComboBox && !TeamModeComboBox->IsOpen())
	{
		const int32 Index = TeamModeOptions.Find(Rules.TeamMode);

		if (Index != INDEX_NONE && TeamModeComboBox->GetSelectedIndex() != Index)
		{
			TeamModeComboBox->SetSelectedIndex(Index);
		}
	}

	if (ShipLivesComboBox && !ShipLivesComboBox->IsOpen())
	{
		SetComboToInt(ShipLivesComboBox, ShipLivesOptions, Rules.ShipLives, false);
	}

	if (SwarmComboBox && !SwarmComboBox->IsOpen())
	{
		const int32 Index = SwarmOptions.Find(FMath::Clamp(Rules.SwarmDifficulty, 0, MyMatch::NumDifficulties - 1));

		if (Index != INDEX_NONE && SwarmComboBox->GetSelectedIndex() != Index)
		{
			SwarmComboBox->SetSelectedIndex(Index);
		}
	}

	if (MaxPlayersComboBox && !MaxPlayersComboBox->IsOpen())
	{
		SetComboToInt(MaxPlayersComboBox, MaxPlayerOptions, FMath::Max(1, MaxPlayers), false);
	}

	if (TimeLimitComboBox && !TimeLimitComboBox->IsOpen())
	{
		SetComboToInt(TimeLimitComboBox, TimeLimitOptions, FMath::Max(0, Rules.TimeLimitMinutes), true);
	}

	// SetIsChecked doesn't broadcast OnCheckStateChanged (only a click does)
	if (FriendlyFireCheckBox && FriendlyFireCheckBox->IsChecked() != Rules.bFriendlyFire) FriendlyFireCheckBox->SetIsChecked(Rules.bFriendlyFire);
	if (GrappleShipsCheckBox && GrappleShipsCheckBox->IsChecked() != Rules.bGrappleShips) GrappleShipsCheckBox->SetIsChecked(Rules.bGrappleShips);
	if (LaneAssistCheckBox && LaneAssistCheckBox->IsChecked() != Rules.bLaneAssist) LaneAssistCheckBox->SetIsChecked(Rules.bLaneAssist);
}

void UMyLobbyWidget::ReadRulesFromControls(FMyMatchRules& OutRules, int32& OutMaxPlayers) const
{
	if (TeamModeComboBox && TeamModeOptions.IsValidIndex(TeamModeComboBox->GetSelectedIndex()))
	{
		OutRules.TeamMode = TeamModeOptions[TeamModeComboBox->GetSelectedIndex()];
	}
	if (ShipLivesComboBox && ShipLivesOptions.IsValidIndex(ShipLivesComboBox->GetSelectedIndex()))
	{
		OutRules.ShipLives = ShipLivesOptions[ShipLivesComboBox->GetSelectedIndex()];
	}
	if (SwarmComboBox && SwarmOptions.IsValidIndex(SwarmComboBox->GetSelectedIndex()))
	{
		OutRules.SwarmDifficulty = SwarmOptions[SwarmComboBox->GetSelectedIndex()];
	}
	if (TimeLimitComboBox && TimeLimitOptions.IsValidIndex(TimeLimitComboBox->GetSelectedIndex()))
	{
		OutRules.TimeLimitMinutes = TimeLimitOptions[TimeLimitComboBox->GetSelectedIndex()];
	}
	if (MaxPlayersComboBox && MaxPlayerOptions.IsValidIndex(MaxPlayersComboBox->GetSelectedIndex()))
	{
		OutMaxPlayers = MaxPlayerOptions[MaxPlayersComboBox->GetSelectedIndex()];
	}
	if (FriendlyFireCheckBox) OutRules.bFriendlyFire = FriendlyFireCheckBox->IsChecked();
	if (GrappleShipsCheckBox) OutRules.bGrappleShips = GrappleShipsCheckBox->IsChecked();
	if (LaneAssistCheckBox)   OutRules.bLaneAssist = LaneAssistCheckBox->IsChecked();

	// 1v1 and 2v2 have room for exactly their players (the server sets it too)
	const int32 ModeMax = UMyTeamLibrary::GetTeamModeMaxPlayers(OutRules.TeamMode);
	if (ModeMax > 0)
	{
		OutMaxPlayers = ModeMax;
	}
}

EMyTeamMode UMyLobbyWidget::GetSelectedTeamMode() const
{
	if (TeamModeComboBox && TeamModeOptions.IsValidIndex(TeamModeComboBox->GetSelectedIndex()))
	{
		return TeamModeOptions[TeamModeComboBox->GetSelectedIndex()];
	}

	const AMyGameState* GameState = GetLobbyGameState();
	return GameState ? GameState->GetMatchRules().TeamMode : EMyTeamMode::Auto;
}

void UMyLobbyWidget::RefreshMaxPlayersLock(EMyTeamMode Mode, bool bHostCanEdit)
{
	if (!MaxPlayersComboBox)
	{
		return;
	}

	const int32 ModeMax = UMyTeamLibrary::GetTeamModeMaxPlayers(Mode);
	const bool bWasLocked = bMaxPlayersLocked;
	bMaxPlayersLocked = ModeMax > 0;

	// As the host menu (UMainMenu3::RefreshMaxPlayersForRules): the free value is kept while a 1v1 / 2v2 forces the box,
	// and comes back when the host picks a mode without a fixed size. Only for his own edit: a mode that came in
	// replicated brings its Max Players with it (ApplyRulesToControls)
	if (bMaxPlayersLocked && !bWasLocked)
	{
		FreeMaxPlayers = (bRulesDirty && MaxPlayerOptions.IsValidIndex(MaxPlayersComboBox->GetSelectedIndex()))
			? MaxPlayerOptions[MaxPlayersComboBox->GetSelectedIndex()] : 0;
	}

	if (bMaxPlayersLocked && !MaxPlayersComboBox->IsOpen())
	{
		SetComboToInt(MaxPlayersComboBox, MaxPlayerOptions, ModeMax, false);
	}
	else if (!bMaxPlayersLocked && bWasLocked)
	{
		if (bRulesDirty && FreeMaxPlayers > 0 && !MaxPlayersComboBox->IsOpen())
		{
			SetComboToInt(MaxPlayersComboBox, MaxPlayerOptions, FreeMaxPlayers, false);
		}
		FreeMaxPlayers = 0;
	}

	MyLobbyWidgetPrivate::SetEnabled(MaxPlayersComboBox, bHostCanEdit && !bMaxPlayersLocked);
}

void UMyLobbyWidget::RefreshRules(const AMyGameState* GameState, bool bCounting)
{
	const bool bHost = IsHostView();
	const bool bCanEdit = bHost && !bCounting && GameState->GetMatchPhase() == EMyMatchPhase::Lobby;

	// A host edit waiting to be sent keeps what he picked
	if (!bRulesDirty)
	{
		ApplyRulesToControls(GameState->GetMatchRules(), GameState->GetExpectedPlayers());
	}

	for (UWidget* Control : TArray<UWidget*>{ TeamModeComboBox, ShipLivesComboBox, SwarmComboBox, TimeLimitComboBox,
		FriendlyFireCheckBox, GrappleShipsCheckBox, LaneAssistCheckBox })
	{
		MyLobbyWidgetPrivate::SetEnabled(Control, bCanEdit);
	}

	RefreshMaxPlayersLock(bRulesDirty ? GetSelectedTeamMode() : GameState->GetMatchRules().TeamMode, bCanEdit);

	if (RulesHintText && RulesHintTimeLeft <= 0.f)
	{
		MyLobbyWidgetPrivate::SetTextIfChanged(RulesHintText, bCounting ? LOCTEXT("RulesLocked", "Locked while the match starts")
			: (bHost ? LOCTEXT("RulesHost", "Changes apply for everyone") : LOCTEXT("RulesClient", "Set by the host")));
	}
}

void UMyLobbyWidget::OnTeamModeChanged(FString SelectedItem, ESelectInfo::Type SelectionType)
{
	if (SelectionType == ESelectInfo::Direct)
	{
		return;
	}

	// 1v1 / 2v2 lock Max Players at once, as the host menu does. Dirty first: the lock keeps the free value only for the
	// host's own edit
	MarkRulesDirty();
	RefreshMaxPlayersLock(GetSelectedTeamMode(), true);
}

void UMyLobbyWidget::OnRuleComboChanged(FString SelectedItem, ESelectInfo::Type SelectionType)
{
	if (SelectionType != ESelectInfo::Direct)
	{
		MarkRulesDirty();
	}
}

void UMyLobbyWidget::OnRuleCheckChanged(bool bIsChecked)
{
	MarkRulesDirty();
}

void UMyLobbyWidget::MarkRulesDirty()
{
	if (!IsHostView())
	{
		return;
	}

	bRulesDirty = true;
	RulesSendTimeLeft = RulesSendDelay;
}

void UMyLobbyWidget::SendRules()
{
	bRulesDirty = false;

	const AMyGameState* GameState = GetLobbyGameState();
	AMyPlayerController2* PC = GetLobbyController();

	if (!GameState || !PC)
	{
		return;
	}

	FMyMatchRules Rules = GameState->GetMatchRules();
	int32 MaxPlayers = GameState->GetExpectedPlayers();
	ReadRulesFromControls(Rules, MaxPlayers);

	LastRulesSendTime = WidgetTime;
	UE_LOG(LogMatch, Log, TEXT("Lobby panel: rules request Teams=%s ShipLives=%d Swarm=%d TimeLimit=%d FF=%d Hook=%d Assist=%d Players=%d"),
		UMyTeamLibrary::GetTeamModeOption(Rules.TeamMode), Rules.ShipLives, Rules.SwarmDifficulty, Rules.TimeLimitMinutes,
		Rules.bFriendlyFire ? 1 : 0, Rules.bGrappleShips ? 1 : 0, Rules.bLaneAssist ? 1 : 0, MaxPlayers);
	PC->ServerLobbySetRules(Rules, MaxPlayers);
	bRefreshPending = true;
}

// -------------------------------------------------------------------------------------------------------------------
// Actions
// -------------------------------------------------------------------------------------------------------------------

FText UMyLobbyWidget::GetStartLabel(const AMyGameState* GameState, bool bCounting) const
{
	if (bCounting)
	{
		return LOCTEXT("StartCancel", "CANCEL");
	}

	const EMyTeamMode Mode = GameState->GetMatchRules().TeamMode;
	const int32 Blue = GameState->GetTeamState(0).NumPlayers;
	const int32 Orange = GameState->GetTeamState(1).NumPlayers;

	if (Mode == EMyTeamMode::Practice)
	{
		return LOCTEXT("StartPractice", "START PRACTICE (ONE SHIP)");
	}
	if (Blue > 0 && Orange > 0)
	{
		return FText::Format(LOCTEXT("StartVersus", "START {0}v{1}"), Blue, Orange);
	}
	if (Mode == EMyTeamMode::OneVsOne || Mode == EMyTeamMode::TwoVsTwo)
	{
		return FText::Format(LOCTEXT("StartMode", "START {0}"), FText::FromString(UMyTeamLibrary::GetTeamModeOption(Mode)));
	}
	// Auto: one player is practice, more on one team play co-op on one ship
	return Blue + Orange <= 1 ? LOCTEXT("StartPracticeAuto", "START PRACTICE (ONE SHIP)") : LOCTEXT("StartCoop", "START CO-OP (ONE SHIP)");
}

void UMyLobbyWidget::RefreshActions(const AMyGameState* GameState, bool bCounting)
{
	const bool bHost = IsHostView();
	const bool bPhaseLobby = GameState->GetMatchPhase() == EMyMatchPhase::Lobby;
	const EMyLobbyStartBlock Block = GameState->GetLobbyStartBlock();
	const int32 NotReady = GameState->GetLobbyNotReady();
	const FText BlockText = UMyTeamLibrary::GetLobbyStartBlockText(this, Block, NotReady);
	const bool bHard = Block != EMyLobbyStartBlock::None && UMyTeamLibrary::IsHardLobbyStartBlock(Block);
	// What the second click confirms: every block counts, not only the first (a rematch drops NotReady only)
	const EMyLobbyStartBlock Confirm = bHard ? EMyLobbyStartBlock::None : GameState->GetLobbyConfirmBlock();
	const FText ConfirmText = UMyTeamLibrary::GetLobbyStartBlockText(this, Confirm, NotReady);

	// A changed block asks again
	if (Confirm != ConfirmBlock)
	{
		StartConfirmTimeLeft = 0.f;
	}

	// READY: clients only
	if (ReadyButton)
	{
		SetButtonShown(ReadyButton, !bHost);
		MyLobbyWidgetPrivate::SetEnabled(ReadyButton, !bHost && bPhaseLobby);

		if (!bHost)
		{
			const AMyPlayerState* Local = GetLocalPlayerState();
			MyLobbyWidgetPrivate::SetTextIfChanged(ReadyText, Local && Local->IsLobbyReady() ? LOCTEXT("NotReady", "NOT READY") : LOCTEXT("Ready", "READY"));
		}
	}

	// START: the host only, naming what starts; CANCEL while counting down
	if (StartButton)
	{
		SetButtonShown(StartButton, bHost);
		MyLobbyWidgetPrivate::SetEnabled(StartButton, bHost && (bCounting || (bPhaseLobby && !bHard)));
	}

	if (bHost)
	{
		MyLobbyWidgetPrivate::SetTextIfChanged(StartText, GetStartLabel(GameState, bCounting));
	}

	if (StartReasonText)
	{
		FText Reason;

		if (bCounting)
		{
			Reason = bHost ? LOCTEXT("ReasonCancel", "Cancel goes back to the lobby") : FText::GetEmpty();
		}
		else if (bHost)
		{
			if (Block == EMyLobbyStartBlock::None)
			{
				Reason = FText::GetEmpty();
			}
			else if (bHard)
			{
				Reason = BlockText;
			}
			else if (Confirm == EMyLobbyStartBlock::None)
			{
				// Only NotReady, in a rematch: the first click starts
				Reason = FText::Format(LOCTEXT("ReasonRematch", "{0} (same teams as last match)"), BlockText);
			}
			else if (StartConfirmTimeLeft > 0.f)
			{
				Reason = FText::Format(LOCTEXT("ReasonConfirm", "{0} - click again to start anyway"), ConfirmText);
			}
			else
			{
				Reason = ConfirmText;
			}
		}
		else
		{
			Reason = Block == EMyLobbyStartBlock::None || Block == EMyLobbyStartBlock::NotReady
				? LOCTEXT("ReasonWaitHost", "Waiting for the host to start")
				: FText::Format(LOCTEXT("ReasonWaitHostBlock", "Waiting for the host to start ({0})"), BlockText);
		}

		MyLobbyWidgetPrivate::SetTextIfChanged(StartReasonText, Reason);
	}
}

void UMyLobbyWidget::StartButtonClicked()
{
	const AMyGameState* GameState = GetLobbyGameState();
	AMyPlayerController2* PC = GetLobbyController();

	if (!GameState || !PC || !IsHostView())
	{
		return;
	}

	if (GameState->IsLobbyCountingDown())
	{
		PC->ServerLobbyCancelStart();
		return;
	}

	// A rules edit still waiting goes first: the host is the server, so it applies now, and the start below reads the
	// blocks it leaves (ApplyLobbyRules refuses anything once the countdown runs)
	if (bRulesDirty)
	{
		const int32 MessagesBefore = LobbyMessageCount;
		SendRules();

		// A refusal answers at once on the host (ClientLobbyMessage on a local controller) and shows: no start with rules
		// he didn't pick
		if (LobbyMessageCount != MessagesBefore)
		{
			UE_LOG(LogMatch, Log, TEXT("Lobby panel: START held, the rules edit sent with it was refused"));
			bRefreshPending = true;
			return;
		}
	}

	const EMyLobbyStartBlock Block = GameState->GetLobbyStartBlock();

	if (Block != EMyLobbyStartBlock::None && UMyTeamLibrary::IsHardLobbyStartBlock(Block))
	{
		ShowMessage(UMyTeamLibrary::GetLobbyStartBlockText(this, Block, GameState->GetLobbyNotReady()));
		return;
	}

	// A soft block needs a second click, except NotReady in a rematch (the host accepted these teams last match): the
	// server's own decision over every block (GetLobbyConfirmBlock), not only the first one
	const EMyLobbyStartBlock Confirm = GameState->GetLobbyConfirmBlock();
	const bool bNeedsConfirm = Confirm != EMyLobbyStartBlock::None;

	if (bNeedsConfirm && (StartConfirmTimeLeft <= 0.f || Confirm != ConfirmBlock))
	{
		StartConfirmTimeLeft = StartConfirmSeconds;
		ConfirmBlock = Confirm;
		RefreshActions(GameState, false);
		return;
	}

	StartConfirmTimeLeft = 0.f;
	UE_LOG(LogMatch, Log, TEXT("Lobby panel: START (%s, confirm %s, force %d)"), *UEnum::GetValueAsString(Block), *UEnum::GetValueAsString(Confirm), bNeedsConfirm ? 1 : 0);
	PC->ServerLobbyStart(bNeedsConfirm);
	bRefreshPending = true;
}

void UMyLobbyWidget::ReadyButtonClicked()
{
	const AMyPlayerState* Local = GetLocalPlayerState();

	if (AMyPlayerController2* PC = GetLobbyController())
	{
		PC->ServerLobbySetReady(!(Local && Local->IsLobbyReady()));
		bRefreshPending = true;
	}
}

void UMyLobbyWidget::SwitchTeamButtonClicked()
{
	const AMyPlayerState* Local = GetLocalPlayerState();
	AMyPlayerController2* PC = GetLobbyController();

	if (!Local || !PC || Local->GetTeamId() >= MyMatch::NumTeams)
	{
		return;
	}

	const uint8 Team = Local->GetTeamId();
	const uint8 Requested = Local->GetRequestedTeam();

	// A pending request: cancel it; else ask for the other team (a move, a swap, or pending)
	PC->ServerLobbyRequestTeam(Requested < MyMatch::NumTeams && Requested != Team ? MyMatch::NoTeam : static_cast<uint8>(1 - Team));
	bRefreshPending = true;
}

void UMyLobbyWidget::RequestMovePlayer(AMyPlayerState* Player)
{
	AMyPlayerController2* PC = GetLobbyController();

	if (!Player || !PC || !IsHostView() || Player->GetTeamId() >= MyMatch::NumTeams)
	{
		return;
	}

	PC->ServerLobbyMovePlayer(Player, static_cast<uint8>(1 - Player->GetTeamId()));
	bRefreshPending = true;
}

void UMyLobbyWidget::CopyCodeButtonClicked()
{
	const FString Code = GetJoinCode(nullptr);

	if (!Code.IsEmpty())
	{
		FPlatformApplicationMisc::ClipboardCopy(*Code);
		ShowMessage(LOCTEXT("CodeCopied", "Join code copied to the clipboard"));
	}
}

void UMyLobbyWidget::CloseButtonClicked()
{
	ClosePanel();
}

void UMyLobbyWidget::MenuButtonClicked()
{
	ClosePanel();

	if (AMyPlayerController2* PC = GetLobbyController())
	{
		PC->OpenPauseMenu();
	}
}

void UMyLobbyWidget::LeaveButtonClicked()
{
	ClosePanel();

	// The pause menu's Leave Session confirm: the host-left kick stays in one place
	if (AMyPlayerController2* PC = GetLobbyController())
	{
		PC->OpenLeaveSessionConfirm();
	}
}

#undef LOCTEXT_NAMESPACE
