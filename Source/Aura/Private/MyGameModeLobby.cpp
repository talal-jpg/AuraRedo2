// Fill out your copyright notice in the Description page of Project Settings.

// The in-level lobby of AMyGameMode (Docs/Airship/round2/SPEC_B_LOBBY.md, revision 2): phase Lobby on the match map,
// teams / ready / host rules, the lobby countdown (PR B's Countdown, forced, from the lobby) and the start in place, the
// seamless return to the lobby after a match, both arrival paths, the session tie-in. Server only; AMyGameState and
// AMyPlayerState replicate the state, AMyPlayerController2 carries the widget's requests.

#include "MyGameMode.h"

#include "AbilitySystemComponent.h"
#include "AbilitySystem/MyAbilitySystemComponent.h"
#include "AIController.h"
#include "EngineUtils.h"
#include "GameplayEffect.h"
#include "MyGameState.h"
#include "MyPlayerState.h"
#include "TimerManager.h"
#include "Actors/MyHexPlatform.h"
#include "Airship/AirshipPawn.h"
#include "Airship/AirshipSubsystem.h"
#include "Burrower/BurrowerSpawnSubsystem.h"
#include "Components/CapsuleComponent.h"
#include "Engine/PlayerStartPIE.h"
#include "EOS/MultiplayerSessionsSubsystem.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerStart.h"
#include "HAL/IConsoleManager.h"
#include "Interfaces/MyCombatInterface.h"
#include "Kismet/GameplayStatics.h"
#include "Match/MyLaneSubsystem.h"
#include "Match/MyMatchMemorySubsystem.h"
#include "Match/MyMatchSettings.h"
#include "Match/MyTeamLibrary.h"
#include "MechSwarm/Spawning/MechSentinelWaveSpawner.h"
#include "PlayerInput/MyPlayerController2.h"

// Named, not anonymous: the unity build compiles this file together with others (MyGameMode.cpp has its own helpers)
namespace MyGameModeLobby
{
	constexpr uint32 Bit(EMyLobbyStartBlock Block)
	{
		return 1u << static_cast<uint32>(Block);
	}

	/** The blocks in the order the UI shows them (the enum's order). */
	constexpr EMyLobbyStartBlock Order[] =
	{
		EMyLobbyStartBlock::Arriving, EMyLobbyStartBlock::Counting, EMyLobbyStartBlock::Traveling, EMyLobbyStartBlock::NeedOpponent,
		EMyLobbyStartBlock::NotReady, EMyLobbyStartBlock::NeedTwoPerTeam, EMyLobbyStartBlock::Uneven, EMyLobbyStartBlock::OneShip
	};

	EMyLobbyStartBlock First(uint32 Mask)
	{
		for (const EMyLobbyStartBlock Block : Order)
		{
			if (Mask & Bit(Block))
			{
				return Block;
			}
		}
		return EMyLobbyStartBlock::None;
	}

	FString BlockName(EMyLobbyStartBlock Block)
	{
		const UEnum* Enum = StaticEnum<EMyLobbyStartBlock>();
		return Enum ? Enum->GetNameStringByValue(static_cast<int64>(Block)) : FString::FromInt(static_cast<int32>(Block));
	}

	FString TeamLabel(uint8 TeamId)
	{
		return TeamId < MyMatch::NumTeams ? UMyTeamLibrary::GetTeamName(TeamId).ToString() : FString(TEXT("none"));
	}

	bool ParseBool(const FString& InValue, bool& bOut)
	{
		const FString Value = InValue.TrimStartAndEnd();

		if (Value == TEXT("1") || Value.Equals(TEXT("true"), ESearchCase::IgnoreCase) || Value.Equals(TEXT("on"), ESearchCase::IgnoreCase))
		{
			bOut = true;
			return true;
		}
		if (Value == TEXT("0") || Value.Equals(TEXT("false"), ESearchCase::IgnoreCase) || Value.Equals(TEXT("off"), ESearchCase::IgnoreCase))
		{
			bOut = false;
			return true;
		}
		return false;
	}

	bool IsDeadCharacter(AActor* Actor)
	{
		return Actor && Actor->Implements<UMyCombatInterface>() && IMyCombatInterface::Execute_IsDead(Actor);
	}

	FString BoxText(const FBox& Box)
	{
		return FString::Printf(TEXT("(%.0f, %.0f, %.0f)..(%.0f, %.0f, %.0f)"), Box.Min.X, Box.Min.Y, Box.Min.Z, Box.Max.X, Box.Max.Y, Box.Max.Z);
	}
}

// =============================================================================
// State
// =============================================================================

bool AMyGameMode::IsInLobby() const
{
	const AMyGameState* MyGameState = GetMatchGameState();
	return bMatchOn && MyGameState && MyGameState->IsInLobby();
}

bool AMyGameMode::IsLobbyCountingDown() const
{
	const AMyGameState* MyGameState = GetMatchGameState();
	return bMatchOn && MyGameState && MyGameState->IsLobbyCountingDown();
}

bool AMyGameMode::IsLobbyHost(const APlayerController* PC) const
{
	// The PostLogin test: the server's own local player (listen host, standalone)
	return PC && PC->IsLocalController() && GetNetMode() != NM_Client;
}

int32 AMyGameMode::GetLobbyMaxPlayers() const
{
	const int32 ModeMax = UMyTeamLibrary::GetTeamModeMaxPlayers(MatchRules.TeamMode);
	return ModeMax > 0 ? ModeMax : FMath::Max(1, ExpectedPlayers);
}

int32 AMyGameMode::GetNumLobbyBots() const
{
	int32 Count = 0;

	for (const TWeakObjectPtr<AController>& Bot : LobbyBots)
	{
		Count += Bot.IsValid() ? 1 : 0;
	}
	return Count;
}

const TCHAR* AMyGameMode::GetLobbyGroundName(EMyLobbyGround Ground)
{
	switch (Ground)
	{
	case EMyLobbyGround::PlayerStarts: return TEXT("PlayerStarts");
	case EMyLobbyGround::PathStart: return TEXT("PathStart");
	case EMyLobbyGround::Waiting: return TEXT("PathStart (waiting for the platform)");
	default: return TEXT("none (PlayerStart, fall catch only)");
	}
}

// =============================================================================
// L3 4.2: the decision (InitGame)
// =============================================================================

void AMyGameMode::DecideLobby(const FString& Options)
{
	// Later wins: the CVar Aura.Lobby.Enable (-1 = by URL), then the URL's Lobby=0|1. Play Solo, console opens and the
	// PR B harnesses have no Lobby option and keep the PR B flow
	bLobbyRound = false;
	LobbyReason = TEXT("no Lobby option");

	if (const IConsoleVariable* EnableCVar = IConsoleManager::Get().FindConsoleVariable(TEXT("Aura.Lobby.Enable")))
	{
		const int32 Enable = EnableCVar->GetInt();

		if (Enable >= 0)
		{
			bLobbyRound = Enable > 0;
			LobbyReason = FString::Printf(TEXT("Aura.Lobby.Enable %d"), Enable);
		}
	}

	if (UGameplayStatics::HasOption(Options, TEXT("Lobby")))
	{
		bool bUrlLobby = false;
		const FString Value = UGameplayStatics::ParseOption(Options, TEXT("Lobby"));

		if (MyGameModeLobby::ParseBool(Value, bUrlLobby))
		{
			bLobbyRound = bUrlLobby;
			LobbyReason = FString::Printf(TEXT("URL Lobby=%s"), *Value);
		}
		else
		{
			UE_LOG(LogMatch, Warning, TEXT("URL option Lobby=%s: use 0 or 1 (unchanged: %s)"), *Value, *LobbyReason);
		}
	}
}

// =============================================================================
// L2 3.1: where players stand
// =============================================================================

