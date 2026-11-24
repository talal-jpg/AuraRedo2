// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Airship/AirshipTypes.h"
#include "Blueprint/UserWidget.h"
#include "Styling/SlateBrush.h"
#include "AirshipHUDWidget.generated.h"

class AAirshipPawn;

/**
 * The ship HUD (Docs/Airship/CPP_NOTES.md): a small comic-ink panel in the bottom-left corner while a local player flies
 * an AAirshipPawn. Hull bar, boost fuel bar, speed (m/s), altitude above the ground (m), and the reload of the port /
 * starboard broadside (the side the cannons face is drawn inverted). No assets: everything is drawn in NativePaint
 * with Slate boxes, lines and the engine font. The ship adds it to the viewport and removes it (AAirshipPawn::UpdateShipHUD).
 * A Blueprint child can change the colours / size (AAirshipPawn::ShipHUDClass).
 *
 * Control schemes (read every frame): Galleon adds the engine telegraph, a speed rule and a helm row (+GalleonExtraHeight),
 * Sky Racer a DRIFT / TURBO row (+SkyRowHeight); the ship re-applies the viewport slot when the scheme changes. Overlay
 * mode (a second instance over the whole viewport): Point & Fly's crosshair, nose marker, heading strip and gun state.
 *
 * Round 2 (every scheme): the pilot's panel has a PILOT row (the pilot character's own health, under the hull bar) and a
 * GUNS row (the two turrets' heat with their health underneath, an X when wrecked, and a dot per gunner station, filled
 * when manned); PORT / STBD read MANNED when both cannons of that side have gunners. Gunner mode (the gunner's own
 * machine, over the whole viewport, UAirshipPilotComponent): a crosshair, the mark where the gun points, and a panel
 * bottom-left with the station, its reload (cannons, OUT OF ARC) or heat and health (turrets), the hull and F LEAVE.
 */
UCLASS(Blueprintable)
class AURA_API UAirshipHUDWidget : public UUserWidget
{
	GENERATED_BODY()

public:

	UAirshipHUDWidget(const FObjectInitializer& ObjectInitializer);

	/** The ship to show (null: draws nothing). */
	void SetAirship(AAirshipPawn* InAirship);

	/** Size of the panel (slate units) the ship gives the viewport slot: PanelSize plus the scheme's rows. */
	FVector2D GetPanelSize() const;

	/** Reads the ship's control scheme now (the ship calls it before it re-applies the slot after a switch). */
	void RefreshLayoutScheme();

	/** Overlay mode (set before the widget is added): draws only Point & Fly's marks, over the whole viewport. */
	void SetOverlayMode(bool bInOverlayMode) { bOverlayMode = bInOverlayMode; }
	bool IsOverlayMode() const { return bOverlayMode; }

	/** Gunner mode (a gunner's own machine; the widget covers the whole viewport): the ship and station. Null / -1 = off. */
	void SetGunnerStation(AAirshipPawn* InAirship, int32 InStation);
	bool IsGunnerMode() const { return GunnerStation >= 0; }

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship HUD")
	FVector2D PanelSize = FVector2D(292.0, 136.0);

	/** Extra panel height (slate units): Galleon's telegraph, speed rule and helm rows, Sky Racer's TURBO row. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship HUD", meta = (ClampMin = "0.0"))
	float GalleonExtraHeight = 78.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship HUD", meta = (ClampMin = "0.0"))
	float SkyRowHeight = 26.f;

	/** Extra panel height (slate units) of the PILOT row (under the hull bar) and the GUNS row (at the bottom), every scheme. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship HUD", meta = (ClampMin = "0.0"))
	float PilotRowHeight = 24.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship HUD", meta = (ClampMin = "0.0"))
	float GunsRowHeight = 24.f;

	/** Gunner mode: the panel's size (bottom-left, slate units). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship HUD")
	FVector2D GunnerPanelSize = FVector2D(272.0, 124.0);

	/** Paper (panel), ink (outlines, text, drop shadow), hull bar, boost bar, reloading mark. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship HUD")
	FLinearColor PaperColor;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship HUD")
	FLinearColor InkColor;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship HUD")
	FLinearColor HullColor;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship HUD")
	FLinearColor BoostColor;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship HUD")
	FLinearColor ReloadColor;

	/** The pilot's own health bar and the turrets' health underlines. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship HUD")
	FLinearColor PilotColor;

	/** Ground distance trace: interval (s) and length (cm). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship HUD", meta = (ClampMin = "0.0"))
	float AltitudeTraceInterval = 0.1f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship HUD", meta = (ClampMin = "100.0"))
	float AltitudeTraceLength = 100000.f;

protected:

	virtual void NativeConstruct() override;

	virtual void NativeTick(const FGeometry& MyGeometry, float InDeltaTime) override;

	virtual int32 NativePaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect, FSlateWindowElementList& OutDrawElements,
		int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const override;

private:

	void RefreshBrushes();

	/** Reads the ship's values for the next paint (bForceAltitude: trace the ground now). */
	void RefreshValues(float DeltaSeconds, bool bForceAltitude);

	/** Overlay mode: the projected nose marker, heading strip and gun state (NativeTick, cached for the paint). */
	void RefreshOverlayValues(float DeltaSeconds);

