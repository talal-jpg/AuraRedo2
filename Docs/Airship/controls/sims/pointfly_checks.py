"""Point & Fly checks beyond M1-M12 (Docs/Airship/controls/SCHEME_POINTFLY.md section 9). Bench: airship_sim.py.

    python3 pointfly_checks.py            -> all checks, prints tables, writes pointfly_checks.json (about 3 min)
    python3 pointfly_checks.py steps      -> one check: steps sweeps drift pass mouse keys pitch latency charge
                                             exit kick park push rival m12cam

  steps    camera snaps of 2-150 deg at cruise and at hover, host and client (100 ms each way); the hover pivot with the
           parked free look off (PFParkSpeed 0: at rest a pivot starts with a drive / turn key, see "park")
  sweeps   the camera swept at 10 / 20 / 30 deg/s for 3 s, then stopped
  drift    90 / 180 deg reversals at cruise: plain turn, S-brake turn, brake-drift
  pass     a broadside on a target 100 m off the track while racing past it: gun lock on / off, Classic
  mouse    the gate course flown by the sloppy bot with a human-like mouse: hand overshoot, jitter, glances
  keys     the gate course with keys only (Q/E turn the heading target): no mouse
  pitch    camera pitch -> climb (PFPitchClimb) on the course, and what glances down do with it
  latency  frames from the input to the camera, cosmetics and hull, host and client
  charge   a target dead ahead: swing the broadside onto it with a plain turn or a drift (the drift broadside); the
           pilot holds Fire while aiming (polish: the gun lock is armed by Fire, PFLockArmTime)
  Polish after judging (2026-11-23, SCHEME_POINTFLY.md "Review changes"):
  exit     the PIE m9 drift exit (3 s brake-drift, then the camera set once to yaw + rate x 0.3 s): overshoot / settle
  kick     the judge's drift-kick snake (1.23 s brake-drifts, camera +-90 deg) vs W held, and the 180 deg brake-drift
           reversal, with the kick cap (DriftBoostCapSpeed) on and off
  park     a 360 deg camera orbit in 4 s at hover with no keys (a new pilot looking at the ship), then a look 120 deg
           right and W: the parked free look on (default) and off
  push     follow-up F-B: parked at hover with the camera 120 deg right, a hit pushes the ship +6 m/s along the bow and
           knocks it 70 deg/s round, no key: the heading holds (the hull comes back), then W takes the camera yaw;
           the polish build (a push past PFParkSpeed ended parking) against the latch (scheme_pointfly.PARK_LATCH)
  rival    racing at cruise, Aim held 3 s on a rival 60 / 120 deg off the bow without firing: heading swing, track offset
  m12cam   M12 with the spring arm's position lag added to the bench camera, calibrated on the PIE frames (lag speeds
           4 / 5 /s fit the recorded camera within 0.05 m): the bot that aims the control rotation (both harnesses) and a
           hand that keeps the crosshair (the lagged view) on the target, at PFLockLeadTime 0.45 / 0.6 / 0.75

The sloppy-mouse model (check "mouse") is mine, not the bench's: the bench's sloppy bot plays keys on/off but moves the
camera as an analog, smooth signal, which flatters any camera-steered scheme. Here the hand is a second-order system
(natural frequency 7.5 rad/s, damping 0.45: about 20 % overshoot on a flick), with 1.5 + 0.8 deg of Perlin jitter and
"glances": every 6-10 s the player looks 25-50 deg aside and 15 deg down for 0.5-0.9 s (without or with Aim held).
"""
import json
import math
import os
import random
import sys

import airship_sim as A
from airship_sim import Sim, Command, RawInput, Intent, run_commands, run_raw, load_scheme, wrap180, clamp, DT, R2D, D2R
import course
import metrics
import scheme_pointfly as PF

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = {}


def cruise(key='pointfly', lat=0.0, **kw):
    s = Sim(load_scheme(key), latency_ms=lat, alt_agl=60, **kw)
    run_commands(s, lambda t, x: Command(), 2.0)
    run_commands(s, lambda t, x: Command(thrust=1.0), 15.0)
    return s


def hover(key='pointfly', lat=0.0, **kw):
    s = Sim(load_scheme(key), latency_ms=lat, alt_agl=60, **kw)
    run_commands(s, lambda t, x: Command(), 4.0)
    return s


def settle_time(err, tol):
    return next((round(i * DT, 2) for i in range(len(err)) if all(abs(e) < tol for e in err[i:])), None)


# ---------------------------------------------------------------------------------------------------------------------
def check_steps():
    rows = []
    for where in ('cruise', 'hover'):
        for lat in (0.0, 100.0):
            for dh in (2.0, 10.0, 45.0, 90.0, 150.0):
                # the hover pivot itself (with the parked free look on, a camera set alone doesn't turn a ship at rest)
                s = cruise(lat=lat) if where == 'cruise' else hover(lat=lat, pawn=dict(PFParkSpeed=0.0))
                y0 = s.tele()['YawDeg']
                tgt = wrap180(y0 + dh)
                thr = 1.0 if where == 'cruise' else 0.0
                lg = run_raw(s, lambda t, x: RawInput(throttle=thr, cam_yaw=tgt, look=True), 8.0)
                err = [wrap180(tgt - r['YawDeg']) for r in lg]
                tol = 0.25 if dh <= 3 else 0.5
                rpk = max(r['YawRateDegS'] for r in lg)
                rows.append(dict(where=where, lat_ms=lat, step_deg=dh, settle_s=settle_time(err, tol), tol_deg=tol,
                                 overshoot_deg=round(max(0.0, -min(err)), 2), peak_rate_degs=round(rpk, 1),
                                 t63_rate_s=next((round((i + 1) * DT, 2) for i, r in enumerate(lg) if r['YawRateDegS'] >= 0.63 * rpk), None),
                                 peak_bank_deg=round(max(r['RollDeg'] for r in lg), 1),
                                 wheel_max_deg=round(max(abs(r['pilot']['WheelAngleDeg']) for r in lg)),
                                 fan_yaw_max_deg=round(max(abs(r['pilot']['TurbineYawDeg']) for r in lg), 1)))
    print('steps: camera snap -> settle (s) / overshoot (deg) / peak turn rate / bank')
    for r in rows:
        print('  %-6s %3d ms %5.0f deg: settle %5s s (+-%.2f)  over %.2f  rate %5.1f (t63 %s s)  bank %4.1f  wheel %4d  fans %4.1f' % (
            r['where'], r['lat_ms'], r['step_deg'], r['settle_s'], r['tol_deg'], r['overshoot_deg'], r['peak_rate_degs'],
            r['t63_rate_s'], r['peak_bank_deg'], r['wheel_max_deg'], r['fan_yaw_max_deg']))
    OUT['steps'] = rows


