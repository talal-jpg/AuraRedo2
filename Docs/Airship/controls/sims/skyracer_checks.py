"""Sky Racer checks: the scheme's own target bands and the behaviours the standard metrics do not cover (drift tiers,
mini-turbo, chain, client-pilot tier agreement under lag, boost burst, progressive S brake, gun deck, camera, and the
gate course over 5 seeds). Prints every number SCHEME_SKYRACER.md quotes. One process, about 40 s.

    python3 skyracer_checks.py            (reads skyracer_metrics.json and classic_metrics.json; run metrics.py first)
    python3 skyracer_checks.py --tune     (the bot-gain sweep behind SkyRacer.GAINS, about 75 s)
"""
import json
import math
import os
import sys

from airship_sim import Sim, Command, RawInput, load_scheme, run_commands, run_raw, wrap180, DT, R2D
import course
import scheme_skyracer  # noqa: F401  (registers 'skyracer')

HERE = os.path.dirname(os.path.abspath(__file__))


def load(key):
    return json.load(open(os.path.join(HERE, '%s_metrics.json' % key)))


# ---------------------------------------------------------------------------------------------------------------------
# 1. Target bands (Sky Racer's own; see SCHEME_SKYRACER.md section 9)
# ---------------------------------------------------------------------------------------------------------------------
BANDS = [
    ('M1 t80 (s)', lambda m: m['M1']['t80_s'], 2.3, 3.0),
    ('M1 speed at 2 s (m/s)', lambda m: m['M1']['speed_at_2s_ms'], 28.0, 36.0),
    ('M2 top steady (m/s)', lambda m: m['M2']['top_steady_ms'], 54.0, 58.0),
    ('M2 boost ratio', lambda m: m['M2']['boost_ratio'], 1.55, 1.75),
    ('M2 boost duration (s)', lambda m: m['M2']['boost_duration_s'], 3.0, 4.0),
    ('M3 stop time (s)', lambda m: m['M3']['stop_time_s'], 2.5, 3.2),
    ('M3 peak decel (g)', lambda m: m['M3']['peak_decel_g'], 1.8, 2.6),
    ('M3 mean decel (g)', lambda m: m['M3']['mean_decel_g'], 1.8, 2.3),
    ('M3 coast to half (s)', lambda m: m['M3']['coast_half_s'], 8.0, 15.0),
    ('M4 t63 (s)', lambda m: m['M4']['t63_s'], 0.0, 0.35),
    ('M4 t90 (s)', lambda m: m['M4']['t90_s'], 0.0, 0.7),
    ('M4 overshoot (%)', lambda m: m['M4']['overshoot_pct'], 0.0, 5.0),
    ('M4 turn rate (deg/s)', lambda m: m['M4']['final_yaw_rate_degs'], 36.0, 42.0),
    ('M4 bank (deg)', lambda m: m['M4']['bank_deg'], 18.0, 25.0),
    ('M4 grip slip at 8 s (deg)', lambda m: m['M4']['slip_8s_deg'], 0.0, 8.0),
    ('M4 height lost (m)', lambda m: m['M4']['alt_loss_8s_m'], -1.0, 1.0),
    ('M5 U-turn (s)', lambda m: m['M5']['time_s'], 4.5, 5.5),
    ('M6 drive pitch min (deg)', lambda m: m['M6']['drive_pitch_min_deg'], -6.0, -3.0),
    ('M6 boost pitch min (deg)', lambda m: m['M6']['boost_pitch_min_deg'], -7.0, -4.0),
    ('M6 brake pitch max (deg)', lambda m: m['M6']['brake_pitch_max_deg'], 2.0, 5.0),
    ('M7 climb (m/s)', lambda m: m['M7']['climb_rate_ms'], 13.0, 15.0),
    ('M7 sink (m/s)', lambda m: m['M7']['sink_rate_ms'], 15.0, 18.0),
    ('M7 +30 m overshoot (m)', lambda m: m['M7']['step30_overshoot_m'], 0.0, 6.0),
    ('M7 |vz| 1 s after release (m/s)', lambda m: m['M7']['step30_vz_1s_ms'], 0.0, 1.0),
    ('M8 strafe t90 (s)', lambda m: m['M8']['t90_s'], 0.0, 0.8),
    ('M8 strafe speed (m/s)', lambda m: m['M8']['strafe_speed_ms'], 13.0, 15.0),
    ('M9 drift slip at 2 s (deg)', lambda m: m['M9']['slip_2s_deg'], 20.0, 30.0),
    ('M9 slip change 2 -> 3 s (deg)', lambda m: abs(m['M9']['slip_3s_deg'] - m['M9']['slip_2s_deg']), 0.0, 3.0),
    ('M9 speed kept (%)', lambda m: m['M9']['speed_kept_pct'], 90.0, 102.0),
    ('M9 exit kick (m/s)', lambda m: m['M9']['exit_kick_ms'], 5.0, 10.0),
    ('M10 host screen turn (frames)', lambda m: m['M10']['lat0']['screen_turn_frames'], 0, 1),
    ('M10 client 100 ms screen turn (frames)', lambda m: m['M10']['lat100']['screen_turn_frames'], 0, 8),
    ('M11 precise 0 ms missed', lambda m: m['M11']['precise']['lat0']['gates_missed'], 0, 0),
    ('M11 precise 100 ms missed', lambda m: m['M11']['precise']['lat100']['gates_missed'], 0, 0),
    ('M11 precise time vs Classic (%)', None, -100.0, -12.0),
    ('M11 precise line error mean (m)', lambda m: m['M11']['precise']['lat0']['line_error_mean_m'], 0.0, 3.0),
    ('M12 precise in arc (%)', lambda m: m['M12']['precise']['lat0']['in_arc_pct'], 90.0, 100.0),
    ('M12 sloppy 100 ms in arc (%)', lambda m: m['M12']['sloppy']['lat100']['in_arc_pct'], 80.0, 100.0),
    ('M12 sloppy 100 ms firing solution (%)', lambda m: m['M12']['sloppy']['lat100']['firing_solution_pct'], 60.0, 100.0),
]


