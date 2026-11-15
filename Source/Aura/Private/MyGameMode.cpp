// Fill out your copyright notice in the Description page of Project Settings.


#include "MyGameMode.h"

#include "AbilitySystemComponent.h"
#include "EngineUtils.h"
#include "MyGameState.h"
#include "MyPlayerState.h"
#include "TimerManager.h"
#include "AbilitySystem/MyAbilitySystemComponent.h"
#include "Actors/MyHexPlatform.h"
#include "Components/CapsuleComponent.h"
#include "EOS/MultiplayerSessionsSubsystem.h"
#include "GameFramework/Character.h"
#include "Interfaces/MyCombatInterface.h"
#include "NiagaraSystem.h"
#include "UObject/ConstructorHelpers.h"


AMyGameMode::AMyGameMode()
{
	// Ranks players by how far along the path they are
	GameStateClass = AMyGameState::StaticClass();
	
	// Loaded with the class, so it is cooked too (the project cooks maps only)
	static ConstructorHelpers::FObjectFinder<UNiagaraSystem> RespawnFXSystem(
		TEXT("/Game/Level/GAS/GameplayAbilities/GA_Beam/Niagara/NS_BeamClaude/NS_Claude_RespawnFX.NS_Claude_RespawnFX"));
	RespawnFX = RespawnFXSystem.Object;
}


void AMyGameMode::PreLogin(const FString& Options, const FString& Address, const FUniqueNetIdRepl& UniqueId, FString& ErrorMessage)
{
	Super::PreLogin(Options, Address, UniqueId, ErrorMessage);
	if (!ErrorMessage.IsEmpty())
	{
		return;
	}

	if (UGameInstance* GameInstance = GetGameInstance())
	{
		if (UMultiplayerSessionsSubsystem* Subsystem = GameInstance->GetSubsystem<UMultiplayerSessionsSubsystem>())
		{
			// A non-empty message refuses the connection and is what the joining player sees
			ErrorMessage = Subsystem->CheckJoinAllowed(UniqueId, GetNumPlayers());
		}
	}
}

void AMyGameMode::PostLogin(APlayerController* NewPlayer)
{
	Super::PostLogin(NewPlayer);

	// Check if this is the hosting player (the first local controller on the server)
	if (NewPlayer && NewPlayer->IsLocalController())
	{
		UGameInstance* GameInstance = GetGameInstance();
		if (GameInstance)
		{
			UMultiplayerSessionsSubsystem* Subsystem = GameInstance->GetSubsystem<UMultiplayerSessionsSubsystem>();
			if (Subsystem)
			{
				// This registers the host fully into the active Steam/EOS session roster
				Subsystem->StartSession();
				UE_LOG(LogTemp, Log, TEXT("Host has logged into map. Starting Online Session."));
			}
		}
	}
	
}

namespace
{
	/**
	 * Ends what Pawn was doing (boost, beam, ...) while it is still the ASC's avatar. The ASC is on the PlayerState
	 * and goes on to the next pawn, which shouldn't start with any of it.
	 */
	void CancelActiveAbilities(const AController* Controller, const APawn* Pawn)
	{
		const AMyPlayerState* MyPlayerState = Controller ? Controller->GetPlayerState<AMyPlayerState>() : nullptr;
		UAbilitySystemComponent* ASC = MyPlayerState ? MyPlayerState->MyAbilitySystemComponent : nullptr;

		if (!ASC || !Pawn || ASC->GetAvatarActor() != Pawn)
		{
			return;
		}

		TArray<FGameplayAbilitySpecHandle> ToCancel;

		for (const FGameplayAbilitySpec& Spec : ASC->GetActivatableAbilities())
		{
			// Passives (GiveAbilityAndActivateOnce) keep running for the next pawn
			if (Spec.IsActive() && !Spec.RemoveAfterActivation)
			{
				ToCancel.Add(Spec.Handle);
			}
		}

		for (const FGameplayAbilitySpecHandle& Handle : ToCancel)
		{
			ASC->CancelAbilityHandle(Handle);
		}
	}
}

void AMyGameMode::SetPlayerDefaults(APawn* PlayerPawn)
{
	Super::SetPlayerDefaults(PlayerPawn);

	WatchPlayerPawn(PlayerPawn);
}

