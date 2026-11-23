# Control scheme 2: Sky Racer

`EAirshipControlScheme::SkyRacer` (2), display name "Sky Racer". Arcade speed and flow: hard acceleration, a fast and
planted turn, a drift that slides the hull and charges a three-tier mini-turbo, a boost burst, punchy climbs and dives,
a chase camera that looks into the turn, and a gun deck for broadsides.

| File | What |
|---|---|
| `Docs/Airship/controls/SCHEME_SKYRACER.md` | This spec |
| `Docs/Airship/controls/sims/scheme_skyracer.py` | The bench model of the scheme (preset table, flight model changes, camera, bot adapters) |
| `Docs/Airship/controls/sims/skyracer_checks.py` | Sky Racer's target bands and the drift, turbo, lag, brake, camera and 5-seed course checks (`--tune` reruns the bot-gain sweep) |
| `Docs/Airship/controls/sims/skyracer_metrics.json` | `python3 metrics.py skyracer` (the M1-M12 keys the PIE harness also writes) |

Everything here is from the bench (`airship_sim.py`, calibrated against PIE within about 0.2 m/s and 1 deg for v1),
written before anything was built or run in Unreal. Numbers marked **guess** are untested.

**Status (2026-11-23):** built and run in PIE pass 1 (17 of 17 runs, `PIE_RESULTS.md`), judged second of the four,
0.24 behind Point & Fly with two of the three first places (`RESULTS.md`), and kept switchable
(`Aura.Airship.Scheme 2`); Point & Fly is the default. Changes made after this spec was written: "Review changes" at
the end; the code: `../CPP_NOTES.md` 14.

---

## 1. Concept: why it is fun

Sky Racer turns the race along the collapsing hex path into a flow game. W launches the 40 t ship hard (33 m/s after
2 s, Classic 23), and A/D turns it fast and planted: the hull banks 23 deg into the turn, holds its height and levels
itself when you let go. The skill move is the drift: hold X with A or D at speed and the tail steps out (the drift
drives at full power, so W can be let go: review R1), and the ship
slides round a tighter arc than it can grip with its nose held 16-26 deg inside the path, while a three-tier
mini-turbo charges (on the HUD and in the exhaust) faster the harder you commit. Let go and the slide straightens
along the nose with a kick of 3, 5 or 7.5 m/s, a burn and some boost fuel; drift again within 2.5 s and the next turbo
chains for up to +45 %. A good pilot snakes a slalom as drift, turbo, drift, turbo, which flies the test course 11 %
faster than the same ship on grip alone and 19 % faster than Classic: a real skill ceiling. An average pilot can
ignore all of it and still has a quick, forgiving ship that stops climbing where they let go and shrugs off hits.
It still reads as a big airship, not a jet fighter, because the throttle and boost spool up visibly (t80 2.9 s), the
bank tops out at 23-24 deg, the drift is a slide with a visible slip angle rather than a flick, the camera trails and
leans, and the brake is a firm 2 g, never a wall. For combat, holding RMB turns it into a steady gun deck (the bank
flattens to a third, the throttle, brake and turn soften), and the broadside then holds its target 100 % of the time
in the orbit test, where Classic's sloppy pilot manages 69 %.

## 2. Controls

No new actions, keys or mapping contexts. The existing IAs are read differently in C++.

| Action (IA) | Keyboard / mouse | Gamepad | Sky Racer | Classic (v1) |
|---|---|---|---|---|
| Throttle (IA_AirshipThrottle) | W / S | left stick Y | W: full drive (1.9 g at low speed, 56 m/s top). S: an analog brake while moving forward faster than 3 m/s, progressive on a key (a 0.1 s tap costs about 1 m/s, a hold stops in 3.3 s); below 3 m/s it reverses | S reverses gently (0.5 g) |
| Steer (IA_AirshipSteer) | A / D | left stick X | Turn rate up to 50 deg/s at 16 m/s, 38 deg/s at top speed; snappy bank (23 deg), levels itself; in a drift it sets the drift's path rate (see X) | up to 45 / 35 deg/s, 18 deg bank |
| Brake / drift (IA_AirshipBrake) | X | B | Alone: full brake (capped at about 2 g, the ship holds its height). With A/D held and faster than 15 m/s: **drift**. A drift drives at full power whether W is held or not (S + X drifts slower). Release X to fire the mini-turbo | brake; brake + steer = v1 drift |
| Boost (IA_AirshipBoost) | Left Shift | A | Boost **burst**: every press gives at least 0.5 s of boost (2.6 g, +6 m/s kick), hold to extend; fuel gated | held boost |
| Lift (IA_AirshipLift) | Space / Ctrl or C | RT / LT | Climb 13.5 m/s, dive 16.5 m/s, stops within 1 s of release with no bob; diving at speed adds forward speed | 12 / 15 m/s, overshoots 12 m |
| Strafe (IA_AirshipStrafe) | E / Q | D-pad right / left | Side slide at 14 m/s (Classic 12) | |
| Aim (IA_AirshipAim) | RMB | LB | **Gun deck** while held: bank x 0.35, throttle x 0.6, brake x 0.3, turn x 0.8, FOV -14 deg, no auto-follow | FOV -15 deg, no recentre |
| Fire (IA_AirshipFire) | LMB | RB | Unchanged: the broadside on the side the camera faces | |
| Look (IA_AirshipLook) | mouse | right stick | Free look; the chase camera takes over again 0.6 s after the last look input | recentre after 1.5 s |
| Zoom (IA_AirshipZoom) | wheel | D-pad up / down | Unchanged | |
| Exit (IA_AirshipExit) | F | Y | Unchanged; also resets the drift / turbo state | |

How to drift on a keyboard (review R1): hold A or D and press X. W is optional, because a drift drives at full power
unless S is held, so a right drift is index finger on D and middle finger on X, a left drift ring finger on A and
index finger on X (as designed, a right drift needed W + D + X at once, with the ring finger crossing under the
middle finger). Hold S as well for a slower, tighter drift. Ease off the turn key (a gamepad stick back to centre, or
a short counter-tap on the keyboard) to widen the slide. Let go of X when the nose points down the exit. On a gamepad,
B + the stick held sideways drifts at full drive although the stick then has no forward component.

---

## 3. Behaviour spec

### 3.1 What runs where

| Behaviour | Function | Pilot | Server | Observers |
|---|---|---|---|---|
| Keys to `FAirshipPilotInput` | `GatherLocalInput` | as Classic (no new fields) | - | - |
| Drift state machine, charge, tier, chain, turbo timer, S-brake ramp, exit window | `ShapeControls` | yes, from its own controls | yes, from the received controls | yes, from `RepInput` |
| Boost burst latch | `UpdateBoostServer` / client gate in `UpdateFlight` | predicted | authoritative | from `RepInput` |
| Drift forces, path force, turbo kick + burn + fuel, grip changes, dive gain, gun deck, base fixes | `ApplyForces` | - | yes | - |
| Cosmetic drift / turbo values, FX pulses, nozzle roll | `UpdateCosmetic`, `ComputeGimbals`, `UpdateFX` | yes | yes (listen host) | yes |
| Chase camera, camera roll, shake, FOV kicks, turbo arm, rumble | `UpdateCamera` | yes | - | - |
| TURBO row | `UAirshipHUDWidget` | yes | - | - |

The drift is decided the same way v1 decides `bDrifting`: from the brake bit, the steer axis and the forward speed, on
every machine. So it needs no new wire field. The pilot's HUD, FX and camera react in the same frame as the key. The
server, a frame plus the latency later, runs the same state machine on the same control stream and pays the turbo from
its own copy (section 8).

### 3.2 Drift state machine (`ShapeControls`, every machine)

New runtime state on the flight component (reset by `ResetSchemeState`, section 11.3): `SkyClock` (s), `SkyDriftDir`
(-1, 0, +1), `SkyCharge` (0..1), `SkyDriftTime` (s), `SkyChain` (0..3), `SkyLastReleaseTime` (s on `SkyClock`),
`SkyTurboTier` (0..3), `SkyTurboLeft` / `SkyTurboTotal` (s), `SkyTurboEvent` (tier released this frame, 0 = none),
`SkyTurboChain`, `SkyTurboEventCount` (uint8, wraps), `SkyExitLeft` (s), `SkySBrake` (0..1), `SkyBrakeAmount` (0..1).

```
// at the top of ShapeControls, when bSkyDrift (Sky Racer); Dt = the clamped physics step, Vf = forward speed (cm/s)
SkyClock += Dt
SkyTurboEvent = 0
RawSteer = Controls.GetSteer();  Brake = Controls.IsBrake()  // X / B

if SkyDriftDir == 0:
    if Brake && |RawSteer| >= SkyDriftEnterSteer (0.5) && Vf >= SkyDriftEnterSpeed (1500):
        SkyDriftDir = sign(RawSteer);  SkyCharge = 0;  SkyDriftTime = 0
        SkyChain = (SkyClock - SkyLastReleaseTime <= SkyChainWindow (2.5 s)) ? min(SkyChain + 1, SkyChainMax (3)) : 0
else if !Brake || Vf < SkyDriftExitSpeed (800):
    Grace = (authority && the pilot is remote) ? SkyTierGrace (0.03) : 0
    Tier  = TierOf(SkyCharge + Grace)        // >= SkyTier3 (1.0): 3, >= SkyTier2 (0.55): 2, >= SkyTier1 (0.25): 1, else 0
    if Tier > 0 && Vf >= SkyDriftExitSpeed:
        SkyTurboTier = Tier;  SkyTurboTotal = SkyTurboLeft = SkyTurboTime<Tier> (0.5 / 0.8 / 1.2 s)
        SkyTurboEvent = Tier;  SkyTurboChain = SkyChain;  SkyLastReleaseTime = SkyClock;  ++SkyTurboEventCount
    else:
        SkyChain = 0
    SkyDriftDir = 0;  SkyCharge = 0;  SkyExitLeft = SkyDriftExitTime (0.4 s)
else:
    SIn = clamp(RawSteer * SkyDriftDir, -1, 1)          // +1 full into the drift, 0 centred, -1 full counter-steer
    SkyCharge = min(1, SkyCharge + lerp(SkyChargeRateMin (0.2), SkyChargeRateMax (0.5), (SIn + 1) / 2) * Dt)
    SkyDriftTime += Dt
SkyTurboLeft = max(0, SkyTurboLeft - Dt)
if SkyExitLeft > 0 && SkyDriftDir == 0 && SkyTurboEvent == 0:  SkyExitLeft = max(0, SkyExitLeft - Dt)
bDrifting = SkyDriftDir != 0                              // replaces v1's bDrifting rule when bSkyDrift
```

