// Fill out your copyright notice in the Description page of Project Settings.


#include "EOS/MultiplayerSessionsSubsystem.h"
#include "OnlineSubsystem.h"
#include "OnlineSessionSettings.h"
#include "Online/OnlineSessionNames.h"
#include "OnlineSubsystemUtils.h"
#include "Interfaces/OnlineExternalUIInterface.h"
#include "TimerManager.h"
#include "Engine/GameInstance.h"
#include "GameFramework/PlayerController.h"
#include "Kismet/KismetSystemLibrary.h"
#include "Misc/AutomationTest.h"
#include "Misc/CommandLine.h"
#include "Engine/Engine.h"
#include "Engine/NetDriver.h"
#include "Kismet/GameplayStatics.h"
#include "Interfaces/OnlineIdentityInterface.h"
#include "GameFramework/GameModeBase.h"
#include "GameFramework/GameSession.h"
#include "GameFramework/PlayerState.h"
#include "GameFramework/OnlineReplStructs.h"

UMultiplayerSessionsSubsystem::UMultiplayerSessionsSubsystem():
	CreateSessionCompleteDelegate(FOnCreateSessionCompleteDelegate::CreateUObject(this, &ThisClass::OnCreateSessionComplete)),
	FindSessionsCompleteDelegate(FOnFindSessionsCompleteDelegate::CreateUObject(this, &ThisClass::OnFindSessionsComplete)),
	JoinSessionCompleteDelegate(FOnJoinSessionCompleteDelegate::CreateUObject(this, &ThisClass::OnJoinSessionComplete)),
	DestroySessionCompleteDelegate(FOnDestroySessionCompleteDelegate::CreateUObject(this, &ThisClass::OnDestroySessionComplete)),
	StartSessionCompleteDelegate(FOnStartSessionCompleteDelegate::CreateUObject(this, &ThisClass::OnStartSessionComplete)),
	UpdateSessionCompleteDelegate(FOnUpdateSessionCompleteDelegate::CreateUObject(this, &ThisClass::OnUpdateSessionComplete)),
	CancelFindSessionsCompleteDelegate(FOnCancelFindSessionsCompleteDelegate::CreateUObject(this, &ThisClass::OnCancelFindSessionsComplete))
{
}

void UMultiplayerSessionsSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	
	UE_LOG(LogTemp, Warning, TEXT("MultiplayerSessionsSubsystem::Initialize"));
	UKismetSystemLibrary::PrintString(GetWorld(), TEXT("MultiplayerSessionsSubsystem Initialized"),true,true,FLinearColor::Black,30);

	IOnlineSubsystem* Subsystem = Online::GetSubsystem(GetGameInstance()->GetWorld());

	// BUGFIX: the old code called Subsystem->GetSubsystemName() here, before the null
	// check below - a missing/misconfigured OSS crashed on startup. Everything that
	// touches Subsystem now lives inside the if.
	if (Subsystem)
	{
		const FString SubsystemName = Subsystem->GetSubsystemName().ToString();
		UKismetSystemLibrary::PrintString(GetWorld(),FString::Printf(TEXT("Subsystem: %s"), *SubsystemName),true,true,FLinearColor::Green,30.f);

		SessionInterface = Subsystem->GetSessionInterface();
		UKismetSystemLibrary::PrintString(GetWorld(), TEXT("SessionInterfaceSet"),true,true,FLinearColor::Black,30);

		if (SessionInterface.IsValid())
		{
			// Load-bearing: TickPendingInvites re-ticks a cold-start invite (game launched
			// from the Steam overlay) until this delegate is bound, so it has to happen
			// here in Initialize(), not lazily the first time a menu opens.
			InviteAcceptedDelegateHandle = SessionInterface->AddOnSessionUserInviteAcceptedDelegate_Handle(
				FOnSessionUserInviteAcceptedDelegate::CreateUObject(this, &ThisClass::OnSessionUserInviteAccepted));
		}
	}
	else
	{
		UE_LOG(LogTemp, Error, TEXT("MultiplayerSessionsSubsystem::Initialize - no OnlineSubsystem found"));
	}
	
	FWorldDelegates::OnPostWorldInitialization.AddUObject(this,&ThisClass::StartHeadlessLogic);

	if (GEngine)
	{
		NetworkFailureDelegateHandle = GEngine->OnNetworkFailure().AddUObject(this, &ThisClass::HandleNetworkFailure);
		TravelFailureDelegateHandle = GEngine->OnTravelFailure().AddUObject(this, &ThisClass::HandleTravelFailure);
	}
}

void UMultiplayerSessionsSubsystem::Deinitialize()
{
	if (SessionInterface.IsValid())
	{
		SessionInterface->ClearOnSessionUserInviteAcceptedDelegate_Handle(InviteAcceptedDelegateHandle);
	}

	if (GEngine)
	{
		GEngine->OnNetworkFailure().Remove(NetworkFailureDelegateHandle);
		GEngine->OnTravelFailure().Remove(TravelFailureDelegateHandle);
	}

	Super::Deinitialize();
}

void UMultiplayerSessionsSubsystem::CreateSession(int32 NumPublicConnections, FString MatchType)
{
	if (!SessionInterface.IsValid())
	{
		return;
	}
	const TArray<FNetDriverDefinition>& Drivers = GEngine->NetDriverDefinitions;

	for (const FNetDriverDefinition& Def : Drivers)
	{
		UE_LOG(LogTemp, Warning,
			TEXT("Def=%s Driver=%s Fallback=%s"),
			*Def.DefName.ToString(),
			*Def.DriverClassName.ToString(),
			*Def.DriverClassNameFallback.ToString());
	}

	auto ExistingSession = SessionInterface->GetNamedSession(NAME_GameSession);
	if (ExistingSession != nullptr)
	{
		bCreateSessionOnDestroy = true;
		bRecreateWithHostSettings = false;
		LastNumPublicConnections = NumPublicConnections;
		LastMatchType = MatchType;

		DestroySession();
		return; // BUGFIX: this used to fall through and call CreateSession() below on a
		        // session that was still mid-destroy. Now it waits for OnDestroySessionComplete.
	}

	// Store the delegate in a FDelegateHandle so we can later remove it from the delegate list
	CreateSessionCompleteDelegateHandle = SessionInterface->AddOnCreateSessionCompleteDelegate_Handle(CreateSessionCompleteDelegate);
	

	LastSessionSettings = MakeShareable(new FOnlineSessionSettings());
	LastSessionSettings->bIsLANMatch = Online::GetSubsystem(GetWorld())->GetSubsystemName() == "NULL" ? true : false;
	LastSessionSettings->NumPublicConnections = NumPublicConnections;
	LastSessionSettings->bAllowJoinInProgress = true;
	LastSessionSettings->bAllowJoinViaPresence = true;
	LastSessionSettings->bShouldAdvertise = true;
	LastSessionSettings->bUsesPresence = true;
	LastSessionSettings->Set(FName("MatchType"), MatchType, EOnlineDataAdvertisementType::ViaOnlineServiceAndPing);
	LastSessionSettings->BuildUniqueId = 1;
	LastSessionSettings->bUseLobbiesIfAvailable = true;
	LastSessionSettings->Set(FName("GameName"),FString("AuraRedo3"),EOnlineDataAdvertisementType::ViaOnlineServiceAndPing);
	

	const ULocalPlayer* LocalPlayer = GetWorld()->GetFirstLocalPlayerFromController();
	if (!SessionInterface->CreateSession(*LocalPlayer->GetPreferredUniqueNetId(), NAME_GameSession, *LastSessionSettings))
	{
		SessionInterface->ClearOnCreateSessionCompleteDelegate_Handle(CreateSessionCompleteDelegateHandle);

		// Broadcast our own custom delegate
		MultiplayerOnCreateSessionComplete.Broadcast(false);
	}
}

