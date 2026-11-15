// Fill out your copyright notice in the Description page of Project Settings.

#include "UI/Settings/MyGameUserSettings.h"
#include "UI/Settings/MyMenuSettings.h"
#include "Engine/Engine.h"
#include "Engine/UserInterfaceSettings.h"
#include "Engine/World.h"
#include "Framework/Application/SlateApplication.h"
#include "HAL/IConsoleManager.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/App.h"
#include "Rendering/SlateRenderer.h"
#include "Sound/AudioSettings.h"
#include "Sound/SoundClass.h"
#include "Sound/SoundMix.h"

namespace
{
	void SetCVarFromGameSetting(const TCHAR* Name, int32 Value)
	{
		if (IConsoleVariable* CVar = IConsoleManager::Get().FindConsoleVariable(Name))
		{
			CVar->Set(Value, ECVF_SetByGameSetting);
		}
	}

	// What BaseScalability.ini gives each quality level (Low..Cinematic), so "on" matches the
	// quality group instead of forcing the maximum
	int32 MotionBlurQualityForLevel(int32 PostProcessQuality)
	{
		static const int32 Values[] = { 0, 3, 3, 4, 4 };
		return Values[FMath::Clamp(PostProcessQuality, 0, 4)];
	}

	int32 LumenAllowedForLevel(int32 QualityLevel)
	{
		return QualityLevel >= 2 ? 1 : 0;
	}
}

UMyGameUserSettings* UMyGameUserSettings::GetMyGameUserSettings()
{
	return GEngine ? Cast<UMyGameUserSettings>(GEngine->GetGameUserSettings()) : nullptr;
}

void UMyGameUserSettings::SetToDefaults()
{
	Super::SetToDefaults();

	ResetAudioToDefaults();
	ResetVideoExtrasToDefaults();
	ResetControlsToDefaults();
	ResetGameplayToDefaults();
	ResetAccessibilityToDefaults();
}

void UMyGameUserSettings::ResetGroupToDefaults(EAuraSettingsGroup Group)
{
	switch (Group)
	{
	case EAuraSettingsGroup::Video:
		// Same values UGameUserSettings::SetToDefaults() uses for the video part, except a real resolution:
		// (0, 0) would make ValidateSettings mark the default mode as confirmed without ever applying it
		SetFullscreenMode(GetDefaultWindowMode());
		SetScreenResolution(GetDesktopResolution());
		SetVSyncEnabled(false);
		SetFrameRateLimit(0.f);
		ScalabilityQuality.SetDefaults(); // also puts the render scale back to 100%
		ResetVideoExtrasToDefaults();
		break;
	case EAuraSettingsGroup::Audio:
		ResetAudioToDefaults();
		break;
	case EAuraSettingsGroup::Controls:
		ResetControlsToDefaults();
		break;
	case EAuraSettingsGroup::Gameplay:
		ResetGameplayToDefaults();
		break;
	case EAuraSettingsGroup::Accessibility:
		ResetAccessibilityToDefaults();
		break;
	}
}

void UMyGameUserSettings::ResetAudioToDefaults()
{
	MasterVolume = 1.f;
	MusicVolume = 1.f;
	EffectsVolume = 1.f;
	VoiceVolume = 1.f;
	InterfaceVolume = 1.f;
	bMuteWhenUnfocused = false;
}

void UMyGameUserSettings::ResetVideoExtrasToDefaults()
{
	Gamma = DefaultGamma;
	bMotionBlur = true;
	AntiAliasingMethod = EAuraAntiAliasingMethod::TSR;
	bLumen = true;
}

void UMyGameUserSettings::ResetControlsToDefaults()
{
	LookSensitivity = 1.f;
	bInvertLookY = false;
	bInvertLookX = false;
}

void UMyGameUserSettings::ResetGameplayToDefaults()
{
	FieldOfView = DefaultFieldOfView;
	bShowDamageNumbers = true;
}

void UMyGameUserSettings::ResetAccessibilityToDefaults()
{
	bScreenShake = true;
	bScreenFlashes = true;
	ColorBlindMode = EAuraColorBlindMode::Off;
	ColorBlindStrength = 10;
	UIScale = 1.f;
	bSubtitles = true;
}

void UMyGameUserSettings::ApplyNonResolutionSettings()
{
	Super::ApplyNonResolutionSettings();

	ApplyRenderingAndAccessibilitySettings();
	OnAuraSettingsChanged.Broadcast(this);
}

