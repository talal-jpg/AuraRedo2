# Airship detail pass, round 3: zone map and shared rules

Talal approved zone 1 on 2026-11-28 ("keep it as it is"). The rest of the ship gets the same density and the same
kinds of detail, in six more zones. This page is the plan every zone agent follows: who owns what, where the seams
are, what continues across them, the conventions, the commands and the checks.

Zone map: `media/zones/zone_map.jpg` (port, starboard, top, bottom; the ship coloured by owning zone).
The map is code: `SourceArt/Airship/scripts/detail_zones.py`. If this page and the code disagree, the code wins.

## 1. The zones

| Zone | Owns | Area (m2, SM_Airship faces) | Status |
|---|---|---:|---|
| Z1 | port flank between the cannon stations (x -11.55 .. 6.95), deck edge to the bilge line; pod FL, its pocket and rim | 479 | done, approved 2026-11-28 |
| Z2 | starboard flank, same x range (mirror of Z1); pod FR, its pocket and rim | 456 | to do |
| Z3 | aft flanks of both sides, from x -11.55 to the transom, above the bilge line; pods RL and RR, their pockets and rims | 774 | to do |
| Z4 | bow: everything forward of x 6.95 below the gantry (both flanks, belly, keel, the belly tabs there), BowWedge, Underside_Front | 743 | to do |
| Z5 | belly and keel below the bilge line, both sides, x -16.36 .. 6.95, around (not on) the pods and pockets; the belly tabs aft of 6.95 | 214 | to do |
| Z6 | stern: transom, Rudder, both turbines (FanHousing, FanRotor, FanMount, hanging rods), the OPEN FAN BACKS | 982 | to do |
| Z7 | gantry and forward superstructure (not its walkable tops), the 4 search lights, both winches, ChainFwd, ChainAft, the 4 hang strips, the deck rails along the whole ship, and the STAIRS from the main deck to the forward turret deck | 627 | to do |
| none | the deck planks and every walkable top (PA_Airship box tops), the deck props: they stay plain | 656 | - |

Changes to the first proposal, and why:
* Z1 / Z3 seam at x -11.55 (not -11.47): that is where zone 1's plates really start (`x_aft`). The aft cannon station
  is at -11.47.
* `Winch_Aft` and `ChainAft` are not at the stern: they hang under the gantry at the bow (winches x 27.4 .. 31.3,
  ChainAft x 12.2 .. 16.2). They go to Z7, not Z6.
* `BowFin` no longer exists: round 2 deleted it (deck_removals.json, arrow 3).
* The belly tabs (the small 'Hull' islands 393-411, one row per side just below the bilge line) go whole to Z5
  (Z4 forward of x 6.95). Zone 1 stops just above them.
* The deck rails go to Z7 (with the gunwale tops nobody walks on). The outer gunwale band below the deck edge stays
  with the flank zone of its x range (zone 1 already put gussets under it).
* Pocket rims: the RL and RR pockets sit inside Z1 / Z2's x range. Zone 1's plates come to 9 cm of the RL opening
  above it, so Z3 owns the RL / RR pocket (walls, roof) and only the part of the rim band that is not in the Z1 / Z2
  flank (section 2, rule 3).

Suggested order (two at a time): **A: Z2 + Z7**, **B: Z3 + Z4**, **C: Z5 + Z6**. Z2 first because Z3 and Z4 continue
its starboard lines; Z7 has no flank seam; Z5 and Z6 border all the others. Z6 (open fan backs) and Z7 (stairs) are
two of Talal's four answers, so do not let them slip to the end of a round.

## 2. Ownership rules (detail_zones.py)

Every SM_Airship polygon gets one owner, by the first rule that matches:

1. **Parts with a fixed owner.** Pods and nozzles: FL Z1, FR Z2, RL and RR Z3. Turbines (housing, rotor, mounts,
   rods) and the rudder: Z6. Gantry (with search lights, winches, chains, hang strips) and DeckRails: Z7. BowWedge and
   Underside_Front: Z4. Deck props: none. Belly tabs: Z5 (Z4 forward of x 6.95), each island whole.
2. **Walkable tops stay plain** (owner none): faces with normal z > 0.7 that lie on the top of a PA_Airship hull box
   (`Saved/Airship/pa_hull_boxes.json`), and the skin's deck (normal z > 0.75 above z 1.5).
