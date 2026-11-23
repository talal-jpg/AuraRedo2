"""Standard maneuvers and metrics M1..M12 for an airship control scheme (the PIE harness ports these 1:1).

Common rules (sim and PIE):
  * Fixed 30 fps (dt = 1/30 s). Telemetry is read once per frame after the physics step (GetFlightTelemetry on the
    server's ship; "pilot" values on the pilot's machine). Times are counted from the first frame in which the
    pilot's machine uses the new input (in the PIE harness that is one frame after the inject / DebugSetInput call).
  * Start: hovering at rest, level, heading +X, 60 m above flat ground with nothing within 600 m, neutral controls
    for 2 s. "Cruise" = after that, 20 s of full forward drive (steady top speed, level).
  * Inputs go through the scheme's own controls (Scheme.command_raw for maneuvers, Scheme.intent_raw for the bots),
    e.g. "full forward" is W held in Classic, "full ahead" on a telegraph scheme.
  * Speeds are ForwardSpeedMS / LateralSpeedMS / VerticalSpeedMS (hull axes, m/s), angles RollDeg / PitchDeg /
    YawDeg, turn rate YawRateDegS (world Z, + = right).
  * Latency: M1-M9 run with the pilot as the listen-server host (no network). M10-M12 also run with the pilot as a
    client with 100 ms each way.

Writes <scheme>_metrics.json with the fixed keys meta, M1..M12 (README.md lists every sub-key).

Run: python3 metrics.py [scheme] [--out DIR]     (Classic: about 40 s, one process)
"""
import json
import math
import os
import sys
import time

from airship_sim import Sim, Command, Intent, RawInput, load_scheme, run_commands, wrap180, clamp, DT, R2D, D2R
import course

HERE = os.path.dirname(os.path.abspath(__file__))
START_AGL = 60.0
G_MS2 = 9.81