Charge times from the drift start (bench): full in 0.53 / 1.13 / 2.03 s to T1 / T2 / T3; stick centred 0.73 / 1.6 /
2.87 s; half counter-steer 0.9 / 2.0 / 3.63 s. A hull hit does **not** cancel a drift (forgiving).

### 3.3 Brake: X and S (`ShapeControls` + `ApplyForces`)

```
// ShapeControls, Sky Racer
STarget  = (!bDrifting && Throttle < 0 && SkySBrakeSpeed (300) > 0 && Vf > SkySBrakeSpeed) ? -Throttle : 0
SkySBrake = ApproachUpDown(SkySBrake, STarget, Dt, SkySBrakeTauUp (0.3 s), SkySBrakeTauDown (0.08 s))
if STarget <= 0 && SkySBrake < 0.02:  SkySBrake = 0
SkyBrakeAmount = (Brake && !bDrifting) ? 1 : (bDrifting ? 0 : SkySBrake)
bShBrake = SkyBrakeAmount > 0
ThrottleTarget = Throttle                                  // W/S as read (S below 3 m/s = reverse, AFanRev)
if bDrifting && SkyDriftThrottle (1.0) > 0 && Throttle >= 0:   // review R1: a drift drives at full power, W optional
    ThrottleTarget = max(ThrottleTarget, SkyDriftThrottle)
if bShBrake:                                               // base fix 4c-2 (BrakeFadeSpeed 1000)
    ThrottleTarget = -BrakeReverseThrottle (0.4) * SkyBrakeAmount * clamp(Vf / BrakeFadeSpeed, 0, 1)

// ApplyForces (server). With bSkyDrift false, SkyBrakeAmount = 1 and SkyBrakeAccelMax = 0: exactly v1
ABrakeRaw = Kbrake (1.5) * Vf * (v1 drift ? DriftBrakeScale : 1)
if BrakeMaxAccel (1470) > 0:  ABrakeRaw = clamp(ABrakeRaw, -BrakeMaxAccel, BrakeMaxAccel)   // shared cap (bench: SkyBrakeAccelMax)
ABrake = bShBrake ? -ABrakeRaw * SkyBrakeAmount : 0
```

From cruise (56 m/s), X stops the ship in 2.87 s over 72 m: peak 2.5 g, mean 2.0 g (Classic: 4.3 g peak, "a wall").
In a W-held cruise an S tap of 0.1 / 0.2 / 0.5 s costs 1.1 / 2.6 / 7.6 m/s. A brake press latches the hold altitude
with the stopping-distance lead (base fix 4c-1).

### 3.4 Grip turning (`ApplyForces`, server)

Three changes make the grip turn planted and stop the 5 m sink of v1 (README Finding 3):

```
// lateral block, not drifting
if SkyExitLeft > 0:   Klat = max(Klat, SkyDriftExitKlat (8)); ALatMax = max(ALatMax, SkyDriftExitALatMaxG (5) * g)
ALatCmd = clamp(SkyGripCentripetalFF (0.5) * AngVel.Z * max(Vf, 0) + Klat * (Strafe * StrafeSpeed - Vl), -ALatMax, ALatMax)
AGrip   = ALatCmd - ALatPhys                                              // as v1
if SkyGripEnergyKeep (0.85) > 0:                                          // energy-based redirect
    ARedirect = (Vf > RedirectMinSpeed) ? SkyGripEnergyKeep * max(0, -ALatCmd * Vl) / max(Vf, 500) : 0
else: ARedirect = v1 (Eta * |AGrip| when AGrip opposes Vl)
GripDir = bLevelGripForce ? (bLevelGripAlongHeading ? normalize(-Fwd.Y, Fwd.X, 0) : normalize(Right.X, Right.Y, 0)) : Right
                                                                          // shared switches (bench: bSkyLevelGrip); Sky: along the heading
ACom = GripDir * AGrip + Right * WindLat + Fwd * (...)                    // was Right * (AGrip + WindLat)
```

* The feed-forward supplies half the centripetal acceleration, so the grip loop settles with a 3 deg slip (v1: 20 deg).
* The energy redirect gives back 85 % of the energy the side force really scrubs (power `-a_lat * vl`). v1's
  `Eta * |AGrip|` would over-pay once the feed-forward makes `AGrip` large while the slip is small.
* Level grip removes the sink: at 23 deg of bank and about 3.9 g of side force, v1's banked axis would pull the ship
  down at 1.5 g.

Result at cruise, full steer: 38.0 deg/s, t63 0.30 s, t90 0.60 s, bank 23.1 deg, slip 3.3 deg, height change 0.0 m
(Classic 35.1 deg/s, 0.50 / 0.90 s, 17.8 deg, 19.6 deg, -5.2 m). In C++ this is the shared `bLevelGripForce` with
`bLevelGripAlongHeading` true. Galleon uses the same switch with the other direction (the hull's right axis made
level). The review tried both formulas on both schemes: the sloppy bot lost 0.6-1.0 gates (5-seed mean) on the
formula it was not tuned with, so each scheme keeps its own and the C++ has one extra bool.

### 3.5 Drift dynamics (`ApplyForces`, server)

