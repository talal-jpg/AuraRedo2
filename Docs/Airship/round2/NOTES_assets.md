# Round 2, PR A: editor scripts (assets owner)

Status 2026-11-25: editor stage run in the clone editor; steps 1-11 PASS (as_58: 51 PASS, compile all_ok). Step 12
(as_59 standalone PIE): 44 PASS, 0 FAIL, 0 WARN, 2 INFO, 14 SKIP after three harness fix rounds, no C++ change (section
"as_59 PIE run 2026-11-25" below; results `Saved/Airship/round2_final_sa/`). Written
2026-11-24 without an editor; run in the order below. Every script refuses to change assets while PIE runs, saves only its own assets by explicit path, prints
`PASS / FAIL / WARN / INFO` lines and a last `RESULT:` line, and writes a JSON report to `Saved/Airship/`.
Spec: `SPEC_A.md` sections 1 (D1, D2, D6, D7), 3 and 4.
Step 4b (`as_61_hull_ink.py`, the hull ink fix for risk 7) was written afterwards, also without an editor: not run
yet (dry run against a mock `unreal` only).

Offline checks done here (no editor): every script parses; the PIE harness was run end to end against a mock `unreal`
module (all 24 phases, no script error of its own); `as_51` / `as_54` / `as_58`'s FX checks were run against a fake
Niagara toolset. That covers enum lookup by set-and-read-back, nested dynamic-input paths and re-runs. `as_56`'s three
text patches were applied to the real `as_10_import.py` (each matches once). None of this tests the editor or the C++.

## Run order (editor on the clone, `L_AirshipTest` open, no PIE)

`inbox.sh` = `Docs/Airship/scripts/harness/inbox.sh <id> <script> <timeout>`.

| Step | Script | Needs | Saves |
|---|---|---|---|
| 1 | `as_51_muzzle_once.py` (300 s) | nothing new | `NS_AirshipMuzzle` |
| 2 | `as_52_cannonball_bp.py` (120 s) | round-2 C++ built | `BP_AirshipCannonball` |
| 3 | existing `as_02_textures_material.py` | Blender outputs (repacked atlas) | atlas textures, `M_AirshipProps` |
| 4 | `as_56_reimport_airship.py` (900 s) | `SourceArt/Airship/SK_Airship.fbx` = `rig/export`, `verify_all.sh` run | `SK_Airship`, `SKEL_Airship` (through as_10) |
| 4b | `as_61_hull_ink.py` (300 s) | step 4; `SourceArt/Airship/textures/T_AirshipDrivable_ComicLines.png` (`hull_ink_drivable.py`, headless Blender) | `T_AirshipDrivable_ComicLines`, `M_AirshipDrivable`, `SK_Airship` |
| 5-6 | existing `as_09` (headless Blender), `as_12_reuse.py`, `as_13_cr_eval.py` | step 4 | `CR_Airship` |
| 6b | `as_11a_hull_survey_blender.py` (headless Blender), `as_11b_hull_boxes.py` (plain python3), `as_11_physics_asset.py` (300 s), then `as_13_cr_eval.py` again | steps 4-5 (`part_bounds.json`) | `PA_Airship`, `SK_Airship` (physics asset link) |
| 7 | `as_53_turret_import.py` (300 s) | turret FBX + `turret_dims.json` | `SM_AirshipTurret_Base`, `_Gun` |
| 8 | `as_54_turret_fx.py` (300 s) | nothing new | 3 turret Niagara systems |
| 9 | `as_55_turret_bp.py` (300 s) | C++ `AAirshipTurret`, steps 7-8 | `BP_AirshipTurret` |
| 10 | `as_57_pawn_defaults.py` (120 s) | C++ | `BP_AirshipPawn` only if it overrode a C++ default |
| 11 | `as_58_verify_round2.py` (300 s) | all above | nothing (read only) |
| 12 | `as_59_pie_round2.py` (60 s, then poll) | all above, `part_bounds.json` from step 5 | nothing (PIE, TEMP actors removed) |

Step 4b is new since the editor stage: in an editor where 1-12 already ran, run 4b alone (`inbox.sh 61
Docs/Airship/scripts/ue/as_61_hull_ink.py 300`); it changes only SK_Airship's slot 0 and adds its two assets, so
nothing else needs a re-run. as_10 (and so as_56) keeps the new slot 0 on a later SK re-import.

`as_51`, `as_54` and `as_58` end with a background compile check. It opens the Niagara system editor (compile errors
only show with it open), reads `GetSystemCompileState` + `GetStackIssues` on later editor ticks, closes the editor, and
writes `Saved/Airship/as_51_compile.json` / `as_54_compile.json` / `as_58_compile.json` (`"done": true`, `"all_ok"`)
5-60 s after the call returns. Wait for `as_58_compile.json` `"done": true` before arming `as_59`. Shared code:
`as_51_muzzle_once.py:296` (`as5x_bg_compile`).

## What each script does

### as_51_muzzle_once.py (D1, smoke gone within 1 s)

* Probe (`as51_probe`, `as_51_muzzle_once.py:102`): every emitter's `EmitterUpdateScript/EmitterState` inputs and the
  system's `SystemState`, with the enum identifiers as the toolset returns them, plus the InitializeParticle lifetimes
  and the module lists. Output: `Saved/Airship/as_51_probe.json`, with the same lines printed.
* No hard-coded enum value. `as51_find_enum` (`:147`) takes "Once" from the probed display names. If no probed value
  shows it, it sets each `NewEnumerator<i>` in turn and reads back the display name. When nothing matches, it restores
  the original value and reports FAIL.
