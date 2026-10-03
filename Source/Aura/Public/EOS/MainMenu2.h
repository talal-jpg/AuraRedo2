// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "Interfaces/OnlineSessionInterface.h"
#include "UI/UserWidgets/MyUserWidget.h"
#include "EOS/MultiplayerSessionTypes.h"
#include "MainMenu2.generated.h"

class UButton;
class UWidget;
class UWidgetSwitcher;
class UPanelWidget;
class UComboBoxString;
class UEditableTextBox;
class UTextBlock;
class UMultiplayerSessionsSubsystem;
class USessionEntry2;

/**
 * Host/Join menu with privacy modes, join codes, Steam invites and a filtered
 * public-lobby browser. Talks to the same UMultiplayerSessionsSubsystem as
 * UMainMenu; UMainMenu itself is left completely untouched.
 */
UCLASS()
class AURA_API UMainMenu2 : public UMyUserWidget
{
	GENERATED_BODY()

public:
	UFUNCTION(BlueprintCallable)
	void MenuSetup(int32 NumberOfPublicConnections = 4, FString TypeOfMatch = FString(TEXT("FreeForAll")), FString LobbyPath = FString(TEXT("/Game/ThirdPersonCPP/Maps/Lobby")));

	// Called by a spawned USessionEntry2 row when its Join button is clicked.
	UFUNCTION(BlueprintCallable)
	void JoinLobbyByIndex(int32 ResultIndex);

protected:
	virtual bool Initialize() override;
	virtual void NativeDestruct() override;

	//
	// Subsystem callbacks
	//
	UFUNCTION()
	void OnCreateSession(bool bWasSuccessful);
	void OnSessionsFound(const TArray<FAuraSessionInfo>& SessionInfos, bool bWasSuccessful);
	void OnJoinSession(EOnJoinSessionCompleteResult::Type Result);
	UFUNCTION()
	void OnDestroySession(bool bWasSuccessful);
	UFUNCTION()
	void OnStartSession(bool bWasSuccessful);
	UFUNCTION()
	void OnInviteAccepted(bool bWasSuccessful);
	UFUNCTION()
	void OnSessionError(const FString& Message);

	// Blueprint hook so the browse list can be re-skinned in UMG without touching C++.
	UFUNCTION(BlueprintImplementableEvent, Category = "Aura|Menu")
	void OnLobbyListUpdated(const TArray<FAuraSessionInfo>& SessionInfos);

private:
	//
	// Panel switching
	//
	void ShowPanel(UWidget* PanelToShow);
	void SetStatus(const FString& Message);

	//
	// Home
	//
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* HostSessionButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* BrowseSessionsButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* QuitButton;

	UFUNCTION()
	void HostSessionButtonClicked();
	UFUNCTION()
	void BrowseSessionsButtonClicked();
	UFUNCTION()
	void QuitButtonClicked();

	//
	// Host panel
	//
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* PrivacyPublicButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* PrivacyFriendsOnlyButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* PrivacyCodeOnlyButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UComboBoxString* HostDifficultyComboBox;
	UPROPERTY(meta = (BindWidgetOptional))
	UComboBoxString* HostRulesComboBox;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* StartLobbyButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* JoinCodeDisplayText;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* CopyJoinCodeButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* PrivacyLabelText;

	UFUNCTION()
	void PrivacyPublicClicked();
	UFUNCTION()
	void PrivacyFriendsOnlyClicked();
	UFUNCTION()
	void PrivacyCodeOnlyClicked();
	UFUNCTION()
	void StartLobbyButtonClicked();
	UFUNCTION()
	void CopyJoinCodeButtonClicked();
	void RefreshPrivacyLabel();

	//
	// Browse panel
	//
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* JoinWithCodeButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* SteamInviteButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* RefreshSessionsButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* ApplyFiltersButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UComboBoxString* DistanceComboBox;
	UPROPERTY(meta = (BindWidgetOptional))
	UComboBoxString* DifficultyFilterComboBox;
	UPROPERTY(meta = (BindWidgetOptional))
	UComboBoxString* RulesFilterComboBox;
	UPROPERTY(meta = (BindWidgetOptional))
	UPanelWidget* SessionListPanel;

	UPROPERTY(EditDefaultsOnly, Category = "Aura|Menu")
	TSubclassOf<USessionEntry2> SessionEntryClass;

	UFUNCTION()
	void JoinWithCodeButtonClicked();
	UFUNCTION()
	void SteamInviteButtonClicked();
	UFUNCTION()
	void RefreshSessionsButtonClicked();
	UFUNCTION()
	void ApplyFiltersButtonClicked();
	FAuraSessionFilter BuildFilterFromWidgets() const;
	void RebuildSessionList(const TArray<FAuraSessionInfo>& SessionInfos);

	//
	// Code panel
	//
	UPROPERTY(meta = (BindWidgetOptional))
	UEditableTextBox* JoinCodeTextBox;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* ConfirmJoinCodeButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* BackButton;

	UFUNCTION()
	void ConfirmJoinCodeButtonClicked();
	UFUNCTION()
	void BackButtonClicked();

	//
	// Shared
	//
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* StatusText;

	UPROPERTY(meta = (BindWidgetOptional))
	UWidgetSwitcher* MenuSwitcher;
	UPROPERTY(meta = (BindWidgetOptional))
	UWidget* HomePanel;
	UPROPERTY(meta = (BindWidgetOptional))
	UWidget* HostPanel;
	UPROPERTY(meta = (BindWidgetOptional))
	UWidget* BrowsePanel;
	UPROPERTY(meta = (BindWidgetOptional))
	UWidget* CodePanel;

	void MenuTearDown();

	UPROPERTY()
	UMultiplayerSessionsSubsystem* MultiplayerSessionsSubsystem;

	FAuraHostSettings PendingHostSettings;
	bool bAwaitingCodeJoin{ false };

	int32 NumPublicConnections{ 4 };
	FString MatchType{ TEXT("FreeForAll") };
	FString PathToLobby{ TEXT("") };
};
