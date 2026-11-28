# Airship detail pass, zone 7: gantry, turret deck and stairs

Zone 7 is the gantry at the bow: the truss, the forward turret deck on top of it, its legs, the four search lights,
the two winches, the chains and hang strips, and the rails along the whole ship. It also carries Talal's point 3 of
2026-11-28: stairs from the main deck up to the forward turret deck, "where looks better".

Sheet: `media/z7/z7_sheet.jpg` (before / after, stairs options, close-ups). Toon is the final look. Zone 1 is loaded in
every render, and the two turrets are placed read only.

## 00. Talal's answer of 2026-11-28 11:00: "make them steel" (the stair hand rails)

The top rails of both flights and of the landing are a steel tube (`DM_Steel`, r 2.6 cm, 10 sides; was a wooden rail,
r 3.4 cm, 8 sides) sitting in a small dark saddle on every post. Posts, mid rails, stringers and treads are
unchanged. The rail line stays 0.95 m above the nosings, so the collision boxes do not change
(`stairs_collision.json`: same md5). Stairs triangles 4,932 -> 5,804. Knob: `detail_z7.py`
`K['stairs']['rail']`. Steel and dark (`DM_Dark`) were both rendered (`rig/tmp/r3ans/cmp/cmpz7_*`). Steel was kept: it
is what Talal asked for and reads as a light line over the rust stringers and dark posts. Dark makes one frame with
the posts and the ship's other rails (`--rail-mat dark_metal`). Code: `detail_z7_stairs.handrail` / `landing_rails`
(`rail` argument; without it the old wooden rail). Checks: rebuilt twice, identical; zone checks pass; rig check
PASS. Against the previous file only the `Stairs` object changed. The guard rails now butt into the steel rail and
its top saddle: 40 triangle pairs, on purpose (32 before).

## 0. Review fixes (2026-11-28, after the whole-ship review)

The numbers further down are from the first build; these changes came after it (`FULL.md` section 8).

* **Fore deck walls: no more "lettering".** On the 0.8 m walls of the raised fore deck the narrow slotted plates
  (their slots merged into one slanted bar) next to framed plates with a small centred rust square read as
  "Z [] Z []". The walls now have no slotted plates (the 0.5 m edge beams keep one each). Patches on every fascia plate
  are low and wide, on the plate's bottom edge at one end, never centred.
* **ChainAft is a heavy chain now:** links 0.55 m long, wire 9 cm thick (was 0.30 m and 6.4 cm), 6-sided section,
  14 links on the same line. PA_Airship still has no box for it.
* **Search light hoods:** one end cap of each hood faced inward (a backface Unreal would cull). Both caps now face
  out.
* **Stairs wording:** the stairs are 0.6 m to port of the centre line, in the gap between the crates (section 1). The
  stairs themselves did not change (same geometry hash, same `stairs_collision.json`).
* Zone 7 is now 45,230 triangles: Gantry 28,830, Chains 1,008, the rest unchanged.
* Checks after the fixes: all objects ok, determinism IDENTICAL GEOMETRY, walk check 0 free-standing, rig check
  (`z7_rigcheck.json`, `full_rigcheck.json`).

## 1. The stairs

### Where, and why

I mocked three places with simple boxes (`media/z7/stairs_options/`, eye height 1.6 m on the main deck and 25 m 3/4):

| Option | What it is | Verdict |
|---|---|---|
| **central** (chosen) | two straight flights near the deck's centre line (0.6 m to port of it, in the gap between the crates), a landing half way, arriving at the turret deck's aft edge 0.6 m to port of its middle | reads as a planned companionway from the helm; meets every number; removes nothing |
| port side | one long flight along the port side, outboard of the crates, then a landing that turns in to the deck | crate 4 cm from the stringer, foot inside cannon L1's sweep, 19 risers with no landing, looks bolted on |
| across | one flight across the gantry's aft face, port to starboard, landing at the starboard corner | landing opening only 1.05 m, foot 0.6 m from the port rail, blocks the walk under the gantry |

Why central:
* It looks intended. From the helm you see it almost straight ahead, rising between the gantry's legs.
* It is not exactly on the centre line: its middle is at y +0.63 (UE y -63 cm), 0.6 m to port, because that is where
  the gap between the crates is. True centring would mean moving the crates `Hull_Props_02 .. 06` (a base edit plus
  their PA boxes). (Review note 2026-11-28.)
