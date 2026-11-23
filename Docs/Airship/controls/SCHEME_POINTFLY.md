# Point & Fly: camera-directed flying (`EAirshipControlScheme::PointFly` = 3)

The design, tuning and C++ change list of the "Point & Fly" control scheme, one of the three iterations judged against
Classic (v1). Everything below was tuned in the offline bench (`sims/`, a port of the C++ at 8f01bca calibrated against
PIE); it was written as a prediction, before anything was built or run in Unreal.

**Status (2026-11-23):** built, run in PIE (pass 1, the final play test and the follow-up after the final review,
`PIE_RESULTS.md`), judged the winner and now **the default scheme** (`RESULTS.md`). Sections 1-14 are the design as
specified before the build; what changed since is in "Review changes" and "Polish after judging" at the end (among
others `PFLockLeadTime` 0.6, `GyroYawMax` 1.0, `KrSteady` 5.5, `AlphaYawMaxSteady` 1.5, `DriftBoostCapSpeed` 4800,
and the new `PFParkSpeed` 300 and `PFLockArmTime` 6; the HUD of section 7 grew, P6 / P7). The code is in
`../CPP_NOTES.md` 14.

| | |
|---|---|
| Bench plug-in | `sims/scheme_pointfly.py` (scheme + base-fix flight model subclass) |
| Extra checks | `sims/pointfly_checks.py` -> `sims/pointfly_checks.json` |
| Metrics | `sims/pointfly_metrics.json` (`python3 metrics.py pointfly`, 6 s) |
| Reproduce | `cd Docs/Airship/controls/sims; python3 scheme_pointfly.py --selftest; python3 metrics.py pointfly; python3 course.py pointfly; python3 pointfly_checks.py` (about 30 s in all) |

## 1. Concept: why it is fun

You look where you want to go and the ship goes there. The mouse or right stick moves the camera, and the camera's yaw is the ship's heading target. W/S drive, and A/D sidestep, so WASD moves the 52 m airship like a third-person character. The ship never snaps: it rolls into an 18 deg bank, the helm wheel spins, the fan housings swing 12 deg and the nose swings at up to 35 deg/s. Then it eases onto your heading without overshooting, so you feel 40 t of ship obey you. Because the server holds the heading you chose, a client pilot on a 200 ms round trip flies with the same zero overshoot as the host, only about 0.13 s later.

Fighting comes for free. Hold Aim (RMB) and the camera is yours, and the ship holds its course while you swing a broadside onto a target you are racing past. If the target slides out of the guns' arc, a gun lock swings the ship to keep the broadside on it: W then circles the enemy and A/D close or open the range. The skill on top is the line you choose, plus a few moves:
- the brake-turn (the tightest reversal);
- the brake-drift (the fastest nose swing, with a +6 m/s kick on the way out);
- the drift broadside: slide sideways at a target and unload, 1.7 s sooner than turning.

Nobody has to learn them to have fun.

## 2. Controls

No new input actions or mappings. Point & Fly reads the existing actions differently in C++.

| Action (IMC key / pad) | Point & Fly | Classic |
|---|---|---|
| IA_AirshipLook (mouse / right stick) | **Steering mode** (Aim up): moves the camera. The camera yaw is the heading target, and the ship turns to it. Camera pitch only aims, and never climbs (section 10). **Broadside mode** (Aim held): free camera, and the ship keeps its heading | Free camera, recentres after 1.5 s |
| IA_AirshipThrottle (W/S, LS Y) | W drives forward. S brakes firmly at 1 g while moving forward, then backs up (0.5 g, 18 m/s) | W forward, S gentle reverse |
| IA_AirshipSteer (A/D, LS X) | **Sidestep** (sent on the Strafe axis): 14 m/s, leaning 7 deg into it | Turn |
| IA_AirshipStrafe (Q/E, D-pad L/R) | **Turn with keys**: the heading target turns at the ship's own full turn rate, and the camera follows. In broadside mode the ship turns while the camera stays on its point | Sidestep |
| IA_AirshipLift (Space / Ctrl / C, RT / LT) | Climb 12 / sink 15 m/s; on release the ship is down to 0.6 m/s after 1 s and holds where it stops | Same rates, floaty stop |
| IA_AirshipBoost (Left Shift, A) | Boost (as Classic) | Boost |
| IA_AirshipBrake (X, B) | Brake: a near constant-deceleration stop from 48 m/s in 2.5 s (2.4 g peak). Held while the camera is 40 deg or more off the nose at speed: **brake-drift**. The slide ends by itself 15 deg before the heading; let go for the +6 m/s kick | Brake; brake + steer = drift |
| IA_AirshipAim (RMB, LB) | **Broadside mode**: free camera, FOV -15, the hull flattens (bank x 0.4), gun lock. The lock only acts on an aim 55-150 deg off the bow, so looking ahead with RMB held never swings the ship (review R1). Release: the camera eases back onto the heading in about 0.5 s | FOV -15 |
| IA_AirshipFire (LMB, RB) | Fire the side the camera faces (as Classic) | Same |
| IA_AirshipZoom (wheel, D-pad U/D) | Zoom (as Classic) | Same |
| IA_AirshipExit (F, Y) | Exit (as Classic) | Same |

Keyboard only (no mouse) works: Q/E turn and A/D sidestep (section 9, "keys").

## 3. Behaviour spec

Units: deg, deg/s, s, m, m/s; cm and cm/s² where a C++ property is in those units. "Pilot" = the machine of the player at the helm (host or client); "server" = the listen server; "all" = every machine.

### 3.1 One frame

| # | Step | Machine | Where (section 12) |
|---|---|---|---|
| 1 | Camera -> heading target H: mouse delta, free look, Q/E, gun lock, lead clamp; writes the control rotation | pilot | `AAirshipPawn::UpdatePointFlyCamera`, start of `GatherLocalInput` |
| 2 | Wire controls: A/D on Strafe; H_send = H + lock lead into `HeadingTarget`; local heading loop on the pilot's own view of the hull into `Steer` | pilot | `GatherLocalInput` |
| 3 | Send / receive as today; `HeadingTarget` rides the 30 Hz heartbeat | both | unchanged |
| 4 | Heading loop on the authoritative hull writes `Controls.Steer` before `RepInput = Controls` | server | `UAirshipFlightComponent::UpdateFlight` |
| 5 | ShapeControls, cosmetics: unchanged code. Every machine's wheel, fans, rudder, nozzles and bank come from the Steer it has: the pilot from its local loop, the observers from the server's | all | unchanged |
| 6 | Forces: the brake cap, S as a brake, the broadside bank scale, turn-lift compensation | server | `ApplyForces` |
| 7 | Feedback: FOV kicks, shake, camera roll, rumble; HUD overlay | pilot | `UpdateCamera`, `UAirshipHUDWidget` overlay mode |

### 3.2 Pilot: camera -> heading target (`UpdatePointFlyCamera`, every frame, before the controls are read)

State, all on the pilot's pawn:
- `H`: heading target, world yaw;
- `Off`: camera offset from H;
- `LastSetYaw`: the control yaw this code wrote last frame;
- `bFree`, `bLock`, `Dwell`, `PrevOffBeam`, `HRate`, `PrevH`;
- `PilotLoop` (`FPointFlyLoopState`).

```
if not valid or bPendingCameraReset:                 # board, possession, scheme switch, respawn
    H = actor yaw
    Off = bPendingCameraReset ? 0 : wrap180(ControlYaw - actor yaw)    # a switch eases the camera in
    LastSetYaw = H + Off ; bLock = false ; Dwell = 0 ; valid = true
d = wrap180(ControlYaw - LastSetYaw)        # this frame's look input (the PC already applied the mouse delta)
external = d != 0 and LastLookInputFrame != GFrameCounter   # no IA_AirshipLook this frame: set from outside
q = axis(IA_AirshipStrafe)                  # Q -1 / E +1 (D-pad)
nudge = q * PFNudgeRateScale * Rmax(view forward speed, shaped boost, no drift) * dt   # open loop, see 10
bFree = Aim held
if bFree:                                   # broadside mode
    Off += d                                # the camera looks around; H holds
    H += nudge ; Off -= nudge               # Q/E turn the ship, the camera stays on its point
    if nudge != 0: bLock = false, Dwell = 0 # a manual turn overrides the gun lock
    else if bPFArcAssist: H, Off = GunLock(H, H + Off, dt)     # 3.3; Off absorbs the change
else:                                       # steering mode
    if external: H = ControlYaw ; Off = 0   # harness / reset: the camera and the target go there
    else:        H += d                     # the mouse moves the target with the camera
    H += nudge
    Off *= exp(-dt / PFLookReturnTau) ; if |Off| < 0.05: Off = 0    # ease back after broadside mode
    bLock = false ; Dwell = 0 ; forget PrevOffBeam
    lead = wrap180(H - view yaw)            # never more than PFHeadingMaxLeadDeg off the nose:
    if |lead| > PFHeadingMaxLeadDeg: H = view yaw + sign(lead) * PFHeadingMaxLeadDeg   # no +-180 flip
H = wrap180(H) ; Off = wrap180(Off)
ControlRotation = (ControlPitch clamped to CameraPitchMin..Max, H + Off, 0) ; LastSetYaw = H + Off
```

`view yaw` is the hull yaw on this machine: the host's own hull, a client's replicated copy. Only the loose
150 deg clamp reads it, and that never binds in normal flying.

### 3.3 Pilot: gun lock (broadside mode only)

The lock measures against the heading target H, not the lagging hull. A client therefore never closes a loop over the network.