def check_sweeps():
    rows = []
    for lat in (0.0, 100.0):
        for rate in (10.0, 20.0, 30.0):
            s = cruise(lat=lat)
            y0 = s.tele()['YawDeg']
            T = 3.0
            lg = run_raw(s, lambda t, x: RawInput(throttle=1.0, cam_yaw=wrap180(y0 + rate * min(t, T)), look=True), T + 5.0)
            lag = [wrap180(y0 + rate * min((i + 1) * DT, T) - r['YawDeg']) for i, r in enumerate(lg)]
            n = int(T / DT)
            rows.append(dict(lat_ms=lat, sweep_degs=rate, lag_deg=round(sum(lag[n - 30:n]) / 30, 1),
                             overshoot_deg=round(max(0.0, -min(lag[n:])), 2), settle_after_stop_s=settle_time(lag[n:], 0.5)))
    print('sweeps: camera swept for 3 s then stopped -> hull lag during the sweep, overshoot after the stop')
    for r in rows:
        print('  %3d ms %4.0f deg/s: lag %5.1f deg  overshoot %.2f deg  settled %s s after the stop' % (
            r['lat_ms'], r['sweep_degs'], r['lag_deg'], r['overshoot_deg'], r['settle_after_stop_s']))
    OUT['sweeps'] = rows


def check_drift():
    """Reversals at cruise, camera flicked onto the new heading: plain turn at full drive, S held until 30 m/s then W
    (brake-turn), and the brake-drift (X held while the hull slides; let go when the slide ends)."""
    rows = []
    for dh in (90.0, 179.0):
        for mode in ('turn', 'brake-turn', 'drift'):
            for lat in (0.0, 100.0):
                s = cruise(lat=lat)
                t0 = s.tele()
                y0 = t0['YawDeg']
                p0 = t0['ActorLocCm']
                right0 = (-math.sin(y0 * D2R), math.cos(y0 * D2R))
                tgt = wrap180(y0 + dh)
                st = {'released': False, 'slow': False}

                def sched(t, x):
                    b, thr = False, 1.0
                    if mode == 'drift':
                        b = not st['released'] and (t < 0.2 or x.pilot_state['loop'].get('drift', False))
                        if not b:
                            st['released'] = True
                    elif mode == 'brake-turn':
                        if not st['slow'] and x.tele()['ForwardSpeedMS'] > 30.0:
                            thr = -1.0
                        else:
                            st['slow'] = True
                    return RawInput(throttle=thr, cam_yaw=PF.PointFly.mouse_to_heading(x, tgt), look=True, brake=b)
                lg = run_raw(s, sched, 10.0)
                err = [wrap180(tgt - r['YawDeg']) for r in lg]
                crs = [wrap180(tgt - r['CourseDeg']) for r in lg]
                k_c = next((i for i, e in enumerate(crs) if abs(e) < 10.0), None)
                diam = None
                if k_c is not None:
                    p = lg[k_c]['ActorLocCm']
                    diam = abs((p[0] - p0[0]) * right0[0] + (p[1] - p0[1]) * right0[1]) / 100.0
                rows.append(dict(reversal_deg=dh, mode=mode, lat_ms=lat, heading_5deg_s=settle_time(err, 5.0),
                                 course_10deg_s=None if k_c is None else round((k_c + 1) * DT, 2),
                                 offset_m=None if diam is None else round(diam, 0),
                                 overshoot_deg=round(max(0.0, -min(err) if dh > 0 else max(err)), 1),
                                 drift_s=round(sum(1 for r in lg if r['bDrifting']) * DT, 2),
                                 kick_ms=round(max(r['Debug'].get('DriftKick', 0.0) for r in lg) / 100.0, 1),
                                 slip_max_deg=round(max(abs(wrap180(r['YawDeg'] - r['CourseDeg'])) for r in lg), 0),
                                 speed_min_ms=round(min(r['SpeedMS'] for r in lg), 1),
                                 speed_at_course_ms=None if k_c is None else round(lg[k_c]['SpeedMS'], 1)))
    print('drift: reversals at cruise (camera flicked to the new heading); offset = sideways distance from the entry line when the course is within 10 deg')
    for r in rows:
        print('  %4.0f deg %-10s %3d ms: heading within 5 deg %5s s, course within 10 deg %5s s, offset %4s m, overshoot %4.1f, drift %.1f s, kick %.0f m/s, slip max %3.0f, speed min %.0f, at the course %s' % (
            r['reversal_deg'], r['mode'], r['lat_ms'], r['heading_5deg_s'], r['course_10deg_s'], r['offset_m'], r['overshoot_deg'],
            r['drift_s'], r['kick_ms'], r['slip_max_deg'], r['speed_min_ms'], r['speed_at_course_ms']))
    OUT['drift'] = rows


