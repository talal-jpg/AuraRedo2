// Mech Sentinel Swarm - obstacle registry: 3D level geometry (hex platforms, boxes) that live sentinels steer around.

#include "MechSwarm/Core/MechSentinelObstacleSubsystem.h"

#include "CoreGlobals.h"
#include "Engine/World.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(MechSentinelObstacleSubsystem)

DEFINE_LOG_CATEGORY_STATIC(LogMechSentinelObstacles, Log, All);

namespace MechSwarm::ObstaclesPrivate
{
	/** Largest coordinate (cm) of an obstacle or a query, so cell indices stay far inside int32. Beyond it, or NaN = unusable. */
	constexpr double MaxCoordinate = 1.0e9;

	constexpr double InvCellSize = 1.0 / double(UMechSentinelObstacleSubsystem::ObstacleCellSize);

	/** Seconds between two sweeps of stale owners from the avoidance. */
	constexpr double StaleSweepInterval = 1.0;

	FORCEINLINE bool IsUsableCoordinate(const double Value)
	{
		// False for NaN as well
		return FMath::Abs(Value) <= MaxCoordinate;
	}

	FORCEINLINE bool IsUsablePoint(const FVector& Point)
	{
		return IsUsableCoordinate(Point.X) && IsUsableCoordinate(Point.Y) && IsUsableCoordinate(Point.Z);
	}

	FORCEINLINE FIntVector ToCell(const FVector& Position)
	{
		return FIntVector(
			FMath::FloorToInt32(Position.X * InvCellSize),
			FMath::FloorToInt32(Position.Y * InvCellSize),
			FMath::FloorToInt32(Position.Z * InvCellSize));
	}

	/**
	 * Inside a shape: the cheapest of NumExits exits (depth, outward normal). The exit whose normal faces GoalDir best
	 * costs Bias x its depth. Ties keep the first. Returns minus the chosen depth.
	 */
	double PickExit(double* Depths, const FVector* Normals, const int32 NumExits, const FVector& GoalDir, const double Bias, FVector& OutNormal)
	{
		int32 Toward = 0;
		double BestDot = FVector::DotProduct(Normals[0], GoalDir);
		for (int32 Index = 1; Index < NumExits; ++Index)
		{
			const double Dot = FVector::DotProduct(Normals[Index], GoalDir);
			if (Dot > BestDot)
			{
				BestDot = Dot;
				Toward = Index;
			}
		}
		Depths[Toward] *= Bias;

		int32 Exit = 0;
		for (int32 Index = 1; Index < NumExits; ++Index)
		{
			if (Depths[Index] < Depths[Exit])
			{
				Exit = Index;
			}
		}
		OutNormal = Normals[Exit];
		return -Depths[Exit];
	}
}

//----------------------------------------------------------------------//
// FMechSentinelObstacleShape
//----------------------------------------------------------------------//
double FMechSentinelObstacleShape::SignedDistance(const FVector& P) const
{
	if (IsCylinder())
	{
		const double RadialGap = FVector2D::Distance(FVector2D(P), Center) - Radius;
		const double VerticalGap = FMath::Max(Bounds.Min.Z - P.Z, P.Z - Bounds.Max.Z);
		if (RadialGap <= 0.0 && VerticalGap <= 0.0)
		{
			return FMath::Max(RadialGap, VerticalGap);
		}
		return FMath::Sqrt(FMath::Square(FMath::Max(RadialGap, 0.0)) + FMath::Square(FMath::Max(VerticalGap, 0.0)));
	}

	const FVector Gap = (P - Bounds.GetCenter()).GetAbs() - Bounds.GetExtent();
	const double Outside = FVector(FMath::Max(Gap.X, 0.0), FMath::Max(Gap.Y, 0.0), FMath::Max(Gap.Z, 0.0)).Size();
	return Outside + FMath::Min(FMath::Max3(Gap.X, Gap.Y, Gap.Z), 0.0);
}

