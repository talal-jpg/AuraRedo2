"""Offline test bench for the airship control schemes (Docs/Airship/controls/).

A Python 6-DOF port of the CURRENT flight model (Source/Aura/Private/Airship/AirshipFlightComponent.cpp at 8f01bca:
UpdateFlight -> UpdateBoostServer -> ShapeControls -> TraceGround -> ApplyForces -> UpdateCosmetic), the Chaos rigid
body step it runs on (PBDRigidsEvolutionGBF::Integrate), the pawn's input path (GatherLocalInput, the input RPC,
camera recentering, cannon arcs, recoil kick) and the anim instance's wheel / turbine cosmetics, with plug-in control
schemes. Standard library only. UE axes and units inside (cm, kg, s; X forward, Y right, Z up; yaw + = right turn).

Calibrated against the PIE runs in Docs/Airship/reports (see calibrate.py and BASELINE_METRICS.md).

Main facts the port depends on (all read in the engine / project source, see README.md):
  * Hull mass properties from the 8 UCX convexes the way Chaos computes them (mass_props.py -> hull_mass.json).
  * GetInertiaTensor() returns the principal inertia in Chaos order (largest, smallest, middle) = about
    (yaw, roll, pitch), and ApplyForces uses it as (roll, pitch, yaw): its roll loop is ~5.7x stiffer and its pitch
    loop ~6x softer than designed. This is what makes the nose dip -16.5 deg in PIE. Sim option
    Sim(..., ctrl_inertia='hull') shows the fixed behaviour; the default 'chaos' is the v1 C++.
  * Accel-change forces / torques (AddForce / AddTorqueInRadians with bAccelChange) are exact accelerations; forces at
    locations (pods, fans) act through the true inertia tensor.

Usage (see README.md):
    from airship_sim import Sim, Classic, RawInput
    sim = Sim(Classic(), latency_ms=0)
    for k in range(300):
        sim.step(RawInput(throttle=1.0))
    print(sim.tele()['ForwardSpeedMS'])
"""
import json
import math
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))

DT = 1.0 / 30.0          # fixed 30 fps (the PIE harnesses' fixed frame rate; MaxPhysicsDeltaTime 1/30, no substeps)
G = 980.0                # -World->GetGravityZ() (cm/s^2)
D2R = math.pi / 180.0
R2D = 180.0 / math.pi


# =====================================================================================================================
# UE math (FQuat / FRotator conventions)
# =====================================================================================================================
def add(a, b): return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
def sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def mul(a, s): return (a[0] * s, a[1] * s, a[2] * s)
def dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
def size(a): return math.sqrt(dot(a, a))
def size2d(a): return math.hypot(a[0], a[1])
def clamp(x, lo, hi): return lo if x < lo else (hi if x > hi else x)
def lerp(a, b, t): return a + (b - a) * t


def norm(a):
    s = size(a)
    return mul(a, 1.0 / s) if s > 1e-12 else (0.0, 0.0, 0.0)


def clampsize(a, m):
    s = size(a)
    return mul(a, m / s) if s > m and s > 1e-12 else a


def wrap180(a):
    a = math.fmod(a + 180.0, 360.0)
    if a < 0:
        a += 360.0
    return a - 180.0


def qmul(a, b):  # (x, y, z, w); a * b = apply b then a
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz)


def qinv(q): return (-q[0], -q[1], -q[2], q[3])


def qrot(q, v):
    # FQuat::RotateVector
    x, y, z, w = q
    tx, ty, tz = 2 * (y * v[2] - z * v[1]), 2 * (z * v[0] - x * v[2]), 2 * (x * v[1] - y * v[0])
    return (v[0] + w * tx + (y * tz - z * ty), v[1] + w * ty + (z * tx - x * tz), v[2] + w * tz + (x * ty - y * tx))


def qunrot(q, v): return qrot(qinv(q), v)


def qnorm(q):
    n = math.sqrt(q[0] * q[0] + q[1] * q[1] + q[2] * q[2] + q[3] * q[3])
    return (q[0] / n, q[1] / n, q[2] / n, q[3] / n)


def rot2quat(p, y, r):
    """FRotator(Pitch, Yaw, Roll).Quaternion() (deg)."""
    sp, cp = math.sin(p * D2R / 2), math.cos(p * D2R / 2)
    sy, cy = math.sin(y * D2R / 2), math.cos(y * D2R / 2)
    sr, cr = math.sin(r * D2R / 2), math.cos(r * D2R / 2)
    return (cr * sp * sy - sr * cp * cy, -cr * sp * cy - sr * cp * sy, cr * cp * sy - sr * sp * cy, cr * cp * cy + sr * sp * sy)


def quat2rot(q):
    """FQuat::Rotator() -> (pitch, yaw, roll) deg."""
    X, Y, Z, W = q
    st = Z * X - W * Y
    pitch = math.asin(clamp(2 * st, -1.0, 1.0)) * R2D
    yaw = math.atan2(2 * (W * Z + X * Y), 1 - 2 * (Y * Y + Z * Z)) * R2D
    roll = math.atan2(-2 * (W * X + Y * Z), 1 - 2 * (X * X + Y * Y)) * R2D
    return pitch, yaw, roll


def to_axis_angle(q):
    X, Y, Z, W = q
    ang = 2 * math.acos(clamp(W, -1.0, 1.0))
    s = math.sqrt(max(0.0, 1 - W * W))
    if s < 1e-8:
        return (1.0, 0.0, 0.0), 0.0
    return (X / s, Y / s, Z / s), ang


def approach(cur, tgt, dt, tau):
    """AirshipFlightPrivate::Approach (first-order filter)."""
    if tau <= 1e-4:
        return tgt
    return cur + (tgt - cur) * (1 - math.exp(-dt / tau))


def approach_ud(cur, tgt, dt, tau_up, tau_down):
    return approach(cur, tgt, dt, tau_up if abs(tgt) > abs(cur) else tau_down)


def solve3(M, B):
    """AirshipFlightPrivate::Solve3x3 (None when singular)."""
    C00 = M[1][1] * M[2][2] - M[1][2] * M[2][1]
    C01 = M[1][2] * M[2][0] - M[1][0] * M[2][2]
    C02 = M[1][0] * M[2][1] - M[1][1] * M[2][0]
    det = M[0][0] * C00 + M[0][1] * C01 + M[0][2] * C02
    if abs(det) < 1e-12:
        return None
    inv = [[C00, M[0][2] * M[2][1] - M[0][1] * M[2][2], M[0][1] * M[1][2] - M[0][2] * M[1][1]],
           [C01, M[0][0] * M[2][2] - M[0][2] * M[2][0], M[0][2] * M[1][0] - M[0][0] * M[1][2]],
           [C02, M[0][1] * M[2][0] - M[0][0] * M[2][1], M[0][0] * M[1][1] - M[0][1] * M[1][0]]]
    return [sum(inv[r][c] * B[c] for c in range(3)) / det for r in range(3)]


def mat3_inv(m):
    a, b, c = m[0]
    d, e, f = m[1]
    g, h, i = m[2]
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    return [[(e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det],
            [(f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det],
            [(d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det]]


def mat3_vec(m, v):
    return (m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2],
            m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2],
            m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2])


# FMath::PerlinNoise1D (Core/Private/Math/UnrealMath.cpp)
_PERM = [63, 9, 212, 205, 31, 128, 72, 59, 137, 203, 195, 170, 181, 115, 165, 40, 116, 139, 175, 225, 132, 99, 222, 2, 41,
         15, 197, 93, 169, 90, 228, 43, 221, 38, 206, 204, 73, 17, 97, 10, 96, 47, 32, 138, 136, 30, 219, 78, 224, 13,
         193, 88, 134, 211, 7, 112, 176, 19, 106, 83, 75, 217, 85, 0, 98, 140, 229, 80, 118, 151, 117, 251, 103, 242, 81,
         238, 172, 82, 110, 4, 227, 77, 243, 46, 12, 189, 34, 188, 200, 161, 68, 76, 171, 194, 57, 48, 247, 233, 51, 105,
         5, 23, 42, 50, 216, 45, 239, 148, 249, 84, 70, 125, 108, 241, 62, 66, 64, 240, 173, 185, 250, 49, 6, 37, 26, 21,
         244, 60, 223, 255, 16, 145, 27, 109, 58, 102, 142, 253, 120, 149, 160, 124, 156, 79, 186, 135, 127, 14, 121, 22,
         65, 54, 153, 91, 213, 174, 24, 252, 131, 192, 190, 202, 208, 35, 94, 231, 56, 95, 183, 163, 111, 147, 25, 67, 36,
         92, 236, 71, 166, 1, 187, 100, 130, 143, 237, 178, 158, 104, 184, 159, 177, 52, 214, 230, 119, 87, 114, 201, 179,
         198, 3, 248, 182, 39, 11, 152, 196, 113, 20, 232, 69, 141, 207, 234, 53, 86, 180, 226, 74, 150, 218, 29, 133, 8,
         44, 123, 28, 146, 89, 101, 154, 220, 126, 155, 122, 210, 168, 254, 162, 129, 33, 18, 209, 61, 191, 199, 157, 245,
         55, 164, 167, 215, 246, 144, 107, 235]
_PERM = _PERM + _PERM
_GRAD1 = [-1.0, -7 / 8., -6 / 8., -5 / 8., -4 / 8., -3 / 8., -2 / 8., -1 / 8., 1 / 8., 2 / 8., 3 / 8., 4 / 8., 5 / 8., 6 / 8.,
          7 / 8., 1.0]


def perlin1d(x):
    xfl = math.floor(x)
    xi = int(xfl) & 255
    x -= xfl
    a, b = _PERM[xi], _PERM[xi + 1]
    u = x * x * x * (x * (x * 6.0 - 15.0) + 10.0)
    return 2.0 * lerp(_GRAD1[a & 15] * x, _GRAD1[b & 15] * (x - 1.0), u)


# =====================================================================================================================
# Hull data (SK_Airship rest pose bones, Saved/Airship/as_10_import.json; mass properties from mass_props.py)
# =====================================================================================================================
POD_LOCAL = [(383.303, -465.572, -93.381), (383.303, 491.791, -112.989), (-716.697, -513.032, -120.362),
             (-716.697, 576.756, -123.902)]                     # Thruster_FL, FR, RL, RR
NOZZLE_EXIT = [(322.762, -465.572, -564.147), (322.762, 491.791, -583.756), (-777.238, -513.032, -591.129),
               (-777.238, 576.756, -594.669)]                   # Thruster_*_Flame
