# Round 2, PR A: Blender side (D7)

What the "blender" implementer did for `SPEC_A.md` D7 (2026-11-24): the wheel at character size, the five marked deck
pieces removed, the wider cannon bore, the new front turret meshes, a repacked prop atlas, and the new SK_Airship /
turret FBX files. Everything was built headless (`/home/talal/.local/bin/blender -b`, Blender 4.5.3) on the rig copy;
Talal's `StylizedAirship.blend` was never opened (it is unchanged since 2026-10-31: md5 4cb832de... = the rig's byte copy
`rig/AirshipRig_src.blend`, so the source checks in `rig_build.py` pass as before).

`rig/` below = `/mnt/new_partition/BlenderProjects/StylizedAirship/rig/`. Scripts live in
`SourceArt/Airship/scripts/` (source of truth) and run from flat copies in `rig/scripts/`.

## Results (numbers for Unreal, UE hull cm)

| Item | Value |
|---|---|
| `PilotSeat` bone | **(-740.0, 0.0, 264.19)** (was (-843, 0, 268.95)): `AirshipPawn.h` `PilotSeatFallback` |
| `Helm_Wheel` bone | **(-685.0, 0.0, 360.48)** (was (-713, 0, 425.48)); rest rotation identity like every bone; spins about +X |
| `Helm` bone | (-650.0, 0.0, 260.48), unchanged |
| Wheel size | 140 x 140 cm across the handle tips, 16.7 cm deep; hub 100 cm above the deck; tips 28.7 cm above the deck at every spin angle (5 deg steps, no contact with the pedestal) |
| Pilot | capsule axis 55 cm aft of the wheel plane (radius 34 + 21 cm for the arms); hub about 25 cm above the 141.6 cm capsule's centre (chest) |
| Skeleton | 118 bones, same names and parents; 105 deforming |
| SK_Airship.fbx | 31 mesh nodes, 55,556 vertices (was 55,948), 104,030 triangles (was 104,730) |
| Removed | 21 islands, 392 vertices, 700 triangles, all on the `Hull` bone |
| Cannon bore | radius 22 cm (was 13), muzzle face 25..28 cm; sockets unchanged |
| Turret `PivotHeight` | **150 cm** (GunMesh origin above BaseMesh origin) |
| Turret `MuzzleForward` | **180 cm** on GunMesh, between the barrels (barrel ends at Y -10 / +10) |
| Turret base | yaw part, radius 43.6 cm, height 187.7 cm, bounds (-42.0, -42.0, -1.0) .. (43.6, 42.0, 187.7) |
| Turret gun | pitch part, bounds (-44.4, -21.5, -24.0) .. (180.0, 21.5, 36.5), fires +X; pitch -20..+40 clear of the base |
| Turret mounts | port (2100, -245, 655), starboard (2100, 245, 655): the spec defaults are right (deck top measured 655.0) |
| Gantry rail at the mounts | inner face at abs(Y) 293.5, top at Z 768.0 (113 cm above the deck) |
| Clearance | yaw part 4.9 cm from the rail; both turrets swept through yaw -110..+30 / -30..+110 x pitch -20..+40 against the ship: 0 contacts |
| Gunner seat | (2000, -/+245, 655) on the gantry deck; 22 cm from the base at any yaw, 18 cm from the spade grips |

All of it is in `SourceArt/Airship/turret_dims.json` (keys `pilot_seat_ue`, `helm_wheel_ue`, `pivot_height_cm`,
`muzzle_forward_cm`, `base_bounds_cm` / `gun_bounds_cm` in the form `as_53_turret_import.py` reads, `mounts`,
`deck_top_cm_at_mounts`, `rail_top_cm`, `rail_inner_y_cm`, `hitbox_suggestion`, `removed_islands`, ...).

## 1. Deck pieces removed (`deck_removals.json`, `rig_build.py`)

Confirmed against Talal's image 1 with a top view of the rig copy in the same framing (bow down, port right), the
listed islands in red: `media/top_before_after.jpg` (left) and `media/removed_pieces_persp.jpg`. Each arrow matched one
piece; no extra islands were found in the same boxes (only the hull skin 392 and the steam bands 414/415 overlap the
boxes, and they are not inside them).

