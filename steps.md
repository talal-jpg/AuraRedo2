# Hex Path and Bridges: Setup Steps

Here's the setup, in the order to do it. Names like `BP_HexBridge` are suggestions; call them what you like.

## 1. Clean up the level
- Delete any `MyHexBridgeBuilder` actors from the level. If you leave them, you get two sets of bridges.
- Platforms you placed by hand can stay. They register with the bridge subsystem and get bridged too.

## 2. Platform Blueprint
Use your existing platform Blueprint, or make one: **`BP_HexPlatform`**, parent class **`MyHexPlatform`**.
- **Assets:** set `HexPillarStaticMesh`, `HexPillarSkeletalMesh`, `RbdAnimSeq` and `NoiseCurve` as you have now.
- **Grid:** set `GridSize`, `HexRadius` and the rest of the outline settings. Note the platform's rough size: about `1.7 × GridSize × HexRadius` from its centre to the edge of the grid.
- **Bridges:** leave `bWaitForBridgesBeforeCollapsing` **on**.

## 3. Platform PCG graph
Create a PCG graph, **`PCG_HexPlatforms`**:
1. **Get Spline Data** with the actor filter set to **Self**. This reads the segment's spline.
2. **Spline Sampler** with mode **Distance**. Set the distance increment to the spacing you want between platform centres, for example 4000 cm.
3. **Remove the last sampled point.** It lands exactly on the next segment's first point, so without this you get two platforms on top of each other at every joint. A filter-by-index node does this (it's called Filter Elements By Index in recent versions).
4. Optional: a **Transform Points** node for some random sideways or height offset, so the platforms aren't in a perfect line.
5. **Spawn Actor** with template class **`BP_HexPlatform`**, and the option set to *no merging* so each platform stays its own actor.

Make the spacing big enough to leave a gap between platforms. Platform edges are usually around `1.3 × GridSize × HexRadius` from the centre once the outline is trimmed.

## 4. Segment Blueprint
Create **`BP_HexPathSegment`**, parent class **`MyHexPathSegment`**:
- Select its **PCGComponent** and set **Graph** to `PCG_HexPlatforms`.
- Leave the generation trigger as **Generate On Demand**. The C++ starts generation once the spline is ready.

## 5. Bridge PCG graph
Create **`PCG_HexBridge`**:
1. **Get Spline Data**, actor filter **Self**. This reads `BridgeSpline`.
2. **Spline Sampler**, mode **Distance**, with the increment set to your plank or segment length.
3. **Static Mesh Spawner** with your bridge piece mesh. **Turn collision on** in its mesh settings, or players will fall through.

The spline sits exactly on the walking surface of both edge tiles. Offset the meshes downward by their thickness if their pivot is at the centre.

## 6. Bridge Blueprint
Create **`BP_HexBridge`**, parent class **`MyHexBridge`**:
- Set its **PCGComponent**'s **Graph** to `PCG_HexBridge`.
- **`bDestroyWhenEndTileCollapses`:** on by default. Set **`DestroyDelay`** if you want time to play an effect first.
- Optional: override **Handle End Tile Collapsed** to play a collapse effect. Call the parent function if you still want it destroyed. Or bind to the **On End Tile Collapsed** event instead.
- `GetEnds` gives you each end's platform, tile coordinate and location.

## 7. Project settings
Go to **Edit > Project Settings > Game > Hex Bridges**:

| Setting | What to set |
|---|---|
| `BridgeClass` | `BP_HexBridge` |
| `NeighborRadiusMultiplier` | **Has to be larger than** `platform spacing ÷ (GridSize × HexRadius)`, or neighbouring platforms are never compared. With 4000 cm spacing, GridSize 10 and HexRadius 100, that's 4, so use **5**. The default of 3 is too small for that spacing. |
| `MaxSlopeDegrees` | Steepest bridge you allow, for example 25–30. |
| `MaxBridgeLength` | 0 for unlimited, or a cap in cm. |
| `CandidateEdgesPerPlatform` | 4 is fine. Raise it if you see platform pairs that should bridge but don't. |
| `SpatialCellSize` | Roughly your platform spacing, for example 5000–10000. |
| `bDrawDebug` | **On** for the first test: green lines are built bridges, red ones are rejected. |

## 8. Path spawner
Place an **`AMyHexPathSpawner`** in the level. No Blueprint is needed, but you can make one for convenience.
- **Position and rotation:** put it where the path should start, usually at or under the player start. Rotate it so its **forward (X) arrow** points the direction the path should go.
- **`SegmentClass`:** `BP_HexPathSegment`.
- **`SegmentLength`:** a whole multiple of your platform spacing, for example 4 × 4000 = 16000.
- **`PointsPerSegment`:** 4.
- **`InitialSegments`:** 2–3, so there's path ahead before the player moves.
- **`ExtendDistance`:** larger than `SegmentLength`, so the path grows before the player reaches the end. For example 20000.
- **Noise:** `MaxYawDeviation` (for example 45–60) and `YawNoiseFrequency` (0.0001 gives a gentle bend about every 100 m). Set `HeightNoiseAmplitude` above 0 if you want the path to rise and fall. Keep it moderate, or `MaxSlopeDegrees` will reject the bridges.
- **`NoiseSeed`:** change it for a different path.
- **`bDrawDebug`:** on for the first test. It draws the path in cyan.

## 9. Test
1. Use **Play as Listen Server** with one client, so you see both sides.
2. In the **Output Log**, look for `LogHexBridgeSubsystem: Bridged N new platforms…` after each extension. `LogHexPath` warns if `SegmentClass` isn't set.
3. Check:
   - Platforms appear ahead along the path.
   - Green debug lines and bridges appear between them, about 0.1 s later.
   - Platforms only start collapsing after their bridges exist.
   - A bridge disappears on both server and client when the tile at either end collapses.
4. **If no bridges appear,** it's almost always `NeighborRadiusMultiplier` being too small, or `MaxSlopeDegrees` with too much height noise. Red debug lines mean the traces are being blocked.
