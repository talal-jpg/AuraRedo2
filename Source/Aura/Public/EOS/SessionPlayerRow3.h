// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "UI/UserWidgets/MyUserWidget.h"
#include "SessionPlayerRow3.generated.h"

class APlayerState;
class UButton;
class UTextBlock;
class UWidget;
class UPauseMenu3;

/**
 * One player in UPauseMenu3's Current Session list: name, ping, host / you badges, and
 * Profile / Kick / Ban buttons. Kick and Ban only show for the host, never on their own row.
 */
UCLASS()
class AURA_API USessionPlayerRow3 : public UMyUserWidget
{
	GENERATED_BODY()

public:
	void Setup(UPauseMenu3* InOwningMenu, APlayerState* InPlayerState, bool bInIsHostPlayer, bool bInIsLocalPlayer, bool bInCanModerate);
	// Name and ping again, called every list refresh
	void Refresh();

	APlayerState* GetPlayerState() const { return PlayerState.Get(); }

protected:
	virtual bool Initialize() override;

	// Blueprint hook to restyle the row (host colour, your own row...).
	UFUNCTION(BlueprintImplementableEvent, Category = "Aura|Menu")
	void OnRowSetup(bool bIsHostPlayer, bool bIsLocalPlayer, bool bCanModerate);

private:
	UFUNCTION()
	void ProfileButtonClicked();
	UFUNCTION()
	void KickButtonClicked();
	UFUNCTION()
	void BanButtonClicked();

	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* PlayerNameText;
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* PingText;
	UPROPERTY(meta = (BindWidgetOptional))
	UWidget* HostBadge;
	UPROPERTY(meta = (BindWidgetOptional))
	UWidget* LocalPlayerBadge;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* ProfileButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* KickButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* BanButton;

	UPROPERTY()
	UPauseMenu3* OwningMenu;

	TWeakObjectPtr<APlayerState> PlayerState;
	bool bIsHostPlayer{ false };
};
