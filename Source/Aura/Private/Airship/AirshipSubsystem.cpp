// Fill out your copyright notice in the Description page of Project Settings.


#include "Airship/AirshipSubsystem.h"

#include "AbilitySystemComponent.h"
#include "AbilitySystem/MyAttributeSet.h"
#include "Airship/AirshipFlightComponent.h"
#include "Airship/AirshipPawn.h"
#include "Airship/AirshipPilotComponent.h"
#include "Airship/AirshipSettings.h"
#include "Animation/AnimInstance.h"
#include "Components/PrimitiveComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Character.h"
#include "GameFramework/GameModeBase.h"
#include "GameFramework/PlayerController.h"
#include "HAL/IConsoleManager.h"
#include "TimerManager.h"
#include "UObject/UnrealType.h"

DEFINE_LOG_CATEGORY_STATIC(LogAirship, Log, All);

UAirshipSubsystem* UAirshipSubsystem::Get(const UObject* WorldContextObject)
{
	const UWorld* World = WorldContextObject ? WorldContextObject->GetWorld() : nullptr;
	return World ? World->GetSubsystem<UAirshipSubsystem>() : nullptr;
}

bool UAirshipSubsystem::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

void UAirshipSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);

	// Static event shared by every world: HandlePostLogin keeps only this world's logins
	PostLoginHandle = FGameModeEvents::GameModePostLoginEvent.AddUObject(this, &ThisClass::HandlePostLogin);
}

void UAirshipSubsystem::Deinitialize()
{
	FGameModeEvents::GameModePostLoginEvent.Remove(PostLoginHandle);
	PostLoginHandle.Reset();
	Airships.Reset();

	// The world is going away with its characters: nothing to restore
	if (UWorld* World = GetWorld())
	{
		World->GetTimerManager().ClearTimer(PassengerTimer);
	}
	Passengers.Reset();

	Super::Deinitialize();
}

void UAirshipSubsystem::OnWorldBeginPlay(UWorld& InWorld)
{
	Super::OnWorldBeginPlay(InWorld);

	// Players that logged in before (the PIE host)
	if (InWorld.GetNetMode() != NM_Client)
	{
		for (FConstPlayerControllerIterator It = InWorld.GetPlayerControllerIterator(); It; ++It)
		{
			EnsurePilotComponent(It->Get());
		}
	}
}

void UAirshipSubsystem::HandlePostLogin(AGameModeBase* GameMode, APlayerController* NewPlayer)
{
	if (GameMode && GameMode->GetWorld() == GetWorld())
	{
		EnsurePilotComponent(NewPlayer);
	}
}

void UAirshipSubsystem::EnsurePilotComponent(APlayerController* PC) const
{
	if (!PC || !PC->HasAuthority() || !UAirshipSettings::Get()->bAddPilotComponent || PC->FindComponentByClass<UAirshipPilotComponent>())
	{
		return;
	}

	// Replicated by default, so the owning client gets it (and binds the board key there)
	UAirshipPilotComponent* Component = NewObject<UAirshipPilotComponent>(PC, TEXT("AirshipPilotComponent"));
	Component->RegisterComponent();
}

void UAirshipSubsystem::RegisterAirship(AAirshipPawn* Airship)
{
	if (Airship)
	{
		Airships.AddUnique(Airship);
	}

	UpdatePassengerTimer();
}

void UAirshipSubsystem::UnregisterAirship(AAirshipPawn* Airship)
{
	Airships.RemoveAll([Airship](const TWeakObjectPtr<AAirshipPawn>& Entry)
	{
		return !Entry.IsValid() || Entry.Get() == Airship;
	});

	// Its passengers get their collision back now (the ship is no longer in the registry), unless the world ends
	const UWorld* World = GetWorld();

	if (World && !World->bIsTearingDown)
	{
		UpdatePassengers();
		UpdatePassengerTimer();
	}
}

TArray<AAirshipPawn*> UAirshipSubsystem::GetAirships() const
{
	TArray<AAirshipPawn*> Result;
	Result.Reserve(Airships.Num());

	for (const TWeakObjectPtr<AAirshipPawn>& Entry : Airships)
	{
		if (AAirshipPawn* Airship = Entry.Get())
		{
			Result.Add(Airship);
		}
	}

	return Result;
}

