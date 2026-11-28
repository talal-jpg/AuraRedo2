# Airship detail pass, round 3: the whole ship

All seven zones are now in one file and were checked as one ship. After the whole-ship review, one fix round changed
zones 4, 5, 6 and 7 and the preview renders (section 8). Then your three answers of 2026-11-28 (keel block rust, a
collar and tip caps on the fan blades, steel stair hand rails) changed zones 6 and 7 and the ship's colour map
(section 5a). Every number on this page is from after those answers.

* Sheet: `media/full/full_sheet.jpg` (15 rows, before / after; toon = the final yellow and rust look; clay = cavity;
  rows for the chase camera, the stern and close-ups). Earlier sheets: `media/full/full_sheet_pass2.jpg` (after the
  review fixes, before your answers) and `media/full/full_sheet_pass1.jpg` (before the review fixes).
* File: `/mnt/new_partition/BlenderProjects/StylizedAirship/rig/detail/zones/AirshipRig_detail_full.blend`
  (md5 1f2b3e05bf0a5a47d82db98170b8daaa, 100.1 MB; the file before your answers was 8b5295f4e51cf590870af58c62650001).
* Reports: `full_report.json` (build and global checks), `full_rigcheck.json` (every moving part),
  `full_verify.json` (the saved file reopened), `full_talal_path_test.json` (test of the "Talal edited zone 1" path),
  `rig/detail/zones/full_hash.json` (fingerprint of the 34 detail objects).
* Script: `SourceArt/Airship/scripts/detail_assemble.py` (sheet: `detail_full_sheet.py`).

## 1. Your four answers (2026-11-28) and how each is met

| Your answer | What the ship has now |
|---|---|
| 1. "keep it as it is" | Zone 1 is in the full file exactly as you approved it: same vertices, faces, colours and bones (fingerprint compare). The other six zones use zone 1's generators, sizes and rules. Whole ship: 27.6 % of the detail triangles are rivets (zone 1: 24 %). Calm plate area per zone is about 28-45 % (zone 1: 30 %); only the transom is calmer (71 %), on purpose (section 8). Heavy rust armour stays at or under about 15 % of the plates. |
| 2. "yellow and rust" | Every detail face has one role material (`DM_Yellow`, `DM_Ochre`, `DM_Rust`, `DM_RustDark`, `DM_Dark`, `DM_Machinery`, `DM_Steel`, `DM_Copper`, `DM_Brass`, `DM_Rivet`, `DM_Wood`, `DM_Orange`). The toon renders show the final colours. The paper-white look is no longer used. |
| 3. "stairs, where looks better" | Two straight flights near the middle of the main deck: 0.6 m to port of the centre line, in the gap between the crates, with a landing half way. They arrive at the turret deck's aft edge, 0.6 m to port of its middle. 19 risers of 0.219 m, 0.30 m going, 36.1 degrees, 1.55 m between the hand rails, open sky above. Rust steel stringers, wooden treads, steel tube hand rails (your answer of 2026-11-28; they were wood), guard rails along the rest of the turret deck's aft edge. No rail or crate was removed (true centring would mean moving the crates and their PA boxes). Views: sheet rows 12 and 13. |
| 4. "remove the back of the fans" | The flat disc behind the blades and the big tail cone are deleted from both fans (base edits `z6_fan_back_L` / `_R`). Behind the blades there is now an open exhaust: dark liner, a five-strut stator, a small bearing housing with a short tail cone, a riveted rim. From behind you see the blades (sheet rows 6-8 and 13). |

Yes, an open back makes sense for a thrust fan. Air goes in at the front and out at the back, so a real ducted fan
is open at the exhaust. Only the stator struts and the bearing hub sit behind the blades.

## 2. What each zone did

