// Fill out your copyright notice in the Description page of Project Settings.


#include "Actors/MyHexPathSpawner.h"

#include "Actors/MyHexAtmosphereFX.h"
#include "Actors/MyHexBridgeSubsystem.h"
#include "Actors/MyHexPathSegment.h"
#include "Components/ExponentialHeightFogComponent.h"
#include "Components/SplineComponent.h"
#include "Engine/ExponentialHeightFog.h"
#include "EngineUtils.h"
#include "HAL/IConsoleManager.h"
#include "DrawDebugHelpers.h"
#include "Engine/World.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "TimerManager.h"

DEFINE_LOG_CATEGORY_STATIC(LogHexPath, Log, All);


// =============================================================================
// Constructor
// =============================================================================

AMyHexPathSpawner::AMyHexPathSpawner()
{
	PrimaryActorTick.bCanEverTick = false;

	// Only the server grows the path. The platforms PCG spawns replicate on their own.
	bReplicates = false;

	PathSpline = CreateDefaultSubobject<USplineComponent>(TEXT("PathSpline"));
	SetRootComponent(PathSpline);
}


// =============================================================================
// BeginPlay
// =============================================================================

void AMyHexPathSpawner::BeginPlay()
{
	Super::BeginPlay();

	StartAtmosphere();

	if (!HasAuthority())
	{
		return;
	}

	StartYaw = GetActorRotation().Yaw;
	StartZ = GetActorLocation().Z;
	TravelledDistance = 0.f;

	// The path starts with a single point at the actor
	PathSpline->ClearSplinePoints(/*bUpdateSpline=*/false);
	PathSpline->AddSplinePoint(GetActorLocation(), ESplineCoordinateSpace::World, /*bUpdateSpline=*/true);
	NextSegmentIndex = 0;

	// Platforms measure "left behind" along this spline
	if (UMyHexBridgeSubsystem* Subsystem = GetWorld()->GetSubsystem<UMyHexBridgeSubsystem>())
	{
		Subsystem->RegisterPathSpline(PathSpline);
	}

	for (int32 Index = 0; Index < InitialSegments; ++Index)
	{
		ExtendPath();
	}

	// The first segments are built while the players load in: no need to wait
	GetWorldTimerManager().ClearTimer(PathEndFogTimerHandle);
	UpdatePathEndFog();

	GetWorldTimerManager().SetTimer(
		CheckTimerHandle,
		this,
		&ThisClass::CheckPlayers,
		CheckInterval,
		true
	);
}


// =============================================================================
// Atmosphere
// =============================================================================

namespace
{
	TAutoConsoleVariable<int32> CVarAtmosphereVariant(
		TEXT("Aura.AtmosphereVariant"),
		-1,
		TEXT("Overrides AMyHexPathSpawner::AtmosphereVariant when 0 or more (an index into AtmosphereVariants; out of range = none). -1 = use the spawner's setting. Read when Play starts."),
		ECVF_Default
	);

	AMyHexPathSpawner* FindPathSpawner(const UObject* WorldContext)
	{
		UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;

		if (!World)
		{
			return nullptr;
		}

		// A level has one path spawner: the first one found holds the atmosphere settings
		TActorIterator<AMyHexPathSpawner> It(World);

		return It ? *It : nullptr;
	}
}

const FMyHexAtmosphereVariant* AMyHexPathSpawner::GetActiveAtmosphere() const
{
	const int32 Override = CVarAtmosphereVariant.GetValueOnGameThread();
	const int32 Index = Override >= 0 ? Override : AtmosphereVariant;

	return AtmosphereVariants.IsValidIndex(Index) ? &AtmosphereVariants[Index] : nullptr;
}

const FMyHexAtmosphereVariant* AMyHexPathSpawner::FindActiveAtmosphere(const UObject* WorldContext)
{
	const AMyHexPathSpawner* Spawner = FindPathSpawner(WorldContext);

	return Spawner ? Spawner->GetActiveAtmosphere() : nullptr;
}

float AMyHexPathSpawner::FindWindYaw(const UObject* WorldContext)
{
	const AMyHexPathSpawner* Spawner = FindPathSpawner(WorldContext);

	return Spawner ? Spawner->WindYaw : 0.f;
}

