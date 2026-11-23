"""Calibration: replays the PIE runs in the sim and tables sim vs PIE (pie_ref.json, see pie_ref.py).

Replays (Classic, the v1 C++):
  val_* : the as_43 validation run (standalone, host pilot, DebugSetInput, fixed 30 fps). Each phase starts from the
          PIE state at its first 0.1 s sample (position, velocity, rotation, yaw rate, shaped controls, hold altitude,
          fuel) and gets the same inputs; the test map's ground (start platform top z 0 within 50 m of the origin,
          AS_Ground top -199.5 m elsewhere) is used for the traces.
  mp_*  : the as_45 multiplayer run 3 (client pilot): keys = IA_AirshipThrottle 0.3-2.3 s + IA_AirshipSteer 1.3-2.3 s
          injected on the client; fly0 / fly1 = DebugSetInput schedule on the client's ship without / with 100 ms
          each way.
  hover : 10 s neutral over the platform, wind phase unknown in PIE (UniqueID % 97): all 97 seeds.

Run: python3 calibrate.py  (about 10 s; writes calibration.json)
"""
import json
import math
import os

from airship_sim import (Sim, Classic, RawInput, run_raw, rot2quat, qrot, add, mul, D2R, DT, wrap180)

HERE = os.path.dirname(os.path.abspath(__file__))
REF = json.load(open(os.path.join(HERE, 'pie_ref.json')))


def test_map_ground(x, y):
    """L_AirshipTest: AS_StartPlatform (100 x 100 m, top z 0) and AS_Ground (top -19950 cm)."""
    if abs(x) <= 5000.0 and abs(y) <= 5000.0:
        return 0.0
    return -19950.0


def init_from_val(sim, s, hold_valid=True, boost_active=False, brake_was=False):
    b = sim.body
    b.q = rot2quat(s['PitchDeg'], s['YawDeg'], s['RollDeg'])
    loc = tuple(s['loc'])
    b.com = add(loc, qrot(b.q, b.com_local))
    b.v = tuple(s['vel'])
    b.w = (0.0, 0.0, s['YawRateDegS'] * D2R)
    fm = sim.server
    fm.sh_throttle, fm.sh_steer, fm.sh_lift, fm.sh_boost = s['Throttle'], s['Steer'], s['Lift'], s['Boost']
    fm.b_brake = bool(s['bBraking'])
    fm.brake_was = brake_was
    fm.fuel = s['BoostFuel']
    if hold_valid and abs(s['HoldAltitudeM'] - s['AltitudeM']) > 1e-3:
        fm.hold_z, fm.hold_valid = s['HoldAltitudeM'] * 100.0, True
    elif hold_valid:
        fm.hold_z, fm.hold_valid = s['AltitudeM'] * 100.0, True
    if boost_active:
        fm.boost_active, fm.last_kick, fm.regen_timer = True, sim.time, 0.0
    sim.server_tele = sim.tele_server()
    sim.snapshots.append(sim.server_tele)


def replay_val(phase):
    """Returns (pie samples, sim samples at the same times)."""
    ss = REF['val'][phase]
    s0 = ss[0]
    sim = Sim(Classic(), ground_fn=test_map_ground, seed=11)
    sim.set_time(s0['t'])
    init_from_val(sim, s0, hold_valid=True, boost_active=(phase == 'boost'), brake_was=(phase == 'brake'))
    t_first = s0['t']
    p_t0 = t_first - DT          # the input changed one frame before the first sample

    def sched(t, _sim):
        el = t + (t_first - p_t0)
        if phase == 'lift':
            return RawInput(lift=1.0 if el < 4.0 else (-1.0 if el < 8.0 else 0.0))
        if phase == 'throttle':
            return RawInput(throttle=1.0)
        if phase == 'steer':
            return RawInput(throttle=1.0, steer=1.0)
        if phase == 'boost':
            return RawInput(throttle=1.0, boost=True)
        if phase == 'brake':
            return RawInput(brake=True)
        return RawInput()

    n = len(ss)
    log = run_raw(sim, sched, (n - 1) * 0.1 + 1e-6)
    # sample k (0.1 k s after the first) = after 3 k frames
    rows = [None] * n
    rows[0] = dict(ForwardSpeedMS=s0['ForwardSpeedMS'], LateralSpeedMS=s0['LateralSpeedMS'], VerticalSpeedMS=s0['VerticalSpeedMS'],
                   AltitudeM=s0['AltitudeM'], YawRateDegS=s0['YawRateDegS'], RollDeg=s0['RollDeg'], PitchDeg=s0['PitchDeg'],
                   YawDeg=s0['YawDeg'], HoldAltitudeM=s0['HoldAltitudeM'], BoostFuel=s0['BoostFuel'], Boost=s0['Boost'],
                   Throttle=s0['Throttle'])
    for k in range(1, n):
        i = 3 * k - 1
        if i < len(log):
            rows[k] = log[i]
    return ss, rows, sim


