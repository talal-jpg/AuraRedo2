// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "UI/UserWidgets/MyUserWidget.h"
#include "MyLobbyPlayerRow.generated.h"

class AMyPlayerState;
class UButton;
class UMyLobbyWidget;
class UTextBlock;
class UWidget;

/**
 * One player in a team list of the lobby panel (Docs/Airship/round2/SPEC_B_LOBBY.md 6.3). UMyLobbyWidget makes it from
 * PlayerRowClass (WBP_LobbyPlayerRow3, built by as_77) and calls Setup once, then Refresh on every lobby refresh: the row
 * is rebuilt only when the player list or a team changes, so a press and release on MOVE land on the same widget (6.4).
 * Every widget is optional.
 */
UCLASS()
class AURA_API UMyLobbyPlayerRow : public UMyUserWidget
{
	GENERATED_BODY()

public:

	/** bIsLocal: this machine's own player (LocalHighlight). bHostView: the host's panel (MoveButton). */
	void Setup(UMyLobbyWidget* InOwner, AMyPlayerState* InPlayer, bool bInIsLocal, bool bInHostView);

	/** Texts only (name, HOST / READY / NOT READY / WANTS ORANGE / LOADING, ping, MOVE): no rebuild. */
	void Refresh();

	AMyPlayerState* GetPlayer() const { return Player.Get(); }

protected:

	virtual bool Initialize() override;

	/** Blueprint hook to restyle the row (the local player's plate, the host's view). */
	UFUNCTION(BlueprintImplementableEvent, Category = "Lobby")
	void OnRowSetup(bool bIsLocalPlayer, bool bIsHostView);

	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* PlayerNameText;

	/** HOST / READY / NOT READY / WANTS ORANGE / LOADING. */
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* StatusText;

	/** APlayerState::GetPingInMilliseconds; empty for the host and a player still loading. */
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* PingText;

	/** Shown on this machine's own row only. */
	UPROPERTY(meta = (BindWidgetOptional))
	UWidget* LocalHighlight;

	/** Host view only: move this player to the other team (a swap when that team is full). */
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* MoveButton;

	/** MOVE's label: "TO ORANGE" / "SWAP TO ORANGE". Optional (not in the spec's list). */
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* MoveText;

private:

	UFUNCTION()
	void MoveButtonClicked();

	TWeakObjectPtr<UMyLobbyWidget> Owner;
	TWeakObjectPtr<AMyPlayerState> Player;
	bool bIsLocal = false;
	bool bHostView = false;
};
