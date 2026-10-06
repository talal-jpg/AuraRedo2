// Fill out your copyright notice in the Description page of Project Settings.


#include "Actors/MyHexBridgeSubsystem.h"

#include "Actors/MyHexBridge.h"
#include "Actors/MyHexBridgeSettings.h"
#include "Actors/MyHexPlatform.h"
#include "Algo/Reverse.h"
#include "CollisionQueryParams.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/SplineComponent.h"
#include "DrawDebugHelpers.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "TimerManager.h"

DEFINE_LOG_CATEGORY_STATIC(LogHexBridgeSubsystem, Log, All);

// Spreads the cost of destroying replicated platforms when the lead moves far quickly
static constexpr int32 MaxPlatformCullsPerFrame = 4;


// Named, not anonymous: Unreal's unity build compiles this file together with MyHexBridgeBuilder.cpp,
// which defines the same names in its own anonymous namespace.
namespace HexBridgeSubsystemTrace
{
	// Same trace layout as AMyHexBridgeBuilder.

	// The traces run this far below the walkable surface, inside the pillars rather than skimming
	// their top faces, which are coplanar with every edge's rim.
	constexpr float BridgeTraceDepth = 5.f;

	// A trace starts this far outside its own tile so it can't begin inside the source collision...
	constexpr float BridgeTraceStartOffset = 5.f;

	// ...and ends this far inside the target tile so it is guaranteed to hit it.
	constexpr float BridgeTraceOvershoot = 10.f;

	// The first hit must be within this many HexRadius of the target side.
	constexpr float BridgeTraceTolerance = 0.6f;
}


// =============================================================================
// Planner constants and geometry
// =============================================================================

namespace HexBridgePlan
{
	constexpr double Inf = TNumericLimits<double>::Max();
	constexpr double Sqrt3Half = 0.8660254037844386;

	// Option generation: facing edges per side and pair, how directly they must face the other
	// platform, edge pairs kept per pair and per end tile (per end side on islets).
	constexpr int32 CandidateEdges = 12;
	constexpr double FacingDot = 0.25;
	constexpr int32 MaxOptions = 10;
	constexpr int32 OptionsPerEndTile = 2;
	constexpr double MinOptionLength = 100.0;

	// Wide options (FALLBACK / RESCUE): twice the edges and options, a wider end angle, no per-tile limit.
	constexpr int32 WideFactor = 2;
	constexpr double WideEndAngleDegrees = 5.0;

	// Visual cost terms, in radians^2: the angle a deck bends through beyond the skew allowance, the
	// angle it meets a tile side with, its net heading change, and its slope.
	constexpr double TurnPenalty = 1.5;
	constexpr double SkewPenalty = 1.0;
	constexpr double ArcPenalty = 1.0;
	constexpr double SlopePenalty = 0.5;
	constexpr double SkewAllowanceDegrees = 12.0;

	// Deck shape. Decks shorter than MinCurvedLength stay straight. The optional sag is off.
	constexpr double MinCurvedLength = 500.0;
	constexpr double MinTurnRadius = 400.0;
	constexpr double MaxLateralDeviation = 150.0;
	constexpr double TangentScale = 1.0;
	constexpr double SagRatio = 0.0;
	constexpr double SagMax = 0.0;
	constexpr double CurveSlopeMarginDegrees = 0.05;
	constexpr int32 DeckSamples = 32;

	// A curved deck this close to its chord is tested and traced like a straight one.
	constexpr double StraightLateralTol = 25.0;
	constexpr double StraightSagTol = 60.0;

	// Coarse deck polyline step, and one trace per this much curved deck (2 to 8 traces).
	constexpr double CoarseStep = 100.0;
	constexpr double TraceSegmentLength = 500.0;
	constexpr int32 MinTraceSegments = 2;
	constexpr int32 MaxTraceSegments = 8;

	// Kinds: GridSize >= StreamMinGridSize within CentreMaxOffset of the path is a centre platform.
	constexpr double CentreMaxOffset = 1500.0;
	constexpr int32 StreamMinGridSize = 6;
	constexpr int32 SmallGridSize = 2;

	// End rules (distances in HexRadius where noted).
	constexpr double StepSpacing = 1.4;
	constexpr double StepDivergeDegrees = 100.0;
	constexpr double SpreadFarSpacing = 6.0;
	constexpr double SpreadFarDivergeDegrees = 25.0;
	constexpr double FanDegrees = 20.0;
	constexpr double FanDistance = 800.0;

	// Crossings: decks sharing a platform are tested once this much is trimmed off the shared end;
	// an intersection this close to a shared end is where they meet, not a crossing. Optional links
	// keep this far from the other chain's decks in plan view.
	constexpr double SharedTrim = 300.0;
	constexpr double SharedEndTolerance = 100.0;
	constexpr double OtherChainOptionalGap = 100.0;

	// Clearance: pillar band = [bottom - PillarHeadroom, top + ClearanceAbove]. FALLBACK / RESCUE
	// clearance. Own platforms' other tiles near deck height (OwnHeightBand), beyond OwnSkip of the end.
	constexpr double PillarHeadroom = 250.0;
	constexpr double ClearanceAbove = 500.0;
	constexpr double RelaxedClearance = 120.0;
	constexpr double OwnClearance = 30.0;
	constexpr double OwnSkip = 100.0;
	constexpr double CurvedOwnClearance = 50.0;
	constexpr double CurvedOwnSkip = 150.0;
	constexpr double OwnHeightBand = 300.0;

	// Natural-neighbour rules for optional links: empty lens (disc of GabrielScale * chord), not the
	// long side of a triangle, islet lengths.
	constexpr double GabrielScale = 0.9;
	constexpr double TriangleRatio = 0.85;
	constexpr double IsletThroughLength = 2200.0;
	constexpr double IsletThroughDegrees = 120.0;

	// SPINE: consecutive centre platforms along the path get their best route first.
	constexpr double SpineMaxGap = 7500.0;
	constexpr int32 SpineMaxHops = 4;
	constexpr int32 SpineAttempts = 4;
	constexpr double SpineSkimScale = 0.7;
	constexpr double SpineSkimPenalty = 1.5;
	constexpr int32 SpineExtraDegree = 1;

	// TREE: an option that failed only an end rule is re-queued once with relaxed rules at this cost factor.
	constexpr double TreeRelaxPenalty = 1.3;

	// LOOP: build when the walk is longer than stretch(L) * L, stretch rising with L.
	constexpr double LoopStretch = 1.5;
	constexpr double LoopStretchLong = 3.0;
	constexpr double LoopShortLength = 800.0;
	constexpr double LoopLongLength = 2500.0;

	// LEAF: a platform with one bridge gets a short second link that saves a real walk.
	constexpr double DeadEndMaxLength = 1600.0;
	constexpr double DeadEndStretch = 1.6;

	// ROUTE / BYPASS / BRANCH.
	constexpr double RouteSpacing = 0.6;
	constexpr double RouteSpread = 0.5;
	constexpr double RouteGabrielScale = 0.6;
	constexpr double RouteCutRadius = 9000.0;
	constexpr double CutNearNew = 6000.0;
	constexpr double BypassStretch = 2.0;
	constexpr double BypassMaxSpan = 12000.0;
	constexpr double BypassMinRadius = 6000.0;
	constexpr double BypassPenalty = 3.0;
	constexpr double BypassNewCost = 500.0;
	constexpr int32 BypassAttempts = 3;
	constexpr int32 CutMinBranch = 2;
	constexpr double CutRadius = 4500.0;
	constexpr double CutMaxLength = 2000.0;
	constexpr int32 ResilienceExtraDegree = 1;

	// Rule-set factors.
	constexpr double RelaxedSpacing = 0.7;
	constexpr double RelaxedSpread = 0.375;
	constexpr double FallbackSpacing = 0.56;
	constexpr double FallbackSpread = 0.375;
	constexpr int32 FallbackExtraDegree = 2;

	// Bridge record grid cell (cm).
	constexpr double RecordCellSize = 2000.0;

	using FPolyline = TArray<FVector, TInlineAllocator<64>>;

	inline uint64 MakeEdgeKey(int32 Serial, int32 Order)
	{
		return (static_cast<uint64>(static_cast<uint32>(Serial)) << 32) | static_cast<uint32>(Order);
	}

	inline double Dist2D(const FVector& A, const FVector& B)
	{
		return FMath::Sqrt(FMath::Square(A.X - B.X) + FMath::Square(A.Y - B.Y));
	}

	inline FVector2D Rotate2D(const FVector2D& V, double Angle)
	{
		const double C = FMath::Cos(Angle);
		const double S = FMath::Sin(Angle);
		return FVector2D(V.X * C - V.Y * S, V.X * S + V.Y * C);
	}

	/** Distance from (PX, PY) to segment S-E in 2D; OutT = parameter of the closest point. */
	inline double PointSegment(double PX, double PY, const FVector& S, const FVector& E, double& OutT)
	{
		const double ABX = E.X - S.X;
		const double ABY = E.Y - S.Y;
		const double LengthSq = ABX * ABX + ABY * ABY;

		if (LengthSq < 1e-12)
		{
			OutT = 0.0;
			return FMath::Sqrt(FMath::Square(PX - S.X) + FMath::Square(PY - S.Y));
		}

		const double T = FMath::Clamp(((PX - S.X) * ABX + (PY - S.Y) * ABY) / LengthSq, 0.0, 1.0);
		OutT = T;
		return FMath::Sqrt(FMath::Square(PX - (S.X + ABX * T)) + FMath::Square(PY - (S.Y + ABY * T)));
	}

	/** Proper or touching intersection of two segments in 2D, with the parameters on each. */
	inline bool SegmentIntersect2D(const FVector& P1, const FVector& P2, const FVector& Q1, const FVector& Q2, double& OutS, double& OutT)
	{
		const double RX = P2.X - P1.X;
		const double RY = P2.Y - P1.Y;
		const double SX = Q2.X - Q1.X;
		const double SY = Q2.Y - Q1.Y;
		const double Den = RX * SY - RY * SX;

		if (FMath::Abs(Den) < 1e-12)
		{
			return false;
		}

		const double QPX = Q1.X - P1.X;
		const double QPY = Q1.Y - P1.Y;
		const double S = (QPX * SY - QPY * SX) / Den;
		const double T = (QPX * RY - QPY * RX) / Den;

		if (S >= -1e-12 && S <= 1.0 + 1e-12 && T >= -1e-12 && T <= 1.0 + 1e-12)
		{
			OutS = S;
			OutT = T;
			return true;
		}

		return false;
	}

	/** 2D distance between two segments (0 when they intersect), with the parameters of the closest points. */
	inline double SegmentDistance2D(const FVector& P1, const FVector& P2, const FVector& Q1, const FVector& Q2, double& OutU, double& OutV)
	{
		if (SegmentIntersect2D(P1, P2, Q1, Q2, OutU, OutV))
		{
			return 0.0;
		}

		double T = 0.0;
		double Best = PointSegment(P1.X, P1.Y, Q1, Q2, T);
		OutU = 0.0;
		OutV = T;

		double D = PointSegment(P2.X, P2.Y, Q1, Q2, T);

		if (D < Best)
		{
			Best = D;
			OutU = 1.0;
			OutV = T;
		}

		D = PointSegment(Q1.X, Q1.Y, P1, P2, T);

		if (D < Best)
		{
			Best = D;
			OutU = T;
			OutV = 0.0;
		}

		D = PointSegment(Q2.X, Q2.Y, P1, P2, T);

		if (D < Best)
		{
			Best = D;
			OutU = T;
			OutV = 1.0;
		}

		return Best;
	}

	inline double PolyLength2D(TConstArrayView<FVector> P)
	{
		double Length = 0.0;

		for (int32 Index = 0; Index + 1 < P.Num(); ++Index)
		{
			Length += Dist2D(P[Index], P[Index + 1]);
		}

		return Length;
	}

	/** P with Cut cm of 2D arc length removed at its start (bFromStart) or end; keeps at least its middle. */
	inline void PolyTrim(TConstArrayView<FVector> P, bool bFromStart, double Cut, FPolyline& Out)
	{
		Out.Reset();

		if (Cut <= 0.0 || P.Num() < 2)
		{
			Out.Append(P.GetData(), P.Num());
			return;
		}

		FPolyline Q;
		Q.Append(P.GetData(), P.Num());

		if (!bFromStart)
		{
			Algo::Reverse(Q);
		}

		Cut = FMath::Min(Cut, 0.5 * PolyLength2D(Q));

		bool bFound = false;
		double Acc = 0.0;

		for (int32 Index = 0; Index + 1 < Q.Num(); ++Index)
		{
			const FVector& A = Q[Index];
			const FVector& B = Q[Index + 1];
			const double Length = Dist2D(A, B);

			if (Acc + Length >= Cut && Length > 0.0)
			{
				Out.Add(A + (B - A) * ((Cut - Acc) / Length));

				for (int32 Rest = Index + 1; Rest < Q.Num(); ++Rest)
				{
					Out.Add(Q[Rest]);
				}

				bFound = true;
				break;
			}

			Acc += Length;
		}

		if (!bFound || Out.Num() < 2)
		{
			Out.Reset();
			Out.Add(Q[Q.Num() - 2]);
			Out.Add(Q.Last());
		}

		if (!bFromStart)
		{
			Algo::Reverse(Out);
		}
	}

	/** Smallest 2D distance between two polylines, and the deck heights at the closest points. */
	inline double PolyDistance(TConstArrayView<FVector> P, TConstArrayView<FVector> Q, double& OutZP, double& OutZQ)
	{
		double Best = Inf;
		OutZP = 0.0;
		OutZQ = 0.0;

		for (int32 I = 0; I + 1 < P.Num(); ++I)
		{
			for (int32 J = 0; J + 1 < Q.Num(); ++J)
			{
				double U = 0.0;
				double V = 0.0;
				const double D = SegmentDistance2D(P[I], P[I + 1], Q[J], Q[J + 1], U, V);

				if (D < Best)
				{
					Best = D;
					OutZP = P[I].Z + (P[I + 1].Z - P[I].Z) * U;
					OutZQ = Q[J].Z + (Q[J + 1].Z - Q[J].Z) * V;
				}
			}
		}

		return Best;
	}

	/** Where two polylines intersect in 2D. */
	inline void PolyIntersections(TConstArrayView<FVector> P, TConstArrayView<FVector> Q, TArray<FVector2D, TInlineAllocator<8>>& Out)
	{
		Out.Reset();

		for (int32 I = 0; I + 1 < P.Num(); ++I)
		{
			for (int32 J = 0; J + 1 < Q.Num(); ++J)
			{
				double U = 0.0;
				double V = 0.0;

				if (SegmentIntersect2D(P[I], P[I + 1], Q[J], Q[J + 1], U, V))
				{
					Out.Emplace(P[I].X + (P[I + 1].X - P[I].X) * U, P[I].Y + (P[I + 1].Y - P[I].Y) * U);
				}
			}
		}
	}

	inline FBox2D PolyBounds(TConstArrayView<FVector> P)
	{
		FBox2D Box(ForceInit);

		for (const FVector& Point : P)
		{
			Box += FVector2D(Point.X, Point.Y);
		}

		return Box;
	}

	// Cubic Hermite segment, UE convention (tangents = derivative with respect to the segment parameter)

	inline FVector HermitePoint(const FVector& P0, const FVector& T0, const FVector& P1, const FVector& T1, double T)
	{
		const double T2 = T * T;
		const double T3 = T2 * T;
		return P0 * (2.0 * T3 - 3.0 * T2 + 1.0) + T0 * (T3 - 2.0 * T2 + T) + P1 * (-2.0 * T3 + 3.0 * T2) + T1 * (T3 - T2);
	}

	inline FVector2D HermitePoint2D(const FVector2D& P0, const FVector2D& T0, const FVector2D& P1, const FVector2D& T1, double T)
	{
		const double T2 = T * T;
		const double T3 = T2 * T;
		return P0 * (2.0 * T3 - 3.0 * T2 + 1.0) + T0 * (T3 - 2.0 * T2 + T) + P1 * (-2.0 * T3 + 3.0 * T2) + T1 * (T3 - T2);
	}

	inline FVector2D HermiteVelocity2D(const FVector2D& P0, const FVector2D& T0, const FVector2D& P1, const FVector2D& T1, double T)
	{
		const double T2 = T * T;
		return P0 * (6.0 * T2 - 6.0 * T) + T0 * (3.0 * T2 - 4.0 * T + 1.0) + P1 * (-6.0 * T2 + 6.0 * T) + T1 * (3.0 * T2 - 2.0 * T);
	}

	inline FVector2D HermiteAcceleration2D(const FVector2D& P0, const FVector2D& T0, const FVector2D& P1, const FVector2D& T1, double T)
	{
		return P0 * (12.0 * T - 6.0) + T0 * (6.0 * T - 4.0) + P1 * (-12.0 * T + 6.0) + T1 * (6.0 * T - 2.0);
	}

	inline double WrapAngleDistance(double A, double B)
	{
		// |A - B| folded into [0, pi]
		double X = A - B + PI;
		X -= 2.0 * PI * FMath::FloorToDouble(X / (2.0 * PI));
		return FMath::Abs(X - PI);
	}
}


// =============================================================================
// Planner (one batch, one game-thread frame)
// =============================================================================

struct UMyHexBridgeSubsystem::FPlanner
{
	// -------------------------------------------------------------------------
	// Types
	// -------------------------------------------------------------------------

	/** Why an option was rejected (the first failing check). */
	enum class EFail : uint8
	{
		None,
		Deck,
		Cap,
		SameSide,
		Spacing,
		Spread,
		Fan,
		Cross,
		Clearance,
		Trace
	};

	/** Factors on the end rules, extra degree and clearance of one build attempt. */
	struct FRules
	{
		double Spacing = 1.0;
		double Spread = 1.0;
		int32 ExtraDegree = 0;
		bool bFan = true;
		bool bOptional = false;
		bool bRelaxedClearance = false;
	};

	/** One bridge end (live or planned) on a platform. */
	struct FEnd
	{
		int32 Record = INDEX_NONE;
		uint64 EdgeKey = 0;
		FVector Point = FVector::ZeroVector;

		/** Angle of the end around the platform centre. */
		double Angle = 0.0;

		/** Deck direction leaving the platform. */
		FVector2D Dir = FVector2D::ZeroVector;
	};

	/** A registered platform as this batch sees it. Plats are sorted by Serial, so index order is Serial order. */
	struct FPlat
	{
		FPlatformEntry* Entry = nullptr;
		AMyHexPlatform* Actor = nullptr;
		FIntPoint Cell = FIntPoint::ZeroValue;

		/** Position in the planned set (the "new" platforms), INDEX_NONE = not in it. */
		int32 NewRank = INDEX_NONE;

		bool bBatchNew = false;
		bool bCollapsing = false;
		bool bEdgesResolved = false;
		bool bHasDeadTiles = false;

		TBitArray<> DeadTiles;

		/** Live edges, resolved once per batch on first use. */
		TArray<FEdgeWorld> Edges;

		TArray<FEnd> Ends;

		/** This batch's candidates touching the platform. */
		TArray<int32> Cands;
	};

	struct FDeck
	{
		/** Coarse polyline for crossing and clearance tests. */
		TArray<FVector, TInlineAllocator<2>> Coarse;

		/** Curved decks only (empty = traced like a straight deck). */
		TArray<FVector> TracePoints;

		FVector T0 = FVector::ZeroVector;
		FVector T1 = FVector::ZeroVector;
		FBox2D Bounds = FBox2D(ForceInit);
		double Arc = 0.0;
		bool bCurved = false;
	};

	/** One edge pair of a candidate. A = the candidate's first platform (higher Serial). */
	struct FOption
	{
		int32 EdgeA = INDEX_NONE;
		int32 EdgeB = INDEX_NONE;
		double L2 = 0.0;
		double L3 = 0.0;
		double ThetaA = 0.0;
		double ThetaB = 0.0;
		double PhiA = 0.0;
		double PhiB = 0.0;
		double Cost = 0.0;
		FVector2D DirA = FVector2D::ZeroVector;
		FVector2D DirB = FVector2D::ZeroVector;
		FDeck Deck;

		// Lazy results: -1 unknown, 0 no, 1 yes. Clear is per clearance (normal, relaxed).
		int8 DeckState = -1;
		int8 Traced = -1;
		int8 Lens = -1;
		int8 Clear[2] = { -1, -1 };
	};

	/** A platform pair that may get a bridge. */
	struct FCand
	{
		int32 A = INDEX_NONE;
		int32 B = INDEX_NONE;
		int32 SerialMin = 0;
		int32 SerialMax = 0;
		double Jump = 0.0;
		int32 Built = INDEX_NONE;
		TArray<FOption, TInlineAllocator<HexBridgePlan::MaxOptions>> Options;

		/** The cheapest option not known to fail its trace. */
		int32 Best() const
		{
			for (int32 Index = 0; Index < Options.Num(); ++Index)
			{
				if (Options[Index].Traced != 0)
				{
					return Index;
				}
			}

			return INDEX_NONE;
		}

		bool operator<(const FCand& Other) const
		{
			if (Options[0].Cost != Other.Options[0].Cost)
			{
				return Options[0].Cost < Other.Options[0].Cost;
			}

			return SerialMin != Other.SerialMin ? SerialMin < Other.SerialMin : SerialMax < Other.SerialMax;
		}
	};

	struct FPlayer
	{
		const AActor* Base = nullptr;
		FVector Location = FVector::ZeroVector;
	};

