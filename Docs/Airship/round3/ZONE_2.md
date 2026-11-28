# Airship detail pass, zone 2: starboard flank and front-right pod

Zone 2 is the starboard twin of zone 1, which Talal approved on 2026-11-28 ("keep it as it is"). It uses the same
kinds of detail, the same density and the same layout code. It has its own seed, so it is not a literal mirror.

Sheet: `media/z2/z2_sheet.jpg`. It shows before / after and zone 1's approved renders next to them.

## 1. What zone 2 covers

* The **starboard hull flank** between the starboard cannon stations (x -11.55 to 6.95), from the deck edge down to
  the bilge line. It carries on forward over the front-right pod's pocket.
* The **front-right pod** `Thruster_FR`: the drum and its plates, the nozzle, and the 12 petals.
* The **FR pocket**: a riveted rim strap round the opening, wall stiffeners, and a ring rib in the cavity.

Not in zone 2: the RR pod and its pocket (Z3), the aft flank behind x -11.55 (Z3), the bow forward of x 6.95 (Z4),
the belly below the bilge line (Z5), and the deck and the rails (Z7).

## 2. How it is built

* Script: `SourceArt/Airship/scripts/detail_z2.py`, with the helpers `detail_z2_rim.py` (FR pocket rim),
  `detail_z2_xcheck.py` (check against other zones) and `detail_z2_sheet.py` (sheet).
* It opens `rig/AirshipRig.blend` read only. It saves `rig/detail/zones/AirshipRig_detail_z2.blend`, collection
  `Detail_Z2`.
* Knobs: zone 1's `K`, copied, with the changes below. Seed 2341. A seed sweep picked the seed whose layer counts
  were closest to zone 1's.
* No shared module was edited. No base-mesh faces are deleted, so there is no `base_edits/z2.json`.

### Changes from zone 1, and why

The starboard hull is not a mirror of the port hull. The RR pod sits 0.64 m further out than a mirror of RL, so its
pocket cuts much higher into the starboard flank. The FR pod sits 0.20 m lower and 0.26 m further out than a mirror of FL.

| Change | Why |
|---|---|
| Upper bays at x -5.5..-3.7 and -0.2..1.4 (zone 1: -8.1..-6.3 and -3.1..-1.5) | Over the RR pocket there is only a 0.45-0.7 m strip under the gunwale band (x -9 to -5.6), and further aft the upper rows are 0.7-0.9 m tall. A bay needs 0.9 m. Both bays now sit in the long free run, staggered with the two lower bays. |
| Pipe channel minimum run 1.20 m (zone 1: 1.40) | The free run at the aft seam is 1.25 m on starboard and 1.40 on port. With this change the channel starts at the Z3 seam on both sides. |
| Pod hull-clearance test by ray parity | The shared test (`detail_pod.HullClear`) decides inside or outside from the normal of the nearest skin point. Under FR the nearest skin is 2-3 m away, on an edge of the pocket opening, and that sign flips at random. With the shared test FR lost its lower hug pipe, both actuators and some drum plates. Zone 2 swaps in a ray-parity test at run time, with the same margins. The 243-pose rig check proves the result. |
| FR pocket rim (`detail_z2_rim.py`) | With the shared rim code, the top strap was wavy and the fore edge had broken bits, one of them 0.9 m forward of the opening (in Z4). The copy changes four things: the edge lines are fitted robustly, each strap is smoothed in 3D, every strap sample must lie in zone 2 on smooth skin, and pieces shorter than 0.6 m are dropped. The result is 4 straps (zone 1: 5). |

## 3. Numbers

| Object (parent `Armature`, Armature modifier) | Bone(s) | Vertices | Triangles |
|---|---|---:|---:|
| `SM_AirshipDetail_Z2_Hull` | `Hull` | 18,025 | 32,206 |
| `SM_AirshipDetail_Z2_Pod_FR` | `Thruster_FR` | 7,766 | 13,896 |
| `SM_AirshipDetail_Z2_Nozzle_FR` | `Thruster_FR_Nozzle` | 1,248 | 2,160 |
| `SM_AirshipDetail_Z2_Petals_FR` | `Thruster_FR_Petal00`..`11` (190 vertices each) | 2,280 | 4,032 |
| **Total** | | | **52,294** (zone 1: 51,204) |

Layers on the flank, zone 2 (zone 1):