def bands(m, c):
    print('\n== 1. Target bands (skyracer_metrics.json; Classic for reference) ==')
    print('%-42s %10s %10s %16s  %s' % ('metric', 'Sky Racer', 'Classic', 'band', ''))
    n_ok = 0
    for name, fn, lo, hi in BANDS:
        if fn is None:
            v = 100.0 * (m['M11']['precise']['lat0']['completion_time_s'] / c['M11']['precise']['lat0']['completion_time_s'] - 1.0)
            vc = 0.0
        else:
            v, vc = fn(m), fn(c)
        ok = v is not None and lo - 1e-9 <= v <= hi + 1e-9
        n_ok += ok
        print('%-42s %10s %10s %16s  %s' % (name, v, vc, '%g .. %g' % (lo, hi), 'ok' if ok else 'OUT'))
    print('in band: %d of %d' % (n_ok, len(BANDS)))


# ---------------------------------------------------------------------------------------------------------------------
def cruise(key='skyracer', latency=0.0):
    s = Sim(load_scheme(key), alt_agl=60, latency_ms=latency)
    run_commands(s, lambda t, sim: Command(), 2.0)
    run_commands(s, lambda t, sim: Command(thrust=1.0), 20.0)
    return s


def drift_checks():
    print('\n== 2. Drift, mini-turbo, chain (host pilot, from cruise at full drive) ==')
    # a. charge timing by steer-in
    for label, st in (('full in (D held)', 1.0), ('neutral (stick centred)', 0.0), ('counter-steer (half)', -0.5)):
        s = cruise()
        times = {}
        n = 0
        while n < int(5 / DT):
            raw = RawInput(throttle=1.0, steer=1.0 if n < 3 else st, brake=True)
            rec = s.step(raw)
            n += 1
            tier = scheme_skyracer._tier(s.P, rec['DriftCharge'])
            for k in (1, 2, 3):
                if tier >= k and k not in times:
                    times[k] = round(n * DT, 2)
        print('  tier times, %-24s T1 %s s  T2 %s s  T3 %s s' % (label, times.get(1), times.get(2), times.get(3)))
    # b. turbo by tier: release at each tier, speed and fuel against a grip turn of the same length
    for tier, hold in ((0, 0.4), (1, 0.6), (2, 1.2), (3, 2.1)):
        s = cruise()
        s.server.fuel = 50.0
        run_raw(s, lambda t, sim: RawInput(throttle=1.0, steer=1.0, brake=True), hold)
        v_rel = s.tele()['SpeedMS']
        f0 = s.tele()['BoostFuel']
        lg = run_raw(s, lambda t, sim: RawInput(throttle=1.0), 3.0)
        crs0 = lg[0]['CourseDeg']
        settle = next((i for i, r in enumerate(lg) if abs(math.atan2(-r['LateralSpeedMS'], r['ForwardSpeedMS']) * R2D) < 3.0), None)
        swing = max(abs(wrap180(r['CourseDeg'] - crs0)) for r in lg[:int(1.0 / DT)])
        kick = max(r['Debug'].get('DriftKick', 0.0) for r in lg) / 100.0
        print('  release at %.1f s (tier %d): kick %.1f m/s, speed at release %.1f -> +1 s %.1f, +2 s %.1f m/s, peak %.1f, '
              'fuel %+.1f, exit swing %.1f deg, slip < 3 deg after %.2f s'
              % (hold, s.server.sky_last_tier, kick, v_rel, lg[29]['SpeedMS'], lg[59]['SpeedMS'], max(r['SpeedMS'] for r in lg),
                 lg[0]['BoostFuel'] - f0, swing, (settle + 1) * DT if settle is not None else -1))
    # c. chain: three 1.2 s drifts, 0.8 s apart
    s = cruise()
    kicks = []
    for k in range(3):
        d = 1.0 if k % 2 == 0 else -1.0
        run_raw(s, lambda t, sim: RawInput(throttle=1.0, steer=d, brake=True), 1.2)
        lg = run_raw(s, lambda t, sim: RawInput(throttle=1.0), 0.8)
        kicks.append(max(r['Debug'].get('DriftKick', 0.0) for r in lg) / 100.0)
    print('  chain of three T2 drifts 0.8 s apart: kicks %s m/s (links %s)' % ([round(x, 2) for x in kicks], [c for _, _, c in s.server.sky_releases]))
    # e. (review) the keyboard chord: the same 1.2 s drift with W held, with W let go (A/D + X only), and with S held
    for label, thr in (('W held', 1.0), ('no W (A/D + X)', 0.0), ('S held (S + X)', -1.0)):
        s = cruise()
        lg = run_raw(s, lambda t, sim: RawInput(throttle=thr, steer=1.0, brake=True), 1.2)
        v0 = lg[0]['SpeedMS']
        lg2 = run_raw(s, lambda t, sim: RawInput(throttle=1.0), 2.0)
        print('  1.2 s drift, %-15s: course %+.1f deg, speed %.1f -> %.1f m/s at release, tier %d, kick %.1f m/s, %.1f m/s 2 s later'
              % (label, wrap180(lg[-1]['CourseDeg'] - lg[0]['CourseDeg']), v0, lg[-1]['SpeedMS'], s.server.sky_last_tier,
                 max(r['Debug'].get('DriftKick', 0.0) for r in lg2) / 100.0, lg2[-1]['SpeedMS']))
    # d. one-key drift: what a drift costs if never released for 6 s
    s = cruise()
    lg = run_raw(s, lambda t, sim: RawInput(throttle=1.0, steer=1.0, brake=True), 6.0)
    print('  6 s held drift: speed %.1f -> %.1f m/s, path turn rate %.1f deg/s, slip %.1f deg, height change %.2f m'
          % (lg[0]['SpeedMS'], lg[-1]['SpeedMS'], (wrap180(lg[-1]['CourseDeg'] - lg[-31]['CourseDeg'])) / 1.0,
             lg[-1]['Debug'].get('SlipNow', 0.0), lg[-1]['AltitudeM'] - lg[0]['AltitudeM']))


