# Airship controls: the Galleon scheme

Control scheme `Galleon` (`EAirshipControlScheme::Galleon = 1`, bench key `galleon`), one of the three iterations judged
against Classic (v1). Designed and tuned in the offline bench (`Docs/Airship/controls/sims/`) before anything was
built; every number marked "sim" comes from `sims/scheme_galleon.py` and the shared bench. **Status (2026-11-23):**
built and run in PIE pass 1 (17 of 17 runs, `PIE_RESULTS.md`), judged third of the four (`RESULTS.md`), and kept
switchable (`Aura.Airship.Scheme 1`); Point & Fly is the default. Changes made after this spec was written: "Review
changes" at the end; the code: `../CPP_NOTES.md` 14.
`../BASELINE.md` is the code reference this document builds on (its section numbers are quoted as "BASELINE 4b" and
so on). File shorthand as in BASELINE: `FC` = `AirshipFlightComponent`, `Pawn` = `AirshipPawn`, `Types.h`, `HUD`.

## 1. Concept: why it is fun

You are the captain, not the helmsman: you give orders and a 52 m, 40 t warship carries them out. W and S ring an
engine telegraph (FULL ASTERN, STOP, SLOW, HALF, FULL) and the ship holds that speed with your hands off the keys. That
frees you to look along the beam, line up a broadside and fire while she keeps her way. A and D swing her into a turn
with a dramatic 26 deg heel that comes in with the turn. Let go and she settles on her new heading; the
helmsman "meets her", so the bow does not wander. Brake plus helm throws the stern round in a slide, for a hairpin or
to bring a broadside onto a target ahead ("crossing the T"). Shift is FULL STEAM. Look out over the side and open
fire (or hold Aim) and the ship goes to broadside stations: the gun deck levels and the helm gives fine orders, so even
a clumsy player holds an enemy in the arc. Merely looking around never changes the handling (review change R1). The weight is readable everywhere: the telegraph's speed needle working up to the ordered notch, the slow
majestic camera, the heel, the 3 s brake. It is never sluggish, though. The bow answers as fast as Classic's, the camera
leans into a turn within 3 frames on any connection, and every order makes the rig, the thrusters and the HUD answer
in the same frame. The skill ceiling comes from choosing speeds for each section, timing the stern swing and its exit,
and fighting while manoeuvring.

## 2. Controls

| Action (IA) | Keyboard / mouse | Gamepad | Galleon |
|---|---|---|---|
| IA_AirshipThrottle | W / S | left stick up / down | Engine telegraph. A press steps one notch: FULL ASTERN, STOP, SLOW (14 m/s), HALF (28 m/s), FULL (full power, 48 m/s). Holding auto-steps (first repeat after 0.25 s, then every 0.15 s: STOP to FULL in 0.43 s). Auto-repeat never passes STOP; a fresh press does (STOP is a detent). Stick: past 0.5 = a press, back under 0.3 = released. |
| IA_AirshipSteer | A / D | left stick left / right (analog) | Helm. Turn rate 26 deg/s at rest, 44 at 15 m/s, 34 at 48 m/s; bank up to 26 deg. On release the turn is taken off firmly ("meet her"). |
| IA_AirshipBrake | X | B | Air brake while held (about 2.3 g peak), then the ordered speed resumes. With A / D above 6 m/s: the stern swing. |
| IA_AirshipBoost | Left Shift | A | FULL STEAM: full power plus boost while held (fuel 4.1 s from full), then back to the order. |
| IA_AirshipStrafe | Q / E | D-pad left / right | Sidle 10 m/s to port / starboard (to set the range for a broadside). |
| IA_AirshipLift | Space / Left Ctrl or C | RT / LT (analog) | Climb 10 m/s / sink 13 m/s; on release the ship stops within about 4 m and holds that height. |
| IA_AirshipLook | mouse | right stick | Ship-relative free look (the camera turns with the ship). More than 55 deg off the bow = beam watch: the view stays on the beam. Broadside stations come on with it only for 6 s after each own broadside (fire to go to stations). |
| IA_AirshipAim | RMB | LB | Tighter view (FOV -18) and broadside stations while held. |
| IA_AirshipFire | LMB | RB | The broadside on the side the camera faces (as Classic). |
| IA_AirshipZoom | wheel | D-pad up / down | Camera arm 50-140 m. |
| IA_AirshipExit | F | Y | Leave the helm (as Classic). |

No new input action, mapping or asset. All reinterpretation is C++.

## 3. Behaviour spec

Runs on: **P** = the pilot's machine, **S** = server, **A** = every machine. Units in code: cm, cm/s, cm/s², s, deg,
rad/s². All named values are tunables (section 5).

### 3.1 Telegraph (P, `GatherLocalInput`, after the IA values are read)

```
v = Axis(ThrottleAction)                                   // W +1, S -1, LS Y
bUp   = v >  GalleonOrderAxisPress || (bUpHeld   && v >  GalleonOrderAxisRelease)     // 0.5 / 0.3
bDown = v < -GalleonOrderAxisPress || (bDownHeld && v < -GalleonOrderAxisRelease)
for (Dir, bHeld, bWasHeld) in { (+1, bUp, bUpHeld), (-1, bDown, bDownHeld) }:
    if bHeld && !bWasHeld:                                  // a new press
        Step(Dir, bRepeat = false); NextRepeatTime = Now + GalleonOrderRepeatDelay (0.25); RepeatDir = Dir
    else if bHeld && RepeatDir == Dir && Now >= NextRepeatTime:
        Step(Dir, bRepeat = true);  NextRepeatTime = Now + GalleonOrderRepeatInterval (0.15)
bUpHeld = bUp; bDownHeld = bDown; if !bUp && !bDown: RepeatDir = 0

Step(Dir, bRepeat):
    N = clamp(GalleonNotch + Dir, -1, 3)
    if bRepeat && (GalleonNotch == STOP || N crosses STOP): return        // the STOP detent
    if N != GalleonNotch: GalleonNotch = N; OnGalleonOrderChanged(Dir)    // feedback, 7
Controls.Throttle = AirshipGalleon::NotchToThrottle(GalleonNotch)          // int8 -127, 0, 42, 85, 127
Controls.SetButton(Airship::Button_Stations, bGalleonStations)            // 3.8
```

`Now` = `GetWorld()->GetTimeSeconds()`. Notches: -1 FULL ASTERN, 0 STOP, 1 SLOW, 2 HALF, 3 FULL.

### 3.2 The order on the wire, neutral input and timeouts

* The order rides `FAirshipPilotInput::Throttle` as a code. Every machine decodes it the same way:
  `Notch = (AxisToFloat(Throttle) <= -0.5) ? -1 : RoundToInt(clamp(AxisToFloat(Throttle), 0, 1) * 3)`. It is a
  latched state, so a lost packet changes nothing, and `SameControls` already sends it at once when it changes.
* Neutral input (`FAirshipPilotInput()`, Throttle 0) is STOP: a ship with no pilot comes to rest and holds station.
* **Timeout (S, `SelectControls`)**: under Galleon, when the newest packet is older than `InputTimeout` but the ship
  still has a controller, use the last `ServerInput` with Steer, Lift and Strafe set to 0 and Boost and Brake
  cleared, **keeping Throttle** (the engine room keeps the last order). A network hiccup then costs only the helm
  for its duration, not a 0.8 g slow-down. Still neutral (STOP) with no controller.
* `DebugSetInput(Throttle, ...)` and `Aura.Airship.Input` pass the code straight through: 1 = FULL, 0.67 = HALF,
  0.33 = SLOW, 0 = STOP, -1 = FULL ASTERN.

### 3.3 Speed loop (A, `ShapeControls`, Galleon branch)

The loop lives in the shaping, so every machine computes the same throttle from (order, forward speed) and the
cosmetics follow it everywhere.

