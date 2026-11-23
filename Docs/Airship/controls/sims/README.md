# Airship controls: offline test bench

This folder holds the shared offline bench for the control-scheme iterations (Classic, Galleon, Sky Racer, Point &
Fly). It is a Python port of the airship as it is in the C++ today (clone `_AirshipWork`, branch
`claude/project-thread-0emzt1`, commit 8f01bca). It covers the flight model, the Chaos rigid body it runs on, the
pilot's input path over the network, the camera and the cannon arcs. On top of that it has a plug-in point for
control schemes, standard maneuvers M1-M12 and a gate course flown by two bots.

`BASELINE_METRICS.md` has the Classic (v1) results and the calibration against PIE. `../BASELINE.md` (a separate
thread) is the code reference for v1 and proposes base fixes; its own port is `baseline_sim.py` /
`baseline_checks.py` in this folder. The two ports agree on the main finding (Finding 1 below).

## Files

| File | What it is |
|---|---|
| `airship_sim.py` | The bench: `Sim` (pilot's machine + network + server), `FlightModel` (a line-by-line port of `UAirshipFlightComponent`), `Body` (the Chaos step), `Scheme` / `Classic` (the plug-in API), `Command` / `Intent` (what maneuvers and bots ask for), `RawInput` / `PilotInput` (keys and the RPC payload) |
| `metrics.py` | Maneuvers and metrics M1-M12. Writes `<scheme>_metrics.json` |
| `course.py` | The gate course (M11), the racing-line planner, the bots (precise and sloppy human), `--tune` for a scheme's bot gains |
| `calibrate.py` | Replays the PIE runs and tables sim against PIE. Writes `calibration.json` |
| `mass_props.py` | Mass, centre of mass and inertia of the hull, worked out the way Chaos does it from the 8 UCX convexes. Writes `hull_mass.json` |
| `pie_ref.py`, `pie_ref.json` | The PIE reference data, extracted from the git-ignored `Saved/Airship` results |
| `scheme_template.py` | A scheme module to copy. Unchanged, it equals Classic, which makes it a self-test of the plug-in path |
| `compare.py` | Prints several `<scheme>_metrics.json` side by side |
| `classic_metrics.json`, `calibration.json`, `hull_mass.json` | Generated outputs (committed so they can be diffed) |

## Running

Python 3.8 or newer, standard library only (numpy is not used). Run one process at a time. Each command finishes in
seconds to about a minute.

```
cd Docs/Airship/controls/sims
python3 metrics.py classic               # M1-M12 -> classic_metrics.json (about 6 s)
python3 course.py classic                # gate course: precise/sloppy bot x 0/100 ms (about 6 s)
python3 course.py classic --tune         # bot gains for a scheme (about 1 min)
python3 calibrate.py                     # sim against PIE -> calibration.json (about 8 s)
python3 compare.py classic galleon       # side by side
python3 mass_props.py                    # regenerate hull_mass.json (< 1 s)
python3 airship_sim.py                   # smoke run: hover, then full throttle
```

Minimal use from Python:

```python
from airship_sim import Sim, Classic, Command, RawInput, run_commands, run_raw
sim = Sim(Classic(), latency_ms=0)                       # pilot = listen-server host
log = run_commands(sim, lambda t, s: Command(thrust=1.0), 10.0)
print(log[-1]['ForwardSpeedMS'], log[-1]['PitchDeg'])
sim = Sim(Classic(), latency_ms=100)                     # pilot = client, 100 ms each way
log = run_raw(sim, lambda t, s: RawInput(throttle=1.0, steer=1.0 if t > 1 else 0.0), 5.0)
print(log[-1]['pilot']['screen']['YawRateDegS'])         # what the client's screen shows
```

`Sim(scheme, latency_ms=0, alt_agl=30, yaw_deg=0, pos_m=(0, 0), seed=1, wind=True, ground_fn=None, flight=None,
pawn=None, ctrl_inertia=None, net=None)`:

* `latency_ms` 0 puts the pilot on the listen-server host: no RPC, like the standalone PIE runs.
* `latency_ms` above 0 makes the pilot a client. The input reaches the server 1 frame plus the latency later. This
  is the frame order of a one-process PIE.
* `net='client'` with `latency_ms=0` gives a client with no lag.
* `ground_fn(x_cm, y_cm)` returns the ground height (cm). The default is flat ground at z = 0.
* `flight` / `pawn` are extra property overrides on top of the scheme's own.
* `seed` is the wind phase. In the C++ it is `GetUniqueID() % 97`.

`sim.step(raw)` runs one frame and returns its record:

* the server's telemetry: the `FAirshipFlightTelemetry` names plus `ActorLocCm`, `VelCm`, `CourseDeg`, `Debug`;
* `pilot`: `view` (the ship state the pilot's logic sees), `screen` (what the pilot's screen shows at the end of
  the frame), the camera yaw/pitch, the pilot's own shaped Steer/Throttle, and the cosmetics `TurbineYawDeg`,
  `WheelAngleDeg`, `NozzlePitchDeg`;
* `raw` and `input`: the keys, and the `FAirshipPilotInput` that was sent;
* `ground_contact`.

## How one frame runs (30 fps, the order in the C++)

1. **Pilot's machine.** `Scheme.camera` (control rotation, recentering, spring-arm rotation lag), then
   `Scheme.pilot_input` (keys + camera + its view of the ship -> `FAirshipPilotInput`, int8 axes), then the local
   shaping for the cosmetics, then the send.
2. **Server.** Receive the input (newest Seq; neutral after 0.5 s) -> `UpdateBoostServer` -> `Scheme.server_controls`
   -> `ShapeControls` (with `Scheme.shaping_targets`) -> `TraceGround` -> `ApplyForces` (with `Scheme.server_commands`
   before the allocation and `Scheme.server_forces` after it) -> cannon fire and recoil -> Chaos step.
3. **Anim instance.** Turbine housing slew (40 deg/s) and the wheel spring on the pilot's machine.

On a client pilot the server runs first and the pilot second, as in a one-process PIE. The pilot sees the server's
state `latency` old. The engine's physics-replication smoothing of the client's copy is not modelled; PIE showed
0-2 frames more than the sim (`BASELINE_METRICS.md`).

## Adding a scheme

1. Copy `scheme_template.py` to `scheme_<key>.py` (`galleon`, `skyracer`, `pointfly`). Give the class
   `@register_scheme`, and set `key`, `enum` (the contract's `EAirshipControlScheme` value) and `label`.
2. **Preset table.** Set `flight = {...}` (names and C++ units of `airship_sim.FLIGHT_DEFAULTS`, which are the
   `AirshipFlightComponent.h` defaults) and `pawn = {...}` (`PAWN_DEFAULTS`: camera, cannons, anim). Anything not
   listed stays at the v1 value, so Classic = no overrides.
3. **Pilot side (a).** Override `pilot_input(sim, raw, cam, view, dt) -> PilotInput`. This is where a telegraph's
   engine order, a heading target or camera-to-steer goes.
   * Keep runtime state in `sim.pilot_state`. `reset(sim)` clears it on a switch and on board/exit.
   * Extra RPC fields go in `ext_fields = {name: (bits, scale, signed)}`; fill them with `quantize_ext`.
4. **Server side (b).**
   * `server_controls(sim, controls, dt)`: rewrite the controls before they replicate. Example: Steer derived from
     a heading target and the authoritative heading, so every machine's cosmetics follow.
   * `shaping_targets(sim, fm, controls, targets, fwd_speed)`: change the filter targets on every machine.
   * `server_commands(sim, fm, cmd)`: edit the commands before the allocation: `AFanCmd`, `ADrag`, `ABrake`,
     `VzCmd`, `BankDeg`, `PitchExtraDeg`, `YawRateCmd`, `Klat`, `ALatMax`, `Eta`, `VlTarget`.
   * `server_forces(sim, fm, cmd, out)`: add exact accelerations to `out['ACom']` / `out['AlphaCom']`.
   * Server state lives in `sim.server_state`. The ship is `sim.body` and `sim.tele()`; the flight model is `fm`
     (shaped values `fm.sh_*`, hold `fm.hold_z`, fuel `fm.fuel`, ...).
5. **Camera (c).** Override `camera(sim, raw, cam, view, dt)` if the camera works differently: set
   `cam.control_yaw/pitch` and `cam.free_look`, then call `self.camera_lag(...)`.
6. **Telemetry.** `telemetry(sim, tele)` fills the contract fields `Scheme`, `ThrottleOrder` (-2 = none),
   `DriftCharge`, `bHeadingTargetActive`, `HeadingTargetDeg`, `bFreeLook`.
7. **Adapters (bench only).**
   * `command_raw(sim, Command)`: turn a maneuver into your scheme's raw inputs. Example: "full forward" on a
     telegraph = tap W until full ahead.
   * `intent_raw(sim, Intent, view, gains)`: turn a goal (course, speed, height, look point) into raw inputs.
   * `KEY_AXES` lists which raw axes are keyboard keys (the sloppy bot plays them on/off).
8. **Bot gains.** Run `python3 course.py <key> --tune` and paste the result into `GAINS`. Every scheme gets the same
   sweep and score, so the precise bot flies each scheme as well as that scheme allows.
9. **Run it.** `python3 metrics.py <key>`, then `python3 compare.py classic <key>`.

To model the inertia fix (Finding 1), set `ctrl_inertia = 'hull'` on the class. It needs that C++ change.

## Metric definitions (the PIE harness ports these 1:1)

Common rules:

* **Frame rate.** Fixed 30 fps. Telemetry is read once per frame after the physics step and after the anim update:
  `GetFlightTelemetry` on the server's ship; cosmetics and the screen on the pilot's machine.
* **Time zero.** Times count from the first frame in which the pilot's machine uses the new input. In the PIE
  harnesses that frame is one frame after the `inject_input_for_action` / `DebugSetInput` call. Find it as the first
  frame where the pilot's own `FAirshipPilotInput` changes.
* **Start.** Hover at rest, level, heading +X, 60 m above the ground, with nothing within 600 m. Hold neutral
  controls for 2 s first.
* **Cruise.** From that start, 20 s of full forward drive.
* **Inputs.** Every maneuver goes through the scheme's own controls (`command_raw`). Speeds are `ForwardSpeedMS`,
  `LateralSpeedMS`, `VerticalSpeedMS`.
* **Network.** M1-M9: host pilot. M10-M12: host, and a client with 100 ms each way (`Net PktLag=100`).

| Key | Maneuver | Sub-keys |
|---|---|---|
| M1 | From the start, full forward for 20 s. | `t80_s`, `t63_s` (first time ForwardSpeed reaches 80 % / 63 % of M2 `top_steady_ms`), `speed_at_2s_ms`, `speed_at_4s_ms` |
| M2 | The M1 run, then from its end hold boost + forward for 6 s. | `top_steady_ms` (mean of 17-20 s), `top_peak_ms`, `boost_peak_ms`, `boost_ratio` (peak / steady top), `boost_duration_s` (until the server's boost latch drops = fuel gone), `boost_t90_s` (90 % of the speed gain) |
| M3 | From cruise, brake for 8 s. Separate run: from cruise, nothing held for 40 s. | `start_speed_ms`, `stop_time_s` (first frame at or below 0.5 m/s), `stop_distance_m` (along the start heading), `half_speed_s`, `peak_decel_g` (max of the 3-frame central difference / 9.81), `mean_decel_g` (start speed / stop time / 9.81), `alt_rise_m`, `coast_half_s` (coast run) |
| M4 | From cruise, forward + full steer right for 8 s. | `final_yaw_rate_degs` (mean of YawRateDegS over 6-8 s), `t63_s`, `t90_s`, `overshoot_pct` ((max - final) / final), `bank_deg` (mean roll 6-8 s), `slip_8s_deg` (atan2(-lateral, forward)), `speed_8s_ms`, `alt_loss_8s_m`, `pitch_min_deg` |
| M5 | From cruise, forward + full steer until the unwrapped yaw change reaches 180 deg. | `time_s`, `diameter_m` (actor offset across the start heading at that frame), `speed_end_ms`, `speed_kept_pct` |
| M6 | Taken from the M1, M2 and M3 runs. | `drive_pitch_min_deg` (M1), `top_pitch_deg` (mean 17-20 s), `drive_alt_dip_m` (M1), `boost_pitch_min_deg` (M2 boost part), `brake_pitch_max_deg` (M3 brake run) |
| M7 | Climb: from the start, full lift for 5 s. Sink: full negative lift for 5 s. Step: hold full lift until the altitude is 30 m above the start, then release, then neutral for 6 s. | `climb_rate_ms`, `sink_rate_ms`, `step30_rise_s` (press to release), `step30_overshoot_m` (max altitude after the release minus the +30 m target), `step30_vz_1s_ms` / `step30_vz_2s_ms` (\|vz\| 1 s / 2 s after the release), `step30_error_5s_m` |
| M8 | From the start, full strafe right for 4 s. Separate run: the same from cruise with forward held. | `t90_s` (90 % of `strafe_speed_ms`), `strafe_speed_ms` (mean 3-4 s), `strafe_speed_cruise_ms` |
| M9 | From cruise, a drift (Classic: brake + full steer, forward held) for 3 s, then forward only for 3 s. | `slip_1s_deg`, `slip_2s_deg`, `slip_3s_deg`, `drift_frames_pct` (frames with bDrifting), `yaw_rate_degs` (mean 1-3 s), `speed_kept_pct` (speed at 3 s / start), `exit_kick_ms` (ForwardSpeed 2 frames after the first non-drifting frame minus 1 frame before it), `server_kick_ms` (sim only: the impulse paid) |
| M10 | `lat0` / `lat100`. Steer: from cruise, forward + full steer. Throttle: from the start, forward. Frames are counted from time zero. | `turbine_frames` (TurbineYawDeg_L on the pilot's machine changes by more than 0.5 deg), `wheel_frames` (WheelAngleDeg, more than 2 deg), `server_turn_frames` (server YawRateDegS rises by more than 10 % of M4 final), `screen_turn_frames` (the same on the pilot's screen), `nozzle_frames` (NozzlePitchDeg_FL, more than 0.2 deg), `screen_speed_frames` (pilot's screen ForwardSpeed rises by more than 0.1 m/s) |
| M11 | `course.py`, for `precise` / `sloppy` x `lat0` / `lat100`. | `completion_time_s`, `finished`, `gates_total`, `gates_missed`, `missed_gates`, `miss_mean_m`, `miss_max_m` (distance from the gate centre in the gate plane), `outside_max_m` (how far outside the frame), `line_error_mean_m`, `line_error_max_m` (from the bot's racing line at the gate), `steer_reversals_per_min` (sign changes of the raw steer, \|steer\| above 0.1), `camera_reversals_per_min` (look input only), `ground_contacts` |
| M12 | Target fixed at the ship's start height; the ship starts 100 m off its port beam (target at (0, 0), ship at (0, +100 m), heading +X). 2 s settle, 15 s run-in, then 60 s measured. The bot keeps the target abeam at 100 m and 60 % of top speed, looks at it, and presses fire whenever it has a solution. `precise` / `sloppy` x `lat0` / `lat100`. | `in_arc_pct` (at least one port cannon: \|yaw from its rest direction\| <= 20 deg and elevation -10..+8.5 deg, hull frame, from its muzzle), `in_arc_both_pct`, `in_range_pct` (80-120 m from the actor), `speed_ok_pct` (ForwardSpeed >= 50 % of top), `camera_port_pct` (the camera-facing side = port), `firing_solution_pct` (all four), `shots_fired` (broadsides), `range_mean_m`, `beam_yaw_mean_deg`, `elev_mean_deg`, `elev_max_deg` |

`meta` holds `scheme`, `scheme_enum`, `label` and `source` (`sim` or `pie`), plus run details. The PIE harness
writes the same keys. A key it cannot measure stays present with `null`.

Notes for the PIE port:

* **Moving start.** Chain the runs from one cruise where you can: 20 s of forward, then M3 or M4. The definitions
  only need a level, steady cruise at the start.
* **M12 target.** Place an actor with a Visibility-blocking collision (a 6 m sphere) at the target, so the
  camera's aim trace returns it (`ComputeLocalAimPoint`). The bench treats the target as a 6 m sphere for the aim
  ray.
* **M11 bots.** `course.py`'s `CoursePath`, `CoursePlanner`, `Bot` and the scheme adapters are plain Python and only
  read telemetry. The editor's Python can import them behind a small object that has the Sim's attributes (`time`,
  `pilot_view()`, `scheme`, `P`, `rmax_deg`, `top_speed_estimate`) and injects the resulting RawInput.
* **Camera.** `RawInput.cam_yaw` / `cam_pitch` is the control rotation the harness sets. `look=True` marks frames
  where the harness also fires IA_AirshipLook. In Classic, a control rotation set without look input is pulled back
  behind the ship after 1.5 s.

## Fun notes and target bands

`metrics.METRIC_INFO` has the one-line "why it matters for fun" and the band I would aim for with a 52 m, 40 t
action-game ship. `BASELINE_METRICS.md` lists them next to Classic's numbers. Designers pick their own targets.

## How the mass properties were estimated (`mass_props.py`)

The C++ sets only the mass and the centre of mass. The inertia is whatever Chaos derives from the hull's 8 UCX
convexes (`ApplyBodySettings`: `SetMassOverrideInKg(40000)`, then `SetCenterOfMass` so the COM lands on
`DesiredCenterOfMass` (-170, 0, 0)). The script follows the engine's own path (source read in
`/mnt/new_partition/5.8`):

1. **Hulls.** Each UCX element's vertices (`Docs/Airship/sims/fix2/ucx.json`, Blender metres) go to UE hull space
   (100x, -100y, 100z cm). The convex hull is rebuilt from them, as UE builds `FKConvexElem` / `FConvex` from the
   vertices.
2. **Per convex.** Volume, centre and inertia come from Chaos's own surface integrals at uniform density
   (`CalculateVolumeAndCenterOfMassImpl`, `CalculateInertiaAndRotationOfMassImpl`).
3. **Combined.** `CombineWorldSpace` adds the parallel-axis terms. The natural centre of mass is (-8, 3, 97) cm.
4. **Mass override.** `ApplyMassPropertiesModifiers` scales the inertia to 40 t, moves the COM by the nudge
   (-162, -3, -97) cm, and (with `p.ComNudgeAffectsInertia`, on by default) adds m·d² of the nudge to the diagonal
   only, as the engine does.
5. **Diagonalized.** `TransformToLocalSpace` returns the principal values in the order (largest, smallest, middle).

Results (kg cm^2):

| | Value |
|---|---|
| True tensor in hull axes, diagonal | (1.205, 6.575, 6.753) e10 |
| Ixz | -7.7e9 (the principal yaw axis tilts 7.8 deg) |
| `GetInertiaTensor()` | (6.86, 1.10, 6.57) e10 |

The research estimate, a 52 x 24 x 17 m box, was (1.73, 5.99, 6.56) e10.

## Findings from the calibration (for the designers and the implementer)

1. **The flight controller uses the wrong inertia axes.** `ApplyForces` reads `Body->GetInertiaTensor()` and uses X,
   Y, Z as the hull's roll, pitch and yaw moments. Chaos returns the principal moments in the order of its eigen
   solver: largest, smallest, middle (`Chaos::TransformToLocalSpace`, `MassProperties.cpp`). For this hull that is
   (6.86, 1.10, 6.57) e10 kg cm^2, about (yaw, roll, pitch). The true hull-axis diagonal is (1.21, 6.57, 6.75) e10.
   * The pitch loop therefore runs about 6 times too soft, and the roll loop about 5.7 times too stiff.
   * The sim reproduces PIE only with this error in place: the -16.5 deg nose dip, the -17.5 deg dip on boost, the
     slow pitch recovery with a +1.7 deg overshoot, and a pitch wobble at hover (0.6-0.9 deg) far larger than the
     roll wobble (0.02-0.04 deg).
   * With the fix (`ctrl_inertia='hull'`) the full-throttle dip is -9.3 deg: the -8 deg target plus the fans'
     torque.
   * The fix: in `ApplyForces`, rebuild the hull-axis tensor from the principal moments and the body's
     RotationOfMass, then take the torques from it. `../BASELINE.md` 4a came to the same conclusion independently.
   * Log `GetInertiaTensor()` once in PIE to confirm it.
2. **A released lift overshoots about 12 m.** M7: release at 12 m/s, overshoot 12.1 m, \|vz\| 5.8 m/s 1 s later,
   and the ship then holds 11.5 m too high.
   * The hold only captures once the shaped lift has decayed below the 0.05 dead zone. With LiftTau 0.25 s that takes
     0.75 s. The capture then adds 0.5 s x vz on top.
   * The task's "6.5 m/s still moving 2 s after the release" was measured 1 s after it (as_30 `c_lift` starts its
     window 1 s after the release). PIE and the sim agree on both values: 6.46 at +1 s, 0.46 at +2 s.
3. **A full-speed turn sinks about 5 m (PIE 5.1).** The grip acceleration (up to 2.5 g) acts along the banked hull's
   right axis, so at 18 deg of bank about 0.77 g of it points down. The P-only height hold (Kvz 2, Kz 0.8) settles
   4.7 m low.
4. **The brake is harder than it looks.** Peak 4.3 g from cruise and 5.2 g from 68 m/s; mean 2.25 g. It flares the
   nose +7.5 deg from cruise and +10 deg from 68 m/s.
5. **"0 to 32.6 m/s in 2 s" is a peak, not a 2 s value.** It is the peak after a 2 s W press (mp_test keys). The speed
   at the release was 23.4 m/s. From rest at full throttle the ship has 22.3 m/s at 2 s and reaches 80 % of top in
   3.3 s.
6. **Client latency.** At 100 ms each way the client pilot's screen shows the turn starting 9 frames (0.30 s) after
   the key; PIE measured 0.30 s. The cosmetics react in the same frame.

## What the bench does not model

* **Contacts.** Hull collisions, the impact cap, deck passengers and their 1.4 m nudge are not modelled. Ground
  contact is only detected (keel or nozzle exits below the ground), counted, and the hull is put back on the surface.
* **Client copy.** The client's physics-replication smoothing is not modelled; PIE showed 0-2 frames more.
* **Camera.** No spring-arm position lag, FOV or camera collision. The aim trace hits only bench targets.
* **Mass properties.** They come from `ucx.json`, a Blender export rounded to 1 mm, through my own convex hull,
  where Chaos cooks its own hull. They are not measured in PIE (see Finding 1).
* **Wind.** The phase in PIE is unknown (`GetUniqueID() % 97`); the calibration uses all 97 seeds.
* **Gyroscopic torque.** Off, which is the Chaos default and so matches the hull.

No fudge factors are used. Everything is the C++ defaults, the rig's bone positions and the Chaos algorithms. The
only choices are:

* the wind seed;
* the replay start states, taken from the first PIE sample with the unlogged roll and pitch rates set to 0;
* the input changing one frame before that first sample;
* the test map's ground: the start platform top at z 0 within 50 m of the origin, AS_Ground at -199.5 m.
