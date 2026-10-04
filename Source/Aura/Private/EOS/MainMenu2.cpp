// Fill out your copyright notice in the Description page of Project Settings.

#include "EOS/MainMenu2.h"
#include "EOS/SessionEntry2.h"
#include "EOS/MultiplayerSessionsSubsystem.h"
#include "Components/Button.h"
#include "Components/ComboBoxString.h"
#include "Components/EditableTextBox.h"
#include "Components/TextBlock.h"
#include "Components/WidgetSwitcher.h"
#include "Components/PanelWidget.h"
#include "Components/Image.h"
#include "Blueprint/WidgetTree.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "OnlineSessionSettings.h"
#include "OnlineSubsystem.h"
#include "OnlineSubsystemUtils.h"
#include "HAL/PlatformApplicationMisc.h"
#include "Kismet/KismetSystemLibrary.h"

void UMainMenu2::MenuSetup(int32 NumberOfPublicConnections, FString TypeOfMatch, FString LobbyPath)
{
	PathToLobby = FString::Printf(TEXT("%s?listen"), *LobbyPath);
	NumPublicConnections = NumberOfPublicConnections;
	MatchType = TypeOfMatch;

	if (MenuSwitcher)
	{
		UKismetSystemLibrary::PrintString(this,"MenuSwitcher already exists!");
	}
	// Seed the host settings the Host panel edits; Difficulty/Rules/Privacy keep
	// FAuraHostSettings' own defaults (1 / "Default" / Public) until the player changes them.
	PendingHostSettings.NumPublicConnections = NumberOfPublicConnections;
	PendingHostSettings.MatchType = TypeOfMatch;

	AddToViewport();
	SetVisibility(ESlateVisibility::Visible);
	bIsFocusable = true;

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
		MultiplayerSessionsSubsystem->MultiplayerOnCreateSessionComplete.AddDynamic(this, &ThisClass::OnCreateSession);
		MultiplayerSessionsSubsystem->MultiplayerOnSessionsFound.AddUObject(this, &ThisClass::OnSessionsFound);
		MultiplayerSessionsSubsystem->MultiplayerOnJoinSessionComplete.AddUObject(this, &ThisClass::OnJoinSession);
		MultiplayerSessionsSubsystem->MultiplayerOnDestroySessionComplete.AddDynamic(this, &ThisClass::OnDestroySession);
		MultiplayerSessionsSubsystem->MultiplayerOnStartSessionComplete.AddDynamic(this, &ThisClass::OnStartSession);
		MultiplayerSessionsSubsystem->MultiplayerOnInviteAccepted.AddDynamic(this, &ThisClass::OnInviteAccepted);
		MultiplayerSessionsSubsystem->MultiplayerOnSessionError.AddDynamic(this, &ThisClass::OnSessionError);
	}

	UKismetSystemLibrary::PrintString(this,"ShowingPanel");
	ShowPanel(HomePanel);
	RefreshPrivacyLabel();
}

