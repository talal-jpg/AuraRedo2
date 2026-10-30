// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "UI/UserWidgets/MyUserWidget.h"
#include "EOS/MenuButtonFX.h"
#include "UI/Settings/MyGameUserSettings.h"
#include "UserSettings/EnhancedInputUserSettings.h"
#include "Types/SlateEnums.h"
#include "SettingsMenu3.generated.h"

class UButton;
class UCheckBox;
class UComboBoxString;
class UPanelWidget;
class USlider;
class UTextBlock;
class UWidget;
class UWidgetSwitcher;
class UKeyBindingRow3;

DECLARE_DYNAMIC_MULTICAST_DELEGATE(FOnSettingsMenu3Closed);

/**
 * The Options screen, shared by UMainMenu3 and UPauseMenu3 (place a WBP of this class as
 * their OptionsPanel). Tabs follow the UMainMenu2 widget-switcher convention: a
 * UWidgetSwitcher "SettingsSwitcher" with VideoTab / AudioTab / ControlsTab / GameplayTab /
 * AccessibilityTab, each opened by its *TabButton. LB / RB switch tabs on a gamepad.
 *
 * Every control applies the moment it changes (live preview). Window mode and resolution
 * apply too but ask "Keep these display settings?" with a countdown, and revert on timeout.
 * Closing saves GameUserSettings.ini and the key bindings.
 *
 * All bindings are optional: leave out what you don't want and the rest still works.
 */
UCLASS()
class AURA_API USettingsMenu3 : public UMyUserWidget
{
	GENERATED_BODY()

public:
	/** Fills every control from the saved settings and opens the first tab. Call each time the panel is shown. */
	UFUNCTION(BlueprintCallable, Category = "Aura|Settings")
	void OpenSettings();

	/** Reverts an unconfirmed display change, saves everything, then fires OnClosed. */
	UFUNCTION(BlueprintCallable, Category = "Aura|Settings")
	void CloseSettings();

	/** Esc / B: dismisses the display confirm first, otherwise closes. Always handled. */
	bool HandleBack();

	UPROPERTY(BlueprintAssignable, Category = "Aura|Settings")
	FOnSettingsMenu3Closed OnClosed;

	// Called by UKeyBindingRow3
	void RebindKey(FName MappingName, EPlayerMappableKeySlot Slot, const FKey& NewKey);
	void ResetKeyRow(FName MappingName);

protected:
	virtual bool Initialize() override;
	virtual void NativeConstruct() override;
	virtual void NativeTick(const FGeometry& MyGeometry, float InDeltaTime) override;
	virtual void NativeDestruct() override;
	virtual FReply NativeOnKeyDown(const FGeometry& InGeometry, const FKeyEvent& InKeyEvent) override;

	UPROPERTY(EditAnywhere, Category = "Aura|Menu|Graffiti")
	FAuraMenuButtonFXSettings ButtonFX;

	// Seconds the "Keep these display settings?" prompt waits before reverting.
	UPROPERTY(EditAnywhere, Category = "Aura|Settings", meta = (ClampMin = "3.0"))
	float DisplayConfirmSeconds = 15.f;

	// Choices of the FPS limit box. 0 = unlimited.
	UPROPERTY(EditAnywhere, Category = "Aura|Settings")
	TArray<int32> FrameRateLimits = { 30, 60, 90, 120, 144, 165, 240, 0 };

	// One row per rebindable action in the Controls tab.
	UPROPERTY(EditDefaultsOnly, Category = "Aura|Settings")
	TSubclassOf<UKeyBindingRow3> KeyBindingRowClass;

	// Blueprint hook to restyle the tab buttons. 0 Video, 1 Audio, 2 Controls, 3 Gameplay, 4 Accessibility.
	UFUNCTION(BlueprintImplementableEvent, Category = "Aura|Settings")
	void OnTabChanged(int32 TabIndex);

private:
	UMyGameUserSettings* GetSettings() const;
	UEnhancedInputUserSettings* GetInputUserSettings() const;

	//
	// Tabs
	//
	void ShowTab(int32 TabIndex);
	TArray<UWidget*> GetTabs() const;
	TArray<UButton*> GetTabButtons() const;
	// Bumpers / Q-E style tab cycling, wraps around
	void CycleTab(int32 Direction);
	int32 CurrentTab{ 0 };

	UFUNCTION()
	void VideoTabClicked();
	UFUNCTION()
	void AudioTabClicked();
	UFUNCTION()
	void ControlsTabClicked();
	UFUNCTION()
	void GameplayTabClicked();
	UFUNCTION()
	void AccessibilityTabClicked();
	UFUNCTION()
	void ResetTabClicked();
	UFUNCTION()
	void SettingsBackClicked();