def lag_tiers():
    print('\n== 3. Client pilot, 100 ms each way: tier the pilot sees at release vs the tier the server pays ==')
    for grace in (0.0, 0.03):
        mism, total, early = 0, 0, 0
        for frames in range(12, 72, 1):
            s = cruise(latency=100.0)
            s.P['SkyTierGrace'] = grace
            run_raw(s, lambda t, sim: RawInput(throttle=1.0, steer=1.0, brake=True), frames * DT)
            run_raw(s, lambda t, sim: RawInput(throttle=1.0), 0.6)
            p = s.pilot_fm.sky_releases[-1][1] if s.pilot_fm.sky_releases else 0
            q = s.server.sky_releases[-1][1] if s.server.sky_releases else 0
            total += 1
            mism += p != q
            early += q < p
        print('  grace %.2f: %d of %d hold lengths (0.4-2.4 s, 1-frame steps) give a different tier, %d of them lower on the server'
              % (grace, mism, total, early))
    # predicted feedback timing
    s = cruise(latency=100.0)
    lg = run_raw(s, lambda t, sim: RawInput(throttle=1.0, steer=1.0, brake=True), 1.0)
    k_pilot = next(i for i, r in enumerate(lg) if s.pilot_fm.sky_drift_dir or True)
    k_srv = next(i for i, r in enumerate(lg) if r['DriftDir'] != 0)
    k_screen = next(i for i, r in enumerate(lg) if r['pilot']['screen']['YawRateDegS'] > 10.0)
    print('  drift start: pilot HUD / FX / camera frame 0, server frame %d, hull turning on the pilot\'s screen frame %d' % (k_srv, k_screen))


