// Fill out your copyright notice in the Description page of Project Settings.

#include "UI/Settings/SettingsMenu3.h"
#include "UI/Settings/KeyBindingRow3.h"
#include "UI/Settings/MyMenuSettings.h"
#include "Components/Button.h"
#include "Components/CheckBox.h"
#include "Components/ComboBoxString.h"
#include "Components/PanelWidget.h"
#include "Components/Slider.h"
#include "Components/TextBlock.h"
#include "Components/WidgetSwitcher.h"
#include "Engine/Engine.h"
#include "Engine/LocalPlayer.h"
#include "EnhancedInputSubsystems.h"
#include "GameFramework/PlayerController.h"
#include "InputMappingContext.h"
#include "Kismet/KismetInternationalizationLibrary.h"
#include "Kismet/KismetSystemLibrary.h"

#define LOCTEXT_NAMESPACE "SettingsMenu3"

namespace
{
	constexpr int32 NumQualityLevels = 5;
	constexpr int32 NumTabs = 5;
	// A slider change is applied once it has been still this long, so dragging doesn't
	// re-apply every scalability cvar (or re-layout the whole UI) each frame
	constexpr float SliderApplyDelay = 0.25f;

	FText QualityLevelName(int32 Level)
	{
		switch (Level)
		{
		case 0: return LOCTEXT("QualityLow", "Low");
		case 1: return LOCTEXT("QualityMedium", "Medium");
		case 2: return LOCTEXT("QualityHigh", "High");
		case 3: return LOCTEXT("QualityEpic", "Epic");
		default: return LOCTEXT("QualityCinematic", "Cinematic");
		}
	}

	void SelectComboIndex(UComboBoxString* Combo, int32 Index)
	{
		if (Combo && Index >= 0 && Index < Combo->GetOptionCount())
		{
			Combo->SetSelectedIndex(Index);
		}
	}

	FText PercentText(float Fraction)
	{
		return FText::FromString(FString::Printf(TEXT("%d%%"), FMath::RoundToInt(Fraction * 100.f)));
	}
}

bool USettingsMenu3::Initialize()
{
	if (!Super::Initialize())
	{
		return false;
	}

	// Tabs
	if (VideoTabButton)         VideoTabButton->OnClicked.AddDynamic(this, &ThisClass::VideoTabClicked);
	if (AudioTabButton)         AudioTabButton->OnClicked.AddDynamic(this, &ThisClass::AudioTabClicked);
	if (ControlsTabButton)      ControlsTabButton->OnClicked.AddDynamic(this, &ThisClass::ControlsTabClicked);
	if (GameplayTabButton)      GameplayTabButton->OnClicked.AddDynamic(this, &ThisClass::GameplayTabClicked);
	if (AccessibilityTabButton) AccessibilityTabButton->OnClicked.AddDynamic(this, &ThisClass::AccessibilityTabClicked);
	if (ResetTabButton)         ResetTabButton->OnClicked.AddDynamic(this, &ThisClass::ResetTabClicked);
	if (SettingsBackButton)     SettingsBackButton->OnClicked.AddDynamic(this, &ThisClass::SettingsBackClicked);

	// Video
	if (WindowModeComboBox)    WindowModeComboBox->OnSelectionChanged.AddDynamic(this, &ThisClass::OnDisplayModeChanged);
	if (ResolutionComboBox)    ResolutionComboBox->OnSelectionChanged.AddDynamic(this, &ThisClass::OnResolutionChanged);
	if (QualityPresetComboBox) QualityPresetComboBox->OnSelectionChanged.AddDynamic(this, &ThisClass::OnQualityPresetChanged);
	for (UComboBoxString* Combo : GetQualityComboBoxes())
	{
		if (Combo) Combo->OnSelectionChanged.AddDynamic(this, &ThisClass::OnVideoComboChanged);
	}
	if (FrameRateLimitComboBox)     FrameRateLimitComboBox->OnSelectionChanged.AddDynamic(this, &ThisClass::OnVideoComboChanged);
	if (AntiAliasingMethodComboBox) AntiAliasingMethodComboBox->OnSelectionChanged.AddDynamic(this, &ThisClass::OnVideoComboChanged);
	if (RenderScaleSlider) RenderScaleSlider->OnValueChanged.AddDynamic(this, &ThisClass::OnVideoSliderChanged);
	if (GammaSlider)       GammaSlider->OnValueChanged.AddDynamic(this, &ThisClass::OnVideoSliderChanged);
	for (UCheckBox* Box : { VSyncCheckBox, MotionBlurCheckBox, LumenCheckBox })
	{
		if (Box) Box->OnCheckStateChanged.AddDynamic(this, &ThisClass::OnVideoCheckChanged);
	}
	if (HDRCheckBox)         HDRCheckBox->OnCheckStateChanged.AddDynamic(this, &ThisClass::OnHDRChanged);
	if (AutoDetectButton)    AutoDetectButton->OnClicked.AddDynamic(this, &ThisClass::AutoDetectClicked);
	if (KeepDisplayButton)   KeepDisplayButton->OnClicked.AddDynamic(this, &ThisClass::KeepDisplayClicked);
	if (RevertDisplayButton) RevertDisplayButton->OnClicked.AddDynamic(this, &ThisClass::RevertDisplayClicked);

	// Audio
	for (USlider* Slider : { MasterVolumeSlider, MusicVolumeSlider, EffectsVolumeSlider, VoiceVolumeSlider, InterfaceVolumeSlider })
	{
		if (Slider) Slider->OnValueChanged.AddDynamic(this, &ThisClass::OnAudioSliderChanged);
	}
	if (MuteWhenUnfocusedCheckBox) MuteWhenUnfocusedCheckBox->OnCheckStateChanged.AddDynamic(this, &ThisClass::OnAudioCheckChanged);

	// Controls
	if (LookSensitivitySlider)  LookSensitivitySlider->OnValueChanged.AddDynamic(this, &ThisClass::OnControlsSliderChanged);
	if (InvertLookYCheckBox)    InvertLookYCheckBox->OnCheckStateChanged.AddDynamic(this, &ThisClass::OnControlsCheckChanged);
	if (InvertLookXCheckBox)    InvertLookXCheckBox->OnCheckStateChanged.AddDynamic(this, &ThisClass::OnControlsCheckChanged);
	if (ResetKeyBindingsButton) ResetKeyBindingsButton->OnClicked.AddDynamic(this, &ThisClass::ResetKeyBindingsClicked);

	// Gameplay
	if (FieldOfViewSlider)         FieldOfViewSlider->OnValueChanged.AddDynamic(this, &ThisClass::OnGameplaySliderChanged);
	if (ShowDamageNumbersCheckBox) ShowDamageNumbersCheckBox->OnCheckStateChanged.AddDynamic(this, &ThisClass::OnGameplayCheckChanged);
	if (LanguageComboBox)          LanguageComboBox->OnSelectionChanged.AddDynamic(this, &ThisClass::OnLanguageChanged);

	// Accessibility
	for (UCheckBox* Box : { ScreenShakeCheckBox, ScreenFlashesCheckBox, SubtitlesCheckBox })
	{
		if (Box) Box->OnCheckStateChanged.AddDynamic(this, &ThisClass::OnAccessibilityCheckChanged);
	}
	if (ColorBlindModeComboBox)   ColorBlindModeComboBox->OnSelectionChanged.AddDynamic(this, &ThisClass::OnAccessibilityComboChanged);
	if (ColorBlindStrengthSlider) ColorBlindStrengthSlider->OnValueChanged.AddDynamic(this, &ThisClass::OnAccessibilitySliderChanged);
	if (UIScaleSlider)            UIScaleSlider->OnValueChanged.AddDynamic(this, &ThisClass::OnAccessibilitySliderChanged);

	return true;
}

