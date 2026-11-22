# Airship pawn: flight model, network model, camera (research)

Scope: the drivable airship pawn (root = physics-simulated `UStaticMeshComponent`, 8 convex hulls). Engine: UE 5.8
source at `/mnt/new_partition/5.8/Engine` (all `file:line` below are relative to `Engine/Source/Runtime/` unless a
path says otherwise). Project physics config: `_AirshipWork/Config/DefaultEngine.ini` has **no**
`[/Script/Engine.PhysicsSettings]` section, so engine defaults apply (sync physics, no substepping, see 4.1).
Numbers in 3.11 were checked with `/mnt/new_partition/UnrealProjects/_AirshipWork_logs/scratch/flight/sim_final.py`
(1D/2D sim of the equations below, not engine code). Anything not read in engine source or simulated is marked
[unverified].

## 0. Decisions (short)

| Topic | Decision |
|---|---|
| Force code location | Game-thread `Tick` (APawn default `TG_PrePhysics`), **authority only**. Gains kept soft (loop bandwidth <= 3 rad/s) so a 1/30 s step is safe. Upgrade path: `AsyncPhysicsTickActor` (per physics step) if needed. No project-wide async physics. |
| Force structure | Every axis is an **acceleration command** (input + P/PD loop). Physical actuators (4 thrusters, 2 fans, gimbals) get what they can deliver via `AddForceAtLocation`; the remainder is applied as COM force ("air grip") or torque (rudder, hidden gyro), capped. Sign mistakes in actuator geometry then only cost authority, never stability. |
| Feel targets (sim) | Hover stable; top 47.8 m/s; 0->80 % in 3.6 s; boost 89 m/s; yaw 30/45/35 deg/s (rest/15 m/s/top); bank 18 deg; full-steer slip 23-30 deg at top speed (drift); coast to half speed 11.5 s; brake 48 m/s->0 in 2.0 s. |
| Network | **Server-authoritative physics**. Pilot input -> `UFUNCTION(Server, Unreliable)` (6-8 bytes/tick). State back via engine `ReplicatedMovement` + physics replication, mode **`EPhysicsReplicationMode::Default`** (legacy, time-based, works with sync physics), A/B test `PredictiveInterpolation`. Cosmetics (fans, wheel, thrusters, VFX, camera) from local input on the pilot's machine, from a replicated input copy (`COND_SkipOwner`) elsewhere. Fallback: client-authoritative state push (6.5). Resimulation / Mover: no. |
| Camera | Spring arm on the root, 65 m arm, control-rotation free look with auto-recenter, position lag 5, rotation lag 7, roll not inherited, FOV 85 -> 107 with speed/boost. |

## 1. Controls

Enhanced Input (project already uses it: `Source/Aura/Private/PlayerInput/MyPlayerController2.cpp:133-141`). The ship
adds its own `IMC_Airship` at priority 1 when possessed (`APawn::NotifyControllerChanged` `Engine/Classes/GameFramework/Pawn.h:397`
or `PawnClientRestart` `Pawn.h:418`) and removes it on unpossess; it binds in `SetupPlayerInputComponent` (`Pawn.h:486`).

| Action (IA) | Value | Keyboard + mouse | Gamepad | Notes |
|---|---|---|---|---|
| IA_AirshipThrottle | Axis1D | W = +1, S = -1 (Negate) | LS Y | hold-to-thrust; S at low speed = reverse (max 0.5 g, 18 m/s) |
| IA_AirshipSteer | Axis1D | D = +1, A = -1 | LS X (DeadZone 0.15, ResponseCurveExponential 1.6) | yaw-rate command |
| IA_AirshipLift | Axis1D | Space = +1, Left Ctrl or C = -1 | RT = +, LT = - (analog) | climb/descend speed; release = altitude hold |
| IA_AirshipStrafe | Axis1D | E = +1, Q = -1 | D-pad L/R | lateral slide 12 m/s; double-tap = side-hop |
| IA_AirshipBoost | Bool (hold) | Left Shift | A / Cross | uses BoostFuel attribute |
| IA_AirshipBrake | Bool (hold) | X | B / Circle | air brake + hover hold; with steer = drift |
| IA_AirshipLook | Axis2D | Mouse XY | RS (ResponseCurveExponential 2.0) | camera orbit only, never steers |
| IA_AirshipZoom | Axis1D | Mouse wheel | D-pad U/D | arm 40-120 m |
| IA_AirshipFire | Bool (pressed) | LMB | RB | fires the 2 cannons on the side the camera faces |
| IA_AirshipAim | Bool (hold) | RMB | LB | cannons track camera within their arcs, camera tightens |
| IA_AirshipHorn | Bool (pressed) | H | X / Square | steam whistle + puff (pure fun, cosmetic) |
| IA_AirshipExit | Bool (pressed) | F | Y / Triangle | leave the wheel |

Modifiers/triggers used exist in 5.8: `UInputModifierNegate`, `UInputModifierSwizzleAxis`, `UInputModifierDeadZone`,
`UInputModifierResponseCurveExponential`, `UInputTriggerPressed/Down/Tap` (`Engine/Plugins/EnhancedInput/Source/EnhancedInput/Public/InputModifiers.h:170,253,306,412`, `InputTriggers.h:262,279,365`).

Why this is fun:
* W/S + A/D is boat/car muscle memory; the ship pivots at rest (fans counter-rotate), so it is never stuck.
* Release Space/Ctrl and the ship holds its altitude: beginners fly in 2D, good pilots use height (clearance floor
  hops the ship over platforms automatically, 3.3). Analog triggers on pad make altitude expressive.
* Mouse is camera only: you steer with keys while looking at a target, and LMB fires the broadside **on the side you
  look at** ("look and shoot"), which suits fixed side cannons. Aim mode lets the cannons track inside their arcs.
* Boost has a meter (risk/reward), brake+steer drifts and a drift longer than 1.2 s pays a small drift boost.
* Strafe (Q/E) and side-hop let you dodge or line up a broadside without turning.
* Visible weight: bank into turns, nose dips when accelerating and flares when braking, spool-up lag, wind sway.

## 2. Frames, positions, signs

* UE body frame: X forward, Y right, Z up, cm. Blender (X fwd, Y left, Z up, m) -> UE: `X = 100x, Y = -100y,
  Z = 100z` (same rule in `Docs/Airship/research/sm_airship_islands.json` "coords").
* Positions (UE cm, component space of the root; read the real ones at BeginPlay from sockets/bones, do not hard-code):