3. **Pockets.** Inside a pod's pocket (within 4 cm of the pocket cylinder, r 2.85 about the pod axis, in the pod's
   height band h -2.9 .. 4.6): the pod's zone. The rim band (up to 0.25 m outside the cylinder): the pod's zone too,
   except where it lies in the Z1 / Z2 flank and the pod is not that zone's own (round RL / RR above the bilge line).
4. **Transom**: aft of x -15.0 with the face looking aft (normal x < -0.6): Z6.
5. **Bow**: forward of x 6.95: Z4.
6. **Belly**: below the bilge line: Z5. The bilge line is a chart angle of -56 deg: the angle of the point seen from
   the axis (x, side x 1.5, 0.3), 0 = horizontal outboard, as in `FlankChart`. It runs at about z -3.7 amidships,
   -2.3 at x -15, -1.1 at x 8.
7. **Aft flank**: aft of x -11.55: Z3.
8. Everything else: the flank between the stations, port Z1, starboard Z2.

Open space has owners too (`VOLUMES`): the stairs box (Z7: x 2.5 .. 10.65, |y| <= 4.6, z 2.35 .. 6.65) and the two
open fan backs (Z6: x -20.0 .. -16.85, within 2.95 m of the fan axis y +-7.6, z 1.4).

Nothing may be built inside the keep-clear volumes (`KEEP_CLEAR`): the helm (1.5 m round the pedestal axis x -6.5,
z 2.3 .. 5.5), the two turrets (r 1.95 round each yaw axis, z 6.5 .. 9.7), the four cannons (upper half ball r 2.3 round
each carriage bone). The rig check sweeps the moving ones exactly.

Point helpers: `zone_of_point`, `ZoneIndex(ship).zone_at(p)` (a volume, else the owner of the nearest SM_Airship face),
`ZoneIndex.near_other(p, zone)`, `keep_clear_hits(points)`, `chart_phi(p)`, `pod_coords(p, pod)`.

## 3. Seam rule and continuity

**Seam rule.** A zone ends on a rib, a strap or a plate seam, never in the middle of a plate. Keep 10 cm from a zone
boundary, unless the piece continues a run that crosses it (then end the piece on the boundary line, like the 8 mm
joints between strake segments). Never touch, cover or edit another zone's objects; they are obstacles. The ownership
check (section 9) lists what lies on a seam.

**Continuity.** The flank runs follow the two steam bands, so they continue across every seam at the same height
below the band. Zone 1's numbers (all in `z1_continuity.json`, copied here; `s` = arc length down the chart section
from the deck edge, `v` = distance below the line named):

| Run | Rule (same on every flank zone) | At Z1's aft edge, x -11.55 | At Z1's fore edge, x 6.95 |
|---|---|---|---|
| Upper plate rows | top 0.27 m below the gunwale band's lower edge (`upper.top_off`) | ref_up s 0.928 | ref_up s 1.056 |
| Gussets | under the gunwale band, every 0.51 m on the grid x = -11.20 + 0.51 k, 10 cm out, 22 cm tall | first at x -11.20, (-11.20, 6.694, 2.178) | last at 3.08 (stopped by the FL pocket): next on the grid are 7.16, 7.67 ... |
| Conduit pair | r 3.0 cm (dark) and 2.6 cm (brass), 6 cm and 15.5 cm above the end of the upper free run, centres 15 cm off the skin; ends drop into glands | glands at x -11.15: (-11.212, 7.048, 1.299) and (-11.210, 7.028, 1.395) | glands at x 2.85: (2.904, 7.467, 0.598) |
| Lower plate rows / strake top | 0.04 m below the lower band's lower edge (`lower.top_off`) | ref_low s 3.374, strake line s 3.356 | ref_low s 3.778 |
| Strake + teeth | rust strake 0.20 m tall, 8.5 cm thick, segments one tooth pitch long with 8 mm joints; dark backing 0.60 m; teeth 0.70-0.90 x 0.62-0.78 m, 9 cm, notches 14-20 cm, 8 mm below the strake | first segment starts at x -11.53: strake top (-11.53, 6.530, -0.429), backing bottom (-11.53, 6.112, -1.117) | last segment ends at x 0.93 (FL pocket) |
| Pipe channel | dark backing v 1.02 .. 1.52 below the strake top; copper r 7 cm at v 1.15, brass r 5.8 cm at v 1.39, centres 10.6 / 9.4 cm off the skin, flanges, clamps every metre, glands at both ends | span starts at -11.55; pipes start at x -11.26: copper (-11.262, 6.097, -1.460), brass (-11.257, 5.928, -1.636) | span ends at 0.90 (pocket) |
| Machinery bays | lower bays v 1.62 .. 2.78 below the strake top, upper bays v 0.10 .. 0.86 below ref_up | (none near the edge) | (none near the edge) |