| Zone | Where | Objects | Triangles | Rivets | What is on it |
|---|---|---:|---:|---:|---|
| Z1 | port flank between the cannons, pod FL | 4 | 51,204 | 24 % | the approved sample: plates, raised armour, slotted plates, picture frames, machinery bays, pipe channel, strake and teeth, conduits; pod plates, lips, straps, pipes, actuators; nozzle hoops; petal hinges |
| Z2 | starboard flank, pod FR | 4 | 52,294 | 23 % | the same kinds as zone 1, own seed; calm area 34 % |
| Z3 | aft flanks of both sides, pods RL, RR | 7 | 60,068 | 27 % | zone 1's runs continued past the seam (gussets, conduits, strake, channel); both rear pods like FL |
| Z4 | bow: flanks, bow wedge, keel block | 3 | 63,774 | 32 % | heavy rust plates in two tones, riveted angle irons on every crease, bent straps, 5 machinery bays, a pipe channel, bolted blocks, a short strake with teeth; the keel block mostly rust with three wrap bands |
| Z5 | belly and keel | 1 | 58,782 | 27 % | riveted keel girder, two pipe mains, belly frames ending on a riveted bilge stringer per side, 4 machinery bays, 2 heavy hoses in short sags, plates |
| Z6 | stern, fans, rudder | 8 | 60,918 | 28 % | the open fan backs; plates and rims on the fan housings; a riveted collar ring, a cuff per blade and a steel tip cap per blade on both rotors; the transom with a pipe header (port) and a riser pair (starboard); the rudder with big plates and a diagonal brace; rod weights |
| Z7 | gantry, turret deck, stairs, rails | 7 | 46,102 | 31 % | the stairs (steel tube hand rails); truss gussets, deck-edge plates, joists and pipes under the turret deck, pumps on the legs, search light details, winch details, the heavy ChainAft link chain, rail collars, guard rails |
| **All** | | **34** | **393,142** | **27.6 %** | |

The zone docs (`ZONE1.md`, `ZONE_2.md` .. `ZONE_7.md`) have the details.

## 3. Triangles

| | Before | After |
|---|---:|---:|
| SM_Airship | 68,510 | 68,006 (504 deleted by the base edits; the keel block is recoloured, not changed) |
| Props (cannons, helm: 30 objects) | 35,520 | 35,520 |
| Details (34 objects) | 0 | 393,142 |
| **SK_Airship** | **104,030** | **496,668** |
| Each front turret (separate static mesh, not in the SK) | 7,778 | 7,778 |

This is inside the 0.48-0.58 M estimate from zone 1.

By bone: `Hull` 258,238; `Turbine_L` 19,482; `Turbine_R` 19,216; the four pods 11,388-13,896 each; the four nozzles
about 2,100 each; the petals 4,032 per pod (336 per petal bone); `Rudder` 6,784; search light heads 768 each, posts
532 each; `Winch_Aft` 1,504, `Winch_Fwd` 168; rotors 4,136 each (216 before the blade collar and caps); rods 176 each. Every bone list is in
`full_report.json -> tris.per_bone`.

LOD estimates for the details (rivets are the Freestyle-marked faces):

| LOD | Keeps | Detail triangles | SK total |
|---|---|---:|---:|
| LOD0 | everything | 393,142 | 496,668 |
| LOD1 | no rivets (108,626 tris) and no loose pieces under 15 cm (31,012 tris: latches, hinges, small clamps, gauges) | 253,504 | about 357,000 |
| LOD2 | only pieces of 0.6 m and more (plates, big pipes, housings, stairs) | 180,826 | about 284,400 |

## 4. Checks on the whole ship

Every check ran on the assembly with the base edits applied (the deleted faces are not there).