void AMyGameMode::ResolveLobbySpawn(EMyLobbySpawn Request)
{
	using namespace MyGameModeLobby;
	UWorld* World = GetWorld();
	const UMyMatchSettings* Settings = UMyMatchSettings::Get();

	LobbySpawnRequest = Request;
	LobbyZones.Reset();
	LobbyStarts.Reset();
	LobbyPlatform.Reset();
	LobbyGroundText.Reset();
	LobbyFallCatchZ = -UE_BIG_NUMBER;
	LobbyOutsideSince.Reset();
	bLobbyGroundReady = true;

	if (!World)
	{
		return;
	}

	// 1. PlayerStarts with ground a pawn could stand on: a capsule sweep straight down on the pawn channel with the
	// default pawn's capsule, ignoring pawns; a walkable normal, and FindTeleportSpot accepts the pawn there. Components
	// are registered before InitGame (World.cpp:5988, :6034), so this works from there
	if (Request != EMyLobbySpawn::PathStart)
	{
		FPawnFit Fit;
		const bool bHasFit = GetPawnFit(nullptr, Fit);
		const float Radius = bHasFit && Fit.Radius > 0.f ? Fit.Radius : 42.f;
		const float HalfHeight = bHasFit && Fit.HalfHeight > 0.f ? Fit.HalfHeight : 96.f;
		const FCollisionShape Capsule = FCollisionShape::MakeCapsule(Radius, HalfHeight);

		FCollisionQueryParams Params(SCENE_QUERY_STAT(LobbyGround), /*bTraceComplex=*/false);

		for (TActorIterator<APawn> It(World); It; ++It)
		{
			Params.AddIgnoredActor(*It);
		}

		static const FName LobbyTag(TEXT("Lobby"));
		TArray<APlayerStart*> Tagged;
		TArray<APlayerStart*> All;

		for (TActorIterator<APlayerStart> It(World); It; ++It)
		{
			if (It->IsA<APlayerStartPIE>())
			{
				continue;
			}
			(It->PlayerStartTag == LobbyTag ? Tagged : All).Add(*It);
		}

		const TArray<APlayerStart*>& Candidates = Tagged.Num() > 0 ? Tagged : All;
		TArray<const AActor*> GroundActors;

		for (APlayerStart* Start : Candidates)
		{
			const FVector From = Start->GetActorLocation();
			const FVector To = From - FVector(0.0, 0.0, Settings->LobbyGroundTraceDepth);
			FHitResult Hit;

			if (!World->SweepSingleByChannel(Hit, From, To, FQuat::Identity, ECC_Pawn, Capsule, Params) || !Hit.bBlockingHit
				|| Hit.ImpactNormal.Z < Settings->LobbyGroundMinNormalZ || !Hit.GetActor())
			{
				continue;
			}

			FVector Stand = Hit.Location + FVector(0.0, 0.0, 2.0);

			if (bHasFit && !World->FindTeleportSpot(Fit.PawnToFit, Stand, Start->GetActorRotation()))
			{
				continue;
			}

			LobbyStarts.Add(Start);
			GroundActors.AddUnique(Hit.GetActor());
		}

		for (const AActor* Ground : GroundActors)
		{
			SetLobbyZoneAround(Ground);
		}

		if (LobbyStarts.Num() > 0)
		{
			// The placed platform above the floor (no SplineDistance) is part of the lobby without naming it: every
			// platform without SplineDistance whose XY bounds overlap a zone box is merged into it (inferred: its pillars
			// at z 1678 are inside the box)
			TArray<FString> Merged;

			for (TActorIterator<AMyHexPlatform> It(World); It; ++It)
			{
				AMyHexPlatform* Platform = *It;

				if (!IsValid(Platform) || Platform->HasSplineDistance())
				{
					continue;
				}

				FBox Bounds = Platform->GetComponentsBoundingBox(true);

				if (!Bounds.IsValid)
				{
					Bounds = FBox(Platform->GetActorLocation(), Platform->GetActorLocation());
				}

				for (FBox& Zone : LobbyZones)
				{
					const bool bOverlapXY = Bounds.Min.X <= Zone.Max.X && Bounds.Max.X >= Zone.Min.X && Bounds.Min.Y <= Zone.Max.Y && Bounds.Max.Y >= Zone.Min.Y;

					if (bOverlapXY)
					{
						Zone += FBox(Bounds.Min - FVector(Settings->LobbyZoneMargin, Settings->LobbyZoneMargin, 0.0),
							Bounds.Max + FVector(Settings->LobbyZoneMargin, Settings->LobbyZoneMargin, Settings->LobbyZoneHeight));
						Merged.Add(Platform->GetName());
						break;
					}
				}
			}

			TArray<FString> GroundNames;

			for (const AActor* Ground : GroundActors)
			{
				GroundNames.Add(Ground->GetName());
			}

			LobbyGround = EMyLobbyGround::PlayerStarts;
			LobbyGroundText = FString::Join(GroundNames, TEXT(", ")) + (Merged.Num() > 0 ? FString::Printf(TEXT(" (+ %s)"), *FString::Join(Merged, TEXT(", "))) : FString());

			TArray<FString> ZoneTexts;

			for (const FBox& Zone : LobbyZones)
			{
				ZoneTexts.Add(BoxText(Zone));
			}

			UE_LOG(LogMatch, Log, TEXT("Lobby: spawn PlayerStarts, ground %s, %d start(s), zone %s"), *LobbyGroundText, LobbyStarts.Num(),
				*FString::Join(ZoneTexts, TEXT(" ")));
			return;
		}

		if (Request == EMyLobbySpawn::PlayerStarts)
		{
			UE_LOG(LogMatch, Warning, TEXT("Lobby: LobbySpawn PlayerStarts, but no PlayerStart has walkable ground under it"));
			SetLobbyGroundNone();
			return;
		}
	}

	// 2. PathStart: the path platform with the smallest SplineDistance that has tiles (the case once the floor is gone).
	// The PCG may build it over several frames: pawns are held until it exists, LobbyTick polls
	if (AMyHexPlatform* First = FindFirstPathPlatform())
	{
		LobbyGround = EMyLobbyGround::PathStart;
		LobbyPlatform = First;
		SetLobbyZoneAround(First);
		LobbyGroundText = First->GetName();
		UE_LOG(LogMatch, Log, TEXT("Lobby: spawn PathStart, ground %s (SplineDistance %.0f), zone %s"), *LobbyGroundText, First->GetSplineDistance(),
			LobbyZones.Num() > 0 ? *BoxText(LobbyZones[0]) : TEXT("none"));
		return;
	}

	LobbyGround = EMyLobbyGround::Waiting;
	bLobbyGroundReady = false;
	UE_LOG(LogMatch, Log, TEXT("Lobby: spawn PathStart, waiting up to %.0f s for the path's first platform"), Settings->LobbyPathStartWait);
}

void AMyGameMode::SetLobbyZoneAround(const AActor* Ground)
{
	if (!Ground)
	{
		return;
	}

	const UMyMatchSettings* Settings = UMyMatchSettings::Get();
	FBox Bounds = Ground->GetComponentsBoundingBox(true);

	if (!Bounds.IsValid)
	{
		Bounds = FBox(Ground->GetActorLocation(), Ground->GetActorLocation());
	}

	// The ground's box grown in X and Y, from its top minus the depth to its top plus the height
	const double Top = Bounds.Max.Z;
	LobbyZones.Add(FBox(FVector(Bounds.Min.X - Settings->LobbyZoneMargin, Bounds.Min.Y - Settings->LobbyZoneMargin, Top - Settings->LobbyZoneDepth),
		FVector(Bounds.Max.X + Settings->LobbyZoneMargin, Bounds.Max.Y + Settings->LobbyZoneMargin, Top + Settings->LobbyZoneHeight)));
}

void AMyGameMode::SetLobbyGroundNone()
{
	// 3. Nothing found: the PlayerStart, no zone (no zone teleport), only a fall catch below it
	LobbyGround = EMyLobbyGround::None;
	LobbyZones.Reset();
	LobbyStarts.Reset();
	LobbyPlatform.Reset();
	LobbyGroundText = TEXT("none");
	bLobbyGroundReady = true;

	const APlayerStart* Start = nullptr;

	for (TActorIterator<APlayerStart> It(GetWorld()); It && !Start; ++It)
	{
		if (!It->IsA<APlayerStartPIE>())
		{
			Start = *It;
		}
	}

	LobbyFallCatchZ = Start ? Start->GetActorLocation().Z - UMyMatchSettings::Get()->LobbyZoneDepth : -UE_BIG_NUMBER;
	UE_LOG(LogMatch, Warning, TEXT("Lobby: no ground under any PlayerStart and no path platform: the PlayerStart with a fall catch below z %.0f"),
		LobbyFallCatchZ);
}

AMyHexPlatform* AMyGameMode::FindFirstPathPlatform() const
{
	AMyHexPlatform* Best = nullptr;

	for (TActorIterator<AMyHexPlatform> It(GetWorld()); It; ++It)
	{
		AMyHexPlatform* Platform = *It;

		if (IsValid(Platform) && Platform->HasSplineDistance() && Platform->GetTileInfos().Num() > 0
			&& (!Best || Platform->GetSplineDistance() < Best->GetSplineDistance()))
		{
			Best = Platform;
		}
	}

	return Best;
}

bool AMyGameMode::GetLobbySpot(AController* Controller, const FPawnFit& Fit, FRespawnSpot& OutSpot)
{
	UWorld* World = GetWorld();

	if (!World || !Fit.PawnToFit)
	{
		return false;
	}

	if (LobbyGround == EMyLobbyGround::PathStart)
	{
		AMyHexPlatform* Platform = LobbyPlatform.Get();

		if (!IsValid(Platform))
		{
			return false;
		}

		// Facing along the path
		const UMyLaneSubsystem* Lanes = UMyLaneSubsystem::Get(this);
		const double Yaw = Lanes && Lanes->HasLanes() ? static_cast<double>(Lanes->GetStartYaw()) : Platform->GetActorRotation().Yaw;
		return FindRespawnTile(Platform, Fit, FRotator(0.0, Yaw, 0.0), Controller, OutSpot);
	}

	// PlayerStarts: the lobby starts in turn, each one and a ring around it (250 / 500 / 750 cm, 8 directions); none: the
	// first PlayerStart the same way
	TArray<APlayerStart*> Starts;

	for (const TWeakObjectPtr<APlayerStart>& WeakStart : LobbyStarts)
	{
		if (APlayerStart* Start = WeakStart.Get())
		{
			Starts.Add(Start);
		}
	}

	if (Starts.IsEmpty())
	{
		for (TActorIterator<APlayerStart> It(World); It && Starts.IsEmpty(); ++It)
		{
			if (!It->IsA<APlayerStartPIE>())
			{
				Starts.Add(*It);
			}
		}
	}

	for (int32 Try = 0; Try < Starts.Num(); ++Try)
	{
		const APlayerStart* Start = Starts[(LobbySpotCounter + Try) % Starts.Num()];
		const FRotator Rotation(0.0, Start->GetActorRotation().Yaw, 0.0);

		for (const float Radius : { 0.f, 250.f, 500.f, 750.f })
		{
			for (int32 Direction = 0; Direction < (Radius > 0.f ? 8 : 1); ++Direction)
			{
				FVector Location = Start->GetActorLocation() + FRotator(0.0, Direction * 45.0, 0.0).Vector() * Radius;

				if (!World->FindTeleportSpot(Fit.PawnToFit, Location, Rotation))
				{
					continue;
				}

				++LobbySpotCounter;
				OutSpot = FRespawnSpot();
				OutSpot.PawnTransform = FTransform(Rotation, Location);
				OutSpot.GroundLocation = Location - FVector(0.f, 0.f, Fit.HalfHeight);
				return true;
			}
		}
	}

	return false;
}

