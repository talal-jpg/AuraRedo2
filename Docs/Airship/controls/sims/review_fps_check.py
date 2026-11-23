"""Review check (2026-11-23): every scheme flown open loop at dt = 1/30 s and 1/120 s (host pilot, the same maneuvers:
cruise, full turn, release, drift / swing, climb and hold, brake, hover). Prints both and the difference; a scheme
whose loops were too stiff for the step would show oscillation (the *_osc rows) or diverge.

    cd Docs/Airship/controls/sims; python3 review_fps_check.py [classic galleon skyracer pointfly]   (about 8 s)
"""
import math, sys, os
sys.path.insert(0, os.getcwd())
from airship_sim import Sim, Command, load_scheme, wrap180
import scheme_galleon, scheme_skyracer, scheme_pointfly  # noqa

def fly(key, dt, plan):
    sim = Sim(load_scheme(key), latency_ms=0, alt_agl=60.0)
    sim.dt = dt
    out = {}
    t = 0.0
    log = []
    for name, secs, cmd in plan:
        n = int(round(secs / dt))
        seg = []
        for i in range(n):
            raw = sim.scheme.command_raw(sim, cmd(sim))
            rec = sim.step(raw)
            seg.append(rec)
        out[name] = seg
    return out

def last(seg, k, frac=0.25):
    m = max(1, int(len(seg) * frac))
    xs = [r[k] for r in seg[-m:]]
    return sum(xs) / len(xs)

def osc(seg, k, frac=0.5):
    m = max(2, int(len(seg) * frac))
    xs = [r[k] for r in seg[-m:]]
    mu = sum(xs) / len(xs)
    return math.sqrt(sum((x - mu) ** 2 for x in xs) / len(xs))

PLAN = [
    ('settle', 2.0, lambda s: Command()),
    ('cruise', 20.0, lambda s: Command(thrust=1.0)),
    ('turn', 8.0, lambda s: Command(thrust=1.0, steer=1.0)),
    ('unturn', 4.0, lambda s: Command(thrust=1.0)),
    ('drift', 3.0, lambda s: Command(thrust=1.0, steer=1.0, drift=True)),
    ('after', 4.0, lambda s: Command(thrust=1.0)),
    ('climb', 3.0, lambda s: Command(thrust=1.0, lift=1.0)),
    ('hold', 5.0, lambda s: Command(thrust=1.0)),
    ('brake', 6.0, lambda s: Command(brake=True)),
    ('hover', 6.0, lambda s: Command()),
]

def summary(out):
    d = {}
    d['cruise_v'] = last(out['cruise'], 'ForwardSpeedMS')
    d['cruise_pitch'] = min(r['PitchDeg'] for r in out['cruise'])
    d['turn_rate'] = last(out['turn'], 'YawRateDegS')
    d['turn_bank'] = last(out['turn'], 'RollDeg')
    d['turn_roll_osc'] = osc(out['turn'], 'RollDeg')
    d['turn_rate_osc'] = osc(out['turn'], 'YawRateDegS')
    d['turn_alt_chg'] = out['turn'][-1]['AltitudeM'] - out['turn'][0]['AltitudeM']
    d['unturn_rate'] = last(out['unturn'], 'YawRateDegS')
    d['unturn_roll'] = last(out['unturn'], 'RollDeg')
    d['drift_rate'] = last(out['drift'], 'YawRateDegS', 0.5)
    d['drift_v_end'] = out['drift'][-1]['ForwardSpeedMS']
    d['after_v'] = out['after'][-1]['ForwardSpeedMS']
    d['after_rate_osc'] = osc(out['after'], 'YawRateDegS')
    a0 = out['climb'][-1]['AltitudeM']
    d['climb_vz'] = last(out['climb'], 'VerticalSpeedMS', 0.2)
    d['hold_overshoot'] = max(r['AltitudeM'] for r in out['hold']) - a0
    d['hold_vz_end'] = abs(out['hold'][-1]['VerticalSpeedMS'])
    st = next((i for i, r in enumerate(out['brake']) if r['ForwardSpeedMS'] <= 0.5), None)
    d['brake_stop_s'] = None if st is None else st * (out['brake'][1]['t'] - out['brake'][0]['t'])
    d['hover_v'] = abs(out['hover'][-1]['ForwardSpeedMS'])
    d['hover_pitch_osc'] = osc(out['hover'], 'PitchDeg')
    d['hover_roll_osc'] = osc(out['hover'], 'RollDeg')
    return d

def main(keys):
    for key in keys:
        a = summary(fly(key, 1.0 / 30.0, PLAN))
        b = summary(fly(key, 1.0 / 120.0, PLAN))
        print('==', key)
        for k in a:
            va, vb = a[k], b[k]
            if va is None or vb is None:
                print('  %-16s %s / %s' % (k, va, vb))
            else:
                print('  %-16s %9.3f %9.3f   diff %+.3f' % (k, va, vb, vb - va))


if __name__ == '__main__':
    main(sys.argv[1:] or ['classic', 'galleon', 'skyracer', 'pointfly'])
