// Fill out your copyright notice in the Description page of Project Settings.


#include "Character/MyCharPlayer.h"

#include "AbilitySystemComponent.h"
#include "MyPlayerState.h"
#include "AbilitySystem/MyAbilitySystemComponent.h"
#include "Kismet/KismetSystemLibrary.h"
#include "UI/MyHUD.h"


// Sets default values
AMyCharPlayer::AMyCharPlayer()
{
	// Set this character to call Tick() every frame.  You can turn this off to improve performance if you don't need it.
	PrimaryActorTick.bCanEverTick = true;
	// SpringArm= CreateDefaultSubobject<USpringArmComponent>(TEXT("SpringArm"));
	// Camera= CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
	// Camera->SetupAttachment(SpringArm);
	// SpringArm->TargetArmLength = 600.0f;
	// SpringArm->SetupAttachment(GetCapsuleComponent());
	// SpringArm->bUsePawnControlRotation = false;
	// SpringArm->bInheritPitch = false;
	// SpringArm->bInheritRoll = false;
	// SpringArm->bInheritYaw = true;

	// Camera->bUsePawnControlRotation = false;

	bUseControllerRotationPitch = false;
	bUseControllerRotationRoll = false;
	bUseControllerRotationYaw = false;
	
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
		if (AMyPlayerState* MyPlayerState = Cast<AMyPlayerState>(GetPlayerState()))
		{
			if (MyPlayerState->MyAbilitySystemComponent)
			{
				MyPlayerState->MyAbilitySystemComponent->InitAbilityActorInfo(MyPlayerState, this);
				// UKismetSystemLibrary::PrintString(GetWorld(), TEXT("OnRep_PlayerState"));
				MyAbilitySystemComponent=MyPlayerState->MyAbilitySystemComponent;
			}
		}
	}
	// Initializing HUD on client (PlayerController is only valid for local player)
	if (APlayerController* PC = Cast<APlayerController>(GetController()))
	{
		if (AMyHUD* MyHUD = PC->GetHUD<AMyHUD>())
		{
			MyHUD->InitOverlay();
		}
	}
}

void AMyCharPlayer::PossessedBy(AController* NewController)
{
	Super::PossessedBy(NewController);
	if (HasAuthority())
	{
		if (AMyPlayerState* MyPlayerState = Cast<AMyPlayerState>(GetPlayerState()))
		{
			if (MyPlayerState->MyAbilitySystemComponent)
			{
				MyPlayerState->MyAbilitySystemComponent->InitAbilityActorInfo(MyPlayerState, this);
				MyAbilitySystemComponent=MyPlayerState->MyAbilitySystemComponent;
				// UKismetSystemLibrary::PrintString(GetWorld(), TEXT("PossessedBy"));
			}
		}
	}
	if (APlayerController* PC=Cast<APlayerController>(NewController))
	{
		AMyHUD* MyHUD=PC->GetHUD<AMyHUD>();
		if (!MyHUD)return;
		MyHUD->InitOverlay();
	}
}