The steer sets the **path** turn rate; the yaw loop swings the nose in to hold a slip angle on top of it; a level
hidden force perpendicular to the velocity turns the path. So the path answers the stick directly, and the slide is
visible but cannot run away (v1's drift slip grows to 63 deg in 3 s).

```
SIn  = clamp(ShSteer * SkyDriftDir, -1, 1);  S01 = (SIn + 1) / 2                 // the SHAPED steer
VH   = |(V.X, V.Y)|;  CourseDeg = VH > 100 ? atan2(V.Y, V.X) : Current.Yaw;  SlipDeg = NormalizeAxis(Current.Yaw - CourseDeg)

// thrust fade and drag use the whole horizontal speed (the slide is no free speed)
VFade = bDrifting ? VH : Vf        // in AFanCmd: 1 - (max(VFade, 0) / VTopEff)^ThrustFadeExponent
SinSlip   = |Vb_horizontal.Y| / max(VH, 1)
ADragPath = -(DragC1 * VH + DragC2 * VH^2 + SkyDriftScrub (0.08) * VH * SinSlip)  // along the horizontal velocity
ADrag     = ADragPath * sqrt(1 - SinSlip^2)                                       // its share along Fwd: pitch lean only

// attitude
BankDeg = SkyDriftBankDeg (24) * Dir * lerp(0.7, 1, S01) * clamp(Vf / BankFullSpeed, BankMinFraction, 1) + StrafeBankDeg * Strafe

// yaw (replaces YawRateCmd, AlphaYawMax, RudderCap |Steer| while drifting); deg and deg/s in this block, the code
// converts to rad / rad/s; YawRateDeg = degrees(AngVel.Z)
PathRate   = Dir * lerp(SkyDriftPathRateMinDeg (24), SkyDriftPathRateMaxDeg (46), S01)
SlipTarget = Dir * lerp(SkyDriftSlipMinDeg (16), SkyDriftSlipMaxDeg (26), S01)
YawRateCmd = clamp(PathRate + SkyDriftSlipGain (3) * (SlipTarget - SlipDeg), +-SkyDriftYawRateMaxDeg (65))
PathRate   = Dir * min(|PathRate|, max(0, YawRateDeg * Dir + SkyDriftPathLeadDeg (10) + SkyDriftSlipGain * max(0, SlipDeg * Dir)))
             // after YawRateCmd: turn-in first, then the tail steps out (the path never runs ahead of the hull)
AlphaYawMax -> DriftAlphaYawMax (2.5 rad/s^2; shared name, bench SkyDriftAlphaYawMax);  RudderCap uses 1 in place of |Steer|

// lateral: the path force replaces the grip loop
PathN   = VH > 1 ? (-V.Y / VH, V.X / VH, 0) : Right
APhys   = dot(sum of the 4 pod forces + 2 fan forces (world), PathN) / Mass
APath   = clamp(PathRate[rad/s] * VH - APhys, +-SkyDriftALatMaxG (5) * g)
AGrip = 0;  ARedirect = 0
ACom += PathN * APath + (V.X, V.Y, 0) / VH * ADragPath          // and Fwd * ADrag is left out of ACom while drifting

// after the drift (SkyExitLeft > 0): the nose swings back part of the slip while the grip pulls the path onto it
YawRateCmd -= SkyDriftExitYawGain (6) * SlipDeg[rad]
```

`ComputeGimbals` adds `SkyDriftGimbalRollDeg (4) * Dir` of roll to every pod while drifting (inside the 5 deg cone), so
the nozzles visibly lean into the slide. It is a real side force and the path loop subtracts it.

Bench, full drift from cruise: the path turns at 46 deg/s; the slip is 8 deg at 1 s, 25 deg at 2 s and holds (24.5 at
3 s); the hull yaws at 56 deg/s on average; speed is kept at 96.5 %; there is no height change. Held for 6 s the speed
goes from 56.4 to 54.0 m/s. On release the course swings another 16 (T1) to 34 (T3) deg as the slide straightens; the
slip is gone 0.6-0.8 s after the release.

### 3.6 Mini-turbo, chain, fuel (`ApplyForces`, server; timers on every machine)

```
if SkyTurboEvent > 0:                                             // the release frame (server)
    KickDV = Fwd * SkyTurboKickDV<Tier> (300 / 500 / 750 cm/s) * (1 + SkyChainBonus (0.15) * min(SkyTurboChain, SkyChainMax))
    Body->AddImpulse(KickDV, NAME_None, true);  Ship->NoteFlightKick(KickDV)
    BoostFuel = min(BoostFuelMax, BoostFuel + SkyTurboFuel<Tier> (4 / 8 / 15))
TurboAlpha = SkyTurboLeft > 0 ? SkyTurboLeft / SkyTurboTotal : 0  // 1 -> 0 linear over 0.5 / 0.8 / 1.2 s
ATurbo = SkyTurboAccel (490) * TurboAlpha * max(0, 1 - (max(Vf, 0) / SkyTurboVTop (9000))^4)     // along Fwd, in ACom
```

| Release (bench, from cruise 56 m/s, W held) | Kick | Peak speed | Fuel | Exit swing |
|---|---|---|---|---|
| T0 (0.4 s) | 0 | 56.6 m/s | 0 | 11 deg |
| T1 (0.6 s) | 3.0 m/s | 59.7 m/s | +4 | 16 deg |
| T2 (1.2 s) | 5.0 m/s | 61.8 m/s | +8 | 28 deg |
| T3 (2.1 s) | 7.5 m/s | 62.6 m/s | +15 | 34 deg |
| Chain of three T2 drifts, 0.8 s apart | 5.0 / 5.75 / 6.5 m/s | | | |

### 3.7 Boost burst (`UpdateBoostServer`, server; the same latch in the client gate)

```
if SkyBoostMinBurst (0.5 s) > 0 && bBoostActive && Now - SkyBoostStartTime < SkyBoostMinBurst:  bWantBoost = true
... v1 body ...;  on the rising edge of bBoostActive: SkyBoostStartTime = Now
// UpdateFlight, client gate (bLocalBoostActive): the same latch with SkyLocalBoostStartTime and the client's clock
```

A one-frame Shift tap gives 0.50 s of boost: +6 m/s kick (BoostKickDV 600), peak 73 m/s from a 56 m/s cruise, and it
costs 21 fuel. Held from cruise, boost peaks at 92.5 m/s and the fuel lasts 3.2 s.

### 3.8 Vertical (`ApplyForces`, server)

All of the BASELINE 4b/4c base fixes, stronger than the suggested set because the climb is faster, plus a dive gain:

```
// v1 vertical + 4b (VertBrakeAccel 1180, HoldBrakeAccel 1960, LiftTauRelease 0.06 s) + 4c (bBrakeHoldLead)
// exactly as baseline_sim.py / BASELINE.md 4b-4c (the lead = the stopping distance vz|vz| / 2 HoldBrakeAccel)
if SkyDiveAccelPerSink (0.06 1/s) > 0 && ShLift <= -LiftDeadZone && Vz < 0 && Vf > SkyDiveMinSpeed (1500):
    ADive = SkyDiveAccelPerSink * -Vz            // along Fwd in ACom: a full dive at 16.5 m/s adds 1.0 m/s^2
```

Climb 13.6 m/s, sink 16.5 m/s. A +30 m step overshoots 5.4 m, which is the stopping distance from 13.6 m/s (about
1.8 g on average, up to 2.1 g). The ship then stays there: |vz| is 0.01 m/s 1 s after the release (Classic: 12.1 m
and 5.8 m/s). Rule from 4e: `ImpactEpisodeAccelUp` >= (CollectiveMax - 1) g + 0.35 g + VertBrakeAccel = 1078 + 343 +
1180 = 2601 cm/s², so the preset uses 2650.

### 3.9 Gun deck (aim held; `ApplyForces`, server)

```
// shared gun-deck properties (bench names SkyAim*Scale); the gun deck is Aim held in Sky Racer
if bShGunDeck:  BankDeg *= GunDeckBankScale (0.35)                  // also while drifting
if bShGunDeck && !bDrifting:
    if AFanCmd > 0: AFanCmd *= GunDeckThrottleScale (0.6)
    ABrake *= GunDeckBrakeScale (0.3);  YawRateCmd *= GunDeckYawScale (0.8); RmaxDeg *= GunDeckYawScale
```

Full steer at cruise with aim held: bank 8.6 deg (23.1 without), 30.5 deg/s. In the orbit test (M12) the target's
elevation in the hull frame drops from Classic's 5.7 deg mean to 1.9 deg, well inside the +8.5 deg cannon limit.

### 3.10 Forgiving collisions (pawn presets; not modelled by the bench)

A racer will scrape platforms, so a hit should cost a little, never the run:

| Tunable | Classic | Sky Racer | Effect |
|---|---|---|---|
| ImpactMinSpeed | 4 m/s | 7 m/s | Glancing scrapes do no damage |
| ImpactDamagePerMS / ImpactMaxDamage | 6 / 500 | 4 / 350 | A 25 m/s head-on hit: 72 HP (Classic 126) |
| ImpactCooldown | 0.4 s | 0.6 s | A scrape along a wall counts once, not every few frames |
| ImpactMaxSpinKickDeg | 20 deg/s | 12 deg/s | A hit does not spin the hull off its line |
| ImpactMaxSpeedGain / ImpactMaxReboundSpeed (4e) | 5 / 2.5 m/s | 4 / 1.2 m/s | No pinball bounce |
| MinClearance / Kfloor | 4 m / 1.5 1/s | 5 m / 2.0 1/s | The floor lifts the ship over platform edges sooner |

A hit does not cancel a drift or its charge. Hits shake the pilot's camera (section 5).

### 3.11 Base fixes (BASELINE.md 4f): all included

| # | Fix | Suggested | Sky Racer | Why it differs |
|---|---|---|---|---|
| 4a-1 | bHullAxisInertia | true | true | |
| 4a-2 | bFanTorqueFeedForward | true | true | |
| 4a-3 | PitchPerG / PitchMinDeg / BoostPitchDeg (PitchMaxDeg) | 4 / -4 / 1.5 (3) | 4.5 / -5 / 1.5 (4) | A slightly deeper launch dip (-4.9 deg) reads as power |
| 4b | VertBrakeAccel / HoldBrakeAccel / LiftTauRelease | 490-784 / 1176-1470 / 0.08 | 1180 / 1960 / 0.06 | The faster climb (13.5 m/s) needs a stronger stop to stay "stops where you let go" |
| 4c | bBrakeHoldLead / BrakeFadeSpeed | true / 1000 | true / 1000 | |
| 4d | StationKeepGain / Speed / AccelMax | 1.0 / 300 / 150 | 1.0 / 300 / 150 | |
| 4e | ImpactEpisodeAccelUp / ImpactMaxReboundSpeed | 1300 / 120 | 2650 / 120 | The 4e rule: at or above the largest upward flight acceleration (2601) |
| (new) | bSkyLevelGrip | - | true | Removes the 5 m turn sink (Finding 3); a base-fix candidate for every scheme |

---

## 4. Parameter table (the preset)

Every value not listed stays at v1. "Classic" is the v1 value, which the Classic preset must restore.
`scheme_skyracer.py` (`SkyRacer.flight`, `SkyRacer.pawn`) is the same table in code.

### 4.1 Flight component, existing tunables

| Tunable | Classic | Sky Racer | | Tunable | Classic | Sky Racer |
|---|---|---|---|---|---|---|
| ThrottleTauUp / Down (s) | 0.30 / 0.45 | 0.18 / 0.30 | | AFan (cm/s²) | 1323 | 1860 |
| BoostTauUp / Down (s) | 0.15 / 0.60 | 0.08 / 0.45 | | VTop (cm/s) | 5000 | 5900 |
| LiftTau (s) | 0.25 | 0.12 | | ThrustFadeExponent | 6 | 5 |
| SteerTau (s) | 0.15 | 0.09 | | AFanBoost (cm/s²) / VTopBoost (cm/s) | 1960 / 9600 | 2550 / 10000 |
| StrafeTau (s) | 0.20 | 0.14 | | FanMax / FanMaxBoost (W per fan) | 0.68 / 1.0 | 0.95 / 1.3 |
| ClimbRate / DescendRate (cm/s) | 1200 / 1500 | 1350 / 1650 | | Kbrake (1/s) | 0.9 | 1.5 |
| Kvz (1/s) | 2.0 | 3.0 | | BrakeReverseThrottle | 0.5 | 0.4 |
| CollectiveMin / Max (W) | 0.25 / 1.9 | 0.15 / 2.1 | | StrafeSpeed (cm/s) | 1200 | 1400 |
| PodForceMax (W per pod) | 0.55 | 0.62 | | GripKlat (1/s) / GripALatMaxG (g) | 4.0 / 2.5 | 4.5 / 4.0 |
| MinClearance (cm) / Kfloor (1/s) | 400 / 1.5 | 500 / 2.0 | | BoostKlat / BoostALatMaxG | 3.0 / 2.0 | 3.5 / 3.0 |
| KpRoll / KdRoll | 6.25 / 4.5 | 9.0 / 5.4 | | Kr (1/s) / AlphaYawMax (rad/s²) | 3.0 / 1.0 | 4.5 / 1.5 |
| BankMaxDeg / BankMaxBoostDeg | 18 / 12 | 22 / 15 | | YawRateAtRest / AtMid / AtTop (deg/s) | 30 / 45 / 35 | 34 / 50 / 38 |
| BankFullSpeed (cm/s) | 2000 | 1800 | | YawRateMidSpeed / TopSpeed (cm/s) | 1500 / 4800 | 1600 / 5600 |
| StrafeBankDeg | 6 | 5 | | YawRateBoost (deg/s) | 25 | 30 |
| PitchPerG / PitchMinDeg / PitchMaxDeg | 8 / -8 / 6 | 4.5 / -5 / 4 | | RudderAuthority / RefSpeed / MaxAlpha | 0.6 / 4800 / 1.2 | 0.9 / 5000 / 1.6 |
| BoostPitchDeg / LiftPitchDeg | 3 / 3 | 1.5 / 4 | | GyroYawMax (rad/s²) | 0.5 | 0.6 |
| BoostDrainRate / RegenRate (/s) | 25 / 12 | 28 / 10 | | BoostRegenDelay (s) | 1.0 | 1.2 |
| BoostMinFuelToStart | 20 | 18 | | BoostKickDV (cm/s) | 400 | 600 |

Unused while `bSkyDrift` / `SkyGripEnergyKeep` are on, left at v1: the v1 drift set (DriftSteerThreshold,
DriftMinSpeed, DriftKlat, DriftALatMaxG, DriftEta, DriftBrakeScale, DriftBoostMinTime, DriftBoostDV, YawRateDrift,
BankMaxDriftDeg) and GripEta / BoostEta.

### 4.2 Flight component, new tunables (all v1-neutral by default)

Base fixes, with BASELINE.md's names (shared with the other schemes; create them once):

| Tunable | v1 / Classic | Sky Racer |
|---|---|---|
| bHullAxisInertia | false | true |
| bFanTorqueFeedForward | false | true |
| VertBrakeAccel (cm/s²) / HoldBrakeAccel (cm/s²) / LiftTauRelease (s) | 0 / 0 / 0 | 1180 / 1960 / 0.06 |
| bBrakeHoldLead / BrakeFadeSpeed (cm/s) | false / 0 | true / 1000 |
| StationKeepGain (1/s) / StationKeepSpeed (cm/s) / StationKeepAccelMax (cm/s²) | 0 / 300 / 150 | 1.0 / 300 / 150 |

Sky Racer (Category "Airship|Sky Racer"):

| Tunable | v1 / Classic | Sky Racer | Meaning |
|---|---|---|---|
| bSkyDrift | false | true | Section 3.2 state machine, 3.5 drift forces, 3.6 turbo (false: v1 drift). C++: not a property; the code tests `ActiveScheme == SkyRacer` (review R2) |
| SkyDriftThrottle (new, review R1) | 0 | 1.0 | While drifting and S not held, the throttle target is at least this: a drift drives at full power, W optional (0 = as designed) |
| SkyDriftEnterSteer / SkyDriftEnterSpeed (cm/s) / SkyDriftExitSpeed (cm/s) | 0.5 / 1500 / 800 | same | Entry: X + \|steer\| >= 0.5 above 15 m/s; ends below 8 m/s |
| SkyDriftPathRateMinDeg / MaxDeg (deg/s) | 24 / 46 | same | Path turn rate, counter-steer .. full in |
| SkyDriftSlipMinDeg / MaxDeg (deg) | 16 / 26 | same | Held slip angle |
| SkyDriftSlipGain (1/s) / SkyDriftPathLeadDeg (deg/s) | 3 / 10 | same | Slip hold; how far the path may lead the hull at turn-in |
| SkyDriftYawRateMaxDeg (deg/s) / SkyDriftAlphaYawMax (rad/s²) | 65 / 2.5 | same | Nose flick limits while drifting. C++: the second is the shared `DriftAlphaYawMax` (v1 0 = AlphaYawMax; Sky preset 2.5) |
| SkyDriftALatMaxG (g) / SkyDriftScrub (1/s) | 5.0 / 0.08 | same | Path force cap; slide drag |
| SkyDriftBankDeg / SkyDriftGimbalRollDeg (deg) | 24 / 4 | same | |
| SkyDriftExitTime (s) / SkyDriftExitKlat (1/s) / SkyDriftExitALatMaxG (g) / SkyDriftExitYawGain (1/s) | 0 / 8 / 5 / 6 | 0.4 / 8 / 5 / 6 | Exit snap (ExitTime 0 = off) |
| SkyChargeRateMin / Max (1/s) | 0.2 / 0.5 | same | Charge per second, counter-steer .. full in |
| SkyTier1 / 2 / 3 | 0.25 / 0.55 / 1.0 | same | Tier thresholds |
| SkyTierGrace | 0.03 | same | Server only, remote pilots |
| SkyTurboKickDV1 / 2 / 3 (cm/s) | 300 / 500 / 750 | same | |
| SkyTurboTime1 / 2 / 3 (s) | 0.5 / 0.8 / 1.2 | same | Burn length |
| SkyTurboAccel (cm/s²) / SkyTurboVTop (cm/s) | 490 / 9000 | same | Burn strength and its fade |
| SkyTurboFuel1 / 2 / 3 | 4 / 8 / 15 | same | Boost fuel per release |
| SkyChainWindow (s) / SkyChainBonus / SkyChainMax | 2.5 / 0.15 / 3 | same | |
| SkySBrakeSpeed (cm/s) / SkySBrakeTauUp / Down (s) | 0 / 0 / 0 | 300 / 0.3 / 0.08 | S = progressive brake above 3 m/s (0 = v1 reverse) |
| SkyBrakeAccelMax (cm/s²) | 0 | 1470 | Air-brake cap (0 = none). C++: the shared `BrakeMaxAccel` |
| bSkyLevelGrip / SkyGripCentripetalFF / SkyGripEnergyKeep | false / 0 / 0 | true / 0.5 / 0.85 | Section 3.4. C++: `bSkyLevelGrip` = the shared `bLevelGripForce` true + `bLevelGripAlongHeading` true |
| SkyDiveAccelPerSink (1/s) / SkyDiveMinSpeed (cm/s) | 0 / 1500 | 0.06 / 1500 | |
| SkyAimBankScale / ThrottleScale / BrakeScale / YawScale | 1 / 1 / 1 / 1 | 0.35 / 0.6 / 0.3 / 0.8 | Gun deck. C++: the shared `GunDeckBankScale` / `GunDeckThrottleScale` / `GunDeckBrakeScale` / `GunDeckYawScale` |
| SkyBoostMinBurst (s) | 0 | 0.5 | |
| SkyFXDriftPulse / SkyFXTurboThrust / SkyFXChargeGlow1 / 2 / 3 | 0 / 0 / 0 / 0 / 0 | 0.25 / 0.4 / 0.25 / 0.45 / 0.65 | Cosmetic (section 6), **guess** |

### 4.3 Pawn

| Tunable | Classic | Sky Racer | | Tunable | Classic | Sky Racer |
|---|---|---|---|---|---|---|
| CameraArmLength (cm) | 6500 | 5400 | | ImpactMinSpeed (cm/s) | 400 | 700 |
| CameraDefaultPitch (deg) | -12 | -8 | | ImpactDamagePerMS | 6 | 4 |
| CameraBoom TargetOffset Z (cm) | 900 | 650 | | ImpactMaxDamage | 500 | 350 |
| CameraBoom CameraLagSpeed / RotationLagSpeed | 5 / 7 | 6.5 / 10 | | ImpactCooldown (s) | 0.4 | 0.6 |
| CameraBoostArmExtra (cm) | 1000 | 1200 | | ImpactMaxSpinKickDeg | 20 | 12 |
| RecenterDelay (s) / MinSpeed (cm/s) / Speed (1/s) | 1.5 / 800 / 2 | 0.6 / 500 / 4 | | ImpactMaxSpeedGain (cm/s) | 500 | 400 |
| BaseFOV / SpeedFOVExtra (deg) | 85 / 10 | 82 / 18 | | ImpactMaxReboundSpeed (cm/s) | 250 | 120 |
| SpeedFOVStart / Full (cm/s) | 2000 / 4800 | 1500 / 5500 | | ImpactEpisodeAccelUp (new, cm/s²) | = ImpactEpisodeAccel (2500) | 2650 |
| BoostFOVExtra / AimFOVOffset (deg) | 12 / -15 | 14 / -14 | | FOVInterpSpeed (1/s) | 4 | 6 |

New pawn tunables (Category "Airship|Sky Racer", all v1-neutral by default):

| Tunable | v1 / Classic | Sky Racer | Meaning |
|---|---|---|---|
| SkyLookIntoTurnTime (s) / SkyLookIntoTurnMaxDeg | 0 / 14 | 0.3 / 14 | Auto-follow aims at ship yaw + this x the commanded turn rate |
| SkyCamSlipShare | 0 | 0.35 | ... minus this share of the slip (the slide reads) |
| bSkyCamYawRateFF | false | true | The control yaw also turns at the commanded rate (no follow lag) |
| SkyCamDivePitchPerMS (deg per m/s) / SkyCamDivePitchMaxDeg | 0 / 8 | 0.4 / 8 | Look down into a dive |
| SkyCamRollShare / SkyCamRollMaxDeg | 0 / 6 | 0.25 / 6 | Camera roll with the hull bank. C++: shared `CameraRollPerBank` / `CameraRollMaxDeg` (`CameraRollInterpSpeed` 0 = none) |
| SkyShakeRotDeg / SkyShakeFrequency (Hz) / SkyShakeDecay (1/s) | 0 / 14 / 1.8 | 1.2 / 14 / 1.8 | Trauma shake (0 = off). C++: shared `ShakeRotDeg` / `ShakeFrequency` / `ShakeDecay` (`ShakeLocCm` 0) |
| SkyShakeBoost / SkyShakeTurbo1 / 2 / 3 / SkyShakeHitMax | 0.35 / 0.3 / 0.45 / 0.65 / 0.8 | same | Trauma added. C++: `FeedbackBoostStart.Trauma`, `FeedbackTurbo1/2/3.Trauma`, `ShakeHitMax` (`ShakeHitPerMS` 0.05 per m/s above ImpactMinSpeed) |
| SkyShakeDriftBase / SkyShakeDriftPerCharge | 0.08 / 0.12 | same | Trauma floor while drifting. C++: shared `DriftTraumaBase` / `DriftTraumaPerCharge` |
| SkyFOVBoostKick / SkyFOVTurboKick1 / 2 / 3 (deg) / SkyFOVKickDecay (1/s) | 0 / 0 / 0 / 0 / 2.5 | 6 / 4 / 7 / 10 / 2.5 | FOV punches. C++: `FeedbackBoostStart.FOVKickDeg`, `FeedbackTurbo1/2/3.FOVKickDeg`, `FOVKickDecay` |
| SkyFOVMax (deg) | 0 (= 170) | 112 | FOV clamp. C++: shared `FOVMaxDeg` |
| SkyTurboArmExtra (cm) | 0 | 600 | Arm grows with the turbo burn (stays a Sky Racer pawn property) |
| bSkyRumble / SkyRumbleDriftBase / PerCharge / SkyRumbleTurbo1 / 2 / 3 / SkyRumbleBoost | false / 0.15 / 0.35 / 0.5 / 0.75 / 1.0 / 0.6 | true / same | Gamepad rumble. C++: shared `RumbleScale` (1 = on), `DriftRumbleBase` / `DriftRumblePerCharge`, `FeedbackTurbo1/2/3.Rumble` (0.25 s), `FeedbackBoostStart.Rumble` (0.2 s) |

Review R3: the camera roll, shake, FOV kicks and rumble above are the shared feedback properties of
`IMPLEMENTATION_PLAN.md` 1.10 (one implementation for the three schemes); the values are the designer's.

No anim instance value changes; every rig variable stays inside RIG_CONTRACT section 5.

---

## 5. Camera (pilot's machine, `UpdateCamera`)

* **Placement**: a lower, closer chase: arm 54 m (Classic 65), pitch -8 deg (Classic -12), look-at 6.5 m above the
  origin (Classic 9). Lag 6.5/s position and 10/s rotation (Classic 5 and 7), so it trails less but still trails: about
  9 m at cruise, more on boost and turbo (the arm adds 12 m at full boost and 6 m at a fresh turbo).
* **Auto-follow** (v1's recentre, generalised; Classic's values make it exactly v1). After 0.6 s without look input,
  above 5 m/s and not aiming:
  ```
  Rate   = Flight->GetPilotYawRateCmdDeg()        // this machine's own shaped steer / drift state, no latency
  Look   = clamp(SkyLookIntoTurnTime * Rate, +-SkyLookIntoTurnMaxDeg)
  Slip   = Vb.X > 3 m/s ? atan2(-Vb.Y, Vb.X) : 0  // the hull copy on this machine
  Target = ActorYaw + Look - SkyCamSlipShare * Slip;   TargetPitch = CameraDefaultPitch - min(SkyCamDivePitchPerMS * dive m/s, max)
  if bSkyCamYawRateFF: Control.Yaw += Rate * Dt
  Control.Yaw += Normalize(Target - Control.Yaw) * (1 - exp(-RecenterSpeed * Dt)); the same for the pitch
  ```
  The view looks 6 deg into a steady full turn (Classic looks 22 deg outside it). For a client at 100 ms it starts
  turning 1 frame after the key and leads by up to 11 deg while the hull's own turn is still in flight, so the lag hides
  behind the camera. In a drift the view sits on the nose, about 26 deg inside the velocity, so the slide shows.
* **Roll**: the camera component rolls 0.25 x the hull bank (max 6 deg).
* **FOV**: 82 + 18 x speed fraction (15-55 m/s) + 14 x boost - 14 when aiming, interpolated at 6/s, plus punches
  (+6 on a boost start, +4 / +7 / +10 on a T1 / T2 / T3 release, decaying at 2.5/s). Clamped at 112 deg.
* **Shake**: a trauma value (0..1) adds Perlin jitter of 1.2 deg x trauma² to the camera's relative pitch, yaw and roll.
  It decays at 1.8/s. Kicks: boost start +0.35, turbo +0.3 / 0.45 / 0.65, hull hit up to +0.8. While drifting it never
  falls below 0.08 + 0.12 x charge, a rumble of the slide.
* **Broadside side**: unchanged rule (the aim point's hull-local Y). With look-into-turn the facing side in auto-follow
  is the inside of the turn; the HUD shows it. Free look and aim behave as in Classic.

## 6. Feedback (no new assets)

| Event | Thrusters / fans (Niagara `Thrust` 0..1.5, `Boost` 0..1) | Rig (from the cosmetic state) | Camera / rumble |
|---|---|---|---|
| Drift held | Rear pods `Thrust` + 0.25 x charge, flickering at 4 / 6 / 9 Hz by tier; all six `Boost` = the charge glow (0.3 x charge before T1, then 0.25 / 0.45 / 0.65 + 0.1 flicker at T3): the exhaust heats up as it charges | Nozzles roll 4 deg into the slide; wheel and rudder follow the steer (hard over at full steer, back with a counter-steer); rear petals flicker with the thrust | Trauma floor, low rumble rising with the charge |
| Tier reached | The glow steps up | | HUD tick flash (section 7) |
| Release (turbo) | All `Boost` = 1 fading with the burn; pods `Thrust` + 0.4 x burn; fans `Thrust` = max(own, burn) | Petal flare spike (thrust alpha up) | FOV punch, shake by tier, rumble pulse 0.25 s |
| Boost start | (as v1) | | FOV +6, shake 0.35, rumble 0.2 s |
| Hull hit | | | Shake up to 0.8 |

The pulse values are **guesses** to tune in PIE; all of them stay inside the rig and FX ranges (thrust clamped to 1.5).

## 7. HUD (`UAirshipHUDWidget`, pilot's machine)

A **TURBO** row between BOOST and the speed line, only in Sky Racer. The panel grows from 136 to 162 units tall.

* Label `DRIFT` (ink tag while drifting, like BOOST). The bar fills with the charge. Ink ticks mark T1 (25 %) and
  T2 (55 %); the fill colour shows the tier: ink grey (none), BoostColor blue (T1), ReloadColor orange (T2), HullColor
  red (T3).
* The value field shows the tier as `I`, `II` or `III`. When a chain is live (a release less than 2.5 s ago) it shows
  `x2`, `x3` or `x4` next to the tier.
* On a release the label becomes a `TURBO` tag in the tier colour. The bar then shows the burn draining (TurboAlpha),
  and the panel outline flashes the tier colour for 0.3 s.
* Values come from the pilot's own cosmetic state, so the HUD is predicted (no latency).

## 8. Multiplayer notes

* **Nothing new crosses the network.** The drift is the brake bit plus the steer, which v1 already sends, already
  replicates in `RepInput` and already adds to `SameControls`. Every machine runs the same state machine on the
  controls it has, as it does for v1's `bDrifting`. There is no new RPC and no new `FAirshipPilotInput` field.
* **Client pilot at 100 ms each way** (bench): the HUD, FX, rig and camera react on frame 0. The server starts the
  drift on frame 4 (1 frame + 100 ms). The hull shows the drift on the pilot's screen on frame 9 (0.30 s). The release
  works the same way: the pilot sees the turbo flash at once and the speed about 0.3 s later.
* **Tier agreement**: the server measures the same hold length, so it pays the tier the HUD showed. Over 60 hold
  lengths (0.4-2.4 s in 1-frame steps), with no grace, 0 differed. The server adds a 0.03 charge grace for remote
  pilots, about 2 frames at full steer, to absorb packet jitter (the bench has none). With it, 3 of 60 releases right
  at a threshold pay one tier more than shown, and never less. A pilot is never cheated, sometimes rewarded.
* **Speed gate**: the drift entry and exit use this machine's forward speed (15 / 8 m/s). The pilot's view lags the
  server's, so the two can disagree for a few frames when a drift starts right at 15 m/s. Cruise is 56 m/s, so in
  practice this happens only out of a near stop.
* **Observers** see the drift FX about half a round trip late, from `RepInput`.
* **Scheme switch or exit mid-drift**: `ResetSchemeState` on every machine: the scheme apply (BeginPlay,
  `SetControlScheme`, `OnRep_ControlScheme`), `OnRep_PilotCharacter` (board / exit, every machine; review R4: the
  designed `PossessedBy` / `UnPossessed` run only on the server, so the client pilot's and the observers' state never
  reset), `ResetInput` on the server and death. A drift in progress is dropped without a turbo.
* **The turbo kick** is a server impulse noted with `NoteFlightKick`, so the impact cap never eats it.
* **Late joiners** start with empty drift state; the first drift after joining shows correctly.

---

## 9. Predicted metrics (bench) vs Classic

`python3 metrics.py skyracer`, `python3 skyracer_checks.py`. M11 and M12 rows are the official seed (7). Section 9.3
has the 5-seed means.

### 9.1 M1-M12

| Metric | Classic | Sky Racer | Sky Racer target band |
|---|---|---|---|
| M1 t80 / t63 | 3.33 / 2.63 s | 2.87 / 2.17 s | t80 2.3-3.0 s |
| M1 speed at 2 / 4 s | 22.6 / 44.4 m/s | 33.0 / 54.0 m/s | 28-36 at 2 s |
| M2 top steady / boost peak | 48.0 / 88.1 m/s | 56.4 / 92.5 m/s | 54-58 m/s |
| M2 boost ratio / duration / t90 | 1.84 / 3.63 s / 3.0 s | 1.64 / 3.23 s / 2.2 s | 1.55-1.75, 3-4 s |
| M3 stop time / distance | 2.17 s / 38.6 m | 2.87 s / 72.4 m | 2.5-3.2 s |
| M3 peak / mean decel | 4.31 / 2.26 g | 2.52 / 2.00 g | peak 1.8-2.6, mean 1.8-2.3 g |
| M3 coast to half speed | 10.8 s | 10.7 s | 8-15 s |
| M4 turn rate, t63 / t90, overshoot | 35.1 deg/s, 0.50 / 0.90 s, 2.2 % | 38.0 deg/s, 0.30 / 0.60 s, 1.5 % | 36-42, <= 0.35 / 0.7 s, <= 5 % |
| M4 bank / slip at 8 s / height lost | 17.8 / 19.6 deg / 5.15 m | 23.1 / 3.3 deg / 0.0 m | 18-25 / <= 8 / <= 1 m |
| M5 U-turn time / diameter / speed kept | 5.6 s / 181 m / 106 % | 5.0 s / 173 m / 101 % | 4.5-5.5 s |
| M6 pitch: drive min / boost min / brake max | -16.6 / -20.2 / +7.5 deg | -4.9 / -5.8 / +3.9 deg | -3..-6 / -4..-7 / +2..+5 |
| M7 climb / sink | 12.0 / 15.0 m/s | 13.6 / 16.5 m/s | 13-15 / 15-18 |
| M7 +30 m step: rise, overshoot, \|vz\| 1 s / 2 s, error 5 s | 3.33 s, 12.1 m, 5.84 / 0.57 m/s, 11.5 m | 2.93 s, 5.35 m, 0.01 / 0.04 m/s, 5.3 m | overshoot <= 6 m (the stopping distance), \|vz\| 1 s <= 1 |
| M8 strafe t90 / speed | 0.87 s / 12.3 m/s | 0.70 s / 14.2 m/s | <= 0.8 s / 13-15 |
| M9 drift slip 1 / 2 / 3 s | 15 / 42 / 63 deg | 8 / 25 / 24 deg | 20-30 at 2 s, held (<= 3 deg change 2-3 s) |
| M9 drift turn rate / speed kept / exit kick (paid) | 49.8 deg/s / 103 % / 4.8 (6.0) m/s | 55.8 deg/s (path 46) / 96.5 % / 8.4 (7.5) m/s | >= 90 %, 5-10 m/s |
| M10 host: cosmetics / turn on screen / speed on screen | 0 / 2 / 1 frames | 0 / 1 / 0 frames | <= 1 |
| M10 client 100 ms: cosmetics / server turn / screen turn / screen speed | 0 / 6 / 9 / 8 frames | 0 / 5 / 8 / 7 frames | screen <= 8 |
| M11 precise 0 ms: time, missed, line error mean / max | 60.5 s, 0, 2.2 / 4.6 m | **49.1 s**, 0, 2.8 / 7.6 m | 0 missed, >= 12 % faster |
| M11 precise 100 ms | 62.7 s, 0, 2.4 / 4.6 m | **49.1 s**, 0, 2.4 / 7.7 m | 0 missed |
| M11 sloppy 0 ms: time, missed, line error, reversals | 61.6 s, 1 (S5), 6.4 / 10.4 m, 9.7/min | 49.6 s, 1 (S5), 5.3 / 11.5 m, 48/min | <= 1 missed |
| M11 sloppy 100 ms | 78.2 s, 6 (S2-S5, H1, H2), 40.5 / 115 m, 13.8/min | **55.7 s, 3 (S3, S4, S5)**, 8.8 / 28.1 m, 33/min (as designed: 52.3 s, 2) | <= 2 missed: one over since review R1 |
| M12 precise 0 / 100 ms: in arc, firing solution | 100 / 100 % | 100 / 100 % | >= 90 % |
| M12 sloppy 0 ms: in arc / solution / shots | 69 / 69 % / 37 | **100 / 100 % / 40** | |
| M12 sloppy 100 ms: in arc / both / solution / shots | 37 / 30 / 34 % / 21 | **100 / 90 / 84 % / 39** | in arc >= 80 %, solution >= 60 % |
| M12 elevation mean / max (precise) | 5.7 / 6.1 deg | 1.9 / 2.9 deg | |

All 39 Sky Racer target bands are met (`skyracer_checks.py` section 1).

### 9.2 Drift and turbo (section 3) and feedback timing

| Check | Result |
|---|---|
| Tier times, full in / centred / half counter | T1-T2-T3 at 0.53-1.13-2.03 s / 0.73-1.6-2.87 s / 0.9-2.0-3.63 s |
| Turbo kicks T1 / T2 / T3, chain links 0-1-2 | 3.0 / 5.0 / 7.5 m/s; a T2 chain pays 5.0 / 5.75 / 6.5 m/s |
| 6 s held drift | 46 deg/s path, 26 deg slip, 56.4 -> 54.0 m/s, no height change |
| Boost tap (1 frame) | 0.50 s burst, -21 fuel, 56 -> 73 m/s |
| 1.2 s drift: W held / W let go (A/D + X) / S held (review R1) | the same 49.4 deg of course, tier 2, 5.0 m/s kick for W held and W let go (as designed, letting go of W lost 3 m/s by the release); S + X: 56 -> 48 m/s, tier 2 |
| Camera in a full turn (view minus hull yaw on the pilot's screen) | host +6 deg; client +4 deg at 0.2 s, +11 at 0.7 s, +7 at 3 s (Classic -21..-22) |
| Client 100 ms: drift start on HUD / server / hull on screen | frame 0 / 4 / 9 |

### 9.3 Gate course over 5 seeds (7, 1, 2, 3, 4)

| | Classic | Sky Racer |
|---|---|---|
| precise 0 ms: time, missed, line error mean / max | 60.6 s, 0, 2.1 / 4.6 m | 49.1 s, 0, 2.8 / 7.6 m |
| precise 100 ms | 62.6 s, 0, 2.4 / 4.9 m | 49.2 s, 0, 2.4 / 7.7 m |
| sloppy 0 ms: time, missed (per seed), reversals | 61.2 s, 1.6 (1 1 1 3 2), 13/min | 49.6 s, 1.2 (1 2 2 1 0), 44/min |
| sloppy 100 ms | 72.9 s, 5.6 (6 4 5 7 6), 16/min | 52.9 s, 2.8 (3 1 4 4 2), 30/min (as designed: 52.1 s, 2.4 (2 1 4 3 2)) |
| Sky Racer precise flown on grip only (same ship, no drift, line planned for grip) | | 55.3 s (0 ms), 56.3 s (100 ms), 0 missed |

Skill ceiling: the precise bot uses three mini-turbos through the slalom (T1-T2-T2 at 0 ms, chained once; T2-T2-T2 at
100 ms, chained twice). The drift technique is worth 6.2-7.1 s (11-13 %) over flying the same ship on grip. The sloppy
pilot's misses are gates passed 0-7 m outside the frame on the outside of slalom turns (a late release under lag).

Bot gains: `course.tune_bot`'s stage 1 grid, unchanged, picks course 1.6, rate_damp 0.6, ct 0.5, lag 0.35 (score
128.8). Stage 2 adds turn_frac 1.0 / 1.1 to the grid, because the planner reads only the grip turn table and the
drift turns faster. It picks margin 5, turn_frac 1.1 and exit_lead 0.9. `python3 skyracer_checks.py --tune`
reproduces this. The drift keys (drift_on 0.9, drift_off 0.8, drift_min_hold 0.25 s, drift_rearm 0.6 s) come from
5-seed sweeps. The broadside bot uses Classic's heading gains (combat_course 0.7) and holds aim.
**Sensitivity:** the tuned course gain of 1.6 makes the sloppy bot's on/off keys chatter (44 reversals/min). With
course 1.0 the result is precise 49.3 / 50.1 s (0 missed) and sloppy 1.0 / 2.2 missed at 19 / 35 reversals/min
(5 seeds). The JSON keeps the tuned 1.6.

---

## 10. Known risks

1. **Weight.** The turn uses up to 4 g of hidden side force and the drift up to 5 g, more than Classic's 2.5 g. The
   big-ship read rests on the visuals: a 23-24 deg bank, a held 16-26 deg slip, the trailing camera, visible spool-up.
   This needs a PIE look, ideally from a deck passenger's view too. If it reads too nimble, lower YawRateAtTop and
   SkyDriftPathRateMaxDeg together (the planner's speeds follow).
2. **Inertia fix first.** KpRoll 9 and the snappier yaw assume base fix 4a-1. If PIE's `GetInertiaTensor()` log differs
   from `hull_mass.json`, retune the roll pair before judging the feel.
3. **Exit swing.** Releasing a drift adds 16-34 deg of course as the slide straightens along the nose. Players must
   learn to "let go when the nose points down the exit"; a late release (lag, reaction) runs wide. This is where the
   sloppy bot loses its 1-4 gates at 100 ms. SkyDriftExitYawGain (6) and SkyDriftSlipMaxDeg (26) are the knobs.
4. **Sloppy chatter** of 44-48 reversals/min comes mostly from the tuned bot gains: with course gain 1.0 it falls to
   19/min (section 9.3). A keyboard pilot who over-corrects will still feel the faster turn; watch for it in PIE.
5. **The brake is longer** than Classic's: 72 m from 56 m/s against 39 m from 48 m/s. That is by design (a 2 g cap that
   reads as weight, with the drift as the cornering tool). A head-on obstacle needs X about 1.3 s earlier.
6. **Deck passengers** feel 4-5 g lateral steps when a drift starts or ends. The bench has no riders. Check in PIE that
   the riders' based movement holds (BASELINE 4d notes the CMC push path).
7. **Speed peaks**: boost to 92 m/s, a boost tap to 73 m/s, T3 to 63 m/s. Impact damage is softened (4 per m/s above
   7 m/s, cap 350), but the hard speed cap (110 m/s) is still the only ceiling.
8. **FX cue values** (drift pulse, charge glow, turbo spike) are untested guesses. The NS_* systems only read
   `Thrust` and `Boost`, so how the glow looks depends on those systems' curves.
9. **Bench limits**: no contacts, no client smoothing (PIE showed 0-2 frames more on the client screen), no camera
   FOV / arm / shake. The predicted feel numbers are relative to Classic on the same bench.
10. **The keyboard drift chord** (fixed by review R1). As designed, the signature move needed W + D + X at once on
   the left hand (a right drift crossed the ring finger under the middle finger), and a drift with W let go lost 3 m/s
   in 1.2 s. A drift now drives at full power unless S is held, so it is A or D + X. The bench bot presses three keys
   without effort, so it cannot show the gain; its sloppy course at 100 ms went from 2.4 to 2.8 gates missed (5-seed
   mean; official seed 2 → 3), because it had been drifting with W accidentally released by its key model.
   `SkyDriftThrottle = 0` restores the designed behaviour.

---

## 11. C++ change list

**`IMPLEMENTATION_PLAN.md` is the authoritative, ordered change list** (shared framework in its section 1, Sky Racer
in 2.2). This section is the designer's list, corrected by the review; where they differ, the plan wins (shared names
for the brake cap, level grip, drift yaw cap, gun deck and feedback; `ActiveScheme` in place of `bSkyDrift`; reset
hooks; the HUD layout refresh).

File shorthand as BASELINE.md (`FC`, `Pawn`, `Types`, `HUD`, `Sub`). The contract parts (the enum, `ControlScheme`,
`SetControlScheme`, OnRep, the preset application, `Aura.Airship.Scheme`, the telemetry fields) are shared work. The
items below are what Sky Racer needs on top of that. Every new tunable defaults to its v1 value, so with
`ControlScheme == Classic` the code paths reduce to v1 line for line.

### 11.1 `Types.h`

```cpp
// FAirshipCosmeticState: add (every machine, from ShapeControls / UpdateCosmetic)
int8  DriftDir = 0;          // -1, 0, +1
float DriftCharge = 0.f;     // 0..1
uint8 DriftTier = 0;         // tier of DriftCharge (no grace)
float TurboAlpha = 0.f;      // 1 -> 0 over the burn
uint8 TurboTier = 0;         // tier of the last release
uint8 TurboChain = 0;        // live chain links (0..3)
uint8 TurboEventCount = 0;   // +1 per release on this machine (wraps): HUD / camera / rumble edge detection
float FXBoost = 0.f;         // Niagara Boost user parameter (v1: = Boost)
float FXFanThrust = 0.f;     // floor for the fans' Thrust parameter (turbo burn)

// FAirshipFlightTelemetry: the contract fields (Scheme, ThrottleOrder, DriftCharge, bHeadingTargetActive,
// HeadingTargetDeg, bFreeLook) plus these Sky Racer extras (BlueprintReadOnly, Category "Airship"; not contract):
UPROPERTY(BlueprintReadOnly, Category = "Airship") int32 DriftDir = 0;
UPROPERTY(BlueprintReadOnly, Category = "Airship") int32 DriftTier = 0;
UPROPERTY(BlueprintReadOnly, Category = "Airship") float TurboAlpha = 0.f;
UPROPERTY(BlueprintReadOnly, Category = "Airship") int32 TurboChain = 0;
```

`FAirshipPilotInput` is **unchanged**.

### 11.2 `FC.h`

* The base-fix UPROPERTYs of BASELINE.md 4f, if they are not there yet: `bHullAxisInertia`, `bFanTorqueFeedForward`,
  `VertBrakeAccel`, `HoldBrakeAccel`, `LiftTauRelease`, `bBrakeHoldLead`, `BrakeFadeSpeed`, `StationKeepGain`,
  `StationKeepSpeed`, `StationKeepAccelMax` (defaults in section 4.2).
* Every Sky Racer tunable of section 4.2, as `UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship|Sky Racer")`
  with the v1 default in the table. Floats except `bSkyDrift`, `bSkyLevelGrip` (bool) and `SkyChainMax` (int32). Use
  ClampMin 0 where it makes sense, but no ClampMax: `Aura.Airship.Set` skips the metadata anyway.
* Public:
  ```cpp
  /** Clears the scheme-local runtime state (drift, charge, chain, turbo, S-brake, exit window, burst timers). */
  void ResetSchemeState();
  /** The turn rate (deg/s, + right) this machine's own shaped controls command now: drift path rate or grip rate. */
  float GetPilotYawRateCmdDeg() const;
  /** Grip full-steer turn rate (deg/s) at |forward speed| (cm/s): the YawRateAtRest/AtMid/AtTop table. */
  float GripYawRateDeg(float AbsForwardSpeed) const;
  ```
* Private runtime state (all reset by `ResetSchemeState`, and by `ResetInput` and `SetFlightEnabled`): `double SkyClock`,
  `int8 SkyDriftDir`, `float SkyCharge`, `float SkyDriftTime`, `uint8 SkyChain`, `double SkyLastReleaseTime = -1000`,
  `uint8 SkyTurboTier`, `float SkyTurboLeft`, `float SkyTurboTotal = 1`, `uint8 SkyTurboEvent`, `uint8 SkyTurboChain`,
  `uint8 SkyTurboEventCount`, `float SkyExitLeft`, `float SkySBrake`, `float SkyBrakeAmount`,
  `double SkyBoostStartTime = -1000`, `double SkyLocalBoostStartTime = -1000`.

### 11.3 `FC.cpp`

| Function | Change |
|---|---|
| `ResetSchemeState` (new) | Zero every field above; `SkyLastReleaseTime = SkyBoostStartTime = SkyLocalBoostStartTime = -1000`. Called from `ResetInput`, `SetFlightEnabled` and the pawn (11.4). |
| `GripYawRateDeg` (new) | Lines 787-790 of `ApplyForces`, moved into a helper (the same lerps); `ApplyForces` calls it. |
| `GetPilotYawRateCmdDeg` (new) | `if (SkyDriftDir) return Dir * Lerp(SkyDriftPathRateMinDeg, SkyDriftPathRateMaxDeg, (Clamp(ShSteer * Dir, -1, 1) + 1) / 2);` otherwise `ShSteer * Lerp(GripYawRateDeg(Abs(Cosmetic.ForwardSpeed)), YawRateBoost, ShBoost) * (bShAiming ? SkyAimYawScale : 1)`. |
| `UpdateBoostServer` | Section 3.7 latch at the top (`Now` = world time); set `SkyBoostStartTime = Now` when `bBoostActive` turns on. |
| `UpdateFlight` | The client gate (lines 450-462): the same latch with `SkyLocalBoostStartTime` and the client's world time. `!bFlightEnabled` branch: also `ResetSchemeState()`. |
| `ShapeControls` | When `bSkyDrift`: section 3.2, then section 3.3 (the S-brake ramp, `SkyBrakeAmount`, `bShBrake`, the throttle target with BrakeFadeSpeed), then the v1 filters, with `LiftTauRelease` (4b-3: the release time constant when the lift target is smaller in size and on the same side). When `bSkyDrift` is false: v1, plus 4b-3 and 4c-2 when their tunables are set. |
| `ComputeGimbals` | After the roll line: `if (bSkyDrift && SkyDriftDir) Roll += SkyDriftGimbalRollDeg * SkyDriftDir;` before the cone clamp. |
| `ApplyForces`, forward | `VH = Size2D(V)`; `bSkyDrifting = bSkyDrift && SkyDriftDir != 0`; the thrust fade uses `bSkyDrifting ? VH : Vf`; `ADrag` / `ADragPath` per section 3.5; `ABrake` per section 3.3 (cap, x `SkyBrakeAmount`). `ADrag`, `ABrake` and `AFanCmd` become non-const. |
| `ApplyForces`, vertical | BASELINE 4b-1/2 and 4c-1 exactly as `baseline_sim.py` 330-356: the stop lead, the sqrt hold limit, the brake-press lead, and `AVert` added to `ACom.Z`. |
| `ApplyForces`, attitude | `BankDeg` per section 3.5 while drifting; `if (bShAiming) BankDeg *= SkyAimBankScale`. The gun-deck scales of section 3.9 on `AFanCmd` / `ABrake`, before `ACmd`. `TauX` / `TauY` from the hull-axis tensor when `bHullAxisInertia` (BASELINE 4a fix 1 code). |
| `ApplyForces`, mixing | 4a-2 fan feed-forward when `bFanTorqueFeedForward` (BASELINE 4a fix 2: `TotalEst` from the collective, `TauFan` at the two fan points, subtracted from `BAttitude`). |
| `ApplyForces`, yaw | Grip: `RmaxDeg = GripYawRateDeg(AbsVf)`, then v1's drift / boost lerps; `if (bShAiming && !bSkyDrifting) YawRateCmd *= SkyAimYawScale`. Drift: section 3.5 (`PathRate`, `SlipTarget`, `YawRateCmd`, the path limiter, `AlphaYawMax`, `RudderCap`). Exit window: `YawRateCmd -= SkyDriftExitYawGain * DegreesToRadians(SlipDeg)`. `TauZ` / `Izz` from the hull tensor when `bHullAxisInertia`. |
| `ApplyForces`, lateral | Drift: the path force of section 3.5 (`PathN`, `APhys` from `PodForceWorld[]` and `Q.RotateVector(FanDir * FanForce[f])`, `APath`), `AGrip = ARedirect = 0`. Grip: section 3.4. The v1 drift-kick block runs only when `!bSkyDrift`. |
| `ApplyForces`, extras | Turbo kick, fuel and burn (section 3.6), `ADive` (3.8), `AKeepF` (BASELINE 4d, `baseline_sim.py` 462-467). |
| `ApplyForces`, apply | `ACom = GripDir * AGrip + Right * WindLat + Fwd * ((bSkyDrifting ? 0 : ADrag) + ABrake + ARedirect + ATurbo + ADive + AKeepF) + PathN * APath + HorizVelDir * ADragPath + FVector(0, 0, AVert)`, then the hard cap as v1. |
| `UpdateCosmetic` | Fill the new cosmetic fields. `DriftTier = TierOf(SkyCharge)`, `TurboAlpha = SkyTurboLeft / SkyTurboTotal`, `TurboChain = SkyChain`. Pulses (section 6): rear pods (2, 3) `PodThrustAlpha += SkyFXDriftPulse * SkyCharge * (0.75 + 0.25 * Sin(2 pi f SkyClock))` with f = 4 / 6 / 9 Hz by tier; all pods `+= SkyFXTurboThrust * TurboAlpha`; clamp 0..1.5. `FXBoost = Max(ShBoost, ChargeGlow, TurboAlpha)` with ChargeGlow = 0.3 x charge (tier 0) or SkyFXChargeGlow1 / 2 / 3 (+ 0.1 Sin(2 pi 8 SkyClock) at T3) while drifting; `FXFanThrust = TurboAlpha`. With the FX tunables at 0 (v1): `FXBoost = ShBoost`, no pulses. |
| `FillTelemetry` | `DriftCharge = bSkyDrift ? SkyCharge : 0`, `ThrottleOrder = -2`, `bHeadingTargetActive = false`, `HeadingTargetDeg = 0`, `bFreeLook = true`; extras `DriftDir`, `DriftTier`, `TurboAlpha`, `TurboChain`. (`Scheme` is filled by the pawn, which owns `ControlScheme`.) |

### 11.4 `Pawn.h` / `Pawn.cpp`

* **Preset**: the Sky Racer row of the compiled-in preset table = sections 4.1-4.3. That covers the flight component,
  the pawn, `CameraBoom->TargetOffset.Z`, `CameraLagSpeed` and `CameraRotationLagSpeed`. Then `OnTuningChanged()`.
* **Reset points**: call `Flight->ResetSchemeState()` and reset the pawn's own Sky state (`SkyShakeTrauma`,
  `SkyFOVKick`, `bSkyWasBoosting`, `SkyLastTurboEventCount = Cosmetic.TurboEventCount`, stop the rumble handle) when the
  scheme is applied (BeginPlay, `SetControlScheme`, OnRep), in `OnRep_PilotCharacter` (every machine: board and
  exit; review R4, since `PossessedBy` / `UnPossessed` only run on the server) and in `HandleDeath`. If the ship HUD
  is up when the scheme changes, the pawn re-applies its viewport slot at the new size with
  `UGameViewportSubsystem::SetWidgetSlot` (`IMPLEMENTATION_PLAN.md` 1.11; hiding and re-showing it would flash the
  on-foot overlay for a frame).