void UMultiplayerSessionsSubsystem::CreateSessionWithSettings(const FAuraHostSettings& HostSettings)
{
	if (!SessionInterface.IsValid())
	{
		MultiplayerOnSessionError.Broadcast(TEXT("No valid online session interface."));
		return;
	}

	auto ExistingSession = SessionInterface->GetNamedSession(NAME_GameSession);
	if (ExistingSession != nullptr)
	{
		bCreateSessionOnDestroy = true;
		bRecreateWithHostSettings = true;
		PendingHostSettings = HostSettings;
		LastNumPublicConnections = HostSettings.NumPublicConnections;
		LastMatchType = HostSettings.MatchType;

		DestroySession();
		return;
	}

	CreateSessionCompleteDelegateHandle = SessionInterface->AddOnCreateSessionCompleteDelegate_Handle(CreateSessionCompleteDelegate);

	CurrentJoinCode = HostSettings.JoinCode.IsEmpty() ? GenerateJoinCode() : HostSettings.JoinCode;
	ClearBans();
	bMenuMessageLocked = false;

	LastSessionSettings = MakeShareable(new FOnlineSessionSettings());
	LastSessionSettings->bIsLANMatch = Online::GetSubsystem(GetWorld())->GetSubsystemName() == "NULL" ? true : false;
	LastSessionSettings->bAllowJoinViaPresence = true;
	LastSessionSettings->bShouldAdvertise = true;
	LastSessionSettings->bUsesPresence = true;
	LastSessionSettings->bUseLobbiesIfAvailable = true;
	LastSessionSettings->bAllowInvites = true;
	LastSessionSettings->BuildUniqueId = 1;

	LastSessionSettings->Set(AuraSessionKeys::GameName, FString("AuraRedo3"), EOnlineDataAdvertisementType::ViaOnlineServiceAndPing);
	// Max players, privacy, difficulty, rules, join code, lobby name, join in progress
	ApplyHostSettings(*LastSessionSettings, HostSettings, CurrentJoinCode);

	LastNumPublicConnections = HostSettings.NumPublicConnections;
	LastMatchType = HostSettings.MatchType;

	const ULocalPlayer* LocalPlayer = GetWorld()->GetFirstLocalPlayerFromController();
	if (!LocalPlayer || !SessionInterface->CreateSession(*LocalPlayer->GetPreferredUniqueNetId(), NAME_GameSession, *LastSessionSettings))
	{
		SessionInterface->ClearOnCreateSessionCompleteDelegate_Handle(CreateSessionCompleteDelegateHandle);
		MultiplayerOnCreateSessionComplete.Broadcast(false);
		MultiplayerOnSessionError.Broadcast(TEXT("Failed to start session creation."));
	}
}

void UMultiplayerSessionsSubsystem::FindSessions(int32 MaxSearchResults)
{
	if (!SessionInterface.IsValid())
	{
		return;
	}

	FindSessionsCompleteDelegateHandle = SessionInterface->AddOnFindSessionsCompleteDelegate_Handle(FindSessionsCompleteDelegate);

	LastSessionSearch = MakeShareable(new FOnlineSessionSearch());
	LastSessionSearch->MaxSearchResults = MaxSearchResults;
	LastSessionSearch->bIsLanQuery = Online::GetSubsystem(GetWorld())->GetSubsystemName() == "NULL" ? true : false;
	LastSessionSearch->QuerySettings.Set(SEARCH_LOBBIES, true, EOnlineComparisonOp::Equals);
	LastSessionSearch->QuerySettings.Set(FName("GameName"),FString("AuraRedo3"),EOnlineComparisonOp::Equals);

	const ULocalPlayer* LocalPlayer = GetWorld()->GetFirstLocalPlayerFromController();
	bSearchInProgress = true; // tracked here too, so IsSearchInProgress()/the invite guard is accurate no matter which path started the search
	if (!SessionInterface->FindSessions(*LocalPlayer->GetPreferredUniqueNetId(), LastSessionSearch.ToSharedRef()))
	{
		bSearchInProgress = false;
		SessionInterface->ClearOnFindSessionsCompleteDelegate_Handle(FindSessionsCompleteDelegateHandle);

		MultiplayerOnFindSessionsComplete.Broadcast(TArray<FOnlineSessionSearchResult>(), false);
	}
}

void UMultiplayerSessionsSubsystem::FindSessionsFiltered(const FAuraSessionFilter& Filter)
{
	// A JoinCode in Filter joins the match by itself (MainMenu2's code panel relies on it)
	FindSessionsFilteredInternal(Filter, false, true);
}

void UMultiplayerSessionsSubsystem::FindSessionsFilteredInternal(const FAuraSessionFilter& Filter, bool bQuickJoin, bool bAutoJoinCode)
{
	if (!SessionInterface.IsValid())
	{
		MultiplayerOnSessionsFound.Broadcast(TArray<FAuraSessionInfo>(), false);
		return;
	}

	if (bSearchInProgress)
	{
		// This is what stops an in-flight browse from silently eating an accepted Steam
		// invite (OnlineSessionAsyncLobbySteam.cpp:1207 drops the invite outright if
		// CurrentSessionSearch.IsValid()).
		MultiplayerOnSessionError.Broadcast(TEXT("A session search is already in progress."));
		return;
	}

	CurrentSessionFilter = Filter;
	bPendingCodeJoin = bAutoJoinCode && !Filter.JoinCode.IsEmpty();
	bPendingQuickJoin = bQuickJoin && Filter.JoinCode.IsEmpty();

	// Clear first: a search started right after a cancel would otherwise leave two bindings
	SessionInterface->ClearOnFindSessionsCompleteDelegate_Handle(FindSessionsCompleteDelegateHandle);
	FindSessionsCompleteDelegateHandle = SessionInterface->AddOnFindSessionsCompleteDelegate_Handle(FindSessionsCompleteDelegate);

	LastSessionSearch = MakeShareable(new FOnlineSessionSearch());
	LastSessionSearch->MaxSearchResults = Filter.MaxSearchResults;
	LastSessionSearch->bIsLanQuery = Online::GetSubsystem(GetWorld())->GetSubsystemName() == "NULL" ? true : false;
	LastSessionSearch->QuerySettings.Set(SEARCH_LOBBIES, true, EOnlineComparisonOp::Equals);
	LastSessionSearch->QuerySettings.Set(AuraSessionKeys::GameName, FString("AuraRedo3"), EOnlineComparisonOp::Equals);

	// Server-side filters. Empty/negative values are skipped on purpose - the engine
	// drops an empty-string lobby filter with a warning instead of matching "any".
	if (Filter.Difficulty >= 0)
	{
		LastSessionSearch->QuerySettings.Set(AuraSessionKeys::Difficulty, Filter.Difficulty, EOnlineComparisonOp::Equals);
	}
	if (!Filter.Rules.IsEmpty())
	{
		LastSessionSearch->QuerySettings.Set(AuraSessionKeys::Rules, Filter.Rules, EOnlineComparisonOp::Equals);
	}
	if (!Filter.JoinCode.IsEmpty())
	{
		LastSessionSearch->QuerySettings.Set(AuraSessionKeys::JoinCode, Filter.JoinCode, EOnlineComparisonOp::Equals);
	}

	const ULocalPlayer* LocalPlayer = GetWorld()->GetFirstLocalPlayerFromController();
	bSearchInProgress = true;

	if (!LocalPlayer || !SessionInterface->FindSessions(*LocalPlayer->GetPreferredUniqueNetId(), LastSessionSearch.ToSharedRef()))
	{
		bSearchInProgress = false;
		bPendingCodeJoin = false;
		bPendingQuickJoin = false;
		SessionInterface->ClearOnFindSessionsCompleteDelegate_Handle(FindSessionsCompleteDelegateHandle);
		MultiplayerOnSessionsFound.Broadcast(TArray<FAuraSessionInfo>(), false);
	}
}

