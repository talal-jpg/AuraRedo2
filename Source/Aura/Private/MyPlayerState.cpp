// Fill out your copyright notice in the Description page of Project Settings.


#include "MyPlayerState.h"

#include <string>

#include "MyGameState.h"
#include "AbilitySystem/MyAbilitySystemComponent.h"
#include "Actors/MyHexPlatform.h"
#include "Engine/World.h"
#include "AbilitySystem/MyAttributeSet.h"
#include "Kismet/KismetSystemLibrary.h"
#include "Net/UnrealNetwork.h"

void AMyPlayerState::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME_CONDITION_NOTIFY(AMyPlayerState,XP,COND_None,REPNOTIFY_Always);
	DOREPLIFETIME_CONDITION_NOTIFY(AMyPlayerState,Level,COND_None,REPNOTIFY_Always);
	DOREPLIFETIME_CONDITION_NOTIFY(AMyPlayerState,AttributePoints,COND_None,REPNOTIFY_Always);
	DOREPLIFETIME_CONDITION_NOTIFY(AMyPlayerState,SpellPoints,COND_None,REPNOTIFY_Always);
	DOREPLIFETIME(AMyPlayerState,CurrentPlatform);
	DOREPLIFETIME(AMyPlayerState,PlatformSplineDistance);
	DOREPLIFETIME(AMyPlayerState,TeamId);
	DOREPLIFETIME(AMyPlayerState,bLobbyReady);
	DOREPLIFETIME(AMyPlayerState,RequestedTeam);
	DOREPLIFETIME(AMyPlayerState,bIsHost);
	DOREPLIFETIME(AMyPlayerState,bArriving);
}

void AMyPlayerState::CopyProperties(APlayerState* PlayerState)
{
	Super::CopyProperties(PlayerState);
	
	// SPEC_B_LOBBY 5.4 row 7: a seamless return keeps the team; AMyGameMode::InitSeamlessTravelPlayer then checks it
	// against the new round's mode and caps (AssignTeam's PreferredTeam)
	if (AMyPlayerState* NewPlayerState = Cast<AMyPlayerState>(PlayerState))
	{
		NewPlayerState->SetTeamId(TeamId);
	}
}

void AMyPlayerState::SetLobbyReady(bool bReady)
{
	if (!HasAuthority() || bLobbyReady == bReady)
	{
		return;
	}
	
	bLobbyReady = bReady;
	ForceNetUpdate();
	OnLobbyChanged.Broadcast();
}

void AMyPlayerState::SetRequestedTeam(uint8 Team, double ServerTime)
{
	if (!HasAuthority())
	{
		return;
	}
	
	RequestServerTime = Team == MyMatch::NoTeam ? 0.0 : ServerTime;
	
	if (RequestedTeam != Team)
	{
		RequestedTeam = Team;
		ForceNetUpdate();
		OnLobbyChanged.Broadcast();
	}
}

void AMyPlayerState::SetIsHost(bool bHost)
{
	if (!HasAuthority() || bIsHost == bHost)
	{
		return;
	}
	
	bIsHost = bHost;
	ForceNetUpdate();
	OnLobbyChanged.Broadcast();
}

void AMyPlayerState::SetArriving(bool bNewArriving)
{
	if (!HasAuthority() || bArriving == bNewArriving)
	{
		return;
	}
	
	bArriving = bNewArriving;
	ForceNetUpdate();
	OnLobbyChanged.Broadcast();
}

void AMyPlayerState::OnRep_Lobby()
{
	OnLobbyChanged.Broadcast();
}

void AMyPlayerState::SetTeamId(uint8 NewTeam)
{
	if (!HasAuthority() || NewTeam == TeamId)
	{
		return;
	}
	
	TeamId = NewTeam;
	ForceNetUpdate();
	OnTeamChanged.Broadcast();
}

void AMyPlayerState::OnRep_TeamId()
{
	OnTeamChanged.Broadcast();
}

void AMyPlayerState::SetCurrentPlatform(AMyHexPlatform* Platform)
{
	if (!HasAuthority() || !Platform || Platform == CurrentPlatform)
	{
		return;
	}
	
	// SPEC_B_LOBBY 3.3: no ranking (so no collapse) in the lobby or its countdown, also during the zone's grace (RL7)
	const AMyGameState* LobbyGameState = GetWorld() ? GetWorld()->GetGameState<AMyGameState>() : nullptr;
	
	if (LobbyGameState && LobbyGameState->IsInLobby())
	{
		return;
	}
	
	CurrentPlatform = Platform;
	
	if (!Platform->HasSplineDistance())
	{
		// Keep the last known distance; the PCG graph didn't set this platform's SplineDistance
		UE_LOG(LogTemp, Warning, TEXT("%s has no SplineDistance, %s keeps its rank"), *Platform->GetName(), *GetPlayerName());
		return;
	}
	
	PlatformSplineDistance = Platform->GetSplineDistance();
	
	if (AMyGameState* MyGameState = GetWorld()->GetGameState<AMyGameState>())
	{
		MyGameState->UpdatePlayerRanking();
	}
}

void AMyPlayerState::AddToXP(int32 InXP)
{
	XP+=InXP;
	OnXPChangedDelegate.Broadcast(XP);
}

void AMyPlayerState::AddToLevel(int32 InLevels)
{
	Level+=InLevels;
	OnLevelChangedDelegate.Broadcast(Level);
}

void AMyPlayerState::AddToAttributePoints(int32 InAttributePoints)
{
	AttributePoints+=InAttributePoints;
	OnAttribPointsChangedDelegate.Broadcast(AttributePoints);
}

void AMyPlayerState::AddToSpellPoints(int32 InSpellPoints)
{
	SpellPoints+=InSpellPoints;
	OnSpellPointsChangedDelegate.Broadcast(SpellPoints);
}

void AMyPlayerState::OnRep_XP(int32 OldXP)
{
	OnXPChangedDelegate.Broadcast(XP);
}

void AMyPlayerState::OnRep_Level(int32 OldLevel)
{
	OnLevelChangedDelegate.Broadcast(Level);
}

void AMyPlayerState::OnRep_AttributePoints(int32 OldAttributePoints)
{
	OnAttribPointsChangedDelegate.Broadcast(AttributePoints);
}

void AMyPlayerState::OnRep_SpellPoints(int32 OldSpellPoints)
{
	OnSpellPointsChangedDelegate.Broadcast(SpellPoints);
}

AMyPlayerState::AMyPlayerState()
{
	MyAbilitySystemComponent=CreateDefaultSubobject<UMyAbilitySystemComponent>(TEXT("MyAbilitySystemComponent"));
	MyAttributeSet=CreateDefaultSubobject<UMyAttributeSet>(TEXT("MyAttributeSet"));
	
}

