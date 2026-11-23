# Port of UAirshipFlightComponent::ApplyForces (+ shaping, gimbals, boost) to a 6-DOF rigid body, UE axes (cm, kg, s).
# Review aid only: checks signs (steer right -> yaw right, bank right), hover, top speed, brake, drift, frame-rate.
import math, sys

D2R = math.pi / 180.0
R2D = 180.0 / math.pi

# ---------------- UE math ----------------
def qmul(a, b):  # Hamilton, (x,y,z,w); a*b = apply b then a
    ax, ay, az, aw = a; bx, by, bz, bw = b
    return (aw*bx + ax*bw + ay*bz - az*by,
            aw*by - ax*bz + ay*bw + az*bx,
            aw*bz + ax*by - ay*bx + az*bw,
            aw*bw - ax*bx - ay*by - az*bz)

def qinv(q): return (-q[0], -q[1], -q[2], q[3])

def qrot(q, v):
    p = (v[0], v[1], v[2], 0.0)
    r = qmul(qmul(q, p), qinv(q))
    return (r[0], r[1], r[2])

def qunrot(q, v): return qrot(qinv(q), v)

def qnorm(q):
    n = math.sqrt(sum(c*c for c in q)); return tuple(c/n for c in q)

def rot2quat(p, y, r):
    sp, cp = math.sin(p*D2R/2), math.cos(p*D2R/2)
    sy, cy = math.sin(y*D2R/2), math.cos(y*D2R/2)
    sr, cr = math.sin(r*D2R/2), math.cos(r*D2R/2)
    return (cr*sp*sy - sr*cp*cy, -cr*sp*cy - sr*cp*sy, cr*cp*sy - sr*sp*cy, cr*cp*cy + sr*sp*sy)

def quat2rot(q):
    X, Y, Z, W = q
    st = Z*X - W*Y
    yy = 2*(W*Z + X*Y); yx = 1 - 2*(Y*Y + Z*Z)
    pitch = math.asin(max(-1, min(1, 2*st))) * R2D
    yaw = math.atan2(yy, yx) * R2D
    roll = math.atan2(-2*(W*X + Y*Z), 1 - 2*(X*X + Y*Y)) * R2D
    return pitch, yaw, roll

def to_axis_angle(q):
    X, Y, Z, W = q
    ang = 2*math.acos(max(-1, min(1, W)))
    s = math.sqrt(max(0.0, 1 - W*W))
    if s < 1e-8: return (1.0, 0.0, 0.0), 0.0
    return (X/s, Y/s, Z/s), ang

