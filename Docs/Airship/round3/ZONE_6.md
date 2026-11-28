# Airship detail pass, zone 6: stern and fans (open fan backs)

Zone 6 is the stern: both big side fans (turbines), their mounts, the transom and the rudder. It also carries
Talal's answer 4 (2026-11-28): "remove the back of the fans so that they are visible from back".

Sheet: `media/z6/z6_sheet.jpg` (all renders, before / after, final colours). Report: `z6_report.json`. Checks:
`z6_checks.json`. Rig check: `z6_rigcheck.json`. Geometry hash: `z6_hash.json`.

## 00. Talal's answer of 2026-11-28 11:00: blade collar and tip caps ("yes")

On both rotors (`SM_AirshipDetail_Z6_Rotor_L` / `_R`, bone `Turbine_X_Rotor`): a riveted rust collar ring round the hub
where the slats start (x -17.34 .. -16.88, r 0.79-0.95, 56 segments, 28 rivets on its aft face), a machinery-grey
cuff on every slat where it leaves the collar (r 0.90-1.04), and a riveted steel cap on every slat end (14 cm long,
`DM_Steel`). The slats are the base model's (no twist or spinner). Rotor triangles: 216 -> 4,136 each. Knobs:
`detail_z6.py` `K['rotor']`; code: `detail_z6_fan.build_rotor_blades`.

* **Caps, not a shroud band** (`tips`): both built and rendered (`rig/tmp/r3ans/cmp/`). The caps read as a ring of
  bright tips from behind at 40-75 m and as finished slat ends close up; the shroud merged with the duct wall.
* **Clearance.** The duct's inner wall is a 32-gon, inscribed radius 2.7747: every new vertex stays at r <= 2.756
  (1.9 cm, at every rotor angle). The base model's fan-mount pylon (`FanMount_X/pylon`, Hull bone) reaches into the
  duct just in front of the blade disc. At yaw +-12 it passes 2.7 mm (swept) from the slat tips' front corners.
  Caps round the whole tip touched it: the first rig check had 33 new contacts per fan. So the caps leave the front
  8 cm of each slat end bare (`skip_fwd`). Every rotor piece is now also tested against the Hull-bone geometry
  swept through a full rotor turn and the yaw range in 0.25-degree steps (`SweptHull`, margin 1 cm): 2.1 cm
  clear.
* Checks: rebuilt twice, identical; zone checks pass; rig check `turbine:L,turbine:R,rudder` PASS, 0 new contacts.
  Against the previous file only the two rotor objects changed.

## 0. Review fixes (2026-11-28, after the whole-ship review)

The numbers further down are from the first build; these changes came after it (`FULL.md` section 8).

* **Transom: no more "face".** From the chase camera the two dark bays with square lids under the deck edge read as a
  pair of eyes (cabin windows), with the rudder as a nose and the 2 + 2 straps on the long low panel as teeth.
  * The two bays are gone. The port side now has a pipe header under the deck edge (copper r 5.5 cm and brass r 4.5 cm,
    flanges, clamps, a valve, glands at both ends). The starboard side has a riser pair down its outboard column
    (copper and brass, clamps, a valve, glands). So the two sides carry different things.
  * Each side is plated with its own random stream, so the plate seams no longer mirror.
  * The narrow columns beside the rudder have one or two tall plates with a riveted rust rib between them (was a stack
    of small tiles). Nothing smaller than 0.5 x 0.38 m.
  * No picture frames on the transom, at most one slotted plate, and patches only low on a plate's bottom edge at one
    end (small framed squares side by side read as windows).
  * The long low panel stays plain, with corner rivets only, like your raised panels. The rudder's swing splits any
    strap across it into a pair of bars.
* **Fan housing bays:** ochre floor and machinery-grey lids (were a dark floor and dark lids). From the side they read
  as windows on a tower. They now read as machinery on a plate.
* **Rudder:** fewer, bigger plates (7 per face, was 13), a wider riveted edge band (20 cm), 2 dark ribs (was 4), one
  diagonal riveted rust brace per face under the tiller bar, and the slotted plate kept. It no longer reads as a
  panelled cabinet door.
* Zone 6 is now 53,078 triangles: Hull (transom, mounts) 6,812, rudder 6,784; the fans keep their triangle counts
  (only the bay colours changed). Rivets 29.8 %.
* Checks after the fixes: all objects ok, determinism IDENTICAL GEOMETRY, PA walkable tops 0, rig check (see
  `z6_rigcheck.json` and `full_rigcheck.json`).

## 1. The open fan backs (answer 4)

Each fan's back was closed twice: a flat disc right behind the blades (`duct_back_wall`) and the big cone with the
flat end that you saw in your screenshot (`tail_cone`, radius 2.46 m, sticking 1.15 m out of the duct). Both had to
go; the cone alone hides the blades as much as the disc.