	/** Cut edges of one chain's bridge graph. */
	struct FCutGraph
	{
		/** Per platform: (neighbour, record). */
		TArray<TArray<TPair<int32, int32>>> Adj;

		/** Platforms with at least one bridge of the chain, in Serial order. */
		TArray<int32> Nodes;

		/** Cut records (bridges whose loss splits the graph). */
		TArray<int32> Cuts;
	};

	/** Cut edges plus what ROUTE needs: route cuts, 2-edge-connected components and the bridge tree. */
	struct FRouteGraph
	{
		FCutGraph Graph;
		TSet<int32> RouteCuts;
		TArray<int32> Comp;
		TArray<TArray<TPair<int32, int32>>> Tree;
	};

	struct FStats
	{
		int32 Pairs = 0;
		int32 Traces = 0;
		int32 TraceCacheHits = 0;
		int32 Kept = 0;
		int32 Spawned = 0;
		int32 DestroyedReplan = 0;
		int32 DestroyedRevalidate = 0;
		int32 Curved = 0;
		int32 RouteCutsLeft = 0;
		int32 Planned[static_cast<int32>(EBridgePass::Num)] = {};
	};


	// -------------------------------------------------------------------------
	// State
	// -------------------------------------------------------------------------

	UMyHexBridgeSubsystem& Sub;
	const UMyHexBridgeSettings& Settings;
	UWorld& World;

	TArray<FBridgeRecord> Recs;
	TArray<FPlat> Plats;
	TMap<int32, int32> SerialToLocal;
	TMap<FIntPoint, TArray<int32>> Cells;
	int32 CellReach = 1;

	TMap<FIntPoint, TArray<int32>> RecGrid;
	TArray<int32> Parent;

	TArray<FCand> Cands;
	int32 NumBatchCands = 0;

	/** (SerialMin, SerialMax) -> candidate, also on-demand pairs (INDEX_NONE = none). */
	TMap<TPair<int32, int32>, int32> CandIndex;

	/** Candidate of every planned record (indexed by record), for roll-backs. */
	TMap<int32, int32> RecordCand;

	/** Planned records, in plan order. */
	TArray<int32> Planned;

	/** The planned set ("new" platforms) and the platforms registered in this batch, in Serial order. */
	TArray<int32> NewPlats;
	TArray<int32> BatchNew;

	TArray<FPlayer> Players;

	/**
	 * Every trace of the batch ignores bridge actors. Their decks never block a planned deck (the
	 * crossing rules keep decks apart), but a tentative bridge that is about to be replaced would,
	 * and that failure would stay in the burst's trace cache after the bridge is gone.
	 */
	FCollisionQueryParams TraceParams;

	double TanMax = 0.0;
	double TanCurve = 0.0;
	bool bCurved = true;

	FRules Strict;
	FRules SpineRules;
	FRules Relaxed;
	FRules Optional;
	FRules Resilient;
	FRules RouteRules;
	FRules FallbackRules;

	FStats Stats;

	// Scratch
	TArray<FOption> OptionScratch;
	TArray<uint32> RecStamp;
	uint32 RecGeneration = 0;
	TArray<double> WalkDistances;
	TArray<uint32> WalkStamp;
	uint32 WalkGeneration = 0;


	FPlanner(UMyHexBridgeSubsystem& InSub, const UMyHexBridgeSettings& InSettings, UWorld& InWorld)
		: Sub(InSub)
		, Settings(InSettings)
		, World(InWorld)
	{
		using namespace HexBridgePlan;

		TanMax = FMath::Tan(FMath::DegreesToRadians(static_cast<double>(Settings.MaxSlopeDegrees)));
		TanCurve = FMath::Tan(FMath::DegreesToRadians(FMath::Max(0.0, Settings.MaxSlopeDegrees - CurveSlopeMarginDegrees)));
		bCurved = Settings.bCurvedBridges;

		SpineRules.ExtraDegree = SpineExtraDegree;

		Relaxed.Spacing = RelaxedSpacing;
		Relaxed.Spread = RelaxedSpread;
		Relaxed.bFan = false;

		Optional.bOptional = true;

		Resilient.bOptional = true;
		Resilient.ExtraDegree = ResilienceExtraDegree;

		RouteRules.Spacing = RouteSpacing;
		RouteRules.Spread = RouteSpread;
		RouteRules.ExtraDegree = ResilienceExtraDegree;
		RouteRules.bFan = false;
		RouteRules.bOptional = true;

		FallbackRules.Spacing = FallbackSpacing;
		FallbackRules.Spread = FallbackSpread;
		FallbackRules.ExtraDegree = FallbackExtraDegree;
		FallbackRules.bFan = false;
		FallbackRules.bRelaxedClearance = true;
	}


	// -------------------------------------------------------------------------
	// Small queries
	// -------------------------------------------------------------------------

	const FPlatformEntry& E(int32 P) const { return *Plats[P].Entry; }

	bool IsNew(int32 P) const { return Plats[P].NewRank != INDEX_NONE; }

	const FEdgeWorld& EdgeA(const FCand& C, const FOption& O) const { return Plats[C.A].Edges[O.EdgeA]; }
	const FEdgeWorld& EdgeB(const FCand& C, const FOption& O) const { return Plats[C.B].Edges[O.EdgeB]; }

	uint64 EdgeKeyA(const FCand& C, const FOption& O) const { return HexBridgePlan::MakeEdgeKey(E(C.A).Serial, EdgeA(C, O).Order); }
	uint64 EdgeKeyB(const FCand& C, const FOption& O) const { return HexBridgePlan::MakeEdgeKey(E(C.B).Serial, EdgeB(C, O).Order); }

	static TPair<int32, int32> PairKey(int32 SerialX, int32 SerialY)
	{
		return TPair<int32, int32>(FMath::Min(SerialX, SerialY), FMath::Max(SerialX, SerialY));
	}

	int32 Cap(int32 P) const
	{
		const int32 GridSize = E(P).GridSize;

		if (GridSize <= HexBridgePlan::SmallGridSize)
		{
			return Settings.MaxBridgesSmall;
		}

		return GridSize < HexBridgePlan::StreamMinGridSize ? Settings.MaxBridgesMedium : Settings.MaxBridgesLarge;
	}

	bool ChainsMayPair(int32 A, int32 B) const
	{
		return Settings.bAllowCrossChain || E(A).Chain == E(B).Chain;
	}

	bool InRange(int32 A, int32 B) const
	{
		const FPlatformEntry& EA = E(A);
		const FPlatformEntry& EB = E(B);
		const double Old = Settings.NeighborRadiusMultiplier * FMath::Max(EA.GridSize * EA.HexRadius, EB.GridSize * EB.HexRadius);
		return HexBridgePlan::Dist2D(EA.Location, EB.Location) <= FMath::Max(Old, static_cast<double>(EA.Footprint + EB.Footprint + Settings.MaxEdgeGap));
	}

	bool IsTileLive(int32 P, int32 TileIndex) const
	{
		return !Plats[P].bHasDeadTiles || !Plats[P].DeadTiles[TileIndex];
	}

	/** Exact 2D distance from (X, Y) to a tile's hexagon (0 inside). */
	static double HexPointDistance(const FPlatformEntry& Entry, const FTileInfo& Tile, double X, double Y)
	{
		const double DX = X - Tile.Center.X;
		const double DY = Y - Tile.Center.Y;
		const double LX = FMath::Abs(DX * Entry.YawCos + DY * Entry.YawSin);
		const double LY = FMath::Abs(-DX * Entry.YawSin + DY * Entry.YawCos);
		const double R = Entry.HexRadius;
		const double Apothem = R * HexBridgePlan::Sqrt3Half;

		if (LX <= Apothem && LX * 0.5 + LY * HexBridgePlan::Sqrt3Half <= Apothem)
		{
			return 0.0;
		}

		// Folded into the first quadrant: the flat side and the side up to the top vertex
		const FVector Sides[2][2] =
		{
			{ FVector(Apothem, -R * 0.5, 0.0), FVector(Apothem, R * 0.5, 0.0) },
			{ FVector(Apothem, R * 0.5, 0.0), FVector(0.0, R, 0.0) }
		};

		double Best = HexBridgePlan::Inf;

		for (const FVector* Side : Sides)
		{
			double T = 0.0;
			Best = FMath::Min(Best, HexBridgePlan::PointSegment(LX, LY, Side[0], Side[1], T));
		}

		return Best;
	}

	/** Exact 2D distance between segment S-End and a tile's hexagon (0 when they overlap). */
	static double HexSegmentDistance(const FPlatformEntry& Entry, const FTileInfo& Tile, const FVector& S, const FVector& End)
	{
		double Best = FMath::Min(HexPointDistance(Entry, Tile, S.X, S.Y), HexPointDistance(Entry, Tile, End.X, End.Y));

		if (Best == 0.0)
		{
			return 0.0;
		}

		for (int32 K = 0; K < 6; ++K)
		{
			const FVector2D VA = Tile.Center + Entry.HexVerts[K];
			const FVector2D VB = Tile.Center + Entry.HexVerts[(K + 1) % 6];

			double U = 0.0;
			double V = 0.0;
			const double D = HexBridgePlan::SegmentDistance2D(FVector(VA.X, VA.Y, 0.0), FVector(VB.X, VB.Y, 0.0), S, End, U, V);

			if (D < Best)
			{
				Best = D;

				if (D == 0.0)
				{
					return 0.0;
				}
			}
		}

		return Best;
	}

	/** Platforms whose cell overlaps the box (Serial order within a cell). */
	template <typename FunctorType>
	void ForEachPlatformNear(double X0, double Y0, double X1, double Y1, FunctorType&& Functor) const
	{
		const double CellSize = Settings.SpatialCellSize;

		for (int32 X = FMath::FloorToInt(X0 / CellSize); X <= FMath::FloorToInt(X1 / CellSize); ++X)
		{
			for (int32 Y = FMath::FloorToInt(Y0 / CellSize); Y <= FMath::FloorToInt(Y1 / CellSize); ++Y)
			{
				if (const TArray<int32>* List = Cells.Find(FIntPoint(X, Y)))
				{
					for (const int32 P : *List)
					{
						Functor(P);
					}
				}
			}
		}
	}


	// -------------------------------------------------------------------------
	// Live edges
	// -------------------------------------------------------------------------

	const TArray<FEdgeWorld>& LiveEdges(int32 P)
	{
		FPlat& Plat = Plats[P];

		if (!Plat.bEdgesResolved)
		{
			Plat.bEdgesResolved = true;

			const TArray<FEdgeTile>& EdgeTiles = Plat.Entry->EdgeTiles;

			for (int32 Index = 0; Index < EdgeTiles.Num(); ++Index)
			{
				if (Plat.Actor->IsTileCollapsed(EdgeTiles[Index].Tile))
				{
					continue;
				}

				FEdgeWorld Edge;

				if (GetEdgeWorld(*Plat.Actor, EdgeTiles[Index], Edge))
				{
					Edge.Order = Index;
					Plat.Edges.Add(Edge);
				}
			}
		}

		return Plat.Edges;
	}


	// -------------------------------------------------------------------------
	// Records: ends, grid, union-find
	// -------------------------------------------------------------------------

	int32 Find(int32 P)
	{
		int32 Root = P;

		while (Parent[Root] != Root)
		{
			Root = Parent[Root];
		}

		while (Parent[P] != Root)
		{
			const int32 Next = Parent[P];
			Parent[P] = Root;
			P = Next;
		}

		return Root;
	}

	void Union(int32 A, int32 B)
	{
		int32 RootA = Find(A);
		int32 RootB = Find(B);

		if (RootA != RootB)
		{
			if (RootA < RootB)
			{
				Swap(RootA, RootB);
			}

			Parent[RootA] = RootB;
		}
	}

	/** Connectivity ignores dying bridges (an end on a collapsing platform). */
	void RebuildUnionFind()
	{
		Parent.SetNumUninitialized(Plats.Num());

		for (int32 Index = 0; Index < Plats.Num(); ++Index)
		{
			Parent[Index] = Index;
		}

		for (const FBridgeRecord& Record : Recs)
		{
			if (!Record.bDying)
			{
				Union(Record.LocalA, Record.LocalB);
			}
		}
	}

	void AddEnds(int32 RecordIndex)
	{
		const FBridgeRecord& Record = Recs[RecordIndex];

		for (int32 Side = 0; Side < 2; ++Side)
		{
			const int32 P = Side == 0 ? Record.LocalA : Record.LocalB;
			const FVector& Mid = Side == 0 ? Record.MidA : Record.MidB;
			const FVector& Center = E(P).Location;

			FEnd& End = Plats[P].Ends.AddDefaulted_GetRef();
			End.Record = RecordIndex;
			End.EdgeKey = HexBridgePlan::MakeEdgeKey(Side == 0 ? Record.SerialA : Record.SerialB, Side == 0 ? Record.OrderA : Record.OrderB);
			End.Point = Mid;
			End.Angle = FMath::Atan2(Mid.Y - Center.Y, Mid.X - Center.X);
			End.Dir = Side == 0 ? Record.DirA : Record.DirB;
		}
	}

	template <typename FunctorType>
	void ForEachRecordCell(const FBox2D& Box, FunctorType&& Functor) const
	{
		const double CellSize = HexBridgePlan::RecordCellSize;

		for (int32 X = FMath::FloorToInt(Box.Min.X / CellSize); X <= FMath::FloorToInt(Box.Max.X / CellSize); ++X)
		{
			for (int32 Y = FMath::FloorToInt(Box.Min.Y / CellSize); Y <= FMath::FloorToInt(Box.Max.Y / CellSize); ++Y)
			{
				Functor(FIntPoint(X, Y));
			}
		}
	}

	void IndexRecord(int32 RecordIndex)
	{
		ForEachRecordCell(Recs[RecordIndex].Bounds, [this, RecordIndex](const FIntPoint& Cell)
		{
			RecGrid.FindOrAdd(Cell).Add(RecordIndex);
		});
	}

	/** Records whose grid cells overlap the box, each once. */
	void RecordsNear(const FBox2D& Box, TArray<int32, TInlineAllocator<64>>& Out)
	{
		Out.Reset();

		if (RecStamp.Num() < Recs.Num())
		{
			RecStamp.SetNumZeroed(Recs.Num());
		}

		if (++RecGeneration == 0)
		{
			FMemory::Memzero(RecStamp.GetData(), RecStamp.Num() * sizeof(uint32));
			RecGeneration = 1;
		}

		ForEachRecordCell(Box, [this, &Out](const FIntPoint& Cell)
		{
			if (const TArray<int32>* List = RecGrid.Find(Cell))
			{
				for (const int32 RecordIndex : *List)
				{
					if (RecStamp[RecordIndex] != RecGeneration)
					{
						RecStamp[RecordIndex] = RecGeneration;
						Out.Add(RecordIndex);
					}
				}
			}
		});
	}

	/** Ends, record grid and union-find from the live records. */
	void RebuildState()
	{
		RecGrid.Reset();

		for (FPlat& Plat : Plats)
		{
			Plat.Ends.Reset();
		}

		for (int32 RecordIndex = 0; RecordIndex < Recs.Num(); ++RecordIndex)
		{
			IndexRecord(RecordIndex);
			AddEnds(RecordIndex);
		}

		RebuildUnionFind();
	}

	bool Linked(int32 A, int32 B) const
	{
		for (const FEnd& End : Plats[A].Ends)
		{
			const FBridgeRecord& Record = Recs[End.Record];

			if (Record.LocalA == B || Record.LocalB == B)
			{
				return true;
			}
		}

		return false;
	}


	// -------------------------------------------------------------------------
	// Players (the guard on re-planned and revalidated bridges)
	// -------------------------------------------------------------------------

	void GatherPlayers()
	{
		for (FConstPlayerControllerIterator It = World.GetPlayerControllerIterator(); It; ++It)
		{
			const APlayerController* PlayerController = It->Get();
			const APawn* Pawn = PlayerController ? PlayerController->GetPawn() : nullptr;

			if (Pawn)
			{
				Players.Add({ APawn::GetMovementBaseActor(Pawn), Pawn->GetActorLocation() });
			}
		}
	}

	/** A player uses the bridge as movement base or is within BridgeKeepDistance (2D) of its deck. */
	bool IsPlayerNear(const FBridgeRecord& Record) const
	{
		if (Players.Num() == 0)
		{
			return false;
		}

		const AMyHexBridge* Bridge = Record.Bridge.Get();
		double KeepDistance = 0.0;

		for (const int32 P : { Record.LocalA, Record.LocalB })
		{
			KeepDistance = FMath::Max(KeepDistance, static_cast<double>(GetBridgeKeepDistance(*Plats[P].Actor)));
		}

		for (const FPlayer& Player : Players)
		{
			if (Bridge && Player.Base == Bridge)
			{
				return true;
			}

			for (int32 Index = 0; Index + 1 < Record.Deck.Num(); ++Index)
			{
				double T = 0.0;

				if (HexBridgePlan::PointSegment(Player.Location.X, Player.Location.Y, Record.Deck[Index], Record.Deck[Index + 1], T) <= KeepDistance)
				{
					return true;
				}
			}
		}

		return false;
	}


	// -------------------------------------------------------------------------
	// Candidates and options (pure geometry, no traces)
	// -------------------------------------------------------------------------

	/** Live edges of P facing O, nearest first (score = distance, more for edges facing it less). */
	void FacingEdges(int32 P, int32 O, int32 MaxEdges, TArray<int32, TInlineAllocator<24>>& Out)
	{
		struct FScored
		{
			double Score;
			int32 Order;
			int32 Index;
		};

		const TArray<FEdgeWorld>& Edges = LiveEdges(P);
		const FVector& Other = E(O).Location;

		TArray<FScored, TInlineAllocator<64>> Scored;

		for (int32 Index = 0; Index < Edges.Num(); ++Index)
		{
			const FEdgeWorld& Edge = Edges[Index];
			const double TX = Other.X - Edge.Mid.X;
			const double TY = Other.Y - Edge.Mid.Y;
			const double D = FMath::Sqrt(TX * TX + TY * TY);

			if (D < 1e-6)
			{
				continue;
			}

			const double Facing = (Edge.Normal2D.X * TX + Edge.Normal2D.Y * TY) / D;

			if (Facing < HexBridgePlan::FacingDot)
			{
				continue;
			}

			Scored.Add({ D * (1.0 + 0.5 * (1.0 - Facing)), Edge.Order, Index });
		}

		Scored.StableSort([](const FScored& Left, const FScored& Right)
		{
			return Left.Score != Right.Score ? Left.Score < Right.Score : Left.Order < Right.Order;
		});

		Out.Reset();

		for (int32 Index = 0; Index < Scored.Num() && Index < MaxEdges; ++Index)
		{
			Out.Add(Scored[Index].Index);
		}
	}

