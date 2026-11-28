# Airship detail pass, round 3: zone 4 (the bow)

Zone 4 is everything forward of x 6.95 below the gantry: both bow flanks forward of the FL / FR pocket rims, the bow
wedge (BowWedge), the grey keel block under the bow (Underside_Front) and the belly tabs there. It uses zone 1's
approved language and density. The kinds and shapes come from reference 1's bow (crop_bow.png): heavy rust armour
plates, riveted strakes and angle irons, big bolted blocks, the teeth line.

Sheet: `media/z4/z4_sheet.jpg`. Report: `z4_report.json`. Checks: `z4_checks.json`, `z4_rigcheck.json`,
`z4_seams.json`, `z4_continuity.json`, `z4_hash.json`.

## 0. Review fixes (2026-11-28, after the whole-ship review)

The numbers further down are from the first build; these changes came after it (`FULL.md` section 8).

* **Keel block** (partly fixed): it read as a grey sticker collage with short rust straps that started and ended
  nowhere.
  * Plates are now mostly rust like the wedge: rust dark 40 %, rust 20 %, machinery grey 32 %, dark 8 %
    (was grey 75 %, dark 25 %).
  * Three wrap bands per half at even spacing (22 %, 50 %, 78 % along the block). Each runs out from the keel angle as
    one band (segments butt with a joint); where the surface gets too lumpy the band ends, instead of leaving stray
    short pieces further out. On this lumpy block the bands stay short.
  * The block's own colour between the plates is the base model's grey, so from below it is still a grey patch with
    rust plates. Whether the block itself should be rust is a question for Talal (`FULL.md` section 5).
* **Wedge:** not changed on purpose, but it was rebuilt. Zone 7's heavier ChainAft hangs beside it and is one of the
  wedge's obstacles, so the top angle iron now starts 5 cm further forward (x 16.30) and the random layers re-rolled
  (same rules, same density).
* Zone 4 is now 63,774 triangles: Hull 7,202 (unchanged), Wedge 47,774, Keel 8,798. Rivets 31.6 %.
* Checks after the fixes: all objects ok, determinism IDENTICAL GEOMETRY, rig check (`z4_rigcheck.json`,
  `full_rigcheck.json`).

## 1. What was built

Three objects in collection `Detail_Z4`. Each is parented to `Armature` with an Armature modifier. Every vertex is
100 % on the `Hull` bone.

| Object | What is on it | Triangles |
|---|---|---:|
| `SM_AirshipDetail_Z4_Hull` | both bow flanks (x 7.05 .. 15.45): yellow / ochre plates, raised plates (some rust armour), patches, one slotted plate, a riveted rust strake with a dark backing and 4 rust teeth per side (x 7.35 .. 11.75, ended on riveted rust end ribs), 5 gussets per side under the gunwale band, corner rivets on the ship's own belly tabs | 7,202 |
| `SM_AirshipDetail_Z4_Wedge` | the bow wedge: plates in two rust tones (one step lighter and darker than the wedge), raised dark-rust armour with rivet rows, patches, dark frame ribs, slotted plates on the front; riveted dark angle irons over every crease; bent straps over the facet creases; a riveted keel strap down the bottom; 5 machinery bays (3 on the bottom, 1 per side: riveted rust frame, dark floor, housing with hinged and latched lid, pump, gas bottle, valve, pipes); one pipe channel on the bottom (copper + brass pipes, flanges, clamps, glands); a conduit pair under the top angle on each side; 10 bolted rust blocks (4 on the lower chamfers, 2 on the front, 4 on the bottom) | 44,370 |
| `SM_AirshipDetail_Z4_Keel` | the keel block: grey plates on fitted patches (lifted over the bumps), raised rust armour, rust straps across both halves, a copper pipe on each side, a riveted rust keel angle along the V | 7,654 |
| **Total** | | **59,226** |

Triangles by kind: rivets 18,872 (about 1,350 rivets), plates 6,756, bays 4,460, pipes 3,560, raised plates 3,058,
fills 2,548, conduits 2,320, housings 2,300, clamps 2,144, pump 1,700, patches 1,552, glands 1,512, blocks 1,320,
bottles 1,280, slotted 1,064, teeth 952, strake 908, straps 732, valves 552, gussets 540, channel 400, angles 380,
frame ribs 316.

No base edits: zone 4 deletes no SM_Airship faces.

## 2. The one look-and-fix pass (2026-11-28)

