// Fill out your copyright notice in the Description page of Project Settings.


#include "Airship/AirshipPilotComponent.h"

#include "Airship/AirshipHUDWidget.h"
#include "Airship/AirshipPawn.h"
#include "Airship/AirshipSettings.h"
#include "Airship/AirshipSubsystem.h"
#include "Airship/AirshipTurret.h"
#include "Blueprint/GameViewportSubsystem.h"
#include "Camera/CameraComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/LocalPlayer.h"
#include "Engine/World.h"
#include "EnhancedInputComponent.h"
#include "EnhancedInputSubsystems.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/SpringArmComponent.h"
#include "InputAction.h"
#include "InputActionValue.h"
#include "InputMappingContext.h"
#include "Interfaces/MyCombatInterface.h"
#include "Match/MyTeamLibrary.h"
#include "UI/Settings/MyGameUserSettings.h"

DEFINE_LOG_CATEGORY_STATIC(LogAirshipPilot, Log, All);

TMulticastDelegate<void(const APlayerController*, EAirshipUseRefusal)> UAirshipPilotComponent::OnLocalUseRefused;

UAirshipPilotComponent::UAirshipPilotComponent()
{
	// Only ticks on the owning client: until its input is set up (every 0.25 s), and every frame while its player mans a gun
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

	// A client's controller can begin play before its local player is set: try again for a while
	SetupRetryTime = 0.f;
	bSetupRetrying = !TrySetupLocalInput();
	UpdateTickState();
}

void UAirshipPilotComponent::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	TeardownLocalInput();

	// Only the local input and HUD: the character is the server's (or the world's) to put down
	TeardownGunnerInput();
	HideGunnerHUD();
	LocalShip.Reset();
	LocalGunner.Reset();
	LocalStation = -1;

	Super::EndPlay(EndPlayReason);
}

void UAirshipPilotComponent::UpdateTickState()
{
	const bool bMounted = LocalStation >= 0;
	SetComponentTickInterval(bMounted ? 0.f : 0.25f);
	SetComponentTickEnabled(bMounted || bSetupRetrying);
}

void UAirshipPilotComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);

	if (bSetupRetrying)
	{
		SetupRetryTime += DeltaTime;

		if (TrySetupLocalInput() || SetupRetryTime > 30.f)
		{
			bSetupRetrying = false;
		}
	}

	if (LocalStation >= 0)
	{
		TickLocalGunner(DeltaTime);
	}

	UpdateTickState();
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

	// Manning a gun: IMC_Airship's F (IA_AirshipExit) normally takes it first (OnGunnerExit)
	if (LocalStation >= 0)
	{
		RequestDismount();
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

void UAirshipPilotComponent::RequestDismount()
{
	ServerRequestDismount();
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
		TryUseNearest();
	}
}

void UAirshipPilotComponent::ServerRequestExit_Implementation()
{
	if (ConsumeRequestCooldown())
	{
		TryExit();
	}
}

void UAirshipPilotComponent::ServerRequestMount_Implementation(AAirshipPawn* Ship, uint8 Station)
{
	if (ConsumeRequestCooldown())
	{
		TryMount(Ship, Station, false);
	}
}

