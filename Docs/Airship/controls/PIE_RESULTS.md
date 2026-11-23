# Airship controls: PIE results

The facts the judges use: what the four control schemes (Classic = v1 baseline, Galleon, Sky Racer, Point & Fly)
measured in PIE, next to the bench predictions, plus the acceptance checks, the scheme checks, what the images show and
every issue found. Written 2026-11-23 00:15 UTC by the analysis step, from PIE pass 1 in the clone
`/mnt/new_partition/UnrealProjects/_AirshipWork` (branch `claude/project-thread-0emzt1`, scheme C++ uncommitted on
`8f01bca`).

Definitions of the metrics: `sims/README.md` and `TEST_PROTOCOL.md`. "PIE" values come from
`Saved/Airship/controls_pass1/<scheme>/metrics.json`, "Sim" values from `sims/<scheme>_metrics.json`. A `!` marks a PIE
value more than 15 % and more than 0.5 away from the sim (the compare.md rule).

Section **Final** (2026-11-23 02:15 UTC): the verify step of the polished build, with Point & Fly as the default
scheme. Section **Follow-up (after the final review)** (end of this file, 2026-11-23 03:35 UTC): the fixes F-A to F-E
in PIE (Fire held arms the gun lock, a hit no longer ends the parked free look, the as_43 / as_45 harness fixes), and
its "Fix2" part (03:50 UTC): as_43 made independent of the build; Classic as_43 is 24/25 every time (f2, a v1 limit).

## Pass 1

### Summary

* **All four schemes can be judged on the pass-1 data.** Every scheme ran 17 of 17 runs, its scheme was confirmed on
  the server (`GetControlScheme` and the telemetry field `Scheme`), 0 script errors, 0 missing telemetry fields, 0 hull
  hits, 0 frames of input delay (`k0` = 0 in every segment).
* **Nothing is BLOCKING.** No dead input, no failed run, no crash, and every scheme mechanic tested works in PIE
  (Galleon telegraph and stations, Sky Racer drift tiers and mini-turbo, Point & Fly heading loop and gun lock).
  **No C++ was changed** (two diagnostic builds were made and reverted; the sources are byte-identical to pass 1 and
  rebuilt at 23:59 UTC).
* **PIE agrees with the bench to 2-4 digits on almost every maneuver metric.** That is real: recomputed from the raw
  PIE frames (positions included), the values match (section "Are the PIE values really PIE?"). The deviations come
  from things the bench does not model: the wind phase, a reset artefact of the harness, engine tick order and the
  real camera.
* **Classic is numerically v1.** `Aura.Airship.Scheme check`: 0 differences. as_43 gave 23/25 in pass 1 and 24/25 on
  the re-runs. The one remaining failure (`a3_deck_stand`) is caused by the v1 wind sway, whose phase is seeded by the
  ship's UObject index (`GetUniqueID() % 97`). The new build gives the PIE ship index 56 instead of 51 (proven by
  fitting the wind model to the hover drift, below). The flight code Classic runs through is v1.
* **Course times are biased by a harness reset artefact.** Each start pose begins with the previous run's throttle
  still decaying, so the ship rolls forward during the reset: Classic starts the course 22.9 m ahead at 3.7 m/s
  (0.67 s faster than the sim), Point & Fly 9.3 m (0.20 s), Sky Racer 5.5 m (0.10 s), Galleon 1.7 m (0.04 s). The
  ranking of the candidates does not change.
