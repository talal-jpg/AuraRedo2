"""Sky Racer (EAirshipControlScheme::SkyRacer = 2): arcade speed and flow for the airship (Docs/Airship/controls/
SCHEME_SKYRACER.md is the spec; this file is its bench model).

    W / S          hard acceleration / brake (S is an analog brake above 3 m/s, reverse below)
    A / D          fast, snappy turn with a planted bank that levels itself on release
    X (+ A / D)    brake; with A / D above 15 m/s: DRIFT. The path turns at 24-46 deg/s (steer sets it), the nose
                   holds a 16-26 deg slip, a 3-tier mini-turbo charges. Let go of X: the turbo fires (kick + burn +
                   boost fuel). Drift again within 2.5 s of a turbo: CHAIN (+15 % per link, up to 3)
    Shift          boost burst (at least 0.5 s per press, fuel gated)
    Space / Ctrl   punchy climb / dive (stops where you let go; diving adds forward speed)
    RMB (aim)      gun deck: the bank flattens to 35 %, throttle / brake / turn soften for broadsides

How it plugs into the bench (no shared file is edited):
  * The bench's FlightModel has none of the BASELINE.md section 4 base fixes and no hook for the attitude solve or the
    hold logic, so reset() swaps the class of the sim's flight models (sim.server and, for a client pilot,
    sim.pilot_fm) to SkyFlightModel below. It is FlightModel with apply_forces copied from airship_sim.py and these
    changes, each one a tunable whose v1 value turns it off (so the C++ Classic preset stays exact v1):
      - base fixes 4a-2 (bFanTorqueFeedForward), 4b (VertBrakeAccel, HoldBrakeAccel, LiftTauRelease),
        4c (bBrakeHoldLead, BrakeFadeSpeed), 4d (StationKeepGain/Speed/AccelMax), ported from baseline_sim.py;
        4a-1 is the bench's own ctrl_inertia = 'hull';
      - Sky Racer: bSkyDrift (drift state machine, mini-turbo, chain), SkySBrakeSpeed (S brakes), SkyBrakeAccelMax
        (brake cap), SkyDiveAccelPerSink (dive gain), SkyAimBankScale (steady deck), SkyBoostMinBurst (burst latch).
  * The drift state machine runs in shape_controls on EVERY machine from the controls alone (brake bit, steer) plus
    the forward speed gate, like v1's bDrifting. So the pilot's HUD / FX / camera predict it with no new
    FAirshipPilotInput field, and the server pays the turbo from its own copy of the same state.

Run:  python3 metrics.py skyracer        -> skyracer_metrics.json
      python3 course.py skyracer         -> gate course, both bots, 0 / 100 ms
      python3 skyracer_checks.py         -> the Sky Racer target bands and the drift / turbo / lag checks
"""
import math

import airship_sim as A
from airship_sim import (Classic, RawInput, register_scheme, BUTTON_BOOST, BUTTON_BRAKE, BUTTON_AIM, clamp, lerp,
                         wrap180, approach, approach_ud, add, sub, mul, dot, cross, size, norm, clampsize, qrot, qunrot,
                         qmul, qinv, quat2rot, rot2quat, to_axis_angle, solve3, perlin1d, D2R, R2D, G)

# ---------------------------------------------------------------------------------------------------------------------
# New flight-component tunables: name -> v1 value (= off). The C++ adds them as UPROPERTYs with these defaults.
# ---------------------------------------------------------------------------------------------------------------------
BASE_FIX_V1 = dict(
    bFanTorqueFeedForward=False, VertBrakeAccel=0.0, HoldBrakeAccel=0.0, LiftTauRelease=0.0, bBrakeHoldLead=False,
    BrakeFadeSpeed=0.0, StationKeepGain=0.0, StationKeepSpeed=300.0, StationKeepAccelMax=150.0,
)
SKY_FLIGHT_V1 = dict(
    bSkyDrift=False,
    SkyDriftEnterSteer=0.5, SkyDriftEnterSpeed=1500.0, SkyDriftExitSpeed=800.0,
    SkyDriftPathRateMinDeg=24.0, SkyDriftPathRateMaxDeg=46.0, SkyDriftSlipMinDeg=16.0, SkyDriftSlipMaxDeg=26.0,
    SkyDriftSlipGain=3.0, SkyDriftPathLeadDeg=10.0, SkyDriftYawRateMaxDeg=65.0, SkyDriftAlphaYawMax=2.5, SkyDriftALatMaxG=5.0,
    SkyDriftScrub=0.08, SkyDriftExitYawGain=6.0, SkyDriftBankDeg=24.0, SkyDriftGimbalRollDeg=4.0,
    SkyChargeRateMin=0.2, SkyChargeRateMax=0.5, SkyTier1=0.25, SkyTier2=0.55, SkyTier3=1.0, SkyTierGrace=0.03,
    SkyTurboKickDV1=300.0, SkyTurboKickDV2=500.0, SkyTurboKickDV3=750.0,
    SkyTurboTime1=0.5, SkyTurboTime2=0.8, SkyTurboTime3=1.2, SkyTurboAccel=490.0, SkyTurboVTop=9000.0,
    SkyTurboFuel1=4.0, SkyTurboFuel2=8.0, SkyTurboFuel3=15.0,
    SkyChainWindow=2.5, SkyChainBonus=0.15, SkyChainMax=3,
    SkySBrakeSpeed=0.0, SkySBrakeTauUp=0.0, SkySBrakeTauDown=0.0, SkyBrakeAccelMax=0.0, SkyDiveAccelPerSink=0.0, SkyDiveMinSpeed=1500.0,
    SkyAimBankScale=1.0, SkyAimThrottleScale=1.0, SkyAimBrakeScale=1.0, SkyAimYawScale=1.0,
    SkyBoostMinBurst=0.0,
    SkyDriftThrottle=0.0,
    # lateral (grip) model: level hidden side force, centripetal feed-forward, energy-based redirect, drift exit snap
    bSkyLevelGrip=False, SkyGripCentripetalFF=0.0, SkyGripEnergyKeep=0.0,
    SkyDriftExitTime=0.0, SkyDriftExitKlat=8.0, SkyDriftExitALatMaxG=5.0,
)
SKY_PAWN_V1 = dict(
    SkyLookIntoTurnTime=0.0, SkyLookIntoTurnMaxDeg=14.0, SkyCamSlipShare=0.0, bSkyCamYawRateFF=False,
    SkyCamDivePitchPerMS=0.0, SkyCamDivePitchMaxDeg=8.0,
    # not modelled by the bench (spec only, listed so the preset table is complete): camera roll, shake, FOV kicks,
    # turbo arm, rumble
    SkyCamRollShare=0.0, SkyCamRollMaxDeg=6.0, SkyShakeRotDeg=0.0, SkyFOVMax=0.0, SkyTurboArmExtra=0.0,
)