	/** The options of a pair. First = the platform with the higher Serial (bridge start). False if none. */
	bool MakeCandidate(int32 First, int32 Second, bool bWide, double MaxLength, FCand& Out)
	{
		using namespace HexBridgePlan;

		const int32 Widen = bWide ? WideFactor : 1;

		TArray<int32, TInlineAllocator<24>> FacingA;
		TArray<int32, TInlineAllocator<24>> FacingB;
		FacingEdges(First, Second, CandidateEdges * Widen, FacingA);
		FacingEdges(Second, First, CandidateEdges * Widen, FacingB);

		if (FacingA.Num() == 0 || FacingB.Num() == 0)
		{
			return false;
		}

		const TArray<FEdgeWorld>& EdgesA = Plats[First].Edges;
		const TArray<FEdgeWorld>& EdgesB = Plats[Second].Edges;

		const double EndLimit = bCurved ? Settings.MaxEndAngleDegrees : Settings.StraightOnlyMaxEndAngleDegrees;
		const double MaxTurn = FMath::DegreesToRadians(EndLimit + (bWide ? WideEndAngleDegrees : 0.0));
		const double Skew = FMath::DegreesToRadians(SkewAllowanceDegrees);

		OptionScratch.Reset();

		for (const int32 IndexA : FacingA)
		{
			const FEdgeWorld& EA = EdgesA[IndexA];

			for (const int32 IndexB : FacingB)
			{
				const FEdgeWorld& EB = EdgesB[IndexB];

				const double DX = EB.Mid.X - EA.Mid.X;
				const double DY = EB.Mid.Y - EA.Mid.Y;
				const double DZ = EB.Mid.Z - EA.Mid.Z;
				const double L2 = FMath::Sqrt(DX * DX + DY * DY);

				if (L2 < MinOptionLength || FMath::Abs(DZ) > TanMax * L2)
				{
					continue;
				}

				const double L3 = FMath::Sqrt(L2 * L2 + DZ * DZ);

				if (L3 > MaxLength)
				{
					continue;
				}

				const FVector2D U(DX / L2, DY / L2);
				const FVector2D NA = EA.Normal2D;
				const FVector2D NB = -EB.Normal2D;

				// Signed angles between the chord and each side's normal (B's flipped to point along the chord)
				const double ThetaA = FMath::Atan2(U.X * NA.Y - U.Y * NA.X, NA.X * U.X + NA.Y * U.Y);
				const double ThetaB = FMath::Atan2(U.X * NB.Y - U.Y * NB.X, NB.X * U.X + NB.Y * U.Y);

				if (FMath::Abs(ThetaA) > MaxTurn || FMath::Abs(ThetaB) > MaxTurn)
				{
					continue;
				}

				// A curved deck bends through all but SkewAllowance of the end angle
				const double BendA = bCurved ? FMath::Max(0.0, FMath::Abs(ThetaA) - Skew) : 0.0;
				const double BendB = bCurved ? FMath::Max(0.0, FMath::Abs(ThetaB) - Skew) : 0.0;
				const double PhiA = ThetaA < 0.0 ? -BendA : BendA;
				const double PhiB = ThetaB < 0.0 ? -BendB : BendB;
				const double SkewA = ThetaA - PhiA;
				const double SkewB = ThetaB - PhiB;
				const double Slope = DZ / L2;

				FOption& Option = OptionScratch.AddDefaulted_GetRef();
				Option.EdgeA = IndexA;
				Option.EdgeB = IndexB;
				Option.L2 = L2;
				Option.L3 = L3;
				Option.ThetaA = ThetaA;
				Option.ThetaB = ThetaB;
				Option.PhiA = PhiA;
				Option.PhiB = PhiB;
				Option.DirA = Rotate2D(U, PhiA);
				Option.DirB = -Rotate2D(U, PhiB);
				Option.Cost = L3 * (1.0
					+ TurnPenalty * (PhiA * PhiA + PhiB * PhiB)
					+ SkewPenalty * (SkewA * SkewA + SkewB * SkewB)
					+ ArcPenalty * FMath::Square(PhiB - PhiA)
					+ SlopePenalty * Slope * Slope);
			}
		}

		if (OptionScratch.Num() == 0)
		{
			return false;
		}

		OptionScratch.StableSort([&EdgesA, &EdgesB](const FOption& Left, const FOption& Right)
		{
			if (Left.Cost != Right.Cost)
			{
				return Left.Cost < Right.Cost;
			}

			const int32 OrderA = EdgesA[Left.EdgeA].Order;
			const int32 OtherOrderA = EdgesA[Right.EdgeA].Order;

			return OrderA != OtherOrderA ? OrderA < OtherOrderA : EdgesB[Left.EdgeB].Order < EdgesB[Right.EdgeB].Order;
		});

		const int32 Keep = MaxOptions * Widen;

		Out = FCand();
		Out.A = First;
		Out.B = Second;
		Out.SerialMin = FMath::Min(E(First).Serial, E(Second).Serial);
		Out.SerialMax = FMath::Max(E(First).Serial, E(Second).Serial);
		Out.Jump = FMath::Abs(E(First).SplineDistance - E(Second).SplineDistance);

		if (!bWide)
		{
			// At most OptionsPerEndTile per end tile (per end side on islets), so the options spread
			TArray<TPair<int64, int32>, TInlineAllocator<16>> CountA;
			TArray<TPair<int64, int32>, TInlineAllocator<16>> CountB;

			auto EndKey = [](const FEdgeWorld& Edge, bool bIslet) -> int64
			{
				return static_cast<int64>(bIslet
					? ((uint64(1) << 62) | static_cast<uint32>(Edge.Order))
					: ((static_cast<uint64>(static_cast<uint32>(Edge.Tile.X)) << 32) | static_cast<uint32>(Edge.Tile.Y)));
			};

			auto Count = [](TArray<TPair<int64, int32>, TInlineAllocator<16>>& Counts, int64 Key) -> int32&
			{
				for (TPair<int64, int32>& Pair : Counts)
				{
					if (Pair.Key == Key)
					{
						return Pair.Value;
					}
				}

				return Counts.Emplace_GetRef(Key, 0).Value;
			};

			for (FOption& Option : OptionScratch)
			{
				int32& UsedA = Count(CountA, EndKey(EdgesA[Option.EdgeA], E(First).bIslet));
				int32& UsedB = Count(CountB, EndKey(EdgesB[Option.EdgeB], E(Second).bIslet));

				if (UsedA >= OptionsPerEndTile || UsedB >= OptionsPerEndTile)
				{
					continue;
				}

				++UsedA;
				++UsedB;
				Out.Options.Add(MoveTemp(Option));

				if (Out.Options.Num() >= Keep)
				{
					break;
				}
			}
		}
		else
		{
			for (int32 Index = 0; Index < OptionScratch.Num() && Index < Keep; ++Index)
			{
				Out.Options.Add(MoveTemp(OptionScratch[Index]));
			}
		}

		return Out.Options.Num() > 0;
	}

	/** This batch's candidate for A-B, else one made on demand (cached per batch), else INDEX_NONE. */
	int32 CandBetween(int32 A, int32 B)
	{
		const TPair<int32, int32> Key = PairKey(E(A).Serial, E(B).Serial);

		if (const int32* Found = CandIndex.Find(Key))
		{
			return *Found;
		}

		int32 Result = INDEX_NONE;

		if (!Plats[A].bCollapsing && !Plats[B].bCollapsing && ChainsMayPair(A, B) && InRange(A, B))
		{
			const bool bAFirst = E(A).Serial > E(B).Serial;
			FCand Cand;

			if (MakeCandidate(bAFirst ? A : B, bAFirst ? B : A, /*bWide=*/false, Settings.MaxBridgeLength, Cand))
			{
				Result = Cands.Add(MoveTemp(Cand));
			}
		}

		CandIndex.Add(Key, Result);
		return Result;
	}


	// -------------------------------------------------------------------------
	// Deck
	// -------------------------------------------------------------------------

	static void MakeStraightDeck(const FVector& P0, const FVector& P1, double L3, FDeck& Out)
	{
		Out = FDeck();
		Out.Coarse.Add(P0);
		Out.Coarse.Add(P1);
		Out.Arc = L3;
		Out.Bounds = HexBridgePlan::PolyBounds(Out.Coarse);
	}

	/**
	 * Deck from P0 to P1 that leaves along rot(chord, PhiA) and arrives along rot(chord, PhiB): one
	 * cubic Hermite segment. False when the curve is too tight, bulges too far or gets too steep.
	 */
	bool BuildDeck(const FVector& P0, const FVector& P1, double L2, double L3, double PhiA, double PhiB, FDeck& Out) const
	{
		using namespace HexBridgePlan;

		const double DZ = P1.Z - P0.Z;
		const FVector2D U((P1.X - P0.X) / L2, (P1.Y - P0.Y) / L2);
		const bool bPlanStraight = PhiA == 0.0 && PhiB == 0.0;
		const double SagHigh = FMath::Min(SagMax, SagRatio * L2);

		if (bPlanStraight && SagHigh <= 0.0)
		{
			MakeStraightDeck(P0, P1, L3, Out);
			return true;
		}

		const double M = TangentScale * L2;
		const FVector2D TA = Rotate2D(U, PhiA) * M;
		const FVector2D TB = Rotate2D(U, PhiB) * M;
		const FVector2D Q0(P0.X, P0.Y);
		const FVector2D Q1(P1.X, P1.Y);

		// (t, plan speed) samples for the slope rule
		TArray<TPair<double, double>, TInlineAllocator<DeckSamples + 1>> Speeds;
		double Lateral = 0.0;

		if (bPlanStraight)
		{
			for (int32 Index = 0; Index <= 8; ++Index)
			{
				Speeds.Emplace(Index / 8.0, M);
			}
		}
		else
		{
			double MaxCurvature = 0.0;

			for (int32 Index = 0; Index <= DeckSamples; ++Index)
			{
				const double T = static_cast<double>(Index) / DeckSamples;
				const FVector2D Velocity = HermiteVelocity2D(Q0, TA, Q1, TB, T);
				const FVector2D Acceleration = HermiteAcceleration2D(Q0, TA, Q1, TB, T);
				const double Speed = Velocity.Size();

				if (Speed < 1e-6)
				{
					return false;
				}

				Speeds.Emplace(T, Speed);
				MaxCurvature = FMath::Max(MaxCurvature, FMath::Abs(Velocity.X * Acceleration.Y - Velocity.Y * Acceleration.X) / (Speed * Speed * Speed));

				const FVector2D Point = HermitePoint2D(Q0, TA, Q1, TB, T);
				Lateral = FMath::Max(Lateral, FMath::Abs((Point.X - Q0.X) * U.Y - (Point.Y - Q0.Y) * U.X));
			}

			const double MinRadius = MaxCurvature > 1e-12 ? 1.0 / MaxCurvature : Inf;

			if (MinRadius < MinTurnRadius || Lateral > MaxLateralDeviation)
			{
				return false;
			}
		}

		// Elevation z(t) = z0 + dz t - 4 S t (1 - t), so z'(t) = dz + S (8 t - 4): keep |z'| / |xy'| <= tan(slope)
		const double TanLimit = bPlanStraight ? TanMax : TanCurve;
		double SagLow = 0.0;
		double SagHighest = SagHigh;

		for (const TPair<double, double>& Sample : Speeds)
		{
			const double Allowed = TanLimit * Sample.Value;
			const double C = 8.0 * Sample.Key - 4.0;

			if (FMath::Abs(C) < 1e-9)
			{
				if (FMath::Abs(DZ) > Allowed)
				{
					return false;
				}

				continue;
			}

			const double A1 = (Allowed - DZ) / C;
			const double A2 = (-Allowed - DZ) / C;
			SagLow = FMath::Max(SagLow, C > 0.0 ? A2 : A1);
			SagHighest = FMath::Min(SagHighest, C > 0.0 ? A1 : A2);
		}

		if (SagLow > SagHighest + 1e-9)
		{
			return false;
		}

		const double Sag = FMath::Max(0.0, SagHighest);

		if (bPlanStraight && Sag < 1.0)
		{
			MakeStraightDeck(P0, P1, L3, Out);
			return true;
		}

		Out = FDeck();
		Out.bCurved = true;
		Out.T0 = FVector(TA.X, TA.Y, DZ - 4.0 * Sag);
		Out.T1 = FVector(TB.X, TB.Y, DZ + 4.0 * Sag);

		FVector Previous = P0;

		for (int32 Index = 1; Index <= DeckSamples; ++Index)
		{
			const FVector Point = HermitePoint(P0, Out.T0, P1, Out.T1, static_cast<double>(Index) / DeckSamples);
			Out.Arc += FVector::Dist(Previous, Point);
			Previous = Point;
		}

		if (Lateral <= StraightLateralTol && Sag <= StraightSagTol)
		{
			Out.Coarse.Add(P0);
			Out.Coarse.Add(P1);
		}
		else
		{
			const int32 NumCoarse = FMath::Max(2, FMath::CeilToInt(Out.Arc / CoarseStep));

			for (int32 Index = 0; Index <= NumCoarse; ++Index)
			{
				Out.Coarse.Add(HermitePoint(P0, Out.T0, P1, Out.T1, static_cast<double>(Index) / NumCoarse));
			}

			const int32 NumTraces = FMath::Clamp(FMath::CeilToInt(Out.Arc / TraceSegmentLength), MinTraceSegments, MaxTraceSegments);

			for (int32 Index = 0; Index <= NumTraces; ++Index)
			{
				Out.TracePoints.Add(HermitePoint(P0, Out.T0, P1, Out.T1, static_cast<double>(Index) / NumTraces));
			}
		}

		Out.Bounds = PolyBounds(Out.Coarse);
		return true;
	}

	/** The option's deck (built once). Also fixes DirA / DirB to the deck's real end directions. */
	bool DeckOf(const FCand& C, FOption& O) const
	{
		using namespace HexBridgePlan;

		if (O.DeckState < 0)
		{
			const FVector& MidA = EdgeA(C, O).Mid;
			const FVector& MidB = EdgeB(C, O).Mid;

			const double StraightLimit = FMath::DegreesToRadians(bCurved ? Settings.MaxStraightEndAngleDegrees : Settings.StraightOnlyMaxEndAngleDegrees);
			const bool bSquareEnough = FMath::Max(FMath::Abs(O.ThetaA), FMath::Abs(O.ThetaB)) <= StraightLimit;

			bool bValid = false;

			if ((O.PhiA != 0.0 || O.PhiB != 0.0) && O.L2 < MinCurvedLength)
			{
				// Too short to bend: only a nearly square-on straight deck will do
				bValid = bSquareEnough && BuildDeck(MidA, MidB, O.L2, O.L3, 0.0, 0.0, O.Deck);
			}
			else
			{
				bValid = BuildDeck(MidA, MidB, O.L2, O.L3, O.PhiA, O.PhiB, O.Deck);

				if (!bValid && bSquareEnough)
				{
					bValid = BuildDeck(MidA, MidB, O.L2, O.L3, 0.0, 0.0, O.Deck);
				}
			}

			if (bValid && !O.Deck.bCurved)
			{
				const FVector2D U((MidB.X - MidA.X) / O.L2, (MidB.Y - MidA.Y) / O.L2);
				O.DirA = U;
				O.DirB = -U;
			}

			O.DeckState = bValid ? 1 : 0;
		}

		return O.DeckState == 1;
	}


	// -------------------------------------------------------------------------
	// Checks (deck, ends, crossings, clearance; traces last)
	// -------------------------------------------------------------------------

	/** End rules for a new end on P at Edge, the deck leaving along Dir. */
	EFail EndConflict(int32 P, const FEdgeWorld& Edge, uint64 EdgeKey, const FVector2D& Dir, const FRules& Rules) const
	{
		using namespace HexBridgePlan;

		const FPlat& Plat = Plats[P];
		const FPlatformEntry& Entry = *Plat.Entry;

		if (Plat.Ends.Num() >= FMath::Min(Cap(P) + Rules.ExtraDegree, Settings.MaxBridgesLarge))
		{
			return EFail::Cap;
		}

		const double R = Entry.HexRadius;
		const double Spacing = Settings.MinEndSpacingRadii * Rules.Spacing * R;
		const double StepDistance = StepSpacing * R;
		const double CosStep = FMath::Cos(FMath::DegreesToRadians(StepDivergeDegrees));
		const double Spread = FMath::DegreesToRadians(Settings.MinBridgeSpreadDegrees * Rules.Spread);
		const double FarDistance = SpreadFarSpacing * R;
		const double CosFar = FMath::Cos(FMath::DegreesToRadians(SpreadFarDivergeDegrees));
		const double CosFan = Rules.bFan ? FMath::Cos(FMath::DegreesToRadians(FanDegrees)) : 2.0;
		const double Angle = FMath::Atan2(Edge.Mid.Y - Entry.Location.Y, Edge.Mid.X - Entry.Location.X);

		for (const FEnd& End : Plat.Ends)
		{
			if (End.EdgeKey == EdgeKey)
			{
				return EFail::SameSide;
			}

			const double DD = Dist2D(End.Point, Edge.Mid);
			const double CD = FVector2D::DotProduct(Dir, End.Dir);

			// An islet may be a stepping stone: two close ends whose bridges leave far apart
			const bool bStep = Entry.bIslet && DD >= StepDistance && CD <= CosStep;

			if (DD < Spacing && !bStep)
			{
				return EFail::Spacing;
			}

			if (WrapAngleDistance(Angle, End.Angle) < Spread && !bStep && !(DD >= FarDistance && CD <= CosFar))
			{
				return EFail::Spread;
			}

			if (CD > CosFan && DD < FanDistance)
			{
				return EFail::Fan;
			}
		}

		return EFail::None;
	}

	/** Would the deck (A -> B) cross or run alongside a live or planned deck? */
	bool CrossConflict(int32 A, int32 B, TConstArrayView<FVector> Poly, const FBox2D& Bounds, const FRules& Rules)
	{
		using namespace HexBridgePlan;

		const double Separation = Settings.BridgeSeparation;
		const double SameSeparation = Settings.SameChainSeparation;
		const double VerticalClearance = Settings.MinBridgeVerticalClearance;
		const double Pad = FMath::Max3(Separation, SameSeparation, OtherChainOptionalGap);
		const FBox2D Box(Bounds.Min - FVector2D(Pad, Pad), Bounds.Max + FVector2D(Pad, Pad));
		const uint8 Chain = E(A).Chain;

		TArray<int32, TInlineAllocator<64>> Near;
		RecordsNear(Box, Near);

		TArray<FVector2D, TInlineAllocator<8>> Hits;
		FPolyline TrimmedNew;
		FPolyline TrimmedOld;

		for (const int32 RecordIndex : Near)
		{
			const FBridgeRecord& Record = Recs[RecordIndex];

			if (Record.Bounds.Max.X < Box.Min.X || Record.Bounds.Min.X > Box.Max.X || Record.Bounds.Max.Y < Box.Min.Y || Record.Bounds.Min.Y > Box.Max.Y)
			{
				continue;
			}

			bool bBad = false;
			double ZNew = 0.0;
			double ZOld = 0.0;

			if (Record.LocalA == A || Record.LocalA == B || Record.LocalB == A || Record.LocalB == B)
			{
				// Sharing a platform: they may meet at the shared end, but not cross or run alongside
				const int32 Shared = (Record.LocalA == A || Record.LocalA == B) ? Record.LocalA : Record.LocalB;
				const FVector& EndNew = Shared == A ? Poly[0] : Poly.Last();
				const FVector& EndOld = Record.LocalA == Shared ? Record.Deck[0] : Record.Deck.Last();

				PolyIntersections(Poly, Record.Deck, Hits);

				for (const FVector2D& Hit : Hits)
				{
					if (FVector2D::Distance(Hit, FVector2D(EndNew.X, EndNew.Y)) > SharedEndTolerance
						&& FVector2D::Distance(Hit, FVector2D(EndOld.X, EndOld.Y)) > SharedEndTolerance)
					{
						bBad = true;
						break;
					}
				}

				if (!bBad)
				{
					PolyTrim(Poly, Shared == A, SharedTrim, TrimmedNew);
					PolyTrim(Record.Deck, Record.LocalA == Shared, SharedTrim, TrimmedOld);

					const double D = PolyDistance(TrimmedNew, TrimmedOld, ZNew, ZOld);
					bBad = D < Separation && FMath::Abs(ZNew - ZOld) < VerticalClearance;
				}
			}
			else
			{
				const double D = PolyDistance(Poly, Record.Deck, ZNew, ZOld);

				if (Record.Chain == Chain)
				{
					// No overpasses within a chain
					bBad = D < SameSeparation;
				}
				else if (Rules.bOptional && D < OtherChainOptionalGap)
				{
					bBad = true;
				}

				if (!bBad)
				{
					bBad = D < Separation && FMath::Abs(ZNew - ZOld) < VerticalClearance;
				}
			}

			if (bBad)
			{
				return true;
			}
		}

		return false;
	}

	/**
	 * No live tile of a third platform (any chain) within Clearance (exact hexagon distance, 2D) of the
	 * deck while the deck is in the tile's pillar band. Only = test only these platforms.
	 */
	bool ClearOfPlatforms(int32 A, int32 B, TConstArrayView<FVector> Poly, const FBox2D& Bounds, double Clearance, const TArray<int32>* Only) const
	{
		using namespace HexBridgePlan;

		const double Reach = Sub.MaxFootprint + Clearance;

		double ZLow = Inf;
		double ZHigh = -Inf;

		for (const FVector& Point : Poly)
		{
			ZLow = FMath::Min(ZLow, Point.Z);
			ZHigh = FMath::Max(ZHigh, Point.Z);
		}

		bool bClear = true;

		ForEachPlatformNear(Bounds.Min.X - Reach, Bounds.Min.Y - Reach, Bounds.Max.X + Reach, Bounds.Max.Y + Reach, [&](int32 C)
		{
			if (!bClear || C == A || C == B || (Only && !Only->Contains(C)))
			{
				return;
			}

			const FPlatformEntry& Entry = E(C);

			// Footprint prefilter
			double MinDistance = Inf;

			for (int32 Index = 0; Index + 1 < Poly.Num(); ++Index)
			{
				double T = 0.0;
				MinDistance = FMath::Min(MinDistance, PointSegment(Entry.Location.X, Entry.Location.Y, Poly[Index], Poly[Index + 1], T));
			}

			if (MinDistance > Entry.Footprint + Clearance)
			{
				return;
			}

			const double Limit = Entry.HexRadius + Clearance;

			for (int32 TileIndex = 0; TileIndex < Entry.Tiles.Num() && bClear; ++TileIndex)
			{
				if (!IsTileLive(C, TileIndex))
				{
					continue;
				}

				const FTileInfo& Tile = Entry.Tiles[TileIndex];
				const double Low = Tile.Bottom - PillarHeadroom;
				const double High = Tile.Top + ClearanceAbove;

				if (ZHigh < Low || ZLow > High)
				{
					continue;
				}

				for (int32 Index = 0; Index + 1 < Poly.Num(); ++Index)
				{
					const FVector& S = Poly[Index];
					const FVector& End = Poly[Index + 1];

					double T = 0.0;

					if (PointSegment(Tile.Center.X, Tile.Center.Y, S, End, T) >= Limit)
					{
						continue;
					}

					if (HexSegmentDistance(Entry, Tile, S, End) >= Clearance)
					{
						continue;
					}

					const double Z = S.Z + (End.Z - S.Z) * T;

					if (Z >= Low && Z <= High)
					{
						bClear = false;
						break;
					}
				}
			}
		});

		return bClear;
	}

