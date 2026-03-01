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
			if (UMyAbilitySystemComponent* MyASC=Cast<UMyAbilitySystemComponent>(MyPlayerState->GetAbilitySystemComponent()))
			{
				MyASC->InitAbilityActorInfo(MyPlayerState, this);
				// UKismetSystemLibrary::PrintString(GetWorld(), TEXT("OnRep_PlayerState"));
				MyAbilitySystemComponent=MyASC;
				InitializeAttributes();
				GiveStartupAbilities();
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
		if (AMyPlayerState* MyPlayerState = GetPlayerState<AMyPlayerState>())
		{
			if (UMyAbilitySystemComponent* MyASC=Cast<UMyAbilitySystemComponent>(MyPlayerState->GetAbilitySystemComponent()))
			{
				MyASC->InitAbilityActorInfo(MyPlayerState, this);
				// UKismetSystemLibrary::PrintString(GetWorld(), TEXT("OnRep_PlayerState"));
				MyAbilitySystemComponent=MyASC;
				InitializeAttributes();
				GiveStartupAbilities();
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

void AMyCharPlayer::InitializeAttributes()
{
	// InitPrimaryAttrs
	FGameplayEffectContextHandle EffectContextHandle=MyAbilitySystemComponent->MakeEffectContext();
	EffectContextHandle.AddInstigator(this,this);
	FGameplayEffectSpecHandle SpecHandlePrimary=MyAbilitySystemComponent->MakeOutgoingSpec(PrimaryAttributesEffect,GetCharLevel(),EffectContextHandle);
	MyAbilitySystemComponent->ApplyGameplayEffectSpecToSelf(*SpecHandlePrimary.Data.Get());
	
	//InitSecondaryAttrs
	FGameplayEffectSpecHandle SpecHandleSecondary=MyAbilitySystemComponent->MakeOutgoingSpec(SecondaryAttributesEffect,GetCharLevel(),EffectContextHandle);
	MyAbilitySystemComponent->ApplyGameplayEffectSpecToSelf(*SpecHandleSecondary.Data.Get());
	
	//InitVitalAttrs
	FGameplayEffectSpecHandle SpecHandleVital=MyAbilitySystemComponent->MakeOutgoingSpec(VitalAttributesEffect,GetCharLevel(),EffectContextHandle);
	MyAbilitySystemComponent->ApplyGameplayEffectSpecToSelf(*SpecHandleVital.Data.Get());
}


void AMyCharPlayer::GiveStartupAbilities()
{
	Super::GiveStartupAbilities();
	GivePassiveAbilities();
	MyAbilitySystemComponent->bAbilitiesGiven=true;
	MyAbilitySystemComponent->OnAbilitiesGivenDelegate.Broadcast();
}

void AMyCharPlayer::GivePassiveAbilities()
{
	Super::GivePassiveAbilities();
}

int32 AMyCharPlayer::GetCharLevel()
{
	return GetPlayerState<AMyPlayerState>()->GetLevel();
}

int32 AMyCharPlayer::FindLevelForXP_Implementation(int32 XP)
{
	return GetPlayerState<AMyPlayerState>()->LevelUpInfo->FindLevelForXp(XP);
}

int32 AMyCharPlayer::GetXP_Implementation()
{
	return GetPlayerState<AMyPlayerState>()->GetXP();
}





