"""Point & Fly (EAirshipControlScheme::PointFly = 3): camera-directed flying, a bench plug-in (README.md "Adding a
scheme"). Spec: Docs/Airship/controls/SCHEME_POINTFLY.md.

    The ship turns toward where the camera looks. Mouse / right stick move the camera, and the camera's yaw is the
    heading target. W/S drive, A/D sidestep, Space/Ctrl climb and sink, Q/E (D-pad) turn the heading target with keys.
    Hold Aim (RMB / LB): broadside mode. The camera is free and the ship keeps its heading; when the aim is off the
    guns' arc and not coming into it, the gun lock swings the ship to keep the broadside on it. Release: the camera
    eases back onto the heading.

Where it runs (as in the C++ spec):
  * pilot's machine (camera() + pilot_input()): camera -> heading target (free look, Q/E, gun lock, lead clamp);
    the local copy of the heading loop drives the Steer axis = the pilot's own wheel / fans / bank cosmetics.
  * wire: FAirshipPilotInput.HeadingTarget (uint16, 0.0055 deg, 0 = no target). A/D go on the Strafe axis, so every
    existing cosmetic and force path keeps working.
  * server (server_controls()): the same heading loop on the authoritative hull writes Controls.Steer before RepInput,
    so the server's forces and every observer's cosmetics use the server's steer. The loop is closed only on the server.

Hooks the bench lacks: the base fixes of BASELINE.md section 4 (fan torque feed-forward, hold brake / vertical brake,
release lift tau, brake-hold lead, brake fade, station keeping) live inside ShapeControls / ApplyForces, so this module
subclasses FlightModel (PFFlightModel: a copy of airship_sim.FlightModel.shape_controls / apply_forces plus exactly
the baseline_sim.py fix definitions) and swaps it in from reset(). With every fix switch off it is the bench's
FlightModel line for line (self-test: python3 scheme_pointfly.py --selftest).

Run:
    python3 metrics.py pointfly          -> pointfly_metrics.json (M1..M12)
    python3 course.py pointfly           -> gate course, both bots, 0 / 100 ms
    python3 pointfly_checks.py           -> the Point & Fly checks of SCHEME_POINTFLY.md 9.1 (heading steps, sweeps,
                                            reversals, broadside pass / charge, human-like mouse, keys, pitch climb)
    python3 scheme_pointfly.py --selftest -> PFFlightModel with the fixes off == the bench
"""
import math
import sys

import airship_sim as A
from airship_sim import (Scheme, Classic, RawInput, PilotInput, Command, Intent, register_scheme, quantize_ext,
                         ext_to_float, quantize_axis, BUTTON_BOOST, BUTTON_BRAKE, BUTTON_AIM, BUTTON_HAS_AIM, clamp,
                         wrap180, lerp, approach, approach_ud, add, sub, mul, dot, cross, norm, size, clampsize, qrot,
                         qunrot, qmul, qinv, rot2quat, quat2rot, to_axis_angle, solve3, perlin1d, D2R, R2D, DT)

HEADING_SPEC = (16, 360.0 / 65534.0, False)   # FAirshipPilotInput.HeadingTarget: uint16, 0 = no target

# Follow-up F-B (2026-11-23, = the C++): once parked, the parked free look holds at any speed until a drive / sidestep /
# turn / boost key, Aim, or an outside set of the camera above PFParkSpeed; entering still needs |forward speed| <
# PFParkSpeed with no such key. False = the polish build, where a push past PFParkSpeed (a hit) ended it and the ship
# turned to the camera (bench-only switch for pointfly_checks.py 'push'; the C++ has no tunable for it).
PARK_LATCH = True


def encode_heading(yaw_deg):
    """World yaw (deg) -> HeadingTarget: 1..65534 (0.0055 deg steps); 0 is reserved for 'no target', so the
    neutral FAirshipPilotInput() (all zero: timeout, possession change, DebugSetInput) never means 'head north'."""
    return 1 + int(round((yaw_deg % 360.0) / 360.0 * 65534.0)) % 65534


def decode_heading(v):
    """HeadingTarget -> world yaw (deg, -180..180), or None for 0."""
    return None if not v else wrap180((v - 1) * 360.0 / 65534.0)


