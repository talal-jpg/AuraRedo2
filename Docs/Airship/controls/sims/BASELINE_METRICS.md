# Classic (v1) baseline: bench calibration and metrics

These are the reference numbers for judging the three control schemes. The bench is `airship_sim.py` (see
`README.md`), a port of the C++ at commit 8f01bca. Everything here comes from the bench, with the Classic scheme,
the v1 code as it is: `ctrl_inertia='chaos'`. Generated 2026-11-23.

Reproduce it with `python3 calibrate.py`, `python3 metrics.py classic` and `python3 course.py classic` (about 20 s in
all). The raw outputs are `calibration.json` and `classic_metrics.json`.

## 1. Calibration against PIE

The PIE data are the as_43 validation run 2 (standalone, host pilot, fixed 30 fps) and the as_45 multiplayer run 3
(client pilot, no lag and 100 ms each way); `pie_ref.json` is the extract.

* **How each replay works.** Each phase starts from the PIE state at its first sample. The sim then gets the same
  inputs on the same map ground and is compared at the same times.
* **Fudge factors: none.** The model is the C++ defaults, the rig's bone positions and the hull's mass properties
  worked out the way Chaos does it (`mass_props.py`). The only choices made are listed at the end of `README.md`.

**Result.** All phase traces match within about 0.1-0.2 m/s on speeds, 0.5 m on height and about 1 deg on angles.
The scalars match within the PIE's own sampling (0.1 s). Response delays match within 1 frame on the server; the
client's screen differs by 0-2 frames, because the client-copy smoothing is not modelled.

The match needs one thing the code does by accident. `ApplyForces` scales its torque requests with Chaos's principal
inertia order (largest, smallest, middle), not the hull axes (README Finding 1). With the "right" inertia the sim
cannot reproduce the -16.5 deg nose dip; it gives -9.3 deg.

### Error per replayed phase: RMS / max of sim minus PIE over the phase (0.1 s samples)

| Phase (PIE inputs) | forward (m/s) | lateral (m/s) | vertical (m/s) | altitude (m) | yaw rate (deg/s) | roll (deg) | pitch (deg) |
|---|---|---|---|---|---|---|---|
| lift: +1 for 4 s, -1 for 4 s, release 3 s | 0.12 / 0.40 | 0.01 / 0.02 | 0.12 / 0.40 | 0.49 / 0.52 | 0.03 / 0.06 | 0.02 / 0.04 | 0.46 / 1.17 |
| throttle 1 from rest, 10 s | 0.06 / 0.12 | 0.01 / 0.02 | 0.01 / 0.02 | 0.02 / 0.04 | 0.00 / 0.00 | 0.00 / 0.00 | 0.15 / 0.39 |
| throttle 1 + full steer at top speed, 8 s | 0.09 / 0.18 | 0.08 / 0.13 | 0.01 / 0.03 | 0.02 / 0.04 | 0.03 / 0.13 | 0.07 / 0.29 | 0.22 / 0.54 |
| boost from the turn, until the obstacle hit (3.0 s) | 0.01 / 0.03 | 0.05 / 0.11 | 0.01 / 0.03 | 0.01 / 0.01 | 0.04 / 0.13 | 0.14 / 0.32 | 0.01 / 0.01 |
| brake from 68 m/s, 4 s | 0.11 / 0.16 | 0.02 / 0.03 | 0.23 / 0.49 | 0.22 / 0.36 | 0.01 / 0.02 | 0.03 / 0.09 | 0.68 / 1.05 |

### Measured quantities

