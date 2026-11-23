"""Galleon-only checks (the numbers in SCHEME_GALLEON.md that M1-M12 do not cover): telegraph steps and settling,
hold-W timing, helm response and release carry, bank timing, the stern swing, broadside stations, sidle, the brake,
and (review, with --course-seeds) the gate course with beam glances.

Run: python3 galleon_checks.py [--json out.json] [--course-seeds] [key=value ...]
     (flight overrides, e.g. SteerTau=0.2; about 5 s, --course-seeds adds the 12-seed sloppy course for Galleon and
     Classic, about 30 s more)
"""
import json
import math
import sys

from airship_sim import Sim, Command, RawInput, load_scheme, run_commands, run_raw, wrap180, DT, R2D, D2R
import scheme_galleon as gal

START_AGL = 60.0


def new_sim(flight=None, pawn=None, latency=0.0, key='galleon'):
    sim = Sim(load_scheme(key), latency_ms=latency, alt_agl=START_AGL, seed=1, flight=flight, pawn=pawn)
    run_commands(sim, lambda t, s: Command(), 2.0)
    return sim


def first(log, fn):
    for i, r in enumerate(log):
        if fn(r):
            return round((i + 1) * DT, 2)
    return None


def cruise(sim, thrust=1.0, seconds=20.0):
    run_commands(sim, lambda t, s: Command(thrust=thrust), seconds)


def telegraph(flight, pawn):
    out = {}
    # notch speeds and settle (from rest, one notch at a time)
    for name, thrust in (('SLOW', 0.33), ('HALF', 0.6), ('FULL', 1.0)):
        sim = new_sim(flight, pawn)
        log = run_commands(sim, lambda t, s: Command(thrust=thrust), 20.0)
        v = [r['ForwardSpeedMS'] for r in log]
        final = sum(v[-60:]) / 60
        out[name] = dict(speed_ms=round(final, 2), t90_s=first(log, lambda r: r['ForwardSpeedMS'] >= 0.9 * final),
                         overshoot_ms=round(max(v) - final, 2))
    # step down Full -> Half -> Slow -> Stop (each 12 s), and Full -> Stop directly
    sim = new_sim(flight, pawn)
    cruise(sim)
    for name, thrust in (('FULL->HALF', 0.6), ('HALF->SLOW', 0.33), ('SLOW->STOP', 0.0)):
        v0 = sim.tele()['ForwardSpeedMS']
        log = run_commands(sim, lambda t, s: Command(thrust=thrust), 12.0)
        v = [r['ForwardSpeedMS'] for r in log]
        final = v[-1]
        out[name] = dict(from_ms=round(v0, 1), to_ms=round(final, 2),
                         t90_s=first(log, lambda r: abs(r['ForwardSpeedMS'] - final) <= 0.1 * abs(v0 - final)),
                         undershoot_ms=round(final - min(v), 2))
    sim = new_sim(flight, pawn)
    cruise(sim)
    v0 = sim.tele()['ForwardSpeedMS']
    log = run_commands(sim, lambda t, s: Command(thrust=0.0), 20.0)
    out['FULL->STOP'] = dict(half_s=first(log, lambda r: r['ForwardSpeedMS'] <= 0.5 * v0),
                             stop_s=first(log, lambda r: r['ForwardSpeedMS'] <= 0.5),
                             dist_m=round((log[-1]['ActorLocCm'][0] - sim.log[-len(log) - 1]['ActorLocCm'][0]) / 100.0, 1),
                             final_ms=round(log[-1]['ForwardSpeedMS'], 2))
    # astern from stop
    sim = new_sim(flight, pawn)
    log = run_commands(sim, lambda t, s: Command(thrust=-1.0), 12.0)
    out['STOP->ASTERN'] = dict(speed_ms=round(log[-1]['ForwardSpeedMS'], 2))
    # hold W from STOP (auto-repeat): when each notch arrives
    sim = new_sim(flight, pawn)
    log = run_raw(sim, lambda t, s: RawInput(throttle=1.0), 1.5)
    when = {}
    for i, r in enumerate(log):
        o = gal.order_index(r['input']['throttle'] / 127.0)
        when.setdefault(gal.ORDER_NAMES[o], round(i * DT, 3))
    out['hold_W_from_STOP'] = when
    # hold S from FULL: stops at STOP (detent)
    sim = new_sim(flight, pawn)
    cruise(sim)
    log = run_raw(sim, lambda t, s: RawInput(throttle=-1.0), 2.0)
    out['hold_S_from_FULL_ends_at'] = gal.ORDER_NAMES[gal.order_index(log[-1]['input']['throttle'] / 127.0)]
    return out


