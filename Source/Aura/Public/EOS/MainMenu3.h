// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Interfaces/OnlineSessionInterface.h"
#include "UI/UserWidgets/MyUserWidget.h"
#include "EOS/MultiplayerSessionTypes.h"
#include "EOS/MenuButtonFX.h"
#include "Types/SlateEnums.h"
#include "MainMenu3.generated.h"

class UButton;
class UCheckBox;
class UWidget;
class UWidgetSwitcher;
class UPanelWidget;
class UComboBoxString;
class UEditableTextBox;
class UScrollBox;
class UTextBlock;
class UMultiplayerSessionsSubsystem;
class USessionEntry3;
class USettingsMenu3;

// What the Confirm panel's Yes does
enum class EMainMenu3ConfirmAction : uint8
{
	None,
	Quit,
	JoinLobby
};

// A search asked for while a browse refresh was still running
enum class EMainMenu3QueuedSearch : uint8
{
	None,
	Refresh,
	CodeLookup,
	QuickJoin
};

/**
 * Full front end in the Far Far West layout: title screen, Create Session, Browse Sessions
 * (filters, refresh, quick join, join with code + "join this lobby?" confirm), Tutorial,
 * Options, Credits and Quit.
 *
 * Same convention as UMainMenu2: one UWidgetSwitcher "MenuSwitcher" holding a panel per
 * screen, every widget bound with BindWidgetOptional, and a visibility fallback when there is
 * no switcher. Panels: TitlePanel, HomePanel, HostPanel, BrowsePanel, CodePanel, BusyPanel,
 * ConfirmPanel, OptionsPanel (or OptionsMenu itself), CreditsPanel. Esc / gamepad B goes back.
 *
 * Talks to the same UMultiplayerSessionsSubsystem as UMainMenu / UMainMenu2, which keep working.
 */
UCLASS()
class AURA_API UMainMenu3 : public UMyUserWidget
{
	GENERATED_BODY()

public:
	// Same signature as UMainMenu2::MenuSetup, so the level blueprint call only changes class.
	UFUNCTION(BlueprintCallable)
	void MenuSetup(int32 NumberOfPublicConnections = 4, FString TypeOfMatch = FString(TEXT("FreeForAll")), FString LobbyPath = FString(TEXT("/Game/ThirdPersonCPP/Maps/Lobby")));

	// Called by a spawned USessionEntry3 row when its Join button is clicked.
	UFUNCTION(BlueprintCallable)
	void JoinLobbyByIndex(int32 ResultIndex);

	// A message box with only OK, on top of whatever panel is open (disconnect reasons, errors).
	UFUNCTION(BlueprintCallable, Category = "Aura|Menu")
	void ShowMessage(const FText& Title, const FText& Message);

	// DifficultyNames[Difficulty], or "Difficulty N" past the end of the list.
	UFUNCTION(BlueprintPure, Category = "Aura|Menu")
	FText GetDifficultyName(int32 Difficulty) const;

protected:
	virtual bool Initialize() override;
	virtual void NativeConstruct() override;
	virtual void NativeTick(const FGeometry& MyGeometry, float InDeltaTime) override;
	virtual void NativeDestruct() override;
	virtual FReply NativeOnKeyDown(const FGeometry& InGeometry, const FKeyEvent& InKeyEvent) override;
	virtual FReply NativeOnMouseButtonDown(const FGeometry& InGeometry, const FPointerEvent& InMouseEvent) override;

	UPROPERTY(EditAnywhere, Category = "Aura|Menu|Graffiti")
	FAuraMenuButtonFXSettings ButtonFX;

	// Start on the "press any key" TitlePanel. Off, or no TitlePanel bound = straight to HomePanel.
	UPROPERTY(EditAnywhere, Category = "Aura|Menu")
	bool bShowTitleScreen = true;

	// Map the Tutorial button opens, offline. Empty hides the button.
	UPROPERTY(EditAnywhere, Category = "Aura|Menu")
	FString TutorialMapPath;

	// Difficulty names, index = the Difficulty number stored on the session.
	UPROPERTY(EditAnywhere, Category = "Aura|Menu")
	TArray<FString> DifficultyNames = { TEXT("Easy"), TEXT("Normal"), TEXT("Hard"), TEXT("Very Hard"), TEXT("Nightmare") };

	// Difficulty a new lobby starts on (index into DifficultyNames).
	UPROPERTY(EditAnywhere, Category = "Aura|Menu")
	int32 DefaultDifficulty = 1;

	// Rule sets offered when hosting and filtering. The first one is the default.
	UPROPERTY(EditAnywhere, Category = "Aura|Menu")
	TArray<FString> RuleSets = { TEXT("Default") };

	// Choices of the Max Players box. MenuSetup's NumberOfPublicConnections is preselected.
	UPROPERTY(EditAnywhere, Category = "Aura|Menu")
	TArray<int32> MaxPlayerChoices = { 1, 2, 3, 4 };

