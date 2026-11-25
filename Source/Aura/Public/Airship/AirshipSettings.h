// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Engine/DeveloperSettings.h"
#include "Airship/AirshipTypes.h"
#include "AirshipSettings.generated.h"

class AAirshipPawn;
class AAirshipTurret;
class UGameplayEffect;
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

		TurretClass = TSoftClassPtr<AAirshipTurret>(FSoftObjectPath(TEXT("/Game/Assets/MyShip/Drivable/Turret/BP_AirshipTurret.BP_AirshipTurret_C")));
		GunDamageEffect = TSoftClassPtr<UGameplayEffect>(FSoftObjectPath(TEXT("/Game/Level/GAS/GameplayEffects/GE_GunShootDamage.GE_GunShootDamage_C")));

		// On the side edges of the narrow forward deck, a bit behind the small grate near the bow (round 2 spec D6.1):
		// deck top z 655, inboard of the side rails (|y| 292-308) by the base radius
		auto Mount = [](const FVector& Location, float YawMin, float YawMax)
		{
			FAirshipTurretMount Result;
			Result.Location = Location;
			Result.YawMinDeg = YawMin;
			Result.YawMaxDeg = YawMax;
			Result.PitchMinDeg = -20.f;
			Result.PitchMaxDeg = 40.f;
			return Result;
		};

		// Port (station TurretL): 110 deg outboard (toward -Y), 30 deg inboard; starboard mirrored
		TurretMounts.Add(Mount(FVector(2100.0, -245.0, 655.0), -110.f, 30.f));
		TurretMounts.Add(Mount(FVector(2100.0, 245.0, 655.0), -30.f, 110.f));
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

	/**
	 * F takes the helm only at the wheel (Talal 11-25, round2/SPEC_A.md 6.8): the character's feet within this horizontal
	 * distance (cm, hull frame) of the helm's standing spot (the pilot seat: where the pilot stands behind the wheel)...
	 * 0 = only the old ranges below.
	 */
	UPROPERTY(Config, EditAnywhere, Category = "Boarding", meta = (ClampMin = "0.0"))
	float HelmReach = 150.f;

	/** ...within this height (cm) above or below it, and not ahead of the wheel (behind or beside it). */
	UPROPERTY(Config, EditAnywhere, Category = "Boarding", meta = (ClampMin = "0.0"))
	float HelmReachHeight = 100.f;

	/**
	 * The old boarding ranges (v1, round 2), off since Talal 11-25: F under or near the hull does nothing, only HelmReach
	 * takes the helm. Kept so a harness can set them back; a non-zero value takes the helm too. The pawn within this
	 * distance (cm) of the ship's pilot seat (v1: 1200)...
	 */
	UPROPERTY(Config, EditAnywhere, Category = "Boarding", meta = (ClampMin = "0.0"))
	float BoardDistance = 0.f;

	/** ...or within this distance (cm) of the hull's collision (v1: 400)... */
	UPROPERTY(Config, EditAnywhere, Category = "Boarding", meta = (ClampMin = "0.0"))
	float BoardHullDistance = 0.f;

	/**
	 * ...or standing under the hull with at most this much space (cm) above the pawn (a trace straight up hits the hull;
	 * round 2: 1000, a ship hovering over the ground keeps its belly 6-8 m above a player's head). 0 = off.
	 */
	UPROPERTY(Config, EditAnywhere, Category = "Boarding", meta = (ClampMin = "0.0"))
	float BoardBelowDistance = 0.f;

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


	// -------------------------------------------------------------------------
	// Gunner stations (four cannons, two turrets; a player presses F near a seat). Gunners stay in their own character.
	// -------------------------------------------------------------------------

	/** Horizontal radius (cm) around a station's seat in which F mans it (the nearest of the helm and the free stations wins). */
	UPROPERTY(Config, EditAnywhere, Category = "Stations", meta = (ClampMin = "0.0"))
	float StationMountDistance = 350.f;

	/** How far (cm) the pawn's capsule centre may be above the seat (the seat is at the feet: a player on the planks is about 71 cm above it). */
	UPROPERTY(Config, EditAnywhere, Category = "Stations", meta = (ClampMin = "0.0"))
	float StationMountHeightAbove = 600.f;

	/** How far (cm) the pawn may be below the seat. */
	UPROPERTY(Config, EditAnywhere, Category = "Stations", meta = (ClampMin = "0.0"))
	float StationMountHeightBelow = 200.f;

	/**
	 * Cannon seat from the carriage bone (cm): X along the hull, Y inboard (mirrored for starboard), Z up. The default
	 * sits beside the breech, clear of the 60 cm recoil.
	 */
	UPROPERTY(Config, EditAnywhere, Category = "Stations")
	FVector CannonSeatOffset = FVector(-90.0, 130.0, 0.0);

	/** Turret seat from the turret mount (hull space, cm): behind the gun. */
	UPROPERTY(Config, EditAnywhere, Category = "Stations")
	FVector TurretSeatOffset = FVector(-100.0, 0.0, 0.0);

	/** Where a cannon gunner gets off, from the seat (cm, Y inboard and mirrored like the seat), then dropped onto the hull top. */
	UPROPERTY(Config, EditAnywhere, Category = "Stations")
	FVector CannonExitOffset = FVector(0.0, 120.0, 0.0);

	/** Where a turret gunner gets off, from the seat (hull space, cm), then dropped onto the hull top. */
	UPROPERTY(Config, EditAnywhere, Category = "Stations")
	FVector TurretExitOffset = FVector(-150.0, 0.0, 0.0);

	/** Most aim updates (unreliable RPCs) a gunner's machine sends per second. */
	UPROPERTY(Config, EditAnywhere, Category = "Stations", meta = (ClampMin = "1.0"))
	float GunnerAimSendRate = 25.f;

	/** cm the aim point must move before it is sent ahead of the heartbeat. */
	UPROPERTY(Config, EditAnywhere, Category = "Stations", meta = (ClampMin = "0.0"))
	float GunnerAimSendMinDelta = 5.f;

	/** Longest gap (s) between two aim updates (a lost unreliable one is replaced). */
	UPROPERTY(Config, EditAnywhere, Category = "Stations", meta = (ClampMin = "0.05"))
	float GunnerAimHeartbeat = 0.5f;

	/** The server ignores gunner aim points farther than this (cm) from the seat (bad data). */
	UPROPERTY(Config, EditAnywhere, Category = "Stations", meta = (ClampMin = "0.0"))
	float GunnerMaxAimDistance = 70000.f;

	/** Added to the gunner's camera FOV (deg) while Aim (RMB) is held. */
	UPROPERTY(Config, EditAnywhere, Category = "Stations")
	float GunnerAimFOVOffset = -15.f;

	/** Arm length (cm) per mouse wheel step for a gunner's camera. */
	UPROPERTY(Config, EditAnywhere, Category = "Stations", meta = (ClampMin = "0.0"))
	float GunnerZoomStep = 75.f;

	/** The gunner's zoom range, as a fraction of the camera arm length at mount. */
	UPROPERTY(Config, EditAnywhere, Category = "Stations", meta = (ClampMin = "0.1"))
	float GunnerZoomMinScale = 0.5f;

	UPROPERTY(Config, EditAnywhere, Category = "Stations", meta = (ClampMin = "0.1"))
	float GunnerZoomMaxScale = 1.5f;


	// -------------------------------------------------------------------------
	// Crew damage (server)
	// -------------------------------------------------------------------------

	/** Share of each loss of ship Health dealt to the pilot and to every mounted gunner (their own Health). 0 = off. */
	UPROPERTY(Config, EditAnywhere, Category = "Crew", meta = (ClampMin = "0.0"))
	float CrewDamageShare = 0.25f;


	// -------------------------------------------------------------------------
	// Cannons
	// -------------------------------------------------------------------------

	/**
	 * Seconds after which a cannon muzzle FX component is cut (DeactivateImmediate), whatever its system does. A safety
	 * net for a muzzle system that loops. 0 = no cap.
	 */
	UPROPERTY(Config, EditAnywhere, Category = "Cannons", meta = (ClampMin = "0.0"))
	float MuzzleFXMaxSeconds = 1.f;

	/** The ballistic cannon aim corrects for the ship's velocity, which the ball inherits (every scheme). */
	UPROPERTY(Config, EditAnywhere, Category = "Cannons")
	bool bCannonAimLeadShipVelocity = true;


	// -------------------------------------------------------------------------
	// Turrets (two machine guns on the forward deck, AAirshipTurret)
	// -------------------------------------------------------------------------

	/** Off: ships spawn no turrets. */
	UPROPERTY(Config, EditAnywhere, Category = "Turrets")
	bool bSpawnTurrets = true;

	/** Spawned by every ship on the server. Missing: plain AAirshipTurret (no meshes, the gun's tracer). */
	UPROPERTY(Config, EditAnywhere, Category = "Turrets")
	TSoftClassPtr<AAirshipTurret> TurretClass;

	/** Turret mounts in hull space (port, starboard); at most Airship::NumTurrets are used. */
	UPROPERTY(Config, EditAnywhere, Category = "Turrets")
	TArray<FAirshipTurretMount> TurretMounts;

	/**
	 * Damage of one turret bullet = this x the character gun's damage per hit (GunDamageEffect, read at runtime). Also the
	 * gun units one bullet takes off a cannonball's health.
	 */
	UPROPERTY(Config, EditAnywhere, Category = "Turrets", meta = (ClampMin = "0.0"))
	float TurretGunDamageMultiplier = 4.f;

	/** The character gun's damage effect: its additive IncomingDamage magnitudes at level 1 are the gun's damage per hit. */
	UPROPERTY(Config, EditAnywhere, Category = "Turrets")
	TSoftClassPtr<UGameplayEffect> GunDamageEffect;

	/** The gun's damage per hit when GunDamageEffect can't be read statically (SetByCaller, attribute based, an execution, missing). */
	UPROPERTY(Config, EditAnywhere, Category = "Turrets", meta = (ClampMin = "0.0"))
	float GunDamageFallback = 1.f;

	/**
	 * The pilot's camera within this many degrees of the bow: holding Fire (LMB) fires the unmanned turrets at the aim
	 * point and a press fires no broadside. Outside it, LMB fires the broadside as before. 0 = LMB always fires broadsides.
	 */
	UPROPERTY(Config, EditAnywhere, Category = "Turrets", meta = (ClampMin = "0.0", ClampMax = "180.0"))
	float DriverTurretArcDeg = 50.f;


	// -------------------------------------------------------------------------
	// Unpiloted ships (server, UAirshipFlightComponent): drift after a moving exit, hold when parked. Every scheme.
	// -------------------------------------------------------------------------

	/** Speed (cm/s) a ship keeps drifting ahead at after the pilot leaves while moving (never faster than at the exit). 0 = no drift. */
	UPROPERTY(Config, EditAnywhere, Category = "Unpiloted", meta = (ClampMin = "0.0"))
	float DriftSpeed = 250.f;

	/** Forward speed (cm/s) at the exit from which the ship drifts; slower exits coast, then hold. */
	UPROPERTY(Config, EditAnywhere, Category = "Unpiloted", meta = (ClampMin = "0.0"))
	float DriftMinExitSpeed = 100.f;

	/** 1/s: the drift's forward speed loop. */
	UPROPERTY(Config, EditAnywhere, Category = "Unpiloted", meta = (ClampMin = "0.0"))
	float DriftGain = 1.f;

	/** Caps (cm/s^2) of the drift's push forward and its brake (it eases down from cruise speed). */
	UPROPERTY(Config, EditAnywhere, Category = "Unpiloted", meta = (ClampMin = "0.0"))
	float DriftAccelMax = 100.f;

	UPROPERTY(Config, EditAnywhere, Category = "Unpiloted", meta = (ClampMin = "0.0"))
	float DriftDecelMax = 200.f;

	/** Look-ahead sweep length: the drift speed times this (s), at least DriftLookAheadMin (cm). */
	UPROPERTY(Config, EditAnywhere, Category = "Unpiloted", meta = (ClampMin = "0.0"))
	float DriftLookAheadTime = 3.f;

	UPROPERTY(Config, EditAnywhere, Category = "Unpiloted", meta = (ClampMin = "0.0"))
	float DriftLookAheadMin = 600.f;

	/** Seconds between two look-ahead sweeps. */
	UPROPERTY(Config, EditAnywhere, Category = "Unpiloted", meta = (ClampMin = "0.02"))
	float DriftSweepInterval = 0.25f;

	/** The sweep box is the hull's bounds shrunk by this (cm) on every side... */
	UPROPERTY(Config, EditAnywhere, Category = "Unpiloted", meta = (ClampMin = "0.0"))
	float DriftSweepInset = 100.f;

	/** ...with its bottom lifted by this (cm), so level flight over the ground doesn't count as blocked. */
	UPROPERTY(Config, EditAnywhere, Category = "Unpiloted", meta = (ClampMin = "0.0"))
	float DriftSweepFloorLift = 200.f;

	/** A hull contact ends the drift when |dot(contact normal, drift direction)| is at least this (a bow hit). */
	UPROPERTY(Config, EditAnywhere, Category = "Unpiloted", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float DriftBowHitMinDot = 0.5f;

	/** The drift ends (the ship holds) after this distance (cm). 0 = no limit. */
	UPROPERTY(Config, EditAnywhere, Category = "Unpiloted", meta = (ClampMin = "0.0"))
	float DriftMaxDistance = 0.f;

	/** An unpiloted, slow ship that isn't drifting holds its position and heading (no parked creep). */
	UPROPERTY(Config, EditAnywhere, Category = "Unpiloted")
	bool bHoldWhenUnpiloted = true;

	/** Horizontal speed (cm/s) below which an unpiloted ship starts holding. */
	UPROPERTY(Config, EditAnywhere, Category = "Unpiloted", meta = (ClampMin = "0.0"))
	float HoldEngageSpeed = 300.f;

	/** Hold: spring (1/s^2) and damper (1/s) on the centre of mass toward the hold point, capped at HoldAccelMax (cm/s^2). */
	UPROPERTY(Config, EditAnywhere, Category = "Unpiloted", meta = (ClampMin = "0.0"))
	float HoldKp = 0.4f;

	UPROPERTY(Config, EditAnywhere, Category = "Unpiloted", meta = (ClampMin = "0.0"))
	float HoldKd = 0.8f;

	UPROPERTY(Config, EditAnywhere, Category = "Unpiloted", meta = (ClampMin = "0.0"))
	float HoldAccelMax = 200.f;

	/** Drift and hold heading loop: turn rate (deg/s) per degree of heading error, capped at HoldYawRateMax (deg/s). */
	UPROPERTY(Config, EditAnywhere, Category = "Unpiloted", meta = (ClampMin = "0.0"))
	float HoldYawGain = 0.5f;

	UPROPERTY(Config, EditAnywhere, Category = "Unpiloted", meta = (ClampMin = "0.0"))
	float HoldYawRateMax = 10.f;

	/** A holding ship pushed farther than this (cm) or turned more than HoldResetYawDeg re-drops its hold point once slow. */
	UPROPERTY(Config, EditAnywhere, Category = "Unpiloted", meta = (ClampMin = "0.0"))
	float HoldResetDistance = 2000.f;

	UPROPERTY(Config, EditAnywhere, Category = "Unpiloted", meta = (ClampMin = "0.0"))
	float HoldResetYawDeg = 60.f;
};
