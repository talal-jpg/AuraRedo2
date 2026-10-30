// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "MenuButtonFX.generated.h"

class UButton;
class UWidget;
class UWidgetTree;
class UTextBlock;
class UMaterialInstanceDynamic;

/** Tuning for FAuraMenuButtonFX. Same defaults as UMainMenu2's graffiti juice. */
USTRUCT(BlueprintType)
struct FAuraMenuButtonFXSettings
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Aura|Menu|Graffiti")
	float HoverScale = 1.08f;

	// Extra scale velocity added the moment the cursor enters, for the overshoot "pop".
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Aura|Menu|Graffiti")
	float HoverKick = 2.5f;

	// Max resting tilt (degrees) so the buttons look hand-placed.
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Aura|Menu|Graffiti")
	float RestTilt = 3.f;

	// Wobble amplitude (degrees) while hovered.
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Aura|Menu|Graffiti")
	float Wobble = 2.2f;

	// Label colour on top of the neon fill while hovered.
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Aura|Menu|Graffiti")
	FLinearColor HoverTextColor = FLinearColor(0.02f, 0.02f, 0.03f, 1.f);
};

/**
 * UMainMenu2's graffiti hover juice, pulled out so every Menu3 widget can share it.
 * Every button whose parent also holds an Image named "Graffiti_*" pops, tilts and
 * wobbles on hover, squashes on press, and drives the image's "Hovered" material
 * parameter (M_UI_Button). Buttons without a graffiti image are left alone.
 *
 * The owning widget calls Setup() from NativeConstruct and Tick() from NativeTick.
 * Gamepad/keyboard focus counts as hover, so the effect follows menu navigation too.
 */
class AURA_API FAuraMenuButtonFX
{
public:
	void Setup(UWidgetTree* WidgetTree, const FAuraMenuButtonFXSettings& InSettings);
	void Tick(float DeltaTime);
	void Reset();

private:
	struct FButtonState
	{
		TWeakObjectPtr<UButton> Button;
		TWeakObjectPtr<UWidget> Container;
		TWeakObjectPtr<UTextBlock> Label;
		TWeakObjectPtr<UMaterialInstanceDynamic> Material;
		FLinearColor RestTextColor = FLinearColor::White;
		float Hover = 0.f;
		float Press = 0.f;
		float Scale = 1.f;
		float ScaleVelocity = 0.f;
		float RestAngle = 0.f;
		float Seed = 0.f;
		bool bWasHovered = false;
	};

	TArray<FButtonState> Buttons;
	FAuraMenuButtonFXSettings Settings;
	float Time = 0.f;
};

namespace AuraMenu
{
	/**
	 * Gives keyboard/gamepad focus to the first visible, enabled control (button, check box,
	 * slider, combo box, text box) under Root. False if there is none.
	 */
	AURA_API bool FocusFirstControl(UWidget* Root);

	/** True for the keys that mean "back" in every Menu3 widget: Escape, gamepad B / Circle, and the gamepad Special Right (Start) when bIncludeStart. */
	AURA_API bool IsBackKey(const FKey& Key, bool bIncludeStart = false);
}