void USettingsMenu3::NativeConstruct()
{
	Super::NativeConstruct();

	ButtonFXState.Setup(WidgetTree, ButtonFX);

	if (DisplayConfirmPanel)
	{
		DisplayConfirmPanel->SetVisibility(ESlateVisibility::Collapsed);
	}
}

void USettingsMenu3::NativeTick(const FGeometry& MyGeometry, float InDeltaTime)
{
	Super::NativeTick(MyGeometry, InDeltaTime);

	ButtonFXState.Tick(InDeltaTime);

	// Debounced slider applies
	if (PendingVideoApplyDelay > 0.f)
	{
		PendingVideoApplyDelay -= InDeltaTime;
		if (PendingVideoApplyDelay <= 0.f)
		{
			ApplyVideoNow();
		}
	}
	if (PendingAccessibilityApplyDelay > 0.f)
	{
		PendingAccessibilityApplyDelay -= InDeltaTime;
		if (PendingAccessibilityApplyDelay <= 0.f)
		{
			ApplyAccessibilityNow();
		}
	}

	// "Keep these display settings?" countdown. Widget time, so it still runs if the game is paused.
	if (bDisplayConfirmPending)
	{
		DisplayConfirmRemaining -= InDeltaTime;
		if (DisplayConfirmRemaining <= 0.f)
		{
			EndDisplayConfirm(false);
		}
		else if (DisplayConfirmText)
		{
			DisplayConfirmText->SetText(FText::Format(
				LOCTEXT("DisplayConfirm", "Keep these display settings? Reverting in {0}s."),
				FText::AsNumber(FMath::CeilToInt(DisplayConfirmRemaining))));
		}
	}
}

void USettingsMenu3::NativeDestruct()
{
	ButtonFXState.Reset();

	// Leaving the menu without closing it (level change): never keep an unconfirmed display mode
	if (bDisplayConfirmPending)
	{
		EndDisplayConfirm(false);
	}
	FlushPendingApplies();

	Super::NativeDestruct();
}

FReply USettingsMenu3::NativeOnKeyDown(const FGeometry& InGeometry, const FKeyEvent& InKeyEvent)
{
	const FKey Key = InKeyEvent.GetKey();

	if (Key == EKeys::Gamepad_LeftShoulder)
	{
		CycleTab(-1);
		return FReply::Handled();
	}
	if (Key == EKeys::Gamepad_RightShoulder)
	{
		CycleTab(1);
		return FReply::Handled();
	}
	if (AuraMenu::IsBackKey(Key))
	{
		HandleBack();
		return FReply::Handled();
	}

	return Super::NativeOnKeyDown(InGeometry, InKeyEvent);
}

//
// Open / close
//
void USettingsMenu3::OpenSettings()
{
	FillStaticOptions();
	RebuildKeyBindingRows();
	RefreshControls();
	SetHint(GetSettings() ? FText::GetEmpty() : LOCTEXT("NoSettingsClass", "GameUserSettingsClassName isn't UMyGameUserSettings - changes won't be saved."));

	// The first tab the layout has
	const TArray<UWidget*> Tabs = GetTabs();
	ShowTab(Tabs.IndexOfByPredicate([](const UWidget* Tab) { return Tab != nullptr; }));
}

void USettingsMenu3::CloseSettings()
{
	if (bDisplayConfirmPending)
	{
		EndDisplayConfirm(false);
	}
	FlushPendingApplies();

	if (UMyGameUserSettings* Settings = GetSettings())
	{
		Settings->SaveSettings();
	}

	if (bKeyBindingsChanged)
	{
		bKeyBindingsChanged = false;
		if (UEnhancedInputUserSettings* UserSettings = GetInputUserSettings())
		{
			UserSettings->SaveSettings();
		}
	}

	OnClosed.Broadcast();
}

bool USettingsMenu3::HandleBack()
{
	if (bDisplayConfirmPending)
	{
		EndDisplayConfirm(false);
		return true;
	}

	CloseSettings();
	return true;
}

UMyGameUserSettings* USettingsMenu3::GetSettings() const
{
	return UMyGameUserSettings::GetMyGameUserSettings();
}

UEnhancedInputUserSettings* USettingsMenu3::GetInputUserSettings() const
{
	const APlayerController* PlayerController = GetOwningPlayer();
	const ULocalPlayer* LocalPlayer = PlayerController ? PlayerController->GetLocalPlayer() : nullptr;
	UEnhancedInputLocalPlayerSubsystem* InputSubsystem = LocalPlayer ? LocalPlayer->GetSubsystem<UEnhancedInputLocalPlayerSubsystem>() : nullptr;
	return InputSubsystem ? InputSubsystem->GetUserSettings() : nullptr;
}

//
// Tabs
//
TArray<UWidget*> USettingsMenu3::GetTabs() const
{
	return { VideoTab, AudioTab, ControlsTab, GameplayTab, AccessibilityTab };
}

TArray<UButton*> USettingsMenu3::GetTabButtons() const
{
	return { VideoTabButton, AudioTabButton, ControlsTabButton, GameplayTabButton, AccessibilityTabButton };
}

void USettingsMenu3::ShowTab(int32 TabIndex)
{
	const TArray<UWidget*> Tabs = GetTabs();
	// A tab left out of the layout can't open, and must not collapse the ones that are there
	if (!Tabs.IsValidIndex(TabIndex) || !Tabs[TabIndex])
	{
		return;
	}

	CurrentTab = TabIndex;
	UWidget* Tab = Tabs[TabIndex];

	if (SettingsSwitcher)
	{
		SettingsSwitcher->SetActiveWidget(Tab);
	}
	else
	{
		// Same fallback as UMainMenu2::ShowPanel for layouts without a switcher
		for (UWidget* Other : Tabs)
		{
			if (Other)
			{
				Other->SetVisibility(Other == Tab ? ESlateVisibility::Visible : ESlateVisibility::Collapsed);
			}
		}
	}

	// The open tab's button is disabled, which doubles as the "selected" look
	const TArray<UButton*> TabButtons = GetTabButtons();
	for (int32 Index = 0; Index < TabButtons.Num(); ++Index)
	{
		if (TabButtons[Index])
		{
			TabButtons[Index]->SetIsEnabled(Index != TabIndex);
		}
	}

	OnTabChanged(TabIndex);
	AuraMenu::FocusFirstControl(Tab);
}

