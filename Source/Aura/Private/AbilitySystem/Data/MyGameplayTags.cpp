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
	
	// AbilityTags
	UE_DEFINE_GAMEPLAY_TAG(Abilities_FireBolt,"Abilities.FireBolt")
	
	// EventTags
	UE_DEFINE_GAMEPLAY_TAG(Event_XPGained,"Event.XPGained")
	UE_DEFINE_GAMEPLAY_TAG(Event_HitReact,"Event.HitReact")
	
}
