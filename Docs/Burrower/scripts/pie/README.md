# Burrower PIE test (EDITOR_SESSION.md step 8)

A listen server + 1 client PIE run on `/Game/Maps/StartupMap` that checks, with numbers, everything step 8 asks for:
spawn behind each player, follow, body wave, rotor spin, tile cutting (server and client), pipes attached, damage,
death + ragdoll, respawn after `SpawnInterval`. It is a frame-by-frame state machine (Slate post-tick callback) armed
through the clone editor's inbox, so the world keeps ticking while it runs. Nothing is saved.

Built on the Mech Sentinel harness (`_MechSentinelCaptures/harness/v2_20261121/pie_t.py`, `pie_gun.py`): same fixed
frame rate trick, missing-pawn restart, server-spline steering, gun injection, TEMP scene capture, X window grabs.

## Files

| File | What |
|---|---|
| `bw_pie_test.py` | The test. Inbox script: preflight, in-memory setup, starts PIE, registers the state machine, returns at once. |
| `bw_pie_config.json` | Main config (SpawnNow per player index). Merged over `BW_DEFAULTS` in the script. |
| `bw_pie_config_auto.json` + `bw_pie_run_auto.py` | Variant: the first Burrower comes from the spawner itself (`FirstSpawnDelay`). |
| `bw_pie_config_turns.json` + `bw_pie_run_turns.py` | Variant: players weave up/down and left/right, head path recorded, `KillAll` at speed; checks j, k, l, m (section "Turns variant"). |
| `bw_pie_preflight.py` | Inbox script: only the read-only checks (changes nothing, no PIE). |
| `bw_pie_report.py` | Prints the result as `PASS:/FAIL:/WARN:/INFO:` lines. Plain `python3` (or inbox). `--full` adds the data. |
| `bw_pie_wait.sh` | Waits for the run to finish (or a crash / editor exit), progress every 30 s, then the report. |
| `bw_pie_cleanup.py` | Inbox script: ends an active run, or restores from `pie_restore.json`, removes `TEMP_BW_` actors. |
| `bw_quit_clean.py` | Inbox script: quits the editor without saving (refuses during PIE, an active run, or unsaved Burrower assets). |
| `bw_ini_playmode.sh` | `set` / `restore` / `show` the PIE net mode keys in the clone's ini. The clone's editor must be closed (an editor of another project may run). |
| `xgrab_loop.sh` | Background loop: grabs the clone editor's own editor/PIE X windows (never another editor's) whenever the test asks (one request per shot). |

Outputs (all under `/mnt/new_partition/UnrealProjects/_BurrowerWork/Saved/Burrower/`):

* `pie_result.json`: checks a..i (status, one-line summary, numbers), setup, preflight lines, events, 1 Hz samples,
  script errors, editor-log scan, restore record. `"done": true` at the end. A copy `pie_result_<run>_<stamp>.json`.
* `pie_log.txt`: one line per event/check (appended across runs, `==== ... armed` separates runs).
* `pie_shots/<run_name>/<label>_<kind>_<server|client>.png`: scene captures; `x_<run>_<label>_<n>_<window>.png`: X grabs.
* `pie_restore.json` while a run is active (the originals of every in-memory change); renamed `.restored` after.
* `xgrab/*.req` (consumed by `xgrab_loop.sh`), `xgrab/log.txt`.

## How to run (step by step)

Paths: `H=/mnt/new_partition/UnrealProjects/_BurrowerWork/Docs/Burrower/scripts/harness`,
`P=/mnt/new_partition/UnrealProjects/_BurrowerWork/Docs/Burrower/scripts/pie`.

0. Before: EDITOR_SESSION steps 1-7 are done in the clone (C++ built, `SK_Burrower`, `PA_Burrower`, `CR_Burrower`,
   `ABP_Burrower`, `BP_Burrower` saved). Check memory (`free -g`: available >= 3 GB; the PC froze below that) and that no
   UnrealEditor runs that someone else is using. Block sleep if the run is long
   (`setsid nohup systemd-inhibit --what=sleep:idle:handle-lid-switch --mode=block sleep 7200 &`).
