#include "AbilitySystem/Data/MyGameplayTags.h"

#include "NativeGameplayTags.h"

namespace MyTags
{
	
	// InputTags
	UE_DEFINE_GAMEPLAY_TAG(Input_None,"Input.None")
	UE_DEFINE_GAMEPLAY_TAG(Input_LMB,"Input.LMB")
	UE_DEFINE_GAMEPLAY_TAG(Input_RMB,"Input.RMB")
	UE_DEFINE_GAMEPLAY_TAG(Input_Space,"Input.Space")
	
	
	// MessageTags
	UE_DEFINE_GAMEPLAY_TAG(Message,"Message")
	UE_DEFINE_GAMEPLAY_TAG(Message_Potion_Health,"Message.Potion.Health")
	
	// AttributeTags
	UE_DEFINE_GAMEPLAY_TAG(Attribute_Vital_Health,"Attribute.Vital.Health")
	UE_DEFINE_GAMEPLAY_TAG(Attribute_Vital_Mana,"Attribute.Vital.Mana")
	
	UE_DEFINE_GAMEPLAY_TAG(Attribute_Primary_Strength,"Attribute.Primary.Strength")
	UE_DEFINE_GAMEPLAY_TAG(Attribute_Primary_Agility,"Attribute.Primary.Agility")
	UE_DEFINE_GAMEPLAY_TAG(Attribute_Primary_Intelligence,"Attribute.Primary.Intelligence")
	
	
	
	UE_DEFINE_GAMEPLAY_TAG(Attribute_Secondary_MaxHealth,"Attribute.Secondary.MaxHealth")
	UE_DEFINE_GAMEPLAY_TAG(Attribute_Secondary_MaxMana,"Attribute.Secondary.MaxMana")
	UE_DEFINE_GAMEPLAY_TAG(Attribute_Secondary_HealthRegen,"Attribute.Secondary.HealthRegen")
	UE_DEFINE_GAMEPLAY_TAG(Attribute_Secondary_ManaRegen,"Attribute.Secondary.ManaRegen")
	UE_DEFINE_GAMEPLAY_TAG(Attribute_Secondary_MagicResist,"Attribute.Secondary.MagicResist")
	UE_DEFINE_GAMEPLAY_TAG(Attribute_Secondary_Armor,"Attribute.Secondary.Armor")
	UE_DEFINE_GAMEPLAY_TAG(Attribute_Secondary_AttackSpeed,"Attribute.Secondary.AttackSpeed");
	UE_DEFINE_GAMEPLAY_TAG(Attribute_Secondary_MoveSpeed,"Attribute.Secondary.MoveSpeed");
	UE_DEFINE_GAMEPLAY_TAG(Attribute_Secondary_TurnSpeed,"Attribute.Secondary.TurnSpeed");
	UE_DEFINE_GAMEPLAY_TAG(Attribute_Secondary_AttackDamage,"Attribute.Secondary.AttackDamage");
	
	UE_DEFINE_GAMEPLAY_TAG(Attribute_Meta_XP,"Attribute.Meta.XP");
	
	
	// AbilityTags
	
	UE_DEFINE_GAMEPLAY_TAG(Ability_None,"Ability.None")
	UE_DEFINE_GAMEPLAY_TAG(Ability_FireBolt,"Ability.FireBolt")
	UE_DEFINE_GAMEPLAY_TAG(Ability_Projectile,"Ability.Projectile")
	UE_DEFINE_GAMEPLAY_TAG(Ability_HitReact,"Ability.HitReact")
	UE_DEFINE_GAMEPLAY_TAG(Ability_Electrocute,"Ability.Electrocute")
	UE_DEFINE_GAMEPLAY_TAG(Ability_Shards,"Ability.Shards")
	UE_DEFINE_GAMEPLAY_TAG(Ability_Launch,"Ability.Launch")
	
	//AbilityStatuses
	UE_DEFINE_GAMEPLAY_TAG(Ability_Status_Locked,"Ability.Status.Locked")
	UE_DEFINE_GAMEPLAY_TAG(Ability_Status_Eligible,"Ability.Status.Eligible")
	UE_DEFINE_GAMEPLAY_TAG(Ability_Status_Unlocked,"Ability.Status.Unlocked")
	UE_DEFINE_GAMEPLAY_TAG(Ability_Status_Equiped,"Ability.Status.Equiped")
	
	// AbilityCooldownTags
	UE_DEFINE_GAMEPLAY_TAG(Ability_Cooldown_None,"Ability.Cooldown.None")
	UE_DEFINE_GAMEPLAY_TAG(Ability_Cooldown_FireBolt,"Ability.Cooldown.FireBolt")
	UE_DEFINE_GAMEPLAY_TAG(Ability_Cooldown_Projectile,"Ability.Cooldown.Projectile")
	UE_DEFINE_GAMEPLAY_TAG(Ability_Cooldown_Electrocute,"Ability.Cooldown.Electrocute")
	UE_DEFINE_GAMEPLAY_TAG(Ability_Cooldown_Shards,"Ability.Cooldown.Shards")
	
	// EventTags
	UE_DEFINE_GAMEPLAY_TAG(Event_XPGained,"Event.XPGained")
	UE_DEFINE_GAMEPLAY_TAG(Event_HitReact,"Event.HitReact")
	UE_DEFINE_GAMEPLAY_TAG(Event_SpawnFireBall,"Event.SpawnFireBall")
	UE_DEFINE_GAMEPLAY_TAG(Event_SpawnElectrocute,"Event.SpawnElectrocute")
	
	// GameplayCues
	UE_DEFINE_GAMEPLAY_TAG(GameplayCue_FireballBurst,"GameplayCue.FireballBurst")
	UE_DEFINE_GAMEPLAY_TAG(GameplayCue_ElectrocuteBurst,"GameplayCue.ElectrocuteBurst")
	UE_DEFINE_GAMEPLAY_TAG(GameplayCue_ElectrocuteLooping,"GameplayCue.ElectrocuteLooping")
	UE_DEFINE_GAMEPLAY_TAG(GameplayCue_Shards,"GameplayCue.Shards")
	
	//StateTags
	UE_DEFINE_GAMEPLAY_TAG(State_Channeling,"State.Channeling")
	
	//SetByCallerMagTag
	UE_DEFINE_GAMEPLAY_TAG(SetDamageByCaller,"SetDamageByCaller")
	
}