NOZZLE_DEPTH = [POD_LOCAL[i][2] - NOZZLE_EXIT[i][2] for i in range(4)]
FAN_LOCAL = [(-1720.0, -760.0, 140.0), (-1720.0, 760.0, 140.0)]  # Turbine_L_Rotor, Turbine_R_Rotor
FRONT_POD = [True, True, False, False]
LEFT_POD = [True, False, True, False]
CANNON_MUZZLE = [(-44.845, -784.47, 323.717), (-1143.66, -578.74, 363.523), (-44.845, 784.47, 323.717),
                 (-1143.66, 578.74, 363.523)]                   # Cannon_L1, L2, R1, R2 _Muzzle
CANNON_REST_DIR = [(0.0, -1.0, 0.0), (0.0, -1.0, 0.0), (0.0, 1.0, 0.0), (0.0, 1.0, 0.0)]  # barrel -> muzzle
PORT_CANNONS = (0, 1)
STBD_CANNONS = (2, 3)
HULL_LENGTH_M = 51.9                                             # SK_Airship bounds x -20.4 .. +31.5 m


def _load_hull():
    path = os.path.join(HERE, 'hull_mass.json')
    if not os.path.exists(path):
        import mass_props  # noqa: E402  (writes hull_mass.json)
        mass_props.main()
    d = json.load(open(path))
    return d


HULL = _load_hull()
TENSOR_ACTOR = HULL['tensor_actor_kgcm2']        # the true inertia (hull axes, about the COM), kg cm^2
TENSOR_ACTOR_INV = mat3_inv(TENSOR_ACTOR)
CHAOS_I = tuple(HULL['chaos_I_kgcm2'])           # GetInertiaTensor(): (largest, smallest, middle)
HULL_AXIS_I = tuple(HULL['hull_axis_I_kgcm2'])   # diagonal of the true tensor (what the code assumes it gets)


def _keel_points():
    """Hull points used for ground contact: the lowest UCX vertices plus the 4 nozzle exits (hull space cm)."""
    pts = list(NOZZLE_EXIT)
    try:
        ucx = json.load(open(os.path.join(HERE, '..', '..', 'sims', 'fix2', 'ucx.json')))
        for k, h in ucx.items():
            if k.startswith('UCX'):
                for v in h['verts']:
                    if v[2] < -3.0:
                        pts.append((100.0 * v[0], -100.0 * v[1], 100.0 * v[2]))
    except (OSError, ValueError):
        pass
    return pts


KEEL_POINTS = _keel_points()


# =====================================================================================================================
# Parameters: every UAirshipFlightComponent UPROPERTY default (AirshipFlightComponent.h), the pawn's camera / cannon
# tunables (AirshipPawn.h + constructor) and the anim instance's cosmetic dynamics (AirshipAnimInstance.h)
# =====================================================================================================================
FLIGHT_DEFAULTS = dict(
    MassKg=40000.0, AngularDamping=0.5, LinearDamping=0.0, MaxAngularVelocityDeg=120.0,
    ThrottleTauUp=0.30, ThrottleTauDown=0.45, BoostTauUp=0.15, BoostTauDown=0.60, LiftTau=0.25, SteerTau=0.15,
    StrafeTau=0.20, PodForceTauUp=0.10, PodForceTauDown=0.15,
    ClimbRate=1200.0, DescendRate=1500.0, Kvz=2.0, Kz=0.8, HoldMaxSpeed=800.0, HoldCaptureLead=0.5, LiftDeadZone=0.05,
    CollectiveMin=0.25, CollectiveMax=1.9, MinClearance=400.0, Kfloor=1.5, FloorBrakeAccel=588.0,
    bUseCeiling=False, CeilingZ=100000.0, Kceil=1.0,
    KpRoll=6.25, KdRoll=4.5, KpPitch=4.0, KdPitch=3.2, BankMaxDeg=18.0, BankMaxDriftDeg=22.0, BankMaxBoostDeg=12.0,
    StrafeBankDeg=6.0, BankFullSpeed=2000.0, BankMinFraction=0.25, PitchPerG=8.0, PitchMinDeg=-8.0, PitchMaxDeg=6.0,
    BoostPitchDeg=3.0, LiftPitchDeg=3.0, GyroTiltMax=0.8,
    PodForceMin=0.02, PodForceMax=0.55, ThrusterGimbalMaxDeg=5.0, GimbalPitchPerThrottle=10.0, GimbalPitchPerBoost=5.0,
    GimbalPitchPerBrake=6.0, GimbalRollPerStrafe=12.0, GimbalRollPerSteer=5.0, GroundEffectStrength=0.35,
    bGroundTraces=True, GroundTraceLength=1500.0,
    Kr=3.0, AlphaYawMax=1.0, YawRateAtRest=30.0, YawRateAtMid=45.0, YawRateMidSpeed=1500.0, YawRateAtTop=35.0,
    YawRateTopSpeed=4800.0, YawRateDrift=50.0, YawRateBoost=25.0, FanYawMaxDeg=12.0, RudderAuthority=0.6,
    RudderRefSpeed=4800.0, RudderMaxAlpha=1.2, GyroYawMax=0.5,
    AFan=1323.0, VTop=5000.0, AFanBoost=1960.0, VTopBoost=9600.0, AFanRev=490.0, VTopRev=1800.0, ThrustFadeExponent=6.0,
    DragC1=0.05, DragC2=3e-6, Kbrake=0.9, BrakeReverseThrottle=0.5, FanMax=0.68, FanMaxBoost=1.0,
    HardSpeedCap=11000.0, HardCapGain=3.0,
    StrafeSpeed=1200.0, GripKlat=4.0, GripALatMaxG=2.5, GripEta=0.35, DriftKlat=1.2, DriftALatMaxG=1.2, DriftEta=0.4,
    BoostKlat=3.0, BoostALatMaxG=2.0, BoostEta=0.3, RedirectMinSpeed=500.0, DriftSteerThreshold=0.3,
    DriftMinSpeed=800.0, DriftBrakeScale=0.0, DriftBoostMinTime=1.2, DriftBoostDV=600.0,
    BoostFuelMax=100.0, BoostDrainRate=25.0, BoostRegenRate=12.0, BoostRegenDelay=1.0, BoostMinFuelToStart=20.0,
    BoostStartFuelCost=10.0, BoostKickDV=400.0, BoostKickCooldown=1.5,
    WindLateralAccel=25.0, WindLateralFrequency=0.15, WindRollAccel=0.03, WindRollFrequency=0.12,
    WindPitchAccel=0.015, WindPitchFrequency=0.21, WindFadeSpeed=3000.0,
    PodAlphaPerLift=0.6, PodAlphaPerBoost=0.3, PodAlphaPerThrottle=0.15, PodAlphaPerSteer=0.15, FanSteerShare=0.6,
    InputSendRate=30.0, InputTimeout=0.5,
)

PAWN_DEFAULTS = dict(
    # camera (AAirshipPawn properties + CameraBoom set in the constructor)
    CameraArmLength=6500.0, CameraArmMin=4000.0, CameraArmMax=12000.0, CameraBoostArmExtra=1000.0,
    CameraTargetOffsetZ=900.0, CameraRotationLagSpeed=7.0, CameraLagSpeed=5.0,
    BaseFOV=85.0, SpeedFOVExtra=10.0, SpeedFOVStart=2000.0, SpeedFOVFull=4800.0, BoostFOVExtra=12.0, AimFOVOffset=-15.0,
    CameraPitchMin=-60.0, CameraPitchMax=25.0, CameraDefaultPitch=-12.0,
    RecenterDelay=1.5, RecenterMinSpeed=800.0, RecenterSpeed=2.0,
    # cannons
    CannonCooldown=1.5, CannonYawLimitDeg=20.0, CannonElevMinDeg=-10.0, CannonElevMaxDeg=8.5, CannonRecoilImpulseDV=80.0,
    CannonAimTraceDistance=60000.0, AimSideHysteresis=300.0, CannonballSpeed=12000.0,
    # anim instance cosmetics
    TurbineYawMaxDeg=12.0, TurbineYawSlewDegPerSec=40.0, WheelDegPerSteer=-270.0, WheelSpringOmega=6.0,
    WheelSpringDamping=0.4,
)

BUTTON_BOOST, BUTTON_BRAKE, BUTTON_AIM, BUTTON_HAS_AIM = 1, 2, 4, 8


# =====================================================================================================================
# Inputs
# =====================================================================================================================
class RawInput:
    """What the pawn reads on the pilot's machine in one frame: Enhanced Input action values (the PIE harness injects
    these with inject_input_for_action / inject_input_vector_for_action) and the PlayerController's control rotation
    (the harness sets it). cam_yaw / cam_pitch None = the harness leaves the control rotation alone; look = the
    IA_AirshipLook action fired this frame (resets the recenter timer)."""
    __slots__ = ('throttle', 'steer', 'lift', 'strafe', 'boost', 'brake', 'aim', 'fire', 'cam_yaw', 'cam_pitch', 'look',
                 'zoom', 'exit')

    def __init__(self, throttle=0.0, steer=0.0, lift=0.0, strafe=0.0, boost=False, brake=False, aim=False, fire=False,
                 cam_yaw=None, cam_pitch=None, look=False, zoom=0.0, exit=False):
        self.throttle, self.steer, self.lift, self.strafe = throttle, steer, lift, strafe
        self.boost, self.brake, self.aim, self.fire = boost, brake, aim, fire
        self.cam_yaw, self.cam_pitch, self.look, self.zoom, self.exit = cam_yaw, cam_pitch, look, zoom, exit

    def copy(self):
        r = RawInput()
        for k in self.__slots__:
            setattr(r, k, getattr(self, k))
        return r

    def as_dict(self):
        return {k: getattr(self, k) for k in self.__slots__}


def quantize_axis(v):
    """FAirshipPilotInput::QuantizeAxis: -1..1 -> int8."""
    return int(round_half_away(clamp(v, -1.0, 1.0) * 127.0))


def round_half_away(x):
    """FMath::RoundToInt (round half away from zero for these magnitudes)."""
    return int(math.floor(x + 0.5)) if x >= 0 else -int(math.floor(-x + 0.5))


def axis_to_float(i):
    return clamp(i / 127.0, -1.0, 1.0)