double FMechSentinelObstacleShape::Closest(const FVector& P, const FVector& GoalDir, const double ExitFaceBias, FVector& OutNormal) const
{
	using namespace MechSwarm::ObstaclesPrivate;

	FVector Nearest;
	if (IsCylinder())
	{
		const FVector2D Radial = FVector2D(P) - Center;
		const double RadialDistance = Radial.Size();
		if (RadialDistance <= Radius && P.Z >= Bounds.Min.Z && P.Z <= Bounds.Max.Z)
		{
			// Inside: out through the rim, the top or the bottom
			const FVector Out = RadialDistance > UE_KINDA_SMALL_NUMBER ? FVector(Radial / RadialDistance, 0.0) : FVector(1.0, 0.0, 0.0);
			double Depths[3] = { Radius - RadialDistance, Bounds.Max.Z - P.Z, P.Z - Bounds.Min.Z };
			const FVector Normals[3] = { Out, FVector::UpVector, FVector::DownVector };
			return PickExit(Depths, Normals, 3, GoalDir, ExitFaceBias, OutNormal);
		}

		const FVector2D Rim = RadialDistance > Radius ? Center + Radial * (Radius / RadialDistance) : FVector2D(P);
		Nearest = FVector(Rim, FMath::Clamp(P.Z, Bounds.Min.Z, Bounds.Max.Z));
	}
	else
	{
		Nearest = FVector(
			FMath::Clamp(P.X, Bounds.Min.X, Bounds.Max.X),
			FMath::Clamp(P.Y, Bounds.Min.Y, Bounds.Max.Y),
			FMath::Clamp(P.Z, Bounds.Min.Z, Bounds.Max.Z));

		if (Nearest == P)
		{
			// Inside: out through one of the six faces
			double Depths[6] = { P.X - Bounds.Min.X, Bounds.Max.X - P.X, P.Y - Bounds.Min.Y, Bounds.Max.Y - P.Y, P.Z - Bounds.Min.Z, Bounds.Max.Z - P.Z };
			const FVector Normals[6] =
			{
				FVector(-1.0, 0.0, 0.0), FVector(1.0, 0.0, 0.0),
				FVector(0.0, -1.0, 0.0), FVector(0.0, 1.0, 0.0),
				FVector::DownVector, FVector::UpVector
			};
			return PickExit(Depths, Normals, 6, GoalDir, ExitFaceBias, OutNormal);
		}
	}

	const FVector Delta = P - Nearest;
	const double Distance = Delta.Size();
	OutNormal = Distance > UE_KINDA_SMALL_NUMBER ? Delta / Distance : FVector::ZeroVector;
	return Distance;
}

