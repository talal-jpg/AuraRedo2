// Mech Sentinel Swarm - processor group names used to order the swarm processors.
//
// Order inside one frame (authority side, PrePhysics):
//   Behavior (effects, targeting) -> Tasks (steering) -> Avoidance (agents, then obstacles) -> ApplyForces -> Movement
//   -> MechSwarm.Combat
// Representation side (PostPhysics, where something is rendered):
//   MechSwarm.LODCollector -> MechSwarm.Representation

#pragma once

#include "CoreMinimal.h"

namespace MechSwarm::ProcessorGroups
{
	/** Attack, death and collision-hash processors, after movement has settled positions. */
	inline FName Combat() { return FName(TEXT("MechSwarm.Combat")); }

	/** Local viewer distance gathering for visual LOD. */
	inline FName LODCollector() { return FName(TEXT("MechSwarm.LODCollector")); }

	/** Visual LOD selection and ISM updates. */
	inline FName Representation() { return FName(TEXT("MechSwarm.Representation")); }
}
