// Fill out your copyright notice in the Description page of Project Settings.


#include "Airship/AirshipHUDWidget.h"

#include "AbilitySystemComponent.h"
#include "AbilitySystemGlobals.h"
#include "AbilitySystem/MyAttributeSet.h"
#include "Airship/AirshipFlightComponent.h"
#include "Airship/AirshipPawn.h"
#include "Airship/AirshipTurret.h"
#include "Blueprint/WidgetLayoutLibrary.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/LocalPlayer.h"
#include "Fonts/FontMeasure.h"
#include "Framework/Application/SlateApplication.h"
#include "GameFramework/Character.h"
#include "GameFramework/PlayerController.h"
#include "Rendering/DrawElements.h"
#include "Rendering/SlateRenderer.h"
#include "Styling/CoreStyle.h"
#include "UObject/ObjectKey.h"

// Named, not anonymous: the unity build compiles this file together with others
namespace AirshipHUDPrivate
{
	void MakeRoundedBrush(FSlateBrush& Brush, const FLinearColor& Fill, float Radius, const FLinearColor& Outline, float OutlineWidth)
	{
		Brush = FSlateBrush();
		Brush.DrawAs = ESlateBrushDrawType::RoundedBox;
		Brush.TintColor = FSlateColor(Fill);
		Brush.OutlineSettings = FSlateBrushOutlineSettings(Radius, FSlateColor(Outline), OutlineWidth);
	}

	/** Width (slate units) of Text in Font, 0 without Slate. */
	float MeasureWidth(const FString& Text, const FSlateFontInfo& Font)
	{
		if (!FSlateApplication::IsInitialized())
		{
			return 0.f;
		}
		const TSharedRef<FSlateFontMeasure> Measure = FSlateApplication::Get().GetRenderer()->GetFontMeasureService();
		return static_cast<float>(FVector2f(Measure->Measure(Text, Font)).X);
	}

	/** Width (slate units) of Text in Font as it is drawn at the paint geometry's Scale (the viewport's DPI scale): the glyph
	 *  advances are rounded at the scaled size, so a width measured at scale 1 came out 7 % short at scale 1.125 and the
	 *  Point & Fly hints overflowed their plates (verify step 2026-11-23). The v1 panel keeps MeasureWidth. */
	float MeasureWidthAtScale(const FString& Text, const FSlateFontInfo& Font, float Scale)
	{
		if (!FSlateApplication::IsInitialized())
		{
			return 0.f;
		}
		const float FontScale = FMath::Max(Scale, 0.01f);
		const TSharedRef<FSlateFontMeasure> Measure = FSlateApplication::Get().GetRenderer()->GetFontMeasureService();
		return static_cast<float>(FVector2f(Measure->Measure(Text, Font, FontScale)).X) / FontScale;
	}

	/** -180..180 (float). */
	float WrapDeg(float AngleDeg)
	{
		return static_cast<float>(FRotator::NormalizeAxis(static_cast<double>(AngleDeg)));
	}

	/** Points of a circular arc (slate units, angles in deg clockwise from +X on screen). */
	TArray<FVector2f> ArcPoints(const FVector2f& Centre, float Radius, float StartDeg, float SweepDeg, int32 Segments)
	{
		TArray<FVector2f> Points;
		const int32 Count = FMath::Max(Segments, 1);
		Points.Reserve(Count + 1);

		for (int32 Index = 0; Index <= Count; ++Index)
		{
			const float Angle = FMath::DegreesToRadians(StartDeg + SweepDeg * static_cast<float>(Index) / static_cast<float>(Count));
			Points.Add(Centre + FVector2f(FMath::Cos(Angle), FMath::Sin(Angle)) * Radius);
		}
		return Points;
	}

	/** Local players that have seen the Point & Fly boarding hint (once per session). */
	TSet<FObjectKey>& PointFlyHintSeen()
	{
		static TSet<FObjectKey> Seen;
		return Seen;
	}

	/** Local players that have held Aim (RMB / LB) in Point & Fly this session: the look hints are done. */
	TSet<FObjectKey>& PointFlyLookLearned()
	{
		static TSet<FObjectKey> Learned;
		return Learned;
	}

	/** The gunner panel's station tag (EAirshipStation order). */
	const TCHAR* GunnerStationLabel(int32 Station)
	{
		static const TCHAR* const Labels[] = { TEXT("CANNON L1"), TEXT("CANNON L2"), TEXT("CANNON R1"), TEXT("CANNON R2"), TEXT("GUN L"), TEXT("GUN R") };
		return (Station >= 0 && Station < static_cast<int32>(UE_ARRAY_COUNT(Labels))) ? Labels[Station] : TEXT("GUN");
	}
}

UAirshipHUDWidget::UAirshipHUDWidget(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	// Comic ink on paper (sRGB)
	PaperColor = FLinearColor(FColor(240, 230, 205));
	InkColor = FLinearColor(FColor(28, 24, 22));
	HullColor = FLinearColor(FColor(196, 58, 44));
	BoostColor = FLinearColor(FColor(38, 120, 178));
	ReloadColor = FLinearColor(FColor(232, 160, 40));
	PilotColor = FLinearColor(FColor(74, 142, 64));

	// Display only: clicks go through to the game
	SetVisibilityInternal(ESlateVisibility::HitTestInvisible);
}

void UAirshipHUDWidget::NativeConstruct()
{
	Super::NativeConstruct();
	RefreshBrushes();
}

void UAirshipHUDWidget::RefreshBrushes()
{
	using namespace AirshipHUDPrivate;
	const FLinearColor Track = FMath::Lerp(PaperColor, InkColor, 0.08f);

	MakeRoundedBrush(ShadowBrush, InkColor, 8.f, FLinearColor::Transparent, 0.f);
	MakeRoundedBrush(PanelBrush, PaperColor, 8.f, InkColor, 3.f);
	MakeRoundedBrush(TrackBrush, Track, 4.f, InkColor, 2.f);
	MakeRoundedBrush(FillBrush, FLinearColor::White, 3.f, FLinearColor::Transparent, 0.f);
	MakeRoundedBrush(TagBrush, InkColor, 4.f, FLinearColor::Transparent, 0.f);
}

void UAirshipHUDWidget::SetAirship(AAirshipPawn* InAirship)
{
	Airship = InAirship;
	AltitudeM = -1.f;

	// A release before the widget existed is no flash; the order shown now is no ring
	if (InAirship)
	{
		LastTurboEventCount = InAirship->GetCosmeticState().TurboEventCount;
		GalleonNotch = InAirship->GetGalleonNotch();
	}

	// Valid values before the first paint (Slate may paint the new widget before it ticks)
	RefreshValues(0.f, true);
}

FVector2D UAirshipHUDWidget::GetPanelSize() const
{
	if (GunnerStation >= 0)
	{
		return GunnerPanelSize;
	}

	// Every scheme: the PILOT and GUNS rows (round 2)
	const float Extra = (LayoutScheme == EAirshipControlScheme::Galleon ? GalleonExtraHeight
		: (LayoutScheme == EAirshipControlScheme::SkyRacer ? SkyRowHeight : 0.f)) + PilotRowHeight + GunsRowHeight;
	return PanelSize + FVector2D(0.0, Extra);
}

void UAirshipHUDWidget::SetGunnerStation(AAirshipPawn* InAirship, int32 InStation)
{
	GunnerStation = (InAirship && InStation >= 0 && InStation < Airship::NumStations) ? InStation : -1;
	SetAirship(GunnerStation >= 0 ? InAirship : nullptr);
}

void UAirshipHUDWidget::RefreshLayoutScheme()
{
	if (const AAirshipPawn* Ship = Airship.Get())
	{
		LayoutScheme = Ship->GetControlScheme();
	}
}

FLinearColor UAirshipHUDWidget::GetTierColor(int32 Tier) const
{
	if (Tier >= 3)
	{
		return HullColor;
	}
	if (Tier == 2)
	{
		return ReloadColor;
	}
	if (Tier == 1)
	{
		return BoostColor;
	}
	return FMath::Lerp(InkColor, PaperColor, 0.45f);
}

void UAirshipHUDWidget::NativeTick(const FGeometry& MyGeometry, float InDeltaTime)
{
	Super::NativeTick(MyGeometry, InDeltaTime);
	RefreshValues(InDeltaTime, false);
}

