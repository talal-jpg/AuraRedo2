// Fill out your copyright notice in the Description page of Project Settings.


#include "Character/MyCharBase.h"

// Sets default values
AMyCharBase::AMyCharBase()
{
	
	CharMesh = CreateDefaultSubobject<USkeletalMeshComponent>(TEXT("CharMesh"));
	WeaponMesh= CreateDefaultSubobject<USkeletalMeshComponent>(TEXT("WeaponMesh"));
	SetRootComponent(CharMesh);
	WeaponMesh->SetupAttachment(CharMesh,FName("WeaponSocket"));
}