void AMyHexPathSpawner::StartAtmosphere()
{
	UWorld* World = GetWorld();

	if (!World || GetNetMode() == NM_DedicatedServer)
	{
		return;
	}

	const FMyHexAtmosphereVariant* Atmosphere = GetActiveAtmosphere();

	if (!Atmosphere)
	{
		return;
	}

	UE_LOG(LogTemp, Log, TEXT("%s: atmosphere variant '%s'"), *GetName(), *Atmosphere->Name.ToString());

	// Falling snow that follows this machine's camera
	TArray<FMyHexCameraEffect> Effects = Atmosphere->CameraEffects;

	for (const TSoftObjectPtr<UNiagaraSystem>& CameraSystem : Atmosphere->CameraSystems)
	{
		FMyHexCameraEffect& Effect = Effects.AddDefaulted_GetRef();
		Effect.System = CameraSystem;
	}

	for (const FMyHexCameraEffect& Effect : Effects)
	{
		if (Effect.System.IsNull())
		{
			continue;
		}

		const FTransform Transform(FRotator(0.f, WindYaw, 0.f), GetActorLocation());

		if (AMyHexAtmosphereFX* FX = World->SpawnActorDeferred<AMyHexAtmosphereFX>(AMyHexAtmosphereFX::StaticClass(), Transform, this))
		{
			FX->SetFollowLocalCamera(true, Atmosphere->CameraFXOffset);
			FX->SetSpawnRate(TEXT("SpawnRate"), Effect.SpawnRate, Effect.GustAmount, Effect.GustPeriod);
			FX->SetSystem(Effect.System);
			FX->FinishSpawning(Transform);
			CameraFXs.Add(FX);
		}
	}

	// Height fog, at runtime only
	if (Atmosphere->bOverrideHeightFog)
	{
		for (TActorIterator<AExponentialHeightFog> It(World); It; ++It)
		{
			UExponentialHeightFogComponent* Fog = It->GetComponent();

			if (!Fog)
			{
				continue;
			}

			Fog->SetFogDensity(Atmosphere->FogDensity);
			Fog->SetFogHeightFalloff(Atmosphere->FogHeightFalloff);
			Fog->SetFogInscatteringColor(Atmosphere->FogInscatteringColor);
			Fog->SetVolumetricFog(Atmosphere->bVolumetricFog);
			Fog->SetVolumetricFogDistance(Atmosphere->VolumetricFogDistance);
			Fog->SetVolumetricFogExtinctionScale(Atmosphere->VolumetricFogExtinctionScale);
			Fog->SetVolumetricFogScatteringDistribution(Atmosphere->VolumetricFogScatteringDistribution);
			Fog->SetVolumetricFogAlbedo(Atmosphere->VolumetricFogAlbedo);
		}
	}
}


// =============================================================================
// EndPlay
// =============================================================================

void AMyHexPathSpawner::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	for (AMyHexAtmosphereFX* Fog : PathEndFogs)
	{
		if (IsValid(Fog))
		{
			Fog->Destroy();
		}
	}

	PathEndFogs.Empty();

	for (AMyHexAtmosphereFX* FX : CameraFXs)
	{
		if (IsValid(FX))
		{
			FX->Destroy();
		}
	}

	CameraFXs.Empty();

	if (HasAuthority())
	{
		if (UWorld* World = GetWorld())
		{
			if (UMyHexBridgeSubsystem* Subsystem = World->GetSubsystem<UMyHexBridgeSubsystem>())
			{
				Subsystem->UnregisterPathSpline(PathSpline);
			}
		}
	}

	Super::EndPlay(EndPlayReason);
}


// =============================================================================
// Player check
// =============================================================================

void AMyHexPathSpawner::CheckPlayers()
{
	DestroyPassedSegments();

	const int32 LastIndex = PathSpline->GetNumberOfSplinePoints() - 1;

	if (LastIndex < 0)
	{
		return;
	}

	const FVector PathEnd = PathSpline->GetLocationAtSplinePoint(LastIndex, ESplineCoordinateSpace::World);

	for (FConstPlayerControllerIterator It = GetWorld()->GetPlayerControllerIterator(); It; ++It)
	{
		const APlayerController* PlayerController = It->Get();
		const APawn* Pawn = PlayerController ? PlayerController->GetPawn() : nullptr;

		if (Pawn && FVector::DistSquared2D(Pawn->GetActorLocation(), PathEnd) <= FMath::Square(ExtendDistance * GetLayoutScale()))
		{
			// One segment per check; if the player is still close, the next check adds another
			ExtendPath();
			return;
		}
	}
}


