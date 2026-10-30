// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "UI/UserWidgets/MyUserWidget.h"
#include "EOS/MultiplayerSessionTypes.h"
#include "SessionEntry3.generated.h"

class UButton;
class UTextBlock;
class UWidget;
class UMainMenu3;

/**
 * One row in UMainMenu3's Browse Sessions list: lobby name, host, players, ping, difficulty,
 * rules and a Join button. Like USessionEntry2 it only displays; UMainMenu3 owns the join.
 */
UCLASS()
class AURA_API USessionEntry3 : public UMyUserWidget
{
	GENERATED_BODY()

public:
	void Setup(UMainMenu3* InOwningMenu, const FAuraSessionInfo& Info);

	UFUNCTION(BlueprintPure, Category = "Aura|Menu")
	FAuraSessionInfo GetSessionInfo() const { return SessionInfo; }

protected:
	virtual bool Initialize() override;

	// Blueprint hook to restyle the row (ping colour, full lobby, ...).
	UFUNCTION(BlueprintImplementableEvent, Category = "Aura|Menu")
	void OnSessionInfoSet(const FAuraSessionInfo& Info);

	// Ping at or under this is "good" (green), at or under Ok is yellow, above is red.
	UPROPERTY(EditAnywhere, Category = "Aura|Menu")
	int32 GoodPingMs = 60;
	UPROPERTY(EditAnywhere, Category = "Aura|Menu")
	int32 OkPingMs = 120;

private:
	UFUNCTION()
	void JoinEntryButtonClicked();

	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* LobbyNameText;
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* HostNameText;
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* PlayersText;
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* PingText;
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* DifficultyText;
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* RulesText;
	// Shown for a full lobby (only listed when "Show full lobbies" is on)
	UPROPERTY(meta = (BindWidgetOptional))
	UWidget* FullBadge;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* JoinEntryButton;

	UPROPERTY()
	UMainMenu3* OwningMenu;

	FAuraSessionInfo SessionInfo;
};