void UMultiplayerSessionsSubsystem::JoinSession(const FOnlineSessionSearchResult& SessionResult)
{
	if (!SessionInterface.IsValid())
	{
		MultiplayerOnJoinSessionComplete.Broadcast(EOnJoinSessionCompleteResult::UnknownError);
		return;
	}

	// A session left over from a lobby we were in (host quit, kicked, travel failed) makes the
	// OSS refuse with AlreadyInSession. Destroy it first; OnDestroySessionComplete joins.
	if (SessionInterface->GetNamedSession(NAME_GameSession) != nullptr)
	{
		bJoinOnDestroy = true;
		PendingJoinResult = SessionResult;
		DestroySession();
		return;
	}

	JoinSessionCompleteDelegateHandle = SessionInterface->AddOnJoinSessionCompleteDelegate_Handle(JoinSessionCompleteDelegate);
	bMenuMessageLocked = false;

	const ULocalPlayer* LocalPlayer = GetWorld()->GetFirstLocalPlayerFromController();
	if (!LocalPlayer || !SessionInterface->JoinSession(*LocalPlayer->GetPreferredUniqueNetId(), NAME_GameSession, SessionResult))
	{
		SessionInterface->ClearOnJoinSessionCompleteDelegate_Handle(JoinSessionCompleteDelegateHandle);

		MultiplayerOnJoinSessionComplete.Broadcast(EOnJoinSessionCompleteResult::UnknownError);
	}
}

void UMultiplayerSessionsSubsystem::JoinSessionByCode(const FString& JoinCode)
{
	FString Cleaned = JoinCode.TrimStartAndEnd().ToUpper();
	Cleaned.ReplaceInline(TEXT(" "), TEXT(""));

	if (Cleaned.IsEmpty())
	{
		MultiplayerOnSessionError.Broadcast(TEXT("Enter a join code first."));
		return;
	}

	FAuraSessionFilter Filter;
	Filter.JoinCode = Cleaned;
	Filter.Difficulty = -1;
	Filter.Distance = EAuraSearchDistance::Worldwide;
	Filter.bOnlyJoinable = true;
	Filter.MaxSearchResults = 10000;

	// FindSessionsFiltered sets bPendingCodeJoin from Filter.JoinCode and auto-joins the
	// match in OnFindSessionsComplete once results come back.
	FindSessionsFiltered(Filter);
}

void UMultiplayerSessionsSubsystem::JoinCachedSession(int32 ResultIndex)
{
	if (!CachedResults.IsValidIndex(ResultIndex))
	{
		MultiplayerOnSessionError.Broadcast(TEXT("That session is no longer available."));
		return;
	}

	JoinSession(CachedResults[ResultIndex]);
}

void UMultiplayerSessionsSubsystem::DestroySession()
{
	if (!SessionInterface.IsValid())
	{
		MultiplayerOnDestroySessionComplete.Broadcast(false);
		return;
	}

	// One binding only, even when called again while a destroy is running
	SessionInterface->ClearOnDestroySessionCompleteDelegate_Handle(DestroySessionCompleteDelegateHandle);
	DestroySessionCompleteDelegateHandle = SessionInterface->AddOnDestroySessionCompleteDelegate_Handle(DestroySessionCompleteDelegate);

	// Already going away (a kick destroys, then the disconnect right after asks again): the running
	// destroy's completion handles the queued leave / join / re-host. Asking the OSS again fails it.
	const FNamedOnlineSession* ExistingSession = SessionInterface->GetNamedSession(NAME_GameSession);
	if (ExistingSession && ExistingSession->SessionState == EOnlineSessionState::Destroying)
	{
		return;
	}

	if (!SessionInterface->DestroySession(NAME_GameSession))
	{
		// Clears the handle and broadcasts false like before, and also resolves a pending
		// leave (still opens the level) or join (fails it) instead of leaving them hanging.
		OnDestroySessionComplete(NAME_GameSession, false);
	}
}

void UMultiplayerSessionsSubsystem::StartSession()
{
	if (!SessionInterface.IsValid())
	{
		return;
	}

	// Bind the completion delegate
	StartSessionCompleteDelegateHandle = SessionInterface->AddOnStartSessionCompleteDelegate_Handle(StartSessionCompleteDelegate);

	if (!SessionInterface->StartSession(NAME_GameSession))
	
	{
		SessionInterface->ClearOnStartSessionCompleteDelegate_Handle(StartSessionCompleteDelegateHandle);
		MultiplayerOnStartSessionComplete.Broadcast(false);
	}
}

void UMultiplayerSessionsSubsystem::LeaveSession()
{
	DestroySession();
}

bool UMultiplayerSessionsSubsystem::ShowSteamInviteUI()
{
	IOnlineSubsystem* Subsystem = Online::GetSubsystem(GetWorld());
	if (!Subsystem)
	{
		MultiplayerOnSessionError.Broadcast(TEXT("No online subsystem available."));
		return false;
	}

	const IOnlineExternalUIPtr ExternalUI = Subsystem->GetExternalUIInterface();
	if (!ExternalUI.IsValid())
	{
		MultiplayerOnSessionError.Broadcast(TEXT("Invite UI isn't available on this platform."));
		return false;
	}

	return ExternalUI->ShowInviteUI(0, NAME_GameSession);
}

FString UMultiplayerSessionsSubsystem::GetCurrentJoinCode() const
{
	return CurrentJoinCode;
}

bool UMultiplayerSessionsSubsystem::IsSearchInProgress() const
{
	return bSearchInProgress;
}

namespace
{
	// No I / O / 0 / 1, so a code never gets misread when someone reads it out over voice chat.
	const TCHAR* const JoinCodeAlphabet = TEXT("ABCDEFGHJKLMNPQRSTUVWXYZ23456789");
}

