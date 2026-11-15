// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "MyGameMode.generated.h"

class AMyHexPlatform;
class UDA_MyAbilityInfo;
class UMyLevelUpInfo;
class UDA_MyEnemyCharacterClassInfo;
class UMySpellMenuWidgetController;
class UNiagaraSystem;
/**
 * 
 */
UCLASS()
class AURA_API AMyGameMode : public AGameModeBase
{
	GENERATED_BODY()
	
public:
	AMyGameMode();
	
	virtual void PostLogin(APlayerController* NewPlayer) override;
	
	// Refuses players the host banned from the lobby (Current Session > Ban) and joins past the lobby's player limit
	virtual void PreLogin(const FString& Options, const FString& Address, const FUniqueNetIdRepl& UniqueId, FString& ErrorMessage) override;
	
	UPROPERTY(EditAnywhere)
	UDA_MyEnemyCharacterClassInfo* DA_MyEnemyCharacterClassInfo;
	
	UPROPERTY(EditAnywhere)
	UMyLevelUpInfo* DA_MyLevelUpInfo;
	
	UPROPERTY(EditAnywhere)
	UDA_MyAbilityInfo* DA_MyAbilityInfo;
	
	UPROPERTY(EditAnywhere)
	TSubclassOf<UMySpellMenuWidgetController> SpellMenuWidgetControllerClass;
	
	// -------------------------------------------------------------------------
	// Respawn: RespawnDelay seconds after a player dies (or falls out of the world), its controller gets a new
	// pawn on the platform just past the lead player's (AMyGameState ranking). The PlayerState and its ASC carry
	// over, so XP, level, spent points and abilities stay. AMyGameState plays RespawnFX there on every machine.
	// -------------------------------------------------------------------------
	
	/** Server. Called for every (re)started pawn: watches it for death and destruction. */
	virtual void SetPlayerDefaults(APawn* PlayerPawn) override;
	
	virtual void Logout(AController* Exiting) override;
	
	/** False while a respawn is pending, so a client's ServerRestartPlayer can't skip the wait. */
	virtual bool PlayerCanRestart_Implementation(APlayerController* Player) override;
	
	/** Off: dead players stay dead. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category="Respawn")
	bool bRespawnEnabled=true;
	
	/** Seconds from death to the new pawn. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category="Respawn", meta=(ClampMin="0.1"))
	float RespawnDelay=5.f;
	
	/** Plays at the respawn spot on every machine. Defaults to NS_Claude_RespawnFX. None = no FX. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category="Respawn")
	TObjectPtr<UNiagaraSystem> RespawnFX;
	
	/**
	 * The FX starts this long before the pawn appears, so its flash and the pawn showing line up
	 * (NS_Claude_RespawnFX flashes about 3 s in). The spot is picked when the FX starts. Capped at RespawnDelay.
	 */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category="Respawn", meta=(ClampMin="0"))
	float RespawnFXLeadTime=3.f;
	
	/** Gap (cm) between the top of the tile and the bottom of the new pawn's capsule. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category="Respawn", meta=(ClampMin="0"))
	float RespawnHeightAboveTile=10.f;
	
private:
	
	/** Where a respawn's pawn goes. */
	struct FRespawnSpot
	{
		FTransform PawnTransform;
		
		/** Under the pawn's capsule, where the FX plays. */
		FVector GroundLocation=FVector::ZeroVector;
		
		/** False for a PlayerStart. */
		bool bOnTile=false;
		TWeakObjectPtr<AMyHexPlatform> Platform;
		FIntVector TileCoord=FIntVector::ZeroValue;
	};
	
	struct FPendingRespawn
	{
		FTimerHandle FXTimer;
		FTimerHandle RespawnTimer;
		
		/** Picked when the FX starts. Other respawns keep clear of it until this one spawns. */
		TOptional<FRespawnSpot> Spot;
	};
	
	/** The pawn a respawn spawns, for the fit tests: its class default and capsule size. */
	struct FPawnFit
	{
		const APawn* PawnToFit=nullptr;
		float HalfHeight=0.f;
		float Radius=0.f;
	};
	
	/** Starts the FX and respawn timers. Does nothing while one is pending for Controller. */
	void ScheduleRespawn(AController* Controller);
	
	/** Picks the spot and plays the FX there. */
	void StartRespawnFX(TWeakObjectPtr<AController> WeakController);
	
	/** Replaces the controller's dead pawn (if it still has one) with a new pawn at the picked spot. */
	void RespawnPlayer(TWeakObjectPtr<AController> WeakController);
	
	/** False when Controller has no default pawn class. */
	bool GetPawnFit(AController* Controller, FPawnFit& OutFit);
	
	/**
	 * A tile on the nearest platform past the lead's (the lead's own platform at the end of the path), or a
	 * PlayerStart when nobody has landed on a platform yet. False = nowhere.
	 */
	bool FindRespawnSpot(AController* Controller, const FPawnFit& Fit, FRespawnSpot& OutSpot);
	
	/** A live tile on Platform the pawn fits on: bridge path first (no props), then away from the edge, then near the centre. */
	bool FindRespawnTile(AMyHexPlatform* Platform, const FPawnFit& Fit, const FRotator& Rotation, const AController* Controller,
		FRespawnSpot& OutSpot) const;
	
	/**
	 * The pawn fits on the tile: it is still there, nothing blocks it (props, pawns), it isn't pushed off it, and
	 * it is clear of the spots other pending respawns (not Controller's) have picked.
	 */
	bool FitPawnOnTile(AMyHexPlatform* Platform, const FIntVector& TileCoord, const FPawnFit& Fit, const FRotator& Rotation,
		const AController* Controller, FRespawnSpot& OutSpot) const;
	
	void PlayRespawnFX(const FRespawnSpot& Spot) const;
	
	void WatchPlayerPawn(APawn* PlayerPawn);
	void UnwatchPlayerPawn(APawn* PlayerPawn);
	
	/** Bound to the pawn's OnDeathDelegate (IMyCombatInterface). */
	UFUNCTION()
	void OnPlayerPawnDied(AActor* DeadActor);
	
	/** Bound to the pawn's OnDestroyed: falling out of the world destroys the pawn without a death. */
	UFUNCTION()
	void OnPlayerPawnDestroyed(AActor* DestroyedActor);
	
	TMap<TWeakObjectPtr<AController>, FPendingRespawn> PendingRespawns;
	
	/** Watched pawns and their controllers (a pawn has none any more by the time OnDestroyed fires). */
	TMap<TWeakObjectPtr<APawn>, TWeakObjectPtr<AController>> WatchedPawns;
	
};