* `as51_one_shot` (`:178`): every stack whose own life cycle (Self) does not have Loop Behavior Once gets Loop Behavior
  Once and Loop Duration 0.2 s. Emitters in Life Cycle Mode System are skipped: they follow the system state, which
  gets the same change if it isn't Once.
* `as51_set_lifetimes` (`:219`): Blast_Puffs lifetime 1.2-2.2 s -> 0.5-0.85 s.
* `as51_alpha_fade` (`:239`): Blast_Puffs ScaleColor Scale Alpha (a FloatFromCurve in the Fountain template) becomes
  `1.0 - Particles.NormalizedAge`. The module is added if missing. The expression doesn't use `User.Global Scale`,
  which can't compile in HLSL (as_07).
* Muzzle_Smoke stays at 0.2-0.3 s. Every change is read back. The script doesn't save if anything FAILs.
* Library mode: `AS51_LIB_ONLY = True` before exec defines the functions only. The flag is popped, so a later direct
  run still runs main. Used by `as_06`, `as_54` and `as_58`.

### as_06_muzzle.py (edited)

* The rebuild keeps the fix. `as_06_muzzle.py:28` sets lifetimes `(0.5, 0.85)` (was `(1.2, 2.2)`).
* `:35-40` execs as_51 as a library and calls `as51_one_shot` + `as51_alpha_fade` before the save. The header comment
  says why (`:6-9`).
* `as_07` must still run after `as_06`, as before.

### as_52_cannonball_bp.py (D2)

* Sets these BP_AirshipCannonball class defaults: Radius 50, GravityScale 0.6, SplashRadius 600, SentinelHitRadius 100,
  MaxLifeSeconds 10, BallMaxHealth 30, ImpactFXScale 3.
* BallMesh scale = 2 x Radius / the sphere mesh's measured diameter, so 1.0 for the engine sphere (was 0.56).
* Run it after any `as_03` run, because as_03 writes 28 / 450 / 8 explicitly (`as_03_physmat_cannonball.py:79-81`).
* Refuses to run without the round-2 C++ (BallMaxHealth / GravityScale properties). Never creates the BP.

### as_53_turret_import.py (D6/D7)

* Imports `SourceArt/Airship/SM_AirshipTurret_{Base,Gun}.fbx` into `/Game/Assets/MyShip/Drivable/Turret`.
* Import settings: legacy FbxFactory, static mesh, combine meshes, FBX normals, no collision, Nanite off, no lightmap
  UVs. `transform_vertex_to_absolute` and `bake_pivot_in_vertex` are off, so the pivot stays at the object origin.