| Arrow | Piece | Islands | Blender box (m) | Vertices |
|---:|---|---|---|---:|
| 1 | aft grate box near the stern fans (hatch + 5 slats) | 18-24 | x -12.1..-8.9, y +-1.5, z 2.79-3.47 | 152 |
| 2 | grate box mid-deck on the wide part (hatch + 5 slats) | 11-17 | x -0.5..3.5, y +-1.5, z 2.41-3.09 | 152 |
| 3 | tall narrow post at the waist (BowFin + 2 side plates) | 0, 1, 2 | x 7.0..10.19, y +-0.23, z 2.36-7.86 | 56 |
| 4 | big flat hatch on the narrow forward deck (raised slab) | 237 | x 12.75..17.25, y +-1.3, z 6.55-7.45 | 8 |
| 5 | small grate near the bow tip (three stepped boxes: the steps up to the bow tier) | 234, 235, 236 | x 22.49..23.47, y +-0.8, z 6.54-7.34 | 24 |

How (file:line in `SourceArt/Airship/scripts/`):

* `deck_removals.json`: the list (arrow, name, islands, box). One file read by the rig scripts (`rig_common.py:72-89`
  `deck_removals()`, `removed_islands()`, `kept_vertex_index()`) and, directly as data, by the independent verifiers.
* `rig_build.py:66-98`: after the unchanged source checks (36908 vertices, 1150 islands, centroids), each listed
  island must lie inside its box and be on `Hull`; the hash of the kept part (positions, UVs, corner vertex indices,
  renumbered in order: `mesh_hash(me, keep)`, `rig_build.py:33-50`) is taken before the bmesh delete (`:86`) and must equal
  the hash of the mesh after it (`:91`) and again after skinning (`:326`, the old `:284` check, now on the kept part). The skin
  maps rig vertex i to source vertex `KEEP[i]` (`:297`). `skin_report.json` has `deck_removal` (removed islands, vertices,
  triangles, kept totals, per piece).
* `rig_place.py:54`: every clearance test leaves the removed islands out (the helm, cannons and turrets do not touch
  them; placements and every motion range are identical to round 1).
* `rig_check_motion.py:30-34`: maps the rig mesh back to the research island ids through `kept_vertex_index()`.
* `rig_export.py:30` (31 mesh nodes) is unchanged: the pieces were inside the SM_Airship node.
* Unreal `/Game/Assets/MyShip/SM_Airship` (the physics body with UCX) is not changed (spec); Talal's file is not changed.

## 2. Wheel at character size (`props/model_helm.py` v3, `rig_common.py:50-52`)

Knobs at `props/model_helm.py:41-74`: `AXLE_H` 1.00, `TIP_R` 0.70, rim 0.44-0.54 x 0.10 deep (`RIM_HB` 0.05, chamfer
0.015), `SPOKE_SCALE` 0.70, `HUB_FLANGE_R` 0.15, `BOLT_RING_R` 0.11 (bolt heads x0.6), `BAND_ARC` 0.06, `BAND_GAP`
0.006, ferrule scaled with the tips, `WHEEL_X` -0.35. The spoke and hub profiles are the v2 ones in design units scaled
along the spoke by `WHEEL_S` = 0.70 / 1.55; the pedestal is the v2 pedestal modelled in its design units and scaled
uniformly by `PED_S` = 1.00 / 1.65 at the end (`:469`), so the stanchions, bearings, drum, rope, knees and plate all
follow the axle height; the plate skirt stays 5 cm below the deck line. `rig_common.HELM_WHEEL_OFS` = (-0.35, 0, 1.00)
(asserted equal to the Helm.blend wheel origin in `rig_place.py`), `PILOT_BEHIND_AXLE` 0.55.

Look: `media/helm_before_after.jpg` (capsule stand-in 141.6 cm at PilotSeat). The atlas bake draws the helm's ink at a
smaller length scale (`props/bake_props_comic.py:67-70` `INK_SCALE`: wheel 0.45, pedestal 0.6; it scales the bevel
radius, the AO crease / spot distances, the hatch spacing and the stroke growth) so the small wheel keeps the round-1
look instead of inking solid (`media/props_baked.jpg`).

## 3. Cannon bore (`props/model_cannon.py:48-51, 92`)

`BORE_R` 0.22, muzzle face entry `(2.600, BORE_R + 0.03)`; the 0.28 lip and the barrel length are unchanged. The wall
behind the muzzle swell is only 2-5 mm (the bore never shows from outside: it bakes as solid ink). The 1 m ball 80 cm
ahead of the muzzle: `media/cannon_bore_before_after.jpg`. The ball is still 2.3 x the bore's diameter (a barrel that
size can't hold a 1 m bore; this is the stylized look the spec chose).