void AMyGameMode::Logout(AController* Exiting)
{
	if (FPendingRespawn* Pending = PendingRespawns.Find(Exiting))
	{
		GetWorldTimerManager().ClearTimer(Pending->FXTimer);
		GetWorldTimerManager().ClearTimer(Pending->RespawnTimer);
		PendingRespawns.Remove(Exiting);
	}

	// Its pawn is destroyed after this; with no entry, OnPlayerPawnDestroyed ignores it
	for (auto It = WatchedPawns.CreateIterator(); It; ++It)
	{
		if (!It.Value().IsValid() || It.Value() == Exiting)
		{
			It.RemoveCurrent();
		}
	}

	Super::Logout(Exiting);
}

bool AMyGameMode::PlayerCanRestart_Implementation(APlayerController* Player)
{
	return !PendingRespawns.Contains(Player) && Super::PlayerCanRestart_Implementation(Player);
}

void AMyGameMode::WatchPlayerPawn(APawn* PlayerPawn)
{
	AController* Controller = PlayerPawn ? PlayerPawn->GetController() : nullptr;

	if (!Controller)
	{
		return;
	}

	for (auto It = WatchedPawns.CreateIterator(); It; ++It)
	{
		if (!It.Key().IsValid())
		{
			It.RemoveCurrent();
		}
	}

	WatchedPawns.Add(PlayerPawn, Controller);

	if (IMyCombatInterface* CombatInterface = Cast<IMyCombatInterface>(PlayerPawn))
	{
		CombatInterface->GetOnDeathDelegate().AddUniqueDynamic(this, &ThisClass::OnPlayerPawnDied);
	}

	PlayerPawn->OnDestroyed.AddUniqueDynamic(this, &ThisClass::OnPlayerPawnDestroyed);
}

void AMyGameMode::UnwatchPlayerPawn(APawn* PlayerPawn)
{
	if (!PlayerPawn)
	{
		return;
	}

	WatchedPawns.Remove(PlayerPawn);

	if (IMyCombatInterface* CombatInterface = Cast<IMyCombatInterface>(PlayerPawn))
	{
		CombatInterface->GetOnDeathDelegate().RemoveDynamic(this, &ThisClass::OnPlayerPawnDied);
	}

	PlayerPawn->OnDestroyed.RemoveDynamic(this, &ThisClass::OnPlayerPawnDestroyed);
}

void AMyGameMode::OnPlayerPawnDied(AActor* DeadActor)
{
	// The dead pawn stays possessed (death anim, camera) until RespawnPlayer replaces it, but stops beaming,
	// boosting, ... now
	if (const APawn* DeadPawn = Cast<APawn>(DeadActor))
	{
		CancelActiveAbilities(DeadPawn->GetController(), DeadPawn);
		ScheduleRespawn(DeadPawn->GetController());
	}
}

void AMyGameMode::OnPlayerPawnDestroyed(AActor* DestroyedActor)
{
	TWeakObjectPtr<AController> WeakController;

	if (!WatchedPawns.RemoveAndCopyValue(Cast<APawn>(DestroyedActor), WeakController))
	{
		return;
	}

	AController* Controller = WeakController.Get();

	// Leaving, or the world is going away
	if (!Controller || Controller->IsActorBeingDestroyed() || GetWorld()->bIsTearingDown)
	{
		return;
	}

	// Already on another pawn
	if (Controller->GetPawn() && Controller->GetPawn() != DestroyedActor)
	{
		return;
	}

	// Still the avatar while it is being destroyed; by the respawn it is gone
	CancelActiveAbilities(Controller, Cast<APawn>(DestroyedActor));
	ScheduleRespawn(Controller);
}