* It arrives where the turret deck's aft edge is open. No rail is cut, no crate moves, no base edit is needed for it.
* It keeps both side walkways and the walk under the gantry free, and stays out of the cannon sweeps and the helm.

### Numbers

| Item | Value | Limit |
|---|---|---|
| Rise | 4.155 m (main deck 2.394 to turret deck 6.550) | |
| Risers | 19 x 0.219 m (10 to the landing, 9 to the deck) | <= 0.22 m |
| Going (tread depth) | 0.30 m, 2.5 cm nosing | >= 0.28 m |
| Slope | 36.1 deg | <= 38 deg |
| Clear width | 1.50 m between the stringers; 1.55 m measured between the hand rails | >= 1.4 m |
| Head room | nothing above the whole flight (open sky) | >= 2.2 m |
| Landing | 1.50 x 1.70 m at 4.58 m, on four columns | |
| Footprint | x 3.4 .. 10.5, y -0.22 .. 1.48 (crates 0.19 m away on both sides) | inside the Z7 stairs box |

The top opens straight onto the turret deck (the deck's aft edge at x 10.5). New guard rails run along the rest of
that aft edge, from the stair rails to the deck's corner posts: the edge was a 4.2 m drop with no rail. They match the
deck's own rails (posts 9 cm, bars at 1.10 / 0.55 m above the deck). They are kind `guard` in `..._Rails`, easy to drop.

### How it is built (reference 1)

Rust steel channel stringers (web, top and bottom flanges, a rivet row every 28 cm), open treads (dark steel tray,
three wooden planks, a rust nosing angle with two rivets), wooden hand rails on dark steel posts, a steel mid rail.
The landing is a rust channel frame with plank decking on four round columns, with riveted foot plates, a band on
each column and X braces on the two outer sides. Riveted foot plates under the stringers on the deck, and riveted
cleats where the upper stringers meet the deck edge.

### Collision for Unreal

`stairs_collision.json` (UE cm, ship component space, the `pa_hull_boxes.json` convention). Each box has its centre,
full size, rotation (pitch) and its 8 corners:
* `Stairs_Ramp1`, `Stairs_Ramp2`: walkable ramps, top face through the tread nosings, 36.1 deg (walkable limit 44.76).
* `Stairs_Landing`, `Stairs_TopStep`: walkable (the top step bridges the 5 cm between the deck edge, UE x 1050, and
  the deck box `Hull_Platform_00_0`, which starts at 1055).
* Blocking: 6 hand rail boxes, 4 landing columns, 2 guard rails.
* `rail_pieces_removed`: none. The crates (`Hull_Props_02 .. 06`) stay.

The stairs are one object, `SM_AirshipDetail_Z7_Stairs`, on the Hull bone. These boxes go on PA_Airship's hull body.

## 2. The rest of the zone

Same language as zone 1: colour by role, three depth levels, rivets only on gussets, ribs, straps, corners and flanges.

* **Truss.** Rust gusset plates over all 44 joints on the outer faces (6-sided, 4 rivets each), rivet rows on the
  bottom chords. Knee gussets where the legs meet the bottom chord.
* **Deck edge (fascia).** One row of yellow / ochre base plates on the edge beams and on the raised fore deck's
  walls, with rust frame ribs over 26 of the seams: 42 plates, 15 calm (36 %), 6 picture frames, 11 patches,
  5 slotted plates, 5 rust armour (12 %). The walls are left bare 0.28 m around the MidL / MidR posts (see section 4).
  Riveted rust straps on the deck slab's tapered bow edge and on its aft face (split where the stairs arrive).
* **Under the turret deck** (what you see from the main deck): 15 I-beam joists between the cross beams, a cable tray
  down the middle with three junction housings (hinged lids facing down), two turret drive housings under the
  mounts, and two pipe pairs (copper r 6.5 cm, brass r 5 cm) with flanges and clamps hung from the joists.
* **Legs ("tower").** Riveted bands on all four legs. Each aft leg has a pump housing (hinged, latched lid). Its pipe
  pair climbs the leg, rises straight up inside the truss and runs forward under the deck: port pair into the winch
  motor box (glands), starboard pair into the starboard turret drive.
* **Search lights** (4). Posts: a riveted sleeve near the foot, a junction box with a brass conduit up to a riveted
  collar under the head. Heads: brass bezel, hood, two cooling fins, rear cap with a cable gland, yoke with trunnions
  and a turntable ring, a handle. Posts on their post bones, heads on their `_Head` bones.
* **Winches.** Bolt circles on the outer flanges. Round bearing bosses and riveted hangers on the Hull. A ridged rope
  layer on `Winch_Aft` only: `Winch_Fwd`'s drum already runs through the bottom cross beam at x 30.6 (base model), so
  a spinning rope there would rub it.
* **Chain.** The chain beside the bow (`ChainAft`, Hull bone) was six plain bars. It is now a heavy link chain
  (26 links, 0.30 m) along the same line, with riveted brackets at both ends. This is the zone's one base edit
  (`base_edits/z7.json`, `z7_chain_aft_bars`, 36 faces / 72 tris, whole islands). `ChainFwd` stays as it is: it hangs
  inside the bow wedge (Z4) and does not show.
* **Hang strips.** Rust bands at the joints above the deck, cleats at the tops, and short beams out to the chord for
  the two strips that hung in the air inside the truss.
* **Rails** (whole ship). Rust collars where the bars meet the posts (290). None inside the turret and cannon sweeps
  (52 skipped).

## 3. Objects, bones, triangles

| Object (collection `Detail_Z7`, parent Armature, Armature modifier) | Bone(s) | Triangles |
|---|---|---:|
| `SM_AirshipDetail_Z7_Stairs` | Hull | 4,932 |
| `SM_AirshipDetail_Z7_Gantry` | Hull | 30,634 |
| `SM_AirshipDetail_Z7_Rails` | Hull | 3,588 |
| `SM_AirshipDetail_Z7_LightPosts` | SearchLight_AftL / MidL / MidR / FwdC | 2,128 |
| `SM_AirshipDetail_Z7_LightHeads` | SearchLight_*_Head | 3,072 |
| `SM_AirshipDetail_Z7_Winches` | Winch_Aft / Winch_Fwd | 1,672 |
| `SM_AirshipDetail_Z7_Chains` | Hull | 1,248 |
| **Total** | | **47,274** |

Rivets are 29.9 % of the triangles (zone 1: 24 %). Gantry by kind: rivets 11.6k, plates of all kinds (base, slotted,
frames, ribs, patches, armour, straps) 9.4k, pipes, clamps and glands 4.3k, housings and drives 2.2k, gussets 0.9k.

## 4. Checks (all in `z7_report.json`, `z7_checks.json`, `z7_rigcheck.json`)

| Check | Result |
|---|---|
| Safety | built with `blender_capped.sh` only; writes only `zones/AirshipRig_detail_z7.blend` and Z7 files. `AirshipRig_detail.blend` md5 31317912621726b5e647c78bfc0cf948 (unchanged); `AirshipRig.blend`, `AirshipRig_src.blend`, `StylizedAirship.blend`, `AirshipProps.blend` not written (dates before today) |
| Determinism | two builds: IDENTICAL GEOMETRY (`z7_hash.json`) |
| Objects | all 7 ok: 0 non-manifold edges, 0 vertices not 100 % on one bone, 0 faces without a role, 0 inside-out pieces (2 flipped in the build), names and collection right |
| Floating pieces | 0 removed (every piece touches the ship or another piece) |
| Rig: search lights | PASS: 216 poses (wobble +-4 x pan 0..345), 0 new contacts |
| Rig: chain + winches | PASS: 36 poses, 0 new contacts |
| Turrets | PASS: both swept through yaw and pitch, 0 overlaps, closest detail 0.34 m |
| Cannons | PASS: L1 / R1 closest 0.34 m, L2 / R2 0.40 m, 0 overlaps |
| Keep-clear | 0 vertices in the helm, turret or cannon volumes |
| Stairs | usability ok (table above); head room and clear width probed along both flights |
| Walkable | 0 details standing free on a walkable top (see below) |

**Walkable.** The shared PA check counts every vertex above any box top inside its footprint, which is true of the
whole gantry and of course the stairs. So the build runs its own check: a vertex inside a box footprint, less than
2.2 m above its top, and more than 0.2 m from existing non-walkable geometry (posts, legs, walls) would be "standing
free" on a walkable top. Result: 0. Left out on purpose: the stairs and the new guard rails (they get collision
boxes). Reported apart: underside pieces over the bow wedge's top (PA `Hull_Well` / `Hull_Bow`, z 4.28), which runs
inside the truss under the deck, and the search light yokes 1.98 m above the fore deck (above the 1.42 m mech).