| Quantity | PIE | Sim | Sim - PIE |
|---|---|---|---|
| Lift +1 4 s: climb rate max (m/s) | 12.00 | 12.00 | +0.00 |
| Lift +1 4 s: height gained (m) | 37.60 | 38.11 | +0.52 |
| Lift -1 4 s: sink rate (m/s) | -14.22 | -14.22 | +0.00 |
| Lift release from -14 m/s: \|vz\| 1 s after (m/s) | 6.46 | 6.46 | +0.00 |
| Lift release: \|vz\| 2 s after (m/s) | 0.47 | 0.46 | -0.01 |
| Lift release: altitude 3 s after minus the held altitude (m) | -0.29 | -0.30 | -0.01 |
| Lift release: held altitude (m) | 34.29 | 34.79 | +0.50 |
| Lift: nose up while climbing (deg) | 3.14 | 3.23 | +0.09 |
| Throttle: forward speed at 1 / 2 / 3 / 4 / 5 s (m/s) | 9.37 / 22.24 / 34.65 / 44.16 / 48.73 | 9.41 / 22.34 / 34.77 / 44.23 / 48.74 | +0.04 / +0.10 / +0.12 / +0.07 / +0.01 |
| Throttle: forward speed at 6 / 7 / 8 / 9 / 10 s (m/s) | 49.47 / 48.64 / 47.94 / 47.72 / 47.77 | 49.45 / 48.63 / 47.94 / 47.73 / 47.77 | -0.02 / -0.01 / -0.00 / +0.00 / +0.00 |
| Throttle: peak forward speed (m/s) | 49.52 | 49.51 | -0.01 |
| Throttle: nose pitch min / max (deg) | -16.46 / +1.73 | -16.37 / +1.70 | +0.09 / -0.03 |
| Throttle: altitude dip (m) | 1.12 | 1.13 | +0.00 |
| Steer at top speed: yaw rate mean 2-8 s (deg/s) | 35.16 | 35.16 | +0.00 |
| Steer: yaw rate 0.4 s after the press (deg/s) | 19.02 | 19.02 | +0.00 |
| Steer: bank 2-8 s min / max (deg) | 16.53 / 17.91 | 16.50 / 17.91 | -0.03 / -0.00 |
| Steer: nose pitch min (deg) | -7.05 | -6.71 | +0.34 |
| Steer: slip speed at 8 s (m/s) | -17.01 | -16.94 | +0.07 |
| Steer: altitude lost in 8 s (m) | 5.11 | 5.11 | -0.00 |
| Boost: forward speed after 3.0 s (m/s) | 86.45 | 86.44 | -0.00 |
| Boost: nose pitch min (deg) | -17.53 | -17.54 | -0.01 |
| Boost: fuel after 3.0 s | 14.17 | 14.17 | +0.00 |
| Brake from 68.0 m/s: speed at 1 s / 2 s (m/s) | 25.22 / 4.81 | 25.31 / 4.96 | +0.09 / +0.15 |
| Brake: half speed after (s) | 0.83 | 0.83 | +0.00 |
| Brake: mean decel over the first 0.4 s (g) | 5.16 | 5.19 | +0.03 |
| Brake: nose flare max (deg) | 10.32 | 10.13 | -0.20 |
| Brake: climb over the latched hold (m) | 3.44 | 3.65 | +0.21 |
| Hover 10 s: \|pitch\| max (deg); PIE runs 0.57 and 0.90, sim median of 97 wind phases (10-90 %: 0.24-0.85) | 0.57 | 0.57 | -0.00 |
| Hover 10 s: \|roll\| max (deg), sim median | 0.04 | 0.02 | -0.02 |
| Hover 10 s: altitude span (m), sim median | 0.04 | 0.02 | -0.02 |
| MP keys, client: IA_AirshipThrottle 2 s + IA_AirshipSteer 1 s, peak forward speed (m/s) ("0 to 32.6 m/s in 2 s") | 32.56 | 32.62 | +0.06 |
| MP keys: forward speed when W is released, 2.0 s after the press (m/s) | 23.44 | 23.46 | +0.02 |
| MP fly0, client with no lag: top forward speed (m/s) | 52.16 | 52.00 | -0.16 |
| MP fly1, client with 100 ms each way: top forward speed (m/s) | 54.49 | 54.64 | +0.15 |

Over a whole flight (420 frames each): fly0 forward speed RMS 0.36 m/s and yaw rate RMS 0.72 deg/s; fly1 0.35 m/s and
0.54 deg/s.

### Response delays, client pilot

Frames after the pilot's own controls changed, PIE / sim. The PIE harness thresholds are steer 0.05, yaw rate
0.5 deg/s, forward speed 0.1 m/s (throttle) or 0.3 m/s (brake).