	/**
	 * The deck, Skip from each end, keeps Clearance (2D) from the other tiles of its own two platforms
	 * near deck height (a deck grazing the pillar next to its edge looks clipped).
	 */
	bool OwnClear(const FCand& C, const FOption& O, TConstArrayView<FVector> Poly, double Clearance, double Skip) const
	{
		using namespace HexBridgePlan;

		if (Clearance <= 0.0)
		{
			return true;
		}

		FPolyline Half;
		FPolyline Trimmed;
		PolyTrim(Poly, true, Skip, Half);
		PolyTrim(Half, false, Skip, Trimmed);

		if (Trimmed.Num() < 2 || PolyLength2D(Trimmed) < 1.0)
		{
			return true;
		}

		const FBox2D Box = PolyBounds(Trimmed);

		for (int32 Side = 0; Side < 2; ++Side)
		{
			const int32 P = Side == 0 ? C.A : C.B;
			const FIntVector& OwnTile = Side == 0 ? EdgeA(C, O).Tile : EdgeB(C, O).Tile;
			const FPlatformEntry& Entry = E(P);
			const double Reach = Entry.HexRadius + Clearance;

			for (int32 TileIndex = 0; TileIndex < Entry.Tiles.Num(); ++TileIndex)
			{
				const FTileInfo& Tile = Entry.Tiles[TileIndex];

				if (Tile.Coord == OwnTile
					|| Tile.Center.X < Box.Min.X - Reach || Tile.Center.X > Box.Max.X + Reach
					|| Tile.Center.Y < Box.Min.Y - Reach || Tile.Center.Y > Box.Max.Y + Reach
					|| !IsTileLive(P, TileIndex))
				{
					continue;
				}

				for (int32 Index = 0; Index + 1 < Trimmed.Num(); ++Index)
				{
					double T = 0.0;

					if (PointSegment(Tile.Center.X, Tile.Center.Y, Trimmed[Index], Trimmed[Index + 1], T) > Reach)
					{
						continue;
					}

					const double Z = Trimmed[Index].Z + (Trimmed[Index + 1].Z - Trimmed[Index].Z) * T;

					if (FMath::Abs(Z - Tile.Top) > OwnHeightBand)
					{
						continue;
					}

					if (HexSegmentDistance(Entry, Tile, Trimmed[Index], Trimmed[Index + 1]) < Clearance)
					{
						return false;
					}
				}
			}
		}

		return true;
	}

	/** Clearance from third platforms and from the own platforms' other tiles (cached per option). */
	bool ClearOk(const FCand& C, FOption& O, const FRules& Rules) const
	{
		using namespace HexBridgePlan;

		const int32 Slot = Rules.bRelaxedClearance ? 1 : 0;

		if (O.Clear[Slot] < 0)
		{
			const double Clearance = Rules.bRelaxedClearance ? RelaxedClearance : static_cast<double>(Settings.PlatformClearance);
			bool bClear = ClearOfPlatforms(C.A, C.B, O.Deck.Coarse, O.Deck.Bounds, Clearance, nullptr);

			if (bClear)
			{
				const bool bCurvedDeck = O.Deck.bCurved;
				bClear = OwnClear(C, O, O.Deck.Coarse, bCurvedDeck ? CurvedOwnClearance : OwnClearance, bCurvedDeck ? CurvedOwnSkip : OwnSkip);
			}

			O.Clear[Slot] = bClear ? 1 : 0;
		}

		return O.Clear[Slot] == 1;
	}

	/** The first geometric rule option Oi of candidate Ci fails under Rules (EFail::None = passes). */
	EFail GeometryOk(int32 Ci, int32 Oi, const FRules& Rules)
	{
		const FCand& C = Cands[Ci];
		FOption& O = Cands[Ci].Options[Oi];

		if (!DeckOf(C, O))
		{
			return EFail::Deck;
		}

		EFail Why = EndConflict(C.A, EdgeA(C, O), EdgeKeyA(C, O), O.DirA, Rules);

		if (Why == EFail::None)
		{
			Why = EndConflict(C.B, EdgeB(C, O), EdgeKeyB(C, O), O.DirB, Rules);
		}

		if (Why != EFail::None)
		{
			return Why;
		}

		if (CrossConflict(C.A, C.B, O.Deck.Coarse, O.Deck.Bounds, Rules))
		{
			return EFail::Cross;
		}

		return ClearOk(C, O, Rules) ? EFail::None : EFail::Clearance;
	}


	// -------------------------------------------------------------------------
	// Traces (only after every geometric check passed; cached for the burst)
	// -------------------------------------------------------------------------

	bool HitReaches(const FHitResult& Hit, bool bHit, int32 Target, const FEdgeWorld& Edge) const
	{
		if (!bHit || Hit.GetActor() != Plats[Target].Actor)
		{
			return false;
		}

		const FVector Expected = Edge.Mid - Edge.Up * HexBridgeSubsystemTrace::BridgeTraceDepth;
		return FVector::DistSquared(Hit.ImpactPoint, Expected) <= FMath::Square(E(Target).HexRadius * HexBridgeSubsystemTrace::BridgeTraceTolerance);
	}

	bool LineHits(const FVector& Start, const FVector& End, FHitResult& OutHit)
	{
		++Stats.Traces;

		const bool bHit = World.LineTraceSingleByChannel(OutHit, Start, End, Settings.TraceChannel, TraceParams);

		if (Settings.bDrawDebug)
		{
			DrawDebugLine(&World, Start, End, bHit ? FColor::Orange : FColor::Cyan, false, 10.f, 0, 3.f);
		}

		return bHit;
	}

	/**
	 * Curved deck: lines just under the deck, S -> Q1 -> ... -> Q(n-1), hit nothing; Q(n-1) -> inside
	 * B's side first hits B at that side; Q1 -> inside A's side first hits A at that side.
	 */
	bool CurvedTraces(const FCand& C, const FOption& O)
	{
		using namespace HexBridgeSubsystemTrace;

		const FEdgeWorld& EA = EdgeA(C, O);
		const FEdgeWorld& EB = EdgeB(C, O);
		const TArray<FVector>& Points = O.Deck.TracePoints;
		const int32 N = Points.Num() - 1;

		const FVector DirA(O.DirA.X, O.DirA.Y, 0.0);
		const FVector DirB(O.DirB.X, O.DirB.Y, 0.0);
		const FVector Down = EA.Up * BridgeTraceDepth;

		TArray<FVector, TInlineAllocator<MaxTraceSegmentsPlusOne>> Line;
		Line.Add(EA.Mid + DirA * BridgeTraceStartOffset - Down);

		for (int32 Index = 1; Index < N; ++Index)
		{
			Line.Add(Points[Index] - Down);
		}

		Line.Add(EB.Mid - DirB * BridgeTraceOvershoot - EB.Up * BridgeTraceDepth);

		FHitResult Hit;

		for (int32 Index = 0; Index + 1 < N; ++Index)
		{
			if (LineHits(Line[Index], Line[Index + 1], Hit))
			{
				return false;
			}
		}

		bool bHit = LineHits(Line[N - 1], Line[N], Hit);

		if (!HitReaches(Hit, bHit, C.B, EB))
		{
			return false;
		}

		bHit = LineHits(Line[1], EA.Mid - DirA * BridgeTraceOvershoot - Down, Hit);
		return HitReaches(Hit, bHit, C.A, EA);
	}

	static constexpr int32 MaxTraceSegmentsPlusOne = HexBridgePlan::MaxTraceSegments + 1;

	bool TraceOk(int32 Ci, int32 Oi)
	{
		const FCand& C = Cands[Ci];
		FOption& O = Cands[Ci].Options[Oi];

		if (O.Traced < 0)
		{
			const TPair<uint64, uint64> Key(EdgeKeyA(C, O), EdgeKeyB(C, O));

			if (const bool* Cached = Sub.TraceCache.Find(Key))
			{
				++Stats.TraceCacheHits;
				O.Traced = *Cached ? 1 : 0;
				return *Cached;
			}

			bool bReaches = false;

			if (O.DeckState != 1 || O.Deck.TracePoints.Num() < 3)
			{
				// Straight or nearly straight: both ways, as the original
				++Stats.Traces;
				bReaches = Sub.TraceReaches(EdgeA(C, O), EdgeB(C, O), *Plats[C.B].Actor, Settings, &TraceParams);

				if (bReaches)
				{
					++Stats.Traces;
					bReaches = Sub.TraceReaches(EdgeB(C, O), EdgeA(C, O), *Plats[C.A].Actor, Settings, &TraceParams);
				}
			}
			else
			{
				bReaches = CurvedTraces(C, O);
			}

			O.Traced = bReaches ? 1 : 0;
			Sub.TraceCache.Add(Key, bReaches);
		}

		return O.Traced == 1;
	}


	// -------------------------------------------------------------------------
	// Natural-neighbour rules and lengths (optional links)
	// -------------------------------------------------------------------------

	/** A live tile of a third same-chain platform inside the disc of diameter Scale * |S End| at its middle. */
	bool LensBlocked(int32 A, int32 B, const FVector& S, const FVector& End, double Scale) const
	{
		if (Scale <= 0.0)
		{
			return false;
		}

		const double MX = (S.X + End.X) * 0.5;
		const double MY = (S.Y + End.Y) * 0.5;
		const double Radius = 0.5 * Scale * HexBridgePlan::Dist2D(S, End);
		const double RadiusSq = Radius * Radius;
		const double Reach = Radius + Sub.MaxFootprint;
		const uint8 Chain = E(A).Chain;

		bool bBlocked = false;

		ForEachPlatformNear(MX - Reach, MY - Reach, MX + Reach, MY + Reach, [&](int32 C)
		{
			if (bBlocked || C == A || C == B || E(C).Chain != Chain)
			{
				return;
			}

			const FPlatformEntry& Entry = E(C);

			if (FMath::Sqrt(FMath::Square(Entry.Location.X - MX) + FMath::Square(Entry.Location.Y - MY)) > Radius + Entry.Footprint)
			{
				return;
			}

			for (int32 TileIndex = 0; TileIndex < Entry.Tiles.Num(); ++TileIndex)
			{
				const FTileInfo& Tile = Entry.Tiles[TileIndex];

				if (IsTileLive(C, TileIndex) && FMath::Square(Tile.Center.X - MX) + FMath::Square(Tile.Center.Y - MY) < RadiusSq)
				{
					bBlocked = true;
					return;
				}
			}
		});

		return bBlocked;
	}

	bool LensOk(const FCand& C, FOption& O) const
	{
		if (O.Lens < 0)
		{
			O.Lens = LensBlocked(C.A, C.B, EdgeA(C, O).Mid, EdgeB(C, O).Mid, HexBridgePlan::GabrielScale) ? 0 : 1;
		}

		return O.Lens == 1;
	}

	/** Some platform has live bridges to both A and B, each shorter than Limit. */
	bool ClosesTriangle(int32 A, int32 B, double Limit) const
	{
		TArray<int32, TInlineAllocator<8>> NearB;

		for (const FEnd& End : Plats[B].Ends)
		{
			const FBridgeRecord& Record = Recs[End.Record];

			if (Record.Length < Limit && !Record.bDying)
			{
				NearB.Add(Record.LocalA == B ? Record.LocalB : Record.LocalA);
			}
		}

		if (NearB.Num() == 0)
		{
			return false;
		}

		for (const FEnd& End : Plats[A].Ends)
		{
			const FBridgeRecord& Record = Recs[End.Record];

			if (Record.Length < Limit && !Record.bDying && NearB.Contains(Record.LocalA == A ? Record.LocalB : Record.LocalA))
			{
				return true;
			}
		}

		return false;
	}

	/** Every bridge already on an islet end leaves at least IsletThroughDegrees away from this deck (a through stone). */
	bool IsThrough(const FCand& C, FOption& O) const
	{
		if (!DeckOf(C, O))
		{
			return false;
		}

		const double CosThrough = FMath::Cos(FMath::DegreesToRadians(HexBridgePlan::IsletThroughDegrees));

		for (int32 Side = 0; Side < 2; ++Side)
		{
			const int32 P = Side == 0 ? C.A : C.B;
			const FVector2D& Dir = Side == 0 ? O.DirA : O.DirB;

			if (!E(P).bIslet)
			{
				continue;
			}

			if (Plats[P].Ends.Num() == 0)
			{
				return false;
			}

			for (const FEnd& End : Plats[P].Ends)
			{
				if (FVector2D::DotProduct(Dir, End.Dir) > CosThrough)
				{
					return false;
				}
			}
		}

		return true;
	}

	/** <= Cap; onto an islet <= IsletMaxLength, or longer only when the islet becomes a through stone. */
	bool OptionalLengthOk(const FCand& C, FOption& O, double LengthCap) const
	{
		if (O.L3 > LengthCap)
		{
			return false;
		}

		if (!E(C.A).bIslet && !E(C.B).bIslet)
		{
			return true;
		}

		if (O.L3 <= Settings.IsletMaxLength)
		{
			return true;
		}

		return O.L3 <= HexBridgePlan::IsletThroughLength && IsThrough(C, O);
	}

	static double LoopStretchOf(double Length)
	{
		using namespace HexBridgePlan;

		const double F = FMath::Clamp((Length - LoopShortLength) / (LoopLongLength - LoopShortLength), 0.0, 1.0);
		return LoopStretch + (LoopStretchLong - LoopStretch) * F;
	}

	bool JumpOk(const FCand& C) const
	{
		return Settings.MaxSplineDistanceJump <= 0.f || C.Jump <= Settings.MaxSplineDistanceJump;
	}

	/**
	 * Route-cut repair / bypass link: <= Cap; an islet end longer than IsletMaxLength must make it a
	 * through stone, unless (bAnyIslet) the islet has at most one bridge; empty route lens.
	 */
	bool RouteOptionOk(const FCand& C, FOption& O, double LengthCap, bool bAnyIslet) const
	{
		if (O.L3 > LengthCap)
		{
			return false;
		}

		for (const int32 P : { C.A, C.B })
		{
			if (E(P).bIslet && O.L3 > Settings.IsletMaxLength && !(bAnyIslet && Plats[P].Ends.Num() <= 1) && !IsThrough(C, O))
			{
				return false;
			}
		}

		return !LensBlocked(C.A, C.B, EdgeA(C, O).Mid, EdgeB(C, O).Mid, HexBridgePlan::RouteGabrielScale);
	}

	bool BranchOptionOk(const FCand& C, FOption& O) const
	{
		return OptionalLengthOk(C, O, HexBridgePlan::CutMaxLength) && LensOk(C, O);
	}


	// -------------------------------------------------------------------------
	// Walking distance over the live network (bounded Dijkstra over bridge ends)
	// -------------------------------------------------------------------------

	/**
	 * Shortest walk from P on A to Q on B over non-dying bridges (deck length) and straight walks
	 * between bridge ends on a platform, never through Avoid. Inf when longer than Limit.
	 */
	double WalkDistance(int32 A, const FVector& P, int32 B, const FVector& Q, double Limit, int32 Avoid = INDEX_NONE)
	{
		using namespace HexBridgePlan;

		struct FItem
		{
			double D;
			int32 Id;
			int32 Side;
			int32 Record;

			bool operator<(const FItem& Other) const
			{
				if (D != Other.D)
				{
					return D < Other.D;
				}

				return Id != Other.Id ? Id < Other.Id : Side < Other.Side;
			}
		};

		const int32 NumSlots = Recs.Num() * 2;

		if (WalkStamp.Num() < NumSlots)
		{
			WalkStamp.SetNumZeroed(NumSlots);
			WalkDistances.SetNumZeroed(NumSlots);
		}

		if (++WalkGeneration == 0)
		{
			FMemory::Memzero(WalkStamp.GetData(), WalkStamp.Num() * sizeof(uint32));
			WalkGeneration = 1;
		}

		auto GetDistance = [this](int32 Slot) { return WalkStamp[Slot] == WalkGeneration ? WalkDistances[Slot] : Inf; };
		auto SetDistance = [this](int32 Slot, double D) { WalkStamp[Slot] = WalkGeneration; WalkDistances[Slot] = D; };

		TArray<FItem, TInlineAllocator<64>> Heap;
		double Best = Inf;

		for (const FEnd& End : Plats[A].Ends)
		{
			const FBridgeRecord& Record = Recs[End.Record];

			if (Record.bDying)
			{
				continue;
			}

			const int32 Side = Record.LocalA == A ? 0 : 1;
			const int32 Other = Side == 0 ? Record.LocalB : Record.LocalA;

			if (Other == Avoid && Other != B)
			{
				continue;
			}

			const double D = FVector::Dist(P, End.Point);
			const int32 Slot = End.Record * 2 + Side;

			if (D < GetDistance(Slot))
			{
				SetDistance(Slot, D);
				Heap.Add({ D, Record.Id, Side, End.Record });
			}
		}

		Heap.Heapify();

		while (Heap.Num() > 0)
		{
			FItem Item;
			Heap.HeapPop(Item, EAllowShrinking::No);

			if (Item.D > GetDistance(Item.Record * 2 + Item.Side) || Item.D >= Best || Item.D > Limit)
			{
				continue;
			}

			const FBridgeRecord& Record = Recs[Item.Record];
			const int32 Plat = Item.Side == 0 ? Record.LocalB : Record.LocalA;
			const FVector& Arrival = Item.Side == 0 ? Record.MidB : Record.MidA;
			const double Crossed = Item.D + Record.Length;

			if (Crossed >= Best || Crossed > Limit)
			{
				continue;
			}

			if (Plat == B)
			{
				Best = FMath::Min(Best, Crossed + FVector::Dist(Arrival, Q));
				continue;
			}

			for (const FEnd& End : Plats[Plat].Ends)
			{
				if (End.Record == Item.Record)
				{
					continue;
				}

				const FBridgeRecord& Next = Recs[End.Record];

				if (Next.bDying)
				{
					continue;
				}

				const int32 Side = Next.LocalA == Plat ? 0 : 1;
				const int32 Other = Side == 0 ? Next.LocalB : Next.LocalA;

				if (Other == Avoid && Other != B)
				{
					continue;
				}

				const double D = Crossed + FVector::Dist(Arrival, End.Point);
				const int32 Slot = End.Record * 2 + Side;

				if (D < GetDistance(Slot) && D < Best && D <= Limit)
				{
					SetDistance(Slot, D);
					Heap.HeapPush({ D, Next.Id, Side, End.Record });
				}
			}
		}

		return Best <= Limit ? Best : Inf;
	}


	// -------------------------------------------------------------------------
	// Build / roll back
	// -------------------------------------------------------------------------

	/**
	 * Plans the cheapest option of candidate Ci that Accept allows and that passes every check
	 * (geometry first, traces last), among options costing at most MaxAlt times the best one not
	 * known to fail its trace (MaxAlt <= 0: any). Returns the record or INDEX_NONE.
	 */
	int32 TryBuild(int32 Ci, EBridgePass Pass, const FRules& Rules, TFunctionRef<bool(int32)> Accept, double MaxAlt = 1.5)
	{
		if (Cands[Ci].Built != INDEX_NONE)
		{
			return Cands[Ci].Built;
		}

		// Never a second bridge between two platforms (e.g. next to a guarded one that stayed)
		if (Linked(Cands[Ci].A, Cands[Ci].B))
		{
			return INDEX_NONE;
		}

		const int32 BestIndex = Cands[Ci].Best();

		if (BestIndex == INDEX_NONE)
		{
			return INDEX_NONE;
		}

		const double Limit = MaxAlt > 0.0 ? Cands[Ci].Options[BestIndex].Cost * MaxAlt : HexBridgePlan::Inf;

		for (int32 Oi = 0; Oi < Cands[Ci].Options.Num(); ++Oi)
		{
			const FOption& O = Cands[Ci].Options[Oi];

			if (O.Traced == 0)
			{
				continue;
			}

			if (O.Cost > Limit)
			{
				break;
			}

			if (!Accept(Oi))
			{
				continue;
			}

			if (GeometryOk(Ci, Oi, Rules) != EFail::None || !TraceOk(Ci, Oi))
			{
				continue;
			}

			return AddRecord(Ci, Oi, Pass);
		}

		return INDEX_NONE;
	}

	int32 AddRecord(int32 Ci, int32 Oi, EBridgePass Pass)
	{
		const FCand& C = Cands[Ci];
		const FOption& O = C.Options[Oi];
		const FEdgeWorld& EA = EdgeA(C, O);
		const FEdgeWorld& EB = EdgeB(C, O);

		FBridgeRecord Record;
		Record.KeyA = FPlatformKey(Plats[C.A].Actor);
		Record.KeyB = FPlatformKey(Plats[C.B].Actor);
		Record.Id = Sub.NextRecordId++;
		Record.SerialA = E(C.A).Serial;
		Record.SerialB = E(C.B).Serial;
		Record.OrderA = EA.Order;
		Record.OrderB = EB.Order;
		Record.TileA = EA.Tile;
		Record.TileB = EB.Tile;
		Record.MissingA = EA.Missing;
		Record.MissingB = EB.Missing;
		Record.MidA = EA.Mid;
		Record.MidB = EB.Mid;
		Record.DirA = O.DirA;
		Record.DirB = O.DirB;
		Record.TangentA = O.Deck.T0;
		Record.TangentB = O.Deck.T1;
		Record.Deck = O.Deck.Coarse;
		Record.Bounds = O.Deck.Bounds;
		Record.Length = O.Deck.Arc;
		Record.Burst = Sub.CurrentBurst;
		Record.Chain = E(C.A).Chain;
		Record.Pass = Pass;
		Record.bCurved = O.Deck.bCurved;
		Record.bPlanned = true;
		Record.bDying = false;
		Record.LocalA = C.A;
		Record.LocalB = C.B;

		const int32 RecordIndex = Recs.Add(MoveTemp(Record));
		IndexRecord(RecordIndex);
		AddEnds(RecordIndex);
		Union(C.A, C.B);

		Cands[Ci].Built = RecordIndex;
		RecordCand.Add(RecordIndex, Ci);
		Planned.Add(RecordIndex);
		++Stats.Planned[static_cast<int32>(Pass)];

		return RecordIndex;
	}

