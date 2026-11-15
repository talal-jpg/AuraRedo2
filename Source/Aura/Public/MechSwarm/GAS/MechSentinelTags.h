// Mech Sentinel Swarm - native gameplay tags used by the sentinel combat bridge.

#pragma once

#include "NativeGameplayTags.h"

namespace MechSentinelTags
{
	/** Granted by stun effects (EMP etc). Mirrored to FMechSentinelStunnedTag: no steering, no attacks. */
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(State_Sentinel_Stunned)

	/** Granted by shield effects. ExecCalc_SentinelDamage scales incoming damage by the rules' shield multiplier. */
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(State_Sentinel_Shielded)

	/** Set when health reaches 0. Mirrored to FMechSentinelDeadTag. */
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(State_Sentinel_Dead)

	/** Present while the sentinel is in its attack state (informational, for effects with tag requirements). */
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(State_Sentinel_Attacking)

	/** Every sentinel effect target carries this, handy for GE application requirements. */
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(Unit_Sentinel)
}