AAirshipPawn* UAirshipSubsystem::FindNearestAirship(const FVector& Location, bool bOnlyBoardable) const
{
	AAirshipPawn* Best = nullptr;
	double BestDistSq = TNumericLimits<double>::Max();

	for (AAirshipPawn* Airship : GetAirships())
	{
		if (bOnlyBoardable && (Airship->IsAirshipDead() || Airship->HasPilot()))
		{
			continue;
		}

		const double DistSq = FVector::DistSquared(Location, Airship->GetPilotSeatLocation());

		if (DistSq < BestDistSq)
		{
			BestDistSq = DistSq;
			Best = Airship;
		}
	}

	return Best;
}

// =============================================================================
// Deck passengers (every machine)
// =============================================================================

void UAirshipSubsystem::UpdatePassengerTimer()
{
	UWorld* World = GetWorld();

	if (!World)
	{
		return;
	}

	// Entries waiting for their collision to come back keep it going after the last ship
	FTimerManager& Timers = World->GetTimerManager();
	const bool bWanted = GetAirships().Num() > 0 || Passengers.Num() > 0;

	if (bWanted && !Timers.IsTimerActive(PassengerTimer))
	{
		Timers.SetTimer(PassengerTimer, this, &ThisClass::UpdatePassengers, FMath::Max(UAirshipSettings::Get()->PassengerCheckInterval, 0.02f), true);
	}
	else if (!bWanted && Timers.IsTimerActive(PassengerTimer))
	{
		Timers.ClearTimer(PassengerTimer);
	}
}

AAirshipPawn* UAirshipSubsystem::FindShipFor(const ACharacter* Character, const TArray<AAirshipPawn*>& Ships)
{
	for (AAirshipPawn* Ship : Ships)
	{
		if (Ship && Ship->IsPassengerCandidate(Character))
		{
			return Ship;
		}
	}
	return nullptr;
}

void UAirshipSubsystem::UpdatePassengers()
{
	UWorld* World = GetWorld();

	if (!World)
	{
		return;
	}

	// Changing collision could run overlap events (it doesn't in practice: the query side stays as it was); a nested
	// call waits for the next check instead of changing the list under this one
	if (bUpdatingPassengers)
	{
		return;
	}

	TGuardValue<bool> UpdatingGuard(bUpdatingPassengers, true);
	const TArray<AAirshipPawn*> Ships = GetAirships();

	// Riders that left (or whose ship went away) get their collision back, after the bookkeeping; a rider that walked
	// onto another ship stays. One whose actor collision is off (the attached pilot once bPassengersQueryOnly goes off)
	// waits in the list without a ship until it is back on: switching its physics now would destroy the body for good.
	TArray<FPassenger> Leaving;

	for (int32 Index = Passengers.Num() - 1; Index >= 0; --Index)
	{
		FPassenger& Passenger = Passengers[Index];
		const ACharacter* Character = Passenger.Character.Get();

		if (!Character)
		{
			Passengers.RemoveAtSwap(Index);
			continue;
		}

		AAirshipPawn* Ship = Passenger.Airship.Get();

		if (Ship && Ships.Contains(Ship) && Ship->IsPassengerCandidate(Character))
		{
			continue;
		}

		// Another ship (or, for a waiting entry, a ship again)
		Passenger.Airship = FindShipFor(Character, Ships);

		if (Passenger.Airship.IsValid())
		{
			continue;
		}

		if (Character->GetActorEnableCollision() || Passenger.Primitives.Num() == 0)
		{
			Leaving.Add(MoveTemp(Passenger));
			Passengers.RemoveAtSwap(Index);
		}
	}

	// New riders
	if (Ships.Num() > 0)
	{
		for (TActorIterator<ACharacter> It(World); It; ++It)
		{
			ACharacter* Character = *It;

			if (!IsValid(Character) || FindPassengerEntry(Character))
			{
				continue;
			}

			if (AAirshipPawn* Ship = FindShipFor(Character, Ships))
			{
				FPassenger& Passenger = Passengers.AddDefaulted_GetRef();
				Passenger.Character = Character;
				Passenger.Airship = Ship;
			}
		}
	}

	// Every rider, old and new: whatever blocks the hull physically (again: an ability may have switched it back, a
	// component may have been added since) goes to query only. Waiting entries are left alone.
	for (FPassenger& Passenger : Passengers)
	{
		if (Passenger.Airship.IsValid())
		{
			ApplyPassengerCollision(Passenger);
		}
	}

	for (FPassenger& Passenger : Leaving)
	{
		RestorePassenger(Passenger);
	}

	// The last waiting entry gone and no ship left: the timer stops
	UpdatePassengerTimer();
}

