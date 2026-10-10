// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include <Subsystems/GameInstanceSubsystem.h>

#include "Engine/World.h"
#include "Interfaces/OnlineSessionInterface.h"
#include "OnlineSessionSettings.h"
#include "EOS/MultiplayerSessionTypes.h"
#include "MultiplayerSessionsSubsystem.generated.h"

//
// Delcaring our own custom delegates for the Menu class to bind callbacks to
//
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FMultiplayerOnCreateSessionComplete, bool, bWasSuccessful);
DECLARE_MULTICAST_DELEGATE_TwoParams(FMultiplayerOnFindSessionsComplete, const TArray<FOnlineSessionSearchResult>& SessionResults, bool bWasSuccessful);
DECLARE_MULTICAST_DELEGATE_OneParam(FMultiplayerOnJoinSessionComplete, EOnJoinSessionCompleteResult::Type Result);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FMultiplayerOnDestroySessionComplete, bool, bWasSuccessful);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FMultiplayerOnStartSessionComplete, bool, bWasSuccessful);

//
// New delegates for MainMenu2 (privacy / join-code / Steam-invite / browse-filter flow).
// SessionsFound carries a plain USTRUCT array the same way FindSessionsComplete carries
// FOnlineSessionSearchResult, so it stays a non-dynamic multicast delegate (AddUObject /
// RemoveAll), not a dynamic one.
//
DECLARE_MULTICAST_DELEGATE_TwoParams(FMultiplayerOnSessionsFound, const TArray<FAuraSessionInfo>& SessionInfos, bool bWasSuccessful);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FMultiplayerOnInviteAccepted, bool, bWasSuccessful);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FMultiplayerOnSessionError, const FString&, Message);

/**
 * 
 */
UCLASS()
class AURA_API UMultiplayerSessionsSubsystem : public UGameInstanceSubsystem
{
	GENERATED_BODY()
	public:
	UMultiplayerSessionsSubsystem();
	
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void Deinitialize() override;
	
	

	//
	// To handle session functionality. The Menu class will call these
	//
	void CreateSession(int32 NumPublicConnections, FString MatchType);
	void FindSessions(int32 MaxSearchResults);
	void JoinSession(const FOnlineSessionSearchResult& SessionResult);
	void DestroySession();
	void StartSession();
	
	void JoinSessionAtInitialisation();
	
	//gpt 
	void LeaveSession();

	//
	// MainMenu2 API - additive. Every signature above is untouched, so UMainMenu and
	// AMyPlayerController2::JoinSessionButtonWrapper keep working exactly as they do today.
	//
	void CreateSessionWithSettings(const FAuraHostSettings& HostSettings);
	void FindSessionsFiltered(const FAuraSessionFilter& Filter);
	void JoinSessionByCode(const FString& JoinCode);
	void JoinCachedSession(int32 ResultIndex);
	bool ShowSteamInviteUI();
	FString GetCurrentJoinCode() const;
	bool IsSearchInProgress() const;
	static FString GenerateJoinCode();

	//
	// Our own custom delegates for the Menu class to bind callbacks to
	//
	FMultiplayerOnCreateSessionComplete MultiplayerOnCreateSessionComplete;
	FMultiplayerOnFindSessionsComplete MultiplayerOnFindSessionsComplete;
	FMultiplayerOnJoinSessionComplete MultiplayerOnJoinSessionComplete;
	FMultiplayerOnDestroySessionComplete MultiplayerOnDestroySessionComplete;
	FMultiplayerOnStartSessionComplete MultiplayerOnStartSessionComplete;

	FMultiplayerOnSessionsFound MultiplayerOnSessionsFound;
	FMultiplayerOnInviteAccepted MultiplayerOnInviteAccepted;
	FMultiplayerOnSessionError MultiplayerOnSessionError;
	
	//My
	void StartHeadlessLogic(UWorld* InWorld, const UWorld::InitializationValues IVS);
	void StartHeadlessLogic2();

protected:

	//
	// Internal callbacks for the delegates we'll add to the Online Session Interface delegate list.
	// Thise don't need to be called outside this class.
	//
	void OnCreateSessionComplete(FName SessionName, bool bWasSuccessful);
	void OnFindSessionsComplete(bool bWasSuccessful);
	void OnJoinSessionComplete(FName SessionName, EOnJoinSessionCompleteResult::Type Result);
	void OnDestroySessionComplete(FName SessionName, bool bWasSuccessful);
	void OnStartSessionComplete(FName SessionName, bool bWasSuccessful);
	
	//my
	void OnFindSessionsCompleteForHeadless(const TArray<FOnlineSessionSearchResult>& SessionResults, bool bWasSuccessful);
	
	void OnJoinSessionCompleteForHeadlesss(EOnJoinSessionCompleteResult::Type Result);

	// Fired by the Online Session Interface when a Steam overlay invite - or a cold-start
	// invite, re-ticked once this delegate is bound - is accepted.
	void OnSessionUserInviteAccepted(const bool bWasSuccessful, const int32 ControllerId, FUniqueNetIdPtr UserId, const FOnlineSessionSearchResult& InviteResult);
	

private:
	IOnlineSessionPtr SessionInterface;
	TSharedPtr<FOnlineSessionSettings> LastSessionSettings;
	TSharedPtr<FOnlineSessionSearch> LastSessionSearch;

	//
	// To add to the Online Session Interface delegate list.
	// We'll bind our MultiplayerSessionsSubsystem internal callbacks to these.
	//
	FOnCreateSessionCompleteDelegate CreateSessionCompleteDelegate;
	FDelegateHandle CreateSessionCompleteDelegateHandle;
	FOnFindSessionsCompleteDelegate FindSessionsCompleteDelegate;
	FDelegateHandle FindSessionsCompleteDelegateHandle;
	FOnJoinSessionCompleteDelegate JoinSessionCompleteDelegate;
	FDelegateHandle JoinSessionCompleteDelegateHandle;
	FOnDestroySessionCompleteDelegate DestroySessionCompleteDelegate;
	FDelegateHandle DestroySessionCompleteDelegateHandle;
	FOnStartSessionCompleteDelegate StartSessionCompleteDelegate;
	FDelegateHandle StartSessionCompleteDelegateHandle;
	FDelegateHandle InviteAcceptedDelegateHandle;

	bool bCreateSessionOnDestroy{ false };
	int32 LastNumPublicConnections;
	FString LastMatchType;

	//
	// MainMenu2 state
	//
	bool bRecreateWithHostSettings{ false };
	FAuraHostSettings PendingHostSettings;

	bool bSearchInProgress{ false };
	bool bPendingCodeJoin{ false };
	FAuraSessionFilter CurrentSessionFilter;
	TArray<FOnlineSessionSearchResult> CachedResults;
	FString CurrentJoinCode;

	static int32 GetPingCapForDistance(EAuraSearchDistance Distance);
	
};