bool UMultiplayerSessionsSubsystem::IsJoinCodeCharacter(TCHAR Character)
{
	return FCString::Strchr(JoinCodeAlphabet, Character) != nullptr && Character != TEXT('\0');
}

FString UMultiplayerSessionsSubsystem::GenerateJoinCode()
{
	const FString Alphabet = JoinCodeAlphabet;

	FString Code;
	Code.Reserve(JoinCodeLength);
	for (int32 i = 0; i < JoinCodeLength; ++i)
	{
		Code.AppendChar(Alphabet[FMath::RandRange(0, Alphabet.Len() - 1)]);
	}
	return Code;
}

int32 UMultiplayerSessionsSubsystem::GetPingCapForDistance(EAuraSearchDistance Distance)
{
	switch (Distance)
	{
	case EAuraSearchDistance::Close:  return 60;
	case EAuraSearchDistance::Medium: return 120;
	case EAuraSearchDistance::Far:    return 250;
	case EAuraSearchDistance::Worldwide:
	default:
		return 0; // 0 == no cap. Steam's own lobby-distance filter is hardcoded engine-side
		          // (k_ELobbyDistanceFilterDefault), so this ping bucket is the closest we
		          // can get to a "Distance" filter from FOnlineSessionSearch.
	}
}

void UMultiplayerSessionsSubsystem::OnCreateSessionComplete(FName SessionName, bool bWasSuccessful)
{
	if (SessionInterface)
	{
		SessionInterface->ClearOnCreateSessionCompleteDelegate_Handle(CreateSessionCompleteDelegateHandle);
	}

	MultiplayerOnCreateSessionComplete.Broadcast(bWasSuccessful);
}

void UMultiplayerSessionsSubsystem::OnFindSessionsComplete(bool bWasSuccessful)
{
	// A search cancelled earlier finishing now, while the current one still runs: keep waiting.
	// The OSS marks its own search Done or Failed before reporting it.
	if (CancelledSearchesPending > 0 && LastSessionSearch.IsValid() && LastSessionSearch->SearchState == EOnlineAsyncTaskState::InProgress)
	{
		--CancelledSearchesPending;
		return;
	}
	CancelledSearchesPending = 0;

	if (SessionInterface)
	{
		SessionInterface->ClearOnFindSessionsCompleteDelegate_Handle(FindSessionsCompleteDelegateHandle);
	}
	bSearchInProgress = false;

	// A listener may start the next search from inside the broadcasts below, which sets these again
	// for that search: take this search's own first
	const bool bCodeJoinSearch = bPendingCodeJoin;
	const bool bQuickJoinSearch = bPendingQuickJoin;
	bPendingCodeJoin = false;
	bPendingQuickJoin = false;

	// BUGFIX: the old code dereferenced LastSessionSearch->SearchResults with no
	// validity check at all.
	if (!LastSessionSearch.IsValid() || LastSessionSearch->SearchResults.Num() <= 0)
	{
		MultiplayerOnFindSessionsComplete.Broadcast(TArray<FOnlineSessionSearchResult>(), false);
		MultiplayerOnSessionsFound.Broadcast(TArray<FAuraSessionInfo>(), bWasSuccessful);

		if (bCodeJoinSearch)
		{
			MultiplayerOnSessionError.Broadcast(TEXT("No session found with that code."));
		}
		if (bQuickJoinSearch)
		{
			MultiplayerOnSessionError.Broadcast(TEXT("No open lobbies found. Host one instead?"));
		}
		return;
	}

	//
	// Existing UMainMenu path - untouched, still drives FindSessions()/OnFindSessions().
	//
	for (const auto& Result : LastSessionSearch->SearchResults)
	{
		FString GameName;
		if (Result.Session.SessionSettings.Get(FName("GameName"), GameName))
		{
			UKismetSystemLibrary::PrintString(GetWorld(), TEXT("Found GameName: ") + GameName);
		}
	}
	
	TArray<FOnlineSessionSearchResult> FilteredResults;

	for (const auto& Result : LastSessionSearch->SearchResults)
	{
		FString GameName;
		if (Result.Session.SessionSettings.Get(FName("GameName"), GameName) && GameName == TEXT("AuraRedo3"))
		{
			FilteredResults.Add(Result);
		}
	}

	MultiplayerOnFindSessionsComplete.Broadcast(FilteredResults, bWasSuccessful);

	//
	// New MainMenu2 path: build FAuraSessionInfo rows, layering difficulty / rules /
	// Listed / ping-bucket / open-slots filtering on top of the server-side query.
	//
	CachedResults = LastSessionSearch->SearchResults;
	TArray<FAuraSessionInfo> SessionInfos;
	const int32 PingCapMs = GetPingCapForDistance(CurrentSessionFilter.Distance);
	const bool bIsCodeLookup = !CurrentSessionFilter.JoinCode.IsEmpty();

	for (int32 Index = 0; Index < CachedResults.Num(); ++Index)
	{
		const FOnlineSessionSearchResult& Result = CachedResults[Index];
		const FOnlineSessionSettings& Settings = Result.Session.SessionSettings;

		FString GameName;
		if (!Settings.Get(AuraSessionKeys::GameName, GameName) || GameName != TEXT("AuraRedo3"))
		{
			continue;
		}

		int32 Listed = 1;
		Settings.Get(AuraSessionKeys::Listed, Listed);

		const FAuraSessionInfo Info = MakeSessionInfo(Result.Session, Result.PingInMs, Index);

		if (Listed == 0 && !bIsCodeLookup)
		{
			continue; // CodeOnly: hidden from browse, only reachable via a code lookup
		}
		if (bIsCodeLookup && !Info.JoinCode.Equals(CurrentSessionFilter.JoinCode, ESearchCase::IgnoreCase))
		{
			continue;
		}
		if (CurrentSessionFilter.bOnlyJoinable && Info.OpenSlots <= 0)
		{
			continue;
		}
		if (PingCapMs > 0 && Info.PingInMs > PingCapMs)
		{
			continue;
		}
		if (CurrentSessionFilter.Difficulty >= 0 && Info.Difficulty != CurrentSessionFilter.Difficulty)
		{
			continue;
		}
		if (!CurrentSessionFilter.Rules.IsEmpty() && !Info.Rules.Equals(CurrentSessionFilter.Rules, ESearchCase::IgnoreCase))
		{
			continue;
		}

		SessionInfos.Add(Info);
	}

	MultiplayerOnSessionsFound.Broadcast(SessionInfos, bWasSuccessful);

	if (bQuickJoinSearch)
	{
		// Fill the fullest lobby first so players end up together, lowest ping breaks ties
		const FAuraSessionInfo* Best = nullptr;
		for (const FAuraSessionInfo& Info : SessionInfos)
		{
			if (Info.OpenSlots <= 0)
			{
				continue;
			}
			const int32 Players = Info.MaxSlots - Info.OpenSlots;
			const int32 BestPlayers = Best ? Best->MaxSlots - Best->OpenSlots : -1;
			if (!Best || Players > BestPlayers || (Players == BestPlayers && Info.PingInMs < Best->PingInMs))
			{
				Best = &Info;
			}
		}

		if (Best)
		{
			JoinCachedSession(Best->ResultIndex);
		}
		else
		{
			MultiplayerOnSessionError.Broadcast(TEXT("No open lobbies found. Host one instead?"));
		}
	}

	if (bCodeJoinSearch)
	{
		if (SessionInfos.Num() > 0)
		{
			JoinCachedSession(SessionInfos[0].ResultIndex);
		}
		else
		{
			MultiplayerOnSessionError.Broadcast(TEXT("No session found with that code."));
		}
	}
}