// =============================================================================
// Extend
// =============================================================================

void AMyHexPathSpawner::ExtendPath()
{
	if (!HasAuthority())
	{
		return;
	}

	const int32 FirstIndex = PathSpline->GetNumberOfSplinePoints() - 1;

	if (FirstIndex < 0)
	{
		return;
	}

	FVector Current = PathSpline->GetLocationAtSplinePoint(FirstIndex, ESplineCoordinateSpace::World);

	const int32 NumPoints = FMath::Max(PointsPerSegment, 1);
	const float Scale = GetLayoutScale();
	const float Step = SegmentLength * Scale / NumPoints;


	// -------------------------------------------------------------------------
	// Walk forward, steering with noise
	// -------------------------------------------------------------------------

	for (int32 Index = 0; Index < NumPoints; ++Index)
	{
		// Heading for this step, sampled half way along it
		const float Yaw = StartYaw + SampleNoise((TravelledDistance + Step * 0.5f) / Scale * YawNoiseFrequency + NoiseSeed) * MaxYawDeviation;

		TravelledDistance += Step;

		FVector Next = Current + FRotator(0.f, Yaw, 0.f).Vector() * Step;

		// Height follows its own noise (offset seed), around the start height
		Next.Z = StartZ + SampleNoise(TravelledDistance / Scale * HeightNoiseFrequency + NoiseSeed + 101.7f) * HeightNoiseAmplitude;

		PathSpline->AddSplinePoint(Next, ESplineCoordinateSpace::World, /*bUpdateSpline=*/false);

		if (bDrawDebug)
		{
			DrawDebugLine(GetWorld(), Current, Next, FColor::Cyan, true, -1.f, 0, 20.f);
		}

		Current = Next;
	}

	PathSpline->UpdateSpline();


	// -------------------------------------------------------------------------
	// Copy the new piece into its own segment actor
	// -------------------------------------------------------------------------

	if (!SegmentClass)
	{
		UE_LOG(LogHexPath, Warning, TEXT("%s: SegmentClass is not set, the path grows but nothing is spawned along it"), *GetName());
		return;
	}

	const int32 LastIndex = PathSpline->GetNumberOfSplinePoints() - 1;

	TArray<FVector> Points;
	TArray<FVector> Tangents;

	for (int32 Index = FirstIndex; Index <= LastIndex; ++Index)
	{
		Points.Add(PathSpline->GetLocationAtSplinePoint(Index, ESplineCoordinateSpace::World));
		Tangents.Add(PathSpline->GetTangentAtSplinePoint(Index, ESplineCoordinateSpace::World));
	}

	const FTransform SpawnTransform(Points[0]);

	FActorSpawnParameters SpawnParams;
	SpawnParams.Owner = this;
	SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;

	AMyHexPathSegment* Segment = GetWorld()->SpawnActor<AMyHexPathSegment>(SegmentClass, SpawnTransform, SpawnParams);

	if (!Segment)
	{
		return;
	}

	// Layout space is scaled around the start of the path, so it is the path grown at HexRadius 100
	Segment->SetLayout(HexRadius, FVector(GetActorLocation().X, GetActorLocation().Y, 0.0));
	Segment->SetPathDistances(
		PathSpline->GetDistanceAlongSplineAtSplinePoint(FirstIndex),
		PathSpline->GetDistanceAlongSplineAtSplinePoint(LastIndex)
	);

	// Where its platforms will be, before PCG has spawned any. From the world path: SegmentSpline is in layout space
	FVector BoundsCenter;
	FVector BoundsExtent;
	FRotator BoundsRotation;
	ComputeSegmentBounds(Segment->GetPathStartDistance(), Segment->GetPathEndDistance(), BoundsCenter, BoundsExtent, BoundsRotation);
	Segment->SetSegmentBounds(BoundsCenter, BoundsExtent, BoundsRotation);

#if ENABLE_DRAW_DEBUG
	if (bDrawSegmentBounds)
	{
		DrawDebugBox(GetWorld(), BoundsCenter, BoundsExtent, BoundsRotation.Quaternion(), FColor::Orange, false, 15.f, 0, 30.f);
	}
#endif

	Segment->InitSegment(NextSegmentIndex++, Points, Tangents);
	Segments.Add(Segment);

	// Server only: this actor is not replicated, so HasAuthority() alone does not rule out a client.
	// Listeners should only queue work, as the wave spawner does (it spawns from its own tick)
	if (GetNetMode() != NM_Client)
	{
		OnSegmentSpawned.Broadcast(this, Segment);
	}

	// The fog stays in front of the new platforms while they spawn, then moves on
	if (!PathEndFogSystem.IsNull())
	{
		GetWorldTimerManager().SetTimer(PathEndFogTimerHandle, this, &ThisClass::UpdatePathEndFog, FMath::Max(PathEndFogMoveDelay, 0.01f), false);
	}
}