bool FMechSentinelObstacleShape::Raycast(const FVector& P, const FVector& Dir, const double MaxDistance, const double Inflate, double& OutT, FVector& OutNormal, bool& bOutInside) const
{
	constexpr double Unbounded = 1.0e18;
	constexpr double ParallelSlab = 1.0e-9;

	double Enter = -Unbounded;
	double Exit = Unbounded;
	FVector EnterNormal = FVector::ZeroVector;
	bool bEnterThroughRim = false;

	// Caps (both shapes): the Z slab of the grown shape
	const double MinZ = Bounds.Min.Z - Inflate;
	const double MaxZ = Bounds.Max.Z + Inflate;
	if (FMath::Abs(Dir.Z) < ParallelSlab)
	{
		if (P.Z < MinZ || P.Z > MaxZ)
		{
			return false;
		}
	}
	else
	{
		const double ToMin = (MinZ - P.Z) / Dir.Z;
		const double ToMax = (MaxZ - P.Z) / Dir.Z;
		Enter = FMath::Min(ToMin, ToMax);
		Exit = FMath::Max(ToMin, ToMax);
		EnterNormal = Dir.Z > 0.0 ? FVector::DownVector : FVector::UpVector;
	}

	if (IsCylinder())
	{
		// The grown rim: |P.XY + t * Dir.XY - Center| = Radius + Inflate
		const double GrownRadius = Radius + Inflate;
		const double OffsetX = P.X - Center.X;
		const double OffsetY = P.Y - Center.Y;
		const double QuadA = Dir.X * Dir.X + Dir.Y * Dir.Y;
		const double QuadB = 2.0 * (OffsetX * Dir.X + OffsetY * Dir.Y);
		const double QuadC = OffsetX * OffsetX + OffsetY * OffsetY - GrownRadius * GrownRadius;
		if (QuadA < 1.0e-12)
		{
			// Vertical ray: inside the circle or never
			if (QuadC > 0.0)
			{
				return false;
			}
		}
		else
		{
			const double Discriminant = QuadB * QuadB - 4.0 * QuadA * QuadC;
			if (Discriminant < 0.0)
			{
				return false;
			}
			const double Root = FMath::Sqrt(Discriminant);
			const double RimEnter = (-QuadB - Root) / (2.0 * QuadA);
			const double RimExit = (-QuadB + Root) / (2.0 * QuadA);
			if (RimEnter > Enter)
			{
				Enter = RimEnter;
				bEnterThroughRim = true;
			}
			Exit = FMath::Min(Exit, RimExit);
		}
	}
	else
	{
		// The X and Y slabs of the grown box
		for (int32 Axis = 0; Axis < 2; ++Axis)
		{
			const double Min = Bounds.Min[Axis] - Inflate;
			const double Max = Bounds.Max[Axis] + Inflate;
			if (FMath::Abs(Dir[Axis]) < ParallelSlab)
			{
				if (P[Axis] < Min || P[Axis] > Max)
				{
					return false;
				}
				continue;
			}
			const double ToMin = (Min - P[Axis]) / Dir[Axis];
			const double ToMax = (Max - P[Axis]) / Dir[Axis];
			const double AxisEnter = FMath::Min(ToMin, ToMax);
			if (AxisEnter > Enter)
			{
				Enter = AxisEnter;
				EnterNormal = FVector::ZeroVector;
				EnterNormal[Axis] = Dir[Axis] > 0.0 ? -1.0 : 1.0;
			}
			Exit = FMath::Min(Exit, FMath::Max(ToMin, ToMax));
		}
	}

	if (Enter > Exit || Exit < 0.0 || Enter > MaxDistance)
	{
		return false;
	}

	if (Enter <= 0.0)
	{
		// Already inside the grown shape
		OutT = 0.0;
		OutNormal = FVector::ZeroVector;
		bOutInside = true;
		return true;
	}

	OutT = Enter;
	bOutInside = false;
	OutNormal = bEnterThroughRim
		? FVector(P.X + Dir.X * Enter - Center.X, P.Y + Dir.Y * Enter - Center.Y, 0.0).GetSafeNormal()
		: EnterNormal;
	return true;
}

bool FMechSentinelObstacleShape::IsOverFootprint(const FVector& P, const double Inflate) const
{
	if (IsCylinder())
	{
		return FVector2D::DistSquared(FVector2D(P), Center) < FMath::Square(Radius + Inflate);
	}
	return P.X > Bounds.Min.X - Inflate && P.X < Bounds.Max.X + Inflate
		&& P.Y > Bounds.Min.Y - Inflate && P.Y < Bounds.Max.Y + Inflate;
}

//----------------------------------------------------------------------//
// Lifecycle
//----------------------------------------------------------------------//
UMechSentinelObstacleSubsystem* UMechSentinelObstacleSubsystem::Get(const UObject* WorldContextObject)
{
	const UWorld* World = WorldContextObject ? WorldContextObject->GetWorld() : nullptr;
	return World ? World->GetSubsystem<UMechSentinelObstacleSubsystem>() : nullptr;
}

bool UMechSentinelObstacleSubsystem::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

void UMechSentinelObstacleSubsystem::Deinitialize()
{
	Slots.Reset();
	FreeSlots.Reset();
	Cells.Reset();
	OversizedSlots.Reset();
	RejectedOwners.Reset();
	NumObstacles = 0;
	NextStaleSweepTime = 0.0;
	++Revision;
	Super::Deinitialize();
}

bool UMechSentinelObstacleSubsystem::HasAuthority() const
{
	const UWorld* World = GetWorld();
	return World && World->GetNetMode() != NM_Client;
}