| Check | Result |
|---|---|
| Identity | All 34 detail objects match their zone's hash file (vertices, faces, roles, bones). In the saved file, zone 1's `Nozzle_FL` and `Pod_FL` differ only in face winding (the fix below). |
| Objects | All 34 ok: 0 non-manifold edges, 0 vertices not 100 % on one bone, 0 faces without a role material, parent `Armature` with an Armature modifier, names and collections right. |
| Inside-out pieces | Zone 1 had 51 (38 in `Nozzle_FL`, 13 in `Pod_FL`). They are flipped in the full file: winding reversed, custom normals turned with them (largest change 0.03 degrees), positions, colours and rivet marks unchanged. Now 0 on the whole ship. |
| Floating pieces | 0 of 13,199 loose pieces. Each touches the ship, a prop or another piece within 2 cm (rivets 1 cm). |
| Overlaps between zones | 0 triangle overlaps between details of different zones. Within a zone, one joint: zone 7's guard rails butt into the top of the stair hand rails and their saddle (40 triangle pairs, on purpose; 32 with the wooden rail). Details against the cannons, helm and turrets at rest: 0. |
| Pods FL, FR, RL, RR | 243 poses each (pod +-3, nozzle +-5, petals -10 .. +35): 0 new contacts. |
| Fans L, R | 99 poses each (yaw +-12, rotor every 15 degrees, rods +-20): 0 new contacts. The new blade collar, cuffs and tip caps are also tested swept (every rotor angle, yaw every 0.25 degrees): 2.1 cm from the hull side (the fan-mount pylon), 1.9 cm from the duct wall (section 5a). |
| Rudder | 13 poses (-30 .. 30): 0 new contacts. |
| Search lights | 216 poses (pan 360, wobble +-4): 0 new contacts. |
| Chain and winches | 36 poses: 0 new contacts. |
| Cannons | All four swept (yaw +-20, elevation -10 .. 8.75, recoil 0-60 cm): 0 overlaps. Closest detail: L1 / R1 0.34 m, L2 / R2 0.40 m (zone 7's rail collars, as in its own check). |
| Turrets | Both swept through their yaw range and pitch -20 .. 40: 0 overlaps, closest detail 0.34 m. |
| Keep-clear (helm 1.5 m, turrets, cannons) | 0 detail vertices inside. |
| Walkable tops (PA_Airship) | Nothing stands free on a walkable top, apart from two known spots (section 5). This check is stricter than the shared one: a vertex inside any box counts as inside collision, so stacked boxes no longer give false alarms. |
| Deck planks | Nothing on the deck planks. |
| Stairs | Measured on the geometry: 19 risers 0.216-0.222 m (json 0.219), going 0.30 m, 36.1 degrees, rise 4.154 m (json 4.155). Landing top 4.582 m, the same as the `Stairs_Landing` box. The ramp boxes' tops pass within 2.1 cm of every nosing. Head room: open sky. Clear width 1.55 m. Nothing of the ship, the props, the turrets or another detail inside the walking space. |
| Silhouette | Hull details stay within about 20 cm of the skin (p99 0.18 m; a few valve and housing vertices reach 0.21 m where the skin curves away; the belly's two short hoses reach 0.28 m). From the side, the outline grows by 11.5 m2 on 344 m2: 8.8 m2 of it within 20 cm. Further out are only the stairs (2.9 m2, on purpose); the hanging chains and long hose sags are gone. From the top, nothing new is more than 20 cm out. Bounding box: 10 cm higher (search light heads) and 7 cm longer (front end of the gantry). The lowest point is still the petal tips (z -6.17). |
| Ownership | No surprises: the counts (every 4th vertex) match what each zone reported and explained. |
| Base edits | 156 faces / 504 triangles deleted, whole islands. Open border edges 294 before and 294 after. The kept vertices, UVs, corners and weights hash the same before and after. |
| Protected files | Same md5 at the start and the end of every run: `AirshipRig_detail.blend` 31317912621726b5e647c78bfc0cf948, `AirshipRig.blend` 50f895b0bd50be523e3aaa0a6ecbfa31, `AirshipRig_src.blend` and `StylizedAirship.blend` 4cb832deaa0fa005bf6a9359e34692bb, `AirshipProps.blend` b253e788be1d887028d3110c0e0c65a2. |

Rig check after your answers: `full_rigcheck.json`, RESULT PASS, 186 s, the same sets and pose counts as above, 0 new
contacts; cannons closest 0.34 / 0.40 m, turrets 0.34 m.

Your zone 1 file (`rig/detail/AirshipRig_detail.blend`) still has the approved md5. So zone 1 came from the generated
file, which has the same geometry. If you edit your file, the assembler takes zone 1 and anything you added from it,
and lists every difference. That path was tested on your unchanged file. It reported "identical" for all four
objects and for SM_Airship.

## 5. Things to know

1. **ChainAft over the bow ledge.** Zone 7 swapped the six ChainAft bars for a heavy link chain on the same line
   (same box to 7 cm). From the gantry bracket at x 12.2 it drops down past the narrow outer ledge of the forward main
   deck (PA box `Hull_MainFwd_01_1`, y 2.76 .. 3.5, top 24 cm below the main deck) to the hull side, as the old bars
   did. Heights above that ledge per 20 cm of x are within about 10 cm of the old bars' (x 12.4: 1.38 m, x 12.6:
   0.88 m), but the walk check's 'free' class (not next to the hull) now reaches down to 1.36 m (was 1.51 m), because
   the heavy links are wider. A 1.42 m mech walking on that ledge right under the bracket would clip the chain by
   about 6 cm; elsewhere it meets the chain where it meets the old bars. The chain has no collision, as before. A
   blocking box over the ledge at x 12.0 .. 13.8 would settle it (lead / Talal).
2. **Guard rail tips.** The last 4.5 cm of each new guard rail bar, where it meets the stair hand rail at the top,
   lies just outside the collision boxes. Nobody fits through 4.5 cm.
3. **Preview ink.** Fixed in the renders (section 8): the toon renders now draw the ink as its own pass and keep it
   off the plain deck, so the stray dashes from edges hidden under the deck are gone. This is a preview fix only; the
   game's ink is the comic bake.
4. **Rivets.** The whole ship is at 27.6 % rivet triangles against zone 1's 24 %. Zones 4, 6 and 7 are at 29-32 %
   (more angle irons, coarser plate grids). Their knobs are in the zone docs if it looks too riveted.
5. **Open questions from the zones**, collected:
   * Z3: the front of the rear pods is plainer than FL's (their hug pipes and actuators had to go aft).
   * Z5: a plain yellow ring, 0.5-1 m wide, stays round each pod on the belly. Fill it?
   * Z6: your raised transom panels and the long low panel have corner rivets only. Anything more read as doors or
     as a face's teeth.
   * Z6 blade collar and tip caps, Z7 steel hand rails, Z4 keel block rust: answered 2026-11-28 and done (5a).
   * Z7: keep the guard rails on the turret deck's aft edge? (still open; they stay)
   * Z5 / Z7: the belly has no hanging chains now (the swags read as necklaces). Do you want one purposeful heavy
     chain there (from a hawse to a winch, or with a hook or weight)?

## 5a. Your answers of 2026-11-28 (11:00 UTC) and what was done

You answered "1 . yes , 2. yes , 3. make them steel" to: 1 the grey keel block rust, 2 a blade-root collar ring and
tip caps on the fan blades, 3 the stair hand rails wood or steel.

| Answer | What the ship has now | Views |
|---|---|---|
| 1. Keel block rust: yes | The block under the bow (the base model's `Underside_Front`: islands 1147-1149, 8,381 faces) is drawn rust (`DM_Rust`'s colour, 0.50 / 0.20 / 0.12) in the "after" renders. Its geometry, UVs and material slot (`M_Airship`) are unchanged: it is a colour override, kept in a small registry like the base edits (`scripts/base_recolor/z4.json`, island ids with face and triangle guards, read by `r3_base_recolor.py`). The renders, the assembler and the bake all read it. In the full file `SM_Airship` carries it as a face attribute `r3_recolor` plus `SM_Airship['round3_base_recolor']`. In the game it is palette slot `keel_block` (EXPORT_R3.md, slot 16), default rust, a live knob. The block's own rust plates now only show by their outlines; its dark-rust and grey plates still read. | `keel_low`, `side`, `q34_fp`, `below` |
| 2. Blade collar and tip caps: yes | On both rotors (bone `Turbine_X_Rotor`, objects `SM_AirshipDetail_Z6_Rotor_L` / `_R`): a riveted rust collar ring round the hub where the slats start (r 0.79-0.95 m, 28 rivets on its aft face, which you see from behind), a machinery-grey cuff on every slat where it leaves the collar, and a riveted steel cap on every slat end (`DM_Steel`). The slats themselves are the base model's (no twist / spinner pass). +3,920 triangles per rotor (216 -> 4,136). | `fan_close_L`, `talal_back`, `pilot_45` |
| 3. Hand rails: steel | The top rails of both flights and the landing are a steel tube (`DM_Steel`, 5.2 cm, 10 sides, was a 6.8 cm wooden rail) sitting in a small dark saddle on every post. Posts, mid rails, stringers and treads are unchanged. The collision boxes do not change (`stairs_collision.json` has the same md5). | `stairs_close`, `deck_eye`, `top` |

Choices made for you (each a knob in the zone scripts):

* **Caps, not a shroud band** (`detail_z6.py` `K['rotor']['tips']`). Both were built and rendered (`rig/tmp/r3ans/cmp/`).
  From behind at 40-75 m the caps read as a ring of bright tips round the blade disc, and close up as finished slat
  ends. The thin shroud band merged with the duct wall and the dark liner.
* **The caps leave the front 8 cm of each slat end bare** (`skip_fwd`). The base model's fan-mount pylon reaches into
  the duct just in front of the blade disc. At full yaw (+-12 degrees) it passes 2.7 mm from the slat tips' front
  corners: a cap round the whole tip touched it. That was 33 new contacts per fan in the rig check. The caps now wrap
  the slat end from 8 cm behind its front edge to past its back edge. Every rotor piece is tested against everything
  on the hull side, swept through a full rotor turn and the whole yaw range: 2.1 cm clear, 1.9 cm from the duct wall.
  From behind and from the intake they read as caps. Only a close look at one tip shows the bare front strip
  (`rig/tmp/r3ans/cmp/tips_back_toon_after_caps3.jpg`).
* **Steel, not dark** (`detail_z7.py` `K['stairs']['rail']['mat']`). Both were rendered. Steel is what you asked for
  and reads as a light line over the rust stringers and dark posts. Dark makes one frame with the posts and the
  ship's other rails. `--rail-mat dark_metal` builds the dark one.
* **Cuffs machinery grey** (dark cuffs on the dark slats only showed by their outlines).

Checks: zones 6 and 7 rebuilt twice, identical geometry each time. Zone checks pass. Zone rig checks pass (zone 6
also passes the swept test). Against the previous zone files only `Rotor_L`, `Rotor_R` and `Stairs` changed: every
other object has the same geometry fingerprint. The full file has all 34 objects identical to their zone hashes. Objects
are ok, 0 floating, 0 overlaps between zones, 0 with props or turrets, 0 in the keep-clear volumes. The walkable
check is the same as before (only the known ChainAft and guard-rail tips). The stairs check passes. The full rig
check passes. Protected files: same md5 at the start and the end.

Renders (all looked at, deck ink mask on): every toon view of the sheet again, before and after (`side`,
`side_stbd`, `top`, `q34_fp`, `q34_rs`, `talal_back`, `below`, `deck_eye`, `pilot_45`, `pilot_45q`, `transom_rear`,
`belly_port`, `stairs_close`, `fan_close_L`), plus `keel_low` (now a sheet row) and clay `q34_fp` / `below`. The
"before" images show the ship as it is, with the grey block and no details. The option comparisons (caps / shroud,
steel / dark) are in `rig/tmp/r3ans/cmp/`.

## 6. For the Unreal stage

**Objects.** 34 detail objects in collections `Detail_Z1` .. `Detail_Z7`, all named `SM_AirshipDetail_ZN_<Part>`,
parented to `Armature` with an Armature modifier, every vertex 100 % on one bone:

| Bone | Objects |
|---|---|
| `Hull` | Z1_Hull, Z2_Hull, Z3_Hull, Z4_Hull, Z4_Wedge, Z4_Keel, Z5_Belly, Z6_Hull, Z7_Stairs, Z7_Gantry, Z7_Rails, Z7_Chains |
| `Thruster_FL` / `FR` / `RL` / `RR` | Z1_Pod_FL, Z2_Pod_FR, Z3_Pod_RL, Z3_Pod_RR |
| `Thruster_XX_Nozzle` | Z1_Nozzle_FL, Z2_Nozzle_FR, Z3_Nozzle_RL, Z3_Nozzle_RR |
| `Thruster_XX_Petal00` .. `11` | Z1_Petals_FL, Z2_Petals_FR, Z3_Petals_RL, Z3_Petals_RR (one vertex group per petal) |
| `Turbine_L` / `R`, `_Rotor`, `_Rod` | Z6_Turbine_L / R, Z6_Rotor_L / R, Z6_Rod_L / R |
| `Rudder` | Z6_Rudder |
| `SearchLight_*`, `SearchLight_*_Head` | Z7_LightPosts, Z7_LightHeads |
| `Winch_Aft`, `Winch_Fwd` | Z7_Winches |

**Role materials.** 12 materials `DM_*`, one per role, in a fixed order. Each carries the custom properties
`palette_key` and `role`. The colour comes from the role (ZONES.md section 5). Rivet faces carry a Freestyle face
mark: the bake should draw rivets as dots, not as outlined shapes.

**UVs and bake.** The detail objects have no UV map yet. They need their own atlas and the comic bake.

**Base colour override** (2026-11-28, section 5a): `SM_Airship`'s keel block (`Underside_Front`, 8,381 faces / 8,998
triangles) is palette slot `keel_block`, default rust (EXPORT_R3.md slot 16). In the full file it is the face
attribute `r3_recolor` (1 = the entry in `SM_Airship['round3_base_recolor']`). The bake / prep reads it with
`r3_base_recolor.read_from_object` (full file) or `detail_render.ship_face_classes()` (rig + registry), which already
returns `keel_block` for those faces. No geometry, UV or material-slot change, so nothing for `rig_export.py`.

