"""Extracts the PIE reference data the calibration replays (calibrate.py) compare against, into pie_ref.json.

Sources (Saved/ is git-ignored, so the extract is committed instead):
  Saved/Airship/val/val_result.json   validation run 2 (as_43_pie_validate.py = as_30 phases, standalone, host pilot,
                                      fixed 30 fps, telemetry every 0.1 s): hover, lift, throttle, steer, boost, brake
  Saved/Airship/mp/run3/mp_result.json multiplayer run 3 (as_45_pie_mp.py, listen server + 1 client, every frame):
                                      keys (real Enhanced Input path), fly0 (no lag), fly1 (Net PktLag=100 each way)

Run once with the clone's Saved folder present: python3 pie_ref.py
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..', '..', '..', '..'))
VAL = os.path.join(ROOT, 'Saved', 'Airship', 'val', 'val_result.json')
MP = os.path.join(ROOT, 'Saved', 'Airship', 'mp', 'run3', 'mp_result.json')
OUT = os.path.join(HERE, 'pie_ref.json')

KEYS = ['t', 'ForwardSpeedMS', 'LateralSpeedMS', 'VerticalSpeedMS', 'AltitudeM', 'HoldAltitudeM', 'YawRateDegS', 'RollDeg',
        'PitchDeg', 'YawDeg', 'Throttle', 'Steer', 'Lift', 'Boost', 'bBraking', 'BoostFuel', 'GroundClearanceM']


def r(x, n=4):
    if isinstance(x, bool) or x is None:
        return x
    if isinstance(x, (list, tuple)):
        return [r(v, n) for v in x]
    return round(float(x), n)


def main():
    out = {'sources': {'val': 'Saved/Airship/val/val_result.json (as_43 run 2, 2026-11-22)',
                       'mp': 'Saved/Airship/mp/run3/mp_result.json (as_45 run 3, 2026-11-22)'}}
    v = json.load(open(VAL))
    phases = {}
    for ph in ('hover', 'lift', 'throttle', 'steer', 'boost', 'brake'):
        ss = [s for s in v['series'] if s['ph'] == ph]
        phases[ph] = [dict({k: r(s.get(k)) for k in KEYS}, loc=r(s['loc'], 1), vel=r(s['vel'], 1)) for s in ss]
    out['val'] = phases
    out['val_checks'] = {k: v['checks'][k].get('summary') for k in ('b_hover', 'c_lift', 'd_throttle', 'e_steer', 'f_boost_brake')
                         if k in v['checks']}
    m = json.load(open(MP))
    mp = {}
    for ph in ('keys', 'fly0', 'fly1'):
        ss = [s for s in m['series'] if s.get('ph') == ph]
        rows = []
        for s in ss:
            S, C = s.get('S') or {}, s.get('C') or {}
            rows.append(dict(t=r(s['t'], 3), el=r(s.get('el'), 3),
                             S={k: r(S.get(k), 3) for k in ('ForwardSpeedMS', 'YawRateDegS', 'Throttle', 'Steer', 'bBraking', 'RollDeg',
                                                            'AltitudeM')},
                             C={k: r(C.get(k), 3) for k in ('ForwardSpeedMS', 'YawRateDegS', 'Throttle', 'Steer')},
                             Canim={k: r((C.get('anim') or {}).get(k), 3) for k in ('WheelAngleDeg', 'TurbineYawDeg_L')}))
        mp[ph] = rows
        S0 = ss[0].get('S') or {}
        mp[ph + '_init'] = {k: r(S0.get(k)) for k in ('loc', 'vel', 'q', 'RollDeg', 'PitchDeg', 'YawDeg', 'YawRateDegS', 'AltitudeM',
                                                      'HoldAltitudeM', 'Throttle', 'Steer', 'Lift', 'Boost', 'bBraking')}
    mp['events'] = [e for e in m['events'] if e.get('event') == 'client_input']
    mp['lat_fly0'] = m['mp'].get('lat_fly0')
    mp['lat_fly1'] = m['mp'].get('lat_fly1')
    mp['pktlag_ms'] = m['mp'].get('pktlag')
    out['mp'] = mp
    json.dump(out, open(OUT, 'w'), separators=(',', ':'))
    print('wrote', OUT, os.path.getsize(OUT), 'bytes')


if __name__ == '__main__':
    main()
