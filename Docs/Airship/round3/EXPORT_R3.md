# Airship round 3: export plan (Blender to Unreal)

Plan for getting the round 3 detail pass into the game with Talal's yellow and rust colours and the navy comic ink.
This page decides the layout, the material, the bake, the LODs, the export and the Unreal import. It also names the
scripts the next agents write and run. The spike in section 7 tried the bake on zone 1.

* Brief: `FULL.md` section 6 (and its section 5 for Talal's open questions), `ZONES.md` section 5 (palette),
  `round2/NOTES_blender.md` sections 7 and 9.
* Input: `rig/detail/zones/AirshipRig_detail_full.blend`, md5 `8b5295f4e51cf590870af58c62650001`. This is the md5
  that FULL.md records and that the file has now (saved 18:31). The task text had `2c92f325...`, which is out of date.
  The prep script checks the file against its fingerprint (`rig/detail/zones/full_hash.json`) instead of an md5.
* Measurements: `export_measure.json` (from `SourceArt/Airship/scripts/r3_measure.py`, read-only).
* Spike: `media/export/spike_*.jpg`. Scripts: `r3_spike.py`, `r3_sdf.py`, `r3_ink.py`, `r3_spike_sheet.py`.
  Outputs: `rig/detail/r3export/spike/`.
* **Update 2026-11-28, after this plan: Talal's three answers are in the full file** (FULL.md section 5a). The new
  md5 is `1f2b3e05bf0a5a47d82db98170b8daaa`, fingerprint `full_hash.json`.
  * The keel block is rust: palette slot `keel_block` (slot 16) for its 8,381 faces. Read it from `r3_base_recolor.py`
    (registry `scripts/base_recolor/z4.json`; full file: face attribute `r3_recolor`). `detail_render.ship_face_classes()`
    already returns `keel_block` there.
  * The rotors have a blade collar, cuffs and steel tip caps: +3,920 triangles per rotor, so
    `SM_AirshipR3Detail_Moving` grows by 7,840.
  * The stair hand rails are a steel tube: +872 Hull-bone triangles.
  * The triangle numbers in sections 1 and 4 predate this (SK LOD0 about 238.4k, HullDetail about 258.2k now).
    `r3_prep.py` recounts them.
* **Update 2026-11-28, UV + bake run (section 13):** the UVs and ink textures of the whole ship are made and checked
  (`r3_prep.py`, `r3_bake.py`, `r3_preview.py`, `r3_checks.py`). Five things changed from this plan, each for a measured
  reason (13.1):
  1. SM_Airship gets its own ink atlas in a third UV channel `R3Ink`; Talal's UV0 stays for his comic mask.
  2. The ink texture stores a **signed** distance: R = (d + 2 cm) / 14 cm.
  3. A numpy rasteriser replaces the Cycles position bake.
  4. Every ink line is a UV island border.
  5. Plate sides show their colour up close and ink from about 15 m out.
  The props and the two turrets are recoloured (the lead's default), so a fourth texture covers the props atlas.
* **Update 2026-11-28, export run (section 14):** the FBX files are written and checked offline, and the Unreal scripts
  are written (not run). Everything is in `rig/detail/r3export/fbx/` and staged into `SourceArt/Airship/r3/` and
  `textures/r3/`. The editor steps are in `EDITOR_STAGE_R3.md`. Four findings change the Unreal plan (14.3):
  1. Unreal must store **full-precision UVs**. Half floats put the ink lines up to 1 texel off on the 4096 pages.
  2. The SK needs **ThresholdUV 1/65536**. With the default 1/1024, 234 corner pairs of SM_Airship's ink atlas would
     weld, up to 4 texels off.
  3. UE 5.8 keeps a skeletal mesh's LOD screen sizes where Python cannot set them as a property. as_91 tries a JSON
     route and otherwise prints the two numbers to type in.
  4. Python cannot set the HullDetail component's parent socket. The Hull bone rests at the origin and never moves, so
     the result is the same.
  The script names differ from section 6 (14.5).
* **Update 2026-11-28, review fixes (section 15):** a review of the export found two blocking problems and several
  smaller ones; each was checked against the engine source, the assets or a measurement, and fixed. The material is now
  **M_AirshipR3 v2**:
  1. In StartupMap (the match level) the plain lit yellow turned teal-green and the rust slate grey. v2 adds a look:
     `BaseColor = c x LitMix`, `Emissive = EyeAdaptationInverse(Sat(c, LiftSat) x ShadeLift)`, defaults 0.5 / 0.55 / 1.3
     chosen with UE 5.8's display model (`r3_shade_calib.py`). This also keeps the shaded stern golden in neutral light.
  2. as_91c would have re-imported round 2's turret FBX; it now points the turrets' stored source at `r3/` first.
  3. Far ships got a navy tint (the ink line's anti-alias band passed InkDistMax); the line now fades out cleanly.
  4. The ink textures sample trilinear (the World group's nearest mip on Vulkan); HasComic is off; the screen-size route
     FAILs on side effects; the SK's 3 UV channels and its own reference skeleton are checked; Nanite's fallback is the
     full LOD0; the hull rivet dots are smaller (hull page re-baked, G only).
  5. A silhouette option (HasSilhouette, default off) and the props A/B are shown for Talal's choice.
  FBX files unchanged; one texture changed (`T_AirshipR3_HullInk`, md5 `71e606b3...`). New sheets: `baked_sheet.jpg`
  (pass 1: `baked_sheet_pass1.jpg`), `game_light_fix.jpg`, `shade_fix.jpg`, `silhouette_option.jpg`, `props_option.jpg`,
  `far_ink_fix.jpg`.

## 0. The decisions

| # | Topic | Decision |
|---|---|---|
| 1 | Mesh layout | **SK_Airship** keeps SM_Airship, the 30 props and the moving-part details, merged into one object `SM_AirshipR3Detail_Moving` (22 objects, 127k triangles, rigid skin kept). The 12 Hull-bone detail objects (257k triangles) become a **separate static mesh** `SM_AirshipR3_HullDetail`. It is a Blueprint component on BP_AirshipPawn, attached to `Mesh` (socket `Hull`) with no collision. **No C++ change.** The skeleton stays the same (118 bones, same names, same order, same rest pose). |
| 2 | Material | (Production values: section 13.1 and 2.2; **v2 look, line and filtering: section 15.**) **One master material `M_AirshipR3`.** Colour comes from a **palette index per face**, stored in UV channel 1 and read from 24 vector parameters in the material instances, so every colour can be changed live in Unreal. Ink comes from a **separate ink texture** on UV0: R = distance to the nearest ink line, G = rivet dots, B = Talal's comic ink (hull only, slider default 0). The material draws lines a fixed number of **pixels** wide (2.2 px) at any distance. There are three textures (hull 4096 on its existing UVs, plus two 4096 detail pages) and three material instances. Colour is not baked. |
| 3 | Bake | (Production method: section 3 and 13.1.) Ink comes from geometry: hard creases, colour-class boundaries, borders and each piece's front outline. It is stored as a distance field, which was the best match to the approved renders in the spike. Talal's `comic_lines.py` shader stays in the pipeline as an option: B channel on the hull, his round 2 mask, with a local re-bake at the three base edits. Rivets become dots. Thin side faces of plates get solid ink, so every plate has its outline band. Faces that cannot be seen get no texture space. Keel block = palette slot `keel_block`, default rust. |
| 4 | LODs | LOD0 everything; LOD1 = no rivet geometry (the baked dots stay) and no pieces under 15 cm; LOD2 = pieces of 0.6 m and more. SK screen sizes are **1.93 (30 m) and 0.72 (80 m)** at FOV 85. The HullDetail static mesh is **Nanite** by default (our LOD1/2 are imported for the non-Nanite case). |
| 5 | Export | Same FBX settings as `rig_export.py` (cm, `Armature` node, primary Z / secondary X, smoothing by face, pre-rotated Y-up data). Round 3 is added behind `--r3` (and `--lod 1/2`). LODs are separate FBX files. The static mesh has its own small exporter. `verify_fbx.py` / `verify_import.py` get `--r3` / `--static`. |
| 6 | Unreal | New scripts `as_90` .. `as_96`: backups, textures and material, SK re-import through an `as_56` wrapper (3 slots, LOD import), static mesh import, Blueprint component, 16 stair boxes into PA_Airship's `Hull` body, final checks. The lead runs them after PR B's tests, then one solo and one multiplayer PIE run. |
| 7 | Spike | Done on zone 1 (section 7). Colours match the approved renders. Plate, frame and bay outlines come out clean. Rivets read as dots, and LOD1's baked dots look the same as LOD0's heads. **Not reached by a bake:** silhouette lines on round parts (big pipes, the hull's strake, edges seen edge-on). Talal's comic shader on colour reads as dirt. |

## 1. Mesh layout

### 1.1 What goes where

| Unreal asset | Content | Bones | Triangles LOD0 / 1 / 2 | Slots |
|---|---|---|---|---|
| `SK_Airship` (re-import) | `SM_Airship` (base edits applied), 30 props, `SM_AirshipR3Detail_Moving` | 118, unchanged | 230.6k / 180.2k / 161.2k | 0 `M_Airship` -> `MI_AirshipR3_Hull`; 1 `M_AirshipProps` (unchanged); 2 `M_AirshipR3_Detail` -> `MI_AirshipR3_Moving` |
| `SM_AirshipR3_HullDetail` (new) | the 12 Hull-bone detail objects (Z1..Z6 hulls, Z4 wedge and keel, Z5 belly, Z7 stairs, gantry, rails, chains) | none | 257.4k / 170.5k / 119.6k (Nanite: one mesh) | 0 `M_AirshipR3_Detail` -> `MI_AirshipR3_HullDetail` |

The moving details are one merged object, `SM_AirshipR3Detail_Moving`, made from the 4 pods, 4 nozzles, 4 petal
sets, fans, rotors, rods, rudder, light posts and heads, and winches. Every vertex keeps its single vertex group,
so the rig stays rigid. The name sorts after `SM_AirshipProp_*` (R after P), so the FBX material order stays
`M_Airship`, `M_AirshipProps`, then the new one. That keeps slots 0 and 1 where `as_10` / `as_56` / `as_61` expect them.
Merging does not change Unreal's draw calls: an SK LOD has one section per material, whatever the number of FBX meshes.
It does make the bake, the checks and the LOD variants one object each.

Sections per ship: SK 3 (today 2), static mesh 1, so 4 draw calls per pass instead of 2. All three use the same
parent material.

### 1.2 Why the Hull-bone details become a static mesh

Measured (`export_measure.json`, unique vertex + corner normal = what Unreal keeps as render vertices):

| | Triangles | Render vertices (est.) |
|---|---:|---:|
| SK_Airship today (`as_10_import.json`) | 104,030 | 126,838 |
| Hull-bone details | 257,366 | ~327,000 |
| Moving details | 127,064 | ~170,000 |
| Everything in the SK | 487,956 | ~624,000 (4.9 times today) |

* The project has **Nanite and virtual shadow maps on** (`Config/DefaultEngine.ini`: `r.Nanite.ProjectEnabled=True`,
  `r.Shadow.Virtual.Enable=1`, commit 82f5399). Only the static mesh can use Nanite here. At the chase camera
  (65 m, FOV 85) a rivet head is under 1 px and a 15 cm latch about 2 px. Nanite draws those 257k small triangles
  as clusters. A skinned mesh draws every triangle in every pass: depth, base, each virtual shadow map page it
  touches, and velocity, for 4 ships.
* No skin cache is configured (`r.SkinCache` is not set), so the skinning runs again in each of those passes. For
  one-bone rigid vertices that alone is cheap (about 1.3 M vertices per pass for 4 ships at LOD0). The real cost is
  the triangle count and the shadow pages, which Nanite takes away.
* A static mesh keeps cached draw commands and its own LOD. The SK's LOD then only carries the parts that move.
* What it costs: one Blueprint component, one more asset and FBX, and the bake's Hull page. **No C++.** I checked
  `Source/Aura`:
  * `AAirshipPawn` uses `Mesh` for the deck and traces (its physics asset, `Mesh->Bodies`, `GetDeckComponent`), for
    bones and sockets (`GetMeshRestLocation`, `DoesSocketExist`) and for the Anim Blueprint. None of that moves.
  * `UMechSentinelObstacleComponent` and `UAirshipSubsystem::RepairPhysicsState` walk all primitive components but
    skip any without collision. The new component is `NoCollision`, so they ignore it.
  * No C++ sets material parameters or dynamic materials on the ship, so nothing has to be mirrored on a second
    component.
* The Hull bone is at the origin with an identity rest pose. CR_Airship drives only the part bones (RIG_CONTRACT:
  Hull is a kinematic body). Attaching to `Mesh` with socket `Hull` matches the skinned result exactly. Python
  cannot reach the Blueprint node's `AttachToName`. If `as_94` cannot set it, the lead sets "Parent Socket: Hull" by
  hand (one field). Without a socket it is the same while Hull is never animated.
* Alternative to test once: if UE 5.8 renders a Nanite skeletal mesh on this RHI, everything could stay in the SK. It
  would need no Blueprint change and no second asset. This is not the plan because it is untested here.

## 2. Material and textures

### 2.1 Colour: a palette index, not a colour bake

Every face has exactly one colour: detail faces by role (`DM_*`), base faces by part class (the toon previews'
`detail_render.ship_face_classes`). The colour is stored as an integer index in **UV channel 1** (`R3Palette`, x =
index, y = 0, the same on all corners of a face). The material looks it up in 24 vector parameters. Why not bake colour:

* Edges between colours stay exactly on the geometry at every distance. A baked colour bleeds between texels and
  mips, and it is soft at the 2 m deck view.
* No colour texture memory. The atlas only has to hold ink.
* **Every colour is a live material-instance knob in Unreal** (Talal can tune the yellow or make the keel block rust
  without a re-bake).
* Integers 0..23 are exact in UE's half-float UVs. UV channels always import; vertex colours depend on the import
  option stored in the asset (the `as_56` stored-pipeline trap).

Palette slots (index = UV1.x). Detail roles keep the `detail_common.ROLES` order, so a detail face's index is its
material index:

| Index | Slot | Default (linear) | Used by |
|---:|---|---|---|
| 0-11 | `paint_yellow`, `paint_ochre`, `paint_orange`, `rust_red`, `rust_dark`, `dark_metal`, `machinery`, `steel`, `copper`, `brass`, `bolt` (rivets and rivet dots), `wood` | ZONES.md section 5 | detail roles; base classes with the same key |
| 12 | `hull_paint` | 0.90, 0.60, 0.17 | base hull skin |
| 13 | `deck` | 0.52, 0.46, 0.38 | base deck tops |
| 14 | `recess` | 0.20, 0.17, 0.16 | pocket walls |
| 15 | `glass` | 0.85, 0.85, 0.70 | (reserved) |
| 16 | `keel_block` | **rust_red 0.50, 0.20, 0.12** (Talal 2026-11-28: yes; knob) | the keel block, `Underside_Front` (8,381 faces), from `base_recolor/z4.json` via `r3_base_recolor.py`; the toon previews draw it rust in the "after" state |
| 17-19 | `prop_wood`, `prop_metal`, `prop_gun` | wood, dark_metal, machinery | the props and both turrets (recolour on by default since 2026-11-28; wheels and carriages wood, the turret gun grey, the rest dark metal, as the approved previews) |
| 20-23 | spare | | |

### 2.2 Ink: a distance field plus pixel-wide lines

Ink texture, linear (sRGB off), **TC_BC7**, clamp addressing, LOD group World (production, section 13):

| Channel | Detail pages, props page | Hull page (SM_Airship's UV2 `R3Ink`) |
|---|---|---|
| R | **signed** distance to the nearest ink line: d = R x (`InkDistMax` 12 + `InkDistNeg` 2) - `InkDistNeg` cm, so R 0..1 = -2..12 cm. Negative only in the margins beyond a feature edge at an island border: bilinear filtering then crosses zero exactly on the edge, so lines at borders stay crisp at any width | the same |
| G | rivet dots (0..1, anti-aliased) | dots of the rivets that sit on the bare hull (710) |
| B | 0 | 0. Talal's comic mask is its **own texture on UV0** (his UVs): `T_AirshipR3_HullComicMask` = round 2's `T_AirshipDrivable_ComicMask.png`, shown by `ComicAmount` (default 0) |

Material `M_AirshipR3`: opaque, Default Lit. Roughness, specular and metallic are copied from `M_Airship` at run time
(roughness 0.9). Usage flags: skeletal mesh and Nanite. Graph:

```
idx   = round(TexCoord[1].x)                         col = Palette(idx)    (Custom node, 24 vector params Pal_*)
s     = InkTex(InkOnUV2 ? TexCoord[2] : TexCoord[0])  [static switch InkOnUV2: on for the hull MI only]
d     = s.r * (InkDistMax 12 + InkDistNeg 2) - InkDistNeg                                 (cm, signed)
col   = lerp(col, Pal_bolt, s.g)                      [static switch HasDots]
px    = PixelDepth * 2 * ViewProperty(TanHalfFieldOfView) / ViewProperty(ViewSize).x        (cm per pixel)
inkpx = lerp(InkPxNear 2.2, InkPxFar 1.2, saturate((PixelDepth - InkFarStart 4000) / (InkFarEnd 12000 - InkFarStart)))
w     = clamp(0.5 * inkpx * px, InkMinHalfWidth 0.2, 0.95 * InkDistMax 12)
line  = 1 - smoothstep(w - 0.5 px, w + 0.5 px, d)
line  = max(line, ComicMask(TexCoord[0]).r * ComicAmount)   [static switch HasComic: hull MI; ComicAmount 0]
BaseColor = lerp(col, InkColor #1C2230, line * InkOpacity 1)
```
**v2 (section 15):** `aa = 0.5 px; w = min(max(0.5 inkpx px, InkMinHalfWidth), InkDistMax - aa); line = (1 - smoothstep(w -
aa, w + aa, d)) * (R <= 0.996) * lerp(1, InkOpacityFar, fade)`; silhouette (HasSilhouette, off) joins the max;
`c = lerp(col, InkColor, line)`, `BaseColor = c * LitMix`, `Emissive = EyeAdaptationInverse(max(Sat(c, LiftSat), 0) *
ShadeLift, LiftLock)`; the hull MI's HasComic is off.

The pixel size comes from `PixelDepth` and the view properties, not from `DDX/DDY`, so the same graph works under
Nanite. `fwidth(AbsoluteWorldPosition)` is the alternative where the slant matters.

| Instance | Texture | Switches / overrides |
|---|---|---|
| `MI_AirshipR3_Hull` (SK slot 0) | `T_AirshipR3_HullInk` (UV2) + `T_AirshipR3_HullComicMask` (UV0) | InkOnUV2 on, HasDots on, HasComic on (ComicAmount 0), **Two Sided on** (FULL.md: SM_Airship shows backfaces round the pods) |
| `MI_AirshipR3_Props` (SK slot 1 + both turret meshes) | `T_AirshipR3_PropsInk` (UV0, the props atlas) | HasDots off. Replaces `M_AirshipProps` on slot 1 (props recolour, default on; knob: keep `M_AirshipProps`) |
| `MI_AirshipR3_Moving` (SK slot 2) | `T_AirshipR3_DetailInk_M` | HasDots on |
| `MI_AirshipR3_HullDetail` (static) | `T_AirshipR3_DetailInk_H` | HasDots on |

### 2.3 Sizes and texel density

| Texture | Size | Content | Texel density (production, section 13) | Memory (BC7 + mips) |
|---|---|---|---|---|
| `T_AirshipR3_HullInk` | 4096 | SM_Airship's own ink atlas, UV2 `R3Ink` (plan: Talal's UV0 at 38.9 texels/m; 13.1 says why not) | 36.4 texels/m | 21 MB |
| `T_AirshipR3_DetailInk_H` | 4096 | Hull-bone details | 70.1 texels/m; Z7 stairs, rails, gantry, chains 105.1 (1.5 times: the deck view). Plan target 80, at least 64 | 21 MB |
| `T_AirshipR3_DetailInk_M` | 4096 (knob: 2048 saves 16 MB at ~59 texels/m) | moving details | 118.7 texels/m (Z7 lights and winches 178) | 21 MB |
| `T_AirshipR3_PropsInk` | 2048 | the props atlas (helm, cannon, turret: Talal's round 2 props UVs, unchanged) | 230.9 texels/m | 5.3 MB |
| `T_AirshipR3_HullComicMask` | 4096 | Talal's comic mask on his UV0 (round 2 file, unchanged; optional, ComicAmount 0; v2: HasComic off, so not sampled or streamed beyond its smallest mips) | 38.9 texels/m | 21 MB (TC_Masks BC1: 10.7 MiB) |

How these were sized:

* **Deck at 2 m:** a pixel is about 2 mm (1080p, FOV 85). No affordable texture reaches that. The distance field
  is what keeps lines sharp when magnified: bilinear filtering of a distance gives a crisp edge with sub-texel
  accuracy. That is why the hull's 39 texels/m (Talal's UVs, unchanged) still gives clean lines up close (spike).
* **Hull at 40-120 m:** a pixel is 3.8-11 cm, so 2-9 texels per pixel at 80 texels/m (mip 1-3). Lines stay
  2.2 to 1.2 px wide because the width follows the pixel size.
* **What the pages hold** (zone 1 spike, 184.4 m² of details): 51 % of the area needs texels. Hidden faces (37 %,
  plate bottoms and faces pressed on other pieces), thin faces (11 %, short side under 2.5 cm) and rivets (1 %)
  map to two reserved 16 x 16 blocks: BLANK (no ink, no dot) and INK (distance 0). Packing efficiency was 28 %
  with 4 px margins and Blender's CONVEX packer. Whole ship: about 755 m² Hull and 360 m² moving need texels. At 28 %
  that is 17.3 M texels for the Hull page, which fits a 4096 page at about 78 texels/m. The prep script picks the
  highest density that fits (64-128 texels/m) and reports it. The production run should try the CONCAVE packer and
  3 px margins first.
* **Margins:** 4 px between islands, 12 px EXTEND bake margin. The distance field tolerates mip bleed: at distance
  a neighbouring border only thickens a line slightly.
* **Base SM_Airship:** the plan reused its UVs as they are (the `UVMap` 4096 layout of Talal's comic texture).
  Production gives it its own ink atlas in UV2 `R3Ink` instead (section 13.1, point 1). UV0 stays his, for his comic
  mask. Its ink texture replaces `T_AirshipDrivable_ComicLines` in the material. Talal's textures and
  `/Game/Assets/MyShip` assets stay untouched.
* **Details:** new atlas, no overlaps (the prep checks this by rasterising every page). Rivet and other blank faces
  get collapsed UVs on purpose.

## 3. The bake

**Production (2026-11-28, section 13):** `r3_bake.py` follows the steps below with four changes:
* Step 1: no Cycles. `r3_raster.py` rasterises each page's UV triangles in numpy. It is deterministic, CPU only, and
  gives every texel within 8 px of an island the 3D position on its nearest triangle's plane, extrapolated outside the
  triangle.
* Step 2: the crease angle on SM_Airship is 42 degrees, the approved renders' Freestyle crease angle (138).
* Step 3: a texel sees the feature edges of its own piece within 12 cm of its face (not the 1-ring), with a
  behind-the-face test. In the margin beyond a feature edge the distance is negative.
* Step 5: the plate sides block holds d = 1.5 cm instead of 0.
It needs no GPU. The plan's version follows.

`r3_bake.py` (Blender, headless, `BL_MEM_MAX=6G`; GPU Cycles, `--cpu` when the Unreal editor holds the GPU). It works
on `rig/detail/r3export/AirshipR3_export.blend`, which `r3_prep.py` writes. It bakes one page at a time:

1. **Bake mesh:** a temporary join of SM_Airship (base edits applied), all details without the rivet faces, and the
   props. The page's atlas faces target the page image, everything else a dummy. Two emission bakes at 1 sample, 12 px
   EXTEND margin: world position (float) and face id (float attribute `r3_fid`). The spike needed 17-22 s on the GPU
   for one 2048 page plus the 4096 hull.
2. **Feature edges** (`r3_sdf.feature_segments`), computed on the merged mesh:
   * hard creases, where the faces turn more than 35° (hull) or 60° (details: corners of boxes and housings);
   * class boundaries (palette slot changes), open borders and non-manifold edges;
   * each piece's **front contour**: the edge between faces within 30° of the piece's front (the mean normal of its
     visible faces, or the hull's outward normal when they cancel) and its other faces. This is the outline a view
     from outside the hull sees: the plate edges of the approved renders. Each texel's distance is measured to the
     feature edges touching its face's vertices.
3. **Distance field** (`r3_sdf.distance_map`) into R. The hull is done on its own UVs with the same rules. Its skin
   (the largest piece) gets creases and class boundaries only; its other pieces (rails, beams) also get front
   contours. The spike needed 1.2 s for zone 1 and 12 s for the 4096 hull.
4. **Rivet dots** into G: each rivet head (Freestyle-marked piece) is projected onto the surface under it (ray along
   the head's axis). Every texel within 1.8 cm of that foot point gets a dot, anti-aliased by half a texel. Dots go
   to whichever page owns the face under the rivet (detail page or hull). In zone 1, 695 of 880 rivets landed on
   detail faces and 183 on the bare hull (the spike dotted only the detail ones; production writes the hull ones too).
5. **Solid-ink sides:** thin side and chamfer faces reached from an atlas front face in up to 2 steps get the INK
   block. This makes the plate's outline band, and it reads like the previews' contour lines from oblique views.
   Thin faces of pieces with no atlas front (conduits, thin rods) stay plain colour.
6. **Hull B channel (Talal's comic ink, optional):** start from round 2's
   `rig/checks/hull_ink/T_AirshipDrivable_ComicMask.png`. Re-bake it locally around the three base edits with
   `hull_ink_drivable.py`'s method (his `M_ComicLines`, 4096, 64 spp, seed 0, his blur and smoothstep): A = the
   edited SM_Airship, B = round 2's, take A where A != B within 1.5 m of a deleted island. The places are each fan's
   inner duct wall (x -17.8 .. -17.9), the hub's rear face and the duct exit, and the ChainAft line (x 12.2 .. 16.2).
   Report per group as round 2 did. The R channel needs no special case: it is computed on the edited mesh, so no
   line remains where deleted parts stood.
7. **Write** 8-bit RGB PNGs (R steps 0.47 mm over 12 cm). Re-run once and compare md5. Write `r3_bake_report.json`:
   densities, coverage, feature counts, rivets dotted, the B re-bake groups, input md5s.

Keel block rust is only a palette value (slot 16), so it needs no geometry or bake change. The bake has no colour
in it.

## 4. LODs

| LOD | Details kept | SK triangles | HullDetail triangles | Screen size (FOV 85) |
|---|---|---:|---:|---|
| 0 | everything | 230.6k | 257.4k | - |
| 1 | no rivet faces (the dots stay), no loose pieces under 15 cm (bounding-box diagonal) | 180.2k | 170.5k | **1.93** (from ~30 m) |
| 2 | only pieces of 0.6 m and more | 161.2k | 119.6k | **0.72** (from ~80 m) |

* Unreal's screen size is `max(P[0][0], P[1][1]) * R / D` (ComputeBoundsScreenSize). With FOV 85 at 16:9,
  `P[1][1] = 1.94`, so the screen size is `1.94 * R / D`. The SK's bounds radius is **29.8 m** (bounds from `as_10_import.json`: -2039..3150,
  -1196..1190, -617..1080 cm). That gives 1.93 at 30 m and 0.72 at 80 m. During boost and speed FOV (up to 107°)
  the switches come at about 20 m and 55 m. The script computes the values from the imported bounds.
* Every deck position is within ~31 m of the bounds centre, so players on deck always see LOD0. The default chase
  camera (`CameraArmLength` 6500, `BaseFOV` 85) sits at about 70 m from the centre, so your own ship is LOD1 and far
  ships are LOD2.
* SM_Airship and the props are the same in every SK LOD.
* Correction to FULL.md: at 40 m a pixel is ~3.8 cm, so pieces under 15 cm are ~4 px there, not under a pixel.
  The baked dots hide the rivet swap (spike, LOD1 tile). Latches and hinges do drop at 30 m. If that pop shows in
  PIE, the knobs are the LOD1 cutoff (0.10 m) or LOD1 from 45 m (screen size 1.28).
* HullDetail: **Nanite on** (knob). When Nanite is on, Unreal renders the full mesh and builds its own fallback, so
  our LOD1 and LOD2 are imported too but only used when Nanite is off (`as_93 --no-nanite`, or a platform without
  Nanite).

## 5. Export and verification

`r3_prep.py` (Blender, read-only on its inputs) writes `rig/detail/r3export/AirshipR3_export.blend` and
`r3export/manifest.json`. It starts from the full file and checks it against `full_hash.json`. Then it:

* merges the 22 moving objects into `SM_AirshipR3Detail_Moving` and the 12 Hull-bone objects into
  `SM_AirshipR3_HullDetail`. Each keeps a face attribute `r3_src` (source object) and its vertex groups;
* gives every mesh exactly two UV layers, `UVMap` (SM_Airship: Talal's; props: the props atlas; details: the page
  atlas) and `R3Palette` (index per face);
* sets one material per object: `M_Airship`, `M_AirshipProps`, `M_AirshipR3_Detail`;
* classifies faces (rivet, hidden, thin, ink side, atlas), unwraps and packs both pages, and checks there are no overlaps;
* builds the LOD1 and LOD2 variants (`..._LOD1`, `..._LOD2` objects);
* writes the manifest: per detail vertex the expected bone; per face the palette index; page densities; bounds in UE cm.

Exports (FBX settings as round 2: `use_space_transform`, axis forward -Z / up Y with the data pre-rotated by `RX`,
cm data with `scale_length 0.01`, `armature_nodetype NULL`, `primary_bone_axis Z`, `secondary_bone_axis X`,
`add_leaf_bones False`, `mesh_smooth_type FACE`, `use_tspace False`, no custom properties):

| Command | Output |
|---|---|
| `rig_export.py -- --r3` | `r3export/SK_Airship.fbx` (32 meshes: SM_Airship, 30 props, Moving; asserts that count and that SM_Airship sorts first) |
| `rig_export.py -- --r3 --lod 1` / `--lod 2` | `r3export/SK_Airship_LOD1.fbx` / `_LOD2.fbx` (the Moving LOD variant in place of LOD0) |
| `r3_export_static.py [--lod 1/2]` | `r3export/SM_AirshipR3_HullDetail[_LOD1/_LOD2].fbx` (the object only: no armature, no skin, same pre-rotation, so the vertices sit at UE `(100x, -100y, 100z)`, Mesh component space) |

`rig_export.py` gets only an `if R3:` branch (input blend, expected count, LOD object swap, output folder). Without
flags it behaves as in round 2 and opens `rig/AirshipRig.blend`. The test sweep FBX is not needed: no bone changes.

`verify_fbx.py -- --r3 --fbx ... --out r3export/checks/fbx_verify.json`:
* SM_Airship = Talal's mesh minus `deck_removals.json` **minus the round 3 base edits**. The islands are resolved
  through `detail_base_edits` (1028, 1030, 1088, 1091, 379-384; 156 faces / 504 triangles), and positions, UV0 and
  face order are compared;
* every mesh has 2 UV layers: UV1 integer, the same on all corners of a face, 0..23;
* materials, in this order: `M_Airship`, `M_AirshipProps`, `M_AirshipR3_Detail`;
* detail weights: one bone, weight 1, and the bone the manifest expects for that vertex;
* bone set, parents and rest pose: the existing contract checks, unchanged (118 bones).

`verify_fbx.py -- --static` covers the HullDetail FBX: positions against the manifest (within 0.01 cm), one
material, 2 UV layers, no skin.

`verify_import.py -- --r3`: the second reader. Its deformation test (each bone rotated alone moves exactly its own
vertices) covers the Moving object, using the manifest.

`verify_all.sh` gets an r3 variant that runs all of these and writes `r3export/checks/`.

## 6. Unreal import plan (scripts written by the export agent, run by the lead; no editor in this run)

> **As written (2026-11-28, section 14.5):** `as_90_r3_textures_material`, `as_91_r3_reimport` (SK + LODs + slots),
> `as_91b_r3_hull_detail` (static mesh + Blueprint component), `as_91c_r3_turrets`, `as_92_r3_pa_stairs` and
> `as_93_r3_verify`, plus the shared `as_9x_r3lib`. Every script backs up what it changes into
> `Saved/Airship/backup_r3/`, so there is no separate backup script. Run order and expected output: `EDITOR_STAGE_R3.md`.
> The table below is the plan as first written.

Assets (`/Game/Assets/MyShip/Drivable/`):

| Asset | Change |
|---|---|
| `SK_Airship` | re-import from `SourceArt/Airship/r3/SK_Airship.fbx` (a copy of `r3export/SK_Airship.fbx`) + LOD1 and LOD2 |
| `SKEL_Airship` | unchanged (re-import keeps it; no reference-pose change because no bone moved) |
| `PA_Airship` | + 16 stair boxes on body `Hull` |
| `CR_Airship`, `ABP_Airship`, `A_Airship_TestSweep` | unchanged |
| `BP_AirshipPawn` | + component `HullDetail` (StaticMeshComponent) |
| `SM_AirshipR3_HullDetail` (new) | static mesh (+ LOD1/2, Nanite) |
| `Materials/M_AirshipR3`, `MI_AirshipR3_Hull`, `MI_AirshipR3_Moving`, `MI_AirshipR3_HullDetail` (new) | section 2 |
| `Textures/T_AirshipR3_HullInk`, `T_AirshipR3_DetailInk_H`, `T_AirshipR3_DetailInk_M` (new) | BC7, sRGB off, clamp |
| `Materials/M_AirshipDrivable`, `M_AirshipProps`, `Textures/T_AirshipDrivable_ComicLines`, `T_AirshipProps_*` | kept, no longer on slot 0 (M_AirshipDrivable) or unchanged (props) |
| Talal's `/Game/Assets/MyShip/M_Airship`, `T_Airship_*`, `SM_Airship` (UCX flight body) | untouched (scripts check bytes before and after) |

Scripts in `Docs/Airship/scripts/ue/`. Run through the inbox harness, without PIE, editors of SK, SKEL, PA, CR, ABP
and BP closed, after PR B's tests:

| Script | What |
|---|---|
| `as_90_r3_backup.py` | Copies the `.uasset` files of every asset above that already exists to `Saved/Airship/r3_backup_<stamp>/` and stores their sha256 (refuses dirty assets). Restore = copy back with the editor closed. |
| `as_91_r3_textures_material.py` | Imports the 3 PNGs (settings above). Builds `M_AirshipR3` with MaterialEditingLibrary: the Custom palette node, the switches, the parameters in section 2.2, comment boxes. Creates the 3 MIs with palette defaults from `manifest.json`. Linear colours match Blender's 1:1. Checks the parameter values by reading them back. Saves only its own assets. |
| `as_92_r3_reimport_sk.py` | Wrapper around `as_56_reimport_airship.py`, using checked in-memory text patches the way as_56 patches as_10: FBX / rig FBX / verify-JSON paths point to round 3; as_10's `MAT0` = `MI_AirshipR3_Hull`; 3 slots expected, with slot 2 = `MI_AirshipR3_Moving`; triangle count from the round 3 `fbx_verify.json`. The stored update-reference-pose flag is not needed and left alone. Then `SkeletalMeshEditorSubsystem.import_lod(SK, 1/2, ...)` and LOD screen sizes 1.93 / 0.72 (computed from the bounds), no reduction. Checks: 118 bones and names, SKEL_Airship, no new skeleton, PA_Airship pointer and bytes unchanged at this step, sockets present, 3 sections per LOD, triangles per LOD = the FBX, UV channels >= 2. Re-importing the base mesh can drop imported LODs: always run the LOD step after any SK re-import. |
| `as_93_r3_hull_detail_sm.py` | Imports `SM_AirshipR3_HullDetail` with the legacy FbxFactory: combine meshes, no collision, no lightmap UVs, import normals, `convert_scene` on, no front-X, scale 1. Imports LOD1/2 with `StaticMeshEditorSubsystem.import_lod`, screen sizes from its bounds. Nanite on (`--no-nanite` knob). Slot -> `MI_AirshipR3_HullDetail`. Checks: bounds = manifest within 1 cm, triangles per LOD, 2 UV channels. |
| `as_94_r3_pawn_component.py` | BP_AirshipPawn, through SubobjectDataSubsystem: adds `HullDetail` under the inherited `Mesh`, socket `Hull` (or a note for the lead to set it by hand), mesh = SM_AirshipR3_HullDetail, `NoCollision`, no overlaps, `CanEverAffectNavigation` off, casts shadow. Compiles and saves. Checks: on the CDO, parent `Mesh`, relative transform identity. |
| `as_95_r3_pa_stairs.py` | Adds the 16 boxes of `round3/stairs_collision.json` to PA_Airship body `Hull` with PhysicsAssetToolset `SetBox`. Centre = json centre minus the Hull bone (at the origin; checked), rotation from the json (pitch 36.093 on the ramps), extent = full size. The four `Stairs_Column` entries get unique names `_0` .. `_3`. Re-runnable (same names update). Reads back and compares each box's 8 corners with the json's within 0.5 cm, kinematic body unchanged. `as_11` rebuilds the PA without them, so re-run `as_95` after any `as_11`. `as_58` will then count 159 boxes / 119 hull boxes (was 143 / 103): expected, not a regression. |
| `as_96_r3_verify.py` | Read-only: slots and MIs, texture settings, palette values, LOD screen sizes, the component, PA box count, SM_Airship triangles (base edits applied), Talal's assets untouched. Optional SceneCapture stills at the spike's cameras for a side-by-side with `media/export/`. |
| PIE (lead, harness, one solo + one multiplayer run per Talal 11-27) | Fly, walk up the stairs onto the turret deck (the boxes), cannons and turrets fire, HullDetail stays on the hull (no lag, no gap on death and wreck), with 4 ships `stat unit` / `stat gpu` against the current build, `r.Nanite 0` once for the fallback. |

## 7. The spike: one zone 1 area baked and rendered

`r3_spike.py` bakes all four zone 1 objects (port flank, pod FL, nozzle, petals) and the hull's ink. It renders in
EEVEE with a material that mimics the planned Unreal one: palette colour per face, ink texture, lines of fixed pixel
width (from the camera's view distance, as `PixelDepth` gives in Unreal), rivet dots, Principled at roughness 0.9,
sun plus sky ambient, Standard view. The props keep their in-game paper texture. Sheets (`r3_spike_sheet.py`):

* `media/export/spike_close_flank.jpg`: approved toon | bake, lit | bake, unlit (texture and palette alone) | LOD1
  (no rivet geometry, baked dots).
* `media/export/spike_ink_methods.jpg`: Talal's comic shader on the details (scaled knobs, his hull ink) | plus his
  shader re-baked on the hull without hatching | geometric distance-field lines (chosen) | approved toon.
* `media/export/spike_q34.jpg`, `spike_side.jpg`: approved vs bake at ~25 m and in side view.
* `media/export/spike_chase.jpg`: the default chase camera (65 m, FOV 85), LOD0 vs LOD1, 1:1 crops.

Zone 1 numbers (`rig/detail/r3export/spike/I/spike_report.json`): 26,725 faces / 184.4 m². 7,103 atlas faces
(94.9 m²), 2,647 hidden (68.2 m²), 9,055 thin, 7,920 rivet. 80 texels/m on a 2048 page used 0.72 x 0.72 of it.
Feature edges 51,350 (46k creases, 4.4k front contours, 380 class boundaries). 880 rivets: 695 dotted, 183 on the
hull. The whole run takes 48 s on the GPU.

**Verdict, honestly:**
* **Colours:** a match. The palette per face gives the approved yellow, ochre, rust and grey exactly, with clean edges.
* **Plate outlines:** good. Plates, picture frames, bays, slotted plates and straps get a clean navy outline 2-3 px
  wide, close to the approved renders. Some outlines are uneven or broken where a plate's chamfer is a single thin
  face. Tuning knobs: `--min-w`, `--cap-deg`, `--ink-px`.
* **Missing:** the approved renders' heavy silhouette lines on round parts (the big copper pipes, the hull's strake
  bar and grey band) and on edges seen edge-on. A texture cannot hold a view-dependent silhouette. The fix is a
  screen-space outline for the ship (question 3). The front contours get some of it (fan rims read well at 65 m).
* **Talal's comic shader on colour** (`spike_ink_methods`, first two tiles): his spotted blacks and hatching turn
  into dark smudges and sawtooth blobs on yellow. With knobs scaled for details, plate edges still do not come out,
  because the post-process removes lines thinner than about 2 texels. Re-baking the hull with the details present
  adds contact blobs under every plate. It is not good enough as the main ink. It stays available as the hull's B
  channel (slider).
* **LOD1:** the baked dots look the same as LOD0's rivet heads (`spike_close_flank`, last tile; `spike_chase`).
* **Props:** paper-white cannons and helm stand out on the yellow and rust ship at every distance (`spike_q34`,
  `spike_chase`). This is a clash (question 1).
* **Not proven:** Unreal's tonemapper and lighting (the mimic uses the Standard view and a simple sun), BC7 on the
  distance field, Nanite with this material, and the whole ship's packing (zone 1 only). `as_96` stills and the
  PIE run close that gap.

## 8. Pipeline: who runs what

> Export steps as run (2026-11-28): `SourceArt/Airship/scripts/r3_export_all.sh` runs everything after the bake (FBX,
> checks, round trip, staging) in about 3 minutes (section 14.6). The lines below are the plan.

```
B=/mnt/new_partition/UnrealProjects/_AirshipWork_logs/blender_capped.sh
S=/mnt/new_partition/UnrealProjects/_AirshipWork/SourceArt/Airship/scripts
X=/mnt/new_partition/BlenderProjects/StylizedAirship/rig/detail/r3export
SA=/mnt/new_partition/UnrealProjects/_AirshipWork/SourceArt/Airship ; R=/mnt/new_partition/BlenderProjects/StylizedAirship/rig
# Export agent (Blender, no editor)
BL_MEM_MAX=6G $B --python $S/r3_prep.py                      # 40 s -> $X/AirshipR3_export.blend, manifest.json, checks/prep_report.json
BL_MEM_MAX=6G $B --python $S/r3_bake.py                      # 6 min, CPU -> $X/textures/T_AirshipR3_*.png, checks/r3_bake_report.json
#   determinism: ... r3_bake.py -- --out $X/textures_det --compare $X/checks/r3_bake_report.json   (SAME per page)
BL_MEM_MAX=5G $B --python $S/r3_preview.py -- --shots q34_fp,side,pilot_45,talal_back,stairs_close,fan_close_L,keel_low,deck_eye
#   (+ --variants flat,idx for the colour check, --lod 1 for the dots alone)  -> media/export/<shot>_baked[_lod1].jpg
BL_MEM_MAX=6G $B --python $S/r3_checks.py                    # base-edit check + Docs/Airship/round3/export_bake.json
python3 -B $S/r3_preview_sheet.py --crops                    # media/export/baked_sheet.jpg, baked_crops.jpg
cp $X/textures/T_AirshipR3_*.png $SA/textures/r3/ ; cp $R/checks/hull_ink/T_AirshipDrivable_ComicMask.png $SA/textures/r3/T_AirshipR3_HullComicMask.png
$B --python $S/rig_export.py -- --r3 ; ... --r3 --lod 1 ; ... --r3 --lod 2
$B --python $S/r3_export_static.py ; ... --lod 1 ; ... --lod 2
$B $X/../../checks/verify/Talal_copy.blend --python $S/verify_fbx.py -- --r3 --fbx $X/SK_Airship.fbx --out $X/checks/fbx_verify.json
$B --python $S/verify_fbx.py -- --static --fbx $X/SM_AirshipR3_HullDetail.fbx --out $X/checks/sm_verify.json
$B --python $S/verify_import.py -- --r3 --fbx $X/SK_Airship.fbx --out $X/checks/import_verify.json
cp $X/SK_Airship*.fbx $X/SM_AirshipR3_HullDetail*.fbx SourceArt/Airship/r3/      # what the UE scripts read
# Lead (editor, after PR B's tests): as_90 .. as_96 in order, then PIE (section 6)
```

Every Blender script records the md5 of the protected files at start and end (as the zone runs did) and never writes
outside `rig/detail/r3export/` and `Docs/Airship/round3/` (`r3_common.check_out_path`). `AirshipRig_detail_full.blend`
is only read.

## 9. Knobs

| Knob | Default | Where |
|---|---|---|
| palette values (24 slots) | ZONES.md section 5, keel block rust | MI vector params `Pal_*` (live) |
| line width near / far, fade distances | 2.2 px -> 1.2 px from 40 to 120 m | MI `InkPxNear/Far`, `InkFarStart/End` |
| ink colour, opacity | #1C2230, 1 | MI |
| Talal's comic ink on the hull | 0 | MI `ComicAmount` |
| stored distance range | -2 .. 12 cm | `r3_bake --dmax 0.12 --dneg 0.02` = MI `InkDistMax` / `InkDistNeg` (must match) |
| crease angles (hull / details / props), front cone, tube cone | 42° / 60° / 45°, 30°, 30° | `r3_bake --crease-deg --box-deg --prop-deg`, `r3_prep --crease-deg --box-deg --cap-deg --cap-deg-tube` (prep and bake must agree: the seams follow the feature edges) |
| thin-face width (details / hull), hidden-face distance | 2.5 cm / 4.5 cm (hull: only strips with a long feature edge), 2 cm | `r3_prep --min-w --min-w-hull --cull` |
| plate sides (side block value) | 1.5 cm: colour up close, ink once a line is wider (about 15 m) | `r3_bake --side-d` (0 = the plan's solid ink) |
| ink lines as island borders | on | `r3_prep --seams features` (`smart` = the plan's smart-project islands only) |
| SM_Airship ink UVs | own atlas in UV2 `R3Ink` | `r3_prep --hull-uv atlas`, or `talal` (UV0, the plan) |
| extrapolated margin, feature lists, behind test | 8 px, piece within 12 cm, 0.7 | `r3_bake --margin-px --lists piece` (`ring` = the spike's 1-ring) `--behind` |
| rivet dot radius | 1.8 cm | `r3_bake --dot-r` |
| page density / size / packer | fills the page (70 / 119 / 36 texels/m), 4096, CONCAVE, 4 px | `r3_prep --density --tex-h --tex-m --tex-hull --pack-px --shape --z7-scale 1.5` |
| LOD1 cutoff, LOD2 cutoff, distances | 15 cm, 0.6 m, 30 m / 80 m | `r3_prep`, `as_92/as_93` |
| Nanite on HullDetail | on | `as_93 --no-nanite` |
| props recolour | **on** (the lead's call, 2026-11-28: like the approved previews; **question to Talal**, section 15.5) | `r3_prep --props-palette`, `r3_preview --props-palette off` shows the old paper props; in Unreal: `AS91_KEEP_PROPS_MATERIAL` / `AS91C_KEEP_PROPS_MATERIAL` keep `M_AirshipProps` (as_93 accepts it) |
| look in the level's light (v2) | LitMix 0.5, ShadeLift 0.55, LiftSat 1.3, LiftLock 1 (StartupMap); 1 / 0 = v1 | MI `LitMix`, `ShadeLift`, `LiftSat`, `LiftLock`; `r3_shade_calib.py`; `r3_preview --look` |
| silhouette option (v2) | off; 2.4 px, fade 60-120 m, SilMinSlope 0.02 | MI switch `HasSilhouette`, `SilWidthPx`, `SilFadeStart/End`, `SilMinSlope`; `r3_preview --sil on` |
| far ink fade (v2) | none (InkOpacityFar 1 from 200 to 400 m) | MI `InkFadeStart/End`, `InkOpacityFar`; `r3_preview --ink-fade-*` |
| ink texture filter (v2) | trilinear | `as_90 AS90_INK_FILTER` / `AS90_INK_LOD_GROUP` |
| hull rivet dot radius (v2) | 1.2 cm (details 1.8 cm) | `r3_bake --dot-r-hull` |

## 10. Risks and open items

1. **Silhouettes:** see the spike verdict. A screen-space outline is a separate task (custom depth plus a
   post-process, or the hex materials' outline code) if Talal wants it.
2. **SK re-import:** the stored Interchange pipeline in SK_Airship (round 2 lesson) and LOD import are untested
   together. Run `as_92` on a restored backup copy first if anything fails, and use the "restart the editor between
   failed runs" rule from as_56.
3. **Nanite:** check it renders with this material on Vulkan SM6 (the project targets SM5 and SM6). The fallback
   mesh is what SM5 sees.
4. **Packing efficiency** (28 % in the spike) decides whether the Hull page reaches 80 texels/m. Production: CONCAVE
   packs 32 % (H) and 40 % (M). H fills its page at 70.1 texels/m (Z7 105.1), above the 64 floor and under the
   80 target. Lines are crisp at any distance anyway (signed borders, 13.1), so the density mostly decides how thin a
   plate may be before it goes to the side block.
5. **Hull creases:** 42° in production (the approved renders' Freestyle angle). At 35° the lumpy keel block drew more
   scribbles than the approved renders.
6. **Thin plate chamfers:** in production they show their colour up close (side block 1.5 cm) and the plate face's own
   border line is crisp. The plan's solid ink made heavy black bands at 5 m (fan close-up, first preview).
7. **PR B's job** is testing in the editor now. Run the Unreal steps only after it finishes. Nothing here touches
   `Source/`, `round2/` or `scripts/harness/`.
8. ChainAft over the bow ledge (FULL.md section 5 point 1) is still open for the lead or Talal. The stairs boxes do
   not change it.

## 11. Questions for Talal (each one changes his look; defaults in brackets)

> **2026-11-28 review fixes:** questions 1-4 are restated with renders in section 15.6 (props A/B, silhouette option,
> the in-game look in StartupMap). Question 1's default is the lead's call (recoloured), now put to Talal explicitly.

1. **Props and turrets:** in game they are paper white with navy ink. On the yellow and rust ship they stand out
   (`spike_q34`, `spike_chase`). Should they be recoloured like the approved previews (wooden carriages and wheels,
   dark-metal barrels and guns) with the same palette material? [Unchanged until you say so; prepared as an opt-in
   step.]
2. **Ink style:** clean geometric outlines like the approved previews, or some of your comic ink (hatching, spotted
   blacks) on top? On colour it reads as dirt in the spike (`spike_ink_methods`). [Outlines; your hull ink stays
   available as a slider at 0.]
3. **Silhouette lines:** the previews draw heavy lines round pipes, hull edges and anything seen edge-on. A baked
   texture cannot. Add a screen-space outline for the ship? [No outline pass for now.]
4. **Shading:** in game the ship is lit by the sun and sky like today. The previews use three flat cel bands. Keep
   it lit? [Lit.]

Answered by Talal on 2026-11-28 (FULL.md section 5a), each still a knob: keel block rust (palette slot 16), a blade
collar and tip caps on the fan blades, steel stair hand rails.

## 12. Files

| File | What |
|---|---|
| `Docs/Airship/round3/EXPORT_R3.md` | this plan |
| `Docs/Airship/round3/export_measure.json` | measurements (`r3_measure.py`) |
| `Docs/Airship/round3/media/export/spike_*.jpg`, `spike_shots.json` | spike sheets and the extra cameras |
| `SourceArt/Airship/scripts/r3_measure.py` | read-only measurements |
| `SourceArt/Airship/scripts/r3_ink.py` | Talal's comic shader as a reusable material (his source read through `ast`, two checked patches for hatch and panel knobs) |
| `SourceArt/Airship/scripts/r3_sdf.py` | feature edges, pieces, front contours, distance field |
| `SourceArt/Airship/scripts/r3_spike.py`, `r3_spike_sheet.py` | the spike |
| `rig/detail/r3export/spike/<A,B,C,D,E,F,G,H,I>/` | spike variants: A-C comic shader (A his knobs; B scaled; C plus hull re-bake), D-H distance-field iterations, I chosen |
| `SourceArt/Airship/scripts/r3_common.py`, `r3_prep.py`, `r3_raster.py`, `r3_bake.py`, `r3_preview.py`, `r3_preview_sheet.py`, `r3_checks.py` (+ additions to `r3_sdf.py`) | the UV + bake run (section 13) |
| `rig/detail/r3export/AirshipR3_export.blend`, `manifest.json`, `manifest_arrays.npz`, `textures/`, `checks/` | its outputs (section 13.6) |
| `Docs/Airship/round3/export_bake.json`, `export_colour_check.json`, `media/export/*_baked*.jpg`, `baked_sheet.jpg`, `baked_crops.jpg` | its reports and renders |
| `SourceArt/Airship/scripts/rig_export.py --round3 [--lod N]`, `r3_export_static.py`, `r3_fbx_check.py`, `verify_fbx.py --r3`, `verify_import.py --r3`, `r3_preview.py --from-fbx`, `r3_roundtrip_sheet.py`, `r3_unreal_inputs.py`, `r3_export_all.sh` | the export run (section 14) |
| `rig/detail/r3export/fbx/*.fbx`, `checks/fbx_check.json`, `fbx_verify*.json`, `import_verify*.json`, `export_static.json`, `r2_repro/` | its outputs |
| `SourceArt/Airship/r3/` (8 FBX + `r3_unreal_inputs.json`), `SourceArt/Airship/textures/r3/` (5 PNG) | what the Unreal scripts read |
| `Docs/Airship/scripts/ue/as_9x_r3lib.py`, `as_90_r3_textures_material.py`, `as_91_r3_reimport.py`, `as_91b_r3_hull_detail.py`, `as_91c_r3_turrets.py`, `as_92_r3_pa_stairs.py`, `as_93_r3_verify.py` | the editor stage (`EDITOR_STAGE_R3.md`) |
| `Docs/Airship/round3/export_fbx_check.json`, `export_roundtrip.json`, `media/export/roundtrip_sheet.jpg`, `media/export/*_baked_{blendref,fbx}.jpg` | the export run's reports and renders |
| `SourceArt/Airship/scripts/r3_look.py`, `r3_shade_calib.py`, `r3_hlsl_check.py`, `r3_tri_check.py`, `r3_review_renders.sh`, `r3_review_sheets.py` (new); `r3_preview.py`, `r3_preview_sheet.py`, `r3_bake.py`, `r3_unreal_inputs.py` (extended) | the review fixes (section 15) |
| `Docs/Airship/round3/export_shade_calib.json`, `export_hlsl_check.json`, `export_tri_check.json`, `export_review_renders.json`, `media/export/{baked_sheet,baked_crops,game_light_fix,shade_fix,silhouette_option,silhouette_option_crops,props_option,far_ink_fix}.jpg`, `review_fix_shots.json`, `media/export/pass1/` | its reports, sheets and the pass-1 renders |

## 13. UV + bake run (2026-11-28): results

The UV atlases and ink textures for the whole ship are made, checked and previewed. They cover SM_Airship with the base
edits, all 34 details (merged into `SM_AirshipR3_HullDetail` and `SM_AirshipR3Detail_Moving`), the 30 props and the
two turret meshes. No Unreal editor and no Blender MCP were used. Everything ran headless through
`blender_capped.sh`.

### 13.1 What changed from the plan, and why

| # | Change | Why (measured in this run) | Knob |
|---|---|---|---|
| 1 | **SM_Airship gets its own ink atlas in UV2 `R3Ink`**. UV0 stays Talal's UVs, which his comic mask, the fallback material and verify_fbx's UV0 compare use. | His UVs give 2.6 cm texels. His bevel strips (2-3 cm) fall between texel centres, so crate and deck-prop edges came out dashed at deck range (`deck_eye`, first two previews). On the new atlas every ink line is an island border, and bevel strips narrower than 4.5 cm whose long edge is a feature edge go to the side block. Density: 36.4 texels/m (his: 38.9). | `r3_prep --hull-uv atlas\|talal --min-w-hull` |
| 2 | **Signed distance**: R = (d + 2 cm) / 14 cm. Margins beyond a feature edge are negative. | With a plain distance and Blender's EXTEND margin, the value at an island border never drops below half a texel (1.3 cm on the hull, 0.7 cm on details). Lines thinner than that vanished: the first `stairs_close` preview lost almost every line. Now bilinear filtering crosses zero exactly on the edge. | `r3_bake --dneg`; MI `InkDistNeg` 2 |
| 3 | **numpy rasteriser** (`r3_raster.py`) instead of the Cycles position / face-id bake. | Change 2 needs positions extrapolated past the triangle; Cycles' EXTEND only copies border texels. It is also deterministic and needs no GPU. | `r3_bake --margin-px 8` |
| 4 | **A texel sees its own piece's feature edges within 12 cm**, plus a behind-the-face test, instead of the 1-ring. | The 1-ring rule gave different distances on the two sides of a UV seam: 11-18 % of the hull's seam samples and 3-8 % of the props' flipped between ink and no ink (first full bake). Now 0.0-0.1 % on the hull and at most 1.1 % elsewhere (6 cm half width only, 13.2). | `r3_bake --lists piece\|ring --behind` |
| 5 | **Every feature edge is an island border** on all three atlases (seams = feature edges + smart-project borders, angle-based unwrap). | A crease inside an island has a V-shaped distance that bilinear filtering cannot reach zero on, so it is dashed up close. 15,094 (H), 8,529 (M) and 3,707 (hull) feature edges lay inside smart-project islands. Cutting them cost no density. | `r3_prep --seams features\|smart` |
| 6 | **Plate sides** (the plan's solid INK block) hold d = 1.5 cm: they show their colour up close and ink once a line is wider than 1.5 cm (beyond about 15 m). | Solid ink made heavy black bands at 5 m (`fan_close_L`, first preview). The approved renders show the side's colour with a thin edge line. | `r3_bake --side-d` (0 = solid ink) |
| 7 | **Hull crease 42°** (was 35°). | 42° is the approved renders' Freestyle crease angle (138°). At 35° the lumpy keel block drew more scribbles than the approved renders. | `--crease-deg` (prep and bake) |
| 8 | **Props page** `T_AirshipR3_PropsInk` (2048, the props atlas: helm, cannon, turret). | The lead's call: props and turrets are recoloured like the approved previews (palette slots 17-19). The four cannons share one set of UVs (checked: identical to L1's). | `r3_prep --props-palette`, MI choice in Unreal |

### 13.2 Pages

| Page | Texture | UV | Atlas area | Texels/m | Packing | UV overlaps | Loops out of 0..1 / in the reserved band | Feature edges | Ink share (d < 1 cm) |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| hull | `T_AirshipR3_HullInk` 4096 | SM_Airship UV2 `R3Ink` | 4,684 m² | 36.4 | 37.6 % | 0 | 0 / 0 | 32,037 | 4.2 % |
| H | `T_AirshipR3_DetailInk_H` 4096 | HullDetail UV0 | 783 m² | 70.1 (Z7 105.1) | 32.2 % | 0 | 0 / 0 | 68,137 | 15.0 % |
| M | `T_AirshipR3_DetailInk_M` 4096 | Moving UV0 | 429 m² | 118.7 (Z7 178.0) | 39.7 % | 0 | 0 / 0 | 35,200 | 11.2 % |
| P | `T_AirshipR3_PropsInk` 2048 | props atlas UV0 (unchanged) | - | 230.9 | - | 0 | 0 / 0 | 7,849 | 17.6 % |
| (Talal's UV0) | - | SM_Airship UV0 | - | 38.9 | - | 0 | 0 / 0 | - | - |

Overlaps are counted by rasterising every page at its own size: texels covered by two different UV islands.
Out-of-range and reserved-band loops are counted per source object (`checks/prep_report.json` -> `uv_checks`).
Texel density per source object (`density_by_source`): every Hull-bone source sits at 70.06 (Z7 sources at 105.09)
and every moving source at 118.66, with p5-p95 within 0.2 texels/m.

Face kinds (rivets, hidden, thin, plate sides map to the reserved blocks; atlas faces get texels):

| | Atlas | Rivet | Hidden | Thin | Plate side |
|---|---:|---:|---:|---:|---:|
| HullDetail | 39,730 (783 m²) | 47,142 | 15,488 (570 m²) | 19,090 | 16,158 |
| Moving | 20,102 (429 m²) | 22,689 | 5,999 (255 m²) | 10,950 | 11,465 |
| SM_Airship | 28,277 (4,677 m²) | 0 | 0 (not tested on the hull) | 7,744 (45 m²) | 1,922 |

The hull's narrow faces whose long edges are smooth keep atlas space: 5,734 copper pipe facets and 3,841 keel-block
faces. Their ring and crease lines need it.

Seam continuity: R is sampled at three points of every UV seam edge between textured faces, on both sides. The same 3D
point should give the same distance.

| Page | Seam edges | Difference p50 / p95 / p99 (cm) | Ink on one side only, at half widths 0.5 / 2 / 6 cm |
|---|---:|---|---|
| hull | 22,884 | 0.03 / 0.51 / 1.08 | 0.09 % / 0.06 % / 0.009 % |
| H | 25,562 | 0.00 / 0.15 / 3.00 | 0 / 0 / 0.12 % |
| M | 10,763 | 0.00 / 0.25 / 2.91 | 0 / 0 / 1.08 % |
| P | 8,430 | 0.00 / 0.11 / 1.24 | 0 / 0.01 % / 0.90 % |

The remaining 6 cm cases come from the behind-the-face test on curved parts (two faces with different normals judge
a far edge differently). No render shows a stripe.

Rivets: 7,759 heads. 7,211 are dotted (H 4,682, M 1,819, hull 710). 540 (7 %) sit on a thin or hidden face, which
has no texels, so they get no dot and vanish at LOD1. 8 found no surface within 8 cm.

LODs (from the export blend):
* SK_Airship: 238,430 / 186,492 / 164,688 triangles.
* SM_AirshipR3_HullDetail: 258,238 / 170,538 / 119,664 triangles.

### 13.3 Checks

* **UV:** 0 overlap texels on every page; 0 loops out of range; 0 atlas loops in the reserved band. Per source:
  `checks/prep_report.json`.
* **Seams:** table above; no stripes in any render.
* **Rivets as dots:** see above. The LOD1 renders (`fan_close_L_baked_lod1.jpg`, `close_flank_baked_lod1.jpg`,
  `pilot_45_baked_lod1.jpg`) have no rivet geometry, and their dots read the same as LOD0's heads.
* **Colours by role** (`export_colour_check.json`): 8 shots, flat render (base colour as emission) against the palette
  on pixels away from ink, dots and edges.
  * Our render: largest error 0.85 / 255 over all 19 slots seen; 0 pixels on a spare slot.
  * The approved toon renders at the same pixels: the share within 6/255 of one of the three cel bands of the same
    palette colour is 80 % rust, 89 % dark metal, 93 % deck, 73 % yellow, 79 % orange, 90 % rust dark, 90 % wood,
    78 % keel block, 63 % hull paint.
  * It is lower for thin roles: brass 43 %, the turret gun 43 %, where Freestyle ink covers them.
  * The median ratio to the palette is about 1.0 in their lit band and about 0.70 in the mid band, so the in-game
    palette is the approved palette.
* **Base-edit areas** (`export_bake.json` -> `base_edits`):
  * R is computed on the edited mesh. The ink share within 0.3 m of the removed parts is 1.5 % (fan back L),
    0.8 % (fan back R) and 5.6 % (ChainAft bars); within 1.5 m it is 4.5 / 4.6 / 5.8 %. The whole hull is 4.2 %, so no
    extra lines.
  * Talal's comic mask (B, its own texture, ComicAmount 0) still has 39-44 % ink near them: the strokes the removed
    parts cast. It is only visible if someone raises ComicAmount, and the local re-bake (section 3 step 6) is open.
  * Renders of those places: `fan_close_L`, `talal_back`, `transom_rear`, `chain_aft`.
* **Determinism:**
  * Prep runs 4 and 5 gave identical UVs (md5) on 38 of 39 export objects. SM_Airship changed on purpose: the hull
    thin rule.
  * The H, M and P textures are byte-identical across bake runs 4, 5 and 6.
  * The final hull page, baked again into `textures_det`: SAME.
* **Protected files:** same md5 at the start and the end of every run.
  * StylizedAirship.blend and AirshipRig_src.blend: 4cb832de...
  * AirshipRig.blend: 50f895b0...
  * AirshipRig_detail.blend: 31317912...
  * AirshipProps.blend: b253e788...
  * AirshipRig_detail_full.blend: 1f2b3e05... (read only).

### 13.4 The look (all renders looked at)

`media/export/baked_sheet.jpg` (approved toon left, baked right: q34_fp, side, pilot_45, talal_back, stairs_close,
fan_close_L, keel_low, deck_eye) and `baked_crops.jpg` (1:1 crops). Also: `below`, `transom_rear`, `chain_aft`, `q34_rs`,
`pilot_45q` `_baked.jpg`, and the LOD1 renders. The material mimics the planned M_AirshipR3: palette by UV1, signed
distance lines of 2.2 px near to 1.2 px far, dots, Principled at roughness 0.9, the toon previews' sun plus sky, Standard
view.

**It matches** the approved look in:
* the colours by role (yellow, ochre, orange, rust, dark, machinery, steel, copper, brass, wood), the keel block rust
  and the props' wood and dark metal;
* thin, crisp navy outlines on plates, frames, bays, straps, stair treads, posts and crates, from the 4 m close-ups to
  the 45 m chase view;
* rivets as dots, and LOD1's dots;
* the rust pods, the fans' collar, cuffs and tip caps, and the steel hand rails.

**It still differs** in four ways:
1. **Silhouettes:** there are no heavy outlines round pipes, tube rails, hand rails, the fan rims and anything seen
   edge-on (the known gap, question 3). The approved renders' 2.4 px silhouettes are a screen-space effect.
2. **Lighting:** the lit material turns yellow faces in shadow olive under the blue sky ambient (`pilot_45` transom).
   The toon renders use neutral bands. Unreal's sky light decides this, not the bake. **Fixed in v2 (section 15.2):**
   the look knobs keep the shade golden, in StartupMap too.
3. **Thin pieces** show plain colour without lines: conduits, small pipes, and hull pipe facets with a crease along
   them.
4. **Plate sides** change from colour to ink between about 10 and 20 m (side block, 13.1 point 6).

### 13.5 Time and memory

| Step | Time | Notes |
|---|---|---|
| prep | 40 s | |
| bake | 5.6 min, CPU only | hull 81 s, H 158 s, M 64 s, P 30 s; the rasteriser is about 75 % of it; peak about 3.5 GB |
| preview | about 1 s per shot | EEVEE on the GPU |
| checks | 14 s | |

### 13.6 Outputs

`rig/detail/r3export/`:
* `AirshipR3_export.blend` (172 MB; never edit it by hand, `r3_prep.py` rebuilds it). Its objects:
  * Armature;
  * SM_Airship (UV0 Talal's, UV1 `R3Palette`, UV2 `R3Ink`; face attributes `r3_pal`, `r3_cap`, `r3_kind`);
  * 30 props (UV0, UV1);
  * `SM_AirshipR3Detail_Moving` and `SM_AirshipR3_HullDetail`, each with `_LOD1` and `_LOD2` (UV0 atlas, UV1 palette,
    `r3_src`, rigid skin kept);
  * `SM_AirshipTurret_Base` / `_Gun` (collection `R3_Turrets`, the frames of AirshipProps.blend, UV0 props atlas, UV1
    palette).
* `manifest.json`: palette, objects with bounds in UE cm, UV md5s, pages, LODs.
* `manifest_arrays.npz`: per-vertex bones, per-face palette, the removed base-edit triangles.
* `textures/T_AirshipR3_HullInk.png` (md5 4041edf8...), `T_AirshipR3_DetailInk_H.png` (e40ea64a...),
  `T_AirshipR3_DetailInk_M.png` (7528f11f...), `T_AirshipR3_PropsInk.png` (5a0f211e...). All 8-bit RGB, linear.
* `checks/`: `prep_report.json`, `r3_bake_report.json` (+ `_run4`, `_run5`, `_textures_det` for the determinism
  checks), `colour_check.json`, `base_edit_check.json`, `preview/` (flat and index passes).

`Docs/Airship/round3/`: `export_bake.json` (summary), `export_colour_check.json`, `media/export/*_baked*.jpg`,
`baked_sheet.jpg`, `baked_crops.jpg`.

Logs: `_AirshipWork_logs/r3export/`.

### 13.7 For the export step (next agent)

* **`rig_export.py --r3`** exports from `AirshipR3_export.blend`: SM_Airship, the 30 props and
  `SM_AirshipR3Detail_Moving`, swapped for `_LOD1` / `_LOD2` with `--lod`. Keep all UV layers. SM_Airship has three,
  so the SK gets three UV channels. **`verify_fbx --r3`** must accept 2 or 3 UV layers, check UV1 as integers per
  face, and compare UV0 with Talal's.
* **`r3_export_static.py`** exports `SM_AirshipR3_HullDetail` (+ LODs) without the armature.
* **Turrets:** `export_turret.py` reads AirshipProps.blend (one UV layer). Round 3 exports `SM_AirshipTurret_Base` /
  `_Gun` from the export blend instead, in the same frames and with UV1. Slot -> `MI_AirshipR3_Props`.
* **`as_91`** imports four ink textures (BC7, sRGB off, clamp) plus `T_AirshipR3_HullComicMask`. It builds the decode
  `d = R * (InkDistMax + InkDistNeg) - InkDistNeg` (12 / 2 cm) and the `InkOnUV2` switch for the hull MI. Palette
  defaults come from `manifest.json`; slots 17-19 are the props.
* Copy the PNGs to `SourceArt/Airship/textures/r3/` before the UE scripts run (section 8 has the commands).

### 13.8 Open

1. Talal's comic mask is not re-baked at the three base edits (section 3 step 6). It is off by default (ComicAmount 0).
2. Silhouette lines (question 3).
3. 540 rivets sit on thin or hidden faces and have no dot at LOD1.
4. H reaches 70 texels/m, not the 80 target. It is enough for crisp lines (they are signed at borders), but plates
   under about 2 cm go to the side block.
5. Not proven without the editor:
   * BC7 on the signed distance: 8-bit steps of 0.55 mm, plus BC7's block error.
   * Mip levels past the 8 px margin (beyond mip 3, neighbouring islands blend in and far lines thicken a little).
   * Unreal's lighting and tonemapper.
6. The keel block's plates over the rust block read only by their outlines (FULL.md 5a; unchanged).

Commands (this run): section 8. Each step is one command and re-runnable:
* `r3_prep.py`;
* `r3_bake.py`, then `r3_bake.py -- --pages hull --out $X/textures_det --compare $X/checks/r3_bake_report.json` for
  determinism;
* `r3_preview.py` (`--variants lit`, `flat,idx`, `--lod 1`);
* `r3_checks.py`;
* `r3_preview_sheet.py --crops`.

## 14. Export run (2026-11-28): FBX files, offline checks, Unreal scripts

The detailed ship is exported as FBX files and checked without an editor. The Unreal scripts are written but not run
(no editor in this run). Blender ran only headless through `blender_capped.sh`; no Blender MCP and no Unreal editor were
used. The run order for the editor is in `EDITOR_STAGE_R3.md`.

### 14.1 The files

In `rig/detail/r3export/fbx/`, staged byte for byte into `SourceArt/Airship/r3/` (the Unreal scripts read these):

| File | What | Triangles | Meshes | Materials (slot order) | UV channels |
|---|---|---:|---|---|---|
| `SK_Airship.fbx` | SM_Airship (base edits applied) + 30 props + `SM_AirshipR3Detail_Moving`, skinned, the `Armature` of round 2 | 238,430 | 32 | M_Airship, M_AirshipProps, M_AirshipR3_Detail | SM_Airship 3 (UVMap = Talal's, R3Palette, R3Ink); the others 2 (UVMap, R3Palette) |
| `SK_Airship_LOD1.fbx` / `_LOD2.fbx` | the same, with `SM_AirshipR3Detail_Moving_LOD1` / `_LOD2` | 186,492 / 164,688 | 32 | the same | the same |
| `SM_AirshipR3_HullDetail.fbx` (+ `_LOD1` / `_LOD2`) | the 12 Hull-bone detail objects, no armature, no skin, vertices in Mesh component space | 258,238 / 170,538 / 119,664 | 1 | M_AirshipR3_Detail | 2 (UVMap = page H, R3Palette) |
| `SM_AirshipTurret_Base.fbx` / `_Gun.fbx` | the turret meshes, the same frames and UV0 as round 2, plus UV1 (slots 18 / 19) | 3,766 / 4,012 | 1 | M_AirshipProps | 2 |

The textures (`textures/r3/`): `T_AirshipR3_HullInk`, `_DetailInk_H`, `_DetailInk_M` (4096), `_PropsInk` (2048) and
`T_AirshipR3_HullComicMask` (round 2's mask, unchanged). `SourceArt/Airship/r3/r3_unreal_inputs.json` holds every staged
file's md5, the triangle counts, slot order, bounds, the 24 palette colours and the ink decode (InkDistMax 12 /
InkDistNeg 2 cm). The Unreal scripts check them before they import anything.

Scripts:
* `rig_export.py --round3 [--lod 1|2]` (new flag): it reads the export blend, picks the 32 meshes by name and asserts
  their order, materials and UV layers. It uses the transforms and FBX settings of round 2. Without the flag it is
  unchanged: a fresh round-2 export equals `rig/export/SK_Airship.fbx` element for element. Only the header, the
  creation time, the uids Blender draws from Python hashes and the output folder in the texture paths differ.
* `r3_export_static.py` (new): writes the HullDetail meshes and the turrets in the conventions of `export_turret.py`.

### 14.2 Offline checks (all pass)

| Check | Tool | Result |
|---|---|---|
| Skeleton = today's SK_Airship (`rig/export/SK_Airship.fbx`): 118 bones plus the `Armature` node, names in file order, parents, local transform properties, global matrices, BindPose matrices, cluster TransformLinks | `r3_fbx_check.py` (low-level reader) | identical for all three SK files: largest difference 0.0 |
| GlobalSettings (axes, units) | same | the same as round 2 |
| Meshes: order (= Unreal's slot order), one material each, slot order M_Airship, M_AirshipProps, M_AirshipR3_Detail | same | ok, all 3 SK files |
| Triangles per file against the manifest | same | 238,430 / 186,492 / 164,688; 258,238 / 170,538 / 119,664 |
| Positions, polygon corners, every UV layer and the corner normals against the export blend objects | same | positions within 2e-6 m, corners identical, UVs identical. 38 corner normals on 11 HullDetail faces of 1.4-2.5 mm² differ by up to 2.3°: Blender's `Mesh.transform` re-encodes custom normals of tiny faces. They cannot be seen. |
| UV1 R3Palette: an integer index, the same on every corner of a face, equal to the manifest | same | ok on every mesh |
| Skin: every vertex 100 % on one bone, the manifest's bone | same | ok (131,182 SK vertices) |
| Props unchanged from round 2 apart from UV1 (positions, corners, UV0) | same | all 30 |
| Turrets: the same frame and UV0 as round 2's turret FBX | same | both |
| Bounds (UE cm) | same | SK -2039 .. 3150, -1196 .. 1190, -617 .. 1090. That is round 2's box plus 9.9 cm at the top (a moving-part detail) and passes as_10's size check. HullDetail = the manifest's |
| SM_Airship = Talal's mesh minus round 2's deck pieces minus the round 3 base edits (islands 1028, 1030, 1088, 1091, 379-384: 156 faces / 504 triangles, guards ok): positions, face corners, UV0, normals; bone rest positions against the contract and the geometry; weights | `verify_fbx.py --r3` | 0 defects (LOD0, LOD1, LOD2) |
| Second reader: Blender's FBX importer; bones against the low-level reader; weights; deformation test (each of the 105 skinned bones rotated alone moves exactly its own vertices, detail vertices included); prop atlas overlap (turrets included) | `verify_import.py --r3` | 0 defects, 0 mismatching vertices (all three LODs) |
| Round trip: the same cameras rendered from the export blend and from a fresh import of the FBX files, with the same material | `r3_preview.py --from-fbx`, `r3_roundtrip_sheet.py` | the flat (lossless) renders match. At most 0.005 % of pixels (stairs_close) differ by more than 32/255: single pixels along the silhouette of the steel hand rail. Lit renders: largest difference 39/255 on 0.0005 % of pixels. LOD1 is the same. `media/export/roundtrip_sheet.jpg`, `export_roundtrip.json` |
| Determinism | two complete runs of `r3_export_all.sh` | all 8 FBX files identical element for element (header and uids aside) |
| Round 2 paths unchanged | `verify_fbx.py` / `verify_import.py` without flags on round 2's `rig/export/SK_Airship.fbx` (outputs to `checks/r2_repro/`) | 0 defects; counts, positions, weights, deformation test and atlas test identical to round 2's own reports |
| Protected files | every script | the same md5 at the start and the end |

### 14.3 What the checks found for Unreal (the scripts handle each)

1. **Half-float UVs.** Unreal stores skeletal-mesh and non-Nanite static-mesh UVs as 16-bit floats unless "Use Full
   Precision UVs" is on. On the 4096 pages that puts a UV up to 1.0 texel off (p99 0.99). With 2-3 cm texels, the
   signed-distance lines would shift by 1-3 cm and break up along seams up close. `as_91`, `as_91b` and `as_91c` turn
   full-precision UVs on for every LOD. The SK also gets it in its stored Interchange pipeline, which a re-import
   applies. Nanite keeps 14-bit UV mantissas, which is enough.
2. **Vertex welding.** Unreal's builders merge corners of one vertex whose normals match and whose UVs all lie within
   1/1024. SM_Airship has 240 such corner pairs on its ink atlas: two islands packed 4 px apart along a seam. 125 of
   them are more than a texel apart, up to 3.96 texels. On the SK, `ThresholdUV` is a build setting, and `as_91` sets
   it to 1/65536 (only 6 pairs closer than that remain, all under 0.06 texel). On the static mesh the threshold is
   fixed at 1/1024: HullDetail has 9 such pairs, all under 0.37 texel, so they are harmless.
3. **LOD screen sizes.** UE 5.8 keeps a skeletal mesh's LOD infos in `SourceModels`, an array of non-copyable structs
   that Python cannot get or set as a property. `as_91` sets the two screen sizes through `ToolsetLibrary`'s JSON. It
   writes only the ScreenSize fields and checks that nothing else in the source models changed. If that is refused,
   the line is a WARN with the two numbers to type into the SK editor (LOD1 1.93, LOD2 0.72 for a 29.8 m bounds
   radius). Static meshes have `SetLodScreenSizes`, which forces the sizes to decrease from LOD0. So LOD0 is set above
   LOD1: with 1.0, HullDetail's LOD1 (1.75 = 30 m) would have been clamped to 1.0 (47 m).
4. **Parent socket.** `USCS_Node::AttachToName` has no editor flags, so no Python route (Blueprint API, subobject
   data subsystem, ToolsetLibrary) can set it. The HullDetail component is attached to `Mesh` with no socket. The Hull
   bone rests at the component origin with an identity rotation (as_91b checks this) and is kinematic, so the result
   is the same. Setting "Parent Socket: Hull" by hand is optional.

Also seen:
* After the stairs, `as_58_verify_round2.py`'s PA section reports the new boxes: 159 instead of 143, and rotated ramps
  where it wants axis-aligned boxes.
* `as_58`'s slot and turret-material checks expect round 2's materials.
* `as_56` would re-import round 2's FBX, so do not run it again after round 3.
* `as_11` rebuilds PA_Airship without the stair boxes, so run `as_92` again after it.

### 14.4 Budget (from the FBX files)

* **SK LOD0:** 238,430 triangles. Estimated render vertices: SM_Airship 106.5k plus Moving 188.4k, plus the props.
  Round 2 had 126.8k in all.
* **SK LOD1 / LOD2:** 186,492 / 164,688 triangles. The Moving object has 114.7k / 76.4k render vertices.
* **HullDetail:** 258,238 triangles, about 344k render vertices, drawn by Nanite. The fallback LOD1 / LOD2 have
  170,538 / 119,664 triangles.
* **Draw sections per ship:** the SK has 3 (it was 2) and HullDetail adds 1.

### 14.5 The Unreal scripts (written, not run)

| Plan (section 6) | As written | What |
|---|---|---|
| as_90 backup | in every script (`as_9x_r3lib.r3_backup`) | `.uasset` / `.uexp` / `.ubulk` copies + sha256 to `Saved/Airship/backup_r3/<stamp>_<script>/`; refuses assets with unsaved changes |
| as_91 textures + material | `as_90_r3_textures_material.py` | 5 textures (BC7 / Masks, linear, clamp); `M_AirshipR3` (Custom palette node over 24 vector parameters, signed-distance ink line with pixel width from PixelDepth / view, dots, comic mask switch); `MI_AirshipR3_Look` (the one place for the 24 colours and the ink knobs) and its children `_Hull` (UV2, two-sided), `_Moving`, `_HullDetail`, `_Props` |
| as_92 SK re-import | `as_91_r3_reimport.py` | the re-import over SK_Airship (Interchange stored pipeline, or FbxFactory with SKEL_Airship), with skeleton, sockets and PA_Airship kept and checked; LOD1/2 import; full-precision UVs, ThresholdUV, screen sizes; slots by name -> MIs |
| as_93 static mesh + as_94 component | `as_91b_r3_hull_detail.py` | `SM_AirshipR3_HullDetail` (Nanite, LOD1/2, MI, bounds check) and BP_AirshipPawn's `HullDetail` component under `Mesh` (NoCollision) |
| (13.7 turrets) | `as_91c_r3_turrets.py` | `as_53_turret_import.py` with checked text patches: the r3 FBX, `MI_AirshipR3_Props`; plus full-precision UVs |
| as_95 stair boxes | `as_92_r3_pa_stairs.py` | 16 boxes on PA_Airship's Hull body. They are idempotent and every corner is checked against the json within 0.5 cm. The json's corners were checked offline against Unreal's FRotator convention (0.1 cm) |
| as_96 verify | `as_93_r3_verify.py` | read-only: everything above, plus Talal's and round 2's assets against the clone's HEAD |

Every script refuses to run during PIE and saves only its own assets, by explicit path (never a map). It writes
`Saved/Airship/<script>.json` and ends with a `RESULT:` line.

### 14.6 Commands

```
SourceArt/Airship/scripts/r3_export_all.sh        # FBX + checks + round trip + staging, about 3 minutes
#   = rig_export.py -- --round3 [--lod 1|2]; r3_export_static.py; rig_export.py -- --out .../r2_repro/... (round 2);
#     r3_fbx_check.py -- --r2-repro ...; verify_fbx.py -- --r3 (per LOD, with rig/checks/verify/Talal_copy.blend);
#     verify_import.py -- --r3 (per LOD); r3_preview.py --tag blendref / --from-fbx ... --tag fbx; r3_roundtrip_sheet.py;
#     r3_unreal_inputs.py (staging)
```
Logs: `_AirshipWork_logs/r3fbx/`.

### 14.7 Open

1. Nothing has run in Unreal yet:
   * the Interchange re-import combined with the LOD import;
   * the screen-size JSON route;
   * BC7 on the signed distance;
   * Nanite with M_AirshipR3;
   * Unreal's lighting.
   `EDITOR_STAGE_R3.md` lists what each step must print and what to capture.
2. Silhouette lines on round parts are still missing (question 3).
3. Talal's comic mask is not re-baked at the base edits. It is off by default (ComicAmount 0).
4. 540 rivets have no dot at LOD1 (13.8).

## 15. Review fixes (2026-11-28)

A review of the export run (sections 13-14) raised 2 must and 9 should findings, plus nits. Each one was checked
before it was fixed: against the UE 5.8 engine source in `/mnt/new_partition/5.8/Engine`, the `.uasset` files, or a
measurement. No Unreal editor and no Blender MCP were used; Blender ran only headless through `blender_capped.sh`. The
FBX files are unchanged (same md5). One texture changed: the hull page, G channel only.

### 15.1 Verdicts

| # | Finding (severity) | Verdict and evidence | Fix |
|---|---|---|---|
| 1 | StartupMap's light turns the yellow green and the rust grey; captures only in L_AirshipTest (must) | **Real.** StartupMap.umap has the V2.1 moon (125,160,255) 2.24 lux and the sky light 0.70 x (73,203,255) on `/Engine/MapTemplates/Sky/DaylightAmbientCubemap` (the same values as the icelook preset; the cubemap name read from the .umap strings). Talal's project's verified UE 5.8 display model (Filmic + the V2.1 grade + LUT, EV100 0.5) puts the shaded hull wall at **sRGB (0,56,39)** and the rust at (1,25,42): teal and navy, not yellow and rust. Worst-case colour error against the approved renders, 14 main colours, 3 face kinds, sky radiance 0.3-1.0: v1 **65 dE**, the review's candidate (palette x 0.8 emissive) 21, v2 **13** (`export_shade_calib.json`). | v2 look knobs (15.2); EDITOR_STAGE 4.1.8 (StartupMap check and tuning) and section 5 (main captures in StartupMap) |
| 2 | shaded faces olive in neutral light; lit yellow may wash to cream (should) | **Real.** At the review's transom pixels in `chase65_back`: approved (208,173,100), v1 (150,128,78) (the review's number). The display model also shows the cream risk: under StartupMap's grade hull_paint at full brightness displays (223,208,153), because highlights get saturation 0.72 and gain 1.45 from luminance 0.12. | the same knobs: v2 (217,176,70) in neutral light, (217,198,106) in StartupMap; `LiftSat` 1.3 compensates the grade's desaturation |
| 3 | no silhouettes on round parts (should) | **Real** (the known gap). | `HasSilhouette` switch, **off by default**, with the project's CN_InkSilhouette maths plus a `SilMinSlope` gate (15.3); shown to Talal (`silhouette_option.jpg`) |
| 4 | ink shimmer at 65-120 m (should) | **Plausible**; it needs TSR to judge. Not re-measured. The trilinear filtering (finding 8) and the v2 far line remove two sources of popping. | PIE shimmer test with knobs `InkPxFar`, `InkOpacityFar` + `InkFadeStart/End` (EDITOR_STAGE 4.1.3) |
| 5 | props and turrets recoloured without Talal's yes (should) | **Real** (process): his 11:00 answers covered the keel, fan blades and rails only. | question 15.6 with `props_option.jpg`; the recolour stays the lead's default; `AS91_KEEP_PROPS_MATERIAL` / `AS91C_KEEP_PROPS_MATERIAL` revert it and as_93 now accepts that |
| 6 | as_91c re-imports round 2's turret FBX (must) | **Real.** Both `SM_AirshipTurret_{Base,Gun}.uasset` hold `InterchangeAssetImportData` with `"RelativeFilename" : "../../../../../SourceArt/Airship/SM_AirshipTurret_*.fbx"`, and as_53's Interchange branch re-imports the stored source. | as_91c points each turret's source at `SourceArt/Airship/r3/<name>.fbx` (scripted_add_filename, read back), sets full-precision UVs in the stored pipeline, and FAILs unless the source is still r3 after as_53 |
| 7 | far ships get a navy tint (should) | **Real.** At 1920 px, FOV 85: a texel with no line within 12 cm (R = 1) got 17 % ink at 150 m and 45 % at 200 m. In the renders the pass-1 line darkens **83 %** of a 200 m ship's pixels by more than 20/255 (mean 33/255), 86 % at 300 m, 1 % at 120 m (`export_review_renders.json`, `far_ink_fix.jpg`). | v2 `R3InkLine`: the band `w +- px/2` ends at InkDistMax by shrinking the core, not the anti-aliasing; plus a saturated-texel guard and an optional far fade (15.3) |
| 8 | ink textures sample the nearest mip (should) | **Real.** `BaseDeviceProfiles.ini:184` World group `MinMagFilter=aniso, MipFilter=point` -> `TextureLODSettings.cpp:127-137` AnisotropicPoint -> `VulkanState.cpp` `VK_SAMPLER_MIPMAP_MODE_NEAREST`; the clone's Config has no TextureLODGroups override. A per-texture `Filter` overrides the group (`GetSamplerFilter`, `TextureLODSettings.cpp:505-529`). | `filter = TF_TRILINEAR` on the four ink pages (`AS90_INK_FILTER`), or a Project01 group with `MipFilter=linear` (EDITOR_STAGE 3); as_93 checks it |
| 9 | HasComic on for the hull MI with ComicAmount 0 (should) | **Real.** | off by default (as_90, as_93) |
| 10 | screen-size JSON route only WARNs on side effects (should) | **Real** (`r3_sk_set_screen_sizes` folded `same_rest` into the WARN). | it returns the changed SourceModels paths; as_91 FAILs and saves nothing; `AS91_SKIP_SCREEN_SIZES` for the by-hand route |
| 11 | nothing checks the SK's 3 UV channels (should) | **Real.** `SkeletalMesh.h` and `SkeletalMeshEditorSubsystem.h` have no UV-channel query; the old `hasattr` was always False. GeometryScript has `GetNumUVSets` (`MeshQueryFunctions.h:257`). | `r3_uv_sets()`; as_91 and as_93 FAIL unless every SK LOD has 3 |
| nit | hull rivet dots blur into a halo | **Real** on the hull page: at 36.4 texels/m the anti-alias of half a texel is 1.37 cm, so a 1.8 cm dot reached 3.2 cm. | `r3_bake --dot-r-hull 0.012`: hull page re-baked, R and B byte-identical, G changed (texels over 0.5: 1,582 -> 702, outer radius 3.2 -> 2.6 cm); determinism SAME |
| nit | keel-block scribbles | Not a regression (the approved render has similar ones). | not changed; the knob is a per-class crease angle in r3_prep / r3_bake if Talal asks |
| nit | ship ink darker and harder than the world's at 100 m+ | A note: #1C2230 is Talal's comic ink; the world's V2.1 ink is #003E77 and fades. | the v2 far fade knobs exist (default off); EDITOR_STAGE 5 asks to compare in StartupMap |
| nit | Nanite fallback is the auto-reduced cut | **Real** (`StaticMeshBuilder.cpp:201-205`; `EngineTypes.h` FallbackTarget Auto, FallbackRelativeError 1.0). | as_91b sets `PercentTriangles 1.0`; as_93 checks it |
| nit | the skeleton check reads SKEL_Airship's reference pose, not the mesh's | **Real** (as_56's lesson). | `r3_mesh_ref_bones()` (SkeletonModifier): as_91 compares before / after, as_93 against bones_ue.csv |
| nit | quads exported untriangulated | **Measured, not changed** (15.4). | none; a fix path is given |
| nit | do-not-run list misses as_61, as_53, as_02; as_93 rejects the keep knobs | **Real.** | EDITOR_STAGE 1.4; as_91 / as_91c record the knob, as_93 reads it |
| nit | budget | **Verified** (texture memory 80 MiB; LOD2 floor; runtime LOD bounds from the PA; redo3 `r.DynamicGlobalIlluminationMethod=1` uncommitted vs the clone's 0). | EDITOR_STAGE 1.5 (baseline notes) |

### 15.2 The look knobs (findings 1 and 2)

M_AirshipR3 v2: `BaseColor = c x LitMix`; `Emissive = EyeAdaptationInverse(max(Sat(c, LiftSat), 0) x ShadeLift, LiftLock)`
with `Sat(c, s) = lum + (c - lum) s` and `c` the palette colour after dots and ink (so the ink stays dark). With
LiftLock 1 the emissive term is divided by the level's exposure, so `ShadeLift` means the same on screen in any level.
`LitMix 1, ShadeLift 0` is the v1 look.

`r3_shade_calib.py` chose the defaults on a grid, using `r3_look.py`: the display model, StartupMap's lights, and three
face kinds (a wall in shade, a wall facing the moon, a deck top). The score is the worst case over the unknown sky
radiance (DaylightAmbientCubemap's source pixels are not readable offline: 0.3, 0.6, 1.0).

| LitMix | best ShadeLift / LiftSat | worst mean dE |
|---|---|---:|
| 0 | 0.60 / 1.1 | 12.5 |
| 0.25 | 0.55 / 1.2 | 12.6 |
| **0.5 (default)** | **0.55 / 1.3** | **13.4** |
| 0.75 | 0.55 / 1.4 | 14.4 |
| 1.0 | 0.50 / 1.5 | 16.1 |
| v1 (1.0, 0) | - | 65.1 |

The rule picked the best LitMix of at least 0.5 that is within 1.5 dE of the overall best: it keeps half of the level's
light, so moon shadows and the sky's shading still show. Predicted in StartupMap (sky 0.6, sRGB): hull wall in shade
(217,198,105) against the approved (208,173,97); facing the moon (219,204,126) against (243,203,115); rust in shade
(162,82,42) against (160,105,82); deck top (186,186,184) against (191,181,166).

What it cannot do:
* The moon is weak (2.24 lux) and blue, so the shading contrast in StartupMap stays small (about 1.05 instead of the
  approved bands' 1.43).
* One global saturation cannot undo the grade's hue shifts: yellow leans a little lemon and rust a little orange.
* LitMix 0.25 keeps the deck beige rather than light grey (178,175,167) at almost the same score.

The editor stage tunes the last part in StartupMap (EDITOR_STAGE 4.1.8).

Renders (`r3_preview --light game`): the scene is rendered scene-linear with StartupMap's moon (its real direction: it
shines from the bow, so the stern is in shadow in the chase view) and sky hemispheres. UE's Filmic + V2.1 grade is then
applied through the display model. The preview light renders (Standard view) use the same material. `game_light_fix.jpg`
(v1 teal / v2 yellow and rust), `shade_fix.jpg` (neutral light: the khaki stern is golden), `baked_sheet.jpg` (three
columns). Not modelled: fog, bloom, Lumen and the real cubemap.

### 15.3 The ink line, the silhouette option, the filtering

* **R3InkLine v2** (as_90 and the r3_preview mimic): `aa = px/2; w = min(max(0.5 inkpx px, InkMinHalfWidth), InkDistMax
  - aa)`. The band ends at InkDistMax, so a texel with no line within 12 cm never gets ink. Beyond about 115 m the line's
  core thins and the line fades out with its anti-aliasing kept. The review's variant kept the core and shrank the
  anti-aliasing to a hard 0.6 cm edge, which would add aliasing where finding 4 already sees crawl. A texel at
  R >= 0.996 draws no line (a guard against BC7 noise). `InkFadeStart / InkFadeEnd / InkOpacityFar` are there for the
  PIE shimmer test (default no fade). Below 115 m nothing changes.
* **Silhouette** (`HasSilhouette`, off): the hex materials' CN_InkSilhouette (`(N.V)^2 / fwidth`, vertex normal,
  Soft 0, FacetSil 0), `SilWidthPx` 2.4 (the approved Freestyle width), faded out from 60 to 120 m.
  * The first mimic drew a thick jagged band along the main deck's rim at eye height. A gently curved surface seen
    edge-on keeps N.V near 0 over many pixels.
  * `SilMinSlope` 0.02 (no line where N.V changes less than that per pixel) removes it and keeps the hand rails, the
    barrels and the fan rims (`silhouette_option.jpg`, `silhouette_option_crops.jpg`).
  * The mimic computes the derivatives between pixels of the same smooth surface, as a GPU quad would. TSR will soften
    the 1-px stepping the mimic shows on the thin rail.
  * It uses no WorldPosition, so the Nanite PDO problem of `fix_nanite_ink.py` does not apply.
* **Offline compile:** `r3_hlsl_check.py` wraps the five Custom node bodies of as_90 as UE does and compiles them with
  the engine's DXC (ps_6_0 and SPIR-V, HLSL 2018 and 2021): **all OK** (`export_hlsl_check.json`). It caught `line` (an
  HLSL keyword) in the first v2 draft.
* **Filtering:** `TF_TRILINEAR` on the four ink pages. It loses anisotropy at grazing angles; the Project01 group in
  EDITOR_STAGE 3 keeps both. Compare them in the chase shot.

### 15.4 Triangulation (review nit), measured

`r3_tri_check.py` (`export_tri_check.json`). The bake rasterises Blender's loop triangles: quads are split 0-2 unless
concave. The FBX keeps quads and n-gons, and Unreal triangulates them with the FBX SDK (closed source; legacy and
Interchange alike, `FbxStaticMeshImport.cpp:483`, Interchange `FbxMesh.cpp:662`). The worst case for a quad is the other
diagonal. Because every ink line lies on a polygon edge, where both splits agree, the shift that matters is the one a
half line-width inside the quad.

| Page | quads | shift 0.5 cm from an edge (5 m view): p99.9 / max | 2 cm from an edge (20 m) | 4 cm (40-70 m) |
|---|---:|---|---|---|
| hull (SM_Airship R3Ink) | 17,145 | 0.75 / 1.78 px (371 quads over 1/4 px) | 0.56 / 0.87 px | 0.27 / 0.33 px |
| HullDetail | 37,398 | 0.35 / 1.01 px | 0.26 / 0.49 px | 0.10 / 0.19 px |
| Moving | 19,136 | 0.21 / 0.23 px | 0.21 / 0.23 px | 0.10 / 0.12 px |

* Inside a quad (away from edges) the hull's shift reaches 6.6 cm, and inside some of Talal's n-gons 21.8 cm. Those
  places are far from any line.
* `use_triangles=True` (the review's suggestion) would not fix this. Blender's FBX exporter triangulates with
  `bmesh.ops.triangulate`, whose default quad method is BEAUTY (`export_fbx_bin.py:2735`), not the loop triangles the
  bake used.
* **Not changed.** If the editor shows wobbly lines on Talal's curved hull up close (EDITOR_STAGE 6), the fix is to
  triangulate SM_Airship from its loop triangles in `rig_export --r3`. `verify_fbx --r3` and `r3_fbx_check` would then
  compare a triangulated reference.

### 15.5 Unreal scripts (still not run)

* **as_90 v2:** look, silhouette, far fade, line, trilinear, HasComic off. It checks the staged look values
  (`r3_unreal_inputs.json` now carries `look` and `bake_knobs`).
* **as_91:** FAILs on screen-size side effects (`AS91_SKIP_SCREEN_SIZES`), checks 3 UV channels per LOD and the mesh
  reference skeleton, and records the keep knob.
* **as_91b:** Nanite fallback PercentTriangles 1.0.
* **as_91c:** re-points the turret sources and checks them; records its keep knob.
* **as_93:** filter, look, HasSilhouette, HasComic off, UV channels, fallback, mesh skeleton, turret sources, keep knobs.

All parse; the name check finds no undefined names; every as_53 patch target still matches once.

### 15.6 Questions for Talal (each a knob; defaults in brackets)

1. **Props and turrets** (`media/export/props_option.jpg`): keep the recolour (wooden carriages and wheels, dark-metal
   barrels and guns, like the approved previews) or Talal's paper look? [Recoloured, the lead's call; one knob reverts
   it.]
2. **Silhouette lines** (`media/export/silhouette_option.jpg`): turn on the outline of round parts (hand rails, barrels,
   fan rims, pipes) like the approved renders? [Off.]
3. **In-game look in StartupMap** (`media/export/game_light_fix.jpg`): the night level's blue light turned the ship
   teal. The v2 look keeps it yellow and rust but flatter (the moon barely shades it). Keep this, or go further toward
   the approved renders' flat cel bands (question 4 of section 11)? [v2 look, tuned in the editor.]

### 15.7 Commands (this run)

```
S=SourceArt/Airship/scripts; B=/mnt/new_partition/UnrealProjects/_AirshipWork_logs/blender_capped.sh
PY=/mnt/new_partition/OldDownloads/blender-4.5.3-linux-x64/4.5/python/bin/python3.11       # Blender's python (numpy)
$PY -I -B $S/r3_shade_calib.py                                         # look defaults -> export_shade_calib.json
BL_MEM_MAX=6G $B --python $S/r3_bake.py -- --pages hull --cpu          # hull page, dots 1.2 cm (+ --out .../textures_det
                                                                       #   --compare .../r3_bake_report.json: SAME)
BL_MEM_MAX=6G $B --python $S/r3_checks.py                              # export_bake.json
python3 -B $S/r3_unreal_inputs.py                                      # staging (FBX unchanged, new hull PNG, look)
python3 -I -B $S/r3_hlsl_check.py                                      # DXC: as_90's Custom nodes (run unpiped)
BL_MEM_MAX=6G $B --python $S/r3_tri_check.py                           # export_tri_check.json
$S/r3_review_renders.sh                                                # every render + r3_review_sheets.py (about 6 min)
```
Logs: `_AirshipWork_logs/r3review/`. The pass-1 renders are in `media/export/pass1/`, the pass-1 textures in
`rig/detail/r3export/textures_pass1/`, the pass-1 bake and colour reports in `checks/pass1/`.

### 15.8 Checks

* Colour check, re-run on 13 shots: flat max error 0.85/255 (as pass 1).
* Hull page re-bake: R and B byte-identical to pass 1, determinism SAME, base-edit ink shares unchanged.
* FBX md5 unchanged; staged inputs re-checked.
* Protected files have the same md5 at the start and the end:
  * StylizedAirship.blend and AirshipRig_src.blend: 4cb832de...
  * AirshipRig.blend: 50f895b0...
  * AirshipRig_detail.blend: 31317912...
  * AirshipProps.blend: b253e788...
  * The full file 1f2b3e05... and the export blend cf3adecb... (both read only).
  * Talal's textures/ and export/: Oct 31.
