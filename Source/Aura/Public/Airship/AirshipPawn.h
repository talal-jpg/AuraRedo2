// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "AbilitySystemInterface.h"
#include "GameFramework/Pawn.h"
#include "Interfaces/MyCombatInterface.h"
#include "Airship/AirshipTypes.h"
#include "Components/SlateWrapperTypes.h"
#include "Engine/TimerHandle.h"
#include "Match/MyMatchTypes.h"
#include "AirshipPawn.generated.h"

class AAirshipCannonball;
class AAirshipPawn;
class AAirshipTurret;
class ACharacter;
class APlayerController;
class UAirshipFlightComponent;
class UAirshipHUDWidget;
class UAirshipLaneComponent;
class UCameraComponent;
class UEnhancedInputLocalPlayerSubsystem;
class UGameplayEffect;
class UInputAction;
class UInputComponent;
class UInputMappingContext;
class UMyAbilitySystemComponent;
class UMyAttributeSet;
class UNiagaraComponent;
class UNiagaraSystem;
class UPhysicalMaterial;
struct FOnAttributeChangeData;
class USkeletalMeshComponent;
class USpringArmComponent;
class UStaticMeshComponent;
class UUserWidget;
struct FGameplayEffectSpecHandle;
struct FInputActionValue;

DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnAirshipPilotChangedSignature, AAirshipPawn*, Airship, ACharacter*, NewPilot);

/** Every machine: a gunner station changed hands (Gunner null = left). Station: EAirshipStation order. */
DECLARE_DYNAMIC_MULTICAST_DELEGATE_ThreeParams(FOnAirshipStationsChangedSignature, AAirshipPawn*, Airship, int32, Station, ACharacter*, Gunner);

/**
 * The drivable airship (Docs/Airship/CPP_NOTES.md). A player on deck walks up to the wheel and presses F
 * (UAirshipPilotComponent, IsWithinHelmReach): the server attaches their character at the helm (PilotSeat), possesses the
 * ship, and F again gives the character back where it stood, behind the wheel.
 *
 * Deck (Talal 11-25, round2/SPEC_A.md 6.8): characters walk on the Mesh's physics asset (PA_Airship, box tops at the
 * planks) and Visibility traces hit it; HullCollision ignores Pawn and Visibility (GetDeckComponent, bDeckOnPhysicsAsset).
 *
 * Root = HullCollision, SM_Airship's 8 convex hulls, simulating physics on every machine and hidden in game. The
 * server applies the flight forces (UAirshipFlightComponent) and the hull replicates through the engine's physics
 * replication (EPhysicsReplicationMode::Default, every server frame: bReplicateEveryFrame; Aura.Airship.RepMode 1 =
 * PredictiveInterpolation, only with Project Settings > Physics > Physics Prediction). The pilot's
 * controls go to the server through an unreliable RPC; the pilot's own machine drives fans, wheel, nozzles and FX from
 * its local input at once, the other machines from the replicated copy.
 *
 * Mesh = SK_Airship (visual, QueryOnly hits), ABP_Airship (UAirshipAnimInstance) writes CR_Airship's rig variables.
 * Camera: spring arm on the hull, free look (control rotation), auto-recenter, FOV with speed and boost.
 *
 * GAS like an enemy: UMyAbilitySystemComponent + UMyAttributeSet on the ship, so every damage source of the project
 * hurts it. Hull impacts above ImpactMinSpeed damage it too. Health 0 -> Die (server, once) -> bIsDead + multicast:
 * forces off, the hull tumbles and falls, the pilot is put back on foot, the rig's wreck solver takes over, LifeSpan.
 *
 * Cannons: 4 on deck (sockets Cannon_L1/L2/R1/R2_Muzzle). Fire shoots the two on the side the camera looks at, aimed
 * at the camera's aim point inside their yaw / elevation limits.
 *
 * Deck passengers (every machine, UAirshipSubsystem): characters standing on the hull, attached to it or airborne next
 * to it ride with QueryOnly collision, so their kinematic capsules don't push the simulated hull (IsPassengerCandidate).
 * Hull hits (every machine): the rebound, speed gain and spin kick of one hit are capped (bLimitImpactResponse).
 * Pilot's machine: the on-foot HUD overlay is hidden and a small ship HUD (UAirshipHUDWidget) shows instead.
 *
 * Control schemes (CPP_NOTES.md section 14): ControlScheme (replicated) picks Classic (v1), Galleon, Sky Racer or
 * Point & Fly; applying it writes a compiled-in preset of every scheme-owned tunable on every machine.
 *
 * Gunner stations (Docs/Airship/round2/SPEC_A.md D5, NOTES_core.md): the four cannons and the two front turrets
 * (AAirshipTurret, spawned on the server at BeginPlay). Any other player presses F near a station's seat: the server
 * attaches their character there (it stays possessed, aims with its own camera) and lists it in StationGunners. The
 * pilot's broadside fires only the unmanned cannons; with the camera in the bow arc, Fire drives the unmanned turrets.
 *
 * Team match (Docs/Airship/round2/SPEC_B.md, CPP_NOTES.md section 16): TeamId (replicated, 255 = a free ship, as in PR A)
 * is set by AMyGameMode for its team ships. Only its own team pilots or mans it (CanBoard / CanMount, UMyTeamLibrary);
 * its fire spares only its own team's deck riders (IsRiderForDamage); sentinel bullets hit it only while it is driven
 * (RefreshSentinelBulletTags); a new team ship is spawn protected until its team boards or mans it (SetSpawnProtected).
 * UAirshipLaneComponent ("Lane") flies an unpiloted team ship along its lane through the flight model's Lane mode.
 */
UCLASS()
class AURA_API AAirshipPawn : public APawn, public IAbilitySystemInterface, public IMyCombatInterface
{
	GENERATED_BODY()

public:

	AAirshipPawn();

	virtual void Tick(float DeltaSeconds) override;

	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	virtual void PossessedBy(AController* NewController) override;

	virtual void UnPossessed() override;

	virtual void NotifyControllerChanged() override;

	virtual void SetupPlayerInputComponent(UInputComponent* PlayerInputComponent) override;

	// IAbilitySystemInterface
	virtual UAbilitySystemComponent* GetAbilitySystemComponent() const override;

	// IMyCombatInterface
	/** Server. Every fatal hit calls it (Health stays at 0): only the first one counts. */
	virtual void Die() override;
	virtual bool IsDead_Implementation() override { return bIsDead; }
	virtual int32 GetLevel_Implementation() override { return ShipLevel; }
	virtual FVector GetCombatSocketLocation_Implementation() override;
	virtual FOnDeathDelegateSignature& GetOnDeathDelegate() override { return OnDeathDelegate; }


	// -------------------------------------------------------------------------
	// Boarding (server)
	// -------------------------------------------------------------------------

	/**
	 * Server: true if Candidate (a living player character with a PlayerState, not manning a gun station) may take the
	 * helm now. Distance not checked.
	 */
	bool CanBoard(const APawn* Candidate) const;

	/**
	 * Distance (cm) from Location to the ship for boarding: within SeatDistance of the pilot seat, within HullDistance of
	 * the hull's collision, or under the hull (a trace straight up from Location hits it within BelowDistance). 0 = that
	 * range off. The old (v1 / round 2) rule: since Talal 11-25 the settings' values are 0, see IsWithinHelmReach.
	 */
	bool IsWithinBoardRange(const FVector& Location, float SeatDistance, float HullDistance, float BelowDistance = 0.f) const;

	/**
	 * Any machine: true if Character may take the helm from where it stands (F, Talal 11-25: "only be able to drive once
	 * close enough to grab the steering wheel"). Its feet within UAirshipSettings::HelmReach (horizontal, hull frame) of the
	 * helm's standing spot (the pilot seat), within HelmReachHeight above or below the deck there (the seat's height on
	 * the physics asset's deck; the hull's lid over it on a ship without physics asset bodies), and not ahead of the wheel: behind
	 * it, or beside it while its capsule still reaches the wheel's plane (the Helm_Wheel bone's hull x + the capsule's
	 * radius). The old ranges (IsWithinBoardRange with the settings' BoardDistance / BoardHullDistance /
	 * BoardBelowDistance, all 0 = off by default) still count when a harness sets them. No other state is checked here
	 * (CanBoard: alive, free helm, not a gunner).
	 */
	bool IsWithinHelmReach(const ACharacter* Character) const;

	/** Server: puts Pilot at the helm and gives PC the ship. False if not allowed (CanBoard). */
	bool BoardPilot(ACharacter* Pilot, APlayerController* PC);

	/**
	 * Server: gives the pilot back their character. Leaving (F): where it stood while driving (the seat, feet on the
	 * planks behind the wheel, facing the bow), walking with the ship as its movement base, no launch (the base carries
	 * it); moved the least that clears it of the ship's bodies. bEject (death, a lethal crew share): 2.5 m to port and
	 * thrown clear with the ship's velocity. A ship whose deck is the hull's collision (no physics asset bodies,
	 * IsDeckOnPhysicsAsset false) leaves like v1: 2.5 m to port on top of the hull, falling with the ship's velocity.
	 */
	void UnboardPilot(bool bEject);

	/**
	 * The owning client of a pilot who just left the helm with F (UAirshipPilotComponent::ClientLeftHelm, after
	 * ClientRestart): its own copy of the character off the hull, its collision back, at the seat on this machine's hull,
	 * walking with the ship as its base. So that copy never falls without a base (left behind at the ship's speed until
	 * the server's correction: the snap of round 1).
	 */
	void PlaceLeftPilotLocal(ACharacter* Pilot);

	UFUNCTION(BlueprintPure, Category = "Airship")
	ACharacter* GetPilot() const { return PilotCharacter; }

	UFUNCTION(BlueprintPure, Category = "Airship")
	bool HasPilot() const { return PilotCharacter != nullptr; }

	/** World location of the pilot seat (where the pilot stands). */
	UFUNCTION(BlueprintPure, Category = "Airship")
	FVector GetPilotSeatLocation() const;

	/**
	 * What characters walk on and what Visibility traces hit (Talal 11-25, SPEC_A.md 6.8): the Mesh's physics asset
	 * (PA_Airship: hull boxes with their tops at the planks, part boxes) when it has bodies and bDeckOnPhysicsAsset, else
	 * the hull's collision (the v1 deck: SM_Airship's UCX lid, 1.2-2.9 m above the planks).
	 */
	UPrimitiveComponent* GetDeckComponent() const;

	/** True if the deck is the Mesh's physics asset (GetDeckComponent): HullCollision then ignores Pawn and Visibility. */
	UFUNCTION(BlueprintPure, Category = "Airship")
	bool IsDeckOnPhysicsAsset() const { return bDeckIsMesh; }

	/**
	 * Sets bDeckOnPhysicsAsset after BeginPlay and applies it on this machine (UpdateDeckCollision): false puts the deck
	 * and the Visibility target back on the hull's collision, as on a ship whose Mesh has no physics asset bodies. Not
	 * replicated: a test or a level script calls it on every machine.
	 */
	UFUNCTION(BlueprintCallable, Category = "Airship")
	void SetDeckOnPhysicsAsset(bool bOnPhysicsAsset);


	// -------------------------------------------------------------------------
	// Team match (SPEC_B; every machine reads, the server writes)
	// -------------------------------------------------------------------------

	/** 0 or 1 for a team ship, 255 (MyMatch::NoTeam) for a free ship (Aura.Airship.Spawn, a placed ship, no match). */
	UFUNCTION(BlueprintPure, Category = "Airship|Match")
	uint8 GetTeamId() const { return TeamId; }