def _tier(P, c):
    if c >= P['SkyTier3'] - 1e-6:
        return 3
    if c >= P['SkyTier2'] - 1e-6:
        return 2
    if c >= P['SkyTier1'] - 1e-6:
        return 1
    return 0


class SkyFlightModel(A.FlightModel):
    """UAirshipFlightComponent with the base fixes and the Sky Racer behaviours (see the module docstring)."""

    # ------------------------------------------------------------------------------------------------ runtime state
    def sky_reset(self):
        """Scheme-local runtime state (C++: ResetSchemeState, on a switch, board / exit, death)."""
        self.sky_clock = 0.0            # this machine's own clock (sum of the shaping dt)
        self.sky_drift_dir = 0          # -1 left, +1 right, 0 none
        self.sky_charge = 0.0           # 0..1
        self.sky_drift_t = 0.0
        self.sky_turbo_tier = 0
        self.sky_turbo_left = 0.0
        self.sky_turbo_total = 1.0
        self.sky_turbo_event = 0        # tier released this frame (the server pays it in apply_forces)
        self.sky_turbo_chain = 0
        self.sky_chain = 0
        self.sky_last_release = -1000.0
        self.sky_brake_amount = 0.0
        self.sky_sbrake = 0.0           # S-brake amount, progressive (a tap trims, a hold stops)
        self.sky_exit_left = 0.0        # drift exit snap window (s)
        self.sky_boost_start = -1000.0
        self.sky_local_boost_start = -1000.0
        self.sky_last_tier = 0          # for the bench's checks: tier of the last release
        self.sky_releases = []          # (clock, tier, chain) on this machine

    # ------------------------------------------------------------------------------------------------ boost (burst latch)
    def update_boost_server(self, want, dt, body, now):
        P = self.P
        if P['SkyBoostMinBurst'] > 0 and self.boost_active and now - self.sky_boost_start < P['SkyBoostMinBurst']:
            want = True
        was = self.boost_active
        on = A.FlightModel.update_boost_server(self, want, dt, body, now)
        if on and not was:
            self.sky_boost_start = now
        return on

    def update_boost_client(self, want, replicated_fuel):
        P = self.P
        if P['SkyBoostMinBurst'] > 0 and self.local_boost_active and self.sky_clock - self.sky_local_boost_start < P['SkyBoostMinBurst']:
            want = True
        was = self.local_boost_active
        on = A.FlightModel.update_boost_client(self, want, replicated_fuel)
        if on and not was:
            self.sky_local_boost_start = self.sky_clock
        return on

    # ------------------------------------------------------------------------------------------------ shaping (every machine)
    def shape_controls(self, controls, dt, fwd_speed):
        P = self.P
        self.sky_clock += dt
        raw_steer = controls.get_steer()
        brake_btn = controls.has(BUTTON_BRAKE)
        self.b_aiming = controls.has(BUTTON_AIM)
        thr_raw = controls.get_throttle()
        self.sky_turbo_event = 0

        if P['bSkyDrift']:
            # ---- drift state machine (Sky Racer) ---------------------------------------------------------------
            if self.sky_drift_dir == 0:
                if brake_btn and abs(raw_steer) >= P['SkyDriftEnterSteer'] and fwd_speed >= P['SkyDriftEnterSpeed']:
                    self.sky_drift_dir = 1 if raw_steer > 0 else -1
                    self.sky_charge = 0.0
                    self.sky_drift_t = 0.0
                    linked = self.sky_clock - self.sky_last_release <= P['SkyChainWindow']
                    self.sky_chain = min(self.sky_chain + 1, int(P['SkyChainMax'])) if linked else 0
            else:
                if (not brake_btn) or fwd_speed < P['SkyDriftExitSpeed']:
                    # the server gives a remote pilot a little grace (packet timing can cost its copy 1-2 frames)
                    grace = P['SkyTierGrace'] if (self.authority and self.sim.net == 'client') else 0.0
                    tier = _tier(P, self.sky_charge + grace)
                    if tier > 0 and fwd_speed >= P['SkyDriftExitSpeed']:
                        self.sky_turbo_tier = tier
                        self.sky_turbo_total = max(P['SkyTurboTime%d' % tier], 1e-3)
                        self.sky_turbo_left = self.sky_turbo_total
                        self.sky_turbo_event = tier
                        self.sky_turbo_chain = self.sky_chain
                        self.sky_last_release = self.sky_clock
                        self.sky_last_tier = tier
                        self.sky_releases.append((self.sky_clock, tier, self.sky_chain))
                    else:
                        self.sky_chain = 0
                        self.sky_last_tier = 0
                    self.sky_drift_dir = 0
                    self.sky_charge = 0.0
                    self.sky_exit_left = P['SkyDriftExitTime']
                else:
                    s_in = clamp(raw_steer * self.sky_drift_dir, -1.0, 1.0)
                    rate = lerp(P['SkyChargeRateMin'], P['SkyChargeRateMax'], 0.5 * (s_in + 1.0))
                    self.sky_charge = min(1.0, self.sky_charge + rate * dt)
                    self.sky_drift_t += dt
            if self.sky_turbo_left > 0:
                self.sky_turbo_left = max(0.0, self.sky_turbo_left - dt)
            if self.sky_exit_left > 0 and self.sky_drift_dir == 0 and not self.sky_turbo_event:
                self.sky_exit_left = max(0.0, self.sky_exit_left - dt)
            drifting = self.sky_drift_dir != 0
        else:
            drifting = brake_btn and abs(raw_steer) > P['DriftSteerThreshold'] and fwd_speed > P['DriftMinSpeed']

        # ---- brake: X (not drifting), or S above SkySBrakeSpeed (analog) ----------------------------------------
        s_target = -thr_raw if (not drifting and thr_raw < 0 and P['SkySBrakeSpeed'] > 0 and fwd_speed > P['SkySBrakeSpeed']) else 0.0
        self.sky_sbrake = approach_ud(self.sky_sbrake, s_target, dt, P['SkySBrakeTauUp'], P['SkySBrakeTauDown'])
        if s_target <= 0.0 and self.sky_sbrake < 0.02:
            self.sky_sbrake = 0.0
        brake_amt = 1.0 if (brake_btn and not drifting) else (self.sky_sbrake if not drifting else 0.0)
        self.sky_brake_amount = brake_amt
        brake = brake_amt > 0.0
        thr_target = thr_raw
        if drifting and P.get('SkyDriftThrottle', 0.0) > 0 and thr_raw >= 0.0:
            # REVIEW: a drift drives at SkyDriftThrottle (full power) unless S is held, so the keyboard chord is A or D
            # + X (W optional) and a gamepad stick held sideways still drifts at full drive; S + X + A/D still slows
            thr_target = max(thr_target, P['SkyDriftThrottle'])
        if brake:
            if P['BrakeFadeSpeed'] > 0:   # base fix 4c-2
                fade = clamp(fwd_speed / P['BrakeFadeSpeed'], 0.0, 1.0)
            else:
                fade = 1.0 if fwd_speed > 100.0 else 0.0
            thr_target = -P['BrakeReverseThrottle'] * brake_amt * fade
        boost = controls.has(BUTTON_BOOST)
        targets = dict(throttle=thr_target, boost=1.0 if boost else 0.0, lift=controls.get_lift(), steer=raw_steer,
                       strafe=controls.get_strafe(), brake=brake, drifting=drifting)
        self.scheme.shaping_targets(self.sim, self, controls, targets, fwd_speed)
        self.b_brake, self.b_drifting = targets['brake'], targets['drifting']
        self.sh_throttle = approach_ud(self.sh_throttle, targets['throttle'], dt, P['ThrottleTauUp'], P['ThrottleTauDown'])
        self.sh_boost = approach(self.sh_boost, targets['boost'], dt, P['BoostTauUp'] if targets['boost'] > 0.5 else P['BoostTauDown'])
        lt = targets['lift']
        tau = P['LiftTau']
        if P['LiftTauRelease'] > 0 and abs(lt) < abs(self.sh_lift) and lt * self.sh_lift >= 0:   # base fix 4b-3
            tau = P['LiftTauRelease']
        self.sh_lift = approach(self.sh_lift, lt, dt, tau)
        self.sh_steer = approach(self.sh_steer, targets['steer'], dt, P['SteerTau'])
        self.sh_strafe = approach(self.sh_strafe, targets['strafe'], dt, P['StrafeTau'])

    def sky_turbo_alpha(self):
        return self.sky_turbo_left / self.sky_turbo_total if self.sky_turbo_left > 0 else 0.0

    def sky_s_in(self):
        """Steer into the drift (-1 counter-steer .. +1 full in), from the shaped steer."""
        return clamp(self.sh_steer * self.sky_drift_dir, -1.0, 1.0) if self.sky_drift_dir else 0.0

    def compute_gimbals(self):
        out = A.FlightModel.compute_gimbals(self)
        P = self.P
        if P['bSkyDrift'] and self.sky_drift_dir and P['SkyDriftGimbalRollDeg'] > 0:
            mx = max(P['ThrusterGimbalMaxDeg'], 0.0)
            res = []
            for (p_, r_) in out:
                r_ = clamp(r_ + P['SkyDriftGimbalRollDeg'] * self.sky_drift_dir, -mx, mx)
                tot = math.hypot(p_, r_)
                if tot > mx and tot > 1e-6:
                    p_ *= mx / tot
                    r_ *= mx / tot
                res.append((p_, r_))
            out = res
        return out

    # ------------------------------------------------------------------------------------------------ forces (server)
    def apply_forces(self, body, dt, now):
        """airship_sim.FlightModel.apply_forces (8f01bca port) + base fixes + Sky Racer. Changed lines are marked."""
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
        cur_yaw = quat2rot(q)[1]
        sky = P['bSkyDrift']
        sky_drift = sky and self.sky_drift_dir != 0
        s_in = self.sky_s_in()
        s01 = 0.5 * (s_in + 1.0)

        # ---- commands ----------------------------------------------------------------------------------------------
        AFanEff = lerp(P['AFan'], P['AFanBoost'], Boost)
        VTopEff = max(lerp(P['VTop'], P['VTopBoost'], Boost), 1.0)
        # [Sky] in a drift the thrust fade and the drag use the whole horizontal speed (the slide is not free speed)
        VSpeed = math.hypot(V[0], V[1])
        VFade = VSpeed if sky_drift else Vf
        if Throttle >= 0:
            AFanCmd = AFanEff * Throttle * max(0.0, 1.0 - (max(VFade, 0.0) / VTopEff) ** P['ThrustFadeExponent'])
        else:
            ARev = P['AFan'] if (brake and not drifting) else P['AFanRev']
            AFanCmd = ARev * Throttle * max(0.0, 1.0 - (max(-Vf, 0.0) / max(P['VTopRev'], 1.0)) ** 2)
        ADrag = -(P['DragC1'] * Vf + P['DragC2'] * Vf * abs(Vf))
        ADragPath = 0.0
        if sky_drift:
            # [Sky] drag along the velocity (+ a scrub that grows with the slip) in place of v1's drag along the hull
            sin_slip = abs(qunrot(q, (V[0], V[1], 0.0))[1]) / max(VSpeed, 1.0)
            ADragPath = -(P['DragC1'] * VSpeed + P['DragC2'] * VSpeed * VSpeed + P['SkyDriftScrub'] * VSpeed * sin_slip)
            ADrag = ADragPath * math.sqrt(max(0.0, 1.0 - sin_slip * sin_slip))   # its share along the hull (pitch lean)
        # [Sky] analog brake amount, capped air brake (SkyBrakeAccelMax 0 = v1: no cap)
        if brake:
            ab = P['Kbrake'] * Vf * (P['DriftBrakeScale'] if drifting else 1.0)
            if P['SkyBrakeAccelMax'] > 0:
                ab = clamp(ab, -P['SkyBrakeAccelMax'], P['SkyBrakeAccelMax'])
            ABrake = -ab * (self.sky_brake_amount if sky else 1.0)
        else:
            ABrake = 0.0

        # vertical, with base fixes 4b / 4c
        brake_pressed = brake and not self.brake_was
        self.brake_was = brake
        hba = P['HoldBrakeAccel']
        stop_lead = (lambda vz: vz * abs(vz) / (2.0 * hba)) if hba > 0 else (lambda vz: vz * P['HoldCaptureLead'])
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
            if hba > 0:
                VzCmd = math.copysign(min(abs(VzCmd), math.sqrt(2.0 * hba * abs(e))), e) if e != 0 else 0.0
            VzCmd = clamp(VzCmd, -P['HoldMaxSpeed'], P['HoldMaxSpeed'])
        if P['MinClearance'] > 0 and self.min_ground >= 0:
            VzCmd = max(VzCmd, P['Kfloor'] * (P['MinClearance'] - self.min_ground))
            if P['FloorBrakeAccel'] > 0:
                VzCmd = max(VzCmd, -math.sqrt(2 * P['FloorBrakeAccel'] * max(self.min_ground - P['MinClearance'], 0.0)))
        if P['bUseCeiling']:
            VzCmd = min(VzCmd, P['Kceil'] * (P['CeilingZ'] - Z))

        if sky_drift:
            # [Sky] the bank follows the drift direction (counter-steer only shallows it), not the momentary steer
            BankDeg = P['SkyDriftBankDeg'] * self.sky_drift_dir * lerp(0.7, 1.0, s01) * \
                clamp(Vf / max(P['BankFullSpeed'], 1.0), P['BankMinFraction'], 1.0) + P['StrafeBankDeg'] * Strafe
        else:
            BankMax = P['BankMaxDriftDeg'] if drifting else lerp(P['BankMaxDeg'], P['BankMaxBoostDeg'], Boost)
            BankDeg = BankMax * Steer * clamp(Vf / max(P['BankFullSpeed'], 1.0), P['BankMinFraction'], 1.0) + P['StrafeBankDeg'] * Strafe
        if self.b_aiming:
            BankDeg *= P['SkyAimBankScale']   # [Sky] steady deck while aiming (1 = v1)

        AbsVf = abs(Vf)
        if AbsVf <= P['YawRateMidSpeed']:
            RmaxDeg = lerp(P['YawRateAtRest'], P['YawRateAtMid'], AbsVf / max(P['YawRateMidSpeed'], 1.0))
        else:
            RmaxDeg = lerp(P['YawRateAtMid'], P['YawRateAtTop'],
                           clamp((AbsVf - P['YawRateMidSpeed']) / max(P['YawRateTopSpeed'] - P['YawRateMidSpeed'], 1.0), 0.0, 1.0))
        RmaxDeg = P['YawRateDrift'] if drifting else lerp(RmaxDeg, P['YawRateBoost'], Boost)
        YawRateCmd = Steer * RmaxDeg * D2R
        Course = math.atan2(V[1], V[0]) if math.hypot(V[0], V[1]) > 100.0 else cur_yaw * D2R
        SlipNow = wrap180(cur_yaw - Course * R2D)          # deg, + = nose right of the velocity
        PathRate = 0.0
        if sky_drift:
            # [Sky] the steer sets the PATH turn rate (counter-steer SkyDriftPathRateMinDeg .. full in ..MaxDeg); the
            # yaw loop swings the nose in to hold the slip angle on top of it
            PathRate = self.sky_drift_dir * lerp(P['SkyDriftPathRateMinDeg'], P['SkyDriftPathRateMaxDeg'], s01) * D2R
            SlipTarget = self.sky_drift_dir * lerp(P['SkyDriftSlipMinDeg'], P['SkyDriftSlipMaxDeg'], s01)
            ymax = P['SkyDriftYawRateMaxDeg'] * D2R
            YawRateCmd = clamp(PathRate + P['SkyDriftSlipGain'] * (SlipTarget - SlipNow) * D2R, -ymax, ymax)
            RmaxDeg = abs(YawRateCmd) * R2D
            # turn-in first, then the tail steps out: the path turns no faster than the hull plus what the slip it
            # already has allows (SkyDriftSlipGain per rad of slip), so the nose never trails the velocity
            PathRate = self.sky_drift_dir * min(abs(PathRate), max(0.0, AngVel[2] * self.sky_drift_dir + P['SkyDriftPathLeadDeg'] * D2R +
                                                                    P['SkyDriftSlipGain'] * max(0.0, SlipNow * self.sky_drift_dir) * D2R))
        elif sky and self.sky_exit_left > 0:
            # [Sky] drift exit: the nose swings back part of the slip while the grip pulls the path onto the nose
            YawRateCmd -= P['SkyDriftExitYawGain'] * SlipNow * D2R

        Klat = P['DriftKlat'] if drifting else lerp(P['GripKlat'], P['BoostKlat'], Boost)
        ALatMax = (P['DriftALatMaxG'] if drifting else lerp(P['GripALatMaxG'], P['BoostALatMaxG'], Boost)) * Gravity
        Eta = P['DriftEta'] if drifting else lerp(P['GripEta'], P['BoostEta'], Boost)
        VlTarget = Strafe * P['StrafeSpeed']

        if self.b_aiming and not sky_drift:
            # [Sky] gun deck: gentler throttle, brake and turn while aiming (1 = v1)
            AFanCmd *= P['SkyAimThrottleScale'] if AFanCmd > 0 else 1.0
            ABrake *= P['SkyAimBrakeScale']
            YawRateCmd *= P['SkyAimYawScale']
            RmaxDeg *= P['SkyAimYawScale']
        cmd = dict(AFanCmd=AFanCmd, ADrag=ADrag, ABrake=ABrake, VzCmd=VzCmd, BankDeg=BankDeg, RmaxDeg=RmaxDeg,
                   YawRateCmd=YawRateCmd, Klat=Klat, ALatMax=ALatMax, Eta=Eta,
                   VlTarget=VlTarget, PitchExtraDeg=0.0, Vf=Vf, Vl=Vl, Vz=Vz, Z=Z,
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
        # base fix 4b-1: hidden vertical brake while vz runs past the command in its own direction
        AVert = 0.0
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
        AlphaYawMax = P['SkyDriftAlphaYawMax'] if sky_drift else P['AlphaYawMax']
        AlphaZ = clamp(P['Kr'] * (YawRateCmd - YawRate) + P['AngularDamping'] * YawRateCmd, -AlphaYawMax, AlphaYawMax)
        if self.ctrl_mode == 'hull':
            T = A.TENSOR_ACTOR
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
        Psi = (-P['FanYawMaxDeg'] * Steer) * D2R
        FanDir = (1.0, math.tan(Psi), 0.0)
        FanMaxF = lerp(P['FanMax'], P['FanMaxBoost'], Boost) * W
        TauFan = (0.0, 0.0, 0.0)
        if yc is not None:
            Col = [Am[0][i] * yc[0] + Am[1][i] * yc[1] + Am[2][i] * yc[2] for i in range(4)]
            if P['bFanTorqueFeedForward']:
                # base fix 4a-2: the fans' estimated forward total, its roll / pitch torque at the fan points
                TotalEst = clamp(Mass * AFanCmd - sum(Col[i] * PodDir[i][0] for i in range(4)), -2 * FanMaxF, 2 * FanMaxF)
                for j in range(2):
                    TauFan = add(TauFan, cross(sub(A.FAN_LOCAL[j], COMLocal), mul(FanDir, 0.5 * TotalEst)))
        ya = solve3(M, [0.0, TauX - TauFan[0], TauY - TauFan[1]])
        if yc is not None and ya is not None:
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

        # ---- fans --------------------------------------------------------------------------------------------------
        KL = cross(sub(A.FAN_LOCAL[0], COMLocal), FanDir)[2]
        KR = cross(sub(A.FAN_LOCAL[1], COMLocal), FanDir)[2]
        KDiff = 0.5 * (KL - KR)
        Total = clamp(Mass * AFanCmd - PodSum[0], -2 * FanMaxF, 2 * FanMaxF)
        RudCap = min(P['RudderAuthority'] * (Vf / max(P['RudderRefSpeed'], 1.0)) ** 2, P['RudderMaxAlpha']) * \
            (1.0 if sky_drift else abs(Steer))   # [Sky] a drift turns with the rudder whatever the steer
        RudderAlpha = clamp(AlphaZ - (PodTauZ + 0.5 * Total * (KL + KR)) / Izz, -RudCap, RudCap) if Izz > 1e-4 else 0.0
        TauKnown = PodTauZ + 0.5 * Total * (KL + KR) + Izz * RudderAlpha
        DMax = max(0.0, 2 * FanMaxF - abs(Total))
        D = clamp((TauZ - TauKnown) / KDiff, -DMax, DMax) if abs(KDiff) > 1 else 0.0
        FanF = [0.5 * Total + 0.5 * D, 0.5 * Total - 0.5 * D]
        AlphaGyroZ = clamp((TauZ - TauKnown - KDiff * D) / Izz, -P['GyroYawMax'], P['GyroYawMax']) if Izz > 1e-4 else 0.0

        # ---- lateral grip, strafe, drift ----------------------------------------------------------------------------
        APath = 0.0
        PathN = (0.0, 0.0, 0.0)
        if sky_drift:
            # [Sky] path force: level, perpendicular to the velocity, sized to turn it at PathRate (no work done:
            # the drift keeps its speed apart from the thrust now pointing SlipNow off the path); the physical
            # forces' share along it comes off, the rest is hidden, capped at SkyDriftALatMaxG
            vh = math.hypot(V[0], V[1])
            PathN = (-V[1] / vh, V[0] / vh, 0.0) if vh > 1.0 else Right
            phys = add(add(PodWorld[0], PodWorld[1]), add(PodWorld[2], PodWorld[3]))
            for j in range(2):
                phys = add(phys, qrot(q, mul(FanDir, FanF[j])))
            APath = clamp(PathRate * vh - dot(phys, PathN) / Mass, -P['SkyDriftALatMaxG'] * Gravity, P['SkyDriftALatMaxG'] * Gravity)
            ALatCmd = 0.0
            keep = 0.0
        else:
            if sky and self.sky_exit_left > 0:
                # [Sky] drift exit snap: the slide straightens out fast (the scrubbed speed comes back forward)
                Klat = max(Klat, P['SkyDriftExitKlat'])
                ALatMax = max(ALatMax, P['SkyDriftExitALatMaxG'] * Gravity)
            # [Sky] centripetal feed-forward (0 = v1): a planted carve with a small, steady slip
            ALatCmd = clamp(P['SkyGripCentripetalFF'] * YawRate * max(Vf, 0.0) + Klat * (VlTarget - Vl), -ALatMax, ALatMax)
            keep = P['SkyGripEnergyKeep']
        ALatPhys = (PodSum[1] + (FanF[0] + FanF[1]) * FanDir[1]) / Mass
        AGrip = 0.0 if sky_drift else ALatCmd - ALatPhys
        if sky_drift:
            ARedirect = 0.0
        elif keep > 0:
            # [Sky] give back `keep` of the energy the side force scrubs (power -a_lat * vl), along Fwd
            ARedirect = keep * max(0.0, -ALatCmd * Vl) / max(Vf, 500.0) if Vf > P['RedirectMinSpeed'] else 0.0
        else:
            ARedirect = Eta * abs(AGrip) if (Vf > P['RedirectMinSpeed'] and AGrip * Vl < 0) else 0.0
        drift_kick = 0.0
        if not sky:
            if drifting:
                self.drift_time += dt
            else:
                if self.drift_time >= P['DriftBoostMinTime'] and P['DriftBoostDV'] > 0:
                    body.add_impulse_vel(mul(Fwd, P['DriftBoostDV']))
                    drift_kick = P['DriftBoostDV']
                self.drift_time = 0.0

        # [Sky] mini-turbo: kick on release (NoteFlightKick in C++), boost fuel, then a burn that fades out
        ATurbo = 0.0
        if sky and self.sky_turbo_event:
            k = self.sky_turbo_event
            dv = P['SkyTurboKickDV%d' % k] * (1.0 + P['SkyChainBonus'] * min(self.sky_turbo_chain, int(P['SkyChainMax'])))
            body.add_impulse_vel(mul(Fwd, dv))
            drift_kick = dv
            self.fuel = min(P['BoostFuelMax'], self.fuel + P['SkyTurboFuel%d' % k])
        ta = self.sky_turbo_alpha() if sky else 0.0
        if ta > 0:
            ATurbo = P['SkyTurboAccel'] * ta * max(0.0, 1.0 - (max(Vf, 0.0) / max(P['SkyTurboVTop'], 1.0)) ** 4)
        # [Sky] diving turns height into speed
        ADive = 0.0
        if P['SkyDiveAccelPerSink'] > 0 and Lift <= -P['LiftDeadZone'] and Vz < 0 and Vf > P['SkyDiveMinSpeed']:
            ADive = P['SkyDiveAccelPerSink'] * -Vz
        # base fix 4d: station keeping at low speed with nothing held
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
            body.add_force_at_location(PodWorld[i], body.transform_position(A.POD_LOCAL[i]))
        for j in range(2):
            body.add_force_at_location(qrot(q, mul(FanDir, FanF[j])), body.transform_position(A.FAN_LOCAL[j]))
        RightGrip = Right
        if P['bSkyLevelGrip']:
            # [Sky] the hidden side force acts level (v1: along the banked right axis, which pulls a banked ship down)
            RightGrip = norm((-Fwd[1], Fwd[0], 0.0))
        FwdDrag = 0.0 if sky_drift else ADrag
        ACom = add(add(mul(RightGrip, AGrip), mul(Right, WindLat)), mul(Fwd, FwdDrag + ABrake + ARedirect + ATurbo + ADive + AKeepF))
        if sky_drift and VSpeed > 1.0:
            ACom = add(ACom, mul((V[0] / VSpeed, V[1] / VSpeed, 0.0), ADragPath))
        ACom = add(ACom, add(mul(PathN, APath), (0.0, 0.0, AVert)))
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
                          ATurbo=ATurbo, ADive=ADive, AVert=AVert, ALatCmd=ALatCmd, APath=APath, SlipNow=SlipNow, DriftDir=self.sky_drift_dir,
                          Charge=self.sky_charge, TurboTier=self.sky_turbo_event)