* **New UPROPERTYs**: section 4.3's new table (Category "Airship|Sky Racer", v1-neutral defaults), plus
  `ImpactEpisodeAccelUp` (BASELINE 4e) if it is not there yet.
* **Private state**: `float SkyShakeTrauma`, `float SkyFOVKick`, `float SmoothedFOV` (initialise from
  `Camera->FieldOfView` at BeginPlay and on a camera reset), `bool bSkyWasBoosting`, `uint8 SkyLastTurboEventCount`,
  `FDynamicForceFeedbackHandle SkyDriftRumble = 0`.
* **`UpdateCamera`**:
  1. Events. Boost start = the rising edge of `Flight->GetCurrentControls().IsBoost()`: trauma += SkyShakeBoost, FOV
     kick += SkyFOVBoostKick, rumble (SkyRumbleBoost, 0.2 s, large motors). Turbo release =
     `C.TurboEventCount != SkyLastTurboEventCount`: trauma += SkyShakeTurbo<T>, kick += SkyFOVTurboKick<T>, rumble
     (SkyRumbleTurbo<T>, 0.25 s, large motors).
  2. The auto-follow block of section 5 in place of lines 1581-1587. With `SkyLookIntoTurnTime = SkyCamSlipShare =
     SkyCamDivePitchPerMS = 0` and `bSkyCamYawRateFF = false` it is exactly v1's recentre.
  3. Arm target `+ SkyTurboArmExtra * C.TurboAlpha`.
  4. FOV: `SmoothedFOV = FInterpTo(SmoothedFOV, TargetFOV, Dt, FOVInterpSpeed)`; `SkyFOVKick *= Exp(-SkyFOVKickDecay * Dt)`;
     `Camera->SetFieldOfView(Clamp(SmoothedFOV + SkyFOVKick, 20, SkyFOVMax > 0 ? SkyFOVMax : 170))`.
  5. Shake and roll: `SkyShakeTrauma = Max(Max(0, SkyShakeTrauma - SkyShakeDecay * Dt), C.DriftDir ? SkyShakeDriftBase + SkyShakeDriftPerCharge * C.DriftCharge : 0)`;
     `J = SkyShakeRotDeg * Square(SkyShakeTrauma)`; with `T = Now * SkyShakeFrequency`, set
     `Camera->SetRelativeRotation(FRotator(J * PerlinNoise1D(T + 11.3), J * PerlinNoise1D(T + 47.1), Clamp(SkyCamRollShare * GetActorRotation().Roll, +-SkyCamRollMaxDeg) + J * PerlinNoise1D(T + 83.9)))`.
     All zero in Classic, which leaves (0, 0, 0) as today.
  6. Rumble while drifting (`bSkyRumble`): start or update `SkyDriftRumble = PC->PlayDynamicForceFeedback(SkyRumbleDriftBase + SkyRumbleDriftPerCharge * C.DriftCharge, -1, false, true, false, true, Start or Update, SkyDriftRumble)`;
     stop it when the drift ends.