void AMyGameMode::ScheduleRespawn(AController* Controller)
{
	if (!bRespawnEnabled || !Controller || PendingRespawns.Contains(Controller))
	{
		return;
	}

	FPendingRespawn& Pending = PendingRespawns.Add(Controller);
	const TWeakObjectPtr<AController> WeakController(Controller);
	FTimerManager& TimerManager = GetWorldTimerManager();

	// Never in the same frame as the death: this can run inside the dead pawn's Destroy
	const float Delay = FMath::Max(RespawnDelay, 0.1f);
	TimerManager.SetTimer(Pending.RespawnTimer, FTimerDelegate::CreateUObject(this, &ThisClass::RespawnPlayer, WeakController), Delay, false);

	const float FXDelay = Delay - FMath::Clamp(RespawnFXLeadTime, 0.f, Delay);

	if (FXDelay > 0.f)
	{
		TimerManager.SetTimer(Pending.FXTimer, FTimerDelegate::CreateUObject(this, &ThisClass::StartRespawnFX, WeakController), FXDelay, false);
	}
	else
	{
		StartRespawnFX(WeakController);
	}
}

void AMyGameMode::StartRespawnFX(TWeakObjectPtr<AController> WeakController)
{
	FPendingRespawn* Pending = PendingRespawns.Find(WeakController);
	AController* Controller = WeakController.Get();

	if (!Pending || !Controller)
	{
		return;
	}

	FPawnFit Fit;
	FRespawnSpot Spot;

	if (GetPawnFit(Controller, Fit) && FindRespawnSpot(Controller, Fit, Spot))
	{
		PlayRespawnFX(Spot);
		Pending->Spot = Spot;
	}
}

void AMyGameMode::RespawnPlayer(TWeakObjectPtr<AController> WeakController)
{
	FPendingRespawn Pending;

	if (!PendingRespawns.RemoveAndCopyValue(WeakController, Pending))
	{
		return;
	}

	GetWorldTimerManager().ClearTimer(Pending.FXTimer);

	AController* Controller = WeakController.Get();

	if (!IsValid(Controller) || Controller->IsActorBeingDestroyed())
	{
		return;
	}

	// First, so the dead pawn's capsule doesn't get in the way of the fit tests. RestartPlayerAtTransform only
	// spawns a pawn for a controller without one
	if (APawn* DeadPawn = Controller->GetPawn())
	{
		CancelActiveAbilities(Controller, DeadPawn);
		UnwatchPlayerPawn(DeadPawn);
		Controller->UnPossess();
		DeadPawn->Destroy();
	}

	FPawnFit Fit;
	FRespawnSpot Spot;
	bool bHasSpot = false;

	if (GetPawnFit(Controller, Fit))
	{
		if (Pending.Spot.IsSet())
		{
			const FRespawnSpot& Picked = Pending.Spot.GetValue();

			if (!Picked.bOnTile)
			{
				Spot = Picked;
				bHasSpot = true;
			}
			else if (AMyHexPlatform* Platform = Picked.Platform.Get())
			{
				// Tested again: since the FX started the tile may have fallen, or someone may be standing on it
				bHasSpot = FitPawnOnTile(Platform, Picked.TileCoord, Fit, Picked.PawnTransform.Rotator(), Controller, Spot);
			}
		}

		if (!bHasSpot && FindRespawnSpot(Controller, Fit, Spot))
		{
			// This FX is late, but plays where the pawn appears
			PlayRespawnFX(Spot);
			bHasSpot = true;
		}
	}

	if (bHasSpot)
	{
		RestartPlayerAtTransform(Controller, Spot.PawnTransform);
	}

	if (!Controller->GetPawn())
	{
		RestartPlayer(Controller);
	}

	if (!Controller->GetPawn())
	{
		UE_LOG(LogTemp, Warning, TEXT("Respawn: couldn't spawn a pawn for %s"), *GetNameSafe(Controller));
	}
}

bool AMyGameMode::GetPawnFit(AController* Controller, FPawnFit& OutFit)
{
	UClass* PawnClass = GetDefaultPawnClassForController(Controller);
	OutFit.PawnToFit = PawnClass ? PawnClass->GetDefaultObject<APawn>() : nullptr;

	if (!OutFit.PawnToFit)
	{
		return false;
	}

	// The class default's capsule: its transform isn't set up, so the scale comes from the relative scale
	const ACharacter* CharacterToFit = Cast<ACharacter>(OutFit.PawnToFit);

	if (const UCapsuleComponent* Capsule = CharacterToFit ? CharacterToFit->GetCapsuleComponent() : nullptr)
	{
		const FVector Scale = Capsule->GetRelativeScale3D();
		OutFit.HalfHeight = Capsule->GetUnscaledCapsuleHalfHeight() * static_cast<float>(Scale.Z);
		OutFit.Radius = Capsule->GetUnscaledCapsuleRadius() * static_cast<float>(FMath::Max(Scale.X, Scale.Y));
	}
	else
	{
		OutFit.HalfHeight = OutFit.PawnToFit->GetDefaultHalfHeight();
		OutFit.Radius = OutFit.HalfHeight;
	}

	return true;
}

