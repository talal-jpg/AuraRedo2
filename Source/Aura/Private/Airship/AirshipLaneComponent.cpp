// Fill out your copyright notice in the Description page of Project Settings.


#include "Airship/AirshipLaneComponent.h"

#include "Airship/AirshipCannonball.h"
#include "Airship/AirshipFlightComponent.h"
#include "Airship/AirshipPawn.h"
#include "Airship/AirshipSettings.h"
#include "Airship/AirshipTypes.h"
#include "Components/PrimitiveComponent.h"
#include "Components/StaticMeshComponent.h"
#include "DrawDebugHelpers.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Match/MyLaneSubsystem.h"
#include "Match/MyMatchSettings.h"
#include "Match/MyTeamLibrary.h"
#include "MyGameMode.h"
#include "MyGameState.h"
#include "Misc/ScopeExit.h"
#include "Net/UnrealNetwork.h"
#include "ProfilingDebugging/CpuProfilerTrace.h"
#include "TimerManager.h"

DECLARE_CYCLE_STAT(TEXT("LaneUpdate"), STAT_LaneUpdate, STATGROUP_Game);

// Named, not anonymous: the unity build compiles this file together with others
namespace AirshipLanePrivate
{
	bool IsFollowing(EMyLaneState State)
	{
		return State == EMyLaneState::Cruising || State == EMyLaneState::Waiting;
	}

	bool IsPiloted(EMyLaneState State)
	{
		return State == EMyLaneState::Assist || State == EMyLaneState::PilotedInLane || State == EMyLaneState::OutOfLane;
	}

	float YawOf(const FVector2D& Direction)
	{
		return static_cast<float>(FMath::RadiansToDegrees(FMath::Atan2(Direction.Y, Direction.X)));
	}

	int16 ToDecimetres16(float Cm)
	{
		return static_cast<int16>(FMath::Clamp(FMath::RoundToInt32(Cm / 10.f), -32767, 32767));
	}

	/** A target slower than this (cm/s), with nothing asking for more, is stopped: Waiting. */
	constexpr float StoppedSpeed = 5.f;

	/** ... and Waiting cruises again above this (hysteresis, so a creeping cap doesn't flip the state every frame). */
	constexpr float MovingSpeed = 30.f;

	/** A bow contact while following the lane stops the target this long (s), then the look-ahead decides. */
	constexpr double ContactHoldSeconds = 2.0;

	/** A bypass ends once the blocker is this far (cm) behind the stern (about one hull length). */
	constexpr float BypassClearBehindStern = 3000.f;

	/** Moving across to (or back from) the bypass line: the sweep goes diagonally while more than this (cm) is left. */
	constexpr float AcrossSweepTolerance = 500.f;

	/** The zone is left when u is this far (cm) outside [LaneStartU, PathEndU]. */
	constexpr float ZoneUMargin = 2000.f;

	/** Recall: heading toward the lane point until this close (cm), then the lane's own heading. */
	constexpr float RecallTangentDistance = 5000.f;

	/** Recall over the field: the crossing starts within this (cm) of the cross height ... */
	constexpr float RecallClimbTolerance = 500.f;

	/** ... and ends once the hull's inner side is this far (cm) outside the field on the own lane's side. */
	constexpr float RecallFieldMargin = 500.f;
}


// =============================================================================
// Component
// =============================================================================

UAirshipLaneComponent::UAirshipLaneComponent()
{
	// The pawn's Tick drives it (server, right before the flight model)
	PrimaryComponentTick.bCanEverTick = false;
	SetIsReplicatedByDefault(true);
}

void UAirshipLaneComponent::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);

	DOREPLIFETIME(UAirshipLaneComponent, LaneState);
	DOREPLIFETIME(UAirshipLaneComponent, LaneHint);
	DOREPLIFETIME(UAirshipLaneComponent, RecallServerTime);
}

AAirshipPawn* UAirshipLaneComponent::GetShip() const
{
	return Cast<AAirshipPawn>(GetOwner());
}

const TCHAR* UAirshipLaneComponent::GetLaneStateName(EMyLaneState State)
{
	switch (State)
	{
	case EMyLaneState::NoLane:			return TEXT("NoLane");
	case EMyLaneState::Cruising:		return TEXT("Cruising");
	case EMyLaneState::Waiting:			return TEXT("Waiting");
	case EMyLaneState::Assist:			return TEXT("Assist");
	case EMyLaneState::PilotedInLane:	return TEXT("PilotedInLane");
	case EMyLaneState::OutOfLane:		return TEXT("OutOfLane");
	case EMyLaneState::Parked:			return TEXT("Parked");
	case EMyLaneState::Returning:		return TEXT("Returning");
	default:							return TEXT("?");
	}
}

const TCHAR* UAirshipLaneComponent::GetClampName(EMyLaneClamp InClamp)
{
	switch (InClamp)
	{
	case EMyLaneClamp::None:		return TEXT("None");
	case EMyLaneClamp::TeamPace:	return TEXT("TeamPace");
	case EMyLaneClamp::PathEnd:		return TEXT("PathEnd");
	case EMyLaneClamp::Blocked:		return TEXT("Blocked");
	case EMyLaneClamp::NotStarted:	return TEXT("NotStarted");
	case EMyLaneClamp::Ended:		return TEXT("Ended");
	case EMyLaneClamp::Bypass:		return TEXT("Bypass");
	case EMyLaneClamp::Reel:		return TEXT("Reel");
	default:						return TEXT("?");
	}
}

FString UAirshipLaneComponent::DescribeStatus() const
{
	const UWorld* World = GetWorld();
	const double Now = World ? World->GetTimeSeconds() : 0.0;
	const AAirshipPawn* Ship = GetShip();
	const UAirshipFlightComponent* Flight = Ship ? Ship->GetFlight() : nullptr;
	const UEnum* ModeEnum = StaticEnum<EAirshipUnpilotedMode>();
	const FString Mode = Flight && ModeEnum ? ModeEnum->GetNameStringByValue(static_cast<int64>(Flight->GetUnpilotedMode())) : FString(TEXT("?"));

	FString Extra;

	if (bBlocked)
	{
		Extra += FString::Printf(TEXT(", blocked by %s for %.1f s"), *BlockerName, BlockedSince >= 0.0 ? Now - BlockedSince : 0.0);
	}
	if (bBypassActive)
	{
		Extra += FString::Printf(TEXT(", bypass %.0f m out"), BypassOffset / 100.f);
	}
	if (LaneState == EMyLaneState::Parked && ParkedSince >= 0.0)
	{
		Extra += FString::Printf(TEXT(", parked %.1f s"), Now - ParkedSince);
	}
	if (LaneState == EMyLaneState::Returning)
	{
		Extra += FString::Printf(TEXT(", returning %.1f s%s"), RecallStartTime >= 0.0 ? Now - RecallStartTime : 0.0, bRecallCrossing ? TEXT(" (crossing the field)") : TEXT(""));
	}

	return FString::Printf(TEXT("%s side %+d%s, u %.1f m, lateral %.1f m, vertical %.1f m, %.1f m/s along, target u %.1f m at %.1f m/s, clamp %s, unpiloted %s%s"),
		GetLaneStateName(LaneState), Side, bInZone ? TEXT(" in zone") : TEXT(""), ShipU / 100.f, LateralError / 100.f, VerticalError / 100.f,
		AlongSpeed / 100.f, TargetU / 100.f, GetTargetSpeed() / 100.f, GetClampName(Clamp), *Mode, *Extra);
}

float UAirshipLaneComponent::GetUpdateTimeMs() const
{
	if (UpdateTimeMeanMs >= 0.f)
	{
		return UpdateTimeMeanMs;
	}

	return UpdateTimeCount > 0 ? static_cast<float>(UpdateTimeSum * 1000.0 / UpdateTimeCount) : 0.f;
}