| Edge | No lag: server controls | No lag: server physics | No lag: client screen | 100 ms each way: server controls | 100 ms: server physics | 100 ms: client screen |
|---|---|---|---|---|---|---|
| throttle | 1 / 1 | 3 / 3 | 4 / 3 | 4 / 4 | 4 / 5 | 8 / 7 |
| steer right | 1 / 1 | 1 / 1 | 3 / 1 | 5 / 4 | 5 / 4 | 8 / 7 |
| steer left | 1 / 1 | 1 / 1 | 1 / 1 | 4 / 4 | 4 / 4 | 0* / 7 |
| brake | 1 / 1 | 1 / 1 | 1 / 1 | 5 / 4 | 5 / 4 | 0* / 7 |

\* PIE threshold artefacts: the client's copy was already drifting that way; `mp_test.md` notes the same. The client
screen in PIE runs 0-2 frames behind the sim, because the bench shows the server's state latency old with no
physics-replication smoothing.

### What the calibration cannot check

* **No PIE measurements exist** for a drift, a strafe, a U-turn, a brake from steady cruise or a +30 m step. The sim
  values for those come from the same validated model.
* **Not modelled:** walking on deck (the 1.4 m nudge), hull contacts and the impact cap (+3.3 m/s per hit step),
  and the client copy's smoothing.
* **Inertia:** the true inertia has never been logged in PIE. One `GetInertiaTensor()` log would close Finding 1.

## 2. Classic metrics (M1-M10)

Each target band is the one I would aim for with an action-game ship of this size (52 m, 40 t); see
`metrics.METRIC_INFO`. The marks: ok = inside the band, LOW / HIGH = outside it, ~ = at its edge.

| Metric | Classic | Target band | | Why it matters for fun |
|---|---|---|---|---|
| M1 time to 80 % of top speed | 3.33 s (63 %: 2.63 s; 22.6 m/s at 2 s, 44.4 m/s at 4 s) | 2.0-3.5 s | ok | How fast W turns into motion: too slow is a barge, instant is a toy |
| M2 top speed steady / peak | 48.0 / 49.5 m/s | 45-60 m/s | ok | Sets the pace of the race |
| M2 boost peak, ratio, duration, t90 | 88.1 m/s, x1.84, 3.6 s, 3.0 s | 1.6-2.0 x top, 3-5 s | ok | Boost must feel like a real gear change |
| M3 brake from cruise: stop time / distance | 2.17 s / 38.6 m (half speed 0.73 s) | 1.5-3.0 s, 30-60 m | ok | A sure brake lets players commit to speed into hairpins |
| M3 peak / mean decel | 4.31 g / 2.26 g | peak <= 2.5 g | HIGH | A 4 g stop reads as a wall, not a 40 t ship |
| M3 coast to half speed | 10.8 s | 8-15 s | ok | The glide of a big ship |
| M4 full-steer step: t63 / t90 | 0.50 / 0.90 s | <= 0.5 / <= 1.0 s | ~ | How quickly the nose answers |
| M4 final turn rate, overshoot | 35.1 deg/s, 2.2 % | 30-45 deg/s, <= 10 % | ok | |
| M4 bank, slip at 8 s, speed at 8 s | 17.8 deg, 19.6 deg, 50.8 m/s | bank 12-22 deg | ok | A planted, carving turn |
| M4 height lost in 8 s, nose pitch min | 5.15 m, -6.7 deg | <= 2 m | HIGH | Turning should not drop the ship into the platforms |
| M5 180 deg turn at full speed | 5.6 s, diameter 181 m, speed kept 106 % | 4-6 s, 100-180 m | ~ | How much room a reversal needs |
| M6 nose pitch: full drive min, at top | -16.6 deg, -1.3 deg | -3..-8 deg | HIGH (too deep) | Weight transfer reads as power, but a big dip hides the horizon |
| M6 boost min / brake max | -20.2 / +7.5 deg | -5..-10 / +3..+8 deg | HIGH / ok | |
| M6 height dip on full drive | 1.44 m | | | |
| M7 climb / sink rate | 12.0 / 15.0 m/s | climb 10-15 m/s | ok | Height is how players dodge and hop |
| M7 +30 m step: rise time | 3.33 s | 2.5-4 s | ok | |
| M7 +30 m step: overshoot | 12.1 m (holds 11.5 m high 5 s later) | <= 1.5 m | HIGH | The ship must stop where the player lets go |
| M7 +30 m step: \|vz\| 1 s / 2 s after release | 5.84 / 0.57 m/s | <= 1.5 / <= 0.5 m/s | HIGH | |
| M8 strafe: t90, speed (hover / cruise) | 0.87 s, 12.3 / 12.3 m/s | 0.6-1.2 s, 10-15 m/s | ok | Side-steps dodge fire and line up a broadside |
| M9 drift: slip at 1 / 2 / 3 s | 15 / 42 / 63 deg | 20-45 deg at 1-2 s | ~ | The skill move: a clear slide |
| M9 drift: turn rate, speed kept, exit kick (measured / paid) | 49.8 deg/s, 103 %, 4.8 / 6.0 m/s | speed kept >= 70 %, kick 4-8 m/s | ok | A reward on the way out |
| M10 host: turbine / wheel / nozzle cosmetics | 0 / 0 / 0 frames | 0-1 frames | ok | Lag between hand and ship kills the fun |
| M10 host: turn on server / on screen, speed on screen | 2 / 2 / 1 frames | <= 2 frames | ok | |
| M10 client 100 ms: cosmetics | 0 / 0 / 0 frames | 0-1 frames | ok | The client's cosmetics are predicted locally |
| M10 client 100 ms: turn on server / on screen, speed on screen | 6 / 9 / 8 frames (0.30 s on screen) | <= 8 frames | HIGH | The turn shows a round trip late on the client |