class PilotInput:
    """FAirshipPilotInput: the input RPC payload. Axes int8, Buttons uint8, Seq uint8, AimPoint (FVector_NetQuantize,
    cm). ext: extra small quantized fields a scheme adds (dict name -> int), declared in Scheme.ext_fields."""
    __slots__ = ('throttle', 'steer', 'lift', 'strafe', 'buttons', 'seq', 'aim', 'ext')

    def __init__(self):
        self.throttle = self.steer = self.lift = self.strafe = 0
        self.buttons = 0
        self.seq = 0
        self.aim = None
        self.ext = {}

    def copy(self):
        p = PilotInput()
        p.throttle, p.steer, p.lift, p.strafe = self.throttle, self.steer, self.lift, self.strafe
        p.buttons, p.seq, p.aim, p.ext = self.buttons, self.seq, self.aim, dict(self.ext)
        return p

    # FAirshipPilotInput accessors
    def get_throttle(self): return axis_to_float(self.throttle)
    def get_steer(self): return axis_to_float(self.steer)
    def get_lift(self): return axis_to_float(self.lift)
    def get_strafe(self): return axis_to_float(self.strafe)
    def has(self, b): return (self.buttons & b) != 0

    def set_button(self, b, on):
        self.buttons = (self.buttons | b) if on else (self.buttons & ~b)

    def same_controls(self, o):
        return (self.throttle == o.throttle and self.steer == o.steer and self.lift == o.lift and self.strafe == o.strafe
                and self.buttons == o.buttons and self.ext == o.ext)

    def set_axes(self, throttle=None, steer=None, lift=None, strafe=None):
        if throttle is not None:
            self.throttle = quantize_axis(throttle)
        if steer is not None:
            self.steer = quantize_axis(steer)
        if lift is not None:
            self.lift = quantize_axis(lift)
        if strafe is not None:
            self.strafe = quantize_axis(strafe)


def quantize_ext(value, spec):
    """spec = (bits, scale, signed): an integer field holding round(value / scale)."""
    bits, scale, signed = spec
    lo, hi = (-(1 << (bits - 1)), (1 << (bits - 1)) - 1) if signed else (0, (1 << bits) - 1)
    return int(clamp(round_half_away(value / scale), lo, hi))


def ext_to_float(i, spec):
    return i * spec[1]


# =====================================================================================================================
# Chaos rigid body (the server's hull)
# =====================================================================================================================
class Body:
    """FPBDRigidsEvolutionGBF::Integrate for one dynamic particle with no contacts: V += a dt, W += I_w^-1 tau dt,
    impulses, ether drag (1 - c dt), max angular speed clamp, then P += V dt and Q from W (dq = w q / 2). The state is
    kept at the actor origin (rotation) and the centre of mass (position)."""

    def __init__(self, P, actor_loc, yaw_deg=0.0):
        self.P = P
        self.mass = P['MassKg']
        self.com_local = (-170.0, 0.0, 0.0)          # DesiredCenterOfMass (ApplyBodySettings moves the COM there)
        self.q = rot2quat(0.0, yaw_deg, 0.0)
        self.com = add(actor_loc, qrot(self.q, self.com_local))
        self.v = (0.0, 0.0, 0.0)
        self.w = (0.0, 0.0, 0.0)
        self.clear()
        self.gravity = True

    def clear(self):
        self.force = (0.0, 0.0, 0.0)
        self.torque = (0.0, 0.0, 0.0)
        self.accel = (0.0, 0.0, 0.0)
        self.alpha = (0.0, 0.0, 0.0)
        self.dv = (0.0, 0.0, 0.0)
        self.dw = (0.0, 0.0, 0.0)

    def actor_loc(self):
        return sub(self.com, qrot(self.q, self.com_local))

    def transform_position(self, local):
        return add(self.actor_loc(), qrot(self.q, local))

    def world_inv_inertia_mul(self, tau_world):
        return qrot(self.q, mat3_vec(TENSOR_ACTOR_INV, qunrot(self.q, tau_world)))

    def world_inertia_mul(self, alpha_world):
        return qrot(self.q, mat3_vec(TENSOR_ACTOR, qunrot(self.q, alpha_world)))

    # FChaosStateOps
    def add_force_at_location(self, f_world, p_world):
        self.force = add(self.force, f_world)
        self.torque = add(self.torque, cross(sub(p_world, self.com), f_world))

    def add_force_accel(self, a_world):        # AddForce(.., bAccelChange = true)
        self.accel = add(self.accel, a_world)

    def add_torque_accel(self, alpha_world):   # AddTorqueInRadians(.., bAccelChange = true): WorldI * alpha
        self.alpha = add(self.alpha, alpha_world)

    def add_impulse_vel(self, dv):             # AddImpulse(.., bVelChange = true)
        self.dv = add(self.dv, dv)

    def add_impulse_at_location(self, j_world, p_world):  # AddImpulseAtLocation (kg cm/s)
        self.dv = add(self.dv, mul(j_world, 1.0 / self.mass))
        self.dw = add(self.dw, self.world_inv_inertia_mul(cross(sub(p_world, self.com), j_world)))

    def integrate(self, dt, ang_damping, lin_damping, max_ang_deg):
        a = add(mul(self.force, 1.0 / self.mass), self.accel)
        if self.gravity:
            a = add(a, (0.0, 0.0, -G))
        alpha = add(self.world_inv_inertia_mul(self.torque), self.alpha)
        v = add(add(self.v, mul(a, dt)), self.dv)
        w = add(add(self.w, mul(alpha, dt)), self.dw)
        v = mul(v, max(0.0, 1.0 - lin_damping * dt))
        w = mul(w, max(0.0, 1.0 - ang_damping * dt))
        w = clampsize(w, max_ang_deg * D2R)
        self.com = add(self.com, mul(v, dt))
        wq = (w[0], w[1], w[2], 0.0)
        dq = qmul(wq, self.q)
        self.q = qnorm(tuple(self.q[i] + 0.5 * dt * dq[i] for i in range(4)))
        self.v, self.w = v, w
        self.clear()