# ------------------------------------------------------------------------------------------------------------------
# What each metric is, why it matters for fun, and the band I think is good for an action-game ship of this size
# (52 m, 40 t). Designers set their own targets; these are a starting point.
# ------------------------------------------------------------------------------------------------------------------
METRIC_INFO = {
    'M1': dict(name='Acceleration', definition='time from rest to 80 % of the steady top speed, full forward drive',
               why='How fast W turns into motion. Too slow feels like a barge; instant feels like a toy, not a 40 t ship.',
               target='t80 2.0-3.5 s'),
    'M2': dict(name='Top speed and boost', definition='steady top speed (mean 17-20 s of full drive), peak; boost held '
               'from cruise: peak speed, how long the fuel lasts',
               why='Sets the pace of the race and how much boost is worth: boost has to feel like a real gear change.',
               target='top 45-60 m/s; boost peak 1.6-2.0 x top; boost 3-5 s'),
    'M3': dict(name='Brake and coast', definition='brake from cruise: time and distance to < 0.5 m/s, peak decel (g, '
               '3-frame central difference); coast from cruise with nothing held: time to half speed',
               why='A sure brake lets players commit to speed into hairpins; a long coast gives the glide of a big ship.',
               target='stop 1.5-3.0 s in 30-60 m, peak <= 2.5 g; coast to half 8-15 s'),
    'M4': dict(name='Turn response', definition='full steer at cruise: time to 63 % and 90 % of the final turn rate '
               '(mean 6-8 s), overshoot %, final turn rate, steady bank (mean roll 6-8 s), slip and height lost at 8 s',
               why='The core feel: how quickly the nose answers the stick and how planted the turn is.',
               target='t63 <= 0.5 s, t90 <= 1.0 s, overshoot <= 10 %, 30-45 deg/s, bank 12-22 deg, height loss <= 2 m'),
    'M5': dict(name='U-turn', definition='full steer at cruise until the heading has changed 180 deg: time and turn '
               'diameter (sideways offset from the entry line)',
               why='How much room a reversal needs: it decides whether hairpins and dogfights are possible.',
               target='4-6 s, diameter 100-180 m'),
    'M6': dict(name='Nose pitch', definition='lowest pitch at full drive from rest (and steady pitch at top speed), '
               'lowest pitch with boost from cruise, highest pitch while braking from cruise',
               why='Visible weight transfer reads as power, but a big dip hides the horizon and the targets ahead.',
               target='drive -3..-8 deg, boost -5..-10 deg, brake flare +3..+8 deg'),
    'M7': dict(name='Vertical', definition='climb and sink rate (full lift 5 s from hover); +30 m step: hold lift '
               'until 30 m above the start, then release: rise time, overshoot, |vz| 1 s and 2 s after the release, '
               'error 5 s after',
               why='Height is how players dodge, hop platforms and line up shots: it must stop where they let go.',
               target='climb 10-15 m/s; rise 2.5-4 s; overshoot <= 1.5 m; |vz| <= 1.5 m/s at +1 s, <= 0.5 at +2 s'),
    'M8': dict(name='Strafe', definition='full strafe from hover: time to 90 % of the final side speed (mean 3-4 s) '
               'and that speed; also the final side speed when strafing at cruise',
               why='Side-steps dodge fire and line up a broadside without turning the bow.',
               target='t90 0.6-1.2 s, 10-15 m/s'),
    'M9': dict(name='Drift', definition='drift (Classic: brake + full steer, drive held) for 3 s from cruise, then let '
               'go: slip angle (nose vs velocity) at 1, 2, 3 s, turn rate, speed kept, exit kick (forward speed change '
               'over the frames around the drift end)',
               why='A drift is the skill move: a clear slide and a reward on the way out make turns fun to master.',
               target='slip 20-45 deg at 1-2 s, speed kept >= 70 %, exit kick 4-8 m/s'),
    'M10': dict(name='Latency', definition='frames (30 fps) from the pilot\'s own input change to: turbine housing '
                '> 0.5 deg and wheel > 2 deg on the pilot\'s screen (anim), the server\'s turn rate > 10 % of the M4 '
                'final, the same on the pilot\'s screen; throttle from hover: forward speed > 0.1 m/s on the pilot\'s '
                'screen; host and client with 100 ms each way',
                why='Lag between the hand and the ship is the biggest fun killer for a client pilot.',
                target='cosmetic 0-1 frames; physics on screen <= 2 frames (host), <= 8 frames (100 ms each way)'),
    'M11': dict(name='Gate course', definition='course.py: 11 gates (straight, slalom, hairpin, climb, dive, finish) '
                'flown by the precise and the sloppy-human bot through the scheme\'s adapter: completion time, gates '
                'missed, miss distance from the gate centre, error from the bot\'s racing line, steering and camera '
                'reversals per minute, ground contacts',
                why='The whole loop: can a good player fly a line, and can an average one still have fun?',
                target='precise: 0 missed; sloppy: <= 1 missed at 0 ms and <= 2 at 100 ms; reversals <= 20/min'),
    'M12': dict(name='Broadside', definition='a fixed target at the ship\'s height, starting 100 m off the port beam; '
                'the bot keeps it abeam to port at 80-120 m at >= 50 % of top speed for 60 s (after a 15 s run-in), '
                'firing whenever it has a solution: % of frames the target is inside a port cannon arc (yaw +-20 deg '
                'from the beam, elevation -10..+8.5 deg, at least one cannon), in range, fast enough, the camera on the '
                'port side, all four (firing solution), shots fired',
                why='The cannons are the ship\'s identity: holding a target in the arc while moving is the payoff.',
                target='in arc >= 70 %, firing solution >= 50 % (precise bot)'),
}


# ------------------------------------------------------------------------------------------------------------------
def new_sim(scheme_key, latency=0.0, **kw):
    sim = Sim(load_scheme(scheme_key), latency_ms=latency, alt_agl=START_AGL, seed=kw.pop('seed', 1), **kw)
    run_commands(sim, lambda t, s: Command(), 2.0)
    return sim


def cruise_sim(scheme_key, latency=0.0):
    sim = new_sim(scheme_key, latency)
    run_commands(sim, lambda t, s: Command(thrust=1.0), 20.0)
    return sim


def mean(v):
    return sum(v) / len(v) if v else None


def first_time(log, fn, dt=DT):
    for i, r in enumerate(log):
        if fn(r):
            return round((i + 1) * dt, 3)
    return None


def rnd(x, n=2):
    return None if x is None else round(x, n)


