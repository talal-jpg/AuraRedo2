// Fill out your copyright notice in the Description page of Project Settings.


#include "MyGameState.h"

#include "EngineUtils.h"
#include "MyPlayerState.h"
#include "NiagaraFunctionLibrary.h"
#include "NiagaraSystem.h"
#include "Actors/MyEffectActor.h"
#include "Actors/MyHexPlatform.h"
#include "Match/MyMatchSettings.h"
#include "Kismet/KismetSystemLibrary.h"
#include "Net/UnrealNetwork.h"


AMyGameState::AMyGameState()
{
	for (int32 Index = 0; Index < MyMatch::NumTeams; ++Index)
	{
		Teams[Index].TeamId = static_cast<uint8>(Index);
	}
}

void AMyGameState::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);

	DOREPLIFETIME(AMyGameState, PlayerRanking);

	DOREPLIFETIME(AMyGameState, MatchPhase);
	DOREPLIFETIME(AMyGameState, MatchRules);
	DOREPLIFETIME(AMyGameState, Teams);
	DOREPLIFETIME(AMyGameState, MatchResult);
	DOREPLIFETIME(AMyGameState, EndReason);
	DOREPLIFETIME(AMyGameState, WinningTeam);
	DOREPLIFETIME(AMyGameState, PhaseEndServerTime);
	DOREPLIFETIME(AMyGameState, MatchEndServerTime);
	DOREPLIFETIME(AMyGameState, ExpectedPlayers);
	DOREPLIFETIME(AMyGameState, RoundIndex);
	DOREPLIFETIME(AMyGameState, bLaneSidesSwapped);
	DOREPLIFETIME(AMyGameState, bPlayGoesOn);
	DOREPLIFETIME(AMyGameState, bLobbyRound);
	DOREPLIFETIME(AMyGameState, bInLobby);
	DOREPLIFETIME(AMyGameState, LobbyStartBlock);
	DOREPLIFETIME(AMyGameState, LobbyConfirmBlock);
	DOREPLIFETIME(AMyGameState, LobbyNotReady);
	DOREPLIFETIME(AMyGameState, bLobbyRematch);
}

void AMyGameState::BeginPlay()
{
	Super::BeginPlay();

	// A client's first replicated state may already say InProgress (a late joiner) or the lobby
	ApplyLobbyActorState();
}

void AMyGameState::AddPlayerState(APlayerState* PlayerState)
{
	Super::AddPlayerState(PlayerState);

	if (HasAuthority())
	{
		UpdatePlayerRanking();
	}
}

void AMyGameState::RemovePlayerState(APlayerState* PlayerState)
{
	Super::RemovePlayerState(PlayerState);

	if (HasAuthority())
	{
		UpdatePlayerRanking();
	}
}

void AMyGameState::UpdatePlayerRanking()
{
	if (!HasAuthority())
	{
		return;
	}

	TArray<TObjectPtr<AMyPlayerState>> Ranked;

	for (APlayerState* PlayerState : PlayerArray)
	{
		if (AMyPlayerState* MyPlayerState = Cast<AMyPlayerState>(PlayerState))
		{
			Ranked.Add(MyPlayerState);
		}
	}

	// Furthest first; -1 (no platform yet) sorts last. Stable, so ties keep join order.
	Ranked.StableSort([](const AMyPlayerState& A, const AMyPlayerState& B)
	{
		return A.GetPlatformSplineDistance() > B.GetPlatformSplineDistance();
	});

	int32 NumLeaders = 0;

	if (Ranked.Num() > 0 && Ranked[0]->HasPlatformSplineDistance())
	{
		const float LeadDistance = Ranked[0]->GetPlatformSplineDistance();

		while (NumLeaders < Ranked.Num()
			&& Ranked[NumLeaders]->GetPlatformSplineDistance() >= LeadDistance - LeadDistanceTolerance)
		{
			++NumLeaders;
		}
	}

	// The lead can move to a further platform without the order changing, so this runs before the
	// "nothing changed" early out below. Only platforms behind the lead's platform: the one the lead
	// stands on (and those at its distance) keep standing until the lead moves on.
	if (NumLeaders > 0)
	{
		ActivatePlatformsUpTo(Ranked[0]->GetPlatformSplineDistance() - CollapseStartBehindLead);
	}

	if (Ranked == PlayerRanking.PlayerStates && NumLeaders == PlayerRanking.NumLeaders)
	{
		return;
	}

	PlayerRanking.PlayerStates = MoveTemp(Ranked);
	PlayerRanking.NumLeaders = NumLeaders;

	//TODO Add Leaders PSs array to the broadcast and Sub to it in OverlayWC And show in HUD
	for (auto PS :GetLeadingPlayerStates() )
	{
		UKismetSystemLibrary::PrintString(GetWorld(), TEXT("Leader: ") + PS->GetPlayerName(),true,true,FLinearColor::Red,2000);
	}
	UKismetSystemLibrary::PrintString(GetWorld(), TEXT("NumLeaders: ") + FString::FromInt(NumLeaders));
	
	OnPlayerRankingChanged.Broadcast();
}