| Part | Brief (Blender m) | UE cm | rig data (`research/rig_clearance.json`, rig agent) |
|---|---|---|---|
| Thruster FL | (3.8, +4.8, -1.0) | (380, -480, -100) | pivot (3.833, 4.656, -0.934) |
| Thruster FR | (3.8, -4.8, -1.0) | (380, 480, -100) | pivot (3.833, -4.918, -1.130) |
| Thruster RL | (-7.2, +5.4, -1.2) | (-720, -540, -120) | pivot (-7.167, 5.130, -1.204) |
| Thruster RR | (-7.2, -5.4, -1.2) | (-720, 540, -120) | pivot (-7.167, -5.768, -1.239) |
| Fan L | (-17.3, +7.6, 1.4) | (-1730, -760, 140) | yaw pivot (-17.446, 7.6, 1.4), spin axis X, blade tip r 2.75 m |
| Fan R | (-17.3, -7.6, 1.4) | (-1730, 760, 140) | yaw pivot (-17.446, -7.6, 1.4) |
| Rudder hinge | - | (-1636, 0, 140) | aft-face hinge, +-54 deg (or leading edge +-24 deg) |

* Rig data says the pods' nozzles rest **8 deg aft** and the hull leaves only ~0-9 deg of gimbal (per pod), and the fan
  housings hit the hull at 0 deg yaw. So the model treats gimbal angles and fan yaw as parameters
  (`ThrusterGimbalMaxDeg`, `FanYawMaxDeg`) and works with 0. **Physics uses body-up as the pod thrust axis plus only the
  commanded gimbal**, not the 8 deg rest tilt (a real 8 deg lean would push the hover forward at 0.14 g and make the fans
  idle in reverse). The visual rest tilt is cosmetic.
* Sign facts (from UE math, verify once in PIE with debug arrows): positive world `w.Z` = yaw right (FRotator yaw up);
  FRotator roll positive = right wing down; FRotator pitch positive = nose up. Torque convention of the engine:
  `Torque = (P - COM) x F` (`PhysicsCore/Private/ChaosEngineInterface.cpp:970`). Do attitude and allocation in
  **vector form** (quaternion error, `r x F`), never with hand-written Euler signs.

## 3. Force model (server, every frame)

Notation: m = `GetMass()`, g = 980 cm/s^2, W = m g, R = component rotation, `F^`, `R^`, `U^` = ship forward/right/up
(world), v = `GetPhysicsLinearVelocity()` (COM velocity), w = `GetPhysicsAngularVelocityInRadians()`, COM =
`GetCenterOfMass()`, body velocity `vb = R^-1 v = (vf, vl, vzb)`, vz = v.Z (world), I = `GetInertiaTensor()`
(local diagonal, kg cm^2). `dt` = physics step of this frame (4.1: `min(DeltaSeconds, MaxPhysicsDeltaTime)`).
Accelerations are in cm/s^2; forces = m * a (kg cm/s^2; 1 N = 100).

### 3.1 Pipeline
1. Read state (above). 2. Inputs -> spool filters (3.2). 3. Gimbal + fan housing angles from smoothed input.
4. Vertical command (3.3). 5. Attitude command (3.4). 6. Thruster mixing (3.5) + actuator lag.
7. Forward thrust + fans + yaw allocation (3.6, 3.7). 8. Lateral grip (3.8). 9. Drag, caps, extras (3.9, 5).
10. Apply: 4x thruster + 2x fan `AddForceAtLocation(F_world, P_world)`; one `AddForce(a, NAME_None, true)` for all
COM accelerations (grip, drag, wind); one `AddTorqueInRadians(alpha, NAME_None, true)` for all residual angular
accelerations (gyro, rudder, wind). With `bAccelChange = true` the engine multiplies by mass / world inertia itself
(`ChaosEngineInterface.cpp:941-944`, `:1029-1031`; force accel change multiplies by M at `:943`), so these terms are mass-independent.
11. Write cosmetic outputs (section 8).

### 3.2 Input shaping (all machines, cosmetics use the same filters)
First-order filter `x += (target - x) * (1 - exp(-dt/tau))`:

| Signal | tau up / down (s) | Notes |
|---|---|---|
| throttle `thr` | 0.30 / 0.45 | spool-up lag the pilot feels |
| boost `bst` (0..1) | 0.15 / 0.60 | punchy in, slow out |
| lift `lift` | 0.25 / 0.25 | |
| steer `str` | 0.15 / 0.15 | also drives wheel, fan yaw, rudder |
| strafe `stf` | 0.20 / 0.20 | |
| thruster force (per pod, actuator) | 0.10 / 0.15 | inside the loops, stable (sim) |

### 3.3 Vertical: collective, altitude hold, caps
```
vz* = lift * (lift > 0 ? ClimbRate : DescendRate)          (12 / 15 m/s)
if |lift| < 0.05:  on release capture Zhold = Z + vz*0.5 s; vz* = clamp(Kz*(Zhold - Z), +-HoldMaxSpeed)
brake held:        Zhold = Z at press (hover hold)
floor:  vz* = max(vz*, Kfloor*(MinClearance - hmin))       hmin = min ground distance under the 4 pods (5.6 traces)
ceiling: vz* = min(vz*, Kceil*(Zceil - Z))
Fv_world = m*(g + Kvz*(vz* - vz))   clamped to [0.25 W, 1.9 W]
Fv_body  = Fv_world / max(0.5, U^.Z)                        tilt compensation
```
Sim: 20 m step -> overshoot 0.13 m; climb command reaches 90 % in 1.5 s; same at dt 1/30 and 1/120.

### 3.4 Attitude: lean targets + PD (vector form)
Targets (deg):
```
bank*  = BankMax * str * clamp(vf / 2000, 0.25, 1) + 6*stf      BankMax 18 (drift 22, boost 12)
pitch* = clamp(-PitchPerG * a_cmd / g, -8, +6) - 3*bst + 3*lift  a_cmd = commanded forward accel (3.7), so
                                                                 accelerating dips the nose, braking flares it
no input: bank* = pitch* = 0 (auto-level)
```
Error: `q_des = FRotator(pitch*, CurrentYaw, bank*).Quaternion()`, `q_e = q_des * q_cur.Inverse()` (shortest arc),
`e = axis * angle` (world, rad). Then
```
alpha_tilt = F^*(KpR*(e.F^) - KdR*(w.F^)) + R^*(KpP*(e.R^) - KdP*(w.R^))
```
Engine `AngularDamping` 0.5 is on top (it is a per-step multiplier `w *= max(0, 1 - c*dt)`,
`Experimental/Chaos/Private/Chaos/PBDRigidsEvolutionGBF.cpp:932-934`, stable at any dt).
Roll KpR 6.25 /s^2, KdR 4.5 /s (w_n 2.5, zeta 0.9); pitch KpP 4.0, KdP 3.2 (w_n 2.0, zeta 0.8). Routh check with the
0.12 s actuator lag: Kd > tau*Kp holds (4.5 > 0.75). Sim: 18 deg bank step reaches 90 % in 1.5 s, no overshoot.