void UAirshipLaneComponent::AddUpdateTime(double WallSeconds)
{
	// Windows of one game second (the harness runs at a fixed frame rate, so game time is what its budgets count)
	const UWorld* World = GetWorld();
	const double Now = World ? World->GetTimeSeconds() : 0.0;

	UpdateTimeSum += WallSeconds;
	++UpdateTimeCount;

	if (UpdateWindowStart < 0.0 || Now < UpdateWindowStart)
	{
		UpdateWindowStart = Now;
	}
	else if (Now - UpdateWindowStart >= 1.0)
	{
		UpdateTimeMeanMs = static_cast<float>(UpdateTimeSum * 1000.0 / UpdateTimeCount);
		UpdateTimeSum = 0.0;
		UpdateTimeCount = 0;
		UpdateWindowStart = Now;
	}
}


// =============================================================================
// Measurements and states
// =============================================================================

void UAirshipLaneComponent::CacheHullSize()
{
	const AAirshipPawn* Ship = GetShip();
	const UPrimitiveComponent* Hull = Ship ? Ship->GetHull() : nullptr;

	if (bHullSizeCached || !Hull)
	{
		return;
	}

	const FBox Local = Hull->CalcBounds(FTransform::Identity).GetBox();

	if (Local.IsValid)
	{
		const FVector Scale = Hull->GetComponentScale().GetAbs();
		HullHalfLength = static_cast<float>(0.5 * (Local.Max.X - Local.Min.X) * Scale.X);
		HullHalfWidth = static_cast<float>(0.5 * (Local.Max.Y - Local.Min.Y) * Scale.Y);
	}

	bHullSizeCached = true;
}

bool UAirshipLaneComponent::Measure(const UMyLaneSubsystem& Lanes)
{
	const AAirshipPawn* Ship = GetShip();
	UPrimitiveComponent* Hull = Ship ? Ship->GetHull() : nullptr;

	if (!Hull || Side == 0)
	{
		return false;
	}

	CacheHullSize();

	// The zone is measured at the hull origin (the actor, which is also what the altitude hold holds); the flight's
	// position law moves the centre of mass, so the lane target is offset by the COM's place in the hull
	ShipOrigin = Ship->GetActorLocation();
	const FVector COM = Hull->GetCenterOfMass();
	COMOffset = FVector2D(COM.X - ShipOrigin.X, COM.Y - ShipOrigin.Y);
	const FVector Velocity = Hull->IsSimulatingPhysics() ? Hull->GetPhysicsLinearVelocity() : Ship->GetVelocity();

	ShipU = Lanes.ProjectU(ShipOrigin);

	FVector LanePoint;
	FVector Tangent;

	if (!Lanes.GetLanePoint(Side, ShipU, LanePoint, Tangent))
	{
		return false;
	}

	LaneTangent2D = FVector2D(Tangent.X, Tangent.Y).GetSafeNormal();

	if (LaneTangent2D.IsNearlyZero())
	{
		LaneTangent2D = FVector2D(1.0, 0.0);
	}

	LaneYawAtShip = AirshipLanePrivate::YawOf(LaneTangent2D);

	const FVector2D Normal(-LaneTangent2D.Y, LaneTangent2D.X);
	LateralError = static_cast<float>(FVector2D::DotProduct(FVector2D(ShipOrigin.X - LanePoint.X, ShipOrigin.Y - LanePoint.Y), Normal));
	VerticalError = static_cast<float>(ShipOrigin.Z - LanePoint.Z);
	AlongSpeed = static_cast<float>(FVector2D::DotProduct(FVector2D(Velocity.X, Velocity.Y), LaneTangent2D));
	Speed2D = static_cast<float>(Velocity.Size2D());

	// The own team's lane zone, with hysteresis (enter close, leave far)
	const UMyMatchSettings* M = UMyMatchSettings::Get();
	const float StartU = Lanes.GetLaneStartU();
	const float EndU = Lanes.GetPathEndU();

	if (bInZone)
	{
		bInZone = FMath::Abs(LateralError) <= M->LaneZoneExitLateral
			&& FMath::Abs(VerticalError) <= M->LaneZoneExitVertical
			&& ShipU >= StartU - AirshipLanePrivate::ZoneUMargin
			&& ShipU <= EndU + AirshipLanePrivate::ZoneUMargin;
	}
	else
	{
		bInZone = FMath::Abs(LateralError) <= M->LaneZoneEnterLateral
			&& FMath::Abs(VerticalError) <= M->LaneZoneEnterVertical
			&& ShipU >= StartU
			&& ShipU <= EndU;
	}

	return true;
}

void UAirshipLaneComponent::SetState(EMyLaneState NewState, const TCHAR* Reason)
{
	if (NewState == LaneState)
	{
		return;
	}

	const UWorld* World = GetWorld();
	const EMyLaneState OldState = LaneState;
	LaneState = NewState;
	StateEnterTime = World ? World->GetTimeSeconds() : 0.0;

	if (OldState == EMyLaneState::Parked)
	{
		ParkedSince = -1.0;
		ParkInLaneSince = -1.0;
	}

	if (NewState != EMyLaneState::Parked)
	{
		RecallServerTime = 0.0;
	}

	AAirshipPawn* Ship = GetShip();

	UE_LOG(LogLane, Log, TEXT("%s team %d: lane %s -> %s (%s; u %.1f m, lateral %.1f m, vertical %.1f m, %.1f m/s)"),
		*GetNameSafe(Ship), LaneTeam, GetLaneStateName(OldState), GetLaneStateName(NewState), Reason, ShipU / 100.f,
		LateralError / 100.f, VerticalError / 100.f, Speed2D / 100.f);

	// A parked ship may be asleep (no per-frame replication): the HUDs should see the state change now
	if (Ship)
	{
		Ship->ForceNetUpdate();
	}
}

void UAirshipLaneComponent::LeaveLane(const TCHAR* Reason, bool bRestoreDrift)
{
	SetState(EMyLaneState::NoLane, Reason);

	Clamp = EMyLaneClamp::None;
	bBlocked = false;
	ClearSweeps = 0;
	BlockedSince = -1.0;
	bBypassActive = false;
	BypassOffset = 0.f;
	RecallServerTime = 0.0;

	if (LaneHint.LateralDm != 0 || LaneHint.VerticalDm != 0 || LaneHint.ProgressDm != 0 || LaneHint.LaneYawDeg10 != 0 || LaneHint.Clamp != 0)
	{
		LaneHint = FMyLaneHint();
	}

	// A free ship (again): PR A's drift limit
	if (bRestoreDrift && bDriftOverrideSet)
	{
		const AAirshipPawn* Ship = GetShip();

		if (UAirshipFlightComponent* Flight = Ship ? Ship->GetFlight() : nullptr)
		{
			Flight->SetDriftMaxDistanceOverride(0.f);
		}

		bDriftOverrideSet = false;
		AppliedDriftOverride = 0.f;
	}

	if (bRestoreDrift)
	{
		Side = 0;
		LaneTeam = MyMatch::NoTeam;
	}
}

float UAirshipLaneComponent::ComputeCap(const UMyLaneSubsystem& Lanes, bool& bOutTeamCap, bool& bOutFront, float& OutFrontU) const
{
	const UMyMatchSettings* M = UMyMatchSettings::Get();
	float Cap = Lanes.GetCruiseEndU();
	bOutTeamCap = false;
	OutFrontU = 0.f;
	bOutFront = Lanes.GetTeamFrontU(LaneTeam, OutFrontU);

	// Never more than LaneMaxLead ahead of the team: the ship is only useful within hook range of its runners
	if (bOutFront && M->LaneMaxLead > 0.f && OutFrontU + M->LaneMaxLead < Cap)
	{
		Cap = OutFrontU + M->LaneMaxLead;
		bOutTeamCap = true;
	}

	return FMath::Max(Cap, Lanes.GetLaneStartU());
}