* **`OnHullHit`**: before the authority return, if `IsLocallyControlled()`:
  `SkyShakeTrauma = Min(1, SkyShakeTrauma + Clamp(NormalImpulse.Size() / Mass / 2000, 0, SkyShakeHitMax))`.
* **`UpdateFX`**: thrusters `Boost = C.FXBoost`; fans `Thrust = Max(Abs(C.FanThrust[f]), C.FXFanThrust)`, `Boost = C.FXBoost`.
* **`GetFlightTelemetry`**: `Telemetry.Scheme = (uint8)ControlScheme`.
* **Death**: `HandleDeath` calls `ResetSchemeState`; the cosmetic drift fields are then 0, so the FX stop pulsing.

### 11.5 `HUD.h` / `HUD.cpp`

* `UPROPERTY(EditAnywhere) float SkyRowHeight = 26.f;` Private: `bool bSkyRow`, `float DriftCharge`,
  `int32 DriftTier`, `bool bDriftActive`, `float TurboAlpha`, `int32 TurboTier`, `int32 TurboChain`,
  `float FlashTime`, `uint8 LastTurboEventCount`.
* `GetPanelSize()`: `PanelSize + FVector2D(0, bSkyRow ? SkyRowHeight : 0)`.
* `RefreshValues` (every frame, not only `SetAirship`): `bSkyRow = Ship->GetControlScheme() == EAirshipControlScheme::SkyRacer`, so a scheme switch with the HUD up redraws at once.
* `RefreshValues`: read `Ship->GetCosmeticState()` (DriftDir, DriftCharge, DriftTier, TurboAlpha, TurboTier,
  TurboChain, TurboEventCount); set `FlashTime = 0.3` on an event-count change; `FlashTime -= DeltaSeconds`.
