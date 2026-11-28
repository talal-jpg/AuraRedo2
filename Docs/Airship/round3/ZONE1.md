# Airship detail pass, zone 1 (sample for approval, pass 2)

Talal asked for the ship to keep its shape but get the detail level of the Burrower (reference 2), with the kinds and
shapes of detail taken from the airship concept (reference 1). Zone 1 is a style and density sample: please approve or
correct it before the rest of the ship is done.

Sheet: `media/zone1/zone1_sheet.jpg` (all renders, before / after, labelled, now with the in-game paper-and-ink look).
The first pass is kept for comparison as `media/zone1/zone1_sheet_pass1.jpg`. Reports: `zone1_report.json` (build
parameters, counts, triangles, checks) and `zone1_rigcheck.json` (rig poses, cannon sweeps, per-bone assignment), copied
here from `rig/detail/`.

## 1. What changed in pass 2 (after review)

The review of pass 1 found it about half as dense as the Burrower at the same distance, coloured like a sticker
collage, and with several pieces that read as things Talal removed (portholes, windows) or as faces. Pass 2 fixes that:

| Review point | Pass 2 |
|---|---|
| Colour picked at random from 4-5 paints | Colour **by role**: base plates are hull yellow plus or minus one value step only; rust red for heavy armour (2 of 49 plates, the raised ones), the strake and teeth, frame ribs, straps and bay frames; dark metal and machinery grey for machinery and anything in a recess; the pod has no yellow at all (rust, dark rust, dark metal). |
| No depth or size hierarchy, a uniform field of flat plates | **Three depth levels**: base plates 4.5 cm; layers on them (picture frames, slotted plates, patches, raised armour) 10-11 cm; frame ribs 11.6 cm, teeth 13 cm; machinery bays and the pipe channel 18-20 cm. **Picture-frame plates** (raised rim, lower centre) give the cavity shading inside them. **Hero clusters**: four machinery bays (a riveted rust frame round a dark floor) with housings, a pump body, a gas bottle, a valve and pipes; a **pipe channel** with two big pipes (r 7 and 5.8 cm) on a dark backing along the lower flank. About 30 % of the plate area stays calm on purpose (rest areas). |
| Upper row read as portholes and cabin windows | **Round grilles, louvre boxes and exhaust stubs removed** from the flank. In their place: **slotted armour plates** (2-4 slanted slots cut through a plate of the same colour, a flush dark backing behind the slots), placed irregularly (two different ones side by side on one plate, others alone), and **through-hull fittings** (a brass branch rises from the conduit and enters the hull through a riveted gland). |
| Teeth read as pockets, cable loops as smiles | **Teeth** rebuilt like reference 1's rack: big rectangular rust blocks 0.7-0.9 m wide, 0.62-0.78 m tall, 9 cm thick on a 2 cm dark backing (the gaps read as deep notches), one small chamfer, two rivets on the top edge, hanging from a riveted rust strake just under the lower band. The strake is built in one-tooth-pitch segments on a straight fitted line; segments that would cover the ship's own hardware under the band, or bend over a shelf in the skin, are left out. **Cable loops, the chain and the black junction boxes are gone.** |
| 45 % of triangles were spiky hex bolts | **Low domed round rivets** (8 sides, 14 triangles, not inked), only on plate corners, frame ribs, straps, the strake, teeth tops, bay frames, lids and flanges, about 28 cm apart: 880 rivets, 24 % of the zone's triangles (pass 1: 1,931 hex bolts, 45 %). The previews skip rivets in the ink, as a comic artist draws rivet rows as dots; the bake will do that. |
| Heatsink boxes, cables into electronics boxes, drawer handles | Replaced by **housings**: chunky machinery grey body, riveted base flange, a lid with **two hinges and two dog latches**, flanged pipe stubs. The pod's side-box lids also got hinges and latches instead of the handle. |
| Stray fragment, cables ending in air, tiny chain | A **floating-piece check** in the build: every loose piece must touch the ship or another piece within 2 cm (a rivet within 1 cm of its own plate), else it is removed and reported (0 left in the final build). Every conduit now ends by dropping straight into a riveted gland. The chain is removed from the flank (heavy hanging chains belong under the hull or on the gantry, later zones). The middle-strip conduit is removed: that strip is a row of stepped blocks and a conduit wobbles over them. |
| A plate crumpled over a step in the skin | Every plate is tested before it is built: if its patch of skin departs from a smooth fitted surface by more than 1.2 cm (a shelf or step), the plate is left out (1 plate in this zone). |
| Pipes too thin | Channel pipes r 7 / 5.8 cm, conduits r 3 / 2.6 cm, pod pipe bundle r 5 cm, pod hugging pipes r 6 / 5 cm. Clamps are now a 6-sided band plus one foot. |
| Pod quilt flattened the big armour plates | The quilt is gone. The three big plates stay the main shapes and get a thick riveted lip along the lower edges of the front and front-outboard plates, two straps bent over the folds of the outboard and front plates, and three large rust patches, all sitting on the plates' outer facets. The density moved into the gap below: two thick pipes hug the drum there, clamped, ends bent into the drum, under the two actuators. |
| Nozzle and petals barely changed | Two riveted **hoops** round the nozzle bell, the 12 fins split between them and in lighter **steel**; each petal has a full-width **hinge barrel** under the lip ring and a short **actuator** down the petal. |
| Zone's forward end was a random doodle | Plates now end at the pocket's fore rim strap (x 6.95), a clean zone edge. |
| Invented cavity machinery invisible | The hanger column, bearing ring, struts and gimbal stub are removed; the cavity keeps its wall stiffeners and one ring rib along the lower edge, the parts that show through the opening. |
| Pod check stricter than the doc said; no cannon or PA check | New checks (section 5): the pod's outline growth seen from each side, the port cannons swept through yaw, elevation and recoil against the hull details, and the details against PA_Airship's hull boxes. |
| Only judged in reference 1's palette | Two more views in the **in-game look** (paper white, blue-grey cel shading, navy ink with a heavy outline and thin creases, no ink on rivets). |

