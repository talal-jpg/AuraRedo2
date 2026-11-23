"""Galleon control scheme (EAirshipControlScheme::Galleon = 1): a captain's ship you command, not steer every frame.

Spec: Docs/Airship/controls/SCHEME_GALLEON.md. Run:

    python3 metrics.py galleon           -> galleon_metrics.json (M1..M12)
    python3 course.py galleon            -> the gate course, both bots, 0 and 100 ms
    python3 galleon_checks.py            -> the Galleon-only checks (telegraph steps, swing, stations, hold W ...)
    python3 compare.py classic galleon

What it does (all values in the GALLEON preset below, C++ units):
  * W / S step an engine-order telegraph: FULL ASTERN / STOP / SLOW / HALF / FULL. The ship holds the ordered speed
    hands-free (a speed loop in ShapeControls, so every machine's cosmetics follow). Holding W / S auto-steps; STOP is
    a detent that auto-repeat never passes. X brakes while held, then the order resumes.
  * A / D: the helm. The bow answers as quickly as Classic; the weight shows in a 26 deg heel that comes in with the
    turn, 9-12 deg of carry after the release (met firmly), no turn sink (the grip force is applied level), and a
    look-ahead camera that answers on the pilot's screen in 3 frames at any latency.
  * Brake + A / D above 6 m/s: the stern swing. A 54 deg/s yaw kick on reduced grip, the speed bleeds, the stern slides
    out; releasing the brake bites, carves the slide back into forward speed and pays a small surge.
  * Q / E sidle, Shift = full steam (full + boost), Space / Ctrl as Classic with the base fixes (10 / 13 m/s).
  * Broadside stations: when the camera looks past 55 deg off the bow (beam watch) or the pilot aims, the gun deck is
    kept near level (bank x 0.2) and the helm gives fine orders (turn rate x 0.5; the swing keeps full authority).
    Sent as Buttons bit 4.
  * Camera: higher, farther, ship-relative free look; beam watch holds the camera on the broadside; slow majestic
    recentre behind the ship otherwise.
  * Every base fix of ../BASELINE.md section 4f.

The bench (airship_sim.py) has no hook for two base fixes (the fan torque feed-forward inside the pod mixer and the
lift release time constant inside ShapeControls), so this file subclasses FlightModel (GalleonFlightModel: copies of
shape_controls / apply_forces / update_cosmetic with the changes marked "GALLEON" or "BASE FIX") and swaps the class of
the sim's flight models in Scheme.reset. airship_sim.py is not edited.
"""
import math

from airship_sim import (Scheme, Classic, RawInput, PilotInput, Command, Intent, FlightModel, register_scheme,
                         BUTTON_BOOST, BUTTON_BRAKE, BUTTON_AIM, BUTTON_HAS_AIM, clamp, wrap180, lerp, approach,
                         approach_ud, add, sub, mul, dot, cross, norm, size, size2d, clampsize, qrot, qunrot, qmul, qinv,
                         quat2rot, rot2quat, to_axis_angle, solve3, perlin1d, POD_LOCAL, FAN_LOCAL, FRONT_POD, LEFT_POD,
                         TENSOR_ACTOR, D2R, R2D, G, DT)

# FAirshipPilotInput::Buttons bit 4 (new: Airship::Button_Stations). Only read while the ship's scheme is Galleon.
BUTTON_STATIONS = 16

# Engine-order telegraph: index -> (HUD name, order value on the wire / in telemetry)
ORDER_NAMES = {-1: 'FULL ASTERN', 0: 'STOP', 1: 'SLOW', 2: 'HALF', 3: 'FULL'}
ORDER_VALUE = {-1: -1.0, 0: 0.0, 1: 1.0 / 3.0, 2: 2.0 / 3.0, 3: 1.0}
ORDER_MIN, ORDER_MAX, ORDER_STOP = -1, 3, 0


def order_index(v):
    """The wire throttle (-1..1, int8-quantized order value) -> the order notch (every machine decodes it the same)."""
    if v <= -0.5:
        return -1
    return int(round(clamp(v, 0.0, 1.0) * 3.0))


# =====================================================================================================================
# Preset: every tunable the scheme owns (C++ units). New names: the base fixes keep the BASELINE.md names (off in
# Classic), Galleon-only tunables start with "Galleon". The Classic value of each new one is in CLASSIC_NEW (= off).
# =====================================================================================================================
CLASSIC_NEW = dict(
    # base fixes (BASELINE.md 4f), v1 = off
    bFanTorqueFeedForward=False, VertBrakeAccel=0.0, HoldBrakeAccel=0.0, LiftTauRelease=0.0, bBrakeHoldLead=False,
    BrakeFadeSpeed=0.0, StationKeepGain=0.0, StationKeepSpeed=300.0, StationKeepAccelMax=150.0,
    # shared new tunables (any scheme may use them; v1 values = off): the grip / sidle force along the level right
    # axis; a cap on the air brake's deceleration; "meet her" (a faster helm return and a firmer yaw loop while a turn
    # is being taken off); the yaw loop gain / cap while drifting; the wheel / rudder swing while drifting (cosmetic)
    bLevelGripForce=False, BrakeMaxAccel=0.0, SteerTauRelease=0.0, KrSteady=0.0, AlphaYawMaxSteady=0.0, DriftKr=0.0,
    DriftAlphaYawMax=0.0, DriftCosmeticSteerScale=1.0,
    # Galleon (only read while the scheme is Galleon)
    GalleonOrderSlowSpeed=1400.0, GalleonOrderHalfSpeed=2800.0, GalleonOrderAsternSpeed=1200.0,
    GalleonOrderSpeedGain=0.001, GalleonOrderReverseAccel=800.0, GalleonStationsBankScale=0.2,
    GalleonStationsHelmScale=0.5, GalleonOrderPulse=0.35, GalleonOrderPulseTime=0.45,
)

