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
class UMaterialInstanceDynamic;

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
	virtual void NativeConstruct() override;
	virtual void NativeTick(const FGeometry& MyGeometry, float InDeltaTime) override;
	virtual void NativeDestruct() override;

	//
	// Graffiti hover juice. Every button whose overlay contains an Image named "Graffiti_*"
	// pops, tilts and wobbles on hover, squashes on press, and drives the image's
	// "Hovered" material parameter (M_UI_Button) smoothly instead of snapping.
	//
	UPROPERTY(EditAnywhere, Category = "Aura|Menu|Graffiti")
	float GraffitiHoverScale = 1.08f;

	// Extra scale velocity added the moment the cursor enters, for the overshoot "pop".
	UPROPERTY(EditAnywhere, Category = "Aura|Menu|Graffiti")
	float GraffitiHoverKick = 2.5f;

	// Max resting tilt (degrees) so the buttons look hand-placed.
	UPROPERTY(EditAnywhere, Category = "Aura|Menu|Graffiti")
	float GraffitiRestTilt = 3.f;

	// Wobble amplitude (degrees) while hovered.
	UPROPERTY(EditAnywhere, Category = "Aura|Menu|Graffiti")
	float GraffitiWobble = 2.2f;

	// Label colour on top of the neon fill while hovered.
	UPROPERTY(EditAnywhere, Category = "Aura|Menu|Graffiti")
	FLinearColor GraffitiHoverTextColor = FLinearColor(0.02f, 0.02f, 0.03f, 1.f);

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

	//
	// Graffiti hover state
	//
	struct FGraffitiButtonFX
	{
		TWeakObjectPtr<UButton> Button;
		TWeakObjectPtr<UWidget> Container;
		TWeakObjectPtr<UTextBlock> Label;
		TWeakObjectPtr<UMaterialInstanceDynamic> Material;
		FLinearColor RestTextColor = FLinearColor::White;
		float Hover = 0.f;
		float Press = 0.f;
		float Scale = 1.f;
		float ScaleVelocity = 0.f;
		float RestAngle = 0.f;
		float Seed = 0.f;
		bool bWasHovered = false;
	};

	TArray<FGraffitiButtonFX> GraffitiButtons;
	float GraffitiTime = 0.f;

	void SetupGraffitiButtons();
	void TickGraffitiButtons(float DeltaTime);

	int32 NumPublicConnections{ 4 };
	FString MatchType{ TEXT("FreeForAll") };
	FString PathToLobby{ TEXT("") };
};