def burst_brake_aim():
    print('\n== 4. Boost burst, progressive S brake, gun deck ==')
    s = cruise()
    lg = run_raw(s, lambda t, sim: RawInput(throttle=1.0, boost=(t < DT)), 2.0)
    on = sum(1 for r in lg if r['BoostActive']) * DT
    print('  one-frame Shift tap: boost on for %.2f s, fuel %.0f -> %.0f, peak %.1f m/s' % (on, 100.0, lg[-1]['BoostFuel'], max(r['ForwardSpeedMS'] for r in lg)))
    for tap in (0.1, 0.2, 0.5):
        s = cruise()
        v0 = s.tele()['ForwardSpeedMS']
        lg = run_raw(s, lambda t, sim: RawInput(throttle=-1.0 if t < tap else 1.0), 2.0)
        print('  S tap %.1f s in a W-held cruise: speed %.1f -> min %.1f m/s' % (tap, v0, min(r['ForwardSpeedMS'] for r in lg)))
    s = cruise()
    v0 = s.tele()['ForwardSpeedMS']
    lg = run_raw(s, lambda t, sim: RawInput(throttle=-1.0), 6.0)
    k = next((i for i, r in enumerate(lg) if r['ForwardSpeedMS'] <= 0.5), None)
    print('  S held from cruise: stop after %.2f s, then reverse to %.1f m/s' % ((k + 1) * DT if k is not None else -1, min(r['ForwardSpeedMS'] for r in lg)))
    for aim in (False, True):
        s = cruise()
        lg = run_raw(s, lambda t, sim: RawInput(throttle=1.0, steer=1.0, aim=aim), 6.0)
        print('  full steer at cruise, aim %-5s: bank %.1f deg, turn %.1f deg/s, speed %.1f m/s'
              % (aim, sum(r['RollDeg'] for r in lg[-60:]) / 60, sum(r['YawRateDegS'] for r in lg[-60:]) / 60, lg[-1]['ForwardSpeedMS']))


def camera():
    print('\n== 5. Camera: view yaw minus the hull yaw on the pilot\'s screen (+ = into the turn), full steer at cruise ==')
    for key in ('classic', 'skyracer'):
        for L in (0.0, 100.0):
            s = cruise(key, L)
            lg = run_commands(s, lambda t, sim: Command(thrust=1.0, steer=1.0), 3.0)
            pts = ' '.join('%.2fs %+5.1f' % ((i + 1) * DT, wrap180(lg[i]['pilot']['cam_yaw'] - lg[i]['pilot']['screen']['YawDeg'])) for i in (2, 5, 10, 20, 89))
            print('  %-8s %3d ms: %s' % (key, L, pts))


