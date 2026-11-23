# Airship controls: PIE test protocol (as_50)

The PIE harness that measures the four control schemes (Classic, Galleon, Sky Racer, Point & Fly) in the editor with
the same maneuvers, bots and metric code as the bench in `sims/`, and makes the judging inputs (metrics next to the
sim predictions, per-frame telemetry, course videos, key-moment stills).

**Status:** written, not yet run in Unreal. Checked offline two ways (section 8): the protocol code reproduces every
value of the four `sims/<scheme>_metrics.json` files exactly when it drives the bench, and the whole editor-side harness
runs end to end against a mock `unreal` module whose world is the bench.

## 1. Files

| File | What it is |
|---|---|
| `Docs/Airship/scripts/ue/as_50_pie_controls.py` | The harness (editor inbox script): settings, TEMP actors, PIE, boarding, scheme switching, start poses, input injection, telemetry, captures, outputs |
| `Docs/Airship/scripts/ue/as_50_protocol.py` | The maneuvers, bot wiring and metric code, pure Python. `--selftest <scheme> [--lat100]` runs it against the bench |
| `Docs/Airship/scripts/ue/as_50s_status.py` | Inbox status (as_31 style) |
| `Docs/Airship/scripts/ue/as_50x_stop.py` | Inbox stop (as_32 style); with no run active it removes leftover `TEMP_AS50_*` actors |
| `Docs/Airship/scripts/harness/as_50_post.py` | After PIE, outside the editor: videos, contact sheets, the 2x2 video, compare.md |
| `Docs/Airship/scripts/ue/as_50t_mock_pie.py` | Test tool: runs the harness without Unreal (bench in place of the C++) |

## 2. Running it

Prerequisites: the C++ with the control-scheme CONTRACT built; the clone editor open on
`/Game/Assets/MyShip/Drivable/Maps/L_AirshipTest` with the Python inbox (`harness/launch.sh`); no PIE running. Keep the
editor on the visible i3 workspace: hidden, it runs at about 3 fps. Game time stays exact, but the wall time grows
about tenfold.

| Step | Command (from the clone root) |
|---|---|
| Start (standalone pass, lat0 values) | `Docs/Airship/scripts/harness/inbox.sh 50 Docs/Airship/scripts/ue/as_50_pie_controls.py 120` |
| Watch | `cat Saved/Airship/controls/status.txt` (rewritten every 2 s), or `inbox.sh 50s Docs/Airship/scripts/ue/as_50s_status.py 30` |
| Stop early | `inbox.sh 50x Docs/Airship/scripts/ue/as_50x_stop.py 30` (ends its PIE, restores, removes the TEMP actors, writes what it has) |
| Options | An inbox script that sets `AS50_CFG = {...}` and then `exec(open('<clone>/Docs/Airship/scripts/ue/as_50_pie_controls.py').read())` (each launch consumes `AS50_CFG`, so a later plain launch runs the defaults) |
| Listen pass (lat100 values, optional, after the standalone pass) | the same with `AS50_CFG = {'net': 'listen'}` |
| Post step by hand (normally started automatically after PIE) | `python3 -I Docs/Airship/scripts/harness/as_50_post.py [--keys galleon,skyracer] [--clean-frames]` |

`AS50_CFG` keys: `schemes` [0, 1, 2, 3] · `net` 'standalone' or 'listen' · `runs` (a list of run names, section 4;
the probe always runs) · `sloppy_repeats` 3 · `capture` True · `capture_every` 4 · `chase_res` (1280, 720) ·
`still_res` (1920, 1080) · `capture_skills` ('precise',) · `xgrab` False (HUD grabs: run `harness/xgrab_loop.sh
Saved/Airship/controls/xgrab` beside it) · `classic_crosscheck` False · `auto_post` True · `require_scheme` True.

**Expected run time** (game time = wall time while the editor holds 30 fps; mock-measured frame counts):

| Pass | Game time per scheme | Four schemes, wall |
|---|---|---|
| Standalone: 17 runs (probe, M1-M10 runs, the course 1 + 3 times, the orbit twice) | ~11 min | ~45-50 min (captures and writes add ~1 min per scheme) |
| Standalone with `sloppy_repeats` 1 | ~9 min | ~38 min |
| Listen (client pilot, Net PktLag 100 each way): 9 runs | ~8 min | ~32 min |
| Post step (ffmpeg / montage at nice 10, after PIE) | | 2-4 min |