	/**
	 * Server (AMyGameMode; before FinishSpawning for the ships it spawns, so the turrets and the lane see it in
	 * BeginPlay): the team. Puts a pilot or gunner of another team on foot, refreshes the sentinel bullet tags and
	 * tells the lane. 255 makes it a free ship again.
	 */
	void SetTeamId(uint8 NewTeam);

	/** The lane follower (every ship has one; it only acts for team ships while the match has lanes). */
	UAirshipLaneComponent* GetLane() const { return Lane; }

	/** Every machine: the team changed (OnRep, and on the server in SetTeamId). */
	FSimpleMulticastDelegate OnTeamChanged;

	/**
	 * Server: sentinel bullets damage this ship's hull and turrets only while it is driven (a pilot at the helm, or a
	 * controller on it), as only a driven ship is a swarm target (SPEC_B B6.4); a free ship and
	 * UMyMatchSettings::bSentinelBulletsHitUndrivenShips keep PR A's always. Board, exit, possession, team, turrets.
	 */
	void RefreshSentinelBulletTags();

	/**
	 * Server: no damage for Seconds from now (AirshipTags::State_SpawnProtected on the ship's and its turrets' ASCs,
	 * which UMyAttributeSet honours), or until its team first boards the helm or mans a station, whichever comes
	 * first. Seconds <= 0 ends it now. A countdown spawn passes the countdown plus the protection (SPEC_B B3.4).
	 */
	void SetSpawnProtected(float Seconds);

	/** Every machine, from the replicated ProtectionEndServerTime. */
	UFUNCTION(BlueprintPure, Category = "Airship|Match")
	bool IsSpawnProtected() const;

	/** Server time the protection ends (AGameStateBase::GetServerWorldTimeSeconds), 0 = none. */
	double GetProtectionEndServerTime() const { return ProtectionEndServerTime; }

	/**
	 * Server, from GA_GrappleSwing2 (SPEC_B B7.4): Reeler reels in toward this ship with the ship hook (bActive) or
	 * stopped. While any reel is registered the lane holds its speed and heading. An entry expires on its own after
	 * IncomingReelSafetySeconds.
	 */
	void NotifyIncomingReel(const AActor* Reeler, bool bActive);

	/** Server: someone reels in toward this ship now. */
	bool HasIncomingReel() const;

	/**
	 * Server (start aboard, SPEC_B B4.2): Count standing spots on the deck for player pawns (feet on the walkable lid,
	 * the default pawn's capsule above it, facing the bow), nearest the helm first. Fewer when the deck has no more room.
	 */
	void GetDeckSpawnTransforms(int32 Count, TArray<FTransform>& Out) const;


	// -------------------------------------------------------------------------
	// Deck passengers (every machine)
	// -------------------------------------------------------------------------

	/**
	 * True if Character rides this ship now: attached to it (the pilot), standing on it (movement base owned by the ship
	 * or by an actor attached to it), or without a base (jumping, falling, flying) inside the hull's bounds grown by
	 * PassengerZoneMargin. Also true for a character standing on something else inside the hull's own box (turned with
	 * the ship) grown by PassengerZoneMargin: not a rider, but its mesh and jet packs (kinematic WorldDynamic bodies the
	 * hull blocks; the hull ignores only the Pawn capsule) must not meet the hull's convex, which reaches 2.6 m above the
	 * planks. UAirshipSubsystem gives such characters query-only collision, while their actor collision is
	 * on (the attached pilot's capsule is switched right after Exit). A dead ship keeps its riders
	 * until they leave it or the wreck goes (EndPlay): the wreck is still a simulated body, and a kinematic capsule given
	 * back its physics mid-tumble (the ejected pilot, a rider on deck) would shove it like an immovable post.
	 */
	bool IsPassengerCandidate(const ACharacter* Character) const;

	/** This ship's passengers on this machine (IsPassengerCandidate: their physics collision is off meanwhile). */
	UFUNCTION(BlueprintPure, Category = "Airship")
	TArray<ACharacter*> GetPassengers() const;

	/**
	 * True if Character rides this ship (team-blind, every machine): attached to it (the pilot, the gunners), standing on
	 * it (movement base owned by the ship or by an actor attached to it), or without a base inside the hull's own box
	 * (its local bounds, turned with the ship) up to RiderZoneHeight above it, which a rider jumping on deck stays in.
	 * Narrower than IsPassengerCandidate, whose zone is the world bounding box grown by PassengerZoneMargin: next to a
	 * turned ship that box reaches tens of metres out, so an enemy jumping or hovering beside the ship would count. What
	 * "ship-borne" means (UAirshipSubsystem::IsShipBorne); an enemy standing on the deck rides it too.
	 */
	bool IsRiding(const ACharacter* Character) const;

	/**
	 * True if this ship's own fire must spare Character (its cannonballs, turrets and aim traces; the character gun of a
	 * rider at the ship's turrets): IsRiding, and for a rider that isn't attached, on this ship's team (any rider of a
	 * free ship). Attached characters are its pilot and gunners, on its team by construction. Every machine.
	 */
	bool IsRiderForDamage(const ACharacter* Character) const;

	/** Every character IsRiderForDamage spares on this machine (not the actors attached to them). */
	TArray<ACharacter*> GetDamageRiders() const;


	// -------------------------------------------------------------------------
	// Gunner stations (EAirshipStation: cannons L1, L2, R1, R2, turrets L, R)
	// -------------------------------------------------------------------------

	/**
	 * Server: true if Candidate (a living player character with a PlayerState, not at a helm, not manning any station)
	 * may man Station now: the station is free, the ship alive, a turret station's turret there and not wrecked.
	 */
	bool CanMount(const ACharacter* Candidate, int32 Station) const;

	/** Within StationMountDistance (horizontal, hull frame) of the station's seat, StationMountHeightBelow..Above vertically. */
	bool IsWithinStationRange(int32 Station, const FVector& PawnLocation) const;

	/** Server: attaches Gunner at Station's seat (it stays possessed by PC) and lists it. False if not allowed (CanMount). */
	bool MountGunner(ACharacter* Gunner, APlayerController* PC, int32 Station);

	/** Server: frees Station and puts its gunner on the deck next to the seat (GetDeckComponent; bEject: thrown clear, ship death). */
	void DismountGunner(int32 Station, bool bEject);

	/** Server: a manned station's aim point (world, cm). Ignored if not finite or farther than GunnerMaxAimDistance from the seat. */
	void SetStationAim(int32 Station, const FVector& AimPoint);

	/** Server: a manned turret station's trigger. */
	void SetStationTrigger(int32 Station, bool bHeld);

	/** Server: a manned cannon station fires one ball at AimPoint if that cannon is loaded (its own reload). */
	void FireStation(int32 Station, const FVector& AimPoint);

	/** The station Character mans on this ship, -1 if none (every machine, from the replicated StationGunners). */
	int32 FindStationOf(const ACharacter* Character) const;

	UFUNCTION(BlueprintPure, Category = "Airship|Stations")
	ACharacter* GetStationGunner(int32 Station) const;

	UFUNCTION(BlueprintPure, Category = "Airship|Stations")
	bool IsStationManned(int32 Station) const;

	bool IsCannonManned(int32 Cannon) const { return IsStationManned(Cannon); }

	/** Both cannons of Side are manned (the pilot's broadside has nothing to fire there). */
	bool IsSideFullyManned(EAirshipSide Side) const;

	/** World location of a station's seat (where the gunner's feet go). */
	UFUNCTION(BlueprintPure, Category = "Airship|Stations")
	FVector GetStationSeatLocation(int32 Station) const;

	/** Hull-relative transform of a gunner's root at the seat (feet + half height + PilotSeatClearance), facing along the gun. */
	FTransform GetStationSeatRelativeTransform(int32 Station, const ACharacter* Gunner) const;

	/** Every machine: a manned station's aim point (the console's, this machine's own gunner's, else the replicated one). */
	FVector GetStationAimPoint(int32 Station) const;

	/** Every machine: Station's gun at rest points here (world, 100 m out along its rest direction). */
	FVector GetStationRestAimPoint(int32 Station) const;

	/** A gunner's own machine, every frame (UAirshipPilotComponent): the barrel tracks it there at once. */
	void SetLocalStationAim(int32 Station, const FVector& AimPoint);

	/**
	 * A gunner's own client: shows its cannon's shot at once (recoil, flash) if this machine's reload of that cannon is
	 * done, and marks it so the server's multicast skips it here. False (nothing shown) while it reloads.
	 */
	bool PredictStationFire(int32 Station);

	/**
	 * Visibility trace for aiming from this ship (the pilot's camera, a gunner's view): ignores the ship, every actor
	 * attached to it (turrets, the pilot, gunners), its deck passengers and every cannonball (traced again past them, at
	 * most 4 times), so a ball crossing the view never yanks the guns onto it. OutPoint = the hit, or Start + Dir * Distance.
	 */
	bool TraceAimPoint(const FVector& Start, const FVector& Dir, float Distance, FVector& OutPoint) const;

	/** Camera aim trace length (cm): gunners trace as far as the pilot. */
	float GetCannonAimTraceDistance() const { return CannonAimTraceDistance; }

	/** Server: ends the character's active abilities (beam, boost, ...) while it is still their avatar (board, mount). */
	static void CancelPilotAbilities(ACharacter* Pilot);

	/** Every machine: a gunner station changed hands. */
	UPROPERTY(BlueprintAssignable, Category = "Airship|Stations")
	FOnAirshipStationsChangedSignature OnStationsChanged;


	// -------------------------------------------------------------------------
	// Turrets (two machine guns on the forward deck)
	// -------------------------------------------------------------------------

	/** Turret 0 (port) or 1 (starboard), null if not spawned (yet, on a client). */
	UFUNCTION(BlueprintPure, Category = "Airship|Turrets")
	AAirshipTurret* GetTurret(int32 TurretIndex) const;

	/**
	 * A shot along Direction that hit this ship's hull collision at HullImpact: the living turret of this ship it would
	 * reach first past that point (within TurretHullReach), or null. Both turret mounts sit inside SM_Airship's forward
	 * deck convex (UCX_01), so every trace from outside stops on the hull first. The shot only carries on when it
	 * entered the hull at or above the turret's deck plane (less TurretHullPassMargin): from there to the turret the line
	 * runs through the open air over the forward deck, never through the main hull below it. OutTurretHit: the hit on
	 * the turret's HitBox. Collision queries only (every machine).
	 */
	AAirshipTurret* FindTurretBehindHullHit(const FVector& HullImpact, const FVector& Direction, FHitResult& OutTurretHit) const;

	/**
	 * Bound to UMechSentinelSwarmSubsystem::BulletTargetRedirect by UAirshipSubsystem: a sentinel bullet on a ship's
	 * hull over the forward deck hits the turret behind it (FindTurretBehindHullHit). Null for anything else.
	 */
	static AActor* RedirectBulletHitToTurret(const FHitResult& Block, const FVector& Direction, FVector& OutImpact);

	/**
	 * Bound to UMechSentinelSwarmSubsystem::BulletAimRedirect by UAirshipSubsystem: with
	 * UAirshipSettings::SwarmTurretAimChance a sentinel bullet at a ship is aimed at the middle of a living turret's
	 * HitBox (picked at random) instead of the ship's root. False (aim unchanged) for anything else.
	 */
	static bool RedirectBulletAimToTurret(const AActor* Target, const FVector& From, FVector& InOutAimPoint);

	/**
	 * The pilot's machine: Fire drives the unmanned turrets now (the camera within DriverTurretArcDeg of the bow and at
	 * least one turret alive and unmanned); a press then fires no broadside. Every scheme.
	 */
	bool IsDriverTurretArc() const;