### 3.5 Thruster mixing (4 pods -> vertical force + roll/pitch torque)
Per pod i: `r_i` = pod pivot - COM (body), `d_i` = thrust direction (body) = `normalize(tan(gp_i), tan(gr_i), 1)` with
gimbal pitch `gp` (+ = thrust leans forward) and roll `gr` (+ = leans right), total tilt <= ThrusterGimbalMaxDeg.
```
gp_i = 10*thr + 5*bst - 6*brake                (deg, clipped to the rig limit)
gr_i = 12*stf + 5*str*(front ? +1 : -1)        (front/rear opposite = small yaw assist)
A (3x4):  A0i = d_i.Z ;  A1i = (r_i x d_i).X ;  A2i = (r_i x d_i).Y
tau_body = I .* (R^-1 alpha_tilt)               (x, y only)
f_c = A^T (A A^T)^-1 [Fv_body, 0, 0]            collective part (= hover shares, exact for the real COM)
f_a = A^T (A A^T)^-1 [0, tau_x, tau_y]          attitude part
s   = largest s in [0,1] with fmin <= f_c + s*f_a <= fmax for every pod
f_i = clamp(f_c + s*f_a)                        fmin 0.02 W, fmax 0.55 W per pod
residual alpha_gyro_tilt = (1 - s) * (R alpha_tilt), capped at GyroTiltMax 0.8 rad/s^2
```
`A A^T` is 3x3 symmetric; write a small 3x3 solve (layout asymmetry from the rig data is handled for free).
Symmetric sanity check: with COM at x = -170 cm the hover share is 0.25 W per pod; COM at x = 0 gives front 0.33 W,
rear 0.17 W. Authority at hover (estimated inertia, 3.10): roll 1.06 rad/s^2, pitch 0.33 rad/s^2 (the 52 m hull is
long, so pitch leans also use the gyro residual).

### 3.6 Fans, rudder, yaw
Yaw-rate target and command:
```
r*     = str * Rmax(vf)   Rmax: 30 deg/s at 0, 45 at 15 m/s, 35 at 48 m/s (linear); drift 50; boost 25
alpha_z = Kr*(r* - w.Z) + c_ang*r*     Kr 3 /s; c_ang = AngularDamping (feed-forward so steady state is exact)
tau_z  = Izz * clamp(alpha_z, +-AlphaYawMax 1.0 rad/s^2)
```
Fans: housing yaw from input (visual and physics agree): `psi = -FanYawMaxDeg * str` (FanYawMaxDeg 25 if the rig allows,
else 0). Fan i force (body) `F_i = Fx_i * (1, tan psi, 0)`, applied at the fan pivot.
```
Fx_total = m*a_cmd - sum_i(f_i * d_i.X)          forward demand minus pod forward components
tau_known = sum over pods+fans (r x F).Z with D = 0, + Izz*RudderAuthority*(vf/4800)^2*str   (rudder, capped 1.2 rad/s^2)
D = clamp((tau_z - tau_known) / yfan, so |Fx_L|,|Fx_R| <= FanMax)     yfan = 760 cm (half spacing)
Fx_L = Fx_total/2 + D/2 ; Fx_R = Fx_total/2 - D/2                     (D > 0 -> left fan harder -> yaw right)
gyro: alpha_gyro_z = clamp((tau_z - tau_known - yfan*D)/Izz, +-GyroYawMax 0.5 rad/s^2)
```
At rest D makes the fans counter-rotate (pivot turn). Fan authority (estimate): housings 25 deg at full thrust
0.39-0.55 rad/s^2, pivot differential 0.45-0.61 rad/s^2, rudder 0.6 at cruise. Sim: 45 deg/s reached (90 %) in 0.97 s,
35 deg/s in 0.80 s.

### 3.7 Forward thrust and drag
Arcade cap by thrust fade (keeps long coasting, unlike a drag cap):
```
a_fan(vf) = AFan * thr * max(0, 1 - (vf/VTop)^6)            forward; boost uses AFanBoost, VTopBoost
reverse (thr < 0): a_fan = AFanRev * thr * max(0, 1 - (|vf|/VTopRev)^2)
brake: thr target = -0.5, extra a = -Kbrake*vf
a_drag = -(C1*vf + C2*vf*|vf|)  (body X) ;  -C1*vl (body Y) ;  vertical drag lives in 3.3
a_cmd = a_fan + a_drag (+ brake term)   (used for pitch lean and the fan demand)
hard cap: if |v| > 110 m/s add -3*(|v| - 11000) along v
```
Sim (dt 1/30 and 1/120 identical): top 47.8 m/s, 0->80 % 3.6 s; boost top 89.3 m/s; cruise 48 -> 80 m/s on boost 2.6 s;
coast 48 -> 24 m/s 11.5 s; boost end 89 -> 55 m/s 6.8 s; brake 48 -> 0 m/s 2.0 s over 34 m.

### 3.8 Lateral grip and drift
```
vl* = stf * StrafeSpeed (12 m/s)
a_lat_cmd = clamp(Klat*(vl* - vl), +-ALatMax)
a_lat_phys = sum(F_i.Y)/m          from pod gimbals + fan housings
a_grip = a_lat_cmd - a_lat_phys    applied at COM along R^  (accel change)
redirect: if a_grip opposes vl, add Eta*|a_grip| along F^ (turning carves instead of scrubbing all speed)
```
| Mode | Klat (/s) | ALatMax | Eta | yaw Rmax | Result (sim, full steer at top speed) |
|---|---|---|---|---|---|
| grip | 4.0 | 2.5 g | 0.35 | 35 deg/s | speed held 49-51 m/s, slip 7/13/23/30 deg at 1/2/4/8 s |
| drift (brake + steer) | 1.2 | 1.2 g | 0.40 | 50 deg/s | slip 17/46/96 deg at 1/2/4 s: a real slide; spins out if held > 2 s |
| boost | 3.0 | 2.0 g | 0.30 | 25 deg/s | 92 m/s, slip 9/20/39 deg at 1/2/4 s (fuel lasts 4 s) |

### 3.9 Damping and caps
* Engine `AngularDamping` 0.5 alive, 0.12 dead (`SetAngularDamping`). `LinearDamping` 0 alive (drag is ours),
  0.02 dead. Formula is `v *= max(0, 1 - LinearDamping*dt)` (`PBDRigidsEvolutionGBF.cpp:928-930`).
* `SetPhysicsMaxAngularVelocityInDegrees(120)` alive, 180 dead.
* No engine linear speed cap exists on `FBodyInstance` (none found in `BodyInstance.h`); caps are 3.7.
* CCD: `bUseCCD` on the root (`BodyInstance.h:418`), 89 m/s * 1/30 s = 3 m per step [cost unverified].

### 3.10 Mass, COM, inertia
* `SetMassOverrideInKg(NAME_None, 40000, true)` (`PrimitiveComponent.h:2857`). Inertia scales with the override
  (`Engine/Private/PhysicsEngine/BodyUtils.cpp:74-76`). All loops use m and I read at runtime, so handling is the same
  for 20-60 t; mass only changes collisions with other dynamic bodies.