// =============================================================================
// Path-end fog
// =============================================================================

void AMyHexPathSpawner::UpdatePathEndFog()
{
	const int32 LastIndex = PathSpline->GetNumberOfSplinePoints() - 1;

	if (!HasAuthority() || PathEndFogSystem.IsNull() || PathEndFogCount <= 0 || LastIndex < 1)
	{
		return;
	}

	const float Scale = GetLayoutScale();
	const FVector End = PathSpline->GetLocationAtSplinePoint(LastIndex, ESplineCoordinateSpace::World);
	const FVector Heading = PathSpline->GetTangentAtSplinePoint(LastIndex, ESplineCoordinateSpace::World).GetSafeNormal2D();
	const FVector Across(-Heading.Y, Heading.X, 0.f);
	const float Yaw = Heading.Rotation().Yaw;

	for (int32 Index = 0; Index < PathEndFogCount; ++Index)
	{
		const float Offset = (Index - (PathEndFogCount - 1) * 0.5f) * PathEndFogSpacing * Scale;
		const FVector Location = End - Heading * PathEndFogBackOff * Scale + Across * Offset + FVector(0.f, 0.f, PathEndFogZOffset);

		// First call, or the bank is gone: spawn it. Its first SetMoveTarget below is a jump, later ones glide
		if (!PathEndFogs.IsValidIndex(Index) || !IsValid(PathEndFogs[Index]))
		{
			FActorSpawnParameters SpawnParams;
			SpawnParams.Owner = this;
			SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;

			const FTransform SpawnTransform(FRotator(0.f, Yaw, 0.f), Location, PathEndFogScale);
			AMyHexAtmosphereFX* Fog = GetWorld()->SpawnActor<AMyHexAtmosphereFXNet>(AMyHexAtmosphereFXNet::StaticClass(), SpawnTransform, SpawnParams);

			if (!Fog)
			{
				continue;
			}

			Fog->SetSystem(PathEndFogSystem);
			Fog->SetMoveSpeed(PathEndFogMoveSpeed);

			if (PathEndFogs.IsValidIndex(Index))
			{
				PathEndFogs[Index] = Fog;
			}
			else
			{
				PathEndFogs.Add(Fog);
			}
		}

		PathEndFogs[Index]->SetMoveTarget(Location, Yaw);
	}
}


// =============================================================================
// Destroy passed segments
// =============================================================================

void AMyHexPathSpawner::DestroyPassedSegments()
{
	if (DestroySegmentsBehindDistance <= 0.f)
	{
		return;
	}

	const float BehindDistance = DestroySegmentsBehindDistance * GetLayoutScale();

	const UMyHexBridgeSubsystem* Subsystem = GetWorld()->GetSubsystem<UMyHexBridgeSubsystem>();
	float LeadDistance = 0.f;

	if (!Subsystem || Subsystem->GetPathSpline() != PathSpline.Get() || !Subsystem->GetLeadPathDistance(LeadDistance))
	{
		return;
	}

	// Segments are in path order, so stop at the first one that isn't far enough behind.
	// Safe for the platforms: PCG doesn't delete the actors it spawned when its component is torn down.
	while (Segments.Num() > 0
		&& (!IsValid(Segments[0]) || Segments[0]->GetPathEndDistance() < LeadDistance - BehindDistance))
	{
		if (IsValid(Segments[0]))
		{
			Segments[0]->Destroy();
		}

		Segments.RemoveAt(0);
	}
}


// =============================================================================
// Segment bounds
// =============================================================================