	/**
	 * Server, test hook (Aura.Airship.TurretFire): the unmanned turrets fire at Point (bHasPoint) or 100 m ahead of the
	 * bow at muzzle height, until called with bFire false.
	 */
	void SetDebugTurretFire(bool bFire, bool bHasPoint, const FVector& Point);

	/** Server, test hook (Aura.Airship.StationFire): Station aims at AimPoint for Seconds whatever its gunner aims at. */
	void SetStationConsoleAim(int32 Station, const FVector& AimPoint, float Seconds);


	// -------------------------------------------------------------------------
	// Cannons
	// -------------------------------------------------------------------------

	/**
	 * The pilot's machine: fires the broadside on the camera's side at the camera's aim point (its unmanned, loaded
	 * cannons). Nothing while the camera is in the bow arc and Fire drives the turrets (IsDriverTurretArc).
	 */
	UFUNCTION(BlueprintCallable, Category = "Airship|Cannons")
	void RequestFire();

	/** Server: fires the unmanned, loaded cannons of Side at AimPoint (world). Each cannon has its own reload. */
	void FireCannons(EAirshipSide Side, const FVector& AimPoint);

	/** Hull-local muzzle position and rest firing direction (outboard) of a cannon. */
	FVector GetCannonMuzzleLocal(int32 Cannon) const;
	FVector GetCannonRestDirLocal(int32 Cannon) const;

	/** Yaw / elevation (deg, clamped to the cannon's limits) that point Cannon at the world point Target. */
	void ComputeCannonAim(int32 Cannon, const FVector& Target, float& OutYawDeg, float& OutElevDeg) const;

	/**
	 * The same without the limits (the arc test). Ballistic: the elevation is the low arc that drops a ball (CannonballSpeed,
	 * the ball class's GravityScale) on Target, corrected for the muzzle velocity the ball inherits when
	 * UAirshipSettings::bCannonAimLeadShipVelocity is on. Out of range: 45 deg (then out of arc).
	 */
	void ComputeCannonAimRaw(int32 Cannon, const FVector& Target, float& OutYawDeg, float& OutElevDeg) const;

	/** World launch direction (before spread) of the ballistic low arc from Muzzle onto Target (see ComputeCannonAimRaw). */
	FVector ComputeCannonLaunchDir(const FVector& Muzzle, const FVector& Target) const;

	/**
	 * Where a ball fired now along Cannon's barrel (as it points on this machine) is once it has covered the horizontal
	 * distance to AimPoint (world): on AimPoint when the gun is on target, low when the elevation cap leaves it short.
	 * The gunner HUD's gun mark.
	 */
	FVector GetCannonBallPathPoint(int32 Cannon, const FVector& AimPoint) const;

	/** The cannonball's gravity (cm/s^2, positive): world gravity x the ball class's GravityScale. */
	double GetCannonballGravity() const;

	/** The velocity a ball inherits at the world point Muzzle (the ship's velocity and its turn), as SpawnCannonball adds it. */
	FVector GetInheritedMuzzleVelocity(const FVector& Muzzle) const;

	/** True if either unmanned cannon of Side can reach AimPoint inside its yaw and elevation limits (the HUD's arc marks). */
	bool IsAimInCannonArc(EAirshipSide Side, const FVector& AimPoint) const;

	/** True if Cannon can reach AimPoint inside its yaw and elevation limits (the gunner HUD). */
	bool IsCannonAimInArc(int32 Cannon, const FVector& AimPoint) const;

	/** The pilot's machine: this frame's camera aim point (world, cm). */
	const FVector& GetLocalAimPoint() const { return LocalAimPoint; }

	/** Hull-local firing direction for a yaw / elevation. */
	FVector GetCannonDirLocal(int32 Cannon, float YawDeg, float ElevDeg) const;

	/** Cosmetic aim targets (deg) of each cannon this frame: the camera side tracks the aim point, the other rests. */
	float GetCannonAimYawDeg(int32 Cannon) const { return CannonAimYawDeg[FMath::Clamp(Cannon, 0, Airship::NumCannons - 1)]; }
	float GetCannonAimElevDeg(int32 Cannon) const { return CannonAimElevDeg[FMath::Clamp(Cannon, 0, Airship::NumCannons - 1)]; }

	/** Counts the shots of each cannon on this machine (the anim instance starts a recoil when it goes up). */
	int32 GetCannonFireCount(int32 Cannon) const { return CannonFireCount[FMath::Clamp(Cannon, 0, Airship::NumCannons - 1)]; }

	/** The side the cannons track this frame. */
	UFUNCTION(BlueprintPure, Category = "Airship|Cannons")
	EAirshipSide GetAimSide() const { return AimSide; }

	/**
	 * 0 = just fired .. 1 = loaded, for the unmanned cannons of one side on this machine (the least loaded of them; a
	 * client: its own reload clock). 1 when both are manned.
	 */
	UFUNCTION(BlueprintPure, Category = "Airship|Cannons")
	float GetCannonReloadAlpha(EAirshipSide Side) const;

	/** The same for one cannon (the server's clock on the server, this machine's predicted clock on a client). */
	float GetCannonReloadAlpha(int32 Cannon) const;

	/** Reload time of one cannon (s). */
	float GetCannonCooldown() const { return CannonCooldown; }


	// -------------------------------------------------------------------------
	// Damage
	// -------------------------------------------------------------------------

	/**
	 * Server: Damage through the project's damage path (DamageEffectClass, SetByCaller SetDamageByCaller on the ship's ASC).
	 * UAirshipSettings::CrewDamageShare of every Health loss also reaches the pilot and the gunners (FlushCrewDamage).
	 * DamageInstigator (round 2 PR B: the shooter of a fixed-damage gun hit, SPEC_B B6.5) goes into the effect context as
	 * its instigator, so a shot can be told from a crash (hull impacts pass none: the ship itself).
	 */
	UFUNCTION(BlueprintCallable, BlueprintAuthorityOnly, Category = "Airship|Damage")
	void ApplyShipDamage(float Damage, AActor* DamageInstigator = nullptr);

	/** Server, console (Aura.Airship.Kill): health 0 and the normal death, without the crew's share (the crew is ejected alive). */
	void DebugKill();

	UFUNCTION(BlueprintPure, Category = "Airship")
	bool IsAirshipDead() const { return bIsDead; }

	/** Seconds since the death ran on this machine, 0 while alive. */
	float GetDeathTime() const;

	/** Distance (cm) from the bottom of the hull's bounds straight down to the ground (Visibility), -1 if nothing within MaxDistance. */
	UFUNCTION(BlueprintCallable, Category = "Airship")
	float TraceGroundDistance(float MaxDistance = 100000.f) const;

	/** The pilot's machine: true while the ship HUD is on screen (and the on-foot overlay hidden). */
	UFUNCTION(BlueprintPure, Category = "Airship|HUD")
	bool IsShipHUDShown() const { return bShipHUDActive; }


	// -------------------------------------------------------------------------
	// Control schemes (CPP_NOTES.md "Control schemes")
	// -------------------------------------------------------------------------

	/**
	 * Authority: switches the ship to NewScheme (every scheme-owned tunable from the compiled-in preset, the schemes'
	 * runtime state reset) and replicates it. A client only logs a warning.
	 */
	UFUNCTION(BlueprintCallable, Category = "Airship|Controls")
	void SetControlScheme(EAirshipControlScheme NewScheme);

	UFUNCTION(BlueprintPure, Category = "Airship|Controls")
	EAirshipControlScheme GetControlScheme() const { return ControlScheme; }

	/**
	 * Console check (Aura.Airship.Scheme check): every scheme-owned property (flight component, pawn, camera boom) whose
	 * value differs from the archetype's, as "Owner.Name = value (default)". Returns the count: 0 under Classic.
	 */
	int32 GetSchemePropertyDifferences(TArray<FString>& OutDifferences) const;

	/** Galleon, the pilot's machine: the ordered notch (-1 ASTERN .. 3 FULL) and the broadside stations flag it sends. */
	int32 GetGalleonNotch() const { return GalleonNotch; }
	bool IsGalleonStations() const { return bGalleonStations; }

	/** Galleon: the notch whose speed is nearest ForwardSpeedCms (a scheme switch at cruise keeps cruising). */
	static int32 NotchForSpeed(float ForwardSpeedCms);

	/** Point & Fly, the pilot's machine: the scheme is on (and the ship alive), the heading target sent (world yaw), Aim held (free look), the gun lock engaged and its swing (-1 left, +1 right, 0 none). */
	bool IsPointFlyActive() const { return ControlScheme == EAirshipControlScheme::PointFly && !bIsDead; }
	float GetPFHeadingTargetDeg() const { return PFSentHeading; }
	bool IsPFFreeLook() const { return bPFFree; }
	bool IsPFGunLocked() const { return bPFLock; }
	int32 GetPFLockSwingDir() const { return PFLockSwingDir; }

	/** Point & Fly, the pilot's machine: parked free look (entered at rest with no drive / turn key, held at any speed until one, Aim or an outside camera set above PFParkSpeed: the mouse looks around, the heading holds). */
	UFUNCTION(BlueprintPure, Category = "Airship|PointFly")
	bool IsPFParked() const { return bPFParked; }

	/** The pilot's machine: the lane flies the ship and the pilot only looks and fires (the replicated lane state is Assist). */
	bool IsLaneAssistLook() const;

	/** The cannons' yaw limit (deg either side of their rest direction): the HUD's arc marks. */
	float GetCannonYawLimitDeg() const { return CannonYawLimitDeg; }


	// -------------------------------------------------------------------------
	// Test hooks (Python PIE harness, console)
	// -------------------------------------------------------------------------

	/**
	 * Flies the ship with these controls (-1..1) until DebugClearInput, pilot or not. On the pilot's machine (host or
	 * client) they replace the keys and reach the server like them (a client's through ServerSetPilotInput); on the
	 * server's copy of a ship piloted from a client, or of one without a pilot, they drive the forces directly.
	 */
	UFUNCTION(BlueprintCallable, Category = "Airship|Test")
	void DebugSetInput(float Throttle, float Steer, float Lift, float Strafe, bool bBoost, bool bBrake);

	UFUNCTION(BlueprintCallable, Category = "Airship|Test")
	void DebugClearInput();

	/** Speeds, altitude, attitude, fuel, health now (server values on the server). */
	UFUNCTION(BlueprintPure, Category = "Airship|Test")
	FAirshipFlightTelemetry GetFlightTelemetry() const;

	/** Re-applies body settings and actuator positions after a property change (Aura.Airship.Set). */
	void OnTuningChanged();

	/** Hull-space rest position (cm) of a bone or socket of the mesh. False if the mesh has neither. */
	bool GetMeshRestLocation(FName BoneOrSocket, FVector& OutHullLocal) const;

	/**
	 * UAirshipFlightComponent (server, inside this pawn's tick): a velocity change (cm/s, world) the flight model gives
	 * the hull in this frame's physics step (boost and drift kicks). The impact cap counts it as the ship's own speed,
	 * not as a contact's kick.
	 */
	void NoteFlightKick(const FVector& DeltaV) { PreStepFlightKick += DeltaV; }


	// -------------------------------------------------------------------------
	// Accessors
	// -------------------------------------------------------------------------

	UStaticMeshComponent* GetHull() const { return HullCollision; }
	USkeletalMeshComponent* GetMesh() const { return Mesh; }
	UAirshipFlightComponent* GetFlight() const { return Flight; }
	UCameraComponent* GetCamera() const { return Camera; }
	const FAirshipCosmeticState& GetCosmeticState() const;

	/** Every machine: the pilot changed (null = left). */
	UPROPERTY(BlueprintAssignable, Category = "Airship")
	FOnAirshipPilotChangedSignature OnPilotChanged;

protected:

	virtual void BeginPlay() override;

	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