void AMyGameMode::SendToLobbySpot(AController* Controller, ACharacter* Character, const TCHAR* Why, bool bMessage)
{
	FPawnFit Fit;
	FRespawnSpot Spot;

	if (!Controller || !IsValid(Character) || !GetPawnFit(Controller, Fit) || !GetLobbySpot(Controller, Fit, Spot))
	{
		UE_LOG(LogMatch, Warning, TEXT("Lobby: no lobby spot for %s (%s)"), *GetNameSafe(Controller ? Controller->PlayerState : nullptr), Why);
		return;
	}

	// Ends a grapple's root motion and the like, then the move
	CancelActiveAbilities(Controller, Character);

	if (UCharacterMovementComponent* Movement = Character->GetCharacterMovement())
	{
		Movement->StopMovementImmediately();
	}

	const FRotator Rotation = Spot.PawnTransform.Rotator();

	if (!Character->TeleportTo(Spot.PawnTransform.GetLocation(), Rotation))
	{
		Character->SetActorLocationAndRotation(Spot.PawnTransform.GetLocation(), Rotation, false, nullptr, ETeleportType::TeleportPhysics);
	}

	if (APlayerController* PC = Cast<APlayerController>(Controller))
	{
		PC->ClientSetRotation(Rotation);
	}

	if (bMessage)
	{
		SendLobbyMessage(Controller, NSLOCTEXT("MyLobby", "StayInLobby", "Stay in the lobby: the match starts when the host presses Start"));
	}

	UE_LOG(LogMatch, Log, TEXT("Lobby: %s back to the lobby (%s) at %s"), *GetNameSafe(Controller->PlayerState), Why, *Spot.PawnTransform.GetLocation().ToCompactString());
}

void AMyGameMode::SendLobbyPawnsToSpots()
{
	if (!IsInLobby())
	{
		return;
	}

	if (!bLobbyGroundReady)
	{
		bLobbySendPawnsWhenReady = true;
		return;
	}

	bLobbySendPawnsWhenReady = false;

	for (FConstPlayerControllerIterator It = GetWorld()->GetPlayerControllerIterator(); It; ++It)
	{
		APlayerController* PC = It->Get();

		if (ACharacter* Character = PC ? Cast<ACharacter>(PC->GetPawn()) : nullptr)
		{
			SendToLobbySpot(PC, Character, TEXT("Aura.Lobby.Resolve"), false);
		}
	}

	SpawnLobbyPlayers();
}

void AMyGameMode::SpawnLobbyPlayers()
{
	for (FConstPlayerControllerIterator It = GetWorld()->GetPlayerControllerIterator(); It; ++It)
	{
		APlayerController* PC = It->Get();

		// PlayerCanRestart also waits for a client still loading the world (SPEC_B_LOBBY 5.4 row 13)
		if (!PC || PC->GetPawn() || PendingRespawns.Contains(PC) || MustSpectate(PC) || !PlayerCanRestart(PC))
		{
			continue;
		}

		RestartPlayer(PC);
	}
}

// =============================================================================
// L3 4.7: the lobby begins (StartPlay), the lobby tick
// =============================================================================

void AMyGameMode::BeginLobby()
{
	AMyGameState* MyGameState = GetMatchGameState();

	if (!MyGameState)
	{
		return;
	}

	// After Super::StartPlay: the wave spawners armed themselves in their BeginPlay. Only those that run now are resumed at
	// the round start (StartWaves would start a never-armed one from wave 1)
	LobbyStoppedSpawners.Reset();

	for (TActorIterator<AMechSentinelWaveSpawner> It(GetWorld()); It; ++It)
	{
		if (IsValid(*It) && !It->IsStopped())
		{
			LobbyStoppedSpawners.Add(*It);
		}
	}

	StopSwarm();
	MyGameState->SetInLobby(true);
	MyGameState->SetLobbyRound(true);
	MyGameState->SetMatchPhase(EMyMatchPhase::Lobby, 0.0);
	LobbyStartServerTime = GetServerTime();
	GetWorldTimerManager().SetTimer(LobbyTickTimer, this, &ThisClass::LobbyTick, 0.25f, true);

	UE_LOG(LogMatch, Log, TEXT("Match: phase Lobby (%s, max players %d, round %d, spawn %s%s)"), UMyTeamLibrary::GetTeamModeOption(MatchRules.TeamMode),
		GetLobbyMaxPlayers(), RoundIndex, GetLobbyGroundName(LobbyGround), LobbyGroundText.IsEmpty() ? TEXT("") : *FString::Printf(TEXT(", ground %s"), *LobbyGroundText));

	AdvertiseIfHosting(/*bInMatch=*/false);
	SpawnLobbyPlayers();
	EvaluateTeams();
}

void AMyGameMode::LobbyTick()
{
	if (!bMatchOn || !IsInLobby() || bRestarting)
	{
		return;
	}

	if (LobbyGround == EMyLobbyGround::Waiting)
	{
		PollLobbyGround();
	}

	UpdateLobbyZone();
	UpdateLobbyState();
}

void AMyGameMode::PollLobbyGround()
{
	const double Waited = GetServerTime() - LobbyStartServerTime;

	if (AMyHexPlatform* First = FindFirstPathPlatform())
	{
		LobbyGround = EMyLobbyGround::PathStart;
		LobbyPlatform = First;
		LobbyZones.Reset();
		SetLobbyZoneAround(First);
		LobbyGroundText = First->GetName();
		bLobbyGroundReady = true;
		UE_LOG(LogMatch, Log, TEXT("Lobby: spawn PathStart, ground %s (SplineDistance %.0f) after %.1f s, zone %s"), *LobbyGroundText,
			First->GetSplineDistance(), Waited, LobbyZones.Num() > 0 ? *MyGameModeLobby::BoxText(LobbyZones[0]) : TEXT("none"));
	}
	else if (Waited >= UMyMatchSettings::Get()->LobbyPathStartWait)
	{
		SetLobbyGroundNone();
	}
	else
	{
		return;
	}

	if (bLobbySendPawnsWhenReady)
	{
		SendLobbyPawnsToSpots();
	}
	else
	{
		SpawnLobbyPlayers();
	}
}

void AMyGameMode::UpdateLobbyZone()
{
	const AMyGameState* MyGameState = GetMatchGameState();
	const UMyMatchSettings* Settings = UMyMatchSettings::Get();

	if (!MyGameState || !bLobbyGroundReady)
	{
		return;
	}

	const double Now = GetServerTime();

	for (auto It = LobbyOutsideSince.CreateIterator(); It; ++It)
	{
		if (!It.Key().IsValid())
		{
			It.RemoveCurrent();
		}
	}

	// Each arrived player's own living character (the UpdateFallDeaths loop shape); a seated pilot's pawn is his ship
	for (const APlayerState* PlayerState : MyGameState->PlayerArray)
	{
		const AMyPlayerState* MyPlayerState = Cast<AMyPlayerState>(PlayerState);
		ACharacter* Character = MyPlayerState && !MyPlayerState->IsArriving() ? Cast<ACharacter>(MyPlayerState->GetPawn()) : nullptr;
		AController* Controller = Character ? Character->GetController() : nullptr;

		if (!IsValid(Character) || !Controller || Character->IsActorBeingDestroyed() || MyGameModeLobby::IsDeadCharacter(Character))
		{
			continue;
		}

		const FVector Location = Character->GetActorLocation();

		// No zone (3.1 step 3): only the fall catch, at once
		if (LobbyZones.IsEmpty())
		{
			if (Location.Z < LobbyFallCatchZ)
			{
				SendToLobbySpot(Controller, Character, TEXT("fell"), true);
			}
			continue;
		}

		bool bInside = false;

		for (const FBox& Zone : LobbyZones)
		{
			bInside |= Zone.IsInsideOrOn(Location);
		}

		if (bInside)
		{
			LobbyOutsideSince.Remove(Character);
			continue;
		}

		const double* Since = LobbyOutsideSince.Find(Character);

		if (!Since)
		{
			LobbyOutsideSince.Add(Character, Now);
			continue;
		}

		if (Now - *Since < Settings->LobbyZoneGraceSeconds)
		{
			continue;
		}

		LobbyOutsideSince.Remove(Character);
		SendToLobbySpot(Controller, Character, TEXT("left the zone"), true);
	}
}

// =============================================================================
// L3 4.7: start blocks
// =============================================================================