## 2. What zone 1 covers

* The **port hull flank** between the aft cannon station (x -11.47) and the forward one (x -0.46), from the deck edge
  down to the turn of the bilge (the chart angle -56 degrees, just above the existing belly tabs). It carries on
  forward over the front-left pod's hull pocket and ends at the pocket's fore rim strap (x 6.95).
* The **front-left thruster pod** `Thruster_FL`: the pod drum and its plates, the nozzle and the 12 petals.
* The **hull pocket** of that pod: a riveted rim strap round the opening, wall stiffeners and a ring rib in the cavity.

Not in zone 1: the aft-left pod (RL) and its pocket (they sit inside the same x range, below the lower band), the
deck, the belly below the bilge line, the starboard side, the bow, the gantry and the fans.

## 3. How it is built

New detail geometry sits **on top of** the unchanged ship. SM_Airship (Talal's mesh), its UVs and its baked textures,
and the props are not touched.

* Build file (since 2026-11-28): `/mnt/new_partition/BlenderProjects/StylizedAirship/rig/detail/zones/AirshipRig_detail_z1.blend`.
  The build opens `rig/AirshipRig.blend` read-only, adds collection `Detail_Z1` and saves the copy there through
  `detail_common.safe_save`, which refuses every other place. The approved pass 2 file
  `rig/detail/AirshipRig_detail.blend` is read only now (md5 31317912621726b5e647c78bfc0cf948); nothing writes it.
  `AirshipRig.blend`, `AirshipRig_src.blend` and `StylizedAirship.blend` are never written.
* The rebuilt file is identical to the approved one: same vertex and face counts, same coordinates (to 0.1 mm), same
  faces, roles and bones for all four objects (`detail_hash.py`, see ZONES.md). Only the material names changed:
  `M_Detail_<Key>` became the role materials `DM_*` (same keys, same order).
* Scripts (in `SourceArt/Airship/scripts/`):

| Script | What it does |
|---|---|
| `detail_common.py` | the generators (section 4), the mesh builder, rigid skinning, Freestyle marks on rivets, target surfaces with smooth normals, the floating-piece check, role materials, safe_save |
| `detail_ship.py` | which SM_Airship faces are what (skin, pods, pipes ...), the hull flank chart, pod frames |
| `detail_flank.py`, `detail_pod.py`, `detail_checks.py` | zone 1's flank layout, pod / pocket code and checks, moved out of `detail_zone1.py` on 2026-11-28 so the other zones share them (geometry unchanged) |
| `detail_zone1.py` | zone 1's knobs `K` and build, report `rig/detail/zones/z1_report.json`, continuity lines `z1_continuity.json` |
| `detail_rigcheck.py` | poses moving parts through their limits and counts new intersections; sweeps cannons and turrets (since 2026-11-28 for any zone: `--sets pod:FL,cannons`) |
| `detail_render.py` | preview renders: `toon` (the final look, reference 1 palette + ink), `paper` (old in-game paper + navy ink), `clay` (clay + cavity); before / after, optional rig pose, other zones, turrets |
| `detail_sheet.py` | the combined sheet (python3 + Pillow) |

Rebuild everything (headless, through the memory-capped wrapper, about 5 minutes in total):

```
B=/mnt/new_partition/UnrealProjects/_AirshipWork_logs/blender_capped.sh     # adds -b --factory-startup, 4 GB cap
S=/mnt/new_partition/UnrealProjects/_AirshipWork/SourceArt/Airship/scripts
Z=/mnt/new_partition/BlenderProjects/StylizedAirship/rig/detail/zones
M=/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/round3/media/zone1
$B --python $S/detail_zone1.py                                             # 9 s, writes $Z/AirshipRig_detail_z1.blend
$B --python $S/detail_hash.py -- --blend $Z/AirshipRig_detail_z1.blend --prefix SM_AirshipDetail_Z1_ \
   --out $Z/z1_rebuild_hash.json --compare $Z/z1_approved_hash.json       # must print IDENTICAL GEOMETRY
$B --python $S/detail_rigcheck.py -- --blend $Z/AirshipRig_detail_z1.blend --sets pod:FL,cannons:L1+L2 --out $Z/z1_rigcheck.json
$B --python $S/detail_render.py -- --blend $Z/AirshipRig_detail_z1.blend --look toon --states before,after --shots side,q34,close_flank,close_pod,pod_low --out $M
$B --python $S/detail_render.py -- --blend $Z/AirshipRig_detail_z1.blend --look toon --states after --shots close_pod,pod_low --pose poseA --out $M   # and poseB
$B --python $S/detail_render.py -- --blend $Z/AirshipRig_detail_z1.blend --look paper --states before,after --shots q34,close_flank --out $M
$B --python $S/detail_render.py -- --blend $Z/AirshipRig_detail_z1.blend --look clay --samples 64 --states before,after --shots q34,close_flank,close_pod --out $M
python3 -B $S/detail_sheet.py                                              # media/zone1/zone1_sheet.jpg
```

(The renders now also show the two front turrets; `--turrets off` gives the old framing.)

All randomness is seeded (`seed` 1301 in `detail_zone1.py`), so a rebuild gives the same geometry.

### How the flank is laid out

1. **Chart.** Rays in the cross-section plane of each station x (every 5 cm, every 0.5 degree) hit the hull skin. Each
   hit keeps its point, its smooth (render) normal, whether other geometry (bands, steam pipes, pods, tabs) is within
   30 cm in front of it, and its arc length s down the section from the deck edge.
2. **Free mask.** A cell is free when nothing is in front of it, it is not next to a crease or a jump, it is above
   the bilge line, and it is outside both pod pockets (plus a margin that grows below the pocket, where the pod moves
   most when it tilts) and the rim strap. Two masks, one under the gunwale band and one under the lower band, use
   coordinates that follow the band above them, so everything runs parallel to the bands.
3. **Plan first, then plates.** On the lower flank, before any plate is placed: the strake-and-teeth strip right under
   the band (1 m), the pipe channel below it (0.5 m), and two machinery bays below that are reserved. On the upper
   rows, two smaller machinery bays are reserved. Then staggered rows of plates (0.8-1.7 m wide) are clipped to the
   largest free rectangle inside each candidate, and a second pass fills the gaps with plates of at least 0.3 x 0.24 m.
4. **Layers.** Some plates are raised and overlap both row neighbours (shingled; half of them heavy rust armour); most
   other seams get a riveted rust frame rib; slotted armour plates go on a few upper and middle-strip plates; then
   picture frames and rust patches on others; about 30 % of the plate area stays calm. Then the strake and teeth,
   gussets under the gunwale band, the pipe channel, the bays and their machinery, the conduit pair with its
   through-hull fittings.

The cleared gap between layers is 1.5 cm on the skin and 6 mm between layers, so nothing z-fights.

## 4. Generators (detail_common.py) and the values zone 1 uses

| Generator | What it makes | Zone 1 values |
|---|---|---|
| `solid_plate` | plate conforming to any surface given as (u, v) -> point + normal: thickness, chamfered top edge, optional cut corners, closed shell | base plates 1.5 cm gap, 4.5 cm thick, 1.4 cm chamfer, 30 % of corners cut 7-17 cm |
| `solid_quad` | the same for any four-sided outline | the slanted bars of the slotted plates |
| `picture_frame` | raised rim of four strips round a panel | 7.5 cm rim, 3.5 cm high, 9-16 cm in from the plate edge, one value step from the plate's yellow; bay frames 8-10 cm rim, 5 cm high, rust |
| `slotted_plate` | armour plate with 2-4 slanted slots through it, flush dark backing | 0.55-0.8 x 0.32-0.45 m, 3.5 cm thick, slots 5 cm wide at 58 degrees; middle strip 0.5 x 0.3 m with 2 slots |
| raised plates | a plate lifted onto its neighbours, overlapping each by 8 cm | 30 % chance per plate, never two neighbours, 4 cm thick, half of them rust armour with a rivet row on the top edge |
| frame ribs | narrow plate over a vertical seam | 12 cm wide, 5 cm thick, rust, on 75 % of plain seams, rivets every 28 cm |
| patches | smaller plate on a plate | 0.4-0.8 x 0.3-0.55 m, 4 cm thick, rust (70 %) or ochre, rivets at the corners |
| strake + teeth | riveted rust strake (0.2 m, 8.5 cm) with a 0.6 m dark backing; rectangular teeth hanging from it | teeth 0.7-0.9 x 0.62-0.78 m, 9 cm on the backing, 14-20 cm notches, one 7 cm chamfer |
| `rivet` / `rivet_row` / `corner_pts` | low domed rivet head, 8 sides, 14 triangles | r 2.2 cm, 1.2 cm high, every 28 cm or one per corner, 7 cm in |
| `housing` | machinery housing: body, riveted base flange, lid with two hinges and two dog latches, flanged pipe stubs | lower bays 0.8 x 0.62 x 0.11 m and 0.58 x 0.62 x 0.11 m; upper bays pairs of about 0.5 x 0.4 x 0.1 m; a 0.42 x 0.3 m one on the pod front |
| `pump_body` | horizontal pump body on two saddles, flanged cover, domed end, bands, side inlet | one, r 6.8 cm, 0.69 m long (the wide lower bay; the narrow one has its housing and valve branch only) |
| `tank` | gas bottle with domed ends and two straps | r 6.2 cm, rust |
| `pipe_run` / `tube` / `flange` / `clamp` | pipes with rounded elbows (only where they turn more than 12 degrees), riveted flanges, clamps (6-sided band + one foot) | channel pair r 7 cm copper and 5.8 cm brass, 12 sides, flanges at 20 / 50 / 80 %, clamps every metre, a valve on the copper pipe; bay pipes r 4 cm |
| conduits | pair along the bottom of the upper rows, over every layer, on a smoothed line | r 3 / 2.6 cm, clamps every 0.7 m, both ends drop into glands, 3 through-hull fittings (r 2.8 cm) |
| `gland` | square riveted plate with a brass collar where a pipe enters the hull | 12-14 cm square |
| `valve_body` | inline valve block, bonnet sideways, gauge disc; **no hand wheel** (Talal had the valve wheels removed) | channel pipe, bay branch pipes and the upper bay link pipes |
| `gusset` | triangular bracket with a foot plate | under the gunwale band every 0.51 m: 10 cm out, 22 cm tall |
| `piston` | hydraulic actuator | 2 on the pod front, 12 on the petals |
| `drop_floating` | removes loose pieces that touch nothing (section 1) | 2 cm, rivets 1 cm |
| first-pass generators kept for later zones | `louver_vent`, `grille_round`, `machinery_box`, `cable`, `chain`, `bolt` | not used on this flank any more |

Pocket rim: a 16 cm wide, 5 cm thick riveted rust strap along the top, aft and fore edges of the pocket opening (edges
found in the chart as outer skin next to pocket wall, smoothed with a cubic fit), cut where the steam pipes cross the
opening and kept 20 cm from the pod's own parts.

Pod: rust / dark rust / dark metal plates on the drum between the ribs (rivets at the corners, some with a smaller plate
on top), rivets on the ribs every 20 degrees, a riveted ring band above the collar, the lips, straps and patches on the
big plates (section 1), lids with hinges and latches on the two side boxes, a pipe bundle of three r 5 cm pipes down the
front-inboard side (clamped at the ribs, bent into the drum above the hull floor), two pipes hugging the drum in the
lowest band, two actuators, a small housing on the front band with a conduit to the bundle.

## 5. Bones and checks

| Object (collection `Detail_Z1`, parent `Armature`, Armature modifier) | Bone(s) | Vertices | Triangles |
|---|---|---:|---:|
| `SM_AirshipDetail_Z1_Hull` | `Hull` | 18,127 | 32,676 |
| `SM_AirshipDetail_Z1_Pod_FL` | `Thruster_FL` | 6,944 | 12,336 |
| `SM_AirshipDetail_Z1_Nozzle_FL` | `Thruster_FL_Nozzle` | 1,248 | 2,160 |
| `SM_AirshipDetail_Z1_Petals_FL` | `Thruster_FL_Petal00` .. `11` (one vertex group each, 190 vertices) | 2,280 | 4,032 |

Every vertex is 100 % on one bone (0 exceptions), 0 non-manifold edges in all four objects, 0 floating pieces.

**Rig motion.** 243 poses = pod pitch and roll each in {-3, 0, +3} deg x nozzle pitch and roll each in {-5, 0, +5}
deg x petal flare {-10, 0, +35} deg (the RIG_CONTRACT limits). Triangle overlaps were counted between the details and
everything that moves against them. Result: **0 overlaps in all 243 poses.** The ship's own pod already overlaps the
hull at rest (184 triangle pairs, 244 at the worst pose) and its nozzle overlaps the pod (54): unchanged, from the
original model. Pod details stay out of the hull floor that runs through the lower drum, with clearance for the 3-degree
tilt.

**Port cannons.** L1 and L2 swept through yaw {-20, 0, +20} x elevation {-10, 0, +8.75} x recoil {0, 60 cm} (18 poses
each): 0 overlaps; the closest any cannon part comes to a hull detail is **1.06 m** (L1) and **1.32 m** (L2), both at
-10 degrees elevation.

**PA_Airship hull boxes** (`Saved/Airship/pa_hull_boxes.json`, UE cm): **0 detail vertices above any box top** inside its
footprint (nothing on the walkable deck); hull details reach at most z 2.23 m. 1,586 detail vertices lie inside boxes:
the boxes are 25 cm columns that overhang the flank's bulge, so physics is slightly coarser than the details there (as
it was for the hull itself).

