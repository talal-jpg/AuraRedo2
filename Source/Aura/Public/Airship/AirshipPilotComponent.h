// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "Airship/AirshipTypes.h"
#include "Engine/NetSerialization.h"
#include "AirshipPilotComponent.generated.h"

class AAirshipPawn;
class ACharacter;
class APlayerController;
class UAirshipHUDWidget;
class UEnhancedInputComponent;
class UEnhancedInputLocalPlayerSubsystem;
class UInputAction;
class UInputMappingContext;
struct FInputActionValue;

/**
 * Lets a player board an airship or man one of its guns. UAirshipSubsystem adds one to every PlayerController on the
 * server (replicated, so the owning client has it too), no edit to the project's controller.
 *
 * Owning client: pushes its own input component and adds IMC_AirshipBoard (IA_AirshipBoard on F); a press sends
 * ServerRequestBoard. Server: the nearest of the helms of free living ships whose wheel the player's character stands at
 * (AAirshipPawn::IsWithinHelmReach: UAirshipSettings HelmReach / HelmReachHeight; AAirshipPawn::BoardPilot) and the free
 * gunner stations in range (StationMountDistance; AAirshipPawn::MountGunner) wins; F anywhere else does nothing. Exit
 * goes through ServerRequestExit (the ship's own Exit key uses its RPC, same result): the character stays at the wheel.
 *
 * Gunner stations (Docs/Airship/round2/SPEC_A.md D5): the gunner stays possessed in its own character. The server tells
 * the owning machine (ClientMountChanged); it then pushes a gunner input component and IMC_Airship (Look, Fire, Aim,
 * Zoom, Exit; every other key of that context consumed), shows the gunner HUD, sends its camera's aim point
 * (ServerSetGunnerAim, about 25 Hz and on change), a cannon press (ServerGunnerFire, predicted at once) and the machine
 * gun's trigger (ServerGunnerTrigger). F (IA_AirshipExit) leaves the station.
 *
 * Team match (round 2 PR B, SPEC_B B6.3): the other team's ship is never offered or used (UMyTeamLibrary::CanUseShip,
 * which every machine can answer from the replicated team ids); an F that finds only an enemy helm or gun in range is
 * refused with ClientUseRefused, which the match HUD turns into a toast (OnLocalUseRefused).
 */
UCLASS(ClassGroup = (Airship), meta = (BlueprintSpawnableComponent))
class AURA_API UAirshipPilotComponent : public UActorComponent
{
	GENERATED_BODY()

public:

	UAirshipPilotComponent();

	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

	/** Local player: take the helm of the ship whose wheel the character stands at, or man the nearest free gun station (sends the request). */
	UFUNCTION(BlueprintCallable, Category = "Airship")
	void RequestBoard();

	/** Local player: leave the helm (sends the request). */
	UFUNCTION(BlueprintCallable, Category = "Airship")
	void RequestExit();

	/** Local player: leave the gunner station (sends the request). */
	UFUNCTION(BlueprintCallable, Category = "Airship")
	void RequestDismount();

	/** Any machine: the free living ship whose helm the player's character could take now, standing at its wheel (for a "Press F" prompt; never the other team's). Null if none. */
	UFUNCTION(BlueprintPure, Category = "Airship")
	AAirshipPawn* FindBoardableAirship() const;

	/** Server: boards Ship (null: the one whose wheel the character stands at, one the player may use). bIgnoreRange for console commands: the nearest free living ship, from any distance. */
	bool TryBoard(AAirshipPawn* Ship, bool bIgnoreRange);

	/** Server: leaves the ship the player flies, if any. */
	bool TryExit();

	/** Server (F on foot): the helm when standing at its wheel, or the nearest free gunner station in range; a mounted gunner leaves its station. */
	bool TryUseNearest();

	/**
	 * Server: mans Station of Ship (null: the nearest living ship where that station is free, in range unless
	 * bIgnoreRange, which the console uses).
	 */
	bool TryMount(AAirshipPawn* Ship, int32 Station, bool bIgnoreRange);

	/** Server: leaves the station the player's character mans, if any. */
	bool TryDismount();

	APlayerController* GetPlayerController() const;

	/** This machine: the ship and station its own player mans (null / -1 when on foot or flying). */
	AAirshipPawn* GetLocalGunnerShip() const { return LocalShip.Get(); }
	int32 GetLocalGunnerStation() const { return LocalStation; }

	/**
	 * Server -> owning client (a local controller on the server runs it at once): mounted (Ship, Station >= 0), or
	 * dismounted (null, -1, the exit point in the ship's hull space, the launch velocity).
	 */
	UFUNCTION(Client, Reliable)
	void ClientMountChanged(AAirshipPawn* Ship, int8 Station, FVector_NetQuantize ExitHullLocal, FVector_NetQuantize LaunchVelocity);

	/** Server -> owning client: the F was refused and why (an enemy ship's helm or gun in range, or nothing). Broadcasts OnLocalUseRefused there. */
	UFUNCTION(Client, Unreliable)
	void ClientUseRefused(EAirshipUseRefusal Reason);

	/**
	 * The local player's machine: an F of its own was refused (the match HUD's toast "That's ORANGE's ship"). Process-wide,
	 * so it names the refused player's controller: single-process PIE runs every player's HUD in one process, and each
	 * HUD only shows its own player's refusals.
	 */
	static TMulticastDelegate<void(const APlayerController* /*Player*/, EAirshipUseRefusal)> OnLocalUseRefused;