# ---------------------------------------------------------------------------------------------------------------------
def broadside_pass(key, lock=True, lat=0.0, skill='precise', seed=5):
    """Racing past a target: cruise along +X; the target is 100 m to port of the track, 600 m ahead. The pilot holds
    Aim from 45 deg off the bow, looking at the target, fires on every solution, and lets go after 2 broadsides (or
    at 135 deg off the bow, or after 6 s); then looks along the old course again (Classic: the camera is free,
    nothing steers; the bot keeps the course with A/D)."""
    pawn = None if key != 'pointfly' else dict(PFArcAssist=lock)
    s = Sim(load_scheme(key), latency_ms=lat, alt_agl=60, seed=seed, pawn=pawn)
    run_commands(s, lambda t, x: Command(), 2.0)
    run_commands(s, lambda t, x: Command(thrust=1.0), 12.0)
    loc0 = s.tele()['ActorLocCm']
    alt = s.tele()['AltitudeM']
    tgt_m = (loc0[0] / 100.0 + 600.0, loc0[1] / 100.0 - 100.0, alt)
    tgt_cm = tuple(c * 100.0 for c in tgt_m)
    s.aim_targets = [(tgt_cm, 600.0)]
    rng = random.Random(seed)
    phase = 'approach'
    t_aim = None
    n_sol = n_frames = 0
    shots0 = len(s.cannon_shots)
    max_dev_y, max_hdg = 0.0, 0.0
    t_end = None
    log = []
    for i in range(int(40.0 / DT)):
        v = s.pilot_view()
        loc = [c * 0.01 for c in v['ActorLocCm']]
        brg = wrap180(math.atan2(tgt_m[1] - loc[1], tgt_m[0] - loc[0]) * R2D - v['YawDeg'])
        fired = (len(s.cannon_shots) - shots0) // 2
        if phase == 'approach' and abs(brg) > 45.0:
            phase, t_aim = 'aim', s.time
        elif phase == 'aim' and (abs(brg) > 135.0 or fired >= 2 or s.time - t_aim > 6.0):
            phase, t_end = 'return', s.time
        r = RawInput(throttle=1.0)
        if phase == 'aim':
            cam = s.camera_location_m(v)
            d = (tgt_m[0] - cam[0], tgt_m[1] - cam[1], tgt_m[2] - cam[2])
            r.aim = True
            r.cam_yaw = math.atan2(d[1], d[0]) * R2D
            r.cam_pitch = math.atan2(d[2], math.hypot(d[0], d[1])) * R2D
            r.look = True
            if skill == 'sloppy':
                r.cam_yaw += 2.0 * A.perlin1d(s.time * 1.7 + 3.1)
        else:
            if key == 'pointfly':
                # look along the old course again, a little toward the line (a mouse move: see mouse_to_heading)
                r.cam_yaw = PF.PointFly.mouse_to_heading(s, -clamp(0.3 * (loc[1] - loc0[1] * 0.01), -25.0, 25.0))
                r.look = True
            else:
                r.steer = clamp(0.05 * wrap180(0.0 - clamp(0.3 * (loc[1] - loc0[1] * 0.01), -25.0, 25.0) - v['YawDeg'])
                                - 0.02 * v['YawRateDegS'], -1.0, 1.0)
        # firing solution (port cannons, the bench's M12 test)
        ins = []
        for c in (0, 1):
            yaw_raw, elev_raw, _ = s.cannon_angles_raw(c, tgt_cm)
            ins.append(abs(yaw_raw) <= s.PP['CannonYawLimitDeg'] and s.PP['CannonElevMinDeg'] <= elev_raw <= s.PP['CannonElevMaxDeg'])
        sol = any(ins) and s.aim_side == 'port' and phase == 'aim'
        r.fire = sol
        rec = s.step(r)
        if phase == 'aim':
            n_frames += 1
            n_sol += sol
        max_dev_y = max(max_dev_y, abs(rec['ActorLocCm'][1] - loc0[1]) / 100.0)
        max_hdg = max(max_hdg, abs(rec['YawDeg']))
        log.append(rec)
        if t_end is not None and s.time - t_end > 8.0:
            break
    back = None
    if t_end is not None:
        k0 = int(round((t_end - log[0]['t']) / DT))
        back = next((round((k - k0) * DT, 2) for k in range(k0, len(log)) if all(abs(x['YawDeg']) < 3.0 for x in log[k:])), None)
    return dict(scheme=key, lock=lock if key == 'pointfly' else None, lat_ms=lat, aim_time_s=round(n_frames * DT, 2),
                solution_s=round(n_sol * DT, 2), broadsides=(len(s.cannon_shots) - shots0) // 2,
                heading_swing_max_deg=round(max_hdg, 1), track_offset_max_m=round(max_dev_y, 1),
                back_on_heading_s=back)


def check_pass():
    rows = []
    for key, lock in (('pointfly', True), ('pointfly', False), ('classic', None)):
        for lat in (0.0, 100.0):
            rows.append(broadside_pass(key, True if lock is None else lock, lat))
    print('pass: broadside while racing past a target 100 m off the track (Aim from 45 deg off the bow, let go after 2 broadsides)')
    for r in rows:
        print('  %-8s lock %-5s %3d ms: aimed %5.2f s, solution %5.2f s, broadsides %d, heading swing %4.1f deg, track offset %5.1f m, back on heading %s s' % (
            r['scheme'], r['lock'], r['lat_ms'], r['aim_time_s'], r['solution_s'], r['broadsides'], r['heading_swing_max_deg'],
            r['track_offset_max_m'], r['back_on_heading_s']))
    OUT['pass'] = rows


# ---------------------------------------------------------------------------------------------------------------------
_BaseBot = course.Bot


class MouseBot(_BaseBot):
    """The sloppy bot with a human hand on the mouse (see the module docstring)."""
    GLANCES = True
    GLANCE_AIM = False
    WN, ZETA = 7.5, 0.45

    def __init__(self, *a, **kw):
        _BaseBot.__init__(self, *a, **kw)
        self.hand_yaw = None
        self.hand_vel = 0.0
        self.mrng = random.Random(97)
        self.next_glance = 4.0 + self.mrng.uniform(0, 4)
        self.glance_until = -1.0
        self.glance_off = 0.0
        self.glances = 0

    def raw(self):
        r = _BaseBot.raw(self)
        if r.cam_yaw is None or self.skill.name != 'sloppy':
            return r
        t = self.sim.time
        want = r.cam_yaw
        glancing = t < self.glance_until
        if self.GLANCES and not glancing and t >= self.next_glance:
            self.glance_until = t + self.mrng.uniform(0.5, 0.9)
            self.glance_off = self.mrng.choice((-1.0, 1.0)) * self.mrng.uniform(25.0, 50.0)
            self.next_glance = t + self.mrng.uniform(6.0, 10.0)
            self.glances += 1
            glancing = True
        if glancing:
            want = want + self.glance_off
            r.cam_pitch = (r.cam_pitch or -12.0) - 15.0
            if self.GLANCE_AIM:
                r.aim = True
        if self.hand_yaw is None:
            self.hand_yaw = want
        e = wrap180(want - self.hand_yaw)
        self.hand_vel += (self.WN * self.WN * e - 2.0 * self.ZETA * self.WN * self.hand_vel) * DT
        self.hand_vel = clamp(self.hand_vel, -400.0, 400.0)
        self.hand_yaw = wrap180(self.hand_yaw + self.hand_vel * DT)
        r.cam_yaw = wrap180(self.hand_yaw + 1.5 * A.perlin1d(t * 1.7 + 11.0) + 0.8 * A.perlin1d(t * 4.3 + 29.0))
        return r


def run_course_with(bot_cls, key, skill, lat):
    orig = course.Bot
    course.Bot = bot_cls
    try:
        return course.run_course(load_scheme(key), skill, lat)
    finally:
        course.Bot = orig


def short(r):
    return dict(time_s=r['completion_time_s'], missed=r['gates_missed'], missed_gates=r['missed_gates'],
                line_mean_m=r['line_error_mean_m'], line_max_m=r['line_error_max_m'], outside_max_m=r['outside_max_m'],
                cam_rev_min=r['camera_reversals_per_min'], ground=r['ground_contacts'])