GALLEON_FLIGHT = dict(
    # ---- base fixes (BASELINE.md 4a-4d) ----
    bFanTorqueFeedForward=True,
    PitchPerG=4.0, PitchMinDeg=-4.0, PitchMaxDeg=3.0, BoostPitchDeg=1.5,
    VertBrakeAccel=784.0, HoldBrakeAccel=1470.0, LiftTauRelease=0.08,
    ClimbRate=1000.0, DescendRate=1300.0,
    bBrakeHoldLead=True, BrakeFadeSpeed=1000.0,
    StationKeepGain=1.0, StationKeepSpeed=300.0, StationKeepAccelMax=150.0,
    # ---- helm: readable momentum, strong bank ----
    SteerTau=0.15, Kr=3.0, AlphaYawMax=1.0,
    SteerTauRelease=0.12, KrSteady=4.0, AlphaYawMaxSteady=1.2,
    YawRateAtRest=26.0, YawRateAtMid=44.0, YawRateMidSpeed=1500.0, YawRateAtTop=34.0, YawRateTopSpeed=4800.0,
    YawRateBoost=24.0,
    BankMaxDeg=26.0, BankMaxBoostDeg=18.0, BankFullSpeed=2400.0, BankMinFraction=0.25, StrafeBankDeg=3.0,
    KpRoll=18.0, KdRoll=5.4, GyroTiltMax=1.5,
    bLevelGripForce=True,
    # ---- sidle ----
    StrafeSpeed=1000.0, StrafeTau=0.25,
    # ---- full steam ----
    BoostKickDV=550.0, BoostDrainRate=22.0,
    # ---- telegraph speed loop, brake ----
    ThrottleTauUp=0.15, ThrottleTauDown=0.25,
    GalleonOrderSlowSpeed=1400.0, GalleonOrderHalfSpeed=2800.0, GalleonOrderAsternSpeed=1200.0,
    GalleonOrderSpeedGain=0.001,
    GalleonOrderReverseAccel=800.0, BrakeMaxAccel=1400.0,
    # ---- stern swing (= the Classic drift path with Galleon values, plus its own yaw loop gain / cap) ----
    DriftSteerThreshold=0.3, DriftMinSpeed=600.0, YawRateDrift=54.0, DriftKr=4.0,
    DriftAlphaYawMax=1.5, DriftKlat=1.6, DriftALatMaxG=1.6, DriftEta=0.15,
    DriftBrakeScale=0.3, BankMaxDriftDeg=28.0, DriftBoostMinTime=0.6, DriftBoostDV=250.0,
    # ---- broadside stations, cosmetics ----
    GalleonStationsBankScale=0.2, GalleonStationsHelmScale=0.5, GalleonOrderPulse=0.35, GalleonOrderPulseTime=0.45,
    DriftCosmeticSteerScale=1.3,
)

GALLEON_PAWN = dict(
    # camera: higher, farther, slower, majestic (the Galleon* camera tunables are new pawn properties)
    CameraArmLength=8000.0, CameraArmMin=5000.0, CameraArmMax=14000.0, CameraBoostArmExtra=1400.0,
    CameraTargetOffsetZ=1200.0, CameraRotationLagSpeed=6.0, CameraLagSpeed=3.5,
    BaseFOV=80.0, SpeedFOVExtra=10.0, BoostFOVExtra=14.0, AimFOVOffset=-18.0,
    CameraPitchMin=-65.0, CameraPitchMax=20.0, CameraDefaultPitch=-16.0,
    RecenterDelay=2.0, RecenterMinSpeed=800.0, RecenterSpeed=1.2,
    GalleonBeamWatchEnterDeg=55.0, GalleonBeamWatchExitDeg=40.0, GalleonLookAheadDeg=10.0, GalleonLookAheadTau=0.12,
    GalleonCameraRollPerBankDeg=0.25, GalleonCameraRollMaxDeg=6.0,
    # telegraph keys
    GalleonOrderRepeatDelay=0.25, GalleonOrderRepeatInterval=0.15, GalleonOrderAxisPress=0.5, GalleonOrderAxisRelease=0.3,
    # REVIEW: beam watch gives broadside stations only within this long (s) of an own broadside (0 = always, as designed)
    GalleonStationsFireHoldTime=6.0,
)