void USettingsMenu3::CycleTab(int32 Direction)
{
	const TArray<UWidget*> Tabs = GetTabs();
	for (int32 Step = 1; Step <= NumTabs; ++Step)
	{
		const int32 Candidate = (CurrentTab + Direction * Step + NumTabs * Step) % NumTabs;
		if (Tabs[Candidate])
		{
			ShowTab(Candidate);
			return;
		}
	}
}

void USettingsMenu3::VideoTabClicked()         { ShowTab(0); }
void USettingsMenu3::AudioTabClicked()         { ShowTab(1); }
void USettingsMenu3::ControlsTabClicked()      { ShowTab(2); }
void USettingsMenu3::GameplayTabClicked()      { ShowTab(3); }
void USettingsMenu3::AccessibilityTabClicked() { ShowTab(4); }

void USettingsMenu3::SettingsBackClicked()
{
	HandleBack();
}

void USettingsMenu3::ResetTabClicked()
{
	UMyGameUserSettings* Settings = GetSettings();
	if (!Settings)
	{
		return;
	}

	// Tab order matches EAuraSettingsGroup
	const EAuraSettingsGroup Group = static_cast<EAuraSettingsGroup>(FMath::Clamp(CurrentTab, 0, NumTabs - 1));
	Settings->ResetGroupToDefaults(Group);

	switch (Group)
	{
	case EAuraSettingsGroup::Video:
		Settings->ApplyNonResolutionSettings();
		if (Settings->GetScreenResolution() != Settings->GetLastConfirmedScreenResolution()
			|| Settings->GetFullscreenMode() != Settings->GetLastConfirmedFullscreenMode())
		{
			ApplyDisplayChange();
		}
		break;
	case EAuraSettingsGroup::Audio:
		Settings->ApplyAudioSettings(this);
		break;
	case EAuraSettingsGroup::Controls:
		ResetAllKeyBindings();
		break;
	case EAuraSettingsGroup::Gameplay:
		Settings->OnAuraSettingsChanged.Broadcast(Settings);
		break;
	case EAuraSettingsGroup::Accessibility:
		ApplyAccessibilityNow();
		break;
	}

	RefreshControls();
	SetHint(LOCTEXT("TabReset", "Defaults restored."));
}

//
// Video
//
void USettingsMenu3::OnDisplayModeChanged(FString SelectedItem, ESelectInfo::Type SelectionType)
{
	UMyGameUserSettings* Settings = GetSettings();
	if (bRefreshingControls || !Settings || !WindowModeComboBox)
	{
		return;
	}

	const int32 Index = WindowModeComboBox->GetSelectedIndex();
	if (!WindowModeOptions.IsValidIndex(Index))
	{
		return;
	}

	const EWindowMode::Type NewMode = WindowModeOptions[Index];
	Settings->SetFullscreenMode(NewMode);
	if (NewMode == EWindowMode::WindowedFullscreen)
	{
		// Borderless always covers the monitor
		Settings->SetScreenResolution(Settings->GetDesktopResolution());
	}

	{
		TGuardValue<bool> RefreshGuard(bRefreshingControls, true);
		RefreshResolutionOptions();
	}
	ApplyDisplayChange();
}

void USettingsMenu3::OnResolutionChanged(FString SelectedItem, ESelectInfo::Type SelectionType)
{
	UMyGameUserSettings* Settings = GetSettings();
	if (bRefreshingControls || !Settings || !ResolutionComboBox)
	{
		return;
	}

	const int32 Index = ResolutionComboBox->GetSelectedIndex();
	if (!ResolutionOptions.IsValidIndex(Index))
	{
		return;
	}

	Settings->SetScreenResolution(ResolutionOptions[Index]);
	ApplyDisplayChange();
}

void USettingsMenu3::OnQualityPresetChanged(FString SelectedItem, ESelectInfo::Type SelectionType)
{
	UMyGameUserSettings* Settings = GetSettings();
	if (bRefreshingControls || !Settings || !QualityPresetComboBox)
	{
		return;
	}

	const int32 Index = QualityPresetComboBox->GetSelectedIndex();
	if (Index >= 0 && Index < NumQualityLevels)
	{
		Settings->SetOverallScalabilityLevel(Index);
		Settings->ApplyNonResolutionSettings();
	}
	// "Custom" isn't a preset to pick; RefreshControls snaps the box back to what's applied
	RefreshControls();
}

void USettingsMenu3::OnVideoComboChanged(FString SelectedItem, ESelectInfo::Type SelectionType)
{
	if (bRefreshingControls)
	{
		return;
	}

	ReadVideoControls();
	ApplyVideoNow();
}

void USettingsMenu3::OnVideoSliderChanged(float Value)
{
	if (bRefreshingControls)
	{
		return;
	}

	ReadVideoControls();

	// Gamma is cheap and the point of the slider is seeing it move
	if (const UMyGameUserSettings* Settings = GetSettings())
	{
		if (GEngine)
		{
			GEngine->DisplayGamma = Settings->GetGamma();
		}
	}
	RefreshValueTexts();
	PendingVideoApplyDelay = SliderApplyDelay;
}

void USettingsMenu3::OnVideoCheckChanged(bool bIsChecked)
{
	if (bRefreshingControls)
	{
		return;
	}

	ReadVideoControls();
	ApplyVideoNow();
}

void USettingsMenu3::OnHDRChanged(bool bIsChecked)
{
	UMyGameUserSettings* Settings = GetSettings();
	if (bRefreshingControls || !Settings)
	{
		return;
	}

	if (Settings->SupportsHDRDisplayOutput())
	{
		Settings->EnableHDRDisplayOutput(bIsChecked);
	}
	RefreshControls();
}