```
Notch = DecodeNotch(Controls.Throttle)
if Notch != LastNotch: GalleonOrderPulse01 = 1; LastNotch = Notch               // cosmetic ring, 7
if Boost && !bPrevBoostButton: GalleonBoostPulse01 = 1; bPrevBoostButton = Boost
bSwing = Brake && |RawSteer| > DriftSteerThreshold (0.3) && ForwardSpeed > DriftMinSpeed (600)   // = bDrifting
if Boost (gated):        ThrottleTarget = 1                                     // FULL STEAM
else if Notch == FULL:   ThrottleTarget = 1                                     // open loop, as Classic W
else:
    Vord = { ASTERN: -GalleonOrderAsternSpeed, STOP: 0, SLOW: GalleonOrderSlowSpeed, HALF: GalleonOrderHalfSpeed }
    ThrottleTarget = clamp(HoldThrottle(Vord) + GalleonOrderSpeedGain * (Vord - ForwardSpeed), -1, 1)
if Brake && !bSwing:     ThrottleTarget = -BrakeReverseThrottle * clamp(ForwardSpeed / BrakeFadeSpeed, 0, 1)   // base fix 4c
ShThrottle = ApproachUpDown(ShThrottle, ThrottleTarget, Dt, ThrottleTauUp, ThrottleTauDown)

HoldThrottle(v) = v >= 0 ? clamp((DragC1 v + DragC2 v|v|) / (AFan    * max(1e-3, 1 - (v / VTop)^ThrustFadeExponent)), 0, 1)
                         : clamp((DragC1 v + DragC2 v|v|) / (AFanRev * max(1e-3, 1 - (|v| / VTopRev)^2)),             -1, 0)
SteerTau' = (SteerTauRelease > 0 && |RawSteer| < |ShSteer|) ? SteerTauRelease : SteerTau      // meet her, 3.5
LiftTau'  = base fix 4b (LiftTauRelease)
GalleonOrderPulse01 -= Dt / GalleonOrderPulseTime; GalleonBoostPulse01 likewise (floor 0)
bShStations = Controls.HasButton(Airship::Button_Stations)
```

In `ApplyForces`, a negative throttle while moving forward backs the engines at `GalleonOrderReverseAccel`. Plain
braking keeps Classic's AFan, and moving astern keeps AFanRev:
`ARev = (bShBrake && !bDrifting) ? AFan : (ActiveScheme == Galleon && Vf > 0 ? GalleonOrderReverseAccel : AFanRev)`.
The `ActiveScheme == Galleon` gate is required (review R5): without it Classic's S key (gentle 0.5 g reverse while
still moving forward) would change.

Sim results (`galleon_checks.json`):

| Step | Settles at | 90 % after | Overshoot |
|---|---|---|---|
| STOP to SLOW / HALF / FULL | 14.0 / 28.0 / 47.8 m/s | 1.37 / 2.20 / 3.93 s | 0.33 / 0.35 / 0 m/s |
| FULL to HALF, HALF to SLOW, SLOW to STOP | 28.0 / 14.0 / 0 m/s | 2.27 / 2.07 / 2.27 s | 0.05 m/s or less |
| FULL to STOP | 0 (station keeping) | half speed 2.5 s, at rest 6.2 s, 123 m | - |
| STOP to FULL ASTERN | -12.0 m/s | - | - |

### 3.4 Brake (S)

As Classic plus two things. The air brake is capped (`ABrake = clamp(-Kbrake * Vf * (bDrifting ? DriftBrakeScale : 1),
±BrakeMaxAccel)`, `BrakeMaxAccel` 1400 cm/s²). The reverse throttle fades below 10 m/s (base fix 4c). From FULL:
3.07 s and 57 m to a stop, 2.32 g peak (Classic 2.17 s, 38.6 m, 4.31 g). When X is released, the order resumes: brake
into a hairpin, let go, and she works back up to FULL by herself.

### 3.5 Helm (A shaping, S forces)

* The yaw-rate command is as Classic (`Steer * Rmax(|Vf|)` with the Galleon table, `Kr` 3, `AlphaYawMax` 1 rad/s²).
  The bow answers as quickly as Classic's: t63 0.37 s, t90 0.87 s at FULL (Classic 0.50 / 0.90).
* **Meet her** (new, S): while the turn is being taken off (`|YawRateCmd| < |YawRate|`, not drifting), the yaw loop
  uses `KrSteady` (4 /s) and `max(AlphaYawMax, AlphaYawMaxSteady)` (1.2 rad/s²). The helm returns with
  `SteerTauRelease` (0.12 s, shaping, every machine). The heading carry after a full-helm release is 8.6 deg at FULL
  and 11.7 deg at HALF (Classic 13.5 deg at FULL), and she is steady in 1.0 s (Classic 1.2 s).
* **Gunnery helm** (S): with broadside stations on and no swing, `Rmax *= GunDeckYawScale` (0.5; bench name GalleonStationsHelmScale). Fine
  orders hold a target in the arc (3.8).

### 3.6 Bank and level grip (S)

```
BankMax = bDrifting ? BankMaxDriftDeg (28) : Lerp(BankMaxDeg (26), BankMaxBoostDeg (18), Boost)
BankDeg = BankMax * Steer * clamp(Vf / BankFullSpeed (2400), BankMinFraction, 1) + StrafeBankDeg (3) * Strafe
if bShGunDeck (= stations bit under Galleon): BankDeg *= GunDeckBankScale (0.2; bench GalleonStationsBankScale)
GripDir = bLevelGripForce ? (Right.X, Right.Y, 0).GetSafeNormal() : Right                 // new shared switch
ACom = GripDir * AGrip + Right * WindLat + Fwd * (ADrag + ABrake + ARedirect + AKeepF) (+ base fix 4b AVert on Z)
```

The roll loop is stiffer (`KpRoll` 18, `KdRoll` 5.4, `GyroTiltMax` 1.5), so the heel arrives with the turn: 50 % of
the bank after 0.53 s, 90 % after 0.8 s (Classic 0.73 / 1.87 s), at most 1 deg of overshoot. The level grip removes the
turn sink: 0.12 m lost in 8 s of full helm at FULL (Classic 5.15 m). The lateral loop itself stays in the hull frame
(the banked collective's inward push still helps the turn: slip 13 deg at 8 s against Classic's 19.6). **The roll
gains need base fix 4a-1** (`bHullAxisInertia`): with today's inertia mix-up they would act 5.7 times stiffer.

### 3.7 Stern swing (A shaping, S forces)

The swing is the Classic drift path with Galleon values, plus two new tunables for its yaw loop:

| Part | Galleon |
|---|---|
| Enters | brake held, \|raw helm\| > `DriftSteerThreshold` 0.3, forward speed > `DriftMinSpeed` 6 m/s (the existing `bDrifting`) |
| Yaw | `YawRateDrift` 54 deg/s; the loop uses `DriftKr` 4 /s and `DriftAlphaYawMax` 1.5 rad/s² (new; 0 = use `Kr` / `AlphaYawMax`) |
| Slide | `DriftKlat` 1.6 /s, `DriftALatMaxG` 1.6 g, `DriftEta` 0.15; the stern slides out, the velocity follows at about half the yaw rate |
| Speed | `DriftBrakeScale` 0.3 of the air brake (it bleeds); the throttle keeps the order (a drift keeps the throttle, as in Classic) |
| Heel | `BankMaxDriftDeg` 28 (x 0.2 at stations: the gun deck stays level while you swing and fire) |
| Exit | releasing the brake restores full grip; the slide carves back into forward speed (redirect). After at least `DriftBoostMinTime` 0.6 s: a `DriftBoostDV` 2.5 m/s surge (existing drift-kick code, `NoteFlightKick`) |
| Look | wheel and rudder thrown hard over: cosmetic `Steer = clamp(ShSteer * DriftCosmeticSteerScale (1.3), ±1.3)` (the rudder clamps at its ±30 deg rig limit; FanYawDeg is unchanged, it stays equal to the forces) |
| Stations | the gunnery helm scale does not apply: the swing keeps full authority |

What it buys (sim, from FULL at 47.8 m/s; U-turn = until the course over ground has turned 180 deg):

| Manoeuvre | Time | Diameter | Speed after |
|---|---|---|---|
| U-turn, helm only (Classic: 6.1 s, 184 m) | 6.07 s | 188 m | 51.5 m/s |
| U-turn, 1.5 s swing then helm (Classic drift 1.5 s: 5.83 s, 158 m) | 5.20 s | 124 m | 50.0 m/s |
| U-turn, 2.5 s swing then helm | 4.37 s | 70 m | 41.0 m/s |
| U-turn at HALF: helm / 2.5 s swing | 5.17 / 4.40 s | 91 / 56 m | 30.9 / 31.0 m/s |
| 2 s swing: heading / course change, slip max | +86 / +45 deg, 40 deg | - | 71 % kept, back to 47.6 m/s 3 s after the exit |

The longer the swing, the tighter the turn and the more speed it costs. A 2 s swing turns the hull 86 deg, so it
brings a target that was dead ahead onto the broadside.

### 3.8 Broadside stations (P flag, S effect)

```
// P, start of GatherLocalInput (review R2: the bit goes out in the same frame; UpdateCamera runs after it)
CamOffsetYaw = NormalizeAxis(Control.Yaw - GalleonLastHullYaw - GalleonLastLookAhead)   // includes this frame's mouse
bBeamWatch = !bBeamWatch ? |CamOffsetYaw| > GalleonBeamWatchEnterDeg (55) : |CamOffsetYaw| >= GalleonBeamWatchExitDeg (40)
bRecentBroadside = GalleonStationsFireHoldTime <= 0 || Now - LastOwnBroadsideTime < GalleonStationsFireHoldTime (6 s)
bGalleonStations = AimHeld || (bBeamWatch && bRecentBroadside)          // sent as Buttons bit 4 (review R1)
// S, ApplyForces: bank x GunDeckBankScale (0.2); Rmax x GunDeckYawScale (0.5) unless drifting
```

