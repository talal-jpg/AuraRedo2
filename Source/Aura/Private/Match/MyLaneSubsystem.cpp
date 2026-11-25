// Fill out your copyright notice in the Description page of Project Settings.


#include "Match/MyLaneSubsystem.h"

#include "Actors/MyHexPathSpawner.h"
#include "Airship/AirshipLaneComponent.h"
#include "Airship/AirshipPawn.h"
#include "Airship/AirshipSubsystem.h"
#include "Components/SplineComponent.h"
#include "DrawDebugHelpers.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Character.h"
#include "HAL/IConsoleManager.h"
#include "Interfaces/MyCombatInterface.h"
#include "Match/MyMatchSettings.h"
#include "Match/MyTeamLibrary.h"
#include "MyGameMode.h"
#include "MyGameState.h"
#include "MyPlayerState.h"

DEFINE_LOG_CATEGORY(LogLane);

// Named, not anonymous: the unity build compiles this file together with others
namespace MyLaneSubsystemPrivate
{
	TAutoConsoleVariable<int32> CVarLaneDebug(
		TEXT("Aura.Lane.Debug"),
		0,
		TEXT("Team lanes debug draw (server): 0 off, 1 both lanes, the field limits, the cruise end and each team ship's lane target, 2 plus the look-ahead sweeps."),
		ECVF_Default
	);

	/** The actor tag that gives the lane frame on a map without a path spawner (tests). */
	const FName MatchLaneOriginTag(TEXT("MatchLaneOrigin"));

	/** 2D distance from P to the segment A-B. */
	double PointSegmentDistance2D(const FVector2D& P, const FVector2D& A, const FVector2D& B)
	{
		const FVector2D AB = B - A;
		const double LengthSq = AB.SizeSquared();
		const double T = LengthSq > UE_KINDA_SMALL_NUMBER ? FMath::Clamp(FVector2D::DotProduct(P - A, AB) / LengthSq, 0.0, 1.0) : 0.0;
		return FVector2D::Distance(P, A + AB * T);
	}
}


// =============================================================================
// Subsystem
// =============================================================================

UMyLaneSubsystem* UMyLaneSubsystem::Get(const UObject* WorldContext)
{
	const UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	return World ? World->GetSubsystem<UMyLaneSubsystem>() : nullptr;
}

bool UMyLaneSubsystem::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

void UMyLaneSubsystem::OnWorldBeginPlay(UWorld& InWorld)
{
	Super::OnWorldBeginPlay(InWorld);

	// The path spline lives on the server only (the spawner doesn't replicate)
	if (InWorld.GetNetMode() == NM_Client)
	{
		return;
	}

	// No match, no team ships: nothing here should cost anything. InitGame has decided it by now (it runs before
	// BeginPlay), and a match turned on later only counts from the next map load (B2.10).
	const AMyGameMode* GameMode = InWorld.GetAuthGameMode<AMyGameMode>();

	if (!GameMode || !GameMode->IsMatchOn())
	{
		return;
	}

	bActive = true;

	// A level has one path spawner (the spawner's own lookup takes the first too). This runs before any actor's
	// BeginPlay: the spawner builds its first segments in its BeginPlay and each one arrives in HandleSegmentSpawned.
	TActorIterator<AMyHexPathSpawner> It(&InWorld);

	if (It)
	{
		Spawner = *It;
		Source = ELaneSource::Spawner;
		It->OnSegmentSpawned.AddDynamic(this, &ThisClass::HandleSegmentSpawned);

		// Bound late (the spawner already built segments): catch up
		if (It->GetSegments().Num() > 0)
		{
			BuildFromSpawner(/*bFull=*/true);
		}
		return;
	}

	for (TActorIterator<AActor> ActorIt(&InWorld); ActorIt; ++ActorIt)
	{
		if (ActorIt->ActorHasTag(MyLaneSubsystemPrivate::MatchLaneOriginTag))
		{
			BuildFromOrigin(*ActorIt);
			return;
		}
	}

	LogNoLanesOnce(TEXT("no AMyHexPathSpawner and no actor tagged MatchLaneOrigin in the level"));
}

void UMyLaneSubsystem::Deinitialize()
{
	if (AMyHexPathSpawner* PathSpawner = Spawner.Get())
	{
		PathSpawner->OnSegmentSpawned.RemoveDynamic(this, &ThisClass::HandleSegmentSpawned);
	}

	Spawner.Reset();
	OriginActor.Reset();
	Samples.Empty();
	SampleDistances.Empty();
	SortedSamples.Empty();
	GridPathV.Empty();
	GridPathZ.Empty();
	GridRawRight.Empty();
	GridRawLeft.Empty();
	GridRight.Empty();
	GridLeft.Empty();
	bHasLanes = false;
	bActive = false;
	OnLanesChanged.Clear();

	Super::Deinitialize();
}

void UMyLaneSubsystem::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);

	DrawDebug(0.f);
}

bool UMyLaneSubsystem::IsTickable() const
{
	return bHasLanes && GetDebugLevel() >= 1;
}

TStatId UMyLaneSubsystem::GetStatId() const
{
	RETURN_QUICK_DECLARE_CYCLE_STAT(UMyLaneSubsystem, STATGROUP_Tickables);
}

int32 UMyLaneSubsystem::GetDebugLevel()
{
	return MyLaneSubsystemPrivate::CVarLaneDebug.GetValueOnGameThread();
}

void UMyLaneSubsystem::LogNoLanesOnce(const TCHAR* Why)
{
	if (!bLoggedNoLanes)
	{
		bLoggedNoLanes = true;
		UE_LOG(LogLane, Warning, TEXT("No team lanes: %s. Team ships fly as PR A ships (no cruise, no recall)."), Why);
	}
}


// =============================================================================
// Build
// =============================================================================

void UMyLaneSubsystem::HandleSegmentSpawned(AMyHexPathSpawner* PathSpawner, AMyHexPathSegment* Segment)
{
	if (PathSpawner && PathSpawner == Spawner.Get())
	{
		BuildFromSpawner(/*bFull=*/false);
	}
}