void USettingsMenu3::ReadVideoControls()
{
	UMyGameUserSettings* Settings = GetSettings();
	if (!Settings)
	{
		return;
	}

	const TArray<UComboBoxString*> QualityBoxes = GetQualityComboBoxes();
	auto ReadQuality = [&QualityBoxes](int32 BoxIndex, int32 CurrentValue)
	{
		const UComboBoxString* Combo = QualityBoxes[BoxIndex];
		const int32 Selected = Combo ? Combo->GetSelectedIndex() : INDEX_NONE;
		return (Selected >= 0 && Selected < NumQualityLevels) ? Selected : CurrentValue;
	};
	Settings->SetViewDistanceQuality(ReadQuality(0, Settings->GetViewDistanceQuality()));
	Settings->SetAntiAliasingQuality(ReadQuality(1, Settings->GetAntiAliasingQuality()));
	Settings->SetShadowQuality(ReadQuality(2, Settings->GetShadowQuality()));
	Settings->SetGlobalIlluminationQuality(ReadQuality(3, Settings->GetGlobalIlluminationQuality()));
	Settings->SetReflectionQuality(ReadQuality(4, Settings->GetReflectionQuality()));
	Settings->SetPostProcessingQuality(ReadQuality(5, Settings->GetPostProcessingQuality()));
	Settings->SetTextureQuality(ReadQuality(6, Settings->GetTextureQuality()));
	Settings->SetVisualEffectQuality(ReadQuality(7, Settings->GetVisualEffectQuality()));
	Settings->SetFoliageQuality(ReadQuality(8, Settings->GetFoliageQuality()));
	Settings->SetShadingQuality(ReadQuality(9, Settings->GetShadingQuality()));

	if (FrameRateLimitComboBox && FrameRateLimits.IsValidIndex(FrameRateLimitComboBox->GetSelectedIndex()))
	{
		Settings->SetFrameRateLimit(static_cast<float>(FrameRateLimits[FrameRateLimitComboBox->GetSelectedIndex()]));
	}
	if (AntiAliasingMethodComboBox && AntiAliasingMethodComboBox->GetSelectedIndex() >= 0)
	{
		Settings->SetAntiAliasingMethod(static_cast<EAuraAntiAliasingMethod>(AntiAliasingMethodComboBox->GetSelectedIndex()));
	}
	if (RenderScaleSlider)  Settings->SetResolutionScaleNormalized(RenderScaleSlider->GetValue());
	if (GammaSlider)        Settings->SetGamma(GammaSlider->GetValue());
	if (VSyncCheckBox)      Settings->SetVSyncEnabled(VSyncCheckBox->IsChecked());
	if (MotionBlurCheckBox) Settings->SetMotionBlurEnabled(MotionBlurCheckBox->IsChecked());
	if (LumenCheckBox)      Settings->SetLumenEnabled(LumenCheckBox->IsChecked());
}

void USettingsMenu3::ApplyVideoNow()
{
	PendingVideoApplyDelay = 0.f;

	if (UMyGameUserSettings* Settings = GetSettings())
	{
		Settings->ApplyNonResolutionSettings();
	}

	// The preset box may have turned into "Custom"
	RefreshControls();
}

void USettingsMenu3::AutoDetectClicked()
{
	UMyGameUserSettings* Settings = GetSettings();
	if (!Settings)
	{
		return;
	}

	SetHint(LOCTEXT("Benchmarking", "Measuring your hardware..."));
	Settings->RunHardwareBenchmark();
	Settings->ApplyHardwareBenchmarkResults();
	RefreshControls();
	SetHint(LOCTEXT("BenchmarkDone", "Quality set for your hardware."));
}

void USettingsMenu3::ApplyDisplayChange()
{
	UMyGameUserSettings* Settings = GetSettings();
	if (!Settings)
	{
		return;
	}

	Settings->ApplyResolutionSettings(false);
	StartDisplayConfirm();
}

void USettingsMenu3::StartDisplayConfirm()
{
	if (!DisplayConfirmPanel)
	{
		// No prompt in this layout: keep the change straight away
		EndDisplayConfirm(true);
		return;
	}

	bDisplayConfirmPending = true;
	DisplayConfirmRemaining = DisplayConfirmSeconds;
	DisplayConfirmPanel->SetVisibility(ESlateVisibility::Visible);
	if (KeepDisplayButton)
	{
		KeepDisplayButton->SetFocus();
	}
}

void USettingsMenu3::EndDisplayConfirm(bool bKeep)
{
	bDisplayConfirmPending = false;
	if (DisplayConfirmPanel)
	{
		DisplayConfirmPanel->SetVisibility(ESlateVisibility::Collapsed);
	}

	UMyGameUserSettings* Settings = GetSettings();
	if (!Settings)
	{
		return;
	}

	if (bKeep)
	{
		Settings->ConfirmVideoMode();
		Settings->SaveSettings();
	}
	else
	{
		Settings->RevertVideoMode();
		Settings->ApplyResolutionSettings(false);
	}

	{
		TGuardValue<bool> RefreshGuard(bRefreshingControls, true);
		RefreshResolutionOptions();
	}
	RefreshControls();
}

void USettingsMenu3::KeepDisplayClicked()
{
	EndDisplayConfirm(true);
}

void USettingsMenu3::RevertDisplayClicked()
{
	EndDisplayConfirm(false);
}

void USettingsMenu3::RefreshResolutionOptions()
{
	UMyGameUserSettings* Settings = GetSettings();
	if (!ResolutionComboBox || !Settings)
	{
		return;
	}

	ResolutionOptions.Reset();
	const EWindowMode::Type Mode = Settings->GetFullscreenMode();
	if (Mode == EWindowMode::Fullscreen)
	{
		UKismetSystemLibrary::GetSupportedFullscreenResolutions(ResolutionOptions);
	}
	else
	{
		UKismetSystemLibrary::GetConvenientWindowedResolutions(ResolutionOptions);
	}

	const FIntPoint Current = Settings->GetScreenResolution();
	ResolutionOptions.AddUnique(Current);
	ResolutionOptions.Sort([](const FIntPoint& A, const FIntPoint& B)
	{
		return A.X != B.X ? A.X < B.X : A.Y < B.Y;
	});

	ResolutionComboBox->ClearOptions();
	for (const FIntPoint& Resolution : ResolutionOptions)
	{
		ResolutionComboBox->AddOption(FString::Printf(TEXT("%d x %d"), Resolution.X, Resolution.Y));
	}
	SelectComboIndex(ResolutionComboBox, ResolutionOptions.IndexOfByKey(Current));

	// Borderless is always the monitor's own resolution
	ResolutionComboBox->SetIsEnabled(Mode != EWindowMode::WindowedFullscreen);
}

//
// Audio
//
void USettingsMenu3::OnAudioSliderChanged(float Value)
{
	if (bRefreshingControls)
	{
		return;
	}

	ReadAudioControls();
}

void USettingsMenu3::OnAudioCheckChanged(bool bIsChecked)
{
	if (bRefreshingControls)
	{
		return;
	}

	ReadAudioControls();
}

void USettingsMenu3::ReadAudioControls()
{
	UMyGameUserSettings* Settings = GetSettings();
	if (!Settings)
	{
		return;
	}

	if (MasterVolumeSlider)    Settings->SetVolume(EAuraVolumeChannel::Master, MasterVolumeSlider->GetValue());
	if (MusicVolumeSlider)     Settings->SetVolume(EAuraVolumeChannel::Music, MusicVolumeSlider->GetValue());
	if (EffectsVolumeSlider)   Settings->SetVolume(EAuraVolumeChannel::Effects, EffectsVolumeSlider->GetValue());
	if (VoiceVolumeSlider)     Settings->SetVolume(EAuraVolumeChannel::Voice, VoiceVolumeSlider->GetValue());
	if (InterfaceVolumeSlider) Settings->SetVolume(EAuraVolumeChannel::Interface, InterfaceVolumeSlider->GetValue());
	if (MuteWhenUnfocusedCheckBox) Settings->SetMuteWhenUnfocused(MuteWhenUnfocusedCheckBox->IsChecked());

	// Cheap, so live while dragging
	Settings->ApplyAudioSettings(this);
	RefreshValueTexts();
}

