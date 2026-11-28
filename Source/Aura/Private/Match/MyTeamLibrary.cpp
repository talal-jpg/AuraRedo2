// Fill out your copyright notice in the Description page of Project Settings.


#include "Match/MyTeamLibrary.h"

#include "AbilitySystemComponent.h"
#include "AbilitySystemGlobals.h"
#include "MyGameState.h"
#include "MyPlayerState.h"
#include "Airship/AirshipCannonball.h"
#include "Airship/AirshipPawn.h"
#include "Airship/AirshipTurret.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "GameFramework/Controller.h"
#include "Match/MyMatchSettings.h"

DEFINE_LOG_CATEGORY(LogMatch);

namespace MyTeamLibraryPrivate
{
	const AMyGameState* GetGameState(const UObject* WorldContext)
	{
		const UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
		return World ? World->GetGameState<AMyGameState>() : nullptr;
	}

	uint8 TeamOfPlayerState(const APlayerState* PlayerState)
	{
		const AMyPlayerState* MyPlayerState = Cast<AMyPlayerState>(PlayerState);
		return MyPlayerState ? MyPlayerState->GetTeamId() : MyMatch::NoTeam;
	}
}

bool UMyTeamLibrary::IsMatchActive(const UObject* WorldContext)
{
	const AMyGameState* GameState = MyTeamLibraryPrivate::GetGameState(WorldContext);
	return GameState && GameState->GetMatchPhase() != EMyMatchPhase::None;
}

const FMyMatchRules& UMyTeamLibrary::GetRules(const UObject* WorldContext)
{
	// No match: the game state's copy was never written (default-constructed), the config's defaults are the real ones
	const AMyGameState* GameState = MyTeamLibraryPrivate::GetGameState(WorldContext);
	return GameState && GameState->GetMatchPhase() != EMyMatchPhase::None ? GameState->GetMatchRules() : UMyMatchSettings::Get()->DefaultRules;
}

uint8 UMyTeamLibrary::GetTeamId(const AActor* Actor)
{
	using namespace MyTeamLibraryPrivate;

	if (!IsValid(Actor))
	{
		return MyMatch::NoTeam;
	}

	if (const APlayerState* PlayerState = Cast<APlayerState>(Actor))
	{
		return TeamOfPlayerState(PlayerState);
	}

	if (const AController* Controller = Cast<AController>(Actor))
	{
		return TeamOfPlayerState(Controller->GetPlayerState<APlayerState>());
	}

	// A ship's team is its own (a piloted ship's player state is the pilot's, the same team by CanUseShip)
	if (const AAirshipPawn* Ship = Cast<AAirshipPawn>(Actor))
	{
		return Ship->GetTeamId();
	}

	if (const AAirshipTurret* Turret = Cast<AAirshipTurret>(Actor))
	{
		const AAirshipPawn* TurretShip = Turret->GetShip();
		return TurretShip ? TurretShip->GetTeamId() : MyMatch::NoTeam;
	}

	// Stored at spawn: the firing ship may be gone by the time the ball lands
	if (const AAirshipCannonball* Cannonball = Cast<AAirshipCannonball>(Actor))
	{
		return Cannonball->SourceTeamId;
	}

	if (const APawn* Pawn = Cast<APawn>(Actor))
	{
		if (const APlayerState* PlayerState = Pawn->GetPlayerState())
		{
			return TeamOfPlayerState(PlayerState);
		}
	}

	// A seated pilot or a gunner is attached and unpossessed: he has no player state, his ship or character has
	const AActor* Parent = Actor->GetAttachParentActor();

	for (int32 Depth = 0; Parent && Depth < 4; ++Depth, Parent = Parent->GetAttachParentActor())
	{
		// The seated pilot: his ship (its team is his, CanUseShip); comes before the character test
		if (const AAirshipPawn* ParentShip = Cast<AAirshipPawn>(Parent))
		{
			return ParentShip->GetTeamId();
		}

		if (const ACharacter* Character = Cast<ACharacter>(Parent))
		{
			if (const APlayerState* PlayerState = Character->GetPlayerState())
			{
				return TeamOfPlayerState(PlayerState);
			}
		}
	}

	// Player characters keep their ASC on the player state, so this also finds an unpossessed mech
	if (const UAbilitySystemComponent* ASC = UAbilitySystemGlobals::GetAbilitySystemComponentFromActor(Actor))
	{
		return TeamOfPlayerState(Cast<APlayerState>(ASC->GetOwnerActor()));
	}

	return MyMatch::NoTeam;
}

