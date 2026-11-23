# Python 6-DOF port of the CURRENT airship flight model (UAirshipFlightComponent at commit e4c98b7 / 8f01bca:
# UpdateFlight -> UpdateBoostServer -> ShapeControls -> ApplyForces), for the control-scheme work in
# Docs/Airship/controls/. UE axes and units (cm, kg, s; X forward, Y right, Z up). Replaces
# Docs/Airship/sims/fix_flight/sim_fixed.py for new work (that one predates fix rounds 1-3).
#
# Not modelled: the wind (Perlin), the hull collision / impact cap, the CMC forces of deck passengers, the cannon recoil,
# physics replication. Ground: optional flat plane (floor, descent limiter, cushion). Inertia and centre of mass are
# NOT logged in PIE yet; the default is INERTIA_UCX (below). v1 as PIE runs it: Ship(code_inertia=INERTIA_UCX_CHAOS).
#
# Base-fix switches (all off = v1, see BASELINE.md section 4): bFanTorqueFeedForward, bBrakeHoldLead, HoldBrakeAccel,
# LiftTauRelease, BrakeFadeSpeed, StationKeepGain, VertBrakeAccel.
#
# Run: python3 baseline_checks.py (one process, < 10 s).
import math

D2R = math.pi / 180.0
R2D = 180.0 / math.pi


# ---------------------------------------------------------------------------------------------------- UE math
def qmul(a, b):  # (x, y, z, w); a * b = apply b, then a
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz)


def qinv(q): return (-q[0], -q[1], -q[2], q[3])


def qrot(q, v):
    r = qmul(qmul(q, (v[0], v[1], v[2], 0.0)), qinv(q))
    return (r[0], r[1], r[2])


def qunrot(q, v): return qrot(qinv(q), v)


def qnorm(q):
    n = math.sqrt(sum(c * c for c in q))
    return tuple(c / n for c in q)


def rot2quat(p, y, r):  # FRotator(Pitch, Yaw, Roll).Quaternion()
    sp, cp = math.sin(p * D2R / 2), math.cos(p * D2R / 2)
    sy, cy = math.sin(y * D2R / 2), math.cos(y * D2R / 2)
    sr, cr = math.sin(r * D2R / 2), math.cos(r * D2R / 2)
    return (cr * sp * sy - sr * cp * cy, -cr * sp * cy - sr * cp * sy, cr * cp * sy - sr * sp * cy, cr * cp * cy + sr * sp * sy)


def quat2rot(q):  # FQuat::Rotator() -> (pitch, yaw, roll)
    X, Y, Z, W = q
    st = Z * X - W * Y
    pitch = math.asin(max(-1.0, min(1.0, 2 * st))) * R2D
    yaw = math.atan2(2 * (W * Z + X * Y), 1 - 2 * (Y * Y + Z * Z)) * R2D
    roll = math.atan2(-2 * (W * X + Y * Z), 1 - 2 * (X * X + Y * Y)) * R2D
    return pitch, yaw, roll


def to_axis_angle(q):
    X, Y, Z, W = q
    ang = 2 * math.acos(max(-1.0, min(1.0, W)))
    s = math.sqrt(max(0.0, 1 - W * W))
    if s < 1e-8:
        return (1.0, 0.0, 0.0), 0.0
    return (X / s, Y / s, Z / s), ang


def add(a, b): return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
def sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def mul(a, s): return (a[0] * s, a[1] * s, a[2] * s)
def dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
def size(a): return math.sqrt(dot(a, a))


def norm(a):
    s = size(a)
    return mul(a, 1.0 / s) if s > 1e-12 else (0.0, 0.0, 0.0)


def clampsize(a, m):
    s = size(a)
    return mul(a, m / s) if s > m else a


def clamp(x, a, b): return max(a, min(b, x))
def lerp(a, b, t): return a + (b - a) * t
def sign(x): return 1.0 if x > 0 else (-1.0 if x < 0 else 0.0)


def approach(cur, tgt, dt, tau):
    if tau <= 1e-4:
        return tgt
    return cur + (tgt - cur) * (1 - math.exp(-dt / tau))