`LastOwnBroadsideTime` is stamped in `HandleCannonsFired` on the pilot's machine (`IsLocallyControlled()`: the host's
real shot and a client's predicted one). Aim held gives stations at once; beam watch alone only moves the camera.

At full helm on stations: 5.6 deg of bank and 19.5 deg/s of turn at HALF. This is the reason the broadside numbers
(M12) jump for the sloppy bot: the deck stays level and an on/off helm can no longer swing the beam out of the ±20 deg
arc. The M12 bot fires whenever it has a solution, so stations come on with the first broadside and M12 is unchanged
by R1 (sloppy 100 ms: 100 % in arc, both cannons 86 % instead of 90 %). The `ComputeAimSide` / fire logic is unchanged.

Why R1: as designed, a glance of more than 55 deg off the bow halved the helm. With beam glances (60-90 deg for 1-2 s
every 6-10 s, no firing) on the gate course, even the precise bot missed 1-2 gates; with R1 it misses none
(`galleon_checks.json` `beam_glances`, 4 seeds):

| Gates missed, mean (4 seeds) | precise 0 ms | precise 100 ms | sloppy 0 ms | sloppy 100 ms |
|---|---|---|---|---|
| As designed (beam watch = stations) | 2.0 | 1.0 | 2.25 | 0.75 |
| Review rule (stations need an own broadside) | 0 | 0 | 0.5 | 1.25 |

### 3.9 Sidle (S)

As Classic's strafe with `StrafeSpeed` 10 m/s, `StrafeTau` 0.25 s, `StrafeBankDeg` 3 (x 0.2 at stations): t90 0.97 s.

### 3.10 Full steam (A / S)

Boost as Classic (gate, fuel, kick) with `BoostKickDV` 5.5 m/s and `BoostDrainRate` 22 /s: 47.8 to 88.2 m/s, 4.1 s
from full fuel. While boosting the throttle target is 1 whatever the order. When it ends the order resumes (from
FULL STEAM back to HALF the engines back down at 0.8 g). Feedback in 7.

### 3.11 Vertical (S)

Classic's model with base fixes 4b and 4c. `ClimbRate` 10 m/s and `DescendRate` 13 m/s (weightier than Classic's
12 / 15). These are also the rates at which the stopping-distance capture keeps the stop short: after releasing a
full climb the ship stops 4.0 m higher and holds there, with no bob back (Classic 12.1 m and settles 11.5 m high);
|vz| is 0.2 m/s 1 s after the release (Classic 5.84).

### 3.12 Resets and switching

* **Board** (a new local pilot; `UpdateLocalMappingContext` adds the IMC): `GalleonNotch` = STOP. Key edges, repeat
  timer, camera offset, beam watch, look-ahead, shake and FOV kicks are cleared.
* **Scheme switch** (`ApplyControlScheme` on the host, `OnRep_ControlScheme` on a client pilot): the same clearing, but
  `GalleonNotch` = `NotchForSpeed(ForwardSpeed)` so a switch at cruise keeps cruising: FULL at 38 m/s or more, HALF at
  21 m/s or more, SLOW at 7 m/s or more, STOP above -3 m/s, else FULL ASTERN (thresholds: midway between notch speeds).
* **Exit / death**: as board (STOP). The server's neutral input is STOP anyway.
* **Flight component** (A): `LastNotch`, both pulses and the swing state reset in `ResetSchemeState`, which runs from
  `ResetInput` / `SetFlightEnabled` (server), from `OnRep_PilotCharacter` (every machine, review R6: `PossessedBy` /
  `UnPossessed` only run on the server) and on every scheme apply. `DriftTime` resets on a scheme apply only.
* **Camera component**: its relative rotation and location (shake, roll) go back to zero on a scheme apply, so nothing
  of Galleon's camera roll is left in Classic (`IMPLEMENTATION_PLAN.md` 1.12).

## 4. Base fixes (all of BASELINE 4f, values chosen for Galleon)

| # | Tunable | Galleon | Why |
|---|---|---|---|
| 4a-1 | `bHullAxisInertia` (bench `ctrl_inertia='hull'`) | true | The stiff roll loop and the level-deck stations depend on the real roll inertia |
| 4a-2 | `bFanTorqueFeedForward` | true | The fans' pitching moment no longer dips the nose |
| 4a-3 | `PitchPerG` / `PitchMinDeg` / `PitchMaxDeg` / `BoostPitchDeg` | 4 / -4 / 3 / 1.5 | Nose -3.95 deg on FULL (Classic -16.6), -5.2 on boost, +3.0 on the brake: the horizon and the targets stay in view |
| 4b | `VertBrakeAccel` / `HoldBrakeAccel` / `LiftTauRelease` | 784 / 1470 / 0.08 | Stops where you let go (3.11) |
| 4c | `bBrakeHoldLead` / `BrakeFadeSpeed` | true / 1000 | No climb after a brake press mid-climb; no back-up after a stop (-0.1 m/s) |
| 4d | `StationKeepGain` / `Speed` / `AccelMax` | 1.0 / 300 / 150 | STOP holds station; deck walking no longer pushes the ship (BASELINE: 2.3 m to 0.27 m) |
| 4e | `ImpactEpisodeAccelUp` / `ImpactMaxReboundSpeed` (pawn) | 2050 / 120 | 2050 cm/s² is at least the largest upward flight acceleration: (1.9 - 1) g + 0.35 g cushion + 784 = 2009 (BASELINE 4e rule). Not modelled in the bench. C++ default of `ImpactEpisodeAccelUp` = 0, meaning "same as ImpactEpisodeAccel" (v1) |

All of them are included. Galleon has no reason to keep a v1 behaviour, and two of its features (stiff bank, STOP
holding station) need them.

## 5. Parameters (Classic value, Galleon value)

Code units. A Galleon preset sets every row below; Classic's preset restores the Classic column (v1). Properties not
listed keep their v1 value in Galleon.

### 5.1 Flight component, existing properties

| Property | Classic | Galleon | Notes |
|---|---|---|---|
| ThrottleTauUp / ThrottleTauDown | 0.30 / 0.45 s | 0.15 / 0.25 s | the fans answer the telegraph at once; the speed loop does the smoothing |
| ClimbRate / DescendRate | 1200 / 1500 cm/s | 1000 / 1300 | 3.11 |
| PitchPerG / PitchMinDeg / PitchMaxDeg / BoostPitchDeg | 8 / -8 / 6 / 3 | 4 / -4 / 3 / 1.5 | base fix 4a-3 |
| YawRateAtRest / AtMid / AtTop / Boost | 30 / 45 / 35 / 25 deg/s | 26 / 44 / 34 / 24 | (YawRateMidSpeed 1500, YawRateTopSpeed 4800 unchanged) |
| BankMaxDeg / BankMaxBoostDeg / BankFullSpeed / StrafeBankDeg | 18 / 12 deg / 2000 cm/s / 6 deg | 26 / 18 / 2400 / 3 | |
| KpRoll / KdRoll / GyroTiltMax | 6.25 / 4.5 / 0.8 rad/s² | 18 / 5.4 / 1.5 | needs base fix 4a-1 |
| StrafeSpeed / StrafeTau | 1200 cm/s / 0.20 s | 1000 / 0.25 | |
| BoostKickDV / BoostDrainRate | 400 cm/s / 25 /s | 550 / 22 | |
| DriftMinSpeed / YawRateDrift | 800 cm/s / 50 deg/s | 600 / 54 | the swing (3.7) |
| DriftKlat / DriftALatMaxG / DriftEta / DriftBrakeScale | 1.2 / 1.2 g / 0.4 / 0 | 1.6 / 1.6 / 0.15 / 0.3 | |
| BankMaxDriftDeg / DriftBoostMinTime / DriftBoostDV | 22 deg / 1.2 s / 600 cm/s | 28 / 0.6 / 250 | |
| SteerTau, Kr, AlphaYawMax, DriftSteerThreshold, BankMinFraction | 0.15, 3.0, 1.0, 0.3, 0.25 | unchanged | listed because the Galleon preset writes them |

### 5.2 Flight component, new properties

Shared ones are generic and off in v1. Galleon ones are only read while `ActiveScheme == Galleon`, so their C++
defaults are simply the Galleon values.