	UPROPERTY(meta = (BindWidgetOptional))
	UWidgetSwitcher* SettingsSwitcher;
	UPROPERTY(meta = (BindWidgetOptional))
	UWidget* VideoTab;
	UPROPERTY(meta = (BindWidgetOptional))
	UWidget* AudioTab;
	UPROPERTY(meta = (BindWidgetOptional))
	UWidget* ControlsTab;
	UPROPERTY(meta = (BindWidgetOptional))
	UWidget* GameplayTab;
	UPROPERTY(meta = (BindWidgetOptional))
	UWidget* AccessibilityTab;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* VideoTabButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* AudioTabButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* ControlsTabButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* GameplayTabButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* AccessibilityTabButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* ResetTabButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* SettingsBackButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* SettingsHintText;

	//
	// Video
	//
	UPROPERTY(meta = (BindWidgetOptional))
	UComboBoxString* WindowModeComboBox;
	UPROPERTY(meta = (BindWidgetOptional))
	UComboBoxString* ResolutionComboBox;
	UPROPERTY(meta = (BindWidgetOptional))
	USlider* RenderScaleSlider;
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* RenderScaleText;
	UPROPERTY(meta = (BindWidgetOptional))
	UComboBoxString* QualityPresetComboBox;
	UPROPERTY(meta = (BindWidgetOptional))
	UComboBoxString* ViewDistanceQualityComboBox;
	UPROPERTY(meta = (BindWidgetOptional))
	UComboBoxString* AntiAliasingQualityComboBox;
	UPROPERTY(meta = (BindWidgetOptional))
	UComboBoxString* ShadowQualityComboBox;
	UPROPERTY(meta = (BindWidgetOptional))
	UComboBoxString* GlobalIlluminationQualityComboBox;
	UPROPERTY(meta = (BindWidgetOptional))
	UComboBoxString* ReflectionQualityComboBox;
	UPROPERTY(meta = (BindWidgetOptional))
	UComboBoxString* PostProcessQualityComboBox;
	UPROPERTY(meta = (BindWidgetOptional))
	UComboBoxString* TextureQualityComboBox;
	UPROPERTY(meta = (BindWidgetOptional))
	UComboBoxString* EffectsQualityComboBox;
	UPROPERTY(meta = (BindWidgetOptional))
	UComboBoxString* FoliageQualityComboBox;
	UPROPERTY(meta = (BindWidgetOptional))
	UComboBoxString* ShadingQualityComboBox;
	UPROPERTY(meta = (BindWidgetOptional))
	UComboBoxString* FrameRateLimitComboBox;
	UPROPERTY(meta = (BindWidgetOptional))
	UComboBoxString* AntiAliasingMethodComboBox;
	UPROPERTY(meta = (BindWidgetOptional))
	UCheckBox* VSyncCheckBox;
	UPROPERTY(meta = (BindWidgetOptional))
	UCheckBox* HDRCheckBox;
	UPROPERTY(meta = (BindWidgetOptional))
	UCheckBox* MotionBlurCheckBox;
	UPROPERTY(meta = (BindWidgetOptional))
	UCheckBox* LumenCheckBox;
	UPROPERTY(meta = (BindWidgetOptional))
	USlider* GammaSlider;
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* GammaText;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* AutoDetectButton;

	// "Keep these display settings?" overlay
	UPROPERTY(meta = (BindWidgetOptional))
	UWidget* DisplayConfirmPanel;
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* DisplayConfirmText;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* KeepDisplayButton;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* RevertDisplayButton;

	UFUNCTION()
	void OnDisplayModeChanged(FString SelectedItem, ESelectInfo::Type SelectionType);
	UFUNCTION()
	void OnResolutionChanged(FString SelectedItem, ESelectInfo::Type SelectionType);
	UFUNCTION()
	void OnQualityPresetChanged(FString SelectedItem, ESelectInfo::Type SelectionType);
	UFUNCTION()
	void OnVideoComboChanged(FString SelectedItem, ESelectInfo::Type SelectionType);
	UFUNCTION()
	void OnVideoSliderChanged(float Value);
	UFUNCTION()
	void OnVideoCheckChanged(bool bIsChecked);
	UFUNCTION()
	void OnHDRChanged(bool bIsChecked);
	UFUNCTION()
	void AutoDetectClicked();
	UFUNCTION()
	void KeepDisplayClicked();
	UFUNCTION()
	void RevertDisplayClicked();

	void ReadVideoControls();
	void ApplyVideoNow();
	void ApplyDisplayChange();
	void RefreshResolutionOptions();
	void StartDisplayConfirm();
	void EndDisplayConfirm(bool bKeep);

	TArray<FIntPoint> ResolutionOptions;
	TArray<EWindowMode::Type> WindowModeOptions;
	bool bDisplayConfirmPending{ false };
	float DisplayConfirmRemaining{ 0.f };