def check_mouse():
    rows = []
    class Hand(MouseBot):
        GLANCES = False

    class Glance(MouseBot):
        GLANCES = True

    class GlanceAim(MouseBot):
        GLANCES, GLANCE_AIM = True, True
    for variant, cls in (('analog (bench)', _BaseBot), ('hand + jitter', Hand), ('+ glances', Glance), ('+ glances on Aim', GlanceAim)):
        for lat in (0.0, 100.0):
            r = short(run_course_with(cls, 'pointfly', 'sloppy', lat))
            r.update(variant=variant, lat_ms=lat)
            rows.append(r)
    print('mouse: gate course, sloppy bot, human-like mouse (Point & Fly)')
    for r in rows:
        print('  %-17s %3d ms: time %s s, missed %d %s, line err %s / %s m, outside %s m, cam rev %s/min, ground %d' % (
            r['variant'], r['lat_ms'], r['time_s'], r['missed'], r['missed_gates'], r['line_mean_m'], r['line_max_m'],
            r['outside_max_m'], r['cam_rev_min'], r['ground']))
    OUT['mouse'] = rows


# ---------------------------------------------------------------------------------------------------------------------
@A.register_scheme
class PointFlyKeys(PF.PointFly):
    """Keyboard only (no mouse): Q/E turn the heading target (the camera follows), a bot that taps them."""
    key = 'pointfly_keys'

    def intent_raw(self, sim, intent, view, gains=None):
        r = PF.PointFly.intent_raw(self, sim, intent, view, gains)
        if r.aim:
            return r
        want = r.cam_yaw
        H = sim.pilot_state.get('H', view['YawDeg'])
        # rate the target should move at (deg/s) to catch the wanted heading, as Q/E (-1..1 of the nudge rate)
        rate = sim.PP['PFNudgeRateScale'] * PF.rmax_deg(sim.P, view['ForwardSpeed'], 0.0, False)
        r.strafe = clamp(wrap180(want - H) * 2.5 / max(rate, 1.0), -1.0, 1.0)
        r.cam_yaw, r.look = None, False
        return r


def check_keys():
    rows = []
    for skill in ('precise', 'sloppy'):
        for lat in (0.0, 100.0):
            r = short(course.run_course(load_scheme('pointfly_keys'), skill, lat))
            r.update(skill=skill, lat_ms=lat)
            rows.append(r)
    print('keys: gate course with Q/E only (no mouse); the sloppy bot plays Q/E on/off')
    for r in rows:
        print('  %-7s %3d ms: time %s s, missed %d %s, line err %s / %s m, outside %s m' % (
            r['skill'], r['lat_ms'], r['time_s'], r['missed'], r['missed_gates'], r['line_mean_m'], r['line_max_m'], r['outside_max_m']))
    OUT['keys'] = rows


# ---------------------------------------------------------------------------------------------------------------------
@A.register_scheme
class PointFlyPitch(PF.PointFly):
    """PFPitchClimb on: the bot climbs and sinks by looking up and down (the lift keys stay up)."""
    key = 'pointfly_pitch'
    pawn = dict(PF.PointFly.pawn, PFPitchClimb=True)

    def intent_raw(self, sim, intent, view, gains=None):
        r = PF.PointFly.intent_raw(self, sim, intent, view, gains)
        if r.aim:
            return r
        PP = sim.PP
        lift = r.lift
        r.lift = 0.0
        if abs(lift) > 1e-3:
            r.cam_pitch = PP['CameraDefaultPitch'] + math.copysign(PP['PFPitchClimbDeadbandDeg'] + abs(lift) * PP['PFPitchClimbFullDeg'], lift)
        return r


def check_pitch():
    rows = []
    for key in ('pointfly', 'pointfly_pitch'):
        for skill in ('precise', 'sloppy'):
            for lat in (0.0, 100.0):
                res = course.run_course(load_scheme(key), skill, lat)
                r = short(res)
                g = {x['gate']: x for x in res['gates']}
                r.update(scheme=key, skill=skill, lat_ms=lat, climb_gate_vert_m=g.get('C', {}).get('vert'),
                         dive_gate_vert_m=g.get('D', {}).get('vert'))
                rows.append(r)
    # glances down while cruising: look 35 deg down for 1 s every 8 s (checking the platforms below), no Aim
    glance = []
    for on in (False, True):
        s = Sim(load_scheme('pointfly'), latency_ms=0, alt_agl=60, pawn=dict(PFPitchClimb=on))
        run_commands(s, lambda t, x: Command(), 2.0)
        run_commands(s, lambda t, x: Command(thrust=1.0), 8.0)
        z0 = s.tele()['AltitudeM']
        lg = run_raw(s, lambda t, x: RawInput(throttle=1.0, cam_pitch=-47.0 if (t % 8.0) < 1.0 else -12.0, look=True), 32.0)
        glance.append(dict(pitch_climb=on, alt_change_max_m=round(max(abs(r['AltitudeM'] - z0) for r in lg), 1),
                           alt_change_end_m=round(lg[-1]['AltitudeM'] - z0, 1)))
    print('pitch: camera pitch -> climb, gate course (C = +40 m climb gate, D = dive gate: vertical miss in m)')
    for r in rows:
        print('  %-15s %-7s %3d ms: time %s s, missed %d, line err %s / %s m, C %s m, D %s m' % (
            r['scheme'], r['skill'], r['lat_ms'], r['time_s'], r['missed'], r['line_mean_m'], r['line_max_m'],
            r['climb_gate_vert_m'], r['dive_gate_vert_m']))
    for g in glance:
        print('  glances down (1 s at -47 deg every 8 s, 32 s), pitch climb %-5s: altitude change max %.1f m, at the end %+.1f m' % (
            g['pitch_climb'], g['alt_change_max_m'], g['alt_change_end_m']))
    OUT['pitch'] = dict(course=rows, glances=glance)


# ---------------------------------------------------------------------------------------------------------------------
def check_latency():
    rows = []
    for key in ('classic', 'pointfly'):
        for lat in (0.0, 100.0):
            s = metrics.cruise_sim(key, lat)
            pre = s.log[-1]
            log = run_commands(s, lambda t, x: Command(thrust=1.0, steer=1.0), 3.0)
            k0 = next(i for i, r in enumerate(log) if r['input']['steer'] != 0 or r['raw'].get('cam_yaw') is not None)

            def frames(fn):
                return next((i - k0 for i in range(k0, len(log)) if fn(log[i])), None)
            final = 35.0
            rows.append(dict(scheme=key, lat_ms=lat,
                             camera_frames=frames(lambda r: abs(wrap180(r['pilot']['cam_yaw'] - pre['pilot']['cam_yaw'])) > 0.5),
                             wheel_frames=frames(lambda r: abs(r['pilot']['WheelAngleDeg'] - pre['pilot']['WheelAngleDeg']) > 2.0),
                             fans_frames=frames(lambda r: abs(r['pilot']['TurbineYawDeg'] - pre['pilot']['TurbineYawDeg']) > 0.5),
                             server_turn_frames=frames(lambda r: r['YawRateDegS'] - pre['YawRateDegS'] > 0.1 * final),
                             screen_turn_frames=frames(lambda r: r['pilot']['screen']['YawRateDegS'] - pre['pilot']['screen']['YawRateDegS'] > 0.1 * final),
                             screen_bank_frames=frames(lambda r: r['pilot']['screen']['RollDeg'] - pre['pilot']['screen']['RollDeg'] > 1.0)))
    print('latency: frames (30 fps) from the turn input to ... on the pilot\'s machine (Classic: D; Point & Fly: camera swung right)')
    for r in rows:
        print('  %-8s %3d ms: camera %s, wheel %s, fans %s, server turn %s, screen turn %s, screen bank %s' % (
            r['scheme'], r['lat_ms'], r['camera_frames'], r['wheel_frames'], r['fans_frames'], r['server_turn_frames'],
            r['screen_turn_frames'], r['screen_bank_frames']))
    OUT['latency'] = rows


