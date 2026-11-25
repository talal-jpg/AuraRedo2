// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "Match/MyMatchTypes.h"
#include "AirshipLaneComponent.generated.h"

class AAirshipPawn;
class ACharacter;
class UAirshipFlightComponent;
class UMyLaneSubsystem;
struct FHitResult;

/**
 * A team ship's lane (Docs/Airship/round2/SPEC_B.md B2.3-B2.11): on AAirshipPawn ("Lane"), no tick of its own. The pawn's
 * Tick calls UpdateLane on the server right before the flight model, so the flight uses this frame's lane target.
 *
 * Server: the lane state machine (Cruising / Waiting / Assist / PilotedInLane / OutOfLane / Parked / Returning), the
 * lane target (pace with the team front, the cruise end, the look-ahead and the bypass round a blocker), the recall of
 * a ship left outside its lane, and the replicated hint for the HUD. Free ships (team 255), no match, no lanes or a dead
 * ship: NoLane, and nothing here touches the flight (PR A behaviour).
 *
 * Every machine: GetLaneState, GetLaneHint, IsAssistActive, GetRecallServerTime (replicated).
 */
UCLASS(ClassGroup = (Airship), meta = (BlueprintSpawnableComponent))
class AURA_API UAirshipLaneComponent : public UActorComponent
{
	GENERATED_BODY()

public:

	UAirshipLaneComponent();

	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	/** Server, AAirshipPawn::Tick before Flight->UpdateFlight: state, target (Flight->SetLaneTarget), hint. */
	void UpdateLane(float DeltaSeconds);

	/** Server, end of BoardPilot / UnboardPilot: the helm changes hands now (the per-frame check catches the rest). */
	void NotifyPilotChanged(bool bHasPilot);

	/** Server, from the pawn's OnHullHit: a bow contact while following the lane stops it for 2 s. */
	void NotifyHullContact(const AActor* Other, const FHitResult& Hit);

	/** Server, from AAirshipPawn::SetTeamId: the lane is chosen again on the next update. */
	void NotifyTeamChanged();

	UFUNCTION(BlueprintPure, Category = "Airship|Lane")
	EMyLaneState GetLaneState() const { return LaneState; }

	/** Every machine, at most every LaneHintInterval: where the ship is against its lane (decimetres), the clamp. */
	const FMyLaneHint& GetLaneHint() const { return LaneHint; }

	/** Every machine: the lane flies, the pilot aims and fires (B2.9). */
	bool IsAssistActive() const { return LaneState == EMyLaneState::Assist; }

	/** Every machine: server time the recall starts (B2.11), 0 = none. */
	double GetRecallServerTime() const { return RecallServerTime; }

	/** Server: this ship is being replaced by a recall (its destruction costs no life). */
	bool IsRecallReplacing() const { return bRecallReplacing; }

	/** Server, console (Aura.Lane.Teleport): on the lane at U (cm), DeltaZ above / below it, velocity zero, cruising. */
	void DebugTeleportToLane(float U, float DeltaZ = 0.f);

	/** Server, console (Aura.Match.Recall): the recall starts now. False when the ship can't recall (piloted, no lane). */
	bool StartRecall();

	// -------------------------------------------------------------------------
	// Exact values for telemetry and the console (server; clients have the hint)
	// -------------------------------------------------------------------------

	/** The ship's progress u (cm) at the hull origin. */
	float GetShipU() const { return ShipU; }

	/** Hull origin minus the lane point at the ship's u (cm, + = right of the lane / up). */
	float GetLateralError() const { return LateralError; }
	float GetVerticalError() const { return VerticalError; }

	/** The lane target's u (cm) and speed (cm/s); the recall target's speed while Returning. */
	float GetTargetU() const { return TargetU; }
	float GetTargetSpeed() const { return LaneState == EMyLaneState::Returning ? RecallSpeed : TargetSpeed; }

	EMyLaneClamp GetClamp() const { return Clamp; }

	/** +1 / -1: the lane this ship follows; 0 = none. */
	int8 GetLaneSide() const { return Side; }

	float GetBypassOffset() const { return BypassOffset; }

	/**
	 * Server: mean wall time (ms) of one UpdateLane over the last game second (before the first full second, the mean so
	 * far). For Aura.Match.Dump (M6.2): the LaneUpdate stat and trace scope can't be read from Python.
	 */
	float GetUpdateTimeMs() const;

	/** One line for Aura.Lane.Status (server). */
	FString DescribeStatus() const;

	static const TCHAR* GetLaneStateName(EMyLaneState State);
	static const TCHAR* GetClampName(EMyLaneClamp InClamp);

protected:

	UPROPERTY(Replicated)
	EMyLaneState LaneState = EMyLaneState::NoLane;

	UPROPERTY(Replicated)
	FMyLaneHint LaneHint;

	UPROPERTY(Replicated)
	double RecallServerTime = 0.0;

private:

	AAirshipPawn* GetShip() const;

	/** This frame's measurements against the own lane (ShipU, errors, speeds, zone hysteresis). False without a lane. */
	bool Measure(const UMyLaneSubsystem& Lanes);

	void SetState(EMyLaneState NewState, const TCHAR* Reason);

	/** Not a team ship on a lane (any more): NoLane, the PR A drift limit back for a free ship. */
	void LeaveLane(const TCHAR* Reason, bool bRestoreDrift);

	/** Following again from the ship's own position and speed along the lane. */
	void EnterFollow(EMyLaneState NewState, const TCHAR* Reason);