def helm(flight, pawn, thrust, key='galleon'):
    """Full helm for 6 s at the notch (Classic: the throttle held), then release: rate build, bank build, carry."""
    sim = new_sim(flight, pawn, key=key)
    cruise(sim, thrust)
    alt0 = sim.tele()['AltitudeM']
    y0 = sim.tele()['YawDeg']
    log = run_commands(sim, lambda t, s: Command(thrust=thrust, steer=1.0), 6.0)
    r = [x['YawRateDegS'] for x in log]
    final = sum(r[-30:]) / 30
    bank = [x['RollDeg'] for x in log]
    bfinal = sum(bank[-30:]) / 30
    yaw_rel = wrap180(log[-1]['YawDeg'] - y0)
    rel = run_commands(sim, lambda t, s: Command(thrust=thrust), 6.0)
    carry, prev = 0.0, log[-1]['YawDeg']
    for x in rel:
        carry += wrap180(x['YawDeg'] - prev)
        prev = x['YawDeg']
    stop_t = first(rel, lambda x: abs(x['YawRateDegS']) < 1.0)
    return dict(rate_degs=round(final, 1), t63_s=first(log, lambda x: x['YawRateDegS'] >= 0.63 * final),
                t90_s=first(log, lambda x: x['YawRateDegS'] >= 0.9 * final),
                overshoot_pct=round(max(0.0, (max(r) - final) / final * 100), 1),
                bank_deg=round(bfinal, 1), bank_t50_s=first(log, lambda x: x['RollDeg'] >= 0.5 * bfinal),
                bank_t90_s=first(log, lambda x: x['RollDeg'] >= 0.9 * bfinal),
                bank_overshoot_deg=round(max(bank) - bfinal, 1), speed_ms=round(log[-1]['ForwardSpeedMS'], 1),
                alt_change_m=round(log[-1]['AltitudeM'] - alt0, 2),
                release_carry_deg=round(carry, 1), release_stop_s=stop_t,
                release_bank_level_s=first(rel, lambda x: abs(x['RollDeg']) < 2.0))


def swing(flight, pawn, thrust, seconds=2.0):
    sim = new_sim(flight, pawn)
    cruise(sim, thrust)
    t0 = sim.tele()
    v0, y0 = t0['ForwardSpeedMS'], t0['YawDeg']
    log = run_commands(sim, lambda t, s: Command(thrust=thrust, steer=1.0, drift=True), seconds)
    slip = [math.atan2(-x['LateralSpeedMS'], x['ForwardSpeedMS']) * R2D for x in log]
    yaw = 0.0
    prev = y0
    for x in log:
        yaw += wrap180(x['YawDeg'] - prev)
        prev = x['YawDeg']
    course0 = t0['CourseDeg']
    course_change = wrap180(log[-1]['CourseDeg'] - course0)
    out = run_commands(sim, lambda t, s: Command(thrust=thrust), 3.0)
    return dict(from_ms=round(v0, 1), heading_change_deg=round(yaw, 1), course_change_deg=round(course_change, 1),
                slip_max_deg=round(max(slip), 1), speed_end_ms=round(log[-1]['SpeedMS'], 1),
                speed_kept_pct=round(log[-1]['SpeedMS'] / v0 * 100, 1), bank_max_deg=round(max(x['RollDeg'] for x in log), 1),
                exit_speed_3s_ms=round(out[-1]['ForwardSpeedMS'], 1),
                exit_kick_ms=round(max(x['Debug'].get('DriftKick', 0.0) for x in out) / 100.0, 2),
                slip_after_1s_deg=round(math.atan2(-out[29]['LateralSpeedMS'], out[29]['ForwardSpeedMS']) * R2D, 1))