# =====================================================================================================================
# Flight model: the server's forces and every machine's shaping / cosmetics under Galleon
# =====================================================================================================================
class GalleonFlightModel(FlightModel):
    """FlightModel with the base fixes and the Galleon modes. Only the lines marked GALLEON / BASE FIX differ from
    airship_sim.FlightModel (= the C++ at 8f01bca)."""

    def _galleon_init(self):
        self.b_stations = False
        self.b_swing = False
        self.order = 0
        self.order_pulse = 0.0
        self.boost_pulse = 0.0
        self.prev_boost_btn = False
        self.swing_exit = 0.0

    # ---- GALLEON: the telegraph speed loop (ShapeControls, every machine) ------------------------------------------
    def hold_throttle(self, v):
        """Throttle that balances the drag at forward speed v (cm/s), forward or astern."""
        P = self.P
        drag = P['DragC1'] * v + P['DragC2'] * v * abs(v)
        if v >= 0:
            fade = max(1e-3, 1.0 - (v / max(P['VTop'], 1.0)) ** P['ThrustFadeExponent'])
            return clamp(drag / (P['AFan'] * fade), 0.0, 1.0)
        fade = max(1e-3, 1.0 - (-v / max(P['VTopRev'], 1.0)) ** 2)
        return clamp(drag / (P['AFanRev'] * fade), -1.0, 0.0)

    def order_throttle(self, notch, vf):
        P = self.P
        if notch >= ORDER_MAX:
            return 1.0                                   # FULL: everything she has (open loop, as Classic W)
        vord = {-1: -P['GalleonOrderAsternSpeed'], 0: 0.0, 1: P['GalleonOrderSlowSpeed'], 2: P['GalleonOrderHalfSpeed']}[notch]
        return clamp(self.hold_throttle(vord) + P['GalleonOrderSpeedGain'] * (vord - vf), -1.0, 1.0)

    def shape_controls(self, controls, dt, fwd_speed):
        if not hasattr(self, 'b_swing'):
            self._galleon_init()
        P = self.P
        raw_steer = controls.get_steer()
        brake = controls.has(BUTTON_BRAKE)
        self.b_aiming = controls.has(BUTTON_AIM)
        self.b_stations = controls.has(BUTTON_STATIONS)                                  # GALLEON
        swing = brake and abs(raw_steer) > P['DriftSteerThreshold'] and fwd_speed > P['DriftMinSpeed']
        notch = order_index(controls.get_throttle())                                    # GALLEON
        if notch != self.order:
            self.order_pulse = 1.0                                                       # GALLEON: the telegraph "ring"
            self.order = notch
        boost = controls.has(BUTTON_BOOST)
        if boost and not self.prev_boost_btn:
            self.boost_pulse = 1.0
        self.prev_boost_btn = boost
        thr_target = 1.0 if boost else self.order_throttle(notch, fwd_speed)           # GALLEON: full steam = full
        if brake and not swing:
            if P['BrakeFadeSpeed'] > 0:                                                  # BASE FIX 4c
                thr_target = -P['BrakeReverseThrottle'] * clamp(fwd_speed / P['BrakeFadeSpeed'], 0.0, 1.0)
            else:
                thr_target = -P['BrakeReverseThrottle'] if fwd_speed > 100.0 else 0.0
        self.b_brake, self.b_drifting, self.b_swing = brake, swing, swing
        self.sh_throttle = approach_ud(self.sh_throttle, thr_target, dt, P['ThrottleTauUp'], P['ThrottleTauDown'])
        self.sh_boost = approach(self.sh_boost, 1.0 if boost else 0.0, dt, P['BoostTauUp'] if boost else P['BoostTauDown'])
        lt = controls.get_lift()
        tau = P['LiftTau']
        if P['LiftTauRelease'] > 0 and abs(lt) < abs(self.sh_lift) and lt * self.sh_lift >= 0:   # BASE FIX 4b
            tau = P['LiftTauRelease']
        self.sh_lift = approach(self.sh_lift, lt, dt, tau)
        steer_tau = P['SteerTau']
        if P['SteerTauRelease'] > 0 and abs(raw_steer) < abs(self.sh_steer):                   # NEW: meet her
            steer_tau = P['SteerTauRelease']
        self.sh_steer = approach(self.sh_steer, raw_steer, dt, steer_tau)
        self.sh_strafe = approach(self.sh_strafe, controls.get_strafe(), dt, P['StrafeTau'])
        # cosmetic pulses decay (every machine)
        self.order_pulse = max(0.0, self.order_pulse - dt / max(P['GalleonOrderPulseTime'], 1e-3))
        self.boost_pulse = max(0.0, self.boost_pulse - dt / max(P['GalleonOrderPulseTime'], 1e-3))

    # ---- forces (server) --------------------------------------------------------------------------------------------
    def apply_forces(self, body, dt, now):
        if not hasattr(self, 'b_swing'):
            self._galleon_init()
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
        brake, swing = self.b_brake, self.b_swing

        # ---- commands --------------------------------------------------------------------------------------------
        AFanEff = lerp(P['AFan'], P['AFanBoost'], Boost)
        VTopEff = max(lerp(P['VTop'], P['VTopBoost'], Boost), 1.0)
        if Throttle >= 0:
            AFanCmd = AFanEff * Throttle * max(0.0, 1.0 - (max(Vf, 0.0) / VTopEff) ** P['ThrustFadeExponent'])
        else:
            if brake and not swing:
                ARev = P['AFan']
            elif Vf > 0:
                ARev = P['GalleonOrderReverseAccel']      # GALLEON: the engines back to slow the ship to the order
            else:
                ARev = P['AFanRev']
            AFanCmd = ARev * Throttle * max(0.0, 1.0 - (max(-Vf, 0.0) / max(P['VTopRev'], 1.0)) ** 2)
        ADrag = -(P['DragC1'] * Vf + P['DragC2'] * Vf * abs(Vf))
        ABrake = -P['Kbrake'] * Vf * (P['DriftBrakeScale'] if swing else 1.0) if brake else 0.0   # GALLEON
        if P['BrakeMaxAccel'] > 0:                                                        # GALLEON (shared switch)
            ABrake = clamp(ABrake, -P['BrakeMaxAccel'], P['BrakeMaxAccel'])

        # ---- vertical (BASE FIX 4b / 4c: stopping-distance capture, sqrt hold limiter, brake lead, vertical brake)
        brake_pressed = brake and not self.brake_was
        self.brake_was = brake
        hb = P['HoldBrakeAccel']
        stop_lead = (lambda vz: vz * abs(vz) / (2.0 * hb)) if hb > 0 else (lambda vz: vz * P['HoldCaptureLead'])
        if abs(Lift) >= P['LiftDeadZone']:
            VzCmd = Lift * (P['ClimbRate'] if Lift > 0 else P['DescendRate'])
            self.hold_valid = False
        else:
            if not self.hold_valid:
                self.hold_z = Z + stop_lead(Vz)
                self.hold_valid = True
            if brake_pressed:
                self.hold_z = Z + (stop_lead(Vz) if P['bBrakeHoldLead'] else 0.0)
            e = self.hold_z - Z
            VzCmd = P['Kz'] * e
            if hb > 0:
                VzCmd = math.copysign(min(abs(VzCmd), math.sqrt(2.0 * hb * abs(e))), e)
            VzCmd = clamp(VzCmd, -P['HoldMaxSpeed'], P['HoldMaxSpeed'])
        if P['MinClearance'] > 0 and self.min_ground >= 0:
            VzCmd = max(VzCmd, P['Kfloor'] * (P['MinClearance'] - self.min_ground))
            if P['FloorBrakeAccel'] > 0:
                VzCmd = max(VzCmd, -math.sqrt(2 * P['FloorBrakeAccel'] * max(self.min_ground - P['MinClearance'], 0.0)))
        if P['bUseCeiling']:
            VzCmd = min(VzCmd, P['Kceil'] * (P['CeilingZ'] - Z))

        # ---- GALLEON: bank (strong, swing heel, broadside stations level the gun deck) --------------------------
        BankMax = P['BankMaxDriftDeg'] if swing else lerp(P['BankMaxDeg'], P['BankMaxBoostDeg'], Boost)
        BankDeg = BankMax * Steer * clamp(Vf / max(P['BankFullSpeed'], 1.0), P['BankMinFraction'], 1.0) + P['StrafeBankDeg'] * Strafe
        if self.b_stations:
            BankDeg *= P['GalleonStationsBankScale']

        AbsVf = abs(Vf)
        if AbsVf <= P['YawRateMidSpeed']:
            RmaxDeg = lerp(P['YawRateAtRest'], P['YawRateAtMid'], AbsVf / max(P['YawRateMidSpeed'], 1.0))
        else:
            RmaxDeg = lerp(P['YawRateAtMid'], P['YawRateAtTop'],
                           clamp((AbsVf - P['YawRateMidSpeed']) / max(P['YawRateTopSpeed'] - P['YawRateMidSpeed'], 1.0), 0.0, 1.0))
        RmaxDeg = P['YawRateDrift'] if swing else lerp(RmaxDeg, P['YawRateBoost'], Boost)       # GALLEON
        if self.b_stations and not swing:
            RmaxDeg *= P['GalleonStationsHelmScale']      # GALLEON: gunnery helm (fine orders while on the beam)

        Klat = P['DriftKlat'] if swing else lerp(P['GripKlat'], P['BoostKlat'], Boost)
        ALatMax = (P['DriftALatMaxG'] if swing else lerp(P['GripALatMaxG'], P['BoostALatMaxG'], Boost)) * Gravity
        Eta = P['DriftEta'] if swing else lerp(P['GripEta'], P['BoostEta'], Boost)

        cmd = dict(AFanCmd=AFanCmd, ADrag=ADrag, ABrake=ABrake, VzCmd=VzCmd, BankDeg=BankDeg, RmaxDeg=RmaxDeg,
                   YawRateCmd=Steer * RmaxDeg * D2R, Klat=Klat, ALatMax=ALatMax, Eta=Eta,
                   VlTarget=Strafe * P['StrafeSpeed'], PitchExtraDeg=0.0, Vf=Vf, Vl=Vl, Vz=Vz, Z=Z,
                   Fwd=Fwd, Right=Right, Up=Up, drifting=swing, brake=brake)
        self.scheme.server_commands(sim, self, cmd)
        AFanCmd, ADrag, ABrake, VzCmd = cmd['AFanCmd'], cmd['ADrag'], cmd['ABrake'], cmd['VzCmd']
        BankDeg, YawRateCmd = cmd['BankDeg'], cmd['YawRateCmd']
        Klat, ALatMax, Eta = cmd['Klat'], cmd['ALatMax'], cmd['Eta']
        ACmd = AFanCmd + ADrag + ABrake
        PitchDeg = clamp(-P['PitchPerG'] * ACmd / Gravity, P['PitchMinDeg'], P['PitchMaxDeg']) - P['BoostPitchDeg'] * Boost + \
            P['LiftPitchDeg'] * Lift + cmd['PitchExtraDeg']

        FvWorld = clamp(Mass * (Gravity + P['Kvz'] * (VzCmd - Vz)), P['CollectiveMin'] * W, P['CollectiveMax'] * W)
        FvBody = FvWorld / max(0.5, Up[2])
        AVert = 0.0                                                                       # BASE FIX 4b
        if P['VertBrakeAccel'] > 0 and Vz * (Vz - VzCmd) > 0 and abs(Vz) > abs(VzCmd):
            AVert = -math.copysign(min(P['VertBrakeAccel'], P['Kvz'] * abs(Vz - VzCmd)), Vz)

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
        YawRate = AngVel[2]
        Kr, AYawMax = P['Kr'], P['AlphaYawMax']
        if swing:                                                                         # NEW: drift yaw loop
            Kr = P['DriftKr'] if P['DriftKr'] > 0 else Kr
            AYawMax = P['DriftAlphaYawMax'] if P['DriftAlphaYawMax'] > 0 else AYawMax
        elif P['KrSteady'] > 0 and abs(YawRateCmd) < abs(YawRate) - 1e-3:              # NEW: meet her
            Kr = P['KrSteady']
            AYawMax = max(AYawMax, P['AlphaYawMaxSteady'])
        AlphaZ = clamp(Kr * (YawRateCmd - YawRate) + P['AngularDamping'] * YawRateCmd, -AYawMax, AYawMax)
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
        Col = [A[0][i] * yc[0] + A[1][i] * yc[1] + A[2][i] * yc[2] for i in range(4)] if yc is not None else [FvBody / 4.0] * 4
        Psi = (-P['FanYawMaxDeg'] * Steer) * D2R
        FanDir = (1.0, math.tan(Psi), 0.0)
        FanMaxF = lerp(P['FanMax'], P['FanMaxBoost'], Boost) * W
        TauFan = (0.0, 0.0, 0.0)
        if P['bFanTorqueFeedForward']:                                                    # BASE FIX 4a-2
            TotalEst = clamp(Mass * AFanCmd - sum(Col[i] * PodDir[i][0] for i in range(4)), -2 * FanMaxF, 2 * FanMaxF)
            for j in range(2):
                TauFan = add(TauFan, cross(sub(FAN_LOCAL[j], COMLocal), mul(FanDir, 0.5 * TotalEst)))
        ya = solve3(M, [0.0, TauX - TauFan[0], TauY - TauFan[1]])
        if yc is not None and ya is not None:
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

        # ---- yaw ---------------------------------------------------------------------------------------------------
        Izz = TENSOR_ACTOR[2][2] if self.ctrl_mode == 'hull' else Inertia[2]

        # ---- fans --------------------------------------------------------------------------------------------------
        KL = cross(sub(FAN_LOCAL[0], COMLocal), FanDir)[2]
        KR = cross(sub(FAN_LOCAL[1], COMLocal), FanDir)[2]
        KDiff = 0.5 * (KL - KR)
        Total = clamp(Mass * AFanCmd - PodSum[0], -2 * FanMaxF, 2 * FanMaxF)
        RudCap = min(P['RudderAuthority'] * (Vf / max(P['RudderRefSpeed'], 1.0)) ** 2, P['RudderMaxAlpha']) * abs(Steer)
        RudderAlpha = clamp(AlphaZ - (PodTauZ + 0.5 * Total * (KL + KR)) / Izz, -RudCap, RudCap) if Izz > 1e-4 else 0.0
        TauKnown = PodTauZ + 0.5 * Total * (KL + KR) + Izz * RudderAlpha
        DMax = max(0.0, 2 * FanMaxF - abs(Total))
        D = clamp((TauZ - TauKnown) / KDiff, -DMax, DMax) if abs(KDiff) > 1 else 0.0
        FanF = [0.5 * Total + 0.5 * D, 0.5 * Total - 0.5 * D]
        AlphaGyroZ = clamp((TauZ - TauKnown - KDiff * D) / Izz, -P['GyroYawMax'], P['GyroYawMax']) if Izz > 1e-4 else 0.0

        # ---- lateral grip, sidle, swing ------------------------------------------------------------------------------
        # GALLEON (shared switch bLevelGripForce): the grip / sidle force acts along the level right axis, so in a
        # banked turn none of it pushes the ship down (no turn sink). The loop itself stays in the hull frame.
        GripDir = Right
        if P['bLevelGripForce'] and size2d(Right) > 1e-3:
            GripDir = norm((Right[0], Right[1], 0.0))
        VlLat = Vl
        ALatPhys = (PodSum[1] + (FanF[0] + FanF[1]) * FanDir[1]) / Mass
        ALatCmd = clamp(Klat * (cmd['VlTarget'] - VlLat), -ALatMax, ALatMax)
        AGrip = ALatCmd - ALatPhys
        ARedirect = Eta * abs(AGrip) if (Vf > P['RedirectMinSpeed'] and AGrip * VlLat < 0) else 0.0
        # the drift kick (Classic code; under Galleon it is the swing's exit surge with the preset's DriftBoost* values)
        swing_kick = 0.0
        if swing:
            self.drift_time += dt
        else:
            if self.drift_time >= P['DriftBoostMinTime'] and P['DriftBoostDV'] > 0:
                body.add_impulse_vel(mul(Fwd, P['DriftBoostDV']))
                swing_kick = P['DriftBoostDV']
                self.swing_exit = 1.0
            self.drift_time = 0.0

        # ---- BASE FIX 4d: station keeping (no throttle / sidle / boost at low speed) ------------------------------
        AKeepF = 0.0
        if P['StationKeepGain'] > 0 and abs(Throttle) < 0.05 and abs(Strafe) < 0.05 and Boost < 0.05:
            hs = math.hypot(Vf, Vl)
            fade = clamp(2.0 - hs / max(P['StationKeepSpeed'], 1.0), 0.0, 1.0)
            AKeepF = clamp(-P['StationKeepGain'] * Vf, -P['StationKeepAccelMax'], P['StationKeepAccelMax']) * fade

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
        ACom = add(mul(GripDir, AGrip), add(mul(Right, WindLat), mul(Fwd, ADrag + ABrake + ARedirect + AKeepF)))
        ACom = add(ACom, (0.0, 0.0, AVert))
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
                          YawRateCmd=YawRateCmd, AlphaGyroTilt=AlphaGyroTilt, DriftKick=swing_kick, ARedirect=ARedirect,
                          AVert=AVert, AKeepF=AKeepF, Order=self.order, Swing=swing, Stations=self.b_stations)

    # ---- cosmetics (every machine) ----------------------------------------------------------------------------------
    def update_cosmetic(self, fwd_speed):
        FlightModel.update_cosmetic(self, fwd_speed)
        if not hasattr(self, 'b_swing'):
            self._galleon_init()
        P = self.P
        c = self.cosmetic
        if self.b_swing:
            # GALLEON: the helmsman throws the wheel hard over (wheel / rudder only; FanYawDeg stays = the forces)
            c['Steer'] = clamp(self.sh_steer * P['DriftCosmeticSteerScale'], -1.3, 1.3)
        # GALLEON: the engines answer the telegraph / full steam: a short thrust pulse on the pods (0..1.5)
        pulse = P['GalleonOrderPulse'] * max(self.order_pulse, self.boost_pulse)
        if pulse > 0:
            c['PodThrustAlpha'] = [clamp(a + pulse, 0.0, 1.5) for a in c['PodThrustAlpha']]