* **Base edit** `SourceArt/Airship/scripts/base_edits/z6.json`, two entries:
  * `z6_fan_back_L`: FanHousing_L, islands 1028 + 1030, 60 faces, 216 triangles.
  * `z6_fan_back_R`: FanHousing_R, islands 1088 + 1091, 60 faces, 216 triangles.
  * Whole islands only. Open border edges of SM_Airship before / after: 294 / 294 (no new holes).
  * The duct (shell), the intake lip, the hub and the 28 blades stay as they were.
* **What a real ducted fan has at its exhaust** (detail objects, not SM_Airship geometry):
  * a dark **liner** inside the duct behind the blades, so the exhaust reads as a dark, solid tube;
  * thin **stiffener ribs** over the liner joints;
  * a **stator spider**: 5 rust struts on riveted feet, holding a small grey **bearing housing** (r 0.60 m, smaller
    than the hub, so the blades stay visible) with flanges and a **short tail cone** (ends at x -19.04; the old cone
    ended at -19.91);
  * a **riveted tail cap** on the hub's flat rear face (it turns with the rotor);
  * 16 riveted **rust rim segments** on the duct's rear face: the heavy exhaust rim.
* The duct wall was already a closed, thick shell, so no liner was needed to hide a void. The hub's rear face is now
  covered by the tail cap.
* From behind you now see the blades through the open exhaust, with the stator in front of them (renders
  `back_L`, `back_R`, `stern`, `talal_back`).

## 2. What else was built

| Object (collection `Detail_Z6`, parent `Armature`, Armature modifier) | Bone | Triangles |
|---|---|---:|
| `SM_AirshipDetail_Z6_Turbine_L` | `Turbine_L` | 19,482 |
| `SM_AirshipDetail_Z6_Turbine_R` | `Turbine_R` | 19,216 |
| `SM_AirshipDetail_Z6_Rotor_L` / `_R` | `Turbine_L_Rotor` / `Turbine_R_Rotor` | 216 each (4,136 since section 00) |
| `SM_AirshipDetail_Z6_Rod_L` / `_R` | `Turbine_L_Rod` / `Turbine_R_Rod` | 176 each |
| `SM_AirshipDetail_Z6_Rudder` | `Rudder` | 9,264 |
| `SM_AirshipDetail_Z6_Hull` (transom, fan mounts) | `Hull` | 8,830 |
| **Total** | | **57,576** |

Every vertex is 100 % on one bone.