	/** Un-plans the most recent planned record (roll-back). Nothing is spawned before the plan is final. */
	void RemoveLastPlanned()
	{
		// Planned records are appended to Recs in plan order, so the latest one is the last record
		if (Planned.Num() == 0 || !ensure(Planned.Last() == Recs.Num() - 1))
		{
			return;
		}

		const int32 RecordIndex = Planned.Pop(EAllowShrinking::No);
		const FBridgeRecord& Record = Recs[RecordIndex];

		ForEachRecordCell(Record.Bounds, [this, RecordIndex](const FIntPoint& Cell)
		{
			if (TArray<int32>* List = RecGrid.Find(Cell))
			{
				List->RemoveSingle(RecordIndex);
			}
		});

		for (const int32 P : { Record.LocalA, Record.LocalB })
		{
			Plats[P].Ends.RemoveAll([RecordIndex](const FEnd& End) { return End.Record == RecordIndex; });
		}

		int32 Ci = INDEX_NONE;

		if (RecordCand.RemoveAndCopyValue(RecordIndex, Ci) && Cands.IsValidIndex(Ci) && Cands[Ci].Built == RecordIndex)
		{
			Cands[Ci].Built = INDEX_NONE;
		}

		--Stats.Planned[static_cast<int32>(Record.Pass)];

		Recs.Pop(EAllowShrinking::No);
		RebuildUnionFind();
	}


	// -------------------------------------------------------------------------
	// Batch setup: platforms, records, tentative / revalidated, planned set, pairs
	// -------------------------------------------------------------------------

	void BuildPlatforms(const TArray<FPlatformKey>& BatchKeys)
	{
		TArray<FPlatformEntry*> Entries;

		for (TPair<FPlatformKey, FPlatformEntry>& Pair : Sub.Platforms)
		{
			if (IsValid(Pair.Value.Platform.Get()))
			{
				Entries.Add(&Pair.Value);
			}
		}

		// Serial order, never map or pointer order
		Entries.Sort([](const FPlatformEntry& Left, const FPlatformEntry& Right) { return Left.Serial < Right.Serial; });

		Plats.SetNum(Entries.Num());

		for (int32 Index = 0; Index < Entries.Num(); ++Index)
		{
			FPlat& Plat = Plats[Index];
			Plat.Entry = Entries[Index];
			Plat.Actor = Plat.Entry->Platform.Get();
			Plat.Cell = Sub.GetCell(Plat.Entry->Location, Settings.SpatialCellSize);
			Plat.bCollapsing = Settings.bSkipCollapsingPlatforms && IsPlatformCollapsing(*Plat.Actor);

			if (MayHaveCollapsedTiles(*Plat.Actor))
			{
				const TArray<FTileInfo>& Tiles = Plat.Entry->Tiles;
				Plat.DeadTiles.Init(false, Tiles.Num());

				for (int32 TileIndex = 0; TileIndex < Tiles.Num(); ++TileIndex)
				{
					if (Plat.Actor->IsTileCollapsed(Tiles[TileIndex].Coord))
					{
						Plat.DeadTiles[TileIndex] = true;
						Plat.bHasDeadTiles = true;
					}
				}
			}

			SerialToLocal.Add(Plat.Entry->Serial, Index);
			Cells.FindOrAdd(Plat.Cell).Add(Index);
		}

		for (const FPlatformKey& Key : BatchKeys)
		{
			const FPlatformEntry* Entry = Sub.Platforms.Find(Key);
			const int32* Local = Entry ? SerialToLocal.Find(Entry->Serial) : nullptr;

			if (Local)
			{
				Plats[*Local].bBatchNew = true;
				BatchNew.Add(*Local);
			}
		}

		BatchNew.Sort();
		CellReach = FMath::Max(1, FMath::CeilToInt(Sub.MaxReach / Settings.SpatialCellSize));
	}

	/** Moves the tentative (this burst's) and revalidated (clipped by a new platform) records out of Recs. */
	void SplitRecords(TArray<FBridgeRecord>& OutTentative, TArray<FBridgeRecord>& OutDropped)
	{
		Recs = MoveTemp(Sub.Bridges);
		Sub.Bridges.Reset();

		// Per batch: platform indices and whether an end is on a collapsing platform
		Recs.RemoveAll([this](FBridgeRecord& Record)
		{
			const int32* LocalA = SerialToLocal.Find(Record.SerialA);
			const int32* LocalB = SerialToLocal.Find(Record.SerialB);

			if (!LocalA || !LocalB)
			{
				return true;
			}

			Record.LocalA = *LocalA;
			Record.LocalB = *LocalB;
			Record.bDying = Plats[*LocalA].bCollapsing || Plats[*LocalB].bCollapsing;
			Record.bPlanned = false;
			return false;
		});

		GatherPlayers();

		// 0 = keep, 1 = tentative, 2 = dropped
		TArray<uint8> Fate;
		Fate.SetNumZeroed(Recs.Num());

		if (Settings.bReplanBursts)
		{
			for (int32 Index = 0; Index < Recs.Num(); ++Index)
			{
				const FBridgeRecord& Record = Recs[Index];

				// Only a bridge with an end on a platform of this burst: that platform is in the
				// planned set, so the pair is formed again. A bridge this burst added between two
				// older platforms (a revalidation re-plan, an on-demand ROUTE / BYPASS pair) would be
				// destroyed and never re-planned, so it stays fixed.
				const bool bBurstEnd = Plats[Record.LocalA].Entry->Burst == Sub.CurrentBurst
					|| Plats[Record.LocalB].Entry->Burst == Sub.CurrentBurst;

				if (Record.Burst == Sub.CurrentBurst && bBurstEnd && !Record.bDying && !IsPlayerNear(Record))
				{
					Fate[Index] = 1;
				}
			}
		}

		if (Settings.bRevalidateBridges && BatchNew.Num() > 0)
		{
			const double Clearance = Settings.RevalidateClearance;
			TArray<int32> Near;

			for (int32 Index = 0; Index < Recs.Num(); ++Index)
			{
				const FBridgeRecord& Record = Recs[Index];

				if (Fate[Index] != 0 || Record.bDying)
				{
					continue;
				}

				Near.Reset();

				for (const int32 P : BatchNew)
				{
					const FPlatformEntry& Entry = E(P);
					const double Reach = Entry.Footprint + Clearance;

					if (Entry.Location.X + Reach >= Record.Bounds.Min.X && Entry.Location.X - Reach <= Record.Bounds.Max.X
						&& Entry.Location.Y + Reach >= Record.Bounds.Min.Y && Entry.Location.Y - Reach <= Record.Bounds.Max.Y)
					{
						Near.Add(P);
					}
				}

				if (Near.Num() > 0
					&& !ClearOfPlatforms(Record.LocalA, Record.LocalB, Record.Deck, Record.Bounds, Clearance, &Near)
					&& !IsPlayerNear(Record))
				{
					Fate[Index] = 2;
				}
			}
		}

		TArray<FBridgeRecord> Keep;
		Keep.Reserve(Recs.Num());

		for (int32 Index = 0; Index < Recs.Num(); ++Index)
		{
			TArray<FBridgeRecord>& Target = Fate[Index] == 0 ? Keep : (Fate[Index] == 1 ? OutTentative : OutDropped);
			Target.Add(MoveTemp(Recs[Index]));
		}

		Recs = MoveTemp(Keep);
		RebuildState();
	}

	/** The planned set: this burst's platforms (or this batch's) plus both ends of every dropped bridge. */
	void BuildPlannedSet(const TArray<FBridgeRecord>& Dropped)
	{
		TBitArray<> InSet(false, Plats.Num());

		for (int32 P = 0; P < Plats.Num(); ++P)
		{
			InSet[P] = Settings.bReplanBursts ? Plats[P].Entry->Burst == Sub.CurrentBurst : Plats[P].bBatchNew;
		}

		for (const FBridgeRecord& Record : Dropped)
		{
			InSet[Record.LocalA] = true;
			InSet[Record.LocalB] = true;
		}

		for (int32 P = 0; P < Plats.Num(); ++P)
		{
			if (InSet[P] && !Plats[P].bCollapsing)
			{
				Plats[P].NewRank = NewPlats.Add(P);
			}
		}
	}

	/** Pairs of a planned platform with any platform near it, each once, and their options. No traces. */
	void FormPairs()
	{
		TSet<TPair<int32, int32>> Seen;

		for (const int32 A : NewPlats)
		{
			for (int32 X = -CellReach; X <= CellReach; ++X)
			{
				for (int32 Y = -CellReach; Y <= CellReach; ++Y)
				{
					const TArray<int32>* List = Cells.Find(Plats[A].Cell + FIntPoint(X, Y));

					if (!List)
					{
						continue;
					}

					for (const int32 B : *List)
					{
						// A planned B with a lower Serial formed this pair already
						if (B == A
							|| (Plats[B].NewRank != INDEX_NONE && Plats[B].NewRank < Plats[A].NewRank)
							|| !ChainsMayPair(A, B)
							|| Plats[B].bCollapsing
							|| !InRange(A, B))
						{
							continue;
						}

						++Stats.Pairs;

						const TPair<int32, int32> Key = PairKey(E(A).Serial, E(B).Serial);
						const bool bAFirst = E(A).Serial > E(B).Serial;
						FCand Cand;

						if (!Seen.Contains(Key) && MakeCandidate(bAFirst ? A : B, bAFirst ? B : A, /*bWide=*/false, Settings.MaxBridgeLength, Cand))
						{
							Seen.Add(Key);
							Cands.Add(MoveTemp(Cand));
						}
					}
				}
			}
		}

		// Cheapest first, ties by serials
		Cands.StableSort();

		NumBatchCands = Cands.Num();

		for (int32 Ci = 0; Ci < NumBatchCands; ++Ci)
		{
			CandIndex.Add(PairKey(Cands[Ci].SerialMin, Cands[Ci].SerialMax), Ci);
			Plats[Cands[Ci].A].Cands.Add(Ci);
			Plats[Cands[Ci].B].Cands.Add(Ci);
		}
	}


	// -------------------------------------------------------------------------
	// Cut edges (ROUTE, BRANCH)
	// -------------------------------------------------------------------------

	void CutBridges(uint8 Chain, FCutGraph& Graph) const
	{
		Graph.Adj.Reset();
		Graph.Adj.SetNum(Plats.Num());
		Graph.Nodes.Reset();
		Graph.Cuts.Reset();

		for (int32 RecordIndex = 0; RecordIndex < Recs.Num(); ++RecordIndex)
		{
			const FBridgeRecord& Record = Recs[RecordIndex];

			if (Record.Chain == Chain && !Record.bDying)
			{
				Graph.Adj[Record.LocalA].Emplace(Record.LocalB, RecordIndex);
				Graph.Adj[Record.LocalB].Emplace(Record.LocalA, RecordIndex);
			}
		}

		for (int32 P = 0; P < Plats.Num(); ++P)
		{
			if (Graph.Adj[P].Num() > 0)
			{
				Graph.Nodes.Add(P);
			}
		}

		// Iterative Tarjan, roots in Serial order
		struct FFrame
		{
			int32 Node;
			int32 ParentRecord;
			int32 Next;
		};

		TArray<int32> Disc;
		TArray<int32> Low;
		Disc.Init(INDEX_NONE, Plats.Num());
		Low.Init(INDEX_NONE, Plats.Num());

		TArray<FFrame> Stack;
		int32 Timer = 0;

		for (const int32 Root : Graph.Nodes)
		{
			if (Disc[Root] != INDEX_NONE)
			{
				continue;
			}

			Disc[Root] = Low[Root] = Timer++;
			Stack.Add({ Root, INDEX_NONE, 0 });

			while (Stack.Num() > 0)
			{
				const int32 Top = Stack.Num() - 1;
				const int32 U = Stack[Top].Node;
				bool bAdvanced = false;

				while (Stack[Top].Next < Graph.Adj[U].Num())
				{
					const TPair<int32, int32> Link = Graph.Adj[U][Stack[Top].Next++];

					if (Link.Value == Stack[Top].ParentRecord)
					{
						continue;
					}

					if (Disc[Link.Key] == INDEX_NONE)
					{
						Disc[Link.Key] = Low[Link.Key] = Timer++;
						Stack.Add({ Link.Key, Link.Value, 0 });
						bAdvanced = true;
						break;
					}

					Low[U] = FMath::Min(Low[U], Disc[Link.Key]);
				}

				if (!bAdvanced)
				{
					const FFrame Done = Stack.Pop(EAllowShrinking::No);

					if (Stack.Num() > 0)
					{
						const int32 Up = Stack.Last().Node;
						Low[Up] = FMath::Min(Low[Up], Low[Done.Node]);

						if (Low[Done.Node] > Disc[Up])
						{
							Graph.Cuts.Add(Done.ParentRecord);
						}
					}
				}
			}
		}
	}

	/** Platforms reachable from Start without crossing record Cut. */
	void SideOf(const FCutGraph& Graph, int32 Start, int32 Cut, TBitArray<>& OutSide) const
	{
		OutSide.Init(false, Plats.Num());
		OutSide[Start] = true;

		TArray<int32, TInlineAllocator<64>> Stack;
		Stack.Add(Start);

		while (Stack.Num() > 0)
		{
			const int32 U = Stack.Pop(EAllowShrinking::No);

			for (const TPair<int32, int32>& Link : Graph.Adj[U])
			{
				if (Link.Value != Cut && !OutSide[Link.Key])
				{
					OutSide[Link.Key] = true;
					Stack.Add(Link.Key);
				}
			}
		}
	}

	void BuildRouteGraph(uint8 Chain, FRouteGraph& Route) const
	{
		CutBridges(Chain, Route.Graph);

		const FCutGraph& Graph = Route.Graph;
		TSet<int32> CutSet;
		CutSet.Append(Graph.Cuts);

		// 2-edge-connected components: union over the non-cut bridges
		TArray<int32> Root;
		Root.SetNumUninitialized(Plats.Num());

		for (int32 P = 0; P < Plats.Num(); ++P)
		{
			Root[P] = P;
		}

		auto FindRoot = [&Root](int32 P)
		{
			while (Root[P] != P)
			{
				Root[P] = Root[Root[P]];
				P = Root[P];
			}

			return P;
		};

		for (int32 RecordIndex = 0; RecordIndex < Recs.Num(); ++RecordIndex)
		{
			const FBridgeRecord& Record = Recs[RecordIndex];

			if (Record.Chain == Chain && !Record.bDying && !CutSet.Contains(RecordIndex))
			{
				const int32 RootA = FindRoot(Record.LocalA);
				const int32 RootB = FindRoot(Record.LocalB);

				if (RootA != RootB)
				{
					Root[FMath::Max(RootA, RootB)] = FMath::Min(RootA, RootB);
				}
			}
		}

		Route.Comp.Init(INDEX_NONE, Plats.Num());

		for (const int32 P : Graph.Nodes)
		{
			Route.Comp[P] = FindRoot(P);
		}

		// Bridge tree, and the cuts with centre platforms on both sides (route cuts)
		Route.Tree.Reset();
		Route.Tree.SetNum(Plats.Num());
		Route.RouteCuts.Reset();

		TBitArray<> Side;

		for (const int32 Cut : Graph.Cuts)
		{
			const FBridgeRecord& Record = Recs[Cut];
			const int32 CompA = Route.Comp[Record.LocalA];
			const int32 CompB = Route.Comp[Record.LocalB];
			Route.Tree[CompA].Emplace(CompB, Cut);
			Route.Tree[CompB].Emplace(CompA, Cut);

			SideOf(Graph, Record.LocalA, Cut, Side);

			bool bCentreInside = false;
			bool bCentreOutside = false;

			for (const int32 P : Graph.Nodes)
			{
				if (E(P).Kind == EPlatformKind::Centre)
				{
					(Side[P] ? bCentreInside : bCentreOutside) = true;
				}
			}

			if (bCentreInside && bCentreOutside)
			{
				Route.RouteCuts.Add(Cut);
			}
		}
	}

	/** Number of route cuts on the bridge-tree path between two components. */
	int32 TreePathCuts(const FRouteGraph& Route, int32 CompA, int32 CompB) const
	{
		if (CompA == CompB)
		{
			return 0;
		}

		// Previous (component, record) on the path from CompA
		TMap<int32, TPair<int32, int32>> Previous;
		Previous.Add(CompA, TPair<int32, int32>(INDEX_NONE, INDEX_NONE));

		TArray<int32, TInlineAllocator<32>> Stack;
		Stack.Add(CompA);

		while (Stack.Num() > 0)
		{
			const int32 U = Stack.Pop(EAllowShrinking::No);

			if (U == CompB)
			{
				break;
			}

			for (const TPair<int32, int32>& Link : Route.Tree[U])
			{
				if (!Previous.Contains(Link.Key))
				{
					Previous.Add(Link.Key, TPair<int32, int32>(U, Link.Value));
					Stack.Add(Link.Key);
				}
			}
		}

		if (!Previous.Contains(CompB))
		{
			return 0;
		}

		int32 Count = 0;

		for (int32 U = CompB; Previous[U].Key != INDEX_NONE; U = Previous[U].Key)
		{
			if (Route.RouteCuts.Contains(Previous[U].Value))
			{
				++Count;
			}
		}

		return Count;
	}

	bool AnyNewNear(uint8 Chain, double X, double Y, double Radius) const
	{
		for (const int32 P : NewPlats)
		{
			const FPlatformEntry& Entry = E(P);

			if (Entry.Chain == Chain && FMath::Sqrt(FMath::Square(Entry.Location.X - X) + FMath::Square(Entry.Location.Y - Y)) <= Radius + Entry.Footprint)
			{
				return true;
			}
		}

		return false;
	}

	/** The chains of the planned set, in order. */
	TArray<uint8, TInlineAllocator<2>> NewChains() const
	{
		TArray<uint8, TInlineAllocator<2>> Chains;

		for (const int32 P : NewPlats)
		{
			Chains.AddUnique(E(P).Chain);
		}

		Chains.Sort();
		return Chains;
	}

	/** Centre platforms of a chain that are not collapsing, by (SplineDistance, Serial). */
	TArray<int32> Centres(uint8 Chain) const
	{
		TArray<int32> Out;

		for (int32 P = 0; P < Plats.Num(); ++P)
		{
			if (E(P).Chain == Chain && E(P).Kind == EPlatformKind::Centre && !Plats[P].bCollapsing)
			{
				Out.Add(P);
			}
		}

		// P is in Serial order, so a stable sort on SplineDistance keeps Serial for ties
		Out.StableSort([this](int32 Left, int32 Right) { return E(Left).SplineDistance < E(Right).SplineDistance; });
		return Out;
	}


	// -------------------------------------------------------------------------
	// Passes (they only plan)
	// -------------------------------------------------------------------------

	/** SPINE: consecutive centre platforms along the path get their best route built first. */
	void SpinePass()
	{
		using namespace HexBridgePlan;

		for (uint8 Chain = 0; Chain < 2; ++Chain)
		{
			const TArray<int32> Cents = Centres(Chain);

			for (int32 Index = 0; Index + 1 < Cents.Num(); ++Index)
			{
				const int32 X = Cents[Index];
				const int32 Y = Cents[Index + 1];

				if ((!IsNew(X) && !IsNew(Y)) || E(Y).SplineDistance - E(X).SplineDistance > SpineMaxGap)
				{
					continue;
				}

				TSet<int32> Excluded;

				for (int32 Attempt = 0; Attempt < SpineAttempts; ++Attempt)
				{
					TArray<int32, TInlineAllocator<SpineMaxHops>> Todo;

					if (!BestRoute(X, Y, Excluded, Todo) || Todo.Num() == 0)
					{
						break;
					}

					bool bAllBuilt = true;

					for (const int32 Ci : Todo)
					{
						if (TryBuild(Ci, EBridgePass::Spine, SpineRules, [](int32) { return true; }) == INDEX_NONE)
						{
							bAllBuilt = false;
							Excluded.Add(Ci);
							break;
						}
					}

					if (bAllBuilt)
					{
						break;
					}
				}
			}
		}
	}

