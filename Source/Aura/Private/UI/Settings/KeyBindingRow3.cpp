// Fill out your copyright notice in the Description page of Project Settings.

#include "UI/Settings/KeyBindingRow3.h"
#include "UI/Settings/SettingsMenu3.h"
#include "Components/Button.h"
#include "Components/InputKeySelector.h"
#include "Components/TextBlock.h"

bool UKeyBindingRow3::Initialize()
{
	if (!Super::Initialize())
	{
		return false;
	}

	if (PrimaryKeySelector)
	{
		PrimaryKeySelector->SetAllowGamepadKeys(false);
		PrimaryKeySelector->SetAllowModifierKeys(false);
		PrimaryKeySelector->OnKeySelected.AddDynamic(this, &ThisClass::OnPrimaryKeySelected);
	}
	if (SecondaryKeySelector)
	{
		SecondaryKeySelector->SetAllowGamepadKeys(false);
		SecondaryKeySelector->SetAllowModifierKeys(false);
		SecondaryKeySelector->OnKeySelected.AddDynamic(this, &ThisClass::OnSecondaryKeySelected);
	}
	if (GamepadKeySelector)
	{
		GamepadKeySelector->SetAllowGamepadKeys(true);
		GamepadKeySelector->SetAllowModifierKeys(false);
		GamepadKeySelector->OnKeySelected.AddDynamic(this, &ThisClass::OnGamepadKeySelected);
	}
	if (ResetRowButton)
	{
		ResetRowButton->OnClicked.AddDynamic(this, &ThisClass::ResetRowClicked);
	}

	return true;
}

void UKeyBindingRow3::Setup(USettingsMenu3* InOwningMenu, FName InMappingName, const FText& InDisplayName, const FText& InCategory)
{
	OwningMenu = InOwningMenu;
	MappingName = InMappingName;

	if (ActionNameText)
	{
		ActionNameText->SetText(InDisplayName);
	}
	if (CategoryText)
	{
		CategoryText->SetText(InCategory);
	}
}

void UKeyBindingRow3::Refresh(const FKeyMappingRow& Row)
{
	TGuardValue<bool> RefreshGuard(bRefreshing, true);

	// Sort the row's mappings into keyboard/mouse and gamepad by their default key (the key
	// the IMC gave them), falling back to the current key for slots the player added
	TArray<const FPlayerKeyMapping*> KeyboardMappings;
	const FPlayerKeyMapping* GamepadMapping = nullptr;
	TSet<EPlayerMappableKeySlot> UsedSlots;

	for (const FPlayerKeyMapping& Mapping : Row.Mappings)
	{
		UsedSlots.Add(Mapping.GetSlot());

		const FKey& ClassifyKey = Mapping.GetDefaultKey().IsValid() ? Mapping.GetDefaultKey() : Mapping.GetCurrentKey();
		if (ClassifyKey.IsGamepadKey())
		{
			if (!GamepadMapping || Mapping.GetSlot() < GamepadMapping->GetSlot())
			{
				GamepadMapping = &Mapping;
			}
		}
		else
		{
			KeyboardMappings.Add(&Mapping);
		}
	}

	KeyboardMappings.Sort([](const FPlayerKeyMapping& A, const FPlayerKeyMapping& B)
	{
		return A.GetSlot() < B.GetSlot();
	});

	// A selector with no mapping yet writes into the lowest slot nobody uses
	auto TakeFreeSlot = [&UsedSlots]()
	{
		for (uint8 SlotIndex = static_cast<uint8>(EPlayerMappableKeySlot::First); SlotIndex <= static_cast<uint8>(EPlayerMappableKeySlot::Seventh); ++SlotIndex)
		{
			const EPlayerMappableKeySlot Candidate = static_cast<EPlayerMappableKeySlot>(SlotIndex);
			if (!UsedSlots.Contains(Candidate))
			{
				UsedSlots.Add(Candidate);
				return Candidate;
			}
		}
		return EPlayerMappableKeySlot::Seventh;
	};

	const FPlayerKeyMapping* PrimaryMapping = KeyboardMappings.IsValidIndex(0) ? KeyboardMappings[0] : nullptr;
	const FPlayerKeyMapping* SecondaryMapping = KeyboardMappings.IsValidIndex(1) ? KeyboardMappings[1] : nullptr;

	PrimarySlot = PrimaryMapping ? PrimaryMapping->GetSlot() : TakeFreeSlot();
	SecondarySlot = SecondaryMapping ? SecondaryMapping->GetSlot() : TakeFreeSlot();
	GamepadSlot = GamepadMapping ? GamepadMapping->GetSlot() : TakeFreeSlot();

	if (PrimaryKeySelector)
	{
		PrimaryKeySelector->SetSelectedKey(FInputChord(PrimaryMapping ? PrimaryMapping->GetCurrentKey() : EKeys::Invalid));
	}
	if (SecondaryKeySelector)
	{
		SecondaryKeySelector->SetSelectedKey(FInputChord(SecondaryMapping ? SecondaryMapping->GetCurrentKey() : EKeys::Invalid));
	}
	if (GamepadKeySelector)
	{
		GamepadKeySelector->SetSelectedKey(FInputChord(GamepadMapping ? GamepadMapping->GetCurrentKey() : EKeys::Invalid));
	}
}

void UKeyBindingRow3::OnPrimaryKeySelected(FInputChord SelectedKey)
{
	KeySelected(PrimarySlot, SelectedKey);
}

void UKeyBindingRow3::OnSecondaryKeySelected(FInputChord SelectedKey)
{
	KeySelected(SecondarySlot, SelectedKey);
}

void UKeyBindingRow3::OnGamepadKeySelected(FInputChord SelectedKey)
{
	KeySelected(GamepadSlot, SelectedKey);
}

void UKeyBindingRow3::KeySelected(EPlayerMappableKeySlot Slot, const FInputChord& SelectedKey)
{
	if (bRefreshing || !OwningMenu || !SelectedKey.Key.IsValid())
	{
		return;
	}

	OwningMenu->RebindKey(MappingName, Slot, SelectedKey.Key);
}

void UKeyBindingRow3::ResetRowClicked()
{
	if (OwningMenu)
	{
		OwningMenu->ResetKeyRow(MappingName);
	}
}