void UMyLaneSubsystem::RebuildLanes()
{
	if (!bActive)
	{
		UE_LOG(LogLane, Warning, TEXT("Lanes: no rebuild, the lanes are off (no match on this map, or a client)"));
		return;
	}

	if (Source == ELaneSource::Spawner)
	{
		// The frame is taken again too (a test may have moved the spawner before the first segment)
		bFrameReady = false;
		BuildFromSpawner(/*bFull=*/true);
	}
	else if (Source == ELaneSource::Origin && OriginActor.IsValid())
	{
		BuildFromOrigin(OriginActor.Get());
	}
	else
	{
		UE_LOG(LogLane, Warning, TEXT("Lanes: no rebuild, no lane source in this level"));
	}
}

bool UMyLaneSubsystem::RefreshGeometrySettings(float NewScale, float NewHalfWidth)
{
	const UMyMatchSettings* M = UMyMatchSettings::Get();
	const float Scale = FMath::Max(NewScale, 0.01f);

	// Aura.Match.Set skips the ClampMin metadata: keep a sane step
	const float NewStep = FMath::Max(M->LaneSampleStep * Scale, 10.f);
	const float NewBackReach = FMath::Max(M->LaneBackReach * Scale, 0.f);
	const float NewSmooth = FMath::Max(M->LaneSmoothHalfWindow * Scale, 0.f);
	const float NewOffset = FMath::Max(NewHalfWidth, 0.f) + FMath::Max(M->LaneClearance, 0.f);

	const bool bChanged = !FMath::IsNearlyEqual(Scale, LayoutScale)
		|| !FMath::IsNearlyEqual(NewStep, SampleStep)
		|| !FMath::IsNearlyEqual(NewBackReach, BackReach)
		|| !FMath::IsNearlyEqual(NewSmooth, SmoothHalfWindow)
		|| !FMath::IsNearlyEqual(NewOffset, LaneOffset)
		|| !FMath::IsNearlyEqual(M->LaneHeight, LaneHeight);

	LayoutScale = Scale;
	HalfWidth = FMath::Max(NewHalfWidth, 0.f);
	LaneOffset = NewOffset;
	SampleStep = NewStep;
	CellStep = NewStep;
	BackReach = NewBackReach;
	SmoothHalfWindow = NewSmooth;
	LaneHeight = M->LaneHeight;

	return bChanged;
}

void UMyLaneSubsystem::BuildFromSpawner(bool bFull)
{
	AMyHexPathSpawner* PathSpawner = Spawner.Get();
	const USplineComponent* Spline = PathSpawner ? PathSpawner->GetPathSpline() : nullptr;
	const int32 NumPoints = Spline ? Spline->GetNumberOfSplinePoints() : 0;

	if (!Spline || NumPoints < 2)
	{
		return;
	}

	const UMyMatchSettings* M = UMyMatchSettings::Get();

	// The frame: the spawner set StartYaw in its BeginPlay, before its first segment (the first call lands here)
	if (!bFrameReady)
	{
		Origin = Spline->GetLocationAtSplinePoint(0, ESplineCoordinateSpace::World);
		StartYawDeg = PathSpawner->GetStartYaw();
		const double YawRad = FMath::DegreesToRadians(static_cast<double>(StartYawDeg));
		Forward = FVector2D(FMath::Cos(YawRad), FMath::Sin(YawRad));
		Right = FVector2D(-Forward.Y, Forward.X);
		bFrameReady = true;
		bFull = true;

		// For MaxYawDeviation < 90 the path never doubles back, so u grows along it and the lane is a function of u
		bStraight = PathSpawner->GetMaxYawDeviation() >= M->MaxYawForEnvelope;

		if (bStraight)
		{
			UE_LOG(LogLane, Error, TEXT("Lanes: %s's MaxYawDeviation %.0f >= MaxYawForEnvelope %.0f: the path could double back, so the lanes are straight lines at +-(H + LaneClearance) along the start heading and may cross the field"),
				*PathSpawner->GetName(), PathSpawner->GetMaxYawDeviation(), M->MaxYawForEnvelope);
		}
	}

	if (RefreshGeometrySettings(PathSpawner->GetLayoutScale(), PathSpawner->GetPathHalfWidth()))
	{
		bFull = true;
	}

	// Appending a point reshapes only the last span before it (the old end's auto tangent): samples from the point
	// before the old end on can move, earlier ones can't
	float FromDistance = 0.f;

	if (!bFull && SampledSplinePoints >= 2 && Samples.Num() > 0)
	{
		FromDistance = Spline->GetDistanceAlongSplineAtSplinePoint(FMath::Clamp(SampledSplinePoints - 2, 0, NumPoints - 1));
	}
	else
	{
		bFull = true;
	}

	const float OldPathEndU = PathEndU;

	if (bFull)
	{
		Samples.Reset();
		SampleDistances.Reset();
	}
	else
	{
		// Dropped: everything from the reshaped span on, the old end sample included
		while (SampleDistances.Num() > 0 && SampleDistances.Last() >= FromDistance - 1.f)
		{
			SampleDistances.Pop(EAllowShrinking::No);
			Samples.Pop(EAllowShrinking::No);
		}
	}

	float FirstChangedU = TNumericLimits<float>::Max();
	const float Length = Spline->GetSplineLength();

	auto AddSample = [&](float Distance)
	{
		const FVector Frame = ToFrame(Spline->GetLocationAtDistanceAlongSpline(Distance, ESplineCoordinateSpace::World));
		Samples.Add(Frame);
		SampleDistances.Add(Distance);
		FirstChangedU = FMath::Min(FirstChangedU, static_cast<float>(Frame.X));
	};

	// Every SampleStep along the spline, then its end
	int32 K = SampleDistances.Num() > 0 ? FMath::FloorToInt32(SampleDistances.Last() / SampleStep) + 1 : 0;

	for (; K * SampleStep < Length - 1.f; ++K)
	{
		AddSample(K * SampleStep);
	}

	AddSample(Length);
	SampledSplinePoints = NumPoints;

	// u grows along the path unless MaxYawDeviation lets it turn back
	bMonotonic = true;

	for (int32 Index = 1; Index < Samples.Num(); ++Index)
	{
		if (Samples[Index].X < Samples[Index - 1].X - 1.0)
		{
			bMonotonic = false;
			break;
		}
	}

	if (!bMonotonic)
	{
		SortedSamples = Samples;
		SortedSamples.Sort([](const FVector& A, const FVector& B) { return A.X < B.X; });

		if (!bStraight)
		{
			bStraight = true;
			bFull = true;
			UE_LOG(LogLane, Error, TEXT("Lanes: the path turns back along the start heading (MaxYawDeviation %.0f): straight lanes from now on"),
				PathSpawner->GetMaxYawDeviation());
		}
	}
	else
	{
		SortedSamples.Reset();
	}

	PathEndU = Samples.Last().X;

	// The spec's bound too (B2.2): a circle reaches R, so lane values up to 2R behind the old end may change
	if (!bFull)
	{
		FirstChangedU = FMath::Min(FirstChangedU, OldPathEndU - 2.f * LaneOffset);
	}

	const bool bFirst = !bHasLanes;
	RebuildGrid(FirstChangedU, bFull);
	bHasLanes = true;

	if (bFirst || bFull)
	{
		UE_LOG(LogLane, Log, TEXT("Lanes built from %s: S %.2f, H %.0f cm, lanes at +-%.0f cm (v), start (%.0f, %.0f, %.0f) yaw %.1f, LaneStartU %.0f, PathEndU %.0f, CruiseEndU %.0f, %d samples, %d cells%s"),
			*PathSpawner->GetName(), LayoutScale, HalfWidth, LaneOffset, Origin.X, Origin.Y, Origin.Z, StartYawDeg, GridStartU, PathEndU,
			GetCruiseEndU(), Samples.Num(), GridRight.Num(), bStraight ? TEXT(", STRAIGHT") : TEXT(""));
	}
	else
	{
		UE_LOG(LogLane, Verbose, TEXT("Lanes extended: PathEndU %.0f, CruiseEndU %.0f, from u %.0f"), PathEndU, GetCruiseEndU(), FirstChangedU);
	}

	OnLanesChanged.Broadcast();
}

