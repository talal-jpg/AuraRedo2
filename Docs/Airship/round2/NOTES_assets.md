# Round 2, PR A: editor scripts (assets owner)

Status 2026-11-24: written, not run (no editor in this stage). The lead runs them in the editor stage, in the order
below. Every script refuses to change assets while PIE runs, saves only its own assets by explicit path, prints
`PASS / FAIL / WARN / INFO` lines and a last `RESULT:` line, and writes a JSON report to `Saved/Airship/`.
Spec: `SPEC_A.md` sections 1 (D1, D2, D6, D7), 3 and 4.

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
| 5-6 | existing `as_09` (headless Blender), `as_12_reuse.py`, `as_13_cr_eval.py` | step 4 | `CR_Airship` |
| 7 | `as_53_turret_import.py` (300 s) | turret FBX + `turret_dims.json` | `SM_AirshipTurret_Base`, `_Gun` |
| 8 | `as_54_turret_fx.py` (300 s) | nothing new | 3 turret Niagara systems |
| 9 | `as_55_turret_bp.py` (300 s) | C++ `AAirshipTurret`, steps 7-8 | `BP_AirshipTurret` |
| 10 | `as_57_pawn_defaults.py` (120 s) | C++ | `BP_AirshipPawn` only if it overrode a C++ default |
| 11 | `as_58_verify_round2.py` (300 s) | all above | nothing (read only) |
| 12 | `as_59_pie_round2.py` (60 s, then poll) | all above, `part_bounds.json` from step 5 | nothing (PIE, TEMP actors removed) |

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
  * PA_Airship untouched: file sha256 unchanged, not dirty, never saved (PA is not rebuilt here);
  * 118 bones;
  * Helm_Wheel / PilotSeat rest positions vs `turret_dims.json` (`helm_wheel_ue`, `pilot_seat_ue`, +-2 cm).
* It prints the value for `AAirshipPawn::PilotSeatFallback` and compares it with the C++ default.
* Editors of SK / SKEL / CR / ABP / PA are closed first. CR_Airship is rebuilt afterwards by `as_12_reuse` (in place).

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
* Frozen assets: `IMC_Airship.uasset` and `PA_Airship.uasset` byte-equal to the clone's HEAD LFS objects (sha256 + size
  from the `git show HEAD:` pointer), and the Input folder's file list equal to HEAD's.
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
  | Drift and hold | T9.1, T9.2 (Galleon, Classic), T9.3, T9.4, T9.5, T9.6 |
  | Console | T10.1 (log scan) |

  Everything else is written as SKIP with the reason (listen-server tests, no swarm or enemy in L_AirshipTest, Blender).
* How the checks measure:
  * Cannon tests aim the pilot camera (control rotation from the camera to the aim point, every frame).
  * Balls are tracked every frame: first sight, path, where they went hidden, shot down.
  * Turret shot counts come from `GetShotCount`.
  * Modes, health and turret heat come from the new telemetry fields. The telemetry export with arrays has its own
    parser (`parse_export`, `:105`).

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
   dead by then) and kills him there; pass when the ragdoll mesh ignores PhysicsBody, the hull's speed and spin barely
   change in 2.5 s, the body doesn't rise over 1 m, and the station is free.
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
6. **PA_Airship.** Talal's later ask ("make a proper PA for ship", memory 11-24 12:01) is not in these scripts. as_56
   keeps PA_Airship untouched and still linked; rebuilding it is a separate step (existing `as_11_physics_asset.py`)
   after as_56 and as_12.