void AMyGameState::ActivatePlatformsUpTo(float MaxDistance)
{
	// Already activated everything up to here
	if (MaxDistance <= ActivatedSplineDistance)
	{
		return;
	}

	ActivatedSplineDistance = MaxDistance;

	// Platforms spawned later check GetActivatedSplineDistance() themselves once their bridges are ready
	for (TActorIterator<AMyHexPlatform> It(GetWorld()); It; ++It)
	{
		AMyHexPlatform* Platform = *It;

		if (IsValid(Platform) && Platform->HasSplineDistance() && Platform->GetSplineDistance() <= MaxDistance)
		{
			// Latched, and all at this moment, so platforms at the same distance collapse in step.
			// Collapsing starts once the platform's bridges are built (timed from now).
			Platform->NotifyLeadLanded();
		}
	}
}

float AMyGameState::GetLeadSplineDistance() const
{
	const AMyPlayerState* Lead = PlayerRanking.NumLeaders > 0 && PlayerRanking.PlayerStates.Num() > 0
		? PlayerRanking.PlayerStates[0].Get()
		: nullptr;

	return Lead ? Lead->GetPlatformSplineDistance() : -1.f;
}

TArray<AMyPlayerState*> AMyGameState::GetLeadingPlayerStates() const
{
	TArray<AMyPlayerState*> Leaders;
	const int32 NumLeaders = FMath::Min(PlayerRanking.NumLeaders, PlayerRanking.PlayerStates.Num());

	for (int32 Index = 0; Index < NumLeaders; ++Index)
	{
		if (AMyPlayerState* PlayerState = PlayerRanking.PlayerStates[Index])
		{
			Leaders.Add(PlayerState);
		}
	}

	return Leaders;
}

bool AMyGameState::IsLeading(const AMyPlayerState* PlayerState) const
{
	const int32 Index = PlayerRanking.PlayerStates.IndexOfByKey(PlayerState);
	return PlayerState && Index != INDEX_NONE && Index < PlayerRanking.NumLeaders;
}

void AMyGameState::OnRep_PlayerRanking()
{
	OnPlayerRankingChanged.Broadcast();
}

void AMyGameState::MulticastPlayRespawnFX_Implementation(UNiagaraSystem* System, FVector_NetQuantize Location, FRotator Rotation)
{
	if (System && GetNetMode() != NM_DedicatedServer)
	{
		UNiagaraFunctionLibrary::SpawnSystemAtLocation(this, System, Location, Rotation);
	}
}

const FMyTeamState& AMyGameState::GetTeamState(uint8 TeamId) const
{
	static const FMyTeamState NoTeamState;
	return TeamId < MyMatch::NumTeams ? Teams[TeamId] : NoTeamState;
}