How to continue:
* **Z3** (aft of -11.55, port): start the strake at the same line, its last segment ending at x -11.538 (8 mm joint to
  Z1's first); start the channel's own dark backing at -11.56 and bring the two pipes out of glands at about x -11.70,
  so the pipe line reads as one run that dives through the hull between the glands; gussets at -11.71, -12.22, ...;
  conduits out of glands at about -11.25 at the same heights. Starboard: the same from Z2's numbers.
* **Z2** builds the starboard flank with zone 1's code and knobs (`Flank(ship, K, side=-1)`); the gusset grid is the
  same (x = -11.20 + 0.51 k). Its build writes `z2_continuity.json`: Z3 and Z4 read their starboard seam from it.
* **Z4** (forward of 6.95): the bands go on to the bow, so the upper rows, gussets (grid above), conduits and the strake
  line start again just forward of the FL / FR rim straps, at the same offsets below the bands. Use your own chart
  (`Flank`, `K['chart_x']` over your x range) and blend your reference lines into Z1's values over the first metre.
* **Z5** (belly): the bilge line is a hard edge, not a run. Do not run plates up over the tabs into Z1 / Z2 / Z3.

## 4. Conventions (the approved zone 1 language, for every zone)

* **Colour by role** (section 5): base plates hull yellow plus or minus one value step; rust red for strakes, teeth,
  frame ribs, straps, bay frames and at most about 15 % heavy armour plates; dark metal / machinery grey for machinery
  and recesses; pods rust and dark metal, no yellow.
* **Three depth levels**: base plates 4.5 cm; layers on them 10-11 cm; ribs and teeth about 12-13 cm; machinery bays
  and the pipe channel 18-20 cm.
* **Kinds**: machinery bays (riveted rust frame, dark floor, housings with hinged and latched lids, pump, bottle,
  valves, pipes), slotted armour plates, pipe channels (r 6-9 cm) with flanges, clamps and valves, picture-frame
  plates, about 30 % calm rest areas.
* **Rivets**: low domed (8 sides, 14 triangles), only on corners, ribs, straps, strakes, lids and flanges, about 28 cm
  apart, never inked.
* **Fit**: every piece touches the ship or another piece (`drop_floating`); 1.5 cm gap to the skin and 6 mm between
  layers (no z-fight); details within about 20 cm of the skin so the silhouette stays, unless your zone says otherwise
  (stairs, fan backs, gantry); no piece inside out (`orient_outward`); 0 non-manifold edges.
* **Rig**: one object per bone, every vertex 100 % on one bone, parented to 'Armature' with an Armature modifier;
  objects `SM_AirshipDetail_ZN_<Part>` in collection `Detail_ZN`; seeded and deterministic (a rebuild gives the same
  hash).
* **Never add** (Talal removed them before): teal horizontal bars, rectangular windows / hatches / cabin windows,
  portholes, round grilles on the hull, the big gear under the hull, hanging ladders. The new stairs are wanted (not a
  hanging ladder). Heavy, purposeful chains like reference 1's are allowed under the belly and on the gantry.
* **Unreal limits**: nothing on walkable surfaces (no detail vertex above a PA_Airship box top inside its footprint;
  UE cm = (100 x, -100 y, 100 z) of Blender metres); the deck planks stay plain; keep the cannons' sweep clear (yaw
  +-20, elevation -10 .. +8.75, recoil 0-60 cm); keep 1.5 m round the helm; respect every moving bone: Thruster_XX
  (+-3 deg), _Nozzle (+-5), _PetalNN (-10 .. +35), Turbine_L/R yaw +-12, rotors 360, rods +-20, Rudder +-30,
  SearchLight heads (pan 360, posts wobble +-4), ChainFwd, Winch_*, Cannon_*.