void UAirshipLaneComponent::EnterFollow(EMyLaneState NewState, const TCHAR* Reason)
{
	const UWorld* World = GetWorld();
	const double Now = World ? World->GetTimeSeconds() : 0.0;
	const UMyLaneSubsystem* Lanes = CachedLanes.Get();

	// From where the ship is, at its speed along the lane: no jerk when a pilot exits at lane speed. A ship ahead of its
	// cap waits where it is (the cap never pulls the target back) instead of flying backwards to its team.
	if (Lanes)
	{
		bool bTeamCap = false;
		bool bFront = false;
		float FrontU = 0.f;
		const float Cap = ComputeCap(*Lanes, bTeamCap, bFront, FrontU);
		TargetU = FMath::Clamp(ShipU, Lanes->GetLaneStartU(), FMath::Max(Cap, ShipU));
	}
	else
	{
		TargetU = ShipU;
	}

	TargetSpeed = FMath::Max(AlongSpeed, 0.f);
	LastTargetSpeed = TargetSpeed;

	bBlocked = false;
	ClearSweeps = 0;
	BlockedSince = -1.0;
	bBypassActive = false;
	BypassOffset = 0.f;
	NextBypassTryTime = 0.0;
	NextSweepTime = Now;
	ContactHoldUntil = -1.0;

	SetState(NewState, Reason);
}

void UAirshipLaneComponent::EnterPiloted(bool bFromFollow, const TCHAR* Reason)
{
	const FMyMatchRules& Rules = UMyTeamLibrary::GetRules(this);

	if (!bInZone)
	{
		SetState(EMyLaneState::OutOfLane, Reason);
	}
	else if (!bFromFollow || !Rules.bLaneAssist)
	{
		SetState(EMyLaneState::PilotedInLane, Reason);
	}
	else if (LaneState == EMyLaneState::Returning)
	{
		// The recall's target isn't a lane target: take the lane up from the ship
		EnterFollow(EMyLaneState::Assist, Reason);
	}
	else
	{
		// The pilot inherits the cruise: same target, same speed
		SetState(EMyLaneState::Assist, Reason);
	}
}

void UAirshipLaneComponent::HandlePilotExit(const TCHAR* Reason)
{
	// "Parked in lane": in the zone and no faster than LaneParkSpeed (a pilot riding along at lane speed counts)
	if (bInZone && Speed2D <= UMyMatchSettings::Get()->LaneParkSpeed)
	{
		EnterFollow(EMyLaneState::Cruising, Reason);
	}
	else
	{
		// PR A: drift after a moving exit, else hold (NotifyPilotLeft was called by UnboardPilot)
		EnterParked(Reason);
	}
}

void UAirshipLaneComponent::EnterParked(const TCHAR* Reason)
{
	const UWorld* World = GetWorld();

	SetState(EMyLaneState::Parked, Reason);
	ParkedSince = World ? World->GetTimeSeconds() : 0.0;
	ParkInLaneSince = -1.0;
	RecallServerTime = 0.0;
	Clamp = EMyLaneClamp::None;
	bBlocked = false;
	ClearSweeps = 0;
	BlockedSince = -1.0;
	bBypassActive = false;
	BypassOffset = 0.f;
}

void UAirshipLaneComponent::EnterReturning(const TCHAR* Reason)
{
	UWorld* World = GetWorld();
	const UMyLaneSubsystem* Lanes = CachedLanes.Get();

	if (!World || !Lanes)
	{
		return;
	}

	const UMyMatchSettings* M = UMyMatchSettings::Get();
	const double Now = World->GetTimeSeconds();

	bool bTeamCap = false;
	bool bFront = false;
	float FrontU = 0.f;
	const float Cap = ComputeCap(*Lanes, bTeamCap, bFront, FrontU);

	FVector Goal;
	FVector GoalTangent;
	Lanes->GetLanePoint(Side, FMath::Clamp(ShipU, Lanes->GetLaneStartU(), Cap), Goal, GoalTangent);

	RecallStartTime = Now;
	RecallBlockedSince = -1.0;
	RecallTargetXY = FVector2D(ShipOrigin.X, ShipOrigin.Y);
	RecallSpeed = 0.f;
	LastRecallSpeed = 0.f;

	const FVector2D ToGoal(Goal.X - ShipOrigin.X, Goal.Y - ShipOrigin.Y);
	RecallDir = ToGoal.IsNearlyZero() ? LaneTangent2D : ToGoal.GetSafeNormal();

	// A ship left on the other side of the field (or beside it) climbs over it first: nothing in the field reaches
	// ShipRecallCrossHeight above the path
	bRecallCrossing = Lanes->DoesSegmentCrossField(ShipOrigin, Goal, M->LaneClearance);

	bBlocked = false;
	ClearSweeps = 0;
	BlockedSince = -1.0;
	bBypassActive = false;
	BypassOffset = 0.f;
	NextSweepTime = Now;
	ContactHoldUntil = -1.0;

	SetState(EMyLaneState::Returning, Reason);

	UE_LOG(LogLane, Log, TEXT("%s team %d: recall to its lane, %.0f m away%s"), *GetNameSafe(GetOwner()), LaneTeam,
		FVector::Dist(ShipOrigin, Goal) / 100.f, bRecallCrossing ? TEXT(", over the field") : TEXT(""));

	if (AMyGameState* GameState = World->GetGameState<AMyGameState>())
	{
		GameState->MulticastMatchEvent(EMyMatchEvent::ShipReturning, LaneTeam, 0);
	}
}


// =============================================================================
// Update (server, every frame from AAirshipPawn::Tick)
// =============================================================================