* `NativePaint`, after the BOOST row and only if `bSkyRow`: `Y += BarHeight + 8`. Draw:
  * the label: a `DRIFT` text, an ink tag while drifting, or a `TURBO` tag in the tier colour during the burn;
  * the bar: fill = the charge (drifting) or TurboAlpha (burning), colour by tier, ink ticks at SkyTier1 and SkyTier2
    of the width;
  * the value: `I` / `II` / `III`, and `xN` when `TurboChain > 0`;
  * the panel outline in the tier colour while `FlashTime > 0`.

  Every row below moves down by `SkyRowHeight`.

### 11.6 `Sub.cpp`

`Aura.Airship.Telemetry` (lines 806-822): add `Drift dir/charge/tier`, `Turbo alpha/chain`. No other console changes
beyond the contract's `Aura.Airship.Scheme`.

### 11.7 PIE harness notes

* Drift = inject `IA_AirshipBrake` (bool) every frame with `IA_AirshipSteer` held at ±1 (and `IA_AirshipThrottle` 1,
  as the bench does; since review R1 the drift drives at full power without it too). Release = stop injecting the
  brake. The M9 maneuver needs nothing special.
* The bench's drift bot reads its own drift state (`pilot_fm.sky_drift_dir`): in PIE take it from the pilot's
  telemetry extra `DriftDir` (`IMPLEMENTATION_PLAN.md` 5).