# ------------------------------------------------------------------------------------------------------------------
def m1_m2_m6(key):
    sim = new_sim(key)
    alt0 = sim.tele()['AltitudeM']
    log = run_commands(sim, lambda t, s: Command(thrust=1.0), 20.0)
    v = [r['ForwardSpeedMS'] for r in log]
    top = mean(v[int(17 / DT):])
    peak = max(v)
    m1 = dict(t80_s=first_time(log, lambda r: r['ForwardSpeedMS'] >= 0.8 * top), t63_s=first_time(log, lambda r: r['ForwardSpeedMS'] >= 0.63 * top),
              speed_at_2s_ms=rnd(v[int(round(2 / DT)) - 1]), speed_at_4s_ms=rnd(v[int(round(4 / DT)) - 1]))
    pitch_min = min(r['PitchDeg'] for r in log)
    pitch_top = mean([r['PitchDeg'] for r in log[int(17 / DT):]])
    alt_dip = alt0 - min(r['AltitudeM'] for r in log)
    # boost from cruise until the fuel is gone (6 s)
    v0 = sim.tele()['ForwardSpeedMS']
    blog = run_commands(sim, lambda t, s: Command(thrust=1.0, boost=True), 6.0)
    bv = [r['ForwardSpeedMS'] for r in blog]
    bpeak = max(bv)
    active = [r['BoostActive'] for r in blog]
    dur = (active.index(False) if False in active else len(active)) * DT
    t90 = first_time(blog, lambda r: r['ForwardSpeedMS'] >= v0 + 0.9 * (bpeak - v0))
    m2 = dict(top_steady_ms=rnd(top), top_peak_ms=rnd(peak), boost_peak_ms=rnd(bpeak), boost_ratio=rnd(bpeak / top, 3),
              boost_duration_s=rnd(dur), boost_t90_s=t90)
    m6 = dict(drive_pitch_min_deg=rnd(pitch_min), top_pitch_deg=rnd(pitch_top), boost_pitch_min_deg=rnd(min(r['PitchDeg'] for r in blog)),
              drive_alt_dip_m=rnd(alt_dip))
    return m1, m2, m6, top


def m3(key):
    sim = cruise_sim(key)
    t0 = sim.tele()
    v0 = t0['ForwardSpeedMS']
    p0 = t0['ActorLocCm']
    yaw0 = t0['YawDeg'] * D2R
    alt0 = t0['AltitudeM']
    log = run_commands(sim, lambda t, s: Command(brake=True), 8.0)
    v = [v0] + [r['ForwardSpeedMS'] for r in log]
    k_stop = next((i for i in range(1, len(v)) if v[i] <= 0.5), None)
    dist = None
    if k_stop is not None:
        p = log[k_stop - 1]['ActorLocCm']
        dist = ((p[0] - p0[0]) * math.cos(yaw0) + (p[1] - p0[1]) * math.sin(yaw0)) / 100.0
    decel = max(-(v[i + 1] - v[i - 1]) / (2 * DT) for i in range(1, len(v) - 1)) / G_MS2
    flare = max(r['PitchDeg'] for r in log)
    rise = max(r['AltitudeM'] for r in log) - alt0
    half = first_time(log, lambda r: r['ForwardSpeedMS'] <= 0.5 * v0)
    # coast
    sim2 = cruise_sim(key)
    c0 = sim2.tele()['ForwardSpeedMS']
    clog = run_commands(sim2, lambda t, s: Command(), 40.0)
    coast_half = first_time(clog, lambda r: r['ForwardSpeedMS'] <= 0.5 * c0)
    mean_decel = v0 / (k_stop * DT) / G_MS2 if k_stop else None
    return dict(start_speed_ms=rnd(v0), stop_time_s=rnd(k_stop * DT if k_stop else None), stop_distance_m=rnd(dist),
                half_speed_s=half, peak_decel_g=rnd(decel), mean_decel_g=rnd(mean_decel), coast_half_s=coast_half,
                alt_rise_m=rnd(rise)), flare


def m4(key):
    sim = cruise_sim(key)
    t0 = sim.tele()
    alt0 = t0['AltitudeM']
    log = run_commands(sim, lambda t, s: Command(thrust=1.0, steer=1.0), 8.0)
    r = [x['YawRateDegS'] for x in log]
    final = mean(r[int(6 / DT):])
    peak = max(r)
    last = log[-1]
    return dict(final_yaw_rate_degs=rnd(final), t63_s=first_time(log, lambda x: x['YawRateDegS'] >= 0.63 * final),
                t90_s=first_time(log, lambda x: x['YawRateDegS'] >= 0.9 * final),
                overshoot_pct=rnd(max(0.0, (peak - final) / final * 100.0), 1),
                bank_deg=rnd(mean([x['RollDeg'] for x in log[int(6 / DT):]])),
                slip_8s_deg=rnd(math.atan2(-last['LateralSpeedMS'], last['ForwardSpeedMS']) * R2D),
                speed_8s_ms=rnd(last['SpeedMS']), alt_loss_8s_m=rnd(alt0 - last['AltitudeM']),
                pitch_min_deg=rnd(min(x['PitchDeg'] for x in log))), final


