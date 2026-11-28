// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/HUD.h"
#include "MyHUD.generated.h"

class UMyHexMinimapWidget;
class UMyLobbyWidget;
class UMyMatchHUDWidget;
class UMyOverlayWidgetController;
class UMyUserWidget;
/**
 * 
 */
UCLASS()
class AURA_API AMyHUD : public AHUD
{
	GENERATED_BODY()
	
public:
	AMyHUD();

	void InitOverlay();

	/** The lobby widget (SPEC_B_LOBBY 6.1), or null (no LobbyWidgetClass, not a local controller). */
	UMyLobbyWidget* GetLobbyWidget() const { return LobbyWidget; }

protected:
	/** Adds the team match HUD: it must show while a versus match waits for players, when there is no pawn yet. */
	virtual void BeginPlay() override;

	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

private:
	/** Team match HUD (Docs/Airship/round2/SPEC_B.md B8): over the whole viewport, draws nothing while no match runs. None = off. */
	UPROPERTY(EditAnywhere, Category = "Match")
	TSubclassOf<UMyMatchHUDWidget> MatchWidgetClass;

	UPROPERTY()
	TObjectPtr<UMyMatchHUDWidget> MatchWidget;

	void AddMatchWidget();

	/**
	 * The in-level lobby's panel and strip (Docs/Airship/round2/SPEC_B_LOBBY.md 6.1): WBP_Lobby3 (as_77), set on BP_MyHUD by
	 * as_78. Added for local controllers on every map; it shows only while AMyGameState::IsInLobby. None = no lobby widget:
	 * Esc opens the pause menu (START MATCH there) and the match HUD draws a one-line lobby strip (6.6).
	 */
	UPROPERTY(EditAnywhere, Category = "Lobby")
	TSubclassOf<UMyLobbyWidget> LobbyWidgetClass;

	UPROPERTY()
	TObjectPtr<UMyLobbyWidget> LobbyWidget;

	void AddLobbyWidget();

	UPROPERTY()
	TObjectPtr<UMyUserWidget> OverlayWidget;

	UPROPERTY(EditAnywhere)
	TSubclassOf<UMyUserWidget> OverlayUserWidgetClass;
	
	
	UPROPERTY(EditAnywhere)
	TSubclassOf<UMyOverlayWidgetController> OverlayWidgetControllerClass;

	/** Hex platform minimap, added to the top-right corner with the overlay. None = no minimap. */
	UPROPERTY(EditAnywhere, Category = "Minimap")
	TSubclassOf<UMyHexMinimapWidget> MinimapWidgetClass;

	/** Gap (slate units) between the minimap and the top-right corner of the screen. */
	UPROPERTY(EditAnywhere, Category = "Minimap")
	FVector2D MinimapCornerOffset = FVector2D(24.f, 24.f);

	UPROPERTY()
	TObjectPtr<UMyHexMinimapWidget> MinimapWidget;
	
	
};
