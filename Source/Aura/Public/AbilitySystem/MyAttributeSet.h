// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "AttributeSet.h"
#include "AbilitySystemComponent.h"
#include "MyAttributeSet.generated.h"

USTRUCT()
struct FEffectProperties
{
	GENERATED_BODY()
	
	FEffectProperties() {}
	
	FGameplayEffectContextHandle EffectContextHandle;
	
	UPROPERTY()
	UAbilitySystemComponent* SourceASC = nullptr;
	
	UPROPERTY()
	AActor* SourceAvatarActor = nullptr;
	
	UPROPERTY()
	AController* SourceController = nullptr;
	
	UPROPERTY()
	ACharacter* SourceCharacter = nullptr;
	
	UPROPERTY()
	UAbilitySystemComponent* TargetASC = nullptr;
	
	UPROPERTY()
	AActor* TargetAvatarActor = nullptr;
	
	UPROPERTY()
	AController* TargetController = nullptr;
	
	UPROPERTY()
	ACharacter* TargetCharacter = nullptr;
};

/**
 * 
 */
UCLASS()
class AURA_API UMyAttributeSet : public UAttributeSet
{
	GENERATED_BODY()
	
	virtual void GetLifetimeReplicatedProps(TArray<class FLifetimeProperty>& OutLifetimeProps) const override;
	
public:
	UMyAttributeSet();
	
	virtual void PostGameplayEffectExecute(FGameplayEffectModCallbackData& Data) override;
	
	virtual void PreAttributeChange(const FGameplayAttribute& Attribute, float& NewValue) override;
	

	/**
	 * vital attributes
	 */
	UPROPERTY(ReplicatedUsing = OnRep_Health)
	FGameplayAttributeData Health;
	ATTRIBUTE_ACCESSORS_BASIC(UMyAttributeSet,Health)
	
	UPROPERTY(ReplicatedUsing = OnRep_MaxHealth)
	FGameplayAttributeData MaxHealth;
	ATTRIBUTE_ACCESSORS_BASIC(UMyAttributeSet,MaxHealth)
	
	UPROPERTY(ReplicatedUsing = OnRep_Mana)
	FGameplayAttributeData Mana;
	ATTRIBUTE_ACCESSORS_BASIC(UMyAttributeSet,Mana)
	
	UPROPERTY(ReplicatedUsing = OnRep_MaxMana)
	FGameplayAttributeData MaxMana;
	ATTRIBUTE_ACCESSORS_BASIC(UMyAttributeSet,MaxMana)
	
	UFUNCTION()
	void OnRep_Health(const FGameplayAttributeData& OldHealth);
	
	UFUNCTION()
	void OnRep_Mana(const FGameplayAttributeData& OldMana);
	
	UFUNCTION()
	void OnRep_MaxHealth(const FGameplayAttributeData& OldMaxHealth);
	
	UFUNCTION()
	void OnRep_MaxMana(const FGameplayAttributeData& OldMaxMana);
	
	/**
	 *Primary Attributes
	 */
	UPROPERTY(EditAnywhere,ReplicatedUsing=OnRep_Strength)
	FGameplayAttributeData Strength;
	ATTRIBUTE_ACCESSORS_BASIC(UMyAttributeSet,Strength)
	
	UPROPERTY(EditAnywhere,ReplicatedUsing=OnRep_Agility)
	FGameplayAttributeData Agility;
	ATTRIBUTE_ACCESSORS_BASIC(UMyAttributeSet,Agility)
	
	UPROPERTY(EditAnywhere,ReplicatedUsing=OnRep_Intelligence)
	FGameplayAttributeData Intelligence;
	ATTRIBUTE_ACCESSORS_BASIC(UMyAttributeSet,Intelligence)
	
	UFUNCTION()
	void OnRep_Strength(const FGameplayAttributeData& OldStrength);
	
	UFUNCTION()
	void OnRep_Agility(const FGameplayAttributeData& OldAgility);
	
	UFUNCTION()
	void OnRep_Intelligence(const FGameplayAttributeData& OldIntelligence);
	
	/**
	 * Secondary Attributes
	 */
	