# =====================================================================================================================
# UAirshipFlightComponent (one instance per machine: the server's drives the forces, the pilot client's only shapes)
# =====================================================================================================================
class FlightModel:
    def __init__(self, P, scheme, sim, authority=True, ctrl_inertia='chaos'):
        self.P = P
        self.scheme = scheme
        self.sim = sim
        self.authority = authority
        # 'chaos' (v1 C++): GetInertiaTensor() components used as hull axes. 'hull': the fix, the true hull-axis tensor
        # (R_mass diag(I) R_mass^T, off-diagonals included). 'hull_diag': only its diagonal.
        self.ctrl_mode = ctrl_inertia
        self.ctrl_inertia = CHAOS_I if ctrl_inertia == 'chaos' else HULL_AXIS_I
        self.sh_throttle = self.sh_boost = self.sh_lift = self.sh_steer = self.sh_strafe = 0.0
        self.b_brake = self.b_aiming = self.b_drifting = False
        self.boost_active = False
        self.local_boost_active = False
        self.last_kick = -1000.0
        self.regen_timer = 0.0
        self.drift_time = 0.0
        self.hold_valid = False
        self.brake_was = False
        self.hold_z = 0.0
        self.pod_init = False
        self.pod_force = [0.0] * 4
        self.ground_dist = [-1.0] * 4
        self.min_ground = -1.0
        self.fuel = P['BoostFuelMax']
        self.cosmetic = {}
        self.debug = {}
        self.wind_seed = 0.0

    # ------------------------------------------------------------------------------------------------ boost (server)
    def update_boost_server(self, want, dt, body, now):
        P = self.P
        if want and not self.boost_active and self.fuel >= P['BoostMinFuelToStart']:
            self.boost_active = True
            self.fuel = max(0.0, self.fuel - P['BoostStartFuelCost'])
            if P['BoostKickDV'] > 0 and now - self.last_kick >= P['BoostKickCooldown']:
                body.add_impulse_vel(mul(qrot(body.q, (1.0, 0.0, 0.0)), P['BoostKickDV']))
                self.last_kick = now
        if not want or self.fuel <= 0:
            self.boost_active = False
        if self.boost_active:
            self.fuel = max(0.0, self.fuel - P['BoostDrainRate'] * dt)
            self.regen_timer = 0.0
        else:
            self.regen_timer += dt
            if self.regen_timer >= P['BoostRegenDelay']:
                self.fuel = min(P['BoostFuelMax'], self.fuel + P['BoostRegenRate'] * dt)
        return self.boost_active

    def update_boost_client(self, want, replicated_fuel):
        """The pilot's client gates its own boost by the replicated fuel (cosmetics)."""
        if want and not self.local_boost_active and replicated_fuel >= self.P['BoostMinFuelToStart']:
            self.local_boost_active = True
        if not want or replicated_fuel <= 0:
            self.local_boost_active = False
        return self.local_boost_active

    # ------------------------------------------------------------------------------------------------ shaping (every machine)
    def shape_controls(self, controls, dt, fwd_speed):
        P = self.P
        raw_steer = controls.get_steer()
        self.b_brake = controls.has(BUTTON_BRAKE)
        self.b_aiming = controls.has(BUTTON_AIM)
        self.b_drifting = self.b_brake and abs(raw_steer) > P['DriftSteerThreshold'] and fwd_speed > P['DriftMinSpeed']
        thr_target = controls.get_throttle()
        if self.b_brake and not self.b_drifting:
            thr_target = -P['BrakeReverseThrottle'] if fwd_speed > 100.0 else 0.0
        boost = controls.has(BUTTON_BOOST)
        targets = dict(throttle=thr_target, boost=1.0 if boost else 0.0, lift=controls.get_lift(), steer=raw_steer,
                       strafe=controls.get_strafe(), brake=self.b_brake, drifting=self.b_drifting)
        self.scheme.shaping_targets(self.sim, self, controls, targets, fwd_speed)
        self.b_brake, self.b_drifting = targets['brake'], targets['drifting']
        self.sh_throttle = approach_ud(self.sh_throttle, targets['throttle'], dt, P['ThrottleTauUp'], P['ThrottleTauDown'])
        self.sh_boost = approach(self.sh_boost, targets['boost'], dt, P['BoostTauUp'] if targets['boost'] > 0.5 else P['BoostTauDown'])
        self.sh_lift = approach(self.sh_lift, targets['lift'], dt, P['LiftTau'])
        self.sh_steer = approach(self.sh_steer, targets['steer'], dt, P['SteerTau'])
        self.sh_strafe = approach(self.sh_strafe, targets['strafe'], dt, P['StrafeTau'])

    def compute_gimbals(self):
        P = self.P
        mx = max(P['ThrusterGimbalMaxDeg'], 0.0)
        pitch = P['GimbalPitchPerThrottle'] * self.sh_throttle + P['GimbalPitchPerBoost'] * self.sh_boost - (
            P['GimbalPitchPerBrake'] if self.b_brake else 0.0)
        out = []
        for i in range(4):
            roll = P['GimbalRollPerStrafe'] * self.sh_strafe + P['GimbalRollPerSteer'] * self.sh_steer * (1.0 if FRONT_POD[i] else -1.0)
            p_ = clamp(pitch, -mx, mx)
            r_ = clamp(roll, -mx, mx)
            tot = math.hypot(p_, r_)
            if tot > mx and tot > 1e-6:
                p_ *= mx / tot
                r_ *= mx / tot
            out.append((p_, r_))
        return out

    # ------------------------------------------------------------------------------------------------ ground (server)
    def trace_ground(self, body, ground_fn):
        P = self.P
        self.min_ground = -1.0
        for i in range(4):
            depth = NOZZLE_DEPTH[i]
            start = body.transform_position(POD_LOCAL[i])
            gz = ground_fn(start[0], start[1])
            length = P['GroundTraceLength'] + depth
            hit = start[2] - gz
            self.ground_dist[i] = max(0.0, hit - depth) if (gz is not None and 0.0 <= hit <= length) else -1.0
            if self.ground_dist[i] >= 0 and (self.min_ground < 0 or self.ground_dist[i] < self.min_ground):
                self.min_ground = self.ground_dist[i]

    # ------------------------------------------------------------------------------------------------ forces (server)
    def apply_forces(self, body, dt, now):
        P = self.P
        sim = self.sim
        q = body.q
        Fwd = qrot(q, (1.0, 0.0, 0.0))
        Right = qrot(q, (0.0, 1.0, 0.0))
        Up = qrot(q, (0.0, 0.0, 1.0))
        Mass = body.mass
        Gravity = G
        W = Mass * Gravity
        V = body.v
        AngVel = body.w
        COMLocal = body.com_local
        Vb = qunrot(q, V)
        Vf, Vl, Vz = Vb[0], Vb[1], V[2]
        Z = body.actor_loc()[2]
        Inertia = self.ctrl_inertia
        Boost, Steer, Strafe, Lift, Throttle = self.sh_boost, self.sh_steer, self.sh_strafe, self.sh_lift, self.sh_throttle
        brake, drifting = self.b_brake, self.b_drifting

        # ---- commands (forward, vertical, attitude targets, yaw rate, lateral) ---------------------------------
        AFanEff = lerp(P['AFan'], P['AFanBoost'], Boost)
        VTopEff = max(lerp(P['VTop'], P['VTopBoost'], Boost), 1.0)
        if Throttle >= 0:
            AFanCmd = AFanEff * Throttle * max(0.0, 1.0 - (max(Vf, 0.0) / VTopEff) ** P['ThrustFadeExponent'])
        else:
            ARev = P['AFan'] if (brake and not drifting) else P['AFanRev']
            AFanCmd = ARev * Throttle * max(0.0, 1.0 - (max(-Vf, 0.0) / max(P['VTopRev'], 1.0)) ** 2)
        ADrag = -(P['DragC1'] * Vf + P['DragC2'] * Vf * abs(Vf))
        ABrake = -P['Kbrake'] * Vf * (P['DriftBrakeScale'] if drifting else 1.0) if brake else 0.0

        brake_pressed = brake and not self.brake_was
        self.brake_was = brake
        if abs(Lift) >= P['LiftDeadZone']:
            VzCmd = Lift * (P['ClimbRate'] if Lift > 0 else P['DescendRate'])
            self.hold_valid = False
        else:
            if not self.hold_valid:
                self.hold_z = Z + Vz * P['HoldCaptureLead']
                self.hold_valid = True
            if brake_pressed:
                self.hold_z = Z
            VzCmd = clamp(P['Kz'] * (self.hold_z - Z), -P['HoldMaxSpeed'], P['HoldMaxSpeed'])
        if P['MinClearance'] > 0 and self.min_ground >= 0:
            VzCmd = max(VzCmd, P['Kfloor'] * (P['MinClearance'] - self.min_ground))
            if P['FloorBrakeAccel'] > 0:
                VzCmd = max(VzCmd, -math.sqrt(2 * P['FloorBrakeAccel'] * max(self.min_ground - P['MinClearance'], 0.0)))
        if P['bUseCeiling']:
            VzCmd = min(VzCmd, P['Kceil'] * (P['CeilingZ'] - Z))

        BankMax = P['BankMaxDriftDeg'] if drifting else lerp(P['BankMaxDeg'], P['BankMaxBoostDeg'], Boost)
        BankDeg = BankMax * Steer * clamp(Vf / max(P['BankFullSpeed'], 1.0), P['BankMinFraction'], 1.0) + P['StrafeBankDeg'] * Strafe

        AbsVf = abs(Vf)
        if AbsVf <= P['YawRateMidSpeed']:
            RmaxDeg = lerp(P['YawRateAtRest'], P['YawRateAtMid'], AbsVf / max(P['YawRateMidSpeed'], 1.0))
        else:
            RmaxDeg = lerp(P['YawRateAtMid'], P['YawRateAtTop'],
                           clamp((AbsVf - P['YawRateMidSpeed']) / max(P['YawRateTopSpeed'] - P['YawRateMidSpeed'], 1.0), 0.0, 1.0))
        RmaxDeg = P['YawRateDrift'] if drifting else lerp(RmaxDeg, P['YawRateBoost'], Boost)

        Klat = P['DriftKlat'] if drifting else lerp(P['GripKlat'], P['BoostKlat'], Boost)
        ALatMax = (P['DriftALatMaxG'] if drifting else lerp(P['GripALatMaxG'], P['BoostALatMaxG'], Boost)) * Gravity
        Eta = P['DriftEta'] if drifting else lerp(P['GripEta'], P['BoostEta'], Boost)

        cmd = dict(AFanCmd=AFanCmd, ADrag=ADrag, ABrake=ABrake, VzCmd=VzCmd, BankDeg=BankDeg, RmaxDeg=RmaxDeg,
                   YawRateCmd=Steer * RmaxDeg * D2R, Klat=Klat, ALatMax=ALatMax, Eta=Eta,
                   VlTarget=Strafe * P['StrafeSpeed'], PitchExtraDeg=0.0, Vf=Vf, Vl=Vl, Vz=Vz, Z=Z,
                   Fwd=Fwd, Right=Right, Up=Up, drifting=drifting, brake=brake)
        self.scheme.server_commands(sim, self, cmd)
        AFanCmd, ADrag, ABrake, VzCmd = cmd['AFanCmd'], cmd['ADrag'], cmd['ABrake'], cmd['VzCmd']
        BankDeg, YawRateCmd = cmd['BankDeg'], cmd['YawRateCmd']
        Klat, ALatMax, Eta = cmd['Klat'], cmd['ALatMax'], cmd['Eta']
        ACmd = AFanCmd + ADrag + ABrake
        PitchDeg = clamp(-P['PitchPerG'] * ACmd / Gravity, P['PitchMinDeg'], P['PitchMaxDeg']) - P['BoostPitchDeg'] * Boost + \
            P['LiftPitchDeg'] * Lift + cmd['PitchExtraDeg']

        FvWorld = clamp(Mass * (Gravity + P['Kvz'] * (VzCmd - Vz)), P['CollectiveMin'] * W, P['CollectiveMax'] * W)
        FvBody = FvWorld / max(0.5, Up[2])

        # ---- attitude PD ------------------------------------------------------------------------------------------
        cur = quat2rot(q)
        qd = rot2quat(PitchDeg, cur[1], BankDeg)
        qe = qmul(qd, qinv(q))
        if qe[3] < 0:
            qe = (-qe[0], -qe[1], -qe[2], -qe[3])
        ax, ang = to_axis_angle(qe)
        Err = mul(ax, ang)
        TiltRate = (AngVel[0], AngVel[1], 0.0)
        AlphaTilt = add(mul(Fwd, P['KpRoll'] * dot(Err, Fwd) - P['KdRoll'] * dot(TiltRate, Fwd)),
                        mul(Right, P['KpPitch'] * dot(Err, Right) - P['KdPitch'] * dot(TiltRate, Right)))
        ATb = qunrot(q, AlphaTilt)
        # the yaw command (state only) is worked out here so the 'hull' fix can use the full tensor
        YawRate = AngVel[2]
        AlphaZ = clamp(P['Kr'] * (YawRateCmd - YawRate) + P['AngularDamping'] * YawRateCmd, -P['AlphaYawMax'], P['AlphaYawMax'])
        if self.ctrl_mode == 'hull':
            T = TENSOR_ACTOR
            TauX = T[0][0] * ATb[0] + T[0][1] * ATb[1] + T[0][2] * AlphaZ
            TauY = T[1][0] * ATb[0] + T[1][1] * ATb[1] + T[1][2] * AlphaZ
            TauZ = T[2][0] * ATb[0] + T[2][1] * ATb[1] + T[2][2] * AlphaZ
        else:
            TauX = Inertia[0] * ATb[0]
            TauY = Inertia[1] * ATb[1]
            TauZ = Inertia[2] * AlphaZ

        # ---- thruster mixing ---------------------------------------------------------------------------------------
        gim = self.compute_gimbals()
        PodDir, PodArm = [], []
        A = [[0.0] * 4 for _ in range(3)]
        for i in range(4):
            gp, gr = gim[i]
            d = norm((math.tan(gp * D2R), math.tan(gr * D2R), 1.0))
            r = sub(POD_LOCAL[i], COMLocal)
            tpf = cross(r, d)
            PodDir.append(d)
            PodArm.append(r)
            A[0][i], A[1][i], A[2][i] = d[2], tpf[0], tpf[1]
        M = [[sum(A[r][k] * A[c][k] for k in range(4)) for c in range(3)] for r in range(3)]
        yc = solve3(M, [FvBody, 0.0, 0.0])
        ya = solve3(M, [0.0, TauX, TauY])
        if yc is not None and ya is not None:
            Col = [A[0][i] * yc[0] + A[1][i] * yc[1] + A[2][i] * yc[2] for i in range(4)]
            Att = [A[0][i] * ya[0] + A[1][i] * ya[1] + A[2][i] * ya[2] for i in range(4)]
        else:
            Col, Att = [FvBody / 4.0] * 4, [0.0] * 4
        FMin = P['PodForceMin'] * W
        FMax = max(P['PodForceMax'], P['PodForceMin']) * W
        S = 1.0
        for i in range(4):
            if Att[i] > 1e-6:
                S = min(S, (FMax - Col[i]) / Att[i])
            elif Att[i] < -1e-6:
                S = min(S, (FMin - Col[i]) / Att[i])
        S = clamp(S, 0.0, 1.0)
        if not self.pod_init:
            self.pod_force = [clamp(Col[i], FMin, FMax) for i in range(4)]
            self.pod_init = True
        PodSum = (0.0, 0.0, 0.0)
        PodTauZ = 0.0
        PodWorld = []
        for i in range(4):
            tgt = clamp(Col[i] + S * Att[i], FMin, FMax)
            self.pod_force[i] = approach(self.pod_force[i], tgt, dt, P['PodForceTauUp'] if tgt > self.pod_force[i] else P['PodForceTauDown'])
            cushion = 0.0
            gd = self.ground_dist[i]
            if P['GroundEffectStrength'] > 0 and 0.0 <= gd < P['GroundTraceLength']:
                cushion = 0.25 * W * P['GroundEffectStrength'] * (1.0 - gd / max(P['GroundTraceLength'], 1.0)) ** 2
            fb = mul(PodDir[i], self.pod_force[i] + cushion)
            PodSum = add(PodSum, fb)
            PodTauZ += cross(PodArm[i], fb)[2]
            PodWorld.append(qrot(q, fb))
        AlphaGyroTilt = clampsize(mul(AlphaTilt, 1.0 - S), P['GyroTiltMax'])

        # ---- yaw (AlphaZ / TauZ above) ----------------------------------------------------------------------------
        Izz = TENSOR_ACTOR[2][2] if self.ctrl_mode == 'hull' else Inertia[2]

        # ---- fans --------------------------------------------------------------------------------------------------
        Psi = (-P['FanYawMaxDeg'] * Steer) * D2R
        FanDir = (1.0, math.tan(Psi), 0.0)
        KL = cross(sub(FAN_LOCAL[0], COMLocal), FanDir)[2]
        KR = cross(sub(FAN_LOCAL[1], COMLocal), FanDir)[2]
        KDiff = 0.5 * (KL - KR)
        FanMaxF = lerp(P['FanMax'], P['FanMaxBoost'], Boost) * W
        Total = clamp(Mass * AFanCmd - PodSum[0], -2 * FanMaxF, 2 * FanMaxF)
        RudCap = min(P['RudderAuthority'] * (Vf / max(P['RudderRefSpeed'], 1.0)) ** 2, P['RudderMaxAlpha']) * abs(Steer)
        RudderAlpha = clamp(AlphaZ - (PodTauZ + 0.5 * Total * (KL + KR)) / Izz, -RudCap, RudCap) if Izz > 1e-4 else 0.0
        TauKnown = PodTauZ + 0.5 * Total * (KL + KR) + Izz * RudderAlpha
        DMax = max(0.0, 2 * FanMaxF - abs(Total))
        D = clamp((TauZ - TauKnown) / KDiff, -DMax, DMax) if abs(KDiff) > 1 else 0.0
        FanF = [0.5 * Total + 0.5 * D, 0.5 * Total - 0.5 * D]
        AlphaGyroZ = clamp((TauZ - TauKnown - KDiff * D) / Izz, -P['GyroYawMax'], P['GyroYawMax']) if Izz > 1e-4 else 0.0

        # ---- lateral grip, strafe, drift ----------------------------------------------------------------------------
        ALatCmd = clamp(Klat * (cmd['VlTarget'] - Vl), -ALatMax, ALatMax)
        ALatPhys = (PodSum[1] + (FanF[0] + FanF[1]) * FanDir[1]) / Mass
        AGrip = ALatCmd - ALatPhys
        ARedirect = Eta * abs(AGrip) if (Vf > P['RedirectMinSpeed'] and AGrip * Vl < 0) else 0.0
        drift_kick = 0.0
        if drifting:
            self.drift_time += dt
        else:
            if self.drift_time >= P['DriftBoostMinTime'] and P['DriftBoostDV'] > 0:
                body.add_impulse_vel(mul(Fwd, P['DriftBoostDV']))
                drift_kick = P['DriftBoostDV']
            self.drift_time = 0.0

        # ---- wind ---------------------------------------------------------------------------------------------------
        WindScale = 1.0 - clamp(size(V) / max(P['WindFadeSpeed'], 1.0), 0.0, 1.0)
        if not sim.wind:
            WindScale = 0.0
        seed = self.wind_seed
        WindLat = P['WindLateralAccel'] * WindScale * perlin1d(now * P['WindLateralFrequency'] + seed)
        WindRoll = P['WindRollAccel'] * WindScale * perlin1d(now * P['WindRollFrequency'] + seed + 17.3)
        WindPitch = P['WindPitchAccel'] * WindScale * perlin1d(now * P['WindPitchFrequency'] + seed + 41.9)

        # ---- apply ----------------------------------------------------------------------------------------------------
        for i in range(4):
            body.add_force_at_location(PodWorld[i], body.transform_position(POD_LOCAL[i]))
        for j in range(2):
            body.add_force_at_location(qrot(q, mul(FanDir, FanF[j])), body.transform_position(FAN_LOCAL[j]))
        ACom = add(mul(Right, AGrip + WindLat), mul(Fwd, ADrag + ABrake + ARedirect))
        sp = size(V)
        if sp > P['HardSpeedCap']:
            ACom = sub(ACom, mul(norm(V), P['HardCapGain'] * (sp - P['HardSpeedCap'])))
        AlphaCom = add(add(mul(Up, RudderAlpha + AlphaGyroZ), AlphaGyroTilt), add(mul(Fwd, WindRoll), mul(Right, WindPitch)))
        out = dict(ACom=ACom, AlphaCom=AlphaCom, PodWorld=PodWorld, FanF=FanF, S=S, D=D, Total=Total)
        self.scheme.server_forces(sim, self, cmd, out)
        body.add_force_accel(out['ACom'])
        body.add_torque_accel(out['AlphaCom'])
        self.debug = dict(S=S, D=D, Total=Total, FanF=FanF, PodF=list(self.pod_force), GyroZ=AlphaGyroZ, Rudder=RudderAlpha,
                          AlphaZ=AlphaZ, BankDeg=BankDeg, PitchDeg=PitchDeg, AGrip=AGrip, ACmd=ACmd, VzCmd=VzCmd,
                          YawRateCmd=YawRateCmd, AlphaGyroTilt=AlphaGyroTilt, DriftKick=drift_kick, ARedirect=ARedirect)

    # ------------------------------------------------------------------------------------------------ cosmetics
    def update_cosmetic(self, fwd_speed):
        P = self.P
        c = self.cosmetic
        c['Throttle'], c['Steer'], c['Lift'], c['Strafe'], c['Boost'] = self.sh_throttle, self.sh_steer, self.sh_lift, self.sh_strafe, self.sh_boost
        c['bBrake'], c['bAiming'] = self.b_brake, self.b_aiming
        c['FanYawDeg'] = -P['FanYawMaxDeg'] * self.sh_steer
        vtop = max(lerp(P['VTop'], P['VTopBoost'], self.sh_boost), 1.0)
        fwd = self.sh_throttle * max(0.0, 1.0 - (max(fwd_speed, 0.0) / vtop) ** P['ThrustFadeExponent']) if self.sh_throttle >= 0 else self.sh_throttle
        diff = self.sh_steer * P['FanSteerShare'] * (1.0 - 0.5 * abs(fwd))
        c['FanThrust'] = (clamp(fwd + diff, -1.0, 1.0), clamp(fwd - diff, -1.0, 1.0))
        c['PodGimbal'] = self.compute_gimbals()
        c['PodThrustAlpha'] = [clamp(1.0 + P['PodAlphaPerLift'] * self.sh_lift + P['PodAlphaPerBoost'] * self.sh_boost
                                     + P['PodAlphaPerThrottle'] * abs(self.sh_throttle)
                                     + P['PodAlphaPerSteer'] * self.sh_steer * (1.0 if LEFT_POD[i] else -1.0), 0.0, 1.5)
                               for i in range(4)]


