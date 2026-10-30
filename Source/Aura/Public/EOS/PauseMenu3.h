// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "UI/UserWidgets/MyUserWidget.h"
#include "EOS/MultiplayerSessionTypes.h"
#include "EOS/MenuButtonFX.h"
#include "PauseMenu3.generated.h"

class APlayerState;
class UButton;
class UPanelWidget;
class UTextBlock;
class UWidget;
class UWidgetSwitcher;
class UMultiplayerSessionsSubsystem;
class USessionPlayerRow3;
class USettingsMenu3;

// What the pause menu's Confirm panel's Yes does
enum class EPauseMenu3ConfirmAction : uint8
{
	None,
	LeaveSession,
	QuitGame,
	KickPlayer,
	BanPlayer
};

/**
 * The in-game Esc menu: Resume, Current Session, Options, Leave Session, Quit. The game keeps
 * running underneath (co-op, nothing pauses).
 *
 * Current Session is Far Far West's lobby tab: the join code with Copy, Invite Friends (Steam
 * overlay), the privacy switch (host only), "Open lobby" for a solo game, and the player list
 * with Profile / Kick / Ban (host only).
 *
 * Same convention as UMainMenu3: a UWidgetSwitcher "MenuSwitcher" with PauseHomePanel,
 * SessionPanel, OptionsPanel (or OptionsMenu itself) and ConfirmPanel; every widget optional.
 * AMyPlayerController2 creates it from PauseMenuClass and opens it on IA_Pause.
 */
UCLASS()
class AURA_API UPauseMenu3 : public UMyUserWidget
{
	GENERATED_BODY()

public:
	// Adds the menu to the viewport, switches to UI input and shows the Home panel.
	UFUNCTION(BlueprintCallable, Category = "Aura|Menu")
	void OpenMenu();

	// Saves open options, removes the menu and gives input back to the game.
	UFUNCTION(BlueprintCallable, Category = "Aura|Menu")
	void CloseMenu();

	UFUNCTION(BlueprintPure, Category = "Aura|Menu")
	bool IsMenuOpen() const { return bMenuOpen; }

	// Called by USessionPlayerRow3
	void ShowPlayerProfile(APlayerState* PlayerState);
	void RequestKick(APlayerState* PlayerState, bool bBan);

protected:
	virtual bool Initialize() override;
	virtual void NativeConstruct() override;
	virtual void NativeTick(const FGeometry& MyGeometry, float InDeltaTime) override;
	virtual void NativeDestruct() override;
	virtual FReply NativeOnKeyDown(const FGeometry& InGeometry, const FKeyEvent& InKeyEvent) override;

	UPROPERTY(EditAnywhere, Category = "Aura|Menu|Graffiti")
	FAuraMenuButtonFXSettings ButtonFX;

	// Map "Leave Session" opens. Empty = Project Settings > Maps & Modes > Game Default Map.
	UPROPERTY(EditAnywhere, Category = "Aura|Menu")
	FString MainMenuMapPath;

	// Lobby created when the host of a solo game presses Open Lobby. Privacy comes from the
	// privacy buttons.
	UPROPERTY(EditAnywhere, Category = "Aura|Menu")
	FAuraHostSettings OpenLobbySettings;

	UPROPERTY(EditDefaultsOnly, Category = "Aura|Menu")
	TSubclassOf<USessionPlayerRow3> PlayerRowClass;

	// How often the Current Session tab re-reads players, pings and the session.
	UPROPERTY(EditAnywhere, Category = "Aura|Menu", meta = (ClampMin = "0.1"))
	float SessionRefreshSeconds = 1.f;

	// Shown to a kicked / banned player, and to everyone when the host leaves.
	UPROPERTY(EditAnywhere, Category = "Aura|Menu")
	FText KickReason = NSLOCTEXT("PauseMenu3", "KickReason", "You were kicked by the host.");
	UPROPERTY(EditAnywhere, Category = "Aura|Menu")
	FText BanReason = NSLOCTEXT("PauseMenu3", "BanReason", "You were banned from this lobby by the host.");
	UPROPERTY(EditAnywhere, Category = "Aura|Menu")
	FText HostLeftReason = NSLOCTEXT("PauseMenu3", "HostLeftReason", "The host closed the lobby.");

