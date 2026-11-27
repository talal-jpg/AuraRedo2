// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Engine/EngineTypes.h"
#include "Engine/TimerHandle.h"
#include "Subsystems/WorldSubsystem.h"
#include "AirshipSubsystem.generated.h"

class AActor;
class AAirshipPawn;
class ACharacter;
class AGameModeBase;
class APawn;
class APlayerController;
class UPrimitiveComponent;

/**
 * Airship bookkeeping per game world.
 *
 * Server: gives every PlayerController a UAirshipPilotComponent (on login and for the ones already there at
 * BeginPlay), so players can board without changes to the project's controller.
 * Every machine: the registry of living ship actors (they register in BeginPlay, leave in EndPlay), and the deck
 * passengers: a character a ship claims (AAirshipPawn::IsPassengerCandidate: standing on it, attached to it, airborne
 * next to it, or standing elsewhere inside the hull's own box) gets its kinematic physics collision switched off (QueryAndPhysics -> QueryOnly on the capsule and any
 * other non-simulating primitive that blocks the hull), checked every PassengerCheckInterval, on board / exit, and each
 * frame before physics for a character new to a ship's zone (CheckNewPassengers). CMC
 * sweeps still walk on the hull (on the QueryOnly body); the capsule no longer pushes the simulated hull every physics
 * step (the ship sank under a standing character). Restored when the character leaves, the ship goes away (EndPlay) or
 * the world ends. Never while the character's actor collision is off (the attached pilot): a physics on/off switch then
 * destroys the body and makes none, so the change waits until the collision is back (RepairPhysicsState).
 * Console (non-shipping): Aura.Airship.Spawn / Board / Exit / Damage / Kill / Set / Get / Input / InputClear /
 * Telemetry / Scheme / Mount / Dismount / TurretFire / TurretDamage / StationFire, and the CVars Aura.Airship.Debug and
 * Aura.Airship.RepMode.
 */
UCLASS()
class AURA_API UAirshipSubsystem : public UWorldSubsystem
{
	GENERATED_BODY()

public:

	static UAirshipSubsystem* Get(const UObject* WorldContextObject);

	virtual void Initialize(FSubsystemCollectionBase& Collection) override;

	virtual void Deinitialize() override;

	virtual void OnWorldBeginPlay(UWorld& InWorld) override;

	void RegisterAirship(AAirshipPawn* Airship);

	void UnregisterAirship(AAirshipPawn* Airship);

	/** Ships of this world (valid ones only). */
	TArray<AAirshipPawn*> GetAirships() const;

	/** Nearest ship to Location (by pilot seat); bOnlyBoardable: alive and without a pilot. */
	AAirshipPawn* FindNearestAirship(const FVector& Location, bool bOnlyBoardable) const;

	/** Every machine: the ship and gunner station (EAirshipStation) Character mans, from the replicated StationGunners. False if none. */
	bool FindGunnerStation(const ACharacter* Character, AAirshipPawn*& OutShip, int32& OutStation) const;

	/** Server: adds the pilot component to PC if it has none (and the settings allow it). */
	void EnsurePilotComponent(APlayerController* PC) const;

	/** Server: spawns UAirshipSettings::AirshipClass in front of Pawn. */
	AAirshipPawn* SpawnAirshipInFront(const APawn* Pawn) const;

	/** Every machine: re-checks which characters ride a ship now (also runs on a timer while ships exist). */
	void UpdatePassengers();

	/**
	 * Every machine, from each ship's tick (before the physics step): runs UpdatePassengers now if a character that is
	 * not in the list yet is one of Airship's passenger candidates. The timed check alone is up to PassengerCheckInterval
	 * late, and timers run after the frame's physics: a character whose kinematic bodies are inside the hull's convex
	 * for even one step shoves the ship hard.
	 */
	void CheckNewPassengers(const AAirshipPawn* Airship);

	/** True while Character rides a ship (this machine's passenger state). */
	bool IsPassenger(const ACharacter* Character) const;

	/** Characters riding Airship (null: any ship) on this machine. */
	TArray<ACharacter*> GetPassengers(const AAirshipPawn* Airship) const;

	/**
	 * Rebuilds the physics body of Actor's registered primitives that should have one and don't (nothing while Actor's
	 * collision is off). Switching a primitive's physics on or off while its actor's collision is off destroys the body
	 * and makes none (ShouldCreatePhysicsState asks the owner), and turning the actor's collision back on only updates
	 * the filters: such a capsule's movement sweeps find nothing, the character falls through every floor. Call it after
	 * SetActorEnableCollision(true). Returns how many bodies it rebuilt (logged).
	 */
	static int32 RepairPhysicsState(AActor* Actor);

protected:

	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;

private:

	void HandlePostLogin(AGameModeBase* GameMode, APlayerController* NewPlayer);

	/** One primitive of a passenger whose collision was changed: restored only if it still has the value we set. */
	struct FPassengerPrimitive
	{
		TWeakObjectPtr<UPrimitiveComponent> Component;
		ECollisionEnabled::Type Original = ECollisionEnabled::QueryAndPhysics;
		ECollisionEnabled::Type Applied = ECollisionEnabled::QueryOnly;
	};

	struct FPassenger
	{
		TWeakObjectPtr<ACharacter> Character;

		/** The ship it rides; null: it left while its actor collision was off, its primitives wait to be restored. */
		TWeakObjectPtr<AAirshipPawn> Airship;

		TArray<FPassengerPrimitive> Primitives;
	};

	/** The first registered ship that claims Character, or null. */
	static AAirshipPawn* FindShipFor(const ACharacter* Character, const TArray<AAirshipPawn*>& Ships);

	/** Character's entry (a rider, or one waiting to be restored), or null. */
	const FPassenger* FindPassengerEntry(const ACharacter* Character) const;

	/**
	 * Physics collision of the rider's non-simulating primitives that block the hull -> query only (physics only ->
	 * none), remembering what each had. Runs on every check, so a primitive switched back meanwhile is caught again.
	 * Does nothing while the rider's actor collision is off (the attached pilot); it stays a passenger.
	 */
	static void ApplyPassengerCollision(FPassenger& Passenger);

	/**
	 * Gives back what ApplyPassengerCollision changed (only where nobody changed it since). The caller makes sure the
	 * actor's collision is on (else the body would go for good).
	 */
	static void RestorePassenger(FPassenger& Passenger);

	/** Runs the passenger timer while ships exist or entries wait to be restored, stops it otherwise. */
	void UpdatePassengerTimer();

	FDelegateHandle PostLoginHandle;

	TArray<TWeakObjectPtr<AAirshipPawn>> Airships;

	TArray<FPassenger> Passengers;

	FTimerHandle PassengerTimer;

	/** UpdatePassengers is running (a nested call returns). */
	bool bUpdatingPassengers = false;
};
