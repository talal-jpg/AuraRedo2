// Fill out your copyright notice in the Description page of Project Settings.


#include "Character/MyCharBase.h"

#include "Components/CapsuleComponent.h"
#include "GameFramework/Character.h"

// Sets default values
AMyCharBase::AMyCharBase()
{
	WeaponMesh= CreateDefaultSubobject<USkeletalMeshComponent>(TEXT("WeaponMesh"));
	WeaponMesh->SetupAttachment(GetMesh(),FName("HandSocket"));
	WeaponMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
}