# ---------------------------------------------------------------------------------------------------------------------
def charge(mode, lat=0.0, seed=5):
    """Charging a target dead ahead (300 m, cruise). At 250 m the pilot swings the camera 90 deg right (port
    broadside onto the target); 'turn': plain turn, Aim held once the target is 60 deg off the bow; 'drift': X with
    the swing (the hull slides on toward the target), Aim held 0.3 s later (the heading target stays on the swing);
    X let go when the slide ends. Holds Fire while aiming for 8 s (polish: the gun lock is armed by Fire held or a
    recent own broadside, PFLockArmTime; with the lock always armed this protocol and 'fire on every solution' give the
    same solution times)."""
    s = Sim(load_scheme('pointfly'), latency_ms=lat, alt_agl=60, seed=seed)
    run_commands(s, lambda t, x: Command(), 2.0)
    run_commands(s, lambda t, x: Command(thrust=1.0), 12.0)
    loc0 = s.tele()['ActorLocCm']
    alt = s.tele()['AltitudeM']
    tgt_m = (loc0[0] / 100.0 + 300.0, loc0[1] / 100.0, alt)
    tgt_cm = tuple(c * 100.0 for c in tgt_m)
    s.aim_targets = [(tgt_cm, 600.0)]
    st = dict(phase='run', t_swing=None, first=None, released=False)
    shots0 = len(s.cannon_shots)
    rmin = 1e9
    n_sol = 0
    for i in range(int(16.0 / DT)):
        v = s.pilot_view()
        loc = [c * 0.01 for c in v['ActorLocCm']]
        rng = math.hypot(tgt_m[0] - loc[0], tgt_m[1] - loc[1])
        brg = wrap180(math.atan2(tgt_m[1] - loc[1], tgt_m[0] - loc[0]) * R2D - v['YawDeg'])
        r = RawInput(throttle=1.0)
        if st['phase'] == 'run' and rng < 250.0:
            st['phase'], st['t_swing'] = 'swing', s.time
            st['H'] = wrap180(v['YawDeg'] + 90.0)
        if st['phase'] == 'swing':
            # the flick comes first (steering mode); the drift pilot takes Aim 0.3 s later, the other at 60 deg
            aim = (s.time - st['t_swing'] > 0.3) if mode == 'drift' else abs(brg) > 60.0
            if mode == 'drift':
                r.brake = not st['released'] and (s.time - st['t_swing'] < 0.2 or s.pilot_state['loop'].get('drift', False))
                if not r.brake:
                    st['released'] = True
            if aim:
                cam = s.camera_location_m(v)
                d = (tgt_m[0] - cam[0], tgt_m[1] - cam[1], tgt_m[2] - cam[2])
                r.aim, r.look = True, True
                r.cam_yaw = math.atan2(d[1], d[0]) * R2D
                r.cam_pitch = math.atan2(d[2], math.hypot(d[0], d[1])) * R2D
            else:
                r.cam_yaw, r.look = PF.PointFly.mouse_to_heading(s, st['H']), True
        ins = []
        for c in (0, 1):
            yaw_raw, elev_raw, _ = s.cannon_angles_raw(c, tgt_cm)
            ins.append(abs(yaw_raw) <= s.PP['CannonYawLimitDeg'] and s.PP['CannonElevMinDeg'] <= elev_raw <= s.PP['CannonElevMaxDeg'])
        sol = any(ins) and s.aim_side == 'port' and r.aim
        r.fire = bool(r.aim)      # a pilot who wants to shoot holds Fire while aiming (it arms the gun lock)
        rec = s.step(r)
        if st['phase'] == 'swing':
            n_sol += sol
            rmin = min(rmin, rng)
            if sol and st['first'] is None:
                st['first'] = round(s.time - st['t_swing'], 2)
            if s.time - st['t_swing'] > 8.0:
                break
    return dict(mode=mode, lat_ms=lat, first_solution_s=st['first'], solution_s=round(n_sol * DT, 2),
                broadsides=(len(s.cannon_shots) - shots0) // 2, closest_m=round(rmin, 0),
                speed_end_ms=round(s.tele()['SpeedMS'], 1))


def check_charge():
    rows = [charge(m, lat) for m in ('turn', 'drift') for lat in (0.0, 100.0)]
    print('charge: target dead ahead, broadside swung onto it at 250 m (8 s window)')
    for r in rows:
        print('  %-5s %3d ms: first solution after %s s, solution %5.2f s, broadsides %d, closest %3.0f m, speed after %.0f m/s' % (
            r['mode'], r['lat_ms'], r['first_solution_s'], r['solution_s'], r['broadsides'], r['closest_m'], r['speed_end_ms']))
    OUT['charge'] = rows


# ---------------------------------------------------------------------------------------------------------------------
# Polish after judging (2026-11-23): the checks behind each change (SCHEME_POINTFLY.md "Review changes", P1-P6)
# ---------------------------------------------------------------------------------------------------------------------
def pf_sim(lat=0.0, flight=None, pawn=None, seed=1, **kw):
    sch = load_scheme('pointfly')
    sch.flight = dict(sch.flight, **(flight or {}))
    sch.pawn = dict(sch.pawn, **(pawn or {}))
    return Sim(sch, latency_ms=lat, alt_agl=kw.pop('alt_agl', 60), seed=seed, **kw)


