# Airship round 3: the editor stage (Unreal)

The steps that put the detailed ship into the game: the yellow and rust palette, the navy ink, 238k skinned triangles
with two LODs, the Hull-bone details as one Nanite static mesh, the recoloured props and turrets, and the stair
collision. Run them in the airship clone (`/mnt/new_partition/UnrealProjects/_AirshipWork`) **after PR B's editor tests
are finished**. Nothing here was run yet: no editor was used when this was written.

* **Inputs:** `SourceArt/Airship/r3/` (8 FBX files and `r3_unreal_inputs.json`) and `SourceArt/Airship/textures/r3/`
  (5 PNG files). `SourceArt/Airship/scripts/r3_export_all.sh` stages them, and every script checks their md5 against
  `r3_unreal_inputs.json`. What they are and how they were checked: `EXPORT_R3.md` section 14.
* **Scripts:** `Docs/Airship/scripts/ue/as_90_r3_textures_material.py`, `as_91_r3_reimport.py`,
  `as_91b_r3_hull_detail.py`, `as_91c_r3_turrets.py`, `as_92_r3_pa_stairs.py`, `as_93_r3_verify.py` and the shared
  `as_9x_r3lib.py`.
* **Review fixes (2026-11-28):** the scripts below are the reviewed versions; section 7 lists what changed and why
  (EXPORT_R3.md section 15 has the evidence). The material is **M_AirshipR3 v2**. The ship is now judged **in
  StartupMap** (the match level), not only in L_AirshipTest: StartupMap's blue moon and cyan sky light turned the plain
  lit yellow green.
* **Rules every script keeps:**
  * it refuses to run during PIE;
  * it backs up the assets it changes into `Saved/Airship/backup_r3/<stamp>_<script>/` (with `backup.json`: sha256 and
    the restore note) and refuses an asset that has unsaved changes;
  * it saves only its own assets, by explicit path, never a map;
  * it saves nothing when any line is a FAIL;
  * it checks that Talal's `/Game/Assets/MyShip/M_Airship`, `T_Airship_ComicLines`, `T_Airship_ComicMask` and
    `SM_Airship` are untouched;
  * it writes `Saved/Airship/<script>.json` and ends with `RESULT: PASS {...}` or `RESULT: FAIL {...}`.

## 1. Before you start

1. Stop PR B's PIE runs. No PIE may be running. Close the editors of SK_Airship, SKEL_Airship, PA_Airship, CR_Airship,
   ABP_Airship, BP_AirshipPawn and BP_AirshipTurret (the scripts close them too).
2. Start a fresh clone editor (`Docs/Airship/scripts/harness/launch.sh`). Check memory with `free -g` (PC memory notes:
   the editor runs in its capped scope).
3. **Frame-time baseline (before anything changes):** run the PIE perf capture of section 4.5 once on today's ship and
   write the numbers down. Without that, "frame time vs before" cannot be answered.
4. Do not run these afterwards:
   * `as_56_reimport_airship.py`: it would re-import round 2's FBX over the new SK;
   * `as_10_import.py`: it checks for 2 slots and 104,730 triangles.
   * `as_11_physics_asset.py` rebuilds PA_Airship without the stair boxes. If it ever runs, run `as_92` again after it.
   * `as_61_hull_ink.py`: it writes M_AirshipDrivable back onto SK slot 0 (as_61 lines 271-291).
   * `as_53_turret_import.py` on its own: it would re-import round 2's turret FBX with M_AirshipProps (as_91c runs it
     patched, with the r3 source files).
   * `as_02_textures_material.py`: round 2's props textures and material set-up.