void UMyLaneSubsystem::BuildFromOrigin(const AActor* InOriginActor)
{
	if (!IsValid(InOriginActor))
	{
		return;
	}

	const UMyMatchSettings* M = UMyMatchSettings::Get();

	Source = ELaneSource::Origin;
	OriginActor = InOriginActor;

	Origin = InOriginActor->GetActorLocation();
	StartYawDeg = static_cast<float>(InOriginActor->GetActorRotation().Yaw);
	const double YawRad = FMath::DegreesToRadians(static_cast<double>(StartYawDeg));
	Forward = FVector2D(FMath::Cos(YawRad), FMath::Sin(YawRad));
	Right = FVector2D(-Forward.Y, Forward.X);
	bFrameReady = true;
	bStraight = false;
	bMonotonic = true;

	// A straight virtual path along the actor's yaw, not scaled
	RefreshGeometrySettings(1.f, M->FallbackLaneHalfWidth);

	const float Length = FMath::Max(M->FallbackLaneLength, SampleStep);
	Samples.Reset();
	SampleDistances.Reset();
	SortedSamples.Reset();

	for (int32 K = 0; K * SampleStep < Length - 1.f; ++K)
	{
		Samples.Add(FVector(K * SampleStep, 0.0, Origin.Z));
		SampleDistances.Add(K * SampleStep);
	}

	Samples.Add(FVector(Length, 0.0, Origin.Z));
	SampleDistances.Add(Length);
	SampledSplinePoints = 0;
	PathEndU = Length;

	RebuildGrid(0.f, /*bFull=*/true);
	bHasLanes = true;

	UE_LOG(LogLane, Log, TEXT("Lanes built from %s (tag MatchLaneOrigin, no path spawner): H %.0f cm, lanes at +-%.0f cm, start (%.0f, %.0f, %.0f) yaw %.1f, LaneStartU %.0f, PathEndU %.0f, CruiseEndU %.0f"),
		*InOriginActor->GetName(), HalfWidth, LaneOffset, Origin.X, Origin.Y, Origin.Z, StartYawDeg, GridStartU, PathEndU, GetCruiseEndU());

	OnLanesChanged.Broadcast();
}