bool UMyTeamLibrary::AreTeammates(const AActor* A, const AActor* B)
{
	const uint8 TeamA = GetTeamId(A);
	return TeamA != MyMatch::NoTeam && TeamA == GetTeamId(B);
}

bool UMyTeamLibrary::IsFriendlyFireBlocked(const AActor* Instigator, const AActor* Target)
{
	if (!IsValid(Instigator) || !IsValid(Target) || Instigator == Target || !IsMatchActive(Target))
	{
		return false;
	}

	return !GetRules(Target).bFriendlyFire && AreTeammates(Instigator, Target);
}

uint8 UMyTeamLibrary::GetFiringTeamId(const AAirshipPawn* Ship, const AActor* Shooter)
{
	if (!IsValid(Ship))
	{
		return GetTeamId(Shooter);
	}

	const uint8 ShipTeam = Ship->GetTeamId();

	if (ShipTeam != MyMatch::NoTeam)
	{
		return ShipTeam;
	}

	// A free ship is anyone's (CanUseShip): its fire belongs to whoever fires it
	if (IsValid(Shooter) && Shooter != Ship)
	{
		return GetTeamId(Shooter);
	}

	return MyTeamLibraryPrivate::TeamOfPlayerState(Ship->GetPlayerState());
}

bool UMyTeamLibrary::IsTeamFireBlocked(uint8 SourceTeam, const AActor* Target)
{
	if (SourceTeam == MyMatch::NoTeam || !IsValid(Target) || !IsMatchActive(Target))
	{
		return false;
	}

	return !GetRules(Target).bFriendlyFire && GetTeamId(Target) == SourceTeam;
}

bool UMyTeamLibrary::CanUseShip(const AActor* User, const AAirshipPawn* Ship)
{
	if (!IsValid(Ship))
	{
		return false;
	}

	// Free ships (and every ship while no match runs) are anyone's, as in PR A
	const uint8 ShipTeam = Ship->GetTeamId();

	if (ShipTeam == MyMatch::NoTeam || !IsMatchActive(Ship))
	{
		return true;
	}

	return GetTeamId(User) == ShipTeam;
}

bool UMyTeamLibrary::IsTeamShipTarget(const AActor* Target)
{
	if (!IsValid(Target) || !IsMatchActive(Target))
	{
		return false;
	}

	if (const AAirshipPawn* Ship = Cast<AAirshipPawn>(Target))
	{
		return Ship->GetTeamId() != MyMatch::NoTeam;
	}

	if (const AAirshipTurret* Turret = Cast<AAirshipTurret>(Target))
	{
		const AAirshipPawn* TurretShip = Turret->GetShip();
		return TurretShip && TurretShip->GetTeamId() != MyMatch::NoTeam;
	}

	return false;
}

int32 UMyTeamLibrary::GetTimeLimitLives(const FMyTeamState& Team)
{
	// The handicap makes up for the bigger team's firepower in fights (B1.2); counted at time-up it would also hand the
	// smaller team a match nobody fought (2v1: 4 lives against 3)
	return UMyMatchSettings::Get()->bTimeLimitCountsHandicap ? Team.LivesLeft : Team.LivesLeft - Team.BonusLives;
}

FLinearColor UMyTeamLibrary::GetTeamColor(uint8 TeamId)
{
	return TeamId < MyMatch::NumTeams ? UMyMatchSettings::Get()->TeamColors[TeamId] : FLinearColor(0.5f, 0.5f, 0.5f);
}

FText UMyTeamLibrary::GetTeamName(uint8 TeamId)
{
	return TeamId < MyMatch::NumTeams ? UMyMatchSettings::Get()->TeamNames[TeamId] : FText::GetEmpty();
}

// -----------------------------------------------------------------------------
// Lobby (SPEC_B_LOBBY 3.3, 4.7)
// -----------------------------------------------------------------------------

bool UMyTeamLibrary::IsInLobby(const UObject* WorldContext)
{
	const AMyGameState* GameState = MyTeamLibraryPrivate::GetGameState(WorldContext);
	return GameState && GameState->IsInLobby();
}

bool UMyTeamLibrary::IsLobbyCountingDown(const UObject* WorldContext)
{
	const AMyGameState* GameState = MyTeamLibraryPrivate::GetGameState(WorldContext);
	return GameState && GameState->IsLobbyCountingDown();
}