class AnimCosmetics:
    """UAirshipAnimInstance: turbine housing slew and the helm wheel spring (the M10 cosmetic response)."""

    def __init__(self, PP):
        self.PP = PP
        self.turbine_yaw = 0.0
        self.wheel = 0.0
        self.wheel_vel = 0.0

    def update(self, cosmetic, dt):
        PP = self.PP
        tgt = clamp(cosmetic.get('FanYawDeg', 0.0), -PP['TurbineYawMaxDeg'], PP['TurbineYawMaxDeg'])
        step = PP['TurbineYawSlewDegPerSec'] * dt
        self.turbine_yaw += clamp(tgt - self.turbine_yaw, -step, step)
        target = cosmetic.get('Steer', 0.0) * PP['WheelDegPerSteer']
        om = PP['WheelSpringOmega']
        self.wheel_vel += (om * om * (target - self.wheel) - 2.0 * PP['WheelSpringDamping'] * om * self.wheel_vel) * dt
        self.wheel += self.wheel_vel * dt


# =====================================================================================================================
# Camera (pilot's machine)
# =====================================================================================================================
class CameraState:
    def __init__(self, yaw=0.0, pitch=-12.0):
        self.control_yaw = yaw         # PlayerController control rotation (deg, world)
        self.control_pitch = pitch
        self.view_yaw = yaw            # after the spring arm's rotation lag (what the camera shows / aims with)
        self.view_pitch = pitch
        self.last_look_time = -1000.0
        self.free_look = True          # Classic: the camera never steers
        self.arm = 6500.0
        self.fov = 85.0

    def look_dir(self):
        cy, sy = math.cos(self.view_yaw * D2R), math.sin(self.view_yaw * D2R)
        cp, sp = math.cos(self.view_pitch * D2R), math.sin(self.view_pitch * D2R)
        return (cp * cy, cp * sy, sp)


# =====================================================================================================================
# Control schemes
# =====================================================================================================================
class Command:
    """An open-loop maneuver command in scheme-neutral terms (metrics M1-M10). A scheme's command_raw turns it into
    the RAW inputs its own controls need (keys held, telegraph taps, camera offsets, ...).
      thrust   -1..1  forward drive wanted (1 = full ahead)
      steer    -1..1  turn wanted (+ = right)
      lift     -1..1  climb / descend
      strafe   -1..1  side slide (+ = right)
      boost, brake, drift (brake + steer slide), aim  bool
      look_yaw / look_pitch  absolute camera direction to hold (deg, world) or None = leave the camera alone"""
    __slots__ = ('thrust', 'steer', 'lift', 'strafe', 'boost', 'brake', 'drift', 'aim', 'look_yaw', 'look_pitch', 'fire')

    def __init__(self, thrust=0.0, steer=0.0, lift=0.0, strafe=0.0, boost=False, brake=False, drift=False, aim=False,
                 look_yaw=None, look_pitch=None, fire=False):
        self.thrust, self.steer, self.lift, self.strafe = thrust, steer, lift, strafe
        self.boost, self.brake, self.drift, self.aim = boost, brake, drift, aim
        self.look_yaw, self.look_pitch, self.fire = look_yaw, look_pitch, fire


class Intent:
    """Closed-loop goal for the bots (course, broadside): where to go, how fast, how high, where to look.
      course_deg  desired course over ground (world yaw of the velocity, deg)
      speed       desired forward speed (m/s); None = as fast as the scheme goes without boost
      alt         desired altitude of the actor origin (m, world Z)
      look_at     world point (m) the pilot looks at, or None = look along the course
      yaw_rate_ff feed-forward turn rate (deg/s, + right) the path needs, 0 if unknown
      brake_hint  True when the planner wants a hard slow-down (hairpin)"""
    __slots__ = ('course_deg', 'speed', 'alt', 'look_at', 'yaw_rate_ff', 'brake_hint')

    def __init__(self, course_deg=0.0, speed=None, alt=None, look_at=None, yaw_rate_ff=0.0, brake_hint=False):
        self.course_deg, self.speed, self.alt = course_deg, speed, alt
        self.look_at, self.yaw_rate_ff, self.brake_hint = look_at, yaw_rate_ff, brake_hint