	// Pixels per second the credits scroll by themselves.
	UPROPERTY(EditAnywhere, Category = "Aura|Menu")
	float CreditsScrollSpeed = 40.f;

	UPROPERTY(EditDefaultsOnly, Category = "Aura|Menu")
	TSubclassOf<USessionEntry3> SessionEntryClass;

	//
	// Subsystem callbacks
	//
	UFUNCTION()
	void OnCreateSession(bool bWasSuccessful);
	void OnSessionsFound(const TArray<FAuraSessionInfo>& SessionInfos, bool bWasSuccessful);
	void OnJoinSession(EOnJoinSessionCompleteResult::Type Result);
	UFUNCTION()
	void OnInviteAccepted(bool bWasSuccessful);
	UFUNCTION()
	void OnSessionError(const FString& Message);
	UFUNCTION()
	void OnFindSessionsCancelled();

	// Blueprint hook so the browse list can be re-skinned in UMG without touching C++.
	UFUNCTION(BlueprintImplementableEvent, Category = "Aura|Menu")
	void OnLobbyListUpdated(const TArray<FAuraSessionInfo>& SessionInfos);

	// Blueprint hook for panel transition animations / sounds.
	UFUNCTION(BlueprintImplementableEvent, Category = "Aura|Menu")
	void OnPanelChanged(UWidget* NewPanel);

private:
	//
	// Panel switching. Busy and Confirm are overlays: they never go on the back stack, so
	// closing them returns to the screen that opened them.
	//
	void ShowPanel(UWidget* PanelToShow);
	// Switches to Panel without touching the back stack
	void ActivatePanel(UWidget* Panel);
	void GoBack();
	// Esc / gamepad B
	void HandleBack();
	void ClearHistory();
	bool IsOverlayPanel(const UWidget* Panel) const;
	TArray<UWidget*> GetAllPanels() const;
	void SetStatus(const FText& Message);

	UPROPERTY()
	TArray<UWidget*> PanelHistory;
	UPROPERTY()
	UWidget* CurrentPanel;

	//
	// Title
	//
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* PressAnyKeyText;
	float TitleTime{ 0.f };
	void LeaveTitleScreen();

	//
	// Home
	//
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* CreateSessionButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* BrowseSessionsButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* TutorialButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* OptionsButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* CreditsButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* QuitButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* VersionText;
	// "Online as <name>" or the red "can't reach the online service" warning
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* OnlineStatusText;

	UFUNCTION()
	void CreateSessionButtonClicked();
	UFUNCTION()
	void BrowseSessionsButtonClicked();
	UFUNCTION()
	void TutorialButtonClicked();
	UFUNCTION()
	void OptionsButtonClicked();
	UFUNCTION()
	void CreditsButtonClicked();
	UFUNCTION()
	void QuitButtonClicked();
	void RefreshOnlineStatus();

	//
	// Host panel (Create Session)
	//
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* PrivacyPublicButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* PrivacyFriendsOnlyButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* PrivacyCodeOnlyButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* PrivacyLabelText;
	UPROPERTY(meta = (BindWidgetOptional))
	UEditableTextBox* LobbyNameTextBox;
	UPROPERTY(meta = (BindWidgetOptional))
	UComboBoxString* MaxPlayersComboBox;
	UPROPERTY(meta = (BindWidgetOptional))
	UComboBoxString* HostDifficultyComboBox;
	UPROPERTY(meta = (BindWidgetOptional))
	UComboBoxString* HostRulesComboBox;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* StartLobbyButton;
	// Offline listen server with no session. It can be opened to others later from the pause menu.
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* PlaySoloButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* HostBackButton;

	UFUNCTION()
	void PrivacyPublicClicked();
	UFUNCTION()
	void PrivacyFriendsOnlyClicked();
	UFUNCTION()
	void PrivacyCodeOnlyClicked();
	UFUNCTION()
	void StartLobbyButtonClicked();
	UFUNCTION()
	void PlaySoloButtonClicked();
	void RefreshPrivacyLabel();
	void ReadHostSettingsFromWidgets();

	//
	// Browse panel
	//
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* RefreshSessionsButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* QuickJoinButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* JoinWithCodeButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* FriendsButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* BrowseBackButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UComboBoxString* DistanceComboBox;
	UPROPERTY(meta = (BindWidgetOptional))
	UComboBoxString* DifficultyFilterComboBox;
	UPROPERTY(meta = (BindWidgetOptional))
	UComboBoxString* RulesFilterComboBox;
	UPROPERTY(meta = (BindWidgetOptional))
	UCheckBox* ShowFullLobbiesCheckBox;
	UPROPERTY(meta = (BindWidgetOptional))
	UPanelWidget* SessionListPanel;
	// Shown instead of the list while searching / when nothing was found
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* SessionListHintText;

