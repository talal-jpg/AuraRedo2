// Mech Sentinel Swarm - native gameplay tags used by the sentinel combat bridge.

#include "MechSwarm/GAS/MechSentinelTags.h"

namespace MechSentinelTags
{
	UE_DEFINE_GAMEPLAY_TAG(State_Sentinel_Stunned, "State.Sentinel.Stunned")
	UE_DEFINE_GAMEPLAY_TAG(State_Sentinel_Shielded, "State.Sentinel.Shielded")
	UE_DEFINE_GAMEPLAY_TAG(State_Sentinel_Dead, "State.Sentinel.Dead")
	UE_DEFINE_GAMEPLAY_TAG(State_Sentinel_Attacking, "State.Sentinel.Attacking")
	UE_DEFINE_GAMEPLAY_TAG(Unit_Sentinel, "Unit.Sentinel")
	UE_DEFINE_GAMEPLAY_TAG(State_Sentinel_Buff_Armor, "State.Sentinel.Buff.Armor")
	UE_DEFINE_GAMEPLAY_TAG(State_Sentinel_Buff_Speed, "State.Sentinel.Buff.Speed")
	UE_DEFINE_GAMEPLAY_TAG(State_Sentinel_Buff_Damage, "State.Sentinel.Buff.Damage")
	UE_DEFINE_GAMEPLAY_TAG(SetByCaller_SelfBuffMagnitude, "SetByCaller.MechSentinel.SelfBuffMagnitude")
}