KEYS = ['ForwardSpeedMS', 'LateralSpeedMS', 'VerticalSpeedMS', 'AltitudeM', 'YawRateDegS', 'RollDeg', 'PitchDeg']


def errors(pie, sim, keys=KEYS, upto=None):
    out = {}
    m = len(pie) if upto is None else upto
    for k in keys:
        d = [sim[i][k] - pie[i][k] for i in range(m) if sim[i] is not None]
        if k == 'YawDeg':
            d = [wrap180(x) for x in d]
        out[k] = dict(rms=math.sqrt(sum(x * x for x in d) / len(d)), max=max(abs(x) for x in d))
    return out


def hover_stats(n_seeds=97):
    """10 s neutral over the platform at 16.2 m: |pitch| max, |roll| max, altitude span, horizontal drift."""
    res = []
    for seed in range(n_seeds):
        sim = Sim(Classic(), alt_agl=16.2, pos_m=(-0.13, 25.1), ground_fn=test_map_ground, seed=seed)
        run_raw(sim, lambda t, s: RawInput(), 3.0)
        lg = run_raw(sim, lambda t, s: RawInput(), 10.0)
        p = max(abs(r['PitchDeg']) for r in lg[90:])
        ro = max(abs(r['RollDeg']) for r in lg[90:])
        alts = [r['AltitudeM'] for r in lg[90:]]
        a0, a1 = lg[0]['ActorLocCm'], lg[-1]['ActorLocCm']
        res.append(dict(seed=seed, pitch=p, roll=ro, alt_span=max(alts) - min(alts),
                        drift=math.hypot(a1[0] - a0[0], a1[1] - a0[1]) / 100.0))
    return res


def replay_mp(ph, latency_ms):
    """Client pilot. keys: Enhanced Input values on the client; fly0/fly1: the DebugSetInput schedule (the client's
    GatherLocalInput takes it in place of the keys, so both are RawInput here)."""
    rows = REF['mp'][ph]
    init = REF['mp'][ph + '_init']
    sim = Sim(Classic(), latency_ms=latency_ms, ground_fn=test_map_ground, seed=5, net='client')
    b = sim.body
    q = tuple(init['q'])
    b.q = q
    b.com = add(tuple(init['loc']), qrot(q, b.com_local))
    b.v = tuple(init['vel'])
    b.w = (0.0, 0.0, init['YawRateDegS'] * D2R)
    for fm in (sim.server, sim.pilot_fm):
        fm.sh_throttle, fm.sh_steer, fm.sh_lift, fm.sh_boost = init['Throttle'], init['Steer'], init['Lift'], init['Boost']
        fm.hold_z, fm.hold_valid = init['HoldAltitudeM'] * 100.0, True
    sim.server_tele = sim.tele_server()
    sim.snapshots = [sim.server_tele] * (sim.lag_frames + 2)
    ev = [e for e in REF['mp']['events'] if e['phase'] == ph]
    t_start = rows[0]['t'] - rows[0]['el']
    edges = [(e['t'] - t_start, e['edge'], e['input']) for e in ev]

    def sched(t, _sim):
        el = t + rows[0]['el']
        if ph == 'keys':
            return RawInput(throttle=1.0 if 0.3 <= el < 2.3 else 0.0, steer=1.0 if 1.3 <= el < 2.3 else 0.0)
        cur = (0.0, 0.0, 0.0, 0.0, False, False)
        for te, name, inp in edges:
            if el >= te + DT - 1e-6:   # the harness calls DebugSetInput in its tick; the pawn reads it the next frame
                cur = inp
        return RawInput(throttle=cur[0], steer=cur[1], lift=cur[2], strafe=cur[3], boost=cur[4], brake=cur[5])

    log = run_raw(sim, sched, len(rows) * DT - 1e-6)
    return rows, log, edges