void UMyLaneSubsystem::RebuildGrid(float FirstChangedU, bool bFull)
{
	if (Samples.Num() == 0)
	{
		return;
	}

	// Cell ZeroCell sits exactly on u = 0, so the straight back reach starts at the path's first point
	GridStartU = -FMath::CeilToFloat(BackReach / CellStep) * CellStep;
	ZeroCell = FMath::RoundToInt32(-GridStartU / CellStep);

	const int32 NumCells = FMath::Max(ZeroCell + 2, FMath::FloorToInt32((PathEndU - GridStartU) / CellStep) + 2);
	const int32 OldNumCells = bFull ? 0 : GridRight.Num();

	GridPathV.SetNumZeroed(NumCells);
	GridPathZ.SetNumZeroed(NumCells);
	GridRawRight.SetNumZeroed(NumCells);
	GridRawLeft.SetNumZeroed(NumCells);
	GridRight.SetNumZeroed(NumCells);
	GridLeft.SetNumZeroed(NumCells);

	// Raw envelope from the first cell a changed sample's circle reaches; new cells always
	int32 RawFrom = 0;

	if (!bFull)
	{
		const float FromU = FirstChangedU - LaneOffset - CellStep;
		RawFrom = FMath::Clamp(FMath::FloorToInt32((FromU - GridStartU) / CellStep), 0, NumCells);
		RawFrom = FMath::Min(RawFrom, OldNumCells);
	}

	const TArray<FVector>& Sorted = GetSortedSamples();
	const double R = LaneOffset;
	const double RSq = R * R;

	for (int32 Cell = FMath::Max(RawFrom, ZeroCell); Cell < NumCells; ++Cell)
	{
		const float U = GridStartU + Cell * CellStep;
		float PathV = 0.f;
		float PathZ = 0.f;
		SamplePath(U, PathV, PathZ);
		GridPathV[Cell] = PathV;
		GridPathZ[Cell] = PathZ;

		if (bStraight)
		{
			GridRawRight[Cell] = LaneOffset;
			GridRawLeft[Cell] = -LaneOffset;
			continue;
		}

		// Outer envelope of the circles of radius R around every sample within R in u: every lane point is then at
		// least R from every sample, so at least LaneClearance from the field, whatever the bend
		double MaxRight = -TNumericLimits<double>::Max();
		double MinLeft = TNumericLimits<double>::Max();
		int32 First = 0;
		int32 Last = -1;

		if (FindSampleWindow(U - LaneOffset, U + LaneOffset, First, Last))
		{
			for (int32 Index = First; Index <= Last; ++Index)
			{
				const double Du = Sorted[Index].X - U;
				const double Reach = FMath::Sqrt(FMath::Max(RSq - Du * Du, 0.0));
				MaxRight = FMath::Max(MaxRight, Sorted[Index].Y + Reach);
				MinLeft = FMath::Min(MinLeft, Sorted[Index].Y - Reach);
			}
		}

		GridRawRight[Cell] = MaxRight > -TNumericLimits<double>::Max() ? static_cast<float>(MaxRight) : PathV + LaneOffset;
		GridRawLeft[Cell] = MinLeft < TNumericLimits<double>::Max() ? static_cast<float>(MinLeft) : PathV - LaneOffset;
	}

	// Before the path start the lane runs straight back along the start heading
	if (RawFrom <= ZeroCell)
	{
		for (int32 Cell = 0; Cell < ZeroCell; ++Cell)
		{
			GridPathV[Cell] = GridPathV[ZeroCell];
			GridPathZ[Cell] = GridPathZ[ZeroCell];
			GridRawRight[Cell] = GridRawRight[ZeroCell];
			GridRawLeft[Cell] = GridRawLeft[ZeroCell];
		}
	}

	// Moving average over +-SmoothHalfWindow, then the max with the unsmoothed envelope (min on the left): it lifts the
	// kinks where two circles meet and never pulls the lane in at an arc's peak, so smoothing only moves it outward
	const int32 Window = bStraight ? 0 : FMath::Max(FMath::RoundToInt32(SmoothHalfWindow / CellStep), 0);
	const int32 SmoothFrom = FMath::Max(RawFrom - Window, 0);

	for (int32 Cell = SmoothFrom; Cell < NumCells; ++Cell)
	{
		const int32 A = FMath::Max(Cell - Window, 0);
		const int32 B = FMath::Min(Cell + Window, NumCells - 1);
		double SumRight = 0.0;
		double SumLeft = 0.0;

		for (int32 Index = A; Index <= B; ++Index)
		{
			SumRight += GridRawRight[Index];
			SumLeft += GridRawLeft[Index];
		}

		const double Count = static_cast<double>(B - A + 1);
		GridRight[Cell] = FMath::Max(GridRawRight[Cell], static_cast<float>(SumRight / Count));
		GridLeft[Cell] = FMath::Min(GridRawLeft[Cell], static_cast<float>(SumLeft / Count));
	}

	// The back reach stays exactly straight (the average next to u = 0 would bend it)
	if (SmoothFrom <= ZeroCell)
	{
		for (int32 Cell = 0; Cell < ZeroCell; ++Cell)
		{
			GridRight[Cell] = GridRight[ZeroCell];
			GridLeft[Cell] = GridLeft[ZeroCell];
		}
	}
}


// =============================================================================
// Queries
// =============================================================================

FVector UMyLaneSubsystem::ToFrame(const FVector& World) const
{
	const FVector2D Offset(World.X - Origin.X, World.Y - Origin.Y);
	return FVector(FVector2D::DotProduct(Offset, Forward), FVector2D::DotProduct(Offset, Right), World.Z);
}

FVector UMyLaneSubsystem::FromFrame(float U, float V, float Z) const
{
	const FVector2D XY = FVector2D(Origin.X, Origin.Y) + Forward * U + Right * V;
	return FVector(XY.X, XY.Y, Z);
}

bool UMyLaneSubsystem::FindSampleWindow(float UMin, float UMax, int32& OutFirst, int32& OutLast) const
{
	const TArray<FVector>& Sorted = GetSortedSamples();
	const int32 Num = Sorted.Num();

	if (Num == 0 || UMax < UMin)
	{
		return false;
	}

	// First with u >= UMin
	int32 Low = 0;
	int32 High = Num;

	while (Low < High)
	{
		const int32 Mid = (Low + High) / 2;

		if (Sorted[Mid].X < UMin)
		{
			Low = Mid + 1;
		}
		else
		{
			High = Mid;
		}
	}

	OutFirst = Low;

	// Last with u <= UMax
	Low = OutFirst;
	High = Num;

	while (Low < High)
	{
		const int32 Mid = (Low + High) / 2;

		if (Sorted[Mid].X <= UMax)
		{
			Low = Mid + 1;
		}
		else
		{
			High = Mid;
		}
	}

	OutLast = Low - 1;
	return OutFirst <= OutLast;
}

void UMyLaneSubsystem::SamplePath(float U, float& OutV, float& OutZ) const
{
	const TArray<FVector>& Sorted = GetSortedSamples();
	const int32 Num = Sorted.Num();

	if (Num == 0)
	{
		OutV = 0.f;
		OutZ = static_cast<float>(Origin.Z);
		return;
	}

	if (U <= Sorted[0].X || Num == 1)
	{
		OutV = static_cast<float>(Sorted[0].Y);
		OutZ = static_cast<float>(Sorted[0].Z);
		return;
	}

	if (U >= Sorted.Last().X)
	{
		OutV = static_cast<float>(Sorted.Last().Y);
		OutZ = static_cast<float>(Sorted.Last().Z);
		return;
	}

	// First sample past U (exists: U is inside the range)
	int32 Low = 1;
	int32 High = Num - 1;

	while (Low < High)
	{
		const int32 Mid = (Low + High) / 2;

		if (Sorted[Mid].X <= U)
		{
			Low = Mid + 1;
		}
		else
		{
			High = Mid;
		}
	}

	const FVector& A = Sorted[Low - 1];
	const FVector& B = Sorted[Low];
	const double Span = B.X - A.X;
	const double T = Span > UE_KINDA_SMALL_NUMBER ? FMath::Clamp((U - A.X) / Span, 0.0, 1.0) : 0.0;
	OutV = static_cast<float>(FMath::Lerp(A.Y, B.Y, T));
	OutZ = static_cast<float>(FMath::Lerp(A.Z, B.Z, T));
}

