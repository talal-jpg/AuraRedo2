// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Engine/DeveloperSettings.h"
#include "AirshipSettings.generated.h"

class AAirshipPawn;
class UInputAction;
class UInputMappingContext;

/**
 * Drivable airship settings: Project Settings > Game > Airship, saved to DefaultGame.ini
 * ([/Script/Aura.AirshipSettings]). The defaults below point at the asset names the editor step creates
 * (Docs/Airship/CPP_NOTES.md), so nothing has to be saved here unless an asset moves.
 *
 * Input: AAirshipPawn and UAirshipPilotComponent use their own UPROPERTYs when set on the Blueprint, else these.
 */
UCLASS(Config = Game, DefaultConfig, meta = (DisplayName = "Airship"))
class AURA_API UAirshipSettings : public UDeveloperSettings
{
	GENERATED_BODY()

public:

	UAirshipSettings()
	{
		const TCHAR* InputFolder = TEXT("/Game/Assets/MyShip/Drivable/Input/");
		auto Action = [InputFolder](const TCHAR* Name)
		{
			return TSoftObjectPtr<UInputAction>(FSoftObjectPath(FString::Printf(TEXT("%s%s.%s"), InputFolder, Name, Name)));
		};
		auto Context = [InputFolder](const TCHAR* Name)
		{
			return TSoftObjectPtr<UInputMappingContext>(FSoftObjectPath(FString::Printf(TEXT("%s%s.%s"), InputFolder, Name, Name)));
		};

		AirshipClass = TSoftClassPtr<AAirshipPawn>(FSoftObjectPath(TEXT("/Game/Assets/MyShip/Drivable/BP_AirshipPawn.BP_AirshipPawn_C")));

		BoardMappingContext = Context(TEXT("IMC_AirshipBoard"));
		BoardAction = Action(TEXT("IA_AirshipBoard"));

		AirshipMappingContext = Context(TEXT("IMC_Airship"));
		ThrottleAction = Action(TEXT("IA_AirshipThrottle"));
		SteerAction = Action(TEXT("IA_AirshipSteer"));
		LiftAction = Action(TEXT("IA_AirshipLift"));
		StrafeAction = Action(TEXT("IA_AirshipStrafe"));
		BoostAction = Action(TEXT("IA_AirshipBoost"));
		BrakeAction = Action(TEXT("IA_AirshipBrake"));
		FireAction = Action(TEXT("IA_AirshipFire"));
		LookAction = Action(TEXT("IA_AirshipLook"));
		ZoomAction = Action(TEXT("IA_AirshipZoom"));
		ExitAction = Action(TEXT("IA_AirshipExit"));
		AimAction = Action(TEXT("IA_AirshipAim"));
	}

	static const UAirshipSettings* Get() { return GetDefault<UAirshipSettings>(); }


	// -------------------------------------------------------------------------
	// Spawning (Aura.Airship.Spawn)
	// -------------------------------------------------------------------------

	/** Spawned by Aura.Airship.Spawn. Use BP_AirshipPawn (mesh, AnimBP, FX set). Unset or missing: plain AAirshipPawn (hull only). */
	UPROPERTY(Config, EditAnywhere, Category = "Spawning")
	TSoftClassPtr<AAirshipPawn> AirshipClass;

	/** Aura.Airship.Spawn: distance (cm) in front of player 0's pawn. */
	UPROPERTY(Config, EditAnywhere, Category = "Spawning", meta = (ClampMin = "0.0"))
	float SpawnDistance = 6000.f;

	/** Aura.Airship.Spawn: height (cm) above player 0's pawn. */
	UPROPERTY(Config, EditAnywhere, Category = "Spawning")
	float SpawnHeight = 1500.f;


	// -------------------------------------------------------------------------
	// Boarding
	// -------------------------------------------------------------------------

	/** Off: no UAirshipPilotComponent is added to the player controllers (nobody can board with the key). */
	UPROPERTY(Config, EditAnywhere, Category = "Boarding")
	bool bAddPilotComponent = true;

	/** A player can board when their pawn is within this distance (cm) of the ship's pilot seat... */
	UPROPERTY(Config, EditAnywhere, Category = "Boarding", meta = (ClampMin = "0.0"))
	float BoardDistance = 1200.f;

	/** ...or within this distance (cm) of the hull's collision (standing on the deck, next to the hull). */
	UPROPERTY(Config, EditAnywhere, Category = "Boarding", meta = (ClampMin = "0.0"))
	float BoardHullDistance = 400.f;

