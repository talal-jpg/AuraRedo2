// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include <Subsystems/GameInstanceSubsystem.h>

#include "Engine/World.h"
#include "Engine/EngineBaseTypes.h"
#include "Interfaces/OnlineSessionInterface.h"
#include "OnlineSessionSettings.h"
#include "EOS/MultiplayerSessionTypes.h"
#include "MultiplayerSessionsSubsystem.generated.h"

class UNetDriver;
class APlayerController;
struct FUniqueNetIdRepl;

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

//
// MainMenu3 delegates (lobby settings changes from the in-game menu, cancelled searches).
//
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FMultiplayerOnUpdateSessionComplete, bool, bWasSuccessful);
DECLARE_DYNAMIC_MULTICAST_DELEGATE(FMultiplayerOnFindSessionsCancelled);

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
	// Codes are this many characters from an alphabet without I / O / 0 / 1
	static constexpr int32 JoinCodeLength = 6;
	static bool IsJoinCodeCharacter(TCHAR Character);

	//
	// MainMenu3 API - additive too. Two fixes reach the calls above: JoinSession() now
	// clears a leftover session before joining (instead of failing with AlreadyInSession),
	// and an accepted invite travels by itself, so it also works in game with no menu open.
	// A dropped connection / failed travel now destroys the stale session as well.
	//

	// Browses with Filter (its JoinCode is ignored) and joins the open, listed lobby with
	// the lowest ping. MultiplayerOnSessionError fires when there is none.
	void QuickJoin(const FAuraSessionFilter& Filter);
	// Stops a browse / code lookup / quick join. Its results are dropped, and
	// MultiplayerOnFindSessionsCancelled fires instead of MultiplayerOnSessionsFound.
	void CancelFindSessions();
	// Host only. Changes privacy / max players / lobby name / difficulty / rules / join in
	// progress of the running session. The join code is kept.
	void UpdateHostSettings(const FAuraHostSettings& HostSettings);
	// The session this game instance is in (hosting or joined). False when there is none.
	bool GetCurrentSessionInfo(FAuraSessionInfo& OutInfo) const;
	// Settings of the running session as an FAuraHostSettings, to edit and pass to UpdateHostSettings().
	bool GetCurrentHostSettings(FAuraHostSettings& OutSettings) const;
	bool IsInSession() const;
	bool IsHostingSession() const;
	// True when PlayerId owns (hosts) the session we're in. Clients use it to tag the host in lists.
	bool IsSessionOwner(const FUniqueNetIdRepl& PlayerId) const;
	// ClientTravel to the session joined last. MainMenu3 calls this from its join callback.
	void TravelToJoinedSession();
	// Destroys the session (if any), then opens LevelPath, e.g. the main menu map. As host this
	// closes the listen server and every client returns to their main menu.
	void LeaveSessionAndOpenLevel(const FString& LevelPath);
	bool ShowFriendsUI();
	// Why the last session ended (lost connection, kicked, host left...). Empty when nothing
	// happened since the last call; the main menu shows it once.
	FString ConsumePendingMenuMessage();

	// Looks a code up without joining: MultiplayerOnSessionsFound gets the matching lobby (or
	// nothing), so the menu can ask "Join <host>'s lobby?" first, then call JoinCachedSession().
	void LookupSessionByCode(const FString& JoinCode);

	// Online service state for the title screen: signed-in name, and whether sessions work at all.
	bool IsOnlineServiceAvailable() const;
	FString GetOnlineServiceName() const;
	FString GetLocalPlayerNickname() const;

	// Opens the platform profile (Steam overlay) of another player.
	bool ShowPlayerProfile(const FUniqueNetIdRepl& PlayerId);

	//
	// Host moderation. Bans last until this game instance hosts a new lobby.
	//
	// Server only. Removes Player with Reason (they get it as their menu message). bBan also
	// refuses them in CheckJoinAllowed() for the rest of the lobby.
	bool KickPlayer(APlayerController* Player, const FText& Reason, bool bBan);
	bool IsPlayerBanned(const FUniqueNetIdRepl& PlayerId) const;
	void ClearBans();
	// Called from AGameModeBase::PreLogin. Empty = let them in, otherwise the error the joining
	// player sees (banned, lobby full).
	FString CheckJoinAllowed(const FUniqueNetIdRepl& PlayerId, int32 NumPlayersInGame) const;
	// Client side, from APlayerController::ClientWasKicked. Keeps Reason as the menu message
	// (the disconnect that follows doesn't overwrite it) and drops the stale session.
	void NotifyKicked(const FText& Reason);

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

	FMultiplayerOnUpdateSessionComplete MultiplayerOnUpdateSessionComplete;
	FMultiplayerOnFindSessionsCancelled MultiplayerOnFindSessionsCancelled;
	
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

	void OnUpdateSessionComplete(FName SessionName, bool bWasSuccessful);
	void OnCancelFindSessionsComplete(bool bWasSuccessful);

	// GEngine events. A dropped connection or failed travel leaves the OSS session behind,
	// which would make the next host/join fail, so both destroy it.
	void HandleNetworkFailure(UWorld* World, UNetDriver* NetDriver, ENetworkFailure::Type FailureType, const FString& ErrorString);
	void HandleTravelFailure(UWorld* World, ETravelFailure::Type FailureType, const FString& ErrorString);
	

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
	FOnUpdateSessionCompleteDelegate UpdateSessionCompleteDelegate;
	FDelegateHandle UpdateSessionCompleteDelegateHandle;
	FOnCancelFindSessionsCompleteDelegate CancelFindSessionsCompleteDelegate;
	FDelegateHandle CancelFindSessionsCompleteDelegateHandle;
	FDelegateHandle NetworkFailureDelegateHandle;
	FDelegateHandle TravelFailureDelegateHandle;

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

	//
	// MainMenu3 state
	//
	bool bPendingQuickJoin{ false };

	// An accepted invite travels by itself once joined, even with no menu open.
	bool bTravelAfterJoin{ false };

	// Guards the cancel callback against firing twice (some OSSs trigger it and return false).
	bool bCancelFindPending{ false };

	// JoinSession() found a leftover session: destroy it, then join this.
	bool bJoinOnDestroy{ false };
	FOnlineSessionSearchResult PendingJoinResult;

	// LeaveSessionAndOpenLevel(): open this once the session is gone.
	bool bOpenLevelOnDestroy{ false };
	FString PendingLevelPath;

	FString PendingMenuMessage;
	// Set by NotifyKicked so the disconnect right after it keeps the kick reason
	bool bMenuMessageLocked{ false };

	// FUniqueNetIdRepl::ToString() of every player banned from the lobby we host
	TSet<FString> BannedPlayerIds;

	// Writes everything FAuraHostSettings controls into Settings. Shared by
	// CreateSessionWithSettings() and UpdateHostSettings().
	static void ApplyHostSettings(FOnlineSessionSettings& Settings, const FAuraHostSettings& HostSettings, const FString& JoinCode);
	static FAuraSessionInfo MakeSessionInfo(const FOnlineSession& Session, int32 PingInMs, int32 ResultIndex);
	void FindSessionsFilteredInternal(const FAuraSessionFilter& Filter, bool bQuickJoin, bool bAutoJoinCode);
	void DestroySessionAfterFailure();
	void OpenPendingLevel();
	
};