	/** Overlay mode's paint (Point & Fly only). */
	int32 PaintPointFlyOverlay(const FGeometry& AllottedGeometry, FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle) const;

	/** The tier colour (Sky Racer): ink grey, BoostColor, ReloadColor, HullColor. */
	FLinearColor GetTierColor(int32 Tier) const;

	/** The pilot's panel: the turrets, the stations, the pilot's own health (NativeTick). */
	void RefreshCrewValues(const AAirshipPawn* Ship);

	/** Gunner mode's values: the gun's mark, reload or heat, health (NativeTick, cached for the paint). */
	void RefreshGunnerValues();

	/** Gunner mode's paint: crosshair, gun mark, panel. */
	int32 PaintGunner(const FGeometry& AllottedGeometry, FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle) const;

	TWeakObjectPtr<AAirshipPawn> Airship;

	/** The ship's scheme (read every frame; the initial value is the pawn's default scheme) and overlay mode. */
	EAirshipControlScheme LayoutScheme = EAirshipControlScheme::PointFly;
	bool bOverlayMode = false;

	// Values of this frame (NativeTick)
	float HealthAlpha = 1.f;
	float Health = 0.f;
	float FuelAlpha = 1.f;
	float SpeedMS = 0.f;
	float AltitudeM = -1.f;
	float ReloadAlpha[2] = { 1.f, 1.f };
	float ReloadSeconds[2] = { 0.f, 0.f };
	bool bBoosting = false;
	EAirshipSide AimSide = EAirshipSide::Port;
	float AltitudeTimer = 0.f;

	// Galleon: the order, its ring (the new tag blinks), the speed rule (m/s), the helm, stations, the facing side's arc
	int32 GalleonNotch = 0;
	float GalleonRingTime = 0.f;
	float ForwardSpeedMS = 0.f;
	float OrderAsternMS = 12.f;
	float OrderSlowMS = 14.f;
	float OrderHalfMS = 28.f;
	float OrderFullMS = 48.f;
	float HelmSteer = 0.f;
	float TurnRateDegS = 0.f;
	bool bHelmDrifting = false;
	bool bGalleonStations = false;
	bool bFacingInArc = false;

	// Sky Racer: drift charge / tier, turbo burn / tier / chain, the outline flash on a release
	bool bDriftActive = false;
	float DriftCharge = 0.f;
	int32 DriftTier = 0;
	float TurboAlpha = 0.f;
	int32 TurboTier = 0;
	int32 TurboChain = 0;
	bool bChainLive = false;
	float FlashTime = 0.f;
	float SinceRelease = 1000.f;
	uint8 LastTurboEventCount = 0;
	float SkyTier1 = 0.25f;
	float SkyTier2 = 0.55f;

	// Point & Fly overlay (viewport-relative slate units)
	bool bPFActive = false;
	bool bPFFreeLook = false;
	bool bPFLock = false;
	int32 PFSwingDir = 0;
	bool bNoseOnScreen = false;
	FVector2D NosePosition = FVector2D::ZeroVector;
	float NoseGapDeg = 0.f;
	float NoseFlashTime = 0.f;
	/**
	 * The broadside heading strip (polish): +-180 deg around the bow (the centre), so the aim 55-150 deg off the bow is on
	 * it; the heading target and the aim (camera yaw) relative to the bow (deg), and the guns' yaw limit (deg).
	 */
	float StripTargetDeg = 0.f;
	float StripAimDeg = 0.f;
	float StripArcDeg = 20.f;

	/** Parked free look (the gap line hides: no turn is coming until a drive / turn key). */
	bool bPFParked = false;

	// The pilot's panel, round 2: turrets (L, R), manned stations, the sides fully manned, the pilot's own health
	bool bTurretShown[2] = { false, false };
	bool bTurretWrecked[2] = { false, false };
	bool bTurretOverheated[2] = { false, false };
	float TurretHeat[2] = { 0.f, 0.f };
	float TurretHealthAlpha[2] = { 1.f, 1.f };
	int32 MannedMask = 0;
	bool bSideManned[2] = { false, false };
	float PilotHealth = -1.f;
	float PilotHealthAlpha = 0.f;

	// Gunner mode
	int32 GunnerStation = -1;
	bool bGunMarkOnScreen = false;
	FVector2D GunMarkPosition = FVector2D::ZeroVector;
	float GunReloadAlpha = 1.f;
	float GunReloadSeconds = 0.f;
	bool bGunInArc = true;
	bool bGunReady = true;

	/** Seconds since the boarding hint started (-1: not yet decided; it shows once per local player and session). */
	float HintAge = -1.f;

	/** The boarding hint fades out from this age (s): 8 s after boarding, or when Aim is first held (whichever is later, at most 45 s). */
	float HintEndAge = 8.f;

	/** The pilot has held Aim (RMB / LB) this session: the look hints retire. */
	bool bLookLearned = false;

	/** Steering mode with the camera far off the nose (s), and the contextual "hold RMB to look" hint's alpha. */
	float OffNoseTime = 0.f;
	float LookHintAlpha = 0.f;

	// Rounded-box brushes (made from the colours in NativeConstruct; NativePaint only reads them)
	FSlateBrush PanelBrush;
	FSlateBrush ShadowBrush;
	FSlateBrush TrackBrush;
	FSlateBrush FillBrush;
	FSlateBrush TagBrush;
};
