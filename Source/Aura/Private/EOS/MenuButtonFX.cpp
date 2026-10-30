// Fill out your copyright notice in the Description page of Project Settings.

#include "EOS/MenuButtonFX.h"
#include "Blueprint/WidgetTree.h"
#include "Components/Button.h"
#include "Components/CheckBox.h"
#include "Components/ComboBoxString.h"
#include "Components/EditableTextBox.h"
#include "Components/Slider.h"
#include "Components/Image.h"
#include "Components/PanelWidget.h"
#include "Components/TextBlock.h"
#include "Materials/MaterialInstanceDynamic.h"

void FAuraMenuButtonFX::Setup(UWidgetTree* WidgetTree, const FAuraMenuButtonFXSettings& InSettings)
{
	Buttons.Reset();
	Settings = InSettings;

	if (!WidgetTree)
	{
		return;
	}

	int32 Index = 0;
	WidgetTree->ForEachWidget([this, &Index](UWidget* Widget)
	{
		UButton* Button = Cast<UButton>(Widget);
		UPanelWidget* Container = Button ? Button->GetParent() : nullptr;
		if (!Container)
		{
			return;
		}

		FButtonState State;
		for (int32 ChildIndex = 0; ChildIndex < Container->GetChildrenCount(); ++ChildIndex)
		{
			UWidget* Child = Container->GetChildAt(ChildIndex);
			if (UImage* Image = Cast<UImage>(Child))
			{
				if (Image->GetName().StartsWith(TEXT("Graffiti_")))
				{
					State.Material = Image->GetDynamicMaterial();
				}
			}
			else if (UTextBlock* Text = Cast<UTextBlock>(Child))
			{
				State.Label = Text;
				State.RestTextColor = Text->GetColorAndOpacity().GetSpecifiedColor();
			}
		}

		// Only buttons that were given a graffiti backing image take part
		if (!State.Material.IsValid())
		{
			return;
		}

		State.Button = Button;
		State.Container = Container;
		State.Seed = Index * 1.37f;
		// Deterministic "hand placed" tilt, alternating left/right
		State.RestAngle = FMath::Sin(Index * 2.3f + 0.7f) * Settings.RestTilt;
		Container->SetRenderTransformAngle(State.RestAngle);

		Buttons.Add(State);
		++Index;
	});
}

void FAuraMenuButtonFX::Reset()
{
	Buttons.Reset();
}

void FAuraMenuButtonFX::Tick(float DeltaTime)
{
	if (Buttons.Num() == 0)
	{
		return;
	}

	// Keep the spring stable on hitches
	const float Dt = FMath::Min(DeltaTime, 1.f / 30.f);
	Time += Dt;

	for (FButtonState& State : Buttons)
	{
		UButton* Button = State.Button.Get();
		UWidget* Container = State.Container.Get();
		if (!Button || !Container)
		{
			continue;
		}

		const bool bHovered = (Button->IsHovered() || Button->HasKeyboardFocus()) && Button->GetIsEnabled();
		const bool bPressed = Button->IsPressed();

		State.Hover = FMath::FInterpTo(State.Hover, bHovered ? 1.f : 0.f, Dt, 12.f);
		State.Press = FMath::FInterpTo(State.Press, bPressed ? 1.f : 0.f, Dt, 30.f);

		// Kick the spring the moment the cursor arrives so the button overshoots and settles
		if (bHovered && !State.bWasHovered)
		{
			State.ScaleVelocity += Settings.HoverKick;
		}
		State.bWasHovered = bHovered;

		// Damped spring towards the target scale
		const float TargetScale = 1.f + (Settings.HoverScale - 1.f) * State.Hover - 0.07f * State.Press;
		const float Accel = (TargetScale - State.Scale) * 260.f - State.ScaleVelocity * 14.f;
		State.ScaleVelocity += Accel * Dt;
		State.Scale += State.ScaleVelocity * Dt;

		// Hovered: lean into a wobble with a little spray-can jitter. Pressed: squash down.
		const float WobbleAngle = FMath::Sin(Time * 10.f + State.Seed) * Settings.Wobble;
		const float Angle = FMath::Lerp(State.RestAngle, WobbleAngle - 1.5f, State.Hover);
		const FVector2D Jitter(
			FMath::PerlinNoise1D(Time * 14.f + State.Seed),
			FMath::PerlinNoise1D(Time * 14.f + State.Seed + 31.7f));
		const FVector2D Translation = FVector2D(10.f, -4.f) * State.Hover + Jitter * 2.5f * State.Hover + FVector2D(0.f, 3.f) * State.Press;
		const FVector2D Scale(State.Scale * (1.f + 0.04f * State.Press), State.Scale * (1.f - 0.07f * State.Press));
		const FVector2D Shear(-8.f * State.Hover, 0.f);

		Container->SetRenderTransform(FWidgetTransform(Translation, Scale, Shear, Angle));

		if (UMaterialInstanceDynamic* Material = State.Material.Get())
		{
			Material->SetScalarParameterValue(TEXT("Hovered"), State.Hover);
		}

		if (UTextBlock* Label = State.Label.Get())
		{
			// Dark ink on the neon fill, with the drop shadow flipping to white
			Label->SetColorAndOpacity(FSlateColor(FMath::Lerp(State.RestTextColor, Settings.HoverTextColor, State.Hover)));
			Label->SetShadowColorAndOpacity(FMath::Lerp(FLinearColor::Black, FLinearColor::White, State.Hover));
		}
	}
}

namespace AuraMenu
{
	bool FocusFirstControl(UWidget* Root)
	{
		if (!Root)
		{
			return false;
		}

		UWidget* FirstControl = nullptr;
		UWidgetTree::ForWidgetAndChildren(Root, [&FirstControl](UWidget* Widget)
		{
			if (FirstControl || !Widget)
			{
				return;
			}
			const bool bIsControl = Widget->IsA<UButton>() || Widget->IsA<UCheckBox>() || Widget->IsA<USlider>()
				|| Widget->IsA<UComboBoxString>() || Widget->IsA<UEditableTextBox>();
			if (bIsControl && Widget->GetIsEnabled() && Widget->IsVisible())
			{
				FirstControl = Widget;
			}
		});

		if (FirstControl)
		{
			FirstControl->SetFocus();
			return true;
		}
		return false;
	}

	bool IsBackKey(const FKey& Key, bool bIncludeStart)
	{
		return Key == EKeys::Escape
			|| Key == EKeys::Gamepad_FaceButton_Right
			|| (bIncludeStart && Key == EKeys::Gamepad_Special_Right);
	}
}