class Scheme:
    """Classic (v1): the controls as shipped. Subclass it for a new scheme and override what changes (README.md).

    Pilot side (pilot's machine, every frame):  camera() -> pilot_input()   [raw keys + camera -> FAirshipPilotInput]
    Server side (every server frame):           server_controls() -> shaping_targets() -> server_commands() -> server_forces()
    Bot adapters (bench only):                  command_raw() (open-loop maneuvers), intent_raw() (closed-loop goals)
    """
    key = 'classic'
    enum = 0
    label = 'Classic (v1)'
    ctrl_inertia = 'chaos'   # 'hull' = assume the ApplyForces inertia fix (README: Finding 1); needs that C++ change
    flight = {}        # UAirshipFlightComponent overrides (the scheme's preset table)
    pawn = {}          # AAirshipPawn / anim overrides
    ext_fields = {}    # extra FAirshipPilotInput fields: name -> (bits, scale, signed)

    # ---- runtime state (reset on a switch and on board / exit) ----------------------------------------------------
    def reset(self, sim):
        """Scheme-local runtime state on the pilot's machine (sim.pilot_state) and the server (sim.server_state)."""
        sim.pilot_state = {}
        sim.server_state = {}

    # ---- (c) camera model: pilot's machine, before the input is gathered ----------------------------------------
    def camera(self, sim, raw, cam, view, dt):
        """AAirshipPawn::UpdateCamera + the spring arm: the harness / mouse sets the control rotation, recenter
        behind the ship after RecenterDelay without look input (moving, not aiming), pitch clamp, rotation lag."""
        PP = sim.PP
        now = sim.time
        if raw.cam_yaw is not None:
            cam.control_yaw = raw.cam_yaw
        if raw.cam_pitch is not None:
            cam.control_pitch = raw.cam_pitch
        if raw.look:
            cam.last_look_time = now
        if raw.zoom:
            cam.arm = clamp(cam.arm - raw.zoom * 800.0, PP['CameraArmMin'], PP['CameraArmMax'])
        cam.control_pitch = wrap180(cam.control_pitch)
        fwd = view['ForwardSpeed']
        if PP['RecenterSpeed'] > 0 and now - cam.last_look_time > PP['RecenterDelay'] and fwd > PP['RecenterMinSpeed'] and not raw.aim:
            a = 1.0 - math.exp(-PP['RecenterSpeed'] * dt)
            cam.control_yaw += wrap180(view['YawDeg'] - cam.control_yaw) * a
            cam.control_pitch += (PP['CameraDefaultPitch'] - cam.control_pitch) * a
        cam.control_pitch = clamp(cam.control_pitch, PP['CameraPitchMin'], PP['CameraPitchMax'])
        self.camera_lag(sim, cam, dt)
        cam.free_look = True

    def camera_lag(self, sim, cam, dt):
        """USpringArmComponent rotation lag (RInterpTo at CameraRotationLagSpeed, substeps of 1/60 s)."""
        speed = sim.PP['CameraRotationLagSpeed']
        n = max(1, int(math.ceil(dt / (1.0 / 60.0) - 1e-9)))
        h = dt / n
        for _ in range(n):
            a = clamp(h * speed, 0.0, 1.0)
            cam.view_yaw += wrap180(cam.control_yaw - cam.view_yaw) * a
            cam.view_pitch += (cam.control_pitch - cam.view_pitch) * a
        cam.view_yaw = wrap180(cam.view_yaw)

    # ---- (a) pilot-side input shaping: AAirshipPawn::GatherLocalInput -------------------------------------------
    def pilot_input(self, sim, raw, cam, view, dt):
        p = PilotInput()
        p.set_axes(raw.throttle, raw.steer, raw.lift, raw.strafe)
        p.set_button(BUTTON_BOOST, raw.boost)
        p.set_button(BUTTON_BRAKE, raw.brake)
        p.set_button(BUTTON_AIM, raw.aim)
        aim = sim.aim_point(cam, view)
        if aim is not None:
            p.aim = aim
            p.set_button(BUTTON_HAS_AIM, True)
        return p

    # ---- (b) server side -----------------------------------------------------------------------------------------
    def server_controls(self, sim, controls, dt):
        """Server, after SelectControls + the boost gate, before the copy to RepInput and the shaping. Return the
        controls to use (e.g. turn a heading target into Steer from the authoritative heading)."""
        return controls

    def shaping_targets(self, sim, fm, controls, targets, fwd_speed):
        """Every machine, inside ShapeControls: the filter targets (throttle, boost, lift, steer, strafe, brake,
        drifting). Change them here (e.g. a telegraph's engine order); cosmetics follow on every machine."""
        return None

    def server_commands(self, sim, fm, cmd):
        """Server, inside ApplyForces after the commands are worked out, before allocation. cmd (writable):
        AFanCmd, ADrag, ABrake (cm/s^2), VzCmd (cm/s), BankDeg, PitchExtraDeg, YawRateCmd (rad/s), RmaxDeg, Klat,
        ALatMax, Eta, VlTarget (cm/s); read-only: Vf, Vl, Vz, Z, Fwd, Right, Up, drifting, brake."""
        return None

    def server_forces(self, sim, fm, cmd, out):
        """Server, after the forces: out['ACom'] (world cm/s^2 at the COM) and out['AlphaCom'] (world rad/s^2) may be
        added to (exact accelerations, like the C++ AddForce / AddTorqueInRadians with bAccelChange)."""
        return None

    def telemetry(self, sim, tele):
        """Scheme fields of FAirshipFlightTelemetry (contract): Scheme, ThrottleOrder, DriftCharge,
        bHeadingTargetActive, HeadingTargetDeg, bFreeLook."""
        tele['Scheme'] = self.enum
        tele['ThrottleOrder'] = -2.0
        tele['DriftCharge'] = 0.0
        tele['bHeadingTargetActive'] = False
        tele['HeadingTargetDeg'] = 0.0
        tele['bFreeLook'] = True

    # ---- bot adapters -------------------------------------------------------------------------------------------
    def command_raw(self, sim, cmd):
        """Open-loop maneuver -> RAW inputs (Classic: hold the matching keys)."""
        r = RawInput(throttle=cmd.thrust, steer=cmd.steer, lift=cmd.lift, strafe=cmd.strafe, boost=cmd.boost,
                     brake=cmd.brake or cmd.drift, aim=cmd.aim, fire=cmd.fire)
        if cmd.look_yaw is not None:
            r.cam_yaw, r.cam_pitch, r.look = cmd.look_yaw, cmd.look_pitch if cmd.look_pitch is not None else -12.0, True
        return r

    # Bot gains for this scheme (course.tune_bot finds them; the sloppy bot multiplies the control gains by its noise):
    #   course (1/s) heading error -> turn rate, rate_damp turn-rate error feedback, speed (throttle per m/s), alt (lift
    #   per m), vz_damp (lift per m/s), ct (1/s) cross-track gain and lag (s) heading lead of the path tracker, margin
    #   (m) how far inside the gate edge the racing line stays, turn_frac share of the scheme's turn rate the line uses
    GAINS = dict(course=0.7, rate_damp=0.6, speed=0.25, alt=0.12, vz_damp=0.06, ct=0.5, lag=0.65, margin=7.0, turn_frac=0.85)
    NOISY_GAINS = ('course', 'rate_damp', 'speed', 'alt', 'vz_damp', 'ct')

    def intent_raw(self, sim, intent, view, gains=None):
        """Closed-loop goal -> RAW inputs (Classic: W/S, A/D, Space/Ctrl from P/PD loops; mouse on the look point)."""
        g = dict(self.GAINS)
        if gains:
            g.update(gains)
        P = sim.P
        course = view['CourseDeg'] if view['SpeedMS'] > 3.0 else view['YawDeg']
        err = wrap180(intent.course_deg - course)
        rmax = sim.rmax_deg(view['ForwardSpeedMS'] * 100.0)
        rate_des = clamp(g['course'] * err + intent.yaw_rate_ff, -rmax, rmax)
        steer = clamp((rate_des + g['rate_damp'] * (rate_des - view['YawRateDegS'])) / max(rmax, 1.0), -1.0, 1.0)
        # speed
        vf = view['ForwardSpeedMS']
        brake = False
        if intent.speed is None:
            thr = 1.0
        else:
            ev = intent.speed - vf
            ff = sim.hold_throttle(intent.speed * 100.0)
            thr = clamp(ff + g['speed'] * ev, -1.0, 1.0)
            if ev < -8.0 or intent.brake_hint and ev < -2.0:
                brake, thr = True, 0.0
        # altitude: proportional lift, released near the target (the hold takes over)
        lift = 0.0
        if intent.alt is not None:
            ez = intent.alt - view['AltitudeM']
            lift = clamp(g['alt'] * ez - g['vz_damp'] * view['VerticalSpeedMS'], -1.0, 1.0)
            if abs(lift) < P['LiftDeadZone'] * 1.2:
                lift = 0.0
        r = RawInput(throttle=thr, steer=steer, lift=lift, brake=brake)
        if brake and abs(steer) > P['DriftSteerThreshold'] and vf > P['DriftMinSpeed'] / 100.0:
            # Classic: brake + steer is a drift; a bot that wants to slow down for a turn keeps steer below it
            r.steer = clamp(steer, -P['DriftSteerThreshold'] * 0.9, P['DriftSteerThreshold'] * 0.9)
        self.look(sim, r, intent, view)
        return r

    def look(self, sim, r, intent, view):
        """Mouse: look at intent.look_at (absolute control rotation, counts as look input) or leave the camera."""
        if intent.look_at is None:
            return
        cam_loc = sim.camera_location_m(view)
        d = sub(intent.look_at, cam_loc)
        r.cam_yaw = math.atan2(d[1], d[0]) * R2D
        r.cam_pitch = math.atan2(d[2], math.hypot(d[0], d[1])) * R2D
        r.look = True


class Classic(Scheme):
    pass


SCHEMES = {'classic': Classic}


def register_scheme(cls):
    """Schemes register themselves (scheme_<key>.py: @register_scheme on the class)."""
    SCHEMES[cls.key] = cls
    return cls


def load_scheme(key):
    """Classic, or a scheme module scheme_<key>.py in this folder."""
    key = key.lower()
    if key not in SCHEMES:
        import importlib
        importlib.import_module('scheme_' + key)
    return SCHEMES[key]()