	/**
	 *Dependency Chart
*	Attribute 	Primary Stat	Secondary Stat	Derived Bonus (per 1 point)
*Strength 🧱	Health	HP & HP Regen	+22 Max HP, +0.1 HP Regeneration
*Agility ⚔️	Physical	Armor & Attack Speed	+1/6 Armor (~0.16), +1 Attack Speed , Movement Speed , Turn Speed
*Intelligence 🔮	Mana	Mana & Magic Resist	+12 Max Mana, +0.05 Mana Regen, +0.1% Magic Resist
*Primary ⭐	Damage	Attack Damage	+1.0 Attack Damage (+0.7 for Universal heroes)
*/	
	
	UPROPERTY(EditAnywhere,ReplicatedUsing=OnRep_HealthRegen)
	FGameplayAttributeData HealthRegen;
	ATTRIBUTE_ACCESSORS_BASIC(UMyAttributeSet,HealthRegen)
	
	
	UPROPERTY(EditAnywhere,ReplicatedUsing=OnRep_ManaRegen)
	FGameplayAttributeData ManaRegen;
	ATTRIBUTE_ACCESSORS_BASIC(UMyAttributeSet,ManaRegen)
	
	UPROPERTY(EditAnywhere,ReplicatedUsing=OnRep_MagicResist)
	FGameplayAttributeData MagicResist;
	ATTRIBUTE_ACCESSORS_BASIC(UMyAttributeSet,MagicResist)
	
	UFUNCTION()
	void OnRep_HealthRegen(const FGameplayAttributeData& OldHealthRegen);
	
	UFUNCTION()
	void OnRep_ManaRegen(const FGameplayAttributeData& OldManaRegen);
	
	UFUNCTION()
	void OnRep_MagicResist(const FGameplayAttributeData& OldMagicResist);
	
	UPROPERTY(EditAnywhere,ReplicatedUsing=OnRep_Armor)
	FGameplayAttributeData Armor;
	ATTRIBUTE_ACCESSORS_BASIC(UMyAttributeSet,Armor)
	
	UPROPERTY(EditAnywhere,ReplicatedUsing=OnRep_AttackSpeed)
	FGameplayAttributeData AttackSpeed;
	ATTRIBUTE_ACCESSORS_BASIC(UMyAttributeSet,AttackSpeed)
	
	UPROPERTY(EditAnywhere,ReplicatedUsing=OnRep_MoveSpeed)
	FGameplayAttributeData MoveSpeed;
	ATTRIBUTE_ACCESSORS_BASIC(UMyAttributeSet,MoveSpeed)
	
	UPROPERTY(EditAnywhere,ReplicatedUsing=OnRep_TurnSpeed)
	FGameplayAttributeData TurnSpeed;
	ATTRIBUTE_ACCESSORS_BASIC(UMyAttributeSet,TurnSpeed)
	
	UPROPERTY(EditAnywhere,ReplicatedUsing=OnRep_AttackDamage)
	FGameplayAttributeData AttackDamage;
	ATTRIBUTE_ACCESSORS_BASIC(UMyAttributeSet,AttackDamage)
	
	UPROPERTY(EditAnywhere,ReplicatedUsing=OnRep_CritChance)
	FGameplayAttributeData CritChance;
	ATTRIBUTE_ACCESSORS_BASIC(UMyAttributeSet,CritChance)
	
	UFUNCTION()
	void OnRep_Armor(const FGameplayAttributeData& OldArmor);
	
	UFUNCTION()
	void OnRep_AttackSpeed(const FGameplayAttributeData& OldAttackSpeed);
	
	UFUNCTION()
	void OnRep_MoveSpeed(const FGameplayAttributeData& OldMoveSpeed);
	
	UFUNCTION()
	void OnRep_TurnSpeed(const FGameplayAttributeData& OldTurnSpeed);
	
	UFUNCTION()
	void OnRep_AttackDamage(const FGameplayAttributeData& OldAttackDamage);
	
	UFUNCTION()
	void OnRep_CritChance(const FGameplayAttributeData& OldCritChance);
	
	/**
	 * Meta Attributes
	 */
	
	UPROPERTY()
	FGameplayAttributeData IncomingDamage;
	ATTRIBUTE_ACCESSORS_BASIC(UMyAttributeSet,IncomingDamage)
	
	
	TMap<FGameplayTag,FGameplayAttribute> TagToAttributeMap;
	
private:
	
	void SetEffectProperties(const FGameplayEffectModCallbackData& Data, FEffectProperties& Props);
};