	//
	// Audio
	//
	UPROPERTY(meta = (BindWidgetOptional))
	USlider* MasterVolumeSlider;
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* MasterVolumeText;
	UPROPERTY(meta = (BindWidgetOptional))
	USlider* MusicVolumeSlider;
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* MusicVolumeText;
	UPROPERTY(meta = (BindWidgetOptional))
	USlider* EffectsVolumeSlider;
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* EffectsVolumeText;
	UPROPERTY(meta = (BindWidgetOptional))
	USlider* VoiceVolumeSlider;
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* VoiceVolumeText;
	UPROPERTY(meta = (BindWidgetOptional))
	USlider* InterfaceVolumeSlider;
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* InterfaceVolumeText;
	UPROPERTY(meta = (BindWidgetOptional))
	UCheckBox* MuteWhenUnfocusedCheckBox;

	UFUNCTION()
	void OnAudioSliderChanged(float Value);
	UFUNCTION()
	void OnAudioCheckChanged(bool bIsChecked);
	void ReadAudioControls();

	//
	// Controls
	//
	UPROPERTY(meta = (BindWidgetOptional))
	USlider* LookSensitivitySlider;
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* LookSensitivityText;
	UPROPERTY(meta = (BindWidgetOptional))
	UCheckBox* InvertLookYCheckBox;
	UPROPERTY(meta = (BindWidgetOptional))
	UCheckBox* InvertLookXCheckBox;
	UPROPERTY(meta = (BindWidgetOptional))
	UPanelWidget* KeyBindingList;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* ResetKeyBindingsButton;

	UFUNCTION()
	void OnControlsSliderChanged(float Value);
	UFUNCTION()
	void OnControlsCheckChanged(bool bIsChecked);
	UFUNCTION()
	void ResetKeyBindingsClicked();
	void ReadControlsControls();
	void RebuildKeyBindingRows();
	void RefreshKeyBindingRows();
	void ResetAllKeyBindings();

	UPROPERTY()
	TArray<UKeyBindingRow3*> KeyBindingRows;
	bool bKeyBindingsChanged{ false };

	//
	// Gameplay
	//
	UPROPERTY(meta = (BindWidgetOptional))
	USlider* FieldOfViewSlider;
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* FieldOfViewText;
	UPROPERTY(meta = (BindWidgetOptional))
	UCheckBox* ShowDamageNumbersCheckBox;
	UPROPERTY(meta = (BindWidgetOptional))
	UComboBoxString* LanguageComboBox;

	UFUNCTION()
	void OnGameplaySliderChanged(float Value);
	UFUNCTION()
	void OnGameplayCheckChanged(bool bIsChecked);
	UFUNCTION()
	void OnLanguageChanged(FString SelectedItem, ESelectInfo::Type SelectionType);
	void ReadGameplayControls();

	TArray<FString> LanguageCultures;

	//
	// Accessibility
	//
	UPROPERTY(meta = (BindWidgetOptional))
	UCheckBox* ScreenShakeCheckBox;
	UPROPERTY(meta = (BindWidgetOptional))
	UCheckBox* ScreenFlashesCheckBox;
	UPROPERTY(meta = (BindWidgetOptional))
	UCheckBox* SubtitlesCheckBox;
	UPROPERTY(meta = (BindWidgetOptional))
	UComboBoxString* ColorBlindModeComboBox;
	UPROPERTY(meta = (BindWidgetOptional))
	USlider* ColorBlindStrengthSlider;
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* ColorBlindStrengthText;
	UPROPERTY(meta = (BindWidgetOptional))
	USlider* UIScaleSlider;
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* UIScaleText;

	UFUNCTION()
	void OnAccessibilityComboChanged(FString SelectedItem, ESelectInfo::Type SelectionType);
	UFUNCTION()
	void OnAccessibilitySliderChanged(float Value);
	UFUNCTION()
	void OnAccessibilityCheckChanged(bool bIsChecked);
	void ReadAccessibilityControls();
	void ApplyAccessibilityNow();

	//
	// Shared
	//
	void FillStaticOptions();
	void RefreshControls();
	void RefreshValueTexts();
	void SetHint(const FText& Hint);
	TArray<UComboBoxString*> GetQualityComboBoxes() const;

	// Sliders fire every frame while dragged, so their settings are applied once the slider rests for SliderApplyDelay
	void FlushPendingApplies();
	float PendingVideoApplyDelay{ 0.f };
	float PendingAccessibilityApplyDelay{ 0.f };

	// Set while RefreshControls() writes into the widgets, so the change handlers ignore it
	bool bRefreshingControls{ false };
	bool bStaticOptionsFilled{ false };

	FAuraMenuButtonFX ButtonFXState;
};
