# Airship detail pass, zone 3: aft flanks and rear pods

Zone 3 is the back part of both hull flanks (aft of the cannon stations at x -11.55, down to the bilge line) and the
two rear thruster pods, RL (port) and RR (starboard), with their hull pockets. It uses zone 1's approved kinds,
sizes, colours and density, and continues zone 1's and zone 2's runs across the seam.

Sheet: `media/z3/z3_sheet.jpg` (before / after, final toon colours, zones 1, 2, 6 and 7 loaded so the seams show).
Report: `z3_report.json`. Checks: `z3_checks.json`. Rig check: `z3_rigcheck.json`. Lines for later zones:
`z3_continuity.json`. Geometry hash: `z3_hash.json` (copy of `rig/detail/zones/z3_hash.json`).

## 1. What was built

### Aft flanks (both sides)

The aft flank is short (about 3.5 m from the seam to the stern corner) and crowded. The fan mount pylon enters
the hull at x -14.1, the lower fan strut crosses the lower flank, the hull tapers hard (the skin faces aft-outboard),
and a 20 cm step in the skin runs diagonally across the lower flank. So the layout follows the ship's own bands, not
fixed heights.

Per side, from top to bottom:

* **Gussets** under the gunwale band on zone 1's grid (x -11.71, -12.22, -12.73, -13.24, -13.75).
* **Upper plate rows** between the gunwale band and the big steam pipe. Plates, one heavy rust armour plate, a
  slotted armour plate, picture frames, rust patches and frame ribs, like zone 1.
* **Conduit pair** (dark r 3 cm and brass r 2.6 cm) along the bottom of the upper rows. It comes out of glands at
  x -11.70, just aft of zone 1's glands at -11.15, so it reads as one line that dives through the hull. It ends
  in glands at the upper end rib.
* **Upper end rib**: a riveted rust rib just forward of the fan mount pylon (x -14.05 .. -13.87). The upper rows
  end on it.
* **Middle strip** (between the steam pipe and the lower band): small plates.
* **Strake and teeth**: the riveted rust strake with its big rectangular teeth on the dark backing, 3 segments per
  side. It is laid from the seam aft. The last segment ends at x -11.538, 8 mm from zone 1's (and zone 2's) first
  segment at -11.53, so the row of teeth runs on without a break.
* **Pipe channel**: the dark backing and the two big pipes (copper r 7 cm, brass r 5.8 cm), with flanges, clamps and
  a valve. The backing ends at -11.56. The pipes come out of glands at -11.70, so the run continues zone 1's /
  zone 2's channel through the hull between the glands.
* **One machinery bay per side**: a riveted rust frame round a dark floor, a housing with a hinged, latched lid, a
  rust gas bottle standing upright (the bay is too narrow for zone 1's pump), copper pipes, and a branch with a valve
  up to the channel. Port bay 1.34 x 1.16 m (zone 1's height), starboard 1.29 x 0.80 m (the skin step leaves less
  room).
* **Lower plate rows** under the channel and the bay, on both sides of the skin step.
* **End rib**: a riveted rust rib (18 cm wide, 12.5 cm off the skin) at x -14.75 .. -14.57. The strake, teeth and
  channel end on it. A few plates sit aft of it, up to the stern corner.

Nothing goes on the stern's aft-facing faces (zone 6), on the fan mount pylons and struts (zone 6, kept 12 cm off),
on the deck (kept 10 cm off) or below the bilge line (zone 5).

Balance per side, like zone 1: calm plates 31 % of the plate area on both sides (zone 1: 30 %), one heavy rust armour
plate per side (11 % / 8 % of the plates; zone 1: 2 of 49), one slotted plate, frames and patches, one frame rib.
The layout seed of each side was picked from 60 by a scan for these numbers.

### Rear pods RL and RR

Built with zone 1's pod code (`detail_pod.build_pod`): drum plates in rust, dark rust and dark metal (no yellow),
rivets on the ribs, the riveted ring band, lips, straps and patches on the three big plates, hinged and latched
lids on the side boxes, the pipe bundle, the junction housing, the two riveted steel hoops and the fins on the nozzle,
and a hinge barrel and an actuator on each petal.

What is different from FL:

* **Hug pipes and actuators face aft.** On FL they sit in the gap under the big plates on the front-outboard
  side. The rear pods sit deeper in the hull: there the gap is inside the hull's clearance (RL) or closed (RR).
  So both rear pods carry the same kit (two thick pipes hugging the drum, two actuators across them) on their aft
  side, the side you see from the stern quarters. RL: pipes 152..176 and 144..184 deg, actuators 154 / 162 deg.
  RR: pipes 160..196 and 140..200 deg, actuators 164 / 178 deg (pod frame, mirrored on starboard).
* **The pod's motion is tested at build time.** Every pod and nozzle piece is posed through the rig limits (pod
  pitch and roll +-3 deg, nozzle pitch and roll +-5 deg). Pieces that would touch the hull are removed, with their
  rivets, flanges and clamps. That removed 23 small pieces on RL (lip and patch pieces on the front plates' lower
  edges, which were already inside the hull skin) and 5 on RR, plus 6 nozzle rivets and one fin piece on RL.