## 4. Turret meshes (`props/model_turret.py`, `export_turret.py`)

`props/model_turret.py` builds `rig/props/Turret.blend` the way `model_cannon.py` builds the cannon (bmesh in code,
metres, smooth + sharp-by-angle, seams on the sharp edges and lathe meridians, one UV map, `M_Turret_Iron/Wood/Brass/
Bore` placeholder materials that the bake turns into `part_kind`):

* `Turret_Base` (`:230`), the yaw part, origin = yaw axis on the deck: bolted foot ring (r 0.42, a 1 cm skirt below the
  deck line), tapered column, collar, turning ring with bolt heads, cradle plate, two cheeks with round tops and trunnion
  bosses at z 1.50, a curved armour shield round the bow side (a cylinder slab round the yaw axis, r 0.425, +-52 deg,
  a slot for the barrels with an apron below it, rivets, two brackets), a wooden ammo crate on the left cheek (UE -Y).
  Nothing is farther than 0.44 m from the axis (`BASE_MAX_R`, asserted): the gantry rail is 0.465-0.485 m away.
* `Turret_Gun` (`:303`), the pitch part, origin = trunnion axis centre, fires +X: receiver with top cover and rear plate,
  trunnion pins (into the cheeks), twin water-jacketed barrels (jacket r 0.07 with cooling bands, bare barrel r 0.03,
  flash hider, dark bore) at Y +-0.10, a clamp and a front strap, a brass ring sight with cross wires on a post, a rear
  leaf sight, a cocking lever, a belt feed port, spade grips hanging behind the receiver (z 1.28-1.45 above the deck,
  chest height for the mech). Nothing more than 0.45 m behind the axis (`REAR_MAX`, asserted).
* `Turret_Muzzle` empty at (1.80, 0, 0) on the gun.
* Checks in the script: the gun pitched -20, -10, 0, +10, +20, +30, +40 has no triangle contact with the base
  (`pitch_clearance`, `:446`); gunner capsule clearances (`gunner_clearance`, `:460`); UVs without overlap.
* Mesh: base 3,766 triangles, gun 4,012.
* `props/bake_props_comic.py:53` adds Turret.blend to the assemble stage; the atlas stage packs every prop's islands
  together (the turret gun at the higher texel weight, `:351`), so the helm, cannon and turret UVs all moved and the two
  `T_AirshipProps_Comic*` maps were rebaked (0 overlapping triangle pairs, 0 shared texels, 230-288 px/m).
* `export_turret.py` writes `SM_AirshipTurret_Base.fbx` and `SM_AirshipTurret_Gun.fbx` with the SK's conventions
  (`rig_export.py`): cm data and UnitScaleFactor 1, Y-up file with pre-rotated data and an identity mesh node, so in
  Unreal X = forward, Z = up, Blender +Y = UE -Y; smoothing by face, normals per corner, no tangents, one UV channel,
  slot `M_AirshipProps`, no armature, no UCX; pivot = the object origin. It also writes `turret_dims.json`.
* `rig_place.py:417-463` measures the mounts on the rig copy (deck top, the rail by horizontal rays, the base radius
  below the rail top) and sweeps both turrets through their yaw limits x pitch range against the ship.

Look: `media/turret_model.jpg`, `media/turret_on_deck.jpg`, `media/top_before_after.jpg` (right), `media/props_baked.jpg`.

## 5. Checks run

* `bash rig/scripts/props_all.sh` steps (model_helm, model_cannon, model_turret, bake_props_comic assemble / atlas /
  bake / render): all asserts passed; bake on the GPU (Unreal was not running).
* `bash rig/scripts/rig_all.sh`: placement (helm spin clean, cannons identical to round 1, turrets 0 contacts), build
  (21 islands, 392 vertices removed, hash of the kept part unchanged, 118 bones, 31 meshes, 55,556 vertices), both FBX
  exports, turret export, FBX inspection (no problems), round trip (118 bones, 0 weight differences, test animation
  within 0.007 mm), motion ranges (identical hard limits to round 1), renders, README.