void AMyGameState::MulticastMatchEvent_Implementation(EMyMatchEvent Event, uint8 TeamId, int32 Value)
{
	// One line on every machine, so the harnesses (as_70_matchlib MB_EVENT_RE) can see a client's receipt, not just the send
	const ENetMode NetMode = GetNetMode();
	const TCHAR* Role = NetMode == NM_Client ? TEXT("client") : NetMode == NM_Standalone ? TEXT("standalone") : TEXT("server");
	const UEnum* EventEnum = StaticEnum<EMyMatchEvent>();
	UE_LOG(LogMatch, Log, TEXT("event %s team %d value %d (%s %s)"),
		EventEnum ? *EventEnum->GetNameStringByValue(static_cast<int64>(Event)) : TEXT("?"), TeamId, Value, Role, *GetNameSafe(GetWorld()));

	OnMatchEvent.Broadcast(Event, TeamId, Value);
}

void AMyGameState::SetMatchPhase(EMyMatchPhase NewPhase, double NewPhaseEndServerTime, bool bInPlayGoesOn)
{
	if (!HasAuthority())
	{
		return;
	}

	MatchPhase = NewPhase;
	PhaseEndServerTime = NewPhaseEndServerTime;
	bPlayGoesOn = NewPhase == EMyMatchPhase::Countdown && bInPlayGoesOn;
	NotifyMatchWritten();
}

void AMyGameState::SetLaneSidesSwapped(bool bSwapped)
{
	if (!HasAuthority())
	{
		return;
	}

	bLaneSidesSwapped = bSwapped;
	NotifyMatchWritten();
}

void AMyGameState::SetMatchRules(const FMyMatchRules& NewRules)
{
	if (!HasAuthority())
	{
		return;
	}

	MatchRules = NewRules;
	NotifyMatchWritten();
}

FMyTeamState& AMyGameState::EditTeam(uint8 TeamId)
{
	if (!ensureMsgf(HasAuthority() && TeamId < MyMatch::NumTeams, TEXT("EditTeam(%d): server only, team 0 or 1"), TeamId))
	{
		ScratchTeam = FMyTeamState();
		return ScratchTeam;
	}

	return Teams[TeamId];
}

void AMyGameState::SetResult(EMyMatchResult NewResult, uint8 NewWinningTeam, EMyMatchEndReason NewEndReason)
{
	if (!HasAuthority())
	{
		return;
	}

	MatchResult = NewResult;
	WinningTeam = NewResult == EMyMatchResult::TeamWon ? NewWinningTeam : MyMatch::NoTeam;
	EndReason = NewEndReason;
	NotifyMatchWritten();
}

void AMyGameState::SetMatchEndServerTime(double NewMatchEndServerTime)
{
	if (!HasAuthority())
	{
		return;
	}

	MatchEndServerTime = NewMatchEndServerTime;
	NotifyMatchWritten();
}

void AMyGameState::SetExpectedPlayers(int32 NewExpectedPlayers)
{
	if (!HasAuthority())
	{
		return;
	}

	ExpectedPlayers = NewExpectedPlayers;
	NotifyMatchWritten();
}

void AMyGameState::SetRoundIndex(int32 NewRoundIndex)
{
	if (!HasAuthority())
	{
		return;
	}

	RoundIndex = NewRoundIndex;
	NotifyMatchWritten();
}

void AMyGameState::MarkTeamsDirty()
{
	if (HasAuthority())
	{
		NotifyMatchWritten();
	}
}

void AMyGameState::NotifyMatchWritten()
{
	ForceNetUpdate();
	ApplyLobbyActorState();
	OnMatchChanged.Broadcast();
}

void AMyGameState::OnRep_Match()
{
	ApplyLobbyActorState();
	OnMatchChanged.Broadcast();
}

// -----------------------------------------------------------------------------
// Lobby (SPEC_B_LOBBY 3.4, 4.3)
// -----------------------------------------------------------------------------

void AMyGameState::SetLobbyRound(bool bNewLobbyRound)
{
	if (HasAuthority() && bLobbyRound != bNewLobbyRound)
	{
		bLobbyRound = bNewLobbyRound;
		NotifyMatchWritten();
	}
}

void AMyGameState::SetInLobby(bool bNewInLobby)
{
	if (HasAuthority() && bInLobby != bNewInLobby)
	{
		bInLobby = bNewInLobby;
		NotifyMatchWritten();
	}
}