void UAirshipHUDWidget::RefreshValues(float DeltaSeconds, bool bForceAltitude)
{
	const AAirshipPawn* Ship = Airship.Get();

	if (!Ship)
	{
		return;
	}

	// Every frame: a scheme switch with the HUD up redraws at once (the ship resizes the slot)
	LayoutScheme = Ship->GetControlScheme();

	if (GunnerStation >= 0)
	{
		RefreshGunnerValues();
		return;
	}

	if (bOverlayMode)
	{
		RefreshOverlayValues(DeltaSeconds);
		return;
	}

	const FAirshipFlightTelemetry Telemetry = Ship->GetFlightTelemetry();
	const UAirshipFlightComponent* Flight = Ship->GetFlight();
	const float FuelMax = Flight ? Flight->BoostFuelMax : 100.f;

	Health = Telemetry.Health;
	HealthAlpha = Telemetry.MaxHealth > 0.f ? FMath::Clamp(Telemetry.Health / Telemetry.MaxHealth, 0.f, 1.f) : 0.f;
	FuelAlpha = FuelMax > 0.f ? FMath::Clamp(Telemetry.BoostFuel / FuelMax, 0.f, 1.f) : 0.f;
	SpeedMS = Telemetry.SpeedMS;
	bBoosting = Telemetry.Boost > 0.5f;
	AimSide = Ship->GetAimSide();

	for (int32 Side = 0; Side < 2; ++Side)
	{
		const EAirshipSide Which = Side == 0 ? EAirshipSide::Port : EAirshipSide::Starboard;
		ReloadAlpha[Side] = Ship->GetCannonReloadAlpha(Which);
		ReloadSeconds[Side] = (1.f - ReloadAlpha[Side]) * Ship->GetCannonCooldown();
	}

	RefreshCrewValues(Ship);

	// The ground under the ship: a trace every AltitudeTraceInterval
	AltitudeTimer -= DeltaSeconds;

	if (bForceAltitude || AltitudeTimer <= 0.f)
	{
		AltitudeTimer = AltitudeTraceInterval;
		const float Distance = Ship->TraceGroundDistance(AltitudeTraceLength);
		AltitudeM = Distance >= 0.f ? Distance * 0.01f : -1.f;
	}

	if (LayoutScheme == EAirshipControlScheme::Galleon)
	{
		// The pilot's own order (no latency); a new one rings for 0.4 s
		const int32 Notch = Ship->GetGalleonNotch();

		if (Notch != GalleonNotch)
		{
			GalleonNotch = Notch;
			GalleonRingTime = 0.4f;
		}
		else
		{
			GalleonRingTime = FMath::Max(0.f, GalleonRingTime - DeltaSeconds);
		}

		ForwardSpeedMS = Telemetry.ForwardSpeedMS;

		if (Flight)
		{
			OrderAsternMS = Flight->GalleonOrderAsternSpeed * 0.01f;
			OrderSlowMS = Flight->GalleonOrderSlowSpeed * 0.01f;
			OrderHalfMS = Flight->GalleonOrderHalfSpeed * 0.01f;
			// FULL is throttle 1: it settles a little under VTop
			OrderFullMS = 0.956f * Flight->VTop * 0.01f;
		}

		HelmSteer = Telemetry.Steer;
		TurnRateDegS = Telemetry.YawRateDegS;
		bHelmDrifting = Telemetry.bDrifting;
		bGalleonStations = Ship->IsGalleonStations();
		bFacingInArc = Ship->IsAimInCannonArc(AimSide, Ship->GetLocalAimPoint());
	}
	else if (LayoutScheme == EAirshipControlScheme::SkyRacer)
	{
		// The pilot's own cosmetic state: the HUD is predicted
		const FAirshipCosmeticState& C = Ship->GetCosmeticState();
		bDriftActive = C.DriftDir != 0;
		DriftCharge = C.DriftCharge;
		DriftTier = C.DriftTier;
		TurboAlpha = C.TurboAlpha;
		TurboTier = C.TurboTier;
		TurboChain = C.TurboChain;

		if (C.TurboEventCount != LastTurboEventCount)
		{
			LastTurboEventCount = C.TurboEventCount;
			FlashTime = 0.3f;
			SinceRelease = 0.f;
		}
		else
		{
			FlashTime = FMath::Max(0.f, FlashTime - DeltaSeconds);
			SinceRelease += DeltaSeconds;
		}

		bChainLive = bDriftActive || SinceRelease <= (Flight ? Flight->SkyChainWindow : 2.5f);

		if (Flight)
		{
			SkyTier1 = Flight->SkyTier1;
			SkyTier2 = Flight->SkyTier2;
		}
	}
}

void UAirshipHUDWidget::RefreshOverlayValues(float DeltaSeconds)
{
	using namespace AirshipHUDPrivate;

	const AAirshipPawn* Ship = Airship.Get();
	const APlayerController* PC = GetOwningPlayer();
	const APlayerCameraManager* CameraManager = PC ? PC->PlayerCameraManager.Get() : nullptr;
	bPFActive = Ship && Ship->IsPointFlyActive() && CameraManager;

	if (!bPFActive)
	{
		return;
	}

	bPFFreeLook = Ship->IsPFFreeLook();
	bPFLock = Ship->IsPFGunLocked();
	PFSwingDir = Ship->GetPFLockSwingDir();
	AimSide = Ship->GetAimSide();
	ReloadAlpha[AimSide == EAirshipSide::Port ? 0 : 1] = Ship->GetCannonReloadAlpha(AimSide);
	bFacingInArc = Ship->IsAimInCannonArc(AimSide, Ship->GetLocalAimPoint());

	const FVector CameraLocation = CameraManager->GetCameraLocation();
	const FRotator CameraRotation = CameraManager->GetCameraRotation();
	const float HullYaw = static_cast<float>(Ship->GetActorRotation().Yaw);
	const float CameraYaw = static_cast<float>(CameraRotation.Yaw);

	// Nose marker: 600 m out along the hull's heading at the camera's pitch (same height as the crosshair, offset by the
	// turn still to come)
	const FVector NoseDirection = FRotator(CameraRotation.Pitch, static_cast<double>(HullYaw), 0.0).Vector();
	FVector2D Projected = FVector2D::ZeroVector;
	bNoseOnScreen = UWidgetLayoutLibrary::ProjectWorldLocationToWidgetPosition(PC, CameraLocation + NoseDirection * 60000.0, Projected, true);

	if (bNoseOnScreen)
	{
		NosePosition = Projected;
	}

	// One paper flash when the gap closes below 1 deg
	const float Gap = FMath::Abs(WrapDeg(HullYaw - CameraYaw));
	NoseFlashTime = (NoseGapDeg >= 1.f && Gap < 1.f) ? 0.3f : FMath::Max(0.f, NoseFlashTime - DeltaSeconds);
	NoseGapDeg = Gap;

	// Heading strip (broadside mode): centred on the bow, so the aim (55-150 deg off the bow in a broadside) is on it
	StripTargetDeg = WrapDeg(Ship->GetPFHeadingTargetDeg() - HullYaw);
	StripAimDeg = WrapDeg(CameraYaw - HullYaw);
	StripArcDeg = Ship->GetCannonYawLimitDeg();
	bPFParked = Ship->IsPFParked();

	// The look hints (once per local player and session): the boarding hint stays at least 8 s and until Aim has been
	// held once (at most 45 s); the contextual "hold RMB to look" shows in steering mode while the camera is far off the
	// nose, until Aim has been held once
	const FObjectKey Key(GetOwningLocalPlayer());

	if (HintAge < 0.f)
	{
		bool bAlreadySeen = false;
		PointFlyHintSeen().Add(Key, &bAlreadySeen);
		HintAge = bAlreadySeen ? 1000.f : 0.f;
		bLookLearned = PointFlyLookLearned().Contains(Key);
	}
	else
	{
		HintAge += DeltaSeconds;
	}

	if (bPFFreeLook && !bLookLearned)
	{
		bLookLearned = true;
		PointFlyLookLearned().Add(Key);
	}

	if (HintAge < 45.f && (HintAge < 8.f || !bLookLearned))
	{
		HintEndAge = FMath::Max(8.f, HintAge);
	}

	const bool bFarOffNose = !bPFFreeLook && !bPFParked && Gap > 50.f;
	OffNoseTime = bFarOffNose ? OffNoseTime + DeltaSeconds : 0.f;
	const bool bShowLookHint = !bLookLearned && OffNoseTime >= 0.3f;
	LookHintAlpha = FMath::FInterpConstantTo(LookHintAlpha, bShowLookHint ? 1.f : 0.f, DeltaSeconds, bShowLookHint ? 6.f : 3.f);
}