bool UMainMenu2::Initialize()
{
	if (!Super::Initialize())
	{
		return false;
	}

	if (HostSessionButton)    HostSessionButton->OnClicked.AddDynamic(this, &ThisClass::HostSessionButtonClicked);
	if (BrowseSessionsButton) BrowseSessionsButton->OnClicked.AddDynamic(this, &ThisClass::BrowseSessionsButtonClicked);
	if (QuitButton)           QuitButton->OnClicked.AddDynamic(this, &ThisClass::QuitButtonClicked);

	if (PrivacyPublicButton)      PrivacyPublicButton->OnClicked.AddDynamic(this, &ThisClass::PrivacyPublicClicked);
	if (PrivacyFriendsOnlyButton) PrivacyFriendsOnlyButton->OnClicked.AddDynamic(this, &ThisClass::PrivacyFriendsOnlyClicked);
	if (PrivacyCodeOnlyButton)    PrivacyCodeOnlyButton->OnClicked.AddDynamic(this, &ThisClass::PrivacyCodeOnlyClicked);
	if (StartLobbyButton)         StartLobbyButton->OnClicked.AddDynamic(this, &ThisClass::StartLobbyButtonClicked);
	if (CopyJoinCodeButton)       CopyJoinCodeButton->OnClicked.AddDynamic(this, &ThisClass::CopyJoinCodeButtonClicked);

	if (JoinWithCodeButton)     JoinWithCodeButton->OnClicked.AddDynamic(this, &ThisClass::JoinWithCodeButtonClicked);
	if (SteamInviteButton)      SteamInviteButton->OnClicked.AddDynamic(this, &ThisClass::SteamInviteButtonClicked);
	if (RefreshSessionsButton)  RefreshSessionsButton->OnClicked.AddDynamic(this, &ThisClass::RefreshSessionsButtonClicked);
	if (ApplyFiltersButton)     ApplyFiltersButton->OnClicked.AddDynamic(this, &ThisClass::ApplyFiltersButtonClicked);

	if (ConfirmJoinCodeButton) ConfirmJoinCodeButton->OnClicked.AddDynamic(this, &ThisClass::ConfirmJoinCodeButtonClicked);
	if (BackButton)            BackButton->OnClicked.AddDynamic(this, &ThisClass::BackButtonClicked);

	return true;
}

void UMainMenu2::NativeConstruct()
{
	Super::NativeConstruct();

	SetupGraffitiButtons();
}

void UMainMenu2::NativeTick(const FGeometry& MyGeometry, float InDeltaTime)
{
	Super::NativeTick(MyGeometry, InDeltaTime);

	TickGraffitiButtons(InDeltaTime);
}

void UMainMenu2::NativeDestruct()
{
	GraffitiButtons.Reset();

	if (MultiplayerSessionsSubsystem)
	{
		MultiplayerSessionsSubsystem->MultiplayerOnCreateSessionComplete.RemoveDynamic(this, &ThisClass::OnCreateSession);
		MultiplayerSessionsSubsystem->MultiplayerOnSessionsFound.RemoveAll(this);
		MultiplayerSessionsSubsystem->MultiplayerOnJoinSessionComplete.RemoveAll(this);
		MultiplayerSessionsSubsystem->MultiplayerOnDestroySessionComplete.RemoveDynamic(this, &ThisClass::OnDestroySession);
		MultiplayerSessionsSubsystem->MultiplayerOnStartSessionComplete.RemoveDynamic(this, &ThisClass::OnStartSession);
		MultiplayerSessionsSubsystem->MultiplayerOnInviteAccepted.RemoveDynamic(this, &ThisClass::OnInviteAccepted);
		MultiplayerSessionsSubsystem->MultiplayerOnSessionError.RemoveDynamic(this, &ThisClass::OnSessionError);
	}

	Super::NativeDestruct();
}

//
// Graffiti hover juice
//

void UMainMenu2::SetupGraffitiButtons()
{
	GraffitiButtons.Reset();

	if (!WidgetTree)
	{
		return;
	}

	int32 Index = 0;
	WidgetTree->ForEachWidget([this, &Index](UWidget* Widget)
	{
		UButton* Button = Cast<UButton>(Widget);
		UPanelWidget* Container = Button ? Button->GetParent() : nullptr;
		if (!Container)
		{
			return;
		}

		FGraffitiButtonFX FX;
		for (int32 ChildIndex = 0; ChildIndex < Container->GetChildrenCount(); ++ChildIndex)
		{
			UWidget* Child = Container->GetChildAt(ChildIndex);
			if (UImage* Image = Cast<UImage>(Child))
			{
				if (Image->GetName().StartsWith(TEXT("Graffiti_")))
				{
					FX.Material = Image->GetDynamicMaterial();
				}
			}
			else if (UTextBlock* Text = Cast<UTextBlock>(Child))
			{
				FX.Label = Text;
			}
		}

		// Only buttons that were given a graffiti backing image take part
		if (!FX.Material.IsValid())
		{
			return;
		}

		FX.Button = Button;
		FX.Container = Container;
		FX.Seed = Index * 1.37f;
		// Deterministic "hand placed" tilt, alternating left/right
		FX.RestAngle = FMath::Sin(Index * 2.3f + 0.7f) * GraffitiRestTilt;
		Container->SetRenderTransformAngle(FX.RestAngle);

		GraffitiButtons.Add(FX);
		++Index;
	});
}