void AMyHexPathSpawner::ComputeSegmentBounds(float StartDistance, float EndDistance, FVector& OutCenter, FVector& OutExtent, FRotator& OutRotation) const
{
	const float Scale = GetLayoutScale();
	const float D0 = StartDistance;
	const float D1 = FMath::Max(EndDistance, StartDistance);

	const FVector P0 = PathSpline->GetLocationAtDistanceAlongSpline(D0, ESplineCoordinateSpace::World);
	const FVector P1 = PathSpline->GetLocationAtDistanceAlongSpline(D1, ESplineCoordinateSpace::World);

	// Box X: from the segment's start to its end, horizontal
	FVector Forward = (P1 - P0).GetSafeNormal2D();

	if (Forward.IsNearlyZero())
	{
		Forward = PathSpline->GetTangentAtDistanceAlongSpline(D0, ESplineCoordinateSpace::World).GetSafeNormal2D();
	}

	if (Forward.IsNearlyZero())
	{
		Forward = GetActorForwardVector().GetSafeNormal2D();
	}

	if (Forward.IsNearlyZero())
	{
		Forward = FVector::ForwardVector;
	}

	// Box Y, the same across vector as the path-end fog's
	const FVector Across(-Forward.Y, Forward.X, 0.0);

	const double HalfWidth = double(SegmentBoundsHalfWidth) * Scale;
	const double BackReach = double(SegmentBoundsBackReach) * Scale;

	// Box-space extremes, relative to P0. P0 itself lies between its own two candidates, so it starts them
	double MinU = 0.0;
	double MaxU = 0.0;
	double MinV = 0.0;
	double MaxV = 0.0;
	double MinZ = P0.Z;
	double MaxZ = P0.Z;

	auto AddCandidate = [&](const FVector& Candidate)
	{
		const FVector Offset = Candidate - P0;
		const double U = FVector::DotProduct(Offset, Forward);
		const double V = FVector::DotProduct(Offset, Across);

		MinU = FMath::Min(MinU, U);
		MaxU = FMath::Max(MaxU, U);
		MinV = FMath::Min(MinV, V);
		MaxV = FMath::Max(MaxV, V);
	};

	auto AddSample = [&](float Distance, bool bWithBackReach)
	{
		const FVector Location = PathSpline->GetLocationAtDistanceAlongSpline(Distance, ESplineCoordinateSpace::World);
		FVector Tangent = PathSpline->GetTangentAtDistanceAlongSpline(Distance, ESplineCoordinateSpace::World).GetSafeNormal2D();

		if (Tangent.IsNearlyZero())
		{
			Tangent = Forward;
		}

		// Across the path at this sample, both sides
		const FVector Side = FVector(-Tangent.Y, Tangent.X, 0.0) * HalfWidth;

		AddCandidate(Location + Side);
		AddCandidate(Location - Side);

		if (bWithBackReach)
		{
			const FVector Back = Location - Tangent * BackReach;

			AddCandidate(Back + Side);
			AddCandidate(Back - Side);
		}

		MinZ = FMath::Min(MinZ, double(Location.Z));
		MaxZ = FMath::Max(MaxZ, double(Location.Z));
	};

	// Every spacing from the start, plus the end. At most 512 steps whatever the settings
	const float Length = D1 - D0;
	const float Step = FMath::Max3(FMath::Max(SegmentBoundsSampleSpacing, 50.f) * Scale, Length / 512.f, 1.f);
	const int32 NumSteps = FMath::Clamp(FMath::CeilToInt32(Length / Step), 1, 512);

	for (int32 Index = 0; Index <= NumSteps; ++Index)
	{
		const float Distance = Index < NumSteps ? D0 + Step * Index : D1;

		AddSample(Distance, Index == 0 && BackReach > 0.0);
	}

	// Heights are not scaled. Min / max in case of negative settings
	const double BottomZ = FMath::Min(MinZ - SegmentBoundsBelow, MaxZ + SegmentBoundsAbove);
	const double TopZ = FMath::Max(MinZ - SegmentBoundsBelow, MaxZ + SegmentBoundsAbove);

	OutCenter = P0 + Forward * ((MinU + MaxU) * 0.5) + Across * ((MinV + MaxV) * 0.5);
	OutCenter.Z = (BottomZ + TopZ) * 0.5;
	OutExtent = FVector((MaxU - MinU) * 0.5, (MaxV - MinV) * 0.5, (TopZ - BottomZ) * 0.5);
	OutRotation = FRotator(0.0, Forward.Rotation().Yaw, 0.0);
}


// =============================================================================
// Noise
// =============================================================================

float AMyHexPathSpawner::SampleNoise(float Value) const
{
	constexpr float PerlinGain = 2.f;

	return FMath::Clamp(FMath::PerlinNoise1D(Value) * PerlinGain, -1.f, 1.f);
}