What the run changes, all restored or removed at the end: UnrealEdEngine fixed frame rate 30; LevelEditorPlaySettings
(Standalone 1 player, or Listen Server 2 players, in memory); `BurrowerSettings.bEnabled` False; Net PktLag (listen); 47
`TEMP_AS50_*` actors in the editor level (2 scene captures, 11 gates of 4 meshes, the M12 target). The map is never
saved: it shows as modified, its content is unchanged. The user's own Play is detected in the log and never stopped.

## 3. What one pass does

1. **Arm:** checks (no PIE, the right map, memory, free disk), the in-memory settings, the TEMP actors, PIE requested.
   A Slate post-tick callback then runs one step per world frame. It ignores ticks without a new world frame (PIE
   paused) and logs skipped frames.
2. **Board once:** `Aura.Airship.Board` (listen: `Aura.Airship.Board 1`, the client; a fallback tries the other index).
3. **Per scheme id:** `Aura.Airship.Scheme <id>` on the server. It is confirmed 15 frames later by
   `GetControlScheme()` and the telemetry field `Scheme`. If neither matches, `SetControlScheme` is called from Python
   and checked again 30 frames later. Still unconfirmed, the scheme is skipped (`require_scheme`); a build without the
   contract can only measure Classic. Then `Aura.Airship.Telemetry` (the inertia line) and `Aura.Airship.Scheme`
   (print) are logged, and the runs of section 4 follow.
4. **End:** `Aura.Airship.Scheme 0`, then `Aura.Airship.Scheme check` (the Classic exactness test of
   `IMPLEMENTATION_PLAN.md` 7, which wants 0 differences). The lines go to `as50_result.json` `final_check`. PIE ends,
   the settings are restored, the TEMP actors removed, compare.md written, the post step started.

### 3.1 The start pose of every run

The bench starts every maneuver from a new `Sim`; PIE gets the same with a reset:

| Frame | Action |
|---|---|
| 0 | Teleport the hull (no sweep), zero its linear and angular velocity, set the control rotation (start yaw, the scheme's `CameraDefaultPitch`), inject `IA_AirshipBrake` for one frame (a brake press re-latches the altitude hold at the new height) |
| 1-4 | Zero the velocities again; camera set every frame of the reset |
| 2 | `Aura.Airship.Scheme <id>` again: scheme-local state reset (Galleon notch to STOP, Point & Fly heading target, Sky Racer drift). It waits 2 frames so the teleport and the zeroed velocity have gone through a physics step (`ResetSchemePilotState` sets Galleon's notch from the hull's live forward speed since the pre-build review; before, it read last frame's cosmetic speed and rang FULL again right after a cruise). Listen: it bounces through another scheme (frame 2) and back (frame 17), because a client gets `OnRep` only on a change |
| 30 | A second brake tap: re-latches the hold after the shaped lift has died away |
| 36+ | (Listen: 66+.) At rest (speed < 0.3 m/s, \|vz\| < 0.2, \|roll\| < 1.5 deg, \|pitch\| < 2 deg, \|yaw rate\| < 1 deg/s) or 3 s later (logged): the run starts. Its clock (`Ctx.time`) restarts at 0, like `Sim.time` |

Then each run does its own 2 s neutral settle, as `metrics.new_sim` does. Fuel is not reset; M2's boost is the first
boost of a scheme pass and its run warns if the tank is not full.

### 3.2 Where it flies (L_AirshipTest)

Over the 4 x 4 km ground block (top z -199.5 m), far from the obstacles (they are at x 350..1500 m, y -300..450 m and
13-60 m above z 0). Every run heads +X.

| Area | World point | Used by |
|---|---|---|
| lane | (-1200, -1500) m, actor origin 60 m above the ground | M1-M10 (up to ~1.6 km along +X) |
| course | (-600, -1000) m, 30 m above the ground | M11 (the gates of `course.GATES` from this origin) |
| orbit | target (1400, -1000) m at 60 m; the ship starts 100 m to its +Y side | M12 |

Gates (TEMP, `NoCollision`, so the ship's ground traces and the camera ignore them): two posts 1.5 m thick from the
ground to the top of the 40 x 25 m frame, a 1 m top bar, and a thin sill bar at the bottom of the frame. They are
yellow (`/Engine/EditorMaterials/WidgetMaterial_Current`); during the captured course run the next gate turns green,
passed gates blue and missed gates red. The M12 target is a 6 m radius sphere (`BlockAll`, so the camera's aim trace,
`ComputeLocalAimPoint`, hits it as the bench's `aim_targets` does).

### 3.3 Inputs

Inputs go through Enhanced Input injection on the pilot's local player
(`inject_input_vector_for_action`, one frame per call, injected in the post-tick of frame N and used in frame N+1) and
the PlayerController's control rotation. `DebugSetInput` is used only by the optional Classic cross-check.

| Bench `RawInput` | PIE |
|---|---|
| throttle, steer, lift, strafe | `IA_AirshipThrottle` / `Steer` / `Lift` / `Strafe` = the value, every frame it is non-zero |
| boost, brake, aim | `IA_AirshipBoost` / `Brake` / `Aim` = 1 every frame held |
| fire | `IA_AirshipFire` on alternate frames while held (it is bound on Started; the C++ ignores presses while reloading) |
| cam_yaw / cam_pitch | `set_control_rotation(Rotator(0, pitch, yaw))`, absolute, on the frames the bench sets them |
| look | Classic, Galleon, Sky Racer: also `IA_AirshipLook` (0.01, 0), which stamps `LastLookInputTime` (no recentre against the set camera). Point & Fly: never, so the set is the absolute heading set (`SCHEME_POINTFLY.md` 13; the C++ external-set rule is `LookDelta != 0 && LastLookInputFrame != GFrameCounter`) |

### 3.4 Bots and scheme adapters

Unchanged bench code (`course.Bot`, `CoursePlanner`, `GateJudge`, `metrics.OrbitPlanner`, each scheme's
`command_raw` / `intent_raw`). It runs behind `as_50_protocol.Ctx`, which has the attributes they read
(`IMPLEMENTATION_PLAN.md` 5.3):

| Attribute | PIE source |
|---|---|
| `P`, `PP`, `scheme` | the bench presets (`FLIGHT_DEFAULTS` / `PAWN_DEFAULTS` + the scheme's), the bench scheme |
| `time`, `dt` | frames since the run's start pose x 1/30 (so the sloppy bot's noise redraws at the bench's times) |
| `pilot_view()` | the pilot machine's `GetFlightTelemetry` (standalone: the ship; listen: the client's copy) + `ActorLocCm`, `VelCm`, `CourseDeg`, `ForwardSpeed` |
| `camera_location_m()` | the pilot's PlayerCameraManager location |
| `rmax_deg`, `hold_throttle`, `top_speed_estimate` | the bench's `Sim` methods on these presets |
| Galleon `pilot_state['order']` | the pilot's `ThrottleOrder` (-1 → ASTERN, else round(3 v)); without the field, the notch is counted from the taps |
| Sky Racer `pilot_fm.sky_drift_dir` | the pilot's `DriftDir` (without it: sign(Steer) while `bDrifting`) |
| Point & Fly `pilot_state` | never holds `'H'`, so `mouse_to_heading` returns the wanted heading (an absolute set) |

Seeds as the bench uses them: the sloppy bot uses 7 on the course and 11 on the orbit. The wind phase is the ship's
`GetUniqueID() % 97` and the world time, not the bench's seeds 1 / 7 / 3.

## 4. Runs and metrics

All definitions are `sims/README.md` "Metric definitions" and the code of `sims/metrics.py` / `course.py`, ported 1:1
(the same expressions and frame counts). `meta` keeps the details of every run.

| Run | What | Gives |
|---|---|---|
| probe | throttle +1 for up to 12 frames: the shaped throttle on the pilot's machine must move | aborts the scheme if the input path is dead |
| m1_m2 | start, 20 s full forward, then 6 s forward + boost | M1, M2, M6 (drive, top, boost), M10 throttle (its first 2 s) |
| m3_brake | cruise (start + 20 s forward), brake 8 s | M3 (all but coast), M6 brake flare |
| m3_coast | cruise, nothing held 40 s | M3 coast_half_s |
| m4_m5 | cruise, forward + full steer for 8 s or until 180 deg (at most 20 s) | M4 (first 8 s), M5, M10 steer (first 3 s): the bench flies all three from the same cruise and command |
| m7_climb, m7_sink, m7_step | full lift 5 s; full sink 5 s; lift to +30 m, then 6 s neutral | M7 |
| m8_hover, m8_cruise | full strafe 4 s from the start; the same at cruise with forward held | M8 |
| m9 | cruise, drift 3 s (each scheme's own drift: Classic X + D, Galleon swing, Sky Racer X + D, Point & Fly X + camera), then forward 3 s | M9 |
| m11_precise, m11_sloppy | the gate course from the course start (30 m), timeout 200 s | M11 precise / sloppy lat0 |
| m11_sloppy_r2, _r3 | the sloppy course again (`sloppy_repeats`) | `meta.repeats` (not the M11 keys) |
| m12_precise, m12_sloppy | 2 s settle, 15 s run-in, 60 s measured broadside orbit | M12 precise / sloppy lat0 |
| xcheck_debug (optional, Classic) | M1 drive and M4 turn through `DebugSetInput` | `meta.xcheck` (a difference points at the input path) |
| listen pass: m10_steer_lat100, m10_thr_lat100, m11_*_lat100, m12_*_lat100 | the same runs with the client piloting at 100 ms each way | the lat100 keys of M10-M12 |

PIE-specific rules (the only places where PIE and the bench measure differently):

* **Time zero** of a segment = the first frame whose shaped controls on the pilot's machine (telemetry Throttle, Steer,
  Lift, Strafe, Boost, bBraking, bDrifting, ThrottleOrder) change, counted from the first frame whose raw input changes.
  The frames in between are the input path's delay and are taken out of the log (0 expected in standalone). Frames
  that an adapter spends before its raw input changes stay, as in the bench (Galleon's release frame between taps).
  The delay per segment is in `meta.runs.<run>.k0`.
* **M2 boost_duration_s:** the server's boost latch is not in the telemetry. It is taken from the fuel: active in frame
  k if the fuel after frame k-1 is above 0 (and above `BoostMinFuelToStart` before the first frame). This is the latch
  rule of `UpdateBoostServer`.
* **M9 server_kick_ms:** null (the impulse is not readable).
* **M11 ground_contacts:** frames where `GroundClearanceM` (nozzle exits to the ground) drops below 0.25 m. Hull hits
  (health drops) are logged separately (`meta.hull_hits`).
* **M12 shots_fired:** cannonballs that appear on the server, / 2. Fire presses are on alternate frames (at most one
  frame later than the bench).
* **M12 cannon arcs:** the bench's rest muzzle positions and directions on the hull's actor transform.

## 5. Judging inputs (outputs)

Everything is under `Saved/Airship/controls/`:

| Path | What |
|---|---|
| `compare.md` | Every metric for every scheme, as **PIE (sim)**, with `!` where PIE is more than 15 % (and 0.5) off the sim, each metric's target band, run notes (failures, input delay, warnings, sloppy repeats, inertia line, media) |
| `<scheme>/metrics.json` | `meta` + M1..M12 with the sims' keys (`meta.source` = 'pie'; unmeasured = null). `meta`: runs (status, frames, game / wall s, k0, warnings, gate results), scheme_confirm, telemetry_missing, repeats, shared (the unrounded top speed and turn rate for the listen pass), inertia_log, media |
| `<scheme>/telemetry.json` (`telemetry_lat100.json`) | Every frame of every run: the server telemetry with all CONTRACT and extra fields, location, velocity, raw inputs, control rotation, camera location, rig cosmetics (WheelAngleDeg, TurbineYawDeg_L/R, NozzlePitchDeg_FL/RR, RudderDeg, ThrustAlpha_FL, NozzleFlareDeg_FL), aim side, shots. Listen: the client copy's telemetry too. About 16 MB per scheme |
| `<scheme>/chase/chase_NNNNN.png`, `frames.json` | The precise bot's course run from the pilot's camera, every 4th frame (7.5 fps), with time, speed, height, next gate, drift / boost / turbo per frame |
| `<scheme>/stills/NN_<moment>_pilot.png`, `_wide.png` | Start, slalom (S3), drift / boost moment (the first drift, boost or turbo; else the hardest turn after S5, `drift_boost_none` if none before H2), hairpin apex (H1), climb, finish, broadside (M12): the pilot's view and a wide view from behind and above |
| `<scheme>/course_<scheme>.mp4`, `contact_<scheme>.png`, `stills_<scheme>.png` | After the post step: the course video in real time with the labels burned in, ~30 frames on one sheet, the stills on one sheet |
| `compare_course_2x2.mp4` | The four course videos side by side (shorter runs hold their last frame) |
| `status.txt`, `as50_log.txt`, `as50_result.json`, `post_log.txt` | Live status, every log line, the run summary (errors, the final `Scheme check` lines, the log scan) |

The scene captures show the world, not the HUD (Slate). For the HUD of each scheme, set `xgrab` and run
`xgrab_loop.sh` beside the harness: it grabs the editor window at the still moments.

## 6. Robustness

| Case | What happens |
|---|---|
| A run raises or exceeds its time-out (1.3 x its nominal game time + 10 s; the course 205 s; or a wall-clock limit) | The run is marked failed with the traceback in `meta.runs`; the next run starts from a fresh start pose |
| The probe fails, or the scheme cannot be confirmed | The scheme is skipped (its `metrics.json` says why); the next scheme starts |
| The pilot no longer possesses the ship at a run start | `Aura.Airship.Board` again |
| The ship dies, PIE ends, the user presses Play, 300 script errors, 4 h wall | The pass is stopped. The finished runs of the current scheme are written, then the end sequence runs |
| End sequence | Ends its own PIE (asks again every 5 s, up to 120 s), restores the settings, removes the TEMP actors once PIE is gone, writes compare.md, starts the post step. If PIE will not end, `as_50x_stop.py` after PIE removes the TEMP actors |
| Status | `status.txt` every 2 s: phase, scheme, run, game / wall time, real fps (warns under 12), ETA, errors, the last lines |

## 7. Assumptions and limits

* **CONTRACT details assumed:** the telemetry field names exactly as `IMPLEMENTATION_PLAN.md` 1.5 (contract plus the
  extras DriftDir, DriftTier, TurboAlpha, TurboChain, bGunDeck, bGunLock; the build in progress matches). The Python
  enum names CLASSIC, GALLEON, SKY_RACER, POINT_FLY (compared without underscores). `Aura.Airship.Scheme <id>`
  re-applies the same scheme on the server. Any missing field is logged once and read with a default
  (`meta.telemetry_missing`).
* **Sloppy bot noise:** the bench's sloppy bot misses 1-3 gates on Classic and 0-1 on Galleon with only the wind phase
  changed (5 phases); in the mock, Classic's first sloppy run missed 4 and its two repeats 1 each. That is why the
  sloppy course runs 3 times. Judge on the median that compare.md prints in the run notes, not on one run (the M11
  sloppy keys hold the first run, the same single sample the sims hold).
* **Client view:** the bench has no physics-replication smoothing on the client copy; PIE showed 0-2 frames more on a
  client's screen (`sims/README.md`).
* **Inertia:** all pitch and roll numbers of the three new schemes assume base fix 4a-1. Read the inertia line
  (`meta.inertia_log`) before judging them (`IMPLEMENTATION_PLAN.md` 5.4, 8).
* **Listen pass:** the play settings are set in memory (as as_30 does for Standalone). If no client world appears, use
  `harness/set_play_mode.sh listen 2` with the editor closed. Net PktLag is real time and is scaled by the measured real
  fps (as as_45). Captures are off in this pass: a capture stalls the frame and bunches the lagged packets.
* **Not covered here:** deck riders, HUD contents, feedback (shake, FOV kicks, rumble) and the scheme-only checks of
  `IMPLEMENTATION_PLAN.md` 5.4 (Galleon telegraph timing, Sky Racer tier against HUD, Point & Fly camera steps). Those
  values are in `telemetry.json` for checking afterwards.

## 8. How the harness was checked (without Unreal)

| Check | Command | Result (2026-11-23) |
|---|---|---|
| The protocol on the bench, host | `python3 Docs/Airship/scripts/ue/as_50_protocol.py --selftest classic` (each scheme, one process at a time) | All four schemes: every lat0 value of `<scheme>_metrics.json` reproduced exactly (0 differences), about 4 s each |
| The protocol on the bench, client 100 ms | `... --selftest --lat100 <scheme>` | All four schemes: every lat100 value reproduced exactly |
| The whole harness, mock editor | `python3 Docs/Airship/scripts/ue/as_50t_mock_pie.py --schemes 0,1,2,3 --post` | 4 x 17 runs OK, 0 script errors, settings restored, 0 TEMP actors left, every output written incl. the videos, sheets and the 2x2 video; precise-bot and maneuver values within a frame or 0.5 % of the sims |
| The listen pass, mock editor | `... --schemes 1` then `... --schemes 1 --listen --keep` | 9 / 9 runs OK, lat100 merged into the standalone metrics.json; M10 lat100 equal to the sim |

The mock checks the plumbing: state machine, resets, injection mapping, files. It cannot check the engine side: the
real `unreal` API calls, the C++ scheme code, physics replication.