# =====================================================================================================================
# The base fixes (BASELINE.md section 4) as a FlightModel subclass. Definitions copied from baseline_sim.py.
# =====================================================================================================================
class PFFlightModel(A.FlightModel):
    """airship_sim.FlightModel + the base-fix switches (names as in BASELINE.md 4f; all off = the bench's v1 port)."""

    def shape_controls(self, controls, dt, fwd_speed):
        P = self.P
        raw_steer = controls.get_steer()
        self.b_brake = controls.has(BUTTON_BRAKE)
        self.b_aiming = controls.has(BUTTON_AIM)
        self.b_drifting = self.b_brake and abs(raw_steer) > P['DriftSteerThreshold'] and fwd_speed > P['DriftMinSpeed']
        thr_target = controls.get_throttle()
        if self.b_brake and not self.b_drifting:
            if P.get('BrakeFadeSpeed', 0.0) > 0:                                   # 4c-2
                thr_target = -P['BrakeReverseThrottle'] * clamp(fwd_speed / P['BrakeFadeSpeed'], 0.0, 1.0)
            else:
                thr_target = -P['BrakeReverseThrottle'] if fwd_speed > 100.0 else 0.0
        boost = controls.has(BUTTON_BOOST)
        targets = dict(throttle=thr_target, boost=1.0 if boost else 0.0, lift=controls.get_lift(), steer=raw_steer,
                       strafe=controls.get_strafe(), brake=self.b_brake, drifting=self.b_drifting)
        self.scheme.shaping_targets(self.sim, self, controls, targets, fwd_speed)
        self.b_brake, self.b_drifting = targets['brake'], targets['drifting']
        self.sh_throttle = approach_ud(self.sh_throttle, targets['throttle'], dt, P['ThrottleTauUp'], P['ThrottleTauDown'])
        self.sh_boost = approach(self.sh_boost, targets['boost'], dt, P['BoostTauUp'] if targets['boost'] > 0.5 else P['BoostTauDown'])
        lt = targets['lift']
        tau = P['LiftTau']
        if P.get('LiftTauRelease', 0.0) > 0 and abs(lt) < abs(self.sh_lift) and lt * self.sh_lift >= 0:   # 4b-3
            tau = P['LiftTauRelease']
        self.sh_lift = approach(self.sh_lift, lt, dt, tau)
        self.sh_steer = approach(self.sh_steer, targets['steer'], dt, P['SteerTau'])
        self.sh_strafe = approach(self.sh_strafe, targets['strafe'], dt, P['StrafeTau'])

    def apply_forces(self, body, dt, now):
        P = self.P
        sim = self.sim
        q = body.q
        Fwd = qrot(q, (1.0, 0.0, 0.0))
        Right = qrot(q, (0.0, 1.0, 0.0))
        Up = qrot(q, (0.0, 0.0, 1.0))
        Mass = body.mass
        Gravity = A.G
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

        AFanEff = lerp(P['AFan'], P['AFanBoost'], Boost)
        VTopEff = max(lerp(P['VTop'], P['VTopBoost'], Boost), 1.0)
        if Throttle >= 0:
            AFanCmd = AFanEff * Throttle * max(0.0, 1.0 - (max(Vf, 0.0) / VTopEff) ** P['ThrustFadeExponent'])
        else:
            ARev = P['AFan'] if (brake and not drifting) else P['AFanRev']
            AFanCmd = ARev * Throttle * max(0.0, 1.0 - (max(-Vf, 0.0) / max(P['VTopRev'], 1.0)) ** 2)
        ADrag = -(P['DragC1'] * Vf + P['DragC2'] * Vf * abs(Vf))
        ABrake = -P['Kbrake'] * Vf * (P['DriftBrakeScale'] if drifting else 1.0) if brake else 0.0

        # ---- vertical (4b-2 HoldBrakeAccel, 4c-1 bBrakeHoldLead) --------------------------------------------------
        brake_pressed = brake and not self.brake_was
        self.brake_was = brake
        hba = P.get('HoldBrakeAccel', 0.0)

        def stop_lead(vz):
            return vz * abs(vz) / (2.0 * hba) if hba > 0 else vz * P['HoldCaptureLead']
        if abs(Lift) >= P['LiftDeadZone']:
            VzCmd = Lift * (P['ClimbRate'] if Lift > 0 else P['DescendRate'])
            self.hold_valid = False
        else:
            if not self.hold_valid:
                self.hold_z = Z + stop_lead(Vz)
                self.hold_valid = True
            if brake_pressed:
                self.hold_z = Z + (stop_lead(Vz) if P.get('bBrakeHoldLead', False) else 0.0)
            e = self.hold_z - Z
            VzCmd = P['Kz'] * e
            if hba > 0:
                VzCmd = math.copysign(min(abs(VzCmd), math.sqrt(2.0 * hba * abs(e))), e)
            VzCmd = clamp(VzCmd, -P['HoldMaxSpeed'], P['HoldMaxSpeed'])
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

        # Point & Fly: PFTurnLiftComp feeds the last frame's vertical part of the lateral grip (the banked hull's grip
        # points partly down in a turn: the 5 m turn sink, README Finding 3) into the collective
        ATurnZ = P.get('PFTurnLiftComp', 0.0) * getattr(self, 'pf_grip_z', 0.0)
        FvWorld = clamp(Mass * (Gravity + P['Kvz'] * (VzCmd - Vz) - ATurnZ), P['CollectiveMin'] * W, P['CollectiveMax'] * W)
        FvBody = FvWorld / max(0.5, Up[2])
        # 4b-1: hidden vertical brake while vz runs past the command in its own direction
        AVert = 0.0
        vba = P.get('VertBrakeAccel', 0.0)
        if vba > 0 and Vz * (Vz - VzCmd) > 0 and abs(Vz) > abs(VzCmd):
            AVert = -math.copysign(min(vba, P['Kvz'] * abs(Vz - VzCmd)), Vz)

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
        # Yaw loop gain / cap: the drift's own, or "meet her" while a turn is being taken off (the shared C++ branch,
        # AirshipFlightComponent.cpp ApplyForces; Galleon's bench port in scheme_galleon.py). 0 = Kr / AlphaYawMax.
        KrEff, AYawCap = P['Kr'], P['AlphaYawMax']
        if drifting:
            KrEff = P.get('DriftKr', 0.0) if P.get('DriftKr', 0.0) > 0 else KrEff
            AYawCap = P.get('DriftAlphaYawMax', 0.0) if P.get('DriftAlphaYawMax', 0.0) > 0 else AYawCap
        elif P.get('KrSteady', 0.0) > 0 and abs(YawRateCmd) < abs(YawRate) - 1e-3:
            KrEff = P['KrSteady']
            AYawCap = max(AYawCap, P.get('AlphaYawMaxSteady', 0.0))
        AlphaZ = clamp(KrEff * (YawRateCmd - YawRate) + P['AngularDamping'] * YawRateCmd, -AYawCap, AYawCap)
        if self.ctrl_mode == 'hull':
            T = A.TENSOR_ACTOR
            TauX = T[0][0] * ATb[0] + T[0][1] * ATb[1] + T[0][2] * AlphaZ
            TauY = T[1][0] * ATb[0] + T[1][1] * ATb[1] + T[1][2] * AlphaZ
            TauZ = T[2][0] * ATb[0] + T[2][1] * ATb[1] + T[2][2] * AlphaZ
        else:
            TauX = Inertia[0] * ATb[0]
            TauY = Inertia[1] * ATb[1]
            TauZ = Inertia[2] * AlphaZ

        gim = self.compute_gimbals()
        PodDir, PodArm = [], []
        Am = [[0.0] * 4 for _ in range(3)]
        for i in range(4):
            gp, gr = gim[i]
            d = norm((math.tan(gp * D2R), math.tan(gr * D2R), 1.0))
            r = sub(A.POD_LOCAL[i], COMLocal)
            tpf = cross(r, d)
            PodDir.append(d)
            PodArm.append(r)
            Am[0][i], Am[1][i], Am[2][i] = d[2], tpf[0], tpf[1]
        M = [[sum(Am[r][k] * Am[c][k] for k in range(4)) for c in range(3)] for r in range(3)]
        yc = solve3(M, [FvBody, 0.0, 0.0])
        # fan geometry (needed by 4a-2 before the attitude solve; the same values as the fan block below)
        Psi = (-P['FanYawMaxDeg'] * Steer) * D2R
        FanDir = (1.0, math.tan(Psi), 0.0)
        FanMaxF = lerp(P['FanMax'], P['FanMaxBoost'], Boost) * W
        TauFan = (0.0, 0.0, 0.0)
        if P.get('bFanTorqueFeedForward', False) and yc is not None:      # 4a-2
            Col0 = [Am[0][i] * yc[0] + Am[1][i] * yc[1] + Am[2][i] * yc[2] for i in range(4)]
            TotalEst = clamp(Mass * AFanCmd - sum(Col0[i] * PodDir[i][0] for i in range(4)), -2 * FanMaxF, 2 * FanMaxF)
            for j in range(2):
                TauFan = add(TauFan, cross(sub(A.FAN_LOCAL[j], COMLocal), mul(FanDir, 0.5 * TotalEst)))
        ya = solve3(M, [0.0, TauX - TauFan[0], TauY - TauFan[1]])
        if yc is not None and ya is not None:
            Col = [Am[0][i] * yc[0] + Am[1][i] * yc[1] + Am[2][i] * yc[2] for i in range(4)]
            Att = [Am[0][i] * ya[0] + Am[1][i] * ya[1] + Am[2][i] * ya[2] for i in range(4)]
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

        Izz = A.TENSOR_ACTOR[2][2] if self.ctrl_mode == 'hull' else Inertia[2]
        KL = cross(sub(A.FAN_LOCAL[0], COMLocal), FanDir)[2]
        KR = cross(sub(A.FAN_LOCAL[1], COMLocal), FanDir)[2]
        KDiff = 0.5 * (KL - KR)
        Total = clamp(Mass * AFanCmd - PodSum[0], -2 * FanMaxF, 2 * FanMaxF)
        RudCap = min(P['RudderAuthority'] * (Vf / max(P['RudderRefSpeed'], 1.0)) ** 2, P['RudderMaxAlpha']) * abs(Steer)
        RudderAlpha = clamp(AlphaZ - (PodTauZ + 0.5 * Total * (KL + KR)) / Izz, -RudCap, RudCap) if Izz > 1e-4 else 0.0
        TauKnown = PodTauZ + 0.5 * Total * (KL + KR) + Izz * RudderAlpha
        DMax = max(0.0, 2 * FanMaxF - abs(Total))
        D = clamp((TauZ - TauKnown) / KDiff, -DMax, DMax) if abs(KDiff) > 1 else 0.0
        FanF = [0.5 * Total + 0.5 * D, 0.5 * Total - 0.5 * D]
        AlphaGyroZ = clamp((TauZ - TauKnown - KDiff * D) / Izz, -P['GyroYawMax'], P['GyroYawMax']) if Izz > 1e-4 else 0.0

        ALatCmd = clamp(Klat * (cmd['VlTarget'] - Vl), -ALatMax, ALatMax)
        ALatPhys = (PodSum[1] + (FanF[0] + FanF[1]) * FanDir[1]) / Mass
        AGrip = ALatCmd - ALatPhys
        self.pf_grip_z = AGrip * Right[2]
        ARedirect = Eta * abs(AGrip) if (Vf > P['RedirectMinSpeed'] and AGrip * Vl < 0) else 0.0
        drift_kick = 0.0
        if drifting:
            self.drift_time += dt
        else:
            if self.drift_time >= P['DriftBoostMinTime'] and P['DriftBoostDV'] > 0:
                # Polish (judge "compete"): DriftBoostCapSpeed > 0 only tops the ship up to that forward speed, so
                # rhythmic brake-drifts no longer beat holding W on a straight (0 = off: the full v1 kick)
                kick = P['DriftBoostDV']
                cap = P.get('DriftBoostCapSpeed', 0.0)
                if cap > 0:
                    kick = min(kick, max(0.0, cap - Vf))
                if kick > 0:
                    body.add_impulse_vel(mul(Fwd, kick))
                drift_kick = kick
            self.drift_time = 0.0

        # 4d: low-speed station keeping (no throttle, no strafe, no boost)
        AKeepF = 0.0
        skg = P.get('StationKeepGain', 0.0)
        if skg > 0 and abs(Throttle) < 0.05 and abs(Strafe) < 0.05 and Boost < 0.05:
            hs = math.hypot(Vf, Vl)
            fade = clamp(2.0 - hs / max(P['StationKeepSpeed'], 1.0), 0.0, 1.0)
            AKeepF = clamp(-skg * Vf, -P['StationKeepAccelMax'], P['StationKeepAccelMax']) * fade

        WindScale = 1.0 - clamp(size(V) / max(P['WindFadeSpeed'], 1.0), 0.0, 1.0)
        if not sim.wind:
            WindScale = 0.0
        seed = self.wind_seed
        WindLat = P['WindLateralAccel'] * WindScale * perlin1d(now * P['WindLateralFrequency'] + seed)
        WindRoll = P['WindRollAccel'] * WindScale * perlin1d(now * P['WindRollFrequency'] + seed + 17.3)
        WindPitch = P['WindPitchAccel'] * WindScale * perlin1d(now * P['WindPitchFrequency'] + seed + 41.9)

        for i in range(4):
            body.add_force_at_location(PodWorld[i], body.transform_position(A.POD_LOCAL[i]))
        for j in range(2):
            body.add_force_at_location(qrot(q, mul(FanDir, FanF[j])), body.transform_position(A.FAN_LOCAL[j]))
        ACom = add(mul(Right, AGrip + WindLat), mul(Fwd, ADrag + ABrake + ARedirect + AKeepF))
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
                          YawRateCmd=YawRateCmd, AlphaGyroTilt=AlphaGyroTilt, DriftKick=drift_kick, ARedirect=ARedirect,
                          AVert=AVert, AKeepF=AKeepF, TauFanY=TauFan[1])


