# Airship detail pass, zone 5: belly and keel

Zone 5 is the underside of the hull below the bilge line, on both sides, from the stern to x 6.95 (where zone 4's keel
block starts). It goes round the four pods and their pockets, which belong to the pod zones. It uses zone 1's approved
kinds, sizes, colours and density. The big shapes come from reference 1's underside (`crop_hull_bottom.png`): a heavy
rust keel, pipe mains, machinery bays, heavy hoses and chains hanging in long sags. Players see the belly from below
when the ship flies over them, so it is built to read at 25-40 m.

Sheet: `media/z5/z5_sheet.jpg` (before / after, final toon colours, zones 1, 2, 3, 4, 6 and 7 loaded so the seams
show). Report: `z5_report.json`. Checks: `z5_checks.json`. Rig check: `z5_rigcheck.json`. Geometry hash:
`z5_hash.json` (copy of `rig/detail/zones/z5_hash.json`).

## 0. Review fixes (2026-11-28, after the whole-ship review)

The numbers further down are from the first build; these changes came after it (`FULL.md` section 8).

* **Chains:** the two keel swags are gone. They hung between two padeyes on the same strake, carried nothing, and read
  as thin beaded necklaces below the hull line from the side.
* **Hoses:** thicker (r 9 cm, was 7.5) and a short sag (0.26 m, was 0.55), so they read as heavy hoses close to the
  belly, not thin lines hanging below it.