	/** Blueprint hooks, every machine. */
	UFUNCTION(BlueprintImplementableEvent, Category = "Airship", meta = (DisplayName = "On Airship Died"))
	void BP_OnAirshipDied();

	UFUNCTION(BlueprintImplementableEvent, Category = "Airship", meta = (DisplayName = "On Cannons Fired"))
	void BP_OnCannonsFired(EAirshipSide Side);

	/** Server: the hull hit something hard enough to take damage. ImpactSpeed in cm/s. */
	UFUNCTION(BlueprintImplementableEvent, Category = "Airship", meta = (DisplayName = "On Hull Impact"))
	void BP_OnHullImpact(float ImpactSpeed, float Damage, const FHitResult& Hit);


	// -------------------------------------------------------------------------
	// Components
	// -------------------------------------------------------------------------

	/** SM_Airship (8 convex hulls): the physics body. Hidden in game. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Airship|Components")
	TObjectPtr<UStaticMeshComponent> HullCollision;

	/** SK_Airship with ABP_Airship. Kinematic; QueryOnly hits (aim, abilities) on its physics asset bodies. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Airship|Components")
	TObjectPtr<USkeletalMeshComponent> Mesh;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Airship|Components")
	TObjectPtr<USpringArmComponent> CameraBoom;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Airship|Components")
	TObjectPtr<UCameraComponent> Camera;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Airship|Components")
	TObjectPtr<UAirshipFlightComponent> Flight;

	/** Team ships: follows the team's lane while nobody flies the ship (SPEC_B B2). Idle on free ships. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Airship|Components")
	TObjectPtr<UAirshipLaneComponent> Lane;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Airship|Components")
	TObjectPtr<UMyAbilitySystemComponent> AbilitySystemComponent;

	UPROPERTY()
	TObjectPtr<UMyAttributeSet> AttributeSet;

	/** Thruster jets on the Thruster_*_Flame sockets (FL, FR, RL, RR); set the Niagara system on the Blueprint. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Airship|Components")
	TObjectPtr<UNiagaraComponent> ThrusterFX_FL;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Airship|Components")
	TObjectPtr<UNiagaraComponent> ThrusterFX_FR;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Airship|Components")
	TObjectPtr<UNiagaraComponent> ThrusterFX_RL;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Airship|Components")
	TObjectPtr<UNiagaraComponent> ThrusterFX_RR;

	/** Fan exhaust on the Turbine_L/R_Exhaust sockets. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Airship|Components")
	TObjectPtr<UNiagaraComponent> TurbineFX_L;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Airship|Components")
	TObjectPtr<UNiagaraComponent> TurbineFX_R;


	// -------------------------------------------------------------------------
	// Input (null: Project Settings > Game > Airship)
	// -------------------------------------------------------------------------

	UPROPERTY(EditDefaultsOnly, Category = "Airship|Input")
	TObjectPtr<UInputMappingContext> AirshipMappingContext;

	UPROPERTY(EditDefaultsOnly, Category = "Airship|Input")
	TObjectPtr<UInputAction> ThrottleAction;

	UPROPERTY(EditDefaultsOnly, Category = "Airship|Input")
	TObjectPtr<UInputAction> SteerAction;

	UPROPERTY(EditDefaultsOnly, Category = "Airship|Input")
	TObjectPtr<UInputAction> LiftAction;

	UPROPERTY(EditDefaultsOnly, Category = "Airship|Input")
	TObjectPtr<UInputAction> StrafeAction;

	UPROPERTY(EditDefaultsOnly, Category = "Airship|Input")
	TObjectPtr<UInputAction> BoostAction;

	UPROPERTY(EditDefaultsOnly, Category = "Airship|Input")
	TObjectPtr<UInputAction> BrakeAction;

	UPROPERTY(EditDefaultsOnly, Category = "Airship|Input")
	TObjectPtr<UInputAction> FireAction;

	UPROPERTY(EditDefaultsOnly, Category = "Airship|Input")
	TObjectPtr<UInputAction> LookAction;

	UPROPERTY(EditDefaultsOnly, Category = "Airship|Input")
	TObjectPtr<UInputAction> ZoomAction;

	UPROPERTY(EditDefaultsOnly, Category = "Airship|Input")
	TObjectPtr<UInputAction> ExitAction;

	UPROPERTY(EditDefaultsOnly, Category = "Airship|Input")
	TObjectPtr<UInputAction> AimAction;


	// -------------------------------------------------------------------------
	// GAS
	// -------------------------------------------------------------------------

	/** Set at BeginPlay (server): MaxHealth first, then Health = MaxHealth. The gun deals 1 per hit. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|GAS", meta = (ClampMin = "1.0"))
	float MaxHealth = 2000.f;

	/** UExecCalc_Damage: percent chance a hit shows as blocked (cosmetic). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|GAS", meta = (ClampMin = "0.0", ClampMax = "100.0"))
	float Armor = 0.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|GAS", meta = (ClampMin = "1"))
	int32 ShipLevel = 1;

	/**
	 * Damage effect for hull impacts, console damage and the cannonballs (when their own is unset): SetByCaller
	 * SetDamageByCaller. Null = UAirshipDamageEffect (built in, IncomingDamage). GE_ProjectileDamage adds block / crit.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|GAS")
	TSubclassOf<UGameplayEffect> DamageEffectClass;


	// -------------------------------------------------------------------------
	// Hull impacts (server)
	// -------------------------------------------------------------------------

	/**
	 * Impact speed (cm/s) from which the hull takes damage: the closing speed along the contact normal at the contact
	 * point before the hit (hull velocity + spin, minus the other body's velocity), so it doesn't depend on restitution.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Impact", meta = (ClampMin = "0.0"))
	float ImpactMinSpeed = 400.f;

	/** Damage per m/s of impact speed above ImpactMinSpeed (head-on at 50 m/s: 276, at 87 m/s boost: 498). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Impact", meta = (ClampMin = "0.0"))
	float ImpactDamagePerMS = 6.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Impact", meta = (ClampMin = "0.0"))
	float ImpactMaxDamage = 500.f;

	/** Seconds between two damaging impacts. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Impact", meta = (ClampMin = "0.0"))
	float ImpactCooldown = 0.4f;

	/**
	 * Every machine: caps what contacts do to the hull in each physics step, measured from the hull's velocities before
	 * that step. What flight forces and gravity can do in one step (ImpactEpisodeAccel / ImpactEpisodeSpinAccelDeg times
	 * the step) always passes. Beyond it, kick budgets: ImpactMaxReboundSpeed of upward speed above the upward speed it
	 * had (0 when falling: no bounce, no depenetration pop upward), ImpactMaxSpeedGain of horizontal speed and of speed (no
	 * sideways kick off a slope, no pop), ImpactMaxSpinKickDeg of spin (dead: DeadImpactMaxSpinKickDeg; a reversal or a
	 * turned spin axis counts from the stop). The hits of one contact (less than ImpactEpisodeGap apart) share them, so a
	 * push-out over several frames can't add its kicks up; during a long contact (landed, scraping) they come back over
	 * ImpactKickRefillTime, so a hit late in it is capped like the first. Losing speed or spin is never limited, and the
	 * boost / drift kicks are the ship's own (NoteFlightKick). Restitution itself is the physical material's.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Impact")
	bool bLimitImpactResponse = true;

	/** cm/s of upward speed a contact may add (budget). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Impact", meta = (ClampMin = "0.0", EditCondition = "bLimitImpactResponse"))
	float ImpactMaxReboundSpeed = 250.f;

	/** cm/s of horizontal speed, and of speed, a contact may add (two budgets). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Impact", meta = (ClampMin = "0.0", EditCondition = "bLimitImpactResponse"))
	float ImpactMaxSpeedGain = 500.f;

	/** deg/s of spin a contact may add (budget). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Impact", meta = (ClampMin = "0.0", EditCondition = "bLimitImpactResponse"))
	float ImpactMaxSpinKickDeg = 20.f;

	/** deg/s, the wreck */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Impact", meta = (ClampMin = "0.0", EditCondition = "bLimitImpactResponse"))
	float DeadImpactMaxSpinKickDeg = 40.f;