**Ownership** (`zone_checks`): `outside_zone` Z4 6, none 84, None 28 (sampled every 2nd vertex). All explained:
* Z4 6: the lower ChainAft bracket on the bottom chord at x 16.2; the bow wedge's top (Z4) is nearer than the chord.
* none 84: the tops of the stair hand rails and the new guard rails, just above the turret deck's walkable top.
* None 28: guard rail collars more than 1 m from any ship face.
* `within_margin_of` Z4 412: the truss's bottom chord sits on the bow wedge (Z4), so its gussets and rivets are within
  10 cm of it. Z6 16: rail collars near the fans at the stern.

**Silhouette.** Details stay close to their parts: gantry p99 0.35 m from the ship (max 0.46: the pipes and drives
under the deck, inside the truss), light posts 0.15 m, heads 0.23 m, winches 0.05 m. The stairs and guard rails build
out into the open on purpose (stairs up to 2.5 m from any ship face).

## 5. Notes for the Unreal stage

1. Add the boxes of `stairs_collision.json` to PA_Airship (hull body). Without them players walk through the stairs.
2. The base edit `z7_chain_aft_bars` deletes the ChainAft bars. The comic ink near them needs the local re-bake, and
   the export stage must apply it (like the other round 3 edits). PA_Airship has no ChainAft boxes, so physics is
   unchanged.
