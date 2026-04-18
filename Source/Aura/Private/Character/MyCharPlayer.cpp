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
	if (!MyAbilitySystemComponent)return;
	
	
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
				// GiveStartupAbilities();
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
	// for (auto Ability:MyAbilitySystemComponent->GetActivatableAbilities())
	// {
	// 	UKismetSystemLibrary::PrintString(this,Ability.GetDebugString());
	// }
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
	FGameplayEffectSpecHandle SpecHandlePrimary=MyAbilitySystemComponent->MakeOutgoingSpec(PrimaryAttributesEffect,IMyCombatInterface::Execute_GetCharLevel(this),EffectContextHandle);
	MyAbilitySystemComponent->ApplyGameplayEffectSpecToSelf(*SpecHandlePrimary.Data.Get());
	
	//InitSecondaryAttrs
	FGameplayEffectSpecHandle SpecHandleSecondary=MyAbilitySystemComponent->MakeOutgoingSpec(SecondaryAttributesEffect,IMyCombatInterface::Execute_GetCharLevel(this),EffectContextHandle);
	MyAbilitySystemComponent->ApplyGameplayEffectSpecToSelf(*SpecHandleSecondary.Data.Get());
	
	//InitVitalAttrs
	FGameplayEffectSpecHandle SpecHandleVital=MyAbilitySystemComponent->MakeOutgoingSpec(VitalAttributesEffect,IMyCombatInterface::Execute_GetCharLevel(this),EffectContextHandle);
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

int32 AMyCharPlayer::GetCharLevel_Implementation()
{
	return GetPlayerState<AMyPlayerState>()->GetLevel();
}


void AMyCharPlayer::AddToXP_Implementation(int32 InXP)
{
	AMyPlayerState* MyPlayerState=GetPlayerState<AMyPlayerState>();
	check(MyPlayerState);
	MyPlayerState->AddToXP(InXP);
}

void AMyCharPlayer::AddToPlayerLevel_Implementation(int32 InPlayerLevel)
{
	AMyPlayerState* MyPlayerState=GetPlayerState<AMyPlayerState>();
	check(MyPlayerState);
	MyPlayerState->AddToLevel(InPlayerLevel);
	
	//GiveAbilityOnLevelUp
	MyAbilitySystemComponent->UpdateAbilityStatuses(MyPlayerState->GetLevel()+InPlayerLevel);
	
}

void AMyCharPlayer::LevelUp_Implementation()
{
	IMyPlayerInterface::LevelUp_Implementation();
}

int32 AMyCharPlayer::FindLevelForXP_Implementation(int32 XP)
{
	return GetPlayerState<AMyPlayerState>()->LevelUpInfo->FindLevelForXP(XP);
}

int32 AMyCharPlayer::GetXP_Implementation()
{
	return GetPlayerState<AMyPlayerState>()->GetXP();
}

int32 AMyCharPlayer::GetAttributePoints_Implementation()
{
	return GetPlayerState<AMyPlayerState>()->GetAttributePoints();
}

int32 AMyCharPlayer::GetSpellPoints_Implementation()
{
	return GetPlayerState<AMyPlayerState>()->GetSpellPoints();
}

void AMyCharPlayer::AddToAttributePoints_Implementation(int32 InAttributePoints)
{
	GetPlayerState<AMyPlayerState>()->AddToAttributePoints(InAttributePoints);
}

void AMyCharPlayer::AddToSpellPoints_Implementation(int32 InSpellPoints)
{
	GetPlayerState<AMyPlayerState>()->AddToSpellPoints(InSpellPoints);
}

int32 AMyCharPlayer::GetAttributePointsReward_Implementation(int32 Level)
{
	const AMyPlayerState* MyPlayerState = GetPlayerState<AMyPlayerState>();
	check(MyPlayerState);
	return MyPlayerState->LevelUpInfo->LevelUpInfos[Level].AttributePointsReward;
}

int32 AMyCharPlayer::GetSpellPointsReward_Implementation(int32 Level)
{
	const AMyPlayerState* MyPlayerState = GetPlayerState<AMyPlayerState>();
	check(MyPlayerState);
	return MyPlayerState->LevelUpInfo->LevelUpInfos[Level].SpellPointsReward;
}





