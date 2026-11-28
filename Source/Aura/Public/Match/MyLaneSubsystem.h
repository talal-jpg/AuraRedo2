// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "MyLaneSubsystem.generated.h"

class AActor;
class AMyHexPathSegment;
class AMyHexPathSpawner;
class USplineComponent;

/** Every lane state change and rebuild logs one line here (the PIE harnesses scan it). Defined in MyLaneSubsystem.cpp. */
DECLARE_LOG_CATEGORY_EXTERN(LogLane, Log, All);

/**
 * The two team lanes beside the platform field (Docs/Airship/round2/SPEC_B.md B2.1, B2.2). Server only: the path spline
 * exists only on the server (the spawner doesn't replicate), so clients see the lanes through each ship's replicated
 * lane hint (UAirshipLaneComponent). Only built while a match runs (AMyGameMode::IsMatchOn at world begin play): with the
 * match off nothing here exists and every ship flies as in PR A.
 *
 * Start-heading frame: origin O = the path's first point, forward F = the spawner's start yaw, right R = F turned +90 deg.
 * For a world point P, u = (P - O).F (progress) and v = (P - O).R (sideways, + = right). Side +1 = the lane right of
 * the start heading, -1 = left.
 *
 * The path is sampled every LaneSampleStep x S along its length. A lane keeps the distance H + LaneClearance from every
 * sample (the outer envelope of circles of that radius, so a bend never brings it closer than LaneClearance to the
 * field, which a sideways shift would), stored at a fixed u step from LaneStartU (LaneBackReach x S before the start,
 * where it runs straight back) to the path end, then smoothed outward only (moving average, then the max with the
 * unsmoothed envelope). Each new segment re-samples only what it can have changed.
 *
 * No path spawner: an actor tagged MatchLaneOrigin gives a straight virtual path (tests on L_AirshipTest). Neither: no
 * lanes, and team ships behave as PR A ships.
 */
UCLASS()
class AURA_API UMyLaneSubsystem : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:

	static UMyLaneSubsystem* Get(const UObject* WorldContext);

	virtual void OnWorldBeginPlay(UWorld& InWorld) override;
	virtual void Deinitialize() override;

	/** Only while Aura.Lane.Debug >= 1: draws the lanes every frame. */
	virtual void Tick(float DeltaTime) override;
	virtual bool IsTickable() const override;
	virtual TStatId GetStatId() const override;

	// -------------------------------------------------------------------------
	// Lanes (server; false / 0 without lanes)
	// -------------------------------------------------------------------------

	bool HasLanes() const { return bHasLanes; }

	/** TeamLaneSide of the team, swapped while the game state says so (odd versus rounds with bAlternateSides, B1.6). 0 = none. Any machine. */
	int8 GetSideForTeam(uint8 TeamId) const;

	/** u of a world point (cm along the start heading from the path start). */
	float ProjectU(const FVector& World) const;

	/** v of a world point minus the path's v at its u (cm, + = right of the start heading). B9.7. */
	float GetLateralFromPath(const FVector& World) const;

	/**
	 * Aura.Lane.Check (B2.1): the smallest gap (cm) between a hull footprint (a HullCheckLength x HullCheckWidth
	 * rectangle on the lane tangent, at every lane step) and the platform field (H around the path), both lanes, and its
	 * u. False without lanes.
	 */
	bool CheckHullClearance(float& OutMinGapCm, float& OutAtU) const;

	/** The same for one lane (Side +1 / -1). */
	bool CheckHullClearanceSide(int8 Side, float& OutMinGapCm, float& OutAtU) const;

	/** The lane point (hull origin height) and unit tangent at U, U clamped to [LaneStartU, PathEndU]. */
	bool GetLanePoint(int8 Side, float U, FVector& OutLocation, FVector& OutTangent) const;

	float GetLaneStartU() const { return GridStartU; }
	float GetPathEndU() const { return PathEndU; }

	/** PathEndU - LaneEndMargin x S, at least LaneStartU (B2.6): an unpiloted ship never cruises past it. */
	float GetCruiseEndU() const;

	/**
	 * The largest u of the team's living players on foot (not aboard a ship), from the game state's player array (B2.4).
	 * False when the team has nobody on foot. TeamId MyMatch::NoTeam = every player (the match front, B3.1).
	 */
	bool GetTeamFrontU(uint8 TeamId, float& OutU) const;

	/** The team's lane point at U, facing along the lane (a ship's actor transform). False without a lane for the team. */
	bool GetSpawnTransform(uint8 TeamId, float U, FTransform& Out) const;

	/** Server: after every (re)build. */
	FSimpleMulticastDelegate OnLanesChanged;

	/** Both lanes, the field limits and the cruise end, for Duration seconds (0 = this frame). Server, not in shipping. */
	void DrawDebug(float Duration) const;

	// -------------------------------------------------------------------------
	// For the lane component and the console (lanes owner)
	// -------------------------------------------------------------------------

	/** Re-samples everything (Aura.Lane.Rebuild; the lane settings are read again). */
	void RebuildLanes();

	/** H: the platform field's reach across the path (cm, world). */
	float GetPathHalfWidth() const { return HalfWidth; }

	/** R = H + LaneClearance: the lanes' distance from every path sample (cm). */
	float GetLaneOffset() const { return LaneOffset; }

	/** The path spawner's layout scale S (1 for the MatchLaneOrigin fallback). */
	float GetLayoutScale() const { return LayoutScale; }

	/** The path's height at U (cm, world; the start height outside the path). */
	float GetPathZ(float U) const;

	/** 2D distance (cm) from a world point to the path line; a huge value without lanes. */
	float GetDistanceToPath2D(const FVector& World) const;

	/** True when the 2D segment A-B passes within H + Margin of the path (a recall has to climb over the field, B2.11). */
	bool DoesSegmentCrossField(const FVector& A, const FVector& B, float Margin) const;

	/** World yaw (deg) of the start heading. */
	float GetStartYaw() const { return StartYawDeg; }

	/** Aura.Lane.Debug: 0 off, 1 lanes and targets, 2 plus look-ahead sweeps. */
	static int32 GetDebugLevel();

	/** Hull footprint for Aura.Lane.Check (cm): the ship's hull is about 29 m long and 22.6 m wide (lanes_map). */
	static constexpr float HullCheckLength = 2900.f;
	static constexpr float HullCheckWidth = 2260.f;