* **Belly frames end on something.** They used to stop in the middle of the skin, right under raised rust plates, so
  from the side each flank showed a row of rust "signs on posts".
  * A riveted rust **bilge stringer** (16 cm wide, 10 cm proud, like the frames) now runs along each half: port at
    v 2.28 m from the keel line over x -14.3 .. -9.8 and -5.6 .. 1.1, starboard at v 2.40 over x -14.3 .. 0.65. It is
    placed where it crosses the most frame stations.
  * 12 of the 17 frames end on it. The 5 that cannot reach it (they stop at a pod's pocket) end in a sniped knee: the
    last 0.30 m is lower and tapers to 6 cm, with one rivet.
  * No raised rust armour plate within 0.5 m of a frame's end.
* Zone 5 is now 58,782 triangles (rivets 27.2 %, calm plate area 39 %, 2 armour plates).
* Checks after the fixes: object ok, determinism IDENTICAL GEOMETRY, ownership clean, PA walkable tops 0, hanging hoses
  at most 0.29 m from the skin (was more), rig check (`z5_rigcheck.json`, `full_rigcheck.json`).

## 1. What was built

One object, `SM_AirshipDetail_Z5_Belly` (collection `Detail_Z5`, every vertex 100 % on the `Hull` bone).
Distances "out from the keel" are measured along the skin from the keel line.

* **Keel girder** along the keel line, x -15.23 .. 6.43. A dark backing 0.80 m wide with two rivet rows, and on it a
  riveted rust keel strake 0.46 m wide and 8.5 cm thick, in segments about 2.25 m long with 8 mm joints. Its top is
  12.6 cm off the skin.
* **Two pipe mains**, one each side of the girder, 0.47 .. 0.97 m out from the keel, x -15.33 .. 6.43. Each is zone 1's
  pipe channel: dark backing, copper pipe r 7 cm and brass pipe r 5.8 cm, flanges about every 4 m, clamps on every
  belly frame and every 1.2 m between, one valve (no hand wheel), and both ends diving into riveted glands.
* **Belly frames**: riveted rust ribs, 16 cm wide and 10 cm thick, every 2.4 m (x -14.0 .. 5.2), from the pipe main
  out to the edge of the free skin. 8 on port, 9 on starboard (the FL pod's area leaves no room for the one at 2.8).
* **Four machinery bays**, 1.70 x 1.16 m, at x -13.86 .. -12.16 and -3.86 .. -2.16 on both sides, 1.10 .. 2.26 m out
  from the keel. Each has zone 1's riveted rust frame round a dark floor, a housing with a hinged and latched lid,
  a copper branch with a valve into a gland. Three have a pump body, two have a gas bottle.
* **Two heavy hoses**, one per side, from the aft bay to the middle bay (x -11.93 to -4.07, 1.68 m out from the keel).
  Each leaves a riveted fitting with a brass flange, rises 20 cm, then sags 0.55 m. Dark hose, r 7.5 cm, steel bands
  every 0.75 m, brass ferrules at the ends.
* **Two heavy chains** under the keel, between riveted padeyes on the keel strake: x -14.45 .. -9.25 and
  -1.35 .. 4.05, sag 0.62 m, 24 links each. Same link as zone 7's chain (0.30 m links, 3.2 cm wire).
* **Plates and layers** (zone 1's code and sizes) from the pipe mains out to the bilge line. Planned: 142 plates (61
  port, 81 starboard), 23 of them raised to overlap their neighbours, 8 of those heavy rust armour (6 % of the plates).
  15 plates were left out because the skin under them has a step, so built: 109 base plates, 18 raised plates, 13 frame
  ribs over plate seams, 9 picture frames, 11 rust or ochre patches, 2 slotted armour plates. Calm plates: 31 % of the
  plate area on port, 36 % on starboard (zone 1: 30 %).
* **The ship's belly tabs stay as they are.** The 9 tabs with a large outer face (islands 394-398, 404-407) get a
  rivet at each corner, like zone 4's tabs.

Rivets are zone 1's low domed ones (14 triangles), only on corners, ribs, the strake, frames, lids and flanges, about
28 cm apart.

Not built, on purpose: no windows, hatches, portholes, round grilles or teal bars; no big gear; no hanging ladders.
Nothing in the pod pockets and rim bands (pod zones), nothing on the turbine struts or the rudder's sweep (zone 6),
nothing forward of x 6.95 (zone 4), nothing above the bilge line (zones 1, 2, 3).

## 2. Look-and-fix pass (after the first renders)

| What read wrong | Fix |
|---|---|
| Too busy from below: only 19-22 % calm plate area, 29 picture frames on 129 plates, 11 heavy armour plates (zone 1: 30 % calm, 3 frames on 49 plates, 2 armour). The belly's plates are bigger than the flank's, so more of them qualify for a frame. | Lower shares for zone 5 only: frames 0.65 to 0.40, patches 0.70 to 0.65, armour share of raised plates 0.5 to 0.3. Seed 1315, picked from 7 seeds by the calm share. Now 31 % / 36 % calm, 14 frames planned (9 built), 8 armour plates. |
| 16 vertices of plates and one rib stood 6-10 cm from the feet of the turbine struts (zone 6), and one raised plate 9 cm from a hull island at the bow (zone 2). | Free cells now keep 17 cm in 3D from every face another zone owns. Ownership check: nothing within the 10 cm margin. |
| The channel valve's gauge disc stood 2.8 cm off its bonnet and was dropped as a floating piece. | Zone 5 uses its own copy of the valve (`valve_body5`) with the disc sunk 6 mm into the bonnet. |
| The low 3/4 views cut the ship off. | Cameras moved (`detail_z5_shots.json`). |

## 3. Numbers

**Triangles:** `SM_AirshipDetail_Z5_Belly` 60,800 (33,960 vertices).

| Group | Triangles | Share |
|---|---:|---:|
| Rivets | 15,638 | 26 % |
| Pipe mains (pipes, clamps, glands, valves, backing) | 14,392 | 24 % |
| Plates and layers | 13,866 | 23 % |
| Machinery bays (frames, floors, housings, pumps, bottles) | 6,720 | 11 % |
| Hoses, chains, padeyes | 6,336 | 10 % |
| Keel girder | 2,368 | 4 % |
| Belly frames | 1,480 | 2 % |

**Density against zone 1:**
* Per m2 of free belly skin (131.7 m2): 462 triangles, 414 without the hoses and chains. Zone 1: about 611 per m2 of
  its free flank skin (ZONE_2.md). The renders read about as dense as zone 1.
* Per m2 of zone 5's faces (214 m2): 284. Zone 1: 128 per m2 of its faces. The two do not compare well: zone 5's faces
  are nearly all free skin, while zone 1's include the ship's own bands, steam pipes and the pocket.
* Rivets: 26 % of the triangles (zone 1: 24 %). Heavy armour: 8 of 142 plates (zone 1: 2 of 49).
* Whole ship with every zone built so far (zones 1-7: 389.8k) plus today's ship (104k): about 0.49 M triangles, inside
  the 0.48-0.58 M estimate.

## 4. Checks (all pass)

| Check | Result |
|---|---|
| Safety | built only through `blender_capped.sh`. Writes only `rig/detail/zones/AirshipRig_detail_z5.blend` and zone 5 files. md5 unchanged at the end: `AirshipRig_detail.blend` 31317912621726b5e647c78bfc0cf948, `AirshipRig.blend`, `AirshipRig_src.blend`, `StylizedAirship.blend`, `props/AirshipProps.blend` |
| Determinism | two builds: `detail_hash.py` prints IDENTICAL GEOMETRY (`z5_hash.json`, `z5_rebuild_hash.json`) |
| Object | ok: 0 non-manifold edges, 0 vertices not 100 % on one bone, 0 faces without a role, 0 inside-out pieces, parent Armature + Armature modifier, name and collection right |
| Floating pieces | 0 left. `drop_floating` removed 5 rivets (on plate corners next to a plate left out over a skin step). 22 rivets that cut into the ship's own parts (tabs, struts) were removed before that. |
| Ownership | outside_zone 0, on a seam 0, within the 10 cm margin of another zone 0, keep-clear volumes: none |
| Walkable | 0 vertices above a PA_Airship box top. Nothing on the deck. |
| Silhouette | fixed details: p99 18.5 cm, max 21.2 cm off the skin (37 of 30,720 vertices over 20 cm: housings, a pump and a valve in the aft bays, where the belly curves away under a flat housing). Hoses and chains hang up to 0.97 m below the skin, on purpose. Their lowest point is z -5.88; the petal tips reach -6.17, so nothing hangs below the pods. |
| Rig check (zones 1, 2, 3, 4, 6, 7 loaded) | RESULT PASS, 0 new contacts: pods FL, FR, RL, RR 243 poses each (pod +-3 deg, nozzle +-5, petals -10 .. +35), turbines L and R 99 poses each (yaw +-12, rotor 360, rods +-20), rudder 13 poses (+-30). The original model's own contacts are unchanged. |
| Cannons, turrets, helm | not near zone 5 (no set applies) |
| Continuity | the bilge line is a hard edge (ZONES.md section 3): nothing runs over the tabs into zones 1, 2, 3. The girder and pipe mains end in glands 50 cm aft of zone 4's keel block, and 1 m forward of the transom. Seam renders: `seam_bilge_port`, `seam_stern`, `seam_bow`. |
| Never-add list | respected |

## 5. Renders (`media/z5/`)

| File | View |
|---|---|
| `z5_sheet.jpg` | everything below on one sheet |
| `belly_30m_toon_before/after.jpg` | from below, about 30 m (how players see it) |
| `belly_ortho_toon_before/after.jpg` | straight up, orthographic |
| `q34_low_toon_*`, `q34_low_aft_toon_*` | low 3/4 from fore-port (about 30 m) and aft-starboard (about 35 m) |
| `close_mid_toon_*`, `close_aft_toon_*`, `close_fwd_toon_*` | belly at about 6 m: amidships, aft, forward |
| `seam_bilge_port_toon_*`, `seam_stern_toon_*`, `seam_bow_toon_*` | seams with zones 1, 6 and 4 |
| `belly_30m_clay_*`, `close_mid_clay_*` | clay + cavity (Cycles ambient occlusion) |

"Before" is the ship as it is. "After" has every done zone loaded and the registered base edits applied.

## 6. Open points

1. **Plain ring round each pod.** On the belly, a plain yellow ring about 0.5-1 m wide stays round each pod. That skin
   is the pod zones' area (rule 3: pocket and rim band, up to 3.1 m from the pod axis), and zone 5 keeps 12-17 cm
   off it. It reads as a calm border in the renders. If Talal wants it filled, that is a small job for the pod zones.
2. **Hanging hoses and chains** have no physics. They hang up to 0.97 m below the skin (lowest z -5.88 m, UE -588 cm).
   The petal tips hang lower (-6.17 m), so the ship's lowest point does not change.
3. **Zone 4 was still in progress** when these renders were made (its build from 14:17, no ZONE_4.md yet). If zone 4
   changes, re-render `seam_bow`.
4. **Base edits:** none. Zone 5 deletes no SM_Airship faces (no `base_edits/z5.json`).
5. **Shared code note:** `detail_common.valve_body` puts the gauge disc 0.45 x r away from the bonnet's rim. On a big
   pipe (r over about 4.4 cm) that is more than `drop_floating`'s 2 cm, so the disc can be dropped. Zone 5 works round
   it with its own copy. The shared module is unchanged.
6. **Export** (as for the other zones): the object needs UVs / the atlas and the comic bake before Unreal.

## 7. How to rebuild

```
B=/mnt/new_partition/UnrealProjects/_AirshipWork_logs/blender_capped.sh
S=/mnt/new_partition/UnrealProjects/_AirshipWork/SourceArt/Airship/scripts
Z=/mnt/new_partition/BlenderProjects/StylizedAirship/rig/detail/zones
D=/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/round3
$B --python $S/detail_z5.py                                             # 25 s -> $Z/AirshipRig_detail_z5.blend, $D/z5_report.json
$B --python $S/detail_hash.py -- --blend $Z/AirshipRig_detail_z5.blend --prefix SM_AirshipDetail_Z5_ --out $Z/z5_rebuild_hash.json --compare $Z/z5_hash.json
$B --python $S/detail_checks.py -- --blend $Z/AirshipRig_detail_z5.blend --zone Z5 --out $D/z5_checks.json --sample 2
$B --python $S/detail_rigcheck.py -- --blend $Z/AirshipRig_detail_z5.blend --zones 1,2,3,4,6,7 --only Detail_Z5 \
   --sets pod:FL,pod:FR,pod:RL,pod:RR,turbine:L,turbine:R,rudder --out $D/z5_rigcheck.json      # about 3 min
$B --python $S/detail_render.py -- --blend $Z/AirshipRig_detail_z5.blend --zones 1,2,3,4,6,7 --look toon --states after \
   --shots-file $S/detail_z5_shots.json --shots belly_30m,belly_ortho,q34_low,q34_low_aft,close_mid,close_aft,close_fwd,seam_bilge_port,seam_stern,seam_bow \
   --out $D/media/z5                                                    # and --states before; clay: --look clay --samples 40 --shots belly_30m,close_mid
python3 -B $S/detail_z5_sheet.py                                        # media/z5/z5_sheet.jpg
```

Scripts: `detail_z5.py` (knobs `K`, build, report), `detail_z5_lib.py` (belly chart and mask, zone 1's layering
copied from zone 4's module, bays, `valve_body5`), `detail_z5_shots.json` (cameras), `detail_z5_sheet.py` (sheet).
All randomness is seeded (`seed` 1315).