1. Editor closed: `bash $P/bw_ini_playmode.sh set`
   Backs up `Saved/Config/LinuxEditor/EditorPerProjectUserSettings.ini` once (`<ini>.bw_pie_backup` + the 3 original
   lines in `<ini>.bw_pie_keys`) and sets, in `[/Script/UnrealEd.LevelEditorPlaySettings]`:
   `PlayNetMode=PIE_ListenServer`, `PlayNumberOfClients=2` (instance 0 is the listen server, instance 1 the client),
   `RunUnderOneProcess=True`. (The test also sets the same three in memory through ToolsetLibrary, `play.force_in_memory`;
   that alone worked for the Mech Sentinel runs but is not written to the ini.)
2. Launch on the map: `$H/launch.sh /Game/Maps/StartupMap` (waits for the inbox and for shader compiles; log in
   `Saved/Burrower/editor_stdout.log`). The editor jumps to workspace 2 by itself. If it ends up on a hidden i3 workspace,
   PIE drops to ~3 fps: the test locks game time (fixed frame rate 30), so results stay valid, the run just takes longer.
3. Optional, for X window grabs: `setsid nohup $P/xgrab_loop.sh > /dev/null 2>&1 &` (ends with the editor).
4. Preflight: `$H/inbox.sh pre $P/bw_pie_preflight.py 120`. Fix every `FAIL:` line before going on. Typical:
   wrong map (relaunch with the map), `BurrowerCharacter` missing (C++ not built), `BP_Burrower` has no mesh. No anim
   class is only a `WARN` (the run goes on, but c, d and f will fail).
   A missing Project Settings `Burrower Class` is only a `WARN`: the run sets it in memory to
   `/Game/Assets/Enemies/Burrower/BP_Burrower.BP_Burrower_C`.
5. Arm: `$H/inbox.sh pie $P/bw_pie_test.py 120` (or `bw_pie_run_auto.py` for the auto-spawn variant). The `.out` shows
   the preflight lines and `INFO: armed ...`. Do not touch the PIE windows during the run if you can help it (focus on the
   client window lowered the fps before; mouse/keyboard in the windows changes the camera and aim).
6. Wait: `$P/bw_pie_wait.sh 2700` (prints progress, then the report). Or look any time: `python3 -B $P/bw_pie_report.py`.
   A full run is about 75 s of game time (2-3 min wall at ~15 fps, ~12 min on a hidden workspace).
   At the end the test restores everything, stops its PIE session (only its own) and removes `TEMP_BW_Capture`.
7. If anything went wrong or you stop early: `$H/inbox.sh clean $P/bw_pie_cleanup.py 60` (twice if it says PIE is still
   running). It never stops a PIE session it did not start unless you put `BW_CLEANUP_STOP_PIE = True` at its top.
8. Quit: `$H/inbox.sh quit $P/bw_quit_clean.py 30`, wait until `ps -C UnrealEditor` is empty.
   The StartupMap shows as modified (the TEMP actor was added and removed): it is discarded, never saved.
9. Editor closed: `bash $P/bw_ini_playmode.sh restore` (puts the 3 keys back, keeps other changes the editor wrote,
   keeps the full backup as `<ini>.bw_pie_backup.<stamp>`).
10. Results: `python3 -B $P/bw_pie_report.py --full`, screenshots in `Saved/Burrower/pie_shots/<run_name>/`.

## What the run does (timeline, game seconds)