void UAirshipLaneComponent::UpdateLane(float DeltaSeconds)
{
	using namespace AirshipLanePrivate;

	TRACE_CPUPROFILER_EVENT_SCOPE(LaneUpdate);
	SCOPE_CYCLE_COUNTER(STAT_LaneUpdate);

	// Every return below counts (GetUpdateTimeMs, Aura.Match.Dump lane_update_ms)
	const double WallStart = FPlatformTime::Seconds();
	ON_SCOPE_EXIT
	{
		AddUpdateTime(FPlatformTime::Seconds() - WallStart);
	};

	AAirshipPawn* Ship = GetShip();
	UWorld* World = GetWorld();
	UAirshipFlightComponent* Flight = Ship ? Ship->GetFlight() : nullptr;

	if (!Ship || !World || !Flight || !Ship->HasAuthority())
	{
		return;
	}

	// Being replaced by a recall: it goes next frame
	if (bRecallReplacing)
	{
		return;
	}

	const UMyMatchSettings* M = UMyMatchSettings::Get();
	const float Dt = FMath::Max(DeltaSeconds, 1.e-4f);
	const double Now = World->GetTimeSeconds();
	const AMyGameState* GameState = World->GetGameState<AMyGameState>();
	const EMyMatchPhase MatchPhase = GameState ? GameState->GetMatchPhase() : EMyMatchPhase::None;

	// The lane's phase: a practice -> versus countdown is one the practice team keeps playing through (B1.3), so its
	// ship keeps cruising and a recall keeps going instead of stopping for it (Clamp NotStarted, Parked)
	const EMyMatchPhase Phase = (MatchPhase == EMyMatchPhase::Countdown && GameState->IsPlayGoingOn()) ? EMyMatchPhase::InProgress : MatchPhase;
	const uint8 Team = Ship->GetTeamId();

	// A free ship, or no match: PR A, exactly
	if (Team >= MyMatch::NumTeams || Phase == EMyMatchPhase::None)
	{
		LeaveLane(TEXT("free ship or no match"), /*bRestoreDrift=*/true);
		return;
	}

	UMyLaneSubsystem* Lanes = CachedLanes.Get();

	if (!Lanes)
	{
		Lanes = UMyLaneSubsystem::Get(this);
		CachedLanes = Lanes;
	}

	const int8 NewSide = Lanes && Lanes->HasLanes() ? Lanes->GetSideForTeam(Team) : 0;

	if (NewSide == 0)
	{
		LeaveLane(TEXT("no lane"), /*bRestoreDrift=*/false);
		return;
	}

	if (Ship->IsAirshipDead() || !Flight->IsFlightEnabled())
	{
		LeaveLane(TEXT("ship dead"), /*bRestoreDrift=*/false);
		return;
	}

	// Team ships left outside their lane drift a limited way (B2.8); PR A's own limit is 0 = never
	if (!bDriftOverrideSet || !FMath::IsNearlyEqual(AppliedDriftOverride, M->LaneOutDriftMaxDistance))
	{
		Flight->SetDriftMaxDistanceOverride(M->LaneOutDriftMaxDistance);
		AppliedDriftOverride = M->LaneOutDriftMaxDistance;
		bDriftOverrideSet = true;
	}

	// First update as a team ship, a team change, or the sides changed: the state is chosen again below
	if (NewSide != Side || Team != LaneTeam)
	{
		SetState(EMyLaneState::NoLane, TEXT("lane chosen"));
		Side = NewSide;
		LaneTeam = Team;
		bInZone = false;
	}

	if (!Measure(*Lanes))
	{
		return;
	}

	// "Pilot" = PR A's rule: a pilot at the helm, or a controller on the ship (a pilot whose character is gone keeps
	// flying). Gunners never count. Debug controls on the server's copy (the harness) fly the ship like a pilot.
	const bool bPiloted = Ship->HasPilot() || Ship->GetController() != nullptr;
	const bool bDebugInput = Flight->HasDebugInput();
	const bool bDriveInput = Flight->HasPilotDriveInput() || (bPiloted && bDebugInput);

	if (bDriveInput)
	{
		LastDriveInputTime = Now;
	}

	const FMyMatchRules& Rules = UMyTeamLibrary::GetRules(this);

	// ---- Transitions (B2.3) ----
	switch (LaneState)
	{
	case EMyLaneState::NoLane:
		if (bPiloted)
		{
			EnterPiloted(/*bFromFollow=*/false, TEXT("team ship, piloted"));
		}
		else if (bInZone && !bDebugInput)
		{
			EnterFollow(EMyLaneState::Cruising, TEXT("team ship on its lane"));
		}
		else
		{
			EnterParked(TEXT("team ship outside its lane"));
		}
		break;

	case EMyLaneState::Cruising:
	case EMyLaneState::Waiting:
		if (bPiloted)
		{
			EnterPiloted(/*bFromFollow=*/true, TEXT("pilot boarded"));
		}
		else if (bDebugInput)
		{
			EnterParked(TEXT("debug input"));
		}
		break;

	case EMyLaneState::Returning:
		if (bPiloted)
		{
			EnterPiloted(/*bFromFollow=*/true, TEXT("pilot boarded"));
		}
		else if (bDebugInput)
		{
			EnterParked(TEXT("debug input"));
		}
		else if (Phase != EMyMatchPhase::InProgress || !M->bShipRecall)
		{
			EnterParked(TEXT("recall off or match not in progress"));
		}
		else if (bInZone)
		{
			EnterFollow(EMyLaneState::Cruising, TEXT("back in its lane"));
		}
		break;

	case EMyLaneState::Assist:
		if (!bPiloted)
		{
			HandlePilotExit(TEXT("pilot left"));
		}
		else if (!bInZone)
		{
			SetState(EMyLaneState::OutOfLane, TEXT("left the lane zone"));
		}
		else if (!Rules.bLaneAssist)
		{
			SetState(EMyLaneState::PilotedInLane, TEXT("lane assist off"));
		}
		else if (bDriveInput)
		{
			SetState(EMyLaneState::PilotedInLane, TEXT("drive input"));
		}
		break;

	case EMyLaneState::PilotedInLane:
		if (!bPiloted)
		{
			HandlePilotExit(TEXT("pilot left"));
		}
		else if (!bInZone)
		{
			SetState(EMyLaneState::OutOfLane, TEXT("left the lane zone"));
		}
		else if (Rules.bLaneAssist
			&& !bDriveInput
			&& Now - FMath::Max(LastDriveInputTime, StateEnterTime) >= M->LaneAssistDelay
			&& Speed2D <= M->LaneAssistMaxSpeed)
		{
			// Hands off the drive for LaneAssistDelay, slow, in the zone: the lane flies again. Point & Fly's steering
			// camera sets the drive-intent bit every frame, so a pilot steering with the mouse alone is never taken over.
			EnterFollow(EMyLaneState::Assist, TEXT("no drive input"));
		}
		break;

	case EMyLaneState::OutOfLane:
		if (!bPiloted)
		{
			HandlePilotExit(TEXT("pilot left"));
		}
		else if (bInZone)
		{
			SetState(EMyLaneState::PilotedInLane, TEXT("entered the lane zone"));
		}
		break;

	case EMyLaneState::Parked:
		if (bPiloted)
		{
			EnterPiloted(/*bFromFollow=*/false, TEXT("pilot boarded"));
		}
		break;

	default:
		break;
	}

	// ---- This frame's work ----
	switch (LaneState)
	{
	case EMyLaneState::Cruising:
	case EMyLaneState::Waiting:
	case EMyLaneState::Assist:
		UpdateFollow(*Lanes, *Flight, Dt, Now, Phase);
		break;

	case EMyLaneState::Returning:
		UpdateReturning(*Lanes, *Flight, Dt, Now);
		break;

	case EMyLaneState::Parked:
		Clamp = EMyLaneClamp::None;
		UpdateParked(Now, Phase, bDebugInput);
		break;

	default:
		Clamp = EMyLaneClamp::None;
		break;
	}

	WriteHint(Now);

#if ENABLE_DRAW_DEBUG
	if (UMyLaneSubsystem::GetDebugLevel() >= 1)
	{
		DrawLaneDebug(DebugTargetPoint, 0.f);
	}
#endif
}

float UAirshipLaneComponent::GetLookAheadLength(float Speed) const
{
	const UMyMatchSettings* M = UMyMatchSettings::Get();
	const float S = FMath::Max(Speed, 0.f);

	// The time ahead plus the stop from there at the lane force cap (a blocked target brakes at LaneAccelMax)
	return FMath::Max(M->LaneLookAheadMin, S * M->LaneLookAheadTime + S * S / (2.f * FMath::Max(M->LaneAccelMax, 1.f)));
}

bool UAirshipLaneComponent::RunLookAhead(const UMyLaneSubsystem& Lanes, UAirshipFlightComponent& Flight, double Now, float SweepYaw, float Length)
{
	const UMyMatchSettings* M = UMyMatchSettings::Get();

	if (Now < NextSweepTime)
	{
		return false;
	}

	NextSweepTime = Now + FMath::Max(M->LaneSweepInterval, 0.02f);

	// PR A's hull box sweep: characters, cannonballs, non-ship pawns and the ship's own attachments never count, other
	// ships do
	FHitResult Hit;
	const bool bHit = Flight.SweepHullAhead(SweepYaw, Length, &Hit);

	LastSweepYaw = SweepYaw;
	LastSweepLength = Length;
	bLastSweepHit = bHit;

	if (bHit)
	{
		ClearSweeps = 0;

		// How far along the lane the blocker reaches (its far end decides when a bypass may return)
		const AActor* Blocker = Hit.GetActor();
		BlockerName = GetNameSafe(Blocker);
		BlockerU = Lanes.ProjectU(Hit.bStartPenetrating && Blocker ? Blocker->GetActorLocation() : FVector(Hit.ImpactPoint));

		if (Blocker)
		{
			const FBox Box = Blocker->GetComponentsBoundingBox(/*bNonColliding=*/false);

			if (Box.IsValid)
			{
				for (int32 Corner = 0; Corner < 8; ++Corner)
				{
					const FVector Point((Corner & 1) ? Box.Max.X : Box.Min.X, (Corner & 2) ? Box.Max.Y : Box.Min.Y, (Corner & 4) ? Box.Max.Z : Box.Min.Z);
					BlockerU = FMath::Max(BlockerU, Lanes.ProjectU(Point));
				}
			}
		}

		if (!bBlocked)
		{
			bBlocked = true;
			BlockedSince = Now;
			UE_LOG(LogLane, Log, TEXT("%s team %d: lane blocked by %s %.0f m ahead (look-ahead %.0f m)"), *GetNameSafe(GetOwner()), LaneTeam,
				*BlockerName, Hit.bStartPenetrating ? 0.f : Hit.Distance / 100.f, Length / 100.f);
		}
	}
	else if (bBlocked && ++ClearSweeps >= FMath::Max(M->LaneBlockedClearChecks, 1))
	{
		bBlocked = false;
		BlockedSince = -1.0;
		ClearSweeps = 0;
		UE_LOG(LogLane, Log, TEXT("%s team %d: lane clear again"), *GetNameSafe(GetOwner()), LaneTeam);
	}

	return true;
}