| Property (category) | Classic | Galleon | Meaning |
|---|---|---|---|
| bHullAxisInertia (Airship\|BaseFix) | false | true | base fix 4a-1 (BASELINE gives the code) |
| bFanTorqueFeedForward (BaseFix) | false | true | 4a-2 |
| VertBrakeAccel / HoldBrakeAccel (BaseFix) | 0 / 0 cm/s² | 784 / 1470 | 4b |
| LiftTauRelease (BaseFix) | 0 s | 0.08 | 4b |
| bBrakeHoldLead / BrakeFadeSpeed (BaseFix) | false / 0 cm/s | true / 1000 | 4c |
| StationKeepGain / StationKeepSpeed / StationKeepAccelMax (BaseFix) | 0 /s / 300 / 150 | 1.0 / 300 / 150 | 4d |
| bLevelGripForce (Airship\|Lateral) | false | true | grip / sidle force along the level right axis (3.6); shared with Sky Racer, which also sets `bLevelGripAlongHeading` |
| BrakeMaxAccel (Airship\|Forward) | 0 cm/s² (no cap) | 1400 | air brake cap (3.4); shared with Sky Racer and Point & Fly (1470) |
| GunDeckBankScale / GunDeckYawScale (Airship\|GunDeck) | 1 / 1 | 0.2 / 0.5 | review R3: the shared names of GalleonStationsBankScale / GalleonStationsHelmScale (the bench keeps the old names) |
| SteerTauRelease (Airship\|Shaping) | 0 s (= SteerTau) | 0.12 | helm return time constant |
| KrSteady / AlphaYawMaxSteady (Airship\|Yaw) | 0 (= Kr) / 0 | 4.0 /s / 1.2 rad/s² | meet her (3.5) |
| DriftKr / DriftAlphaYawMax (Airship\|Lateral) | 0 (= Kr) / 0 (= AlphaYawMax) | 4.0 /s / 1.5 rad/s² | yaw loop while drifting |
| DriftCosmeticSteerScale (Airship\|Cosmetic) | 1.0 | 1.3 | wheel / rudder while drifting |
| GalleonOrderSlowSpeed / GalleonOrderHalfSpeed / GalleonOrderAsternSpeed (Airship\|Galleon) | - | 1400 / 2800 / 1200 cm/s | notch speeds (FULL = throttle 1) |
| GalleonOrderSpeedGain (Galleon) | - | 0.001 per cm/s | speed loop P gain (throttle per cm/s of error) |
| GalleonOrderReverseAccel (Galleon) | - | 800 cm/s² | engines backing to slow to the order (moving forward) |
| GalleonStationsBankScale / GalleonStationsHelmScale (Galleon) | - | 0.2 / 0.5 | broadside stations; C++: `GunDeckBankScale` / `GunDeckYawScale` (above) |
| GalleonOrderPulse / GalleonOrderPulseTime (Galleon) | - | 0.35 / 0.45 s | thruster pulse on an order change or boost start |
| ActiveScheme (not a UPROPERTY) | Classic | Galleon | set by the pawn when a scheme is applied, on every machine |

### 5.3 Pawn, existing properties (and CameraBoom)

| Property | Classic | Galleon |
|---|---|---|
| CameraArmLength / CameraArmMin / CameraArmMax | 6500 / 4000 / 12000 cm | 8000 / 5000 / 14000 |
| CameraBoostArmExtra | 1000 cm | 1400 |
| BaseFOV / BoostFOVExtra / AimFOVOffset | 85 / 12 / -15 deg | 80 / 14 / -18 (SpeedFOVExtra 10 unchanged) |
| CameraPitchMin / CameraPitchMax / CameraDefaultPitch | -60 / 25 / -12 deg | -65 / 20 / -16 |
| RecenterDelay / RecenterSpeed | 1.5 s / 2 /s | 2.0 / 1.2 (RecenterMinSpeed 800 unchanged) |
| ImpactMaxReboundSpeed | 250 cm/s | 120 (base fix 4e) |
| CameraBoom->TargetOffset.Z | 900 cm | 1200 |
| CameraBoom->CameraLagSpeed / CameraLagMaxDistance | 5 /s / 2500 cm | 3.5 / 3000 |
| CameraBoom->CameraRotationLagSpeed | 7 /s | 6 |

### 5.4 Pawn, new properties (category Airship|Galleon unless noted)

| Property | Value | Meaning |
|---|---|---|
| ImpactEpisodeAccelUp (Airship\|Impact) | Classic 0 (= ImpactEpisodeAccel, 2500), Galleon 2050 cm/s² | base fix 4e |
| GalleonOrderAxisPress / GalleonOrderAxisRelease | 0.5 / 0.3 | telegraph key / stick thresholds |
| GalleonOrderRepeatDelay / GalleonOrderRepeatInterval | 0.25 / 0.15 s | auto-step |
| GalleonBeamWatchEnterDeg / GalleonBeamWatchExitDeg | 55 / 40 deg | beam watch hysteresis |
| GalleonStationsFireHoldTime (new, review R1) | 6 s | beam watch gives stations only this long after an own broadside (0 = always, the original design) |
| GalleonLookAheadDeg / GalleonLookAheadTau | 10 deg / 0.12 s | camera yaw into the turn per unit helm |

Camera roll, shake, FOV kicks and rumble use the shared feedback properties of `IMPLEMENTATION_PLAN.md` 1.10 (review
R4: one implementation for all three schemes). Galleon's values, with the spec's original names:

| Shared property | Galleon | Was |
|---|---|---|
| CameraRollPerSteerDeg / CameraRollPerBank / CameraRollMaxDeg / CameraRollInterpSpeed | 6.5 deg (= 0.25 x BankMaxDeg 26) / 0 / 6 deg / 8 /s | GalleonCameraRollPerBankDeg 0.25, GalleonCameraRollMaxDeg 6, GalleonCameraRollInterpSpeed 8 |
| ShakeDecay / ShakeRotDeg / ShakeLocCm / ShakeFrequency | 1.8 /s / 1.0 deg / 20 cm / 8 Hz | GalleonShake* |
| FeedbackOwnBroadside (Trauma, FOVKickDeg, Rumble, RumbleTime) | 0.35, -3, 0.6, 0.25 s | GalleonShakeFire, GalleonFOVKickFire |
| FeedbackBoostStart | 0.30, +6, 0.4, 0.4 s | GalleonShakeBoost, GalleonFOVKickBoost |
| FeedbackDriftKick (the swing's exit surge) | 0.25, +4, 0.5, 0.2 s | GalleonShakeSwingExit, GalleonFOVKickSwingExit |
| FeedbackOrderChange | 0.06, 1.5 (sign = order direction), 0.25, 0.08 s | GalleonShakeOrder, GalleonFOVKickOrder |
| ShakeHitPerMS / ShakeHitMax / RumbleHitPerMS | 0.06 / 1.0 / 0.06 (per m/s above ImpactMinSpeed) | GalleonShakeHitPerMS |
| DriftRumbleBase / DriftRumblePerCharge | 0.2 / 0 (while swinging) | section 7 |
| FOVKickDecay / FOVMaxDeg / RumbleScale | 3 /s / 0 (= 170) / 1.0 | GalleonFOVKickDecay, GalleonRumbleScale |

The anim instance and the rig contract are unchanged: wheel unbounded, rudder clamped at ±30 by `RudderMaxDeg`,
thrust 0..1.5.

## 6. Camera (P)

Higher, farther and slower: an 80 m arm at -16 deg puts the camera about 77 m behind and 34 m above the hull origin. The
look-at point is 12 m up, FOV 80 to 90 deg with speed. The view is about 134 m wide at the ship, which fills 39 % of it
(Classic 44 %). Position lag 3.5 /s trails 14 m at 48 m/s and 25 m at the boost peak (cap 30 m); rotation lag 6 /s.

```
// UpdateCamera, Galleon branch (P), every frame after UpdateFlight
HullYaw = GetActorRotation().Yaw                           // the hull as this machine sees it
if bPendingCameraReset || !bGalleonCamInit: Offset = 0; LookAhead = 0; Control = (CameraDefaultPitch, HullYaw, 0)
else: Offset = NormalizeAxis(Control.Yaw - LastHullYaw - LastLookAhead)        // includes this frame's mouse input
// bBeamWatch: already updated from the same Offset at the start of GatherLocalInput this frame (3.8)
if !bBeamWatch && !Aiming && Now - LastLookInputTime > RecenterDelay && C.ForwardSpeed > RecenterMinSpeed:
    a = 1 - exp(-RecenterSpeed * Dt); Offset -= Offset * a; Control.Pitch += (CameraDefaultPitch - Control.Pitch) * a
LookAheadTarget = (bBeamWatch || Aiming) ? 0 : GalleonLookAheadDeg * C.Steer       // the pilot's own shaped helm
LookAhead = Approach(LookAhead, LookAheadTarget, Dt, GalleonLookAheadTau)
Control.Yaw = HullYaw + Offset + LookAhead; clamp pitch; Roll 0; SetControlRotation
LastHullYaw = HullYaw; LastLookAhead = LookAhead
// roll, shake, FOV kick, rumble: the shared feedback code (IMPLEMENTATION_PLAN.md 1.10), with Galleon's values:
Roll = clamp(CameraRollPerSteerDeg (6.5) * C.Steer * (bGunDeck ? GunDeckBankScale : 1) + CameraRollPerBank (0) * HullRoll, ±CameraRollMaxDeg)
CamRoll = FInterpTo(CamRoll, Roll, Dt, CameraRollInterpSpeed (8))
Camera->SetRelativeRotation(FRotator(ShakePitch, ShakeYaw, CamRoll + ShakeRoll)); Camera->SetRelativeLocation(ShakeLoc)
Arm: ZoomTarget + CameraBoostArmExtra * C.Boost (as Classic); FOV: SmoothedFOV (Classic's formula, interpolated) + FOVKick (7)
```

* The camera is **ship-relative**: it turns with the ship, so an enemy kept on the port beam stays on screen while
  you circle it. In Classic the view stays fixed in the world and recentres after 1.5 s.
* **Beam watch** (offset beyond 55 deg) never recentres. That is "watching the broadside", and it switches broadside
  stations on. Looking back within 40 deg of the bow ends it, and the slow recentre (2 s, 1.2 /s) takes over.
* **Look-ahead and roll** come from the pilot's own shaped helm, so they move at once on every connection. Sim: the
  camera yaw moves 0.5 deg in 3 frames and 5 deg in 9-11 frames after A/D, at 0 and at 100 ms each way. Classic's
  camera needs 13 / 19 frames and 27 / 33, because it only follows the hull. The hull's own turn shows on a client's
  screen after 9 frames in both schemes. The roll goes on the camera component (no arm lag) and rolls with the hull's
  sign (+ = right side down).
* Harness note: a control rotation set from Python is carried with the hull. It is not pulled back unless it is
  within 55 deg of the bow at more than 8 m/s (then after 2 s). Setting it every frame works as in Classic, at most
  one frame of hull turn off.

## 7. Feedback (no new assets)

| Event | Machine | Response |
|---|---|---|
| Telegraph step | A (cosmetics from the controls) | Pods' Niagara `Thrust` (and the anim's petal flare) pulse +0.35 decaying over 0.45 s; the fans' spin and the nozzles' lean follow the faster throttle filter (0.15 s) |
| | P | HUD tag rings (8); camera trauma 0.06; FOV ±1.5 deg kick (up / down); rumble 0.25 for 0.08 s |
| A / D | P | Wheel, rudder and fan housings in frame 0; camera look-ahead and roll within 3 frames; HUD helm needle |
| | S (seen by all) | 26 deg heel, half of it in 0.53 s |
| Stern swing | A | Wheel and rudder hard over (x 1.3, the rudder to its 30 deg stop); 28 deg heel |
| | P | Rumble 0.2 while swinging; on the exit surge: trauma 0.25, FOV +4 deg, rumble 0.5 for 0.2 s |
| FULL STEAM start | A | Pods `Thrust` pulse +0.35, `Boost` param as Classic |
| | P | Trauma 0.30, FOV +6 deg kick (on top of +14 boost FOV, arm +14 m), rumble 0.4 for 0.4 s |
| Own broadside fired | P (`HandleCannonsFired` on the pilot's own ship) | Trauma 0.35, FOV -3 deg punch, rumble 0.6 for 0.25 s (the hull's recoil roll is physical, as Classic) |
| Hull hit | P (`OnHullHit` fires on every machine) | Trauma `0.06 * (impact speed in m/s - 4)`, clamped 0..1; rumble likewise |
| Broadside stations on / off | P / S | HUD STATIONS tag; the deck visibly levels (bank x 0.2). Stations need Aim or an own broadside in the last 6 s (R1) |

Shake, FOV kicks and rumble are the shared feedback code of `IMPLEMENTATION_PLAN.md` 1.10 (review R4), with the
values of section 5.4: `Trauma = min(1, Trauma + amount)`, then `Trauma -= ShakeDecay * Dt`; the offset is
`Trauma² * (ShakeRotDeg * PerlinNoise1D(t * ShakeFrequency + seed_i) per axis, ShakeLocCm * PerlinNoise1D(...) per
axis)`; FOV kick `Kick += amount; Kick *= exp(-FOVKickDecay * Dt)`, added after the FOV interpolation so the punch is
not smoothed away; rumble through the native `APlayerController::PlayDynamicForceFeedback(Intensity * RumbleScale,
Duration, bLarge, !bLarge, bLarge, !bLarge)` overload (PlayerController.h:1315; the 8-argument latent one is for
Blueprints).

## 8. HUD (Slate, `UAirshipHUDWidget`, Galleon only)

The panel grows from 292 x 136 to 292 x 214 (`GalleonPanelSize`, new UPROPERTY). Two rows are added above the hull
bar and one helm row above the cannons; same paper / ink style, boxes, lines and the engine font only.

1. **Telegraph** (y 12): five notch boxes across the width, each 50 x 18 with 4 px gaps: `ASTERN STOP SLOW HALF FULL`.
   The ordered notch is an ink tag with paper text, the others ink outlines. While boosting, FULL is drawn in
   BoostColor with the label `STEAM`. On an order change the new tag blinks (ink / BoostColor at 10 Hz) for 0.4 s:
   the telegraph "ring".
2. **Speed rule** (y 36): a track 268 x 10 from -12 to 52 m/s with ink ticks at the notch speeds (-12, 0, 14, 28, 48).
   A ReloadColor fill runs from 0 to the forward speed, and a hollow ink triangle above the track marks the ordered
   speed (FULL: 48, STEAM: the boost peak 88 drawn at the right end). The gap between the fill and the triangle is the
   ship's momentum, working up to the order.
