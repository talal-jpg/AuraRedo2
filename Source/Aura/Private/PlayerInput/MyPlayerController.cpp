// Fill out your copyright notice in the Description page of Project Settings.


#include "PlayerInput/MyPlayerController.h"
#include "EnhancedInputComponent.h"
#include "EnhancedInputSubsystems.h"
#include "Kismet/GameplayStatics.h"


class UEnhancedPlayerInput;
class UEnhancedInputLocalPlayerSubsystem;

void AMyPlayerController::SetupInputComponent()
{
	Super::SetupInputComponent();
	
	
	UEnhancedInputLocalPlayerSubsystem* EnhancedInputSubsystem=ULocalPlayer::GetSubsystem<UEnhancedInputLocalPlayerSubsystem>(GetLocalPlayer());
	
	EnhancedInputSubsystem->AddMappingContext(IMC_PlayerInputMappingContext,0);
	
	UEnhancedInputComponent* EnhancedInputComp=Cast<UEnhancedInputComponent>(InputComponent);
	EnhancedInputComp->BindAction(IA_Move,ETriggerEvent::Started,this,&AMyPlayerController::Move);
}

void AMyPlayerController::Move(const FInputActionValue& Value)
{
	
}