# =====================================================================================================================
# The heading loop: one function, run by the server (authoritative steer) and by the pilot's machine (its cosmetics)
# =====================================================================================================================
def rmax_deg(P, vf_cm, boost, drifting):
    """The yaw-rate table of ApplyForces (deg/s at full steer)."""
    a = abs(vf_cm)
    if a <= P['YawRateMidSpeed']:
        r = lerp(P['YawRateAtRest'], P['YawRateAtMid'], a / max(P['YawRateMidSpeed'], 1.0))
    else:
        r = lerp(P['YawRateAtMid'], P['YawRateAtTop'], clamp((a - P['YawRateMidSpeed']) / max(P['YawRateTopSpeed'] - P['YawRateMidSpeed'], 1.0), 0.0, 1.0))
    return P['YawRateDrift'] if drifting else lerp(r, P['YawRateBoost'], boost)


def heading_steer(P, st, target_deg, yaw_deg, rate_degs, vf_cm, boost, brake, dt):
    """Heading target -> steer (-1..1), the Classic-shaped value every consumer of Steer already understands.

    st: this machine's loop state (dict) = {'drift': bool}. Deterministic from (target, the hull this machine sees,
    boost, brake). The C++ port is UAirshipFlightComponent::ComputeHeadingSteer (SCHEME_POINTFLY.md section 4)."""
    e = wrap180(target_deg - yaw_deg)
    # drift: brake + a big turn at speed (hysteresis: it starts beyond PFDriftStartDeg, runs until the brake
    # is let go or the remaining turn is below PFDriftEndDeg; ShapeControls sees it as |Steer| above the threshold)
    drift = st.get('drift', False)
    if not brake or vf_cm <= P['DriftMinSpeed']:
        drift = False
    elif not drift and abs(e) >= P['PFDriftStartDeg']:
        drift = True
    elif drift and abs(e) < P['PFDriftEndDeg']:
        drift = False
    st['drift'] = drift
    rmax = max(rmax_deg(P, vf_cm, boost, drift), 1.0)
    ep = e - rate_degs * P['PFHeadingLead']
    dec = P['PFHeadingDecelDeg'] * (P['PFDriftDecelScale'] if drift else 1.0)
    mag = min(rmax, P['PFHeadingKp'] * abs(ep), math.sqrt(2.0 * dec * abs(ep)))
    if abs(e) < P['PFHeadingDeadbandDeg'] and abs(rate_degs) < 2.0:
        mag = 0.0
    steer = math.copysign(mag, ep) / rmax
    thr = P['DriftSteerThreshold']
    if drift:
        # keep the slide alive until the end of the turn
        steer = math.copysign(max(abs(steer), thr + 0.05), e if abs(steer) < 1e-6 else steer)
    elif brake and vf_cm > P['DriftMinSpeed']:
        # braking without a drift: stay under the drift threshold
        steer = clamp(steer, -(thr - 0.02), thr - 0.02)
    st['e'] = e
    return clamp(steer, -1.0, 1.0)