	/**
	 * Cheapest chain of links X -> Y (<= SpineMaxHops): non-dying bridges (length) and this batch's
	 * unbuilt candidates (cost, more when a third platform sits in their narrow lens), plus straight
	 * walks on each platform. OutTodo = the route's unbuilt candidates, in route order.
	 */
	bool BestRoute(int32 X, int32 Y, const TSet<int32>& Excluded, TArray<int32, TInlineAllocator<HexBridgePlan::SpineMaxHops>>& OutTodo)
	{
		using namespace HexBridgePlan;

		struct FNode
		{
			int32 Parent;
			int32 Cand;		// INDEX_NONE for a live bridge hop
			int32 Hops;
		};

		struct FItem
		{
			double D;
			int32 Count;
			int32 Plat;
			int32 Node;
			FVector Point;

			bool operator<(const FItem& Other) const
			{
				return D != Other.D ? D < Other.D : Count < Other.Count;
			}
		};

		TArray<FNode> Nodes;
		Nodes.Add({ INDEX_NONE, INDEX_NONE, 0 });

		TArray<FItem> Heap;
		Heap.Add({ 0.0, 0, X, 0, E(X).Location });

		TBitArray<> Settled(false, Plats.Num());
		int32 Count = 1;
		double BestTotal = Inf;
		int32 Result = INDEX_NONE;

		while (Heap.Num() > 0)
		{
			FItem Item;
			Heap.HeapPop(Item, EAllowShrinking::No);

			if (Item.D >= BestTotal)
			{
				break;
			}

			if (Settled[Item.Plat])
			{
				continue;
			}

			Settled[Item.Plat] = true;

			if (Item.Plat == Y)
			{
				const double Total = Item.D + FVector::Dist(Item.Point, E(Y).Location);

				if (Total < BestTotal)
				{
					BestTotal = Total;
					Result = Item.Node;
				}

				continue;
			}

			if (Nodes[Item.Node].Hops >= SpineMaxHops)
			{
				continue;
			}

			for (const FEnd& End : Plats[Item.Plat].Ends)
			{
				const FBridgeRecord& Record = Recs[End.Record];

				if (Record.bDying)
				{
					continue;
				}

				const bool bFromA = Record.LocalA == Item.Plat;
				const int32 Next = bFromA ? Record.LocalB : Record.LocalA;

				if (Settled[Next])
				{
					continue;
				}

				const FVector& Departure = bFromA ? Record.MidA : Record.MidB;
				const FVector& Arrival = bFromA ? Record.MidB : Record.MidA;
				const int32 Node = Nodes.Add({ Item.Node, INDEX_NONE, Nodes[Item.Node].Hops + 1 });
				Heap.HeapPush({ Item.D + FVector::Dist(Item.Point, Departure) + Record.Length, Count++, Next, Node, Arrival });
			}

			for (const int32 Ci : Plats[Item.Plat].Cands)
			{
				const FCand& C = Cands[Ci];

				if (C.Built != INDEX_NONE || Excluded.Contains(Ci))
				{
					continue;
				}

				const int32 Oi = C.Best();

				if (Oi == INDEX_NONE)
				{
					continue;
				}

				const FOption& O = C.Options[Oi];
				const bool bFromA = C.A == Item.Plat;
				const int32 Next = bFromA ? C.B : C.A;

				if (Settled[Next])
				{
					continue;
				}

				const FVector& MidA = EdgeA(C, O).Mid;
				const FVector& MidB = EdgeB(C, O).Mid;
				double Cost = O.Cost;

				if (SpineSkimPenalty > 1.0 && LensBlocked(C.A, C.B, MidA, MidB, SpineSkimScale))
				{
					Cost *= SpineSkimPenalty;
				}

				const int32 Node = Nodes.Add({ Item.Node, Ci, Nodes[Item.Node].Hops + 1 });
				Heap.HeapPush({ Item.D + FVector::Dist(Item.Point, bFromA ? MidA : MidB) + Cost, Count++, Next, Node, bFromA ? MidB : MidA });
			}
		}

		if (Result == INDEX_NONE)
		{
			return false;
		}

		OutTodo.Reset();

		for (int32 Node = Result; Node != INDEX_NONE; Node = Nodes[Node].Parent)
		{
			if (Nodes[Node].Cand != INDEX_NONE && Cands[Nodes[Node].Cand].Built == INDEX_NONE)
			{
				OutTodo.Add(Nodes[Node].Cand);
			}
		}

		Algo::Reverse(OutTodo);
		return true;
	}

	/**
	 * TREE: Kruskal on cost over every candidate. A failed option queues the pair's next option; one
	 * that failed only an end rule is re-queued once at cost * TreeRelaxPenalty with relaxed end rules.
	 */
	void TreePass()
	{
		struct FItem
		{
			double Cost;
			int32 SerialMin;
			int32 SerialMax;
			int32 Option;
			int32 bRelaxed;
			int32 Cand;

			bool operator<(const FItem& Other) const
			{
				if (Cost != Other.Cost) { return Cost < Other.Cost; }
				if (SerialMin != Other.SerialMin) { return SerialMin < Other.SerialMin; }
				if (SerialMax != Other.SerialMax) { return SerialMax < Other.SerialMax; }
				if (Option != Other.Option) { return Option < Other.Option; }
				if (bRelaxed != Other.bRelaxed) { return bRelaxed < Other.bRelaxed; }
				return Cand < Other.Cand;
			}
		};

		TArray<FItem> Heap;

		for (int32 Ci = 0; Ci < NumBatchCands; ++Ci)
		{
			const FCand& C = Cands[Ci];

			if (C.Built == INDEX_NONE)
			{
				Heap.Add({ C.Options[0].Cost, C.SerialMin, C.SerialMax, 0, 0, Ci });
			}
		}

		Heap.Heapify();

		while (Heap.Num() > 0)
		{
			FItem Item;
			Heap.HeapPop(Item, EAllowShrinking::No);

			const int32 Ci = Item.Cand;

			if (Cands[Ci].Built != INDEX_NONE || Find(Cands[Ci].A) == Find(Cands[Ci].B))
			{
				continue;
			}

			EFail Why = EFail::Trace;

			if (Cands[Ci].Options[Item.Option].Traced != 0)
			{
				Why = GeometryOk(Ci, Item.Option, Item.bRelaxed ? Relaxed : Strict);

				if (Why == EFail::None && !TraceOk(Ci, Item.Option))
				{
					Why = EFail::Trace;
				}
			}

			if (Why == EFail::None)
			{
				AddRecord(Ci, Item.Option, EBridgePass::Tree);
				continue;
			}

			if (!Item.bRelaxed && (Why == EFail::Spacing || Why == EFail::Spread || Why == EFail::Fan))
			{
				Heap.HeapPush({ Cands[Ci].Options[Item.Option].Cost * HexBridgePlan::TreeRelaxPenalty, Item.SerialMin, Item.SerialMax, Item.Option, 1, Ci });
			}

			if (!Item.bRelaxed && Item.Option + 1 < Cands[Ci].Options.Num())
			{
				Heap.HeapPush({ Cands[Ci].Options[Item.Option + 1].Cost, Item.SerialMin, Item.SerialMax, Item.Option + 1, 0, Ci });
			}
		}
	}

	/** Natural optional link: short enough, empty lens, not the long side of a triangle, saves a walk longer than Stretch * L. */
	bool WantedLink(int32 Ci, int32 Oi, double LengthCap, double Stretch)
	{
		const FCand& C = Cands[Ci];
		FOption& O = Cands[Ci].Options[Oi];

		if (!OptionalLengthOk(C, O, LengthCap) || !LensOk(C, O))
		{
			return false;
		}

		if (HexBridgePlan::TriangleRatio > 0.0 && ClosesTriangle(C.A, C.B, HexBridgePlan::TriangleRatio * O.L3))
		{
			return false;
		}

		const double Limit = (Stretch > 0.0 ? Stretch : LoopStretchOf(O.L3)) * O.L3;
		return WalkDistance(C.A, EdgeA(C, O).Mid, C.B, EdgeB(C, O).Mid, Limit) > Limit;
	}

	/**
	 * LOOP: greedy spanner in cost order. A pair not linked yet gets a natural link when the walk
	 * between its ends over the network is longer than stretch(L) * L.
	 */
	void LoopPass()
	{
		for (int32 Ci = 0; Ci < NumBatchCands; ++Ci)
		{
			const FCand& C = Cands[Ci];

			if (C.Built != INDEX_NONE || Linked(C.A, C.B) || !JumpOk(C))
			{
				continue;
			}

			const int32 First = C.Best();

			if (First == INDEX_NONE)
			{
				continue;
			}

			const FOption& O = C.Options[First];
			const double Limit = LoopStretchOf(O.L3) * O.L3;

			if (WalkDistance(C.A, EdgeA(C, O).Mid, C.B, EdgeB(C, O).Mid, Limit) <= Limit)
			{
				continue;
			}

			TryBuild(Ci, EBridgePass::Loop, Optional, [this, Ci](int32 Oi) { return WantedLink(Ci, Oi, Settings.LoopMaxLength, 0.0); });
		}
	}

	/**
	 * LEAF: a platform left with one bridge gets a short natural second link that saves a real walk,
	 * shortest first, not to its only neighbour.
	 */
	void LeafPass()
	{
		TArray<int32> Touched;

		for (int32 Ci = 0; Ci < NumBatchCands; ++Ci)
		{
			Touched.AddUnique(Cands[Ci].A);
			Touched.AddUnique(Cands[Ci].B);
		}

		Touched.Sort();

		for (const int32 P : Touched)
		{
			if (Plats[P].Ends.Num() != 1 || Plats[P].bCollapsing)
			{
				continue;
			}

			const FBridgeRecord& Only = Recs[Plats[P].Ends[0].Record];
			const int32 Neighbour = Only.LocalA == P ? Only.LocalB : Only.LocalA;

			TArray<int32> Options;

			for (const int32 Ci : Plats[P].Cands)
			{
				if (Cands[Ci].Built == INDEX_NONE)
				{
					Options.Add(Ci);
				}
			}

			Options.StableSort([this](int32 Left, int32 Right)
			{
				const FCand& L = Cands[Left];
				const FCand& R = Cands[Right];

				if (L.Options[0].L3 != R.Options[0].L3)
				{
					return L.Options[0].L3 < R.Options[0].L3;
				}

				return L.SerialMin != R.SerialMin ? L.SerialMin < R.SerialMin : L.SerialMax < R.SerialMax;
			});

			for (const int32 Ci : Options)
			{
				const FCand& C = Cands[Ci];
				const int32 Other = C.A == P ? C.B : C.A;

				if (Other == Neighbour || Linked(C.A, C.B) || !JumpOk(C))
				{
					continue;
				}

				if (TryBuild(Ci, EBridgePass::Leaf, Optional, [this, Ci](int32 Oi) { return WantedLink(Ci, Oi, HexBridgePlan::DeadEndMaxLength, HexBridgePlan::DeadEndStretch); }) != INDEX_NONE)
				{
					break;
				}
			}
		}
	}

	/**
	 * ROUTE: a cut bridge near the batch whose loss would split the main route (centre platforms on
	 * both sides) is repaired with the route-rule link across it that removes the most route cuts
	 * per cost. Repeated until no such cut is left untried.
	 */
	void RoutePass()
	{
		using namespace HexBridgePlan;

		const double LengthCap = Settings.RouteMaxLength;

		for (const uint8 Chain : NewChains())
		{
			TSet<int32> Done;
			FRouteGraph Route;
			TBitArray<> SideA;

			while (true)
			{
				BuildRouteGraph(Chain, Route);

				TArray<int32> Cuts = Route.Graph.Cuts;
				Cuts.Sort([this](int32 Left, int32 Right) { return Recs[Left].Id < Recs[Right].Id; });

				int32 Target = INDEX_NONE;

				for (const int32 Cut : Cuts)
				{
					const FBridgeRecord& Record = Recs[Cut];

					if (!Route.RouteCuts.Contains(Cut) || Done.Contains(Record.Id))
					{
						continue;
					}

					const double MX = (Record.MidA.X + Record.MidB.X) * 0.5;
					const double MY = (Record.MidA.Y + Record.MidB.Y) * 0.5;

					if (Record.bPlanned || AnyNewNear(Chain, MX, MY, CutNearNew))
					{
						Target = Cut;
						break;
					}
				}

				if (Target == INDEX_NONE)
				{
					break;
				}

				Done.Add(Recs[Target].Id);

				const double MX = (Recs[Target].MidA.X + Recs[Target].MidB.X) * 0.5;
				const double MY = (Recs[Target].MidA.Y + Recs[Target].MidB.Y) * 0.5;

				SideOf(Route.Graph, Recs[Target].LocalA, Target, SideA);

				auto IsNear = [this, MX, MY](int32 P)
				{
					const FPlatformEntry& Entry = E(P);
					return FMath::Sqrt(FMath::Square(Entry.Location.X - MX) + FMath::Square(Entry.Location.Y - MY)) <= RouteCutRadius + Entry.Footprint
						&& !Plats[P].bCollapsing;
				};

				TArray<int32> As;
				TArray<int32> Bs;

				for (const int32 P : Route.Graph.Nodes)
				{
					if (IsNear(P))
					{
						(SideA[P] ? As : Bs).Add(P);
					}
				}

				struct FLink
				{
					double Score;
					int32 SerialMin;
					int32 SerialMax;
					int32 Cand;
				};

				TArray<FLink> Links;

				for (const int32 A : As)
				{
					for (const int32 B : Bs)
					{
						if (Dist2D(E(A).Location, E(B).Location) > E(A).Footprint + E(B).Footprint + LengthCap)
						{
							continue;
						}

						const int32 Ci = CandBetween(A, B);

						if (Ci == INDEX_NONE || Cands[Ci].Built != INDEX_NONE || Linked(A, B) || !JumpOk(Cands[Ci]))
						{
							continue;
						}

						const int32 Oi = Cands[Ci].Best();

						if (Oi == INDEX_NONE || !RouteOptionOk(Cands[Ci], Cands[Ci].Options[Oi], LengthCap, /*bAnyIslet=*/true))
						{
							continue;
						}

						const int32 PathCuts = FMath::Max(1, TreePathCuts(Route, Route.Comp[A], Route.Comp[B]));
						Links.Add({ Cands[Ci].Options[Oi].Cost / PathCuts, Cands[Ci].SerialMin, Cands[Ci].SerialMax, Ci });
					}
				}

				Links.StableSort([](const FLink& Left, const FLink& Right)
				{
					if (Left.Score != Right.Score)
					{
						return Left.Score < Right.Score;
					}

					return Left.SerialMin != Right.SerialMin ? Left.SerialMin < Right.SerialMin : Left.SerialMax < Right.SerialMax;
				});

				for (const FLink& Link : Links)
				{
					const int32 Ci = Link.Cand;

					if (TryBuild(Ci, EBridgePass::Route, RouteRules, [this, Ci, LengthCap](int32 Oi) { return RouteOptionOk(Cands[Ci], Cands[Ci].Options[Oi], LengthCap, true); }) != INDEX_NONE)
					{
						break;
					}
				}
			}
		}
	}

	/**
	 * BYPASS: for consecutive centre platforms Kp, K, Kn around the batch, when Kp can't reach Kn
	 * without K within BypassStretch * |Kp Kn|, plans the cheapest set of route-rule links that gives
	 * such a walk (rolled back when one of them fails).
	 */
	void BypassPass()
	{
		using namespace HexBridgePlan;

		const double LengthCap = Settings.RouteMaxLength;

		for (const uint8 Chain : NewChains())
		{
			const TArray<int32> Cents = Centres(Chain);

			TArray<double> NewDistances;

			for (const int32 P : NewPlats)
			{
				if (E(P).Chain == Chain)
				{
					NewDistances.Add(E(P).SplineDistance);
				}
			}

			for (int32 Index = 1; Index + 1 < Cents.Num(); ++Index)
			{
				const int32 Kp = Cents[Index - 1];
				const int32 K = Cents[Index];
				const int32 Kn = Cents[Index + 1];

				const double From = E(Kp).SplineDistance;
				const double To = E(Kn).SplineDistance;

				if (To - From > BypassMaxSpan)
				{
					continue;
				}

				bool bNewInside = false;

				for (const double Distance : NewDistances)
				{
					bNewInside |= Distance >= From - 1.0 && Distance <= To + 1.0;
				}

				if (!bNewInside)
				{
					continue;
				}

				const double Straight = Dist2D(E(Kp).Location, E(Kn).Location);
				const double Limit = BypassStretch * Straight;

				if (WalkDistance(Kp, E(Kp).Location, Kn, E(Kn).Location, Limit, K) <= Limit)
				{
					continue;
				}

				const double Radius = FMath::Max(Straight, BypassMinRadius);
				TArray<int32> Links;
				BypassLinks(K, Radius, LengthCap, Links);

				if (Links.Num() == 0)
				{
					continue;
				}

				for (int32 Attempt = 0; Attempt < BypassAttempts; ++Attempt)
				{
					TArray<int32> Path;

					if (!BypassSearch(Kp, Kn, K, Radius, Links, Limit, Path) || Path.Num() == 0)
					{
						break;
					}

					const int32 PlannedBefore = Planned.Num();
					bool bAllBuilt = true;

					for (const int32 Ci : Path)
					{
						if (TryBuild(Ci, EBridgePass::Bypass, RouteRules, [this, Ci, LengthCap](int32 Oi) { return RouteOptionOk(Cands[Ci], Cands[Ci].Options[Oi], LengthCap, false); }) == INDEX_NONE)
						{
							Links.Remove(Ci);
							bAllBuilt = false;
							break;
						}
					}

					if (bAllBuilt)
					{
						break;
					}

					while (Planned.Num() > PlannedBefore)
					{
						RemoveLastPlanned();
					}
				}
			}
		}
	}

	/** Unbuilt, unlinked links near K (not touching K) whose best option passes the route rule. */
	void BypassLinks(int32 K, double Radius, double LengthCap, TArray<int32>& Out)
	{
		using namespace HexBridgePlan;

		TArray<int32> Near;
		TBitArray<> IsNear(false, Plats.Num());

		for (int32 P = 0; P < Plats.Num(); ++P)
		{
			if (P != K && E(P).Chain == E(K).Chain && !Plats[P].bCollapsing && Dist2D(E(P).Location, E(K).Location) <= Radius + E(P).Footprint)
			{
				Near.Add(P);
				IsNear[P] = true;
			}
		}

		auto LinkOk = [this, LengthCap](int32 Ci)
		{
			if (Ci == INDEX_NONE || Cands[Ci].Built != INDEX_NONE)
			{
				return false;
			}

			const int32 Oi = Cands[Ci].Best();
			return Oi != INDEX_NONE && RouteOptionOk(Cands[Ci], Cands[Ci].Options[Oi], LengthCap, false);
		};

		TSet<TPair<int32, int32>> Seen;
		Out.Reset();

		for (int32 Ci = 0; Ci < NumBatchCands; ++Ci)
		{
			const FCand& C = Cands[Ci];

			if (IsNear[C.A] && IsNear[C.B] && !Linked(C.A, C.B) && LinkOk(Ci))
			{
				Out.Add(Ci);
				Seen.Add(PairKey(C.SerialMin, C.SerialMax));
			}
		}

		// Pairs of two older platforms near the batch, made on demand
		for (int32 I = 0; I < Near.Num(); ++I)
		{
			for (int32 J = I + 1; J < Near.Num(); ++J)
			{
				const int32 A = Near[I];
				const int32 B = Near[J];

				if (Seen.Contains(PairKey(E(A).Serial, E(B).Serial)) || IsNew(A) || IsNew(B)
					|| Dist2D(E(A).Location, E(B).Location) > E(A).Footprint + E(B).Footprint + LengthCap
					|| Linked(A, B))
				{
					continue;
				}

				const int32 Ci = CandBetween(A, B);

				if (LinkOk(Ci))
				{
					Out.Add(Ci);
					Seen.Add(PairKey(E(A).Serial, E(B).Serial));
				}
			}
		}

		Out.StableSort([this](int32 Left, int32 Right)
		{
			const FCand& L = Cands[Left];
			const FCand& R = Cands[Right];

			if (L.Options[0].Cost != R.Options[0].Cost)
			{
				return L.Options[0].Cost < R.Options[0].Cost;
			}

			return L.SerialMin != R.SerialMin ? L.SerialMin < R.SerialMin : L.SerialMax < R.SerialMax;
		});
	}

