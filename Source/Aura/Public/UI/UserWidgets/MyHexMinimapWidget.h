// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "MyHexMinimapWidget.generated.h"

class UImage;
class UMaterialInstanceDynamic;
class UMaterialInterface;

/**
 * Round minimap of the hex platforms and bridges. Draws one image with MinimapMaterial, fed every
 * frame from UMyHexMinimapSubsystem (the baked texture) and the players' positions.
 *
 * Works as a plain C++ widget (it builds its own image) or as the parent of a Widget Blueprint
 * with an Image named MinimapImage. Hidden until the first platform has been drawn.
 *
 * Material parameters it sets:
 * - MapTexture (texture): the subsystem's texture.
 * - MapWindow: (MinX, MinY, Size, 0) world cm the texture holds. UV = WorldXY / Size.
 * - View: (CentreX, CentreY, ViewRadius cm, yaw in radians of the direction shown as "up").
 * - Height: (HeightMin, HeightMax, local player Z, local player yaw relative to "up", radians).
 * - Player0..Player3: (X, Y, 1 = shown, 0) for the other players.
 */
UCLASS(BlueprintType, Blueprintable)
class AURA_API UMyHexMinimapWidget : public UUserWidget
{
	GENERATED_BODY()

public:

	UMyHexMinimapWidget(const FObjectInitializer& ObjectInitializer);

	/** Material in the UI domain that reads the parameters above. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Minimap")
	TSoftObjectPtr<UMaterialInterface> MinimapMaterial;

	/** World radius (cm, for HexRadius 100) shown from the centre to the rim. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Hex Minimap", meta = (ClampMin = "100.0"))
	float ViewRadius = 6000.f;

	/** Turn the map with the camera so "up" is where the camera looks. Off = world +X is up. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Hex Minimap")
	bool bRotateWithCamera = true;

	/** On-screen size (slate units) of the image the C++ widget builds for itself. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Hex Minimap")
	float MinimapSize = 256.f;

	UFUNCTION(BlueprintPure, Category = "Hex Minimap")
	UMaterialInstanceDynamic* GetMinimapMaterialInstance() const { return MaterialInstance; }

protected:

	virtual void NativeOnInitialized() override;

	virtual void NativeTick(const FGeometry& MyGeometry, float InDeltaTime) override;

	UPROPERTY(BlueprintReadOnly, Category = "Hex Minimap", meta = (BindWidgetOptional))
	TObjectPtr<UImage> MinimapImage;

private:

	UPROPERTY(Transient)
	TObjectPtr<UMaterialInstanceDynamic> MaterialInstance;

	/** Players besides the local one the material can show. Matches Player0..Player3. */
	static constexpr int32 MaxOtherPlayers = 4;
};