* `bash rig/scripts/verify_all.sh`: `verify_fbx` 0 defects (SM_Airship = Talal's mesh minus the 21 islands: positions
  within 0.002 mm, identical face corners and UVs, normals within 0.13 deg; helm contract (-0.35, 0, 1.00) and
  0.55 m; wheel 1.40 m), testanim 0 defects, `verify_import` 0 defects (105-bone deform test 0 mismatches; prop atlas
  raster with the two turret FBX files: 0 overlapping texels), `verify_props` no defects (SK props and both turret FBX
  files: UVs identical to the baked source, positions within 0.0002 mm, units, axes, identity node, one material),
  `verify_rigblend` 118 bones, deform == skinned.

Changed verifier expectations (all derived, nothing typed in): `verify_fbx.py:31-34, 191-200, 314-366, 432-460`,
`verify_import.py:76-104, 179-190`, `verify_props.py:62-110`; README totals from `rig_fbx_inspect.py:166-168, 190`
(`tris` per mesh, `total_triangles`) and `skin_report.json`.

## 6. How to rebuild and test

```
bash rig/scripts/props_all.sh      # only when a prop script changed (BAKE_ARGS=--cpu bakes on the CPU)
bash rig/scripts/rig_all.sh
bash rig/scripts/verify_all.sh     # every [verify_*] line must say "defects: 0" / "none"
```

The three scripts take `BLENDER=/path/to/blender` (default `/home/talal/.local/bin/blender`). Copy the outputs into
the repo: `export/SK_Airship.fbx`, `export/SK_Airship_testanim.fbx`, `export/SM_AirshipTurret_Base.fbx`,
`export/SM_AirshipTurret_Gun.fbx`, `export/README_rig.md` -> `SourceArt/Airship/`; `props/textures/T_AirshipProps_Comic
{Lines,Mask}.png` -> `SourceArt/Airship/textures/`; `checks/rig/turret_dims.json` -> `SourceArt/Airship/`. Review
renders: `blender -b --factory-startup --python rig/scripts/round2_render.py -- --mode highlight|before|after|turret`
(`rig/renders/round2/`; `rig_all.sh` runs `--mode after`). Round-1 state (rig, prop blends, textures, FBX, checks): `rig/_backup_round1_20261124/`.

## 7. What the Unreal import must know

* Re-import `T_AirshipProps_ComicLines` / `ComicMask` (as_02) together with SK_Airship (as_56): the atlas was repacked,
  so the old textures on the new meshes (or the reverse) put the wrong ink on the helm and cannons.
* SK_Airship re-import keeps the skeleton (same 118 bones, same names); `Helm_Wheel` and `PilotSeat` moved (above);
  every other bone is where it was (cannons, sockets, thrusters, lamps).
* PA_Airship is not rebuilt (spec): its helm boxes are larger than the new wheel, the hatch / post / steps pieces are
  gone from the render mesh but stay in `SM_Airship`'s UCX physics body (unchanged on purpose).
* Turret import (as_53): static meshes, no collision, combine meshes, slot -> `M_AirshipProps`, keep the pivot. The base
  bottom is at Z -1 cm (a skirt), the footprint half size 43.6 cm, the gun's rear -44.4 cm (all inside as_53's limits).
* BP_AirshipTurret (as_55): `PivotHeight` 150, `MuzzleForward` 180. The spec's HitBox (60, 60, 95) at z 95 is wider than
  the mesh (radius 43.6) and reaches past the rail's inner face at the mounts (245 + 60 = 305 > 293.5); it is
  QueryOnly, so it only matters for what it blocks: `hitbox_suggestion` in turret_dims.json is (43.6, 43.6, 93.8) at z
  93.8. The gun sweeps above it (muzzle up to Z 266 at +40).
* The ammo crate is on the turret's left (UE -Y), on both turrets (same mesh): outboard on the port turret.

## 8. Notes and deviations

* Spec D7.4 says `props/uv_layouts.py` reserves an atlas region for the turret: that script only rasterises the
  cannon's UVs for inspection. The atlas is packed in `bake_props_comic.py`'s atlas stage (all props together, exact
  overlap test), which now includes the turret; `uv_layouts.py` is unchanged.
* The shield is a slab round the yaw axis (r 0.425) instead of a flatter plate: a flat 0.84 m wide plate reaches
  0.515 m from the axis at its corners and hit the gantry rail when the port turret turned outboard (found by the sweep).
* The spade grips stay within the 0.45 m the spec allows behind the trunnion (the first version reached 0.59 m and left
  the gunner only 2-4 cm).
* The renders of the props on Talal's ship in `bake_props_comic.py`'s render stage still use his full mesh (preview only).