void UAirshipSubsystem::ApplyPassengerCollision(FPassenger& Passenger)
{
	ACharacter* Character = Passenger.Character.Get();
	const AAirshipPawn* Airship = Passenger.Airship.Get();

	if (!IsValid(Character) || !Airship)
	{
		return;
	}

	// Not while the actor's collision is off (the attached pilot): the physics on/off switch would destroy the body and
	// make none (ShouldCreatePhysicsState asks the owner), and turning the collision back on doesn't make one, so the
	// character would sweep through the deck after Exit. It stays a passenger; the check right after its collision comes
	// back (exit, client restore) applies it then, with a valid QueryOnly body.
	if (!Character->GetActorEnableCollision())
	{
		return;
	}

	// A body lost while the collision was off (whoever switched it) comes back first
	RepairPhysicsState(Character);

	const UPrimitiveComponent* Hull = Airship->GetHull();
	const ECollisionChannel HullChannel = Hull ? Hull->GetCollisionObjectType() : ECC_PhysicsBody;

	TInlineComponentArray<UPrimitiveComponent*> Components(Character);

	for (UPrimitiveComponent* Component : Components)
	{
		// Simulated parts (ragdoll) keep their physics; only kinematic bodies that would block the hull are changed.
		// The component's own setting (not the actor's: an attached pilot has actor collision off).
		if (!IsValid(Component) || Component->IsSimulatingPhysics())
		{
			continue;
		}

		const ECollisionEnabled::Type Current = Component->BodyInstance.GetCollisionEnabled(false);

		if (!CollisionEnabledHasPhysics(Current) || Component->GetCollisionResponseToChannel(HullChannel) != ECR_Block)
		{
			continue;
		}

		// Physics -> query only (the CMC sweeps still walk on the hull, on the new QueryOnly body), physics only ->
		// none. The engine recreates the body when physics goes on or off (FBodyInstance::SetCollisionEnabled ->
		// RecreatePhysicsState): once per boarding / leaving, and only with the actor's collision on (checked above).
		const ECollisionEnabled::Type Applied = (Current == ECollisionEnabled::PhysicsOnly) ? ECollisionEnabled::NoCollision : ECollisionEnabled::QueryOnly;
		FPassengerPrimitive* Entry = Passenger.Primitives.FindByPredicate([Component](const FPassengerPrimitive& Primitive)
		{
			return Primitive.Component.Get() == Component;
		});

		if (Entry)
		{
			// Switched back by someone else since: on leaving it gets what they set
			Entry->Original = Current;
			Entry->Applied = Applied;
		}
		else
		{
			Passenger.Primitives.Add({ Component, Current, Applied });
		}

		Component->SetCollisionEnabled(Applied);
	}
}

void UAirshipSubsystem::RestorePassenger(FPassenger& Passenger)
{
	// UpdatePassengers restores only with the actor's collision on (or nothing recorded)
	for (const FPassengerPrimitive& Primitive : Passenger.Primitives)
	{
		UPrimitiveComponent* Component = Primitive.Component.Get();

		// Changed since (death: NoCollision, ragdoll...): leave it to whoever changed it
		if (IsValid(Component) && Component->BodyInstance.GetCollisionEnabled(false) == Primitive.Applied)
		{
			Component->SetCollisionEnabled(Primitive.Original);
		}
	}

	Passenger.Primitives.Reset();
}

const UAirshipSubsystem::FPassenger* UAirshipSubsystem::FindPassengerEntry(const ACharacter* Character) const
{
	return Character ? Passengers.FindByPredicate([Character](const FPassenger& Passenger)
	{
		return Passenger.Character.Get() == Character;
	}) : nullptr;
}

bool UAirshipSubsystem::IsPassenger(const ACharacter* Character) const
{
	// A waiting entry (no ship) doesn't ride anything
	const FPassenger* Entry = FindPassengerEntry(Character);
	return Entry && Entry->Airship.IsValid();
}

TArray<ACharacter*> UAirshipSubsystem::GetPassengers(const AAirshipPawn* Airship) const
{
	TArray<ACharacter*> Result;

	for (const FPassenger& Passenger : Passengers)
	{
		ACharacter* Character = Passenger.Character.Get();
		const AAirshipPawn* Ship = Passenger.Airship.Get();

		if (Character && Ship && (!Airship || Ship == Airship))
		{
			Result.Add(Character);
		}
	}

	return Result;
}