* The front side of RL and RR is plainer than FL's (no hug pipes or actuators there). That is the hull clearance,
  not a choice.

### Pockets

* **Wall stiffeners**: zone 1's dark vertical straps on the pocket wall, riveted (24 in RL, 20 in RR).
* **Rust lip on the opening edge**: a riveted rust band on the pocket wall, just inside the opening. It follows the
  real edge of the opening, where the pod leaves room for it when it tilts (2 pieces per pocket). It reads as the
  rim strap from outside. Zone 1 / zone 2's plates come to 9 cm of the RL / RR opening, so the rim strap cannot sit
  on the outer skin there (ZONES.md, section 10).

Never-add list respected: no teal bars, no windows or hatches, no portholes, no round grilles, no gear, no ladders,
no chains.

## 2. Objects, bones, triangles

| Object (collection `Detail_Z3`, parent `Armature`, Armature modifier) | Bone(s) | Triangles |
|---|---|---:|
| `SM_AirshipDetail_Z3_Hull` | `Hull` | 24,758 |
| `SM_AirshipDetail_Z3_Pod_RL` | `Thruster_RL` | 11,388 |
| `SM_AirshipDetail_Z3_Nozzle_RL` | `Thruster_RL_Nozzle` | 2,056 |
| `SM_AirshipDetail_Z3_Petals_RL` | `Thruster_RL_Petal00` .. `11` | 4,032 |
| `SM_AirshipDetail_Z3_Pod_RR` | `Thruster_RR` | 11,642 |
| `SM_AirshipDetail_Z3_Nozzle_RR` | `Thruster_RR_Nozzle` | 2,160 |
| `SM_AirshipDetail_Z3_Petals_RR` | `Thruster_RR_Petal00` .. `11` | 4,032 |
| **Total** | | **60,068** |

Where they go: rivets 27 %, pod pipes and actuators 18 %, pod plates / lips / band / boxes 15 %, channel pipes,
conduits, clamps, glands and valves 10 %, pocket lips and stiffeners 8 %, machinery bays 6 %, nozzle hoops and fins
5 %, petals 5 %, flank plates of all kinds 4 %, strake and teeth 2 %.

**Density against zone 1:**
* Per pod (pod + nozzle + petals): RL 17,476 and RR 17,834 triangles. Zone 1's FL: 18,528.
* Flank details (hull object minus the pockets): 16,966 triangles on 106 m2 of zone 3 flank faces, 160 per m2. Zone 1:
  about 186 per m2 of its flank. The aft flank has more skin that cannot take plates (pylon root, strut, the skin
  step, the stern corner next to zone 6). Where there is room, the plates and layers are as dense as zone 1's.
* Rivets: 27 % of the triangles (zone 1: 24 %).