//----------------------------------------------------------------------//
// Registration
//----------------------------------------------------------------------//
void UMechSentinelObstacleSubsystem::RegisterObstacle(UObject* Owner, const FMechSentinelObstacle& Obstacle, const int32 Key)
{
	if (!ensureMsgf(IsInGameThread(), TEXT("UMechSentinelObstacleSubsystem::RegisterObstacle must run on the game thread")) || !HasAuthority())
	{
		return;
	}

	if (!Owner)
	{
		LogRejected(nullptr, TEXT("it has no owner"));
		return;
	}

	RemoveStaleOwners();

	int32 SlotIndex = FindSlot(Owner, Key);

	FMechSentinelObstacleShape Shape;
	if (!MakeShape(Obstacle, Shape))
	{
		LogRejected(Owner, TEXT("its bounds are empty, inverted, not finite or beyond 1e9 cm"));
		if (SlotIndex != INDEX_NONE)
		{
			RemoveSlot(SlotIndex);
			++Revision;
		}
		return;
	}

	if (SlotIndex == INDEX_NONE)
	{
		SlotIndex = FreeSlots.Num() > 0 ? FreeSlots.Pop(EAllowShrinking::No) : Slots.AddDefaulted();
		++NumObstacles;
	}
	else
	{
		UnlinkSlot(SlotIndex);
	}

	FObstacleSlot& Slot = Slots[SlotIndex];
	Slot.Owner = Owner;
	Slot.Key = Key;
	Slot.Shape = Shape;
	Slot.bUsed = true;
	LinkSlot(SlotIndex);
	++Revision;
}

void UMechSentinelObstacleSubsystem::UnregisterObstacle(UObject* Owner, const int32 Key)
{
	if (!ensureMsgf(IsInGameThread(), TEXT("UMechSentinelObstacleSubsystem::UnregisterObstacle must run on the game thread")) || NumObstacles == 0)
	{
		return;
	}

	RemoveStaleOwners();

	const int32 SlotIndex = Owner ? FindSlot(Owner, Key) : INDEX_NONE;
	if (SlotIndex != INDEX_NONE)
	{
		RemoveSlot(SlotIndex);
		++Revision;
	}
}

void UMechSentinelObstacleSubsystem::UnregisterObstacles(UObject* Owner)
{
	if (!ensureMsgf(IsInGameThread(), TEXT("UMechSentinelObstacleSubsystem::UnregisterObstacles must run on the game thread")) || NumObstacles == 0)
	{
		return;
	}

	RemoveStaleOwners();

	if (!Owner)
	{
		return;
	}

	bool bRemoved = false;
	for (int32 SlotIndex = 0; SlotIndex < Slots.Num(); ++SlotIndex)
	{
		if (Slots[SlotIndex].bUsed && Slots[SlotIndex].Owner.Get() == Owner)
		{
			RemoveSlot(SlotIndex);
			bRemoved = true;
		}
	}
	if (bRemoved)
	{
		++Revision;
	}
}

bool UMechSentinelObstacleSubsystem::MakeShape(const FMechSentinelObstacle& Obstacle, FMechSentinelObstacleShape& OutShape)
{
	using namespace MechSwarm::ObstaclesPrivate;

	const FBox& Bounds = Obstacle.Bounds;
	if (!Bounds.IsValid || !IsUsablePoint(Bounds.Min) || !IsUsablePoint(Bounds.Max)
		|| Bounds.Min.X > Bounds.Max.X || Bounds.Min.Y > Bounds.Max.Y || Bounds.Min.Z > Bounds.Max.Z)
	{
		return false;
	}

	OutShape = FMechSentinelObstacleShape();
	OutShape.Bounds = Bounds;
	OutShape.Margin = FMath::IsFinite(Obstacle.Margin) ? FMath::Clamp(double(Obstacle.Margin), 0.0, MaxCoordinate) : 0.0;

	if (Obstacle.FootprintRadius > 0.f)
	{
		if (!IsUsableCoordinate(Obstacle.FootprintCenter.X) || !IsUsableCoordinate(Obstacle.FootprintCenter.Y)
			|| !IsUsableCoordinate(double(Obstacle.FootprintRadius)))
		{
			return false;
		}

		OutShape.Center = Obstacle.FootprintCenter;
		OutShape.Radius = double(Obstacle.FootprintRadius);

		// The bounds are the broad phase of the cylinder: they must hold its whole circle
		OutShape.Bounds.Min.X = FMath::Min(OutShape.Bounds.Min.X, OutShape.Center.X - OutShape.Radius);
		OutShape.Bounds.Min.Y = FMath::Min(OutShape.Bounds.Min.Y, OutShape.Center.Y - OutShape.Radius);
		OutShape.Bounds.Max.X = FMath::Max(OutShape.Bounds.Max.X, OutShape.Center.X + OutShape.Radius);
		OutShape.Bounds.Max.Y = FMath::Max(OutShape.Bounds.Max.Y, OutShape.Center.Y + OutShape.Radius);
		if (!IsUsablePoint(OutShape.Bounds.Min) || !IsUsablePoint(OutShape.Bounds.Max))
		{
			return false;
		}
	}
	return true;
}