int32 AMyGameMode::CountLobbyPlayers(const APlayerState* Leaving) const
{
	const AMyGameState* MyGameState = GetMatchGameState();
	int32 Count = 0;

	if (MyGameState)
	{
		for (const APlayerState* PlayerState : MyGameState->PlayerArray)
		{
			const AMyPlayerState* MyPlayerState = Cast<AMyPlayerState>(PlayerState);

			if (MyPlayerState && MyPlayerState != Leaving && !MyPlayerState->IsActorBeingDestroyed() && !MyPlayerState->IsOnlyASpectator()
				&& !MyPlayerState->IsArriving() && MyPlayerState->GetTeamId() < MyMatch::NumTeams)
			{
				++Count;
			}
		}
	}

	return Count;
}

uint32 AMyGameMode::GetLobbyStartBlocks(int32& OutNotReady, const APlayerState* Leaving) const
{
	using namespace MyGameModeLobby;
	OutNotReady = 0;
	const AMyGameState* MyGameState = GetMatchGameState();

	if (!MyGameState)
	{
		return 0;
	}

	int32 Count[MyMatch::NumTeams] = {};
	int32 NumArriving = 0;

	for (const APlayerState* PlayerState : MyGameState->PlayerArray)
	{
		const AMyPlayerState* MyPlayerState = Cast<AMyPlayerState>(PlayerState);

		if (!MyPlayerState || MyPlayerState == Leaving || MyPlayerState->IsActorBeingDestroyed() || MyPlayerState->IsOnlyASpectator())
		{
			continue;
		}

		if (MyPlayerState->IsArriving())
		{
			++NumArriving;
			continue;
		}

		if (MyPlayerState->GetTeamId() < MyMatch::NumTeams)
		{
			++Count[MyPlayerState->GetTeamId()];
		}

		if (!MyPlayerState->IsHost() && !MyPlayerState->IsLobbyReady())
		{
			++OutNotReady;
		}
	}

	uint32 Mask = 0;
	const UMyMatchSettings* Settings = UMyMatchSettings::Get();

	if (NumArriving > 0 && GetServerTime() - LobbyStartServerTime < Settings->LobbyArrivalTimeout)
	{
		Mask |= Bit(EMyLobbyStartBlock::Arriving);
	}

	if (MyGameState->IsLobbyCountingDown())
	{
		Mask |= Bit(EMyLobbyStartBlock::Counting);
	}

	if (bRestarting)
	{
		Mask |= Bit(EMyLobbyStartBlock::Traveling);
	}

	if (OutNotReady > 0)
	{
		Mask |= Bit(EMyLobbyStartBlock::NotReady);
	}

	// Practice: everyone on one ship, nothing about the teams blocks it
	const EMyTeamMode Mode = MatchRules.TeamMode;

	if (Mode == EMyTeamMode::Practice)
	{
		return Mask;
	}

	const bool bTeamEmpty = Count[0] == 0 || Count[1] == 0;

	if ((Mode == EMyTeamMode::OneVsOne || Mode == EMyTeamMode::TwoVsTwo) && bTeamEmpty)
	{
		Mask |= Bit(EMyLobbyStartBlock::NeedOpponent);
	}

	if (Mode == EMyTeamMode::TwoVsTwo && (Count[0] == 1 || Count[1] == 1))
	{
		Mask |= Bit(EMyLobbyStartBlock::NeedTwoPerTeam);
	}

	if (FMath::Abs(Count[0] - Count[1]) > 1)
	{
		Mask |= Bit(EMyLobbyStartBlock::Uneven);
	}

	if (Mode == EMyTeamMode::Auto && Count[0] + Count[1] >= 2 && bTeamEmpty)
	{
		Mask |= Bit(EMyLobbyStartBlock::OneShip);
	}

	return Mask;
}

EMyLobbyStartBlock AMyGameMode::GetLobbyStartBlock(int32& OutNotReady) const
{
	return MyGameModeLobby::First(GetLobbyStartBlocks(OutNotReady));
}

EMyLobbyStartBlock AMyGameMode::GetLobbyConfirmBlock(uint32 Mask, bool bRematch)
{
	using namespace MyGameModeLobby;
	uint32 Soft = 0;

	for (const EMyLobbyStartBlock Block : Order)
	{
		if ((Mask & Bit(Block)) && !UMyTeamLibrary::IsHardLobbyStartBlock(Block))
		{
			Soft |= Bit(Block);
		}
	}

	// A rematch with the same players on the same teams: the host accepted these teams last match (Q-L4 default)
	if (bRematch)
	{
		Soft &= ~Bit(EMyLobbyStartBlock::NotReady);
	}

	return First(Soft);
}

bool AMyGameMode::ComputeLobbyRematch(const APlayerState* Leaving) const
{
	// The same players on the same teams as the match the host just played: he accepted these teams then. Needs valid
	// net ids (the match memory), so PIE with the NULL subsystem never has it
	const UMyMatchMemorySubsystem* Memory = UMyMatchMemorySubsystem::Get(this);
	const AMyGameState* MyGameState = GetMatchGameState();

	if (!bLobbyFromRound || !Memory || Memory->GetNumRemembered() == 0 || !MyGameState)
	{
		return false;
	}

	int32 Found = 0;

	for (const APlayerState* PlayerState : MyGameState->PlayerArray)
	{
		const AMyPlayerState* MyPlayerState = Cast<AMyPlayerState>(PlayerState);

		if (!MyPlayerState || MyPlayerState == Leaving || MyPlayerState->IsActorBeingDestroyed() || MyPlayerState->IsOnlyASpectator()
			|| MyPlayerState->GetTeamId() >= MyMatch::NumTeams)
		{
			continue;
		}

		uint8 Remembered = MyMatch::NoTeam;

		if (MyPlayerState->IsArriving() || !Memory->FindTeam(MyPlayerState->GetUniqueId(), Remembered) || Remembered != MyPlayerState->GetTeamId())
		{
			return false;
		}

		++Found;
	}

	return Found > 0 && Found == Memory->GetNumRemembered();
}

void AMyGameMode::UpdateLobbyState(const APlayerState* Leaving)
{
	AMyGameState* MyGameState = GetMatchGameState();

	if (!bMatchOn || !MyGameState || !MyGameState->IsInLobby())
	{
		return;
	}

	int32 NotReady = 0;
	const uint32 Mask = GetLobbyStartBlocks(NotReady, Leaving);
	const EMyLobbyStartBlock Block = MyGameModeLobby::First(Mask);
	const EMyLobbyStartBlock OldBlock = MyGameState->GetLobbyStartBlock();
	const bool bRematch = ComputeLobbyRematch(Leaving);
	// The widget's confirm decision: the same soft block StartFromLobby refuses without bForce (the first block alone is
	// not enough: a rematch drops NotReady, and a soft block after it still needs the second click)
	MyGameState->SetLobbyStartBlock(Block, NotReady, GetLobbyConfirmBlock(Mask, bRematch));
	MyGameState->SetLobbyRematch(bRematch);

	if (Block != OldBlock)
	{
		UE_LOG(LogMatch, Log, TEXT("Lobby: start block %s (%d not ready, BLUE %d / ORANGE %d)"), *MyGameModeLobby::BlockName(Block), NotReady,
			MyGameState->GetTeamState(0).NumPlayers, MyGameState->GetTeamState(1).NumPlayers);
	}
}

// =============================================================================
// L3 4.7: start and cancel
// =============================================================================

bool AMyGameMode::StartFromLobby(bool bForce, FText& OutWhy)
{
	using namespace MyGameModeLobby;
	const UMyMatchSettings* Settings = UMyMatchSettings::Get();
	AMyGameState* MyGameState = GetMatchGameState();

	if (!bMatchOn || !MyGameState || GetPhase() != EMyMatchPhase::Lobby || !IsInLobby())
	{
		OutWhy = IsLobbyCountingDown() ? NSLOCTEXT("MyLobby", "AlreadyStarting", "The match is already starting")
			: NSLOCTEXT("MyLobby", "StartLobbyOnly", "Start works in the lobby only");
		return false;
	}

	if (GetNumLobbyBots() > 0)
	{
		OutWhy = NSLOCTEXT("MyLobby", "StartBots", "Remove the test bots first (Aura.Lobby.Bots 0)");
		UE_LOG(LogMatch, Log, TEXT("Lobby: start refused (%s)"), *OutWhy.ToString());
		return false;
	}

	RecountTeams();
	int32 NotReady = 0;
	const uint32 Mask = GetLobbyStartBlocks(NotReady);

	for (const EMyLobbyStartBlock Block : Order)
	{
		if (!(Mask & Bit(Block)))
		{
			continue;
		}

		if (UMyTeamLibrary::IsHardLobbyStartBlock(Block))
		{
			OutWhy = UMyTeamLibrary::GetLobbyStartBlockText(this, Block, NotReady);
			UE_LOG(LogMatch, Log, TEXT("Lobby: start refused, %s (%s)"), *BlockName(Block), *OutWhy.ToString());
			return false;
		}
	}

	const EMyLobbyStartBlock Confirm = GetLobbyConfirmBlock(Mask, MyGameState->IsLobbyRematch());

	if (Confirm != EMyLobbyStartBlock::None && !bForce)
	{
		const EMyLobbyStartBlock Block = Confirm;
		OutWhy = FText::Format(NSLOCTEXT("MyLobby", "StartConfirm", "{0} - click again to start anyway"), UMyTeamLibrary::GetLobbyStartBlockText(this, Block, NotReady));
		UE_LOG(LogMatch, Log, TEXT("Lobby: start needs the host's second click, %s (%s)"), *BlockName(Block), *OutWhy.ToString());
		return false;
	}

	UE_LOG(LogMatch, Log, TEXT("Lobby: the host starts (%s, BLUE %d / ORANGE %d, %d not ready%s%s)"), UMyTeamLibrary::GetTeamModeOption(MatchRules.TeamMode),
		MyGameState->GetTeamState(0).NumPlayers, MyGameState->GetTeamState(1).NumPlayers, NotReady, Confirm != EMyLobbyStartBlock::None ? TEXT(", soft blocks overridden") : TEXT(""),
		MyGameState->IsLobbyRematch() ? TEXT(", rematch") : TEXT(""));

	// PR B's countdown, forced, from the lobby: active teams, sides, handicap, lives and ships now; bInLobby stays on, so
	// the zone, damage off, the ship locks and the ranking gate hold for the 5 s (SPEC_B_LOBBY 4.7, D9)
	StartCountdown(/*bForced=*/true, Settings->LobbyCountdownSeconds, /*bFromLobby=*/true);
	UpdateLobbyState();
	return true;
}