## 3. Checks (all pass)

| Check | Result |
|---|---|
| Safety | built only through `blender_capped.sh`. Writes only `rig/detail/zones/AirshipRig_detail_z3.blend` and zone 3 files. md5 unchanged: `AirshipRig_detail.blend` 31317912621726b5e647c78bfc0cf948, `AirshipRig.blend`, `AirshipRig_src.blend`, `StylizedAirship.blend`, `props/AirshipProps.blend` |
| Determinism | two builds: `detail_hash.py` prints IDENTICAL GEOMETRY (`z3_hash.json`, `z3_rebuild_hash.json`) |
| Objects | all 7 ok: 0 non-manifold edges, 0 vertices not 100 % on one bone, 0 faces without a role, 0 inside-out pieces (24 pod and 75 nozzle pieces, zone 1's kinds, flipped in the build), names and collection right |
| Floating pieces | 0 left (0 removed by `drop_floating`; the motion test removes a piece together with its rivets, flanges and clamps) |
| Rig: pod RL, pod RR | PASS, 243 poses each, 0 new contacts (zones 1, 2, 6 loaded as context) |
| Rig: turbine L, turbine R | PASS, 99 poses each, 0 new contacts |
| Cannons L2, R2 | PASS, 18 poses each, 0 overlaps, closest detail 1.11 m |
| Keep-clear (helm, turrets, cannons) | 0 vertices |
| Walkable (PA_Airship box tops) | 0 vertices above a box top |
| Silhouette, flank | details within 20.9 cm of the skin, p99 18.4 cm. Only 4 vertices of one channel valve pass 20 cm (the skin curves away under it at the stern) |
| Silhouette, pockets | within 6 cm of the pocket wall |
| Pod outline | grows by at most 8.3 cm (RL) and 9.9 cm (RR), from the lips and patches on the big plates (zone 1: 10.3 cm). Nozzle and petal details stay inside the outline |
| Ownership (`zone_checks`, every 2nd vertex) | `outside_zone` Z1 10, Z2 10; `on_seam_with` Z1 329, Z2 336; `within_margin_of` Z1 51, Z2 47, Z5 2; `keep_clear` none |

**Ownership, explained.** With every vertex tested (`z3_report.json` -> `checks.ownership_by_kind`), the 36
`outside_zone` vertices are all strake segments (22) and the channel backing (14) at the seam: they end at
x -11.538 and -11.56, as ZONES.md section 3 asks, and the big hull face that crosses the seam belongs to zone 1 /
zone 2 by its centre. The `within_margin_of` Z1 / Z2 vertices are the runs that continue across the seam. Z6 (4) and
Z5 (4): plate corners next to the fan mount pylon and next to the bilge line (zone 1 also runs its plates to the
bilge line).

## 4. Renders (`media/z3/`, final toon look, zones 1, 2, 6, 7 loaded)

| File | View |
|---|---|
| `q34_aft_port_toon_before/after`, `q34_aft_stbd_toon_*` | 3/4 from aft-port / aft-starboard, low, about 25 m |
| `side_aft_toon_*`, `side_aft_stbd_toon_*` | each aft flank from the side, orthographic |
| `close_aft_flank_toon_*`, `close_aft_flank_stbd_toon_*` | each aft flank, about 5.7 m |
| `close_rear_pod_toon_*`, `close_rear_pod_stbd_toon_*` | RL and RR from aft, about 7 m |
| `rear_pods_below_toon_*` | both rear pods from below and aft |
| `rear_pod_front_toon_*`, `pocket_RL_toon_*` | RL's front plates; the RL pocket wall and lip |
| `seam_z1z3_toon_*`, `seam_z2z3_toon_*`, `seam_z3z6_toon_*` | the seams with zones 1 and 2, and the aft end by the fan |
| `close_rear_pod_toon_after_poseARL / poseBRL` | rig limits on RL: A = pod +3 / +3, nozzle -5 / +5, petals +35; B = pod -3 / -3, nozzle +5 / -5, petals -10 |
| `q34_aft_port_clay_*`, `close_aft_flank_clay_*` | clay + cavity (Cycles) |

Cameras: `SourceArt/Airship/scripts/detail_z3_shots.json`.

## 5. How it is built

Scripts in `SourceArt/Airship/scripts/` (zone 3 only; the shared modules are only imported):

| Script | What it does |
|---|---|
| `detail_z3.py` | knobs `K` (zone 1's, plus what zone 3 needs), the build, the checks, the report |
| `detail_z3_flank.py` | the aft flank: a modified copy of zone 1's `build_flank`. Regions follow the ship's bands; masks keep off zone 6, the deck and zone 7; continuity at the seam; strake laid from the seam aft; end ribs; one bay per side; calm balance |
| `detail_z3_pod.py` | the rear pods' hug pipes and actuators (free angles per pod, tested through the pod's tilt), the pocket stiffeners and lip, the build-time motion test |
| `detail_z3_shots.json` | the zone 3 cameras |
| `detail_z3_sheet.py` | the sheet |

```
B=/mnt/new_partition/UnrealProjects/_AirshipWork_logs/blender_capped.sh
S=/mnt/new_partition/UnrealProjects/_AirshipWork/SourceArt/Airship/scripts
Z=/mnt/new_partition/BlenderProjects/StylizedAirship/rig/detail/zones
D=/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/round3
$B --python $S/detail_z3.py                                  # about 25 s -> $Z/AirshipRig_detail_z3.blend, $D/z3_report.json
$B --python $S/detail_hash.py -- --blend $Z/AirshipRig_detail_z3.blend --prefix SM_AirshipDetail_Z3_ --out $Z/z3_rebuild_hash.json --compare $Z/z3_hash.json
$B --python $S/detail_checks.py -- --blend $Z/AirshipRig_detail_z3.blend --zone Z3 --out $D/z3_checks.json --sample 2
$B --python $S/detail_rigcheck.py -- --blend $Z/AirshipRig_detail_z3.blend --zones 1,2,6 --only Detail_Z3 \
   --sets pod:RL,pod:RR,turbine:L,turbine:R,cannons:L2+R2 --out $D/z3_rigcheck.json
$B --python $S/detail_render.py -- --blend $Z/AirshipRig_detail_z3.blend --zones 1,2,6,7 --look toon --states before,after \
   --shots q34_aft_port,side_aft,close_aft_flank,close_rear_pod,rear_pods_below,seam_z1z3 --shots-file $S/detail_z3_shots.json --out $D/media/z3
$B --python $S/detail_render.py -- ... --states after --shots close_rear_pod --pose poseA:RL      # and poseB:RL
$B --python $S/detail_render.py -- ... --look clay --samples 32 --states before,after --shots q34_aft_port,close_aft_flank
python3 -B $S/detail_z3_sheet.py
```

Seeds: 1303 (pods, pockets), 1325 (port flank), 1311 (starboard flank). `--debug DIR` dumps the flank masks.

## 6. Notes for the lead and open questions

1. **Zone 2 seam.** The starboard seam reads `z2_continuity.json` as it was at 13:14 today. Zone 2's lines at the seam
   are the same deterministic lines the zone 1 code makes on starboard (ref_up 0.9327, ref_low 3.3902, strake 3.3696),
   so a re-seeded zone 2 does not move them. If zone 2 changes its knobs for the bands, rebuild zone 3 (25 s).
2. **Rear pods' front side.** The hull clearance leaves no room for FL's hug pipes and actuators on the front of RL
   and RR, so the rear pods carry them aft. Say if the front of the rear pods should get something else.
3. **Inside-out pieces.** None in zone 3 (flipped in the build). Zone 1's FL hoops are still the ones to flip at export.
4. **Export.** Zone 3 has no base edit. The pods' details are on the pod bones, so they tilt with the pods in Unreal.
5. **Turrets:** not in this zone. Nothing to report.