* Every slot gets `M_AirshipProps`. Any simple collision is removed.
* Bounds checks against `turret_dims.json` (+-2 cm):
  * `base_bounds_cm` / `gun_bounds_cm` (`{"min": [...], "max": [...]}`, UE cm in the mesh's space) are compared when the
    file has them.
  * Always checked: base bottom at z 0, footprint inside 0.9 x 0.9 m, base top reaching `pivot_height_cm`, gun front vs
    `muzzle_forward_cm`, gun x extent vs `gun_length_cm`, receiver <= 45 cm behind the trunnion.
* Re-imports over its own meshes. Refuses an asset of the same name that isn't a static mesh or came from another FBX.

### as_54_turret_fx.py (D6)

* Copies into `/Game/Assets/MyShip/Drivable/FX`. A copy is made only when missing; an existing copy is edited in place.
  The functions are `as54_*`, and `AS54_LIB_ONLY` enables library mode.
* `NS_AirshipTurretTracer` (copy of `PS_06_Flipbook_Sprites_my`):
  * `as54_tracer_probe` (`as_54_turret_fx.py:89`) walks every module input of every emitter and system script. That
    includes nested dynamic-input chains (`GetDynamicInputChain`) and user parameters.
  * It looks for 7500 (a float, or a number inside an HLSL expression) and sets it to 30000.
  * It prints the speed-like inputs it leaves alone. If no 7500 is found, it WARNs and leaves the copy as it is
    (spec risk 10).
* `NS_AirshipTurretMuzzle` (copy of `NS_MuzzleFlash`):
  * Bullet_Shell_Eject removed, User.Use Bullet Shell 0, User.Global Scale 1.5.
  * `as51_one_shot` applied.
  * Smoke emitter lifetimes (InitializeParticle / SetVariables `Particles.Lifetime`) capped at 0.5 s (Min 0.3 when it
    has to change).
* `NS_AirshipTurretFire` (copy of `NS_Fire`): unchanged. The BP scales it to 0.3.

### as_55_turret_bp.py (D6)

* Creates or reuses `/Game/Assets/MyShip/Drivable/Turret/BP_AirshipTurret` (parent `/Script/Aura.AirshipTurret`). It
  refuses a BP with another parent and never deletes one.
* Meshes: BaseMesh / GunMesh. Placement: GunMesh at (0, 0, PivotHeight), Muzzle at (MuzzleForward, 0, 0).
  PivotHeight / MuzzleForward come from `turret_dims.json` (`pivot_height_cm`, `muzzle_forward_cm`); the C++ 150 / 180
  are kept when the file has none.
* FX: MuzzleFXComponent = NS_AirshipTurretMuzzle, DestroyedFXComponent = NS_AirshipTurretFire at scale 0.3.
* Tracer: TracerSystem = NS_AirshipTurretTracer, TracerDataChannel = `NDC_GunShootHit` (the gun's own channel, never a
  new one).
* DestroyedExplosionFX = NS_FireExplosion.
* HitBox sized from the imported base mesh: half width = footprint half size + 10 (at least 60), half height =
  (PivotHeight + 40) / 2 (at least 95), centre z = half height. With the defaults that is the C++'s (60, 60, 95) at z 95.
* Reads everything back after the compile.

### as_56_reimport_airship.py (D7, SK_Airship reimport)

* Wraps `as_10_import.py` (`AS10_EXISTING = 'reimport'`), with three checked text patches applied in memory. as_10
  itself is not edited.
  1. The import UI gets the existing `SKEL_Airship`. **The spec assumed as_10's reimport keeps the skeleton. It
     doesn't**: with `ImportUI->Skeleton` null, the FBX importer creates a new `<mesh>_Skeleton` in the LOD 0 block even
     on a reimport (`Engine/Source/Editor/UnrealEd/Private/Fbx/FbxSkeletalMeshImport.cpp:2193-2214`, after
     `RestoreExistingSkelMeshData` at `:2176` has put the old skeleton back). as_10 would then FAIL its skeleton rename,
     and CR_Airship / ABP_Airship would lose their skeleton.
  2. `update_skeleton_reference_pose` True: Helm_Wheel and PilotSeat moved; same bones, so the bone merge needs no
     dialog.
  3. The triangle check expects the verified count (`rig/checks/verify/fbx_verify.json` `total_tris`) instead of the
     hard-coded 104730.
* Preconditions: `SourceArt/Airship/SK_Airship.fbx` byte-equal (sha256) to `rig/export/SK_Airship.fbx`;
  `fbx_verify.json` newer than that FBX and without defects.
* After the import it checks:
  * no new Skeleton asset (a stray one is deleted only if unused);
  * the skeleton is SKEL_Airship and the physics asset is still PA_Airship;
  * PA_Airship untouched by this reimport: file sha256 before vs after the run, not dirty, never saved here (as_11
    rebuilds it afterwards, step 6b);
  * 118 bones;
  * Helm_Wheel / PilotSeat rest positions vs `turret_dims.json` (`helm_wheel_ue`, `pilot_seat_ue`, +-2 cm).
* It prints the value for `AAirshipPawn::PilotSeatFallback` and compares it with the C++ default.
* Editors of SK / SKEL / CR / ABP / PA are closed first. CR_Airship is rebuilt afterwards by `as_12_reuse` (in place).

### as_61_hull_ink.py (risk 7: hull ink without the removed deck pieces; step 4b, written 2026-11-25)

* Input: `SourceArt/Airship/textures/T_AirshipDrivable_ComicLines.png` (4096, 8-bit RGB like Talal's), made by
  `SourceArt/Airship/scripts/hull_ink_drivable.py` (headless Blender on the rig copy; NOTES_blender.md section 9). The
  script checks the PNG header and its md5 against `rig/checks/hull_ink/hull_ink_report.json` (WARN if it differs).
* Texture: imports the PNG as `/Game/Assets/MyShip/Drivable/Textures/T_AirshipDrivable_ComicLines` (AssetImportTask, as
  as_02; re-imports over its own asset, refuses one of that name that isn't a Texture2D or came from another file). Then
  copies Talal's `/Game/Assets/MyShip/T_Airship_ComicLines` settings, read at run time: compression, sRGB, mip
  generation, LOD group, address X / Y must match (FAIL); filter, never stream, VT streaming, compression no alpha /
  quality, max size, LOD bias, power of two, the adjust_* values are copied when both have them (WARN). Only values that
  differ are set (each set rebuilds the 4K texture). Size must be 4096 x 4096 like the original.
* Material: M_Airship is a `Material` (as_02 / as_10b already rely on that) -> duplicate to
  `/Game/Assets/MyShip/Drivable/Materials/M_AirshipDrivable` (reused on a re-run), and only the texture sample that holds
  `T_Airship_ComicLines` in M_Airship gets the new texture (matched by expression name like as_02b, sampler type kept;
  the unplugged ComicMask sample keeps Talal's mask). A copy whose expressions don't match M_Airship's is refused. If
  M_Airship were a material instance: an MI copy `MI_AirshipDrivable` with the texture parameter that holds
  T_Airship_ComicLines set. `bUsedWithSkeletalMesh` read (set on our copy when missing); usage flags, shading model,
  blend mode and two-sided compared with M_Airship. The copy must use the new texture and not T_Airship_ComicLines.
* SK_Airship: slot 0 (slot name `M_Airship`) -> the copy, slot 1 `M_AirshipProps` unchanged, attribute setter as as_10
  (no mesh rebuild). Editors of SK_Airship, the texture and both materials are closed first.
* Saves only the texture, the copy and SK_Airship (nothing when anything FAILed; a run that finds them changed in memory
  refuses: restart the editor). Then checks: ours clean, SK_Airship slot 0, Talal's M_Airship / T_Airship_ComicLines /
  T_Airship_ComicMask / SM_Airship not dirtied and their `.uasset` bytes unchanged (sha256 before / after).
* `as_10_import.py` (edited): slot 0 = `Drivable/Materials/M_AirshipDrivable` (or `MI_AirshipDrivable`) when it exists,
  else M_Airship, so a later as_56 / as_10 run keeps the drivable hull material. as_56's three patch targets are
  untouched (each still matches once).
* Dry run against a mock `unreal` (Material path twice = re-run, missing skeletal-mesh flag, MI path, PIE refusal): no
  script error, the expected PASS / FAIL lines. Not run in an editor yet.
* Look check after the run: the round-2 stills (`_AirshipWork_logs/scratch/r2/stills/r2_stills.py`, `top_deck.png`,
  `top_fwd_deck.png`) or as_59's `t7_top_top.png`: no black rectangles / bar where the five pieces stood. The Blender
  renders of the same fix: `media/deck_ink_before_after.jpg`.

### as_57_pawn_defaults.py

* BP_AirshipPawn's CannonballSpeed / CannonSpawnForwardOffset / PilotSeatFallback must equal the native class defaults.
  A BP override is reset and reported. It also checks the C++ values 7000 / 80 and PilotSeatFallback vs
  `turret_dims.json`.
* Reports CannonballClass, and that `UAirshipSettings.TurretClass` loads `BP_AirshipTurret_C`, plus the TurretMounts.
* Saves only if it reset something.

### as_58_verify_round2.py (read only)

* FX:
  * NS_AirshipMuzzle: nothing of its own life cycle loops; Blast_Puffs 0.5-0.85 s with the NormalizedAge fade.
  * NS_AirshipTurretTracer: no 7500 left, 30000 present.
  * NS_AirshipTurretMuzzle: no shells, Global Scale 1.5, loops once, smoke <= 0.5 s.
* Ball: BP_AirshipCannonball class defaults and mesh scale 1.0.
* Turret: meshes (M_AirshipProps, no collision, Nanite off), BP_AirshipTurret wiring, PivotHeight / MuzzleForward =
  dims, TurretClass loads.
* Ship: SK_Airship skeleton / PA / 118 bones / moved bones; BP_AirshipPawn defaults.
* PA_Airship (rebuilt in step 6b, so checked by its bodies, not its bytes): SK_Airship uses it; the bodies and boxes read
  back through the PhysicsAssetToolset equal `as_11_physics_asset.json`; every bone with geometry in `part_bounds.json`
  has a body; part boxes = their bones' AABB + 2 cm; the Helm_Wheel box fits the 140 cm wheel; all Kinematic, no
  constraints; one SkeletalBodySetup per body in a fresh editor; the Hull boxes pass as_11b's survey rules (no column
  above the hull's top hit or below its bottom hit, none over no hull, each inside its region's z band, so nothing in
  the open truss under the forward platform) and no body stands where the five removed deck pieces were.
* Frozen assets: `IMC_Airship.uasset` byte-equal to the clone's HEAD LFS object (sha256 + size from the `git show HEAD:`
  pointer), and the Input folder's file list equal to HEAD's.
* The FX checks are targeted (each Niagara toolset call grows the editor ~25 MB for good): the tracer re-reads only the
  18 modules as_54 recorded in `as_54_turret_fx.json`; the muzzle checks read the life cycle module, InitializeParticle
  and ScaleColor of each stack. About 100 calls (the editor grew 4.9 -> 7.1 GB on 2026-11-25): run it in a fresh editor.
* Prints the previous `as_51/54/58_compile.json` and starts a new background compile check of the four systems.

### as_59_pie_round2.py (+ as_59s_status.py, as_59x_stop.py): standalone PIE harness

* Built like as_30 / as_43 / as_45, using as_30's maths header:
  * fixed 30 fps, Standalone / 1 player and Burrower off, all in memory and restored;
  * the UAirshipSettings values the run changes are restored on the class default object;
  * wind sway off on both ships;
  * TEMP_AS59_Capture + TEMP_AS59_SplashPost in the editor level, removed after PIE; the map is never saved;
  * the user's own Play is never stopped.
* Run: `inbox.sh 59 Docs/Airship/scripts/ue/as_59_pie_round2.py 60`, then poll `inbox.sh 59s
  Docs/Airship/scripts/ue/as_59s_status.py 30`. About 315 game s; the phase list is in the header (`:20-59`).
* Results: `Saved/Airship/round2/r2_result.json`, `r2_report.txt`, `r2_log.txt`, `r2_status.txt`; captures in
  `Saved/Airship/captures/round2/`.
* Knobs:
  * `AS59_SCHEME` (3): the scheme for everything except the two cases below.
  * `AS59_AIM_SCHEME` (0): Classic for the cannon aim phases, because Point & Fly's gun lock would turn the hull while
    the harness aims.
  * `AS59_DRIFT_SCHEMES` ((3, 1, 0)): the schemes of the drift phases.
  * `AS59_ONLY` (tuple of phase-name prefixes): a short run.
* Covered (S = one-player stand-in for a listen test):

  | Group | Checks |
  |---|---|
  | Muzzle smoke | T1.1, T1.2, T1.3 |
  | Cannonballs | T2.1, T2.2, T2.3, T2.4, T2.5, T2.6, T2.9 |
  | Sentinel bullets | T3.1, T3.2, T3.3 |
  | Crew damage | T4.1 S, T4.2 S, T4.4 S |
  | Stations | T5.6 S, T5.7 S, T5.8 S, T5.9, T5.10 S, T5.11 S, T5.14 S, T5.15 S (review fix, last phase `t5_dead`) |
  | Turrets | T6.1 S, T6.4, T6.5, T6.6 S, T6.8, T6.9 (review fix, phase `t6_turret`) |
  | Model | T7.2 (part_bounds.json + captures), T7.3 (captures) |
  | Boarding | T8.1 S (phase `t8_below`, 2026-11-25) |
  | Drift and hold | T9.1, T9.2 (Galleon, Classic), T9.3, T9.4, T9.5, T9.6 |
  | Console | T10.1 (log scan) |

  Everything else is written as SKIP with the reason (listen-server tests, no swarm or enemy in L_AirshipTest, Blender).
* How the checks measure:
  * Cannon tests aim the pilot camera (control rotation from the camera to the aim point, every frame).
  * Balls are tracked every frame: first sight, path, where they went hidden, shot down.
  * Turret shot counts come from `GetShotCount`.
  * Modes, health and turret heat come from the new telemetry fields. The telemetry export with arrays has its own
    parser (`parse_export`, `:105`).

### as_59 PIE run 2026-11-25 (standalone, clone editor)

* Runner: `_AirshipWork_logs/run_r2_pie.sh` (outside the repo, like run_r2_listen.sh): sets the ini to standalone
  (set_play_mode.sh, editor closed), waits for Talal's editor / >= 7 GB, takes the lock, launches L_AirshipTest, arms
  as_59 through a wrapper with the knobs (`AS59_ONLY="t9_ t3_"`, `AS59_SCHEME`, `AS59_AIM_SCHEME`, `AS59_DRIFT_SCHEMES`,
  `AS59_PRE` = inbox probe scripts before arming), polls as_59s every 30 s, re-runs once if PIE is stopped from outside,
  quits and releases (trap). The previous r2_* files go to `round2_prev_<ts>/`, captures to `captures/round2_prev_<ts>/`.
  Run in the background with the output in `_AirshipWork_logs/run_r2_pie_<label>_<ts>.log`.
* Runs: first run 32 PASS / 9 FAIL / 2 WARN; fix 1: 40 / 4; fix 2: 42 / 2; fix 3: 42 / 1 FAIL / 1 WARN; final 44 PASS,
  0 FAIL, 0 WARN, 2 INFO (T1.3, T7.3 captures), 14 SKIP. 346 game s, 357 s wall, editor RSS 5.1 GB. Every FAIL was the
  harness measuring the wrong thing; the C++ was not changed. Editor log during PIE: no error, ensure, Accessed None,
  LogScript or Niagara warning from the airship; only older warnings (missing FrozenNorse packs, `M_Thruster` missing the
  Nanite usage flag, GA_HitReact with no montage at PIE start).
* Harness fixes (all in `as_59_pie_round2.py`; no threshold changed):
  1. `hit_info`: UE 5.8 Python has no `GameplayStatics.break_hit_result`, and the old code swallowed the error, so every
     Python trace read "no hit" (T2.9 could only WARN; T3.x / T6.9 named no first hit). It reads `HitResult.to_tuple()`
     now (properties as the last fallback) and lists read failures in the report.
  2. T2.1: the launch speed is taken relative to the ship's velocity in the frame before the shot. The broadside's recoil
     (`CannonRecoilImpulseDV` 80 cm/s per cannon, the same frame) had added 158 cm/s: 7158 instead of 6998.
  3. T2.9: 2 s of settling before the baseline (the camera swings from t1_cap0's starboard aim, the cannons slew), the
     ball at 2.5 s, the baseline's spread reported (WARN if over 0.1 deg: not settled).
  4. T2.3: 2.5 s of steady flight before the shot (was 1 s after a 430 m teleport and a 180 deg camera swing). While the
     harness aims, a 0.01 look input each frame: Classic's camera recenter (after `RecenterDelay` 1.5 s without look input
     above 8 m/s) had pulled the crosshair toward the bow and the balls flew past the wall's end. `aim_at(..,
     lag_comp=True)` (t2_lead, t2_gun only) adds the spring arm's rotation lag (at 30 m/s the crosshair sat 9 m ahead of
     the aim point). Now: crosshair 1.6 m off the aim point, balls 1.2 and 2.0 m from it.
  5. T2.6: the player rides ship 1's deck and shoots ship 2's ball hovering 1 m outside ship 1's port side (17 m away).
     From the start platform under the ship the aim was ~50 deg up, the on-foot camera sat in the platform and 4 s of
     rounds missed. The phase lasts up to 16 s, ends 1 s after the shoot-down, and the after-check no longer needs the
     ball (it is removed 1 s after it goes down).
  6. T9.2 (Galleon, Classic): "no reverse" is read from 3 s after the exit, and the throttle must only recover until then.
     The harness teleports a piloted ship to 48 m/s with no input, so Galleon's boarding STOP order (-0.83) and Classic's
     brake (-0.25) command reverse before the exit; it decays with the shaping lag (time constant 0.25 s Galleon, 0.45 s
     Classic). The drift itself commands none (-5e-6 and -3e-4 from 3 s).
  7. T9.6: `Aura.Airship.Input` flies every ship of the world: ship 2 is cleared in the same frame (it stays within
     27 cm). The player waits on the start platform: as a rider he was carried 800 m, t7_caps's teleport of ship 1 left him
     there, `Board 0` took the nearest ship (ship 2) and T5.11 / T4.2 / T5.15 measured the wrong ship. The phase runs up to
     75 s and ends 2 s after the Hold: coasting from 48 m/s to 3 m/s takes 39 s (v1 drag only, by design D9.4).
  8. T5.15: BP_MyCharMech dies with its Control Rig ragdoll and the disintegration; no part simulates physics (C++ log
     "0 simulated part(s) ignore the hull"), so the ignore rule is checked only for parts that simulate. The rise is
     measured after the death's dismount places the body at the exit point (120 cm inboard, dropped onto the UCX lid:
     +134 cm, a set move, not a throw). Hull speed change 0.0 cm/s, spin 0.01 deg/s.
  9. T10.1: Telemetry's lines don't carry the command's name; it is matched on its own output, and "line 3" on the
     unpiloted / stations / turrets line (it had matched a turret BeginPlay line).
  10. New phase `t8_below` (6 s, after t2_splash): T8.1 S, the player on the ground under the hull's centre presses F
     (IA_AirshipBoard): 708 cm below the belly boards, 1197 cm below is refused. as_60 doesn't cover T8.1 either.
  11. T1.1 / T1.2 report the measured smoke life: the first NS_AirshipMuzzle component to the frame none is left.
  12. The skip reasons of T2.8 and T4.5 say what is missing (3 characters at once; a second pilot): no harness covers them.
* Measured (clone: GE_GunShootDamage 1 per hit; Talal's tree has 1000):

  | What | Measured | Setting |
  |---|---|---|
  | Turret bullet damage | 4.0 (84 from 21 bullets on ship 2) | 4 x GE; 4000 in Talal's game |
  | Turret fire | 11 rounds in a 1.0 s trigger, 21 from both turrets in 1 s | FireInterval 0.1 s, spread 1 deg, range 250 m |
  | Turret heat | 0.31 after 1 s; overheat 2.9 s into a hold, 0 rounds while hot; fires again 1.2 s after release (heat 0.35) | 1/30 per round, cool 0.4/s after 0.2 s |
  | Turret round through ship 2's hull at its turret | 10 of 21 rounds on the turret (40), the rest on the hull | |
  | Ball | radius 50 cm (1 m), mesh scale 1.0, gravity scale 0.6, 6998 cm/s relative to the muzzle | 7000 cm/s |
  | Ball at 150 m (parked) | impacts 0.9 and 1.1 m from the aim point, apex 3.2-3.3 m, 2.1 s | |
  | Ball from 30 m/s, 120 m off the beam, 15 m ahead | 1.2 and 2.0 m from the aim point | lead on |
  | Range at the 8.5 deg cap (level) | 233 and 254 m (spread 0.6 deg), 3.4-3.7 s, apex 8-10 m | theory 244 m |
  | Ball health | 30 rounds of the character gun (shot down at 7.6 s of fire, ~4.5 rounds/s) = 8 turret bullets | 30 gun units |
  | Splash | 21.4 at 551 cm | 600 cm, 60 at the centre to 18 at the edge |
  | Muzzle smoke | 0.90 s with the C++ cap, 0.87 s from the asset alone; 0 components at +1.5 s | cap 1.0 s |
  | Crew share | pilot 110 -> 85 for 100 ship damage | 0.25 |
  | Drift after a 47 m/s exit | 2.50 m/s from 30 s (P&F, Galleon), 2.51 (Classic); heading within 0.02 deg | 250 cm/s |
  | Exit at rest | Hold, moved 1.5 cm in 30 s | |
  | Drift at a wall | stopped 7.3 m short, then Hold, no damage | look-ahead 3 s |
  | Coast (debug input cleared at 48 m/s) | Hold after 39 s at 2.9 m/s | HoldEngageSpeed 300 |
  | Helm wheel | 140 cm across (part_bounds), at the mech's chest in `t7_helm_helm.png` | mech 174 cm |

* Seen, not fixed: a gunner killed at the gun stays where he died in world space (CMC off, no physics), so on a moving
  ship the body hangs in the air while the ship moves on until the disintegration (1.6 s) and the respawn (5 s). The
  T1.3 captures can't show the puffs (white smoke against the white hull from that camera); the component count is the
  measurement. The black rectangles of risk 7 show in `t7_top_top.png`.

### as_62_pie_swarm.py (+ as_62s_status.py, as_62x_stop.py): standalone PIE with a real swarm (2026-11-25)

Written without an editor; not run in PIE yet (mock run only, below). It covers T3.5 and T6.7, which as_59 skips, and
Talal's rule that the swarm only attacks a ship while it is driven. No `Aura.MechSentinel.TestBullet`: every bullet comes
from the swarm's own combat processor.

* The swarm: `TEMP_AS62_Spawner`, an `AMechSentinelWaveSpawner` placed in the editor level before PIE, because Python
  can't spawn actors in a PIE world. Its settings:
  * EntityConfig `DA_MechSentinelConfig`, WhenCleared, bAutoStart off, no fallback point;
  * wave 1: `AS62_COUNT` (5) sentinels at full stats;
  * wave 2: `AS62_COUNT_D` (8) at `AS62_D_HEALTH` (0.5) x health.

  Each phase that needs a fresh swarm calls `DespawnAll(false)`, then a few frames later `StartWaveAtPoints`. Requests
  queued in the same frame as a DespawnAll are dropped by it. The rules are the GameMode's (BP_MyGameMode ->
  DA_MechSentinelSwarmRules).
* How sentinels are read (server truth):
  * `UMechSentinelCombatLibrary::FindSentinelsInCapsule` (300 m capsule) + `GetSentinelInfo` give location, state and
    health;
  * `OnSentinelKilled` / `OnSentinelDamaged` are bound with `add_callable` and removed at the end;
  * the PlayerState's pawn is what `GatherPlayerTargets` hands the swarm;
  * with `log LogMechSentinel Verbose`, the "Sentinel bullet hit tagged target X" lines count the tagged-path hits per
    phase and target. A ship loss without such a line came through the Pawn sweep on the driven ship's PA bodies.
* Phases (131 game s): settle, spawn2 (ship 2 at P2, 50 m to starboard of P1 = (-30000, 2500, 1600)), board, then:

  | Phase | What happens | Checks |
  |---|---|---|
  | `s_pilot` 30 s | (a) driven ship 1 hovers at P1, wave 1 from 55 m to port; (c1) ship 2 parked 50 m off | SW.a1 target = ship 1, T3.5 hull loss, SW.a2 pilot = 0.25 x loss, SW.a3 turrets (INFO), SW.c1 ship 2 untouched |
  | `s_gunner` 25 s | (b) Exit, Mount 0 4 (turret L) on the now undriven ship 1 | SW.b1 target = the gunner (re-centred swarm), SW.b2 losses (crew share + direct), SW.b3 turret hit by real bullets |
  | `s_empty` 22 s | (c2) Dismount, the player 280 m away on the start platform | SW.c2 ships unchanged over 20 s, the swarm leaves |
  | `s_turret` 45 s | (d) DespawnAll, Board, wave 2 from 55 m ahead; TurretFire tracking (2.5-9 s, 29-44 s with jump-backs); holds (9-29 s) | T6.7, SW.d3 kills, SW.d1 (INFO), SW.d2 redirect in holds, SW.d4 crew share |

* Why the holds (geometry, from SPEC_A D6.1 / 6.3 and the trait defaults):
  * the swarm orbits its target point (the ship's ROOT + TargetHeightOffset 90) at 11-19 m, 2-9 m up;
  * the turrets sit at hull x 2100, 21 m forward of the root;
  * a bullet aimed at the root never passes a point farther from it than the sentinel, so in a plain hover no aim line
    crosses a turret;
  * an aim line from outside the forward-deck convex (UCX_01: x 10.2-31.2 m, |y| <= 3.6 m, z 3-10.8 m) through a HitBox
    needs a sentinel about 25-31 m ahead, 4 m to the side and 9.5-10.5 m up. That is still inside the attack exit range
    (31.25 m), but only a spot sentinels pass through.

  So for up to 4 s per sentinel the harness teleports the ship every frame (yaw 0) to keep one ATTACKING sentinel at hull
  `AS62_HOLD` = (2900, -395, 1001):
  * 3065 cm from the target point;
  * its aim line meets UCX_01's port face about 2.7 m from the sentinel, then crosses turret 0's HitBox 19 cm inside its
    outer face, at mid height.

  Each hold records a Python trace of that line (the first Visibility hit, whether it crosses the HitBox) and how far the
  sentinel was off its spot. SW.d2 FAILs only when a hold had that geometry and the turret still took nothing.
* The window-B jump-backs exist for the same reason: the orbiting swarm sits behind the turrets' arcs.
* Safety:
  * between phases the player is topped up with GE_HealthPotion (instant only, when below 70 %);
  * below `AS62_MIN_HP` (30) the phase's sentinels are removed, and the phase's checks say so.
* Runner: `_AirshipWork_logs/run_r2_swarm.sh`, a copy of run_r2_pie.sh's flow. The knobs are environment variables of
  the same names. Results: `Saved/Airship/round2_swarm/` (`sw_*`); captures: `Saved/Airship/captures/round2_swarm/`
  (6 shots).
* Offline: `_AirshipWork_logs/scratch/r2x/mock62/run_mock62.py`, a fake `unreal` with a crude orbiting swarm. The full
  run and these cases ran with 0 script errors:
  * phase subsets;
  * the safety cut;
  * PIE ended from outside;
  * as_62x stop;
  * the user's Play.
* Not covered: T2.8. There is no damage dummy with its own ASC: no enemy Blueprint, and an unpossessed BP_MyCharMech has
  no PlayerState. A gunner on a DRIVEN ship needs a second player (as_60).

## Numbers and geometry the harness uses (L_AirshipTest, `as_22_test_map.py`)

* Ship spawn (0, 2500, 1600). Cannon walls: port face y -9300 (back face -9700), starboard face +14300. Both walls are
  60 x 4 x 30 m: x -3000..3000, z 100..3100.
* T2.2: ship moved to y = -9300 + 15000 - mean port muzzle y, so the port muzzles are 150 m from the wall face.
* T2.4: ship at y = -9700 - 30000 - mean starboard muzzle y (300 m from the back face). Expected: the elevation targets
  at the 8.5 cap (`CannonElevDeg_R1/R2`), and the ball 10 m below the aim point when it reaches the wall.
* T2.3: 30 m/s along +X, aim 120 m off and 15 m ahead of the beam. Aiming abeam would need about 24 deg of lead
  (asin(30/70)), past the cannons' 20 deg yaw limit, so it can't pass as written in the spec.
* T6.4: ship 1 at (-10780, 40000, 1600), ship 2 at (0, 40000, 1600). The turret muzzles are about 60 m from ship 2's
  stern. Expected drop = 20 x TurretGunDamageMultiplier x the GE value read at runtime (80 in the clone).
* T2.5: the on-foot player stands 550 cm from the impact on TEMP_AS59_SplashPost's -Y face (post at (-3500, -3500, 200),
  2 x 2 x 4 m). Expected 60 x lerp(1, 0.3, d / 600) = 21.4.

## Deviations from the spec, and why

1. The harness is `as_59_pie_round2.py`, as the spec's table numbers it. The task text said `as_55_pie_round2.py`, but
   the spec gives as_55 to the turret Blueprint.
2. `as_56` patches as_10 in memory instead of running it unchanged (the skeleton problem above).
3. T2.5 uses the on-foot player as the dummy. The splash measures to the actor's centre, and a ship's centre can't be
   5.5 m from an impact outside its 51 x 24 m hull.
4. T3.2 turns the Mesh collision off (as T3.1 does) for the bullet. Until the review fixes it also turned the hull's
   Visibility response off; since 2026-11-25 the hull keeps it and the C++ hands the hull hit to the turret (risk 1).
5. T5.11 sets `Settings.CrewDamageShare 0` for that phase. `Aura.Airship.Kill` / ApplyShipDamage take the whole Health
   away, and D4 would give the gunner 25 % of it (about 500), which kills him (eject, then the on-foot death). The spec
   expects him ejected alive. See risk 3.
6. T9.1 checks the heading over the phase's 37 s, not 60 s, to keep the run near 5 minutes.
7. Review fixes (2026-11-25): two phases were added. `t6_turret` (3 s, after `t6_hit`): ship 1's turrets fire 1 s at
   ship 2's port turret HitBox from behind; pass when that turret loses health in whole bullets. `t5_dead` (12 s, last):
   it waits for the player respawned after `t4_kill`'s death, mans R1 of ship 2 (`Aura.Airship.Mount 0 2`, ship 1 is
   dead by then) and kills him there; pass when every part that simulates ignores PhysicsBody (the mech has none: Control
   Rig ragdoll), the hull's speed and spin barely change in 2.5 s, the body doesn't rise over 1 m after the dismount
   placed it, and the station is free.
9. T8.1 S (2026-11-25, phase `t8_below`): the one player stands in for the spec's client (board from 7 m under the
   belly, refused from 12 m).
8. Regression harnesses (review fixes): `as_30_pie_smoke.py` (and with it as_43) and `as_45_pie_mp.py` set
   `UAirshipSettings.CrewDamageShare` to 0 on the class default for the whole run and restore it (knobs
   `AS30_CREW_SHARE`, `AS45_CREW_SHARE`; default 0.0, None keeps the project value). Their v1 checks compare the
   pilot's health with its value before boarding.

## Risks and open items for the lead

1. **Hidden turret HitBox (fixed in C++, 2026-11-25).** The review confirmed it: the HitBox is inside SM_Airship's
   forward deck convex (UCX_01) on every side, so no Visibility trace from outside reaches it. The C++ now hands a hull
   hit over the forward deck to the turret behind it (`AAirshipPawn::FindTurretBehindHullHit`, SPEC_A.md section 6.3)
   for sentinel bullets, turret rounds and the character gun. T3.2 no longer switches the hull's Visibility off and
   names the first Visibility hit (`b2_trace`, the hull expected); T6.9 does the same for turret rounds at ship 2's
   turret.
2. **Crew share on a kill.** Should the crew share apply to the Health drop of a kill (Kill / ApplyShipDamage)? As
   written, a ship killed from high health kills its whole crew through the share.
3. **Tracer speed.** If PS_06's 7500 cm/s lives inside a scratch module or the material, as_54 finds nothing and only
   WARNs. Then the tracers lag at range (spec risk 10).
4. **turret_dims.json keys.** as_53 / as_55 / as_56 / as_57 read `pivot_height_cm`, `muzzle_forward_cm`,
   `base_radius_cm`, `gun_length_cm`, `pilot_seat_ue`, `helm_wheel_ue` and, if present, `base_bounds_cm` /
   `gun_bounds_cm`. Vectors may be `[x, y, z]` or `{"x", "y", "z"}`, in UE cm. Keep the Blender output to these names.
5. **Shared namespace.** The background compile checks and as_59 run on Slate post-tick callbacks in the shared inbox
   namespace. Don't start PIE yourself while one is open. as_59 refuses to arm while PIE runs, and as_58's check opens
   Niagara editors.
6. **PA_Airship (done in the editor stage, 2026-11-25).** Talal's later ask ("make a proper PA for ship"): step 6b
   rebuilds PA_Airship with `as_11_physics_asset.py` from the round-2 `part_bounds.json` and the hull boxes that
   `as_11a` (column survey of the round-2 rig) + `as_11b` fit: 35 bodies, 119 boxes (79 hull, 7 chain links), every
   bone with geometry covered, no box above the deck or in the open truss, nothing where the five removed pieces were.
   His local PA_Airship is empty; this one replaces it when he pulls (a conflict on that file: take ours).
7. **Baked ink where the removed deck pieces stood (found 2026-11-25; fix written, run step 4b `as_61_hull_ink.py`).** The hull keeps Talal's baked comic texture
   (`/Game/Assets/MyShip/T_Airship_ComicLines`, 4096, in `M_Airship`, SK_Airship slot 0). It was baked with the five
   pieces in place, so the deck under each of them is solid ink: sampled on the rig copy (headless Blender, rays down on a
   10 cm grid, UV at the hit), luminance 0.13 under every piece (99-100 % of the points darker than 0.15) vs 0.91-0.93 on
   the deck 0.5-1.5 m around it. In Unreal the deck shows five black rectangles / bars where the pieces were
   (`Saved/Airship/round2/stills/top_deck.png`, `top_fwd_deck.png`, `cannon_L1.png`, `helm_scale.png`; probe:
   `_AirshipWork_logs/scratch/r2/stills/deck_ink_probe.json`). Fix (Blender side, not done): re-bake the hull comic
   texture on the rig copy without the pieces into a drivable-ship copy (texture + `M_Airship` copy for SK_Airship's
   slot 0; Talal's `/Game/Assets/MyShip` assets and SM_Airship stay as they are), or paint those UV islands paper.
   Done (2026-11-25, Blender side): `hull_ink_drivable.py` re-baked the ink on the rig copy with and without the pieces
   (comic_lines.py's own shader and settings; with the pieces it reproduces Talal's texture byte for byte on 99.99 % of
   the texels near them) and took the re-bake only where the removal changes it, within 1.5 m of a removed piece:
   59,869 texels (0.36 % of the 4096 texture; 58,955 ink -> paper, 914 paper -> ink where the bow tier's edge outline
   now runs on across the old steps), every other texel byte-identical. Deck under the pieces: luminance 0.15-0.16 ->
   0.91-0.93. Renders: `media/deck_ink_before_after.jpg` (changed pixels only inside the pieces' screen boxes). The
   editor side is `as_61_hull_ink.py` (step 4b): `T_AirshipDrivable_ComicLines` + `M_AirshipDrivable` on SK_Airship
   slot 0; Talal's `/Game/Assets/MyShip` assets and SM_Airship stay as they are.
