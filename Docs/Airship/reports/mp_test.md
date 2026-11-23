# Airship multiplayer PIE test (2026-11-22, 16:17-16:59 UTC)

Play As Listen Server with 2 players (the host + 1 client, one editor process) on
`/Game/Assets/MyShip/Drivable/Maps/L_AirshipTest`, clone `_AirshipWork`, branch `claude/project-thread-0emzt1`. Nothing
was committed.

**Result:** all five tests (a-e) pass after the fixes below. In the final full run (run 3), 21 of 22 checks passed as
written. The 22nd, `c_cannons`, failed because of how the harness measured the impact: the port balls did hit the wall
on both machines. Re-scored on the corrected measure, it passes, and the 6-volley re-runs (runs 2 and 4) pass as written.

## Setup

- **Play mode:** `PlayNetMode=PIE_ListenServer`, `PlayNumberOfClients=2`, `RunUnderOneProcess=True`.
  - Set in `Saved/Config/LinuxEditor/EditorPerProjectUserSettings.ini` with the editor closed, using the new
    `Docs/Airship/scripts/harness/set_play_mode.sh listen 2`.
  - Restored at the end with `set_play_mode.sh standalone` (PIE_Standalone, 1 player). A backup of the ini from before
    each switch is in `_AirshipWork_logs/scratch/mp/`.
- **Map:** unchanged. No second PlayerStart was needed: the client spawns on the start platform at (0, 0, 73) and the
  host at the PlayerStart (-2500, -2500).
- **Game time:** fixed at 30 fps. The real frame rate was 30.1-30.2 with the editor visible, so `Net PktLag=100`
  (a real-time delay) equals 100 ms of game time each way.
- **Harness:** `Docs/Airship/scripts/ue/as_45_pie_mp.py` drives both PIE worlds from the editor's Python.
  - Everything the client does goes through the client's own machine. F, fire, exit, throttle and steer are injected
    into the client's Enhanced Input subsystem. The flight schedules call `DebugSetInput` on the client's copy of its
    ship.
  - Server-only console commands (`Aura.Airship.Kill`, `Aura.Airship.Spawn`) run in the server world.
  - The host fires `GA_GunShoot` the way the sentinel harness did: it aims its control rotation from the camera and
    injects `IA_LMB`.
  - `p.NetShowCorrections 1` logs character corrections. Scene captures and X window grabs are taken from both machines.

## Runs

| Run | Script | What | Files |
|---|---|---|---|
| 1 | as_45 | full test, before the replication fix | `mp/run1/` (report, json, contact sheets, X grabs), `captures/mp_run1/` |
| 2 | as_46 | 3 cannon volleys with a fixed ball tracker; replication compared in 4 variants x {no lag, PktLag 100}; every-frame updates emulated from Python | `mp/run2/`, `captures/mp_run2/` |
| 3 | as_45 | full test after the C++ fixes (**final**) | `mp/run3/` (report, json, `sheet_run3_captures.png`, `sheet_run3_xgrab.png`, X grabs), `captures/mp_run3/` |
| 4 | as_47 | run 2 again with the C++ property `bReplicateEveryFrame`, plus the RepMode guard | `mp/run4/`, `captures/mp_run4/` |