* **FEEL items worth fixing if the scheme wins:** Point & Fly's gun lock holds the target 7 deg aft of the beam
  (bench: 2.6 deg), and stopping a fast turn on a fixed target overshoots 8.5 deg. Galleon and Sky Racer showed no
  feel problem in these runs. (Classic's camera shows the ship side-on in slow hairpins: v1 behaviour, kept.)

### Runs

| Scheme | Editor session | Runs OK | Game time (s) | Wall time (s) | Notes |
|---|---|---|---|---|---|
| Classic (v1) | 1 (from 22:29 UTC) | 17 / 17 | 686.1 | 744.9 | 8 runs warn "start pose not at rest after 4.2 s" (4.0-4.6 m/s) |
| Galleon | 1 | 17 / 17 | 676.9 | 750.6 | no warnings |
| Sky Racer | 2 (re-run from 23:07 UTC, KEEP_CONTROLS) | 17 / 17 | 636.3 | 686.1 | the session-1 attempt stopped at its course run when PIE was ended from outside (23:02); not used |
| Point & Fly | 2 | 17 / 17 | 681.1 | 759.9 | 8 runs warn "not at rest" (0.41-0.42 m/s) |

The pass ran standalone (no 100 ms lag values; the listen pass is a later step). The final `Aura.Airship.Scheme 0` +
`Aura.Airship.Scheme check` ran at the end of session 2 (`as50_result.json` `final_check`). `as50_log.txt` has no ERR
line; its WARN lines are the start-pose drift (below) and one "real fps 11.9" warning in the interrupted session 1.

### Phase A acceptance (IMPLEMENTATION_PLAN 7 and 5.4)

| Check | Result | Verdict |
|---|---|---|
| as_43 25/25 with Classic | pass 1 23/25 (`a3_deck_stand` 3.166 m, `f2_boost_path` +5.98 m/s); re-run 24/25 (`a3_deck_stand` 3.127 m; `f2` +4.86 m/s PASS) | **not met literally.** Both failures are explained below (wind seed, not code). No threshold was changed |
| `Aura.Airship.Scheme check` after `Scheme 0` | `[23.32.04] Aura.Airship.Scheme check: BP_AirshipPawn_C_0: Classic (v1), 0 difference(s) from the class defaults` | met |
| Inertia line (5.4) | principal X = 6.8586e10, Y = 1.0998e10, Z = 6.5744e10 kg cm², mass-frame rotation P 82.02 Y 166.96 R -102.80, COM (-170, 0, 0) cm, the same in all four scheme blocks | met (`hull_mass.json`: 6.8586, 1.0998, 6.5744 e10) |
| Classic M1 / M4 / M7 against `reports/pie_validate.md` run 2 and `sims/classic_metrics.json` | see the table below | met within the noise, except where the as_43 start state differs (explained) |
| as_45 multiplayer 5/5 | not part of this step | open (the verify step) |

**Classic M1 / M4 / M7**

| Value | PIE pass 1 (as_50) | PIE pass 1 (as_43) | v1 PIE run 2 (`pie_validate.md`) | v1 rebuilt 23:45 (as_43) | Sim |
|---|---|---|---|---|---|
| M1 t80 (s) | 3.30 | - | - | - | 3.333 |
| Forward speed at 1 / 2 / 3 / 4 / 5 s of full throttle (m/s) | - / 22.91 / - / 44.59 / - | 9.77 / 22.55 / 34.84 / 44.20 / 48.71 | 9.4 / 22.3 / 34.7 / 44.2 / 48.8 | 9.37 / 22.24 / 34.65 / 44.16 / 48.73 | - / 22.55 / - / 44.44 / - |
| Top speed (m/s) | 48.00 steady, 49.52 peak | 49.50 peak | 49.5 | 49.52 | 48.00 / 49.53 |
| Pitch range under drive (deg) | -16.50 min | -16.2 .. +1.7 | -16.5 .. +1.7 | -16.5 .. +1.7 | -16.58 |
| M4 turn rate (deg/s) | 35.14 | 35.16 mean (34.89-35.96) | 35.2 | 35.16 mean (34.89-35.96) | 35.14 |
| M4 bank (deg) | 17.84 | 16.5 .. 17.9 | 16.5 .. 17.9 | 16.5 .. 17.9 | 17.84 |
| M7 climb / sink (m/s) | 12.00 / 14.99 | 12.00 / 14.22 (4 s run) | +38.4 m / -6.9 m in 4 s | 12.00 / 14.22 | 12.00 / 14.99 |

The as_43 throttle run is not a clean M1: it starts from whatever the lift phase left (first throttle frame: the scheme
build at +1.23 m/s forward, v1 at +0.80 m/s), which is the whole 0.3-0.4 m/s difference at 1-2 s. From 4 s on the
speeds agree within 0.05 m/s, the steer run is identical to 0.01 deg/s and the lift run to 0.01 m/s.

### Why as_43 fails `a3_deck_stand` (and failed `f2_boost_path` once): the wind seed

(Since the follow-up's Fix2, as_43 turns the wind sway off for the whole run and starts the flight path from the spawn
pose, so its result no longer depends on the seed: section "Follow-up", "Fix2".)

`a3_deck_stand` (a character stands on the deck of the unpiloted ship for 10 s; the ship may move at most 1.5 m)
fails on the scheme build every time, and passes on v1 every time:

| as_43 run (`Saved/Airship/`) | Build | Armed (UTC) | Checks | a3 drift in 10 s (m) | f2 vz after the hit (m/s) | b_hover pitch max / drift | Wind seed that fits (`GetUniqueID() % 97`) |
|---|---|---|---|---|---|---|---|
| `val_pass1_2227` | scheme build | 22:27 | 23 / 25 | 3.166 FAIL | +5.98 FAIL | 0.09 deg / 0.29 m | 56 (explains 94 % of the lateral push) |
| `val_rerun1_2333` (= `val`) | scheme build | 23:34 | 24 / 25 | 3.127 FAIL | +4.86 | 0.09 deg / 0.29 m | 56 (95 %) |
| `val_expA_2353` | scheme build, BeginPlay skips the scheme apply for Classic (test, reverted) | 23:54 | 24 / 25 | 3.127 FAIL | +4.86 | 0.09 deg / 0.29 m | 56 (95 %) |
| `val_v1build_2344` | v1 (HEAD `8f01bca`) rebuilt for this test | 23:45 | 25 / 25 | 0.817 | +4.83 | 0.30 deg / 0.20 m | 51 (100 %) |
| `val_ref_oldbuild_1755` | v1 | 17:55 | 25 / 25 | 0.817 | +4.83 | 0.30 deg / 0.20 m | 51 (100 %) |
| `reports/pie_validate.md` run 2 | v1 before the redo3 merge | 2026-11-22 | 25 / 25 | 0.34 | +4.84 | 0.57 deg / 0.47 m | (raw data not kept) |

What the frames show (scripts `_AirshipWork_logs/scratch/controls/val_diff.py`, `wind_fit.py`):

1. **as_43 is deterministic per build.** The rebuilt v1 run matches the 17:55 v1 run to 0.00 cm for the first 28 s.
   The two scheme-build runs agree within 0.2 cm through the hover and 12 cm at the end of the deck stand.
2. **Between builds, the hulls differ from the first frame, but only at low speed.** In the settle phase (no pilot,
   no input) the lateral speed differs by up to 1.8 cm/s. Whenever the ship is above 30 m/s with the same input, the
   two builds match frame by frame to 1 cm/s and 0.01 deg (the steer run, the boost run up to the obstacle). The
   shaped controls are identical in every frame.
3. **v1's wind sway is exactly that kind of force.** `ApplyForces` (unchanged from v1) adds
   `WindLateralAccel` 25 cm/s² × `PerlinNoise1D(WorldTime × 0.15 + Seed)` sideways, plus roll and pitch sway,
   faded out from rest to 30 m/s, with `Seed = (GetOwner()->GetUniqueID() % 97) × 3.7`. The unique ID is the
   object's index in the UObject array: the scheme build registers more reflected objects (enum, functions), so the
   PIE ship gets another index and another gust history.
4. **The fit proves it.** From the hull's own lateral speed in the low-speed stretches (settle, hover, deck stand, deck
   walk: 296 samples), the push is `dv/dt + GripKlat × v` (GripKlat 4 /s is v1's only lateral control at rest). Fitting
   the C++ wind formula over all 97 seeds and the world-time offset gives: v1 runs → seed 51, residual 0.31 cm/s² of
   a 4.96 cm/s² signal (100 %); scheme-build runs → seed 56, residual 1.30-1.35 of 5.6 cm/s² (94-95 %). Seed 51
   does not fit the scheme build (-41 %), seed 56 does not fit v1 (-33 %), the best other seeds explain 45 % / 82 %.
   Both builds fit the same world-time offset (0.07 s).
5. **The BeginPlay scheme apply is not the cause**: with it skipped for Classic (`val_expA_2353`) the run is
   identical to the plain scheme build.
6. **f2_boost_path** is a contact event: the ship clips `AS_Obstacle_1` at 91.6 m/s. Before the hit the builds match
   to 1 cm/s, but the hover phases left the hull 8.4 m sideways of v1's path (pass 1) or 1.2 m from pass 1 (re-run),
   so the hull meets the obstacle at another point: +5.98 / +4.86 / +4.83 m/s. Noise of the test, not of the code.

So with seed 56 the unpiloted ship drifts 3.1 m in the deck-stand window: the v1 gusts carry it, exactly as they
would carry v1 itself with that seed. It is v1 behaviour (no station keeping at rest), and the check is sensitive to
the seed. Making as_43 independent of the seed (wind off or a fixed seed for `a3`) is a harness change for the lead
to decide. It was not made here, and no threshold was touched.

### Are the PIE values really PIE?

Yes. The metrics files say `meta.source` = `pie`. The inertia and scheme lines are engine log lines with engine
timestamps (the mock harness would print "inertia (6.86, 1.10, 6.57) e10 kg cm2 MassSpace (mock)"). The telemetry
holds camera locations, rig cosmetics and ground traces the bench does not have. And the reset artefacts below cannot
happen in the bench. Recomputed with my own code from the raw frames of `telemetry.json` (`recompute.py`), including
speeds taken from the positions:

| Value | Classic | Galleon | Sky Racer | Point & Fly |
|---|---|---|---|---|
| M1 t80 (s): recomputed / metrics.json | 3.300 / 3.3 | 3.300 / 3.3 | 2.867 / 2.867 | 3.267 / 3.267 |
| M2 top speed from telemetry speed / from positions over 17-20 s / metrics.json (m/s) | 48.00 / 48.01 / 48.0 | 47.84 / 47.84 / 47.84 | 56.38 / 56.38 / 56.38 | 47.97 / 47.97 / 47.97 |
| M4 turn rate from YawRate / from the heading change over 6-8 s / metrics.json (deg/s) | 35.14 / 35.14 / 35.14 | 34.06 / 34.06 / 34.06 | 38.01 / 38.01 / 38.01 | 34.98 / 34.98 / 34.98 |
| M7 climb from vz max / from z over the last 1 s / metrics.json (m/s) | 12.00 / 12.01 / 12.0 | 10.01 / 10.01 / 10.01 | 13.62 / 13.51 / 13.62 | 12.01 / 12.01 / 12.01 |
| M3 stop time (s): recomputed / metrics.json | 2.17 / 2.17 | 3.07 / 3.07 | 2.87 / 2.87 | 2.47 / 2.47 |

Why the bench agrees so closely: it was calibrated against v1 PIE (`sims/calibration.json`), the C++ schemes follow
the bench's equations 1:1, and every maneuver starts from a reset at rest with fixed 30 fps steps. Where PIE has
something the bench lacks, the numbers part (next sections).

### Start-pose drift during the reset (harness artefact)

The reset (`TEST_PROTOCOL.md` 3.1) teleports the hull and zeroes its velocity for 5 frames, but the scheme's shaped
throttle is still decaying from the previous run (0.93 on the first reset frame after a full-throttle run), so the
ship accelerates again during the reset. This is the "start pose drifted N m" warning.

| Scheme (course run `m11_precise`) | Shaped throttle at reset frame 0 | Ahead of the course start when the course begins | Speed then | Course time PIE vs sim |
|---|---|---|---|---|
| Classic | 0.93 | 22.9 m | 3.72 m/s (v1 keeps coasting: no station keeping, coast-to-half 10.8 s) | 59.83 vs 60.50 s (-0.67) |
| Point & Fly | 0.93 | 9.3 m | 0.11 m/s | 58.93 vs 59.13 s (-0.20) |
| Sky Racer | 0.90 | 5.5 m | 0.14 m/s | 48.97 vs 49.07 s (-0.10) |
| Galleon | 0.88 (the speed loop backs it off to STOP) | 1.7 m | 0.09 m/s | 61.03 vs 61.07 s (-0.04) |

It affects runs that follow a run ending at throttle: `m3_brake`, `m7_climb`, `m9`, the four course runs and
`m12_precise`. `m3_brake` and `m9` start with 20 s of cruise and `m12` with a 15 s run-in, so only the course times (and
Classic's `m7_climb`, started at 4 m/s, climb rate unchanged at 12.00 m/s) carry it. Judges: read course times with
these offsets. Sky Racer stays about 10 s ahead of everything and Point & Fly ahead of Galleon either way. Fix for the
next pass: hold the brake or wait for the shaped throttle to reach 0 before the teleport.

### Per scheme: PIE against the sim

#### Classic (v1)

| Metric | PIE | Sim | |
|---|---|---|---|
| M1 time to 80 % of top speed (s) | 3.3 | 3.333 |  |
| M1 speed at 2 s (m/s) | 22.91 | 22.55 |  |
| M2 top speed (m/s) | 48 | 48 |  |
| M2 boost peak (m/s) | 87.95 | 88.13 |  |
| M2 boost duration (s) | 3.6 | 3.63 |  |
| M3 brake: stop time (s) | 2.17 | 2.17 |  |
| M3 brake: stop distance (m) | 38.58 | 38.58 |  |
| M3 brake: peak decel (g) | 4.31 | 4.31 |  |
| M3 coast to half speed (s) | 10.767 | 10.767 |  |
| M4 turn rate (deg/s) | 35.14 | 35.14 |  |
| M4 t90 (s) | 0.9 | 0.9 |  |
| M4 bank (deg) | 17.84 | 17.84 |  |
| M4 slip at 8 s (deg) | 19.59 | 19.59 |  |
| M4 height lost at 8 s (m) | 5.15 | 5.15 |  |
| M5 U-turn time (s) | 5.6 | 5.6 |  |
| M5 U-turn diameter (m) | 180.84 | 180.84 |  |
| M6 nose dip under drive (deg) | -16.5 | -16.58 |  |
| M6 nose dip under boost (deg) | -20.16 | -20.16 |  |
| M6 brake flare (deg) | 7.27 | 7.47 |  |
| M7 climb rate (m/s) | 12 | 12 |  |
| M7 +30 m step overshoot (m) | 12.2 | 12.1 |  |
| M7 vz 1 s after release (m/s) | 5.84 | 5.84 |  |
| M8 strafe t90 (s) | 0.867 | 0.867 |  |
| M8 strafe speed (m/s) | 12.24 | 12.29 |  |
| M9 drift slip at 2 s (deg) | 41.83 | 41.83 |  |
| M9 drift speed kept (%) | 102.7 | 102.7 |  |
| M9 drift exit kick (m/s) | 4.78 | 4.78 |  |
| M10 turn on screen (frames) | 2 | 2 |  |
| M10 turbine housing moves (frames) | 1 | 0 | ! (a) |
| M11 precise: course time (s) | 59.83 | 60.5 | (start drift) |
| M11 precise: gates missed | 0 | 0 |  |
| M11 precise: line error mean (m) | 2.03 | 2.2 |  |
| M11 precise: steer reversals (/min) | 9 | 8.9 |  |
| M11 sloppy run 1: course time (s) | 61.33 | 61.6 |  |
| M11 sloppy run 1: gates missed | 2 | 1 | ! (b) |
| M11 sloppy, median of 3: course time (s) | 60.67 (runs 61.33, 60.4, 60.67) | - | |
| M11 sloppy, median of 3: gates missed | 2 (runs 2, 3, 1) | - | |
| M11 sloppy, median of 3: line error mean (m) | 7.1 (runs 6.19, 7.1, 7.93) | - | |
| M12 precise: target in a port arc (%) | 100 | 100 |  |
| M12 precise: firing solution (%) | 100 | 100 |  |
| M12 precise: target off the beam, mean (deg) | 3.7 | 3.67 |  |
| M12 sloppy: target in a port arc (%) | 66.6 | 68.8 |  |
| M12 sloppy: firing solution (%) | 66.6 | 68.8 |  |
| M12 sloppy: elevation max (deg) | 17.53 | 17.86 |  |

#### Galleon

| Metric | PIE | Sim | |
|---|---|---|---|
| M1 time to 80 % of top speed (s) | 3.3 | 3.3 |  |
| M1 speed at 2 s (m/s) | 24.11 | 24.14 |  |
| M2 top speed (m/s) | 47.84 | 47.84 |  |
| M2 boost peak (m/s) | 88.21 | 88.21 |  |
| M2 boost duration (s) | 4.1 | 4.1 |  |
| M3 brake: stop time (s) | 3.07 | 3.07 |  |
| M3 brake: stop distance (m) | 57.07 | 57.07 |  |
| M3 brake: peak decel (g) | 2.32 | 2.32 |  |
| M3 coast to half speed (s) | 2.5 | 2.5 |  |
| M4 turn rate (deg/s) | 34.06 | 34.06 |  |
| M4 t90 (s) | 0.867 | 0.867 |  |
| M4 bank (deg) | 26.56 | 26.56 |  |
| M4 slip at 8 s (deg) | 13.01 | 13.02 |  |
| M4 height lost at 8 s (m) | 0.12 | 0.12 |  |
| M5 U-turn time (s) | 5.67 | 5.67 |  |
| M5 U-turn diameter (m) | 186.61 | 186.62 |  |
| M6 nose dip under drive (deg) | -3.95 | -3.95 |  |
| M6 nose dip under boost (deg) | -5.17 | -5.17 |  |
| M6 brake flare (deg) | 2.99 | 2.95 |  |
| M7 climb rate (m/s) | 10.01 | 10.01 |  |
| M7 +30 m step overshoot (m) | 4.01 | 4.01 |  |
| M7 vz 1 s after release (m/s) | 0.2 | 0.2 |  |
| M8 strafe t90 (s) | 0.967 | 0.967 |  |
| M8 strafe speed (m/s) | 10.13 | 10.17 |  |
| M9 drift slip at 2 s (deg) | 39.92 | 39.92 |  |
| M9 drift speed kept (%) | 52 | 51.9 |  |
| M9 drift exit kick (m/s) | 2.93 | 2.93 |  |
| M10 turn on screen (frames) | 2 | 2 |  |
| M10 turbine housing moves (frames) | 1 | 0 | ! (a) |
| M11 precise: course time (s) | 61.03 | 61.07 |  |
| M11 precise: gates missed | 0 | 0 |  |
| M11 precise: line error mean (m) | 3.26 | 3.27 |  |
| M11 precise: steer reversals (/min) | 6.9 | 8.8 | ! (c) |
| M11 sloppy run 1: course time (s) | 62.93 | 63.3 |  |
| M11 sloppy run 1: gates missed | 0 | 0 |  |
| M11 sloppy, median of 3: course time (s) | 62.93 (runs 62.93, 62.43, 63.47) | - | |
| M11 sloppy, median of 3: gates missed | 0 (runs 0, 0, 1) | - | |
| M11 sloppy, median of 3: line error mean (m) | 4.53 (runs 4.53, 4.34, 5.75) | - | |
| M12 precise: target in a port arc (%) | 100 | 100 |  |
| M12 precise: firing solution (%) | 100 | 100 |  |
| M12 precise: target off the beam, mean (deg) | 3.55 | 3.53 |  |
| M12 sloppy: target in a port arc (%) | 100 | 100 |  |
| M12 sloppy: firing solution (%) | 100 | 100 |  |
| M12 sloppy: elevation max (deg) | 4.91 | 4.94 |  |

#### Sky Racer

| Metric | PIE | Sim | |
|---|---|---|---|
| M1 time to 80 % of top speed (s) | 2.867 | 2.867 |  |
| M1 speed at 2 s (m/s) | 32.99 | 32.97 |  |
| M2 top speed (m/s) | 56.38 | 56.38 |  |
| M2 boost peak (m/s) | 92.53 | 92.53 |  |
| M2 boost duration (s) | 3.23 | 3.23 |  |
| M3 brake: stop time (s) | 2.87 | 2.87 |  |
| M3 brake: stop distance (m) | 72.41 | 72.41 |  |
| M3 brake: peak decel (g) | 2.52 | 2.52 |  |
| M3 coast to half speed (s) | 10.7 | 10.7 |  |
| M4 turn rate (deg/s) | 38.01 | 38.01 |  |
| M4 t90 (s) | 0.6 | 0.6 |  |
| M4 bank (deg) | 23.06 | 23.06 |  |
| M4 slip at 8 s (deg) | 3.29 | 3.29 |  |
| M4 height lost at 8 s (m) | -0.03 | -0.03 |  |
| M5 U-turn time (s) | 5 | 5 |  |
| M5 U-turn diameter (m) | 172.59 | 172.59 |  |
| M6 nose dip under drive (deg) | -4.91 | -4.91 |  |
| M6 nose dip under boost (deg) | -5.76 | -5.76 |  |
| M6 brake flare (deg) | 3.9 | 3.94 |  |
| M7 climb rate (m/s) | 13.62 | 13.62 |  |
| M7 +30 m step overshoot (m) | 5.35 | 5.35 |  |
| M7 vz 1 s after release (m/s) | 0 | 0.01 |  |
| M8 strafe t90 (s) | 0.7 | 0.7 |  |
| M8 strafe speed (m/s) | 14.2 | 14.22 |  |
| M9 drift slip at 2 s (deg) | 24.72 | 24.72 |  |
| M9 drift speed kept (%) | 96.5 | 96.5 |  |
| M9 drift exit kick (m/s) | 8.35 | 8.35 |  |
| M10 turn on screen (frames) | 1 | 1 |  |
| M10 turbine housing moves (frames) | 1 | 0 | ! (a) |
| M11 precise: course time (s) | 48.97 | 49.07 |  |
| M11 precise: gates missed | 0 | 0 |  |
| M11 precise: line error mean (m) | 2.78 | 2.78 |  |
| M11 precise: steer reversals (/min) | 9.8 | 9.8 |  |
| M11 sloppy run 1: course time (s) | 49.83 | 49.63 |  |
| M11 sloppy run 1: gates missed | 1 | 1 |  |
| M11 sloppy, median of 3: course time (s) | 50.07 (runs 49.83, 50.07, 50.2) | - | |
| M11 sloppy, median of 3: gates missed | 1 (runs 1, 1, 2) | - | |
| M11 sloppy, median of 3: line error mean (m) | 5.46 (runs 5.46, 5.67, 5.32) | - | |
| M12 precise: target in a port arc (%) | 100 | 100 |  |
| M12 precise: firing solution (%) | 100 | 100 |  |
| M12 precise: target off the beam, mean (deg) | 1.4 | 1.36 |  |
| M12 sloppy: target in a port arc (%) | 100 | 100 |  |
| M12 sloppy: firing solution (%) | 100 | 100 |  |
| M12 sloppy: elevation max (deg) | 5.9 | 6.23 |  |

#### Point & Fly

| Metric | PIE | Sim | |
|---|---|---|---|
| M1 time to 80 % of top speed (s) | 3.267 | 3.267 |  |
| M1 speed at 2 s (m/s) | 23.56 | 23.56 |  |
| M2 top speed (m/s) | 47.97 | 47.97 |  |
| M2 boost peak (m/s) | 86.93 | 87.03 |  |
| M2 boost duration (s) | 3.6 | 3.63 |  |
| M3 brake: stop time (s) | 2.47 | 2.47 |  |
| M3 brake: stop distance (m) | 56.86 | 56.85 |  |
| M3 brake: peak decel (g) | 2.39 | 2.39 |  |
| M3 coast to half speed (s) | 11.333 | 11.333 |  |
| M4 turn rate (deg/s) | 34.98 | 34.98 |  |
| M4 t90 (s) | 0.7 | 0.7 |  |
| M4 bank (deg) | 18.75 | 18.75 |  |
| M4 slip at 8 s (deg) | 15.72 | 15.72 |  |
| M4 height lost at 8 s (m) | 0.06 | 0.06 |  |
| M5 U-turn time (s) | 5.5 | 5.5 |  |
| M5 U-turn diameter (m) | 176.17 | 176.18 |  |
| M6 nose dip under drive (deg) | -3.95 | -3.95 |  |
| M6 nose dip under boost (deg) | -5.2 | -5.2 |  |
| M6 brake flare (deg) | 5.75 | 5.82 |  |
| M7 climb rate (m/s) | 12.01 | 12.01 |  |
| M7 +30 m step overshoot (m) | 5.7 | 5.7 |  |
| M7 vz 1 s after release (m/s) | 0.56 | 0.56 |  |
| M8 strafe t90 (s) | 0.767 | 0.767 |  |
| M8 strafe speed (m/s) | 14.29 | 14.33 |  |
| M9 drift slip at 2 s (deg) | 42.27 | 42.27 |  |
| M9 drift speed kept (%) | 100 | 100 |  |
| M9 drift exit kick (m/s) | 4.71 | 4.71 |  |
| M10 turn on screen (frames) | 1 | 1 |  |
| M10 turbine housing moves (frames) | 1 | 0 | ! (a) |
| M11 precise: course time (s) | 58.93 | 59.13 | (start drift) |
| M11 precise: gates missed | 0 | 0 |  |
| M11 precise: line error mean (m) | 2.71 | 2.71 |  |
| M11 precise: steer reversals (/min) | 0 | 0 |  |
| M11 precise: camera reversals (/min) | 58 | 57.8 |  |
| M11 sloppy run 1: course time (s) | 59.6 | 59.83 |  |
| M11 sloppy run 1: gates missed | 0 | 0 |  |
| M11 sloppy, median of 3: course time (s) | 59.6 (runs 59.6, 59.6, 59.57) | - | |
| M11 sloppy, median of 3: gates missed | 0 (runs 0, 0, 0) | - | |
| M11 sloppy, median of 3: line error mean (m) | 1.28 (runs 1.28, 1.17, 1.3) | - | |
| M12 precise: target in a port arc (%) | 100 | 100 |  |
| M12 precise: firing solution (%) | 100 | 100 |  |
| M12 precise: target off the beam, mean (deg) | -7.39 | -2.6 | ! (d) |
| M12 sloppy: target in a port arc (%) | 100 | 100 |  |
| M12 sloppy: firing solution (%) | 100 | 100 |  |
| M12 sloppy: elevation max (deg) | 4.53 | 4.48 |  |

#### The deviations explained

| | Deviation | Cause | Class |
|---|---|---|---|
| (a) | M10 turbine, wheel and nozzle cosmetics 1 frame (sim 0), all four schemes | Engine tick order: the frames show the rig values one frame after the shaped control (Classic turn: shaped steer 0.199 in frame 0, wheel -2.15 deg in frame 1; Sky Racer the same). The anim instance reads the cosmetic state before the flight component updates it in that frame. The bench has no anim tick. Still inside the band (cosmetic 0-1 frames). The physics answers in frame 0 (yaw rate already 0.77 deg/s) | harness / bench simplification |
| (b) | Classic sloppy course: 2 gates missed in run 1 (sim 1); compare.md also flags outside_max, line_error_max and steer reversals | The sloppy bot's errors depend on the wind phase (PIE: the ship's ID, the bench: seed 7), and TEST_PROTOCOL 7 says this alone moves Classic by 1-3 gates. Classic also starts 22.9 m ahead at 3.7 m/s. Median of 3 = 2 missed (runs 2, 3, 1) | bench simplification |
| (c) | Galleon precise course: 6.9 steer reversals per minute (sim 8.8) | A count of the bot's small corrections: 7 against 9 in 61 s. The wind (active below 30 m/s, so in the 29-33 m/s slalom and the hairpins) has another phase than in the bench. Course time and line error equal the sim to 0.04 s / 0.01 m | bench simplification |
| (d) | Point & Fly orbit: target 7.4 deg off the beam (sim 2.6 deg); sloppy 7.3 (sim 6.2) | Measured from the frames (`m12_beam.py`): in the steady orbit (16.4 deg/s left turn at 29-30 m/s) the hull lags its sent heading target by 4.9 deg, and the target sits 7.1 deg aft of the port beam. Classic and Galleon hold it 3 deg ahead of the beam, Sky Racer 1 deg. The gun lock was on in 97 % of the frames. Both port guns stay in arc (100 %), so the firing solution is unchanged, but the bench's lock lead does not cancel the lag the way it does in PIE | FEEL (Point & Fly) |
| - | Sloppy line errors on Galleon / Sky Racer (compare.md `!` on line_error_mean / max, outside_max) | the same wind-phase effect as (b) on the sloppy bot | bench simplification |
| - | Course times 0.04-0.67 s faster than the sim | the start-pose drift above | harness |

No deviation points at a C++ bug.

### Scheme checks (IMPLEMENTATION_PLAN 5.4), from `telemetry.json` (`scheme_checks.py`)

| Scheme | Check | What the PIE frames show | Verdict |
|---|---|---|---|
| Galleon | Telegraph: hold W from STOP, `ThrottleOrder` 0 → 1/3 → 2/3 → 1 at 0 / 0.27 / 0.43 s | The runs never hold W from STOP: the bench's Galleon adapter taps it (press on frames 0, 2, 4 of `m1_m2`), and each tap rings one notch: 1/3 at 0 s, 2/3 at 0.067 s, FULL at 0.133 s. STOP during the settle, every reset back to STOP | taps OK. The held-W auto-step (0.27 / 0.43 s) is **not in the runs** |
| Galleon | Beam watch without firing keeps `bGunDeck` false; a broadside sets it | `m12_precise`: 74 orbit frames of beam watch (camera 82 deg off the bow) before the first broadside with `bGunDeck` false; on from the first broadside (frame 196); shots every 1.40 s keep it on (0 frames off afterwards). No `bGunDeck` in any non-orbit run. `m12_sloppy` starts with it on for 49 frames: the previous run's last broadside was under 6 s earlier (back-to-back runs, the rule as designed) | met |
| Sky Racer | Drift tiers and turbo release | `m9` (full steer into the drift): tier 1 at 0.50 s (charge 0.25), tier 2 at 1.10 s (0.55), tier 3 at 2.00 s (1.00): charge rate 0.5 /s as `SkyChargeRateMax`. Release at 3.00 s: `TurboAlpha` 0.97 → 0 in 1.2 s (`SkyTurboTime3`); speed +7.15 m/s in one frame (kick 7.5 m/s, `SkyTurboKickDV3`), forward speed 48.94 → 56.95 m/s as the nose swings back. Fuel stays at 100 (already full; the +15 is clamped) | met |
| Sky Racer | On the courses | precise: 4 drifts (highest tier 0, 1, 2, 2), 3 turbo releases. Sloppy: 5 / 5 / 7 drifts, 3 releases each | the mechanic is used in racing |
| Sky Racer | Drift with and without W gives the same course and tier; client HUD tier at 100 ms | not in the standalone runs | **not in the runs** (listen pass) |
| Point & Fly | Camera steps of 10 / 90 deg at cruise settle in 0.9 / 3.4 s with < 0.1 deg overshoot | No clean step from straight cruise in the runs. Closest: `m9` drift exit, the target held while the hull still turns at 49 deg/s with 13.6 deg to go: overshoot 8.5 deg at 0.8 s, under 0.5 deg at 1.8 s, 0.1-0.26 deg left at 2.2-2.8 s. The bench gives the same exit (M9 values equal). In `m4_m5` the bot keeps the target 88.8 deg ahead (steer saturated, 34.9 deg/s). On the precise course the hull follows the target with 4.0 deg mean error, 32.7 deg max | steps **not in the runs**. Stopping a fast turn overshoots 8.5 deg (FEEL) |
| Point & Fly | With Aim held, a look 40 deg off the bow never sets `bGunLock` | No aim under 57 deg off the bow in the runs (`m12`: aim held all 2250 orbit frames at 57-110 deg, lock on 97.0 % / 96.4 %). No `bGunLock` in any run without Aim | lock works on the beam. The 40-deg case is **not in the runs** |

### Sloppy course, median of 3 runs (judge on this, not on run 1)

| Scheme | Gates missed (runs) | Course time (s) (runs) | Line error mean (m) | Steer / camera reversals per min |
|---|---|---|---|---|
| Classic (v1) | **2** (2, 3, 1): S5+C, S4+S5+H2, S3 | 60.67 (61.33, 60.40, 60.67) | 7.10 | 11.7 / 0 |
| Galleon | **0** (0, 0, 1): H1 once | 62.93 (62.93, 62.43, 63.47) | 4.53 | 8.6 / 0 |
| Sky Racer | **1** (1, 1, 2): S5 each time, S2 once | 50.07 (49.83, 50.07, 50.20) | 5.46 | 45.8 / 0 |
| Point & Fly | **0** (0, 0, 0) | 59.60 (59.60, 59.60, 59.57) | 1.28 | 0 / 65.4 |

The three runs of a scheme share one editor session (one wind seed) and differ by world time. Classic and Galleon ran
in session 1, Sky Racer and Point & Fly in session 2, so the two pairs had different gust histories at low speed.

### Images

| File | What it shows |
|---|---|
| `controls_pass1/<scheme>/contact_<scheme>.png` | Precise course from the pilot camera, every 2 s. All four: the ship stays in frame, no black frames, nothing through the ground, gates turn green / blue as designed. Sky Racer's camera is closest (the ship biggest), Galleon's farthest and highest. Classic at the H2 hairpin (t 41-43 s, 6 m/s) shows the ship side-on: v1's free camera does not recentre below `RecenterMinSpeed` |
| `controls_pass1/<scheme>/stills_<scheme>.png` | Start, slalom, drift / boost, hairpin apex, climb, finish, broadside: pilot and wide views, all framed. Sky Racer's drift still shows the banked slide through the gate. In the broadside stills the ship is side-on with the target sphere above the deck |
| `contact_galleon.png`, `contact_pointfly.png` vs `contact_classic.png`, `contact_skyracer.png` | Galleon and Point & Fly trail a thick fan-wash smoke column through the whole course; Classic and Sky Racer show it only in the broadside orbit. Same FX code (v1 `abs(FanThrust)`): their speed / heading loops keep the fans working at cruise. Visual, not a bug |
| `controls_pass1/xgrab/x_galleon_0*.png` | Galleon HUD: telegraph row ASTERN STOP SLOW HALF FULL with the ordered notch inverted, speed rule with the order marker, HELM row (needle, deg/s), STATIONS tag and the PORT reload bar in the broadside grab |
| `controls_pass1/xgrab/x_skyracer_03_slalom_1.png` | Sky Racer DRIFT row: charge bar with the tier marks, tier "I" shown. The `02_drift_boost` grab came late (the X grab lags the request by 5-8 s of wall time) and shows an empty row |
| `controls_pass1/xgrab/x_pointfly_02_slalom_1.png`, `x_pointfly_07_broadside_1.png` | Point & Fly overlay: crosshair and nose marker in steering, the gun ring on the target with the LOCK tag and the heading strip at the top in the broadside. Classic and Point & Fly keep the v1 panel |
| all `xgrab` grabs | Two debug lines such as "[0059] False / [0058] False" at the top left of the viewport: a PrintString from a non-airship Blueprint. Cosmetic, unrelated |

### Issues

| # | Class | Scheme | Issue | Evidence | Status |
|---|---|---|---|---|---|
| 1 | HARNESS (acceptance) | Classic | as_43 `a3_deck_stand` fails on the scheme build (3.13-3.17 m in 10 s, limit 1.5 m) | Deterministic per build. The wind seed `GetUniqueID() % 97` is 56 on the scheme build and 51 on v1 (fit above); the flight code is v1 | open: the lead decides (seed-independent `a3`, e.g. wind off or a fixed seed for that check). Threshold untouched. **Closed in the follow-up** (F-D, then Fix2: the wind sway is off for the whole as_43 run; a3 0.009 m) |
| 2 | HARNESS | Classic | as_43 `f2_boost_path` +5.98 m/s in pass 1 (limit 5.0) | Same build, re-run +4.86; v1 +4.83. The obstacle contact point moves with the hover-phase offset (8.4 m in pass 1) | noise of the test; passes on the re-run. Since the follow-up's Fix2 the run is the same every time and f2 fails at +5.35 m/s: a v1 limit (section "Follow-up", "Fix2") |
| 3 | HARNESS | all | Start-pose drift: the reset leaves the shaped throttle decaying | Course times 0.04-0.67 s faster than the sim (table above); "drifted 15 m", "not at rest 4 m/s" warnings | not fixed (the candidates' ranking is unchanged); fix for the next pass in that section |
| 4 | HARNESS | Galleon, Sky Racer, Point & Fly | 5.4 cases not covered: held-W telegraph, drift with / without W, client HUD tier, 10 / 90 deg camera steps, 40-deg aim | The bench adapters tap the telegraph and set absolute headings | open: add dedicated runs in the verify pass if the winner needs them |
| 5 | HARNESS | all | The two scheme pairs ran in different editor sessions, so different wind seeds | Classic + Galleon session 1, Sky Racer + Point & Fly session 2 | noted. It affects only low-speed segments (wind fades out at 30 m/s) |
| 6 | HARNESS | all | The X grab lags the still request by 5-8 s of wall time | `xgrab/log.txt` timestamps | noted |
| 7 | FEEL | Point & Fly | The gun lock holds the target 7.1 deg aft of the port beam in a steady orbit (bench 2.6) | The hull lags its sent heading target by 4.9 deg at 16.4 deg/s; in arc and firing solution still 100 % | if it wins: check the lock lead (`PFLockLeadTime` × the heading-rate estimate) or add a yaw-rate feed-forward to `ComputeHeadingSteer` |
| 8 | FEEL | Point & Fly | Stopping a 49 deg/s turn on a fixed target overshoots 8.5 deg, settles in 1.8 s | `m9` drift exit frames | if it wins: more braking lead in the heading loop for fast stops (`PFHeadingLead`, `PFHeadingDecelDeg`) |
| 9 | FEEL (v1) | Classic | The camera shows the ship side-on in slow hairpins | `contact_classic.png` t 41-43 s | v1 behaviour, Classic stays v1 |
| 10 | HARNESS | all | M10 cosmetics one frame after the control | (a) above | inside the band, no action |

Nothing is BLOCKING, so there were no fix rounds and no as_50 re-runs.

### Files

| What | Where |
|---|---|
| Stable copy of the pass-1 results (use this) | `Saved/Airship/controls_pass1/` (copy of `Saved/Airship/controls/` at 00:10 UTC 2026-11-23) |
| Session-1 folder as interrupted (Classic, Galleon and the stopped Sky Racer attempt) | `Saved/Airship/controls_bak_230717/` |
| as_43 runs used above | `Saved/Airship/val_pass1_2227`, `val_rerun1_2333` (also copied to `val`, the current build's as_43), `val_expA_2353`, `val_v1build_2344`, `val_ref_oldbuild_1755` |
| Runner logs | `_AirshipWork_logs/run_controls_pie_1.log`, `run_controls_pie_rerun_sky_pf.log`, `run_controls_as43_rerun1.log`, `run_v1_ab_test.log`, `run_expA_test.log` |
| Analysis scripts (python3 -B) | `_AirshipWork_logs/scratch/controls/`: `val_diff.py` (as_43 frame comparison), `wind_fit.py` (wind seed fit), `recompute.py` (metrics from raw frames), `scheme_checks.py` (5.4 checks), `m12_beam.py` (orbit geometry), `make_tables.py` (the tables above) |

## Final

The verify step of the polished build, with Point & Fly (id 3) as the default scheme and the polish P0-P7 of
`CPP_NOTES.md` 14.12 / `SCHEME_POINTFLY.md` "Polish after judging". Written 2026-11-23 02:15 UTC by the verify step.
Clone `/mnt/new_partition/UnrealProjects/_AirshipWork`, branch `claude/project-thread-0emzt1`, C++ uncommitted on
`8f01bca`. The polish build (01:02 UTC, `_AirshipWork_logs/build_010229.log`, clean, no new warnings) is what sessions
1-3 ran; session 4 ran the same build plus the one HUD fix below (`build_020125.log`, issue F1).

### Summary

* **Point & Fly is the default and verified.** A fresh PIE ship is in Point & Fly (3). It ran 17/17 standalone runs
  and 9/9 client-pilot runs, 0 script errors, and every maneuver value equals the polished bench prediction
  (`sims/pointfly_metrics.json`) to the printed digits. Both bots finish every course with 0 missed gates, as host and
  as client at 100 ms.
* **Every polish change does what it was built for:**
  * P2: the m9 drift exit overshoots 1.67 deg (pass 1: 8.63). The turn onset is unchanged.
  * P1: the kick snake averages 48.9 m/s (pass 1 bench: 71.5; W held: 48.0). The 180 deg reversal keeps its kick.
  * P3: a 360 deg mouse orbit at rest turns the hull 0 deg. W then turns the ship to the camera.
  * P4: Aim without Fire never locks (0 deg swing, 0 m off the line). With Fire injected every frame it locks after
    0.23 s: the first press fires a broadside, and that broadside arms the lock (this build never reads Fire as held;
    fixed in the follow-up, F-A).
  * P5: M12 holds the target 4.7 deg aft of the beam (pass 1: 7.4).
  * P6, P7: overlay sizes, the ±180 deg strip and both hints are visible in the HUD grabs.
* **One HUD bug found and fixed (F1):** the boarding hint's text ran past its plate, and the look hint's tag lost its
  right padding. The text width is now measured at the viewport's DPI scale. Built clean, seen fixed on the client.
  No flight code changed.
* **Classic is still v1:** `Scheme check` 0 differences, and every run above 30 m/s is identical to pass 1 frame by
  frame. as_43 under Classic: 24/25. The failure is the known wind-seed `a3_deck_stand` (seed 57 on this build, fit
  100 %). The follow-up made as_43 independent of the seed: a3 passes, f2 fails on every run (section Follow-up, Fix2).
* **as_43 and as_45 under Point & Fly** fail only checks written for v1's camera and single HUD widget: the overlay is a
  second widget, a camera set steers, and D is the sidestep. Boarding, replication, exit, death, riders and the host
  flying all pass. as_45 Classic: 21/22, the same as the multiplayer step (follow-up, with ship 2 set to Classic too:
  22/22).

### Sessions

| # | When (UTC) | Play mode | What ran | Result | Output |
|---|---|---|---|---|---|
| 1 | 01:14-01:44 | Standalone | `run_controls_pie2.sh "{'schemes': [3, 0], 'xgrab': True}" final`: as_43 (it sets Classic itself since the polish), then as_50 for Point & Fly and Classic with HUD X grabs | as_43 Classic 24/25 (wind seed, below); Point & Fly 17/17 runs, Classic 17/17, 0 script errors, `Scheme check` 0 differences | `Saved/Airship/controls/`, `Saved/Airship/val_final_classic/`; log `_AirshipWork_logs/run_controls_final_011452.log` |
| 2 | 01:44-01:52 | Standalone | `_AirshipWork_logs/run_polish_checks.sh`: as_43 with `AS43_SCHEME = 3` (the new default), then `scratch/controls/final/as_50p_polish.py`: the polish checks the as_50 protocol does not cover, run on the as_50 machinery (fresh-PIE default, P1 snake and reversal, P3 parked look, P4 lock arming, P7 hint, every scheme's `check` list) | as_43 Point & Fly 23/25 (both failures by design, below); 9/9 polish runs OK | `Saved/Airship/val_final_pf/`, `Saved/Airship/controls_polish/` (`polish_checks.json`, `xgrab/`); log `run_polish_checks_014443.log` |
| 3 | 01:52-02:01 | Listen, 2 players | `KEEP_CONTROLS=1 SKIP_43=1 run_controls_pie2.sh "{'schemes': [3], 'net': 'listen'}" listen` (the client pilots, 100 ms each way) | 9/9 runs OK; the client flies every course without a missed gate | lat100 values merged into `Saved/Airship/controls/pointfly/metrics.json`; log `run_controls_listen_015230.log` |
| 4 | 02:01-02:07 | Listen, 2 players | build of the HUD fix, then `_AirshipWork_logs/run_as45_pf.sh`: as_45 with the ship in Point & Fly, then again in Classic (one editor session) | build clean (10 s); as_45 Point & Fly 18/22, Classic 21/22, every failure by design (below); the HUD fix seen on the client | `Saved/Airship/mp_final_pf/`, `Saved/Airship/mp_final_classic_polish/` (this run's Classic folder; `mp_final_classic/` now holds the follow-up run); log `chain_after_listen.log`, `run_as45_*.log` |

The clone's play settings were set back to Standalone (`set_play_mode.sh standalone`) with the editor closed at the end.

### Acceptance

| Check | Result | Verdict |
|---|---|---|
| Default scheme in a fresh PIE | Before any switch: `GetControlScheme` = POINT_FLY on the ship, telemetry `Scheme` 3, and `[01.48.05:220] Aura.Airship.Scheme: BP_AirshipPawn_C_0: Point & Fly (3), active Point & Fly (3)` (session 2 log `Saved/Logs/Aura-backup-2026.11.23-01.52.17.log`) | met |
| `Aura.Airship.Scheme 0` + `check` | Session 1: `Classic (v1), 0 difference(s) from the class defaults` (`controls/as50_result.json` `final_check`); session 2 again 0 | met |
| Galleon / Sky Racer `check` lists | Galleon 82, Sky Racer 114 differences: none of them is `DriftBoostCapSpeed`, `PFParkSpeed`, `PFLockArmTime` or `PFLockLeadTime`. Point & Fly lists 41, among them `DriftBoostCapSpeed = 4800`, `GyroYawMax = 1.0`, `KrSteady = 5.5`, `AlphaYawMaxSteady = 1.5` (the polish preset) | met |
| Inertia line (5.4) | X = 6.8586e10, Y = 1.0998e10, Z = 6.5744e10 kg cm², COM (-170, 0, 0) cm: the same as pass 1 | met |
| as_43 under Classic (session 1) | 24/25. `a3_deck_stand` fails: the unpiloted ship drifts 2.32 m in 10 s (limit 1.5). The v1 wind sway again: fitted over all 97 seeds (`scratch/controls/wind_fit.py`), seed 57 explains 100 % of the hover push (residual 0.30 of 6.02 cm/s²). The polish added reflected objects (`IsPFParked`, new properties), so the ship's `GetUniqueID() % 97` moved again (v1 build 51, pass-1 build 56, now 57). `f2_boost_path` passes (+4.84 m/s, v1 +4.83). `e_steer` is v1 to 0.01 deg/s (35.16) | same known harness issue as pass 1 (issue 1); the flight code is v1 |
| as_43 under Point & Fly (session 2, `AS43_SCHEME = 3`) | 23/25. `a3_deck_stand` now passes (0.04 m: Point & Fly holds station at rest). Two checks fail by design, see the next table | the default scheme is not what as_43 was written for |
| Classic as_50 against pass 1 | 76 of 107 metric keys identical; every run above 30 m/s identical frame by frame (m4_m5 turn, m9 drift, the boost: 0.000 m/s, 0.000 deg/s difference). The 31 that moved are low-speed values the wind seed changes: M1 at 2 s 22.61 (pass 1 22.91, sim 22.55), M6 nose dip -16.79 (-16.50, sim -16.58), sloppy course 0 missed (2; sim 1), sloppy M12 in arc 68.9 % (66.6; sim 68.8). Shaped controls identical in every run except one frame of m3_brake's throttle decay (the stop came a frame earlier) | Classic unchanged |
| Hover with the gyro at 1.0 (no wheel / fan buzz) | All `settle` segments of Point & Fly (975 frames at rest, no input): shaped Steer 0.000, no sign flips, turbine yaw 0.0 deg, yaw rate under 0.03 deg/s. The wheel moves only while it eases back from the previous run's turn (4.4 deg → 0 in 2 s) | met |

as_43 under Point & Fly, the two failures:

| Check | What happened | Why it is by design |
|---|---|---|
| `b2_hud_flying` (wants exactly 1 ship HUD widget) | 2 `AirshipHUDWidget`s in the viewport while flying, the on-foot overlay collapsed; after the exit and after the death both are gone (`b3`, `b4` pass) | In Point & Fly `ShowShipHUD` adds the full-screen overlay (`AddShipOverlay`: crosshair, nose chevron, strip, hints) as a second instance of the same class, next to the corner panel. Under Classic the check passes (1 widget) |
| `i_cannons` (both broadsides must reach the walls at y -93 / +143 m) | All 4 balls fired, recoil 45 cm on each gun, but they land far off: the hull pivoted at 30 deg/s through the whole phase (yaw 0 → -103 deg → +10 deg, `Steer` ±1.0) | as_43 aims each broadside by setting the control rotation to the hull's yaw ∓ 90 deg every frame. In Point & Fly a camera set without Aim is the heading target, so the ship turns after the camera, as a player's mouse would turn it. A Point & Fly broadside is fired with Aim held (free look), as M12 and the P4 checks do |

### Point & Fly: final PIE against the polished bench and pass 1

"Bench" = `sims/pointfly_metrics.json` (the polished prediction) unless a check of `sims/pointfly_checks.json` is
named. Session 1 frames, standalone (host pilot).

| Metric | Final PIE | Bench, polished (`pointfly_metrics.json`) | Pass-1 PIE | Note |
|---|---|---|---|---|
| M1 time to 80 % of top speed (s) | 3.267 | 3.267 | 3.267 | |
| M2 top speed / boost peak (m/s) | 47.97 / 86.93 | 47.97 / 87.03 | 47.97 / 86.93 | |
| M3 brake: stop time (s) / distance (m) | 2.47 / 56.86 | 2.47 / 56.85 | 2.47 / 56.86 | |
| M4 turn rate (deg/s), t63 / t90 (s), overshoot (%) | 34.98, 0.433 / 0.70, 0.5 | 34.98, 0.433 / 0.70, 0.5 | 34.98, 0.433 / 0.70, 0.5 | P2: the turn onset is unchanged |
| M5 U-turn time (s) / diameter (m) | 5.5 / 176.17 | 5.5 / 176.18 | 5.5 / 176.17 | |
| M6 nose dip under drive / boost (deg), brake flare (deg) | -3.95 / -5.2, 5.79 | -3.95 / -5.2, 5.82 | -3.95 / -5.2, 5.75 | |
| M7 climb / sink (m/s), +30 m step overshoot (m) | 12.01 / 14.97, 5.7 | 12.01 / 14.97, 5.7 | 12.01 / 14.97, 5.7 | |
| M8 strafe speed (m/s), t90 (s) | 14.3, 0.767 | 14.33, 0.767 | 14.29, 0.767 | |
| M9 drift slip at 2 s (deg), speed kept (%) | 42.27, 100 | 42.27, 100 | 42.27, 100 | |
| M9 drift exit kick, measured (m/s) | **4.84** | 4.84 | 4.71 | P1: the M9 drift ends far below the 48 m/s cap, so the full 6.0 m/s is still paid; the +0.13 comes from P2's quicker exit (the bench predicted it) |
| M9 drift exit: overshoot past the target (deg) / within 0.5 deg after (s) | **1.67 / 1.03** | 1.67 / 1.07 (`pointfly_checks.json` exit) | 8.63 / 1.8 | P2 |
| M10 turn on screen / server (frames) | 1 / 1 | 1 / 1 | 1 / 1 | wheel, turbine, nozzle 1 frame (sim 0): engine tick order, as pass 1 (a) |
| M11 precise: time (s), gates missed, line error mean (m) | 58.93, 0, 2.75 | 59.13, 0, 2.74 | 58.93, 0, 2.71 | 0.20 s: the start-pose drift (9.1 m) |
| M11 sloppy run 1: time (s), gates missed, line error mean (m) | 59.5, 0, 1.29 | 59.33, 0, 1.06 | 59.6, 0, 1.28 | |
| M11 sloppy, 3 runs: times (s), gates missed | 59.5 / 59.5 / 59.5, 0 / 0 / 0 (median 59.5 s, line error 1.29 m) | - | 59.6 / 59.6 / 59.57, 0 / 0 / 0 | |
| M12 precise: in arc / firing solution (%) | 100 / 100 | 100 / 100 | 100 / 100 | |
| M12 precise: target off the beam, mean (deg) | **-4.72** | 0.14 (bench camera); **-4.71** with the PIE-calibrated camera (`m12cam`) | -7.39 | P5 |
| M12 sloppy: target off the beam, mean (deg) | **-4.71** | -3.54; **-4.70** (`m12cam`) | -7.32 | P5 |
| M12 precise / sloppy: control yaw off the port beam (deg) | +1.99 / +1.93 | +1.99 / +1.94 (`m12cam`) | -0.48 / -0.54 | P5 |
| M12 precise / sloppy: gun lock on, % of orbit frames | 96.9 / 96.4 | - | 97.0 / 96.4 | P4: first fire 2.03 s, first lock 2.30 / 2.67 s |
| M12 shots fired (precise / sloppy) | 43 / 43 | 40 / 40 | 43 / 43 | |

Every other M1-M10 key equals the bench as in pass 1 (`controls/compare.md`). The only `!` cells are the M10 cosmetics
(1 frame, engine tick order, pass-1 deviation (a)) and M12 `beam_yaw_mean_deg`, whose bench value uses the bench camera;
the PIE-calibrated camera of `m12cam` predicts -4.71 / -4.70 deg and PIE gives -4.72 / -4.71.

### The polish checks (P0-P7)

Bench = the same input sequence run on the bench (`scratch/controls/final/bench_polish_pie.py`, or the named
`pointfly_checks.json` check). Session 2 unless noted.

| # | Check (`pie_checks` of the polish step) | PIE | Bench | Pass 1 | Verdict |
|---|---|---|---|---|---|
| P0 | Fresh PIE prints Point & Fly (3); `Scheme 0` + `check` 0 differences; Galleon / Sky Racer lists without the new tunables | see Acceptance | - | Classic was the default | met |
| P2 | m9 drift exit: overshoot past the camera's heading, time to stay within 0.5 deg (session 1 `m9`) | 1.67 deg, 1.03 s | 1.67 deg, 1.07 s | 8.63 deg, 1.8 s | met |
| P2 | M4 turn onset t63 / t90, overshoot (session 1) | 0.433 / 0.70 s, 0.5 % | 0.433 / 0.70 s, 0.5 % | same | met (unchanged) |
| P1 | M9 exit kick as measured (2 frames after the drift ends minus 1 before) (session 1) | 4.84 m/s | 4.84 (server pays 6.0) | 4.71 | met |
| P1 | Kick snake: from cruise, 30 s of brake-drifts (camera ±90 deg, X held 1.23 s, 0.1 s gaps), mean ground speed 4-30 s | **48.91 m/s** (22 drifts, peak 50.2) | 48.91 (`kick`: 48.75; W held 47.97) | 71.5 (bench, cap off) | met |
| P1 | 180 deg brake-drift reversal (camera set 179 deg round, X held until the drift ends) | speed 47.97 → 7.86 → 47.86 m/s at 8 s; at the drift end (3.77 s) +5.37 m/s in one frame (`exit_kick` measure 5.20) | 7.86 / 47.86, +5.37 / 5.20 (server pays 6.0) | same | met: the reversal keeps its kick |
| P3 | At hover, no keys, `IA_AirshipLook` injected for 4 s (the camera orbits 359.5 deg) | hull turned 0.00 deg, `IsPFParked()` true in 100 % of the frames; 2 s later still 0.00 deg | 0 / 0 deg | 111 / 100 deg (bench) | met |
| P3 | Then a look 120 deg right (injected look) and W held 8 s | the first W frame sends heading 119.99 deg (the camera's yaw); on the heading within 5 deg after 3.3 s, overshoot 0.04 deg; not parked any more | 3.3 s, 0.03 deg | - | met |
| P3 | At rest, the control rotation set from outside to +60 deg (no look input) | the hull turns 59.93 deg (within 5 deg after 2.13 s), parked the whole time | 59.93 deg, 2.13 s | - | met: absolute sets still steer |
| P4 | Cruise, Aim held 3 s with the camera 60 / 120 deg off the port bow, no Fire, then the camera back on the course | `bGunLock` 0 frames, free look 90 / 90 frames, heading swing 0.00 deg, track offset 0.00 m (both bearings) | 0 frames, 0.4 deg, 0.15 m | 26.9 deg, 62 m (bench) | met |
| P4 | The same at 60 deg with Fire held (injected every frame) | lock on after 0.23 s, 83 of 90 frames; the lock swings the beam onto the aim: 26.86 deg, 62.8 m. What arms it is the broadside of the first injected press (`OnFireInput`, Started), not Fire held, which this build never reads (fixed in the follow-up, F-A): nothing else could arm it, since the run starts with 12 s of cruise and no earlier shot. The run's `shots_fired` 0 is no measurement: the harness counts balls only in m12 runs (`count_balls`) | 83 frames, 26.96 deg, 63.1 m | - | met |
| P4 | M12 (session 1): lock on in the orbit, first fire before the first lock | 96.9 % / 96.4 % of 2250 orbit frames (100 % after the run-in); first broadside 2.03 s, first lock 2.30 / 2.67 s | - | 97.0 / 96.4 % | met |
| P5 | M12 target off the port beam, mean (session 1) | -4.72 / -4.71 deg | -4.71 / -4.70 (`m12cam`, harness bot) | -7.39 / -7.32 | met |
| P5 | Control yaw off the port beam (`m12_beam.py` geometry) | +1.99 / +1.93 deg | +1.99 / +1.94 | -0.48 / -0.54 | met |
| P5 | M12 in arc, firing solution | 100 / 100 % (both bots) | 100 / 100 % | 100 / 100 % | met |
| P6 | Overlay sizes (session 1 grabs) | crosshair arms 24-25 px, 2 px lines; nose chevron 18 px (21 px with the outline); gap line amber, 2 px with an ink outline | - | 14 / 10 px, 1 px ink | met |
| P6 | Broadside strip (session 1 `x_pointfly_07_broadside_1.png`) | the bow triangle at the strip centre, the heading-target diamond above it, ticks every 30 deg over ±180, both guns' arcs (port arc ink: the port guns were reloading, 0.4 s on the panel; starboard arc grey), the aim ring inside the port arc, `LOCK` in the 16 pt tag with the swing chevron | - | ±60 deg strip, edge arrows | met |
| P6 | Parked (session 2 `x_p3_orbit_parked_1.png`) | crosshair faded, no gap line while the camera orbits | - | - | met |
| P7 | Boarding hint (session 2 `x_p0_boarded_1.png` at boarding, `x_p3_orbit_parked_1.png` 10 s later) | shown at boarding and still shown 10 s later (no Aim held yet); gone in the grab 51 s after boarding (`x_p7_look_hint_1.png`, the 45 s limit) | - | 8 s | met, but its text overflowed the plate: fixed, see Issues |
| P7 | `HOLD RMB / LB TO LOOK` (session 2 `x_p7_look_hint_1.png`) | shown under the crosshair while steering with the camera 89 deg off the nose, before any Aim | - | - | met (the same plate overflow, smaller) |

### Listen pass: the client pilots Point & Fly (session 3)

Play As Listen Server with 2 players; `Aura.Airship.Board 1` put the client's character (`BP_MyCharMech_C_1`) at the
helm; `Net PktLag=104` on both worlds (100 ms of game time at the measured 30 fps). The scheme was confirmed on the
server and on the client's copy (`GetControlScheme` POINT_FLY and telemetry `Scheme` 3 on both). 9 of 9 runs OK,
0 script errors, 0 missing telemetry fields, 0 hull hits, 0 input-delay frames on the client (`k0` = 0). The values are
merged into `Saved/Airship/controls/pointfly/metrics.json` (`meta.listen_pass`); the standalone folder before the merge
is `Saved/Airship/controls_bak_015230/`.

| Metric (client, 100 ms each way) | PIE | Bench (`pointfly_metrics.json` lat100) |
|---|---|---|
| M10 server turn / client screen turn / client screen speed (frames) | 6 / 10 / 11 | 5 / 8 / 8 |
| M10 wheel, turbine, nozzle (frames) | 1 / 1 / 1 | 0 / 0 / 0 |
| M11 precise: time (s), gates missed, line error mean (m) | 59.7, 0, 1.46 | 60.1, 0, 1.38 |
| M11 sloppy, 3 runs: time (s), gates missed | 58.53 / 58.87 / 58.57, 0 / 0 / 0 (line error 3.49 / 3.97 / 3.68 m) | 58.83, 0 (3.38 m) |
| M12 precise: in arc / firing solution (%), shots | 100 / 100, 39 | 100 / 100, 40 |
| M12 sloppy: in arc / firing solution (%), in range (%), speed ok (%) | 100 / 97.7, 99.3, 98.4 | 100 / 99.8, 100, 99.8 |
| M12 target off the port beam, precise / sloppy (deg) | -8.93 / -9.00 | -4.03 / -7.55 (bench camera) |

* **Racing over the network works as predicted:** both bots finish every client course without a missed gate, within
  0.4 s of the bench.
* **The client sees its inputs 2-3 frames later than the bench says** (screen turn 10 vs 8 frames, speed 11 vs 8). The
  bench has no physics-replication smoothing on the client copy (`TEST_PROTOCOL.md` 7, `sims/README.md`); PktLag was
  104 ms, not 100. Server response 6 frames (bench 5). This is the network path, not the scheme: every scheme sends the
  same RPC.
* **M12 beam offset:** the standalone pass showed that the bench camera puts the target 4.9 deg further forward than the
  real spring arm (precise: bench 0.14, PIE -4.72, PIE-calibrated bench -4.71). The same offset on the lat100 bench value
  gives -8.9 deg: PIE -8.93. Both port guns stay in arc in every frame.

### Multiplayer: as_45 with the ship in Point & Fly, then in Classic (session 4)

Listen server with 2 players, the fixed build. `as45_pf.py` / `as45_classic.py` set `AS45_SCHEME` (3 / 0: the
harness sets it on the server's ship in the settle phase) and only add records: the scheme on both machines at the end
of the client's hover, and `Strafe`, `Scheme`, `bHeadingTargetActive`, `HeadingTargetDeg`, `bFreeLook`, `bGunLock` in
every series sample. No check was changed. Reference: run 3 of the multiplayer step (2026-11-22, v1 build, now in
`Saved/Airship/mp_prev_020135/run3/`).

**The client pilots in Point & Fly:** at the end of its hover, `GetControlScheme` = POINT_FLY on the server's and on
the client's copy, telemetry `Scheme` 3 and `bHeadingTargetActive` true on both (the client sends a heading target, the
Point & Fly input path). In the keys phase (W and D injected into the client's Enhanced Input) the shaped throttle is
1.00 on both machines and the server ship goes from 0 to 32.5 m/s; D is the sidestep in Point & Fly: `Strafe` 1.00 on
both machines, `Steer` 0.03.

| Check | Run 3 (v1 build) | Point & Fly | Classic | Note |
|---|---|---|---|---|
| a0, a0b, a1 boarding out of range / on deck / client F | PASS | PASS | PASS | |
| b1_hud_board (1 ship HUD widget) | PASS | **FAIL** | PASS | by design: panel + overlay (as as_43 `b2`) |
| a2_hover_sync | PASS (0.92 cm mean) | PASS (0.50 cm) | PASS | |
| c_cannons | FAIL (the old impact measure) | **FAIL** | PASS | by design: the harness turns the client's camera ±90 deg without Aim, and Point & Fly turns the ship after it; all 8 balls fired, recoil and muzzle FX on both machines |
| b2_host_gun | PASS | PASS | PASS | |
| a3_keys_rpc (server `Steer` > 0.3) | PASS | **FAIL** | PASS | by design: D is the sidestep (`Strafe` 1.00 / 1.00); throttle 1.00 / 1.00, 0 → 32.5 m/s |
| a4_fly0 / a4_fly1 (DebugSetInput, no lag / 100 ms) | PASS | PASS | PASS | response delays as run 3 (server 0.066 / 0.166-0.2 s) |
| k1, k2, b3, a5 exit and board again | PASS | PASS | PASS | |
| d1, d2, d3 death on both, pilot ejected, HUD | PASS | PASS | PASS | |
| e0, e1, e2 second ship, two on deck, host boards | PASS | PASS | PASS | |
| e3_hud_host_flying (1 ship HUD widget) | PASS | **FAIL** | **FAIL** | by design: ship 2 comes from `Aura.Airship.Spawn` in the new default (telemetry `Scheme` 3 in both runs; the harness sets only ship 1), so the host's HUD is panel + overlay. The follow-up (F-E) sets ship 2 too: Classic 22/22 |
| e4_host_fly_rider | PASS | PASS | PASS | |
| Total | 21 / 22 | 18 / 22 | 21 / 22 | every failure explained by the scheme; 0 script errors |


### Issues found in the verify step

| # | Class | Issue | Evidence | Status |
|---|---|---|---|---|
| F1 | BUG (polish P7 / P6, Point & Fly HUD) | The boarding hint's text ran past its dark plate: "Q/E TU**RN**" and "X / B IN A TURN: D**RIFT**" were drawn over the scene, hard to read on sky or platforms; the `HOLD RMB / LB TO LOOK` tag lost its right padding. The plates were sized with the text width measured at scale 1, but the text is drawn at the viewport's DPI scale (about 1.12 in the 2990 x 1170 PIE viewport, from the plate padding in the grab), where the text came out about 7 % wider than measured (glyph advances are rounded at the scaled font size) | `controls_polish/xgrab/x_p0_boarded_1.png`, `x_p7_look_hint_1.png`; crops `final_media/hud_pointfly_boarding_hint_before_fix.png` | **fixed**: new `MeasureWidthAtScale` (`FSlateFontMeasure::Measure` at the paint geometry's layout scale, divided by it) for the overlay's tags and the two hint rows in `PaintPointFlyOverlay`. The v1 panel keeps `MeasureWidth`, so Classic's HUD is unchanged. Built clean 02:01 UTC (`build_020125.log`, `AirshipHUDWidget.cpp` only, no warnings). Verified in session 4: the client's boarding grab (`mp_final_pf/xgrab/x_board_client.png`, a 2533 x 1358 window, another DPI scale) shows both rows inside their plates with even padding |
| F2 | HARNESS (acceptance, open since pass 1) | as_43 `a3_deck_stand` under Classic: 2.32 m in 10 s (limit 1.5) | v1 wind seed `GetUniqueID() % 97` = 57 on this build (fit 100 %) | open: the lead decides (wind off or a fixed seed for `a3`). Threshold untouched. **Closed in the follow-up** (F-D, then Fix2: wind off for the whole as_43 run; a3 0.009 m) |
| F3 | HARNESS | as_43 run under Point & Fly fails `b2_hud_flying` and `i_cannons` | the overlay is a second widget; a camera set steers | by design. as_43 / as_45 set Classic by default (`AS43_SCHEME` / `AS45_SCHEME` 0). To cover Point & Fly in as_43, `b2` would have to skip the overlay widget and `i_cannons` would have to hold Aim |
| F4 | HARNESS (pass-1 issue 3) | Start-pose drift: Point & Fly starts runs 9.0-9.1 m ahead (shaped throttle still decaying), "not at rest" 0.39-0.43 m/s | `as50_log.txt` | not fixed; course times 0.2 s faster than the bench, as in pass 1 |
| F5 | NETWORK (information) | The client sees its turn and speed 2-3 frames later than the bench predicts at 100 ms | listen pass M10 | the same RPC path for every scheme; the bench has no replication smoothing |
| - | cosmetic, unrelated | "[0059] False / [0058] False" at the top left of every grab: a PrintString from a non-airship Blueprint | all grabs | as pass 1 |

No flight-code bug was found: every Point & Fly maneuver value equals the polished bench, and every polish mechanic
does what the bench predicted.

### Images and videos

| File | What it shows |
|---|---|
| `controls/pointfly/course_pointfly.mp4` | The polished Point & Fly on the gate course, precise bot, pilot camera (final build, session 1) |
| `controls_pass1/compare_course_2x2.mp4` | The four schemes side by side on the course (pass 1, the judging input) |
| `controls/pointfly/contact_pointfly.png`, `stills_pointfly.png` | Course every 2 s and the key moments (pilot and wide views): the ship stays framed, gates turn as designed, the broadside shows the hull side-on with the target above the deck |
| `final_media/hud_pointfly_steering_slalom.png` | Steering: 24 px crosshair, 18 px nose chevron, amber gap line between them |
| `final_media/hud_pointfly_broadside_lock.png` | Broadside: ±180 deg strip with the bow at the centre, both gun arcs, the aim ring in the port arc, the LOCK tag |
| `final_media/hud_pointfly_aim_no_fire.png`, `hud_pointfly_aim_fire_lock.png` | P4: Aim alone 60 deg off the bow (no lock, the ship holds its line) and the same with Fire held (LOCK, the beam swings onto the aim) |
| `final_media/hud_pointfly_parked_orbit.png` | P3: the camera orbiting the parked ship (faded crosshair, no gap line, boarding hint still up) |
| `final_media/hud_pointfly_look_hint.png` | P7: HOLD RMB / LB TO LOOK under the crosshair while steering 89 deg off the nose |
| `final_media/hud_pointfly_boarding_hint_before_fix.png`, `hud_pointfly_boarding_hint_fixed_client.png` | F1: the boarding hint overflowing its plate, and fixed (client window, session 4) |

`final_media/` = `Saved/Airship/final_media/` (8-bit viewport crops of the X grabs; the full grabs are in
`controls/xgrab/`, `controls_polish/xgrab/`, `mp_final_pf/xgrab/`).

### Files

| What | Where |
|---|---|
| Session 1: Point & Fly + Classic as_50 (metrics, telemetry, chase frames, stills, videos, compare.md, X grabs), with the listen values merged | `Saved/Airship/controls/` (before the listen merge: `controls_bak_015230/`; pass 1 stays in `controls_pass1/`, and the live folder of pass 1 moved to `controls_prev_011452/`) |
| as_43 Classic / Point & Fly | `Saved/Airship/val_final_classic/` (`val/` now holds the latest as_43 run, section Follow-up), `Saved/Airship/val_final_pf/` |
| Polish checks | `Saved/Airship/controls_polish/` (`polish_checks.json`: every number above, frames included; `pointfly/telemetry.json` with `pk` = `IsPFParked()` per frame; `xgrab/`) |
| as_45 | `Saved/Airship/mp_final_pf/`, `Saved/Airship/mp_final_classic_polish/` (this step's Classic run; `mp_final_classic/` now holds the follow-up run; the multiplayer step's folder moved to `mp_prev_*`) |
| Runners and logs (`_AirshipWork_logs/`) | `run_controls_final_011452.log`, `run_polish_checks.sh` + `run_polish_checks_014443.log`, `run_controls_listen_015230.log`, `chain_after_listen.sh` + `.log`, `run_as45_pf.sh` + `run_as45_015601.log`, `build_020125.log` |
| Scripts (`_AirshipWork_logs/scratch/controls/final/`, python3 -B) | `as_50p_polish.py` (the polish checks on the as_50 machinery; `mock_polish.py` runs it on the mock editor), `as45_pf.py` / `as45_classic.py`, `final_analysis.py` (final vs bench vs pass 1, the m9 exit, M12 lock and beam, hover buzz), `listen_analysis.py`, `mp_analysis.py`, `bench_polish_pie.py` (bench predictions for the custom checks) |

## Follow-up (after the final review)

The verify step of the follow-up build: the five items F-A to F-E that the final review left open. Written 2026-11-23
03:35 UTC by the follow-up verify step. Clone `/mnt/new_partition/UnrealProjects/_AirshipWork`, branch
`claude/project-thread-0emzt1`, changes uncommitted on `421646d`. Build 02:51 UTC (`_AirshipWork_logs/build_025149.log`):
clean in 56 s, `AirshipPawn.cpp` compiled alone, only the two known `bIsFocusable` deprecation warnings
(`MainMenu.cpp:24`, `MainMenu2.cpp:38`). No source file changed after the build.

### What changed

| # | Change | Where |
|---|---|---|
| F-A | **Fire held arms the gun lock.** `IA_AirshipFire` gets a value binding (`BindActionValue`) next to its press binding, so `Button(FireAction)` is true while LMB / RB is held. The lock is now armed while Fire is held, or for `PFLockArmTime` (6 s) after the pilot's own broadside. The shot is still the press (`Started`): holding Fire fires once | `AirshipPawn.cpp` (`SetupPlayerInputComponent`, the comment in `GatherLocalInput`), `AirshipPawn.h` |
| F-B | **A hit no longer ends the parked free look.** Parking still starts only below `PFParkSpeed` (3 m/s) with no W/S, A/D, Q/E or boost held. Once parked it holds at any speed until one of those keys, Aim, or an outside camera set above 3 m/s. After a hit the heading holds (the heading loop turns a knocked hull back) and the camera stays where it looked | `AirshipPawn.cpp` (`UpdatePointFlyCamera`), `AirshipPawn.h` |
| F-C | Tooltip of `bFreeLook` (comment only): false in steering mode and in the parked free look | `AirshipTypes.h` |
| F-D | **as_43 `a3_deck_stand`, harness only.** For a3 the PIE ship's wind sway (`WindLateralAccel`, `WindRollAccel`, `WindPitchAccel` on its flight component) is set to 0 and restored right after a3, and the hull's velocities are zeroed at the a3 start (no transform change). Thresholds unchanged. Fix2 (below) turns the wind off for the whole run instead and starts the flight path from the spawn pose | `scripts/ue/as_43_pie_validate.py` |
| F-E | **as_45, harness only.** `AS45_SCHEME` is applied to ship 2 too, on the server, as soon as `Aura.Airship.Spawn` has made it | `scripts/ue/as_45_pie_mp.py` |
| bench | F-B mirrored (`PARK_LATCH`) and a new check `push` | `sims/scheme_pointfly.py`, `sims/pointfly_checks.py` (+ `.json`) |

Classic, Galleon and Sky Racer are untouched: the new Fire value is read only by the Point & Fly camera
(`UpdatePointFlyCamera`), and the parking change is inside it.

### Summary

* **F-A works.** With Fire held for 10 s the lock stays on in all 110 frames after the broadside's 6 s window
  (6.3-10 s) and drops on the frame Fire is let go (10.0 s). Holding Fire fired one broadside only. A single tap still
  uses the P4 timer: the lock drops 6.0 s after the broadside.
* **F-B works.** Parked with the camera 120 deg right of the bow, the hull pushed to 6 m/s (5.5 s above 3 m/s) and
  knocked round at 70 deg/s: the ship stays parked in every frame, the heading target does not move, the hull swings
  24.6 deg and comes back to 0.1 deg, and the camera stays put. W then takes the camera's yaw on its first frame, and
  the ship is within 5 deg of it after 3.3 s. The polish build (bench) unparked and turned the ship 119.9 deg to the
  camera.
* **PIE matches the bench** (`pointfly_checks.json` `push` and the fix step's F-A predictions): knock 24.62 / 24.6 deg,
  back to 0.1 / 0.09 deg, W 3.3 / 3.3 s, lock times within one frame. Only the push fades a little faster in PIE
  (5.5 s above 3 m/s, bench 6.1 s).
* **No regression.** The final verify's runs (`p3_park`, `p3_abs`, `p4_aim60`, `p4_fire60`) give the same values; a
  fresh PIE ship is in Point & Fly; `Scheme check` lists Galleon 82, Sky Racer 114, Point & Fly 41 and Classic 0
  differences, as before. 9/9 runs PASS, 0 script errors.
* **as_45 under Classic: 22/22** (polish build 21/22). Ship 2 is Classic on both machines now, so
  `e3_hud_host_flying` passes.
* **as_43 under Classic: 24/25.** `a3_deck_stand` passes (1.371 m, limit 1.5 m; polish build 2.315 m) with the wind off
  for a3 only and restored after it. `f2_boost_path` fails (+5.98 m/s, limit 5.0 m/s): the known contact flake of
  pass 1. The quieter deck stand leaves the hull 3.7 m further to the side when it reaches `AS_Obstacle_1`, and there
  it meets the obstacle in its +5.98 m/s way, as in pass 1. The flight code is v1 (below). (Fix2, next bullet, shows
  it is a v1 limit rather than a flake.)
* **Fix2 (after the follow-up review, sessions 4-5): as_43 under Classic is 24/25 every time.** The harness now turns
  the wind sway off for the whole run and starts the flight path from the spawn pose at rest, so the run no longer
  depends on the build or on the deck phases. a3 passes at 0.009 m. f2 fails the same way in both runs (+5.35 m/s,
  limit 5.0): a v1 limit of the obstacle clip, not a flake (section "Fix2" below). No threshold or C++ changed.

### Sessions

| # | When (UTC) | Play mode | What ran | Result | Output |
|---|---|---|---|---|---|
| 1 | 03:12-03:16 | Standalone | `ONLY_43=1 _AirshipWork_logs/run_controls_pie2.sh "{}" followup43`: as_43 with the harness default, Classic (`AS43_SCHEME` 0) | 24/25 (`f2_boost_path`) | `Saved/Airship/val/` (copy `val_followup_classic/`; the polish build's folder moved to `val_prev/`); log `_AirshipWork_logs/run_controls_followup43_031254.log` |
| 2 | 03:17-03:21 | Standalone | `_AirshipWork_logs/run_followup_checks.sh`: `scratch/controls/followup/as_50f_followup.py` on the as_50 machinery (Point & Fly, injected `IA_AirshipLook` / `IA_AirshipFire`, push and knock on the server hull) | 9/9 PASS, 0 script errors | `Saved/Airship/controls_followup/` (`followup_summary.txt`, `followup_checks.json`, `xgrab/`, `media/`); log `run_followup_checks_031755.log` |
| 3 | 03:24-03:27 | Listen, 2 players | `set_play_mode.sh listen 2` (editor closed), then `ONLY_CLASSIC=1 _AirshipWork_logs/run_as45_pf.sh` (`scratch/controls/final/as45_classic.py`) | 22/22, 0 script errors | `Saved/Airship/mp_final_classic/` (the polish build's run copied to `mp_final_classic_polish/` first); log `run_as45_followup_032406.log` |
| 4 | 03:40-03:44 | Standalone | Fix2: `ONLY_43=1 _AirshipWork_logs/run_controls_pie2.sh "{}" fix2_43` with the Fix2 harness, Classic | 24/25 (`f2_boost_path`), 0 script errors | `Saved/Airship/val_fix2_classic_1/`; log `run_controls_fix2_43_034027.log` |
| 5 | 03:44-03:48 | Standalone | Fix2: the same again (`fix2_43b`), to see whether f2 repeats | 24/25, 0 script errors. The ship's path is identical to session 4 in every sample up to the kill (0.000 cm, 0.000 m/s); only the cannonballs' and the wreck's flights differ (`i_cannons`, `j2`, `j3` pass in both) | `Saved/Airship/val/` (copy `val_fix2_classic_2/`); log `run_controls_fix2_43b_034416.log` |

After session 3 the clone's play settings went back to Standalone with the editor closed (`set_play_mode.sh
standalone`: `PlayNetMode=PIE_Standalone`, `PlayNumberOfClients=1`); sessions 4-5 ran in Standalone. L_AirshipTest was
not saved and no asset changed.

### F-B: a hit while parked (`p3_push`, session 2)

Hover with no keys (4 s settle); `IA_AirshipLook` turns the camera 120 deg right of the bow (2 s); then +6 m/s is added
to the server hull along the bow and, 1 s later, +70 deg/s of yaw toward the camera; 7 s with no key; then W for 8 s.

| Check | PIE | Bench, follow-up (`push`, latched) | Bench, polish build (no latch) | Verdict |
|---|---|---|---|---|
| Before the hit: parked; camera off the bow; hull turned | yes; 120.0 deg; 0.0 deg | yes | yes | met |
| The push: top forward speed; time above 3 m/s | 5.99 m/s; 5.5 s | 6.1 s | 7.0 s | setup met (>= 1 s) |
| Parked in the 7 s after the hit (210 frames, no key) | **100 %** | 100 % | 0.5 % | met |
| Heading target: largest change | 0.0 deg | - | - | met (limit 0.5 deg) |
| Hull turned toward the camera: peak (time after the push) | 24.62 deg (1.83 s) | 24.6 deg (1.83 s) | 119.9 deg (4.2 s) | met (limit < 60 deg) |
| Hull off the held heading after 7 s | **+0.1 deg** | +0.09 deg | +119.92 deg | met (limit 3 deg) |
| Camera moved | 0.0 deg | 0.0 deg | 0.0 deg | met (limit 1 deg) |
| Then W: heading target vs camera on the first frame; within 5 deg after; overshoot; end error | 0.0 deg; 3.3 s; 0.0 deg; 0.06 deg | -; 3.3 s; 0.0 deg; 0.1 deg | - | met |

The X grab 0.5 s after the knock (`controls_followup/media/fb_push_knock_still_parked.png`) shows the parked HUD at
6 m/s: faded crosshair, no gap line.

### F-A: Fire held arms the gun lock (`p4_firehold`, `p4_tap60`, session 2)

Cruise at 48 m/s, Aim held for 14 s with the camera 60 deg off the port bow. `p4_firehold`: `IA_AirshipFire` injected
in every frame of the first 10 s (one press, then held), then let go with Aim still held for 4 s. `p4_tap60`: Fire on
frame 0 only. t = 0 is the press.

| Check | `p4_firehold` (held 10 s) | `p4_tap60` (one tap) | Bench | Verdict |
|---|---|---|---|---|
| Broadsides (reload-alpha drops); balls | 1 at 0.0 s; 2 | 1 at 0.0 s; 2 | 1 | met: holding Fire never fires again |
| Lock on after | 0.233 s | 0.233 s | 0.233 s | met (limit 1.0 s) |
| Lock frames in the first 10 s | 293 of 300 | 173 of 300 | - | |
| Lock in the frames after broadside + 6.3 s while Fire is held | **110 of 110** | 0 of 110 (Fire up) | 110 of 110 | met (F-A) |
| Lock off at | **10.0 s** (Fire let go; expected max(10.0, 0 + 6) = 10.0 s) | 6.0 s (expected broadside + 6 = 6.0 s) | 10.0 s / 6.033 s | met (±0.2 s) |
| Lock back on after it dropped | no | no | - | met |
| Heading swing; heading change after the release | 26.88 deg; 0.0 deg | 26.86 deg; 0.0 deg | 26.9 deg; 0 deg | met (limit 2 deg) |

* The X grabs show it: 8 s after the press, 2 s past the old timer, the `LOCK` tag is under the crosshair with Fire
  held and gone after the tap, with the ship on the same swung heading in both
  (`controls_followup/media/fa_fire_held_8s_lock.png`, `fa_tap_8s_no_lock.png`, side by side
  `fa_fire_held_vs_tap_8s_small.png`).
* Side note, not a follow-up item: the one broadside came from the starboard pair in `p4_firehold` and from the port
  pair in `p4_tap60` (the frame-0 yaw kick, +0.18 / -0.17 deg, is that broadside's recoil). The harness turns the
  camera to port and presses Fire on the same frame. Reading the code (the runs do not log the aim side): the press aims
  from `GetPlayerViewPoint`, the view of the frame before, which still looked along the course; there the aim point is
  near the centreline, where `ComputeAimSide` keeps the side the guns had before (3 m hysteresis), and that depends on
  the run before. This is the unchanged v1 fire path: a press after the camera has turned fires the side it faces. The
  lock works from the camera's bearing, so both runs lock to port.

### Regression and scheme checks (session 2) against the final verify

"Final verify" = `Saved/Airship/controls_polish/polish_checks.json` (session 2 of section Final).

| Run | Follow-up build | Final verify | Verdict |
|---|---|---|---|
| `default`: a fresh PIE ship | Point & Fly on the server and the pilot (telemetry `Scheme` 3) | the same | met |
| `p3_park` orbit: camera travel, hull turn max, parked | 359.5 deg, 0.0 deg, 100 % | 359.5 deg, 0.0 deg, 100 % | same |
| `p3_park` pause, look 120 deg: hull turn, parked | 0.0 / 0.0 deg, parked | 0.0 / 0.0 deg, parked | same |
| `p3_park` W: first heading target, within 5 deg after, overshoot, end error | 119.998 deg, 3.3 s, 0.03 deg, 0.02 deg | 119.995 deg, 3.3 s, 0.04 deg, 0.01 deg | same (0.01 deg noise) |
| `p3_abs` outside set to +60 deg: hull turn, within 5 deg after, parked | 59.93 deg, 2.133 s, 100 % | 59.93 deg, 2.133 s, 100 % | same |
| `p4_aim60` Aim, no Fire: lock frames, swing, track offset, free look | 0, 0.0 deg, 0.0 m, 90 of 90 | 0, 0.0 deg, 0.0 m, 90 of 90 | same |
| `p4_fire60` Fire held 3 s: first lock, lock frames, swing, track offset | 0.233 s, 83 of 90, 26.86 deg, 62.76 m | 0.233 s, 83 of 90, 26.86 deg, 62.76 m | same |
| `final`: `Aura.Airship.Scheme 1/2/3/0`, each + `check` | Galleon 82, Sky Racer 114, Point & Fly 41 (with `DriftBoostCapSpeed = 4800`, `GyroYawMax = 1.0`), Classic (v1) 0 differences | the same counts | Classic = v1 |

`p4_fire60` is now armed twice over (its first press fires a broadside on frame 0, and Fire stays held), so it gives the
same numbers as before. The other differences are in the start values (start speed 0.002 instead of 0.0 m/s, yaw
0.001 deg): the reset, not the code.

### as_43 under Classic (session 1): 24/25

| Check | Follow-up | Polish build (`val_final_classic/`) |
|---|---|---|
| `a3_deck_stand`: ship drift in 10 s (limit 1.5 m) | **1.371 m, PASS** | 2.315 m, FAIL |
| `a3_deck_stand`: height change; pitch; roll; largest vertical speed | -0.015 m; -0.01..0.62 deg; -0.01..0.00 deg; 0.006 m/s | -0.028 m; -0.96..0.75 deg; -0.02..0.00 deg; 0.012 m/s |
| a3 start (F-D): hull velocity; angular velocity (both zeroed); pitch | -0.005 / -0.002 / -0.01 m/s; -0.01 / -0.28 / 0.01 deg/s; 0.62 deg | not zeroed; 0.63 deg |
| Wind sway (lateral cm/s², roll, pitch) | 25.0, 0.03, 0.015 → 0, 0, 0 at 28.0 s (a3 start) → back to 25.0, 0.03, 0.015 at 38.0 s (a3 end) | on all the time |
| `b_hover` (before a3, wind on): drift; pitch max | 1.17 m; 0.30 deg | 1.17 m; 0.30 deg (the same wind seed, 57) |
| `e_steer` yaw rate | +35.16 deg/s | +35.16 deg/s (v1) |
| `f2_boost_path`: vertical speed after the hit (limit 5.0 m/s) | **+5.98 m/s, FAIL** | +4.84 m/s, PASS |
| The other 22 checks | PASS | PASS |

The wind was off for a3 only: the harness logs it going to 0 at the a3 start and back at the a3 end (`val_log.txt`, the
two "a3 (F-D)" lines; `val_result.json` `setup.a3_still` and the a3 check's `harness` data), and the a3 summary ends
with "harness (F-D): wind sway off, hull velocity at the start [-0.005, -0.002, -0.01] m/s zeroed".

**What is left of the a3 drift** is the 0.62 deg nose-up pitch the ship has when the deck stand starts. v1 levels it in
about 2 s, and meanwhile the tilted lift pushes the hull aft to 0.15 m/s. v1 has no station keeping, so the hull coasts
on at that speed: 0.18 m after 2 s, 0.50 m after 4 s, 0.81 m after 6 s, 1.09 m after 8 s, 1.37 m at the end. The margin
to the limit is 0.13 m; the fix step's bench predicted about 1.0 m for this start pitch.

**Why `f2_boost_path` failed.** f2 boosts the ship along the as_30 path into `AS_Obstacle_1` at 91.6 m/s and fails if
the hull comes off it faster than 5.0 m/s upward. The bump depends on where the hull meets the obstacle, and that
depends on where the slow phases before it left the ship. This run and the polish-build run are identical up to the a3
start. The quieter deck stand ends 0.94 m from the polish-build position, the slow phases after it (deck walk,
boarding, lift, with the wind back on) grow that to 3.7 m by 69 s, and from there on, above 30 m/s, the two runs fly the
same path 3.7 m apart. All as_43 runs so far, at 80.0 s (0.2 s before the hit; heading about -80 deg, so x is the
sideways position):

| as_43 run (`Saved/Airship/`) | Build / harness | a3 drift (m) | Hull x at 80.0 s (m) | f2 vertical speed (m/s) |
|---|---|---|---|---|
| `val_followup_classic` (this run) | follow-up build, F-D harness | 1.371 | 346.05 | **+5.98 FAIL** |
| `val_pass1_2227` | scheme build (pass 1) | 3.166 | 347.51 | **+5.98 FAIL** |
| `val_rerun1_2333` | the same build, run again | 3.127 | 348.73 | +4.86 |
| `val_prev` (= `val_final_classic`) | polish build | 2.315 | 349.76 | +4.84 |
| `val_v1build_2344` | v1 | 0.817 | 355.92 | +4.83 |

The two failures met the obstacle at x 347.5 m or less, the three passes at 348.7 m or more. Pass 1 and its re-run
(same build, same harness) differ by 1.2 m here, so the check is not repeatable at this point; this run is 2.7 m on
the failing side of the nearest pass. Nothing in the flight code changed: the hover before a3 and the fast phases up to
the hit match the polish build (throttle top 49.52 m/s, steer +35.16 deg/s, boost peak 87.0 m/s), and `Scheme 0` +
`check` gives 0 differences. Making f2 independent of the slow phases
(for example by starting the boost run from a fixed pose) is a harness change for the lead to decide. No threshold was
touched, and as_43 was not re-run. (Done in Fix2, below: f2 then fails the same way every time.)

### as_45 under Classic (session 3): 22/22

| Check | Follow-up | Polish build (`mp_final_classic_polish/`) | Note |
|---|---|---|---|
| Ship 1 scheme | CLASSIC, set on the server ship at 0.07 s; at the end of the client's hover CLASSIC on both machines (telemetry `Scheme` 0, `bHeadingTargetActive` false) | the same | |
| Ship 2 scheme | `Aura.Airship.Spawn` at 89.27 s, set to CLASSIC on the server at 90.57 s; at the end of spawn2 (92.07 s) CLASSIC on the server and on the client (`setup.scheme_ship2` CLASSIC, `setup.scheme_ship2_both` {server: CLASSIC, client: CLASSIC}); the host presses F at 96.27 s (boarded at the 99.07 s check) | Point & Fly (telemetry `Scheme` 3) | F-E |
| `e3_hud_host_flying` | **PASS**: 1 ship HUD widget, on-foot overlay collapsed | FAIL: 2 widgets (Point & Fly panel + overlay) | F-E |
| `e4_host_fly_rider` | PASS: top 50.1 m/s; neutral z span 1.0 cm, largest pitch 0.30 deg | PASS: 47.9 m/s; 0.6 cm, 0.14 deg (ship 2 flew Point & Fly) | ship 2 now flies v1 |
| `a2_hover_sync` position error mean / max | 0.56 / 1.12 cm | 0.64 / 1.2 cm | |
| `a3_keys_rpc` steer client / server; server speed | 1.00 / 1.00; 0.07 → 32.34 m/s | 1.00 / 1.00; -0.10 → 32.68 m/s | |
| `a4_fly0` / `a4_fly1` top speed | 52.2 / 54.6 m/s | 52.2 / 54.5 m/s | |
| The other 16 checks | PASS | PASS | |
| Total | **22/22**, 0 script errors | 21/22 | |

### Fix2: as_43 independent of the build and of the deck phases (sessions 4-5)

The review of this follow-up (must fix): F-D made a3 pass, but in the same run f2 failed, so as_43 under Classic stayed
at 24/25. The as_43 phases run on with no reset, so the a3 change moved the ship for every later phase, and both a3
(1.371 of 1.5 m) and f2 sat close to their limits under v1. Fixed in the harness only
(`scripts/ue/as_43_pie_validate.py`); no threshold and no C++ changed.

| Change | Why | Knob (default) |
|---|---|---|
| v1's wind sway is off for the whole run: `WindLateralAccel`, `WindRollAccel` and `WindPitchAccel` of the run's ship go to 0 in the settle phase (0.0 s) and back in `finish()` (122.0 s); both are logged | v1 seeds the sway per ship by `GetUniqueID() % 97` (`AirshipFlightComponent.cpp:1608`), which moves with every build (seeds 51, 56, 57 so far), and v1 has no station keeping, so the unpiloted hull's drift in the deck phases changed from build to build. No check measures gusts. This replaces F-D's a3-only switch | `AS43_WIND_OFF` (True) |
| a3 starts at rest, as in F-D: the hull's velocities are zeroed, the transform is not touched | unchanged | `AS43_A3_AT_REST` (True) |
| The flight path (lift, throttle, steer, boost, brake: `c_lift` to `f2_boost_path`) starts from the ship's spawn x/y and yaw (0 m, 25 m, 0 deg), level and at rest, at its current height (the altitude hold is kept), with the pilot aboard. The bumps and the kill teleport the same way | the deck phases before it (as_30's cannons, exit and board2, plus as_43's a3 and a4) left the unpiloted hull 0-7 m off and moving at up to 0.4 m/s, and f2 depends on where the hull meets `AS_Obstacle_1` | `AS43_PATH_FROM_SPAWN` (True) |

An offline test of the three helpers on fake `unreal` objects passed before the runs
(`_AirshipWork_logs/scratch/controls/followup/test_as43_fix2.py`). Two runs of the same harness, against the earlier runs:

| Check | Fix2 run 1 (session 4) | Fix2 run 2 (session 5) | Follow-up (F-D) | Polish build |
|---|---|---|---|---|
| Total | 24/25 | 24/25 | 24/25 | 24/25 |
| `a3_deck_stand`: drift in 10 s (limit 1.5 m) | **0.009 m, PASS** | 0.009 m, PASS | 1.371 m, PASS | 2.315 m, FAIL |
| a3 start: pitch; hull speed before it is zeroed | 0.05 deg; 0.06 m/s | the same | 0.62 deg; 0.01 m/s | 0.63 deg; not zeroed |
| `b_hover`: drift in 10 s | 0.41 m | the same | 1.17 m (wind on) | 1.17 m |
| Ship at the lift start, before the reset | (-0.05, 24.99) m, at rest | the same | (-6.02, 25.00) m, 0.38 m/s (no reset) | (-4.31, 25.03) m, 0.17 m/s |
| `c_lift` gain / `d_throttle` top / `e_steer` rate / `f_boost_brake` peak | +38.4 m / 49.50 m/s / +35.16 deg/s / 87.0 m/s | the same | +38.4 m / 49.52 m/s / +35.16 deg/s / 87.0 m/s | as the follow-up |
| f2: hull 0.2 s before the hit (x = sideways, y = along the path) | 356.16, -69.80 m | the same | 346.05, -69.75 m | 349.76, -69.79 m |
| f2: speed at the hit; vertical speed after it (limit 5.0 m/s); rise (limit 8 m) | 91.6 -> 65.9 m/s; **+5.35 m/s, FAIL**; +5.9 m | the same (health 2000.0 -> 1872.118 in both) | 91.6 -> 80.3 m/s; +5.98 m/s, FAIL | 91.6 -> 75.8 m/s; +4.84 m/s, PASS |
| Every other check; script errors | PASS; 0 | PASS; 0 | PASS; 0 | PASS; 0 |

**a3 is fixed for good.** With no wind the hull is still when the deck stand starts (pitch 0.05 deg instead of 0.62),
and it moves 9 mm in the 10 s.

**f2 is v1 behaviour.** Nothing before the boost depends on the build or on the deck phases any more, and the two runs
gave the same hit to the printed digits, so f2 now fails every time, at +5.35 m/s against 5.0 m/s (the rise, +5.9 m,
is within its 8 m limit). Every as_43 run so far hits `AS_Obstacle_1` on the same frame (80.23 s) with the same attitude
0.2 s before it (roll 0.30 deg, pitch -17.53 deg); they differ only in where the hull is on that frame:

| as_43 run (`Saved/Airship/`) | Build / harness | a3 drift (m) | Hull at 80.0 s: x, y (m) | Speed at the hit (m/s) | f2 vertical speed (m/s) |
|---|---|---|---|---|---|
| `val_ref_oldbuild_1755`, `val_v1build_2344` (identical) | v1 build (seed 51) | 0.817 | 355.92, -68.78 | 91.6 -> 74.7 | +4.83 |
| `val_pass1_2227` | scheme build (seed 56) | 3.166 | 347.51, -69.01 | 91.6 -> 80.6 | **+5.98 FAIL** |
| `val_rerun1_2333`, `val_expA_2353` (identical) | the same build | 3.127 | 348.73, -69.04 | 91.6 -> 79.9 | +4.86 |
| `val_final_classic` | polish build (seed 57) | 2.315 | 349.76, -69.79 | 91.6 -> 75.8 | +4.84 |
| `val_followup_classic` | follow-up build, F-D | 1.371 | 346.05, -69.75 | 91.6 -> 80.3 | **+5.98 FAIL** |
| `val_fix2_classic_1`, `val_fix2_classic_2` (identical) | follow-up build, Fix2 | 0.009 | 356.16, -69.80 | 91.6 -> 65.9 | **+5.35 FAIL** |

At 91.6 m/s and 30 fps the hull moves 3.05 m per frame, so how deep it is in the obstacle on the contact frame changes
by metres with small changes of the path. The windless path is about where the v1-build runs were sideways (356.16
against 355.92 m) but 1.0 m further along the path; it loses 25.7 m/s in the hit instead of 16.9 and comes off at
+5.35 m/s instead of +4.83. The 5.0 m/s limit lies inside the +4.83..+5.98 m/s spread of this one contact. The flight
code is v1 (the fast phases match the polish build; `Scheme 0` + `check` gives 0 differences, session 2), the threshold
is untouched, and the windless start is the natural one, not one picked to pass: so as_43 under Classic is **24/25
every time**, and the f2 failure is a v1 limit, not a harness flake.

### Issues

| # | Class | Issue | Status |
|---|---|---|---|
| U1 | HARNESS (as_43, known since pass 1) | `f2_boost_path` +5.98 m/s (limit 5.0): it depends on where the hull meets `AS_Obstacle_1`, and the F-D deck stand moved the hull 3.7 m sideways there | Fix2: the run no longer depends on the build or the deck phases (wind off for the run, flight path from the spawn pose). f2 then fails the same way every time (+5.35 m/s, 2 of 2 runs identical): a v1 limit of the obstacle clip, reported as such; threshold untouched, Classic C++ unchanged |
| U2 | HARNESS (as_43, information) | `a3_deck_stand` passes with 0.13 m to spare; the rest is the 0.62 deg start pitch, which the earlier phases (and so the wind seed) set | Fix2: with the wind off for the whole run the hull is level at the a3 start (0.05 deg) and a3 drifts 0.009 m; threshold untouched |
| U3 | COVERAGE (information) | F-A and F-B were checked standalone only (session 2: the host pilots); no client-pilot run at 100 ms of `p3_push` / `p4_firehold`. Both run only on the pilot's machine (`GatherLocalInput` when locally controlled), the server code is unchanged, and a client pilot's `LastOwnBroadsideTime` comes from its predicted shot (`HandleCannonsFired`) | not run (optional) |
| - | cleanup | the editor's Python wrote `__pycache__` into `Docs/Airship/scripts/ue/` (untracked) and `Docs/Airship/controls/sims/` while session 2 ran | deleted |

No flight-code or C++ bug was found. This step changed nothing but this section, the intro line pointing to it, and the
media crops in `Saved/Airship/controls_followup/media/`. Fix2 changed `scripts/ue/as_43_pie_validate.py` and the docs
(`HOW_TO_FLY.md`, `CPP_NOTES.md` 14.1 / 14.12, `RESULTS.md`, `SCHEME_POINTFLY.md`, this file), no C++. The docs step
after it brought the rest in line: `RESULTS.md` (new section "Follow-up after review", "Known limits"),
`CPP_NOTES.md` (2, 14, 14.6, 14.12 rows F-A to F-E with file:line), `HOW_TO_FLY.md`, `SCHEME_POINTFLY.md`,
`TEST_PROTOCOL.md`, `README.md`, the header comments of as_43 / as_45, and the pointers in this file's pass-1 and
"Final" sections.

### Files

| What | Where |
|---|---|
| Follow-up checks: verdicts, every number, frames, X grabs, crops | `Saved/Airship/controls_followup/` (`followup_summary.txt`, `followup_checks.json` with `lock_per_frame`, `pointfly/telemetry.json` with `pk` = `IsPFParked()` per frame, `as50_log.txt`, `status.txt`, `xgrab/`, `media/`) |
| as_43 Classic | Follow-up: `val_followup_classic/` (`val_report.txt`, `val_result.json`, `val_log.txt`); Fix2: `val_fix2_classic_1/` (= `val_prev/`), `val_fix2_classic_2/` (= `val/`); the polish build's run: `val_final_classic/` |
| as_45 Classic | `Saved/Airship/mp_final_classic/` (`mp_report.txt`, `mp_result.json`, `mp_log.txt`; this now holds the follow-up run); the polish build's run: `mp_final_classic_polish/` |
| Runners and logs (`_AirshipWork_logs/`) | `run_controls_pie2.sh` + `run_controls_followup43_031254.log`, `run_followup_checks.sh` + `run_followup_checks_031755.log`, `run_as45_pf.sh` (`ONLY_CLASSIC=1`) + `run_as45_followup_032406.log`, `build_025149.log`; Fix2: `run_controls_fix2_43_034027.log`, `run_controls_fix2_43b_034416.log` |
| Scripts (`_AirshipWork_logs/scratch/controls/followup/`, python3 -B) | `as_50f_followup.py` (the PIE checks), `mock_followup.py` (its offline test on the mock editor), `test_as43_a3.py` (F-D's a3-only helpers, replaced in Fix2), bench probes; Fix2: `test_as43_fix2.py` (offline test of the Fix2 helpers), `f2_table.py` and `phase_starts.py` (the f2 tables above, run from `Saved/Airship`) |
