// Fill out your copyright notice in the Description page of Project Settings.


#include "Character/MyCharPlayer.h"

#include <string>

#include "AbilitySystemComponent.h"
#include "MyPlayerState.h"
#include "AbilitySystem/MyAbilitySystemComponent.h"
#include "AbilitySystem/Abilities/MyGameplayAbility.h"
#include "AbilitySystem/Data/MyGameplayTags.h"
#include "AbilitySystem/Data/MyLevelUpInfo.h"
#include "GameFramework/PawnMovementComponent.h"
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
	LerpChestRotToRot();
	LerpFeetRotToRot();
	
	VelocityCharSpace=GetMesh()->GetComponentTransform().InverseTransformVector(GetMovementComponent()->Velocity);
	ControlRotForwardVec= FVector(GetControlRotation().Vector().X,GetControlRotation().Vector().Y,0);
	SetFootLockLoc();
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
				InitializeAttributes();
				GiveStartupAbilities();
				GivePassiveStartupAbilities();
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
				InitializeAttributes();
				GiveStartupAbilities();
				GivePassiveStartupAbilities();
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
	FGameplayEffectSpecHandle SpecHandlePrimary=MyAbilitySystemComponent->MakeOutgoingSpec(PrimaryAttributesEffect,GetLevel_Implementation(),EffectContextHandle);
	MyAbilitySystemComponent->ApplyGameplayEffectSpecToSelf(*SpecHandlePrimary.Data.Get());
	
	//InitSecondaryAttrs
	FGameplayEffectSpecHandle SpecHandleSecondary=MyAbilitySystemComponent->MakeOutgoingSpec(SecondaryAttributesEffect,GetLevel_Implementation(),EffectContextHandle);
	MyAbilitySystemComponent->ApplyGameplayEffectSpecToSelf(*SpecHandleSecondary.Data.Get());
	
	//InitVitalAttrs
	FGameplayEffectSpecHandle SpecHandleVital=MyAbilitySystemComponent->MakeOutgoingSpec(VitalAttributesEffect,GetLevel_Implementation(),EffectContextHandle);
	MyAbilitySystemComponent->ApplyGameplayEffectSpecToSelf(*SpecHandleVital.Data.Get());
}


int32 AMyCharPlayer::GetLevel_Implementation()
{
	return GetPlayerState<AMyPlayerState>()->GetLevel();
}

void AMyCharPlayer::GiveStartupAbilities()
{
	Super::GiveStartupAbilities();
	MyAbilitySystemComponent->bAbilitiesGiven=true;
	MyAbilitySystemComponent->OnAbilitiesGivenDelegate.Broadcast();
}

void AMyCharPlayer::AddToXP_Implementation(int32 XP)
{
	GetPlayerState<AMyPlayerState>()->AddToXP(XP);
}

int32 AMyCharPlayer::GetXP_Implementation()
{
	return GetPlayerState<AMyPlayerState>()->GetXP();
}

void AMyCharPlayer::AddToLevel_Implementation(int32 InLevels)
{
	GetPlayerState<AMyPlayerState>()->AddToLevel(InLevels);
}

void AMyCharPlayer::AddToAttribPoints_Implementation(int32 InAttribPoints)
{
	GetPlayerState<AMyPlayerState>()->AddToAttributePoints(InAttribPoints);
}

int32 AMyCharPlayer::GetAttribPoints_Implementation()
{
	return GetPlayerState<AMyPlayerState>()->GetAttributePoints();
}

void AMyCharPlayer::AddToSpellPoints_Implementation(int32 InSpellPoints)
{
	GetPlayerState<AMyPlayerState>()->AddToSpellPoints(InSpellPoints);
}

int32 AMyCharPlayer::GetSpellPoints_Implementation()
{
	return GetPlayerState<AMyPlayerState>()->GetSpellPoints();
}

void AMyCharPlayer::LevelUp_Implementation()
{
	TArray<TSubclassOf<UGameplayAbility>> AbilitiesUnLocked;
	
	UMyLevelUpInfo* MyLevelUpInfo=GetPlayerState<AMyPlayerState>()->MyLevelUpInfo;
	checkf(MyLevelUpInfo,TEXT("PleaseSetLevelUpInfoOnPlayerStateSoThatItCanBePresentOnClientsAsWell"));
	// UKismetSystemLibrary::PrintString(GetWorld(),std::to_string(GetLevel()).c_str());
	// GetLevel -1 bcz will look in the levelUpInfo list 
	MyLevelUpInfo->GetAbilitiesForLevel(GetLevel_Implementation()-1,AbilitiesUnLocked);
	if (AbilitiesUnLocked.Num()==0)return;
	
	for (TSubclassOf<UGameplayAbility> AbilityClass : AbilitiesUnLocked)
	{
		UMyGameplayAbility* MyGA =Cast<UMyGameplayAbility>(AbilityClass.GetDefaultObject());
		FGameplayTag InputTag= MyTags::Input_None;
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
			GameplayAbilitySpec.GetDynamicSpecSourceTags().AddTag(MyTags::Ability_Status_Eligible);
			
			MyAbilitySystemComponent->GiveAbility(GameplayAbilitySpec);
		}
		else
		{
			UKismetSystemLibrary::PrintString(GetWorld(),TEXT("Invalid InputTag for Ability: ") + AbilityClass.Get()->GetName());
		}
	}

}

