// Fill out your copyright notice in the Description page of Project Settings.


#include "Character/MyCharPlayer.h"

#include "AbilitySystemComponent.h"
#include "EnhancedInputSubsystems.h"
#include "MyPlayerState.h"


// Sets default values
AMyCharPlayer::AMyCharPlayer()
{
	// Set this character to call Tick() every frame.  You can turn this off to improve performance if you don't need it.
	PrimaryActorTick.bCanEverTick = true;
}


// Called when the game starts or when spawned
void AMyCharPlayer::BeginPlay()
{
	Super::BeginPlay();
	
	
}

// Called every frame
void AMyCharPlayer::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);
}

void AMyCharPlayer::OnRep_PlayerState()
{
	Super::OnRep_PlayerState();
	
	if (!HasAuthority())
	{
		Cast<AMyPlayerState>(GetPlayerState())->AbilitySystemComponent->InitAbilityActorInfo(GetPlayerState(),this);
	}
}

void AMyCharPlayer::PossessedBy(AController* NewController)
{
	Super::PossessedBy(NewController);
	if (HasAuthority())
	{
		Cast<AMyPlayerState>(GetPlayerState())->AbilitySystemComponent->InitAbilityActorInfo(GetPlayerState(),this);
	}
}