# =====================================================================================================================
# The scheme
# =====================================================================================================================
@register_scheme
class PointFly(Classic):
    key = 'pointfly'
    enum = 3
    label = 'Point & Fly'
    ctrl_inertia = 'hull'                  # base fix 4a-1 (bHullAxisInertia)

    flight = dict(
        # ---- base fixes (BASELINE.md 4f), all on -----------------------------------------------------------------
        bFanTorqueFeedForward=True,                          # 4a-2
        PitchPerG=4.0, PitchMinDeg=-4.0, BoostPitchDeg=1.5,  # 4a-3
        VertBrakeAccel=784.0, HoldBrakeAccel=1470.0, LiftTauRelease=0.08,   # 4b
        bBrakeHoldLead=True, BrakeFadeSpeed=1000.0,          # 4c
        StationKeepGain=1.0, StationKeepSpeed=300.0, StationKeepAccelMax=150.0,   # 4d
        # ---- Point & Fly flight tunables (new, UAirshipFlightComponent, category "Airship|PointFly") ----------------
        PFHeadingKp=6.5,            # 1/s: turn rate per degree of (predicted) heading error
        PFHeadingLead=0.18,         # s: the loop works on the error this far ahead (yaw-loop + filter lag)
        PFHeadingDecelDeg=55.0,     # deg/s^2: planned yaw deceleration onto the target (sqrt profile)
        PFHeadingDeadbandDeg=0.25,  # deg: no steer inside this (wheel and fans rest)
        PFDriftStartDeg=40.0,       # deg: brake with this much turn left = a drift
        PFDriftEndDeg=15.0,         # deg: the drift ends with this much left
        PFDriftDecelScale=0.8,      # the sliding hull stops its yaw more gently (no overshoot at the exit)
        PFBrakeAccelMax=1470.0,     # cm/s^2: air-brake cap (constant-decel brake, 1.5 g + the reversed fans)
        PFReverseBrakeAccel=980.0,  # cm/s^2: S while moving forward brakes at 1 g (then reverses)
        PFAimBankScale=0.4,         # bank in broadside mode (steady gun deck)
        PFTurnLiftComp=1.0,         # 0..1: collective makes up the turn's downward grip (no sink in turns)
        # ---- existing tunables, Point & Fly values ----------------------------------------------------------------
        SteerTau=0.10,              # the loop's steer is already smooth
        Kr=5.5,                     # 1/s: stiffer yaw-rate loop under the heading loop (the 1 rad/s^2 cap keeps big turns heavy)
        StrafeTau=0.12, StrafeSpeed=1400.0, StrafeBankDeg=7.0,
        DriftSteerThreshold=0.3,
        Kbrake=2.0,                 # 1/s: with PFBrakeAccelMax a near constant-deceleration stop (48 -> 0 m/s in 2.5 s)
        AFan=1400.0,                # cm/s^2: the launch of v1 back (the dip fix took the 0.27 g the nose dip added)
        # ---- polish after judging (SCHEME_POINTFLY.md "Review changes", P1 / P2) --------------------------------------
        DriftBoostCapSpeed=4800.0,  # cm/s: the drift kick only tops up to cruise (no straight-line drift snake)
        GyroYawMax=1.0,             # rad/s^2 (v1 0.5): the stop of a fast turn is no longer actuator-limited
        KrSteady=5.5, AlphaYawMaxSteady=1.5,   # "meet her" while a turn is taken off (onset still capped by AlphaYawMax 1)
    )
    pawn = dict(
        RecenterSpeed=0.0,          # the camera is the steering: it never moves by itself
        # ---- Point & Fly pawn tunables (new, AAirshipPawn, category "Airship|PointFly") ---------------------------
        PFNudgeRateScale=1.0,       # Q/E (D-pad) turn the heading target at this x the ship's full turn rate
        PFHeadingMaxLeadDeg=150.0,  # deg: the target stays within this of the ship's heading (steering mode)
        PFLockLeadTime=0.6,         # s: while the gun lock follows a target, the sent target leads by its rate x this
                                    #    (polish P5, was 0.45: centres a crosshair-held target with the PIE camera lag)
        PFHeadingLeadRateMax=30.0,  # deg/s: rate estimate clamp (flicks don't lead)
        PFHeadingLeadTau=0.12,      # s: rate estimate filter
        PFLookReturnTau=0.22,       # s: after broadside mode the camera eases back onto the heading
        PFArcAssist=True,           # broadside mode: swing the ship when the aim is off the guns' arc
        PFArcMarginDeg=6.0,         # deg: keep the aim this far inside the cannons' yaw limit
        PFArcMinBearingDeg=55.0,    # deg off the bow: below / above these the aim never swings the ship (REVIEW: was 35)
        PFArcMaxBearingDeg=150.0,
        PFArcRateDeg=45.0,          # deg/s: fastest swing of the heading target by the assist
        PFArcLockDeadbandDeg=3.0,   # deg: once locked, the beam stays this close to the aim
        PFArcApproachRateDeg=3.0,   # deg/s: an aim closing on the arc faster than this is waited for (no lock)
        PFArcLockDelay=0.25,        # s: outside the arc and not coming in for this long = lock
        PFArcApproachTau=0.1,
        PFPitchClimb=False,         # camera pitch -> climb / sink (tested: off, see SCHEME_POINTFLY.md)
        PFPitchClimbDeadbandDeg=10.0,
        PFPitchClimbFullDeg=20.0,
        # ---- polish after judging (P3 / P4) -------------------------------------------------------------------------
        PFParkSpeed=300.0,          # cm/s: parked free look below this with no drive / sidestep / turn / boost key
        PFLockArmTime=6.0,          # s: the gun lock is armed while Fire is held or this long after the own broadside
    )
    ext_fields = {'HeadingTarget': HEADING_SPEC}

    # course.py pointfly --tune (2026-11-23): score 140.9 (Classic's own gains score 141.6 on Classic)
    GAINS = dict(course=0.7, rate_damp=0.3, speed=0.25, alt=0.12, vz_damp=0.06, ct=1.2, lag=0.65, margin=7.0, turn_frac=0.95,
                 range_k=0.12, range_damp=0.25)

    # ---- runtime state ---------------------------------------------------------------------------------------------
    def reset(self, sim):
        sim.pilot_state = {}
        sim.server_state = {}
        # the base fixes (see the module docstring)
        for fm in (sim.server, sim.pilot_fm):
            if fm.__class__ is A.FlightModel:
                fm.__class__ = PFFlightModel

    # ---- pilot's machine: camera -> heading target -------------------------------------------------------------
    def camera(self, sim, raw, cam, view, dt):
        PP, P = sim.PP, sim.P
        ps = sim.pilot_state
        yaw_v = view['YawDeg']
        if 'H' not in ps:
            # board / switch: the target starts on the ship's heading, the camera behind it
            ps.update(H=yaw_v, off=0.0, last_set=cam.control_yaw, free=False, assist=False)
            cam.control_yaw = yaw_v
            ps['last_set'] = yaw_v
        # this frame's look input = the change of the control rotation since we last set it. With IA_AirshipLook this
        # frame it is the mouse / stick (a delta); without it the rotation was set from outside (the PIE harness,
        # a possession reset): an absolute set of the camera, and in steering mode of the heading target as well
        d_yaw = wrap180(raw.cam_yaw - ps['last_set']) if raw.cam_yaw is not None else 0.0
        external = raw.cam_yaw is not None and not raw.look and abs(d_yaw) > 1e-6
        if raw.cam_pitch is not None:
            cam.control_pitch = raw.cam_pitch
        if raw.look:
            cam.last_look_time = sim.time
        if raw.zoom:
            cam.arm = clamp(cam.arm - raw.zoom * 800.0, PP['CameraArmMin'], PP['CameraArmMax'])
        free = bool(raw.aim)
        H, off = ps['H'], ps['off']
        # Q/E (IA_AirshipStrafe): turn the heading target with keys at the ship's own full turn rate for this speed
        # (x PFNudgeRateScale), so the target runs only the loop's tracking lag ahead and the turn stops soon after
        # the key is let go. Open loop on purpose: a clamp against the pilot's lagging view of the nose would close a
        # loop over the network (tested: 3-6 gates missed at 100 ms)
        nudge_rate = PP['PFNudgeRateScale'] * rmax_deg(P, view['ForwardSpeed'], sim.pilot_fm.sh_boost, False)
        nudge = clamp(raw.strafe, -1.0, 1.0) * nudge_rate * dt
        # Polish (judge "newplayer"): parked free look. At rest (|forward speed| < PFParkSpeed) with no drive, sidestep,
        # turn or boost key, the mouse looks around and the heading holds (as on foot); the first such key takes the
        # camera's yaw as the heading. An outside set (harness, reset) still sets the heading (steering-mode rule).
        # F-B: once parked it holds at any speed (a hit that pushes the ship past PFParkSpeed doesn't end it) until a
        # key, Aim, or an outside set above PFParkSpeed (PARK_LATCH)
        move_keys = abs(raw.throttle) > 0.05 or abs(raw.steer) > 0.05 or abs(raw.strafe) > 0.05 or bool(raw.boost)
        latched = PARK_LATCH and bool(ps.get('parked')) and not external
        parked = (PP.get('PFParkSpeed', 0.0) > 0 and not free and not move_keys
                  and (abs(view['ForwardSpeed']) < PP['PFParkSpeed'] or latched))
        if parked:
            if external:
                H, off = raw.cam_yaw, 0.0
            else:
                off = wrap180(off + d_yaw)        # look around; the heading holds
            ps['parked'] = True
            ps['assist'], ps['dwell'] = False, 0.0
            ps.pop('ob_prev', None)
            ps.pop('ob_rate', None)
            free = False
        elif not free and ps.get('parked'):
            # the first drive / turn key: go where the camera looks (the 150 deg reach clamp keeps the camera
            # still: the part beyond it eases back as after broadside mode)
            ps['parked'] = False
            cam_y = raw.cam_yaw if external else wrap180(H + off + d_yaw)
            lead = wrap180(cam_y - yaw_v)
            m = PP['PFHeadingMaxLeadDeg']
            H = cam_y if abs(lead) <= m else wrap180(yaw_v + math.copysign(m, lead))
            off = wrap180(cam_y - H)
            d_yaw = 0.0
        elif free:
            ps['parked'] = False
        if parked:
            pass
        elif free:
            off = off + d_yaw                     # the camera looks around, the heading holds
            H += nudge
            off -= nudge                          # Q/E turn the ship, the camera stays on its point
            # Polish (judge "compete"): PFLockArmTime > 0 arms the gun lock only while Fire is held or for that long
            # after the pilot's own broadside, so Aim alone is a clean free look (0 = always armed in broadside mode)
            arm_t = PP.get('PFLockArmTime', 0.0)
            last_own = sim.cannon_shots[-1]['t'] if sim.cannon_shots else -1e9
            armed = arm_t <= 0 or bool(raw.fire) or sim.time - last_own <= arm_t
            if nudge != 0.0 or not armed:
                ps['assist'], ps['dwell'] = False, 0.0          # a manual turn overrides the gun lock
                if not armed:
                    ps.pop('ob_prev', None)
                    ps.pop('ob_rate', None)
            elif PP['PFArcAssist']:
                H_new = self.arc_assist(PP, H, H + off, dt, ps)
                off -= wrap180(H_new - H)
                H = H_new
            off = wrap180(off)
        else:
            if external:
                H, off = raw.cam_yaw, 0.0         # set from outside: heading target and camera both there
            else:
                H += d_yaw                        # steering: the camera yaw is the heading target
            H += nudge
            off *= math.exp(-dt / max(PP['PFLookReturnTau'], 1e-3))
            if abs(off) < 0.05:
                off = 0.0
            ps['assist'] = False
            ps['dwell'] = 0.0
            ps.pop('ob_prev', None)
            ps.pop('ob_rate', None)
            # the target stays within reach (no +-180 flip on the server)
            lead = wrap180(H - yaw_v)
            m = PP['PFHeadingMaxLeadDeg']
            if abs(lead) > m:
                H = yaw_v + math.copysign(m, lead)
        ps['H'], ps['off'], ps['free'] = wrap180(H), off, free
        cam.control_yaw = wrap180(ps['H'] + off)
        ps['last_set'] = cam.control_yaw
        cam.control_pitch = clamp(wrap180(cam.control_pitch), PP['CameraPitchMin'], PP['CameraPitchMax'])
        self.camera_lag(sim, cam, dt)
        cam.free_look = free

    @staticmethod
    def arc_assist(PP, H, cam_yaw, dt, ps):
        """Broadside mode, the gun lock. While the aim is inside the facing side's gun arc (cannon yaw limit minus
        PFArcMarginDeg), or outside it but coming into it (a target the ship is sailing past), the heading holds. When
        the aim has been outside the arc and not coming in for PFArcLockDelay, the lock engages: the heading target is
        dragged so the beam stays within PFArcLockDeadbandDeg of the aim, at most PFArcRateDeg per second, until the
        aim leaves the broadside sector or Aim is released. Pilot-side only: it changes the heading target (measured
        against the target, not the lagging hull); the server just follows it."""
        b = wrap180(cam_yaw - H)                 # the aim's bearing off the target heading (+ = starboard)
        ab = abs(b)
        ob = abs(ab - 90.0)
        rate_raw = (ob - ps['ob_prev']) / dt if 'ob_prev' in ps else 0.0
        ps['ob_prev'] = ob
        ob_rate = ps['ob_rate'] = approach(ps.get('ob_rate', 0.0), rate_raw, dt, PP.get('PFArcApproachTau', 0.0))
        if ab < PP['PFArcMinBearingDeg'] or ab > PP['PFArcMaxBearingDeg']:
            ps['assist'] = False
            ps['dwell'] = 0.0
            return H
        side = 1.0 if b > 0 else -1.0
        off_beam = ab - 90.0                      # + = aft of the beam
        if not ps.get('assist'):
            outside = ob > PP['CannonYawLimitDeg'] - PP['PFArcMarginDeg']
            coming_in = ob_rate < -PP['PFArcApproachRateDeg']
            ps['dwell'] = ps.get('dwell', 0.0) + dt if (outside and not coming_in) else 0.0
            if ps['dwell'] >= PP['PFArcLockDelay']:
                ps['assist'] = True
        if not ps.get('assist'):
            return H
        db = PP['PFArcLockDeadbandDeg']
        if abs(off_beam) <= db:
            return H
        excess = off_beam - math.copysign(db, off_beam)
        # aim aft of the beam on starboard (b > 90): turn right (H +); forward of it: turn left; mirrored on port
        step = PP['PFArcRateDeg'] * dt
        return H + clamp(side * excess, -step, step)

    def pilot_input(self, sim, raw, cam, view, dt):
        P, PP = sim.P, sim.PP
        ps = sim.pilot_state
        p = PilotInput()
        lift = raw.lift
        if PP['PFPitchClimb'] and not raw.aim and abs(lift) < 0.05:
            dp = cam.control_pitch - PP['CameraDefaultPitch']
            db = PP['PFPitchClimbDeadbandDeg']
            if abs(dp) > db:
                lift = clamp((abs(dp) - db) / max(PP['PFPitchClimbFullDeg'], 1.0), 0.0, 1.0) * (1.0 if dp > 0 else -1.0)
                lift = round(lift * 16.0) / 16.0           # coarse steps: the send-on-change stays rare
        # lock lead: while the gun lock drags the target along (it follows a moving target smoothly), send it ahead by
        # its own rate x PFLockLeadTime so the beam doesn't trail the aim. Steering mode sends the plain target: a
        # lead there would overshoot when the camera stops (tested: 1-4 deg after a 20-30 deg/s sweep)
        H = ps['H']
        rate_raw = wrap180(H - ps.get('H_prev', H)) / dt
        ps['H_prev'] = H
        rm = PP['PFHeadingLeadRateMax']
        ps['H_rate'] = approach(ps.get('H_rate', 0.0), clamp(rate_raw, -rm, rm), dt, PP['PFHeadingLeadTau'])
        lead_t = PP['PFLockLeadTime'] if (raw.aim and ps.get('assist')) else 0.0
        H_send = wrap180(H + lead_t * ps['H_rate'])
        ps['H_send'] = H_send
        # the local copy of the heading loop: the pilot's own wheel, fans and bank cosmetics (and the wire Steer)
        st = ps.setdefault('loop', {})
        steer = heading_steer(P, st, H_send, view['YawDeg'], view['YawRateDegS'], view['ForwardSpeed'],
                              sim.pilot_fm.sh_boost, raw.brake, dt)
        p.set_axes(throttle=raw.throttle, steer=steer, lift=lift, strafe=raw.steer)     # A/D -> Strafe axis
        p.set_button(BUTTON_BOOST, raw.boost)
        p.set_button(BUTTON_BRAKE, raw.brake)
        p.set_button(BUTTON_AIM, raw.aim)
        p.ext['HeadingTarget'] = encode_heading(H_send)
        aim = sim.aim_point(cam, view)
        if aim is not None:
            p.aim = aim
            p.set_button(BUTTON_HAS_AIM, True)
        return p

    # ---- server ------------------------------------------------------------------------------------------------------
    def server_controls(self, sim, controls, dt):
        H = decode_heading(controls.ext.get('HeadingTarget', 0))
        if H is None:
            sim.server_state['H'] = None
            return controls          # no target (neutral input, timeout, DebugSetInput): the Steer axis as sent
        P = sim.P
        b = sim.body
        st = sim.server_state.setdefault('loop', {})
        pit, yaw, roll = quat2rot(b.q)
        vf = dot(b.v, qrot(b.q, (1.0, 0.0, 0.0)))
        steer = heading_steer(P, st, H, yaw, b.w[2] * R2D, vf, sim.server.sh_boost, controls.has(BUTTON_BRAKE), dt)
        controls.steer = quantize_axis(steer)   # RepInput carries the server's steer: observers' cosmetics follow
        sim.server_state['H'] = H
        return controls

    def server_commands(self, sim, fm, cmd):
        P = sim.P
        Vf = cmd['Vf']
        # constant-deceleration brake: the air brake is capped, the reversed fans add their share
        if cmd['ABrake'] != 0.0 and P['PFBrakeAccelMax'] > 0:
            cmd['ABrake'] = clamp(cmd['ABrake'], -P['PFBrakeAccelMax'], P['PFBrakeAccelMax'])
        # S while moving forward: a firm 1 g slow-down (the fans reverse), then the normal gentle reverse
        if fm.sh_throttle < 0 and not cmd['brake'] and Vf > 200.0 and P['PFReverseBrakeAccel'] > 0:
            cmd['AFanCmd'] = min(cmd['AFanCmd'], P['PFReverseBrakeAccel'] * fm.sh_throttle * clamp(Vf / 600.0, 0.0, 1.0))
        # broadside mode: a steadier gun deck
        if fm.b_aiming:
            cmd['BankDeg'] = cmd['BankDeg'] * P['PFAimBankScale']

    def telemetry(self, sim, tele):
        tele['Scheme'] = self.enum
        tele['ThrottleOrder'] = -2.0
        tele['DriftCharge'] = 0.0
        H = sim.server_state.get('H') if hasattr(sim, 'server_state') else None
        tele['bHeadingTargetActive'] = H is not None
        tele['HeadingTargetDeg'] = wrap180(H) if H is not None else 0.0
        ps = getattr(sim, 'pilot_state', {})
        rep = getattr(sim, 'rep_input', None)
        tele['bFreeLook'] = bool(rep.has(BUTTON_AIM)) if rep is not None else False      # server: Button_Aim
        tele['PilotHeadingTargetDeg'] = ps.get('H')
        tele['bArcAssist'] = bool(ps.get('assist', False))

    # ---- bench adapters ------------------------------------------------------------------------------------------
    def command_raw(self, sim, cmd):
        """Open-loop maneuvers: 'steer' = the camera swung that way (it leads the ship by 90 deg, so the loop turns at
        full rate), 'strafe' = A/D, 'drift' = brake + a big camera swing, the rest as Classic."""
        ps = sim.pilot_state
        view = sim.pilot_view()
        r = RawInput(throttle=cmd.thrust, steer=cmd.strafe, lift=cmd.lift, boost=cmd.boost,
                     brake=cmd.brake or cmd.drift, aim=cmd.aim, fire=cmd.fire)
        if cmd.look_yaw is not None:
            r.cam_yaw, r.cam_pitch, r.look = cmd.look_yaw, cmd.look_pitch if cmd.look_pitch is not None else -12.0, True
            return r
        if abs(cmd.steer) > 1e-3:
            r.cam_yaw = self.mouse_to_heading(sim, view['YawDeg'] + 90.0 * cmd.steer)
            r.look = True
            ps['cmd_turning'] = True
        elif ps.get('cmd_turning'):
            # stop turning: the camera back onto the nose (where the turn would stop)
            r.cam_yaw = self.mouse_to_heading(sim, view['YawDeg'] + view['YawRateDegS'] * 0.3)
            r.look = True
            ps['cmd_turning'] = False
        return r

    # bot gains (course.py --tune): the camera looks along the wanted course, led by the line's turn rate for
    # LEAD_PER_COURSE * course seconds (the tuner's 'course' slot); rate_damp is unused; the rest as Classic (speed,
    # alt, vz_damp, ct, lag, margin, turn_frac). Broadside: range_k (1/m), range_damp (s) on A/D.
    LEAD_PER_COURSE = 0.25

    def intent_raw(self, sim, intent, view, gains=None):
        g = dict(self.GAINS)
        if gains:
            g.update(gains)
        P, PP = sim.P, sim.PP
        vf = view['ForwardSpeedMS']
        r = RawInput()
        # ---- speed: W, S as a firm brake, X only when it can't start a drift
        brake = False
        if intent.speed is None:
            thr = 1.0
        else:
            ev = intent.speed - vf
            ff = sim.hold_throttle(intent.speed * 100.0)
            thr = clamp(ff + g['speed'] * ev, -1.0, 1.0)
            if ev < -3.0 or (intent.brake_hint and ev < -1.5):
                thr = -1.0
        # ---- altitude: Space / Ctrl, released near the target
        lift = 0.0
        if intent.alt is not None:
            ez = intent.alt - view['AltitudeM']
            lift = clamp(g['alt'] * ez - g['vz_damp'] * view['VerticalSpeedMS'], -1.0, 1.0)
            if abs(lift) < P['LiftDeadZone'] * 1.2:
                lift = 0.0
        r.throttle, r.lift, r.brake = thr, lift, brake
        look = intent.look_at
        if look is not None:
            cam_loc = sim.camera_location_m(view)
            d = sub(look, cam_loc)
            look_yaw = math.atan2(d[1], d[0]) * R2D
            look_pitch = math.atan2(d[2], math.hypot(d[0], d[1])) * R2D
            bearing = wrap180(look_yaw - view['YawDeg'])
            if abs(bearing) > 30.0:
                return self.broadside_raw(sim, intent, view, g, r, look, look_yaw, look_pitch, bearing)
        # ---- steering: look along the wanted course, a little into the turn (what a player does: look where the
        # ship should go). No feedback on the ship's own heading: the server's heading loop closes that.
        H = intent.course_deg + self.LEAD_PER_COURSE * g['course'] * intent.yaw_rate_ff
        r.cam_yaw = self.mouse_to_heading(sim, H)
        r.cam_pitch = PP['CameraDefaultPitch']
        r.look = True
        return r

    @staticmethod
    def mouse_to_heading(sim, H):
        """The control rotation a mouse move that brings the heading target to H leaves behind (the bench sets the
        control rotation absolutely; while the camera eases back after broadside mode it is not on the target)."""
        ps = sim.pilot_state
        if 'H' not in ps:
            return wrap180(H)
        return wrap180(sim.cam.control_yaw + wrap180(H - ps['H']))

    def broadside_raw(self, sim, intent, view, g, r, look, look_yaw, look_pitch, bearing):
        """Broadside mode: hold Aim and look at the target. The gun lock keeps the beam on it, so flying forward
        circles it; A/D (sidestep) hold the range, W/S the speed."""
        loc = mul(view['ActorLocCm'], 0.01)
        dx, dy = look[0] - loc[0], look[1] - loc[1]
        rng = math.hypot(dx, dy)
        vel = mul(view['VelCm'], 0.01)
        rdot = -(vel[0] * dx + vel[1] * dy) / max(rng, 1.0)      # + = opening
        r.aim = True
        r.cam_yaw, r.cam_pitch, r.look = look_yaw, look_pitch, True
        side = 1.0 if bearing > 0 else -1.0       # + = target to starboard
        r0 = getattr(intent, 'range_m', None) or 100.0
        # too far or opening: sidestep toward the target (A/D)
        want = g.get('range_k', 0.08) * (rng - r0) + g.get('range_damp', 0.25) * rdot
        r.steer = clamp(side * want, -1.0, 1.0)
        return r

    KEY_AXES = ('throttle', 'steer', 'lift', 'strafe')


