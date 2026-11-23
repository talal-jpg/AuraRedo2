// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameplayEffect.h"
#include "AirshipDamageEffect.generated.h"

/**
 * Built-in airship damage: instant, Additive on UMyAttributeSet::IncomingDamage, magnitude SetByCaller
 * SetDamageByCaller. Used for hull impacts, console damage and cannonballs when no damage effect asset is set.
 */
UCLASS(meta = (DisplayName = "Airship Damage (built-in)"))
class AURA_API UAirshipDamageEffect : public UGameplayEffect
{
	GENERATED_BODY()

public:

	UAirshipDamageEffect();
};
