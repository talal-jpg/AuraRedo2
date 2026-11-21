# Hex tile activation API for the Burrower's rotor box

Source read: `Source/Aura/Public/Actors/MyHexPlatform.h` (all), `Source/Aura/Private/Actors/MyHexPlatform.cpp` (all of the
activation, grid, tile info, props and lead code; the paving section 2599-4588 only skimmed, it doesn't touch activation),
`MyHexBridgeSubsystem.cpp` (registration, InitPlatformEntry, IsPlatformCollapsing, edges), `MyHexBridge.cpp` (tile
collapse binding), `MyHexMinimapSubsystem.cpp` (tile collapse binding), `MyHexBridgeBuilder.cpp` (edges),
`MyHexPillarBreakSubsystem.h` (break budget), `MyGameState.cpp` (lead activation).
Line numbers below are for the clone at `/home/claude/AuraRedo2` as it is now.

No engine headers are in this container. Every engine API used below is an old, stable one (FTransform, FBox, FVector,
UWorld::OverlapMultiByObjectType, FOverlapResult::GetActor / GetComponent, which the project already uses in
GA_Electrocute.cpp / GA_Shards.cpp with `#include "Engine/OverlapResult.h"`).

---

## 1. How a tile is activated today (server)

| Step | Where | What it does |
|---|---|---|
| Gate | `BeginPlay` 275-307, `NotifyBridgesReady` 414, `NotifyLeadLanded` 425, `TryStartCollapsing` 437 | `bBridgesReady` (set by UMyHexBridgeSubsystem after the platform's batch is planned, or in BeginPlay when there is no subsystem / `bWaitForBridgesBeforeCollapsing` is off) and `bLeadLanded` (AMyGameState calls NotifyLeadLanded on every platform with `SplineDistance <= lead`, or the lead stands on a platform with no SplineDistance). Both true (or `!bCollapseOnlyWhenLeadLands`) -> `StartCollapsing`. |
| Start | `StartCollapsing` 345 | Once (`bCollapseStarted`), `FreezePath()`, first chain after `FirstCollapseDelay` (or `SmallPlatformFirstCollapseDelay` for <= 15 tiles). |
| Chains | `ScheduleNextCollapseChain` 366, `CollapseNextChain` 377, `GetCollapseInterval` 389 | One-shot timer re-armed after every chain; interval lerps from 5 s (at the lead) to 1.5 s (far behind). Stops when `HexMap` is empty. |
| Pick | `GenerateAndActivateChainFromRandomSelectedGrid` 1543, `GenerateChain` 1477, `GetNeighbors` 1436 | Random start among live tiles not in `PendingActivationTiles`, random walk of up to 15 live, unreserved neighbours; <= 15 tiles left = all of them. The chain is added to `PendingActivationTiles` (server only, not replicated). |
| Stagger | `ActivateChain` 1639 | First tile now, tile i after `i * 0.1 s` (weak-lambda timers calling `ActivateHex`). |
| Activate | `ActivateHex` 1685 | Authority; returns if already in `LocalActivatedTiles` or not in `HexMap`; `ActivatedTiles.Add(Coord)` (replicated); `ActivateHexLocal(Coord)`; `PendingActivationTiles.Remove(Coord)`. |
| Local | `ActivateHexLocal` 1765 | Reads the instance's world transform and custom data, `RemoveHexInstance` (ISM uses `SetRemoveSwap`, so the last instance moves into the hole; `HexMap` / `InstanceToHex` are repaired, 2046-2106), adds to `LocalActivatedTiles`, plays the far break or queues the Geometry Collection break (UMyHexPillarBreakSubsystem) or the skeletal fall, and broadcasts `OnHexTileActivated`. |

Replication: only `ActivatedTiles` (TArray<FIntVector>, append only, `ReplicatedUsing = OnRep_ActivatedTiles`) carries
the activation state. Clients run `ApplyActivatedTiles(true)` -> `ActivateHexLocal` for every coord they haven't done
(`LocalActivatedTiles` is per machine). Late joiners: the initial bunch arrives before BeginPlay builds the grid, so
`BeginPlay` calls `ApplyActivatedTiles(false)` (tiles removed without effects). The platform is `bAlwaysRelevant`.
`PendingActivationTiles`, `bCollapseStarted`, `bBridgesReady` and `bLeadLanded` are server only.

Who listens to `OnHexTileActivated` (every machine): the platform itself (`HandleTileActivated` 4774: removes the tile
from `TileInfos`, drops a pending prop regeneration, breaks the tile's props near / far / remove-only), every bridge
ending on the platform (`AMyHexBridge::OnPlatformTileActivated` MyHexBridge.cpp 251 -> `NotifyEndTileCollapsed` -> the
bridge collapses or is destroyed), and the minimap (`UMyHexMinimapSubsystem::OnTileActivated` 249: clears the cell).

## 2. Activating a tile outside the normal collapse flow

`ActivateHex` is self-contained and already used without chains: `DebugBreakTiles(0)` (2231, console
`Aura.BreakTopPlatform 0`) calls it on every tile. Nothing downstream assumes chains:

* Chains read `HexMap` and `PendingActivationTiles` live, so holes are fine. A tile that a running chain has reserved
  and the rotor takes first: `ActivateHex` removes it from `PendingActivationTiles`; the chain's later timer calls
  `ActivateHex` again, which returns at the `LocalActivatedTiles` check. Safe.
* `CollapseNextChain` stops when `HexMap` is empty, so a platform the rotor emptied stops its own timer.
* Props, bridges and minimap react through `OnHexTileActivated` on every machine, whoever called `ActivateHex`.
  The first fallen tile freezes the props (`AreTilePropsFrozen` checks `LocalActivatedTiles`), same as a chain.
* Bridges: an end tile cut by the rotor collapses that bridge (players on it fall). Its walkway stays
  (`UnregisterPathBridge` -> `RetainedPathStarts`). Culling ("bridges holding a platform alive", `IsAnyPlayerOnPlatform`)
  only looks at players and bridges, not tiles, so it is unaffected.
* AMyGameState / lead: ranks players by the SplineDistance of the platform they landed on; nothing counts tiles.
  Rotor activations don't call `StartCollapsing` or `NotifyLeadLanded`, so a bitten platform keeps its own gate.
* Bottom vs top platforms: same code path; only the break assets differ. The API handles both; the burrower can
  filter with `IsBottomPlatform()` if it should cut only one chain.

**One real hazard: tiles must not fall before the bridges are planned.** `UMyHexBridgeSubsystem::InitPlatformEntry`
(MyHexBridgeSubsystem.cpp 5018, comment "Nothing has collapsed yet, so the cached EdgeInstances indices are valid")
reads `Platform.EdgeInstances` (instance index -> missing neighbours, cached at the end of `BuildHexGrid`) through
`InstanceToHex`. A removal swaps the last instance into the hole, so after one fallen tile the cached indices point at
other tiles: edges would be attributed to the wrong tiles and bridges built from wrong spots. Platforms register in
BeginPlay and are planned within `MaxBuildDelay` (0.5 s), then get `NotifyBridgesReady`. The new API therefore does
nothing until `bBridgesReady` (the same gate the normal collapse waits for). With `bWaitForBridgesBeforeCollapsing`
off, `bBridgesReady` is set in BeginPlay and the race is open, exactly as it already is for the normal collapse.
(AMyHexBridgeBuilder, the debug/editor bridge builder, also reads the cached EdgeInstances; existing behaviour.)

Other side effects worth knowing:
* `UMyHexBridgeSubsystem::IsPlatformCollapsing` is `bCollapseStarted && ...`, so a platform with rotor holes that
  hasn't started collapsing can still be paired by later bridge batches; they use live edges only (`LiveEdges` skips
  collapsed edge tiles, `DeadTiles` marks fallen tiles). Acceptable.
* Break budget: `TopPillarBreak.MaxSpawnsPerFrame = 2`, `MaxQueueTime = 0.5 s` (shared by top and bottom). A rotor
  check takes a handful of tiles, so the queue keeps up; a break older than 0.5 s is dropped (tile just vanishes).
  Effects only play near the local player (`BreakEffectsMaxDistance` 50 m, far breaks to 200 m), so a rotor far from
  everyone costs only the instance removal and the replicated coord.
* `ActivatedTiles` grows by one FIntVector per tile, max 331 per platform at GridSize 10 (well under
  `net.MaxRepArraySize` 2048).
* Without Geometry Collections set, the fallback skeletal-mesh fall pillar is QueryAndPhysics and blocks every
  channel (object type: the USkeletalMeshComponent default), so it can stop a burrower capsule that blocks that type.
  The GC pieces don't block pawns (`bBlocksPawns` false).

## 3. Tile geometry: spaces and bounds

* `HexPillarsISM` is the root component, so ISM component space = actor space. `AddHexInstance` adds instances
  relative to the component.
* Instances: location `(HexToWorld(Q, R), 0)`, yaw `-60 * OutwardSide` (pillar +X towards the outline), scale
  `(HexRadius/100, HexRadius/100, Z)` with per-tile Z on top platforms and one Z (`HexRadius/100 * HexPillarBottomScaleZ`)
  on bottom ones. Pivot at the top of the pillar (the mesh hangs below).
* `FHexTileInfo` (built once in `BuildTileInfos` 2401, removed from `TileInfos` when the tile falls, on every machine):
  * `LocalBounds`: the mesh bounding box through the instance transform **with the rotation removed**. The pillar is a
    regular hexagon with flat sides on +-X, so its 60 degree turns cover the same ground; the box is X +-apothem,
    Y +-circumradius, Z = full pillar height. Actor space.
  * `LocalTopCenter`: `(instance X, instance Y, LocalBounds.Max.Z)`. Actor space.
  * `Apothem`: mesh X half size times the instance X scale (actor space cm, same on every tile of a platform).
* `HexMap` (coord -> current instance index) and `InstanceToHex` (index -> coord) are live; indices change on every
  removal, so never cache an instance index. Use coords.
* To world: `HexPillarsISM->GetComponentTransform()` (= actor transform). A tile's world OBB from its AABB: centre
  `T.TransformPosition(LocalBounds.GetCenter())`, axes `T.GetUnitAxis(X/Y/Z)`, half sizes
  `LocalBounds.GetExtent() * T.GetScale3D().GetAbs()` (exact even with non-uniform actor scale, because the box is
  axis-aligned in actor space). Instance world transform: `HexPillarsISM->GetInstanceTransform(HexMap[Coord], Out, true)`.
* On the server `TileInfos` keys == `HexMap` keys (both built in BeginPlay, both lose a tile in the same
  `ActivateHexLocal` call).

## 4. Collision: one overlap query to find candidate platforms

* C++ (constructor, MyHexPlatform.cpp 73-79): `HexPillarsISM` is `QueryAndPhysics` and blocks **every channel**.
  Its object type is not set in C++, so it is the one from UStaticMeshComponent's default profile `BlockAll`:
  **WorldStatic**. No custom channels or profiles exist in Config/DefaultEngine.ini.
  The Blueprints (BP_MyHexPlatform, BP_MyHexPlatformBottom) are LFS pointers here, so a Blueprint override of the
  component's collision cannot be ruled out: check HexPillarsISM > Collision in both Blueprints on the user's machine.
* An ISM has one physics body per instance, so `OverlapMultiByObjectType` with a box finds the platform as soon as the
  box touches any pillar's collision, through the physics acceleration structure, without iterating actors. The
  result's `GetComponent()` is the ISM (the platform's root) and `ItemIndex` the instance index (not needed here).
* Filter results by `Cast<AMyHexPlatform>(Overlap.GetActor())` **and** `Overlap.GetComponent() == Platform->GetRootComponent()`:
  the platform also owns its PCG prop ISMs, falling skeletal pillars and Geometry Collection pieces.
* Query on WorldStatic + WorldDynamic object types (covers a Blueprint that switched it), ignore the burrower itself.
* The tile collision may be a little smaller than the mesh bounds the exact test uses, so give the query box a small
  margin (10-25 cm). The query only finds candidates; the exact test in the platform decides.
* Don't use overlap events for this: the RotorBox rides on a moving skeletal mesh, so `bGenerateOverlapEvents` would
  run `UpdateOverlaps` against the tile bodies on every move. The RotorBox can be `NoCollision` (or QueryOnly, ignore
  all, no overlap events) because the burrower queries with its transform and extent explicitly.

## 5. The test: why an exact hex-prism separating-axis test

The pillar is a hexagonal prism; the rotor box is an oriented box. Testing the pillar's AABB (`LocalBounds`) over-reaches
at the hexagon's corners by up to 0.43 x circumradius (43 cm at HexRadius 100), on top of the box padding. The exact
test costs the same:

* Both shapes are **zonotopes** (sums of line segments): the box is the sum of its three half axes; a regular hexagon
  is the sum of three segments one side long, one parallel to each pair of opposite sides, and the prism adds its height.
  Two zonotopes are apart exactly when the cross product of some two of their segments separates them, so testing
  the cross products of every pair of the 7 segment directions (21 axes at most) is exact, not conservative.
* Done in the platform's actor space, where every pillar is axis aligned and shares the same side directions: the axes
  and the box's reach along them are computed once per call; per tile only the centre offset and the tile's half
  height change. The box goes into actor space exactly with `InverseTransformPosition` / `InverseTransformVector` (with
  a non-uniform actor scale it becomes a parallelepiped, still three segments, still exact).
* Per tile: an AABB reject against `LocalBounds` (6 compares), then at most 21 dot products. A platform has at most 331
  tiles. Negligible at 20 Hz.
* Touching counts as overlapping. Directions within ~0.006 degrees of parallel are skipped (their face is a sliver);
  that can only report a touch up to a fraction of a mm early.
* Checked in Python against an independent polyhedron separating-axis test (vertex projections on all face normals and
  edge cross products): 24,000 random boxes (rotated, yaw only, axis aligned, and sheared by a non-uniform frame
  scale), 0 disagreements. In a sample of boxes near a tile's corners about a fifth of the AABB hits missed the actual
  hexagon. Script: `/tmp/claude-0/-home-claude/90ee2597-e224-5d35-9bdb-c168adc8483b/scratchpad/ue/hexsat/test.py`.

Assumption: HexPillar and HexPillarBottom are regular hexagons, flat sides on +-X, centred on the pivot in XY (BuildHexGrid
and `FHexTileInfo::Apothem` already assume this; the grid wouldn't tile otherwise).

Decision on tiles a chain has already reserved (`PendingActivationTiles`, will fall within 1.4 s): **they go now**
(the user asked for activation "as soon as" the box overlaps a tile; otherwise the rotor would visibly pass through
standing pillars). Tiles that already fell are skipped (they are no longer in `TileInfos` / `HexMap`). To skip
reserved tiles instead, add `|| PendingActivationTiles.Contains(Coord)` to the `continue` in the activation loop.

## 6. Code

### 6.1 Header (`Source/Aura/Public/Actors/MyHexPlatform.h`)

Public, after `void DebugBreakTiles(int32 NumChains);` (line 260):

```cpp
	/**
	 * Server. Collapses now every standing tile whose pillar touches the box, through ActivateHex like the
	 * platform's own chains, so it replicates and the props, bridges and minimap follow. BoxExtent is the box's
	 * half size in world cm (a UBoxComponent's GetScaledBoxExtent); only BoxToWorld's location and rotation are
	 * used. Tiles a running chain has reserved go now too. Does nothing until the bridges are built (they are
	 * planned from the untouched edges). Returns how many tiles it collapsed.
	 */
	int32 ActivateTilesInWorldBox(const FTransform& BoxToWorld, const FVector& BoxExtent);

	/**
	 * Cheap test: false when the box can't touch any tile (the bounds of the grid as built). ActivateTilesInWorldBox
	 * does it first itself. Any machine.
	 */
	bool CouldWorldBoxTouchTiles(const FTransform& BoxToWorld, const FVector& BoxExtent) const;
```

Private, after `TMap<FIntVector, FHexTileInfo> TileInfos;` (line 1200):

```cpp
	/** Every tile's LocalBounds together, as built (BuildTileInfos). Doesn't shrink as tiles fall. */
	FBox TilesLocalBounds = FBox(ForceInit);
```

### 6.2 `BuildTileInfos` (MyHexPlatform.cpp 2401): two added lines

```cpp
void AMyHexPlatform::BuildTileInfos()
{
	TileInfos.Reset();
	TilesLocalBounds = FBox(ForceInit);                       // added

	...
		Info.LocalBounds = Box;
		TilesLocalBounds += Box;                              // added
		Info.Apothem = static_cast<float>(MeshBox.GetExtent().X * InstanceTransform.GetScale3D().X);
	...
```

### 6.3 New section in MyHexPlatform.cpp

Insert after `IsTileCollapsed` (ends at line 2263), before `// GetEdges`. No new includes (CoreMinimal covers FBox,
FTransform, EAxis; the ISM header comes through MyHexPlatform.h).

```cpp
// =============================================================================
// Activation by a box (server; the Burrower's rotor)
// =============================================================================

// Named, not anonymous: the unity build compiles this file together with others
namespace HexBoxTest
{
	/** A world box in the platform's actor space (a parallelepiped there when the actor has a non-uniform scale). */
	struct FBoxInActorSpace
	{
		FVector Centre = FVector::ZeroVector;

		/** Centre to the middle of each face, one per box axis. */
		FVector HalfAxes[3] = { FVector::ZeroVector, FVector::ZeroVector, FVector::ZeroVector };

		/** Exact axis-aligned bounds of it. */
		FBox Bounds = FBox(ForceInit);
	};

	/** A candidate separating axis: the box's reach along it, and a pillar's per cm of half side and of half height. */
	struct FAxis
	{
		FVector Dir = FVector::ZeroVector;
		double BoxReach = 0.0;
		double SideReach = 0.0;
		double UpReach = 0.0;
	};

	using FAxes = TArray<FAxis, TInlineAllocator<21>>;

	static FBoxInActorSpace ToActorSpace(const FTransform& ActorToWorld, const FTransform& BoxToWorld, const FVector& BoxExtent)
	{
		static const EAxis::Type BoxAxes[3] = { EAxis::X, EAxis::Y, EAxis::Z };

		FBoxInActorSpace Box;
		Box.Centre = ActorToWorld.InverseTransformPosition(BoxToWorld.GetLocation());

		FVector Reach = FVector::ZeroVector;

		for (int32 Axis = 0; Axis < 3; ++Axis)
		{
			// Undoes the actor's rotation and scale, so it is exact whatever the actor transform
			Box.HalfAxes[Axis] = ActorToWorld.InverseTransformVector(BoxToWorld.GetUnitAxis(BoxAxes[Axis]) * FMath::Abs(BoxExtent[Axis]));
			Reach += Box.HalfAxes[Axis].GetAbs();
		}

		Box.Bounds = FBox(Box.Centre - Reach, Box.Centre + Reach);
		return Box;
	}

	/**
	 * Separating axes of the box against this platform's pillars. Both are sums of segments: the box of its three
	 * half axes, a pillar of its height and of three horizontal segments, one along each pair of opposite sides
	 * (a regular hexagon is the sum of three segments one side long). Two such shapes are apart exactly when the
	 * cross product of some two of their segments separates them, so these are all the axes needed (21 at most).
	 * Every pillar of a platform has the same directions; only the lengths differ.
	 */
	static void MakeAxes(const FBoxInActorSpace& Box, FAxes& OutAxes)
	{
		FVector Dirs[7];
		int32 NumDirs = 0;

		// The pillar: along each pair of opposite sides (the side's outward direction turned 90 degrees), then up
		for (int32 Side = 0; Side < 3; ++Side)
		{
			const FVector2D Out = AMyHexPlatform::GetHexSideDirection(Side);
			Dirs[NumDirs++] = FVector(-Out.Y, Out.X, 0.0);
		}

		Dirs[NumDirs++] = FVector::UpVector;

		// The box (a zero extent adds nothing)
		for (const FVector& HalfAxis : Box.HalfAxes)
		{
			if (!HalfAxis.IsNearlyZero())
			{
				Dirs[NumDirs++] = HalfAxis.GetUnsafeNormal();
			}
		}

		for (int32 A = 0; A < NumDirs; ++A)
		{
			for (int32 B = A + 1; B < NumDirs; ++B)
			{
				const FVector Dir = FVector::CrossProduct(Dirs[A], Dirs[B]);

				// Parallel: no face between them
				if (Dir.SizeSquared() < 1.e-8)
				{
					continue;
				}

				FAxis& Axis = OutAxes.AddDefaulted_GetRef();
				Axis.Dir = Dir;
				Axis.UpReach = FMath::Abs(Dir.Z);

				for (int32 Side = 0; Side < 3; ++Side)
				{
					Axis.SideReach += FMath::Abs(FVector::DotProduct(Dir, Dirs[Side]));
				}

				for (const FVector& HalfAxis : Box.HalfAxes)
				{
					Axis.BoxReach += FMath::Abs(FVector::DotProduct(Dir, HalfAxis));
				}
			}
		}
	}

	/** Does the box touch the tile's pillar: a regular hexagon of Info.Apothem, as tall as Info.LocalBounds? */
	static bool TouchesPillar(const FAxes& Axes, const FBoxInActorSpace& Box, const FHexTileInfo& Info)
	{
		const FVector Offset = Box.Centre - Info.LocalBounds.GetCenter();

		// A side is 2 * Apothem / sqrt 3 long; each segment reaches half of it either way
		const double HalfSide = Info.Apothem / FMath::Sqrt(3.0);
		const double HalfHeight = Info.LocalBounds.GetExtent().Z;

		for (const FAxis& Axis : Axes)
		{
			if (FMath::Abs(FVector::DotProduct(Axis.Dir, Offset)) > Axis.BoxReach + HalfSide * Axis.SideReach + HalfHeight * Axis.UpReach)
			{
				return false;
			}
		}

		return true;
	}
}

int32 AMyHexPlatform::ActivateTilesInWorldBox(const FTransform& BoxToWorld, const FVector& BoxExtent)
{
	// Server only. Not before the bridges are built: UMyHexBridgeSubsystem reads the edges through the instance
	// indices BuildHexGrid cached (EdgeInstances), and a removed tile reorders them.
	if (!HasAuthority() || !bBridgesReady || IsActorBeingDestroyed() || !HexPillarsISM || TileInfos.IsEmpty())
	{
		return 0;
	}

	const HexBoxTest::FBoxInActorSpace Box = HexBoxTest::ToActorSpace(HexPillarsISM->GetComponentTransform(), BoxToWorld, BoxExtent);

	if (!Box.Bounds.Intersect(TilesLocalBounds))
	{
		return 0;
	}

	HexBoxTest::FAxes Axes;
	HexBoxTest::MakeAxes(Box, Axes);

	// Gathered first: ActivateHex takes the tile out of TileInfos (HandleTileActivated) and HexMap
	TArray<FIntVector, TInlineAllocator<16>> Touched;

	for (const TPair<FIntVector, FHexTileInfo>& Pair : TileInfos)
	{
		if (Pair.Value.LocalBounds.Intersect(Box.Bounds) && HexBoxTest::TouchesPillar(Axes, Box, Pair.Value))
		{
			Touched.Add(Pair.Key);
		}
	}

	int32 NumActivated = 0;

	for (const FIntVector& Coord : Touched)
	{
		// A tile a chain has reserved goes now; the chain's timer then finds it gone
		if (LocalActivatedTiles.Contains(Coord))
		{
			continue;
		}

		ActivateHex(Coord);

		if (LocalActivatedTiles.Contains(Coord))
		{
			++NumActivated;
		}
	}

	return NumActivated;
}

bool AMyHexPlatform::CouldWorldBoxTouchTiles(const FTransform& BoxToWorld, const FVector& BoxExtent) const
{
	if (!HexPillarsISM || TileInfos.IsEmpty())
	{
		return false;
	}

	return HexBoxTest::ToActorSpace(HexPillarsISM->GetComponentTransform(), BoxToWorld, BoxExtent).Bounds.Intersect(TilesLocalBounds);
}
```

Notes on the code:
* `TileInfos.IsEmpty()` is the "nothing standing" test and also guarantees `TilesLocalBounds` was filled (avoids
  touching `FBox::IsValid`).
* Success is counted through `LocalActivatedTiles`, which `ActivateHexLocal` only adds to after the instance is
  removed (`ActivateHex` returns void).
* `ActivateHex` stays protected; the new methods are members, so no access change. `GetHexSideDirection` and
  `FHexTileInfo` are public, so the free helpers can use them.

### 6.4 Burrower side (server, every RotorCheckInterval)

Includes: `Engine/OverlapResult.h`, `Engine/World.h`, `CollisionQueryParams.h`, `Components/BoxComponent.h`,
`Actors/MyHexPlatform.h`.

```cpp
void ABurrowerCharacter::CheckRotorTiles()
{
	if (!HasAuthority() || !RotorBox)
	{
		return;
	}

	const FTransform BoxToWorld = RotorBox->GetComponentTransform();
	const FVector Extent = RotorBox->GetScaledBoxExtent();

	// The tiles are WorldStatic and block everything; WorldDynamic too in case a platform Blueprint changed it
	FCollisionObjectQueryParams ObjectParams;
	ObjectParams.AddObjectTypesToQuery(ECC_WorldStatic);
	ObjectParams.AddObjectTypesToQuery(ECC_WorldDynamic);

	FCollisionQueryParams Params(SCENE_QUERY_STAT(BurrowerRotorTiles), /*bTraceComplex=*/false, this);

	// A little bigger than the box: the tile collision may sit inside the mesh bounds the exact test uses
	TArray<FOverlapResult> Overlaps;
	GetWorld()->OverlapMultiByObjectType(Overlaps, BoxToWorld.GetLocation(), BoxToWorld.GetRotation(), ObjectParams,
		FCollisionShape::MakeBox(Extent + FVector(RotorQueryMargin)), Params);

	TArray<AMyHexPlatform*, TInlineAllocator<4>> Platforms;

	for (const FOverlapResult& Overlap : Overlaps)
	{
		AMyHexPlatform* Platform = Cast<AMyHexPlatform>(Overlap.GetActor());

		// The tile ISM is the platform's root; skip its props, falling pillars and debris
		if (Platform && Overlap.GetComponent() == Platform->GetRootComponent())
		{
			Platforms.AddUnique(Platform);
		}
	}

	for (AMyHexPlatform* Platform : Platforms)
	{
		Platform->ActivateTilesInWorldBox(BoxToWorld, Extent);
	}
}
```

(`RotorQueryMargin`: a float UPROPERTY, e.g. 25 cm.) No platform pointers are kept between checks, so platforms
culled by `bAutoDestroyWhenLeftBehind` are never a problem. Without physics (or for a debug path), the same can be
done with `TActorIterator<AMyHexPlatform>` + `CouldWorldBoxTouchTiles`.

Speed: the box can't skip a tile while `speed * RotorCheckInterval < 2 * Extent.X` (rotor 38 cm deep + 2 x 50 cm
padding = 138 cm -> up to ~27 m/s at 0.05 s). For faster, stretch the box back along its X over the distance moved
since the last check (centre moved back by half of it, `Extent.X` grown by half of it) for both calls.

## 7. Notes for the Burrower author (outside this API, but they decide whether it works)

1. **RotorBox on a skeletal bone is stale on the server.** ACharacter's mesh uses `AlwaysTickPose`, which only
   refreshes bone transforms when rendered. On a dedicated server (and a listen server that isn't looking at the
   burrower) a component attached to bone `Rotor` stays at the last refreshed pose; on a host that sees it, it spins
   and sways with the Control Rig. For a deterministic gameplay box, attach RotorBox to the mesh with no socket at the
   rotor's reference-pose centre (980, 0, 180.5) cm, or attach to the socket and set the mesh to
   `AlwaysTickPoseAndRefreshBones` on the server (costs the full pose every frame). The rotor bone is parented to
   root, so its reference pose doesn't follow the head wave anyway; the padding covers the sway.
2. The burrower's capsule should not be blocked by the tiles (it cuts through them): ignore or overlap WorldStatic
   (and the skeletal fall pillars' object type, if Geometry Collections aren't set).
3. RotorBox collision: `NoCollision` or QueryOnly without overlap events (see section 4).