bool AMyGameMode::CancelLobbyStart(const FString& Reason, EMyLobbyStartBlock Cause)
{
	AMyGameState* MyGameState = GetMatchGameState();

	if (!MyGameState || !IsLobbyCountingDown())
	{
		return false;
	}

	GetWorldTimerManager().ClearTimer(CountdownTimer);

	// A claimed placed ship goes back to being free, a spawned one is destroyed; no life counted
	for (uint8 Team = 0; Team < MyMatch::NumTeams; ++Team)
	{
		RemoveTeamShip(Team, TEXT("lobby start cancelled"));
		MyGameState->EditTeam(Team).bActive = false;
	}

	// The lobby shows no lives: both teams inactive again (no handicap, 0 lives)
	UpdateHandicap();
	ResetTeamsForRound();
	bCountdownVersus = false;
	bHostForcedStart = false;
	bPracticeToVersus = false;
	MyGameState->SetMatchPhase(EMyMatchPhase::Lobby, 0.0);
	MyGameState->MarkTeamsDirty();
	MyGameState->MulticastMatchEvent(EMyMatchEvent::LobbyCancelled, MyMatch::NoTeam, static_cast<int32>(Cause));
	UE_LOG(LogMatch, Log, TEXT("Lobby: start cancelled (%s: %s), back to phase Lobby"), *Reason, *MyGameModeLobby::BlockName(Cause));

	// The countdown held every new pawn (IsHoldingPawns) and dropped every respawn (ScheduleRespawn, RespawnPlayer): a
	// player who joined, finished loading or died during it gets his lobby pawn now. A dead pawn stays possessed until
	// RespawnPlayer replaces it; a missing one comes from SpawnLobbyPlayers (or PollLobbyGround while PathStart waits)
	int32 NumRespawns = 0;

	for (FConstPlayerControllerIterator It = GetWorld()->GetPlayerControllerIterator(); It; ++It)
	{
		APlayerController* PC = It->Get();

		if (PC && !PC->IsActorBeingDestroyed() && !PendingRespawns.Contains(PC) && MyGameModeLobby::IsDeadCharacter(PC->GetPawn()))
		{
			ScheduleRespawn(PC);
			NumRespawns += PendingRespawns.Contains(PC) ? 1 : 0;
		}
	}

	const int32 NumPawnsBefore = GetNumPlayerPawns();
	SpawnLobbyPlayers();
	const int32 NumSpawned = GetNumPlayerPawns() - NumPawnsBefore;

	if (NumRespawns > 0 || NumSpawned > 0)
	{
		UE_LOG(LogMatch, Log, TEXT("Lobby: after the cancel %d lobby pawn(s) spawned, %d respawn(s) scheduled"), NumSpawned, NumRespawns);
	}

	UpdateLobbyState();
	return true;
}

int32 AMyGameMode::GetNumPlayerPawns() const
{
	int32 Count = 0;

	for (FConstPlayerControllerIterator It = GetWorld()->GetPlayerControllerIterator(); It; ++It)
	{
		Count += (It->Get() && It->Get()->GetPawn()) ? 1 : 0;
	}
	return Count;
}

// =============================================================================
// L3 4.4, 4.5: teams and ready
// =============================================================================

void AMyGameMode::MoveLobbyTeam(AMyPlayerState* Player, uint8 Target, const TCHAR* Why)
{
	AMyGameState* MyGameState = GetMatchGameState();

	if (!Player || !MyGameState || Target >= MyMatch::NumTeams)
	{
		return;
	}

	// The ready flag stays: a team move isn't a rules change
	const uint8 From = Player->GetTeamId();
	Player->SetTeamId(Target);
	Player->SetRequestedTeam(MyMatch::NoTeam);
	RecountTeams();
	MyGameState->MulticastMatchEvent(EMyMatchEvent::LobbyTeamChanged, Target, Player->GetPlayerId());
	UE_LOG(LogMatch, Log, TEXT("Lobby: %s %s -> %s (%s), teams %d / %d"), *Player->GetPlayerName(), *MyGameModeLobby::TeamLabel(From),
		*MyGameModeLobby::TeamLabel(Target), Why, MyGameState->GetTeamState(0).NumPlayers, MyGameState->GetTeamState(1).NumPlayers);
	EvaluateTeams();
}

bool AMyGameMode::RequestLobbyTeam(AMyPlayerState* Player, uint8 Target, FText& OutWhy)
{
	using namespace MyGameModeLobby;
	AMyGameState* MyGameState = GetMatchGameState();

	if (!bMatchOn || !Player || !MyGameState || Player->IsArriving() || Player->IsOnlyASpectator())
	{
		return false;
	}

	if (!IsInLobby() || IsLobbyCountingDown())
	{
		OutWhy = NSLOCTEXT("MyLobby", "TeamsLocked", "Teams are locked while the match starts");
		return false;
	}

	if (!UMyMatchSettings::Get()->bLobbyTeamSwitch)
	{
		OutWhy = NSLOCTEXT("MyLobby", "SwitchOff", "Team switching is off");
		return false;
	}

	if (MatchRules.TeamMode == EMyTeamMode::Practice)
	{
		OutWhy = NSLOCTEXT("MyLobby", "PracticeOneShip", "Practice: everyone is on one ship");
		return false;
	}

	const uint8 From = Player->GetTeamId();

	if (From >= MyMatch::NumTeams)
	{
		return false;
	}

	// Cancel
	if (Target == From || Target >= MyMatch::NumTeams)
	{
		if (Player->GetRequestedTeam() != MyMatch::NoTeam)
		{
			Player->SetRequestedTeam(MyMatch::NoTeam);
			UE_LOG(LogMatch, Log, TEXT("Lobby: %s cancels the switch request"), *Player->GetPlayerName());
		}
		return true;
	}

	RecountTeams();
	const int32 CountFrom = MyGameState->GetTeamState(From).NumPlayers;
	const int32 CountTarget = MyGameState->GetTeamState(Target).NumPlayers;
	const int32 Cap = GetTeamCap();

	// The teams stay within one
	if ((Cap == 0 || CountTarget < Cap) && CountTarget < CountFrom)
	{
		MoveLobbyTeam(Player, Target, TEXT("switch"));
		return true;
	}

	// A swap with the oldest request for his team
	AMyPlayerState* Other = nullptr;

	for (APlayerState* PlayerState : MyGameState->PlayerArray)
	{
		AMyPlayerState* Candidate = Cast<AMyPlayerState>(PlayerState);

		if (Candidate && Candidate != Player && !Candidate->IsArriving() && Candidate->GetTeamId() == Target && Candidate->GetRequestedTeam() == From
			&& (!Other || Candidate->GetRequestServerTime() < Other->GetRequestServerTime()))
		{
			Other = Candidate;
		}
	}

	if (Other)
	{
		MoveLobbyTeam(Other, From, TEXT("swap"));
		MoveLobbyTeam(Player, Target, TEXT("swap"));
		SendLobbyMessage(Other->GetOwningController(), FText::Format(NSLOCTEXT("MyLobby", "Swapped", "Swapped with {0}: you are {1} now"),
			FText::FromString(Player->GetPlayerName()), UMyTeamLibrary::GetTeamName(From)));
		OutWhy = FText::Format(NSLOCTEXT("MyLobby", "SwappedSelf", "Swapped with {0}: you are {1} now"), FText::FromString(Other->GetPlayerName()),
			UMyTeamLibrary::GetTeamName(Target));
		return true;
	}

	Player->SetRequestedTeam(Target, GetServerTime());
	OutWhy = FText::Format(NSLOCTEXT("MyLobby", "SwitchPending", "You swap when an {0} player asks for {1}"), UMyTeamLibrary::GetTeamName(Target),
		UMyTeamLibrary::GetTeamName(From));
	UE_LOG(LogMatch, Log, TEXT("Lobby: %s asks for %s (pending: teams %d / %d)"), *Player->GetPlayerName(), *TeamLabel(Target),
		MyGameState->GetTeamState(0).NumPlayers, MyGameState->GetTeamState(1).NumPlayers);
	return true;
}