void UMainMenu2::TickGraffitiButtons(float DeltaTime)
{
	if (GraffitiButtons.Num() == 0)
	{
		return;
	}

	// Keep the spring stable on hitches
	const float Dt = FMath::Min(DeltaTime, 1.f / 30.f);
	GraffitiTime += Dt;

	for (FGraffitiButtonFX& FX : GraffitiButtons)
	{
		UButton* Button = FX.Button.Get();
		UWidget* Container = FX.Container.Get();
		if (!Button || !Container)
		{
			continue;
		}

		const bool bHovered = Button->IsHovered() && Button->GetIsEnabled();
		const bool bPressed = Button->IsPressed();

		FX.Hover = FMath::FInterpTo(FX.Hover, bHovered ? 1.f : 0.f, Dt, 12.f);
		FX.Press = FMath::FInterpTo(FX.Press, bPressed ? 1.f : 0.f, Dt, 30.f);

		// Kick the spring the moment the cursor arrives so the button overshoots and settles
		if (bHovered && !FX.bWasHovered)
		{
			FX.ScaleVelocity += GraffitiHoverKick;
		}
		FX.bWasHovered = bHovered;

		// Damped spring towards the target scale
		const float TargetScale = 1.f + (GraffitiHoverScale - 1.f) * FX.Hover - 0.07f * FX.Press;
		const float Accel = (TargetScale - FX.Scale) * 260.f - FX.ScaleVelocity * 14.f;
		FX.ScaleVelocity += Accel * Dt;
		FX.Scale += FX.ScaleVelocity * Dt;

		// Hovered: lean into a wobble with a little spray-can jitter. Pressed: squash down.
		const float Wobble = FMath::Sin(GraffitiTime * 10.f + FX.Seed) * GraffitiWobble;
		const float Angle = FMath::Lerp(FX.RestAngle, Wobble - 1.5f, FX.Hover);
		const FVector2D Jitter(
			FMath::PerlinNoise1D(GraffitiTime * 14.f + FX.Seed),
			FMath::PerlinNoise1D(GraffitiTime * 14.f + FX.Seed + 31.7f));
		const FVector2D Translation = FVector2D(10.f, -4.f) * FX.Hover + Jitter * 2.5f * FX.Hover + FVector2D(0.f, 3.f) * FX.Press;
		const FVector2D Scale(FX.Scale * (1.f + 0.04f * FX.Press), FX.Scale * (1.f - 0.07f * FX.Press));
		const FVector2D Shear(-8.f * FX.Hover, 0.f);

		Container->SetRenderTransform(FWidgetTransform(Translation, Scale, Shear, Angle));

		if (UMaterialInstanceDynamic* Material = FX.Material.Get())
		{
			Material->SetScalarParameterValue(TEXT("Hovered"), FX.Hover);
		}

		if (UTextBlock* Label = FX.Label.Get())
		{
			// Dark ink on the neon fill, with the drop shadow flipping to white
			Label->SetColorAndOpacity(FSlateColor(FMath::Lerp(FX.RestTextColor, GraffitiHoverTextColor, FX.Hover)));
			Label->SetShadowColorAndOpacity(FMath::Lerp(FLinearColor::Black, FLinearColor::White, FX.Hover));
		}
	}
}

//
// Home
//
void UMainMenu2::HostSessionButtonClicked()
{
	ShowPanel(HostPanel);
	RefreshPrivacyLabel();
}

void UMainMenu2::BrowseSessionsButtonClicked()
{
	ShowPanel(BrowsePanel);
	RefreshSessionsButtonClicked();
}

void UMainMenu2::QuitButtonClicked()
{
	if (APlayerController* PlayerController = GetOwningPlayer())
	{
		UKismetSystemLibrary::QuitGame(GetWorld(), PlayerController, EQuitPreference::Quit, false);
	}
}