def approach_ud(cur, tgt, dt, up, down):
    return approach(cur, tgt, dt, up if abs(tgt) > abs(cur) else down)


def solve3(M, B):
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


def q8(x):  # FAirshipPilotInput::QuantizeAxis + AxisToFloat
    return clamp(round(clamp(x, -1.0, 1.0) * 127.0) / 127.0, -1.0, 1.0)


# ---------------------------------------------------------------------------------------------------- parameters
# UAirshipFlightComponent defaults (AirshipFlightComponent.h); BP_AirshipPawn overrides none of them.
V1 = dict(
    ThrottleTauUp=0.30, ThrottleTauDown=0.45, BoostTauUp=0.15, BoostTauDown=0.60, LiftTau=0.25, SteerTau=0.15,
    StrafeTau=0.20, PodForceTauUp=0.10, PodForceTauDown=0.15,
    ClimbRate=1200., DescendRate=1500., Kvz=2.0, Kz=0.8, HoldMaxSpeed=800., HoldCaptureLead=0.5, LiftDeadZone=0.05,
    CollectiveMin=0.25, CollectiveMax=1.9, MinClearance=400., Kfloor=1.5, FloorBrakeAccel=588.,
    KpRoll=6.25, KdRoll=4.5, KpPitch=4.0, KdPitch=3.2, BankMaxDeg=18., BankMaxDriftDeg=22., BankMaxBoostDeg=12.,
    StrafeBankDeg=6., BankFullSpeed=2000., BankMinFraction=0.25, PitchPerG=8., PitchMinDeg=-8., PitchMaxDeg=6.,
    BoostPitchDeg=3., LiftPitchDeg=3., GyroTiltMax=0.8,
    PodForceMin=0.02, PodForceMax=0.55, ThrusterGimbalMaxDeg=5., GimbalPitchPerThrottle=10., GimbalPitchPerBoost=5.,
    GimbalPitchPerBrake=6., GimbalRollPerStrafe=12., GimbalRollPerSteer=5., GroundEffectStrength=0.35,
    GroundTraceLength=1500.,
    Kr=3.0, AlphaYawMax=1.0, YawRateAtRest=30., YawRateAtMid=45., YawRateMidSpeed=1500., YawRateAtTop=35.,
    YawRateTopSpeed=4800., YawRateDrift=50., YawRateBoost=25., FanYawMaxDeg=12., RudderAuthority=0.6,
    RudderRefSpeed=4800., RudderMaxAlpha=1.2, GyroYawMax=0.5,
    AFan=1323., VTop=5000., AFanBoost=1960., VTopBoost=9600., AFanRev=490., VTopRev=1800., ThrustFadeExponent=6.,
    DragC1=0.05, DragC2=3e-6, Kbrake=0.9, BrakeReverseThrottle=0.5, FanMax=0.68, FanMaxBoost=1.0,
    HardSpeedCap=11000., HardCapGain=3.,
    StrafeSpeed=1200., GripKlat=4.0, GripALatMaxG=2.5, GripEta=0.35, DriftKlat=1.2, DriftALatMaxG=1.2, DriftEta=0.4,
    BoostKlat=3.0, BoostALatMaxG=2.0, BoostEta=0.3, RedirectMinSpeed=500., DriftSteerThreshold=0.3, DriftMinSpeed=800.,
    DriftBrakeScale=0.0, DriftBoostMinTime=1.2, DriftBoostDV=600.,
    BoostFuelMax=100., BoostDrainRate=25., BoostRegenRate=12., BoostRegenDelay=1., BoostMinFuelToStart=20.,
    BoostStartFuelCost=10., BoostKickDV=400., BoostKickCooldown=1.5,
    AngularDamping=0.5, MaxAngularVelocityDeg=120.,
    # ---- base-fix switches (0 / False = v1 behaviour) ----
    # (bHullAxisInertia, 4a fix 1, is the Ship's code_inertia argument: None = fixed, (Izz, Ixx, Iyy) = v1 in Chaos order)
    bFanTorqueFeedForward=False,  # feed the fans' pitch/roll torque into the pod mixer (4a fix 2)
    bBrakeHoldLead=False,         # a brake press in hold mode latches Z + lead, not Z (4c)
    HoldBrakeAccel=0.0,           # >0: hold speed limited to sqrt(2 a |e|), capture lead = stopping distance (4b)
    LiftTauRelease=0.0,           # >0: lift filter time constant toward 0 (release) (4b)
    BrakeFadeSpeed=0.0,           # >0: reverse-fan brake throttle fades to 0 below this forward speed (cm/s) (4c)
    StationKeepGain=0.0,          # >0: low-speed forward velocity hold (1/s) with no throttle / strafe / boost (4d)
    StationKeepSpeed=300.,        # cm/s: full hold below this, fades out to 0 at 2x
    StationKeepAccelMax=150.,     # cm/s^2 cap
    VertBrakeAccel=0.0,           # >0: extra COM vertical decel (cm/s^2) while vz runs past the command (4b)
)