Notes on these numbers:

* **M1 / M6.** About +0.27 g of the acceleration comes from the nose-down dip tilting the pods' thrust forward.
  With the inertia fix the dip is -9.3 deg, the 49.5 m/s overshoot goes away and the top speed is 47.9 m/s.
* **M3.** The brake is `Kbrake` 0.9/s times the speed plus the fans reversed at 0.5 x AFan. The decel is largest at
  the start (4.3 g at 48 m/s) and fades with the speed.
* **M4.** Turning at full speed sinks the ship by 5 m. The banked grip force points about 0.77 g down, and the P-only
  height hold settles 4.7 m low (README Finding 3). The redirect (Eta 0.35) speeds the ship up in turns (106 %).
* **M7.** The hold captures only after the shaped lift has faded below the 0.05 dead zone (0.75 s), and then adds
  0.5 s of the vertical speed (README Finding 2).
* **M10.** The client's turn shows on its screen after 1 frame + 100 ms (3 frames) up, the server step, and
  100 ms (3 frames) down.

## 3. Gate course (M11)

`course.py`. Gates are 40 m x 25 m; the start is 30 m above flat ground, heading +X. In order: G1 (end of a 300 m
straight), slalom S1-S5 (+-60 m, 150 m apart), hairpin H1 (apex) and H2 (exit, radius about 80 m), C (+40 m climb),
D (40 m dive), F (finish).

The bots fly a racing line that cuts each turn up to 15 m inside the gate centre. "Miss" is the distance from the
gate centre. "Line error" is the error from the bot's own line, which is the comparable precision measure.

* **Precise bot:** no reaction delay, analog inputs, gains tuned by `course.py --tune`.
* **Sloppy bot:** 0.2 s reaction delay; gains with +-15 % noise from a fixed seed, re-drawn every 0.4-1.2 s; W/S,
  A/D, Space/Ctrl played as on/off keys with a 0.1 s minimum press or release. It does not adapt its speed to the
  lag, so its 100 ms result is a worst case.