**Base edits** (applied in the full file, listed in `SM_Airship['round3_base_edits']`):

| Id | What goes | Faces / tris | Physics |
|---|---|---:|---|
| `z6_fan_back_L` | port fan: back disc + tail cone (islands 1028, 1030) | 60 / 216 | no PA box there |
| `z6_fan_back_R` | starboard fan: the same (islands 1088, 1091) | 60 / 216 | no PA box there |
| `z7_chain_aft_bars` | the six ChainAft bars (islands 379-384), replaced by `Z7_Chains` | 36 / 72 | no PA box there |

* No rail and no deck piece was removed for the stairs (the turret deck's aft edge had no rail there). The crates
  `Hull_Props_02 .. 06` stay.
* `rig_export.py` and `verify_import.py` only know round 2's `deck_removals.json`. Add these three edits.
* Re-bake SM_Airship's comic ink locally where the deleted parts stood (as round 2 did): each fan's inner duct wall
  at x -17.8 .. -17.9, the hub's rear face and the duct exit; the ChainAft line at x 12.2 .. 16.2.

**Stairs collision.** Add the 16 boxes of `stairs_collision.json` to PA_Airship's hull body: 2 walkable ramps
(36.1 degrees), the landing and the top step (walkable), 12 blocking boxes (hand rails, landing columns, the two guard
rails). The ramp's foot sinks into the deck boxes and the top step overlaps `Hull_Platform_00_0`, on purpose. Without
these boxes players walk through the stairs.

**Export.**
* `rig_export.py` opens `rig/AirshipRig.blend` and asserts 31 meshes. The full file has 65 (31 + 34 details), and
  `SM_Airship` still sorts first, so its material stays slot 0. Point it at `AirshipRig_detail_full.blend` and change
  the count, or merge the details first.
* Merging cuts draw calls. 34 objects with up to 12 materials each make many mesh sections. Merging per bone gives
  one Hull detail mesh (259k triangles), one per pod, nozzle and petal set, fan, rotor, rod, the rudder, the lights
  and the winches.
* The zone 1 inside-out fix is already in the full file. Nothing else needs flipping.
* The turrets are separate props (`BP_AirshipTurret`). They are not changed and not in the SK.

**LOD ideas.** LOD1 drops the rivets and the pieces under 15 cm: 254k detail triangles, SK about 357k. LOD2 keeps
only pieces of 0.6 m and more: 181k, SK about 284k. The rotors' new collar, cuffs and tip caps (3,920 triangles per
rotor) spin with the rotor bone; their rivets drop at LOD1 like the others. Rivets are easy to drop by their Freestyle face mark. Pieces are
the loose parts of each object. You fly with the camera 40-120 m behind the ship, where rivets and pieces under
15 cm are below a pixel: set the LOD1 screen size so it is active from about 30 m and LOD2 from about 80 m. LOD0
then only serves players on the deck.

