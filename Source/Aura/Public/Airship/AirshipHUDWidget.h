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
 */
UCLASS(Blueprintable)
class AURA_API UAirshipHUDWidget : public UUserWidget
{
	GENERATED_BODY()

public:

	UAirshipHUDWidget(const FObjectInitializer& ObjectInitializer);

	/** The ship to show (null: draws nothing). */
	void SetAirship(AAirshipPawn* InAirship);

	/** Size of the panel (slate units) the ship gives the viewport slot. */
	FVector2D GetPanelSize() const { return PanelSize; }

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship HUD")
	FVector2D PanelSize = FVector2D(292.0, 136.0);

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

	TWeakObjectPtr<AAirshipPawn> Airship;

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

	// Rounded-box brushes (made from the colours in NativeConstruct; NativePaint only reads them)
	FSlateBrush PanelBrush;
	FSlateBrush ShadowBrush;
	FSlateBrush TrackBrush;
	FSlateBrush FillBrush;
	FSlateBrush TagBrush;
};
