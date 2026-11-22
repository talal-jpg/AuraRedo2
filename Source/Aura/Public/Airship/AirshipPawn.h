// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "AbilitySystemInterface.h"
#include "GameFramework/Pawn.h"
#include "Interfaces/MyCombatInterface.h"
#include "Airship/AirshipTypes.h"
#include "Components/SlateWrapperTypes.h"
#include "AirshipPawn.generated.h"

class AAirshipCannonball;
class AAirshipPawn;
class ACharacter;
class APlayerController;
class UAirshipFlightComponent;
class UAirshipHUDWidget;
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
class USkeletalMeshComponent;
class USpringArmComponent;
class UStaticMeshComponent;
class UUserWidget;
struct FInputActionValue;

DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnAirshipPilotChangedSignature, AAirshipPawn*, Airship, ACharacter*, NewPilot);

/**
 * The drivable airship (Docs/Airship/CPP_NOTES.md). A player walks up to it and presses F (UAirshipPilotComponent):
 * the server attaches their character at the helm (PilotSeat), possesses the ship, and F again gives the character
 * back next to the helm.
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

	/** Server: true if Candidate (a living player character with a PlayerState) may take the helm now. Distance not checked. */
	bool CanBoard(const APawn* Candidate) const;

	/** Distance (cm) from Location to the ship for boarding: the smaller of pilot seat and hull distances, each against its own limit. */
	bool IsWithinBoardRange(const FVector& Location, float SeatDistance, float HullDistance) const;

	/** Server: puts Pilot at the helm and gives PC the ship. False if not allowed (CanBoard). */
	bool BoardPilot(ACharacter* Pilot, APlayerController* PC);

	/** Server: gives the pilot back their character next to the helm. bEject: thrown clear (death). */
	void UnboardPilot(bool bEject);

	UFUNCTION(BlueprintPure, Category = "Airship")
	ACharacter* GetPilot() const { return PilotCharacter; }

	UFUNCTION(BlueprintPure, Category = "Airship")
	bool HasPilot() const { return PilotCharacter != nullptr; }

	/** World location of the pilot seat (where the pilot stands). */
	UFUNCTION(BlueprintPure, Category = "Airship")
	FVector GetPilotSeatLocation() const;


	// -------------------------------------------------------------------------
	// Deck passengers (every machine)
	// -------------------------------------------------------------------------

	/**
	 * True if Character rides this ship now: attached to it (the pilot), standing on it (movement base owned by the ship
	 * or by an actor attached to it), or without a base (jumping, falling, flying) inside the hull's bounds grown by
	 * PassengerZoneMargin. UAirshipSubsystem gives such characters query-only collision, while their actor collision is
	 * on (the attached pilot's capsule is switched right after Exit). A dead ship keeps its riders
	 * until they leave it or the wreck goes (EndPlay): the wreck is still a simulated body, and a kinematic capsule given
	 * back its physics mid-tumble (the ejected pilot, a rider on deck) would shove it like an immovable post.
	 */
	bool IsPassengerCandidate(const ACharacter* Character) const;

	/** Characters riding this ship on this machine (their physics collision is off while aboard). */
	UFUNCTION(BlueprintPure, Category = "Airship")
	TArray<ACharacter*> GetPassengers() const;


	// -------------------------------------------------------------------------
	// Cannons
	// -------------------------------------------------------------------------

	/** The pilot's machine: fires the broadside on the camera's side at the camera's aim point. */
	UFUNCTION(BlueprintCallable, Category = "Airship|Cannons")
	void RequestFire();

	/** Server: fires the two cannons of Side at AimPoint (world) if that side is loaded. */
	void FireCannons(EAirshipSide Side, const FVector& AimPoint);

	/** Hull-local muzzle position and rest firing direction (outboard) of a cannon. */
	FVector GetCannonMuzzleLocal(int32 Cannon) const;
	FVector GetCannonRestDirLocal(int32 Cannon) const;

	/** Yaw / elevation (deg, clamped to the cannon's limits) that point Cannon at the world point Target. */
	void ComputeCannonAim(int32 Cannon, const FVector& Target, float& OutYawDeg, float& OutElevDeg) const;

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

	/** 0 = just fired .. 1 = loaded, for one side on this machine (the pilot's client: its own reload clock). */
	UFUNCTION(BlueprintPure, Category = "Airship|Cannons")
	float GetCannonReloadAlpha(EAirshipSide Side) const;

	/** Reload time of one side (s). */
	float GetCannonCooldown() const { return CannonCooldown; }


	// -------------------------------------------------------------------------
	// Damage
	// -------------------------------------------------------------------------

	/** Server: Damage through the project's damage path (DamageEffectClass, SetByCaller SetDamageByCaller on the ship's ASC). */
	UFUNCTION(BlueprintCallable, BlueprintAuthorityOnly, Category = "Airship|Damage")
	void ApplyShipDamage(float Damage);

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

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Impact", meta = (ClampMin = "0.0", EditCondition = "bLimitImpactResponse"))
	float ImpactEpisodeSpinAccelDeg = 90.f;

	/** The hull mesh shows in game when the Mesh has no skeletal mesh (C++-only tests). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Debug")
	bool bShowHullWithoutMesh = true;

	/** Optional physical material for the hull (friction 0.2, restitution 0.35 suggested). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Impact")
	TObjectPtr<UPhysicalMaterial> HullPhysicalMaterial;


	// -------------------------------------------------------------------------
	// Pilot
	// -------------------------------------------------------------------------

	/** Bone or socket of the mesh where the pilot stands (rest pose). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Pilot")
	FName PilotSeatSocket = TEXT("PilotSeat");

	/** Hull-space pilot seat (cm) when the mesh has no PilotSeat bone. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Pilot")
	FVector PilotSeatFallback = FVector(-843.0, 0.0, 262.0);

	/** Extra height (cm) above the seat for the pilot's capsule bottom, so it never touches the hull. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Pilot", meta = (ClampMin = "0.0"))
	float PilotSeatClearance = 5.f;

	/** Hull-space offset (cm) from the seat where the pilot steps off (then dropped onto the deck by a trace). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Pilot")
	FVector ExitOffset = FVector(0.0, -250.0, 0.0);

	/**
	 * Off: characters on the deck keep their physics collision (their kinematic capsules push the simulated hull: the
	 * ship sinks under a standing character).
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Pilot")
	bool bPassengersQueryOnly = true;

	/** Characters without a movement base (jumping, falling) inside the hull's bounds grown by this (cm) count as passengers. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Pilot", meta = (ClampMin = "0.0"))
	float PassengerZoneMargin = 300.f;

	/** Ship death: the pilot is thrown up and out to the side (cm/s), on top of the ship's velocity. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Pilot", meta = (ClampMin = "0.0"))
	float EjectUpSpeed = 1200.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Pilot", meta = (ClampMin = "0.0"))
	float EjectSideSpeed = 600.f;


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

	/** Null: AAirshipCannonball. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Cannons")
	TSubclassOf<AAirshipCannonball> CannonballClass;

	/** Muzzle speed (cm/s), the ship's own velocity is added. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Cannons", meta = (ClampMin = "0.0"))
	float CannonballSpeed = 12000.f;

	/** Damage per ball (SetByCaller). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Cannons", meta = (ClampMin = "0.0"))
	float CannonballDamage = 60.f;

	/** Reload time of one side (s). */
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

	/** Balls start this far (cm) in front of the muzzle. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Cannons", meta = (ClampMin = "0.0"))
	float CannonSpawnForwardOffset = 60.f;

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

	UFUNCTION()
	void OnRep_PilotCharacter();

	UFUNCTION()
	void OnRep_IsDead();

	UFUNCTION(NetMulticast, Reliable)
	void MulticastHandleDeath();

	/** Recoil, muzzle FX, hull kick on every machine (the pilot's client already played its own shot and skips the one it predicted). */
	UFUNCTION(NetMulticast, Unreliable)
	void MulticastCannonsFired(EAirshipSide Side);

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

	// HUD (pilot's machine)
	void UpdateShipHUD();

	/** True once the widget is on screen (only then the on-foot overlay is hidden and the HUD counts as shown). */
	bool ShowShipHUD(APlayerController* PC);
	void HideShipHUD();
	void HideOnFootHUD(APlayerController* PC);
	void RestoreOnFootHUD();

	/** The side whose cannons face AimPoint (with hysteresis around the keel). */
	EAirshipSide ComputeAimSide(const FVector& AimPoint) const;

	/** Recoil counters, muzzle FX, hull kick. Every machine. */
	void HandleCannonsFired(EAirshipSide Side);

	/** Every machine, once: from the multicast, OnRep_IsDead or BeginPlay. bLateJoin (a client that got the ship dead): no explosion, DeathTime from the server's death time. */
	void HandleDeath(bool bLateJoin);

	/** Server, the tick after Die: the pilot gets their character back before anything else happens to it. */
	void EjectPilotAfterDeath();

	UFUNCTION()
	void OnHullHit(UPrimitiveComponent* HitComponent, AActor* OtherActor, UPrimitiveComponent* OtherComp, FVector NormalImpulse, const FHitResult& Hit);

	/** Hull-relative transform of the pilot's root at the seat. */
	FTransform GetPilotSeatRelativeTransform(const ACharacter* Pilot) const;

	FVector GetPilotSeatLocal() const;

	/** Server: ends the pilot's active abilities (beam, boost, ...) while they are still its avatar. */
	static void CancelPilotAbilities(ACharacter* Pilot);

	/** Weak: the pilot's controller, to give the character back to. */
	TWeakObjectPtr<APlayerController> PilotController;

	/** The pilot's Health / Mana when boarding (re-possessing refills them). */
	float SavedPilotHealth = 0.f;
	float SavedPilotMana = 0.f;
	bool bHasSavedPilotVitals = false;
	bool bPilotWasAlwaysRelevant = false;
	bool bPilotHadCollision = true;
	bool bUnboarding = false;
	double LastExitRequestTime = -1000.0;

	/** Hull-space seat (cm), from the PilotSeat bone or PilotSeatFallback. */
	FVector PilotSeatLocal = FVector::ZeroVector;

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
	float ZoomTarget = 0.f;
	bool bLocalAimValid = false;
	FVector LocalAimPoint = FVector::ZeroVector;

	// Cannons
	FVector CannonMuzzleLocal[Airship::NumCannons];
	FVector CannonRestDirLocal[Airship::NumCannons];
	float CannonAimYawDeg[Airship::NumCannons] = {};
	float CannonAimElevDeg[Airship::NumCannons] = {};
	int32 CannonFireCount[Airship::NumCannons] = {};
	double LastSideFireTime[2] = { -1000.0, -1000.0 };
	double LastPredictedFireTime[2] = { -1000.0, -1000.0 };
	bool bPredictedShotPending[2] = { false, false };
	EAirshipSide AimSide = EAirshipSide::Port;

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

	TWeakObjectPtr<APlayerController> ShipHUDOwner;
	TWeakObjectPtr<UUserWidget> HiddenOnFootWidget;
	ESlateVisibility HiddenOnFootVisibility = ESlateVisibility::SelfHitTestInvisible;
	double LastOnFootHUDSearchTime = -1000.0;

	/** After a failed ShowShipHUD (no game viewport, no widget): the next try, not every frame. */
	double NextShipHUDAttemptTime = -1000.0;
	bool bShipHUDActive = false;
};