int32 UAirshipHUDWidget::NativePaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect, FSlateWindowElementList& OutDrawElements,
	int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const
{
	int32 Layer = Super::NativePaint(Args, AllottedGeometry, MyCullingRect, OutDrawElements, LayerId, InWidgetStyle, bParentEnabled);

	if (!Airship.IsValid())
	{
		return Layer;
	}

	// A gunner's own machine: crosshair, gun mark, the gunner panel
	if (GunnerStation >= 0)
	{
		return PaintGunner(AllottedGeometry, OutDrawElements, Layer, InWidgetStyle);
	}

	// Point & Fly's marks over the viewport (nothing in other schemes)
	if (bOverlayMode)
	{
		return PaintPointFlyOverlay(AllottedGeometry, OutDrawElements, Layer, InWidgetStyle);
	}

	using namespace AirshipHUDPrivate;
	const FLinearColor Opacity = InWidgetStyle.GetColorAndOpacityTint();
	const FVector2f Size(AllottedGeometry.GetLocalSize());
	const float Pad = 12.f;
	const float ShadowOffset = 5.f;
	const FVector2f Panel(Size.X - ShadowOffset, Size.Y - ShadowOffset);
	const bool bGalleon = LayoutScheme == EAirshipControlScheme::Galleon;
	const bool bSky = LayoutScheme == EAirshipControlScheme::SkyRacer;

	const FSlateFontInfo LabelFont = FCoreStyle::GetDefaultFontStyle(TEXT("Black"), 11);
	const FSlateFontInfo ValueFont = FCoreStyle::GetDefaultFontStyle(TEXT("Bold"), 11);
	const FSlateFontInfo BigFont = FCoreStyle::GetDefaultFontStyle(TEXT("Black"), 20);
	const FSlateFontInfo SmallFont = FCoreStyle::GetDefaultFontStyle(TEXT("Bold"), 9);

	// MakeBox fills a RoundedBox brush with the element tint alone and never reads the brush's own TintColor (widgets
	// multiply Brush.GetTint into it themselves, SBorder-style). Without that the paper panel, the ink shadow, the bar
	// tracks and the ink tags all came out white: the facing side's PORT / STBD label and the boosting BOOST label
	// (paper-coloured text on an ink tag) were invisible (validation PIE run 2026-11-22).
	auto Box = [&](const FVector2f& Position, const FVector2f& BoxSize, const FSlateBrush& Brush, const FLinearColor& Tint, int32 InLayer)
	{
		FSlateDrawElement::MakeBox(OutDrawElements, InLayer, AllottedGeometry.ToPaintGeometry(BoxSize, FSlateLayoutTransform(Position)), &Brush,
			ESlateDrawEffect::None, Brush.GetTint(InWidgetStyle) * Tint * Opacity);
	};

	auto Text = [&](const FVector2f& Position, const FString& String, const FSlateFontInfo& Font, const FLinearColor& Color, int32 InLayer)
	{
		FSlateDrawElement::MakeText(OutDrawElements, InLayer, AllottedGeometry.ToPaintGeometry(FVector2f(Size.X, Font.Size * 1.6f), FSlateLayoutTransform(Position)),
			String, Font, ESlateDrawEffect::None, Color * Opacity);
	};

	auto Lines = [&](const TArray<FVector2f>& Points, const FLinearColor& Color, float Thickness, int32 InLayer)
	{
		FSlateDrawElement::MakeLines(OutDrawElements, InLayer, AllottedGeometry.ToPaintGeometry(), Points, ESlateDrawEffect::None, Color * Opacity, true, Thickness);
	};

	// A bar: ink-outlined track, coloured fill, ink ticks at quarters
	auto Bar = [&](const FVector2f& Position, const FVector2f& BarSize, float Alpha, const FLinearColor& Color, int32 InLayer)
	{
		Box(Position, BarSize, TrackBrush, FLinearColor::White, InLayer);
		const float Inset = 3.f;
		const float FillWidth = (BarSize.X - 2.f * Inset) * FMath::Clamp(Alpha, 0.f, 1.f);

		if (FillWidth > 0.5f)
		{
			Box(Position + FVector2f(Inset, Inset), FVector2f(FillWidth, BarSize.Y - 2.f * Inset), FillBrush, Color, InLayer + 1);
		}

		for (int32 Tick = 1; Tick < 4; ++Tick)
		{
			const float X = Position.X + BarSize.X * 0.25f * Tick;
			TArray<FVector2f> Points = { FVector2f(X, Position.Y + 2.f), FVector2f(X, Position.Y + BarSize.Y * 0.45f) };
			FSlateDrawElement::MakeLines(OutDrawElements, InLayer + 2, AllottedGeometry.ToPaintGeometry(), MoveTemp(Points), ESlateDrawEffect::None, InkColor * Opacity, true, 1.5f);
		}
	};

	// An ink tag with paper text (Galleon's SWING / STATIONS)
	auto SmallTag = [&](const FVector2f& Position, const FString& String, int32 InLayer)
	{
		const float TagWidth = MeasureWidth(String, SmallFont) + 8.f;
		Box(Position, FVector2f(TagWidth, 13.f), TagBrush, FLinearColor::White, InLayer);
		Text(Position + FVector2f(4.f, -1.f), String, SmallFont, PaperColor, InLayer + 1);
		return TagWidth;
	};

	// Panel: ink drop shadow, paper with an ink outline
	++Layer;
	Box(FVector2f(ShadowOffset, ShadowOffset), Panel, ShadowBrush, FLinearColor::White, Layer);
	++Layer;
	Box(FVector2f::ZeroVector, Panel, PanelBrush, FLinearColor::White, Layer);
	++Layer;

	const float LabelWidth = 52.f;
	const float ValueWidth = 46.f;
	const float BarX = Pad + LabelWidth;
	const float BarWidth = Panel.X - BarX - ValueWidth - Pad;
	const float BarHeight = 16.f;

	// ---- Galleon: the engine telegraph and the speed rule (the rows below move down 50) ----------------------------
	if (bGalleon)
	{
		const float NotchGap = 4.f;
		const float NotchWidth = (Panel.X - 2.f * Pad - 4.f * NotchGap) / 5.f;
		const float NotchHeight = 18.f;
		const bool bBlink = GalleonRingTime > 0.f && FMath::Frac(GalleonRingTime * 10.f) >= 0.5f;

		for (int32 Notch = AirshipGalleon::Astern; Notch <= AirshipGalleon::Full; ++Notch)
		{
			const FVector2f NotchPosition(Pad + static_cast<float>(Notch + 1) * (NotchWidth + NotchGap), Pad);
			const bool bOrdered = Notch == GalleonNotch;
			// While boosting, FULL is FULL STEAM
			const bool bSteam = Notch == AirshipGalleon::Full && bBoosting;

			if (bSteam || (bOrdered && bBlink))
			{
				Box(NotchPosition, FVector2f(NotchWidth, NotchHeight), FillBrush, BoostColor, Layer);
			}
			else if (bOrdered)
			{
				Box(NotchPosition, FVector2f(NotchWidth, NotchHeight), TagBrush, FLinearColor::White, Layer);
			}
			else
			{
				Box(NotchPosition, FVector2f(NotchWidth, NotchHeight), TrackBrush, FLinearColor::White, Layer);
			}

			const FString Label = bSteam ? FString(TEXT("STEAM")) : FString(AirshipGalleon::NotchName(Notch));
			const float NameWidth = MeasureWidth(Label, SmallFont);
			Text(NotchPosition + FVector2f(0.5f * (NotchWidth - NameWidth), 2.f), Label, SmallFont, (bOrdered || bSteam) ? PaperColor : InkColor, Layer + 1);
		}

		// The speed rule: the forward speed (fill) working up to the ordered speed (hollow triangle)
		const float RuleX = Pad;
		const float RuleY = Pad + 24.f;
		const float RuleWidth = Panel.X - 2.f * Pad;
		const float RuleHeight = 10.f;
		const float RuleMinMS = -FMath::Max(OrderAsternMS, 1.f);
		const float RuleMaxMS = FMath::Max(OrderFullMS + 4.f, RuleMinMS + 10.f);

		auto RuleXAt = [&](float SpeedValueMS)
		{
			return RuleX + RuleWidth * FMath::Clamp((SpeedValueMS - RuleMinMS) / (RuleMaxMS - RuleMinMS), 0.f, 1.f);
		};

		Box(FVector2f(RuleX, RuleY), FVector2f(RuleWidth, RuleHeight), TrackBrush, FLinearColor::White, Layer);

		const float ZeroX = RuleXAt(0.f);
		const float SpeedX = RuleXAt(ForwardSpeedMS);

		if (FMath::Abs(SpeedX - ZeroX) > 0.5f)
		{
			Box(FVector2f(FMath::Min(ZeroX, SpeedX), RuleY + 2.f), FVector2f(FMath::Abs(SpeedX - ZeroX), RuleHeight - 4.f), FillBrush, ReloadColor, Layer + 1);
		}

		for (const float TickMS : { -OrderAsternMS, 0.f, OrderSlowMS, OrderHalfMS, OrderFullMS })
		{
			const float TickX = RuleXAt(TickMS);
			Lines({ FVector2f(TickX, RuleY), FVector2f(TickX, RuleY + RuleHeight) }, InkColor, 1.5f, Layer + 2);
		}

		const float OrderMS = GalleonNotch < 0 ? -OrderAsternMS
			: (GalleonNotch == AirshipGalleon::Slow ? OrderSlowMS : (GalleonNotch == AirshipGalleon::Half ? OrderHalfMS : (GalleonNotch >= AirshipGalleon::Full ? OrderFullMS : 0.f)));
		// FULL STEAM: the boost peak, at the right end
		const float TriangleX = bBoosting ? RuleX + RuleWidth : RuleXAt(OrderMS);
		Lines({ FVector2f(TriangleX - 4.f, RuleY - 6.f), FVector2f(TriangleX + 4.f, RuleY - 6.f), FVector2f(TriangleX, RuleY - 1.f), FVector2f(TriangleX - 4.f, RuleY - 6.f) },
			InkColor, 1.5f, Layer + 2);
	}

	// Hull
	float Y = Pad + (bGalleon ? 50.f : 0.f);
	Text(FVector2f(Pad, Y - 1.f), TEXT("HULL"), LabelFont, InkColor, Layer);
	Bar(FVector2f(BarX, Y), FVector2f(BarWidth, BarHeight), HealthAlpha, HullColor, Layer);
	{
		const FString Value = FString::FromInt(FMath::CeilToInt(Health));
		Text(FVector2f(Panel.X - Pad - MeasureWidth(Value, ValueFont), Y - 1.f), Value, ValueFont, InkColor, Layer);
	}

	// The pilot's own health (round 2: the on-foot overlay is hidden while flying, and the crew takes a share of hull damage)
	Y += BarHeight + 8.f;
	Text(FVector2f(Pad, Y - 1.f), TEXT("PILOT"), LabelFont, InkColor, Layer);
	Bar(FVector2f(BarX, Y), FVector2f(BarWidth, BarHeight), PilotHealthAlpha, PilotColor, Layer);
	{
		const FString Value = PilotHealth >= 0.f ? FString::FromInt(FMath::CeilToInt(PilotHealth)) : FString(TEXT("--"));
		Text(FVector2f(Panel.X - Pad - MeasureWidth(Value, ValueFont), Y - 1.f), Value, ValueFont, InkColor, Layer);
	}

	// Boost fuel (the label turns into an ink tag while boosting)
	Y += BarHeight + 8.f;

	if (bBoosting)
	{
		// As wide as the word plus 4 on each side (a fixed LabelWidth - 4 cut the T off), never into the bar
		const float TagWidth = FMath::Clamp(MeasureWidth(TEXT("BOOST"), LabelFont) + 8.f, LabelWidth - 4.f, LabelWidth);
		Box(FVector2f(Pad - 4.f, Y - 2.f), FVector2f(TagWidth, BarHeight + 4.f), TagBrush, FLinearColor::White, Layer);
	}
	Text(FVector2f(Pad, Y - 1.f), TEXT("BOOST"), LabelFont, bBoosting ? PaperColor : InkColor, Layer + 1);
	Bar(FVector2f(BarX, Y), FVector2f(BarWidth, BarHeight), FuelAlpha, BoostColor, Layer);
	{
		const FString Value = FString::Printf(TEXT("%d%%"), FMath::RoundToInt(FuelAlpha * 100.f));
		Text(FVector2f(Panel.X - Pad - MeasureWidth(Value, ValueFont), Y - 1.f), Value, ValueFont, InkColor, Layer);
	}

	// ---- Sky Racer: DRIFT (the charge) / TURBO (the burn) ------------------------------------------------------------
	if (bSky)
	{
		Y += BarHeight + 8.f;
		const bool bBurning = TurboAlpha > 0.f && !bDriftActive;
		const int32 ShownTier = bBurning ? TurboTier : DriftTier;
		const FLinearColor TierColor = GetTierColor(ShownTier);
		const FString Label = bBurning ? FString(TEXT("TURBO")) : FString(TEXT("DRIFT"));

		if (bDriftActive || bBurning)
		{
			const float TagWidth = FMath::Clamp(MeasureWidth(Label, LabelFont) + 8.f, LabelWidth - 4.f, LabelWidth);

			if (bBurning)
			{
				Box(FVector2f(Pad - 4.f, Y - 2.f), FVector2f(TagWidth, BarHeight + 4.f), FillBrush, TierColor, Layer);
			}
			else
			{
				Box(FVector2f(Pad - 4.f, Y - 2.f), FVector2f(TagWidth, BarHeight + 4.f), TagBrush, FLinearColor::White, Layer);
			}
		}
		Text(FVector2f(Pad, Y - 1.f), Label, LabelFont, (bDriftActive || bBurning) ? PaperColor : InkColor, Layer + 1);
		Bar(FVector2f(BarX, Y), FVector2f(BarWidth, BarHeight), bBurning ? TurboAlpha : DriftCharge, TierColor, Layer);

		// The tier thresholds
		for (const float TierAt : { SkyTier1, SkyTier2 })
		{
			const float TickX = BarX + BarWidth * FMath::Clamp(TierAt, 0.f, 1.f);
			Lines({ FVector2f(TickX, Y - 2.f), FVector2f(TickX, Y + BarHeight + 2.f) }, InkColor, 2.f, Layer + 3);
		}

		// I / II / III, and the chain multiplier while a chain is live
		FString Value = ShownTier >= 3 ? FString(TEXT("III")) : (ShownTier == 2 ? FString(TEXT("II")) : (ShownTier == 1 ? FString(TEXT("I")) : FString(TEXT("-"))));

		if (bChainLive && TurboChain > 0)
		{
			Value += FString::Printf(TEXT(" x%d"), TurboChain + 1);
		}
		Text(FVector2f(Panel.X - Pad - MeasureWidth(Value, ValueFont), Y - 1.f), Value, ValueFont, InkColor, Layer);
	}

	// Speed and altitude, big
	Y += BarHeight + 6.f;
	{
		const FString Speed = FString::FromInt(FMath::RoundToInt(SpeedMS));
		Text(FVector2f(Pad, Y), Speed, BigFont, InkColor, Layer);
		Text(FVector2f(Pad + MeasureWidth(Speed, BigFont) + 4.f, Y + 12.f), TEXT("m/s"), ValueFont, InkColor, Layer);

		const float AltX = Panel.X * 0.5f + 6.f;
		Text(FVector2f(AltX, Y + 12.f), TEXT("ALT"), LabelFont, InkColor, Layer);
		const float AltValueX = AltX + MeasureWidth(TEXT("ALT"), LabelFont) + 6.f;
		const FString Altitude = AltitudeM >= 0.f ? FString::FromInt(FMath::RoundToInt(AltitudeM)) : FString(TEXT("--"));
		Text(FVector2f(AltValueX, Y), Altitude, BigFont, InkColor, Layer);
		Text(FVector2f(AltValueX + MeasureWidth(Altitude, BigFont) + 4.f, Y + 12.f), TEXT("m"), ValueFont, InkColor, Layer);
	}

	// Cannons: the side they face as an ink tag, reload bar, READY or seconds left
	Y += 36.f;

	// ---- Galleon: the helm (needle at the shaped helm, turn rate, SWING / STATIONS) above the cannons ----------------
	if (bGalleon)
	{
		const float HelmWidth = 120.f;
		const float HelmX = 0.5f * (Panel.X - HelmWidth);
		const float HelmY = Y + 3.f;
		Text(FVector2f(Pad, Y - 1.f), TEXT("HELM"), LabelFont, InkColor, Layer);
		Box(FVector2f(HelmX, HelmY), FVector2f(HelmWidth, 10.f), TrackBrush, FLinearColor::White, Layer);

		const float CentreX = HelmX + 0.5f * HelmWidth;
		Lines({ FVector2f(CentreX, HelmY + 2.f), FVector2f(CentreX, HelmY + 8.f) }, InkColor, 1.f, Layer + 1);
		const float NeedleX = CentreX + 0.5f * HelmWidth * FMath::Clamp(HelmSteer, -1.f, 1.f);
		Lines({ FVector2f(NeedleX, HelmY - 3.f), FVector2f(NeedleX, HelmY + 13.f) }, InkColor, 3.f, Layer + 2);

		Text(FVector2f(HelmX + HelmWidth + 6.f, Y), FString::Printf(TEXT("%d deg/s"), FMath::RoundToInt(FMath::Abs(TurnRateDegS))), SmallFont, InkColor, Layer);

		if (bHelmDrifting)
		{
			SmallTag(FVector2f(Pad, Y + 14.f), TEXT("SWING"), Layer);
		}

		if (bGalleonStations)
		{
			const FString Stations = TEXT("STATIONS");
			SmallTag(FVector2f(Panel.X - Pad - MeasureWidth(Stations, SmallFont) - 8.f, Y + 14.f), Stations, Layer);
		}

		Y += 28.f;
	}

	const float HalfWidth = (Panel.X - 2.f * Pad) * 0.5f;

	for (int32 Side = 0; Side < 2; ++Side)
	{
		const float X = Pad + HalfWidth * Side;
		const bool bFacing = (Side == 0) == (AimSide == EAirshipSide::Port);
		const TCHAR* Name = Side == 0 ? TEXT("PORT") : TEXT("STBD");
		const float TagWidth = 44.f;

		// Galleon: the facing side's tag gets a ReloadColor outline while the aim point is inside its arc
		const bool bInArc = bGalleon && bFacing && bFacingInArc;

		if (bFacing)
		{
			Box(FVector2f(X - 4.f, Y - 2.f), FVector2f(TagWidth, 18.f), TagBrush, FLinearColor::White, Layer);

			if (bInArc)
			{
				const FVector2f TopLeft(X - 6.f, Y - 4.f);
				const FVector2f BottomRight(X - 6.f + TagWidth + 4.f, Y + 18.f);
				Lines({ TopLeft, FVector2f(BottomRight.X, TopLeft.Y), BottomRight, FVector2f(TopLeft.X, BottomRight.Y), TopLeft }, ReloadColor, 2.f, Layer + 2);
			}
		}
		Text(FVector2f(X, Y - 1.f), Name, LabelFont, bFacing ? PaperColor : InkColor, Layer + 1);

		const bool bReady = ReloadAlpha[Side] >= 1.f;
		const FVector2f BarPosition(X + TagWidth + 2.f, Y + 2.f);
		const FVector2f BarSize(HalfWidth - TagWidth - 8.f, 10.f);

		if (bSideManned[Side])
		{
			// Both cannons have gunners: the broadside is theirs
			Text(BarPosition + FVector2f(0.f, -4.f), TEXT("MANNED"), ValueFont, InkColor, Layer);
		}
		else if (bReady)
		{
			// Galleon: in the arc and loaded = FIRE
			Text(BarPosition + FVector2f(0.f, -4.f), bInArc ? TEXT("FIRE") : TEXT("READY"), ValueFont, bInArc ? HullColor : InkColor, Layer);
		}
		else
		{
			Bar(BarPosition, BarSize, ReloadAlpha[Side], ReloadColor, Layer);
			Text(BarPosition + FVector2f(0.f, 11.f), FString::Printf(TEXT("%.1fs"), ReloadSeconds[Side]), SmallFont, InkColor, Layer);
		}
	}

	// ---- GUNS (round 2): the turrets' heat (health underneath, an X when wrecked), then a dot per station (cannons L1,
	// L2, R1, R2, turrets L, R), filled when manned -------------------------------------------------------------------
	{
		const float GunsY = Y + 30.f;
		const float GaugeWidth = 54.f;
		const float GaugeHeight = 10.f;
		Text(FVector2f(Pad, GunsY - 3.f), TEXT("GUNS"), LabelFont, InkColor, Layer);

		for (int32 TurretIndex = 0; TurretIndex < 2; ++TurretIndex)
		{
			const FVector2f GaugePosition(BarX + static_cast<float>(TurretIndex) * (GaugeWidth + 10.f), GunsY);

			if (!bTurretShown[TurretIndex])
			{
				Text(GaugePosition + FVector2f(0.f, -3.f), TEXT("--"), ValueFont, InkColor, Layer);
				continue;
			}

			Bar(GaugePosition, FVector2f(GaugeWidth, GaugeHeight), TurretHeat[TurretIndex], bTurretOverheated[TurretIndex] ? HullColor : ReloadColor, Layer);
			const float HealthWidth = GaugeWidth * FMath::Clamp(TurretHealthAlpha[TurretIndex], 0.f, 1.f);

			if (HealthWidth > 0.5f)
			{
				Lines({ GaugePosition + FVector2f(0.f, GaugeHeight + 3.f), GaugePosition + FVector2f(HealthWidth, GaugeHeight + 3.f) }, PilotColor, 3.f, Layer + 1);
			}

			if (bTurretWrecked[TurretIndex])
			{
				const FVector2f A = GaugePosition + FVector2f(GaugeWidth * 0.5f - 8.f, -3.f);
				const FVector2f B = GaugePosition + FVector2f(GaugeWidth * 0.5f + 8.f, GaugeHeight + 3.f);
				Lines({ A, B }, HullColor, 3.f, Layer + 3);
				Lines({ FVector2f(A.X, B.Y), FVector2f(B.X, A.Y) }, HullColor, 3.f, Layer + 3);
			}
		}

		const float DotSize = 9.f;
		float DotX = BarX + 2.f * (GaugeWidth + 10.f) + 2.f;

		for (int32 Station = 0; Station < Airship::NumStations; ++Station)
		{
			// A small gap between the cannons and the turrets
			if (Station == Airship::FirstTurretStation)
			{
				DotX += 6.f;
			}

			const bool bManned = (MannedMask & (1 << Station)) != 0;
			Box(FVector2f(DotX, GunsY), FVector2f(DotSize, DotSize), bManned ? TagBrush : TrackBrush, FLinearColor::White, Layer);
			DotX += DotSize + 3.f;
		}
	}

	// Sky Racer: the panel outline flashes the tier colour on a mini-turbo release
	if (bSky && FlashTime > 0.f)
	{
		const FLinearColor FlashColor = GetTierColor(TurboTier).CopyWithNewOpacity(FMath::Clamp(FlashTime / 0.3f, 0.f, 1.f));
		const FVector2f TopLeft(1.5f, 1.5f);
		const FVector2f BottomRight(Panel.X - 1.5f, Panel.Y - 1.5f);
		Lines({ TopLeft, FVector2f(BottomRight.X, TopLeft.Y), BottomRight, FVector2f(TopLeft.X, BottomRight.Y), TopLeft }, FlashColor, 3.f, Layer + 4);
	}

	return Layer + 5;
}