def camera_response(flight, pawn, key='galleon'):
    """Frames (30 fps) from the first A/D input on the wire to: the pilot's camera yaw moving 0.5 deg relative to its
    pre-press path (look-ahead), and the hull's turn on the pilot's screen (10 % of the final rate); host and client
    100 ms each way. Classic for comparison (its camera only follows the hull)."""
    out = {}
    for L in (0.0, 100.0):
        sim = Sim(load_scheme(key), latency_ms=L, alt_agl=START_AGL, seed=1, flight=flight if key == 'galleon' else None,
                  pawn=pawn if key == 'galleon' else None)
        run_commands(sim, lambda t, s: Command(), 2.0)
        cruise(sim, 1.0)
        log = run_commands(sim, lambda t, s: Command(thrust=1.0, steer=1.0), 2.0)
        k0 = next(i for i, r in enumerate(log) if r['input']['steer'] != 0)
        pre = log[k0 - 1] if k0 > 0 else sim.log[-len(log) - 1]
        cam0 = pre['pilot']['cam_yaw']
        r0 = pre['pilot']['screen']['YawRateDegS']
        cam = next((i - k0 for i in range(k0, len(log)) if abs(wrap180(log[i]['pilot']['cam_yaw'] - cam0)) > 0.5), None)
        scr = next((i - k0 for i in range(k0, len(log)) if log[i]['pilot']['screen']['YawRateDegS'] - r0 > 3.5), None)
        cam_10 = next((i - k0 for i in range(k0, len(log)) if abs(wrap180(log[i]['pilot']['cam_yaw'] - cam0)) > 5.0), None)
        out['lat%d' % L] = dict(camera_frames=cam, camera_5deg_frames=cam_10, screen_turn_frames=scr)
    return out


def uturn(flight, thrust, t_swing, key='galleon'):
    """From cruise at the notch: full helm (+ brake for the first t_swing s = the stern swing) until the course over
    ground has turned 180 deg: time, diameter (offset across the entry line), speed at the end."""
    sim = new_sim(flight, None, key=key)
    cruise(sim, thrust)
    t0 = sim.tele()
    c0, p0, v0 = t0['CourseDeg'], t0['ActorLocCm'], t0['ForwardSpeedMS']
    right0 = (-math.sin(c0 * D2R), math.cos(c0 * D2R))
    turned, prev, n, r = 0.0, c0, 0, None
    while turned < 180.0 and n < 600:
        r = sim.step(sim.scheme.command_raw(sim, Command(thrust=thrust, steer=1.0, drift=(n * DT < t_swing))))
        turned += wrap180(r['CourseDeg'] - prev)
        prev = r['CourseDeg']
        n += 1
    p = r['ActorLocCm']
    off = ((p[0] - p0[0]) * right0[0] + (p[1] - p0[1]) * right0[1]) / 100.0
    return dict(time_s=round(n * DT, 2), diameter_m=round(off, 1), speed_end_ms=round(r['SpeedMS'], 1), from_ms=round(v0, 1))


def course_seeds(key, seeds=range(1, 13)):
    """Gate course, sloppy bot, 12 noise / wind seeds: mean gates missed and completion time (the official M11 uses
    seed 7 only; the sloppy bot's result moves by 1-3 gates between seeds)."""
    import course
    out = {}
    for L in (0.0, 100.0):
        miss, tim = [], []
        for seed in seeds:
            res = course.run_course(load_scheme(key), 'sloppy', L, seed=seed)
            miss.append(res['gates_missed'])
            tim.append(res['completion_time_s'] or 200.0)
        out['lat%d' % L] = dict(gates_missed_mean=round(sum(miss) / len(miss), 2), gates_missed=miss,
                                time_mean_s=round(sum(tim) / len(tim), 1))
    return out


def beam_glances(seeds=(7, 1, 2, 3)):
    """REVIEW: the gate course while the pilot glances out over the side without firing (60-90 deg off the bow for
    1-2 s every 6-10 s): broadside stations from beam watch alone (as designed, GalleonStationsFireHoldTime 0) against
    stations only after an own broadside (the review rule, 6 s). Precise and sloppy bot, 0 / 100 ms, 4 seeds."""
    import random
    import course
    base = course.Bot

    class GlanceBot(base):
        def __init__(self, *a, **kw):
            base.__init__(self, *a, **kw)
            self.g = random.Random(41)
            self.next, self.until, self.off, self.back = 5.0 + self.g.uniform(0, 3), -1.0, 0.0, False

        def raw(self):
            r = base.raw(self)
            t = self.sim.time
            v = self.sim.pilot_view()
            if t >= self.next and t >= self.until:
                self.until = t + self.g.uniform(1.0, 2.0)
                self.off = self.g.choice((-1.0, 1.0)) * self.g.uniform(60.0, 90.0)
                self.next = t + self.g.uniform(6.0, 10.0)
            if t < self.until:
                r.cam_yaw, r.cam_pitch, r.look, self.back = wrap180(v['YawDeg'] + self.off), -16.0, True, True
            elif self.back:
                r.cam_yaw, r.cam_pitch, r.look, self.back = v['YawDeg'], -16.0, True, False
            return r

    out = {}
    course.Bot = GlanceBot
    try:
        for hold, name in ((0.0, 'designed'), (6.0, 'review')):
            out[name] = {}
            for skill in ('precise', 'sloppy'):
                for L in (0.0, 100.0):
                    miss, tim = [], []
                    for seed in seeds:
                        sch = load_scheme('galleon')
                        sch.pawn = dict(sch.pawn, GalleonStationsFireHoldTime=hold)
                        res = course.run_course(sch, skill, L, seed=seed)
                        miss.append(res['gates_missed'])
                        tim.append(res['completion_time_s'] or 200.0)
                    out[name]['%s_lat%d' % (skill, L)] = dict(gates_missed=miss, gates_missed_mean=round(sum(miss) / len(miss), 2),
                                                             time_mean_s=round(sum(tim) / len(tim), 1))
    finally:
        course.Bot = base
    return out


