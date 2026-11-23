// Fill out your copyright notice in the Description page of Project Settings.


#include "Airship/AirshipDamageEffect.h"

#include "AbilitySystem/Data/MyGameplayTags.h"
#include "AbilitySystem/MyAttributeSet.h"

UAirshipDamageEffect::UAirshipDamageEffect()
{
	DurationPolicy = EGameplayEffectDurationType::Instant;

	FSetByCallerFloat SetByCaller;
	SetByCaller.DataTag = MyTags::SetDamageByCaller;

	FGameplayModifierInfo& Modifier = Modifiers.AddDefaulted_GetRef();
	Modifier.Attribute = UMyAttributeSet::GetIncomingDamageAttribute();
	Modifier.ModifierOp = EGameplayModOp::Additive;
	Modifier.ModifierMagnitude = FGameplayEffectModifierMagnitude(SetByCaller);
}