	/** Seconds between two board/exit requests of one player (key repeat, double presses). */
	UPROPERTY(Config, EditAnywhere, Category = "Boarding", meta = (ClampMin = "0.0"))
	float BoardCooldown = 0.5f;

	/**
	 * Seconds between two passenger checks (every machine, UAirshipSubsystem): characters standing on a ship, attached
	 * to it or airborne next to it get QueryOnly collision, so their kinematic capsule doesn't push the simulated hull.
	 */
	UPROPERTY(Config, EditAnywhere, Category = "Boarding", meta = (ClampMin = "0.02"))
	float PassengerCheckInterval = 0.1f;


	// -------------------------------------------------------------------------
	// Input: on foot (UAirshipPilotComponent, owning client)
	// -------------------------------------------------------------------------

	/** Holds IA_AirshipBoard (F, gamepad Y). Added on the owning client while the player is on foot or flying. */
	UPROPERTY(Config, EditAnywhere, Category = "Input|On Foot")
	TSoftObjectPtr<UInputMappingContext> BoardMappingContext;

	/** Priority of BoardMappingContext. Below AirshipMappingPriority, so IA_AirshipExit gets F while flying. */
	UPROPERTY(Config, EditAnywhere, Category = "Input|On Foot")
	int32 BoardMappingPriority = 0;

	/** Bool, Started: board the nearest free ship in range. */
	UPROPERTY(Config, EditAnywhere, Category = "Input|On Foot")
	TSoftObjectPtr<UInputAction> BoardAction;


	// -------------------------------------------------------------------------
	// Input: flying (AAirshipPawn, added while it is locally possessed)
	// -------------------------------------------------------------------------

	/** Holds the IA_Airship* actions below. Must map the same keys as IMC_PlayerMappings (WASD, Space, Shift, LMB, mouse) so they are consumed. */
	UPROPERTY(Config, EditAnywhere, Category = "Input|Flying")
	TSoftObjectPtr<UInputMappingContext> AirshipMappingContext;

	/** Priority of AirshipMappingContext: above IMC_PlayerMappings (0) and BoardMappingContext. */
	UPROPERTY(Config, EditAnywhere, Category = "Input|Flying")
	int32 AirshipMappingPriority = 1;

	/** Axis1D: W +1, S -1. */
	UPROPERTY(Config, EditAnywhere, Category = "Input|Flying")
	TSoftObjectPtr<UInputAction> ThrottleAction;

	/** Axis1D: D +1, A -1. */
	UPROPERTY(Config, EditAnywhere, Category = "Input|Flying")
	TSoftObjectPtr<UInputAction> SteerAction;

	/** Axis1D: Space +1, Left Ctrl -1. Released = altitude hold. */
	UPROPERTY(Config, EditAnywhere, Category = "Input|Flying")
	TSoftObjectPtr<UInputAction> LiftAction;

	/** Axis1D: E +1 (right), Q -1. */
	UPROPERTY(Config, EditAnywhere, Category = "Input|Flying")
	TSoftObjectPtr<UInputAction> StrafeAction;

	/** Bool (hold): Left Shift. */
	UPROPERTY(Config, EditAnywhere, Category = "Input|Flying")
	TSoftObjectPtr<UInputAction> BoostAction;

	/** Bool (hold): X. Air brake + hover hold; with steer = drift. */
	UPROPERTY(Config, EditAnywhere, Category = "Input|Flying")
	TSoftObjectPtr<UInputAction> BrakeAction;

	/** Bool, Started: LMB. Fires the two cannons on the side the camera looks at. */
	UPROPERTY(Config, EditAnywhere, Category = "Input|Flying")
	TSoftObjectPtr<UInputAction> FireAction;

	/** Axis2D: mouse XY / right stick, camera orbit (same modifiers as IA_Rotate). */
	UPROPERTY(Config, EditAnywhere, Category = "Input|Flying")
	TSoftObjectPtr<UInputAction> LookAction;

	/** Axis1D: mouse wheel (+ = zoom in). */
	UPROPERTY(Config, EditAnywhere, Category = "Input|Flying")
	TSoftObjectPtr<UInputAction> ZoomAction;

	/** Bool, Started: F. Leave the helm. */
	UPROPERTY(Config, EditAnywhere, Category = "Input|Flying")
	TSoftObjectPtr<UInputAction> ExitAction;

	/** Bool (hold): RMB. Aim mode (tighter camera). Mapping RMB also keeps the on-foot beam (RMB) from firing while flying. Clear it if unused. */
	UPROPERTY(Config, EditAnywhere, Category = "Input|Flying")
	TSoftObjectPtr<UInputAction> AimAction;
};
