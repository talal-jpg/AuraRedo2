// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "UI/UserWidgets/MyUserWidget.h"
#include "EOS/MenuButtonFX.h"
#include "Match/MyLobbyPanel.h"
#include "Match/MyMatchTypes.h"
#include "Types/SlateEnums.h"
#include "MyLobbyWidget.generated.h"

class AMyGameState;
class AMyPlayerController2;
class AMyPlayerState;
class APlayerState;
class UButton;
class UCheckBox;
class UComboBoxString;
class UMyLobbyPlayerRow;
class UPanelWidget;
class UTextBlock;
class UWidget;

/**
 * The in-level lobby's UI (Docs/Airship/round2/SPEC_B_LOBBY.md section 6): teams with ready flags and pings, the host's
 * rules, READY / START / CLOSE / MENU / LEAVE, the join code; a compact strip while the panel is closed; the big
 * "MATCH STARTS IN n" of the lobby countdown. AMyHUD adds it for local controllers (LobbyWidgetClass, WBP_Lobby3 built by
 * as_77) over the whole viewport. It registers itself with AMyPlayerController2::SetLobbyPanel, so Esc in the lobby opens
 * and closes the panel (TogglePauseMenu); with the panel open (UI-only input) it closes itself on Esc / gamepad B.
 *
 * Reads only replicated state (AMyGameState's lobby fields, rules, team counts; AMyPlayerState's team, ready, request,
 * host flag) and sends every change through the controller's Server RPCs, so the listen host's panel takes the same route
 * as a client's. Controls are set with ESelectInfo::Direct and the change handlers ignore Direct: a refresh never sends a
 * request. Every widget is BindWidgetOptional; without PlayerRowClass the team lists get one plain text line per player.
 *
 * Shows nothing outside the lobby (IsInLobby false): the root stays hit-test invisible and keeps ticking, so a game state
 * that replicates late still brings it up.
 */
UCLASS()
class AURA_API UMyLobbyWidget : public UMyUserWidget, public IMyLobbyPanel
{
	GENERATED_BODY()

public:

	// IMyLobbyPanel
	/** The full panel, UI-only input focused on it, cursor on (as UPauseMenu3::OpenMenu). Lobby only. */
	virtual void OpenPanel() override;
	/** Back to the compact strip, game-only input, cursor as it was (as UPauseMenu3::CloseMenu). Sends a pending rules edit. */
	virtual void ClosePanel() override;
	virtual bool IsPanelOpen() const override { return bPanelOpen; }

	/** A row's MOVE (host view): the player to the other team, a swap when that team is full. */
	void RequestMovePlayer(AMyPlayerState* Player);

	/** This machine's player is the host (his player state's flag, or the listen server's / standalone local player). */
	bool IsHostView() const;

	/** The players each team has room for, for the headers ("BLUE  2 / 2") and the rows' MOVE label; 0 = no cap. */
	int32 GetDisplayTeamCap(uint8 TeamId) const;

	AMyGameState* GetLobbyGameState() const;

	/**
	 * Shows or hides a button together with what is drawn with it: as_77's archetypes put the button, its label and its
	 * graffiti slab or ring in an Item_<key> overlay (a word inside a Wrap_<key> box). Climbs those parents while they hold
	 * no other button and collapses the outermost; the button itself stays Visible inside it. Without such a parent it is
	 * the button alone (any designer layout).
	 */
	static void SetButtonShown(UWidget* Button, bool bShown);

	/** SetButtonShown's target: the outermost Item_ / Wrap_ parent of Button that holds no other button, else Button. */
	static UWidget* FindButtonItem(UWidget* Button);

protected:

	virtual bool Initialize() override;
	virtual void NativeConstruct() override;
	virtual void NativeDestruct() override;
	virtual void NativeTick(const FGeometry& MyGeometry, float InDeltaTime) override;
	virtual FReply NativeOnKeyDown(const FGeometry& InGeometry, const FKeyEvent& InKeyEvent) override;

	/** Blueprint hook: the panel opened (true) or closed (false), for an animation or a sound. */
	UFUNCTION(BlueprintImplementableEvent, Category = "Lobby")
	void OnPanelToggled(bool bOpen);

	UPROPERTY(EditAnywhere, Category = "Aura|Menu|Graffiti")
	FAuraMenuButtonFXSettings ButtonFX;

	//
	// Views
	//
	/** The full panel (teams, rules, actions). */
	UPROPERTY(meta = (BindWidgetOptional))
	UWidget* LobbyPanel;
	/** The strip while the panel is closed: "LOBBY   BLUE 2 - ORANGE 1   1 NOT READY   Esc: lobby". */
	UPROPERTY(meta = (BindWidgetOptional))
	UWidget* CompactPanel;
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* CompactText;
	/** "MATCH STARTS IN n" while the lobby counts down (both views). */
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* CountdownText;
	/** "Esc: lobby" / the host's "Esc: lobby (CANCEL)" during the countdown, panel closed. */
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* CountdownHintText;
	/** ClientLobbyMessage (refusals, the zone, swaps) for MessageSeconds. */
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* MessageText;