void UMultiplayerSessionsSubsystem::OnJoinSessionComplete(FName SessionName, EOnJoinSessionCompleteResult::Type Result)
{
	if (SessionInterface)
	{
		SessionInterface->ClearOnJoinSessionCompleteDelegate_Handle(JoinSessionCompleteDelegateHandle);
	}

	const bool bTravel = bTravelAfterJoin && Result == EOnJoinSessionCompleteResult::Success;
	bTravelAfterJoin = false;

	MultiplayerOnJoinSessionComplete.Broadcast(Result);

	// An invite accepted in game has no menu to do the ClientTravel. When a menu is open and
	// travels too, both set the same pending travel URL, which is harmless.
	if (bTravel)
	{
		TravelToJoinedSession();
	}
}

void UMultiplayerSessionsSubsystem::OnDestroySessionComplete(FName SessionName, bool bWasSuccessful)
{
	if (SessionInterface)
	{
		SessionInterface->ClearOnDestroySessionCompleteDelegate_Handle(DestroySessionCompleteDelegateHandle);
	}
	if (bWasSuccessful && bCreateSessionOnDestroy)
	{
		bCreateSessionOnDestroy = false;
		if (bRecreateWithHostSettings)
		{
			bRecreateWithHostSettings = false;
			CreateSessionWithSettings(PendingHostSettings);
		}
		else
		{
			CreateSession(LastNumPublicConnections, LastMatchType);
		}
	}

	if (!bWasSuccessful && bCreateSessionOnDestroy)
	{
		// The old session wouldn't go away, so the re-host can't happen: tell the menu
		// instead of leaving its Start button disabled forever.
		bCreateSessionOnDestroy = false;
		bRecreateWithHostSettings = false;
		MultiplayerOnCreateSessionComplete.Broadcast(false);
	}

	if (bJoinOnDestroy)
	{
		bJoinOnDestroy = false;
		if (bWasSuccessful)
		{
			JoinSession(PendingJoinResult);
		}
		else
		{
			bTravelAfterJoin = false;
			MultiplayerOnJoinSessionComplete.Broadcast(EOnJoinSessionCompleteResult::AlreadyInSession);
		}
	}

	if (bOpenLevelOnDestroy)
	{
		// Open the level even if the destroy failed - staying stuck in the lobby is worse
		OpenPendingLevel();
	}

	MultiplayerOnDestroySessionComplete.Broadcast(bWasSuccessful);
}

void UMultiplayerSessionsSubsystem::OnStartSessionComplete(FName SessionName, bool bWasSuccessful)
{
	if (SessionInterface)
	{
		SessionInterface->ClearOnStartSessionCompleteDelegate_Handle(StartSessionCompleteDelegateHandle);
	}

	// Tell anyone listening (like our UI or GameMode) that the session is officially active!
	MultiplayerOnStartSessionComplete.Broadcast(bWasSuccessful);
}

void UMultiplayerSessionsSubsystem::OnSessionUserInviteAccepted(const bool bWasSuccessful, const int32 ControllerId, FUniqueNetIdPtr UserId, const FOnlineSessionSearchResult& InviteResult)
{
	if (!bWasSuccessful || !InviteResult.IsValid())
	{
		MultiplayerOnInviteAccepted.Broadcast(false);
		MultiplayerOnSessionError.Broadcast(TEXT("Failed to accept the Steam invite."));
		return;
	}

	// Reuses the existing join path; OnJoinSessionComplete then travels by itself
	// (bTravelAfterJoin), so the invite also works in game with no menu listening.
	bTravelAfterJoin = true;
	JoinSession(InviteResult);
	MultiplayerOnInviteAccepted.Broadcast(true);
}

//
// MainMenu3 API
//
void UMultiplayerSessionsSubsystem::QuickJoin(const FAuraSessionFilter& Filter)
{
	FAuraSessionFilter QuickFilter = Filter;
	QuickFilter.JoinCode.Reset();
	QuickFilter.bOnlyJoinable = true;

	FindSessionsFilteredInternal(QuickFilter, true, false);
}

void UMultiplayerSessionsSubsystem::CancelFindSessions()
{
	if (!bSearchInProgress || !SessionInterface.IsValid())
	{
		return;
	}

	// Unbind first so the cancelled search's results never reach the menu
	SessionInterface->ClearOnFindSessionsCompleteDelegate_Handle(FindSessionsCompleteDelegateHandle);
	bSearchInProgress = false;
	++CancelledSearchesPending;
	bPendingCodeJoin = false;
	bPendingQuickJoin = false;

	bCancelFindPending = true;
	SessionInterface->ClearOnCancelFindSessionsCompleteDelegate_Handle(CancelFindSessionsCompleteDelegateHandle);
	CancelFindSessionsCompleteDelegateHandle = SessionInterface->AddOnCancelFindSessionsCompleteDelegate_Handle(CancelFindSessionsCompleteDelegate);

	if (!SessionInterface->CancelFindSessions())
	{
		OnCancelFindSessionsComplete(false);
	}
}

void UMultiplayerSessionsSubsystem::OnCancelFindSessionsComplete(bool bWasSuccessful)
{
	if (SessionInterface)
	{
		SessionInterface->ClearOnCancelFindSessionsCompleteDelegate_Handle(CancelFindSessionsCompleteDelegateHandle);
	}

	if (!bCancelFindPending)
	{
		return;
	}
	bCancelFindPending = false;

	// Either way the search's results are already dropped
	MultiplayerOnFindSessionsCancelled.Broadcast();
}

void UMultiplayerSessionsSubsystem::UpdateHostSettings(const FAuraHostSettings& HostSettings)
{
	FOnlineSessionSettings* CurrentSettings = SessionInterface.IsValid() ? SessionInterface->GetSessionSettings(NAME_GameSession) : nullptr;
	if (!CurrentSettings || !IsHostingSession())
	{
		MultiplayerOnUpdateSessionComplete.Broadcast(false);
		MultiplayerOnSessionError.Broadcast(TEXT("Only the host can change the lobby settings."));
		return;
	}

	// Keep the code players already have
	FString JoinCode;
	CurrentSettings->Get(AuraSessionKeys::JoinCode, JoinCode);
	if (JoinCode.IsEmpty())
	{
		JoinCode = CurrentJoinCode.IsEmpty() ? GenerateJoinCode() : CurrentJoinCode;
	}
	CurrentJoinCode = JoinCode;

	FOnlineSessionSettings UpdatedSettings = *CurrentSettings;
	ApplyHostSettings(UpdatedSettings, HostSettings, JoinCode);

	// Only one update in flight: a second Add without a Clear would leave a stale binding behind
	SessionInterface->ClearOnUpdateSessionCompleteDelegate_Handle(UpdateSessionCompleteDelegateHandle);
	UpdateSessionCompleteDelegateHandle = SessionInterface->AddOnUpdateSessionCompleteDelegate_Handle(UpdateSessionCompleteDelegate);

	if (!SessionInterface->UpdateSession(NAME_GameSession, UpdatedSettings, true))
	{
		SessionInterface->ClearOnUpdateSessionCompleteDelegate_Handle(UpdateSessionCompleteDelegateHandle);
		MultiplayerOnUpdateSessionComplete.Broadcast(false);
		MultiplayerOnSessionError.Broadcast(TEXT("Could not update the lobby settings."));
	}
}