int32 UAirshipSubsystem::RepairPhysicsState(AActor* Actor)
{
	// Without the actor's collision nothing can be made (ShouldCreatePhysicsState is false for every primitive)
	const UWorld* World = IsValid(Actor) ? Actor->GetWorld() : nullptr;

	if (!World || World->bIsTearingDown || !World->GetPhysicsScene() || !Actor->GetActorEnableCollision())
	{
		return 0;
	}

	int32 NumRebuilt = 0;
	TInlineComponentArray<UPrimitiveComponent*> Components(Actor);

	for (UPrimitiveComponent* Component : Components)
	{
		// What EnsurePhysicsStateCreated (protected) does for the missing case only; never during async creation
		if (IsValid(Component) && Component->IsRegistered() && !Component->IsPhysicsStateCreated()
			&& !Component->IsAsyncCreatePhysicsStateRunning() && !Component->IsAsyncDestroyPhysicsStateRunning()
			&& Component->ShouldCreatePhysicsState())
		{
			Component->RecreatePhysicsState();
			++NumRebuilt;
			UE_LOG(LogAirship, Log, TEXT("%s: rebuilt the physics body of %s (lost while the actor's collision was off)"), *Actor->GetName(), *Component->GetName());
		}
	}

	return NumRebuilt;
}


AAirshipPawn* UAirshipSubsystem::SpawnAirshipInFront(const APawn* Pawn) const
{
	UWorld* World = GetWorld();

	if (!World || World->GetNetMode() == NM_Client || !Pawn)
	{
		return nullptr;
	}

	const UAirshipSettings* Settings = UAirshipSettings::Get();
	UClass* Class = Settings->AirshipClass.IsNull() ? nullptr : Settings->AirshipClass.LoadSynchronous();

	if (!Class)
	{
		UE_LOG(LogAirship, Warning, TEXT("AirshipClass (Project Settings > Game > Airship) not found: spawning a plain AAirshipPawn (hull only)"));
		Class = AAirshipPawn::StaticClass();
	}

	const FRotator Yaw(0.0, Pawn->GetActorRotation().Yaw, 0.0);
	const FVector Location = Pawn->GetActorLocation() + Yaw.Vector() * Settings->SpawnDistance + FVector(0.0, 0.0, Settings->SpawnHeight);

	FActorSpawnParameters Params;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn;
	return World->SpawnActor<AAirshipPawn>(Class, Location, Yaw, Params);
}


// =============================================================================
// Console
// =============================================================================

#if !UE_BUILD_SHIPPING
// Named, not anonymous: the unity build compiles this file together with others
namespace AirshipConsole
{
	bool CheckServer(const UWorld* World, const TCHAR* Command)
	{
		if (!World || World->GetNetMode() == NM_Client)
		{
			UE_LOG(LogAirship, Warning, TEXT("%s: run it on the server (listen server window or standalone)"), Command);
			return false;
		}
		return true;
	}

	/** PlayerIndex-th player controller of the world (0 = the host in PIE). */
	APlayerController* GetPlayerController(const UWorld* World, int32 PlayerIndex)
	{
		int32 Index = 0;

		for (FConstPlayerControllerIterator It = World->GetPlayerControllerIterator(); It; ++It, ++Index)
		{
			if (Index == PlayerIndex)
			{
				return It->Get();
			}
		}
		return nullptr;
	}

	UAirshipPilotComponent* GetPilotComponent(UWorld* World, int32 PlayerIndex)
	{
		APlayerController* PC = GetPlayerController(World, PlayerIndex);

		if (!PC)
		{
			return nullptr;
		}

		if (UAirshipSubsystem* Subsystem = UAirshipSubsystem::Get(World))
		{
			Subsystem->EnsurePilotComponent(PC);
		}
		return PC->FindComponentByClass<UAirshipPilotComponent>();
	}

	/** "Pawn.Name" -> the ship, "Anim.Name" -> its anim instance, "Flight.Name" or "Name" -> the flight component. */
	UObject* ResolveTarget(AAirshipPawn* Ship, const FString& FullName, FString& OutProperty)
	{
		OutProperty = FullName;
		FString Prefix;
		FString Rest;

		if (FullName.Split(TEXT("."), &Prefix, &Rest))
		{
			OutProperty = Rest;

			if (Prefix.Equals(TEXT("Pawn"), ESearchCase::IgnoreCase))
			{
				return Ship;
			}
			if (Prefix.Equals(TEXT("Anim"), ESearchCase::IgnoreCase))
			{
				return Ship->GetMesh() ? Ship->GetMesh()->GetAnimInstance() : nullptr;
			}
		}
		return Ship->GetFlight();
	}

