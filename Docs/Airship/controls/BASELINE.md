# Airship controls: baseline (v1) reference

The shared starting point for the three control schemes (Galleon, Sky Racer, Point & Fly), their judging and the
implementation of the winner. It describes the v1 controls exactly as the code is today (clone `_AirshipWork`, branch
`claude/project-thread-0emzt1`, commit 8f01bca), what each tunable does, why the measured feel problems happen, and where a
scheme can hook in.

**How to read it**

* "PIE" numbers were measured in the editor (`Docs/Airship/reports/pie_validate.md` run 2, `pie_smoke.txt`, `mp_test.md`,
  fixed 30 fps). "Sim" numbers come from the Python port in `Docs/Airship/controls/sims/` (section 9). Anything not read
  in code or measured is marked **guess**.
* Units in the text: m, m/s, deg, deg/s, s, g (1 g = 9.8 m/s²). Tunables are listed in their code units (cm, cm/s,
  cm/s², rad/s², 1/s) because that is what a preset table must contain.
* File shorthand (all under `Source/Aura/`):

| Short | File |
|---|---|
| `FC.h` / `FC.cpp` | `Public/Airship/AirshipFlightComponent.h` / `Private/Airship/AirshipFlightComponent.cpp` |
| `Pawn.h` / `Pawn.cpp` | `Public/Airship/AirshipPawn.h` / `Private/Airship/AirshipPawn.cpp` |
| `Types.h` | `Public/Airship/AirshipTypes.h` |
| `Anim.h` / `Anim.cpp` | `Public/Airship/AirshipAnimInstance.h` / `Private/Airship/AirshipAnimInstance.cpp` |
| `HUD.cpp` | `Private/Airship/AirshipHUDWidget.cpp` |
| `Sub.cpp` | `Private/Airship/AirshipSubsystem.cpp` |
| `Settings.h` | `Public/Airship/AirshipSettings.h` |

## Top facts for scheme designers

1. **The pitch loop is about 6 times too soft, and that, not the targets, is most of the nose dip (section 4a).**
   `ApplyForces` multiplies its angular-acceleration commands by `Body->GetInertiaTensor()` as if X/Y/Z were the hull's
   roll/pitch/yaw moments, but Chaos returns the principal moments in its eigen-solver order (largest, smallest, middle).
   For this long hull the pitch command is therefore scaled by the roll moment. The sim with the hull's real inertia
   (from the 8 UCX convexes) and that error reproduces PIE almost exactly: full-throttle pitch within 0.5 deg RMS (-16.6
   against -16.5 deg), the turn bank (16.5..17.9) and the turn pitch (-6.8..-2.8 against about -7..-2.8). Without the
   error it cannot. Fixing it plus two small changes takes the full-throttle dip from -16.6 to -4 deg (sim).
2. **The only thing that crosses the network is `FAirshipPilotInput`:** 4 int8 axes, 8 button bits (4 free), a sequence
   number and the aim point, sent unreliably at 30/s and whenever the controls change. The server keeps only the newest
   packet and samples it once per server frame. Every machine builds its cosmetics by running the same shaping on the
   controls it has. So a scheme should put its intent into Classic-shaped axes on the pilot's machine, or write what the
   server derived back into the controls before they replicate (section 5).
3. **A client pilot feels the hull one round trip late** (0.07-0.17 s without lag, 0.30-0.37 s with 100 ms each way), while
   the wheel, fans, nozzles, FX, camera and HUD answer after 0.066 s. Closed loops such as heading hold belong on the server.
   The pilot's machine should send targets and give strong local feedback (section 6).
4. **Vertical and low-speed handling are the weak axes.** After the lift key is released the ship needs about 2.1 s to stop.
   A brake press latches the altitude with no lead, and the ship bobs about 1.5-3 m. Below a few m/s nothing holds the
   ship's position (the forward drag time constant is 20 s), which is why deck walking and wind make it drift. The base
   fixes in section 4 cut these to about 1.2 s, under 0.2 m of bob and 0.3 m of drift (sim).
5. **The camera is a free-look orbit (control rotation).** It recentres behind the ship 1.5 s after the last look input,
   above 8 m/s, unless the pilot is aiming. The broadside side is the one whose hull-local Y holds the camera's aim point,
   with 3 m of hysteresis. A camera looking forward therefore fires the last side, at the ±20 deg yaw limit. Note for the
   harness: a control rotation set from Python is pulled back by the recentre, because only `IA_AirshipLook` resets the
   timer (section 3).

---

## 1. One frame of control

Every machine runs `AAirshipPawn::Tick` in `TG_PrePhysics` (`Pawn.cpp:331-384`). The PlayerController ticks first: it is
a tick prerequisite of its pawn, so this frame's Enhanced Input values are ready. The flight component does not tick on its
own (`FC.cpp:73`); the pawn calls it, so the order is fixed.

### 1.1 Who runs what

"Pilot" is the machine of the player at the helm (the listen-server host or a client). "Server" is the listen server.
"Observers" are the other clients.