5. **Budget notes for the baseline** (write them next to the numbers of point 3):
   * Texture memory: about 80 MiB for the ship's textures, shared by all 4 ships (3 x 21.3 MiB BC7 4096 + 5.3 MiB props +
     10.7 MiB comic mask; round 2 about 16 MiB). With HasComic off (v2 default) the comic mask is not sampled, so it is not
     streamed in beyond its smallest mips. `DetailInk_M` at 2048 would save 16 MiB (59 texels/m instead of 119).
   * SK LOD2 floor: 164.7k triangles, about 208k render vertices; SM_Airship and the props are in every LOD and there is no
     LOD beyond 80 m. With no skin cache every far ship is skinned at 1.6 times round 2's whole ship in each pass. If the
     4-ship GPU numbers are tight, an LOD3 at about 200 m is the next step.
   * LOD distances: at runtime the SK picks LODs from its component bounds, which come from the physics asset when bodies
     exist (USkinnedMeshComponent::CalcMeshBound), not from the imported bounds: the 30 / 80 m switches can shift a little.
     `ShowFlag.LODColoration 1` shows where they really are.
   * Lumen: the clone has `r.DynamicGlobalIlluminationMethod=0`; Talal's redo3 tree has 1 (Lumen, uncommitted in his
     DefaultEngine.ini). The clone's baseline does not include Lumen, and only HullDetail (a static mesh, distance fields
     on) enters the Lumen scene. Measure once with redo3's setting before merging.

## 2. The steps, in order

Each step is one inbox call (`Docs/Airship/scripts/harness/inbox.sh <n> <script> <timeout s>`). If a step ends in
FAIL after it changed something in memory, quit the editor without saving (`quit_keep_lock.sh`), start it again and
re-run that step. All steps can be re-run. To undo a step that saved, quit the editor and copy that step's backup folder
(`Saved/Airship/backup_r3/<stamp>_<script>/Content/...`) back over `Content/`.