//
// Controls
//
void USettingsMenu3::OnControlsSliderChanged(float Value)
{
	if (bRefreshingControls)
	{
		return;
	}

	ReadControlsControls();
}

void USettingsMenu3::OnControlsCheckChanged(bool bIsChecked)
{
	if (bRefreshingControls)
	{
		return;
	}

	ReadControlsControls();
}

void USettingsMenu3::ReadControlsControls()
{
	UMyGameUserSettings* Settings = GetSettings();
	if (!Settings)
	{
		return;
	}

	// Read live by AMyPlayerController2::Rotate, nothing to apply
	if (LookSensitivitySlider) Settings->SetLookSensitivity(LookSensitivitySlider->GetValue());
	if (InvertLookYCheckBox)   Settings->SetInvertLookY(InvertLookYCheckBox->IsChecked());
	if (InvertLookXCheckBox)   Settings->SetInvertLookX(InvertLookXCheckBox->IsChecked());
	RefreshValueTexts();
}

void USettingsMenu3::ResetKeyBindingsClicked()
{
	ResetAllKeyBindings();
	SetHint(LOCTEXT("KeysReset", "Key bindings restored to defaults."));
}

void USettingsMenu3::RebuildKeyBindingRows()
{
	if (!KeyBindingList)
	{
		return;
	}

	KeyBindingList->ClearChildren();
	KeyBindingRows.Reset();

	UEnhancedInputUserSettings* UserSettings = GetInputUserSettings();
	if (!UserSettings)
	{
		SetHint(LOCTEXT("NoInputUserSettings", "Key rebinding needs Enhanced Input user settings (Project Settings > Enhanced Input > Enable User Settings)."));
		return;
	}
	if (!KeyBindingRowClass)
	{
		return;
	}

	// The main menu has no gameplay controller that added these, so register them here
	for (const TSoftObjectPtr<UInputMappingContext>& ContextPtr : GetDefault<UMyMenuSettings>()->RebindableMappingContexts)
	{
		if (const UInputMappingContext* Context = ContextPtr.LoadSynchronous())
		{
			UserSettings->RegisterInputMappingContext(Context);
		}
	}

	const UEnhancedPlayerMappableKeyProfile* Profile = UserSettings->GetActiveKeyProfile();
	if (!Profile)
	{
		return;
	}

	struct FRowEntry
	{
		FName MappingName;
		FText DisplayName;
		FText Category;
	};

	TArray<FRowEntry> Entries;
	for (const TPair<FName, FKeyMappingRow>& Pair : Profile->GetPlayerMappingRows())
	{
		if (!Pair.Value.HasAnyMappings())
		{
			continue;
		}

		FRowEntry Entry;
		Entry.MappingName = Pair.Key;
		// Name and category come from the row's first mapping
		if (TSet<FPlayerKeyMapping>::TConstIterator FirstMapping = Pair.Value.Mappings.CreateConstIterator())
		{
			Entry.DisplayName = FirstMapping->GetDisplayName();
			Entry.Category = FirstMapping->GetDisplayCategory();
		}
		if (Entry.DisplayName.IsEmpty())
		{
			Entry.DisplayName = FText::FromName(Pair.Key);
		}
		Entries.Add(Entry);
	}

	// Grouped by category, alphabetical inside
	Entries.Sort([](const FRowEntry& A, const FRowEntry& B)
	{
		const int32 CategoryOrder = A.Category.CompareTo(B.Category);
		return CategoryOrder != 0 ? CategoryOrder < 0 : A.DisplayName.CompareTo(B.DisplayName) < 0;
	});

	for (const FRowEntry& Entry : Entries)
	{
		if (UKeyBindingRow3* Row = CreateWidget<UKeyBindingRow3>(this, KeyBindingRowClass))
		{
			Row->Setup(this, Entry.MappingName, Entry.DisplayName, Entry.Category);
			KeyBindingList->AddChild(Row);
			KeyBindingRows.Add(Row);
		}
	}

	if (Entries.Num() == 0)
	{
		SetHint(LOCTEXT("NoMappableKeys", "No rebindable actions: give the Input Actions Player Mappable Key Settings and list their IMC in Project Settings > Aura Menu."));
	}

	RefreshKeyBindingRows();
}

void USettingsMenu3::RefreshKeyBindingRows()
{
	UEnhancedInputUserSettings* UserSettings = GetInputUserSettings();
	const UEnhancedPlayerMappableKeyProfile* Profile = UserSettings ? UserSettings->GetActiveKeyProfile() : nullptr;
	if (!Profile)
	{
		return;
	}

	for (UKeyBindingRow3* Row : KeyBindingRows)
	{
		if (!Row)
		{
			continue;
		}
		if (const FKeyMappingRow* MappingRow = Profile->GetPlayerMappingRows().Find(Row->GetMappingName()))
		{
			Row->Refresh(*MappingRow);
		}
	}
}

void USettingsMenu3::RebindKey(FName MappingName, EPlayerMappableKeySlot KeySlot, const FKey& NewKey)
{
	UEnhancedInputUserSettings* UserSettings = GetInputUserSettings();
	if (!UserSettings)
	{
		return;
	}

	FMapPlayerKeyArgs Args;
	Args.MappingName = MappingName;
	Args.Slot = KeySlot;
	Args.NewKey = NewKey;

	FGameplayTagContainer FailureReason;
	UserSettings->MapPlayerKey(Args, FailureReason);
	if (!FailureReason.IsEmpty())
	{
		SetHint(FText::FromString(FailureReason.ToStringSimple()));
	}

	UserSettings->ApplySettings();
	bKeyBindingsChanged = true;
	RefreshKeyBindingRows();
}

void USettingsMenu3::ResetKeyRow(FName MappingName)
{
	UEnhancedInputUserSettings* UserSettings = GetInputUserSettings();
	if (!UserSettings)
	{
		return;
	}

	FMapPlayerKeyArgs Args;
	Args.MappingName = MappingName;

	FGameplayTagContainer FailureReason;
	UserSettings->ResetAllPlayerKeysInRow(Args, FailureReason);

	UserSettings->ApplySettings();
	bKeyBindingsChanged = true;
	RefreshKeyBindingRows();
}