**Sections and skinning.** 34 objects with up to 12 role materials add at least 12 mesh sections, and about 257k
Hull-bone triangles (258k now) would be GPU-skinned every frame although they never move against the hull. Two options for the
export stage: fold the 12 `DM_*` roles into one material with a palette or atlas texture (the comic bake needs UVs
anyway), and export the 12 Hull-bone detail objects as one static mesh on a Hull bone socket, keeping only the moving
parts' details in SK_Airship.

**Backfaces.** A ray-cast survey (review, 11 views) found the details clean apart from one search-light hood cap,
now fixed. SM_Airship itself shows backfaces round the pods (base model, not round 3): make its material two-sided
in Unreal or flip those faces in the base.

## 7. Commands

```
B=/mnt/new_partition/UnrealProjects/_AirshipWork_logs/blender_capped.sh
S=/mnt/new_partition/UnrealProjects/_AirshipWork/SourceArt/Airship/scripts
Z=/mnt/new_partition/BlenderProjects/StylizedAirship/rig/detail/zones
D=/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/round3
R=/mnt/new_partition/BlenderProjects/StylizedAirship/rig/AirshipRig.blend
$B --python $S/detail_assemble.py                    # 45 s: full .blend + full_report.json
$B --python $S/detail_assemble.py -- --verify        # reopen the saved file -> full_verify.json
$B --python $S/detail_hash.py -- --blend $Z/AirshipRig_detail_full.blend --prefix SM_AirshipDetail_ --out $Z/full_hash.json
$B --python $S/detail_assemble.py -- --tool rigcheck --blend $R --zones 1,2,3,4,5,6,7 \
   --sets pod:FL,pod:FR,pod:RL,pod:RR,turbine:L,turbine:R,rudder,searchlights,chain,cannons,turrets --out $D/full_rigcheck.json
BL_MEM_MAX=5G $B --python $S/detail_assemble.py -- --tool render --blend $R --zones 1,2,3,4,5,6,7 --look toon \
   --states before,after --shots-file $D/media/full/full_shots.json --shots side,side_stbd --out $D/media/full
#   also: top,q34_fp,q34_rs / talal_back,below,deck_eye (a run per 2-3 shots; toon renders need about 3.7 GB)
DETAIL_ASSEMBLE_CPU=1 BL_MEM_MAX=5G $B --python $S/detail_assemble.py -- --tool render --blend $R --zones 1,2,3,4,5,6,7 \
   --look clay --samples 32 --states before,after --shots-file $D/media/full/full_shots.json --shots q34_fp,below --out $D/media/full
python3 -B $S/detail_full_sheet.py
```

