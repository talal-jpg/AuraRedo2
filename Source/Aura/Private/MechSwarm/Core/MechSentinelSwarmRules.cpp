// Mech Sentinel Swarm - global, server side rules. Referenced by AMyGameMode (never DeveloperSettings).

#include "MechSwarm/Core/MechSentinelSwarmRules.h"

#include "MechSwarm/GAS/MechSentinelDefaultEffects.h"
#include "MechSwarm/Sentinel/MechSentinelFragments.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(MechSentinelSwarmRules)

UMechSentinelSwarmRules::UMechSentinelSwarmRules()
{
	// Damage works out of the box, both ways; rules assets can still pick their own effects (or clear the attack one).
	DefaultSentinelDamageEffect = UMechSentinelDamageEffect::StaticClass();
	SentinelAttackEffect = UMechSentinelAttackEffect::StaticClass();

	// Self-buffs work out of the box too. Armor whenever, speed to close in on a far target, damage when near it.
	ArmorBuff.Effect = UMechSentinelArmorBuffEffect::StaticClass();
	ArmorBuff.Magnitude = 1.75f;
	ArmorBuff.Duration = 6.f;
	ArmorBuff.Cooldown = 18.f;

	SpeedBuff.Effect = UMechSentinelSpeedBuffEffect::StaticClass();
	SpeedBuff.Magnitude = 1.5f;
	SpeedBuff.Duration = 4.f;
	SpeedBuff.Cooldown = 12.f;
	SpeedBuff.MinTargetDistance = 1500.f;

	DamageBuff.Effect = UMechSentinelDamageBuffEffect::StaticClass();
	DamageBuff.Magnitude = 1.5f;
	DamageBuff.Duration = 5.f;
	DamageBuff.Cooldown = 15.f;
	DamageBuff.MaxTargetDistance = 2500.f;
}

const FMechSentinelSelfBuffDef& UMechSentinelSwarmRules::GetSelfBuffDef(const int32 BuffIndex) const
{
	switch (BuffIndex)
	{
	case int32(EMechSentinelSelfBuff::Speed):
		return SpeedBuff;
	case int32(EMechSentinelSelfBuff::Damage):
		return DamageBuff;
	default:
		return ArmorBuff;
	}
}