I looked at the first renders next to reference 1 and zone 1's approved renders. Three things read wrong. I fixed them
and rendered again.

| What read wrong | Fix |
|---|---|
| The bolted blocks read as small framed windows from 25 m (a dark cap inside a grey body). A grey cap then read as a screen. | Blocks are now one solid stepped rust lump: dark-rust body and cap on a riveted flange in the wedge's own rust. |
| The bow flank gaps round the ship's own rust plates were filled with many small yellow scraps (a mosaic). | Gap fillers on the bow flank are now at least 0.5 x 0.38 m. The rest stays calm. |
| Dark plates on the grey keel read as hatches from below. | Keel plates are now 75 % the keel's own grey, 25 % dark (was 65 / 35). |

The geometry after the colour changes is identical to the rig-checked build (same coordinates and faces).

## 3. Numbers next to zone 1

| | Zone 1 | Zone 4 |
|---|---:|---:|
| Triangles | 51,204 (with pod FL) | 59,226 (no pod) |
| Zone area (SM_Airship faces) | 479 m2 | 743 m2 |
| Triangles per m2 of zone | about 107 | about 80 |
| Rivets per m2 of zone | about 1.8 | about 1.8 |
| Rivet share of triangles | 24 % | 32 % |
| Calm plate area | 30 % | 44 % |
| Heavy rust armour | 2 of 49 plates | 19 of 133 plates (14 %; the wedge is rust, so armour there is dark rust) |

Zone 4 is a little less dense per m2 than zone 1, but the parts you see up close (wedge sides, bottom, front) are about
as dense as zone 1's flank. The rivet share is higher because the wedge has many riveted angle irons and straps, and
zone 4 has no pod (pods are pipe-heavy). The calm share is higher because the bow flank is mostly the ship's own big
rust plates, and the keel block is lumpy (2 plates refused there).

## 4. Checks (ZONES.md section 9)

| Check | Result |
|---|---|
| Safety | Blender only through `blender_capped.sh`, headless. Output only `zones/AirshipRig_detail_z4.blend` and zone 4 files. md5 of AirshipRig_detail.blend (31317912621726b5e647c78bfc0cf948), AirshipRig.blend, AirshipRig_src.blend, StylizedAirship.blend, AirshipProps.blend unchanged. |
| Determinism | Two builds: IDENTICAL GEOMETRY, all hash fields equal (`zones/z4_hash.json`, `z4_rebuild_hash.json`). |
| Objects | All 3 ok: 0 non-manifold edges, 0 not-rigid vertices, 0 faces without a role, 0 inside-out pieces (20 were flipped in the build: 14 wedge, 6 keel), names and collection right. |
| Floating pieces | 0 left. The build removed 12 hull rivets and 1 wedge fill plate that touched nothing. |
| Ownership | `outside_zone` 0, `keep_clear` empty. On the seam / within 10 cm of a neighbour: see section 5. |
| Other zones | 0 pieces intersect zone 1, 2, 3, 6 or 7 details. Zone 5 (in progress) cross-check: 0 pieces intersect its current file. |
| Walkable | 0 detail vertices above a PA_Airship box top. Nothing on the deck. |
| Silhouette | All details within 19.7 cm of the ship (p99 17.9 cm). Hull flank p99 13.1 cm, wedge p99 17.8 cm, keel p99 18.1 cm. |
| Rig check | RESULT PASS (`z4_rigcheck.json`, zones 1, 2, 3, 6, 7 loaded): pod FL 243 poses 0 new contacts, pod FR 243 poses 0, chain 36 poses 0, turret L 45 poses 0 overlaps (closest 2.73 m), turret R the same. |
| Never-add list | No teal bars, windows, hatches, portholes, round grilles, belly gear or hanging ladders. No picture frames on rust or grey (they read as windows there, as zone 6 found on the rudder). |

## 5. Seams

| Where | What | Why it is fine |
|---|---|---|
| Port x 7.12 .. 7.22, z 1.25 (and starboard) | the first gusset, x 7.16 | it continues zone 1's / zone 2's gusset grid (x = -11.20 + 0.51 k): 7.16, 7.67, 8.18, 8.69, 9.20 |
| Port x 7.29 .. 7.40, z -0.1 .. -0.4 (and starboard) | the strake's aft end rib and the first strake segment | the run starts just forward of the FL / FR pocket rim strap and ends on a riveted rust rib (seam rule) |
| Wedge x 15.9 .. 16.25, z 3.3 .. 3.8 | the aft end of the top angle iron | within 10 cm of the deck rail / gantry foot (Z7); no contact |
| Wedge x 27.0, z 4.15 | the edge of a front plate | within 10 cm of the gantry front (Z7); no contact |

