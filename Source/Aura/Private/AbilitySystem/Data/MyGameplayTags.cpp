#include "AbilitySystem/Data/MyGameplayTags.h"

#include "NativeGameplayTags.h"

namespace MyTags
{
	
	// InputTags
	UE_DEFINE_GAMEPLAY_TAG(Input_LMB,"Input.LMB")
	UE_DEFINE_GAMEPLAY_TAG(Input_RMB,"Input.RMB")
	
	// MessageTags
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
	
	UE_DEFINE_GAMEPLAY_TAG(Attribute_Meta_IncomingDamage,"Attribute.Meta.IncomingDamage");
	UE_DEFINE_GAMEPLAY_TAG(Attribute_Meta_IncomingXp,"Attribute.Meta.IncomingXp");
	
	// AbilityTags
	UE_DEFINE_GAMEPLAY_TAG(Ability_None,"Ability.None")
	UE_DEFINE_GAMEPLAY_TAG(Ability_FireBolt,"Ability.FireBolt")
	UE_DEFINE_GAMEPLAY_TAG(Ability_Projectile,"Ability.Projectile")
	UE_DEFINE_GAMEPLAY_TAG(Ability_HitReact,"Ability.HitReact")
	UE_DEFINE_GAMEPLAY_TAG(Ability_Enemy_MeleeDamage,"Ability.Enemy.MeleeDamage")
	UE_DEFINE_GAMEPLAY_TAG(Ability_Enemy_RangedDamage,"Ability.Enemy.RangedDamage")
	
	// AbilityStatus
	UE_DEFINE_GAMEPLAY_TAG(Ability_Status_Locked,"Ability.Status.Locked")
	UE_DEFINE_GAMEPLAY_TAG(Ability_Status_Eligible,"Ability.Status.Eligible");
	UE_DEFINE_GAMEPLAY_TAG(Ability_Status_Unlocked,"Ability.Status.Unlocked");
	UE_DEFINE_GAMEPLAY_TAG(Ability_Status_Equipped,"Ability.Status.Equipped");
	
	// AbilityType
	UE_DEFINE_GAMEPLAY_TAG(Ability_Type_Passive,"Ability.Type.Passive");
	UE_DEFINE_GAMEPLAY_TAG(Ability_Type_Offensive,"Ability.Type.Offensive");
	UE_DEFINE_GAMEPLAY_TAG(Ability_Type_None,"Ability.Type.None");
	// EventTags
	UE_DEFINE_GAMEPLAY_TAG(Event_ApplyGEPassively,"Event.ApplyGEPassively")
	UE_DEFINE_GAMEPLAY_TAG(Event_HitReact,"Event.HitReact")
	UE_DEFINE_GAMEPLAY_TAG(Event_SpawnFireBall,"Event.SpawnFireBall")
	UE_DEFINE_GAMEPLAY_TAG(Event_Enemy_MeleeAttack,"Event.Enemy.MeleeAttack")
	UE_DEFINE_GAMEPLAY_TAG(Event_Enemy_RangedAttack,"Event.Enemy.RangedAttack")
	
	//SetByCallerMagTag
	UE_DEFINE_GAMEPLAY_TAG(SetDamageByCaller,"SetDamageByCaller")
	
}