void UAirshipLaneComponent::UpdateFollow(const UMyLaneSubsystem& Lanes, UAirshipFlightComponent& Flight, float Dt, double Now, EMyMatchPhase Phase)
{
	using namespace AirshipLanePrivate;

	const UMyMatchSettings* M = UMyMatchSettings::Get();
	const AAirshipPawn* Ship = GetShip();

	// ---- Pace (B2.4, B2.6) ----
	bool bTeamCap = false;
	bool bFront = false;
	float FrontU = 0.f;
	const float Cap = ComputeCap(Lanes, bTeamCap, bFront, FrontU);

	const bool bReel = Ship && Ship->HasIncomingReel();
	const bool bContactHold = Now < ContactHoldUntil;
	const bool bNotStarted = Phase == EMyMatchPhase::WaitingToStart || Phase == EMyMatchPhase::Countdown;
	const bool bEnded = Phase == EMyMatchPhase::Ended;
	const bool bHoldStill = bBlocked || bContactHold || bNotStarted || bEnded;

	// Proportional toward a point LanePaceOffset ahead of the team front, never below the cruise speed
	float Desired = M->LaneSpeed;

	if (bFront)
	{
		Desired = FMath::Clamp(M->LaneSpeed + M->LanePaceGain * (FrontU + M->LanePaceOffset - ShipU), M->LaneSpeed, FMath::Max(M->LaneSpeed, M->LaneCatchUpSpeed));
	}

	if (bHoldStill)
	{
		Desired = 0.f;
	}

	// Moving out to the bypass line (or back): slowly ahead while mostly across, the diagonal sweep covered that path
	const float CurrentOut = Side * LateralError;
	const float AcrossGap = BypassOffset - CurrentOut;

	if (bBypassActive && FMath::Abs(AcrossGap) > AcrossSweepTolerance)
	{
		Desired = FMath::Min(Desired, M->LaneSpeed);
	}

	// Eases into the cap: no overshoot, no spring back
	Desired = FMath::Min(Desired, FMath::Sqrt(2.f * FMath::Max(M->LaneAccel, 1.f) * FMath::Max(0.f, Cap - TargetU)));

	// Someone reels in with the ship hook: the speed is frozen, so the reel's anchor moves predictably (B7.4)
	if (bReel)
	{
		Desired = TargetSpeed;
	}

	// A stop for a blocker brakes at the lane force cap (the look-ahead's stopping distance assumes it); every other
	// change ramps at LaneAccel
	const float Rate = bHoldStill && Desired < TargetSpeed ? FMath::Max(M->LaneAccel, M->LaneAccelMax) : M->LaneAccel;
	TargetSpeed = FMath::FInterpConstantTo(TargetSpeed, Desired, Dt, FMath::Max(Rate, 1.f));
	const float TargetAccel = (TargetSpeed - LastTargetSpeed) / Dt;
	LastTargetSpeed = TargetSpeed;

	// Never far ahead of the ship; the cap stops the target but never pulls it back
	float NewU = FMath::Min(TargetU + TargetSpeed * Dt, ShipU + M->LaneMaxTargetLead);

	if (!bReel)
	{
		NewU = FMath::Min(NewU, FMath::Max(Cap, TargetU));
	}

	TargetU = FMath::Max(NewU, Lanes.GetLaneStartU());

	// ---- Clamp and Cruising / Waiting ----
	if (bReel)
	{
		Clamp = EMyLaneClamp::Reel;
	}
	else if (bBlocked || bContactHold)
	{
		Clamp = EMyLaneClamp::Blocked;
	}
	else if (bNotStarted)
	{
		Clamp = EMyLaneClamp::NotStarted;
	}
	else if (bEnded)
	{
		Clamp = EMyLaneClamp::Ended;
	}
	else if (bBypassActive)
	{
		Clamp = EMyLaneClamp::Bypass;
	}
	else if (TargetU >= Cap - 10.f)
	{
		Clamp = bTeamCap ? EMyLaneClamp::TeamPace : EMyLaneClamp::PathEnd;
	}
	else
	{
		Clamp = EMyLaneClamp::None;
	}

	if (LaneState == EMyLaneState::Cruising && TargetSpeed <= StoppedSpeed && Desired <= StoppedSpeed)
	{
		SetState(EMyLaneState::Waiting, *FString::Printf(TEXT("target stopped, %s"), GetClampName(Clamp)));
	}
	else if (LaneState == EMyLaneState::Waiting && (TargetSpeed > MovingSpeed || Desired > MovingSpeed))
	{
		SetState(EMyLaneState::Cruising, TEXT("target moving"));
	}

	// ---- Target point ----
	FVector Point;
	FVector Tangent;
	Lanes.GetLanePoint(Side, TargetU, Point, Tangent);

	FVector2D TargetTangent = FVector2D(Tangent.X, Tangent.Y).GetSafeNormal();

	if (TargetTangent.IsNearlyZero())
	{
		TargetTangent = LaneTangent2D;
	}

	const FVector2D TargetNormal(-TargetTangent.Y, TargetTangent.X);
	FVector2D Point2D = FVector2D(Point.X, Point.Y) + TargetNormal * (Side * BypassOffset);

	// Lateral join: the point is never more than LaneJoinStep across from the ship, so a ship off its lane joins it
	// gradually (a bypass ramps in and out the same way)
	const float Across = static_cast<float>(FVector2D::DotProduct(FVector2D(ShipOrigin.X, ShipOrigin.Y) - Point2D, TargetNormal));

	if (M->LaneJoinStep > 0.f && FMath::Abs(Across) > M->LaneJoinStep)
	{
		Point2D += TargetNormal * (Across - FMath::Sign(Across) * M->LaneJoinStep);
	}

	FAirshipUnpilotedTarget Target;
	Target.Mode = EAirshipUnpilotedMode::Lane;
	Target.ForwardSpeed = TargetSpeed;
	Target.HeadingYaw = LaneYawAtShip;
	Target.HoldPoint = Point2D + COMOffset;
	Target.HoldVelocity = TargetTangent * TargetSpeed;
	Target.HoldAccel = TargetTangent * TargetAccel;
	Target.bHasHoldZ = true;
	Target.HoldZ = static_cast<float>(Point.Z);
	Flight.SetLaneTarget(Target, LaneState == EMyLaneState::Assist);

	DebugTargetPoint = FVector(Point2D.X, Point2D.Y, Point.Z);

	// ---- Look-ahead and bypass (B2.7) ----
	const float Length = GetLookAheadLength(FMath::Max(AlongSpeed, TargetSpeed));
	float SweepYaw = LaneYawAtShip;

	if (FMath::Abs(AcrossGap) > AcrossSweepTolerance)
	{
		// Across to the bypass line or back to the lane: along the diagonal the ship will take
		SweepYaw += Side * FMath::RadiansToDegrees(FMath::Atan2(AcrossGap, Length));
	}

	if (!RunLookAhead(Lanes, Flight, Now, SweepYaw, Length))
	{
		return;
	}

	if (bBlocked && !bBypassActive && M->LaneBypassOffset > 0.f && BlockedSince >= 0.0
		&& Now - BlockedSince >= M->LaneBlockedTimeout && Now >= NextBypassTryTime)
	{
		// Blocked too long: try a line LaneBypassOffset further outward (away from the field, only sky there)
		const float Out = M->LaneBypassOffset - CurrentOut;
		const float DiagYaw = LaneYawAtShip + Side * FMath::RadiansToDegrees(FMath::Atan2(Out, Length));
		const float DiagLength = FMath::Sqrt(Length * Length + Out * Out);

		if (!Flight.SweepHullAhead(DiagYaw, DiagLength, nullptr))
		{
			bBypassActive = true;
			BypassOffset = M->LaneBypassOffset;
			bBlocked = false;
			ClearSweeps = 0;
			BlockedSince = -1.0;
			UE_LOG(LogLane, Log, TEXT("%s team %d: going round %s, %.0f m outward"), *GetNameSafe(GetOwner()), LaneTeam, *BlockerName, BypassOffset / 100.f);
		}
		else
		{
			NextBypassTryTime = Now + FMath::Max(M->LaneBlockedTimeout, 1.f);
			UE_LOG(LogLane, Log, TEXT("%s team %d: the bypass line is blocked too, waiting behind %s"), *GetNameSafe(GetOwner()), LaneTeam, *BlockerName);
		}
	}
	else if (bBypassActive && !bBlocked && BlockerU < ShipU - HullHalfLength - BypassClearBehindStern)
	{
		// Past the blocker by a hull length: back to the lane once the way back is clear
		const float Back = -CurrentOut;
		const float BackYaw = LaneYawAtShip + Side * FMath::RadiansToDegrees(FMath::Atan2(Back, Length));

		if (!Flight.SweepHullAhead(BackYaw, FMath::Sqrt(Length * Length + Back * Back), nullptr))
		{
			bBypassActive = false;
			BypassOffset = 0.f;
			UE_LOG(LogLane, Log, TEXT("%s team %d: past %s, back to the lane"), *GetNameSafe(GetOwner()), LaneTeam, *BlockerName);
		}
	}
}