bool UMyTeamLibrary::AreShipsLocked(const UObject* WorldContext)
{
	return IsInLobby(WorldContext);
}

bool UMyTeamLibrary::IsDamageOff(const UObject* WorldContext)
{
	return IsInLobby(WorldContext) && !UMyMatchSettings::Get()->bLobbyDamage;
}

int32 UMyTeamLibrary::GetTeamModeMaxPlayers(EMyTeamMode Mode)
{
	switch (Mode)
	{
	case EMyTeamMode::OneVsOne: return 2;
	case EMyTeamMode::TwoVsTwo: return 4;
	default: return 0;
	}
}

bool UMyTeamLibrary::IsHardLobbyStartBlock(EMyLobbyStartBlock Block)
{
	switch (Block)
	{
	case EMyLobbyStartBlock::Arriving:
	case EMyLobbyStartBlock::Counting:
	case EMyLobbyStartBlock::Traveling:
	case EMyLobbyStartBlock::NeedOpponent:
		return true;
	case EMyLobbyStartBlock::NotReady:
		return UMyMatchSettings::Get()->bLobbyRequireReady;
	default:
		return false;
	}
}

FText UMyTeamLibrary::GetLobbyStartBlockText(const UObject* WorldContext, EMyLobbyStartBlock Block, int32 NotReady)
{
	const AMyGameState* GameState = MyTeamLibraryPrivate::GetGameState(WorldContext);
	const int32 Count0 = GameState ? GameState->GetTeamState(0).NumPlayers : 0;
	const int32 Count1 = GameState ? GameState->GetTeamState(1).NumPlayers : 0;
	const EMyTeamMode Mode = GetRules(WorldContext).TeamMode;

	switch (Block)
	{
	case EMyLobbyStartBlock::Arriving:
		return FText::Format(NSLOCTEXT("MyLobby", "BlockArriving", "Waiting for {0} {0}|plural(one=player,other=players) to load"),
			GameState ? GameState->CountArrivingPlayers() : 0);
	case EMyLobbyStartBlock::Counting:
		return NSLOCTEXT("MyLobby", "BlockCounting", "The match is starting");
	case EMyLobbyStartBlock::Traveling:
		return NSLOCTEXT("MyLobby", "BlockTraveling", "Loading the next round");
	case EMyLobbyStartBlock::NeedOpponent:
		return FText::Format(NSLOCTEXT("MyLobby", "BlockNeedOpponent", "{0} needs a player on {1}"),
			FText::FromString(GetTeamModeOption(Mode)), GetTeamName(Count0 == 0 ? 0 : 1));
	case EMyLobbyStartBlock::NotReady:
		return FText::Format(NSLOCTEXT("MyLobby", "BlockNotReady", "{0} not ready"), FMath::Max(1, NotReady));
	case EMyLobbyStartBlock::NeedTwoPerTeam:
		return FText::Format(NSLOCTEXT("MyLobby", "BlockNeedTwo", "2v2 with {0} and {1}: plays {0}v{1}"), Count0, Count1);
	case EMyLobbyStartBlock::Uneven:
		return FText::Format(NSLOCTEXT("MyLobby", "BlockUneven", "Teams uneven ({0} - {1})"), Count0, Count1);
	case EMyLobbyStartBlock::OneShip:
		return NSLOCTEXT("MyLobby", "BlockOneShip", "Everyone on one team: one ship");
	default:
		return FText::GetEmpty();
	}
}

const TCHAR* UMyTeamLibrary::GetMatchPhaseName(EMyMatchPhase Phase)
{
	switch (Phase)
	{
	case EMyMatchPhase::WaitingToStart: return TEXT("WaitingToStart");
	case EMyMatchPhase::Countdown: return TEXT("Countdown");
	case EMyMatchPhase::InProgress: return TEXT("InProgress");
	case EMyMatchPhase::Ended: return TEXT("Ended");
	case EMyMatchPhase::Lobby: return TEXT("Lobby");
	default: return TEXT("None");
	}
}

const TCHAR* UMyTeamLibrary::GetTeamModeOption(EMyTeamMode Mode)
{
	switch (Mode)
	{
	case EMyTeamMode::Practice: return TEXT("practice");
	case EMyTeamMode::OneVsOne: return TEXT("1v1");
	case EMyTeamMode::TwoVsTwo: return TEXT("2v2");
	default: return TEXT("auto");
	}
}