# =====================================================================================================================
# The bench: pilot's machine + network + server
# =====================================================================================================================
def default_ground(x, y):
    """Flat ground at z = 0 (cm)."""
    return 0.0


class Sim:
    """One ship, one pilot. latency_ms = 0: the pilot is the listen-server host (no network, like the standalone PIE
    runs the calibration used). latency_ms > 0: the pilot is a client; its input reaches the server 1 frame + latency
    later (frame order of a one-process PIE), and it sees the server's state latency later.

    Per frame (dt = 1/30 s): pilot camera -> pilot input (scheme) -> local cosmetics -> send; server: receive ->
    SelectControls -> boost gate -> scheme.server_controls -> ShapeControls -> TraceGround -> ApplyForces -> Chaos step.
    """

    def __init__(self, scheme=None, latency_ms=0.0, alt_agl=30.0, yaw_deg=0.0, pos_m=(0.0, 0.0), seed=1, wind=True,
                 ground_fn=None, flight=None, pawn=None, ctrl_inertia=None, net=None):
        self.scheme = scheme or Classic()
        self.P = dict(FLIGHT_DEFAULTS)
        self.P.update(self.scheme.flight)
        if flight:
            self.P.update(flight)
        self.PP = dict(PAWN_DEFAULTS)
        self.PP.update(self.scheme.pawn)
        if pawn:
            self.PP.update(pawn)
        self.dt = DT
        self.frame = 0
        self.t_origin = 0.0
        self.time = 0.0
        self.wind = wind
        self.ground_fn = ground_fn or default_ground
        self.latency_ms = latency_ms
        self.net = net or ('host' if latency_ms <= 0 else 'client')
        self.lag_frames = int(round(latency_ms / 1000.0 / DT))
        gz = self.ground_fn(pos_m[0] * 100.0, pos_m[1] * 100.0) or 0.0
        start = (pos_m[0] * 100.0, pos_m[1] * 100.0, gz + alt_agl * 100.0)
        ctrl_inertia = ctrl_inertia or getattr(self.scheme, 'ctrl_inertia', 'chaos')
        self.ctrl_inertia = ctrl_inertia
        self.body = Body(self.P, start, yaw_deg)
        self.server = FlightModel(self.P, self.scheme, self, True, ctrl_inertia)
        self.server.wind_seed = (seed % 97) * 3.7
        self.pilot_fm = FlightModel(self.P, self.scheme, self, False, ctrl_inertia) if self.net == 'client' else self.server
        self.anim = AnimCosmetics(self.PP)
        self.cam = CameraState(yaw_deg, self.PP['CameraDefaultPitch'])
        self.cam.arm = self.PP['CameraArmLength']
        self.rng = random.Random(seed)
        self.uplink = []           # (arrival frame, PilotInput)
        self.server_input = PilotInput()
        self.has_server_input = False
        self.last_server_input_time = -1000.0
        self.local_input = PilotInput()
        self.last_sent = None
        self.last_send_time = -1000.0
        self.seq = 0
        self.rep_input = PilotInput()
        self.snapshots = []        # server telemetry after each step (pilot view source)
        self.aim_side = 'port'
        self.last_fire = {'port': -1000.0, 'stbd': -1000.0}
        self.last_fire_pred = {'port': -1000.0, 'stbd': -1000.0}
        self.pending_fire = []
        self.aim_targets = []      # (world point cm, radius cm): bench targets the camera ray can hit
        self.events = []
        self.cannon_shots = []
        self.log = []
        self.scheme.reset(self)
        self.pilot_state = getattr(self, 'pilot_state', {})
        self.server_state = getattr(self, 'server_state', {})
        self._last_raw = RawInput()
        self.server_tele = self.tele_server()
        self.snapshots.append(self.server_tele)

    # ------------------------------------------------------------------------------------------------ helpers
    def rmax_deg(self, vf_cm):
        P = self.P
        a = abs(vf_cm)
        if a <= P['YawRateMidSpeed']:
            return lerp(P['YawRateAtRest'], P['YawRateAtMid'], a / max(P['YawRateMidSpeed'], 1.0))
        return lerp(P['YawRateAtMid'], P['YawRateAtTop'], clamp((a - P['YawRateMidSpeed']) / max(P['YawRateTopSpeed'] - P['YawRateMidSpeed'], 1.0), 0.0, 1.0))

    def top_speed_estimate(self):
        """Level full-throttle top speed (m/s) from the thrust fade and the drag (no boost)."""
        P = self.P
        lo, hi = 0.0, P['VTop']
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            f = P['AFan'] * (1.0 - (mid / P['VTop']) ** P['ThrustFadeExponent']) - (P['DragC1'] * mid + P['DragC2'] * mid * mid)
            lo, hi = (mid, hi) if f > 0 else (lo, mid)
        return lo / 100.0

    def hold_throttle(self, v_cm):
        """Throttle that balances the drag at forward speed v (no boost, level)."""
        P = self.P
        drag = P['DragC1'] * v_cm + P['DragC2'] * v_cm * abs(v_cm)
        fade = max(1e-3, 1.0 - (max(v_cm, 0.0) / P['VTop']) ** P['ThrustFadeExponent'])
        return clamp(drag / (P['AFan'] * fade), 0.0, 1.0)

    def camera_location_m(self, view):
        """Spring arm end: the ship root + TargetOffset, ArmLength back along the view rotation (no collision)."""
        root = view['ActorLocCm']
        d = self.cam.look_dir()
        target = (root[0], root[1], root[2] + self.PP['CameraTargetOffsetZ'])
        loc = sub(target, mul(d, self.cam.arm))
        return mul(loc, 0.01)

    def aim_point(self, cam, view):
        """ComputeLocalAimPoint: camera view ray to CannonAimTraceDistance (free space: the end point; a bench target
        registered in self.aim_targets is hit when the ray passes within its radius)."""
        loc = mul(self.camera_location_m(view), 100.0)
        d = cam.look_dir()
        end = add(loc, mul(d, self.PP['CannonAimTraceDistance']))
        for tgt, radius in self.aim_targets:
            t = dot(sub(tgt, loc), d)
            if 0 < t < self.PP['CannonAimTraceDistance'] and size(sub(add(loc, mul(d, t)), tgt)) < radius:
                return tgt
        return end

    def ground_z_at(self, x, y):
        g = self.ground_fn(x, y)
        return -1e12 if g is None else g

    # ------------------------------------------------------------------------------------------------ telemetry
    def tele_server(self):
        b = self.body
        fm = self.server
        q = b.q
        V = b.v
        vb = qunrot(q, V)
        pit, yaw, roll = quat2rot(q)
        loc = b.actor_loc()
        t = dict(t=self.time, frame=self.frame, ActorLocCm=loc, VelCm=V,
                 SpeedMS=size(V) * 0.01, ForwardSpeedMS=vb[0] * 0.01, LateralSpeedMS=vb[1] * 0.01, VerticalSpeedMS=V[2] * 0.01,
                 AltitudeM=loc[2] * 0.01, GroundClearanceM=fm.min_ground * 0.01 if fm.min_ground >= 0 else -1.0,
                 YawRateDegS=b.w[2] * R2D, RollDeg=roll, PitchDeg=pit, YawDeg=yaw,
                 HoldAltitudeM=fm.hold_z * 0.01 if fm.hold_valid else loc[2] * 0.01, BoostFuel=fm.fuel, MassKg=b.mass,
                 Throttle=fm.sh_throttle, Steer=fm.sh_steer, Lift=fm.sh_lift, Strafe=fm.sh_strafe, Boost=fm.sh_boost,
                 bBraking=fm.b_brake, bDrifting=fm.b_drifting, ForwardSpeed=vb[0],
                 CourseDeg=math.atan2(V[1], V[0]) * R2D if size2d(V) > 1.0 else yaw, AngVel=b.w,
                 Q=q, BoostActive=fm.boost_active, Debug=dict(fm.debug))
        self.scheme.telemetry(self, t)
        return t

    def pilot_view(self):
        """The ship state as the pilot's machine sees it this frame."""
        if self.net == 'host':
            return self.snapshots[-1]
        k = len(self.snapshots) - 1 - self.lag_frames
        return self.snapshots[max(0, k)]

    # ------------------------------------------------------------------------------------------------ one frame
    def step(self, raw):
        if self.net == 'host':
            self._pilot_frame(raw)
            self._server_frame()
        else:
            self._server_frame()
            self._pilot_frame(raw)
        # the anim instance updates after the pawn tick on the pilot's machine
        self.anim.update(self.pilot_fm.cosmetic, self.dt)
        self.log.append(self._frame_record(self.server_tele))
        self.frame += 1
        self.time = self.t_origin + self.frame * self.dt
        return self.log[-1]

    def set_time(self, t):
        """Moves the world clock (GetTimeSeconds) to t now (replays start at the PIE time)."""
        self.t_origin = t - self.frame * self.dt
        self.time = t

    def _pilot_frame(self, raw):
        dt = self.dt
        view = self.pilot_view()
        self.scheme.camera(self, raw, self.cam, view, dt)
        p = self.scheme.pilot_input(self, raw, self.cam, view, dt)
        self.local_input = p
        # cosmetics on the pilot's machine (a client shapes its own input at once, boost gated by replicated fuel)
        fm = self.pilot_fm
        if self.net == 'client':
            c = p.copy()
            c.set_button(BUTTON_BOOST, fm.update_boost_client(p.has(BUTTON_BOOST), view['BoostFuel']))
            fm.shape_controls(c, dt, view['ForwardSpeed'])
            fm.update_cosmetic(view['ForwardSpeed'])
        # send (host: no RPC)
        if self.net == 'host':
            self.server_input = p
            self.has_server_input = True
            self.last_server_input_time = self.time
        else:
            changed = self.last_sent is None or not p.same_controls(self.last_sent)
            if changed or self.time - self.last_send_time >= 1.0 / max(self.P['InputSendRate'], 1.0) - 1e-6:
                self.seq = (self.seq + 1) & 255
                pk = p.copy()
                pk.seq = self.seq
                self.last_sent = pk
                self.last_send_time = self.time
                self.uplink.append((self.frame + 1 + self.lag_frames, pk))
        # UpdateCannonAim: the camera-facing side from the aim point (hull-space Y, hysteresis), every frame
        if p.aim is not None:
            self.compute_aim_side(p.aim, self.body)
        # fire (RequestFire on the pilot's machine -> ServerFireCannons, 1 frame + latency later on a client)
        if raw.fire and p.aim is not None:
            side = self.aim_side
            if self.time - self.last_fire_pred[side] >= self.PP['CannonCooldown']:
                self.last_fire_pred[side] = self.time
                arrival = self.frame if self.net == 'host' else self.frame + 1 + self.lag_frames
                self.pending_fire.append((arrival, side, p.aim))
        self._last_raw = raw
        self._pilot_view_now = view

    def _receive(self):
        keep = []
        for arrival, pk in self.uplink:
            if arrival <= self.frame:
                stale = self.time - self.last_server_input_time > self.P['InputTimeout']
                if self.has_server_input and not stale and ((pk.seq - self.server_input.seq + 128) % 256) - 128 <= 0:
                    continue
                self.server_input = pk
                self.has_server_input = True
                self.last_server_input_time = self.time
            else:
                keep.append((arrival, pk))
        self.uplink = keep

    def _select_controls(self):
        if self.net == 'host':
            return self.local_input.copy()
        fresh = self.has_server_input and self.time - self.last_server_input_time <= self.P['InputTimeout']
        return self.server_input.copy() if fresh else PilotInput()

    def _server_frame(self):
        dt = self.dt
        P = self.P
        b = self.body
        fm = self.server
        if self.net == 'client':
            self._receive()
        fwd_speed = dot(b.v, qrot(b.q, (1.0, 0.0, 0.0)))
        controls = self._select_controls()
        controls.set_button(BUTTON_BOOST, fm.update_boost_server(controls.has(BUTTON_BOOST), dt, b, self.time))
        controls = self.scheme.server_controls(self, controls, dt) or controls
        self.rep_input = controls
        fm.shape_controls(controls, dt, fwd_speed)
        if P['bGroundTraces']:
            fm.trace_ground(b, self.ground_fn)
        else:
            fm.min_ground = -1.0
            fm.ground_dist = [-1.0] * 4
        fm.apply_forces(b, dt, self.time)
        fm.update_cosmetic(fwd_speed)
        self._server_fire()
        b.integrate(dt, P['AngularDamping'], P['LinearDamping'], P['MaxAngularVelocityDeg'])
        self._ground_contact()
        tele = self.tele_server()
        tele['t'] = self.time + dt
        self.server_tele = tele
        self.snapshots.append(tele)
        if len(self.snapshots) > 64:
            del self.snapshots[0]

    def _frame_record(self, tele):
        view = getattr(self, '_pilot_view_now', tele)
        rec = dict(tele)
        # what the pilot's screen shows at the end of this frame: the host renders this frame's physics step; a
        # client shows the server's state latency old (it ticks after the server in a one-process PIE)
        screen = tele if self.net == 'host' else view
        rec['pilot'] = dict(view=view, screen=screen, cam_yaw=self.cam.view_yaw, cam_pitch=self.cam.view_pitch,
                            control_yaw=self.cam.control_yaw, free_look=self.cam.free_look,
                            Steer=self.pilot_fm.sh_steer, Throttle=self.pilot_fm.sh_throttle,
                            FanYawDeg=self.pilot_fm.cosmetic.get('FanYawDeg', 0.0),
                            NozzlePitchDeg=(self.pilot_fm.cosmetic.get('PodGimbal') or [(0.0, 0.0)])[0][0],
                            aim_side=self.aim_side,
                            TurbineYawDeg=self.anim.turbine_yaw, WheelAngleDeg=self.anim.wheel)
        rec['raw'] = self._last_raw.as_dict()
        rec['input'] = dict(throttle=self.local_input.throttle, steer=self.local_input.steer, lift=self.local_input.lift,
                            strafe=self.local_input.strafe, buttons=self.local_input.buttons, ext=dict(self.local_input.ext))
        rec['ground_contact'] = self._contact
        return rec

    # ------------------------------------------------------------------------------------------------ ground contact
    _contact = False

    def _ground_contact(self):
        """No contact solver: the bench only detects the hull's keel / nozzle exits going below the ground and, to keep
        a run going, puts the hull back on the surface with its downward speed removed (counted by the course)."""
        b = self.body
        low = None
        for p in KEEL_POINTS:
            w = b.transform_position(p)
            depth = self.ground_z_at(w[0], w[1]) - w[2]
            if low is None or depth > low:
                low = depth
        self._contact = low is not None and low > 0
        if self._contact:
            b.com = add(b.com, (0.0, 0.0, low))
            if b.v[2] < 0:
                b.v = (b.v[0], b.v[1], 0.0)

    # ------------------------------------------------------------------------------------------------ cannons
    def _server_fire(self):
        """FireCannons on the server (per-side cooldown with 0.1 s tolerance) and the recoil kick of
        HandleCannonsFired: an impulse of -dir * m * CannonRecoilImpulseDV at each muzzle of that side."""
        keep = []
        b = self.body
        for arrival, side, aim in self.pending_fire:
            if arrival > self.frame:
                keep.append((arrival, side, aim))
                continue
            if self.time - self.last_fire[side] < max(self.PP['CannonCooldown'] - 0.1, 0.0):
                continue
            self.last_fire[side] = self.time
            for c in (PORT_CANNONS if side == 'port' else STBD_CANNONS):
                yaw, elev = self.cannon_aim(c, aim, b)
                d = qrot(b.q, self.cannon_dir_local(c, yaw, elev))
                muzzle = b.transform_position(CANNON_MUZZLE[c])
                b.add_impulse_at_location(mul(d, -b.mass * self.PP['CannonRecoilImpulseDV']), muzzle)
                self.cannon_shots.append(dict(t=self.time, cannon=c, side=side, dir=d, muzzle=muzzle, aim=aim))
        self.pending_fire = keep

    def compute_aim_side(self, aim, body):
        local = qunrot(body.q, sub(aim, body.actor_loc()))
        h = self.PP['AimSideHysteresis']
        if self.aim_side == 'port' and local[1] > h:
            self.aim_side = 'stbd'
        elif self.aim_side == 'stbd' and local[1] < -h:
            self.aim_side = 'port'
        return self.aim_side

    def cannon_aim(self, c, target, body):
        """AAirshipPawn::ComputeCannonAim (deg, clamped) plus the unclamped values: (yaw, elev, yaw_raw, elev_raw)."""
        muzzle = body.transform_position(CANNON_MUZZLE[c])
        to = qunrot(body.q, sub(target, muzzle))
        n = size(to)
        if n < 1e-6:
            return 0.0, 0.0
        to = mul(to, 1.0 / n)
        rest = CANNON_REST_DIR[c]
        rest_flat = norm((rest[0], rest[1], 0.0))
        flat = (to[0], to[1], 0.0)
        yaw = math.atan2(cross(rest_flat, flat)[2], dot(rest_flat, flat)) * R2D
        elev = math.atan2(to[2], size2d(flat)) * R2D
        return (clamp(yaw, -self.PP['CannonYawLimitDeg'], self.PP['CannonYawLimitDeg']),
                clamp(elev, self.PP['CannonElevMinDeg'], self.PP['CannonElevMaxDeg']))

    def cannon_angles_raw(self, c, target, body=None):
        body = body or self.body
        muzzle = body.transform_position(CANNON_MUZZLE[c])
        to = qunrot(body.q, sub(target, muzzle))
        rest = CANNON_REST_DIR[c]
        rest_flat = norm((rest[0], rest[1], 0.0))
        flat = (to[0], to[1], 0.0)
        yaw = math.atan2(cross(rest_flat, flat)[2], dot(rest_flat, flat)) * R2D
        elev = math.atan2(to[2], size2d(flat)) * R2D
        return yaw, elev, size(to)

    @staticmethod
    def cannon_dir_local(c, yaw_deg, elev_deg):
        rest = CANNON_REST_DIR[c]
        rest_flat = norm((rest[0], rest[1], 0.0))
        cy, sy = math.cos(yaw_deg * D2R), math.sin(yaw_deg * D2R)
        yawed = (rest_flat[0] * cy - rest_flat[1] * sy, rest_flat[0] * sy + rest_flat[1] * cy, 0.0)
        ce, se = math.cos(elev_deg * D2R), math.sin(elev_deg * D2R)
        return norm((yawed[0] * ce, yawed[1] * ce, se))

    # ------------------------------------------------------------------------------------------------ state setting
    def tele(self):
        return self.server_tele

    def set_state(self, vel_ms=None, yaw_deg=None, pitch_deg=0.0, roll_deg=0.0, yaw_rate_degs=None, alt_m=None,
                  pos_m=None, shaped=None, hold_alt_m=None, fuel=None):
        """Put the ship in a given state (calibration replays start each PIE phase from the measured state)."""
        b = self.body
        loc = b.actor_loc()
        if yaw_deg is not None or pitch_deg or roll_deg:
            cur = quat2rot(b.q)
            b.q = rot2quat(pitch_deg, cur[1] if yaw_deg is None else yaw_deg, roll_deg)
        if pos_m is not None:
            loc = (pos_m[0] * 100.0, pos_m[1] * 100.0, loc[2])
        if alt_m is not None:
            loc = (loc[0], loc[1], alt_m * 100.0)
        b.com = add(loc, qrot(b.q, b.com_local))
        if vel_ms is not None:
            b.v = mul(vel_ms, 100.0)
        if yaw_rate_degs is not None:
            b.w = (0.0, 0.0, yaw_rate_degs * D2R)
        fm = self.server
        if shaped:
            for k, v in shaped.items():
                setattr(fm, k, v)
                if fm is not self.pilot_fm:
                    setattr(self.pilot_fm, k, v)
        if hold_alt_m is not None:
            fm.hold_z = hold_alt_m * 100.0
            fm.hold_valid = True
        if fuel is not None:
            fm.fuel = fuel
        self.server_tele = self.tele_server()
        self.snapshots.append(self.server_tele)