def m5(key):
    sim = cruise_sim(key)
    t0 = sim.tele()
    p0 = t0['ActorLocCm']
    y0 = t0['YawDeg']
    v0 = t0['ForwardSpeedMS']
    right0 = (-math.sin(y0 * D2R), math.cos(y0 * D2R))
    turned = 0.0
    prev = y0
    n = 0
    rec = None
    while turned < 180.0 and n < int(20 / DT):
        rec = sim.step(sim.scheme.command_raw(sim, Command(thrust=1.0, steer=1.0)))
        turned += wrap180(rec['YawDeg'] - prev)
        prev = rec['YawDeg']
        n += 1
    p = rec['ActorLocCm']
    diam = abs((p[0] - p0[0]) * right0[0] + (p[1] - p0[1]) * right0[1]) / 100.0
    return dict(time_s=rnd(n * DT if turned >= 180 else None), diameter_m=rnd(diam), speed_end_ms=rnd(rec['SpeedMS']),
                speed_kept_pct=rnd(rec['SpeedMS'] / v0 * 100.0, 1))


def m7(key):
    sim = new_sim(key)
    log = run_commands(sim, lambda t, s: Command(lift=1.0), 5.0)
    climb = max(r['VerticalSpeedMS'] for r in log)
    sim = new_sim(key)
    log = run_commands(sim, lambda t, s: Command(lift=-1.0), 5.0)
    sink = -min(r['VerticalSpeedMS'] for r in log)
    # +30 m step
    sim = new_sim(key)
    z0 = sim.tele()['AltitudeM']
    n = 0
    while sim.tele()['AltitudeM'] < z0 + 30.0 and n < int(10 / DT):
        sim.step(sim.scheme.command_raw(sim, Command(lift=1.0)))
        n += 1
    rise = n * DT
    log = run_commands(sim, lambda t, s: Command(), 6.0)
    over = max(r['AltitudeM'] for r in log) - (z0 + 30.0)
    vz1 = abs(log[int(round(1 / DT)) - 1]['VerticalSpeedMS'])
    vz2 = abs(log[int(round(2 / DT)) - 1]['VerticalSpeedMS'])
    err5 = abs(log[int(round(5 / DT)) - 1]['AltitudeM'] - (z0 + 30.0))
    return dict(climb_rate_ms=rnd(climb), sink_rate_ms=rnd(sink), step30_rise_s=rnd(rise), step30_overshoot_m=rnd(over),
                step30_vz_1s_ms=rnd(vz1), step30_vz_2s_ms=rnd(vz2), step30_error_5s_m=rnd(err5))


def m8(key):
    sim = new_sim(key)
    log = run_commands(sim, lambda t, s: Command(strafe=1.0), 4.0)
    final = mean([r['LateralSpeedMS'] for r in log[int(3 / DT):]])
    t90 = first_time(log, lambda r: r['LateralSpeedMS'] >= 0.9 * final)
    sim = cruise_sim(key)
    log = run_commands(sim, lambda t, s: Command(thrust=1.0, strafe=1.0), 4.0)
    cruise = mean([r['LateralSpeedMS'] for r in log[int(3 / DT):]])
    return dict(t90_s=t90, strafe_speed_ms=rnd(final), strafe_speed_cruise_ms=rnd(cruise))


def m9(key):
    sim = cruise_sim(key)
    v0 = sim.tele()['ForwardSpeedMS']
    log = run_commands(sim, lambda t, s: Command(thrust=1.0, steer=1.0, drift=True), 3.0)
    slip = [math.atan2(-r['LateralSpeedMS'], r['ForwardSpeedMS']) * R2D for r in log]
    drifting = [r['bDrifting'] for r in log]
    v_end = log[-1]['SpeedMS']
    rate = mean([r['YawRateDegS'] for r in log[int(1 / DT):]])
    log2 = run_commands(sim, lambda t, s: Command(thrust=1.0), 3.0)
    allr = log + log2
    k = next((i for i in range(len(log), len(allr)) if not allr[i]['bDrifting']), None)
    kick = None
    if k is not None and k + 2 < len(allr):
        kick = allr[k + 2]['ForwardSpeedMS'] - allr[k - 1]['ForwardSpeedMS']
    return dict(slip_1s_deg=rnd(slip[int(1 / DT) - 1]), slip_2s_deg=rnd(slip[int(2 / DT) - 1]), slip_3s_deg=rnd(slip[-1]),
                drift_frames_pct=rnd(100.0 * sum(drifting) / len(drifting), 1), yaw_rate_degs=rnd(rate),
                speed_kept_pct=rnd(v_end / v0 * 100.0, 1), exit_kick_ms=rnd(kick),
                server_kick_ms=rnd(max(r['Debug'].get('DriftKick', 0.0) for r in allr) / 100.0))