void UMyLaneSubsystem::SampleLane(int8 Side, float U, float& OutV, float& OutZ, float& OutDvDu, float& OutDzDu) const
{
	const TArray<float>& Lane = Side > 0 ? GridRight : GridLeft;
	const int32 Num = Lane.Num();

	if (Num < 2)
	{
		OutV = Side > 0 ? LaneOffset : -LaneOffset;
		OutZ = static_cast<float>(Origin.Z) + LaneHeight;
		OutDvDu = 0.f;
		OutDzDu = 0.f;
		return;
	}

	const float Clamped = FMath::Clamp(U, GridStartU, FMath::Max(PathEndU, GridStartU));
	const float F = (Clamped - GridStartU) / CellStep;
	const int32 Cell = FMath::Clamp(FMath::FloorToInt32(F), 0, Num - 2);
	const float T = FMath::Clamp(F - Cell, 0.f, 1.f);

	// Central differences per cell, blended: the heading turns smoothly instead of stepping at every cell
	auto Slope = [this, Num](const TArray<float>& Values, int32 At)
	{
		const int32 A = FMath::Max(At - 1, 0);
		const int32 B = FMath::Min(At + 1, Num - 1);
		return B > A ? (Values[B] - Values[A]) / ((B - A) * CellStep) : 0.f;
	};

	OutV = FMath::Lerp(Lane[Cell], Lane[Cell + 1], T);
	OutZ = FMath::Lerp(GridPathZ[Cell], GridPathZ[Cell + 1], T) + LaneHeight;
	OutDvDu = FMath::Lerp(Slope(Lane, Cell), Slope(Lane, Cell + 1), T);
	OutDzDu = FMath::Lerp(Slope(GridPathZ, Cell), Slope(GridPathZ, Cell + 1), T);
}

int8 UMyLaneSubsystem::GetSideForTeam(uint8 TeamId) const
{
	const UMyMatchSettings* M = UMyMatchSettings::Get();
	const int8 Base = M->GetBaseLaneSide(TeamId);

	if (Base == 0)
	{
		return 0;
	}

	// Odd versus rounds swap the sides, so the start floor's side alternates between the teams (B1.6). The game mode
	// decides it when the round's countdown starts (bAlternateSides, the round, versus or not): a practice round keeps
	// round 0's sides, so its lone ship isn't put on the lane about 274 m from the floor, and nothing flips mid-round
	const UWorld* World = GetWorld();
	const AMyGameState* GameState = World ? World->GetGameState<AMyGameState>() : nullptr;

	return (GameState && GameState->AreLaneSidesSwapped()) ? static_cast<int8>(-Base) : Base;
}

float UMyLaneSubsystem::ProjectU(const FVector& World) const
{
	return bFrameReady ? static_cast<float>(ToFrame(World).X) : 0.f;
}

float UMyLaneSubsystem::GetLateralFromPath(const FVector& World) const
{
	if (!bHasLanes)
	{
		return 0.f;
	}

	const FVector Frame = ToFrame(World);
	float PathV = 0.f;
	float PathZ = 0.f;
	SamplePath(static_cast<float>(Frame.X), PathV, PathZ);
	return static_cast<float>(Frame.Y) - PathV;
}

float UMyLaneSubsystem::GetPathZ(float U) const
{
	if (!bHasLanes)
	{
		return static_cast<float>(Origin.Z);
	}

	float PathV = 0.f;
	float PathZ = 0.f;
	SamplePath(U, PathV, PathZ);
	return PathZ;
}

bool UMyLaneSubsystem::GetLanePoint(int8 Side, float U, FVector& OutLocation, FVector& OutTangent) const
{
	if (!bHasLanes || Side == 0)
	{
		return false;
	}

	const float Clamped = FMath::Clamp(U, GridStartU, FMath::Max(PathEndU, GridStartU));
	float V = 0.f;
	float Z = 0.f;
	float DvDu = 0.f;
	float DzDu = 0.f;
	SampleLane(Side, Clamped, V, Z, DvDu, DzDu);

	OutLocation = FromFrame(Clamped, V, Z);

	const FVector2D Along = Forward + Right * DvDu;
	OutTangent = FVector(Along.X, Along.Y, DzDu).GetSafeNormal();

	if (OutTangent.IsNearlyZero())
	{
		OutTangent = FVector(Forward.X, Forward.Y, 0.0);
	}

	return true;
}

float UMyLaneSubsystem::GetCruiseEndU() const
{
	return FMath::Max(GridStartU, PathEndU - UMyMatchSettings::Get()->LaneEndMargin * LayoutScale);
}

bool UMyLaneSubsystem::GetTeamFrontU(uint8 TeamId, float& OutU) const
{
	const UWorld* World = GetWorld();
	const AGameStateBase* GameState = World ? World->GetGameState() : nullptr;

	if (!bFrameReady || !GameState)
	{
		return false;
	}

	bool bFound = false;
	float Best = 0.f;

	for (const APlayerState* PlayerState : GameState->PlayerArray)
	{
		const AMyPlayerState* MyPlayerState = Cast<AMyPlayerState>(PlayerState);

		if (!MyPlayerState || (TeamId != MyMatch::NoTeam && MyPlayerState->GetTeamId() != TeamId))
		{
			continue;
		}

		// On foot: his own living character, not at a helm (then his pawn is the ship), a station or on a deck
		APawn* Pawn = MyPlayerState->GetPawn();

		if (!IsValid(Pawn) || !Pawn->IsA<ACharacter>() || UAirshipSubsystem::IsShipBorne(Pawn))
		{
			continue;
		}

		if (Pawn->Implements<UMyCombatInterface>() && IMyCombatInterface::Execute_IsDead(Pawn))
		{
			continue;
		}

		const float U = ProjectU(Pawn->GetActorLocation());

		if (!bFound || U > Best)
		{
			Best = U;
			bFound = true;
		}
	}

	OutU = Best;
	return bFound;
}