def check_exit():
    """P2: the PIE m9 drift exit. 3 s brake-drift with the camera 90 deg ahead, then the camera set once to the hull's
    yaw + yaw rate x 0.3 s and X let go (the harness's 'steer off'): how far the nose swings past it."""
    rows = []
    for name, fl in (('pass 1 (GyroYawMax 0.5, no meet her)', dict(GyroYawMax=0.5, KrSteady=0.0, AlphaYawMaxSteady=0.0)),
                     ('polish (GyroYawMax 1, KrSteady 5.5, AlphaYawMaxSteady 1.5)', {})):
        for lat in (0.0, 100.0):
            sim = pf_sim(lat, fl)
            run_commands(sim, lambda t, x: Command(), 2.0)
            run_commands(sim, lambda t, x: Command(thrust=1.0), 15.0)
            run_commands(sim, lambda t, x: Command(thrust=1.0, steer=1.0, drift=True), 3.0)
            tl = sim.tele()
            tgt = wrap180(tl['YawDeg'] + tl['YawRateDegS'] * 0.3)
            log = run_commands(sim, lambda t, x: Command(thrust=1.0), 4.0)
            err = [wrap180(tgt - r['YawDeg']) for r in log]
            rows.append(dict(variant=name, lat_ms=lat, rate_at_exit_degs=round(tl['YawRateDegS'], 1),
                             to_go_deg=round(wrap180(tgt - tl['YawDeg']), 1), overshoot_deg=round(max(0.0, -min(err)), 2),
                             settle_05_s=settle_time(err, 0.5)))
    print('exit: the M9 drift exit (camera set once to yaw + rate x 0.3 s, X let go)')
    for r in rows:
        print('  %-60s %3d ms: %.1f deg/s with %.1f deg to go: overshoot %.2f deg, within 0.5 deg after %s s' % (
            r['variant'], r['lat_ms'], r['rate_at_exit_degs'], r['to_go_deg'], r['overshoot_deg'], r['settle_05_s']))
    OUT['exit'] = rows


def check_kick():
    """P1: the drift-kick snake (judge 'compete'): brake-drifts of 1.23 / 1.5 s with the camera swung +-90 deg and 0.1 /
    0.4 s gaps, mean speed over the ground (4-30 s) against W held; and the 180 deg brake-drift reversal."""
    def snake(fl, drift_s, gap_s, total=30.0):
        sim = pf_sim(0.0, fl)
        run_commands(sim, lambda t, x: Command(), 2.0)
        run_commands(sim, lambda t, x: Command(thrust=1.0), 20.0)
        period = 2 * (drift_s + gap_s)

        def sched(t, x):
            ph = t % period
            d = 1.0 if ph < drift_s + gap_s else -1.0
            ph2 = ph if d > 0 else ph - (drift_s + gap_s)
            if t < (drift_s + gap_s) / 2.0:
                return Command(thrust=1.0, drift=True, steer=-1.0)
            if ph2 < drift_s:
                return Command(thrust=1.0, drift=True, steer=d)
            return Command(thrust=1.0)
        log = run_commands(sim, sched, total)
        i0 = int(round(4.0 / DT))
        a, b = log[i0], log[-1]
        T = (len(log) - 1 - i0) * DT
        return round(math.hypot(b['ActorLocCm'][0] - a['ActorLocCm'][0], b['ActorLocCm'][1] - a['ActorLocCm'][1]) / 100.0 / T, 2)

    def reversal(fl):
        sim = pf_sim(0.0, fl)
        run_commands(sim, lambda t, x: Command(), 2.0)
        run_commands(sim, lambda t, x: Command(thrust=1.0), 20.0)
        y0 = sim.log[-1]['YawDeg']
        st = dict(released=False)

        def sched(t, x):
            if not st['released'] and t > 0.3 and not x.log[-1]['bDrifting']:
                st['released'] = True
            return Command(thrust=1.0, brake=not st['released'] and t < 6.0, look_yaw=y0 + 179.0)
        log = run_commands(sim, sched, 8.0)
        return dict(speed_min_ms=round(min(r['ForwardSpeedMS'] for r in log), 1), speed_8s_ms=round(log[-1]['ForwardSpeedMS'], 1),
                    kick_ms=round(max(r['Debug'].get('DriftKick', 0.0) for r in log) / 100.0, 2))
    w = pf_sim(0.0)
    run_commands(w, lambda t, x: Command(), 2.0)
    w_ms = round(run_commands(w, lambda t, x: Command(thrust=1.0), 30.0)[-1]['ForwardSpeedMS'], 2)
    rows = []
    for name, fl in (('cap off (pass 1)', dict(DriftBoostCapSpeed=0.0)), ('cap 48 m/s (polish)', {})):
        rows.append(dict(variant=name, w_held_ms=w_ms, snake_123_01_ms=snake(fl, 1.23, 0.1), snake_123_04_ms=snake(fl, 1.23, 0.4),
                         snake_15_01_ms=snake(fl, 1.5, 0.1), reversal=reversal(fl)))
    print('kick: drift-kick snake, mean speed over the ground (m/s); W held = %s' % w_ms)
    for r in rows:
        print('  %-20s 1.23 s / 0.1 s gaps %s, 1.23 / 0.4 %s, 1.5 / 0.1 %s | 180 deg reversal %s' % (
            r['variant'], r['snake_123_01_ms'], r['snake_123_04_ms'], r['snake_15_01_ms'], r['reversal']))
    OUT['kick'] = rows


def check_park():
    """P3: a new pilot at rest orbits the camera 360 deg in 4 s (mouse, no keys), then looks 120 deg right and holds W."""
    rows = []
    for name, pawn in (('parked free look off (pass 1)', dict(PFParkSpeed=0.0)), ('parked free look on (polish)', {})):
        sim = pf_sim(0.0, None, pawn)
        run_commands(sim, lambda t, x: Command(), 4.0)
        y0 = sim.tele()['YawDeg']
        lg = run_raw(sim, lambda t, x: RawInput(cam_yaw=wrap180(x.cam.control_yaw + 90.0 * DT), look=True), 4.0)
        during = max(abs(wrap180(r['YawDeg'] - y0)) for r in lg)
        lg2 = run_raw(sim, lambda t, x: RawInput(cam_yaw=x.cam.control_yaw), 6.0)
        after = abs(wrap180(lg2[-1]['YawDeg'] - y0))
        look = wrap180(sim.tele()['YawDeg'] + 120.0)
        run_raw(sim, lambda t, x: RawInput(cam_yaw=wrap180(x.cam.control_yaw + wrap180(look - x.cam.control_yaw) * 0.3), look=True), 1.5)
        lg3 = run_raw(sim, lambda t, x: RawInput(throttle=1.0, cam_yaw=x.cam.control_yaw), 8.0)
        err = [wrap180(look - r['YawDeg']) for r in lg3]
        rows.append(dict(variant=name, orbit_turn_deg=round(during, 0), turn_6s_after_deg=round(after, 0),
                         w_heading_5deg_s=settle_time(err, 5.0), w_overshoot_deg=round(max(0.0, -min(err)), 1)))
    print('park: 360 deg camera orbit in 4 s at hover (no keys), then a look 120 deg right and W')
    for r in rows:
        print('  %-30s hull turned %3.0f deg during the orbit, %3.0f deg 6 s later | W: on the look heading (5 deg) after %s s, overshoot %.1f deg' % (
            r['variant'], r['orbit_turn_deg'], r['turn_6s_after_deg'], r['w_heading_5deg_s'], r['w_overshoot_deg']))
    OUT['park'] = rows


