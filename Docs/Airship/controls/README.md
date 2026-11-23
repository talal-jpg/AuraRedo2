# Airship controls: folder index

The control-scheme work of 2026-11-22/23: three new ways to fly the airship (Galleon, Sky Racer, Point & Fly) built
next to Classic (v1), tested, judged and polished. **Point & Fly won and is the default.** Start with `RESULTS.md`;
how to fly is in `../HOW_TO_FLY.md`.

## Documents

| File | What it is |
|---|---|
| `README.md` | This index |
| `RESULTS.md` | The summary: what was built, how it was tested and judged, why Point & Fly won, the polish, the final play test, multiplayer, the follow-up after review, known limits, how to try every scheme |
| `PIE_RESULTS.md` | Every PIE number of pass 1 next to the bench, the acceptance and scheme checks, the images, the issues; the verify step's "Final" section; the "Follow-up (after the final review)" section (F-A to F-E, and "Fix2" for as_43) |
| `SCHEME_POINTFLY.md` | The Point & Fly design (the default): concept, controls, behaviour, parameters, camera, feedback, HUD, multiplayer, predicted metrics, risks, review changes, "Polish after judging" |
| `SCHEME_SKYRACER.md` | The Sky Racer design, same sections |
| `SCHEME_GALLEON.md` | The Galleon design, same sections |
| `BASELINE.md` | Classic (v1) as a code reference: one frame of control, tunables, measured feel, the root causes and the base fixes (4f), extension points, multiplayer constraints |
| `IMPLEMENTATION_PLAN.md` | The C++ plan the code follows: shared framework, per-scheme change lists, new properties, harness, acceptance (7), open risks (8) |
| `TEST_PROTOCOL.md` | The PIE harness as_50: running it, what one pass does, start poses, inputs, bots, runs and metrics, outputs, robustness |

## media/

8-bit PNG copies of the PIE sheets at full size (the 16-bit originals are in `Saved/Airship/`, not in the repo).

| File | What it is |
|---|---|
| `media/pass1_contact_classic.png` | Pass 1, Classic: the precise bot's course run from the pilot camera, every 2 s |
| `media/pass1_contact_galleon.png` | Pass 1, Galleon: the same |
| `media/pass1_contact_skyracer.png` | Pass 1, Sky Racer: the same |
| `media/pass1_contact_pointfly.png` | Pass 1, Point & Fly: the same |
| `media/pass1_stills_classic.png` | Pass 1, Classic: start, slalom, drift / boost, hairpin apex, climb, finish, broadside; pilot and wide views |
| `media/pass1_stills_galleon.png` | Pass 1, Galleon: the same |
| `media/pass1_stills_skyracer.png` | Pass 1, Sky Racer: the same |
| `media/pass1_stills_pointfly.png` | Pass 1, Point & Fly: the same |
| `media/final_contact_pointfly.png` | The final play test, polished Point & Fly: the course run |
| `media/final_stills_pointfly.png` | The final play test, polished Point & Fly: the stills |

## sims/ (the offline bench; run `python3 -B` from inside `sims/`, one process at a time)