void USettingsMenu3::ResetAllKeyBindings()
{
	UEnhancedInputUserSettings* UserSettings = GetInputUserSettings();
	const UEnhancedPlayerMappableKeyProfile* Profile = UserSettings ? UserSettings->GetActiveKeyProfile() : nullptr;
	if (!Profile)
	{
		return;
	}

	// Copy the names first: resetting edits the rows we'd be iterating
	TArray<FName> MappingNames;
	Profile->GetPlayerMappingRows().GetKeys(MappingNames);

	for (const FName& Name : MappingNames)
	{
		FMapPlayerKeyArgs Args;
		Args.MappingName = Name;
		FGameplayTagContainer FailureReason;
		UserSettings->ResetAllPlayerKeysInRow(Args, FailureReason);
	}

	UserSettings->ApplySettings();
	bKeyBindingsChanged = true;
	RefreshKeyBindingRows();
}

//
// Gameplay
//
void USettingsMenu3::OnGameplaySliderChanged(float Value)
{
	if (bRefreshingControls)
	{
		return;
	}

	ReadGameplayControls();
}

void USettingsMenu3::OnGameplayCheckChanged(bool bIsChecked)
{
	if (bRefreshingControls)
	{
		return;
	}

	ReadGameplayControls();
}

void USettingsMenu3::ReadGameplayControls()
{
	UMyGameUserSettings* Settings = GetSettings();
	if (!Settings)
	{
		return;
	}

	// FOV and damage numbers are read live by AMyPlayerController2
	if (FieldOfViewSlider)         Settings->SetFieldOfView(FieldOfViewSlider->GetValue());
	if (ShowDamageNumbersCheckBox) Settings->SetShowDamageNumbers(ShowDamageNumbersCheckBox->IsChecked());
	Settings->OnAuraSettingsChanged.Broadcast(Settings);
	RefreshValueTexts();
}

void USettingsMenu3::OnLanguageChanged(FString SelectedItem, ESelectInfo::Type SelectionType)
{
	if (bRefreshingControls || !LanguageComboBox)
	{
		return;
	}

	const int32 Index = LanguageComboBox->GetSelectedIndex();
	if (!LanguageCultures.IsValidIndex(Index))
	{
		return;
	}

	// Saved to GameUserSettings.ini [Internationalization]
	UKismetInternationalizationLibrary::SetCurrentCulture(LanguageCultures[Index], true);

	// Re-fill the boxes so their labels come back in the new language
	bStaticOptionsFilled = false;
	FillStaticOptions();
	{
		TGuardValue<bool> RefreshGuard(bRefreshingControls, true);
		RefreshResolutionOptions();
	}
	RefreshControls();
}

//
// Accessibility
//
void USettingsMenu3::OnAccessibilityComboChanged(FString SelectedItem, ESelectInfo::Type SelectionType)
{
	if (bRefreshingControls)
	{
		return;
	}

	ReadAccessibilityControls();
	ApplyAccessibilityNow();

	// Strength means nothing with the mode off
	UMyGameUserSettings* Settings = GetSettings();
	if (ColorBlindStrengthSlider && Settings)
	{
		ColorBlindStrengthSlider->SetIsEnabled(Settings->GetColorBlindMode() != EAuraColorBlindMode::Off);
	}
}

void USettingsMenu3::OnAccessibilitySliderChanged(float Value)
{
	if (bRefreshingControls)
	{
		return;
	}

	// UI scale re-lays out every widget, including the slider being dragged: apply once it settles
	ReadAccessibilityControls();
	RefreshValueTexts();
	PendingAccessibilityApplyDelay = SliderApplyDelay;
}

void USettingsMenu3::OnAccessibilityCheckChanged(bool bIsChecked)
{
	if (bRefreshingControls)
	{
		return;
	}

	ReadAccessibilityControls();
	ApplyAccessibilityNow();
}

void USettingsMenu3::ReadAccessibilityControls()
{
	UMyGameUserSettings* Settings = GetSettings();
	if (!Settings)
	{
		return;
	}

	if (ScreenShakeCheckBox)   Settings->SetScreenShakeEnabled(ScreenShakeCheckBox->IsChecked());
	if (ScreenFlashesCheckBox) Settings->SetScreenFlashesEnabled(ScreenFlashesCheckBox->IsChecked());
	if (SubtitlesCheckBox)     Settings->SetSubtitlesEnabled(SubtitlesCheckBox->IsChecked());
	if (ColorBlindModeComboBox && ColorBlindModeComboBox->GetSelectedIndex() >= 0)
	{
		Settings->SetColorBlindMode(static_cast<EAuraColorBlindMode>(ColorBlindModeComboBox->GetSelectedIndex()));
	}
	if (ColorBlindStrengthSlider) Settings->SetColorBlindStrength(FMath::RoundToInt(ColorBlindStrengthSlider->GetValue()));
	if (UIScaleSlider)            Settings->SetUIScale(UIScaleSlider->GetValue());
}

void USettingsMenu3::ApplyAccessibilityNow()
{
	PendingAccessibilityApplyDelay = 0.f;

	if (UMyGameUserSettings* Settings = GetSettings())
	{
		Settings->ApplyRenderingAndAccessibilitySettings();
		Settings->OnAuraSettingsChanged.Broadcast(Settings);
	}
	RefreshValueTexts();
}

void USettingsMenu3::FlushPendingApplies()
{
	if (PendingVideoApplyDelay > 0.f)
	{
		ApplyVideoNow();
	}
	if (PendingAccessibilityApplyDelay > 0.f)
	{
		ApplyAccessibilityNow();
	}
}

//
// Shared
//
TArray<UComboBoxString*> USettingsMenu3::GetQualityComboBoxes() const
{
	// Order matters: ReadVideoControls / RefreshControls index into it
	return {
		ViewDistanceQualityComboBox, AntiAliasingQualityComboBox, ShadowQualityComboBox,
		GlobalIlluminationQualityComboBox, ReflectionQualityComboBox, PostProcessQualityComboBox,
		TextureQualityComboBox, EffectsQualityComboBox, FoliageQualityComboBox, ShadingQualityComboBox
	};
}

