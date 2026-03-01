// Fill out your copyright notice in the Description page of Project Settings.


#include "Character/MyCharBase.h"

#include "AbilitySystem/MyAbilitySystemComponent.h"
#include "AbilitySystem/Abilities/MyGameplayAbility.h"
#include "Components/CapsuleComponent.h"
#include "GameFramework/Character.h"
#include "MotionWarpingComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Kismet/KismetSystemLibrary.h"

// Sets default values
AMyCharBase::AMyCharBase()
{
	WeaponMesh= CreateDefaultSubobject<USkeletalMeshComponent>(TEXT("WeaponMesh"));
	WeaponMesh->SetupAttachment(GetMesh(),FName("HandSocket"));
	WeaponMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
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
			
			MyAbilitySystemComponent->GiveAbility(GameplayAbilitySpec);
		}
		else
		{
			UKismetSystemLibrary::PrintString(GetWorld(),TEXT("Invalid InputTag for Ability: ") + AbilityClass.Get()->GetName());
		}
	}
}

void AMyCharBase::GivePassiveAbilities()
{
	if (PassiveAbilities.Num() <= 0)return;
	for (TSubclassOf<UGameplayAbility> AbilityClass : PassiveAbilities)
	{
		FGameplayAbilitySpec GASpec=MyAbilitySystemComponent->BuildAbilitySpecFromClass(AbilityClass);
		MyAbilitySystemComponent->GiveAbilityAndActivateOnce(GASpec);
	}
}


FVector AMyCharBase::GetCombatSocketLocation_Implementation()
{
	return WeaponMesh->GetSocketLocation(FName("CombatSocket"));
}

void AMyCharBase::SetCombatTarget_Implementation(AActor* InCombatTarget)
{
	
	if (UActorComponent* MotionWarpingComponent= GetComponentByClass(UMotionWarpingComponent::StaticClass()))
	{
		// UKismetSystemLibrary::PrintString(GetWorld(),TEXT("MotionWarpingComponent Found"));
		UMotionWarpingComponent* MotionWarpingComp=Cast<UMotionWarpingComponent>(MotionWarpingComponent);
		FMotionWarpingTarget WarpTarget;
		WarpTarget.Name=TEXT("LookAt");
		if (!InCombatTarget)return;
		WarpTarget.Location=InCombatTarget->GetActorLocation();
		MotionWarpingComp->AddOrUpdateWarpTarget(WarpTarget);
	}
	else
	{
		// UKismetSystemLibrary::PrintString(GetWorld(),TEXT("MotionWarpingComponent Not Found"));
	}
	CombatTarget=InCombatTarget;
}

ECharacterClass AMyCharBase::GetCharacterClass()
{
	return CharacterClass;
}

AActor* AMyCharBase::GetCombatTarget_Implementation()
{
	return CombatTarget;
}

void AMyCharBase::HandleDeath_Implementation()
{
	WeaponMesh->DetachFromComponent(FDetachmentTransformRules::KeepWorldTransform);
	WeaponMesh->SetCollisionProfileName("Ragdoll");
	WeaponMesh->SetSimulatePhysics(true);
	GetCharacterMovement()->DisableMovement();
	GetCharacterMovement()->StopMovementImmediately();
	
	GetCapsuleComponent()->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	// GetMesh()->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);//IsRedundant
	GetMesh()->SetCollisionProfileName("Ragdoll");
	GetMesh()->SetSimulatePhysics(true);
	
}