	FString JoinArgs(const TArray<FString>& Args, int32 First)
	{
		FString Result;

		for (int32 Index = First; Index < Args.Num(); ++Index)
		{
			Result += (Index > First ? TEXT(" ") : TEXT("")) + Args[Index];
		}
		return Result;
	}

	FString ExportValue(const FProperty* Property, UObject* Target)
	{
		FString Text;
		Property->ExportTextItem_Direct(Text, Property->ContainerPtrToValuePtr<void>(Target), nullptr, Target, PPF_None);
		return Text;
	}

	FAutoConsoleCommandWithWorldAndArgs GSetCommand(
		TEXT("Aura.Airship.Set"),
		TEXT("Aura.Airship.Set <Property> <Value> - sets a property on every airship of this world by name: the flight component (UAirshipFlightComponent), or Pawn.<Name> / Anim.<Name>. Any type that imports from text (float, int, bool, FVector as (X=..,Y=..,Z=..)). Forces run on the server: use the server window."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			UAirshipSubsystem* Subsystem = UAirshipSubsystem::Get(World);

			if (!Subsystem || Args.Num() < 2)
			{
				UE_LOG(LogAirship, Warning, TEXT("Usage: Aura.Airship.Set <Property> <Value>"));
				return;
			}

			const FString Value = JoinArgs(Args, 1);
			int32 NumSet = 0;

			for (AAirshipPawn* Ship : Subsystem->GetAirships())
			{
				FString PropertyName;
				UObject* Target = ResolveTarget(Ship, Args[0], PropertyName);
				FProperty* Property = Target ? FindFProperty<FProperty>(Target->GetClass(), *PropertyName) : nullptr;

				if (!Property)
				{
					UE_LOG(LogAirship, Warning, TEXT("Aura.Airship.Set: %s has no property %s"), Target ? *Target->GetClass()->GetName() : TEXT("(none)"), *PropertyName);
					continue;
				}

				if (!Property->ImportText_Direct(*Value, Property->ContainerPtrToValuePtr<void>(Target), Target, PPF_None))
				{
					UE_LOG(LogAirship, Warning, TEXT("Aura.Airship.Set: '%s' is not a valid %s"), *Value, *Property->GetCPPType());
					continue;
				}

				Ship->OnTuningChanged();
				++NumSet;
				UE_LOG(LogAirship, Log, TEXT("Aura.Airship.Set: %s.%s = %s"), *Ship->GetName(), *PropertyName, *ExportValue(Property, Target));
			}

			UE_LOG(LogAirship, Log, TEXT("Aura.Airship.Set: %d ship(s)"), NumSet);
		})
	);

	FAutoConsoleCommandWithWorldAndArgs GGetCommand(
		TEXT("Aura.Airship.Get"),
		TEXT("Aura.Airship.Get <Property> - prints a property of every airship of this world (same names as Aura.Airship.Set)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			UAirshipSubsystem* Subsystem = UAirshipSubsystem::Get(World);

			if (!Subsystem || Args.Num() < 1)
			{
				UE_LOG(LogAirship, Warning, TEXT("Usage: Aura.Airship.Get <Property>"));
				return;
			}

			for (AAirshipPawn* Ship : Subsystem->GetAirships())
			{
				FString PropertyName;
				UObject* Target = ResolveTarget(Ship, Args[0], PropertyName);
				const FProperty* Property = Target ? FindFProperty<FProperty>(Target->GetClass(), *PropertyName) : nullptr;

				if (Property)
				{
					UE_LOG(LogAirship, Log, TEXT("Aura.Airship.Get: %s.%s = %s"), *Ship->GetName(), *PropertyName, *ExportValue(Property, Target));
				}
				else
				{
					UE_LOG(LogAirship, Warning, TEXT("Aura.Airship.Get: %s has no property %s"), Target ? *Target->GetClass()->GetName() : TEXT("(none)"), *PropertyName);
				}
			}
		})
	);

	FAutoConsoleCommandWithWorld GSpawnCommand(
		TEXT("Aura.Airship.Spawn"),
		TEXT("Aura.Airship.Spawn - server: spawns AirshipClass (Project Settings > Game > Airship) in front of and above player 0's pawn."),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* World)
		{
			if (!CheckServer(World, TEXT("Aura.Airship.Spawn")))
			{
				return;
			}

			const APlayerController* PC = GetPlayerController(World, 0);
			const UAirshipSubsystem* Subsystem = UAirshipSubsystem::Get(World);
			AAirshipPawn* Ship = (PC && Subsystem) ? Subsystem->SpawnAirshipInFront(PC->GetPawn()) : nullptr;

			UE_LOG(LogAirship, Log, TEXT("Aura.Airship.Spawn: %s"), Ship ? *Ship->GetName() : TEXT("failed (no player pawn?)"));
		})
	);

	FAutoConsoleCommandWithWorldAndArgs GBoardCommand(
		TEXT("Aura.Airship.Board"),
		TEXT("Aura.Airship.Board [PlayerIndex] - server: the player (default 0) takes the helm of the nearest free airship, any distance."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (!CheckServer(World, TEXT("Aura.Airship.Board")))
			{
				return;
			}

			UAirshipPilotComponent* Pilot = GetPilotComponent(World, Args.Num() > 0 ? FCString::Atoi(*Args[0]) : 0);
			const bool bBoarded = Pilot && Pilot->TryBoard(nullptr, true);
			UE_LOG(LogAirship, Log, TEXT("Aura.Airship.Board: %s"), bBoarded ? TEXT("boarded") : TEXT("failed (no player character, no free ship, or the player is dead)"));
		})
	);

	FAutoConsoleCommandWithWorldAndArgs GExitCommand(
		TEXT("Aura.Airship.Exit"),
		TEXT("Aura.Airship.Exit [PlayerIndex] - server: the player (default 0) leaves the helm."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (!CheckServer(World, TEXT("Aura.Airship.Exit")))
			{
				return;
			}

			UAirshipPilotComponent* Pilot = GetPilotComponent(World, Args.Num() > 0 ? FCString::Atoi(*Args[0]) : 0);
			const bool bExited = Pilot && Pilot->TryExit();
			UE_LOG(LogAirship, Log, TEXT("Aura.Airship.Exit: %s"), bExited ? TEXT("on foot") : TEXT("not flying"));
		})
	);

	FAutoConsoleCommandWithWorldAndArgs GDamageCommand(
		TEXT("Aura.Airship.Damage"),
		TEXT("Aura.Airship.Damage <Amount> - server: every living airship takes Amount damage through its damage effect."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			UAirshipSubsystem* Subsystem = UAirshipSubsystem::Get(World);

			if (!CheckServer(World, TEXT("Aura.Airship.Damage")) || !Subsystem)
			{
				return;
			}

			const float Amount = Args.Num() > 0 ? FCString::Atof(*Args[0]) : 100.f;

			for (AAirshipPawn* Ship : Subsystem->GetAirships())
			{
				if (!Ship->IsAirshipDead())
				{
					Ship->ApplyShipDamage(Amount);
					UE_LOG(LogAirship, Log, TEXT("Aura.Airship.Damage: %s health %.0f"), *Ship->GetName(), Ship->GetFlightTelemetry().Health);
				}
			}
		})
	);

	FAutoConsoleCommandWithWorld GKillCommand(
		TEXT("Aura.Airship.Kill"),
		TEXT("Aura.Airship.Kill - server: every living airship dies (health 0, normal death: pilot ejected, wreck, LifeSpan)."),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* World)
		{
			UAirshipSubsystem* Subsystem = UAirshipSubsystem::Get(World);

			if (!CheckServer(World, TEXT("Aura.Airship.Kill")) || !Subsystem)
			{
				return;
			}

			int32 NumKilled = 0;

			for (AAirshipPawn* Ship : Subsystem->GetAirships())
			{
				if (Ship->IsAirshipDead())
				{
					continue;
				}

				if (UAbilitySystemComponent* ASC = Ship->GetAbilitySystemComponent())
				{
					ASC->SetNumericAttributeBase(UMyAttributeSet::GetHealthAttribute(), 0.f);
				}
				Ship->Die();
				++NumKilled;
			}

			UE_LOG(LogAirship, Log, TEXT("Aura.Airship.Kill: %d killed"), NumKilled);
		})
	);

	FAutoConsoleCommandWithWorldAndArgs GInputCommand(
		TEXT("Aura.Airship.Input"),
		TEXT("Aura.Airship.Input <Throttle> <Steer> [Lift] [Strafe] [Boost 0/1] [Brake 0/1] - flies every airship of this world with these controls (-1..1) until Aura.Airship.InputClear. Use the server window."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			UAirshipSubsystem* Subsystem = UAirshipSubsystem::Get(World);

			if (!Subsystem)
			{
				return;
			}

			auto Arg = [&Args](int32 Index) { return Args.IsValidIndex(Index) ? FCString::Atof(*Args[Index]) : 0.f; };

			for (AAirshipPawn* Ship : Subsystem->GetAirships())
			{
				Ship->DebugSetInput(Arg(0), Arg(1), Arg(2), Arg(3), Arg(4) > 0.5f, Arg(5) > 0.5f);
			}
		})
	);

	FAutoConsoleCommandWithWorld GInputClearCommand(
		TEXT("Aura.Airship.InputClear"),
		TEXT("Aura.Airship.InputClear - ends Aura.Airship.Input / DebugSetInput on every airship of this world."),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* World)
		{
			if (UAirshipSubsystem* Subsystem = UAirshipSubsystem::Get(World))
			{
				for (AAirshipPawn* Ship : Subsystem->GetAirships())
				{
					Ship->DebugClearInput();
				}
			}
		})
	);

	FAutoConsoleCommandWithWorld GPassengersCommand(
		TEXT("Aura.Airship.Passengers"),
		TEXT("Aura.Airship.Passengers - logs the characters riding an airship on this machine (their capsule collision is query only)."),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* World)
		{
			if (UAirshipSubsystem* Subsystem = UAirshipSubsystem::Get(World))
			{
				Subsystem->UpdatePassengers();

				for (AAirshipPawn* Ship : Subsystem->GetAirships())
				{
					for (const ACharacter* Character : Subsystem->GetPassengers(Ship))
					{
						// The flag (1 = QueryOnly) and whether the root has a physics body at all (the movement sweeps need one)
						const UPrimitiveComponent* Capsule = Cast<UPrimitiveComponent>(Character->GetRootComponent());
						UE_LOG(LogAirship, Log, TEXT("Aura.Airship.Passengers: %s on %s (root collision %d, body %d, actor collision %d, attached %d)"),
							*Character->GetName(), *Ship->GetName(), Capsule ? static_cast<int32>(Capsule->BodyInstance.GetCollisionEnabled(false)) : -1,
							(Capsule && Capsule->IsPhysicsStateCreated() && Capsule->BodyInstance.IsValidBodyInstance()) ? 1 : 0,
							Character->GetActorEnableCollision() ? 1 : 0, Character->IsAttachedTo(Ship) ? 1 : 0);
					}
				}
				UE_LOG(LogAirship, Log, TEXT("Aura.Airship.Passengers: %d"), Subsystem->GetPassengers(nullptr).Num());
			}
		})
	);

	FAutoConsoleCommandWithWorld GTelemetryCommand(
		TEXT("Aura.Airship.Telemetry"),
		TEXT("Aura.Airship.Telemetry - logs speed, altitude, attitude, fuel, health and the control scheme's state of every airship of this world, then its hull inertia (Chaos principal moments, mass frame, hull-space COM)."),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* World)
		{
			if (UAirshipSubsystem* Subsystem = UAirshipSubsystem::Get(World))
			{
				for (AAirshipPawn* Ship : Subsystem->GetAirships())
				{
					const FAirshipFlightTelemetry T = Ship->GetFlightTelemetry();
					UE_LOG(LogAirship, Log, TEXT("%s: speed %.1f m/s (fwd %.1f, side %.1f, up %.1f), alt %.1f m (hold %.1f, ground %.1f), yaw rate %.1f deg/s, roll %.1f pitch %.1f yaw %.1f, fuel %.0f, health %.0f/%.0f, pilot %d, dead %d"),
						*Ship->GetName(), T.SpeedMS, T.ForwardSpeedMS, T.LateralSpeedMS, T.VerticalSpeedMS, T.AltitudeM, T.HoldAltitudeM, T.GroundClearanceM,
						T.YawRateDegS, T.RollDeg, T.PitchDeg, T.YawDeg, T.BoostFuel, T.Health, T.MaxHealth, T.bHasPilot ? 1 : 0, T.bIsDead ? 1 : 0);
					UE_LOG(LogAirship, Log, TEXT("%s: scheme %d order %.2f drift %.2f (dir %d tier %d turbo %.2f chain %d) heading %d %.1f freelook %d gundeck %d lock %d"),
						*Ship->GetName(), static_cast<int32>(T.Scheme), T.ThrottleOrder, T.DriftCharge, T.DriftDir, T.DriftTier, T.TurboAlpha, T.TurboChain,
						T.bHeadingTargetActive ? 1 : 0, T.HeadingTargetDeg, T.bFreeLook ? 1 : 0, T.bGunDeck ? 1 : 0, T.bGunLock ? 1 : 0);

					// BASELINE.md 4a / 4f row 0: what GetInertiaTensor returns (Chaos's principal moments, largest / smallest /
					// middle), the mass frame's rotation and position in the hull, and the hull-space COM. Read it before
					// judging any pitch or roll numbers (bHullAxisInertia).
					UPrimitiveComponent* Hull = Ship->GetHull();
					const FBodyInstance* BodyInstance = Hull ? Hull->GetBodyInstance() : nullptr;

					if (Hull && BodyInstance && Hull->IsSimulatingPhysics())
					{
						const FVector Inertia = Hull->GetInertiaTensor();
						const FTransform MassSpace = BodyInstance->GetMassSpaceLocal();
						const FVector COMHull = Hull->GetComponentTransform().InverseTransformPosition(Hull->GetCenterOfMass());
						UE_LOG(LogAirship, Log, TEXT("%s: inertia (principal, kg cm^2) %s, mass frame rotation %s translation %s, hull-space COM %s"),
							*Ship->GetName(), *Inertia.ToString(), *MassSpace.GetRotation().Rotator().ToString(), *MassSpace.GetTranslation().ToString(), *COMHull.ToString());
					}
				}
			}
		})
	);

	FAutoConsoleCommandWithWorldAndArgs GSchemeCommand(
		TEXT("Aura.Airship.Scheme"),
		TEXT("Aura.Airship.Scheme <0-3> - server: every airship of this world switches control scheme (0 Classic (v1), 1 Galleon, 2 Sky Racer, 3 Point & Fly = the default; it replicates). No argument (any machine): prints each ship's scheme. 'check' (any machine): lists every scheme-owned property that differs from the class defaults (0 after Aura.Airship.Scheme 0)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			UAirshipSubsystem* Subsystem = UAirshipSubsystem::Get(World);

			if (!Subsystem)
			{
				return;
			}

			// No argument: each ship's replicated scheme and the flight model's copy
			if (Args.Num() == 0)
			{
				for (const AAirshipPawn* Ship : Subsystem->GetAirships())
				{
					const EAirshipControlScheme Scheme = Ship->GetControlScheme();
					const EAirshipControlScheme Active = Ship->GetFlight() ? Ship->GetFlight()->GetActiveScheme() : Scheme;
					UE_LOG(LogAirship, Log, TEXT("Aura.Airship.Scheme: %s: %s (%d), active %s (%d)"), *Ship->GetName(),
						*UEnum::GetDisplayValueAsText(Scheme).ToString(), static_cast<int32>(Scheme), *UEnum::GetDisplayValueAsText(Active).ToString(), static_cast<int32>(Active));
				}
				return;
			}

			// The Classic exactness test (and a quick look at a preset): what differs from the archetype
			if (Args[0].Equals(TEXT("check"), ESearchCase::IgnoreCase))
			{
				for (const AAirshipPawn* Ship : Subsystem->GetAirships())
				{
					TArray<FString> Differences;
					const int32 NumDifferences = Ship->GetSchemePropertyDifferences(Differences);

					for (const FString& Line : Differences)
					{
						UE_LOG(LogAirship, Log, TEXT("Aura.Airship.Scheme check: %s: %s"), *Ship->GetName(), *Line);
					}
					UE_LOG(LogAirship, Log, TEXT("Aura.Airship.Scheme check: %s: %s, %d difference(s) from the class defaults"), *Ship->GetName(),
						*UEnum::GetDisplayValueAsText(Ship->GetControlScheme()).ToString(), NumDifferences);
				}
				return;
			}

			const int32 Value = Args[0].IsNumeric() ? FCString::Atoi(*Args[0]) : -1;

			if (Value < 0 || Value > 3)
			{
				UE_LOG(LogAirship, Warning, TEXT("Usage: Aura.Airship.Scheme [0-3 | check] (0 Classic (v1), 1 Galleon, 2 Sky Racer, 3 Point & Fly)"));
				return;
			}

			if (!CheckServer(World, TEXT("Aura.Airship.Scheme")))
			{
				return;
			}

			const EAirshipControlScheme NewScheme = static_cast<EAirshipControlScheme>(Value);

			for (AAirshipPawn* Ship : Subsystem->GetAirships())
			{
				Ship->SetControlScheme(NewScheme);
				UE_LOG(LogAirship, Log, TEXT("Aura.Airship.Scheme: %s = %s (%d)"), *Ship->GetName(), *UEnum::GetDisplayValueAsText(NewScheme).ToString(), Value);
			}
		})
	);
}
#endif