void AMyGameState::SetLobbyStartBlock(EMyLobbyStartBlock NewBlock, int32 NewNotReady, EMyLobbyStartBlock NewConfirmBlock)
{
	const uint8 NotReady = static_cast<uint8>(FMath::Clamp(NewNotReady, 0, 255));

	if (HasAuthority() && (LobbyStartBlock != NewBlock || LobbyNotReady != NotReady || LobbyConfirmBlock != NewConfirmBlock))
	{
		LobbyStartBlock = NewBlock;
		LobbyNotReady = NotReady;
		LobbyConfirmBlock = NewConfirmBlock;
		NotifyMatchWritten();
	}
}

void AMyGameState::SetLobbyRematch(bool bNewRematch)
{
	if (HasAuthority() && bLobbyRematch != bNewRematch)
	{
		bLobbyRematch = bNewRematch;
		NotifyMatchWritten();
	}
}

int32 AMyGameState::CountArrivingPlayers() const
{
	int32 Count = 0;

	for (const APlayerState* PlayerState : PlayerArray)
	{
		const AMyPlayerState* MyPlayerState = Cast<AMyPlayerState>(PlayerState);
		Count += (MyPlayerState && MyPlayerState->IsArriving()) ? 1 : 0;
	}

	return Count;
}

void AMyGameState::ApplyLobbyActorState()
{
	UWorld* World = GetWorld();

	// Not before the world plays (BeginPlay applies it), never in an editor world
	if (!World || !World->IsGameWorld() || !HasActorBegunPlay())
	{
		return;
	}

	const UMyMatchSettings* Settings = UMyMatchSettings::Get();

	// Q-L1: actors Talal tags LobbyOnly are there only while there is no match or the lobby runs. A state, not an edge, so
	// a late joiner's first InProgress hides them too (critique m5)
	const bool bShow = MatchPhase == EMyMatchPhase::None || bInLobby;

	if (bShow != bLobbyActorsShown)
	{
		bLobbyActorsShown = bShow;

		if (!bShow)
		{
			HiddenLobbyActors.Reset();

			if (!Settings->LobbyOnlyActorTag.IsNone())
			{
				for (TActorIterator<AActor> It(World); It; ++It)
				{
					AActor* Actor = *It;

					if (IsValid(Actor) && Actor->ActorHasTag(Settings->LobbyOnlyActorTag) && !Actor->IsHidden())
					{
						Actor->SetActorHiddenInGame(true);
						Actor->SetActorEnableCollision(false);
						HiddenLobbyActors.Add(Actor);
					}
				}
			}

			if (HiddenLobbyActors.Num() > 0)
			{
				UE_LOG(LogMatch, Log, TEXT("Lobby: %d %s actor(s) hidden for the match"), HiddenLobbyActors.Num(), *Settings->LobbyOnlyActorTag.ToString());
			}
		}
		else
		{
			for (const TWeakObjectPtr<AActor>& WeakActor : HiddenLobbyActors)
			{
				if (AActor* Actor = WeakActor.Get())
				{
					Actor->SetActorHiddenInGame(false);
					Actor->SetActorEnableCollision(true);
				}
			}

			HiddenLobbyActors.Reset();
		}
	}

	// Pickups: nothing to collect in the lobby, so round 1 starts like every later round (critique m11). Their overlap
	// runs on clients too (MyEffectActor.cpp OnOverlap has no authority test), hence every machine
	if (bInLobby != bPickupsOff)
	{
		bPickupsOff = bInLobby;

		if (bPickupsOff)
		{
			DisabledPickups.Reset();

			for (TActorIterator<AMyEffectActor> It(World); It; ++It)
			{
				if (IsValid(*It) && It->GetActorEnableCollision())
				{
					It->SetActorEnableCollision(false);
					DisabledPickups.Add(*It);
				}
			}
		}
		else
		{
			for (const TWeakObjectPtr<AActor>& WeakActor : DisabledPickups)
			{
				if (AActor* Actor = WeakActor.Get())
				{
					Actor->SetActorEnableCollision(true);
				}
			}

			DisabledPickups.Reset();
		}

		UE_LOG(LogMatch, Verbose, TEXT("Lobby: pickups %s"), bPickupsOff ? TEXT("off") : TEXT("on"));
	}
}