| # | Step | Code | Pilot | Server | Observers |
|---|---|---|---|---|---|
| 1 | Record the hull velocities before the physics step (impact cap) | `RecordPreStepState`, `Pawn.cpp:1646-1661` | yes | yes | yes |
| 2 | Read the input values, quantize, add the camera aim point | `GatherLocalInput`, `Pawn.cpp:631-678` | yes | - | - |
| 3 | Store / send: the host stores directly; a client sends an RPC on change or at the 30 Hz heartbeat | `SetLocalInput` `FC.cpp:207-221`, `SendLocalInput` `FC.cpp:223-246` | yes | - | - |
| 4 | Receive, drop older sequence numbers | `ServerSetPilotInput_Implementation`, `FC.cpp:248-263` | - | yes | - |
| 5 | Pick this frame's controls | `SelectControls`, `FC.cpp:285-317` | own `LocalInput` | `ServerInput` (neutral after 0.5 s of silence or with no controller), or `DebugInput` | `RepInput` |
| 6 | Gate boost by fuel; copy the used controls to `RepInput` | `UpdateBoostServer` `FC.cpp:319-364`, `FC.cpp:443-449` | client pilot predicts the gate from the replicated fuel (`FC.cpp:450-462`) | yes | - |
| 7 | Shape the controls (first-order filters, brake and drift logic) | `ShapeControls`, `FC.cpp:366-389` | yes | yes | yes |
| 8 | Ground traces from the 4 pods | `TraceGround`, `FC.cpp:497-535` | - | yes | - |
| 9 | Forces and torques | `ApplyForces`, `FC.cpp:537-919` | - | yes | - |
| 10 | Cosmetic state (gimbals, fan yaw, thrust levels) | `UpdateCosmetic`, `FC.cpp:921-957` | yes | yes | yes |
| 11 | Cannon aim targets (pilot: its camera; others: the replicated aim point) | `UpdateCannonAim`, `Pawn.cpp:1267-1303` | yes | yes | yes |
| 12 | Niagara `Thrust` / `Boost` user parameters | `UpdateFX`, `Pawn.cpp:1520-1549` | yes | yes (listen) | yes |
| 13 | Camera: recentre, pitch clamp, arm length, FOV | `UpdateCamera`, `Pawn.cpp:1556-1617` | yes | - | - |
| 14 | Ship HUD on or off | `UpdateShipHUD`, `Pawn.cpp:2057-2090` | yes | - | - |
| 15 | Replicate this frame (`ForceNetUpdate`) | `Pawn.cpp:361-364` | - | yes | - |
| 16 | Physics step (Chaos, the frame's dt, no substeps) | engine | host: the authoritative step; client: its copy, gravity off, corrected toward the server | the authoritative step | their copy, like a client pilot's |
| 17 | Rig variables (game thread copies, worker thread integrates) | `Anim.cpp:102-137`, `:139-306` | yes | yes | yes |
| 18 | HUD values and paint | `HUD.cpp:84-120`, `:122-266` | yes | - | - |

Input callbacks outside the tick (pilot only): look `OnLookInput` (`Pawn.cpp:705-731`, `Triggered`, adds control
yaw/pitch, stamps `LastLookInputTime`), zoom `OnZoomInput` (`:733-737`), fire `OnFireInput` -> `RequestFire`
(`:739-742`, `:1305-1341`, `Started`), exit `OnExitInput` (`:744-754`, `Started`). Throttle, steer, lift, strafe, boost,
brake and aim are bound with `BindActionValue` and polled each frame (`Pawn.cpp:546-552`).

### 1.2 Pilot side (step 2)

`GatherLocalInput` (`Pawn.cpp:631-678`):

* Axis values come from `GetBoundActionValue`. The keyboard gives exactly -1, 0 or +1; the gamepad sticks have the IMC
  modifiers (steer: dead zone 0.15, exponent 1.6). The IAs have no triggers, so `Started` / `Completed` events fire on
  press and release and a scheme can detect taps in C++. W and S map to one axis; the IA's accumulation
  (`TakeHighestAbsoluteValue`, the default) decides what W+S gives.
* `QuantizeAxis`: `round(clamp(v) * 127)` into int8 (`Types.h:76-79`). The buttons go into bits 0-3 (`Types.h:27-31`).
* Aim point: a Visibility trace from the player view point (last frame's camera, with the spring arm's lag) along the view
  direction, 600 m, ignoring the ship and anything attached to it (`Pawn.cpp:680-703`). It sets bit 3 `HasAimPoint`.
* `DebugSetInput` (`Pawn.cpp:2193-2208`) replaces the keys on the pilot's machine (`Pawn.cpp:652-657`) and goes the same way
  to the server. It skips any pilot-side scheme shaping placed after this point.

### 1.3 Network (steps 3-5)

* Client: `SendLocalInput` sends when `SameControls` is false (axes and buttons changed; the sequence number and aim point
  are ignored, `Types.h:99-103`) or `1 / InputSendRate` (30/s) of real time has passed. A stick that moves every frame
  sends every frame.
* Server: keeps the newest packet (wrap-aware 8-bit sequence; after 0.5 s of silence it takes any packet). `SelectControls`
  returns neutral controls when the newest packet is older than `InputTimeout` (0.5 s) or the ship has no controller. A
  neutral ship holds its altitude and coasts.
* `RepInput` (the controls the server used, boost gated) replicates `COND_SkipOwner` (`FC.cpp:93`). With
  `bReplicateEveryFrame` the ship goes out every server frame (`Pawn.cpp:361-364`).

### 1.4 Shaping (step 7, every machine)

`ShapeControls` (`FC.cpp:366-389`), with `Approach` = `x += (target - x)(1 - e^(-dt/tau))` (`FC.cpp:27-39`):

* `bDrifting` = brake held, |raw steer| > 0.3, forward speed > 8 m/s.
* Braking (not drifting): the throttle target becomes -0.5 while moving forward faster than 1 m/s, else 0. The W/S key
  is ignored while braking. A drift keeps the throttle.
* Filters: throttle 0.30 s up / 0.45 s down, boost 0.15 / 0.60 s, lift 0.25 s, steer 0.15 s, strafe 0.20 s. `dt` is the
  physics step, `min(frame dt, 1/30 s)` (`FC.cpp:435-436`), so below 30 fps everything runs slower than real time.

### 1.5 Forces (step 9, server only)

`ApplyForces` (`FC.cpp:537-919`). Every axis is an acceleration command: the loops scale with the runtime mass and inertia,
so handling should not depend on mass (section 4a shows the inertia part does not hold today). The physical actuators get
what they can deliver; the rest goes to capped hidden terms.

| Block | Lines | What it does |
|---|---|---|
| State | 557-573 | Velocity, angular velocity, COM, body-frame speeds `Vf` (forward), `Vl` (right), world `Vz`, actor `Z`, `Inertia = Body->GetInertiaTensor()` (567), the shaped controls |
| Forward command | 575-594 | `AFanCmd = AFan(boost-lerped) * throttle * (1 - (Vf/VTop)^6)`. Reverse: braking uses `AFan`, S alone `AFanRev` with a `1 - (abs(Vf)/VTopRev)^2` fade. Drag `-(C1 Vf + C2 Vf abs(Vf))` along the hull's forward axis. Air brake `-Kbrake * Vf` (0 share while drifting). `ACmd = AFanCmd + ADrag + ABrake` feeds the pitch target and the fans. |
| Vertical | 596-640 | Lift held (\|lift\| >= 0.05): commanded climb / sink speed `lift * 12 or 15 m/s`. Released: on the first released frame, hold altitude `HoldZ = Z + Vz * 0.5 s`. A brake press (a rising edge, in hold mode only) sets `HoldZ = Z` with no lead (615-618). Hold speed `clamp(0.8/s * (HoldZ - Z), ±8 m/s)`. Floor: at least `1.5/s * (4 m - clearance)` up, and the sink is limited so the nozzles can stop 4 m above the ground at 0.6 g. Optional ceiling. Collective `m (g + 2/s (VzCmd - Vz))` clamped to 0.25..1.9 W, divided by the body's up Z (tilt compensation). |
| Attitude targets | 642-645 | Bank = `BankMax(18 / drift 22 / boost 12) * steer * clamp(Vf/20 m/s, 0.25, 1) + 6 * strafe`. Pitch = `clamp(-8 deg/g * ACmd/g, -8, +6) - 3 * boost + 3 * lift`. |
| Attitude PD | 647-670 | Quaternion error to (pitch target, current yaw, bank target). PD on roll (6.25, 4.5) and pitch (4.0, 3.2); the D terms damp only the tilt rate (the world-Z part of the spin is removed). Torque request `TauX = Inertia.X * a_x`, `TauY = Inertia.Y * a_y` (669-670). |
| Thruster mixing | 672-784 | Gimbal lean per pod: pitch `10 * throttle + 5 * boost - 6 * brake`, roll `12 * strafe ± 5 * steer` (front / rear opposite), cone limit 5 deg (`ComputeGimbals` `FC.cpp:391-414`). A 3x3 least-squares solve splits the collective and the roll / pitch torque over 4 pods. `S` = the largest share of the attitude part that fits each pod's 0.02..0.55 W range. Pod force spool 0.10 / 0.15 s. Ground cushion outside the loops: `0.25 W * 0.35 * (1 - h/15 m)^2` per pod. The undelivered `(1 - S)` share of the tilt acceleration goes to a hidden gyro capped at 0.8 rad/s². |
| Yaw command | 786-796 | Yaw-rate target `steer * Rmax(abs(Vf))`: 30 deg/s standing, 45 at 15 m/s, 35 at 48 m/s and above, drift 50, boost lerps to 25. `AlphaZ = clamp(3/s * (target - w.Z) + 0.5 * target, ±1 rad/s²)`, `TauZ = Inertia.Z * AlphaZ`. |
| Fans + rudder | 798-819 | Fan housings yaw `-12 deg * steer` (physics and the rig agree). Fan forward total = `m * AFanCmd - pods' forward share`, clamped to `±2 FanMax` (0.68 W each, boost 1.0). Rudder (hidden, inside the yaw loop) gives what the pods and housings don't, up to `0.6 rad/s² * (Vf/48 m/s)² * abs(steer)`, max 1.2. The fan differential `D` does the rest (counter-rotating fans at rest = pivot turn); the remainder goes to a hidden yaw gyro, cap 0.5 rad/s². |
| Lateral grip | 821-831 | Side-speed loop toward `strafe * 12 m/s`: grip 4/s, 2.5 g cap; drift 1.2/s, 1.2 g; boost 3/s, 2.0 g. The physical side forces (gimbals, fan housings) are subtracted. Redirect: above 5 m/s, a share `Eta` (0.35 / drift 0.4 / boost 0.3) of the scrubbed side speed is added forward, so turns carve. |
| Drift kick | 833-852 | A drift held at least 1.2 s pays +6 m/s forward when it ends (impulse, noted for the impact cap). |
| Boost | `FC.cpp:319-364` | A start needs 20 fuel and costs 10. It drains 25/s and regenerates 12/s after 1 s off. The kick is +4 m/s forward, at most once per 1.5 s. Holding boost from full fuel lasts 3.6 s. |
| Wind | 854-861 | Perlin sway: lateral 0.25 m/s², roll 0.03, pitch 0.015 rad/s², fading to 0 at 30 m/s. |
| Apply + caps | 863-888 | 4 pod forces and 2 fan forces at their points (`AddForceAtLocation`); one COM acceleration (grip, drag, brake, redirect, wind lateral, hard cap above 110 m/s); one accel-change torque (rudder, yaw gyro, tilt gyro, wind). Engine angular damping 0.5/s and a 120 deg/s spin cap (`ApplyBodySettings` `FC.cpp:157-188`). |

### 1.6 Cosmetics (steps 10-18, every machine)

`UpdateCosmetic` (`FC.cpp:921-957`) turns the shaped controls into `FAirshipCosmeticState` (`Types.h:201-227`). This
includes the pod gimbals (the same function the forces use) and the fan yaw (the same angle). The pod thrust level is
approximate: `1 + 0.6 lift + 0.3 boost + 0.15 |throttle| ± 0.15 steer`, clamped to 0..1.5. The fan thrust is the forward
part with the speed fade plus `0.6 * steer` of differential. Readers:

* `UAirshipAnimInstance` (`Anim.cpp:139-306`): nozzle pitch/roll (interp 8/s), petal flare `6 + 40 (alpha - 1)` deg,
  turbine yaw (slew 40 deg/s), rotor spin `±(300 + 1500 |thrust|) deg/s` (x2 on boost), rudder `-25 deg * steer`, wheel
  `-270 deg * steer` on a spring (6 rad/s, damping 0.4, overshoots), cannon aim slew 45 deg/s, recoil, searchlights.
* `UpdateFX` (`Pawn.cpp:1520-1549`): thrusters `Thrust` = pod thrust level (0..1.5), fans `Thrust` = |fan thrust| (0..1),
  all `Boost` = shaped boost.
* HUD (`HUD.cpp:84-120`): telemetry (speed, fuel, health), aim side, reload, and the ground distance traced every 0.1 s.
* Camera (`Pawn.cpp:1556-1617`): FOV and arm from the cosmetic forward speed and boost.

---

## 2. Tunables (v1 values)

`BP_AirshipPawn` overrides none of these (it only sets assets: `Docs/Airship/scripts/ue/as_21_blueprint.py`), and the
test map's ship instance overrides nothing, so the C++ defaults are the live v1 values. A Classic preset must copy every
value below. `Aura.Airship.Set <Name> <Value>` changes them live: the flight component by default, `Pawn.<Name>`,
`Anim.<Name>`. Note that `Aura.Airship.Set` skips the ClampMin metadata.

### 2.1 Flight component (`FC.h`)

**Body (`FC.h:94-133`)**

| Tunable | v1 | Meaning |
|---|---|---|
| MassKg | 40000 kg | Hull mass override (handling should be mass independent; matters for collisions) |
| bOverrideCenterOfMass / DesiredCenterOfMass | true / (-170, 0, 0) cm | COM at the thrust centroid in X, hull Z 0 (the fans sit 1.4 m above it, the pods 0.9-1.2 m below) |
| AngularDamping / LinearDamping | 0.5 / 0 1/s | Engine damping while alive (the yaw loop feeds the angular damping forward) |
| MaxAngularVelocityDeg | 120 deg/s | Engine spin cap while alive |
| DeadAngularDamping / DeadLinearDamping / DeadMaxAngularVelocityDeg | 0.12 / 0.02 / 180 | After death |
| bUseCCD | true | Continuous collision on the hull |
| bDisableGravityOnClients | true | Client copies coast between corrections |

**Geometry (`FC.h:140-164`):** pod and fan points are read from bones `Thruster_FL/FR/RL/RR`, `Thruster_*_Flame`,
`Turbine_L/R_Rotor` (fallbacks are equal to the rig: pods (383, ±466..492, -93..-113) and (-717, ±513..577, -120..-124) cm,
fans (-1720, ±760, 140) cm, nozzle depth 470 cm). Not scheme tunables.

**Shaping (`FC.h:171-197`)**

| Tunable | v1 | Meaning |
|---|---|---|
| ThrottleTauUp / ThrottleTauDown | 0.30 / 0.45 s | Throttle spool (up = toward a larger magnitude) |
| BoostTauUp / BoostTauDown | 0.15 / 0.60 s | Boost in / out |
| LiftTau | 0.25 s | Lift filter (also delays the hold capture, section 4b) |
| SteerTau | 0.15 s | Steer filter (drives the wheel, fans, rudder, bank) |
| StrafeTau | 0.20 s | Strafe filter |
| PodForceTauUp / PodForceTauDown | 0.10 / 0.15 s | Pod force spool (actuator lag inside the loops) |

**Vertical (`FC.h:204-258`)**

| Tunable | v1 | Meaning |
|---|---|---|
| ClimbRate / DescendRate | 1200 / 1500 cm/s | Climb / sink speed at full lift (12 / 15 m/s) |
| Kvz | 2.0 1/s | Vertical speed loop gain |
| Kz | 0.8 1/s | Altitude hold: speed command per metre of error |
| HoldMaxSpeed | 800 cm/s | Fastest hold correction |
| HoldCaptureLead | 0.5 s | On lift release, hold at `Z + vz * lead` |
| LiftDeadZone | 0.05 | Shaped lift below this = released |
| CollectiveMin / CollectiveMax | 0.25 / 1.9 W | Collective clamp: at most 0.75 g down, 0.9 g up |
| MinClearance / Kfloor | 400 cm / 1.5 1/s | Floor: keeps 4 m between the nozzle exits and the ground (hops platforms) |
| FloorBrakeAccel | 588 cm/s² | Sink limit toward the ground (0.6 g stop) |
| bUseCeiling / CeilingZ / Kceil | false / 100000 cm / 1.0 | Optional ceiling |

**Attitude (`FC.h:265-318`)**

| Tunable | v1 | Meaning |
|---|---|---|
| KpRoll / KdRoll | 6.25 / 4.5 | Roll PD (designed ωn 2.5 rad/s, ζ 0.9) |
| KpPitch / KdPitch | 4.0 / 3.2 | Pitch PD (designed ωn 2.0 rad/s, ζ 0.8; effectively about 0.8 rad/s, ζ 0.33 today, section 4a) |
| BankMaxDeg / BankMaxDriftDeg / BankMaxBoostDeg | 18 / 22 / 12 deg | Bank at full steer |
| StrafeBankDeg | 6 deg | Extra bank per unit strafe |
| BankFullSpeed / BankMinFraction | 2000 cm/s / 0.25 | Below 20 m/s the bank fades to 25 % |
| PitchPerG | 8 deg/g | Nose dip per g of commanded forward acceleration (braking flares the nose) |
| PitchMinDeg / PitchMaxDeg | -8 / +6 deg | Clamp of that lean |
| BoostPitchDeg / LiftPitchDeg | 3 / 3 deg | Extra nose-down at full boost / nose-up at full lift |
| GyroTiltMax | 0.8 rad/s² | Cap of the hidden roll/pitch stabiliser (only the share the pods can't deliver) |

**Thrusters (`FC.h:325-363`)**

| Tunable | v1 | Meaning |
|---|---|---|
| PodForceMin / PodForceMax | 0.02 / 0.55 W per pod | Pod force range (4 x 0.55 = 2.2 W) |
| ThrusterGimbalMaxDeg | 5 deg | Nozzle lean cone (rig limit ±5) |
| GimbalPitchPerThrottle / PerBoost / PerBrake | 10 / 5 / 6 deg | Lean forward per unit (brake leans back); full throttle already hits the 5 deg cone |
| GimbalRollPerStrafe / PerSteer | 12 / 5 deg | Lean right per strafe; front right / rear left per steer |
| GroundEffectStrength | 0.35 | Cushion at 0 m (fraction of the hover share), fading out at GroundTraceLength |
| bGroundTraces / GroundTraceLength | true / 1500 cm | Server pod traces (floor, cushion, telemetry) |

**Yaw (`FC.h:371-417`)**

| Tunable | v1 | Meaning |
|---|---|---|
| Kr / AlphaYawMax | 3.0 1/s / 1.0 rad/s² | Yaw-rate loop gain / cap |
| YawRateAtRest / AtMid / AtTop | 30 / 45 / 35 deg/s | Full-steer rate standing / at YawRateMidSpeed / at YawRateTopSpeed and above |
| YawRateMidSpeed / YawRateTopSpeed | 1500 / 4800 cm/s | Breakpoints (linear between) |
| YawRateDrift / YawRateBoost | 50 / 25 deg/s | While drifting / at full boost |
| FanYawMaxDeg | 12 deg | Fan housing yaw at full steer (rig limit ±12) |
| RudderAuthority / RudderRefSpeed / RudderMaxAlpha | 0.6 rad/s² / 4800 cm/s / 1.2 rad/s² | Hidden rudder, grows with speed squared |
| GyroYawMax | 0.5 rad/s² | Hidden yaw stabiliser cap |

Turn radius at full steer: about 79 m at 48 m/s (35 deg/s), 19 m at 15 m/s (45 deg/s); a pivot at rest turns at 30 deg/s.

**Forward (`FC.h:424-476`)**

| Tunable | v1 | Meaning |
|---|---|---|
| AFan / VTop | 1323 cm/s² / 5000 cm/s | Fan acceleration at full throttle (1.35 g) fading to 0 at 50 m/s (top about 48 m/s with drag) |
| AFanBoost / VTopBoost | 1960 cm/s² / 9600 cm/s | The same at full boost (2.0 g, top about 87-89 m/s) |
| AFanRev / VTopRev | 490 cm/s² / 1800 cm/s | S alone: 0.5 g reverse, 18 m/s top |
| ThrustFadeExponent | 6 | Thrust fade `1 - (v/VTop)^n` |
| DragC1 / DragC2 | 0.05 1/s / 3e-6 1/cm | Drag along the hull's forward axis (long coasts: half speed after about 11 s; at low speed only C1, time constant 20 s) |
| Kbrake | 0.9 1/s | Air brake, proportional to speed (with the reversed fans: peak about 4.4 g from 48 m/s (sim), about 7.5 g from 70 m/s) |
| BrakeReverseThrottle | 0.5 | Fans reverse to -0.5 throttle while braking above 1 m/s |
| FanMax / FanMaxBoost | 0.68 / 1.0 W per fan | Fan force caps |
| HardSpeedCap / HardCapGain | 11000 cm/s / 3 1/s | Strong pull above 110 m/s |

**Lateral (`FC.h:483-537`)**

| Tunable | v1 | Meaning |
|---|---|---|
| StrafeSpeed | 1200 cm/s | Side speed at full strafe |
| GripKlat / GripALatMaxG / GripEta | 4.0 1/s / 2.5 g / 0.35 | Normal grip: side-speed loop, cap, scrub-to-forward share |
| DriftKlat / DriftALatMaxG / DriftEta | 1.2 / 1.2 / 0.4 | While drifting |
| BoostKlat / BoostALatMaxG / BoostEta | 3.0 / 2.0 / 0.3 | At full boost |
| RedirectMinSpeed | 500 cm/s | The redirect needs this forward speed |
| DriftSteerThreshold / DriftMinSpeed | 0.3 / 800 cm/s | Drift = brake + \|steer\| above, faster than |
| DriftBrakeScale | 0 | Air-brake share while drifting (0: slides without slowing) |
| DriftBoostMinTime / DriftBoostDV | 1.2 s / 600 cm/s | Drift-end kick |

**Boost (`FC.h:544-570`)**

| Tunable | v1 | Meaning |
|---|---|---|
| BoostFuelMax | 100 | Fuel (replicated) |
| BoostDrainRate / BoostRegenRate / BoostRegenDelay | 25 /s / 12 /s / 1 s | Drain, regen, regen delay |
| BoostMinFuelToStart / BoostStartFuelCost | 20 / 10 | A start needs / costs |
| BoostKickDV / BoostKickCooldown | 400 cm/s / 1.5 s | Start kick and its cooldown |

**Wind (`FC.h:577-599`):** WindLateralAccel 25 cm/s² at 0.15 Hz, WindRollAccel 0.03 rad/s² at 0.12 Hz, WindPitchAccel
0.015 rad/s² at 0.21 Hz, WindFadeSpeed 3000 cm/s.

**Cosmetic (`FC.h:606-621`):** PodAlphaPerLift 0.6, PodAlphaPerBoost 0.3, PodAlphaPerThrottle 0.15, PodAlphaPerSteer 0.15,
FanSteerShare 0.6 (rotor differential at full steer).

**Network (`FC.h:628-634`):** InputSendRate 30 /s (plus every change), InputTimeout 0.5 s.

### 2.2 Pawn: camera, cannon aim, FX, HUD (`Pawn.h`)

**Camera (`Pawn.h:605-666`)**

| Tunable | v1 | Meaning |
|---|---|---|
| CameraArmLength / CameraArmMin / CameraArmMax | 6500 / 4000 / 12000 cm | Arm length, zoom range |
| CameraZoomStep / CameraZoomInterpSpeed | 800 cm / 6 1/s | Per wheel step, follow speed |
| CameraBoostArmExtra | 1000 cm | Extra arm at full boost |
| BaseFOV | 85 deg | Base field of view |
| SpeedFOVExtra / SpeedFOVStart / SpeedFOVFull | 10 deg / 2000 / 4800 cm/s | +10 deg from 20 to 48 m/s forward speed |
| BoostFOVExtra / AimFOVOffset | 12 / -15 deg | Boost / aim |
| FOVInterpSpeed | 4 1/s | FOV follow speed |
| CameraPitchMin / CameraPitchMax / CameraDefaultPitch | -60 / 25 / -12 deg | Pitch range, start and recentre pitch |
| RecenterDelay / RecenterMinSpeed / RecenterSpeed | 1.5 s / 800 cm/s / 2 1/s | Auto recentre |

Spring arm and camera component values are set in the constructor (`Pawn.cpp:175-194`), not as pawn properties. A preset
that changes them must write `CameraBoom` itself: TargetOffset (0, 0, 900) cm in world space, bUsePawnControlRotation true,
bInheritRoll false, camera lag on (CameraLagSpeed 5, CameraLagMaxDistance 2500 cm), rotation lag on (CameraRotationLagSpeed
7), collision probe 50 cm. The camera component has bUsePawnControlRotation false and FOV 85.

**Cannon aim and firing (`Pawn.h:507-571`)**

| Tunable | v1 | Meaning |
|---|---|---|
| CannonYawLimitDeg | 20 deg | Yaw either way about hull +Z from the outboard rest direction |
| CannonElevMinDeg / CannonElevMaxDeg | -10 / 8.5 deg | Elevation, relative to the hull (keep equal to the anim instance's) |
| CannonAimTraceDistance | 60000 cm | Camera aim trace (no hit: the end point) |
| AimSideHysteresis | 300 cm | The side flips once the aim point is 3 m past the keel line |
| CannonCooldown | 1.5 s | Reload per side |
| CannonballSpeed / CannonSpreadDeg / CannonSpawnForwardOffset | 12000 cm/s / 0.6 deg / 60 cm | Ball launch (the muzzle's own velocity is added) |
| CannonballDamage | 60 | SetByCaller damage per ball |
| CannonRecoilImpulseDV | 80 cm/s per cannon | Hull kick at the muzzle (every machine) |

**Impact cap and damage (`Pawn.h:392-453`)**: ImpactMinSpeed 400 cm/s, ImpactDamagePerMS 6, ImpactMaxDamage 500,
ImpactCooldown 0.4 s; bLimitImpactResponse true, ImpactMaxReboundSpeed 250 cm/s, ImpactMaxSpeedGain 500 cm/s,
ImpactMaxSpinKickDeg 20 (dead 40), ImpactEpisodeGap 0.25 s, ImpactKickRefillTime 1 s, ImpactEpisodeAccel 2500 cm/s²,
ImpactEpisodeSpinAccelDeg 90 deg/s².

**FX / HUD / network:** FXThrustParam `Thrust`, FXBoostParam `Boost` (`Pawn.h:675-678`); bShowShipHUD true, ShipHUDClass
null = `UAirshipHUDWidget`, ShipHUDCornerOffset (24, 24), bHideOnFootHUD true (`Pawn.h:686-703`); bReplicateEveryFrame true
(`Pawn.h:713-714`). Passengers: bPassengersQueryOnly true, PassengerZoneMargin 300 cm (`Pawn.h:488-493`).

### 2.3 Anim instance (rig feel, cosmetic only; `Anim.h:187-323`, class defaults of ABP_Airship)

| Group | Tunables (v1) |
|---|---|
| Nozzles | NozzleMaxDeg 5, NozzleInterpSpeed 8, FlareAtHoverDeg 6, FlarePerThrust 40, FlareMinDeg -10, FlareMaxDeg 35, FlareInterpSpeed 6, ThrustAlphaInterpSpeed 6 |
| Turbines | TurbineYawMaxDeg 12, TurbineYawSlewDegPerSec 40, RotorIdleDegPerSec 300, RotorMaxDegPerSec 1500, RotorBoostMultiplier 2, RotorSpinAcceleration 1500, RotorSpinDownRate 250 |
| Helm | RudderDegPerSteer -25, RudderMaxDeg 30, RudderInterpSpeed 6, WheelDegPerSteer -270, WheelSpringOmega 6, WheelSpringDamping 0.4, WheelDeathSpinDegPerSec 540, WheelDeathSpinDecay 0.5 |
| Cannons | CannonYawLimitDeg 20, CannonElevMinDeg -10, CannonElevMaxDeg 8.5, CannonAimSlewDegPerSec 45, CannonElevSettleRate 8, CannonRecoilMaxCm 45, CannonRecoilAttackTime 0.06, CannonRecoilReturnTime 0.5 |
| Searchlights | SearchLightPanAmplitudeDeg 30, SearchLightPanFrequency 0.05 |

Any scheme value must stay inside the RIG_CONTRACT section 5 ranges: nozzles ±5, flare -10..35, thrust 0..1.5, turbine ±12,
rudder ±30, cannon yaw ±20, elevation -10..8.75 (the C++ sends at most 8.5), recoil 0..60 cm.

### 2.4 Measured v1 feel (PIE, fixed 30 fps)

| Manoeuvre | Result |
|---|---|
| Throttle from rest | 9.4 / 22.3 / 34.7 / 44.2 / 48.8 m/s at 1-5 s, top 49.5, settles at 47.8. In the MP test the server ship made 32.6 m/s in 2 s from the client's keys (`mp_test.md`) |
| Pitch on throttle / boost | -16.5 deg (peak at about 4 s) / -18 deg; brake flare +6.5, then +10 deg at standstill |
| Full steer at top speed | 35.2 deg/s, bank 16.5-17.9 deg, nose -3..-7 deg, 19 deg slip |
| Boost | 47.8 -> 87 m/s, fuel 100 -> 0 in 3.6 s |
| Brake | from 70.8 m/s half speed in 0.83 s; 2.3 g averaged to standstill (peaks 4-7 g); ends reversing at -2 m/s |
| Lift | climb 12 m/s, sink 14.2 m/s; 1.0 s after release still 6.5 m/s, 2.0 s after 0.5 m/s |
| Hover | ±0.6 deg pitch, drifts 0.47 m in 10 s alone; 0.34 m with a player standing on deck, 1.41 m in 8 s with one walking |

---

## 3. Camera

* **Rig** (`Pawn.cpp:175-194`): the spring arm is attached to the hull root (the actor origin), not to the mesh. The look-at
  point is 9 m above the origin in world space (TargetOffset). The arm is 65 m long, so at the default -12 deg pitch the
  camera sits about 64 m behind and 22 m above the origin. Roll is never inherited, so the horizon stays level when the ship
  banks; the ship's pitch and bank show as the hull tilting in view. With position lag 5/s the camera trails by `v / 5`:
  about 10 m at 48 m/s and 17 m at 87 m/s, capped at 25 m. Add the boost arm extra of 10 m: on boost the camera falls back
  about 27 m (the speed feel). The rotation lag is 7/s.
* **Free look**: the arm uses the control rotation. Mouse and right stick turn it through `AddControllerYaw/PitchInput`, with
  the Options look sensitivity and invert (`Pawn.cpp:705-731`). The camera does not follow the ship's heading by itself.
* **Reset**: on possession the view is put behind the ship at -12 deg (`bPendingCameraReset`, `Pawn.cpp:610`, `:1571-1576`).
* **Recentre** (`Pawn.cpp:1581-1587`): when all of these hold — 1.5 s since the last non-zero look input, cosmetic forward
  speed above 8 m/s, not aiming — the control yaw eases toward the ship yaw and the pitch toward -12 at 2/s (exponential).
  In a steady 35 deg/s turn this lags the heading by about 35/2 = 17.5 deg, plus the rotation lag. The view therefore looks
  outside the turn. Below 8 m/s it never recentres.
* **Pitch clamp** -60..+25 deg (`Pawn.cpp:1589-1595`); roll is forced to 0.
* **Zoom and arm**: wheel steps of 8 m in 40-120 m, plus 10 m x shaped boost, interpolated at 6/s (`Pawn.cpp:1603-1605`).
* **FOV** (`Pawn.cpp:1607-1616`): `85 + 10 * clamp((Vf - 20 m/s) / 28 m/s) + 12 * boost - 15 (aiming) + (the player's FOV
  setting - default)`, interpolated at 4/s, clamped 20..170. The maximum is 107 deg.
* **Aim mode** (RMB / LB held, bit `Button_Aim`): FOV -15 and no recentre. Nothing else: the cannons track the aim point
  whether or not the pilot aims.
* **Cannon side** (`ComputeAimSide`, `Pawn.cpp:1245-1265`): the camera aim point (section 1.2) in hull space. The side
  switches to starboard when the point's Y goes above +3 m, and to port below -3 m. For a far aim point that is a fraction of
  a degree off the keel, so a camera looking forward keeps the last side and fires it at the yaw clamp. `RequestFire`
  recomputes the side from a fresh trace (`Pawn.cpp:1305-1341`). The cannon limits are hull-relative (yaw ±20 deg off the
  beam, elevation -10..+8.5 deg). An 18 deg bank therefore tilts the low side's broadside 18 deg down and the high side's up:
  a level target is out of the elevation range for the low side during a hard turn.
* **Harness note**: `LastLookInputTime` is only set by `IA_AirshipLook` (`Pawn.cpp:727-730`). A control rotation set with
  `PlayerController.set_control_rotation` is pulled back by the recentre at about 6 % per frame (30 fps) once the ship is
  faster than 8 m/s. Either set it every frame or inject `IA_AirshipLook` with non-zero values. Injected Enhanced Input
  values last one tick (`UEnhancedPlayerInput::InjectInputForAction` fills `InputsInjectedThisTick`). Hold a key by
  injecting every frame (as `as_45_pie_mp.py` does) or use `start_continuous_input_injection_for_action`.

---

## 4. Root causes of the measured feel problems, and base fixes

Every base fix below is a new or changed tunable with a v1 value that keeps v1 behaviour exactly, so the Classic preset can
stay exact v1 (contract). Every other scheme can switch them on. Section 4f lists them all.

### 4a. Nose dips -16.5 deg at full throttle and -18 deg on boost

The PIE pitch trace at full throttle from rest (`pie_smoke.txt`, 1 Hz telemetry; validation run 2 had the same -16.5 deg
minimum) was -2.7, -9.0, -14.5, -16.3, -13.0, -6.3, -0.7, +1.6 deg at 1-8 s: slow to start, deeper than the target, late,
then overshooting nose-up. Three causes add up.

**Cause 1 (the largest; confirmed offline, to be logged in PIE): the torque requests use the wrong moments of inertia.**
`FC.cpp:567` reads `Body->GetInertiaTensor()` and `FC.cpp:669-670`, `:796`, `:811-819` use its X/Y/Z as the hull's roll,
pitch and yaw moments. `GetInertiaTensor` returns Chaos's diagonal `I()`, which is in the body's principal mass frame.
Engine paths below are under `/mnt/new_partition/5.8/Engine/Source/Runtime/`:

* `PhysicsCore/Private/ChaosEngineInterface.cpp:772-779` returns `I()`.
* Chaos diagonalizes every body's tensor with `TransformToLocalSpace`
  (`Experimental/Chaos/Private/Chaos/MassProperties.cpp:17-90`). It is called from
  `Engine/Private/PhysicsEngine/BodyUtils.cpp:120-137`, and again after the COM nudge (`:101-111`).

Unless the tensor is already diagonal to 1e-4, `TransformToLocalSpace` returns the eigenvalues ordered **largest,
smallest, middle**, plus a `RotationOfMass`. A long hull has its smallest moment about the long axis (roll), so
`Inertia.Y` (used for pitch) is the roll moment, whatever the order of Iyy and Izz.

The hull's real mass properties are in `Docs/Airship/controls/sims/hull_mass.json`. They were computed by `mass_props.py`
in the same folder (written by another step of this run; the numbers are also copied into `baseline_sim.py`). That script
is an offline port of the Chaos and BodyUtils code above, run on the 8 UCX convexes with 40 t and the COM nudged to
(-170, 0, 0):

* Tensor in hull axes: Ixx 1.21e10, Iyy 6.57e10, Izz 6.75e10 kg·cm². The product Ixz is -7.7e9, so the principal axes are
  tilted about 8 deg about Y and the tensor is far from diagonal.
* What `GetInertiaTensor()` returns: (6.86e10, 1.10e10, 6.57e10).

The code therefore scales:

| Axis | Moment the code uses | Real moment | Effect |
|---|---|---|---|
| Pitch | 1.10e10 (about the roll moment) | 6.57e10 | Torque 6.0x too small: KpPitch 4 / KdPitch 3.2 act like 0.67 / 0.54 (ωn 0.82 rad/s, ζ 0.33 instead of 2.0 / 0.8) |
| Roll | 6.86e10 (about the yaw moment) | 1.21e10 | 5.7x too strong (overdamped, saturates the pods sooner) |
| Yaw | 6.57e10 | 6.75e10 | 0.97x |

Evidence (sim, `baseline_checks.py` section 0). With the UCX inertia used the way the code uses it, the port reproduces
the PIE runs; read as the code intends, it cannot:

| | PIE | Sim, as the code uses it | Sim, code intent (fixed) |
|---|---|---|---|
| Full-throttle pitch 1-9 s | -2.7 -9.0 -14.5 -16.3 -13.0 -6.3 -0.7 +1.6 +1.2 | -2.6 -9.2 -14.7 -16.5 -13.3 -6.5 -0.7 +1.6 +1.2 | -5.2 -8.8 -9.3 -7.9 -3.8 -1.0 -0.3 -0.2 -0.2 |
| Full-throttle speed 1-5 s | 9.4 22.3 34.7 44.2 48.8 | 9.5 22.5 35.0 44.4 48.8 | 9.7 23.0 35.4 44.1 47.5 |
| Boost from the end of the turn, pitch 1-3 s | -8.0 -14.0 -17.5 | -9.3 -15.9 -16.9 | -8.0 -12.2 -11.1 |
| Full-steer bank at top speed | 16.5..17.9 | 16.5..17.9 | 17.1..18.1 |
| Pitch during that turn | about -7..-2.8 | -6.8..-2.8 | -1.3..+1.1 |

The research box estimate (1.73e10, 5.99e10, 6.56e10) in the same mix-up gives -14.1 deg: the same story, less exact.
**Confirm it in the first PIE run**: on the server, log `Body->GetInertiaTensor()`,
`Body->GetBodyInstance()->GetMassSpaceLocal()` (rotation and COM) and the hull-space COM once. A good place is an extra line
in `Aura.Airship.Telemetry` (`Sub.cpp:806-822`).

**Cause 2 (design): the pitch target itself is -8 deg.** `PitchDeg = clamp(-PitchPerG * ACmd / g, -8, +6) - 3 * boost`
(`FC.cpp:645`). Full throttle at low speed commands 1.35 g, which gives -10.8 deg, clamped to -8. Boost adds -3 (-11). The
brake commands -4..-7 g and gets the +6 clamp. A nose-down hull also tilts the collective forward and adds `g sin(pitch)` of
forward acceleration (+0.27 g at -16 deg). Part of v1's acceleration and of the 49.5 m/s overshoot comes from the dip.

**Cause 3 (disturbance): the fans push 1.4 m above the COM.** The fan points are at hull Z +140 cm, the COM at Z 0
(`FC.h:104`). The forward fan force (up to 1.26 W at full throttle, 2 W on boost) therefore pitches the nose down.
Reversed on the brake it pitches the nose up; with the soft loop of cause 1, that is part of the +10 deg flare at
standstill. The fan force is computed after the pod mixer (`FC.cpp:806`), so the mixer never compensates it and the
pitch PD absorbs it as steady error. With the correct inertia that error is about 1.3 deg (sim: -9.3 against the -8
target); with today's soft loop about 8 deg. The PD gains themselves are reasonable, and the gyro cap (0.8 rad/s²) and
the spin cap (120 deg/s) are never reached.

**Base fixes (sim, `baseline_checks.py` section 4a):**

1. **Hull-axis inertia** (code, new switch `bHullAxisInertia`, v1 false). Build the hull-space torque from the principal
   moments and the mass-frame rotation:
   ```cpp
   const FQuat MassRot = Body->GetBodyInstance()->GetMassSpaceLocal().GetRotation(); // principal -> hull
   const FVector Principal = Body->GetInertiaTensor();
   auto HullTorque = [&](const FVector& AlphaHull)
   {
       return MassRot.RotateVector(Principal * MassRot.UnrotateVector(AlphaHull)); // component-wise in the principal frame
   };
   // TauX/TauY = HullTorque(AlphaTiltBody).X/.Y (FC.cpp:669-670); the yaw lines 796, 811-819 use
   // IzzHull = HullTorque(FVector::UpVector).Z in place of Inertia.Z
   ```
   The accel-change torques (gyros, rudder) are already right: Chaos multiplies them by the real world inertia.
2. **Fan torque feed-forward** (code, new switch `bFanTorqueFeedForward`, v1 false). Before the attitude solve, estimate the
   fans' forward total from the collective, `m * AFanCmd - sum(Collective[i] * PodDir[i].X)` clamped to ±2 FanMax. Take the
   roll / pitch torque of half that total at each fan point (`(FanLocal - COM) x (FanDir * F/2)`), and subtract it from
   `[TauX, TauY]` in `BAttitude` (`FC.cpp:709`). The yaw differential adds no roll or pitch torque, so the estimate is enough.
3. **Gentler targets** (presets): PitchPerG 8 -> 4, PitchMinDeg -8 -> -4, BoostPitchDeg 3 -> 1.5 (optionally PitchMaxDeg
   6 -> 3).

| Case (sim) | Throttle pitch min | Speed at 3 s | Boost pitch min | Brake flare max | Turn pitch |
|---|---|---|---|---|---|
| v1 (as PIE) | -16.6 | 35.0 | -20.2 | +7.2 | -6.8..-2.8 |
| 1 | -9.3 | 35.4 | -12.2 | +6.3 | -1.3..+1.1 |
| 1 + 2 | -7.9 | 35.1 | -10.4 | +5.8 | -1.2..+1.0 |
| 1 + 2 + 3 | -4.0 | 34.0 | -5.2 | +5.5 | -1.4..-0.2 |
| 1 + 2 + targets 3 / -3 / 1, flare 3 | -3.0 | 33.7 | -3.8 | +2.9 | -1.4..-0.5 |
| 2 + 3 only (fix 1 left out) | -4.1 | 33.6 | -5.0 | +4.5 | -7.2..-4.5 |

The port reproduces the v1 PIE runs within about 0.5 deg, so expect PIE within 1-2 deg of these (**guess** until run).
Without fix 1 the pitch stays soft and underdamped in every manoeuvre, so fix 1 should come first. With fix 1 the roll also
gets its designed response: 90 % of the bank after 1.7 s at top speed (v1 1.9 s, overdamped), the same final bank.

### 4b. About 6.5 m/s of vertical speed left after releasing lift

Measured more precisely: the `c_lift` check (`as_30_pie_smoke.py:944-953`) takes the largest |vz| from 1 s to 3 s after
release. So PIE shows -6.46 m/s **1.0 s** after releasing a full descent and -0.46 m/s 2.0 s after (the same in the
smoke run and validation run 2). The sim gives -7.05 and -0.64.

Causes (`FC.cpp:384-388`, `:601-640`):

1. **The release goes through the 0.25 s lift filter.** The shaped lift needs 0.75 s to fall below the 0.05 dead zone. For
   that 0.75 s the ship is still commanded to climb or sink at the decaying rate, and the hold is not captured yet.
2. **The vertical authority is small.** The collective clamp of 0.25..1.9 W gives at most 0.75 g down and 0.9 g up of net
   acceleration. Stopping a 14.4 m/s sink takes at least 1.6 s; stopping a 12 m/s climb, 1.6 s.
3. **The hold capture lead `vz * 0.5 s` and the linear hold loop** (ωn 1.26 rad/s, ζ 0.79) finish the stop gently and slowly.

Result (sim): about 2.1 s to settle, and the ship travels 11-14 m after the release with a 0.5 m bob. A shorter lift filter
alone makes it worse (it captures earlier at higher speed: 2.9 m bob).

**Base fixes (sim, section 4b of the checks):**

* `VertBrakeAccel` (new, cm/s², v1 0): a hidden COM vertical acceleration, up to this cap, that opposes the vertical speed
  while it runs past the command in its own direction. It is applied like the lateral grip (`FC.cpp:877`).
* `HoldBrakeAccel` (new, cm/s², v1 0 = linear hold with the 0.5 s lead): the hold speed is limited to
  `sqrt(2 a |error|)` (like the floor's descent limiter, `FC.cpp:628-631`), and the capture lead becomes the stopping
  distance `vz |vz| / 2a`.
* `LiftTauRelease` (new, s, v1 0 = LiftTau): the filter time constant toward 0, only together with the two above.

| Case (sim) | Climb release (+12): vz at 0.5 / 1 / 1.5 / 2 s | Settled | Bob | Descent release (-15): vz at 0.5 / 1 / 1.5 s | Settled | Bob |
|---|---|---|---|---|---|---|
| v1 | 9.7 / 6.1 / 2.6 / 0.7 | 2.1 s | 0.55 m | -11.8 / -7.4 / -3.2 | 2.1 s | 0.61 m |
| Collective 0..2.2, PodForceMax 0.65 | 9.3 / 5.0 / 2.2 / 0.7 | 2.1 s | 0.28 m | -11.0 / -5.5 / -2.3 | 2.1 s | 0.16 m |
| VertBrakeAccel 490, HoldBrakeAccel 1176, LiftTauRelease 0.08 | 7.2 / 1.6 / 0.1 / 0.0 | 1.2 s | 0.05 m | -9.3 / -2.8 / -0.6 | 1.7 s | 0 |
| The same with 784 / 1470 | 5.9 / 0.7 / 0.0 | 1.1 s | 0.14 m | -8.0 / -1.4 / -0.2 | 1.2 s | 0 |

Side effect: a 0.3 s tap of lift now climbs 0.75 m instead of 3.3 m. That is more precise and less floaty, which is a
per-scheme choice. Widening the collective alone barely helps. If a scheme raises it anyway, `ImpactEpisodeAccelUp` (4e)
must grow with it.

### 4c. Braking mid-climb overshoots the held altitude by about 3 m (and the brake itself)

**Overshoot.** A brake press in hold mode sets `HoldZ = Z` with no lead (`FC.cpp:615-618`); a lift release uses
`Z + vz * 0.5 s` (`:608-612`). In validation run 2 (f2 path) the ship was rising at 3-5 m/s: the obstacle hit added up to
4.8 m/s and the floor kept pushing it 4 m over the obstacle. The press latched 37.3 m, the ship rose to 40.4 m (+3.1 m)
and sank back over 2-3 s. With a clean 4.8 m/s rise and no floor, the sim gives +1.5 m up and 1.5 m back down.

**Base fix**: `bBrakeHoldLead` (new, v1 false) uses the same lead or stopping distance as the release. Alone it lets the ship
rise 2.4 m and stay there (0.24 m back); with the 4b set, 0.8 m up and 0.2 m back (sim).

**The brake itself** (not listed as a problem, but every scheme meets it): `ABrake = -0.9/s * Vf` plus the fans reversed at
`AFan * 0.5` (`FC.cpp:588`, `:593`). The deceleration is proportional to speed: 4.4 g at 48 m/s (sim) and about 7.5 g at
70 m/s. Half speed comes after 0.8 s, then it is soft near the end. The reversed fans and the nose-up flare keep pushing
after the stop: the ship backs up at -1.8 m/s (PIE -2.1). `BrakeFadeSpeed` (new, cm/s, v1 0): the reverse throttle target
fades to 0 below this forward speed (`FC.cpp:379-382`). At 1000 it cuts the back-up to -1.1 m/s and keeps the
stopping distance (39 m); fixes 4a-1/3 shrink the flare that causes the rest. A constant-deceleration brake (cap
`-Kbrake * Vf` at about 1.5-2 g) would be more controllable; that is a scheme decision.

### 4d. Walking on deck nudges the ship about 1.4 m (and the hover drifts)

Measured: 1.41 m of horizontal travel in 8 s of walking, 0.34 m in 10 s standing, 0.47 m in 10 s alone (wind). There was no
sink and the pitch stayed under 0.6 deg.

Causes:

1. **Nothing holds the ship's horizontal position or a low speed.** At zero throttle the only forward drag is DragC1 0.05/s
   (`FC.cpp:592`), a 20 s time constant: a 0.3 m/s nudge coasts 2.3 m in 10 s (sim). The lateral grip holds the side speed
   at 0 (4/s) but not the position.
2. **The pushes (guess, from engine code, not measured per term):**
   * The rider's capsule is QueryOnly, so the CMC's own physics interaction still acts on the hull. On every blocking sweep
     hit against the simulated hull — props, the sloped UCX lid the rider walks on (CPP_NOTES 3) — it pushes along -normal
     with PushForceFactor 750000 (about 0.02 W). The code is in
     `Engine/Private/Components/CharacterMovementComponent.cpp:7814-7905` (engine Runtime path as above), defaults `:771-773`.
   * It adds the standing downward force of the CMC Mass at the feet (`:11784-11796`).
   * Each push leaves a slow drift because of cause 1.
   * The tilt from small pitch and roll errors also leans the collective sideways (about 17 cm/s² per degree).

**Base fix**: station keeping. `StationKeepGain` (new, 1/s, v1 0), `StationKeepSpeed` (300 cm/s) and
`StationKeepAccelMax` (150 cm/s²): with |throttle|, |strafe| and boost near 0, add a forward COM acceleration
`-gain * Vf` (capped). It is full below StationKeepSpeed and fades out at twice that, so coasting at speed is untouched.
The lateral grip already holds the side speed.

| Case (sim) | Drift after a 0.3 m/s nudge, 10 s | Coast from top speed, half speed after |
|---|---|---|
| v1 | 2.30 m | 10.7 s |
| StationKeepGain 1.0 | 0.27 m | 10.7 s |
| StationKeepGain 2.0 | 0.14 m | 10.7 s |

Optional (shared-code change, not a base fix): the subsystem could turn the riders' CMC `bEnablePhysicsInteraction` off
while they ride. That removes the pushes at their source; earlier tests only showed it does not cure the old sink.

### 4e. The impact cap lets about +3.3 m/s through per hit step

`LimitImpactResponse` (`Pawn.cpp:1663-1773`) lets a "free" change of `ImpactEpisodeAccel * step` pass every physics step:
2500 cm/s² x 1/30 s = 0.83 m/s (`:1710-1712`). The free part is the same upward as sideways. On top, the first hit of a
contact may spend the whole rebound budget, ImpactMaxReboundSpeed 2.5 m/s (`:1720-1729`). One hit step therefore passes
0.83 + 2.5 = 3.33 m/s up, and each later step of the same contact about 0.9 m/s. The 2500 was chosen to cover the lateral
grip's 2.5 g. Upward, the flight model can only do (CollectiveMax - 1) g + the full cushion 0.35 g = 1.25 g, about
1225 cm/s².

**Base fix**: `ImpactEpisodeAccelUp` (new, cm/s², v1 = ImpactEpisodeAccel 2500) set to 1300, plus ImpactMaxReboundSpeed
250 -> 120. With the fix3 cap model (`Docs/Airship/sims/fix3/cap_model.py`, extended in `baseline_checks.py`):

| Case | +26 m/s clip, after 1 step / 2 push steps | Take-off from landed, 0.5 g / 1.25 g for 0.3 s (want 1.47 / 3.68 m/s) |
|---|---|---|
| v1 | 3.33 / 4.25 m/s | 1.47 / 3.67 |
| ImpactMaxReboundSpeed 120 | 2.03 / 2.91 | 1.47 / 3.67 |
| ImpactEpisodeAccelUp 1300 + Rebound 120 | 1.63 / 2.11 | 1.47 / 3.67 |

Rule: `ImpactEpisodeAccelUp` must stay at or above the scheme's largest upward flight acceleration. That is
`(CollectiveMax - 1) g + 0.35 g + VertBrakeAccel` (4b), about 1750 cm/s² with the 4b set. Below that, flight forces during a scrape are
capped like kicks. The f2 climb of +6.1 m was also the floor (MinClearance) pushing over the obstacle plus the brake re-latch
(4c), not only the cap.

### 4f. Base-fix summary (Classic keeps the v1 column)

| # | Tunable (new unless noted) | Where | v1 / Classic | Suggested | Sim effect |
|---|---|---|---|---|---|
| 0 | (log inertia, mass frame, COM) | `Aura.Airship.Telemetry` | - | do it first | confirms 4a cause 1 in PIE |
| 4a-1 | bHullAxisInertia | FC `ApplyForces` 669-670, 796, 811-819 | false | true | throttle dip -16.6 -> -9.3 deg |
| 4a-2 | bFanTorqueFeedForward | FC `ApplyForces` 706-713 | false | true | -> -7.9 deg |
| 4a-3 | PitchPerG / PitchMinDeg / BoostPitchDeg (existing) | presets | 8 / -8 / 3 | 4 / -4 / 1.5 | -> -4.0 deg, boost -5.2 |
| 4b-1 | VertBrakeAccel | FC vertical + COM force | 0 | 490-784 cm/s² | release settles in 1.1-1.2 s |
| 4b-2 | HoldBrakeAccel | FC vertical 608-620 | 0 | 1176-1470 cm/s² | no bob |
| 4b-3 | LiftTauRelease | FC `ShapeControls` 386 | 0 | 0.08 s | only with 4b-1/2 |
| 4c-1 | bBrakeHoldLead | FC vertical 615-618 | false | true | brake mid-climb: 0.8 m up, 0.2 m back |
| 4c-2 | BrakeFadeSpeed | FC `ShapeControls` 379-382 | 0 | 1000 cm/s | back-up -1.8 -> -1.1 m/s |
| 4d | StationKeepGain / StationKeepSpeed / StationKeepAccelMax | FC forward COM force (877) | 0 / 300 / 150 | 1.0 / 300 / 150 | nudge drift 2.3 -> 0.27 m |
| 4e | ImpactEpisodeAccelUp; ImpactMaxReboundSpeed (existing) | Pawn `LimitImpactResponse` 1710-1729 | 2500; 250 | 1300 (>= max up accel); 120 | hit step +3.3 -> +1.6 m/s |

---

## 5. Extension points

### 5.1 Where a scheme hooks in

| Hook | Where | Runs on | Use it for |
|---|---|---|---|
| Input bindings | `SetupPlayerInputComponent`, `Pawn.cpp:532-573` | pilot | Extra `Started` / `Completed` / `Triggered` events on the existing IAs (taps, double taps, holds, order steps). No new IA or IMC: the 11 actions and their key mappings are fixed. |
| Pilot-side shaping | `GatherLocalInput`, `Pawn.cpp:631-678`, between reading the values (660-666) and `SetLocalInput` (677) | pilot | Turning keys and camera into the wire controls: throttle orders, heading targets, camera-relative steering, charge timers. Scheme-local pilot state (order, charge, free-look flag) lives on the pawn here. |
| The wire | `FAirshipPilotInput`, `Types.h:48-104` | both | New small fields (5.2) |
| Server selection | `SelectControls`, `FC.cpp:285-317`; boost gate `FC.cpp:443-449` | server | Validating or overriding controls; anything written into `Controls` before `RepInput = Controls` (448) reaches the observers' cosmetics |
| Shaping | `ShapeControls`, `FC.cpp:366-389` | every machine | Mode logic that cosmetics must see (drift, brake, order -> throttle). Keep it deterministic from (controls, forward speed) so all machines agree. |
| Forces | `ApplyForces`, `FC.cpp:537-919` | server | New command modes: heading-to-target yaw loop (replace `YawRateCmd`, 793), speed-order loop (replace `AFanCmd`, 579-590), vertical modes (601-621), grip modes (822-831), kicks (like the drift kick, 833-852; call `NoteFlightKick` for the impact cap) |
| Cosmetics | `UpdateCosmetic`, `FC.cpp:921-957`; `UAirshipAnimInstance` (`Anim.cpp:139-306`); `UpdateFX` (`Pawn.cpp:1520-1549`) | every machine | Rig and FX reactions, within the rig ranges |
| Camera | `UpdateCamera`, `Pawn.cpp:1556-1617`; `OnLookInput` 705-731 | pilot | Coupling or decoupling the camera and steering, look-ahead, shakes, FOV kicks |
| HUD | `UAirshipHUDWidget::RefreshValues` / `NativePaint` (`HUD.cpp:84-266`), `PanelSize` (`AirshipHUDWidget.h:36`) | pilot | Order telegraph, drift meter, heading marker, reticle (`GetOwningPlayer()->ProjectWorldLocationToScreen`). Slate boxes, lines and the engine font only. |
| Telemetry | `FillTelemetry` (`FC.cpp:959-995`), `GetFlightTelemetry` (`Pawn.cpp:2218-2236`) | any | The contract's new fields |
| Reset points | `PossessedBy` / `UnPossessed` (`Pawn.cpp:435-469`, both call `Flight->ResetInput`), `UpdateLocalMappingContext` (`:575-613`, camera reset), `HandleDeath` (`:1907`) | server / pilot | Resetting scheme-local state on board, exit, death and a scheme switch |

### 5.2 What extending `FAirshipPilotInput` costs

* **Today's payload** (USTRUCT without a custom NetSerialize; the RPC sends every field each time): 4 x int8 + Buttons +
  Seq = 6 bytes, plus the `FVector_NetQuantize` aim point. That is packed per component at 1 cm, about 7-8 bytes for
  positions within ±650 m (**guess** at the exact bit count). About 14 bytes per packet, 30+ packets/s: about 0.4-0.6 KB/s
  of payload from each client pilot. `RepInput` replicates per changed member to every other client.
* **Free space**: Buttons bits 4-7 are unused (`Types.h:27-31`). Use them for flags: free look, heading-target valid, a
  2-bit scheme id so the server can ignore packets sent under the previous scheme for the ~half RTT after a switch.
* **A new field** costs its size per packet (int8 / uint8: 1 byte, about 30 B/s; uint16: 2 bytes). Suggested
  quantizations: an engine order as int8 steps; a heading target as uint16 (`yaw / 360 * 65536`, 0.0055 deg); a charge as
  uint8 (1/255).
* **`SameControls`** (`Types.h:99-103`) decides when to send at once. Add discrete fields (orders, flags, counters) to it.
  Leave continuous camera-driven fields out, as the aim point is; they then ride the 30 Hz heartbeat. Otherwise a moving
  mouse sends every frame.
* **Events must survive loss and merging.** The RPC is unreliable and latest-wins, and the server reads one packet per
  server frame (a 60 fps client sends two). A one-frame bit (a tap) can vanish. Send events as a wrap-around counter (uint8,
  incremented per event; the server acts on the difference) or as a latched state.
* **Neutral must be safe.** `FAirshipPilotInput()` (all zero) is what the server uses after a 0.5 s timeout, on possession
  changes and with no controller (`FC.cpp:265-271`, `:312-313`). Give every field a valid-bit or a zero that means
  "nothing", for example "no heading target" rather than "head north".
* **Also update**: `DebugSetInput` (`Pawn.cpp:2193-2208`, new fields stay 0), the `Aura.Airship.Input` console (`Sub.cpp:744-763`),
  and the observers' path. `RepInput` is the same struct, so new fields reach observers for free.

### 5.3 Where state lives

| State | Machine | Where |
|---|---|---|
| Raw keys, `LocalInput`, `LastSentInput`, `LocalSeq`, send time | pilot | `FC.h:676-685` |
| Camera: `ZoomTarget`, `LastLookInputTime`, `bPendingCameraReset`; aim point; fire prediction | pilot | `Pawn.h:846-860` |
| Client boost prediction `bLocalBoostActive` | client pilot | `FC.h:700`, `FC.cpp:450-462` |
| `ServerInput`, timeout, boost latch, kick cooldown, regen timer, `DriftTime`, `HoldZ` / `bHoldValid` / `bBrakeWasHeld`, pod spool, ground distances | server | `FC.h:677-710` |
| `BoostFuel`, `RepInput` (skip owner) | replicated | `FC.h:641-645` |
| Shaped controls, `bDrifting`, `FAirshipCosmeticState` | every machine, from the controls it has | `FC.h:689-696`, `:717` |
| Rig integrators (wheel spring, rotors, nozzle and turbine slew) | every machine | `Anim.h:357-371` |

Consequence: a server-only quantity (`DriftTime`, `HoldZ`, a heading-loop output) is invisible to the pilot's and observers'
cosmetics unless it is (a) recomputed on every machine from the controls plus the replicated hull state, or (b) written into
`Controls` on the server before `RepInput` (observers) **and** mirrored on the pilot's machine, which never receives
`RepInput`. Example for a heading target: the pilot sends the target; the server runs the heading loop and writes the
resulting steer into `Controls.Steer` (observers' wheel and fans turn); the pilot's machine runs the same loop on its own
copy of the ship for its wheel and HUD.

### 5.4 What a scheme can't do

No new input actions, mappings, Niagara systems, meshes, materials or sounds; the rig variable names and ranges stay; the
hull stays a server-simulated Chaos body; only the `Thrust` and `Boost` user parameters exist on the FX. Taps, holds and
double taps are C++ logic on the pilot's machine. The inputs a scheme can reinterpret (`IMC_Airship`, priority 1,
`Docs/Airship/scripts/ue/as_01_input.py`; no triggers on any of them):

| Action | Type | Keyboard / mouse | Gamepad | v1 read as |
|---|---|---|---|---|
| IA_AirshipThrottle | Axis1D | W +1, S -1 | left stick Y | value every frame |
| IA_AirshipSteer | Axis1D | D +1, A -1 | left stick X (dead zone 0.15, exponent 1.6) | value every frame |
| IA_AirshipLift | Axis1D | Space +1, Left Ctrl / C -1 | RT +, LT - (analog) | value every frame |
| IA_AirshipStrafe | Axis1D | E +1, Q -1 | D-pad right / left | value every frame |
| IA_AirshipBoost | Bool | Left Shift | A | held, every frame |
| IA_AirshipBrake | Bool | X | B | held, every frame |
| IA_AirshipAim | Bool | RMB | LB | held, every frame |
| IA_AirshipFire | Bool | LMB | RB | `Started` |
| IA_AirshipLook | Axis2D | mouse XY | right stick (exponent 2) | `Triggered` |
| IA_AirshipZoom | Axis1D | wheel | D-pad up / down | `Triggered` |
| IA_AirshipExit | Bool | F | Y | `Started` |

---

## 6. Multiplayer constraints

**Latency** (`mp_test.md`, run 3; times after the client's input, one frame = 0.033 s). The host pilot has no network
delay.

| | No lag | 100 ms each way |
|---|---|---|
| Client's controls change | 0.033 s | 0.033 s |
| Client's own cosmetics (wheel, fans, nozzles) | 0.066 s | 0.066 s |
| Server applies the controls | 0.066 s | 0.17-0.2 s |
| Host sees the client's cosmetics | 0.10 s | 0.2-0.23 s |
| Client sees its own hull respond | 0.066-0.17 s | 0.30-0.37 s |

* **Predicted on the pilot's machine:** the shaped controls and everything cosmetic (rig, Niagara, HUD, camera FOV and arm),
  the boost gate (from the replicated fuel), and the pilot's own cannon shot (`RequestFire` plays it at once; the multicast
  skips it).
* **Not predicted:** the hull's motion. The client's copy is a simulated body with gravity off. Default physics replication
  corrects it toward the server's state. With lag it judders in bursts and hard-snaps now and then (once 6.3 m at 54 m/s).
  The camera rides that copy and the position lag (5/s) hides most of it.
* **What that means for a scheme:**
  * Anything whose fun depends on the hull reacting within a frame works for the host but feels 0.3 s late for a client on
    a 200 ms RTT: twitch yaw aiming, drift release timing, last-moment dodges.
  * Prefer intent and targets from the pilot (orders, headings, charges) executed smoothly by the server, plus instant,
    rich local feedback: camera, HUD, rig, FX, rumble.
  * Never run a closed loop on the pilot's machine against the ship's replicated state. A client heading-hold sees the yaw
    a round trip late and overshoots.
* **Same presets everywhere.** Cosmetics on every machine use the presets of the replicated `ControlScheme`. Per-machine
  `Aura.Airship.Set` changes only diverge cosmetics.
* **Scheme switch while flying.** The client keeps sending old-scheme packets until `OnRep_ControlScheme` arrives (half an
  RTT). Tag packets with the scheme id (5.2) or make the wire meaning identical across schemes.
* **Late joiners** get `RepInput`, `BoostFuel`, `PilotCharacter`, `bIsDead` and the scheme by initial replication. A rep
  notify can run before the actor's BeginPlay on a new client, so applying a scheme must not depend on BeginPlay state, and
  BeginPlay must apply the current scheme again (it must be idempotent). The shaping filters start at 0 and catch up within
  about 0.5 s (cosmetic only).
* **Forces only on the server.** Clients must never add flight forces; they would fight the corrections. A client-side
  impulse (the cannon recoil, `Pawn.cpp:1505-1509`) is acceptable because the server applies the same impulse.

---

## 7. Feedback ("juice")

### 7.1 What exists

| Channel | What | Where |
|---|---|---|
| Camera | FOV +10 with forward speed (20-48 m/s), +12 boost, -15 aim; arm +10 m on boost; position lag trails 10-17 m at speed; level horizon | `Pawn.cpp:1603-1616`, `:183-187` |
| Niagara | Pods `Thrust` 0..1.5 (rises with lift, boost, throttle and the outer side in turns), fans `Thrust` 0..1, `Boost` 0..1 on all six | `Pawn.cpp:1520-1549` |
| Rig | Nozzle gimbal ±5 (throttle, boost, brake, strafe, steer), petal flare -10..35, turbine yaw ±12 at 40 deg/s, rotor spin 300-1800 deg/s (x2 boost, reverses with the fans), rudder -25 x steer, wheel -270 x steer on an overshooting spring, cannon aim slew and 45 cm recoil, searchlight pan | `Anim.cpp:167-261` |
| Hull | Bank 18 deg into turns, nose dip on acceleration and flare on braking (4a), boost kick +4 m/s, drift kick +6 m/s, cannon recoil 0.8 m/s per cannon, wind sway at low speed, ground cushion | `FC.cpp` |
| HUD | Hull bar + value, boost bar + % (BOOST tag while boosting), speed m/s, height above ground, PORT / STBD reload (READY or seconds; the facing side as a tag) | `HUD.cpp:122-266` |
| Blueprint hooks | `BP_OnCannonsFired` (every machine), `BP_OnHullImpact` (server only), `BP_OnAirshipDied` | `Pawn.h:261-269` |

Missing from the research plan (research_flight 5, 7): camera shakes, the cannon FOV punch, drift-kick FOV, rumble, the
side-hop, the horn (no input action exists), dust at the ground (would need an asset).

### 7.2 What could be added without assets

| Idea | How | Machine |
|---|---|---|
| Camera shake | A decaying "trauma" value in `UpdateCamera`, shaking the camera's relative rotation / location with `FMath::PerlinNoise1D` (no shake class or asset needed). Kick it on boost start, own cannon fire, hull hits (every machine gets `OnHullHit`, so the pilot sees its own hits without an RPC), drift kick and hard landings. | pilot |
| FOV kicks | Short additive FOV pulses: +6 on boost start, -3 on firing, +5 on the drift kick, decaying over 0.3-0.8 s | pilot |
| Camera roll / look-ahead | A few degrees of camera roll with the bank (for example 0.2 x bank, max 4 deg); yaw look-ahead into the turn (offset by steer or yaw rate) | pilot |
| Rumble | `APlayerController::PlayDynamicForceFeedback` (intensity and duration, no asset) on boost, firing, hits, drift kick | pilot |
| HUD | Speed tape or needle, throttle telegraph, drift charge bar, heading-target marker and crosshair, broadside-ready flash, boost-ready flash, hit flash on a health drop | pilot |
| Thruster FX intensity | Pulse the existing `Thrust` (within 0..1.5) and `Boost` (0..1) parameters on events: a boost start spike, a drift-kick burst, a brake flare on the front pods | every machine |
| Rig accents | Wheel spun hard during a drift, rudder to its ±30 limit, nozzles kicked sideways in a slide, petal flare spike on a kick; all from the cosmetic state, inside the rig ranges | every machine |
| Hull "weight" | Small real impulses on events (like the existing kicks); server only, with `NoteFlightKick` | server |

Audio is out of scope: no airship sounds exist and no new assets may be made.

---

## 8. Contract notes for the implementer and the PIE harness

The contract (names are fixed):

* `EAirshipControlScheme : uint8 { Classic = 0 "Classic (v1)", Galleon = 1, SkyRacer = 2 "Sky Racer", PointFly = 3
  "Point & Fly" }` in `Types.h`.
* `AAirshipPawn::ControlScheme` (EditAnywhere, BlueprintReadOnly, ReplicatedUsing = OnRep_ControlScheme, category
  "Airship|Controls", default Classic; Point & Fly since the polish after judging, CPP_NOTES 14.12), `SetControlScheme` (authority applies and replicates; a client only logs a
  warning), `GetControlScheme`.
* Applying a scheme (BeginPlay, SetControlScheme, OnRep) sets every scheme-owned tunable from a compiled-in preset table.
  Classic restores the exact v1 values, so switching is order-independent. Scheme-local runtime state (throttle order,
  drift charge, heading target, free look) resets on a switch and on board / exit.
* Console `Aura.Airship.Scheme <0-3>` (server, all ships; no argument prints each ship's scheme). It belongs next to the
  other commands in `Sub.cpp:476-824`.
* `FAirshipFlightTelemetry` gains: uint8 `Scheme`; float `ThrottleOrder` (Galleon -1..1, else -2); float `DriftCharge`
  (Sky Racer 0..1, else 0); bool `bHeadingTargetActive` + float `HeadingTargetDeg` (world deg); bool `bFreeLook`.

Notes from the code:

* **Preset contents**: include every tunable any scheme touches: flight component, pawn camera and cannon values, the
  `CameraBoom` lag values (component properties, 2.2), anim instance values if a scheme changes the rig mapping, and the
  base-fix switches of section 4 (off in Classic). Call `Flight->ApplyBodySettings()` after changing body values
  (`OnTuningChanged`, `Pawn.cpp:2238-2248`). A scheme switch overwrites any `Aura.Airship.Set` tuning.
* **Telemetry fields** go through `FillTelemetry` / `GetFlightTelemetry`; Python reads them with
  `get_flight_telemetry().export_text()`.
* **Harness** (as `as_45_pie_mp.py`): inject raw IA values on the pilot's local player every frame
  (`inject_input_vector_for_action`; one tick per call), set the camera through the PlayerController's control rotation
  every frame or inject `IA_AirshipLook` (section 3, harness note). `DebugSetInput` skips pilot-side shaping: use it only
  for Classic cross-checks. Taps need a one-frame injection with at least one empty frame after it, so `Completed` fires
  and the next tap reads as a new press.
* **Measure first** (4f row 0): log the principal inertia, mass-frame rotation and COM. Every pitch number in this document
  that depends on 4a cause 1 should be re-checked in PIE.

---

## 9. Sims

| File | What |
|---|---|
| `Docs/Airship/controls/sims/baseline_sim.py` | Python 6-DOF port of the current `UpdateBoostServer` / `ShapeControls` / `ApplyForces` (commit e4c98b7 code, unchanged at 8f01bca), plus the base-fix switches of section 4 under the same names (`bFanTorqueFeedForward`, `HoldBrakeAccel`, `VertBrakeAccel`, `LiftTauRelease`, `bBrakeHoldLead`, `BrakeFadeSpeed`, `StationKeepGain/Speed/AccelMax`; all off = v1). `bHullAxisInertia` is modelled by the `code_inertia=` argument: `None` = fixed, `INERTIA_UCX_CHAOS` = v1 as PIE runs (4a). Default inertia `INERTIA_UCX` (copied from `hull_mass.json`; its product of inertia is ignored). No wind, collisions, passengers or replication. |
| `Docs/Airship/controls/sims/baseline_checks.py` | Prints every sim number in this document (`python3 Docs/Airship/controls/sims/baseline_checks.py`, about 2 s, one process) |
| `Docs/Airship/sims/fix3/cap_model.py`, `scenarios.py` | Impact cap model (4e) |
| `Docs/Airship/controls/sims/mass_props.py`, `hull_mass.json` | The hull's mass properties as Chaos builds them from the UCX convexes (not written for this document; used for 4a) |
| `Docs/Airship/sims/fix_flight/sim_fixed.py` | The older port (before fix rounds 1-3); superseded by `baseline_sim.py` |

The sims use the UCX hull inertia (diagonal 1.21e10, 6.57e10, 6.75e10 kg·cm²), COM (-170, 0, 0), 40 t, 30 Hz. Run as v1
(`code_inertia=INERTIA_UCX_CHAOS`), they match the v1 PIE runs within 0.3 m/s on speeds, 0.5 deg RMS on the full-throttle
pitch, the turn bank and the turn rate exactly, and 0.6 m/s on the lift release (section 4a table). They are good for
comparing schemes against each other and against v1; PIE stays the judge.