	/**
	 * Server -> owning client, right after the possession went back to Pilot (ClientRestart is on the same channel, so it
	 * has run): the pilot left Ship's helm with F and stays where it stood. This machine's copy does the same at once
	 * (AAirshipPawn::PlaceLeftPilotLocal).
	 */
	UFUNCTION(Client, Reliable)
	void ClientLeftHelm(AAirshipPawn* Ship, ACharacter* Pilot);

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

	/** An explicit station (UI, tests). */
	UFUNCTION(Server, Reliable)
	void ServerRequestMount(AAirshipPawn* Ship, uint8 Station);

	UFUNCTION(Server, Reliable)
	void ServerRequestDismount();

	/** A mounted gunner's aim point (world): about GunnerAimSendRate per second, when it moved, and a heartbeat. */
	UFUNCTION(Server, Unreliable)
	void ServerSetGunnerAim(FVector_NetQuantize AimPoint);

	/** A cannon gunner's press (the server checks the reload). */
	UFUNCTION(Server, Reliable)
	void ServerGunnerFire(FVector_NetQuantize AimPoint);

	/** A turret gunner's trigger (held / released). */
	UFUNCTION(Server, Reliable)
	void ServerGunnerTrigger(bool bHeld, FVector_NetQuantize AimPoint);

private:

	/** Owning client: input component + mapping context, once the local player exists. True when done (or not needed). */
	bool TrySetupLocalInput();

	void TeardownLocalInput();

	void OnBoardPressed();

	/** Server: request debounce (key repeat, double press). */
	bool ConsumeRequestCooldown();

	/** Server: the ship and station the player's pawn mans, or false. */
	bool FindServerStation(AAirshipPawn*& OutShip, int32& OutStation) const;

	/** The tick runs while the input setup retries or a local gunner is mounted. */
	void UpdateTickState();

	// Gunner (the owning machine)
	void BeginLocalGunner(AAirshipPawn* Ship, int32 Station);
	void EndLocalGunner(AAirshipPawn* Ship, const FVector& ExitHullLocal, const FVector& LaunchVelocity, bool bPlaceCharacter);
	void SetupGunnerInput();
	void TeardownGunnerInput();
	void ShowGunnerHUD();
	void HideGunnerHUD();

	/** The mounted gunner's frame: aim trace, local barrel / turret, aim sends, the safety net. */
	void TickLocalGunner(float DeltaTime);

	/** This frame's camera aim point (the ship's aim trace from the player's view). False without a view. */
	bool ComputeGunnerAim(FVector& OutAim) const;

	/** A cannon press: the host fires at once, a client predicts and asks. */
	void RequestGunnerCannonFire();

	void SendGunnerTrigger(bool bHeld);

	void OnGunnerLook(const FInputActionValue& Value);
	void OnGunnerFireStarted(const FInputActionValue& Value);
	void OnGunnerFireReleased(const FInputActionValue& Value);
	void OnGunnerAimStarted(const FInputActionValue& Value);
	void OnGunnerAimReleased(const FInputActionValue& Value);
	void OnGunnerZoom(const FInputActionValue& Value);
	void OnGunnerExit(const FInputActionValue& Value);

	UPROPERTY(Transient)
	TObjectPtr<UEnhancedInputComponent> BoardInputComponent;

	TWeakObjectPtr<UEnhancedInputLocalPlayerSubsystem> MappingSubsystem;
	TWeakObjectPtr<const UInputMappingContext> AddedMappingContext;

	bool bLocalInputDone = false;
	/** The owning client's input setup is still waiting for its local player (retried on the tick for 30 s). */
	bool bSetupRetrying = false;
	float SetupRetryTime = 0.f;
	double LastRequestTime = -1000.0;

	// ---- The local gunner (this machine's own player at a station)

	TWeakObjectPtr<AAirshipPawn> LocalShip;
	TWeakObjectPtr<ACharacter> LocalGunner;
	int32 LocalStation = -1;

	/**
	 * Seconds the ship hasn't listed the pawn at LocalStation, and whether it has listed it since the mount: the
	 * replicated list may come after the RPC (5 s of grace), and once it stops listing it this machine lets go after 1 s.
	 */
	float LocalStationMissingTime = 0.f;
	bool bLocalStationConfirmed = false;

	bool bLocalTrigger = false;
	FVector LocalAim = FVector::ZeroVector;
	bool bLocalAimValid = false;
	FVector LastSentAim = FVector::ZeroVector;
	double LastAimSendTime = -1000.0;

	/** A client's own gunner: the movement's bClientIgnoreMovementCorrections before the mount (restored at the dismount). */
	bool bSavedClientIgnoreCorrections = false;
	bool bHasSavedClientIgnoreCorrections = false;

	/** Camera FOV / arm length at mount (restored at dismount), whether Aim is held. */
	float SavedFOV = 0.f;
	float SavedArmLength = 0.f;
	bool bHasSavedFOV = false;
	bool bHasSavedArm = false;
	bool bGunnerAimHeld = false;

	UPROPERTY(Transient)
	TObjectPtr<UEnhancedInputComponent> GunnerInputComponent;

	TWeakObjectPtr<UEnhancedInputLocalPlayerSubsystem> GunnerMappingSubsystem;
	TWeakObjectPtr<const UInputMappingContext> GunnerMappingContext;

	UPROPERTY(Transient)
	TObjectPtr<UAirshipHUDWidget> GunnerHUDWidget;
};