//
// Host panel
//
void UMainMenu2::PrivacyPublicClicked()
{
	PendingHostSettings.Privacy = EAuraSessionPrivacy::Public;
	RefreshPrivacyLabel();
}

void UMainMenu2::PrivacyFriendsOnlyClicked()
{
	PendingHostSettings.Privacy = EAuraSessionPrivacy::FriendsOnly;
	RefreshPrivacyLabel();
}

void UMainMenu2::PrivacyCodeOnlyClicked()
{
	PendingHostSettings.Privacy = EAuraSessionPrivacy::CodeOnly;
	RefreshPrivacyLabel();
}

void UMainMenu2::RefreshPrivacyLabel()
{
	if (!PrivacyLabelText)
	{
		return;
	}

	switch (PendingHostSettings.Privacy)
	{
	case EAuraSessionPrivacy::Public:
		PrivacyLabelText->SetText(FText::FromString(TEXT("Public - listed in Browse, joinable by anyone or by code")));
		break;
	case EAuraSessionPrivacy::FriendsOnly:
		PrivacyLabelText->SetText(FText::FromString(TEXT("Friends Only - Steam invite or friends list only, no code join")));
		break;
	case EAuraSessionPrivacy::CodeOnly:
		PrivacyLabelText->SetText(FText::FromString(TEXT("Code Only - hidden from Browse, joinable with your code")));
		break;
	}
}

void UMainMenu2::StartLobbyButtonClicked()
{
	if (!MultiplayerSessionsSubsystem)
	{
		return;
	}

	if (HostDifficultyComboBox && HostDifficultyComboBox->GetSelectedOption().IsNumeric())
	{
		PendingHostSettings.Difficulty = FCString::Atoi(*HostDifficultyComboBox->GetSelectedOption());
	}
	if (HostRulesComboBox && !HostRulesComboBox->GetSelectedOption().IsEmpty())
	{
		PendingHostSettings.Rules = HostRulesComboBox->GetSelectedOption();
	}

	if (StartLobbyButton)
	{
		StartLobbyButton->SetIsEnabled(false);
	}

	SetStatus(TEXT("Starting lobby..."));
	MultiplayerSessionsSubsystem->CreateSessionWithSettings(PendingHostSettings);
}

void UMainMenu2::CopyJoinCodeButtonClicked()
{
	if (MultiplayerSessionsSubsystem)
	{
		FPlatformApplicationMisc::ClipboardCopy(*MultiplayerSessionsSubsystem->GetCurrentJoinCode());
		SetStatus(TEXT("Join code copied to clipboard."));
	}
}

//
// Browse panel
//
void UMainMenu2::JoinWithCodeButtonClicked()
{
	ShowPanel(CodePanel);
}

void UMainMenu2::SteamInviteButtonClicked()
{
	if (MultiplayerSessionsSubsystem)
	{
		MultiplayerSessionsSubsystem->ShowSteamInviteUI();
	}
}

void UMainMenu2::RefreshSessionsButtonClicked()
{
	if (!MultiplayerSessionsSubsystem || MultiplayerSessionsSubsystem->IsSearchInProgress())
	{
		return;
	}

	if (RefreshSessionsButton) RefreshSessionsButton->SetIsEnabled(false);
	if (ApplyFiltersButton)    ApplyFiltersButton->SetIsEnabled(false);

	SetStatus(TEXT("Searching for lobbies..."));
	MultiplayerSessionsSubsystem->FindSessionsFiltered(BuildFilterFromWidgets());
}

void UMainMenu2::ApplyFiltersButtonClicked()
{
	RefreshSessionsButtonClicked();
}