bool AMyGameMode::MoveLobbyPlayer(AMyPlayerState* Player, uint8 Target, FText& OutWhy)
{
	AMyGameState* MyGameState = GetMatchGameState();

	if (!bMatchOn || !Player || !MyGameState || Player->IsArriving() || Player->IsOnlyASpectator() || Target >= MyMatch::NumTeams)
	{
		return false;
	}

	if (GetPhase() != EMyMatchPhase::Lobby || !IsInLobby())
	{
		OutWhy = NSLOCTEXT("MyLobby", "TeamsLocked", "Teams are locked while the match starts");
		return false;
	}

	if (MatchRules.TeamMode == EMyTeamMode::Practice)
	{
		OutWhy = NSLOCTEXT("MyLobby", "PracticeOneShip", "Practice: everyone is on one ship");
		return false;
	}

	const uint8 From = Player->GetTeamId();

	if (From == Target || From >= MyMatch::NumTeams)
	{
		return true;
	}

	// Under its cap: a move, no balance rule (the host may build a 3v1; Start then warns, Uneven)
	RecountTeams();
	const int32 Cap = GetTeamCap();

	if (Cap == 0 || MyGameState->GetTeamState(Target).NumPlayers < Cap)
	{
		MoveLobbyTeam(Player, Target, TEXT("moved by the host"));
		return true;
	}

	// Full (1v1, 2v2): a swap, so the host can always arrange it. A player of the target team who asked for the mover's
	// team first (the oldest request), else the one who joined last (PlayerArray order)
	AMyPlayerState* Other = nullptr;

	for (APlayerState* PlayerState : MyGameState->PlayerArray)
	{
		AMyPlayerState* Candidate = Cast<AMyPlayerState>(PlayerState);

		if (Candidate && Candidate != Player && !Candidate->IsArriving() && Candidate->GetTeamId() == Target && Candidate->GetRequestedTeam() == From
			&& (!Other || Candidate->GetRequestServerTime() < Other->GetRequestServerTime()))
		{
			Other = Candidate;
		}
	}

	if (!Other)
	{
		for (APlayerState* PlayerState : MyGameState->PlayerArray)
		{
			AMyPlayerState* Candidate = Cast<AMyPlayerState>(PlayerState);

			if (Candidate && Candidate != Player && !Candidate->IsArriving() && !Candidate->IsOnlyASpectator() && Candidate->GetTeamId() == Target)
			{
				Other = Candidate;
			}
		}
	}

	if (!Other)
	{
		return false;
	}

	MoveLobbyTeam(Other, From, TEXT("swapped by the host"));
	MoveLobbyTeam(Player, Target, TEXT("swapped by the host"));
	return true;
}

void AMyGameMode::RebalanceLobbyTeams()
{
	AMyGameState* MyGameState = GetMatchGameState();

	if (!MyGameState)
	{
		return;
	}

	// Every request cleared, every team again by AssignTeam in join order: the memory and join order apply again.
	// Players still loading keep theirs (their arrival checks it against the new mode)
	TArray<AMyPlayerState*> Players;

	for (APlayerState* PlayerState : MyGameState->PlayerArray)
	{
		AMyPlayerState* MyPlayerState = Cast<AMyPlayerState>(PlayerState);

		if (MyPlayerState && !MyPlayerState->IsArriving() && !MyPlayerState->IsOnlyASpectator() && !MyPlayerState->IsActorBeingDestroyed())
		{
			MyPlayerState->SetRequestedTeam(MyMatch::NoTeam);
			MyPlayerState->SetTeamId(MyMatch::NoTeam);
			Players.Add(MyPlayerState);
		}
	}

	RecountTeams();
	TArray<FString> Result;

	for (AMyPlayerState* MyPlayerState : Players)
	{
		AssignTeam(MyPlayerState, MyPlayerState->GetUniqueId());
		Result.Add(FString::Printf(TEXT("%s %s"), *MyPlayerState->GetPlayerName(), *MyGameModeLobby::TeamLabel(MyPlayerState->GetTeamId())));
	}

	RecountTeams();
	MyGameState->MulticastMatchEvent(EMyMatchEvent::LobbyTeamChanged, MyMatch::NoTeam, -1);
	UE_LOG(LogMatch, Log, TEXT("Lobby: teams rebalanced for %s: %s"), UMyTeamLibrary::GetTeamModeOption(MatchRules.TeamMode), *FString::Join(Result, TEXT(", ")));
}

void AMyGameMode::ClearLobbyReady(const TCHAR* Why)
{
	const AMyGameState* MyGameState = GetMatchGameState();

	if (!MyGameState || !UMyMatchSettings::Get()->bLobbyRulesClearReady)
	{
		return;
	}

	int32 Cleared = 0;

	for (APlayerState* PlayerState : MyGameState->PlayerArray)
	{
		AMyPlayerState* MyPlayerState = Cast<AMyPlayerState>(PlayerState);

		if (MyPlayerState && MyPlayerState->IsLobbyReady())
		{
			MyPlayerState->SetLobbyReady(false);
			SendLobbyMessage(MyPlayerState->GetOwningController(), NSLOCTEXT("MyLobby", "ReadyAgain", "Teams changed: press READY again"));
			++Cleared;
		}
	}

	if (Cleared > 0)
	{
		UE_LOG(LogMatch, Log, TEXT("Lobby: %d ready flag(s) cleared (%s)"), Cleared, Why);
	}
}

bool AMyGameMode::SetLobbyReady(AMyPlayerState* Player, bool bReady, FText& OutWhy)
{
	if (!bMatchOn || !Player || !IsInLobby())
	{
		OutWhy = NSLOCTEXT("MyLobby", "ReadyLobbyOnly", "Ready works in the lobby only");
		return false;
	}

	if (IsLobbyCountingDown())
	{
		OutWhy = NSLOCTEXT("MyLobby", "AlreadyStarting", "The match is already starting");
		return false;
	}

	if (Player->IsHost())
	{
		OutWhy = NSLOCTEXT("MyLobby", "HostReady", "The host is ready when he presses Start");
		return false;
	}

	if (Player->IsLobbyReady() != bReady)
	{
		Player->SetLobbyReady(bReady);
		UE_LOG(LogMatch, Log, TEXT("Lobby: %s %s"), *Player->GetPlayerName(), bReady ? TEXT("is ready") : TEXT("is not ready"));
		UpdateLobbyState();
	}
	return true;
}

// =============================================================================
// L3 4.6: rules
// =============================================================================

bool AMyGameMode::ApplyLobbyRules(const FMyMatchRules& NewRules, int32 MaxPlayers, FText& OutWhy)
{
	AMyGameState* MyGameState = GetMatchGameState();

	if (!bMatchOn || !MyGameState || GetPhase() != EMyMatchPhase::Lobby || !IsInLobby())
	{
		OutWhy = IsLobbyCountingDown() ? NSLOCTEXT("MyLobby", "RulesLocked", "Rules are locked while the match starts")
			: NSLOCTEXT("MyLobby", "RulesLobbyOnly", "The lobby's rules change in the lobby only");
		return false;
	}

	RecountTeams();
	const int32 NumIn = CountLobbyPlayers();
	const int32 ModeMax = UMyTeamLibrary::GetTeamModeMaxPlayers(NewRules.TeamMode);

	if (ModeMax > 0 && NumIn > ModeMax)
	{
		OutWhy = FText::Format(NSLOCTEXT("MyLobby", "ModeNoRoom", "{0} has room for {1}: {2} players are in"),
			FText::FromString(UMyTeamLibrary::GetTeamModeOption(NewRules.TeamMode)), ModeMax, NumIn);
		UE_LOG(LogMatch, Log, TEXT("Lobby: rules refused (%s)"), *OutWhy.ToString());
		return false;
	}

	const int32 NewMax = ModeMax > 0 ? ModeMax : FMath::Clamp(MaxPlayers, 1, 64);

	if (NewMax < NumIn)
	{
		OutWhy = FText::Format(NSLOCTEXT("MyLobby", "MaxNoRoom", "Max Players {0}: {1} players are in"), NewMax, NumIn);
		UE_LOG(LogMatch, Log, TEXT("Lobby: rules refused (%s)"), *OutWhy.ToString());
		return false;
	}

	const EMyTeamMode OldMode = MatchRules.TeamMode;
	const int32 OldMax = GetLobbyMaxPlayers();

	// The team mode applies at once in the lobby; ApplyRules rebalances and clears the ready flags itself on a change
	ApplyRules(NewRules);

	ExpectedPlayers = NewMax;
	MyGameState->SetExpectedPlayers(NewMax);

	if (NewMax != OldMax && OldMode == MatchRules.TeamMode)
	{
		ClearLobbyReady(TEXT("Max Players changed"));
	}

	MyGameState->MulticastMatchEvent(EMyMatchEvent::LobbyRulesChanged, MyMatch::NoTeam, NewMax);
	UE_LOG(LogMatch, Log, TEXT("Lobby: rules applied, max players %d -> %d"), OldMax, NewMax);

	// One session update per accepted request (the widget batches edits for 0.75 s)
	AdvertiseIfHosting(/*bInMatch=*/false);
	UpdateLobbyState();
	return true;
}

// =============================================================================
// L3 4.7: the round start ends the lobby
// =============================================================================

int32 AMyGameMode::RemoveTimedEffects(UAbilitySystemComponent* ASC)
{
	if (!ASC)
	{
		return 0;
	}

	// Cooldowns and timed buffs. Infinite effects stay: the secondary attributes and passives belong to the player
	FGameplayEffectQuery Query;
	Query.CustomMatchDelegate.BindLambda([](const FActiveGameplayEffect& Effect)
	{
		return Effect.GetDuration() > 0.f;
	});
	return ASC->RemoveActiveEffects(Query);
}