* `DriftCharge` is valid on the pilot's machine and on the server; the tier needs the extras (`DriftTier`).
* `DebugSetInput` still works for Sky Racer: the drift is decided from the controls, so a debug brake + steer drifts.

---

## 12. Bench notes

* `scheme_skyracer.py` registers `skyracer` (enum 2) with `@register_scheme`, `ctrl_inertia = 'hull'` (4a-1), the
  preset in `flight` / `pawn`, and the camera and bot adapters.
* **Wrapped hooks.** The bench's `FlightModel` has neither the base fixes nor a hook for the attitude solve, the hold
  logic or the boost latch. So `SkyRacer.reset()` switches the sim's flight models (`sim.server` and the client
  pilot's `sim.pilot_fm`) to `SkyFlightModel`. That is `FlightModel` with its own `shape_controls`,
  `compute_gimbals`, `update_boost_server` / `_client` and a copy of `apply_forces` with the changes marked `[Sky]` or
  "base fix". No shared bench file was edited. Every change is gated by a tunable whose v1 value turns it off, as in
  the C++.
* The bench has no impact model, FOV, arm, shake, rumble, FX or HUD. Those values are in the preset for completeness
  and are spec only.
* Reproduce: `python3 metrics.py skyracer` (6 s), `python3 course.py skyracer` (2 s), `python3 skyracer_checks.py`
  (40 s), `python3 skyracer_checks.py --tune` (75 s), `python3 compare.py classic skyracer`.
