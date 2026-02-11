// Fill out your copyright notice in the Description page of Project Settings.


#include "PlayerInput/MyPlayerController.h"

#include <string>

#include "EnhancedInputComponent.h"
#include "EnhancedInputSubsystems.h"
#include "MyPlayerState.h"
#include "NavigationPath.h"
#include "NavigationSystem.h"
#include "AbilitySystem/MyAbilitySystemComponent.h"
#include "AbilitySystem/Data/MyGameplayTags.h"
#include "Components/SplineComponent.h"
#include "GameFramework/Character.h"
#include "Interfaces/MyHighlightInterface.h"
#include "Kismet/GameplayStatics.h"
#include "PlayerInput/MyInputComponent.h"


class UEnhancedPlayerInput;
class UEnhancedInputLocalPlayerSubsystem;

AMyPlayerController::AMyPlayerController()
{
	SplineComp= CreateDefaultSubobject<USplineComponent>(TEXT("SplineComp"));
	// FInputModeGameOnly InputMode;
}

void AMyPlayerController::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);
	AutoMove();
	CursorTrace();
}

void AMyPlayerController::SetupInputComponent()
{
	Super::SetupInputComponent();
	
	UEnhancedInputLocalPlayerSubsystem* EnhancedInputSubsystem=ULocalPlayer::GetSubsystem<UEnhancedInputLocalPlayerSubsystem>(GetLocalPlayer());
	
	EnhancedInputSubsystem->AddMappingContext(IMC_PlayerInputMappingContext,0);
	
	UMyInputComponent* MyInputComp=Cast<UMyInputComponent>(InputComponent);
	MyInputComp->BindAction(IA_Move,ETriggerEvent::Triggered,this,&AMyPlayerController::Move);
	
	MyInputComp->BindAbilityAction(InputConfig,this,&AMyPlayerController::PressedFunc,&AMyPlayerController::HeldFunc,&AMyPlayerController::ReleasedFunc);
}

void AMyPlayerController::BeginPlay()
{
	Super::BeginPlay();
	FInputModeGameAndUI InputMode;
	InputMode.SetHideCursorDuringCapture(false);
	InputMode.SetLockMouseToViewportBehavior(EMouseLockMode::DoNotLock);
	
	SetInputMode(InputMode);
	bShowMouseCursor=true;
}

void AMyPlayerController::Move(const FInputActionValue& Value)
{
	const FVector2d InputVal= Value.Get<FVector2d>();
	FRotationMatrix RotMat=FRotationMatrix(GetControlRotation());
	FVector ForwardDir=RotMat.GetUnitAxis(EAxis::X);
	FVector RightVector=RotMat.GetUnitAxis(EAxis::Y);
	GetCharacter()->AddMovementInput(ForwardDir,InputVal.X);
	GetCharacter()->AddMovementInput(RightVector,InputVal.Y);
}

void AMyPlayerController::AutoMove()
{
	if (!bIsAutoRunning)return;
	float Dist= (GetCharacter()->GetActorLocation()-CachedLocation).SizeSquared();
	if (Dist<DistThreshold)
	{
		bIsAutoRunning=false;
	}
	else
	{
		FVector Dir= SplineComp->FindTangentClosestToWorldLocation(GetCharacter()->GetActorLocation(),ESplineCoordinateSpace::World);
		GetCharacter()->AddMovementInput(Dir*MovementSpeed,1);
	}
}

void AMyPlayerController::CursorTrace()
{
	GetHitResultUnderCursor(ECC_Visibility,false,HitResult);
	LastActor=ThisActor;
	ThisActor=Cast<IMyHighlightInterface>(HitResult.GetActor());
	// if (!HitResult.bBlockingHit) return;
	if (ThisActor)
	{
		ThisActor->Highlight();
	}
	if (LastActor)
	{
		LastActor->UnHighlight();
	}
	bIsTargeting=ThisActor!=nullptr;
}

void AMyPlayerController::PressedFunc(FGameplayTag InputTag)
{
	PressedTime=0;
	UMyAbilitySystemComponent* MyASC=GetPlayerState<AMyPlayerState>()->MyAbilitySystemComponent;
	
	for (auto Ability:MyASC->GetActivatableAbilities())
	{
		FGameplayTagContainer AbilityTags=Ability.GetDynamicSpecSourceTags();
		if (InputTag.MatchesTagExact(AbilityTags.First()))
		{
			MyASC->TryActivateAbility(Ability.Handle);
		}
	}
}

void AMyPlayerController::HeldFunc(FGameplayTag InputTag)
{
	PressedTime+=GetWorld()->DeltaTimeSeconds;
}

void AMyPlayerController::ReleasedFunc(FGameplayTag InputTag)
{
	if (InputTag == MyTags::Input_LMB)
	{
		if (PressedTime>PressedTimeThreshold)return;
		if (!bIsTargeting)
		{
			CachedLocation=HitResult.ImpactPoint;
			FVector PathStart= GetCharacter()->GetActorLocation();
			UNavigationPath* NavigationPath=UNavigationSystemV1::FindPathToLocationSynchronously(this,PathStart,CachedLocation);
			for (auto Point:NavigationPath->PathPoints)
			{
				SplineComp->AddSplinePoint(Point,ESplineCoordinateSpace::World,true);
				DrawDebugSphere(GetWorld(),Point,10,10,FColor::Red,false,0.1f);
			}
			bIsAutoRunning=true;
		}
	}
}