| # | Command | Changes and saves | Must print (besides `RESULT: PASS`) |
|---|---|---|---|
| 1 | `inbox.sh 90 Docs/Airship/scripts/ue/as_90_r3_textures_material.py 600` | `Drivable/Textures/T_AirshipR3_HullInk`, `_DetailInk_H`, `_DetailInk_M`, `_PropsInk`, `_HullComicMask`; `Drivable/Materials/M_AirshipR3`, `MI_AirshipR3_Look`, `MI_AirshipR3_Hull`, `_Moving`, `_HullDetail`, `_Props` | `staged inputs (13 files) = r3_unreal_inputs.json`; `look defaults {'LitMix': 0.5, 'ShadeLift': 0.55, 'LiftSat': 1.3, 'LiftLock': 1.0} = the staged export_shade_calib.json choice`; one PASS per texture with `[4096, 4096]` (Props `[2048, 2048]`), `srgb False`, `TC_BC7` (comic mask `TC_MASKS`), `TA_CLAMP`, ink pages `filter TF_TRILINEAR`; `built ... M_AirshipR3` (comment `as_90 M_AirshipR3 v2 ...`); `M_AirshipR3 compiles`; `usage MATUSAGE_SKELETAL_MESH` / `MATUSAGE_NANITE`; `master defaults: 24 palette colours + 23 scalars`; `MI_AirshipR3_Look: look {...}, switches {'HasSilhouette': False}`; four MI lines (`MI_AirshipR3_Hull: parent .../MI_AirshipR3_Look, InkTex .../T_AirshipR3_HullInk, switches {InkOnUV2: True, HasDots: True, HasComic: False}, two sided True`, and so on); `MI_AirshipR3_Hull sees the palette ... keel block [0.5, 0.2, 0.12]`; 10 `saved` lines; `Talal's assets untouched` |
| 2 | `inbox.sh 91 Docs/Airship/scripts/ue/as_91_r3_reimport.py 1200` | `SK_Airship` (and `SKEL_Airship` only if the import touched it) | `before: 118 bones, ... slots ['M_Airship', 'M_AirshipProps'] ...`; `stored Interchange pipeline: [...use_full_precision_u_vs ... True, ... threshold_uv ... 1.52e-05]`; `SK_Airship re-imported through the Interchange manager ...: True`; `no new skeleton / physics asset`; `skeleton .../SKEL_Airship`; `skeleton unchanged: 118 bones, names / order True, parents True, rest positions within 0.0000 cm`; `sockets unchanged`; `PA_Airship kept: ... file unchanged, dirty False`; `material slots [...3 names...]`; `LOD0/1/2 build settings {use_full_precision_u_vs: True, threshold_uv: 1.52e-05, recompute_normals: False ...}`; `LOD1 imported`, `LOD2 imported`; `3 LODs`; `mesh reference skeleton unchanged: 118 bones ...`; `LOD screen sizes now [2.4, 1.93, 0.72]` (PASS, or WARN with the two numbers to type in by hand; a FAIL if the JSON route changed any other SourceModels field: then restart without saving and run with `AS91_SKIP_SCREEN_SIZES = True`); per LOD `3 sections ... source triangles 238430 / 186492 / 164688 ... UV channels 3 (want 3)`; `slots [('M_Airship', .../MI_AirshipR3_Hull), ('M_AirshipProps', .../MI_AirshipR3_Props), ('M_AirshipR3_Detail', .../MI_AirshipR3_Moving)]`; `LODn sections -> slots [0, 1, 2]`; `saved .../SK_Airship`; `PA_Airship file unchanged after the save` |
| 3 | `inbox.sh 91b Docs/Airship/scripts/ue/as_91b_r3_hull_detail.py 900` | `Drivable/SM_AirshipR3_HullDetail`, `BP_AirshipPawn` | `imported SM_AirshipR3_HullDetail.fbx`; `LOD0/1/2 build settings {use_full_precision_u_vs: True ...}`; `3 LODs`; `Nanite True, fallback {... PERCENT_TRIANGLES ..., 1.0}`; `LOD screen sizes [2.25, 1.75, 0.66]`; `material slots [.../MI_AirshipR3_HullDetail]`; `bounds ... vs the export ...: 0.0x cm`; per LOD `source triangles 258238 / 170538 / 119664, UV channels 2`; `added a StaticMeshComponent under Mesh, renamed HullDetail: True` (or `reusing`); `HullDetail attached to Mesh`; `BP_AirshipPawn compiled: BS_UP_TO_DATE`; `BP_AirshipPawn.HullDetail {... NO_COLLISION ..., attached_to_mesh: True ...}`; `Hull bone rest at the component origin, no rotation`; `Mesh component material overrides []`; 2 `saved` lines. The INFO line about the parent socket is expected (14.3 point 4) |
| 4 | `inbox.sh 91c Docs/Airship/scripts/ue/as_91c_r3_turrets.py 300` | `Drivable/Turret/SM_AirshipTurret_Base`, `_Gun` | per turret `source file .../SourceArt/Airship/SM_AirshipTurret_*.fbx -> .../SourceArt/Airship/r3/SM_AirshipTurret_*.fbx` (the review fix: as_53 re-imports the stored source); as_53's own lines: `re-importing over ... (was from .../r3/...)`, `materials [.../MI_AirshipR3_Props...]`, `Nanite False`, the `turret_dims.json` bounds checks; `---- as_53 counts {... 'FAIL': 0 ...}`; per mesh `full-precision UVs True, UV channels 2, slots [.../MI_AirshipR3_Props], bounds vs the export 0.00 cm, ... source file .../r3/... (r3: True)`; `BP_AirshipTurret components ... no overrides`; 2 `saved` lines |
| 5 | `inbox.sh 92 Docs/Airship/scripts/ue/as_92_r3_pa_stairs.py 300` | `PA_Airship` | `stairs_collision.json: 16 boxes, unique names [...]`; `json corners = centre + size + FRotator: worst 0.0xx cm`; `Hull bone rest [0.0, 0.0, 0.0], no rotation`; `before: 35 bodies, 143 shapes, 103 on Hull (0 Stairs_* ...)`; `bodies unchanged (35)`; `16 stair boxes on Hull, corners within 0.xxx cm of the json`; `every other shape unchanged`; `Hull body physics mode ... Kinematic`; `0 constraints`; `35 bodies / 159 shapes / 119 on Hull`; `saved .../PA_Airship` |
| 6 | restart the editor, then `inbox.sh 93 Docs/Airship/scripts/ue/as_93_r3_verify.py 600` | nothing (read-only) | PASS lines for the 5 textures (with `filter TF_TRILINEAR` on the ink pages), the material, `MI_AirshipR3_Look look ... HasSilhouette False` and its 4 MIs (hull `HasComic: False`), `118 bones = bones_ue.csv`, `SK_Airship's own reference skeleton ... = bones_ue.csv`, per LOD `UV channels 3`, `Nanite fallback ... PERCENT_TRIANGLES 1.0`, both turrets `source ... (r3 True)`, `sockets = as_91's record`, `3 LODs`, per LOD `3 sections`, slots, `SM_AirshipR3_HullDetail: Nanite True, 3 LODs ...`, `BP_AirshipPawn.HullDetail ...`, both turrets, `PA_Airship 35 bodies / 159 shapes / 119 on Hull`, `16 stair boxes ...`, and `... unchanged vs HEAD` for Talal's 4 assets, M_AirshipDrivable, M_AirshipProps, CR_Airship, ABP_Airship, A_Airship_TestSweep and IMC_Airship |

