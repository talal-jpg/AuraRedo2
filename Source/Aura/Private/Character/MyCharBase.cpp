// Fill out your copyright notice in the Description page of Project Settings.


#include "Character/MyCharBase.h"

#include "AbilitySystem/MyAbilitySystemComponent.h"
#include "AbilitySystem/Abilities/MyGameplayAbility.h"
#include "AbilitySystem/Data/MyGameplayTags.h"
#include "Components/CapsuleComponent.h"
#include "GameFramework/Character.h"
#include "Kismet/KismetSystemLibrary.h"

// Sets default values
AMyCharBase::AMyCharBase()
{
	WeaponMesh= CreateDefaultSubobject<USkeletalMeshComponent>(TEXT("WeaponMesh"));
	WeaponMesh->SetupAttachment(GetMesh(),FName("HandSocket"));
	WeaponMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
}

void AMyCharBase::Dissolve()
{
	if (IsValid(DissolveMaterialInstance))
	{
		UMaterialInstanceDynamic* DynamicMatInst= UMaterialInstanceDynamic::Create(DissolveMaterialInstance,this);
		GetMesh()->SetMaterial(0,DynamicMatInst);
		
		StartDissolveTimeline(DynamicMatInst);
	}
	if (IsValid(WeaponDissolveMaterialInstance))
	{
		UMaterialInstanceDynamic* DynamicMatInst2= UMaterialInstanceDynamic::Create(WeaponDissolveMaterialInstance,this);
		WeaponMesh->SetMaterial(0,DynamicMatInst2);
		StartWeaponDissolveTimeline(DynamicMatInst2);
	}
}

UAbilitySystemComponent* AMyCharBase::GetAbilitySystemComponent() const
{
	return MyAbilitySystemComponent;
}

void AMyCharBase::GiveStartupAbilities()
{
	for (TSubclassOf<UGameplayAbility> AbilityClass : StartupAbilities)
	{
		UMyGameplayAbility* MyGA =Cast<UMyGameplayAbility>(AbilityClass.GetDefaultObject());
		FGameplayTag InputTag= MyGA->InputTag;
		FGameplayTag AbilityTag= MyGA->AbilityTag;
		if (!MyGA)
		{
			UKismetSystemLibrary::PrintString(GetWorld(),TEXT("Invalid AbilityClass for Ability: ") + AbilityClass.Get()->GetName());
		}
		if (MyGA)
		{
			FGameplayAbilitySpec GameplayAbilitySpec=MyAbilitySystemComponent->BuildAbilitySpecFromClass(AbilityClass);
			
			if (InputTag.IsValid())
			{
				GameplayAbilitySpec.GetDynamicSpecSourceTags().AddTag(InputTag);
			}
			if (AbilityTag.IsValid())
			{
				GameplayAbilitySpec.GetDynamicSpecSourceTags().AddTag(AbilityTag);
			}
			GameplayAbilitySpec.GetDynamicSpecSourceTags().AddTag(MyTags::Ability_Status_Equiped);
			
			MyAbilitySystemComponent->GiveAbility(GameplayAbilitySpec);
		}
		else
		{
			UKismetSystemLibrary::PrintString(GetWorld(),TEXT("Invalid InputTag for Ability: ") + AbilityClass.Get()->GetName());
		}
	}
}

void AMyCharBase::GivePassiveStartupAbilities()
{
	for (auto Ability: PassiveStartupAbilities)
	{
		FGameplayAbilitySpec AbilitySpec = GetAbilitySystemComponent()->BuildAbilitySpecFromClass(Ability);
		GetAbilitySystemComponent()->GiveAbilityAndActivateOnce(AbilitySpec);
	}
	
}

FVector AMyCharBase::GetCombatSocketLocation_Implementation()
{
	return WeaponMesh->GetSocketLocation(FName("CombatSocket"));
}

void AMyCharBase::Die()
{
	WeaponMesh->DetachFromComponent(FDetachmentTransformRules(EDetachmentRule::KeepWorld,true));
	MulticastHandleDeath();
	
	//Do we need to set replicated?
	bIsDead=true;
}

FOnDeathDelegateSignature& AMyCharBase::GetOnDeathDelegate()
{
	return OnDeathDelegate;
}

void AMyCharBase::MulticastHandleDeath_Implementation()
{
	WeaponMesh->SetSimulatePhysics(true);
	WeaponMesh->SetEnableGravity(true);
	WeaponMesh->SetCollisionEnabled(ECollisionEnabled::PhysicsOnly);
	
	GetMesh()->SetSimulatePhysics(true);
	GetMesh()->SetEnableGravity(true);
	GetMesh()->SetCollisionEnabled(ECollisionEnabled::PhysicsOnly);
	GetMesh()->SetCollisionResponseToChannel(ECC_WorldStatic,ECR_Block);
	
	GetCapsuleComponent()->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	
	Dissolve();
	OnDeathDelegate.Broadcast(this);
}