PUSH_MS, KNOCK_DEGS, KNOCK_AT_S = 6.0, 70.0, 1.0      # the PIE check as_50f p3_push uses the same values


def check_push():
    """F-B (follow-up 2026-11-23): parked at hover with the camera 120 deg right of the bow (mouse), a hit pushes the ship
    PUSH_MS along the bow and KNOCK_AT_S later knocks it KNOCK_DEGS round toward the camera, no key, the mouse still:
    the parked free look must hold, the hull must not turn toward the camera (the heading loop brings a knocked hull
    back to the held heading) and the camera must not move; then W: the ship turns to the camera yaw."""
    rows = []
    keep = PF.PARK_LATCH
    try:
        for name, latch in (('polish build (no latch)', False), ('follow-up (latched)', True)):
            PF.PARK_LATCH = latch
            sim = pf_sim(0.0, None, None)
            run_commands(sim, lambda t, x: Command(), 4.0)
            y0 = sim.tele()['YawDeg']
            look = wrap180(y0 + 120.0)
            run_raw(sim, lambda t, x: RawInput(cam_yaw=wrap180(x.cam.control_yaw + wrap180(look - x.cam.control_yaw) * 0.3), look=True), 1.5)
            cam0 = sim.cam.control_yaw
            parked0 = bool(sim.pilot_state.get('parked'))
            b = sim.body
            b.v = A.add(b.v, A.mul(A.qrot(b.q, (1.0, 0.0, 0.0)), PUSH_MS * 100.0))
            hold = []
            for i in range(int(round(7.0 / DT))):
                if i == int(round(KNOCK_AT_S / DT)):
                    b.w = (b.w[0], b.w[1], b.w[2] + KNOCK_DEGS * D2R)
                sim.step(RawInput(cam_yaw=sim.cam.control_yaw))
                t = sim.tele()
                hold.append((wrap180(t['YawDeg'] - y0), t['ForwardSpeedMS'], bool(sim.pilot_state.get('parked')), sim.cam.control_yaw))
            k_peak = max(range(len(hold)), key=lambda i: hold[i][0])
            lg = run_raw(sim, lambda t, x: RawInput(throttle=1.0, cam_yaw=x.cam.control_yaw), 8.0)
            err = [wrap180(cam0 - r['YawDeg']) for r in lg]
            rows.append(dict(variant=name, parked_before=parked0,
                             fwd_over_park_s=round(sum(1 for h in hold if abs(h[1]) * 100.0 > sim.PP['PFParkSpeed']) * DT, 2),
                             parked_hold_pct=round(100.0 * sum(1 for h in hold if h[2]) / len(hold), 1),
                             peak_toward_camera_deg=round(hold[k_peak][0], 1), peak_t_s=round(k_peak * DT, 2),
                             end_off_heading_deg=round(hold[-1][0], 2), camera_moved_deg=round(wrap180(hold[-1][3] - cam0), 2),
                             w_heading_5deg_s=settle_time(err, 5.0), w_overshoot_deg=round(max(0.0, -min(err)), 1),
                             w_end_err_deg=round(err[-1], 2)))
    finally:
        PF.PARK_LATCH = keep
    print('push: parked at hover, camera 120 deg right, +%.0f m/s along the bow and %.0f deg/s round at %.1f s, 7 s no key, then W' % (
        PUSH_MS, KNOCK_DEGS, KNOCK_AT_S))
    for r in rows:
        print('  %-24s over %.0f m/s for %.1f s, parked %5.1f %% | hull peak %+6.1f deg at %.1f s, after 7 s %+6.1f deg off the heading, camera moved %.1f'
              ' | W: on the camera yaw (5 deg) after %s s, overshoot %.1f deg' % (
                  r['variant'], 3.0, r['fwd_over_park_s'], r['parked_hold_pct'], r['peak_toward_camera_deg'], r['peak_t_s'],
                  r['end_off_heading_deg'], r['camera_moved_deg'], r['w_heading_5deg_s'], r['w_overshoot_deg']))
    OUT['push'] = rows


def check_rival():
    """P4: racing at cruise, Aim held for 3 s on a rival flying alongside 60 / 120 deg off the bow, no Fire, then the
    camera back on the course: heading swing and track offset (the gun lock armed always vs only by Fire)."""
    rows = []
    for name, arm in (('lock always armed (pass 1)', 0.0), ('armed by Fire (polish)', 6.0)):
        for bearing in (60.0, 120.0):
            s = pf_sim(0.0, None, dict(PFLockArmTime=arm), seed=5)
            run_commands(s, lambda t, x: Command(), 2.0)
            run_commands(s, lambda t, x: Command(thrust=1.0), 12.0)
            y0 = s.tele()['YawDeg']
            loc0 = s.tele()['ActorLocCm']
            lg = []
            for i in range(int(7.0 / DT)):
                r = RawInput(throttle=1.0)
                if i * DT < 3.0:
                    r.aim, r.look, r.cam_yaw = True, True, wrap180(y0 - bearing)
                else:
                    r.cam_yaw, r.look = PF.PointFly.mouse_to_heading(s, y0), True
                lg.append(s.step(r))
            fy = (-math.sin(y0 * D2R), math.cos(y0 * D2R))
            rows.append(dict(variant=name, bearing_deg=bearing, heading_swing_deg=round(max(abs(wrap180(x['YawDeg'] - y0)) for x in lg), 1),
                             track_offset_m=round(max(abs((x['ActorLocCm'][0] - loc0[0]) * fy[0] + (x['ActorLocCm'][1] - loc0[1]) * fy[1]) for x in lg) / 100.0, 1),
                             lock_frames=sum(1 for x in lg if x.get('bArcAssist'))))
    print('rival: Aim held 3 s on a rival alongside, no Fire')
    for r in rows:
        print('  %-28s %3.0f deg off the bow: heading swing %4.1f deg, track offset %5.1f m, lock frames %d' % (
            r['variant'], r['bearing_deg'], r['heading_swing_deg'], r['track_offset_m'], r['lock_frames']))
    OUT['rival'] = rows