| Phase | Players | What happens |
|---|---|---|
| `wait_pie` | | PIE requested; waits up to 180 s wall for the worlds. |
| `wait_pawns` | hold | Needs 2 worlds (server, client) and 2 player pawns. A player controller without a pawn after 3 s (StartupMap's "NO PLAYERSTART with positive rating") is restarted with `GameMode.restart_player_at_transform` next to the host. Check `setup`. |
| `warmup` 14 s | hold (flying) | Path / platforms / bridges build. Then `Aura.Burrower.DebugRotorBox 1` in the server world. |
| `spawn` 1.5 s | hold | `Aura.Burrower.SpawnNow <i>` in the server world for every GameState PlayerArray index; the spawn geometry is read in the same frame. Check (a) after the replication wait. |
| `follow` 16 s | fly the lane at 900 cm/s, 500 cm above the path | Distances, poses at 10 Hz, rotor every frame from 6 to 8 s. Checks (b), (c), (d), (f) at the end. |
| `cut` 12 s + 2.5 s | hover 140 cm above a clear tile ~6 m ahead | The Burrower dives under its player; tiles are tracked per platform on both machines. Check (e). |
| `damage` 8 s | hover, look at own Burrower | The server player fires `GA_GunShoot` (IA_LMB injected, control rotation aimed at `J2_Midbody`), stops after 3 health. No drop: the project's damage GE is applied from Python instead. Check (g). |
| `kill` 4 s | hover, look | `bEnabled = True` (memory), `Aura.Burrower.KillAll` in the server world, bones sampled every 0.2 s. Check (h). |
| `respawn` | hover, look | Waits for a new Burrower per player (up to SpawnInterval + 8.5 s). Check (i). Then 2.5 s more for the last shot, then finish. |

Players fly (`MOVE_Flying`, max fly speed 900, braking 2000) the whole time so they never fall through cut tiles. Client
pawns are steered in the client world (movement input, so prediction and the server agree) along the SERVER world's path
spline (a client's spline has only the level's points). Burrowers are never touched except `VisibilityBasedAnimTickOption =
AlwaysTickPoseAndRefreshBones` on their meshes (so the bones are evaluated even where the Burrower is off screen or the
editor does not render; set without PostEditChange, PIE only).

## The checks and how they are measured

All positions in cm. "component space" = the Burrower mesh component (`get_bone_transform(bone, RTS_COMPONENT)`).

* **setup**: worlds, player pawns, restarts, `DebugDieAfterBeginPlaySeconds` of the pawns (> 0 kills players every few
  seconds and pauses the spawner: WARN), the GameMode's `DA_MyEnemyCharacterClassInfo` (missing: spawns are refused).
* **(a) a_spawn**: per player exactly one living Burrower whose `TargetPlayer` is that player, on the server and on the
  client. Spawn geometry against the player at that frame: horizontal distance = `SpawnDistanceBehind` +-10 % + 50,
  height offset = `SpawnHeightOffset` +-80, direction: dot with "behind" (against velocity above
  `MinSpeedForVelocityDirection`, else against facing) >= 0.9. Client copy within 400 cm of the server's.
  Auto variant: the spawn also has to come `FirstSpawnDelay` (-0.5/+1.5 s) after that player's pawn appeared.
* **(b) b_follow** (server): distance actor (head) to its player from spawn to the end of `follow`. PASS when the mean of
  the last 2 s is 200 cm under the start or <= 2500 cm, the max stays <= start + 600, and it travelled >= 1000 cm.
  (C++ steady state at 900 cm/s is about 1100-1300 cm: the throttle ramps over `SlowdownDistance` 1500.)
* **(c) c_wave** (server and client): sideways offset `J4_Tail.y - J0_Head.y` (component space) sampled at 10 Hz over
  `follow`. PASS: peak-to-peak >= 15 cm and >= 2 crossings of its mean (20 % hysteresis). Also: `J2` series, the lag
  J2 -> J4 in samples (> 0 = the wave travels head to tail), the anim instance's `WaveAmplitudeDeg` / `WaveTime` range
  (if those move but the bones do not, the Control Rig node's pins are not wired / exposed).
* **(d) d_rotor** (server and client): `Rotor` in component space every frame for 2 s. The rotation relative to the first
  sample is split into twist about +X and swing; PASS: unwrapped twist >= 90 deg, swing <= 3 deg, location within 3 cm of
  its reference-pose place (from the mesh ref pose; the config's `(977.9, 0, 180.5)` is compared for information).
  Reports deg/s against `RotorSpinSpeed` (720) and the anim instance's `RotorAngleDeg` turn. At 30 fps fixed, 720 deg/s is
  24 deg per frame; steps above 150 deg are flagged as possible aliasing.
* **(e) e_tiles**: `AMyHexPlatform.ActivatedTiles` / `IsTileCollapsed` are not readable from Python (no Blueprint/Edit
  flags, not UFUNCTIONs), so tiles are read from `HexPillarsISM` (readable): instance world positions (pillar top) per
  platform. Platforms within 60 m of a rotor box are tracked; when a count drops, the missing tiles are found and each is
  classed `rotor` if a rotor box centre of the last moments was within `hypot(box extent X, Y) + 1.2 * HexRadius + 100`
  horizontally and the box bottom reached the tile top (+50), else `other` (the platform's own collapse chains). PASS: >= 1
  rotor cut on the server, every one of them gone on the client too (no client tile within 30 cm), and equal tile counts
  per tracked platform (a mismatch with all rotor cuts matched is a WARN: other collapses still replicating).
  `cut_diag` in the data has rotor centre / extent vs the hover point and the tile top when nothing is cut.
* **(f) f_pipes** (server and client): for each of the 8 chains of `Burrower_rig_info.json`: distance of `_01` and `_end`
  to `J1_Forequarters` (component space) vs the reference pose; PASS within 5 cm for every chain. Middle bones (1/3 and
  2/3 along) in J1's local frame: std >= 0.5 cm in at least one chain (none: FAIL "dynamics not running"; some chains
  still: WARN). Also the anchors' drift in J1's local frame.
* **(g) g_damage**: `Health` / `MaxHealth` of each Burrower's ASC (`UMyAttributeSet`) on server and client before and
  after; PASS when it dropped >= 0.5 on both via the gun; WARN when only the Python GE fallback
  (`GE_GunShootDamage`, SetByCaller `SetDamageByCaller`, from the target player's ASC) lowered it; FAIL otherwise. Also:
  injected shots, `HitActor: ...Burrower...` lines in the log (GA_GunShoot.cpp:267 prints them), health bar percent (first
  UMG ProgressBar inside the Burrower's `HealthBar` widget; `None` = not readable, information only).
* **(h) h_death** (server and client): after `KillAll`: `IsBurrowerDead()` true within 1 s (server) / 2.5 s (client);
  max displacement of `J0..J4` world positions >= 30 cm within 4 s (ragdoll moves the body); actor location moves <= 50 cm.
  Also the anim instance `bIsDead` delay and the mean bone drop. Notes `bUseMeshRagdollFallback` (C++ ragdoll vs rig).
* **(i) i_respawn**: per player a new Burrower (not seen before the kill) on the server `SpawnInterval` (-0.5/+2.5 s) after
  `KillAll`, and seen on the client.

## Config keys (bw_pie_config.json)

* `spawn_mode`: `spawnnow` (main: `bEnabled` off so only `SpawnNow` spawns; `FirstSpawnDelay` 4 <= `SpawnInterval` 8, so
  the respawn countdown after the kill is exactly SpawnInterval: the C++ re-arms with `max(Countdown, SpawnInterval)`,
  BurrowerSpawnSubsystem.cpp:147, 288, 421) or `auto` (variant). `spawn_indices`: `all` or a list of PlayerArray indexes.
* `settings`: values put on the `UBurrowerSettings` CDO in memory for the run (`bEnabled`, `FirstSpawnDelay`,
  `SpawnInterval`); `burrower_class_if_unset`; `allow_map_if_filtered` (adds the map to a non-empty `AllowedMaps`).
  `enable_before_kill`: sets `bEnabled` true right before `KillAll` so the respawn countdown runs.
* `timeline`: phase lengths (game s) and wall-clock limits (`*_wall_s`). In auto mode keep `warmup_s` < `FirstSpawnDelay`.
* `move`: player flight speed, heights (`follow_z` above the path, `cut_hover_z` above a tile top), `cut_ahead`.
* `sampling`: rates; `rotor_window_start` / `rotor_window_s` inside `follow`; `tile_track_radius`.
* `thresholds`: every PASS limit named above.
* `damage`: `fire_roles` (`["server"]`, add `"client"` to also fire from the client), aim bone, input action, fallback GE.
* `shots.plan`: `{phase, at, label, kinds}`; kinds `side` (body from the side), `rotor` (rotor close-up), `top`
  (rotor from above, for tiles), `player` (the player camera, which is turned toward its Burrower 1 s before).
  One render target per world, made once; a failed capture setup is not retried (leaked render targets crashed Vulkan
  before). `max_captures` caps the total. Scene captures are written as `<label>_<kind>_<role>.png`.
* `fixed_frame_rate`: 30 (UnrealEdEngine `bUseFixedFrameRate`/`FixedFrameRate`, restored after). `force_refresh_bones`.
* `match_enable`: 0 = CVar `Aura.Match.Enable 0` for the run (restored after, also by `bw_pie_cleanup.py`). The airship
  round 2 team match is on for StartupMap by default; with it a listen PIE waits for players, starts everyone on ship
  decks and the Burrower skips ship-borne players, so this test turns it off. `None` leaves the CVar alone.

## Turns variant (bw_pie_config_turns.json): path-follow bend and death momentum

For the 2026-11-22 fixes (the tail traces the head's path in yaw and pitch; the corpse keeps its velocity and turn).
Arm with `$H/inbox.sh pie $P/bw_pie_run_turns.py 120`, wait with `$P/bw_pie_wait.sh 2700`. Every switch below is off
in `BW_DEFAULTS`, so the main / auto / gun / crragdoll runs behave exactly as before (same phases, same checks a..i;
the only addition there is `o_no_attach_warning`, evaluated from the editor log in every config).

**`bw_pie_report.py` only lists a..i** (its order list is fixed): read j..m from the log or the JSON:
`grep -E '(PASS|FAIL|WARN): [jklm]_' /mnt/new_partition/UnrealProjects/_BurrowerWork/Saved/Burrower/pie_log.txt | tail -4`, or
`python3 -c "import json; d=json.load(open('/mnt/new_partition/UnrealProjects/_BurrowerWork/Saved/Burrower/pie_result.json')); [print(k, c['status'], c['summary']) for k, c in d['checks'].items()]"`.
`bw_pie_wait.sh` progress lines show every check's status. `e_tiles` / `g_damage` say `OFF` (not run; INFO, not a WARN).

Timeline: wait_pawns, warmup 14 s, spawn, **follow 18 s weaving**, then at the follow's end (b, c, d, f, j, k evaluated)
straight to **kill** (`KillAll` while the Burrowers fly at ~900-1400 cm/s; h, l, m, n after `ragdoll_s`, 5.5 s in this config), respawn (i).
No cut / damage phases. About 45 s of game time after the warmup.

Switches and keys (all in `BW_DEFAULTS`):

* `move.weave_y_amp` / `weave_y_period` (1500 cm / 9 s), `move.weave_z_amp` / `weave_z_period` (700 cm / 6 s): during
  follow each pawn flies along its lane's spline (the server's, as before) at `move.speed`, with the side offset
  `A sin(2 pi t / P)` from the spline (horizontal normal) and the height `centre + A sin(2 pi t / P)` above it; the pawn's
  wanted velocity is the offsets' rates plus `weave_gain` (1.5 /s) times their errors (so it really flies the weave, not
  a lagged copy of a moving carrot). `centre = max(follow_z, weave_z_floor + weave_z_amp)` (`weave_z_floor` 500 cm, the
  old safe lane height: the lowest point stays 5 m above the path, i.e. the lane runs 5..19 m above the path). The side
  part is capped so the speed stays within `weave_max_speed` (0 = auto: 1.15 x sqrt(speed^2 + peak side rate^2 + peak
  height rate^2), ~1800 cm/s); every copy of every player pawn gets that `MaxFlySpeed` during follow and `move.speed`
  again after (the analog input size sets the actual speed). `series.weave` in the JSON has wanted vs flown offsets at 2 Hz.
* `record_head_path`: every `sampling.path_dt` (0.03 = every frame at 30 fps) in spawn + follow, and every frame for
  `sampling.kill_track_s` (2.5 s) after `KillAll`: per Burrower on server and client, `J0..J4` world positions, actor
  location / velocity, mesh component world transform, the anim instance's `FollowYawDeg1..4`, `FollowPitchDeg1..4`,
  `DeathVelocity`, `DeathAngularVelocity`, `bIsDead`. Written to `Saved/Burrower/pie_headpath_<run>.json` (`columns` +
  one row per sample) at the kill evaluation and at the end. The frame a machine first sees a Burrower dead is its death
  frame (`death_t`, `death_base`).
* `kill_during_follow`: `KillAll` at the end of follow, no cut / damage. (h) then measures bones and actor from each
  machine's death frame (a client copy flies on until the death reaches it). Implies the recording.
* Property names: the anim instance values are read as `follow_yaw_deg1` (UE keeps a trailing digit on the word:
  CamelCaseBreakIterator.cpp:125-133), falling back to `follow_yaw_deg_1` and the C++ name `FollowYawDeg1` (an unmapped
  name falls through as the C++ name, PyWrapperObject.cpp:1223-1240). Missing (old C++): logged once, the dependent
  check reports WARN with its would-be verdict, never a crash. The character's `PathFollow*`, `bInheritVelocityOnDeath`,
  `DeathVelocityScale`, `bInheritTurnOnDeath` are read the same way (missing: the fixed-interface defaults are used).

The checks (server and client, every Burrower; numbers in `checks.<key>.data`):

* **(j) j_climb_dive**: eval samples every `path_eval_dt` 0.1 s of the follow with |pitch rate| > `j_pitch_rate_min` 8
  deg/s (rates from the MESH rotation over +-0.15 s, so client mesh smoothing is included). Head path = the recorded
  `J0_Head` positions back to the tail tip's arc length + `path_trail_margin_cm` 200 (~2.5 s at 900 cm/s; samples whose
  path is shorter than J4's arc length + 50 cm are skipped). For the bent `J4_Tail` and for a RIGID J4 (the mesh's current
  transform applied to J4's reference position) the offset from the nearest path point is split along the path
  normals; j uses the vertical part (k the sideways part), so a yaw bend cannot hide a rigid pitch. Metric
  `path_ratio_metric` `signed` (default): mean of the bent offset measured toward the side the rigid tail lies on,
  divided by the mean |rigid offset| (the body wave swings both ways and cancels; `abs` = mean |bent| / mean |rigid|, the
  literal reading, and `3d` are reported too and selectable). PASS per Burrower: ratio < `path_ratio_max` 0.6, and
  `FollowPitchDeg1..4` nonzero (max >= `follow_min_deg` 0.5) with the sign the trail prescribes in >= 70 %
  (`follow_sign_agree_min`) of the joint samples where that expected angle is >= `follow_sign_min_deg` 2. WARN when
  fewer than 10 turning samples (`path_min_samples`) or the rigid error is < 25 cm (`path_min_rigid_cm`: turns too
  gentle to judge), or only one machine had data.
  The expected angles are the fixed-interface formula run on the harness's own trail (`bw_follow_expected`: targets at
  the ref-pose arc lengths 340 / 740 / 1260 / 1560 / 2017 cm, segment directions in component space, global yaw / pitch
  vs the rest directions, local = difference to the previous segment, head segment = 0, x strength, clamped). Sign rule
  this gives (offline-tested): pitch rate > 0 (nose rising) -> the path behind lies ABOVE the backward head line ->
  `FollowPitchDeg` > 0 (tail lifted toward +Z); a right turn (yaw rate > 0, toward +Y) -> `FollowYawDeg` < 0. Also
  reported: per-joint mean |anim - expected|, joint 1's sign vs the rate, and `expected_straight_flight_deg`: the literal
  formula gives pitch about -1.0 / +1.0 / -0.4 / 0 deg in straight level flight (the reference chain is not straight).
* **(k) k_yaw_turn**: the same with |yaw rate| > `k_yaw_rate_min` 10 deg/s, the sideways part of the path error and
  `FollowYawDeg1..4`.
* **(l) l_death_momentum**: pre-death velocity = actor displacement over the last `death_pre_window_s` 0.3 s before
  `KillAll` (+ mean `GetVelocity()` for information); J2_Midbody's displacement over `death_window_s` 1.0 s from the
  machine's death frame. PASS: horizontal carry along the pre-death horizontal direction >= `death_carry_frac` 0.5 x
  |v_h| x 1 s, and the anim `DeathVelocity` (first nonzero value after death) within `death_vel_tol_frac` 25 % (vector
  error / |expected|) of `DeathVelocityScale` x the measured velocity, or of `DeathVelocityScale` x that machine's last
  `GetVelocity()` above 10 cm/s before its own death frame (what the C++ captures there: a client dies later and has
  turned meanwhile); zero expected when `bInheritVelocityOnDeath` is off. WARN: |v_h| < 300 cm/s (`death_min_speed`, not "at speed"). Reported: drop, sideways drift, angle and speed ratio
  of `DeathVelocity`, `DeathAngularVelocity` vs the measured rates (expected `(0, 0, yaw rate) - right x pitch rate`:
  a nose-up pitch rate is a NEGATIVE rotation about the actor's right axis, FRotator pitch +p = FQuat(+Y, -p),
  UnrealMath.cpp:532-535; a wrong sign is a WARN), and the corpse heading change (J0 - J4 horizontal) over the window
  vs `DeathAngularVelocity.z` x 1 s (opposite sign with >= 3 deg expected: WARN "does not keep curving"), and the
  Follow* values 1..2 s after death (should have faded to 0).
* **(m) m_stable**: no NaN / inf in any recorded sample (bones, transforms, anim values, also the ragdoll); max bone
  speed while alive < `stable_max_bone_speed` 6000 cm/s (from consecutive samples, the first 0.5 s after a Burrower
  appeared and gaps > 0.5 s skipped); server vs client `FollowYawDeg` / `FollowPitchDeg` (same player's Burrower, same
  frames, the client shifted by 0..`stable_sc_max_lag_s` 0.3 s, best lag reported): mean abs difference over the 8
  values < `stable_sc_max_diff_deg` 3 deg. Missing anim values: WARN (not compared); NaN or speed: FAIL.

Not verified (needs the editor): that the pawns really fly the weave near the hex path (`series.weave`; if they get
stuck on tall props raise `weave_z_floor`), how far the Burrowers lag a weaving player (b may fail in this variant;
it is not what this run is for), and the client mesh smoothing lag in m.

## Safety and cleanup

* Nothing is saved. In-memory only: `UBurrowerSettings` CDO (set with `PropertyAccessChangeNotifyMode.NEVER`, so no
  PostEditChange and no settings-section save), LevelEditorPlaySettings (net mode), UnrealEdEngine fixed frame rate, CVar
  `Aura.Burrower.DebugRotorBox`. All restored at the end; `pie_restore.json` lets `bw_pie_cleanup.py` restore after a crash
  of the script. The ini is changed only by `bw_ini_playmode.sh` with the editor closed.
* The level gets one `TEMP_BW_Capture` (SceneCapture2D) before Play (Python cannot spawn into a PIE world); it is removed
  when PIE has ended. Other `TEMP_` actors are listed, never touched.
* The user may press Play himself: the arm refuses if PIE already runs; the run watches the editor log for
  `Repeating last play command` (logged only by the toolbar's RepeatLastPlay, DebuggerCommands.cpp:1350; the test's own
  `editor_request_begin_play` does not log it) and for a restarted session (world real time going back). In both cases it
  finishes without stopping PIE.
* PIE ended by someone else: the run finishes (`PIE ended before the test finished`), unreached checks are `SKIP` (WARN).
* Never more than one run: arming again while a run is active prints `FAIL` and does nothing.

## When a check fails: first things to look at

* setup FAIL: only one world -> the ini / in-memory play settings did not apply (`bw_ini_playmode.sh show`, the `setup`
  data has `play_settings`); no second pawn even after the restart -> see `events` `restart_player_at_transform`.
* a FAIL with 0 Burrowers: log lines `LogBurrowerSpawn` in the report (class not set / not loading, "No Burrower spawns
  here: the GameMode is not an AMyGameMode with DA_MyEnemyCharacterClassInfo set", "run it on the server").
* c / d / f FAIL with the anim instance values moving: the Control Rig node in ABP_Burrower does not get the variables
  (pins not exposed / not bound: AnimBP task) or CR_Burrower's forwards solve misses a step. Bones missing are listed as
  `WARN ... bones missing on the mesh` when the Burrower is first seen.
* e FAIL with no rotor cut: `cut_diag` (`box_bottom_minus_tile_top` > 0 means the box stays above the tiles: lower
  `move.cut_hover_z`, check `FollowHeightOffset` on BP_Burrower); platforms not bridged yet (`bBridgesReady` gate) -> longer `warmup_s`.
* g WARN (fallback only): the gun did not hit: check `HitActor` lines, the Burrower mesh's Visibility response
  (BP_Burrower must keep the C++ collision), the aim bone. g FAIL: the GE did not apply either (ASC / attribute set).
* h FAIL bones did not move: `bUseMeshRagdollFallback` false and the rig ragdoll is not wired, or the mesh has no
  physics asset; actor moved: movement not stopped on death.
* i FAIL: `bRespawnAfterDeath` false, `bEnabled` not true at the kill (`settings_at_kill` in the data), class info missing.

## Not verified (could not be checked without running the editor)

* That `editor_request_begin_play()` picks up the in-memory net mode when the ini says otherwise (worked for the Mech
  Sentinel runs on this PC, `t_t2c_listen*.json`); the ini step makes it moot.
* That `PlayerState.get_pawn()` is set on the client for the other player's pawn (Pawn.cpp:647-665 says it is set in
  `OnRep_PlayerState`); the script also falls back to characters whose `player_state` is set.
* The camera aim reaching the Burrower's body through the 3rd-person boom (the old harness converged this way on
  sentinels); the aim bone is `J2_Midbody`. The GE fallback covers a miss.
* Vertical relation of the path spline to the tile tops: the hover point is taken from the tile instance positions
  (pillar pivot = top, hex_api.md 3), not from the spline, so this should not matter.
* That a SceneCapture2D's capture shows the debug rotor box lines (scene captures usually render line batchers).
* The HealthBar percent read (UMG ProgressBar found by walking outers); information only.
* `comp_xf` fallback (if `unreal.RelativeTransformSpace` were missing) keeps world rotations: the rotor twist would then
  be wrong. The clone's generated stub has `RelativeTransformSpace.RTS_COMPONENT`, so the fallback should never run.