**Silhouette** (`zone1_report.json` -> `checks`):

| Part | Result |
|---|---|
| Hull flank details | all within **19.9 cm** of the skin (99 % within 18.5 cm) |
| Pocket cavity details | within 8.7 cm of the cavity wall |
| Pod details | the pod's outline seen from any side grows by at most **10.3 cm** (lips and patches on the big plates: 6.2 / 4.4 cm above their facets; the side-box lids and their hinges by up to 4 cm). Measured as distance to the nearest pod surface, details reach up to 31 cm, because pipes over the 10 cm rib crests and the actuators stand off the drum between the ribs, and the surface queries do not find the outer face of the three big plates (only their inner face, 13 cm lower; cause not chased, the outline check uses the plates' vertices as well). |
| Nozzle hoops and fins | inside the radius of the nozzle band and lip ring (outline growth below zero) |
| Petal hinges and actuators | within 5 cm of the petal, inside the outline |

## 6. Triangles and the whole-ship estimate

* Zone 1 adds **51,204 triangles** (hull 32,676, pod 12,336, nozzle 2,160, petals 4,032). Pass 1 added 85,792.
* Where they go: rivets 24 %, pipes / conduits / clamps / glands / valves 20 %, pod 20 %, plates of all kinds 13 %,
  machinery bays 12 %, nozzle, petals, strake, teeth, rim and cavity the rest.
