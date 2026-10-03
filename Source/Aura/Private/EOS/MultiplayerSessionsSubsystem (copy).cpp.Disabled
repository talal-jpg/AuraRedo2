// Fill out your copyright notice in the Description page of Project Settings.


#include "EOS/MultiplayerSessionsSubsystem.h"
#include "OnlineSubsystem.h"
#include "OnlineSessionSettings.h"
#include "Online/OnlineSessionNames.h"
#include "OnlineSubsystemUtils.h"
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
	
	// IVoiceChat::Get()
	
	FString SubsystemName = Subsystem->GetSubsystemName().ToString();

	UKismetSystemLibrary::PrintString(GetWorld(),FString::Printf(TEXT("Subsystem: %s"), *SubsystemName),true,true,FLinearColor::Green,30.f);
	
	if (Subsystem)
	{
		SessionInterface = Subsystem->GetSessionInterface();
		UKismetSystemLibrary::PrintString(GetWorld(), TEXT("SessionInterfaceSet"),true,true,FLinearColor::Black,30);
	}
	
	FWorldDelegates::OnPostWorldInitialization.AddUObject(this,&ThisClass::StartHeadlessLogic);
	
	
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
		LastNumPublicConnections = NumPublicConnections;
		LastMatchType = MatchType;

		DestroySession();
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
	if (!SessionInterface->FindSessions(*LocalPlayer->GetPreferredUniqueNetId(), LastSessionSearch.ToSharedRef()))
	{
		SessionInterface->ClearOnFindSessionsCompleteDelegate_Handle(FindSessionsCompleteDelegateHandle);

		MultiplayerOnFindSessionsComplete.Broadcast(TArray<FOnlineSessionSearchResult>(), false);
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

	if (LastSessionSearch->SearchResults.Num() <= 0)
	{
		MultiplayerOnFindSessionsComplete.Broadcast(TArray<FOnlineSessionSearchResult>(), false);
		return;
	}
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
		CreateSession(LastNumPublicConnections, LastMatchType);
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