bool AMyGameMode::FindRespawnSpot(AController* Controller, const FPawnFit& Fit, FRespawnSpot& OutSpot)
{
	const AMyGameState* MyGameState = GetGameState<AMyGameState>();

	if (MyGameState && MyGameState->GetLeadSplineDistance() >= 0.f)
	{
		// Platforms up to the furthest distance the lead has reached are collapsing. It only goes up, so a
		// lead that walks back (or leaves) doesn't put the spot on one of them
		const float PastDistance = FMath::Max(MyGameState->GetLeadSplineDistance(), MyGameState->GetActivatedSplineDistance());

		AMyHexPlatform* LeadPlatform = nullptr;

		for (const AMyPlayerState* Leader : MyGameState->GetLeadingPlayerStates())
		{
			if (Leader && IsValid(Leader->GetCurrentPlatform()))
			{
				LeadPlatform = Leader->GetCurrentPlatform();
				break;
			}
		}

		struct FCandidate
		{
			AMyHexPlatform* Platform;
			float SplineDistance;
			double DistSqToLead;
		};

		TArray<FCandidate> Candidates;

		for (TActorIterator<AMyHexPlatform> It(GetWorld()); It; ++It)
		{
			AMyHexPlatform* Platform = *It;

			if (IsValid(Platform) && Platform->HasSplineDistance() && Platform->GetSplineDistance() > PastDistance
				&& Platform->GetTileInfos().Num() > 0)
			{
				const double DistSqToLead = LeadPlatform
					? FVector::DistSquared(Platform->GetActorLocation(), LeadPlatform->GetActorLocation())
					: 0.0;
				Candidates.Add({ Platform, Platform->GetSplineDistance(), DistSqToLead });
			}
		}

		// Nearest along the path first; at the same distance (both chains), the one nearest the lead's platform
		Candidates.Sort([](const FCandidate& A, const FCandidate& B)
		{
			return A.SplineDistance != B.SplineDistance ? A.SplineDistance < B.SplineDistance : A.DistSqToLead < B.DistSqToLead;
		});

		// Last resort (the end of the path, or no room ahead): the lead's own platform
		if (LeadPlatform && LeadPlatform->GetTileInfos().Num() > 0)
		{
			Candidates.Add({ LeadPlatform, LeadPlatform->GetSplineDistance(), 0.0 });
		}

		for (const FCandidate& Candidate : Candidates)
		{
			// Face on along the path, away from the lead
			const FVector Forward = LeadPlatform && LeadPlatform != Candidate.Platform
				? (Candidate.Platform->GetActorLocation() - LeadPlatform->GetActorLocation()).GetSafeNormal2D()
				: FVector::ZeroVector;
			const double Yaw = Forward.IsNearlyZero() ? Controller->GetControlRotation().Yaw : Forward.Rotation().Yaw;

			if (FindRespawnTile(Candidate.Platform, Fit, FRotator(0.0, Yaw, 0.0), Controller, OutSpot))
			{
				return true;
			}
		}
	}

	// Nobody has landed on a platform yet, or no platform has room
	AActor* StartSpot = FindPlayerStart(Controller);

	if (!StartSpot)
	{
		return false;
	}

	OutSpot = FRespawnSpot();
	OutSpot.PawnTransform = FTransform(FRotator(0.0, StartSpot->GetActorRotation().Yaw, 0.0), StartSpot->GetActorLocation());
	OutSpot.GroundLocation = StartSpot->GetActorLocation() - FVector(0.f, 0.f, Fit.HalfHeight);
	return true;
}