int32 UMechSentinelObstacleSubsystem::FindSlot(const UObject* Owner, const int32 Key) const
{
	for (int32 SlotIndex = 0; SlotIndex < Slots.Num(); ++SlotIndex)
	{
		const FObstacleSlot& Slot = Slots[SlotIndex];
		if (Slot.bUsed && Slot.Key == Key && Slot.Owner.Get() == Owner)
		{
			return SlotIndex;
		}
	}
	return INDEX_NONE;
}

void UMechSentinelObstacleSubsystem::LinkSlot(const int32 SlotIndex)
{
	using namespace MechSwarm::ObstaclesPrivate;

	FObstacleSlot& Slot = Slots[SlotIndex];

	// Every cell within the reach of the bounds lists the obstacle, so a query only reads its own cell
	const FBox Reach = Slot.Shape.Bounds.ExpandBy(double(ObstacleReach) + Slot.Shape.Margin);
	Slot.CellMin = ToCell(Reach.Min);
	Slot.CellMax = ToCell(Reach.Max);

	const int64 NumCells = int64(Slot.CellMax.X - Slot.CellMin.X + 1)
		* int64(Slot.CellMax.Y - Slot.CellMin.Y + 1)
		* int64(Slot.CellMax.Z - Slot.CellMin.Z + 1);

	Slot.bOversized = NumCells > int64(MaxCellsPerObstacle);
	if (Slot.bOversized)
	{
		OversizedSlots.Add(SlotIndex);
		return;
	}

	for (int32 Z = Slot.CellMin.Z; Z <= Slot.CellMax.Z; ++Z)
	for (int32 Y = Slot.CellMin.Y; Y <= Slot.CellMax.Y; ++Y)
	for (int32 X = Slot.CellMin.X; X <= Slot.CellMax.X; ++X)
	{
		Cells.FindOrAdd(FIntVector(X, Y, Z)).Add(SlotIndex);
	}
}

void UMechSentinelObstacleSubsystem::UnlinkSlot(const int32 SlotIndex)
{
	const FObstacleSlot& Slot = Slots[SlotIndex];

	if (Slot.bOversized)
	{
		const int32 Found = OversizedSlots.Find(SlotIndex);
		if (Found != INDEX_NONE)
		{
			OversizedSlots.RemoveAtSwap(Found, EAllowShrinking::No);
		}
		return;
	}

	for (int32 Z = Slot.CellMin.Z; Z <= Slot.CellMax.Z; ++Z)
	for (int32 Y = Slot.CellMin.Y; Y <= Slot.CellMax.Y; ++Y)
	for (int32 X = Slot.CellMin.X; X <= Slot.CellMax.X; ++X)
	{
		const FIntVector Cell(X, Y, Z);
		TArray<int32>* Entries = Cells.Find(Cell);
		if (!Entries)
		{
			continue;
		}

		const int32 Found = Entries->Find(SlotIndex);
		if (Found != INDEX_NONE)
		{
			Entries->RemoveAtSwap(Found, EAllowShrinking::No);
		}

		// Empty cells go, so the map does not grow as the path moves on
		if (Entries->IsEmpty())
		{
			Cells.Remove(Cell);
		}
	}
}

void UMechSentinelObstacleSubsystem::RemoveSlot(const int32 SlotIndex)
{
	UnlinkSlot(SlotIndex);
	Slots[SlotIndex] = FObstacleSlot();
	FreeSlots.Add(SlotIndex);
	--NumObstacles;
}