The bow flank's upper rows are almost empty: the copper steam pipes and the gunwale band cover that strip (0.2 m2 free
per side). So the conduit pair does not continue there. Zone 1's strake line ends at the FL pocket (x 0.93). Zone 4's
strake hangs under the bow's own lower band (islands 416 / 418, from x 6.84), so it is a new run, not a continuation.
It stops at x 11.75, where the belly tabs and the keel block come too close below. Seam renders: `seam_p`, `seam_s`.

## 6. Renders (`media/z4/`, toon = final look, zones 1, 2, 3, 6, 7 loaded)

| File | View |
|---|---|
| `q34_bow_p_toon_*`, `q34_bow_s_toon_*` | 3/4 from bow-port / bow-starboard, low, about 25 m |
| `side_bow_p_toon_*`, `side_bow_s_toon_*` | bow from the side, orthographic |
| `bow_head_toon_*`, `bow_below_toon_*` | head-on, from below |
| `close_wedge_p_toon_*`, `close_wedge_low_toon_*`, `close_front_toon_*` | wedge side, bottom, front, about 5.5 m |
| `close_flank_bow_p_toon_*`, `close_flank_bow_s_toon_*` | bow flanks, about 5.5 m |
| `close_keel_p_toon_*` | keel block |
| `seam_p_toon_*`, `seam_s_toon_*` | the zone 1 / zone 4 and zone 2 / zone 4 seams |
| `q34_bow_p_clay_*`, `close_wedge_low_clay_*` | clay + cavity |
| `z4_sheet.jpg` | all of the above on one sheet |

## 7. Commands

```
B=/mnt/new_partition/UnrealProjects/_AirshipWork_logs/blender_capped.sh
S=/mnt/new_partition/UnrealProjects/_AirshipWork/SourceArt/Airship/scripts
Z=/mnt/new_partition/BlenderProjects/StylizedAirship/rig/detail/zones
D=/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/round3
$B --python $S/detail_z4.py                                                  # 25 s -> $Z/AirshipRig_detail_z4.blend, $D/z4_report.json
$B --python $S/detail_hash.py -- --blend $Z/AirshipRig_detail_z4.blend --prefix SM_AirshipDetail_Z4_ --out $Z/z4_hash.json
$B --python $S/detail_checks.py -- --blend $Z/AirshipRig_detail_z4.blend --zone Z4 --out $D/z4_checks.json --sample 2
$B --python $S/detail_rigcheck.py -- --blend $Z/AirshipRig_detail_z4.blend --zones 1,2,3,6,7 --only Detail_Z4 \
   --sets pod:FL,pod:FR,chain,turrets --out $D/z4_rigcheck.json
$B --python $S/detail_z4_seams.py                                            # -> $D/z4_seams.json
$B --python $S/detail_render.py -- --blend $Z/AirshipRig_detail_z4.blend --zones 1,2,3,6,7 --look toon \
   --states before,after --shots-file $S/detail_z4_shots.json --shots q34_bow_p,bow_head,... --out $D/media/z4
python3 -B $S/detail_z4_sheet.py                                             # -> media/z4/z4_sheet.jpg
```

Scripts: `detail_z4.py` (knobs and build), `detail_z4_flank.py` (bow flanks), `detail_z4_wedge.py` (wedge, keel block,
tab rivets), `detail_z4_lib.py` (masks on faces, zone 1's layering, angle irons, blocks, straps, bays, channel),
`detail_z4_seams.py`, `detail_z4_sheet.py`, `detail_z4_shots.json`. Seed 1304. No shared module was changed.

## 8. Notes for the lead

* Zone 4's build loads the finished zones (1, 2, 3, 6, 7) as obstacles, not zone 5. Zone 5 loads zone 4, so loading it
  back would make the two builds circular. If zone 5 changes, re-run `detail_z4.py` and look at
  `log.z5_crosscheck` in `z4_report.json` (0 intersecting pieces today).
* The wedge is the heaviest object (44k triangles). If the budget gets tight, its knobs are `wedge_bays`, `blocks`,
  `wedge_rows` and `rivet_min_area` in `K['z4']`.
* Nothing to add to PA_Airship: zone 4 removes nothing and puts nothing on a walkable top.