void UAirshipLaneComponent::UpdateParked(double Now, EMyMatchPhase Phase, bool bDebugInput)
{
	const UMyMatchSettings* M = UMyMatchSettings::Get();

	// Parked back in its lane (a pilot's park, or a drift that slows inside the zone): it cruises again
	if (bInZone && Speed2D <= M->LaneParkSpeed && !bDebugInput)
	{
		if (ParkInLaneSince < 0.0)
		{
			ParkInLaneSince = Now;
		}

		if (Now - ParkInLaneSince >= M->LaneParkSettleTime)
		{
			EnterFollow(EMyLaneState::Cruising, TEXT("parked in its lane"));
			return;
		}
	}
	else
	{
		ParkInLaneSince = -1.0;
	}

	// The recall clock runs only while it can happen (B2.11); boarding resets it (the state changes)
	if (!M->bShipRecall || Phase != EMyMatchPhase::InProgress || bDebugInput)
	{
		ParkedSince = Now;
		RecallServerTime = 0.0;
		return;
	}

	if (ParkedSince < 0.0)
	{
		ParkedSince = Now;
	}

	if (RecallServerTime == 0.0)
	{
		// For the HUD ("SHIP RETURNS TO LANE IN 12 s"): in the server time clients compare against
		const UWorld* World = GetWorld();
		const AGameStateBase* GameState = World ? World->GetGameState() : nullptr;
		const double ServerNow = GameState ? GameState->GetServerWorldTimeSeconds() : Now;
		RecallServerTime = FMath::Max(ServerNow + (ParkedSince + M->ShipRecallDelay - Now), 0.001);
	}

	if (Now - ParkedSince >= M->ShipRecallDelay)
	{
		EnterReturning(TEXT("parked outside its lane for ShipRecallDelay"));
	}
}

void UAirshipLaneComponent::UpdateReturning(const UMyLaneSubsystem& Lanes, UAirshipFlightComponent& Flight, float Dt, double Now)
{
	using namespace AirshipLanePrivate;

	const UMyMatchSettings* M = UMyMatchSettings::Get();

	// The own lane's point at the ship's own u
	bool bTeamCap = false;
	bool bFront = false;
	float FrontU = 0.f;
	const float Cap = ComputeCap(Lanes, bTeamCap, bFront, FrontU);
	TargetU = FMath::Clamp(ShipU, Lanes.GetLaneStartU(), Cap);

	FVector Goal;
	FVector GoalTangent;
	Lanes.GetLanePoint(Side, TargetU, Goal, GoalTangent);

	const FVector2D Ship2D(ShipOrigin.X, ShipOrigin.Y);
	const FVector2D Goal2D(Goal.X, Goal.Y);

	// ---- Fallbacks: replaced with no life lost ----
	if (M->ShipRecallMaxDistance > 0.f && FVector::Dist(ShipOrigin, Goal) > M->ShipRecallMaxDistance)
	{
		ReplaceShip(TEXT("too far from its lane"));
		return;
	}

	if (M->ShipRecallMaxTime > 0.f && RecallStartTime >= 0.0 && Now - RecallStartTime > M->ShipRecallMaxTime)
	{
		ReplaceShip(TEXT("not back within ShipRecallMaxTime"));
		return;
	}

	if (bBlocked && RecallBlockedSince >= 0.0 && Now - RecallBlockedSince > M->ShipRecallBlockedTime)
	{
		ReplaceShip(TEXT("blocked for ShipRecallBlockedTime"));
		return;
	}

	// ---- Altitude: over the field when the way home crosses it ----
	const float CrossZ = Lanes.GetPathZ(ShipU) + M->ShipRecallCrossHeight;
	const float FieldClear = Lanes.GetPathHalfWidth() + HullHalfWidth + RecallFieldMargin;

	if (bRecallCrossing && Side * Lanes.GetLateralFromPath(ShipOrigin) >= FieldClear)
	{
		bRecallCrossing = false;
		UE_LOG(LogLane, Log, TEXT("%s team %d: recall crossed the field, down to the lane"), *GetNameSafe(GetOwner()), LaneTeam);
	}

	const bool bHighEnough = ShipOrigin.Z >= CrossZ - RecallClimbTolerance;
	const float HoldZ = bRecallCrossing ? CrossZ : static_cast<float>(Goal.Z);

	// ---- Horizontal target: toward the lane point at up to ShipRecallSpeed, easing in ----
	const FVector2D ToGoal = Goal2D - RecallTargetXY;
	const float Remaining = static_cast<float>(ToGoal.Size());

	if (Remaining > 1.f)
	{
		RecallDir = ToGoal / Remaining;
	}

	float Desired = FMath::Min(M->ShipRecallSpeed, FMath::Sqrt(2.f * FMath::Max(M->LaneAccel, 1.f) * Remaining));

	// Still too low to cross: up first, and not into the field meanwhile. It may close in on the field's edge, and
	// moving away from the path is always allowed (a ship parked over the field's edge on its own side just leaves).
	bool bWaitForClimb = false;

	if (bRecallCrossing && !bHighEnough)
	{
		const FVector2D Next = RecallTargetXY + RecallDir * FMath::Max(Desired * Dt, 100.f);
		const float NextDistance = Lanes.GetDistanceToPath2D(FVector(Next.X, Next.Y, ShipOrigin.Z));
		const float NowDistance = Lanes.GetDistanceToPath2D(FVector(RecallTargetXY.X, RecallTargetXY.Y, ShipOrigin.Z));
		bWaitForClimb = NextDistance < FieldClear && NextDistance <= NowDistance;
	}

	const bool bContactHold = Now < ContactHoldUntil;
	const bool bStop = bBlocked || bContactHold || bWaitForClimb;

	if (bStop)
	{
		Desired = 0.f;
	}

	const float Rate = bStop && Desired < RecallSpeed ? FMath::Max(M->LaneAccel, M->LaneAccelMax) : M->LaneAccel;
	RecallSpeed = FMath::FInterpConstantTo(RecallSpeed, Desired, Dt, FMath::Max(Rate, 1.f));
	const float RecallAccel = (RecallSpeed - LastRecallSpeed) / Dt;
	LastRecallSpeed = RecallSpeed;

	RecallTargetXY += RecallDir * FMath::Min(RecallSpeed * Dt, Remaining);

	// Never far ahead of the ship (a ship held back never gets a target running away from it)
	const FVector2D Lead = RecallTargetXY - Ship2D;

	if (M->LaneMaxTargetLead > 0.f && Lead.Size() > M->LaneMaxTargetLead)
	{
		RecallTargetXY = Ship2D + Lead.GetSafeNormal() * M->LaneMaxTargetLead;
	}

	// Heading toward the lane point while far, then along the lane
	const FVector2D GoalTangent2D = FVector2D(GoalTangent.X, GoalTangent.Y).GetSafeNormal();
	const float HeadingYaw = FVector2D::Distance(Ship2D, Goal2D) > RecallTangentDistance || GoalTangent2D.IsNearlyZero()
		? YawOf(Goal2D - Ship2D)
		: YawOf(GoalTangent2D);

	FAirshipUnpilotedTarget Target;
	Target.Mode = EAirshipUnpilotedMode::Lane;
	Target.ForwardSpeed = RecallSpeed;
	Target.HeadingYaw = HeadingYaw;
	Target.HoldPoint = RecallTargetXY + COMOffset;
	Target.HoldVelocity = RecallDir * RecallSpeed;
	Target.HoldAccel = RecallDir * RecallAccel;
	Target.bHasHoldZ = true;
	Target.HoldZ = HoldZ;
	// The whole recall, the climb over the field and the descent to the lane alike (LaneClimbRate would outlast ShipRecallMaxTime)
	Target.ClimbRate = M->ShipRecallClimbRate;
	Flight.SetLaneTarget(Target, /*bAssist=*/false);

	DebugTargetPoint = FVector(RecallTargetXY.X, RecallTargetXY.Y, HoldZ);

	// ---- Look-ahead along the travel direction; not while it only climbs beside the field ----
	if (bWaitForClimb)
	{
		bBlocked = false;
		ClearSweeps = 0;
		BlockedSince = -1.0;
		RecallBlockedSince = -1.0;
	}
	else if (RunLookAhead(Lanes, Flight, Now, YawOf(RecallDir), GetLookAheadLength(FMath::Max(RecallSpeed, Speed2D))))
	{
		if (bBlocked && RecallBlockedSince < 0.0)
		{
			RecallBlockedSince = Now;
		}
		else if (!bBlocked)
		{
			RecallBlockedSince = -1.0;
		}
	}

	Clamp = bBlocked || bContactHold ? EMyLaneClamp::Blocked : EMyLaneClamp::None;
}