```
b = wrap180(CamYaw - H) ; ab = |b| ; ob = |ab - 90|          # aim bearing; distance from the beam
obRate = Approach(obRate, (ob - PrevOffBeam) / dt, dt, PFArcApproachTau (0.1 s)) ; PrevOffBeam = ob   # review R2: filtered
if ab < PFArcMinBearingDeg (55) or ab > PFArcMaxBearingDeg (150):   # looking ahead or astern: plain free look (R1: was 35)
    bLock = false ; Dwell = 0 ; return H
if not bLock:
    outside  = ob > CannonYawLimitDeg - PFArcMarginDeg         # 20 - 6 = 14 deg off the beam
    comingIn = obRate < -PFArcApproachRateDeg                  # a target the ship is sailing past: wait for it
    Dwell = (outside and not comingIn) ? Dwell + dt : 0
    if Dwell >= PFArcLockDelay: bLock = true                   # (overlay "LOCK", rumble tick)
if not bLock: return H
offBeam = ab - 90                                              # + = aft of the beam
if |offBeam| <= PFArcLockDeadbandDeg: return H
excess = offBeam - sign(offBeam) * PFArcLockDeadbandDeg
return H + clamp(sign(b) * excess, -PFArcRateDeg * dt, +PFArcRateDeg * dt)
```

The result:
- Firing at a target you race past leaves your line alone. In the test it swung 0.4 deg off the heading and 0.8 m off the track, and fired 2 broadsides.
- Holding Aim on a target that drifts out of the arc turns the ship to follow it. The beam stays within 3 deg of the aim, so W circles the target.

### 3.4 Pilot: wire controls (`GatherLocalInput`, Point & Fly branch; `DebugSetInput` bypasses it as today)

```
Throttle = quantize(axis(IA_AirshipThrottle)) ; Strafe = quantize(axis(IA_AirshipSteer))    # A/D sidestep
Lift = quantize(axis(IA_AirshipLift))       # (+ camera-pitch climb only if bPFPitchClimb, off: section 10)
Boost / Brake / Aim bits as Classic ; AimPoint as Classic
# lock lead: while the gun lock drags H along, send it ahead by its own rate so the beam does not trail the aim
HRate = approach(HRate, clamp(wrap180(H - PrevH) / dt, +-PFHeadingLeadRateMax), dt, PFHeadingLeadTau) ; PrevH = H
H_send = wrap180(H + (bLock and bFree ? PFLockLeadTime : 0) * HRate)
HeadingTarget = EncodeHeading(H_send)       # 1..65534, 0 = no target (3.5)
Steer = quantize(ComputeHeadingSteer(H_send, view yaw, view yaw rate, view forward speed,
                                     Flight->GetShapedBoost(), Brake held, PilotLoop))   # own wheel / fans / bank
```

The Steer on the wire is the pilot's own estimate, for its own cosmetics. The server overwrites it whenever a heading target arrives. Without a target it is used as sent, which is the fallback for neutral input or a Classic-to-Point & Fly switch window.

### 3.5 The heading loop (`UAirshipFlightComponent::ComputeHeadingSteer`; server = authoritative, pilot = cosmetic)

One function on both machines. It turns a heading target into a Classic-shaped Steer value, so every existing consumer works unchanged: the yaw-rate loop, bank, fan yaw, rudder, gimbals, wheel, FX and the drift detection.

```
e = wrap180(Target - Yaw)                                  # deg
# drift: brake + a big turn at speed (hysteresis)
if not bBrake or ForwardSpeed <= DriftMinSpeed:      St.bDrift = false
elif not St.bDrift and |e| >= PFDriftStartDeg:       St.bDrift = true
elif St.bDrift and |e| < PFDriftEndDeg:              St.bDrift = false
Rmax = max(1, GetYawRateMaxDeg(ForwardSpeed, Boost, St.bDrift))   # the ApplyForces table (drift 50, boost 25)
ep  = e - YawRate * PFHeadingLead                          # the error the loop will see after its own lag
dec = PFHeadingDecelDeg * (St.bDrift ? PFDriftDecelScale : 1)
mag = min(Rmax, PFHeadingKp * |ep|, sqrt(2 * dec * |ep|))  # turn at full rate, brake onto the target
if |e| < PFHeadingDeadbandDeg and |YawRate| < 2: mag = 0   # wheel and fans rest
s = sign(ep) * mag / Rmax
if St.bDrift:                                  s = sign(s or e) * max(|s|, DriftSteerThreshold + 0.05)  # keep sliding
elif bBrake and ForwardSpeed > DriftMinSpeed:  s = clamp(s, +-(DriftSteerThreshold - 0.02))         # brake, no slide
return clamp(s, -1, 1)
```

Server, in `UpdateFlight` after the boost gate (`FC.cpp:445`) and before `RepInput = Controls` (`:448`), when the ship's `ControlScheme == PointFly`, flight is enabled and the controls carry a target:
- run `Controls.Steer = QuantizeAxis(ComputeHeadingSteer(Controls.GetHeadingTargetDeg(), BodyYaw, BodyYawRateDeg, ForwardSpeed, ShBoost, Controls.IsBrake(), ServerHeadingLoop))`;
- otherwise reset `ServerHeadingLoop`.

The loop is closed only on the server. The pilot's copy drives nothing physical.

### 3.6 Server: force changes (`ApplyForces`; all inert at their defaults, so other schemes are untouched)

```
# after the forward command (FC.cpp:579-590), before ACmd (:594)
if PFReverseBrakeAccel > 0 and ShThrottle < 0 and not bShBrake and Vf > 200 cm/s:        # S = firm slow-down
    AFanCmd = min(AFanCmd, PFReverseBrakeAccel * ShThrottle * clamp(Vf / 600 cm/s, 0, 1))
ABrake = (BrakeMaxAccel > 0) ? clamp(ABrake, +-BrakeMaxAccel) : ABrake                    # constant-decel brake (shared cap; bench PFBrakeAccelMax)
# vertical (:639): the turn's downward grip made up by the collective (last frame's value)
FvWorld = clamp(Mass * (Gravity + Kvz * (VzCmd - Vz) - PFTurnLiftComp * LastGripAccelZ), CollectiveMin W, CollectiveMax W)
# bank (:644)
BankDeg *= bShGunDeck ? GunDeckBankScale : 1                                              # steady gun deck (shared; bench PFAimBankScale; gun deck = Aim held)
# lateral (after :828)
LastGripAccelZ = AGrip * Right.Z                 # reset with bHoldValid when flight is disabled (:489-491)
```

`PFTurnLiftComp` removes the 5 m sink of a full-speed turn (M4: 5.15 -> 0.06 m). The cause: the grip of the 18 deg banked hull points about 0.77 g down, and the P-only height hold settled 4.7 m low (sims README Finding 3).

### 3.7 Base fixes (BASELINE.md 4f): all included

Point & Fly needs each one: the steady pitch, the crisp vertical stop and the station keeping make the "point and it obeys" promise true.

| # | Fix | Point & Fly value |
|---|---|---|
| 4a-1 | `bHullAxisInertia` | true (bench `ctrl_inertia='hull'`) |
| 4a-2 | `bFanTorqueFeedForward` | true |
| 4a-3 | PitchPerG / PitchMinDeg / BoostPitchDeg | 4 / -4 / 1.5 (PitchMaxDeg stays 6) |
| 4b | VertBrakeAccel / HoldBrakeAccel / LiftTauRelease | 784 cm/s² / 1470 cm/s² / 0.08 s |
| 4c | bBrakeHoldLead / BrakeFadeSpeed | true / 1000 cm/s |
| 4d | StationKeepGain / StationKeepSpeed / StationKeepAccelMax | 1.0 / 300 / 150 |
| 4e | ImpactEpisodeAccelUp / ImpactMaxReboundSpeed | **2000** cm/s² / 120 cm/s |

The fixes are ported into the bench as `PFFlightModel` with the exact `baseline_sim.py` definitions; with every switch off it equals the bench (`--selftest`). They reproduce BASELINE.md 4a: throttle dip -16.6 / -9.3 / -7.9 / -4.0 deg.

ImpactEpisodeAccelUp is 2000, not 1300, because of BASELINE 4e's rule: it must stay at or above the largest upward flight acceleration. That is (1.9 - 1) g + 0.35 g + VertBrakeAccel = 882 + 343 + 784 ≈ 2009 cm/s².

### 3.8 Reset rules (contract: scheme-local state resets on a switch and on board / exit)