void AMyGameMode::TakeBackLobbyPawns()
{
	AMyGameState* MyGameState = GetMatchGameState();

	// Pending respawns of lobby pawns would bring them back somewhere else: they start aboard with everyone
	for (TPair<TWeakObjectPtr<AController>, FPendingRespawn>& Pending : PendingRespawns)
	{
		GetWorldTimerManager().ClearTimer(Pending.Value.FXTimer);
		GetWorldTimerManager().ClearTimer(Pending.Value.RespawnTimer);
	}

	PendingRespawns.Reset();
	LobbyOutsideSince.Reset();
	FallingSince.Reset();

	int32 NumPawns = 0;

	for (FConstPlayerControllerIterator It = GetWorld()->GetPlayerControllerIterator(); It; ++It)
	{
		NumPawns += TakeBackPawn(It->Get(), TEXT("the lobby is over")) ? 1 : 0;
	}

	// So round 1 starts like every later round (critique m11). The new pawn refills Health and Mana
	int32 NumEffects = 0;

	if (MyGameState)
	{
		for (APlayerState* PlayerState : MyGameState->PlayerArray)
		{
			if (const AMyPlayerState* MyPlayerState = Cast<AMyPlayerState>(PlayerState))
			{
				NumEffects += RemoveTimedEffects(MyPlayerState->MyAbilitySystemComponent);
			}
		}
	}

	UE_LOG(LogMatch, Log, TEXT("Lobby: %d lobby pawn(s) taken back, %d timed effect(s) removed"), NumPawns, NumEffects);
}

void AMyGameMode::ResumeSwarm()
{
	// The spawners that ran when the lobby began (armed in their BeginPlay, stopped by BeginLobby); the others were never
	// meant to run (StartWaves would start them from wave 1)
	int32 NumResumed = 0;

	for (const TWeakObjectPtr<AMechSentinelWaveSpawner>& WeakSpawner : LobbyStoppedSpawners)
	{
		if (AMechSentinelWaveSpawner* Spawner = WeakSpawner.Get())
		{
			Spawner->StartWaves(/*bRestartFromFirstWave=*/false);
			++NumResumed;
		}
	}

	LobbyStoppedSpawners.Reset();

	if (UBurrowerSpawnSubsystem* Burrowers = UBurrowerSpawnSubsystem::Get(this))
	{
		Burrowers->SetSpawningPaused(false);
	}

	UE_LOG(LogMatch, Log, TEXT("Lobby: swarm resumed (%d wave spawner(s), Burrowers unpaused)"), NumResumed);
}

// =============================================================================
// L4 5.3: back to the lobby, the restart
// =============================================================================

bool AMyGameMode::WillReturnToLobby() const
{
	if (!bMatchOn)
	{
		return false;
	}

	if (bLobbyRound)
	{
		return true;
	}

	const UGameInstance* GameInstance = GetGameInstance();
	const UMultiplayerSessionsSubsystem* Sessions = GameInstance ? GameInstance->GetSubsystem<UMultiplayerSessionsSubsystem>() : nullptr;
	return Sessions && Sessions->IsHostingSession();
}

void AMyGameMode::ReturnToLobby()
{
	TravelToRound(/*bLobby=*/true);
}

int32 AMyGameMode::GetReturnLobbyMaxPlayers(int32 NumPlayers) const
{
	// A round that was not a lobby round (Play Solo, then the pause menu's Open Lobby) has ExpectedPlayers 1: the lobby it
	// returns to keeps room for the players in now and for the slots the host's session was opened with. The new
	// lobby's 1v1 / 2v2 still cap it (GetLobbyMaxPlayers there)
	int32 MaxPlayers = FMath::Max(GetLobbyMaxPlayers(), NumPlayers);

	if (!bLobbyRound)
	{
		const UGameInstance* GameInstance = GetGameInstance();
		const UMultiplayerSessionsSubsystem* Sessions = GameInstance ? GameInstance->GetSubsystem<UMultiplayerSessionsSubsystem>() : nullptr;
		FAuraHostSettings Host;

		if (Sessions && Sessions->IsHostingSession() && Sessions->GetCurrentHostSettings(Host))
		{
			MaxPlayers = FMath::Max(MaxPlayers, Host.NumPublicConnections);
		}
	}

	return FMath::Clamp(MaxPlayers, 1, 64);
}

void AMyGameMode::TravelToRound(bool bLobby)
{
	UWorld* World = GetWorld();
	AMyGameState* MyGameState = GetMatchGameState();

	if (!bMatchOn || bRestarting || !World || GetNetMode() == NM_Client)
	{
		return;
	}

	const UMyMatchSettings* Settings = UMyMatchSettings::Get();
	FTimerManager& TimerManager = GetWorldTimerManager();
	TimerManager.ClearTimer(RestartTimer);
	TimerManager.ClearTimer(CountdownTimer);

	// The round counts versus rounds: the lane sides swap on odd ones so the start floor's side alternates between the
	// two teams (B1.6, decided in StartCountdown). A practice round never swaps (no opponent to be fair to, and its lone
	// ship stays near the floor), and its restart keeps the round, so the next versus round still alternates
	const bool bSwapSides = IsVersusRound();
	int32 NextRound = bSwapSides ? RoundIndex + 1 : RoundIndex;

	if (UMyMatchMemorySubsystem* Memory = UMyMatchMemorySubsystem::Get(this))
	{
		Memory->SetRoundIndex(RoundIndex);
		Memory->RememberTeams(MyGameState);

		if (bSwapSides)
		{
			Memory->NextRound();
		}
		NextRound = Memory->GetRoundIndex();
	}

	// A BACK TO LOBBY during a match skips EndMatch, so the session ends here too (5.6; only from InProgress)
	if (bLobby)
	{
		EndSessionIfHost();
	}

	// The players that played come back; waiting for that many starts the next round as soon as they are all in, the
	// host's Start match covers anyone who doesn't. With the lobby, Players is the host's Max Players
	int32 NumPlayers = 0;

	if (MyGameState)
	{
		for (const APlayerState* PlayerState : MyGameState->PlayerArray)
		{
			NumPlayers += (PlayerState && !PlayerState->IsOnlyASpectator() && !PlayerState->IsABot()) ? 1 : 0;
		}
	}

	// ?SeamlessTravel on the URL, not the class's bUseSeamlessTravel: BP_MyGameMode is the global default game mode and
	// MatchMaps may be empty, so the flag could reach other maps' travels (5.3). OpenLevel (standalone) has no clients
	const bool bServerTravel = GetNetMode() != NM_Standalone;
	const bool bSeamless = bServerTravel && Settings->bSeamlessTravel;
	FString Options = BuildRulesOptions(MatchRules, NextTeamMode)
		+ FString::Printf(TEXT("?Players=%d?Match=1?Round=%d"), bLobby ? GetReturnLobbyMaxPlayers(NumPlayers) : FMath::Max(1, NumPlayers), NextRound);

	if (bLobby)
	{
		Options += TEXT("?Lobby=1");
	}

	if (bSeamless)
	{
		Options += TEXT("?SeamlessTravel");
	}

	const FString MapPath = UWorld::RemovePIEPrefix(World->GetPackage()->GetName());
	bRestarting = true;
	UpdateLobbyState();

	if (bLobby && MyGameState)
	{
		MyGameState->MulticastMatchEvent(EMyMatchEvent::LobbyReturn, MyMatch::NoTeam, NextRound);
	}

	// PIE turns the option off and travels hard unless net.AllowPIESeamlessTravel 1 (GameModeBase.cpp:503-511)
	const IConsoleVariable* PIESeamless = IConsoleManager::Get().FindConsoleVariable(TEXT("net.AllowPIESeamlessTravel"));
	const bool bPIEHard = bSeamless && World->WorldType == EWorldType::PIE && !(PIESeamless && PIESeamless->GetBool());
	const TCHAR* Kind = !bServerTravel ? TEXT("OpenLevel") : (bSeamless ? (bPIEHard ? TEXT("hard (PIE, net.AllowPIESeamlessTravel 0)") : TEXT("seamless")) : TEXT("hard"));

	if (bLobby)
	{
		UE_LOG(LogMatch, Log, TEXT("Match: back to the lobby, round %d, %s: %s%s"), NextRound, Kind, *MapPath, *Options);
	}
	else
	{
		UE_LOG(LogMatch, Log, TEXT("Match: restart, round %d, %s: %s%s"), NextRound, Kind, *MapPath, *Options);
	}

	if (!bServerTravel)
	{
		// OpenLevel adds its own '?'
		UGameplayStatics::OpenLevel(this, FName(*MapPath), true, Options.RightChop(1));
		return;
	}

	// Relative, so the next map listens on this one's port: an absolute URL takes FURL's default port (7777) while the
	// clients are sent back to the current address and port (PIE listens on ServerPort 17777, -port= elsewhere), and a
	// hard travel never got them back in (as_80 LM1.8, 2026-11-28). A relative URL keeps this map's options unless set
	// again: every option the next round reads is set above, and a restart without the lobby says so when this map had it
	const FString TravelURL = MapPath + (GetNetMode() == NM_ListenServer ? TEXT("?listen") : TEXT("")) + Options
		+ (!bLobby && World->URL.HasOption(TEXT("Lobby")) ? TEXT("?Lobby=0") : TEXT(""));

	if (!World->ServerTravel(TravelURL, /*bAbsolute=*/false))
	{
		bRestarting = false;
		UE_LOG(LogMatch, Warning, TEXT("Match: ServerTravel to %s refused"), *TravelURL);
	}
}