def stations(flight, pawn):
    sim = new_sim(flight, pawn)
    cruise(sim, 0.6)
    log = run_raw(sim, lambda t, s: RawInput(throttle=0.0, steer=1.0, aim=True), 5.0)
    return dict(bank_deg_aiming=round(sum(x['RollDeg'] for x in log[-30:]) / 30, 1),
                rate_degs=round(sum(x['YawRateDegS'] for x in log[-30:]) / 30, 1))


def strafe_brake_lift(flight, pawn):
    out = {}
    sim = new_sim(flight, pawn)
    log = run_commands(sim, lambda t, s: Command(strafe=1.0), 4.0)
    final = sum(x['LateralSpeedMS'] for x in log[90:]) / len(log[90:])
    out['sidle'] = dict(speed_ms=round(final, 2), t90_s=first(log, lambda x: x['LateralSpeedMS'] >= 0.9 * final),
                        bank_deg=round(log[-1]['RollDeg'], 1))
    sim = new_sim(flight, pawn)
    cruise(sim)
    v0 = sim.tele()['ForwardSpeedMS']
    log = run_commands(sim, lambda t, s: Command(brake=True), 8.0)
    v = [v0] + [x['ForwardSpeedMS'] for x in log]
    k = next((i for i in range(1, len(v)) if v[i] <= 0.5), None)
    dec = max(-(v[i + 1] - v[i - 1]) / (2 * DT) for i in range(1, len(v) - 1)) / 9.81
    out['brake'] = dict(stop_s=round(k * DT, 2) if k else None, peak_g=round(dec, 2), backup_ms=round(min(v), 2),
                        flare_deg=round(max(x['PitchDeg'] for x in log), 1))
    return out


def main(argv):
    flight = {}
    out_path = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == '--json':
            out_path = argv[i + 1]
            i += 1
        elif '=' in a:
            k, v = a.split('=', 1)
            flight[k] = (v.lower() == 'true') if v.lower() in ('true', 'false') else float(v)
        i += 1
    res = dict(telegraph=telegraph(flight, None), helm_half=helm(flight, None, 0.6), helm_full=helm(flight, None, 1.0),
               helm_full_classic=helm(None, None, 1.0, 'classic'),
               uturn=dict(galleon_helm=uturn(flight, 1.0, 0.0), galleon_swing_1_5s=uturn(flight, 1.0, 1.5),
                          galleon_swing_2_5s=uturn(flight, 1.0, 2.5), galleon_half_helm=uturn(flight, 0.6, 0.0),
                          galleon_half_swing_2_5s=uturn(flight, 0.6, 2.5), classic_helm=uturn(None, 1.0, 0.0, 'classic'),
                          classic_drift_1_5s=uturn(None, 1.0, 1.5, 'classic')),
               swing_full=swing(flight, None, 1.0), swing_half=swing(flight, None, 0.6), stations=stations(flight, None),
               camera_galleon=camera_response(flight, None), camera_classic=camera_response(None, None, 'classic'))
    res.update(strafe_brake_lift(flight, None))
    if '--course-seeds' in argv:
        res['course_sloppy_12_seeds'] = dict(galleon=course_seeds('galleon'), classic=course_seeds('classic'))
        res['beam_glances'] = beam_glances()
    for k, v in res.items():
        print(k, json.dumps(v))
    if out_path:
        json.dump(res, open(out_path, 'w'), indent=1)


if __name__ == '__main__':
    main(sys.argv[1:])