* **Turrets**: the two front machine-gun turrets are separate props (rig/props/AirshipProps.blend, objects
  Turret_Base, Turret_Gun; never save that file), placed by BP_AirshipTurret at UE (2100, +-245, 655) cm. Base pivot
  = yaw axis on the deck top, gun pivot = trunnion 1.50 m above it, gun 1.80 m ahead and 0.44 m behind, yaw (Blender)
  port -30 .. +110 deg, starboard -110 .. +30, pitch -20 .. +40. They are obstacles (the render and the rig check place
  them). They keep their own props atlas and are not detailed here. Checked at about 5 m on 2026-11-28 (bolted foot
  flange, water-jacketed twin guns, ammo box, sight): not clearly lower in detail than the detailed hull, so nothing
  to report. Never change them.
* Write plain, short sentences in the zone doc. Look at every render before you report it.

## 5. Role materials

Every detail face carries one of these materials (`detail_common.ROLES`; material index = position, never reorder,
only append). The Unreal stage bakes the colours by role, so the material name is the role. The toon preview colour is
the final colour (Talal 2026-11-28: reference 1's yellow and rust).

| Key (code) | Material | Colour (linear RGB) | Use |
|---|---|---|---|
| paint_yellow | DM_Yellow | 0.95, 0.68, 0.21 | base plates, one step lighter than the hull paint (0.90, 0.60, 0.17) |
| paint_ochre | DM_Ochre | 0.83, 0.54, 0.15 | base plates one step darker; picture-frame rims on yellow plates |
| paint_orange | DM_Orange | 0.85, 0.38, 0.12 | reserved: the turbine housings' own orange (Z6 only, if a piece must match them) |
| rust_red | DM_Rust | 0.50, 0.20, 0.12 | strakes, teeth, frame ribs, straps, bay frames, rim straps, heavy armour, patches, pods |
| rust_dark | DM_RustDark | 0.34, 0.14, 0.09 | pod plates and lips, second rust tone |
| dark_metal | DM_Dark | 0.17, 0.16, 0.16 | recesses, bay floors, backings, clamps, glands, lids, hinges, conduits |
| machinery | DM_Machinery | 0.28, 0.29, 0.31 | housings, pump bodies, cavity ribs |
| steel | DM_Steel | 0.50, 0.52, 0.55 | nozzle hoops and fins, latches; fan blade tip caps and stair hand rails (2026-11-28) |
| copper | DM_Copper | 0.70, 0.36, 0.17 | big pipes, pipe stubs |
| brass | DM_Brass | 0.76, 0.58, 0.24 | second pipe, flanges, valves, collars |
| bolt | DM_Rivet | 0.33, 0.30, 0.27 | rivet heads (never inked) |
| wood | DM_Wood | 0.45, 0.30, 0.18 | wooden stair treads (Z7; the hand rails are steel since 2026-11-28), only where wood makes sense |

Until 2026-11-28 the same keys were materials `M_Detail_<Key>`. Each material carries the custom properties
`palette_key` and `role` (= the key). `detail_checks.object_report` fails any face without a role.

## 6. Shared modules (do not edit them from a zone)

Zone agents import these and never change them. To change behaviour, pass knobs in `K`, or copy one function into your
own zone script and change the copy.

| Module | What it is |
|---|---|
| `detail_common.py` | generators, `Mesh` (with `orient_outward`), rigid skinning, role materials, `safe_save`, `zone_blend`, `append_zone` |
| `detail_ship.py` | `Ship` (faces by island / part / bone), `FlankChart` (side +1 / -1), pod frames |
| `detail_flank.py` | zone 1's flank layout: `Flank(ship, K, side)`, `build_flank` (+ continuity export) |
| `detail_pod.py` | `pocket_rim`, `cavity`, `build_pod(which=...)`, `pod_islands`; starboard pods mirrored |
| `detail_checks.py` | silhouette / pod outline / PA checks, `object_report`, `zone_checks`; CLI for any zone file |
| `detail_zones.py` | the zone map (rules, volumes, keep-clear, point tests, `ownership_report`) |
| `detail_base_edits.py` + `base_edits/` | the only place SM_Airship faces get deleted (section 8) |
| `detail_render.py` | previews: toon (final), paper, clay; any zones; turrets; base edits; generic cameras |
| `detail_rigcheck.py` | rig check for any zone: pods, turbines, rudder, search lights, chain, cannons, turrets |
| `detail_hash.py` | geometry fingerprint of a zone's objects (determinism, identity) |
| `detail_zonemap.py`, `detail_survey.py`, `detail_selftest.py` | the zone map render, the ship survey (`zones/ship_survey.json`), the shared-code self test |
| `detail_zone_template.py` | the minimal zone script: copy it to `detail_zN.py` |
| `detail_zone1.py` | zone 1 (approved, frozen): its `K` is the reference density; import it, do not edit it |

## 7. Commands

```
B=/mnt/new_partition/UnrealProjects/_AirshipWork_logs/blender_capped.sh     # -b --factory-startup, 4 GB cap, max 2 runs
S=/mnt/new_partition/UnrealProjects/_AirshipWork/SourceArt/Airship/scripts
Z=/mnt/new_partition/BlenderProjects/StylizedAirship/rig/detail/zones
D=/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/round3
N=2                                                                         # your zone number

cp $S/detail_zone_template.py $S/detail_z$N.py                              # then set ZONE = 'Z2', write build()
$B --python $S/detail_z$N.py                                                # -> $Z/AirshipRig_detail_z$N.blend, $D/z${N}_report.json
$B --python $S/detail_z$N.py -- --no-save                                   # try without saving
$B --python $S/detail_hash.py -- --blend $Z/AirshipRig_detail_z$N.blend --prefix SM_AirshipDetail_Z${N}_ --out $Z/z${N}_hash.json
#   rebuild, then the same with --compare $Z/z${N}_hash.json: must print IDENTICAL GEOMETRY (determinism)
$B --python $S/detail_checks.py -- --blend $Z/AirshipRig_detail_z$N.blend --zone Z$N --out $D/z${N}_checks.json --sample 2
$B --python $S/detail_rigcheck.py -- --blend $Z/AirshipRig_detail_z$N.blend --zones 1 --only Detail_Z$N \
   --sets pod:FR,cannons:R1+R2 --out $D/z${N}_rigcheck.json                 # sets: section 9
$B --python $S/detail_render.py -- --blend $Z/AirshipRig_detail_z$N.blend --zones 1 --look toon \
   --states before,after --shots side_stbd,q34_stbd --out $D/media/z$N    # + --cam 'name:x,y,z:tx,ty,tz:28' close-ups
$B --python $S/detail_render.py -- ... --look clay --samples 48 ...         # clay + cavity (Cycles: keep runs < 9 min)
$B --python $S/detail_base_edits.py -- --list                               # resolve the registered base edits
$B --python $S/detail_selftest.py                                           # shared code on starboard / FR / RL / RR
$B --python $S/detail_zonemap.py && python3 -B $S/detail_zonemap.py --sheet $D/media/zones $D/media/zones/zone_map.jpg
```

Built-in shots (`detail_render.SHOTS`): side, side_stbd, top, bottom, q34, q34_stbd, q34_aft, q34_aft_stbd, q34_bow,
q34_bow_stbd, close_flank, close_pod, pocket, below, pod_low, stern, stern_q34, fan_back_L, fan_back_R, fwd_deck,
stairs_area, gantry_port, belly, q34_belly. Poses: `--pose poseA:FR` (any pod), or JSON control values, for example
`--pose '{"TurbineYawDeg_L": 12, "RotorAngleDeg_L": 30}'`. `--zones 1,2,3` shows the other zones' details; render
with every zone that is done, so seams show. Long Cycles renders: split them or lower `--samples`; a run must stay
under about 9 minutes. Never use the Blender MCP tools (they drive Talal's live Blender).

## 8. Base edits (deleting faces of the ship's own mesh)

* Each zone may add ONE file `SourceArt/Airship/scripts/base_edits/zN.json` (format in `detail_base_edits.py` and
  `base_edits/_example.json`). Select faces by research island metadata (islands, src, part, piece, index), optionally
  filtered by a box and a normal; give `expect_faces` / `expect_tris` guards (the counts `--list` prints).
* Edits only delete faces. New geometry is always a detail object, never added into SM_Airship.
* The zone builds, renders and rig checks apply them in memory; `AirshipRig.blend` and Talal's files never change. The
  assembler / export applies them once, at the end.
* How round 2's `deck_removals.json` was applied: `rig_build.py` deletes those 21 islands when it builds
  `AirshipRig.blend` (hashes of the kept vertices and UVs before and after); `hull_ink_drivable.py` then re-baked
  the comic ink texture locally, because the baked ambient-occlusion ink still drew black rectangles where the pieces
  had stood (`T_AirshipDrivable_ComicLines.png`); `verify_import.py` checks the Unreal import against the same list.
  What follows for round 3:
  - Deleting whole islands is safe for SM_Airship's UVs and leaves no open edges. A partial island leaves an open
    border: cover it with a detail piece (a lip, a rim) and say so.
  - The baked ink near deleted faces must be re-baked the same way (the lead's Unreal stage; list your edit ids).
  - The rig mesh keeps its vertex order for round 2's removals only; that is why zones never delete for real.
  - `rig_export.py` and `verify_import.py` know only round 2's list: the export stage must add these edits.
  - PA_Airship (physics) is separate. If an edit removes something that has a physics box (a deck crate has one:
    `Hull_Props_02 .. 06`), the lead must remove the box too: say so in the zone doc.
* Tested on 2026-11-28 (scratch copy, not registered): deleting `duct_back_wall` and `tail_cone` of both fans
  (120 faces, 432 triangles, whole islands, 0 new open edges) opens the fan backs and the blades show from behind.
  The tail cone (r 2.46 at x -18.76, tip at -19.9) hides the blades as much as the back wall does, so both must go.

## 9. Per-zone checklist (every zone runs these and reports them in zN_report.json / ZONE_N.md)

1. **Safety**: built through `blender_capped.sh`; output only `rig/detail/zones/AirshipRig_detail_zN.blend`
   (`safe_save`) and files under `Docs/Airship/round3/` named for your zone; md5 of `AirshipRig_detail.blend`
   (31317912621726b5e647c78bfc0cf948), `AirshipRig.blend`, `AirshipRig_src.blend`, `StylizedAirship.blend`,
   `props/AirshipProps.blend` unchanged at the end.
2. **Determinism**: two builds give the same `detail_hash.py` fingerprint.
3. **Objects** (`detail_checks.object_report`, `ok` true for every object): 0 non-manifold edges, 0 vertices not 100 %
   on one bone, 0 faces without a role material, 0 inside-out pieces, parent 'Armature' + Armature modifier, name
   `SM_AirshipDetail_ZN_*`, collection `Detail_ZN`.
4. **Floating pieces**: 0 left after `drop_floating` (report what it removed and why).
5. **Ownership** (`zone_checks` -> `ownership`): `outside_zone` 0 (or each one explained); `within_margin_of` only
   for runs continued across a seam; `keep_clear` empty.
6. **Walkable**: `pa_boxes.verts_above_a_box_top` 0. Nothing on the deck planks.
7. **Silhouette**: hull details within about 20 cm of the skin (p99 <= 0.185 m); pod details grow the pod's outline
   by at most about 10 cm (zone 1's `envelope_report`); zones that build out into open space (stairs, fan backs,
   gantry) say how far and why.
8. **Rig check** (`detail_rigcheck.py --only Detail_ZN --zones 1,<done zones>`): RESULT PASS. Sets per zone:
   Z2 `pod:FR,cannons:R1+R2`; Z3 `pod:RL,pod:RR,turbine:L,turbine:R,cannons:L2+R2`; Z4 `pod:FL,pod:FR,chain,turrets`;
   Z5 `pod:FL,pod:FR,pod:RL,pod:RR,turbine:L,turbine:R,rudder`; Z6 `turbine:L,turbine:R,rudder`;
   Z7 `searchlights,chain,turrets,cannons`.
9. **Continuity**: the runs of section 3 continue at the seams; a close-up render of each seam with the neighbour
   loaded (`--zones`).
10. **Never-add list** respected (section 4).
11. **Density like zone 1**: about 130 triangles per m2 of hull, rivets about 24 % of the triangles, about 30 % calm
    plate area, heavy rust armour at most about 15 % of the plates. Report triangles per object and per kind.
12. **Renders**, toon = final look, before / after, with the done zones loaded: the whole zone (ortho side or top),
    25 m 3/4, 5.5 m close-ups, every seam; clay optional. Look at every one. Media in `media/zN/`.
13. **Doc** `ZONE_N.md`: what was built, numbers, checks, open questions; short sentences.

## 10. What the plan stage found (2026-11-28)

* **Zone 1 rebuild is identical** to the approved file: same counts and coordinates (0.1 mm), faces, roles and bones
  for all four objects (`z1_approved_hash.json`; the rebuild after moving the code to the shared modules compared
  IDENTICAL GEOMETRY). The generalized rig check reproduces zone 1's results (pod FL 243 poses 0 new contacts; ship
  baselines 244 / 54; cannon L1 1.055 m, L2 1.321 m) and adds turbine L, rudder, search lights, chain, R cannons and
  turrets (all PASS, `z1_rigcheck_all_sets.json`).
* **Zone 1 has inside-out pieces**: 38 in `Nozzle_FL` (the hoops) and 13 in `Pod_FL` (ring band, side-box lids). The
  previews hide it; Unreal would cull their outsides. Zone 1 is frozen, so they stay; flip them at export. New zones
  call `orient_outward()` (the template does). The self test flipped the same kinds on FR / RL / RR.
* **Zone 1 sits in Z1**: 8 of 9,603 sampled vertices have their nearest hull face in Z4 / Z5 (pod parts over the
  belly), 104 lie on a seam (`z1_checks.json`).
* **Pods**: the four are the same model, FR / RR mirrored (plates at -90 / -35.6 / 0 deg, side boxes at -110 / -84 deg).
  They are not placed symmetrically: FR is 0.196 m lower and 0.262 m further out than a mirror of FL, RR 0.035 m lower
  and 0.637 m further out than a mirror of RL. With zone 1's pod knobs, the hull-clearance test drops the lower hug
  pipe and the actuators on FR, RL and RR (one hug pipe left), so the gap under the big plates would stay bare: Z2 and
  Z3 must tune `K['pod']` (`hug_th`, `hug_r`, `act_th`, ...) per pod to reach zone 1's look there.
* **Starboard flank with zone 1's knobs** (self test, seed 2301): it builds and passes every object check, but with
  less calm area (17 % vs 30 %), more heavy armour (5 of 8 raised plates) and only one channel span (-4.40 .. 0.80):
  Z2 must tune seed / knobs to match zone 1's numbers, not just run it.
* **RL rim**: zone 1's plates come to 2.942 m from the RL axis (9 cm outside the 2.85 m opening) above it, so Z3's RL
  rim strap can only be a lip there (or sit on the pocket wall); the same for RR next to Z2. The RL cavity wall reads
  as nearly a full circle (sector -175 .. 175 deg).
* **Turbines**: at +12 deg yaw the port fan housing is 1 deg from touching steam band island 414 (motion range test:
  first contact at +13); the starboard one the same at -12. Z3 / Z6 details on the bands near the stern must not grow
  outward there. The rods swing +-20 deg in the rig test.
* **Stairs facts (Z7)**: main deck top z 2.39 at x 5 and 2.36 at x 10; the turret deck (PA 'Platform' boxes) starts at
  x 10.55, top z 6.53 (the gantry structure from x 10.19): a 4.15 m rise. Hull half-width 6.7 m at x 5, 4.8 m at x 10
  (the rails stand inside that).
  In the way: deck crates and barrels (DeckProps islands, PA boxes `Hull_Props_02 .. 06` at x 4.55 .. 7.2, |y| up to
  2.95); the gantry legs at its aft corners; search light AftL post at (11.2, 2.8) on the platform's aft port corner;
  the platform's rails (inner |y| 2.935, 1.13 m tall) need a gap where the stairs land (Gantry src: a Z7 base edit).
  The stairs need walkable collision in Unreal: keep them one object `SM_AirshipDetail_Z7_Stairs` (Hull bone) and give
  the lead the tread boxes for PA_Airship.
* **Budget**: at zone 1's density the ship lands at about 0.48-0.58 M triangles for LOD0 (ZONE1.md section 6): about
  130 per m2 of hull plus about 18.5k per pod (pod 12.3k, nozzle 2.2k, petals 4.0k).

## 11. Files

* `media/zones/zone_map.jpg` (+ `zonemap_<view>.jpg`, `zone_faces.json`: faces and area per zone and per rule)
* `z1_continuity.json` (zone 1's lines and runs), `z1_checks.json`, `z1_rigcheck_all_sets.json`, `z1_approved_hash.json`
* `rig/detail/zones/ship_survey.json` (sections, transom, part groups with boxes, pod angles, bone heads)
* `rig/detail/zones/AirshipRig_detail_z1.blend` (zone 1, rebuilt; the approved `rig/detail/AirshipRig_detail.blend`
  is read only)