	/** Seconds without a hit that end a contact (at least 2.5 frames, for low frame rates): the budgets are full again. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Impact", meta = (ClampMin = "0.0", EditCondition = "bLimitImpactResponse"))
	float ImpactEpisodeGap = 0.25f;

	/** Seconds for a used-up budget to come back while a contact lasts. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Impact", meta = (ClampMin = "0.01", EditCondition = "bLimitImpactResponse"))
	float ImpactKickRefillTime = 1.f;

	/**
	 * What flight forces and gravity may change per second during a contact, never counted as a kick: this times the
	 * physics step passes every step (cm/s per s, 2500 covers the boost's 1960; spin: deg/s per s). The wreck has no
	 * lift: no free upward change once dead.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Impact", meta = (ClampMin = "0.0", EditCondition = "bLimitImpactResponse"))
	float ImpactEpisodeAccel = 2500.f;

	/**
	 * Base fix 4e: the free upward change per second (cm/s per s) in place of ImpactEpisodeAccel. 0 = the same as
	 * ImpactEpisodeAccel (v1). Keep it at or above the largest upward flight acceleration, (CollectiveMax - 1) g +
	 * 0.35 g + VertBrakeAccel, or a scrape caps the flight forces like kicks.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Impact", meta = (ClampMin = "0.0", EditCondition = "bLimitImpactResponse"))
	float ImpactEpisodeAccelUp = 0.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Impact", meta = (ClampMin = "0.0", EditCondition = "bLimitImpactResponse"))
	float ImpactEpisodeSpinAccelDeg = 90.f;

	/** The hull mesh shows in game when the Mesh has no skeletal mesh (C++-only tests). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Debug")
	bool bShowHullWithoutMesh = true;

	/**
	 * Optional physical material for the hull. BP_AirshipPawn uses PM_AirshipHull: friction 0.2, restitution 0.08 with
	 * Restitution Combine Mode Min + override, so the hull's low bounce wins against any surface (as_42; it was 0.35 Max).
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Impact")
	TObjectPtr<UPhysicalMaterial> HullPhysicalMaterial;


	// -------------------------------------------------------------------------
	// Pilot
	// -------------------------------------------------------------------------

	/** Bone or socket of the mesh where the pilot stands (rest pose). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Pilot")
	FName PilotSeatSocket = TEXT("PilotSeat");

	/** Hull-space pilot seat (cm) when the mesh has no PilotSeat bone (round 2 helm, SourceArt/Airship/turret_dims.json pilot_seat_ue). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Pilot")
	FVector PilotSeatFallback = FVector(-740.0, 0.0, 264.2);

	/** Extra height (cm) above the seat for the pilot's capsule bottom, so it never touches the hull. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Pilot", meta = (ClampMin = "0.0"))
	float PilotSeatClearance = 5.f;

	/**
	 * Hull-space offset (cm) from the seat where an ejected pilot (death, lethal crew share) is put before it is thrown
	 * clear (then dropped onto the top of the hull's collision by a trace). Leaving with F keeps the seat (UnboardPilot).
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Pilot")
	FVector ExitOffset = FVector(0.0, -250.0, 0.0);

	/** Bone of the steering wheel (rest pose): F at the helm must not come from ahead of its plane (IsWithinHelmReach). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Pilot")
	FName HelmWheelBone = TEXT("Helm_Wheel");

	/** Hull-space wheel hub (cm) when the mesh has no HelmWheelBone (round 2 helm, SourceArt/Airship/turret_dims.json helm_wheel_ue). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Pilot")
	FVector HelmWheelFallback = FVector(-685.0, 0.0, 360.5);

	/**
	 * Characters walk on the Mesh's physics asset (PA_Airship) and Visibility traces hit it, while HullCollision (the
	 * flight body) ignores Pawn and Visibility (Talal 11-25, SPEC_A.md 6.8). Off, or a Mesh without physics bodies (a
	 * plain AAirshipPawn): the hull's collision is the deck and the target (v1). Applied at BeginPlay.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Pilot")
	bool bDeckOnPhysicsAsset = true;

	/**
	 * Off: characters on the deck keep their physics collision (their kinematic capsules push the simulated hull: the
	 * ship sinks under a standing character).
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Pilot")
	bool bPassengersQueryOnly = true;

	/**
	 * Characters without a movement base (jumping, falling) inside the hull's world bounds grown by this (cm) count as
	 * passengers; so do characters standing on something else inside the hull's own box grown by this.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Pilot", meta = (ClampMin = "0.0"))
	float PassengerZoneMargin = 300.f;

	/**
	 * Friendly fire (IsRiderForDamage): a character without a movement base inside the hull's own box, or up to this far
	 * (cm) above its top, is still one of this ship's riders (a jump on deck, a fall back onto it).
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Pilot", meta = (ClampMin = "0.0"))
	float RiderZoneHeight = 400.f;

	/** Ship death: the pilot is thrown up and out to the side (cm/s), on top of the ship's velocity. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Pilot", meta = (ClampMin = "0.0"))
	float EjectUpSpeed = 1200.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Pilot", meta = (ClampMin = "0.0"))
	float EjectSideSpeed = 600.f;

	/** Start aboard (GetDeckSpawnTransforms): spots this far apart (cm) on the deck. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Pilot", meta = (ClampMin = "50.0"))
	float DeckSpawnSpacing = 260.f;

	/** A ship-hook reel announced with NotifyIncomingReel ends by itself after this long (s) if nobody ends it (the reel's own limit is 5 s). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Pilot", meta = (ClampMin = "0.1"))
	float IncomingReelSafetySeconds = 6.f;


	// -------------------------------------------------------------------------
	// Cannons
	// -------------------------------------------------------------------------

	/** Muzzle bones / sockets, L1, L2, R1, R2. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Cannons", EditFixedSize)
	TArray<FName> CannonMuzzleSockets = { TEXT("Cannon_L1_Muzzle"), TEXT("Cannon_L2_Muzzle"), TEXT("Cannon_R1_Muzzle"), TEXT("Cannon_R2_Muzzle") };

	/** Barrel bones (trunnions): rest direction = muzzle - barrel. Missing: straight outboard. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Cannons", EditFixedSize)
	TArray<FName> CannonBarrelSockets = { TEXT("Cannon_L1_Barrel"), TEXT("Cannon_L2_Barrel"), TEXT("Cannon_R1_Barrel"), TEXT("Cannon_R2_Barrel") };

	/** Hull-space muzzles (cm) when the mesh has no muzzle bones. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Cannons", EditFixedSize)
	TArray<FVector> CannonMuzzleFallback = { FVector(-44.8, -784.5, 323.7), FVector(-1143.7, -578.7, 363.5), FVector(-44.8, 784.5, 323.7), FVector(-1143.7, 578.7, 363.5) };

	/** Carriage bones, L1, L2, R1, R2: a cannon gunner's seat is UAirshipSettings::CannonSeatOffset from it. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Cannons", EditFixedSize)
	TArray<FName> CannonCarriageBones = { TEXT("Cannon_L1"), TEXT("Cannon_L2"), TEXT("Cannon_R1"), TEXT("Cannon_R2") };

	/** Hull-space carriages (cm, README_rig.md) when the mesh has no carriage bones. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Cannons", EditFixedSize)
	TArray<FVector> CannonCarriageFallback = { FVector(-46.3, -598.5, 243.7), FVector(-1147.2, -392.7, 283.6), FVector(-46.3, 598.5, 243.7), FVector(-1147.2, 392.7, 283.6) };

	/** Null: AAirshipCannonball. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Cannons")
	TSubclassOf<AAirshipCannonball> CannonballClass;

	/**
	 * Muzzle speed (cm/s), the ship's own velocity is added. Slow enough to see the arc: with the ball's GravityScale 0.6 the
	 * level range at the 8.5 deg elevation cap is v^2 sin 17 / g' = 244 m.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Cannons", meta = (ClampMin = "0.0"))
	float CannonballSpeed = 7000.f;

	/** Damage per ball (SetByCaller). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Cannons", meta = (ClampMin = "0.0"))
	float CannonballDamage = 60.f;

	/** Reload time of one cannon (s). Each cannon reloads on its own (a gunner's cannon, the pilot's broadside). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Cannons", meta = (ClampMin = "0.0"))
	float CannonCooldown = 1.5f;

	/** Aim limits (deg): yaw both ways about hull +Z, elevation down / up. Same as the anim instance's. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Cannons", meta = (ClampMin = "0.0", ClampMax = "90.0"))
	float CannonYawLimitDeg = 20.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Cannons", meta = (ClampMin = "-90.0", ClampMax = "0.0"))
	float CannonElevMinDeg = -10.f;

	/**
	 * The barrel meets its own carriage at 8.75 (README_rig.md ranges); 8.5 leaves room for the barrel drive's
	 * overshoot (9.32 peak at an 8.75 target, cr_eval R2). Same as the anim instance's.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Cannons", meta = (ClampMin = "0.0", ClampMax = "90.0"))
	float CannonElevMaxDeg = 8.5f;

	/** Random spread of each ball (deg). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Cannons", meta = (ClampMin = "0.0"))
	float CannonSpreadDeg = 0.6f;

	/** Balls start this far (cm) in front of the muzzle, and at least the ball's radius + 30 (a 1 m ball never starts in the barrel). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Cannons", meta = (ClampMin = "0.0"))
	float CannonSpawnForwardOffset = 80.f;

	/** Hull kick per cannon (speed change, cm/s), at the muzzle, every machine. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Cannons", meta = (ClampMin = "0.0"))
	float CannonRecoilImpulseDV = 80.f;

	/** Camera aim trace length (cm). Nothing hit: the point at this distance. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Cannons", meta = (ClampMin = "100.0"))
	float CannonAimTraceDistance = 60000.f;

	/** The aim side switches once the aim point is this far (cm) on the other side of the keel. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Cannons", meta = (ClampMin = "0.0"))
	float AimSideHysteresis = 300.f;

	/** Muzzle flash spawned on each muzzle bone when it fires (every machine). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Cannons")
	TObjectPtr<UNiagaraSystem> MuzzleFX;


	// -------------------------------------------------------------------------
	// Death
	// -------------------------------------------------------------------------

	/** Seconds the wreck stays after death. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Death", meta = (ClampMin = "0.0"))
	float WreckLifeSpan = 25.f;

	/** Server: random spin kick at death (rad/s per axis, roll / pitch / yaw) and a push (cm/s) at a random pod. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Death")
	FVector DeathAngularKick = FVector(0.25, 0.15, 0.3);

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Death", meta = (ClampMin = "0.0"))
	float DeathPodKickDV = 300.f;

	/** Spawned at the ship at death (every machine). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Death")
	TObjectPtr<UNiagaraSystem> DeathExplosionFX;

	/** Attached to DeathFireSocket at death and left burning on the wreck. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Death")
	TObjectPtr<UNiagaraSystem> DeathFireFX;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Death")
	FName DeathFireSocket = TEXT("Hull");


	// -------------------------------------------------------------------------
	// Camera (pilot's machine)
	// -------------------------------------------------------------------------

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Camera", meta = (ClampMin = "0.0"))
	float CameraArmLength = 6500.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Camera", meta = (ClampMin = "0.0"))
	float CameraArmMin = 4000.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Camera", meta = (ClampMin = "0.0"))
	float CameraArmMax = 12000.f;

	/** Arm change per wheel step (cm) and how fast the arm follows (1/s). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Camera", meta = (ClampMin = "0.0"))
	float CameraZoomStep = 800.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Camera", meta = (ClampMin = "0.0"))
	float CameraZoomInterpSpeed = 6.f;

	/** Extra arm length at full boost (cm): the camera falls back. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Camera", meta = (ClampMin = "0.0"))
	float CameraBoostArmExtra = 1000.f;

	/** Field of view (deg): base, + SpeedFOVExtra from SpeedFOVStart to SpeedFOVFull forward speed (cm/s), + boost, + aim. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Camera", meta = (ClampMin = "10.0", ClampMax = "170.0"))
	float BaseFOV = 85.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Camera")
	float SpeedFOVExtra = 10.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Camera", meta = (ClampMin = "0.0"))
	float SpeedFOVStart = 2000.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Camera", meta = (ClampMin = "0.0"))
	float SpeedFOVFull = 4800.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Camera")
	float BoostFOVExtra = 12.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Camera")
	float AimFOVOffset = -15.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Camera", meta = (ClampMin = "0.0"))
	float FOVInterpSpeed = 4.f;

	/** Camera pitch range (deg) and the pitch it starts at / recenters to. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Camera", meta = (ClampMin = "-89.0", ClampMax = "0.0"))
	float CameraPitchMin = -60.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Camera", meta = (ClampMin = "0.0", ClampMax = "89.0"))
	float CameraPitchMax = 25.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Camera")
	float CameraDefaultPitch = -12.f;

	/** Auto-recenter: after this long without look input (s) and above RecenterMinSpeed (cm/s), the view eases behind the ship. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Camera", meta = (ClampMin = "0.0"))
	float RecenterDelay = 1.5f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Camera", meta = (ClampMin = "0.0"))
	float RecenterMinSpeed = 800.f;

	/** Recenter rate (1/s, exponential). 0 = off. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Camera", meta = (ClampMin = "0.0"))
	float RecenterSpeed = 2.f;


	// -------------------------------------------------------------------------
	// Control scheme (CPP_NOTES.md "Control schemes")
	// -------------------------------------------------------------------------

	/**
	 * How the pilot's keys and camera fly the ship. Applying it (BeginPlay, SetControlScheme, OnRep) writes every
	 * scheme-owned tunable of the flight component, this pawn and the camera boom from a compiled-in preset (Classic =
	 * the class defaults, i.e. v1), on every machine. Change it at runtime with SetControlScheme or Aura.Airship.Scheme.
	 * Default Point & Fly (the judged winner, 2026-11-23); the tunables' class defaults stay Classic's (v1), so Classic is
	 * still exact v1 and "Aura.Airship.Scheme 0" + "check" still lists 0 differences.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, ReplicatedUsing = OnRep_ControlScheme, Category = "Airship|Controls")
	EAirshipControlScheme ControlScheme = EAirshipControlScheme::PointFly;


	// -------------------------------------------------------------------------
	// Feedback: camera shake, FOV kick, camera roll, rumble (pilot's machine; the defaults are off = v1)
	// -------------------------------------------------------------------------

	/** Camera relative rotation (deg) / location (cm) jitter at trauma 1 (it grows with trauma squared), its Perlin frequency (Hz) and the trauma decay (1/s). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Feedback", meta = (ClampMin = "0.0"))
	float ShakeRotDeg = 0.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Feedback", meta = (ClampMin = "0.0"))
	float ShakeLocCm = 0.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Feedback", meta = (ClampMin = "0.0"))
	float ShakeFrequency = 10.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Feedback", meta = (ClampMin = "0.0"))
	float ShakeDecay = 2.f;

	/** FOV punch decay (1/s, exponential) and the FOV clamp (deg; 0 = 170). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Feedback", meta = (ClampMin = "0.0"))
	float FOVKickDecay = 3.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Feedback", meta = (ClampMin = "0.0"))
	float FOVMaxDeg = 0.f;

	/**
	 * Camera roll (deg, + = right side down) = CameraRollPerBank x hull roll + CameraRollPerSteerDeg x cosmetic steer (x
	 * GunDeckBankScale on the gun deck), clamped to CameraRollMaxDeg, interpolated at CameraRollInterpSpeed (1/s; 0 = none).
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Feedback")
	float CameraRollPerBank = 0.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Feedback")
	float CameraRollPerSteerDeg = 0.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Feedback", meta = (ClampMin = "0.0"))
	float CameraRollMaxDeg = 6.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Feedback", meta = (ClampMin = "0.0"))
	float CameraRollInterpSpeed = 0.f;

	/** Multiplies every gamepad rumble (0 = off). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Feedback", meta = (ClampMin = "0.0"))
	float RumbleScale = 0.f;

	/** Hull hit: trauma and rumble per m/s of impact speed above ImpactMinSpeed (trauma capped at ShakeHitMax). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Feedback", meta = (ClampMin = "0.0"))
	float ShakeHitPerMS = 0.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Feedback", meta = (ClampMin = "0.0"))
	float ShakeHitMax = 1.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Feedback", meta = (ClampMin = "0.0"))
	float RumbleHitPerMS = 0.f;

	/** While drifting: a trauma floor and a continuous small-motor rumble, each base + per unit Sky Racer charge. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Feedback", meta = (ClampMin = "0.0"))
	float DriftTraumaBase = 0.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Feedback", meta = (ClampMin = "0.0"))
	float DriftTraumaPerCharge = 0.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Feedback", meta = (ClampMin = "0.0"))
	float DriftRumbleBase = 0.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Feedback", meta = (ClampMin = "0.0"))
	float DriftRumblePerCharge = 0.f;

	/** Per event: boost start, own broadside, drift kick (v1 drift / Galleon swing exit), Sky Racer turbo tier 1 / 2 / 3, Galleon order change (FOV sign = direction), Point & Fly gun lock. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Feedback")
	FAirshipFeedbackEvent FeedbackBoostStart;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Feedback")
	FAirshipFeedbackEvent FeedbackOwnBroadside;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Feedback")
	FAirshipFeedbackEvent FeedbackDriftKick;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Feedback")
	FAirshipFeedbackEvent FeedbackTurbo1;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Feedback")
	FAirshipFeedbackEvent FeedbackTurbo2;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Feedback")
	FAirshipFeedbackEvent FeedbackTurbo3;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Feedback")
	FAirshipFeedbackEvent FeedbackOrderChange;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Feedback")
	FAirshipFeedbackEvent FeedbackLockEngage;


	// -------------------------------------------------------------------------
	// Galleon, pilot side (only read while ControlScheme == Galleon: the defaults are Galleon's values)
	// -------------------------------------------------------------------------

	/** Telegraph: the throttle axis past Press is a press, back under Release a release (keys and stick). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Galleon", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float GalleonOrderAxisPress = 0.5f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Galleon", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float GalleonOrderAxisRelease = 0.3f;

	/** Holding W / S auto-steps after this (s), then every interval (s). Auto-repeat never passes STOP. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Galleon", meta = (ClampMin = "0.0"))
	float GalleonOrderRepeatDelay = 0.25f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Galleon", meta = (ClampMin = "0.0"))
	float GalleonOrderRepeatInterval = 0.15f;

	/** Beam watch: the camera more than Enter (deg) off the bow, until back within Exit. It never recentres. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Galleon", meta = (ClampMin = "0.0"))
	float GalleonBeamWatchEnterDeg = 55.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Galleon", meta = (ClampMin = "0.0"))
	float GalleonBeamWatchExitDeg = 40.f;

	/** Beam watch gives broadside stations only this long (s) after an own broadside (review R1; 0 = always). Aim held gives them at once. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Galleon", meta = (ClampMin = "0.0"))
	float GalleonStationsFireHoldTime = 6.f;

	/** Camera yaw into the turn per unit shaped helm (deg) and its filter (s). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Galleon")
	float GalleonLookAheadDeg = 10.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Galleon", meta = (ClampMin = "0.0"))
	float GalleonLookAheadTau = 0.12f;


	// -------------------------------------------------------------------------
	// Sky Racer, pilot side (only read while ControlScheme == SkyRacer: the defaults are Sky Racer's values)
	// -------------------------------------------------------------------------

	/** Auto-follow aims this long (s) ahead of the commanded turn (capped, deg) ... */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyLookIntoTurnTime = 0.3f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyLookIntoTurnMaxDeg = 14.f;

	/** ... minus this share of the slip (the slide reads) ... */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyCamSlipShare = 0.35f;

	/** ... and also turns at the commanded rate (no follow lag). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer")
	bool bSkyCamYawRateFF = true;

	/** Look down into a dive: deg per m/s of sink, capped (deg). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyCamDivePitchPerMS = 0.4f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyCamDivePitchMaxDeg = 8.f;

	/** The arm grows by this (cm) with a fresh mini-turbo burn. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer", meta = (ClampMin = "0.0"))
	float SkyTurboArmExtra = 600.f;


	// -------------------------------------------------------------------------
	// Point & Fly, pilot side (only read while ControlScheme == PointFly: the defaults are Point & Fly's values)
	// -------------------------------------------------------------------------

	/** Q/E turn the heading target at this x the ship's own full turn rate for its speed. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|PointFly", meta = (ClampMin = "0.0"))
	float PFNudgeRateScale = 1.f;

	/** In steering mode the target stays within this (deg) of the nose (no flip at 180). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|PointFly", meta = (ClampMin = "0.0"))
	float PFHeadingMaxLeadDeg = 150.f;

	/** After broadside mode the camera eases back onto the heading target (s). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|PointFly", meta = (ClampMin = "0.0"))
	float PFLookReturnTau = 0.22f;

	/** Broadside mode: the gun lock swings the ship to keep the beam on an aim that left the arc. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|PointFly")
	bool bPFArcAssist = true;

	/** The arc counts as the cannon yaw limit minus this (deg). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|PointFly", meta = (ClampMin = "0.0"))
	float PFArcMarginDeg = 6.f;

	/** Broadside sector (deg off the bow): outside it the aim never swings the ship (review R1: 55). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|PointFly", meta = (ClampMin = "0.0"))
	float PFArcMinBearingDeg = 55.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|PointFly", meta = (ClampMin = "0.0"))
	float PFArcMaxBearingDeg = 150.f;

	/** An aim closing on the arc faster than this (deg/s, filtered with PFArcApproachTau s, review R2) is waited for. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|PointFly", meta = (ClampMin = "0.0"))
	float PFArcApproachRateDeg = 3.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|PointFly", meta = (ClampMin = "0.0"))
	float PFArcApproachTau = 0.1f;

	/** Outside the arc and not coming in this long (s) = lock; locked, the beam stays this close (deg) to the aim, swinging at most this fast (deg/s). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|PointFly", meta = (ClampMin = "0.0"))
	float PFArcLockDelay = 0.25f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|PointFly", meta = (ClampMin = "0.0"))
	float PFArcLockDeadbandDeg = 3.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|PointFly", meta = (ClampMin = "0.0"))
	float PFArcRateDeg = 45.f;

	/**
	 * Locked: the sent target leads by its own rate x this (s); the rate estimate's clamp (deg/s) and filter (s). 0.6 (was
	 * 0.45): with the spring arm's lag (PIE-calibrated) a pilot who keeps the crosshair on a target in a 100 m orbit has it
	 * on the beam (0.45: 3 deg aft); the 0.45 already cancelled the hull's own lag (aim 0.5 deg off the hull's beam).
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|PointFly", meta = (ClampMin = "0.0"))
	float PFLockLeadTime = 0.6f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|PointFly", meta = (ClampMin = "0.0"))
	float PFHeadingLeadRateMax = 30.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|PointFly", meta = (ClampMin = "0.0"))
	float PFHeadingLeadTau = 0.12f;

	/** Camera pitch away from CameraDefaultPitch climbs / sinks (tested, off): dead band and full-rate distance (deg). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|PointFly")
	bool bPFPitchClimb = false;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|PointFly", meta = (ClampMin = "0.0"))
	float PFPitchClimbDeadbandDeg = 10.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|PointFly", meta = (ClampMin = "1.0"))
	float PFPitchClimbFullDeg = 20.f;

	/**
	 * Parked free look: below this forward speed (cm/s) with no W/S, A/D, Q/E or boost held, the mouse looks around and the
	 * heading holds (as on foot); the first such key takes the camera's yaw as the heading. Once parked it holds at any speed
	 * (a hit that pushes the ship faster doesn't end it) until such a key, Aim, or an outside camera set above this speed.
	 * 0 = off (the camera always steers).
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|PointFly", meta = (ClampMin = "0.0"))
	float PFParkSpeed = 300.f;

	/** The gun lock is armed only while Fire is held or this long (s) after the pilot's own broadside, so Aim alone is a clean free look. 0 = always armed. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|PointFly", meta = (ClampMin = "0.0"))
	float PFLockArmTime = 6.f;


	// -------------------------------------------------------------------------
	// FX (every machine)
	// -------------------------------------------------------------------------

	/** Float user parameters set on the thruster / turbine Niagara components every frame ("User." is added by Niagara). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|FX")
	FName FXThrustParam = TEXT("Thrust");

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|FX")
	FName FXBoostParam = TEXT("Boost");


	// -------------------------------------------------------------------------
	// HUD (pilot's machine)
	// -------------------------------------------------------------------------

	/** Ship HUD while a local player flies the ship (hull, boost, speed, altitude, cannons). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|HUD")
	bool bShowShipHUD = true;

	/** Null: UAirshipHUDWidget (C++ only, no assets). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|HUD")
	TSubclassOf<UAirshipHUDWidget> ShipHUDClass;

	/** Gap (slate units) between the ship HUD and the bottom-left corner of the screen. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|HUD")
	FVector2D ShipHUDCornerOffset = FVector2D(24.0, 24.0);

	/** Hide the on-foot overlay (health / mana globes, ability icons) while flying. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|HUD")
	bool bHideOnFootHUD = true;

	/** Widget property of the player's HUD actor (AMyHUD::OverlayWidget) that holds the on-foot overlay. Read by reflection. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|HUD")
	FName OnFootHUDWidgetProperty = TEXT("OverlayWidget");

	/**
	 * Server: replicate the ship every server frame while its hull is awake (ForceNetUpdate in Tick). The engine
	 * otherwise schedules the next update 1/NetUpdateFrequency plus a random part of a server tick ahead
	 * (UNetDriver::ServerReplicateActors), which skips about every other frame at a 30-60 Hz server; a client's Default
	 * physics replication then chases a target that moves in uneven steps, and the ship judders on its screen
	 * (listen-server test 2026-11-22 at ~50 m/s: +-10 cm per frame, accel noise 10.5 cm/frame^2 against 2.0 on the
	 * server; every frame: 2.4). Costs one movement update per frame per client.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Network")
	bool bReplicateEveryFrame = true;


	// -------------------------------------------------------------------------
	// Replicated state
	// -------------------------------------------------------------------------

	/** The character at the helm (server sets it; every machine hides its collision). */
	UPROPERTY(ReplicatedUsing = OnRep_PilotCharacter, VisibleInstanceOnly, BlueprintReadOnly, Category = "Airship")
	TObjectPtr<ACharacter> PilotCharacter;

	/** Set on the server at death, for clients that get the actor after the death multicast. */
	UPROPERTY(ReplicatedUsing = OnRep_IsDead, VisibleInstanceOnly, BlueprintReadOnly, Category = "Airship")
	bool bIsDead = false;

	/** Server world time of the death (AGameStateBase::GetServerWorldTimeSeconds), for clients that join later. */
	UPROPERTY(Replicated)
	double DeathServerTime = 0.0;