* SK_Airship today: 104,030 triangles (SM_Airship 68,510 + props).
* **By area:** zone 1 covers about 476 m^2 (pass 1: 484; the forward edge moved back to the rim strap) of the 4,458 m^2
  of detail-able surface. At the same density the whole ship gets 51,204 x 4,458 / 476 = 480k new triangles, about
  **0.58 M in total**.
* **By part:** hull detail density 130 tris/m^2 over the 2,343 m^2 of hull-like surfaces = 304k, plus four pods at
  18.5k = 74k, plus today's 104k: about **0.48 M**.
* So the whole ship at this density lands at **0.48-0.58 M triangles for LOD0**, below the 0.8-1.5 M target. The
  review asked to spend the bolt budget on forms; forms are cheap in triangles, so the count fell while the read got
  denser. If Talal wants the 0.8 M+ range, the knobs in `K` (top of `detail_zone1.py`) are: more bays per metre and a
  second channel (`bay`, `ubay`, `channel`), smoother pipes (`sides`), a second rivet row on armour, frame and patch
  shares (`frame`, `patch`), and rounded plate edges (not used yet: they add crease lines in the ink).

## 7. Renders (`media/zone1/`)

| File | View |
|---|---|
| `zone1_sheet.jpg` | everything below on one labelled sheet (pass 1: `zone1_sheet_pass1.jpg`) |
| `side_toon_before/after.jpg` | whole port side, orthographic, same camera |
| `q34_toon_before/after.jpg` | 3/4 low from port-forward, about 25 m |
| `close_flank_toon_before/after.jpg` | hull flank, about 5.5 m |
| `close_pod_toon_before/after.jpg` | front-left pod, about 5.5 m |
| `pod_low_toon_before/after.jpg` | pod, nozzle and petals from below |
| `q34_paper_*`, `close_flank_paper_*` | the in-game look: paper white, blue-grey cel shading, navy ink |
| `q34_clay_*`, `close_flank_clay_*`, `close_pod_clay_*` | clay + cavity (Cycles, ambient occlusion) of the three views above |
| `close_pod_toon_after_poseA/B.jpg`, `pod_low_toon_after_poseA/B.jpg` | rig limits: A = pod +3/+3, nozzle -5/+5, petals open +35; B = pod -3/-3, nozzle +5/-5, petals closed -10 |