| Event | Pilot | Server |
|---|---|---|
| Board / possession (`UpdateLocalMappingContext` sets `bPendingCameraReset`) | H = actor yaw, Off = 0, lock off, `PilotLoop` cleared | `ServerHeadingLoop` cleared (`ResetInput`) |
| Scheme switch to Point & Fly (`ApplyControlScheme` / `OnRep_ControlScheme`) | H = actor yaw, Off = control yaw - actor yaw (the camera eases behind in about 0.5 s; the ship does not turn) | cleared |
| Switch away | state dropped; Classic recentre resumes (its preset) | cleared |
| Exit, death | cleared | cleared |
| Pilot changes (`OnRep_PilotCharacter`, every machine; review R5) | cleared | `ServerHeadingLoop` cleared (observers' copies too) |
| Debug input active on the pilot's machine (`DebugSetInput`) | `bPFValid = false` while it lasts, so the heading target restarts on the hull's heading afterwards (review R5) | the debug controls carry no target |
| Input timeout or neutral input | (n/a) | no target -> the Steer axis (0): the ship stops turning and holds altitude |

## 4. Parameters

**New flight-component tunables** (`UAirshipFlightComponent`, category `Airship|PointFly`). The loop constants only act when a heading target arrives. The force switches default to inert values, so Classic stays exact v1.

| Name | Unit | C++ default (= Classic) | Point & Fly | Meaning |
|---|---|---|---|---|
| PFHeadingKp | 1/s | 6.5 | 6.5 | Turn rate per degree of predicted error |
| PFHeadingLead | s | 0.18 | 0.18 | The loop acts on the error this far ahead |
| PFHeadingDecelDeg | deg/s² | 55 | 55 | Planned yaw deceleration onto the target (sqrt profile); the yaw loop's cap is 57 |
| PFHeadingDeadbandDeg | deg | 0.25 | 0.25 | No steer inside this, with the yaw rate under 2 deg/s |
| PFDriftStartDeg / PFDriftEndDeg | deg | 40 / 15 | 40 / 15 | Brake with this much turn left starts a drift; it ends with this much left |
| PFDriftDecelScale | - | 0.8 | 0.8 | The sliding hull stops its yaw more gently (no exit overshoot) |
| PFBrakeAccelMax | cm/s² | 0 (off) | 1470 | Air-brake cap: a constant-deceleration stop. C++: the shared `BrakeMaxAccel` (review R3) |
| PFReverseBrakeAccel | cm/s² | 0 (off) | 980 | S while moving forward slows at 1 g |
| PFAimBankScale | - | 1 (off) | 0.4 | Bank while Aim is held. C++: the shared `GunDeckBankScale` (review R3) |
| PFTurnLiftComp | 0..1 | 0 (off) | 1 | Collective makes up the turn's downward grip |

**New pawn tunables** (`AAirshipPawn`, category `Airship|PointFly`; pilot-side, only read in Point & Fly):

| Name | Unit | Default = Point & Fly | Meaning |
|---|---|---|---|
| PFNudgeRateScale | - | 1.0 | Q/E turn the target at this x the ship's full turn rate for its speed |
| PFHeadingMaxLeadDeg | deg | 150 | The target stays within this of the nose (steering mode) |
| PFLookReturnTau | s | 0.22 | Camera ease-back after broadside mode |
| bPFArcAssist | bool | true | Gun lock on |
| PFArcMarginDeg | deg | 6 | The arc counts as the cannon yaw limit minus this (20 - 6 = 14) |
| PFArcMinBearingDeg / PFArcMaxBearingDeg | deg | 55 / 150 (review R1: was 35 / 150) | Broadside sector: outside it the aim never swings the ship |
| PFArcApproachRateDeg | deg/s | 3 | An aim closing on the arc faster than this is waited for |
| PFArcApproachTau (new, review R2) | s | 0.1 | Filter on that approach rate (uneven mouse counts at a high frame rate) |
| PFArcLockDelay | s | 0.25 | Outside the arc and not coming in this long = lock |
| PFArcLockDeadbandDeg | deg | 3 | Locked: the beam stays this close to the aim |
| PFArcRateDeg | deg/s | 45 | Fastest swing of the target by the lock |
| PFLockLeadTime | s | 0.45 | Locked: the sent target leads by its own rate x this |
| PFHeadingLeadRateMax / PFHeadingLeadTau | deg/s / s | 30 / 0.12 | Rate estimate for the lock lead (clamp, filter) |
| bPFPitchClimb | bool | false | Camera pitch -> climb (tested, off: section 10) |
| PFPitchClimbDeadbandDeg / PFPitchClimbFullDeg | deg | 10 / 20 | Its dead band around CameraDefaultPitch / full rate this far beyond |
| PFCameraRollPerBank / PFCameraRollMaxDeg | - / deg | 0.15 / 3 | Feedback (section 6). C++: shared `CameraRollPerBank` / `CameraRollMaxDeg` (`CameraRollInterpSpeed` 6) |
| PFFOVKickBoost / PFFOVKickFire / PFFOVKickDrift / PFFOVKickDecay | deg, deg, deg, 1/s | 5 / -3 / 4 / 5 | Feedback. C++: `FeedbackBoostStart` / `FeedbackOwnBroadside` / `FeedbackDriftKick` `.FOVKickDeg`, `FOVKickDecay` |
| PFShakeFire / PFShakeDriftKick / PFShakeHitPerMS / PFShakeMaxDeg / PFShakeDecay | -, -, 1/(m/s), deg, 1/s | 0.25 / 0.2 / 0.05 / 1.2 / 2.5 | Feedback (trauma shake). C++: `FeedbackOwnBroadside.Trauma`, `FeedbackDriftKick.Trauma`, `ShakeHitPerMS`, `ShakeRotDeg`, `ShakeDecay` (`ShakeFrequency` 13 Hz, one frequency with per-axis offsets) |
| PFRumbleScale | - | 1 | Gamepad rumble strength (0 = off). C++: shared `RumbleScale` |

Review R3: the feedback rows above are the shared feedback properties of `IMPLEMENTATION_PLAN.md` 1.10 (one
implementation for the three schemes); the values are the designer's.

**Existing tunables the Point & Fly preset changes** (every other tunable keeps its v1 value):

| Name | Classic (v1) | Point & Fly | Why |
|---|---|---|---|
| SteerTau (FC) | 0.15 s | 0.10 s | The loop's steer is already smooth; less lag inside the heading loop |
| Kr (FC) | 3.0 1/s | 5.5 1/s | Stiffer yaw-rate loop under the heading loop. The 1 rad/s² cap (AlphaYawMax) keeps big turns heavy (M4 t63 0.43 s) |
| StrafeTau / StrafeSpeed / StrafeBankDeg (FC) | 0.20 s / 1200 cm/s / 6 deg | 0.12 s / 1400 cm/s / 7 deg | A/D is the character-style sidestep |
| Kbrake (FC) | 0.9 1/s | 2.0 1/s | With PFBrakeAccelMax: 1.5 g air brake down to 7 m/s |
| AFan (FC) | 1323 cm/s² | 1400 cm/s² | Gives back v1's launch: the dip fix removed the 0.27 g the nose dip added (t80 3.27 s, v1 3.33). The fans plus the gimbal lean can deliver 1.45 W |
| PitchPerG / PitchMinDeg / BoostPitchDeg (FC) | 8 / -8 / 3 | 4 / -4 / 1.5 | Base fix 4a-3 |
| base-fix switches (FC) | off | section 3.7 | |
| RecenterSpeed (pawn) | 2 1/s | 0 | The camera is the steering: it never moves by itself |
| ImpactEpisodeAccelUp / ImpactMaxReboundSpeed (pawn) | 2500 / 250 | 2000 / 120 | Base fix 4e (rule above) |

DriftSteerThreshold, the yaw-rate table (30 / 45 / 35, drift 50, boost 25), the bank limits, boost, vertical rates, camera arm, FOV and cannon values all stay v1.

## 5. Camera

* **Steering mode.** The control rotation is the camera and the heading target at once. No recentre (RecenterSpeed 0): the camera moves only when you move it. The spring arm keeps its v1 rotation lag (7/s) and position lag (5/s), so the ship swings into view under the crosshair as it turns.
* **Pitch** is free (-60..+25 deg) and only aims. Looking down at the platforms never changes height (section 10).
* **Broadside mode** (Aim held): the camera is free. The FOV drops 15 deg (v1 AimFOVOffset), the hull flattens (bank x 0.4) and the gun lock may swing the ship (3.3).
* **Release:** the camera eases back onto the heading target (PFLookReturnTau 0.22 s: 95 % in 0.66 s). Mouse input during the ease-back steers at once.
* **The clamp:** the target never runs more than 150 deg off the nose. A full mouse spin drags the ship around at its full rate instead of flipping direction at 180 deg.
* **Set from outside** (harness, reset): a control rotation that changes with no IA_AirshipLook that frame is taken as an absolute camera and heading set (3.2). Without that rule, a harness that sets the camera while it eases back would swing the ship. That happened in the first bench version, a 12 deg swing.

## 6. Feedback (no new assets)

| What | How | Machine |
|---|---|---|
| The turn, readable | Unchanged rig paths, now driven by the heading loop's Steer. Wheel (spring, spins to ±321 deg on a big swing), fans ±12 deg, rudder, nozzle roll, 18 deg bank at speed, Niagara thrust differential | all |
| Nose marker vs crosshair | Section 7: the gap shows the turn still to come | pilot |
| Camera roll | Camera component relative roll = 0.15 x hull roll, max 3 deg, interp 6/s (aim and control rotation untouched) | pilot |
| FOV kicks | Additive offset, decays at 5/s: +5 on boost start, -3 on own fire, +4 on the drift kick | pilot |
| Trauma shake | T (0..1) decays at 2.5/s; offset = T² x 1.2 deg x Perlin noise at 11 / 13 / 17 Hz on the camera component's relative pitch / yaw / roll. Adds 0.25 on own fire, 0.2 on the drift kick, 0.05 per m/s of hull impact speed (`OnHullHit` already runs on every machine) | pilot |
| Rumble (gamepad) | The native `APlayerController::PlayDynamicForceFeedback(Intensity, Duration, bLeftLarge, bLeftSmall, bRightLarge, bRightSmall)` overload (PlayerController.h:1315; review R4: the CallbackTarget / UUID version is the Blueprint latent one). Fire 0.5 / 0.15 s large; boost start 0.3 / 0.35 s small; drift kick 0.6 / 0.2 s both large; hull hit min(1, v / 15 m/s) / 0.25 s; lock engages 0.15 / 0.06 s small (a tick). Times RumbleScale | pilot |
| Events on the pilot | Boost start = shaped boost crossing 0.5 upward. Drift kick = the pilot's own shaped `bDrifting` (new getter `IsDrifting()`) ending after at least DriftBoostMinTime. Own fire = `HandleCannonsFired` when locally controlled | pilot |

## 7. HUD (Slate, no assets)

A second instance of `UAirshipHUDWidget` in a new overlay mode. `ShowShipHUD` / `HideShipHUD` add and remove it next to the corner panel:
- `bOverlayMode = true`, set before it is added;
- the slot covers the whole viewport (anchors 0..1, offsets 0), with ZOrder 0, below the panel;
- the widget is `HitTestInvisible` like the panel;
- it draws only while the ship's scheme is Point & Fly.

The panel instance and its paint code are untouched.

Colours are the panel's ink (28, 24, 22), paper (240, 230, 205) and amber (232, 160, 40). Every mark is ink with a 1 px paper outline, for contrast on sky and platforms. Positions come from `UWidgetLayoutLibrary::ProjectWorldLocationToWidgetPosition(PC, P, Out, true)` in NativeTick and are cached for NativePaint.

| Element | Steering mode | Broadside mode |
|---|---|---|
| Crosshair (screen centre) | Small "+", 14 px: the heading target | Gun ring 36 px with two side brackets |
| Nose marker | "Λ" chevron 10 px at the projection of `CameraLocation + 600 m · Dir(hull yaw, camera pitch)`: same height as the crosshair, offset by the turn still to come. A thin ink line from it to the centre while the gap is over 3 deg, alpha with the gap. One paper flash when the gap closes below 1 deg | Same marker (shows where the bow points) |
| Heading strip | Hidden | Tick strip at top centre, ±60 deg wide (3 px/deg, ticks every 10 deg). "◆" = heading target, "▲" = bow; edge arrows when outside |
| Gun state | - | In arc (new `IsAimInCannonArc(Side, LocalAimPoint)`: either cannon of the facing side within ±CannonYawLimitDeg and CannonElevMin..Max, unclamped math of `ComputeCannonAim`) and loaded: amber brackets. In arc and reloading: the ring fills with the reload alpha. Out of arc: ink, dashed |
| Lock | - | "LOCK" tag (paper text on an ink box) under the ring, with a small arrow toward the swing |
| Hint | First 8 s after boarding in Point & Fly (once per session), bottom centre, fading: "LOOK = STEER · W/S DRIVE · A/D SIDESTEP · Q/E TURN" and "HOLD RMB / LB TO LOOK AROUND OR AIM · X / B IN A TURN: DRIFT" (review R1) | - |

The corner panel is unchanged.

## 8. Multiplayer

* **What runs where.**
  - Pilot: the camera, the heading target, Q/E, the gun lock, the lock lead, its own heading loop (cosmetics only), the feedback and the HUD.
  - Server: the heading loop on the authoritative hull, writing `Controls.Steer` before `RepInput`, and all forces.
  - Observers: ShapeControls on `RepInput`, as today. They see the server's Steer, so their wheel, fans and rudder follow the real hull.
* **Client pilot with 100 ms each way.**
  - The camera answers in 0 frames: the view swings the moment you move the mouse (Classic's view lags 13-19 frames behind a turn).
  - The wheel, fans and nozzles answer in 0 frames from the local loop.
  - The hull turns on the server after 5 frames and on your screen after 8 (Classic 6 / 9).
  - What you command is an absolute heading. The ship cannot oscillate under lag, because no loop runs over the network. The sloppy bot at 100 ms flies the gate course with 0 gates missed and a 7.7 m worst line error; in Classic it missed 6 gates and was 115 m off.
  - Steps settle about 0.13 s later than on the host, with the same zero overshoot (9.1).
* **What the client's cosmetics show.** The pilot's own loop runs on its replicated, lagging copy of the hull. Its wheel therefore unwinds about 0.1-0.2 s after the server's: cosmetic only, and it matches the hull the pilot sees.
* **Wire cost.**
  - `HeadingTarget` is a uint16, 2 bytes per packet, about 60 B/s.
  - It is not part of `SameControls`: camera driven, it rides the 30 Hz heartbeat like `AimPoint`.
  - The Steer axis now changes every frame of a turn, so packets go every frame while turning: 30/s at 30 fps, at most 60/s from a 60 fps client, under 1 KB/s.
* **Loss and neutral input.**
  - The server keeps the last target until the 0.5 s timeout.
  - Neutral input means no target, so the ship flies straight on and holds its altitude.
  - 0 is never a valid encoded heading, so neutral never means "head to yaw 0".
* **Scheme switch window** (half a round trip):
  - Classic packets arriving at a Point & Fly server carry no target, so their Steer axis is used, which is right.
  - Point & Fly packets arriving at another scheme's server are ignored apart from their axes: the local-loop Steer and the A/D Strafe, both sane for a few frames.
  - No scheme id is needed in the packet for this scheme.
* **Host pilot.** SelectControls returns the local input. The server loop recomputes Steer from the same hull state, so the value is the same.

## 9. Predicted metrics (sim) next to Classic

Classic = `classic_metrics.json` (v1 as it runs, bench calibrated against PIE). Point & Fly = `pointfly_metrics.json`. Bands are the ones I set for this scheme. "Bench band" is `metrics.METRIC_INFO` where mine differs.

| Metric | Classic | Point & Fly | Point & Fly band |
|---|---|---|---|
| M1 time to 80 % of top speed (s) | 3.33 | 3.27 | 2.8-3.5 ok |
| M1 speed at 2 s / 4 s (m/s) | 22.6 / 44.4 | 23.6 / 44.0 | |
| M2 top steady / peak (m/s) | 48.0 / 49.5 | 48.0 / 48.0 (no dip overshoot) | 45-55 ok |
| M2 boost peak (m/s), ratio | 88.1, x1.84 | 87.0, x1.81 | x1.7-1.9 ok |
| M2 boost duration / t90 (s) | 3.6 / 3.0 | 3.6 / 2.8 | |
| M3 brake: stop time (s) / distance (m) | 2.17 / 38.6 | 2.47 / 56.9 | 1.8-2.8 s, ≤ 60 m ok |
| M3 peak / mean decel (g) | **4.31** / 2.26 | 2.39 / 1.98 | peak ≤ 2.5 ok (v1 fails) |
| M3 coast to half speed (s) | 10.8 | 11.3 | 8-15 ok |
| M4 full turn: t63 / t90 (s) | 0.50 / 0.90 | 0.43 / 0.70 | ≤ 0.5 / ≤ 0.8 ok |
| M4 turn rate (deg/s), overshoot | 35.1, 2.2 % | 35.0, 0.5 % | ≤ 3 % ok |
| M4 bank / slip at 8 s (deg) | 17.8 / 19.6 | 18.8 / 15.7 | bank 15-22 ok |
| M4 height lost in 8 s (m) | **5.15** | 0.06 | ≤ 1 ok |
| M4 nose pitch min (deg) | -6.7 | -1.8 | |
| M5 180 deg turn: time (s) / diameter (m) | 5.6 / 181 | 5.5 / 176 | 4-6 s, ≤ 180 m ok |
| M6 nose pitch: drive min / at top (deg) | **-16.6** / -1.3 | -4.0 / 0.0 | -3..-6 ok |
| M6 boost min / brake max (deg) | **-20.2** / +7.5 | -5.2 / +5.8 | -4..-8 / +3..+7 ok |
| M7 climb / sink (m/s) | 12.0 / 15.0 | 12.0 / 15.0 | 10-15 ok |
| M7 +30 m step: rise (s) / overshoot (m) | 3.33 / **12.1** | 3.33 / 5.7 | overshoot ≤ 6 ok (bench band ≤ 1.5: see 11) |
| M7 abs vz 1 s / 2 s after release (m/s) | **5.84** / 0.57 | 0.56 / 0.06 | ≤ 1.0 / ≤ 0.3 ok |
| M7 error 5 s after release (m) | 11.5 | 5.6 (= where it stopped) | |
| M8 sidestep: t90 (s) / speed hover, cruise (m/s) | 0.87 / 12.3, 12.3 | 0.77 / 14.3, 14.3 | ≤ 0.8 s, 12-16 ok |
| M9 drift: slip at 1 / 2 / 3 s (deg) | 15 / 42 / 63 | 16 / 42 / 65 | |
| M9 drift turn rate (deg/s), speed kept | 49.8, 103 % | 50.1, 100 % | |
| M9 exit kick measured / paid (m/s) | 4.8 / 6.0 | 4.7 / 6.0 | 4-8 ok |
| M10 host: turbine / wheel / nozzle (frames) | 0 / 0 / 0 | 0 / 0 / 0 | 0 ok |
| M10 host: turn on server / screen, speed on screen | 2 / 2 / 1 | 1 / 1 / 1 | ≤ 2 ok |
| M10 client 100 ms: turbine / wheel / nozzle | 0 / 0 / 0 | 0 / 0 / 0 | 0 ok |
| M10 client 100 ms: turn on server / screen, speed on screen | 6 / **9** / 8 | 5 / 8 / 8 | ≤ 8 ok |
| (extra) camera view reacts to the turn input, host / 100 ms (frames) | 13 / 19 | 0 / 0 | 0 ok |

**M11 gate course** (`course.py`; Point & Fly bot gains from `course.py pointfly --tune`, score 140.9 against Classic's 141.6):

| Bot / pilot | Classic | Point & Fly |
|---|---|---|
| precise, host | 60.5 s, 0 missed, line 2.2 / 4.6 m | 59.1 s, 0 missed, line 2.7 / 5.9 m |
| precise, client 100 ms | 62.7 s, 0 missed, line 2.4 / 4.6 m | 60.2 s, 0 missed, line 1.5 / 4.6 m |
| sloppy, host | 61.6 s, **1 missed**, line 6.4 / 10.4 m | 59.8 s, 0 missed, line 1.1 / 1.8 m |
| sloppy, client 100 ms | 78.2 s, **6 missed**, line 40.5 / 115 m, 2 ground hits | 59.1 s, 0 missed, line 4.1 / 7.7 m |

Line = error from the bot's racing line at the gates, mean / max. The Point & Fly bot looks along the planned course, a little into the turn (`LEAD_PER_COURSE * course` s of the line's turn rate). It never reads the ship's own heading: the server closes that loop. Camera reversals 54-93 /min, the mouse's equivalent of Classic's 9-14 steer reversals /min.

**M12 broadside orbit** (the bot holds Aim and looks at the target; the gun lock keeps the beam on it, A/D hold the range):

| Bot / pilot | Classic: in arc / firing solution / broadsides / elev max | Point & Fly: in arc / firing solution / broadsides / elev max / beam yaw mean |
|---|---|---|
| precise, host | 100 / 100 % / 40 / 6.1 deg | 100 / 100 % / 40 / 2.0 deg / -2.6 deg |
| precise, 100 ms | 100 / 100 % / 40 / 6.0 deg | 100 / 100 % / 40 / 3.6 deg / -6.7 deg |
| sloppy, host | **69 / 69 %** / 37 / 17.9 deg | 100 / 100 % / 40 / 4.5 deg / -6.2 deg |
| sloppy, 100 ms | **37 / 34 %** / 21 / 22.7 deg | 100 / 100 % / 40 / 5.7 deg / -10.2 deg |

Two things give the gain:
- **The steady gun deck** (bank x 0.4 while aiming) keeps the target inside the +8.5 deg elevation limit. In Classic, the sloppy bot's on/off steering banked the hull 18-23 deg and lifted the target out of the arc.
- **The gun lock** steers the orbit, so a sloppy hand only works the range.

The bench sloppy bot moves the camera as a smooth analog signal. That flatters any camera-steered scheme, so 9.1 adds a human-like mouse.

### 9.1 Point & Fly checks (`pointfly_checks.py`, in `pointfly_checks.json`)

| Check | Result |
|---|---|
| **Camera snaps at cruise** (host): settle to ±0.5 deg (±0.25 for 2 deg), overshoot | 2 deg 0.53 s; 10 deg 0.87 s; 45 deg 2.07 s; 90 deg 3.43 s; 150 deg 5.17 s; overshoot ≤ 0.02 deg every time; turn rate t63 0.43 s, 19 deg bank, wheel to ±321 deg |
| Same, client 100 ms | +0.13 s each (10 deg 1.0 s, 90 deg 3.57 s), overshoot ≤ 0.02 deg |
| Same, at hover (pivot, 30 deg/s) | 10 deg 0.87 s, 90 deg 3.6 s, no overshoot, 5 deg bank |
| **Camera sweeps** 10 / 20 / 30 deg/s for 3 s, then stop | hull trails 3.3 / 7.2 / 13.6 deg (100 ms: 4.7 / 9.9 / 17.6), **0 overshoot** after the stop, settled in 0.4-1.0 s |
| **Reversals at cruise** (camera flicked onto the new heading) | 180 deg: plain turn 5.6 s, 178 m wide, keeps 50.7 m/s. **Brake-turn** (S to 30 m/s, then W) 5.1 s, 112 m. **Brake-drift**: nose round in 4.1 s (plain 5.4), 79 deg slip, +6 m/s kick, 122 m. 90 deg: turn 2.8 s / brake-turn 2.7 s, 47 m / drift nose 2.4 s |
| **Racing pass**: target 100 m off the track, Aim from 45 deg off the bow, let go after 2 broadsides | 2 broadsides, 1.5 s of firing solution, heading swing 0.4 deg, 0.8 m off the track; the same with the lock off; Classic 2 broadsides, 1.4 deg, 1.3 m |
| **Charge**: target dead ahead, broadside swung onto it at 250 m | plain turn: first solution after 4.0 s, 3 broadsides in 8 s. **Drift broadside** (flick + X, Aim 0.3 s later): first solution after 2.3 s, 4 broadsides, closest 134 m, leaves at 56 m/s |
| **Human-like mouse**, sloppy bot, gate course (hand overshoot 20 %, 1.5 + 0.8 deg jitter) | 0 missed (line 1.5 / 2.6 m host, 4.7 / 9.9 m at 100 ms) |
| ... plus glances (25-50 deg aside, 15 deg down, 0.5-0.9 s every 6-10 s) **without** Aim | **1 missed** (H1) on the host and 1 (H1) at 100 ms, the hairpin run up to 101 / 140 m wide; line 8.5 / 13.0 m mean (review: the JSON's numbers; the spec had said 2 missed). Glancing steers: the known cost of camera steering (section 11) |
| ... the same glances **with** Aim held | 0 missed (line 2.6 / 9.1 m host, 9.9 / 32 m at 100 ms) |
| **Keyboard only** (Q/E turn, no mouse) | precise 0 / 0 missed (host / 100 ms), sloppy 0 / 0 missed; line max 6.0 / 9.2 / 6.2 / 14.7 m |
| **Pitch climb** (bPFPitchClimb) | no gain on the course (same 0 missed, similar climb / dive gate errors); 1 s glances down at -47 deg every 8 s cost **20.7 m** of altitude in 32 s (off: 0 m). Off by default |

## 10. Design decisions the bench settled

| Tried | Result | Decision |
|---|---|---|
| Loop gains (Kp 2.2-8, lead 0.15-0.3 s, decel 40-70, Kr 3-6, SteerTau 0.06-0.10), scored on settle time + 6 x overshoot over 2 / 10 / 90 deg steps at cruise and hover | Kp 2.2 / Kr 3: 10 deg in 1.7 s (a slow exponential tail). Kp 6.5, lead 0.18, decel 55, Kr 5.5: 10 deg in 0.87 s, no overshoot. Kp 8 / Kr 6 at most 0.1 s better | 6.5 / 0.18 / 55 / 5.5: crisp small corrections, big turns still accel-limited (heavy) |
| Leading the sent target by its own rate in steering mode (0.2-0.4 s) | Halves the sweep lag but overshoots 1-6 deg when the camera stops | Off in steering mode (precision first); on only while the gun lock drags the target (0.45 s: beam offset -10..-17 -> -2.6..-10 deg) |
| Bot adapter: over-pointing by the course error / rate-to-heading offset | Oscillated (330 camera reversals /min, 3-9 gates missed) | The bot just looks along the course, as a player does |
| Gun lock parks the aim at the arc edge | The orbit drifts out to 180-220 m (the beam trails the tangent by 18 deg) | Lock with a 3 deg dead band |
| Lock engages whenever the aim is outside the arc | Racing pass: the ship swings 28 deg off the line (35 m, 5.6 s to recover) | Waits for a target that is coming into the arc (approach rate) plus a 0.25 s dwell: pass 0.4 deg / 0.8 m, orbit unchanged |
| Q/E target clamped to 10-20 deg ahead of the nose | At 100 ms it closes a loop on the lagging view: 3-6 gates missed | Open loop: Q/E turn at the ship's own full rate (0 missed; the ship turns 16 deg more after the key is let go, Classic 13 after D) |
| Camera pitch -> climb | No precision gain (the lift keys already stop dead with the base fixes); glances down cost 21 m | Off (`bPFPitchClimb` stays for anyone who wants to try it) |
| A drift through the course hairpin (expert line) | Faster but cut the H1 / H2 gates: the hairpin is taken at full speed anyway | The drift's value is the nose swing (reversals, the drift broadside), not this course |
| Double-tap A/D dodge | Not built. Feathering A/D (the sloppy bot's 0.1 s taps) would set it off by accident | Left out; the drift broadside is the special move |

## 11. Known risks

1. **Looking around steers** (the weakest point; reduced by review R1, not removable). A yaw glance without Aim turns the ship. A 0.5-0.9 s glance every 6-10 s cost 1 gate on the course (the hairpin, 100-140 m wide); with Aim held it cost none at 0 ms.
   - It is the identity of the scheme: any rule that ignored a glance would delay every real steering input, because a turn is acceleration-limited from about 10 deg of error.
   - Mitigations: camera pitch never steers, the nose marker shows the turn, and Aim is the "look" button.
   - Review R1 makes that button clean for looking ahead: the gun lock only acts on an aim 55-150 deg off the bow, so a look ahead with RMB held never swings the ship (bench-neutral: M12, the pass and the charge are unchanged).
   - Tutorial hint: "HOLD RMB / LB TO LOOK AROUND OR AIM" (section 7).
2. **PIE may not match the bench on the stiffer yaw loop (Kr 5.5).** Real contacts, deck walkers and recoil are not in the bench.
   - Risk: wheel or fan jitter at rest, or a yaw buzz.
   - Watch: `Aura.Airship.Telemetry` Steer at hover with a walker on deck. The 0.25 deg / 2 deg/s dead band should hide it.
   - Fallback: Kr 4.5 (sweep: 0.1 s slower, still no overshoot).
3. **Base-fix dependence.** The pitch numbers (M6) need 4a-1 (inertia). The yaw numbers barely do: Izz is used 0.97x either way.
   - Confirm the inertia log first (BASELINE 4f row 0).
4. **M7 overshoot 5.7 m is physics, not a bug.** From a 12 m/s climb at 0.75 g + 0.8 g of hidden brake the stopping distance is 4.7 m, plus the 0.08 s filter. The bench band of ≤ 1.5 m would need a 5 g stop.
   - The ship stops where it stops (no bounce back), 0.56 m/s 1 s after release.
   - A harder stop needs VertBrakeAccel 1200 and ImpactEpisodeAccelUp 2400: 5.0 m (sim).
5. **Softer brake.** 57 m from cruise (Classic 39 m) in exchange for 2.4 g instead of 4.3 g.
   - If races need shorter stops: PFBrakeAccelMax 1960 (sim: 2.2 s, 47 m, 2.85 g peak).
6. **Relearning for Classic players.** A/D now sidestep and Q/E turn. The boarding hint (section 7) and the switchable scheme cover it.
7. **The gun lock can surprise.** Holding Aim after the target passes turns the ship to follow it.
   - That is by design and signalled ("LOCK" tag, rumble tick); releasing Aim ends it.
   - `bPFArcAssist` = false gives plain free look (racing pass identical, orbit needs Q/E).
8. **Bench limits.** No contacts and no client-copy smoothing (PIE showed 0-2 frames more). The bench bots drive the camera as mouse deltas (`mouse_to_heading`). The PIE harness sets the control rotation absolutely, which the external-set rule (3.2) reads the same way.
9. **Bit and field budget.** Point & Fly uses no Buttons bit. If another scheme also adds a uint16, the packet grows by 2 bytes each.

## 12. C++ change list

**`IMPLEMENTATION_PLAN.md` is the authoritative, ordered change list** (shared framework in its section 1, Point & Fly
in 2.3). This section is the designer's list, corrected by the review; where they differ, the plan wins (the shared
brake cap, gun deck, yaw table and arc helper; `ActiveScheme` on the flight component; reset hooks; the HUD layout
refresh).

Paths are under `Source/Aura/`; line numbers are at 8f01bca. The contract items (`EAirshipControlScheme`, `ControlScheme` + `SetControlScheme` / `GetControlScheme` / `OnRep_ControlScheme`, the preset table, `Aura.Airship.Scheme`, the telemetry fields) are shared and assumed implemented once by the implementer. The base fixes (3.7) are shared too, per BASELINE.md 4. Below is what Point & Fly adds on top.

### 12.1 `Public/Airship/AirshipTypes.h`

```cpp
// FAirshipPilotInput, after AimPoint:
/** Point & Fly heading target (world yaw): 1..65534 = 1 + round(yaw mod 360 / 360 * 65534), 0 = no target.
 *  Not in SameControls (camera driven; rides the InputSendRate heartbeat like AimPoint). */
UPROPERTY()
uint16 HeadingTarget = 0;

static uint16 EncodeHeading(float YawDeg)
{
    float W = FMath::Fmod(YawDeg, 360.f);
    if (W < 0.f) { W += 360.f; }
    return static_cast<uint16>(1 + FMath::RoundToInt(W / 360.f * 65534.f) % 65534);
}
bool HasHeadingTarget() const { return HeadingTarget != 0; }
float GetHeadingTargetDeg() const { return FRotator::NormalizeAxis((HeadingTarget - 1) * (360.f / 65534.f)); }

// new plain struct (not a USTRUCT), shared by the server and the pilot copy of the loop
struct FPointFlyLoopState { bool bDrift = false; };
```

`SameControls` is unchanged. `DebugSetInput` and `Aura.Airship.Input` leave `HeadingTarget` = 0, so they stay Classic-style cross-checks in any scheme.

### 12.2 `Public/Airship/AirshipFlightComponent.h`

* The UPROPERTYs of section 4, first table (EditAnywhere, BlueprintReadOnly, category `Airship|PointFly`, ClampMin 0 on all), with the "C++ default" column as default.
* Public:
  * `float GetYawRateMaxDeg(float ForwardSpeed, float Boost, bool bDrift) const;` (the table of `FC.cpp:787-791`; ApplyForces calls it too).
  * `float ComputeHeadingSteer(float TargetYawDeg, float YawDeg, float YawRateDegS, float ForwardSpeed, float Boost, bool bBrake, FPointFlyLoopState& State) const;` (3.5).
  * `float GetShapedBoost() const { return ShBoost; }` and `bool IsDrifting() const { return bDrifting; }`.
  * `void ResetPointFlyState() { ServerHeadingLoop = FPointFlyLoopState(); LastGripAccelZ = 0.f; }`.
* Private: `FPointFlyLoopState ServerHeadingLoop;` and `float LastGripAccelZ = 0.f;` (cm/s², server).

### 12.3 `Private/Airship/AirshipFlightComponent.cpp`

* `UpdateFlight`, authority branch between `:445` and `:448`, runs the server heading loop (3.5). Inputs:
  * BodyYaw = `Body->GetComponentRotation().Yaw`;
  * BodyYawRateDeg = `Body->GetPhysicsAngularVelocityInDegrees().Z`;
  * ForwardSpeed from `:439`;
  * `ShBoost` = last frame's shaped boost.

  Run it only when `ActiveScheme == EAirshipControlScheme::PointFly && bFlightEnabled && Controls.HasHeadingTarget()` (`ActiveScheme`: the flight component's copy of the pawn's scheme, set by `ApplyControlScheme`; no cast per frame); else `ServerHeadingLoop = FPointFlyLoopState()`.
* `ComputeHeadingSteer`: 3.5 verbatim.
* `ApplyForces`: 3.6.
  * `ACmd` (`:594`) must be computed after the AFanCmd / ABrake changes, so the pitch target sees them.
  * Reset `LastGripAccelZ` and `ServerHeadingLoop` where `bHoldValid` / `DriftTime` are reset (`:489-491`) and in `ResetInput` (`:265-271`).
* `FillTelemetry`: `bHeadingTargetActive = CurrentControls.HasHeadingTarget()` and `HeadingTargetDeg = CurrentControls.GetHeadingTargetDeg()` (else 0). On the server these are the received values; on observers they come from `RepInput`.

### 12.4 `Public/Airship/AirshipPawn.h`

* The UPROPERTYs of section 4, second table (EditAnywhere, BlueprintReadOnly, category `Airship|PointFly`).
* Private state:

```cpp
bool bPFValid = false;  bool bPFFree = false;  bool bPFLock = false;
float PFHeading = 0.f;  float PFLookOffset = 0.f;  float PFLastSetYaw = 0.f;  float PFSentHeading = 0.f;
float PFLockDwell = 0.f; float PFPrevOffBeam = -1.f; float PFHeadingRate = 0.f; float PFPrevHeading = 0.f;
FPointFlyLoopState PilotHeadingLoop;
uint64 LastLookInputFrame = 0;
// feedback
float PFTrauma = 0.f; float PFFOVKick = 0.f; float PFCameraRoll = 0.f;
bool bPFWasBoosting = false; bool bPFWasDrifting = false; float PFLocalDriftTime = 0.f;
```

* Functions:
  * `void UpdatePointFlyCamera(float Dt, APlayerController* PC);` (3.2).
  * `float PointFlyGunLock(float H, float CamYaw, float Dt);` (3.3).
  * `void ResetPointFlyState(bool bEaseCamera);` (3.8).
  * `bool IsAimInCannonArc(EAirshipSide Side, const FVector& AimPoint) const;`.
* Overlay accessors (BlueprintPure is fine): `IsPointFlyActive()`, `GetPFHeadingTargetDeg()` (= `PFSentHeading`), `IsPFFreeLook()`, `IsPFGunLocked()`.

### 12.5 `Private/Airship/AirshipPawn.cpp`

* `OnLookInput` (`:727-730`): beside `LastLookInputTime`, set `LastLookInputFrame = GFrameCounter`. The PlayerController applies the mouse delta (TickPlayerInput, then UpdateRotation, both in its PlayerTick) before the pawn ticks, so the delta is in the control rotation when `UpdatePointFlyCamera` runs.
* `GatherLocalInput` (`:631-678`): in the `else` branch (not debug input), when `ControlScheme == PointFly`:
  1. call `UpdatePointFlyCamera(DeltaSeconds, PC)` first;
  2. then fill the controls as in 3.4: `Strafe` from `SteerAction`, Q/E read inside step 1 and not sent, `HeadingTarget`, and `Steer` from `Flight->ComputeHeadingSteer`;
  3. the hull values for that call come from this machine's body: yaw, angular velocity Z in deg/s, and the forward speed `dot(GetPhysicsLinearVelocity(), GetForwardVector())`.
* `UpdatePointFlyCamera`: 3.2 and 3.3.
  * Read Q/E with the existing `Axis(StrafeAction)` lambda.
  * The nudge rate is `PFNudgeRateScale * Flight->GetYawRateMaxDeg(ForwardSpeed, Flight->GetShapedBoost(), false)`.
  * Write the rotation with `PC->SetControlRotation(FRotator(ClampedPitch, PFHeading + PFLookOffset, 0))`.
  * Handle `bPendingCameraReset` like `UpdateCamera` does (it stays the place that consumes the flag); `UpdateCamera`'s recentre is off through the preset (RecenterSpeed 0).
* `UpdateCamera` (`:1556-1617`), Point & Fly only, after the FOV line:
  * target FOV += `PFFOVKick`;
  * `PFFOVKick` decays (`FInterpTo` toward 0 at `PFFOVKickDecay`);
  * trauma shake and camera roll on `Camera->SetRelativeRotation(FRotator(ShakePitch, ShakeYaw, PFCameraRoll + ShakeRoll))` (section 6);
  * event detection (boost start, drift kick) and rumble.
* `HandleCannonsFired` (`:1467`): if locally controlled and Point & Fly, add trauma 0.25, `PFFOVKick += PFFOVKickFire` and rumble.
* `OnHullHit` (`:1775`): on the pilot's machine, add trauma `PFShakeHitPerMS * impact m/s`, capped at 1, and rumble.
* `ResetPointFlyState`:
  * called from the scheme apply (BeginPlay / `SetControlScheme` / `OnRep_ControlScheme`, with `bEaseCamera = true`), from `UpdateLocalMappingContext` (via `bPFValid = false`), from `OnRep_PilotCharacter` (every machine) and from `HandleDeath`; `bPFValid` is also kept false while debug input is active;
  * it also calls the flight component's server-loop reset.
* `GetFlightTelemetry` (`:2218-2236`): on the pilot's machine (`IsLocallyControlled()`) in Point & Fly:
  * `bHeadingTargetActive = bPFValid`, `HeadingTargetDeg = PFSentHeading`, `bFreeLook = bPFFree`;
  * on the server for a client's ship: `bFreeLook = CurrentControls.IsAiming()`;
  * `Scheme = 3`, `ThrottleOrder = -2`, `DriftCharge = 0`.
* `ShowShipHUD` / `HideShipHUD` (`:2092-2153`): also create / remove the overlay instance. It is a second `UAirshipHUDWidget` (same `ShipHUDClass`) with `SetOverlayMode(true)` before `AddWidgetForPlayer`, a full-viewport slot (`Anchors (0,0,1,1)`, offsets 0, ZOrder 0), and `SetAirship(this)`. Keep it in a new `UPROPERTY(Transient) TObjectPtr<UAirshipHUDWidget> ShipOverlayWidget`.
* `IsAimInCannonArc`: the unclamped yaw / elevation of `ComputeCannonAim` for the side's two cannons against the point; true if either is within the limits.

### 12.6 `Public/Airship/AirshipHUDWidget.h`, `Private/Airship/AirshipHUDWidget.cpp`: overlay mode

* New: `void SetOverlayMode(bool bOverlay)` and a private `bool bOverlayMode = false`.
* `RefreshValues` (`HUD.cpp:84-120`): in overlay mode, read and cache instead:
  * the pawn's Point & Fly state;
  * the projected nose point (`UWidgetLayoutLibrary::ProjectWorldLocationToWidgetPosition`) and the heading-strip markers;
  * `GetCannonReloadAlpha` / `IsAimInCannonArc` for the facing side;
  * the lock flag.
  Skip the ground trace there.
* `NativePaint` (`HUD.cpp:122-266`): in overlay mode, return after drawing section 7's marks with the existing `Box` / `Text` / `MakeLines` helpers. Nothing when `!Airship->IsPointFlyActive()`. The panel path is unchanged.
* Two new brushes for the gun ring (a rounded box with radius = half its size, outline 2 px) come from `RefreshBrushes`. The colours reuse the panel's UPROPERTYs.

### 12.7 Preset table: the Point & Fly row

Every value in section 4: the PF-column flight and pawn tunables, the changed existing tunables, and the base-fix switches. A switch away restores each one from its own row; Classic is the v1 column.

### 12.8 Telemetry (contract fields, Point & Fly values)

| Field | Pilot's machine | Server | Observers |
|---|---|---|---|
| Scheme | 3 | 3 | 3 |
| ThrottleOrder / DriftCharge | -2 / 0 | -2 / 0 | -2 / 0 |
| bHeadingTargetActive | target valid | a target arrived (`CurrentControls`) | from `RepInput` |
| HeadingTargetDeg | sent target (with lock lead), world deg -180..180 | received target | from `RepInput` |
| bFreeLook | Aim held | `Button_Aim` | `Button_Aim` |

Optional, not in the contract: `bPFGunLock` (pilot only) for the harness.

## 13. PIE harness notes for this scheme

* **Steering.** Set the PlayerController's control rotation without injecting IA_AirshipLook. The rule in 3.2 takes it as an absolute heading target and camera.
  - The bench bots call `PointFly.mouse_to_heading`, which turns a wanted heading into a mouse-relative control yaw while the camera eases back after broadside mode. In PIE the set is absolute, so the adapter must use the wanted heading itself: keep `'H'` out of the PIE adapter's `pilot_state` and `mouse_to_heading` returns it unchanged (`IMPLEMENTATION_PLAN.md` 5).
  - "Full steer" (M4 / M5 / M10) = set yaw = ship yaw + 90 deg every frame.
  - "Steer off" = set yaw = ship yaw + yaw rate x 0.3 s once, then leave it.
* **Sidestep (M8)** is IA_AirshipSteer (A/D) in this scheme. IA_AirshipStrafe (Q/E) turns.
* **Drift (M9):** keep the camera 90 deg ahead of the nose and hold IA_AirshipBrake.
* **Broadside (M12):** hold IA_AirshipAim and set the control rotation onto the target every frame, absolute. Use A/D for range.
* **Time zero (M10):** the first frame where the pilot's own `FAirshipPilotInput` changes. That is `HeadingTarget`, and Steer in the same frame.
* **Aiming** in broadside mode works the same way: set the rotation absolutely without IA_AirshipLook, and the camera goes there while the heading holds (or the gun lock moves it).
* **Checks:** `pointfly_checks.py` holds the steps, sweeps, pass and charge protocols as plain Python, the same way `course.py` holds the bots.

## 14. Files

| File | What |
|---|---|
| `sims/scheme_pointfly.py` | The scheme plug-in: presets, camera / heading target, gun lock, heading loop, server hooks, bot adapters, the base-fix `PFFlightModel` (a subclass, because the bench has no hook inside ShapeControls / ApplyForces; `--selftest` proves it equals the bench with the fixes off) |
| `sims/pointfly_checks.py`, `sims/pointfly_checks.json` | Section 9.1 checks (my own; the bench files are untouched) |
| `sims/pointfly_metrics.json` | M1-M12 (`metrics.py pointfly`) |
| `SCHEME_POINTFLY.md` | This spec |

## Review changes

Adversarial review before any C++ was written (2026-11-23). Re-run first: `scheme_pointfly.py --selftest` PASS,
`metrics.py pointfly` reproduced `pointfly_metrics.json` exactly and `pointfly_checks.py` reproduced
`pointfly_checks.json` exactly; both again after R1 / R2 (0 differences: the bench bots never aim 35-55 deg off the bow
and move the camera smoothly). The sims must run from their own folder (`airship_sim.py` reads its keel points from
`../../sims/fix2/ucx.json`). The design and every number are the designer's, apart from the glance row of 9.1.

| # | What changed | Why |
|---|---|---|
| R1 | **Weakest point (looking around steers), reduced:** the gun lock's broadside sector starts at 55 deg off the bow (`PFArcMinBearingDeg` 35 → 55), so RMB is a clean "look around" key for anything ahead; the boarding hint says so. Sections 2, 3.3, 4, 7, 11 (risk 1). | Glancing without Aim cost a gate and a 100-140 m wide hairpin. That cannot be removed without delaying every real steering input (a turn is acceleration-limited from about 10 deg of error, so a glance and a steer look alike for the first 0.3 s). The fix is to make the existing mitigation clean: as designed, a look 35-55 deg off the bow with RMB held engaged the lock after 0.25 s and swung the ship toward putting its beam there. Two alternatives were tried and dropped: arming the lock only by a broadside (the "charge" check then never got a solution) and a 0.8 s lock delay with an instant lock on fire (the "racing pass" then swung 11-18 deg off the line). |
| R2 | The aim's approach rate in the gun lock is filtered (`PFArcApproachTau` 0.1 s, new pawn property). | Mouse counts arrive unevenly; at 120 fps the raw per-frame rate flips "coming in" on and off and resets the dwell. Bench-neutral. |
| R3 | Shared names: `PFBrakeAccelMax` → `BrakeMaxAccel`, `PFAimBankScale` → `GunDeckBankScale`, the camera roll / FOV / shake / rumble values → the shared feedback properties, `GetYawRateMaxDeg` and `IsAimInCannonArc` shared with the other schemes. The bench keeps the old names (mapping in `IMPLEMENTATION_PLAN.md` 6). | One implementation per mechanism for all three schemes. `PFTurnLiftComp` stays: the review tried the shared level grip in its place; M1-M12 were the same, but the single-seed glance and keys checks moved by 1-2 gates either way, so the designer's tested choice is kept. |
| R4 | Rumble names the native `PlayDynamicForceFeedback` overload. | The CallbackTarget / UUID form is the Blueprint latent function. |
| R5 | Resets also run from `OnRep_PilotCharacter` (every machine), and the pilot-side heading state is invalid while debug input is active. | `PossessedBy` / `UnPossessed` run only on the server; after a `DebugSetInput` run the old heading target would swing the ship back. |
| R6 | Section 9.1's glance-without-Aim row now quotes `pointfly_checks.json` (1 missed on the host, H1; the text had 2). Section 13: the PIE adapter sets the camera to the wanted heading itself. | The JSON is the source; `mouse_to_heading` is mouse-relative and would be off by the ease-back offset under an absolute set. |
| R7 | Section 12 points at `IMPLEMENTATION_PLAN.md` as the authoritative change list; the server loop and the force changes test the flight component's `ActiveScheme`, so `PFReverseBrakeAccel` and `PFTurnLiftComp` default to their Point & Fly values (980, 1) instead of 0 (the preset still restores them on every switch). | One list for the implementer; no pawn cast every frame; scheme-only behaviour is gated by the scheme everywhere. |

Checked and left as designed: the external-set rule relies on the PlayerController ticking before the pawn
(`AController::AddPawnTickDependency`, Controller.cpp:495) and on `PlayerTick` running `TickPlayerInput` before
`UpdateRotation` (PlayerController.cpp:2326-2365), both true in 5.8; the control yaw comes back in [0, 360) from
`LimitViewYaw`, which the wrap of `d` handles; the heading encoding never sends 0; the server-only loop; the lock lead;
gains at 1/30 s and 1/120 s (`sims/review_fps_check.py`: the same turn, settle and brake within 0.05 deg/s and 0.03 s); all contract
fields. Distinctness: Point & Fly is the only scheme where the camera steers and A/D sidestep; it is the one most
unlike Classic, and the one to watch for "I only wanted to look" in PIE.

### Polish after judging (2026-11-23)

Point & Fly won the judging (weighted totals 22.31 against Sky Racer 22.07, Galleon 21.17, Classic 14.03; one first
place of three) and is now **the default scheme** (`AAirshipPawn::ControlScheme`; the tunables' class defaults are
still v1, so Classic is unchanged). Each change below was modelled in the bench first and kept only where the bench
and the judges' reasoning agreed. New checks: `pointfly_checks.py exit kick park rival m12cam`. Pass 1 is kept in
`sims/pointfly_metrics_pass1.json` and `sims/pointfly_checks_pass1.json`. The C++ is listed in CPP_NOTES.md 14.12.
Built clean and **verified in PIE** (2026-11-23, `PIE_RESULTS.md` "Final"): every maneuver equals the polished bench;
m9 exit overshoot 1.67 deg, kick snake 48.91 m/s, a parked look orbit turns the hull 0.00 deg, Aim without Fire 0 lock
frames, M12 target 4.72 / 4.71 deg aft of the beam. **Follow-up after the final review** (`PIE_RESULTS.md`
"Follow-up", 9/9 checks): F-A, Fire held now arms the lock (P4); F-B, a hit no longer ends the parked free look (P3;
bench switch `PARK_LATCH` in `sims/scheme_pointfly.py`, new check `push`). PIE matches the bench: knock 24.62 / 24.6
deg, back to 0.1 / 0.09 deg, W 3.3 / 3.3 s.

| # | Change | Why (judge / PIE issue) | Bench, pass 1 -> polish |
|---|---|---|---|
| P1 | Drift-kick cap: kick = min(6 m/s, max(0, 48 m/s - forward speed)). New shared tunable `DriftBoostCapSpeed` (0 = off, as in every other scheme); Point & Fly 4800 cm/s. The pilot's FOV / shake / rumble punch scales with the share paid | compete (dealbreaker): rhythmic brake-drifts beat W by 49 % on a straight | snake 1.23 s / 0.1 s gaps 71.5 -> 48.8 m/s, 0.4 s gaps 57.7 -> 47.4, 1.5 s drifts 60.5 -> 48.1 (W: 48.0). The 180 deg brake-drift reversal still pays 6 m/s (47.9 m/s 8 s later); M9 still pays 6.0 (the slide leaves the forward speed near 20 m/s) |
| P2 | `GyroYawMax` 0.5 -> 1.0 rad/s², plus Galleon's "meet her" `KrSteady` 5.5 /s, `AlphaYawMaxSteady` 1.5 rad/s² | feel + compete grafts, PIE issue 8 (8.5 deg past the target after a 49 deg/s turn) | The judges' meet-her alone changed nothing (8.63 -> 8.64 deg): the actuators, not the 1 rad/s² cap, limited the stop (the gyro sat at its 0.5 limit with the fans saturated). With the gyro at 1.0: M9 exit overshoot 8.63 -> **1.67 deg** host (11.62 -> 6.33 at 100 ms), within 0.5 deg after 1.07 s (was 1.8); 179 deg brake-drift reversal 2.9 -> 0.3 deg. Turn onset unchanged (AlphaYawMax 1 still caps it: M4 t63 0.43 s, steps / sweeps identical) |
| P3 | Parked free look: below 3 m/s with no W/S, A/D, Q/E or boost held, the mouse looks around and the heading holds; the first such key takes the camera's yaw as the heading (beyond the 150 deg reach the camera eases back as after broadside mode). New `PFParkSpeed` 300 cm/s (0 = off). An outside set (harness) still sets the heading. Follow-up F-B: once parked it holds at any speed until such a key, Aim, or an outside set above 3 m/s, so a hit no longer ends it (`PARK_LATCH`) | newplayer (dealbreaker + graft): orbiting the camera after boarding spun the ship; on foot, looking never moves the mech | 360 deg camera orbit in 4 s at hover: hull turned 111 deg during it and 100 deg 6 s later -> 0 / 0. Look 120 deg right, then W: on that heading (5 deg) after 3.3 s, no overshoot (pass 1: 2.17 s, because the look itself had turned the ship). The hover-pivot rows of `steps` now run with `PFParkSpeed` 0 (the pivot itself is unchanged). Check `push` (follow-up, polish build -> latch): parked with the camera 120 deg off the bow, a 6 m/s push and a 70 deg/s knock: parked 0.5 -> 100 % of the 7 s with no key, the hull ends 119.92 -> 0.09 deg off the held heading (knock peak 24.6 deg); W then reaches the camera's yaw after 3.3 s |
| P4 | The gun lock is armed only while Fire is held or 6 s after the pilot's own broadside (`PFLockArmTime` 6 s, 0 = always). Follow-up F-A: the polish build never saw Fire held (`IA_AirshipFire` had no value binding, so in play only the 6 s counted); it now has one (`../CPP_NOTES.md` 14.12, F-A). The bench always armed the lock on Fire held, so it did not change | compete: RMB is the only clean way to look, but a rival held 55-150 deg off the bow swung the ship | Aim held 3 s on a rival 60 or 120 deg off the bow, no Fire: heading swing 26.9 -> 0 deg, 62 -> 0 m off the line. M12, the racing pass: identical (the bot fires on its first solution, before the lock would engage). The charge check now holds Fire while aiming (a pilot who wants to shoot); with the lock always armed that protocol gives the same solution times, so the rule costs nothing in a fight |
| P5 | `PFLockLeadTime` 0.45 -> 0.6 s | feel, newplayer (0.75), compete (feed-forward), PIE issue 7 (target 7.4 deg aft of the beam) | Root cause from the PIE frames: the lead already cancels the hull's lag (control yaw -0.48 deg off the hull's beam, the same in the bench). The rest is the spring arm's **position** lag, which the bench camera lacked: the harness bot aims the control rotation from a camera that trails the turn, so its line of sight passes 6.6 deg off the hull. A camera model fitted to the PIE frames (lag speeds 4 / 5 /s, 0.05 m mean error) reproduces PIE: -7.38 / -7.31 deg (PIE -7.39 / -7.32). A hand that keeps the crosshair (the lagged view) on the target gets -2.9 deg at 0.45 s, **-0.2 at 0.6 s**, +2.6 at 0.75 s (over-leads). The PIE bot will read about -4.7 at 0.6 s (final PIE: -4.72 / -4.71) |
| P6 | Overlay: crosshair 24 px, nose chevron 18 px, gap line 2 px amber with an ink outline (hidden while parked), LOCK tag 1.5 x; broadside heading strip +-180 deg around the bow at 1.5 px/deg with the guns' arcs, the aim ring, the heading-target diamond and the bow fixed at the centre | newplayer (legibility), feel (the +-60 deg strip around the view only showed two edge arrows) | HUD only |
| P7 | Hints: the boarding hint stays at least 8 s and until Aim has been held once (at most 45 s); "HOLD RMB / LB TO LOOK" under the crosshair while steering with the camera more than 50 deg off the nose for 0.3 s, until Aim has been held once this session | newplayer | HUD only |

Metrics that moved (`pointfly_metrics.json`, pass 1 -> polish): M11 sloppy 59.83 -> 59.33 s host and 59.1 -> 58.83 s at
100 ms (line 4.1 / 7.7 -> 3.4 / 6.9 m), precise 100 ms 60.2 -> 60.1 s, all 0 missed; M12 beam yaw (bench camera) precise
-2.6 -> +0.14, sloppy -6.18 -> -3.54, 100 ms -6.68 / -10.18 -> -4.03 / -7.55 deg; M12 sloppy 100 ms firing solution
100 -> 99.8 %; M9 measured exit kick 4.71 -> 4.84 m/s. M1-M8 and M10 are unchanged. The charge check (now with Fire held
while aiming): first solution 2.97 s with a turn, 2.7 s with a drift (pass 1, firing only on a solution: 4.0 / 2.33 s).

Watch: the human-like mouse course with glances (`mouse`; 5 course seeds, run in the polish session) moves within its one-gate
noise (always H1, the hairpin): without Aim 0.6 / 1.0 -> 1.0 / 1.0 gates (host / 100 ms), with Aim 0.6 / 1.2 -> 0.8 / 1.0;
the P2 gyro is what moves it. Glancing in the hairpin is still the cost of camera steering (risk 1).

Rejected:

| Idea | From | Why not |
|---|---|---|
| `PFLockLeadTime` 0.75 | feel, newplayer | Centres the harness bot (-2.1 deg), but over-leads a pilot who aims with the crosshair by 2.3-2.6 deg, and a bigger lead jumps the sent target further when the lock lets go |
| Yaw-rate feed-forward in `ComputeHeadingSteer` | compete | The PIE frames show the hull already on the sent target's beam (the lead does that job); a feed-forward would count it twice. The 7 deg is camera parallax, not loop lag |
| `PFDriftEndDeg` 15 -> 25 | newplayer | No gain: the M9 exit is a brake release, not the end angle (8.63 deg either way), and the 179 deg reversal stays 2.9-3.0 deg; with P2 both are 0.3 deg anyway |
| Sky Racer's tiered mini-turbo on the brake-drift | compete, newplayer | A new mechanic (charge, tiers, client agreement, HUD row) in a polish pass; P1 already removes the exploit. The best next step if Point & Fly needs more skill ceiling |
| "Classic keys" layout (A/D turn, Q/E sidestep) | compete | Nothing in the game can switch it on yet (no settings UI), and Classic itself stays one console command away |
| Sky Racer's forgiving collision preset | newplayer | It changes damage (`ImpactMinSpeed`, damage per m/s, cooldown), i.e. balance between schemes in a shared race, and no PIE run showed Point & Fly scrapes knocking the heading off; P2's stronger yaw stabiliser also resists spin kicks |