bool UMyLaneSubsystem::GetSpawnTransform(uint8 TeamId, float U, FTransform& Out) const
{
	FVector Location;
	FVector Tangent;

	if (!GetLanePoint(GetSideForTeam(TeamId), U, Location, Tangent))
	{
		return false;
	}

	Out = FTransform(FRotator(0.0, Tangent.Rotation().Yaw, 0.0), Location);
	return true;
}

float UMyLaneSubsystem::DistanceToPathUV(float U, float V, float Window) const
{
	using namespace MyLaneSubsystemPrivate;

	const FVector2D P(U, V);
	double Best = TNumericLimits<double>::Max();

	// A path that turns back: its samples sorted by u aren't neighbours along it, so test every span
	if (!bMonotonic)
	{
		for (int32 Index = 1; Index < Samples.Num(); ++Index)
		{
			Best = FMath::Min(Best, PointSegmentDistance2D(P, FVector2D(Samples[Index - 1]), FVector2D(Samples[Index])));
		}
		return static_cast<float>(Best);
	}

	int32 First = 0;
	int32 Last = -1;

	if (!FindSampleWindow(U - Window, U + Window, First, Last))
	{
		// Beyond either end of the path: its end point is the nearest
		if (Samples.Num() > 0)
		{
			const FVector& End = U < Samples[0].X ? Samples[0] : Samples.Last();
			return static_cast<float>(FVector2D::Distance(P, FVector2D(End)));
		}
		return static_cast<float>(Best);
	}

	// One more span each side, so the nearest span crossing the window edge counts
	First = FMath::Max(First - 1, 0);
	Last = FMath::Min(Last + 1, Samples.Num() - 1);

	if (First == Last)
	{
		return static_cast<float>(FVector2D::Distance(P, FVector2D(Samples[First])));
	}

	for (int32 Index = First + 1; Index <= Last; ++Index)
	{
		Best = FMath::Min(Best, PointSegmentDistance2D(P, FVector2D(Samples[Index - 1]), FVector2D(Samples[Index])));
	}

	return static_cast<float>(Best);
}

float UMyLaneSubsystem::GetDistanceToPath2D(const FVector& World) const
{
	if (!bHasLanes)
	{
		return TNumericLimits<float>::Max();
	}

	const FVector Frame = ToFrame(World);
	const float Window = 2.f * LaneOffset;
	const float Near = DistanceToPathUV(static_cast<float>(Frame.X), static_cast<float>(Frame.Y), Window);

	// Farther than the window: a point outside it could be nearer, look at the whole path
	return Near <= Window ? Near : DistanceToPathUV(static_cast<float>(Frame.X), static_cast<float>(Frame.Y), TNumericLimits<float>::Max() * 0.25f);
}

bool UMyLaneSubsystem::DoesSegmentCrossField(const FVector& A, const FVector& B, float Margin) const
{
	using namespace MyLaneSubsystemPrivate;

	if (!bHasLanes)
	{
		return false;
	}

	const FVector FA = ToFrame(A);
	const FVector FB = ToFrame(B);
	const FVector2D A2(FA);
	const FVector2D B2(FB);

	// Strictly within (1 m less): a lane point is exactly H + LaneClearance from its nearest samples, so a segment that
	// only ends on the lane must not count
	const double Limit = HalfWidth + Margin - 100.0;

	// Every sample within Limit of the segment (samples are at most SampleStep apart, so a span can't slip through)
	auto Near = [&](const FVector& Sample)
	{
		return PointSegmentDistance2D(FVector2D(Sample), A2, B2) < Limit;
	};

	if (!bMonotonic)
	{
		for (const FVector& Sample : Samples)
		{
			if (Near(Sample))
			{
				return true;
			}
		}
		return false;
	}

	int32 First = 0;
	int32 Last = -1;

	if (!FindSampleWindow(static_cast<float>(FMath::Min(FA.X, FB.X) - Limit), static_cast<float>(FMath::Max(FA.X, FB.X) + Limit), First, Last))
	{
		return false;
	}

	for (int32 Index = First; Index <= Last; ++Index)
	{
		if (Near(Samples[Index]))
		{
			return true;
		}
	}

	return false;
}

bool UMyLaneSubsystem::CheckHullClearanceSide(int8 Side, float& OutMinGapCm, float& OutAtU) const
{
	OutMinGapCm = TNumericLimits<float>::Max();
	OutAtU = 0.f;

	if (!bHasLanes || Side == 0 || GridRight.Num() < 2)
	{
		return false;
	}

	const float HalfLength = HullCheckLength * 0.5f;
	const float HalfWidthHull = HullCheckWidth * 0.5f;
	const float Window = LaneOffset + HalfLength + 2.f * CellStep;

	// The footprint's outline, every 5 m or closer
	constexpr float OutlineStep = 500.f;
	const int32 StepsLength = FMath::Max(FMath::CeilToInt32(HullCheckLength / OutlineStep), 1);
	const int32 StepsWidth = FMath::Max(FMath::CeilToInt32(HullCheckWidth / OutlineStep), 1);

	for (int32 Cell = 0; Cell < GridRight.Num(); ++Cell)
	{
		const float U = GridStartU + Cell * CellStep;

		if (U > PathEndU)
		{
			break;
		}

		float V = 0.f;
		float Z = 0.f;
		float DvDu = 0.f;
		float DzDu = 0.f;
		SampleLane(Side, U, V, Z, DvDu, DzDu);

		// In the frame (u, v are orthonormal): the hull lies along the lane tangent
		const FVector2D Center(U, V);
		const FVector2D T = FVector2D(1.0, DvDu).GetSafeNormal();
		const FVector2D N(-T.Y, T.X);

		auto Measure = [&](const FVector2D& Q)
		{
			const float Gap = DistanceToPathUV(static_cast<float>(Q.X), static_cast<float>(Q.Y), Window) - HalfWidth;

			if (Gap < OutMinGapCm)
			{
				OutMinGapCm = Gap;
				OutAtU = U;
			}
		};

		for (int32 Step = 0; Step <= StepsLength; ++Step)
		{
			const double Along = -HalfLength + HullCheckLength * Step / StepsLength;
			Measure(Center + T * Along + N * HalfWidthHull);
			Measure(Center + T * Along - N * HalfWidthHull);
		}

		for (int32 Step = 1; Step < StepsWidth; ++Step)
		{
			const double Across = -HalfWidthHull + HullCheckWidth * Step / StepsWidth;
			Measure(Center + T * HalfLength + N * Across);
			Measure(Center - T * HalfLength + N * Across);
		}
	}

	return OutMinGapCm < TNumericLimits<float>::Max();
}