Expected WARNs:
* GeometryScript missing: then the triangle counts are not checked, and the other checks still hold.
* The screen-size JSON route refused in step 2: type the two numbers into the SK editor (LOD1 / LOD2 -> LOD Info ->
  Screen Size), save SK_Airship, and as_93 then passes them.
* `CR_Airship` / `ABP_Airship` dirty in memory after a load (seen in round 2; never save them from this session).

After step 5, `as_58_verify_round2.py` reports FAILs that are expected:
* the SK slots are no longer M_AirshipDrivable / M_AirshipProps;
* the turret material is MI_AirshipR3_Props;
* PA_Airship has 143 -> 159 boxes, and the stair ramps are rotated boxes.

`as_93` is the check for round 3.

## 3. Knobs in the editor

| What | Where | Default |
|---|---|---|
| the 24 palette colours (yellow, ochre, orange, rust, keel block slot 16 = rust ...) | `MI_AirshipR3_Look`, group Palette (`Pal_00_paint_yellow` ... `Pal_23_spare_23`) | the export's, linear = Blender's values |
| line width near / far and where it changes | `MI_AirshipR3_Look`: `InkPxNear` 2.2, `InkPxFar` 1.2, `InkFarStart` 4000, `InkFarEnd` 12000 cm, `InkMinHalfWidth` 0.2 cm | as the previews |
| ink colour, opacity | `InkColor` (#1C2230), `InkOpacity` 1 | |
| Talal's comic ink on the hull | `HasComic` switch on `MI_AirshipR3_Hull` **and** `ComicAmount` | off, 0 (v2: the switch is off, so the mask is not sampled; turn both on only after the mask's local re-bake at the base edits) |
| **look in the level's light** (v2) | `MI_AirshipR3_Look`, group Look: `LitMix` (share of the base colour that takes the level's light), `ShadeLift` (emissive floor of the palette colour, the same on screen in any level: `LiftLock` 1 = through EyeAdaptationInverse), `LiftSat` (saturation of that floor: StartupMap's grade desaturates highlights to 0.72) | 0.5, 0.55, 1.3, 1 (calibrated for StartupMap, section 4.8; `LitMix 1, ShadeLift 0` = the v1 plain lit look) |
| **silhouette lines** (v2, question for Talal) | `MI_AirshipR3_Look`: switch `HasSilhouette`, `SilWidthPx`, `SilFadeStart` / `SilFadeEnd` (cm) | off; 2.4 px, faded out from 6000 to 12000 cm |
| far ink fade (v2) | `InkFadeStart` / `InkFadeEnd` (cm), `InkOpacityFar` | 20000 / 40000, 1 (= no fade; lower it if far ships crawl, section 4.1.3) |
| ink decode (must match the bake) | `InkDistMax` 12, `InkDistNeg` 2 | do not change without a re-bake |
| roughness / specular / metallic | `Roughness` 0.9 (M_Airship's), `Specular` 0.5, `Metallic` 0 | |
| props and turrets recoloured (**question for Talal**, `media/export/props_option.jpg`) | SK slot 1 and both turret meshes: `MI_AirshipR3_Props`; back to paper: `AS91_KEEP_PROPS_MATERIAL = True` / `AS91C_KEEP_PROPS_MATERIAL = True` before the exec (as_93 then accepts M_AirshipProps; it reads the knob from their reports), or set slot 1 to `M_AirshipProps` by hand | recoloured (the lead's call; reverts with the knob) |
| LOD distances | SK: LOD1 1.93 (30 m), LOD2 0.72 (80 m); HullDetail (only without Nanite) 1.75 / 0.66 | `AS91_LOD_DIST_M` |
| Nanite on HullDetail | `AS91B_NANITE = False` before the exec of as_91b | on |
| ink texture compression | `AS90_INK_COMPRESSION = 'TC_VECTOR_DISPLACEMENTMAP'` (8-bit uncompressed, 4 times the memory) if BC7 blocks show on the lines | `TC_BC7` |
| ink texture filtering (v2) | `AS90_INK_FILTER`: `TF_TRILINEAR` (blended mips, no anisotropy). Better if the lead adds a project group: in `Config/DefaultDeviceProfiles.ini` under `[GlobalDefaults DeviceProfile]` the line `+TextureLODGroups=(Group=TEXTUREGROUP_Project01,MinLODSize=1,MaxLODSize=16384,LODBias=0,MinMagFilter=aniso,MipFilter=linear,MipGenSettings=TMGS_SimpleAverage)`, then `AS90_INK_FILTER = 'TF_DEFAULT'`, `AS90_INK_LOD_GROUP = 'TEXTUREGROUP_PROJECT01'` (anisotropic and blended). Compare both in the chase shot | `TF_TRILINEAR` |

## 4. PIE checks (lean: one solo run and one listen-server run; Talal 11-27)

The harness scripts are the round 2 / PR B ones; none of them is changed. Fixed 30 fps, as they set it.

### 4.1 Solo (Standalone, 1 player, `L_AirshipTest`)

1. **Regression subset, harness:** set `AS59_ONLY = ('t1_port', 't5_cannon', 't5_turret', 't6_turret', 't3_bullets',
   't8_helm', 't8_walk')` in the inbox namespace, then run `inbox.sh 59 Docs/Airship/scripts/ue/as_59_pie_round2.py 60`.
   Results go to `Saved/Airship/round2/r2_report.txt`. Each check must pass as in round 2:
   * cannons fire from the muzzles;
   * a turret fires, heats and overheats;
   * Visibility traces and sentinel bullets meet the PA boxes;
   * F at the wheel; walking on the planks.
   This is what proves the skeleton, sockets and PA survived. Reset `AS59_ONLY = ()` afterwards.
2. **Stairs (by hand, Play in the viewport):**
   * Walk the mech from the main deck (aft of the stairs, around x 3.3 m) up flight 1, across the landing and up
     flight 2 onto the turret deck, then back down.
   * Feet stay on the treads; no sliding or stepping into the air.
   * The hand rails, the four landing columns and the two guard rails at the platform's aft edge block you.
   * Jump on the ramp once.
   * `show Collision` shows the 16 boxes.
3. **Fly with the chase camera:**
   * Take off, cruise and boost: boost raises the FOV to 107 and brings the LOD switches to about 20 m and 55 m.
   * Watch the ship at 30 m and 80 m for LOD pops: `ShowFlag.LODColoration 1` shows the LOD in use.
   * At 65 m (the default chase distance) the plate outlines are thin and navy, with no shimmer or crawl on the yellow.
   * **Shimmer test (review finding 4):** fly two ships past each other at 80-120 m and watch the Z7 gantry, the stairs and
     the hull side of the other ship. If the lines crawl: `InkPxFar` 1.6-2.0, or `InkOpacityFar` 0.5 with `InkFadeStart`
     8000 / `InkFadeEnd` 15000 (cm), or repack the Z7 sub-page with 6-8 px margins (r3_prep). The offline one-sample test
     showed the ink doubling the frame-to-frame change on ship pixels at 65-120 m; TSR hides part of it.
   * **Far ships (review finding 7):** look at a ship 200-300 m away: no navy wash over the yellow (the v2 line fades out;
     pass 1 put up to 45 % ink on every texel at 200 m).
   * **Mip filtering (review finding 8):** at 40-120 m the line width must not jump as the ship moves through mip
     boundaries; compare `TF_TRILINEAR` with the Project01 group (section 3) once.
4. **Fans from behind:** park and look at the stern (Talal's back view). The fan backs are open; the blades show the
   collar, cuffs and steel tip caps and spin; there is no gap between HullDetail and the skinned parts.
5. **Frame time vs before** (the baseline of step 1.3):
   * Spawn 3 more ships with `Aura.Airship.Spawn` (4 in all) and take the chase view of your own ship from 65 m with
     all 4 in view.
   * Read `stat unit` (Frame, Game, Draw, GPU) and `stat gpu` (BasePass, ShadowDepths, Nanite passes) after 10 s; also
     `stat rhi` (triangles drawn).
   * Do the same on the deck at the stairs (LOD0).
   * Report both against the baseline. Flag a GPU increase over 10 %: the knobs are the LOD distances, and LOD1 of the
     SK from 45 m.
6. **Nanite fallback once:** `r.Nanite 0`. HullDetail switches to its LODs and must still sit on the hull and look the
   same from 40 m and further; up close it must be the full detail mesh (v2: fallback PercentTriangles 1.0, not the
   automatic reduced cut). Then `r.Nanite 1`.
7. **Death and wreck:** `Aura.Airship.Damage` until the ship dies. The HullDetail stays on the wreck (it is attached to
   the Mesh component, which the wreck keeps), and the parts that fall off take their own details with them.

8. **StartupMap look (review findings 1 and 2), once, after the regression runs:** open StartupMap (the match level;
   moon 2.24 lux (125,160,255), sky light 0.7 x (73,203,255), the V2.1 grade), spawn the ship (Aura.Airship.Spawn), and
   take these HighResShots: the chase camera at 65 m with the stern in shadow (fly toward the moon: it shines from the
   bow), `deck_eye`, `q34_fp` (port side, bow quarter). Then:
   * the hull must read **golden yellow, not green or lemon-cream**, and the rust must read **rust, not slate grey**;
     compare with `media/export/game_light_fix.jpg` (the offline model: v1 turned teal, v2 golden);
   * targets from the approved renders (median of a flat painted area, sRGB): shaded hull wall about (208,173,97),
     lit hull about (243,203,115), rust about (160,105,82) shaded;
   * tune in `MI_AirshipR3_Look` only: too pale or lemon -> lower `ShadeLift` by 0.05 and raise `LiftSat` by 0.1; too
     dark or green -> raise `ShadeLift`; flat shading -> raise `LitMix` (more of the level's light); too much cyan in
     the shade -> lower `LitMix`. `export_shade_calib.json` lists the predicted colours per setting;
   * then the same three shots in L_AirshipTest (neutral daylight): the ship must not wash out to cream there either
     (lower `hull_paint` slightly if it does), and once with `LitMix 1, ShadeLift 0` (v1) for the record.
   Write the final values into `as_90`'s `AS90_LOOK_DEFAULT` (and EXPORT_R3 section 15) so a rebuild keeps them.

### 4.2 Listen server (2 players: `set_play_mode.sh listen 2` with the editor closed)

1. Both see both ships with the details, the palette and the ink (HullDetail is a Blueprint component on every
   BP_AirshipPawn).
2. **The client walks the stairs** up and down: the PA boxes exist on both machines, so there is no rubber-banding
   (`p.NetShowCorrections 1` shows none).
3. The client mans a turret and fires, and mans a cannon and fires (or the as_60 subset of those phases).
4. The host flies; the client rides on the deck and on the turret deck while the ship turns. The client stays on it.
5. `stat unit` on both windows once (one process: only a rough check).

## 5. What to capture for Talal

Use `HighResShot 1920x1080` in PIE. Put the shots into `Saved/Airship/captures/round3/` and make a sheet next to the
Blender previews (`Docs/Airship/round3/media/export/baked_sheet.jpg`: approved | preview light | StartupMap light) and
the approved toon renders (`media/full/*_toon_after.jpg`). **Take the main set in StartupMap** (the match level, section
4.1.8) and repeat `side`, `q34_fp` and `chase` in L_AirshipTest. Match these views:

| Shot | View | Compare with |
|---|---|---|
| side | port side, long lens, whole ship | `side_toon_after.jpg`, `side_baked.jpg` |
| q34_fp | three-quarter from the bow, port, slightly above | `q34_fp_*` |
| talal_back | from behind and above: both fans, open fan backs, tip caps | `talal_back_*` |
| pilot_45 | from behind the helm over the deck | `pilot_45_*` |
| deck_eye | standing on the main deck looking at the stairs and the turret deck | `deck_eye_*` |
| stairs_close | 4 m from the stairs: treads, steel hand rails, rivet dots, line width up close | `stairs_close_*` |
| fan_close_L | close on the port fan from behind | `fan_close_L_*` |
| keel_low | under the bow: the rust keel block | `keel_low_*` |
| chase | the default chase camera at 65 m, then boost FOV | `media/export/spike_chase.jpg` |
| fleet | 4 ships at 80-120 m (LOD2) | - |
| far | one ship 200-300 m away (the v2 line fades out, no navy wash) | `media/export/far_ink_fix.jpg` |
| chase, stern in shadow | StartupMap, chase 65 m flying toward the moon | `media/export/game_light_fix.jpg` (chase65_back) |
| LOD1 | the ship at about 40 m (LOD1: no rivet geometry, the dots stay) | `*_baked_lod1.jpg` |
| silhouette A/B | `stairs_close`, `q34_fp`, `deck_cannon`, chase 65 m with `HasSilhouette` off and on (MI_AirshipR3_Look) | `media/export/silhouette_option.jpg` |
| props A/B | `deck_cannon`, `turret_deck` with slot 1 / turrets on `MI_AirshipR3_Props` and on `M_AirshipProps` | `media/export/props_option.jpg` |

Also note what differs from the previews:
* **Silhouettes:** with `HasSilhouette` off (default) there are no heavy silhouette lines on round parts (question 3;
  the switch shows the option).
* **Lighting:** v2's ShadeLift keeps the shaded yellow ochre; check that the lit side is not cream (StartupMap's grade
  desaturates highlights).
* **Ink against the world:** the ship's ink is #1C2230 at full opacity; the world's V2.1 ink is #003E77 and fades with
  distance. At 100 m+ the ship's lines may look darker and harder than the platforms: `InkColor` and the far fade are
  the knobs (a note, not a change: #1C2230 is Talal's comic ink).
* **Plate sides:** they turn from colour to ink beyond about 15 m.
* **Anything that shimmers.**

## 6. If something goes wrong

| Symptom | Likely cause | What to do |
|---|---|---|
| lines dashed or doubled along seams up close | half-float UVs or a weld | `as_93`'s build-settings lines must show `use_full_precision_u_vs True` and `threshold_uv 1.53e-05` on every SK LOD and on HullDetail's LODs |
| blocky or blotchy lines | BC7 on the distance field | `AS90_INK_COMPRESSION = 'TC_VECTOR_DISPLACEMENTMAP'`, then re-run as_90 (only the textures change) |
| line width jumps while flying at 40-120 m | nearest-mip sampling (TEXTUREGROUP_World) | as_93's texture lines must show `filter TF_TRILINEAR` (or the Project01 group) |
| lines on Talal's curved hull wobble by a pixel up close | Unreal triangulated some quads along the other diagonal than the bake (measured offline: at most 1-2 px on a few hundred SM_Airship quads at 5 m, `export_tri_check.json`) | if it shows: triangulate SM_Airship from Blender's loop triangles before export (EXPORT_R3 15.4) |
| ship green / grey in StartupMap | v1 look (LitMix 1, ShadeLift 0) | `MI_AirshipR3_Look` look values (section 4.1.8) |
| the turrets keep the paper look and have 1 UV channel | as_53 re-imported round 2's FBX (pass-1 as_91c) | the v2 as_91c re-points the source first; its lines must show `source ... r3` |
| magenta faces | a palette index on a spare slot | report the face; the export's colour check had 0 such pixels |
| black or wrong colours on the props or turrets | a UV1 palette index missing (round 2 meshes still in place) | re-run as_91 / as_91c, and check `UV channels 2/3` |
| HullDetail shifted against the hull | the Hull bone moved (it should not), or the component is not under Mesh | as_93's `Hull bone rest` and `BP_AirshipPawn.HullDetail` lines; set "Parent Socket: Hull" by hand |
| players fall through the stairs | as_11 ran after as_92 | re-run as_92 |
| SK re-import refused or slots wrong | the stored Interchange pipeline | restart, restore `backup_r3/<stamp>_as_91`, run as_91 again; the as_91 report lists the import data type and the stored pipeline values |

## 7. Review fixes (2026-11-28)

A review of the export run found two blocking problems and several smaller ones. Everything is fixed in the scripts above
and checked offline; nothing has run in the editor yet. The evidence and the renders are in EXPORT_R3.md section 15.

| # | Finding | Verdict | What changed for this stage |
|---|---|---|---|
| 1 | StartupMap's blue moon and cyan sky light turn the plain lit yellow green and the rust grey; the captures were planned only in L_AirshipTest | **real** (the UE 5.8 display model predicts the shaded hull at sRGB (0,56,39): teal) | M_AirshipR3 v2: `LitMix`, `ShadeLift`, `LiftSat`, `LiftLock` (section 3); StartupMap check and tuning (4.1.8); main captures in StartupMap (5) |
| 2 | shaded faces olive even in neutral light, lit yellow can wash to cream | **real** | the same knobs; L_AirshipTest check in 4.1.8 |
| 3 | no silhouettes on round parts | real (known gap) | `HasSilhouette` switch, off by default, shown to Talal (5: silhouette A/B) |
| 4 | ink shimmer at 65-120 m | plausible, a PIE check | shimmer test (4.1.3), far fade knobs (3) |
| 5 | props and turrets recoloured without Talal's yes | **real** (process) | question to Talal with `props_option.jpg`; revert knobs, as_93 accepts them (3) |
| 6 | as_91c re-imported round 2's turret FBX | **real** (both turret assets carry Interchange data pointing at `SourceArt/Airship/SM_AirshipTurret_*.fbx`) | as_91c re-points the source to `r3/` first and checks it after (step 4) |
| 7 | far ships get a navy tint | **real** (45 % ink at 200 m on texels with no line) | v2 `R3InkLine`: the band ends at InkDistMax; far shot (5) |
| 8 | ink textures sample the nearest mip | **real** (World group: MipFilter=point, Vulkan NEAREST) | `filter TF_TRILINEAR` (or a Project01 group), as_93 checks it |
| 9 | HasComic on for the hull MI with ComicAmount 0 | **real** | off by default |
| 10 | screen-size JSON route only WARNs when other fields changed | **real** | FAIL, nothing saved; `AS91_SKIP_SCREEN_SIZES` (step 2) |
| 11 | no UV-channel check on the SK | **real** (`get_num_uv_channels` is not a USkeletalMesh function) | GeometryScript `get_num_uv_sets`, 3 per LOD, in as_91 and as_93 |
| nits | hull rivet halo; Nanite fallback; mesh reference skeleton; do-not-run list; as_93 and the keep knobs; budget notes | real | hull dots 1.2 cm (re-baked hull page), fallback PercentTriangles 1.0, SkeletonModifier check in as_91 / as_93, list in 1.4, budget in 1.5 |
| nits | keel-block scribbles; triangulation; ink colour vs the world | measured / noted | not changed (EXPORT_R3 15.4); ink colour noted in 5 |