void AMyCharPlayer::SetLookAtTarget_Implementation(FVector TargetLocation)
{
}

bool AMyCharPlayer::IsChanneling_Implementation()
{
	return bIsChanneling;
}

void AMyCharPlayer::SetChanneling_Implementation(bool InbIsChanneling)
{
	bIsChanneling=InbIsChanneling;
}

void AMyCharPlayer::SetIsFlying_Implementation(bool InbIsFlying)
{
	bIsFlying=InbIsFlying;
}

bool AMyCharPlayer::IsFlying_Implementation()
{
	return bIsFlying;
}


void AMyCharPlayer::LerpChestRotToRot()
{
	const float AmountToRotateEachTimerTick=.1f;
	// RotChest= FMath::Lerp(RotChest,ForwardVecRigSpace,AmountToRotateEachTimerTick);
	ForwardVecChest=FMath::Lerp(GetMesh()->GetComponentRotation().Vector(),GetControlRotation().Vector(),AmountToRotateEachTimerTick);
}

void AMyCharPlayer::LerpFeetRotToRot()
{
	const float AmountToRotateEachTimerTick=.05f;
	// RotFeet= FMath::Lerp(RotFeet,GetControlRotation().Vector(),AmountToRotateEachTimerTick);
	
	FRotator ControlRot=GetControlRotation();
	ControlRot.Pitch=0;
	FRotator NewRot=FMath::Lerp(GetMesh()->GetComponentRotation(),ControlRot,AmountToRotateEachTimerTick);
	YawDelta = FMath::FindDeltaAngleDegrees(NewRot.Yaw, ControlRot.Yaw);
	// UKismetSystemLibrary::PrintString(GetWorld(),FString::Printf(TEXT("YawDelta: %f"),YawDelta),true,true,FLinearColor::Red,1.f);
	// FVector PawnLoc=GetPawn()->GetActorLocation();
	// UKismetSystemLibrary::DrawDebugArrow(GetWorld(),PawnLoc,PawnLoc+NewRot.Vetor()*1000,10,FLinearColor::Yellow,.1f,10);
	GetMesh()->SetWorldRotation(NewRot);
	// GetPawn()->SetActorRotation(NewRot);
}

void AMyCharPlayer::SetFootLockLoc()
{
	if (UAnimInstance* AnimInstance=GetMesh()->GetAnimInstance())
	{
		float FootLock_l=AnimInstance->GetCurveValue(TEXT("FootLock_l"));
		bFootLock_Left=FootLock_l > .9;
		
		float FootLock_r=AnimInstance->GetCurveValue(TEXT("FootLock_r"));
		bFootLock_Right=FootLock_r > .9;
		
		FVector LFBoneLoc=GetMesh()->GetBoneLocation(FName("LF_point_4"));
		FVector RFBoneLoc=GetMesh()->GetBoneLocation(FName("RF_point_4"));
		
		if (bFootLock_Left)
		{
			FHitResult HitResult;
			FVector TraceStart=LFBoneLoc;
			FCollisionQueryParams Params;
			Params.AddIgnoredActor(this);
			GetWorld()->LineTraceSingleByChannel(HitResult,TraceStart,TraceStart-FVector(0,0,1000),ECC_Visibility,Params);
			if (HitResult.bBlockingHit)
			{
				// FootLockLoc_L=HitResult.ImpactPoint;
				FootLockLoc_L=LFBoneLoc;
				// FootLockLoc_L=GetMesh()->GetComponentTransform().InverseTransformPosition(LFBoneLoc);
				FootLockNormal_L= HitResult.Normal;
			}
		}
		else
		{
			// FootLockLoc_L=GetMesh()->GetComponentTransform().InverseTransformPosition(LFBoneLoc);
			// FootLockLoc_L=GetActorTransform().InverseTransformPosition(LFBoneLoc);
			FootLockLoc_L=LFBoneLoc;
			FootLockNormal_L=FVector(0,0,1);
		}
		
		if (bFootLock_Right)
		{
			FHitResult HitResult;
			FVector TraceStart=RFBoneLoc;
			FCollisionQueryParams Params;
			Params.AddIgnoredActor(this);
			GetWorld()->LineTraceSingleByChannel(HitResult,TraceStart,TraceStart-FVector(0,0,1000),ECC_Visibility,Params);
			if (HitResult.bBlockingHit)
			{
				FootLockLoc_R= HitResult.ImpactPoint;
				// FootLockLoc_R=GetMesh()->GetComponentTransform().InverseTransformPosition(RFBoneLoc);
				FootLockNormal_R= HitResult.Normal;
			}
		}
		else
		{
			// FootLockLoc_R=GetMesh()->GetComponentTransform().InverseTransformPosition(RFBoneLoc);
			FootLockLoc_R=RFBoneLoc;
			FootLockNormal_R=FVector(0,0,1);
		}
		
		// UKismetSystemLibrary::DrawDebugLine(GetWorld(),FootLockLoc_L,FootLockLoc_L+FootLockNormal_L*1000,FLinearColor::Red,true,10);
		// UKismetSystemLibrary::DrawDebugLine(GetWorld(),FootLockLoc_R,FootLockLoc_R+FootLockNormal_R*1000,FLinearColor::Red,true,10);
		
		
	}
	
}