* Calm plate area: 34 % (30 %).
* Raised plates: 6 (6), of which 2 are heavy rust armour (2).
* Frame ribs: 6 (6).
* Slotted plates: 5 (5).
* Picture frames: 3 (3).
* Patches: 3 (6).
* Machinery bays: 2 lower + 2 upper, 6 housings (the same).
* Channel spans: 2 (2).
* Teeth: 4 (5).
* Gussets: 28 (29).
* Conduits: 2, with 3 through-hull fittings (the same).

Triangles by kind:

* Rivets: 23.4 % (zone 1: 24 %).
* Pipes, conduits, clamps, glands and valves: 20.1 %.
* Pod: 21.8 %.
* Machinery bays: 12.0 %.
* Plates: 10.5 %.
* Nozzle and petals: 5.5 %.
* Strake, teeth, rim, cavity, gussets and channel: 6.7 %.

Density:

* The hull object comes to 139 triangles per m² of Z2's non-pod faces (zone 1: 128 on its own faces). Zone 2 has
  less flank than zone 1, because the RR pocket takes a large piece of it, yet the triangle count is about the same.
  On the free skin where plates go, the counts are 655 versus 611 per m². That gap is inside the spread between
  seeds (28.7k to 31.4k flank triangles).
* The pod group has 20.1k triangles (zone 1: 18.5k). The sound clearance test leaves room for 19 drum plates (FL: 16)
  and for a longer pair of hug pipes. Seen from players' angles the pod reads like FL (sheet, row 4).

## 4. Checks (all pass)

| Check | Result |
|---|---|
| Safety | Built only through `blender_capped.sh`. The md5 of `AirshipRig_detail.blend` is 31317912621726b5e647c78bfc0cf948 at the end. `AirshipRig.blend`, `AirshipRig_src.blend`, `StylizedAirship.blend` and `AirshipProps.blend` are unchanged (listed in `z2_report.json`). |
| Determinism | A second build gives IDENTICAL GEOMETRY (`rig/detail/zones/z2_hash.json`, `z2_rebuild_hash.json`). |
| Objects | All 4 objects are ok. 0 non-manifold edges. Every vertex is 100 % on one bone. Every face has a role material. 0 inside-out pieces (49 were flipped in the build: 38 nozzle hoop pieces and 11 pod pieces). |
| Floating pieces | 0 left. None were removed in the final build. |
| Ownership (`z2_checks.json`, every 2nd vertex) | 2 vertices are outside Z2: a plate corner 1-2 cm below the bilge line (x -0.66), which is Z5 by a hair. Other vertices sit on seams: 42 on Z5, 15 on Z3, 5 on Z4. They are plates and straps ending on the zone edge, the FR fore rim strap (the rim band is Z2 by rule 3), and plates next to the RR cavity (Z3), like zone 1 next to RL. The keep-clear volumes have 0 vertices in them. |
| Other zones' objects (`z2_xcheck.json`) | 0 shared triangles with zones 1, 6 and 7. The nearest is Z7's rails, 0.99 m away. |
| Walkable | 0 detail vertices above a PA_Airship box top. Hull details reach at most z 2.23 m. |
| Silhouette | Hull details are within 20.1 cm of the skin. The one vertex over 20 cm is a valve, 1 mm over. p99 is 18.4 cm. Cavity details are within 8.9 cm. The pod outline grows by at most 9.9 cm. The nozzle and the petals stay inside the outline. |
| Rig (`z2_rigcheck.json`, zones 1, 6 and 7 loaded) | **PASS**. Pod FR: 243 poses, 0 new contacts. The ship's own baseline is pod vs hull 152 and nozzle vs pod 56, unchanged. Cannon R1: 18 poses, 0 overlaps, closest 1.05 m. Cannon R2: 0 overlaps, closest 1.32 m. Port has L1 1.06 m and L2 1.32 m. |
| Never-add list | No windows, hatches, portholes, round grilles, teal bars, gear or ladders. |

## 5. Seams: what Z3 and Z4 continue (`z2_continuity.json`)

The starboard numbers at the aft seam mirror zone 1's within 2 cm.