# =====================================================================================================================
# Drivers
# =====================================================================================================================
def run_commands(sim, schedule, seconds):
    """schedule(t, sim) -> Command (open-loop maneuver through the scheme's command_raw). Returns the frame log."""
    n = int(round(seconds / sim.dt))
    start = len(sim.log)
    t0 = sim.time
    for _ in range(n):
        cmd = schedule(sim.time - t0, sim)
        sim.step(sim.scheme.command_raw(sim, cmd))
    return sim.log[start:]


def run_raw(sim, schedule, seconds):
    """schedule(t, sim) -> RawInput (raw keys, like the PIE harness injecting actions)."""
    n = int(round(seconds / sim.dt))
    start = len(sim.log)
    t0 = sim.time
    for _ in range(n):
        sim.step(schedule(sim.time - t0, sim))
    return sim.log[start:]


if __name__ == '__main__':
    # smoke run: hover 3 s, full throttle 10 s
    s = Sim(Classic())
    run_commands(s, lambda t, sim: Command(), 3.0)
    lg = run_commands(s, lambda t, sim: Command(thrust=1.0), 10.0)
    for r in lg[29::30]:
        print('t %5.2f vf %6.2f pitch %6.2f alt %6.2f roll %5.2f' % (r['t'], r['ForwardSpeedMS'], r['PitchDeg'], r['AltitudeM'], r['RollDeg']))