class ArmLag:
    """USpringArmComponent position lag for the bench camera (the bench models the rotation lag only): the arm's origin
    follows the ship root with VInterpTo at `speed` /s in 1/60 s sub-steps, at most max_dist cm behind. With speed 4 and
    the rotation lag at 5 /s it reproduces the PIE camera of the M12 orbit within 0.05 m (the frames' 'cam' against a
    replay of their hull and control rotation; the engine's 5 / 7 /s plus a frame of camera-manager delay)."""

    def __init__(self, sim, speed=4.0, max_dist=2500.0):
        self.sim, self.speed, self.max_dist = sim, speed, max_dist
        self.origin, self.t = None, None
        self.prev_root = list(sim.tele()['ActorLocCm'])

    def __call__(self, view):
        sim = self.sim
        root = list(view['ActorLocCm'])
        if self.origin is None:
            self.origin, self.t = list(root), sim.time
        if sim.time != self.t:
            dt = sim.time - self.t
            n = max(1, int(math.ceil(dt / (1.0 / 60.0) - 1e-9)))
            prev = self.prev_root
            for k in range(1, n + 1):
                tgt = [prev[i] + (root[i] - prev[i]) * k / n for i in range(3)]
                a = clamp(dt / n * self.speed, 0.0, 1.0)
                self.origin = [self.origin[i] + (tgt[i] - self.origin[i]) * a for i in range(3)]
            d = [self.origin[i] - root[i] for i in range(3)]
            m = math.sqrt(sum(x * x for x in d))
            if m > self.max_dist:
                self.origin = [root[i] + d[i] * self.max_dist / m for i in range(3)]
            self.t = sim.time
        # the root of the last call (a call inside the step sees the pre-step root: the next frame starts from it)
        self.prev_root = list(root)
        d = sim.cam.look_dir()
        tgt = (self.origin[0], self.origin[1], self.origin[2] + sim.PP['CameraTargetOffsetZ'])
        return tuple(c * 0.01 for c in A.sub(tgt, A.mul(d, sim.cam.arm)))


def m12_cam_case(lead, skill, aim, seconds=30.0, top=47.97):
    """The M12 orbit (metrics.m12's loop) with the PIE-calibrated camera. aim 'control': the bot sets the control
    rotation from the camera to the target (as the bench and the PIE harness do); 'view': a hand keeps the crosshair
    (the lagged view) on the target. Means over the run: cannon 0's yaw to the target (M12 beam_yaw), the target's
    bearing from the hull origin and the control yaw, both against the port beam (+ = forward)."""
    sim = pf_sim(0.0, None, dict(PFLockLeadTime=lead, CameraRotationLagSpeed=5.0), seed=3, alt_agl=metrics.START_AGL, pos_m=(0.0, 100.0))
    lagm = ArmLag(sim)
    sim.camera_location_m = lagm
    alt = sim.tele()['AltitudeM']
    target = (0.0, 0.0, alt)
    tgt_cm = (0.0, 0.0, alt * 100.0)
    sim.aim_targets = [(tgt_cm, 600.0)]
    bot = course.Bot(sim, metrics.OrbitPlanner(target, 100.0, 0.6 * top), course.Skill(skill), seed=11)
    run_commands(sim, lambda t, x: Command(), 2.0)
    n_run, n_meas = int(15 / DT), int(seconds / DT)
    yaws, rel_hull, rel_ctrl = [], [], []
    for i in range(n_run + n_meas):
        raw = bot.raw()
        if aim == 'view' and raw.aim and raw.cam_yaw is not None:
            v = sim.pilot_view()
            cam = sim.camera_location_m(v)
            want = math.atan2(target[1] - cam[1], target[0] - cam[0]) * R2D
            raw.cam_yaw = wrap180(sim.cam.control_yaw + 0.6 * wrap180(want - sim.cam.view_yaw))
        tele = sim.tele()
        ins = []
        for c in (0, 1):
            yaw_raw, elev_raw, _ = sim.cannon_angles_raw(c, tgt_cm)
            ins.append(abs(yaw_raw) <= sim.PP['CannonYawLimitDeg'] and sim.PP['CannonElevMinDeg'] <= elev_raw <= sim.PP['CannonElevMaxDeg'])
            if c == 0 and i >= n_run:
                yaws.append(yaw_raw)
        loc = tele['ActorLocCm']
        rng_m = math.sqrt(sum((loc[k] - tgt_cm[k]) ** 2 for k in range(3))) / 100.0
        raw.fire = any(ins) and 80.0 <= rng_m <= 120.0 and tele['ForwardSpeedMS'] >= 0.5 * top and sim.aim_side == 'port'
        sim.step(raw)
        # the spring arm ticks after physics (TG_PostPhysics): the camera moves with this frame's root
        sim.camera_location_m(sim.pilot_view())
        if i >= n_run:
            t2 = sim.tele()
            yaw = t2['YawDeg']
            b = math.atan2(target[1] - t2['ActorLocCm'][1] / 100.0, target[0] - t2['ActorLocCm'][0] / 100.0) * R2D
            rel_hull.append(wrap180(b - (yaw - 90.0)))
            rel_ctrl.append(wrap180(sim.cam.control_yaw - (yaw - 90.0)))
    m = lambda v: round(sum(v) / len(v), 2)
    return dict(beam_yaw_deg=m(yaws), target_vs_beam_deg=m(rel_hull), control_vs_beam_deg=m(rel_ctrl))


def check_m12cam():
    rows = []
    for aim in ('control', 'view'):
        for lead in (0.45, 0.6, 0.75):
            for skill in ('precise', 'sloppy'):
                r = m12_cam_case(lead, skill, aim)
                r.update(aim=aim, lead_s=lead, skill=skill)
                rows.append(r)
    print('m12cam: M12 with the PIE-calibrated camera (PIE pass 1, lead 0.45, bot: beam yaw -7.39 / -7.32, control vs beam -0.48)')
    for r in rows:
        print('  aim %-7s lead %.2f %-7s: beam yaw %+6.2f, target vs the port beam %+6.2f, control yaw vs the beam %+6.2f deg' % (
            r['aim'], r['lead_s'], r['skill'], r['beam_yaw_deg'], r['target_vs_beam_deg'], r['control_vs_beam_deg']))
    OUT['m12cam'] = rows


CHECKS = dict(steps=check_steps, sweeps=check_sweeps, drift=check_drift, passing=check_pass, mouse=check_mouse,
              keys=check_keys, pitch=check_pitch, latency=check_latency, charge=check_charge,
              exit=check_exit, kick=check_kick, park=check_park, push=check_push, rival=check_rival, m12cam=check_m12cam)

if __name__ == '__main__':
    names = [a for a in sys.argv[1:] if not a.startswith('-')]
    names = ['passing' if n == 'pass' else n for n in names]
    for n in names or list(CHECKS):
        CHECKS[n]()
        print()
    if not names:
        json.dump(OUT, open(os.path.join(HERE, 'pointfly_checks.json'), 'w'), indent=1)
        print('wrote pointfly_checks.json')