	/**
	 * Walk Kp -> Kn avoiding K over live bridges near K, plus candidate links (weighted
	 * BypassPenalty * length + BypassNewCost; the real walk counts the length). OutPath stays empty
	 * when the live bridges are enough. False when there is no walk within Limit.
	 */
	bool BypassSearch(int32 Kp, int32 Kn, int32 K, double Radius, const TArray<int32>& Links, double Limit, TArray<int32>& OutPath)
	{
		using namespace HexBridgePlan;

		struct FEdge
		{
			int32 From;
			int32 To;
			double Length;
			int32 Cand;
		};

		auto Inside = [this, K, Radius](int32 P)
		{
			return P != K && Dist2D(E(P).Location, E(K).Location) <= Radius + E(P).Footprint;
		};

		TArray<FVector> Points;
		TArray<TPair<int32, TArray<int32>>> NodesOn;	// per platform in first-seen order
		TArray<FEdge> Edges;

		auto AddNode = [&Points, &NodesOn](int32 P, const FVector& Point)
		{
			const int32 Node = Points.Add(Point);
			TPair<int32, TArray<int32>>* Found = NodesOn.FindByPredicate([P](const TPair<int32, TArray<int32>>& Pair) { return Pair.Key == P; });

			if (!Found)
			{
				Found = &NodesOn.Emplace_GetRef(P, TArray<int32>());
			}

			Found->Value.Add(Node);
			return Node;
		};

		for (const FBridgeRecord& Record : Recs)
		{
			if (Record.bDying || Record.LocalA == K || Record.LocalB == K
				|| !(Inside(Record.LocalA) || Record.LocalA == Kp || Record.LocalA == Kn)
				|| !(Inside(Record.LocalB) || Record.LocalB == Kp || Record.LocalB == Kn))
			{
				continue;
			}

			const int32 NodeA = AddNode(Record.LocalA, Record.MidA);
			const int32 NodeB = AddNode(Record.LocalB, Record.MidB);
			Edges.Add({ NodeA, NodeB, Record.Length, INDEX_NONE });
		}

		const int32 NumRecordEdges = Edges.Num();

		for (const int32 Ci : Links)
		{
			const int32 Oi = Cands[Ci].Best();

			if (Oi == INDEX_NONE)
			{
				continue;
			}

			const FCand& C = Cands[Ci];
			const FOption& O = C.Options[Oi];
			const int32 NodeA = AddNode(C.A, EdgeA(C, O).Mid);
			const int32 NodeB = AddNode(C.B, EdgeB(C, O).Mid);
			Edges.Add({ NodeA, NodeB, O.L3, Ci });
		}

		const FVector Source = E(Kp).Location;
		const FVector Destination = E(Kn).Location;

		auto Search = [&](int32 NumEdges, TArray<int32>& OutCands) -> bool
		{
			struct FArc
			{
				int32 To;
				double Length;
				int32 Cand;
			};

			const int32 NumNodes = Points.Num();
			const int32 Src = NumNodes;
			const int32 Dst = NumNodes + 1;

			TArray<TArray<FArc>> Adj;
			Adj.SetNum(NumNodes + 2);
			TBitArray<> Used(false, NumNodes);

			for (int32 Index = 0; Index < NumEdges; ++Index)
			{
				const FEdge& Edge = Edges[Index];
				Adj[Edge.From].Add({ Edge.To, Edge.Length, Edge.Cand });
				Adj[Edge.To].Add({ Edge.From, Edge.Length, Edge.Cand });
				Used[Edge.From] = true;
				Used[Edge.To] = true;
			}

			// Straight walks between the used nodes of each platform
			for (const TPair<int32, TArray<int32>>& Pair : NodesOn)
			{
				TArray<int32, TInlineAllocator<16>> List;

				for (const int32 Node : Pair.Value)
				{
					if (Used[Node])
					{
						List.Add(Node);
					}
				}

				for (int32 I = 0; I < List.Num(); ++I)
				{
					for (int32 J = I + 1; J < List.Num(); ++J)
					{
						const double D = FVector::Dist(Points[List[I]], Points[List[J]]);
						Adj[List[I]].Add({ List[J], D, INDEX_NONE });
						Adj[List[J]].Add({ List[I], D, INDEX_NONE });
					}
				}
			}

			for (const TPair<int32, TArray<int32>>& Pair : NodesOn)
			{
				for (const int32 Node : Pair.Value)
				{
					if (!Used[Node])
					{
						continue;
					}

					if (Pair.Key == Kp)
					{
						Adj[Src].Add({ Node, FVector::Dist(Source, Points[Node]), INDEX_NONE });
					}

					if (Pair.Key == Kn)
					{
						Adj[Node].Add({ Dst, FVector::Dist(Points[Node], Destination), INDEX_NONE });
					}
				}
			}

			struct FItem
			{
				double Weight;
				double Walk;
				int32 Count;
				int32 Node;

				bool operator<(const FItem& Other) const
				{
					if (Weight != Other.Weight) { return Weight < Other.Weight; }
					if (Walk != Other.Walk) { return Walk < Other.Walk; }
					return Count < Other.Count;
				}
			};

			TArray<double> Best;
			Best.Init(Inf, NumNodes + 2);
			Best[Src] = 0.0;

			// (previous node, candidate of the link used) per node
			TArray<TPair<int32, int32>> Previous;
			Previous.Init(TPair<int32, int32>(INDEX_NONE, INDEX_NONE), NumNodes + 2);

			TArray<FItem> Heap;
			Heap.Add({ 0.0, 0.0, 0, Src });
			int32 Count = 1;

			while (Heap.Num() > 0)
			{
				FItem Item;
				Heap.HeapPop(Item, EAllowShrinking::No);

				if (Item.Node == Dst)
				{
					OutCands.Reset();

					for (int32 Node = Dst; Previous[Node].Key != INDEX_NONE; Node = Previous[Node].Key)
					{
						if (Previous[Node].Value != INDEX_NONE)
						{
							OutCands.AddUnique(Previous[Node].Value);
						}
					}

					Algo::Reverse(OutCands);
					return true;
				}

				if (Item.Weight > Best[Item.Node])
				{
					continue;
				}

				for (const FArc& Arc : Adj[Item.Node])
				{
					const double Walk = Item.Walk + Arc.Length;

					if (Walk > Limit)
					{
						continue;
					}

					const double Weight = Item.Weight + Arc.Length + (Arc.Cand != INDEX_NONE ? (BypassPenalty - 1.0) * Arc.Length + BypassNewCost : 0.0);

					if (Weight < Best[Arc.To])
					{
						Best[Arc.To] = Weight;
						Previous[Arc.To] = TPair<int32, int32>(Item.Node, Arc.Cand);
						Heap.HeapPush({ Weight, Walk, Count++, Arc.To });
					}
				}
			}

			return false;
		};

		TArray<int32> Ignored;

		if (Search(NumRecordEdges, Ignored))
		{
			OutPath.Reset();
			return true;
		}

		return Search(Edges.Num(), OutPath);
	}

	/**
	 * BRANCH: a cut bridge near the batch that cuts off a branch of >= CutMinBranch platforms (no centre
	 * on the small side) gets the cheapest short natural link across.
	 */
	void BranchPass()
	{
		using namespace HexBridgePlan;

		for (const uint8 Chain : NewChains())
		{
			FCutGraph Graph;
			CutBridges(Chain, Graph);

			TArray<int32> Cuts = Graph.Cuts;
			Cuts.Sort([this](int32 Left, int32 Right) { return Recs[Left].Id < Recs[Right].Id; });

			TBitArray<> SideA;
			TBitArray<> SideB;

			for (const int32 Cut : Cuts)
			{
				const int32 LocalA = Recs[Cut].LocalA;
				const int32 LocalB = Recs[Cut].LocalB;
				const double MX = (Recs[Cut].MidA.X + Recs[Cut].MidB.X) * 0.5;
				const double MY = (Recs[Cut].MidA.Y + Recs[Cut].MidB.Y) * 0.5;

				if (!Recs[Cut].bPlanned && !AnyNewNear(Chain, MX, MY, CutNearNew))
				{
					continue;
				}

				SideOf(Graph, LocalA, Cut, SideA);

				// No longer a cut (a link was added meanwhile)
				if (SideA[LocalB])
				{
					continue;
				}

				SideOf(Graph, LocalB, Cut, SideB);

				const int32 CountA = SideA.CountSetBits();
				const int32 CountB = SideB.CountSetBits();
				const TBitArray<>& Small = CountA <= CountB ? SideA : SideB;
				const TBitArray<>& Big = CountA <= CountB ? SideB : SideA;

				bool bCentre = false;

				for (TConstSetBitIterator<> It(Small); It; ++It)
				{
					bCentre |= E(It.GetIndex()).Kind == EPlatformKind::Centre;
				}

				if (bCentre || FMath::Min(CountA, CountB) < CutMinBranch)
				{
					continue;
				}

				auto IsNear = [this, MX, MY](int32 P)
				{
					const FPlatformEntry& Entry = E(P);
					return FMath::Sqrt(FMath::Square(Entry.Location.X - MX) + FMath::Square(Entry.Location.Y - MY)) <= CutRadius + Entry.Footprint
						&& !Plats[P].bCollapsing;
				};

				TArray<int32> As;
				TArray<int32> Bs;

				for (TConstSetBitIterator<> It(Small); It; ++It)
				{
					if (IsNear(It.GetIndex()))
					{
						As.Add(It.GetIndex());
					}
				}

				for (TConstSetBitIterator<> It(Big); It; ++It)
				{
					if (IsNear(It.GetIndex()))
					{
						Bs.Add(It.GetIndex());
					}
				}

				TArray<int32> Links;

				for (const int32 A : As)
				{
					for (const int32 B : Bs)
					{
						if (Dist2D(E(A).Location, E(B).Location) > E(A).Footprint + E(B).Footprint + CutMaxLength)
						{
							continue;
						}

						const int32 Ci = CandBetween(A, B);

						if (Ci == INDEX_NONE || Cands[Ci].Built != INDEX_NONE || Linked(A, B) || !JumpOk(Cands[Ci]))
						{
							continue;
						}

						const int32 Oi = Cands[Ci].Best();

						if (Oi != INDEX_NONE && BranchOptionOk(Cands[Ci], Cands[Ci].Options[Oi]))
						{
							Links.Add(Ci);
						}
					}
				}

				Links.StableSort([this](int32 Left, int32 Right)
				{
					const FCand& L = Cands[Left];
					const FCand& R = Cands[Right];
					const double CostL = L.Options[L.Best()].Cost;
					const double CostR = R.Options[R.Best()].Cost;

					if (CostL != CostR)
					{
						return CostL < CostR;
					}

					return L.SerialMin != R.SerialMin ? L.SerialMin < R.SerialMin : L.SerialMax < R.SerialMax;
				});

				for (const int32 Ci : Links)
				{
					const int32 RecordIndex = TryBuild(Ci, EBridgePass::Branch, Resilient, [this, Ci](int32 Oi) { return BranchOptionOk(Cands[Ci], Cands[Ci].Options[Oi]); });

					if (RecordIndex != INDEX_NONE)
					{
						Graph.Adj[Recs[RecordIndex].LocalA].Emplace(Recs[RecordIndex].LocalB, RecordIndex);
						Graph.Adj[Recs[RecordIndex].LocalB].Emplace(Recs[RecordIndex].LocalA, RecordIndex);
						break;
					}
				}
			}
		}
	}

	/** FALLBACK: pairs still in different components: any option with relaxed rules, then wide options. */
	void FallbackPass()
	{
		for (int32 Ci = 0; Ci < NumBatchCands; ++Ci)
		{
			if (Cands[Ci].Built != INDEX_NONE || Find(Cands[Ci].A) == Find(Cands[Ci].B))
			{
				continue;
			}

			if (TryBuild(Ci, EBridgePass::Fallback, FallbackRules, [](int32) { return true; }, /*MaxAlt=*/0.0) != INDEX_NONE)
			{
				continue;
			}

			FCand Wide;

			if (MakeCandidate(Cands[Ci].A, Cands[Ci].B, /*bWide=*/true, Settings.MaxBridgeLength, Wide))
			{
				const int32 Wi = Cands.Add(MoveTemp(Wide));
				const int32 RecordIndex = TryBuild(Wi, EBridgePass::Fallback, FallbackRules, [](int32) { return true; }, /*MaxAlt=*/0.0);

				if (RecordIndex != INDEX_NONE)
				{
					Cands[Ci].Built = RecordIndex;
				}
			}
		}
	}

	/** RESCUE: a planned platform still without a bridge tries every platform within reach, nearest first, wide options, no length cap. */
	void RescuePass()
	{
		for (const int32 P : NewPlats)
		{
			if (Plats[P].Ends.Num() > 0 || Plats[P].bCollapsing)
			{
				continue;
			}

			struct FOther
			{
				double Distance;
				int32 Serial;
				int32 Plat;
			};

			TArray<FOther> Others;

			for (int32 X = -CellReach; X <= CellReach; ++X)
			{
				for (int32 Y = -CellReach; Y <= CellReach; ++Y)
				{
					if (const TArray<int32>* List = Cells.Find(Plats[P].Cell + FIntPoint(X, Y)))
					{
						for (const int32 B : *List)
						{
							if (B != P && ChainsMayPair(P, B) && !Plats[B].bCollapsing && InRange(P, B))
							{
								Others.Add({ HexBridgePlan::Dist2D(E(P).Location, E(B).Location), E(B).Serial, B });
							}
						}
					}
				}
			}

			Others.StableSort([](const FOther& Left, const FOther& Right)
			{
				return Left.Distance != Right.Distance ? Left.Distance < Right.Distance : Left.Serial < Right.Serial;
			});

			for (const FOther& Other : Others)
			{
				const bool bPFirst = E(P).Serial > Other.Serial;
				FCand Wide;

				if (!MakeCandidate(bPFirst ? P : Other.Plat, bPFirst ? Other.Plat : P, /*bWide=*/true, HexBridgePlan::Inf, Wide))
				{
					continue;
				}

				const int32 Wi = Cands.Add(MoveTemp(Wide));

				if (TryBuild(Wi, EBridgePass::Rescue, FallbackRules, [](int32) { return true; }, /*MaxAlt=*/0.0) != INDEX_NONE)
				{
					break;
				}
			}
		}
	}

	int32 CountRouteCuts()
	{
		int32 Count = 0;
		FRouteGraph Route;

		for (const uint8 Chain : NewChains())
		{
			BuildRouteGraph(Chain, Route);
			Count += Route.RouteCuts.Num();
		}

		return Count;
	}


	// -------------------------------------------------------------------------
	// Run
	// -------------------------------------------------------------------------

	void Run(const TArray<FPlatformKey>& BatchKeys, double StartSeconds)
	{
		// 1. Platforms of this batch's view (Serial order), collapsing ones, live tiles
		BuildPlatforms(BatchKeys);

		// 2. Records: this burst's bridges become tentative (re-planned), fixed ones a new platform
		//    clips are dropped. Bridges a player is on or near stay as they are.
		TArray<FBridgeRecord> Tentative;
		TArray<FBridgeRecord> Dropped;
		SplitRecords(Tentative, Dropped);

		TraceParams = FCollisionQueryParams(SCENE_QUERY_STAT(HexBridgeSubsystemTrace), /*bTraceComplex=*/false);

		for (TActorIterator<AMyHexBridge> It(&World); It; ++It)
		{
			TraceParams.AddIgnoredActor(*It);
		}

		// 3. The planned set and its pairs
		BuildPlannedSet(Dropped);
		FormPairs();

		// 4. Passes. They only plan; nothing is spawned before the plan is final.
		SpinePass();
		TreePass();
		LoopPass();
		LeafPass();
		RoutePass();
		BypassPass();
		BranchPass();
		FallbackPass();
		RescuePass();

		Stats.RouteCutsLeft = CountRouteCuts();

		// 5. Actors
		Finish(Tentative, Dropped);

		const double Milliseconds = (FPlatformTime::Seconds() - StartSeconds) * 1000.0;
		const int32* PlannedCounts = Stats.Planned;

		UE_LOG(
			LogHexBridgeSubsystem,
			Log,
			TEXT("Bridged %d new platforms (%d total), burst %d (+%d re-planned), %d pairs, %d candidates | planned spine %d tree %d loop %d leaf %d route %d bypass %d branch %d fallback %d rescue %d | kept %d, spawned %d, destroyed %d/%d (re-plan/revalidated), %d curved | %d traces (%d cached) | %d route cuts left | %.1f ms"),
			BatchNew.Num(),
			Plats.Num(),
			Sub.CurrentBurst,
			FMath::Max(0, NewPlats.Num() - BatchNew.Num()),
			Stats.Pairs,
			NumBatchCands,
			PlannedCounts[static_cast<int32>(EBridgePass::Spine)],
			PlannedCounts[static_cast<int32>(EBridgePass::Tree)],
			PlannedCounts[static_cast<int32>(EBridgePass::Loop)],
			PlannedCounts[static_cast<int32>(EBridgePass::Leaf)],
			PlannedCounts[static_cast<int32>(EBridgePass::Route)],
			PlannedCounts[static_cast<int32>(EBridgePass::Bypass)],
			PlannedCounts[static_cast<int32>(EBridgePass::Branch)],
			PlannedCounts[static_cast<int32>(EBridgePass::Fallback)],
			PlannedCounts[static_cast<int32>(EBridgePass::Rescue)],
			Stats.Kept,
			Stats.Spawned,
			Stats.DestroyedReplan,
			Stats.DestroyedRevalidate,
			Stats.Curved,
			Stats.Traces,
			Stats.TraceCacheHits,
			Stats.RouteCutsLeft,
			Milliseconds
		);
	}

	/** Keeps identical tentative bridges, destroys the rest and the dropped ones, spawns the plan, notifies the batch. */
	void Finish(TArray<FBridgeRecord>& Tentative, TArray<FBridgeRecord>& Dropped)
	{
		// Same pair and edges = same deck and tangents: take over the actor
		using FReuseKey = TTuple<int32, int32, int32, int32>;

		TMap<FReuseKey, int32> TentativeByKey;

		for (int32 Index = 0; Index < Tentative.Num(); ++Index)
		{
			const FBridgeRecord& Record = Tentative[Index];
			TentativeByKey.Add(FReuseKey(Record.SerialA, Record.SerialB, Record.OrderA, Record.OrderB), Index);
		}

		TBitArray<> Reused(false, Tentative.Num());

		for (const int32 RecordIndex : Planned)
		{
			FBridgeRecord& Record = Recs[RecordIndex];
			const int32* Found = TentativeByKey.Find(FReuseKey(Record.SerialA, Record.SerialB, Record.OrderA, Record.OrderB));

			if (Found && !Reused[*Found] && Tentative[*Found].Bridge.IsValid())
			{
				Reused[*Found] = true;
				Record.Bridge = Tentative[*Found].Bridge;
				++Stats.Kept;
			}
		}

		for (int32 Index = 0; Index < Tentative.Num(); ++Index)
		{
			if (!Reused[Index])
			{
				if (AMyHexBridge* Bridge = Tentative[Index].Bridge.Get())
				{
					Bridge->Destroy();
				}

				++Stats.DestroyedReplan;
			}
		}

		for (const FBridgeRecord& Record : Dropped)
		{
			if (AMyHexBridge* Bridge = Record.Bridge.Get())
			{
				Bridge->Destroy();
			}

			++Stats.DestroyedRevalidate;
		}

		// Everything a spawn needs, so nothing below reads the platform entries (spawning runs
		// BeginPlay, which must not be able to leave this planner with dangling entry pointers)
		struct FSpawn
		{
			int32 Record;
			TWeakObjectPtr<AMyHexPlatform> First;
			TWeakObjectPtr<AMyHexPlatform> Second;
			FEdgeWorld EdgeFirst;
			FEdgeWorld EdgeSecond;
			FVector StartTangent;
			FVector EndTangent;
		};

		TArray<FSpawn> Spawns;

		for (const int32 RecordIndex : Planned)
		{
			const FBridgeRecord& Record = Recs[RecordIndex];

			if (Record.Bridge.IsValid())
			{
				continue;
			}

			FEdgeWorld EdgeA;
			EdgeA.Tile = Record.TileA;
			EdgeA.Missing = Record.MissingA;
			EdgeA.Mid = Record.MidA;
			EdgeA.Order = Record.OrderA;

			FEdgeWorld EdgeB;
			EdgeB.Tile = Record.TileB;
			EdgeB.Missing = Record.MissingB;
			EdgeB.Mid = Record.MidB;
			EdgeB.Order = Record.OrderB;

			// The bridge starts on the platform registered later. A deck planned the other way round
			// is reversed: P(1 - t) swaps and negates the tangents.
			const bool bAFirst = Record.SerialA >= Record.SerialB;

			FSpawn& Spawn = Spawns.AddDefaulted_GetRef();
			Spawn.Record = RecordIndex;
			Spawn.First = Plats[bAFirst ? Record.LocalA : Record.LocalB].Actor;
			Spawn.Second = Plats[bAFirst ? Record.LocalB : Record.LocalA].Actor;
			Spawn.EdgeFirst = bAFirst ? EdgeA : EdgeB;
			Spawn.EdgeSecond = bAFirst ? EdgeB : EdgeA;
			Spawn.StartTangent = bAFirst ? Record.TangentA : -Record.TangentB;
			Spawn.EndTangent = bAFirst ? Record.TangentB : -Record.TangentA;
		}

		TArray<TWeakObjectPtr<AMyHexPlatform>> ToNotify;

		for (const int32 P : BatchNew)
		{
			ToNotify.Add(Plats[P].Actor);
		}

		for (const FSpawn& Spawn : Spawns)
		{
			AMyHexPlatform* First = Spawn.First.Get();
			AMyHexPlatform* Second = Spawn.Second.Get();

			if (!IsValid(First) || !IsValid(Second))
			{
				continue;
			}

			if (AMyHexBridge* Bridge = Sub.SpawnBridge(*First, Spawn.EdgeFirst, *Second, Spawn.EdgeSecond, Spawn.StartTangent, Spawn.EndTangent, Settings))
			{
				Recs[Spawn.Record].Bridge = Bridge;
				++Stats.Spawned;
			}
		}

		// Kept: every fixed record, and planned ones that kept or got an actor
		TArray<FBridgeRecord> Final;
		Final.Reserve(Recs.Num());

		for (FBridgeRecord& Record : Recs)
		{
			if (Record.bPlanned)
			{
				if (!Record.Bridge.IsValid())
				{
					continue;
				}

				Stats.Curved += Record.bCurved ? 1 : 0;

				if (Settings.bDrawDebug)
				{
					DrawDeck(Record);
				}
			}

			Record.bPlanned = false;
			Final.Add(MoveTemp(Record));
		}

		Recs.Reset();
		Sub.Bridges = MoveTemp(Final);

		// Bridges are built from the untouched edges. Each platform may now collapse, but starts only
		// once the lead player is on it.
		for (const TWeakObjectPtr<AMyHexPlatform>& WeakPlatform : ToNotify)
		{
			if (AMyHexPlatform* Platform = WeakPlatform.Get())
			{
				Platform->NotifyBridgesReady();
			}
		}
	}

	void DrawDeck(const FBridgeRecord& Record) const
	{
		static const FColor PassColors[static_cast<int32>(EBridgePass::Num)] =
		{
			FColor::Blue,		// Spine
			FColor::Green,		// Tree
			FColor::Cyan,		// Loop
			FColor::Yellow,		// Leaf
			FColor::Orange,		// Route
			FColor::Magenta,	// Bypass
			FColor::Purple,		// Branch
			FColor::Red,		// Fallback
			FColor::White		// Rescue
		};

		const FColor Color = PassColors[static_cast<int32>(Record.Pass)];

		for (int32 Index = 0; Index + 1 < Record.Deck.Num(); ++Index)
		{
			DrawDebugLine(&World, Record.Deck[Index] + FVector(0.0, 0.0, 30.0), Record.Deck[Index + 1] + FVector(0.0, 0.0, 30.0), Color, false, 10.f, 0, 8.f);
		}
	}
};