def m10(key, final_rate):
    out = {}
    for L in (0.0, 100.0):
        name = 'lat%d' % L
        sim = cruise_sim(key, L)
        log = run_commands(sim, lambda t, s: Command(thrust=1.0, steer=1.0), 3.0)
        k0 = next(i for i, r in enumerate(log) if r['input']['steer'] != 0)
        before = sim.log[-len(log) - 1]
        pre = log[k0 - 1] if k0 > 0 else before

        def frames(fn):
            for i in range(k0, len(log)):
                if fn(log[i]):
                    return i - k0
            return None
        thr = 0.1 * final_rate
        r0s = pre['YawRateDegS']
        r0p = pre['pilot']['screen']['YawRateDegS']
        d = dict(turbine_frames=frames(lambda r: abs(r['pilot']['TurbineYawDeg'] - pre['pilot']['TurbineYawDeg']) > 0.5),
                 wheel_frames=frames(lambda r: abs(r['pilot']['WheelAngleDeg'] - pre['pilot']['WheelAngleDeg']) > 2.0),
                 server_turn_frames=frames(lambda r: r['YawRateDegS'] - r0s > thr),
                 screen_turn_frames=frames(lambda r: r['pilot']['screen']['YawRateDegS'] - r0p > thr))
        sim = new_sim(key, L)
        log = run_commands(sim, lambda t, s: Command(thrust=1.0), 2.0)
        k0 = next(i for i, r in enumerate(log) if r['input']['throttle'] != 0)
        pre = log[k0 - 1] if k0 > 0 else sim.log[-len(log) - 1]
        d['nozzle_frames'] = next((i - k0 for i in range(k0, len(log)) if abs(log[i]['pilot']['NozzlePitchDeg'] - pre['pilot']['NozzlePitchDeg']) > 0.2), None)
        d['screen_speed_frames'] = next((i - k0 for i in range(k0, len(log))
                                         if log[i]['pilot']['screen']['ForwardSpeedMS'] - pre['pilot']['screen']['ForwardSpeedMS'] > 0.1), None)
        out[name] = d
    return out


def m11(key):
    out = {}
    for skill in ('precise', 'sloppy'):
        out[skill] = {}
        for L in (0.0, 100.0):
            r = course.run_course(load_scheme(key), skill, L)
            r.pop('gates', None)
            out[skill]['lat%d' % L] = r
    return out


class OrbitPlanner:
    """Keep the target abeam to port at R0 m: course = bearing + 90 deg - k (r - R0) (clamped), left-turn rate
    feed-forward v / R0, speed 60 % of top, the target's height, look at the target."""

    def __init__(self, target_m, r0, speed):
        self.target = target_m
        self.r0 = r0
        self.speed = speed

    def __call__(self, sim, view):
        loc = [c * 0.01 for c in view['ActorLocCm']]
        dx, dy = self.target[0] - loc[0], self.target[1] - loc[1]
        r = math.hypot(dx, dy)
        b = math.atan2(dy, dx) * R2D
        corr = clamp(1.2 * (r - self.r0), -40.0, 40.0)
        course_deg = b + 90.0 + corr * -1.0
        v = max(view['ForwardSpeedMS'], 5.0)
        return Intent(course_deg=course_deg, speed=self.speed, alt=self.target[2], look_at=self.target,
                      yaw_rate_ff=-(v / self.r0) * R2D)