* COM: put it at the thrust centroid in X so hover shares are even: desired local COM (-170, 0, 0) [hull-dependent].
  `SetCenterOfMass(Offset)` sets `COMNudge` (offset from the computed COM, actor space, `BodyUtils.cpp:78-79`,
  `Engine/Private/PrimitiveComponentPhysics.cpp:508-516`). At BeginPlay (body simulating):
  `Offset = DesiredLocal - (InverseTransformPosition(GetCenterOfMass()) - CurrentNudge)`. Moving the COM also adds
  m*d^2 to inertia (`BodyUtils.cpp:102-110`).
* Inertia estimate (box 52x24x17 m x 0.6, 40 t): Ixx 1.73e10, Iyy 5.99e10, Izz 6.56e10 kg cm^2 [estimate; log
  `GetInertiaTensor()` once]. Keep `InertiaTensorScale` (1,1,1): it rescales via an "equivalent box"
  (`BodyUtils.cpp:81-95`) and is hard to reason about; tune gains instead.
* Physical material on the hulls: Friction 0.2, Restitution 0.35, `RestitutionCombineMode` Max with override
  (`PhysicsCore/Public/PhysicalMaterials/PhysicalMaterial.h:115,131,135,139`).

### 3.11 Default parameters (UAirshipFlightSettings or UPROPERTYs on the pawn)

| Name | Default | Unit | Notes |
|---|---|---|---|
| MassKg | 40000 | kg | 20000-60000 fine |
| DesiredCOMLocal | (-170, 0, 0) | cm | thrust centroid X |
| ClimbRate / DescendRate | 1200 / 1500 | cm/s | |
| Kvz / Kz / HoldMaxSpeed | 2.0 / 0.8 / 800 | 1/s, 1/s, cm/s | |
| FvMin / FvMax | 0.25 / 1.9 | x W | collective clamp |
| PodFMin / PodFMax | 0.02 / 0.55 | x W | per pod |
| MinClearance / Kfloor | 600 / 1.5 | cm, 1/s | auto hop over platforms |
| Zceil / Kceil | map value / 1.0 | cm, 1/s | |
| KpR / KdR | 6.25 / 4.5 | 1/s^2, 1/s | roll |
| KpP / KdP | 4.0 / 3.2 | 1/s^2, 1/s | pitch |
| BankMax (grip/drift/boost) | 18 / 22 / 12 | deg | |
| PitchPerG / pitch clamp | 8 / -8..+6 | deg per g, deg | |
| GyroTiltMax / GyroYawMax | 0.8 / 0.5 | rad/s^2 | hidden stabiliser caps |
| AFan / VTop | 1.35 g = 1323 / 5000 | cm/s^2, cm/s | fade exponent 6 |
| AFanBoost / VTopBoost | 2.0 g = 1960 / 9600 | cm/s^2, cm/s | |
| AFanRev / VTopRev | 0.5 g / 1800 | cm/s^2, cm/s | |
| C1 / C2 | 0.05 / 3e-6 | 1/s, 1/cm | |
| Kbrake | 0.9 | 1/s | |
| FanMax (each, normal/boost) | 0.68 / 1.0 | x W | from AFan / 2 |
| FanYawMaxDeg | 25 (0 if rig cannot) | deg | |
| ThrusterGimbalMaxDeg | 15 (rig: 0-9) | deg | |
| Kr / AlphaYawMax | 3.0 / 1.0 | 1/s, rad/s^2 | |
| Rmax at 0 / 15 / 48 m/s | 30 / 45 / 35 | deg/s | drift 50, boost 25 |
| RudderAuthority / ref speed | 0.6 / 4800 | rad/s^2, cm/s | capped 1.2 |
| Klat / ALatMax / Eta | 4.0 / 2.5 g / 0.35 | | grip mode |
| StrafeSpeed | 1200 | cm/s | |
| AngularDamping alive / dead | 0.5 / 0.12 | 1/s | engine |
| MaxAngularVelocity alive / dead | 120 / 180 | deg/s | |

## 4. Where to apply forces (variable frame rate, 5.8 facts)

### 4.1 What the engine does with a game-thread force
* Project = engine defaults: `bSubstepping=false`, `bTickPhysicsAsync=false`, `MaxPhysicsDeltaTime=1/30`,
  `AsyncFixedTimeStepSize=1/30`, `MaxSubstepDeltaTime=1/60`, `MaxSubsteps=6`
  (`Engine/Private/PhysicsEngine/PhysicsSettings.cpp:22-27`; `Engine/Config/BaseEngine.ini:3406-3408` only sets gravity).
* Physics dt per frame = `min(DeltaSeconds, MaxPhysicsDeltaTime)` (no substepping) or
  `min(DeltaSeconds, MaxSubsteps*MaxSubstepDeltaTime)` (`PhysicsCore/Private/ChaosScene.cpp:338-346`). Below 30 fps the
  whole sim runs slower than real time (existing project behaviour). Set up before `TG_PrePhysics`
  (`Engine/Private/LevelTick.cpp:1740`, `PhysLevel.cpp:137-212`). Use the same formula for `dt` in 3.x.
* `AddForce*` from the GT accumulates into the particle acceleration (`F * InvM`,
  `Experimental/Chaos/Public/Chaos/ParticleHandle.h:3593-3597`), is held constant over the frame's step, **copied into
  every substep** (impulses are not) (`Experimental/Chaos/Private/Chaos/ChaosMarshallingManager.cpp:325-361`), averaged
  over game frames in async mode (`ApplyDynamicsWeight`, `Experimental/Chaos/Private/PBDRigidsSolver.cpp:1582,1600`,
  `ParticleHandle.h:3604-3614`), and cleared after the step (`Experimental/Chaos/Public/Chaos/PBDRigidsEvolutionGBF.h:243-249`).
  The `bAllowSubstepping` argument is ignored by Chaos (`ChaosEngineInterface.cpp:932-950`).
  => Tick-computed forces are a zero-order hold at frame rate. With loop bandwidth w <= 3 rad/s, w*dt <= 0.1 at 30 Hz:
  the sim gives the same response at dt 1/30 and 1/120 (3.3-3.8).
* `FBodyInstance::AddCustomPhysics` is **not** a substep hook in Chaos: `FPhysScene_Chaos::AddCustomPhysics_AssumesLocked`
  just calls the delegate once, now, with the frame dt (`Engine/Private/PhysicsEngine/Experimental/PhysScene_Chaos.cpp:1665-1668`). Do not use it.

### 4.2 Options