// =============================================================================
// Lifetime
// =============================================================================

bool UMyHexBridgeSubsystem::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

void UMyHexBridgeSubsystem::Deinitialize()
{
	if (UWorld* World = GetWorld())
	{
		World->GetTimerManager().ClearTimer(ProcessTimerHandle);
	}

	Platforms.Empty();
	PendingPlatforms.Empty();
	Bridges.Empty();
	TraceCache.Empty();
	PathSpline.Reset();
	CachedLeadPawn.Reset();

	Super::Deinitialize();
}


// =============================================================================
// Lead player
// =============================================================================

APawn* UMyHexBridgeSubsystem::SelectLeadPawn() const
{
	const UWorld* World = GetWorld();

	if (!World || World->GetNetMode() == NM_Client)
	{
		return nullptr;
	}

	// For now: the first player on the server (the listen-server host). Iterate rather than use
	// GetFirstPlayerController(), whose first entry can be a stale weak pointer.
	for (FConstPlayerControllerIterator It = World->GetPlayerControllerIterator(); It; ++It)
	{
		if (const APlayerController* PlayerController = It->Get())
		{
			APawn* Pawn = PlayerController->GetPawn();

			// Dead / respawning / spectating: no lead this frame
			return IsValid(Pawn) ? Pawn : nullptr;
		}
	}

	return nullptr;
}

APawn* UMyHexBridgeSubsystem::GetLeadPawn() const
{
	if (LeadPawnFrame != GFrameCounter)
	{
		LeadPawnFrame = GFrameCounter;
		CachedLeadPawn = SelectLeadPawn();
	}

	return CachedLeadPawn.Get();
}

bool UMyHexBridgeSubsystem::GetLeadPathDistance(float& OutDistance) const
{
	if (LeadPathFrame != GFrameCounter)
	{
		LeadPathFrame = GFrameCounter;
		bLeadPathDistanceValid = false;

		const USplineComponent* Spline = PathSpline.Get();
		const APawn* Lead = GetLeadPawn();

		if (Lead && Spline && Spline->GetNumberOfSplinePoints() >= 2)
		{
			CachedLeadPathDistance = Spline->GetDistanceAlongSplineAtSplineInputKey(
				Spline->FindInputKeyClosestToWorldLocation(Lead->GetActorLocation()));
			bLeadPathDistanceValid = true;
		}
	}

	OutDistance = CachedLeadPathDistance;
	return bLeadPathDistanceValid;
}

void UMyHexBridgeSubsystem::RegisterPathSpline(USplineComponent* Spline)
{
	if (PathSpline.IsValid() && PathSpline.Get() != Spline)
	{
		UE_LOG(LogHexBridgeSubsystem, Warning, TEXT("A second path spline was registered; platforms now measure against %s"), *GetNameSafe(Spline));
	}

	PathSpline = Spline;
	LeadPathFrame = MAX_uint64;
}

void UMyHexBridgeSubsystem::UnregisterPathSpline(USplineComponent* Spline)
{
	if (PathSpline.Get() == Spline)
	{
		PathSpline.Reset();
		LeadPathFrame = MAX_uint64;
	}
}

bool UMyHexBridgeSubsystem::TryConsumeCullBudget()
{
	if (CullBudgetFrame != GFrameCounter)
	{
		CullBudgetFrame = GFrameCounter;
		CullsThisFrame = 0;
	}

	if (CullsThisFrame >= MaxPlatformCullsPerFrame)
	{
		return false;
	}

	++CullsThisFrame;
	return true;
}


// =============================================================================
// Registration
// =============================================================================

void UMyHexBridgeSubsystem::RegisterPlatform(AMyHexPlatform* Platform)
{
	if (!IsValid(Platform))
	{
		return;
	}

	PendingPlatforms.AddUnique(Platform);

	// Debounced: every registration restarts BuildDelay, but the batch is built at most MaxBuildDelay
	// after its first registration, so one PCG segment is normally one batch
	const UMyHexBridgeSettings& Settings = *GetDefault<UMyHexBridgeSettings>();
	FTimerManager& TimerManager = GetWorld()->GetTimerManager();
	const double Now = GetWorld()->GetTimeSeconds();

	const bool bTimerActive = TimerManager.IsTimerActive(ProcessTimerHandle);

	if (!bTimerActive)
	{
		FirstPendingTime = Now;
	}

	const double Remaining = Settings.MaxBuildDelay - (Now - FirstPendingTime);

	// Cap reached: leave the pending timer alone. Restarting it at the 0.01 s floor on every
	// registration would keep pushing the batch back while registrations arrive every frame.
	if (bTimerActive && Remaining <= 0.01)
	{
		return;
	}

	// SetTimer restarts an active handle; a rate <= 0 would clear it instead, hence the floor
	const double Delay = FMath::Max(0.01, FMath::Min(static_cast<double>(Settings.BuildDelay), Remaining));

	TimerManager.SetTimer(
		ProcessTimerHandle,
		this,
		&ThisClass::ProcessPendingPlatforms,
		static_cast<float>(Delay),
		false
	);
}

void UMyHexBridgeSubsystem::UnregisterPlatform(AMyHexPlatform* Platform)
{
	PendingPlatforms.Remove(Platform);

	const FPlatformKey Key(Platform);

	Platforms.Remove(Key);

	Bridges.RemoveAll([&Key](const FBridgeRecord& Record) { return Record.KeyA == Key || Record.KeyB == Key; });
}

bool UMyHexBridgeSubsystem::IsPlatformCollapsing(const AMyHexPlatform& Platform)
{
	return Platform.bCollapseStarted
		&& (Platform.bCollapseOnlyWhenLeadLands || MayHaveCollapsedTiles(Platform));
}

bool UMyHexBridgeSubsystem::MayHaveCollapsedTiles(const AMyHexPlatform& Platform)
{
	return Platform.ActivatedTiles.Num() > 0 || Platform.LocalActivatedTiles.Num() > 0;
}

float UMyHexBridgeSubsystem::GetBridgeKeepDistance(const AMyHexPlatform& Platform)
{
	return Platform.BridgeKeepDistance;
}

void UMyHexBridgeSubsystem::InitPlatformEntry(AMyHexPlatform& Platform, FPlatformEntry& Entry)
{
	using namespace HexBridgePlan;

	const UMyHexBridgeSettings& Settings = *GetDefault<UMyHexBridgeSettings>();

	Entry.Platform = &Platform;
	Entry.Serial = NextSerial++;
	Entry.Burst = CurrentBurst;
	Entry.Location = Platform.GetActorLocation();
	Entry.GridSize = Platform.GridSize;
	Entry.bIslet = Platform.GridSize <= SmallGridSize;
	Entry.Footprint = Platform.ComputeFootprintRadius();
	Entry.SplineDistance = Platform.GetSplineDistance();

	const UInstancedStaticMeshComponent* ISM = Platform.HexPillarsISM;
	const FTransform ToWorld = ISM ? ISM->GetComponentTransform() : Platform.GetActorTransform();

	// Tiles are laid out with HexToWorld in the ISM's space: pointy-top hexagons rotated with it
	Entry.HexRadius = Platform.HexRadius * static_cast<float>(FMath::Max(FMath::Abs(ToWorld.GetScale3D().X), FMath::Abs(ToWorld.GetScale3D().Y)));

	const double Yaw = FMath::DegreesToRadians(ToWorld.GetRotation().Rotator().Yaw);
	Entry.YawCos = FMath::Cos(Yaw);
	Entry.YawSin = FMath::Sin(Yaw);

	for (int32 K = 0; K < 6; ++K)
	{
		const double Angle = Yaw + FMath::DegreesToRadians(30.0 + 60.0 * K);
		Entry.HexVerts[K] = FVector2D(Entry.HexRadius * FMath::Cos(Angle), Entry.HexRadius * FMath::Sin(Angle));
	}

	// Kind, from the path's closest point
	const USplineComponent* Path = PathSpline.Get();
	const bool bHasPath = Path && Path->GetNumberOfSplinePoints() >= 2;
	const FVector PathPoint = bHasPath ? Path->FindLocationClosestToWorldLocation(Entry.Location, ESplineCoordinateSpace::World) : FVector::ZeroVector;

	if (Platform.GridSize < StreamMinGridSize)
	{
		Entry.Kind = EPlatformKind::Ring;
	}
	else
	{
		Entry.Kind = (!bHasPath || Dist2D(PathPoint, Entry.Location) <= CentreMaxOffset) ? EPlatformKind::Centre : EPlatformKind::Side;
	}

	// Chain, from the tag PCG gives the platform (read now, not in BeginPlay: tags may come later)
	static const FName LowerTag(TEXT("HexLower"));
	static const FName UpperTag(TEXT("HexUpper"));

	if (Platform.ActorHasTag(LowerTag))
	{
		Entry.Chain = 0;
	}
	else if (Platform.ActorHasTag(UpperTag))
	{
		Entry.Chain = 1;
	}
	else
	{
		Entry.Chain = (bHasPath && Entry.Location.Z - PathPoint.Z > Settings.ChainSplitHeight) ? 1 : 0;

		if (!bWarnedChainFallback)
		{
			bWarnedChainFallback = true;
			UE_LOG(LogHexBridgeSubsystem, Warning, TEXT("%s has neither the HexLower nor the HexUpper tag; chains are told apart by height above the path (ChainSplitHeight %.0f)"), *GetNameSafe(&Platform), Settings.ChainSplitHeight);
		}
	}

	// Edges, stored by coordinate. Nothing has collapsed yet, so the cached EdgeInstances indices are valid.
	for (const TPair<int32, TArray<FIntVector>>& Pair : Platform.EdgeInstances)
	{
		const FIntVector* Tile = Platform.InstanceToHex.Find(Pair.Key);

		if (!Tile)
		{
			continue;
		}

		for (const FIntVector& Missing : Pair.Value)
		{
			Entry.EdgeTiles.Add({ *Tile, Missing });
		}
	}

	// Pillars in world space, from the real mesh bounds (top = walkable surface, bottom = pillar foot)
	if (ISM && ISM->GetStaticMesh())
	{
		const FBoxSphereBounds MeshBounds = ISM->GetStaticMesh()->GetBounds();
		const double MeshTopZ = MeshBounds.Origin.Z + MeshBounds.BoxExtent.Z;
		const double MeshBottomZ = MeshBounds.Origin.Z - MeshBounds.BoxExtent.Z;

		for (const TPair<FIntVector, int32>& Pair : Platform.HexMap)
		{
			FTransform TileLocal;

			if (!ISM->GetInstanceTransform(Pair.Value, TileLocal, /*bWorldSpace=*/false))
			{
				continue;
			}

			const FVector Center = ToWorld.TransformPosition(TileLocal.GetLocation());

			FTileInfo& Tile = Entry.Tiles.AddDefaulted_GetRef();
			Tile.Coord = Pair.Key;
			Tile.Center = FVector2D(Center.X, Center.Y);
			Tile.Top = ToWorld.TransformPosition(TileLocal.TransformPosition(FVector(0.0, 0.0, MeshTopZ))).Z;
			Tile.Bottom = ToWorld.TransformPosition(TileLocal.TransformPosition(FVector(0.0, 0.0, MeshBottomZ))).Z;
		}
	}
}


// =============================================================================
// Process a batch of new platforms
// =============================================================================

void UMyHexBridgeSubsystem::ProcessPendingPlatforms()
{
	const UMyHexBridgeSettings& Settings = *GetDefault<UMyHexBridgeSettings>();
	UWorld* World = GetWorld();

	if (!World)
	{
		return;
	}

	const double StartSeconds = FPlatformTime::Seconds();
	const double Now = World->GetTimeSeconds();


	// -------------------------------------------------------------------------
	// 0. Bursts: batches less than BurstQuietTime apart are planned together, at most
	//    BurstMaxDuration long. A new burst fixes the previous one's bridges.
	// -------------------------------------------------------------------------

	if (Now - LastBatchTime > Settings.BurstQuietTime || Now - BurstStartTime > Settings.BurstMaxDuration)
	{
		++CurrentBurst;
		BurstStartTime = Now;
		TraceCache.Reset();
	}

	LastBatchTime = Now;


	// -------------------------------------------------------------------------
	// 1. Prune platforms that are gone and bridges that are gone, going (pending lifespan after an
	//    end tile fell) or lost an end
	// -------------------------------------------------------------------------

	for (auto It = Platforms.CreateIterator(); It; ++It)
	{
		const AMyHexPlatform* Platform = It->Value.Platform.Get();

		if (!IsValid(Platform) || Platform->IsActorBeingDestroyed())
		{
			It.RemoveCurrent();
		}
	}

	Bridges.RemoveAll([this](const FBridgeRecord& Record)
	{
		const AMyHexBridge* Bridge = Record.Bridge.Get();

		if (!IsValid(Bridge) || Bridge->IsActorBeingDestroyed() || Bridge->GetLifeSpan() > 0.f)
		{
			return true;
		}

		const FPlatformEntry* EntryA = Platforms.Find(Record.KeyA);
		const FPlatformEntry* EntryB = Platforms.Find(Record.KeyB);
		const AMyHexPlatform* PlatformA = EntryA ? EntryA->Platform.Get() : nullptr;
		const AMyHexPlatform* PlatformB = EntryB ? EntryB->Platform.Get() : nullptr;

		if (!PlatformA || !PlatformB || PlatformA->IsTileCollapsed(Record.TileA) || PlatformB->IsTileCollapsed(Record.TileB))
		{
			return true;
		}

		FEdgeWorld Unused;
		return !GetEdgeWorld(*PlatformA, { Record.TileA, Record.MissingA }, Unused)
			|| !GetEdgeWorld(*PlatformB, { Record.TileB, Record.MissingB }, Unused);
	});


	// -------------------------------------------------------------------------
	// 2. Register the new platforms (serial, burst, chain, kind, tiles, edges)
	// -------------------------------------------------------------------------

	TArray<FPlatformKey> BatchKeys;

	for (const TWeakObjectPtr<AMyHexPlatform>& WeakPlatform : PendingPlatforms)
	{
		AMyHexPlatform* Platform = WeakPlatform.Get();
		const FPlatformKey Key(Platform);

		if (!IsValid(Platform) || Platform->IsActorBeingDestroyed() || Platforms.Contains(Key))
		{
			continue;
		}

		FPlatformEntry& Entry = Platforms.Add(Key);
		InitPlatformEntry(*Platform, Entry);

		MaxFootprint = FMath::Max(MaxFootprint, Entry.Footprint);
		MaxReach = FMath::Max3(MaxReach, Settings.NeighborRadiusMultiplier * Entry.GridSize * Entry.HexRadius, 2.f * MaxFootprint + Settings.MaxEdgeGap);

		BatchKeys.Add(Key);
	}

	PendingPlatforms.Reset();


	// -------------------------------------------------------------------------
	// 3. Plan, spawn, notify (FPlanner)
	// -------------------------------------------------------------------------

	FPlanner Planner(*this, Settings, *World);
	Planner.Run(BatchKeys, StartSeconds);
}


// =============================================================================
// Edges
// =============================================================================

bool UMyHexBridgeSubsystem::GetEdgeWorld(const AMyHexPlatform& Platform, const FEdgeTile& EdgeTile, FEdgeWorld& OutEdge)
{
	const UInstancedStaticMeshComponent* ISM = Platform.HexPillarsISM;

	if (!ISM || !ISM->GetStaticMesh())
	{
		return false;
	}

	// The tile's current instance index (indices move when other tiles collapse)
	const int32* InstanceIndex = Platform.HexMap.Find(EdgeTile.Tile);

	if (!InstanceIndex)
	{
		return false;
	}

	FTransform TileLocal;

	if (!ISM->GetInstanceTransform(*InstanceIndex, TileLocal, /*bWorldSpace=*/false))
	{
		return false;
	}

	// Top of the pillar mesh, so the edge sits on the walkable surface whatever the mesh pivot is
	const FBoxSphereBounds MeshBounds = ISM->GetStaticMesh()->GetBounds();
	const double MeshTopZ = MeshBounds.Origin.Z + MeshBounds.BoxExtent.Z;

	const FTransform& ToWorld = ISM->GetComponentTransform();
	const FVector TileTop = TileLocal.TransformPosition(FVector(0.0, 0.0, MeshTopZ));

	// The missing neighbour has no instance, but its centre follows from the hex layout
	const FVector2D NeighbourXY = Platform.HexToWorld(EdgeTile.MissingNeighbour.X, EdgeTile.MissingNeighbour.Y, Platform.HexRadius);
	const FVector NeighbourTop(NeighbourXY.X, NeighbourXY.Y, TileTop.Z);

	// The shared side sits exactly half way between the two tile centres
	OutEdge.Tile = EdgeTile.Tile;
	OutEdge.Missing = EdgeTile.MissingNeighbour;
	OutEdge.Mid = ToWorld.TransformPosition((TileTop + NeighbourTop) * 0.5);
	OutEdge.Normal = ToWorld.TransformVectorNoScale((NeighbourTop - TileTop).GetSafeNormal());
	OutEdge.Normal2D = FVector2D(OutEdge.Normal.X, OutEdge.Normal.Y).GetSafeNormal();
	OutEdge.Up = ToWorld.GetUnitAxis(EAxis::Z);

	return true;
}


// =============================================================================
// Trace
// =============================================================================

bool UMyHexBridgeSubsystem::TraceReaches(const FEdgeWorld& From, const FEdgeWorld& To, const AMyHexPlatform& Target, const UMyHexBridgeSettings& Settings, const FCollisionQueryParams* InQueryParams) const
{
	UWorld* World = GetWorld();

	const FVector Start = From.Mid + From.Normal * HexBridgeSubsystemTrace::BridgeTraceStartOffset - From.Up * HexBridgeSubsystemTrace::BridgeTraceDepth;
	const FVector End = To.Mid - To.Normal * HexBridgeSubsystemTrace::BridgeTraceOvershoot - To.Up * HexBridgeSubsystemTrace::BridgeTraceDepth;

	// The source platform is deliberately NOT ignored, so an edge whose line would pass back
	// through its own tiles is rejected
	const FCollisionQueryParams DefaultParams(SCENE_QUERY_STAT(HexBridgeSubsystemTrace), /*bTraceComplex=*/false);
	const FCollisionQueryParams& QueryParams = InQueryParams ? *InQueryParams : DefaultParams;

	FHitResult Hit;
	bool bReaches = false;

	if (World->LineTraceSingleByChannel(Hit, Start, End, Settings.TraceChannel, QueryParams))
	{
		// The first thing the line meets must be the target platform, at the target tile's side.
		// Anything else (a third platform, the source platform, another part of the target's
		// outline) means the two edges can't see each other.
		const FVector Expected = To.Mid - To.Up * HexBridgeSubsystemTrace::BridgeTraceDepth;

		bReaches = Hit.GetActor() == &Target
			&& FVector::DistSquared(Hit.ImpactPoint, Expected) <= FMath::Square(Target.HexRadius * HexBridgeSubsystemTrace::BridgeTraceTolerance);
	}

	if (Settings.bDrawDebug)
	{
		DrawDebugLine(World, Start, End, bReaches ? FColor::Green : FColor::Red, false, 10.f, 0, 4.f);
	}

	return bReaches;
}


// =============================================================================
// Spawn
// =============================================================================

AMyHexBridge* UMyHexBridgeSubsystem::SpawnBridge(AMyHexPlatform& A, const FEdgeWorld& EdgeA, AMyHexPlatform& B, const FEdgeWorld& EdgeB, const FVector& StartTangent, const FVector& EndTangent, const UMyHexBridgeSettings& Settings)
{
	UClass* BridgeClass = Settings.BridgeClass.LoadSynchronous();

	if (!BridgeClass)
	{
		BridgeClass = AMyHexBridge::StaticClass();
	}

	const FTransform SpawnTransform(EdgeA.Mid);

	AMyHexBridge* Bridge = GetWorld()->SpawnActorDeferred<AMyHexBridge>(
		BridgeClass,
		SpawnTransform,
		nullptr,
		nullptr,
		ESpawnActorCollisionHandlingMethod::AlwaysSpawn
	);

	if (!Bridge)
	{
		return nullptr;
	}

	FMyHexBridgeEnd Start;
	Start.Platform = &A;
	Start.Tile = EdgeA.Tile;
	Start.Location = EdgeA.Mid;

	FMyHexBridgeEnd End;
	End.Platform = &B;
	End.Tile = EdgeB.Tile;
	End.Location = EdgeB.Mid;

	// Set before FinishSpawning so BeginPlay already has the spline points and tangents
	Bridge->InitBridge(Start, End, StartTangent, EndTangent);
	Bridge->FinishSpawning(SpawnTransform);

	// BeginPlay destroys a bridge whose end tile already collapsed
	return IsValid(Bridge) && !Bridge->IsActorBeingDestroyed() ? Bridge : nullptr;
}


// =============================================================================
// Helpers
// =============================================================================

FIntPoint UMyHexBridgeSubsystem::GetCell(const FVector& Location, float CellSize) const
{
	return FIntPoint(
		FMath::FloorToInt(Location.X / CellSize),
		FMath::FloorToInt(Location.Y / CellSize)
	);
}