# =====================================================================================================================
if __name__ == '__main__':
    if '--selftest' in sys.argv:
        # PFFlightModel with every fix off and Classic presets must equal the bench's FlightModel
        from airship_sim import Sim, run_commands

        class _Check(Classic):
            key = '_pfcheck'

            def reset(self, sim):
                Classic.reset(self, sim)
                for fm in (sim.server, sim.pilot_fm):
                    fm.__class__ = PFFlightModel
        worst = 0.0
        for name, sched in (('throttle', lambda t, s: Command(thrust=1.0)),
                            ('steer', lambda t, s: Command(thrust=1.0, steer=1.0 if t > 3 else 0.0)),
                            ('lift', lambda t, s: Command(lift=1.0 if t < 3 else 0.0, brake=6 < t < 7)),
                            ('drift', lambda t, s: Command(thrust=1.0, steer=1.0 if t > 5 else 0.0, drift=5 < t < 8))):
            a = Sim(Classic(), latency_ms=0)
            b = Sim(_Check(), latency_ms=0)
            la = run_commands(a, sched, 12.0)
            lb = run_commands(b, sched, 12.0)
            d = max(max(abs(x['ForwardSpeedMS'] - y['ForwardSpeedMS']), abs(x['PitchDeg'] - y['PitchDeg']),
                        abs(x['YawRateDegS'] - y['YawRateDegS']), abs(x['AltitudeM'] - y['AltitudeM'])) for x, y in zip(la, lb))
            worst = max(worst, d)
            print('%-8s max |difference| %.2e' % (name, d))
        print('self-test', 'PASS' if worst < 1e-9 else 'FAIL')