PODS = [(383.3, -465.6, -93.4), (383.3, 491.8, -113.0), (-716.7, -513.0, -120.4), (-716.7, 576.8, -123.9)]
FANS = [(-1720.0, -760.0, 140.0), (-1720.0, 760.0, 140.0)]
FRONT = [True, True, False, False]
NOZZLE_DEPTH = 470.0
MASS = 40000.0
INERTIA_BOX = (1.73e10, 5.99e10, 6.56e10)  # research_flight 3.10 estimate, kg cm^2 (NOT measured)
# The hull body as Chaos builds it from SM_Airship's 8 UCX convexes (40 t, COM nudged to (-170, 0, 0)), copied from
# hull_mass.json (mass_props.py in this folder, an offline port of Chaos MassProperties.cpp + BodyUtils.cpp, 2026-11-23):
# the diagonal of the hull-axis tensor (its product Ixz -7.72e9 is ignored here) and what GetInertiaTensor() returns
# (Chaos principal order: largest, smallest, middle). Not yet logged in PIE.
INERTIA_UCX = (1.20536e10, 6.57469e10, 6.75284e10)
INERTIA_UCX_CHAOS = (6.85863e10, 1.09982e10, 6.57443e10)
COM_LOCAL = (-170.0, 0.0, 0.0)            # DesiredCenterOfMass
G = 980.0