All runs: 0 `Error:` lines (apart from the pre-existing ones below), 0 ensures, 0 `Accessed None`, 0 `rebuilt the
physics body`, 0 `LogAirship` warnings (except run 4's single deliberate RepMode-guard warning). Character corrections:
runs 1 and 3 have exactly 4 on each side (the 2 harness teleports, the exit and the eject; see Remaining issues),
runs 2 and 4 have 1 (the teleport).

## (a) The client boards and flies

### Boarding
- **F out of range (32 m from the seat):** refused; the client stays on foot.
- **F on the deck** (`IA_AirshipBoard` -> `UAirshipPilotComponent::ServerRequestBoard`, the client's own path):
  - The server boarded the ship 0.07 s after F. The pilot is the client's character, the controller is the client's
    PC, and the character is attached to the hull.
  - On the client, the ship is possessed as an autonomous proxy 0.07 s after F, and the attached character's collision
    is off.
  - The client's HUD switches to the ship HUD with the on-foot overlay collapsed. The host stays on foot with its
    overlay and no ship HUD (X grabs `x_board_client.png` / `x_board_main.png`).
- **Hover, client piloting:** server-vs-client position error 0.9 cm mean (1.8 max), rotation 0.1 deg.

### Flying
- **Real key path:** `IA_AirshipThrottle` and `IA_AirshipSteer` injected on the client. The shaped throttle reaches 1.00
  on both machines and steer 1.00 on both, and the server ship goes from 0 to 32.6 m/s in 2 s. The server applies the
  client's keys.
- **`DebugSetInput` on the client's ship:** goes through the same RPC since the C++ change below. The server applied
  every edge (throttle, steer right, steer left, brake); top speed 52-55 m/s.

**Response times in run 3** (s after the client input, frame = 0.033 s):

| | Client controls | Client cosmetics (wheel, fans, nozzles) | Server controls | Host sees cosmetics | Server physics | Client's own ship |
|---|---|---|---|---|---|---|
| No lag | 0.033 | 0.066 | 0.066 | 0.10 | 0.066-0.133 | 0.066-0.166 |
| PktLag 100 each way | 0.033 | 0.066 | 0.166-0.2 | 0.2-0.233 | 0.166-0.2 | 0.30 |

The cosmetics are predicted on the client: wheel, fans and nozzles move 2 frames after the input whatever the lag. The
physics answers after one RTT. (Two "client's own ship" values of 0.033 s under lag are threshold artefacts and are not
counted.)

### Correction jitter
Server-vs-client ship transform, compared every frame. "Accel" is the second difference of the client's ship position
in cm/frame² (the server's own is 1.4-2.0). "View" is the ship relative to the client pilot's camera.

| Config | Position error mean / max | Lag fit | Residual mean / p95 | Client accel median / mean / p95 | View accel median / p95 | Frames > 10 cm/frame² |
|---|---|---|---|---|---|---|
| Before the fix, no lag (run 1, run 4 v0a) | 84-99 / 162-164 cm | client 1 frame ahead | 42-43 / 74 cm | 6.6-13.0 / 10.6-11.2 / 22-23 | 12.0 / 23.1 | 163-226 |
| After the fix, no lag (run 3, run 4 v1a) | 123-142 / 182-191 cm | client 1 frame ahead | 15.4-15.9 / 31.5 cm | **1.6 / 2.1-2.4 / 4.0-4.3** | **2.6-2.9 / 6.8-7.9** | 4-6 |
| Before the fix, PktLag 100 (run 1, run 4 v0b) | 290-310 / 513-536 cm | client 3 frames behind | 56-60 / 107-122 cm | 11.8-13.4 / 12.3-12.5 / 24 | 13.0 / 25.5 | 189-221 |
| After the fix, PktLag 100 (run 3, run 4 v1b) | 247-259 / 433-471 cm | client 2 frames behind | 34-36 / 63-65 cm | **3.4-3.5** / 7.9-12.7 / 22.4-22.7 | 4.4-4.9 / 22.7 | 111-139 |

- **Before the fix**, the client's ship moved in alternating steps of about 145 and 165 cm per frame at 50 m/s (the
  server's: 157-160, smooth). That is a ±10 cm judder at 15 Hz on the pilot's screen.
- **Cause:** the engine schedules the ship's next update at `1/NetUpdateFrequency + rand x server tick`, which at a
  30 Hz server skips about every other frame (`UNetDriver::ServerReplicateActors`). Default physics replication then
  chases a target that moves in uneven steps.
- **The fix** replicates every server frame and brings the client back to the server's own smoothness when there is no
  lag. The server's own motion (what the host sees) was smooth throughout.
- **With 100 ms lag each way:**
  - The median improves (3.4 from 11-13), but bursts remain: lagged packets bunch up, p95 is about 22.
  - Without the fix: no hard snaps in 3 lagged flights.
  - With the fix: one engine hard snap of 6.3 m at 54 m/s in run 3's lagged flight (error about 3.9 m before it), and
    none in the other 2 lagged flights (runs 2 and 4).
  - With `p.LogPhysicsReplicationHardSnaps 1` (run 4), the in-flight "accumulated error" snaps were 11-67 cm, with and
    without the fix (each gap's reset teleport, 4.8-357 m, also snapped, as expected).
- **Watching the host's ship** (test e): the client's accel went from 4.96 to 1.35 (server 1.04), and frames over
  10 cm/frame² from 98 to 6.
- **`Aura.Airship.RepMode 1` (PredictiveInterpolation):** run 2 showed the client copy was never corrected. It coasted
  290-690 m away, with no response to the server, both without and with every-frame updates. The project has Physics
  Prediction off. The new guard keeps the ship on Default (run 4 v2a reads DEFAULT on both machines, numbers identical
  to v1a) and logs one warning.

## (b) The host on foot

- **Smoothness:** the host sees the server's own simulation. Accel median 1.4-1.6 and p95 3.4-3.9 cm/frame² in every
  flight, with no steps.
- **Lag:** the host's view of the client's wheel and fans trails the client's by 1 frame (0.10 vs 0.066 s), or 0.2 s
  with lag.
- **Captures:** the host's view during the flights is in `fly0_host_view_player_server.png` and
  `gun_host_view_player_server.png`.
- **GA_GunShoot on the client's ship:** `IA_LMB` was injected for 3 s while aiming at the hull.
  - The server logged `HitActor: BP_AirshipPawn_C_0` 13 times.
  - Ship health went 2000 -> 1987 on the server and on the client. The client saw each drop in the same frame as the
    server.
  - It is 1 HP per hit because `GA_GunShoot::MyFunc` uses SetByCaller 1 (pre-existing gun tuning, not the ship).

## (c) The client fires the cannons

- **Volleys:** client F on `IA_AirshipFire`, port then starboard, plus a second port volley in runs 2 and 4. Each
  volley spawns 2 balls on the server and replicates 2 copies to the client, and the balls hit the walls (impact y
  -9270.6 / +14270.6 on both machines) after 0.87-0.94 s.
- **Muzzle FX:** exactly 2 new NS_AirshipMuzzle per volley on each machine. The client's predicted shot is shown once:
  the multicast skips it, there is 1 recoil peak per cannon, and no double FX.
- **Recoil:** `CannonRecoilCm` peaks at 44.98 cm on both machines.
- **Hull kick:** 92.8-93.1 cm/s on the server, 85-86 cm/s predicted on the client.
- **Score:** runs 2 and 4 are 3/3 volleys PASS. Run 3 is re-scored PASS (below).
- **Harness artefact:** run 1 marked the first port volley as "exploded at spawn". Run 3's tracker saw those balls not
  advance for 1 frame right after spawn on both machines. In both runs the same balls then hit the wall at 0.9 s and
  were removed 1 s later, exactly like the starboard ones. The harness now takes the impact from the position where the
  ball goes hidden (Explode).

## (d) `Aura.Airship.Kill` on the server

- **Death:** dead on the server at once and on the client 1 frame later (0.033 s).
- **FX:** the thruster jets are off 0.3 s after each machine's death and the fan wash by 3 s.
- **Rig:** `bIsDead` and `DeathTime` are set on both anim instances.
- **Wreck:** the break-off parts flew 9-54 m from their place on both machines. The CR wreck solver runs on each
  machine, so the debris differs per machine; that is cosmetic.
- **Pilot:** ejected and re-possessed 0.4 s after the kill on the server and on the client.
  - Health is 85 on both machines: the value from before boarding, after the character was hurt by 25, so it was
    restored, not refilled.
  - The capsule has a body on both copies.
  - Both copies fell about 213 m and ended Walking on the ground at the same spot (< 1 m apart).
- **HUD:** the client's ship HUD is gone and its on-foot overlay is back (`x_after_death_client.png`).

## (e) The host boards a ship while the client stands on its deck

- **Setup:** `Aura.Airship.Spawn` made ship 2, and both copies match. The client (both copies) and the host were put
  on ship 2's deck: both are riders, QueryOnly and Walking. The host's F boarded ship 2 while the client rode.
- **HUD:** the host's ship HUD is on with its overlay collapsed. The client stays on foot (`x_host_flying_main.png` /
  `x_host_flying_client.png`).
- **Host flies 14 s** (neutral 4 s, throttle 0.5, turn, brake; top 50 m/s):
  - **No sink with the client on deck:** z span 0.4 cm, |vz| 0.00 m/s and |pitch| 0.26 deg in the neutral part.
  - **The client stayed aboard on both machines**, in ship-2 space x -8.55..-8.33, y -2.63..-2.50 and z 5.29..5.32 m;
    rider, QueryOnly and Walking 100 % of frames.
  - The two copies of the client agree to 0.17 cm mean (0.6 max).
  - No character corrections in this phase.

## Fixes made (C++, both builds clean: `_AirshipWork_logs/build_161635.log`, `build_164949.log`)

1. **`DebugSetInput` through the pilot's input path:**
   - Found by reading the code before the first run; that version was not run in PIE. On a client it only changed the
     client's cosmetics, because the pilot's machine kept sending its idle keys, so the server never flew it.
   - Now, on the pilot's machine, `AAirshipPawn::GatherLocalInput` uses the debug controls in place of the keys and
     they go out through `ServerSetPilotInput`.
   - `UAirshipFlightComponent::SelectControls` takes `LocalInput` first on the pilot's machine, and `DebugInput` only
     on the server's copy of a client-piloted or empty ship.
   - The host and standalone paths are unchanged; run 3's host-piloted flight in (e) used it.
2. **`AAirshipPawn::bReplicateEveryFrame`** (default true): `ForceNetUpdate` in Tick on the server while the hull is
   awake. This is the judder fix measured above.
3. **`Aura.Airship.RepMode 1` guard:** PredictiveInterpolation is applied only with Project Settings > Physics >
   Physics Prediction on; otherwise the ship stays on Default and warns once.

Docs: `Docs/Airship/CPP_NOTES.md` has a new section 13, and sections 5, 6 and 8 are updated.

## Remaining issues

- **Lag judder:** with 100 ms lag each way the client's ship still judders in bursts (p95 about 22 cm/frame²). The
  engine also hard-snaps it now and then: once by 6.3 m at 54 m/s, otherwise 0.1-0.7 m. Options, not done:
  - a `UNetworkPhysicsSettingsComponent` on BP_AirshipPawn with a larger hard-snap distance and error-accumulation time;
  - visual smoothing of the mesh on clients;
  - Physics Prediction for the project, which is a project-wide decision.
- **Pilot latency:** the client pilot's own ship answers after one RTT (0.3-0.37 s at 200 ms RTT). Only the cosmetics
  are predicted (design option A).
- **Exit and eject snap:** the client's own character starts its first move from the helm. The server corrects it
  3.1-3.3 m to the exit point, one `LogNetPlayerMovement` correction per exit or eject, visible as a one-RTT snap. A
  `ClientSetLocation` after the possession would avoid it, but it also sets the control rotation, so it was not done.
- **Pre-existing, not airship:**
  - 14 `GiveAbility called on ability ... on the client, not allowed!` errors when the client's character gets its
    PlayerState: `AMyCharPlayer::OnRep_PlayerState` calls `GiveStartupAbilities` on the client.
  - The gun's damage is 1 per hit.
- **Harness notes:**
  - `character.get_movement_base()` returns None in this build's Python even while based on the hull; based movement
    itself works.
  - Each 2533x1358 X grab takes about 8 s.
  - The PIE client window is "Aura Preview [NetMode: Client 1] ...".

## Files

- **Reports:** `mp/run1..4/` (`mp_report.txt` / `mp2_report.txt` / `mp3_report.txt` + json), `mp/mp_log.txt`,
  `mp/probe.json`.
- **Captures:** `captures/mp_run1..4/`. Client captures have an alpha channel; flatten with `-alpha off`.
- **Contact sheets:** `mp/run1/sheet_run1_*.png`, `mp/run3/sheet_run3_captures.png`, `mp/run3/sheet_run3_xgrab.png`.
- **Scripts:**
  - `Docs/Airship/scripts/ue/as_45a_mp_probe.py`, `as_45_pie_mp.py`, `as_45s_mp_status.py`, `as_45x_mp_stop.py`,
    `as_46_pie_mp_rep.py`, `as_47_pie_mp_rep_fix.py`.
  - `Docs/Airship/scripts/harness/set_play_mode.sh`, `xgrab_mp.sh`.