def add(a, b): return (a[0]+b[0], a[1]+b[1], a[2]+b[2])
def sub(a, b): return (a[0]-b[0], a[1]-b[1], a[2]-b[2])
def mul(a, s): return (a[0]*s, a[1]*s, a[2]*s)
def dot(a, b): return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]
def cross(a, b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
def size(a): return math.sqrt(dot(a, a))
def norm(a):
    s = size(a); return mul(a, 1/s) if s > 1e-12 else (0.0, 0.0, 0.0)
def clampsize(a, m):
    s = size(a); return mul(a, m/s) if s > m else a
def clamp(x, a, b): return max(a, min(b, x))
def lerp(a, b, t): return a + (b - a) * t

def approach(cur, tgt, dt, tau):
    if tau <= 1e-4: return tgt
    return cur + (tgt - cur) * (1 - math.exp(-dt / tau))
def approach_ud(cur, tgt, dt, up, down):
    return approach(cur, tgt, dt, up if abs(tgt) > abs(cur) else down)

def solve3(M, B):
    C00 = M[1][1]*M[2][2] - M[1][2]*M[2][1]
    C01 = M[1][2]*M[2][0] - M[1][0]*M[2][2]
    C02 = M[1][0]*M[2][1] - M[1][1]*M[2][0]
    det = M[0][0]*C00 + M[0][1]*C01 + M[0][2]*C02
    if abs(det) < 1e-12: return None
    inv = [[C00, M[0][2]*M[2][1]-M[0][1]*M[2][2], M[0][1]*M[1][2]-M[0][2]*M[1][1]],
           [C01, M[0][0]*M[2][2]-M[0][2]*M[2][0], M[0][2]*M[1][0]-M[0][0]*M[1][2]],
           [C02, M[0][1]*M[2][0]-M[0][0]*M[2][1], M[0][0]*M[1][1]-M[0][1]*M[1][0]]]
    return [sum(inv[r][c]*B[c] for c in range(3))/det for r in range(3)]

# ---------------- parameters (header defaults) ----------------
P = dict(
    ThrottleTauUp=0.30, ThrottleTauDown=0.45, BoostTauUp=0.15, BoostTauDown=0.60, LiftTau=0.25, SteerTau=0.15,
    StrafeTau=0.20, PodForceTauUp=0.10, PodForceTauDown=0.15,
    ClimbRate=1200., DescendRate=1500., Kvz=2.0, Kz=0.8, HoldMaxSpeed=800., HoldCaptureLead=0.5, LiftDeadZone=0.05,
    CollectiveMin=0.25, CollectiveMax=1.9,
    KpRoll=6.25, KdRoll=4.5, KpPitch=4.0, KdPitch=3.2, BankMaxDeg=18., BankMaxDriftDeg=22., BankMaxBoostDeg=12.,
    StrafeBankDeg=6., BankFullSpeed=2000., BankMinFraction=0.25, PitchPerG=8., PitchMinDeg=-8., PitchMaxDeg=6.,
    BoostPitchDeg=3., LiftPitchDeg=3., GyroTiltMax=0.8,
    PodForceMin=0.02, PodForceMax=0.55, ThrusterGimbalMaxDeg=5., GimbalPitchPerThrottle=10., GimbalPitchPerBoost=5.,
    GimbalPitchPerBrake=6., GimbalRollPerStrafe=12., GimbalRollPerSteer=5.,
    Kr=3.0, AlphaYawMax=1.0, YawRateAtRest=30., YawRateAtMid=45., YawRateMidSpeed=1500., YawRateAtTop=35.,
    YawRateTopSpeed=4800., YawRateDrift=50., YawRateBoost=25., FanYawMaxDeg=12., RudderAuthority=0.6,
    RudderRefSpeed=4800., RudderMaxAlpha=1.2, GyroYawMax=0.5,
    AFan=1323., VTop=5000., AFanBoost=1960., VTopBoost=9600., AFanRev=490., VTopRev=1800., ThrustFadeExponent=6.,
    DragC1=0.05, DragC2=3e-6, Kbrake=0.9, BrakeReverseThrottle=0.5, FanMax=0.68, FanMaxBoost=1.0,
    HardSpeedCap=11000., HardCapGain=3.,
    StrafeSpeed=1200., GripKlat=4.0, GripALatMaxG=2.5, GripEta=0.35, DriftKlat=1.2, DriftALatMaxG=1.2, DriftEta=0.4,
    BoostKlat=3.0, BoostALatMaxG=2.0, BoostEta=0.3, RedirectMinSpeed=500., DriftSteerThreshold=0.3, DriftMinSpeed=800.,
    DriftBrakeScale=0.3, DriftBoostMinTime=1.2, DriftBoostDV=600.,
    BoostFuelMax=100., BoostDrainRate=25., BoostRegenRate=12., BoostRegenDelay=1., BoostMinFuelToStart=20.,
    BoostKickDV=400., AngularDamping=0.5, MaxAngularVelocityDeg=120.,
    FixRudder=False, FixTilt=False, BoostStartFuelCost=0., BoostKickCooldown=0., BrakeUseAFan=False, DriftKeepThrottle=False, FloorBrakeAccel=0.,
)
PODS = [(383.3, -465.6, -93.4), (383.3, 491.8, -113.0), (-716.7, -513.0, -120.4), (-716.7, 576.8, -123.9)]
FANS = [(-1720.0, -760.0, 140.0), (-1720.0, 760.0, 140.0)]
FRONT = [True, True, False, False]
MASS = 40000.0
INERTIA = (1.73e10, 5.99e10, 6.56e10)
COM_LOCAL = (-170.0, 0.0, 0.0)
G = 980.0

class Ship:
    def __init__(s, p=None):
        s.p = dict(P); s.p.update(p or {})
        s.com = (0.0, 0.0, 100000.0)  # world COM
        s.q = (0.0, 0.0, 0.0, 1.0)
        s.v = (0.0, 0.0, 0.0); s.w = (0.0, 0.0, 0.0)
        s.th = s.bst = s.lift = s.str = s.stf = 0.0
        s.brake = False; s.drift = False
        s.boost_active = False; s.fuel = 100.0; s.regen = 0.0; s.drift_time = 0.0
        s.hold_valid = False; s.brake_was = False; s.holdz = 0.0
        s.pod_init = False; s.podF = [0.0]*4
        s.impulse_v = (0.0, 0.0, 0.0)
        s.log = {}
        s.t = 0.0; s.last_kick = -1000.0

    def actor_loc(s): return sub(s.com, qrot(s.q, COM_LOCAL))

    def gimbals(s):
        p = s.p; mx = max(p['ThrusterGimbalMaxDeg'], 0)
        pitch = p['GimbalPitchPerThrottle']*s.th + p['GimbalPitchPerBoost']*s.bst - (p['GimbalPitchPerBrake'] if s.brake else 0)
        out = []
        for i in range(4):
            roll = p['GimbalRollPerStrafe']*s.stf + p['GimbalRollPerSteer']*s.str*(1 if FRONT[i] else -1)
            P_ = clamp(pitch, -mx, mx); R_ = clamp(roll, -mx, mx)
            t = math.hypot(P_, R_)
            if t > mx and t > 1e-6: P_ *= mx/t; R_ *= mx/t
            out.append((P_, R_))
        return out

    def step(s, ctl, dt):
        p = s.p
        fwd = qrot(s.q, (1, 0, 0))
        vf_now = dot(s.v, fwd)
        # boost server
        want = ctl.get('boost', False)
        if want and not s.boost_active and s.fuel >= p['BoostMinFuelToStart']:
            s.boost_active = True
            s.fuel = max(0, s.fuel - p['BoostStartFuelCost'])
            if s.t - s.last_kick >= p['BoostKickCooldown']:
                s.v = add(s.v, mul(fwd, p['BoostKickDV'])); s.last_kick = s.t
        if not want or s.fuel <= 0: s.boost_active = False
        if s.boost_active: s.fuel = max(0, s.fuel - p['BoostDrainRate']*dt); s.regen = 0
        else:
            s.regen += dt
            if s.regen >= p['BoostRegenDelay']: s.fuel = min(p['BoostFuelMax'], s.fuel + p['BoostRegenRate']*dt)
        boost_btn = s.boost_active
        # shaping
        raw_steer = ctl.get('steer', 0.0)
        s.brake = ctl.get('brake', False)
        s.drift = s.brake and abs(raw_steer) > p['DriftSteerThreshold'] and vf_now > p['DriftMinSpeed']
        tt = ctl.get('thr', 0.0)
        if s.brake and not (s.drift and p['DriftKeepThrottle']): tt = (-p['BrakeReverseThrottle'] if (not s.drift and vf_now > 100) else 0.0)
        s.th = approach_ud(s.th, tt, dt, p['ThrottleTauUp'], p['ThrottleTauDown'])
        s.bst = approach(s.bst, 1.0 if boost_btn else 0.0, dt, p['BoostTauUp'] if boost_btn else p['BoostTauDown'])
        s.lift = approach(s.lift, ctl.get('lift', 0.0), dt, p['LiftTau'])
        s.str = approach(s.str, raw_steer, dt, p['SteerTau'])
        s.stf = approach(s.stf, ctl.get('strafe', 0.0), dt, p['StrafeTau'])
        F, Tq = s.forces(dt)
        s.t += dt
        # integrate (semi-implicit, Chaos-like)
        a = add(mul(F, 1/MASS), (0, 0, -G))
        s.v = add(s.v, mul(a, dt))
        # world inverse inertia
        tb = qunrot(s.q, Tq)
        ab = (tb[0]/INERTIA[0], tb[1]/INERTIA[1], tb[2]/INERTIA[2])
        s.w = add(s.w, mul(qrot(s.q, ab), dt))
        s.w = mul(s.w, max(0, 1 - p['AngularDamping']*dt))
        s.w = clampsize(s.w, p['MaxAngularVelocityDeg']*D2R)
        s.com = add(s.com, mul(s.v, dt))
        wq = (s.w[0], s.w[1], s.w[2], 0.0)
        dq = qmul(wq, s.q)
        s.q = qnorm(tuple(s.q[i] + 0.5*dt*dq[i] for i in range(4)))

    def forces(s, dt):
        p = s.p
        q = s.q
        Fwd = qrot(q, (1, 0, 0)); Right = qrot(q, (0, 1, 0)); Up = qrot(q, (0, 0, 1))
        m = MASS; g = G; W = m*g
        V = s.v; AngVel = s.w; AngTilt = (s.w[0], s.w[1], 0.0) if p['FixTilt'] else s.w
        Vb = qunrot(q, V); Vf, Vl, Vz = Vb[0], Vb[1], V[2]
        Z = s.actor_loc()[2]
        I = INERTIA
        Boost, Steer, Strafe, Lift, Throttle = s.bst, s.str, s.stf, s.lift, s.th
        AFanEff = lerp(p['AFan'], p['AFanBoost'], Boost); VTopEff = max(lerp(p['VTop'], p['VTopBoost'], Boost), 1)
        if Throttle >= 0: AFanCmd = AFanEff*Throttle*max(0, 1 - (max(Vf, 0)/VTopEff)**p['ThrustFadeExponent'])
        else: AFanCmd = (p['AFan'] if (s.brake and p['BrakeUseAFan']) else p['AFanRev'])*Throttle*max(0, 1 - (max(-Vf, 0)/max(p['VTopRev'], 1))**2)
        ADrag = -(p['DragC1']*Vf + p['DragC2']*Vf*abs(Vf))
        ABrake = -p['Kbrake']*Vf*(p['DriftBrakeScale'] if s.drift else 1.0) if s.brake else 0.0
        ACmd = AFanCmd + ADrag + ABrake
        # vertical
        pressed = s.brake and not s.brake_was; s.brake_was = s.brake
        if abs(Lift) >= p['LiftDeadZone']:
            VzCmd = Lift*(p['ClimbRate'] if Lift > 0 else p['DescendRate']); s.hold_valid = False
        else:
            if not s.hold_valid: s.holdz = Z + Vz*p['HoldCaptureLead']; s.hold_valid = True
            if pressed: s.holdz = Z
            VzCmd = clamp(p['Kz']*(s.holdz - Z), -p['HoldMaxSpeed'], p['HoldMaxSpeed'])
        FvWorld = clamp(m*(g + p['Kvz']*(VzCmd - Vz)), p['CollectiveMin']*W, p['CollectiveMax']*W)
        FvBody = FvWorld/max(0.5, Up[2])
        # attitude
        BankMax = p['BankMaxDriftDeg'] if s.drift else lerp(p['BankMaxDeg'], p['BankMaxBoostDeg'], Boost)
        BankDeg = BankMax*Steer*clamp(Vf/max(p['BankFullSpeed'], 1), p['BankMinFraction'], 1) + p['StrafeBankDeg']*Strafe
        PitchDeg = clamp(-p['PitchPerG']*ACmd/g, p['PitchMinDeg'], p['PitchMaxDeg']) - p['BoostPitchDeg']*Boost + p['LiftPitchDeg']*Lift
        cur = quat2rot(q)
        qd = rot2quat(PitchDeg, cur[1], BankDeg)
        qe = qmul(qd, qinv(q))
        if qe[3] < 0: qe = tuple(-c for c in qe)
        ax, ang = to_axis_angle(qe)
        Err = mul(ax, ang)
        AlphaTilt = add(mul(Fwd, p['KpRoll']*dot(Err, Fwd) - p['KdRoll']*dot(AngTilt, Fwd)),
                        mul(Right, p['KpPitch']*dot(Err, Right) - p['KdPitch']*dot(AngTilt, Right)))
        ATb = qunrot(q, AlphaTilt)
        TauX = I[0]*ATb[0]; TauY = I[1]*ATb[1]
        gim = s.gimbals()
        PodDir = []; PodArm = []; A = [[0]*4 for _ in range(3)]
        for i in range(4):
            gp, gr = gim[i]
            d = norm((math.tan(gp*D2R), math.tan(gr*D2R), 1.0))
            r = sub(PODS[i], COM_LOCAL)
            tpf = cross(r, d)
            PodDir.append(d); PodArm.append(r)
            A[0][i] = d[2]; A[1][i] = tpf[0]; A[2][i] = tpf[1]
        M = [[sum(A[r][k]*A[c][k] for k in range(4)) for c in range(3)] for r in range(3)]
        yc = solve3(M, [FvBody, 0, 0]); ya = solve3(M, [0, TauX, TauY])
        Col = [sum(A[r][i]*yc[r] for r in range(3)) for i in range(4)]
        Att = [sum(A[r][i]*ya[r] for r in range(3)) for i in range(4)]
        FMin = p['PodForceMin']*W; FMax = max(p['PodForceMax'], p['PodForceMin'])*W
        S = 1.0
        for i in range(4):
            if Att[i] > 1e-6: S = min(S, (FMax - Col[i])/Att[i])
            elif Att[i] < -1e-6: S = min(S, (FMin - Col[i])/Att[i])
        S = clamp(S, 0, 1)
        if not s.pod_init:
            s.podF = [clamp(Col[i], FMin, FMax) for i in range(4)]; s.pod_init = True
        PodSum = (0, 0, 0); PodTauZ = 0.0; PodWorld = []
        for i in range(4):
            tgt = clamp(Col[i] + S*Att[i], FMin, FMax)
            s.podF[i] = approach(s.podF[i], tgt, dt, p['PodForceTauUp'] if tgt > s.podF[i] else p['PodForceTauDown'])
            fb = mul(PodDir[i], s.podF[i])
            PodSum = add(PodSum, fb); PodTauZ += cross(PodArm[i], fb)[2]
            PodWorld.append(qrot(q, fb))
        AlphaGyroTilt = clampsize(mul(AlphaTilt, 1 - S), p['GyroTiltMax'])
        # yaw
        AbsVf = abs(Vf)
        if AbsVf <= p['YawRateMidSpeed']:
            Rmax = lerp(p['YawRateAtRest'], p['YawRateAtMid'], AbsVf/max(p['YawRateMidSpeed'], 1))
        else:
            Rmax = lerp(p['YawRateAtMid'], p['YawRateAtTop'], clamp((AbsVf - p['YawRateMidSpeed'])/max(p['YawRateTopSpeed'] - p['YawRateMidSpeed'], 1), 0, 1))
        Rmax = p['YawRateDrift'] if s.drift else lerp(Rmax, p['YawRateBoost'], Boost)
        YawCmd = Steer*Rmax*D2R
        YawRate = AngVel[2] if p['FixTilt'] else dot(AngVel, Up)
        AlphaZ = clamp(p['Kr']*(YawCmd - YawRate) + p['AngularDamping']*YawCmd, -p['AlphaYawMax'], p['AlphaYawMax'])
        TauZ = I[2]*AlphaZ
        Psi = (-p['FanYawMaxDeg']*Steer)*D2R
        FanDir = (1.0, math.tan(Psi), 0.0)
        KL = cross(sub(FANS[0], COM_LOCAL), FanDir)[2]; KR = cross(sub(FANS[1], COM_LOCAL), FanDir)[2]
        KDiff = 0.5*(KL - KR)
        FanMaxF = lerp(p['FanMax'], p['FanMaxBoost'], Boost)*W
        Total = clamp(m*AFanCmd - PodSum[0], -2*FanMaxF, 2*FanMaxF)
        RudCap = min(p['RudderAuthority']*(Vf/max(p['RudderRefSpeed'], 1))**2, p['RudderMaxAlpha'])
        if p['FixRudder']:
            RudCap *= abs(Steer)
            RudderAlpha = clamp(AlphaZ - (PodTauZ + 0.5*Total*(KL + KR))/I[2], -RudCap, RudCap)
        else:
            RudderAlpha = RudCap*Steer*(1 if Vf >= 0 else -1)
        TauKnown = PodTauZ + 0.5*Total*(KL + KR) + I[2]*RudderAlpha
        DMax = max(0, 2*FanMaxF - abs(Total))
        D = clamp((TauZ - TauKnown)/KDiff, -DMax, DMax) if abs(KDiff) > 1 else 0
        FanF = [0.5*Total + 0.5*D, 0.5*Total - 0.5*D]
        AlphaGyroZ = clamp((TauZ - TauKnown - KDiff*D)/I[2], -p['GyroYawMax'], p['GyroYawMax'])
        # lateral
        Klat = p['DriftKlat'] if s.drift else lerp(p['GripKlat'], p['BoostKlat'], Boost)
        ALatMax = (p['DriftALatMaxG'] if s.drift else lerp(p['GripALatMaxG'], p['BoostALatMaxG'], Boost))*g
        Eta = p['DriftEta'] if s.drift else lerp(p['GripEta'], p['BoostEta'], Boost)
        ALatCmd = clamp(Klat*(Strafe*p['StrafeSpeed'] - Vl), -ALatMax, ALatMax)
        ALatPhys = (PodSum[1] + (FanF[0] + FanF[1])*FanDir[1])/m
        AGrip = ALatCmd - ALatPhys
        ARed = Eta*abs(AGrip) if (Vf > p['RedirectMinSpeed'] and AGrip*Vl < 0) else 0.0
        if s.drift: s.drift_time += dt
        else:
            if s.drift_time >= p['DriftBoostMinTime'] and p['DriftBoostDV'] > 0: s.v = add(s.v, mul(Fwd, p['DriftBoostDV']))
            s.drift_time = 0
        # assemble forces/torques about COM (world)
        Ftot = (0, 0, 0); Ttot = (0, 0, 0)
        BodyRot = lambda v: qrot(q, v)
        for i in range(4):
            Pw = BodyRot(sub(PODS[i], COM_LOCAL))
            Ftot = add(Ftot, PodWorld[i]); Ttot = add(Ttot, cross(Pw, PodWorld[i]))
        for j in range(2):
            fw = BodyRot(mul(FanDir, FanF[j])); Pw = BodyRot(sub(FANS[j], COM_LOCAL))
            Ftot = add(Ftot, fw); Ttot = add(Ttot, cross(Pw, fw))
        ACom = add(mul(Right, AGrip), mul(Fwd, ADrag + ABrake + ARed))
        sp = size(V)
        if sp > p['HardSpeedCap']: ACom = sub(ACom, mul(norm(V), p['HardCapGain']*(sp - p['HardSpeedCap'])))
        Ftot = add(Ftot, mul(ACom, m))
        AlphaCom = add(mul(Up, RudderAlpha + AlphaGyroZ), AlphaGyroTilt)
        # accel change torque: world inertia * alpha
        ab = qunrot(q, AlphaCom)
        Ttot = add(Ttot, qrot(q, (ab[0]*I[0], ab[1]*I[1], ab[2]*I[2])))
        s.log = dict(S=S, D=D, Total=Total, FanF=FanF, podF=list(s.podF), Gyro=AlphaGyroZ, Rud=RudderAlpha,
                     AlphaZ=AlphaZ, BankDeg=BankDeg, PitchDeg=PitchDeg, AGrip=AGrip, FvBody=FvBody, ACmd=ACmd)
        return Ftot, Ttot

    def tele(s):
        fwd = qrot(s.q, (1, 0, 0)); up = qrot(s.q, (0, 0, 1))
        vb = qunrot(s.q, s.v)
        pit, yaw, roll = quat2rot(s.q)
        return dict(speed=size(s.v)/100, vf=vb[0]/100, vl=vb[1]/100, vz=s.v[2]/100, z=s.actor_loc()[2]/100,
                    yawrate=dot(s.w, up)*R2D, roll=roll, pitch=pit, yaw=yaw, fuel=s.fuel)

def run(script, dt, T, ship=None, every=1.0, label=""):
    s = ship or Ship()
    t = 0.0; nxt = 0.0; rows = []
    while t < T - 1e-9:
        ctl = script(t, s)
        s.step(ctl, dt); t += dt
        if t + 1e-9 >= nxt:
            rows.append((round(t, 2), s.tele(), dict(s.log))); nxt += every
    return s, rows

def show(rows, keys=('speed', 'vf', 'vl', 'vz', 'z', 'yawrate', 'roll', 'pitch', 'yaw')):
    for t, te, lg in rows:
        print(f"  t={t:5.2f} " + " ".join(f"{k}={te[k]:7.2f}" for k in keys) + f"  S={lg.get('S',0):.2f} gyroZ={lg.get('Gyro',0):+.2f} D/W={lg.get('D',0)/(MASS*G):+.2f}")

if __name__ == '__main__':
    for dt in (1/30, 1/60, 1/120):
        print(f"=== dt={dt:.4f}")
        # hover
        s, rows = run(lambda t, s: {}, dt, 10, every=5)
        te = rows[-1][1]; print(f" hover 10s: z drift {te['z']-1000-1.7*0:.3f} m vz {te['vz']:.3f} roll {te['roll']:.2f} pitch {te['pitch']:.2f}")
        # full throttle 30 s
        s, rows = run(lambda t, s: {'thr': 1.0}, dt, 30, every=1)
        vss = rows[-1][1]['vf']
        t80 = next(t for t, te, lg in rows if te['vf'] >= 0.8*vss)
        print(f" throttle: top {vss:.1f} m/s, 0->80% ~{t80:.0f}s, pitch at 2s {rows[1][1]['pitch']:.1f}, at 30s {rows[-1][1]['pitch']:.1f}, z {rows[-1][1]['z']-1000:.2f}")
        # brake from top
        def brake_script(t, s):
            return {'thr': 1.0} if t < 30 else {'brake': True}
        s, rows = run(brake_script, dt, 40, every=0.25)
        t_stop = next((t for t, te, lg in rows if t > 30 and te['vf'] <= 1.0), None)
        print(f" brake from {vss:.1f}: vf<1 m/s after {t_stop-30 if t_stop else None} s")
        # turn right at top speed
        def turn(t, s):
            return {'thr': 1.0} if t < 30 else {'thr': 1.0, 'steer': 1.0}
        s, rows = run(turn, dt, 38, every=1)
        print(" full steer right at top speed:")
        show([r for r in rows if r[0] in (31, 32, 34, 38)])
        # pivot at rest
        s, rows = run(lambda t, s: {'steer': 1.0}, dt, 5, every=1)
        print(" pivot right at rest:"); show(rows)
        # drift
        def drift(t, s):
            return {'thr': 1.0} if t < 30 else {'thr': 1.0, 'steer': 1.0, 'brake': True}
        s, rows = run(drift, dt, 34, every=1)
        print(" drift (brake+steer, throttle held) from top:"); show([r for r in rows if r[0] >= 30])
        # strafe right
        s, rows = run(lambda t, s: {'strafe': 1.0}, dt, 4, every=1)
        print(" strafe right at rest:"); show(rows)
