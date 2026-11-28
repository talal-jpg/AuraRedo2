// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "UObject/Interface.h"
#include "MyLobbyPanel.generated.h"

/**
 * The lobby widget's panel as AMyPlayerController2 and the console see it (Docs/Airship/round2/SPEC_B_LOBBY.md 6.1,
 * 6.3). UMyLobbyWidget implements it and registers itself with AMyPlayerController2::SetLobbyPanel in NativeConstruct
 * (and clears it in NativeDestruct). With nothing registered (no WBP, SPEC_B_LOBBY 6.6) Esc opens the pause menu.
 */
UINTERFACE(MinimalAPI, meta = (CannotImplementInterfaceInBlueprint))
class UMyLobbyPanel : public UInterface
{
	GENERATED_BODY()
};

class AURA_API IMyLobbyPanel
{
	GENERATED_BODY()

public:

	/** The full panel, UI-only input focused on it, cursor on (as UPauseMenu3::OpenMenu). */
	virtual void OpenPanel() = 0;

	/** Back to the compact strip, game-only input, cursor as it was (as UPauseMenu3::CloseMenu). */
	virtual void ClosePanel() = 0;

	virtual bool IsPanelOpen() const = 0;
};