class Ship(object):
    def __init__(s, params=None, inertia=INERTIA_UCX, com=COM_LOCAL, z0=10000.0, ground_z=None, dt=1.0 / 30.0,
                 code_inertia=None):
        s.p = dict(V1)
        s.p.update(params or {})
        s.I = inertia                       # the body's real moments about hull X, Y, Z (integration, accel-change torques)
        s.Ic = code_inertia or inertia      # what ApplyForces multiplies its torque requests by (Body->GetInertiaTensor())
        s.comL = com
        s.ground_z = ground_z
        s.dt = dt
        s.q = (0.0, 0.0, 0.0, 1.0)
        s.com = add((0.0, 0.0, z0), qrot(s.q, s.comL))  # world COM; actor origin at z0
        s.v = (0.0, 0.0, 0.0)
        s.w = (0.0, 0.0, 0.0)
        s.th = s.bst = s.lift = s.str = s.stf = 0.0
        s.brake = s.drift = s.boost_active = False
        s.fuel = s.p['BoostFuelMax']
        s.regen = s.drift_time = 0.0
        s.last_kick = -1000.0
        s.hold_valid = s.brake_was = False
        s.holdz = 0.0
        s.pod_init = False
        s.podF = [0.0] * 4
        s.gd = [-1.0] * 4
        s.mingd = -1.0
        s.t = 0.0
        s.log = {}

    def actor_loc(s):
        return sub(s.com, qrot(s.q, s.comL))

    # ---- UpdateBoostServer
    def boost_server(s, want, dt):
        p = s.p
        if want and not s.boost_active and s.fuel >= p['BoostMinFuelToStart']:
            s.boost_active = True
            s.fuel = max(0.0, s.fuel - p['BoostStartFuelCost'])
            if p['BoostKickDV'] > 0 and s.t - s.last_kick >= p['BoostKickCooldown']:
                s.v = add(s.v, mul(qrot(s.q, (1, 0, 0)), p['BoostKickDV']))
                s.last_kick = s.t
        if not want or s.fuel <= 0:
            s.boost_active = False
        if s.boost_active:
            s.fuel = max(0.0, s.fuel - p['BoostDrainRate'] * dt)
            s.regen = 0.0
        else:
            s.regen += dt
            if s.regen >= p['BoostRegenDelay']:
                s.fuel = min(p['BoostFuelMax'], s.fuel + p['BoostRegenRate'] * dt)
        return s.boost_active

    # ---- ShapeControls
    def shape(s, c, dt, vf):
        p = s.p
        raw_steer = q8(c.get('steer', 0.0))
        s.brake = bool(c.get('brake', False))
        s.drift = s.brake and abs(raw_steer) > p['DriftSteerThreshold'] and vf > p['DriftMinSpeed']
        tt = q8(c.get('thr', 0.0))
        if s.brake and not s.drift:
            if p['BrakeFadeSpeed'] > 0:
                tt = -p['BrakeReverseThrottle'] * clamp(vf / p['BrakeFadeSpeed'], 0.0, 1.0)
            else:
                tt = -p['BrakeReverseThrottle'] if vf > 100.0 else 0.0
        s.th = approach_ud(s.th, tt, dt, p['ThrottleTauUp'], p['ThrottleTauDown'])
        b = 1.0 if c.get('boost_gated', False) else 0.0
        s.bst = approach(s.bst, b, dt, p['BoostTauUp'] if b > 0 else p['BoostTauDown'])
        lt = q8(c.get('lift', 0.0))
        tau = p['LiftTau']
        if p['LiftTauRelease'] > 0 and abs(lt) < abs(s.lift) and lt * s.lift >= 0:
            tau = p['LiftTauRelease']
        s.lift = approach(s.lift, lt, dt, tau)
        s.str = approach(s.str, raw_steer, dt, p['SteerTau'])
        s.stf = approach(s.stf, q8(c.get('strafe', 0.0)), dt, p['StrafeTau'])
        s.raw = c

    def gimbals(s):
        p = s.p
        mx = max(p['ThrusterGimbalMaxDeg'], 0.0)
        pitch = p['GimbalPitchPerThrottle'] * s.th + p['GimbalPitchPerBoost'] * s.bst - (p['GimbalPitchPerBrake'] if s.brake else 0.0)
        out = []
        for i in range(4):
            roll = p['GimbalRollPerStrafe'] * s.stf + p['GimbalRollPerSteer'] * s.str * (1 if FRONT[i] else -1)
            P_ = clamp(pitch, -mx, mx)
            R_ = clamp(roll, -mx, mx)
            t = math.hypot(P_, R_)
            if t > mx and t > 1e-6:
                P_ *= mx / t
                R_ *= mx / t
            out.append((P_, R_))
        return out

    def trace_ground(s):
        s.mingd = -1.0
        for i in range(4):
            if s.ground_z is None:
                s.gd[i] = -1.0
                continue
            pz = add(s.actor_loc(), qrot(s.q, PODS[i]))[2]
            dist = pz - s.ground_z
            ok = 0 <= dist <= s.p['GroundTraceLength'] + NOZZLE_DEPTH
            s.gd[i] = max(0.0, dist - NOZZLE_DEPTH) if ok else -1.0
            if s.gd[i] >= 0 and (s.mingd < 0 or s.gd[i] < s.mingd):
                s.mingd = s.gd[i]

    # ---- one game frame: UpdateFlight on the server + one physics step
    def step(s, c):
        dt = s.dt
        p = s.p
        fwd = qrot(s.q, (1, 0, 0))
        vf_now = dot(s.v, fwd)
        c = dict(c)
        c['boost_gated'] = s.boost_server(bool(c.get('boost', False)), dt)
        s.shape(c, dt, vf_now)
        s.trace_ground()
        F, Tq = s.forces(dt)
        s.t += dt
        a = add(mul(F, 1.0 / MASS), (0.0, 0.0, -G))
        s.v = add(s.v, mul(a, dt))
        tb = qunrot(s.q, Tq)
        ab = (tb[0] / s.I[0], tb[1] / s.I[1], tb[2] / s.I[2])
        s.w = add(s.w, mul(qrot(s.q, ab), dt))
        s.w = mul(s.w, max(0.0, 1 - p['AngularDamping'] * dt))
        s.w = clampsize(s.w, p['MaxAngularVelocityDeg'] * D2R)
        s.com = add(s.com, mul(s.v, dt))
        dq = qmul((s.w[0], s.w[1], s.w[2], 0.0), s.q)
        s.q = qnorm(tuple(s.q[i] + 0.5 * dt * dq[i] for i in range(4)))

    # ---- ApplyForces (returns world force and torque about the COM)
    def forces(s, dt):
        p = s.p
        q = s.q
        Fwd, Right, Up = qrot(q, (1, 0, 0)), qrot(q, (0, 1, 0)), qrot(q, (0, 0, 1))
        m, g = MASS, G
        W = m * g
        V, AngVel = s.v, s.w
        Vb = qunrot(q, V)
        Vf, Vl, Vz = Vb[0], Vb[1], V[2]
        Z = s.actor_loc()[2]
        I = s.Ic
        Boost, Steer, Strafe, Lift, Throttle = s.bst, s.str, s.stf, s.lift, s.th
        drift, brake = s.drift, s.brake

        # forward command
        AFanEff = lerp(p['AFan'], p['AFanBoost'], Boost)
        VTopEff = max(lerp(p['VTop'], p['VTopBoost'], Boost), 1.0)
        if Throttle >= 0:
            AFanCmd = AFanEff * Throttle * max(0.0, 1 - (max(Vf, 0.0) / VTopEff) ** p['ThrustFadeExponent'])
        else:
            ARev = p['AFan'] if (brake and not drift) else p['AFanRev']
            AFanCmd = ARev * Throttle * max(0.0, 1 - (max(-Vf, 0.0) / max(p['VTopRev'], 1.0)) ** 2)
        ADrag = -(p['DragC1'] * Vf + p['DragC2'] * Vf * abs(Vf))
        ABrake = -p['Kbrake'] * Vf * (p['DriftBrakeScale'] if drift else 1.0) if brake else 0.0
        ACmd = AFanCmd + ADrag + ABrake

        # vertical
        pressed = brake and not s.brake_was
        s.brake_was = brake
        stop_lead = lambda vz: (vz * abs(vz) / (2 * p['HoldBrakeAccel'])) if p['HoldBrakeAccel'] > 0 else vz * p['HoldCaptureLead']
        if abs(Lift) >= p['LiftDeadZone']:
            VzCmd = Lift * (p['ClimbRate'] if Lift > 0 else p['DescendRate'])
            s.hold_valid = False
        else:
            if not s.hold_valid:
                s.holdz = Z + stop_lead(Vz)
                s.hold_valid = True
            if pressed:
                s.holdz = Z + (stop_lead(Vz) if p['bBrakeHoldLead'] else 0.0)
            e = s.holdz - Z
            VzCmd = p['Kz'] * e
            if p['HoldBrakeAccel'] > 0:
                VzCmd = sign(e) * min(abs(VzCmd), math.sqrt(2 * p['HoldBrakeAccel'] * abs(e)))
            VzCmd = clamp(VzCmd, -p['HoldMaxSpeed'], p['HoldMaxSpeed'])
        if p['MinClearance'] > 0 and s.mingd >= 0:
            VzCmd = max(VzCmd, p['Kfloor'] * (p['MinClearance'] - s.mingd))
            if p['FloorBrakeAccel'] > 0:
                VzCmd = max(VzCmd, -math.sqrt(2 * p['FloorBrakeAccel'] * max(s.mingd - p['MinClearance'], 0.0)))
        FvWorld = clamp(m * (g + p['Kvz'] * (VzCmd - Vz)), p['CollectiveMin'] * W, p['CollectiveMax'] * W)
        FvBody = FvWorld / max(0.5, Up[2])
        AVert = 0.0
        if p['VertBrakeAccel'] > 0 and Vz * (Vz - VzCmd) > 0 and abs(Vz) > abs(VzCmd):
            AVert = -sign(Vz) * min(p['VertBrakeAccel'], p['Kvz'] * abs(Vz - VzCmd))

        # attitude
        BankMax = p['BankMaxDriftDeg'] if drift else lerp(p['BankMaxDeg'], p['BankMaxBoostDeg'], Boost)
        BankDeg = BankMax * Steer * clamp(Vf / max(p['BankFullSpeed'], 1.0), p['BankMinFraction'], 1.0) + p['StrafeBankDeg'] * Strafe
        PitchDeg = clamp(-p['PitchPerG'] * ACmd / g, p['PitchMinDeg'], p['PitchMaxDeg']) - p['BoostPitchDeg'] * Boost + p['LiftPitchDeg'] * Lift
        cur = quat2rot(q)
        qe = qmul(rot2quat(PitchDeg, cur[1], BankDeg), qinv(q))
        if qe[3] < 0:
            qe = tuple(-c for c in qe)
        ax, ang = to_axis_angle(qe)
        Err = mul(ax, ang)
        Tilt = (AngVel[0], AngVel[1], 0.0)
        AlphaTilt = add(mul(Fwd, p['KpRoll'] * dot(Err, Fwd) - p['KdRoll'] * dot(Tilt, Fwd)),
                        mul(Right, p['KpPitch'] * dot(Err, Right) - p['KdPitch'] * dot(Tilt, Right)))
        ATb = qunrot(q, AlphaTilt)
        TauX, TauY = I[0] * ATb[0], I[1] * ATb[1]

        # thruster mixing
        gim = s.gimbals()
        PodDir, PodArm = [], []
        A = [[0.0] * 4 for _ in range(3)]
        for i in range(4):
            gp, gr = gim[i]
            d = norm((math.tan(gp * D2R), math.tan(gr * D2R), 1.0))
            r = sub(PODS[i], s.comL)
            tpf = cross(r, d)
            PodDir.append(d)
            PodArm.append(r)
            A[0][i], A[1][i], A[2][i] = d[2], tpf[0], tpf[1]
        M = [[sum(A[r][k] * A[c][k] for k in range(4)) for c in range(3)] for r in range(3)]
        yc = solve3(M, [FvBody, 0.0, 0.0])
        Col = [sum(A[r][i] * yc[r] for r in range(3)) for i in range(4)]
        Psi = (-p['FanYawMaxDeg'] * Steer) * D2R
        FanDir = (1.0, math.tan(Psi), 0.0)
        FanMaxF = lerp(p['FanMax'], p['FanMaxBoost'], Boost) * W
        TauFan = (0.0, 0.0, 0.0)
        if p['bFanTorqueFeedForward']:
            # base fix 4a: the fans' share of the forward demand (from the collective), its pitch / roll torque at the
            # fan points goes into the pods' attitude request (the yaw differential D adds none)
            TotalEst = clamp(m * AFanCmd - sum(Col[i] * PodDir[i][0] for i in range(4)), -2 * FanMaxF, 2 * FanMaxF)
            for j in range(2):
                TauFan = add(TauFan, cross(sub(FANS[j], s.comL), mul(FanDir, 0.5 * TotalEst)))
        ya = solve3(M, [0.0, TauX - TauFan[0], TauY - TauFan[1]])
        Att = [sum(A[r][i] * ya[r] for r in range(3)) for i in range(4)]
        FMin = p['PodForceMin'] * W
        FMax = max(p['PodForceMax'], p['PodForceMin']) * W
        S = 1.0
        for i in range(4):
            if Att[i] > 1e-6:
                S = min(S, (FMax - Col[i]) / Att[i])
            elif Att[i] < -1e-6:
                S = min(S, (FMin - Col[i]) / Att[i])
        S = clamp(S, 0.0, 1.0)
        if not s.pod_init:
            s.podF = [clamp(Col[i], FMin, FMax) for i in range(4)]
            s.pod_init = True
        PodSum, PodTauZ, PodWorld = (0.0, 0.0, 0.0), 0.0, []
        for i in range(4):
            tgt = clamp(Col[i] + S * Att[i], FMin, FMax)
            s.podF[i] = approach(s.podF[i], tgt, dt, p['PodForceTauUp'] if tgt > s.podF[i] else p['PodForceTauDown'])
            cushion = 0.0
            if p['GroundEffectStrength'] > 0 and 0 <= s.gd[i] < p['GroundTraceLength']:
                cushion = 0.25 * W * p['GroundEffectStrength'] * (1 - s.gd[i] / max(p['GroundTraceLength'], 1.0)) ** 2
            fb = mul(PodDir[i], s.podF[i] + cushion)
            PodSum = add(PodSum, fb)
            PodTauZ += cross(PodArm[i], fb)[2]
            PodWorld.append(qrot(q, fb))
        AlphaGyroTilt = clampsize(mul(AlphaTilt, 1 - S), p['GyroTiltMax'])

        # yaw
        AbsVf = abs(Vf)
        if AbsVf <= p['YawRateMidSpeed']:
            Rmax = lerp(p['YawRateAtRest'], p['YawRateAtMid'], AbsVf / max(p['YawRateMidSpeed'], 1.0))
        else:
            Rmax = lerp(p['YawRateAtMid'], p['YawRateAtTop'], clamp((AbsVf - p['YawRateMidSpeed']) / max(p['YawRateTopSpeed'] - p['YawRateMidSpeed'], 1.0), 0.0, 1.0))
        Rmax = p['YawRateDrift'] if drift else lerp(Rmax, p['YawRateBoost'], Boost)
        YawCmd = Steer * Rmax * D2R
        AlphaZ = clamp(p['Kr'] * (YawCmd - AngVel[2]) + p['AngularDamping'] * YawCmd, -p['AlphaYawMax'], p['AlphaYawMax'])
        TauZ = I[2] * AlphaZ
        KL = cross(sub(FANS[0], s.comL), FanDir)[2]
        KR = cross(sub(FANS[1], s.comL), FanDir)[2]
        KDiff = 0.5 * (KL - KR)
        Total = clamp(m * AFanCmd - PodSum[0], -2 * FanMaxF, 2 * FanMaxF)
        RudCap = min(p['RudderAuthority'] * (Vf / max(p['RudderRefSpeed'], 1.0)) ** 2, p['RudderMaxAlpha']) * abs(Steer)
        RudderAlpha = clamp(AlphaZ - (PodTauZ + 0.5 * Total * (KL + KR)) / I[2], -RudCap, RudCap)
        TauKnown = PodTauZ + 0.5 * Total * (KL + KR) + I[2] * RudderAlpha
        DMax = max(0.0, 2 * FanMaxF - abs(Total))
        D = clamp((TauZ - TauKnown) / KDiff, -DMax, DMax) if abs(KDiff) > 1 else 0.0
        FanF = [0.5 * Total + 0.5 * D, 0.5 * Total - 0.5 * D]
        AlphaGyroZ = clamp((TauZ - TauKnown - KDiff * D) / I[2], -p['GyroYawMax'], p['GyroYawMax'])

        # lateral
        Klat = p['DriftKlat'] if drift else lerp(p['GripKlat'], p['BoostKlat'], Boost)
        ALatMax = (p['DriftALatMaxG'] if drift else lerp(p['GripALatMaxG'], p['BoostALatMaxG'], Boost)) * g
        Eta = p['DriftEta'] if drift else lerp(p['GripEta'], p['BoostEta'], Boost)
        ALatCmd = clamp(Klat * (Strafe * p['StrafeSpeed'] - Vl), -ALatMax, ALatMax)
        ALatPhys = (PodSum[1] + (FanF[0] + FanF[1]) * FanDir[1]) / m
        AGrip = ALatCmd - ALatPhys
        ARed = Eta * abs(AGrip) if (Vf > p['RedirectMinSpeed'] and AGrip * Vl < 0) else 0.0
        if drift:
            s.drift_time += dt
        else:
            if s.drift_time >= p['DriftBoostMinTime'] and p['DriftBoostDV'] > 0:
                s.v = add(s.v, mul(Fwd, p['DriftBoostDV']))
            s.drift_time = 0.0

        # base fix 4d: low-speed station keeping (no throttle, no strafe, no boost)
        AKeepF = AKeepL = 0.0
        if p['StationKeepGain'] > 0 and abs(Throttle) < 0.05 and abs(Strafe) < 0.05 and Boost < 0.05:
            hs = math.hypot(Vf, Vl)
            fade = clamp(2.0 - hs / max(p['StationKeepSpeed'], 1.0), 0.0, 1.0)
            AKeepF = clamp(-p['StationKeepGain'] * Vf, -p['StationKeepAccelMax'], p['StationKeepAccelMax']) * fade

        # assemble (forces at points -> force + torque about the COM)
        Ftot, Ttot = (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
        for i in range(4):
            Ftot = add(Ftot, PodWorld[i])
            Ttot = add(Ttot, cross(qrot(q, PodArm[i]), PodWorld[i]))
        for j in range(2):
            fw = qrot(q, mul(FanDir, FanF[j]))
            Ftot = add(Ftot, fw)
            Ttot = add(Ttot, cross(qrot(q, sub(FANS[j], s.comL)), fw))
        ACom = add(mul(Right, AGrip + AKeepL), mul(Fwd, ADrag + ABrake + ARed + AKeepF))
        ACom = add(ACom, (0.0, 0.0, AVert))
        sp = size(V)
        if sp > p['HardSpeedCap']:
            ACom = sub(ACom, mul(norm(V), p['HardCapGain'] * (sp - p['HardSpeedCap'])))
        Ftot = add(Ftot, mul(ACom, m))
        AlphaCom = add(mul(Up, RudderAlpha + AlphaGyroZ), AlphaGyroTilt)
        ab = qunrot(q, AlphaCom)
        Ir = s.I  # bAccelChange: Chaos multiplies by the body's real world inertia
        Ttot = add(Ttot, qrot(q, (ab[0] * Ir[0], ab[1] * Ir[1], ab[2] * Ir[2])))
        s.log = dict(S=S, Total=Total, PitchDeg=PitchDeg, BankDeg=BankDeg, ACmd=ACmd, AFanCmd=AFanCmd, VzCmd=VzCmd,
                     FvWorld=FvWorld / W, TauFanY=TauFan[1], D=D, gyroZ=AlphaGyroZ, rud=RudderAlpha)
        return Ftot, Ttot

    def tele(s):
        vb = qunrot(s.q, s.v)
        pit, yaw, roll = quat2rot(s.q)
        return dict(t=s.t, speed=size(s.v) / 100, vf=vb[0] / 100, vl=vb[1] / 100, vz=s.v[2] / 100,
                    z=s.actor_loc()[2] / 100, x=s.actor_loc()[0] / 100, y=s.actor_loc()[1] / 100,
                    yawrate=s.w[2] * R2D, roll=roll, pitch=pit, yaw=yaw, fuel=s.fuel, hold=s.holdz / 100)


def run(script, T, ship=None, **kw):
    """script(t, ship) -> controls dict (thr, steer, lift, strafe, boost, brake). Returns the ship and per-frame rows."""
    s = ship or Ship(**kw)
    rows = []
    n = int(round(T / s.dt))
    for _ in range(n):
        s.step(script(s.t, s))
        te = s.tele()
        te.update(s.log)
        rows.append(te)
    return s, rows


def at(rows, t):
    """The row closest to time t."""
    return min(rows, key=lambda r: abs(r['t'] - t))