	/** A pilot took the helm: Assist (from a following ship, with Rules.bLaneAssist), PilotedInLane or OutOfLane. */
	void EnterPiloted(bool bFromFollow, const TCHAR* Reason);

	/** The helm is free: parked in the lane cruises, anything else parks (PR A drift / hold). */
	void HandlePilotExit(const TCHAR* Reason);

	void EnterParked(const TCHAR* Reason);
	void EnterReturning(const TCHAR* Reason);

	/** Recall fallback (B2.11): a new ship at the team front through the game mode, the crew put on its deck. */
	void ReplaceShip(const TCHAR* Reason);

	/** Puts a character on a deck spot of the new ship (gunners dismounted, riders). */
	static void PutOnDeck(ACharacter* Character, const FTransform& Spot);

	/** The pace limit (B2.4, B2.6): CruiseEndU, or the team front + LaneMaxLead when nearer. */
	float ComputeCap(const UMyLaneSubsystem& Lanes, bool& bOutTeamCap, bool& bOutFront, float& OutFrontU) const;

	/** Cruising / Waiting / Assist: pace, target point, look-ahead, bypass; sets the flight's lane target. */
	void UpdateFollow(const UMyLaneSubsystem& Lanes, UAirshipFlightComponent& Flight, float Dt, double Now, EMyMatchPhase Phase);

	/** Returning: the recall target (climbing over the field when it must cross it), fallbacks. */
	void UpdateReturning(const UMyLaneSubsystem& Lanes, UAirshipFlightComponent& Flight, float Dt, double Now);

	/** Parked: lane capture (parked in the zone for LaneParkSettleTime) and the recall timer. */
	void UpdateParked(double Now, EMyMatchPhase Phase, bool bDebugInput);

	/** The look-ahead's length (cm) at Speed: the time ahead plus the stop at LaneAccelMax, at least LaneLookAheadMin. */
	float GetLookAheadLength(float Speed) const;

	/** Look-ahead every LaneSweepInterval along SweepYaw for Length; updates bBlocked. True when a sweep ran this frame. */
	bool RunLookAhead(const UMyLaneSubsystem& Lanes, UAirshipFlightComponent& Flight, double Now, float SweepYaw, float Length);

	void WriteHint(double Now);

	void DrawLaneDebug(const FVector& TargetPoint, float Duration) const;

	/** Hull footprint half sizes (cm), from the hull's collision bounds (cached). */
	void CacheHullSize();

	/** Adds one UpdateLane's wall time (s) to the per-second mean GetUpdateTimeMs reports. */
	void AddUpdateTime(double WallSeconds);

	TWeakObjectPtr<UMyLaneSubsystem> CachedLanes;

	/** The lane followed and the team it was chosen for. */
	int8 Side = 0;
	uint8 LaneTeam = MyMatch::NoTeam;

	/** SetDriftMaxDistanceOverride(LaneOutDriftMaxDistance) was made (team ships only), with this value. */
	bool bDriftOverrideSet = false;
	float AppliedDriftOverride = 0.f;

	// ---- This frame (Measure) ----
	FVector ShipOrigin = FVector::ZeroVector;
	FVector2D COMOffset = FVector2D::ZeroVector;
	FVector2D LaneTangent2D = FVector2D(1.0, 0.0);
	float LaneYawAtShip = 0.f;
	float ShipU = 0.f;
	float LateralError = 0.f;
	float VerticalError = 0.f;
	float AlongSpeed = 0.f;
	float Speed2D = 0.f;
	bool bInZone = false;

	// ---- Lane target ----
	float TargetU = 0.f;
	float TargetSpeed = 0.f;
	float LastTargetSpeed = 0.f;
	EMyLaneClamp Clamp = EMyLaneClamp::None;

	// ---- Timers (server world time, s; < 0 = not running) ----
	double StateEnterTime = 0.0;
	double ParkedSince = -1.0;
	double ParkInLaneSince = -1.0;
	double LastDriveInputTime = -1.0;
	double ContactHoldUntil = -1.0;
	double NextHintTime = 0.0;

	// ---- Look-ahead and bypass (B2.7) ----
	double NextSweepTime = 0.0;
	bool bBlocked = false;
	int32 ClearSweeps = 0;
	double BlockedSince = -1.0;
	float BlockerU = 0.f;
	FString BlockerName;
	bool bBypassActive = false;
	float BypassOffset = 0.f;
	double NextBypassTryTime = 0.0;

	// ---- Recall (B2.11) ----
	double RecallStartTime = -1.0;
	double RecallBlockedSince = -1.0;
	FVector2D RecallTargetXY = FVector2D::ZeroVector;
	FVector2D RecallDir = FVector2D(1.0, 0.0);
	float RecallSpeed = 0.f;
	float LastRecallSpeed = 0.f;
	bool bRecallCrossing = false;
	bool bRecallReplacing = false;

	// ---- Hull size (cm) ----
	float HullHalfLength = 1450.f;
	float HullHalfWidth = 1130.f;
	bool bHullSizeCached = false;

	// ---- Debug ----
	FVector DebugTargetPoint = FVector::ZeroVector;
	float LastSweepYaw = 0.f;
	float LastSweepLength = 0.f;
	bool bLastSweepHit = false;

	// ---- UpdateLane cost (GetUpdateTimeMs) ----
	double UpdateTimeSum = 0.0;
	int32 UpdateTimeCount = 0;
	double UpdateWindowStart = -1.0;
	float UpdateTimeMeanMs = -1.f;
};
