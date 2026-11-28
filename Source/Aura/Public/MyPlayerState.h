// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PlayerState.h"
#include "Match/MyMatchTypes.h"
#include "MyPlayerState.generated.h"

class UMySpellMenuWidgetController;
class AMyHexPlatform;
class UMyLevelUpInfo;
class UMyAttributeSet;
class UMyAbilitySystemComponent;
/**
 * 
 */
DECLARE_MULTICAST_DELEGATE_OneParam(FOnStatChangedDelegateSignature,int32);//NewXP

UCLASS()
class AURA_API AMyPlayerState : public APlayerState
{
	GENERATED_BODY()
	
public:
	
	UPROPERTY(EditAnywhere)
	UMyLevelUpInfo* MyLevelUpInfo;
	
	UPROPERTY(EditAnywhere)
	TSubclassOf<UMySpellMenuWidgetController> MySpellMenuWidgetControllerClass;
	
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
	
	UPROPERTY()
	UMyAbilitySystemComponent* MyAbilitySystemComponent;
	
	UPROPERTY()
	UMyAttributeSet* MyAttributeSet;
	
	AMyPlayerState();
	
	
	FOnStatChangedDelegateSignature OnXPChangedDelegate;
	
	FOnStatChangedDelegateSignature OnLevelChangedDelegate;
	
	FOnStatChangedDelegateSignature OnAttribPointsChangedDelegate;
	
	FOnStatChangedDelegateSignature OnSpellPointsChangedDelegate;
	
	int32 GetXP() const {return XP;}
	
	int32 GetLevel() const {return Level;}
	
	int32 GetAttributePoints() const {return AttributePoints;}
	
	int32 GetSpellPoints() const {return SpellPoints;}
	
	void AddToXP(int32 InExp);
	
	void AddToLevel(int32 InLevels);
	
	void AddToAttributePoints(int32 InAttributePoints);
	
	void AddToSpellPoints(int32 InSpellPoints);
	
	/** Server. The pawn landed on Platform; re-ranks the players in AMyGameState when it is a new one. */
	void SetCurrentPlatform(AMyHexPlatform* Platform);
	
	AMyHexPlatform* GetCurrentPlatform() const { return CurrentPlatform; }
	
	/** Path distance of the platform this player last landed on. -1 until it lands on one that has it. */
	UFUNCTION(BlueprintPure, Category = "Player Ranking")
	float GetPlatformSplineDistance() const { return PlatformSplineDistance; }
	
	bool HasPlatformSplineDistance() const { return PlatformSplineDistance >= 0.f; }
	
	/** Team match team: 0 or 1, 255 (MyMatch::NoTeam) outside a match. Set by AMyGameMode when the player joins; survives respawns. */
	UFUNCTION(BlueprintPure, Category = "Match")
	uint8 GetTeamId() const { return TeamId; }
	
	/** Server. Broadcasts OnTeamChanged when it changes. */
	void SetTeamId(uint8 NewTeam);
	
	/** Every machine: on the server from SetTeamId, on clients when TeamId replicates. */
	FSimpleMulticastDelegate OnTeamChanged;
	
	// -------------------------------------------------------------------------
	// Lobby (Docs/Airship/round2/SPEC_B_LOBBY.md 4.3-4.5): written by AMyGameMode on the server, replicated
	// -------------------------------------------------------------------------
	
	/** The player pressed READY in the lobby. The host has no flag (he is ready when he starts). */
	UFUNCTION(BlueprintPure, Category = "Lobby")
	bool IsLobbyReady() const { return bLobbyReady; }
	
	/** A pending switch request to this team (255 = none): he swaps when a player of that team asks for his. */
	UFUNCTION(BlueprintPure, Category = "Lobby")
	uint8 GetRequestedTeam() const { return RequestedTeam; }
	
	/** The host's player state (a local controller on the server). */
	UFUNCTION(BlueprintPure, Category = "Lobby")
	bool IsHost() const { return bIsHost; }
	
	/**
	 * Carried through a seamless travel and its owner hasn't arrived yet: the lobby counts it out, shows LOADING and
	 * blocks the Start (EMyLobbyStartBlock::Arriving). Replicated, any machine. Not the engine's bActorSeamlessTraveled:
	 * InitializeNetworkActors clears that on every actor before any game code runs (World.cpp:9021, Level.cpp:3709).
	 * AMyGameMode::PostSeamlessTravel sets it on every carried player state; the player state that replaces it when its
	 * owner has loaded (HandleSeamlessTravelPlayer) starts without it, and the carried one is destroyed then.
	 */
	UFUNCTION(BlueprintPure, Category = "Lobby")
	bool IsArriving() const { return bArriving; }
	
	/** Server only: when the pending request was made (oldest answered first). */
	double GetRequestServerTime() const { return RequestServerTime; }
	
	// Server writers (AMyGameMode): force a net update and broadcast OnLobbyChanged
	void SetLobbyReady(bool bReady);
	void SetRequestedTeam(uint8 Team, double ServerTime = 0.0);
	void SetIsHost(bool bHost);
	void SetArriving(bool bNewArriving);
	
	/** Every machine: a lobby field changed (on the server from the setters, on clients when one replicates). */
	FSimpleMulticastDelegate OnLobbyChanged;
	
	protected:
	
	/** Seamless travel (and an inactive player state): Super, then the team. Not the ready, host or arriving flags, not the platform. */
	virtual void CopyProperties(APlayerState* PlayerState) override;
	
	private:
	
	UPROPERTY(ReplicatedUsing=OnRep_Lobby)
	bool bLobbyReady=false;
	
	UPROPERTY(ReplicatedUsing=OnRep_Lobby)
	uint8 RequestedTeam=MyMatch::NoTeam;
	
	UPROPERTY(ReplicatedUsing=OnRep_Lobby)
	bool bIsHost=false;
	
	/** IsArriving. Never copied (CopyProperties): the replacement has arrived. */
	UPROPERTY(ReplicatedUsing=OnRep_Lobby)
	bool bArriving=false;
	
	double RequestServerTime=0.0;
	
	UFUNCTION()
	void OnRep_Lobby();
	
	
	UPROPERTY(ReplicatedUsing=OnRep_TeamId)
	uint8 TeamId=MyMatch::NoTeam;
	
	UFUNCTION()
	void OnRep_TeamId();
	
	/** Last platform the pawn landed on (kept while on bridges or in the air). Null once destroyed. */
	UPROPERTY(Replicated)
	TObjectPtr<AMyHexPlatform> CurrentPlatform;
	
	UPROPERTY(Replicated)
	float PlatformSplineDistance = -1.f;
	
	
	UPROPERTY(ReplicatedUsing=OnRep_XP)
	int32 XP=0;
	
	UPROPERTY(ReplicatedUsing=OnRep_Level)
	int32 Level=1;
	
	UPROPERTY(ReplicatedUsing=OnRep_AttributePoints)
	int32 AttributePoints=0;
	
	UPROPERTY(ReplicatedUsing=OnRep_SpellPoints)
	int32 SpellPoints=0;
	
	UFUNCTION()
	void OnRep_XP(int32 OldExp);
	
	UFUNCTION()
	void OnRep_Level(int32 OldLevel);
	
	UFUNCTION()
	void OnRep_AttributePoints(int32 OldAttributePoints);
	
	UFUNCTION()
	void OnRep_SpellPoints(int32 OldSpellPoints);
	
};