# =====================================================================================================================
@register_scheme
class SkyRacer(Classic):
    key = 'skyracer'
    enum = 2
    label = 'Sky Racer'
    ctrl_inertia = 'hull'     # base fix 4a-1 (bHullAxisInertia)

    flight = dict(BASE_FIX_V1, **SKY_FLIGHT_V1)
    flight.update(
        # ---- base fixes (BASELINE.md 4f), all on -------------------------------------------------------------------
        bFanTorqueFeedForward=True, VertBrakeAccel=1180.0, HoldBrakeAccel=1960.0, LiftTauRelease=0.06, bBrakeHoldLead=True,
        BrakeFadeSpeed=1000.0, StationKeepGain=1.0, StationKeepSpeed=300.0, StationKeepAccelMax=150.0,
        PitchPerG=4.5, PitchMinDeg=-5.0, PitchMaxDeg=4.0, BoostPitchDeg=1.5,
        # ---- forward: hard acceleration, higher top speed ------------------------------------------------------------
        AFan=1860.0, VTop=5900.0, ThrustFadeExponent=5.0, ThrottleTauUp=0.18, ThrottleTauDown=0.30,
        FanMax=0.95, FanMaxBoost=1.30, AFanBoost=2550.0, VTopBoost=10000.0,
        # ---- brake: S and X, capped (readable) ---------------------------------------------------------------------
        SkySBrakeSpeed=300.0, SkySBrakeTauUp=0.3, SkySBrakeTauDown=0.08, SkyBrakeAccelMax=1470.0, Kbrake=1.5,
        BrakeReverseThrottle=0.4,
        # ---- turn: fast, snappy bank, levels itself, planted (level grip, feed-forward, energy redirect) -------------
        SteerTau=0.09, Kr=4.5, AlphaYawMax=1.5, YawRateAtRest=34.0, YawRateAtMid=50.0, YawRateMidSpeed=1600.0,
        YawRateAtTop=38.0, YawRateTopSpeed=5600.0, YawRateBoost=30.0, RudderAuthority=0.9, RudderRefSpeed=5000.0,
        RudderMaxAlpha=1.6, GyroYawMax=0.6,
        KpRoll=9.0, KdRoll=5.4, BankMaxDeg=22.0, BankMaxBoostDeg=15.0, BankFullSpeed=1800.0, StrafeBankDeg=5.0,
        GripKlat=4.5, GripALatMaxG=4.0, BoostKlat=3.5, BoostALatMaxG=3.0,
        bSkyLevelGrip=True, SkyGripCentripetalFF=0.5, SkyGripEnergyKeep=0.85,   # GripEta / BoostEta unused (energy redirect)
        StrafeSpeed=1400.0, StrafeTau=0.14,
        # ---- vertical: punchy, stops where released --------------------------------------------------------------
        ClimbRate=1350.0, DescendRate=1650.0, LiftTau=0.12, Kvz=3.0, CollectiveMax=2.1, CollectiveMin=0.15,
        PodForceMax=0.62, LiftPitchDeg=4.0, MinClearance=500.0, Kfloor=2.0, SkyDiveAccelPerSink=0.06,
        # ---- boost: a burst per press ------------------------------------------------------------------------------
        BoostKickDV=600.0, BoostTauUp=0.08, BoostTauDown=0.45, BoostDrainRate=28.0, BoostRegenRate=10.0,
        BoostRegenDelay=1.2, BoostMinFuelToStart=18.0, SkyBoostMinBurst=0.5,
        # ---- drift + mini-turbo ------------------------------------------------------------------------------------
        bSkyDrift=True, SkyDriftThrottle=1.0, SkyAimBankScale=0.35, SkyAimThrottleScale=0.6, SkyAimBrakeScale=0.3, SkyAimYawScale=0.8,
        SkyDriftExitTime=0.4, SkyDriftExitKlat=8.0, SkyDriftExitALatMaxG=5.0,
    )
    pawn = dict(SKY_PAWN_V1)
    pawn.update(
        CameraArmLength=5400.0, CameraDefaultPitch=-8.0, CameraTargetOffsetZ=650.0, CameraRotationLagSpeed=10.0,
        CameraLagSpeed=6.5, RecenterDelay=0.6, RecenterMinSpeed=500.0, RecenterSpeed=4.0,
        BaseFOV=82.0, SpeedFOVExtra=18.0, SpeedFOVStart=1500.0, SpeedFOVFull=5500.0, BoostFOVExtra=14.0, AimFOVOffset=-14.0,
        SkyLookIntoTurnTime=0.3, SkyLookIntoTurnMaxDeg=14.0, SkyCamSlipShare=0.35, bSkyCamYawRateFF=True,
        SkyCamDivePitchPerMS=0.4, SkyCamRollShare=0.25, SkyShakeRotDeg=1.2, SkyFOVMax=112.0, SkyTurboArmExtra=600.0,
        # spec only (the bench has no FOV / arm / impact model): listed so this dict is the whole pawn preset
        FOVInterpSpeed=6.0, CameraBoostArmExtra=1200.0,
        ImpactMinSpeed=700.0, ImpactDamagePerMS=4.0, ImpactMaxDamage=350.0, ImpactCooldown=0.6, ImpactMaxSpinKickDeg=12.0,
        ImpactMaxSpeedGain=400.0, ImpactMaxReboundSpeed=120.0, ImpactEpisodeAccelUp=2650.0,
    )

    # bot gains: control gains from course.tune_bot's stage 1 (unchanged sweep and score), line keys from the same
    # stage 2 extended with turn_frac 1.0 / 1.1 and exit_lead (python3 skyracer_checks.py --tune); drift_on, drift_off,
    # drift_min_hold, drift_rearm from 5-seed sweeps; combat_* = Classic's heading gains for the broadside bot
    GAINS = dict(course=1.6, rate_damp=0.6, speed=0.25, alt=0.12, vz_damp=0.06, ct=0.5, lag=0.35, margin=5.0, turn_frac=1.1,
                 drift=1.0, drift_on=0.9, drift_off=0.8, drift_min_speed=22.0, exit_lead=0.9,
                 combat_course=0.7, combat_rate_damp=0.6, drift_min_hold=0.25, drift_rearm=0.6)

    # ---- runtime state ------------------------------------------------------------------------------------------
    def reset(self, sim):
        sim.pilot_state = {}
        sim.server_state = {}
        for fm in {id(sim.server): sim.server, id(sim.pilot_fm): sim.pilot_fm}.values():
            if not isinstance(fm, SkyFlightModel):
                fm.__class__ = SkyFlightModel
            fm.sky_reset()

    # ---- pilot's machine ------------------------------------------------------------------------------------------
    def camera(self, sim, raw, cam, view, dt):
        """Chase camera: auto-follow after RecenterDelay without look input (not aiming), aimed at the ship's yaw
        + look-into-turn (from the pilot's own commanded turn rate, so it answers in the same frame even for a lagged
        client) - a share of the slip (the slide reads), the control yaw fed forward with that commanded rate, and
        the pitch dipping on a dive. Free look with the mouse / right stick as in Classic."""
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
        auto = now - cam.last_look_time > PP['RecenterDelay'] and fwd > PP['RecenterMinSpeed'] and not raw.aim
        if auto and PP['RecenterSpeed'] > 0:
            rate = self.local_rate_cmd(sim, view)
            look = clamp(PP['SkyLookIntoTurnTime'] * rate, -PP['SkyLookIntoTurnMaxDeg'], PP['SkyLookIntoTurnMaxDeg'])
            vf, vl = view['ForwardSpeedMS'], view['LateralSpeedMS']
            slip = math.atan2(-vl, vf) * R2D if vf > 3.0 else 0.0
            target_yaw = view['YawDeg'] + look - PP['SkyCamSlipShare'] * slip
            dive = max(0.0, -view['VerticalSpeedMS'])
            target_pitch = PP['CameraDefaultPitch'] - min(PP['SkyCamDivePitchPerMS'] * dive, PP['SkyCamDivePitchMaxDeg'])
            if PP['bSkyCamYawRateFF']:
                cam.control_yaw += rate * dt
            a = 1.0 - math.exp(-PP['RecenterSpeed'] * dt)
            cam.control_yaw += wrap180(target_yaw - cam.control_yaw) * a
            cam.control_pitch += (target_pitch - cam.control_pitch) * a
        cam.control_yaw = wrap180(cam.control_yaw)
        cam.control_pitch = clamp(cam.control_pitch, PP['CameraPitchMin'], PP['CameraPitchMax'])
        self.camera_lag(sim, cam, dt)
        cam.free_look = True

    def local_rate_cmd(self, sim, view):
        """The turn rate the pilot's own controls command right now (deg/s), from its shaped steer / drift state."""
        fm = sim.pilot_fm
        P = sim.P
        if fm.sky_drift_dir:
            return fm.sky_drift_dir * lerp(P['SkyDriftPathRateMinDeg'], P['SkyDriftPathRateMaxDeg'], 0.5 * (fm.sky_s_in() + 1.0))
        r = sim.rmax_deg(view['ForwardSpeed'])
        r = lerp(r, P['YawRateBoost'], fm.sh_boost)
        return fm.sh_steer * r

    def telemetry(self, sim, tele):
        Classic.telemetry(self, sim, tele)
        fm = sim.server
        tele['Scheme'] = self.enum
        tele['DriftCharge'] = getattr(fm, 'sky_charge', 0.0)
        tele['DriftDir'] = getattr(fm, 'sky_drift_dir', 0)
        tele['TurboAlpha'] = fm.sky_turbo_alpha() if hasattr(fm, 'sky_turbo_left') else 0.0
        tele['TurboChain'] = getattr(fm, 'sky_chain', 0)

    # ---- bench adapters ------------------------------------------------------------------------------------------
    def command_raw(self, sim, cmd):
        """Same keys as Classic: forward = W, brake = X, drift = X + steer (+ W), boost = Shift."""
        return Classic.command_raw(self, sim, cmd)

    def intent_raw(self, sim, intent, view, gains=None):
        """Bots: Classic's course / speed / height loops with Sky Racer's turn table and S as the brake, plus the drift:
        X + full steer when the line ahead (yaw_rate_ff) needs more than drift_on x the grip rate above
        drift_min_speed; in the drift the steer maps the needed rate onto the drift's path-rate range; X is let go
        (mini-turbo) when the line ahead drops under drift_off x the slowest drift rate or the course still to turn is
        down to exit_lead x the slip (the exit swing finishes the turn). A press lasts at least drift_min_hold s and
        is not repeated within drift_rearm s (no X chatter). Broadside (look_at set): aim held (gun deck), no drift,
        the gentler combat heading gains."""
        g = dict(self.GAINS)
        if gains:
            g.update(gains)
        P = sim.P
        fm = sim.pilot_fm
        course = view['CourseDeg'] if view['SpeedMS'] > 3.0 else view['YawDeg']
        err = wrap180(intent.course_deg - course)
        vf = view['ForwardSpeedMS']
        rmax = sim.rmax_deg(vf * 100.0)
        combat = intent.look_at is not None
        if combat:
            # lining up a broadside (aim held): the gentle heading gains of the steady-deck mode
            g['course'] = g['combat_course'] * g['course'] / self.GAINS['course']           # keeps the sloppy bot's noise
            g['rate_damp'] = g['combat_rate_damp'] * g['rate_damp'] / self.GAINS['rate_damp']
        rate_des = g['course'] * err + intent.yaw_rate_ff
        drifting = fm.sky_drift_dir != 0
        brake_btn = False
        ymin, ymax = P['SkyDriftPathRateMinDeg'], P['SkyDriftPathRateMaxDeg']
        ffr = intent.yaw_rate_ff
        bot = sim.pilot_state.setdefault('bot', dict(held=0.0, free=10.0))
        if g.get('drift', 0) and not combat:
            if not drifting:
                # the line ahead needs more than the grip turn: drift into it (a human commits to a corner: no
                # re-press within drift_rearm s of a release)
                if abs(ffr) > g['drift_on'] * rmax and vf > g['drift_min_speed'] and rate_des * ffr > 0 and bot['free'] >= g['drift_rearm']:
                    brake_btn = True
                    drifting = True
                    dir_ = 1 if ffr > 0 else -1
                    steer = float(dir_)
            else:
                dir_ = fm.sky_drift_dir
                need = rate_des * dir_
                # let go (turbo) when the line ahead is back under drift_off x the drift's widest rate, or the course
                # still to turn is down to exit_lead x the slip (the exit swing finishes the turn)
                slip = math.atan2(-view['LateralSpeedMS'], max(vf, 1.0)) * R2D * dir_
                exit_now = ffr * dir_ < g['drift_off'] * ymin or err * dir_ < g['exit_lead'] * max(slip, 0.0)
                if bot['held'] < g['drift_min_hold']:
                    exit_now = False
                if not exit_now:
                    brake_btn = True
                    s_in = clamp(2.0 * (need - ymin) / max(ymax - ymin, 1.0) - 1.0, -1.0, 1.0)
                    steer = dir_ * s_in
                else:
                    drifting = False
        if brake_btn:
            bot['held'] += sim.dt
            bot['free'] = 0.0
        else:
            bot['held'] = 0.0
            bot['free'] += sim.dt
        if not drifting or not brake_btn:
            rate = clamp(rate_des, -rmax, rmax)
            steer = clamp((rate + g['rate_damp'] * (rate - view['YawRateDegS'])) / max(rmax, 1.0), -1.0, 1.0)
            brake_btn = False
        # speed: S is the brake (X would drift); a drift keeps the throttle
        if intent.speed is None or brake_btn:
            thr = 1.0
        else:
            ev = intent.speed - vf
            hold = sim.hold_throttle(intent.speed * 100.0)
            thr = clamp(hold + g['speed'] * ev, -1.0, 1.0)
            if ev < -8.0 or intent.brake_hint and ev < -2.0:
                thr = -1.0
        lift = 0.0
        if intent.alt is not None:
            ez = intent.alt - view['AltitudeM']
            lift = clamp(g['alt'] * ez - g['vz_damp'] * view['VerticalSpeedMS'], -1.0, 1.0)
            if abs(lift) < P['LiftDeadZone'] * 1.2:
                lift = 0.0
        r = RawInput(throttle=thr, steer=steer, lift=lift, brake=brake_btn, aim=combat)
        self.look(sim, r, intent, view)
        return r