void USettingsMenu3::FillStaticOptions()
{
	if (bStaticOptionsFilled)
	{
		return;
	}
	bStaticOptionsFilled = true;

	TGuardValue<bool> RefreshGuard(bRefreshingControls, true);

	WindowModeOptions = { EWindowMode::Fullscreen, EWindowMode::WindowedFullscreen, EWindowMode::Windowed };
	if (WindowModeComboBox)
	{
		WindowModeComboBox->ClearOptions();
		WindowModeComboBox->AddOption(LOCTEXT("Fullscreen", "Fullscreen").ToString());
		WindowModeComboBox->AddOption(LOCTEXT("Borderless", "Borderless").ToString());
		WindowModeComboBox->AddOption(LOCTEXT("Windowed", "Windowed").ToString());
	}

	for (UComboBoxString* Combo : GetQualityComboBoxes())
	{
		if (Combo)
		{
			Combo->ClearOptions();
			for (int32 Level = 0; Level < NumQualityLevels; ++Level)
			{
				Combo->AddOption(QualityLevelName(Level).ToString());
			}
		}
	}
	if (QualityPresetComboBox)
	{
		QualityPresetComboBox->ClearOptions();
		for (int32 Level = 0; Level < NumQualityLevels; ++Level)
		{
			QualityPresetComboBox->AddOption(QualityLevelName(Level).ToString());
		}
		QualityPresetComboBox->AddOption(LOCTEXT("QualityCustom", "Custom").ToString());
	}

	if (FrameRateLimitComboBox)
	{
		FrameRateLimitComboBox->ClearOptions();
		for (const int32 Limit : FrameRateLimits)
		{
			FrameRateLimitComboBox->AddOption(Limit > 0 ? FString::FromInt(Limit) : LOCTEXT("Unlimited", "Unlimited").ToString());
		}
	}

	// Same order as EAuraAntiAliasingMethod
	if (AntiAliasingMethodComboBox)
	{
		AntiAliasingMethodComboBox->ClearOptions();
		AntiAliasingMethodComboBox->AddOption(LOCTEXT("AAOff", "Off").ToString());
		AntiAliasingMethodComboBox->AddOption(TEXT("FXAA"));
		AntiAliasingMethodComboBox->AddOption(TEXT("TAA"));
		AntiAliasingMethodComboBox->AddOption(LOCTEXT("AATSR", "TSR (upscaler)").ToString());
	}

	// Same order as EAuraColorBlindMode
	if (ColorBlindModeComboBox)
	{
		ColorBlindModeComboBox->ClearOptions();
		ColorBlindModeComboBox->AddOption(LOCTEXT("ColorBlindOff", "Off").ToString());
		ColorBlindModeComboBox->AddOption(LOCTEXT("Deuteranope", "Deuteranope (green-weak)").ToString());
		ColorBlindModeComboBox->AddOption(LOCTEXT("Protanope", "Protanope (red-weak)").ToString());
		ColorBlindModeComboBox->AddOption(LOCTEXT("Tritanope", "Tritanope (blue-weak)").ToString());
	}

	if (LanguageComboBox)
	{
		LanguageCultures = UKismetInternationalizationLibrary::GetLocalizedCultures(true, false, false, false);
		const FString CurrentCulture = UKismetInternationalizationLibrary::GetCurrentCulture();
		if (LanguageCultures.Num() == 0)
		{
			LanguageCultures.Add(CurrentCulture);
		}

		LanguageComboBox->ClearOptions();
		for (const FString& Culture : LanguageCultures)
		{
			// Each language named in itself, like most games do
			LanguageComboBox->AddOption(UKismetInternationalizationLibrary::GetCultureDisplayName(Culture, false));
		}
		LanguageComboBox->SetIsEnabled(LanguageCultures.Num() > 1);
	}

	// Slider ranges
	if (RenderScaleSlider)
	{
		RenderScaleSlider->SetMinValue(0.f);
		RenderScaleSlider->SetMaxValue(1.f);
		RenderScaleSlider->SetStepSize(0.01f);
	}
	if (GammaSlider)
	{
		GammaSlider->SetMinValue(UMyGameUserSettings::MinGamma);
		GammaSlider->SetMaxValue(UMyGameUserSettings::MaxGamma);
		GammaSlider->SetStepSize(0.05f);
	}
	for (USlider* Slider : { MasterVolumeSlider, MusicVolumeSlider, EffectsVolumeSlider, VoiceVolumeSlider, InterfaceVolumeSlider })
	{
		if (Slider)
		{
			Slider->SetMinValue(0.f);
			Slider->SetMaxValue(1.f);
			Slider->SetStepSize(0.01f);
		}
	}
	if (LookSensitivitySlider)
	{
		LookSensitivitySlider->SetMinValue(UMyGameUserSettings::MinLookSensitivity);
		LookSensitivitySlider->SetMaxValue(UMyGameUserSettings::MaxLookSensitivity);
		LookSensitivitySlider->SetStepSize(0.05f);
	}
	if (FieldOfViewSlider)
	{
		FieldOfViewSlider->SetMinValue(UMyGameUserSettings::MinFieldOfView);
		FieldOfViewSlider->SetMaxValue(UMyGameUserSettings::MaxFieldOfView);
		FieldOfViewSlider->SetStepSize(1.f);
	}
	if (ColorBlindStrengthSlider)
	{
		ColorBlindStrengthSlider->SetMinValue(0.f);
		ColorBlindStrengthSlider->SetMaxValue(10.f);
		ColorBlindStrengthSlider->SetStepSize(1.f);
	}
	if (UIScaleSlider)
	{
		UIScaleSlider->SetMinValue(UMyGameUserSettings::MinUIScale);
		UIScaleSlider->SetMaxValue(UMyGameUserSettings::MaxUIScale);
		UIScaleSlider->SetStepSize(0.05f);
	}
}