	// Blueprint hook for panel transition animations / sounds.
	UFUNCTION(BlueprintImplementableEvent, Category = "Aura|Menu")
	void OnPanelChanged(UWidget* NewPanel);

	UFUNCTION()
	void OnUpdateSession(bool bWasSuccessful);
	UFUNCTION()
	void OnCreateSession(bool bWasSuccessful);
	UFUNCTION()
	void OnSessionError(const FString& Message);

private:
	void ShowPanel(UWidget* PanelToShow);
	void HandleBack();
	UWidget* GetOptionsPanel() const;
	UMultiplayerSessionsSubsystem* GetSessions() const;
	bool IsServer() const;

	//
	// Home
	//
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* ResumeButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* CurrentSessionButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* OptionsButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* LeaveSessionButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* QuitGameButton;

	UFUNCTION()
	void ResumeButtonClicked();
	UFUNCTION()
	void CurrentSessionButtonClicked();
	UFUNCTION()
	void OptionsButtonClicked();
	UFUNCTION()
	void LeaveSessionButtonClicked();
	UFUNCTION()
	void QuitGameButtonClicked();

	//
	// Current Session
	//
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* SessionCodeText;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* CopyCodeButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* InviteFriendsButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* PrivacyPublicButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* PrivacyFriendsOnlyButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* PrivacyCodeOnlyButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* PrivacyLabelText;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* OpenLobbyButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* SessionInfoText;
	UPROPERTY(meta = (BindWidgetOptional))
	UPanelWidget* PlayerListPanel;
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* SessionStatusText;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* SessionBackButton;

	UFUNCTION()
	void CopyCodeButtonClicked();
	UFUNCTION()
	void InviteFriendsButtonClicked();
	UFUNCTION()
	void PrivacyPublicClicked();
	UFUNCTION()
	void PrivacyFriendsOnlyClicked();
	UFUNCTION()
	void PrivacyCodeOnlyClicked();
	UFUNCTION()
	void OpenLobbyButtonClicked();
	UFUNCTION()
	void BackToHomeClicked();

	void SetPrivacy(EAuraSessionPrivacy Privacy);
	void RefreshSessionPanel();
	void RefreshPlayerList();
	void SetSessionStatus(const FText& Message);

	UPROPERTY()
	TArray<USessionPlayerRow3*> PlayerRows;
	// Privacy picked in the tab; what Open Lobby uses, and what a solo game shows as selected
	EAuraSessionPrivacy SelectedPrivacy{ EAuraSessionPrivacy::FriendsOnly };
	float SessionRefreshTimer{ 0.f };
	bool bAwaitingCreate{ false };
	bool bAwaitingUpdate{ false };

	//
	// Confirm
	//
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* ConfirmTitleText;
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* ConfirmMessageText;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* ConfirmYesButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* ConfirmNoButton;

	UFUNCTION()
	void ConfirmYesButtonClicked();
	UFUNCTION()
	void ConfirmNoButtonClicked();
	void ShowConfirm(const FText& Title, const FText& Message, EPauseMenu3ConfirmAction Action);

	EPauseMenu3ConfirmAction PendingConfirmAction{ EPauseMenu3ConfirmAction::None };
	TWeakObjectPtr<APlayerState> PendingKickTarget;
	UPROPERTY()
	UWidget* PanelBeforeConfirm;

	// As host: tell every client why they're about to be dropped, so they don't just see "lost connection"
	void SendClientsHostLeft();
	void LeaveSession();

	//
	// Options
	//
	UPROPERTY(meta = (BindWidgetOptional))
	USettingsMenu3* OptionsMenu;

	UFUNCTION()
	void OnOptionsClosed();

	//
	// Shared
	//
	UPROPERTY(meta = (BindWidgetOptional))
	UWidgetSwitcher* MenuSwitcher;
	UPROPERTY(meta = (BindWidgetOptional))
	UWidget* PauseHomePanel;
	UPROPERTY(meta = (BindWidgetOptional))
	UWidget* SessionPanel;
	UPROPERTY(meta = (BindWidgetOptional))
	UWidget* OptionsPanel;
	UPROPERTY(meta = (BindWidgetOptional))
	UWidget* ConfirmPanel;

	UPROPERTY()
	UWidget* CurrentPanel;

	bool bMenuOpen{ false };
	bool bCursorWasShown{ false };

	FAuraMenuButtonFX ButtonFXState;
};