	UFUNCTION()
	void RefreshSessionsButtonClicked();
	UFUNCTION()
	void QuickJoinButtonClicked();
	UFUNCTION()
	void JoinWithCodeButtonClicked();
	UFUNCTION()
	void FriendsButtonClicked();
	UFUNCTION()
	void OnBrowseFilterChanged(FString SelectedItem, ESelectInfo::Type SelectionType);
	UFUNCTION()
	void OnShowFullLobbiesChanged(bool bIsChecked);
	FAuraSessionFilter BuildFilterFromWidgets() const;
	void RebuildSessionList(const TArray<FAuraSessionInfo>& SessionInfos);
	void SetBrowseButtonsEnabled(bool bEnabled);

	//
	// Code panel
	//
	UPROPERTY(meta = (BindWidgetOptional))
	UEditableTextBox* JoinCodeTextBox;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* ConfirmJoinCodeButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* PasteCodeButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* CodeBackButton;

	UFUNCTION()
	void ConfirmJoinCodeButtonClicked();
	UFUNCTION()
	void PasteCodeButtonClicked();
	UFUNCTION()
	void OnJoinCodeTextChanged(const FText& Text);
	UFUNCTION()
	void OnJoinCodeTextCommitted(const FText& Text, ETextCommit::Type CommitMethod);
	// Upper case, only the join code alphabet, at most the code length
	static FString SanitizeJoinCode(const FString& Raw);
	bool IsJoinCodeComplete() const;

	//
	// Busy panel ("Searching...", "Joining...") with an optional Cancel
	//
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* BusyText;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* CancelBusyButton;

	UFUNCTION()
	void CancelBusyButtonClicked();
	void ShowBusy(const FText& Message, bool bCancellable);

	//
	// Confirm panel: yes/no question or OK-only message (Action None)
	//
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* ConfirmTitleText;
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* ConfirmMessageText;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* ConfirmYesButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* ConfirmNoButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* ConfirmYesText;

	UFUNCTION()
	void ConfirmYesButtonClicked();
	UFUNCTION()
	void ConfirmNoButtonClicked();
	void ShowConfirm(const FText& Title, const FText& Message, EMainMenu3ConfirmAction Action);

	EMainMenu3ConfirmAction PendingConfirmAction{ EMainMenu3ConfirmAction::None };
	int32 PendingJoinIndex{ INDEX_NONE };

	//
	// Options / Credits
	//
	UPROPERTY(meta = (BindWidgetOptional))
	USettingsMenu3* OptionsMenu;
	UPROPERTY(meta = (BindWidgetOptional))
	UScrollBox* CreditsScrollBox;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* CreditsBackButton;

	UFUNCTION()
	void OnOptionsClosed();
	UFUNCTION()
	void BackButtonClicked();
	void TickCredits(float DeltaTime);
	float CreditsEndPause{ 0.f };

	//
	// Shared
	//
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* StatusText;

	UPROPERTY(meta = (BindWidgetOptional))
	UWidgetSwitcher* MenuSwitcher;
	UPROPERTY(meta = (BindWidgetOptional))
	UWidget* TitlePanel;
	UPROPERTY(meta = (BindWidgetOptional))
	UWidget* HomePanel;
	UPROPERTY(meta = (BindWidgetOptional))
	UWidget* HostPanel;
	UPROPERTY(meta = (BindWidgetOptional))
	UWidget* BrowsePanel;
	UPROPERTY(meta = (BindWidgetOptional))
	UWidget* CodePanel;
	UPROPERTY(meta = (BindWidgetOptional))
	UWidget* BusyPanel;
	UPROPERTY(meta = (BindWidgetOptional))
	UWidget* ConfirmPanel;
	UPROPERTY(meta = (BindWidgetOptional))
	UWidget* OptionsPanel;
	UPROPERTY(meta = (BindWidgetOptional))
	UWidget* CreditsPanel;

	UWidget* GetOptionsPanel() const;
	void FillStaticOptions();
	void OpenLevelLeavingSession(const FString& LevelPath);

	UPROPERTY()
	UMultiplayerSessionsSubsystem* MultiplayerSessionsSubsystem;

	FAuraHostSettings PendingHostSettings;

	// What the menu is waiting on, so subsystem broadcasts meant for another flow are ignored
	bool bAwaitingCodeLookup{ false };
	bool bAwaitingQuickJoin{ false };
	bool bAwaitingJoin{ false };
	bool bAwaitingCreate{ false };
	bool bBrowseSearchPending{ false };

	// Starts once the running browse refresh reports back (a second search would be refused)
	EMainMenu3QueuedSearch QueuedSearch{ EMainMenu3QueuedSearch::None };
	FString QueuedJoinCode;
	void StartCodeLookup(const FString& Code);
	void StartQuickJoin();
	void RunQueuedSearch();

	FAuraMenuButtonFX ButtonFXState;

	int32 NumPublicConnections{ 4 };
	FString MatchType{ TEXT("FreeForAll") };
	FString PathToLobby{ TEXT("") };
	FString LobbyMapPath{ TEXT("") };
};
