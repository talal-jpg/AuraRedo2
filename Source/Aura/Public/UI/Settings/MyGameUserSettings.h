// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameUserSettings.h"
#include "MyGameUserSettings.generated.h"

class USoundMix;

DECLARE_MULTICAST_DELEGATE_OneParam(FOnAuraSettingsChangedSignature, class UMyGameUserSettings*);

UENUM(BlueprintType)
enum class EAuraVolumeChannel : uint8
{
	Master UMETA(DisplayName = "Master"),
	Music UMETA(DisplayName = "Music"),
	Effects UMETA(DisplayName = "Effects"),
	Voice UMETA(DisplayName = "Voice"),
	Interface UMETA(DisplayName = "Interface")
};

UENUM(BlueprintType)
enum class EAuraAntiAliasingMethod : uint8
{
	None UMETA(DisplayName = "Off"),
	FXAA UMETA(DisplayName = "FXAA"),
	TAA UMETA(DisplayName = "TAA"),
	TSR UMETA(DisplayName = "TSR")
};

UENUM(BlueprintType)
enum class EAuraColorBlindMode : uint8
{
	Off UMETA(DisplayName = "Off"),
	Deuteranope UMETA(DisplayName = "Deuteranope (green-weak)"),
	Protanope UMETA(DisplayName = "Protanope (red-weak)"),
	Tritanope UMETA(DisplayName = "Tritanope (blue-weak)")
};

/** The tabs of USettingsMenu3, used to reset one tab to its defaults. */
UENUM(BlueprintType)
enum class EAuraSettingsGroup : uint8
{
	Video,
	Audio,
	Controls,
	Gameplay,
	Accessibility
};

/**
 * Everything the Options screen edits that UGameUserSettings doesn't already store:
 * audio volumes, gamma, motion blur, anti-aliasing, Lumen, look sensitivity,
 * invert Y, field of view, damage numbers, screen shake / flashes, colour blind mode,
 * UI scale and subtitles. Saved per device to GameUserSettings.ini like the video
 * settings. Key bindings live in the Enhanced Input user settings save instead.
 *
 * Needs [/Script/Engine.Engine] GameUserSettingsClassName=/Script/Aura.MyGameUserSettings
 * in DefaultEngine.ini (already added).
 *
 * Applying: the rendering / accessibility values apply with ApplyNonResolutionSettings()
 * (so ApplySettings() covers them too). Volumes need a world: ApplyAudioSettings(),
 * which UMySettingsSubsystem calls for every map. Gameplay values (sensitivity, FOV,
 * screen shake, flashes, damage numbers) are read by AMyPlayerController2.
 */
UCLASS(Config = GameUserSettings, ConfigDoNotCheckDefaults)
class AURA_API UMyGameUserSettings : public UGameUserSettings
{
	GENERATED_BODY()

public:
	/** GEngine's settings object as UMyGameUserSettings. Null if GameUserSettingsClassName isn't set to this class. */
	UFUNCTION(BlueprintPure, Category = "Aura|Settings", meta = (DisplayName = "Get Aura Game User Settings"))
	static UMyGameUserSettings* GetMyGameUserSettings();

	//~ UGameUserSettings
	virtual void SetToDefaults() override;
	virtual void ApplyNonResolutionSettings() override;
	//~ End UGameUserSettings

	/** Puts one Options tab back to its defaults (Video also runs through the display confirm in the menu). */
	UFUNCTION(BlueprintCallable, Category = "Aura|Settings")
	void ResetGroupToDefaults(EAuraSettingsGroup Group);

	/** Pushes the volumes to the sound classes set in Project Settings > Game > Aura Menu. */
	UFUNCTION(BlueprintCallable, Category = "Aura|Settings", meta = (WorldContext = "WorldContextObject"))
	void ApplyAudioSettings(const UObject* WorldContextObject);

	/** Gamma, motion blur, anti-aliasing, Lumen, colour blind mode, UI scale, subtitles, mute in background. Part of ApplyNonResolutionSettings(). */
	void ApplyRenderingAndAccessibilitySettings();

	/** Fires after Apply... so live gameplay (camera FOV, screen shake) can pick changes up. */
	FOnAuraSettingsChangedSignature OnAuraSettingsChanged;

