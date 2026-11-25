// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "Match/MyMatchTypes.h"
#include "Styling/SlateBrush.h"
#include "MyMatchHUDWidget.generated.h"

class AAirshipPawn;
class AMyGameState;
class APawn;
enum class EAirshipUseRefusal : uint8;

/**
 * The team match HUD (Docs/Airship/round2/SPEC_B.md B8), every player, over the whole viewport (AMyHUD adds it at
 * BeginPlay: it must show while a versus match waits with no pawn). Drawn in NativePaint with Slate boxes, lines and the
 * engine font, the comic ink style of UAirshipHUDWidget; no assets, takes no input. Draws nothing while the phase is
 * None (match off). Reads only replicated state: AMyGameState (phase, rules, teams, events), the ships' lane component
 * and spawn protection, the player states' teams.
 *
 *  - Match bar, top centre: team names, lives as boxes (solo practice: SHIPS LOST n), both ships' hull bars, the phase
 *    or the match clock, the own ship's status line; the objective line for 6 s at the start.
 *  - Ship markers: a diamond 15 m above each living team ship, team colour, distance, hull bar, YOU, a shield ring while
 *    spawn-protected, AIM + GRAPPLE in hook range; the own one sticks to the screen edge, flashes on an attack.
 *  - Toasts, centre, 3 s, at most 3: ship destroyed / back / under attack / returning, forfeit warnings, 1 minute left,
 *    "that ship isn't yours" (UAirshipPilotComponent::OnLocalUseRefused).
 *  - Name tags over other players in team colour (teammates always, enemies within 100 m or in sight), TEAMMATE under
 *    the crosshair on a teammate.
 *  - End panel: VICTORY / DEFEAT / DRAW / PRACTICE OVER, why, ships left, the restart countdown.
 */
UCLASS(Blueprintable)
class AURA_API UMyMatchHUDWidget : public UUserWidget
{
	GENERATED_BODY()

public:

	UMyMatchHUDWidget(const FObjectInitializer& ObjectInitializer);