| Bot | Pilot | Time (s) | Gates missed | Miss from centre mean / max (m) | Line error mean / max (m) | Outside the frame max (m) | Steer reversals / min | Ground contacts |
|---|---|---|---|---|---|---|---|---|
| precise | host | 60.5 | 0 | 10.9 / 17.4 | 2.2 / 4.6 | 0 | 8.9 | 0 |
| precise | client, 100 ms each way | 62.7 | 0 | 9.4 / 16.5 | 2.4 / 4.6 | 0 | 8.6 | 0 |
| sloppy | host | 61.6 | 1 (S5) | 13.6 / 24.7 | 6.4 / 10.4 | 4.7 | 9.7 | 0 |
| sloppy | client, 100 ms each way | 78.2 | 6 (S2-S5, H1, H2) | 52.1 / 139.5 | 40.5 / 115.0 | 119.3 | 13.8 | 2 |

Per gate: lateral / vertical offset from the gate centre in m; ! = missed.

* precise, host: G1 11.8/-0.4, S1 -12.2/-1.6, S2 15.9/-1.4, S3 -16.7/-0.8, S4 17.3/-1.0, S5 -13.3/-0.4,
  H1 16.8/-0.5, H2 12.8/-1.5, C -0.2/-1.2, D 0.0/0.8, F 0.2/0.1
* precise, 100 ms: G1 10.4/-0.2, S1 -9.3/-1.9, S2 11.2/-1.1, S3 -12.1/-0.6, S4 11.5/-0.5, S5 -14.9/-0.6,
  H1 16.5/0.2, H2 8.7/-1.7, C 1.5/-4.4, D 0.0/-3.0, F 0.2/0.1
* sloppy, host: G1 18.2/-0.1, S1 -2.7/-1.2, S2 16.0/0.5, S3 -18.3/0.5, S4 18.3/-0.2, S5! -24.7/-1.6,
  H1 15.0/-0.8, H2 20.0/-2.5, C 1.0/-9.5, D 1.5/-2.9, F 2.1/2.6
* sloppy, 100 ms: G1 18.2/-0.8, S1 -18.6/-2.5, S2! 88.0/-21.9, S3! -139.3/-6.4, S4! 74.4/-0.8, S5! 37.5/-10.6,
  H1! 66.0/4.8, H2! -108.8/-2.7, C -4.7/-2.9, D 5.7/1.0, F -5.9/0.7

**Reading it.** Classic is precise enough for a good player: the line error stays under 5 m even at 100 ms. The
slalom is the hard part:

* The racing line through the slalom needs about a 50 m turn radius, so about 31 m/s.
* With keys alone and a 0.2 s reaction, a player drifts to the edge of the slalom gates.
* Add a 0.23 s round trip and that same player loses the slalom entirely, oscillating up to 140 m wide.

A scheme that holds a turn rate or a heading for the player (less closed-loop work), or that answers faster, should
show up here first.

## 4. Broadside (M12)

The target is fixed at the ship's height, 100 m off the port beam at the start. The ship orbits it at 60 % of top
speed for 60 s after a 15 s run-in, the camera on the target, firing whenever it has a solution.

| Bot | Pilot | In a port arc | Both cannons | In range 80-120 m | Speed >= 50 % | Camera on port | Firing solution | Broadsides fired | Elevation mean / max (deg) |
|---|---|---|---|---|---|---|---|---|---|
| precise | host | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 40 | 5.7 / 6.1 |
| precise | client, 100 ms | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 40 | 5.6 / 6.0 |
| sloppy | host | 69 % | 64 % | 100 % | 100 % | 100 % | 69 % | 37 | 6.8 / 17.9 |
| sloppy | client, 100 ms | 37 % | 30 % | 96 % | 96 % | 100 % | 34 % | 21 | 8.7 / 22.7 |

**Reading it.**

* **Why the target sits high.** The orbit's bank (about 6 deg at 29 m/s on a 100 m circle) lowers the port side,
  which raises a beam target in the hull frame. That eats most of the cannons' +8.5 deg of elevation.
* **The sloppy bot.** Its on/off steering banks the hull 18-23 deg in pulses and lifts the target out of the arc.
  That, not the range or the camera, is where its broadside time goes.
* **The camera.** In Classic the camera is free, so the camera-facing side never gets in the way.
* **What to look for.** A camera-steered scheme has to show it can hold a target abeam. A scheme that keeps the
  hull flatter while aiming should win time in the arc.