	//
	// Header
	//
	/** The lobby's name ("Talal's lobby"), or "Local game" without a session. */
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* TitleText;
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* JoinCodeText;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* CopyCodeButton;

	//
	// Teams
	//
	/** "BLUE  2 / 2" in the team colour. */
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* BlueHeaderText;
	/** Rows of PlayerRowClass. */
	UPROPERTY(meta = (BindWidgetOptional))
	UPanelWidget* BlueList;
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* OrangeHeaderText;
	UPROPERTY(meta = (BindWidgetOptional))
	UPanelWidget* OrangeList;
	/** The local player's switch request (hidden in practice). */
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* SwitchTeamButton;
	/** SWITCH TO ORANGE / CANCEL SWITCH. */
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* SwitchTeamText;

	//
	// Rules (the host edits; clients see them disabled)
	//
	UPROPERTY(meta = (BindWidgetOptional))
	UWidget* RulesPanel;
	/** UMainMenu3's RuleSets; the Practice entry reads PracticeRuleLabel. */
	UPROPERTY(meta = (BindWidgetOptional))
	UComboBoxString* TeamModeComboBox;
	/** UMainMenu3's ShipLivesChoices. */
	UPROPERTY(meta = (BindWidgetOptional))
	UComboBoxString* ShipLivesComboBox;
	/** UMainMenu3's DifficultyNames (index = Rules.SwarmDifficulty). */
	UPROPERTY(meta = (BindWidgetOptional))
	UComboBoxString* SwarmComboBox;
	/** UMainMenu3's MaxPlayerChoices; 1v1 and 2v2 set and lock it. */
	UPROPERTY(meta = (BindWidgetOptional))
	UComboBoxString* MaxPlayersComboBox;
	/** TimeLimitChoices (minutes, 0 = none). */
	UPROPERTY(meta = (BindWidgetOptional))
	UComboBoxString* TimeLimitComboBox;
	UPROPERTY(meta = (BindWidgetOptional))
	UCheckBox* FriendlyFireCheckBox;
	UPROPERTY(meta = (BindWidgetOptional))
	UCheckBox* GrappleShipsCheckBox;
	UPROPERTY(meta = (BindWidgetOptional))
	UCheckBox* LaneAssistCheckBox;
	/** Clients: "Set by the host"; the host: a refusal of his last edit; the countdown: locked. */
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* RulesHintText;

	//
	// Actions
	//
	/** Clients only (the host has no ready flag). */
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* ReadyButton;
	/** READY (press to be ready) / NOT READY (press to take it back). */
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* ReadyText;
	/** Host only. */
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* StartButton;
	/** START 2v1 / START CO-OP (ONE SHIP) / START PRACTICE (ONE SHIP) / CANCEL. */
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* StartText;
	/** The start block's reason, the "click again" hint, or the clients' "Waiting for the host to start". */
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* StartReasonText;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* CloseButton;
	/** Closes the panel and opens the pause menu. */
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* MenuButton;
	/** The pause menu's Leave Session confirm. */
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* LeaveButton;

	//
	// Settings
	//
	UPROPERTY(EditAnywhere, Category = "Lobby")
	TSubclassOf<UMyLobbyPlayerRow> PlayerRowClass;

	/** Minutes; 0 = no time limit. A rules value not in the list is added to the box. */
	UPROPERTY(EditAnywhere, Category = "Lobby")
	TArray<int32> TimeLimitChoices = { 0, 5, 10, 15, 20, 30 };

	/** Seconds between refreshes (also on every AMyGameState::OnMatchChanged). */
	UPROPERTY(EditAnywhere, Category = "Lobby", meta = (ClampMin = "0.05"))
	float RefreshInterval = 0.25f;

	/** A soft start block: the first click shows "click again to start anyway" for this long. */
	UPROPERTY(EditAnywhere, Category = "Lobby", meta = (ClampMin = "0.5"))
	float StartConfirmSeconds = 3.f;

	/** The host's rules edits go out as one request this long after the last one. */
	UPROPERTY(EditAnywhere, Category = "Lobby", meta = (ClampMin = "0.0"))
	float RulesSendDelay = 0.75f;

	/** How long MessageText shows a lobby message. */
	UPROPERTY(EditAnywhere, Category = "Lobby", meta = (ClampMin = "0.5"))
	float MessageSeconds = 3.f;

	/** Opens the panel once per map load, when the local player's lobby pawn first exists in phase Lobby. */
	UPROPERTY(EditAnywhere, Category = "Lobby")
	bool bAutoOpen = true;

	/** The Practice entry of the team mode box. */
	UPROPERTY(EditAnywhere, Category = "Lobby")
	FText PracticeRuleLabel = NSLOCTEXT("MyLobby", "PracticeRuleLabel", "Practice (co-op, one ship)");

private:

