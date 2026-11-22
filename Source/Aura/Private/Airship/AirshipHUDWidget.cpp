// Fill out your copyright notice in the Description page of Project Settings.


#include "Airship/AirshipHUDWidget.h"

#include "Airship/AirshipFlightComponent.h"
#include "Airship/AirshipPawn.h"
#include "Fonts/FontMeasure.h"
#include "Framework/Application/SlateApplication.h"
#include "Rendering/DrawElements.h"
#include "Rendering/SlateRenderer.h"
#include "Styling/CoreStyle.h"

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

	// Valid values before the first paint (Slate may paint the new widget before it ticks)
	RefreshValues(0.f, true);
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

	// The ground under the ship: a trace every AltitudeTraceInterval
	AltitudeTimer -= DeltaSeconds;

	if (bForceAltitude || AltitudeTimer <= 0.f)
	{
		AltitudeTimer = AltitudeTraceInterval;
		const float Distance = Ship->TraceGroundDistance(AltitudeTraceLength);
		AltitudeM = Distance >= 0.f ? Distance * 0.01f : -1.f;
	}
}

int32 UAirshipHUDWidget::NativePaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect, FSlateWindowElementList& OutDrawElements,
	int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const
{
	int32 Layer = Super::NativePaint(Args, AllottedGeometry, MyCullingRect, OutDrawElements, LayerId, InWidgetStyle, bParentEnabled);

	if (!Airship.IsValid())
	{
		return Layer;
	}

	using namespace AirshipHUDPrivate;
	const FLinearColor Opacity = InWidgetStyle.GetColorAndOpacityTint();
	const FVector2f Size(AllottedGeometry.GetLocalSize());
	const float Pad = 12.f;
	const float ShadowOffset = 5.f;
	const FVector2f Panel(Size.X - ShadowOffset, Size.Y - ShadowOffset);

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

	// Hull
	float Y = Pad;
	Text(FVector2f(Pad, Y - 1.f), TEXT("HULL"), LabelFont, InkColor, Layer);
	Bar(FVector2f(BarX, Y), FVector2f(BarWidth, BarHeight), HealthAlpha, HullColor, Layer);
	{
		const FString Value = FString::FromInt(FMath::CeilToInt(Health));
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
	const float HalfWidth = (Panel.X - 2.f * Pad) * 0.5f;

	for (int32 Side = 0; Side < 2; ++Side)
	{
		const float X = Pad + HalfWidth * Side;
		const bool bFacing = (Side == 0) == (AimSide == EAirshipSide::Port);
		const TCHAR* Name = Side == 0 ? TEXT("PORT") : TEXT("STBD");
		const float TagWidth = 44.f;

		if (bFacing)
		{
			Box(FVector2f(X - 4.f, Y - 2.f), FVector2f(TagWidth, 18.f), TagBrush, FLinearColor::White, Layer);
		}
		Text(FVector2f(X, Y - 1.f), Name, LabelFont, bFacing ? PaperColor : InkColor, Layer + 1);

		const bool bReady = ReloadAlpha[Side] >= 1.f;
		const FVector2f BarPosition(X + TagWidth + 2.f, Y + 2.f);
		const FVector2f BarSize(HalfWidth - TagWidth - 8.f, 10.f);

		if (bReady)
		{
			Text(BarPosition + FVector2f(0.f, -4.f), TEXT("READY"), ValueFont, InkColor, Layer);
		}
		else
		{
			Bar(BarPosition, BarSize, ReloadAlpha[Side], ReloadColor, Layer);
			Text(BarPosition + FVector2f(0.f, 11.f), FString::Printf(TEXT("%.1fs"), ReloadSeconds[Side]), SmallFont, InkColor, Layer);
		}
	}

	return Layer + 3;
}