def course_seeds():
    print('\n== 6. Gate course over 5 seeds (7 = the official one): mean time, gates missed, line error mean / max, steer reversals ==')
    for key in ('classic', 'skyracer'):
        for skill in ('precise', 'sloppy'):
            for L in (0.0, 100.0):
                rs = [course.run_course(load_scheme(key), skill, L, seed=sd) for sd in (7, 1, 2, 3, 4)]
                n = len(rs)
                print('  %-8s %-7s %3d ms: %.1f s, missed %.1f (%s), line %.1f / %.1f m, reversals %.0f/min'
                      % (key, skill, L, sum((r['completion_time_s'] or 200.0) for r in rs) / n, sum(r['gates_missed'] for r in rs) / n,
                         ' '.join(str(r['gates_missed']) for r in rs), sum((r['line_error_mean_m'] or 50) for r in rs) / n,
                         max((r['line_error_max_m'] or 50) for r in rs), sum(r['steer_reversals_per_min'] for r in rs) / n))
    # drifts the precise bot uses (official seed)
    cap = {}
    _Sim = course.Sim

    def S(*a, **k):
        cap['sim'] = _Sim(*a, **k)
        return cap['sim']
    course.Sim = S
    for skill in ('precise', 'sloppy'):
        for L in (0.0, 100.0):
            course.run_course(load_scheme('skyracer'), skill, L)
            rel = cap['sim'].server.sky_releases
            print('  skyracer %-7s %3d ms (seed 7): %d mini-turbos, tiers %s, chain links %s' % (skill, L, len(rel), [k for _, k, _ in rel], [c for _, _, c in rel]))
    course.Sim = _Sim
    # the same scheme flown without the drift (grip only, the same tuned gains)
    from scheme_skyracer import SkyRacer

    class Grip(SkyRacer):
        GAINS = dict(SkyRacer.GAINS, drift=0.0, turn_frac=0.75)
    for L in (0.0, 100.0):
        r = course.run_course(Grip(), 'precise', L)
        print('  skyracer precise, grip only (no drift, line planned for grip), %3d ms: %s s, missed %d, line %s / %s m'
              % (L, r['completion_time_s'], r['gates_missed'], r['line_error_mean_m'], r['line_error_max_m']))


def tune():
    """course.tune_bot's stage 1 (the same grid and score), then its stage 2 extended with turn_frac 1.0 / 1.1 (the drift
    turns faster than the grip table the planner reads) and the drift release lead. About 75 s."""
    import itertools
    from scheme_skyracer import SkyRacer

    def score(g):
        tot = 0.0
        for L in (0.0, 100.0):
            r = course.run_course(SkyRacer(), 'precise', L, gains=g)
            tot += r['gates_missed'] * 100 + (r['completion_time_s'] or 200.0) + 2 * (r['line_error_max_m'] or 50.0)
        return tot
    base = dict(SkyRacer.GAINS)
    best = (score(base), base)
    print('current GAINS: score %.1f' % best[0])
    for ct, lag, crs, rd in itertools.product((0.5, 0.8, 1.2), (0.35, 0.5, 0.65), (0.7, 1.0, 1.6), (0.3, 0.6)):
        g = dict(base, ct=ct, lag=lag, course=crs, rate_damp=rd)
        sc = score(g)
        if sc < best[0]:
            best = (sc, g)
    print('stage 1: score %.1f' % best[0], {k: best[1][k] for k in ('ct', 'lag', 'course', 'rate_damp')})
    for margin, frac, el in itertools.product((5.0, 7.0, 9.0), (0.85, 0.95, 1.0, 1.1), (0.9, 1.1, 1.4)):
        g = dict(best[1], margin=margin, turn_frac=frac, exit_lead=el)
        sc = score(g)
        if sc < best[0]:
            best = (sc, g)
    print('stage 2: score %.1f' % best[0], best[1])


def main(argv):
    if '--tune' in argv:
        tune()
        return
    m, c = load('skyracer'), load('classic')
    bands(m, c)
    drift_checks()
    lag_tiers()
    burst_brake_aim()
    camera()
    course_seeds()


if __name__ == '__main__':
    main(sys.argv[1:])