protected:

	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;

private:

	enum class ELaneSource : uint8
	{
		None,
		Spawner,
		Origin
	};

	UFUNCTION()
	void HandleSegmentSpawned(AMyHexPathSpawner* PathSpawner, AMyHexPathSegment* Segment);

	/** Spawner source: the frame on the first call, then the samples from the first one the new segment can change. */
	void BuildFromSpawner(bool bFull);

	/** MatchLaneOrigin source: a straight virtual path from the actor along its yaw. */
	void BuildFromOrigin(const AActor* InOriginActor);

	/** Reads the scale and the lane settings; true when one that shapes the grid changed (a full rebuild is needed). */
	bool RefreshGeometrySettings(float NewScale, float NewHalfWidth);

	/** Recomputes the grid from FirstChangedU on (the circles reach R, the smoothing its half window). */
	void RebuildGrid(float FirstChangedU, bool bFull);

	/** Samples sorted by u (the samples themselves when u grows along the path). */
	const TArray<FVector>& GetSortedSamples() const { return bMonotonic ? Samples : SortedSamples; }

	/** Index range of the sorted samples with u in [UMin, UMax]; false if none. */
	bool FindSampleWindow(float UMin, float UMax, int32& OutFirst, int32& OutLast) const;

	/** The path's v and z at U (linear between the samples sorted by u). */
	void SamplePath(float U, float& OutV, float& OutZ) const;

	/** u, v, z of a world point in the start-heading frame. */
	FVector ToFrame(const FVector& World) const;
	FVector FromFrame(float U, float V, float Z) const;

	/** Grid lookup at U: lane v, lane z, and their slopes along u. */
	void SampleLane(int8 Side, float U, float& OutV, float& OutZ, float& OutDvDu, float& OutDzDu) const;

	/** Min 2D distance from a frame point (u, v) to the path polyline, over samples within the u window. */
	float DistanceToPathUV(float U, float V, float Window) const;

	void LogNoLanesOnce(const TCHAR* Why);

	bool bActive = false;
	bool bHasLanes = false;
	bool bLoggedNoLanes = false;
	ELaneSource Source = ELaneSource::None;

	TWeakObjectPtr<AMyHexPathSpawner> Spawner;
	TWeakObjectPtr<const AActor> OriginActor;

	/** Start-heading frame. */
	bool bFrameReady = false;
	FVector Origin = FVector::ZeroVector;
	FVector2D Forward = FVector2D(1.0, 0.0);
	FVector2D Right = FVector2D(0.0, 1.0);
	float StartYawDeg = 0.f;

	/** Geometry from the source and the settings (cm). */
	float LayoutScale = 1.f;
	float HalfWidth = 0.f;
	float LaneOffset = 0.f;
	float SampleStep = 1000.f;
	float CellStep = 1000.f;
	float BackReach = 0.f;
	float SmoothHalfWindow = 0.f;
	float LaneHeight = 0.f;

	/** MaxYawDeviation >= MaxYawForEnvelope: straight lanes at +-R along the start heading (the path could double back). */
	bool bStraight = false;

	/** Path samples in path order: X = u, Y = v, Z = world z; SampleDistances = distance along the spline. */
	TArray<FVector> Samples;
	TArray<float> SampleDistances;
	TArray<FVector> SortedSamples;
	bool bMonotonic = true;

	/** Spline points when the samples were last taken (the incremental rebuild starts at the span before the old end). */
	int32 SampledSplinePoints = 0;

	float PathEndU = 0.f;

	/** Grid: cell i is at u = GridStartU + i x CellStep. Cell ZeroCell is u = 0; the cells before it run straight back. */
	float GridStartU = 0.f;
	int32 ZeroCell = 0;
	TArray<float> GridPathV;
	TArray<float> GridPathZ;
	TArray<float> GridRawRight;
	TArray<float> GridRawLeft;
	TArray<float> GridRight;
	TArray<float> GridLeft;
};
