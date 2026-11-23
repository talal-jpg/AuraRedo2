// Fill out your copyright notice in the Description page of Project Settings.


#include "Airship/AirshipPilotComponent.h"

#include "Airship/AirshipPawn.h"
#include "Airship/AirshipSettings.h"
#include "Airship/AirshipSubsystem.h"
#include "Engine/LocalPlayer.h"
#include "Engine/World.h"
#include "EnhancedInputComponent.h"
#include "EnhancedInputSubsystems.h"
#include "GameFramework/Character.h"
#include "GameFramework/PlayerController.h"
#include "InputAction.h"
#include "InputMappingContext.h"

DEFINE_LOG_CATEGORY_STATIC(LogAirshipPilot, Log, All);

UAirshipPilotComponent::UAirshipPilotComponent()
{
	// Only ticks on the owning client until its input is set up
	PrimaryComponentTick.bCanEverTick = true;
	PrimaryComponentTick.bStartWithTickEnabled = false;
	PrimaryComponentTick.TickInterval = 0.25f;
	SetIsReplicatedByDefault(true);
}

APlayerController* UAirshipPilotComponent::GetPlayerController() const
{
	return Cast<APlayerController>(GetOwner());
}

void UAirshipPilotComponent::BeginPlay()
{
	Super::BeginPlay();

	if (!TrySetupLocalInput())
	{
		// A client's controller can begin play before its local player is set: try again for a while
		SetupRetryTime = 0.f;
		SetComponentTickEnabled(true);
	}
}

void UAirshipPilotComponent::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	TeardownLocalInput();

	Super::EndPlay(EndPlayReason);
}

void UAirshipPilotComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);

	SetupRetryTime += DeltaTime;

	if (TrySetupLocalInput() || SetupRetryTime > 30.f)
	{
		SetComponentTickEnabled(false);
	}
}

bool UAirshipPilotComponent::TrySetupLocalInput()
{
	if (bLocalInputDone)
	{
		return true;
	}

	APlayerController* PC = GetPlayerController();

	if (!PC)
	{
		return true;
	}

	// The server's copy of a remote player's controller: nothing to do here
	if (PC->GetNetMode() != NM_Client && !PC->IsLocalController())
	{
		bLocalInputDone = true;
		return true;
	}

	const ULocalPlayer* LocalPlayer = PC->GetLocalPlayer();
	UEnhancedInputLocalPlayerSubsystem* Subsystem = LocalPlayer ? LocalPlayer->GetSubsystem<UEnhancedInputLocalPlayerSubsystem>() : nullptr;

	if (!PC->IsLocalController() || !Subsystem)
	{
		return false;
	}

	const UAirshipSettings* Settings = UAirshipSettings::Get();
	const UInputMappingContext* Context = BoardMappingContext ? BoardMappingContext.Get() : Settings->BoardMappingContext.LoadSynchronous();
	const UInputAction* Action = BoardAction ? BoardAction.Get() : Settings->BoardAction.LoadSynchronous();

	bLocalInputDone = true;

	if (!Context || !Action)
	{
		UE_LOG(LogAirshipPilot, Warning, TEXT("%s: no IMC_AirshipBoard / IA_AirshipBoard (Project Settings > Game > Airship), boarding only through Aura.Airship.Board"), *GetName());
		return true;
	}

	BoardInputComponent = NewObject<UEnhancedInputComponent>(PC, UEnhancedInputComponent::StaticClass(), TEXT("AirshipBoardInput"));
	BoardInputComponent->RegisterComponent();
	BoardInputComponent->BindAction(Action, ETriggerEvent::Started, this, &ThisClass::OnBoardPressed);
	PC->PushInputComponent(BoardInputComponent);

	Subsystem->AddMappingContext(Context, Settings->BoardMappingPriority);
	MappingSubsystem = Subsystem;
	AddedMappingContext = Context;
	return true;
}

void UAirshipPilotComponent::TeardownLocalInput()
{
	if (UEnhancedInputLocalPlayerSubsystem* Subsystem = MappingSubsystem.Get())
	{
		if (const UInputMappingContext* Context = AddedMappingContext.Get())
		{
			Subsystem->RemoveMappingContext(Context);
		}
	}

	MappingSubsystem.Reset();
	AddedMappingContext.Reset();

	if (BoardInputComponent)
	{
		if (APlayerController* PC = GetPlayerController())
		{
			PC->PopInputComponent(BoardInputComponent);
		}

		BoardInputComponent->DestroyComponent();
		BoardInputComponent = nullptr;
	}
}

