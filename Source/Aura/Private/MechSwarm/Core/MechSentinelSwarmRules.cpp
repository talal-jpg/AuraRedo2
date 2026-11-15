// Mech Sentinel Swarm - global, server side rules. Referenced by AMyGameMode (never DeveloperSettings).

#include "MechSwarm/Core/MechSentinelSwarmRules.h"

#include "MechSwarm/GAS/MechSentinelDefaultEffects.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(MechSentinelSwarmRules)

UMechSentinelSwarmRules::UMechSentinelSwarmRules()
{
	// Damage works out of the box, both ways; rules assets can still pick their own effects (or clear the attack one).
	DefaultSentinelDamageEffect = UMechSentinelDamageEffect::StaticClass();
	SentinelAttackEffect = UMechSentinelAttackEffect::StaticClass();
}