	//
	// Audio (0..1)
	//
	UFUNCTION(BlueprintPure, Category = "Aura|Settings|Audio")
	float GetVolume(EAuraVolumeChannel Channel) const;
	UFUNCTION(BlueprintCallable, Category = "Aura|Settings|Audio")
	void SetVolume(EAuraVolumeChannel Channel, float InVolume);

	UFUNCTION(BlueprintPure, Category = "Aura|Settings|Audio")
	bool GetMuteWhenUnfocused() const { return bMuteWhenUnfocused; }
	UFUNCTION(BlueprintCallable, Category = "Aura|Settings|Audio")
	void SetMuteWhenUnfocused(bool bInMute) { bMuteWhenUnfocused = bInMute; }

	//
	// Video extras
	//
	UFUNCTION(BlueprintPure, Category = "Aura|Settings|Video")
	float GetGamma() const { return Gamma; }
	UFUNCTION(BlueprintCallable, Category = "Aura|Settings|Video")
	void SetGamma(float InGamma);

	UFUNCTION(BlueprintPure, Category = "Aura|Settings|Video")
	bool GetMotionBlurEnabled() const { return bMotionBlur; }
	UFUNCTION(BlueprintCallable, Category = "Aura|Settings|Video")
	void SetMotionBlurEnabled(bool bEnabled) { bMotionBlur = bEnabled; }

	UFUNCTION(BlueprintPure, Category = "Aura|Settings|Video")
	EAuraAntiAliasingMethod GetAntiAliasingMethod() const { return AntiAliasingMethod; }
	UFUNCTION(BlueprintCallable, Category = "Aura|Settings|Video")
	void SetAntiAliasingMethod(EAuraAntiAliasingMethod InMethod) { AntiAliasingMethod = InMethod; }

	UFUNCTION(BlueprintPure, Category = "Aura|Settings|Video")
	bool GetLumenEnabled() const { return bLumen; }
	UFUNCTION(BlueprintCallable, Category = "Aura|Settings|Video")
	void SetLumenEnabled(bool bEnabled) { bLumen = bEnabled; }

	//
	// Controls
	//
	UFUNCTION(BlueprintPure, Category = "Aura|Settings|Controls")
	float GetLookSensitivity() const { return LookSensitivity; }
	UFUNCTION(BlueprintCallable, Category = "Aura|Settings|Controls")
	void SetLookSensitivity(float InSensitivity);

	UFUNCTION(BlueprintPure, Category = "Aura|Settings|Controls")
	bool GetInvertLookY() const { return bInvertLookY; }
	UFUNCTION(BlueprintCallable, Category = "Aura|Settings|Controls")
	void SetInvertLookY(bool bInvert) { bInvertLookY = bInvert; }

	UFUNCTION(BlueprintPure, Category = "Aura|Settings|Controls")
	bool GetInvertLookX() const { return bInvertLookX; }
	UFUNCTION(BlueprintCallable, Category = "Aura|Settings|Controls")
	void SetInvertLookX(bool bInvert) { bInvertLookX = bInvert; }

	//
	// Gameplay
	//
	UFUNCTION(BlueprintPure, Category = "Aura|Settings|Gameplay")
	float GetFieldOfView() const { return FieldOfView; }
	UFUNCTION(BlueprintCallable, Category = "Aura|Settings|Gameplay")
	void SetFieldOfView(float InFieldOfView);

	UFUNCTION(BlueprintPure, Category = "Aura|Settings|Gameplay")
	bool GetShowDamageNumbers() const { return bShowDamageNumbers; }
	UFUNCTION(BlueprintCallable, Category = "Aura|Settings|Gameplay")
	void SetShowDamageNumbers(bool bShow) { bShowDamageNumbers = bShow; }

	//
	// Accessibility
	//
	UFUNCTION(BlueprintPure, Category = "Aura|Settings|Accessibility")
	bool GetScreenShakeEnabled() const { return bScreenShake; }
	UFUNCTION(BlueprintCallable, Category = "Aura|Settings|Accessibility")
	void SetScreenShakeEnabled(bool bEnabled) { bScreenShake = bEnabled; }

	UFUNCTION(BlueprintPure, Category = "Aura|Settings|Accessibility")
	bool GetScreenFlashesEnabled() const { return bScreenFlashes; }
	UFUNCTION(BlueprintCallable, Category = "Aura|Settings|Accessibility")
	void SetScreenFlashesEnabled(bool bEnabled) { bScreenFlashes = bEnabled; }