bool AMyGameMode::FindRespawnTile(AMyHexPlatform* Platform, const FPawnFit& Fit, const FRotator& Rotation,
	const AController* Controller, FRespawnSpot& OutSpot) const
{
	// Each try is a few overlap tests; a platform that fits nobody in this many tiles is crowded or covered in props
	constexpr int32 MaxTileTries = 12;

	TArray<const FHexTileInfo*> Tiles;

	for (const TPair<FIntVector, FHexTileInfo>& Tile : Platform->GetTileInfos())
	{
		if (!Platform->IsTileCollapsed(Tile.Key))
		{
			Tiles.Add(&Tile.Value);
		}
	}

	// A pointer array's Sort compares the pointed-to tiles
	Tiles.Sort([](const FHexTileInfo& A, const FHexTileInfo& B)
	{
		const bool bAOnPath = A.PathDistance == 0;
		const bool bBOnPath = B.PathDistance == 0;

		if (bAOnPath != bBOnPath)
		{
			return bAOnPath;
		}

		const bool bAInside = A.EdgeDepth > 0;
		const bool bBInside = B.EdgeDepth > 0;

		if (bAInside != bBInside)
		{
			return bAInside;
		}

		return A.LocalTopCenter.SizeSquared2D() < B.LocalTopCenter.SizeSquared2D();
	});

	for (int32 Index = 0; Index < Tiles.Num() && Index < MaxTileTries; ++Index)
	{
		if (FitPawnOnTile(Platform, Tiles[Index]->Coord, Fit, Rotation, Controller, OutSpot))
		{
			return true;
		}
	}

	return false;
}

bool AMyGameMode::FitPawnOnTile(AMyHexPlatform* Platform, const FIntVector& TileCoord, const FPawnFit& Fit, const FRotator& Rotation,
	const AController* Controller, FRespawnSpot& OutSpot) const
{
	const FHexTileInfo* Tile = Platform ? Platform->GetTileInfos().Find(TileCoord) : nullptr;

	if (!Tile || Platform->IsTileCollapsed(TileCoord))
	{
		return false;
	}

	const FTransform& PlatformTransform = Platform->GetActorTransform();
	const float CapsuleLift = Fit.HalfHeight + RespawnHeightAboveTile;
	const FVector Ground = PlatformTransform.TransformPosition(Tile->LocalTopCenter);
	FVector Location = Ground + FVector(0.f, 0.f, CapsuleLift);

	// Moves the spot off pawns and props; false when nothing close by fits
	if (!GetWorld()->FindTeleportSpot(Fit.PawnToFit, Location, Rotation))
	{
		return false;
	}

	// Pushed off the tile, possibly over the edge
	const double TileReach = Tile->Apothem * PlatformTransform.GetScale3D().GetAbsMax();

	if (FVector::DistSquared2D(Location, Ground) > FMath::Square(TileReach))
	{
		return false;
	}

	// Pawns that haven't spawned yet are invisible to FindTeleportSpot: keep a capsule's width from their spots
	const double MinGap = 2.0 * Fit.Radius;

	for (const TPair<TWeakObjectPtr<AController>, FPendingRespawn>& Other : PendingRespawns)
	{
		if (Other.Key != Controller && Other.Value.Spot.IsSet()
			&& FVector::DistSquared(Other.Value.Spot->PawnTransform.GetLocation(), Location) < FMath::Square(MinGap))
		{
			return false;
		}
	}

	OutSpot = FRespawnSpot();
	OutSpot.PawnTransform = FTransform(Rotation, Location);
	OutSpot.GroundLocation = Location - FVector(0.f, 0.f, CapsuleLift);
	OutSpot.bOnTile = true;
	OutSpot.Platform = Platform;
	OutSpot.TileCoord = TileCoord;
	return true;
}

void AMyGameMode::PlayRespawnFX(const FRespawnSpot& Spot) const
{
	AMyGameState* MyGameState = GetGameState<AMyGameState>();

	if (MyGameState && RespawnFX)
	{
		MyGameState->MulticastPlayRespawnFX(RespawnFX, Spot.GroundLocation, Spot.PawnTransform.Rotator());
	}
}