	/** Paper (panels), ink (outlines, text, shadow), the warning colour (under attack, out of ships). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Match HUD")
	FLinearColor PaperColor;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Match HUD")
	FLinearColor InkColor;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Match HUD")
	FLinearColor WarningColor;

	/** Match bar size (slate units) and its gap from the top of the screen. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Match HUD")
	FVector2D BarSize = FVector2D(620.0, 76.0);

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Match HUD")
	float BarTop = 16.f;

	/** Ship marker height above the ship's origin (cm). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Match HUD")
	float MarkerHeight = 1500.f;

	/** The enemy ship's marker shows on screen only, or off screen within this distance (cm). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Match HUD", meta = (ClampMin = "0.0"))
	float EnemyMarkerRange = 60000.f;

	/** AIM + GRAPPLE under the own ship's marker within this distance (cm): GA_GrappleSwing2's MaxShipHookDistance. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Match HUD", meta = (ClampMin = "0.0"))
	float ShipHookDistance = 12000.f;

	/** Name tags: height above the character's origin (cm); enemies show within EnemyTagRange (cm) or in sight. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Match HUD")
	float NameTagHeight = 220.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Match HUD", meta = (ClampMin = "0.0"))
	float EnemyTagRange = 10000.f;

	/** Seconds between the line-of-sight traces to each enemy. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Match HUD", meta = (ClampMin = "0.0"))
	float EnemyTagTraceInterval = 0.25f;

	/** TEAMMATE under the crosshair: the camera trace's length (cm, Pawn channel). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Match HUD", meta = (ClampMin = "0.0"))
	float CrosshairTraceDistance = 20000.f;

	/** Toasts: seconds each, at most this many at once. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Match HUD", meta = (ClampMin = "0.1"))
	float ToastSeconds = 3.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Match HUD", meta = (ClampMin = "1"))
	int32 MaxToasts = 3;

	/** The objective line's seconds at a start, FIGHT's, the own marker's flash after an attack. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Match HUD", meta = (ClampMin = "0.0"))
	float ObjectiveSeconds = 6.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Match HUD", meta = (ClampMin = "0.0"))
	float FightSeconds = 2.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Match HUD", meta = (ClampMin = "0.0"))
	float AttackFlashSeconds = 2.f;

protected:

	virtual void NativeConstruct() override;

	virtual void NativeDestruct() override;

	virtual void NativeTick(const FGeometry& MyGeometry, float InDeltaTime) override;

	virtual int32 NativePaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect, FSlateWindowElementList& OutDrawElements,
		int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const override;

private:

	struct FShipMarker
	{
		uint8 TeamId = MyMatch::NoTeam;
		bool bOwn = false;
		bool bOnScreen = false;

		/** Widget-local position of the diamond; off screen: on the edge, Direction pointing out. */
		FVector2D Position = FVector2D::ZeroVector;
		FVector2D Direction = FVector2D::ZeroVector;
		float DistanceM = 0.f;
		float HealthAlpha = 0.f;
		bool bProtected = false;
		bool bGrappleHint = false;
		bool bFlashOn = true;
	};

	struct FNameTag
	{
		FVector2D Position = FVector2D::ZeroVector;
		FString Name;
		FLinearColor Color = FLinearColor::White;
	};

	struct FToast
	{
		FString Text;
		FLinearColor Color = FLinearColor::White;
		float TimeLeft = 0.f;
	};

	void RefreshBrushes();

	/** Finds the game state (it may replicate after the widget is made) and binds its match events. */
	void BindGameState();
	void UnbindGameState();

	void HandleMatchEvent(EMyMatchEvent Event, uint8 TeamId, int32 Value);
	void HandleUseRefused(const APlayerController* Player, EAirshipUseRefusal Reason);
	void AddToast(const FString& Text, const FLinearColor& Color);

	/** This frame's texts, markers and tags for NativePaint (NativeTick). */
	void RefreshValues(const FGeometry& MyGeometry, float DeltaSeconds);
	void RefreshMarkers(const FGeometry& MyGeometry, const APlayerController* PC, const APawn* LocalPawn);
	void RefreshNameTags(const APlayerController* PC, const APawn* LocalPawn, float DeltaSeconds);
	void RefreshCrosshair(const APlayerController* PC, const APawn* LocalPawn);

	FString GetShipStatusText() const;
	FString GetEndReasonText() const;

	/** The team the local player plays for (his player state), 255 for none. */
	uint8 GetLocalTeam() const;

	bool IsSoloPractice(uint8 TeamId) const;

	TWeakObjectPtr<AMyGameState> GameState;
	FDelegateHandle MatchEventHandle;
	FDelegateHandle UseRefusedHandle;

	// This frame's values (NativeTick)
	EMyMatchPhase Phase = EMyMatchPhase::None;
	bool bVersus = false;
	uint8 LocalTeam = MyMatch::NoTeam;
	FMyMatchRules Rules;
	FMyTeamState Teams[MyMatch::NumTeams];
	bool bShipAlive[MyMatch::NumTeams] = {};
	FString CentreText;
	FString CentreSubText;
	FString StatusText;
	FString ObjectiveText;
	FString EndTitle;
	FString EndReason;
	FString EndShipsLine;
	FString EndRestartLine;
	FLinearColor CentreColor = FLinearColor::White;
	bool bTeammateUnderCrosshair = false;
	TArray<FShipMarker> Markers;
	TArray<FNameTag> NameTags;

	TArray<FToast> Toasts;
	float ObjectiveTimeLeft = 0.f;
	float FightTimeLeft = 0.f;
	float AttackFlashTimeLeft[MyMatch::NumTeams] = {};
	float HUDTime = 0.f;

	/** Enemy pawns in sight (traced every EnemyTagTraceInterval). */
	TMap<TWeakObjectPtr<const APawn>, bool> EnemyInSight;
	float EnemyTraceTimer = 0.f;

	FSlateBrush PanelBrush;
	FSlateBrush ShadowBrush;
	FSlateBrush TrackBrush;
	FSlateBrush FillBrush;
	FSlateBrush TagBrush;
};