| File | What it is |
|---|---|
| `sims/README.md` | The bench: files, running it, one frame, adding a scheme, the metric definitions M1-M12, what it does not model |
| `sims/airship_sim.py` | The bench itself: the flight model port, the Chaos body, the pilot's network path, the camera, the scheme plug-in API |
| `sims/metrics.py` | Maneuvers and metrics M1-M12; writes `<scheme>_metrics.json` |
| `sims/course.py` | The gate course (M11), the racing-line planner and the precise / sloppy bots |
| `sims/compare.py` | Prints several `<scheme>_metrics.json` side by side |
| `sims/calibrate.py` | Replays the v1 PIE runs and tables the bench against them; writes `calibration.json` |
| `sims/calibration.json` | The bench against v1 PIE |
| `sims/mass_props.py` | Mass, centre of mass and inertia of the hull from its 8 collision hulls; writes `hull_mass.json` |
| `sims/hull_mass.json` | The hull's mass properties |
| `sims/pie_ref.py` | Extracts the v1 PIE reference data from `Saved/Airship` into `pie_ref.json` |
| `sims/pie_ref.json` | The v1 PIE reference data (committed because `Saved/` is not) |
| `sims/scheme_template.py` | A scheme module to copy; unchanged it equals Classic (a self-test of the plug-in path) |
| `sims/classic_metrics.json` | Classic (v1): M1-M12 from the bench |
| `sims/BASELINE_METRICS.md` | Classic (v1): the bench results and the calibration against PIE |
| `sims/baseline_sim.py` | `BASELINE.md`'s own port of v1 (6-DOF), used for the base-fix numbers |
| `sims/baseline_checks.py` | The numbers behind `BASELINE.md` 4a-4e |
| `sims/scheme_galleon.py` | Galleon's bench model: preset, flight model changes, camera, bot adapters |
| `sims/galleon_metrics.json` | Galleon: M1-M12 from the bench |
| `sims/galleon_checks.py` | Galleon-only checks: telegraph, helm, stern swing, stations, sidle, brake, the course with beam glances |
| `sims/galleon_checks.json` | Their results |
| `sims/galleon_sweep.py` | A course sweep used to tune Galleon (design aid) |
| `sims/scheme_skyracer.py` | Sky Racer's bench model |
| `sims/skyracer_metrics.json` | Sky Racer: M1-M12 from the bench |
| `sims/skyracer_checks.py` | Sky Racer checks: drift tiers, mini-turbo, chain, tier agreement under lag, boost burst, S brake, gun deck, camera, the 5-seed course |
| `sims/scheme_pointfly.py` | Point & Fly's bench model (with the polish and the follow-up's parking latch, `PARK_LATCH`) |
| `sims/pointfly_metrics.json` | Point & Fly after the polish: M1-M12 from the bench |
| `sims/pointfly_metrics_pass1.json` | Point & Fly as judged (pass 1): M1-M12 from the bench |
| `sims/pointfly_checks.py` | Point & Fly checks: steps, sweeps, drift, the racing pass, the mouse and keys courses, camera pitch, latency, the charge, the polish checks (exit, kick, park, rival, m12cam) and the follow-up's push |
| `sims/pointfly_checks.json` | Their results after the polish and the follow-up |
| `sims/pointfly_checks_pass1.json` | Their results as judged (pass 1) |
| `sims/review_fps_check.py` | Review check: every scheme at 30 and 120 fps (loop stability) |
| `sims/review_preset_table.py` | Review tool: prints the preset table of `IMPLEMENTATION_PLAN.md` 1.13 from the bench presets |
| `sims/.gitignore` | Keeps `__pycache__` out of git |

## Elsewhere

| File | What it is |
|---|---|
| `../HOW_TO_FLY.md` | How to fly: keys, HUD and moves for every scheme, switching, console commands |
| `../CPP_NOTES.md` section 14 | What the control-scheme C++ does (14.12: the polish after judging and the follow-up F-A to F-E) |
| `../scripts/ue/as_50_pie_controls.py` | The PIE harness (editor inbox script) |
| `../scripts/ue/as_50_protocol.py` | The harness's maneuvers, bot wiring and metrics, pure Python (`--selftest` against the bench) |
| `../scripts/ue/as_50s_status.py`, `../scripts/ue/as_50x_stop.py` | Harness status and stop (inbox scripts) |
| `../scripts/ue/as_50t_mock_pie.py` | Runs the harness without Unreal (the bench in place of the C++) |
| `../scripts/harness/as_50_post.py` | After PIE: videos, contact sheets, the 2x2 video, compare.md |
| `../scripts/ue/as_43_pie_validate.py`, `../scripts/ue/as_45_pie_mp.py` | The v1 validation (standalone) and multiplayer (listen server + 1 client) PIE tests, run under Classic by default (`AS43_SCHEME` / `AS45_SCHEME`). Since the follow-up, as_43 runs with v1's wind sway off and its flight path from the spawn pose, and as_45 sets the scheme on both its ships (`PIE_RESULTS.md` "Follow-up") |
| `Saved/Airship/controls_pass1/` (not in the repo) | Pass 1 outputs: metrics, telemetry, course videos, `compare_course_2x2.mp4`, sheets, HUD grabs |
| `Saved/Airship/controls_followup/` (not in the repo) | The follow-up PIE checks: `followup_summary.txt`, `followup_checks.json`, X grabs, crops |