int32 UAirshipHUDWidget::PaintPointFlyOverlay(const FGeometry& AllottedGeometry, FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle) const
{
	if (!bPFActive)
	{
		return LayerId;
	}

	using namespace AirshipHUDPrivate;
	const FLinearColor Opacity = InWidgetStyle.GetColorAndOpacityTint();
	const FVector2f Size(AllottedGeometry.GetLocalSize());
	const FVector2f Centre = Size * 0.5f;
	const int32 Layer = LayerId + 1;
	const float PaintScale = AllottedGeometry.GetAccumulatedLayoutTransform().GetScale();

	const FSlateFontInfo SmallFont = FCoreStyle::GetDefaultFontStyle(TEXT("Bold"), 10);
	const FSlateFontInfo LockFont = FCoreStyle::GetDefaultFontStyle(TEXT("Black"), 16);

	// Every mark is ink (or amber) with a 1 px paper outline, for contrast on sky and platforms
	auto Stroke = [&](const TArray<FVector2f>& Points, const FLinearColor& Color, float Thickness, int32 InLayer)
	{
		FSlateDrawElement::MakeLines(OutDrawElements, InLayer, AllottedGeometry.ToPaintGeometry(), Points, ESlateDrawEffect::None,
			PaperColor.CopyWithNewOpacity(Color.A) * Opacity, true, Thickness + 2.f);
		FSlateDrawElement::MakeLines(OutDrawElements, InLayer + 1, AllottedGeometry.ToPaintGeometry(), Points, ESlateDrawEffect::None, Color * Opacity, true, Thickness);
	};

	auto Box = [&](const FVector2f& Position, const FVector2f& BoxSize, const FSlateBrush& Brush, const FLinearColor& Tint, int32 InLayer)
	{
		FSlateDrawElement::MakeBox(OutDrawElements, InLayer, AllottedGeometry.ToPaintGeometry(BoxSize, FSlateLayoutTransform(Position)), &Brush,
			ESlateDrawEffect::None, Brush.GetTint(InWidgetStyle) * Tint * Opacity);
	};

	auto Text = [&](const FVector2f& Position, const FString& String, const FSlateFontInfo& Font, const FLinearColor& Color, int32 InLayer)
	{
		FSlateDrawElement::MakeText(OutDrawElements, InLayer, AllottedGeometry.ToPaintGeometry(FVector2f(Size.X, Font.Size * 1.6f), FSlateLayoutTransform(Position)),
			String, Font, ESlateDrawEffect::None, Color * Opacity);
	};

	// Polish (judge "newplayer"): a 2 px line with an ink outline, for the amber gap line
	auto StrokeInk = [&](const TArray<FVector2f>& Points, const FLinearColor& Color, float Thickness, int32 InLayer)
	{
		FSlateDrawElement::MakeLines(OutDrawElements, InLayer, AllottedGeometry.ToPaintGeometry(), Points, ESlateDrawEffect::None,
			InkColor.CopyWithNewOpacity(Color.A) * Opacity, true, Thickness + 2.f);
		FSlateDrawElement::MakeLines(OutDrawElements, InLayer + 1, AllottedGeometry.ToPaintGeometry(), Points, ESlateDrawEffect::None, Color * Opacity, true, Thickness);
	};

	// A tag: paper text on an ink box, centred on X at the top Y
	auto Tag = [&](float CentreX, float TopY, const FString& String, const FSlateFontInfo& Font, float Alpha, int32 InLayer)
	{
		const float TagWidth = MeasureWidthAtScale(String, Font, PaintScale) + 16.f;
		const float TagHeight = Font.Size * 1.75f;
		Box(FVector2f(CentreX - 0.5f * TagWidth, TopY), FVector2f(TagWidth, TagHeight), TagBrush, FLinearColor(1.f, 1.f, 1.f, 0.85f * Alpha), InLayer);
		Text(FVector2f(CentreX - 0.5f * TagWidth + 8.f, TopY + 0.12f * Font.Size), String, Font, PaperColor.CopyWithNewOpacity(Alpha), InLayer + 1);
		return TagWidth;
	};

	// ---- Nose marker: where the bow points, at the crosshair's height (the gap is the turn still to come) ----------------
	// Polish (judge "newplayer"): chevron 18 px (was 10), gap line 2 px amber with an ink outline (was 1 px ink); parked, no
	// turn is coming until a drive / turn key, so no gap line
	if (bNoseOnScreen)
	{
		const FVector2f Nose(NosePosition);

		if (NoseGapDeg > 3.f && !bPFParked)
		{
			StrokeInk({ Nose, Centre }, ReloadColor.CopyWithNewOpacity(FMath::Clamp(NoseGapDeg / 30.f, 0.35f, 0.9f)), 2.f, Layer);
		}

		Stroke({ Nose + FVector2f(-9.f, 7.f), Nose + FVector2f(0.f, -9.f), Nose + FVector2f(9.f, 7.f) }, InkColor, 3.f, Layer + 2);

		if (NoseFlashTime > 0.f)
		{
			Stroke(ArcPoints(Nose, 15.f, 0.f, 360.f, 24), PaperColor.CopyWithNewOpacity(FMath::Clamp(NoseFlashTime / 0.3f, 0.f, 1.f)), 2.f, Layer + 2);
		}
	}

	if (!bPFFreeLook)
	{
		// ---- Steering mode: a "+" at the screen centre (the heading target), 24 px (was 14); parked: faded (free look) ---
		const FLinearColor CrossColor = InkColor.CopyWithNewOpacity(bPFParked ? 0.55f : 1.f);
		Stroke({ Centre + FVector2f(-12.f, 0.f), Centre + FVector2f(12.f, 0.f) }, CrossColor, 2.f, Layer + 2);
		Stroke({ Centre + FVector2f(0.f, -12.f), Centre + FVector2f(0.f, 12.f) }, CrossColor, 2.f, Layer + 2);

		// The contextual look hint (until Aim has been held once this session)
		if (LookHintAlpha > 0.01f)
		{
			Tag(Centre.X, Centre.Y + 34.f, TEXT("HOLD RMB / LB TO LOOK"), SmallFont, LookHintAlpha, Layer + 6);
		}
	}
	else
	{
		// ---- Broadside mode: the gun ring, its brackets, the lock and the heading strip ---------------------------------
		const float RingRadius = 18.f;
		const float Reload = ReloadAlpha[AimSide == EAirshipSide::Port ? 0 : 1];
		const bool bLoaded = Reload >= 1.f;

		if (bFacingInArc)
		{
			Stroke(ArcPoints(Centre, RingRadius, 0.f, 360.f, 32), InkColor, 1.5f, Layer + 2);

			// In the arc and reloading: the ring fills with the reload
			if (!bLoaded && Reload > 0.f)
			{
				FSlateDrawElement::MakeLines(OutDrawElements, Layer + 4, AllottedGeometry.ToPaintGeometry(), ArcPoints(Centre, RingRadius, -90.f, 360.f * Reload, 32),
					ESlateDrawEffect::None, ReloadColor * Opacity, true, 3.f);
			}
		}
		else
		{
			// Out of the arc: dashed
			for (int32 Dash = 0; Dash < 16; ++Dash)
			{
				Stroke(ArcPoints(Centre, RingRadius, 22.5f * static_cast<float>(Dash), 11.25f, 3), InkColor, 1.5f, Layer + 2);
			}
		}

		// In the arc and loaded: amber brackets
		const FLinearColor BracketColor = (bFacingInArc && bLoaded) ? ReloadColor : InkColor;

		for (const float BracketSide : { -1.f, 1.f })
		{
			const float BracketX = Centre.X + BracketSide * (RingRadius + 8.f);
			Stroke({ FVector2f(BracketX - BracketSide * 4.f, Centre.Y - 10.f), FVector2f(BracketX, Centre.Y - 10.f), FVector2f(BracketX, Centre.Y + 10.f),
				FVector2f(BracketX - BracketSide * 4.f, Centre.Y + 10.f) }, BracketColor, 2.f, Layer + 2);
		}

		// The gun lock: a LOCK tag under the ring with an arrow toward the swing (1.5 x, polish)
		if (bPFLock)
		{
			const float TagTop = Centre.Y + RingRadius + 14.f;
			const float TagWidth = Tag(Centre.X, TagTop, TEXT("LOCK"), LockFont, 1.f, Layer + 4);

			if (PFSwingDir != 0)
			{
				const float Dir = static_cast<float>(PFSwingDir);
				const float TipX = Centre.X + Dir * (0.5f * TagWidth + 18.f);
				const float MidY = TagTop + 0.875f * LockFont.Size;
				Stroke({ FVector2f(TipX - Dir * 10.f, MidY - 7.5f), FVector2f(TipX, MidY), FVector2f(TipX - Dir * 10.f, MidY + 7.5f) }, InkColor, 3.f, Layer + 4);
			}
		}

		// The heading strip at the top centre (polish, judge "feel"): +-180 deg around the BOW (the centre mark), 1.5 px per
		// deg, so the aim (55-150 deg off the bow in a broadside) is on it. The guns' arcs (beam +-yaw limit) are thick
		// segments (the facing side amber while it is in arc and loaded), the aim a ring, the heading target a diamond.
		const float PixelsPerDeg = 1.5f;
		const float HalfSpanDeg = 180.f;
		const float StripY = 66.f;
		const float StripX0 = Centre.X - HalfSpanDeg * PixelsPerDeg;
		const float StripX1 = Centre.X + HalfSpanDeg * PixelsPerDeg;
		auto StripX = [&](float RelativeDeg) { return Centre.X + FMath::Clamp(RelativeDeg, -HalfSpanDeg, HalfSpanDeg) * PixelsPerDeg; };

		Stroke({ FVector2f(StripX0, StripY), FVector2f(StripX1, StripY) }, InkColor, 2.f, Layer + 2);

		for (int32 Tick = -6; Tick <= 6; ++Tick)
		{
			const float TickX = Centre.X + 30.f * static_cast<float>(Tick) * PixelsPerDeg;
			const bool bMajor = Tick % 3 == 0;
			Stroke({ FVector2f(TickX, StripY), FVector2f(TickX, StripY + (bMajor ? 12.f : 7.5f)) }, InkColor, 2.f, Layer + 2);
		}

		for (const float BeamDeg : { -90.f, 90.f })
		{
			const bool bFacing = (BeamDeg < 0.f) == (AimSide == EAirshipSide::Port);
			const FLinearColor ArcColor = bFacing ? ((bFacingInArc && bLoaded) ? ReloadColor : InkColor) : InkColor.CopyWithNewOpacity(0.45f);
			Stroke({ FVector2f(StripX(BeamDeg - StripArcDeg), StripY), FVector2f(StripX(BeamDeg + StripArcDeg), StripY) }, ArcColor, 6.f, Layer + 3);
		}

		// The bow: a triangle under the centre
		Stroke({ FVector2f(Centre.X - 7.5f, StripY + 21.f), FVector2f(Centre.X, StripY + 7.5f), FVector2f(Centre.X + 7.5f, StripY + 21.f),
			FVector2f(Centre.X - 7.5f, StripY + 21.f) }, InkColor, 3.f, Layer + 4);

		// The heading target: a diamond above the line
		const float TargetX = StripX(StripTargetDeg);
		const float TargetY = StripY - 13.5f;
		Stroke({ FVector2f(TargetX, TargetY - 9.f), FVector2f(TargetX + 7.5f, TargetY), FVector2f(TargetX, TargetY + 9.f), FVector2f(TargetX - 7.5f, TargetY),
			FVector2f(TargetX, TargetY - 9.f) }, InkColor, 3.f, Layer + 4);

		// The aim: a ring on the line (amber in the arc and loaded)
		Stroke(ArcPoints(FVector2f(StripX(StripAimDeg), StripY), 7.5f, 0.f, 360.f, 16), (bFacingInArc && bLoaded) ? ReloadColor : InkColor, 3.f, Layer + 5);
	}

	// ---- The boarding hint: at least 8 s in Point & Fly and until Aim has been held once (at most 45 s), once per
	// session, fading -------------------------------------------------------------------------------------------------------
	const float HintAlpha = HintAge >= 0.f ? FMath::Clamp((HintEndAge + 1.5f - HintAge) / 1.5f, 0.f, 1.f) : 0.f;

	if (HintAlpha > 0.f)
	{
		const FString Lines[] =
		{
			TEXT("LOOK = STEER  ·  W/S DRIVE  ·  A/D SIDESTEP  ·  Q/E TURN"),
			TEXT("HOLD RMB / LB TO LOOK AROUND OR AIM  ·  X / B IN A TURN: DRIFT")
		};

		for (int32 Row = 0; Row < 2; ++Row)
		{
			const float RowWidth = MeasureWidthAtScale(Lines[Row], SmallFont, PaintScale);
			const FVector2f RowPosition(Centre.X - 0.5f * RowWidth, Size.Y - 130.f + 22.f * static_cast<float>(Row));
			Box(RowPosition - FVector2f(8.f, 2.f), FVector2f(RowWidth + 16.f, 20.f), TagBrush, FLinearColor(1.f, 1.f, 1.f, 0.85f * HintAlpha), Layer + 6);
			Text(RowPosition, Lines[Row], SmallFont, PaperColor.CopyWithNewOpacity(HintAlpha), Layer + 7);
		}
	}

	return Layer + 8;
}