	/** Team match: 0 or 1, 255 = a free ship (SetTeamId, server). */
	UPROPERTY(ReplicatedUsing = OnRep_TeamId, VisibleInstanceOnly, BlueprintReadOnly, Category = "Airship|Match")
	uint8 TeamId = MyMatch::NoTeam;

	/** Spawn protection's end (server world time, AGameStateBase::GetServerWorldTimeSeconds), 0 = none. HUD shield. */
	UPROPERTY(Replicated)
	double ProtectionEndServerTime = 0.0;

	UFUNCTION()
	void OnRep_TeamId();

	/** Who mans each gunner station (EAirshipStation order; Airship::NumStations entries, set in the constructor). */
	UPROPERTY(ReplicatedUsing = OnRep_StationGunners, VisibleInstanceOnly, BlueprintReadOnly, Category = "Airship|Stations")
	TArray<TObjectPtr<ACharacter>> StationGunners;

	/** Each manned station's aim point (world, cm) from its gunner (ServerSetGunnerAim): the other machines aim the guns with it. */
	UPROPERTY(Replicated)
	TArray<FVector_NetQuantize> StationAims;

	/** The two turrets (the server spawns them at BeginPlay; Airship::NumTurrets entries). */
	UPROPERTY(Replicated, VisibleInstanceOnly, BlueprintReadOnly, Category = "Airship|Turrets")
	TArray<TObjectPtr<AAirshipTurret>> Turrets;

	UFUNCTION()
	void OnRep_PilotCharacter();

	/** Clients: a gunner keeps its actor collision on this machine (other machines' traces must hit it), the change event. */
	UFUNCTION()
	void OnRep_StationGunners();

	/**
	 * Every machine (bound by NotifyStationsChanged to each gunner's OnDeathDelegate, which AMyCharBase's death
	 * multicast broadcasts right after it starts the ragdoll): a gunner who dies at the station keeps its body off the
	 * hull (KeepCorpseOffHull), before the ragdoll's first physics step.
	 */
	UFUNCTION()
	void OnStationGunnerDied(AActor* DeadActor);

	UFUNCTION()
	void OnRep_IsDead();

	/** Clients: applies the scheme the server chose (the first bunch arrives before BeginPlay, which applies it then). */
	UFUNCTION()
	void OnRep_ControlScheme();

	UFUNCTION(NetMulticast, Reliable)
	void MulticastHandleDeath();

	/**
	 * Recoil, muzzle FX, hull kick on every machine for the cannons in CannonMask (bit c = cannon c). The machine that
	 * predicted a cannon's shot (the pilot's client, a gunner's client) already played it and skips that cannon.
	 */
	UFUNCTION(NetMulticast, Unreliable)
	void MulticastCannonsFired(uint8 CannonMask);

	UFUNCTION(Server, Reliable)
	void ServerFireCannons(EAirshipSide Side, FVector_NetQuantize AimPoint);

	UFUNCTION(Server, Reliable)
	void ServerRequestExit();

	FOnDeathDelegateSignature OnDeathDelegate;

private:

	// Input
	void ResolveInputAssets();
	void UpdateLocalMappingContext();
	void RemoveLocalMappingContext();
	void GatherLocalInput(float DeltaSeconds);
	void OnLookInput(const FInputActionValue& Value);
	void OnZoomInput(const FInputActionValue& Value);
	void OnFireInput(const FInputActionValue& Value);
	void OnExitInput(const FInputActionValue& Value);

	/** The pilot's machine: camera aim trace. */
	bool ComputeLocalAimPoint(FVector& OutAimPoint) const;

	// Every machine
	void UpdateCannonAim();
	void UpdateFX();
	void UpdateCamera(float DeltaSeconds);
	void UpdateRepMode();
	void UpdatePassengerCollision();
	void RefreshCannonGeometry();

	/** Asks the subsystem to re-check the deck passengers now (board, exit, collision restored). */
	void RefreshPassengers() const;

	// Hull impacts
	/** Every machine, before the physics step: the hull's velocities, for the impact cap and the impact speed. */
	void RecordPreStepState();

	/** Every machine: caps the rebound, speed gain and spin kick of this frame's hits (kick budgets of the contact). */
	void LimitImpactResponse();

	/**
	 * The impact speed (cm/s) of a hull hit as the damage measures it (closing speed along the normal before the step);
	 * -1 if the hit doesn't count (the ship's own pilot / balls, characters, pawns, resting contact).
	 */
	float MeasureHullImpactSpeed(const AActor* OtherActor, const UPrimitiveComponent* OtherComp, const FVector& NormalImpulse, const FHitResult& Hit) const;

	// Control schemes (every machine)
	/** The preset of ControlScheme, the flight model's copy, the runtime state reset, the HUD layout. bSwitch: a runtime switch. */
	void ApplyControlScheme(bool bSwitch);

	/** Every scheme-owned tunable from the archetype (Classic = the class defaults), then Scheme's overrides. */
	void ApplySchemePreset(EAirshipControlScheme Scheme);
	void ApplyGalleonPreset();
	void ApplySkyRacerPreset();
	void ApplyPointFlyPreset();

	/** The pawn's scheme-local pilot state: Galleon telegraph and camera (bFromSwitch: the notch from the speed, else STOP), Point & Fly heading target, feedback. */
	void ResetSchemePilotState(bool bFromSwitch);

	// Galleon (pilot's machine)
	/** Beam watch and broadside stations (from this frame's camera, so the bit leaves this frame), then the telegraph. */
	void UpdateGalleonOrders(float ThrottleAxis, bool bAimHeld, const APlayerController* PC, double Now);
	void StepGalleonOrder(int32 Dir, bool bRepeat);

	/** The ship-relative camera: offset, look-ahead, slow recentre outside beam watch. Consumes bPendingCameraReset. */
	void UpdateGalleonCamera(float DeltaSeconds, double Now, const FAirshipCosmeticState& C, FRotator& Control);

	// Sky Racer (pilot's machine)
	/** The chase camera's auto-follow step (look into the turn, slip share, yaw rate feed-forward, dive pitch). */
	void UpdateSkyRacerFollow(float DeltaSeconds, double Alpha, FRotator& Control) const;

	// Point & Fly (pilot's machine)
	/**
	 * Camera -> heading target (free look, Q/E nudge, gun lock, lead clamp, parked free look); writes the control rotation.
	 * bMoveKeys: W/S, A/D, Q/E or boost held (ends the parked free look); bFireHeld: Fire held, arms the gun lock (so does
	 * PFLockArmTime after an own broadside). bLaneAssistLook (round 2 PR B): the lane flies the ship, so the camera parks
	 * at any speed (a team ship's helm also starts parked: the lane may be flying it).
	 */
	void UpdatePointFlyCamera(float Dt, APlayerController* PC, float NudgeAxis, bool bAimHeld, bool bMoveKeys, bool bFireHeld, bool bLaneAssistLook);

	/** Broadside mode: the heading target the gun lock wants (H while it doesn't act). */
	float PointFlyGunLock(float H, float CamYaw, float Dt);

	// Feedback (pilot's machine)
	void AddFeedback(const FAirshipFeedbackEvent& Event, float FOVSign = 1.f);
	void PlayRumble(float Intensity, float Duration, bool bLarge);

	/** End of UpdateCamera: events, trauma shake, camera roll, the drift rumble. */
	void UpdateFeedback(float DeltaSeconds, const FAirshipCosmeticState& C);
	void StopDriftRumble();

	// HUD (pilot's machine)
	void UpdateShipHUD();

	/** True once the widget is on screen (only then the on-foot overlay is hidden and the HUD counts as shown). */
	bool ShowShipHUD(APlayerController* PC);
	void HideShipHUD();
	void HideOnFootHUD(APlayerController* PC);
	void RestoreOnFootHUD();

	/** After a scheme switch: the panel's slot at its new size, the Point & Fly overlay added or removed (no hide / re-show). */
	void RefreshShipHUDLayout();
	bool AddShipOverlay(APlayerController* PC);
	void RemoveShipOverlay();

	/** The side whose cannons face AimPoint (with hysteresis around the keel). */
	EAirshipSide ComputeAimSide(const FVector& AimPoint) const;

	/**
	 * Recoil counters, muzzle FX (cut after UAirshipSettings::MuzzleFXMaxSeconds), hull kick of the cannons in CannonMask.
	 * Every machine. bLocalShot: this machine's own shot (the host's, or a prediction): the pilot's broadside feedback.
	 */
	void HandleCannonsFired(uint8 CannonMask, bool bLocalShot);

	/** Server: the ship's damage spec for its cannonballs (CannonballDamage), credited to DamageInstigator (the ship, a gunner). */
	FGameplayEffectSpecHandle MakeCannonballSpec(AActor* DamageInstigator) const;

	/** Server: one ball from Cannon toward AimPoint (its limits, spread, the muzzle's velocity). Null if it couldn't spawn. */
	AAirshipCannonball* SpawnCannonball(int32 Cannon, const FVector& AimPoint, const FGameplayEffectSpecHandle& Spec);

	/** Server: Cannon's reload is done (CannonCooldown, minus 0.1 s for the client's clock). */
	bool IsCannonLoadedServer(int32 Cannon, double Now) const;

	/** Every machine, once: from the multicast, OnRep_IsDead or BeginPlay. bLateJoin (a client that got the ship dead): no explosion, DeathTime from the server's death time. */
	void HandleDeath(bool bLateJoin);

	/**
	 * Server, the tick after Die: the last loss reaches the crew (FlushCrewDamage), then the pilot and every gunner get
	 * their character back (thrown clear) before anything else happens to it.
	 */
	void EjectCrewAfterDeath();

	// Crew damage (UAirshipSettings::CrewDamageShare)
	/** Server: the ship's Health went down: the crew's share is queued for the next tick (this runs inside the damage effect). */
	void OnShipHealthChanged(const FOnAttributeChangeData& Data);

	/**
	 * Server: the queued share to the pilot and every gunner, through the ship's damage effect on their own ASC. A share
	 * that would kill puts them on foot first (eject / dismount), so the normal on-foot death runs.
	 */
	void FlushCrewDamage();

	// Team match (server)
	/** Adds or removes AirshipTags::State_SpawnProtected on the ship's and its turrets' ASCs. */
	void ApplySpawnProtectionTag(bool bProtected);

	/** The protection's time ran out. */
	void OnSpawnProtectionTimer();

	/** The tag state RefreshSentinelBulletTags last applied (Tick re-checks it: board, exit, possession, a settings change). */
	bool bSentinelTagsOn = true;
	FTimerHandle SpawnProtectionTimer;

	/** NotifyIncomingReel: each reeler and the server time its entry expires. */
	TMap<TWeakObjectPtr<const AActor>, double> IncomingReels;

	float PendingCrewDamage = 0.f;
	float PendingCrewLoss = 0.f;
	bool bCrewDamageFlushQueued = false;
	/** DebugKill: the console's kill gives the crew nothing. */
	bool bSuppressCrewDamage = false;

	// Gunner stations and turrets
	/** Server, at the end of BeginPlay: the turrets at UAirshipSettings::TurretMounts, attached to the hull without welding. */
	void SpawnTurrets();

	/** Server, every tick: frees the stations whose gunner died, left, was unpossessed or detached, or whose turret was wrecked. */
	void UpdateStations();

	/** Server, every tick (after UpdateStations): each turret's command (its gunner, the console, the pilot, or rest). */
	void UpdateTurretCommands();

	/** The pilot's client, every frame: the unmanned turrets' local command (their aim and predicted rounds there). */
	void UpdateLocalTurretCommands(bool bFireHeld);

	/** Every machine: the change events of the stations that changed since the last call; binds OnStationGunnerDied. */
	void NotifyStationsChanged();

