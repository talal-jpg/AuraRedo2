// Mech Sentinel Swarm - the sentinel trait.

#include "MechSwarm/Sentinel/MechSentinelTrait.h"

#include "Engine/World.h"
#include "MassEntityTemplateRegistry.h"
#include "MassEntityUtils.h"
#include "Mass/EntityFragments.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(MechSentinelTrait)

void UMechSentinelTrait::BuildTemplate(FMassEntityTemplateBuildContext& BuildContext, const UWorld& World) const
{
	FMassEntityManager& EntityManager = UE::Mass::Utils::GetEntityManagerChecked(World);

	// The engine transform fragment is kept on purpose: MassReplication reads it for relevancy.
	BuildContext.AddFragment<FTransformFragment>();
	BuildContext.AddTag<FMechSentinelTag>();

	FMechSentinelAttributesFragment& AttributesFragment = BuildContext.AddFragment_GetRef<FMechSentinelAttributesFragment>();
	AttributesFragment.MaxHealth = Attributes.MaxHealth;
	AttributesFragment.Health = Attributes.MaxHealth;
	AttributesFragment.BaseArmor = AttributesFragment.Armor = Attributes.Armor;
	AttributesFragment.BaseAttackDamage = AttributesFragment.AttackDamage = Attributes.AttackDamage;
	AttributesFragment.BaseAttackSpeed = AttributesFragment.AttackSpeed = Attributes.AttackSpeed;
	AttributesFragment.BaseMoveSpeedMultiplier = AttributesFragment.MoveSpeedMultiplier = 1.f;

	BuildContext.AddFragment<FMechSentinelGASFragment>();
	BuildContext.AddFragment<FMechSentinelStateFragment>();
	BuildContext.AddFragment<FMechSentinelTargetFragment>();
	BuildContext.AddFragment<FMechSentinelAttackFragment>();

	BuildContext.AddConstSharedFragment(EntityManager.GetOrCreateConstSharedFragment(Parameters));

	FMechSentinelSharedAttributesFragment SharedAttributes;
	SharedAttributes.SwarmGroup = SwarmGroup;
	SharedAttributes.MovementSpeed = MovementSpeed;
	BuildContext.AddSharedFragment(EntityManager.GetOrCreateSharedFragment(SharedAttributes));

	FMechSentinelTargetingSharedFragment TargetingBoard;
	TargetingBoard.SwarmGroup = SwarmGroup;
	BuildContext.AddSharedFragment(EntityManager.GetOrCreateSharedFragment(TargetingBoard));

	// Clients do not simulate; they ease toward the replicated samples.
	if (World.GetNetMode() == NM_Client || BuildContext.IsInspectingData())
	{
		BuildContext.AddFragment<FMechSentinelNetSmoothingFragment>();
	}
}
