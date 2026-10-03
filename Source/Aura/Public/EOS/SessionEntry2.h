// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "UI/UserWidgets/MyUserWidget.h"
#include "EOS/MultiplayerSessionTypes.h"
#include "SessionEntry2.generated.h"

class UButton;
class UTextBlock;
class UMainMenu2;

/**
 * One row in UMainMenu2's browse list. Purely a display + "join me" widget -
 * UMainMenu2 owns the actual join call and the cached search results.
 */
UCLASS()
class AURA_API USessionEntry2 : public UMyUserWidget
{
	GENERATED_BODY()

public:
	void Setup(UMainMenu2* InOwningMenu, const FAuraSessionInfo& Info);

protected:
	virtual bool Initialize() override;

private:
	UFUNCTION()
	void JoinEntryButtonClicked();

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
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* JoinEntryButton;

	UPROPERTY()
	UMainMenu2* OwningMenu;

	int32 ResultIndex{ INDEX_NONE };
};