void UMultiplayerSessionsSubsystem::OnUpdateSessionComplete(FName SessionName, bool bWasSuccessful)
{
	if (SessionInterface)
	{
		SessionInterface->ClearOnUpdateSessionCompleteDelegate_Handle(UpdateSessionCompleteDelegateHandle);
	}

	MultiplayerOnUpdateSessionComplete.Broadcast(bWasSuccessful);
	if (!bWasSuccessful)
	{
		MultiplayerOnSessionError.Broadcast(TEXT("Could not update the lobby settings."));
	}
}

bool UMultiplayerSessionsSubsystem::GetCurrentSessionInfo(FAuraSessionInfo& OutInfo) const
{
	if (!SessionInterface.IsValid())
	{
		return false;
	}

	const FNamedOnlineSession* Session = SessionInterface->GetNamedSession(NAME_GameSession);
	if (!Session)
	{
		return false;
	}

	OutInfo = MakeSessionInfo(*Session, 0, INDEX_NONE);
	if (OutInfo.JoinCode.IsEmpty() && Session->bHosting)
	{
		OutInfo.JoinCode = CurrentJoinCode;
	}
	return true;
}

bool UMultiplayerSessionsSubsystem::GetCurrentHostSettings(FAuraHostSettings& OutSettings) const
{
	FAuraSessionInfo Info;
	if (!GetCurrentSessionInfo(Info))
	{
		return false;
	}

	OutSettings.NumPublicConnections = Info.MaxSlots;
	OutSettings.MatchType = Info.MatchType;
	OutSettings.Privacy = Info.Privacy;
	OutSettings.Difficulty = Info.Difficulty;
	OutSettings.Rules = Info.Rules;
	OutSettings.JoinCode = Info.JoinCode;
	OutSettings.LobbyName = Info.LobbyName;
	OutSettings.bAllowJoinInProgress = Info.bAllowJoinInProgress;
	return true;
}

bool UMultiplayerSessionsSubsystem::IsInSession() const
{
	return SessionInterface.IsValid() && SessionInterface->GetNamedSession(NAME_GameSession) != nullptr;
}

bool UMultiplayerSessionsSubsystem::IsHostingSession() const
{
	if (!SessionInterface.IsValid())
	{
		return false;
	}

	const FNamedOnlineSession* Session = SessionInterface->GetNamedSession(NAME_GameSession);
	return Session && Session->bHosting;
}

bool UMultiplayerSessionsSubsystem::IsSessionOwner(const FUniqueNetIdRepl& PlayerId) const
{
	if (!SessionInterface.IsValid() || !PlayerId.IsValid())
	{
		return false;
	}

	const FNamedOnlineSession* Session = SessionInterface->GetNamedSession(NAME_GameSession);
	return Session && Session->OwningUserId.IsValid() && Session->OwningUserId->ToString() == PlayerId.ToString();
}

void UMultiplayerSessionsSubsystem::TravelToJoinedSession()
{
	if (!SessionInterface.IsValid())
	{
		return;
	}

	FString Address;
	if (!SessionInterface->GetResolvedConnectString(NAME_GameSession, Address))
	{
		MultiplayerOnSessionError.Broadcast(TEXT("Could not retrieve the host's address."));
		return;
	}

	if (APlayerController* PlayerController = GetGameInstance()->GetFirstLocalPlayerController())
	{
		PlayerController->ClientTravel(Address, ETravelType::TRAVEL_Absolute);
	}
}

void UMultiplayerSessionsSubsystem::LeaveSessionAndOpenLevel(const FString& LevelPath)
{
	PendingLevelPath = LevelPath;

	if (IsInSession())
	{
		// Leaving wins over anything queued behind a destroy
		bCreateSessionOnDestroy = false;
		bRecreateWithHostSettings = false;
		bJoinOnDestroy = false;
		bOpenLevelOnDestroy = true;
		DestroySession();
		return;
	}

	OpenPendingLevel();
}

void UMultiplayerSessionsSubsystem::OpenPendingLevel()
{
	bOpenLevelOnDestroy = false;

	UWorld* World = GetGameInstance() ? GetGameInstance()->GetWorld() : nullptr;
	if (World && !PendingLevelPath.IsEmpty())
	{
		UGameplayStatics::OpenLevel(World, FName(*PendingLevelPath));
	}
}

bool UMultiplayerSessionsSubsystem::ShowFriendsUI()
{
	IOnlineSubsystem* Subsystem = Online::GetSubsystem(GetWorld());
	IOnlineExternalUIPtr ExternalUI;
	if (Subsystem)
	{
		ExternalUI = Subsystem->GetExternalUIInterface();
	}
	if (!ExternalUI.IsValid())
	{
		MultiplayerOnSessionError.Broadcast(TEXT("Friends list isn't available on this platform."));
		return false;
	}

	return ExternalUI->ShowFriendsUI(0);
}

FString UMultiplayerSessionsSubsystem::ConsumePendingMenuMessage()
{
	FString Message = MoveTemp(PendingMenuMessage);
	PendingMenuMessage.Reset();
	bMenuMessageLocked = false;
	return Message;
}

void UMultiplayerSessionsSubsystem::LookupSessionByCode(const FString& JoinCode)
{
	FString Cleaned = JoinCode.TrimStartAndEnd().ToUpper();
	Cleaned.ReplaceInline(TEXT(" "), TEXT(""));

	if (Cleaned.IsEmpty())
	{
		MultiplayerOnSessionError.Broadcast(TEXT("Enter a join code first."));
		return;
	}

	FAuraSessionFilter Filter;
	Filter.JoinCode = Cleaned;
	Filter.Distance = EAuraSearchDistance::Worldwide;
	// Full lobbies come back too, so the menu can say "that lobby is full" instead of "no lobby"
	Filter.bOnlyJoinable = false;

	FindSessionsFilteredInternal(Filter, false, false);
}

bool UMultiplayerSessionsSubsystem::IsOnlineServiceAvailable() const
{
	return SessionInterface.IsValid();
}

FString UMultiplayerSessionsSubsystem::GetOnlineServiceName() const
{
	IOnlineSubsystem* Subsystem = Online::GetSubsystem(GetWorld());
	return Subsystem ? Subsystem->GetSubsystemName().ToString() : FString();
}