FAuraSessionFilter UMainMenu2::BuildFilterFromWidgets() const
{
	FAuraSessionFilter Filter;

	if (DistanceComboBox)
	{
		const FString Selected = DistanceComboBox->GetSelectedOption();
		if (Selected == TEXT("Close"))        Filter.Distance = EAuraSearchDistance::Close;
		else if (Selected == TEXT("Medium"))  Filter.Distance = EAuraSearchDistance::Medium;
		else if (Selected == TEXT("Far"))     Filter.Distance = EAuraSearchDistance::Far;
		else                                   Filter.Distance = EAuraSearchDistance::Worldwide;
	}

	if (DifficultyFilterComboBox)
	{
		const FString Selected = DifficultyFilterComboBox->GetSelectedOption();
		Filter.Difficulty = (Selected.IsEmpty() || Selected == TEXT("Any")) ? -1 : FCString::Atoi(*Selected);
	}

	if (RulesFilterComboBox)
	{
		const FString Selected = RulesFilterComboBox->GetSelectedOption();
		Filter.Rules = (Selected == TEXT("Any")) ? FString() : Selected;
	}

	Filter.bOnlyJoinable = true;
	Filter.MaxSearchResults = 10000;
	return Filter;
}

void UMainMenu2::RebuildSessionList(const TArray<FAuraSessionInfo>& SessionInfos)
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
		if (USessionEntry2* Entry = CreateWidget<USessionEntry2>(this, SessionEntryClass))
		{
			Entry->Setup(this, Info);
			SessionListPanel->AddChild(Entry);
		}
	}
}

void UMainMenu2::JoinLobbyByIndex(int32 ResultIndex)
{
	if (!MultiplayerSessionsSubsystem)
	{
		return;
	}

	SetStatus(TEXT("Joining lobby..."));
	MultiplayerSessionsSubsystem->JoinCachedSession(ResultIndex);
}

//
// Code panel
//
void UMainMenu2::ConfirmJoinCodeButtonClicked()
{
	if (!MultiplayerSessionsSubsystem || !JoinCodeTextBox)
	{
		return;
	}

	FString Code = JoinCodeTextBox->GetText().ToString();
	Code = Code.TrimStartAndEnd().ToUpper().Replace(TEXT(" "), TEXT(""));
	if (Code.IsEmpty())
	{
		SetStatus(TEXT("Enter a join code first."));
		return;
	}

	if (ConfirmJoinCodeButton)
	{
		ConfirmJoinCodeButton->SetIsEnabled(false);
	}

	bAwaitingCodeJoin = true;
	SetStatus(TEXT("Looking for that lobby..."));
	MultiplayerSessionsSubsystem->JoinSessionByCode(Code);
}

void UMainMenu2::BackButtonClicked()
{
	ShowPanel(BrowsePanel);
}

//
// Shared
//
void UMainMenu2::ShowPanel(UWidget* PanelToShow)
{
	if (!MenuSwitcher)
	{
		UKismetSystemLibrary::PrintString(this,"No MenuSwitcher!");
	}
	
	if (!PanelToShow)
	{
		UKismetSystemLibrary::PrintString(this,"No PanelToShow!");
	}
	if (MenuSwitcher && PanelToShow)
	{
		MenuSwitcher->SetActiveWidget(PanelToShow);
		UKismetSystemLibrary::PrintString(this,"ShowingPanel");
		return;
	}

	// Fallback for menus built before a WidgetSwitcher exists: plain visibility toggling.
	for (UWidget* Panel : { HomePanel, HostPanel, BrowsePanel, CodePanel })
	{
		if (Panel)
		{
			Panel->SetVisibility(Panel == PanelToShow ? ESlateVisibility::Visible : ESlateVisibility::Collapsed);
		}
	}
}

void UMainMenu2::SetStatus(const FString& Message)
{
	if (StatusText)
	{
		StatusText->SetText(FText::FromString(Message));
	}
}

//
// Subsystem callbacks
//
void UMainMenu2::OnCreateSession(bool bWasSuccessful)
{
	if (bWasSuccessful)
	{
		if (MultiplayerSessionsSubsystem && JoinCodeDisplayText)
		{
			JoinCodeDisplayText->SetText(FText::FromString(MultiplayerSessionsSubsystem->GetCurrentJoinCode()));
		}

		if (UWorld* World = GetWorld())
		{
			World->ServerTravel(PathToLobby);
		}
	}
	else
	{
		SetStatus(TEXT("Failed to create session!"));
		if (StartLobbyButton)
		{
			StartLobbyButton->SetIsEnabled(true);
		}
	}
}