void UAirshipPilotComponent::ServerRequestDismount_Implementation()
{
	if (ConsumeRequestCooldown())
	{
		TryDismount();
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
		// Never the other team's ship (CanBoard is server only; the replicated team ids answer this on any machine)
		if (!Ship || Ship->IsAirshipDead() || Ship->HasPilot() || !UMyTeamLibrary::CanUseShip(Pawn, Ship)
			|| !Ship->IsWithinBoardRange(Location, Settings->BoardDistance, Settings->BoardHullDistance, Settings->BoardBelowDistance))
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
			// Console: the nearest free living ship the player may use, any distance (a nearer enemy ship is skipped)
			const UAirshipSubsystem* Subsystem = UAirshipSubsystem::Get(this);
			Ship = Subsystem ? Subsystem->FindNearestAirship(Character->GetActorLocation(), true, Character) : nullptr;
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

		if (!Ship->IsWithinBoardRange(Character->GetActorLocation(), Settings->BoardDistance, Settings->BoardHullDistance, Settings->BoardBelowDistance))
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

bool UAirshipPilotComponent::FindServerStation(AAirshipPawn*& OutShip, int32& OutStation) const
{
	OutShip = nullptr;
	OutStation = INDEX_NONE;

	const APlayerController* PC = GetPlayerController();
	const ACharacter* Character = PC ? Cast<ACharacter>(PC->GetPawn()) : nullptr;
	const UAirshipSubsystem* Subsystem = UAirshipSubsystem::Get(this);

	return PC && PC->HasAuthority() && Character && Subsystem && Subsystem->FindGunnerStation(Character, OutShip, OutStation);
}

bool UAirshipPilotComponent::TryUseNearest()
{
	APlayerController* PC = GetPlayerController();
	ACharacter* Character = PC ? Cast<ACharacter>(PC->GetPawn()) : nullptr;
	const UAirshipSubsystem* Subsystem = UAirshipSubsystem::Get(this);

	if (!PC || !PC->HasAuthority() || !Character || !Subsystem)
	{
		return false;
	}

	// A gunner's F leaves the station (normally its Exit key sends the dismount itself)
	AAirshipPawn* GunnerShip = nullptr;
	int32 GunnerStation = INDEX_NONE;

	if (FindServerStation(GunnerShip, GunnerStation))
	{
		return TryDismount();
	}

	// The nearest wins: the helm of a free living ship in its own range (distance to the pilot seat), or a free station
	// in range (3D distance to its seat). From the deck the helm is always in range (BoardHullDistance), so standing at
	// a gun mans it and standing elsewhere takes the helm.
	const UAirshipSettings* Settings = UAirshipSettings::Get();
	const FVector Location = Character->GetActorLocation();
	AAirshipPawn* BestShip = nullptr;
	int32 BestStation = INDEX_NONE;
	double BestDistSq = TNumericLimits<double>::Max();
	const AAirshipPawn* EnemyShipInRange = nullptr;

	for (AAirshipPawn* Ship : Subsystem->GetAirships())
	{
		if (!Ship || Ship->IsAirshipDead())
		{
			continue;
		}

		// Team match: the other team's ship is never used; remembered for the refusal's reason (its helm or a gun in range)
		if (!UMyTeamLibrary::CanUseShip(Character, Ship))
		{
			bool bInRange = Ship->IsWithinBoardRange(Location, Settings->BoardDistance, Settings->BoardHullDistance, Settings->BoardBelowDistance);

			for (int32 Station = 0; Station < Airship::NumStations && !bInRange; ++Station)
			{
				bInRange = Ship->IsWithinStationRange(Station, Location);
			}

			if (bInRange)
			{
				EnemyShipInRange = Ship;
			}
			continue;
		}

		if (!Ship->HasPilot() && Ship->CanBoard(Character)
			&& Ship->IsWithinBoardRange(Location, Settings->BoardDistance, Settings->BoardHullDistance, Settings->BoardBelowDistance))
		{
			const double DistSq = FVector::DistSquared(Location, Ship->GetPilotSeatLocation());

			if (DistSq < BestDistSq)
			{
				BestDistSq = DistSq;
				BestShip = Ship;
				BestStation = INDEX_NONE;
			}
		}

		for (int32 Station = 0; Station < Airship::NumStations; ++Station)
		{
			if (!Ship->IsWithinStationRange(Station, Location) || !Ship->CanMount(Character, Station))
			{
				continue;
			}

			const double DistSq = FVector::DistSquared(Location, Ship->GetStationSeatLocation(Station));

			if (DistSq < BestDistSq)
			{
				BestDistSq = DistSq;
				BestShip = Ship;
				BestStation = Station;
			}
		}
	}

	if (!BestShip)
	{
		const EAirshipUseRefusal Reason = EnemyShipInRange ? EAirshipUseRefusal::EnemyShip : EAirshipUseRefusal::NothingInRange;
		UE_LOG(LogAirshipPilot, Log, TEXT("%s: F refused (%s)"), *Character->GetName(),
			EnemyShipInRange ? *FString::Printf(TEXT("%s is the other team's ship"), *EnemyShipInRange->GetName()) : TEXT("no free helm or gun in range"));
		ClientUseRefused(Reason);
		return false;
	}

	if (BestStation == INDEX_NONE)
	{
		const bool bBoarded = BestShip->BoardPilot(Character, PC);
		UE_LOG(LogAirshipPilot, Log, TEXT("%s -> %s: %s"), *Character->GetName(), *BestShip->GetName(), bBoarded ? TEXT("boarded") : TEXT("refused"));
		return bBoarded;
	}

	const bool bMounted = BestShip->MountGunner(Character, PC, BestStation);
	UE_LOG(LogAirshipPilot, Log, TEXT("%s -> %s station %d: %s"), *Character->GetName(), *BestShip->GetName(), BestStation, bMounted ? TEXT("manned") : TEXT("refused"));
	return bMounted;
}

void UAirshipPilotComponent::ClientUseRefused_Implementation(EAirshipUseRefusal Reason)
{
	// The local player's own machine (a local controller on the server runs it at once): the HUD's toast. The log line
	// is the harness's proof that the client got it (M2.1)
	UE_LOG(LogAirshipPilot, Log, TEXT("%s: use refused (%s) on this machine"), *GetNameSafe(GetOwner()), *UEnum::GetValueAsString(Reason));
	OnLocalUseRefused.Broadcast(GetPlayerController(), Reason);
}

bool UAirshipPilotComponent::TryMount(AAirshipPawn* Ship, int32 Station, bool bIgnoreRange)
{
	APlayerController* PC = GetPlayerController();
	ACharacter* Character = PC ? Cast<ACharacter>(PC->GetPawn()) : nullptr;

	if (!PC || !PC->HasAuthority() || !Character || Station < 0 || Station >= Airship::NumStations)
	{
		return false;
	}

	const FVector Location = Character->GetActorLocation();

	if (!Ship)
	{
		// The nearest living ship (by that station's seat) where it is free
		const UAirshipSubsystem* Subsystem = UAirshipSubsystem::Get(this);
		double BestDistSq = TNumericLimits<double>::Max();

		for (AAirshipPawn* Candidate : Subsystem ? Subsystem->GetAirships() : TArray<AAirshipPawn*>())
		{
			if (!Candidate || !Candidate->CanMount(Character, Station) || (!bIgnoreRange && !Candidate->IsWithinStationRange(Station, Location)))
			{
				continue;
			}

			const double DistSq = FVector::DistSquared(Location, Candidate->GetStationSeatLocation(Station));

			if (DistSq < BestDistSq)
			{
				BestDistSq = DistSq;
				Ship = Candidate;
			}
		}
	}

	if (!Ship || (!bIgnoreRange && !Ship->IsWithinStationRange(Station, Location)))
	{
		UE_LOG(LogAirshipPilot, Log, TEXT("%s: station %d refused (no ship with it free%s)"), *Character->GetName(), Station, bIgnoreRange ? TEXT("") : TEXT(" in range"));
		return false;
	}

	const bool bMounted = Ship->MountGunner(Character, PC, Station);
	UE_LOG(LogAirshipPilot, Log, TEXT("%s -> %s station %d: %s"), *Character->GetName(), *Ship->GetName(), Station, bMounted ? TEXT("manned") : TEXT("refused"));
	return bMounted;
}

bool UAirshipPilotComponent::TryDismount()
{
	AAirshipPawn* Ship = nullptr;
	int32 Station = INDEX_NONE;

	if (!FindServerStation(Ship, Station))
	{
		return false;
	}

	Ship->DismountGunner(Station, false);
	return true;
}


// =============================================================================
// Gunner RPCs (server)
// =============================================================================

void UAirshipPilotComponent::ServerSetGunnerAim_Implementation(FVector_NetQuantize AimPoint)
{
	AAirshipPawn* Ship = nullptr;
	int32 Station = INDEX_NONE;

	// Nothing from the client is trusted beyond its aim (the ship checks it is finite and near)
	if (FindServerStation(Ship, Station) && !AimPoint.ContainsNaN())
	{
		Ship->SetStationAim(Station, AimPoint);
	}
}

void UAirshipPilotComponent::ServerGunnerFire_Implementation(FVector_NetQuantize AimPoint)
{
	AAirshipPawn* Ship = nullptr;
	int32 Station = INDEX_NONE;

	if (!FindServerStation(Ship, Station) || !Airship::IsCannonStation(Station) || AimPoint.ContainsNaN())
	{
		return;
	}

	// The ship checks the cannon's reload
	Ship->SetStationAim(Station, AimPoint);
	Ship->FireStation(Station, AimPoint);
}

void UAirshipPilotComponent::ServerGunnerTrigger_Implementation(bool bHeld, FVector_NetQuantize AimPoint)
{
	AAirshipPawn* Ship = nullptr;
	int32 Station = INDEX_NONE;

	if (!FindServerStation(Ship, Station) || !Airship::IsTurretStation(Station))
	{
		return;
	}

	if (!AimPoint.ContainsNaN())
	{
		Ship->SetStationAim(Station, AimPoint);
	}

	Ship->SetStationTrigger(Station, bHeld);
}

void UAirshipPilotComponent::ClientMountChanged_Implementation(AAirshipPawn* Ship, int8 Station, FVector_NetQuantize ExitHullLocal, FVector_NetQuantize LaunchVelocity)
{
	if (Ship && Station >= 0)
	{
		BeginLocalGunner(Ship, Station);
	}
	else
	{
		EndLocalGunner(LocalShip.Get(), ExitHullLocal, LaunchVelocity, true);
	}
}


// =============================================================================
// The local gunner (the owning machine)
// =============================================================================

void UAirshipPilotComponent::BeginLocalGunner(AAirshipPawn* Ship, int32 Station)
{
	APlayerController* PC = GetPlayerController();

	if (!PC || !PC->IsLocalController() || !Ship || !Ship->GetHull() || Station < 0 || Station >= Airship::NumStations)
	{
		return;
	}

	// A new station without a dismount in between (never expected): the old one's input and HUD go first
	if (LocalStation >= 0)
	{
		EndLocalGunner(LocalShip.Get(), FVector::ZeroVector, FVector::ZeroVector, false);
	}

	ACharacter* Character = Cast<ACharacter>(PC->GetPawn());
	LocalShip = Ship;
	LocalGunner = Character;
	LocalStation = Station;
	LocalStationMissingTime = 0.f;
	bLocalStationConfirmed = false;
	bLocalTrigger = false;
	bLocalAimValid = false;
	LastAimSendTime = -1000.0;
	bGunnerAimHeld = false;

	if (Character)
	{
		// A client's own copy rides the hull at the seat as the server's does (the replicated attachment then agrees).
		// Its movement is off: no moves sent while attached to a simulated hull. A correction of a move sent before the
		// mount (the server acks those, MountGunner, but one may already be on the way) would set the attached capsule's
		// world location from the server's clock of the hull: it is ignored until the dismount.
		if (!PC->HasAuthority())
		{
			if (UCharacterMovementComponent* Move = Character->GetCharacterMovement())
			{
				if (!bHasSavedClientIgnoreCorrections)
				{
					bSavedClientIgnoreCorrections = Move->bClientIgnoreMovementCorrections;
					bHasSavedClientIgnoreCorrections = true;
				}
				Move->bClientIgnoreMovementCorrections = true;
				Move->StopMovementImmediately();
				Move->DisableMovement();
				Move->SetComponentTickEnabled(false);
			}

			Character->AttachToComponent(Ship->GetHull(), FAttachmentTransformRules::SnapToTargetNotIncludingScale);
			Character->SetActorRelativeTransform(Ship->GetStationSeatRelativeTransform(Station, Character));
		}

		// The view starts along the gun, a little down
		const FTransform SeatTM = Ship->GetStationSeatRelativeTransform(Station, Character) * Ship->GetHull()->GetComponentTransform();
		PC->SetControlRotation(FRotator(-5.0, SeatTM.Rotator().Yaw, 0.0));

		// The camera's FOV and arm length at mount (Aim and Zoom change them, the dismount restores them)
		bHasSavedFOV = false;
		bHasSavedArm = false;

		if (const UCameraComponent* Camera = Character->FindComponentByClass<UCameraComponent>())
		{
			SavedFOV = Camera->FieldOfView;
			bHasSavedFOV = true;
		}

		if (const USpringArmComponent* Arm = Character->FindComponentByClass<USpringArmComponent>())
		{
			SavedArmLength = Arm->TargetArmLength;
			bHasSavedArm = true;
		}
	}

	SetupGunnerInput();
	ShowGunnerHUD();
	UpdateTickState();

	UE_LOG(LogAirshipPilot, Log, TEXT("%s: manning %s station %d on this machine"), *GetNameSafe(Character), *Ship->GetName(), Station);
}

void UAirshipPilotComponent::EndLocalGunner(AAirshipPawn* Ship, const FVector& ExitHullLocal, const FVector& LaunchVelocity, bool bPlaceCharacter)
{
	if (LocalStation < 0 && !GunnerInputComponent && !GunnerHUDWidget)
	{
		return;
	}

	APlayerController* PC = GetPlayerController();
	ACharacter* Character = LocalGunner.Get();

	// The client's own copy of the turret: no more predicted rounds (its local command would hold the trigger a moment)
	if (Ship && Airship::IsTurretStation(LocalStation) && PC && !PC->HasAuthority())
	{
		if (AAirshipTurret* Turret = Ship->GetTurret(Airship::StationToTurret(LocalStation)))
		{
			FAirshipTurretCommand Release;
			Release.AimPoint = LocalAim;
			Release.bHasAim = bLocalAimValid;
			Release.Instigator = Character;
			Turret->SetLocalCommand(Release);
		}
	}

	TeardownGunnerInput();
	HideGunnerHUD();

	if (Character)
	{
		if (UCameraComponent* Camera = Character->FindComponentByClass<UCameraComponent>(); Camera && bHasSavedFOV)
		{
			Camera->SetFieldOfView(SavedFOV);
		}

		if (USpringArmComponent* Arm = Character->FindComponentByClass<USpringArmComponent>(); Arm && bHasSavedArm)
		{
			Arm->TargetArmLength = SavedArmLength;
		}
	}

	// A client's own copy takes the server's corrections again (its moves restart below)
	if (bHasSavedClientIgnoreCorrections)
	{
		if (UCharacterMovementComponent* Move = Character ? Character->GetCharacterMovement() : nullptr)
		{
			Move->bClientIgnoreMovementCorrections = bSavedClientIgnoreCorrections;
		}
		bHasSavedClientIgnoreCorrections = false;
	}

	// A client's own copy: off the hull where the server put it (hull-relative, against this machine's hull), falling
	// with the launch. The server (a listen host's own player) already did all of it.
	if (Character && PC && !PC->HasAuthority() && PC->GetPawn() == Character)
	{
		if (Ship ? Character->IsAttachedTo(Ship) : Character->GetAttachParentActor() != nullptr)
		{
			Character->DetachFromActor(FDetachmentTransformRules::KeepWorldTransform);
		}

		if (bPlaceCharacter && Ship && Ship->GetHull() && !ExitHullLocal.IsNearlyZero())
		{
			const FVector Exit = Ship->GetHull()->GetComponentTransform().TransformPosition(ExitHullLocal);
			Character->SetActorLocationAndRotation(Exit, FRotator(0.0, Ship->GetActorRotation().Yaw, 0.0), false, nullptr, ETeleportType::TeleportPhysics);
		}

		const bool bDead = Character->Implements<UMyCombatInterface>() && IMyCombatInterface::Execute_IsDead(Character);

		if (UCharacterMovementComponent* Move = Character->GetCharacterMovement())
		{
			Move->SetComponentTickEnabled(true);

			if (!bDead && Move->MovementMode == MOVE_None)
			{
				Move->SetMovementMode(MOVE_Falling);
			}

			if (!bDead && bPlaceCharacter)
			{
				Move->Velocity = LaunchVelocity;
			}
		}
	}

	UE_LOG(LogAirshipPilot, Log, TEXT("%s: left station %d on this machine%s"), *GetNameSafe(Character), LocalStation, bPlaceCharacter ? TEXT("") : TEXT(" (local safety net)"));

	LocalShip.Reset();
	LocalGunner.Reset();
	LocalStation = -1;
	bLocalTrigger = false;
	bGunnerAimHeld = false;
	bHasSavedFOV = false;
	bHasSavedArm = false;
	UpdateTickState();
}

void UAirshipPilotComponent::SetupGunnerInput()
{
	APlayerController* PC = GetPlayerController();
	const ULocalPlayer* LocalPlayer = PC ? PC->GetLocalPlayer() : nullptr;
	UEnhancedInputLocalPlayerSubsystem* Subsystem = LocalPlayer ? LocalPlayer->GetSubsystem<UEnhancedInputLocalPlayerSubsystem>() : nullptr;

	if (!PC || !PC->IsLocalController() || GunnerInputComponent)
	{
		return;
	}

	// The flying keys (IMC_Airship above IMC_PlayerMappings): a gunner's on-foot movement, jump and the abilities on
	// those keys stay quiet, and its own Look / Fire / Aim / Zoom / Exit come here
	const UAirshipSettings* Settings = UAirshipSettings::Get();
	auto Load = [](const TSoftObjectPtr<UInputAction>& Soft) -> const UInputAction*
	{
		return Soft.IsNull() ? nullptr : Soft.LoadSynchronous();
	};

	const UInputAction* LookAction = Load(Settings->LookAction);
	const UInputAction* FireAction = Load(Settings->FireAction);
	const UInputAction* AimAction = Load(Settings->AimAction);
	const UInputAction* ZoomAction = Load(Settings->ZoomAction);
	const UInputAction* ExitAction = Load(Settings->ExitAction);
	const UInputMappingContext* Context = Settings->AirshipMappingContext.IsNull() ? nullptr : Settings->AirshipMappingContext.LoadSynchronous();

	// No fixed name: a component of an earlier mount may still wait for the garbage collector
	GunnerInputComponent = NewObject<UEnhancedInputComponent>(PC, UEnhancedInputComponent::StaticClass());
	GunnerInputComponent->RegisterComponent();

	for (const UInputAction* Action : { Load(Settings->ThrottleAction), Load(Settings->SteerAction), Load(Settings->LiftAction), Load(Settings->StrafeAction),
		Load(Settings->BoostAction), Load(Settings->BrakeAction), FireAction, LookAction, ZoomAction, ExitAction, AimAction })
	{
		if (Action)
		{
			GunnerInputComponent->BindActionValue(Action);
		}
	}

	if (LookAction)
	{
		GunnerInputComponent->BindAction(LookAction, ETriggerEvent::Triggered, this, &ThisClass::OnGunnerLook);
	}

	if (FireAction)
	{
		GunnerInputComponent->BindAction(FireAction, ETriggerEvent::Started, this, &ThisClass::OnGunnerFireStarted);
		GunnerInputComponent->BindAction(FireAction, ETriggerEvent::Completed, this, &ThisClass::OnGunnerFireReleased);
		GunnerInputComponent->BindAction(FireAction, ETriggerEvent::Canceled, this, &ThisClass::OnGunnerFireReleased);
	}

	if (AimAction)
	{
		GunnerInputComponent->BindAction(AimAction, ETriggerEvent::Started, this, &ThisClass::OnGunnerAimStarted);
		GunnerInputComponent->BindAction(AimAction, ETriggerEvent::Completed, this, &ThisClass::OnGunnerAimReleased);
		GunnerInputComponent->BindAction(AimAction, ETriggerEvent::Canceled, this, &ThisClass::OnGunnerAimReleased);
	}

	if (ZoomAction)
	{
		GunnerInputComponent->BindAction(ZoomAction, ETriggerEvent::Triggered, this, &ThisClass::OnGunnerZoom);
	}

	if (ExitAction)
	{
		GunnerInputComponent->BindAction(ExitAction, ETriggerEvent::Started, this, &ThisClass::OnGunnerExit);
	}

	PC->PushInputComponent(GunnerInputComponent);

	if (Subsystem && Context)
	{
		FModifyContextOptions Options;
		Options.bNotifyUserSettings = true;
		Subsystem->AddMappingContext(Context, Settings->AirshipMappingPriority, Options);
		GunnerMappingSubsystem = Subsystem;
		GunnerMappingContext = Context;
	}
	else
	{
		UE_LOG(LogAirshipPilot, Warning, TEXT("%s: no IMC_Airship (Project Settings > Game > Airship): the gunner's keys are the on-foot ones"), *GetName());
	}
}

void UAirshipPilotComponent::TeardownGunnerInput()
{
	if (UEnhancedInputLocalPlayerSubsystem* Subsystem = GunnerMappingSubsystem.Get())
	{
		if (const UInputMappingContext* Context = GunnerMappingContext.Get())
		{
			FModifyContextOptions Options;
			Options.bNotifyUserSettings = true;
			Subsystem->RemoveMappingContext(Context, Options);
		}
	}

	GunnerMappingSubsystem.Reset();
	GunnerMappingContext.Reset();

	if (GunnerInputComponent)
	{
		if (APlayerController* PC = GetPlayerController())
		{
			PC->PopInputComponent(GunnerInputComponent);
		}

		GunnerInputComponent->DestroyComponent();
		GunnerInputComponent = nullptr;
	}
}

void UAirshipPilotComponent::ShowGunnerHUD()
{
	APlayerController* PC = GetPlayerController();
	UGameViewportSubsystem* ViewportSubsystem = UGameViewportSubsystem::Get();
	AAirshipPawn* Ship = LocalShip.Get();

	if (!PC || !PC->IsLocalController() || !ViewportSubsystem || !Ship || GunnerHUDWidget || PC->GetNetMode() == NM_DedicatedServer)
	{
		return;
	}

	UAirshipHUDWidget* Widget = CreateWidget<UAirshipHUDWidget>(PC, UAirshipHUDWidget::StaticClass());

	if (!Widget)
	{
		return;
	}

	// Gunner mode before it is added; over the whole viewport (crosshair, the gun's mark, the panel bottom-left)
	Widget->SetGunnerStation(Ship, LocalStation);
	FGameViewportWidgetSlot FullScreenSlot;
	FullScreenSlot.ZOrder = 1;

	ULocalPlayer* LocalPlayer = PC->GetLocalPlayer();
	const bool bAdded = LocalPlayer ? ViewportSubsystem->AddWidgetForPlayer(Widget, LocalPlayer, FullScreenSlot) : ViewportSubsystem->AddWidget(Widget, FullScreenSlot);

	if (!bAdded)
	{
		Widget->SetGunnerStation(nullptr, -1);
		return;
	}

	GunnerHUDWidget = Widget;
}

void UAirshipPilotComponent::HideGunnerHUD()
{
	if (GunnerHUDWidget)
	{
		GunnerHUDWidget->SetGunnerStation(nullptr, -1);
		GunnerHUDWidget->RemoveFromParent();
		GunnerHUDWidget = nullptr;
	}
}

bool UAirshipPilotComponent::ComputeGunnerAim(FVector& OutAim) const
{
	const APlayerController* PC = GetPlayerController();
	const AAirshipPawn* Ship = LocalShip.Get();

	if (!PC || !Ship)
	{
		return false;
	}

	// The character's own camera (the control rotation's view), past the ship, its crew and every cannonball
	FVector ViewLocation;
	FRotator ViewRotation;
	PC->GetPlayerViewPoint(ViewLocation, ViewRotation);
	return Ship->TraceAimPoint(ViewLocation, ViewRotation.Vector(), Ship->GetCannonAimTraceDistance(), OutAim);
}

void UAirshipPilotComponent::TickLocalGunner(float DeltaTime)
{
	AAirshipPawn* Ship = LocalShip.Get();
	APlayerController* PC = GetPlayerController();
	ACharacter* Character = LocalGunner.Get();
	const UWorld* World = GetWorld();

	// Safety net: the ship went, or the player has another pawn (respawn) without a dismount reaching this machine
	if (!Ship || Ship->IsActorBeingDestroyed() || !PC || !Character || PC->GetPawn() != Character || !World)
	{
		EndLocalGunner(Ship, FVector::ZeroVector, FVector::ZeroVector, false);
		return;
	}

	// The replicated list may come after the RPC (another actor channel): a long grace until it first lists the pawn,
	// then a second without it and this machine lets go on its own (the server's dismount normally comes first)
	if (Ship->GetStationGunner(LocalStation) != Character)
	{
		LocalStationMissingTime += DeltaTime;

		if (LocalStationMissingTime > (bLocalStationConfirmed ? 1.f : 5.f))
		{
			EndLocalGunner(Ship, FVector::ZeroVector, FVector::ZeroVector, false);
			return;
		}
	}
	else
	{
		LocalStationMissingTime = 0.f;
		bLocalStationConfirmed = true;
	}

	// Safety net (a client's own copy, before the view is read): anything that still moved the attached capsule off the
	// seat (a correction that got through, a replicated location) is put back. The seat is hull-relative, so it is the
	// same point on every machine whatever the hull's lag.
	USceneComponent* Root = Character->GetRootComponent();

	if (!PC->HasAuthority() && Root && Root->GetAttachParent() == Ship->GetHull())
	{
		constexpr double SeatDriftTolerance = 5.0;
		const FTransform Seat = Ship->GetStationSeatRelativeTransform(LocalStation, Character);

		if (FVector::DistSquared(Root->GetRelativeLocation(), Seat.GetLocation()) > FMath::Square(SeatDriftTolerance))
		{
			UE_LOG(LogAirshipPilot, Verbose, TEXT("%s: back on the seat of station %d (%.0f cm off)"), *Character->GetName(), LocalStation,
				FVector::Dist(Root->GetRelativeLocation(), Seat.GetLocation()));
			Character->SetActorRelativeTransform(Seat);
		}
	}

	FVector Aim;
	bLocalAimValid = ComputeGunnerAim(Aim);

	if (!bLocalAimValid)
	{
		return;
	}

	LocalAim = Aim;

	// This machine's barrel tracks at once; a client's own turret copy aims and predicts its rounds
	Ship->SetLocalStationAim(LocalStation, Aim);

	if (!PC->HasAuthority() && Airship::IsTurretStation(LocalStation))
	{
		if (AAirshipTurret* Turret = Ship->GetTurret(Airship::StationToTurret(LocalStation)))
		{
			FAirshipTurretCommand Command;
			Command.AimPoint = Aim;
			Command.bHasAim = true;
			Command.bTrigger = bLocalTrigger;
			Command.Instigator = Character;
			Turret->SetLocalCommand(Command);
		}
	}

	// The listen host's own gunner: straight to the ship, every frame
	if (PC->HasAuthority())
	{
		Ship->SetStationAim(LocalStation, Aim);
		return;
	}

	// A client: at most GunnerAimSendRate per second, when the point moved, and a heartbeat (unreliable)
	const UAirshipSettings* Settings = UAirshipSettings::Get();
	const double Now = World->GetTimeSeconds();
	const double SinceSend = Now - LastAimSendTime;

	if (SinceSend >= 1.0 / FMath::Max(Settings->GunnerAimSendRate, 1.f)
		&& (FVector::DistSquared(Aim, LastSentAim) > FMath::Square(Settings->GunnerAimSendMinDelta) || SinceSend >= Settings->GunnerAimHeartbeat))
	{
		ServerSetGunnerAim(Aim);
		LastSentAim = Aim;
		LastAimSendTime = Now;
	}
}

void UAirshipPilotComponent::RequestGunnerCannonFire()
{
	AAirshipPawn* Ship = LocalShip.Get();
	const APlayerController* PC = GetPlayerController();
	FVector Aim;

	if (!Ship || !PC || !Airship::IsCannonStation(LocalStation) || !ComputeGunnerAim(Aim))
	{
		return;
	}

	LocalAim = Aim;

	// The host fires at once (no prediction); a client shows its shot when its own reload is done, then asks
	if (PC->HasAuthority())
	{
		Ship->SetStationAim(LocalStation, Aim);
		Ship->FireStation(LocalStation, Aim);
		return;
	}

	if (Ship->PredictStationFire(LocalStation))
	{
		ServerGunnerFire(Aim);
	}
}

void UAirshipPilotComponent::SendGunnerTrigger(bool bHeld)
{
	AAirshipPawn* Ship = LocalShip.Get();
	const APlayerController* PC = GetPlayerController();

	if (!Ship || !PC || !Airship::IsTurretStation(LocalStation))
	{
		return;
	}

	FVector Aim;

	if (ComputeGunnerAim(Aim))
	{
		LocalAim = Aim;
	}

	if (PC->HasAuthority())
	{
		Ship->SetStationAim(LocalStation, LocalAim);
		Ship->SetStationTrigger(LocalStation, bHeld);
		return;
	}

	ServerGunnerTrigger(bHeld, LocalAim);
}

void UAirshipPilotComponent::OnGunnerLook(const FInputActionValue& Value)
{
	APlayerController* PC = GetPlayerController();

	if (!PC)
	{
		return;
	}

	FVector2D Look = Value.Get<FVector2D>();

	// Same as the on-foot camera and the ship's (AAirshipPawn::OnLookInput): Options > Controls sensitivity and invert
	if (const UMyGameUserSettings* GameSettings = UMyGameUserSettings::GetMyGameUserSettings())
	{
		Look *= GameSettings->GetLookSensitivity();

		if (GameSettings->GetInvertLookX())
		{
			Look.X = -Look.X;
		}
		if (GameSettings->GetInvertLookY())
		{
			Look.Y = -Look.Y;
		}
	}

	PC->AddYawInput(static_cast<float>(Look.X));
	PC->AddPitchInput(static_cast<float>(Look.Y));
}

void UAirshipPilotComponent::OnGunnerFireStarted(const FInputActionValue& Value)
{
	if (Airship::IsCannonStation(LocalStation))
	{
		RequestGunnerCannonFire();
	}
	else if (Airship::IsTurretStation(LocalStation) && !bLocalTrigger)
	{
		bLocalTrigger = true;
		SendGunnerTrigger(true);
	}
}

void UAirshipPilotComponent::OnGunnerFireReleased(const FInputActionValue& Value)
{
	if (Airship::IsTurretStation(LocalStation) && bLocalTrigger)
	{
		bLocalTrigger = false;
		SendGunnerTrigger(false);
	}
}

void UAirshipPilotComponent::OnGunnerAimStarted(const FInputActionValue& Value)
{
	const ACharacter* Character = LocalGunner.Get();
	UCameraComponent* Camera = Character ? Character->FindComponentByClass<UCameraComponent>() : nullptr;

	if (!Camera || bGunnerAimHeld)
	{
		return;
	}

	if (!bHasSavedFOV)
	{
		SavedFOV = Camera->FieldOfView;
		bHasSavedFOV = true;
	}

	bGunnerAimHeld = true;
	Camera->SetFieldOfView(FMath::Clamp(SavedFOV + UAirshipSettings::Get()->GunnerAimFOVOffset, 10.f, 170.f));
}

void UAirshipPilotComponent::OnGunnerAimReleased(const FInputActionValue& Value)
{
	const ACharacter* Character = LocalGunner.Get();
	UCameraComponent* Camera = Character ? Character->FindComponentByClass<UCameraComponent>() : nullptr;
	bGunnerAimHeld = false;

	if (Camera && bHasSavedFOV)
	{
		Camera->SetFieldOfView(SavedFOV);
	}
}

void UAirshipPilotComponent::OnGunnerZoom(const FInputActionValue& Value)
{
	const ACharacter* Character = LocalGunner.Get();
	USpringArmComponent* Arm = Character ? Character->FindComponentByClass<USpringArmComponent>() : nullptr;

	if (!Arm)
	{
		return;
	}

	if (!bHasSavedArm)
	{
		SavedArmLength = Arm->TargetArmLength;
		bHasSavedArm = true;
	}

	// Wheel up (+) = closer, as the ship's zoom; within a range around the arm length at mount
	const UAirshipSettings* Settings = UAirshipSettings::Get();
	const float MinLength = SavedArmLength * FMath::Min(Settings->GunnerZoomMinScale, Settings->GunnerZoomMaxScale);
	const float MaxLength = SavedArmLength * FMath::Max(Settings->GunnerZoomMinScale, Settings->GunnerZoomMaxScale);
	Arm->TargetArmLength = FMath::Clamp(Arm->TargetArmLength - Value.Get<float>() * Settings->GunnerZoomStep, MinLength, MaxLength);
}

void UAirshipPilotComponent::OnGunnerExit(const FInputActionValue& Value)
{
	// F: IMC_Airship's IA_AirshipExit takes the key from IA_AirshipBoard (OnBoardPressed never sees it)
	RequestDismount();
}