bool UMyLaneSubsystem::CheckHullClearance(float& OutMinGapCm, float& OutAtU) const
{
	float GapRight = 0.f;
	float AtRight = 0.f;
	float GapLeft = 0.f;
	float AtLeft = 0.f;
	const bool bRight = CheckHullClearanceSide(1, GapRight, AtRight);
	const bool bLeft = CheckHullClearanceSide(-1, GapLeft, AtLeft);

	if (!bRight && !bLeft)
	{
		OutMinGapCm = 0.f;
		OutAtU = 0.f;
		return false;
	}

	const bool bRightSmaller = bRight && (!bLeft || GapRight <= GapLeft);
	OutMinGapCm = bRightSmaller ? GapRight : GapLeft;
	OutAtU = bRightSmaller ? AtRight : AtLeft;
	return true;
}


// =============================================================================
// Debug draw
// =============================================================================

void UMyLaneSubsystem::DrawDebug(float Duration) const
{
#if ENABLE_DRAW_DEBUG
	const UWorld* World = GetWorld();

	if (!World || !bHasLanes || GridRight.Num() < 2)
	{
		return;
	}

	const bool bPersistent = Duration < 0.f;
	const int32 Num = GridRight.Num();

	// At most about 1500 pieces per line, whatever the path length
	const int32 Stride = FMath::Max(1, Num / 1500);
	const float LastU = FMath::Min(PathEndU, GridStartU + (Num - 1) * CellStep);

	auto LaneAt = [this](int8 Side, float U)
	{
		FVector Location;
		FVector Tangent;
		GetLanePoint(Side, U, Location, Tangent);
		return Location;
	};

	auto PathAt = [this](float U, float Offset)
	{
		float PathV = 0.f;
		float PathZ = 0.f;
		SamplePath(U, PathV, PathZ);
		return FromFrame(U, PathV + Offset, PathZ);
	};

	for (int8 Side : { static_cast<int8>(1), static_cast<int8>(-1) })
	{
		// The lane in the colour of the team on that side this round
		uint8 Team = MyMatch::NoTeam;

		for (uint8 Candidate = 0; Candidate < MyMatch::NumTeams; ++Candidate)
		{
			if (GetSideForTeam(Candidate) == Side)
			{
				Team = Candidate;
			}
		}

		const FColor LaneColor = Team != MyMatch::NoTeam ? UMyTeamLibrary::GetTeamColor(Team).ToFColor(true) : FColor::White;
		const FColor FieldColor(110, 110, 110);
		FVector PreviousLane = LaneAt(Side, GridStartU);
		FVector PreviousField = PathAt(FMath::Max(GridStartU, 0.f), Side * HalfWidth);

		for (int32 Cell = Stride; ; Cell += Stride)
		{
			const float U = FMath::Min(GridStartU + Cell * CellStep, LastU);
			const FVector Lane = LaneAt(Side, U);
			DrawDebugLine(World, PreviousLane, Lane, LaneColor, bPersistent, Duration, 0, 40.f);
			PreviousLane = Lane;

			if (U >= 0.f)
			{
				const FVector Field = PathAt(U, Side * HalfWidth);
				DrawDebugLine(World, PreviousField, Field, FieldColor, bPersistent, Duration, 0, 15.f);
				PreviousField = Field;
			}

			if (U >= LastU)
			{
				break;
			}
		}

		// Cruise end (yellow) and path end (red) across the lane
		const FVector Cruise = LaneAt(Side, GetCruiseEndU());
		const FVector End = LaneAt(Side, PathEndU);
		DrawDebugLine(World, Cruise - FVector(0, 0, 1500), Cruise + FVector(0, 0, 1500), FColor::Yellow, bPersistent, Duration, 0, 40.f);
		DrawDebugLine(World, End - FVector(0, 0, 1500), End + FVector(0, 0, 1500), FColor::Red, bPersistent, Duration, 0, 40.f);
	}

	// The path itself
	FVector PreviousPath = PathAt(0.f, 0.f);

	for (int32 Cell = ZeroCell + Stride; ; Cell += Stride)
	{
		const float U = FMath::Min(GridStartU + Cell * CellStep, LastU);
		const FVector Path = PathAt(U, 0.f);
		DrawDebugLine(World, PreviousPath, Path, FColor::Cyan, bPersistent, Duration, 0, 15.f);
		PreviousPath = Path;

		if (U >= LastU)
		{
			break;
		}
	}
#endif
}


// =============================================================================
// Console
// =============================================================================

#if !UE_BUILD_SHIPPING
namespace LaneConsole
{
	bool CheckServer(const UWorld* World, const TCHAR* Command)
	{
		if (!World || World->GetNetMode() == NM_Client)
		{
			UE_LOG(LogLane, Warning, TEXT("%s: run it on the server (listen server window or standalone)"), Command);
			return false;
		}
		return true;
	}

	UMyLaneSubsystem* GetLanes(UWorld* World, const TCHAR* Command)
	{
		UMyLaneSubsystem* Lanes = UMyLaneSubsystem::Get(World);

		if (!Lanes || !Lanes->HasLanes())
		{
			UE_LOG(LogLane, Warning, TEXT("%s: no team lanes in this world (match off, or no lane source)"), Command);
			return nullptr;
		}
		return Lanes;
	}