| Run | At the aft edge, x -11.55 (Z3 continues) | At the fore edge (Z4 continues) |
|---|---|---|
| Upper rows | ref_up s 0.933 | ref_up s 1.017 at x 6.95 |
| Gussets | Grid x = -11.20 + 0.51 k. The first is at (-11.20, -6.694, 2.178). | The last is at x 2.57, stopped by the FR pocket. The next grid points are 7.16, 7.67 ... |
| Conduits | Glands at x -11.15: (-11.212, -7.048, 1.299) and (-11.210, -7.028, 1.395) | They end at x 2.35: (2.400, -7.658, 0.590) and (2.399, -7.675, 0.684) |
| Strake + teeth | Line at s 3.370. The first segment starts at x -11.53, with its top at (-11.53, -6.506, -0.438) and the backing bottom at (-11.53, -6.100, -1.134). | It ends at x 0.85 (FR pocket). |
| Pipe channel | Span -11.55 .. -10.30. Copper r 7 cm starts at (-11.262, -6.078, -1.465). Brass r 5.8 cm starts at (-11.257, -5.910, -1.640). | Span -4.40 .. 0.80 |

## 6. Renders (`media/z2/`)

| File | View |
|---|---|
| `z2_sheet.jpg` | everything below on one sheet, with zone 1's approved renders for comparison |
| `side_stbd_toon_before/after.jpg` | whole starboard side, orthographic |
| `q34_stbd_toon_*`, `q34_stbd_clay_*` | 3/4 from starboard-forward, about 25 m (toon and clay) |
| `close_flank_s_toon_*`, `close_flank_s_clay_*` | flank, about 5.5 m |
| `close_pod_s_toon_*`, `close_pod_s_clay_*` | pod FR, about 5.5 m |
| `pod_low_s_toon_*` | pod, nozzle and petals from below |
| `*_poseAFR.jpg`, `*_poseBFR.jpg` | rig limits. Pose A: pod +3/+3, nozzle -5/+5, petals +35. Pose B: pod -3/-3, nozzle +5/-5, petals -10. |
| `pocket_f_toon_*` | FR pocket and its rim |
| `seam_aft_s_toon_*`, `seam_fwd_s_toon_*` | the Z3 and Z4 seams (those zones are not built yet) |
| `rr_strip_s_toon_*` | the narrow strip above the RR pocket |

The cameras are in `media/z2/z2_shots.json`. Zones 1, 6 and 7 are loaded, and the turrets are placed read only.

## 7. Commands

```
B=/mnt/new_partition/UnrealProjects/_AirshipWork_logs/blender_capped.sh
S=/mnt/new_partition/UnrealProjects/_AirshipWork/SourceArt/Airship/scripts
Z=/mnt/new_partition/BlenderProjects/StylizedAirship/rig/detail/zones
D=/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/round3
$B --python $S/detail_z2.py                                   # 12 s: blend, z2_report.json, z2_continuity.json
$B --python $S/detail_z2.py -- --sweep 2301,2302,...          # layer stats per seed (no save)
$B --python $S/detail_hash.py -- --blend $Z/AirshipRig_detail_z2.blend --prefix SM_AirshipDetail_Z2_ --out $Z/z2_hash.json
$B --python $S/detail_checks.py -- --blend $Z/AirshipRig_detail_z2.blend --zone Z2 --out $D/z2_checks.json --sample 2
$B --python $S/detail_rigcheck.py -- --blend $Z/AirshipRig_detail_z2.blend --zones 1,6,7 --only Detail_Z2 \
   --sets pod:FR,cannons:R1+R2 --out $D/z2_rigcheck.json
$B --python $S/detail_z2_xcheck.py -- --zones 1,3,4,5,6,7
$B --python $S/detail_render.py -- --blend $Z/AirshipRig_detail_z2.blend --zones 1,6,7 --look toon --states before,after \
   --shots side_stbd,q34_stbd,close_flank_s,close_pod_s,pod_low_s,pocket_f,seam_aft_s,seam_fwd_s,rr_strip_s \
   --shots-file $D/media/z2/z2_shots.json --out $D/media/z2
python3 -B $S/detail_z2_sheet.py
```

## 8. Notes and open points

* **Shared-code issue, for the lead:** `detail_pod.HullClear` is unreliable far from the hull (section 2). Z3 will
  probably hit it on RL and RR. Zone 2 works around it at run time (`detail_z2.HullClearParity`); the shared module
  was not changed.
* **Shared-code issue:** `detail_pod.pocket_rim` can extrapolate a strap past the pocket edge and leave short bits.
  Zone 2 uses its own copy (`detail_z2_rim.py`). Zone 1's FL rim is frozen as approved.
* **Export:** the 4 objects follow the same rules as zone 1 (UVs, the bake, and the `rig_export.py` mesh-count
  assert). Zone 2 has no inside-out pieces left to flip.
* **The RR pocket** is Z3's. Zone 2's plates come close to its opening above it, as zone 1's do above RL. Z3 can only
  put a lip there, not a full rim strap.