void UAirshipHUDWidget::RefreshCrewValues(const AAirshipPawn* Ship)
{
	if (!Ship)
	{
		return;
	}

	for (int32 TurretIndex = 0; TurretIndex < 2; ++TurretIndex)
	{
		const AAirshipTurret* Turret = Ship->GetTurret(TurretIndex);
		bTurretShown[TurretIndex] = Turret != nullptr;

		if (Turret)
		{
			const float MaxHealth = Turret->GetMaxHealth();
			bTurretWrecked[TurretIndex] = Turret->IsTurretDestroyed();
			bTurretOverheated[TurretIndex] = Turret->IsOverheated();
			TurretHeat[TurretIndex] = Turret->GetHeat01();
			TurretHealthAlpha[TurretIndex] = MaxHealth > 0.f ? FMath::Clamp(Turret->GetHealth() / MaxHealth, 0.f, 1.f) : 0.f;
		}
	}

	MannedMask = 0;

	for (int32 Station = 0; Station < Airship::NumStations; ++Station)
	{
		if (Ship->IsStationManned(Station))
		{
			MannedMask |= 1 << Station;
		}
	}

	bSideManned[0] = Ship->IsSideFullyManned(EAirshipSide::Port);
	bSideManned[1] = Ship->IsSideFullyManned(EAirshipSide::Starboard);

	// The pilot character's own attributes (its ASC is on the PlayerState, replicated to the owner)
	PilotHealth = -1.f;
	PilotHealthAlpha = 0.f;
	const UAbilitySystemComponent* PilotASC = UAbilitySystemGlobals::GetAbilitySystemComponentFromActor(Ship->GetPilot());

	if (PilotASC && PilotASC->HasAttributeSetForAttribute(UMyAttributeSet::GetHealthAttribute()))
	{
		const float MaxHealth = PilotASC->GetNumericAttribute(UMyAttributeSet::GetMaxHealthAttribute());
		PilotHealth = PilotASC->GetNumericAttribute(UMyAttributeSet::GetHealthAttribute());
		PilotHealthAlpha = MaxHealth > 0.f ? FMath::Clamp(PilotHealth / MaxHealth, 0.f, 1.f) : 0.f;
	}
}