	/** The team's living ship: the game state's, else any living ship of that team. */
	AAirshipPawn* FindTeamShip(UWorld* World, uint8 TeamId)
	{
		if (const AMyGameState* GameState = World->GetGameState<AMyGameState>())
		{
			AAirshipPawn* Ship = GameState->GetTeamState(TeamId).Ship;

			if (IsValid(Ship) && !Ship->IsAirshipDead())
			{
				return Ship;
			}
		}

		for (TActorIterator<AAirshipPawn> It(World); It; ++It)
		{
			if (It->GetTeamId() == TeamId && !It->IsAirshipDead())
			{
				return *It;
			}
		}
		return nullptr;
	}

	FAutoConsoleCommandWithWorldAndArgs GStatusCommand(
		TEXT("Aura.Lane.Status"),
		TEXT("Aura.Lane.Status - per team ship: lane state, u, lateral / vertical error, target u and speed, clamp, bypass, recall; the team front, cruise end and path end u (m). Server."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (!CheckServer(World, TEXT("Aura.Lane.Status")))
			{
				return;
			}

			UMyLaneSubsystem* Lanes = GetLanes(World, TEXT("Aura.Lane.Status"));

			if (!Lanes)
			{
				return;
			}

			UE_LOG(LogLane, Log, TEXT("Aura.Lane.Status: LaneStartU %.1f m, PathEndU %.1f m, CruiseEndU %.1f m, lanes at +-%.1f m, sides team0 %+d team1 %+d"),
				Lanes->GetLaneStartU() / 100.f, Lanes->GetPathEndU() / 100.f, Lanes->GetCruiseEndU() / 100.f, Lanes->GetLaneOffset() / 100.f,
				Lanes->GetSideForTeam(0), Lanes->GetSideForTeam(1));

			int32 Count = 0;

			for (TActorIterator<AAirshipPawn> It(World); It; ++It)
			{
				const uint8 TeamId = It->GetTeamId();
				const UAirshipLaneComponent* Lane = It->GetLane();

				if (TeamId == MyMatch::NoTeam || !Lane)
				{
					continue;
				}

				float FrontU = 0.f;
				const bool bFront = Lanes->GetTeamFrontU(TeamId, FrontU);
				UE_LOG(LogLane, Log, TEXT("Aura.Lane.Status: %s team %d: %s, front %s"), *It->GetName(), TeamId, *Lane->DescribeStatus(),
					bFront ? *FString::Printf(TEXT("%.1f m"), FrontU / 100.f) : TEXT("none"));
				++Count;
			}

			if (Count == 0)
			{
				UE_LOG(LogLane, Log, TEXT("Aura.Lane.Status: no team ship"));
			}
		})
	);

	FAutoConsoleCommandWithWorldAndArgs GTeleportCommand(
		TEXT("Aura.Lane.Teleport"),
		TEXT("Aura.Lane.Teleport <Team> <U m> [dZ m] - puts that team's ship on its lane at U (dZ above or below it), velocity zero, cruising when nobody pilots it. Server."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (!CheckServer(World, TEXT("Aura.Lane.Teleport")) || !GetLanes(World, TEXT("Aura.Lane.Teleport")))
			{
				return;
			}

			if (Args.Num() < 2)
			{
				UE_LOG(LogLane, Warning, TEXT("Aura.Lane.Teleport <Team> <U m> [dZ m]"));
				return;
			}

			const uint8 TeamId = static_cast<uint8>(FMath::Clamp(FCString::Atoi(*Args[0]), 0, 255));
			AAirshipPawn* Ship = FindTeamShip(World, TeamId);
			UAirshipLaneComponent* Lane = Ship ? Ship->GetLane() : nullptr;

			if (!Lane)
			{
				UE_LOG(LogLane, Warning, TEXT("Aura.Lane.Teleport: team %d has no living ship"), TeamId);
				return;
			}

			const float U = FCString::Atof(*Args[1]) * 100.f;
			const float DeltaZ = Args.Num() >= 3 ? FCString::Atof(*Args[2]) * 100.f : 0.f;
			Lane->DebugTeleportToLane(U, DeltaZ);
		})
	);

	FAutoConsoleCommandWithWorldAndArgs GRebuildCommand(
		TEXT("Aura.Lane.Rebuild"),
		TEXT("Aura.Lane.Rebuild - re-samples both lanes from the path (after Aura.Match.Set of a Lanes setting). Server."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (!CheckServer(World, TEXT("Aura.Lane.Rebuild")))
			{
				return;
			}

			if (UMyLaneSubsystem* Lanes = UMyLaneSubsystem::Get(World))
			{
				Lanes->RebuildLanes();
			}
		})
	);

	FAutoConsoleCommandWithWorldAndArgs GCheckCommand(
		TEXT("Aura.Lane.Check"),
		TEXT("Aura.Lane.Check - the smallest gap between a hull footprint (29 x 22.6 m on the lane tangent) and the platform field along each lane, and its u. Server."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (!CheckServer(World, TEXT("Aura.Lane.Check")))
			{
				return;
			}

			UMyLaneSubsystem* Lanes = GetLanes(World, TEXT("Aura.Lane.Check"));

			if (!Lanes)
			{
				return;
			}

			for (int8 Side : { static_cast<int8>(1), static_cast<int8>(-1) })
			{
				float Gap = 0.f;
				float AtU = 0.f;

				if (Lanes->CheckHullClearanceSide(Side, Gap, AtU))
				{
					UE_LOG(LogLane, Log, TEXT("Aura.Lane.Check: side %+d: smallest hull-to-field gap %.2f m at u %.1f m (path end %.1f m)"),
						Side, Gap / 100.f, AtU / 100.f, Lanes->GetPathEndU() / 100.f);
				}
			}

			float Gap = 0.f;
			float AtU = 0.f;

			if (Lanes->CheckHullClearance(Gap, AtU))
			{
				UE_LOG(LogLane, Log, TEXT("Aura.Lane.Check: smallest %.2f m at u %.1f m"), Gap / 100.f, AtU / 100.f);
			}
		})
	);
}
#endif