	UFUNCTION(BlueprintPure, Category = "Aura|Settings|Accessibility")
	EAuraColorBlindMode GetColorBlindMode() const { return ColorBlindMode; }
	UFUNCTION(BlueprintCallable, Category = "Aura|Settings|Accessibility")
	void SetColorBlindMode(EAuraColorBlindMode InMode) { ColorBlindMode = InMode; }

	// 0..10, how strongly the colour blind correction is applied
	UFUNCTION(BlueprintPure, Category = "Aura|Settings|Accessibility")
	int32 GetColorBlindStrength() const { return ColorBlindStrength; }
	UFUNCTION(BlueprintCallable, Category = "Aura|Settings|Accessibility")
	void SetColorBlindStrength(int32 InStrength) { ColorBlindStrength = FMath::Clamp(InStrength, 0, 10); }

	UFUNCTION(BlueprintPure, Category = "Aura|Settings|Accessibility")
	float GetUIScale() const { return UIScale; }
	UFUNCTION(BlueprintCallable, Category = "Aura|Settings|Accessibility")
	void SetUIScale(float InScale);

	UFUNCTION(BlueprintPure, Category = "Aura|Settings|Accessibility")
	bool GetSubtitlesEnabled() const { return bSubtitles; }
	UFUNCTION(BlueprintCallable, Category = "Aura|Settings|Accessibility")
	void SetSubtitlesEnabled(bool bEnabled) { bSubtitles = bEnabled; }

	// Slider ranges, shared by the menu and the setters' clamps
	static constexpr float MinGamma = 1.4f;
	static constexpr float MaxGamma = 3.2f;
	static constexpr float DefaultGamma = 2.2f;
	static constexpr float MinLookSensitivity = 0.1f;
	static constexpr float MaxLookSensitivity = 5.f;
	static constexpr float MinFieldOfView = 70.f;
	static constexpr float MaxFieldOfView = 120.f;
	static constexpr float DefaultFieldOfView = 90.f;
	static constexpr float MinUIScale = 0.75f;
	static constexpr float MaxUIScale = 1.5f;

protected:
	UPROPERTY(Config)
	float MasterVolume = 1.f;
	UPROPERTY(Config)
	float MusicVolume = 1.f;
	UPROPERTY(Config)
	float EffectsVolume = 1.f;
	UPROPERTY(Config)
	float VoiceVolume = 1.f;
	UPROPERTY(Config)
	float InterfaceVolume = 1.f;
	UPROPERTY(Config)
	bool bMuteWhenUnfocused = false;

	UPROPERTY(Config)
	float Gamma = DefaultGamma;
	UPROPERTY(Config)
	bool bMotionBlur = true;
	UPROPERTY(Config)
	EAuraAntiAliasingMethod AntiAliasingMethod = EAuraAntiAliasingMethod::TSR;
	// Off forces Lumen GI and reflections off; on leaves them to the GI / Reflection quality levels
	UPROPERTY(Config)
	bool bLumen = true;

	UPROPERTY(Config)
	float LookSensitivity = 1.f;
	UPROPERTY(Config)
	bool bInvertLookY = false;
	UPROPERTY(Config)
	bool bInvertLookX = false;

	UPROPERTY(Config)
	float FieldOfView = DefaultFieldOfView;
	UPROPERTY(Config)
	bool bShowDamageNumbers = true;

	UPROPERTY(Config)
	bool bScreenShake = true;
	UPROPERTY(Config)
	bool bScreenFlashes = true;
	UPROPERTY(Config)
	EAuraColorBlindMode ColorBlindMode = EAuraColorBlindMode::Off;
	UPROPERTY(Config)
	int32 ColorBlindStrength = 10;
	UPROPERTY(Config)
	float UIScale = 1.f;
	UPROPERTY(Config)
	bool bSubtitles = true;

private:
	// Used when Project Settings > Game > Aura Menu has no Volume Sound Mix
	UPROPERTY(Transient)
	TObjectPtr<USoundMix> RuntimeVolumeMix;

	void ResetAudioToDefaults();
	void ResetVideoExtrasToDefaults();
	void ResetControlsToDefaults();
	void ResetGameplayToDefaults();
	void ResetAccessibilityToDefaults();
};