| Option | How | Verdict |
|---|---|---|
| A. Tick (TG_PrePhysics), authority | 3.1 as written; APawn ticks `TG_PrePhysics` by default (`Engine/Private/Pawn.cpp:51`) | **use (v1)** |
| B. Per physics step on the GT | `bAsyncPhysicsTickEnabled` (`Actor.h:699`) + override `AsyncPhysicsTickActor(DeltaTime, SimTime)` (`Actor.h:2930`). Runs once per physics step/substep from a `RunOnFrozenGameThread` sim callback (`PhysScene_Chaos.cpp:146-243`, dispatched per step `Experimental/Chaos/Private/Chaos/Framework/PhysicsSolverBase.cpp:713-717`), also in sync mode. Must use `GetBodyInstanceAsyncPhysicsTickHandle()` (`PrimitiveComponent.h:2349`) -> `FRigidBodyHandle_Internal` (`GetX/GetR/GetV/GetW/AddForce/AddTorque/M/CenterOfMass`, `Experimental/Chaos/Public/PhysicsProxy/SingleParticlePhysicsProxy.h:237,258,316,356,706,757,930,978`); GT physics getters fire ensures there (`PhysicsSolverBase.cpp:156-158`). Force at a point = `AddForce(F)` + `AddTorque((P - COMworld) x F)`. | upgrade path if low-fps feel is bad |
| C. Project async physics | `bTickPhysicsAsync` + `AsyncFixedTimeStepSize` (`Engine/Classes/PhysicsEngine/PhysicsSettings.h:333,337`) | no: project-wide change (GCs, Burrower ragdoll, CMC, interpolation) |
| D. Project substepping | `bSubstepping`, `MaxSubstepDeltaTime`, `MaxSubsteps` (`PhysicsSettings.h:325,341,345`) | optional later, only if the game often runs < 30 fps; test the whole game |
| E. `bEnableEnhancedDeterminism` | `PhysicsCore/Public/PhysicsSettingsCore.h:49` -> `SetIsDeterministic` (`ChaosScene.cpp:94`) | off: no use without resimulation |

## 5. Cheap fun features (numbers)

