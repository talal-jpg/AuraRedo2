// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Engine/DeveloperSettings.h"
#include "MyHexMinimapSettings.generated.h"

/**
 * Settings used by UMyHexMinimapSubsystem when it bakes the platforms and bridges into the minimap
 * texture. Project Settings > Game > Hex Minimap, saved to DefaultGame.ini.
 *
 * Lengths are for platforms of HexRadius 100 and are multiplied by HexRadius / 100 (the first
 * platform registered decides), like the bridge settings.
 */
UCLASS(Config = Game, DefaultConfig, meta = (DisplayName = "Hex Minimap"))
class AURA_API UMyHexMinimapSettings : public UDeveloperSettings
{
	GENERATED_BODY()

public:

	/** Width and height of the minimap texture in pixels. 1024 = 4 MB. */
	UPROPERTY(Config, EditAnywhere, Category = "Texture", meta = (ClampMin = "64", ClampMax = "4096"))
	int32 TextureSize = 1024;

	/**
	 * cm of the world per texture pixel (for HexRadius 100). The texture covers TextureSize * CmPerPixel
	 * around the local player; 40 gives a tile about 5 pixels wide and a 410 m window.
	 */
	UPROPERTY(Config, EditAnywhere, Category = "Texture", meta = (ClampMin = "1.0"))
	float CmPerPixel = 40.f;

	/**
	 * The window scrolls once the local player is this fraction of the window away from its centre.
	 * Only the strip that scrolls in is redrawn (the texture wraps). Keep the widget's ViewRadius
	 * below (0.5 - RecenterFraction) * the window so the view never leaves it.
	 */
	UPROPERTY(Config, EditAnywhere, Category = "Texture", meta = (ClampMin = "0.01", ClampMax = "0.4"))
	float RecenterFraction = 0.125f;

	/** Seconds between texture uploads. Changes in between (collapsing tiles, new platforms) are batched. */
	UPROPERTY(Config, EditAnywhere, Category = "Texture", meta = (ClampMin = "0.0"))
	float UpdateInterval = 0.1f;

	/** Bridge width on the minimap, in hex radii of the platforms it joins. */
	UPROPERTY(Config, EditAnywhere, Category = "Shapes", meta = (ClampMin = "0.05"))
	float BridgeWidthInHexRadii = 0.8f;

	/** Straight pieces a curved bridge is drawn with. */
	UPROPERTY(Config, EditAnywhere, Category = "Shapes", meta = (ClampMin = "1", ClampMax = "32"))
	int32 BridgeSegments = 8;

	/**
	 * World height (cm) of the lowest and highest tile tops. The texture's blue channel stores where a
	 * tile or bridge sits in this range (1..255, 0 = empty) so the material can shade by height.
	 */
	UPROPERTY(Config, EditAnywhere, Category = "Height")
	float HeightMin = -2000.f;

	UPROPERTY(Config, EditAnywhere, Category = "Height")
	float HeightMax = 4000.f;
};