def mp_latency(rows, log, edges, src):
    """Frames from the pilot's own controls changing to the server's controls / physics and the pilot's view of the
    physics (PIE harness thresholds: steer 0.05, yaw rate 0.5 deg/s, forward speed 0.1 / 0.3 m/s)."""
    out = {}
    for te, name, inp in edges:
        if not name.startswith('E'):
            continue
        k0 = next(i for i, r in enumerate(rows) if r['el'] >= te - 1e-6)
        b = k0 - 1
        if src == 'pie':
            S = lambda i: rows[i]['S']
            C = lambda i: rows[i]['C']
        else:
            S = lambda i: log[i]
            C = lambda i: log[i]['pilot']['view']
        Cc = (lambda i: rows[i]['C']) if src == 'pie' else (lambda i: dict(Steer=log[i]['pilot']['Steer'], Throttle=log[i]['pilot']['Throttle']))

        def first(fn):
            for i in range(k0, min(len(rows), len(log)) if src != 'pie' else len(rows)):
                try:
                    if fn(i):
                        return i
                except (KeyError, TypeError):
                    continue
            return None
        if name == 'E1_throttle':
            cc = first(lambda i: Cc(i)['Throttle'] > Cc(b)['Throttle'] + 0.05)
            sc = first(lambda i: S(i)['Throttle'] > S(b)['Throttle'] + 0.05)
            sp = first(lambda i: S(i)['ForwardSpeedMS'] > S(b)['ForwardSpeedMS'] + 0.1)
            cp = first(lambda i: C(i)['ForwardSpeedMS'] > C(b)['ForwardSpeedMS'] + 0.1)
        elif name in ('E2_steer_right', 'E3_steer_left'):
            sg = 1.0 if name == 'E2_steer_right' else -1.0
            cc = first(lambda i: sg * (Cc(i)['Steer'] - Cc(b)['Steer']) > 0.05)
            sc = first(lambda i: sg * (S(i)['Steer'] - S(b)['Steer']) > 0.05)
            sp = first(lambda i: sg * (S(i)['YawRateDegS'] - S(b)['YawRateDegS']) > 0.5)
            cp = first(lambda i: sg * (C(i)['YawRateDegS'] - C(b)['YawRateDegS']) > 0.5)
        else:
            cc = first(lambda i: (Cc(i).get('Throttle', 0) < Cc(b).get('Throttle', 0) - 0.05) or rows[i]['C'].get('Throttle', 0) < -0.01) if src == 'pie' else first(lambda i: log[i]['pilot']['Throttle'] < log[b]['pilot']['Throttle'] - 0.05)
            sc = first(lambda i: S(i)['bBraking'] is True)
            sp = first(lambda i: S(i)['ForwardSpeedMS'] < S(b)['ForwardSpeedMS'] - 0.3)
            cp = first(lambda i: C(i)['ForwardSpeedMS'] < C(b)['ForwardSpeedMS'] - 0.3)
        out[name] = dict(client_controls=cc, server_controls=sc, server_physics=sp, client_physics=cp, k0=k0)
    return out


