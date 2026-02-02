// Fill out your copyright notice in the Description page of Project Settings.


#include "PlayerInput/MyPlayerController.h"
#include "EnhancedInputComponent.h"
#include "EnhancedInputSubsystems.h"
#include "NavigationPath.h"
#include "NavigationSystem.h"
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
}

void AMyPlayerController::SetupInputComponent()
{
	Super::SetupInputComponent();
	
	UEnhancedInputLocalPlayerSubsystem* EnhancedInputSubsystem=ULocalPlayer::GetSubsystem<UEnhancedInputLocalPlayerSubsystem>(GetLocalPlayer());
	
	EnhancedInputSubsystem->AddMappingContext(IMC_PlayerInputMappingContext,0);
	
	UMyInputComponent* MyInputComp=Cast<UMyInputComponent>(InputComponent);
	MyInputComp->BindAction(IA_Move,ETriggerEvent::Triggered,this,&AMyPlayerController::Move);
	
	MyInputComp->BindAbilityAction(InputConfig,this,PressedFunc,HeldFunc,ReleasedFunc);
	
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

void AMyPlayerController::AutoMove(const FInputActionValue& Value)
{
	if (ThisActor==nullptr)
	{
		CachedLocation=HitResult.ImpactPoint;
		FVector PathStart= GetCharacter()->GetActorLocation();
		UNavigationPath* NavigationPath=UNavigationSystemV1::FindPathToLocationSynchronously(this,PathStart,CachedLocation);
		for (auto Point:NavigationPath->PathPoints)
		{
			SplineComp->AddSplinePoint(Point,ESplineCoordinateSpace::World,true);
		}
		
		GetCharacter()->AddMovementInput()
		
		
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
	
}

void AMyPlayerController::PressedFunc(FGameplayTag InputTag)
{
	
}

void AMyPlayerController::HeldFunc(FGameplayTag InputTag)
{
}

void AMyPlayerController::ReleasedFunc(FGameplayTag InputTag)
{
}