FString UMultiplayerSessionsSubsystem::GetLocalPlayerNickname() const
{
	IOnlineSubsystem* Subsystem = Online::GetSubsystem(GetWorld());
	IOnlineIdentityPtr Identity;
	if (Subsystem)
	{
		Identity = Subsystem->GetIdentityInterface();
	}
	if (!Identity.IsValid())
	{
		return FString();
	}

	// Controller 0, the same user every other call here acts for
	return Identity->GetPlayerNickname(0);
}

bool UMultiplayerSessionsSubsystem::ShowPlayerProfile(const FUniqueNetIdRepl& PlayerId)
{
	IOnlineSubsystem* Subsystem = Online::GetSubsystem(GetWorld());
	IOnlineExternalUIPtr ExternalUI;
	IOnlineIdentityPtr Identity;
	if (Subsystem)
	{
		ExternalUI = Subsystem->GetExternalUIInterface();
		Identity = Subsystem->GetIdentityInterface();
	}

	FUniqueNetIdPtr LocalId;
	if (Identity.IsValid())
	{
		LocalId = Identity->GetUniquePlayerId(0);
	}
	if (!ExternalUI.IsValid() || !LocalId.IsValid() || !PlayerId.IsValid())
	{
		MultiplayerOnSessionError.Broadcast(TEXT("Player profiles aren't available on this platform."));
		return false;
	}

	return ExternalUI->ShowProfileUI(*LocalId, *PlayerId.GetUniqueNetId());
}

bool UMultiplayerSessionsSubsystem::KickPlayer(APlayerController* Player, const FText& Reason, bool bBan)
{
	UWorld* World = Player ? Player->GetWorld() : nullptr;
	AGameModeBase* GameMode = World ? World->GetAuthGameMode() : nullptr;
	if (!GameMode || !GameMode->GameSession || Player->IsLocalController())
	{
		return false;
	}

	if (bBan && Player->PlayerState && Player->PlayerState->GetUniqueId().IsValid())
	{
		BannedPlayerIds.Add(Player->PlayerState->GetUniqueId().ToString());
	}

	// Sends ClientWasKicked(Reason) to them, then removes their controller
	return GameMode->GameSession->KickPlayer(Player, Reason);
}

bool UMultiplayerSessionsSubsystem::IsPlayerBanned(const FUniqueNetIdRepl& PlayerId) const
{
	return PlayerId.IsValid() && BannedPlayerIds.Contains(PlayerId.ToString());
}

void UMultiplayerSessionsSubsystem::ClearBans()
{
	BannedPlayerIds.Reset();
}

FString UMultiplayerSessionsSubsystem::CheckJoinAllowed(const FUniqueNetIdRepl& PlayerId, int32 NumPlayersInGame) const
{
	if (IsPlayerBanned(PlayerId))
	{
		return TEXT("You are banned from this lobby.");
	}

	// The OSS only counts lobby members; this also stops anyone connecting by address once
	// every slot is taken. NumPublicConnections includes the host.
	const FOnlineSessionSettings* Settings = SessionInterface.IsValid() ? SessionInterface->GetSessionSettings(NAME_GameSession) : nullptr;
	if (Settings && IsHostingSession() && Settings->NumPublicConnections > 0 && NumPlayersInGame >= Settings->NumPublicConnections)
	{
		return TEXT("That lobby is full.");
	}

	return FString();
}

void UMultiplayerSessionsSubsystem::NotifyKicked(const FText& Reason)
{
	PendingMenuMessage = Reason.IsEmpty() ? TEXT("You were removed from the lobby by the host.") : Reason.ToString();
	bMenuMessageLocked = true;

	DestroySessionAfterFailure();
	MultiplayerOnSessionError.Broadcast(PendingMenuMessage);
}

void UMultiplayerSessionsSubsystem::ApplyHostSettings(FOnlineSessionSettings& Settings, const FAuraHostSettings& HostSettings, const FString& JoinCode)
{
	Settings.NumPublicConnections = HostSettings.NumPublicConnections;
	Settings.bAllowJoinInProgress = HostSettings.bAllowJoinInProgress;
	// This is the flag BuildLobbyType() reads to pick k_ELobbyTypeFriendsOnly over
	// k_ELobbyTypePublic (OnlineSessionAsyncLobbySteam.cpp:70-95).
	Settings.bAllowJoinViaPresenceFriendsOnly = (HostSettings.Privacy == EAuraSessionPrivacy::FriendsOnly);

	Settings.Set(AuraSessionKeys::MatchType, HostSettings.MatchType, EOnlineDataAdvertisementType::ViaOnlineServiceAndPing);
	Settings.Set(AuraSessionKeys::Difficulty, HostSettings.Difficulty, EOnlineDataAdvertisementType::ViaOnlineServiceAndPing);
	Settings.Set(AuraSessionKeys::Rules, HostSettings.Rules, EOnlineDataAdvertisementType::ViaOnlineServiceAndPing);
	Settings.Set(AuraSessionKeys::JoinCode, JoinCode, EOnlineDataAdvertisementType::ViaOnlineServiceAndPing);
	Settings.Set(AuraSessionKeys::LobbyName, HostSettings.LobbyName, EOnlineDataAdvertisementType::ViaOnlineServiceAndPing);
	// CodeOnly is still advertised (so a typed code resolves) but Listed=0 tells the
	// browse UI to filter it out - see FindSessionsFiltered / OnFindSessionsComplete.
	Settings.Set(AuraSessionKeys::Listed, HostSettings.Privacy == EAuraSessionPrivacy::CodeOnly ? 0 : 1, EOnlineDataAdvertisementType::ViaOnlineServiceAndPing);
}

FAuraSessionInfo UMultiplayerSessionsSubsystem::MakeSessionInfo(const FOnlineSession& Session, int32 PingInMs, int32 ResultIndex)
{
	const FOnlineSessionSettings& Settings = Session.SessionSettings;

	FAuraSessionInfo Info;
	Info.SessionId = Session.GetSessionIdStr();
	Info.HostName = Session.OwningUserName;
	Settings.Get(AuraSessionKeys::MatchType, Info.MatchType);
	Settings.Get(AuraSessionKeys::Rules, Info.Rules);
	Settings.Get(AuraSessionKeys::JoinCode, Info.JoinCode);
	Settings.Get(AuraSessionKeys::Difficulty, Info.Difficulty);
	Settings.Get(AuraSessionKeys::LobbyName, Info.LobbyName);
	Info.PingInMs = PingInMs;
	Info.OpenSlots = Session.NumOpenPublicConnections;
	Info.MaxSlots = Settings.NumPublicConnections;
	Info.ResultIndex = ResultIndex;
	Info.bAllowJoinInProgress = Settings.bAllowJoinInProgress;

	int32 Listed = 1;
	Settings.Get(AuraSessionKeys::Listed, Listed);
	if (Listed == 0)
	{
		Info.Privacy = EAuraSessionPrivacy::CodeOnly;
	}
	else if (Settings.bAllowJoinViaPresenceFriendsOnly)
	{
		Info.Privacy = EAuraSessionPrivacy::FriendsOnly;
	}
	else
	{
		Info.Privacy = EAuraSessionPrivacy::Public;
	}
	return Info;
}