3. The existing hull / boost / speed / ALT rows (shifted down 50 px).
4. **Helm** (above the cannons): a 120 px centred bar with a needle at the shaped helm (`Telemetry.Steer`), the turn
   rate as text ("12 deg/s"), and tags `SWING` (while `bDrifting`) and `STATIONS` (the pilot's flag).
5. **Cannons**: as Classic. The facing side's tag gets a ReloadColor outline while the aim point is inside that
   side's arc (`AAirshipPawn::IsAimInCannonArc(Side, AimPoint)`, the helper shared with Point & Fly, review R3), and
   shows `FIRE` in HullColor instead of `READY` when it is also reloaded.

Values read in `RefreshValues`: `Ship->GetGalleonNotch()`, `Ship->IsGalleonStations()`,
`Ship->IsAimInCannonArc(AimSide, Ship->GetLocalAimPoint())` (pawn getters, pilot-side state),
`Flight->GalleonOrderSlowSpeed` / `GalleonOrderHalfSpeed` / `GalleonOrderAsternSpeed`, `Telemetry.ForwardSpeedMS`,
`Telemetry.Steer`, `Telemetry.YawRateDegS`, `Telemetry.bDrifting`, `Telemetry.Boost`. The widget reads the ship's scheme
in every `RefreshValues` (not only in `SetAirship`), and the pawn re-applies the viewport slot size with
`UGameViewportSubsystem::SetWidgetSlot` on a scheme switch (`IMPLEMENTATION_PLAN.md` 1.11), so the panel grows and
shrinks without re-creating the widget.

## 9. Multiplayer

| What | Where it runs | Latency effect for a client pilot (100 ms each way) |
|---|---|---|
| Telegraph, notch, HUD ring, shake, FOV kicks, rumble, camera look-ahead and roll | P | none: same frame / within 3 frames |
| Order on the wire (Throttle code), stations (Buttons bit 4) | P to S, latched states | the server sees them 0.17-0.2 s later; lost packets cost nothing |
| Speed loop, thruster pulse, wheel / rudder / fans, swing cosmetics | A (from the controls each machine has) | the client's own cosmetics answer at once; observers see them via RepInput |
| Forces: speed loop thrust, meet her, bank, stations scales, swing, level grip, base fixes | S | the hull answers a round trip late, as Classic (M10: 9 frames on the client's screen) |

* **Why Galleon is robust under lag.** Speed is held by the server and changes slowly anyway, so the latency is
  invisible on the throttle. Broadside stations remove the biggest lag problem of Classic combat: the on/off helm
  swinging the beam out of the arc. Meet her shortens the heading carry the client must anticipate (8.6 deg against
  13.5). The camera answers locally. Sim evidence: the sloppy bot at 100 ms misses 1 gate (12-seed mean 1.25) against
  Classic's 6 (mean 5.33), and keeps a broadside target in arc 100 % of the time against 37 %.
* **Scheme switch while flying**: the client re-initialises its notch from its own view of the speed (3.12). For the
  half round trip before `OnRep_ControlScheme` arrives, the server reads Classic throttle values as order codes. Both
  mean "this much forward", so no lurch beyond one notch.
* **Timeout**: the order is kept on a stall (3.2), so a brief loss doesn't stop the ship.
* **Bandwidth**: no new RPC field; one Buttons bit.

## 10. Predicted metrics (sim) against Classic

`sims/galleon_metrics.json` (fixed keys M1-M12, 2026-11-23) and `sims/galleon_checks.json`. Classic from
`sims/classic_metrics.json`. Bot gains: `course.py galleon --tune` (started from the bench defaults) returned exactly
Classic's gains, so both schemes are flown by identical bots.

| Metric | Classic | Galleon | Band (bench) | Note |
|---|---|---|---|---|
| M1 time to 80 % of top | 3.33 s | 3.30 s | 2.0-3.5 | 24.1 m/s at 2 s (Classic 22.6) |
| M2 top / boost peak / boost time | 48.0 / 88.1 m/s / 3.6 s | 47.8 / 88.2 / 4.1 s | 45-60, x1.6-2.0, 3-5 s | same race pace |
| M3 brake: stop time / distance / peak | 2.17 s / 38.6 m / 4.31 g | 3.07 s / 57.1 m / 2.32 g | 1.5-3 s, 30-60 m, <= 2.5 g | a 40 t ship's brake, not a wall |
| M3 coast to half speed | 10.8 s | 2.5 s | 8-15 s | Galleon has no unpowered coast: "nothing held" is STOP, which backs the engines |
| M4 turn rate / t63 / t90 | 35.1 deg/s / 0.50 / 0.90 s | 34.1 / 0.37 / 0.87 s | 30-45, <= 0.5 / 1.0 | |
| M4 bank / slip / height lost | 17.8 deg / 19.6 deg / 5.15 m | 26.6 / 13.0 / 0.12 m | 12-22, -, <= 2 m | the bank is above the bench band by design (cinematic) |
| M5 U-turn (helm only) | 5.6 s / 181 m | 5.7 s / 187 m | 4-6 s, 100-180 m | 124 m (1.5 s swing) or 70 m (2.5 s swing): 3.7 |
| M6 nose: drive / boost / brake | -16.6 / -20.2 / +7.5 deg | -3.95 / -5.2 / +3.0 | -3..-8, -5..-10, +3..+8 | |
| M7 climb / sink | 12.0 / 15.0 m/s | 10.0 / 13.0 | climb 10-15 | |
| M7 +30 m step: overshoot / \|vz\| 1 s after / error 5 s | 12.1 m / 5.84 m/s / 11.5 m | 4.0 / 0.20 / 3.9 | <= 1.5 m, <= 1.5, - | stops where physics allows and holds, no bob |
| M8 sidle t90 / speed | 0.87 s / 12.3 m/s | 0.97 / 10.2 | 0.6-1.2, 10-15 | |
| M9 swing (drift): slip at 1 / 2 / 3 s | 15 / 42 / 63 deg | 18 / 40 / 54 | 20-45 at 1-2 s | |
| M9 turn rate / speed kept (3 s) / exit kick | 49.8 deg/s / 103 % / 4.8 m/s | 54.4 / 52 % / 2.9 | kept >= 70 %, 4-8 m/s | the swing trades speed for a tight turn on purpose; a 2 s swing keeps 71 % |
| M10 host: cosmetics / server turn / screen turn / speed | 0 / 2 / 2 / 1 frames | 0 / 2 / 2 / 1 | 0-1, <= 2 | |
| M10 client 100 ms: cosmetics / server / screen turn / speed | 0 / 6 / 9 / 8 | 0 / 6 / 9 / 8 | <= 8 | camera look-ahead: 3 frames (Classic camera 19) |
| M11 precise, host / 100 ms: time, missed | 60.5 / 62.7 s, 0 / 0 | 61.1 / 63.0 s, 0 / 0 | 0 missed | line error mean 3.3 / 2.4 m (Classic 2.2 / 2.4) |
| M11 sloppy, host: missed (12-seed mean) | 1 (1.58) | 0 (1.08) | <= 1 | |
| M11 sloppy, 100 ms: missed (12-seed mean), time | 6 (5.33), 78.2 s | 1 (1.25), 62.8 s | <= 2 | line error max 16.8 m (Classic 115) |
| M12 precise, host / 100 ms: in arc, firing solution | 100 / 100 % | 100 / 100 % | >= 70 / 50 % | elevation mean 1.9 deg (Classic 5.7) |
| M12 sloppy, host: in arc / both / solution / broadsides | 69 / 64 / 69 % / 37 | 100 / 100 / 100 % / 40 | | |
| M12 sloppy, 100 ms: in arc / both / solution / broadsides | 37 / 30 / 34 % / 21 | 100 / 86 / 100 % / 40 | | stations: level deck + fine helm (after the first broadside, R1; was 90 % both) |

Galleon-only checks (`galleon_checks.json`):

| Check | Result |
|---|---|
| Hold W from STOP: SLOW / HALF / FULL arrive at | 0 / 0.27 / 0.43 s |
| Hold S from FULL ends at | STOP (detent) |
| Helm at HALF (28 m/s): turn rate, t63 / t90, bank, carry after release | 39.4 deg/s, 0.47 / 0.87 s, 26.5 deg, 11.7 deg |
| Broadside stations, full helm at HALF: bank / turn rate | 5.6 deg / 19.5 deg/s |
| Bank level again after a full-helm release | 0.8 s (Classic 1.9 s) |

How the numbers map to the judging:

* **Responsiveness.** Every input moves something in frame 0-1 (M10 cosmetics 0, the thruster pulse, the HUD). The
  bow answers faster than Classic's (t63 0.37 s) and the camera moves within 3 frames on any connection.
* **Controllability.** No turn sink, nose under 4 deg, the vertical stops where you let go, the heading carry is
  smaller. The sloppy bot misses fewer gates than on Classic at both latencies.
* **Expressiveness.** Notch choice per section, the swing (a 70-124 m U-turn against 188 m, paid in speed), sidle
  for range, full steam timing. The precise bot still beats the sloppy one, by 2.2 s on the host.
* **Weight and readability.** Telegraph needle and order, the 26 deg heel, a 3 s brake, 10 m/s climb, the majestic
  camera.
* **Combat fit.** Hands-free speed, ship-relative beam watch, stations. Sloppy broadside time-on-target goes from
  69 / 37 % to 100 / 100 %.
* **Accessibility.** Hold W = FULL in 0.43 s, hold S = STOP; no need to keep a key down to keep moving; the deck
  levels itself for gunnery.
* **Feedback.** Section 7.
* **Lag robustness.** Section 9.

## 11. Known risks

1. **Inertia fix dependency.** `KpRoll` 18 is tuned on the real roll inertia (base fix 4a-1). Without the fix, the roll
   loop is 5.7 times stiffer and saturates the pods. Do 4a-1 (and its PIE log) first.
2. **Accidental stern swing.** Braking while holding a helm key above 6 m/s swings the stern (the bench's sloppy bot
   did this until its adapter learned to let go of the helm while braking). The SWING tag and the wheel make it
   obvious; if playtests show it as a trap, raise `DriftSteerThreshold` for the gamepad or require the helm to be held
   before the brake.
3. **Stations while sightseeing** (fixed by review R1). As designed, looking out over the side during a race halved
   the turn rate, and beam glances cost even the precise bot 1-2 gates. Stations now need Aim or an own broadside in
   the last 6 s, so looking around never changes the handling; firing on the beam still levels the deck at once.
4. **Telegraph habits.** Classic players expect W to be a pedal. Holding W reaches FULL in 0.43 s and holding S stops
   at STOP, so the pedal habit still works. The difference: letting go of W keeps the speed.
5. **The brake resumes the order.** Releasing X after a stop at FULL accelerates again. That is deliberate (hands-free
   hairpins), but a player wanting to stay stopped must ring STOP.
6. **The swing costs speed** (M9 52 % kept over 3 s, below the bench's 70 % band). A 1-2 s swing keeps 71-100 %; the
   cost is the trade for a 70 m U-turn.
7. **No coast.** There is no unpowered glide notch (M3 coast is the STOP order). A race doesn't need one.
8. **Deck heel.** 26 deg of heel tilts the deck for passengers (CMC walkable floor is 44.8 deg, so they stay on), and the
   view from the deck rolls more. Test with a rider.
9. **Look-ahead and the cannon side.** The look-ahead turns the aim point, so a pilot looking forward in a hard turn
   can flip the facing side (cosmetic barrel swing; firing still uses a fresh trace).
10. **Bench limits.** No collisions, passengers, client-copy smoothing, camera position lag or collision. Shake, roll,
    FOV and HUD are spec only. The base fixes are re-implemented in `scheme_galleon.py` (the bench has no hooks for
    two of them). PIE stays the judge; expect PIE within 1-2 deg and 0.3 m/s of these numbers where Classic's
    calibration holds, and recheck everything pitch-related after 4a-1.

## 12. C++ change list

**`IMPLEMENTATION_PLAN.md` is the authoritative, ordered change list** (shared framework in its section 1, Galleon in
2.1). This section is the designer's list, corrected by the review; where they differ, the plan wins (shared names for
the gun deck, the feedback and the arc helper; reset hooks; the stations rule).

Contract items (enum, `ControlScheme` property, `SetControlScheme`, `Aura.Airship.Scheme`, telemetry fields) are the
implementer's shared work and are not repeated here. Galleon needs **no contract change and no new RPC field**. It
uses one free Buttons bit and the existing Throttle axis as the order code.

### `Public/Airship/AirshipTypes.h`

* `namespace Airship`: `constexpr uint8 Button_Stations = 1 << 4;` (Galleon: broadside stations; only read when the
  ship's scheme is Galleon, so another scheme may give bit 4 its own meaning).
* New `namespace AirshipGalleon`:
  ```cpp
  constexpr int32 Astern = -1, Stop = 0, Slow = 1, Half = 2, Full = 3;
  inline int8 NotchToThrottle(int32 N) { return N < 0 ? int8(-127) : static_cast<int8>(FMath::RoundToInt(127.f * FMath::Clamp(N, 0, 3) / 3.f)); } // -127 0 42 85 127
  inline int32 ThrottleToNotch(int8 T) { const float V = FAirshipPilotInput::AxisToFloat(T); return V <= -0.5f ? Astern : FMath::RoundToInt(FMath::Clamp(V, 0.f, 1.f) * 3.f); }
  inline float NotchToOrderValue(int32 N) { return N < 0 ? -1.f : N / 3.f; }   // telemetry ThrottleOrder
  inline const TCHAR* NotchName(int32 N) { static const TCHAR* Names[] = { TEXT("FULL ASTERN"), TEXT("STOP"), TEXT("SLOW"), TEXT("HALF"), TEXT("FULL") }; return Names[FMath::Clamp(N, -1, 3) + 1]; }
  ```
* Comment on `FAirshipPilotInput::Throttle`: "Galleon: the engine order code (`AirshipGalleon::NotchToThrottle`)".

### `Public/Airship/AirshipFlightComponent.h`

* The new UPROPERTYs of 5.2 (EditAnywhere, BlueprintReadOnly, the categories given), with the defaults in its
  Classic column for the shared ones and the Galleon values for the `Galleon*` ones.
* `EAirshipControlScheme ActiveScheme = EAirshipControlScheme::Classic;` + `void SetActiveScheme(EAirshipControlScheme)`
  (resets the state below).
* Private state: `int32 GalleonLastNotch = 0; float GalleonOrderPulse01 = 0.f; float GalleonBoostPulse01 = 0.f;
  bool bGalleonPrevBoost = false; bool bShStations = false; FAirshipPilotInput LastGoodServerInput;`
* Getters: `int32 GetGalleonNotch() const` (decoded from `CurrentControls`), `bool IsStations() const`.

### `Private/Airship/AirshipFlightComponent.cpp`

* `SelectControls`: Galleon timeout rule (3.2). Keep `LastGoodServerInput` = the last fresh `ServerInput`. On a stale
  input with a controller, return it with Steer / Lift / Strafe 0 and the Boost / Brake / Aim / Stations bits cleared.
* `ShapeControls`: Galleon branch (3.3): notch decode, pulses, throttle target from the speed loop (helper
  `GalleonHoldThrottle(float V)`), boost = 1, brake with `BrakeFadeSpeed` (4c), `SteerTauRelease`, `LiftTauRelease`
  (4b), `bShStations`. Under Galleon `bDrifting` (the swing) uses the same existing test with the preset's
  `DriftSteerThreshold` / `DriftMinSpeed`.
* `ApplyForces`:
  * `ARev` rule (3.3) and the `BrakeMaxAccel` clamp on `ABrake` (3.4).
  * Base fixes 4a-1, 4a-2, 4b, 4c, 4d exactly as BASELINE section 4 specifies (the bench ports them line by line in
    `scheme_galleon.py`, marked BASE FIX).
  * Bank: `if (bShGunDeck) BankDeg *= GunDeckBankScale` after Classic's formula (`BankMaxDriftDeg` already
    applies when drifting).
  * Yaw: `if (bShGunDeck && !bDrifting) { RmaxDeg *= GunDeckYawScale; YawRateCmd *= GunDeckYawScale; }`. Then the loop gain / cap:
    `Kr' = bDrifting && DriftKr > 0 ? DriftKr : Kr`, `AYawMax' = bDrifting && DriftAlphaYawMax > 0 ? DriftAlphaYawMax :
    AlphaYawMax`. Else, when `KrSteady > 0 && |YawRateCmd| < |YawRate|`, use `Kr' = KrSteady` and
    `AYawMax' = max(AlphaYawMax, AlphaYawMaxSteady)`. These replace `Kr` / `AlphaYawMax` in the `AlphaZ` line only.
  * Lateral: `GripDir = bLevelGripForce ? FVector(Right.X, Right.Y, 0).GetSafeNormal() : Right` and
    `ACom = GripDir * AGrip + Right * WindLat + Fwd * (ADrag + ABrake + ARedirect + AKeepF)` (+ 4b's vertical term).
  * The drift kick is unchanged: under Galleon it is the swing's exit surge via the preset's `DriftBoostMinTime` /
    `DriftBoostDV`.
* `UpdateCosmetic`: if `bDrifting`, `C.Steer = clamp(ShSteer * DriftCosmeticSteerScale, -1.3, 1.3)`, with
  `C.FanYawDeg` still from `ShSteer`. Under Galleon, `Pulse = GalleonOrderPulse * max(GalleonOrderPulse01,
  GalleonBoostPulse01)` is added to each `C.PodThrustAlpha` (clamp 0..1.5).
* `FillTelemetry`: under Galleon `Scheme` 1, `ThrottleOrder = NotchToOrderValue(GetGalleonNotch())`, `bFreeLook` true,
  `DriftCharge` 0, `bHeadingTargetActive` false. `bDrifting` already reports the swing.
* `ResetInput`, `SetFlightEnabled`: reset `GalleonLastNotch`, the pulses, `DriftTime`.

### `Public/Airship/AirshipPawn.h` / `Private/Airship/AirshipPawn.cpp`

* New UPROPERTYs of 5.4, plus the `ImpactEpisodeAccelUp` base fix (4e) in `LimitImpactResponse` (BASELINE 4e).
* Pilot-side state: `int32 GalleonNotch; bool bGalleonUpHeld, bGalleonDownHeld; int32 GalleonRepeatDir; double
  GalleonNextRepeatTime; float GalleonCamOffsetYaw, GalleonLookAhead, GalleonLastHullYaw, GalleonLastLookAhead,
  GalleonCamRoll; bool bGalleonBeamWatch, bGalleonStations, bGalleonCamInit; float CameraTrauma, CameraFOVKick;
  bool bGalleonPrevBoostLocal, bGalleonPrevSwingLocal; float GalleonSwingLocalTime;`
* `ResetGalleonPilotState(bool bNotchFromSpeed)` (3.12): call it from `UpdateLocalMappingContext` (when the IMC is
  added), `ApplyControlScheme` / `OnRep_ControlScheme` (with true), `OnRep_PilotCharacter` (every machine; review R6)
  and `HandleDeath`. (`UnPossessed` only runs on the server; the reset there is covered by `ResetInput`.)
* `GatherLocalInput`: under Galleon, after reading the keys (and only when there is no debug input), the beam watch
  and stations flag (3.8, evaluated here so the bit leaves in the same frame), the telegraph (3.1) sets
  `Controls.Throttle`, and `Controls.SetButton(Airship::Button_Stations, bGalleonStations)`.
* `HandleCannonsFired`: when `IsLocallyControlled()`, `LastOwnBroadsideTime = Now` (R1) and the own-broadside feedback.
* `UpdateCamera`: Galleon branch (6), including the trauma shake and the FOV kick. The FOV kick adds to Classic's
  `TargetFOV`.
* Feedback hooks on the pilot's machine (7): the order change in the telegraph `Step`; boost start when
  `Flight->GetCosmeticState().Boost` crosses 0.5 upward (or the local boost latch rises); swing exit when the local
  cosmetic `bDrifting` falls after at least `DriftBoostMinTime`; `HandleCannonsFired` when `IsLocallyControlled()`;
  `OnHullHit` when `IsLocallyControlled()` (impact speed from the pre-step velocity, as `LimitImpactResponse` measures
  it). Rumble via `Cast<APlayerController>(GetController())->PlayDynamicForceFeedback(...)`.
* New getters: `int32 GetGalleonNotch() const`, `bool IsGalleonStations() const`, `bool IsAimInCannonArc(EAirshipSide Side, const FVector& AimPoint)
  const`. The last uses the local aim point and the unclamped yaw / elevation of `ComputeCannonAim` (split it into a
  raw helper): true if either cannon of that side has |yaw| <= `CannonYawLimitDeg` and elevation in
  `CannonElevMinDeg..CannonElevMaxDeg`.
* `ApplyControlScheme` (contract) writes the Galleon preset (5.1-5.4, CameraBoom values included), calls
  `Flight->SetActiveScheme`, then `OnTuningChanged()`.

### `Public/Airship/AirshipHUDWidget.h` / `Private/Airship/AirshipHUDWidget.cpp`

* New UPROPERTY `FVector2D GalleonPanelSize = (292, 214)`. `GetPanelSize()` returns it under Galleon (the pawn's
  `ShowShipHUD` must re-read the size on a scheme switch).
* `RefreshValues`: the values listed in 8, plus `GalleonRingTimer` (0.4 s from a notch change).
* `NativePaint`: the telegraph row, the speed rule, the helm row and the in-arc / FIRE marks (8). Classic's layout is
  unchanged when the scheme is not Galleon.

### `Private/Airship/AirshipSubsystem.cpp`

Nothing Galleon-specific. `Aura.Airship.Input <throttle> ...` sends the order code under Galleon (3.2).

## 13. PIE harness notes (Galleon)

* **Telegraph.** A notch step is `IA_AirshipThrottle` +1 (or -1) injected for one frame, then at least one empty
  frame (so `Completed` fires). Holding the injection auto-steps (0.25 s, then every 0.15 s). "Full forward drive" =
  three steps from STOP; "nothing held" = STOP. The bench's `command_raw` does exactly this.
* **Camera.** Set the control rotation every frame (absolute yaw; the Galleon camera turns it into a ship-relative
  offset). A beam target (more than 55 deg off the bow) gives beam watch; stations follow with the first broadside
  (R1). The M12 bot fires whenever it has a solution, so no aim key is needed for M12. For a stations check without
  firing, hold `IA_AirshipAim`.
* **M10.** The first wire change is the first telegraph step (SLOW), whose throttle target is already 1 from rest.
* **Checks to log:** `ThrottleOrder` (telemetry), `bDrifting` (swing), the Buttons bit 4 on the server's
  `CurrentControls` (stations).

## 14. Sim files

| File | What |
|---|---|
| `sims/scheme_galleon.py` | The scheme plug-in: preset, `GalleonFlightModel` (shaping / forces / cosmetics with the base fixes and Galleon branches, marked), telegraph, camera, telemetry, bot adapters |
| `sims/galleon_checks.py` | Telegraph, helm, swing, U-turns, stations, camera response, sidle, brake, 12-seed sloppy course for Galleon and Classic, and (review) the course with beam glances: `python3 galleon_checks.py --json galleon_checks.json --course-seeds` (about 45 s) |
| `sims/galleon_sweep.py` | Course sweep helper used while tuning (several seeds, flight / gain overrides) |
| `sims/galleon_metrics.json`, `sims/galleon_checks.json` | Outputs (2026-11-23) |

Reproduce: `cd Docs/Airship/controls/sims; python3 metrics.py galleon; python3 galleon_checks.py --json
galleon_checks.json --course-seeds; python3 compare.py classic galleon`. Shared bench files were not edited.

Tuning history, in short:
* A slower yaw onset (more "momentum") made both bots worse. The tune then wanted aggressive gains that made the
  sloppy bot reverse the helm in the broadside orbit, so the onset went back to Classic's and the weight moved into
  the heel, the carry and the telegraph.
* A full level-frame lateral loop added slip and was dropped for the simple level force.
* A latency-compensated heading hold ("steady") helped the 100 ms client a little, hurt the host, and added
  ping-dependent state, so it was dropped.
* A progressive keyboard helm helped neither bot.
* The gunnery helm (x 0.5 at stations) took the sloppy broadside from 58-69 % to 100 % in arc.

## Review changes

Adversarial review before any C++ was written (2026-11-23). The bench was re-run first: `metrics.py galleon`
reproduced `galleon_metrics.json` exactly and `galleon_checks.py --course-seeds` reproduced `galleon_checks.json`
exactly (the sims must run from their own folder: `airship_sim.py` reads the keel points from
`../../sims/fix2/ucx.json`, and a copy elsewhere silently loses them and changes Classic's sloppy course). The design,
the feel targets and every other number are the designer's.

| # | What changed | Why |
|---|---|---|
| R1 | **Weakest point, fixed: broadside stations from beam watch need an own broadside within `GalleonStationsFireHoldTime` (6 s, new pawn property).** Aim held still gives stations at once. Sections 1, 2, 3.8, 7, 11 (risk 3), 13; bench `scheme_galleon.py` `pilot_input`. | As designed, any look more than 55 deg off the bow halved the helm. The ship-relative camera never recentres in beam watch, so a pilot who glanced at an enemy while racing was left with a half-strength helm. New check `beam_glances` (gate course, 60-90 deg glances for 1-2 s every 6-10 s, no firing): the precise bot missed 2.0 / 1.0 gates (0 / 100 ms) as designed and 0 / 0 with R1; the sloppy bot 2.25 / 0.75 against 0.5 / 1.25 (4 seeds; the 100 ms sloppy pair is within seed noise). M12 is unchanged (the bot fires as soon as it has a solution): 100 % in arc and firing solution at both latencies; sloppy 100 ms both-cannons 90 → 86 %. |
| R2 | The beam watch / stations flag is evaluated at the start of `GatherLocalInput`, not in `UpdateCamera`. | `UpdateCamera` runs after `GatherLocalInput` in `AAirshipPawn::Tick`, so the bit would have left one frame late. The bench evaluates the camera before the input too. |
| R3 | Shared names: `GalleonStationsBankScale` / `GalleonStationsHelmScale` → `GunDeckBankScale` / `GunDeckYawScale`; `IsAimInArc` → `IsAimInCannonArc(Side, AimPoint)`; `bLevelGripForce`, `BrakeMaxAccel`, `DriftAlphaYawMax` are shared with the other schemes. The bench keeps the old names (mapping in `IMPLEMENTATION_PLAN.md` 6). | All three schemes have a "steady gun deck" and an arc test; one implementation, one set of properties. |
| R4 | Camera roll, trauma shake, FOV kicks and rumble use the shared feedback properties (section 5.4 table); the FOV kick is added after the FOV interpolation; rumble names the native `PlayDynamicForceFeedback` overload. | Three schemes had three copies of the same "juice" code. A kick added to the interpolated target is smoothed away by the 4 /s FOV filter. |
| R5 | The `ARev` rule (3.3) is gated by `ActiveScheme == Galleon`. | Ungated it changes Classic's S key. |
| R6 | Resets also run from `OnRep_PilotCharacter` on every machine; the camera component's relative rotation / location are zeroed on every scheme apply; `DriftTime` resets on a scheme apply. | `PossessedBy` / `UnPossessed` run only on the server, so a client pilot and the observers never reset; a Galleon camera roll would otherwise stay on in Classic. |
| R7 | `ImpactEpisodeAccelUp` defaults to 0 = "same as ImpactEpisodeAccel". | Classic stays exact v1 even if `ImpactEpisodeAccel` is tuned live. |
| R8 | Section 12 now points at `IMPLEMENTATION_PLAN.md` as the authoritative change list. | One list for the implementer. |

Checked and left as designed: the speed loop gain (0.001 per cm/s through a 0.15 s filter: loop time constant about
0.76 s, no overshoot); the roll pair (KpRoll 18 / KdRoll 5.4: ωn 4.2 rad/s, ζ 0.64, stable at 1/30 s and at 1/120 s:
`sims/review_fps_check.py` gave the same turn, swing, brake and climb numbers within 0.3 m and 0.2 deg/s); the order on
the Throttle axis (a latched state, safe under loss and in the switch window); the timeout rule; the telegraph's edge
detection on the axis value (works with one-frame Enhanced Input injection); all contract fields. Distinctness: Galleon
is the only scheme with a speed order and a ship-relative camera; it keeps Classic's helm rates, so it reads as
Classic with weight, orders and gunnery rather than a new way to steer.