void UAirshipHUDWidget::RefreshGunnerValues()
{
	const AAirshipPawn* Ship = Airship.Get();
	const APlayerController* PC = GetOwningPlayer();

	if (!Ship || !Ship->GetHull())
	{
		return;
	}

	const FAirshipFlightTelemetry Telemetry = Ship->GetFlightTelemetry();
	Health = Telemetry.Health;
	HealthAlpha = Telemetry.MaxHealth > 0.f ? FMath::Clamp(Telemetry.Health / Telemetry.MaxHealth, 0.f, 1.f) : 0.f;

	// Where the gun points now (this machine's barrel or turret): a turret 100 m along its barrel, a cannon where its ball
	// would come down at the aim's distance (its arc lifts the barrel above the crosshair)
	FVector From = Ship->GetActorLocation();
	FVector Direction = Ship->GetActorForwardVector();
	FVector MarkPoint = FVector::ZeroVector;
	bool bHasMarkPoint = false;
	const FVector Aim = Ship->GetStationAimPoint(GunnerStation);

	if (Airship::IsCannonStation(GunnerStation))
	{
		const int32 Cannon = GunnerStation;
		const FTransform HullTM = Ship->GetHull()->GetComponentTransform();
		From = HullTM.TransformPosition(Ship->GetCannonMuzzleLocal(Cannon));
		Direction = HullTM.TransformVectorNoScale(Ship->GetCannonDirLocal(Cannon, Ship->GetCannonAimYawDeg(Cannon), Ship->GetCannonAimElevDeg(Cannon)));
		MarkPoint = Ship->GetCannonBallPathPoint(Cannon, Aim);
		bHasMarkPoint = true;
		GunReloadAlpha = Ship->GetCannonReloadAlpha(Cannon);
		GunReloadSeconds = (1.f - GunReloadAlpha) * Ship->GetCannonCooldown();
		bGunInArc = Ship->IsCannonAimInArc(Cannon, Aim);
		bGunReady = GunReloadAlpha >= 1.f;
	}
	else
	{
		const int32 TurretIndex = Airship::StationToTurret(GunnerStation);
		RefreshCrewValues(Ship);

		if (const AAirshipTurret* Turret = Ship->GetTurret(TurretIndex))
		{
			From = Turret->GetMuzzleLocation();
			Direction = Turret->GetBarrelDirection();
			bGunInArc = Turret->IsAimInArc(Aim, 3.f);
			bGunReady = !Turret->IsOverheated() && !Turret->IsTurretDestroyed();
		}
	}

	bGunMarkOnScreen = PC && UWidgetLayoutLibrary::ProjectWorldLocationToWidgetPosition(PC, bHasMarkPoint ? MarkPoint : From + Direction * 10000.0, GunMarkPosition, true);
}