void UAirshipPilotComponent::OnBoardPressed()
{
	// Flying: the ship's IMC has F (IA_AirshipExit) at a higher priority; if both fire, only the exit counts
	const APlayerController* PC = GetPlayerController();

	if (PC && Cast<AAirshipPawn>(PC->GetPawn()))
	{
		return;
	}

	RequestBoard();
}

void UAirshipPilotComponent::RequestBoard()
{
	ServerRequestBoard();
}

void UAirshipPilotComponent::RequestExit()
{
	ServerRequestExit();
}

bool UAirshipPilotComponent::ConsumeRequestCooldown()
{
	const UWorld* World = GetWorld();
	const double Now = World ? World->GetTimeSeconds() : 0.0;

	if (Now - LastRequestTime < UAirshipSettings::Get()->BoardCooldown)
	{
		return false;
	}

	LastRequestTime = Now;
	return true;
}

void UAirshipPilotComponent::ServerRequestBoard_Implementation()
{
	if (ConsumeRequestCooldown())
	{
		TryBoard(nullptr, false);
	}
}

void UAirshipPilotComponent::ServerRequestExit_Implementation()
{
	if (ConsumeRequestCooldown())
	{
		TryExit();
	}
}

AAirshipPawn* UAirshipPilotComponent::FindBoardableAirship() const
{
	const APlayerController* PC = GetPlayerController();
	const APawn* Pawn = PC ? PC->GetPawn() : nullptr;
	const UAirshipSubsystem* Subsystem = UAirshipSubsystem::Get(this);

	if (!Pawn || !Subsystem || Cast<AAirshipPawn>(Pawn))
	{
		return nullptr;
	}

	const UAirshipSettings* Settings = UAirshipSettings::Get();
	const FVector Location = Pawn->GetActorLocation();
	AAirshipPawn* Best = nullptr;
	double BestDistSq = TNumericLimits<double>::Max();

	for (AAirshipPawn* Ship : Subsystem->GetAirships())
	{
		if (!Ship || Ship->IsAirshipDead() || Ship->HasPilot() || !Ship->IsWithinBoardRange(Location, Settings->BoardDistance, Settings->BoardHullDistance))
		{
			continue;
		}

		const double DistSq = FVector::DistSquared(Location, Ship->GetPilotSeatLocation());

		if (DistSq < BestDistSq)
		{
			BestDistSq = DistSq;
			Best = Ship;
		}
	}

	return Best;
}

bool UAirshipPilotComponent::TryBoard(AAirshipPawn* Ship, bool bIgnoreRange)
{
	APlayerController* PC = GetPlayerController();

	if (!PC || !PC->HasAuthority())
	{
		return false;
	}

	ACharacter* Character = Cast<ACharacter>(PC->GetPawn());

	if (!Character)
	{
		return false;
	}

	if (!Ship)
	{
		if (bIgnoreRange)
		{
			// Console: the nearest free living ship, any distance
			const UAirshipSubsystem* Subsystem = UAirshipSubsystem::Get(this);
			Ship = Subsystem ? Subsystem->FindNearestAirship(Character->GetActorLocation(), true) : nullptr;
		}
		else
		{
			Ship = FindBoardableAirship();
		}
	}

	if (!Ship)
	{
		return false;
	}

	if (!bIgnoreRange)
	{
		const UAirshipSettings* Settings = UAirshipSettings::Get();

		if (!Ship->IsWithinBoardRange(Character->GetActorLocation(), Settings->BoardDistance, Settings->BoardHullDistance))
		{
			return false;
		}
	}

	const bool bBoarded = Ship->BoardPilot(Character, PC);
	UE_LOG(LogAirshipPilot, Log, TEXT("%s -> %s: %s"), *Character->GetName(), *Ship->GetName(), bBoarded ? TEXT("boarded") : TEXT("refused"));
	return bBoarded;
}

bool UAirshipPilotComponent::TryExit()
{
	APlayerController* PC = GetPlayerController();
	AAirshipPawn* Ship = PC ? Cast<AAirshipPawn>(PC->GetPawn()) : nullptr;

	if (!Ship || !PC->HasAuthority() || !Ship->HasPilot())
	{
		return false;
	}

	Ship->UnboardPilot(false);
	return true;
}