**Fan housings** (both fans, same plan, own random seed each):
* Riveted rust **front rim band** right behind the intake lip (the reference's heavy riveted rim).
* Two **plate rows** in orange (the housing colour) and ochre, with the approved layers:
  * raised rust armour (1-2 per fan, 4-8 % of the plates);
  * picture frames (ochre on orange, orange on ochre);
  * rust patches;
  * slotted plates (2 on the starboard fan);
  * rust frame ribs over 7 seams per fan;
  * calm plates: 40 % of the plate area (port) and 35 % (starboard).
* A dark **gimbal track band** under the gimbal ring, and a rust **rear band**.
* Two **machinery bays** per fan, each with a riveted rust frame and a dark floor:
  * lower outboard bay: a housing with a hinged, latched lid, a gas bottle, and pipes into glands;
  * upper outboard bay: two housings joined by a flanged pipe with a valve.
* Rivets on the gimbal ring's aft face.
* Small support blocks under the top platform (it used to float 12 cm above the shell).

**Hanging rods:** a riveted end cap and a plumb weight at the lower end. There is no collar higher up, because the
rod passes through the gimbal ring there.

**Rudder** (both faces):
* a riveted dark edge band along the aft edges;
* 4 horizontal dark frame ribs;
* 26 plates in two rust tones;
* rust patches and one slotted plate per face;
* two clamp bands on the tiller bar.

Everything stays aft of x -16.75, so nothing swings into the transom at +-30 deg.

**Transom:**
* Free flat area: only narrow columns between your raised panels and the rudder (15.5 m2).
* 15 plates (2 rust armour, 4 patches, 1 frame, 1 slotted) and 4 rust frame ribs.
* One machinery bay each side under the deck edge: two housings, a valve, and a riser into a gland.
* Your raised panels stay as they are, with corner rivets only. A strap across them read as a door handle.
* The long low panel gets two riveted vertical straps.

**Fan mounts:**
* riveted rust straps and frame ribs on the open long face of each pylon;
* clamp bands on the struts (4 of 8 kept; the others hit the rails or the fan's yaw sweep).

Not in zone 6: `Winch_Aft` and `ChainAft` are at the bow, under the gantry (zone 7), not at the stern.

## 3. Colours (role materials)

* Fan plates: `DM_Orange` (the housing's own orange) and `DM_Ochre`.
* Rust (`DM_Rust`, `DM_RustDark`): straps, rims, struts, armour, patches, rudder plates.
* `DM_Dark`: liner, gimbal track, bay floors, rudder ribs and edge band.
* `DM_Machinery`: bearing housing, machinery housings, liner ribs.
* `DM_Copper` / `DM_Brass`: pipes and valves.
* `DM_Rivet`: rivets.
* Transom plates: `DM_Yellow` / `DM_Ochre`, as on zone 1.

Nothing from the never-add list: no teal bars, windows, hatches, portholes, round grilles, gear or ladders. Picture
frames on the rudder read as windows, so they were taken off there.

## 4. Checks (all pass)

| Check | Result |
|---|---|
| Objects (`detail_checks.object_report`) | all 8 ok: 0 non-manifold edges, 0 non-rigid vertices, 0 faces without a role, 0 inside-out pieces, names and collection right |
| Floating pieces | 0 removed (every piece touches the ship or another piece) |
| Determinism | two builds: `detail_hash.py` prints IDENTICAL GEOMETRY (`z6_hash.json`) |
| Rig check `turbine:L,turbine:R,rudder` with zone 1 loaded | PASS, 0 new contacts. Each turbine: 99 poses (yaw +-12 x rotor 0..345 every 15; yaw x rod swing +-20). Rudder: 13 poses (-30..30). The ship's own baselines are unchanged (housing vs hull 519 / 524 pairs, rudder vs hull 120). |
| Build-time tests | every piece was tested before it was kept against: the fan yaw at 7 angles, the rod swing at 9 poses, the rotor's swept volume, the rudder at 13 angles, the housing's own fittings, and the PA box tops. Rejected pieces are counted in `z6_report.json -> log.pieces`. |
| PA_Airship walkable tops | 0 vertices above a box top |
| Keep-clear (helm, turrets, cannons) | none. Every zone 6 detail is at least 2.9 m from cannon L2 / R2, outside their sweep, so no cannon set applies. |
| Ownership | outside_zone 0. on_seam_with Z3 11 / Z5 9 and within_margin_of Z3 50 / Z5 50 (sample every 2): all on the transom, next to the side walls of your raised transom panels. The zone map gives those walls to Z3 / Z5, because they do not face aft; physically they are part of the transom. |
| Silhouette (distance to SM_Airship) | hull details max 18.3 cm; rudder 12.8 cm; fan housing details outside the open exhaust max 19.1 cm (p99 17 cm); rotor tail cap 11.6 cm. Two things stand further out on purpose: the stator and bearing housing inside the open fan back (up to 1.27 m from the duct wall, inside zone 6's fan-back volume), and the plumb weights (41 cm below the rod's end). |
| Fan outline | outer-shell details stay well inside the gimbal ring (r 4.36). The bays stand about 20 cm off the shell. |
| Protected files | md5 unchanged: AirshipRig_detail.blend 31317912621726b5e647c78bfc0cf948, AirshipRig.blend, AirshipRig_src.blend, StylizedAirship.blend, AirshipProps.blend |

**Density.**
* Total: 57.6 k triangles.
* Per fan housing: about 19.5 k, close to the ~18.5 k budget per pod.
* Rivets: 31 % of the triangles (zone 1: 24 %). Each plate, strap and rib uses zone 1's rivet rules. The share is
  higher mainly because the plates here use coarser grids (fewer plate triangles).
* In the 5 m close-ups the rivets do not read as speckle.
* Knobs to lower the rivet share are in `K` (`detail_z6.py`):
  * the band rivet spacing in `detail_z6_fan.py` (`band('front', ..., 0.35)`);
  * `fan.ring_rivet_step`;
  * the rudder rib spacing.

## 5. Renders (`media/z6/`, final toon look, zone 1 loaded)

| File | View |
|---|---|
| `talal_back_toon_before/after` | your screenshot angle (behind-port, above the deck, looking forward at both fans) |
| `stern_toon_before/after` | straight from behind, both fans |
| `back_L_toon_before/after`, `back_R_toon_after` | each fan straight from behind (blades through the duct) |
| `side_L_toon_before/after` | port fan from the side |
| `q34_aft_hi_toon_before/after` | stern 3/4 from aft-port, high |
| `transom_close_toon_before/after`, `rudder_close_toon_after` | transom and rudder at about 5 m |
| `fan_close_L`, `fan_low_L`, `fan_front_L` (`_toon_after`) | port fan exhaust, from below, intake side |
| `*_toon_after_pose_poseA/B` | rig limits: A = yaw L +12 / R -12, rudder +30, rods +20; B = the opposite |
| `talal_back_clay_*`, `back_L_clay_*` | clay + cavity (Cycles, 32 samples) |

Zones 3 and 5 (the neighbours at the stern flanks and the belly) are not built yet, so there are no seam renders.
Zone 6 has no flank runs to continue.

## 6. How it is built

Scripts (`SourceArt/Airship/scripts/`), zone 6 only:

| Script | What it does |
|---|---|
| `detail_z6.py` | knobs `K`, the build, the per-piece tests, the report |
| `detail_z6_fan.py` | fan housing, exhaust, stator, rotor tail cap, rod weight; a free map of the outer shell per (x, angle) cell and height level |
| `detail_z6_stern.py` | transom chart and plates, the raised panels, fan mounts, rudder |
| `detail_z6_lib.py` | pose matrices, posed BVHs, piece tests, largest free rectangle, polygon helpers |
| `detail_z6_shots.json` | the zone 6 cameras (`talal_back` = your screenshot angle) |
| `detail_z6_sheet.py` | the sheet |
| `base_edits/z6.json` | the open fan backs |

```
B=/mnt/new_partition/UnrealProjects/_AirshipWork_logs/blender_capped.sh
S=/mnt/new_partition/UnrealProjects/_AirshipWork/SourceArt/Airship/scripts
Z=/mnt/new_partition/BlenderProjects/StylizedAirship/rig/detail/zones
D=/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/round3
$B --python $S/detail_z6.py                                     # about 1 min -> $Z/AirshipRig_detail_z6.blend, $D/z6_report.json
$B --python $S/detail_hash.py -- --blend $Z/AirshipRig_detail_z6.blend --prefix SM_AirshipDetail_Z6_ --out $Z/z6_rebuild_hash.json --compare $Z/z6_hash.json
$B --python $S/detail_checks.py -- --blend $Z/AirshipRig_detail_z6.blend --zone Z6 --out $D/z6_checks.json --sample 2
$B --python $S/detail_rigcheck.py -- --blend $Z/AirshipRig_detail_z6.blend --zones 1 --only Detail_Z6 --sets turbine:L,turbine:R,rudder --out $D/z6_rigcheck.json
$B --python $S/detail_render.py -- --blend $Z/AirshipRig_detail_z6.blend --zones 1 --look toon --states before,after \
   --shots talal_back,stern,back_L,side_L,q34_aft_hi,transom_close --shots-file $S/detail_z6_shots.json --out $D/media/z6
$B --python $S/detail_render.py -- ... --states after --pose '{"TurbineYawDeg_L": 12, "TurbineYawDeg_R": -12, "RudderDeg": 30}' --tag poseA
$B --python $S/detail_render.py -- ... --look clay --samples 32 --states before,after --shots talal_back,back_L
python3 -B $S/detail_z6_sheet.py
```

Seed 1306; a rebuild gives the same geometry.

## 7. Notes for the lead and open questions

1. **Export of the base edit.** `rig_export.py` and `verify_import.py` only know round 2's list; add `z6_fan_back_L`
   and `z6_fan_back_R`. The baked comic ink of SM_Airship near the deleted islands must be re-baked locally, like
   round 2 did. The old cone and disc sat against:
   * the duct's inner wall at x -17.8 .. -17.9;
   * the hub's rear face;
   * the duct exit.

   PA_Airship has no box for these parts, so collision does not change.
2. **PA check with stacked boxes.** `pa_report` counts a vertex as "above a box top" when it is above any box whose
   footprint holds it, even when it is inside a taller box there. The stern box `Hull_Stern_03_2` (top z 2.03) starts
   1.6 cm behind the flat transom (x -16.20), so every transom detail above z 2.03 would count. The transom details
   therefore keep all their vertices aft of x -16.19 (the plates sit 0.8 cm further off that face). Worth fixing in
   the shared check later.
3. **Zone map quirk.** The side walls of your raised transom panels are owned by Z3 / Z5 (rule 4 needs an aft-facing
   normal). Zone 6 details lie within 10 cm of them; that is the only "margin" count. Z3 and Z5 should not put details on those
   walls.
4. **The fan pylons.** Each pylon is a big box beam that runs into the duct, ahead of the blades (your original
   model). From the open back you can glimpse its end at the bottom of the duct. It does not touch the rotor (rotor vs
   hull baseline 0).
5. **Rivet share** is 31 % vs zone 1's 24 % (section 4). Say if the fans or the rudder look too riveted, and they can
   go down.
6. **Your raised transom panels** are kept plain (corner rivets only). Anything laid on them made them read as doors.
   Should they get something else, or stay as they are?
7. **Turrets:** not in this zone. Nothing to report.