void UMainMenu2::OnSessionsFound(const TArray<FAuraSessionInfo>& SessionInfos, bool bWasSuccessful)
{
	if (RefreshSessionsButton) RefreshSessionsButton->SetIsEnabled(true);
	if (ApplyFiltersButton)    ApplyFiltersButton->SetIsEnabled(true);

	if (bAwaitingCodeJoin)
	{
		// The subsystem auto-joins a code match itself; don't repaint the Browse list
		// underneath the Code panel while that's happening - just wait for
		// OnJoinSession / OnSessionError.
		return;
	}

	RebuildSessionList(SessionInfos);
	OnLobbyListUpdated(SessionInfos);

	if (bWasSuccessful && SessionInfos.Num() == 0)
	{
		SetStatus(TEXT("No lobbies found."));
	}
	else if (bWasSuccessful)
	{
		SetStatus(FString::Printf(TEXT("Found %d lobbies."), SessionInfos.Num()));
	}
}

void UMainMenu2::OnJoinSession(EOnJoinSessionCompleteResult::Type Result)
{
	bAwaitingCodeJoin = false;
	if (ConfirmJoinCodeButton)
	{
		ConfirmJoinCodeButton->SetIsEnabled(true);
	}

	switch (Result)
	{
	case EOnJoinSessionCompleteResult::Success:
		break;
	case EOnJoinSessionCompleteResult::SessionIsFull:
		SetStatus(TEXT("That lobby is full."));
		return;
	case EOnJoinSessionCompleteResult::SessionDoesNotExist:
		SetStatus(TEXT("That lobby no longer exists."));
		return;
	case EOnJoinSessionCompleteResult::CouldNotRetrieveAddress:
		SetStatus(TEXT("Could not retrieve the host's address."));
		return;
	case EOnJoinSessionCompleteResult::AlreadyInSession:
		SetStatus(TEXT("You're already in a session."));
		return;
	default:
		SetStatus(TEXT("Could not join that session."));
		return;
	}

	IOnlineSubsystem* Subsystem = Online::GetSubsystem(GetWorld());
	if (!Subsystem)
	{
		return;
	}

	IOnlineSessionPtr SessionInterface = Subsystem->GetSessionInterface();
	if (!SessionInterface.IsValid())
	{
		return;
	}

	FString Address;
	SessionInterface->GetResolvedConnectString(NAME_GameSession, Address);

	if (APlayerController* PlayerController = GetGameInstance()->GetFirstLocalPlayerController())
	{
		PlayerController->ClientTravel(Address, ETravelType::TRAVEL_Absolute);
	}
}

void UMainMenu2::OnDestroySession(bool bWasSuccessful)
{
}

void UMainMenu2::OnStartSession(bool bWasSuccessful)
{
}

void UMainMenu2::OnInviteAccepted(bool bWasSuccessful)
{
	SetStatus(bWasSuccessful ? TEXT("Invite accepted, joining...") : TEXT("Could not accept the invite."));
}

void UMainMenu2::OnSessionError(const FString& Message)
{
	bAwaitingCodeJoin = false;
	if (ConfirmJoinCodeButton) ConfirmJoinCodeButton->SetIsEnabled(true);
	if (StartLobbyButton)      StartLobbyButton->SetIsEnabled(true);
	if (RefreshSessionsButton) RefreshSessionsButton->SetIsEnabled(true);
	if (ApplyFiltersButton)    ApplyFiltersButton->SetIsEnabled(true);

	SetStatus(Message);
}

void UMainMenu2::MenuTearDown()
{
	RemoveFromParent();
	if (UWorld* World = GetWorld())
	{
		if (APlayerController* PlayerController = World->GetFirstPlayerController())
		{
			FInputModeGameOnly InputModeData;
			PlayerController->SetInputMode(InputModeData);
			PlayerController->SetShowMouseCursor(false);
		}
	}
}