void UMultiplayerSessionsSubsystem::HandleNetworkFailure(UWorld* World, UNetDriver* NetDriver, ENetworkFailure::Type FailureType, const FString& ErrorString)
{
	// GEngine's events fire for every game instance (PIE runs several) and every net driver
	if (World && World->GetGameInstance() != GetGameInstance())
	{
		return;
	}
	if (NetDriver && NetDriver->NetDriverName != NAME_GameNetDriver)
	{
		// A refused or failed connect (PreLogin's "You are banned from this lobby.", a handshake
		// timeout) is reported by the pending net driver, which has no world yet
		if (NetDriver->NetDriverName != NAME_PendingNetDriver)
		{
			return;
		}
		const FWorldContext* PendingContext = GEngine ? GEngine->GetWorldContextFromPendingNetGameNetDriver(NetDriver) : nullptr;
		// No context left to check against: only a game with a single game instance can be sure it's its own
		const bool bOwnConnect = PendingContext ? PendingContext->OwningGameInstance == GetGameInstance() : !GIsEditor;
		if (!bOwnConnect)
		{
			return;
		}
	}
	// Only a client losing its host. A listen server also hears about clients timing out,
	// and must keep its session for everyone else.
	const bool bIsClient = NetDriver ? !NetDriver->IsServer() : (World && World->GetNetMode() == NM_Client);
	if (!bIsClient)
	{
		return;
	}

	if (bMenuMessageLocked)
	{
		// Kicked: the disconnect that follows must not replace the reason
		DestroySessionAfterFailure();
		return;
	}

	switch (FailureType)
	{
	case ENetworkFailure::ConnectionLost:
	case ENetworkFailure::ConnectionTimeout:
		PendingMenuMessage = TEXT("Lost connection to the host.");
		break;
	case ENetworkFailure::PendingConnectionFailure:
		// The host refused the connection with its reason (PreLogin: banned, lobby full), or the handshake failed
		PendingMenuMessage = ErrorString.IsEmpty() ? TEXT("Couldn't connect to the host.") : ErrorString;
		break;
	case ENetworkFailure::FailureReceived:
		// The server's own reason for closing the connection
		PendingMenuMessage = ErrorString.IsEmpty() ? TEXT("The host closed the connection.") : ErrorString;
		break;
	case ENetworkFailure::OutdatedClient:
	case ENetworkFailure::OutdatedServer:
		PendingMenuMessage = TEXT("Your game version doesn't match the host's.");
		break;
	default:
		PendingMenuMessage = FString::Printf(TEXT("Disconnected: %s"), ErrorString.IsEmpty() ? ENetworkFailure::ToString(FailureType) : *ErrorString);
		break;
	}

	DestroySessionAfterFailure();
	MultiplayerOnSessionError.Broadcast(PendingMenuMessage);
}

void UMultiplayerSessionsSubsystem::HandleTravelFailure(UWorld* World, ETravelFailure::Type FailureType, const FString& ErrorString)
{
	if (World && World->GetGameInstance() != GetGameInstance())
	{
		return;
	}

	if (bMenuMessageLocked)
	{
		DestroySessionAfterFailure();
		return;
	}

	if (FailureType == ETravelFailure::PendingNetGameCreateFailure && !ErrorString.IsEmpty())
	{
		// The pending connection couldn't start, ErrorString says why
		PendingMenuMessage = ErrorString;
	}
	else
	{
		PendingMenuMessage = FString::Printf(TEXT("Couldn't reach the lobby: %s"), ErrorString.IsEmpty() ? ETravelFailure::ToString(FailureType) : *ErrorString);
	}

	DestroySessionAfterFailure();
	MultiplayerOnSessionError.Broadcast(PendingMenuMessage);
}

void UMultiplayerSessionsSubsystem::DestroySessionAfterFailure()
{
	bCreateSessionOnDestroy = false;
	bRecreateWithHostSettings = false;
	bJoinOnDestroy = false;
	bTravelAfterJoin = false;

	if (IsInSession())
	{
		DestroySession();
	}
}

void UMultiplayerSessionsSubsystem::OnFindSessionsCompleteForHeadless(const TArray<FOnlineSessionSearchResult>& SessionResults, bool bWasSuccessful)
{
	for (auto Result : SessionResults)
	{
		FString SettingsValue;
		//TODO Add Search settings to filter
		Result.Session.SessionSettings.Get(FName("MatchType"), SettingsValue);
		if (SettingsValue == FString("AuraRedo3"))
		{
			JoinSession(Result);
			return;
		}
	}
}

void UMultiplayerSessionsSubsystem::OnJoinSessionCompleteForHeadlesss(EOnJoinSessionCompleteResult::Type Result)
{
		if (SessionInterface.IsValid())
		{
			FString Address;
			SessionInterface->GetResolvedConnectString(NAME_GameSession, Address);

			APlayerController* PlayerController = GetGameInstance()->GetFirstLocalPlayerController();
			if (PlayerController)
			{
				PlayerController->ClientTravel(Address, ETravelType::TRAVEL_Absolute);
			}
		}
}

void UMultiplayerSessionsSubsystem::StartHeadlessLogic(UWorld* InWorld, const UWorld::InitializationValues IVS)
{
		if (InWorld)
		{
			UE_LOG(LogTemp, Warning, TEXT("HeadlessClient = %s"),
		FParse::Param(FCommandLine::Get(), TEXT("HeadlessClient"))
			? TEXT("true")
			: TEXT("false"));
		
			if (FParse::Param(FCommandLine::Get(), TEXT("HeadlessClient")))
			{
				FTimerHandle TimerHandle;
				InWorld->GetTimerManager().SetTimer(TimerHandle,this,&ThisClass::JoinSessionAtInitialisation,1,false,1);
				MultiplayerOnFindSessionsComplete.AddUObject(this,&ThisClass::OnFindSessionsCompleteForHeadless);
				MultiplayerOnJoinSessionComplete.AddUObject(this,&ThisClass::OnJoinSessionCompleteForHeadlesss);
			}
		}
}

void UMultiplayerSessionsSubsystem::StartHeadlessLogic2()
{
	if (UWorld* World=GetWorld())
	{
		UE_LOG(LogTemp, Warning, TEXT("HeadlessClient = %s"),
	FParse::Param(FCommandLine::Get(), TEXT("HeadlessClient"))
		? TEXT("true")
		: TEXT("false"));
		
		if (FParse::Param(FCommandLine::Get(), TEXT("HeadlessClient")))
		{
			FTimerHandle TimerHandle;
			World->GetTimerManager().SetTimer(TimerHandle,this,&ThisClass::JoinSessionAtInitialisation,1,false,1);
			MultiplayerOnFindSessionsComplete.AddUObject(this,&ThisClass::OnFindSessionsCompleteForHeadless);
			MultiplayerOnJoinSessionComplete.AddUObject(this,&ThisClass::OnJoinSessionCompleteForHeadlesss);
		}
	}
}

void UMultiplayerSessionsSubsystem::JoinSessionAtInitialisation()
{
		FindSessions(10000);
}