def main():
    cal = {}
    lines = []
    P = lambda *a: lines.append(' '.join(str(x) for x in a))

    # ---------------------------------------------------------------------------------------------- val phases
    val = {}
    for ph in ('lift', 'throttle', 'steer', 'boost', 'brake'):
        pie, sim, s = replay_val(ph)
        upto = None
        if ph == 'boost':   # AS_Obstacle_1 clipped at 80.1 s (pie_validate f2): compare before the hit
            upto = next(i for i, r in enumerate(pie) if r['t'] > 80.05)
        val[ph] = dict(pie=pie, sim=sim, err=errors(pie, sim, upto=upto), upto=upto)
        e = val[ph]['err']
        P('%-8s rms/max err: ' % ph + ', '.join('%s %.2f/%.2f' % (k.replace('Speed', '').replace('MS', '').replace('Deg', ''), v['rms'], v['max']) for k, v in e.items()))
    cal['val_errors'] = {ph: v['err'] for ph, v in val.items()}

    def at(ph, t_rel, key, src):
        rows = val[ph]['pie'] if src == 'pie' else val[ph]['sim']
        k = int(round(t_rel / 0.1))
        return rows[k][key]

    # scalars (same definitions as the as_30 / as_43 checks)
    thr_p = val['throttle']['pie']
    thr_s = val['throttle']['sim']
    curve_p = [thr_p[min(10 * k - 1, len(thr_p) - 1)]['ForwardSpeedMS'] for k in range(1, 11)]
    curve_s = [thr_s[min(10 * k - 1, len(thr_s) - 1)]['ForwardSpeedMS'] for k in range(1, 11)]
    st_p, st_s = val['steer']['pie'], val['steer']['sim']
    lift_p, lift_s = val['lift']['pie'], val['lift']['sim']
    br_p, br_s = val['brake']['pie'], val['brake']['sim']
    bo_p, bo_s = val['boost']['pie'], val['boost']['sim']
    upto = val['boost']['upto']

    def tail(rows, a, b_, key, fn):
        vals = [r[key] for r in rows[a:b_] if r is not None]
        return fn(vals)

    def mean(v): return sum(v) / len(v)

    def half_time(rows, v0):
        for k, r in enumerate(rows):
            if r is not None and r['ForwardSpeedMS'] < 0.5 * v0:
                return 0.1 * k + DT
        return None

    rel1, rel2 = 90, 100   # samples 1 s and 2 s after the release (release at 8.0 s; sample k = 0.033 + 0.1 k s)
    table = [
        ('Lift +1 4 s: climb rate max (m/s)', tail(lift_p, 0, 40, 'VerticalSpeedMS', max), tail(lift_s, 0, 40, 'VerticalSpeedMS', max)),
        ('Lift +1 4 s: height gained (m)', lift_p[39]['AltitudeM'] - lift_p[0]['AltitudeM'], lift_s[39]['AltitudeM'] - lift_s[0]['AltitudeM']),
        ('Lift -1 4 s: sink rate min (m/s)', tail(lift_p, 40, 80, 'VerticalSpeedMS', min), tail(lift_s, 40, 80, 'VerticalSpeedMS', min)),
        ('Lift release (from -14 m/s): |vz| 1 s after (m/s)', abs(lift_p[rel1]['VerticalSpeedMS']), abs(lift_s[rel1]['VerticalSpeedMS'])),
        ('Lift release: |vz| 2 s after (m/s)', abs(lift_p[rel2]['VerticalSpeedMS']), abs(lift_s[rel2]['VerticalSpeedMS'])),
        ('Lift release: altitude 3 s after minus the held altitude (m)', lift_p[-1]['AltitudeM'] - lift_p[-1]['HoldAltitudeM'],
         lift_s[-1]['AltitudeM'] - lift_s[-1]['HoldAltitudeM']),
        ('Lift release: held altitude (m)', lift_p[-1]['HoldAltitudeM'], lift_s[-1]['HoldAltitudeM']),
        ('Lift: nose up while climbing (deg)', tail(lift_p, 0, 40, 'PitchDeg', max), tail(lift_s, 0, 40, 'PitchDeg', max)),
    ]
    for k in range(10):
        table.append(('Throttle: forward speed at %d s (m/s)' % (k + 1), curve_p[k], curve_s[k]))
    table += [
        ('Throttle: peak forward speed (m/s)', tail(thr_p, 0, 100, 'ForwardSpeedMS', max), tail(thr_s, 0, 100, 'ForwardSpeedMS', max)),
        ('Throttle: speed at 10 s (steady, m/s)', thr_p[-1]['ForwardSpeedMS'], thr_s[-1]['ForwardSpeedMS']),
        ('Throttle: nose pitch min (deg)', tail(thr_p, 0, 100, 'PitchDeg', min), tail(thr_s, 0, 100, 'PitchDeg', min)),
        ('Throttle: nose pitch max (deg)', tail(thr_p, 0, 100, 'PitchDeg', max), tail(thr_s, 0, 100, 'PitchDeg', max)),
        ('Throttle: altitude dip (m)', thr_p[0]['AltitudeM'] - tail(thr_p, 0, 100, 'AltitudeM', min), thr_s[0]['AltitudeM'] - tail(thr_s, 0, 100, 'AltitudeM', min)),
        ('Steer: yaw rate mean 2-8 s (deg/s)', tail(st_p, 20, 80, 'YawRateDegS', mean), tail(st_s, 20, 80, 'YawRateDegS', mean)),
        ('Steer: yaw rate at 0.4 s (deg/s)', st_p[4]['YawRateDegS'], st_s[4]['YawRateDegS']),
        ('Steer: bank 2-8 s min (deg)', tail(st_p, 20, 80, 'RollDeg', min), tail(st_s, 20, 80, 'RollDeg', min)),
        ('Steer: bank 2-8 s max (deg)', tail(st_p, 20, 80, 'RollDeg', max), tail(st_s, 20, 80, 'RollDeg', max)),
        ('Steer: nose pitch min (deg)', tail(st_p, 0, 80, 'PitchDeg', min), tail(st_s, 0, 80, 'PitchDeg', min)),
        ('Steer: slip speed at 8 s (m/s)', st_p[-1]['LateralSpeedMS'], st_s[-1]['LateralSpeedMS']),
        ('Steer: altitude lost (m)', st_p[0]['AltitudeM'] - st_p[-1]['AltitudeM'], st_s[0]['AltitudeM'] - st_s[-1]['AltitudeM']),
        ('Boost: forward speed at 3.0 s (m/s)', bo_p[upto - 1]['ForwardSpeedMS'], bo_s[upto - 1]['ForwardSpeedMS']),
        ('Boost: nose pitch min before the hit (deg)', tail(bo_p, 0, upto, 'PitchDeg', min), tail(bo_s, 0, upto, 'PitchDeg', min)),
        ('Boost: fuel at 3.0 s', bo_p[upto - 1]['BoostFuel'], bo_s[upto - 1]['BoostFuel']),
        ('Brake from %.1f m/s: speed at 1 s (m/s)' % br_p[0]['ForwardSpeedMS'], br_p[10]['ForwardSpeedMS'], br_s[10]['ForwardSpeedMS']),
        ('Brake: speed at 2 s (m/s)', br_p[20]['ForwardSpeedMS'], br_s[20]['ForwardSpeedMS']),
        ('Brake: half speed after (s)', half_time(br_p, br_p[0]['ForwardSpeedMS']), half_time(br_s, br_p[0]['ForwardSpeedMS'])),
        ('Brake: peak decel 0-0.4 s (g)', (br_p[0]['ForwardSpeedMS'] - br_p[4]['ForwardSpeedMS']) / 0.4 / 9.8,
         (br_s[0]['ForwardSpeedMS'] - br_s[4]['ForwardSpeedMS']) / 0.4 / 9.8),
        ('Brake: nose flare max (deg)', tail(br_p, 0, 40, 'PitchDeg', max), tail(br_s, 0, 40, 'PitchDeg', max)),
        ('Brake: climb over the latched hold (m)', tail(br_p, 0, 40, 'AltitudeM', max) - br_p[0]['HoldAltitudeM'],
         tail(br_s, 0, 40, 'AltitudeM', max) - br_p[0]['HoldAltitudeM']),
    ]

    # ---------------------------------------------------------------------------------------------- hover
    hs = hover_stats()
    pitches = sorted(h['pitch'] for h in hs)
    rolls = sorted(h['roll'] for h in hs)
    spans = sorted(h['alt_span'] for h in hs)
    hov_p = REF['val']['hover']
    table += [
        ('Hover 10 s: |pitch| max (deg), PIE runs 0.57 / 0.90; sim median of 97 wind seeds', 0.57, pitches[len(pitches) // 2]),
        ('Hover: |pitch| max over seeds, 10-90 %% range (%.2f-%.2f)' % (pitches[9], pitches[87]), 0.90, pitches[87]),
        ('Hover 10 s: |roll| max (deg), sim median', 0.04, rolls[len(rolls) // 2]),
        ('Hover 10 s: altitude span (m), sim median', 0.04, spans[len(spans) // 2]),
    ]
    cal['hover'] = dict(pitch_p10=pitches[9], pitch_med=pitches[len(pitches) // 2], pitch_p90=pitches[87],
                        roll_med=rolls[len(rolls) // 2], alt_span_med=spans[len(spans) // 2])

    # ---------------------------------------------------------------------------------------------- mp
    rows, log, edges = replay_mp('keys', 0.0)
    vmax_p = max(r['S']['ForwardSpeedMS'] for r in rows)
    vmax_s = max(l['ForwardSpeedMS'] for l in log)
    table.append(('MP keys (client): throttle 2 s + steer 1 s, max forward speed (m/s)', vmax_p, vmax_s))
    k23 = next(i for i, r in enumerate(rows) if r['el'] >= 2.3)
    table.append(('MP keys: forward speed at release 2.3 s (m/s)', rows[k23]['S']['ForwardSpeedMS'], log[k23]['ForwardSpeedMS']))
    lat = {}
    for ph, L in (('fly0', 0.0), ('fly1', 100.0)):
        rows, log, edges = replay_mp(ph, L)
        top_p = max(r['S']['ForwardSpeedMS'] for r in rows)
        top_s = max(l['ForwardSpeedMS'] for l in log)
        table.append(('MP %s (%s): top forward speed (m/s)' % (ph, 'no lag' if L == 0 else '100 ms each way'), top_p, top_s))
        n = min(len(rows), len(log))
        e_v = math.sqrt(sum((rows[i]['S']['ForwardSpeedMS'] - log[i]['ForwardSpeedMS']) ** 2 for i in range(n)) / n)
        e_y = math.sqrt(sum((rows[i]['S']['YawRateDegS'] - log[i]['YawRateDegS']) ** 2 for i in range(n)) / n)
        cal['mp_' + ph + '_rms'] = dict(forward_speed=e_v, yaw_rate=e_y)
        lp = mp_latency(rows, log, edges, 'pie')
        ls = mp_latency(rows, log, edges, 'sim')
        lat[ph] = dict(pie=lp, sim=ls)
        for edge in ('E1_throttle', 'E2_steer_right', 'E3_steer_left', 'E4_brake'):
            a, s_ = lp[edge], ls[edge]
            for k in ('server_controls', 'server_physics', 'client_physics'):
                if a[k] is not None and a['client_controls'] is not None and s_[k] is not None and s_['client_controls'] is not None:
                    table.append(('MP %s %s: %s, frames after the pilot\'s controls' % (ph, edge, k), a[k] - a['client_controls'],
                                  s_[k] - s_['client_controls']))
    cal['mp_latency'] = lat

    # ---------------------------------------------------------------------------------------------- print
    P('')
    P('%-82s %9s %9s %9s' % ('quantity', 'PIE', 'sim', 'sim-PIE'))
    rows_out = []
    for name, p, s in table:
        if p is None or s is None:
            P('%-82s %9s %9s' % (name, p, s))
            rows_out.append(dict(name=name, pie=p, sim=s, err=None))
            continue
        P('%-82s %9.2f %9.2f %+9.2f' % (name, p, s, s - p))
        rows_out.append(dict(name=name, pie=round(p, 3), sim=round(s, 3), err=round(s - p, 3)))
    cal['table'] = rows_out
    print('\n'.join(lines))
    json.dump(cal, open(os.path.join(HERE, 'calibration.json'), 'w'), indent=1, default=str)


if __name__ == '__main__':
    main()
