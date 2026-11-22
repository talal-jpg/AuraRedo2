// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "AirshipPilotComponent.generated.h"

class AAirshipPawn;
class APlayerController;
class UEnhancedInputComponent;
class UEnhancedInputLocalPlayerSubsystem;
class UInputAction;
class UInputMappingContext;

/**
 * Lets a player board an airship. UAirshipSubsystem adds one to every PlayerController on the server (replicated, so
 * the owning client has it too), no edit to the project's controller.
 *
 * Owning client: pushes its own input component and adds IMC_AirshipBoard (IA_AirshipBoard on F); a press sends
 * ServerRequestBoard. Server: the nearest free living ship in range of the player's pawn (UAirshipSettings
 * BoardDistance / BoardHullDistance) takes the character at its helm (AAirshipPawn::BoardPilot). Exit goes through
 * ServerRequestExit (the ship's own Exit key uses its RPC, same result).
 */
UCLASS(ClassGroup = (Airship), meta = (BlueprintSpawnableComponent))
class AURA_API UAirshipPilotComponent : public UActorComponent
{
	GENERATED_BODY()

public:

	UAirshipPilotComponent();

	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

	/** Local player: board the nearest ship in range (sends the request). */
	UFUNCTION(BlueprintCallable, Category = "Airship")
	void RequestBoard();

	/** Local player: leave the helm (sends the request). */
	UFUNCTION(BlueprintCallable, Category = "Airship")
	void RequestExit();

	/** Any machine: the nearest free living ship the player's pawn could board now (for a "Press F" prompt). Null if none. */
	UFUNCTION(BlueprintPure, Category = "Airship")
	AAirshipPawn* FindBoardableAirship() const;

	/** Server: boards Ship (nearest in range when null). bIgnoreRange for console commands. */
	bool TryBoard(AAirshipPawn* Ship, bool bIgnoreRange);

	/** Server: leaves the ship the player flies, if any. */
	bool TryExit();

	APlayerController* GetPlayerController() const;

	/** Optional: overrides Project Settings > Game > Airship. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Input")
	TObjectPtr<UInputMappingContext> BoardMappingContext;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Input")
	TObjectPtr<UInputAction> BoardAction;

protected:

	virtual void BeginPlay() override;

	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

	UFUNCTION(Server, Reliable)
	void ServerRequestBoard();

	UFUNCTION(Server, Reliable)
	void ServerRequestExit();

private:

	/** Owning client: input component + mapping context, once the local player exists. True when done (or not needed). */
	bool TrySetupLocalInput();

	void TeardownLocalInput();

	void OnBoardPressed();

	/** Server: request debounce (key repeat, double press). */
	bool ConsumeRequestCooldown();

	UPROPERTY(Transient)
	TObjectPtr<UEnhancedInputComponent> BoardInputComponent;

	TWeakObjectPtr<UEnhancedInputLocalPlayerSubsystem> MappingSubsystem;
	TWeakObjectPtr<const UInputMappingContext> AddedMappingContext;

	bool bLocalInputDone = false;
	float SetupRetryTime = 0.f;
	double LastRequestTime = -1000.0;
};
