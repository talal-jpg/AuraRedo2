// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "UI/UserWidgets/MyUserWidget.h"
#include "Framework/Commands/InputChord.h"
#include "UserSettings/EnhancedInputUserSettings.h"
#include "KeyBindingRow3.generated.h"

class UButton;
class UInputKeySelector;
class UTextBlock;
class USettingsMenu3;

/**
 * One rebindable action in Options > Controls: two keyboard/mouse binds and one gamepad
 * bind, like Far Far West's "multiple binds per action". USettingsMenu3 owns the actual
 * Enhanced Input calls; this row only shows the keys and reports what was picked.
 */
UCLASS()
class AURA_API UKeyBindingRow3 : public UMyUserWidget
{
	GENERATED_BODY()

public:
	void Setup(USettingsMenu3* InOwningMenu, FName InMappingName, const FText& InDisplayName, const FText& InCategory);

	/** Shows Row's current keys and works out which slot each selector writes to. */
	void Refresh(const FKeyMappingRow& Row);

	FName GetMappingName() const { return MappingName; }

protected:
	virtual bool Initialize() override;

private:
	UFUNCTION()
	void OnPrimaryKeySelected(FInputChord SelectedKey);
	UFUNCTION()
	void OnSecondaryKeySelected(FInputChord SelectedKey);
	UFUNCTION()
	void OnGamepadKeySelected(FInputChord SelectedKey);
	UFUNCTION()
	void ResetRowClicked();

	void KeySelected(EPlayerMappableKeySlot KeySlot, const FInputChord& SelectedKey);

	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* ActionNameText;
	UPROPERTY(meta = (BindWidgetOptional))
	UTextBlock* CategoryText;
	UPROPERTY(meta = (BindWidgetOptional))
	UInputKeySelector* PrimaryKeySelector;
	UPROPERTY(meta = (BindWidgetOptional))
	UInputKeySelector* SecondaryKeySelector;
	UPROPERTY(meta = (BindWidgetOptional))
	UInputKeySelector* GamepadKeySelector;
	UPROPERTY(meta = (BindWidgetOptional))
	UButton* ResetRowButton;

	UPROPERTY()
	USettingsMenu3* OwningMenu;

	FName MappingName;
	EPlayerMappableKeySlot PrimarySlot{ EPlayerMappableKeySlot::First };
	EPlayerMappableKeySlot SecondarySlot{ EPlayerMappableKeySlot::Second };
	EPlayerMappableKeySlot GamepadSlot{ EPlayerMappableKeySlot::Third };

	// Set while Refresh() writes the keys, so the selectors' callbacks ignore it
	bool bRefreshing{ false };
};