void USettingsMenu3::RefreshControls()
{
	UMyGameUserSettings* Settings = GetSettings();
	if (!Settings)
	{
		return;
	}

	TGuardValue<bool> RefreshGuard(bRefreshingControls, true);

	//
	// Video
	//
	SelectComboIndex(WindowModeComboBox, WindowModeOptions.IndexOfByKey(Settings->GetFullscreenMode()));
	if (ResolutionComboBox)
	{
		if (ResolutionOptions.Num() == 0)
		{
			RefreshResolutionOptions();
		}
		SelectComboIndex(ResolutionComboBox, ResolutionOptions.IndexOfByKey(Settings->GetScreenResolution()));
	}

	if (RenderScaleSlider)
	{
		RenderScaleSlider->SetValue(Settings->GetResolutionScaleNormalized());
	}

	// -1 = the groups don't share one level
	const int32 OverallLevel = Settings->GetOverallScalabilityLevel();
	SelectComboIndex(QualityPresetComboBox, OverallLevel >= 0 ? OverallLevel : NumQualityLevels);

	const TArray<UComboBoxString*> QualityBoxes = GetQualityComboBoxes();
	const int32 QualityLevels[] = {
		Settings->GetViewDistanceQuality(), Settings->GetAntiAliasingQuality(), Settings->GetShadowQuality(),
		Settings->GetGlobalIlluminationQuality(), Settings->GetReflectionQuality(), Settings->GetPostProcessingQuality(),
		Settings->GetTextureQuality(), Settings->GetVisualEffectQuality(), Settings->GetFoliageQuality(), Settings->GetShadingQuality()
	};
	for (int32 Index = 0; Index < QualityBoxes.Num(); ++Index)
	{
		SelectComboIndex(QualityBoxes[Index], FMath::Clamp(QualityLevels[Index], 0, NumQualityLevels - 1));
	}

	SelectComboIndex(FrameRateLimitComboBox, FrameRateLimits.IndexOfByKey(FMath::RoundToInt(Settings->GetFrameRateLimit())));
	SelectComboIndex(AntiAliasingMethodComboBox, static_cast<int32>(Settings->GetAntiAliasingMethod()));

	if (VSyncCheckBox) VSyncCheckBox->SetIsChecked(Settings->IsVSyncEnabled());
	if (HDRCheckBox)
	{
		HDRCheckBox->SetIsChecked(Settings->IsHDREnabled());
		HDRCheckBox->SetIsEnabled(Settings->SupportsHDRDisplayOutput());
	}
	if (MotionBlurCheckBox) MotionBlurCheckBox->SetIsChecked(Settings->GetMotionBlurEnabled());
	if (LumenCheckBox)      LumenCheckBox->SetIsChecked(Settings->GetLumenEnabled());
	if (GammaSlider)        GammaSlider->SetValue(Settings->GetGamma());

	//
	// Audio
	//
	if (MasterVolumeSlider)    MasterVolumeSlider->SetValue(Settings->GetVolume(EAuraVolumeChannel::Master));
	if (MusicVolumeSlider)     MusicVolumeSlider->SetValue(Settings->GetVolume(EAuraVolumeChannel::Music));
	if (EffectsVolumeSlider)   EffectsVolumeSlider->SetValue(Settings->GetVolume(EAuraVolumeChannel::Effects));
	if (VoiceVolumeSlider)     VoiceVolumeSlider->SetValue(Settings->GetVolume(EAuraVolumeChannel::Voice));
	if (InterfaceVolumeSlider) InterfaceVolumeSlider->SetValue(Settings->GetVolume(EAuraVolumeChannel::Interface));
	if (MuteWhenUnfocusedCheckBox) MuteWhenUnfocusedCheckBox->SetIsChecked(Settings->GetMuteWhenUnfocused());

	//
	// Controls
	//
	if (LookSensitivitySlider) LookSensitivitySlider->SetValue(Settings->GetLookSensitivity());
	if (InvertLookYCheckBox)   InvertLookYCheckBox->SetIsChecked(Settings->GetInvertLookY());
	if (InvertLookXCheckBox)   InvertLookXCheckBox->SetIsChecked(Settings->GetInvertLookX());
	RefreshKeyBindingRows();

	//
	// Gameplay
	//
	if (FieldOfViewSlider)         FieldOfViewSlider->SetValue(Settings->GetFieldOfView());
	if (ShowDamageNumbersCheckBox) ShowDamageNumbersCheckBox->SetIsChecked(Settings->GetShowDamageNumbers());
	if (LanguageComboBox)
	{
		// Exact culture first ("en-US"), then the same language ("en")
		const FString Current = UKismetInternationalizationLibrary::GetCurrentCulture();
		int32 CultureIndex = LanguageCultures.IndexOfByKey(Current);
		if (CultureIndex == INDEX_NONE)
		{
			FString Language = Current;
			Current.Split(TEXT("-"), &Language, nullptr);
			CultureIndex = LanguageCultures.IndexOfByPredicate([&Language](const FString& Culture)
			{
				return Culture.Equals(Language, ESearchCase::IgnoreCase) || Culture.StartsWith(Language + TEXT("-"), ESearchCase::IgnoreCase);
			});
		}
		SelectComboIndex(LanguageComboBox, CultureIndex);
	}

	//
	// Accessibility
	//
	if (ScreenShakeCheckBox)   ScreenShakeCheckBox->SetIsChecked(Settings->GetScreenShakeEnabled());
	if (ScreenFlashesCheckBox) ScreenFlashesCheckBox->SetIsChecked(Settings->GetScreenFlashesEnabled());
	if (SubtitlesCheckBox)     SubtitlesCheckBox->SetIsChecked(Settings->GetSubtitlesEnabled());
	SelectComboIndex(ColorBlindModeComboBox, static_cast<int32>(Settings->GetColorBlindMode()));
	if (ColorBlindStrengthSlider)
	{
		ColorBlindStrengthSlider->SetValue(static_cast<float>(Settings->GetColorBlindStrength()));
		ColorBlindStrengthSlider->SetIsEnabled(Settings->GetColorBlindMode() != EAuraColorBlindMode::Off);
	}
	if (UIScaleSlider) UIScaleSlider->SetValue(Settings->GetUIScale());

	RefreshValueTexts();
}

void USettingsMenu3::RefreshValueTexts()
{
	const UMyGameUserSettings* Settings = GetSettings();
	if (!Settings)
	{
		return;
	}

	if (RenderScaleText)
	{
		float CurrentNormalized = 0.f, CurrentValue = 100.f, MinValue = 0.f, MaxValue = 100.f;
		Settings->GetResolutionScaleInformationEx(CurrentNormalized, CurrentValue, MinValue, MaxValue);
		// Show what the slider says right now, even before the debounced apply
		const float SliderValue = RenderScaleSlider ? FMath::Lerp(MinValue, MaxValue, RenderScaleSlider->GetValue()) : CurrentValue;
		RenderScaleText->SetText(FText::FromString(FString::Printf(TEXT("%d%%"), FMath::RoundToInt(SliderValue))));
	}
	if (GammaText)
	{
		GammaText->SetText(FText::AsNumber(Settings->GetGamma(), &FNumberFormattingOptions::DefaultNoGrouping()));
	}

	if (MasterVolumeText)    MasterVolumeText->SetText(PercentText(Settings->GetVolume(EAuraVolumeChannel::Master)));
	if (MusicVolumeText)     MusicVolumeText->SetText(PercentText(Settings->GetVolume(EAuraVolumeChannel::Music)));
	if (EffectsVolumeText)   EffectsVolumeText->SetText(PercentText(Settings->GetVolume(EAuraVolumeChannel::Effects)));
	if (VoiceVolumeText)     VoiceVolumeText->SetText(PercentText(Settings->GetVolume(EAuraVolumeChannel::Voice)));
	if (InterfaceVolumeText) InterfaceVolumeText->SetText(PercentText(Settings->GetVolume(EAuraVolumeChannel::Interface)));

	if (LookSensitivityText)
	{
		LookSensitivityText->SetText(FText::FromString(FString::Printf(TEXT("%.2f"), Settings->GetLookSensitivity())));
	}
	if (FieldOfViewText)
	{
		FieldOfViewText->SetText(FText::AsNumber(FMath::RoundToInt(Settings->GetFieldOfView())));
	}
	if (ColorBlindStrengthText)
	{
		ColorBlindStrengthText->SetText(FText::AsNumber(Settings->GetColorBlindStrength()));
	}
	if (UIScaleText)
	{
		UIScaleText->SetText(PercentText(Settings->GetUIScale()));
	}
}

void USettingsMenu3::SetHint(const FText& Hint)
{
	if (SettingsHintText)
	{
		SettingsHintText->SetText(Hint);
	}
}

#undef LOCTEXT_NAMESPACE