The `toon` look is preview only: flat colours from reference 1 by role, three-band cel shading, Freestyle ink weighted by
size (2.4 px outline, 1.2 px creases and colour borders, no ink on rivets). In the preview the ship's own parts get the
same palette by part, so before and after compare fairly. The `paper` look uses one paper colour everywhere (pocket walls
dark), 2.6 px navy outlines and 1.1 px creases.

## 8. Open questions for Talal

1. **Colour.** In the game the hull is paper white with navy ink. Both looks are on the sheet now. Should the final bake
   of the details (and maybe the hull) be coloured like reference 1, or keep the paper-and-ink look?
2. **Density and budget.** Is this the right amount and the right kind? It puts the whole ship at about 0.48-0.58 M
   triangles, below the 0.8-1.5 M target (section 6 lists the knobs to go up).
3. **Things reference 1 shows that were not added**, because Talal removed that kind before: the teal horizontal bars
   on the flank (like the steam rubrails), the rectangular window / hatches, portholes, the big gear in the recess under
   the hull, hanging ladders. Say if any should come back.
4. **New kinds to approve:** the machinery bays (riveted frame, dark floor, housings with hinged lids), the slotted
   armour plates, the rack of teeth, the pipe channel, the picture-frame plates.
5. **Zone edges.** The flank stops at the bilge line (just above the existing belly tabs); the belly, the aft-left pod and
   its pocket come with later zones. The strake has a gap of about a metre under the ship's own hardware that hangs
   below the lower band (near x -2.5).