* Tried and dropped:
  * a keyboard steer ramp on the pilot's machine (taps steer at 50-60 % first): no gain on 5 seeds, it only added lag;
  * v1-style drift grip (a loose side-speed loop): the slip runs away and the path is late;
  * a slip-loop drift (the side speed pulled to a target slip): it pushed the ship outward at turn-in;
  * an un-progressive S brake: the sloppy orbit pilot oscillated in speed (M12 firing solution 46 %, now 84 %).

## Review changes

Adversarial review before any C++ was written (2026-11-23). Re-run first: `metrics.py skyracer` reproduced
`skyracer_metrics.json` exactly and `skyracer_checks.py` reproduced every number of section 9 (39 of 39 bands). Run the
sims from their own folder: `airship_sim.py` reads its keel points from `../../sims/fix2/ucx.json`, and a copy
elsewhere silently loses them (Classic's sloppy course then changes). The design and every other number are the
designer's.

| # | What changed | Why |
|---|---|---|
| R1 | **Weakest point, fixed: a drift drives at full power unless S is held** (new `SkyDriftThrottle`, preset 1.0, v1 0). Sections 1, 2 (how to drift), 3.3, 4.2, 9, 10 (risk 10), 11.7; bench `scheme_skyracer.py` `shape_controls`, new check in `skyracer_checks.py` section 2. | The signature move needed W + D + X on one hand (a right drift crossed the ring finger under the middle finger), and a drift with W released lost 3 m/s in 1.2 s, so the awkward chord was the only good technique. On a gamepad the stick held sideways has no forward part, so a B-drift was always a coasting drift. Now A/D + X drifts exactly like W + A/D + X (check: same 49.4 deg, tier 2, 5.0 m/s kick); S + X still gives a slower drift (56 → 48 m/s). Cost in the bench: the sloppy bot at 100 ms misses 2.8 gates instead of 2.4 (5 seeds; official seed 3 instead of 2, one over the designer's band), because its key model had been dropping W during some drifts; everything else is unchanged. |
| R2 | `bSkyDrift` is not a C++ property: the Sky Racer branches test `ActiveScheme == SkyRacer`. Because every `Sky*` tunable is then read only under Sky Racer, its C++ default is the Sky Racer value of section 4.2 (not the "v1" column); the preset still restores it on every switch (`IMPLEMENTATION_PLAN.md` 1.13). | The scheme already selects the behaviour; a second switch could disagree with it. |
| R3 | Shared names: `SkyBrakeAccelMax` → `BrakeMaxAccel`, `SkyDriftAlphaYawMax` → `DriftAlphaYawMax`, `bSkyLevelGrip` → `bLevelGripForce` + `bLevelGripAlongHeading`, `SkyAim*Scale` → `GunDeck*Scale`, and the camera roll / shake / FOV / rumble values → the shared feedback properties. The bench keeps the old names (mapping in `IMPLEMENTATION_PLAN.md` 6). | The same mechanisms exist in Galleon and Point & Fly; one implementation each. The two level-grip formulas stay separate (one bool): swapping them cost each scheme's sloppy bot 0.6-1.0 gates. |
| R4 | Reset points: `OnRep_PilotCharacter` (every machine) in place of `PossessedBy` / `UnPossessed`; the HUD re-reads the scheme every frame and the pawn resizes its viewport slot instead of hiding and re-showing it. | `PossessedBy` / `UnPossessed` run only on the server, so a client pilot's and the observers' drift state would survive an exit and could fire a cosmetic turbo; hide / show flashes the on-foot overlay. |
| R5 | Section 6: the wheel and rudder follow the steer in a drift (nothing forces them hard over). | The spec claimed a behaviour the C++ list never implemented. |
| R6 | Section 11 now points at `IMPLEMENTATION_PLAN.md` as the authoritative change list. | One list for the implementer. |

Checked and left as designed: the drift state machine runs from the controls alone on every machine (deterministic;
the tier grace covers packet timing); the turbo kick is noted with `NoteFlightKick`; the gains at 1/30 s (largest
`gain x dt` 0.27, the exit snap) and at 1/120 s (`sims/review_fps_check.py`: turn, drift, climb, brake within 1 deg/s, 0.3 m and
0.05 s of the 30 fps run); no new wire field; all contract fields. Distinctness: Sky Racer is the only scheme with a
drift-and-boost economy and an 18 % faster course time; it keeps Classic's keys, so it reads as "Classic made into a
racer".