def m12(key, top):
    out = {}
    for skill in ('precise', 'sloppy'):
        out[skill] = {}
        for L in (0.0, 100.0):
            sim = Sim(load_scheme(key), latency_ms=L, alt_agl=START_AGL, pos_m=(0.0, 100.0), seed=3)
            alt = sim.tele()['AltitudeM']
            target = (0.0, 0.0, alt)
            sim.aim_targets = [((0.0, 0.0, alt * 100.0), 600.0)]
            planner = OrbitPlanner(target, 100.0, 0.6 * top)
            bot = course.Bot(sim, planner, course.Skill(skill), seed=11)
            run_commands(sim, lambda t, s: Command(), 2.0)
            n_run, n_meas = int(15 / DT), int(60 / DT)
            stats = dict(arc=0, arc_both=0, rng=0, spd=0, cam=0, sol=0)
            ranges, yaws, elevs = [], [], []
            shots0 = None
            for i in range(n_run + n_meas):
                raw = bot.raw()
                tele = sim.tele()
                tgt_cm = (target[0] * 100.0, target[1] * 100.0, target[2] * 100.0)
                ins = []
                for c in (0, 1):
                    yaw_raw, elev_raw, _ = sim.cannon_angles_raw(c, tgt_cm)
                    ins.append(abs(yaw_raw) <= sim.PP['CannonYawLimitDeg'] and sim.PP['CannonElevMinDeg'] <= elev_raw <= sim.PP['CannonElevMaxDeg'])
                    if c == 0:
                        yaws.append(yaw_raw)
                        elevs.append(elev_raw)
                loc = tele['ActorLocCm']
                rng_m = math.sqrt(sum((loc[k] - tgt_cm[k]) ** 2 for k in range(3))) / 100.0
                in_rng = 80.0 <= rng_m <= 120.0
                spd = tele['ForwardSpeedMS'] >= 0.5 * top
                cam = sim.aim_side == 'port'
                sol = any(ins) and in_rng and spd and cam
                raw.fire = sol
                sim.step(raw)
                if i == n_run:
                    shots0 = len(sim.cannon_shots)
                if i >= n_run:
                    stats['arc'] += any(ins)
                    stats['arc_both'] += all(ins)
                    stats['rng'] += in_rng
                    stats['spd'] += spd
                    stats['cam'] += cam
                    stats['sol'] += sol
                    ranges.append(rng_m)
            m = n_meas
            out[skill]['lat%d' % L] = dict(
                in_arc_pct=rnd(100.0 * stats['arc'] / m, 1), in_arc_both_pct=rnd(100.0 * stats['arc_both'] / m, 1),
                in_range_pct=rnd(100.0 * stats['rng'] / m, 1), speed_ok_pct=rnd(100.0 * stats['spd'] / m, 1),
                camera_port_pct=rnd(100.0 * stats['cam'] / m, 1), firing_solution_pct=rnd(100.0 * stats['sol'] / m, 1),
                shots_fired=(len(sim.cannon_shots) - shots0) // 2, range_mean_m=rnd(mean(ranges)),
                beam_yaw_mean_deg=rnd(mean(yaws[n_run:])), elev_mean_deg=rnd(mean(elevs[n_run:])),
                elev_max_deg=rnd(max(elevs[n_run:])))
    return out


def run_all(key):
    t0 = time.time()
    res = {}
    m1, m2, m6, top = m1_m2_m6(key)
    res['M1'], res['M2'] = m1, m2
    res['M3'], flare = m3(key)
    m6['brake_pitch_max_deg'] = rnd(flare)
    res['M4'], final_rate = m4(key)
    res['M5'] = m5(key)
    res['M6'] = m6
    res['M7'] = m7(key)
    res['M8'] = m8(key)
    res['M9'] = m9(key)
    res['M10'] = m10(key, final_rate)
    res['M11'] = m11(key)
    res['M12'] = m12(key, top)
    scheme = load_scheme(key)
    res = dict(meta=dict(scheme=scheme.key, scheme_enum=scheme.enum, label=scheme.label, source='sim',
                         sim='Docs/Airship/controls/sims/airship_sim.py', fps=30, start_agl_m=START_AGL,
                         generated=time.strftime('%Y-%m-%d %H:%M'), runtime_s=round(time.time() - t0, 1)), **res)
    return res


def main(argv):
    key = 'classic'
    out_dir = HERE
    i = 0
    while i < len(argv):
        if argv[i] == '--out':
            out_dir = argv[i + 1]
            i += 1
        else:
            key = argv[i]
        i += 1
    res = run_all(key)
    path = os.path.join(out_dir, '%s_metrics.json' % key)
    json.dump(res, open(path, 'w'), indent=1)
    for k in ['M%d' % n for n in range(1, 13)]:
        print(k, json.dumps(res[k]))
    print('wrote', path, 'in %.1f s' % res['meta']['runtime_s'])


if __name__ == '__main__':
    main(sys.argv[1:])