// =============================================================================
// Recall replacement (B2.11 fallback)
// =============================================================================

void UAirshipLaneComponent::ReplaceShip(const TCHAR* Reason)
{
	AAirshipPawn* Ship = GetShip();
	UWorld* World = GetWorld();
	const UMyLaneSubsystem* Lanes = CachedLanes.Get();

	if (bRecallReplacing || !Ship || !World || !Lanes)
	{
		return;
	}

	AMyGameMode* GameMode = World->GetAuthGameMode<AMyGameMode>();

	if (!GameMode)
	{
		UE_LOG(LogLane, Warning, TEXT("%s team %d: recall gives up (%s), but there is no AMyGameMode to replace the ship: it holds"), *Ship->GetName(), LaneTeam, Reason);
		EnterParked(TEXT("recall replacement impossible"));
		return;
	}

	// At the team front, else the match front, else where this ship is (B3.1)
	float U = 0.f;

	if (!Lanes->GetTeamFrontU(LaneTeam, U) && !Lanes->GetTeamFrontU(MyMatch::NoTeam, U))
	{
		U = ShipU;
	}

	U = FMath::Clamp(U, Lanes->GetLaneStartU(), Lanes->GetCruiseEndU());

	// The crew goes along: gunners at their stations and everyone riding the deck (team-blind, like riding itself)
	TArray<int32> GunnerStations;
	TArray<ACharacter*> Crew;

	for (int32 Station = 0; Station < Airship::NumStations; ++Station)
	{
		if (ACharacter* Gunner = Ship->GetStationGunner(Station))
		{
			GunnerStations.Add(Station);
			Crew.AddUnique(Gunner);
		}
	}

	for (ACharacter* Rider : Ship->GetPassengers())
	{
		if (IsValid(Rider) && !Rider->IsAttachedTo(Ship) && Ship->IsRiding(Rider))
		{
			Crew.AddUnique(Rider);
		}
	}

	// Set before the spawn: the game mode's OnTeamShipDestroyed reads it, and this ship does nothing more
	bRecallReplacing = true;

	UE_LOG(LogLane, Warning, TEXT("%s team %d: recall gives up (%s): a new ship at u %.1f m, no life lost, %d crew moved"),
		*Ship->GetName(), LaneTeam, Reason, U / 100.f, Crew.Num());

	AAirshipPawn* NewShip = GameMode->SpawnTeamShip(LaneTeam, U);

	if (!IsValid(NewShip))
	{
		bRecallReplacing = false;
		UE_LOG(LogLane, Error, TEXT("%s team %d: SpawnTeamShip gave no ship: this one stays and holds"), *Ship->GetName(), LaneTeam);
		EnterParked(TEXT("recall replacement failed"));
		return;
	}

	for (const int32 Station : GunnerStations)
	{
		Ship->DismountGunner(Station, /*bEject=*/false);
	}

	TArray<FTransform> Spots;
	NewShip->GetDeckSpawnTransforms(Crew.Num(), Spots);

	for (int32 Index = 0; Index < Crew.Num(); ++Index)
	{
		if (Spots.IsValidIndex(Index))
		{
			PutOnDeck(Crew[Index], Spots[Index]);
		}
	}

	LeaveLane(TEXT("replaced by a recall"), /*bRestoreDrift=*/false);

	// Destroyed next frame, outside its own Tick (the flight model still runs after this in AAirshipPawn::Tick)
	const TWeakObjectPtr<AAirshipPawn> WeakShip(Ship);
	World->GetTimerManager().SetTimerForNextTick(FTimerDelegate::CreateLambda([WeakShip]()
	{
		if (AAirshipPawn* OldShip = WeakShip.Get())
		{
			OldShip->Destroy();
		}
	}));
}

void UAirshipLaneComponent::PutOnDeck(ACharacter* Character, const FTransform& Spot)
{
	if (!IsValid(Character) || Character->IsActorBeingDestroyed())
	{
		return;
	}

	const FRotator Rotation(0.0, Spot.Rotator().Yaw, 0.0);

	if (!Character->TeleportTo(Spot.GetLocation(), Rotation))
	{
		Character->SetActorLocationAndRotation(Spot.GetLocation(), Rotation, false, nullptr, ETeleportType::TeleportPhysics);
	}

	// Lands on the deck and takes the hull as its base
	if (UCharacterMovementComponent* Movement = Character->GetCharacterMovement())
	{
		Movement->StopMovementImmediately();
		Movement->SetMovementMode(MOVE_Falling);
	}
}


// =============================================================================
// Notifications and console
// =============================================================================

void UAirshipLaneComponent::NotifyPilotChanged(bool bHasPilot)
{
	using namespace AirshipLanePrivate;

	const AAirshipPawn* Ship = GetShip();
	const UMyLaneSubsystem* Lanes = CachedLanes.Get();

	if (!Ship || !Ship->HasAuthority() || LaneState == EMyLaneState::NoLane || !Lanes || !Measure(*Lanes))
	{
		return;
	}

	if (bHasPilot)
	{
		if (IsFollowing(LaneState) || LaneState == EMyLaneState::Returning)
		{
			EnterPiloted(/*bFromFollow=*/true, TEXT("pilot boarded"));
		}
		else if (LaneState == EMyLaneState::Parked)
		{
			EnterPiloted(/*bFromFollow=*/false, TEXT("pilot boarded"));
		}
	}
	else if (IsPiloted(LaneState) && !Ship->HasPilot() && !Ship->GetController())
	{
		// Still possessed (a leaving player's controller unpossesses after this): the next update sees it
		HandlePilotExit(TEXT("pilot exit"));
	}
}