int32 UAirshipHUDWidget::PaintGunner(const FGeometry& AllottedGeometry, FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle) const
{
	using namespace AirshipHUDPrivate;

	const FLinearColor Opacity = InWidgetStyle.GetColorAndOpacityTint();
	const FVector2f Size(AllottedGeometry.GetLocalSize());
	const FVector2f Centre = Size * 0.5f;
	int32 Layer = LayerId + 1;

	const FSlateFontInfo LabelFont = FCoreStyle::GetDefaultFontStyle(TEXT("Black"), 11);
	const FSlateFontInfo ValueFont = FCoreStyle::GetDefaultFontStyle(TEXT("Bold"), 11);
	const FSlateFontInfo SmallFont = FCoreStyle::GetDefaultFontStyle(TEXT("Bold"), 9);

	auto Box = [&](const FVector2f& Position, const FVector2f& BoxSize, const FSlateBrush& Brush, const FLinearColor& Tint, int32 InLayer)
	{
		FSlateDrawElement::MakeBox(OutDrawElements, InLayer, AllottedGeometry.ToPaintGeometry(BoxSize, FSlateLayoutTransform(Position)), &Brush,
			ESlateDrawEffect::None, Brush.GetTint(InWidgetStyle) * Tint * Opacity);
	};

	auto Text = [&](const FVector2f& Position, const FString& String, const FSlateFontInfo& Font, const FLinearColor& Color, int32 InLayer)
	{
		FSlateDrawElement::MakeText(OutDrawElements, InLayer, AllottedGeometry.ToPaintGeometry(FVector2f(Size.X, Font.Size * 1.6f), FSlateLayoutTransform(Position)),
			String, Font, ESlateDrawEffect::None, Color * Opacity);
	};

	// Ink (or amber) with a paper outline, for contrast on sky and platforms
	auto Stroke = [&](const TArray<FVector2f>& Points, const FLinearColor& Color, float Thickness, int32 InLayer)
	{
		FSlateDrawElement::MakeLines(OutDrawElements, InLayer, AllottedGeometry.ToPaintGeometry(), Points, ESlateDrawEffect::None,
			PaperColor.CopyWithNewOpacity(Color.A) * Opacity, true, Thickness + 2.f);
		FSlateDrawElement::MakeLines(OutDrawElements, InLayer + 1, AllottedGeometry.ToPaintGeometry(), Points, ESlateDrawEffect::None, Color * Opacity, true, Thickness);
	};

	auto Bar = [&](const FVector2f& Position, const FVector2f& BarSize, float Alpha, const FLinearColor& Color, int32 InLayer)
	{
		Box(Position, BarSize, TrackBrush, FLinearColor::White, InLayer);
		const float Inset = 3.f;
		const float FillWidth = (BarSize.X - 2.f * Inset) * FMath::Clamp(Alpha, 0.f, 1.f);

		if (FillWidth > 0.5f)
		{
			Box(Position + FVector2f(Inset, Inset), FVector2f(FillWidth, BarSize.Y - 2.f * Inset), FillBrush, Color, InLayer + 1);
		}
	};

	// An ink tag with paper text; returns its width
	auto Tag = [&](const FVector2f& Position, const FString& String, const FSlateFontInfo& Font, int32 InLayer)
	{
		const float TagWidth = MeasureWidth(String, Font) + 10.f;
		Box(Position, FVector2f(TagWidth, Font.Size * 1.6f), TagBrush, FLinearColor::White, InLayer);
		Text(Position + FVector2f(5.f, 0.f), String, Font, PaperColor, InLayer + 1);
		return TagWidth;
	};

	// ---- The crosshair (the camera's aim) and the mark where the gun points now (it slews to the crosshair) -----------
	for (const FVector2f& Arm : { FVector2f(1.f, 0.f), FVector2f(-1.f, 0.f), FVector2f(0.f, 1.f), FVector2f(0.f, -1.f) })
	{
		Stroke({ Centre + Arm * 4.f, Centre + Arm * 12.f }, InkColor, 2.f, Layer);
	}

	if (bGunMarkOnScreen)
	{
		const FLinearColor MarkColor = (bGunReady && bGunInArc) ? ReloadColor : InkColor;
		Stroke(ArcPoints(FVector2f(GunMarkPosition), 9.f, 0.f, 360.f, 20), MarkColor, 2.f, Layer + 2);
	}

	// ---- The panel, bottom-left ----------------------------------------------------------------------------------------
	const float Pad = 12.f;
	const float ShadowOffset = 5.f;
	const FVector2f PanelSizeF(GunnerPanelSize);
	const FVector2f Origin(24.f, Size.Y - 24.f - PanelSizeF.Y);
	const FVector2f Panel(PanelSizeF.X - ShadowOffset, PanelSizeF.Y - ShadowOffset);
	Layer += 4;
	Box(Origin + FVector2f(ShadowOffset, ShadowOffset), Panel, ShadowBrush, FLinearColor::White, Layer);
	++Layer;
	Box(Origin, Panel, PanelBrush, FLinearColor::White, Layer);
	++Layer;

	const float LabelWidth = 58.f;
	const float ValueWidth = 50.f;
	const float BarX = Origin.X + Pad + LabelWidth;
	const float BarWidth = Panel.X - Pad - LabelWidth - ValueWidth - Pad;
	const float BarHeight = 16.f;
	float Y = Origin.Y + Pad;

	// The station and the way out
	Tag(FVector2f(Origin.X + Pad - 4.f, Y - 2.f), GunnerStationLabel(GunnerStation), LabelFont, Layer);
	{
		const FString Leave = TEXT("F  LEAVE");
		Text(FVector2f(Origin.X + Panel.X - Pad - MeasureWidth(Leave, SmallFont), Y + 1.f), Leave, SmallFont, InkColor, Layer);
	}

	Y += 26.f;
	const float ValueX = Origin.X + Panel.X - Pad;

	if (Airship::IsCannonStation(GunnerStation))
	{
		// Reload, then the arc (the crosshair beyond the gun's yaw / elevation limits: it would miss)
		Text(FVector2f(Origin.X + Pad, Y - 1.f), TEXT("LOAD"), LabelFont, InkColor, Layer);
		Bar(FVector2f(BarX, Y), FVector2f(BarWidth, BarHeight), GunReloadAlpha, ReloadColor, Layer);
		const FString Value = bGunReady ? FString(TEXT("READY")) : FString::Printf(TEXT("%.1fs"), GunReloadSeconds);
		Text(FVector2f(ValueX - MeasureWidth(Value, ValueFont), Y - 1.f), Value, ValueFont, InkColor, Layer);

		Y += BarHeight + 8.f;

		if (bGunInArc)
		{
			Text(FVector2f(Origin.X + Pad, Y - 1.f), TEXT("IN ARC"), ValueFont, InkColor, Layer);
		}
		else
		{
			Tag(FVector2f(Origin.X + Pad - 4.f, Y - 2.f), TEXT("OUT OF ARC"), ValueFont, Layer);
		}
	}
	else
	{
		const int32 TurretIndex = FMath::Clamp(Airship::StationToTurret(GunnerStation), 0, 1);

		// Heat (the label is an ink tag while overheated), then the gun's own health
		if (bTurretOverheated[TurretIndex])
		{
			Tag(FVector2f(Origin.X + Pad - 4.f, Y - 2.f), TEXT("OVERHEAT"), SmallFont, Layer);
		}
		else
		{
			Text(FVector2f(Origin.X + Pad, Y - 1.f), TEXT("HEAT"), LabelFont, InkColor, Layer);
		}

		Bar(FVector2f(BarX, Y), FVector2f(BarWidth, BarHeight), TurretHeat[TurretIndex], bTurretOverheated[TurretIndex] ? HullColor : ReloadColor, Layer);
		{
			const FString Value = FString::Printf(TEXT("%d%%"), FMath::RoundToInt(TurretHeat[TurretIndex] * 100.f));
			Text(FVector2f(ValueX - MeasureWidth(Value, ValueFont), Y - 1.f), Value, ValueFont, InkColor, Layer);
		}

		Y += BarHeight + 8.f;
		Text(FVector2f(Origin.X + Pad, Y - 1.f), TEXT("GUN"), LabelFont, InkColor, Layer);
		Bar(FVector2f(BarX, Y), FVector2f(BarWidth, BarHeight), TurretHealthAlpha[TurretIndex], PilotColor, Layer);

		if (bTurretWrecked[TurretIndex])
		{
			Text(FVector2f(ValueX - MeasureWidth(TEXT("WRECK"), ValueFont), Y - 1.f), TEXT("WRECK"), ValueFont, HullColor, Layer);
		}
	}

	// The ship's hull
	Y += BarHeight + 8.f;
	Text(FVector2f(Origin.X + Pad, Y - 1.f), TEXT("HULL"), LabelFont, InkColor, Layer);
	Bar(FVector2f(BarX, Y), FVector2f(BarWidth, BarHeight), HealthAlpha, HullColor, Layer);
	{
		const FString Value = FString::FromInt(FMath::CeilToInt(Health));
		Text(FVector2f(ValueX - MeasureWidth(Value, ValueFont), Y - 1.f), Value, ValueFont, InkColor, Layer);
	}

	return Layer + 3;
}