int32 UMechSentinelObstacleSubsystem::RemoveStaleOwners()
{
	int32 NumRemoved = 0;
	for (int32 SlotIndex = 0; SlotIndex < Slots.Num(); ++SlotIndex)
	{
		if (Slots[SlotIndex].bUsed && !Slots[SlotIndex].Owner.IsValid())
		{
			RemoveSlot(SlotIndex);
			++NumRemoved;
		}
	}
	if (NumRemoved > 0)
	{
		++Revision;
	}
	return NumRemoved;
}

void UMechSentinelObstacleSubsystem::SweepStaleOwners()
{
	if (NumObstacles == 0)
	{
		return;
	}

	const UWorld* World = GetWorld();
	const double Now = World ? World->GetTimeSeconds() : 0.0;
	if (Now < NextStaleSweepTime)
	{
		return;
	}
	NextStaleSweepTime = Now + MechSwarm::ObstaclesPrivate::StaleSweepInterval;

	if (const int32 NumRemoved = RemoveStaleOwners())
	{
		UE_LOG(LogMechSentinelObstacles, Verbose, TEXT("Removed %d obstacles whose owner is gone without unregistering"), NumRemoved);
	}
}

void UMechSentinelObstacleSubsystem::LogRejected(const UObject* Owner, const TCHAR* Reason)
{
	bool bAlreadyLogged = false;
	RejectedOwners.Add(FObjectKey(Owner), &bAlreadyLogged);
	if (!bAlreadyLogged)
	{
		UE_LOG(LogMechSentinelObstacles, Warning, TEXT("RegisterObstacle from %s ignored: %s. Logged once per owner."), *GetNameSafe(Owner), Reason);
	}
}

//----------------------------------------------------------------------//
// Queries
//----------------------------------------------------------------------//
bool UMechSentinelObstacleSubsystem::IsInsideObstacle(const FVector& Location, const float Inflate) const
{
	using namespace MechSwarm::ObstaclesPrivate;

	if (NumObstacles == 0 || Location.ContainsNaN() || FMath::IsNaN(Inflate))
	{
		return false;
	}

	const auto IsInside = [this, &Location, Inflate](const int32 SlotIndex)
	{
		const FMechSentinelObstacleShape& Shape = Slots[SlotIndex].Shape;
		return Shape.SignedDistance(Location) < double(Inflate) + Shape.Margin;
	};

	// The hash lists every obstacle within ObstacleReach (+ its Margin) of its bounds in the cell of Location
	if (Inflate <= ObstacleReach && IsUsablePoint(Location))
	{
		for (const int32 SlotIndex : GetObstacleCandidates(Location))
		{
			if (IsInside(SlotIndex))
			{
				return true;
			}
		}
		for (const int32 SlotIndex : OversizedSlots)
		{
			if (IsInside(SlotIndex))
			{
				return true;
			}
		}
		return false;
	}

	for (int32 SlotIndex = 0; SlotIndex < Slots.Num(); ++SlotIndex)
	{
		if (Slots[SlotIndex].bUsed && IsInside(SlotIndex))
		{
			return true;
		}
	}
	return false;
}

TConstArrayView<int32> UMechSentinelObstacleSubsystem::GetObstacleCandidates(const FVector& Location) const
{
	using namespace MechSwarm::ObstaclesPrivate;

	if (Cells.IsEmpty() || !IsUsablePoint(Location))
	{
		return TConstArrayView<int32>();
	}
	if (const TArray<int32>* Entries = Cells.Find(ToCell(Location)))
	{
		return *Entries;
	}
	return TConstArrayView<int32>();
}

void UMechSentinelObstacleSubsystem::GetObstacleShapes(TArray<FMechSentinelObstacleShape>& OutShapes, TArray<bool>* OutOversized) const
{
	OutShapes.Reset(NumObstacles);
	if (OutOversized)
	{
		OutOversized->Reset(NumObstacles);
	}

	for (const FObstacleSlot& Slot : Slots)
	{
		if (Slot.bUsed)
		{
			OutShapes.Add(Slot.Shape);
			if (OutOversized)
			{
				OutOversized->Add(Slot.bOversized);
			}
		}
	}
}
