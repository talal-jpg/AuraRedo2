// Mech Sentinel Swarm - obstacle registry: 3D level geometry (hex platforms, boxes) that live sentinels steer around.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "UObject/ObjectKey.h"
#include "MechSentinelObstacleSubsystem.generated.h"

/** One obstacle as registered: a vertical capped cylinder (hex platforms) or a box (generic geometry). World space. */
USTRUCT(BlueprintType)
struct AURA_API FMechSentinelObstacle
{
	GENERATED_BODY()

	/** World AABB. With FootprintRadius > 0 it bounds a vertical capped cylinder (the real shape); else it is the shape. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Obstacle")
	FBox Bounds = FBox(ForceInit);

	/** Cylinder axis (world XY), used when FootprintRadius > 0. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Obstacle")
	FVector2D FootprintCenter = FVector2D::ZeroVector;

	/** > 0: the shape is a vertical cylinder of this radius around FootprintCenter, capped at Bounds.Min.Z / Bounds.Max.Z. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Obstacle", meta = (ClampMin = "0", ForceUnits = "cm"))
	float FootprintRadius = 0.f;

	/** Extra clearance (cm) for this obstacle only. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Obstacle", meta = (ClampMin = "0", ForceUnits = "cm"))
	float Margin = 0.f;
};

/**
 * A registered obstacle as the avoidance reads it, after validation: a cylinder's Bounds are grown in XY to hold its
 * whole circle. Distances in cm, normals point out of the shape.
 */
struct AURA_API FMechSentinelObstacleShape
{
	/** World AABB: the broad phase, and the shape itself when Radius is 0. */
	FBox Bounds = FBox(ForceInit);

	/** Cylinder axis (world XY). */
	FVector2D Center = FVector2D::ZeroVector;

	/** > 0: vertical capped cylinder over [Bounds.Min.Z, Bounds.Max.Z]. 0: the box. */
	double Radius = 0.0;

	/** Extra clearance (cm) for this obstacle only. */
	double Margin = 0.0;

	bool IsCylinder() const { return Radius > 0.0; }

	/** Signed distance from P to the surface, negative inside. */
	double SignedDistance(const FVector& P) const;

	/**
	 * Distance from P to the surface and the outward normal there (zero when P is on the surface). Inside, the result is
	 * minus the depth of the cheapest exit (radial / caps, or the six box faces); the exit whose normal faces GoalDir best
	 * has its depth scaled by ExitFaceBias first, so sentinels prefer to leave on the side of their goal.
	 */
	double Closest(const FVector& P, const FVector& GoalDir, double ExitFaceBias, FVector& OutNormal) const;

	/**
	 * Ray P + t * Dir (Dir unit length), t in [0, MaxDistance], against the shape grown sharply by Inflate: a cylinder of
	 * radius Radius + Inflate over [MinZ - Inflate, MaxZ + Inflate], or the box expanded by Inflate. False on a miss.
	 * A start inside the grown shape hits at t = 0 with bOutInside set and no normal.
	 */
	bool Raycast(const FVector& P, const FVector& Dir, double MaxDistance, double Inflate, double& OutT, FVector& OutNormal, bool& bOutInside) const;

	/** Is P (XY) over the footprint grown by Inflate: the circle, or the box's XY rectangle. */
	bool IsOverFootprint(const FVector& P, double Inflate) const;
};

/**
 * World subsystem holding the obstacles live sentinels avoid (UMechSentinelObstacleAvoidanceProcessor).
 *
 *  - Hex platforms register their tiles as a cylinder (AMyHexPlatform::RefreshSentinelObstacle); other geometry uses
 *    UMechSentinelObstacleComponent (a box) or RegisterObstacle from Blueprint.
 *  - Server only: registering is a no-op on network clients (the avoidance runs on the authority).
 *  - Game thread only. A spatial hash of ObstacleCellSize cells lists every obstacle in each cell that lies within
 *    ObstacleReach (+ its Margin) of its bounds; obstacles touching more than MaxCellsPerObstacle cells go to an
 *    oversized list that every query tests.
 *  - Owners are held weakly: obstacles of destroyed owners are swept on each registration and once per second.
 */
UCLASS()
class AURA_API UMechSentinelObstacleSubsystem : public UWorldSubsystem
{
	GENERATED_BODY()

public:
	/** Spatial hash cell size (cm). */
	static constexpr float ObstacleCellSize = 4000.f;

	/**
	 * Distance (cm) from an obstacle's bounds (plus its Margin) within which a query finds it. The avoidance needs the
	 * sentinel radius + soft margin + look-ahead (140 + 250 + 1600 by default); it shortens its look-ahead to stay inside.
	 */
	static constexpr float ObstacleReach = 2000.f;