`--tool rigcheck` and `--tool render` run the shared tools on the rig plus the seven zone files, with the base edits
in memory. That is the same content as the full file, and the renders still have the unedited ship for "before".
`--tool render` keeps the ink off the plain deck by default (section 8); `--deck-ink raw` renders the old way.
`DETAIL_ASSEMBLE_CPU=1` renders clay on the CPU with no GPU context at all. The GPU was full today because an Unreal
editor was running.

After your answers (section 5a): `$B --python $S/r3_base_recolor.py -- --list` (the colour overrides with their guard
counts); per-zone checks with `_AirshipWork_logs/r3ans/verify_zone.sh 6 "--zones 1 --only Detail_Z6 --sets
turbine:L,turbine:R,rudder"` and `... 7 "--zones 1 --only Detail_Z7 --sets searchlights,chain,turrets,cannons"`;
renders `_AirshipWork_logs/r3ans/render_r3ans.sh A|B|C|D|E`. `--tool render` draws the overrides in the "after" state
(`--base-recolor none` leaves them out).

The review fix round's extra views: `--shots-file $D/media/full/fix_shots.json --shots pilot_45,pilot_45q,transom_rear,
belly_port,stairs_close,fan_close_L` (sheet rows) and `rudder_close,fan_side_L,fwd_wall_stbd,chain_aft,keel_low`
(the fixes' own close-ups, `media/full/`). Per-zone rebuild and checks: each zone doc's commands; the round used
`_AirshipWork_logs/fix_logs/verify_zone.sh N "<rigcheck args>"` (hash, a second build into rig/tmp compared for
determinism, zone checks, zone rig check).

## 8. Review fixes (2026-11-28)

A review of the assembled ship, made for you as art director, listed 5 major and 10 minor points. This round fixed
every major one and the cheap minor ones, in the zone scripts that own them (zones 4, 5, 6, 7) and in the assembler.
Zones 1, 2 and 3 did not change. The previous sheet is `media/full/full_sheet_pass1.jpg`.

| # | Point (zone) | Done | What changed, or why not |
|---|---|---|---|
| 1 | Major. The stern reads as a face from the chase camera: two dark square-lidded bays as eyes, the rudder as a nose, the 2 + 2 straps on the long low panel as teeth, stacks of small tiles beside the rudder (Z6) | fixed | The two transom bays are gone. Port: a pipe header under the deck edge (copper and brass, flanges, clamps, a valve, glands). Starboard: a riser pair down the outboard column. Each side is plated with its own random stream. The columns beside the rudder have one or two tall plates with a riveted rust rib. Nothing under 0.5 x 0.38 m, no picture frames on the transom, one slotted plate, patches only low at a plate's end. The long low panel is plain like your raised panels (the rudder's swing would split any strap into a pair of bars). Views: sheet rows 7-9, `transom_rear`. |
| 2 | Major. The belly chains are not heavy or purposeful: two swags between padeyes on the keel, 3.2 cm wire; thin sagging hoses (Z5, Z7 ChainAft) | fixed | The two keel swags are dropped. The hoses are thicker (r 9 cm, was 7.5) and sag 0.26 m (was 0.55). ChainAft beside the bow is a heavy chain: 0.55 m links, 9 cm thick wire (was 0.30 m, 6.4 cm). Nothing hangs below the hull line from the side any more. One purposeful belly chain is a question for you (section 5). |
| 3 | Major. Stray ink dashes on the main deck in the "after" views (render tool) | fixed | `detail_assemble.py --tool render` draws the Freestyle ink as its own pass and keeps it off deck pixels: an AOV mask of the toon deck material, shrunk by 3 px so the outlines of crates, rails, the helm and the stairs stay whole. All sheet views were rendered again, before and after, the same way. Preview only. |
| 4 | Major. The fore deck's side walls read as lettering, "Z [] Z []" (Z7) | fixed | No slotted plates on the 0.8 m walls (the 0.5 m edge beams keep one each). Every fascia patch is low and wide, on the plate's bottom edge at one end, never centred. View: `fwd_wall_stbd`, sheet row 2. |
| 5 | Major. Belly frames end in the middle of the skin under raised rust plates: "signs on posts" along each flank (Z5) | fixed | A riveted rust bilge stringer per side (16 cm wide, 10 cm proud) where it crosses the most frames: port x -14.3 .. -9.8 and -5.6 .. 1.1, starboard x -14.3 .. 0.65. 12 of the 17 frames end on it; the 5 that stop at a pod's pocket end in a sniped knee (the last 0.30 m lower and tapering). No raised rust armour within 0.5 m of a frame's end. Views: sheet rows 1, 2, 10, 11. |
| 6 | Minor. The grey keel block under the bow reads as a sticker collage (Z4) | partly fixed (block rust since your answer, 5a) | Its plates are now mostly rust like the wedge (rust dark 40 %, rust 20 %, grey 32 %, dark 8 %; was grey 75 %, dark 25 %), and no dark plates read as hatches any more. The three wrap bands per half now run out from the keel angle and stop where the block gets lumpy, so they stay short on this lumpy block. Between the plates the block's own base colour still shows: it is the base model's grey (`Underside_Front`), so from below it is still a grey patch with rust plates. Whether the block itself should be rust is a question for you (section 5). The wedge was rebuilt too (the heavier chain is one of its obstacles): its top angle iron starts 5 cm further forward and its random layers re-rolled with the same rules. View: `keel_low`. |
| 7 | Minor. The rudder reads as a panelled cabinet door (Z6) | fixed | 7 plates per face (was 13), a 20 cm riveted edge band (was 14), 2 ribs (was 4), one diagonal riveted rust brace per face under the tiller bar, the slotted plate kept. View: `rudder_close`. |
| 8 | Minor. The stairs are not on the centre line, but the docs say "up the middle" (Z7 docs) | fixed | Section 1 and `ZONE_7.md` now say 0.6 m to port of the centre line, in the gap between the crates. True centring would mean moving the crates and their PA boxes. |
| 9 | Minor. The fan blades are crude next to the plated duct now that they show (Z6) | done after your answer (5a) | Optional, and a change to the rotor that turns at speed. It is a question for you (section 5): a blade-root collar ring and tip caps, or a twist / spinner pass later. |
| 10 | Minor. The rear pods' fronts are plainer than FL's (Z3) | not fixed | Already your question 1 from zone 3. Filling the gap needs per-pod tuning of the hug pipes and actuators and a new 243-pose sweep per pod; it is a look question first. |
| 11 | Minor. The fan housings' bays read as windows on a tower from the side (Z6) | fixed | Their floors are ochre and their lids machinery grey (were dark floor, dark lids), so no dark square faces out. View: `fan_side_L`, sheet rows 1 and 2. |
| 12 | Minor. The sheet has no chase-camera view, stern view or close-ups | fixed | New rows: chase camera at 45 m (straight and 30 degrees to port), the stern from behind at 15 m, the belly from port, and close-ups of the stairs and the port fan's exhaust. |
| 13 | Minor. Rivets and small pieces are sub-pixel at 40-120 m (Unreal LOD) | noted | Section 6: LOD1 from about 30 m, LOD2 from about 80 m. For the export stage. |
| 14 | Minor. Many mesh sections, and 257k Hull-bone triangles skinned for nothing (Unreal export) | noted | Section 6: one palette material instead of 12 roles; the Hull-bone details as one static mesh on a socket. For the export stage. |
| 15 | Minor. Backfaces: one search-light hood cap; SM_Airship faces round the pods (info) | fixed / noted | The hood's two end caps now wind opposite ways (both had the same winding). The pod-area faces are the base model's (section 6). |

**Checks after the fixes** (all on the assembly with the base edits applied):
* Identity: all 34 detail objects match their zone's new hash file. Zones 4, 5, 6 and 7 rebuilt twice: IDENTICAL
  GEOMETRY each time. Zone checks and zone rig checks (`z4_*` .. `z7_*.json`) pass.
* Objects ok (after zone 1's inside-out flip), 0 floating of 12,955 pieces, 0 overlaps between zones, 0 with props or
  turrets, 0 in the keep-clear volumes. Stairs unchanged (same hash, same `stairs_collision.json`).
* Full rig check: PASS (section 4). Reopen check: `full_verify.json`, 65 rig meshes, `SM_Airship` first, all detail
  objects ok. Fingerprint: `rig/detail/zones/full_hash.json`.
* Walkable: free vertices only on the ChainAft (section 5, point 1) and the 12 guard-rail tip vertices (point 2).
* Protected files: the same md5 at the start and the end of every run.

**Renders** (`media/full/`, all looked at): the 10 sheet views again (toon before / after with the deck ink mask;
clay before / after), the new sheet rows (`pilot_45`, `pilot_45q`, `transom_rear`, `belly_port`, `stairs_close`,
`fan_close_L`) and the fixes' own close-ups (`rudder_close`, `fan_side_L`, `fwd_wall_stbd`, `chain_aft`, `keel_low`),
before / after. Cameras: `full_shots.json`, `fix_shots.json`.