	/**
	 * Every machine: a character that died at a gun station. The seats are at plank height, inside the hull's convex
	 * hulls (under the walkable lid, or in the forward deck's convex), so its ragdoll would start deep inside the
	 * simulated hull and be pushed out, throwing the body and kicking the ship. Its simulating bodies ignore the hull's
	 * object type from then on: the body drops through the deck (the GameMode's respawn removes it).
	 */
	void KeepCorpseOffHull(ACharacter* Corpse) const;

	/** Clamped station index (0 for an invalid one: callers check IsValidStation first). */
	static int32 StationSlot(int32 Station) { return FMath::Clamp(Station, 0, Airship::NumStations - 1); }
	static bool IsValidStation(int32 Station) { return Station >= 0 && Station < Airship::NumStations; }

	/** Hull-local rest direction of a station's gun (cannon: barrel; turret: the bow). */
	FVector GetStationRestDirLocal(int32 Station) const;

	UFUNCTION()
	void OnHullHit(UPrimitiveComponent* HitComponent, AActor* OtherActor, UPrimitiveComponent* OtherComp, FVector NormalImpulse, const FHitResult& Hit);

	/** Hull-relative transform of the pilot's root at the seat. */
	FTransform GetPilotSeatRelativeTransform(const ACharacter* Pilot) const;

	FVector GetPilotSeatLocal() const;

	/** Weak: the pilot's controller, to give the character back to. */
	TWeakObjectPtr<APlayerController> PilotController;

	bool bPilotWasAlwaysRelevant = false;
	bool bPilotHadCollision = true;
	bool bUnboarding = false;
	double LastExitRequestTime = -1000.0;

	/** Hull-space seat (cm), from the PilotSeat bone or PilotSeatFallback. */
	FVector PilotSeatLocal = FVector::ZeroVector;

	/** Hull-space wheel hub (cm), from HelmWheelBone or HelmWheelFallback. */
	FVector HelmWheelLocal = FVector::ZeroVector;

	/** The Mesh's physics asset is the deck (UpdateDeckCollision, BeginPlay). */
	bool bDeckIsMesh = false;

	/**
	 * Hull-space height (cm) of the surface a character stands on at the helm (IsWithinHelmReach measures the feet
	 * against it): the seat's own height on the physics asset's deck, the hull collision's top over the seat without one.
	 */
	double HelmStandLocalZ = 0.0;

	/** UpdateDeckCollision, RefreshCannonGeometry: HelmStandLocalZ for the deck in use. */
	void UpdateHelmStandHeight();

	/** BeginPlay: the deck and the Visibility target (bDeckOnPhysicsAsset): HullCollision's and Mesh's Pawn / Visibility responses. */
	void UpdateDeckCollision();

	/**
	 * Down the hull's up axis from Point (world), the first deck surface (GetDeckComponent) between Above and Below cm of
	 * it; a trace that starts inside a body is skipped and the next one starts higher (+300 cm, twice).
	 */
	bool TraceDeckBelow(const FVector& Point, double Above, double Below, FVector& OutDeck) const;

	/**
	 * Moves Character's capsule placed at InOutCentre (world) the least that clears it of the ship's deck bodies (the
	 * Mesh's physics asset: the wheel, the pedestal, rails): up to 4 steps of their minimum translation, at most MaxPush cm
	 * in all. Returns the distance moved (0: it was clear, or the deck is the hull's collision).
	 */
	double ClearDeckBodies(const ACharacter* Character, FVector& InOutCentre, double MaxPush = 100.0) const;

	/** The pilot last seen by OnRep_PilotCharacter (every machine), for the change event and the collision restore. */
	TWeakObjectPtr<ACharacter> KnownPilot;

	/** Clients: characters whose collision this ship turned off, restored once they are no longer attached. */
	TArray<TWeakObjectPtr<ACharacter>> PassengersWithCollisionOff;

	/** Where the IMC was added (to remove it from the same player). */
	TWeakObjectPtr<UEnhancedInputLocalPlayerSubsystem> MappingSubsystem;
	TWeakObjectPtr<const UInputMappingContext> AddedMappingContext;
	bool bInputAssetsResolved = false;

	// Local controls
	bool bPendingCameraReset = false;
	double LastLookInputTime = -1000.0;
	/** GFrameCounter of the last look input (Point & Fly: a control rotation change without one was set from outside). */
	uint64 LastLookInputFrame = 0;
	float ZoomTarget = 0.f;
	bool bLocalAimValid = false;
	FVector LocalAimPoint = FVector::ZeroVector;

	// Galleon (pilot's machine)
	int32 GalleonNotch = 0;
	bool bGalleonUpHeld = false;
	bool bGalleonDownHeld = false;
	int32 GalleonRepeatDir = 0;
	double GalleonNextRepeatTime = 0.0;
	float GalleonCamOffsetYaw = 0.f;
	float GalleonLookAhead = 0.f;
	float GalleonLastHullYaw = 0.f;
	float GalleonLastLookAhead = 0.f;
	bool bGalleonBeamWatch = false;
	bool bGalleonStations = false;
	bool bGalleonCamInit = false;

	// Point & Fly (pilot's machine): heading target H, camera offset from it, last control yaw this code set, lock
	bool bPFValid = false;
	bool bPFFree = false;
	bool bPFLock = false;
	/** Parked free look this frame (the first drive / turn key then takes the camera's yaw as the heading). Last frame's value keeps it above PFParkSpeed. */
	bool bPFParked = false;
	float PFHeading = 0.f;
	float PFLookOffset = 0.f;
	float PFLastSetYaw = 0.f;
	float PFSentHeading = 0.f;
	float PFLockDwell = 0.f;
	/** -1 = no previous sample. */
	float PFPrevOffBeam = -1.f;
	float PFOffBeamRate = 0.f;
	float PFHeadingRate = 0.f;
	float PFPrevHeading = 0.f;
	int32 PFLockSwingDir = 0;
	FPointFlyLoopState PilotHeadingLoop;

	// Feedback (pilot's machine)
	float CameraTrauma = 0.f;
	float CameraFOVKick = 0.f;
	float CameraRollDeg = 0.f;
	/** The FOV before the kick (interpolated toward the target) and the FOV last written (someone else's write is followed). */
	float SmoothedFOV = 0.f;
	float LastAppliedFOV = 0.f;
	bool bCameraFeedbackApplied = false;
	uint8 LastTurboEventCount = 0;
	bool bPrevBoostBit = false;
	bool bPrevLocalDrift = false;
	float LocalDriftTime = 0.f;
	uint64 LastFeedbackHitFrame = 0;
	double LastOwnBroadsideTime = -1000.0;
	/** FDynamicForceFeedbackHandle (PlayerController.h) of the continuous drift rumble, and the controller playing it. */
	uint64 DriftRumbleHandle = 0;
	TWeakObjectPtr<APlayerController> DriftRumblePC;

	// Cannons
	FVector CannonMuzzleLocal[Airship::NumCannons];
	FVector CannonRestDirLocal[Airship::NumCannons];
	float CannonAimYawDeg[Airship::NumCannons] = {};
	float CannonAimElevDeg[Airship::NumCannons] = {};
	int32 CannonFireCount[Airship::NumCannons] = {};
	/** Server: each cannon's last shot (its own reload). */
	double LastCannonFireTime[Airship::NumCannons] = { -1000.0, -1000.0, -1000.0, -1000.0 };
	/**
	 * Clients: each cannon's last shot on this machine's clock (its predicted shots and the multicast shots it played),
	 * and whether a predicted shot waits for the multicast to skip (only on the machine that predicted it).
	 */
	double LastPredictedCannonFireTime[Airship::NumCannons] = { -1000.0, -1000.0, -1000.0, -1000.0 };
	bool bPredictedShotPending[Airship::NumCannons] = { false, false, false, false };
	EAirshipSide AimSide = EAirshipSide::Port;

	// Gunner stations
	/** Hull-space seats (cm): cannons from the carriage bones (RefreshCannonGeometry), turrets from the settings' mounts. */
	FVector StationSeatLocal[Airship::NumStations];
	/**
	 * Server: each station's controller, trigger (turrets), and the gunner's bAlwaysRelevant and movement
	 * bIgnoreClientMovementErrorChecksAndCorrection before it mounted.
	 */
	TWeakObjectPtr<APlayerController> StationControllers[Airship::NumStations];
	bool StationTrigger[Airship::NumStations] = {};
	bool bStationGunnerWasAlwaysRelevant[Airship::NumStations] = {};
	bool bStationGunnerIgnoredCorrections[Airship::NumStations] = {};
	/** This machine's own gunner's aim (SetLocalStationAim) and the frame it was set (used for this and the next frame). */
	FVector LocalStationAim[Airship::NumStations];
	uint64 LocalStationAimFrame[Airship::NumStations] = {};
	/** Test hook (SetStationConsoleAim): an aim that wins over the gunner's until this world time. */
	FVector StationConsoleAim[Airship::NumStations];
	double StationConsoleAimUntil[Airship::NumStations] = { -1.0, -1.0, -1.0, -1.0, -1.0, -1.0 };
	/** The gunners last seen by NotifyStationsChanged (every machine), for the change events. */
	TWeakObjectPtr<ACharacter> KnownStationGunners[Airship::NumStations];
	/** Server: Aura.Airship.TurretFire (unmanned turrets fire at the point, or ahead of the bow). */
	bool bDebugTurretFire = false;
	bool bDebugTurretFireHasPoint = false;
	FVector DebugTurretFirePoint = FVector::ZeroVector;
	bool bWarnedTurretClass = false;

	// Death / impacts
	bool bDeathHandled = false;
	double DeathWorldTime = 0.0;
	double LastImpactTime = -1000.0;

	/** Hull state before this frame's physics step (GFrameCounter of the record). */
	FVector PreStepLinearVelocity = FVector::ZeroVector;
	FVector PreStepAngularVelocity = FVector::ZeroVector;
	FVector PreStepCenterOfMass = FVector::ZeroVector;
	uint64 PreStepFrame = 0;

	/** Boost / drift kicks the flight model put into this frame's step (NoteFlightKick; reset with the record). */
	FVector PreStepFlightKick = FVector::ZeroVector;

	/**
	 * Impact cap: the frame it last ran, the last hit of the contact, and the used part (0..1) of each kick budget:
	 * upward speed, horizontal speed, speed, spin.
	 */
	uint64 ImpactLimitFrame = 0;
	double ImpactEpisodeLast = -1000.0;
	double ImpactUsedUp = 0.0;
	double ImpactUsedHorizontal = 0.0;
	double ImpactUsedSpeed = 0.0;
	double ImpactUsedSpin = 0.0;

	/** Impact damage: the frame of the last damaging hit and what it dealt (the hardest contact of a frame counts). */
	uint64 ImpactDamageFrame = 0;
	float ImpactDamageThisFrame = 0.f;

	// HUD (pilot's machine)
	UPROPERTY(Transient)
	TObjectPtr<UAirshipHUDWidget> ShipHUDWidget;

	/** Point & Fly: a second UAirshipHUDWidget in overlay mode over the whole viewport (crosshair, nose marker, gun state). */
	UPROPERTY(Transient)
	TObjectPtr<UAirshipHUDWidget> ShipOverlayWidget;

	TWeakObjectPtr<APlayerController> ShipHUDOwner;
	TWeakObjectPtr<UUserWidget> HiddenOnFootWidget;
	ESlateVisibility HiddenOnFootVisibility = ESlateVisibility::SelfHitTestInvisible;
	double LastOnFootHUDSearchTime = -1000.0;

	/** After a failed ShowShipHUD (no game viewport, no widget): the next try, not every frame. */
	double NextShipHUDAttemptTime = -1000.0;
	bool bShipHUDActive = false;
};