	/** Obstacles touching more cells than this are not hashed but tested by every query. */
	static constexpr int32 MaxCellsPerObstacle = 512;

	/** Null outside game / PIE worlds. */
	static UMechSentinelObstacleSubsystem* Get(const UObject* WorldContextObject);

	//~ USubsystem
	virtual void Deinitialize() override;

	/** True where obstacles are registered and avoided: standalone, listen and dedicated servers. */
	bool HasAuthority() const;

	/**
	 * Adds an obstacle. The same Owner and Key replace the previous one. An invalid obstacle (no or non-finite bounds,
	 * coordinates beyond 1e9) is rejected, and the one it would replace is removed. No-op on clients. Game thread.
	 */
	UFUNCTION(BlueprintCallable, Category = "Mech Sentinels|Obstacles", meta = (DefaultToSelf = "Owner"))
	void RegisterObstacle(UObject* Owner, const FMechSentinelObstacle& Obstacle, int32 Key = 0);

	/** Removes Owner's obstacle with this Key. */
	UFUNCTION(BlueprintCallable, Category = "Mech Sentinels|Obstacles", meta = (DefaultToSelf = "Owner"))
	void UnregisterObstacle(UObject* Owner, int32 Key = 0);

	/** Removes every obstacle of Owner. */
	UFUNCTION(BlueprintCallable, Category = "Mech Sentinels|Obstacles", meta = (DefaultToSelf = "Owner"))
	void UnregisterObstacles(UObject* Owner);

	UFUNCTION(BlueprintPure, Category = "Mech Sentinels|Obstacles")
	int32 GetNumObstacles() const { return NumObstacles; }

	/** True when Location is inside any registered obstacle grown by Inflate (cm) plus that obstacle's Margin. Game thread. */
	bool IsInsideObstacle(const FVector& Location, float Inflate) const;

	//----------------------------------------------------------------------//
	// Queries for the avoidance (game thread; the views stay valid until the next (un)registration)
	//----------------------------------------------------------------------//

	/**
	 * Hashed obstacles that may lie within ObstacleReach (+ their Margin) of Location: the slots listed in Location's
	 * cell. Empty when nothing is near, or Location is NaN or beyond 1e9. Test GetOversizedObstacles() as well.
	 */
	TConstArrayView<int32> GetObstacleCandidates(const FVector& Location) const;

	/** Obstacles too large for the hash: every query tests them. */
	TConstArrayView<int32> GetOversizedObstacles() const { return OversizedSlots; }

	/** The shape in a slot listed by the two views above. */
	const FMechSentinelObstacleShape& GetObstacleShape(const int32 SlotIndex) const { return Slots[SlotIndex].Shape; }

	/** Changes on every registration change. */
	uint32 GetObstacleRevision() const { return Revision; }

	/** Copies of every registered shape (debug drawing). bOutOversized (optional) is index-aligned with OutShapes. */
	void GetObstacleShapes(TArray<FMechSentinelObstacleShape>& OutShapes, TArray<bool>* OutOversized = nullptr) const;

	/** Drops obstacles whose owner is gone without unregistering. Called every frame by the avoidance; works once per second. */
	void SweepStaleOwners();

protected:
	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;

	struct FObstacleSlot
	{
		TWeakObjectPtr<UObject> Owner;
		FMechSentinelObstacleShape Shape;
		FIntVector CellMin = FIntVector::ZeroValue;
		FIntVector CellMax = FIntVector::ZeroValue;
		int32 Key = 0;
		bool bUsed = false;
		bool bOversized = false;
	};

	/** Validates Obstacle and fills Shape (cylinder bounds grown to hold the circle). False when it is unusable. */
	static bool MakeShape(const FMechSentinelObstacle& Obstacle, FMechSentinelObstacleShape& OutShape);

	int32 FindSlot(const UObject* Owner, int32 Key) const;

	/** Adds a used slot to its cells (or the oversized list). */
	void LinkSlot(int32 SlotIndex);

	/** Takes a used slot out of its cells (or the oversized list). */
	void UnlinkSlot(int32 SlotIndex);

	/** Unlinks and frees a used slot. */
	void RemoveSlot(int32 SlotIndex);

	/** Removes the obstacles of owners that are gone. Returns how many. */
	int32 RemoveStaleOwners();

	/** Logs a rejected registration, once per owner. */
	void LogRejected(const UObject* Owner, const TCHAR* Reason);

	TArray<FObstacleSlot> Slots;
	TArray<int32> FreeSlots;
	TMap<FIntVector, TArray<int32>> Cells;
	TArray<int32> OversizedSlots;
	TSet<FObjectKey> RejectedOwners;
	int32 NumObstacles = 0;
	uint32 Revision = 0;
	double NextStaleSweepTime = 0.0;
};