6. **Stairs / ladder to the forward turret deck** (agreed for this pass): not in zone 1, since the forward deck is
   another zone. Planned for that zone: which side, and stairs or a ladder?

## 9. Notes for the later steps

* Export: `rig_export.py` asserts 31 meshes; the detail objects add 4 per zone. Before an export the details need UVs
  (their own atlas), the comic bake (rivet rows as ink dots there), and either the assert updated or the details merged
  per bone.
* Physics: the details are visual only. PA_Airship and the walkable deck are unchanged; the details stay within 20 cm of
  the hull, below the rail line and off the deck (section 5).
* The same generators and the same chart / mask code work for the starboard side (`Flank(ship, K, side=-1)`) and the
  other pods (`build_pod(..., which='FR' / 'RL' / 'RR')`): checked on 2026-11-28 (`detail_selftest.py`, ZONES.md).
  The plate islands are the same on every pod (12 vertices each; FR = FL + 78, RL = FL + 156, RR = FL + 234).
* 38 pieces of `SM_AirshipDetail_Z1_Nozzle_FL` (the hoops) and 13 of `SM_AirshipDetail_Z1_Pod_FL` (the ring band,
  the side-box lids) are built inside out (faces wound inward). The previews do not show it, Unreal would (back-face
  culling). Zone 1 is approved and frozen, so they are left as they are; flip them at the export step
  (`detail_checks.object_report` counts them). The new zones flip theirs in the build (`Mesh.orient_outward`).
