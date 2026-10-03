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

UMultiplayerSessionsSubsystem::UMultiplayerSessionsSubsystem():
	CreateSessionCompleteDelegate(FOnCreateSessionCompleteDelegate::CreateUObject(this, &ThisClass::OnCreateSessionComplete)),
	FindSessionsCompleteDelegate(FOnFindSessionsCompleteDelegate::CreateUObject(this, &ThisClass::OnFindSessionsComplete)),
	JoinSessionCompleteDelegate(FOnJoinSessionCompleteDelegate::CreateUObject(this, &ThisClass::OnJoinSessionComplete)),
	DestroySessionCompleteDelegate(FOnDestroySessionCompleteDelegate::CreateUObject(this, &ThisClass::OnDestroySessionComplete)),
	StartSessionCompleteDelegate(FOnStartSessionCompleteDelegate::CreateUObject(this, &ThisClass::OnStartSessionComplete))
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
}

void UMultiplayerSessionsSubsystem::Deinitialize()
{
	if (SessionInterface.IsValid())
	{
		SessionInterface->ClearOnSessionUserInviteAcceptedDelegate_Handle(InviteAcceptedDelegateHandle);
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

	LastSessionSettings = MakeShareable(new FOnlineSessionSettings());
	LastSessionSettings->bIsLANMatch = Online::GetSubsystem(GetWorld())->GetSubsystemName() == "NULL" ? true : false;
	LastSessionSettings->NumPublicConnections = HostSettings.NumPublicConnections;
	LastSessionSettings->bAllowJoinInProgress = true;
	LastSessionSettings->bAllowJoinViaPresence = true;
	LastSessionSettings->bShouldAdvertise = true;
	LastSessionSettings->bUsesPresence = true;
	LastSessionSettings->bUseLobbiesIfAvailable = true;
	LastSessionSettings->bAllowInvites = true;
	// This is the flag BuildLobbyType() reads to pick k_ELobbyTypeFriendsOnly over
	// k_ELobbyTypePublic (OnlineSessionAsyncLobbySteam.cpp:70-95).
	LastSessionSettings->bAllowJoinViaPresenceFriendsOnly = (HostSettings.Privacy == EAuraSessionPrivacy::FriendsOnly);
	LastSessionSettings->BuildUniqueId = 1;

	LastSessionSettings->Set(AuraSessionKeys::GameName, FString("AuraRedo3"), EOnlineDataAdvertisementType::ViaOnlineServiceAndPing);
	LastSessionSettings->Set(AuraSessionKeys::MatchType, HostSettings.MatchType, EOnlineDataAdvertisementType::ViaOnlineServiceAndPing);
	LastSessionSettings->Set(AuraSessionKeys::Difficulty, HostSettings.Difficulty, EOnlineDataAdvertisementType::ViaOnlineServiceAndPing);
	LastSessionSettings->Set(AuraSessionKeys::Rules, HostSettings.Rules, EOnlineDataAdvertisementType::ViaOnlineServiceAndPing);
	LastSessionSettings->Set(AuraSessionKeys::JoinCode, CurrentJoinCode, EOnlineDataAdvertisementType::ViaOnlineServiceAndPing);
	// CodeOnly is still advertised (so a typed code resolves) but Listed=0 tells the
	// browse UI to filter it out - see FindSessionsFiltered / OnFindSessionsComplete.
	LastSessionSettings->Set(AuraSessionKeys::Listed, HostSettings.Privacy == EAuraSessionPrivacy::CodeOnly ? 0 : 1, EOnlineDataAdvertisementType::ViaOnlineServiceAndPing);

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
	bPendingCodeJoin = !Filter.JoinCode.IsEmpty();

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

	JoinSessionCompleteDelegateHandle = SessionInterface->AddOnJoinSessionCompleteDelegate_Handle(JoinSessionCompleteDelegate);

	const ULocalPlayer* LocalPlayer = GetWorld()->GetFirstLocalPlayerFromController();
	if (!SessionInterface->JoinSession(*LocalPlayer->GetPreferredUniqueNetId(), NAME_GameSession, SessionResult))
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

	DestroySessionCompleteDelegateHandle = SessionInterface->AddOnDestroySessionCompleteDelegate_Handle(DestroySessionCompleteDelegate);

	if (!SessionInterface->DestroySession(NAME_GameSession))
	{
		SessionInterface->ClearOnDestroySessionCompleteDelegate_Handle(DestroySessionCompleteDelegateHandle);
		MultiplayerOnDestroySessionComplete.Broadcast(false);
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

FString UMultiplayerSessionsSubsystem::GenerateJoinCode()
{
	// No I / O / 0 / 1, so a code never gets misread when someone reads it out over voice chat.
	static const FString Alphabet = TEXT("ABCDEFGHJKLMNPQRSTUVWXYZ23456789");

	FString Code;
	Code.Reserve(6);
	for (int32 i = 0; i < 6; ++i)
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
	if (SessionInterface)
	{
		SessionInterface->ClearOnFindSessionsCompleteDelegate_Handle(FindSessionsCompleteDelegateHandle);
	}
	bSearchInProgress = false;

	// BUGFIX: the old code dereferenced LastSessionSearch->SearchResults with no
	// validity check at all.
	if (!LastSessionSearch.IsValid() || LastSessionSearch->SearchResults.Num() <= 0)
	{
		MultiplayerOnFindSessionsComplete.Broadcast(TArray<FOnlineSessionSearchResult>(), false);
		MultiplayerOnSessionsFound.Broadcast(TArray<FAuraSessionInfo>(), bWasSuccessful);

		if (bPendingCodeJoin)
		{
			bPendingCodeJoin = false;
			MultiplayerOnSessionError.Broadcast(TEXT("No session found with that code."));
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

		FString JoinCodeValue;
		Settings.Get(AuraSessionKeys::JoinCode, JoinCodeValue);

		if (Listed == 0 && !bIsCodeLookup)
		{
			continue; // CodeOnly: hidden from browse, only reachable via a code lookup
		}
		if (bIsCodeLookup && !JoinCodeValue.Equals(CurrentSessionFilter.JoinCode, ESearchCase::IgnoreCase))
		{
			continue;
		}
		if (CurrentSessionFilter.bOnlyJoinable && Result.Session.NumOpenPublicConnections <= 0)
		{
			continue;
		}
		if (PingCapMs > 0 && Result.PingInMs > PingCapMs)
		{
			continue;
		}

		int32 Difficulty = 0;
		Settings.Get(AuraSessionKeys::Difficulty, Difficulty);
		if (CurrentSessionFilter.Difficulty >= 0 && Difficulty != CurrentSessionFilter.Difficulty)
		{
			continue;
		}

		FString Rules;
		Settings.Get(AuraSessionKeys::Rules, Rules);
		if (!CurrentSessionFilter.Rules.IsEmpty() && !Rules.Equals(CurrentSessionFilter.Rules, ESearchCase::IgnoreCase))
		{
			continue;
		}

		FString MatchTypeValue;
		Settings.Get(AuraSessionKeys::MatchType, MatchTypeValue);

		FAuraSessionInfo Info;
		Info.SessionId = Result.GetSessionIdStr();
		Info.HostName = Result.Session.OwningUserName;
		Info.MatchType = MatchTypeValue;
		Info.Rules = Rules;
		Info.JoinCode = JoinCodeValue;
		Info.Difficulty = Difficulty;
		Info.PingInMs = Result.PingInMs;
		Info.OpenSlots = Result.Session.NumOpenPublicConnections;
		Info.MaxSlots = Settings.NumPublicConnections;
		Info.ResultIndex = Index;
		SessionInfos.Add(Info);
	}

	MultiplayerOnSessionsFound.Broadcast(SessionInfos, bWasSuccessful);

	if (bPendingCodeJoin)
	{
		bPendingCodeJoin = false;
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

	MultiplayerOnJoinSessionComplete.Broadcast(Result);
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

	// Reuses the existing join path, so MultiplayerOnJoinSessionComplete drives the
	// ClientTravel exactly like a normal Browse-list join.
	JoinSession(InviteResult);
	MultiplayerOnInviteAccepted.Broadcast(true);
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