	//
	// Handlers
	//
	UFUNCTION()
	void CopyCodeButtonClicked();
	UFUNCTION()
	void SwitchTeamButtonClicked();
	UFUNCTION()
	void ReadyButtonClicked();
	UFUNCTION()
	void StartButtonClicked();
	UFUNCTION()
	void CloseButtonClicked();
	UFUNCTION()
	void MenuButtonClicked();
	UFUNCTION()
	void LeaveButtonClicked();
	UFUNCTION()
	void OnTeamModeChanged(FString SelectedItem, ESelectInfo::Type SelectionType);
	UFUNCTION()
	void OnRuleComboChanged(FString SelectedItem, ESelectInfo::Type SelectionType);
	UFUNCTION()
	void OnRuleCheckChanged(bool bIsChecked);

	void HandleMatchChanged();
	void HandleLobbyMessage(const FText& Text);

	//
	// Refresh
	//
	void BindGameState();
	void UnbindGameState();
	void BindController();
	void UnbindController();
	void Refresh();
	void RefreshViews(bool bInLobby, bool bCounting);
	void RefreshRows(const AMyGameState* GameState);
	void RefreshHeader();
	void RefreshTeams(const AMyGameState* GameState, bool bCounting);
	void RefreshRules(const AMyGameState* GameState, bool bCounting);
	void RefreshActions(const AMyGameState* GameState, bool bCounting);
	void RefreshCompact(const AMyGameState* GameState, bool bCounting);
	void RefreshCountdown(const AMyGameState* GameState);
	void RebuildRows(const TArray<AMyPlayerState*>& Players);
	void RefreshRowTexts();

	/** The team mode, lives, swarm, Max Players and time limit boxes from UMainMenu3's lists (once, NativeConstruct). */
	void FillRuleOptions();
	/** Rules -> the controls (ESelectInfo::Direct), unless a host edit waits to be sent or a box is open. */
	void ApplyRulesToControls(const struct FMyMatchRules& Rules, int32 MaxPlayers);
	/** The controls -> rules (the replicated rules for anything the panel has no control for). */
	void ReadRulesFromControls(struct FMyMatchRules& OutRules, int32& OutMaxPlayers) const;
	void SetComboToInt(UComboBoxString* Combo, TArray<int32>& Values, int32 Value, bool bTimeLimit);
	EMyTeamMode GetSelectedTeamMode() const;
	/** 1v1 / 2v2 set Max Players to their count and lock the box; else free (host only). */
	void RefreshMaxPlayersLock(EMyTeamMode Mode, bool bHostCanEdit);
	void MarkRulesDirty();
	void SendRules();

	FText GetStartLabel(const AMyGameState* GameState, bool bCounting) const;
	FString GetJoinCode(FString* OutLobbyName) const;
	void ShowMessage(const FText& Text);
	bool IsAnyComboOpen() const;

	AMyPlayerController2* GetLobbyController() const;
	AMyPlayerState* GetLocalPlayerState() const;

	//
	// State
	//
	TWeakObjectPtr<AMyGameState> GameStateWeak;
	FDelegateHandle MatchChangedHandle;
	TWeakObjectPtr<AMyPlayerController2> ControllerWeak;
	FDelegateHandle LobbyMessageHandle;

	UPROPERTY()
	TArray<TObjectPtr<UMyLobbyPlayerRow>> Rows;

	/** Without PlayerRowClass: one text line per player, updated in place. */
	UPROPERTY()
	TArray<TObjectPtr<UTextBlock>> FallbackRows;
	TArray<TWeakObjectPtr<AMyPlayerState>> FallbackRowPlayers;

	/** (PlayerId, TeamId, arriving) per shown player, the local player state and the host view: rows are rebuilt only when it changes. */
	FString RowSignature;

	// Option values in box order
	TArray<EMyTeamMode> TeamModeOptions;
	TArray<int32> ShipLivesOptions;
	TArray<int32> MaxPlayerOptions;
	TArray<int32> TimeLimitOptions;
	TArray<int32> SwarmOptions;

	bool bPanelOpen = false;
	bool bCursorWasShown = false;
	bool bAutoOpenDone = false;
	bool bWasInLobby = false;
	bool bWasCounting = false;
	bool bRefreshPending = true;
	bool bRulesDirty = false;
	bool bMaxPlayersLocked = false;
	/** The Max Players the box showed before a 1v1 / 2v2 the host picked forced it (put back when he picks a mode without a fixed size); 0 = none. */
	int32 FreeMaxPlayers = 0;
	int32 LastCountdownSecond = -1;
	EMyLobbyStartBlock ConfirmBlock = EMyLobbyStartBlock::None;

	float RefreshTimer = 0.f;
	float RulesSendTimeLeft = 0.f;
	float StartConfirmTimeLeft = 0.f;
	float MessageTimeLeft = 0.f;
	float RulesHintTimeLeft = 0.f;
	/** Widget time of the last rules request: a message right after it is its answer (shown in RulesHintText too). */
	float LastRulesSendTime = -100.f;
	float WidgetTime = 0.f;
	/** Lobby messages received (StartButtonClicked: did the rules edit it sent first get refused?). */
	int32 LobbyMessageCount = 0;

	FAuraMenuButtonFX ButtonFXState;
};