3. Things in the base model I worked around, not fixed: `ChainFwd` hangs inside the bow wedge; `Winch_Fwd`'s drum
   runs through the bottom cross beam at x 30.6; the MidL / MidR posts run down through the fore deck and, as they
   wobble, swing inside it (so the wall stays bare 0.28 m around them); HangStrip_2 / _3 pass through the main deck.
4. The turrets are not clearly lower in detail than the hull. Nothing to report.

## 6. Questions for Talal

1. Do you want the new guard rails on the turret deck's aft edge? Without them, the edge beside the stairs is open.
2. Stairs colours: rust stringers, wooden treads and hand rails. Should the hand rails be steel instead of wood?
   Answered 2026-11-28: steel (section 00).

## 7. Files and commands

* Scripts: `detail_z7.py` (the build), `detail_z7_stairs.py` (plan, detailed stairs, collision), `detail_z7_mocks.py`
  (the three options), `detail_z7_sheet.py` (the sheet), `base_edits/z7.json`.
* Output: `rig/detail/zones/AirshipRig_detail_z7.blend`, `z7_hash.json`.
* Docs: `z7_report.json`, `z7_checks.json`, `z7_rigcheck.json`, `z7_hash.json`, `stairs_collision.json`, `media/z7/`.

```
B=/mnt/new_partition/UnrealProjects/_AirshipWork_logs/blender_capped.sh
S=/mnt/new_partition/UnrealProjects/_AirshipWork/SourceArt/Airship/scripts
Z=/mnt/new_partition/BlenderProjects/StylizedAirship/rig/detail/zones
D=/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/round3
$B --python $S/detail_z7.py                         # 7 s: the blend, z7_report.json, stairs_collision.json
$B --python $S/detail_checks.py -- --blend $Z/AirshipRig_detail_z7.blend --zone Z7 --out $D/z7_checks.json --sample 2
$B --python $S/detail_rigcheck.py -- --blend $Z/AirshipRig_detail_z7.blend --zones 1 --only Detail_Z7 \
   --sets searchlights,chain,turrets,cannons --out $D/z7_rigcheck.json
$B --python $S/detail_render.py -- --blend $Z/AirshipRig_detail_z7.blend --zones 1 --look toon --states before,after \
   --shots-file $D/media/z7/z7_shots.json --shots side_gantry,stairs_q34p,stairs_eye,foredeck,truss,under,q34_bow \
   --scale 75 --out $D/media/z7
$B --python $S/detail_z7_mocks.py                   # the three stairs mocks (rig/tmp/z7_mock_*.blend)
python3 -B $S/detail_z7_sheet.py
```