# =====================================================================================================================
# The scheme
# =====================================================================================================================
@register_scheme
class Galleon(Classic):
    key = 'galleon'
    enum = 1
    label = 'Galleon'
    flight = dict(CLASSIC_NEW, **GALLEON_FLIGHT)     # every scheme-owned key present (CLASSIC_NEW = the off values)
    pawn = dict(GALLEON_PAWN)
    ctrl_inertia = 'hull'     # BASE FIX 4a-1 (bHullAxisInertia)
    ext_fields = {}           # no new RPC field: the order rides Throttle, stations rides Buttons bit 4

    # course.py galleon --tune, started from the bench defaults (2026-11-23, final preset): its best set is exactly
    # Classic's gains (score 146.9), so both schemes are flown by identically tuned bots. The telegraph / stations /
    # swing handling of a player lives in intent_raw / command_raw below.
    GAINS = dict(Classic.GAINS)

    # ---- runtime state ----------------------------------------------------------------------------------------------
    def reset(self, sim):
        sim.pilot_state = dict(order=ORDER_STOP, up=False, down=False, held_t=0.0, next_rep=0.0, rep_dir=0,
                               cam_off=0.0, beam=False, la=0.0, roll=0.0, stations=False, last_raw_throttle=0.0)
        sim.server_state = {}
        for fm in {id(sim.server): sim.server, id(sim.pilot_fm): sim.pilot_fm}.values():
            fm.__class__ = GalleonFlightModel
            fm._galleon_init()
        # the bench builds the camera before reset: apply the Galleon arm / pitch
        sim.cam.arm = sim.PP['CameraArmLength']
        sim.cam.control_pitch = sim.cam.view_pitch = sim.PP['CameraDefaultPitch']

    # ---- pilot's machine: the telegraph --------------------------------------------------------------------------
    def telegraph(self, sim, raw, dt):
        """W / S (or the stick) -> the order notch. A press steps one notch; holding auto-steps after
        GalleonOrderRepeatDelay every GalleonOrderRepeatInterval; auto-repeat never passes STOP (detent)."""
        st = sim.pilot_state
        PP = sim.PP
        press, rel = PP['GalleonOrderAxisPress'], PP['GalleonOrderAxisRelease']
        v = raw.throttle
        up = v > press or (st['up'] and v > rel)
        down = v < -press or (st['down'] and v < -rel)

        def step(d, repeat):
            o = st['order']
            n = clamp(o + d, ORDER_MIN, ORDER_MAX)
            if repeat and ((o == ORDER_STOP) or (o > ORDER_STOP > n) or (o < ORDER_STOP < n)):
                return          # detent: auto-repeat stops at STOP; a fresh press passes it
            st['order'] = int(n)

        now = sim.time
        for flag, d in (('up', 1), ('down', -1)):
            held = up if d > 0 else down
            if held and not st[flag]:
                step(d, False)
                st['held_t'] = 0.0
                st['next_rep'] = now + PP['GalleonOrderRepeatDelay']
                st['rep_dir'] = d
            elif held and st['rep_dir'] == d:
                st['held_t'] += dt
                if now >= st['next_rep'] - 1e-6:
                    step(d, True)
                    st['next_rep'] = now + PP['GalleonOrderRepeatInterval']
            st[flag] = held
        if not up and not down:
            st['rep_dir'] = 0
        return st['order']

    def pilot_input(self, sim, raw, cam, view, dt):
        st = sim.pilot_state
        order = self.telegraph(sim, raw, dt)
        p = PilotInput()
        p.set_axes(ORDER_VALUE[order], raw.steer, raw.lift, raw.strafe)
        p.set_button(BUTTON_BOOST, raw.boost)
        p.set_button(BUTTON_BRAKE, raw.brake)
        p.set_button(BUTTON_AIM, raw.aim)
        # REVIEW: beam watch alone no longer changes the handling; it takes stations only while the pilot is fighting
        # (an own broadside within GalleonStationsFireHoldTime s). Aim held = stations at once (an explicit request).
        hold = sim.PP.get('GalleonStationsFireHoldTime', 0.0)
        fired = hold <= 0.0 or (sim.time - max(sim.last_fire_pred.values())) < hold
        st['stations'] = bool((st['beam'] and fired) or raw.aim)
        p.set_button(BUTTON_STATIONS, st['stations'])
        aim = sim.aim_point(cam, view)
        if aim is not None:
            p.aim = aim
            p.set_button(BUTTON_HAS_AIM, True)
        return p

    # ---- pilot's machine: the camera -----------------------------------------------------------------------------
    def camera(self, sim, raw, cam, view, dt):
        """Ship-relative free look. The control yaw = hull yaw + offset + look-ahead. Mouse / harness changes set the
        offset. Beam watch (|offset| > enter) holds the offset; otherwise it eases back to 0 (slow) after RecenterDelay
        without look input, moving, not aiming. Look-ahead: GalleonLookAheadDeg x the pilot's own shaped helm."""
        PP = sim.PP
        st = sim.pilot_state
        now = sim.time
        hull = view['YawDeg']
        if raw.cam_yaw is not None:
            st['cam_off'] = wrap180(raw.cam_yaw - hull - st['la'])
        if raw.cam_pitch is not None:
            cam.control_pitch = raw.cam_pitch
        if raw.look:
            cam.last_look_time = now
        if raw.zoom:
            cam.arm = clamp(cam.arm - raw.zoom * 800.0, PP['CameraArmMin'], PP['CameraArmMax'])
        off = st['cam_off']
        if not st['beam'] and abs(off) > PP['GalleonBeamWatchEnterDeg']:
            st['beam'] = True
        elif st['beam'] and abs(off) < PP['GalleonBeamWatchExitDeg']:
            st['beam'] = False
        fwd = view['ForwardSpeed']
        if (not st['beam'] and not raw.aim and PP['RecenterSpeed'] > 0 and now - cam.last_look_time > PP['RecenterDelay']
                and fwd > PP['RecenterMinSpeed']):
            a = 1.0 - math.exp(-PP['RecenterSpeed'] * dt)
            st['cam_off'] += (0.0 - st['cam_off']) * a
            cam.control_pitch += (PP['CameraDefaultPitch'] - cam.control_pitch) * a
        la_target = 0.0 if (st['beam'] or raw.aim) else PP['GalleonLookAheadDeg'] * sim.pilot_fm.sh_steer
        st['la'] = approach(st['la'], la_target, dt, PP['GalleonLookAheadTau'])
        cam.control_yaw = wrap180(hull + st['cam_off'] + st['la'])
        cam.control_pitch = clamp(wrap180(cam.control_pitch), PP['CameraPitchMin'], PP['CameraPitchMax'])
        # camera roll with the helm (cosmetic; the bench only records it)
        bank_est = sim.P['BankMaxDeg'] * sim.pilot_fm.sh_steer * (sim.P['GalleonStationsBankScale'] if st['stations'] else 1.0)
        st['roll'] = clamp(PP['GalleonCameraRollPerBankDeg'] * bank_est, -PP['GalleonCameraRollMaxDeg'], PP['GalleonCameraRollMaxDeg'])
        self.camera_lag(sim, cam, dt)
        cam.free_look = True

    # ---- telemetry (contract fields) -----------------------------------------------------------------------------
    def telemetry(self, sim, tele):
        Classic.telemetry(self, sim, tele)
        tele['Scheme'] = self.enum
        fm = sim.server
        tele['ThrottleOrder'] = ORDER_VALUE.get(getattr(fm, 'order', 0), 0.0)
        tele['bFreeLook'] = True
        tele['GalleonOrderName'] = ORDER_NAMES.get(getattr(fm, 'order', 0), 'STOP')
        tele['bSwing'] = getattr(fm, 'b_swing', False)
        tele['bStations'] = getattr(fm, 'b_stations', False)

    # ---- bench adapters --------------------------------------------------------------------------------------------
    @staticmethod
    def notch_for_thrust(thrust):
        if thrust >= 0.83:
            return 3
        if thrust >= 0.5:
            return 2
        if thrust >= 0.17:
            return 1
        if thrust > -0.5:
            return 0
        return -1

    def tap_toward(self, sim, want):
        """Raw throttle that moves the telegraph one tap toward the wanted notch: 1 frame pressed, 1 frame released."""
        st = sim.pilot_state
        o = st['order']
        if want == o:
            return 0.0
        last = st.get('last_raw_throttle', 0.0)
        d = 1.0 if want > o else -1.0
        if abs(last) > 0.5:          # a release frame between taps (Completed, then a new Started)
            st['last_raw_throttle'] = 0.0
            return 0.0
        st['last_raw_throttle'] = d
        return d

    def command_raw(self, sim, cmd):
        thr = self.tap_toward(sim, self.notch_for_thrust(cmd.thrust))
        r = RawInput(throttle=thr, steer=cmd.steer, lift=cmd.lift, strafe=cmd.strafe, boost=cmd.boost,
                     brake=cmd.brake or cmd.drift, aim=cmd.aim, fire=cmd.fire)
        if cmd.look_yaw is not None:
            r.cam_yaw, r.cam_pitch, r.look = cmd.look_yaw, cmd.look_pitch if cmd.look_pitch is not None else sim.PP['CameraDefaultPitch'], True
        return r

    def intent_raw(self, sim, intent, view, gains=None):
        """Closed-loop goal -> RAW inputs for a decent Galleon player: pick the telegraph notch for the planned speed
        (with hysteresis; brake when much too fast), steer like Classic's adapter, lift like Classic, look at the
        target. Notch changes are taps (the sloppy bot's keyboard model turns them into 0.1 s presses)."""
        g = dict(self.GAINS)
        if gains:
            g.update(gains)
        P = sim.P
        st = sim.pilot_state
        course = view['CourseDeg'] if view['SpeedMS'] > 3.0 else view['YawDeg']
        err = wrap180(intent.course_deg - course)
        rmax = sim.rmax_deg(view['ForwardSpeedMS'] * 100.0)
        rate_des = clamp(g['course'] * err + intent.yaw_rate_ff, -rmax, rmax)
        steer = clamp((rate_des + g['rate_damp'] * (rate_des - view['YawRateDegS'])) / max(rmax, 1.0), -1.0, 1.0)
        vf = view['ForwardSpeedMS']
        brake = False
        # the notch nearest the planned speed (FULL counts as the top speed), with 2 m/s of hysteresis on the current
        # one; the brake covers what the notch leaves. Like a player, the bot rings a notch for the section: it steps
        # down at once, but up only when the higher speed has been wanted for NOTCH_UP_DELAY s.
        cur = st['order']
        top = 0.97 * sim.top_speed_estimate()
        if intent.speed is None:
            want = 3
        else:
            best, want = None, 1
            for n in (1, 2, 3):
                vn = {1: P['GalleonOrderSlowSpeed'] / 100.0, 2: P['GalleonOrderHalfSpeed'] / 100.0, 3: top}[n]
                d = abs(vn - intent.speed) - (2.0 if n == cur else 0.0)
                if best is None or d < best:
                    best, want = d, n
        if want > cur and cur >= 1:
            since = st.setdefault('up_since', sim.time)
            if sim.time - since < self.NOTCH_UP_DELAY:
                want = cur
        else:
            st.pop('up_since', None)
        if intent.speed is not None:
            ev = intent.speed - vf
            if ev < -8.0 or (intent.brake_hint and ev < -2.0):
                brake = True
        thr = self.tap_toward(sim, want)
        lift = 0.0
        if intent.alt is not None:
            ez = intent.alt - view['AltitudeM']
            lift = clamp(g['alt'] * ez - g['vz_damp'] * view['VerticalSpeedMS'], -1.0, 1.0)
            if abs(lift) < P['LiftDeadZone'] * 1.2:
                lift = 0.0
        if brake and vf > P['DriftMinSpeed'] / 100.0:
            # brake + helm is the stern swing (a deliberate move): a player who only wants to slow down lets go of the
            # helm while braking (helm below the keyboard model's 0.15 release level), or skips the brake when the
            # turn needs a lot of helm (the telegraph's reverse thrust slows the ship anyway)
            if abs(steer) > 0.6:
                brake = False
            else:
                steer = clamp(steer, -0.12, 0.12)
        r = RawInput(throttle=thr, steer=steer, lift=lift, brake=brake)
        self.look(sim, r, intent, view)
        return r

    KEY_AXES = ('throttle', 'steer', 'lift', 'strafe')
    NOTCH_UP_DELAY = 1.5      # s the bot waits before ringing a higher notch (bench adapter only)