| # | Feature | Implementation | Defaults |
|---|---|---|---|
| 5.1 | Boost | `bst` filter; AFanBoost/VTopBoost; on start an impulse along F^ (`AddImpulse(m*dv*F^)`, `PrimitiveComponent.h:1692`); BoostFuel attribute in the ship's attribute set (server gates) | fuel 100, drain 25/s, regen 12/s after 1 s, min 20 to start, kick dv 400 cm/s; FOV +12 deg (in 0.25 s, out 0.8 s), arm +1000 cm, Perlin shake (loc 20 cm, rot 0.5 deg, 8 Hz), pad rumble 0.4 |
| 5.2 | Drift | brake + steer -> drift row of 3.8; drift > 1.2 s then release -> mini boost | mini boost dv 600 cm/s, 0.6 s FOV +5 |
| 5.3 | Auto-level | bank*/pitch* -> 0 with no input; brake = hover hold | 3.4 |
| 5.4 | Lean | bank into turns, nose dip/flare | 3.4 |
| 5.5 | Spool-up | 3.2; Niagara/fan visuals read the filtered values so they visibly wind up | |
| 5.6 | Ground effect + floor | 4 down traces from the pods (`UWorld::LineTraceSingleByChannel`, `Engine/Classes/Engine/World.h:2161`), length 1500 cm; extra pod force `0.25 W * 0.35 * (1 - h/1500)^2` outside the loops (felt as cushion); floor in 3.3; dust ring Niagara at the hit | |
| 5.7 | Wind sway | `FMath::PerlinNoise1D` on 3 channels, scaled by `1 - clamp(v/3000)` | lateral 25 cm/s^2 (0.15 Hz), roll 0.03 rad/s^2 (0.12 Hz), pitch 0.015 rad/s^2 (0.21 Hz) |
| 5.8 | Strafe + side-hop | 3.8; double-tap Q/E -> `AddImpulse` sideways | hop dv 800 cm/s, cooldown 3 s |
| 5.9 | Cannon recoil | `AddImpulseAtLocation(-MuzzleDir * m * 80, MuzzleWorld)` (`PrimitiveComponent.h:1725`) per cannon on the server | dv 0.8 m/s per cannon -> roll kick ~0.11 rad/s for a cannon 6 m above COM, ~2-3 deg rock; shake 0.25 s, FOV -3 deg punch |
| 5.10 | Collision bounce + impact damage | `SetNotifyRigidBodyCollision(true)` (`PrimitiveComponent.h:1949`), bind `OnComponentHit` (`:1457`, signature `:274`). `dv = |NormalImpulse| / m` (NormalImpulse = accumulated impulse along the contact normal, `PhysScene_Chaos.cpp:1068-1070`). If dv > 400 cm/s and 0.4 s since last: damage GE (project's IncomingDamage meta attribute, `Source/Aura/Public/AbilitySystem/MyAttributeSet.h:200`) = 6 HP per m/s above 4 m/s; extra bounce `AddImpulse(n * m * min(0.3*dv, 600))` with n chosen so `n.v_before < 0` [normal sign unverified]; restitution 0.35 (3.10); shake scale `clamp(dv/1500, 0.2, 1)` | |
| 5.11 | Death fall/tumble | server, on Health <= 0: controllers off; one random pod cuts at once, others decay tau 0.8 s, fans coast 1 s; `AddAngularImpulseInRadians` (`PrimitiveComponent.h:1702`) / `AddImpulseAtLocation` at a random pod for dv ~3 m/s and w ~(0.25, 0.15, 0.3) rad/s; AngularDamping 0.12, max ang vel 180; multicast bIsDead (Control Rig physics, Niagara sputter, smoke trail); first hit with dv > 6 m/s or `FellOutOfWorld` (`Actor.h:3575`, KillZ `WorldSettings.h:599`) -> explode, LifeSpan 6 s | |
| 5.12 | Steam horn | cosmetic only, multicast unreliable | |

## 6. Network model (listen server, pilot may be a client)

### 6.1 What 5.8 offers (verified)
* `EPhysicsReplicationMode { Default, PredictiveInterpolation, Resimulation (WIP), None }`
  (`Engine/Classes/Engine/EngineTypes.h:3614-3634`). Engine comments: PredictiveInterpolation is "not forward predicted
  which makes this not viable for ROLE_AutonomousProxy if input latency is of concern", "Enable Project Settings > Physics
  Prediction for best result"; Resimulation is "Work In Progress", for physics pawns, needs Physics Prediction.
* Per actor: `SetPhysicsReplicationMode` / `GetPhysicsReplicationMode` (`Engine/Classes/GameFramework/Actor.h:924,928`,
  impl `Engine/Private/ActorReplication.cpp:1181-1198`, clears the current target).
* `UPrimitiveComponent::bReplicatePhysicsToAutonomousProxy` (`PrimitiveComponent.h:678`, default true
  `PrimitiveComponent.cpp:417`): "true for server-authoritative simulations, false for client authoritative".
  Checked at `Engine/Private/PhysicsEngine/PhysicsReplication.cpp:347,511`.
* Flow: server `GatherCurrentMovement` fills `ReplicatedMovement` from the body (`ActorReplication.cpp:426-470`;
  non-Default modes read a PT replication cache). Client `OnRep_ReplicatedMovement` -> `PostNetReceivePhysicState` ->
  `SetRigidBodyReplicatedTarget` (`ActorReplication.cpp:182-249, 304-314`, `PrimitiveComponent.h:2980`).
* Default mode = legacy `ApplyRigidBodyState` path (`PhysicsReplication.cpp:343` only non-Default modes take the
  PhysicsObject flow): target extrapolated by `ping * PingExtrapolation`, velocity correction
  `LinVel + LinDiff * LinearVelocityCoefficient * dt`, hard snap if error > `MaxLinearHardSnapDistance` or accumulated
  error > `ErrorAccumulationSeconds` (`PhysicsReplication.cpp:663-700, 776-850`). Project defaults
  (`FRigidBodyErrorCorrection`, `EngineTypes.h:2020-2032`): PingExtrapolation 0.1, PingLimit 100, MaxLinearHardSnapDistance
  400 cm, LinearVelocityCoefficient 100, AngularVelocityCoefficient 10, AngleLerp 0.4, ErrorAccumulationSeconds 0.5.
  Project-wide in `UPhysicsSettings::PhysicErrorCorrection` (`PhysicsSettings.h:271`); per actor via
  `UNetworkPhysicsSettingsComponent` (`Engine/Public/Physics/NetworkPhysicsSettingsComponent.h:791`) with a
  `UNetworkPhysicsSettingsDataAsset` (`:738`, `SettingsDataAsset` `:831`), field
  `FNetworkPhysicsSettingsDefaultReplication::MaxLinearHardSnapDistance` (`:141`), read at `PhysicsReplication.cpp:505,683-688`.
* PredictiveInterpolation runs in `FPhysicsReplicationAsync` (a sim callback, always created:
  `PhysicsReplication.cpp:314-325`, `:2281`), times targets in **server physics frames** (`UpdateAsyncTarget`
  `:1430-1530`); with sync physics the frame length differs per machine, so timing is approximate [quality unverified].
  Tuning cvars `np2.PredictiveInterpolation.*` (`:174-303`, e.g. VelocityBased default 1, InterpolationTimeMultiplier 1.1,
  ErrorAccumulationSeconds 3).
* Physics Prediction: `UPhysicsSettings::PhysicsPrediction.bEnablePhysicsPrediction` "needs Physics -> Framerate ->
  Tick Physics Async enabled" (`PhysicsSettings.h:205-210`).
* `UNetworkPhysicsComponent` (`Engine/Public/Physics/NetworkPhysicsComponent.h:2290`) with input/state history
  (`FNetworkPhysicsData` `:1893`, `CreateDataHistory` `:2704,2714`) is the input side of Resimulation.
* Mover / ChaosMover: `Engine/Plugins/Experimental/Mover`, `.../ChaosMover`, both `IsExperimentalVersion: true`;
  ChaosMover warns unless `bTickPhysicsAsync` and `bEnablePhysicsPrediction` are on
  (`Engine/Plugins/Experimental/ChaosMover/Source/ChaosMover/Private/Backends/ChaosMoverSubsystem.cpp:72-89`); character oriented.
* `FRepMovement` defaults: Location/Velocity `RoundWholeNumber`, Rotation **`ByteComponents`** = 1.4 deg steps
  (`Engine/Private/Engine/ReplicatedState.cpp:34-36`); at 26 m from the centre that is 0.6 m. `ShortComponents` exists
  (`Engine/Classes/Engine/ReplicatedState.h:23-29`).
* APawn defaults: replicates, `NetPriority 3`, `NetUpdateFrequency 100`, replicates movement (`Pawn.cpp:85-89`); a remote
  PlayerController makes it `AutonomousProxy` (`Pawn.cpp:690-696`). Actor default `NetCullDistanceSquared = 225e6`
  (150 m, `Engine/Private/Actor.cpp:312`) is too small for a 52 m ship.

### 6.2 Options

| Option | Pilot (client) feel | Work | Risk |
|---|---|---|---|
| **A. Server-auth physics + input RPC + engine replication (Default mode)** | input -> hull motion ~ RTT + half send interval; cosmetics instant | small: 1 RPC + 1 replicated struct | low, all gameplay (damage, death, hits) native on server |
| A'. same with PredictiveInterpolation | same latency, smoother velocity-based correction | 1 line | timing tuned for fixed-step physics |
| B. Client-auth state push | zero latency for the pilot | ~150 lines: state RPC, server correction, authority hand-back on death | host sees corrections; server-side contacts become approximate |
| C. Resimulation + UNetworkPhysicsComponent | predicted, rollback | large | WIP, needs project-wide async physics + prediction |
| D. Mover / ChaosMover | predicted | large | experimental, character focused, needs async + prediction |

Latency for option A (estimate): host pilot 0 ms. Client pilot: input reaches the server after RTT/2, the state returns
after RTT/2 + up to one send interval, Default mode extrapolates 10 % of ping: about RTT + 10-20 ms at 60 Hz.
RTT 50/100/150 ms -> ~65/115/165 ms. Against a 0.3 s throttle spool and 1 s to reach full yaw rate the extra delay adds
~20-50 % to response time, and fans, wheel, thruster VFX, sound, camera and FOV react at once from local input.
Cheating is irrelevant, so B stays the fallback if playtests over the internet feel sluggish.

### 6.3 Recommended setup (option A)
Constructor / BeginPlay:
* `bReplicates = true`, `SetReplicatingMovement(true)` (APawn already), `SetNetUpdateFrequency(60)`,
  `SetMinNetUpdateFrequency(30)` (`Actor.h:4624,4636`), `bAlwaysRelevant = true` (`Actor.h:333`) or
  `SetNetCullDistanceSquared(FMath::Square(1e6))` (`Actor.h:4648`).
* `GetReplicatedMovement_Mutable().RotationQuantizationLevel = ERotatorQuantization::ShortComponents` (`Actor.h:4615`),
  location `RoundWholeNumber` is fine (1 cm).
* `SetPhysicsReplicationMode(EPhysicsReplicationMode::Default)`; console var `Aura.Airship.RepMode` (0 Default,
  1 PredictiveInterpolation) for A/B.
* Root `bReplicatePhysicsToAutonomousProxy = true` (default).
* `UNetworkPhysicsSettingsComponent` + data asset: `MaxLinearHardSnapDistance` 1200 cm (a 4 m snap on a 52 m ship at
  90 m/s is a visible jump; larger errors are corrected softly) [value to tune in PIE with `Net PktLag=100`].
* Non-authority copies while alive: `SetEnableGravity(false)` on the root (`PrimitiveComponent.h:2801`) so the client
  body coasts like the hovering server body between updates instead of sagging [design choice, verify]. Re-enable on death.
* Forces: only `if (HasAuthority())`. Clients never add flight forces (they would fight the corrections).

Input path:
```cpp
USTRUCT() struct FAirshipPilotInput {       // 8 bytes
  UPROPERTY() int8 Throttle=0, Steer=0, Lift=0, Strafe=0;  // -127..127
  UPROPERTY() int8 AimYaw=0, AimPitch=0;                   // cannon aim, relative to ship, deg/1.5
  UPROPERTY() uint8 Buttons=0;                              // bit0 Boost, bit1 Brake, bit2 Aim, bit3 Horn
  UPROPERTY() uint8 Seq=0;
};
UFUNCTION(Server, Unreliable) void ServerSetPilotInput(FAirshipPilotInput In);   // every tick while non-zero, on change, 10 Hz heartbeat
UPROPERTY(Replicated) FAirshipPilotInput RepInput;   // DOREPLIFETIME_CONDITION(..., COND_SkipOwner) (CoreUObject/Public/UObject/CoreNetTypes.h:21)
UPROPERTY(ReplicatedUsing=OnRep_Dead) bool bDead;
```
* Server drops packets with an older `Seq` (wrap-aware), clamps values, gates Boost by BoostFuel, copies into
  `RepInput`. No packet for 0.5 s -> neutral input (hover hold).
* Locally controlled host: write the input directly, no RPC.
* Cannon fire / boost cost / damage: GAS abilities and effects on the ship's ASC (server), as in the project.
* Each machine derives cosmetics from input: pilot from its own raw input, others from `RepInput`, through the same 3.2
  filters, plus replicated velocity for spin rates. Fans/wheel/rudder angles are therefore never sent.
* Death: server sets `bDead` and multicasts like the Burrower (`MulticastHandleDeath`); the tumble is real physics on the
  server and arrives through `ReplicatedMovement`.
* Debug: `Net.RepMovement.DrawDebug 1` (`ActorReplication.cpp:180`), `p.Net.DebugDraw.ShowRepMode`,
  `p.LogPhysicsReplicationHardSnaps 1` (`PhysicsReplication.cpp:106,113`), `Net PktLag=100`.

### 6.4 Why not the others now
* Resimulation needs `bTickPhysicsAsync` + `bEnablePhysicsPrediction` project-wide, a resim-safe force model on the
  physics thread and input history via `UNetworkPhysicsComponent`; the enum still says WIP.
* ChaosMover/Mover: experimental, needs the same project settings, built around characters.

### 6.5 Fallback B: client-authoritative state push (if A feels sluggish)
* Owner: `bReplicatePhysicsToAutonomousProxy = false` on the root (owner ignores server targets), runs the force model
  locally (`IsLocallyControlled()`), sends `ServerShipState(FVector_NetQuantize10 Pos, FRotator Rot (short),
  FVector_NetQuantize10 Vel, FVector_NetQuantize10 AngVelDeg, float ClientTime, FAirshipPilotInput In)` at 30 Hz
  unreliable (`Engine/Classes/Engine/NetSerialization.h:454`).
* Server keeps simulating with the same input (extrapolates between packets) and corrects: error > 300 cm ->
  `SetWorldLocationAndRotation(..., ETeleportType::TeleportPhysics)` + `SetPhysicsLinearVelocity` +
  `SetPhysicsAngularVelocityInDegrees` (`PrimitiveComponent.h:1825,1871`); smaller -> blend velocity
  `v_srv = v_cli + (p_cli_extrap - p_srv) * 4/s`. Other clients still get `ReplicatedMovement` from the server.
* Impact damage from the owner's hit events (reported), death decided on the server; at death the server hands
  authority back (owner sets `bReplicatePhysicsToAutonomousProxy = true`, stops forces).

## 7. Camera

| Setting | Value | API |
|---|---|---|
| Spring arm on root | `TargetArmLength` 6500 cm, zoom 4000-12000 (wheel steps 800, interp 6/s), boost +1000 | `Engine/Classes/GameFramework/SpringArmComponent.h:25` |
| Look-at height | `TargetOffset` (0, 0, 900), `SocketOffset` 0 | `:29,33` |
| Free look | `bUsePawnControlRotation` true; mouse/RS -> `AddControllerYawInput/PitchInput` (`Pawn.h:539,548`); pitch limits -60..+25 via `APlayerCameraManager::ViewPitchMin/Max` (`Engine/Classes/Camera/PlayerCameraManager.h:473,477`) | `:57` |
| Horizon | `bInheritRoll` false (ship banks, horizon stays level); applies with control rotation too (`Engine/Private/GameFramework/SpringArmComponent.cpp:70-88`) | `:69` |
| Auto-recenter | locally controlled only: after 1.5 s without look input and vf > 800 cm/s, ease control yaw to ship yaw at 2/s (exp) and pitch to -12 deg; off while aiming | `AController::SetControlRotation` (`Engine/Classes/GameFramework/Controller.h:163`) |
| Lag | `bEnableCameraLag` true, `CameraLagSpeed` 5, `CameraLagMaxDistance` 2500 (falls back 15-25 m on boost = speed feel, also hides replication corrections); `bEnableCameraRotationLag` true, `CameraRotationLagSpeed` 7; `bUseCameraLagSubstepping` true (default, `CameraLagMaxTimeStep` 1/60) | `:76,83,90,101,105,109,113`; defaults `SpringArmComponent.cpp:18-44` |
| Collision | `bDoCollisionTest` true, `ProbeSize` 50, `ProbeChannel` ECC_Camera; the trace ignores the owner (`SpringArmComponent.cpp:194`) | `:37,41,45` |
| FOV | base 85, + 10 * clamp((vf - 2000)/2800, 0, 1), + 12 boost, -3 cannon punch (0.15 s): ~107 max; set every frame on the local camera | `UCameraComponent::SetFieldOfView` (`Engine/Classes/Camera/CameraComponent.h:46`) |
| Shakes | `UDefaultCameraShakeBase` + `UPerlinNoiseCameraShakePattern` / `UWaveOscillatorCameraShakePattern` (EngineCameras plugin, enabled by default: `Engine/Plugins/Cameras/EngineCameras/Source/EngineCameras/Public/Shakes/`); start on the pilot's camera manager (`StartCameraShake` `PlayerCameraManager.h:811`; from server `APlayerController::ClientStartCameraShake` `Engine/Classes/GameFramework/PlayerController.h:1087`); speed rumble = one looping shake with `ShakeScale` updated (`Engine/Classes/Camera/CameraShakeBase.h:536`) | |
| Rumble | `PlayDynamicForceFeedback` (`PlayerController.h:1315`) on boost/impact/cannon | |
| Tick order | spring arm ticks `TG_PostPhysics` (`SpringArmComponent.cpp:22`), after the body moved | |

Framing check: at 65 m and FOV 85 the view is ~120 m wide, the 52 m ship fills ~45 %; camera sits ~22 m above the root
looking down 12 deg, so the balloon does not block the horizon.

## 8. Outputs for Control Rig / Niagara (every machine, cosmetic)
Computed in the pawn from the 3.2 filters, read by the anim instance (Burrower pattern: thread-safe properties ->
Control Rig variables):

| Output | Formula |
|---|---|
| FanYawDeg[L,R] | `-FanYawMaxDeg * str` |
| FanSpinAngleDeg[L,R] (accumulated) | rate = sign(Fx_i) * (300 + 1500*|Fx_i|/FanMax) deg/s, x2 on boost; pivot turn spins them opposite |
| PodGimbalPitchDeg[4], PodGimbalRollDeg[4] | 3.5 commands (rest 8 deg tilt added by the rig) |
| PodPower01[4] | f_i / (0.25 W) on the server; elsewhere approximate: 1 + 0.6*lift + 0.3*bst (+ ground effect) |
| WheelAngleDeg | `str * 270` with spring-back overshoot (second-order, w_n 6, zeta 0.4) |
| RudderDeg | `str * 25` (or up to the 54 deg hinge limit) |
| Speed, BoostAlpha, GroundDist01[4], bIsDead, DeathTime | for VFX / CR physics switch |
Niagara: `UNiagaraComponent::SetVariableFloat(FName("User.Power"), x)` (`Engine/Plugins/FX/Niagara/Source/Niagara/Public/NiagaraComponent.h:533`).

## 9. Verified API list (5.8)

| API | Where |
|---|---|
| `AddForce(Force, Bone, bAccelChange)` | `Engine/Classes/Components/PrimitiveComponent.h:1759` |
| `AddForceAtLocation(Force, WorldLocation, Bone)` | `PrimitiveComponent.h:1770`; impl `Engine/Private/PrimitiveComponentPhysics.cpp:327-334` |
| `AddForceAtLocationLocal` | `PrimitiveComponent.h:1781` |
| `AddTorqueInRadians(Torque, Bone, bAccelChange)` | `PrimitiveComponent.h:1802`; accel change = world inertia * alpha (`ChaosEngineInterface.cpp:1024-1038`) |
| `AddImpulse` / `AddImpulseAtLocation` | `PrimitiveComponent.h:1692` / `:1725` |
| `Set/GetPhysicsLinearVelocity` | `PrimitiveComponent.h:1825` / `:1832` |
| `SetPhysicsAngularVelocityInDegrees`, `GetPhysicsAngularVelocityInRadians` | `:1871`, `:1914` |
| `SetPhysicsMaxAngularVelocityInDegrees` | `:1884` |
| `GetCenterOfMass`, `SetCenterOfMass` (COMNudge) | `:1922`, `:1931`; `BodyInstance.h:641` |
| `SetNotifyRigidBodyCollision`, `OnComponentHit`, `FComponentHitSignature` | `:1949`, `:1457`, `:274` |
| `SetEnableGravity`, `SetLinearDamping`, `SetAngularDamping` | `:2801`, `:2825`, `:2833` |
| `SetMassOverrideInKg`, `GetMass`, `GetInertiaTensor`, `ScaleByMomentOfInertia` | `:2857`, `:2861`, `:2865`, `:2869` |
| `SetUseCCD`, `SetPhysMaterialOverride` | `:2894`, `:3008` |
| `SetRigidBodyReplicatedTarget`, `GetRigidBodyState` | `:2980`, `:3000` |
| `bReplicatePhysicsToAutonomousProxy` | `:678` |
| `GetBodyInstanceAsyncPhysicsTickHandle`, `FBodyInstanceAsyncPhysicsTickHandle` | `:2349`; `Engine/Classes/PhysicsEngine/BodyInstance.h:336` |
| `UPhysicsThreadLibrary::AddForce` (only function there) | `Engine/Public/Physics/Experimental/PhysicsThreadLibrary.h:32` |
| `FBodyInstance::AddCustomPhysics` (Chaos: immediate, once) | `Engine/Private/PhysicsEngine/BodyInstance.cpp:3726`; `PhysScene_Chaos.cpp:1665-1668` |
| `FBodyInstance` LinearDamping / AngularDamping / InertiaTensorScale / bUseCCD / MaxAngularVelocity | `BodyInstance.h:629, 633, 653, 418, 691` |
| `AActor::bAsyncPhysicsTickEnabled`, `AsyncPhysicsTickActor` | `Engine/Classes/GameFramework/Actor.h:699`, `:2930` |
| `UActorComponent::bAsyncPhysicsTickEnabled`, `AsyncPhysicsTickComponent` | `Engine/Classes/Components/ActorComponent.h:407`, `:985` |
| `UPhysicsSettings` bSubstepping / bTickPhysicsAsync / AsyncFixedTimeStepSize / MaxSubstepDeltaTime / MaxSubsteps / MaxPhysicsDeltaTime / PhysicsPrediction / PhysicErrorCorrection | `PhysicsSettings.h:325, 333, 337, 341, 345, 321, 267, 271` |
| `EPhysicsReplicationMode` | `EngineTypes.h:3614` |
| `AActor::SetPhysicsReplicationMode`, `ReplicatedMovement`, `OnRep_ReplicatedMovement`, `PostNetReceivePhysicState`, `GatherCurrentMovement` | `Actor.h:924, 831, 2962, 2971, 2467` |
| `AActor::SetNetUpdateFrequency`, `SetMinNetUpdateFrequency`, `GetReplicatedMovement_Mutable`, `SetNetCullDistanceSquared`, `bAlwaysRelevant` | `Actor.h:4624, 4636, 4615, 4648, 333` |
| `FRepMovement`, `ERotatorQuantization` | `Engine/Classes/Engine/ReplicatedState.h:118`, `:23` |
| `UNetworkPhysicsSettingsComponent`, `UNetworkPhysicsSettingsDataAsset` | `NetworkPhysicsSettingsComponent.h:791`, `:738` |
| `UNetworkPhysicsComponent` | `NetworkPhysicsComponent.h:2290` |
| `APawn::NotifyControllerChanged / PawnClientRestart / IsLocallyControlled / SetupPlayerInputComponent / PossessedBy` | `Pawn.h:397, 418, 426, 486, 374` |
| `APlayerController::ClientStartCameraShake`, `PlayDynamicForceFeedback`, `GetPhysicsTimestamp` | `PlayerController.h:1087, 1315, 2350` |
| `USpringArmComponent` fields | `SpringArmComponent.h:25-117` |
| `UPhysicalMaterial` Friction / Restitution / RestitutionCombineMode | `PhysicalMaterial.h:115, 131, 135` |
| `UNiagaraComponent::SetVariableFloat` | `NiagaraComponent.h:533` |

## 10. Not verified / test in PIE
* Real COM, inertia and hull mass distribution of the 8 hulls (log `GetCenterOfMass`, `GetInertiaTensor` once).
* Sign checks with debug arrows: yaw right = +w.Z, fan housing sign, rudder sign, impact normal sign (5.10).
* Rig limits for pod gimbal (0-9 deg per rig data) and fan yaw (0 deg at rest per rig data): the model works with 0,
  but the visuals the brief asked for (+-15 / +-25 deg) need the rig agent to free the geometry.
* Default-mode correction quality for the owning client at 100-150 ms (`Net PktLag`), hard-snap distance, and whether
  turning gravity off on clients helps; A/B with PredictiveInterpolation under sync physics.
* CCD cost on the root; `AsyncPhysicsTickActor` path is only needed if low-fps feel is bad.
* Control Rig physics on a body that receives replication corrections may twitch (rig agent).
* Feel numbers come from a point-mass sim (`_AirshipWork_logs/scratch/flight/sim_final.py`), not from the engine.