void UMyGameUserSettings::ApplyRenderingAndAccessibilitySettings()
{
	if (GEngine)
	{
		GEngine->DisplayGamma = Gamma;
		GEngine->bSubtitlesEnabled = bSubtitles;
	}

	// SetByGameSetting outranks the SetByScalability values the quality groups just wrote
	SetCVarFromGameSetting(TEXT("r.MotionBlurQuality"), bMotionBlur ? MotionBlurQualityForLevel(GetPostProcessingQuality()) : 0);
	SetCVarFromGameSetting(TEXT("r.Lumen.DiffuseIndirect.Allow"), bLumen ? LumenAllowedForLevel(GetGlobalIlluminationQuality()) : 0);
	SetCVarFromGameSetting(TEXT("r.Lumen.Reflections.Allow"), bLumen ? LumenAllowedForLevel(GetReflectionQuality()) : 0);

	int32 AntiAliasingCVarValue = 4;
	switch (AntiAliasingMethod)
	{
	case EAuraAntiAliasingMethod::None: AntiAliasingCVarValue = 0; break;
	case EAuraAntiAliasingMethod::FXAA: AntiAliasingCVarValue = 1; break;
	case EAuraAntiAliasingMethod::TAA:  AntiAliasingCVarValue = 2; break;
	case EAuraAntiAliasingMethod::TSR:  AntiAliasingCVarValue = 4; break;
	}
	SetCVarFromGameSetting(TEXT("r.AntiAliasingMethod"), AntiAliasingCVarValue);

	FApp::SetUnfocusedVolumeMultiplier(bMuteWhenUnfocused ? 0.f : 1.f);

	// Not in the editor: ApplicationScale is a config value of a project settings object, and
	// the editor would write a value tested in PIE into DefaultEngine.ini the next time UI
	// settings are saved. Packaged and -game builds apply it.
	if (!GIsEditor)
	{
		GetMutableDefault<UUserInterfaceSettings>()->ApplicationScale = UIScale;
	}

	if (FSlateApplication::IsInitialized())
	{
		if (FSlateRenderer* Renderer = FSlateApplication::Get().GetRenderer())
		{
			EColorVisionDeficiency Deficiency = EColorVisionDeficiency::NormalVision;
			switch (ColorBlindMode)
			{
			case EAuraColorBlindMode::Off:         Deficiency = EColorVisionDeficiency::NormalVision; break;
			case EAuraColorBlindMode::Deuteranope: Deficiency = EColorVisionDeficiency::Deuteranope; break;
			case EAuraColorBlindMode::Protanope:   Deficiency = EColorVisionDeficiency::Protanope; break;
			case EAuraColorBlindMode::Tritanope:   Deficiency = EColorVisionDeficiency::Tritanope; break;
			}
			// Correct for the deficiency (not simulate it)
			Renderer->SetColorVisionDeficiencyType(Deficiency, ColorBlindStrength, true, false);
		}
	}
}

void UMyGameUserSettings::ApplyAudioSettings(const UObject* WorldContextObject)
{
	FApp::SetUnfocusedVolumeMultiplier(bMuteWhenUnfocused ? 0.f : 1.f);

	UWorld* World = GEngine ? GEngine->GetWorldFromContextObject(WorldContextObject, EGetWorldErrorMode::ReturnNull) : nullptr;
	if (!World)
	{
		return;
	}

	const UMyMenuSettings* MenuSettings = GetDefault<UMyMenuSettings>();

	USoundMix* Mix = MenuSettings->VolumeSoundMix.LoadSynchronous();
	if (!Mix)
	{
		if (!RuntimeVolumeMix)
		{
			RuntimeVolumeMix = NewObject<USoundMix>(this, TEXT("AuraRuntimeVolumeMix"));
		}
		Mix = RuntimeVolumeMix;
	}

	USoundClass* MasterClass = MenuSettings->MasterSoundClass.LoadSynchronous();
	if (!MasterClass)
	{
		MasterClass = Cast<USoundClass>(GetDefault<UAudioSettings>()->DefaultSoundClassName.TryLoad());
	}

	// Children inherit the master override, so Music at 0.5 under Master at 0.5 plays at 0.25
	auto OverrideClass = [World, Mix](USoundClass* SoundClass, float ClassVolume)
	{
		if (SoundClass)
		{
			UGameplayStatics::SetSoundMixClassOverride(World, Mix, SoundClass, ClassVolume, 1.f, 0.f, true);
		}
	};
	OverrideClass(MasterClass, MasterVolume);
	OverrideClass(MenuSettings->MusicSoundClass.LoadSynchronous(), MusicVolume);
	OverrideClass(MenuSettings->EffectsSoundClass.LoadSynchronous(), EffectsVolume);
	OverrideClass(MenuSettings->VoiceSoundClass.LoadSynchronous(), VoiceVolume);
	OverrideClass(MenuSettings->InterfaceSoundClass.LoadSynchronous(), InterfaceVolume);

	UGameplayStatics::PushSoundMixModifier(World, Mix);
}

float UMyGameUserSettings::GetVolume(EAuraVolumeChannel Channel) const
{
	switch (Channel)
	{
	case EAuraVolumeChannel::Master:    return MasterVolume;
	case EAuraVolumeChannel::Music:     return MusicVolume;
	case EAuraVolumeChannel::Effects:   return EffectsVolume;
	case EAuraVolumeChannel::Voice:     return VoiceVolume;
	case EAuraVolumeChannel::Interface: return InterfaceVolume;
	}
	return 1.f;
}

void UMyGameUserSettings::SetVolume(EAuraVolumeChannel Channel, float InVolume)
{
	const float Clamped = FMath::Clamp(InVolume, 0.f, 1.f);
	switch (Channel)
	{
	case EAuraVolumeChannel::Master:    MasterVolume = Clamped; break;
	case EAuraVolumeChannel::Music:     MusicVolume = Clamped; break;
	case EAuraVolumeChannel::Effects:   EffectsVolume = Clamped; break;
	case EAuraVolumeChannel::Voice:     VoiceVolume = Clamped; break;
	case EAuraVolumeChannel::Interface: InterfaceVolume = Clamped; break;
	}
}

void UMyGameUserSettings::SetGamma(float InGamma)
{
	Gamma = FMath::Clamp(InGamma, MinGamma, MaxGamma);
}

void UMyGameUserSettings::SetLookSensitivity(float InSensitivity)
{
	LookSensitivity = FMath::Clamp(InSensitivity, MinLookSensitivity, MaxLookSensitivity);
}

void UMyGameUserSettings::SetFieldOfView(float InFieldOfView)
{
	FieldOfView = FMath::Clamp(InFieldOfView, MinFieldOfView, MaxFieldOfView);
}

void UMyGameUserSettings::SetUIScale(float InScale)
{
	UIScale = FMath::Clamp(InScale, MinUIScale, MaxUIScale);
}