void UAirshipLaneComponent::NotifyHullContact(const AActor* Other, const FHitResult& Hit)
{
	const AAirshipPawn* Ship = GetShip();
	const UPrimitiveComponent* Hull = Ship ? Ship->GetHull() : nullptr;
	const UWorld* World = GetWorld();

	const bool bLaneFlies = AirshipLanePrivate::IsFollowing(LaneState) || LaneState == EMyLaneState::Assist || LaneState == EMyLaneState::Returning;

	if (!bLaneFlies || !Hull || !World || !Other || !Ship->HasAuthority())
	{
		return;
	}

	// PR A's drift rule: its own parts and riders, characters, cannonballs and pawns that aren't ships never stop it
	if (Other == Ship || Other->IsAttachedTo(Ship) || Other->IsA<ACharacter>() || Other->IsA<AAirshipCannonball>()
		|| (Other->IsA<APawn>() && !Other->IsA<AAirshipPawn>()))
	{
		return;
	}

	// At the bow: ahead of the centre of mass by more than 30 % of the hull's half length, facing the travel direction
	const FTransform BodyTM = Hull->GetComponentTransform();
	const FBox Local = Hull->CalcBounds(FTransform::Identity).GetBox();
	const double HalfLength = Local.IsValid ? 0.5 * (Local.Max.X - Local.Min.X) : 0.0;
	const double AheadOfCOM = BodyTM.InverseTransformPosition(Hit.ImpactPoint).X - BodyTM.InverseTransformPosition(Hull->GetCenterOfMass()).X;
	const FVector2D Travel = LaneState == EMyLaneState::Returning ? RecallDir : LaneTangent2D;
	const FVector TravelDir(Travel.X, Travel.Y, 0.0);

	if (AheadOfCOM <= 0.3 * HalfLength || FMath::Abs(FVector::DotProduct(Hit.ImpactNormal, TravelDir)) < UAirshipSettings::Get()->DriftBowHitMinDot)
	{
		return;
	}

	const double Now = World->GetTimeSeconds();

	if (Now >= ContactHoldUntil)
	{
		UE_LOG(LogLane, Log, TEXT("%s team %d: bow contact with %s, the lane waits %.0f s"), *Ship->GetName(), LaneTeam, *GetNameSafe(Other),
			AirshipLanePrivate::ContactHoldSeconds);
	}

	ContactHoldUntil = Now + AirshipLanePrivate::ContactHoldSeconds;
}

void UAirshipLaneComponent::NotifyTeamChanged()
{
	const AAirshipPawn* Ship = GetShip();

	if (!Ship || !Ship->HasAuthority())
	{
		return;
	}

	// The next update picks the lane (and the state) for the new team; a free ship gets PR A's drift limit back there
	SetState(EMyLaneState::NoLane, TEXT("team changed"));
	Side = 0;
	LaneTeam = MyMatch::NoTeam;
	bInZone = false;
}

void UAirshipLaneComponent::DebugTeleportToLane(float U, float DeltaZ)
{
	AAirshipPawn* Ship = GetShip();
	UPrimitiveComponent* Hull = Ship ? Ship->GetHull() : nullptr;
	UMyLaneSubsystem* Lanes = UMyLaneSubsystem::Get(this);

	if (!Ship || !Hull || !Ship->HasAuthority() || !Lanes || !Lanes->HasLanes())
	{
		UE_LOG(LogLane, Warning, TEXT("%s: no teleport, no lane (server only)"), *GetNameSafe(Ship));
		return;
	}

	CachedLanes = Lanes;
	const int8 TeleportSide = Side != 0 ? Side : Lanes->GetSideForTeam(Ship->GetTeamId());
	FVector Point;
	FVector Tangent;

	if (!Lanes->GetLanePoint(TeleportSide, U, Point, Tangent))
	{
		UE_LOG(LogLane, Warning, TEXT("%s: no teleport, team %d has no lane"), *Ship->GetName(), Ship->GetTeamId());
		return;
	}

	Point.Z += DeltaZ;
	Ship->SetActorLocationAndRotation(Point, FRotator(0.0, Tangent.Rotation().Yaw, 0.0), false, nullptr, ETeleportType::TeleportPhysics);

	if (Hull->IsSimulatingPhysics())
	{
		Hull->SetPhysicsLinearVelocity(FVector::ZeroVector);
		Hull->SetPhysicsAngularVelocityInDegrees(FVector::ZeroVector);
	}

	UE_LOG(LogLane, Log, TEXT("%s team %d: teleported onto its lane at u %.1f m, dZ %.1f m"), *Ship->GetName(), Ship->GetTeamId(), U / 100.f, DeltaZ / 100.f);

	// Unpiloted: it cruises from there (a piloted ship stays the pilot's)
	const bool bPiloted = Ship->HasPilot() || Ship->GetController() != nullptr;

	if (LaneState != EMyLaneState::NoLane && !bPiloted && Side != 0 && Measure(*Lanes))
	{
		EnterFollow(EMyLaneState::Cruising, TEXT("teleported"));
		TargetU = FMath::Clamp(U, Lanes->GetLaneStartU(), Lanes->GetPathEndU());
		TargetSpeed = 0.f;
		LastTargetSpeed = 0.f;
	}
}

bool UAirshipLaneComponent::StartRecall()
{
	const AAirshipPawn* Ship = GetShip();
	const UMyLaneSubsystem* Lanes = CachedLanes.Get();

	if (!Ship || !Ship->HasAuthority() || !Lanes || LaneState == EMyLaneState::NoLane || AirshipLanePrivate::IsPiloted(LaneState)
		|| LaneState == EMyLaneState::Returning || !Measure(*Lanes))
	{
		return false;
	}

	EnterReturning(TEXT("recall asked for"));
	return true;
}

void UAirshipLaneComponent::WriteHint(double Now)
{
	using namespace AirshipLanePrivate;

	if (Now < NextHintTime)
	{
		return;
	}

	NextHintTime = Now + FMath::Max(UMyMatchSettings::Get()->LaneHintInterval, 0.f);

	FMyLaneHint Hint;
	Hint.LateralDm = ToDecimetres16(LateralError);
	Hint.VerticalDm = ToDecimetres16(VerticalError);
	Hint.ProgressDm = FMath::RoundToInt32(ShipU / 10.f);
	Hint.LaneYawDeg10 = static_cast<int16>(FMath::RoundToInt32(FRotator::NormalizeAxis(LaneYawAtShip) * 10.f));
	Hint.Clamp = static_cast<uint8>(Clamp);

	// Only a real change goes out (the property compare would skip it too, this skips the dirtying)
	if (Hint.LateralDm != LaneHint.LateralDm || Hint.VerticalDm != LaneHint.VerticalDm || Hint.ProgressDm != LaneHint.ProgressDm
		|| Hint.LaneYawDeg10 != LaneHint.LaneYawDeg10 || Hint.Clamp != LaneHint.Clamp)
	{
		LaneHint = Hint;
	}
}

void UAirshipLaneComponent::DrawLaneDebug(const FVector& TargetPoint, float Duration) const
{
#if ENABLE_DRAW_DEBUG
	const UWorld* World = GetWorld();
	const AAirshipPawn* Ship = GetShip();

	if (!World || !Ship || LaneState == EMyLaneState::NoLane)
	{
		return;
	}

	const FColor Color = UMyTeamLibrary::GetTeamColor(LaneTeam).ToFColor(true);
	const bool bFlies = AirshipLanePrivate::IsFollowing(LaneState) || LaneState == EMyLaneState::Assist || LaneState == EMyLaneState::Returning;

	if (bFlies)
	{
		DrawDebugSphere(World, TargetPoint, 300.f, 12, Color, false, Duration, 0, 20.f);
		DrawDebugLine(World, ShipOrigin, TargetPoint, Color, false, Duration, 0, 10.f);
	}

	DrawDebugString(World, ShipOrigin + FVector(0.0, 0.0, 1500.0),
		FString::Printf(TEXT("%s %s %.1f m/s"), GetLaneStateName(LaneState), GetClampName(Clamp), GetTargetSpeed() / 100.f),
		nullptr, Color, Duration, false, 1.2f);

	// Level 2: the last look-ahead sweep (red when it hit), with the hull box at its end
	if (UMyLaneSubsystem::GetDebugLevel() >= 2 && LastSweepLength > 0.f && bFlies)
	{
		const FVector Direction = FRotator(0.0, LastSweepYaw, 0.0).Vector();
		const FVector End = ShipOrigin + Direction * LastSweepLength;
		const FColor SweepColor = bLastSweepHit ? FColor::Red : FColor::Green;
		DrawDebugLine(World, ShipOrigin, End, SweepColor, false, Duration, 0, 15.f);
		DrawDebugBox(World, End, FVector(HullHalfLength, HullHalfWidth, 400.0), FRotator(0.0, LastSweepYaw, 0.0).Quaternion(), SweepColor, false, Duration, 0, 15.f);
	}
#endif
}