// =============================================================================
// L4 5.4: both arrival paths, leaving the map
// =============================================================================

void AMyGameMode::OnPlayerArrived(APlayerController* PC, bool bSeamless)
{
	AMyPlayerState* MyPlayerState = PC ? PC->GetPlayerState<AMyPlayerState>() : nullptr;

	if (!PC)
	{
		return;
	}

	if (MyPlayerState)
	{
		MyPlayerState->SetIsHost(IsLobbyHost(PC));
	}

	// The pilot component is added only on GameModePostLoginEvent (AirshipSubsystem.cpp HandlePostLogin) and for the PCs
	// present at BeginPlay: a seamless client arrives after both. Idempotent
	if (const UAirshipSubsystem* Airships = UAirshipSubsystem::Get(this))
	{
		Airships->EnsurePilotComponent(PC);
	}

	if (!bMatchOn)
	{
		return;
	}

	// The hard path ran EvaluateTeams in InitNewPlayer (before PlayerCanRestart); HandleStartingNewPlayer runs after
	// InitSeamlessTravelPlayer, so the order holds here too
	if (bSeamless)
	{
		EvaluateTeams();
	}

	UE_LOG(LogMatch, Log, TEXT("Team: %s arrives (%s), team %s, phase %s%s"), MyPlayerState ? *MyPlayerState->GetPlayerName() : *PC->GetName(),
		bSeamless ? TEXT("seamless") : TEXT("hard"), MyPlayerState ? *MyGameModeLobby::TeamLabel(MyPlayerState->GetTeamId()) : TEXT("none"),
		UMyTeamLibrary::GetMatchPhaseName(GetPhase()), MyPlayerState && MyPlayerState->IsHost() ? TEXT(", host") : TEXT(""));
}

void AMyGameMode::InitSeamlessTravelPlayer(AController* NewController)
{
	AMyPlayerState* MyPlayerState = NewController ? NewController->GetPlayerState<AMyPlayerState>() : nullptr;

	// The team before Super: it picks the start spot (ChoosePlayerStart prefers the team's starts). CopyProperties brought
	// the old team; the new round's mode and caps still apply (a mode changed to Practice puts everyone on team 0)
	if (MyPlayerState)
	{
		const uint8 Kept = MyPlayerState->GetTeamId();
		MyPlayerState->SetTeamId(MyMatch::NoTeam);

		if (bMatchOn && !MyPlayerState->IsOnlyASpectator())
		{
			AssignTeam(MyPlayerState, MyPlayerState->GetUniqueId(), Kept);
		}
	}

	Super::InitSeamlessTravelPlayer(NewController);

	if (APlayerController* PC = Cast<APlayerController>(NewController))
	{
		OnPlayerArrived(PC, /*bSeamless=*/true);
	}
}

void AMyGameMode::PostSeamlessTravel()
{
	// Every player state in this world now was carried by the travel: no login has run on this map yet. The engine's
	// bActorSeamlessTraveled is already false here (InitializeNetworkActors, World.cpp:9021 -> Level.cpp:3709)
	int32 NumCarried = 0;

	for (TActorIterator<AMyPlayerState> It(GetWorld()); It; ++It)
	{
		if (IsValid(*It) && !It->IsABot() && !It->IsActorBeingDestroyed())
		{
			It->SetArriving(true);
			++NumCarried;
		}
	}

	if (bMatchOn)
	{
		UE_LOG(LogMatch, Log, TEXT("Match: seamless arrival, %d carried player state(s) arriving until their owners load"), NumCarried);
	}

	// Replaces the player states of the owners already loaded (the host): their new ones are not arriving
	Super::PostSeamlessTravel();
}

void AMyGameMode::StartToLeaveMap()
{
	Super::StartToLeaveMap();

	// Runs for every server travel (a hard one twice: ProcessServerTravel and the switch). Timers live on the game
	// instance's timer manager (World.cpp:8056) and this game mode lives on in the transition world: nothing of the
	// match may keep firing there (SPEC_B_LOBBY 5.4 row 1)
	GetWorldTimerManager().ClearAllTimersForObject(this);
	PendingRespawns.Reset();
	LobbyOutsideSince.Reset();
	FallingSince.Reset();
	bEndCheckPending = false;

	if (bMatchOn)
	{
		UE_LOG(LogMatch, Log, TEXT("Match: leaving the map (game mode timers cleared)"));
	}

	bRestarting = true;

	if (bMatchOn)
	{
		StopSwarm();
	}

	// An AI controller with a player state is carried by seamless travel, keeps its old player state and would count as
	// arriving forever (Controller.cpp ShouldParticipateInSeamlessTravel)
	FText Ignored;
	SetLobbyBots(0, Ignored);
}

// =============================================================================
// L4 5.6: the session
// =============================================================================

void AMyGameMode::StartSessionIfHost()
{
	UGameInstance* GameInstance = GetGameInstance();
	UMultiplayerSessionsSubsystem* Sessions = GameInstance ? GameInstance->GetSubsystem<UMultiplayerSessionsSubsystem>() : nullptr;

	if (!Sessions || !Sessions->IsHostingSession())
	{
		return;
	}

	UE_LOG(LogMatch, Log, TEXT("Session: StartSession (round start)"));
	Sessions->StartSession();
	AdvertiseIfHosting(/*bInMatch=*/true);
}

void AMyGameMode::EndSessionIfHost()
{
	UGameInstance* GameInstance = GetGameInstance();
	UMultiplayerSessionsSubsystem* Sessions = GameInstance ? GameInstance->GetSubsystem<UMultiplayerSessionsSubsystem>() : nullptr;

	if (Sessions && Sessions->IsHostingSession())
	{
		UE_LOG(LogMatch, Log, TEXT("Session: EndSession (match end)"));
		Sessions->EndSession();
	}
}

void AMyGameMode::AdvertiseIfHosting(bool bInMatch)
{
	UGameInstance* GameInstance = GetGameInstance();
	UMultiplayerSessionsSubsystem* Sessions = GameInstance ? GameInstance->GetSubsystem<UMultiplayerSessionsSubsystem>() : nullptr;

	if (!Sessions || !Sessions->IsHostingSession())
	{
		UE_LOG(LogMatch, Log, TEXT("Lobby: no session to advertise (%s)"), bInMatch ? TEXT("in match") : TEXT("in lobby"));
		return;
	}

	// Without the lobby the slots stay what the session was made with (0 = keep)
	Sessions->AdvertiseMatch(MatchRules.TeamMode, MatchRules.SwarmDifficulty, bLobbyRound ? GetLobbyMaxPlayers() : 0, bInMatch);
}

// =============================================================================
// Messages, bots
// =============================================================================

void AMyGameMode::SendLobbyMessage(AController* Controller, const FText& Text) const
{
	if (AMyPlayerController2* PC = Cast<AMyPlayerController2>(Controller))
	{
		PC->ClientLobbyMessage(Text);
	}
}

int32 AMyGameMode::SetLobbyBots(int32 Count, FText& OutWhy)
{
	UWorld* World = GetWorld();
	Count = FMath::Clamp(Count, 0, 8);
	LobbyBots.RemoveAll([](const TWeakObjectPtr<AController>& Bot) { return !Bot.IsValid(); });

	while (LobbyBots.Num() > Count)
	{
		AController* Bot = LobbyBots.Pop().Get();

		if (IsValid(Bot))
		{
			UE_LOG(LogMatch, Log, TEXT("Lobby: bot %s leaves"), *GetNameSafe(Bot->PlayerState));
			// AController::Destroyed logs it out (EvaluateTeams) with its player state
			Bot->Destroy();
		}
	}

	if (LobbyBots.Num() < Count && (!World || !bMatchOn || GetPhase() != EMyMatchPhase::Lobby))
	{
		OutWhy = NSLOCTEXT("MyLobby", "BotsLobbyOnly", "Bots join in the lobby only");
		return LobbyBots.Num();
	}

	while (LobbyBots.Num() < Count)
	{
		FActorSpawnParameters SpawnParams;
		SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		SpawnParams.bDeferConstruction = true;
		SpawnParams.ObjectFlags |= RF_Transient;
		AAIController* Bot = World->SpawnActor<AAIController>(AAIController::StaticClass(), FTransform::Identity, SpawnParams);

		if (!Bot)
		{
			break;
		}

		// Before PostInitializeComponents: that is where it makes its player state (the game mode's class, AMyPlayerState)
		Bot->bWantsPlayerState = true;
		Bot->FinishSpawning(FTransform::Identity);
		AMyPlayerState* BotState = Bot->GetPlayerState<AMyPlayerState>();

		if (!BotState)
		{
			UE_LOG(LogMatch, Warning, TEXT("Lobby: a bot got no AMyPlayerState"));
			Bot->Destroy();
			break;
		}

		BotState->SetIsABot(true);
		BotState->SetPlayerName(FString::Printf(TEXT("Bot %d"), ++LobbyBotCounter));
		AssignTeam(BotState, BotState->GetUniqueId());
		LobbyBots.Add(Bot);
		UE_LOG(LogMatch, Log, TEXT("Lobby: bot %s joins %s"), *BotState->GetPlayerName(), *MyGameModeLobby::TeamLabel(BotState->GetTeamId()));
		EvaluateTeams();
	}

	return LobbyBots.Num();
}
